"""Receiver API uses only waveform samples and public protocol parameters."""
import argparse
import math
from collections import Counter
import numpy as np
from scipy import signal
from protocol import Config, PREAMBLE, symbols, symbol_bytes, checksum
import fec


def energy_tracks(x, fs, cfg):
    target = 12000
    divisor = math.gcd(fs, target)
    x = signal.resample_poly(x, target//divisor, fs//divisor)
    x = x - np.mean(x)
    n = cfg.symbol_ms * target/1000
    window = max(8, round(n*.65))
    t = np.arange(len(x))/target
    tracks = []
    for frequency in cfg.frequencies:
        mixed = x*np.exp(-2j*np.pi*frequency*t)
        sums = np.r_[0j, np.cumsum(mixed)]
        integrated = (sums[window:] - sums[:-window])/window
        energy = np.abs(integrated)**2
        tracks.append(np.pad(energy, (window//2, window-1-window//2)))
    return np.asarray(tracks), target, n


def decode(x, fs, cfg):
    cfg.validate()
    if len(x)/fs > 180 or len(x) < fs*.1:
        raise ValueError('请导入0.1～180秒的单轮完整录音')
    e, rate, n = energy_tracks(x, fs, cfg)
    total_energy = e.sum(axis=0)
    if total_energy.max() < 1e-12:
        return assemble([], [], cfg)
    fractions = e / (total_energy + 1e-20)
    pre = symbols(PREAMBLE, cfg)
    hop = max(1, round(n/8))
    starts = np.arange(0, max(0, e.shape[1]-round((len(pre)+1)*n)), hop)
    if not len(starts):
        return assemble([], [], cfg)
    score = np.zeros(len(starts))
    for j, value in enumerate(pre):
        centers = np.round(starts+(j+.5)*n).astype(int)
        score += fractions[value, centers]
    score /= len(pre)
    peaks, _ = signal.find_peaks(score, height=.70, distance=max(1, round(len(pre)*n*.7/hop)))
    if score[0] >= .70:
        peaks = np.r_[0, peaks]
    packets, rejected = [], []
    consumed = -1
    for peak in peaks:
        guess = starts[peak]
        if guess < consumed:
            continue
        trials = []
        for scale in (.996, .998, 1., 1.002, 1.004):
            step = n*scale
            for offset in np.linspace(-.35*n, .35*n, 9):
                start = guess + offset
                centers = np.round(start + (np.arange(len(pre))+.5)*step).astype(int)
                if centers.min() < 0 or centers.max() >= e.shape[1]:
                    continue
                quality = float(fractions[pre, centers].mean())
                if quality < .68:
                    continue
                # Equalize carrier response using known preamble symbols only.
                gains = np.array([np.median(e[k, centers[pre==k]]) for k in range(len(cfg.frequencies))])
                # Other known preamble symbols expose this carrier's interference
                # and window-leakage background. A per-carrier floor keeps its
                # median off-symbol response <= 1/4 after normalization while
                # allowing large, frequency-dependent speaker/microphone losses.
                background = np.array([np.median(e[k, centers[pre!=k]]) for k in range(len(cfg.frequencies))])
                gains = np.maximum(gains, np.maximum(4*background, 1e-15))

                def read(count,skip=0):
                    at = np.round(start+(len(pre)+skip+np.arange(count)+.5)*step).astype(int)
                    if at.min() < 0 or at.max() >= e.shape[1]:
                        return None
                    return np.argmax(e[:, at]/gains[:, None], axis=0)

                header_count=fec.symbol_count(3) if cfg.coding!='none' else 24//cfg.width
                header_values = read(header_count)
                if header_values is None:
                    continue
                if cfg.coding!='none':
                    header,raw_header,header_fixes,header_words=fec.decode(header_values,3)
                else:
                    header=symbol_bytes(header_values,cfg);header_fixes=header_words=0
                total, seq, length = header
                if not (4 <= total <= 8 and 1 <= seq <= total and 1 <= length <= 10):
                    continue
                if seq < total and length != 10:
                    continue
                tail_count=fec.symbol_count(length+cfg.check_size) if cfg.coding!='none' else (length+cfg.check_size)*8//cfg.width
                tail_values = read(tail_count,header_count)
                if tail_values is None:
                    continue
                if cfg.coding!='none':
                    tail,raw_tail,tail_fixes,tail_words=fec.decode(tail_values,length+cfg.check_size)
                else:
                    tail=symbol_bytes(tail_values,cfg);raw_tail=tail;tail_fixes=tail_words=0
                count=header_count+tail_count
                raw=header+tail
                payload = raw[3:3+length]
                ok = checksum(raw[:-cfg.check_size], cfg) == raw[-cfg.check_size:]
                trials.append(dict(seq=seq, total=total, length=length, payload_hex=payload.hex(),
                                   text=payload.decode('ascii', errors='replace'), checksum_ok=bool(ok),
                                   printable=all(32<=v<=126 for v in payload),
                                   start_s=max(0., float(start/rate)),
                                   end_s=float((start+(len(pre)+count)*step)/rate),
                                   sync_score=quality, symbol_ms=step/rate*1000,
                                   synchronized=True,coding=cfg.coding,
                                   fec_correction_attempts=header_fixes+tail_fixes,
                                   fec_codewords=header_words+tail_words,
                                   raw_payload_hex=raw_tail[:length].hex()))
        if trials:
            best = max(trials, key=lambda p:(p['checksum_ok'], p['sync_score']))
            packets.append(best)
            consumed = best['end_s']*rate - n
        else:
            rejected.append(dict(start_s=float(guess/rate), sync_score=float(score[peak]),
                                 reason='前导码候选：包头或长度无法解析'))
    return assemble(packets, rejected, cfg)


def assemble(packets, rejected, cfg):
    good = [p for p in packets if p['checksum_ok'] and p['printable']]
    votes = Counter(p['total'] for p in good)
    total = votes.most_common(1)[0][0] if votes else None
    selected, conflicts = {}, []
    for p in good:
        if p['total'] != total:
            continue
        seq = p['seq']
        if seq in selected and selected[seq]['payload_hex'] != p['payload_hex']:
            conflicts.append(seq)
        elif seq not in selected:
            selected[seq] = p
    for seq in set(conflicts):
        selected.pop(seq, None)
    missing = [i for i in range(1, total+1) if i not in selected] if total else []
    complete = total is not None and not missing
    display = ''.join(selected[i]['text'] if i in selected else f'[缺包{i}]'
                      for i in range(1, total+1)) if total else '尚未解析到有效包头'
    recovered = ''.join(selected[i]['text'] for i in range(1, total+1)) if complete else None
    return dict(scheme=cfg.scheme,coding=cfg.coding, packets=packets, rejected_candidates=rejected,
                total_packets=total, missing_sequences=missing, conflicting_sequences=sorted(set(conflicts)),
                complete=complete, recovered_text=recovered, display_text=display)


def main():
    from audio import read_wav, load_json, save_json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='独立接收：仅使用完整录音和协议参数')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--protocol', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    x, fs = read_wav(args.input)
    result = decode(x, fs, Config(**load_json(args.protocol)))
    save_json(args.output, result)
    print(result['display_text'])


if __name__ == '__main__':
    main()

"""Experiment files and CLI; decode first, evaluate separately."""
import argparse
import shutil
import math
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from audio import ROOT, load_json, save_json, write_wav, read_wav, sha256, convert_full
from protocol import Config, transmit
from receiver import decode
from metrics import assess


def prepare(folder, text, cfg, kind='quiet', level=0., seed=2026):
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('该实验目录已有文件，请新建实验或选择其他目录')
    cfg.validate()
    x, metadata = transmit(text, cfg, kind, level, seed)
    folder.mkdir(parents=True, exist_ok=True)
    write_wav(folder/'tx.wav', x, cfg.sample_rate)
    (folder/'send.txt').write_text(text, encoding='ascii')
    save_json(folder/'protocol.json', cfg.to_dict())
    metadata.update(tx_sha256=sha256(folder/'tx.wav'), text_sha256=sha256(folder/'send.txt'),
                    protocol_sha256=sha256(folder/'protocol.json'))
    save_json(folder/'transmission.json', metadata)
    return metadata


def receive(folder):
    folder = Path(folder)
    cfg = Config(**load_json(folder/'protocol.json'))
    x, fs = read_wav(folder/'rx.wav')
    result = decode(x, fs, cfg)
    result['rx_sha256'] = sha256(folder/'rx.wav')
    result['protocol_sha256'] = sha256(folder/'protocol.json')
    save_json(folder/'decoded.json', result)
    # Successful text is exact; incomplete rounds explicitly display missing packets.
    (folder/'rec.txt').write_text(result['recovered_text'] if result['complete'] else result['display_text'], encoding='utf-8')
    return result


def transmission_duration(folder):
    folder = Path(folder)
    tx = load_json(folder/'transmission.json')
    if tx['tx_sha256'] != sha256(folder/'tx.wav') or tx['text_sha256'] != sha256(folder/'send.txt'):
        raise ValueError('发送数据发生变化，请核对本轮实验')
    if tx.get('protocol_sha256') and tx['protocol_sha256'] != sha256(folder/'protocol.json'):
        raise ValueError('发送协议参数发生变化，请使用生成该音频时的参数')
    samples, fs = read_wav(folder/'tx.wav')
    duration = len(samples)/fs
    if abs(duration-tx['duration_s']) > 1/fs:
        raise ValueError('发送时长记录与实际WAV不一致')
    return duration


def evaluate(folder):
    folder = Path(folder)
    result = load_json(folder/'decoded.json')
    duration = transmission_duration(folder)
    if result['rx_sha256'] != sha256(folder/'rx.wav'):
        raise ValueError('接收数据已更新，请重新解码')
    if result.get('protocol_sha256') and result['protocol_sha256'] != sha256(folder/'protocol.json'):
        raise ValueError('解码参数已更新，请重新解码')
    report = assess((folder/'send.txt').read_text(encoding='ascii'), result, duration)
    save_json(folder/'metrics.json', report)
    return report


def import_recording(folder, source, conditions):
    folder, source = Path(folder), Path(source)
    if not (folder/'tx.wav').is_file():
        raise ValueError('请先生成本轮发送信号')
    if (folder/'rx.wav').exists():
        raise ValueError('本轮已有录音；再次采集请新建实验，保留原始记录')
    distance = float(conditions.get('distance_m',0))
    volume = float(conditions.get('system_volume',0))
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError('请填写本次实际距离（米）')
    if not math.isfinite(volume) or not 0 < volume <= 100:
        raise ValueError('请填写1～100范围内的电脑系统音量')
    conditions = dict(conditions,distance_m=distance,system_volume=volume)
    duration = transmission_duration(folder)
    if sha256(source)==sha256(folder/'tx.wav'):
        raise ValueError('请选择手机采集的完整录音，当前选择为发送音频')
    # Complete conversion, decoding and assessment before publishing trial files.
    # A failed import leaves the experiment available for another selection.
    with tempfile.TemporaryDirectory(prefix='.import_',dir=folder) as temporary:
        stage = Path(temporary)
        original = stage/('original'+source.suffix.lower())
        shutil.copy2(source, original)
        metadata = convert_full(original, stage/'rx.wav')
        if metadata['rx_sha256']==sha256(folder/'tx.wav'):
            raise ValueError('录音内容与发送WAV完全相同，请导入麦克风录音')
        x, fs = read_wav(stage/'rx.wav')
        result = decode(x,fs,Config(**load_json(folder/'protocol.json')))
        result.update(rx_sha256=metadata['rx_sha256'],protocol_sha256=sha256(folder/'protocol.json'))
        report = assess((folder/'send.txt').read_text(encoding='ascii'),result,duration)
        metadata.update(original_file=original.name,origin='physical_recording',
                        imported_at=datetime.now(timezone.utc).isoformat())
        save_json(stage/'recording.json',metadata)
        save_json(stage/'conditions.json',conditions)
        save_json(stage/'decoded.json',result)
        save_json(stage/'metrics.json',report)
        (stage/'rec.txt').write_text(result['recovered_text'] if result['complete'] else result['display_text'],encoding='utf-8')
        for path in stage.iterdir():
            path.replace(folder/path.name)
    return result, report


def main():
    p = argparse.ArgumentParser(description='声波通信生成、解码和评测')
    sub = p.add_subparsers(dest='command', required=True)
    send = sub.add_parser('send')
    send.add_argument('--folder', type=Path, required=True)
    send.add_argument('--text', required=True)
    send.add_argument('--scheme', choices=['BFSK','4FSK'],default='BFSK')
    send.add_argument('--coding',choices=['none','hamming15_11'],help='4FSK默认启用纠错；none用于旧方案对照')
    send.add_argument('--symbol-ms', type=float,default=10)
    send.add_argument('--interference',choices=['quiet','noise','tone'],default='quiet')
    send.add_argument('--level',type=float,default=0)
    for name in ['decode','evaluate','import']:
        q=sub.add_parser(name);q.add_argument('--folder',type=Path,required=True)
        if name=='import':
            q.add_argument('--source',type=Path,required=True)
            q.add_argument('--conditions',type=Path,required=True)
    a=p.parse_args()
    if a.command=='send':
        print(prepare(a.folder,a.text,Config(scheme=a.scheme,symbol_ms=a.symbol_ms,coding=a.coding or ('hamming15_11' if a.scheme=='4FSK' else 'none')),a.interference,a.level))
    elif a.command=='decode': print(receive(a.folder)['display_text'])
    elif a.command=='evaluate': print(evaluate(a.folder))
    else: print(import_recording(a.folder,a.source,load_json(a.conditions))[1])


if __name__=='__main__': main()

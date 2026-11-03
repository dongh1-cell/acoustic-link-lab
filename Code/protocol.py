"""ASCII framing and noncoherent FSK waveform generation."""
from dataclasses import dataclass, asdict
import binascii
import math
import numpy as np
import fec

PREAMBLE = bytes.fromhex('D391AC6B')


@dataclass
class Config:
    scheme: str = 'BFSK'
    sample_rate: int = 48000
    symbol_ms: float = 10.0
    gap_s: float = 0.2
    padding_s: float = 0.5
    amplitude: float = 0.22
    coding: str = 'none'

    def validate(self):
        if self.coding not in ('none','hamming15_11') or (self.scheme=='BFSK' and self.coding!='none'):
            raise ValueError('纠错编码适用于4FSK；可选none或hamming15_11')
        if self.scheme not in ('BFSK', '4FSK'):
            raise ValueError('方案应为 BFSK 或 4FSK')
        if self.sample_rate != 48000:
            raise ValueError('两方案统一采用 48000 Hz')
        if not 5 <= self.symbol_ms <= 20:
            raise ValueError('符号时长范围为 5～20 ms')
        if not 0 <= self.gap_s <= .5 or not 0 <= self.padding_s <= 2:
            raise ValueError('包间隔应在0～0.5秒，首尾静音应在0～2秒')
        if not 0 < self.amplitude <= .25:
            raise ValueError('信号幅度范围为0～0.25，以保留叠加干扰的余量')
        return self

    @property
    def frequencies(self):
        return (2000, 3000) if self.scheme == 'BFSK' else (1500, 2000, 2500, 3000)

    @property
    def width(self):
        return 1 if self.scheme == 'BFSK' else 2

    @property
    def check_size(self):
        return 1 if self.scheme == 'BFSK' else 2

    def to_dict(self):
        return asdict(self)


def validate_text(text):
    if not 40 <= len(text) <= 80 or any(not 32 <= ord(c) <= 126 for c in text):
        raise ValueError('请输入40～80个可打印ASCII字符（英文、数字、空格、英文标点）')
    return text.encode('ascii')


def checksum(data, cfg):
    if cfg.scheme == '4FSK':
        return binascii.crc_hqx(data, 0xFFFF).to_bytes(2, 'big')
    value = 0
    for byte in data:
        value ^= byte
    return bytes([value])


def split_text(text):
    raw = validate_text(text)
    return [raw[i:i+10] for i in range(0, len(raw), 10)]


def frame(payload, total, seq, cfg):
    body = bytes([total, seq, len(payload)]) + payload
    return PREAMBLE + body + checksum(body, cfg)


def symbols(data, cfg):
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    return bits if cfg.width == 1 else bits.reshape(-1, 2) @ np.array([2, 1])


def symbol_bytes(values, cfg):
    values = np.asarray(values, dtype=np.uint8)
    bits = values if cfg.width == 1 else np.column_stack((values >> 1, values & 1)).ravel()
    return np.packbits(bits).tobytes()


def modulate(data, cfg):
    return modulate_symbols(wire_symbols(data,cfg),cfg)


def wire_symbols(data,cfg):
    if cfg.coding=='none':return symbols(data,cfg)
    return np.concatenate((symbols(data[:4],cfg),fec.encode(data[4:7]),fec.encode(data[7:])))


def modulate_symbols(values,cfg):
    n = round(cfg.sample_rate * cfg.symbol_ms / 1000)
    freqs = np.repeat(np.array(cfg.frequencies)[values], n)
    phase = 2 * np.pi * np.cumsum(freqs) / cfg.sample_rate
    wave = cfg.amplitude * np.sin(phase)
    # Smooth the two packet edges while retaining continuous phase internally.
    edge = max(1, round(.001 * cfg.sample_rate))
    ramp = np.sin(np.linspace(0, np.pi/2, edge)) ** 2
    wave[:edge] *= ramp
    wave[-edge:] *= ramp[::-1]
    return wave


def transmit(text, cfg, interference='quiet', level=0.0, seed=2026):
    cfg.validate()
    chunks = split_text(text)
    parts = [np.zeros(round(cfg.padding_s * cfg.sample_rate))]
    packets = []
    position = len(parts[0])
    for i, payload in enumerate(chunks, 1):
        raw = frame(payload, len(chunks), i, cfg)
        wave = modulate(raw, cfg)
        packets.append(dict(seq=i, total=len(chunks), length=len(payload),
                            payload=payload.decode('ascii'), start_s=position/cfg.sample_rate,
                            end_s=(position+len(wave))/cfg.sample_rate))
        parts.append(wave)
        position += len(wave)
        if i < len(chunks):
            gap = np.zeros(round(cfg.gap_s * cfg.sample_rate))
            parts.append(gap)
            position += len(gap)
    parts.append(np.zeros(round(cfg.padding_s * cfg.sample_rate)))
    clean = np.concatenate(parts)
    if len(clean)/cfg.sample_rate > 30:
        raise ValueError('单轮发送时长超过30秒，请缩短符号时长')
    if interference not in ('quiet', 'noise', 'tone') or not 0 <= level <= 2:
        raise ValueError('干扰类型为quiet/noise/tone；RMS比例范围0～2')
    if interference == 'quiet' and level != 0:
        raise ValueError('安静测试的干扰比例应为0')
    t = np.arange(len(clean))/cfg.sample_rate
    rng = np.random.default_rng(seed)
    if interference == 'noise':
        noise = rng.normal(size=len(clean))
    elif interference == 'tone':
        noise = np.sin(2*np.pi*2000*t)
    else:
        noise = np.zeros(len(clean))
    rms = np.sqrt(np.mean(noise**2))
    if rms > 0:
        noise *= level * cfg.amplitude/math.sqrt(2)/rms
    result = clean + noise
    if np.max(np.abs(result)) >= .98:
        raise ValueError('混合信号峰值超限，请降低信号幅度或干扰强度')
    return result, dict(packets=packets, duration_s=len(result)/cfg.sample_rate,
                       interference=interference, interference_rms_ratio=level,
                       interference_frequency_hz=2000 if interference == 'tone' else None,
                       seed=seed, peak=float(np.max(np.abs(result))))

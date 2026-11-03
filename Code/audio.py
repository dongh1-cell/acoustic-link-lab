"""Preserve full recordings; convert compressed phone files with bundled FFmpeg."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parent.parent


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_wav(path, channel=0):
    fs, raw = wavfile.read(str(path))
    if raw.ndim == 2:
        if not 0 <= channel < raw.shape[1]:
            raise ValueError('录音声道不存在')
        raw = raw[:, channel]
    if raw.dtype.kind == 'i':
        data = raw.astype(float) / (2 ** (raw.dtype.itemsize*8-1))
    elif raw.dtype == np.uint8:
        data = (raw.astype(float)-128)/128
    else:
        data = raw.astype(float)
    if not len(data) or not np.isfinite(data).all():
        raise ValueError('录音为空或含无效采样')
    return data, int(fs)


def write_wav(path, data, fs=48000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(path), fs, np.round(np.clip(data, -1, 32767/32768)*32768).astype(np.int16))


def convert_full(source, destination):
    source, destination = Path(source), Path(destination)
    if source.suffix.lower() == '.wav':
        data, fs = read_wav(source)
        write_wav(destination, data, fs)
    else:
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v','error','-nostdin','-y',
                        '-i', str(source), '-af','pan=mono|c0=c0','-c:a','pcm_s16le',
                        str(destination)], check=True, capture_output=True)
    data, fs = read_wav(destination)
    return dict(original_sha256=sha256(source), rx_sha256=sha256(destination),
                samples=len(data), sample_rate=fs, duration_s=len(data)/fs,
                selected_channel=0, clipped_fraction=float(np.mean(np.abs(data)>=.999)),
                conversion='完整时长，首声道，原采样率，PCM16')

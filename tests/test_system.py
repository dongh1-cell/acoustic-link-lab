"""Automated verification uses synthetic audio stored only under work/."""
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
import json
import numpy as np
from scipy.signal import resample_poly, butter, sosfilt

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
from protocol import *
from receiver import decode,assemble
from metrics import assess,aggregate
from workflow import prepare,receive,evaluate
from audio import write_wav,save_json,load_json
from batch import TEXTS


class SystemTests(unittest.TestCase):
    def test_ascii_lengths_and_constraints(self):
        for scheme in ['BFSK','4FSK']:
            for size in (40,43,55,80):
                for ms in (5,8,10,15,20):
                    with self.subTest(scheme=scheme,size=size,ms=ms):
                        rng=np.random.default_rng(size)
                        text=''.join(chr(int(v)) for v in rng.integers(32,127,size))
                        c=Config(scheme=scheme,symbol_ms=ms)
                        x,m=transmit(text,c)
                        r=decode(np.r_[np.zeros(17333),x,np.zeros(7161)],48000,c)
                        self.assertEqual(r['recovered_text'],text)
                        self.assertEqual(len(r['packets']),math.ceil(size/10))
                        self.assertLessEqual(m['duration_s'],30)

    def test_invalid_text(self):
        for text in ['short','中'*50,'a'*81,'a'*39,'a'*40+'\n']:
            with self.assertRaises(ValueError):transmit(text,Config())

    def test_crc_standard_vector(self):
        self.assertEqual(checksum(b'123456789',Config(scheme='4FSK')).hex(),'29b1')

    def test_example_framing(self):
        text='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 hello!'
        chunks=split_text(text)
        self.assertEqual(len(chunks),5);self.assertEqual(chunks[-1],b'lo!')
        self.assertEqual(frame(chunks[0],5,1,Config())[-1],5)
        self.assertEqual(frame(chunks[-1],5,5,Config())[-1],0x21)

    def test_random_gain_noise_and_channel(self):
        rng=np.random.default_rng(912)
        for scheme in ['BFSK','4FSK']:
            for seed in range(4):
                c=Config(scheme=scheme)
                text=''.join(chr(v) for v in rng.integers(32,127,57))
                x,_=transmit(text,c)
                x=sosfilt(butter(3,[1100,3600],fs=48000,btype='bandpass',output='sos'),x)
                x=x*.2+rng.normal(0,.001,len(x))
                x=np.r_[rng.normal(0,.001,int(rng.integers(2000,42000))),x]
                self.assertEqual(decode(x,48000,c)['recovered_text'],text)

    def test_sample_rates_and_clock(self):
        for scheme in ['BFSK','4FSK']:
            c=Config(scheme=scheme);x,_=transmit(TEXTS[0],c)
            self.assertEqual(decode(resample_poly(x,147,160),44100,c)['recovered_text'],TEXTS[0])
            self.assertEqual(decode(resample_poly(x,1001,1000),48000,c)['recovered_text'],TEXTS[0])

    def make_stream(self,frames,c):
        parts=[np.zeros(13817)]
        for raw in frames:parts.extend([modulate(raw,c),np.zeros(9600)])
        return np.concatenate(parts)

    def test_missing_duplicate_reordered(self):
        for scheme in ['BFSK','4FSK']:
            c=Config(scheme=scheme);chunks=split_text(TEXTS[0])
            frames=[frame(p,len(chunks),i,c) for i,p in enumerate(chunks,1)]
            r=decode(self.make_stream([frames[i] for i in [2,0,0,5,1,4,3]],c),48000,c)
            self.assertEqual(r['recovered_text'],TEXTS[0]);self.assertEqual(assess(TEXTS[0],r,10)['loss_rate'],0)
            r=decode(self.make_stream([frames[i] for i in [0,2,3,4,5]],c),48000,c)
            m=assess(TEXTS[0],r,10)
            self.assertEqual(m['lost_packets'],1);self.assertEqual(m['compared_bits'],(len(TEXTS[0])-10)*8)
            self.assertIsNone(r['recovered_text'])

    def test_checksum_failure_counts_in_ber(self):
        for scheme in ['BFSK','4FSK']:
            c=Config(scheme=scheme);chunks=split_text(TEXTS[0])
            frames=[frame(p,len(chunks),i,c) for i,p in enumerate(chunks,1)]
            damaged=bytearray(frames[1]);damaged[len(PREAMBLE)+3]^=1;frames[1]=bytes(damaged)
            r=decode(self.make_stream(frames,c),48000,c);m=assess(TEXTS[0],r,10)
            self.assertEqual(m['error_bits'],1);self.assertEqual(m['compared_bits'],len(TEXTS[0])*8)
            self.assertEqual(m['lost_packets'],1);self.assertFalse(r['complete'])

    def test_silence_and_noise(self):
        for c in [Config(),Config(scheme='4FSK')]:
            for x in [np.zeros(48000),np.random.default_rng(42).normal(0,.01,48000*4)]:
                r=decode(x,48000,c);self.assertIsNone(r['recovered_text'])
                m=assess(TEXTS[0],r,4);self.assertIsNone(m['ber']);self.assertEqual(m['loss_rate'],1)

    def test_conflicting_valid_duplicates(self):
        c=Config();chunks=split_text(TEXTS[0]);frames=[frame(p,len(chunks),i,c) for i,p in enumerate(chunks,1)]
        frames.insert(1,frame(b'0123456789',len(chunks),1,c))
        r=decode(self.make_stream(frames,c),48000,c)
        self.assertEqual(r['conflicting_sequences'],[1]);self.assertFalse(r['complete'])

    def test_independent_cli_and_cwd(self):
        folder=Path(tempfile.mkdtemp(dir=ROOT/'work',prefix='isolated_'))
        c=Config(scheme='4FSK');text=TEXTS[2];x,_=transmit(text,c)
        write_wav(folder/'recording.wav',np.r_[np.zeros(12127),x])
        save_json(folder/'public.json',c.to_dict())
        p=subprocess.run([sys.executable,str(ROOT/'Code/receiver.py'),'--input',str(folder/'recording.wav'),
                          '--protocol',str(folder/'public.json'),'--output',str(folder/'decoded.json')],cwd=folder,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(load_json(folder/'decoded.json')['recovered_text'],text)

    def test_full_workflow_and_aggregation(self):
        parent=Path(tempfile.mkdtemp(dir=ROOT/'work',prefix='workflow_'));rows=[]
        for scheme in ['BFSK','4FSK']:
            folder=parent/scheme;cfg=Config(scheme=scheme)
            prepare(folder,TEXTS[0],cfg);x,_=transmit(TEXTS[0],cfg)
            write_wav(folder/'rx.wav',np.r_[np.zeros(3217),x])
            receive(folder);rows.append(evaluate(folder))
        self.assertGreater(rows[1]['throughput_bps'],rows[0]['throughput_bps']*1.5)
        a=aggregate(rows);self.assertEqual(a['total_rounds'],2);self.assertEqual(a['text_recovery_rate'],1)
        save_json(ROOT/'work/software_validation_example.json',dict(kind='synthetic_only',results=rows))

    def test_compressed_import_full_duration(self):
        from workflow import import_recording
        from audio import read_wav,sha256
        import imageio_ffmpeg
        parent=Path(tempfile.mkdtemp(dir=ROOT/'work',prefix='import_test_'))
        cfg=Config(scheme='4FSK');text=TEXTS[1]
        prepare(parent/'trial',text,cfg)
        x,_=transmit(text,cfg);x=np.r_[np.zeros(12345),x*.6,np.zeros(23456)]
        write_wav(parent/'synthetic.wav',x)
        proc=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(parent/'synthetic.wav'),
                             '-c:a','aac','-b:a','128k',str(parent/'synthetic.m4a')],capture_output=True)
        self.assertEqual(proc.returncode,0)
        result,metrics=import_recording(parent/'trial',parent/'synthetic.m4a',
                      dict(distance_m=1,system_volume=50,environment='synthetic unit test',
                           playback_device='test',recording_device='test'))
        self.assertEqual(result['recovered_text'],text)
        actual,fs=read_wav(parent/'trial/rx.wav')
        self.assertGreaterEqual(len(actual)/fs,len(x)/48000-.03)
        self.assertEqual(sha256(parent/'synthetic.m4a'),sha256(parent/'trial/original.m4a'))
        with self.assertRaises(ValueError):import_recording(parent/'trial',parent/'synthetic.m4a',dict(distance_m=1,system_volume=50))

    def test_summary_pairing_and_empty_readiness(self):
        from batch import create_batch
        from summary import summarize
        parent=Path(tempfile.mkdtemp(dir=ROOT/'work',prefix='summary_test_'))
        plan=create_batch(parent/'data',pilot=True)
        status=summarize(parent/'data',parent/'results')
        self.assertEqual(status['completed_rounds'],0);self.assertEqual(len(status['pending']),2)
        self.assertFalse(list((parent/'results').glob('*.png')))
        for row in plan:
            folder=parent/'data'/row['folder'];cfg=Config(scheme=row['scheme']);x,_=transmit(row['text'],cfg)
            write_wav(folder/'rx.wav',np.r_[np.zeros(1234),x]);receive(folder);evaluate(folder)
            import shutil
            shutil.copy2(folder/'rx.wav',folder/'original.wav')
            from audio import sha256
            save_json(folder/'recording.json',dict(origin='physical_recording',rx_sha256=sha256(folder/'rx.wav'),
                       original_sha256=sha256(folder/'original.wav'),original_file='original.wav'))
            save_json(folder/'conditions.json',dict(playback_device='unit test',recording_device='unit test',
                       distance_m=1,system_volume=50,environment='synthetic test fixture'))
        status=summarize(parent/'data',parent/'results');self.assertEqual(status['completed_rounds'],2)
        self.assertEqual(status['condition_mismatches'],[])
        save_json(parent/'data'/plan[1]['folder']/'conditions.json',dict(distance_m=2))
        status=summarize(parent/'data',parent/'results');self.assertEqual(len(status['condition_mismatches']),1)


if __name__=='__main__':unittest.main(verbosity=2)

"""FEC checks use synthetic waveforms, independent of physical measurements."""
from pathlib import Path
import sys,unittest
import subprocess,tempfile
from scipy.signal import resample_poly,butter,sosfilt
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Code'))
import fec
from protocol import *
from receiver import decode
from metrics import assess
from audio import save_json,write_wav,load_json
from batch import TEXTS

class FecTests(unittest.TestCase):
    def test_single_errors_and_padding(self):
        rng=np.random.default_rng(22)
        for size in range(1,14):
            data=rng.integers(0,256,size,dtype=np.uint8).tobytes();v=fec.encode(data)
            words=(size*8+10)//11
            self.assertEqual(len(v),fec.symbol_count(size))
            self.assertEqual(fec.decode(v,size)[0],data)
            # Every codeword position is exercised, including parity and padding.
            for bit in range(words*15):
                damaged=v.copy();damaged[bit//2]^=2 if bit%2==0 else 1
                out,raw,attempts,count=fec.decode(damaged,size)
                self.assertEqual(out,data);self.assertEqual(attempts,1)

    def test_interleaved_burst(self):
        data=b'abcdefghij12';v=fec.encode(data);words=(len(data)*8+10)//11
        bits=np.column_stack((v>>1,v&1)).ravel()
        for start in range(0,words*15-words+1):
            damaged=bits.copy();damaged[start:start+words]^=1
            symbols=damaged.reshape(-1,2)@np.array([2,1])
            self.assertEqual(fec.decode(symbols,len(data))[0],data)

    def test_clean_20_combinations(self):
        for length in (40,43,55,80):
            text=''.join(chr(v) for v in np.random.default_rng(length).integers(32,127,length))
            for ms in (5,8,10,15,20):
                cfg=Config(scheme='4FSK',symbol_ms=ms,coding='hamming15_11')
                x,m=transmit(text,cfg)
                result=decode(np.r_[np.zeros(17333),x,np.zeros(7000)],48000,cfg)
                self.assertEqual(result['recovered_text'],text)
                self.assertLessEqual(m['duration_s'],30)

    def stream(self,cfg,burst=1):
        chunks=split_text(TEXTS[0]);parts=[np.zeros(17000)]
        for seq,p in enumerate(chunks,1):
            v=wire_symbols(frame(p,len(chunks),seq,cfg),cfg)
            header=fec.symbol_count(3) if cfg.coding!='none' else 12
            # Force wrong payload symbols after synchronization/header.
            pos=16+header+(9 if cfg.coding!='none' else 0)
            v[pos:pos+burst]^=3
            parts.extend([modulate_symbols(v,cfg),np.zeros(9600)])
        return np.concatenate(parts)

    def test_waveform_correction_and_crc_failure(self):
        cfg=Config(scheme='4FSK',coding='hamming15_11')
        recovered=decode(self.stream(cfg),48000,cfg)
        m=assess(TEXTS[0],recovered,8.34)
        self.assertEqual(m['complete_rounds'],1)
        self.assertGreater(m['pre_fec_error_bits'],0);self.assertEqual(m['error_bits'],0)
        self.assertGreater(m['fec_correction_attempts'],0)
        old=Config(scheme='4FSK');plain=decode(self.stream(old),48000,old)
        self.assertFalse(plain['complete'])
        severe=decode(self.stream(cfg,burst=25),48000,cfg)
        self.assertFalse(severe['complete'])
        save_json(ROOT/'work/fec_waveform_validation.json',dict(kind='synthetic_controlled_symbol_errors',
            coded=m,uncoded=assess(TEXTS[0],plain,6.48),severe=assess(TEXTS[0],severe,8.34)))

    def test_header_correction(self):
        cfg=Config(scheme='4FSK',coding='hamming15_11');parts=[np.zeros(12000)]
        chunks=split_text(TEXTS[1])
        for i,p in enumerate(chunks,1):
            v=wire_symbols(frame(p,len(chunks),i,cfg),cfg);v[19]^=3
            parts.extend([modulate_symbols(v,cfg),np.zeros(9600)])
        self.assertEqual(decode(np.concatenate(parts),48000,cfg)['recovered_text'],TEXTS[1])

    def test_throughput_budget(self):
        text=TEXTS[0];_,base=transmit(text,Config())
        _,new=transmit(text,Config(scheme='4FSK',coding='hamming15_11'))
        self.assertAlmostEqual(new['duration_s'],8.34)
        self.assertGreater(base['duration_s']/new['duration_s'],1.25)

    def test_resampling_clock_and_channel(self):
        cfg=Config(scheme='4FSK',coding='hamming15_11');x,_=transmit(TEXTS[2],cfg)
        x=sosfilt(butter(3,[1100,3600],fs=48000,btype='bandpass',output='sos'),x)
        x=x*.3+np.random.default_rng(17).normal(0,.001,len(x))
        for audio,rate in [(resample_poly(x,147,160),44100),(resample_poly(x,1001,1000),48000)]:
            self.assertEqual(decode(np.r_[np.zeros(16003),audio],rate,cfg)['recovered_text'],TEXTS[2])

    def test_independent_fec_receiver(self):
        cfg=Config(scheme='4FSK',coding='hamming15_11')
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            p=Path(d);write_wav(p/'rx.wav',self.stream(cfg));save_json(p/'protocol.json',cfg.to_dict())
            result=subprocess.run([sys.executable,str(ROOT/'Code/receiver.py'),'--input',str(p/'rx.wav'),
                '--protocol',str(p/'protocol.json'),'--output',str(p/'decoded.json')],cwd=p,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(load_json(p/'decoded.json')['recovered_text'],TEXTS[0])

if __name__=='__main__':unittest.main(verbosity=2)

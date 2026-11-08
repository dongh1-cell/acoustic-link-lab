"""Additional receiver boundaries and transactional import regression checks."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
from audio import read_wav,write_wav,load_json,save_json
from batch import TEXTS,create_batch
from protocol import Config,transmit
from receiver import decode
from workflow import prepare,import_recording
from summary import summarize
from audit import audit


class CoreAuditTests(unittest.TestCase):
    def test_publish_failure_preserves_retry_and_prior_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);trial=root/'trial'
            prepare(trial,TEXTS[0],Config())
            x,fs=read_wav(trial/'tx.wav')
            write_wav(root/'synthetic.wav',np.r_[np.zeros(10813),x*.6,np.zeros(7000)],fs)
            # An old derived file is retained when publication fails.
            old=b'previous derived output\n'
            (trial/'decoded.json').write_bytes(old)
            replace=Path.replace
            def fail_manifest(path,target):
                if path.name=='recording.json' and path.parent.name.startswith('.import_'):
                    self.assertTrue((trial/'rx.wav').exists())
                    raise OSError('injected publication failure')
                return replace(path,target)
            conditions=dict(distance_m=.7,system_volume=50,environment='synthetic test')
            with patch.object(Path,'replace',fail_manifest):
                with self.assertRaises(OSError):import_recording(trial,root/'synthetic.wav',conditions)
            self.assertEqual((trial/'decoded.json').read_bytes(),old)
            self.assertFalse((trial/'rx.wav').exists())
            self.assertFalse((trial/'recording.json').exists())
            self.assertFalse((trial/'original.wav').exists())
            self.assertFalse(list(trial.glob('.import_*')))
            result,metrics=import_recording(trial,root/'synthetic.wav',conditions)
            self.assertEqual(result['recovered_text'],TEXTS[0])
            self.assertEqual(metrics['complete_rounds'],1)
            self.assertEqual(load_json(trial/'recording.json')['rx_sha256'],result['rx_sha256'])

    def test_contiguous_packets_and_recording_start_boundary(self):
        for scheme,coding in [('BFSK','none'),('4FSK','hamming15_11')]:
            cfg=Config(scheme=scheme,coding=coding,gap_s=0,padding_s=0)
            x,_=transmit(TEXTS[0],cfg)
            result=decode(x,48000,cfg)
            self.assertEqual(result['recovered_text'],TEXTS[0])
            self.assertEqual(len(result['packets']),6)

    def test_high_interference_with_peak_headroom(self):
        for kind in ('noise','tone'):
            for scheme,coding in [('BFSK','none'),('4FSK','hamming15_11')]:
                cfg=Config(scheme=scheme,coding=coding,amplitude=.005)
                x,metadata=transmit(TEXTS[0],cfg,kind,20)
                self.assertTrue(np.isfinite(x).all())
                self.assertLess(np.abs(x).max(),.98)
                self.assertEqual(metadata['interference_rms_ratio'],20)
            with self.assertRaisesRegex(ValueError,'峰值'):
                transmit(TEXTS[0],Config(),kind,20)
        with self.assertRaises(ValueError):transmit(TEXTS[0],Config(amplitude=.005),'noise',21)

    def test_invalid_conditions_are_isolated_per_round(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);plan=create_batch(root/'data',pilot=True)
            conditions=dict(distance_m=.7,system_volume=50,environment='synthetic test',
                            playback_device='test',recording_device='test')
            for row in plan:
                folder=root/'data'/row['folder'];x,fs=read_wav(folder/'tx.wav')
                write_wav(root/'fixture.wav',np.r_[np.zeros(7003),x*.6],fs)
                import_recording(folder,root/'fixture.wav',conditions)
            for invalid in ([],None):
                with self.subTest(invalid=invalid):
                    save_json(root/'data'/plan[0]['folder']/'conditions.json',invalid)
                    status=summarize(root/'data',root/'results')
                    self.assertEqual(status['completed_rounds'],1)
                    self.assertEqual(len(status['invalid_rounds']),1)
                    self.assertIn('conditions.json',status['invalid_rounds'][0]['reason'])
                    self.assertEqual(status['pending'],[plan[0]['id']])

    def test_malformed_report_review_keeps_other_checks_running(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);(root/'report').mkdir()
            for content in ('{broken','[]','null'):
                with self.subTest(content=content):
                    (root/'report/review.json').write_text(content,encoding='utf-8')
                    status=audit(root)
                    self.assertFalse(status['ready'])
                    self.assertTrue(any('review.json' in item for item in status['pending']))
                    self.assertTrue(any('演示视频' in item for item in status['pending']))
                    self.assertEqual(load_json(root/'Results/readiness.json'),status)


if __name__=='__main__':unittest.main(verbosity=2)

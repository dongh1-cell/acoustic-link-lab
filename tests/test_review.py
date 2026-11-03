"""Regression checks for findings from the assignment compliance audit."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
from audio import load_json,save_json,write_wav,read_wav
from workflow import prepare,import_recording,evaluate
from protocol import Config,transmit
from batch import TEXTS,create_batch
from coverage import inspect_plan
from summary import summarize


class AuditTests(unittest.TestCase):
    def test_failed_import_is_retryable(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            p=Path(d);folder=p/'trial';prepare(folder,TEXTS[0],Config())
            write_wav(p/'short.wav',np.zeros(100))
            conditions=dict(distance_m=.7,system_volume=50)
            with self.assertRaises(ValueError):import_recording(folder,p/'short.wav',conditions)
            self.assertFalse((folder/'rx.wav').exists());self.assertFalse((folder/'recording.json').exists())
            self.assertFalse(list(folder.glob('.import_*')))
            x,_=transmit(TEXTS[0],Config());write_wav(p/'synthetic.wav',np.r_[np.zeros(7613),x*.7])
            r,m=import_recording(folder,p/'synthetic.wav',conditions)
            self.assertEqual(r['recovered_text'],TEXTS[0]);self.assertEqual(m['complete_rounds'],1)

    def test_conditions_validated_for_cli(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            p=Path(d);prepare(p/'trial',TEXTS[0],Config());write_wav(p/'audio.wav',np.zeros(48000))
            for c in [dict(distance_m=float('nan'),system_volume=50),dict(distance_m=.7,system_volume=200),dict(distance_m=.7,system_volume=float('inf'))]:
                with self.assertRaises(ValueError):import_recording(p/'trial',p/'audio.wav',c)
            self.assertFalse((p/'trial/rx.wav').exists())

    def test_plan_coverage(self):
        plan=load_json(ROOT/'Data/formal/plan.json');self.assertEqual(inspect_plan(plan),[])
        short=[r for r in plan if r['round']!=3]
        self.assertTrue(any('3段' in s for s in inspect_plan(short)))
        mismatched=copy.deepcopy(plan);mismatched[1]['text']+='X'
        self.assertTrue(any('配对发送文本不同' in s for s in inspect_plan(mismatched)))
        self.assertTrue(inspect_plan([]))

    def test_missing_rec_and_stale_outputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            p=Path(d);plan=create_batch(p/'data',pilot=True);row=plan[0];folder=p/'data'/row['folder']
            x,_=transmit(row['text'],Config(scheme=row['scheme']))
            write_wav(p/'fixture.wav',np.r_[np.zeros(17000),x*.8])
            import_recording(folder,p/'fixture.wav',dict(distance_m=1,system_volume=50,
                playback_device='test',recording_device='test',environment='synthetic test'))
            status=summarize(p/'data',p/'results');self.assertEqual(status['completed_rounds'],1)
            self.assertTrue((p/'results/quiet_curves.png').exists())
            (folder/'rec.txt').unlink()
            status=summarize(p/'data',p/'results');self.assertEqual(status['completed_rounds'],0)
            self.assertIn('rec.txt',status['invalid_rounds'][0]['reason'])
            self.assertFalse((p/'results/quiet_curves.png').exists())
            self.assertFalse((p/'results/per_round.csv').exists())

    def test_protocol_and_duration_provenance(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            p=Path(d);folder=p/'trial';prepare(folder,TEXTS[0],Config())
            x,_=transmit(TEXTS[0],Config());write_wav(p/'test.wav',np.r_[np.zeros(7313),x*.8])
            import_recording(folder,p/'test.wav',dict(distance_m=1,system_volume=50))
            tx=load_json(folder/'transmission.json');tx['duration_s']=1;save_json(folder/'transmission.json',tx)
            with self.assertRaisesRegex(ValueError,'时长'):evaluate(folder)
            tx['duration_s']=len(read_wav(folder/'tx.wav')[0])/48000;save_json(folder/'transmission.json',tx)
            cfg=load_json(folder/'protocol.json');cfg['symbol_ms']=5;save_json(folder/'protocol.json',cfg)
            with self.assertRaisesRegex(ValueError,'协议'):evaluate(folder)


if __name__=='__main__':unittest.main(verbosity=2)

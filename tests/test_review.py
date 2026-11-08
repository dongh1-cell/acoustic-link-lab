"""Regression checks for findings from the assignment compliance audit."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil
import os
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

    def test_compact_plan_and_pair_extension(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d)/'formal';plan=create_batch(root)
            self.assertEqual(len(plan),14)
            self.assertEqual(inspect_plan(plan),[])
            self.assertEqual([r['scheme'] for r in plan[:2]],['BFSK','4FSK'])
            for scheme in ('BFSK','4FSK'):
                baseline=[r for r in plan if r['scheme']==scheme and r['interference']=='quiet' and r['symbol_ms']==10]
                for kind in ('noise','tone'):
                    sweep=baseline+[r for r in plan if r['scheme']==scheme and r['interference']==kind]
                    self.assertEqual(len(sweep),3)
                    self.assertEqual(len({r['text'] for r in sweep}),3)
            plan=create_batch(root,add_point=('noise',.75,10),text_index=1)
            self.assertEqual(len(plan),16);self.assertEqual(inspect_plan(plan),[])
            before=(root/'plan.json').read_bytes()
            with self.assertRaises(ValueError):create_batch(root,add_point=('noise',.75,10))
            self.assertEqual((root/'plan.json').read_bytes(),before)
            with self.assertRaises(ValueError):create_batch(root,add_point=('quiet',1,10))
            self.assertEqual((root/'plan.json').read_bytes(),before)
            self.assertFalse(list(root.glob('.plan_stage_*')))

    def test_shared_baseline_required(self):
        plan=load_json(ROOT/'Data/formal/plan.json')
        wrong=copy.deepcopy(plan)
        for r in wrong:
            if r['interference']=='noise':r['symbol_ms']=8
        self.assertTrue(any('基线' in s for s in inspect_plan(wrong)))

    def test_pair_commit_failure_is_retryable(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);create_batch(root,pilot=True)
            before={name:(root/name).read_bytes() for name in ('plan.json','录音清单.csv')}
            move=shutil.move;replace=os.replace
            for failure in ('move','metadata'):
                count=[0]
                def fail_move(src,dst):
                    count[0]+=1
                    if count[0]==2:raise OSError('injected move failure')
                    return move(src,dst)
                def fail_replace(src,dst):
                    if Path(src).name=='plan.json':raise OSError('injected metadata failure')
                    return replace(src,dst)
                with patch('batch.shutil.move',side_effect=fail_move if failure=='move' else move),patch('batch.os.replace',side_effect=fail_replace if failure=='metadata' else replace):
                    with self.assertRaises(OSError):create_batch(root,add_point=('noise',.5,10),text_index=2)
                for name,content in before.items():self.assertEqual((root/name).read_bytes(),content)
                self.assertFalse(list(root.glob('noise_*')));self.assertFalse(list(root.glob('.plan_stage_*')))
            self.assertEqual(len(create_batch(root,add_point=('noise',.5,10),text_index=2)),4)

    def test_shared_baseline_conditions(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);plan=create_batch(root/'data',pilot=True)
            plan=create_batch(root/'data',add_point=('noise',.5,10),text_index=2)
            for i,row in enumerate(plan):
                folder=root/'data'/row['folder'];x,fs=read_wav(folder/'tx.wav')
                write_wav(root/'fixture.wav',np.r_[np.zeros(7001),x*.7],fs)
                import_recording(folder,root/'fixture.wav',dict(distance_m=.7 if i<2 else 1,
                    system_volume=50,playback_device='test',recording_device='test',environment='synthetic test'))
            result=summarize(root/'data',root/'results')
            self.assertEqual(result['completed_rounds'],4)
            self.assertTrue(result['condition_mismatches'])

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

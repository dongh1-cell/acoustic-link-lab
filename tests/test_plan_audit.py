"""Regression checks for full PPT review and adaptive noise sweeps."""
from pathlib import Path
import csv
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
from audio import load_json,save_json,read_wav,write_wav
from batch import create_batch,TEXTS
from protocol import Config
from workflow import prepare,import_recording
from summary import summarize
from audit import audit


class PlanAuditTests(unittest.TestCase):
    def test_strong_noise_pair_has_common_safe_amplitude(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);create_batch(root,pilot=True)
            plan=create_batch(root,add_point=('noise',12,10),text_index=1)
            amplitudes=[]
            for row in plan[-2:]:
                folder=root/row['folder'];cfg=load_json(folder/'protocol.json');tx=load_json(folder/'transmission.json')
                amplitudes.append(cfg['amplitude'])
                self.assertEqual(tx['signal_amplitude'],cfg['amplitude'])
                self.assertEqual(tx['pair_gain'],cfg['amplitude']/.22)
                self.assertAlmostEqual(tx['interference_rms_ratio'],12)
                self.assertLessEqual(tx['peak'],.950001)
                samples,_=read_wav(folder/'tx.wav');self.assertLess(abs(samples).max(),.951)
            self.assertEqual(amplitudes[0],amplitudes[1]);self.assertLess(amplitudes[0],.22)
            extended=create_batch(root,add_point=('noise',12,10),text_index=2)
            for row in extended[-2:]:self.assertEqual(load_json(root/row['folder']/'protocol.json')['amplitude'],amplitudes[0])
            self.assertEqual(load_json(root/plan[0]['folder']/'protocol.json')['amplitude'],.22)

    def test_recording_checkmarks_survive_added_point(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);create_batch(root,pilot=True);path=root/'录音清单.csv'
            with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            rows[0]['recording_done']='已录 01_BFSK'
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            create_batch(root,add_point=('noise',.5,10),text_index=2)
            with path.open(encoding='utf-8-sig',newline='') as f:updated=list(csv.DictReader(f))
            self.assertEqual(updated[0]['recording_done'],'已录 01_BFSK')
            self.assertEqual(updated[-1]['recording_done'],'')

    def test_missing_source_files_reported_per_round(self):
        for name in ('protocol.json','transmission.json','send.txt'):
            with self.subTest(name=name),tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
                root=Path(d);plan=create_batch(root/'data',pilot=True)
                path=root/'data'/plan[0]['folder']/name;path.rename(path.with_suffix('.bak'))
                result=summarize(root/'data',root/'results')
                self.assertEqual(len(result['invalid_rounds']),1)
                self.assertIn(name,result['invalid_rounds'][0]['reason'])
                self.assertEqual(len(result['pending']),2)

    def test_mixed_amplitudes_excluded_from_aggregate(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);data=root/'data';plan=[]
            conditions=dict(playback_device='test',recording_device='test',distance_m=.7,
                            system_volume=50,environment='synthetic fixture')
            for i,amplitude in [(1,.22),(2,.11)]:
                for scheme in ('BFSK','4FSK'):
                    name=f'quiet_0_T10_R{i}_{scheme}';folder=data/name
                    row=dict(id=name,folder=name,scheme=scheme,symbol_ms=10.,interference='quiet',level=0.,round=i,text=TEXTS[i-1]);plan.append(row)
                    prepare(folder,row['text'],Config(scheme=scheme,amplitude=amplitude))
                    x,fs=read_wav(folder/'tx.wav');write_wav(root/'fixture.wav',np.r_[np.zeros(7123),x*.7],fs)
                    import_recording(folder,root/'fixture.wav',conditions)
            save_json(data/'plan.json',plan)
            result=summarize(data,root/'results')
            self.assertEqual(result['completed_rounds'],4)
            self.assertEqual(len(result['group_issues']),2)
            self.assertEqual(result['groups'],[])
            self.assertTrue((root/'results/per_round.csv').exists())
            self.assertFalse((root/'results/aggregated.csv').exists())
            self.assertFalse(list((root/'results').glob('*_curves.png')))

    def test_group_exposes_physical_and_signal_settings(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);plan=create_batch(root/'data',pilot=True)
            conditions=dict(playback_device='test',recording_device='test',distance_m=.7,
                            system_volume=50,environment='synthetic fixture')
            folder=root/'data'/plan[0]['folder'];x,fs=read_wav(folder/'tx.wav')
            write_wav(root/'fixture.wav',np.r_[np.zeros(7111),x*.7],fs)
            import_recording(folder,root/'fixture.wav',conditions)
            result=summarize(root/'data',root/'results');group=result['groups'][0]
            self.assertEqual(group['amplitude'],.22)
            for key,value in conditions.items():self.assertEqual(group[key],value)

    def test_mixed_coding_keeps_per_round_and_reports_issue(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            root=Path(d);data=root/'Data/formal';plan=[]
            conditions=dict(playback_device='test',recording_device='test',distance_m=.7,
                            system_volume=50,environment='synthetic fixture')
            for i,coding in [(1,'none'),(2,'hamming15_11')]:
                name=f'quiet_0_T10_R{i}_4FSK';folder=data/name
                row=dict(id=name,folder=name,scheme='4FSK',symbol_ms=10.,interference='quiet',level=0.,round=i,text=TEXTS[i-1]);plan.append(row)
                prepare(folder,row['text'],Config(scheme='4FSK',coding=coding))
                x,fs=read_wav(folder/'tx.wav');write_wav(root/'fixture.wav',np.r_[np.zeros(7131),x*.7],fs)
                import_recording(folder,root/'fixture.wav',conditions)
            save_json(data/'plan.json',plan)
            result=summarize(data,root/'results')
            self.assertEqual(result['completed_rounds'],2)
            self.assertTrue(any('纠错配置' in s for s in result['group_issues']))
            self.assertEqual(result['groups'],[])
            self.assertTrue((root/'results/per_round.csv').exists())
            checked=audit(root)
            self.assertFalse(checked['ready'])
            self.assertTrue(any('纠错配置' in s for s in checked['pending']))
            self.assertTrue(any('视频' in s for s in checked['pending']))

    def test_missing_plan_keeps_auditing_deliverables(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
            result=audit(Path(d))
            self.assertFalse(result['ready'])
            self.assertTrue(any('清单读取失败' in s for s in result['pending']))
            self.assertTrue(any('报告' in s for s in result['pending']))
            self.assertTrue(any('视频' in s for s in result['pending']))


if __name__=='__main__':unittest.main(verbosity=2)

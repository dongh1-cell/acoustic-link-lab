"""Create paired experiments with reproducible interference settings."""
import argparse
import csv
import tempfile
import shutil
import os
from pathlib import Path
from audio import ROOT, save_json, load_json
from protocol import Config, transmit
from workflow import prepare

TEXTS = [
    'DH 2023012159 Hello_IoT_2026! Round A: Sound carries data.',
    'Hello_IoT_2026! DH 2023012159 Round B: Check 42 packets?',
    'Round C: DH 2023012159 Hello_IoT_2026! Test space & symbols.',
]


def create_batch(root, pilot=False, add_point=None, text_index=1):
    root=Path(root)
    # One paired trial at each point. The 10 ms quiet pair is also the
    # zero-interference measurement for both interference sweeps.
    points=[('quiet',0.,10.,1)] if pilot else [
        ('quiet',0.,10.,1), ('quiet',0.,20.,2), ('quiet',0.,5.,3),
        ('noise',.5,10.,2), ('noise',1.,10.,3),
        ('tone',.5,10.,2), ('tone',1.,10.,3),
    ]
    if add_point:
        if text_index not in (1,2,3):raise ValueError('文本编号为1、2或3')
        points=[(*add_point,text_index)]
    plan=load_json(root/'plan.json') if add_point and (root/'plan.json').exists() else []
    pending=[]
    for kind,level,ms,i in points:
        for scheme in ('BFSK','4FSK'):
            name=f'{kind}_{level:g}_T{ms:g}_R{i}_{scheme}'
            if (root/name).exists():
                raise ValueError('已有实验目录，请选择新目录或添加其他测试点：'+name)
            pending.append(dict(id=name,scheme=scheme,interference=kind,level=level,
                             symbol_ms=ms,round=i,text=TEXTS[i-1],folder=name))
    root.mkdir(parents=True,exist_ok=True)
    # A supplemental pair shares one playback amplitude. Keep the selected
    # signal/interference RMS ratio while reserving headroom for strong noise.
    amplitudes={}
    for kind,level,ms,i in points:
        point=(kind,level,ms)
        existing=[r for r in plan if (r['interference'],r['level'],r['symbol_ms'])==point]
        if existing:
            values={Config(**load_json(root/r['folder']/'protocol.json')).amplitude for r in existing}
            if len(values)!=1:raise ValueError('该测试点已有不同信号幅度，请先核对配置')
            amplitudes[point]=values.pop()
        elif add_point:
            peaks=[]
            for scheme in ('BFSK','4FSK'):
                cfg=Config(scheme=scheme,symbol_ms=ms,amplitude=.005,
                           coding='hamming15_11' if scheme=='4FSK' else 'none')
                _,metadata=transmit(TEXTS[i-1],cfg,kind,level,2026+i)
                peaks.append(metadata['peak'])
            amplitudes[point]=min(.22,.95*.005/max(peaks))
        else:amplitudes[point]=.22
    with tempfile.TemporaryDirectory(prefix='.plan_stage_',dir=root) as temporary:
        stage=Path(temporary)
        for row in pending:
            amplitude=amplitudes[(row['interference'],row['level'],row['symbol_ms'])]
            try:
                prepare(stage/row['folder'],row['text'],Config(scheme=row['scheme'],symbol_ms=row['symbol_ms'],amplitude=amplitude,coding='hamming15_11' if row['scheme']=='4FSK' else 'none'),
                    row['interference'],row['level'],2026+row['round'])
            except ValueError as exc:
                if '峰值' in str(exc):raise ValueError('该点沿用已有信号幅度时峰值超限，请另设测试配置并重新采集对应对照') from exc
                raise
            txfile=stage/row['folder']/'transmission.json'
            metadata=load_json(txfile)
            metadata.update(signal_amplitude=amplitude,nominal_amplitude=.22,pair_gain=amplitude/.22)
            save_json(txfile,metadata)
        plan.extend(pending)
        save_json(stage/'plan.json',plan)
        marks={}
        if (root/'录音清单.csv').is_file():
            with (root/'录音清单.csv').open(encoding='utf-8-sig',newline='') as f:
                marks={r['id']:r.get('recording_done','') for r in csv.DictReader(f)}
        with (stage/'录音清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(plan[0])+['recording_done'])
            w.writeheader();w.writerows(dict(p,recording_done=marks.get(p['id'],'')) for p in plan)
        metadata=('录音清单.csv','plan.json');moved=[];replaced=[]
        for name in metadata:
            if (root/name).exists():shutil.copy2(root/name,stage/(name+'.previous'))
        try:
            for row in pending:
                source=(stage/row['folder']).resolve();target=(root/row['folder']).resolve()
                if not source.is_relative_to(stage.resolve()) or not target.is_relative_to(root.resolve()):
                    raise ValueError('实验目录路径无效')
                shutil.move(str(source),str(target));moved.append((source,target))
            for name in metadata:
                os.replace(stage/name,root/name);replaced.append(name)
        except Exception:
            for name in reversed(replaced):
                previous=stage/(name+'.previous')
                if previous.exists():os.replace(previous,root/name)
                else:(root/name).unlink()
            for source,target in reversed(moved):shutil.move(str(target),str(source))
            raise
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Data/formal')
    p.add_argument('--pilot',action='store_true')
    p.add_argument('--add-point',nargs=3,metavar=('KIND','LEVEL','MS'),help='增加一个配对测试点，共2段录音')
    p.add_argument('--text-index',type=int,choices=(1,2,3),default=1,help='补测使用的文本，1/2/3对应A/B/C')
    a=p.parse_args()
    point=(a.add_point[0],float(a.add_point[1]),float(a.add_point[2])) if a.add_point else None
    print(f'清单共 {len(create_batch(a.output,a.pilot,point,a.text_index))} 轮实验')

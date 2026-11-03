"""Create paired experiments with reproducible interference settings."""
import argparse
import csv
from pathlib import Path
from audio import ROOT, save_json, load_json
from protocol import Config
from workflow import prepare

TEXTS = [
    'DH 2023012159 Hello_IoT_2026! Round A: Sound carries data.',
    'Hello_IoT_2026! DH 2023012159 Round B: Check 42 packets?',
    'Round C: DH 2023012159 Hello_IoT_2026! Test space & symbols.',
]


def create_batch(root, pilot=False, add_point=None):
    root=Path(root)
    points=[('quiet',0.,10.)] if pilot else [('quiet',0.,t) for t in (20.,15.,10.,8.,5.)]
    if not pilot:
        points += [(kind, level, 10.) for kind in ('noise','tone') for level in (.25,.5,1.)]
    if add_point:
        points=[add_point]
    plan=load_json(root/'plan.json') if add_point and (root/'plan.json').exists() else []
    pending=[]
    for kind,level,ms in points:
        for i,text in enumerate(TEXTS[:1] if pilot else TEXTS,1):
            for scheme in ('BFSK','4FSK'):
                name=f'{kind}_{level:g}_T{ms:g}_R{i}_{scheme}'
                if (root/name).exists():
                    raise ValueError('已有实验目录，请选择新目录或添加其他测试点：'+name)
                pending.append(dict(id=name,scheme=scheme,interference=kind,level=level,
                                 symbol_ms=ms,round=i,text=text,folder=name))
    for row in pending:
        prepare(root/row['folder'],row['text'],Config(scheme=row['scheme'],symbol_ms=row['symbol_ms'],coding='hamming15_11' if row['scheme']=='4FSK' else 'none'),
                row['interference'],row['level'],2026+row['round'])
    plan.extend(pending)
    save_json(root/'plan.json',plan)
    with (root/'录音清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(plan[0])+['recording_done'])
        w.writeheader();w.writerows(dict(p,recording_done='') for p in plan)
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Data/formal')
    p.add_argument('--pilot',action='store_true')
    p.add_argument('--add-point',nargs=3,metavar=('KIND','LEVEL','MS'),help='为现有清单增加一组3文本×2方案测试')
    a=p.parse_args()
    point=(a.add_point[0],float(a.add_point[1]),float(a.add_point[2])) if a.add_point else None
    print(f'清单共 {len(create_batch(a.output,a.pilot,point))} 轮实验')

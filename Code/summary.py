"""Aggregate real paired trials with denominators and plot measured curves."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audio import ROOT,load_json,save_json,sha256
from metrics import aggregate
from workflow import evaluate
from coverage import inspect_plan
from protocol import Config


def summarize(data, output):
    data,output=Path(data),Path(output);output.mkdir(parents=True,exist_ok=True)
    plan=load_json(data/'plan.json')
    buckets=defaultdict(list);members=defaultdict(list);completed=[];pending=[];conditions={};configs={};transmissions={};invalid=[]
    for row in plan:
        try:
            folder=(data/row['folder']).resolve()
            if not folder.is_relative_to(data.resolve()):
                raise ValueError('清单中的实验目录超出当前数据目录')
            cfg=load_json(folder/'protocol.json');tx=load_json(folder/'transmission.json')
            Config(**cfg).validate()
            if (cfg['scheme']!=row['scheme'] or cfg['symbol_ms']!=row['symbol_ms'] or
                tx['interference']!=row['interference'] or tx['interference_rms_ratio']!=row['level'] or
                (folder/'send.txt').read_text(encoding='ascii')!=row['text']):
                raise ValueError(f"清单与本轮发送配置不一致：{row['id']}")
            if not (folder/'recording.json').exists():
                pending.append(row['id']);continue
            required=('tx.wav','rx.wav','send.txt','rec.txt','decoded.json','conditions.json')
            missing=[name for name in required if not (folder/name).is_file()]
            if missing:raise ValueError('缺少文件：'+', '.join(missing))
            recording=load_json(folder/'recording.json')
            original=(folder/recording['original_file']).resolve()
            if not original.is_relative_to(folder):raise ValueError('原始录音路径无效')
            if recording['origin']!='physical_recording':raise ValueError('本轮为软件测试数据')
            if recording['rx_sha256']!=sha256(folder/'rx.wav') or recording['original_sha256']!=sha256(original):
                raise ValueError('原始录音校验失败')
            decoded=load_json(folder/'decoded.json')
            expected_rec=decoded['recovered_text'] if decoded['complete'] else decoded['display_text']
            if (folder/'rec.txt').read_text(encoding='utf-8')!=expected_rec:
                raise ValueError('rec.txt 与本轮解码结果不一致')
            metrics=evaluate(folder)
            current_conditions=load_json(folder/'conditions.json')
            if not isinstance(current_conditions,dict):
                raise ValueError('conditions.json 应为采集条件对象')
            completed_row=dict(row,**current_conditions,sample_rate=cfg['sample_rate'],
                               coding=cfg.get('coding','none'),
                               amplitude=cfg['amplitude'],gap_s=cfg['gap_s'],padding_s=cfg['padding_s'],
                               nominal_amplitude=tx.get('nominal_amplitude',cfg['amplitude']),
                               pair_gain=tx.get('pair_gain',1.0),
                               **{k:v for k,v in metrics.items() if k!='packets'})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            invalid.append(dict(id=row['id'],reason=str(exc)));pending.append(row['id']);continue
        key=(row['scheme'],row['interference'],row['level'],row['symbol_ms'])
        buckets[key].append(metrics);members[key].append(row['id'])
        conditions[row['id']]=current_conditions
        configs[row['id']]=cfg;transmissions[row['id']]=tx
        completed.append(completed_row)
    mismatches=[]
    pairing=defaultdict(dict)
    for row in plan:
        pairing[(row['interference'],row['level'],row['symbol_ms'],row['round'])][row['scheme']]=row
    for pair in pairing.values():
        if set(pair)!= {'BFSK','4FSK'}: continue
        a,b=pair['BFSK'],pair['4FSK']
        if a['id'] in conditions and b['id'] in conditions:
            ca,cb=conditions[a['id']],conditions[b['id']]
            keys=['playback_device','recording_device','distance_m','system_volume','environment']
            protocol_keys=['sample_rate']
            tx_keys=['interference','interference_rms_ratio','interference_frequency_hz','seed']
            if (any(not str(ca.get(k,'')).strip() or not str(cb.get(k,'')).strip() or ca[k]!=cb[k] for k in keys)
                or any(configs[a['id']][k]!=configs[b['id']][k] for k in protocol_keys)
                or any(transmissions[a['id']].get(k)!=transmissions[b['id']].get(k) for k in tx_keys)
                or configs[a['id']]['amplitude']!=configs[b['id']]['amplitude']
                or a['text']!=b['text']):mismatches.append([a['id'],b['id']])
    # Shared baselines and the sweep points use the same physical setup.
    if completed:
        reference=completed[0]['id']
        keys=('playback_device','recording_device','distance_m','system_volume','environment')
        for row in completed[1:]:
            identifier=row['id']
            if any(conditions[reference].get(k)!=conditions[identifier].get(k) for k in keys):
                pair=[reference,identifier]
                if pair not in mismatches:mismatches.append(pair)
    groups=[];group_issues=[]
    condition_keys=('playback_device','recording_device','distance_m','system_volume','environment')
    for key,metrics_rows in buckets.items():
        identifiers=members[key]
        amplitudes={configs[i]['amplitude'] for i in identifiers}
        setups={json.dumps({k:conditions[i].get(k) for k in condition_keys},sort_keys=True,ensure_ascii=False) for i in identifiers}
        if len(amplitudes)>1 or len(setups)>1:
            group_issues.append(f'{key} 的信号幅度或采集条件不同，请分别整理同条件结果；本组保留逐轮记录，等待核对后汇总')
            continue
        groups.append(dict(scheme=key[0],interference=key[1],level=key[2],symbol_ms=key[3],
                           amplitude=amplitudes.pop(),**json.loads(setups.pop()),**aggregate(metrics_rows)))
    for scheme in ('BFSK','4FSK'):
        codes={c.get('coding','none') for c in configs.values() if c['scheme']==scheme}
        if len(codes)>1:
            group_issues.append(scheme+' 的纠错配置不同，请分别整理各版本结果；本方案保留逐轮记录，等待核对后汇总')
            groups=[group for group in groups if group['scheme']!=scheme]
    status=dict(planned_rounds=len(plan),completed_rounds=len(completed),pending=pending,
                condition_mismatches=mismatches,invalid_rounds=invalid,group_issues=group_issues,plan_issues=inspect_plan(plan),groups=groups,
                note='首轮每点每方案1次录音；10 ms安静点共用于两条干扰曲线。每条曲线含3段不同文本，样本量按实际录音计。根据实测在转折处补点。')
    save_json(output/'summary.json',status)
    if completed:
        with (output/'per_round.csv').open('w',encoding='utf-8-sig',newline='') as f:
            fields=list(dict.fromkeys(k for row in completed for k in row))
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(completed)
        if groups:
            with (output/'aggregated.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(groups[0]));w.writeheader();w.writerows(groups)
        else:(output/'aggregated.csv').unlink(missing_ok=True)
    else:
        # These are derived files owned by this writer; keep the visible results current.
        for name in ('per_round.csv','aggregated.csv','quiet_curves.png','noise_curves.png','tone_curves.png'):
            (output/name).unlink(missing_ok=True)
    for kind in ('quiet','noise','tone'):
        if not any(r['interference']==kind for r in groups):
            (output/f'{kind}_curves.png').unlink(missing_ok=True)
            continue
        fig,axes=plt.subplots(2,2,figsize=(10,7))
        rates=[None] if kind=='quiet' else sorted({r['symbol_ms'] for r in groups if r['interference']==kind}) or [10]
        for scheme in ('BFSK','4FSK'):
            for rate in rates:
                rows=[r for r in groups if r['scheme']==scheme and
                      (r['interference']=='quiet' if kind=='quiet' else
                       r['symbol_ms']==rate and r['interference'] in (kind,'quiet'))]
                rows.sort(key=lambda r:1000/r['symbol_ms'] if kind=='quiet' else r['level'])
                xx=[1000/r['symbol_ms'] if kind=='quiet' else r['level'] for r in rows]
                label=scheme if rate is None else f'{scheme} T={rate:g}ms'
                for ax,key in zip(axes.ravel(),['loss_rate','ber','throughput_bps','text_recovery_rate']):
                    ax.plot(xx,[r[key] if r[key] is not None else float('nan') for r in rows],'o-',label=label)
                    ax.set_ylabel(key);ax.set_xlabel('symbols/s' if kind=='quiet' else 'interference / active-signal RMS')
                    ax.grid(alpha=.3)
        for ax in axes.ravel(): ax.legend()
        fig.suptitle(f'{kind}: physical recordings ({len(completed)}/{len(plan)} rounds available)')
        fig.tight_layout();fig.savefig(output/f'{kind}_curves.png',dpi=160);plt.close(fig)
    return status


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=ROOT/'Data/formal')
    p.add_argument('--output',type=Path,default=ROOT/'Results/formal');a=p.parse_args()
    print(summarize(a.data,a.output))

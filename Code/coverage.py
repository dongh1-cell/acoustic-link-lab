"""Check the planned comparison matrix independently of recorded performance."""
from collections import defaultdict


def inspect_plan(plan):
    issues=[]
    points=defaultdict(list);pairs=defaultdict(dict);seen=set()
    for row in plan:
        if row['id'] in seen:issues.append('重复实验编号：'+row['id'])
        seen.add(row['id'])
        key=(row['interference'],row['level'],row['symbol_ms'])
        points[(row['scheme'],*key)].append(row)
        pair=pairs[(*key,row['round'])]
        if row['scheme'] in pair:issues.append('同一配对位置重复方案：'+row['id'])
        pair[row['scheme']]=row
        if row['scheme'] not in ('BFSK','4FSK'):issues.append('方案名称无效：'+row['id'])
        if not all(token in row['text'] for token in ('DH','2023012159','Hello_IoT_2026!')):
            issues.append('实验文本缺少指定内容：'+row['id'])
    for key,pair in pairs.items():
        if set(pair)!= {'BFSK','4FSK'}:issues.append(f'{key} 缺少配对方案')
        elif pair['BFSK']['text']!=pair['4FSK']['text']:issues.append(f'{key} 配对发送文本不同')
    for scheme in ('BFSK','4FSK'):
        quiet_rows=[r for r in plan if r['scheme']==scheme and r['interference']=='quiet']
        quiet={r['symbol_ms'] for r in quiet_rows}
        if len(quiet)<3:issues.append(f'{scheme} 安静速率曲线少于3个测试点')
        if len({r['text'] for r in quiet_rows})<3:issues.append(f'{scheme} 速率测试少于3段不同文本')
        for kind in ('noise','tone'):
            rows=[r for r in plan if r['scheme']==scheme and r['interference']==kind]
            if not rows:issues.append(f'{scheme} {kind} 干扰扫描尚缺多个非零强度点')
            for ms in {r['symbol_ms'] for r in rows}:
                sweep=[r for r in rows if r['symbol_ms']==ms]
                baseline=[r for r in quiet_rows if r['symbol_ms']==ms]
                if not baseline:issues.append(f'{scheme} {kind} T={ms:g} 缺少同速率安静基线')
                if len({r['level'] for r in sweep if r['level']>0})<2:
                    issues.append(f'{scheme} {kind} T={ms:g} 干扰扫描尚缺多个非零强度点')
                if len({r['text'] for r in sweep+baseline})<3:
                    issues.append(f'{scheme} {kind} T={ms:g} 测试少于3段不同文本（含安静基线）')
    return list(dict.fromkeys(issues))

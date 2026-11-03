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
    for key,rows in points.items():
        if len({r['text'] for r in rows})<3:issues.append(f'{key} 少于3段不同文本')
    for key,pair in pairs.items():
        if set(pair)!= {'BFSK','4FSK'}:issues.append(f'{key} 缺少配对方案')
        elif pair['BFSK']['text']!=pair['4FSK']['text']:issues.append(f'{key} 配对发送文本不同')
    for scheme in ('BFSK','4FSK'):
        quiet={r['symbol_ms'] for r in plan if r['scheme']==scheme and r['interference']=='quiet'}
        if len(quiet)<3:issues.append(f'{scheme} 安静速率曲线少于3个测试点')
        for kind in ('noise','tone'):
            levels={r['level'] for r in plan if r['scheme']==scheme and r['interference']==kind and r['level']>0}
            if len(levels)<2:issues.append(f'{scheme} {kind} 干扰扫描尚缺多个非零强度点')
    return list(dict.fromkeys(issues))

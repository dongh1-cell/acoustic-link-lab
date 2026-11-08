"""Submission readiness audit; genuine missing evidence stays explicit."""
import argparse
import re
import subprocess
from pathlib import Path
from audio import ROOT,load_json,save_json
from summary import summarize


def audit(root=ROOT):
    pending=[]
    status=summarize(root/'Data/formal',root/'Results/formal')
    if status['pending']:pending.append(f"正式录音尚缺{len(status['pending'])}轮")
    if status['condition_mismatches']:pending.append('部分配对实验的实际采集条件不同')
    pending.extend('测试覆盖：'+message for message in status['plan_issues'])
    pending.extend('数据检查：'+row['id']+' '+row['reason'] for row in status['invalid_rounds'])
    required=['README.md','requirements.txt','启动界面.cmd','Code/protocol.py','Code/receiver.py',
              'Code/workflow.py','Code/metrics.py','Code/web_app.py','Code/summary.py','Code/coverage.py',
              'Code/audio.py','Code/fec.py','Code/batch.py','Code/audit.py','Code/frontend/package.json','Code/frontend/package-lock.json',
              'Code/frontend/index.html','Code/frontend/vite.config.js','Code/frontend/src/comparison.js',
              'Code/frontend/src/main.jsx','Code/frontend/src/style.css','Code/frontend/dist/index.html']
    required.extend(['Code/initialize.py','Code/frontend/src/charts.jsx'])
    pending.extend('缺少复现文件：'+name for name in required if not (root/name).is_file())
    index=root/'Code/frontend/dist/index.html'
    if index.is_file():
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"',index.read_text(encoding='utf-8')):
            if not (root/'Code/frontend/dist'/asset.lstrip('/')).is_file():pending.append('缺少网页构建资源：'+asset)
    if not (root/'report/main.pdf').is_file():pending.append('待完成正式实验报告PDF')
    elif (root/'report/main.tex').is_file() and '软件实现阶段稿' in (root/'report/main.tex').read_text(encoding='utf-8'):
        pending.append('报告当前为软件实现阶段稿，待补充真实实验结果与结论')
    elif (root/'report/main.tex').is_file() and (root/'report/main.tex').stat().st_mtime>(root/'report/main.pdf').stat().st_mtime:
        pending.append('报告源码已更新，PDF需重新编译')
    review=root/'report/review.json'
    if not review.exists():
        pending.append('待结合实测审核性能改善、极限曲线和组内分工')
    else:
        info=load_json(review)
        for field in ['measured_improvement','limit_curves_reviewed','two_members_and_roles','report_final']:
            if info.get(field) is not True:pending.append('报告检查未完成：'+field)
    video=root/'Demo/demo.mp4'
    duration=None
    if not video.is_file():pending.append('待录制两方案真实运行演示视频')
    else:
        import imageio_ffmpeg
        result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(video)],capture_output=True)
        match=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',result.stderr.decode(errors='replace'))
        if match:
            h,m,s=map(float,match.groups());duration=h*3600+m*60+s
            if duration>300:pending.append('演示视频超过300秒')
        else:pending.append('演示视频时长读取失败')
    report=dict(ready=not pending,completed_physical_rounds=status['completed_rounds'],
                planned_physical_rounds=status['planned_rounds'],video_duration_s=duration,pending=pending)
    save_json(root/'Results/readiness.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.parse_args()
    result=audit()
    print('正式提交已就绪' if result['ready'] else '当前待完成：\n'+'\n'.join(result['pending']))

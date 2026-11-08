"""Create reproducible playback files on first use, preserving existing trials."""
from audio import ROOT
from batch import create_batch
import argparse
from datetime import datetime
import shutil


def initialize(compact=False):
    (ROOT/'work').mkdir(exist_ok=True)
    if compact:
        data=(ROOT/'Data').resolve()
        folders=[data/name for name in ('pilot','formal') if (data/name).exists()]
        # Migration applies to unrecorded plans; recorded plans remain intact.
        for folder in folders:
            if not folder.resolve().is_relative_to(data):raise ValueError('实验目录路径无效')
            if any(folder.rglob('rx.wav')) or any(folder.rglob('recording.json')):
                raise ValueError('已有实际录音，请先保留原清单并单独规划迁移：'+str(folder))
        archive=(ROOT/'work'/('plan_archive_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
        if not archive.is_relative_to(ROOT.resolve()):raise ValueError('备份目录路径无效')
        if folders:
            archive.mkdir(parents=True)
            for folder in folders:shutil.move(str(folder),str(archive/folder.name))
            print('原发送文件已保存：'+str(archive))
    for name,pilot in [('formal',False)]:
        folder=ROOT/'Data'/name
        if (folder/'plan.json').is_file():
            print(f'{name}: 已有实验清单，继续使用现有文件')
        else:
            rows=create_batch(folder,pilot=pilot)
            print(f'{name}: 已生成 {len(rows)} 轮发送文件')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--compact',action='store_true',help='将尚未录音的旧计划备份到work，生成14轮精简计划')
    initialize(parser.parse_args().compact)

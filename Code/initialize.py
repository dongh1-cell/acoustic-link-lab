"""Create reproducible playback files on first use, preserving existing trials."""
from audio import ROOT
from batch import create_batch


def initialize():
    (ROOT/'work').mkdir(exist_ok=True)
    for name,pilot in [('pilot',True),('formal',False)]:
        folder=ROOT/'Data'/name
        if (folder/'plan.json').is_file():
            print(f'{name}: 已有实验清单，继续使用现有文件')
        else:
            rows=create_batch(folder,pilot=pilot)
            print(f'{name}: 已生成 {len(rows)} 轮发送文件')


if __name__=='__main__':initialize()

"""Desktop UI for both protocols, capture records and per-packet inspection."""
import os
from pathlib import Path
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from audio import ROOT,load_json,read_wav
from protocol import Config
from workflow import prepare,import_recording,receive,evaluate
from batch import TEXTS


class App:
    def __init__(self, root):
        self.root=root;self.folder=None;self.jobs=queue.Queue();self.busy=False
        root.title('作业4 · 声波通信与协议设计');root.geometry('1180x850');root.minsize(1000,760)
        self.scheme=tk.StringVar(value='BFSK');self.ms=tk.StringVar(value='10')
        self.kind=tk.StringVar(value='quiet');self.level=tk.StringVar(value='0')
        self.distance=tk.StringVar();self.volume=tk.StringVar();self.environment=tk.StringVar(value='安静宿舍')
        self.status=tk.StringVar(value='先打开预实验目录，或输入40～80个ASCII字符生成新实验。')
        self.location=tk.StringVar(value='尚未选择实验目录')
        self.stats=tk.StringVar(value='统计将在导入真实录音并解码后显示。')
        outer=ttk.Frame(root,padding=12);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='声波通信实验',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
        ttk.Label(outer,text='生成发送音频 → 手机连续录音 → 导入完整录音 → 自动同步与重组').pack(anchor='w',pady=(2,8))
        self.text=tk.Text(outer,height=3,font=('Consolas',11),wrap='word');self.text.pack(fill='x');self.text.insert('1.0',TEXTS[0])
        config=ttk.Frame(outer);config.pack(fill='x',pady=6)
        for label,var,values,width in [('方案',self.scheme,['BFSK','4FSK'],8),('符号时长/ms',self.ms,['5','8','10','15','20'],7),
                                       ('干扰',self.kind,['quiet','noise','tone'],8),('干扰RMS比例',self.level,['0','0.25','0.5','1','1.5','2'],7)]:
            ttk.Label(config,text=label).pack(side='left',padx=(0,5))
            ttk.Combobox(config,textvariable=var,values=values,state='readonly',width=width).pack(side='left',padx=(0,15))
        ttk.Label(config,text='48 kHz · 间隔0.2 s · 新4FSK启用Hamming纠错与交织').pack(side='left')
        controls=ttk.Frame(outer);controls.pack(fill='x',pady=4)
        for title,command in [('生成新实验',self.generate),('打开已有实验',self.open_folder),('播放 tx.wav',self.play),
                              ('停止播放',self.stop),('导入手机录音并解码',self.import_audio),('重新解码',self.redo),('打开结果目录',self.open_results)]:
            ttk.Button(controls,text=title,command=command).pack(side='left',padx=(0,6))
        ttk.Label(outer,textvariable=self.location,wraplength=1100).pack(anchor='w',pady=3)
        capture=ttk.Frame(outer);capture.pack(fill='x',pady=4)
        ttk.Label(capture,text='魔霸新锐2023 → vivo X200s   实际距离/m').pack(side='left')
        ttk.Entry(capture,textvariable=self.distance,width=6).pack(side='left',padx=5)
        ttk.Label(capture,text='系统音量/%').pack(side='left');ttk.Entry(capture,textvariable=self.volume,width=6).pack(side='left',padx=5)
        ttk.Label(capture,text='环境').pack(side='left');ttk.Entry(capture,textvariable=self.environment,width=20).pack(side='left',padx=5)
        self.fig=Figure(figsize=(10,2.2),dpi=100)
        self.wave=self.fig.add_subplot(121);self.spectrum=self.fig.add_subplot(122)
        self.fig.tight_layout();self.canvas=FigureCanvasTkAgg(self.fig,master=outer)
        self.canvas.get_tk_widget().pack(fill='both',expand=True,pady=4)
        table=ttk.Frame(outer);table.pack(fill='x')
        columns=('seq','length','sync','check','start','text')
        self.tree=ttk.Treeview(table,columns=columns,show='headings',height=6)
        for name,title,width in zip(columns,['包序号','长度','同步状态','校验','起点/s','解码文本'],[70,60,120,80,90,470]):
            self.tree.heading(name,text=title);self.tree.column(name,width=width,stretch=name=='text')
        self.tree.pack(side='left',fill='x',expand=True)
        scroll=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        ttk.Label(outer,text='恢复文本').pack(anchor='w',pady=(5,0))
        self.recovered=tk.Text(outer,height=2,font=('Consolas',11),wrap='word');self.recovered.pack(fill='x')
        ttk.Label(outer,textvariable=self.stats,wraplength=1100).pack(anchor='w',pady=6)
        ttk.Label(outer,textvariable=self.status,wraplength=1100,foreground='#225588').pack(anchor='w')
        root.after(100,self.poll)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):
        self.stop();self.root.destroy()

    def available(self):
        if self.busy:
            messagebox.showinfo('正在处理','请等待当前解码完成。');return False
        return True

    def run_job(self, job, done):
        if not self.available():return
        self.busy=True;self.status.set('正在处理完整录音……')
        def work():
            try:self.jobs.put((done,job(),None))
            except Exception as exc:self.jobs.put((done,None,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            done,result,error=self.jobs.get_nowait();self.busy=False
            if error:self.status.set(error);messagebox.showerror('处理提示',error)
            else:done(result)
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def load_folder(self,folder):
        folder=Path(folder);cfg=Config(**load_json(folder/'protocol.json'))
        tx=load_json(folder/'transmission.json');self.folder=folder
        self.scheme.set(cfg.scheme);self.ms.set(f'{cfg.symbol_ms:g}')
        self.kind.set(tx['interference']);self.level.set(f"{tx['interference_rms_ratio']:g}")
        self.text.delete('1.0','end');self.text.insert('1.0',(folder/'send.txt').read_text(encoding='ascii'))
        self.location.set(str(folder));self.tree.delete(*self.tree.get_children())
        self.recovered.delete('1.0','end');self.stats.set('等待本轮真实录音。')
        if (folder/'conditions.json').exists():
            c=load_json(folder/'conditions.json');self.distance.set(str(c['distance_m']));self.volume.set(str(c['system_volume']));self.environment.set(c['environment'])
        self.plot(folder/('rx.wav' if (folder/'rx.wav').exists() else 'tx.wav'))
        if (folder/'decoded.json').exists():self.show_result((load_json(folder/'decoded.json'),evaluate(folder)))
        self.status.set('当前目录的协议已固定；修改参数后请生成新实验。')

    def open_folder(self):
        if not self.available():return
        folder=filedialog.askdirectory(initialdir=ROOT/'Data',title='选择包含 tx.wav 和 protocol.json 的实验目录')
        if folder:
            try:self.load_folder(folder)
            except Exception as exc:messagebox.showerror('打开失败',str(exc))

    def generate(self):
        if not self.available():return
        parent=filedialog.askdirectory(initialdir=ROOT/'Data',title='选择保存位置；程序将创建新的实验子目录')
        if not parent:return
        from datetime import datetime
        folder=Path(parent)/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+self.scheme.get())
        try:
            cfg=Config(scheme=self.scheme.get(),symbol_ms=float(self.ms.get()),coding='hamming15_11' if self.scheme.get()=='4FSK' else 'none')
            prepare(folder,self.text.get('1.0','end-1c'),cfg,self.kind.get(),float(self.level.get()))
            self.load_folder(folder);self.status.set('发送文件已生成。手机开始录音后再点击播放，播放结束后继续录制2秒。')
        except Exception as exc:messagebox.showerror('生成失败',str(exc))

    def play(self):
        if self.folder:
            import winsound
            winsound.PlaySound(str(self.folder/'tx.wav'),winsound.SND_FILENAME|winsound.SND_ASYNC)
            self.status.set('正在播放；请保持设备位置和音量，播放结束后继续录制2秒。')

    def stop(self):
        if os.name=='nt':
            import winsound
            winsound.PlaySound(None,0)

    def import_audio(self):
        if not self.available():return
        if not self.folder:messagebox.showinfo('选择实验','请先打开或生成实验。');return
        source=filedialog.askopenfilename(title='选择手机采集的完整录音',filetypes=[('音频','*.wav *.m4a *.mp4a *.mp3 *.aac *.mp4'),('全部文件','*.*')])
        if not source:return
        try:
            distance=float(self.distance.get());volume=float(self.volume.get())
            if not 0<volume<=100:raise ValueError('系统音量应为1～100')
        except ValueError as exc:messagebox.showerror('采集条件','请填写正数距离和1～100的系统音量。');return
        conditions=dict(playback_device='魔霸新锐2023电脑扬声器',recording_device='vivo X200s',
                        distance_m=distance,system_volume=volume,environment=self.environment.get())
        folder=self.folder
        self.run_job(lambda:import_recording(folder,source,conditions),self.show_result)

    def redo(self):
        if self.folder and self.available():
            folder=self.folder
            self.run_job(lambda:(receive(folder),evaluate(folder)),self.show_result)

    def show_result(self,pair):
        result,metrics=pair;self.tree.delete(*self.tree.get_children())
        for p in result['packets']:
            self.tree.insert('','end',values=(p['seq'],p['length'],'已同步', '通过' if p['checksum_ok'] else '失败',f"{p['start_s']:.3f}",p['text']))
        for p in result['rejected_candidates']:
            self.tree.insert('','end',values=('—','—','候选定位','包头异常',f"{p['start_s']:.3f}",'待有效字段'))
        self.recovered.delete('1.0','end');self.recovered.insert('1.0',result['display_text'])
        m=metrics;ber=f"{m['error_bits']}/{m['compared_bits']} = {m['ber']:.2%}" if m['ber'] is not None else '0个可比较位'
        self.stats.set(f"丢包率 {m['lost_packets']}/{m['expected_packets']} = {m['loss_rate']:.1%}    BER {ber}\n"
                       f"有效吞吐 {m['delivered_bits']} bit / {m['duration_s']:.3f} s = {m['throughput_bps']:.2f} bit/s    完整文本恢复 {m['complete_rounds']}/1 轮")
        self.plot(self.folder/'rx.wav');self.status.set('解码和统计已保存。批量曲线按同条件的多轮结果汇总。')

    def plot(self,path):
        x,fs=read_wav(path);step=max(1,len(x)//6000);self.wave.clear();self.spectrum.clear()
        self.wave.plot(np.arange(0,len(x),step)/fs,x[::step],lw=.5);self.wave.set(xlabel='Time / s',ylabel='Amplitude',title=path.name)
        from scipy.signal import welch
        f,p=welch(x,fs,nperseg=min(4096,len(x)))
        self.spectrum.plot(f,10*np.log10(p+1e-16),lw=.8);self.spectrum.set(xlim=(0,5000),xlabel='Frequency / Hz',ylabel='PSD / dB',title='Spectrum')
        self.fig.tight_layout();self.canvas.draw_idle()

    def open_results(self):
        if self.folder:os.startfile(self.folder)


def main():
    root=tk.Tk();app=App(root)
    import sys
    if len(sys.argv)>1:app.load_folder(Path(sys.argv[1]))
    root.mainloop()


if __name__=='__main__':main()

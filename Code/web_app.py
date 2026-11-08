"""Local-only HTTP adapter for the existing experiment workflow and React UI."""
import argparse
import base64
import json
import math
import mimetypes
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import threading
from urllib.parse import urlparse, parse_qs
import webbrowser
import numpy as np
from scipy.signal import welch
from audio import ROOT, load_json, read_wav
from protocol import Config
from workflow import prepare, import_recording, receive, evaluate
from summary import summarize
from batch import create_batch

DATA = ROOT/'Data'
DIST = ROOT/'Code/frontend/dist'
RESULTS = ROOT/'Results'
LOCK = threading.Lock()
MAX_BODY = 100*1024*1024


def experiment(identifier):
    if not identifier or '\\' in identifier:
        raise ValueError('请选择实验')
    folder = (DATA/identifier).resolve()
    if not folder.is_relative_to(DATA.resolve()) or not (folder/'protocol.json').is_file():
        raise ValueError('实验目录不存在')
    return folder


def inventory():
    def read_record(path):
        try:return load_json(path)
        except (OSError,ValueError) as exc:raise ValueError(path.name+'：'+str(exc)) from exc
    plan=load_json(DATA/'formal/plan.json') if (DATA/'formal/plan.json').is_file() else []
    planned={'formal/'+r['folder']:(i+1,r) for i,r in enumerate(plan)}
    identifiers=set(planned)
    for config_file in DATA.rglob('protocol.json'):
        relative=config_file.parent.relative_to(DATA)
        if not any(part.startswith('.') for part in relative.parts):identifiers.add(relative.as_posix())
    rows=[]
    for identifier in identifiers:
        number,entry=planned.get(identifier,(None,{}))
        folder=DATA/identifier
        row=dict(id=identifier,name=folder.name,number=number,group=Path(identifier).parts[0],
                 scheme=entry.get('scheme','未知方案'),symbol_ms=entry.get('symbol_ms'),
                 interference=entry.get('interference','quiet'),level=entry.get('level',0),
                 duration_s=None,recorded=False,decoded=False,complete=False)
        try:
            if not folder.resolve().is_relative_to(DATA.resolve()):raise ValueError('实验路径超出数据目录')
            for name in ('protocol.json','transmission.json','send.txt','tx.wav'):
                if not (folder/name).is_file():raise ValueError('缺少文件：'+name)
            cfg=read_record(folder/'protocol.json');Config(**cfg).validate()
            tx=read_record(folder/'transmission.json')
            duration=float(tx['duration_s']);level=float(tx['interference_rms_ratio'])
            if not math.isfinite(duration) or duration<=0:
                raise ValueError('transmission.json 中的发送时长无效')
            if tx['interference'] not in ('quiet','noise','tone') or not math.isfinite(level):
                raise ValueError('transmission.json 中的干扰设置无效')
            row.update(scheme=cfg['scheme'],symbol_ms=cfg['symbol_ms'],interference=tx['interference'],
                       level=level,duration_s=duration)
            optional={}
            for name in ('metrics','decoded','conditions','recording'):
                if (folder/(name+'.json')).is_file():
                    value=read_record(folder/(name+'.json'))
                    if not isinstance(value,dict):raise ValueError(name+'.json 格式无效')
                    optional[name]=value
            recorded=(folder/'rx.wav').is_file();decoded='decoded' in optional
            if (recorded or decoded) and 'metrics' not in optional:raise ValueError('缺少文件：metrics.json')
            if decoded and not isinstance(optional['decoded'].get('packets'),list):
                raise ValueError('decoded.json 中的逐包结果无效')
            metrics=optional.get('metrics')
            row.update(recorded=recorded,decoded=decoded,complete=bool(metrics and metrics['complete_rounds']))
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
            row['error']='文件待修复：'+str(exc)
        rows.append(row)
    return sorted(rows,key=lambda r:(0 if r['group']=='formal' else 1,r['number'] or 999,r['id']))


def details(identifier):
    folder = experiment(identifier)
    result = dict(id=identifier, text=(folder/'send.txt').read_text(encoding='ascii'),
                  config=load_json(folder/'protocol.json'), transmission=load_json(folder/'transmission.json'),
                  recorded=(folder/'rx.wav').exists())
    for name in ('conditions','decoded','metrics','recording'):
        result[name] = load_json(folder/(name+'.json')) if (folder/(name+'.json')).exists() else None
    return result


def signal_data(identifier, kind):
    folder = experiment(identifier)
    if kind not in ('tx','rx'):
        raise ValueError('信号类型应为tx或rx')
    path = folder/(kind+'.wav')
    if not path.exists():
        raise ValueError('本轮还没有接收录音')
    x, fs = read_wav(path)
    count = min(1000,len(x))
    edges = np.linspace(0,len(x),count+1,dtype=int)
    wave = [[round((a+b)/2/fs,5),round(float(x[a:b].min()),5),round(float(x[a:b].max()),5)] for a,b in zip(edges[:-1],edges[1:])]
    f,p = welch(x,fs,nperseg=min(4096,len(x)))
    spectrum = [[round(float(a),1),round(float(10*np.log10(b+1e-16)),2)] for a,b in zip(f,p) if a<=5000]
    return dict(kind=kind,duration_s=len(x)/fs,sample_rate=fs,wave=wave,spectrum=spectrum,
                peak=round(float(np.abs(x).max()),4))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def json_response(self, value, status=200):
        raw = json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(raw)

    def trusted_request(self):
        host = urlparse('http://'+self.headers.get('Host','')).hostname
        if host not in ('127.0.0.1','localhost'):
            raise ValueError('请通过本机地址打开实验界面')

    def send_file(self,path,download=False):
        if not path.is_file():
            raise FileNotFoundError('文件尚未生成')
        size=path.stat().st_size;start,end=0,size-1;partial=False
        request_range=self.headers.get('Range','')
        if request_range.startswith('bytes=') and ',' not in request_range:
            a,b=request_range[6:].split('-',1)
            if a:start=int(a);end=min(int(b) if b else end,end)
            elif b:start=max(0,size-int(b))
            if not 0<=start<=end<size:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
            partial=True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-cache')
        if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if download:self.send_header('Content-Disposition',f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start);remaining=end-start+1
            while remaining:
                chunk=f.read(min(remaining,65536))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)

    def do_GET(self):
        try:
            self.trusted_request()
            url=urlparse(self.path);query=parse_qs(url.query)
            arg=lambda k,default='':query.get(k,[default])[0]
            if url.path=='/api/health':return self.json_response(dict(app='acoustic-lab',version=2,project=str(ROOT.resolve())))
            if url.path=='/api/experiments':return self.json_response(inventory())
            if url.path=='/api/experiment':return self.json_response(details(arg('id')))
            if url.path=='/api/signal':return self.json_response(signal_data(arg('id'),arg('kind','tx')))
            if url.path=='/api/summary':
                path=RESULTS/'formal/summary.json'
                plan=load_json(DATA/'formal/plan.json') if (DATA/'formal/plan.json').is_file() else []
                result=load_json(path) if path.exists() else dict(groups=[],completed_rounds=0)
                result['planned_rounds']=len(plan)
                return self.json_response(result)
            if url.path=='/api/file':
                name=arg('name')
                if name not in ('tx.wav','rx.wav','send.txt','rec.txt','protocol.json','metrics.json','decoded.json'):
                    raise ValueError('文件类型无效')
                return self.send_file(experiment(arg('id'))/name,download=arg('download')=='1')
            if url.path.startswith('/api/'):
                return self.json_response(dict(error='接口不存在'),404)
            relative=url.path.lstrip('/') or 'index.html'
            path=(DIST/relative).resolve()
            if not path.is_relative_to(DIST.resolve()):raise ValueError('路径无效')
            if not path.is_file() and '.' not in Path(relative).name:path=DIST/'index.html'
            self.send_file(path)
        except (BrokenPipeError,ConnectionResetError):pass
        except FileNotFoundError as exc:self.json_response(dict(error=str(exc)),404)
        except Exception as exc:self.json_response(dict(error=str(exc)),400)

    def do_POST(self):
        try:
            self.trusted_request()
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).hostname not in ('127.0.0.1','localhost'):
                raise ValueError('请在本机实验界面中操作')
            if self.headers.get('X-Acoustic-Lab')!='1':raise ValueError('请求标识无效')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=MAX_BODY:raise ValueError('请求大小超限，单个录音限制为60MB')
            body=json.loads(self.rfile.read(size))
            if not LOCK.acquire(blocking=False):
                return self.json_response(dict(error='正在处理另一项任务，请稍后重试'),409)
            try:
                route=urlparse(self.path).path
                if route=='/api/create':
                    cfg=Config(scheme=body['scheme'],symbol_ms=float(body['symbol_ms']),coding='hamming15_11' if body['scheme']=='4FSK' else 'none')
                    identifier='custom/'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+cfg.scheme
                    DATA.mkdir(parents=True,exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix='.create_',dir=DATA) as temp:
                        source=Path(temp)/'trial'
                        prepare(source,body['text'],cfg,body['interference'],float(body['level']))
                        target=(DATA/identifier).resolve()
                        if not target.is_relative_to(DATA.resolve()):raise ValueError('实验目录路径无效')
                        target.parent.mkdir(exist_ok=True)
                        source.replace(target)
                    result=details(identifier)
                elif route=='/api/import':
                    folder=experiment(body['id']);conditions=body['conditions']
                    conditions['distance_m']=float(conditions['distance_m']);conditions['system_volume']=float(conditions['system_volume'])
                    if not math.isfinite(conditions['distance_m']) or conditions['distance_m']<=0:
                        raise ValueError('请填写实际距离')
                    if not 0<conditions['system_volume']<=100:raise ValueError('系统音量范围为1～100%')
                    ext=Path(body['filename']).suffix.lower()
                    if ext not in ('.wav','.m4a','.mp4a','.mp3','.aac','.mp4'):raise ValueError('请选择WAV或手机录音文件')
                    raw=base64.b64decode(body['audio'],validate=True)
                    if len(raw)>60*1024*1024:raise ValueError('单个录音限制为60MB')
                    with tempfile.TemporaryDirectory(prefix='acoustic_upload_') as temp:
                        source=Path(temp)/('upload'+ext);source.write_bytes(raw)
                        import_recording(folder,source,conditions)
                    result=details(body['id'])
                elif route=='/api/decode':
                    folder=experiment(body['id']);receive(folder);evaluate(folder);result=details(body['id'])
                elif route=='/api/add-point':
                    before=load_json(DATA/'formal/plan.json')
                    plan=create_batch(DATA/'formal',add_point=(body['interference'],float(body['level']),float(body['symbol_ms'])),text_index=int(body.get('text_index',1)))
                    result=dict(ids=['formal/'+r['folder'] for r in plan[len(before):]],planned_rounds=len(plan))
                elif route=='/api/summarize':result=summarize(DATA/'formal',RESULTS/'formal')
                else:raise ValueError('操作不存在')
            finally:LOCK.release()
            self.json_response(result)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.json_response(dict(error=str(exc)),400)


def main():
    parser=argparse.ArgumentParser(description='声波通信 React 本地工作台')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open',action='store_true');args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}'
    if not (DIST/'index.html').exists():raise SystemExit('请先在 Code/frontend 中运行 npm install 和 npm run build')
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        from urllib.request import urlopen
        try:
            with urlopen(url+'/api/health',timeout=2) as response:existing=json.load(response)
            if existing.get('app')=='acoustic-lab':
                if not existing.get('project') or Path(existing['project']).resolve()!=ROOT.resolve():
                    raise SystemExit('该端口正在运行另一项目或旧版本，请关闭该服务后重启当前项目，或使用 --port 指定其他端口')
                if args.open:webbrowser.open(url)
                print('实验工作台已运行：'+url);return
        except Exception:pass
        raise SystemExit('端口已占用，请使用 --port 指定其他端口')
    print('声波通信实验工作台：'+url,flush=True)
    if args.open:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()

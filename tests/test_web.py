"""Exercise the local HTTP adapter against an isolated synthetic test directory."""
from pathlib import Path
import base64
import json
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
import web_app
from audio import read_wav,write_wav


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='web_test_')
        cls.old_data=web_app.DATA
        web_app.DATA=Path(cls.temp.name)/'Data';web_app.DATA.mkdir()
        cls.server=web_app.ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();web_app.DATA=cls.old_data;cls.temp.cleanup()

    def request(self,path,body=None,token=True,headers=None):
        headers=dict(headers or {})
        if token:headers['X-Acoustic-Lab']='1'
        if body is not None:headers['Content-Type']='application/json'
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=30) as r:return r.status,r.headers,r.read()
        except HTTPError as r:return r.code,r.headers,r.read()

    def create(self):
        code,_,raw=self.request('/api/create',dict(text='DH 2023012159 Hello_IoT_2026! Web interface test.',scheme='4FSK',symbol_ms=10,interference='quiet',level=0))
        self.assertEqual(code,200,raw)
        return json.loads(raw)

    def test_generation_signal_and_range(self):
        r=self.create();identifier=r['id']
        code,_,raw=self.request('/api/signal?id='+identifier+'&kind=tx')
        self.assertEqual(code,200);s=json.loads(raw);self.assertEqual(len(s['wave']),1000);self.assertEqual(s['sample_rate'],48000)
        code,headers,raw=self.request('/api/file?id='+identifier+'&name=tx.wav',headers={'Range':'bytes=0-43'})
        self.assertEqual(code,206);self.assertEqual(len(raw),44);self.assertEqual(raw[:4],b'RIFF');self.assertIn('Content-Range',headers)
        code,_,raw=self.request('/api/experiments');self.assertEqual(code,200);self.assertTrue(json.loads(raw))

    def test_path_and_request_validation(self):
        self.assertEqual(self.request('/api/experiment?id=../../')[0],400)
        self.assertEqual(self.request('/api/create',{},token=False)[0],400)
        self.assertEqual(self.request('/api/create',{},headers={'Origin':'https://example.com'})[0],400)
        self.assertEqual(self.request('/api/health',headers={'Host':'example.com'})[0],400)
        self.assertEqual(self.request('/api/create',dict(text='short',scheme='BFSK',symbol_ms=10,interference='quiet',level=0))[0],400)
        self.assertEqual(self.request('/api/file?id=../&name=main.tex')[0],400)

    def test_full_upload_decode_and_preservation(self):
        r=self.create();folder=web_app.experiment(r['id'])
        conditions=dict(distance_m=.7,system_volume=50,environment='synthetic HTTP test',playback_device='test',recording_device='test')
        data=dict(id=r['id'],filename='recording.wav',conditions=conditions,audio=base64.b64encode((folder/'tx.wav').read_bytes()).decode())
        self.assertEqual(self.request('/api/import',data)[0],400)
        x,fs=read_wav(folder/'tx.wav');target=Path(self.temp.name)/'synthetic.wav'
        write_wav(target,np.r_[np.zeros(7381),x*.7,np.zeros(5301)],fs)
        data['audio']=base64.b64encode(target.read_bytes()).decode()
        code,_,raw=self.request('/api/import',data)
        self.assertEqual(code,200,raw);result=json.loads(raw)
        self.assertEqual(result['decoded']['recovered_text'],r['text']);self.assertEqual(result['metrics']['complete_rounds'],1)
        self.assertEqual((folder/'original.wav').read_bytes(),target.read_bytes())
        self.assertEqual(self.request('/api/import',data)[0],400)
        code,_,raw=self.request('/api/decode',dict(id=r['id']));self.assertEqual(code,200,raw)
        self.assertEqual(self.request('/api/file?id='+r['id']+'&name=rec.txt')[2].decode(),r['text'])


if __name__=='__main__':unittest.main(verbosity=2)

"""Regression checks for server identity and partially generated experiments."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Code'))
import web_app
from batch import create_batch


class WebAuditTests(unittest.TestCase):
    def test_inventory_keeps_plan_slots_when_trial_files_are_damaged(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='inventory_audit_') as temp,patch.object(web_app,'DATA',Path(temp)/'Data'):
            plan=create_batch(web_app.DATA/'formal')
            first=web_app.DATA/'formal'/plan[0]['folder'];second=web_app.DATA/'formal'/plan[1]['folder']
            third=web_app.DATA/'formal'/plan[2]['folder'];fourth=web_app.DATA/'formal'/plan[3]['folder']
            (first/'protocol.json').unlink()
            (second/'transmission.json').write_text('{broken',encoding='utf-8')
            (third/'metrics.json').write_text('{broken',encoding='utf-8')
            meta=json.loads((fourth/'transmission.json').read_text(encoding='utf-8'));meta['duration_s']=float('nan')
            (fourth/'transmission.json').write_text(json.dumps(meta),encoding='utf-8')
            rows=web_app.inventory()
            self.assertEqual(len(rows),14)
            self.assertEqual([r['number'] for r in rows],list(range(1,15)))
            for row,name in zip(rows[:4],['protocol.json','transmission.json','metrics.json','transmission.json']):
                self.assertIn(name,row['error'])
            self.assertTrue(all('error' not in r for r in rows[4:]))
            self.assertEqual(web_app.details(rows[4]['id'])['config']['scheme'],'BFSK')
            json.dumps(rows,allow_nan=False)

    def test_existing_server_must_match_project(self):
        for project in (None,str(ROOT.parent/'another_project')):
            response=io.BytesIO(json.dumps(dict(app='acoustic-lab',project=project)).encode())
            with patch.object(sys,'argv',['web_app.py','--open']),patch.object(web_app,'ThreadingHTTPServer',side_effect=OSError('in use')),patch('urllib.request.urlopen',return_value=response),patch.object(web_app.webbrowser,'open') as opened:
                with self.assertRaisesRegex(SystemExit,'另一项目或旧版本'):web_app.main()
                opened.assert_not_called()

    def test_existing_matching_server_is_reused(self):
        response=io.BytesIO(json.dumps(dict(app='acoustic-lab',project=str(ROOT.resolve()))).encode())
        with patch.object(sys,'argv',['web_app.py','--open']),patch.object(web_app,'ThreadingHTTPServer',side_effect=OSError('in use')),patch('urllib.request.urlopen',return_value=response),patch.object(web_app.webbrowser,'open') as opened:
            web_app.main()
            opened.assert_called_once_with('http://127.0.0.1:8765')

    def test_failed_create_stays_out_of_inventory_and_retries(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='web_audit_') as temp,patch.object(web_app,'DATA',Path(temp)/'Data'):
            web_app.DATA.mkdir()
            server=web_app.ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)
            payload=dict(text='DH 2023012159 Hello_IoT_2026! Atomic create test.',scheme='BFSK',symbol_ms=10,interference='quiet',level=0)
            def request_create():
                return urlopen(Request(url+'/api/create',data=json.dumps(payload).encode(),headers={'X-Acoustic-Lab':'1','Content-Type':'application/json'}),timeout=10)
            def broken_prepare(folder,*args):
                folder.mkdir(parents=True)
                (folder/'protocol.json').write_text('{}')
                self.assertEqual(web_app.inventory(),[])
                raise OSError('injected write failure')
            try:
                with patch.object(web_app,'prepare',side_effect=broken_prepare):
                    with self.assertRaises(HTTPError) as caught:request_create()
                    self.assertEqual(caught.exception.code,400)
                self.assertEqual(web_app.inventory(),[])
                self.assertFalse(list(web_app.DATA.glob('.create_*')))
                with request_create() as response:
                    result=json.load(response)
                self.assertTrue((web_app.DATA/result['id']/'transmission.json').exists())
                self.assertEqual(len(web_app.inventory()),1)
                with urlopen(url+'/api/health') as response:
                    self.assertEqual(json.load(response)['project'],str(ROOT.resolve()))
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main(verbosity=2)

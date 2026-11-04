from pathlib import Path
import hashlib
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import bootstrap
from server import State, scan, Handler, ThreadingHTTPServer
from fixtures import fixture


class LocalAppTests(unittest.TestCase):
    def test_batch_outputs_and_restricted_loopback_API(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'楽譜';(source/'子').mkdir(parents=True)
            (source/'曲.mus').write_bytes(fixture('big','etf'))
            shutil.copyfile(ROOT/'tests/fixtures/triplet.musx',source/'曲.musx')
            (source/'子/分譜.mus').write_bytes(fixture('little','extended'))
            (source/'unknown.mus').write_bytes(fixture('big','etf','unverified'))
            (source/'bad.musx').write_bytes(b'broken')
            (source/'notes.txt').write_text('Do not convert',encoding='utf-8')
            before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in source.rglob('*') if p.is_file()}
            state=State();state.selection=scan(source,'folder')
            self.assertEqual((state.selection['count'],state.selection['ignored']),(5,1))
            job=state.start(state.selection['id'])
            deadline=time.monotonic()+100
            while job['status']=='running' and time.monotonic()<deadline:
                time.sleep(.1);job=state.view(job['id'])
            self.assertEqual(job['status'],'completed')
            self.assertEqual((job['counts']['success'],job['counts']['failed'],job['counts']['unsupported']),(3,1,1))
            output=Path(job['output'])
            self.assertEqual(output.name,'楽譜_変換済み')
            names={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(names,{'曲.mxl','曲_2.mxl','子/分譜.mxl'})
            saved={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*.mxl')}
            second=state.start(state.selection['id'])
            while second['status']=='running' and time.monotonic()<deadline:
                time.sleep(.1);second=state.view(second['id'])
            self.assertEqual(second['counts']['success'],3)
            self.assertEqual(Path(second['output']).name,'楽譜_変換済み_2')
            self.assertTrue(all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in saved.items()))
            self.assertEqual(before,{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in source.rglob('*') if p.is_file()})
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            server.state=state;server.token='test-token-only';server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def request(path,headers=None):
                req=urllib.request.Request(base+path,headers={'X-Finale-Token':server.token} if headers is None else headers)
                with urllib.request.urlopen(req,timeout=10) as response:return response.read()
            try:
                self.assertTrue(json.loads(request('/api/health'))['offline'])
                for headers in [{},{'X-Finale-Token':server.token,'Origin':'https://example.org'},
                                {'X-Finale-Token':server.token,'Host':'example.org'}]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:request('/api/health',headers)
                    self.assertEqual(caught.exception.code,403)
                with zipfile.ZipFile(io.BytesIO(request(f"/api/jobs/{job['id']}/archive"))) as archive:
                    self.assertEqual(len(archive.namelist()),3)
                    self.assertTrue(all(name.endswith('.mxl') for name in archive.namelist()))
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':unittest.main()

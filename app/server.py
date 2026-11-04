"""Loopback-only offline app, with native selection and local output folders."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap
import argparse
import copy
import io
import json
import mimetypes
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,unquote,urlsplit,quote
from conversion import convert,is_music,score_xml
from native_picker import choose

VERSION='0.6.2'
ROOT=bootstrap.ROOT
WEB=ROOT/'web'
REASONS={'changed':'確認後に原本が変更されました。もう一度選択してください。','conversion_error':'この形式・内容を読み取れませんでした。','mus_variant':'このMUSの世代・構造は現在読み取れません。FinaleでMUSXとして保存するか、MusicXMLへ書き出してください。','too_large':'1ファイル20 MBまでです。','timeout':'処理時間の上限に達しました。','save_error':'保存先への書き込みに失敗しました。'}


class UserError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status


def linked(path):
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&0x400)


def output_name(source,kind):
    return source.name if kind=='folder' else source.stem if source.suffix else source.name


def scan(source,kind):
    source=source.expanduser().resolve(strict=True)
    if kind=='folder' and (not source.is_dir() or source.parent==source):raise UserError('楽譜が入っているフォルダを選んでください。ドライブ全体は選択できません。')
    if kind=='file' and not source.is_file():raise UserError('ファイルを選んでください。')
    if kind=='file' and not is_music(source):raise UserError('MUS または MUSX を選んでください。.etf は未対応です。')
    base=source if kind=='folder' else source.parent
    files=[];ignored=0;links=0;unreadable=0
    pending=[source]
    while pending:
        path=pending.pop()
        try:
            if linked(path):links+=1;continue
            if path.is_dir():
                with os.scandir(path) as entries:pending.extend(Path(entry.path) for entry in entries)
            elif is_music(path):
                info=path.stat()
                files.append({'path':str(path),'name':path.relative_to(base).as_posix(),'bytes':info.st_size,'mtime':info.st_mtime_ns})
                if len(files)>5000:raise UserError('1回5000ファイルまでです。フォルダを分けて選択してください。')
            else:ignored+=1
        except OSError:unreadable+=1
    files.sort(key=lambda row:row['name'].casefold())
    if not files:raise UserError('MUS / MUSX ファイルが見つかりませんでした。')
    return {'id':uuid.uuid4().hex,'source':str(source),'kind':kind,'files':files,'count':len(files),'ignored':ignored,'linked':links,'unreadable':unreadable,'output_example':str(source.parent/(output_name(source,kind)+'_変換済み'))}


def selection_view(selection):
    if not selection:return None
    return {**{k:v for k,v in selection.items() if k!='files'},'files':[row['name'] for row in selection['files']]}


class State:
    def __init__(self):
        self.lock=threading.RLock();self.picker_lock=threading.Lock();self.selection=None;self.jobs={};self.current=None;self.last_activity=time.monotonic()

    def busy(self):return any(job['status']=='running' for job in self.jobs.values())

    def select(self,kind):
        if kind not in {'file','folder'}:raise UserError('選択方法を確認してください。')
        if not self.picker_lock.acquire(blocking=False):raise UserError('選択ウィンドウを確認してください。',409)
        try:
            with self.lock:
                if self.busy():raise UserError('変換が終わるまでお待ちください。',409)
            path=choose(kind)
            if path is None:return {'cancelled':True}
            selection=scan(path,kind)
            with self.lock:self.selection=selection;self.current=None
            return selection_view(selection)
        finally:self.picker_lock.release()

    def start(self,selection_id):
        with self.lock:
            if self.busy():raise UserError('変換中です。',409)
            selection=self.selection
            if not selection or selection['id']!=selection_id:raise UserError('ファイルまたはフォルダを選び直してください。')
            source=Path(selection['source']);stem=output_name(source,selection['kind'])+'_変換済み'
            for number in range(1,10001):
                output=source.parent/(stem if number==1 else stem+'_'+str(number))
                try:output.mkdir();break
                except FileExistsError:continue
                except OSError:raise UserError('元フォルダと同じ階層に保存できません。書き込み可能な場所へ原本のコピーを置いてから選択してください。')
            else:raise UserError('保存先フォルダを作成できません。')
            job={'id':uuid.uuid4().hex,'source':str(source),'output':str(output),'kind':selection['kind'],'status':'running','created':time.time(),'files':[]}
            used=set()
            for i,row in enumerate(selection['files']):
                relative=Path(row['name']);target=relative.with_suffix('.mxl') if relative.suffix else relative.with_name(relative.name+'.mxl');attempt=target;n=2
                while attempt.as_posix().casefold() in used:
                    attempt=target.with_name(target.stem+'_'+str(n)+'.mxl');n+=1
                used.add(attempt.as_posix().casefold())
                job['files'].append({'index':i,'name':row['name'],'output':attempt.as_posix(),'status':'pending'})
            self.jobs[job['id']]=job;self.current=job['id']
            threading.Thread(target=self.work,args=(job,copy.deepcopy(selection)),daemon=True).start()
            return self.view(job['id'])

    def view(self,job_id):
        with self.lock:
            if job_id not in self.jobs:raise UserError('結果が見つかりません。',404)
            job=copy.deepcopy(self.jobs[job_id])
        job['counts']={status:sum(row['status']==status for row in job['files']) for status in ['pending','running','success','failed','unsupported']}
        return job

    def work(self,job,selection):
        for row,original in zip(job['files'],selection['files']):
            with self.lock:row['status']='running'
            source=Path(original['path']);target=Path(job['output'])/row['output']
            try:
                info=source.stat()
                if linked(source) or info.st_size!=original['bytes'] or info.st_mtime_ns!=original['mtime']:
                    result={'status':'failed','reason':'changed'}
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists():raise FileExistsError('Output already exists')
                    result=convert(source,target)
            except OSError:result={'status':'failed','reason':'save_error'}
            except Exception:result={'status':'failed','reason':'conversion_error'}
            with self.lock:row.update(result)
        with self.lock:job['status']='completed';job['finished']=time.time()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def send_headers(self,status,length,content_type='application/json; charset=utf-8',filename=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(length));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename))
        self.end_headers()

    def send(self,status,body,content_type='application/json; charset=utf-8',filename=None):
        if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        self.send_headers(status,len(body),content_type,filename);self.wfile.write(body)

    def permitted(self,authenticated=True):
        port=self.server.server_port
        if self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:raise UserError('Invalid host',403)
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:raise UserError('Invalid origin',403)
        if self.headers.get('Sec-Fetch-Site')=='cross-site':raise UserError('Cross-site access denied',403)
        if authenticated:
            token=self.headers.get('X-Finale-Token') or parse_qs(urlsplit(self.path).query).get('token',[''])[0]
            if not secrets.compare_digest(token,self.server.token):raise UserError('起動用ファイルから開き直してください。',403)
        self.server.state.last_activity=time.monotonic()

    def get_job(self,path):
        parts=path.split('/')
        if len(parts)<4:raise UserError('Not found',404)
        return self.server.state.view(parts[3])

    def do_GET(self):
        try:
            path=unquote(urlsplit(self.path).path)
            self.permitted(path=='/' or path.startswith('/api/'))
            if path=='/api/health':return self.send(200,{'ok':True,'version':VERSION,'offline':True,'current_job':self.server.state.current,'selection':selection_view(self.server.state.selection)})
            if path.startswith('/api/jobs/'):
                parts=path.split('/');job=self.get_job(path)
                if len(parts)==4:return self.send(200,job)
                if parts[4]=='archive' and len(parts)==5:
                    if job['status']!='completed':raise UserError('変換中です。',409)
                    with tempfile.TemporaryFile() as temp:
                        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                            for row in job['files']:
                                if row['status']=='success':archive.write(Path(job['output'])/row['output'],Path(job['output']).name+'/'+row['output'])
                        length=temp.tell();temp.seek(0);self.send_headers(200,length,'application/zip',Path(job['output']).name+'.zip');shutil.copyfileobj(temp,self.wfile);return
                if parts[4]=='files' and len(parts)==6 and parts[5].isdigit():
                    index=int(parts[5])
                    if index>=len(job['files']):raise UserError('Not found',404)
                    row=job['files'][index]
                    if row['status']!='success':raise UserError('Not found',404)
                    target=Path(job['output'])/row['output']
                    if parse_qs(urlsplit(self.path).query).get('xml')==['true']:return self.send(200,score_xml(target),'application/xml')
                    return self.send(200,target.read_bytes(),'application/vnd.recordare.musicxml',target.name)
                raise UserError('Not found',404)
            if path.startswith('/api/'):raise UserError('Not found',404)
            target=WEB/'index.html' if path=='/' else (WEB/path.lstrip('/')).resolve()
            if WEB.resolve() not in target.resolve().parents or not target.is_file():raise UserError('Not found',404)
            return self.send(200,target.read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
        except UserError as error:self.send(error.status,{'detail':str(error)})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:self.send(500,{'detail':'読み込みに失敗しました。'})

    def do_POST(self):
        try:
            self.permitted();size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8192:raise UserError('Invalid request',413)
            data=json.loads(self.rfile.read(size));state=self.server.state
            if self.path=='/api/choose':return self.send(200,state.select(data.get('kind')))
            if self.path=='/api/jobs':return self.send(200,state.start(data.get('selection_id')))
            if self.path.startswith('/api/jobs/') and self.path.endswith('/open'):
                job=self.get_job(self.path);target=Path(job['output'])
                if os.name=='nt':os.startfile(target)
                else:subprocess.Popen(['/usr/bin/open',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return self.send(200,{'ok':True})
            if self.path=='/api/quit':
                if state.busy() or state.picker_lock.locked():raise UserError('変換・選択が終わってから終了してください。',409)
                self.send(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            raise UserError('Not found',404)
        except UserError as error:self.send(error.status,{'detail':str(error)})
        except (ValueError,TypeError):self.send(400,{'detail':'操作を確認してください。'})
        except Exception:self.send(500,{'detail':'操作できませんでした。ファイル・フォルダのアクセス許可を確認してください。'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=0);parser.add_argument('--session-file',type=Path);options=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',options.port),Handler);server.daemon_threads=True;server.state=State();server.token=secrets.token_urlsafe(32)
    url=f'http://127.0.0.1:{server.server_port}/?token={server.token}'
    if options.session_file:options.session_file.write_text(json.dumps({'url':url,'token':server.token,'port':server.server_port,'pid':os.getpid()}),encoding='utf-8')
    def idle_shutdown():
        while True:
            time.sleep(30)
            if not server.state.busy() and not server.state.picker_lock.locked() and time.monotonic()-server.state.last_activity>1800:
                server.shutdown();return
    threading.Thread(target=idle_shutdown,daemon=True).start()
    if not options.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.3)
    finally:server.server_close()


if __name__=='__main__':main()

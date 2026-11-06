"""Build offline Windows and universal Mac archives from verified runtimes/wheels."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import urllib.request
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.build-cache'
CACHE.mkdir(exist_ok=True)
RUNTIME_RELEASE = '20261026'
VERSION = '0.6.3'
RUNTIMES = {
    'windows': ('x86_64-pc-windows-msvc', '1f2ab53880fc67ea323398c6388e05af28addc99a8e389209f08a51fdff4b149'),
    'arm64': ('aarch64-apple-darwin', '353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e'),
    'x86_64': ('x86_64-apple-darwin', '37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734'),
}
PACKAGES = {'musx2mxl':'0.2.9','finale-file-parser':'0.4.0','defusedxml':'0.7.1','lxml':'6.0.2'}


def download(url, path, digest=None):
    if path.exists() and (not digest or hashlib.sha256(path.read_bytes()).hexdigest()==digest):
        return path
    with urllib.request.urlopen(url, timeout=120) as response:
        data=response.read()
    if digest and hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError('Digest mismatch: '+str(path))
    path.write_bytes(data)
    return path


def prepare():
    tasks=[]
    for key,(platform,digest) in RUNTIMES.items():
        name=f'cpython-3.12.16+{RUNTIME_RELEASE}-{platform}-install_only_stripped.tar.gz'
        url=f'https://github.com/astral-sh/python-build-standalone/releases/download/{RUNTIME_RELEASE}/'+urllib.parse.quote(name)
        tasks.append((url,CACHE/(key+'.tar.gz'),digest))
    provenance=[]
    for name,version in PACKAGES.items():
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
            metadata=json.load(response)
        urls=metadata['urls']
        for key in RUNTIMES:
            candidates=[x for x in urls if x['filename'].endswith('none-any.whl')]
            if not candidates:
                target={'windows':'win_amd64','arm64':'universal2.whl','x86_64':'universal2.whl'}[key]
                candidates=[x for x in urls if '-cp312-cp312-' in x['filename'] and target in x['filename']]
            if not candidates:
                raise ValueError(f'No {key} wheel for {name}: {[x["filename"] for x in urls]}')
            item=candidates[0]
            tasks.append((item['url'],CACHE/item['filename'],item['digests']['sha256']))
            provenance.append({'platform':key,'package':name,'version':version,'file':item['filename'],'sha256':item['digests']['sha256'],'url':item['url']})
    tasks.extend([
        ('https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.9.2/build/opensheetmusicdisplay.min.js',CACHE/'opensheetmusicdisplay.min.js','54d8e763a75559f78308d09b7bf36cd33f538a280c3c816b34355240335d6630'),
        ('https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.9.2/LICENSE',CACHE/'LICENSE-OSMD.txt','261655f10cf6b90bd062fbe3c7fa4dd03e0324fdfc4b53a3c7d626e3aec694a8'),
    ])
    unique={str(t[1]):t for t in tasks}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(download,*t) for t in unique.values()]
        for future in concurrent.futures.as_completed(futures):
            print('Prepared',future.result().name,flush=True)
    (CACHE/'wheels.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    win=ROOT/'release'/'Finale-Archive-Windows'
    runtime=win/'runtime'
    runtime.mkdir(parents=True,exist_ok=True)
    with tarfile.open(CACHE/'windows.tar.gz') as archive:
        for member in archive.getmembers():
            parts=PurePosixPath(member.name).parts
            if not parts or parts[0]!='python' or not member.isfile():
                continue
            target=runtime.joinpath(*parts[1:])
            if '..' in parts:raise ValueError('Unsafe tar member')
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as source:target.write_bytes(source.read())
    (ROOT/'web/assets/opensheetmusicdisplay.min.js').write_bytes((CACHE/'opensheetmusicdisplay.min.js').read_bytes())
    print('PREPARED',win,flush=True)


def add_bytes(archive,name,data,mode=0o644):
    info=zipfile.ZipInfo(name)
    info.create_system=3
    info.external_attr=(stat.S_IFREG|mode)<<16
    info.compress_type=zipfile.ZIP_DEFLATED
    archive.writestr(info,data)


def package():
    provenance=json.loads((CACHE/'wheels.json').read_text())
    win=ROOT/'release'/'Finale-Archive-Windows'
    for directory in ['app','web']:
        shutil.copytree(ROOT/directory,win/directory,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for item in provenance:
        if item['platform']!='windows':continue
        with zipfile.ZipFile(CACHE/item['file']) as archive:archive.extractall(win/'deps')
    shutil.copyfile(ROOT/'Start-Windows.cmd',win/'Start-Windows.cmd')
    shutil.copyfile(ROOT/'README-ja.txt',win/'README-ja.txt')
    shutil.copyfile(ROOT/'THIRD-PARTY.txt',win/'THIRD-PARTY.txt')
    shutil.copyfile(ROOT/'LICENSE',win/'LICENSE')
    shutil.copyfile(ROOT/'README.md',win/'README.md')
    shutil.copyfile(ROOT/'README.zh-CN.md',win/'README.zh-CN.md')
    shutil.copytree(ROOT/'LICENSES',win/'LICENSES',dirs_exist_ok=True)
    shutil.copyfile(CACHE/'LICENSE-OSMD.txt',win/'LICENSE-OSMD.txt')
    (win/'BUILD-MANIFEST.json').write_text(json.dumps({'version':VERSION,'python':'3.12.16','runtime_release':RUNTIME_RELEASE,'runtime_sha256':{k:v[1] for k,v in RUNTIMES.items()},'wheels':[p for p in provenance if p['platform']=='windows']},indent=2),encoding='utf-8')
    with zipfile.ZipFile(ROOT/'release'/f'Finale-Archive-Windows-v{VERSION}.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for file in win.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':archive.write(file,'Finale-Archive-Windows/'+file.relative_to(win).as_posix())
    with zipfile.ZipFile(ROOT/'release'/f'Finale-Archive-Mac-v{VERSION}.zip','w',zipfile.ZIP_DEFLATED) as archive:
        prefix='Finale-Archive-Mac/'
        for directory in ['app','web']:
            for file in (ROOT/directory).rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':add_bytes(archive,prefix+file.relative_to(ROOT).as_posix(),file.read_bytes())
        for name in ['Start-Mac.command','README-ja.txt','THIRD-PARTY.txt','LICENSE','README.md','README.zh-CN.md']:
            add_bytes(archive,prefix+name,(ROOT/name).read_bytes(),0o755 if name.endswith('.command') else 0o644)
        for file in (ROOT/'LICENSES').iterdir():
            if file.is_file():add_bytes(archive,prefix+'LICENSES/'+file.name,file.read_bytes())
        add_bytes(archive,prefix+'LICENSE-OSMD.txt',(CACHE/'LICENSE-OSMD.txt').read_bytes())
        for key in ['arm64','x86_64']:
            with tarfile.open(CACHE/(key+'.tar.gz')) as runtime:
                for member in runtime.getmembers():
                    parts=PurePosixPath(member.name).parts
                    if not parts or parts[0]!='python' or '..' in parts:continue
                    name=prefix+'runtime/'+key+'/'+'/'.join(parts[1:])
                    if member.isfile():
                        with runtime.extractfile(member) as data:add_bytes(archive,name,data.read(),member.mode)
                    elif member.issym():
                        info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,member.linkname)
            for item in provenance:
                if item['platform']!=key:continue
                with zipfile.ZipFile(CACHE/item['file']) as wheel:
                    for name in wheel.namelist():
                        if not name.endswith('/'):add_bytes(archive,prefix+'deps/'+key+'/'+name,wheel.read(name),0o755 if name.endswith(('.so','.dylib')) else 0o644)
        add_bytes(archive,prefix+'BUILD-MANIFEST.json',json.dumps({'version':VERSION,'python':'3.12.16','runtime_release':RUNTIME_RELEASE,'runtime_sha256':{k:v[1] for k,v in RUNTIMES.items()},'wheels':[p for p in provenance if p['platform']!='windows']},indent=2).encode())
    for file in (ROOT/'release').glob('*.zip'):
        print(file.name,round(file.stat().st_size/1024**2,1),'MB',hashlib.sha256(file.read_bytes()).hexdigest(),flush=True)


if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='package':package()

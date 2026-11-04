import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from defusedxml import ElementTree as ET

MAX_FILE=20*1024**2


def is_music(path):
    if path.suffix.lower() in {'.mus','.musx'}:
        return True
    if not path.suffix:
        try:
            with path.open('rb') as stream:return stream.read(18).startswith(b'ENIGMA BINARY FILE')
        except OSError:return False
    return False


def score_xml(path):
    with zipfile.ZipFile(path) as archive:
        container=ET.fromstring(archive.read('META-INF/container.xml'))
        entry=next(n.attrib['full-path'] for n in container.iter() if n.tag.split('}')[-1]=='rootfile')
        if archive.getinfo(entry).file_size>80*1024**2:raise ValueError('Output too large')
        return archive.read(entry)


def inspect(path):
    root=ET.fromstring(score_xml(path),forbid_dtd=False)
    parts=root.findall('part')
    if root.tag!='score-partwise' or not parts or not parts[0].findall('measure'):
        raise ValueError('No valid score')
    return {'parts':len(parts),'measures':len(parts[0].findall('measure')),'notes':len(root.findall('.//note'))}


def convert(source,target):
    if source.stat().st_size>MAX_FILE:return {'status':'failed','reason':'too_large'}
    command=[sys.executable,'-I',str(Path(__file__).with_name('worker.py')),str(source),str(target)]
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    try:
        process=subprocess.run(command,capture_output=True,timeout=90,**options)
        output=(process.stdout+process.stderr).decode('utf-8',errors='replace')
        markers=[line[7:] for line in output.splitlines() if line.startswith('RESULT=')]
        if process.returncode==0 and markers and target.is_file():
            return {'status':'success','reason':'review_required',**json.loads(markers[-1])}
        target.unlink(missing_ok=True)
        return {'status':'unsupported' if 'MUS_UNREADABLE' in output else 'failed',
                'reason':'mus_variant' if 'MUS_UNREADABLE' in output else 'conversion_error'}
    except subprocess.TimeoutExpired:
        target.unlink(missing_ok=True)
        return {'status':'failed','reason':'timeout'}
    except OSError:
        target.unlink(missing_ok=True)
        return {'status':'failed','reason':'save_error'}

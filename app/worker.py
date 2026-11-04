"""One isolated, network-disabled conversion; no persistent intermediate files."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap
bootstrap.deny_network()
import gzip
import io
import json
import zipfile
from defusedxml import ElementTree as ET
from conversion import inspect,MAX_FILE

try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(60,65))
    resource.setrlimit(resource.RLIMIT_FSIZE,(80*1024**2,80*1024**2))
except (ImportError,OSError,ValueError):
    pass

source,target=map(Path,sys.argv[1:3])
if source.stat().st_size>MAX_FILE:raise ValueError('Input too large')
with source.open('rb') as stream:legacy=stream.read(18).startswith(b'ENIGMA BINARY FILE')
if legacy or source.suffix.lower()=='.mus':
    from mus_compat import read_score
    from finale_file_parser.export.musicxml import to_musicxml
    try:
        xml=to_musicxml(read_score(source))
    except Exception:
        print('MUS_UNREADABLE')
        raise SystemExit(20)
    if len(xml)>80*1024**2:raise ValueError('Output too large')
    container=b'''<?xml version="1.0" encoding="UTF-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>'''
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('mimetype','application/vnd.recordare.musicxml',compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml',container)
        archive.writestr('score.musicxml',xml)
else:
    from musx2mxl.musx2mxl import convert_file,decrypt
    from finale_compat import install
    with zipfile.ZipFile(source) as archive:
        if not {'score.dat','NotationMetadata.xml'}.issubset(archive.namelist()):raise ValueError('Not MUSX')
        if sum(info.file_size for info in archive.infolist())>128*1024**2:raise ValueError('Expanded input too large')
        encoded=bytearray(archive.read('score.dat'))
        decrypt(encoded)
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:decoded=stream.read(128*1024**2+1)
        if len(decoded)>128*1024**2:raise ValueError('Expanded score too large')
        ET.fromstring(decoded,forbid_dtd=True)
        ET.fromstring(archive.read('NotationMetadata.xml'),forbid_dtd=True)
    install()
    convert_file(str(source),str(target))
facts=inspect(target)
if not facts['notes']:raise ValueError('No musical events')
print('RESULT='+json.dumps(facts))

"""Derive smaller per-CPU downloads from an already built universal Mac ZIP."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.6.2'


def main():
    release=ROOT/'release'
    source=release/f'Finale-Archive-Mac-v{VERSION}.zip'
    prefix='Finale-Archive-Mac/'
    for arch,label in [('arm64','Apple-Silicon'),('x86_64','Intel')]:
        target=release/f'Finale-Archive-Mac-{label}-v{VERSION}.zip'
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as out:
            for info in original.infolist():
                relative=info.filename[len(prefix):]
                parts=relative.split('/')
                if parts[0] in {'runtime','deps'} and len(parts)>1 and parts[1] in {'arm64','x86_64'} and parts[1]!=arch:
                    continue
                data=original.read(info.filename)
                if relative=='BUILD-MANIFEST.json':
                    manifest=json.loads(data);manifest['target_architecture']=arch
                    manifest['wheels']=[p for p in manifest['wheels'] if p['platform']==arch]
                    manifest['runtime_sha256']={arch:manifest['runtime_sha256'][arch]}
                    data=json.dumps(manifest,indent=2).encode()
                if relative=='README-ja.txt':
                    text=data.decode('utf-8').replace('Mac版にはApple SiliconとIntel両方の実行環境を同梱しています。',
                        f'このZIPは {label} Mac 専用です。異なるCPUのMacでは対応するZIPを選んでください。')
                    data=(f'このZIPの対象CPU: {label}\n\n'+text).encode('utf-8')
                if relative=='README.md':
                    text=data.decode('utf-8').replace('Mac builds include Apple Silicon and Intel runtimes.',
                        f'This ZIP contains the {label} Mac runtime only; select the matching download for your Mac.')
                    data=(f'This ZIP targets {label} Macs only.\n\n'+text).encode('utf-8')
                if relative=='Start-Mac.command':
                    text=data.decode('utf-8').replace('exec "$APP_DIR/runtime/',
                        'if [ ! -x "$APP_DIR/runtime/$ARCH/bin/python3.12" ]; then\n'
                        '    echo "Please download the Mac build matching your CPU (Apple Silicon or Intel)."\n'
                        '    exit 1\nfi\nexec "$APP_DIR/runtime/')
                    data=text.encode('utf-8')
                out.writestr(info,data)
        with zipfile.ZipFile(target) as archive:
            if archive.testzip() is not None:raise ValueError('Variant ZIP failed CRC validation')
            if prefix+'runtime/'+arch+'/bin/python3.12' not in archive.namelist():
                raise ValueError('Variant is missing its runtime')
        print(target.name,hashlib.sha256(target.read_bytes()).hexdigest(),flush=True)


if __name__=='__main__':main()

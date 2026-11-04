"""Obtain the pinned preview dependency for source runs; no runtime downloads."""
from pathlib import Path
import hashlib
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OSMD_URL='https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.9.2/build/opensheetmusicdisplay.min.js'
OSMD_SHA256='54d8e763a75559f78308d09b7bf36cd33f538a280c3c816b34355240335d6630'


def main():
    target=ROOT/'web/assets/opensheetmusicdisplay.min.js'
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==OSMD_SHA256:
        print('Preview dependency is ready.')
        return
    with urllib.request.urlopen(OSMD_URL,timeout=90) as response:
        data=response.read()
    if hashlib.sha256(data).hexdigest()!=OSMD_SHA256:
        raise ValueError('Preview dependency digest does not match the pinned version')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
    print('Preview dependency downloaded and verified.')


if __name__=='__main__':main()

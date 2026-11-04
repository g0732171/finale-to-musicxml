"""Use only the dependencies shipped inside this offline distribution."""
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
if sys.platform=='darwin':
    architecture='arm64' if platform.machine()=='arm64' else 'x86_64'
    DEPS=ROOT/'deps'/architecture
else:
    DEPS=ROOT/'deps'
sys.path.insert(0,str(DEPS))


def deny_network():
    def audit(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr'}:
            raise PermissionError('This offline converter does not use network connections')
    sys.addaudithook(audit)

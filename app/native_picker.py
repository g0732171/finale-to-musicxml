"""Native file/folder selection; no browser directory-access API is required."""
import json
import os
from pathlib import Path
import subprocess
import sys


def choose(kind):
    if kind not in {'file','folder'}:raise ValueError('Invalid selection')
    if sys.platform=='darwin':
        command='POSIX path of (choose '+('folder' if kind=='folder' else 'file')+' with prompt "'+('変換するフォルダを選んでください' if kind=='folder' else '変換するMUS / MUSXファイルを選んでください')+'")'
        process=subprocess.run(['/usr/bin/osascript','-e','activate','-e',command],capture_output=True,text=True,encoding='utf-8')
        if process.returncode:
            if '-128' in process.stderr:return None
            raise OSError('ファイル選択ウィンドウを開けませんでした。')
        return Path(process.stdout.rstrip('\r\n'))
    if os.name=='nt':
        process=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),kind],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode:raise OSError('ファイル選択ウィンドウを開けませんでした。')
        value=json.loads(process.stdout.decode('utf-8'))['path']
        return Path(value) if value else None
    raise OSError('Windows または macOS で実行してください。')


if __name__=='__main__':
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk()
    root.withdraw()
    root.attributes('-topmost',True)
    root.update()
    try:
        if sys.argv[1]=='folder':
            value=filedialog.askdirectory(parent=root,title='変換するフォルダを選んでください',mustexist=True)
        else:
            value=filedialog.askopenfilename(parent=root,title='変換するMUS / MUSXファイルを選んでください',filetypes=[('Finale scores',('*.mus','*.musx')),('All files','*')])
        print(json.dumps({'path':value or None}),flush=True)
    finally:root.destroy()

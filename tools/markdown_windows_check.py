"""Native offline Windows local-link safety checks; no provider/network access."""
import ctypes
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module(sys.argv[1] if len(sys.argv)>1 else 'pfc')
if os.name!='nt':raise SystemExit('Windows-only check')

memory_check='''import pfc
assert pfc.limit_markdown_worker_memory(), 'Cannot enforce worker memory limit'
try:
    data=bytearray(600*1024*1024)
except MemoryError:
    print('PASS: Windows Job Object refuses a 600 MiB allocation in a private child')
else:
    raise AssertionError('Worker memory limit was not enforced')
'''
result=subprocess.run([sys.executable,'-c',memory_check],cwd=Path(pfc.__file__).parent,
                      capture_output=True,text=True,timeout=15)
assert result.returncode==0,result.stderr
print(result.stdout.strip(),flush=True)

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);scope=root/'scope';scope.mkdir()
    target=scope/'normal.md';target.write_bytes(b'hello')
    data,signature=pfc.read_linked_markdown(target,scope,2)
    assert data==b'hel' and signature[1]==5
    assert pfc.read_linked_markdown(target,scope,-1)[0]==b''
    print('PASS: exact regular-file handle read and metadata probe',flush=True)
    # A directory junction is allowed to be created without symlink privilege.
    outside=root/'outside';outside.mkdir();(outside/'secret.md').write_bytes(b'not for preview')
    junction=scope/'redirect'
    result=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],capture_output=True)
    assert result.returncode==0,result.stderr
    try:
        try:pfc.read_linked_markdown(junction/'secret.md',scope,100)
        except (ValueError,OSError):pass
        else:raise AssertionError('Junction was followed')
    finally:os.rmdir(junction)
    print('PASS: junction redirection refused',flush=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetFileAttributesW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32]
    kernel.GetFileAttributesW.argtypes=[ctypes.c_wchar_p]
    attrs=kernel.GetFileAttributesW(str(target))
    assert kernel.SetFileAttributesW(str(target),attrs|0x1000)
    try:
        with patch('msvcrt.open_osfhandle',side_effect=AssertionError('Unexpected content handle conversion')):
            try:pfc.read_linked_markdown(target,scope,100)
            except ValueError:pass
            else:raise AssertionError('Offline file was read')
    finally:assert kernel.SetFileAttributesW(str(target),attrs)
    print('PASS: offline attribute refused before content stream creation (not a live cloud-provider test)',flush=True)

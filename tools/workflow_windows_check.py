"""Native Windows text replacement contracts; runs on disposable fixtures only."""
import codecs
import ctypes
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from ctypes import wintypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pfc

assert os.name == 'nt'
with tempfile.TemporaryDirectory(prefix='pfc-save-contract-') as raw:
    root = Path(raw); path = root/'sample.txt'
    count = 0
    for codec, bom in (('utf-8', b''), ('utf-8', codecs.BOM_UTF8),
            ('utf-16-le', codecs.BOM_UTF16_LE), ('utf-16-be', codecs.BOM_UTF16_BE),
            ('utf-32-le', codecs.BOM_UTF32_LE), ('utf-32-be', codecs.BOM_UTF32_BE)):
        for eol in ('\n', '\r\n', '\r'):
            for final in ('', eol):
                content = '第一行'+eol+'café 🙂'+final
                path.write_bytes(bom+content.encode(codec))
                document = pfc.read_text_document(path)
                document.save(document.text.replace('café','coffee'))
                assert path.read_bytes() == bom+content.replace('café','coffee').encode(codec)
                count += 1
    path.write_bytes(b'original\r\n')
    ads = Path(str(path)+':PFCFixture')
    ads.write_bytes(b'preserve-stream')
    security = ctypes.WinDLL('advapi32', use_last_error=True).GetFileSecurityW
    security.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p,
                         wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    security.restype = wintypes.BOOL
    def acl():
        needed = wintypes.DWORD()
        security(str(path),7,None,0,ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not security(str(path),7,buffer,len(buffer),ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:needed.value]
    before = acl()
    document = pfc.read_text_document(path); document.save('edited\n')
    assert path.read_bytes() == b'edited\r\n'
    assert ads.read_bytes() == b'preserve-stream'
    assert acl() == before
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
        ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path),0x80000000,1,None,3,0,None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        document = pfc.read_text_document(path)
        try: document.save('must not replace')
        except OSError: pass
        else: raise AssertionError('Locked replacement unexpectedly succeeded')
        assert path.read_bytes() == b'edited\r\n'
        assert not list(root.glob('.pfc-edit-*'))
    finally: kernel.CloseHandle(handle)
    path.chmod(0o444)
    try:
        document = pfc.read_text_document(path)
        assert document.reason
        try: document.save('must stay read-only')
        except OSError: pass
        else: raise AssertionError('Read-only file was overwritten')
        assert path.read_bytes() == b'edited\r\n'
    finally: path.chmod(0o600)
    print(f'PASS: {count} native BOM/EOL round trips, ACL and ADS preservation, locked-file refusal/cleanup', flush=True)
print('ARTIFACT_SHA256='+hashlib.sha256(Path(pfc.__file__).read_bytes()).hexdigest(), flush=True)

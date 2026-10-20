"""Reproducibly emit an apply_patch patch for pinned, offline preview assets.

No dependency installation or VM/network changes. Downloads are integrity-checked;
only trusted upstream sources below are included, never documents being previewed.
"""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import textwrap
import urllib.request
import zipfile
import zlib

SOURCES = (
    ('mermaid', '12.2.0', 'https://registry.npmjs.org/mermaid/-/mermaid-12.2.0.tgz',
     'sha512', 'w7nr/SFrLO7BaVTs3dQTvYSV6nYSBj0Yy9DjBhsIJtAcHqRzXSq4Pg32ujHZ/AdWsAMNEvvhbm5dt9E2tOiHzw=='),
    ('yaml', '6.0.3', 'https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz',
     'sha256', 'd76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f'),
    ('tomli', '2.5.0', 'https://files.pythonhosted.org/packages/b0/78/9ad63712633ed3ab5cc1a648d863d7e7da371e9425e209555a0fe711b695/tomli-2.5.0.tar.gz',
     'sha256', '264507556cd8b8c8e7c6ee037cdf443a463f03f4c958e57195e3d369711b8ff6'),
)


def build():
    code = ['"""Generated pinned offline render dependencies; see docs/preview-dependencies.md."""',
            'import base64', 'import zlib', '', 'PREVIEW_ASSETS = {']
    licenses = []
    for name,version,url,algorithm,expected in SOURCES:
        data=urllib.request.urlopen(url,timeout=60).read(40*1024*1024)
        digest=hashlib.new(algorithm,data).digest()
        assert (base64.b64encode(digest).decode() if algorithm=='sha512' else digest.hex())==expected,name
        archive=tarfile.open(fileobj=io.BytesIO(data))
        if name=='mermaid':
            payload=archive.extractfile('package/dist/mermaid.min.js').read()
            assert b'import(' not in payload, 'Offline bundle must not load remote chunks'
            license_data=archive.extractfile('package/LICENSE').read().decode()
        else:
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as target:
                for entry in archive.getmembers():
                    marker='/lib/yaml/' if name=='yaml' else '/src/tomli/'
                    if marker in entry.name and entry.name.endswith('.py') and not entry.name.endswith('/cyaml.py'):
                        suffix=entry.name.split(marker,1)[1]
                        target.writestr(zipfile.ZipInfo(f'_pfc_{name}/{suffix}',(2026,1,1,0,0,0)),archive.extractfile(entry).read())
            payload=output.getvalue()
            assert len(payload)>10000,name
            license_entry=next(e for e in archive.getmembers() if e.name.split('/')[-1] in ('LICENSE','LICENSE.txt'))
            license_data=archive.extractfile(license_entry).read().decode()
        encoded=base64.b85encode(zlib.compress(payload,9)).decode()
        code.append(f'    {name!r}: (')
        code.extend('        '+repr(part) for part in textwrap.wrap(encoded,100,break_on_hyphens=False))
        code.append('    ),')
        licenses.append(f'## {name} {version}\n\nSource: {url}\n\n{algorithm}: {expected}\n\n```text\n{license_data.strip()}\n```\n')
    code.extend(['}', '', 'PREVIEW_DEPENDENCY_NOTICES = '+repr('\n'.join(licenses)), '',
                 'def preview_asset(name):', '    return zlib.decompress(base64.b85decode(PREVIEW_ASSETS[name]))', ''])
    root=Path(__file__).resolve().parents[1]
    outputs={'pycommander/previewassets.py':'\n'.join(code),
             'docs/preview-dependencies.md':'# Offline preview dependencies\n\nPinned upstream assets are bundled in the portable file; no runtime download or pip install.\nOnly library code runs; previewed documents are never imported or executed.\n\n'+'\n'.join(licenses)}
    print('*** Begin Patch')
    for path,value in outputs.items():
        print('*** '+('Delete' if (root/path).exists() else 'Add')+' File: '+path)
        if (root/path).exists():print('*** Add File: '+path)
        for line in value.splitlines():print('+'+line)
    print('*** End Patch')

if __name__=='__main__':build()

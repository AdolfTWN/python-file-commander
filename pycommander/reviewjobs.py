"""Cancelable process-isolated comparison jobs. UI never waits for diff work."""
import dataclasses
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from .reviewcore import review_opcodes
from .textio import read_text_document
from .workbook import read_workbook
from .mdjobs import limit_markdown_worker_memory
from .preview import render_markdown


def comparison_worker_main():
    try:
        if not limit_markdown_worker_memory(2*1024*1024*1024):
            raise OSError('Cannot enforce comparison worker memory budget')
        request = json.load(sys.stdin)
        mode = request['mode']
        if mode == 'load':
            docs = [read_text_document(Path(p), limit=20*1024*1024) for p in request['paths']]
            result = {'documents': [dict(text=d.text, encoding=d.encoding, bom=d.bom.hex(),
                       ending=d.ending,digest=d.digest,reason=d.reason) for d in docs]}
            result['opcodes'] = review_opcodes(docs[0].text,docs[1].text)
        elif mode == 'diff':
            if len(request['texts'])!=2 or any(len(t)>20*1024*1024 for t in request['texts']):
                raise ValueError('Comparison exceeds 20 MiB per side')
            result = {'opcodes': review_opcodes(*request['texts'])}
        elif mode == 'workbook': result = {'books': [read_workbook(Path(p)) for p in request['paths']]}
        elif mode == 'preview':
            if len(request['text'])>64000:raise ValueError('Reading excerpt exceeds limit')
            content,spans=render_markdown(request['text'])
            result={'content':content,'spans':spans}
        else: raise ValueError('Unknown comparison request')
    except MemoryError: result = {'error':'Comparison exceeded the 2 GiB worker memory budget; sources unchanged'}
    except Exception as exc: result = {'error': str(exc)}
    json.dump(result,sys.stdout,ensure_ascii=True)


class ComparisonJobs:
    def __init__(self):
        self.serial=0; self.results=queue.Queue(); self.process=None; self.lock=threading.Lock()

    def submit(self, request):
        self.cancel(); serial=self.serial
        if __package__:
            args=[sys.executable,'-c','from pycommander.reviewjobs import comparison_worker_main; comparison_worker_main()']
            cwd=str(Path(__file__).resolve().parents[1])
        else:
            args=[sys.executable,'-c',"import runpy,sys; runpy.run_path(sys.argv[1],run_name='pfc_compare_worker')['comparison_worker_main']()",str(Path(__file__).resolve())]
            cwd=str(Path(__file__).resolve().parent)
        def work():
            process=None
            try:
                with self.lock:
                    if serial!=self.serial: return
                    process=subprocess.Popen(args,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
                    self.process=process
                out,err=process.communicate(json.dumps(request).encode(),timeout=5 if request['mode']=='preview' else 90)
                result=json.loads(out) if process.returncode==0 else {'error':'Comparison worker exited without a result'}
            except Exception as exc:
                if process and process.poll() is None: process.kill(); process.communicate()
                result={'error':str(exc)}
            if serial==self.serial: self.results.put((serial,result))
        threading.Thread(target=work,daemon=True).start()
        return serial

    def cancel(self):
        with self.lock:
            self.serial+=1
            if self.process and self.process.poll() is None: self.process.terminate()
            self.process=None

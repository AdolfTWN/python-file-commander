"""Disposable, offline static rasterization using an installed Chromium browser.

Only loopback CDP is contacted. Documents are sanitized, remote/file resources
blocked, source scripts disabled, and no existing browser profile is touched.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from .previewassets import preview_asset
from .rendercore import static_preview_html,static_preview_svg,notebook_preview_html


def preview_browser_path():
    candidates=[]
    if os.name=='nt':
        for name in ('ProgramFiles(x86)','ProgramFiles','LOCALAPPDATA'):
            base=os.environ.get(name)
            if base:
                candidates.extend(Path(base)/suffix for suffix in
                    ('Microsoft/Edge/Application/msedge.exe','Google/Chrome/Application/chrome.exe'))
    else:
        candidates.extend(filter(None,(shutil.which(name) for name in
            ('chromium','chromium-browser','google-chrome','microsoft-edge'))))
    return next((str(path) for path in candidates if Path(path).is_file()),None)


class _PreviewCDP:
    def __init__(self,url,deadline):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='ws' or parsed.hostname not in {'127.0.0.1','localhost'}:raise ValueError('Non-local render endpoint')
        self.deadline=deadline;self.serial=0;self.buffer=bytearray()
        self.socket=socket.create_connection(('127.0.0.1',parsed.port),timeout=5)
        key=base64.b64encode(os.urandom(16)).decode()
        request=(f'GET {parsed.path} HTTP/1.1\r\nHost: 127.0.0.1:{parsed.port}\r\nUpgrade: websocket\r\n'
                 f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        self.socket.sendall(request.encode())
        while b'\r\n\r\n' not in self.buffer:
            part=self.socket.recv(4096)
            if not part:raise OSError('Render handshake closed')
            self.buffer.extend(part)
            if len(self.buffer)>16384:raise ValueError('Invalid render handshake')
        header,rest=self.buffer.split(b'\r\n\r\n',1);self.buffer=bytearray(rest)
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if b' 101 ' not in header or expected not in header:raise ValueError('Render handshake refused')
    def read(self,count):
        self.socket.settimeout(max(.05,self.deadline-time.monotonic()))
        while len(self.buffer)<count:
            part=self.socket.recv(min(65536,count-len(self.buffer)))
            if not part:raise OSError('Render channel closed')
            self.buffer.extend(part)
        result=bytes(self.buffer[:count]);del self.buffer[:count];return result
    def send(self,value,opcode=1):
        raw=value.encode() if isinstance(value,str) else value;length=len(raw)
        header=bytes((0x80|opcode,0x80|min(length,126))) if length<126 else bytes((0x80|opcode,0x80|(126 if length<65536 else 127)))+struct.pack('>H' if length<65536 else '>Q',length)
        mask=os.urandom(4)
        masked=bytes(v^mask[i%4] for i,v in enumerate(raw))
        self.socket.sendall(header+mask+masked)
    def receive(self):
        chunks=[];total=0
        while True:
            a,b=self.read(2);length=b&127
            if length==126:length=struct.unpack('>H',self.read(2))[0]
            elif length==127:length=struct.unpack('>Q',self.read(8))[0]
            if length>32*1024*1024:raise ValueError('Render response limit reached')
            mask=self.read(4) if b&128 else None
            raw=self.read(length)
            if mask:raw=bytes(v^mask[i%4] for i,v in enumerate(raw))
            opcode=a&15
            if opcode==8:raise OSError('Render channel closed')
            if opcode==9:self.send(raw,10);continue
            if opcode==10:continue
            chunks.append(raw);total+=len(raw)
            if total>32*1024*1024:raise ValueError('Render response limit reached')
            if a&128:return json.loads(b''.join(chunks))
    def call(self,method,**params):
        self.serial+=1;ident=self.serial
        self.send(json.dumps(dict(id=ident,method=method,params=params)))
        while time.monotonic()<self.deadline:
            response=self.receive()
            if response.get('id')==ident:
                if 'error' in response:raise ValueError('Render protocol: '+str(response['error'].get('message')))
                return response.get('result',{})
        raise TimeoutError('Static rendering timed out')
    def evaluate(self,expression):
        result=self.call('Runtime.evaluate',expression=expression,awaitPromise=True,returnByValue=True)
        if 'exceptionDetails' in result:
            info=result['exceptionDetails'];raise ValueError('Render: '+info.get('exception',{}).get('description',info.get('text','failed'))[:500])
        return result.get('result',{}).get('value')
    def close(self):self.socket.close()


def raster_preview(text,suffix,*,width=1100,font_size=16):
    browser=preview_browser_path()
    if not browser:raise ValueError('Static graphics require installed Microsoft Edge or Chrome/Chromium; showing Source (no automatic installation)')
    content_limited=False
    if suffix in {'.mmd','.mermaid'}:
        if len(text)>100000:raise ValueError('Diagram source limit reached; use Source')
        # Do not allow document-level directives/frontmatter to weaken renderer policy.
        if re_preview_directive(text):raise ValueError('Diagram configuration directives are disabled; use plain diagram syntax')
        body='<div id="diagram"></div>';notice='Offline diagram · read-only'
    elif suffix=='.svg':body=static_preview_svg(text);notice='Static SVG · scripts and external resources blocked'
    elif suffix=='.ipynb':body,notice,content_limited=notebook_preview_html(text,with_limits=True)
    else:body=static_preview_html(text);notice='Static HTML · scripts/forms/external resources blocked'
    width=max(640,min(1600,int(width)));font_size=max(12,min(48,int(font_size)))
    style=(f'html,body{{margin:0;background:white;color:#202124;font:{font_size}px Arial,sans-serif}}'
           'body{padding:18px;box-sizing:border-box;overflow-wrap:anywhere}h1,h2,h3{line-height:1.25}'
           'table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #b8c1ca;padding:6px;vertical-align:top}'
           'pre{background:#f3f5f7;border:1px solid #d9dfe5;padding:10px;white-space:pre-wrap;overflow-wrap:anywhere}'
           'code{font-family:Consolas,monospace}img,svg{max-width:100%;height:auto}section{border-bottom:1px solid #c5cdd5;padding-bottom:12px}'
           '.output{background:#f4faf5}.error{color:#9c1623}a{color:#1261a0;text-decoration:underline}')
    document=('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
              'content="default-src &apos;none&apos;; img-src data:; style-src &apos;unsafe-inline&apos;; '
              'script-src &apos;none&apos;; connect-src &apos;none&apos;; form-action &apos;none&apos;; base-uri &apos;none&apos;">'
              '<style>'+style+'</style><body>'+body+'</body>')
    cache=None
    owned_root=os.environ.get('PFC_STATIC_ROOT')
    if owned_root and Path(owned_root).is_dir():cache=Path(owned_root)
    elif os.name!='nt':
        snap_cache=Path.home()/'snap/chromium/common'
        cache=snap_cache if browser.startswith('/snap/') and snap_cache.is_dir() else Path.home()/'.cache'
        cache.mkdir(exist_ok=True)
    deadline=time.monotonic()+22
    # Chromium child teardown can briefly retain Windows file handles. The
    # parent worker owns this root and retries cleanup after the worker exits.
    with tempfile.TemporaryDirectory(prefix='pfc-static-',dir=cache,ignore_cleanup_errors=True) as profile:
        args=[browser,'--headless=new','--disable-gpu','--disable-background-networking','--disable-component-update',
              '--disable-sync','--metrics-recording-only','--no-first-run','--no-default-browser-check',
              '--disable-extensions','--disable-default-apps','--disable-breakpad',
              '--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=<-loopback>',
              '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
              '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
              '--user-data-dir='+profile,'--window-size='+str(width)+',900','about:blank']
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 creationflags=0x08000000 if os.name=='nt' else 0)
        channel=None
        try:
            active=Path(profile)/'DevToolsActivePort'
            port=_preview_browser_port(active,process,deadline)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            targets=json.load(opener.open(f'http://127.0.0.1:{port}/json/list',timeout=5))
            target=next(t for t in targets if t.get('type')=='page')
            channel=_PreviewCDP(target['webSocketDebuggerUrl'],deadline)
            channel.call('Page.enable');channel.call('Network.enable')
            channel.call('Network.setBlockedURLs',urls=['http://*','https://*','file://*','ftp://*','ws://*','wss://*'])
            channel.call('Emulation.setDeviceMetricsOverride',width=width,height=900,deviceScaleFactor=1,mobile=False)
            frame=channel.call('Page.getFrameTree')['frameTree']['frame']['id']
            channel.call('Page.setDocumentContent',frameId=frame,html=document)
            if suffix in {'.mmd','.mermaid'}:
                channel.evaluate(preview_asset('mermaid').decode('utf-8')+'\ntrue')
                channel.evaluate('mermaid.initialize({startOnLoad:false,securityLevel:"strict",suppressErrorRendering:true,maxTextSize:100000,maxEdges:500,theme:"default",themeVariables:{fontSize:'+json.dumps(str(font_size)+'px')+'},flowchart:{htmlLabels:false},secure:["securityLevel","startOnLoad","maxTextSize","maxEdges","secure"]});true')
                channel.evaluate('(async()=>{const r=await mermaid.render("pfc_diagram",'+json.dumps(text)+');document.getElementById("diagram").innerHTML=r.svg;return true})()')
            failed_images=channel.evaluate('Promise.all(Array.from(document.images).map(i=>i.decode().then(()=>0,()=>1))).then(r=>r.reduce((a,b)=>a+b,0))')
            if failed_images:notice+='; '+str(failed_images)+' embedded images could not be decoded (see Source)'
            metrics=channel.call('Page.getLayoutMetrics').get('cssContentSize',{})
            content_height=channel.evaluate('Math.max(document.body.getBoundingClientRect().height,...Array.from(document.body.children).filter(e=>!["STYLE","SCRIPT"].includes(e.tagName)).map(e=>e.getBoundingClientRect().bottom))')
            height=min(8000,max(100,math.ceil(content_height+2)))
            maximum=max(100,4000000//width)
            clipped=height>maximum or content_height>8000
            height=min(height,maximum)
            text_model=channel.evaluate('''(()=>{let p=[],n,limited=false;const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
while((n=w.nextNode())){if(!n.textContent.trim()||n.parentElement.closest('style,script'))continue;
const r=document.createRange();r.selectNodeContents(n);const b=r.getBoundingClientRect();if(!b.width||!b.height)continue;
if(p.length>=3000){limited=true;break;}
if(b.y>='''+str(height)+'''||b.bottom<=0||b.x>='''+str(width)+'''||b.right<=0){limited=true;continue;}
if(b.bottom>'''+str(height)+'''||b.y<0||b.right>'''+str(width)+'''||b.x<0)limited=true;
p.push({text:n.textContent,x:b.x,y:b.y,w:b.width,h:b.height});}return {positions:p,limited}})()''')
            positions=text_model['positions']
            offset=0
            for position in positions:
                position.update(start=offset,end=offset+len(position['text']));offset=position['end']+1
            if not positions and not channel.evaluate('Array.from(document.querySelectorAll("svg,img")).some(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0})'):
                raise ValueError('No static visible content after safety filtering; use Source')
            png=channel.call('Page.captureScreenshot',format='png',captureBeyondViewport=True,
                             clip=dict(x=0,y=0,width=width,height=height,scale=1))['data']
            if len(png)>12*1024*1024:raise ValueError('Rendered image size limit reached')
            if clipped:notice+='; rendered height limited; use Source for remaining content'
            if text_model['limited']:notice+='; rendered search covers part of visible text; use Source for remaining content'
            return dict(kind='image',png=png,width=width,height=height,positions=positions,
                        content='\n'.join(p['text'] for p in positions),notice=notice,
                        truncated=clipped or content_limited or text_model['limited'])
        finally:
            if channel:
                try:channel.call('Browser.close')
                except (OSError,ValueError,TimeoutError):pass
                channel.close()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                else:process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()


def _preview_browser_port(active, process, deadline):
    """Chromium publishes this file non-atomically and briefly locks it on Windows."""
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise ValueError('Installed browser could not start isolated static renderer')
        try:
            lines=active.read_text(encoding='ascii').splitlines()
            port=int(lines[0])
            if 0<port<65536:return port
        except (OSError,ValueError,IndexError):
            pass
        time.sleep(.05)
    raise TimeoutError('Static renderer startup timed out')


def re_preview_directive(text):
    import re
    return bool(re.search(r'%%\s*\{|^\s*---\s*$',text,re.M))

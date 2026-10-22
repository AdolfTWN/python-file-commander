"""Bounded read-only document models. No document code, constructors or links run."""
import csv
import html
from html.parser import HTMLParser
import importlib.abc
import importlib.util
import io
import json
import re
import sys
import zipfile
from .previewassets import preview_asset
from .markdownblocks import markdown_blocks

RENDER_EXTENSIONS={'.json','.jsonl','.ndjson','.csv','.tsv','.svg','.yaml','.yml','.toml',
                   '.ipynb','.mmd','.mermaid','.diff','.patch','.html','.htm'}
RENDER_INPUT_LIMIT=2*1024*1024
RENDER_NODE_LIMIT=3000
RENDER_CELL_LIMIT=20000
RENDER_DEPTH_LIMIT=64


class _PreviewVendor(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    """Only our integrity-checked, bundled library code; never document imports."""
    def __init__(self,name):
        self.prefix='_pfc_'+name
        self.archive=zipfile.ZipFile(io.BytesIO(preview_asset(name)))
    def find_spec(self,fullname,path=None,target=None):
        if fullname!=self.prefix and not fullname.startswith(self.prefix+'.'):return None
        path=fullname.replace('.','/')
        package=path+'/__init__.py' in self.archive.namelist()
        if package or path+'.py' in self.archive.namelist():
            return importlib.util.spec_from_loader(fullname,self,is_package=package)
    def create_module(self,spec):return None
    def exec_module(self,module):
        name=module.__name__.replace('.','/')+('/__init__.py' if hasattr(module,'__path__') else '.py')
        module.__file__='<PFC vendor/'+name+'>'
        exec(compile(self.archive.read(name),module.__file__,'exec'),module.__dict__)


def preview_vendor(name):
    prefix='_pfc_'+name
    if prefix not in sys.modules:
        finder=next((f for f in sys.meta_path if isinstance(f,_PreviewVendor) and f.prefix==prefix),None)
        if finder is None:sys.meta_path.insert(0,_PreviewVendor(name))
    return __import__(prefix)


class _PreviewNumber(str):pass
class _PreviewObject(list):pass


def _preview_json(text):
    def constant(value):raise ValueError('Non-finite JSON number: '+value)
    return json.loads(text,parse_int=_PreviewNumber,parse_float=_PreviewNumber,
                      parse_constant=constant,object_pairs_hook=_PreviewObject)


def _preview_scalar(value):
    if isinstance(value,_PreviewNumber):return str(value),'number'
    if isinstance(value,str):return value,'string'
    if value is None:return 'null','null'
    if isinstance(value,bool):return ('true' if value else 'false'),'boolean'
    return str(value),type(value).__name__


def structured_preview(text,suffix,*,node_limit=RENDER_NODE_LIMIT,text_limit=2*1024*1024):
    rows=[];notice=[];seen=set();text_budget=0;partial=False
    def emit(parent,label,value,kind,path):
        nonlocal text_budget
        if len(rows)>=node_limit:raise OverflowError(f'First {node_limit:,} nodes displayed; search can reveal more')
        text_budget+=len(str(label))+len(value)+len(path)
        if text_budget>text_limit:raise OverflowError('Structure text limit reached')
        iid='n'+str(len(rows));rows.append(dict(id=iid,parent=parent,label=str(label),value=value,kind=kind,path=path))
        return iid
    def walk(value,parent='',label='$',path='',depth=0):
        if depth>RENDER_DEPTH_LIMIT:raise OverflowError('Nesting limit reached; use Source')
        if isinstance(value,(_PreviewObject,dict,list)):
            kind='object' if isinstance(value,(_PreviewObject,dict)) else 'array'
            iid=emit(parent,label,str(len(value))+' items',kind,path)
            if id(value) in seen:
                rows[-1]['value']='Alias / recursive reference';return
            seen.add(id(value))
            pairs=value if isinstance(value,_PreviewObject) else value.items() if isinstance(value,dict) else enumerate(value)
            keys=set()
            for key,item in pairs:
                if str(key) in keys:notice.append('Duplicate keys are preserved')
                keys.add(str(key));pointer=path+'/'+str(key).replace('~','~0').replace('/','~1')
                walk(item,iid,key,pointer,depth+1)
        else:
            shown,kind=_preview_scalar(value);emit(parent,label,shown,kind,path)
    try:
        if suffix in {'.yaml','.yml'}:
            # Compose nodes, never construct Python objects or invoke YAML tags.
            yaml=preview_vendor('yaml');events=0
            for event in yaml.parse(text,Loader=yaml.BaseLoader):
                events+=1
                if events>20000:raise ValueError('YAML event limit reached')
            documents=list(yaml.compose_all(text,Loader=yaml.BaseLoader))
            def yaml_walk(node,parent='',label='$',path='',depth=0):
                if depth>RENDER_DEPTH_LIMIT:raise OverflowError('Nesting limit reached; use Source')
                if node is None:return
                kind=node.id
                iid=emit(parent,label,node.value if kind=='scalar' else str(len(node.value))+' items',kind,path)
                if kind=='scalar':return
                if id(node) in seen:rows[-1]['value']='Alias / recursive reference';return
                seen.add(id(node))
                pairs=node.value if kind=='mapping' else enumerate(node.value)
                for key,value in pairs:
                    key=key.value if hasattr(key,'value') else str(key)
                    if not isinstance(key,str):key='[complex key]'
                    yaml_walk(value,iid,key,path+'/'+key.replace('~','~0').replace('/','~1'),depth+1)
            for number,node in enumerate(documents):yaml_walk(node,label='$' if len(documents)==1 else 'Document '+str(number+1))
        elif suffix=='.toml':
            try:import tomllib
            except ImportError:tomllib=preview_vendor('tomli')
            walk(tomllib.loads(text,parse_float=_PreviewNumber))
        elif suffix in {'.jsonl','.ndjson'}:
            for number,line in enumerate(text.splitlines(),1):
                if not line.strip():raise ValueError(f'Blank JSONL record at line {number}')
                try:record=_preview_json(line)
                except ValueError as exc:raise ValueError(f'JSONL line {number}: {exc}') from exc
                walk(record,label='Record '+str(number),path='/'+str(number-1))
        else:walk(_preview_json(text))
    except OverflowError as exc:
        if not rows:raise ValueError(str(exc)) from exc
        notice.append(str(exc));partial=True
    summary=suffix[1:].upper()+' structure · '+str(len(rows))+' nodes'
    return dict(kind='tree',rows=rows,content='\n'.join(r['path']+'  '+r['value'] for r in rows),notice=summary+('; '+'; '.join(dict.fromkeys(notice)) if notice else ''),truncated=partial)


def structured_search(text,suffix,needle,case=False,index=0):
    """Worker-only bounded scan; return one real ancestor path, never a text view.

    Preorder IDs match the initial tree, including duplicate object keys. Only
    the selected branch crosses the process boundary, keeping Tk work bounded.
    """
    model=structured_preview(text,suffix,node_limit=100000,text_limit=8*1024*1024)
    pattern=re.compile(re.escape(needle),0 if case else re.I) if needle else None
    hits=[];limited=False
    if pattern:
        for row in model['rows']:
            found=False
            for field in ('label','value'):
                for match in pattern.finditer(row[field]):
                    found=True
                    if len(hits)>=5000:limited=True;break
                    hits.append((row,field,match.start(),match.end()))
                if limited:break
            if limited:break
            if not found:
                match=pattern.search(row['path'])
                if match:
                    if len(hits)>=5000:limited=True;break
                    hits.append((row,'path',match.start(),match.end()))
    result=dict(kind='tree_search',rows=[],count=len(hits),index=-1,
                partial=model['truncated'] or limited)
    if hits:
        index=index%len(hits);row,field,start,end=hits[index]
        lookup={r['id']:r for r in model['rows']};branch=[row]
        while branch[-1]['parent']:branch.append(lookup[branch[-1]['parent']])
        result.update(rows=list(reversed(branch)),index=index,field=field,start=start,end=end)
    return result


def table_preview(text,suffix):
    # No type inference: identifiers, dates, leading zeros and formulas stay text.
    delimiter='\t' if suffix=='.tsv' else ','
    if suffix=='.csv':
        try:delimiter=csv.Sniffer().sniff(text[:16384],delimiters=',;\t|').delimiter
        except csv.Error:pass
    reader=csv.reader(io.StringIO(text,newline=''),delimiter=delimiter,strict=True)
    rows=[];width=0;notice=''
    for row in reader:
        next_width=max(width,len(row))
        if len(rows)>=1001 or (len(rows)+1)*next_width>RENDER_CELL_LIMIT or len(row)>200:
            notice='Table preview limited to 1,000 records / 20,000 cells; use Source';break
        rows.append(row);width=next_width
    header=(rows.pop(0) if rows else [])
    header+=['Column '+str(i+1) for i in range(len(header),width)]
    return dict(kind='grid',columns=header,rows=[r+['']*(width-len(r)) for r in rows],
                content=text,notice=notice or ('Empty table' if not header else ''),delimiter=delimiter,truncated=bool(notice))


def patch_preview(text):
    spans=[];sections=[];position=0;files=0;added=0;removed=0
    for line in text.splitlines(keepends=True):
        tag=None
        if line.startswith(('diff --git ','--- ','+++ ')):
            tag='render_heading'
            if line.startswith('diff --git '):files+=1
        elif line.startswith('@@'):
            tag='render_hunk';sections.append(dict(title=line.strip(),offset=position))
        elif line.startswith('+'):tag='render_add';added+=1
        elif line.startswith('-'):tag='render_remove';removed+=1
        if tag:spans.append((position,position+len(line),tag))
        position+=len(line)
        if len(spans)>20000:raise ValueError('Patch span limit reached; use Source')
    return dict(kind='document',content=text,spans=spans,sections=sections,
                notice=f'{files} file sections · +{added} / −{removed} lines · read-only (never applied)')


def safe_preview_css(value):
    lowered=re.sub(r'/\*.*?\*/','',value,flags=re.S).lower()
    if any(t in lowered for t in ('\\','@import','@font-face','expression','javascript:','behavior','-moz-binding')):return ''
    for match in re.finditer(r'url\((.*?)\)',lowered,flags=re.S):
        if not re.fullmatch(r'''\s*["']?#[\w.-]+["']?\s*''',match.group(1)):return ''
    return value[:65536]


def safe_preview_image(uri,allow_svg=False):
    import base64,struct
    if allow_svg and uri.startswith('data:image/svg+xml;base64,') and len(uri)<700000:
        try:
            decoded=base64.b64decode(uri.split(',',1)[1],validate=True).decode('utf-8')
            safe=static_preview_svg(decoded)
            return 'data:image/svg+xml;base64,'+base64.b64encode(safe.encode()).decode()
        except (ValueError,UnicodeError):return None
    match=re.fullmatch(r'data:image/(png|jpeg|gif);base64,([A-Za-z0-9+/=\s]+)',uri)
    if not match or len(uri)>3*1024*1024:return None
    try:
        data=base64.b64decode(match[2],validate=False);width=height=0
        if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:width,height=struct.unpack('>II',data[16:24])
        elif data[:3]==b'GIF' and len(data)>=10:width,height=struct.unpack('<HH',data[6:10])
        elif data.startswith(b'\xff\xd8'):
            pos=2
            while pos+9<len(data):
                if data[pos]!=255:break
                marker=data[pos+1];pos+=2
                if marker in (0xd8,0xd9):continue
                length=int.from_bytes(data[pos:pos+2],'big')
                if length<2:break
                if marker in (0xc0,0xc1,0xc2):height,width=struct.unpack('>HH',data[pos+3:pos+7]);break
                pos+=length
        if not width or not height or width*height>4000000:return None
        return 'data:image/'+match[1]+';base64,'+base64.b64encode(data).decode()
    except (ValueError,OverflowError,struct.error):return None


class _StaticPreviewHTML(HTMLParser):
    ALLOWED=set('html head body title div span p pre code h1 h2 h3 h4 h5 h6 strong em b i u s del ul ol li table thead tbody tfoot tr th td hr br blockquote a details summary sup sub dl dt dd img style'.split())
    VOID={'hr','br','img'}
    BLOCKED={'script','iframe','object','embed','form','input','button','textarea','select','video','audio','canvas','svg','math','template','noscript'}
    def __init__(self,allow_styles=True):
        super().__init__(convert_charrefs=True);self.output=[];self.skipped=[];self.in_style=False;self.nodes=0;self.allow_styles=allow_styles
    def handle_starttag(self,tag,attrs):
        self.nodes+=1
        if self.nodes>10000:raise ValueError('HTML node limit reached')
        if self.skipped:
            if tag not in self.VOID and tag not in {'input','embed'}:self.skipped.append(tag)
            return
        if tag in self.BLOCKED or (tag=='style' and not self.allow_styles):
            if tag not in {'input','embed'}:self.skipped.append(tag)
            return
        if tag not in self.ALLOWED:return
        if tag in {'html','head','body','title'}:return
        allowed=[]
        for key,value in attrs:
            value=value or ''
            if key=='style' and self.allow_styles:
                css=safe_preview_css(value)
                if css:allowed.append(('style',css))
            elif key in {'colspan','rowspan'} and value.isdigit() and 0<int(value)<=50:allowed.append((key,value))
            elif key in {'class','id','title','alt'}:allowed.append((key,value[:2000]))
            elif tag=='img' and key=='src':
                safe=safe_preview_image(value,allow_svg=True)
                if safe:allowed.append((key,safe))
            elif tag=='img' and key in {'width','height'} and value.isdigit() and 0<int(value)<=2048:allowed.append((key,value))
        if tag=='img' and not any(k=='src' for k,v in allowed):
            self.output.append('<span>[External or unsupported image omitted]</span>');return
        self.output.append('<'+tag+(' open' if tag=='details' else '')+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in allowed)+'>')
        if tag=='style':self.in_style=True
    def handle_endtag(self,tag):
        if self.skipped:
            if tag in self.skipped:self.skipped=self.skipped[:len(self.skipped)-1-self.skipped[::-1].index(tag)]
            return
        if tag in self.ALLOWED and tag not in self.VOID and tag not in {'html','head','body','title'}:self.output.append('</'+tag+'>')
        if tag=='style':self.in_style=False
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)
    def handle_data(self,value):
        if not self.skipped:self.output.append(safe_preview_css(value) if self.in_style else html.escape(value))


def static_preview_html(text,allow_styles=True):
    import base64
    def svg_image(match):
        try:
            safe=static_preview_svg(match[0]);uri=base64.b64encode(safe.encode()).decode()
            return '<img src="data:image/svg+xml;base64,'+uri+'">'
        except (ValueError,RecursionError):return '<span>[Unsupported SVG omitted]</span>'
    text=re.sub(r'<svg\b[^>]*>[\s\S]*?</svg\s*>',svg_image,text,flags=re.I)
    parser=_StaticPreviewHTML(allow_styles);parser.feed(text);parser.close()
    return ''.join(parser.output)


def static_preview_svg(text):
    import xml.etree.ElementTree as ET
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)',text,re.I):raise ValueError('SVG declarations/entities are not allowed')
    root=ET.fromstring(text)
    if root.tag.split('}')[-1]!='svg':raise ValueError('Not an SVG document')
    forbidden={'script','foreignObject','animate','animateMotion','animateTransform','set','audio','video','iframe'}
    count=0
    def clean(node,depth=0):
        nonlocal count
        count+=1
        if count>5000 or depth>64:raise ValueError('SVG complexity limit reached')
        node.tag=node.tag.split('}')[-1]
        for key,value in list(node.attrib.items()):
            local=key.split('}')[-1]
            del node.attrib[key]
            if local.lower().startswith('on'):continue
            if local in {'href','src'}:
                if value.startswith('#'):node.set('href',value)
                elif node.tag=='image':
                    safe=safe_preview_image(value)
                    if safe:node.set('href',safe)
                continue
            if local=='style':value=safe_preview_css(value)
            elif 'url(' in value.lower() and not safe_preview_css(value):continue
            if local not in {'xmlns','base'} and value:node.set(local,value)
        if node.tag=='style':node.text=safe_preview_css(node.text or '')
        for child in list(node):
            if child.tag.split('}')[-1] in forbidden:node.remove(child)
            else:clean(child,depth+1)
    clean(root);root.set('xmlns','http://www.w3.org/2000/svg')
    return ET.tostring(root,encoding='unicode')


def markdown_preview_html(text):
    """Conservative static Markdown for notebook cells, never raw HTML execution."""
    output=[]
    for kind,raw in markdown_blocks(text):
        if kind=='table':
            output.append('<table>'+''.join('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in row)+'</tr>' for row in raw[0])+'</table>')
        elif kind=='properties':output.append('<pre>'+html.escape('\n'.join(raw))+'</pre>')
        elif kind=='code':output.append('<pre>'+html.escape(raw)+'</pre>')
        else:
            match=re.match(r'^(#{1,6})\s+(.*)',raw)
            tag='h'+str(len(match[1])) if match else 'p';value=match[2] if match else raw
            escaped=html.escape(value)
            escaped=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',escaped)
            escaped=re.sub(r'`([^`]+)`',r'<code>\1</code>',escaped)
            output.append('<'+tag+'>'+escaped+'</'+tag+'>')
    return ''.join(output)


def notebook_preview_html(text):
    data=json.loads(text)
    if not isinstance(data,dict) or data.get('nbformat')!=4 or not isinstance(data.get('cells'),list):raise ValueError('Expected notebook format 4 with cells')
    output=[];notice='Stored outputs only; no cell execution';images=0
    def source(value):
        if isinstance(value,list) and all(isinstance(v,str) for v in value):return ''.join(value)
        if isinstance(value,str):return value
        raise ValueError('Invalid notebook text field')
    for index,cell in enumerate(data['cells'][:60]):
        if not isinstance(cell,dict):raise ValueError('Invalid notebook cell')
        kind=cell.get('cell_type');value=source(cell.get('source',''))
        output.append('<section><h3>Cell '+str(index+1)+' · '+html.escape(str(kind))+'</h3>')
        output.append(markdown_preview_html(value) if kind=='markdown' else '<pre><code>'+html.escape(value)+'</code></pre>')
        for item in cell.get('outputs',[])[:30]:
            if not isinstance(item,dict):continue
            if 'text' in item:output.append('<pre class="output">'+html.escape(source(item['text']))+'</pre>')
            if item.get('output_type')=='error':output.append('<pre class="error">'+html.escape('\n'.join(item.get('traceback',[])))+'</pre>')
            mime=item.get('data',{})
            if not isinstance(mime,dict):continue
            handled=False
            for name in ('image/png','image/jpeg','image/gif'):
                if name in mime and images<8:
                    uri=safe_preview_image('data:'+name+';base64,'+source(mime[name]))
                    if uri:output.append('<img src="'+uri+'">');images+=1;handled=True;break
            if not handled and 'image/svg+xml' in mime and images<8:
                import base64
                svg=static_preview_svg(source(mime['image/svg+xml']))
                output.append('<img src="data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()+'">');images+=1;handled=True
            if not handled and 'text/html' in mime:output.append(static_preview_html(source(mime['text/html']),allow_styles=False));handled=True
            if not handled and 'text/plain' in mime:output.append('<pre class="output">'+html.escape(source(mime['text/plain']))+'</pre>')
            if not handled and any(k.startswith('image/') or k.startswith('application/') for k in mime):notice+='; unsupported rich output omitted (see Source)'
        output.append('</section>')
    if len(data['cells'])>60:notice+='; first 60 cells only; use Source'
    result=''.join(output)
    if len(result)>4*1024*1024:raise ValueError('Notebook visual output limit reached; use Source')
    return result,notice

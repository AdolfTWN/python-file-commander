"""Read-only Office Open XML values/formulas. Never starts Excel or a macro."""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .textio import read_text_document


WORKBOOK_XML_LIMIT = 256 * 1024 * 1024
WORKBOOK_CELL_LIMIT = 1_000_000
_WB_MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_WB_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def workbook_normalize_element(element):
    # Strict OOXML uses different namespaces from the more common Transitional
    # format. Normalize identifiers only; never silently return an empty book.
    namespaces = {
        '{http://purl.oclc.org/ooxml/spreadsheetml/main}': _WB_MAIN,
        '{http://purl.oclc.org/ooxml/officeDocument/relationships}': _WB_REL,
    }
    for source, target in namespaces.items():
        if element.tag.startswith(source):element.tag=target+element.tag[len(source):]
        for key in list(element.attrib):
            if key.startswith(source):element.set(target+key[len(source):],element.attrib.pop(key))
    return element


def excel_date(serial,date1904):
    value=float(serial)
    if not date1904 and 60<=value<61:
        return '1900-02-29 (Excel leap-day compatibility) '+str(value-60)
    epoch=datetime(1904,1,1) if date1904 else datetime(1899,12,31) if value<60 else datetime(1899,12,30)
    return (epoch+timedelta(days=value)).isoformat(timespec='milliseconds')


def cell_values_equal(a,b,mode='Both'):
    if a is None or b is None:return a==b
    if mode=='Formulas':return a[2]==b[2]
    def normalized(cell):
        kind,value,_=cell
        if kind in ('s','inlineStr','str','text'):kind='text'
        if kind=='n' and value is not None:
            try:value=Decimal(value)
            except InvalidOperation:pass
        return kind,value
    equal=normalized(a)==normalized(b)
    return equal if mode=='Values' else equal and a[2]==b[2]


def cell_position(ref):
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', ref or '')
    if not match: raise ValueError('Invalid cell address')
    column = 0
    for ch in match[1]: column = column * 26 + ord(ch)-64
    row = int(match[2])
    if column > 16384 or row > 1048576: raise ValueError('Cell address outside Excel bounds')
    return row, column


def cell_address(row, col):
    letters = ''
    while col:
        col, rem = divmod(col-1,26); letters = chr(65+rem)+letters
    return letters+str(row)


def shared_formula(formula, anchor, target):
    ar, ac = cell_position(anchor); tr, tc = cell_position(target)
    # Skip Excel string literals and quoted sheet names. References outside
    # literals retain absolute components; no formula is evaluated.
    tokens = re.split(r'("(?:[^"]|"")*"|\x27(?:[^\x27]|\x27\x27)*\x27|\[[^]]*\])', formula)
    pattern = re.compile(r'(?<![A-Za-z0-9_.])([$]?)([A-Z]{1,3})([$]?)([1-9][0-9]*)(?![A-Za-z0-9_(])')
    def shift(m):
        r,c = cell_position(m[2]+m[4])
        r += 0 if m[3] else tr-ar; c += 0 if m[1] else tc-ac
        if r < 1 or c < 1 or r > 1048576 or c > 16384: return '#REF!'
        address = cell_address(r,c); letters = address.rstrip('0123456789')
        return m[1]+letters+m[3]+str(r)
    return ''.join(token if n%2 else pattern.sub(shift,token) for n,token in enumerate(tokens))


def read_workbook(path):
    """Sparse sheets, each cell = (kind, cached value or None, formula)."""
    path = Path(path)
    if path.suffix.lower() in ('.csv','.tsv'):
        text = read_text_document(path).text
        cells = {}
        for row, values in enumerate(csv.reader(io.StringIO(text), delimiter='\t' if path.suffix.lower()=='.tsv' else ','),1):
            for col,value in enumerate(values,1):
                if len(cells) >= WORKBOOK_CELL_LIMIT: raise ValueError('Table exceeds 1,000,000 populated cells')
                cells[cell_address(row,col)] = ('text',value,'')
        return {'date1904':False,'sheets':[{'name':'Table','state':'visible','cells':cells,'merged':[]}]}
    if path.suffix.lower() not in ('.xlsx','.xlsm'):
        raise ValueError('Supported workbooks: .xlsx / .xlsm (read-only)')
    try:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>100000 or len({i.filename for i in infos})!=len(infos):
                raise ValueError('Invalid or oversized workbook package')
            if any(i.flag_bits&1 for i in infos): raise ValueError('Encrypted workbooks are not supported')
            total=0
            def xml(name):
                nonlocal total
                info=z.getinfo(name); total+=info.file_size
                if info.file_size>WORKBOOK_XML_LIMIT or total>WORKBOOK_XML_LIMIT:
                    raise ValueError('Workbook XML exceeds 256 MiB safety budget')
                data=z.read(name)
                safe=data.replace(b'\x00',b'').upper()
                if b'<!DOCTYPE' in safe or b'<!ENTITY' in safe:
                    raise ValueError('DTD/entity declarations are not allowed')
                root=ET.fromstring(data)
                for element in root.iter():workbook_normalize_element(element)
                return root
            def sheet_elements(name):
                nonlocal total
                info=z.getinfo(name);total+=info.file_size
                if info.file_size>WORKBOOK_XML_LIMIT or total>WORKBOOK_XML_LIMIT:
                    raise ValueError('Workbook XML exceeds 256 MiB safety budget')
                class CheckedReader:
                    def __init__(self,stream):self.stream=stream;self.tail=b'';self.count=0
                    def read(self,size):
                        chunk=self.stream.read(size);self.count+=len(chunk)
                        safe=(self.tail+chunk).replace(b'\x00',b'').upper()
                        if self.count>WORKBOOK_XML_LIMIT or b'<!DOCTYPE' in safe or b'<!ENTITY' in safe:
                            raise ValueError('Unsafe or oversized worksheet XML')
                        self.tail=chunk[-64:];return chunk
                with z.open(name) as stream:
                    stack=[]
                    for event,element in ET.iterparse(CheckedReader(stream),events=('start','end')):
                        if event=='start':
                            workbook_normalize_element(element)
                            if not stack and element.tag!=_WB_MAIN+'worksheet':
                                raise ValueError('Unsupported worksheet XML namespace or type')
                            stack.append(element);continue
                        if element.tag in (_WB_MAIN+'c',_WB_MAIN+'mergeCell'):
                            yield element
                            element.clear()
                        elif element.tag==_WB_MAIN+'row':
                            element.clear()
                            if len(stack)>1:stack[-2].remove(element)
                        stack.pop()
            book=xml('xl/workbook.xml')
            if book.tag!=_WB_MAIN+'workbook':raise ValueError('Unsupported workbook XML namespace')
            links=xml('xl/_rels/workbook.xml.rels')
            targets={r.get('Id'):r.get('Target') for r in links if r.get('TargetMode')!='External'}
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                for si in xml('xl/sharedStrings.xml'):
                    strings.append(''.join(t.text or '' for t in si.iter(_WB_MAIN+'t')))
            prop=book.find(_WB_MAIN+'workbookPr')
            result={'date1904':prop is not None and prop.get('date1904') in ('1','true'),'sheets':[]}
            date_styles=set()
            if 'xl/styles.xml' in z.namelist():
                styles=xml('xl/styles.xml');formats={}
                for fmt in styles.findall(_WB_MAIN+'numFmts/'+_WB_MAIN+'numFmt'):
                    code=re.sub(r'"[^"]*"|\\.|\[[^]]*\]','',fmt.get('formatCode','')).lower()
                    formats[int(fmt.get('numFmtId'))]=bool(re.search(r'[ymdhs]',code))
                for index,style in enumerate(styles.findall(_WB_MAIN+'cellXfs/'+_WB_MAIN+'xf')):
                    number=int(style.get('numFmtId','0'))
                    if number in set(range(14,23))|{45,46,47} or formats.get(number,False):date_styles.add(index)
            count=0
            for element in book.findall(_WB_MAIN+'sheets/'+_WB_MAIN+'sheet'):
                name=element.get('name')
                if not name or any(s['name']==name for s in result['sheets']):raise ValueError('Missing or duplicate worksheet name')
                target=targets.get(element.get(_WB_REL+'id'))
                if not target: raise ValueError('Missing or external worksheet relationship')
                target=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
                if not target.startswith('xl/') or '..' in target.split('/'):
                    raise ValueError('Unsafe worksheet relationship')
                cells={}; formulas={}; pending=[];merged=[]
                for c in sheet_elements(target):
                    if c.tag==_WB_MAIN+'mergeCell':merged.append(c.get('ref'));continue
                    count+=1
                    if count>WORKBOOK_CELL_LIMIT: raise ValueError('Workbook exceeds 1,000,000 populated cells')
                    ref=c.get('r'); cell_position(ref)
                    if ref in cells: raise ValueError('Duplicate cell address')
                    typ=c.get('t','n'); v=c.find(_WB_MAIN+'v'); f=c.find(_WB_MAIN+'f')
                    value=v.text if v is not None else None
                    if typ=='s':
                        string_index=int(value)
                        if not 0<=string_index<len(strings):raise ValueError('Invalid shared-string index')
                        value=strings[string_index]
                    if typ=='inlineStr': value=''.join(t.text or '' for t in c.iter(_WB_MAIN+'t'))
                    if typ=='n' and value is not None and int(c.get('s','0')) in date_styles:
                        try:value=excel_date(value,result['date1904']);typ='date'
                        except (ValueError,OverflowError):pass
                    formula=f.text or '' if f is not None else ''
                    if f is not None and f.get('t')=='shared':
                        key=f.get('si')
                        if formula: formulas[key]=(ref,formula)
                        else: pending.append((ref,key))
                    cells[ref]=(typ,value,formula)
                for ref,key in pending:
                    if key not in formulas: raise ValueError('Missing shared formula anchor')
                    anchor,formula=formulas[key]
                    typ,value,_=cells[ref];cells[ref]=(typ,value,shared_formula(formula,anchor,ref))
                result['sheets'].append({'name':element.get('name'), 'state':element.get('state','visible'),
                                         'cells':cells,'merged':merged})
            return result
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError, TypeError) as exc:
        raise ValueError('Unreadable, encrypted or invalid Excel workbook: '+str(exc)) from exc


def workbook_rows(left, right, key_columns=(), header_row=1):
    """Pair sparse cells, optionally align unique row keys. Never guess duplicates."""
    a=left['cells'] if left else {}; b=right['cells'] if right else {}
    if not key_columns:
        return [(ref,ref,a.get(ref),b.get(ref)) for ref in sorted(set(a)|set(b),key=cell_position)]
    def keyed(cells):
        rows={}
        for ref,value in cells.items():
            r,c=cell_position(ref); rows.setdefault(r,{})[c]=(ref,value)
        index={}
        for r,values in rows.items():
            if r<=header_row: key=('header',r)
            else:
                key=tuple(values.get(c,('',('n',None,'')))[1][1] for c in key_columns)
                if all(v in (None,'') for v in key): raise ValueError('Key columns contain an empty row key')
            if key in index: raise ValueError('Duplicate row key; use coordinate alignment or unique keys')
            index[key]=values
        return index
    la,rb=keyed(a),keyed(b); out=[]
    for key in list(la)+[key for key in rb if key not in la]:
        l,r=la.get(key,{}),rb.get(key,{})
        for col in sorted(set(l)|set(r)):
            ar,av=l.get(col,('',None));br,bv=r.get(col,('',None));out.append((ar,br,av,bv))
    return out

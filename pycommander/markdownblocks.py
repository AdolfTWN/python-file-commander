"""Lossless, dependency-free Markdown table/frontmatter structure for preview.

This is a reader, not a YAML interpreter: property values (including nested or
unrecognized syntax) stay literal. No constructors, plugins or links execute.
"""
import re
import unicodedata


def table_cells(line):
    """Split pipe tables, retaining escaped pipes and pipes in code spans."""
    value = line.strip()
    cells, cell, fence, index = [], [], 0, 0
    while index < len(value):
        char = value[index]
        if char == '\\' and index+1 < len(value) and value[index+1] in '|\\':
            cell.append(value[index+1]); index += 2; continue
        if char == '`':
            end = index
            while end < len(value) and value[end] == '`': end += 1
            count = end-index
            if fence == count: fence = 0
            elif not fence: fence = count
            cell.append(value[index:end]); index = end; continue
        if char == '|' and not fence:
            cells.append(''.join(cell).strip()); cell = []
        else:
            cell.append(char)
        index += 1
    cells.append(''.join(cell).strip())
    if value.startswith('|'): cells.pop(0)
    if value.endswith('|') and cells and cells[-1] == '': cells.pop()
    return cells


def markdown_blocks(text):
    """Yield text, fenced-code lines, tables and a complete frontmatter block."""
    lines = text.lstrip('\ufeff').splitlines()
    index, fence_char, fence_size = 0, '', 0
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1,len(lines)) if lines[i].strip() in ('---','...')), None)
        if end is not None:
            yield 'properties', lines[1:end]
            index = end+1
    while index < len(lines):
        raw = lines[index]
        fence = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$',raw)
        if fence_char:
            if fence and fence.group(1)[0] == fence_char and len(fence.group(1)) >= fence_size and not fence.group(2).strip():
                fence_char = ''
            else:
                yield 'code', raw
            index += 1; continue
        if fence:
            fence_char, fence_size = fence.group(1)[0], len(fence.group(1))
            index += 1; continue
        if index+1 < len(lines) and '|' in raw:
            header, delimiter = table_cells(raw), table_cells(lines[index+1])
            if header and len(header) == len(delimiter) and all(re.fullmatch(r':?-{2,}:?',c) for c in delimiter):
                aligns = ['center' if c.startswith(':') and c.endswith(':') else
                          'right' if c.endswith(':') else 'left' for c in delimiter]
                rows = [header]; index += 2
                while index < len(lines) and lines[index].strip() and '|' in lines[index]:
                    if re.match(r'^\s*(`{3,}|~{3,})',lines[index]): break
                    rows.append(table_cells(lines[index])); index += 1
                # Extra cells are retained rather than silently discarded.
                yield 'table', (rows, aligns)
                continue
        yield 'text', raw
        index += 1


def property_rows(lines):
    rows = []
    for line in lines:
        match = re.match(r'^([^\s#][^:]*):[ \t]*(.*)$',line)
        if match:
            rows.append([match.group(1), match.group(2)])
        elif rows:
            rows[-1][1] += '\n' + line
        else:
            rows.append(['', line])
    return rows or [['', '']]


def display_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in text)


def wrap_cell(text, width):
    """Wrap without dropping whitespace/content; CJK cells count as two columns."""
    result = []
    for line in text.expandtabs(4).split('\n'):
        chunk, used = [], 0
        for char in line:
            size = display_width(char)
            if used+size > width and chunk:
                result.append(''.join(chunk)); chunk, used = [], 0
            chunk.append(char); used += size
        result.append(''.join(chunk))
    return result


def render_grid(rows, aligns=()):
    """Readable/selectable grid, wrapping wide cells without truncation.

    A bounded expansion guard falls back to complete tab-separated text for
    pathologically sparse/wide tables; it never silently drops rows or cells.
    """
    count = max(map(len, rows), default=0)
    if count*len(rows) > 500000:
        return ''.join('\t'.join(row)+'\n' for row in rows)
    rows = [row+['']*(count-len(row)) for row in rows]
    widths = [max(3,min(60,max(display_width(part) for row in rows for part in row[c].split('\n')))) for c in range(count)]
    wrapped = [[wrap_cell(value,widths[c]) for c,value in enumerate(row)] for row in rows]
    estimated = (sum(max(map(len,row),default=1) for row in wrapped)+len(rows)+1)*(sum(widths)+3*count+1)
    if estimated > 16*1024*1024:
        return ''.join('\t'.join(row)+'\n' for row in rows)
    output = []
    def border(left, middle, right):
        output.append(left+middle.join('─'*(width+2) for width in widths)+right+'\n')
    border('┌','┬','┐')
    for row_index,row in enumerate(wrapped):
        for line in range(max(map(len,row),default=1)):
            values=[]
            for col,cell in enumerate(row):
                value = cell[line] if line < len(cell) else ''
                padding = widths[col]-display_width(value)
                align = aligns[col] if col < len(aligns) else 'left'
                left = padding if align == 'right' else padding//2 if align == 'center' else 0
                values.append(' '+(' '*left)+value+(' '*(padding-left))+' ')
            output.append('│'+'│'.join(values)+'│\n')
        if row_index < len(wrapped)-1: border('├','┼','┤')
    border('└','┴','┘')
    return ''.join(output)

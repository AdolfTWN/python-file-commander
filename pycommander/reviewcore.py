"""Comparison data, independent of Tk. No automatic writes to source files."""
from array import array
from bisect import bisect_right, bisect_left
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path


REVIEW_LIMIT = 20 * 1024 * 1024


class LineIndex:
    """Compact line offsets; unlike splitlines(), a million rows aren't objects."""
    def __init__(self, text):
        self.text = text
        self.starts = array('I', [0])
        start = 0
        while True:
            start = text.find('\n', start)
            if start < 0: break
            start += 1
            self.starts.append(start)

    def __len__(self):
        return len(self.starts)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self[i] for i in range(*key.indices(len(self))) ]
        if key < 0: key += len(self)
        if not 0 <= key < len(self): raise IndexError(key)
        end = self.starts[key + 1] - 1 if key + 1 < len(self) else len(self.text)
        return self.text[self.starts[key]:end]

    def span(self, start, stop):
        a = self.starts[start] if start < len(self) else len(self.text)
        b = self.starts[stop] if stop < len(self) else len(self.text)
        return a, b


def review_opcodes(left, right):
    """Patience anchors plus bounded fine alignment; coarse changes stay honest.

    No positional fallback: an insertion never makes the remaining file differ.
    Oversized ambiguous spans are a replace block, not an equality assertion.
    """
    a, b = LineIndex(left), LineIndex(right)
    if left == right:
        return [('equal', 0, len(a), 0, len(b))]
    # Digest keys bound memory for wide lines. Equality is checked against source
    # text before anchors are used, rather than trusting hash equality alone.
    def keys(lines):
        return [hashlib.blake2b(lines.text[slice(*lines.span(i,i+1))].encode('utf-8'), digest_size=16).digest()
                for i in range(len(lines))]
    ka, kb = keys(a), keys(b)
    ca, cb = Counter(ka), Counter(kb)
    positions = {key: i for i, key in enumerate(kb) if cb[key] == 1}
    pairs = [(i, positions[key]) for i, key in enumerate(ka)
             if ca[key] == 1 and key in positions and a[i] == b[positions[key]]]
    tails, tail_indices, previous = [], [], []
    for index, (_, j) in enumerate(pairs):
        k = bisect_left(tails, j)
        previous.append(tail_indices[k-1] if k else -1)
        if k == len(tails): tails.append(j); tail_indices.append(index)
        else: tails[k] = j; tail_indices[k] = index
    anchors = []
    node = tail_indices[-1] if tail_indices else -1
    while node >= 0:
        anchors.append(pairs[node]); node = previous[node]
    anchors.reverse()
    result = []
    def emit(tag, i, x, j, y):
        if i == x and j == y: return
        if result and result[-1][0] == tag and result[-1][2] == i and result[-1][4] == j:
            old = result.pop(); result.append((tag, old[1], x, old[3], y))
        else: result.append((tag, i, x, j, y))
    def gap(i, x, j, y):
        while i < x and j < y and ka[i] == kb[j] and a[i] == b[j]:
            emit('equal', i, i+1, j, j+1); i += 1; j += 1
        end_x, end_y = x, y
        while i < x and j < y and ka[x-1] == kb[y-1] and a[x-1] == b[y-1]: x -= 1; y -= 1
        if i == x: emit('insert', i, x, j, y)
        elif j == y: emit('delete', i, x, j, y)
        elif (x-i)*(y-j) <= 1_000_000 and max(x-i, y-j) <= 4000:
            ta=[a.text[slice(*a.span(n,n+1))] for n in range(i,x)]
            tb=[b.text[slice(*b.span(n,n+1))] for n in range(j,y)]
            for tag, p, q, r, s in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
                emit(tag, i+p, i+q, j+r, j+s)
        else: emit('replace', i, x, j, y)
        emit('equal', x, end_x, y, end_y)
    i = j = 0
    for x, y in anchors:
        gap(i, x, j, y); emit('equal', x, x+1, y, y+1); i, j = x+1, y+1
    gap(i, len(a), j, len(b))
    return result


class ReviewAlignment:
    def __init__(self, left, right, opcodes):
        self.lines = (LineIndex(left), LineIndex(right))
        self.opcodes = opcodes
        self.starts = [0]
        self.differences = []
        for n, (tag, a, b, c, d) in enumerate(opcodes):
            if tag != 'equal': self.differences.append(n)
            self.starts.append(self.starts[-1] + max(b-a, d-c))

    def row(self, number):
        block = min(len(self.opcodes)-1, bisect_right(self.starts, number)-1)
        tag, a, b, c, d = self.opcodes[block]
        offset = number-self.starts[block]
        return block, (a+offset if a+offset < b else None), (c+offset if c+offset < d else None)

    def block_key(self, index):
        tag, a, b, c, d = self.opcodes[index]
        return hashlib.sha256(json.dumps([tag, a, b, c, d,
            self.lines[0].text[slice(*self.lines[0].span(a,b))],
            self.lines[1].text[slice(*self.lines[1].span(c,d))]], ensure_ascii=False).encode()).hexdigest()

    def take(self, index, source):
        tag, a, b, c, d = self.opcodes[index]
        spans = (self.lines[0].span(a,b), self.lines[1].span(c,d))
        target = 1-source; lo, hi = spans[target]
        chunk = self.lines[source].text[slice(*spans[source])]
        return self.lines[target].text[:lo] + chunk + self.lines[target].text[hi:]


def review_state(texts, checked):
    return {'format': 'pfc-review-1',
            'digests': [hashlib.sha256(t.encode()).hexdigest() for t in texts],
            'checked': sorted(checked)}


def restore_review_state(record, texts):
    expected = review_state(texts, ())
    if record.get('format') != expected['format'] or record.get('digests') != expected['digests']:
        raise ValueError('Review belongs to different document contents; no marks restored.')
    checked = record.get('checked')
    if not isinstance(checked, list) or len(checked) > 1_000_000 or any(
            not isinstance(k, str) or len(k) != 64 for k in checked):
        raise ValueError('Invalid review marks')
    return set(checked)

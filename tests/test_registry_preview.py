import unittest
from pathlib import Path
from pycommander.preview import (syntax_spans, looks_text, decode_text, CODE_EXTENSIONS,
                                REG_SYNTAX_TEXT_LIMIT, REG_SYNTAX_SPAN_LIMIT)


class RegistryPreviewTests(unittest.TestCase):
    def tokens(self,text):
        spans=syntax_spans(text,'.REG')
        self.assertTrue(all(0<=a<b<=len(text) for a,b,_ in spans))
        self.assertTrue(all(x[1]<=y[0] for x,y in zip(spans,spans[1:])))
        return [(text[a:b],tag) for a,b,tag in spans]

    def test_registry_headers_keys_defaults_types_deletions_and_continuations(self):
        text=('Windows Registry Editor Version 5.00\r\n\r\n'
              '[HKEY_CURRENT_USER\\Software\\Example]\r\n'
              '@="default"\r\n"Enabled"=dword:000000ff\r\n'
              '"Data"=hex(2):25,00,\\\r\n  50,00\r\n'
              '"Obsolete"=-\r\n[-HKEY_CURRENT_USER\\Software\\Old]\r\n;comment\r\n')
        tokens=self.tokens(text)
        for item in (('Windows Registry Editor Version 5.00\r','syntax_heading'),
                     ('@','syntax_keyword'),('"default"','syntax_string'),
                     ('"Enabled"','syntax_keyword'),('dword:','syntax_keyword'),
                     ('000000ff','syntax_number'),('hex(2):','syntax_keyword'),
                     ('\\','syntax_operator'),('-','syntax_deletion'),
                     ('[-HKEY_CURRENT_USER\\Software\\Old]','syntax_deletion'),
                     (';comment','syntax_comment')):
            self.assertIn(item,tokens)
        self.assertIn(('REGEDIT4','syntax_heading'),self.tokens('REGEDIT4\n'))

    def test_quoted_semicolon_hash_url_and_escaped_quotes_are_not_comments(self):
        text=r'"Path"="C:\\a;#b\\file\"name\".txt"'+ '\n' + r'"URL"="https://example.test/#x;y"'+'\n'
        tokens=self.tokens(text)
        self.assertFalse(any(tag=='syntax_comment' for _,tag in tokens))
        self.assertEqual(sum(tag=='syntax_string' for _,tag in tokens),2)
        self.assertIn(('[HKEY_CURRENT_USER\\Key;name]','syntax_heading'),
                      self.tokens('[HKEY_CURRENT_USER\\Key;name]\n'))

    def test_encodings_and_case_insensitive_extension(self):
        text='Windows Registry Editor Version 5.00\n"中文"="測試😀"\n'
        for codec in ('utf-8-sig','utf-16','utf-16-be','utf-32'):
            data=text.encode(codec)
            if codec=='utf-16-be':data=b'\xfe\xff'+data
            decoded,_=decode_text(data)
            self.assertEqual(decoded,text)
            self.assertTrue(looks_text(Path('sample.REG'),data))
            self.assertTrue(self.tokens(decoded))
        self.assertEqual(CODE_EXTENSIONS['.reg'],'Registry')
        self.assertEqual(decode_text('REGEDIT4\n"é"="café"'.encode('cp1252'))[0],
                         'REGEDIT4\n"é"="café"')

    def test_malformed_and_large_inputs_are_bounded_without_rewriting_text(self):
        for text in ('', 'not registry data', '"unterminated; string', '['*20000):
            self.tokens(text)
        source='"v"=hex:'+('ff,'*300000)+'\n"Late"="NEEDLE"\n'
        before=source
        spans=syntax_spans(source,'.reg')
        self.assertLessEqual(len(spans),REG_SYNTAX_SPAN_LIMIT)
        self.assertTrue(all(b<=REG_SYNTAX_TEXT_LIMIT for a,b,_ in spans))
        self.assertEqual(source,before)


if __name__=='__main__':unittest.main()

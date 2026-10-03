import codecs
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile

from pycommander.reviewcore import ReviewAlignment, review_opcodes, review_state, restore_review_state
from pycommander.textio import read_text_document
from pycommander.workbook import read_workbook, workbook_rows, shared_formula, cell_values_equal, excel_date
from pycommander.archivereview import ArchiveReviewSession, archive_manifest, checked_archive_members
from pycommander.reviewstorage import safe_review_write
from pycommander.comparecolors import comparison_colors


class ReviewTests(unittest.TestCase):
    def reconcile(self, left, right):
        for source in (0,1):
            a,b=left,right
            for _ in range(100):
                alignment=ReviewAlignment(a,b,review_opcodes(a,b))
                if not alignment.differences:break
                updated=alignment.take(alignment.differences[0],source)
                if source==0:self.assertNotEqual(b,updated);b=updated
                else:self.assertNotEqual(a,updated);a=updated
            self.assertEqual(a,b)

    def test_all_newline_and_empty_boundaries(self):
        samples=['','a','a\n','a\nb','a\nb\n','\n','\n\n','b\n\na']
        for a in samples:
            for b in samples:
                with self.subTest(a=a,b=b):self.reconcile(a,b)

    def test_random_content_reconciliation(self):
        rng=random.Random(713)
        for _ in range(100):
            self.reconcile(''.join(rng.choice(['a\n','b\n','c\n','\n']) for _ in range(12)),
                           ''.join(rng.choice(['a\n','b\n','c\n','\n']) for _ in range(12)))

    def test_late_difference_and_wide_line(self):
        a=''.join(f'{n}\n' for n in range(30000));b=a.replace('29000\n','changed\n')
        ops=review_opcodes(a,b)
        self.assertEqual([op[1] for op in ops if op[0]!='equal'],[29000])
        self.reconcile('a'*1000000+'left','a'*1000000+'right')

    def test_review_marks_only_restore_exact_content(self):
        record=review_state(['a','b'],{'f'*64})
        self.assertEqual(restore_review_state(record,['a','b']),{'f'*64})
        with self.assertRaises(ValueError):restore_review_state(record,['a','B'])

    def test_large_edit_opt_in_preserves_encoding_and_detects_external_change(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'wide.md';data='a'*2200000+'\r\n'
            path.write_bytes(codecs.BOM_UTF8+data.encode())
            with self.assertRaises(OSError):read_text_document(path)
            doc=read_text_document(path,limit=20*1024*1024);doc.save(doc.text+'end\n')
            self.assertEqual(path.read_bytes(),codecs.BOM_UTF8+(data+'end\r\n').encode())
            path.write_text('external')
            with self.assertRaises(OSError):doc.save('overwrite')
            self.assertEqual(path.read_text(),'external')

    def test_exports_cannot_replace_source_or_link(self):
        with tempfile.TemporaryDirectory() as raw:
            source=Path(raw)/'original';source.write_text('safe')
            with self.assertRaises(OSError):safe_review_write(source,b'bad',[source])
            link=Path(raw)/'alias';os.link(source,link)
            with self.assertRaises(OSError):safe_review_write(link,b'bad',[source])
            self.assertEqual(source.read_text(),'safe')


class ArchiveReviewTests(unittest.TestCase):
    def test_zip_draft_review_backup_and_verified_save(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'left.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('folder/a.md','old');z.writestr('delete.txt','delete')
            original=path.read_bytes();s=ArchiveReviewSession(path)
            try:
                (s.root/'folder/a.md').write_text('new')
                (s.root/'delete.txt').unlink();(s.root/'add.txt').write_text('added')
                changes=dict(s.changes());self.assertEqual(changes['folder/a.md'],'Replace')
                self.assertEqual(changes['delete.txt'],'Delete');self.assertEqual(changes['add.txt'],'Add')
                approved=archive_manifest(s.root);backup=s.commit(approved)
                self.assertEqual(backup.read_bytes(),original)
                with zipfile.ZipFile(path) as z:
                    self.assertEqual(z.read('folder/a.md'),b'new');self.assertNotIn('delete.txt',z.namelist())
                self.assertEqual(s.changes(),[])
            finally:s.cleanup()

    def test_archive_conflicts_and_cancel_never_overwrite(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'left.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('a.txt','old')
            original=path.read_bytes();s=ArchiveReviewSession(path)
            try:
                approved=archive_manifest(s.root);(s.root/'a.txt').write_text('new')
                with self.assertRaises(OSError):s.commit(approved)
                self.assertEqual(path.read_bytes(),original)
                s.cancel.set()
                with self.assertRaises(OSError):s.commit()
                s.cancel.clear();path.write_bytes(original+b'external')
                with self.assertRaises(OSError):s.commit()
                self.assertEqual(path.read_bytes(),original+b'external')
            finally:s.cleanup()

    def test_draft_delete_is_recoverable_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'left.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('folder/a.txt','kept in original')
            before=path.read_bytes();s=ArchiveReviewSession(path)
            try:
                s.delete_from_draft(['folder']);self.assertFalse((s.root/'folder').exists())
                s.undo_delete();self.assertEqual((s.root/'folder/a.txt').read_text(),'kept in original')
                self.assertEqual(path.read_bytes(),before)
                with self.assertRaises(OSError):s.delete_from_draft(['../outside'])
            finally:s.cleanup()

    def test_unsafe_archives_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'unsafe.zip'
            for names in [('a.txt','A.txt'),('../escape',),('CON.txt',),('a:b',),('a','a/b')]:
                with zipfile.ZipFile(path,'w') as z:
                    for name in names:z.writestr(name,'x')
                with self.subTest(names=names),self.assertRaises(OSError):checked_archive_members(path)

    @unittest.skipUnless(shutil.which('7z') or shutil.which('7zz'),'7-Zip unavailable')
    def test_seven_zip_verified_save(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'a.txt').write_text('old');path=root/'test.7z'
            subprocess.run([shutil.which('7z') or shutil.which('7zz'),'a',str(path),'a.txt'],cwd=root,check=True,stdout=subprocess.DEVNULL)
            s=ArchiveReviewSession(path)
            try:
                (s.root/'a.txt').write_text('new');s.commit(archive_manifest(s.root))
                check=ArchiveReviewSession(path)
                try:self.assertEqual((check.root/'a.txt').read_text(),'new')
                finally:check.cleanup()
            finally:s.cleanup()

    @unittest.skipUnless(shutil.which('7z') or shutil.which('7zz'),'7-Zip unavailable')
    def test_seven_zip_explicit_directories_not_file_collisions(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'nested').mkdir();(root/'nested/a.md').write_text('before')
            path=root/'nested.7z'
            subprocess.run([shutil.which('7z') or shutil.which('7zz'),'a',str(path),'nested'],cwd=root,check=True,stdout=subprocess.DEVNULL)
            records,_=checked_archive_members(path)
            self.assertTrue(next(isdir for name,_,isdir in records if name=='nested'))
            session=ArchiveReviewSession(path)
            try:
                (session.root/'nested/a.md').write_text('after');session.commit(archive_manifest(session.root))
                check=ArchiveReviewSession(path)
                try:self.assertEqual((check.root/'nested/a.md').read_text(),'after')
                finally:check.cleanup()
            finally:session.cleanup()


class WorkbookTests(unittest.TestCase):
    def test_strict_workbook_strings_merged_cells_and_formula(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'strict.xlsx'
            main='http://purl.oclc.org/ooxml/spreadsheetml/main'
            rel='http://purl.oclc.org/ooxml/officeDocument/relationships'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('xl/workbook.xml',f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="Data" r:id="one"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="one" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/sharedStrings.xml',f'<sst xmlns="{main}"><si><r><t>Monitor </t></r><r><t>list</t></r></si></sst>')
                z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{main}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>資料</t></is></c><c r="C1"><f>1+2</f><v>3</v></c></row></sheetData><mergeCells><mergeCell ref="A2:C2"/></mergeCells></worksheet>')
            sheet=read_workbook(path)['sheets'][0]
            self.assertEqual(sheet['cells']['A1'],('s','Monitor list',''))
            self.assertEqual(sheet['cells']['B1'],('inlineStr','資料',''))
            self.assertEqual(sheet['cells']['C1'],('n','3','1+2'))
            self.assertEqual(sheet['merged'],['A2:C2'])

    def test_unknown_namespace_is_error_not_empty_success(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'bad.xlsx'
            with zipfile.ZipFile(path,'w') as z:z.writestr('xl/workbook.xml','<workbook xmlns="urn:unknown"/>')
            with self.assertRaisesRegex(ValueError,'Unsupported workbook'):read_workbook(path)

    def test_comparison_highlights_have_readable_contrast(self):
        def luminance(color):
            rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            rgb=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))
        for content in ('#ffffff','#dedede','#202124','#20262c'):
            colors=comparison_colors({'content':content})
            for bg,fg in [(k,'text') for k in ('base','line','inline','orphan','gap')]+[('match','match_text'),('current','current_text')]:
                a,b=sorted((luminance(colors[bg]),luminance(colors[fg])))
                self.assertGreaterEqual((b+.05)/(a+.05),4.5,(content,bg))

    def test_numeric_representation_and_date_epochs(self):
        self.assertTrue(cell_values_equal(('n','1',''),('n','1.00','')))
        self.assertFalse(cell_values_equal(('text','1',''),('n','1','')))
        self.assertEqual(excel_date('1462',False),excel_date('0',True))
        self.assertTrue(excel_date('60',False).startswith('1900-02-29'))

    def test_shared_formulas_and_unique_keys(self):
        self.assertEqual(shared_formula('A1+$B$1+"A1"','C1','C2'),'A2+$B$1+"A1"')
        self.assertEqual(shared_formula('Table[A1]+B1','C1','C2'),'Table[A1]+B2')
        a={'cells':{'A2':('s','one',''),'B2':('n','1',''),'A3':('s','two','')}}
        b={'cells':{'A2':('s','two',''),'A3':('s','one',''),'B3':('n','1','')}}
        rows=workbook_rows(a,b,(1,))
        self.assertIn(('B2','B3',('n','1',''),('n','1','')),rows)
        b['cells']['A3']=('s','two','')
        with self.assertRaises(ValueError):workbook_rows(a,b,(1,))

    def test_xlsm_readonly_multisheet_formula_cached_missing(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'book.xlsm'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('xl/workbook.xml','''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr date1904="1"/><sheets><sheet name="Data" sheetId="1" r:id="rId1"/><sheet name="Hidden" state="hidden" sheetId="2" r:id="rId2"/></sheets></workbook>''')
                z.writestr('xl/_rels/workbook.xml.rels','''<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>''')
                z.writestr('xl/worksheets/sheet1.xml','''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><f t="shared" si="0">B1+1</f></c></row><row r="2"><c r="A2"><f t="shared" si="0"/><v>3</v></c></row></sheetData><mergeCells><mergeCell ref="C1:D2"/></mergeCells></worksheet>''')
                z.writestr('xl/worksheets/sheet2.xml','''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>''')
                z.writestr('xl/vbaProject.bin',b'not executable')
            before=path.read_bytes();book=read_workbook(path)
            self.assertTrue(book['date1904']);self.assertEqual(book['sheets'][1]['state'],'hidden')
            self.assertEqual(book['sheets'][0]['cells']['A1'],('n',None,'B1+1'))
            self.assertEqual(book['sheets'][0]['cells']['A2'],('n','3','B2+1'))
            self.assertEqual(before,path.read_bytes())


if __name__=='__main__':unittest.main()

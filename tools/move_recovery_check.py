import shutil
import importlib
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ops=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.fileops')
if 'pfc' in sys.argv:sys.argv.remove('pfc')


class MoveRecoveryTests(unittest.TestCase):
    def test_failed_cross_volume_directory_move_keeps_last_copy_of_deleted_source_children(self):
        with tempfile.TemporaryDirectory(prefix='pfc-move-recovery-') as raw:
            root=Path(raw);source=root/'src'/'project';target_dir=root/'dst'
            source.mkdir(parents=True);target_dir.mkdir()
            (source/'a.txt').write_bytes(b'UNIQUE A');(source/'b.txt').write_bytes(b'UNIQUE B')
            target=target_dir/'project';target.mkdir();(target/'old.txt').write_bytes(b'OLD TARGET')
            def interrupted_move(src,dst,move):
                self.assertTrue(move)
                shutil.copytree(src,dst)
                # shutil.move across filesystems copies the tree then removes
                # the source tree; rmtree can fail AFTER deleting some children.
                (src/'a.txt').unlink()
                raise PermissionError('Simulated source cleanup failure')
            with patch.object(ops,'_copy_or_move',side_effect=interrupted_move):
                result=ops.move_items([source],target_dir,lambda *_:'replace')
            self.assertEqual(len(result.failures),1)
            self.assertEqual((target/'old.txt').read_bytes(),b'OLD TARGET')
            survivors=[p for p in root.rglob('a.txt') if p.read_bytes()==b'UNIQUE A']
            self.assertTrue(survivors,'Rollback deleted the only remaining copy of source a.txt')
            self.assertIn(str(survivors[0].parent),result.failures[0].message)
            self.assertEqual((source/'b.txt').read_bytes(),b'UNIQUE B')

    def test_failed_copy_restores_old_destination_without_retaining_duplicate(self):
        with tempfile.TemporaryDirectory(prefix='pfc-copy-rollback-') as raw:
            root=Path(raw);source=root/'source';dest=root/'dest';source.mkdir();dest.mkdir()
            item=source/'a.txt';item.write_bytes(b'SOURCE');(dest/item.name).write_bytes(b'OLD')
            def interrupted_copy(src,target,move):
                self.assertFalse(move);target.write_bytes(b'PARTIAL');raise OSError('Copy failed')
            with patch.object(ops,'_copy_or_move',side_effect=interrupted_copy):
                result=ops.copy_items([item],dest,lambda *_:'replace')
            self.assertEqual(len(result.failures),1)
            self.assertEqual(item.read_bytes(),b'SOURCE')
            self.assertEqual((dest/item.name).read_bytes(),b'OLD')
            self.assertEqual(list(dest.iterdir()),[dest/item.name])

    def test_failed_recovery_rename_keeps_both_target_and_backup(self):
        with tempfile.TemporaryDirectory(prefix='pfc-move-rollback-') as raw:
            root=Path(raw);source=root/'source';dest=root/'dest';source.mkdir();dest.mkdir()
            item=source/'a.txt';item.write_bytes(b'SOURCE');target=dest/item.name;target.write_bytes(b'OLD')
            original=Path.rename
            def rename(path,to):
                if path==target and target.read_bytes()==b'NEW COPY':raise PermissionError('Recovery rename denied')
                return original(path,to)
            def interrupted_move(src,to,move):
                to.write_bytes(b'NEW COPY');src.unlink();raise OSError('Move failed')
            with patch.object(ops,'_copy_or_move',side_effect=interrupted_move),patch.object(Path,'rename',rename):
                result=ops.move_items([item],dest,lambda *_:'replace')
            self.assertEqual(target.read_bytes(),b'NEW COPY')
            self.assertEqual((dest/'.a.txt.pfc-backup').read_bytes(),b'OLD')
            self.assertIn('rollback incomplete',result.failures[0].message)


if __name__=='__main__':unittest.main()

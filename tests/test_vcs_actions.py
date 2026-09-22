import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pycommander.vcsactions import (VcsContext, VcsLocation, vcs_context, vcs_location,
    vcs_status, vcs_parse_git_status, vcs_dialog_command, vcs_find_client)


class VcsActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo space ü'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'one.txt').write_text('base')
        (self.root / 'two.txt').write_text('base')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True).stdout

    def test_scope_and_untracked_and_missing_upstream(self):
        (self.root / 'one.txt').write_text('change')
        (self.root / 'new.txt').write_text('new')
        selected = vcs_context([self.root / 'one.txt'], self.root / 'one.txt')
        summary = vcs_status(selected)
        self.assertEqual((summary.changed, summary.untracked, summary.branch), (1, 0, 'main'))
        self.assertIsNone(summary.ahead)
        self.assertEqual(vcs_status(vcs_context([], self.root)).untracked, 1)
        self.assertEqual(vcs_status(vcs_context([], self.root / 'two.txt')).changed, 0)

    def test_detached_worktree_nested_and_metadata(self):
        worktree = Path(self.tmp.name) / 'worktree'
        self.git('worktree', 'add', '-qb', 'feature', str(worktree))
        self.assertEqual(vcs_location(worktree / 'one.txt').root, worktree)
        self.assertEqual(vcs_status(vcs_context([], worktree)).branch, 'feature')
        nested = self.root / 'nested'; nested.mkdir()
        subprocess.run(['git', 'init', '-q', str(nested)], check=True)
        self.assertEqual(vcs_location(nested).root, nested)
        self.assertIsNone(vcs_location(self.root / '.git' / 'config'))
        self.assertIsNone(vcs_context([], self.root, virtual=True).location)
        self.git('checkout', '--detach', '-q')
        self.assertEqual(vcs_status(vcs_context([], self.root)).branch, '(detached)')

    def test_mixed_roots_and_dialog_commands(self):
        other = Path(self.tmp.name) / 'other'; other.mkdir(); (other / '.svn').mkdir()
        focus = self.root / 'one.txt'
        context = vcs_context([focus, other], focus)
        self.assertTrue(context.mixed)
        for action in ('commit', 'commit_all', 'push'):
            with self.assertRaises(ValueError): vcs_dialog_command('gui.exe', context, action)
        self.assertIn('/path:' + str(focus), vcs_dialog_command('gui.exe', context, 'log'))
        context = vcs_context([focus, self.root / 'two.txt'], focus)
        command = vcs_dialog_command('TortoiseGitProc.exe', context, 'commit')
        self.assertEqual(command, ['TortoiseGitProc.exe', '/command:commit',
                                  '/path:' + str(focus) + '*' + str(self.root / 'two.txt')])
        for action in ('push', 'commit_all', 'revisiongraph'):
            self.assertEqual(vcs_dialog_command('gui.exe', context, action)[-1], '/path:' + str(self.root))

    def test_parser_conflict_rename_and_upstream(self):
        summary = vcs_parse_git_status(b'# branch.head main\0# branch.upstream origin/main\0'
            b'# branch.ab +2 -3\0u UU conflict\0? untracked\0'
            b'2 R. renamed path\0? source is not an untracked record\0'
            b'1 .M modified\0')
        self.assertEqual((summary.changed, summary.untracked, summary.conflicts), (2, 1, 1))
        self.assertEqual((summary.ahead, summary.behind, summary.upstream), (2, 3, 'origin/main'))

    def test_real_local_upstream_no_network(self):
        remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-qu', 'origin', 'main')
        (self.root / 'one.txt').write_text('ahead')
        self.git('commit', '-qam', 'ahead')
        summary = vcs_status(vcs_context([], self.root / 'two.txt'))
        self.assertEqual((summary.changed, summary.ahead, summary.behind), (0, 1, 0))

    def test_literal_pathspec_and_no_writes(self):
        filename = '[one].txt'
        (self.root / filename).write_text('special')
        before = (self.root / '.git' / 'index').read_bytes()
        command_run = subprocess.run
        with patch('pycommander.vcsactions.subprocess.run', wraps=command_run) as run:
            summary = vcs_status(vcs_context([], self.root / filename))
        self.assertEqual(summary.untracked, 1)
        self.assertEqual((self.root / '.git' / 'index').read_bytes(), before)
        for call in run.call_args_list:
            self.assertIn('--literal-pathspecs', call.args[0])
            self.assertEqual(call.kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
            self.assertFalse(call.kwargs.get('shell', False))
            self.assertEqual(call.kwargs['timeout'], 4)

    def test_cli_missing_error_and_timeout_are_unknown(self):
        context = vcs_context([], self.root)
        with patch('pycommander.vcsactions.vcs_cli', return_value=None):
            result = vcs_status(context)
        self.assertTrue(result.error); self.assertIsNone(result.ahead)
        with patch('pycommander.vcsactions.vcs_run', side_effect=subprocess.TimeoutExpired('git', 4)):
            result = vcs_status(context)
        self.assertTrue(result.error); self.assertIsNone(result.ahead)

    def test_svn_local_status_properties_and_network_free_commands(self):
        root = Path(self.tmp.name) / 'svn'; root.mkdir(); (root / '.svn').mkdir()
        context = vcs_context([], root)
        outputs = [b'<status><target><entry path="a"><wc-status item="normal" props="modified"/></entry>'
                   b'<entry path="b"><wc-status item="unversioned"/></entry>'
                   b'<entry path="c"><wc-status item="normal" tree-conflicted="true"/></entry></target></status>',
                   b'<info><entry><relative-url>^/branches/demo</relative-url></entry></info>']
        with patch('pycommander.vcsactions.vcs_cli', return_value='svn'), \
                patch('pycommander.vcsactions.vcs_run', side_effect=outputs) as run:
            summary = vcs_status(context)
        self.assertEqual((summary.changed, summary.untracked, summary.conflicts), (1, 1, 1))
        self.assertEqual(summary.url, '^/branches/demo')
        self.assertNotIn('-u', run.call_args_list[0].args[0])
        self.assertIn('--ignore-externals', run.call_args_list[0].args[0])
        with self.assertRaises(ValueError): vcs_dialog_command('gui.exe', context, 'push')
        self.assertIn('/command:revisiongraph', vcs_dialog_command('gui.exe', context, 'revisiongraph'))

    def test_explicit_client_and_invalid_commands(self):
        client = Path(self.tmp.name) / 'TortoiseGitProc.exe'; client.write_bytes(b'test')
        self.assertEqual(vcs_find_client('git', str(client)), str(client))
        self.assertIsNone(vcs_find_client('git', 'relative/TortoiseGitProc.exe'))
        with self.assertRaises(ValueError):
            vcs_dialog_command('gui.exe', vcs_context([], self.root), 'fetch')


if __name__ == '__main__':
    unittest.main()

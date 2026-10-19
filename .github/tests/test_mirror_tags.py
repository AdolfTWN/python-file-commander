"""Exercise the exact workflow retag block against disposable local Git repos."""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


class MirrorTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Fixture', GIT_COMMITTER_NAME='Fixture',
                        GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '--bare', 'target.git')
        self.git('init', 'mirror.git')
        self.git('-C', 'mirror.git', 'commit', '--allow-empty', '-m', 'original')
        self.old = self.git('-C', 'mirror.git', 'rev-parse', 'HEAD')
        self.git('-C', 'mirror.git', 'tag', 'v0.18.33')
        self.git('-C', 'mirror.git', 'push', str(self.root/'target.git'), 'refs/tags/v0.18.33')
        self.git('-C', 'mirror.git', 'commit', '--allow-empty', '-m', 'replacement')
        self.new = self.git('-C', 'mirror.git', 'rev-parse', 'HEAD')
        self.git('-C', 'mirror.git', 'tag', '-f', 'v0.18.33')
        workflow = (Path(__file__).resolve().parents[1]/'workflows/gitlab-mirror.yml').read_text()
        self.script = textwrap.dedent(workflow.split('          # BEGIN leased tag replacement:')[1]
                                     .split('          # END leased tag replacement.')[0].split('\n', 1)[1])

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, env=self.env, stderr=subprocess.DEVNULL).decode().strip()

    def run_block(self, ref='refs/tags/v0.18.33', before=None, event='push', requested_tag='v0.18.33', requested_old=None):
        env = dict(self.env, EVENT_FORCED='false', GITHUB_REF=ref, EVENT_BEFORE=before or self.old,
                   GITHUB_EVENT_NAME=event, REQUESTED_TAG=requested_tag, REQUESTED_OLD_SHA=requested_old or self.old,
                   TEST_TARGET=str(self.root/'target.git'))
        return subprocess.run(['bash', '-eu', '-c', 'target="$TEST_TARGET"\n'+self.script],
                              cwd=self.root, env=env, capture_output=True).returncode

    def remote_tag(self):
        return self.git('--git-dir=target.git', 'rev-parse', 'refs/tags/v0.18.33')

    def test_exact_tag_update_replaces_old_revision_even_when_forced_flag_is_false(self):
        self.assertEqual(self.run_block(), 0)
        self.assertEqual(self.remote_tag(), self.new)
        self.assertEqual(self.run_block(), 0)  # Idempotent delivery of same event.

    def test_stale_lease_does_not_overwrite_another_revision(self):
        self.assertNotEqual(self.run_block(before='a'*40), 0)
        self.assertEqual(self.remote_tag(), self.old)

    def test_created_tag_and_branch_events_never_force_retag(self):
        self.assertEqual(self.run_block(before='0'*40), 0)
        self.assertEqual(self.run_block(ref='refs/heads/main'), 0)
        self.assertEqual(self.remote_tag(), self.old)

    def test_invalid_expected_sha_fails_closed(self):
        self.assertNotEqual(self.run_block(before='not-a-sha'), 0)
        self.assertEqual(self.remote_tag(), self.old)

    def test_manual_recovery_uses_exact_remote_old_sha_after_missed_event(self):
        self.assertNotEqual(self.run_block(before=self.new), 0)
        self.assertEqual(self.remote_tag(), self.old)
        self.assertEqual(self.run_block(ref='refs/heads/main', event='workflow_dispatch'), 0)
        self.assertEqual(self.remote_tag(), self.new)

    def test_manual_recovery_rejects_wrong_lease_and_invalid_tag(self):
        self.assertNotEqual(self.run_block(event='workflow_dispatch', requested_old='a'*40), 0)
        self.assertNotEqual(self.run_block(event='workflow_dispatch', requested_tag='../main'), 0)
        self.assertEqual(self.remote_tag(), self.old)


if __name__ == '__main__':
    unittest.main()

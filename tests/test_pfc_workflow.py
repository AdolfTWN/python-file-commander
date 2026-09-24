import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

TOOLS = Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0, str(TOOLS))
import pfc_workflow as workflow
import pfc_vm_runner as vm
import pfc_windows_worker as worker


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = workflow.Store(self.temp.name)

    def complete(self, seconds=10, kind='bugfix', scope='same', status='passed'):
        run = self.store.start(kind)
        self.store.stage(run['id'], 'test', status, seconds, scope=scope)
        run.update(started=run['started']-seconds, ended=run['started'], status=status)
        self.store.save(run)
        return run

    def test_unknown_tokens_and_empty_run_not_passed(self):
        run = self.store.start('bugfix')
        self.assertIsNone(self.store.report(run['id'])['usage'])
        with self.assertRaises(ValueError): self.store.finish(run['id'], 'passed')

    def test_phase_transitions_and_bootstrap_compatibility(self):
        run = self.store.start('maintenance')
        for key in ('phases', 'active_phase', 'phase_started'):
            del run[key]
        self.store.save(run)
        self.store.mark(run['id'], 'validation')
        self.store.stage(run['id'], 'test', 'passed', 1)
        result = self.store.finish(run['id'], 'passed')
        self.assertEqual([p['phase'] for p in result['phases']], ['unclassified', 'validation'])
        self.assertTrue(all(p['seconds'] >= 0 for p in result['phases']))
        with self.assertRaises(ValueError): self.store.finish(run['id'], 'passed')
        with self.assertRaises(ValueError): self.store.mark(run['id'], 'release')

    def test_only_matching_success_compares(self):
        self.complete(seconds=50, status='blocked')
        self.complete(seconds=30, scope='different')
        self.complete(seconds=20)
        current = self.complete(seconds=10)
        report = self.store.report(current['id'])
        self.assertEqual(report['comparison']['samples'], 1)
        self.assertEqual(report['comparison']['elapsed_change_percent'], -50)
        self.assertEqual(report['comparison']['tokens'], 'unknown or incomparable')

    def test_environment_mismatch_excluded(self):
        prior = self.complete()
        prior['environment']['host'] = 'different'
        self.store.save(prior)
        result = self.store.report(self.complete()['id'])
        self.assertEqual(result['comparison']['status'], 'no comparable baseline')

    def test_retry_recovered_but_unresolved_block_prevents_pass(self):
        run = self.store.start('bugfix')
        self.store.stage(run['id'], 'test', 'failed', 1)
        self.store.stage(run['id'], 'test', 'passed', 1)
        self.assertEqual(self.store.finish(run['id'], 'passed')['retries'], 1)
        run = self.store.start('bugfix')
        self.store.stage(run['id'], 'windows', 'blocked', 1)
        with self.assertRaises(ValueError): self.store.finish(run['id'], 'passed')

    def test_stage_compare_even_when_vm_blocks(self):
        prior = self.complete(seconds=20)
        current = self.store.start('bugfix')
        self.store.stage(current['id'], 'test', 'passed', 10, scope='same')
        self.store.stage(current['id'], 'windows', 'blocked', 1)
        result = self.store.finish(current['id'], 'blocked')
        self.assertEqual(result['stage_comparisons'][0]['change_percent'], -50)
        self.assertEqual(result['comparison']['status'], 'no comparable baseline')

    def test_official_usage_only_and_subset_not_double_counted(self):
        events = [json.dumps({'type':'turn.completed','usage':{
            'input_tokens':100,'cached_input_tokens':80,'output_tokens':10}}),
            json.dumps({'type':'event_msg','payload':{'info':{'total_token_usage':999}}}), 'bad']
        result = workflow.parse_usage(events)
        self.assertEqual(result['input_tokens'], 100)
        self.assertEqual(result['cached_input_tokens'], 80)
        self.assertEqual(result['output_tokens'], 10)
        self.assertIsNone(result['reasoning_output_tokens'])
        self.assertIsNone(workflow.parse_usage(['{}']))
        with self.assertRaises(ValueError):
            workflow.parse_usage([json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'cached_input_tokens':5,'output_tokens':0}})])

    def test_usage_requires_full_same_model_effort(self):
        old = self.complete()
        old.update(model='fixture', effort='fixture', coverage='full', usage={'input_tokens':100, 'output_tokens':50})
        self.store.save(old)
        new = self.complete()
        new.update(model='fixture', effort='fixture', coverage='partial', usage={'input_tokens':50, 'output_tokens':25})
        self.store.save(new)
        self.assertIsInstance(self.store.report(new['id'])['comparison']['tokens'], str)
        new['coverage'] = 'full'; self.store.save(new)
        self.assertEqual(self.store.report(new['id'])['comparison']['tokens']['output_tokens']['change_percent'], -50)

    def test_command_output_is_private_and_timeout_is_failure(self):
        run = self.store.start('validation')
        result = workflow.run_command(self.store, run['id'], 'fixture',
                                      [sys.executable, '-c', 'print("private-fixture")'])
        self.assertEqual(result['status'], 'passed')
        self.assertNotIn('private-fixture', json.dumps(result))
        result = workflow.run_command(self.store, run['id'], 'timeout',
                                      [sys.executable, '-c', 'import time; time.sleep(10)'], timeout=.05)
        self.assertEqual(result['status'], 'timeout')

    def test_profiles_include_source_portable_and_no_shell(self):
        selected = workflow.checks('tooltip')
        self.assertIn('tooltip-source', [label for label, _ in selected])
        self.assertIn('tooltip-portable', [label for label, _ in selected])
        self.assertEqual(selected[1][1][2], sys.executable)
        self.assertGreater(len(workflow.checks('full')), len(selected))

    def test_release_gate_requires_mirror_proof(self):
        import re
        from pycommander import app
        version = re.search(r'__version__ = "([0-9.]+)"', (workflow.ROOT/'pycommander/__init__.py').read_text())[1]
        portable = (workflow.ROOT/'pfc.py').read_bytes()
        for proof, expected in [('missing proof', 'blocked'),
                                ('Verified: GitHub and GitLab branch/tag references match.', 'passed')]:
            run = self.store.start('release')
            responses = [b'', b'fixture-head',
                         ('fixture-head\trefs/heads/main\nfixture-head\trefs/tags/v'+version).encode(),
                         b'[{"databaseId":1,"status":"completed","conclusion":"success"}]', proof.encode()]
            with patch.object(workflow.subprocess, 'check_output', side_effect=responses), \
                    patch.object(app, 'fetch_pfc_update', return_value=(version, portable)):
                self.assertEqual(workflow.release_check(self.store, run['id'])['status'], expected)

    def test_live_usage_is_partial_and_not_accumulated_twice(self):
        events = Path(self.temp.name)/'events.jsonl'
        events.write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':8,'output_tokens':2}})+'\n')
        run = self.store.start('maintenance')
        run['events_path'] = str(events)
        self.store.save(run)
        first = self.store.report(run['id'])
        second = self.store.report(run['id'])
        self.assertEqual(first['usage'], second['usage'])
        self.assertEqual(second['usage_coverage'], 'partial')

    def test_changing_source_during_suite_fails(self):
        run = self.store.start('maintenance')
        with patch.object(workflow, 'source_fingerprint', side_effect=['before','after']), \
                patch.object(workflow, 'run_command', return_value={'status':'passed'}):
            result = workflow.run_tests(self.store, run['id'], 'workflow', 1, 5)
        self.assertEqual(result['status'], 'failed')


class VmRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = workflow.Store(self.temp.name)
        self.run = self.store.start('validation')['id']
        self.leases = MagicMock()
        self.leases.request_lease.return_value = {'result':'granted', 'lease':{'lease_id':'fixture','vm_id':'vm2'}}
        self.leases.release.return_value = {'result':'released'}
        self.leases.wait_for_lease.return_value = {'result':'waiting'}
        self.leases.cancel.return_value = {'result':'cancelled'}
        self.specs = MagicMock(); self.specs.VM_SPECS = {'vm2':MagicMock(vm_id='vm2')}
        self.modules = patch.object(vm.importlib, 'import_module', side_effect=lambda name: self.leases if name == 'vm_lease' else self.specs)
        self.modules.start(); self.addCleanup(self.modules.stop)

    def test_qga_failure_blocks_before_deploy_and_releases(self):
        with patch.object(vm, 'Guest') as guest, patch.object(vm.subprocess, 'run') as command:
            guest.return_value.execute.side_effect = vm.Blocked('guest-exec-unavailable')
            command.return_value.returncode = 0
            result = vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['reason'], 'guest-exec-unavailable')
            guest.return_value.put.assert_not_called()
            self.leases.release.assert_called_once_with('fixture')
            self.assertEqual(guest.call_args.args[1].vm_id, 'vm2')

    def test_queue_never_touches_guest(self):
        self.leases.request_lease.return_value = {'result':'waiting','request':{'request_id':'queued'}}
        with patch.object(vm, 'Guest') as guest:
            result = vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            guest.assert_not_called()
            self.leases.cancel.assert_called_once_with('queued')
            self.leases.wait_for_lease.assert_called_once_with('queued', 45)
            self.leases.release.assert_not_called()
            self.assertEqual(result['reason'], 'vm-pool-busy')

    def test_queue_promotion_racing_cancel_is_released_without_guest_input(self):
        self.leases.request_lease.return_value = {'result':'waiting','request':{'request_id':'queued'}}
        self.leases.cancel.return_value = {'result':'missing'}
        self.leases.wait_for_lease.side_effect = [
            {'result':'waiting'}, {'result':'granted','lease':{'lease_id':'late','vm_id':'vm2'}}]
        with patch.object(vm, 'Guest') as guest, patch.object(vm.subprocess, 'run') as command:
            command.return_value.returncode = 0
            result = vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            guest.assert_not_called()
            self.leases.release.assert_called_once_with('late')
            self.assertEqual(result['cleanup'], [])

    def test_queue_promotion_uses_assigned_vm(self):
        self.leases.request_lease.return_value = {'result':'waiting','request':{'request_id':'queued'}}
        self.leases.wait_for_lease.return_value = {'result':'granted','lease':{'lease_id':'fixture','vm_id':'vm2'}}
        with patch.object(vm, 'Guest') as guest, patch.object(vm.subprocess, 'run') as command:
            guest.return_value.execute.side_effect = vm.Blocked('guest-exec-unavailable')
            command.return_value.returncode = 0
            vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            self.assertEqual(guest.call_args.args[1].vm_id, 'vm2')
            self.leases.release.assert_called_once_with('fixture')
            self.leases.cancel.assert_not_called()

    def test_cleanup_failure_not_pass_and_release_still_attempted(self):
        with patch.object(vm, 'Guest'), patch.object(vm, 'windows_checks', return_value={'status':'passed'}), patch.object(vm.subprocess, 'run', side_effect=OSError):
            result = vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('network-disable-unconfirmed', result['cleanup'])
            self.leases.release.assert_called_once()

    def test_reused_lease_not_released_or_touched(self):
        self.leases.request_lease.return_value['reused'] = True
        with patch.object(vm, 'Guest') as guest:
            vm.run_vm(self.store, self.run, ['tooltip_check.py'])
            guest.assert_not_called(); self.leases.release.assert_not_called()

    def test_stale_and_incomplete_result_rejected(self):
        for result in ({'request_id':'old','status':'passed'}, {'request_id':'new','status':'passed','tests':[]}):
            with self.assertRaises(vm.Blocked): vm.validate_result(result, 'new', ['tooltip_check.py'])

    def test_lost_lease_prevents_socket_access(self):
        self.leases.snapshot.return_value = {'vms':{'vm2':{'active':{'lease_id':'other'}}}}
        guest = vm.Guest({'lease_id':'fixture'}, self.specs.VM_SPECS['vm2'], self.leases)
        with patch.object(vm.socket, 'socket') as sock, self.assertRaises(vm.Blocked):
            guest.call('guest-ping')
        sock.assert_not_called()

    def test_no_credentials_in_interactive_task(self):
        xml = vm.task_xml('C:\\PFC-Test\\workflow\\fixture').decode('utf-16')
        self.assertIn('InteractiveToken', xml)
        self.assertIn('LeastPrivilege', xml)
        self.assertNotIn('Password', xml)

    def test_task_registration_failure_preserves_cleanup_errors(self):
        guest = MagicMock()
        def execute(path, args, **kwargs):
            if path == vm.SCHTASKS:
                raise vm.Blocked('guest-command-failed')
        guest.execute.side_effect = execute
        cleanup = []
        with self.assertRaises(vm.Blocked):
            vm.windows_checks(guest, ['tooltip_check.py'], 5, 5, cleanup)
        self.assertEqual(cleanup, ['task-stop-unconfirmed','task-removal-unconfirmed'])

    def test_worker_blocks_before_importing_pfc(self):
        directory = Path(self.temp.name)
        request = directory/'request.json'
        request.write_text(json.dumps({'request_id':'fixture','files':{},'checks':['tooltip_check.py']}))
        with patch.object(worker, 'desktop_ready', return_value=False), patch.object(worker.subprocess, 'Popen') as process:
            self.assertEqual(worker.execute(request), 2)
            process.assert_not_called()
        self.assertEqual(json.loads((directory/'result.json').read_text())['reason'], 'interactive-desktop-unavailable')


if __name__ == '__main__': unittest.main()

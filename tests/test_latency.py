import tempfile
import time
import unittest
from pathlib import Path

from pycommander.debuglog import DiagnosticLog, diagnostic_incidents, diagnostic_records, diagnostic_summary
from pycommander.latency import UiLatencyMonitor, latency_user_wait, latency_responsive_wait


class LatencyTests(unittest.TestCase):
    def setUp(self):
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.log = DiagnosticLog('test-version', raw.name, automatic=True)
        self.addCleanup(self.log.close)
        self.monitor = UiLatencyMonitor(self.log, stall=.16, total=.10, phase=.08,
                                        sample=.01, repeats=3, poll=.01)
        self.addCleanup(self.stop_monitor)

    def stop_monitor(self):
        self.monitor.close()
        self.monitor._thread.join(1)
        self.assertFalse(self.monitor._thread.is_alive())

    def records(self):
        return [row for row in diagnostic_records(self.log.snapshot(automatic=True))
                if row['event'].startswith('ui.')]

    def wait(self, predicate):
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.005)
        self.fail('No matching latency record')

    def test_repeated_delays_aggregate_and_fast_actions_stay_quiet(self):
        self.monitor.action('Refresh file list', lambda: self.monitor.measure('fast', lambda: None))
        self.assertEqual(self.records(), [])

        def operation():
            for i in range(3):
                self.monitor.measure('metadata', time.sleep, .014, item=Path(f'PRIVATE_{i}.unknown'))
            self.monitor.rows(3)

        self.log.event('context.test', note='PRIVATE_NOT_NEEDED')
        self.monitor.action('Refresh file list', operation)
        row = self.wait(lambda: next((r for r in self.records() if r['event']=='ui.operation.slow'), None))
        self.assertEqual(row['version'], 'test-version')
        self.assertTrue(row['time'] and row['utc_time'])
        self.assertEqual(row['latency']['rows'], 3)
        stats = row['latency']['phases'][0]
        self.assertEqual((stats['calls'], stats['slow_calls'], stats['file_type']), (3, 3, 'other entry'))
        self.assertNotIn('PRIVATE', str(row))
        self.assertNotIn('context', row)
        self.monitor.action('Refresh file list', operation)
        self.assertEqual(len(self.records()), 1)  # Repeated audit is rate-limited.

    def test_watchdog_persists_before_return_and_merges_recovery(self):
        def blocked_call():
            seen = self.wait(lambda: next((r for r in self.records() if r['event']=='ui.stall.detected'), None))
            self.assertEqual(seen['latency']['pending_phase'], 'Windows Shell icon')
            self.assertEqual(seen['latency']['pending_type'], '.lnk')
            self.assertNotIn('NDA_NAME', str(seen))

        self.monitor.action('Open folder', lambda: self.monitor.measure(
            'Windows Shell icon', blocked_call, item=Path('/PRIVATE/NDA_NAME.lnk')))
        self.monitor.heartbeat()
        self.wait(lambda: len(self.records())==3)
        rows = diagnostic_incidents(self.log.snapshot(automatic=True))
        row = next(row for row in rows if row.get('latency'))
        self.assertEqual(len(row['events']), 3)
        self.assertGreaterEqual(row['latency']['duration_ms'], 160)
        text = diagnostic_summary(row)
        for part in ('Action: Open folder', 'Waiting at capture: Windows Shell icon',
                     'Operation finished:', 'UI responded again'):
            self.assertIn(part, text)

    def test_generic_stall_and_intentional_user_wait(self):
        self.monitor.action('Open folder', lambda: latency_user_wait(self.monitor, time.sleep, .22))
        self.monitor.heartbeat()
        self.assertEqual(self.records(), [])
        row = self.wait(lambda: next((r for r in self.records() if r['event']=='ui.stall.detected'), None))
        self.assertNotIn('action', row['latency'])
        self.assertIn('Main window (unclassified)', diagnostic_summary(row))

    def test_total_can_trigger_without_a_slow_step(self):
        def callback():
            for i in range(8):
                self.monitor.measure('step '+str(i), time.sleep, .014)
        self.monitor.action('Open folder', callback)
        row = self.wait(lambda: next((r for r in self.records() if r['event']=='ui.operation.slow'), None))
        self.assertGreaterEqual(row['latency']['duration_ms'], 100)
        self.assertLessEqual(len(row['latency']['phases']), 4)

    def test_responsive_wait_does_not_hide_a_nested_stall(self):
        self.monitor.action('Open folder',lambda:latency_responsive_wait(self.monitor,time.sleep,.22))
        self.monitor.heartbeat()
        row=self.wait(lambda:next((r for r in self.records() if r['event']=='ui.stall.detected'),None))
        self.assertIn('stalled_ms',row['latency'])


if __name__ == '__main__':
    unittest.main()

import ctypes
from pathlib import Path
import struct
import threading
import time
import unittest
from pycommander.cloudstatus import CLOUD_LABELS, CloudStatusCache, cloud_state, _CloudPropertyKey, _CloudVariant
from pycommander.icons import cloud_badge_png


class CloudStatusTests(unittest.TestCase):
    def test_precedence_and_unknown(self):
        self.assertIsNone(cloud_state(None))
        self.assertIsNone(cloud_state(0xffffffff))
        self.assertIsNone(cloud_state(0x80, 0))
        self.assertIsNone(cloud_state(0x80000, 0))  # pinned intent alone is not hydration
        self.assertEqual(cloud_state(0x1000, 0x10, 10), 'error')
        self.assertEqual(cloud_state(0x1000, 8, 10), 'paused')
        self.assertEqual(cloud_state(0x80, 0x80), 'warning')
        for transfer in (1,2,4,0x20,0x40):
            self.assertEqual(cloud_state(0x1000, transfer), 'syncing')
        for attributes in (0x1000,0x40000,0x400000,0x81000):
            self.assertEqual(cloud_state(attributes), 'online')
        self.assertEqual(cloud_state(0x80,0,10),'available')
        self.assertEqual(cloud_state(0x80000,0,10),'pinned')

    def test_badges_distinct_and_scaled(self):
        for size in (8,16,32):
            icons = [cloud_badge_png(size, state) for state in CLOUD_LABELS]
            self.assertEqual(len(set(icons)), len(CLOUD_LABELS))
            for icon in icons:
                self.assertEqual(struct.unpack('>II',icon[16:24]), (size,size))

    def test_native_structure_layout(self):
        self.assertEqual(ctypes.sizeof(_CloudPropertyKey),20)
        self.assertEqual(_CloudVariant.value.offset,8)
        self.assertEqual(ctypes.sizeof(_CloudVariant),24)

    def test_one_worker_and_root_boundary(self):
        gate = threading.Event(); seen = []
        def reader(path):
            seen.append((path, threading.current_thread().name))
            gate.wait(2)
            return 'online'
        cache = CloudStatusCache([Path('/cloud')], reader)
        self.assertFalse(cache.eligible('/cloud-other/a'))
        cache.poll(['/cloud/a', '/cloud-other/b'])
        cache.due = 0
        for _ in range(10):
            cache.poll(['/cloud/a'])
        self.assertTrue(cache.busy)
        gate.set()
        deadline = time.monotonic()+3
        while cache.results.empty() and time.monotonic()<deadline:
            time.sleep(.01)
        cache.due = time.monotonic()+10
        self.assertTrue(cache.poll([]))
        self.assertEqual(cache.get('/cloud/a'),'online')
        self.assertEqual(seen,[('/cloud/a','PFC-OneDrive-metadata')])

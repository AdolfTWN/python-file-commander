import ctypes
from pathlib import Path
import struct
import threading
import time
import unittest
from pycommander.cloudstatus import CLOUD_LABELS, CloudStatusCache, cloud_state, _CloudPropertyKey, _CloudVariant
from pycommander.icons import cloud_badge_png, cloud_badge_geometry, cloud_badge_needs_lightening, CLOUD_BADGE_COLORS


class CloudStatusTests(unittest.TestCase):
    def test_only_similar_opaque_icon_colors_trigger_lightening(self):
        cyan=(0,217,255);white=(255,255,255);red=(255,48,48)
        self.assertTrue(cloud_badge_needs_lightening('available',[cyan,cyan,white]))
        self.assertFalse(cloud_badge_needs_lightening('available',[cyan,red,white]))
        self.assertTrue(cloud_badge_needs_lightening('error',[red]))
        self.assertFalse(cloud_badge_needs_lightening('available',[white,(0,0,0)]))
        self.assertFalse(cloud_badge_needs_lightening('available',[]))
        self.assertFalse(cloud_badge_needs_lightening('unknown',[cyan]))
        self.assertFalse(cloud_badge_needs_lightening('online',[(185,167,255)]))

    def test_lightened_variant_is_separate_and_cached_without_mutating_palette(self):
        palette=dict(CLOUD_BADGE_COLORS)
        first=cloud_badge_png(16,'available',True)
        self.assertNotEqual(first,cloud_badge_png(16,'available'))
        self.assertIs(first,cloud_badge_png(16,'available',True))
        self.assertEqual(CLOUD_BADGE_COLORS,palette)

    def test_triangle_is_attached_and_leaves_vcs_half_uncovered(self):
        for size in (16,24,42,48,80):
            diameter,x=cloud_badge_geometry(size)
            self.assertGreaterEqual(diameter,8)
            self.assertLessEqual(diameter,size//2)
            self.assertEqual(x+diameter,size)
            self.assertGreaterEqual(x,size//2)
    def test_new_folder_does_not_wait_for_previous_refresh_timer(self):
        started=threading.Event();release=threading.Event();seen=[]
        def reader(path):
            seen.append((path,threading.current_thread().name));started.set()
            release.wait(2);return 'available'
        cache=CloudStatusCache([Path('/cloud')],reader)
        cache.due=time.monotonic()+100
        cache.poll(['/cloud/new/a'])
        self.assertTrue(started.wait(1))
        self.assertTrue(cache.busy)
        self.assertEqual(seen,[('/cloud/new/a','PFC-OneDrive-metadata')])
        cache.poll(['/cloud/next/b']);cache.poll(['/cloud/latest/c'])
        self.assertEqual(len(seen),1)  # Never add parallel metadata workers.
        release.set()
        end=time.monotonic()+3
        while cache.results.empty() and time.monotonic()<end:time.sleep(.01)
        cache.poll(['/cloud/latest/c'])
        while len(seen)<2 and time.monotonic()<end:time.sleep(.01)
        self.assertEqual([p for p,_ in seen],['/cloud/new/a','/cloud/latest/c'])
        self.assertEqual(cache.get('/cloud/new/a'),'available')

    def test_badge_rasterization_is_bounded_and_reused(self):
        cloud_badge_png.cache_clear()
        first=cloud_badge_png(16,'available')
        self.assertIs(cloud_badge_png(16,'available'),first)
        self.assertEqual(cloud_badge_png.cache_info().hits,1)
        self.assertEqual(cloud_badge_png.cache_info().maxsize,128)
    def test_triangle_faces_contrast_with_dark_keyline(self):
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
        for state,(face,ink) in CLOUD_BADGE_COLORS.items():
            hi,lo=sorted((luminance(face),luminance(ink)),reverse=True)
            self.assertGreaterEqual((hi+.05)/(lo+.05),4.5,state)
        self.assertNotEqual(CLOUD_BADGE_COLORS['syncing'],CLOUD_BADGE_COLORS['online'])
        for invalid in ('unknown','synced',''):
            with self.assertRaises(ValueError):cloud_badge_png(16,invalid)

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
            self.assertEqual(len(set(icons)), len(CLOUD_LABELS)-1)  # available/pinned share the synced triangle
            self.assertEqual(cloud_badge_png(size,'available'),cloud_badge_png(size,'pinned'))
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

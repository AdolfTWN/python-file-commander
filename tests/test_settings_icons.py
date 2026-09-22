import struct
import unittest
import zlib

from pycommander.settings import settings_check_icon_png


def pixels(png):
    size=struct.unpack('>I',png[16:20])[0]
    offset=8;compressed=bytearray()
    while offset<len(png):
        length=struct.unpack('>I',png[offset:offset+4])[0]
        if png[offset+4:offset+8]==b'IDAT':compressed.extend(png[offset+8:offset+8+length])
        offset+=length+12
    rows=zlib.decompress(compressed);stride=1+4*size
    return [tuple(rows[y*stride+1+x*4:y*stride+5+x*4]) for y in range(size) for x in range(size)]


class SettingsCheckIconTests(unittest.TestCase):
    def test_four_distinct_states_and_antialiased_edges(self):
        for size in (18,20,24):
            for dark in (False,True):
                images=[]
                for selected,disabled in ((False,False),(True,False),(False,True),(True,True)):
                    png=settings_check_icon_png(size,selected,disabled,dark)
                    self.assertEqual(struct.unpack('>II',png[16:24]),(size,size))
                    rgba=pixels(png)
                    self.assertEqual(rgba[0][3],0)
                    self.assertTrue(any(0<p[3]<255 for p in rgba))
                    images.append(png)
                self.assertEqual(len(set(images)),4)

    def test_enabled_symbol_is_a_tick_not_cross(self):
        rgba=pixels(settings_check_icon_png(20,True,False,False))
        for x,y in ((5,10),(8,13),(14,7)):
            self.assertEqual(rgba[y*20+x],(255,255,255,255))
        for x,y in ((5,5),(14,14),(10,6)):
            self.assertEqual(rgba[y*20+x],(23,111,188,255))

    def test_bytes_reused_without_interpreter_owned_image_cache(self):
        self.assertIs(settings_check_icon_png(20,True,False,False),
                      settings_check_icon_png(20,True,False,False))


if __name__=='__main__':unittest.main()

"""Compact lock badges rendered from geometry, without fonts or image dependencies."""
from functools import lru_cache
import math

from .icons import _distance_to_segment, _hex_rgba, _rgba_png_downsample


@lru_cache(maxsize=48)
def tab_lock_icon_png(mode: str, size: int, background: str, foreground: str) -> bytes:
    """Render at 4x resolution; cache bytes, never Tk images across interpreters."""
    if mode not in {'locked', 'reset'}:
        raise ValueError('A badge requires a locked or reset tab')
    if not 16 <= size <= 128:
        raise ValueError('Tab badge size must be between 16 and 128 pixels')
    supersample = 4
    extent = size * supersample
    unit = extent / 32
    pixels = bytearray(extent * extent * 4)
    face, ink = _hex_rgba(background), _hex_rgba(foreground)

    def paint(bounds, inside, color):
        x1, y1, x2, y2 = bounds
        for y in range(max(0, math.floor(y1*unit)), min(extent, math.ceil(y2*unit))):
            py = (y+.5)/unit
            for x in range(max(0, math.floor(x1*unit)), min(extent, math.ceil(x2*unit))):
                if inside((x+.5)/unit, py):
                    index = (y*extent+x)*4
                    pixels[index:index+4] = bytes(color)

    def rounded(x1, y1, x2, y2, radius, color):
        def inside(x, y):
            cx = max(x1+radius, min(x, x2-radius))
            cy = max(y1+radius, min(y, y2-radius))
            return (x-cx)**2 + (y-cy)**2 <= radius**2
        paint((x1, y1, x2, y2), inside, color)

    def line(x1, y1, x2, y2, width, color):
        r = width/2
        paint((min(x1,x2)-r, min(y1,y2)-r, max(x1,x2)+r, max(y1,y2)+r),
              lambda x,y: _distance_to_segment(x,y,x1,y1,x2,y2) <= r, color)

    # Identical neutral tile for BOTH modes. A fine contrasting edge keeps the
    # light tile legible on a custom pastel tab in the dark application theme.
    rounded(.5, .5, 31.5, 31.5, 5, ink)
    rounded(1.3, 1.3, 30.7, 30.7, 4.2, face)
    if mode == 'locked':
        rounded(9, 5, 23, 21, 7, ink)
        rounded(12, 8, 20, 20, 4, face)
        rounded(6.5, 14, 25.5, 27, 2, ink)
        rounded(14.6, 17.5, 17.4, 23.5, 1.4, face)
    else:
        # Small closed lock at upper right; a large hooked arrow dominates the
        # lower/left silhouette. Distinguishable even with identical tile colors.
        rounded(18, 4, 27, 15, 4.5, ink)
        rounded(20.5, 6.5, 24.5, 15, 2, face)
        rounded(16, 10, 29, 18, 1.5, ink)
        line(11, 15, 5, 21, 3, ink)
        line(5, 21, 11, 27, 3, ink)
        line(5, 21, 22, 21, 3, ink)
        # Right semicircle connects the top return stroke to its lower tail.
        paint((20, 19.5, 29, 29.5),
              lambda x,y: x >= 22 and 1 <= (x-22)**2+(y-24.5)**2 <= 25, ink)
        line(16, 28, 22, 28, 3, ink)
    return _rgba_png_downsample(pixels, size, supersample)

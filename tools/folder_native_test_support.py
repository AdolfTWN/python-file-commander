"""Assertions shared by native-image tree tests (not a fake overlay)."""
def capture_window(window, path):
    """GDI visual evidence with no optional packages in the Windows guest."""
    import ctypes as c
    from ctypes import wintypes as w
    import struct
    import time
    user, gdi = c.WinDLL('user32'), c.WinDLL('gdi32')
    user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
    user.SetForegroundWindow.argtypes=[w.HWND]
    user.SetForegroundWindow(user.GetAncestor(window.winfo_id(),2))
    window.update();time.sleep(.25);window.update()
    user.GetDC.argtypes=[w.HWND];user.GetDC.restype=w.HDC
    user.ReleaseDC.argtypes=[w.HWND,w.HDC]
    gdi.CreateCompatibleDC.argtypes=[w.HDC];gdi.CreateCompatibleDC.restype=w.HDC
    gdi.CreateCompatibleBitmap.argtypes=[w.HDC,c.c_int,c.c_int];gdi.CreateCompatibleBitmap.restype=w.HBITMAP
    gdi.SelectObject.argtypes=[w.HDC,w.HGDIOBJ];gdi.SelectObject.restype=w.HGDIOBJ
    gdi.DeleteObject.argtypes=[w.HGDIOBJ];gdi.DeleteDC.argtypes=[w.HDC]
    gdi.BitBlt.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,w.HDC,c.c_int,c.c_int,w.DWORD]
    gdi.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,c.c_void_p,c.c_void_p,w.UINT]
    width,height=window.winfo_width(),window.winfo_height()
    screen=user.GetDC(None);dc=gdi.CreateCompatibleDC(screen)
    bitmap=gdi.CreateCompatibleBitmap(screen,width,height);old=gdi.SelectObject(dc,bitmap)
    try:
        assert gdi.BitBlt(dc,0,0,width,height,screen,window.winfo_rootx(),window.winfo_rooty(),0x00CC0020)
        gdi.SelectObject(dc,old)
        info=struct.pack('<IiiHHIIiiII',40,width,height,1,32,0,width*height*4,0,0,0,0)
        header=c.create_string_buffer(info);pixels=c.create_string_buffer(width*height*4)
        assert gdi.GetDIBits(dc,bitmap,0,height,pixels,header,0)==height
        assert len(set(pixels.raw))>16, 'Blank native capture is not visual acceptance'
        path.write_bytes(struct.pack('<2sIHHI',b'BM',54+len(pixels.raw),0,0,54)+info+pixels.raw)
    finally:
        gdi.SelectObject(dc,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(dc);user.ReleaseDC(None,screen)

def row_geometry(nav, iid):
    box=nav.tree.bbox(iid)
    assert box, ('row not visible',iid)
    image=nav._row_images[iid]
    return box[0], box[1], image.width(), box[3]

def has_badge(nav, iid):
    image=nav._row_images[iid]
    r=max(3,min(5,round(nav._line_indent*.13)))
    px=round(image.width()-nav._line_indent/2)+round(nav._icon_size*.28)
    py=image.height()//2+round(nav._icon_size*.26)
    # The badge bottom edge is below the folder glyph and horizontal connector.
    return not image.transparency_get(px,py+r)

def assert_guides(nav, iid):
    chain=[];item=iid
    while item:
        chain.append(item);item=nav.tree.parent(item)
    chain.reverse()
    image=nav._row_images[iid]
    for level in range(1,len(chain)-1):
        x=round((level-.5)*nav._line_indent)
        assert (not image.transparency_get(x,0))==bool(nav.tree.next(chain[level])),(iid,level)
    return max(0,len(chain)-2)

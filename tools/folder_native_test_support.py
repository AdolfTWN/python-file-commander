"""Assertions shared by native-image tree tests (not a fake overlay)."""
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

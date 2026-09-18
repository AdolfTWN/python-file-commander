"""Display-only column settings; sorting always uses underlying metadata."""
from datetime import datetime


def modified_text(timestamp, date_order="ymd", time_style="24"):
    value = datetime.fromtimestamp(timestamp)
    date = value.strftime("%m/%d/%Y" if date_order == "mdy" else "%Y/%m/%d")
    if time_style == "none":
        return date
    clock = (f"{value.hour % 12 or 12:02}{value.minute:02}{'a' if value.hour < 12 else 'p'}"
             if time_style == "12" else value.strftime("%H:%M"))
    return date + " " + clock


def font_snapshot(font, **changes):
    """Preserve negative pixel sizes: Font.actual() converts them to points."""
    attributes = font.actual()
    attributes['size'] = font.cget('size')
    attributes.update(changes)
    return attributes

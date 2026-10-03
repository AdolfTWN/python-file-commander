"""Shared comparison semantics, independent of application accent colors."""


def comparison_colors(palette):
    color=palette.get('content','#ffffff').lstrip('#')
    dark=len(color)==6 and sum(int(color[n:n+2],16) for n in (0,2,4))<384
    if dark:
        return dict(base='#23282e',text='#f1f3f5',line='#513238',inline='#81454c',
                    orphan='#403452',gap='#30363e',gutter='#2b323a',muted='#bcc5cf',
                    match='#66561b',match_text='#fff2b0',current='#284d70',current_text='#ffffff')
    return dict(base='#ffffff',text='#202830',line='#fde9e7',inline='#f4b8b2',
                orphan='#eee6f7',gap='#edf0f3',gutter='#f2f4f6',muted='#56616d',
                match='#fff0a6',match_text='#292600',current='#d5e8fa',current_text='#153955')


def style_comparison_text(widget,palette):
    colors=comparison_colors(palette)
    widget.configure(background=colors['base'],foreground=colors['text'],insertbackground=colors['text'],
                     selectbackground='#245e91',selectforeground='#ffffff')
    for tag,key in [('diff','line'),('inline_diff','inline'),('orphan','orphan'),('gap','gap')]:
        widget.tag_configure(tag,background=colors[key],foreground=colors['text'])
    # Current difference is a navigation cue, not selection of every character.
    widget.tag_configure('current',background='',foreground='',underline=True)
    widget.tag_configure('match',background=colors['match'],foreground=colors['match_text'])
    widget.tag_configure('current_match',background=colors['match'],foreground=colors['match_text'],underline=True)
    for tag in ('diff','orphan','gap','inline_diff','current','match','current_match','sel'):widget.tag_raise(tag)
    return colors

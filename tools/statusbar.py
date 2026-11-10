#!/usr/bin/env python3
"""The status bar's geometry and text styles, one table for both copies of the bar.

ui/system_bar.bin is the real bar (every page); ui/dialog/dropdown_dialog.bin carries its own
copy, view_sysbar, which stock code fills the same way (dropdown_showface @0x475c3c and its twin @0x545168 set the
same widgets by name). Both are laid out by `apply` from this table, so they cannot drift apart: the same
element positions (play / pause, volume glyph and number, digital-out glyph, clock, Bluetooth, SyncLink, Wi-Fi, battery
outline and fill), font sizes, colours, alignment and spacing, in 12 h and 24 h mode. The
pull-down's bar sits at y 0 of the dialog, which is open at y 0 of the screen, exactly over the real bar, on the same
black. test/pod/assets.py compares the two built files widget by widget.

Usage: imported by tools/mod_theme.py (system bar) and tools/mod_pulldown.py (pull-down bar).
"""

from awtk_ui import Widget

EDGE, GAP = 10, 4                # left margin of the left group and right margin of the battery; spacing inside both groups
SMALL_PX, CLOCK_PX = 16, 18      # volume number, clock
PCT_PX = 13                      # the battery percentage label (patch/battery.c; hidden unless Settings > System > Battery > Battery Percentage is on): white, right-aligned in the right group
LO_WIDGET, LO_IMAGE, LO_W = 'pod_lo', 'pod_bar_lo', 26   # the Line Out pill (patch/lineout.h LO_PILL; tools/mod_icons.py LO_BAR, 26 x 16): in view_bar_left right after label_volume, in both bar copies; the widget is label_volume's VOLUME_W wide with the image centred, so the icons after it do not move
SYNC_WIDGET, SYNC_IMAGE, SYNC_W = 'pod_sync', 'pod_bar_sync', 18   # the sync icon (patch/lineout.h SYNC_IND; tools/mod_icons.py SYNC_BAR, 18 x 18): in view_bar_right right after img_btclass, in both bar copies, hidden and insensitive until patch/lineout.c shows it while a cover or duration build runs
VOLUME_W = 30                 # the volume label's box ("100" at 16 px)
CLOCK_X, CLOCK_W = 104, 90       # centre 149: "12:59 PM" (66 px at 18) spans 116..182
BAR_BG = '#000000'               # the bar's colour (system_bar's own style; the pull-down panel behind it is #141414)
STATES = ('normal', 'disable', 'focused')
NAMES = ('view_bar_left', 'bar_dclock', 'view_bar_right', 'label_volume', 'pgbar_battery', 'img_battery')


def apply(bar):
    """Lay out `bar` (the system_bar root, or the pull-down's view_sysbar) from the table. The battery outline and its
    fill (tools/mod_battery.py) are already placed; the right-hand icon group is kept GAP px clear of the outline."""
    left, right, clock, vol, img = (bar.find(n) for n in ('view_bar_left', 'view_bar_right', 'bar_dclock', 'label_volume', 'img_battery'))
    assert all(w is not None for w in (left, right, clock, vol, img)), 'unexpected status bar layout'
    assert img.x + img.w == 320 - EDGE, 'the battery outline is not at the bar\'s right edge'
    left.set('children_layout', f'default(r=1,c=0,x={EDGE},s={GAP})')
    for st in STATES:
        vol.set(f'style:{st}:font_size', str(SMALL_PX)); vol.set(f'style:{st}:text_align_v', 'middle')
    vol.w = VOLUME_W
    clock.x, clock.w = CLOCK_X, CLOCK_W
    clock.set('self_layout', f'default(x={CLOCK_X},y=0,w={CLOCK_W},h=100%)')
    clock.set('style:normal:font_size', str(CLOCK_PX))
    right.set('children_layout', f'default(r=1,c=0,a=right,s={GAP})')
    right.x = img.x - GAP - right.w
    assert left.find(LO_WIDGET) is None, 'the Line Out pill is already in the bar'
    pill = Widget('image', 0, 0, VOLUME_W, 0, [('name', LO_WIDGET), ('image', LO_IMAGE), ('draw_type', 'center'), ('visible', 'false'), ('sensitive', 'false')])
    left.children.insert(left.children.index(vol) + 1, pill)   # right after label_volume: hidden and insensitive, the layouter skips it until patch/lineout.c swaps it for the label
    assert right.find(SYNC_WIDGET) is None, 'the sync icon is already in the bar'
    bt = right.find('img_btclass')
    assert bt is not None, 'unexpected status bar layout'
    sync = Widget('image', 0, 0, SYNC_W, 0, [('name', SYNC_WIDGET), ('image', SYNC_IMAGE), ('draw_type', 'center'), ('visible', 'false'), ('sensitive', 'false')])
    right.children.insert(right.children.index(bt) + 1, sync)   # after the Bluetooth box (its 47 px box ends in the glyph, so the icon sits right of the glyph: left of the box would be over the clock); the layouter skips it while hidden

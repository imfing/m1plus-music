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
import battery_art

EDGE, GAP, RGAP, BAT_GAP = 10, 4, 3, 5   # left margin of the left group and right margin of the battery; spacing inside the left group; spacing inside the right group (patch/lineout.h SLEEP_GAP) and from it to the battery. The right group is spaced by shape: Wi-Fi's fan is narrow at the bottom and the moon is hollow on its right, so they sit RGAP px from the mark before them, and the moon, SyncLink and the sync arrows carry 3, 2 and 1 px of empty canvas on the left (tools/status_art.py), which puts them 6, 5 and 4 px from it
SMALL_PX, CLOCK_PX = 16, 18      # volume number, clock
PCT_PX, PCT_FACE, PCT_RGB, PCT_DY = 15, 'lyrics', '#000000', 1   # the battery percentage (patch/battery.c; hidden unless Settings > Battery > Battery Percentage is on): black digits in the bold face, centred in the battery's body (battery_parts); the box is PCT_PX high, PCT_DY px below the body's top (so it ends 2 px below the body): AWTK centres the whole line and puts the baseline int(ascender * scale) below its top, and digits have no descender, so this puts their ink, 9.3 px tall, 2.7 px below the body's top and 2 px above its bottom; "100" is 1 px from the rim
LO_WIDGET, LO_IMAGE, LO_W = 'pod_lo', 'pod_bar_lo', 26   # the Line Out pill (patch/lineout.h LO_PILL; tools/mod_icons.py LO_BAR, 26 x 16): in view_bar_left right after label_volume, in both bar copies; the widget is label_volume's VOLUME_W wide with the image centred, so the icons after it do not move
SYNC_WIDGET, SYNC_IMAGE, SYNC_W = 'pod_sync', 'pod_bar_sync', 16   # the sync icon (patch/lineout.h SYNC_IND; tools/mod_icons.py SYNC_BAR, 16 x 18): in view_bar_right right after img_btclass, in both bar copies, hidden and insensitive until patch/lineout.c shows it while a cover or duration build runs
SLEEP_WIDGET, SLEEP_IMAGE, SLEEP_W = 'pod_sleep', 'pod_bar_sleep', 17   # the sleep timer icon (patch/lineout.h SLEEP_IND; tools/mod_icons.py SLEEP_BAR, 17 x 16): in view_bar_right right after pod_sync, in both bar copies, hidden and insensitive until patch/lineout.c shows it while a Sleep Timer is running
EQ_WIDGET, EQ_TEXT, EQ_PX, EQ_W = 'pod_eq', 'EQ', SMALL_PX, 19   # the EQ mark (patch/lineout.h EQ_IND): a label in label_volume's colour at the volume number's size, 16 px ("EQ" is 19 px wide), in view_bar_left right after the Line Out pill, in both bar copies, hidden and insensitive until patch/lineout.c shows it while the Equalizer is on
CHG_LEVEL, CHG_GREEN = 'pod_chg_lvl', '#34C759'   # the battery's green level while charging (patch/battery.h BP_LEVEL; battery_art.CHARGE)
CHG_WIDGET, CHG_IMAGE, CHG_S_WIDGET, CHG_S_IMAGE = 'pod_chg_bolt', 'pod_bar_chg', 'pod_chg_bolts', 'pod_bar_chgs'   # the battery's charging bolts (patch/battery.h BP_BOLT, BP_BOLT_S; tools/mod_icons.py CHG_BAR, CHG_BAR_S): the middle one, and the small one right of the number (battery_parts)
WIFI_W = 16                  # stock's img_wifi, narrowed to the glyph (tools/status_art.py wifi: 16 x 16)
VOLUME_W = 30                # the volume label's box ("100" at 16 px)
CLOCK_X, CLOCK_W = 115, 90       # centred on the 320 px bar (160), text centred in the box: "10:59 AM" (74 px at 18) spans 123..197, "23:59" (45 px) 138..182; the right group's own marks yield to keep clear of it (patch/lineout.h BAR_ROOM_12H)
BAR_BG = '#000000'               # the bar's colour (system_bar's own style; the pull-down panel behind it is #141414)
STATES = ('normal', 'disable', 'focused')
NAMES = ('view_bar_left', 'bar_dclock', 'view_bar_right', 'label_volume', 'pgbar_battery', 'img_battery')


def apply(bar):
    """Lay out `bar` (the system_bar root, or the pull-down's view_sysbar) from the table. The battery outline and its
    fill (tools/mod_battery.py) are already placed; the right-hand icon group is kept BAT_GAP px clear of the outline."""
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
    right.set('children_layout', f'default(r=1,c=0,a=right,s={RGAP})')
    right.x = img.x - BAT_GAP - right.w
    wifi = right.find('img_wifi'); assert wifi is not None, 'unexpected status bar layout'
    wifi.w = WIFI_W
    assert left.find(LO_WIDGET) is None, 'the Line Out pill is already in the bar'
    pill = Widget('image', 0, 0, VOLUME_W, 0, [('name', LO_WIDGET), ('image', LO_IMAGE), ('draw_type', 'center'), ('visible', 'false'), ('sensitive', 'false')])
    left.children.insert(left.children.index(vol) + 1, pill)   # right after label_volume: hidden and insensitive, the layouter skips it until patch/lineout.c swaps it for the label
    assert left.find(EQ_WIDGET) is None, 'the EQ mark is already in the bar'
    props = [('name', EQ_WIDGET), ('text', EQ_TEXT), ('visible', 'false'), ('sensitive', 'false')]
    for st in STATES:
        props += [(f'style:{st}:text_color', vol.get(f'style:{st}:text_color')), (f'style:{st}:font_size', str(EQ_PX)), (f'style:{st}:text_align_h', 'center'), (f'style:{st}:text_align_v', 'middle')]
    left.children.insert(left.children.index(pill) + 1, Widget('label', 0, 0, EQ_W, 0, props))   # after the volume number (or the pill), before the digital-out glyph; the layouter skips it while hidden
    assert right.find(SYNC_WIDGET) is None, 'the sync icon is already in the bar'
    bt = right.find('img_btclass')
    assert bt is not None, 'unexpected status bar layout'
    sync = Widget('image', 0, 0, SYNC_W, 0, [('name', SYNC_WIDGET), ('image', SYNC_IMAGE), ('draw_type', 'center'), ('visible', 'false'), ('sensitive', 'false')])
    right.children.insert(right.children.index(bt) + 1, sync)   # after the Bluetooth box (its 47 px box ends in the glyph, so the icon sits right of the glyph: left of the box would be over the clock); the layouter skips it while hidden
    assert right.find(SLEEP_WIDGET) is None, 'the sleep timer icon is already in the bar'
    sleep = Widget('image', 0, 0, SLEEP_W, 0, [('name', SLEEP_WIDGET), ('image', SLEEP_IMAGE), ('draw_type', 'center'), ('visible', 'false'), ('sensitive', 'false')])
    right.children.insert(right.children.index(sync) + 1, sleep)   # beside the sync icon, between Bluetooth and Wi-Fi; the layouter skips it while hidden


def battery_parts(root, suffix=''):
    """The Battery Percentage's widgets around the battery of `root` (the status bar, the pull-down's bar copy, the lock screen), named with `suffix`
    ('' / '_dd' / '_lk'; patch/battery.h). In paint order: pod_bat_bg (the body's grey, battery_art.EMPTY), pod_pct_bg (the lighter grey EMPTY_PCT, hidden),
    pgbar_battery (the white level, its own background now transparent), pod_chg_lvl (the same bar in the charging green, hidden: it covers the white level),
    img_battery (the rim and the nub), pod_chg_bolt (the charging bolt in the body's middle, hidden), pod_chg_bolts (the small bolt at the interior's right end, hidden)
    and pod_pct (the number: black, the bold face, its ink centred in the body, hidden). All the new widgets are insensitive; patch/battery.c shows pod_pct_bg and pod_pct
    together, and while charging pod_chg_lvl with the level's value and one of the bolts: the middle one without the number, the small one right of a number of one or two digits."""
    img, pg = root.find('img_battery'), root.find('pgbar_battery')
    owner = next(w for w in root.walk() if pg in w.children)
    assert img in owner.children and owner.children.index(pg) < owner.children.index(img) and root.find('pod_pct' + suffix) is None, 'unexpected battery layout'
    assert (pg.x - img.x, pg.y - img.y, pg.w, pg.h) == battery_art.STATUS.fill, 'the level is not the battery\'s interior'
    for st in STATES: pg.set(f'style:{st}:bg_color', '#00000000')
    def backdrop(name, rgb, shown):
        v = Widget('view', pg.x, pg.y, pg.w, pg.h, [('name', name + suffix), ('sensitive', 'false')] + ([] if shown else [('visible', 'false')]))
        v.set('style:normal:bg_color', rgb); return v
    at = owner.children.index(pg)
    owner.children[at:at] = [backdrop('pod_bat_bg', battery_art.EMPTY, True), backdrop('pod_pct_bg', battery_art.EMPTY_PCT, False)]
    green = Widget('progress_bar', pg.x, pg.y, pg.w, pg.h, [('name', CHG_LEVEL + suffix)] + [(k, v) for k, v in pg.props if k not in ('name', 'visible', 'sensitive')] + [('visible', 'false'), ('sensitive', 'false')])
    for st in STATES: green.set(f'style:{st}:fg_color', CHG_GREEN)
    owner.children.insert(owner.children.index(pg) + 1, green)
    bx, by, bw, bh = battery_art.STATUS.body
    props = [('name', 'pod_pct' + suffix), ('text', '87'), ('visible', 'false'), ('sensitive', 'false')]
    for st in STATES:
        props += [(f'style:{st}:text_color', PCT_RGB), (f'style:{st}:font_size', str(PCT_PX)), (f'style:{st}:font_name', PCT_FACE),
                  (f'style:{st}:text_align_h', 'center'), (f'style:{st}:text_align_v', 'middle')]
    def bolt(name, image, box):
        return Widget('image', img.x + box[0], img.y + box[1], box[2], box[3], [('name', name + suffix), ('image', image), ('draw_type', 'default'), ('visible', 'false'), ('sensitive', 'false')])
    owner.children[owner.children.index(img) + 1:owner.children.index(img) + 1] = [
        bolt(CHG_WIDGET, CHG_IMAGE, battery_art.BOLT_MID), bolt(CHG_S_WIDGET, CHG_S_IMAGE, battery_art.BOLT_SMALL), Widget('label', img.x + bx, img.y + by + PCT_DY, bw, PCT_PX, props)]

#!/usr/bin/env python3
"""Build the M1+ Music page assets (ui/*.bin) from tools/pod_pages.py.

These are new AWTK UI files, not edits of stock ones, so they are added to the rootfs (fwtool
repack --allow-added lists them). Each page is a window with a stock-styled navigation bar (title,
Back, Now Playing) over a column of touch-friendly row buttons; the hello page shows a label
instead. Row widget names are pod_row0, pod_row1, ... so patch/m1plus.c can bind them by name.

Layout follows q2-pod's iPod menu (docs/ipod.md) adapted to 320x480 touch, inside the 450 px a
normal window gets under the 30 px status bar: a 50 px navbar over a stock-structured scrolling
list of 52 px rows (400 px visible, so seven and a half rows show and the rest scroll into view).
Cover Flow's page has its own layout.

Usage: pod_ui.py WORKDIR   (writes ui/*.bin into WORKDIR/rootfs; prints the files)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui
from awtk_ui import Widget
import pod_i18n, pod_pages
import pod_keyboard as PK
import pod_search as PS

UI = 'release/assets/default/raw/ui'   # relative to a rootfs dir
SCREEN_W, SCREEN_H = 320, 480
# A normal window gets the screen under the 30 px system_bar: 450 px. 68 stock pages end exactly at
# y=450 (systemset/sysset_page.bin: navbar 0-50, list 50-450); only fullscreen windows
# (screensaver_page, fullscreen=true) use all 480.
CLIENT_H = 450
NAVBAR_H = 50
ROW_H = 52        # every row page uses full-height rows and scrolls when they do not fit
UI_MODE = 0o744         # stock ui/*.bin mode
UI_MTIME = 1750924035   # a stock ui/*.bin mtime (2025-06-26); fixed so added assets build deterministically


def styled(w, states, prop, value):
    for st in states: w.set(f'style:{st}:{prop}', value)


def _offsets():
    import re
    out = {}
    for line in open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patch', 'offsets.inc')):
        m = re.match(r'#define (\w+) (-?(?:0x[0-9a-fA-F]+|\d+))u?\s*(?:/\*.*)?$', line.strip())
        if m: out[m.group(1)] = int(m.group(2), 0)
    return out


OFFSETS = _offsets()


# The navbar toggle of the Pod pages (Albums grid, Artists), flush left of Now Playing (x 260): a plain white glyph
# showing the view a tap switches to (the Albums page swaps the glyph with its mode, as the Artists page does).
NAV_VIEW_X, NAV_VIEW_W = 214, 46     # patch/offsets.inc NAV_VIEW_X, NAV_VIEW_W: main's slots (docs/modules/navbar.md); the glass capsule's pieces are cut to them (docs/modules/navbar.md)
NAV_VIEW_ICON = {'list': 'pod_nav_list', 'grid': 'pod_nav_grid',
                 'artist': 'pod_nav_albumartist'}   # images added by tools/mod_icons.py (glass pieces); artist: built in Artist mode, so the Album Artist glyph
TOGGLE_NAME = {'list': 'btn_albumview', 'grid': 'btn_albumview', 'artist': 'btn_artisttype'}
# The Albums page's Cover Flow button, flush left of the toggle: the capsule's left cap.
NAV_CF_W = NAV_VIEW_W
NAV_CF_X = NAV_VIEW_X - NAV_CF_W     # 168; patch/offsets.inc NAV_CF_X, NAV_CF_W
NAV_CF_ICON = 'pod_nav_coverflow'
NAV_ICON_OVERFLOW = 7               # 60 px icons centred in 46 px slots paint 7 px beyond their touch rectangles
NAV_BACK_X, NAV_BACK_W = 7, 44       # Back: the glass disc ah_nav_back (42 px) centred in a 44 x 50 button: x 8 .. 50, y 4 .. 46 (img_btn_style, so the shared navbar_btnreturn_style and the stock pages are untouched)
NAV_TITLE_X = 58                     # the title starts 8 px after the disc
NAV_PLAY_X, NAV_PLAY_W = 260, 60     # Now Playing: main's button; its image is the disc ah_nav_np alone (glyph centre 290) or a capsule's right cap ah_nav_play (same glyph, the glass ends at x 311)
NAV_TITLE_END = NAV_PLAY_X            # a title with no toggle ends before Now Playing's button (its disc starts at 269)


NAV_SONGS_ICON = 'pod_nav_songs'
NB_FADE_NAME, NB_FADE_H = 'img_nb_fade', 20     # the soft fade under the bar (tools/mod_icons.py NB_FADE; mod_ipodrows.NB_FADE_NAME)


def nav_fade(shown=True):
    """The fade over the first rows of the list under the bar: an insensitive image (never takes a touch), right after the list.
    shown=False (the cover pages, whose first row would be darkened at rest): built hidden, the page's code shows it while the list is scrolled."""
    w = Widget('image', 0, NAVBAR_H, SCREEN_W, NB_FADE_H, [('name', NB_FADE_NAME), ('image', 'nb_fade'), ('draw_type', 'default'),
                                                           ('clickable', 'false'), ('sensitive', 'false')])
    if not shown: w.set('visible', 'false')
    return w


SONGS_BUTTONS = (('btn_search', 'pod_nav_search', 122), ('btn_sort', 'pod_nav_songsort', 168), ('btn_select', 'pod_nav_select', 214))   # the Songs page's capsule, the stock Songs page's order: Search, Sort, Select, then Now Playing
NAV_SEARCH_X = SONGS_BUTTONS[0][2]


NAV_SETTINGS_ICON = 'pod_nav_settings'   # the Extras page's Settings button: the capsule's left cap on the 214 slot (tools/mod_icons.py)


def navbar(title, toggle=None, coverflow=False, artist_songs=False, more=False, songs=False, settings=False, select=False, show_more=False, show_globe=False):
    nb = Widget('view', 0, 0, SCREEN_W, NAVBAR_H, [('name', 'navigationbar_view')])
    # a title runs under a toggle's button no further than the button's left edge
    right = NAV_SEARCH_X if songs else NAV_CF_X if coverflow or more else NAV_VIEW_X if toggle or settings or select or show_more else NAV_TITLE_END
    lbl = Widget('label', NAV_TITLE_X, 14, right - NAV_TITLE_X, 22,
                 [('name', 'label_title'), ('style', 'navbar_label_white'), ('length', '31'), pod_i18n.text_prop(title)])
    ret = Widget('button', NAV_BACK_X, 0, NAV_BACK_W, NAVBAR_H, [
        ('name', 'btn_return'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:over:icon', 'ah_nav_back'), ('style:normal:icon', 'ah_nav_back'), ('style:pressed:icon', 'ah_nav_back_down')])
    img = 'ah_nav_play' if toggle or coverflow or more or songs or settings else 'ah_nav_np'   # a toggle / button makes Now Playing the capsule's right cap; else a disc
    player = Widget('button', NAV_PLAY_X, 0, NAV_PLAY_W, NAVBAR_H, [
        ('name', 'btn_backtoplayer'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', img + '_down'), ('style:normal:icon', img), ('style:over:icon', img)])
    nb.children = [lbl, ret, player]
    if toggle:
        icon = NAV_VIEW_ICON[toggle]
        nb.children.append(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', TOGGLE_NAME[toggle]), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)]))
    if settings:   # the Extras page's Settings button (patch/m1plus.c opens the Settings page on its tap)
        nb.children.append(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_settings'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', NAV_SETTINGS_ICON + '_down'), ('style:normal:icon', NAV_SETTINGS_ICON), ('style:over:icon', NAV_SETTINGS_ICON)]))
    if select:   # the Folders page's Select button (patch/folders.c shows it, as the capsule's left cap, below the root)
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_select'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_selectl_down'), ('style:normal:icon', 'pod_nav_selectl'), ('style:over:icon', 'pod_nav_selectl')])))
    if show_more:   # the Podcasts page's "..." (opens a bottom sheet): the capsule's left cap on the 214 slot, shown on the Show level and on the Shows level when Import is possible (patch/podcasts.c)
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_more'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_more_down'), ('style:normal:icon', 'pod_nav_more'), ('style:over:icon', 'pod_nav_more')])))
    if show_globe:   # the Podcasts page's globe (Apple Podcasts search, only while Podcast Search is on in Settings): the capsule's left cap, on the 168 slot with the "..." as its middle piece, or on the 214 slot beside Now Playing alone (patch/podcasts.c pg_nav moves it)
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_globe'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_globe_down'), ('style:normal:icon', 'pod_nav_globe'), ('style:over:icon', 'pod_nav_globe')])))
    if coverflow:
        nb.children.append(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_coverflow'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', NAV_CF_ICON + '_down'), ('style:normal:icon', NAV_CF_ICON), ('style:over:icon', NAV_CF_ICON)]))
    if more:   # the Playlists page's "..." menu button, in the Cover Flow button's place
        nb.children.append(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_more'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_more_down'), ('style:normal:icon', 'pod_nav_more'), ('style:over:icon', 'pod_nav_more')]))
    if songs:   # Search, Sort, Select: three pieces of the capsule that ends in Now Playing (x 131 .. 311, glass; docs/modules/navbar.md)
        for name, icon, x in SONGS_BUTTONS:
            nb.children.append(Widget('button', x, 0, NAV_VIEW_W, NAVBAR_H, [
                ('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)]))
    if songs:   # the artist's songs list (patch/songs.c shows it there only): the Cover Flow button, the capsule's left cap on Search's list slot (the Albums page's, NAV_CF_X); the toggle back to the covers
        nb.children.append(hidden(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_coverflow'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', NAV_CF_ICON + '_down'), ('style:normal:icon', NAV_CF_ICON), ('style:over:icon', NAV_CF_ICON)])))
    if songs:   # Recently Added's songs / albums toggle (patch/songs.c shows it there only; docs/modules/recent-albums.md): the Albums page's slot 214 and glyph, the capsule's third middle piece
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', TOGGLE_NAME['grid']), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_grid_down'), ('style:normal:icon', 'pod_nav_grid'), ('style:over:icon', 'pod_nav_grid')])))
    if artist_songs:   # Cover Flow's artist page (patch/coverflow.c shows it, makes Now Playing the right cap, and shortens the title, only there)
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [   # the capsule's left cap: opens our Songs page on the artist's songs
            ('name', 'btn_songs'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', NAV_SONGS_ICON + '_down'), ('style:normal:icon', NAV_SONGS_ICON), ('style:over:icon', NAV_SONGS_ICON)])))
    for child in nb.children:
        if child.type == 'button' and child.w == NAV_VIEW_W:
            child.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))
    return nb


SWITCH_W, SWITCH_H, SWITCH_MARGIN = 57, 28, 12   # the stock on/off switch image (sset_on / sset_off) and its right margin
UP_W = 50                                        # the Main Menu page's up arrow button, left of the switch


def switch_x(w): return w - SWITCH_MARGIN - SWITCH_W


def switch_image(name, w, h, on):
    """The stock on/off switch (systemset/powermanager_page.bin's img_switch*: an image of sset_on / sset_off, the
    themed toggle art). Insensitive: the row takes the tap. The payload swaps the image at run time."""
    return Widget('image', switch_x(w), (h - SWITCH_H) // 2, SWITCH_W, SWITCH_H, [
        ('name', name), ('image', 'sset_on' if on else 'sset_off'), ('draw_type', 'default'), ('sensitive', 'false')])


VALUE_W, VALUE_PX = 110, 19                      # a value row's grey value (Settings > Library > Album Order): right aligned, 12 px margin


def value_x(w): return w - SWITCH_MARGIN - VALUE_W


def value_label(name, w, h, english):
    """The value at the right of a value row, #AAAAAA like the library rows' second line. Insensitive: the row takes the tap.
    The payload sets it with widget_set_tr_text, so it follows the language."""
    lab = Widget('label', value_x(w), 0, VALUE_W, h, [('name', name), pod_i18n.text_prop(english), ('sensitive', 'false')])
    styled(lab, ('normal',), 'text_color', '#AAAAAA')
    styled(lab, ('normal',), 'font_size', str(VALUE_PX))
    styled(lab, ('normal',), 'text_align_h', 'right')
    styled(lab, ('normal',), 'text_align_v', 'middle')
    return lab


CHEV_X, CHEV_TEXT_END = 288, 278      # the shared list chevron's left edge (patch/offsets.inc LIST_CHEV_X) and where a row with one ends its text
CHEV_BTN_X = CHEV_X - 3               # the 13 px wide right_arrow image: the 10 px glyph is right aligned in it


def row_item(name, y, label, chevron, h=ROW_H, w=SCREEN_W, switch=None, value=None):
    """A row built like stock's scrolling rows (systemset_sysset_page_init @0x4adb7c): a list_item
    themed "list_item_style" holding an hscroll_label themed "srlabel_leftwhite21_style" (white,
    21 px, left; scrolls only while its row has focus, ellipsis) and, for navigating rows, the
    stock "right_arrow" image. Stock's own widget and theme styles, so the look matches the
    settings lists in every state and drags reach the scroll_view as in every stock list."""
    item = Widget('list_item', 0, y, w, h, [('name', name), ('style', 'list_item_style')])
    text_w = (switch_x(w) if switch else value_x(w) if value else (CHEV_TEXT_END if chevron else w - 12)) - 24
    item.children.append(Widget('hscroll_label', 24, 0, text_w, h, [
        ('style', 'srlabel_leftwhite21_style'), pod_i18n.text_prop(label), ('only_parent_focus', 'true'),
        ('ellipses', 'true'), ('yoyo', 'true'), ('loop', 'true')]))
    if chevron:
        item.children.append(Widget('image', CHEV_BTN_X, 0, 13, h - 1, [   # the shared list chevron: right_arrow's 13 x 22 canvas holds it right aligned, so its ink is x 288..298, centred above the hairline
            ('image', 'right_arrow'), ('draw_type', 'icon')]))
    if switch:   # switch = (widget name, state)
        item.children.append(switch_image(switch[0], w, h, switch[1]))
    if value:    # value = (widget name, English text)
        item.children.append(value_label(value[0], w, h, value[1]))
    return item


def label(name, x, y, w, h, text, size, colour, align='center'):
    lab = Widget('label', x, y, w, h, [('name', name), ('text', text)])
    styled(lab, ('normal',), 'text_color', colour)
    styled(lab, ('normal',), 'font_size', str(size))
    styled(lab, ('normal',), 'text_align_h', align)
    return lab


def hidden(w):
    """Start hidden *and* insensitive. This demo's AWTK hit test (widget_find_target_default
    0x6747d4) checks only enable and sensitive, never visible, so a merely hidden widget still
    swallows every touch over its rectangle; patch/coverflow.c keeps the two in step at runtime."""
    w.set('visible', 'false')
    w.set('sensitive', 'false')
    return w


# Cover Flow's page layout (tests and previews read these): the shelf is 168 px covers in a 320x276
# frame (patch/offsets.inc), the captions hscroll_labels in 16 px side margins that scroll a long
# title back and forth (stock Now Playing's info lines: loop, yoyo, a 3 s lull at each end) and
# centre one that fits. The block is centred in the 400 px under the navbar: the art's top
# (COVER_Y + CF_TOP = 120) and the artist line's bottom (380) are 70 px from the body's edges; the
# album line starts 4 px below the reflections (CF_TOP + ART_SIZE + CF_REFLECT = 225).
COVER_FRAME_H = 276              # CF_VIEW_H
COVER_Y = NAVBAR_H + 39          # view_covers: 89..365
ALBUM_Y, ALBUM_H = COVER_Y + 229, 34      # 318..352
ARTIST_Y, ARTIST_H = ALBUM_Y + ALBUM_H, 28   # 352..380
CAPTION_X = 16                   # side margins of the scrolling captions
CAPTION_LULL = '3000'            # ms at each end, as playing_page.bin's label_album


def cover_layout():
    """(frame y, album y, album h, artist y, artist h) of the cover page."""
    return COVER_Y, ALBUM_Y, ALBUM_H, ARTIST_Y, ARTIST_H


def scroll_caption(name, y, h, size, colour):
    """A caption as stock Now Playing's info lines (playing_page.bin label_album): an hscroll_label,
    centred, white or grey in every state, that loops back and forth (yoyo) with a lull at each end
    when its text is wider than the box and shows it centred when it fits; ellipses for the frames
    it is not scrolling. Insensitive: it lies over the frame's black rows, whose touch layer takes
    the touch (this AWTK hit-tests insensitive widgets through, hidden ones not)."""
    w = Widget('hscroll_label', CAPTION_X, y, SCREEN_W - 2 * CAPTION_X, h, [('name', name), ('text', '')])
    for st in ('normal', 'disable', 'focused'):
        styled(w, (st,), 'font_size', str(size))
        styled(w, (st,), 'text_color', colour)
        styled(w, (st,), 'text_align_h', 'center')
    for k, v in (('yoyo', 'true'), ('loop', 'true'), ('lull', CAPTION_LULL), ('ellipses', 'true'),
                 ('sensitive', 'false')):
        w.set(k, v)
    return w


def build_cover_page(page):
    """Cover Flow's page: the covers frame, the scrolling album and artist captions under the
    covers, and the first-run cache build's progress label and Cancel button. patch/coverflow.c
    fills view_covers with a stock slide_menu; the frame's size must match the CF_* constants in
    patch/offsets.inc."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title, artist_songs=True))
    fy, ay, ah, ry, rh = cover_layout()
    frame = Widget('view', 0, fy, SCREEN_W, COVER_FRAME_H, [('name', 'view_covers')])
    styled(frame, ('normal',), 'bg_color', '#000000')
    root.children.append(frame)
    root.children.append(scroll_caption('label_album', ay, ah, 22, '#FFFFFF'))
    root.children.append(scroll_caption('label_artist', ry, rh, 18, '#AAAAAA'))
    status = label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')
    root.children.append(hidden(status))
    cancel = Widget('button', 100, 260, 120, 46, [('name', 'btn_cancel'), ('enable', 'true'),
                                                  pod_i18n.text_prop('Cancel')])
    for st in ('normal', 'over', 'focused', 'disable', 'selected'):
        styled(cancel, (st,), 'bg_color', '#1E1E1E')
        styled(cancel, (st,), 'text_color', '#FFFFFF')
        styled(cancel, (st,), 'font_size', '20')
        styled(cancel, (st,), 'border_color', '#3A3A3A')
        styled(cancel, (st,), 'border_width', '1')
    styled(cancel, ('pressed',), 'bg_color', '#2A2A2A')
    styled(cancel, ('pressed',), 'text_color', '#FFFFFF')
    styled(cancel, ('pressed',), 'font_size', '20')
    root.children.append(hidden(cancel))
    return root


def stock_list(rows, scroll, top=NAVBAR_H):
    """The structure and properties of systemset/sysset_page.bin's list, the stock scrolling list:
    list_view (default_item_height, black in every state) > scroll_view (310 wide when a bar is
    there, the speed scales) + scroll_bar_m (10 px, max 1000) at the right."""
    list_h = CLIENT_H - top
    sv_w = SCREEN_W - 10 if scroll else SCREEN_W
    lv = Widget('list_view', 0, top, SCREEN_W, list_h, [
        ('name', 'pod_listview'), ('default_item_height', str(ROW_H))])
    for st in ('normal', 'disable', 'focused'):
        lv.set(f'style:{st}:bg_color', '#000000')
    for st in ('normal', 'disable', 'focused'):
        lv.set(f'style:{st}:border_color', '#00000000')
    lv.set('style:normal:border_width', '0')
    sv = Widget('scroll_view', 0, 0, sv_w, list_h, [
        ('name', 'pod_scrollview'), ('yspeed_scale', '1'), ('xspeed_scale', '1')])
    for i, r in enumerate(rows):
        chevron = r.action not in pod_pages.NO_CHEVRON_ACTIONS + pod_pages.SWITCH_ACTIONS + pod_pages.VALUE_ACTIONS   # rows that play, act in place, switch or show a value: no chevron
        switch = (f'pod_switch{i}', False) if r.action in pod_pages.SWITCH_ACTIONS else None   # the payload sets the state at open
        value = (f'pod_value{i}', pod_pages.VALUE_INIT[r.action]) if r.action in pod_pages.VALUE_ACTIONS else None   # ... and the value
        sv.children.append(row_item(f'pod_row{i}', i * ROW_H, r.label, chevron, ROW_H, sv_w, switch, value))
    lv.children = [sv]
    if scroll:   # stock's scroll bar, only when there is something to scroll
        lv.children.append(Widget('scroll_bar_m', sv_w, 0, 10, list_h,
                                  [('name', 'scroll_bar_m'), ('max', '1000')]))
    return lv



# The Albums page (patch/albums.c): a stock list (list_view > scroll_view) under the navbar whose one child, view_grid, paints the covers and titles itself.
# Its style carries the title text (16 px white, left, middle), which widget_prepare_text_style reads.
GRID_VIEW_H = CLIENT_H - NAVBAR_H     # patch/offsets.inc GRID_VIEW_H
GRID_TITLE_PX = 16
GRID_ALBUM_PX, GRID_ARTIST_PX = 18, 15   # the grid's album / artist text under each cover (white / #AAAAAA)
LIST_TITLE_PX, LIST_SUB_PX = 21, 18   # the list mode's album / artist text (the library rows': 21 px white, 18 px #AAAAAA)


def build_grid_page(page, toggle='list', coverflow=True, names=('albums_listview', 'albums_scrollview'), more=False):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title, toggle=toggle, coverflow=coverflow, more=more))
    lv = stock_list([], True)   # the library lists' structure: list_view > scroll_view 310 wide + scroll_bar_m. The mobile bar is not decoration: the list_view layouter makes the scroll_view yslidable only for it (0x60b1c8), scroll_view_create leaves it 0
    lv.set('name', names[0])
    sv = lv.children[0]
    sv.set('name', names[1])
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])   # the content: the payload sizes it to the whole library
    styled(grid, ('normal',), 'bg_color', '#000000')
    styled(grid, ('normal',), 'text_color', '#FFFFFF')
    styled(grid, ('normal',), 'font_size', str(GRID_TITLE_PX))
    styled(grid, ('normal',), 'text_align_h', 'left')
    styled(grid, ('normal',), 'text_align_v', 'middle')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/albums.c / playlists.c show it while yoffset > 0
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    # The two modes' text styles (patch/albums.c reads them with widget_prepare_text_style; never shown)
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, '#FFFFFF'), ('label_row_sub', LIST_SUB_PX, '#AAAAAA'),
                             ('label_grid_title', GRID_ALBUM_PX, '#FFFFFF'), ('label_grid_sub', GRID_ARTIST_PX, '#AAAAAA')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    return root


# The Show page's text styles (patch/podcasts.c; hidden labels the payload reads with widget_prepare_text_style and measures with widget_measure_text): name, px, colour, alignment.
# Colours as the approved design: the description #B8B8B8, the grey lines #AAAAAA, a played title #A6A6A6; the Latest Episode pill's label is dark on its white pill.
PS_STYLES = (('label_ps_name', 22, '#FFFFFF', 'center'), ('label_ps_sec', 16, '#B8B8B8', 'left'), ('label_ps_meta', 15, '#AAAAAA', 'left'), ('label_ps_head', 22, '#FFFFFF', 'left'),
             ('label_ps_date', 15, '#AAAAAA', 'left'), ('label_ps_ctitle', 20, '#FFFFFF', 'left'), ('label_ps_cdim', 20, '#A6A6A6', 'left'), ('label_ps_cdesc', 16, '#AAAAAA', 'left'),
             ('label_ps_pill', 16, '#FFFFFF', 'left'), ('label_ps_latest', 18, '#000000', 'left'), ('label_ps_latestw', 18, '#FFFFFF', 'left'),
             # the Shows page (round 2): the section headers (Continue Listening, Shows), the refresh line's white "Refresh", a Continue Listening item's title and its grey "35m left", the grid's title and grey line under each cover (the Albums grid's 18 / 15 px)
             ('label_ps_sech', 20, '#FFFFFF', 'left'), ('label_ps_line', 15, '#FFFFFF', 'left'), ('label_ps_stitle', 14, '#FFFFFF', 'left'), ('label_ps_sleft', 13, '#AAAAAA', 'left'),
             ('label_ps_gtitle', 18, '#FFFFFF', 'left'), ('label_ps_gsub', 15, '#AAAAAA', 'left'))
PS_TINT_NAME = 'img_ah_tint'   # the album page's tint gradient (ah_tint), a window sized insensitive image under everything; shown on the Show level once the cover's tone is set


def search_field():
    """The search level's field (patch/podcasts.c, docs/modules/podcasts.md "Search"): the keyboard page's field look as widgets of the content view (so it scrolls with the rows): a rounded #1C1C1E view, the
    magnifier, the grey hint and the white text (the payload sets the texts). Hidden and insensitive; a touch on it goes to the content view, which opens the keyboard."""
    o = OFFSETS
    f = kb_view('ps_field', o['PQ_FIELD_X'], o['PQ_FIELD_Y'], o['PQ_FIELD_W'], o['PQ_FIELD_H'], PK.KB_BG, o['PQ_FIELD_R'])
    mag = Widget('image', o['PQ_MAG_X'], (o['PQ_FIELD_H'] - o['PQ_MAG']) // 2, o['PQ_MAG'], o['PQ_MAG'], [('name', 'ps_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')])
    hint = label('ps_hint', o['PQ_TEXT_X'], 0, o['PQ_TEXT_W'], o['PQ_FIELD_H'], '', PK.FIELD_PX, PK.KB_GREY, 'left')
    text = label('ps_text', o['PQ_TEXT_X'], 0, o['PQ_TEXT_W'], o['PQ_FIELD_H'], '', PK.FIELD_PX, PK.KB_INK, 'left')
    for lab in (hint, text):
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
    clear = hidden(Widget('image', o['PQ_CLEAR_X'] + (o['PQ_CLEAR_W'] - o['PQ_CLEAR']) // 2, (o['PQ_FIELD_H'] - o['PQ_CLEAR']) // 2, o['PQ_CLEAR'], o['PQ_CLEAR'], [('name', 'ps_clear'), ('image', 'qk_clear'), ('draw_type', 'center')]))   # the keyboard page's clear disc (its touch is the payload's: PH_CLEAR)
    f.children = [mag, hint, text, clear]
    return hidden(f)


def build_podcasts_page(page):
    """The Podcasts page (patch/podcasts.c, docs/modules/podcasts.md): the Albums list mode's structure (a stock list holding the one content view the payload paints) under the
    plain navbar (Back, title, Now Playing). The payload paints the levels in view_grid; label_status is its empty-state hint (two lines); the hidden labels are the text styles.
    The Show level is tinted from the cover as the album page is (docs/modules/album-page.md "Cover tint"): the window's colour is set by the payload and img_ah_tint, the gradient
    over it, is shown; so the list, its scroll view and the content view are transparent (on every level: over the black window they look as before)."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(hidden(Widget('image', 0, 0, SCREEN_W, CLIENT_H, [('name', PS_TINT_NAME), ('image', 'ah_tint'), ('draw_type', 'default'), ('clickable', 'false')])))   # first: under everything
    root.children.append(navbar(page.title, show_more=True, show_globe=True))
    root.children[1].children.append(selall_button())   # the select mode's navbar text (the Playlists page's)
    lv = stock_list([], True)
    lv.set('name', 'podcasts_listview')
    sv = lv.children[0]
    sv.set('name', 'podcasts_scrollview')
    for w in (lv, sv):
        for st in ('normal', 'disable', 'focused'): w.set(f'style:{st}:bg_color', '#00000000')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])   # the content: the payload sizes it to the level's rows
    big = Widget('label', OFFSETS['PP_TITLE_X'], 0, SCREEN_W - 2 * OFFSETS['PP_TITLE_X'], OFFSETS['PP_TITLE_H'], [('name', 'pg_big'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])   # the large heading of the Shows, Downloads and Subscriptions levels (the Songs page's): a child of the content, so it scrolls and is clipped with it
    styled(big, ('normal',), 'text_color', '#FFFFFF')
    styled(big, ('normal',), 'font_size', str(OFFSETS['PP_TITLE_PX']))
    styled(big, ('normal',), 'text_align_h', 'left')
    styled(big, ('normal',), 'text_align_v', 'middle')
    grid.children = [big, search_field()]
    styled(grid, ('normal',), 'bg_color', '#00000000')
    styled(grid, ('normal',), 'text_color', '#FFFFFF')
    styled(grid, ('normal',), 'font_size', str(GRID_TITLE_PX))
    styled(grid, ('normal',), 'text_align_h', 'left')
    styled(grid, ('normal',), 'text_align_v', 'middle')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/podcasts.c shows it while yoffset > 0 (not on the Show level, which paints a fade in the page's colour)
    status = hidden(label('label_status', 20, 180, SCREEN_W - 40, 90, '', 18, '#FFFFFF'))
    styled(status, ('normal',), 'text_align_v', 'middle')
    root.children.append(status)
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, '#FFFFFF'), ('label_row_sub', LIST_SUB_PX, '#AAAAAA')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    for name, px, colour, align in PS_STYLES:
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if name == 'label_ps_latest': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', '#FFFFFF')   # the dark label of the white pill: the contrast scan reads the label's own background
        root.children.append(lab)
    bar = select_bar('pg_bar', 'pg_bar_line', [('pg_del', OFFSETS['SG_PILL_X0'], 'Delete', 'sg_trash', OFFSETS['PL_BAR_PILL_W']), ('pg_unsubp', OFFSETS['SG_PILL_X0'], 'Unsubscribe', 'sg_trash', OFFSETS['PL_BAR_PILL_W'])])   # the select mode's bar: one Delete pill across it, as the Playlists page's; the Subscriptions page's Unsubscribe is a second pill in the same place (the payload shows one of them)
    hidden(bar.children[-1])
    root.children.append(bar)
    root.children.extend(podcasts_sheet())   # the two bottom sheets' one widget set: above the list, the bar and the navbar
    root.children.extend(podcasts_dialog())   # last: above everything
    return root


# The Show page's bottom sheets (the show's "..." and an episode's), in the style of Now Playing's More sheet (docs/modules/playmore.md): the page dimmed (the Playlists menu's scrim), the
# 320 px glass from the bottom of the window (pc_sheet5 .. pc_sheet1, a picture for each number of rows: tools/mod_icons.py PC_SHEETS; the payload sets the image
# and the card's height and place for the rows it shows), PM_ROW_H rows, each a button (transparent, 6 % white pressed) with its 20 px glyph at x PS_SHEET_ICON_X, the label from
# PS_SHEET_TEXT_X and, for the two rows that have one, the grey value right aligned to PS_SHEET_VALUE_R; a 1 px hairline child on the top of every row but the first (the payload shows it).
# One widget set serves both sheets: the thirteen rows are fixed (glyph and label each), the payload shows and places the ones the sheet needs. Everything starts hidden and insensitive.
PS_SHEET_ROWS = (('speed', 'pc_ic_speed', 'Playback Speed', True, False), ('refresh', 'pc_ic_refresh', 'Refresh Feed', True, False), ('select', 'pc_ic_select', 'Select Episodes', False, False),
                 ('markall', 'pc_ic_check', 'Mark All as Played', False, False), ('unsub', 'pc_ic_unsub', 'Unsubscribe', False, True),
                 ('dl', 'pc_ic_down', 'Download', False, False), ('rm', 'pc_ic_trash', 'Remove Download', False, False),
                 ('mark', 'pc_ic_check', 'Mark as Played', False, False), ('unmark', 'pc_ic_undo', 'Mark as Unplayed', False, False),
                 ('import', 'pc_ic_import', 'Import from Card', False, False), ('delplayed', 'pc_ic_trash', 'Delete Played Episodes', False, False),
                 ('export', 'pod_ic_export', 'Export OPML', False, False), ('save', 'pod_ic_save', 'Save Episode', False, False))   # id, glyph, label, has a value, red; import is the Shows level's sheet, select (relabelled Select, or Select Shows) and delplayed the Downloads page's, select and export the Subscriptions page's, save (relabelled Unsave Episode when it is saved) an episode's
PS_SHEET_ICON_X, PS_SHEET_TEXT_X, PS_SHEET_VALUE_R, PS_SHEET_VALUE_W, PS_SHEET_GAP = (OFFSETS[k] for k in ('PS_SHEET_ICON_X', 'PS_SHEET_TEXT_X', 'PS_SHEET_VALUE_R', 'PS_SHEET_VALUE_W', 'PS_SHEET_GAP'))   # patch/offsets.inc
PS_SHEET_RED = '#FF6B6B'
PS_SHEET_PX = 18   # the labels (Now Playing's More sheet: 18 px)


def podcasts_sheet():
    """(scrim, card) of the Show page's sheets: the card at its tallest (five rows, pc_sheet5), at the bottom of the window."""
    return sheet_widgets('pg_sh', PS_SHEET_ROWS, 5)


def sheet_widgets(prefix, sheet_rows, tallest):
    """(scrim, card) of a bottom sheet with the fixed rows `sheet_rows` (id, glyph, label, has a value, red), named <prefix>_scrim, <prefix>_card, <prefix>_<id> (+ _ic, _tx, _vl, _hr); the card's
    height the tallest of its pictures (pc_sheet<tallest>)."""
    from mod_icons import PC_SHEET_PX
    o = OFFSETS
    rh, rows = o['PM_ROW_H'], len(sheet_rows)
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', f'{prefix}_scrim'), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', '#FFFFFF')
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    card = hidden(Widget('view', 0, CLIENT_H - tallest * rh, SCREEN_W, tallest * rh, [('name', f'{prefix}_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', f'pc_sheet{tallest}')
        styled(card, (st,), 'bg_image_draw_type', 'default')
        styled(card, (st,), 'border_width', '0')
    for i, (rid, icon, text, value, red) in enumerate(sheet_rows):
        item = hidden(Widget('button', 0, i * rh, SCREEN_W, rh, [('name', f'{prefix}_{rid}'), ('enable', 'true')]))
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', '#FFFFFF')
            styled(item, (st,), 'border_width', '0')
            styled(item, (st,), 'border_color', '#00000000')
        item.children.append(Widget('image', PS_SHEET_ICON_X, (rh - PC_SHEET_PX) // 2, PC_SHEET_PX, PC_SHEET_PX, [
            ('name', f'{prefix}_{rid}_ic'), ('draw_type', 'default'), ('image', icon), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', PS_SHEET_TEXT_X, 0, PS_SHEET_VALUE_R - PS_SHEET_TEXT_X, rh, [
            ('name', f'{prefix}_{rid}_tx'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PS_SHEET_PX))
            styled(lab, (st,), 'text_color', PS_SHEET_RED if red else '#FFFFFF')
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
            styled(lab, (st,), 'margin_left', '0')
            styled(lab, (st,), 'margin_right', '0')
        item.children.append(lab)
        if value:
            val = Widget('hscroll_label', PS_SHEET_VALUE_R - PS_SHEET_VALUE_W, 0, PS_SHEET_VALUE_W, rh, [
                ('name', f'{prefix}_{rid}_vl'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
            for st in ('normal', 'disable', 'focused'):
                styled(val, (st,), 'font_size', str(PS_SHEET_PX))
                styled(val, (st,), 'text_color', '#AAAAAA')
                styled(val, (st,), 'text_align_h', 'right')
                styled(val, (st,), 'text_align_v', 'middle')
                styled(val, (st,), 'margin_left', '0')
                styled(val, (st,), 'margin_right', '0')
            item.children.append(val)
        hair = Widget('view', 0, 0, SCREEN_W, 1, [('name', f'{prefix}_{rid}_hr'), ('sensitive', 'false')])
        for st in STATES: styled(hair, (st,), 'bg_color', PL_HAIR)
        item.children.append(hair)
        card.children.append(item)
    assert len(card.children) == rows
    return scrim, card


# The refresh dialog of the Podcasts page (patch/podcasts.c pg_dlg_*): the Playlists menu's pieces. A full-client scrim (dimmed as that menu's, it takes every touch: the dialog is
# modal) and a card in that menu's glass (pl_glass, patch3_x, PD_CARD_H = its 200 px), centred: the title, the current show's name (the payload sets it; ellipsis), the bar (a track and
# a fill whose width the payload sets), the "2 of 5" line (or "Cancelling..."), and a Cancel row filling the card's last 50 px with the menu rows' hairline above it and the pressed 6 % white.
# Everything starts hidden and insensitive; the texts inside are insensitive too (only the Cancel row takes touches).
PD_CARD_W, PD_CARD_H, PD_BAR_W, PD_BAR_H = (OFFSETS[k] for k in ('PD_CARD_W', 'PD_CARD_H', 'PD_BAR_W', 'PD_BAR_H'))
PD_MARGIN = (PD_CARD_W - PD_BAR_W) // 2
PD_TITLE_Y, PD_TITLE_H, PD_TITLE_PX = 16, 28, 20
PD_NAME_Y, PD_NAME_H, PD_NAME_PX = 54, 26, 17
PD_BAR_Y = 94
PD_COUNT_Y, PD_COUNT_H, PD_COUNT_PX = 106, 26, 15
PD_CANCEL_PX = 18
PD_TRACK_RGB, PD_FILL_RGB, PD_NAME_RGB, PD_COUNT_RGB, PD_CANCEL_RGB = '#FFFFFF33', '#EBEBEB', '#EBEBEB', '#AAAAAA', '#FFFFFF'   # neutral: no accent colour


def podcasts_dialog(prefix='pod_pd', title='Refreshing Podcasts', big=False):
    """(scrim, card) of the refresh dialog."""
    ty, th, tpx, ny, nh, npx, by, bh, cy, ch, cpx, row = (14, 30, 20, 48, 26, 18, 92, 6, 104, 28, 20, 48) if big else (PD_TITLE_Y, PD_TITLE_H, PD_TITLE_PX, PD_NAME_Y, PD_NAME_H, PD_NAME_PX, PD_BAR_Y, PD_BAR_H, PD_COUNT_Y, PD_COUNT_H, PD_COUNT_PX, PL_ROW_H)   # big: the Software Update popup, larger type, a 6 px bar, the stock dialog's 48 px button row
    assert PD_CARD_H == OFFSETS['PL_MENU_ROWS'] * PL_ROW_H
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', prefix + '_scrim'), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', '#FFFFFF')
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    card = hidden(Widget('view', (SCREEN_W - PD_CARD_W) // 2, (CLIENT_H - PD_CARD_H) // 2, PD_CARD_W, PD_CARD_H, [('name', prefix + '_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', PL_GLASS)
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    def text(name, y, h, px, colour, text_prop):
        lab = Widget('hscroll_label', PD_MARGIN, y, PD_BAR_W, h, [('name', name), text_prop, ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', colour)
            styled(lab, (st,), 'text_align_h', 'center')
            styled(lab, (st,), 'text_align_v', 'middle')
        return lab
    card.children.append(text(prefix + '_title', ty, th, tpx, '#FFFFFF', pod_i18n.text_prop(title)))
    card.children.append(text(prefix + '_name', ny, nh, npx, PD_NAME_RGB, ('text', '')))
    for name, w, rgb in ((prefix + '_track', PD_BAR_W, PD_TRACK_RGB), (prefix + '_fill', 1, PD_FILL_RGB)):
        bar = Widget('view', PD_MARGIN, by, w, bh, [('name', name), ('sensitive', 'false')])
        for st in STATES:
            styled(bar, (st,), 'bg_color', rgb)
            styled(bar, (st,), 'border_width', '0')
            styled(bar, (st,), 'round_radius', str(bh // 2))
        card.children.append(bar)
    card.children.append(text(prefix + '_count', cy, ch, cpx, PD_COUNT_RGB, ('text', '')))
    cancel = Widget('button', 0, PD_CARD_H - row, PD_CARD_W, row, [('name', prefix + '_cancel'), ('enable', 'true'), pod_i18n.text_prop('Cancel')])
    for st in STATES:
        styled(cancel, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
        styled(cancel, (st,), 'text_color', PD_CANCEL_RGB)
        styled(cancel, (st,), 'font_size', str(cpx if big else PD_CANCEL_PX))
        styled(cancel, (st,), 'border', 'top')
        styled(cancel, (st,), 'border_width', '1')
        styled(cancel, (st,), 'border_color', PL_HAIR)
    card.children.append(cancel)
    return scrim, card


# The Playlists page (patch/playlists.c): the Albums grid's structure (a stock list holding the one content view that paints the cells) under a navbar
# with a "..." button at the toggle's place, and the popup menu: a full-window scrim (a tap outside closes it; it dims the page as Now Playing's
# More sheet's highlighter does) and a card under the button in that sheet's glass (pl_glass: tools/mod_icons.py, all four corners rounded, drawn
# patch3_x so the payload can narrow the card to the language: the image's middle third stretches, its gradient is vertical only) of PL_ROW_H rows
# filling it, each a button (transparent, the sheet's 6 % white pressed, its 13 % white hairline above every row but the first) with a 20 px glyph
# (tools/mod_icons.py PL_MENU_ICONS) and its label, as the sheet's rows. All of it starts hidden and insensitive; the payload shows the scrim and
# the card together.
STATES = ('normal', 'pressed', 'over', 'focused', 'disable', 'selected')
PL_CARD_RIGHT, PL_CARD_Y, PL_ROW_H, PL_CARD_R, PL_ICON_X, PL_TEXT_X, PL_TEXT_R, PL_CARD_MIN, PL_CARD_MAX = (OFFSETS[k] for k in (
    'PL_CARD_RIGHT', 'PL_CARD_Y', 'PL_ROW_H', 'PL_CARD_R', 'PL_ICON_X', 'PL_TEXT_X', 'PL_TEXT_R', 'PL_CARD_MIN', 'PL_CARD_MAX'))
PL_CARD_H = OFFSETS['PL_MENU_ROWS'] * PL_ROW_H
PL_LABEL_PX = 18
PL_GLASS = 'pl_glass'
PL_DIM = '#00000082'          # the sheet's highlight="default(alpha=130)" (tools/mod_lists.py edit_playmore)
PL_PRESSED, PL_HAIR = '#FFFFFF10', '#FFFFFF22'   # the sheet's rows (tools/mod_lists.py PM_PRESSED, PM_HAIR)


def playlist_menu():
    """(scrim, card): the popup menu of the Playlists page, the card at its widest (PL_CARD_MAX); the payload narrows it."""
    assert len(pod_pages.PLAYLIST_MENU) == OFFSETS['PL_MENU_ROWS']
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', 'pl_scrim'), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', '#FFFFFF')
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    card = hidden(Widget('view', PL_CARD_RIGHT - PL_CARD_MAX, PL_CARD_Y, PL_CARD_MAX, PL_CARD_H, [('name', 'pl_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', PL_GLASS)
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    from mod_icons import PL_MENU_ICONS, PL_MENU_PX as PL_ICON
    for i, (text, (icon, _)) in enumerate(zip(pod_pages.PLAYLIST_MENU, PL_MENU_ICONS)):
        item = Widget('button', 0, i * PL_ROW_H, PL_CARD_MAX, PL_ROW_H, [('name', f'pl_item{i}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', '#FFFFFF')
            styled(item, (st,), 'border', 'top' if i else 'none')
            styled(item, (st,), 'border_width', '1' if i else '0')
            styled(item, (st,), 'border_color', PL_HAIR if i else '#00000000')
        item.children.append(Widget('image', PL_ICON_X, (PL_ROW_H - PL_ICON) // 2, PL_ICON, PL_ICON, [
            ('name', f'pl_icon{i}'), ('draw_type', 'default'), ('image', icon), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', PL_TEXT_X, 0, PL_CARD_MAX - PL_TEXT_X - PL_TEXT_R, PL_ROW_H, [
            ('name', f'pl_label{i}'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PL_LABEL_PX))
            styled(lab, (st,), 'text_color', '#FFFFFF')
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        card.children.append(item)
    return scrim, card


RM_KEYS = ('Play Next', 'Play After', 'Add to Playlist')   # the track rows' "..." menu (patch/rowmenu.c): the rows in order, each with its glyph (tools/mod_icons.py RM_MENU_ICONS)
RM_GLASS = 'rm_glass'                                       # the sheet's glass: Now Playing's More sheet's pane, three rows high, top corners only (tools/mod_icons.py GLASS_ROWMENU)
RM_ICON_X, RM_TEXT_X, RM_TEXT_R = 14, 48, 22                  # Now Playing's More sheet's rows (pod_tape: the 24 px glyph at x 14, the label from x 48, ending at 298)
RM_LABEL_PX = 18


def row_menu():
    """(scrim, card): the track rows' "..." menu, shared by the album page and the Songs page (patch/rowmenu.c, docs/modules/rowmenu.md): a bottom sheet as Now Playing's More sheet
    (tools/mod_lists.py edit_playmore): the window's dim scrim, a full-width card at the window's foot in that sheet's glass, three PM_ROW_H rows filling it, each a transparent button
    (6 % white pressed) with a bare 24 px glyph and the 18 px white label, the sheet's 13 % white hairline above every row but the first. Rows: Play Next, Play After, Add to Playlist.
    Hidden AND insensitive until the payload shows them; nothing is placed or sized at open. Put it last in the window, above the list, the bars and the navbar."""
    from mod_icons import RM_MENU_ICONS, BARE_PX
    rows, rh = OFFSETS['RM_ROWS'], OFFSETS['PM_ROW_H']
    assert len(RM_KEYS) == rows
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', 'rm_scrim'), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', '#FFFFFF')
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    card = hidden(Widget('view', 0, CLIENT_H - rows * rh, SCREEN_W, rows * rh, [('name', 'rm_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', RM_GLASS)
        styled(card, (st,), 'bg_image_draw_type', 'default')
        styled(card, (st,), 'border_width', '0')
    for i, (text, (icon, _)) in enumerate(zip(RM_KEYS, RM_MENU_ICONS)):
        item = Widget('button', 0, i * rh, SCREEN_W, rh, [('name', f'rm_item{i}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', '#FFFFFF')
            styled(item, (st,), 'border', 'top' if i else 'none')
            styled(item, (st,), 'border_width', '1' if i else '0')
            styled(item, (st,), 'border_color', PL_HAIR if i else '#00000000')
        item.children.append(Widget('image', RM_ICON_X, (rh - BARE_PX) // 2, BARE_PX, BARE_PX, [
            ('name', f'rm_icon{i}'), ('draw_type', 'default'), ('image', icon), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', RM_TEXT_X, 0, SCREEN_W - RM_TEXT_X - RM_TEXT_R, rh, [
            ('name', f'rm_label{i}'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(RM_LABEL_PX))
            styled(lab, (st,), 'text_color', '#FFFFFF')
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        card.children.append(item)
    return scrim, card


def build_playlists_page(page):
    root = build_grid_page(page, toggle='list', coverflow=False, more=True, names=('playlists_listview', 'playlists_scrollview'))
    root.children[0].children.append(selall_button())   # the navbar's select mode text (the menu's Delete Playlists starts select mode: patch/playlists.c)
    root.children.append(select_bar('pl_bar', 'pl_bar_line', [('pl_del', OFFSETS['SG_PILL_X0'], 'Delete', 'sg_trash', OFFSETS['PL_BAR_PILL_W'])]))
    root.children.extend(playlist_menu())   # last: above the list, the bar and the navbar
    return root


# The Songs page (patch/songs.c, docs/modules/songs.md): the Albums structure (a stock list holding the one content view that paints the rows, headers and
# pinned header itself) under the glass navbar (Back, the small title, Search / Sort / Select / Now Playing), with the page's own widgets: in the content view the
# large title and the Play / Shuffle pills (real flat buttons: they scroll with the list); over the list the rail (a view of its own, outside the scroll_view, so a
# touch on it never starts a drag) and the letter bubble (insensitive); the sort card (a scrim and the Playlists card's glass) and, hidden until select mode, the
# bar with the Add to playlist and Delete pills and the navbar's Select All text. Everything that is shown later starts hidden AND insensitive.
SG_TITLE_PX, SG_HDR_PX, SG_RAIL_PX, SG_BUBBLE_PX, SG_PILL_PX = 32, 20, 12, 56, 18
SG_PILL_RGB, SG_PILL_DOWN_RGB, SG_PILL_OFF_RGB = '#1E1E1E', '#333333', '#141414'   # flat: no glass
SG_PILL_PRESS_RGB = '#333335'   # the Play / Shuffle pills pressed: palette.ROLE_PRESS_PILL, one blue level off #333333 so the accent can find it (the select bars' pills keep #333333)
SG_FOOT_RGB = '#9C9C9C'   # the song count under the last row: the album page's meta line colour (mod_ipodrows.META_COLOR)
SG_CARD_ROWS = len(pod_pages.SORT_MENU)


RAIL_INK_MIN = 64   # a pixel is "ink" from 25 % coverage up (the antialiased fringe of the outline's bbox is not)


def rail_ink(font, px, ch):
    """(first, last + 1) of the rows and of the columns of ch's ink, y from the top of the 12 px text box (the baseline is int(ascender * scale) below it) and x from the pen."""
    g = font.glyph(ch)
    x0, y0, w, h, rows = font.bitmap(g, px)
    ys = [i for i, r in enumerate(rows) if max(r) >= RAIL_INK_MIN]
    xs = [i for i in range(w) if max(r[i] for r in rows) >= RAIL_INK_MIN]
    base = font.baseline(px)
    return (base + y0 + ys[0], base + y0 + ys[-1] + 1), (x0 + xs[0], x0 + xs[-1] + 1)


def rail_metrics(font_path):
    """What the payload needs of the tree's own font to align the rail's dots, disc and letters (patch/songs.c sg_on_rail_paint, docs/modules/songs.md "Alignment"):
    (ink2, dx). AWTK's canvas_draw_text_in_rect puts a text of measured width lw (the truncated advances + 1 px per glyph) at rect.x + (rect.w - lw) / 2 (integer),
    and the text box of a 13 px item is (13 - 12) / 2 = 0 below the item's top with the baseline int(ascender * scale) lower. ink2 = twice the height of the cap
    ink's centre within the item (A..Z share the cap height; the 'H' gives it), so dots and discs are placed from it. dx[k] (k 0 for '#', 1..26 for A..Z) is the
    integer shift of the letter's rect, in a SG_RAIL_TEXT_W wide rect centred on the dot's x, that puts the ink's centre on that x within half a pixel."""
    from stb_raster import StbFont
    from awtk_text import Ttf, StbText
    o = OFFSETS
    px, font, st = SG_RAIL_PX, StbFont(font_path), StbText(Ttf(font_path), SG_RAIL_PX)
    top = (o['SG_RAIL_PITCH'] - px) // 2
    (a, b), _ = rail_ink(font, px, 'H')
    ink2 = 2 * top + a + b
    dx = []
    for ch in '#ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        _, (lo, hi) = rail_ink(font, px, ch)
        e = o['SG_RAIL_TEXT_W'] / 2 - ((o['SG_RAIL_TEXT_W'] - st.layout(ch)[1]) // 2 + (lo + hi) / 2)   # how far the ink's centre is left of the rect's centre
        d = int(e)
        if abs(e - d) > 0.5: d += 1 if e > 0 else -1
        dx.append(d)
    return ink2, dx
# the sort card: flat (the toolbar alone is glass), the Playlists menu's rhythm (PL_ROW_H rows, no padding, right edge PL_CARD_RIGHT, y PL_CARD_Y, radius PL_CARD_R)
SG_CARD_W, SG_LABEL_X = 268, 16
SG_CARD_X = PL_CARD_RIGHT - SG_CARD_W
SG_CARD_H = SG_CARD_ROWS * PL_ROW_H
SG_TICK_W = 18
SG_GLASS = 'sg_glass'    # the card's glass: the Playlists card's pane, 250 px high (tools/mod_icons.py GLASS_SORT)
SG_SELALL_X, SG_SELALL_W = 208, 104     # the select mode's "Select All" text, right aligned to a 8 px margin


def sg_pill(name, x, y, text, icon, ink='#FFFFFF', w=None, down=SG_PILL_DOWN_RGB):
    """A flat pill: the button's fill with round_radius (the stock dialogs' buttons do the same), the glyph and the 18 px label, which the payload centres as a pair."""
    o = OFFSETS
    b = Widget('button', x, y, w or o['SG_PILL_W'], o['SG_PILL_H'], [('name', name), ('enable', 'true'), pod_i18n.text_prop(text)])
    for st in STATES:
        styled(b, (st,), 'bg_color', down if st == 'pressed' else SG_PILL_OFF_RGB if st == 'disable' else SG_PILL_RGB)
        styled(b, (st,), 'text_color', '#666666' if st == 'disable' else ink)
        styled(b, (st,), 'font_size', str(SG_PILL_PX))
        styled(b, (st,), 'border_width', '0')
        styled(b, (st,), 'border_color', '#00000000')
        styled(b, (st,), 'round_radius', str(o['SG_PILL_R']))
        styled(b, (st,), 'icon', icon)
    return b


def sort_card():
    """(scrim, card): the sort order card under the Sort button, in the Playlists menu's glass (sg_glass, patch3_x, scrim, pressed fill and hairlines of playlist_menu; PL_ROW_H rows, no padding):
    the five stock labels and, at the right of each, the tick image that is shown on the current order."""
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', 'sg_scrim'), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', '#FFFFFF')
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    card = hidden(Widget('view', SG_CARD_X, PL_CARD_Y, SG_CARD_W, SG_CARD_H, [('name', 'sg_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', SG_GLASS)
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    for i, key in enumerate(pod_pages.SORT_MENU):
        item = Widget('button', 0, i * PL_ROW_H, SG_CARD_W, PL_ROW_H, [('name', f'sg_item{i}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', '#FFFFFF')
            styled(item, (st,), 'border', 'top' if i else 'none')
            styled(item, (st,), 'border_width', '1' if i else '0')
            styled(item, (st,), 'border_color', PL_HAIR if i else '#00000000')
        lab = Widget('hscroll_label', SG_LABEL_X, 0, SG_CARD_W - 2 * SG_LABEL_X - SG_TICK_W - 8, PL_ROW_H, [
            ('name', f'sg_label{i}'), pod_i18n.text_prop(pod_i18n.english(key)), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PL_LABEL_PX))
            styled(lab, (st,), 'text_color', '#FFFFFF')
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        item.children.append(hidden(Widget('image', SG_CARD_W - SG_LABEL_X - SG_TICK_W, (PL_ROW_H - SG_TICK_W) // 2, SG_TICK_W, SG_TICK_W, [
            ('name', f'sg_tick{i}'), ('image', 'sg_tick'), ('draw_type', 'default')])))
        card.children.append(item)
    return scrim, card


def selall_button():
    """The select mode's Select All: a flat text button at the navbar's right (hidden and insensitive until select mode: the Songs and Playlists pages)."""
    sa = hidden(Widget('button', SG_SELALL_X, 0, SG_SELALL_W, NAVBAR_H, [('name', 'btn_selall'), ('enable', 'true'), pod_i18n.text_prop('Select All')]))
    for st in STATES:   # select mode's text button: flat, right aligned
        styled(sa, (st,), 'bg_color', '#00000000')
        styled(sa, (st,), 'text_color', '#777777' if st == 'pressed' else '#FFFFFF')
        styled(sa, (st,), 'font_size', '18')
        styled(sa, (st,), 'border_width', '0')
        styled(sa, (st,), 'border_color', '#00000000')
        styled(sa, (st,), 'text_align_h', 'right')
        styled(sa, (st,), 'margin_right', '8')
    return sa


def select_bar(name, line_name, pills):
    """The select mode's bottom bar (hidden until select mode): black, a #222222 top hairline, flat pills [(name, x, text, glyph, width)]."""
    o = OFFSETS
    bar = hidden(Widget('view', 0, CLIENT_H - o['SG_BAR_H'], SCREEN_W, o['SG_BAR_H'], [('name', name)]))
    for st in STATES: styled(bar, (st,), 'bg_color', '#000000')
    line = Widget('view', 0, 0, SCREEN_W, 1, [('name', line_name), ('sensitive', 'false')])
    for st in STATES: styled(line, (st,), 'bg_color', '#222222')
    py = (o['SG_BAR_H'] - o['SG_PILL_H']) // 2
    bar.children = [line] + [sg_pill(n, x, py, text, glyph, w=w) for n, x, text, glyph, w in pills]
    return bar


def azlist_labels():
    """The hidden text styles of the A-Z furniture (patch/azlist.c, shared by the Songs and Artists pages): the header letter, the rail letter and the touched rail letter."""
    out = []
    for name, px, colour, align in (('label_hdr', SG_HDR_PX, '#FFFFFF', 'left'), ('label_rail', SG_RAIL_PX, '#EEEEEC', 'center'), ('label_rail_on', SG_RAIL_PX, '#000000', 'center')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))   # text styles only (widget_prepare_text_style); never shown
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if name == 'label_rail_on': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', '#EEEEEC')   # the letter on the disc: black on the accent (the contrast scan reads the label's own background)
        out.append(lab)
    return out


def azlist_rail():
    """(rail, bubble): the rail (a transparent view of its own, outside the scroll_view, so a touch on it never starts a drag; the payload paints the letters) and the letter bubble."""
    o = OFFSETS
    rail = Widget('view', o['SG_RAIL_X'], NAVBAR_H, o['SG_RAIL_W'], GRID_VIEW_H, [('name', 'sg_rail')])
    for st in STATES: styled(rail, (st,), 'bg_color', '#00000000')
    bubble = hidden(Widget('view', (SCREEN_W - o['SG_BUBBLE']) // 2, NAVBAR_H + (GRID_VIEW_H - o['SG_BUBBLE']) // 2, o['SG_BUBBLE'], o['SG_BUBBLE'], [('name', 'sg_bubble')]))
    for st in STATES:   # the look tools/mod_lists.py gives the stock view_letter: a dark rounded square with a white letter
        styled(bubble, (st,), 'bg_color', '#262626')
        styled(bubble, (st,), 'round_radius', '14')
        styled(bubble, (st,), 'border_color', '#3A3A3A')
        styled(bubble, (st,), 'border_width', '1')
    letter = Widget('label', 0, 0, o['SG_BUBBLE'], o['SG_BUBBLE'], [('name', 'sg_bubble_letter'), ('text', ''), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(letter, (st,), 'text_color', '#FFFFFF')
        styled(letter, (st,), 'font_size', str(SG_BUBBLE_PX))
        styled(letter, (st,), 'text_align_h', 'center')
        styled(letter, (st,), 'text_align_v', 'middle')
    bubble.children.append(letter)
    return [rail, bubble]


def build_artists_page(page):
    """The Artists / Genres / Composers page (patch/artists.c, docs/modules/artists.md): the Songs page's structure (a stock list holding one content view that paints the
    rows, the section letters and the pinned header; the rail and the bubble beside it; the large title in the content view, the small one in the navbar once it has scrolled
    away) under the navbar with the Artist / Album Artist switch. No pills, no select mode, no sort card."""
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, toggle='artist')
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'artists_listview')
    sv = lv.children[0]
    sv.set('name', 'artists_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = Widget('label', o['SG_TITLE_X'], 0, 250, o['SG_TITLE_H'], [('name', 'ar_title'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
    styled(title, ('normal',), 'text_color', '#FFFFFF')
    styled(title, ('normal',), 'font_size', str(SG_TITLE_PX))
    styled(title, ('normal',), 'text_align_h', 'left')
    styled(title, ('normal',), 'text_align_v', 'middle')
    grid.children = [title]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/artists.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    lab = hidden(label('label_row_title', 0, 0, 10, 10, '', LIST_TITLE_PX, '#FFFFFF', 'left'))   # the row text style (the stock srlabel_leftwhite21_style's 21 px white)
    styled(lab, ('normal',), 'text_align_v', 'middle')
    root.children.append(lab)
    root.children.extend(azlist_labels())
    root.children.extend(azlist_rail())
    return root


def search_field_widget():
    """The Search page's field (kb_field with the magnifier, hint, text, caret and clear button; patch/keyboard.c keyboard_attach finds them by name); the Radio page has the same."""
    field = kb_view('kb_field', PS.SE_FIELD_X, PS.SE_FIELD_Y, PS.SE_FIELD_W, PS.SE_FIELD_H, PS.FIELD_RGB, PS.SE_FIELD_R)
    field.set('sensitive', 'true')   # the clear button inside it needs it, and a tap on the field brings the keyboard back
    mag = Widget('image', PS.SE_MAG_X, (PS.SE_FIELD_H - PK.FIELD_MAG) // 2, PK.FIELD_MAG, PK.FIELD_MAG, [('name', 'kb_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')])
    hint = label('kb_hint', PS.SE_TEXT_X, 0, PS.SE_TEXT_W, PS.SE_FIELD_H, '', PS.FIELD_PX, PS.FIELD_HINT, 'left')
    text = label('kb_text', PS.SE_TEXT_X, 0, PS.SE_TEXT_W, PS.SE_FIELD_H, '', PS.FIELD_PX, PS.FIELD_INK, 'left')
    for lab in (hint, text):
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
    caret = kb_view('kb_caret', PS.SE_TEXT_X, PS.SE_CARET_Y, PK.CARET_W, PK.CARET_H, PK.KB_INK)
    clear = hidden(Widget('button', PS.SE_FIELD_W - PS.SE_CLEAR_W, 0, PS.SE_CLEAR_W, PS.SE_FIELD_H, [('name', 'kb_clear'), ('enable', 'true'), ('style', 'img_btn_style'),
                   ('style:pressed:icon', 'qk_clear'), ('style:normal:icon', 'qk_clear'), ('style:over:icon', 'qk_clear')]))
    field.children = [mag, hint, text, caret, clear]
    return field


def build_search_page(page):
    """The Search page (patch/search.c, docs/modules/search.md; the numbers are tools/pod_search.py's, parsed from patch/search.h): the Apple Music search screen. A rounded field with the
    keyboard's own field widgets (kb_field with the magnifier, hint, text, caret and clear button), the round X button (btn_return), a row of chips (se_chips: the payload paints the texts and
    moves the selected chip's pill se_chip_hl), the line under it, a stock list holding one content view that paints the rows, and the keyboard's pad, strip and pop-up at the bottom. Hidden
    labels carry the text styles; label_title (hidden) is the page's title, which the asset tests read from every page."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    lv = stock_list([], True, top=PS.SE_LIST_Y)
    lv.set('name', 'se_listview')
    sv = lv.children[0]
    sv.set('name', 'se_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, PS.SE_LIST_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(Widget('view', 0, PS.SE_SEP_Y, SCREEN_W, 1, [('name', 'se_sep'), ('sensitive', 'false')]))
    styled(root.children[-1], STATES, 'bg_color', PS.SEP_RGB)
    chips = Widget('view', 0, PS.SE_CHIPS_Y, SCREEN_W, PS.SE_CHIPS_H, [('name', 'se_chips'), ('enable', 'true')])
    for st in STATES:
        styled(chips, (st,), 'bg_color', '#000000')
        styled(chips, (st,), 'border_width', '0')
    chips.children = [kb_view('se_chip_hl', PS.SE_CHIP_X, PS.SE_CHIP_Y, 80, PS.SE_CHIP_H, PS.CHIP_ON_RGB, PS.SE_CHIP_R)]
    root.children.append(chips)
    field = search_field_widget()
    root.children.append(field)
    root.children.append(Widget('button', PS.SE_CLOSE_X, PS.SE_CLOSE_Y, PS.SE_CLOSE_W, PS.SE_CLOSE_H, [
        ('name', 'btn_return'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:over:icon', 'se_close'), ('style:normal:icon', 'se_close'), ('style:pressed:icon', 'se_close_down')]))
    root.children.append(hidden(label('label_status', 10, 150, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    root.children.append(hidden(label('label_title', 0, 0, 200, 22, '', 16, '#FFFFFF', 'left')))
    root.children[-1].set(*pod_i18n.text_prop(page.title))
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB), ('label_chip', PS.SE_CHIP_PX, PS.CHIP_INK), ('label_chip_on', PS.SE_CHIP_PX, PS.CHIP_ON_INK)):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'center' if name.startswith('label_chip') else 'left'))   # text styles only (widget_prepare_text_style); never shown
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if name == 'label_chip_on': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', PS.CHIP_ON_RGB)   # the dark text is on the selected pill (the contrast scan reads the label's own background)
        root.children.append(lab)
    root.children += keyboard_pad_widgets()
    return root


def build_subsonic_page(page):
    """English-only Navidrome labels with stock list/grid controls."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar('Navidrome'))
    btn = Widget('button', 8, NAVBAR_H + 4, 112, 44, [('name', 'sb_connect'), ('enable', 'true')])
    btn.set('style', 'btn_tablerow_style')
    styled(btn, STATES, 'text_color', '#FFFFFF')
    styled(btn, STATES, 'font_size', '16')
    server_label = label('sb_connect_label', 8, 0, 82, 44, '', 14, '#FFFFFF', 'left')
    server_label.set('text', 'Server')
    server_label.set('sensitive', 'false')
    dot = Widget('view', 97, 17, 10, 10, [('name', 'sb_connected_dot'), ('sensitive', 'false')])
    styled(dot, ('normal',), 'bg_color', '#8E8E93')
    styled(dot, ('normal',), 'round_radius', '5')
    btn.children.extend([server_label, dot])
    root.children.append(btn)
    for name, x, icon in (('sb_search', 210, 'pod_ic_search'), ('sb_sync', 266, 'pod_sb_sync')):
        btn = Widget('button', x, NAVBAR_H + 4, 44, 44, [('name', name), ('enable', 'true'), ('style', 'img_btn_style')])
        btn.children.append(Widget('image', 6, 6, 32, 32, [('name', f'{name}_icon'), ('image', icon), ('draw_type', 'icon'), ('sensitive', 'false')]))
        root.children.append(btn)
    tabs = (('sb_tracks', 12, 116, 'Songs', 'pod_ic_navidrome'),
            ('sb_dsd', 138, 116, 'DSD Downloads', 'pod_sb_dsd'))
    for name, x, width, text, icon in tabs:
        btn = Widget('button', x, NAVBAR_H + 50, width, 44, [('name', name), ('enable', 'true')])
        btn.set('style', 'btn_tablerow_style')
        btn.children.append(Widget('image', 5, 10, 24, 24, [('name', f'{name}_icon'), ('image', icon), ('draw_type', 'icon'), ('sensitive', 'false')]))
        mark = Widget('view', 0, 41, width, 3, [('name', f'{name}_mark'), ('visible', 'false'), ('sensitive', 'false')])
        styled(mark, ('normal',), 'bg_color', '#EEEEEC')
        caption = label(f'{name}_label', 32, 0, width - 34, 44, '', 13, '#FFFFFF', 'left')
        caption.set('text', text)
        caption.set('style', 'btn_tablerow_style')
        caption.set('sensitive', 'false')
        btn.children.extend([caption, mark])
        root.children.append(btn)
    view_btn = Widget('button', 266, NAVBAR_H + 50, 42, 44, [('name', 'sb_view'), ('enable', 'true'), ('style', 'img_btn_style')])
    view_btn.children.append(Widget('image', 8, 8, 26, 26, [('name', 'sb_view_icon'), ('image', 'pod_nav_grid'), ('draw_type', 'icon'), ('sensitive', 'false')]))
    root.children.append(view_btn)
    status = label('sb_status', 12, NAVBAR_H + 96, 296, 22, '', 14, '#AAAAAA', 'left')
    status.set('text', 'Connect to browse your music')
    root.children.append(status)
    progress = Widget('view', 12, NAVBAR_H + 118, 296, 6,
                      [('name', 'sb_download_progress'), ('visible', 'false'), ('sensitive', 'false')])
    styled(progress, ('normal',), 'bg_color', '#333333')
    fill = Widget('view', 0, 0, 1, 6,
                  [('name', 'sb_download_fill'), ('visible', 'false'), ('sensitive', 'false')])
    styled(fill, ('normal',), 'bg_color', '#EEEEEC')
    progress.children.append(fill)
    root.children.append(progress)
    lv = stock_list([], True, top=NAVBAR_H + 124)
    lv.h = 276
    lv.set('name', 'sb_listview')
    sv = lv.children[0]
    sv.h = 276
    lv.children[1].h = 276
    sv.set('name', 'sb_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, 6 * 210, [('name', 'sb_rows')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    for i in range(6):
        item = Widget('list_item', 0, i * 52, SCREEN_W, 52, [('name', f'sb_row{i}'), ('style', 'list_item_style'), ('enable', 'true')])
        art = Widget('image', 4, 4, 44, 44, [('name', f'sb_art{i}'), ('draw_type', 'scale_auto'), ('sensitive', 'false')])
        title = Widget('hscroll_label', 58, 2, 152, 22, [('name', f'sb_title{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        styled(title, STATES, 'text_color', '#FFFFFF')
        styled(title, ('normal',), 'font_size', str(LIST_TITLE_PX))
        sub = Widget('hscroll_label', 58, 29, 152, 19, [('name', f'sb_sub{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        styled(sub, STATES, 'text_color', '#AAAAAA')
        styled(sub, ('normal',), 'font_size', str(LIST_SUB_PX))
        actions = []
        for action, x, icon in (('download', 272, 'pod_sb_download'),):
            button = Widget('button', x, 4, 42, 44, [('name', f'sb_row_{action}{i}'), ('enable', 'true'), ('sensitive', 'false'), ('style', 'img_btn_style')])
            button.children.append(Widget('image', 9, 10, 24, 24, [('name', f'sb_row_{action}_icon{i}'), ('image', icon), ('draw_type', 'icon'), ('sensitive', 'false')]))
            actions.append(button)
        gitem = Widget('view', (i % 2) * 160, (i // 2) * 210, 160, 204, [('name', f'sb_grid_row{i}'), ('enable', 'true')])
        g_art = Widget('image', 12, 4, 136, 136, [('name', f'sb_grid_art{i}'), ('draw_type', 'scale_auto'), ('sensitive', 'false')])
        g_title = Widget('hscroll_label', 6, 142, 148, 19, [('name', f'sb_grid_title{i}'), ('text', ''), ('ellipses', 'true'), ('sensitive', 'false')])
        styled(g_title, STATES, 'text_color', '#FFFFFF')
        styled(g_title, ('normal',), 'font_size', '14')
        g_sub = Widget('hscroll_label', 6, 161, 148, 17, [('name', f'sb_grid_sub{i}'), ('text', ''), ('ellipses', 'true'), ('sensitive', 'false')])
        styled(g_sub, STATES, 'text_color', '#AAAAAA')
        styled(g_sub, ('normal',), 'font_size', '12')
        g_actions = []
        for action, x, icon in (('download', 59, 'pod_sb_download'),):
            button = Widget('button', x, 177, 42, 36, [('name', f'sb_grid_{action}{i}'), ('enable', 'true'), ('sensitive', 'false'), ('style', 'img_btn_style')])
            button.children.append(Widget('image', 9, 6, 24, 24, [('name', f'sb_grid_{action}_icon{i}'), ('image', icon), ('draw_type', 'icon'), ('sensitive', 'false')]))
            g_actions.append(button)
        gitem.children = [g_art, g_title, g_sub, *g_actions]
        item.children = [art, title, sub, *actions]
        grid.children.append(item)
        grid.children.append(gitem)
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(hidden(label('label_title', 0, 0, 200, 22, '', 16, '#FFFFFF', 'left')))
    return root


def build_songs_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, songs=True)
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    nb.children.append(selall_button())
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'songs_listview')
    sv = lv.children[0]
    sv.set('name', 'songs_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = Widget('label', o['SG_TITLE_X'], 0, 250, o['SG_TITLE_H'], [('name', 'sg_title'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
    styled(title, ('normal',), 'text_color', '#FFFFFF')
    styled(title, ('normal',), 'font_size', str(SG_TITLE_PX))
    styled(title, ('normal',), 'text_align_h', 'left')
    styled(title, ('normal',), 'text_align_v', 'middle')
    foot = label('sg_foot', o['SG_HDR_X'], 0, SCREEN_W - 2 * o['SG_HDR_X'], o['SG_FOOT_TEXT_H'], '', o['SG_FOOT_PX'], SG_FOOT_RGB, 'left')   # the song count: the payload sets the text and puts it under the last row
    foot.set('sensitive', 'false')
    styled(foot, ('normal',), 'text_align_v', 'middle')
    # a playlist's header (patch/songs.c, class 0xff13): the name and the count, centred under the mosaic the payload paints; the payload moves the pills down and
    # shows these two (hidden and insensitive here, like every decoration it shows later)
    hname = hidden(label('sg_hname', o['PH_NAME_X'], o['PH_NAME_Y'], o['PH_NAME_W'], o['PH_NAME_H'], '', 22, '#FFFFFF', 'center'))
    styled(hname, ('normal',), 'text_align_v', 'middle')
    grid.children = [title, hname, sg_pill('btn_play', o['SG_PILL_X0'], o['SG_PILL_Y'], 'Play', 'sg_play', down=SG_PILL_PRESS_RGB),
                     sg_pill('btn_shuffle', o['SG_PILL_X1'], o['SG_PILL_Y'], 'Shuffle', 'sg_shuffle', down=SG_PILL_PRESS_RGB), foot]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/songs.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    for name, px, colour, align in (('label_row_title', LIST_TITLE_PX, '#FFFFFF', 'left'), ('label_row_sub', LIST_SUB_PX, '#AAAAAA', 'left'),
                                    ('label_grid_title', GRID_ALBUM_PX, '#FFFFFF', 'left'), ('label_grid_sub', GRID_ARTIST_PX, '#AAAAAA', 'left')):   # the last two: Recently Added's album grid
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))   # text styles only (widget_prepare_text_style); never shown
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    root.children.extend(azlist_labels())
    root.children.extend(azlist_rail())
    root.children.append(select_bar('sg_bar', 'sg_bar_line', [('sg_add', o['SG_PILL_X0'], 'Add to Playlist', 'sg_listplus', o['SG_BAR_PILL_W']),
                                                              ('sg_del', o['SG_BAR_PILL_X1'], 'Delete', 'sg_trash', o['SG_BAR_PILL_W'])]))
    root.children.extend(sort_card())   # above the list, the rail and the select bar
    root.children.extend(row_menu())   # last: above everything (the track rows' "..." menu, patch/rowmenu.c)
    return root


# The album page (patch/albumpage.c, docs/modules/album-page.md; the numbers are patch/offsets.inc AH_* and AB_*): the stock album page's design with our own glass controls. The list is the
# whole 450 px window (list_view > scroll_view + the mobile scroll bar, the library lists' structure) holding one content view, view_grid, that paints the cover, the tracks and
# their press fill itself and holds the header's widgets: the title, the artist and the "year . N tracks" line (centred hscroll_labels that scroll a long text), the Shuffle disc (a
# button, its picture the disc), the Play all pill (a button, its picture the pill) with its glyph (an image) and its text (a label) over it, which the payload centres as a pair.
# The window's colour is the cover's tone (the payload sets it); the gradient image img_ah_tint, first in the window, darkens it from the top (the stock page's), and the list over it is
# transparent. The glass controls are the window's last child, so they paint and take touches over the rows: Back, Select | Now Playing as one capsule (the genre songs list's), and
# in select mode the all / none toggle, Add, Delete and Cancel in the places the stock builder gave them. Two hidden labels carry the rows' text styles (the number, the title; the playing row's number is the ah_wave image); label_title (hidden) is the page's title for the i18n and asset tests.
AB_STYLES = (('label_row_num', 'right', '#AAAAAA'), ('label_row_title', 'left', '#FFFFFF'))   # the stock rows' 19 px number (the grey line's colour) and title (white)
AB_ROW_PX = 19
AB_META = (('ab_title', 'AH_TITLE_Y', 'AH_TITLE_H', 22, '#FFFFFF'), ('ab_artist', 'AH_ARTIST_Y', 'AH_ARTIST_H', 18, '#AAAAAA'), ('ab_meta', 'AH_META_Y', 'AH_META_H', 15, '#9C9C9C'))   # srlabel_ah{title,artist,meta}_style
AB_FOOT_RGB = '#AAAAAA'   # the footer's grey: the artist line's (not the meta line's #9C9C9C)
AB_PLAY_TEXT_W = OFFSETS['AB_PLAY_TEXT_W']   # the English "Play all" at 18 px, where the payload cannot measure it; the payload centres the pair for the language


def ab_nav_button(name, x, w, rest, down=None, hide=False):
    b = Widget('button', x, 0, w, NAVBAR_H, [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                                             ('style:pressed:icon', down or rest), ('style:normal:icon', rest), ('style:over:icon', rest)])
    if w == NAV_VIEW_W: b.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))
    return hidden(b) if hide else b


def album_navbar(page):
    """The glass controls of the album page, the window's last children: Back, the capsule Select | Now Playing (Select the left cap, Now Playing the right: the genre songs list's),
    and the select mode's toggle, Add, Delete and Cancel (hidden until select mode). They are the window's own children, not a bar view's: a view over the list would take every touch
    in its band (this AWTK's hit test never descends into an insensitive container), and a drag that starts between the discs must scroll the list."""
    o = OFFSETS
    title = hidden(Widget('label', NAV_TITLE_X, 14, NAV_VIEW_X - NAV_TITLE_X, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))   # never shown: the page has no title
    return [title,
            ab_nav_button('btn_return', NAV_BACK_X, NAV_BACK_W, 'ah_nav_back', 'ah_nav_back_down'),
            ab_nav_button('btn_select', NAV_VIEW_X, NAV_VIEW_W, 'pod_nav_selectl', 'pod_nav_selectl_down'),
            ab_nav_button('btn_backtoplayer', NAV_PLAY_X, NAV_PLAY_W, 'ah_nav_play', 'ah_nav_play_down'),
            ab_nav_button('btn_selall', o['AB_SELALL_X'], o['AB_SELALL_W'], 'ah_nav_unsel', 'ah_nav_unsel_down', hide=True),
            ab_nav_button('sg_add', o['AB_ADD_X'], o['AB_BTN_W'], 'ah_nav_add', 'ah_nav_add_down', hide=True),
            ab_nav_button('sg_del', o['AB_DEL_X'], o['AB_BTN_W'], 'ah_nav_del', 'ah_nav_del_down', hide=True),
            ab_nav_button('btn_cancel', o['AB_CANCEL_X'], o['AB_BTN_W'], 'ah_nav_cancel', 'ah_nav_cancel_down', hide=True)]


def build_album_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(Widget('image', 0, 0, SCREEN_W, CLIENT_H, [('name', PS_TINT_NAME), ('image', 'ah_tint'), ('draw_type', 'default'), ('clickable', 'false'), ('sensitive', 'false')]))   # first: under everything
    lv = stock_list([], True, top=0)
    lv.set('name', 'songs_listview')
    sv = lv.children[0]
    sv.set('name', 'songs_scrollview')
    for w in (lv, sv):
        for st in ('normal', 'disable', 'focused'): w.set(f'style:{st}:bg_color', '#00000000')   # the window's colour (the cover's tone) and the gradient show through
    grid = Widget('view', 0, 0, SCREEN_W, o['AH_WIN_H'], [('name', 'view_grid')])   # the content: the payload sizes it to the header and the tracks
    styled(grid, ('normal',), 'bg_color', '#00000000')
    kids = []
    for name, y, h, px, colour in AB_META:
        lab = Widget('hscroll_label', o['AH_TEXT_X'], o[y], o['AH_TEXT_W'], o[h], [('name', name), ('text', ''), ('sensitive', 'false'), ('yoyo', 'true'), ('loop', 'true'), ('lull', CAPTION_LULL), ('ellipses', 'true')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', colour)
            styled(lab, (st,), 'text_align_h', 'center')
        kids.append(lab)
    kids.append(ab_button('btn_shuffle', o['AH_SHUF_X'], o['AH_SHUF_W'], 'ah_shuffle', 'ah_shuffle_down'))
    kids.append(ab_button('btn_play', o['AH_PLAY_X'], o['AH_PLAY_W'], 'ah_pill', 'ah_pill_down'))
    pair = o['AH_PILL_GLYPH'] + o['AH_PILL_GAP'] + AB_PLAY_TEXT_W
    gx = o['AH_PLAY_X'] + (o['AH_PLAY_W'] - pair) // 2
    kids.append(Widget('image', gx, o['AH_BTN_Y'] + (o['AH_BTN_H'] - o['AH_PILL_GLYPH']) // 2, o['AH_PILL_GLYPH'], o['AH_PILL_GLYPH'], [('name', 'ab_glyph'), ('image', 'ah_play'), ('draw_type', 'center'), ('sensitive', 'false')]))
    foot = hidden(label('ab_foot', o['AB_NUM_X'], 0, SCREEN_W - o['AB_NUM_X'] - o['AB_FOOT_R'], o['AB_FOOT_TEXT_H'], '', o['AB_FOOT_PX'], AB_FOOT_RGB, 'left'))   # the track count and the duration under the last row: the payload sets the text and the place, and shows it once the duration is known
    styled(foot, ('normal',), 'text_align_v', 'middle')
    kids.append(foot)
    grid.children = kids
    sv.children.append(grid)
    root.children.append(lv)
    play_text = hidden(Widget('label', 0, 0, 10, 10, [('name', 'ab_play_text'), pod_i18n.text_prop('Play all')]))   # the pill's text style and its translated text; the payload paints the text over the pill
    for st in ('normal', 'pressed', 'disable', 'focused'):
        styled(play_text, (st,), 'font_size', '18')
        styled(play_text, (st,), 'text_color', '#141414')
        styled(play_text, (st,), 'text_align_h', 'left')
        styled(play_text, (st,), 'text_align_v', 'middle')
        styled(play_text, (st,), 'bg_color', '#FFFFFF')   # the dark text of the white pill: the contrast scan reads the label's own background
    root.children.append(play_text)
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    for name, align, colour in AB_STYLES:
        lab = hidden(label(name, 0, 0, 10, 10, '', AB_ROW_PX, colour, align))   # text styles only (widget_prepare_text_style); never shown
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    root.children.extend(album_navbar(page))   # the glass controls paint and take touches over the list
    root.children.extend(row_menu())   # last: the track rows' "..." menu (patch/rowmenu.c) covers the navbar too
    return root


def ab_button(name, x, w, rest, down):
    o = OFFSETS
    return Widget('button', x, o['AH_BTN_Y'], w, o['AH_BTN_H'], [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                                                                 ('style:pressed:icon', down), ('style:normal:icon', rest), ('style:over:icon', rest)])


# The Queue page (patch/queuepage.c, docs/modules/queue.md; the numbers are patch/offsets.inc QP_*): the play queue in the album page's structure. The list is the whole 450 px window
# holding one content view, view_queue, that paints the rows (the Songs page's) and holds the header's widgets: the playing track's title and artist (hscroll_labels), the Shuffle and
# Repeat buttons (the Songs page's flat pills, icon only), the section line "Queue" with the song count at its right. The cover is painted by the payload. The window is black; the
# glass Back is the window's last child, over the rows.
QP_HEAD_PX, QP_EMPTY_PX = 20, 16
QP_EMPTY_RGB = '#9C9C9C'
QP_CLEAR_PX, QP_CLEAR_RGB, QP_CLEAR_DOWN_RGB = 17, '#9C9C9C', '#7A7A7A'   # the Clear text button: neutral grey, dimmer while pressed
QP_OFF_RGB, QP_OFF_DOWN_RGB = '#2C2C2E', '#3A3A3D'   # a mode button that is off (the payload sets the lit look: #C8C8C8, pressed #A8A8A8, with the dark glyph); patch/offsets.inc QP_PILL_*; pressed #3A3A3D is palette.ROLE_PRESS_QPILL (one blue level off #3A3A3C)


def qp_button(name, x, icon):
    """An icon-only flat button (the Songs page's pill without its label): the glyph is centred by the button's own style."""
    o = OFFSETS
    b = Widget('button', x, o['QP_PILL_Y'], o['QP_PILL_W'], o['SG_PILL_H'], [('name', name), ('enable', 'true')])
    for st in STATES:
        styled(b, (st,), 'bg_color', QP_OFF_DOWN_RGB if st == 'pressed' else QP_OFF_RGB)
        styled(b, (st,), 'border_width', '0')
        styled(b, (st,), 'border_color', '#00000000')
        styled(b, (st,), 'round_radius', str(o['SG_PILL_R']))
        styled(b, (st,), 'icon', icon)
    return b


def queue_navbar(page):
    title = hidden(Widget('label', NAV_TITLE_X, 14, NAV_VIEW_X - NAV_TITLE_X, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))   # never shown: the section line is the title
    return [title,
            ab_nav_button('btn_return', NAV_BACK_X, NAV_BACK_W, 'ah_nav_back', 'ah_nav_back_down')]


def build_queue_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    lv = stock_list([], True, top=0)
    lv.set('name', 'queue_listview')
    sv = lv.children[0]
    sv.set('name', 'queue_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, o['QP_WIN_H'], [('name', 'view_queue')])   # the content: the payload sizes it to the header and the rows
    styled(view, ('normal',), 'bg_color', '#000000')
    kids = []
    for name, y, h, px, colour in (('qp_title', 'QP_TITLE_Y', 'QP_TITLE_H', 20, '#FFFFFF'), ('qp_artist', 'QP_ARTIST_Y', 'QP_ARTIST_H', 16, '#AAAAAA')):
        lab = Widget('hscroll_label', o['QP_TEXT_X'], o[y], o['QP_TEXT_W'], o[h], [('name', name), ('text', ''), ('sensitive', 'false'), ('yoyo', 'true'), ('loop', 'true'), ('lull', CAPTION_LULL), ('ellipses', 'true')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', colour)
            styled(lab, (st,), 'text_align_h', 'left')
        kids.append(lab)
    kids.append(qp_button('btn_shuffle', o['QP_PILL_X0'], 'sg_shuffle'))
    kids.append(qp_button('btn_repeat', o['QP_PILL_X1'], 'sg_repeat'))
    head = Widget('label', o['SG_HDR_X'], o['QP_HEAD_Y'], 310 - o['SG_HDR_X'], o['QP_HEAD_H'], [('name', 'qp_head'), pod_i18n.text_prop('Queue'), ('sensitive', 'false')])
    for prop, v in (('text_color', '#FFFFFF'), ('font_size', str(QP_HEAD_PX)), ('text_align_h', 'left'), ('text_align_v', 'middle')): styled(head, ('normal',), prop, v)
    empty = hidden(Widget('label', o['SG_HDR_X'], o['QP_TOP'] + o['QP_EMPTY_Y'], 310 - o['SG_HDR_X'], o['QP_EMPTY_H'], [('name', 'qp_empty'), pod_i18n.text_prop('No upcoming songs')]))   # shown by the payload when nothing follows
    for prop, v in (('text_color', QP_EMPTY_RGB), ('font_size', str(QP_EMPTY_PX)), ('text_align_h', 'left'), ('text_align_v', 'middle')): styled(empty, ('normal',), prop, v)
    clear = hidden(Widget('button', o['QP_CLEAR_X'], o['QP_CLEAR_Y'], o['QP_CLEAR_W'], o['QP_CLEAR_H'], [('name', 'btn_qclear'), ('enable', 'true'), pod_i18n.text_prop('Clear')]))   # shown by the payload while songs follow
    for st in STATES:   # a flat text button, right aligned to x 310
        styled(clear, (st,), 'bg_color', '#00000000')
        styled(clear, (st,), 'text_color', QP_CLEAR_DOWN_RGB if st == 'pressed' else QP_CLEAR_RGB)
        styled(clear, (st,), 'font_size', str(QP_CLEAR_PX))
        styled(clear, (st,), 'border_width', '0')
        styled(clear, (st,), 'border_color', '#00000000')
        styled(clear, (st,), 'text_align_h', 'right')
        styled(clear, (st,), 'margin_right', '0')
    kids += [head, empty, clear]
    view.children = kids
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, '#FFFFFF'), ('label_row_sub', LIST_SUB_PX, '#AAAAAA')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))   # text styles only (widget_prepare_text_style); never shown
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    root.children.extend(queue_navbar(page))   # last: the glass controls paint and take touches over the list
    return root


# The Daily Mix page (patch/dailymix.c dp_*, docs/modules/dailymix.md "The page"; tools/pod_dailymix.py DP_* and patch/offsets.inc carry the numbers): no navbar. The list is the
# whole 450 px window (list_view > scroll_view + the mobile scroll bar, the library lists' structure) holding one content view, view_dm, that paints the art, the texts and the
# songs itself (as the Albums page's view_grid) and holds the three widgets that need images or touches: the Shuffle disc, the white Play pill and the pill's dark play glyph
# (insensitive: the pill takes the tap). A floating glass back disc (btn_return, the window's last child: fixed, over the list) is the only control outside the list.
# Seven hidden, insensitive labels carry the text styles (the payload sets their colours from the tint). label_title (hidden) is the page's title: the i18n and asset tests
# read it from every page; nothing shows it. The window, the list and the view are black here: the payload sets the tint on all of them (black is the fallback).
DP_STYLES = (('label_dp_title', 'DP_TITLE_PX', '#FFFFFF', 'center'), ('label_dp_sub', 'DP_SUB_PX', '#FFFFFF', 'center'), ('label_dp_upd', 'DP_UPD_PX', '#FFFFFF', 'center'),
             ('label_dp_desc', 'DP_DESC_PX', '#FFFFFF', 'left'), ('label_dp_play', 'DP_PLAY_PX', '#FFFFFF', 'left'), ('label_dp_row', 'DP_ROW_PX', '#FFFFFF', 'left'),
             ('label_dp_artist', 'DP_ARTIST_PX', '#FFFFFF', 'left'))
DP_PLAY_PX, DP_ROW_PX, DP_ARTIST_PX = 18, LIST_TITLE_PX, LIST_SUB_PX


def build_dailymix_page(page):
    import pod_dailymix as D
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    lv = stock_list([], True, top=0)
    lv.set('name', 'dp_listview')
    sv = lv.children[0]
    sv.set('name', 'dp_scrollview')
    styled(sv, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    view = Widget('view', 0, 0, SCREEN_W, D.DP_VIEW_H, [('name', 'view_dm')])   # the content: the payload sizes it to the header and the songs
    styled(view, ('normal',), 'bg_color', '#000000')
    view.children = [
        Widget('button', D.DP_SHUF_X, D.DP_BTN_Y, D.DP_SHUF_W, D.DP_BTN_H, [
            ('name', 'btn_dp_shuffle'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'ah_shuffle_down'), ('style:normal:icon', 'ah_shuffle'), ('style:over:icon', 'ah_shuffle')]),
        Widget('button', D.DP_PLAY_X, D.DP_BTN_Y, D.DP_PLAY_W, D.DP_BTN_H, [
            ('name', 'btn_dp_play'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'dp_pill_down'), ('style:normal:icon', 'dp_pill'), ('style:over:icon', 'dp_pill')]),
        Widget('image', D.DP_PLAY_X + (D.DP_PLAY_W - D.DP_PILL_GLYPH) // 2, D.DP_BTN_Y + (D.DP_BTN_H - D.DP_PILL_GLYPH) // 2, D.DP_PILL_GLYPH, D.DP_PILL_GLYPH, [
            ('name', 'img_dp_glyph'), ('image', 'dp_play'), ('draw_type', 'center'), ('sensitive', 'false')]),
        Widget('button', D.DP_ADD_X, D.DP_BTN_Y, D.DP_ADD_W, D.DP_BTN_H, [   # saves the mix as a stock playlist (Shuffle's disc mirrored, a plus)
            ('name', 'btn_dp_add'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'dp_add_down'), ('style:normal:icon', 'dp_add'), ('style:over:icon', 'dp_add')])]
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(Widget('button', D.DP_BACK_X, D.DP_BACK_Y, D.DP_BACK_BTN, D.DP_BACK_BTN, [
        ('name', 'btn_return'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', 'dp_back_down'), ('style:normal:icon', 'dp_back'), ('style:over:icon', 'dp_back')]))
    for name, px, colour, align in DP_STYLES:
        lab = hidden(label(name, 0, 0, 10, 10, '', globals()[px] if px in globals() else getattr(D, px), colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    root.children.append(hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)])))
    return root


# The iPod page (patch/ipod.c, docs/modules/ipod.md; the numbers are patch/offsets.inc IP_*): a fullscreen window (the lock screen's `fullscreen = true`, so the stock status bar is not drawn and
# the window is 320 x 480) in the wheel's body colour. ipod_screen (320 x 240) is painted by the payload in its own EVT_AFTER_PAINT and takes no touch (insensitive); ipod_wheel
# (220 x 220, the touch target: the payload does the circle's hit test and grabs the touch) holds the wheel picture as an insensitive image child. Ten hidden, insensitive labels
# only carry the text styles. label_title (hidden) is the page's title for the i18n and asset tests.
IP_STYLES = (('label_ip_row', 18, '#000000', 'left'), ('label_ip_sel', 18, '#FFFFFF', 'left'), ('label_ip_title', 16, '#000000', 'left'),
             ('label_ip_small', 16, '#666666', 'left'), ('label_ip_subsel', 16, '#FFFFFF', 'left'), ('label_ip_np1', 18, '#000000', 'left'), ('label_ip_np2', 16, '#666666', 'left'), ('label_ip_time', 15, '#000000', 'right'),
             ('label_ip_val', 16, '#0C62D2', 'left'), ('label_ip_np3', 14, '#666666', 'left'))


def build_ipod_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#C6C9CE')
    screen = Widget('view', 0, 0, o['IP_W'], o['IP_SCREEN_H'], [('name', 'ipod_screen'), ('sensitive', 'false')])
    styled(screen, ('normal',), 'bg_color', '#FFFFFF')
    wheel = Widget('view', o['IP_WHEEL_X'], o['IP_WHEEL_Y'], o['IP_WHEEL_D'], o['IP_WHEEL_D'], [('name', 'ipod_wheel')])
    wheel.children = [Widget('image', 0, 0, o['IP_WHEEL_D'], o['IP_WHEEL_D'], [('name', 'ipod_wheel_img'), ('image', 'ipod_wheel'), ('draw_type', 'default'), ('sensitive', 'false')])]
    root.children = [screen, wheel]
    # the style labels sit in two hidden, insensitive views whose background is the colour the text is drawn on (the theme scan reads a label's contrast against it)
    light = hidden(Widget('view', 0, 0, 10, 10, [('name', 'ip_styles_light')])); styled(light, ('normal',), 'bg_color', '#FFFFFF')
    blue = hidden(Widget('view', 0, 0, 10, 10, [('name', 'ip_styles_blue')])); styled(blue, ('normal',), 'bg_color', '#0C62D2')
    for name, px, colour, align in IP_STYLES:
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        (blue if name in ('label_ip_sel', 'label_ip_subsel') else light).children.append(lab)
    blue.children.append(hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)])))
    root.children += [light, blue]
    return root


# The Tape page (patch/tape.c, docs/modules/tape.md): a fullscreen window (320 x 480; the picture is landscape, turned into it by the payload) in the surface colour behind the cassette,
# one view over the whole window (tape_view: the touch target, painted by the payload in its own EVT_AFTER_PAINT) and a hidden, insensitive label that only carries the font.
# label_title (hidden) is the page's title for the i18n and asset tests.
def build_tape_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#111112')
    view = Widget('view', 0, 0, 320, 480, [('name', 'tape_view')])
    styled(view, ('normal',), 'bg_color', '#111112')
    holder = hidden(Widget('view', 0, 0, 10, 10, [('name', 'tp_styles')])); styled(holder, ('normal',), 'bg_color', '#111112')
    lab = hidden(label('label_tp_font', 0, 0, 10, 10, '', 16, '#FFFFFF', 'left')); styled(lab, ('normal',), 'text_align_v', 'middle')
    holder.children = [lab, hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))]
    root.children = [view, holder]
    return root


# The Vinyl page (patch/vinyl.c, docs/modules/vinyl.md): a fullscreen window (320 x 480, portrait), one view over the whole window (vinyl_view: the touch target, painted by the
# payload in its own EVT_AFTER_PAINT) and the text over it as insensitive hscroll_labels that never scroll (cut with an ellipsis; tools/vinyl_art.py TEXT): the title and its twin one
# pixel right (the weight of the mock's title), the artist, the times, the status line. label_title (hidden) is the page's name for the i18n and asset tests.
VN_LABELS = (('vn_title', 'title', 0), ('vn_title2', 'title', 1), ('vn_artist', 'artist', 0), ('vn_times', 'times', 0), ('vn_status', 'status', 0))


def build_vinyl_page(page):
    import vinyl_art
    th = getattr(page, 'theme', 'graphite'); bg = '#%02X%02X%02X' % tuple(vinyl_art.window_bg(th))
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', bg)
    view = Widget('view', 0, 0, 320, 480, [('name', 'vinyl_view')])
    styled(view, ('normal',), 'bg_color', bg)
    root.children = [view]
    for name, field, dx in VN_LABELS:
        t = vinyl_art.TEXT[field]; x, y, w, h = vinyl_art.label_box(field)
        lab = Widget('hscroll_label', x + dx, y, w, h, [('name', name), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(t['px']))
            styled(lab, (st,), 'text_color', '#%02X%02X%02X' % vinyl_art.text_rgb(field, th))
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        root.children.append(lab)
    title = hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))
    if th == 'white':   # never seen; the build's contrast scan still reads it against the light plinth
        for st in ('normal', 'disable', 'focused'): styled(title, (st,), 'text_color', '#1C1C1E')
    root.children.append(title)
    return root


# Find Cover & Lyrics (patch/onlineart.c, docs/modules/onlineart.md): the stock navbar, the Search page's chip row (Covers, Lyrics) and line, then the Search page's list (list_view > scroll_view holding
# ONE content view, oa_view, that the payload paints: the cover thumbnails of the Covers tab, the candidate rows of the Lyrics tab, a lyrics text's lines in a detail). Two details are the same window with other
# widgets shown (hidden = visible=false and sensitive=false): the cover's confirmation (oa_dc: the larger cover painted on oa_dc_art, its texts and the pill oa_save) and the lyrics' (the header oa_dh_*, the
# list showing the text, the pill oa_lsave). Every y of the labels is a window y (the navbar is 50 px).
# The empty / failed state's block over the list (patch/onlineart.c OA_ES_*, the same numbers; the payload stacks and centres what a state has on window y OA_ES_CENTRE): a 40 px glyph (the image of the state, pod_es_*),
# the title (oa_status: white, 18 px), the explanation (oa_es_text, two lines, grey, 14 px, wrapped by the label) and the Try Again pill (oa_es_retry).
OA_ES_CENTRE, OA_ES_ICON, OA_ES_TITLE_H, OA_ES_TEXT_H, OA_ES_TEXT_W, OA_ES_PILL_W, OA_ES_PILL_H = 260, 40, 26, 40, 260, 168, 36
OA_ES_ICON_GAP, OA_ES_TITLE_GAP, OA_ES_PILL_GAP = 14, 4, 18
OA_ES_TEXT_PX = 14
# The states (patch/onlineart.c oa_es_fail / oa_es_state; test/pod/onlineartpage.py proves the payload shows exactly these; tools/preview_onlineart.py draws them): name -> (glyph image, title, explanation, Try Again pill).
# "Searching…" has only the title. The failure titles are the Podcasts' words.
OA_ES_STATES = {
    'lyrics busy': ('pod_es_timer', 'Lyrics Service Busy', 'LRCLIB is under heavy load. Try again in a moment.', True),
    'covers busy': ('pod_es_timer', 'Cover Service Busy', 'iTunes and Deezer are busy. Try again in a moment.', True),
    'no lyrics': ('pod_es_music', 'No Lyrics Found', 'LRCLIB has no lyrics for this song.', False),
    'no covers': ('pod_es_image', 'No Covers Found', 'Nothing on iTunes or Deezer for this album.', False),
    'no connection': ('pod_es_plug', "Can't connect", 'Check your Wi-Fi connection.', True),
    'certificate': ('pod_es_lock', 'Certificate problem', "The server's certificate was not accepted.", True),
    'no certificates': ('pod_es_lock', 'Certificates missing', 'This device has no certificate bundle.', False),
    'server error': ('pod_es_info', 'Server error', 'The server could not answer. Try again later.', True),
    'no Wi-Fi': ('pod_es_wifi', 'No Wi-Fi', 'Turn on Wi-Fi to search online.', True),
    'no date': ('pod_es_calendar', 'Set the date first', 'Secure connections need the right date.', True),
    'no card': ('pod_es_card', 'Storage unavailable', 'The SD card could not be used.', True),
    'no memory': ('pod_es_drive', 'Not enough memory', 'There is not enough memory to search.', True),
}


def oa_es_layout(glyph, text, pill):
    """The block's y's (window coordinates) as patch/onlineart.c oa_es_apply stacks them: (icon, title, text, pill), None for a part the state does not have; the whole centred on OA_ES_CENTRE."""
    h = (OA_ES_ICON + OA_ES_ICON_GAP if glyph else 0) + OA_ES_TITLE_H + (OA_ES_TITLE_GAP + OA_ES_TEXT_H if text else 0) + (OA_ES_PILL_GAP + OA_ES_PILL_H if pill else 0)
    y = OA_ES_CENTRE - h // 2
    ys = [None, None, None, None]
    if glyph: ys[0], y = y, y + OA_ES_ICON + OA_ES_ICON_GAP
    ys[1], y = y, y + OA_ES_TITLE_H
    if text: y += OA_ES_TITLE_GAP; ys[2], y = y, y + OA_ES_TEXT_H
    if pill: ys[3] = y + OA_ES_PILL_GAP
    return tuple(ys)


OA_STATUS =(16, 214, 288, OA_ES_TITLE_H, 18, '#FFFFFF')    # x, y, w, h, px, colour: the title of the state block
OA_HEAD_TITLE = (16, 52, 288, 20, 17, '#FFFFFF')   # the lyrics detail's header, in the chip row's place
OA_HEAD_SUB = (16, 72, 288, 15, 13, '#8E8E93')
OA_LPILL = (16, 400, 288, 40)    # the lyrics detail's pill (window y); the text lines stop above it (OA_LY_H of patch/onlineart.c)
OA_DC = (0, NAVBAR_H, SCREEN_W, CLIENT_H - NAVBAR_H)   # the cover detail's container (window y)
OA_DC_ART = (40, 8, 240, 240)    # the larger cover (container y)
OA_DC_LABELS = (   # name, y (container), h, px, colour: the album, the artist, the source, the failure line
    ('oa_dc_name', 256, 26, 20, '#FFFFFF'),
    ('oa_dc_artist', 282, 22, 16, '#AAAAAA'),
    ('oa_dc_source', 304, 20, 13, '#8E8E93'),
    ('oa_hint', 326, 20, 14, '#8E8E93'))
OA_PILL = (16, 352, 288, 40)     # the cover detail's pill (container y)
OA_BADGE_PX = 12
OA_LINE_PX = 17                  # a lyrics text line


def _oa_label(name, x, y, w, h, px, colour, align='center', text=None, valign='middle'):
    lab = Widget('label', x, y, w, h, [('name', name), ('sensitive', 'false'), pod_i18n.text_prop(text) if text else ('text', '')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'text_color', colour)
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_align_h', align)
        styled(lab, (st,), 'text_align_v', valign)
    return lab


def _oa_pill(name, x, y, w, h, px=18):
    pill = hidden(Widget('button', x, y, w, h, [('name', name), ('enable', 'true'), ('text', '')]))
    for st in STATES:
        styled(pill, (st,), 'bg_color', SG_PILL_DOWN_RGB if st == 'pressed' else SG_PILL_OFF_RGB if st == 'disable' else SG_PILL_RGB)
        styled(pill, (st,), 'text_color', '#FFFFFF')
        styled(pill, (st,), 'font_size', str(px))
        styled(pill, (st,), 'border_width', '0')
        styled(pill, (st,), 'border_color', '#00000000')
        styled(pill, (st,), 'round_radius', str(max(OFFSETS['SG_PILL_R'], h // 2)))
    return pill


def build_onlineart_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    # the Search page's chip row, line and list (the same numbers: tools/pod_search.py)
    chips = Widget('view', 0, PS.SE_CHIPS_Y, SCREEN_W, PS.SE_CHIPS_H, [('name', 'oa_chips'), ('enable', 'true')])
    for st in STATES:
        styled(chips, (st,), 'bg_color', '#000000')
        styled(chips, (st,), 'border_width', '0')
    chips.children = [kb_view('oa_chip_hl', PS.SE_CHIP_X, PS.SE_CHIP_Y, 80, PS.SE_CHIP_H, PS.CHIP_ON_RGB, PS.SE_CHIP_R)]
    root.children.append(chips)
    sep = Widget('view', 0, PS.SE_SEP_Y, SCREEN_W, 1, [('name', 'oa_sep'), ('sensitive', 'false')])
    styled(sep, STATES, 'bg_color', PS.SEP_RGB)
    root.children.append(sep)
    lv = stock_list([], True, top=PS.SE_LIST_Y)
    lv.set('name', 'oa_listview')
    sv = lv.children[0]
    sv.set('name', 'oa_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, PS.SE_LIST_H, [('name', 'oa_view')])
    styled(view, ('normal',), 'bg_color', '#000000')
    sv.children.append(view)
    root.children.append(lv)
    x, y, w, h, px, colour = OA_STATUS
    root.children.append(hidden(_oa_label('oa_status', x, y, w, h, px, colour)))
    root.children.append(hidden(Widget('image', (SCREEN_W - OA_ES_ICON) // 2, OA_ES_CENTRE - 100, OA_ES_ICON, OA_ES_ICON, [('name', 'oa_es_icon'), ('image', 'pod_es_info'), ('draw_type', 'center'), ('sensitive', 'false')])))
    root.children.append(hidden(_oa_label('oa_es_text', (SCREEN_W - OA_ES_TEXT_W) // 2, OA_ES_CENTRE - 20, OA_ES_TEXT_W, OA_ES_TEXT_H, OA_ES_TEXT_PX, '#8E8E93', valign='top')))
    root.children.append(_oa_pill('oa_es_retry', (SCREEN_W - OA_ES_PILL_W) // 2, OA_ES_CENTRE + 30, OA_ES_PILL_W, OA_ES_PILL_H))
    x, y, w, h, px, colour = OA_HEAD_TITLE
    root.children.append(hidden(_oa_label('oa_dh_title', x, y, w, h, px, colour)))
    x, y, w, h, px, colour = OA_HEAD_SUB
    root.children.append(hidden(_oa_label('oa_dh_sub', x, y, w, h, px, colour)))
    root.children.append(_oa_pill('oa_lsave', *OA_LPILL))
    # the cover detail
    dc = hidden(Widget('view', *OA_DC, [('name', 'oa_dc')]))
    styled(dc, ('normal',), 'bg_color', '#000000')
    dc.children.append(Widget('view', *OA_DC_ART, [('name', 'oa_dc_art'), ('sensitive', 'false')]))
    styled(dc.children[-1], ('normal',), 'bg_color', '#000000')
    for name, y, h, px, colour in OA_DC_LABELS:
        dc.children.append(hidden(_oa_label(name, 16, y, SCREEN_W - 32, h, px, colour)) if name == 'oa_hint' else _oa_label(name, 16, y, SCREEN_W - 32, h, px, colour))
    dc.children.append(_oa_pill('oa_save', 16, OA_PILL[1], OA_PILL[2], OA_PILL[3]))
    root.children.append(dc)
    # text styles only (widget_prepare_text_style), never shown; the title of the navbar is its own label_title
    for name, px, colour, align in (('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB, 'left'), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB, 'left'), ('label_chip', PS.SE_CHIP_PX, PS.CHIP_INK, 'center'),
                                    ('label_chip_on', PS.SE_CHIP_PX, PS.CHIP_ON_INK, 'center'), ('label_badge', OA_BADGE_PX, PS.SUB_RGB, 'center'), ('label_badge_on', OA_BADGE_PX, PS.CHIP_ON_INK, 'center'),
                                    ('label_line', OA_LINE_PX, '#FFFFFF', 'left')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if name == 'label_chip_on': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', PS.CHIP_ON_RGB)
        if name == 'label_badge': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', PS.SEP_RGB)
        if name == 'label_badge_on': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', PS.CHIP_ON_RGB)
        root.children.append(lab)
    return root




# Software Update (patch/update.c, docs/modules/update.md): the stock navbar over one block with FIXED places (the same in every state, so nothing jumps between states), centred in the 400 px under the navbar: a 48 px glyph, 16 px, the title
# (22 px white, UP_TITLE_W wide), 8 px, the detail (18 px grey #AAAAAA, centred, wrapped to at most two lines, UP_TEXT_W), 24 px, a pill (UP_PILL_W x UP_PILL_H, 20 px text), 12 px, a second pill. The payload shows the parts a state has. A download runs in
# a modal popup over the page: the Podcasts refresh dialog's scrim and card (podcasts_dialog(big=True), names up_pd_*: the title "Downloading 1.0.1", a grey line, a 6 px bar, the percentage and Cancel). Neutral white and grey, no accent colour.
UP_ICON, UP_ICON_GAP, UP_TITLE_H, UP_TITLE_GAP, UP_TITLE_W = 48, 16, 30, 8, 288
UP_TEXT_H, UP_TEXT_W, UP_TEXT_PX, UP_TITLE_PX, UP_PILL_PX = 48, 280, 18, 22, 20
UP_PILL_GAP, UP_PILL_W, UP_PILL_H, UP_PILL2_GAP = 24, 260, 48, 12
UP_BLOCK_H = UP_ICON + UP_ICON_GAP + UP_TITLE_H + UP_TITLE_GAP + UP_TEXT_H + UP_PILL_GAP + UP_PILL_H + UP_PILL2_GAP + UP_PILL_H
UP_TOP = NAVBAR_H + (CLIENT_H - NAVBAR_H - UP_BLOCK_H) // 2
UP_YS = (UP_TOP, UP_TOP + UP_ICON + UP_ICON_GAP, UP_TOP + UP_ICON + UP_ICON_GAP + UP_TITLE_H + UP_TITLE_GAP)   # icon, title, detail
UP_YS += (UP_YS[2] + UP_TEXT_H + UP_PILL_GAP, UP_YS[2] + UP_TEXT_H + UP_PILL_GAP + UP_PILL_H + UP_PILL2_GAP)   # pill, second pill


def build_update_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    root.children.append(hidden(Widget('image', (SCREEN_W - UP_ICON) // 2, UP_YS[0], UP_ICON, UP_ICON, [('name', 'up_icon'), ('image', 'pod_es_download'), ('draw_type', 'center'), ('sensitive', 'false')])))
    root.children.append(_oa_label('up_title', (SCREEN_W - UP_TITLE_W) // 2, UP_YS[1], UP_TITLE_W, UP_TITLE_H, UP_TITLE_PX, '#FFFFFF'))
    root.children.append(hidden(_oa_label('up_text', (SCREEN_W - UP_TEXT_W) // 2, UP_YS[2], UP_TEXT_W, UP_TEXT_H, UP_TEXT_PX, '#AAAAAA', valign='top')))
    root.children.append(_oa_pill('up_pill', (SCREEN_W - UP_PILL_W) // 2, UP_YS[3], UP_PILL_W, UP_PILL_H, UP_PILL_PX))
    root.children.append(_oa_pill('up_pill2', (SCREEN_W - UP_PILL_W) // 2, UP_YS[4], UP_PILL_W, UP_PILL_H, UP_PILL_PX))
    root.children.extend(podcasts_dialog('up_pd', 'Downloading %s', big=True))   # last: above everything
    return root


# Release Notes (patch/relnotes.c, docs/modules/update.md "Release notes"): the stock navbar over a stock list (list_view > scroll_view + scroll bar) holding one content view the payload paints the heading and the wrapped
# notes on, as the Find Cover & Lyrics lyrics detail does. Two hidden labels only carry the text styles (22 px white heading, 18 px light grey text). Neutral, no accent colour.
RN_HEAD_PX, RN_LINE_PX, RN_LINE_RGB = 22, 18, '#E6E6E6'


def build_relnotes_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'rn_listview')
    sv = lv.children[0]
    sv.set('name', 'rn_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, CLIENT_H - NAVBAR_H, [('name', 'rn_view')])
    styled(view, ('normal',), 'bg_color', '#000000')
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(nav_fade())
    for name, px, colour in (('label_head', RN_HEAD_PX, '#FFFFFF'), ('label_line', RN_LINE_PX, RN_LINE_RGB)):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    return root


def build_menucfg_page(page):
    """The Main Menu page (patch/menu.c) and the Pull-down page (patch/pulldown.c, kind pdcfg: a row per tile): a row per menu item in the default order, each with an up arrow (a stock
    button with the stock chevron-up art, expansion_2, insensitive: a picture, the row decides by the tap position)
    and a switch. The payload orders the rows, sets the switches and hides the arrows of the hidden items and of the
    first shown one."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    sv = lv.children[0]
    if page.kind == 'pdcfg':   # the Pull-down page (patch/pulldown.c): the same rows for the eight tiles, all shown by default
        sv.children += cfg_rows(sv.w, pod_pages.PULLDOWN_TILES, range(len(pod_pages.PULLDOWN_TILES)))
    else:
        sv.children += cfg_rows(sv.w, [r.label for r in pod_pages.ITEMS], pod_pages.DEFAULT_MENU)
    root.children.append(lv)
    root.children.append(nav_fade())
    return root


def cfg_rows(w, labels, on):
    """The rows of a Main Menu style page (the menu items, the pull-down tiles): a switch (on for the ids in `on`) and an up arrow each."""
    rows = []
    for i, label_ in enumerate(labels):
        row = row_item(f'pod_row{i}', i * ROW_H, label_, False, ROW_H, w, (f'pod_switch{i}', i in on))
        row.children[0].w = switch_x(w) - UP_W - row.children[0].x
        row.children.append(Widget('button', switch_x(w) - UP_W, 0, UP_W, ROW_H, [
            ('name', f'pod_up{i}'), ('enable', 'true'), ('sensitive', 'false'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'expansion_2_down'), ('style:normal:icon', 'expansion_2'), ('style:over:icon', 'expansion_2')]))
        rows.append(row)
    return rows


# The Extras page's section headers (patch/menu.c mn_extras; iOS grouped-list captions): one per group of pod_pages.EXTRAS_GROUPS, pod_hdr0 ..,
# a plain view HDR_H (40) high, shorter than a row, the child of the list's scroll_view like a row (the stock list_view layouter keeps the height of a child that is not
# a row, as it does the shelf's, and sums it). The caption is a stock hscroll_label (never scrolls, ellipsis) in the style of the Home menu's "Made for You" heading
# (pod_dm_head) and the Recently Played shelf's: x 10, 20 px (SH_HEAD_X, SH_HEAD_PX, defined below; test/pod/menu.py asserts they agree), but in the secondary grey, left aligned,
# so every section heading of the Music pages sits on one left edge. Insensitive always and hidden in the asset (the payload shows it by visible alone): never a touch target, and no list_item (no press visual, no
# chevron or icon). The label is 22 px high in the strip's bottom 26 px.
HDR_X, HDR_PX, HDR_RGB = 10, 20, '#AAAAAA'   # the secondary grey (SH_SUB_RGB, pod_settings.GREY): a group caption, dimmer than its rows
HDR_LABEL_Y, HDR_LABEL_H = 14, 22
HDR_NAMES = tuple(f'pod_hdr{g}' for g in range(len(pod_pages.EXTRAS_GROUPS)))


def extras_headers(w):
    """The hidden, insensitive section headers of the Extras page and of Settings > Extras, for a list `w` wide."""
    out = []
    for g, title in enumerate(pod_pages.EXTRAS_TITLES):
        hdr = hidden(Widget('view', 0, 0, w, pod_pages.HDR_H, [('name', f'pod_hdr{g}')]))
        styled(hdr, ('normal', 'disable', 'focused', 'pressed', 'over', 'selected'), 'bg_color', '#000000')
        lab = Widget('hscroll_label', HDR_X, HDR_LABEL_Y, w - HDR_X - 12, HDR_LABEL_H, [
            ('name', f'pod_hdr_text{g}'), pod_i18n.text_prop(title), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(HDR_PX))
            styled(lab, (st,), 'text_color', HDR_RGB)
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        hdr.children.append(lab)
        out.append(hdr)
    return out


def build_extrascfg_page(page):
    """Settings > Extras (patch/menu.c menu_extras_opened): a switch row (the whole row toggles) per item but Settings, in id order
    like the Extras page's asset, all on. The payload shows only the items the menu does not show, stacked in EXTRAS_ORDER, and sets the
    switches from the saved list. No up arrows: the order is fixed."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    sv = lv.children[0]
    for k, (i, r) in enumerate((i, r) for i, r in enumerate(pod_pages.ITEMS) if i != pod_pages.SETTINGS_ID):
        sv.children.append(row_item(f'pod_row{i}', k * ROW_H, r.label, False, ROW_H, sv.w, (f'pod_switch{i}', True)))
    sv.children += extras_headers(sv.w)   # after the rows: the payload stacks them in place
    root.children.append(lv)
    root.children.append(nav_fade())
    return root


# The Settings pages (docs/modules/settings.md "Cards"): iOS-style grouped cards in the stock list (list_view > scroll_view 310 wide + scroll_bar_m, stock list_item rows). The stock list_view
# layouter stacks every visible child of the scroll_view in child order and ignores its y, so the children ARE the column (tools/pod_settings.py layout): a spacer, then the rows, headers,
# notes and gaps in display order, then a spacer. A card is drawn by its rows: each row's background is a picture piece (single / top / middle / bottom, pod_cd_*, the card's inset,
# corners and fill baked in, a lit twin when pressed). A row is a stock list_item with a glyph image, the stock 21 px label, a hairline child from the label to the card's edge (not on a
# card's last row) and the right accessory: the chevron image (pod_chev), a value label and chevron, the stock switch image or the picker's check (hidden until the payload shows it on
# the chosen row). Headers and notes are insensitive views whose grey label starts where the row glyphs' ink does. The numbers are tools/pod_settings.py's.
def cards_row(i, row, piece, last):
    import pod_settings as ST
    from mod_icons import CARD_GLYPHS, card_name, CARD_CHEVRON, CARD_CHECK
    kind = pod_pages.row_kind(row)
    swatch = row.action == pod_pages.ACT_ACCENTSET   # the Accent picker's rows show the accent's round swatch where a glyph goes (never tinted: docs/modules/accent.md)
    has_icon = swatch or (kind not in ('check', 'info') and row.action not in (pod_pages.ACT_CCLIST, pod_pages.ACT_UPDATE))   # (the Cover Cache counts and About's Software Update link have no glyph, like the rows around them)
    item = Widget('list_item', 0, 0, ST.LIST_W, ST.ROW_H, [('name', f'pod_row{i}'), ('style', 'list_item_style')] + ([('sensitive', 'false')] if kind == 'info' else []))
    normal, down = ST.piece_images(piece)
    for st in ('normal', 'over', 'pressed', 'focused', 'disable'):
        styled(item, (st,), 'bg_color', '#00000000')
        styled(item, (st,), 'bg_image', down if st == 'pressed' else normal)
        styled(item, (st,), 'bg_image_draw_type', 'default')
        styled(item, (st,), 'border_width', '0')
        styled(item, (st,), 'border_color', '#00000000')
    x, w = ST.label_box(kind, has_icon)
    if has_icon:
        item.children.append(Widget('image', ST.ICON_X, ST.ICON_Y, ST.ICON_PX, ST.ICON_PX, [
            ('name', 'pod_swatch' if swatch else 'pod_icon'), ('image', f'pod_sw{row.arg}' if swatch else card_name(CARD_GLYPHS[row.label])), ('draw_type', 'icon'), ('sensitive', 'false')]))
    item.children.append(Widget('hscroll_label', x, 0, w, ST.ROW_H, [
        ('name', f'pod_label{i}'), ('style', 'srlabel_leftwhite21_style'), pod_i18n.text_prop(row.label), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('yoyo', 'true'), ('loop', 'true')]))
    if kind in ('link', 'value'):
        ax, ay, aw, ah = ST.accessory('chevron')
        item.children.append(Widget('image', ax, ay, aw, ah, [('name', 'pod_chevron'), ('image', CARD_CHEVRON[0]), ('draw_type', 'icon'), ('sensitive', 'false')]))
    if kind == 'value':
        vx, vw = ST.value_box()
        init = pod_pages.VALUE_INIT.get(row.action)
        val = Widget('hscroll_label', vx, 0, vw, ST.ROW_H, [('name', f'pod_value{i}'), pod_i18n.text_prop(init) if init else ('text', ''), ('only_parent_focus', 'true'),
                                                              ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(val, (st,), 'font_size', str(ST.VALUE_PX))
            styled(val, (st,), 'text_color', ST.GREY)
            styled(val, (st,), 'text_align_h', 'right')
            styled(val, (st,), 'text_align_v', 'middle')
        item.children.append(val)
    if kind == 'info':
        vx, vw = ST.info_box()
        val = Widget('hscroll_label', vx, 0, vw, ST.ROW_H, [('name', f'pod_value{i}'), ('text', ''), ('only_parent_focus', 'true'),
                                                              ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(val, (st,), 'font_size', str(ST.VALUE_PX if row.arg >= pod_pages.INFO_CC_ALBUMS else ST.INFO_PX))   # (the Cover Cache page's values are the standard 18 px value size, About's the stock About's 16)
            styled(val, (st,), 'text_color', ST.GREY)
            styled(val, (st,), 'text_align_h', 'right')
            styled(val, (st,), 'text_align_v', 'middle')
        item.children.append(val)
    if kind == 'switch':
        ax, ay, aw, ah = ST.accessory('switch')
        item.children.append(Widget('image', ax, ay, aw, ah, [('name', f'pod_switch{i}'), ('image', 'sset_off'), ('draw_type', 'default'), ('sensitive', 'false')]))
    if kind == 'check':
        ax, ay, aw, ah = ST.accessory('check')
        item.children.append(hidden(Widget('image', ax, ay, aw, ah, [('name', f'pod_check{i}'), ('image', CARD_CHECK[0]), ('draw_type', 'icon')])))
    if not last:
        hair = Widget('view', x, ST.ROW_H - 1, ST.CM + ST.CARD_W - x, 1, [('name', 'pod_hair'), ('sensitive', 'false')])
        for st in STATES: styled(hair, (st,), 'bg_color', ST.CARD_HAIR_RGB)
        item.children.append(hair)
    return item


def cards_spacer(name, h):
    import pod_settings as ST
    """An insensitive black view h high: the layouter gives it the list's width and its place."""
    v = Widget('view', 0, 0, ST.LIST_W, h, [('name', name), ('sensitive', 'false')])
    for st in STATES: styled(v, (st,), 'bg_color', '#000000')
    return v


def cards_text(name, y, h, text, px, item_h):
    """A header or a note: an insensitive view item_h high holding the grey label (text from HDR_X, which the layouter does not move: it is the child's)."""
    import pod_settings as ST
    v = cards_spacer(name, item_h)
    lab = Widget('hscroll_label', ST.HDR_X, y, ST.HDR_W, h, [('name', name + '_t'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_color', ST.GREY)
        styled(lab, (st,), 'text_align_h', 'left')
        styled(lab, (st,), 'text_align_v', 'middle')
    v.children.append(lab)
    return v


def build_cards_page(page):
    import pod_settings as ST
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    sv = lv.children[0]
    placed, end = ST.layout(page.layout)
    pieces = ST.pieces(page.layout)
    n_hdr = n_note = n_gap = i = 0
    for it, y in placed:
        if it == ST.TOP: sv.children.append(cards_spacer('pod_top', ST.CM))
        elif it == ST.END: sv.children.append(cards_spacer('pod_end', ST.END_H))
        elif it is pod_pages.GAP: sv.children.append(cards_spacer(f'pod_gap{n_gap}', ST.GAP_H)); n_gap += 1
        elif isinstance(it, pod_pages.Hdr): sv.children.append(cards_text(f'pod_sec{n_hdr}', ST.HDR_LABEL_Y, ST.HDR_LABEL_H, it.text, ST.HDR_PX, ST.HDR_H)); n_hdr += 1
        elif isinstance(it, pod_pages.Note): sv.children.append(cards_text(f'pod_note{n_note}', ST.NOTE_LABEL_Y, ST.NOTE_LABEL_H, it.text, ST.NOTE_PX, ST.NOTE_H)); n_note += 1
        else:
            sv.children.append(cards_row(i, it, pieces[i], pieces[i] in ('single', 'bot'))); i += 1
        sv.children[-1].y = y   # (the layouter sets it again: the asset says the same)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # the first card is 10 px under the bar: the fade would dim its top at rest, so it stays hidden (the content clips at the bar)
    return root


# The mini player bar of the menu's Home instance (patch/minibar.c, docs/modules/minibar.md): a hidden, insensitive view holding a
# floating glass pill (a button: the tap target that opens Now Playing; its look is the pre-rendered translucent image mb_glass), the
# title and artist as non-scrolling hscroll_labels (ellipsis), and the play, pause (one shows) and next buttons with the bare white bar glyphs (mb_*, tools/mod_icons.py). patch/offsets.inc MB_* hold the same numbers (test/pod/minibar.py asserts it).
MB_X, MB_Y, MB_W, MB_H, MB_R, MB_GAP = 8, 384, 304, 56, 28, 8
MB_ART, MB_ART_X, MB_ART_Y, MB_ART_R = 36, 14, 10, 5
MB_TEXT_X, MB_TEXT_W = 60, 130
MB_TITLE_Y, MB_TITLE_H, MB_TITLE_PX = 7, 22, 17
MB_ARTIST_Y, MB_ARTIST_H, MB_ARTIST_PX = 29, 20, 16
MB_PLAY_X, MB_NEXT_X, MB_BTN_W = 194, 245, 48
MB_GLASS, MB_GLASS_DOWN = 'mb_glass', 'mb_glass_down'   # the pill's images (tools/mod_icons.py glass_image, MB_W x MB_H, alpha): normal and pressed (brighter)
MB_PAD = 64                                  # the list's bottom padding while the bar shows: the window's 440 less (MB_Y - MB_GAP), so the last row scrolls clear above the pill
MB_TITLE_RGB, MB_ARTIST_RGB = '#FFFFFF', '#D0D0D0'
MB_NAMES = ('pod_minibar', 'pod_mb_card', 'pod_mb_title', 'pod_mb_artist', 'pod_mb_play', 'pod_mb_pause', 'pod_mb_next')


def minibar():
    bar = hidden(Widget('view', MB_X, MB_Y, MB_W, MB_H, [('name', 'pod_minibar')]))
    card = Widget('button', 0, 0, MB_W, MB_H, [('name', 'pod_mb_card'), ('enable', 'true')])
    for st in ('normal', 'pressed', 'over', 'focused', 'disable', 'selected'):
        styled(card, (st,), 'bg_color', '#00000000')   # the glass image is the whole look; nothing is filled or stroked under or over it
        styled(card, (st,), 'bg_image', MB_GLASS_DOWN if st == 'pressed' else MB_GLASS)
        styled(card, (st,), 'text_color', '#FFFFFF')   # the card has no text; every inline-styled button is dark with light text (test/pod/assets.py)
        styled(card, (st,), 'border_width', '0')
        styled(card, (st,), 'border_color', '#00000000')
    bar.children.append(card)
    for name, y, h, px, colour in (('pod_mb_title', MB_TITLE_Y, MB_TITLE_H, MB_TITLE_PX, MB_TITLE_RGB),
                                   ('pod_mb_artist', MB_ARTIST_Y, MB_ARTIST_H, MB_ARTIST_PX, MB_ARTIST_RGB)):
        lab = Widget('hscroll_label', MB_TEXT_X, y, MB_TEXT_W, h, [('name', name), ('text', ''), ('only_parent_focus', 'true'),
                                                                     ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', colour)
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        bar.children.append(lab)
    for name, x, icon, off in (('pod_mb_play', MB_PLAY_X, 'mb_play', False), ('pod_mb_pause', MB_PLAY_X, 'mb_pause', True),
                               ('pod_mb_next', MB_NEXT_X, 'mb_next', False)):
        btn = Widget('button', x, 0, MB_BTN_W, MB_H, [
            ('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)])
        bar.children.append(hidden(btn) if off else btn)
    return bar




# The Recently Played shelf of the menu's Home instance (patch/recent.c, docs/modules/recent.md): the Albums grid (patch/grid.c) in a view of its own, the child of
# the list's scroll view that follows the last shown row (Settings), a hidden and insensitive view the payload shows only when there is an album to show. The cell
# geometry is the Albums grid's: GRID_* are read from patch/offsets.inc, not copied. At its top a section header, the label pod_sh_head (the translation of
# "Recently Played", SH_HEAD_PX white, an hscroll_label that never scrolls and ends in an ellipsis, insensitive: a touch on it falls to the shelf, which has no cell
# there); the view then paints up to SH_TILES (GRID_COLS x SH_ROWS) covers and their two text lines itself (its own EVT_AFTER_PAINT) and takes the taps; the two hidden
# labels inside it only carry the text styles (widget_prepare_text_style: the grid's 18 px white album and 15 px #AAAAAA artist). The header's text lines up with the
# covers: the label starts 2 px before them and an hscroll_label insets its text 2 px. ceil(albums / 2) rows of covers, SH_H(n): the asset
# has the largest height (SH_HMAX), the payload sets the real one.
GRID_COLS, GRID_COVER, GRID_GAP, GRID_MARGIN, GRID_ROW_GAP, GRID_R = (OFFSETS[k] for k in ('GRID_COLS', 'GRID_COVER', 'GRID_GAP', 'GRID_MARGIN', 'GRID_ROW_GAP', 'GRID_R'))
GRID_TITLE_GAP, GRID_TITLE_H, GRID_SUB_H = (OFFSETS[k] for k in ('GRID_TITLE_GAP', 'GRID_TITLE_H', 'GRID_SUB_H'))
GRID_CELL_H = GRID_COVER + GRID_TITLE_GAP + GRID_TITLE_H + GRID_SUB_H      # 190
GRID_PITCH = GRID_CELL_H + GRID_ROW_GAP                                       # 200
SH_W, SH_ROWS = 310, 3
SH_TILES = GRID_COLS * SH_ROWS                    # 6: every album the file keeps (RC_MAX)
assert SH_TILES == OFFSETS['SH_TILES'] and SH_ROWS == OFFSETS['SH_ROWS'] == 3
SH_HEAD_X, SH_HEAD_W, SH_HEAD_TOP, SH_HEAD_H, SH_HEAD_PX, SH_HEAD_GAP = 10, 300, 17, 22, 20, 5   # the 20 px line's ink runs from 20 to 36 (the line box has slack): 20 px of air above, 8 below
SH_TOP = SH_HEAD_TOP + SH_HEAD_H + SH_HEAD_GAP     # 44: the first row of covers
SH_BOTTOM = 0                                      # the artist line's box ends the shelf: scrolled to the end it is MB_GAP above the pill, as the last row was
def SH_H(n): return SH_TOP + n * GRID_CELL_H + (n - 1) * GRID_ROW_GAP + SH_BOTTOM   # the shelf's height for n rows of covers: 234, 434, 634
SH_HMAX = SH_H(SH_ROWS)
SH_NAMES = ('pod_shelf', 'pod_sh_head', 'pod_sh_title', 'pod_sh_sub')
SH_TITLE_RGB, SH_SUB_RGB = '#FFFFFF', '#AAAAAA'
SH_TITLE_PX, SH_SUB_PX = GRID_ALBUM_PX, GRID_ARTIST_PX


def shelf():
    sh = hidden(Widget('view', 0, 0, SH_W, SH_HMAX, [('name', 'pod_shelf')]))
    styled(sh, ('normal', 'disable', 'focused', 'pressed', 'over', 'selected'), 'bg_color', '#000000')   # (no state of a plain view shows another colour)
    head = Widget('hscroll_label', SH_HEAD_X, SH_HEAD_TOP, SH_HEAD_W, SH_HEAD_H, [
        ('name', 'pod_sh_head'), pod_i18n.text_prop('Recently Played'), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(head, (st,), 'font_size', str(SH_HEAD_PX))
        styled(head, (st,), 'text_color', SH_TITLE_RGB)
        styled(head, (st,), 'text_align_h', 'left')
        styled(head, (st,), 'text_align_v', 'middle')
    sh.children.append(head)
    for name, px, colour in (('pod_sh_title', SH_TITLE_PX, SH_TITLE_RGB), ('pod_sh_sub', SH_SUB_PX, SH_SUB_RGB)):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        sh.children.append(lab)
    return sh


# The cover build's progress line of the Home instance (patch/homecover.c, docs/modules/homecover.md; HC_* of patch/offsets.inc): a plain 15 px #AAAAAA label above the list, hidden and
# insensitive until the payload shows it (and moves the list down by HC_H); the payload sets its text ("Preparing covers 120/840").
COVER_PROG = 'pod_cover_prog'
HC_PX = OFFSETS['HC_PX']


def cover_progress():
    lab = hidden(label(COVER_PROG, OFFSETS['HC_X'], OFFSETS['HC_Y'], OFFSETS['HC_W'], OFFSETS['HC_H'], '', HC_PX, SH_SUB_RGB, 'left'))
    styled(lab, ('normal',), 'text_align_v', 'middle')
    return lab


# The Daily Mix section of the menu's Home instance (patch/dailymix.c, docs/modules/dailymix.md; the DM_* numbers are tools/pod_dailymix.py's, patch/offsets.inc has the
# same): a view the width of the list between the shown rows and the Recently Played shelf, hidden and insensitive until the payload has a mix to show. The header
# pod_dm_head is the shelf's (a stock hscroll_label, the key "Made for You"); the card pod_dm_card (DM_W x DM_H at DM_X, DM_TOP) paints the art and the text itself
# (its own EVT_AFTER_PAINT) and takes the taps that open the playlist; the play disc pod_dm_play is a stock button over its corner (a later sibling, so it takes its own
# touches) whose look is the glass images dm_disc / dm_disc_down; the two hidden labels only carry the title (36 px white) and artists (16 px #EBEBEB) text styles.
DM_NAMES = ('pod_daily', 'pod_dm_head', 'pod_dm_card', 'pod_dm_play', 'pod_dm_title', 'pod_dm_sub')
DM_DISC_IMAGE = 'dm_disc'


def daily():
    import pod_dailymix as D
    sec = hidden(Widget('view', 0, 0, D.DM_W_VIEW, D.DM_SEC_H, [('name', 'pod_daily')]))
    styled(sec, ('normal', 'disable', 'focused', 'pressed', 'over', 'selected'), 'bg_color', '#000000')
    head = Widget('hscroll_label', D.DM_HEAD_X, D.DM_HEAD_TOP, D.DM_HEAD_W, D.DM_HEAD_H, [
        ('name', 'pod_dm_head'), pod_i18n.text_prop('Made for You'), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(head, (st,), 'font_size', str(D.DM_HEAD_PX))
        styled(head, (st,), 'text_color', SH_TITLE_RGB)
        styled(head, (st,), 'text_align_h', 'left')
        styled(head, (st,), 'text_align_v', 'middle')
    card = Widget('view', D.DM_X, D.DM_TOP, D.DM_W, D.DM_H, [('name', 'pod_dm_card')])
    styled(card, ('normal', 'disable', 'focused', 'pressed', 'over', 'selected'), 'bg_color', '#000000')
    play = Widget('button', D.DM_X + D.DM_DISC_X, D.DM_TOP + D.DM_DISC_Y, D.DM_DISC, D.DM_DISC, [
        ('name', 'pod_dm_play'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', DM_DISC_IMAGE + '_down'), ('style:normal:icon', DM_DISC_IMAGE), ('style:over:icon', DM_DISC_IMAGE)])
    sec.children = [head, card, play]
    for name, px, colour in (('pod_dm_title', D.DM_TITLE_PX, '#FFFFFF'), ('pod_dm_sub', D.DM_SUB_PX, '#%02X%02X%02X' % D.SUB_RGB)):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        sec.children.append(lab)
    return sec


# The keyboard page (patch/keyboard.c, docs/modules/keyboard.md; geometry: tools/pod_keyboard.py): the plain navbar, the search field (magnifier, grey hint, text, caret, clear button),
# the 180 px pad of buttons at the bottom of the window (26 char keys laid out as the lowercase page, the function keys; the payload moves, relabels and hides them per page), and
# last the key pop-up (a stem and a balloon with the letter): insensitive, shown by the payload while a key is down. White and grey only.
def kb_button(name, x, y, w, fill, down, ink=PK.KB_INK, px=20, text=None, icon=None):
    b = Widget('button', x, y, w, PK.KB_KH, [('name', name), ('enable', 'true')] + ([text] if text else []))
    for st in STATES:
        styled(b, (st,), 'bg_color', down if st == 'pressed' else fill)
        styled(b, (st,), 'text_color', ink)
        styled(b, (st,), 'font_size', str(px))
        styled(b, (st,), 'border_width', '0')
        styled(b, (st,), 'round_radius', str(PK.KB_RADIUS))
        if icon: styled(b, (st,), 'icon', icon)
    return b


def kb_view(name, x, y, w, h, fill, radius=0):
    v = Widget('view', x, y, w, h, [('name', name), ('sensitive', 'false')])
    for st in STATES:
        styled(v, (st,), 'bg_color', fill)
        styled(v, (st,), 'border_width', '0')
        if radius: styled(v, (st,), 'round_radius', str(radius))
    return v


def keyboard_pad_widgets():
    """The pad, the candidate strip and the key pop-up (patch/keyboard.c), in paint order: [pad, strip, stem, pop]. The keyboard page and the Search page (which embeds the keyboard,
    keyboard_attach) both end with these, so the payload finds the same widgets by the same names in either."""
    pad = Widget('view', 0, CLIENT_H - PK.KB_H, SCREEN_W, PK.KB_H, [('name', 'kb_pad'), ('enable', 'true')])
    for st in STATES:
        styled(pad, (st,), 'bg_color', PK.KB_BG)
        styled(pad, (st,), 'border_width', '0')
    lay = PK.layout('abc')
    for i, (c, x, y, w) in enumerate(lay['keys']):
        pad.children.append(kb_button(f'kb_k{i}', x, y, w, PK.KB_KEY, PK.KB_KEY_DOWN, text=('text', c)))
    fx, fy, fw = lay['fn']['shift']
    pad.children.append(kb_button('kb_shift', fx, fy, fw, PK.KB_FN, PK.KB_FN_DOWN, icon='qk_shift'))
    pad.children.append(hidden(kb_button('kb_shifton', fx, fy, fw, PK.KB_ON, PK.KB_ON_DOWN, icon='qk_shifton')))
    pad.children.append(hidden(kb_button('kb_sym', fx, fy, fw, PK.KB_FN, PK.KB_FN_DOWN, px=15, text=('text', '#+='))))
    x, y, w = lay['fn']['del']
    pad.children.append(kb_button('kb_del', x, y, w, PK.KB_FN, PK.KB_FN_DOWN, icon='qk_delete'))
    x, y, w = lay['fn']['mode']
    pad.children.append(kb_button('kb_mode', x, y, w, PK.KB_FN, PK.KB_FN_DOWN, px=15, text=('text', '123')))
    x, y, w = lay['fn']['space']
    pad.children.append(kb_button('kb_space', x, y, w, PK.KB_KEY, PK.KB_KEY_DOWN, px=15, text=pod_i18n.text_prop('space')))
    x, y, w = lay['fn']['go']
    pad.children.append(kb_button('kb_go', x, y, w, PK.KB_FN, PK.KB_FN_DOWN, px=15, text=pod_i18n.text_prop('Search')))
    lx, ly, lw = PK.layout('abc', lang=True)['fn']['lang']   # the language key: hidden until the payload finds a second keyboard enabled, then space gives it the room
    pad.children.append(hidden(kb_button('kb_lang', lx, ly, lw, PK.KB_FN, PK.KB_FN_DOWN, px=18, text=('text', PK.LANG_TAGS[0]))))
    # The candidate strip (Chinese layer), a window child before the pop-up so that the balloons of the top row paint over it. It must be sensitive for its candidates view inside it to take
    # touches (stock's hit test does not look into an insensitive parent); hidden() takes it out of the hit test while it is not shown, the payload shows both together.
    strip = hidden(kb_view('kb_strip', 0, PK.STRIP_Y, SCREEN_W, PK.STRIP_H, PK.STRIP_BG))
    py = label('kb_py', PK.PY_X, 0, PK.PY_MAX, PK.STRIP_H, '', PK.PY_PX, PK.STRIP_PY_INK, 'left')
    sep = hidden(kb_view('kb_sep', 0, PK.SEP_Y, 1, PK.SEP_H, PK.STRIP_SEP))
    cands = Widget('view', 0, 0, SCREEN_W, PK.STRIP_H, [('name', 'kb_cands'), ('enable', 'true')])
    for st in STATES:
        styled(cands, (st,), 'bg_color', PK.STRIP_BG)
        styled(cands, (st,), 'border_width', '0')
    chl = hidden(kb_view('kb_chl', 0, PK.CHL_Y, PK.CAND_MIN, PK.CHL_H, PK.KB_KEY, PK.KB_RADIUS))
    items = [hidden(label(f'kb_c{i}', 0, 0, PK.CAND_MIN, PK.STRIP_H, '', PK.CAND_PX, PK.KB_INK, 'left')) for i in range(PK.POOL)]
    for lab in [py] + items:
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
    cands.children = [chl] + items
    strip.set('sensitive', 'false')
    strip.children = [py, sep, cands]
    stem = hidden(kb_view('kb_stem', 0, 0, PK.KB_KW, PK.KB_STEM_UP + PK.KB_KH, PK.KB_POP, PK.KB_RADIUS))
    pop = hidden(kb_view('kb_pop', 0, 0, PK.KB_POP_W, PK.KB_POP_H, PK.KB_POP, PK.KB_POP_R))
    glyph = label('kb_pop_l', 0, 0, PK.KB_POP_W, PK.KB_POP_H, '', PK.KB_POP_PX, PK.KB_INK, 'center')
    glyph.set('sensitive', 'false')
    styled(glyph, ('normal',), 'text_align_v', 'middle')
    pop.children.append(glyph)
    return [pad, strip, stem, pop]


def build_keyboard_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    field = kb_view('kb_field', PK.FIELD_X, PK.FIELD_Y, PK.FIELD_W, PK.FIELD_H, PK.KB_BG, PK.FIELD_R)
    field.set('sensitive', 'true')   # the clear button inside it needs it: stock's hit test does not look into an insensitive parent
    mag = Widget('image', PK.FIELD_MAG_X, (PK.FIELD_H - PK.FIELD_MAG) // 2, PK.FIELD_MAG, PK.FIELD_MAG, [('name', 'kb_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')])
    hint = label('kb_hint', PK.FIELD_TEXT_X, 0, PK.FIELD_TEXT_W, PK.FIELD_H, '', PK.FIELD_PX, PK.KB_GREY, 'left')
    text = label('kb_text', PK.FIELD_TEXT_X, 0, PK.FIELD_TEXT_W, PK.FIELD_H, '', PK.FIELD_PX, PK.KB_INK, 'left')
    for lab in (hint, text):
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
    caret = kb_view('kb_caret', PK.FIELD_TEXT_X, PK.CARET_Y, PK.CARET_W, PK.CARET_H, PK.KB_INK)
    clear = hidden(Widget('button', PK.FIELD_CLEAR_X, 0, PK.FIELD_CLEAR_W, PK.FIELD_H, [('name', 'kb_clear'), ('enable', 'true'), ('style', 'img_btn_style'),
                   ('style:pressed:icon', 'qk_clear'), ('style:normal:icon', 'qk_clear'), ('style:over:icon', 'qk_clear')]))
    field.children = [mag, hint, text, caret, clear]
    root.children.append(field)
    root.children += keyboard_pad_widgets()
    return root


# The Folders page (patch/folders.c, docs/modules/folders.md): the Songs page's structure without its sections, rail, sort card and count. The glass navbar (Back, the small title, Select | Now Playing as one
# capsule: Select is the left cap, Now Playing the right cap) over a stock list whose one child, view_grid, holds the large title and the Play / Shuffle pills (the payload shows the pills for a folder that holds an
# audio file) and has the rows painted into it; the select mode's Select All text and bar are the Songs page's.
def build_folders_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, select=True)
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    for c in nb.children:
        if c.name == 'btn_select':   # shown from the start: the capsule's left cap
            c.remove('visible'); c.remove('sensitive')
        elif c.name == 'btn_backtoplayer':   # the capsule's right cap
            for st, img in (('pressed', 'ah_nav_play_down'), ('normal', 'ah_nav_play'), ('over', 'ah_nav_play')): c.set(f'style:{st}:icon', img)
    nb.children.append(selall_button())
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'folders_listview')
    sv = lv.children[0]
    sv.set('name', 'folders_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = Widget('label', o['SG_TITLE_X'], 0, 250, o['SG_TITLE_H'], [('name', 'sg_title'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
    styled(title, ('normal',), 'text_color', '#FFFFFF')
    styled(title, ('normal',), 'font_size', str(SG_TITLE_PX))
    styled(title, ('normal',), 'text_align_h', 'left')
    styled(title, ('normal',), 'text_align_v', 'middle')
    grid.children = [title, hidden(sg_pill('btn_play', o['SG_PILL_X0'], o['SG_PILL_Y'], 'Play', 'sg_play', down=SG_PILL_PRESS_RGB)),
                     hidden(sg_pill('btn_shuffle', o['SG_PILL_X1'], o['SG_PILL_Y'], 'Shuffle', 'sg_shuffle', down=SG_PILL_PRESS_RGB))]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/folders.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, '#FFFFFF')))
    lab = hidden(label('label_row_title', 0, 0, 10, 10, '', LIST_TITLE_PX, '#FFFFFF', 'left'))   # the text style only (widget_prepare_text_style); never shown
    styled(lab, ('normal',), 'text_align_v', 'middle')
    root.children.append(lab)
    root.children.append(select_bar('sg_bar', 'sg_bar_line', [('sg_add', o['SG_PILL_X0'], 'Add to Playlist', 'sg_listplus', o['SG_BAR_PILL_W']),
                                                              ('sg_del', o['SG_BAR_PILL_X1'], 'Delete', 'sg_trash', o['SG_BAR_PILL_W'])]))
    return root
RD_FIELD_W = SCREEN_W - 2 * PS.SE_FIELD_X   # the Radio search field's width (patch/radiopage.c RP_TEXT_W is its text's)
RD_TEXT_W = RD_FIELD_W - PS.SE_TEXT_X - PS.SE_CLEAR_W
RD_CREDIT_PX = 14   # the credit line's size (patch/radiopage.c RP_CREDIT_PX)
RD_SHEET_ROWS = (('add', 'pod_ic_rd_add', 'Add to My Stations', False, False), ('info', 'pod_ic_rd_info', 'Station Info', False, False))   # Radio Now Playing's sheet: two rows, the first's glyph and label swapped for Remove from My Stations by the payload (patch/radionp.c)
RS_SHEET_ROWS = (('import', 'pod_ic_rd_import', 'Import from Card', False, False), ('clear', 'pc_ic_trash', 'Clear Recently Played', False, False))   # the "..." sheets (patch/radiopage.c): My Stations has Import from Card, Recently Played Clear Recently Played (the payload shows one row)


def build_radio_page(page):
    """The Radio page (patch/radiopage.c, docs/modules/radio.md): the Folders page's structure (the glass navbar with the globe as its left cap, a stock list holding one view the payload
    paints, the large title in that view) and the station grid's and the countries' text styles."""
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, show_globe=True, show_more=True)   # btn_more: the Stations level's "...", the capsule's left cap where Search sits (hidden; the payload places and shows it)
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    nb.children[0].w = NAV_VIEW_X - NAV_TITLE_X
    for c in nb.children:
        if c.name == 'btn_globe':   # the magnifier (Search), shown from the start: the capsule's left cap
            c.remove('visible'); c.remove('sensitive')
            c.set('name', 'btn_search')
            for st, img in (('pressed', 'pod_nav_search_down'), ('normal', 'pod_nav_search'), ('over', 'pod_nav_search')): c.set(f'style:{st}:icon', img)
        elif c.name == 'btn_backtoplayer':   # the capsule's right cap
            for st, img in (('pressed', 'ah_nav_play_down'), ('normal', 'ah_nav_play'), ('over', 'ah_nav_play')): c.set(f'style:{st}:icon', img)
    view_btn = Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [   # the station lists' grid / list toggle (the Albums page's): the middle piece beside Search, shown by the payload on the station lists
        ('name', 'btn_radioview'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', 'pod_nav_list_down'), ('style:normal:icon', 'pod_nav_list'), ('style:over:icon', 'pod_nav_list')])
    view_btn.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))   # (its 60 px glyph paints beyond the 46 px slot, as on the Albums page)
    nb.children.append(hidden(view_btn))
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'radio_listview')
    sv = lv.children[0]
    sv.set('name', 'radio_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = Widget('label', o['SG_TITLE_X'], 0, SCREEN_W - 2 * o['SG_TITLE_X'], o['SG_TITLE_H'], [('name', 'sg_title'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
    styled(title, ('normal',), 'text_color', '#FFFFFF')
    styled(title, ('normal',), 'font_size', str(SG_TITLE_PX))
    styled(title, ('normal',), 'text_align_h', 'left')
    styled(title, ('normal',), 'text_align_v', 'middle')
    credit = hidden(label('rd_credit', 0, 0, SCREEN_W - 2 * 12, 20, '', RD_CREDIT_PX, '#8E8E93', 'left'))   # the directory's credit under its rows (patch/radiopage.c moves it and shows it)
    credit.set(*pod_i18n.text_prop('Stations from radio-browser.info'))
    styled(credit, ('normal',), 'text_align_v', 'middle')
    grid.children = [title, credit]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/radiopage.c shows it while yoffset > 0 (at rest it would darken the large title)
    status = hidden(label('label_status', 20, 165, SCREEN_W - 40, 120, '', 18, '#8E8E93'))   # the captions are grey, centred on y 225; up to four lines of 280 px (the payload sets line_wrap and word_wrap)
    styled(status, ('normal',), 'text_align_v', 'middle')
    root.children.append(status)
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, '#FFFFFF'), ('label_row_sub', LIST_SUB_PX, '#AAAAAA'),
                             ('label_grid_title', GRID_ALBUM_PX, '#FFFFFF'), ('label_grid_sub', GRID_ARTIST_PX, '#AAAAAA')):   # the row and the Albums grid's text styles (never shown)
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    root.children.extend(azlist_labels())   # the countries' A-Z list (patch/azlist.c): the header letter, the rail letters
    root.children.extend(azlist_rail())
    field = search_field_widget()   # the search page's field and pad (keyboard_attach): hidden until the magnifier is tapped
    field.y = 56
    field.w = RD_FIELD_W   # no round X beside it here (the Search page's 250 leaves room for one): it runs the page's width, the Search page's margin each side
    for c in field.children:
        if c.name == 'kb_clear': c.x = RD_FIELD_W - PS.SE_CLEAR_W
        elif c.name in ('kb_hint', 'kb_text'): c.w = RD_TEXT_W
    hidden(field); field.set('sensitive', 'false')
    root.children.append(field)
    root.children += keyboard_pad_widgets()
    root.children.extend(sheet_widgets(RN_SHEET, RS_SHEET_ROWS, 1))   # the Stations "..." sheet, last: above everything
    return root


RN_SHEET = 'rd_sh'   # the stations page's station sheet, the same widget set
RN_CARD_GLYPH = '#2C2C2E'   # the art card without a logo (patch/radionp.c RN_CARD_GLYPH); with one it is white and the window takes the logo's tone
RN_ART_R = 10   # the art card's corners (the album page's)
RDN_TITLE_PX, RDN_LINE_PX, RDN_LIVE_PX, RDN_LIVE_Y, RN_PLAY = 22, 17, 13, 366, 64


def build_radionp_page(page):
    """Radio's Now Playing (patch/radionp.c): Apple Music's radio page on this player's Now Playing numbers (tools/mod_nowplaying.py): the grabber, a square art card with the station's logo (or the
    radio glyph) over a tinted window, the station's name and a line under it, the round "..." (the sheet holds Add to / Remove from My Stations), a LIVE divider and one large play / stop button.
    Widgets the payload looks up that the design no longer shows are kept hidden and insensitive (btn_fav, btn_prev, btn_next, rn_station, rn_info, rn_elapsed)."""
    import mod_nowplaying as NP
    W, H = SCREEN_W, CLIENT_H
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', NP.BG)
    root.children.append(Widget('image', 0, 0, W, H, [('name', 'img_np_tint'), ('image', 'np_tint'), ('draw_type', 'default'), ('clickable', 'false'), ('sensitive', 'false')]))
    art = Widget('view', NP.ART_X, NP.ART_Y, NP.ART, NP.ART, [('name', 'rn_art'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(art, (st,), 'bg_color', RN_CARD_GLYPH)
        styled(art, (st,), 'round_radius', str(RN_ART_R))
        styled(art, (st,), 'border_width', '0')
    glyph_px = 96
    art.children.append(Widget('image', (NP.ART - glyph_px) // 2, (NP.ART - glyph_px) // 2, glyph_px, glyph_px, [('name', 'rn_art_ic'), ('image', 'pod_ic_rd_art'), ('draw_type', 'default'),
                                                                                                              ('clickable', 'false'), ('sensitive', 'false')]))
    root.children.append(art)
    root.children.append(Widget('image', NP.ART_X - NP.SHADOW_PAD, NP.ART_Y - NP.SHADOW_PAD, NP.SHADOW_SIZE, NP.SHADOW_SIZE, [('name', 'img_np_shadow'), ('image', 'np_shadow'), ('draw_type', 'default'),
                                                                                                                       ('clickable', 'false'), ('sensitive', 'false')]))
    def text(name, x, y, w, h, px, rgb, align):
        t = Widget('hscroll_label', x, y, w, h, [('name', name), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        NP.text_style(t, px, rgb, align)
        for st in NP.STATES: styled(t, (st,), 'text_align_v', 'middle')
        return t
    tw = NP.MORE_X - NP.M - 8   # the block runs to the "..." disc
    root.children.append(text('rn_title', NP.M, NP.TITLE_Y - 4, tw, 30, RDN_TITLE_PX, NP.TITLE_RGB, 'left'))
    root.children.append(text('rn_artist', NP.M, NP.ARTIST_Y + 2, tw, 22, RDN_LINE_PX, NP.GREY, 'left'))
    more = Widget('button', NP.MORE_X, NP.BTN_Y, NP.BTN, NP.BTN, [('name', 'rn_more'), ('enable', 'true')])
    NP.img_button(more, 'np_more', 'np_more_down')
    root.children.append(more)
    # the LIVE divider: a 4 px capsule each side (rn_live_l / rn_live_r, alpha fading towards LIVE) around a small white LIVE
    lw, live_w, side = NP.W - 2 * NP.M, NP.LIVE_W, NP.LIVE_BAR_W
    live = Widget('view', NP.M, RDN_LIVE_Y, lw, 16, [('name', 'rn_live'), ('sensitive', 'false'), ('visible', 'false')])
    for st in NP.STATES:
        styled(live, (st,), 'bg_color', '#00000000')
        styled(live, (st,), 'border_width', '0')
    for name, x in (('rn_live_l', 0), ('rn_live_r', lw - side)):
        live.children.append(Widget('image', x, (16 - NP.LIVE_BAR_H) // 2, side, NP.LIVE_BAR_H, [('name', name), ('image', name), ('draw_type', 'default'), ('clickable', 'false'), ('sensitive', 'false')]))
    tx = Widget('label', (lw - live_w) // 2, 0, live_w, 16, [('name', 'rn_live_tx'), pod_i18n.text_prop('LIVE'), ('sensitive', 'false')])
    NP.text_style(tx, RDN_LIVE_PX, '#FFFFFF', 'center')
    for st in NP.STATES: styled(tx, (st,), 'text_align_v', 'middle')
    live.children.append(tx)
    root.children.append(live)
    play = Widget('button', (W - RN_PLAY) // 2, RDN_LIVE_Y + 18, RN_PLAY, RN_PLAY, [('name', 'btn_play'), ('enable', 'true')])
    NP.img_button(play, 'rn_play', 'rn_play_down')
    root.children.append(play)
    # kept for the payload, hidden and insensitive
    fav = Widget('button', NP.FAV_X, NP.BTN_Y, NP.BTN, NP.BTN, [('name', 'btn_fav'), ('enable', 'true')])
    NP.img_button(fav, 'np_unfav', 'np_unfav_down')
    root.children.append(hidden(fav))
    for n, (x, w), normal, pressed in (('btn_prev', NP.SLOTS['btn_prev'], 'np_prev', 'np_prev_down'), ('btn_next', NP.SLOTS['btn_next'], 'np_next', 'np_next_down')):
        b = Widget('button', x, NP.ROW_Y, w, NP.ROW_H, [('name', n), ('enable', 'true')])
        NP.img_button(b, normal, pressed)
        root.children.append(hidden(b))
    root.children.append(hidden(text('rn_station', NP.M, NP.TIMES_Y, 190, NP.TIMES_H, NP.TIMES_PX, NP.GREY, 'left')))
    root.children.append(hidden(text('rn_info', W - NP.M - 130, NP.TIMES_Y, 130, NP.TIMES_H, NP.TIMES_PX, NP.GREY, 'right')))
    root.children.append(hidden(text('rn_elapsed', W - NP.M - NP.TIMES_W, NP.TIMES_Y, NP.TIMES_W, NP.TIMES_H, NP.TIMES_PX, NP.GREY, 'right')))
    ret = Widget('button', *NP.RETURN, [('name', 'btn_return'), ('enable', 'true')])
    NP.img_button(ret, 'np_grabber', 'np_grabber_down')
    root.children.append(ret)
    root.children.append(hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)])))   # (the page's name for the i18n and asset tests)
    root.children.extend(sheet_widgets(RN_SHEET, RD_SHEET_ROWS, 2))   # the station's sheet (two rows), last: above everything
    return root


# Station Info (patch/radioinfo.c, docs/modules/radio.md "Station Info"): the Release Notes page's structure (the stock navbar over a stock list holding one content view the payload paints the heading and the
# label / value pairs on, wrapped by the Podcasts episode page's wrapper). Three hidden labels only carry the text styles: the station's name (28 px white), a pair's label (14 px grey), its value (18 px white).
SI_HEAD_PX, SI_KEY_PX, SI_VAL_PX = 28, 14, 18


def build_radioinfo_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'ri_listview')
    sv = lv.children[0]
    sv.set('name', 'ri_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, CLIENT_H - NAVBAR_H, [('name', 'ri_view')])
    styled(view, ('normal',), 'bg_color', '#000000')
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # the payload shows it while the content is scrolled (at rest it would darken the heading)
    for name, px, colour in (('label_head', SI_HEAD_PX, '#FFFFFF'), ('label_key', SI_KEY_PX, '#8E8E93'), ('label_val', SI_VAL_PX, '#FFFFFF')):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    return root


def build_page(page):
    if page.kind == 'radio':
        return build_radio_page(page)
    if page.kind == 'radioinfo':
        return build_radioinfo_page(page)
    if page.kind == 'radionp':
        return build_radionp_page(page)
    if page.kind == 'folders':
        return build_folders_page(page)
    if page.kind == 'cards':
        return build_cards_page(page)
    if page.kind == 'keyboard':
        return build_keyboard_page(page)
    if page.kind in ('menucfg', 'pdcfg'):
        return build_menucfg_page(page)
    if page.kind == 'extrascfg':
        return build_extrascfg_page(page)
    if page.kind == 'covlist':
        return build_grid_page(page, toggle=None, coverflow=False, names=('covlist_listview', 'covlist_scrollview'))
    if page.kind == 'grid':
        return build_grid_page(page)
    if page.kind == 'podcasts':
        return build_podcasts_page(page)
    if page.kind == 'playlists':
        return build_playlists_page(page)
    if page.kind == 'songs':
        return build_songs_page(page)
    if page.kind == 'search':
        return build_search_page(page)
    if page.kind == 'subsonic':
        return build_subsonic_page(page)
    if page.kind == 'album':
        return build_album_page(page)
    if page.kind == 'queue':
        return build_queue_page(page)
    if page.kind == 'dailymix':
        return build_dailymix_page(page)
    if page.kind == 'ipod':
        return build_ipod_page(page)
    if page.kind == 'tape':
        return build_tape_page(page)
    if page.kind == 'vinyl':
        return build_vinyl_page(page)
    if page.kind == 'onlineart':
        return build_onlineart_page(page)
    if page.kind == 'update':
        return build_update_page(page)
    if page.kind == 'relnotes':
        return build_relnotes_page(page)
    if page.kind == 'cover':
        return build_cover_page(page)
    if page.kind == 'artists':
        return build_artists_page(page)
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title, settings=page is pod_pages.EXTRAS_PAGE))
    lv = stock_list(page.rows, len(page.rows) * ROW_H > CLIENT_H - NAVBAR_H)
    root.children.append(lv)
    root.children.append(nav_fade())
    if page is pod_pages.EXTRAS_PAGE:   # the group headers, after the rows (the payload shows the ones whose group has a row and stacks them in place)
        lv.children[0].children += extras_headers(lv.children[0].w)
    if page is pod_pages.MENU:   # the mini player bar (shown by the payload, on the Home instance only) and the list's padding under it
        sv = lv.children[0]
        assert sv.w == SH_W
        sv.children.append(daily())   # after the rows, before the shelf: the Daily Mix card (the payload moves it below the last shown row and shows it when there is a mix)
        sv.children.append(shelf())   # then the shelf (the payload moves it below the last shown row and shows it when there are albums to show)
        sv.children.append(hidden(Widget('view', 0, len(page.rows) * ROW_H, sv.w, MB_PAD, [('name', 'pod_pad')])))   # last child; the payload shows it with the bar
        root.children.append(cover_progress())   # (hidden; the bar stays the last child: it paints over everything)
        root.children.append(minibar())
    return root


def write_assets(rootfs, pages):
    out = []
    for page in pages:
        root = build_page(page)
        data = awtk_ui.serialize(root)
        assert awtk_ui.parse(data).name == page.name, 'round-trip name mismatch'
        assert awtk_ui.serialize(awtk_ui.parse(data)) == data, 'asset does not round-trip byte-exact'
        rel = f'{UI}/{page.key}.bin'
        path = os.path.join(rootfs, rel)
        with open(path, 'wb') as f: f.write(data)
        os.chmod(path, UI_MODE)
        os.utime(path, (UI_MTIME, UI_MTIME))   # deterministic build: fixed mtime on added files
        out.append((rel, len(data)))
    return out


SYSTEM_BAR = f'{UI}/system_bar.bin'
SHOT_WIDGET = 'pod_shot'      # patch/shot.h SHOT_IND
SHOT_IMAGE, SHOT_W = 'pod_bar_shot', 16   # the 16 px camera tools/mod_icons.py adds to images/xx


def add_shot_indicator(rootfs):
    """The Screenshot countdown's camera: one hidden, insensitive image, the last child of the status bar's right-aligned
    icon group (view_bar_right, so after the Wi-Fi icon and next to the battery outline). The group's layouter skips
    an invisible child (widget_get_children_for_layout 0x657194, keep_invisible off), so while it is hidden the bar is
    laid out as stock; patch/shot.c shows it for the countdown, and the group then makes room for it: the icons to its
    left move 16 + 4 px left, the clock and the left group stay put."""
    def edit(root):
        right = root.find('view_bar_right')
        assert right is not None and root.find(SHOT_WIDGET) is None, 'unexpected system_bar layout'
        right.children.append(hidden(Widget('image', 0, 0, SHOT_W, 0, [('name', SHOT_WIDGET), ('image', SHOT_IMAGE), ('draw_type', 'center')])))
    from modlib import edit_ui
    edit_ui(os.path.join(rootfs, SYSTEM_BAR), edit)


PCT_WIDGET, PCT_WIDGET_DD = 'pod_pct', 'pod_pct_dd'   # patch/battery.h BP_LABEL, BP_LABEL_DD
PCT_FONT = 'release/assets/default/raw/fonts/default.ttf'


def pct_widths(font_path):
    """The percentage label's box width (AWTK text width at statusbar.PCT_PX: truncated advances + 1 px per glyph, tools/awtk_text.py StbText) for a text of 2, 3 and 4
    characters ("5%", "87%", "100%"); the widest digit decides, so every number of that length fits."""
    import statusbar
    from awtk_text import Ttf, StbText
    st = StbText(Ttf(font_path), statusbar.PCT_PX)
    wid = max(st.layout(d)[1] for d in '0123456789')
    pct = st.layout('%')[1]
    return tuple((n - 1) * wid + pct for n in (2, 3, 4))


def add_battery_label(rootfs):
    """The Battery Percentage label (patch/battery.c): a hidden, insensitive white label in the status bar's right-aligned icon group, and its twin in the pull-down's own bar (both
    dropdown_dialog.bin themes). It is the group's last child but the Screenshot camera (the camera, when it counts down, stays against the battery outline), so shown it sits
    4 px before the outline and the icons to its left move aside by its width (the group's layouter skips an invisible child); the payload sets its text and width."""
    import statusbar
    w3 = pct_widths(os.path.join(rootfs, PCT_FONT))[1]

    def edit_for(name):
        def edit(root):
            right = root.find('view_bar_right')
            assert right is not None and root.find(name) is None, 'unexpected status bar layout'
            props = [('name', name), ('text', '87%')]
            for st in statusbar.STATES:
                props += [(f'style:{st}:text_color', '#FFFFFF'), (f'style:{st}:font_size', str(statusbar.PCT_PX)),
                          (f'style:{st}:text_align_h', 'right'), (f'style:{st}:text_align_v', 'middle')]
            label = hidden(Widget('label', 0, 0, w3, 0, props))
            at = len(right.children) - 1 if right.children and right.children[-1].name == SHOT_WIDGET else len(right.children)
            right.children.insert(at, label)
        return edit
    from modlib import edit_ui
    edit_ui(os.path.join(rootfs, SYSTEM_BAR), edit_for(PCT_WIDGET))
    edit_ui(os.path.join(rootfs, 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), edit_for(PCT_WIDGET_DD))


def asset_rels(pages):
    return [f'{UI}/{p.key}.bin' for p in pages]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir')
    a = ap.parse_args()
    rootfs = os.path.join(a.workdir, 'rootfs') if os.path.isdir(os.path.join(a.workdir, 'rootfs')) else a.workdir
    for rel, n in write_assets(rootfs, pod_pages.PAGES):
        print(f'wrote {rel} ({n} bytes)')


if __name__ == '__main__': main()

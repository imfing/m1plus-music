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
import cdefs
from awtk_ui import Widget
import pod_i18n, pod_pages
import pod_keyboard as PK
import pod_search as PS
from pod_roles import INK_RGB, SUB_RGB, HINT_RGB, RED_RGB, PLACEHOLDER_RGB, CHEV_RGB, DIM_RGB, RAISED_RGB, SURFACE_RGB, LINE_RGB, SECTION_PX, CAPTION_LABEL_Y, CAPTION_LABEL_H, CAPTION_PX

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


def room_y(h, top=NAVBAR_H):
    """The y of a block h high centred in the room under window y `top` (the navbar's bottom, or a kept large title's; patch/libsrc.c ls_room): a page's empty-state hint and its loading spinner."""
    return top + (CLIENT_H - top - h) // 2


def styled(w, states, prop, value):
    for st in states: w.set(f'style:{st}:{prop}', value)


OFFSETS = cdefs.defines(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patch', 'offsets.inc'))


# The navbar toggle of the Pod pages (Albums grid, Artists), flush left of Now Playing (x 260): a plain white glyph
# showing the view a tap switches to (the Albums page swaps the glyph with its mode, as the Artists page does).
NAV_VIEW_X, NAV_VIEW_W = 214, 46     # patch/offsets.inc NAV_VIEW_X, NAV_VIEW_W: main's slots (docs/modules/navbar.md); the glass capsule's pieces are cut to them (docs/modules/navbar.md)
NAV_VIEW_ICON = {'list': 'pod_nav_list', 'grid': 'pod_nav_grid'}   # images added by tools/mod_icons.py (glass pieces)
TOGGLE_NAME = {'list': 'btn_albumview', 'grid': 'btn_albumview'}
# The Albums page's Cover Flow button, flush left of the toggle: the capsule's left cap.
NAV_CF_W = NAV_VIEW_W
NAV_CF_X = NAV_VIEW_X - NAV_CF_W     # 168; patch/offsets.inc NAV_CF_X, NAV_CF_W
NAV_CF_ICON = 'pod_nav_coverflow'
NAV_ICON_OVERFLOW = 7               # 60 px icons centred in 46 px slots paint 7 px beyond their touch rectangles
NAV_BACK_X, NAV_BACK_W = 7, 44       # Back: the glass disc ah_nav_back (42 px) centred in a 44 x 50 button: x 8 .. 50, y 4 .. 46 (img_btn_style, so the shared navbar_btnreturn_style and the stock pages are untouched)
NAV_TITLE_X = 58                     # the title starts 8 px after the disc
NAV_PLAY_X, NAV_PLAY_W = 260, 60     # Now Playing: main's button; its image is the disc ah_nav_np alone (glyph centre 290) or a capsule's right cap ah_nav_play (same glyph, the glass ends at x 311)
NAV_TITLE_END = NAV_PLAY_X            # a title with no toggle ends before Now Playing's button (its disc starts at 269)


NAV_SONGS_ICON = 'pod_nav_listl'   # the list glyph on the capsule's left cap: the Radio results' toggle's image
NB_FADE_NAME, NB_FADE_H = 'img_nb_fade', 20     # the soft fade under the bar (tools/mod_icons.py NB_FADE; mod_ipodrows.NB_FADE_NAME)


def nav_fade(shown=True):
    """The fade over the first rows of the list under the bar: an insensitive image (never takes a touch), right after the list.
    shown=False (the cover pages, whose first row would be darkened at rest): built hidden, the page's code shows it while the list is scrolled."""
    w = Widget('image', 0, NAVBAR_H, SCREEN_W, NB_FADE_H, [('name', NB_FADE_NAME), ('image', 'nb_fade'), ('draw_type', 'default'),
                                                           ('clickable', 'false'), ('sensitive', 'false')])
    if not shown: w.set('visible', 'false')
    return w


ALBUMS_BUTTONS = (('btn_coverflow', 'pod_nav_coverflow', 168), ('btn_more', 'pod_nav_moremid', 214))   # the Albums page's capsule: Cover Flow (left cap), "..." (middle), then Now Playing (the Songs page's slots 168 / 214 / 260)


NAV_SETTINGS_ICON = 'pod_nav_settings'   # the Extras page's Settings button: the capsule's left cap on the 214 slot (tools/mod_icons.py)


def navbar(title, toggle=None, coverflow=False, artist_songs=False, more=False, songs=False, settings=False, show_more=False, show_globe=False, albums=False, more_left=False, plactions=False, settings_icon=NAV_SETTINGS_ICON, search=False):
    nb = Widget('view', 0, 0, SCREEN_W, NAVBAR_H, [('name', 'navigationbar_view')])
    # a title runs under a toggle's button no further than the button's left edge
    right = NAV_CF_X if songs or plactions or coverflow or more or albums else NAV_VIEW_X if toggle or settings or show_more or more_left else NAV_TITLE_END
    lbl = Widget('label', NAV_TITLE_X, 14, right - NAV_TITLE_X, 22,
                 [('name', 'label_title'), ('style', 'navbar_label_white'), ('length', '31'), pod_i18n.text_prop(title)])
    ret = Widget('button', NAV_BACK_X, 0, NAV_BACK_W, NAVBAR_H, [
        ('name', 'btn_return'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:over:icon', 'ah_nav_back'), ('style:normal:icon', 'ah_nav_back'), ('style:pressed:icon', 'ah_nav_back_down')])
    img = 'ah_nav_play' if toggle or coverflow or more or songs or plactions or settings or albums or more_left else 'ah_nav_np'   # a toggle / button makes Now Playing the capsule's right cap; else a disc
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
            ('style:pressed:icon', settings_icon + '_down'), ('style:normal:icon', settings_icon), ('style:over:icon', settings_icon)]))
    if show_more:   # the Podcasts page's "..." (opens a bottom sheet): the capsule's left cap on the 214 slot, shown on the Show level and on the Shows level when Import is possible (patch/podcasts.c)
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_more'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_more_down'), ('style:normal:icon', 'pod_nav_more'), ('style:over:icon', 'pod_nav_more')])))
    if more_left:   # the Artists page's "...": the capsule's left cap on the 214 slot, shown always (its card holds Search, the Artist / Album Artist rows and the order; patch/artists.c)
        mid = 'pod_nav_moremid' if plactions else 'pod_nav_more'   # (the Playlists page: the list-plus button is the left cap and the "..." the middle piece)
        nb.children.append(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_more'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', mid + '_down'), ('style:normal:icon', mid), ('style:over:icon', mid)]))
    if plactions:   # the Playlists page's list-plus button (patch/playlists.c): the capsule's left cap on the Albums page's Cover Flow slot (NAV_CF_X), opening the actions card
        nb.children.append(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_plactions'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_listplus_down'), ('style:normal:icon', 'pod_nav_listplus'), ('style:over:icon', 'pod_nav_listplus')]))
    if show_globe:   # the Podcasts page's globe (Apple Podcasts search, only while Podcast Discover is on in Settings): the capsule's left cap, on the 168 slot with the "..." as its middle piece, or on the 214 slot beside Now Playing alone (patch/podcasts.c pg_nav moves it)
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
    if albums:   # the Albums page's capsule: Cover Flow 168 (left cap), "..." 214 (middle), Now Playing 260; Search and the grid / list switch are rows of the "..." card (patch/albums.c, docs/modules/albums.md)
        for name, icon, x in ALBUMS_BUTTONS:
            nb.children.append(Widget('button', x, 0, NAV_VIEW_W, NAVBAR_H, [
                ('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)]))
    if songs:   # the "..." (its card holds Select, Recently Added's Albums / Songs and the library's sort rows; patch/songs.c): the capsule's left cap on 214, a middle piece where Search (the lists that search) or Cover Flow (an artist's songs) is the left cap
        nb.children.append(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_more'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_more_down'), ('style:normal:icon', 'pod_nav_more'), ('style:over:icon', 'pod_nav_more')]))
    if songs:   # Select (patch/songs.c shows it instead of the "..." on the lists whose card would hold Select alone): the capsule's left cap on 214, a middle piece where Search or Cover Flow is the left cap; it enters select mode at once
        nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
            ('name', 'btn_select'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_selectl_down'), ('style:normal:icon', 'pod_nav_selectl'), ('style:over:icon', 'pod_nav_selectl')])))
    if songs:   # the artist's songs list (patch/songs.c shows it there only): the Cover Flow button, the capsule's left cap on the Albums page's slot (NAV_CF_X), back to the covers
        nb.children.append(hidden(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_coverflow'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', NAV_CF_ICON + '_down'), ('style:normal:icon', NAV_CF_ICON), ('style:over:icon', NAV_CF_ICON)])))
    if songs:   # Search (patch/songs.c shows it on every list but a genre's and an artist's songs): the capsule's left cap on the Albums page's Cover Flow slot (NAV_CF_X), the same scoped search the card's row used to open
        nb.children.append(hidden(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_search'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_search_down'), ('style:normal:icon', 'pod_nav_search'), ('style:over:icon', 'pod_nav_search')])))
    if search:   # the Subsonic root's Search (patch/ndroot.c shows it with a server saved and a source that searches; the "..." is then its middle piece, pod_nav_moremid): the capsule's left cap on the Albums page's Cover Flow slot (NAV_CF_X), as the Songs page's
        nb.children.append(hidden(Widget('button', NAV_CF_X, 0, NAV_CF_W, NAVBAR_H, [
            ('name', 'btn_search'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'pod_nav_search_down'), ('style:normal:icon', 'pod_nav_search'), ('style:over:icon', 'pod_nav_search')])))
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


VALUE_W, VALUE_PX = 110, 19                      # a value row's grey value (Settings > Appearance > Background): right aligned, 12 px margin


def value_x(w): return w - SWITCH_MARGIN - VALUE_W


def value_label(name, w, h, english):
    """The value at the right of a value row, #AAAAAA like the library rows' second line. Insensitive: the row takes the tap.
    The payload sets it with widget_set_tr_text, so it follows the language."""
    lab = Widget('label', value_x(w), 0, VALUE_W, h, [('name', name), pod_i18n.text_prop(english), ('sensitive', 'false')])
    styled(lab, ('normal',), 'text_color', SUB_RGB)
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


def scroll_text(name, x, y, w, h, px, colour, align, text=None):
    """An insensitive hscroll_label with its own size, colour and alignment (no style name), vertically middle; `text` is the English text of a translated label, empty when the payload sets it."""
    lab = Widget('hscroll_label', x, y, w, h, [('name', name), pod_i18n.text_prop(text) if text else ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_color', colour)
        styled(lab, (st,), 'text_align_h', align)
        styled(lab, (st,), 'text_align_v', 'middle')
    return lab


def hidden(w):
    """Start hidden *and* insensitive. This demo's AWTK hit test (widget_find_target_default
    0x6747d4) checks only enable and sensitive, never visible, so a merely hidden widget still
    swallows every touch over its rectangle; patch/coverflow.c keeps the two in step at runtime."""
    w.set('visible', 'false')
    w.set('sensitive', 'false')
    return w


STYLE_BG_STATES = ('normal', 'pressed', 'disable', 'focused')


def style_labels(table, bg=None):
    """Hidden labels that only carry text styles (widget_prepare_text_style; never shown): one per (name, px, colour[, align]) row, align 'left' by default, vertically middle;
    bg = {name: colour} gives a label its own background (the contrast scan reads it, for a dark text on a light pill)."""
    out = []
    for name, px, colour, align in (r if len(r) == 4 else (*r, 'left') for r in table):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if bg and name in bg: styled(lab, STYLE_BG_STATES, 'bg_color', bg[name])
        out.append(lab)
    return out


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
    root.children.append(scroll_caption('label_album', ay, ah, 22, INK_RGB))
    root.children.append(scroll_caption('label_artist', ry, rh, 18, SUB_RGB))
    status = label('label_status', 10, 210, SCREEN_W - 20, 30, '', 20, HINT_RGB)
    root.children.append(hidden(status))
    cancel = Widget('button', 100, 260, 120, 46, [('name', 'btn_cancel'), ('enable', 'true'),
                                                  pod_i18n.text_prop('Cancel')])
    for st in ('normal', 'over', 'focused', 'disable', 'selected'):
        styled(cancel, (st,), 'bg_color', SURFACE_RGB)
        styled(cancel, (st,), 'text_color', INK_RGB)
        styled(cancel, (st,), 'font_size', '20')
        styled(cancel, (st,), 'border_color', '#3A3A3A')
        styled(cancel, (st,), 'border_width', '1')
    styled(cancel, ('pressed',), 'bg_color', '#2A2A2A')
    styled(cancel, ('pressed',), 'text_color', INK_RGB)
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
LIST_TITLE_PX, LIST_SUB_PX = 20, 18   # the list mode's album / artist text (the library rows': 20 px white, 18 px #AAAAAA)


def large_title(name, text, states=('normal',)):
    """The large title of a page with a grid or list content (the Songs and Artists pages' label): 32 px white at x 12, SG_TITLE_W wide, SG_TITLE_H high (= PP_TITLE_H, the Podcasts levels' heading),
    insensitive; it is the first child of the content view and scrolls away with it (patch/albums.c, patch/playlists.c). The Navidrome pages style every state in `states`."""
    o = OFFSETS
    title = Widget('label', o['SG_TITLE_X'], 0, o['SG_TITLE_W'], o['SG_TITLE_H'], [('name', name), pod_i18n.text_prop(text), ('sensitive', 'false')])
    for st in states:
        styled(title, (st,), 'text_color', INK_RGB)
        styled(title, (st,), 'font_size', str(SG_TITLE_PX))
        styled(title, (st,), 'text_align_h', 'left')
        styled(title, (st,), 'text_align_v', 'middle')
    return title


def build_grid_page(page, toggle='list', coverflow=True, names=('albums_listview', 'albums_scrollview'), more=False, albums=False, more_left=False, plactions=False, title_name=None, az=False):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, toggle=toggle, coverflow=coverflow, more=more, albums=albums, more_left=more_left, plactions=plactions)
    if albums or title_name: nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    root.children.append(nb)
    lv = stock_list([], True)   # the library lists' structure: list_view > scroll_view 310 wide + scroll_bar_m. The mobile bar is not decoration: the list_view layouter makes the scroll_view yslidable only for it (0x60b1c8), scroll_view_create leaves it 0
    lv.set('name', names[0])
    sv = lv.children[0]
    sv.set('name', names[1])
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])   # the content: the payload sizes it to the whole library
    styled(grid, ('normal',), 'bg_color', '#000000')
    styled(grid, ('normal',), 'text_color', INK_RGB)
    styled(grid, ('normal',), 'font_size', str(GRID_TITLE_PX))
    styled(grid, ('normal',), 'text_align_h', 'left')
    styled(grid, ('normal',), 'text_align_v', 'middle')
    if albums or title_name:   # the large title, the first thing in the content: it scrolls away and the navbar's small title takes over
        grid.children = [large_title(title_name or 'al_title', page.title)]
    if albums:   # an artist's page shows the pills under the title (patch/albums.c); the library's keeps them hidden
        o = OFFSETS
        grid.children += [hidden(sg_pill('btn_play', o['AL_PLAY_X'], o['SG_PILL_Y'], 'Play', 'sg_play', w=o['AL_PLAY_W'], down=SG_PILL_PRESS_RGB)),
                          hidden(sg_pill('btn_shuffle', o['AL_SHUFFLE_X'], o['SG_PILL_Y'], 'Shuffle', 'sg_shuffle', w=o['AL_SHUFFLE_W'], down=SG_PILL_PRESS_RGB)),
                          # the photo header's name (22 px white, centred, the album page's title label; docs/modules/albums.md "Scoped to an artist"): shown in place of al_title, the circle is drawn by the payload
                          hidden(label('al_name', o['PH_NAME_X'], o['AL_NAME_Y'], o['PH_NAME_W'], o['PH_NAME_H'], '', 22, INK_RGB))]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/albums.c / playlists.c show it while yoffset > 0
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    if albums or title_name:   # a source's list still loading: the one spinner, centred in the room under the navbar here and under the large title by the payload (patch/libsrc.c ls_spin)
        root.children.append(hidden(wf_image((title_name or 'al_title')[:2] + '_spin', (SCREEN_W - WF_SPIN_PX) // 2, room_y(WF_SPIN_PX), WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')))
    # The two modes' text styles (patch/albums.c reads them with widget_prepare_text_style; never shown)
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB),
                                   ('label_grid_title', GRID_ALBUM_PX, INK_RGB), ('label_grid_sub', GRID_ARTIST_PX, SUB_RGB)))
    if az:   # the list mode's section letters, rail and bubble (patch/albums.c, the Songs page's furniture); the payload hides the rail while the grid shows or the Index Rail switch is off
        root.children.extend(azlist_labels())
        root.children.extend(azlist_rail())
    if albums:
        root.children.extend(view_sort_card())   # above the list, the rail and the navbar
        root.children.extend(row_menu(album=True))   # last: the long press sheet of an album (Play, Shuffle, Play Next, Play After, Pin Album / Unpin Album; patch/albums.c, docs/modules/pins.md)
    return root


# The Show page's text styles (patch/podcasts.c; hidden labels the payload reads with widget_prepare_text_style and measures with widget_measure_text): name, px, colour, alignment.
# Colours as the approved design: the description #B8B8B8, the grey lines, a played title and the empty pages' hint #AAAAAA; the Latest Episode pill's label is dark on its white pill.
PS_STYLES = (('label_ps_name', 22, INK_RGB, 'center'), ('label_ps_sec', 16, '#B8B8B8', 'left'), ('label_ps_meta', 15, SUB_RGB, 'left'), ('label_ps_head', 22, INK_RGB, 'left'),
             ('label_ps_date', 15, SUB_RGB, 'left'), ('label_ps_ctitle', 20, INK_RGB, 'left'), ('label_ps_cdim', 20, SUB_RGB, 'left'), ('label_ps_cdesc', 16, SUB_RGB, 'left'),
             ('label_ps_pill', 16, INK_RGB, 'left'), ('label_ps_latest', 18, '#000000', 'left'), ('label_ps_latestw', 18, INK_RGB, 'left'),
             # the Shows page (round 2): the section headers (Continue Listening, Shows), a Continue Listening item's title and its grey "35m left", the grid's title and grey line under each cover (the Albums grid's 18 / 15 px)
             ('label_ps_sech', SECTION_PX, INK_RGB, 'left'), ('label_ps_stitle', 14, INK_RGB, 'left'), ('label_ps_sleft', 13, SUB_RGB, 'left'),
             ('label_ps_gtitle', 18, INK_RGB, 'left'), ('label_ps_gsub', 15, SUB_RGB, 'left'))
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


def discover_find():
    """The Discover level's magnifier, hidden (patch/podcasts.c pg_nav and patch/bkpage.c bk_nav show it there only, as the left cap on the 214 slot beside Now Playing): the Radio page's Search button."""
    find = hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [
        ('name', 'btn_search'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', 'pod_nav_search_down'), ('style:normal:icon', 'pod_nav_search'), ('style:over:icon', 'pod_nav_search')]))
    find.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))
    return find


def build_podcasts_page(page):
    """The Podcasts page (patch/podcasts.c, docs/modules/podcasts.md): the Albums list mode's structure (a stock list holding the one content view the payload paints) under the
    plain navbar (Back, title, Now Playing). The payload paints the levels in view_grid; label_status is its empty-state hint (two lines); the hidden labels are the text styles.
    The Show level is tinted from the cover as the album page is (docs/modules/album-page.md "Artwork and shared tint"): the window's colour is set by the payload and img_ah_tint, the gradient
    over it, is shown; so the list, its scroll view and the content view are transparent (on every level: over the black window they look as before)."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(hidden(Widget('image', 0, 0, SCREEN_W, CLIENT_H, [('name', PS_TINT_NAME), ('image', 'ah_tint'), ('draw_type', 'default'), ('clickable', 'false')])))   # first: under everything
    nb = navbar(page.title, show_more=True, show_globe=True)   # btn_globe: the Shows level's Apple Podcasts search (the left cap; patch/podcasts.c pg_nav places it)
    srch = [c for c in nb.children if c.name == 'btn_globe'][0]
    nb.children.insert(nb.children.index(srch) + 1, discover_find())
    root.children.append(nb)
    root.children[1].children.append(selall_button())   # the select mode's navbar text (the Playlists page's)
    lv = stock_list([], True)
    lv.set('name', 'podcasts_listview')
    sv = lv.children[0]
    sv.set('name', 'podcasts_scrollview')
    for w in (lv, sv):
        for st in ('normal', 'disable', 'focused'): w.set(f'style:{st}:bg_color', '#00000000')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])   # the content: the payload sizes it to the level's rows
    big = large_title('pg_big', page.title)   # the large heading of the Shows, Downloads and Subscriptions levels (the Songs page's): a child of the content, so it scrolls and is clipped with it
    grid.children = [big, search_field()]
    styled(grid, ('normal',), 'bg_color', '#00000000')
    styled(grid, ('normal',), 'text_color', INK_RGB)
    styled(grid, ('normal',), 'font_size', str(GRID_TITLE_PX))
    styled(grid, ('normal',), 'text_align_h', 'left')
    styled(grid, ('normal',), 'text_align_v', 'middle')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/podcasts.c shows it while yoffset > 0 (not on the Show level, which paints a fade in the page's colour)
    status = hidden(label('label_status', 20, room_y(90), SCREEN_W - 40, 90, '', 18, HINT_RGB))
    styled(status, ('normal',), 'text_align_v', 'middle')
    root.children.append(status)
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB)))
    root.children += style_labels(PS_STYLES, {'label_ps_latest': INK_RGB})   # the dark label of the white pill: the contrast scan reads the label's own background
    bar = select_bar('pg_bar', [('pg_del', 'one'), ('pg_unsubp', 'one')])   # the select mode's bar: one Delete pill across it, as the Playlists page's; the Subscriptions page's Unsubscribe is a second pill in the same place (the payload shows one of them)
    hidden(bar.children[-1])
    root.children.append(bar)
    root.children.extend(podcasts_sheet())   # the two bottom sheets' one widget set: above the list, the bar and the navbar
    root.children.extend(podcasts_dialog())   # last: above everything
    return root


# The Audiobooks page's text styles (patch/bkpage.c; hidden labels the payload reads with widget_prepare_text_style and measures with widget_measure_text): name, px, colour, alignment.
# The header's title (22 px white, centred, as the Show page's name), its grey line (15 px, centred), the capsule's word (18 px black on the white capsule),
# and the title of a played part (the row title's size in the played grey of the Show page).
BK_STYLES = (('label_bk_title', 22, '#FFFFFF', 'center'), ('label_bk_sub', 15, '#AAAAAA', 'center'), ('label_bk_btn', 18, '#000000', 'center'),
             ('label_bk_dim', LIST_TITLE_PX, SUB_RGB, 'left'),
             # the LibriVox level (patch/bkfind.c): the grey section line (the Podcasts levels' meta line, 15 px) and the status line (their 20 px grey hint)
             ('label_bk_meta', 15, SUB_RGB, 'left'), ('label_bk_hint', 20, SUB_RGB, 'left'),
             # the Library's Continue Listening shelf (the Podcasts Shows level's text styles, the same labels) and the See All row's title
             *(r if len(r) == 4 else (*r, 'left') for r in PS_STYLES if r[0] in ('label_ps_sech', 'label_ps_stitle', 'label_ps_sleft', 'label_ps_ctitle')))
# The Book level's "..." sheet (patch/bkpage.c): the Podcasts sheets' widget set (sheet_widgets), four fixed rows: Playback Speed (every book; a grey value, a tap cycles), then for a LibriVox book Pause Download or Resume Download by the download's state and Delete Book (red as Unsubscribe is)
BK_SHEET = 'bk_sh'
BK_SHEET_ROWS = (('speed', 'pc_ic_speed', 'Playback Speed', True, False), ('pause', 'pod_ic_pause', 'Pause Download', False, False), ('resume', 'pod_ic_play', 'Resume Download', False, False), ('delete', 'pod_ic_trash_red', 'Delete Book', False, True))


def build_books_page(page):
    """The Audiobooks page (patch/bkpage.c, docs/modules/audiobooks.md): the Podcasts page's structure (a stock list holding the one content view the payload paints) under the plain navbar
    (Back, title, Now Playing). The payload paints the four levels in view_grid; bk_big is the large heading of the Library and LibriVox levels, ps_field the LibriVox level's search field; label_status is the empty-state hint; the hidden labels are the text styles."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, show_more=True)   # btn_more: the Book level's "..." while the book has a LibriVox manifest (the payload shows it and makes Now Playing the capsule's right cap)
    nb.children.append(discover_find())   # btn_search: the LibriVox level's magnifier, the Podcasts Discover level's (bk_nav shows it there only)
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'books_listview')
    sv = lv.children[0]
    sv.set('name', 'books_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])   # the content: the payload sizes it to the level's rows
    big = Widget('label', OFFSETS['SG_TITLE_X'], 0, OFFSETS['SG_TITLE_W'], OFFSETS['PP_TITLE_H'], [('name', 'bk_big'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])   # the Library's large heading (the Podcasts pages'): a child of the content, so it scrolls and is clipped with it
    styled(big, ('normal',), 'text_color', '#FFFFFF')
    styled(big, ('normal',), 'font_size', str(OFFSETS['PP_TITLE_PX']))
    styled(big, ('normal',), 'text_align_h', 'left')
    styled(big, ('normal',), 'text_align_v', 'middle')
    grid.children = [big, search_field()]   # the LibriVox level's search field (the Podcasts search level's widgets; the payload moves and shows it there only)
    styled(grid, ('normal',), 'bg_color', '#000000')
    styled(grid, ('normal',), 'text_color', '#FFFFFF')
    styled(grid, ('normal',), 'font_size', str(GRID_TITLE_PX))
    styled(grid, ('normal',), 'text_align_h', 'left')
    styled(grid, ('normal',), 'text_align_v', 'middle')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/bkpage.c shows it while yoffset > 0
    status = hidden(label('label_status', 20, 180, SCREEN_W - 40, 90, '', 18, HINT_RGB))
    styled(status, ('normal',), 'text_align_v', 'middle')
    root.children.append(status)
    for name, px, colour in (('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB)):
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, 'left'))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        root.children.append(lab)
    for name, px, colour, align in BK_STYLES:
        lab = hidden(label(name, 0, 0, 10, 10, '', px, colour, align))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        if name == 'label_bk_btn': styled(lab, ('normal', 'pressed', 'disable', 'focused'), 'bg_color', '#FFFFFF')   # the dark word of the white capsule: the contrast scan reads the label's own background
        root.children.append(lab)
    root.children.extend(sheet_widgets(BK_SHEET, BK_SHEET_ROWS, 3))   # the sheet, last: above the list and the navbar
    return root

# The Show page's bottom sheets (the show's "..." and an episode's), in the style of Now Playing's More sheet (docs/modules/playmore.md): the page dimmed (the Playlists menu's scrim), the
# 320 px glass from the bottom of the window (pc_sheet6 .. pc_sheet1, a picture for each number of rows: tools/mod_icons.py PC_SHEETS; the payload sets the image
# and the card's height and place for the rows it shows), PM_ROW_H rows, each a button (transparent, 6 % white pressed) with its 24 px glyph at x PS_SHEET_ICON_X (the geometry of the track rows' menu, row_menu: 14 and 48), the label from
# PS_SHEET_TEXT_X and, for the two rows that have one, the grey value right aligned to PS_SHEET_VALUE_R; a 1 px hairline child on the top of every row but the first (the payload shows it).
# One widget set serves both sheets: the fifteen rows are fixed (glyph and label each), the payload shows and places the ones the sheet needs. Everything starts hidden and insensitive.
PS_SHEET_ROWS = (('speed', 'pc_ic_speed', 'Playback Speed', True, False), ('refresh', 'pc_ic_refresh', 'Refresh Feed', True, False), ('select', 'pc_ic_select', 'Select Episodes', False, False),
                 ('markall', 'pc_ic_check', 'Mark All as Played', False, False), ('unsub', 'pc_ic_unsub', 'Unsubscribe', False, True),
                 ('dl', 'pc_ic_down', 'Download', False, False), ('rm', 'pc_ic_trash', 'Remove Download', False, False),
                 ('mark', 'pc_ic_check', 'Mark as Played', False, False), ('unmark', 'pc_ic_undo', 'Mark as Unplayed', False, False),
                 ('import', 'pc_ic_import', 'Import from Card', False, False), ('delplayed', 'pod_ic_trash_red', 'Delete Played Episodes', False, True),
                 ('export', 'pod_ic_export', 'Export OPML', False, False), ('save', 'pod_ic_save', 'Save Episode', False, False), ('order', 'pod_ic_order', 'Episode Order', True, False), ('filter', 'pod_ic_filter', 'Filter', True, False),
                 ('dlpause', 'pod_ic_pause', 'Pause', False, False), ('dlresume', 'pod_ic_play', 'Resume', False, False), ('dlretry', 'pc_ic_undo', 'Retry', False, False), ('dlcancel', 'pod_ic_cancel', 'Cancel Download', False, False))   # an In Progress row's sheet: the first of dlpause / dlresume / dlretry by the download's state, then dlcancel; id, glyph, label, has a value, red; import is the Shows level's sheet, select (relabelled Select, or Select Shows) and delplayed the Downloads page's, select and export the Subscriptions page's, save (relabelled Unsave Episode when it is saved) an episode's
PS_SHEET_ICON_X, PS_SHEET_TEXT_X, PS_SHEET_VALUE_R, PS_SHEET_VALUE_W, PS_SHEET_GAP = (OFFSETS[k] for k in ('PS_SHEET_ICON_X', 'PS_SHEET_TEXT_X', 'PS_SHEET_VALUE_R', 'PS_SHEET_VALUE_W', 'PS_SHEET_GAP'))   # patch/offsets.inc
PS_SHEET_RED = RED_RGB
PS_SHEET_PX = 18   # the labels (Now Playing's More sheet: 18 px)


def podcasts_sheet():
    """(scrim, card) of the Show page's sheets: the card at its tallest (seven rows, pc_sheet7), at the bottom of the window."""
    return sheet_widgets('pg_sh', PS_SHEET_ROWS, 7)


def sheet_widgets(prefix, sheet_rows, tallest):
    """(scrim, card) of a bottom sheet with the fixed rows `sheet_rows` (id, glyph, label, has a value, red), named <prefix>_scrim, <prefix>_card, <prefix>_<id> (+ _ic, _tx, _vl, _hr); the card's
    height the tallest of its pictures (pc_sheet<tallest>)."""
    from mod_icons import PC_SHEET_PX
    o = OFFSETS
    rh, rows = o['PM_ROW_H'], len(sheet_rows)
    scrim = modal_scrim(f'{prefix}_scrim')
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
            styled(item, (st,), 'text_color', INK_RGB)
            styled(item, (st,), 'border_width', '0')
            styled(item, (st,), 'border_color', '#00000000')
        item.children.append(Widget('image', PS_SHEET_ICON_X, (rh - PC_SHEET_PX) // 2, PC_SHEET_PX, PC_SHEET_PX, [
            ('name', f'{prefix}_{rid}_ic'), ('draw_type', 'default'), ('image', icon), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', PS_SHEET_TEXT_X, 0, PS_SHEET_VALUE_R - PS_SHEET_TEXT_X, rh, [
            ('name', f'{prefix}_{rid}_tx'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PS_SHEET_PX))
            styled(lab, (st,), 'text_color', PS_SHEET_RED if red else INK_RGB)
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
                styled(val, (st,), 'text_color', SUB_RGB)
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


PQ_FIRST, PQ_ROWS = OFFSETS['PQ_FIRST'], OFFSETS['PQ_ROWS']
assert PQ_ROWS == pod_pages.PEQ_ROWS and PQ_FIRST == 2


PEQP_ROWS = OFFSETS['GR_BANDS']
assert PEQP_ROWS == pod_pages.PEQP_ROWS == 64


PQD_W, PQD_HEAD, PQD_ROW_H = OFFSETS['PD_CARD_W'], 76, OFFSETS['PL_ROW_H']   # the unsaved-changes dialog (patch/peqband.c): the card's width (the Podcasts dialog's PD_CARD_W), the head above the buttons, a button row (PL_ROW_H)
PQD_KEYS = ('Save', 'Save As New…', "Don't Save", 'Cancel')   # its buttons, top to bottom (pq_item<k>)
PQD_H = PQD_HEAD + len(PQD_KEYS) * PQD_ROW_H


def peq_dialog():
    """(scrim, card): the band page's unsaved-changes dialog (patch/peqband.c, docs/modules/peq.md "Preset editing"), the Podcasts refresh dialog's pieces (podcasts_dialog): a full-client dim scrim that takes every touch (a tap on it is Cancel) and a
    centred card in the Playlists menu's glass (pq_glass, patch3_x) with the title "Save Changes?" (pq_title, 20 px white), the preset's name (pq_name, 16 px grey, the payload sets it) and PQD_ROW_H button rows (pq_item<k>: PQD_KEYS, 18 px white
    centred, the menu rows' 13 % white hairline above each and 6 % white pressed). Hidden AND insensitive until the payload shows them."""
    scrim = modal_scrim('pq_scrim')
    card = hidden(Widget('view', (SCREEN_W - PQD_W) // 2, (CLIENT_H - PQD_H) // 2, PQD_W, PQD_H, [('name', 'pq_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', 'pq_glass')
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    def text(name, y, h, px, rgb, prop):
        lab = Widget('hscroll_label', 12, y, PQD_W - 24, h, [('name', name), prop, ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', rgb)
            styled(lab, (st,), 'text_align_h', 'center')
            styled(lab, (st,), 'text_align_v', 'middle')
        return lab
    card.children.append(text('pq_title', 14, 30, 20, INK_RGB, pod_i18n.text_prop('Save Changes?')))
    card.children.append(text('pq_name', 44, 24, 16, PD_NAME_RGB, ('text', '')))
    for k, key in enumerate(PQD_KEYS):
        b = Widget('button', 0, PQD_HEAD + k * PQD_ROW_H, PQD_W, PQD_ROW_H, [('name', f'pq_item{k}'), ('enable', 'true'), pod_i18n.text_prop(key)])
        for st in STATES:
            styled(b, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(b, (st,), 'text_color', INK_RGB)
            styled(b, (st,), 'font_size', '18')
            styled(b, (st,), 'border', 'top')
            styled(b, (st,), 'border_width', '1')
            styled(b, (st,), 'border_color', PL_HAIR)
        card.children.append(b)
    return scrim, card


BK_H, BK_GLASS = 320, 'bk_glass'                              # the number keypad sheet (patch/peqband.c): its height, the sheet's glass (tools/mod_icons.py GLASS_BANDKEYPAD)
BK_GRAB_W, BK_GRAB_H, BK_GRAB_Y = 36, 5, 8
BK_TOP_Y, BK_TOP_H, BK_TOP_PX, BK_TOP_W = 14, 36, 17, 100       # Cancel / title / Done row
BK_RANGE_Y, BK_RANGE_H, BK_RANGE_PX = 54, 22, 14
BK_FIELD_X, BK_FIELD_Y, BK_FIELD_W, BK_FIELD_H, BK_VAL_H, BK_CARET_W, BK_CARET_H = (OFFSETS[k] for k in ('BK_FIELD_X', 'BK_FIELD_Y', 'BK_FIELD_W', 'BK_FIELD_H', 'BK_VAL_H', 'BK_CARET_W', 'BK_CARET_H'))   # patch/offsets.inc
BK_FIELD_R, BK_VAL_PX, BK_UNIT_PX = 12, 38, 17
BK_KEY_X0, BK_KEY_PITCH_X, BK_KEY_W = 6, 78, 74                  # four columns of 74 px, 4 px apart
BK_KEY_Y0, BK_KEY_PITCH_Y, BK_KEY_H, BK_KEY_PX = 136, 46, 40, 22
BK_KEY_R = 9
BK_FIELD_RGB, BK_GRAB_RGB, BK_DIM_RGB = RAISED_RGB, '#6E6E73', '#5A5A5E'


def band_keypad():
    """(scrim, card): the band page's number keypad (patch/peqband.c, docs/modules/peq.md "Preset editing", mockup 10c): the dim scrim (a tap on it is Cancel) and a bottom sheet in the track rows' menu's glass
    (bk_glass, BK_H high, top corners rounded) with a grabber, Cancel / the field's title / Done, a grey "Range ..." line, the value field (bk_val right aligned, bk_caret, bk_unit; the payload places the three by the unit's width) and
    the keys: 1-9, a wide 0, "." and, in the right column, backspace, the sign (Gain only) and the Hz / kHz key (Frequency only; the payload sets the texts of those two keys). Neutral greys, no accent. Hidden AND insensitive until the payload shows them."""
    scrim = modal_scrim('bk_scrim')
    card = hidden(Widget('view', 0, CLIENT_H - BK_H, SCREEN_W, BK_H, [('name', 'bk_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', BK_GLASS)
        styled(card, (st,), 'bg_image_draw_type', 'default')
        styled(card, (st,), 'border_width', '0')

    def plain(name, x, y, w, h, fill, radius=0):
        v = Widget('view', x, y, w, h, [('name', name), ('sensitive', 'false')])
        for st in STATES:
            styled(v, (st,), 'bg_color', fill)
            styled(v, (st,), 'border_width', '0')
            if radius: styled(v, (st,), 'round_radius', str(radius))
        return v

    def text(name, x, y, w, h, px, rgb, align, prop):
        lab = Widget('hscroll_label', x, y, w, h, [('name', name), prop, ('only_parent_focus', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', rgb)
            styled(lab, (st,), 'text_align_h', align)
            styled(lab, (st,), 'text_align_v', 'middle')
            styled(lab, (st,), 'margin_left', '0')
            styled(lab, (st,), 'margin_right', '0')
        return lab

    def key(name, x, y, w, prop, fill, down, px=BK_KEY_PX):
        b = Widget('button', x, y, w, BK_KEY_H, [('name', name), ('enable', 'true'), prop])
        for st in STATES:
            styled(b, (st,), 'bg_color', down if st == 'pressed' else fill)
            styled(b, (st,), 'text_color', BK_DIM_RGB if st == 'disable' else INK_RGB)
            styled(b, (st,), 'font_size', str(px))
            styled(b, (st,), 'border_width', '0')
            styled(b, (st,), 'round_radius', str(BK_KEY_R))
        return b

    card.children.append(plain('bk_grab', (SCREEN_W - BK_GRAB_W) // 2, BK_GRAB_Y, BK_GRAB_W, BK_GRAB_H, BK_GRAB_RGB, BK_GRAB_H // 2))
    for name, x, align, key_text in (('bk_cancel', 0, 'left', 'Cancel'), ('bk_done', SCREEN_W - BK_TOP_W, 'right', 'Done')):
        b = Widget('button', x, BK_TOP_Y, BK_TOP_W, BK_TOP_H, [('name', name), ('enable', 'true')])
        for st in STATES:
            styled(b, (st,), 'bg_color', '#00000000')
            styled(b, (st,), 'text_color', INK_RGB)
            styled(b, (st,), 'border_width', '0')
        b.children.append(text(f'{name}_t', 16 if align == 'left' else 0, 0, BK_TOP_W - 16, BK_TOP_H, BK_TOP_PX, INK_RGB, align, pod_i18n.text_prop(key_text)))
        card.children.append(b)
    card.children.append(text('bk_title', BK_TOP_W, BK_TOP_Y, SCREEN_W - 2 * BK_TOP_W, BK_TOP_H, BK_TOP_PX, INK_RGB, 'center', ('text', '')))
    card.children.append(text('bk_range', 16, BK_RANGE_Y, SCREEN_W - 32, BK_RANGE_H, BK_RANGE_PX, PD_COUNT_RGB, 'left', ('text', '')))
    card.children.append(plain('bk_field', BK_FIELD_X, BK_FIELD_Y, BK_FIELD_W, BK_FIELD_H, BK_FIELD_RGB, BK_FIELD_R))
    card.children.append(text('bk_val', BK_FIELD_X + 10, BK_FIELD_Y + (BK_FIELD_H - BK_VAL_H) // 2, 200, BK_VAL_H, BK_VAL_PX, INK_RGB, 'right', ('text', '')))
    card.children.append(plain('bk_caret', BK_FIELD_X + 220, BK_FIELD_Y + (BK_FIELD_H - BK_CARET_H) // 2, BK_CARET_W, BK_CARET_H, INK_RGB))
    card.children.append(text('bk_unit', BK_FIELD_X + 226, BK_FIELD_Y, 40, BK_FIELD_H, BK_UNIT_PX, PLACEHOLDER_RGB, 'left', ('text', '')))
    kx = lambda c: BK_KEY_X0 + c * BK_KEY_PITCH_X
    ky = lambda r: BK_KEY_Y0 + r * BK_KEY_PITCH_Y
    for d in range(1, 10):
        r, c = divmod(d - 1, 3)
        card.children.append(key(f'bk_k{d}', kx(c), ky(r), BK_KEY_W, ('text', str(d)), PK.KB_KEY, PK.KB_KEY_DOWN))
    card.children.append(key('bk_k0', kx(0), ky(3), 2 * BK_KEY_PITCH_X - 4 + 0, ('text', '0'), PK.KB_KEY, PK.KB_KEY_DOWN))
    card.children.append(key('bk_dot', kx(2), ky(3), BK_KEY_W, ('text', '.'), PK.KB_KEY, PK.KB_KEY_DOWN))
    delete = key('bk_del', kx(3), ky(0), BK_KEY_W, ('text', ''), PK.KB_FN, PK.KB_FN_DOWN)
    for st in STATES: styled(delete, (st,), 'icon', 'qk_delete')
    card.children.append(delete)
    card.children.append(key('bk_sign', kx(3), ky(1), BK_KEY_W, ('text', ''), PK.KB_FN, PK.KB_FN_DOWN))
    card.children.append(key('bk_unitk', kx(3), ky(2), BK_KEY_W, ('text', ''), PK.KB_FN, PK.KB_FN_DOWN, px=BK_UNIT_PX))
    return scrim, card


def build_peqpage_page(page):
    """The preset page (patch/peqpage.c, docs/modules/peq.md "Preset page", "Preset editing"): a cards page (build_cards_page, page.layout). pod_graph is the graph card, pod_row0 the preamp row (pod_value0), pod_row1 .. the band
    rows (pod_label<i> the frequency, pod_value<i> the gain, pod_sub<i> the grey line, a chevron: a tap opens the band page); the band rows and the note (pod_note0) start hidden and insensitive.
    The Delete Preset row (pod_row<PEQP_ROWS + 1>) and Rename Preset above it (pod_row<PEQP_ROWS + 2>) are always shown: one card with a touch each (patch/peqpage.c)."""
    root = build_cards_page(page)
    sv = next(w for w in root.walk() if w.name == 'pod_scrollview')
    for c in sv.children:
        if c.name == 'pod_note0' or (c.name.startswith('pod_row') and 1 <= int(c.name[7:]) <= PEQP_ROWS): hidden(c)
    return root


def build_peqband_page(page):
    """The band page (patch/peqband.c, docs/modules/peq.md "Preset editing"): a cards page (build_cards_page, page.layout) whose navbar is the glass capsule [Previous band | Next band | Now Playing] (btn_bprev, btn_bnext); the title is the payload's ("Band 4"). The unsaved-changes dialog (peq_dialog) is last, above the list and the navbar."""
    root = build_cards_page(page)
    nb = root.children[0]
    nb.children[0].w = NAV_CF_X - NAV_TITLE_X
    for c in nb.children:
        if c.name == 'btn_backtoplayer':   # the capsule's right cap
            for st, img in (('pressed', 'ah_nav_play_down'), ('normal', 'ah_nav_play'), ('over', 'ah_nav_play')): c.set(f'style:{st}:icon', img)
    for name, icon, x in (('btn_bprev', 'pod_nav_bprev', NAV_CF_X), ('btn_bnext', 'pod_nav_bnext', NAV_VIEW_X)):
        b = Widget('button', x, 0, NAV_VIEW_W, NAVBAR_H, [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                                                           ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)])
        b.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))
        nb.children.append(b)
    root.children.extend(band_keypad())   # the number keypad sheet, then the dialog: above the list and the navbar
    root.children.extend(peq_dialog())
    return root


def build_peq_page(page):
    """Settings > Playback > EQ (patch/peq_ui.c, docs/modules/peq.md): a cards page (build_cards_page, page.layout). pod_row0 is the Equalizer switch (pod_switch0) in a card
    of its own, pod_row1 10-Band EQ (its grey curve name pod_value1) and PQ_ROWS preset rows (pod_label<i>, no text in the asset) one card, a check pod_check<i> on each. The preset rows and the hint
    (pod_note1, a wrapping label) start hidden and insensitive; the payload shows as many rows as the card has presets, or the hint, and sets each row's card piece and hairline.
    pod_note0 under the switch card is the grey output line ("For Headphones", the payload sets the text, pod_note0_t), always shown.
    The bottom card (after the gap pod_gap0, which the payload hides while the hint shows) is always there: the 10-Band EQ link row (pod_row<PQ_FIRST + PQ_ROWS>, its curve name pod_value<that row>) and the Presets link row (the next one, its count pod_value<that row>)."""
    root = build_cards_page(page)
    sv = next(w for w in root.walk() if w.name == 'pod_scrollview')
    for c in sv.children:
        if c.name == 'pod_note1' or (c.name.startswith('pod_row') and PQ_FIRST <= int(c.name[7:]) < PQ_FIRST + PQ_ROWS): hidden(c)
    return root


def build_peqlib_page(page):
    """The Presets page (patch/peqlib.c, docs/modules/peq.md "Presets page"): a cards page (build_cards_page, page.layout). pod_row0 is the Download from AutoEq row; the two section
    headers (pod_sec0 AutoEq, pod_sec1 On Card) and the file rows (pod_row1 .. pod_row<2 * PQ_ROWS>: pod_label<i> the name, pod_sub<i> the grey line, a chevron) start hidden and insensitive,
    and the payload shows what the card has, with its pieces and hairlines."""
    root = build_cards_page(page)
    sv = next(w for w in root.walk() if w.name == 'pod_scrollview')
    for c in sv.children:
        if c.name in ('pod_sec0', 'pod_sec1') or (c.name.startswith('pod_row') and int(c.name[7:]) >= 1): hidden(c)
    return root


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
PD_TRACK_RGB, PD_FILL_RGB, PD_NAME_RGB, PD_COUNT_RGB, PD_CANCEL_RGB = '#FFFFFF33', '#EBEBEC', '#EBEBEB', SUB_RGB, INK_RGB   # the fill is palette.ROLE_FILL (#EBEBEB one blue level up): the accent maps it; the track stays neutral


def podcasts_dialog(prefix='pod_pd', title='Refreshing Podcasts', big=False):
    """(scrim, card) of the refresh dialog."""
    ty, th, tpx, ny, nh, npx, by, bh, cy, ch, cpx, row = (14, 30, 20, 48, 26, 18, 92, 6, 104, 28, 20, 48) if big else (PD_TITLE_Y, PD_TITLE_H, PD_TITLE_PX, PD_NAME_Y, PD_NAME_H, PD_NAME_PX, PD_BAR_Y, PD_BAR_H, PD_COUNT_Y, PD_COUNT_H, PD_COUNT_PX, PL_ROW_H)   # big: the Software Update popup, larger type, a 6 px bar, the stock dialog's 48 px button row
    assert PD_CARD_H == OFFSETS['PL_MENU_ROWS'] * PL_ROW_H
    scrim = modal_scrim(prefix + '_scrim')
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
    card.children.append(text(prefix + '_title', ty, th, tpx, INK_RGB, pod_i18n.text_prop(title)))
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
# "..." | Now Playing (the Songs and Artists capsule). Its "..." card is the shared view-sort card (view_sort_card below, patch/viewsort.c): the four page
# actions (New Playlist, Import, Export, Delete Playlists: slots 6..9), the View group (Grid, List) and Name. Everything starts hidden and insensitive.
STATES = ('normal', 'pressed', 'over', 'focused', 'disable', 'selected')
PL_CARD_RIGHT, PL_CARD_Y, PL_ROW_H, PL_CARD_R, PL_CARD_MAX = (OFFSETS[k] for k in (
    'PL_CARD_RIGHT', 'PL_CARD_Y', 'PL_ROW_H', 'PL_CARD_R', 'PL_CARD_MAX'))
PL_CARD_H = OFFSETS['PL_MENU_ROWS'] * PL_ROW_H   # the pl_glass card of the dialogs that borrow it (pcdialog)
PL_LABEL_PX = 18
PL_GLASS = 'pl_glass'
PL_DIM = '#00000082'          # the sheet's highlight="default(alpha=130)" (tools/mod_lists.py edit_playmore)


def modal_scrim(name):
    """The full-client dimming button behind a sheet or dialog (PL_DIM in every state): hidden and insensitive until the payload shows it, takes every touch while shown."""
    scrim = hidden(Widget('button', 0, 0, SCREEN_W, CLIENT_H, [('name', name), ('enable', 'true')]))
    for st in STATES:
        styled(scrim, (st,), 'bg_color', PL_DIM)
        styled(scrim, (st,), 'text_color', INK_RGB)
        styled(scrim, (st,), 'border_width', '0')
        styled(scrim, (st,), 'border_color', '#00000000')
    return scrim
PL_PRESSED, PL_HAIR = '#FFFFFD10', '#FFFFFF22'   # the sheet's rows (tools/mod_lists.py PM_PRESSED, PM_HAIR); pressed is palette.ROLE_SHEET_PRESS (6 % white, one blue level off): an accent makes it the accent at 22 % alpha


def build_playlists_page(page):
    from mod_icons import PL_MENU_ICONS
    root = build_grid_page(page, toggle=None, coverflow=False, more_left=True, plactions=True, names=('playlists_listview', 'playlists_scrollview'), title_name='pl_title')
    root.children[0].children.append(selall_button())   # the navbar's select mode text (the card's Delete Playlists starts select mode: patch/playlists.c)
    root.children.append(select_bar('pl_bar', [('pl_del', 'one')]))
    root.children.extend(view_sort_card(sort_keys=('Name',) * len(VS_SORT_KEYS), act_keys=pod_pages.PLAYLIST_MENU, act_glyphs=[n for n, _ in PL_MENU_ICONS]))   # above the list, the bar and the navbar
    root.children.extend(row_menu(pins=True))   # last: the long press sheet of a playlist (Play, Shuffle, Pin Playlist / Unpin Playlist; patch/playlists.c, docs/modules/pins.md)
    return root



RM_KEYS = ('Play Next', 'Play After', 'Add to Playlist', 'Favorite', 'Get Info', 'Pin Song', 'Remove from Playlist')   # the track rows' "..." menu (patch/rowmenu.c): the rows in order, each with its glyph (tools/mod_icons.py RM_MENU_ICONS, then RM_REMOVE)
RM_QUEUE_KEYS = ('Play Next', 'Play After', 'Remove from Queue')   # the Queue page's sheet: three rows (the same code path, patch/rowmenu.c rowmenu_bind_queue), the glass of three rows
RM_QUEUE_GLASS = 'pc_sheet3'
PIN_KEYS = ('Play', 'Shuffle', 'Unpin Album')   # the Artists page's long press sheet (patch/artists.c): three rows on the same sheet, the glyphs of tools/mod_icons.py RM_PIN_ICONS
ALBUM_SHEET_KEYS = ('Play', 'Shuffle', 'Unpin Album', 'Add to Playlist', 'Play Next', 'Play After')   # the album long press sheet (Albums, Home pins, Recently Played; patch/albums.c, patch/pins.c): six rows in three groups on pc_sheet6 (the payload words them: rowmenu_open_rows)
ALBUM_SHEET_GLASS = 'pc_sheet6'
RM_RED_KEYS = ('Remove from Playlist', 'Remove from Queue')   # a sheet's destructive rows: the label RED_RGB, the glyph the red pod_ic_remove_red (as the other sheets' Delete rows: PS_SHEET_RED, pod_ic_trash_red)
RM_GLASS = 'pc_sheet7'                                       # the sheet's glass: Now Playing's More sheet's pane, seven rows high (the payload makes it as high as the rows a row has, five to seven: patch/rowmenu.c rowmenu_set_rows), top corners only
RM_ICON_X, RM_TEXT_X, RM_TEXT_R = 14, 48, 22                  # Now Playing's More sheet's rows (pod_tape: the 24 px glyph at x 14, the label from x 48, ending at 298)
RM_LABEL_PX = 18


def row_menu(queue=False, pins=False, album=False):
    """(scrim, card): the track rows' "..." menu, shared by the album page and the Songs page (patch/rowmenu.c, docs/modules/rowmenu.md): a bottom sheet as Now Playing's More sheet
    (tools/mod_lists.py edit_playmore): the window's dim scrim, a full-width card at the window's foot in that sheet's glass, five PM_ROW_H rows filling it, each a transparent button
    (6 % white pressed) with a bare 24 px glyph and the 18 px white label, the sheet's 13 % white hairline above every row but the first. Rows: Play Next, Play After, Add to Playlist, Favorite (the payload swaps its label and star), Get Info, Pin Song (the payload swaps its label and glyph to Unpin Song, and hides it for a row that is not a song of the card), Remove from Playlist (shown on a stock playlist's songs page only, moved up when Pin Song is hidden; the glass as high as the rows shown).
    Hidden AND insensitive until the payload shows them; nothing is placed or sized at open. Put it last in the window, above the list, the bars and the navbar.
    queue: the Queue page's sheet, three rows (Play Next, Play After, Remove from Queue) on the three-row glass.
    pins: the Artists page's long press sheet, three rows: Play, Shuffle, Unpin Album (the payload sets Pin Artist / Unpin Artist).
    album: the album long press sheet (Home pins, Recently Played, Albums page), five rows: Play, Shuffle, Play Next, Play After, Unpin Album on pc_sheet5 (Home shrinks it to three rows for a pinned playlist or artist, and two for a pinned song)."""
    from mod_icons import RM_MENU_ICONS, RM_REMOVE, RM_PIN_ICONS, BARE_PX
    if album:
        keys, icons, glass, rows = ALBUM_SHEET_KEYS, RM_PIN_ICONS + (RM_MENU_ICONS[2],) + RM_MENU_ICONS[:2], ALBUM_SHEET_GLASS, OFFSETS['RM_ALBUM_ROWS']
    elif pins:
        keys, icons, glass, rows = PIN_KEYS, RM_PIN_ICONS, RM_QUEUE_GLASS, OFFSETS['RM_QUEUE_ROWS']
    elif queue:
        keys, icons, glass, rows = RM_QUEUE_KEYS, RM_MENU_ICONS[:2] + (RM_REMOVE,), RM_QUEUE_GLASS, OFFSETS['RM_QUEUE_ROWS']
    else:
        keys, icons, glass, rows = RM_KEYS, RM_MENU_ICONS + (RM_REMOVE,), RM_GLASS, OFFSETS['RM_ROWS']
    rh = OFFSETS['PM_ROW_H']
    assert len(keys) == rows == len(icons)
    scrim = modal_scrim('rm_scrim')
    card = hidden(Widget('view', 0, CLIENT_H - rows * rh, SCREEN_W, rows * rh, [('name', 'rm_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', glass)
        styled(card, (st,), 'bg_image_draw_type', 'default')
        styled(card, (st,), 'border_width', '0')
    for i, (text, (icon, _)) in enumerate(zip(keys, icons)):
        item = Widget('button', 0, i * rh, SCREEN_W, rh, [('name', f'rm_item{i}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', INK_RGB)
            styled(item, (st,), 'border', 'none')
            styled(item, (st,), 'border_width', '0')
        item.children.append(Widget('image', RM_ICON_X, (rh - BARE_PX) // 2, BARE_PX, BARE_PX, [
            ('name', f'rm_icon{i}'), ('draw_type', 'default'), ('image', icon), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', RM_TEXT_X, 0, SCREEN_W - RM_TEXT_X - RM_TEXT_R, rh, [
            ('name', f'rm_label{i}'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(RM_LABEL_PX))
            styled(lab, (st,), 'text_color', RED_RGB if text in RM_RED_KEYS else INK_RGB)
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        card.children.append(item)
    for k in range(OFFSETS['RM_HAIRS']):   # the hairlines between the groups, placed by the payload (patch/rowmenu.c rm_layout); none inside a group
        hair = hidden(Widget('view', 0, 0, SCREEN_W, 1, [('name', f'rm_hair{k}')]))
        for st in STATES: styled(hair, (st,), 'bg_color', PL_HAIR)
        card.children.append(hair)
    return scrim, card


def popup_menu():
    """(scrim, card): an item's actions as a floating card under a navbar "..." (patch/rowmenu.c rowmenu_bind_popup; the library album page's "..."): the view-sort card's look (its glass vs_glass<n>
    patch3_x, PL_CARD_RIGHT / PL_CARD_Y, 50 px rows, a 20 px glyph at the tick column's x and the 18 px label after it, as that card's action-only form) with the row menu's groups (rp_hair0..1, one
    hairline between two groups). RM_POPUP_ROWS rows; the payload words them, packs them, fits the width to the language and sizes the glass. Hidden AND insensitive until shown."""
    rows, rh = OFFSETS['RM_POPUP_ROWS'], VS_ROW_H
    gx, lx = VS_TICK_X, VS_TICK_X + VS_LABEL_X_GLYPH - VS_GLYPH_X
    scrim = modal_scrim('rp_scrim')
    card = hidden(Widget('view', PL_CARD_RIGHT - PL_CARD_MAX, PL_CARD_Y, PL_CARD_MAX, rows * rh, [('name', 'rp_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', f'vs_glass{rows}')
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    for i in range(rows):
        item = Widget('button', 0, i * rh, PL_CARD_MAX, rh, [('name', f'rp_item{i}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', INK_RGB)
            styled(item, (st,), 'border', 'none')
            styled(item, (st,), 'border_width', '0')
        item.children.append(Widget('image', gx, (rh - VS_GLYPH) // 2, VS_GLYPH, VS_GLYPH, [
            ('name', f'rp_icon{i}'), ('draw_type', 'default'), ('image', 'pod_ic_vsselect'), ('sensitive', 'false')]))
        lab = Widget('hscroll_label', lx, 0, PL_CARD_MAX - lx - 16, rh, [
            ('name', f'rp_label{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PL_LABEL_PX))
            styled(lab, (st,), 'text_color', INK_RGB)
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        card.children.append(item)
    for k in range(OFFSETS['RM_HAIRS']):
        hair = hidden(Widget('view', 0, 0, PL_CARD_MAX, 1, [('name', f'rp_hair{k}')]))
        for st in STATES: styled(hair, (st,), 'bg_color', PL_HAIR)
        card.children.append(hair)
    return scrim, card


# The Songs page (patch/songs.c, docs/modules/songs.md): the Albums structure (a stock list holding the one content view that paints the rows, headers and
# pinned header itself) under the glass navbar (Back, the small title, Search / Sort / Select / Now Playing), with the page's own widgets: in the content view the
# large title and the Play / Shuffle pills (real flat buttons: they scroll with the list; a playlist's header has hidden album-style image buttons, hd_shuffle / hd_play, instead); over the list the rail (a view of its own, outside the scroll_view, so a
# touch on it never starts a drag) and the letter bubble (insensitive); the sort card (a scrim and the Playlists card's glass) and, hidden until select mode, the
# bar with the Add to playlist and Delete pills and the navbar's Select All text. Everything that is shown later starts hidden AND insensitive.
SG_HDR_PX, SG_RAIL_PX, SG_PILL_PX = SECTION_PX, 12, 18
SG_BUBBLE_PX = OFFSETS['SG_BUBBLE_PX']
SG_TITLE_PX = OFFSETS['PP_TITLE_PX']   # the large title's size, the Podcasts heading's too (patch/offsets.inc PP_TITLE_PX)
SG_PILL_RGB, SG_PILL_DOWN_RGB, SG_PILL_OFF_RGB = SURFACE_RGB, LINE_RGB, '#141414'   # flat: no glass
SG_PILL_PRESS_RGB = '#333335'   # the Play / Shuffle pills pressed: palette.ROLE_PRESS_PILL, one blue level off #333333 so the accent can find it (the select bars' pills keep #333333)
SG_FOOT_RGB = SUB_RGB   # the song count under the last row: the album page's footer's grey


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
SG_SELALL_X = OFFSETS['SG_SELALL_X']     # the title's end in select mode (the pill's left edge at its widest label, patch/offsets.inc)


def flat_pill(b, fill, down, radius, disabled=None, ink=None, px=None, dim=None, border_color=True, icon=None):
    """Styles the button b as a flat pill (the stock dialogs' buttons do the same): the fill (down while pressed, disabled when given), round_radius, no border (border_color: the transparent one too),
    the label's ink at px (dim while disabled; no label style when ink is None) and the glyph. The one loop of the pills and the keyboard's keys."""
    for st in STATES:
        styled(b, (st,), 'bg_color', down if st == 'pressed' else disabled if disabled and st == 'disable' else fill)
        if ink is not None:
            styled(b, (st,), 'text_color', dim if dim and st == 'disable' else ink)
            styled(b, (st,), 'font_size', str(px))
        styled(b, (st,), 'border_width', '0')
        if border_color: styled(b, (st,), 'border_color', '#00000000')
        styled(b, (st,), 'round_radius', str(radius))
        if icon: styled(b, (st,), 'icon', icon)
    return b


def sg_pill(name, x, y, text, icon, ink=INK_RGB, w=None, down=SG_PILL_DOWN_RGB, dim='#666666'):
    """The Shuffle / Play pill: the glyph and the 18 px label, which the payload centres as a pair. Disabled: the fill SG_PILL_OFF_RGB and the label in dim."""
    o = OFFSETS
    b = Widget('button', x, y, w or o['SG_PILL_W'], o['SG_PILL_H'], [('name', name), ('enable', 'true'), pod_i18n.text_prop(text)])
    return flat_pill(b, SG_PILL_RGB, down, o['SG_PILL_R'], SG_PILL_OFF_RGB, ink, SG_PILL_PX, dim, icon=icon)


VS_SORT_KEYS = ('Title', 'Artist', 'Recently Added', 'Year')   # the Albums "..." card's sort rows in order (patch/covercache.h CC_SORT_*)
VS_VIEW_KEYS = ('Grid', 'List')                                  # the View group's rows (slots 4 and 5), shown above the sorts
VS_SEARCH_KEY = 'Search Albums'                                  # the optional first row (slot 6, with a search glyph and no tick), above the View group
VS_ROW_H, VS_TICK_X, VS_TICK_W, VS_GLYPH, VS_GLYPH_X, VS_LABEL_X, VS_LABEL_X_GLYPH = (OFFSETS[k] for k in (   # patch/offsets.inc: a tick column at x 14 (14 px), a glyph 10 px after it, the labels after the glyph
    'VS_ROW_H', 'VS_TICK_X', 'VS_TICK_W', 'VS_GLYPH', 'VS_GLYPH_X', 'VS_LABEL_X', 'VS_LABEL_X_GLYPH'))
VS_CARD_H = (len(VS_SORT_KEYS) + len(VS_VIEW_KEYS) + 1) * VS_ROW_H   # = mod_icons.GLASS_VIEWSORT's height (the six-row glass for a card one row short is the payload's choice, vs_glass6)
VS_SUB_PX, VS_SUB_Y, VS_SUB_H = 15, 25, 22   # a ticked sort row's second line (the direction): 15 px grey, y 25..47; its label then sits at y 5..27


def view_sort_card(sort_keys=VS_SORT_KEYS, view_keys=VS_VIEW_KEYS, search_key=VS_SEARCH_KEY, view_glyphs=('pod_ic_vsgrid', 'pod_ic_vslist'), select_key='Select', act_keys=None, act_glyphs=None):
    """(scrim, card): the "..." card of the pages with a sort order and a grid / list view (patch/viewsort.c; the Albums page first, docs/modules/albums.md), an Apple-style grouped menu in its own
    glass (vs_glass7, patch3_x): the Search Albums row, then the View group (Grid, List, each with its glyph; a tick on the current view) above the Sort group (Title, Artist, Recently Added, Year; a tick on the current one and,
    under its label, a 15 px grey line with the direction), seven 48 px rows, 13 % white hairlines between the groups (above the first sort row: that row's top border; under the Search row:
    the vs_hair widget, which the payload hides with the row), pressed 6 % white. Widget slots: the sorts are vs_item0..3, Grid vs_item4, List vs_item5, Search vs_item6 (laid out Search,
    Grid, List, then the sorts; Search has a glyph and no tick). The card is at its widest (PL_CARD_MAX); the payload narrows it to the language. The Albums page's texts are the defaults; the Artists page
    (patch/artists.c) gives its own: Name for the sort (a card offers the first sort rows it needs and hides the rest), Artists / Album Artists as the two view rows (the Show group) and Search Artists.
    The Playlists page (patch/playlists.c) gives four action rows instead of Search and Select (act_keys, with the glyph image names act_glyphs): slots 6..9, vs_item8 / 9 exist only then."""
    from mod_icons import GLASS_VIEWSORT
    assert VS_CARD_H == GLASS_VIEWSORT[1]
    scrim = modal_scrim('vs_scrim')
    card = hidden(Widget('view', PL_CARD_RIGHT - PL_CARD_MAX, PL_CARD_Y, PL_CARD_MAX, VS_CARD_H, [('name', 'vs_card')]))
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', 'vs_glass7')
        styled(card, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(card, (st,), 'border_width', '0')
    acts = tuple(act_keys) if act_keys else (search_key, select_key)
    act_gl = tuple(act_glyphs) if act_glyphs else ('pod_ic_vssearch', 'pod_ic_vsselect')
    assert len(acts) == len(act_gl) and len(acts) in (2, 3, 4)
    keys = tuple(sort_keys) + tuple(view_keys) + acts
    assert len(sort_keys) == len(VS_SORT_KEYS) and len(view_keys) == len(VS_VIEW_KEYS)
    slots = (6, 7, 8, 9)[:len(acts)] + (4, 5, 0, 1, 2, 3)   # the actions, Grid, List, Title, Artist, Recently Added, Year: the payload packs the rows a page offers (the asset is seven rows high, Select shares Grid's place until then)
    where = {6: 0, 7: 1, 8: 2, 4: 1, 5: 2, 0: 3, 1: 4, 2: 5, 3: 6} if len(acts) < 4 else {6: 0, 7: 1, 8: 2, 9: 3, 4: 4, 5: 5, 0: 6, 1: 6, 2: 6, 3: 6}   # (a third action, the Songs page's, shares List's place as Select shares Grid's; four actions, two views and one sort fill the seven rows; the other sort rows share the last)
    for slot in slots:
        pos = where[slot]
        key, y, glyph = keys[slot], pos * VS_ROW_H, slot >= len(VS_SORT_KEYS)
        hair = slot == 0   # the one 13 % hairline: between the groups
        item = Widget('button', 0, y, PL_CARD_MAX, VS_ROW_H, [('name', f'vs_item{slot}'), ('enable', 'true')])
        for st in STATES:
            styled(item, (st,), 'bg_color', PL_PRESSED if st == 'pressed' else '#00000000')
            styled(item, (st,), 'text_color', INK_RGB)
            styled(item, (st,), 'border', 'top' if hair else 'none')
            styled(item, (st,), 'border_width', '1' if hair else '0')
            styled(item, (st,), 'border_color', PL_HAIR if hair else '#00000000')
        x0 = VS_LABEL_X_GLYPH if glyph else VS_LABEL_X
        lab = Widget('hscroll_label', x0, 0, PL_CARD_MAX - x0 - 16, VS_ROW_H, [
            ('name', f'vs_label{slot}'), pod_i18n.text_prop(key), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(PL_LABEL_PX))
            styled(lab, (st,), 'text_color', INK_RGB)
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        item.children.append(lab)
        if slot < 6:   # (the Search and Select rows have no tick)
            item.children.append(hidden(Widget('image', VS_TICK_X, (VS_ROW_H - VS_TICK_W) // 2, VS_TICK_W, VS_TICK_W, [
                ('name', f'vs_tick{slot}'), ('image', 'sg_tick'), ('draw_type', 'default')])))
        if glyph:
            item.children.append(Widget('image', VS_GLYPH_X, (VS_ROW_H - VS_GLYPH) // 2, VS_GLYPH, VS_GLYPH, [
                ('name', f'vs_glyph{slot}'), ('image', {4: view_glyphs[0], 5: view_glyphs[1], **{6 + i: g for i, g in enumerate(act_gl)}}[slot]), ('draw_type', 'default'), ('sensitive', 'false')]))
        else:   # the direction under the label of the ticked sort row (the payload sets the text and the rows' positions)
            sub = hidden(Widget('hscroll_label', x0, VS_SUB_Y, PL_CARD_MAX - x0 - 16, VS_SUB_H, [
                ('name', f'vs_sub{slot}'), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')]))
            for st in ('normal', 'disable', 'focused'):
                styled(sub, (st,), 'font_size', str(VS_SUB_PX))
                styled(sub, (st,), 'text_color', SUB_RGB)
                styled(sub, (st,), 'text_align_h', 'left')
                styled(sub, (st,), 'text_align_v', 'middle')
            item.children.append(sub)
        card.children.append(item)
    hair = Widget('view', 0, VS_ROW_H, PL_CARD_MAX, 1, [('name', 'vs_hair'), ('sensitive', 'false')])   # the hairline under the Search row (the payload hides it without the row)
    for st in STATES: styled(hair, (st,), 'bg_color', PL_HAIR)
    card.children.append(hair)
    return scrim, card


def selall_button():
    """The select mode's Select All: a glass pill at the navbar's right (hidden and insensitive until select mode: every page with the mode and the folder picker). The glass is sg_selall_glass drawn
    patch3_x, so the width can follow the label: patch/selmode.c m1_selall_fit sets it at run time, right edge at SG_SELALL_R; the 104 px here is the stock width of "Select All" and a start."""
    o = OFFSETS
    sa = hidden(Widget('button', o['SG_SELALL_R'] - 104, o['SG_SELALL_Y'], 104, o['SG_SELALL_H'], [('name', 'btn_selall'), ('enable', 'true'), pod_i18n.text_prop('Select All')]))
    for st in STATES:
        styled(sa, (st,), 'bg_color', '#00000000')
        styled(sa, (st,), 'bg_image', 'sg_selall_glass_down' if st == 'pressed' else 'sg_selall_glass')
        styled(sa, (st,), 'bg_image_draw_type', 'patch3_x')
        styled(sa, (st,), 'text_color', SELECT_DIM if st == 'disable' else INK_RGB)   # disable: the folder picker's inert button (patch/lupick.c): the glass stays, the label dims
        styled(sa, (st,), 'font_size', '17')
        styled(sa, (st,), 'border_width', '0')
        styled(sa, (st,), 'border_color', '#00000000')
        styled(sa, (st,), 'text_align_h', 'center')
    return sa


SELECT_DIM = '#595959'   # the dimmed ink (35 % white): Select All in the folder picker's inert state
SB_SLOT_W, SB_BTN_H = 60, 42   # the select bar's capsule: 60 px icon slots, glass 42 px high (tools/mod_icons.py SELBAR_*)


def select_bar(name, buttons):
    """The select mode's bottom bar (hidden until select mode): no background, no hairline, ONE centred glass capsule of icon-only buttons [(name, piece)] floating over the list,
    vertically centred in the window's last SG_BAR_H rows (the list scrolls SG_BAR_H further, so the last row clears it). The bar view is the capsule's own box, so a touch beside it
    reaches the rows. 'add' and 'del' are the two 60 px slots of a 120 px capsule, 'one' is a 60 px capsule (Delete / Unsubscribe alone). The images are the capsule's slices
    sg_bar_<piece>, _down (the round highlight) and _off (the glyph at 35 %, nothing marked)."""
    o = OFFSETS
    w = SB_SLOT_W * (1 if all(p == 'one' for _, p in buttons) else 2)   # (the Podcasts bar's two 'one' pills share the one place)
    bar = hidden(Widget('view', (SCREEN_W - w) // 2, CLIENT_H - o['SG_BAR_H'] + (o['SG_BAR_H'] - SB_BTN_H) // 2, w, SB_BTN_H, [('name', name)]))
    for st in STATES: styled(bar, (st,), 'bg_color', '#00000000')
    bar.children = []
    for n, piece in buttons:
        b = Widget('button', SB_SLOT_W if piece == 'del' else 0, 0, SB_SLOT_W, SB_BTN_H, [('name', n), ('enable', 'true'), ('style', 'img_btn_style')])
        for st in STATES: styled(b, (st,), 'icon', f'sg_bar_{piece}_down' if st == 'pressed' else f'sg_bar_{piece}_off' if st == 'disable' else f'sg_bar_{piece}')
        bar.children.append(b)
    return bar


def azlist_labels():
    """The hidden text styles of the A-Z furniture (patch/azlist.c, shared by the Songs and Artists pages): the header letter, the rail letter and the touched rail letter."""
    return style_labels((('label_hdr', SG_HDR_PX, INK_RGB, 'left'), ('label_rail', SG_RAIL_PX, '#EEEEEC', 'center'), ('label_rail_on', SG_RAIL_PX, '#000000', 'center')),
                        {'label_rail_on': '#EEEEEC'})   # the letter on the disc: black on the accent (the contrast scan reads the label's own background)


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
        styled(letter, (st,), 'text_color', INK_RGB)
        styled(letter, (st,), 'font_size', str(SG_BUBBLE_PX))
        styled(letter, (st,), 'text_align_h', 'center')
        styled(letter, (st,), 'text_align_v', 'middle')
    bubble.children.append(letter)
    return [rail, bubble]


def build_artists_page(page):
    """The Artists / Genres / Composers page (patch/artists.c, docs/modules/artists.md): the Songs page's structure (a stock list holding one content view that paints the
    rows, the section letters and the pinned header; the rail and the bubble beside it; the large title in the content view, the small one in the navbar once it has scrolled
    away) under the navbar with the "..." (the capsule's left cap; its card: Search Artists, the Show group Artists / Album Artists, Name). No pills, no select mode."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, more_left=True)
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'artists_listview')
    sv = lv.children[0]
    sv.set('name', 'artists_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = large_title('ar_title', page.title)
    grid.children = [title]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/artists.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children.append(hidden(wf_image('ar_spin', (SCREEN_W - WF_SPIN_PX) // 2, room_y(WF_SPIN_PX), WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')))   # a source's list still loading (patch/libsrc.c ls_spin)
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB),))   # the row text style (the stock srlabel_leftwhite21_style's 21 px white)
    root.children.extend(azlist_labels())
    root.children.extend(azlist_rail())
    scrim, card = view_sort_card(sort_keys=('Name',) * len(VS_SORT_KEYS), view_keys=('Artists', 'Album Artists'), search_key='Search Artists', view_glyphs=('pod_ic_vsartist', 'pod_ic_vsalbumartist'))
    root.children.extend((scrim, card))   # (the "..." card: Search Artists, Show: Artists / Album Artists, Name)
    root.children.extend(row_menu(pins=True))   # last: the long press sheet of an artist (Play, Shuffle, Pin Artist / Unpin Artist; patch/artists.c, docs/modules/pins.md)
    return root


def text_field(x, y, w, h, fill, radius, text_x, text_w, px, hint_rgb, ink_rgb, caret_y, clear_x, clear_w, mag=None, sensitive=False):
    """The keyboard's text field (kb_field with an optional magnifier (x, size), the hint, text, caret and clear button; patch/keyboard.c keyboard_attach finds them by name) at x, y, w x h; the label and caret
    x are text_x, the labels are text_w wide, the caret_y and the clear button (clear_x, clear_w) are relative to the field. sensitive: the clear button inside needs it, and a tap on the field brings the keyboard back."""
    field = kb_view('kb_field', x, y, w, h, fill, radius)
    if sensitive: field.set('sensitive', 'true')
    kids = []
    if mag: kids.append(Widget('image', mag[0], (h - mag[1]) // 2, mag[1], mag[1], [('name', 'kb_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')]))
    hint = label('kb_hint', text_x, 0, text_w, h, '', px, hint_rgb, 'left')
    text = label('kb_text', text_x, 0, text_w, h, '', px, ink_rgb, 'left')
    for lab in (hint, text):
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
    caret = kb_view('kb_caret', text_x, caret_y, PK.CARET_W, PK.CARET_H, PK.KB_INK)
    clear = hidden(Widget('button', clear_x, 0, clear_w, h, [('name', 'kb_clear'), ('enable', 'true'), ('style', 'img_btn_style'),
                   ('style:pressed:icon', 'qk_clear'), ('style:normal:icon', 'qk_clear'), ('style:over:icon', 'qk_clear')]))
    field.children = kids + [hint, text, caret, clear]
    return field


def search_field_widget(y=PS.SE_FIELD_Y, w=PS.SE_FIELD_W, text_w=PS.SE_TEXT_W):
    """The Search page's field (the magnifier, hint, text, caret and clear button); the Radio and AutoEq pages have the same at y, w wide with text_w wide labels."""
    return text_field(PS.SE_FIELD_X, y, w, PS.SE_FIELD_H, PS.FIELD_RGB, PS.SE_FIELD_R, PS.SE_TEXT_X, text_w, PS.FIELD_PX, PS.FIELD_HINT, PS.FIELD_INK, PS.SE_CARET_Y,
                      w - PS.SE_CLEAR_W, PS.SE_CLEAR_W, (PS.SE_MAG_X, PK.FIELD_MAG), True)


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
    root.children.append(hidden(label('label_status', 10, 150, SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children.append(hidden(wf_image('se_spin', (SCREEN_W - WF_SPIN_PX) // 2, 120, WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')))   # a source's loading spinner (patch/search.c shows and turns it)
    root.children.append(hidden(label('label_title', 0, 0, 200, 22, '', 16, INK_RGB, 'left')))
    root.children[-1].set(*pod_i18n.text_prop(page.title))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB), ('label_chip', PS.SE_CHIP_PX, PS.CHIP_INK, 'center'),
                                   ('label_chip_on', PS.SE_CHIP_PX, PS.CHIP_ON_INK, 'center')), {'label_chip_on': PS.CHIP_ON_RGB})   # the dark text is on the selected pill (the contrast scan reads the label's own background)
    root.children += keyboard_pad_widgets()
    return root


PF_LIST_Y = PS.SE_FIELD_Y + PS.SE_FIELD_H + 8   # the in-show search's list: under the field (patch/pcfind.h PF_LIST_Y), to the window's bottom


def build_pcfind_page(page):
    """The search inside one show (patch/pcfind.c, docs/modules/podcasts.md "Search inside a show"): the Search page's field (the keyboard's own field widgets) and its round X (pf_close), a stock list
    holding one content view that paints the rows (a title, a grey line), the dim "No results" line and the keyboard's pad, strip and pop-up. Hidden labels carry the text styles (a played
    episode's title is the dim one); label_title (hidden) is the page's title, which the asset tests read from every page."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    lv = stock_list([], True, top=PF_LIST_Y)
    lv.set('name', 'pf_listview')
    sv = lv.children[0]
    sv.set('name', 'pf_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, CLIENT_H - PF_LIST_Y, [('name', 'pf_view')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(search_field_widget())
    root.children.append(Widget('button', PS.SE_CLOSE_X, PS.SE_CLOSE_Y, PS.SE_CLOSE_W, PS.SE_CLOSE_H, [
        ('name', 'pf_close'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:over:icon', 'se_close'), ('style:normal:icon', 'se_close'), ('style:pressed:icon', 'se_close_down')]))
    root.children.append(hidden(label('pf_status', 10, 150, SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children.append(hidden(label('label_title', 0, 0, 200, 22, '', 16, INK_RGB, 'left')))
    root.children[-1].set(*pod_i18n.text_prop(page.title))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB), ('label_row_dim', LIST_TITLE_PX, PS.SUB_RGB), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB)))
    root.children += keyboard_pad_widgets()
    return root


AE_LIST_Y = NAVBAR_H + 48   # the AutoEq page's list: under the bar, its rows from Radio's search level (patch/radiopage.c RP_TOP_SEARCH 48 below the bar), so they start under the field (patch/autoeq.c AE_LIST_Y)


def build_autoeq_page(page):
    """The AutoEq download page (patch/autoeq.c, docs/modules/peq.md "AutoEq download"): Radio's search level's top, the glass navbar (Back, the title, Now Playing as the disc) over the search field
    (y 56, the page's width, no round X: RD_FIELD_W, RD_TEXT_W), a stock list holding one content view the payload paints from AE_LIST_Y, the state line and the keyboard's pad."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))   # btn_return (Back), the small title, btn_backtoplayer (Now Playing's disc)
    lv = stock_list([], True, top=AE_LIST_Y)
    lv.set('name', 'se_listview')
    sv = lv.children[0]
    sv.set('name', 'se_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, PS.SE_LIST_H + PS.SE_LIST_Y - AE_LIST_Y, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    sv.children.append(grid)
    root.children.append(lv)
    field = search_field_widget(56, RD_FIELD_W, RD_TEXT_W)
    root.children.append(field)
    root.children.append(hidden(label('label_status', 10, 150, SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB)))
    root.children += keyboard_pad_widgets()
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
    title = large_title('sg_title', page.title)
    foot = label('sg_foot', o['SG_HDR_X'], 0, SCREEN_W - 2 * o['SG_HDR_X'], o['SG_FOOT_TEXT_H'], '', o['SG_FOOT_PX'], SG_FOOT_RGB, 'left')   # the song count: the payload sets the text and puts it under the last row
    foot.set('sensitive', 'false')
    styled(foot, ('normal',), 'text_align_v', 'middle')
    # a playlist's header (patch/songs.c, class 0xff13): the name and the count, centred under the mosaic the payload paints; the payload moves the pills down and
    # shows these two (hidden and insensitive here, like every decoration it shows later)
    hname = hidden(label('sg_hname', o['PH_NAME_X'], o['PH_NAME_Y'], o['PH_NAME_W'], o['PH_NAME_H'], '', 22, INK_RGB, 'center'))
    hname2 = hidden(label('sg_hname2', o['PH_NAME_X'], o['PH_NAME_Y'] + o['AH_TITLE_LH'], o['PH_NAME_W'], o['PH_NAME_H'], '', 22, INK_RGB, 'center'))   # the name's second line (m1_wrap2)
    for lab in (hname, hname2):   # vertically middle, no side margins: m1_wrap2 fits each line to the full PH_NAME_W
        for k, v in (('text_align_v', 'middle'), ('margin_left', '0'), ('margin_right', '0')): styled(lab, ('normal',), k, v)
    # the library's flat pills, and a playlist's header disc and pill (the album page's; hidden, patch/songs.c sg_pills shows one set)
    pills, ptext = play_header(o['PH_BTN_Y'])
    grid.children = [title, hname, hname2, sg_pill('btn_play', o['SG_PILL_X0'], o['SG_PILL_Y'], 'Play', 'sg_play', down=SG_PILL_PRESS_RGB),
                     sg_pill('btn_shuffle', o['SG_PILL_X1'], o['SG_PILL_Y'], 'Shuffle', 'sg_shuffle', down=SG_PILL_PRESS_RGB), *pills, foot,
                     hidden(wf_image('sg_spin', (SCREEN_W - WF_SPIN_PX) // 2, room_y(WF_SPIN_PX, NAVBAR_H + o['SG_TITLE_H']) - NAVBAR_H, WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')),
                     hidden(wf_image('sg_hpencil', 0, o['PH_NAME_Y'], 16, 16, 'sg_pencil', 'default'))]   # a source's loading spinner (the payload places, shows and turns it)
    root.children.append(ptext)
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/songs.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB),
                                   ('label_row_dim', LIST_TITLE_PX, DIM_RGB), ('label_row_subdim', LIST_SUB_PX, DIM_RGB),   # a source's rows that cannot play
                                   ('label_grid_title', GRID_ALBUM_PX, INK_RGB), ('label_grid_sub', GRID_ARTIST_PX, SUB_RGB)))   # the last two: Recently Added's album grid
    root.children.extend(azlist_labels())
    root.children.extend(azlist_rail())
    songs_bar = select_bar('sg_bar', [('sg_add', 'add'), ('sg_del', 'del')])
    for n, piece, x in (('sg_edel', 'edel', 0), ('sg_eplus', 'eplus', SB_SLOT_W)):   # a stock playlist's Edit mode: Delete | + over Add | Delete (patch/songs.c sg_bar_edit), hidden and insensitive until then
        b = hidden(Widget('button', x, 0, SB_SLOT_W, SB_BTN_H, [('name', n), ('enable', 'true'), ('style', 'img_btn_style')]))
        for st in STATES: styled(b, (st,), 'icon', f'sg_bar_{piece}_down' if st == 'pressed' else f'sg_bar_{piece}_off' if st == 'disable' else f'sg_bar_{piece}')
        songs_bar.children.append(b)
    root.children.append(songs_bar)
    root.children.extend(view_sort_card(sort_keys=pod_pages.SONGS_SORT_KEYS, view_keys=('Albums', 'Songs'), act_keys=('Rename', 'Select', 'Clean Up', 'Pin Playlist'),
                                        act_glyphs=('pod_ic_vsrename', 'pod_ic_vsselect', 'pod_ic_vsclean', 'pod_ic_vspin')))   # above the list, the rail and the select bar (the "..." card: Select, a playlist's Rename (slot 6, packed under Select: VS_SELECT_FIRST), Clean Up Playlist (slot 8) and Pin Playlist / Unpin Playlist (slot 9), Albums / Songs on Recently Added, the four sort rows of the library; vs_bind hides what a list does not offer; Search is the navbar button)
    root.children.extend(row_menu())   # last: above everything (the track rows' "..." menu, patch/rowmenu.c)
    return root


# The album page (patch/albumpage.c, docs/modules/album-page.md; the numbers are patch/offsets.inc AH_* and AB_*): the stock album page's design with our own glass controls. The list is the
# whole 450 px window (list_view > scroll_view + the mobile scroll bar, the library lists' structure) holding one content view, view_grid, that paints the cover, the tracks and
# their press fill itself and holds the header's widgets: the title, the artist and the "year . N tracks" line (centred hscroll_labels that scroll a long text), the Shuffle disc (a
# button, its picture the disc), the Play pill (a button, its picture the pill) with its glyph (an image) and its text (a label) over it, which the payload centres as a pair.
# The window's colour is the cover's tone (the payload sets it); the gradient image img_ah_tint, first in the window, darkens it from the top (the stock page's), and the list over it is
# transparent. The glass controls are the window's last child, so they paint and take touches over the rows: Back, Select | Now Playing as one capsule (the genre songs list's), and
# in select mode the close x (Back), "N Selected" and Select All in the navbar and the bottom bar with Add to Playlist and Delete. Two hidden labels carry the rows' text styles (the number, the title; the playing row's number is the ah_wave image); label_title (hidden) is the page's title for the i18n and asset tests.
AB_STYLES = (('label_row_num', OFFSETS['AB_NUM_PX'], SUB_RGB, 'right'), ('label_row_title', LIST_TITLE_PX, INK_RGB),   # the number (the grey line's colour) and the title (white) at the list title size like every list
             ('label_row_dim', LIST_TITLE_PX, DIM_RGB),   # a source's rows: the title of a row that cannot play
             ('label_row_disc', OFFSETS['AB_DISC_PX'], SUB_RGB))   # a multi-disc album's "Disc N" headings
AB_META = (('ab_title', 'AH_TITLE_Y', 'AH_TITLE_H', 22, INK_RGB), ('ab_artist', 'AH_ARTIST_Y', 'AH_ARTIST_H', 18, SUB_RGB), ('ab_meta', 'AH_META_Y', 'AH_META_H', 15, '#9C9C9C'))   # srlabel_ah{title,artist,meta}_style
AB_FOOT_RGB = SUB_RGB   # the footer's grey: the artist line's (not the meta line's #9C9C9C)
AB_PLAY_TEXT_W = OFFSETS['AB_PLAY_TEXT_W']   # the English "Play" at 18 px, where the payload cannot measure it; the payload centres the pair for the language


def ab_nav_button(name, x, w, rest, down=None, hide=False):
    b = Widget('button', x, 0, w, NAVBAR_H, [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                                             ('style:pressed:icon', down or rest), ('style:normal:icon', rest), ('style:over:icon', rest)])
    if w == NAV_VIEW_W: b.set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))
    return hidden(b) if hide else b


def album_navbar(page):
    """The glass controls of the album page, the window's last children: Back, the capsule "..." | Now Playing (the "..." is the left cap),
    and the select mode's title (label_title) and Select All text button (hidden until select mode). They are the window's own children, not a bar view's: a view over the list would take every touch
    in its band (this AWTK's hit test never descends into an insensitive container), and a drag that starts between the discs must scroll the list."""
    title = hidden(Widget('label', NAV_TITLE_X, 14, NAV_VIEW_X - NAV_TITLE_X, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))   # shown only in select mode (patch/selmode.c)
    return [title,
            ab_nav_button('btn_return', NAV_BACK_X, NAV_BACK_W, 'ah_nav_back', 'ah_nav_back_down'),
            ab_nav_button('btn_more', NAV_VIEW_X, NAV_VIEW_W, 'pod_nav_more', 'pod_nav_more_down', hide=True),   # the capsule's left cap on the 214 slot: a source's page: the "..." card below (Download Album); the library's: the popup below (Pin Album, Add to Playlist, Play Next, Play After, Select; patch/albumpage.c ab_on_more)
            ab_nav_button('btn_backtoplayer', NAV_PLAY_X, NAV_PLAY_W, 'ah_nav_play', 'ah_nav_play_down'),
            selall_button()]


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
            if name == 'ab_title':   # no side margins: m1_wrap2 fits each line to the full AH_TEXT_W
                styled(lab, (st,), 'margin_left', '0')
                styled(lab, (st,), 'margin_right', '0')
        kids.append(lab)
        if name == 'ab_title':   # the title's second line (patch/albumpage.c ab_head_place: shown, and the lines under it moved down AH_TITLE_LH, when the title takes two)
            lab2 = Widget('hscroll_label', o['AH_TEXT_X'], o[y] + o['AH_TITLE_LH'], o['AH_TEXT_W'], o[h], [(k, 'ab_title2' if k == 'name' else v) for k, v in lab.props])
            kids.append(hidden(lab2))
    kids.append(ab_button('btn_shuffle', o['AH_SHUF_X'], o['AH_SHUF_W'], 'ah_shuffle', 'ah_shuffle_down'))
    kids.append(ab_button('btn_play', o['AH_PLAY_X'], o['AH_PLAY_W'], 'ah_pill', 'ah_pill_down'))
    pair = o['AH_PILL_GLYPH'] + o['AH_PILL_GAP'] + AB_PLAY_TEXT_W
    gx = o['AH_PLAY_X'] + (o['AH_PLAY_W'] - pair) // 2
    kids.append(Widget('image', gx, o['AH_BTN_Y'] + (o['AH_BTN_H'] - o['AH_PILL_GLYPH']) // 2, o['AH_PILL_GLYPH'], o['AH_PILL_GLYPH'], [('name', 'ab_glyph'), ('image', 'ah_play'), ('draw_type', 'center'), ('sensitive', 'false')]))
    foot = hidden(label('ab_foot', o['AB_NUM_X'], 0, SCREEN_W - o['AB_NUM_X'] - o['AB_FOOT_R'], o['AB_FOOT_TEXT_H'], '', o['AB_FOOT_PX'], AB_FOOT_RGB, 'left'))   # the track count and the duration under the last row: the payload sets the text and the place, and shows it once the duration is known
    styled(foot, ('normal',), 'text_align_v', 'middle')
    kids.append(foot)
    kids.append(hidden(wf_image('ab_spin', (SCREEN_W - WF_SPIN_PX) // 2, o['AH_BTN_Y'] + (o['AH_BTN_H'] - WF_SPIN_PX) // 2, WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')))   # the loading spinner where the pills will be while a source's tracks are on their way (the payload shows it and turns the frames)
    grid.children = kids
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(play_text('ab_play_text'))   # the pill's text style and its translated text; the payload paints the text over the pill
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels(AB_STYLES)
    root.children.append(select_bar('sg_bar', [('sg_add', 'add'), ('sg_del', 'del')]))   # the select mode's capsule over the rows
    root.children.extend(album_navbar(page))   # the glass controls paint and take touches over the list
    root.children.extend(view_sort_card(sort_keys=('Name',) * len(VS_SORT_KEYS), act_keys=('Download Album', 'Select'), act_glyphs=('pod_ic_vsdownload', 'pod_ic_vsselect')))   # a source's "..." card (patch/albumpage.c: Download Album, the first row)
    root.children.extend(popup_menu())   # the library's "...": Pin Album, Add to Playlist, Play Next, Play After, Select (patch/albumpage.c ab_on_more)
    root.children.extend(row_menu())   # last: the track rows' "..." menu (patch/rowmenu.c) covers the navbar too
    return root


def play_header(y):
    """The album page's Shuffle disc and Play pill for a playlist's header on the Songs page (patch/common.c m1_pill_place): (the content view's widgets, hidden and insensitive until patch/songs.c sg_pills shows them; the hidden label the pill's text is painted with).
    y is the 44 px buttons' top (PH_BTN_Y); the glyph is placed for the English text and the payload centres it for the language."""
    o = OFFSETS
    pair = o['AH_PILL_GLYPH'] + o['AH_PILL_GAP'] + AB_PLAY_TEXT_W
    gx = o['AH_PLAY_X'] + (o['AH_PLAY_W'] - pair) // 2
    kids = [ab_button('hd_shuffle', o['AH_SHUF_X'], o['AH_SHUF_W'], 'ah_shuffle', 'ah_shuffle_down', y),
            ab_button('hd_play', o['AH_PLAY_X'], o['AH_PLAY_W'], 'ah_pill', 'ah_pill_down', y),
            Widget('image', gx, y + (o['AH_BTN_H'] - o['AH_PILL_GLYPH']) // 2, o['AH_PILL_GLYPH'], o['AH_PILL_GLYPH'], [('name', 'sg_glyph'), ('image', 'ah_play'), ('draw_type', 'center'), ('sensitive', 'false')])]
    return [hidden(k) for k in kids], play_text('sg_play_text')


def play_text(name):
    """The Play pill's text style and translated text (hidden; the payload paints the text over the pill)."""
    t = hidden(Widget('label', 0, 0, 10, 10, [('name', name), pod_i18n.text_prop('Play')]))
    for st in ('normal', 'pressed', 'disable', 'focused'):
        styled(t, (st,), 'font_size', '18')
        styled(t, (st,), 'text_color', '#141414')
        styled(t, (st,), 'text_align_h', 'left')
        styled(t, (st,), 'text_align_v', 'middle')
        styled(t, (st,), 'bg_color', INK_RGB)   # the dark text of the white pill: the contrast scan reads the label's own background
    return t


def ab_button(name, x, w, rest, down, y=None):
    o = OFFSETS
    return Widget('button', x, o['AH_BTN_Y'] if y is None else y, w, o['AH_BTN_H'], [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                                                                 ('style:pressed:icon', down), ('style:normal:icon', rest), ('style:over:icon', rest)])


# The Queue page (patch/queuepage.c, docs/modules/queue.md; the numbers are patch/offsets.inc QP_*): the play queue in the album page's structure. The list is the whole 450 px window
# holding one content view, view_queue, that paints the rows (the Songs page's) and holds the header's widgets: the playing track's title and artist (hscroll_labels), the Shuffle and
# Repeat buttons (the Songs page's flat pills, icon only), the section line "Queue" with the song count at its right. The cover is painted by the payload. The window is black; the
# glass Back is the window's last child, over the rows.
QP_HEAD_PX, QP_EMPTY_PX = 20, 16
QP_EMPTY_RGB = SUB_RGB
QP_CLEAR_PX, QP_CLEAR_RGB, QP_CLEAR_DOWN_RGB = 17, SUB_RGB, '#7A7A7A'   # the Clear text button: neutral grey, dimmer while pressed
QP_OFF_RGB, QP_OFF_DOWN_RGB = RAISED_RGB, '#3A3A3D'   # a mode button that is off (the payload sets the lit look: #C8C8C8, pressed #A8A8A8, with the dark glyph); patch/offsets.inc QP_PILL_*; pressed #3A3A3D is palette.ROLE_PRESS_QPILL (one blue level off #3A3A3C)


def qp_button(name, x, icon):
    """An icon-only flat button (the Songs page's pill without its label): the glyph is centred by the button's own style."""
    o = OFFSETS
    b = Widget('button', x, o['QP_PILL_Y'], o['QP_PILL_W'], o['SG_PILL_H'], [('name', name), ('enable', 'true')])
    return flat_pill(b, QP_OFF_RGB, QP_OFF_DOWN_RGB, o['SG_PILL_R'], icon=icon)


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
    for name, y, h, px, colour in (('qp_title', 'QP_TITLE_Y', 'QP_TITLE_H', 20, INK_RGB), ('qp_artist', 'QP_ARTIST_Y', 'QP_ARTIST_H', 16, SUB_RGB)):
        lab = Widget('hscroll_label', o['QP_TEXT_X'], o[y], o['QP_TEXT_W'], o[h], [('name', name), ('text', ''), ('sensitive', 'false'), ('yoyo', 'true'), ('loop', 'true'), ('lull', CAPTION_LULL), ('ellipses', 'true')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px))
            styled(lab, (st,), 'text_color', colour)
            styled(lab, (st,), 'text_align_h', 'left')
        kids.append(lab)
    kids.append(qp_button('btn_shuffle', o['QP_PILL_X0'], 'sg_shuffle'))
    kids.append(qp_button('btn_repeat', o['QP_PILL_X1'], 'sg_repeat'))
    head = Widget('label', o['SG_HDR_X'], o['QP_HEAD_Y'], 310 - o['SG_HDR_X'], o['QP_HEAD_H'], [('name', 'qp_head'), pod_i18n.text_prop('Queue'), ('sensitive', 'false')])
    for prop, v in (('text_color', INK_RGB), ('font_size', str(QP_HEAD_PX)), ('text_align_h', 'left'), ('text_align_v', 'middle')): styled(head, ('normal',), prop, v)
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
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB)))
    root.children.extend(queue_navbar(page))   # the glass controls paint and take touches over the list
    root.children.extend(row_menu(queue=True))   # last: the Queue page's "..." sheet covers the navbar too (patch/rowmenu.c)
    return root


# The Daily Mix page (patch/dailymix.c dp_*, docs/modules/dailymix.md "The page"; tools/pod_dailymix.py DP_* and patch/offsets.inc carry the numbers): no navbar. The list is the
# whole 450 px window (list_view > scroll_view + the mobile scroll bar, the library lists' structure) holding one content view, view_dm, that paints the art, the texts and the
# songs itself (as the Albums page's view_grid) and holds the three widgets that need images or touches: the Shuffle disc, the white Play pill and the pill's dark play glyph
# (insensitive: the pill takes the tap). A floating glass back disc (btn_return, the window's last child: fixed, over the list) is the only control outside the list.
# Seven hidden, insensitive labels carry the text styles (the payload sets their colours from the tint). label_title (hidden) is the page's title: the i18n and asset tests
# read it from every page; nothing shows it. The window, the list and the view are black here: the payload sets the tint on all of them (black is the fallback).
DP_STYLES = (('label_dp_title', 'DP_TITLE_PX', INK_RGB, 'center'), ('label_dp_sub', 'DP_SUB_PX', INK_RGB, 'center'), ('label_dp_upd', 'DP_UPD_PX', INK_RGB, 'center'),
             ('label_dp_desc', 'DP_DESC_PX', INK_RGB, 'left'), ('label_dp_play', 'DP_PLAY_PX', INK_RGB, 'left'), ('label_dp_row', 'DP_ROW_PX', INK_RGB, 'left'),
             ('label_dp_artist', 'DP_ARTIST_PX', INK_RGB, 'left'))
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
            ('name', 'img_dp_glyph'), ('image', 'ah_play'), ('draw_type', 'center'), ('sensitive', 'false')]),
        Widget('button', D.DP_ADD_X, D.DP_BTN_Y, D.DP_ADD_W, D.DP_BTN_H, [   # saves the mix as a stock playlist (Shuffle's disc mirrored, a plus)
            ('name', 'btn_dp_add'), ('enable', 'true'), ('style', 'img_btn_style'),
            ('style:pressed:icon', 'dp_add_down'), ('style:normal:icon', 'dp_add'), ('style:over:icon', 'dp_add')])]
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(Widget('button', D.DP_BACK_X, D.DP_BACK_Y, D.DP_BACK_BTN, D.DP_BACK_BTN, [
        ('name', 'btn_return'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', 'dp_back_down'), ('style:normal:icon', 'dp_back'), ('style:over:icon', 'dp_back')]))
    root.children += style_labels([(name, globals()[px] if px in globals() else getattr(D, px), colour, align) for name, px, colour, align in DP_STYLES])
    root.children.append(hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)])))
    return root


# The iPod page (patch/ipod.c, docs/modules/ipod.md; the numbers are patch/offsets.inc IP_*): a fullscreen window (the lock screen's `fullscreen = true`, so the stock status bar is not drawn and
# the window is 320 x 480) in the wheel's body colour. ipod_screen (320 x 240) is painted by the payload in its own EVT_AFTER_PAINT and takes no touch (insensitive); ipod_wheel
# (220 x 220, the touch target: the payload does the circle's hit test and grabs the touch) holds the wheel picture as an insensitive image child. Twelve hidden, insensitive labels
# only carry the text styles. label_title (hidden) is the page's title for the i18n and asset tests.
IP_STYLES = (('label_ip_row', 18, '#000000', 'left'), ('label_ip_sel', 18, INK_RGB, 'left'), ('label_ip_selb', 18, INK_RGB, 'left'), ('label_ip_title', 16, '#000000', 'left'),
             ('label_ip_small', 16, '#666666', 'left'), ('label_ip_subsel', 16, INK_RGB, 'left'), ('label_ip_np1', 18, '#000000', 'left'), ('label_ip_np2', 16, '#3C3C3C', 'left'), ('label_ip_time', 16, '#000000', 'right'),
             ('label_ip_val', 16, '#0C62D2', 'left'), ('label_ip_np3', 14, '#3C3C3C', 'left'), ('label_ip_shuf', 14, '#0C62D2', 'left'))


def build_ipod_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#C6C9CE')
    screen = Widget('view', 0, 0, o['IP_W'], o['IP_SCREEN_H'], [('name', 'ipod_screen'), ('sensitive', 'false')])
    styled(screen, ('normal',), 'bg_color', INK_RGB)
    wheel = Widget('view', o['IP_WHEEL_X'], o['IP_WHEEL_Y'], o['IP_WHEEL_D'], o['IP_WHEEL_D'], [('name', 'ipod_wheel')])
    wheel.children = [Widget('image', 0, 0, o['IP_WHEEL_D'], o['IP_WHEEL_D'], [('name', 'ipod_wheel_img'), ('image', 'ipod_wheel'), ('draw_type', 'default'), ('sensitive', 'false')])]
    root.children = [screen, wheel]
    # the style labels sit in two hidden, insensitive views whose background is the colour the text is drawn on (the theme scan reads a label's contrast against it)
    light = hidden(Widget('view', 0, 0, 10, 10, [('name', 'ip_styles_light')])); styled(light, ('normal',), 'bg_color', INK_RGB)
    blue = hidden(Widget('view', 0, 0, 10, 10, [('name', 'ip_styles_blue')])); styled(blue, ('normal',), 'bg_color', '#0C62D2')
    for lab in style_labels(IP_STYLES):
        if lab.name == 'label_ip_selb':   # the bold face (ly_font; the payload uses it for the Cover Flow card's Latin album title only)
            for st in ('normal', 'disable', 'focused'): styled(lab, (st,), 'font_name', 'lyrics')
        (blue if lab.name in ('label_ip_sel', 'label_ip_selb', 'label_ip_subsel') else light).children.append(lab)
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
    holder.children = [*style_labels((('label_tp_font', 16, INK_RGB),)), hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))]
    root.children = [view, holder]
    return root


# The idle lyrics page (patch/idlelyrics.c, docs/modules/idlelyrics.md; the numbers are patch/offsets.inc IL_*): a fullscreen window (320 x 480, no status bar) in the Now Playing tone (the payload sets
# its colour) with the cover tint and the lyrics scrim over it (np_tint_idle, np_scrim_idle: insensitive images), then il_view, the touch target over the whole window (transparent; the payload paints the
# rounded cover in its own EVT_AFTER_PAINT), the title and the artist (hscroll_labels that end in an ellipsis and never scroll, as the mini bar's), il_lyrics (the engine's box: a scroll_view of the
# lyrics, LY_W x IL_BOX_H) and the hint (20 px #AAAAAA, hidden and insensitive until the track has no lyrics). The window takes Now Playing's theme (styles/playing_page.bin) for the lyric label styles
# the engine names (np_lyric_style[_m|_s], np_lyric_cjk_style[_m|_s]). label_title (hidden) is the page's name for the i18n and asset tests.
def build_idlelyrics_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('theme', 'playing_page'), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#202020')
    tint = Widget('image', 0, 0, o['IL_W'], o['IL_H'], [('name', 'img_il_tint'), ('image', 'np_tint_idle'), ('draw_type', 'default'), ('sensitive', 'false')])
    scrim = Widget('image', 0, 0, o['IL_W'], o['IL_H'], [('name', 'img_il_scrim'), ('image', 'np_scrim_idle'), ('draw_type', 'default'), ('sensitive', 'false')])
    view = Widget('view', 0, 0, o['IL_W'], o['IL_H'], [('name', 'il_view')])
    for st in ('normal', 'disable', 'focused'): styled(view, (st,), 'bg_color', '#00000000')
    title = scroll_text('il_title', o['IL_TEXT_X'], o['IL_TITLE_Y'], o['IL_TEXT_W'], o['IL_TITLE_H'], o['IL_TITLE_PX'], MB_TITLE_RGB, 'left')
    artist = scroll_text('il_artist', o['IL_TEXT_X'], o['IL_ARTIST_Y'], o['IL_TEXT_W'], o['IL_ARTIST_H'], o['IL_ARTIST_PX'], MB_ARTIST_RGB, 'left')
    box = Widget('scroll_view', o['IL_BOX_X'], o['IL_BOX_Y'], o['LY_W'], o['IL_BOX_H'], [('name', 'il_lyrics'), ('floating', 'false')])
    for st in ('normal', 'disable', 'focused'): styled(box, (st,), 'bg_color', '#00000000')
    hint = hidden(scroll_text('il_hint', o['IL_BOX_X'], o['IL_BOX_Y'], o['LY_W'], o['IL_BOX_H'], o['IL_HINT_PX'], SUB_RGB, 'center', 'No Lyrics Found'))
    root.children = [tint, scrim, view, title, artist, box, hint,
                     hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))]
    return root


# The Vinyl page (patch/vinyl.c, docs/modules/vinyl.md): a fullscreen window (320 x 480, portrait), one view over the whole window (vinyl_view: the touch target, painted by the
# payload in its own EVT_AFTER_PAINT) and the text over it as insensitive hscroll_labels that never scroll (cut with an ellipsis; tools/vinyl_art.py TEXT): the title (the payload sets its font: the bold face lyrics for a Latin / Greek /
# Cyrillic title, the default font for any other, patch/lyrics.c ly_title_face), the artist, the times, the status line. label_title (hidden) is the page's name for the i18n and asset tests.
VN_LABELS = (('vn_title', 'title', 0), ('vn_artist', 'artist', 0), ('vn_times', 'times', 0), ('vn_status', 'status', 0))


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
        for st in ('normal', 'disable', 'focused'): styled(title, (st,), 'text_color', SURFACE_RGB)
    root.children.append(title)
    return root


# The VU Meter page (patch/vupage.c, docs/modules/vu.md): the Vinyl page's structure, one view (vu_view) painted by the payload and the same four labels (tools/vu_art.py TEXT).
VU_LABELS = (('vu_title', 'title', 0), ('vu_artist', 'artist', 0), ('vu_times', 'times', 0), ('vu_status', 'status', 0))


def build_vu_page(page):
    import vu_art
    bg = '#%02X%02X%02X' % tuple(vu_art.WINDOW_BG)
    root = Widget('window', 0, 0, 0, 0, [('name', page.name), ('fullscreen', 'true')])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', bg)
    view = Widget('view', 0, 0, 320, 480, [('name', 'vu_view')])
    styled(view, ('normal',), 'bg_color', bg)
    root.children = [view]
    for name, field, dx in VU_LABELS:
        t = vu_art.TEXT[field]; x, y, w, h = vu_art.label_box(field)
        lab = Widget('hscroll_label', x + dx, y, w, h, [('name', name), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(t['px']))
            styled(lab, (st,), 'text_color', '#%02X%02X%02X' % t['rgb'])
            styled(lab, (st,), 'text_align_h', 'left')
            styled(lab, (st,), 'text_align_v', 'middle')
        root.children.append(lab)
    title = hidden(Widget('label', 36, 14, 200, 22, [('name', 'label_title'), ('style', 'navbar_label_white'), pod_i18n.text_prop(page.title)]))
    for st in ('normal', 'disable', 'focused'): styled(title, (st,), 'text_color', SURFACE_RGB)   # (never seen; the build's contrast scan reads it against the light faceplate)
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
# The states (patch/onlineart.c oa_es_fail / oa_es_state; test/pod/onlineartpage.py proves the payload shows exactly these; tools/preview/preview_onlineart.py draws them): name -> (glyph image, title, explanation, Try Again pill).
# "Searching…" has only the title. The failure titles are the Podcasts' words.
OA_ES_STATES = {
    'lyrics busy': ('pod_es_timer', 'Lyrics Service Busy', 'LRCLIB is under heavy load. Try again in a moment.', True),
    'covers busy': ('pod_es_timer', 'Cover Service Busy', 'iTunes and Deezer are busy. Try again in a moment.', True),
    'no lyrics': ('pod_es_music', 'No Lyrics Found', 'LRCLIB has no lyrics for this song.', False),
    'no covers': ('pod_es_image', 'No Covers Found', 'Nothing on iTunes or Deezer for this album.', False),
    'photos busy': ('pod_es_timer', 'Photo Service Busy', 'The photo service is busy. Try again in a moment.', True),   # Find Artist Photo (onlineart_open_artist): the two states of its own; the others are shared
    'no photos': ('pod_es_image', 'No Photos Found', 'No photos online for this artist.', False),
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


OA_STATUS =(16, 214, 288, OA_ES_TITLE_H, 18, INK_RGB)    # x, y, w, h, px, colour: the title of the state block
OA_HEAD_TITLE = (16, 52, 288, 20, 17, INK_RGB)   # the lyrics detail's header, in the chip row's place
OA_HEAD_SUB = (16, 72, 288, 15, 13, SUB_RGB)
OA_LPILL = (16, 400, 288, 40)    # the lyrics detail's pill (window y); the text lines stop above it (OA_LY_H of patch/onlineart.c)
OA_DC = (0, NAVBAR_H, SCREEN_W, CLIENT_H - NAVBAR_H)   # the cover detail's container (window y)
OA_DC_ART = (40, 8, 240, 240)    # the larger cover (container y)
OA_DC_LABELS = (   # name, y (container), h, px, colour: the album, the artist, the source, the failure line
    ('oa_dc_name', 256, 26, 20, INK_RGB),
    ('oa_dc_artist', 282, 22, 16, SUB_RGB),
    ('oa_dc_source', 304, 20, 13, SUB_RGB),
    ('oa_hint', 326, 20, 14, SUB_RGB))
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
    return flat_pill(pill, SG_PILL_RGB, SG_PILL_DOWN_RGB, max(OFFSETS['SG_PILL_R'], h // 2), SG_PILL_OFF_RGB, INK_RGB, px)


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
    root.children.append(hidden(_oa_label('oa_es_text', (SCREEN_W - OA_ES_TEXT_W) // 2, OA_ES_CENTRE - 20, OA_ES_TEXT_W, OA_ES_TEXT_H, OA_ES_TEXT_PX, SUB_RGB, valign='top')))
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
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, PS.TITLE_RGB), ('label_row_sub', LIST_SUB_PX, PS.SUB_RGB), ('label_chip', PS.SE_CHIP_PX, PS.CHIP_INK, 'center'),
                                   ('label_chip_on', PS.SE_CHIP_PX, PS.CHIP_ON_INK, 'center'), ('label_badge', OA_BADGE_PX, PS.SUB_RGB, 'center'), ('label_badge_on', OA_BADGE_PX, PS.CHIP_ON_INK, 'center'),
                                   ('label_line', OA_LINE_PX, INK_RGB)), {'label_chip_on': PS.CHIP_ON_RGB, 'label_badge': PS.SEP_RGB, 'label_badge_on': PS.CHIP_ON_RGB})
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
    root.children.append(_oa_label('up_title', (SCREEN_W - UP_TITLE_W) // 2, UP_YS[1], UP_TITLE_W, UP_TITLE_H, UP_TITLE_PX, INK_RGB))
    root.children.append(hidden(_oa_label('up_text', (SCREEN_W - UP_TEXT_W) // 2, UP_YS[2], UP_TEXT_W, UP_TEXT_H, UP_TEXT_PX, SUB_RGB, valign='top')))
    root.children.append(_oa_pill('up_pill', (SCREEN_W - UP_PILL_W) // 2, UP_YS[3], UP_PILL_W, UP_PILL_H, UP_PILL_PX))
    root.children.append(_oa_pill('up_pill2', (SCREEN_W - UP_PILL_W) // 2, UP_YS[4], UP_PILL_W, UP_PILL_H, UP_PILL_PX))
    root.children.extend(podcasts_dialog('up_pd', 'Downloading %s', big=True))   # last: above everything
    return root


# Release Notes (patch/relnotes.c, docs/modules/update.md "Release notes"): the stock navbar over a stock list (list_view > scroll_view + scroll bar) holding one content view the payload paints the heading and the wrapped
# notes on, as the Find Cover & Lyrics lyrics detail does. Two hidden labels only carry the text styles (22 px white heading, 18 px light grey text). Neutral, no accent colour.
RN_HEAD_PX, RN_LINE_PX, RN_LINE_RGB = 22, 18, '#E6E6E6'
RN_CARD_LINE_PX = 15   # the Card Script pages' text (pod_pages.CARDLOG_PAGE / CARDSRC_PAGE, no painted heading); pitch 20 px (patch/relnotes.c RN_PITCH_CARD)
RN_LOCK_LINE_PX = 20   # the Custom Wallpaper instructions' text (pod_pages.LOCKINFO_PAGE, same asset otherwise); the painter's pitch for it is 27 px (patch/relnotes.c RN_PITCH_LOCK)


def build_relnotes_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title)
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'rn_listview')
    sv = lv.children[0]
    sv.set('name', 'rn_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, CLIENT_H - NAVBAR_H, [('name', 'rn_view')])
    styled(view, ('normal',), 'bg_color', '#000000')
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(nav_fade())
    root.children += style_labels((('label_head', RN_HEAD_PX, INK_RGB), ('label_line', RN_LOCK_LINE_PX if page.key == pod_pages.LOCKINFO_PAGE.key else RN_CARD_LINE_PX if page.key in (pod_pages.CARDLOG_PAGE.key, pod_pages.CARDSRC_PAGE.key) else RN_LINE_PX, RN_LINE_RGB)))
    return root


# The Lock Screen's Wallpaper picker (patch/lockscreen.c lkwp_*, docs/modules/lockscreen.md "Wallpaper picker"): the wallpaper grid of stock's systemset/screensaver_page, which stock builds in code inside its view_covers
# (0x4abe04: image_create at x 12 + 103 per column, y 0 then 143, 90 x 135, three to a row; cell builder 0x4abb3c: draw type 4 = scale_auto, clickable, name imgcover<i>, a 26 px child img_choice<i> at 4,4,
# cell 0 also the 24 px screensaver_defaulticon at 0,111), copied under our navbar. The widget names are stock's. Every cell starts hidden and insensitive; the payload shows the ones it has a picture for.
# Selected look: stock's picture_selected_style is a 2 px #FE7E40 border (the theme styles/screensaver_page.bin; unselected: none), here a 2 px border that is transparent until the payload sets border_color to the accent.
LW_COLS, LW_ROWS, LW_N = 3, 2, 6
LW_X0, LW_PITCH_X, LW_Y = 12, 103, (0, 143)
LW_CELL_W, LW_CELL_H = 90, 135
LW_MARK, LW_MARK_XY = 26, 4
LW_DEFAULT_ICON, LW_DEFAULT_ICON_XY = 24, (0, 111)
LW_VIEW_Y, LW_VIEW_H = NAVBAR_H, 400


def build_lockwall_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    covers = Widget('view', 0, LW_VIEW_Y, SCREEN_W, LW_VIEW_H, [('name', 'view_covers')])
    for i in range(LW_N):
        cell = hidden(Widget('image', LW_X0 + LW_PITCH_X * (i % LW_COLS), LW_Y[i // LW_COLS], LW_CELL_W, LW_CELL_H,
                             [('name', f'imgcover{i}'), ('draw_type', 'scale_auto'), ('clickable', 'true')]))
        styled(cell, ('normal', 'disable', 'focused'), 'border_width', '2')
        styled(cell, ('normal', 'disable', 'focused'), 'border_color', '#00000000')
        cell.children.append(Widget('image', LW_MARK_XY, LW_MARK_XY, LW_MARK, LW_MARK, [('name', f'img_choice{i}'), ('image', 'screensaver_unselect'), ('draw_type', 'default'), ('sensitive', 'false')]))
        if i == 0:
            cell.children.append(Widget('image', LW_DEFAULT_ICON_XY[0], LW_DEFAULT_ICON_XY[1], LW_DEFAULT_ICON, LW_DEFAULT_ICON,
                                        [('name', 'img_defaulticon'), ('image', 'screensaver_defaulticon'), ('draw_type', 'default'), ('sensitive', 'false')]))
        covers.children.append(cell)
    root.children.append(covers)
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
    if page.kind == 'pdcfg':   # the Pull-down page (patch/pulldown.c): the same rows for the twelve tiles, the eight stock ones shown by default
        sv.children += cfg_rows(sv.w, pod_pages.PULLDOWN_TILES, range(pod_pages.PULLDOWN_STOCK))
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
# (pod_dm_head) and the Recently Played shelf's, but the group caption role (pod_roles CAPTION_*): 18 px secondary grey, in the Settings pages' strip, its label box at x 14 so the text ink is at the rows' glyph ink (x 17; the Settings
# captions' ink sits on the glyph ink of their cards, x 24, box 21). Insensitive always and hidden in the asset (the payload shows it by visible alone): never a touch target, and no list_item (no press visual, no
# chevron or icon). The label is CAPTION_LABEL_H high, CAPTION_LABEL_Y down the strip.
import pod_settings as _ST
HDR_X, HDR_PX, HDR_RGB = 14, _ST.HDR_PX, SUB_RGB   # the Settings pages' caption (pod_settings.HDR_*; size and colour shared): the secondary grey, dimmer than its rows; label box x 14: the text ink starts 3 px right of the box (hscroll_label inset 2 + side bearing ~1), at x 17 = the left of the rows' glyph ink (the 24 px glyph at x 16, ink from 17), as the Settings captions sit on theirs
HDR_LABEL_Y, HDR_LABEL_H = CAPTION_LABEL_Y, CAPTION_LABEL_H


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
def cards_row(i, row, piece, last, icon=True):
    import pod_settings as ST
    from mod_icons import CARD_GLYPHS, card_name, CARD_CHEVRON, CARD_CHECK
    kind = pod_pages.row_kind(row)
    swatch = row.action == pod_pages.ACT_ACCENTSET   # the Accent picker's rows show the accent's round swatch where a glyph goes (never tinted: docs/modules/accent.md)
    has_icon = swatch or (icon and kind not in ('check', 'info', 'preset', 'preamp', 'band', 'lib', 'delete', 'plain', 'wvalue') and row.action not in (pod_pages.ACT_CCLIST, pod_pages.ACT_SFOLD, pod_pages.ACT_REGION, pod_pages.ACT_PCDIR, pod_pages.ACT_RGBROW, pod_pages.ACT_LEDFOLLOW, *pod_pages.ASSEP_ACTIONS, *pod_pages.GSSEP_ACTIONS, *pod_pages.NOGLYPH_ACTIONS, pod_pages.ACT_PEQ_PRESETS, pod_pages.ACT_PEQ_TENBAND))   # (the Cache counts, Unsupported Files, the Podcast Region row, LED Light's Theme and Follow Screen rows and the Presets count have no glyph, like the rows around them)
    h = ST.row_h(row)
    item = Widget('list_item', 0, 0, ST.LIST_W, h, [('name', f'pod_row{i}'), ('style', 'list_item_style')] + ([('sensitive', 'false')] if kind in ('info', 'preamp') and row.action != pod_pages.ACT_SFDEL else []))
    normal, down = ST.piece_images(piece, h != ST.ROW_H)
    for st in ('normal', 'over', 'pressed', 'focused', 'disable'):
        styled(item, (st,), 'bg_color', '#00000000')
        styled(item, (st,), 'bg_image', down if st == 'pressed' else normal)
        styled(item, (st,), 'bg_image_draw_type', 'default')
        styled(item, (st,), 'border_width', '0')
        styled(item, (st,), 'border_color', '#00000000')
    x, w = ST.label_box(kind, has_icon)
    curve = row.action in (pod_pages.ACT_PEQ_PICK, pod_pages.ACT_PEQ_PAUTO) and row.label   # the Equalizer page's 10-Band EQ row: a grey curve name before the check (the payload sets it; the preset rows have no label and no name)
    if curve: w = ST.curve_box()[0] - ST.VALUE_LABEL_GAP - x
    if has_icon:
        item.children.append(Widget('image', ST.ICON_X, ST.ICON_Y, ST.ICON_PX, ST.ICON_PX, [
            ('name', 'pod_swatch' if swatch else 'pod_icon'), ('image', f'pod_sw{row.arg}' if swatch else card_name(CARD_GLYPHS[row.label])), ('draw_type', 'icon'), ('sensitive', 'false')]))
    two_lines = kind in ('band', 'lib')   # the preset page's band row: the frequency and the gain on the first line, the type and Q (grey) under it; the Presets page's row: the name and a grey line
    ty, th, sy, sh = (ST.LIB_TITLE_Y, ST.LIB_TITLE_H, ST.LIB_SUB_Y, ST.LIB_SUB_H) if kind == 'lib' else (ST.BAND_TITLE_Y, ST.BAND_TITLE_H, ST.BAND_SUB_Y, ST.BAND_SUB_H)
    item.children.append(Widget('hscroll_label', x, ty if two_lines else 0, w, th if two_lines else h, [
        ('name', f'pod_label{i}'), ('style', 'srlabel_leftwhite21_style'), pod_i18n.text_prop(row.label) if row.label else ('text', ''),('only_parent_focus', 'true'), ('ellipses', 'true'), ('yoyo', 'true'), ('loop', 'true')]))
    if two_lines:
        for st in ('normal', 'disable', 'focused'): styled(item.children[-1], (st,), 'font_size', str(ST.BAND_TITLE_PX))
    if kind in ('preamp', 'band'): item.children[-1].set('sensitive', 'false')   # (a label takes no touch: the row does, or for the Preamp row nothing does)
    if kind == 'delete' or row.action in (pod_pages.ACT_SFDELALL, pod_pages.ACT_RESETALL):   # the destructive row: its label in the red of the Songs trash (PA_RED)
        for st in ('normal', 'disable', 'focused'): styled(item.children[-1], (st,), 'text_color', PS_SHEET_RED)
    if kind == 'lib':   # the Presets page's row: the grey line under the name, the chevron's room on its right
        sub = Widget('hscroll_label', x, sy, w, sh, [('name', f'pod_sub{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(sub, (st,), 'font_size', str(ST.BAND_SUB_PX))
            styled(sub, (st,), 'text_color', ST.GREY)
            styled(sub, (st,), 'text_align_h', 'left')
            styled(sub, (st,), 'text_align_v', 'middle')
        item.children.append(sub)
    if kind == 'band':   # the gain is a value as every value row's (ST.VALUE_PX grey, the full row high so that it is centred like the chevron, ends VALUE_GAP before it); the grey line stops before it
        gain = Widget('hscroll_label', ST.band_right() - ST.BAND_GAIN_W, 0, ST.BAND_GAIN_W, ST.ROW_H, [('name', f'pod_value{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        sx, sw = ST.band_sub_box()
        sub = Widget('hscroll_label', sx, sy, sw, sh, [('name', f'pod_sub{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            for wd, px, al in ((gain, ST.VALUE_PX, 'right'), (sub, ST.BAND_SUB_PX, 'left')):
                styled(wd, (st,), 'font_size', str(px))
                styled(wd, (st,), 'text_color', ST.GREY)
                styled(wd, (st,), 'text_align_h', al)
                styled(wd, (st,), 'text_align_v', 'middle')
        item.children += [gain, sub]
    if kind == 'preamp':   # a grey value, right aligned at the card's ink edge, no chevron: the row takes no touch
        val = Widget('hscroll_label', ST.band_right() - ST.PREAMP_W, 0, ST.PREAMP_W, ST.ROW_H, [('name', f'pod_value{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(val, (st,), 'font_size', str(ST.VALUE_PX))
            styled(val, (st,), 'text_color', ST.GREY)
            styled(val, (st,), 'text_align_h', 'right')
            styled(val, (st,), 'text_align_v', 'middle')
        item.children.append(val)
    if curve:
        vx, vw = ST.curve_box()
        val = Widget('hscroll_label', vx, 0, vw, ST.ROW_H, [('name', f'pod_value{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(val, (st,), 'font_size', str(ST.VALUE_PX))
            styled(val, (st,), 'text_color', ST.GREY)
            styled(val, (st,), 'text_align_h', 'right')
            styled(val, (st,), 'text_align_v', 'middle')
        item.children.append(val)
    if kind in ('link', 'value', 'wvalue', 'lib', 'band'):
        ax, ay, aw, ah = ST.accessory('chevron', h)
        item.children.append(Widget('image', ax, ay, aw, ah, [('name', 'pod_chevron'), ('image', CARD_CHEVRON[0]), ('draw_type', 'icon'), ('sensitive', 'false')]))
    if kind in ('value', 'wvalue'):
        vx, vw = ST.wvalue_box() if kind == 'wvalue' else ST.value_box()
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
            styled(val, (st,), 'font_size', str(ST.VALUE_PX if row.arg >= pod_pages.INFO_CC_ALBUMS else ST.INFO_PX))   # (the Cache page's values are the standard 18 px value size, About's the stock About's 16)
            styled(val, (st,), 'text_color', ST.GREY)
            styled(val, (st,), 'text_align_h', 'right')
            styled(val, (st,), 'text_align_v', 'middle')
        item.children.append(val)
    if kind == 'switch':
        ax, ay, aw, ah = ST.accessory('switch')
        item.children.append(Widget('image', ax, ay, aw, ah, [('name', f'pod_switch{i}'), ('image', 'sset_off'), ('draw_type', 'default'), ('sensitive', 'false')]))
    if kind in ('check', 'preset'):
        ax, ay, aw, ah = ST.accessory('check')
        item.children.append(hidden(Widget('image', ax, ay, aw, ah, [('name', f'pod_check{i}'), ('image', CARD_CHECK[0]), ('draw_type', 'icon')])))
    if not last:
        hair = Widget('view', x, h - 1, ST.CM + ST.CARD_W - x, 1, [('name', 'pod_hair'), ('sensitive', 'false')])
        for st in STATES: styled(hair, (st,), 'bg_color', ST.CARD_HAIR_RGB)
        item.children.append(hair)
    return item


GR_W, GR_H, GR_X0, GR_W0, GR_Y0, GR_H0, GR_DECADE = (OFFSETS[k] for k in ('GR_W', 'GR_H', 'GR_PX0', 'GR_PW', 'GR_PY0', 'GR_PH', 'GR_DECADE'))
GR_LABEL_PX, GR_LABEL_RGB = 15, CHEV_RGB   # every graph's labels (PEQ curve, 10-Band, Battery History): one chart-label grey
assert GR_H == _ST.GRAPH_H and GR_W == _ST.CARD_W and GR_W0 == 3 * GR_DECADE and GR_X0 + GR_W0 < GR_W and GR_Y0 + GR_H0 + 19 <= GR_H   # (the labels under the plot fit in the card)


def cards_graph():
    """The preset page's graph card (patch/peqpage.c): a transparent view, so that the bitmap the payload blits in its EVT_BEFORE_PAINT (the card, the grid, the curve) shows under its children, the
    labels: the scale at the left (the payload sets the top and bottom ones: +12 / -12, or +18, +24) and the frequencies under the plot. The labels never take a touch."""
    import math, pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.GRAPH_H, [('name', 'pod_graph'), ('sensitive', 'false')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    def lab(name, text, cx, cy, w, align):
        l = Widget('label', ST.CM + cx, cy - 9, w, 18, [('name', name), ('text', text), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(l, (st,), 'font_size', str(GR_LABEL_PX))
            styled(l, (st,), 'text_color', GR_LABEL_RGB)
            styled(l, (st,), 'text_align_h', align)
            styled(l, (st,), 'text_align_v', 'middle')
        return l
    mid = GR_Y0 + GR_H0 // 2
    v.children += [lab('pod_gr_top', pod_pages.GRAPH_TEXTS[0], 6, GR_Y0, 26, 'right'), lab('pod_gr_mid', pod_pages.GRAPH_TEXTS[1], 6, mid, 26, 'right'), lab('pod_gr_bot', pod_pages.GRAPH_TEXTS[2], 6, GR_Y0 + GR_H0, 26, 'right')]
    for (text, hz), name in zip(zip(pod_pages.GRAPH_TEXTS[3:6], (100, 1000, 10000)), ('pod_gr_f100', 'pod_gr_f1k', 'pod_gr_f10k')):
        cx = GR_X0 + round(GR_DECADE * math.log10(hz / 20))
        v.children.append(lab(name, text, cx - 20, GR_Y0 + GR_H0 + 10, 40, 'center'))
    v.children.append(lab('pod_gr_hz', pod_pages.GRAPH_TEXTS[6], GR_X0 + GR_W0 - 7, GR_Y0 + GR_H0 + 10, 22, 'left'))
    return v


TB = {k: OFFSETS[k] for k in ('TB_W', 'TB_H', 'TB_COLS', 'TB_COL_W', 'TB_X0', 'TB_Y0', 'TB_SPAN', 'TB_VAL_Y', 'TB_VAL_H', 'TB_FREQ_Y', 'TB_FREQ_H', 'TB_LABEL_W', 'TB_LABEL_PX')}
assert TB['TB_H'] == _ST.SLIDERS_H and TB['TB_W'] == _ST.CARD_W and TB['TB_COLS'] == len(pod_pages.SLIDER_TEXTS) == 10 and TB['TB_X0'] * 2 + TB['TB_COLS'] * TB['TB_COL_W'] == TB['TB_W']
assert TB['TB_FREQ_Y'] + TB['TB_FREQ_H'] <= TB['TB_H'] and TB['TB_VAL_Y'] + TB['TB_VAL_H'] < TB['TB_Y0']


def cards_sliders():
    """The 10-Band editor's slider card (patch/tenband.c): a sensitive transparent view (the payload blits the card, the tracks and the thumbs in its EVT_BEFORE_PAINT and takes its touch), and over it the ten
    value labels pod_sl_v<c> (empty in the asset; grey, white-on-the-pill black while dragged) and the ten frequency labels pod_sl_f<c> (31 .. 16k, grey, white while dragged), none sensitive."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.SLIDERS_H, [('name', 'pod_sliders')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    def lab(name, text, c, y, h):
        cx = ST.CM + TB['TB_X0'] + c * TB['TB_COL_W'] + TB['TB_COL_W'] // 2
        l = Widget('label', cx - TB['TB_LABEL_W'] // 2, y, TB['TB_LABEL_W'], h, [('name', name), ('text', text), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(l, (st,), 'font_size', str(TB['TB_LABEL_PX']))
            styled(l, (st,), 'text_color', GR_LABEL_RGB)
            styled(l, (st,), 'text_align_h', 'center')
            styled(l, (st,), 'text_align_v', 'middle')
        return l
    for c in range(TB['TB_COLS']):
        v.children.append(lab(f'pod_sl_v{c}', '', c, TB['TB_VAL_Y'], TB['TB_VAL_H']))
        v.children.append(lab(f'pod_sl_f{c}', pod_pages.SLIDER_TEXTS[c], c, TB['TB_FREQ_Y'], TB['TB_FREQ_H']))
    return v


BD = {k: OFFSETS[k] for k in ('BD_CARD_X', 'BD_SEG_ITEM_H', 'BD_SEG_Y', 'BD_SEG_W', 'BD_SEG_H', 'BD_HSL_W', 'BD_HSL_H', 'BD_ROWS', 'BD_ROW_H', 'BD_TRACK_X', 'BD_TRACK_W', 'BD_NAME_X', 'BD_NAME_W', 'BD_VAL_W', 'BD_LABEL_Y', 'BD_LABEL_H')}
assert BD['BD_SEG_ITEM_H'] == _ST.SEG_H and BD['BD_HSL_H'] == _ST.HSL_H == BD['BD_ROWS'] * BD['BD_ROW_H'] and BD['BD_HSL_W'] == BD['BD_SEG_W'] == _ST.CARD_W and BD['BD_CARD_X'] == _ST.CM
BD_LABEL_PX, BD_SEG_PX = 18, 14


BRIGHT_SUN, BRIGHT_SLIDER_W, BRIGHT_SLIDER_H, BRIGHT_SLIDER_Y = 20, 200, 50, 1   # the suns (drop_lighticon0 / 1), the slider's width and height (stock's, dialog/dropdown_dialog slider_backlight) and its y in a ROW_H card


def bright_control(lo, slider, hi, dx):
    """The brightness control's one look, shared by the Display page's card (cards_brightness, dx = ST.CM) and the pull-down's card (tools/mod_pulldown.py, dx = 0; its widgets are stock's, kept by name):
    the widgets placed in a card ST.CARD_W x ST.ROW_H whose left edge is at dx (small sun in the glyph column, the slider from the label column, the large sun at the right padding), the slider's 6 px track
    and fill (drop_bg, drop_fg) under our white capsule thumb (pod_sl_thumb). Name, range, value and handlers are the caller's."""
    import pod_settings as ST
    y = (ST.ROW_H - BRIGHT_SUN) // 2
    lo.x, lo.y, hi.x, hi.y = dx + ST.PAD, y, dx + ST.CARD_W - ST.PAD - BRIGHT_SUN, y
    slider.x, slider.y, slider.w, slider.h = dx + ST.TEXT_X - ST.CM, BRIGHT_SLIDER_Y, BRIGHT_SLIDER_W, BRIGHT_SLIDER_H
    slider_look(slider)


def slider_look(slider):
    """The slider of the Display page's brightness card, kept by every slider card that follows it (the loudness pages, the Crossfade page): the 6 px track and fill under the white capsule thumb."""
    for k, val in (('slide_with_bar', 'true'), ('bar_size', '6'), ('dragger_size', '50'), ('dragger_adapt_to_icon', 'true')): slider.set(k, val)
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'):
        styled(slider, (st,), 'bg_color', '#00000000'); styled(slider, (st,), 'fg_color', '#00000000')
        styled(slider, (st,), 'icon', 'pod_sl_thumb'); styled(slider, (st,), 'bg_image', 'drop_bg'); styled(slider, (st,), 'fg_image', 'drop_fg')
    styled(slider, ('normal',), 'round_radius', '6')


def cards_brightness():
    """The Display page's brightness card (patch/display.c): one card of a row's height with the pull-down's brightness control in it, the small sun in the glyph column, the slider from the label column and the
    large sun at the card's right padding. The slider is the iOS Settings kind: the pull-down slider's 6 px track and fill (drop_bg, drop_fg: the fill takes the accent) under a white capsule thumb of our own
    (pod_sl_thumb, tools/mod_icons.py slider_thumb). It has the name and range of stock's systemset/brightness_page slider (slider_brightness, 0 .. 100), because stock's two handlers are
    bound to it and look it up by name; label_brightness is the percentage they also write: hidden and insensitive, it is there because stock's refresh does nothing without it."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.ROW_H, [('name', 'pod_bright')])
    for st in STATES:
        styled(v, (st,), 'bg_color', '#00000000')
        styled(v, (st,), 'bg_image', ST.piece_images('single')[0])
        styled(v, (st,), 'bg_image_draw_type', 'default')
    lo = Widget('image', 0, 0, BRIGHT_SUN, BRIGHT_SUN, [('name', 'pod_bright_lo'), ('image', 'drop_lighticon0'), ('draw_type', 'default'), ('sensitive', 'false')])
    s = Widget('slider', 0, 0, BRIGHT_SLIDER_W, BRIGHT_SLIDER_H, [('name', 'slider_brightness'), ('max', '100'), ('step', '1'), ('value', '0')])
    hi = Widget('image', 0, 0, BRIGHT_SUN, BRIGHT_SUN, [('name', 'pod_bright_hi'), ('image', 'drop_lighticon1'), ('draw_type', 'default'), ('sensitive', 'false')])
    bright_control(lo, s, hi, ST.CM)
    v.children += [lo, s, hi]
    lab = Widget('label', 0, 0, 1, 1, [('name', 'label_brightness'), ('text', ''), ('visible', 'false'), ('sensitive', 'false')])
    for st in STATES: styled(lab, (st,), 'text_color', '#FFFFFF')   # (never shown; the contrast scan reads every label)
    v.children.append(lab)
    return v


XF_LABEL_Y, XF_LABEL_H, XF_LABEL_PX, XF_END_PX = 12, 22, 17, 16   # the Crossfade card: the duration text's top, height and size; the "1 s" / "12 s" ends' size
XF_SLIDER_X, XF_SLIDER_Y, XF_END_W, XF_DOTS_Y = 54, 33, 30, 73   # the slider's x in the page (its width BRIGHT_SLIDER_W, 50 high: centre 58), the end labels' width, the dots' top


def cards_xfade():
    """The Crossfade page's duration card (patch/xfadeset.c xfade_show / xfade_opened): the item is the card (ST.XFADE_CARD_H, a top and a bottom piece overlapping) and the gap under it. In it the duration as text (pod_xf_val,
    grey 17 px: "5 seconds", written as the slider moves), under it "1 s" (pod_xf_lo), the slider (pod_xf_slider, 1 .. 12, step 1: the Display page's look, slider_look) and "12 s" (pod_xf_hi), and twelve small dots under the
    track, one per second (the image pod_xf_dots, tools/mod_icons.py xf_dots: the thumb's travel is the dots' span)."""
    import pod_settings as ST, mod_icons
    v = Widget('view', 0, 0, ST.LIST_W, ST.XFADE_H, [('name', 'pod_xfcard')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    for k, (piece, y) in enumerate((('top', 0), ('bot', ST.XFADE_CARD_H - ST.ROW_H))):
        p = Widget('view', 0, y, ST.LIST_W, ST.ROW_H, [('name', f'pod_xfcard{k}'), ('sensitive', 'false')])
        for st in STATES:
            styled(p, (st,), 'bg_color', '#00000000')
            styled(p, (st,), 'bg_image', ST.piece_images(piece)[0])
            styled(p, (st,), 'bg_image_draw_type', 'default')
        v.children.append(p)

    def label(name, x, y, w, h, text, px, rgb, align):
        lab = Widget('label', x, y, w, h, [('name', name), pod_i18n.text_prop(text) if text else ('text', ''), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px)); styled(lab, (st,), 'text_color', rgb)
            styled(lab, (st,), 'text_align_h', align); styled(lab, (st,), 'text_align_v', 'middle')
        return lab
    x0, w = ST.CM + ST.PAD, ST.CARD_W - 2 * ST.PAD
    v.children.append(label('pod_xf_val', x0, XF_LABEL_Y, w, XF_LABEL_H, '', XF_LABEL_PX, ST.GREY, 'left'))
    cy = XF_SLIDER_Y + BRIGHT_SLIDER_H // 2
    v.children.append(label('pod_xf_lo', x0, cy - 12, XF_END_W, 24, '1 s', XF_END_PX, '#FFFFFF', 'left'))
    v.children.append(label('pod_xf_hi', ST.CM + ST.CARD_W - ST.PAD - XF_END_W - 4, cy - 12, XF_END_W + 4, 24, '12 s', XF_END_PX, '#FFFFFF', 'right'))
    sl = Widget('slider', XF_SLIDER_X, XF_SLIDER_Y, BRIGHT_SLIDER_W, BRIGHT_SLIDER_H, [('name', 'pod_xf_slider'), ('min', '1'), ('max', '12'), ('step', '1'), ('value', '5')])
    slider_look(sl)
    v.children.append(sl)
    v.children.append(Widget('image', XF_SLIDER_X, XF_DOTS_Y, BRIGHT_SLIDER_W, mod_icons.XF_DOTS[2], [('name', 'pod_xf_dots'), ('image', mod_icons.XF_DOTS[0]), ('draw_type', 'default'), ('sensitive', 'false')]))
    return v


VOL_NAMES = {'maxvol': ('label_vol', 'vol_slider', 100), 'bootvol': ('label_vol', 'vol_slider', 100), 'balance': ('label_balance', 'slider_balance', 20)}   # stock's widget names of the three loudness pages (label, slider) and the slider's top
VOL_BTN_W, VOL_VALUE_PX, VOL_BTN_PX = 46, 22, 24   # the - and + buttons' width (a touch target; the card is 300 wide), the value's text size, the buttons' text size
VOL_DISC, VOL_DISC_FILL, VOL_GAP = 36, '#FFFFFF14', 8   # the round disc drawn under each button's text (its diameter, 8 % white) and the space between a button and the slider's end, so the bar's ends stand 13 px clear of the discs
VOL_BTN_TEXTS = {'maxvol': ('−', '+'), 'bootvol': ('−', '+'), 'balance': ('L', 'R')}   # the buttons' texts: a step down or up; Channel Balance's step toward the left or the right (shown as they are in every language)


def cards_volcard(card):
    """A card of the Playback Settings loudness pages (patch/playset.c ps_vol_opened), one row high with the single piece, holding stock's own widgets by stock's names because stock's handlers and refresh are bound to
    them and look them up by name: part 'value' the label (label_vol / label_balance, white, centred: stock's refresh writes "VOL: 80" or "L3" into it; on Max Volume and Default Volume it is hidden and insensitive, and pod_vsnum, the same look, shows the number alone), part 'slider' the buttons btn_dec / btn_add (stock's click
    handlers) either side of the slider (vol_slider / slider_balance, 0 .. 100 or 0 .. 20: stock's value-changing handler), the Display page's slider look (pod_sl_thumb, drop_bg, drop_fg)."""
    import pod_settings as ST
    label_name, slider_name, top = VOL_NAMES[card.kind]
    v = Widget('view', 0, 0, ST.LIST_W, ST.ROW_H, [('name', 'pod_vsval' if card.part == 'value' else 'pod_vsctl')])
    for st in STATES:
        styled(v, (st,), 'bg_color', '#00000000')
        styled(v, (st,), 'bg_image', ST.piece_images('single')[0])
        styled(v, (st,), 'bg_image_draw_type', 'default')
    if card.part == 'value':
        hidden = card.kind != 'balance'   # Max Volume, Default Volume: stock's label (it writes "VOL: 80") is kept for stock's refresh but hidden; ours (pod_vsnum) shows the number
        for name, props in ((label_name, [('visible', 'false')] if hidden else []),) + ((('pod_vsnum', []),) if hidden else ()):
            lab = Widget('label', ST.CM, 0, ST.CARD_W, ST.ROW_H, [('name', name), ('text', ''), ('sensitive', 'false')] + props)
            for st in ('normal', 'disable', 'focused'):
                styled(lab, (st,), 'font_size', str(VOL_VALUE_PX))
                styled(lab, (st,), 'text_color', '#FFFFFF')
                styled(lab, (st,), 'text_align_h', 'center')
                styled(lab, (st,), 'text_align_v', 'middle')
            v.children.append(lab)
        return v
    left, right = VOL_BTN_TEXTS[card.kind]
    sx = ST.CM + 4 + VOL_BTN_W + VOL_GAP
    for name, x, text in (('btn_dec', ST.CM + 4, left), ('btn_add', ST.CM + ST.CARD_W - 4 - VOL_BTN_W, right)):
        disc = Widget('view', x + (VOL_BTN_W - VOL_DISC) // 2, (ST.ROW_H - VOL_DISC) // 2, VOL_DISC, VOL_DISC, [('name', name.replace('btn', 'pod_vsdisc')), ('sensitive', 'false')])   # the faint disc under the button's text; the button over it stays the touch target
        for st in STATES:
            styled(disc, (st,), 'bg_color', VOL_DISC_FILL); styled(disc, (st,), 'round_radius', str(VOL_DISC // 2))
            styled(disc, (st,), 'border_width', '0'); styled(disc, (st,), 'border_color', '#00000000')
        v.children.append(disc)
        b = Widget('button', x, 3, VOL_BTN_W, ST.ROW_H - 6, [('name', name), ('text', text)])
        for st in STATES:
            styled(b, (st,), 'bg_color', '#00000000')
            styled(b, (st,), 'border_width', '0'); styled(b, (st,), 'border_color', '#00000000')   # the theme's default button style draws a square border when the widget's own style names none
            styled(b, (st,), 'text_color', '#8C8C8C' if st == 'pressed' else '#FFFFFF')
            styled(b, (st,), 'font_size', str(VOL_BTN_PX))
            styled(b, (st,), 'text_align_h', 'center')
            styled(b, (st,), 'text_align_v', 'middle')
        v.children.append(b)
    s = Widget('slider', sx, 1, ST.CARD_W - 8 - 2 * (VOL_BTN_W + VOL_GAP), 50, [('name', slider_name), ('max', str(top)), ('step', '1'), ('slide_with_bar', 'true'), ('bar_size', '6'), ('dragger_size', '50'), ('dragger_adapt_to_icon', 'true'), ('value', '0')])
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'):
        styled(s, (st,), 'bg_color', '#00000000'); styled(s, (st,), 'fg_color', '#00000000')
        styled(s, (st,), 'icon', 'pod_sl_thumb'); styled(s, (st,), 'bg_image', 'drop_bg'); styled(s, (st,), 'fg_image', 'drop_fg')
    styled(s, ('normal',), 'round_radius', '6')
    v.children.append(s)
    return v


VOLUME_NUM_PX, VOLUME_INFO_PX = 60, 16   # the Volume page's number (the bold face) and its grey line
VOLUME_INNER_X, VOLUME_INNER_W = 22, 276   # the card's inner width: the 52 px capsule bar spans it (the card is x 10 .. 310)
VOLUME_NUM_Y, VOLUME_NUM_H, VOLUME_INFO_Y, VOLUME_INFO_H, VOLUME_BAR_Y = 12, 66, 78, 22, 104   # item rows: the number, its info line, the bar (52 high, 12 px above the card's bottom: the card's side padding)
VOLUME_BTN_CY = 45   # the - / + buttons' centre: the number's


def cards_volume():
    """The Volume page's card (patch/volume.c): a top, a mid and a bottom card piece stacked (insensitive), and over them stock's vol_label (hidden), our number pod_volnum (60 px, the bold face, left) and grey line pod_volinfo,
    the round - / + buttons (btn_dec, btn_add: VolCard's disc and transparent button) at the right of the number's row, and the stock slider vol_slider in the place of the bar (invisible: it keeps the touch and
    the drag), under pod_volbar, the insensitive view the payload paints the capsule in. Stock's handlers are bound to the buttons and the slider, stock's refresh writes vol_label and sets the slider; the payload writes the
    number and the line and repaints the bar."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.VOLUME_ITEM_H, [('name', 'pod_volume')])   # (the card is VOLUME_CARD_H high; the gap under it is part of the item)
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    for k, (piece, y) in enumerate((('top', 0), ('mid', ST.ROW_H), ('bot', ST.VOLUME_CARD_H - ST.ROW_H), ('mid', ST.VOLUME_CARD_H - 2 * ST.ROW_H))):   # (the second mid piece fills the card's extra height between the first and the bottom)
        p = Widget('view', 0, y, ST.LIST_W, ST.ROW_H, [('name', f'pod_volcard{k}'), ('sensitive', 'false')])
        for st in STATES:
            styled(p, (st,), 'bg_color', '#00000000')
            styled(p, (st,), 'bg_image', ST.piece_images(piece)[0])
            styled(p, (st,), 'bg_image_draw_type', 'default')
        v.children.append(p)

    def label(name, y, h, px, rgb, text='', face=None, extra=()):
        lab = Widget('label', VOLUME_INNER_X, y, 150 if name == 'pod_volnum' else VOLUME_INNER_W, h, [('name', name), ('text', text), ('sensitive', 'false')] + list(extra))
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(px)); styled(lab, (st,), 'text_color', rgb)
            styled(lab, (st,), 'text_align_h', 'left'); styled(lab, (st,), 'text_align_v', 'middle')
            if face: styled(lab, (st,), 'font_name', face)
        return lab
    v.children.append(label('vol_label', VOLUME_NUM_Y, 24, VOL_VALUE_PX, INK_RGB, extra=[('visible', 'false')]))   # stock's: its refresh writes "VOL: 42" here, nobody sees it
    v.children.append(label('pod_volnum', VOLUME_NUM_Y, VOLUME_NUM_H, VOLUME_NUM_PX, INK_RGB, face=ST.BIG_FACE))
    v.children.append(label('pod_volinfo', VOLUME_INFO_Y, VOLUME_INFO_H, VOLUME_INFO_PX, ST.GREY))
    add_x = VOLUME_INNER_X + VOLUME_INNER_W + (VOL_BTN_W - VOL_DISC) // 2 - VOL_BTN_W
    for name, x, text in (('btn_dec', add_x - VOL_BTN_W - 4, '−'), ('btn_add', add_x, '+')):
        disc = Widget('view', x + (VOL_BTN_W - VOL_DISC) // 2, VOLUME_BTN_CY - VOL_DISC // 2, VOL_DISC, VOL_DISC, [('name', name.replace('btn', 'pod_vsdisc')), ('sensitive', 'false')])
        for st in STATES:
            styled(disc, (st,), 'bg_color', VOL_DISC_FILL); styled(disc, (st,), 'round_radius', str(VOL_DISC // 2))
            styled(disc, (st,), 'border_width', '0'); styled(disc, (st,), 'border_color', '#00000000')
        v.children.append(disc)
        b = Widget('button', x, VOLUME_BTN_CY - (ST.ROW_H - 6) // 2, VOL_BTN_W, ST.ROW_H - 6, [('name', name), ('text', text)])
        for st in STATES:
            styled(b, (st,), 'bg_color', '#00000000')
            styled(b, (st,), 'border_width', '0'); styled(b, (st,), 'border_color', '#00000000')
            styled(b, (st,), 'text_color', '#8C8C8C' if st == 'pressed' else '#FFFFFF')
            styled(b, (st,), 'font_size', str(VOL_BTN_PX))
            styled(b, (st,), 'text_align_h', 'center'); styled(b, (st,), 'text_align_v', 'middle')
        v.children.append(b)
    s = Widget('slider', VOLUME_INNER_X, VOLUME_BAR_Y, VOLUME_INNER_W, ST.ROW_H, [('name', 'vol_slider'), ('max', '100'), ('step', '1'), ('slide_with_bar', 'true'), ('bar_size', '6'), ('dragger_size', '2'), ('dragger_adapt_to_icon', 'false'), ('value', '0'), ('visible', 'false')])   # drawn by nobody (hit testing ignores visible: the touch and the drag stay stock's); the bar over it is pod_volbar
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'):
        styled(s, (st,), 'bg_color', '#00000000'); styled(s, (st,), 'fg_color', '#00000000')
    v.children.append(s)
    bar = Widget('view', VOLUME_INNER_X, VOLUME_BAR_Y, VOLUME_INNER_W, ST.ROW_H, [('name', 'pod_volbar'), ('sensitive', 'false')])   # the capsule: the payload paints it in its EVT_BEFORE_PAINT (patch/volume.c vp_paint)
    for st in STATES: styled(bar, (st,), 'bg_color', '#00000000')
    v.children.append(bar)
    return v


def cards_cover():
    """The Cover page's card (patch/plcpage.c): a sensitive transparent view the payload paints (the six thumbnails and the ring in its EVT_BEFORE_PAINT) and takes the touch of, and under each thumbnail its name, pod_covl<k> (14 px centred, insensitive;
    the payload makes the chosen one white and the others grey)."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.COVER_ITEM_H, [('name', 'pod_cover')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    for k, key in enumerate(pod_pages.COVER_STYLES):
        lab = Widget('label', ST.CM + k % 3 * ST.COVER_PITCH_X, k // 3 * ST.COVER_PITCH_Y + ST.COVER_LAB_Y, ST.COVER_T, ST.COVER_LAB_H, [('name', f'pod_covl{k}'), pod_i18n.text_prop(key), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(lab, (st,), 'font_size', str(ST.COVER_PX)); styled(lab, (st,), 'text_color', ST.GREY)
            styled(lab, (st,), 'text_align_h', 'center'); styled(lab, (st,), 'text_align_v', 'middle')
            styled(lab, (st,), 'margin_left', '0'); styled(lab, (st,), 'margin_right', '0')
        v.children.append(lab)
    v.children += style_labels((('pod_covname', GRID_ALBUM_PX - 4, INK_RGB),))   # the text style of the name drawn on a thumbnail (grid_plc_name)
    return v


def cards_segment():
    """The band page's Peak / Low shelf / High shelf control (patch/peqband.c): a sensitive transparent view (the payload blits the container and the selected pill in its EVT_BEFORE_PAINT and takes the touch) with the three labels pod_seg_l<k> over it
    (white; the selected one is black on its pill, set by the payload), none sensitive."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.SEG_H, [('name', 'pod_seg')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    w = BD['BD_SEG_W'] // 3
    for k, key in enumerate(pod_pages.BAND_SEG_KEYS):
        l = Widget('label', ST.CM + k * w, BD['BD_SEG_Y'], w, BD['BD_SEG_H'], [('name', f'pod_seg_l{k}'), pod_i18n.text_prop(key), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'):
            styled(l, (st,), 'font_size', str(BD_SEG_PX))
            styled(l, (st,), 'text_color', INK_RGB)
            styled(l, (st,), 'text_align_h', 'center')
            styled(l, (st,), 'text_align_v', 'middle')
        v.children.append(l)
    return v


def cards_hsliders():
    """The band page's card of three horizontal sliders (patch/peqband.c): a sensitive transparent view (the payload blits the card with its tracks, the fills and the thumbs in its EVT_BEFORE_PAINT and takes the touch) with, in each BD_ROW_H row, the name
    pod_hs_n<r> (Frequency, Gain, Q: 18 px white) and the value pod_hs_v<r> (18 px grey, right aligned; written by the payload), none sensitive."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.HSL_H, [('name', 'pod_hsl')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    for r, key in enumerate(pod_pages.BAND_ROW_KEYS):
        for name, x, w, text, rgb, al in ((f'pod_hs_n{r}', BD['BD_NAME_X'], BD['BD_NAME_W'], pod_i18n.text_prop(key), INK_RGB, 'left'),
                                          (f'pod_hs_v{r}', BD['BD_TRACK_X'] + BD['BD_TRACK_W'] - BD['BD_VAL_W'], BD['BD_VAL_W'], ('text', ''), ST.GREY, 'right')):
            l = Widget('label', ST.CM + x, r * BD['BD_ROW_H'] + BD['BD_LABEL_Y'], w, BD['BD_LABEL_H'], [('name', name), text, ('sensitive', 'false')])
            for st in ('normal', 'disable', 'focused'):
                styled(l, (st,), 'font_size', str(BD_LABEL_PX))
                styled(l, (st,), 'text_color', rgb)
                styled(l, (st,), 'text_align_h', al)
                styled(l, (st,), 'text_align_v', 'middle')
            v.children.append(l)
    return v


def cards_spacer(name, h):
    import pod_settings as ST
    """An insensitive black view h high: the layouter gives it the list's width and its place."""
    v = Widget('view', 0, 0, ST.LIST_W, h, [('name', name), ('sensitive', 'false')])
    for st in STATES: styled(v, (st,), 'bg_color', '#000000')
    return v


def cards_region():
    """The box between the editor's graph card and slider card with the region line in it: an 18 px grey label centred in REGION_H (empty; the payload writes the dragged band's region and clears it at the release), from the notes' text x."""
    import pod_settings as ST
    v = cards_spacer('pod_regionbox', ST.REGION_H)
    lab = Widget('label', ST.HDR_X + 2, 0, ST.HDR_W - 4, ST.REGION_H, [('name', 'pod_region'), ('text', ''), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(ST.HDR_PX))
        styled(lab, (st,), 'text_color', ST.GREY)
        styled(lab, (st,), 'text_align_h', 'left')
        styled(lab, (st,), 'text_align_v', 'middle')
    v.children.append(lab)
    return v


HC = {k: OFFSETS[k] for k in ('BHC_LIST_W', 'BHC_W', 'BHC_X', 'BHC_R', 'BHC_PX0', 'BHL_H', 'BHL_CARD', 'BHL_PY0', 'BHL_PH', 'BHL_PITCH', 'BHL_BAR', 'BHA_H', 'BHA_CARD', 'BHA_PY0', 'BHA_PH', 'BHA_PITCH', 'BHA_BAR',
                                  'BHA_LEGEND_Y', 'BHC_AXIS_X', 'BHC_AXIS_W', 'BHC_TICK_W', 'BHL_TICK_Y', 'BHA_TICK_Y', 'BHS_H', 'BHS_CARD', 'BHS_PAD', 'BHS_CAP_Y', 'BHS_DUR_Y', 'BHS_LEFT_Y', 'BHS_BAR_Y', 'BHS_BAR_H', 'BHS_ROW0_Y', 'BHS_ROW_H', 'BHS_MARK_X', 'BHS_MARK_SIZE', 'BHS_MARK_R', 'BHS_NAME_X', 'BHS_MARK_CY', 'BHS_SUB_CY', 'BHS_PCT_CY')}
assert (HC['BHL_H'], HC['BHA_H'], HC['BHS_H'], HC['BHS_CARD']) == (_ST.HIST_LEVEL_H, _ST.HIST_ACT_H, _ST.HIST_SUMMARY_H, _ST.HIST_SUMMARY_CARD) and HC['BHC_W'] == _ST.CARD_W and HC['BHC_X'] == _ST.CM and HC['BHC_LIST_W'] == _ST.LIST_W
assert HC['BHS_MARK_R'] == _ST.STAT_MARK_R and HC['BHS_MARK_SIZE'] == _ST.STAT_MARK   # one legend mark: the charts' and the card's rows'
assert HC['BHC_PX0'] + 48 * HC['BHL_PITCH'] <= HC['BHC_AXIS_X'] and HC['BHC_PX0'] + 24 * HC['BHA_PITCH'] <= HC['BHC_AXIS_X'] and HC['BHC_AXIS_X'] + HC['BHC_AXIS_W'] <= HC['BHC_W']
HIST_LABEL_PX, HIST_LEGEND_PX, HIST_DUR_PX = 13, 14, 28   # the card's other sizes are the list rows': ST.NOTE_PX caption, ST.VALUE_PX percent left, ST.STAT_TITLE_PX names, ST.STAT_SUB_PX + 1 durations and ST.STAT_PX percents
HIST_NAME_W, HIST_PCT_W = 170, 60   # a row's name and duration boxes (they end 68 px short of the card's right padding) and the percent's box (right aligned, ink at the padding)
HIST_AXIS_TEXTS = {'level': pod_pages.HIST_AXIS}   # the activity chart's axis ("60 min", "30 min", "0") is the payload's: it needs the language's "min"
HIST_LEGEND = ('Screen On', 'Playing, Screen Off')   # the activity chart's legend labels
HIST_KINDS = ('Screen On', 'Playing, Screen Off', 'Standby')   # the Since Last Charge card's three rows
HIST_LEG_X = ((30, 90), (140, 150))                  # their boxes (x, w) in the card; the swatches are 10 px squares at x 14 and 124 (patch/bhpage.c)


def _hist_label(name, x, cy, w, px, align, text=None, rgb=None, h=18):
    l = Widget('label', x, cy - h // 2, w, h, [('name', name), text if text is not None else ('text', ''), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(l, (st,), 'font_size', str(px))
        styled(l, (st,), 'text_color', rgb or GR_LABEL_RGB)
        styled(l, (st,), 'text_align_h', align)
        styled(l, (st,), 'text_align_v', 'middle')
    return l


def cards_hist(chart, n):
    """A Battery History chart (patch/bhpage.c): a transparent insensitive view whose before-paint blit draws the card, the gridlines and the bars; over it the axis labels pod_h<k>_a<0..2> at the right (the level chart's are
    fixed, the activity's are written by the payload), four hour labels pod_h<k>_t<0..3> (empty; the payload writes and places them by the local time zone) and, in the activity chart, the legend labels pod_h<k>_l<0..1>."""
    import pod_settings as ST
    lv = chart.kind == 'level'
    k = 'l' if lv else 'a'
    v = Widget('view', 0, 0, ST.LIST_W, HC['BHL_H'] if lv else HC['BHA_H'], [('name', f'pod_hist{n}'), ('sensitive', 'false')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    py0, ph = (HC['BHL_PY0'], HC['BHL_PH']) if lv else (HC['BHA_PY0'], HC['BHA_PH'])
    for j, y in enumerate((py0, py0 + ph // 2, py0 + ph)):
        v.children.append(_hist_label(f'pod_h{k}_a{j}', ST.CM + HC['BHC_AXIS_X'], y, HC['BHC_AXIS_W'], HIST_LABEL_PX, 'left', ('text', HIST_AXIS_TEXTS['level'][j]) if lv else None))
    for j in range(4):
        v.children.append(_hist_label(f'pod_h{k}_t{j}', ST.CM, HC['BHL_TICK_Y'] if lv else HC['BHA_TICK_Y'], HC['BHC_TICK_W'], HIST_LABEL_PX, 'center'))
    if not lv:
        for j, ((x, w), text) in enumerate(zip(HIST_LEG_X, HIST_LEGEND)):
            v.children.append(_hist_label(f'pod_h{k}_l{j}', ST.CM + x, HC['BHA_LEGEND_Y'], w, HIST_LEGEND_PX, 'left', pod_i18n.text_prop(text), ST.GREY))
    return v


def cards_summary(n):
    """The Battery History Since Last Charge card (patch/bhpage.c): a transparent insensitive view whose before-paint blit draws the card, the stacked bar, the row marks and hairlines; over it the grey caption pod_hs_cap (when the charger was removed),
    the bold total pod_hs_dur, the grey percent pod_hs_left (right aligned), and per row k the name pod_hs_n<k> (set in the asset), the grey duration pod_hs_d<k> under it and the bold white estimated percent pod_hs_p<k> at the right. The payload writes the texts."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, HC['BHS_H'], [('name', f'pod_hist{n}'), ('sensitive', 'false')])
    for st in STATES: styled(v, (st,), 'bg_color', '#00000000')
    x0, x1 = ST.CM + HC['BHS_PAD'], ST.CM + HC['BHC_W'] - HC['BHS_PAD']
    v.children.append(_hist_label('pod_hs_cap', x0, HC['BHS_CAP_Y'], x1 - x0, ST.NOTE_PX, 'left', None, ST.GREY, h=22))
    v.children.append(_hist_label('pod_hs_dur', x0, HC['BHS_DUR_Y'], 190, HIST_DUR_PX, 'left', None, INK_RGB, h=36))
    v.children.append(_hist_label('pod_hs_left', x1 - 100, HC['BHS_LEFT_Y'], 100, ST.VALUE_PX, 'right', None, ST.GREY, h=24))
    for k, text in enumerate(HIST_KINDS):
        top = HC['BHS_ROW0_Y'] + HC['BHS_ROW_H'] * k
        v.children.append(_hist_label(f'pod_hs_n{k}', ST.CM + HC['BHS_NAME_X'], top + HC['BHS_MARK_CY'], HIST_NAME_W, ST.STAT_TITLE_PX, 'left', pod_i18n.text_prop(text), INK_RGB, h=24))
        v.children.append(_hist_label(f'pod_hs_d{k}', ST.CM + HC['BHS_NAME_X'], top + HC['BHS_SUB_CY'], HIST_NAME_W, ST.STAT_SUB_PX + 1, 'left', None, ST.GREY, h=20))
        v.children.append(_hist_label(f'pod_hs_p{k}', x1 - HIST_PCT_W, top + HC['BHS_PCT_CY'], HIST_PCT_W, ST.STAT_PX, 'right', None, INK_RGB, h=24))
    return v


def cards_text(name, y, h, text, px, item_h, wrap=False):
    """A header or a note: an insensitive view item_h high holding the grey label (text from HDR_X, which the layouter does not move: it is the child's).
    wrap: a plain label (the payload turns its line wrap on: patch/peq_ui.c), several lines, the text from the top."""
    import pod_settings as ST
    v = cards_spacer(name, item_h)
    # (a plain label does not inset its text as the hscroll_label does: 2 px each side)
    if wrap: lab = Widget('label', ST.HDR_X + 2, y, ST.HDR_W - 4, h, [('name', name + '_t'), pod_i18n.text_prop(text), ('sensitive', 'false')])
    else: lab = Widget('hscroll_label', ST.HDR_X, y, ST.HDR_W, h, [('name', name + '_t'), pod_i18n.text_prop(text), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_color', ST.GREY)
        styled(lab, (st,), 'text_align_h', 'left')
        styled(lab, (st,), 'text_align_v', 'top' if wrap else 'middle')
    v.children.append(lab)
    return v


def _centred_label(name, x, y, w, h, prop, px, rgb, valign='middle', face=None):
    """An insensitive label with a centred text of its own (prop: the text property)."""
    lab = Widget('label', x, y, w, h, [('name', name), prop, ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_color', rgb)
        styled(lab, (st,), 'text_align_h', 'center')
        styled(lab, (st,), 'text_align_v', valign)
        if face: styled(lab, (st,), 'font_name', face)
    return lab


def cards_hero(hero, n_note):
    """A Hero (tools/pod_pages.py): the glyph tile centred on the page (a RAISED_RGB rounded square, the white glyph image pod_hero_<glyph> in it), the 22 px title under it and the grey wrapping description (pod_note<n>_t: a
    note by its number, so that the wrap bit of Page.wrap_notes is the page's), all centred on the card column (x CM .. CM + CARD_W)."""
    import pod_settings as ST
    v = cards_spacer('pod_hero', ST.hero_h(hero))
    tile = Widget('view', ST.CM + (ST.CARD_W - ST.HERO_TILE) // 2, ST.HERO_TILE_Y, ST.HERO_TILE, ST.HERO_TILE, [('name', 'pod_hero_tile'), ('sensitive', 'false')])
    for st in STATES:
        styled(tile, (st,), 'bg_color', RAISED_RGB)
        styled(tile, (st,), 'round_radius', str(ST.HERO_TILE_R))
        styled(tile, (st,), 'border_width', '0')
    g = (ST.HERO_TILE - ST.HERO_GLYPH) // 2
    tile.children.append(Widget('image', g, g, ST.HERO_GLYPH, ST.HERO_GLYPH, [('name', 'pod_hero_icon'), ('image', 'pod_hero_' + hero.glyph.replace('-', '_')), ('draw_type', 'default'), ('sensitive', 'false')]))
    v.children.append(tile)
    v.children.append(_centred_label('pod_hero_title', ST.CM, ST.HERO_TITLE_Y, ST.CARD_W, ST.HERO_TITLE_H, pod_i18n.text_prop(hero.title), ST.HERO_TITLE_PX, INK_RGB))
    v.children.append(_centred_label(f'pod_note{n_note}_t', ST.CM + ST.CENTRE_INSET, ST.HERO_DESC_Y, ST.CARD_W - 2 * ST.CENTRE_INSET, ST.hero_desc_h(hero.lines), pod_i18n.text_prop(hero.text), ST.HERO_DESC_PX, ST.GREY, 'top'))
    return v


def cards_bigcard(n):
    """A BigCard: one tall single card piece with a large centred label pod_big<n>_t (empty: the payload writes it as the page opens) in the bold face."""
    import pod_settings as ST
    v = cards_spacer(f'pod_big{n}', ST.BIG_H)
    card = Widget('view', 0, 0, ST.LIST_W, ST.BIG_CARD_H, [('name', f'pod_big{n}_card'), ('sensitive', 'false')])
    for st in STATES:
        styled(card, (st,), 'bg_color', '#00000000')
        styled(card, (st,), 'bg_image', ST.piece_images('single', True)[0])
        styled(card, (st,), 'bg_image_draw_type', 'default')
    card.children.append(_centred_label(f'pod_big{n}_t', ST.CM + 8, 0, ST.CARD_W - 16, ST.BIG_CARD_H, ('text', ''), ST.BIG_PX, INK_RGB, face=ST.BIG_FACE))
    v.children.append(card)
    return v


def cards_qr(card):
    """A QrCard: a black view as high as its Hero (hidden and insensitive until the payload shows it in the Hero's place) holding pod_qr_code, a QR_SIDE square centred on the card column and on the
    item's height that the payload paints in its EVT_AFTER_PAINT (patch/netservice.c wt_qr_paint: the paper, the modules, the corners)."""
    import pod_settings as ST
    v = cards_spacer('pod_qr', ST.hero_h(card.hero))
    v.children.append(Widget('view', ST.CM + (ST.CARD_W - ST.QR_SIDE) // 2, (v.h - ST.QR_SIDE) // 2, ST.QR_SIDE, ST.QR_SIDE, [('name', 'pod_qr_code'), ('sensitive', 'false')]))
    return v


def cards_qrpill(pill):
    """A QrPill: a sensitive black view (its button must be reachable) holding the flat pill pod_qrbtn in the flat pills' colours (SG_PILL_RGB, pressed SG_PILL_DOWN_RGB), the grey 14 px label and the wt_qr glyph; the
    payload sets its width and centres it for the language (patch/netservice.c wt_pill_fit), the asset's is the English label's at most."""
    import pod_settings as ST
    v = Widget('view', 0, 0, ST.LIST_W, ST.PILL_ITEM_H, [('name', 'pod_qrpill')])
    for st in STATES: styled(v, (st,), 'bg_color', '#000000')
    w = 2 * ST.PILL_PAD + ST.PILL_GLYPH + ST.PILL_GAP + 100
    b = Widget('button', ST.CM + (ST.CARD_W - w) // 2, ST.PILL_Y, w, ST.PILL_H, [('name', 'pod_qrbtn'), ('enable', 'true'), pod_i18n.text_prop(pill.text)])
    for st in STATES:   # the label ST.PILL_DROP px low, its caps centred on the glyph (whose PNG is padded below to stay where it was)
        styled(b, (st,), 'margin_top', str(2 + ST.PILL_DROP)); styled(b, (st,), 'margin_bottom', str(2 - ST.PILL_DROP))
    v.children.append(flat_pill(b, SG_PILL_RGB, SG_PILL_DOWN_RGB, ST.PILL_R, ink=ST.GREY, px=ST.PILL_PX, icon='wt_qr'))
    return v


def cards_cnote(name, note):
    """A centred note (Note.center): a view holding the note-size grey wrapping label pod_note<n>_t, centred on the card column."""
    import pod_settings as ST
    v = cards_spacer(name, ST.cnote_h(note))
    v.children.append(_centred_label(name + '_t', ST.CM + ST.CENTRE_INSET, ST.NOTE_LABEL_Y, ST.CARD_W - 2 * ST.CENTRE_INSET, ST.cnote_label_h(note), pod_i18n.text_prop(note.text), ST.CNOTE_PX, ST.GREY, 'top'))
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
    n_hdr = n_note = n_gap = n_big = n_hist = i = pos = 0  # i: the number the next row without a rid gets; pos: its place among the rows (its card piece)
    for it, y in placed:
        if it == ST.TOP: sv.children.append(cards_spacer('pod_top', ST.CM))
        elif it == ST.END: sv.children.append(cards_spacer('pod_end', ST.END_H))
        elif it is pod_pages.GAP: sv.children.append(cards_spacer(f'pod_gap{n_gap}', ST.GAP_H)); n_gap += 1
        elif it is pod_pages.REGION: sv.children.append(cards_region())
        elif isinstance(it, pod_pages.Graph): sv.children.append(cards_graph())
        elif isinstance(it, pod_pages.HistChart): sv.children.append(cards_hist(it, n_hist)); n_hist += 1
        elif isinstance(it, pod_pages.HistSummary): sv.children.append(cards_summary(n_hist)); n_hist += 1
        elif isinstance(it, pod_pages.Sliders): sv.children.append(cards_sliders())
        elif isinstance(it, pod_pages.Segment): sv.children.append(cards_segment())
        elif isinstance(it, pod_pages.HSliders): sv.children.append(cards_hsliders())
        elif isinstance(it, pod_pages.Brightness): sv.children.append(cards_brightness())
        elif isinstance(it, pod_pages.VolCard): sv.children.append(cards_volcard(it))
        elif isinstance(it, pod_pages.XfadeCard): sv.children.append(cards_xfade())
        elif isinstance(it, pod_pages.VolumeCard): sv.children.append(cards_volume())
        elif isinstance(it, pod_pages.CoverCard): sv.children.append(cards_cover())
        elif isinstance(it, pod_pages.Hdr): sv.children.append(cards_text(f'pod_sec{n_hdr}', ST.HDR_LABEL_Y, ST.HDR_LABEL_H, it.text, ST.HDR_PX, ST.HDR_H)); n_hdr += 1
        elif isinstance(it, pod_pages.Hero): sv.children.append(cards_hero(it, n_note)); n_note += 1
        elif isinstance(it, pod_pages.BigCard): sv.children.append(cards_bigcard(n_big)); n_big += 1
        elif isinstance(it, pod_pages.QrCard): sv.children.append(cards_qr(it))
        elif isinstance(it, pod_pages.QrPill): sv.children.append(cards_qrpill(it))
        elif isinstance(it, pod_pages.Note) and it.center: sv.children.append(cards_cnote(f'pod_note{n_note}', it)); n_note += 1
        elif isinstance(it, pod_pages.Note):
            sv.children.append(cards_text(f'pod_note{n_note}', ST.NOTE_LABEL_Y, ST.NOTE_LABEL_H + (it.lines - 1) * ST.WRAP_LINE, it.text, ST.NOTE_PX, ST.item_h(it), it.lines > 1)); n_note += 1
        else:
            sv.children.append(cards_row(i if it.rid is None else it.rid, it, pieces[pos], pieces[pos] in ('single', 'bot'))); pos += 1
            if it.rid is None: i += 1
        if getattr(it, 'start_hidden', False): hidden(sv.children[-1])   # (Battery History's items: the payload shows them while the switch is on)
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
MB_TITLE_RGB, MB_ARTIST_RGB = INK_RGB, '#D0D0D0'
MB_NAMES = ('pod_minibar', 'pod_mb_card', 'pod_mb_title', 'pod_mb_artist', 'pod_mb_play', 'pod_mb_pause', 'pod_mb_next')


def minibar():
    bar = hidden(Widget('view', MB_X, MB_Y, MB_W, MB_H, [('name', 'pod_minibar')]))
    card = Widget('button', 0, 0, MB_W, MB_H, [('name', 'pod_mb_card'), ('enable', 'true')])
    for st in ('normal', 'pressed', 'over', 'focused', 'disable', 'selected'):
        styled(card, (st,), 'bg_color', '#00000000')   # the glass image is the whole look; nothing is filled or stroked under or over it
        styled(card, (st,), 'bg_image', MB_GLASS_DOWN if st == 'pressed' else MB_GLASS)
        styled(card, (st,), 'text_color', INK_RGB)   # the card has no text; every inline-styled button is dark with light text (test/pod/assets.py)
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
SH_HEAD_X, SH_HEAD_W, SH_HEAD_TOP, SH_HEAD_H, SH_HEAD_PX, SH_HEAD_GAP = 10, 300, 17, 22, SECTION_PX, 5   # the 20 px line's ink runs from 20 to 36 (the line box has slack): 20 px of air above, 8 below
SH_TOP = SH_HEAD_TOP + SH_HEAD_H + SH_HEAD_GAP     # 44: the first row of covers
SH_BOTTOM = 0                                      # the artist line's box ends the shelf: scrolled to the end it is MB_GAP above the pill, as the last row was
def SH_H(n): return SH_TOP + n * GRID_CELL_H + (n - 1) * GRID_ROW_GAP + SH_BOTTOM   # the shelf's height for n rows of covers: 234, 434, 634
SH_HMAX = SH_H(SH_ROWS)
SH_NAMES = ('pod_shelf', 'pod_sh_head', 'pod_sh_title', 'pod_sh_sub')
SH_TITLE_RGB, SH_SUB_RGB = INK_RGB, SUB_RGB
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
    sh.children += style_labels((('pod_sh_title', SH_TITLE_PX, SH_TITLE_RGB), ('pod_sh_sub', SH_SUB_PX, SH_SUB_RGB)))
    return sh


# The Home pins of the menu's Home instance (patch/pins.c, docs/modules/pins.md; PIN_* of patch/offsets.inc): a view the width of the list, the first child of the scroll view while shown (the payload puts the
# rows below it), hidden and insensitive until something is pinned. No header: the tiles (covers and names) are painted by the payload in its own EVT_AFTER_PAINT, and it takes the taps; the one hidden
# label pod_pin_title only carries the name's text style (15 px white, centred).
PIN_W, PIN_TEXT_PX, PIN_COVER, PIN_TOP, PIN_PITCH, PIN_ROW_GAP, PIN_BOTTOM, PIN_ROWS = (OFFSETS[k] for k in ('PIN_W', 'PIN_TEXT_PX', 'PIN_COVER', 'PIN_TOP', 'PIN_PITCH', 'PIN_ROW_GAP', 'PIN_BOTTOM', 'PIN_ROWS'))
def PIN_H(n): return PIN_TOP + n * PIN_PITCH - PIN_ROW_GAP + PIN_BOTTOM   # the section's height for n rows of tiles: 130, 256 (patch/offsets.inc PIN_H)
PIN_HMAX = PIN_H(PIN_ROWS)
def pin_x(i, n):
    """Tile i's x with n pins (patch/pins.c pn_x): 1 or 2 pins are one row centred in the section, 3 or more start at PIN_MARGIN (a partial last row from the left)."""
    cols, gap, margin = (OFFSETS[k] for k in ('PIN_COLS', 'PIN_GAP', 'PIN_MARGIN'))
    x0 = (PIN_W - (n * PIN_COVER + (n - 1) * gap)) // 2 if n < cols else margin
    return x0 + i % cols * (PIN_COVER + gap)
PIN_NAMES = ('pod_pins', 'pod_pin_title')


def pins():
    sec = hidden(Widget('view', 0, 0, PIN_W, PIN_HMAX, [('name', 'pod_pins')]))
    styled(sec, ('normal', 'disable', 'focused', 'pressed', 'over', 'selected'), 'bg_color', '#000000')
    sec.children += style_labels((('pod_pin_title', PIN_TEXT_PX, INK_RGB, 'center'),))
    return sec


# The cache pill of the Home instance (patch/homecover.c, docs/modules/homecover.md; HC_* of patch/offsets.inc): a 296 x 40 capsule (#1C1C1E, fully rounded) above the list, hidden and insensitive until the payload
# shows it (and moves the list down by HC_H). Children: the text label pod_cover_prog (15 px #AAAAAA, "Preparing covers 120/840"), a 4 px progress bar (pod_cache_track #FFFFFF33, pod_cache_fill #EBEBEB, the
# payload resizes the fill like the Podcasts refresh card's) and the stop button pod_cache_x (the disc pod_cache_x / _down; a 40 px touch box).
COVER_PROG, CACHE_PILL, CACHE_FILL, CACHE_X = 'pod_cover_prog', 'pod_cache_pill', 'pod_cache_fill', 'pod_cache_x'
HC_PX = OFFSETS['HC_PX']


def cache_pill():
    o = OFFSETS
    pill = hidden(Widget('view', o['HC_X'], o['HC_Y'], o['HC_W'], o['HC_PH'], [('name', CACHE_PILL)]))
    for st in STATES:
        styled(pill, (st,), 'bg_color', SURFACE_RGB)
        styled(pill, (st,), 'border_width', '0')
        styled(pill, (st,), 'round_radius', str(o['HC_PH'] // 2))
    lab = label(COVER_PROG, o['HC_TX'], o['HC_TY'], o['HC_BW'], o['HC_TH'], '', HC_PX, SH_SUB_RGB, 'left')
    styled(lab, ('normal',), 'text_align_v', 'middle')
    lab.set('sensitive', 'false')
    pill.children.append(lab)
    for name, w, rgb in (('pod_cache_track', o['HC_BW'], PD_TRACK_RGB), (CACHE_FILL, o['HC_BH'], PD_FILL_RGB)):
        bar = Widget('view', o['HC_TX'], o['HC_BY'], w, o['HC_BH'], [('name', name), ('sensitive', 'false')])
        for st in STATES:
            styled(bar, (st,), 'bg_color', rgb)
            styled(bar, (st,), 'border_width', '0')
            styled(bar, (st,), 'round_radius', str(o['HC_BH'] // 2))
        pill.children.append(bar)
    pill.children.append(Widget('button', o['HC_XX'], o['HC_XY'], o['HC_XW'], o['HC_PH'], [
        ('name', CACHE_X), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:over:icon', CACHE_X), ('style:normal:icon', CACHE_X), ('style:pressed:icon', CACHE_X + '_down')]))
    return pill


# The Daily Mix section of the menu's Home instance (patch/dailymix.c, docs/modules/dailymix.md; the DM_* numbers are tools/pod_dailymix.py's, patch/offsets.inc has the
# same): a view the width of the list between the shown rows and the Recently Played shelf, hidden and insensitive until the payload has a mix to show. The header
# pod_dm_head is the shelf's (a stock hscroll_label, the key "Made for You"); the card pod_dm_card (DM_W x DM_H at DM_X, DM_TOP) paints the art and the text itself
# (its own EVT_AFTER_PAINT) and takes the taps that open the playlist; the play disc pod_dm_play is a stock button over its corner (a later sibling, so it takes its own
# touches) whose look is the glass images dm_disc / dm_disc_down; the two hidden labels only carry the title (36 px white) and artists (16 px #EBEBEB) text styles.
DM_DISC_IMAGE = 'dm_disc'


def daily():
    import pod_dailymix as D
    from mod_icons import SYNC_DM
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
    busy = hidden(Widget('image', D.DM_BUSY_X, D.DM_BUSY_Y, D.DM_BUSY_PX, D.DM_BUSY_PX, [('name', 'pod_dm_busy'), ('image', SYNC_DM), ('draw_type', 'center')]))
    sec.children = [head, busy, card, play]
    sec.children += style_labels((('pod_dm_title', D.DM_TITLE_PX, INK_RGB), ('pod_dm_sub', D.DM_SUB_PX, '#%02X%02X%02X' % D.SUB_RGB)))
    return sec


# The keyboard page (patch/keyboard.c, docs/modules/keyboard.md; geometry: tools/pod_keyboard.py): the plain navbar, the search field (magnifier, grey hint, text, caret, clear button),
# the 180 px pad of buttons at the bottom of the window (26 char keys laid out as the lowercase page, the function keys; the payload moves, relabels and hides them per page), and
# last the key pop-up (a stem and a balloon with the letter): insensitive, shown by the payload while a key is down. White and grey only.
def kb_button(name, x, y, w, fill, down, ink=PK.KB_INK, px=20, text=None, icon=None, dim=None):
    b = Widget('button', x, y, w, PK.KB_KH, [('name', name), ('enable', 'true')] + ([text] if text else []))
    return flat_pill(b, fill, down, PK.KB_RADIUS, None, ink, px, dim, False, icon)


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
    pad.children.append(kb_button('kb_go', x, y, w, PK.KB_FN, PK.KB_FN_DOWN, px=15, text=pod_i18n.text_prop('Search'), dim=PK.KB_DIM))
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
    # The long-press accent strip (English and French letter pages): a rounded #6E6E73 bar over the key, a highlight pill behind the selected variant and a pool of ACC_MAX labels the payload fills and
    # moves; all insensitive for life, only visibility, text and position change (as the balloon).
    acc = hidden(kb_view('kb_acc', 0, 0, 2 * PK.ACC_PAD + PK.ACC_MAX * PK.ACC_CELL, PK.ACC_H, PK.KB_POP, PK.ACC_R))
    acch = hidden(kb_view('kb_acc_h', PK.ACC_PAD, PK.ACC_PAD, PK.ACC_CELL, PK.ACC_H - 2 * PK.ACC_PAD, PK.KB_ACC_HL, PK.ACC_HL_R))
    accl = [hidden(label(f'kb_a{i}', PK.ACC_PAD + i * PK.ACC_CELL, 0, PK.ACC_CELL, PK.ACC_H, '', PK.ACC_PX, PK.KB_INK, 'center')) for i in range(PK.ACC_MAX)]
    for lab in accl:
        styled(lab, ('normal',), 'text_align_v', 'middle')
    acc.children = [acch] + accl
    return [pad, strip, stem, pop, acc]


def build_keyboard_page(page):
    """The keyboard page (patch/keyboard.c keyboard_open): the search field is kb_capsule (fill and magnifier) under a transparent kb_field; a name entry (KB_DONE) hides it, shows kb_card
    (Radio's Add by URL row) and moves kb_field onto the row."""
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    cap = kb_view('kb_capsule', PK.FIELD_X, PK.FIELD_Y, PK.FIELD_W, PK.FIELD_H, PK.KB_BG, PK.FIELD_R)
    cap.children.append(Widget('image', PK.FIELD_MAG_X, (PK.FIELD_H - PK.FIELD_MAG) // 2, PK.FIELD_MAG, PK.FIELD_MAG, [('name', 'kb_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')]))
    cap.set('sensitive', 'false')   # the field over it takes the touches
    root.children.append(cap)
    root.children.append(hidden(kb_view('kb_card', _ST.CM, PK.NAME_Y, _ST.CARD_W, PK.NAME_ROW, _ST.CARD_RGB, _ST.CARD_R)))
    tw = max(PK.FIELD_TEXT_W, PK.NAME_TW)   # the labels hold either room (the keyboard fits the text to the room it is given)
    field = text_field(PK.FIELD_X, PK.FIELD_Y, PK.FIELD_W, PK.FIELD_H, '#00000000', 0, PK.FIELD_TEXT_X, tw, PK.FIELD_PX, PK.KB_GREY, PK.KB_INK, PK.CARET_Y,
                       PK.FIELD_CLEAR_X, PK.FIELD_CLEAR_W, None, True)   # sensitive: stock's hit test does not look into an insensitive parent
    root.children.append(field)
    root.children += keyboard_pad_widgets()
    return root


# The Folders page (patch/folders.c, docs/modules/folders.md): the Songs page's structure without its sections, rail, sort card and count. The glass navbar (Back, the small title, "..." | Now Playing as one
# capsule: the "..." (or btn_select, Select, on a playlist file's tracks) is the left cap, Now Playing the right cap) over a stock list whose one child, view_grid, holds the large title and the Play / Shuffle pills (the payload shows the pills for a folder that holds an
# audio file) and has the rows painted into it; the select mode's Select All text and bar are the Songs page's.
def build_folders_page(page):
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, more_left=True)   # "..." | Now Playing (the Songs and Artists capsule); the payload hides the "..." at the root list of storages (Now Playing is the disc there)
    nb.children[0].set('visible', 'false')   # the small title: the payload shows it once the large title has scrolled away
    nb.children.append(hidden(Widget('button', NAV_VIEW_X, 0, NAV_VIEW_W, NAVBAR_H, [   # Select in the "..." place on a playlist file's tracks (patch/folders.c fo_direct): the left cap at 214, no card
        ('name', 'btn_select'), ('enable', 'true'), ('style', 'img_btn_style'),
        ('style:pressed:icon', 'pod_nav_selectl_down'), ('style:normal:icon', 'pod_nav_selectl'), ('style:over:icon', 'pod_nav_selectl')])))
    nb.children[-1].set('dirty_rect_tolerance', str(NAV_ICON_OVERFLOW))   # (added after navbar's loop: its 60 px glyph paints 7 px beyond the slot)
    nb.children.append(selall_button())
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'folders_listview')
    sv = lv.children[0]
    sv.set('name', 'folders_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = large_title('sg_title', page.title)
    grid.children = [title, hidden(sg_pill('btn_play', o['SG_PILL_X0'], o['SG_PILL_Y'], 'Play', 'sg_play', down=SG_PILL_PRESS_RGB)),
                     hidden(sg_pill('btn_shuffle', o['SG_PILL_X1'], o['SG_PILL_Y'], 'Shuffle', 'sg_shuffle', down=SG_PILL_PRESS_RGB))]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/folders.c shows it while yoffset > 0 (at rest it would darken the large title)
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB),))
    root.children.append(select_bar('sg_bar', [('sg_add', 'add'), ('sg_del', 'del')]))
    root.children.extend(view_sort_card(sort_keys=pod_pages.FOLDERS_SORT_KEYS))   # the "..." card: Select, then Name, Date Modified, Type (patch/folders.c offers rows 0..2; Search and the view rows stay hidden)
    return root
LP_DIM_RGB = DIM_RGB   # a covered row's name (patch/lupick.c): the grey of a row that cannot be chosen


def build_lupick_page(page):
    """Update Library > Choose Folders (patch/lupick.c, docs/modules/libupdate.md "The folder picker"): the Folders page's structure with no large title: the glass navbar (Back, the title, the flat
    Select All text button of the select mode; Now Playing hidden), a stock list holding one view the payload paints (a card of rows with select circles), the text styles of the rows and the caption, and the bottom bar with the Scan pill."""
    o = OFFSETS
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title)
    for c in nb.children:   # Select All takes the right end: Now Playing stays, hidden, as in the select mode
        if c.name == 'btn_backtoplayer': hidden(c)
    nb.children[0].w = SG_SELALL_X - NAV_TITLE_X   # the title runs to the Select All button
    sa = selall_button()
    sa.set('visible', 'true')
    sa.set('sensitive', 'true')
    nb.children.append(sa)
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'lupick_listview')
    sv = lv.children[0]
    sv.set('name', 'lupick_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))
    root.children.append(hidden(label('label_status', 10, room_y(30), SCREEN_W - 20, 30, '', 20, HINT_RGB)))
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_dim', LIST_TITLE_PX, LP_DIM_RGB), ('label_cap', CAPTION_PX, SUB_RGB, 'left')))
    bar = Widget('view', 0, CLIENT_H - o['SG_BAR_H'], SCREEN_W, o['SG_BAR_H'], [('name', 'lp_bar')])
    for st in STATES: styled(bar, (st,), 'bg_color', '#000000')
    pill = Widget('button', 16, (o['SG_BAR_H'] - o['SG_PILL_H']) // 2, SCREEN_W - 32, o['SG_PILL_H'], [('name', 'lp_scan'), ('enable', 'true'), pod_i18n.text_prop('Scan Folders')])
    flat_pill(pill, LP_PILL_RGB, LP_PILL_DOWN_RGB, o['SG_PILL_R'], RAISED_RGB, '#000000', SG_PILL_PX, LP_PILL_DIM_RGB)   # live: a light grey pill with black text (the toggle rule); dimmed: dark grey with grey text
    bar.children = [pill]
    root.children.append(bar)
    return root
LP_PILL_RGB, LP_PILL_DOWN_RGB, LP_PILL_DIM_RGB = '#E5E5EA', '#C7C7CC', '#98989D'   # pod_search CHIP_ON_RGB: the light grey of the selected chip

RD_FIELD_W = SCREEN_W - 2 * PS.SE_FIELD_X   # the Radio search field's width (patch/radiopage.c RP_TEXT_W is its text's)
RD_TEXT_W = RD_FIELD_W - PS.SE_TEXT_X - PS.SE_CLEAR_W
# Add by URL (patch/radiopage.c rp_entry): the Sign In page's card (tools/pod_ndserver.py build_login), two 48 px rows (Stream URL, Station Name) under the navbar. The
# search capsule's fill and magnifier are rd_capsule; kb_field itself has no fill and its text at x 0, so the payload moves it between the capsule (x 48, after the
# magnifier) and a card row (x 24, 6 px down: the 36 px field centred in the 48 px row) without the keyboard's text origin changing.
RD_ADD_Y, RD_ADD_ROW, RD_ADD_X, RD_ADD_VAL_W, RD_ADD_TW = 56, 48, 24, 272, 232   # patch/radiopage.c RP_ADD_Y, RP_ADD_ROW, RP_ADD_X, -, RP_ADD_TW
RD_ADD_ROWS = ('Stream URL', 'Station Name')
RD_KB_X, RD_KB_W = PS.SE_FIELD_X + PS.SE_TEXT_X, RD_FIELD_W - PS.SE_TEXT_X   # the field over the capsule (patch/radiopage.c RP_KB_X, RP_KB_W)
RD_CREDIT_PX = 14   # the credit line's size (patch/radiopage.c RP_CREDIT_PX)
RD_SHEET_ROWS = (('add', 'pod_ic_rd_add', 'Add to My Stations', False, False), ('info', 'rm_ic_info', 'Station Info', False, False))   # Radio Now Playing's sheet: two rows, the first's glyph and label swapped for Remove from My Stations by the payload (patch/radionp.c)
RS_SHEET_ROWS = (('remove', 'pod_ic_trash_red', 'Remove from My Stations', False, True),)   # the sheet (patch/radiopage.c): a long press on a My Stations row, Remove from My Stations
RS_CARD_ACTS, RS_CARD_GLYPHS = ('Select', 'Sort by Name', 'Add by URL', 'Import from Card'), ('pod_ic_vsselect', 'pod_ic_vsorder', 'pod_ic_vslink', 'pod_ic_vsimport')   # the stations' "..." card's four actions (slots 6..9; Recently Played retexts slot 9 to Clear Recently Played, red, as the last row)


def radio_field_widgets():
    """The Radio page's two fields on one kb_field, in paint order: the search capsule (rd_capsule: the Search page's fill, radius and magnifier, the page's width, a tap on it brings the pad
    back), Add by URL's card (rd_add_card, its hairline, each row's value rd_add_v<i> and grey name rd_add_h<i>, a button a row rd_add_hit<i>), then kb_field over both: no fill, text at x 0,
    the Search page's clear button at its right end. All hidden; patch/radiopage.c shows one set and moves the field onto it."""
    cap = kb_view('rd_capsule', PS.SE_FIELD_X, RD_ADD_Y, RD_FIELD_W, PS.SE_FIELD_H, PS.FIELD_RGB, PS.SE_FIELD_R)
    cap.children.append(Widget('image', PS.SE_MAG_X, (PS.SE_FIELD_H - PK.FIELD_MAG) // 2, PK.FIELD_MAG, PK.FIELD_MAG, [('name', 'kb_mag'), ('image', 'qk_mag'), ('draw_type', 'center'), ('sensitive', 'false')]))
    out = [hidden(cap)]
    n = len(RD_ADD_ROWS)
    out.append(hidden(kb_view('rd_add_card', _ST.CM, RD_ADD_Y, _ST.CARD_W, n * RD_ADD_ROW, _ST.CARD_RGB, _ST.CARD_R)))
    hair = Widget('view', RD_ADD_X, RD_ADD_Y + RD_ADD_ROW - 1, _ST.CM + _ST.CARD_W - RD_ADD_X, 1, [('name', 'rd_add_hair'), ('sensitive', 'false')])
    for st in STATES: styled(hair, (st,), 'bg_color', _ST.CARD_HAIR_RGB)
    out.append(hidden(hair))
    for i, english in enumerate(RD_ADD_ROWS):
        for name, colour, key in ((f'rd_add_v{i}', PK.KB_INK, None), (f'rd_add_h{i}', PK.KB_GREY, english)):
            lab = label(name, RD_ADD_X, RD_ADD_Y + i * RD_ADD_ROW, RD_ADD_VAL_W, RD_ADD_ROW, '', PS.FIELD_PX, colour, 'left')
            if key: lab.set(*pod_i18n.text_prop(key))
            lab.set('sensitive', 'false')
            styled(lab, ('normal',), 'text_align_v', 'middle')
            out.append(hidden(lab))
    for i in range(n):
        out.append(hidden(Widget('button', _ST.CM, RD_ADD_Y + i * RD_ADD_ROW, _ST.CARD_W, RD_ADD_ROW, [('name', f'rd_add_hit{i}'), ('enable', 'true'), ('style', 'img_btn_style')])))
    tw = max(RD_TEXT_W, RD_ADD_TW)   # the labels hold either field's text room (the keyboard fits the text to the room it is given)
    field = text_field(RD_KB_X, RD_ADD_Y, RD_KB_W, PS.SE_FIELD_H, '#00000000', 0, 0, tw, PS.FIELD_PX, PS.FIELD_HINT, PS.FIELD_INK, PS.SE_CARET_Y,
                       RD_KB_W - PS.SE_CLEAR_W, PS.SE_CLEAR_W, sensitive=True)
    hidden(field); field.set('sensitive', 'false')
    out.append(field)
    return out


def build_radio_page(page):
    """The Radio page (patch/radiopage.c, docs/modules/radio.md): the Folders page's structure (the glass navbar with the globe as its left cap, a stock list holding one view the payload
    paints, the large title in that view) and the station grid's and the countries' text styles."""
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
    nb.children.append(selall_button())   # My Stations' select mode (patch/radiopage.c)
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'radio_listview')
    sv = lv.children[0]
    sv.set('name', 'radio_scrollview')
    grid = Widget('view', 0, 0, SCREEN_W, GRID_VIEW_H, [('name', 'view_grid')])
    styled(grid, ('normal',), 'bg_color', '#000000')
    title = large_title('sg_title', page.title)
    credit = hidden(label('rd_credit', 0, 0, SCREEN_W - 2 * 12, 20, '', RD_CREDIT_PX, SUB_RGB, 'left'))   # the directory's credit under its rows (patch/radiopage.c moves it and shows it)
    credit.set(*pod_i18n.text_prop('Stations from radio-browser.info'))
    styled(credit, ('normal',), 'text_align_v', 'middle')
    grid.children = [title, credit]
    sv.children.append(grid)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/radiopage.c shows it while yoffset > 0 (at rest it would darken the large title)
    status = hidden(label('label_status', 20, room_y(120), SCREEN_W - 40, 120, '', 18, HINT_RGB))   # the captions are grey, centred in the room under the navbar (room_y); up to four lines of 280 px (the payload sets line_wrap and word_wrap)
    styled(status, ('normal',), 'text_align_v', 'middle')
    root.children.append(status)
    root.children += style_labels((('label_row_title', LIST_TITLE_PX, INK_RGB), ('label_row_sub', LIST_SUB_PX, SUB_RGB),
                                   ('label_grid_title', GRID_ALBUM_PX, INK_RGB), ('label_grid_sub', GRID_ARTIST_PX, SUB_RGB)))   # the row and the Albums grid's text styles (never shown)
    root.children.extend(azlist_labels())   # the countries' A-Z list (patch/azlist.c): the header letter, the rail letters
    root.children.extend(azlist_rail())
    root.children += radio_field_widgets()

    root.children += keyboard_pad_widgets()
    root.children.append(select_bar('rd_bar', [('rd_del', 'one')]))   # My Stations' select mode: one Delete pill (the Playlists page's)
    root.children.extend(view_sort_card(sort_keys=('Name',) * len(VS_SORT_KEYS), act_keys=RS_CARD_ACTS, act_glyphs=RS_CARD_GLYPHS))   # the "..." card (My Stations: the four actions, Grid, List; Recently Played: Grid, List, Clear Recently Played)
    root.children.extend(sheet_widgets(RN_SHEET, RS_SHEET_ROWS, 1))   # the long press sheet, last: above everything
    return root


RN_SHEET = 'rd_sh'   # the stations page's station sheet, the same widget set
RN_CARD_GLYPH = RAISED_RGB   # the art card without a logo (patch/radionp.c RN_CARD_GLYPH); with one it is white and the window takes the logo's tone
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
    NP.text_style(tx, RDN_LIVE_PX, INK_RGB, 'center')
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
# label / value pairs on, wrapped by the Podcasts episode page's wrapper). Three hidden labels only carry the text styles: the station's name (22 px white), a pair's label (14 px grey), its value (18 px white).
SI_HEAD_PX, SI_KEY_PX, SI_VAL_PX = 22, 14, 18


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
    root.children += style_labels((('label_head', SI_HEAD_PX, INK_RGB), ('label_key', SI_KEY_PX, SUB_RGB), ('label_val', SI_VAL_PX, INK_RGB)))
    return root


# Get Info (patch/songinfo.c, docs/modules/songinfo.md): Station Info's structure (the stock navbar over a stock list holding one content view the payload paints on): the cover, the title, artist and
# album beside it, then label / value pairs. Four hidden labels only carry the text styles: the title (22 px white), the artist and the album (16 px grey), a pair's label (14 px grey), its value (18 px white).
GI_HEAD_PX, GI_SUB_PX, GI_KEY_PX, GI_VAL_PX = 22, 16, 14, 18


def build_songinfo_page(page):
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'gi_listview')
    sv = lv.children[0]
    sv.set('name', 'gi_scrollview')
    view = Widget('view', 0, 0, SCREEN_W, CLIENT_H - NAVBAR_H, [('name', 'gi_view')])
    styled(view, ('normal',), 'bg_color', '#000000')
    sv.children.append(view)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))
    root.children += style_labels((('label_head', GI_HEAD_PX, INK_RGB), ('label_sub', GI_SUB_PX, SUB_RGB), ('label_key', GI_KEY_PX, SUB_RGB), ('label_val', GI_VAL_PX, INK_RGB)))
    return root


# The Wi-Fi page (patch/wifipage.c, docs/modules/wifi.md): the Settings pages' grouped cards (tools/pod_settings.py numbers: 52 px rows, cards 10..310, #1C1C1E, 12 px corners, hairlines, the
# stock switch) under our navbar, in the stock list. The payload shows and hides rows and sets each shown row's picture piece (single / top / mid / bottom) and text, so no widget is made at run
# time. The children are in display order, so the stock list_view layouter (which stacks the visible children and ignores y) and the payload's own widget_move agree: a top spacer, the switch
# row, the connected network's row (the first group's second row), the My Networks header and its rows, the Networks header (a spinner after its text while scanning), its rows and Other..., a bottom spacer.
# A network row is a stock list_item holding the check or spinner (left), the name, the lock, the Wi-Fi fan signal and the info glyph (right); every child is insensitive: the row takes the tap
# (a tap right of WF_INFO_X is the info glyph's). Pool sizes: patch/wifictl.h WF_MAX scanned networks, patch/wifipage.c WP_MY saved ones.
WF_CUR, WF_MY, WF_OTH = 1, 16, 32   # the row pools: the connected network, My Networks, Networks (patch/wifipage.c WP_CUR, WP_MY, WP_OTH)
WF_ROWS = WF_CUR + WF_MY + WF_OTH
WF_CHK_X, WF_NAME_X, WF_NAME_W, WF_LOCK_X, WF_SIG_X, WF_INFO_X, WF_INFO_PX = 24, 54, 156, 216, 242, 274, 22   # row relative: the check column, the name's box (its ink starts at 56), the glyphs' left edges
WF_SIG_W, WF_SIG_H, WF_LOCK_PX, WF_CHK_PX, WF_SPIN_PX = 20, 16, 16, 20, 14   # the signal fan (mod_icons.WIFI_SIG_W x H): 16 px tall like the lock
WF_HDR_PX, WF_HDR_X, WF_HDR_H = _ST.HDR_PX, 24, 40   # the grey group headers: the Settings pages' (18 px), the text of the rows (x 24), a 40 px strip (the label 14..36 in it)


def wf_hair(name, x):
    import pod_settings as ST
    hair = Widget('view', x, ST.ROW_H - 1, ST.CM + ST.CARD_W - x, 1, [('name', name), ('sensitive', 'false')])
    for st in STATES: styled(hair, (st,), 'bg_color', ST.CARD_HAIR_RGB)
    return hair


def wf_row(name, piece):
    """A card row: a stock list_item whose background is the picture piece (the payload changes it), nothing else of its own."""
    import pod_settings as ST
    item = Widget('list_item', 0, 0, ST.LIST_W, ST.ROW_H, [('name', name), ('style', 'list_item_style')])
    normal, down = ST.piece_images(piece)
    for st in ('normal', 'over', 'pressed', 'focused', 'disable'):
        styled(item, (st,), 'bg_color', '#00000000')
        styled(item, (st,), 'bg_image', down if st == 'pressed' else normal)
        styled(item, (st,), 'bg_image_draw_type', 'default')
        styled(item, (st,), 'border_width', '0')
        styled(item, (st,), 'border_color', '#00000000')
    return item


def wf_label(name, x, w, english, style='srlabel_leftwhite21_style'):
    import pod_settings as ST
    return Widget('hscroll_label', x, 0, w, ST.ROW_H, [('name', name), ('style', style), pod_i18n.text_prop(english) if english else ('text', ''),
                                                        ('only_parent_focus', 'true'), ('ellipses', 'true'), ('yoyo', 'true'), ('loop', 'true'), ('sensitive', 'false')])


def wf_image(name, x, y, w, h, image, draw='icon'):
    return Widget('image', x, y, w, h, [('name', name), ('image', image), ('draw_type', draw), ('sensitive', 'false')])


def wf_net_row(k):
    import pod_settings as ST
    row = hidden(wf_row(f'wf_row{k}', 'mid'))
    mid = lambda h: (ST.ROW_H - h) // 2
    row.children = [hidden(wf_image(f'wf_chk{k}', WF_CHK_X, mid(WF_CHK_PX), WF_CHK_PX, WF_CHK_PX, 'pod_check')), wf_label(f'wf_name{k}', WF_NAME_X, WF_NAME_W, ''),
                    hidden(wf_image(f'wf_lock{k}', WF_LOCK_X, mid(WF_LOCK_PX), WF_LOCK_PX, WF_LOCK_PX, 'wf_lock')),
                    wf_image(f'wf_sig{k}', WF_SIG_X, mid(WF_SIG_H), WF_SIG_W, WF_SIG_H, 'wf_sig3'), wf_image(f'wf_info{k}', WF_INFO_X, mid(WF_INFO_PX), WF_INFO_PX, WF_INFO_PX, 'wf_info'),
                    wf_hair(f'wf_hair{k}', WF_HDR_X)]
    return row


def wf_header(name, english, spinner=False):
    import pod_settings as ST
    v = hidden(cards_spacer(name, WF_HDR_H))
    v.children.append(scroll_text(name + '_t', WF_HDR_X, ST.HDR_LABEL_Y, ST.HDR_W, ST.HDR_LABEL_H, WF_HDR_PX, ST.GREY, 'left', english))
    if spinner:   # after the text: the payload moves it there; hidden until a scan runs
        v.children.append(hidden(wf_image(name + '_spin', 100, ST.HDR_LABEL_Y + (ST.HDR_LABEL_H - WF_SPIN_PX) // 2, WF_SPIN_PX, WF_SPIN_PX, 'wf_spin0', 'default')))
    return v


def build_wifi_page(page):
    import pod_settings as ST
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'wifi_listview')
    sv = lv.children[0]
    sv.set('name', 'wifi_scrollview')
    sw = wf_row('wf_row_sw', 'single')
    x, w = ST.label_box('switch', False)
    ax, ay, aw, ah = ST.accessory('switch')
    sw.children = [wf_label('wf_sw_label', x, w, 'Wi-Fi'), wf_image('wf_sw_img', ax, ay, aw, ah, 'sset_off', 'default'), wf_hair('wf_hair_sw', WF_HDR_X)]
    sv.children.append(cards_spacer('pod_top', ST.CM))
    sv.children.append(sw)
    sv.children += [wf_net_row(k) for k in range(WF_CUR)]
    sv.children.append(wf_header('wf_hdr_my', 'My Networks'))
    sv.children += [wf_net_row(k) for k in range(WF_CUR, WF_CUR + WF_MY)]
    sv.children.append(wf_header('wf_hdr_net', 'Networks', True))
    sv.children += [wf_net_row(k) for k in range(WF_CUR + WF_MY, WF_ROWS)]
    other = hidden(wf_row('wf_row_other', 'bot'))
    other.children = [wf_label('wf_other_label', WF_NAME_X, WF_NAME_W + 40, 'Other…')]
    sv.children.append(other)
    sv.children.append(cards_spacer('pod_end', ST.END_H))
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/wifipage.c shows it while the list is scrolled
    return root


# The Bluetooth page (patch/btpage.c, docs/modules/bluetooth.md "The page"): the Wi-Fi page's cards, rows, glyphs and numbers. Card 1 holds the Bluetooth switch row and, while it is on, the Audio Codec value row; under it a grey
# note (this player's name); My Devices (the paired devices) and Other Devices (the found ones, a small spinner after the header's text while the search runs) are cards of pooled device rows; the last row of the
# second card is Search Again. A device row is the Wi-Fi network row without the lock and the signal: the check or the connecting spinner at the left, the name, and (a paired device) the info glyph at the right.
# Children are in display order (the stock layouter stacks the visible ones; the payload moves them to the same places). Pools: patch/btpage.c BP_MY paired, BP_OTH found devices (stock's lists are unbounded).
BT_MY, BT_OTH = 8, 16
BT_ROWS = BT_MY + BT_OTH
BT_NAME_W_PAIRED, BT_NAME_W_OTHER = WF_INFO_X - 10 - WF_NAME_X, 296 - WF_NAME_X   # the name's box: up to the info glyph (less 10), or to the card's right ink edge


def bt_dev_row(k):
    import pod_settings as ST
    paired = k < BT_MY
    row = hidden(wf_row(f'bt_row{k}', 'mid'))
    mid = lambda h: (ST.ROW_H - h) // 2
    row.children = [hidden(wf_image(f'bt_chk{k}', WF_CHK_X, mid(WF_CHK_PX), WF_CHK_PX, WF_CHK_PX, 'pod_check')), wf_label(f'bt_name{k}', WF_NAME_X, BT_NAME_W_PAIRED if paired else BT_NAME_W_OTHER, '')]
    if paired: row.children.append(wf_image(f'bt_info{k}', WF_INFO_X, mid(WF_INFO_PX), WF_INFO_PX, WF_INFO_PX, 'wf_info'))
    row.children.append(wf_hair(f'bt_hair{k}', WF_HDR_X))
    return row


def build_bluetooth_page(page):
    import pod_settings as ST
    from mod_icons import CARD_CHEVRON
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'bluetooth_listview')   # (stock's own names for the page's two lists)
    sv = lv.children[0]
    sv.set('name', 'bluetooth_scrollview')
    sw = wf_row('bt_row_sw', 'single')
    x, w = ST.label_box('switch', False)
    ax, ay, aw, ah = ST.accessory('switch')
    sw.children = [wf_label('bt_sw_label', x, w, 'Bluetooth'), wf_image('bt_sw_img', ax, ay, aw, ah, 'sset_off', 'default'), wf_hair('bt_hair_sw', WF_HDR_X)]
    codec = hidden(wf_row('bt_row_codec', 'bot'))   # a value row: the label, the codec's name (right aligned, grey, the payload gives it the room its text needs) and the Settings chevron
    cx, cw = ST.label_box('value', False)
    vx, vw = ST.value_box()
    val = Widget('hscroll_label', vx, 0, vw, ST.ROW_H, [('name', 'bt_codec_val'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(val, (st,), 'font_size', str(ST.VALUE_PX))
        styled(val, (st,), 'text_color', ST.GREY)
        styled(val, (st,), 'text_align_h', 'right')
        styled(val, (st,), 'text_align_v', 'middle')
    chx, chy, chw, chh = ST.accessory('chevron')
    codec.children = [wf_label('bt_codec_label', cx, cw, 'Audio Codec'), val, wf_image('bt_codec_chev', chx, chy, chw, chh, CARD_CHEVRON[0])]
    sv.children.append(cards_spacer('pod_top', ST.CM))
    sv.children.append(sw)
    sv.children.append(codec)
    sv.children.append(hidden(cards_text('bt_note', ST.NOTE_LABEL_Y, ST.NOTE_LABEL_H, 'This player is shown as “%s”', ST.NOTE_PX, ST.NOTE_H)))
    sv.children.append(wf_header('bt_hdr_my', 'My Devices'))
    sv.children += [bt_dev_row(k) for k in range(BT_MY)]
    sv.children.append(wf_header('bt_hdr_oth', 'Other Devices', True))
    sv.children += [bt_dev_row(k) for k in range(BT_MY, BT_ROWS)]
    search = hidden(wf_row('bt_row_search', 'bot'))
    search.children = [wf_label('bt_search_label', WF_NAME_X, WF_NAME_W + 40, 'Search Again')]
    sv.children.append(search)
    sv.children.append(cards_spacer('pod_end', ST.END_H))
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/btpage.c shows it while the list is scrolled
    return root


# One network's info page (patch/wifipage.c wi_open, docs/modules/wifi.md "The info page"): the same cards and pieces as the Wi-Fi page; the payload shows, hides and moves the rows (display order again, so the
# stock layouter's stacking agrees): Forget This Network (a saved network), the info card (WI_FIELDS label / value rows, room for the enterprise rows of a later stage), Auto-Join (saved) or Join (not saved),
# with the card gaps between them. The navbar's title is the network's name (set by the payload).
WI_FIELDS = 4   # patch/wifipage.c WI_FIELDS
WI_NAME_H = 20  # patch/wifipage.c WI_NAME_H: a line of the whole name above the cards
WI_LABEL_W, WI_VALUE_X, WI_VALUE_PX = 116, 140, 18   # a field row: the label's box (card relative from x 24) and the right aligned grey value's box up to the card's right ink edge (x 296)


def wi_text(name, x, w, english, px, rgb, align):
    """A label of a row that takes no style name: its own size, colour and alignment (the value labels of the Settings cards are made the same way)."""
    return scroll_text(name, x, 0, w, 52, px, rgb, align, english)


def build_wifiinfo_page(page):
    import pod_settings as ST
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'wifiinfo_listview')
    sv = lv.children[0]
    sv.set('name', 'wifiinfo_scrollview')
    x = ST.CM + ST.PAD
    centred = lambda name, english, rgb=INK_RGB: wi_text(name, x, ST.CARD_W - 2 * ST.PAD, english, 21, rgb, 'center')
    forget = hidden(wf_row('wi_row_forget', 'single'))
    forget.children = [centred('wi_forget_t', 'Forget This Network', RED_RGB)]
    auto = hidden(wf_row('wi_row_auto', 'single'))
    ax, ay, aw, ah = ST.accessory('switch')
    auto.children = [wf_label('wi_auto_t', x, ST.accessory('switch')[0] - 8 - x, 'Auto-Join'), wf_image('wi_auto_img', ax, ay, aw, ah, 'sset_on', 'default')]
    join = hidden(wf_row('wi_row_join', 'single'))
    join.children = [centred('wi_join_t', 'Join')]
    sv.children.append(cards_spacer('pod_top', ST.CM))
    for k in range(2):   # the whole name's lines, shown above the cards when the navbar's title is cut (patch/wifipage.c wi_name): grey, centred, as the password page's line
        nm = hidden(cards_spacer(f'wi_nm{k}', WI_NAME_H))
        nm.children = [label(f'wi_name{k}', ST.CM, 0, ST.CARD_W, WI_NAME_H, '', WK_LINE_PX, ST.GREY, 'center')]
        sv.children.append(nm)
    sv.children.append(forget)
    sv.children.append(hidden(cards_spacer('wi_gap0', ST.GAP_H)))
    for k in range(WI_FIELDS):
        row = hidden(wf_row(f'wi_f{k}', 'mid'))
        row.set('sensitive', 'false')
        row.children = [wi_text(f'wi_fl{k}', x, WI_LABEL_W, '', 21, INK_RGB, 'left'), wi_text(f'wi_fv{k}', WI_VALUE_X, ST.RIGHT - WI_VALUE_X, '', WI_VALUE_PX, ST.GREY, 'right'), wf_hair(f'wi_fh{k}', WF_HDR_X)]
        sv.children.append(row)
    sv.children.append(hidden(cards_spacer('wi_gap1', ST.GAP_H)))
    sv.children.append(auto)
    sv.children.append(hidden(cards_spacer('wi_gap2', ST.GAP_H)))
    sv.children.append(join)
    sv.children.append(cards_spacer('pod_end', ST.END_H))
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/wifipage.c shows it while the list is scrolled
    return root


# One paired device's page (patch/btpage.c bd_open, docs/modules/bluetooth.md "The device page"): the info page's cards, pieces and gaps. Connect / Disconnect (one centred row), Headset Volume with its two round keys
# (only while the device is the connected one and the volume can be set), Forget This Device (one centred row), the card gaps between them; the payload shows, hides and moves them (display order again). The navbar's
# title is the device's name, and the whole name goes above the cards when the title is cut (the same two lines as the Wi-Fi info page).
BD_KEY_PX, BD_KEY_GAP, BD_KEY_PAD = (38, 34), 10, 4   # a key's pill (the images pod_ic_btvol_*), the gap between the two, the touch area's room around the pill's width


def bd_key(name, x, icon):
    """A Headset Volume key: a button with its own images (normal, pressed), its touch area the row's height by the pill's width + 2 x BD_KEY_PAD, the pill centred in it."""
    import pod_settings as ST
    return Widget('button', x - BD_KEY_PAD, 0, BD_KEY_PX[0] + 2 * BD_KEY_PAD, ST.ROW_H, [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                  ('style:pressed:icon', icon + '_down'), ('style:normal:icon', icon), ('style:over:icon', icon)])


def build_btdevice_page(page):
    import pod_settings as ST
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'btdevice_listview')
    sv = lv.children[0]
    sv.set('name', 'btdevice_scrollview')
    x = ST.CM + ST.PAD
    centred = lambda name, english, rgb=INK_RGB: wi_text(name, x, ST.CARD_W - 2 * ST.PAD, english, 21, rgb, 'center')
    link = hidden(wf_row('bd_row_link', 'single'))
    link.children = [centred('bd_link_t', 'Connect')]
    vol = hidden(wf_row('bd_row_vol', 'single'))   # not a tap target itself: the keys are; its pressed picture is its normal one
    for st in ('over', 'pressed', 'focused'): styled(vol, (st,), 'bg_image', ST.piece_images('single')[0])
    up_x = ST.RIGHT - BD_KEY_PX[0]
    dn_x = up_x - BD_KEY_GAP - BD_KEY_PX[0]
    vol.children = [wf_label('bd_vol_t', x, dn_x - BD_KEY_PAD - 4 - x, 'Headset Volume'), hidden(bd_key('bd_vol_dn', dn_x, 'pod_ic_btvol_dn')), hidden(bd_key('bd_vol_up', up_x, 'pod_ic_btvol_up'))]
    forget = hidden(wf_row('bd_row_forget', 'single'))
    forget.children = [centred('bd_forget_t', 'Forget This Device', RED_RGB)]
    sv.children.append(cards_spacer('pod_top', ST.CM))
    for k in range(2):   # the whole name's lines (patch/wifipage.c wf_name_lines)
        nm = hidden(cards_spacer(f'bd_nm{k}', WI_NAME_H))
        nm.children = [label(f'bd_name{k}', ST.CM, 0, ST.CARD_W, WI_NAME_H, '', WK_LINE_PX, ST.GREY, 'center')]
        sv.children.append(nm)
    sv.children.append(link)
    sv.children.append(hidden(cards_spacer('bd_gap0', ST.GAP_H)))
    sv.children.append(vol)
    sv.children.append(hidden(cards_spacer('bd_gap1', ST.GAP_H)))
    sv.children.append(forget)
    sv.children.append(cards_spacer('pod_end', ST.END_H))
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/btpage.c shows it while the list is scrolled
    return root


# The password page (patch/wifipage.c wk_open, docs/modules/wifi.md "The password page"): the navbar, a grey line naming the network, one Settings card holding the "Password" label, the keyboard's own field
# (kb_field with its text, hint, caret and clear button, found by keyboard_attach by name; the clear button never shows for a password) and the eye button, an error line under the card, and the keyboard's
# pad, strip and pop-up. Everything above the candidate strip (y 234): the card ends at y 152, the error line at 182. There is no Join button: the keyboard's action key reads Join.
WK_LINE_Y, WK_LINE_H, WK_LINE_PX = 62, 22, 15      # the grey line under the navbar (centred, UTF-8, cut with an ellipsis by the payload)
WK_CARD_X, WK_CARD_Y, WK_CARD_W, WK_CARD_H, WK_CARD_R = 10, 100, 300, 52, 12
WK_LABEL_X, WK_LABEL_W, WK_LABEL_PX = 24, 118, 21   # "Password", the Settings rows' label (118 px: French's "Mot de passe" is the longest, 117)
WK_FIELD_X, WK_FIELD_W, WK_FIELD_PX, WK_CARET_Y = 144, 120, 18, 15   # the field: text from x 144, 118 px of room (a dot or a letter is cut with an ellipsis, its end shown); the caret 22 px high centred in the row
WK_EYE_X, WK_EYE_W = 264, 46                        # the eye button's touch area (the 22 px glyph is centred in it: x 276..298)
WK_ERR_Y, WK_ERR_H, WK_ERR_PX = 160, 22, 18


def trail_field_w(x):
    """The width of a kb_field that starts at x on a card with an eye button: its clear button's disc is centred on the eye's glyph (x 287), so the trailing controls of the card's rows are one column."""
    return WK_EYE_X + WK_EYE_W // 2 + PK.FIELD_CLEAR_W // 2 - x


def kb_field_widget(x, y, w, h, caret_y):
    """The keyboard's own field (kb_field with its hint, text, caret and clear button, found by keyboard_attach by name) at x, y, w x h; the caret_y is relative to the field. It has no fill: the card is under it."""
    return text_field(x, y, w, h, '#00000000', 0, 0, w, WK_FIELD_PX, PK.KB_GREY, PK.KB_INK, caret_y, w - PK.FIELD_CLEAR_W, PK.FIELD_CLEAR_W,
                      sensitive=True)   # the clear button inside it needs it: stock's hit test does not look into an insensitive parent (a page puts its eye button after the field, so over it)


def eye_button(name, x, y, w, h):
    return Widget('button', x, y, w, h, [('name', name), ('enable', 'true'), ('style', 'img_btn_style'),
                  ('style:pressed:icon', 'wf_eyeoff'), ('style:normal:icon', 'wf_eyeoff'), ('style:over:icon', 'wf_eyeoff')])


def build_wifipass_page(page):
    """The password page's widgets, in paint order: the navbar, the grey line, the card with its label, the keyboard's field, the eye, the error line, the pad."""
    import pod_settings as ST
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    line = label('wk_line', WK_CARD_X, WK_LINE_Y, WK_CARD_W, WK_LINE_H, '', WK_LINE_PX, ST.GREY, 'center')
    line.set('sensitive', 'false')
    styled(line, ('normal',), 'text_align_v', 'middle')
    root.children.append(line)
    root.children.append(kb_view('wk_card', WK_CARD_X, WK_CARD_Y, WK_CARD_W, WK_CARD_H, ST.CARD_RGB, ST.CARD_R))
    lab = label('wk_label', WK_LABEL_X, WK_CARD_Y, WK_LABEL_W, WK_CARD_H, '', WK_LABEL_PX, INK_RGB, 'left')
    lab.set(*pod_i18n.text_prop('Password'))
    lab.set('sensitive', 'false')
    styled(lab, ('normal',), 'text_align_v', 'middle')
    root.children.append(lab)
    root.children.append(kb_field_widget(WK_FIELD_X, WK_CARD_Y, WK_FIELD_W, WK_CARD_H, WK_CARET_Y))
    root.children.append(eye_button('wk_eye', WK_EYE_X, WK_CARD_Y, WK_EYE_W, WK_CARD_H))
    err = hidden(label('wk_err', WK_LABEL_X, WK_ERR_Y, WK_CARD_W - 2 * (WK_LABEL_X - WK_CARD_X), WK_ERR_H, '', WK_ERR_PX, ST.GREY, 'left'))
    err.set(*pod_i18n.text_prop('Incorrect password'))
    styled(err, ('normal',), 'text_align_v', 'middle')
    root.children.append(err)
    root.children += keyboard_pad_widgets()
    return root


# The Join Wi-Fi Network page (patch/wifipage.c wo_open, docs/modules/wifi.md "The Other Network flow"; the iOS sheet's layout): the navbar (Back = cancel), no grey line, two Settings cards: card 1 holds the
# Name row, card 2 the Security row (value and chevron) and, under a hairline, the Password row (card 2 is the one-row card while Security is None: the payload shows wo_card1a or wo_card1b). Rows are 48 px
# (not 52) so that the Password row, the error line under card 2 and nothing else end above the candidate strip (y 234): name y 56..104, gap 12, Security 116..164, Password 164..212, error 212..232.
# The keyboard has one field, kb_field, which the payload moves to the row being typed in (Name at x 100, Password at x 144, as the password page's); the other row shows its value in a static label
# (wo_name_v, or wo_name_h, the grey placeholder, while the name is empty; wo_pass_v, dots or the text). Three buttons take the taps on the rows (wo_hit_*), insensitive widgets pass them through.
WO_ROW_H, WO_NAME_Y, WO_SEC_Y, WO_PASS_Y, WO_ERR_Y, WO_ERR_H, WO_ERR_PX = 48, 56, 116, 164, 212, 20, 16
WO_NAME_X, WO_NAME_TW = 100, 156                            # the Name field: room for the text before the clear button
WO_NAME_FIELD_W = trail_field_w(WO_NAME_X)                  # (205: the clear button's disc under the eye of the Password row)
WO_PASS_X, WO_PASS_TW = 144, 118                            # the Password field (the password page's): the same container, 118 px of text room, the eye button right of it
WO_CARET_Y = (WO_ROW_H - 22) // 2
WO_LABEL_W = 118


def build_wifiother_page(page):
    import pod_settings as ST
    from mod_icons import CARD_CHEVRON
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    root.children.append(kb_view('wo_card0', WK_CARD_X, WO_NAME_Y, WK_CARD_W, WO_ROW_H, ST.CARD_RGB, ST.CARD_R))
    root.children.append(hidden(kb_view('wo_card1a', WK_CARD_X, WO_SEC_Y, WK_CARD_W, WO_ROW_H, ST.CARD_RGB, ST.CARD_R)))
    root.children.append(kb_view('wo_card1b', WK_CARD_X, WO_SEC_Y, WK_CARD_W, 2 * WO_ROW_H, ST.CARD_RGB, ST.CARD_R))
    def row_label(name, y, english, w=WO_LABEL_W):
        lab = label(name, WK_LABEL_X, y, w, WO_ROW_H, '', WK_LABEL_PX, INK_RGB, 'left')
        lab.set(*pod_i18n.text_prop(english))
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
        return lab
    def value_label(name, x, y, w, colour, english=None, align='left'):
        lab = label(name, x, y, w, WO_ROW_H, '', WK_FIELD_PX, colour, align)
        if english: lab.set(*pod_i18n.text_prop(english))
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
        return lab
    root.children.append(row_label('wo_name_l', WO_NAME_Y, 'Name', 76))
    root.children.append(row_label('wo_sec_l', WO_SEC_Y, 'Security', 150))   # (Polish's Zabezpieczenia is 132 px; the value is right aligned and never reaches it)
    root.children.append(row_label('wo_pass_l', WO_PASS_Y, 'Password'))
    vx, vw = ST.value_box()
    root.children.append(value_label('wo_sec_v', vx + vw - ST.VALUE_MAX, WO_SEC_Y, ST.VALUE_MAX, ST.GREY, align='right'))
    ax, ay, aw, ah = ST.accessory('chevron')
    root.children.append(wf_image('wo_chev', ax, WO_SEC_Y + (WO_ROW_H - 1 - ah) // 2, aw, ah, CARD_CHEVRON[0]))
    hair = Widget('view', WK_LABEL_X, WO_PASS_Y - 1, ST.CM + ST.CARD_W - WK_LABEL_X, 1, [('name', 'wo_hair'), ('sensitive', 'false')])
    for st in STATES: styled(hair, (st,), 'bg_color', ST.CARD_HAIR_RGB)
    root.children.append(hair)
    root.children.append(hidden(value_label('wo_name_v', WO_NAME_X, WO_NAME_Y, WO_NAME_TW, PK.KB_INK)))
    root.children.append(hidden(value_label('wo_name_h', WO_NAME_X, WO_NAME_Y, WO_NAME_TW, PK.KB_GREY, 'Network Name')))
    root.children.append(hidden(value_label('wo_pass_v', WO_PASS_X, WO_PASS_Y, WO_PASS_TW, PK.KB_INK)))
    for name, y, w in (('wo_hit_name', WO_NAME_Y, WK_CARD_W), ('wo_hit_sec', WO_SEC_Y, WK_CARD_W), ('wo_hit_pass', WO_PASS_Y, WK_EYE_X - WK_CARD_X)):
        root.children.append(Widget('button', WK_CARD_X, y, w, WO_ROW_H, [('name', name), ('enable', 'true'), ('style', 'img_btn_style')]))
    root.children.append(kb_field_widget(WO_NAME_X, WO_NAME_Y, WO_NAME_FIELD_W, WO_ROW_H, WO_CARET_Y))
    root.children.append(eye_button('wo_eye', WK_EYE_X, WO_PASS_Y, WK_EYE_W, WO_ROW_H))
    err = hidden(label('wo_err', WK_LABEL_X, WO_ERR_Y, WK_CARD_W - 2 * (WK_LABEL_X - WK_CARD_X), WO_ERR_H, '', WO_ERR_PX, ST.GREY, 'left'))
    err.set(*pod_i18n.text_prop('Incorrect password'))
    styled(err, ('normal',), 'text_align_v', 'middle')
    root.children.append(err)
    root.children += keyboard_pad_widgets()
    return root


# The Security page (patch/wifipage.c ws_open): a Settings-style choice list that the Join Wi-Fi Network page opens as a picker: None, WPA2/WPA3, WPA3 in one card (the pieces and the neutral check of the
# picker pages); the payload puts the check on the page's current choice, a tap sets it and goes back. The rows are the asset's, the payload only binds them. Enterprise joins the list with the enterprise phase.
WS_ROWS = ('None', 'WPA2/WPA3', 'WPA3')
WS_DEFAULT = 1


def build_wifisec_page(page):
    import pod_settings as ST
    from mod_icons import CARD_CHECK
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    lv = stock_list([], True)
    lv.set('name', 'wifisec_listview')
    sv = lv.children[0]
    sv.set('name', 'wifisec_scrollview')
    sv.children.append(cards_spacer('pod_top', ST.CM))
    x, w = ST.label_box('check', False)
    for k, name in enumerate(WS_ROWS):
        row = wf_row(f'ws_row{k}', 'top' if k == 0 else 'bot' if k == len(WS_ROWS) - 1 else 'mid')
        row.children = [wf_label(f'ws_label{k}', x, w, name)]
        ax, ay, aw, ah = ST.accessory('check')
        chk = Widget('image', ax, ay, aw, ah, [('name', f'ws_check{k}'), ('image', CARD_CHECK[0]), ('draw_type', 'icon'), ('sensitive', 'false')])
        if k != WS_DEFAULT: chk = hidden(chk)
        row.children.append(chk)
        if k < len(WS_ROWS) - 1: row.children.append(wf_hair(f'ws_hair{k}', x))
        sv.children.append(row)
    sv.children.append(cards_spacer('pod_end', ST.END_H))
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))
    return root


def build_page(page):
    if page.kind == 'bluetooth':
        return build_bluetooth_page(page)
    if page.kind == 'btdevice':
        return build_btdevice_page(page)
    if page.kind == 'wifiother':
        return build_wifiother_page(page)
    if page.kind == 'wifisec':
        return build_wifisec_page(page)
    if page.kind == 'songinfo':
        return build_songinfo_page(page)
    if page.kind == 'wifipass':
        return build_wifipass_page(page)
    if page.kind == 'wifi':
        return build_wifi_page(page)
    if page.kind == 'wifiinfo':
        return build_wifiinfo_page(page)
    if page.kind == 'radio':
        return build_radio_page(page)
    if page.kind == 'radioinfo':
        return build_radioinfo_page(page)
    if page.kind == 'radionp':
        return build_radionp_page(page)
    if page.kind == 'folders':
        return build_folders_page(page)
    if page.kind == 'lupick':
        return build_lupick_page(page)
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
        return build_grid_page(page, toggle=None, coverflow=False, albums=True, az=True)   # the Albums page: its list mode has the A-Z furniture (patch/azlist.c)
    if page.kind == 'podcasts':
        return build_podcasts_page(page)
    if page.kind == 'peq':
        return build_peq_page(page)
    if page.kind == 'peqpage':
        return build_peqpage_page(page)
    if page.kind == 'peqband':
        return build_peqband_page(page)
    if page.kind == 'peqlib':
        return build_peqlib_page(page)
    if page.kind in ('tenband', 'tencurve', 'tenpreamp'):
        return build_cards_page(page)   # (the payload binds the rows by name: patch/tenband.c; the Preamp page's rows have no text in the asset)
    if page.kind == 'books':
        return build_books_page(page)
    if page.kind == 'playlists':
        return build_playlists_page(page)
    if page.kind == 'songs':
        return build_songs_page(page)
    if page.kind == 'search':
        return build_search_page(page)
    if page.kind == 'autoeq':
        return build_autoeq_page(page)
    if page.kind == 'pcfind':
        return build_pcfind_page(page)
    if page.kind == 'ndlogin':
        import pod_ndserver; return pod_ndserver.build_login(page)
    if page.kind == 'ndserver':
        import pod_ndserver; return pod_ndserver.build(page)
    if page.kind == 'ndroot':
        import pod_nd; return pod_nd.build(page)
    if page.kind == 'ndfolders':
        import pod_nd; return pod_nd.build_folders(page)
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
    if page.kind == 'idlelyrics':
        return build_idlelyrics_page(page)
    if page.kind == 'vinyl':
        return build_vinyl_page(page)
    if page.kind == 'vu':
        return build_vu_page(page)
    if page.kind == 'onlineart':
        return build_onlineart_page(page)
    if page.kind == 'update':
        return build_update_page(page)
    if page.kind == 'relnotes':
        return build_relnotes_page(page)
    if page.kind == 'lockwall':
        return build_lockwall_page(page)
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
        sv.children.append(pins())   # the Home pins (the payload puts them first, above the rows, and shows them when something is pinned)
        sv.children.append(daily())   # after the rows, before the shelf: the Daily Mix card (the payload moves it below the last shown row and shows it when there is a mix)
        sv.children.append(shelf())   # then the shelf (the payload moves it below the last shown row and shows it when there are albums to show)
        sv.children.append(hidden(Widget('view', 0, len(page.rows) * ROW_H, sv.w, MB_PAD, [('name', 'pod_pad')])))   # last child; the payload shows it with the bar
        root.children.append(cache_pill())   # (hidden; the bar stays the last child: it paints over everything)
        root.children.append(minibar())
        root.children.extend(row_menu(album=True))   # the pins' / Recently Played long press sheet: five rows for an album (shrunk to three for playlist/artist, two for song), above the bar
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


def add_battery_label(rootfs):
    """The Battery Percentage's number (patch/battery.c): hidden, in the battery's body, in the status bar and in the pull-down's own bar (tools/statusbar.py battery_parts;
    the lock screen's is tools/mod_lockscreen.py). The payload sets its text."""
    import statusbar
    from modlib import edit_ui
    edit_ui(os.path.join(rootfs, SYSTEM_BAR), lambda root: statusbar.battery_parts(root))
    edit_ui(os.path.join(rootfs, 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), lambda root: statusbar.battery_parts(root, '_dd'))


TIDAL_SEARCH = f'{UI}/tidal/tidal_serach_page.bin'
TK = cdefs.defines(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patch', 'tidalkb.h'))
TK_HINT_RGB = SUB_RGB   # the stock edit's tips_text_color


def tidal_field():
    """The keyboard's field inside the Tidal search bar (patch/tidalkb.c): kb_field with its hint, text, caret and clear button, transparent so that the stock bar shows, in the stock edit's
    font size and colours. Sensitive: the clear button inside it needs it, and a view has no on_event of its own, so a tap on it still reaches the bar's list_item as a click."""
    w, tx = TK['TK_FIELD_W'], TK['TK_TEXT_X']
    return text_field(TK['TK_FIELD_X'], 0, w, TK['TK_FIELD_H'], '#00000000', 0, tx, w - tx, TK['TK_PX'], TK_HINT_RGB, PK.KB_INK, TK['TK_CARET_Y'], w - TK['TK_CLEAR_W'], TK['TK_CLEAR_W'], sensitive=True)


def add_tidal_keyboard(rootfs):
    """Tidal > Search with our keyboard embedded (patch/tidalkb.c, docs/modules/tidalkb.md): the keyboard's field goes into the search bar (listitem_ssid) over the stock edit, and the pad, the
    candidate strip and the pop-up (keyboard_pad_widgets) end the window, over the history and the results. The window fills the 450 px client area (0, 0, 0, 0), so the pad's bottom is the
    screen's. The stock layout this relies on is asserted."""
    def edit(root):
        bar = root.find('listitem_ssid')
        assert root.name == 'tidal_search_page' and (root.x, root.y, root.w, root.h) == (0, 0, 0, 0), 'unexpected Tidal search page layout'
        assert bar is not None and (bar.x, bar.y, bar.w, bar.h) == (33, 6, 240, 38) and bar.type == 'list_item' and root.children.count(bar) == 1, 'unexpected Tidal search bar'
        assert [(c.type, c.name, c.x, c.y, c.w, c.h) for c in bar.children] == [('edit', 'search_edit', 15, 0, 210, 38)], 'unexpected Tidal search bar children'
        assert root.find('kb_pad') is None and root.find('kb_field') is None and all(root.find(n) for n in ('view', 'tab_control')), 'unexpected Tidal search page widgets'
        assert TK['TK_FIELD_X'] + TK['TK_FIELD_W'] <= bar.w and TK['TK_FIELD_H'] == bar.h
        bar.children.append(tidal_field())
        root.children += keyboard_pad_widgets()
    from modlib import edit_ui
    edit_ui(os.path.join(rootfs, TIDAL_SEARCH), edit)


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

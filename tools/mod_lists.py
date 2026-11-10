#!/usr/bin/env python3
"""iPod-style library lists for the Shanling M1 Plus (asset-only: page styles and ui/*.bin).

The library pages (Folders, Artists/Genres/Composers, Songs, Albums, Album detail, Playlists, Search,
the Now Playing "jump" list) and the dialogs they open are restyled to the look of the M1+ Music menu:
black page, rows that are stock `list_item_style` tiles, white left-aligned titles (21 px where the
row's label box is tall enough), grey secondary text, the stock right chevron, one pressed colour.

Almost every row on these pages is built by demo's code, not by the asset (docs/ui.md):
`folder_create_tablerow`, `localclass_create_tablerow` and `music_create_tablerow` make a table_row
(310 x 64/60) holding a button themed "btn_tablerow_style" (310 x 60/56, layout
default(r=1,c=0,x=12,s=8)) with a 40 px icon, an hscroll_label themed "srlabel_item_white_style" and
a "btn_rightarrow_style" chevron; the album, album-detail, playlist and search rows are list_items
themed "list_item_style". Their geometry is code, so it stays; their look is whatever those style
names resolve to. This AWTK resolves a style in the window's own theme first, then in the global
theme (style_const @0x6d3038 via widget_get_window_theme), and a window's theme is
styles/<window name>.bin (window_base @0x6761dc: assets_manager_ref(STYLE, theme or name)).
So each page gets a page theme here, derived at build time from the tree's styles/default.bin (the
theme mod owns that file; run this mod after it and the lists follow its colours):

  btn_tablerow_style       every state copied from default, bg_color taken from list_item_style's
                           same state: the table rows (Folders, Artists, Songs, jump list) always
                           match the list_item_style rows (Albums, Playlists, Search, M1+ Music menu)
  srlabel_item_white/gold20_style  21 px on the single-line pages (Folders, Artists; label box
                           56-60 px tall); the two-line rows keep 20 px in their 20 px boxes
  srlabel_item_gray26_style  defined (copy of srlabel_item_gray18_style): stock creates the Songs
                           and jump-list artist line with this name, which no theme defines, so it
                           drew #444444 on #131313 until the row's data loaded
  playlist_btnitem_style   Import/Export tiles: list_item_style colours (stock pressed #2E2A19)
  srlabel_leftwhite22_style  the navbar title of the queue (jump list), the song lists (allmusic_page: Songs,
                           a playlist's songs), Folders, Artists / Genres / Composers (localclass_page) and
                           the stock Playlists page, 22 -> 20 px as every navbar title (docs/modules/navbar.md)
  btn_tab_style            Search tabs: grey text on the row colour, the active tab white with a
                           3 px accent underline (stock: a solid accent block, #FE7E40)

and ui edits: the Songs index letter (view_letter) becomes a dark rounded square with a white
letter (stock: a light-grey disc, black letter); the add-to dialog presses in the list pressed
colour (stock olive #2E2A19), and the confirm and sort dialogs follow it too (stock already uses
the stock list pressed colour #362221 there, so they only change if the theme's does).
Style colours are stored as R, G, B, A bytes.

Page themes are written for the default asset theme (stock's theme1 is removed from the rootfs,
docs/modules/theme.md). Nothing else changes: every
widget the app looks up keeps its name, type and geometry; no window gets an open/close animation
(docs/ui.md: the "play from here" handlers loop on navigator_back until Now Playing is on
top, which an animated close would turn into a hang).

Usage: mod_lists.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import argparse, os, stat, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_style, awtk_ui
from awtk_style import T_INT32, T_UINT32
from modlib import clone_workdir, edit_ui

RAW = 'rootfs/release/assets/default/raw'
STYLE_MODE = 0o744                           # stock styles/*.bin mode
STYLE_MTIME = 1750924035                     # a stock asset mtime: added files build deterministically
TITLE_PX = 21                                # the M1+ Music menu's row text (srlabel_leftwhite21_style)
NAVBAR_PX = 20                               # navbar titles (mod_polish.TITLE_NEW)

# page (window name == theme name) -> page-theme recipes, in the order they are applied
PAGES = {
    'folder_page':         ('rows', 'title', 'navtitle'),
    'localclass_page':     ('rows', 'title', 'navtitle'),
    'allmusic_page':       ('rows', 'gray26', 'navtitle'),
    'playerjumpinfo_page': ('rows', 'gray26', 'navtitle'),
    'playlist_page':       ('tiles', 'navtitle'),
    'playqueue_dialog':    ('queue',),
    'search_page':         ('tabs',),
}
# ui/*.bin edits (relative to raw/ui of the default theme)
UI_EDITS = ('allmusic_page.bin', 'dialog/confirminfo_dialog.bin', 'dialog/sortselect_dialog.bin',
            'dialog/batchadd_dialog.bin', 'dialog/playqueue_dialog.bin', 'dialog/playmore_dialog.bin')
GEOMETRY_EDITS = ('dialog/playqueue_dialog.bin',)   # these change widget sizes on purpose (the row template)
ADD_EDITS = ('dialog/playmore_dialog.bin',)         # these add widgets (the More rows, docs/modules/playmore.md): every stock widget stays, at its place (but the speed row's)
PM_HIGHLIGHT = 'default(alpha=130)'                 # the AWTK dialog highlighter: the page under the bottom sheet is dimmed by the window manager (set up when the dialog opens)
PM_SPEED = {'scrlabel1': ((48, 8, 60, 20), (48, 8, 96, 20)),          # Playback speed's row: the label, the note under it and the four badges
            'label1_msg': ((48, 31, 138, 14), (48, 31, 262, 14)),     # (stock rectangle, ours): the label gets the room before the badges, which
            'img_1x': ((122, 0, 36, 50), (148, 0, 36, 50)),           # move right (40 px apart, the last one ends at 304 of the 310 px row); the
            'img_1_25x': ((172, 0, 36, 50), (188, 0, 36, 50)),        # note under them may use the whole row
            'img_1_5x': ((222, 0, 36, 50), (228, 0, 36, 50)),
            'img_2x': ((272, 0, 36, 50), (268, 0, 36, 50))}
PM_SHEET = 'pm_sheet'                               # the glass image of page 2 (320 x 250, five rows, top corners r 18; tools/mod_icons.py GLASS_SHEET); page 1's is pm_sheet6 (320 x 300, GLASS_SHEET6): the payload sets the one the page needs on the dialog's first child, the insensitive image pod_glass
PM_GLASS = 'pod_glass'
PM_PRESSED, PM_HAIR = '#FFFFFF10', '#FFFFFF22'      # the rows over it: transparent, pressed 6 % white (a 20 % band, as the album page's, takes the red under 3:1), hairline 13 % white
PM_RED = '#FF5A4F'                                 # the Delete label: >= 4.5:1 on the glass at rest (test/pod/playmore.py; a label in a pressed row stays in its normal state)
QUEUE_ROW, QUEUE_BTN = 44, 40                       # the queue drawer's rows: table row, its button / label (4 px gap)
QUEUE_NAME_PX, QUEUE_NOW_PX = 18, 20                # other rows / the playing row

BORDER_BOTTOM = 8


# ---- AWTK style files: tools/awtk_style.py (styles/*.bin; colours are uint32 0xAABBGGRR) -------
# Lookup is a linear scan over the items (0x662100), so order does not matter; existing order is kept.

def hexcol(v):
    """uint32 colour -> '#RRGGBB' (opaque) or '#RRGGBBAA', the form the ui files use."""
    c = awtk_style.color_to_str(v); return c[:7] if c.endswith('FF') else c

class Theme:
    """awtk_style.Theme plus the (widget, style)-level helpers the recipes use."""
    def __init__(self, th): self.th = th
    @property
    def items(self): return self.th.items
    def states(self, wt, name): return self.th.find(wt, name)
    def find(self, wt, name, state):
        return next(iter(self.th.find(wt, name, state)), None)
    def put(self, s):
        """Replace the entry with the same (widget, style, state), else append."""
        for i, o in enumerate(self.items):
            if (o.widget, o.style, o.state) == (s.widget, s.style, s.state): self.items[i] = s; return
        self.items.append(s)

def copy(s, name=None):
    return awtk_style.Item(s.widget, name or s.style, s.state, list(s.props))

def parse(d):
    th = awtk_style.parse(d)
    assert th.version == 0, 'not an AWTK style file'
    return Theme(th)

# ---- the palette, read from a theme's default.bin --------------------------------------------
def palette(base):
    li = {s.state: s.get('bg_color') for s in base.states('list_item', 'list_item_style')}
    assert li.get('normal') is not None and li.get('pressed') is not None, 'default.bin has no list_item_style'
    gold = base.find('hscroll_label', 'srlabel_item_gold20_style', 'normal')
    gray = base.find('hscroll_label', 'srlabel_item_gray18_style', 'normal')
    assert gold and gray, 'default.bin lacks the stock row text styles'
    return dict(row=li, accent=gold.get('text_color'), muted=gray.get('text_color'),
                white=awtk_style.color_from_str('#FFFFFF'), clear=awtk_style.color_from_str('#00000000'))

# ---- page-theme recipes -------------------------------------------------------------------------
def r_rows(page, base, pal):
    """btn_tablerow_style = default's, with list_item_style's background in each state."""
    src = base.states('button', 'btn_tablerow_style')
    assert src, 'default.bin has no btn_tablerow_style'
    for s in src:
        n = copy(s); n.set('bg_color', pal['row'].get(s.state, pal['row']['normal']), T_UINT32); page.put(n)

def r_title(page, base, pal):
    for name in ('srlabel_item_white_style', 'srlabel_item_gold20_style'):
        src = base.states('hscroll_label', name)
        assert src, f'default.bin has no {name}'
        for s in src:
            n = copy(s); n.set('font_size', TITLE_PX, T_UINT32); page.put(n)

def r_gray26(page, base, pal):
    assert not base.states('hscroll_label', 'srlabel_item_gray26_style'), 'gray26 is defined now: drop this recipe'
    for s in base.states('hscroll_label', 'srlabel_item_gray18_style'):
        page.put(copy(s, 'srlabel_item_gray26_style'))

def r_navtitle(page, base, pal):
    """The navbar title the pages' builders make with srlabel_leftwhite22_style (the jump list, Songs, Folders, Artists, Playlists: 22 px
    where every other page's title is 20 px since mod_polish): the same white at the navbar size."""
    src = base.states('hscroll_label', 'srlabel_leftwhite22_style')
    assert src, 'default.bin has no srlabel_leftwhite22_style'
    for s in src:
        n = copy(s); n.set('font_size', NAVBAR_PX, T_UINT32); page.put(n)

def r_tiles(page, base, pal):
    src = page.states('button', 'playlist_btnitem_style')
    assert src, 'playlist page theme has no playlist_btnitem_style'
    for s in src:
        s.set('bg_color', pal['row'].get(s.state, pal['row']['normal']), T_UINT32)

def r_tabs(page, base, pal):
    """Search tabs: grey text on the row colour; the active tab white over a 3 px accent line."""
    src = page.states('tab_button', 'btn_tab_style')
    assert len(src) == 10, 'unexpected search tab styles'
    for s in src:
        active = s.state.endswith('_of_active')
        pressed = s.state.startswith('pressed')
        s.set('bg_color', pal['row']['pressed' if pressed and not active else 'normal'], T_UINT32)
        s.set('text_color', pal['white'] if active or pressed else pal['muted'], T_UINT32)
        if active:
            s.set('border', BORDER_BOTTOM, T_INT32); s.set('border_width', 3, T_UINT32)
            s.set('border_color', pal['accent'], T_UINT32)
        else:
            s.set('border_color', pal['clear'], T_UINT32)

def r_queue(page, base, pal):
    """The queue drawer (ui/dialog/playqueue_dialog.bin, Now Playing's list button on the player's right): its
    rows are labelled by the app's row bind (@0x47a19c): srlabel_item_white_style for every row and
    srlabel_item_gold20_style for the playing one (white in the minimal theme too, so the two were the same).
    Here the other rows are muted 18 px and the playing row white 20 px."""
    for name, px, col in (('srlabel_item_white_style', QUEUE_NAME_PX, pal['muted']), ('srlabel_item_gold20_style', QUEUE_NOW_PX, pal['white'])):
        src = base.states('hscroll_label', name)
        assert src, f'default.bin has no {name}'
        for s in src:
            n = copy(s); n.set('font_size', px, T_UINT32); n.set('text_color', col, T_UINT32); page.put(n)

RECIPES = {'rows': r_rows, 'title': r_title, 'gray26': r_gray26, 'navtitle': r_navtitle, 'tiles': r_tiles, 'queue': r_queue, 'tabs': r_tabs}


def style_rels():
    """(page, rel path under rootfs/) of every page theme this mod writes."""
    return [(p, f'release/assets/default/raw/styles/{p}.bin') for p in PAGES]

def added_rels(stock_rootfs):
    """Page themes that are new files (absent in the stock rootfs): fwtool --allow-added list."""
    return [rel for _, rel in style_rels() if not os.path.exists(os.path.join(stock_rootfs, rel))]

def write_file(path, data, existed):
    if existed:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        os.chmod(path, mode | 0o200); open(path, 'wb').write(data); os.chmod(path, mode)
    else:
        open(path, 'wb').write(data); os.chmod(path, STYLE_MODE); os.utime(path, (STYLE_MTIME, STYLE_MTIME))

def read(path):
    return open(path, 'rb').read() if os.path.exists(path) else None

def build_page_themes(work):
    # Read every source before writing anything: a page without its own file falls back to
    # default's file as it was before this mod.
    sources = {}
    for page, rel in style_rels():
        own = read(os.path.join(work, 'rootfs', rel))
        sources[rel] = (own is not None, own if own is not None else
                        read(os.path.join(work, RAW, 'styles', f'{page}.bin')))
    report = []
    for page, rel in style_rels():
        base_path = os.path.join(work, RAW, 'styles', 'default.bin')
        base_raw = read(base_path)
        assert base_raw, f'{base_path} missing'
        base = parse(base_raw)
        assert awtk_style.serialize(base.th) == base_raw, f'{base_path}: style round trip is not byte-exact'
        path = os.path.join(work, 'rootfs', rel)
        existed, old = sources[rel]
        th = parse(old) if old else Theme(awtk_style.Theme())
        if old: assert awtk_style.serialize(th.th) == old, f'{rel}: style round trip is not byte-exact'
        pal = palette(base)
        for r in PAGES[page]: RECIPES[r](th, base, pal)
        new = awtk_style.serialize(th.th)
        assert awtk_style.serialize(awtk_style.parse(new)) == new
        write_file(path, new, existed)
        report.append(f'{rel}: {"edited" if existed else "added"} {len(old) if existed else 0} -> {len(new)} bytes '
                      f'({len(th.items)} styles; {", ".join(PAGES[page])})')
    return report


# ---- ui/*.bin edits -------------------------------------------------------------------------------
def default_palette(work):
    return palette(parse(open(os.path.join(work, RAW, 'styles', 'default.bin'), 'rb').read()))

def each_state(w, prop, value, only=None):
    """Set an inline style prop in every state the widget already styles it in (or `only`)."""
    states = only or sorted({k.split(':')[1] for k, _ in w.props if k.startswith('style:') and k.endswith(':' + prop)})
    assert states, f'{w.name}: no inline {prop}'
    for st in states: w.set(f'style:{st}:{prop}', value)

def edit_allmusic(root, pal):
    """The Songs index letter: a dark rounded square with a white letter, as iPod's."""
    view, label = root.find('view_letter'), root.find('label_letter')
    assert view and label and view.type == 'view' and label.type == 'label' and label in view.children
    view.props = [(k, v) for k, v in view.props if 'bg_image' not in k]
    for st in ('normal', 'disable', 'focused'):
        view.set(f'style:{st}:bg_color', '#262626')
        view.set(f'style:{st}:round_radius', '14')
        view.set(f'style:{st}:border_color', '#3A3A3A')
        view.set(f'style:{st}:border_width', '1')
    each_state(label, 'text_color', '#FFFFFF')

def edit_playmore(root, pal):
    """Now Playing's More dialog (patch/playmore.c, docs/modules/playmore.md): the sheet dims the page under it (the dialog's
    highlight); two rows after listitem6, both in the look of the Add to playlist row: "More" (list_item pod_more: the Extras
    ellipsis glyph, the label, the stock grey chevron-right) and the second page's header (pod_back: the stock chevron-left
    `return`, the label "More"); Delete Song's label in red; the hairlines for the order the payload shows (Go to album first
    has none, A-B repeat is no longer first, the back header has none); Playback speed's row with room for its label. Stock
    widgets keep their names, order and rectangles, but the speed row's (PM_SPEED)."""
    sv, add, first, ab = root.find('playmore_scrollview'), root.find('listitem2'), root.find('listitem4'), root.find('listitem0')
    assert sv and add and first and ab and add in sv.children and root.find('pod_more') is None and root.find('pod_back') is None and root.find('pod_tape') is None and root.find('pod_vinyl') is None and root.find('pod_goep') is None and root.find('pod_art') is None and root.find('pod_sleep') is None, 'unexpected playmore_dialog'
    assert root.type == 'dialog' and root.get('highlight') is None
    root.set('highlight', PM_HIGHLIGHT)
    for name, (stock, ours) in PM_SPEED.items():
        w = root.find(name)
        assert w is not None and (w.x, w.y, w.w, w.h) == stock, f'{name}: unexpected rectangle'
        w.x, w.y, w.w, w.h = ours
    def row(name, children):
        r = awtk_ui.Widget('list_item', 0, 0, 0, 0, [(k, v) for k, v in add.props])
        r.set('name', name)
        r.set('visible', 'false')       # the payload shows it; with the kill switch (or any failure) the dialog is the stock seven rows
        r.set('sensitive', 'false')
        r.children = children
        sv.children.append(r)
        return r
    row('pod_more', [
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_more_icon'), ('draw_type', 'default'), ('image', 'pod_ic_extras'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_more_label'), ('style', 'srlabel_item_white_style')]),
        awtk_ui.Widget('image', 285, 14, 13, 22, [('name', 'pod_more_chev'), ('draw_type', 'default'), ('image', 'right_arrow'), ('sensitive', 'false')])])
    back = row('pod_back', [
        awtk_ui.Widget('image', 14, 14, 13, 22, [('name', 'pod_back_chev'), ('draw_type', 'default'), ('image', 'return'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 40, 15, 200, 20, [('name', 'pod_back_label'), ('style', 'srlabel_item_white_style')])])
    row('pod_tape', [   # page 1, above More: the Cassette Mode page (patch/tape.c); the row's hairline is Add to playlist's (a top line)
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_tape_icon'), ('draw_type', 'default'), ('image', 'pod_ic_tape'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_tape_label'), ('style', 'srlabel_item_white_style')])])
    row('pod_vinyl', [   # page 1, under Cassette Mode: the Vinyl Mode page (patch/vinyl.c); a top hairline like the rows above it
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_vinyl_icon'), ('draw_type', 'default'), ('image', 'pod_ic_vinyl'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_vinyl_label'), ('style', 'srlabel_item_white_style')])])
    goep = row('pod_goep', [   # page 1 of a podcast episode, the first row: the Podcasts page (patch/podcasts.c podcasts_go); no hairline, as the first row
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_goep_icon'), ('draw_type', 'default'), ('image', 'pod_ic_podcasts'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_goep_label'), ('style', 'srlabel_item_white_style')])])
    row('pod_art', [   # page 2, between A-B repeat and Delete: Find Cover & Lyrics (patch/onlineart.c); a top hairline like the rows around it; the payload dims it and takes its touches away while the Wi-Fi is off
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_art_icon'), ('draw_type', 'default'), ('image', 'pod_ic_art'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_art_label'), ('style', 'srlabel_item_white_style')])])
    row('pod_sleep', [   # page 2, under Playback speed: a link to the stock Settings > Power page (the Sleep Timer switch and its hour / minute selectors); a top hairline, the grey chevron-right of a row that opens a page
        awtk_ui.Widget('image', 14, 13, 24, 24, [('name', 'pod_sleep_icon'), ('draw_type', 'default'), ('image', 'pod_ic_sleep'), ('sensitive', 'false')]),
        awtk_ui.Widget('hscroll_label', 48, 15, 200, 20, [('name', 'pod_sleep_label'), ('style', 'srlabel_item_white_style')]),
        awtk_ui.Widget('image', 285, 14, 13, 22, [('name', 'pod_sleep_chev'), ('draw_type', 'default'), ('image', 'right_arrow'), ('sensitive', 'false')])])
    assert first.get('style:normal:border') == 'top' and ab.get('style:normal:border') == 'none'
    goep.set('style:normal:border', 'none')
    first.set('style:normal:border', 'none')
    back.set('style:normal:border', 'none')
    ab.set('style:normal:border', 'top')
    # the glass sheet (pm_sheet, mod_icons.glass_image top corners only): the dialog's image is its whole look (no fill, no #666666 top line:
    # the rim is in the image), the list and its scroll view and every row are transparent over it. Inline styles of this dialog's widgets only.
    lv = root.find('playmore_listview')
    assert root.get('style:normal:bg_color') == '#000000' and root.get('style:normal:border') == 'top' and lv.get('style:normal:bg_color') == '#000000'
    for st in ('normal', 'disable', 'focused'):
        root.set(f'style:{st}:bg_color', '#00000000')
        root.set(f'style:{st}:border', 'none')
        lv.set(f'style:{st}:bg_color', '#00000000'); sv.set(f'style:{st}:bg_color', '#00000000')
    # the glass is the dialog's FIRST child, an insensitive image (drawn under the list): the dialog's own bg_image cannot change with the page (250 px on page 2, 300 on page 1),
    # so the payload sets the image and the size of this one, pm_sheet (page 2's, the kill switch's look) or pm_sheet6
    root.children.insert(0, awtk_ui.Widget('image', 0, 0, 320, 250, [('name', PM_GLASS), ('draw_type', 'default'), ('image', PM_SHEET), ('sensitive', 'false')]))
    for r in sv.children:
        assert r.type == 'list_item' and r.get('style:normal:bg_color') == '#000000' and r.get('style:pressed:border_color') == '#666666', f'{r.name}: unexpected row style'
        for st in ('normal', 'pressed', 'over', 'disable', 'focused'):
            r.set(f'style:{st}:bg_color', PM_PRESSED if st == 'pressed' else '#00000000')
            r.set(f'style:{st}:border_color', PM_HAIR)
    lab = root.find('scrlabel6')
    assert lab and lab.get('style') == 'srlabel_item_white_style' and lab.get('style:normal:text_color') is None
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'): lab.set(f'style:{st}:text_color', PM_RED)

def edit_pressed(root, pal, names, old):
    """Dialog buttons with an inline pressed colour press in the list's pressed colour."""
    new = hexcol(pal['row']['pressed'])
    for n in names:
        w = root.find(n)
        assert w is not None and w.get('style:pressed:bg_color', '').upper() in (old, new.upper()), f'{n}: unexpected pressed colour'
        w.set('style:pressed:bg_color', new)

def edit_playqueue(root, pal):
    """The queue drawer: rows 44 px (stock 64) with a 40 px button and label, the label 18 px (the playing row's
    style makes it 20 white, r_queue), the list's own row colours, a header hairline under the play mode line,
    a quieter left border and the bottom button in the dark button look. The dialog's position, animation, the
    table and every widget name stay."""
    row_bg, row_down = hexcol(pal['row']['normal']), hexcol(pal['row']['pressed'])
    dlg = root.find('playqueue_dialog')
    for st in ('normal', 'disable', 'focused'): dlg.set(f'style:{st}:border_color', '#3A3A3A')
    client, trow, btn, name = (root.find(n) for n in ('queue_table_client', 'queue_table_row', 'btn_table_row', 'scrlabel_name'))
    client.set('row_height', str(QUEUE_ROW))
    trow.h, btn.h, name.h = QUEUE_ROW, QUEUE_BTN, QUEUE_BTN
    for st in ('normal', 'over', 'disable', 'focused'): btn.set(f'style:{st}:bg_color', row_bg)
    btn.set('style:pressed:bg_color', row_down)
    for st in ('normal', 'disable', 'focused'): name.set(f'style:{st}:font_size', str(QUEUE_NAME_PX))
    head, mode = root.find('list_item'), root.find('label_playmode')
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'):
        head.set(f'style:{st}:border', 'bottom'); head.set(f'style:{st}:border_color', '#3A3A3A')
        head.set(f'style:{st}:border_width', '1')
    for st in ('normal', 'disable', 'focused'): mode.set(f'style:{st}:font_size', str(QUEUE_NAME_PX))
    btm = root.find('button')
    for st in ('normal', 'over', 'disable', 'focused'): btm.set(f'style:{st}:bg_color', '#1E1E1E')
    btm.set('style:pressed:bg_color', '#333333')
    for st in ('normal', 'pressed', 'over', 'disable', 'focused'): btm.set(f'style:{st}:font_size', '20')

def ui_edit(rel, root, pal):
    if rel == 'dialog/playqueue_dialog.bin': edit_playqueue(root, pal); return
    if rel == 'allmusic_page.bin': edit_allmusic(root, pal)
    elif rel == 'dialog/confirminfo_dialog.bin': edit_pressed(root, pal, ('btn_cancel', 'btn_enter'), '#362221')
    elif rel == 'dialog/sortselect_dialog.bin': edit_pressed(root, pal, ('button_return',), '#362221')
    elif rel == 'dialog/batchadd_dialog.bin': edit_pressed(root, pal, ('btn_addplaylist', 'btn_addfav'), '#2E2A19')
    elif rel == 'dialog/playmore_dialog.bin': edit_playmore(root, pal)
    else: raise KeyError(rel)

def build_ui(work):
    pal, report = default_palette(work), []
    for rel in UI_EDITS:
        path = os.path.join(work, RAW, 'ui', rel)
        old, new, _ = edit_ui(path, lambda root, rel=rel: ui_edit(rel, root, pal))
        shape = lambda d: [(w.type, w.name, w.x, w.y, w.w, w.h) for w in awtk_ui.parse(d).walk()]
        if rel in ADD_EDITS:
            ours = lambda s: s[1] in ('pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep', PM_GLASS) or s[1].startswith(('pod_more_', 'pod_back_', 'pod_tape_', 'pod_vinyl_', 'pod_goep_', 'pod_art_', 'pod_sleep_'))
            other = lambda s: s[:2] if s[1] in PM_SPEED else s   # the speed row's rectangles are ours (PM_SPEED)
            assert [other(s) for s in shape(new) if not ours(s)] == [other(s) for s in shape(old)], f'{rel}: a stock widget was removed, renamed or moved'
        elif rel in GEOMETRY_EDITS:
            names = lambda d: [(w.type, w.name) for w in awtk_ui.parse(d).walk()]
            assert names(old) == names(new), f'{rel}: a widget was added, removed or renamed'
        else:
            assert shape(old) == shape(new), f'{rel}: a widget was added, removed, renamed or moved'
        report.append(f'default/ui/{rel}: {len(old)} -> {len(new)} bytes')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('out')
    a = ap.parse_args()
    clone_workdir(a.src, a.out)
    pal = default_palette(a.out)   # the tree's default.bin: stock, or the theme mod's when stacked after it
    print('lists: palette from styles/default.bin: row ' + ' / '.join(f'{st} {hexcol(v)}' for st, v in sorted(pal['row'].items()))
          + f', accent {hexcol(pal["accent"])}, muted {hexcol(pal["muted"])}')
    for line in build_page_themes(a.out) + build_ui(a.out): print('lists:', line)

if __name__ == '__main__': main()

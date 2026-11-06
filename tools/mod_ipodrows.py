#!/usr/bin/env python3
"""iPod-style library rows, the asset half (V2.1gB, docs/architecture.md). The code half is the payload
feature 'rows' (patch/rows.c, the pinned demo edits in patch/rows.json, tools/pod.py).

After q2-pod's restyle of the stock list pages (patch/ipod.json, tools/ipod.py): every library row is PITCH = 64 px, its body BODY = 60 px (the
Folders page already is, and its offset maths divides by 64 with a shift, so 64 it is everywhere),
titles 21 px in 24 px boxes, the grey second line 18 px. demo's row constructors make the rows
(patched in demo); what an asset decides is the pitch the lists step by, and the jump list's row
template, which its table clones without any row constructor:

  ui/localclass_page.bin     localclass_table_client row_height 60 -> 64
  ui/allmusic_page.bin       music_table_client row_height 60 -> 64; the template row (rebuilt by
                             code, kept consistent) table_row h 60 -> 64, btn_table_row h 56 -> 60;
                             navigationbar_view y 0 -> 3, h 50 -> 47 (the builder's 44 px buttons
                             centred in the 50 px bar, as the Pod pages' navbar)
  ui/playerjumpinfo_page.bin row_height 60 -> 64; template table_row 310x64, btn_table_row 310x60,
                             view_info w 238, scrlabel_name (0,7,238,24), view_artist at y 33 h 20,
                             scrlabel_artist w 213 (the jump list's rebind sizes view_info 238x60)
  ui/album_page.bin          album_listview default_item_height 60 -> 64
  ui/albuminfo_page.bin      (the plain stock album page, the fallback of ours) navigationbar_view y 0 -> 3, as allmusic_page
  ui/playlist_page.bin       playlist_listview default_item_height 60 -> 64 (its rows are created
                             0 high, so this is their pitch)
  ui/playset/equalizer_page.bin, ui/systemset/specfolder_page.bin
                             Now Playing (and the folder picker's select-all button) onto the Pod
                             navbar's slots, docs/modules/navbar.md

and page themes (derived from the tree's styles as tools/mod_lists.py does; run
after it): srlabel_item_white_style and srlabel_item_gold20_style at 21 px on the pages whose title
boxes are 24 px now (Songs and the other song lists, the jump list, Albums, Playlists,
Search). Folders and Artists have them from the lists step. The grey line stays stock's
srlabel_item_gray18_style (#AAAAAA, 18 px). styles/default.bin is not touched (shared with every
page), nor the stock layout strings in demo.

Usage: mod_ipodrows.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_style, awtk_ui
import mod_lists
from modlib import clone_workdir, edit_ui

PITCH, BODY = 64, 60
NAV_H = 44             # the shared navbar builder's button height (patch/rows.json NAV_H)
STOCK_PITCH, STOCK_BODY = 60, 56
TEXT_W = 238           # x 60 .. 298 in a 310 px row (12 px margins, a 40 px icon + 8)
TITLE = (0, 7, TEXT_W, 24)
SUB_Y, SUB_H = 33, 20
ARTIST_W = TEXT_W - 25  # after the 20 px MQA badge + 5
TITLE_PAGES = ('allmusic_page', 'playerjumpinfo_page', 'album_page', 'playlist_page', 'search_page')
TITLE_PX, ARTIST_PX, META_PX = 22, 18, 15   # the album page's header lines (patch/offsets.inc AH_TITLE_H.. = AB_META in tools/pod_ui.py): what tools/ah_ink.py measures


def one(root, name, kind):
    ws = [w for w in root.walk() if w.name == name]
    assert len(ws) == 1 and ws[0].type == kind, f'{name}: expected one {kind}'
    return ws[0]


def row_height(root, name):
    tc = one(root, name, 'table_client')
    assert tc.get('row_height') == str(STOCK_PITCH), f'{name}: row_height {tc.get("row_height")}'
    tc.set('row_height', str(PITCH))


def item_height(root, name):
    lv = one(root, name, 'list_view')
    assert lv.get('default_item_height') == str(STOCK_PITCH), f'{name}: default_item_height {lv.get("default_item_height")}'
    lv.set('default_item_height', str(PITCH))


def template_row(root):
    row, btn = one(root, 'table_row', 'table_row'), one(root, 'btn_table_row', 'button')
    assert row.h == STOCK_PITCH and btn.h == STOCK_BODY, 'unexpected template row'
    row.h, btn.h = PITCH, BODY
    lay = row.get('self_layout')
    if lay is not None:
        assert lay == f'default(w=100%,h={STOCK_PITCH})', lay
        row.set('self_layout', f'default(w=100%,h={PITCH})')
    return row, btn


def center_navbar(root, page):
    """The shared navbar builder makes NAV_H high buttons at y 0 (patch/rows.json NAV_H); these pages keep their 50 px bar,
    so the bar's view starts (50 - NAV_H) / 2 down: glyphs and title centre at y 25 as on the Pod pages, the bottom line stays at 50."""
    nav = one(root, 'navigationbar_view', 'view')
    assert (nav.x, nav.y, nav.w, nav.h) == (0, 0, 320, 50), f'unexpected {page} navbar'
    nav.y = (50 - NAV_H) // 2
    nav.h = 50 - nav.y


def edit_allmusic(root):
    row_height(root, 'music_table_client')
    template_row(root)
    center_navbar(root, 'allmusic_page')


def edit_jumplist(root):
    row_height(root, 'music_table_client')
    template_row(root)
    info, name = one(root, 'view_info', 'view'), one(root, 'scrlabel_name', 'hscroll_label')
    va, artist = one(root, 'view_artist', 'view'), one(root, 'scrlabel_artist', 'hscroll_label')
    assert (info.w, (name.x, name.y, name.w, name.h)) == (200, (0, 10, 200, 20)), 'unexpected jump list text'
    assert va.get('self_layout') == 'default(x=0,y=30,w=100%,h=26)' and artist.w == 175, 'unexpected jump list artist line'
    info.w = TEXT_W
    name.x, name.y, name.w, name.h = TITLE
    va.set('self_layout', f'default(x=0,y={SUB_Y},w=100%,h={SUB_H})'); va.y, va.h = SUB_Y, SUB_H
    artist.w = ARTIST_W


def edit_albuminfo(root):
    """The plain stock album page (the fallback of our own, patch/albumpage.c): only its navbar sits as allmusic_page's does, the shared
    builder's NAV_H high buttons centred in the 50 px bar (see edit_allmusic). Nothing else is touched."""
    center_navbar(root, 'albuminfo_page')


NAV_NP = (260, 0, 60, 50)   # the Pod navbar's btn_backtoplayer (tools/pod_ui.py navbar())


def edit_equalizer(root):
    """Settings > Equalizer: Now Playing (270, 50 wide) onto the Pod navbar's slot (docs/modules/navbar.md)."""
    np_ = one(root, 'btn_backtoplayer', 'button')
    assert (np_.x, np_.y, np_.w, np_.h) == (270, 0, 50, 50), 'unexpected equalizer_page Now Playing'
    np_.x, np_.y, np_.w, np_.h = NAV_NP


def edit_specfolder(root):
    """Settings > Update music > a folder picker: Now Playing (279, 41 wide, img_btn_style) onto the Pod navbar's slot and the
    select-all button (229, 38 wide) onto the Pod navbar's NAV_VIEW_X slot (214, 46 wide), as the code-built multi-select
    buttons (an icon_at 5 glyph measured on the device lands on the Pod toggle's columns there)."""
    np_, all_ = one(root, 'btn_backtoplayer', 'button'), one(root, 'navigation_btn_allchoice', 'button')
    assert (np_.x, np_.y, np_.w, np_.h) == (279, 0, 41, 50), 'unexpected specfolder_page Now Playing'
    assert (all_.x, all_.y, all_.w, all_.h) == (229, 0, 38, 50), 'unexpected specfolder_page select-all button'
    np_.x, np_.y, np_.w, np_.h = NAV_NP
    all_.x, all_.w = 214, 46


NAV_BACK = (7, 0, 44, 50)   # the Pod navbar's Back (tools/pod_ui.py NAV_BACK_X, NAV_BACK_W): the glass disc ah_nav_back at x 8 .. 50, y 4 .. 46
USB_SET_ICON = 'ah_nav_set'  # tools/mod_icons.py AH_NAV_PIECES: a glass disc with the Lucide settings glyph, Now Playing's disc columns


def edit_usbmode(root):
    """The USB mode page (USB DAC / USB storage; no navbar): Back (9, 5, 50, 60, stock return chevron) and the DAC settings button
    (274, 0, 46, 53, the dac_set image on a black fill) were on two different rows. Both become the glass discs of our navbar, on its row:
    Back on the Pod navbar's Back, settings on Now Playing's slot (glyph 290, glass 269 .. 311). Stock code only shows / hides them
    (on_usbmodeset_onclick, usbmode_showface: widget_set_visible / widget_set_enable); the charge glyph (236, 10, 20, 30) is centred on
    the discs' row (y 25) already."""
    back, dset = one(root, 'btn_return', 'button'), one(root, 'btn_dacset', 'button')
    assert (back.x, back.y, back.w, back.h) == (9, 5, 50, 60) and back.get('style') == 'img_btn_style', 'unexpected usbmode_page Back'
    assert (dset.x, dset.y, dset.w, dset.h) == (274, 0, 46, 53) and dset.get('style:normal:bg_image') == 'dac_set', 'unexpected usbmode_page DAC settings'
    back.x, back.y, back.w, back.h = NAV_BACK
    for st in ('over', 'normal'): back.set(f'style:{st}:icon', 'ah_nav_back')
    back.set('style:pressed:icon', 'ah_nav_back_down')
    dset.x, dset.y, dset.w, dset.h = NAV_NP
    dset.props = [(k, v) for k, v in dset.props if not k.startswith('style:')]   # the black fill and the bg_image: the disc is the icon now
    dset.set('style', 'img_btn_style')
    for st in ('over', 'normal'): dset.set(f'style:{st}:icon', USB_SET_ICON)
    dset.set('style:pressed:icon', USB_SET_ICON + '_down')


def edit_volume(root):
    """The stock full-page volume screen: the root dialog is a 42 px strip (0, 0, 320, 42) that stock code never resizes, and AWTK does not
    clip children, so its all-sides 1 px black border (painted after the children) lands at y 41 across the page, through the glass Back
    disc (y 34 .. 76). The border becomes transparent; the bg colour and every rectangle are untouched."""
    assert (root.x, root.y, root.w, root.h) == (0, 0, 320, 42), 'unexpected volume_dialog root'
    for st in ('normal', 'disable', 'focused'):
        assert root.get(f'style:{st}:border_color') == '#000000', f'volume_dialog: unexpected {st} border_color'
        root.set(f'style:{st}:border_color', '#00000000')


NAVBAR_UI_EDITS = {
    'dialog/volume_dialog.bin': edit_volume,
    'playset/equalizer_page.bin': edit_equalizer,
    'systemset/specfolder_page.bin': edit_specfolder,
}


# The Settings-type pages (systemset/*, playset/*, audiosetting_page and the keyboard / edit dialogs: every ui file with the stock navbar
# Back) take the glass navbar of our pages: Back the glass disc ah_nav_back and Now Playing the disc ah_nav_np. Back keeps its button
# (0, 0, 80, 50, the whole touch) and navbar_btnreturn_style (icon_at left: the icon centred in a button-high square at x + h / 2 +
# x_offset); x_offset +4 (stock -6) puts the 42 px disc at x 8 .. 50, as the album page's theme does for the code-built Back. Now
# Playing (260, 0, 60, 50, img_btn_style) shows the disc centred: glass 269 .. 311, glyph 290. The title (x 36, under the disc now)
# starts at NAV_TITLE_X, its right end kept but before the bar's next widget (a switch, select-all). The Bluetooth receiver page
# is left as it is (no Bluetooth work).
NAV_TITLE_X, BACK_X_OFFSET = 58, 4   # tools/pod_ui.py NAV_TITLE_X
GLASS_NAV_SKIP = ('bluetoothrecv_page.bin',)
STATES = ('normal', 'pressed', 'over', 'focused', 'disable')


def glass_navbar(root):
    """Restyle the stock navbar's Back / Now Playing in root (see above); returns how many bars it changed."""
    n = 0
    for bar in root.walk():
        backs = [c for c in bar.children if c.name == 'btn_return' and (c.x, c.y, c.w, c.h) == (0, 0, 80, 50)
                 and c.get('style') == 'navbar_btnreturn_style' and c.get('style:normal:icon') == 'return']
        if not backs: continue
        back, = backs
        for st in ('over', 'normal'): back.set(f'style:{st}:icon', 'ah_nav_back')
        back.set('style:pressed:icon', 'ah_nav_back_down')
        for st in STATES: back.set(f'style:{st}:x_offset', str(BACK_X_OFFSET))
        for np_ in bar.children:
            if np_.name == 'btn_backtoplayer' and (np_.x, np_.y, np_.w, np_.h) == NAV_NP and np_.get('style') == 'img_btn_style':
                for st in ('over', 'normal'): np_.set(f'style:{st}:icon', 'ah_nav_np')
                np_.set('style:pressed:icon', 'ah_nav_np_down')
        for t in bar.children:
            if t.name == 'label_title' and t.x == 36:
                right = min([t.x + t.w] + [c.x for c in bar.children if c.y < 50 and c.x > t.x and c not in (t, back)] + [NAV_NP[0]])
                t.x, t.w = NAV_TITLE_X, right - NAV_TITLE_X
        n += 1
    return n


def build_navbar_ui(work):
    report = []
    for rel, fn in NAVBAR_UI_EDITS.items():
        path = os.path.join(work, mod_lists.RAW, 'ui', rel)
        old, new, root = edit_ui(path, fn)
        names = lambda d: [(w.type, w.name) for w in awtk_ui.parse(d).walk()]
        assert names(old) == names(new), f'{rel}: a widget was added, removed or renamed'
        report.append(f'default/ui/{rel}: {len(old)} -> {len(new)} bytes')
    bars = 0
    ui = os.path.join(work, mod_lists.RAW, 'ui')
    for d, _, files in sorted(os.walk(ui)):
        for f in sorted(files):
            if not f.endswith('.bin') or f in GLASS_NAV_SKIP: continue
            path = os.path.join(d, f)
            if b'return' not in open(path, 'rb').read(): continue
            counted = []
            old, new, root = edit_ui(path, lambda r: counted.append(glass_navbar(r)))
            bars += counted[0]
    assert bars >= 45, f'glass navbar: only {bars} stock navbars found'
    report.append(f'glass navbar: {bars} stock navbars (Back, Now Playing, title)')
    return report


UI_EDITS = {
    'albuminfo_page.bin': edit_albuminfo,
    'localclass_page.bin': lambda r: row_height(r, 'localclass_table_client'),
    'allmusic_page.bin': edit_allmusic,
    'playerjumpinfo_page.bin': edit_jumplist,
    'album_page.bin': lambda r: item_height(r, 'album_listview'),
    'playlist_page.bin': lambda r: item_height(r, 'playlist_listview'),
    'usbmode_page.bin': edit_usbmode,
}


def build_ui(work):
    report = []
    for rel, fn in UI_EDITS.items():
        path = os.path.join(work, mod_lists.RAW, 'ui', rel)
        old, new, root = edit_ui(path, fn)
        names = lambda d: [(w.type, w.name) for w in awtk_ui.parse(d).walk()]
        assert sorted(names(new), key=str) == sorted(names(old), key=str), f'{rel}: a widget was added, removed or renamed'
        report.append(f'ui/{rel}: {len(old)} -> {len(new)} bytes')
    return report



def style_rels():
    return [(p, f'release/assets/default/raw/styles/{p}.bin') for p in TITLE_PAGES]


def added_rels(stock_rootfs):
    """Page themes this step adds that neither stock nor the lists step has (fwtool --allow-added)."""
    lists = set(mod_lists.added_rels(stock_rootfs))
    return [rel for _, rel in style_rels() if not os.path.exists(os.path.join(stock_rootfs, rel)) and rel not in lists]


def build_page_themes(work):
    """The 21 px title on TITLE_PAGES, in each page's file (its own, else default's)."""
    sources = {}
    for page, rel in style_rels():
        own = mod_lists.read(os.path.join(work, 'rootfs', rel))
        sources[rel] = (own is not None, own if own is not None else
                        mod_lists.read(os.path.join(work, mod_lists.RAW, 'styles', f'{page}.bin')))
    report = []
    for page, rel in style_rels():
        base_raw = mod_lists.read(os.path.join(work, mod_lists.RAW, 'styles', 'default.bin'))
        base = mod_lists.parse(base_raw)
        assert awtk_style.serialize(base.th) == base_raw, 'default.bin: style round trip is not byte-exact'
        existed, old = sources[rel]
        th = mod_lists.parse(old) if old else mod_lists.Theme(awtk_style.Theme())
        if old: assert awtk_style.serialize(th.th) == old, f'{rel}: style round trip is not byte-exact'
        mod_lists.r_title(th, base, None)
        gray = base.find('hscroll_label', 'srlabel_item_gray18_style', 'normal')
        assert gray and gray.get('font_size') == 18, 'the grey line is not 18 px'
        new = awtk_style.serialize(th.th)
        assert awtk_style.serialize(awtk_style.parse(new)) == new
        path = os.path.join(work, 'rootfs', rel)
        mtime = os.stat(path).st_mtime if existed else None
        mod_lists.write_file(path, new, existed)
        if mtime is not None:   # files the lists step added carry its fixed mtime: keep it (deterministic)
            os.utime(path, (mtime, mtime))
        report.append(f'{rel}: {"edited" if existed else "added"} {len(old) if existed else 0} -> {len(new)} bytes')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('out')
    a = ap.parse_args()
    clone_workdir(a.src, a.out)
    for line in build_ui(a.out) + build_navbar_ui(a.out) + build_page_themes(a.out): print('rows:', line)


if __name__ == '__main__': main()

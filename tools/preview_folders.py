#!/usr/bin/env python3
"""Approximate PIL mock-up of the Folders page (patch/folders.c, docs/modules/folders.md) drawn from the built asset (ui/m1plus_folders.bin) and the payload's constants (patch/folders.c
FO_*, patch/offsets.inc SG_*, LIST_*), on the Songs page's layout model (tools/preview_songs.py: the same pills, glass pieces, select marks and bar): the root list of storages, a folder with
files (Play / Shuffle pills, the wave on what plays), the list scrolled past the large title (the navbar's small title), select mode (marks on folders and audio files), a
folder with long names and an empty one.
Not pixel-exact AWTK (the text is the project's own text model).

  preview_folders.py WORKDIR OUT.png [--lang CODE] [--accent NAME]

WORKDIR is a built tree (work/mod-release).
"""
import argparse, os, re, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui
import preview_icons as PI
import preview_songs as PS
import pod_ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = PS.O
W, WIN, NAV, ROW_H = PS.W, PS.WIN, PS.NAV, PS.ROW_H
GREY, HAIR = PS.GREY, PS.HAIR


def fo_consts():
    """The #define numbers of patch/folders.c (plain integers and the two expressions made of them)."""
    c = dict(O, ROW=pod_ui.ROW_H, POD_ROW_H=pod_ui.ROW_H)
    for line in open(os.path.join(ROOT, 'patch', 'folders.c')):
        m = re.match(r'#define (FO_\w+) (\(?[-\w+*/() ]+?\)?)\s*(?:/\*.*)?$', line.strip())
        if m:
            try: c[m.group(1)] = int(eval(m.group(2).replace('/', '//'), {}, c))
            except Exception: pass
    return c


F = fo_consts()
TEXT_END = F['FO_TEXT_END']
T_LIST, T_SD, T_OTG, T_DIR, T_FILE = 1, 2, 3, 4, 8
ROW_H = F['FO_ICON_Y'] * 2 + F['FO_ICON']   # the menu rows' pitch (52)
ICON = {T_SD: 'fo_ic_sd', T_OTG: 'fo_ic_usb', T_DIR: 'pod_ic_folders', T_LIST: 'pod_ic_playlists', T_FILE: 'fo_ic_file'}


def chevron(im, x, y):
    """pod_make_chevron: a two segment stroke, 10 x 16, grey."""
    d = ImageDraw.Draw(im)
    pts = [(x + 14 / 8, y + 14 / 8), (x + 68 / 8, y + 64 / 8), (x + 14 / 8, y + 114 / 8)]
    d.line(pts, fill=(0x8A,) * 3, width=2, joint='curve')


def rows_top(rows): return O['SG_TOP'] if any(r[0] == T_FILE for r in rows) else F['FO_TOP_PLAIN']


def content(s, title, rows, select=None, playing=()):
    """The whole list as one tall image (window x, content y): the large title, the pills when the folder holds a file, the rows. select: the set of marked names (a mark column
    on audio files, the pills dim); playing: the names of the rows that carry the wave."""
    top = rows_top(rows)
    end = top + len(rows) * ROW_H + F['FO_END'] + (O['SG_BAR_H'] if select is not None else 0)
    im = Image.new('RGBA', (W, max(end, WIN - NAV)), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    s.text(im, O['SG_TITLE_X'], O['SG_TITLE_H'] / 2, PS.fit(s, title, 32, O['SG_TITLE_W']), 32)
    if top == O['SG_TOP']:
        for i, (label, g) in enumerate((('Play', 'sg_play'), ('Shuffle', 'sg_shuffle'))):
            PS.pill(s, im, (O['SG_PILL_X0'], O['SG_PILL_X1'])[i], O['SG_PILL_Y'], PS.tr(s, label), s.img(g), PS.PILL_RGB if select is None else PS.BAND)
    shift = O['SG_SEL_COL'] if select is not None else 0
    tx = F['FO_TEXT_X'] + shift
    on, off = s.img('selected'), s.img('unselect')
    for i, (type, name) in enumerate(rows):
        y = top + i * ROW_H
        d.rectangle((tx, y + ROW_H - 1, W - 11, y + ROW_H - 1), fill=HAIR)
        if select is not None and type in (T_FILE, T_DIR):
            mk = on if name in select else off
            im.alpha_composite(mk, ((O['SG_SEL_COL'] - mk.width) // 2, y + (ROW_H - mk.height) // 2))
        icon = 'pod_ic_cdripper' if name == 'CD Library' else ICON[type]
        im.alpha_composite(s.img(icon), (F['FO_ICON_X'] + shift, y + F['FO_ICON_Y']))
        if name in playing: im.alpha_composite(s.img('pod_ic_nowplaying'), (F['FO_MARK_X'], y + F['FO_ICON_Y']))
        if type != T_FILE: chevron(im, F['FO_CHEV_X'], y + (ROW_H - 16) // 2)
        s.text(im, tx, y + F['FO_TEXT_Y'] + O['LIST_TITLE_H'] / 2, s.clip(name, 21, TEXT_END - tx), 21)
    return im, end


def page(s, title, rows, scroll=0, select=None, playing=(), empty=False, root=False):
    tall, end = content(s, title, rows, select, playing)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    scroll = max(0, min(scroll, end - (WIN - NAV)))
    if empty:
        s.text(im, W / 2, NAV + 160 + 15, PS.tr(s, 'Empty folder'), 20, anchor='m')
    else:
        im.alpha_composite(tall.crop((0, scroll, W, min(tall.height, scroll + WIN - NAV))), (0, NAV))
    if root:   # the list of storages: no Select, Now Playing alone is the glass disc
        ImageDraw.Draw(im).rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0)); PS.glass(s, im, 'ah_nav_back', 7, 44); PS.glass(s, im, 'ah_nav_np', 260, 60)
    else: PS.navbar(s, im, 10 ** 6 if empty else scroll, select, title, genre=True)   # the capsule Select | Now Playing, the small title once the large one has scrolled away (always in an empty folder)
    if select is not None:
        d = ImageDraw.Draw(im); d.rectangle((0, WIN - O['SG_BAR_H'], W - 1, WIN - 1), fill=(0, 0, 0)); d.rectangle((0, WIN - O['SG_BAR_H'], W - 1, WIN - O['SG_BAR_H']), fill=HAIR)
        py = WIN - O['SG_BAR_H'] + (O['SG_BAR_H'] - O['SG_PILL_H']) // 2
        PS.pill(s, im, O['SG_PILL_X0'], py, PS.tr(s, 'Add to Playlist'), s.img('sg_listplus'), w=O['SG_BAR_PILL_W'])
        PS.pill(s, im, O['SG_BAR_PILL_X1'], py, PS.tr(s, 'Delete'), s.img('sg_trash'), w=O['SG_BAR_PILL_W'])
    elif scroll > 0:   # the navbar's fade (img_nb_fade), shown while the list is scrolled
        fade = Image.new('RGBA', (W, 20), (0, 0, 0, 0)); fd = ImageDraw.Draw(fade)
        for y in range(20): fd.rectangle((0, y, W, y), fill=(0, 0, 0, int(160 * (1 - y / 20))))
        im.alpha_composite(fade, (0, NAV))
    return im


ROOT_ROWS = [(T_SD, 'SD'), (T_OTG, 'OTG'), (T_SD, 'CD Library')]
ALBUM_ROWS = [(T_DIR, 'Artwork'), (T_DIR, 'Live 1964'), (T_FILE, '01 So What.flac'), (T_FILE, '02 Freddie Freeloader.flac'), (T_FILE, '03 Blue in Green.flac'),
              (T_FILE, '04 All Blues.flac'), (T_FILE, '05 Flamenco Sketches.flac'), (T_LIST, 'Kind of Blue.m3u8')]
LONG_ROWS = [(T_DIR, 'Disc 1 - The Complete Columbia Studio Recordings 1955-1961'), (T_DIR, '日本語のフォルダ'), (T_FILE, 'A Very Long File Name That Does Not Fit The Row At All (Remastered 2009).flac'),
             (T_FILE, '東京の夜.mp3')]


def extras_panel(s):
    """The Extras / menu page's first rows (stock list rows: a 24 px glyph at x 16, the label at x 56, the stock chevron in its 40 px box at w - 44), for comparison."""
    import mod_icons as M, pod_pages
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    PS.navbar(s, im, 0, None, None)
    s.text(im, O['NAV_TITLE_X'], 25, 'Extras', PI.title_px(s.tree))
    for i, r in enumerate(pod_pages.ITEMS[:8]):
        y = NAV + i * pod_ui.ROW_H
        im.alpha_composite(s.img(M.POD_ROWS[r.label][0]), (M.POD_ICON_X, y + (pod_ui.ROW_H - M.POD_ICON) // 2))
        s.text(im, M.POD_TEXT_X, y + pod_ui.ROW_H / 2, s.clip(PS.tr(s, r.label), 21, pod_ui.CHEV_TEXT_END - M.POD_TEXT_X), 21)
        ra = s.img('right_arrow'); im.alpha_composite(ra, (pod_ui.CHEV_BTN_X, y + (pod_ui.ROW_H - 1 - ra.height) // 2))
        d.rectangle((M.HAIR_X, y + pod_ui.ROW_H - 1, 309, y + pod_ui.ROW_H - 1), fill=HAIR)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    ap.add_argument('--accent', default='neutral', help='an accent (red, orange, ...): every image through palette.render_image, so the pod_ic_ / fo_ic_ glyphs are the accent')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    if a.accent != 'neutral':
        import palette
        img0 = s.img
        s.img = lambda n: palette.render_image(n, img0(n), 'black', a.accent)
    asset = awtk_ui.parse(open(os.path.join(a.workdir, PI.RAW, 'ui', 'm1plus_folders.bin'), 'rb').read())
    assert asset.find('folders_scrollview') is not None and asset.find('btn_select') is not None, 'not the Folders asset'
    root = PS.tr(s, 'Folders')
    panels = [('Extras (the menu rows: glyph x 16, text x 56), for comparison', extras_panel(s)),
              ('Root: the storages (the SD card plays), no Select', page(s, root, ROOT_ROWS, playing={'SD'}, root=True)),
              ('A folder with audio files: pills, the wave', page(s, 'Kind of Blue', ALBUM_ROWS, playing={'03 Blue in Green.flac'})),
              ('Scrolled past the large title: the small one, the fade', page(s, 'Kind of Blue', ALBUM_ROWS * 2, scroll=120, playing={'03 Blue in Green.flac'})),
              ('Select: marks on folders and audio files', page(s, 'Kind of Blue', ALBUM_ROWS, select={'Live 1964', '01 So What.flac', '04 All Blues.flac'})),
              ('Long names, a CJK name', page(s, 'Disc 1 - The Complete Columbia Studio Recordings', LONG_ROWS)),
              ('An empty folder', page(s, 'Artwork', [], empty=True))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()

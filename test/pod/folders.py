"""The Folders page (patch/folders.c, docs/modules/folders.md): the menu row and its fallbacks to the stock folder_page, the built asset (the glass navbar with Select | Now Playing,
the large title and the flat pills in the content view, the select bar), the stock folder state read through the stock functions (folder_enter / folder_back / folder_reload run
on a model of the stock page's layers), the rows painted from the stock list (icons, names, the extension line, the chevron, the wave of what plays, dot names left out), the taps
(a folder goes in, a file plays like the stock row: loadSongList of class 1 and Now Playing), Back (one level up, the root closes), Play and Shuffle, the select mode (audio files
only) with Delete and Add on the stock selection vector, a stock list replaced under the page, and the small title that collapses into the navbar.
The compiled payload runs under Unicorn; the stock folder state is the machine's model."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import preview_folders as PF   # the FO_* numbers of patch/folders.c

SG = sibling('songs')
F = PF.F
SCREEN_Y0 = 30 + 50
ROW, VIEW_H, TOP = pod_ui.ROW_H, O['GRID_VIEW_H'], O['SG_TOP']
# expected draw output, written out (patch/folders.c FO_*): the tests check the drawing, so they must not read the constants back
TOP_PLAIN = 60                       # the first row with no pills: under the large title (SG_PILL_Y 52 + 8)
TEXT_X, TEXT_END, ICON, ICON_X, ICON_Y, TEXT_Y, MARK_X, CHEV_X = 56, 256, 24, 16, 14, 14, 262, 288
MARK_X_CHEV, TEXT_END_CHEV = 254, 248   # a row with a chevron that plays: the wave and the name's end (a file row keeps 262 / 256)
SC_YOFF = O['SC_YOFF']
LAYER, TITLE, M3U = (pod.DATA[k][0] for k in ('FOLDER_LAYER', 'FOLDER_TITLE', 'FOLDER_M3U'))
SHOWLIST, G_CLASS, SEL_VEC, NAV_TITLE = (pod.DATA[k][0] for k in ('PDEQ_SHOWLIST', 'G_CLASS_TYPE', 'SEL_VEC', 'NAV_TITLE'))
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_folders.bin') if WORK else None
T_LIST, T_SD, T_OTG, T_DIR, T_FILE = 1, 2, 3, 4, 8
WIDGETS = ('view_grid', 'btn_return', 'btn_backtoplayer', 'btn_select', 'btn_selall', 'btn_play', 'btn_shuffle', 'sg_add', 'sg_del', 'label_title', 'sg_title', 'label_status',
           'label_row_title', 'sg_bar', 'img_nb_fade') + VS_WIDGETS
ICONS = ('pod_ic_folders', 'fo_ic_sd', 'pod_ic_usbmode', 'pod_ic_cdripper', 'pod_ic_playlists', 'fo_ic_file', 'pod_ic_nowplaying')
ROOT = [(T_SD, 'SD', '/mnt/mmc'), (T_OTG, 'OTG', '/mnt/usb'), (T_SD, 'CD Library', '/mnt/mmc/Ripper')]
TREE = {
    '/mnt/mmc': [(T_DIR, 'Blank'), (T_DIR, '.m1plus'), (T_DIR, 'Music'), (T_DIR, 'Podcasts'), (T_DIR, 'Sort'), (T_FILE, 'readme.mp3'), (T_FILE, '.hidden.flac')],
    '/mnt/mmc/Music': [(T_DIR, 'Kind of Blue'), (T_FILE, '01 So What.flac'), (T_FILE, '02 Freddie Freeloader.FLAC'), (T_FILE, '03 Blue in Green.flac'), (T_LIST, 'Mix.m3u8')],
    '/mnt/mmc/Music/Kind of Blue': [(T_FILE, 'a.flac')],
    '/mnt/mmc/Podcasts': [(T_DIR, '.cache')],   # only a dot name: the stock load lists it, our page shows "Empty folder"
    '/mnt/mmc/Sort': [(T_FILE, 'b.mp3'), (T_DIR, 'zeta'), (T_FILE, 'A.flac'), (T_FILE, '10 x.ogg'), (T_DIR, 'Alpha'), (T_FILE, '2 x.mp3'), (T_LIST, 'Mix.m3u8'), (T_FILE, 'c.FLAC'), (T_DIR, 'beta')],   # the listing order is not the name order
    # a CUE rip (cue_tests enters it; no storage lists it otherwise): stock's parser makes one record per TRACK, (type, TITLE, the image's file name, start, end), all with the image's path
    '/mnt/mmc/Cue': [(T_DIR, 'Scans'), (T_FILE, 'Zebra', 'B side.flac', 0, 300), (T_FILE, 'Apple', 'B side.flac', 300, 600), (T_FILE, 'Mango', 'B side.flac', 600, 0), (T_FILE, '01 intro.mp3'),
                     (T_FILE, 'Kiwi', 'A side.flac', 0, 200), (T_FILE, 'Fig', 'A side.flac', 200, 0)],
    '/mnt/mmc/Cue/Scans': [(T_FILE, 'x.flac')],
    '/mnt/mmc/Blank': [],   # nothing at all: toolsLoadDirectory returns 0
    '/mnt/mmc/.m1plus': [],
}


class FM(SG.SongsMachine):
    """The songs machine plus the stock folder page's state and functions (folder_enter, folder_back, folder_reload, is_folderplaying, is_playing) modelled on a tree of
    folders: the layer (1 = the storages), the path, the stack of offsets and the shown list, as the stock functions leave them in the stock globals."""
    playing = None   # the file is_playing says yes to: (name, url)
    playing_dir = None   # the url of the file the folder queue plays (is_folderplaying: a folder holding it)
    present_usb = False
    fail_list = False
    tld_cleared = False   # toolsLoadDirectory ran on an empty directory (it clears the queue deque 0xa03964, never the shown list)

    def f_title(self, text): self.u.mem_write(TITLE, text.encode() + b'\0' + bytes(0x200 - len(text.encode()) - 1))

    def f_list(self):
        if self.layer <= 1:
            recs = []
            for type, name, url in ROOT:
                r = self.record(path=url, title='', name=name); self.setword(r + O['REC_TYPE'], type); recs.append(r)
        else:
            recs = []
            for type, name, *cue in TREE.get(self.path, []):
                r = self.record(path=f'{self.path}/{cue[0] if cue else name}', title=name if cue else '', name=name); self.setword(r + O['REC_TYPE'], type); recs.append(r)
                if cue: self.setword(r + O['REC_CUE_START'], cue[1]); self.setword(r + O['REC_CUE_END'], cue[2])
        self.shown = recs
        self.deques[self.shown_h] = recs
        self.setword(SHOWLIST, self.shown_h)
        self.setword(LAYER, self.layer)

    def f_enter(self, idx, y):
        if idx < 0:
            self.layer, self.path, self.offs = 1, '', [y]
            self.f_title('Folder'); self.f_list(); return 1
        rec = self.shown[idx]
        type, name, url = self.s32(rec + O['REC_TYPE']), self.read_cstr(self.word(rec + O['REC_NAME'])), self.read_cstr(self.word(rec + O['REC_PATH']))
        if type == T_FILE: return 8
        if self.layer <= 1:
            if url == '/mnt/usb' and not self.present_usb: return -3
            target = url
        else: target = f'{self.path}/{name}'
        if type == T_LIST and self.fail_list: return -1   # the m3u8 parse failed (0x4dbe48)
        if TREE.get(target) == []: self.tld_cleared = True; return -1   # toolsLoadDirectory 0x5e8860 cleared *0xa03964 and listed nothing: folder_enter 0x4dbcbc strips the path again (0x4dbcf8: -1); layer, offsets, title and the shown list stay
        self.path = target
        self.layer += 1; self.offs.append(y); self.f_title(name); self.f_list(); return 1

    def f_back(self, out):
        self.layer -= 1
        if self.layer <= 0:
            self.setword(LAYER, 0); return 0
        if self.layer == 1: self.path, self.offs = '', []; self.f_title('Folder')
        else:
            self.path = self.path.rsplit('/', 1)[0]
            if self.layer == 2: self.f_title({'/mnt/mmc': 'SD'}.get(self.path, self.path.rsplit('/', 1)[-1]))
            else: self.f_title(self.path.rsplit('/', 1)[-1])
            self.setword(out, self.offs.pop())
        self.f_list(); return 1

    def _statx(self, u, intno, _):
        """The statx syscall (ft_statx): stx_mtime.tv_sec of the path from self.mtimes, STATX_MTIME in the mask; an unknown path fails."""
        path = self.read_cstr(u.reg_read(UC_MIPS_REG_A1))
        buf = self.word(u.reg_read(UC_MIPS_REG_SP) + 16)
        self.statx_paths.append(path)
        if path not in self.mtimes:
            u.reg_write(UC_MIPS_REG_A3, 1); u.reg_write(UC_MIPS_REG_V0, 2); return
        u.mem_write(buf, bytes(256)); u.mem_write(buf, struct.pack('<I', 0x40)); u.mem_write(buf + 112, struct.pack('<Q', self.mtimes[path]))
        u.reg_write(UC_MIPS_REG_A3, 0); u.reg_write(UC_MIPS_REG_V0, 0)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('folder_enter', 'folder_back', 'folder_reload', 'is_folderplaying', 'is_playing'): return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'folder_enter':
            self.calls.append(('folder_enter', struct.unpack('<i', struct.pack('<I', a0))[0], a1)); ret = self.f_enter(struct.unpack('<i', struct.pack('<I', a0))[0], a1)
        elif name == 'folder_back':
            self.calls.append(('folder_back',)); ret = self.f_back(a0)
        elif name == 'folder_reload':
            self.calls.append(('folder_reload',)); self.f_list(); ret = 1
        elif name == 'is_folderplaying':
            url = self.read_cstr(a0); self.calls.append(('is_folderplaying', url))
            ret = int(self.playing_dir is not None and self.playing_dir.startswith(url + '/'))
        elif name == 'is_playing':
            self.calls.append(('is_playing', a0, a1))
            ret = int(self.playing is not None and self.playing == (self.read_cstr(a2), self.read_cstr(a3)))
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def folder_machine(window=0x20001000, usb=False):
    m = FM()
    m.nav_asset = ui_asset('m1plus_folders')
    m.mtimes, m.statx_paths, m.copy_queue = {}, [], True
    m.u.hook_add(UC_HOOK_INTR, m._statx)
    m.window = window
    m.load_image = 0
    m.present_usb = usb
    m.layer, m.path, m.offs, m.shown = 0, '', [], []
    m.shown_h = m.new_deque()
    m.setword(SHOWLIST, m.shown_h)
    for w in WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.images = {'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)}
    for n in ICONS: m.images[n] = (24, 24, bytes((0xee, 0xee, 0xee, 255)) * (24 * 24))
    m.setword(SEL_VEC, m.alloc(8))
    m.stock_songlist = True
    win, lv, sv, view = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_grid']
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['folders_scrollview'] = sv
    for off, v in ((4, 0), (8, 320), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
    m.setword(m.widgets['label_title'] + 8, 156); m.setword(m.widgets['sg_title'] + 8, O['SG_TITLE_W'])
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    for n, t in (('btn_play', 'Play'), ('btn_shuffle', 'Shuffle'), ('sg_add', 'Add to Playlist'), ('sg_del', 'Delete')): m.wtext[m.widgets[n]] = t
    m.sv, m.view = sv, view
    return m


def open_page(m): m.call(PSYMS['folders_open'], a0=O['HOME_FOLDER'] if 'HOME_FOLDER' in O else 4, count=900000000); return list(m.calls)
def opened(**kw):
    m = folder_machine(**kw); open_page(m)
    return m


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts with their styles, fills) of that frame."""
    ev = m.paint_event()
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['fo_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(zip(m.texts, m.text_styles)), list(m.fills)


def touch(m, kind, x, y, fn, t=1000): return m.touch(kind, x, y, t, fn=fn)


def tap(m, x, y, dx=0, dy=0):
    """A tap at content point (x, y) (the list's top is 0; the scroll offset is not included)."""
    touch(m, 'down', x, SCREEN_Y0 + y, 'fo_on_down')
    touch(m, 'up', x + dx, SCREEN_Y0 + y + dy, 'fo_on_up', 1080)
    return list(m.calls)


def tap_row(m, r, top=TOP):
    m.calls.clear()
    return tap(m, 100, top + r * ROW + 20)


def open_select(m):
    """The \"...\" card's Select row (the old Select button)."""
    click(m, 'btn_more')
    return click(m, 'vs_item7')


def ui(): return awtk_ui.parse(open(UI, 'rb').read())
def enter(m, name, top=None):
    """Tap the shown row called name."""
    i = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.shown if not m.read_cstr(m.word(r + O['REC_NAME'])).startswith('.')].index(name)
    return tap_row(m, i, top if top is not None else (TOP if any(m.s32(r + O['REC_TYPE']) == T_FILE for r in m.shown) else TOP_PLAIN))


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def asset_tests(ctx):
    """1. The built asset and the menu row."""
    expect = ctx.expect
    root = ui()
    f = root.find
    expect(root.name == 'm1plus_folders_page' == pod_pages.FOLDERS.name and pod_pages.FOLDERS in pod_pages.PAGES and pod_pages.FOLDERS.key == 'm1plus_folders',
           'the page is m1plus_folders (window m1plus_folders_page), in the page table')
    row = next(r for r in pod_pages.ITEMS if r.label == 'Folders')
    expect(row.action == pod_pages.ACT_FOLDERS == 37 and row.arg == pod_pages.HOME_FOLDER, 'the menu\'s Folders row is ACT_FOLDERS (the stock tile is its fallback)')
    expect(all(f(n) is not None for n in WIDGETS if n != 'img_nb_fade') and f('img_nb_fade') is not None, 'every widget the payload looks up is in the asset')
    lv, sv, grid = f('folders_listview'), f('folders_scrollview'), f('view_grid')
    expect((lv.y, lv.h) == (50, VIEW_H) and sv.w == 310 and f('scroll_bar_m') is not None and grid.get('style:normal:bg_color') == '#000000',
           'a stock list under the 50 px navbar (400 high, scroll_view 310 wide with the stock scroll bar) holding the content view')
    nb = f('navigationbar_view')
    k = {c.name: c for c in nb.children}
    expect(k['btn_select'].get('visible') == 'false' and k['btn_select'].get('sensitive') == 'false' and (k['btn_select'].x, k['btn_select'].w) == (214, 46)
           and k['btn_select'].get('style:normal:icon') == 'pod_nav_selectl' and k['btn_select'].get('style:pressed:icon') == 'pod_nav_selectl_down',
           'btn_select: hidden and insensitive, Select (pod_nav_selectl, the left cap at 214) for a playlist file\'s tracks, where the "..." card would hold Select alone')
    expect((k['btn_more'].x, k['btn_more'].w) == (214, 46) and k['btn_more'].get('style:normal:icon') == 'pod_nav_more' and k['btn_more'].get('visible') != 'false'
           and k['btn_more'].x + k['btn_more'].w == k['btn_backtoplayer'].x and k['btn_backtoplayer'].get('style:normal:icon') == 'ah_nav_play'
           and k['btn_backtoplayer'].get('style:pressed:icon') == 'ah_nav_play_down', '"..." | Now Playing is one glass capsule (the Songs and Artists one): the "..." the left cap at 214, flush against Now Playing, the right cap; no Select button of its own')
    expect(k['label_title'].get('visible') == 'false' and k['label_title'].w == 214 - 58 and k['btn_selall'].get('visible') == 'false' and k['btn_selall'].get('sensitive') == 'false',
           'the small title is hidden until the large one has scrolled away (it runs to the "..."); Select All is hidden and insensitive')
    scrim, card = f('vs_scrim'), f('vs_card')
    expect(scrim is not None and card is not None and scrim.get('visible') == 'false' and card.get('visible') == 'false' and root.children[-1] is card,
           'the card and its scrim are in the asset, hidden')
    expect(pod_pages.FOLDERS_SORT_KEYS[:3] == ('Name', 'Date Modified', 'Type') and len(pod_pages.FOLDERS_SORT_KEYS) == 4 and all(k in pod_i18n.TEXT for k in pod_pages.FOLDERS_SORT_KEYS),
           'the card\'s sort rows are Name, Date Modified and Type (translated; the fourth slot is the unused one)')
    expect('folders-sort' in pod_pages.SETTING_FILES and pod_pages.SETTING_FILES.index('folders-sort') == pod_pages.SETTING_FILES.index('songs-sort-rev') + 1 and pod_pages.SETTING_FILES.count('folders-sort') == 1,
           'folders-sort is on the Settings Files page, after songs-sort-rev (patch/setfiles.c has it in the same place)')
    big = f('sg_title')
    expect((big.x, big.y, big.h) == (O['SG_TITLE_X'], 0, O['SG_TITLE_H']) and big.get('style:normal:font_size') == '32' and big.get('sensitive') == 'false', 'the large title is the Songs page\'s: 32 px at x 12, insensitive')
    for n, x in (('btn_play', O['SG_PILL_X0']), ('btn_shuffle', O['SG_PILL_X1'])):
        b = f(n)
        expect((b.x, b.y, b.w, b.h) == (x, O['SG_PILL_Y'], O['SG_PILL_W'], O['SG_PILL_H']) and b.get('visible') == 'false' and b.get('sensitive') == 'false',
               f'{n}: the Songs page\'s pill, hidden and insensitive until the folder holds an audio file')
    bar = f('sg_bar')
    expect(bar.get('visible') == 'false' and {c.name for c in bar.children} >= {'sg_add', 'sg_del'} and f('img_nb_fade').get('visible') == 'false', 'the select bar (Add to Playlist, Delete) and the navbar fade are hidden at rest')
    xx = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    from PIL import Image
    expect(all(os.path.exists(os.path.join(xx, n + '.png')) and Image.open(os.path.join(xx, n + '.png')).size == (ICON, ICON) for n in ICONS), 'the seven glyphs the rows draw are in the tree, 24 x 24')
    import mod_icons
    expect((F['FO_ICON'], F['FO_ICON_X'], F['FO_TEXT_X'], ROW) == (mod_icons.POD_ICON, mod_icons.POD_ICON_X, mod_icons.POD_TEXT_X, pod_ui.ROW_H) == (24, 16, 56, 52)
           and F['FO_CHEV_X'] == O['LIST_CHEV_X'] == 288 and F['FO_ICON_Y'] == (ROW - 24) // 2 and set(mod_icons.FOLDER_ROWS) <= set(ICONS)
           and {'pod_ic_folders', 'pod_ic_playlists', 'pod_ic_cdripper', 'pod_ic_nowplaying'} <= {v[0] for v in mod_icons.POD_ROWS.values()} | {'pod_ic_cdripper'},
           'the menu rows\' numbers: a 24 px glyph at x 16, the text at x 56, the 52 px pitch, the stock chevron\'s place; the glyphs are theirs')
    expect(F['FO_TOP_PLAIN'] >= O['SG_PILL_Y'] and F['FO_TEXT_END'] <= F['FO_MARK_X'] + 8 and F['FO_MARK_X'] + F['FO_ICON'] - 4 <= F['FO_CHEV_X'] + 4
           and (F['FO_MARK_X_CHEV'], F['FO_TEXT_END_CHEV']) == (MARK_X_CHEV, TEXT_END_CHEV) and F['FO_TEXT_END_CHEV'] <= F['FO_MARK_X_CHEV'] and F['FO_MARK_X_CHEV'] + F['FO_ICON'] + 8 <= F['FO_CHEV_X'] + 2
           and (F['FO_COVER'], F['FO_COVER_X'], F['FO_COVER_Y']) == (40, 8, 6) and F['FO_TEXT_Y'] == (ROW - O['LIST_TITLE_H']) // 2,
           'the geometry: the plain list starts under the large title, the names end before the wave, the wave before the chevron')
    expect(all(f(n) is None for n in ('label_row_sub',)) and f('sg_title').x == O['SG_TITLE_X'] == 12 and f('btn_play').x == O['SG_PILL_X0'] == 10,
           'one line a row: no second text style; the large title and the pills are at the Songs page\'s x (12, 10)')


def open_tests(ctx):
    """2. The row opens the page, with the fallbacks; the stock state is entered like folder_page_init does."""
    expect = ctx.expect
    page = pod_pages.MENU
    row = next(i for i, r in enumerate(page.rows) if r.label == 'Folders')
    m = folder_machine()
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * row, count=900000000)
    expect(('window_open', 'm1plus_folders') in m.calls and 'stock_resume' not in m.names(), 'the Folders row opens our page')
    fe = [c for c in m.calls if c[0] == 'folder_enter']
    expect(fe == [('folder_enter', -1, 0)] and m.word(LAYER) == 1 and m.word(G_CLASS) == 1, f'folder_enter(-1, 0) as folder_page_init: the storages, layer 1, class 1 ({fe})')
    m = folder_machine(window=0)
    open_page(m)
    expect(('stock_resume', str(pod_pages.HOME_FOLDER)) in m.calls and 'folder_enter' not in m.names(), 'a window that will not open leaves the stock folder page')
    m = folder_machine(); m.widgets.pop('sg_bar')
    open_page(m)
    expect(('navigator_back',) in m.calls and 'folder_enter' not in m.names(), 'an asset that is not ours: the page leaves again, the stock state untouched')
    m = opened()
    m.call(PSYMS['folders_open'], a0=4, count=900000000)
    expect('window_open' not in m.names() and 'stock_resume' not in m.names(), f'a page already open is not opened twice (and the stock page is not the answer): {m.names()}')
    m.call(PSYMS['fo_on_destroy'], count=4000000)
    expect(m.destroyed >= len(ICONS) + 3, f'destroy frees the glyphs, the chevron and the marks ({m.destroyed} bitmaps)')


def rows_tests(ctx):
    """3. The rows painted from the stock list."""
    expect = ctx.expect
    m = opened()
    blits, texts, fills = paint(m)
    tx = TEXT_X
    ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
    expect(ttl == [(n, (tx, TOP_PLAIN + i * ROW + TEXT_Y, TEXT_END - tx, O['LIST_TITLE_H'])) for i, (_, n, _) in enumerate(ROOT)],
           f'the root list: SD, OTG, CD Library, one line each centred in the row, from x 56 to the wave\'s room: {ttl}')
    expect([(b[2][0], b[2][1]) for b in blits if b[2][2] == ICON] == [(ICON_X, TOP_PLAIN + i * ROW + ICON_Y) for i in range(3)], 'a 24 px glyph at x 16, centred in each row')
    chev = [b for b in blits if b[2][2] == PF.O.get('POD_CHEV_W', 10) and b[2][3] == 16]
    expect(len(chev) == 3 and all(b[2][0] == CHEV_X for b in chev), 'a chevron ends each storage row (x 288)')
    hair = [f_ for f_ in fills if f_[0] == O['LIST_HAIR']]
    expect(len(hair) == 3 and hair[0][1:] == (tx, TOP_PLAIN + ROW - 1, 320 - 10 - tx, 1), f'a hairline at each row\'s foot: {hair[:1]}')
    expect(vis(m, 'btn_play') == (0, 0) and vis(m, 'btn_shuffle') == (0, 0), 'no pills at the root')
    # a folder with files: pills, the rows start under the pills, dot names are not shown
    m = opened()
    enter(m, 'SD')
    blits, texts, fills = paint(m)
    names = [t for (t, r), s in texts if s == 'label_row_title']
    expect(m.word(LAYER) == 2 and names == ['Blank', 'Music', 'Podcasts', 'Sort', 'readme.mp3'],
           f'inside SD: the dot folder and the dot file are not shown, a file is shown by its file name ({names})')
    expect(vis(m, 'btn_play') == (1, 1) and vis(m, 'btn_shuffle') == (1, 1), 'the folder holds an audio file: the pills show')
    expect(m.wtext.get(m.widgets['sg_title']) == 'SD' and m.wtext.get(m.widgets['label_title']) == 'SD', 'the titles are the folder\'s name (the stock title buffer)')
    # the wave: a file by is_playing, a folder by is_folderplaying
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.playing = ('03 Blue in Green.flac', '/mnt/mmc/Music/03 Blue in Green.flac')
    blits, texts, fills = paint(m)
    wave = [b for b in blits if b[2][0] == MARK_X]
    expect(len(wave) == 1 and wave[0][2][1] == TOP + 3 * ROW + ICON_Y, f'the wave marks the playing file ({wave})')
    expect(('is_playing', 1, 0) in m.calls, 'is_playing is asked as the stock row asks it: class 1, the cue start')
    m = opened(); m.playing_dir = '/mnt/mmc/Music/x.flac'
    enter(m, 'SD')
    blits, texts, fills = paint(m)
    wave = [b for b in blits if b[2][0] == MARK_X_CHEV]
    expect(len(wave) == 1 and wave[0][2][1] == TOP + ROW + ICON_Y and not [b for b in blits if b[2][0] == MARK_X], 'the folder that holds the playing file carries the wave, 8 px clear of its chevron (x 254)')
    ttl = {t: r for (t, r), s in texts if s == 'label_row_title'}
    expect(ttl['Music'][2] == TEXT_END_CHEV - TEXT_X and ttl['Blank'][2] == TEXT_END - TEXT_X, f'a playing folder\'s name ends at 248, the others at 256 ({ttl["Music"]}, {ttl["Blank"]})')
    # the wave comes and goes while the level is open: the name is cut again for the width it gets (the tile keeps a cut name)
    long = 'ABCDEFGHIJKLMNOPQRSTUVWXY'   # 25 chars at 8 px: 200 px, the row's whole width
    root = TREE['/mnt/mmc']
    TREE['/mnt/mmc'] = root[:5] + [(T_DIR, 'Tall')] + root[5:]; TREE['/mnt/mmc/Tall'] = [(T_DIR, long)]; TREE['/mnt/mmc/Tall/' + long] = []   # (after Sort: the listing's place is the shown one)
    try:
        m = opened(); enter(m, 'SD'); enter(m, 'Tall')
        name = lambda: [t for (t, r), s in paint(m)[1] if s == 'label_row_title']
        first = name()
        m.playing_dir = f'/mnt/mmc/Tall/{long}/x.flac'; cut = name()
        m.playing_dir = None; back = name()
        expect(first == [long] and cut == [long[:22] + '\u2026'] and back == [long], f'a folder that starts to play has its name cut to 192 px, and whole again when it stops ({first}, {cut}, {back})')
    finally:
        TREE['/mnt/mmc'] = root
        for k in ('/mnt/mmc/Tall', '/mnt/mmc/Tall/' + long): TREE.pop(k, None)
    # press fill
    m = opened()
    touch(m, 'down', 100, SCREEN_Y0 + TOP_PLAIN + 20, 'fo_on_down')
    blits, texts, fills = paint(m)
    expect([f_ for f_ in fills if f_[0] == O['LIST_PRESS']] == [(O['LIST_PRESS'], 0, TOP_PLAIN, 320, ROW - 1)], 'a finger on a row fills it')
    touch(m, 'abort', 100, SCREEN_Y0 + TOP_PLAIN + 20, 'fo_on_abort')
    expect(not [f_ for f_ in paint(m)[2] if f_[0] == O['LIST_PRESS']], 'an abort lets go of it')


def levels_tests(ctx):
    """4. Levels: a folder goes in, Back goes up through the stock stack, the root closes; a card that is not there is the stock message; the title collapses."""
    expect = ctx.expect
    m = opened()
    calls = enter(m, 'SD')
    expect(('folder_enter', 0, 0) in calls and m.word(LAYER) == 2, f'a tap on SD is folder_enter(0, the offset): layer 2 ({[c for c in calls if c[0] == "folder_enter"]})')
    scroll_to(m, 0)
    enter(m, 'Music')
    expect(m.word(LAYER) == 3 and m.path == '/mnt/mmc/Music' and m.wtext[m.widgets['sg_title']] == 'Music', 'a tap on Music goes in: layer 3, the title is Music')
    m.setword(m.sv + SC_YOFF, 20)
    m.calls.clear(); click(m, 'btn_return')
    expect(m.names().count('folder_back') == 1 and m.word(LAYER) == 2 and 'navigator_back' not in m.names() and m.wtext[m.widgets['sg_title']] == 'SD', 'Back is folder_back: one level up, the page stays')
    click(m, 'btn_return'); calls = click(m, 'btn_return')
    expect(m.word(LAYER) == 0 and calls.count(('navigator_back',)) == 1, 'Back at the root: folder_back returns 0 (the stock state is cleared) and the window closes')
    # the offset the level was left at comes back
    m = opened(); enter(m, 'SD')
    m.offs[-1] = 0
    enter(m, 'Music')
    m.offs[-1] = 77
    click(m, 'btn_return')
    expect(m.s32(m.sv + SC_YOFF) == 0 and ('folder_back',) in m.calls, 'the offset comes back clamped to the list (a short list scrolls to 0)')
    # the card that is not there
    m = opened()
    m.calls.clear(); tap_row(m, 1, TOP_PLAIN)
    expect(any(c[0] == 'toast' and c[1] == 'msg_nototg' for c in m.calls) and m.word(LAYER) == 1, 'OTG without a drive: the stock "No OTG Found" message, the list stays')
    # a folder with nothing in it: folder_enter returns -1 and leaves the level; ours says so (not the stock "File Not Found") and the parent's list stays
    m = opened(); enter(m, 'SD')
    before = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.shown]
    m.calls.clear(); enter(m, 'Blank')
    toasts = [c[1] for c in m.calls if c[0] == 'toast']
    after = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.shown]
    expect(m.tld_cleared and toasts == ['No music in this folder'], f'an empty folder: the toast is "No music in this folder", not msg_notfile ({toasts})')
    expect('folder_reload' in m.names(), 'the level is read again: the failed load emptied the folder deque 0xa03964 (batch_delete_file\'s class 1 source)')
    expect(m.word(LAYER) == 2 and m.path == '/mnt/mmc' and m.wtext[m.widgets['sg_title']] == 'SD' and after == before and m.word(SHOWLIST) == m.shown_h,
           f'the stock load leaves the layer, the path, the title and the shown list (*0xa045d8) alone ({after})')
    blits, texts, fills = paint(m)
    names = [t for (t, r), s in texts if s == 'label_row_title']
    expect(names == ['Blank', 'Music', 'Podcasts', 'Sort', 'readme.mp3'], f'the page still shows the parent folder\'s rows ({names})')
    m = opened(); enter(m, 'SD'); enter(m, 'Music'); m.fail_list = True
    m.calls.clear(); enter(m, 'Mix.m3u8')
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['msg_notfile'], 'a playlist file that fails keeps the stock "File Not Found"')
    # a playlist file goes in like a folder
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.calls.clear(); enter(m, 'Mix.m3u8')
    expect(('folder_enter', 4, 0) in m.calls, 'a playlist file is entered through folder_enter too')
    # the small title: shown once the large one has scrolled away; the navbar fade while scrolled
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    expect(vis(m, 'label_title')[0] == 0 and vis(m, 'img_nb_fade')[0] == 0, 'at rest: the large title, no small title, no fade')
    scroll_to(m, O['SG_COLLAPSE'] + 1)
    expect(vis(m, 'label_title')[0] == 1 and vis(m, 'img_nb_fade')[0] == 1, 'past the collapse: the small title and the fade show')
    scroll_to(m, 0)
    expect(vis(m, 'label_title')[0] == 0, 'back at the top: the large title again')
    # an empty folder: the status line and the small title, no rows
    m = opened(); enter(m, 'SD'); enter(m, 'Podcasts')
    expect(vis(m, 'label_status')[0] == 1 and vis(m, 'view_grid')[0] == 0 and vis(m, 'label_title')[0] == 1 and m.wtext[m.widgets['label_status']] == 'Empty folder', 'an empty folder says so and keeps its small title')


def play_tests(ctx):
    """5. A file plays like the stock row; Play and Shuffle."""
    expect = ctx.expect
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.present.update(f'/mnt/mmc/Music/{n}' for n in ('01 So What.flac', '02 Freddie Freeloader.FLAC', '03 Blue in Green.flac'))
    calls = tap_row(m, 2)   # '02 Freddie Freeloader.FLAC': rows are Kind of Blue, 01, 02, 03, Mix
    ll = [c for c in calls if c[0] == 'loadSongList']
    pl = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(ll == [('loadSongList', '02 Freddie Freeloader.FLAC', 0, 1)] and pl and pl[0][2:] == (1, 1, 2) and getattr(m, 'played', None) and [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.played[0]] == ['01 So What.flac', '02 Freddie Freeloader.FLAC', '03 Blue in Green.flac'],
           f'a file\'s tap: loadSongList(queue, name, cue, class 1) on the folder\'s files, then Now Playing at it ({ll}, {pl})')
    expect(m.word(G_CLASS) == 1, 'the browsing class is 1 (as folder_page_init leaves it)')
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.present.update(f'/mnt/mmc/Music/{n}' for n in ('01 So What.flac', '02 Freddie Freeloader.FLAC', '03 Blue in Green.flac'))
    calls = tap_row(m, 2)
    expect(any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), 'a file on the card plays')
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.present.update(f'/mnt/mmc/Music/{n}' for n in ('01 So What.flac', '02 Freddie Freeloader.FLAC', '03 Blue in Green.flac'))
    calls = click(m, 'btn_play')
    ll = [c for c in calls if c[0] == 'loadSongList']
    expect(ll and ll[0][1] == '01 So What.flac' and ll[0][3] == 1 and any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), f'Play: the first audio file ({ll})')
    m.calls.clear()
    calls = click(m, 'btn_shuffle')
    ll = [c for c in calls if c[0] == 'loadSongList']
    expect(ll and ll[0][3] == 1 and ll[0][1].lower().endswith('.flac') and any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), f'Shuffle: a file of the folder, never a folder or a playlist file ({ll})')
    # a missing file: the message, nothing plays
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    calls = tap_row(m, 1)
    expect(any(c[0] == 'toast' for c in calls) and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), 'a file that is not on the card: the message box, nothing plays')
    # a drag is not a tap
    m = opened(); enter(m, 'SD'); m.calls.clear()
    tap(m, 100, TOP + 20, dy=40)
    expect(not any(c[0] == 'folder_enter' for c in m.calls), 'a drag does not go in')


def select_tests(ctx):
    """6. Select mode: marks on folders and audio files, Select All, Delete and Add on the stock selection vector; no Select at the root."""
    expect = ctx.expect
    m = opened()
    expect(vis(m, 'btn_more') == (0, 0) and vis(m, 'btn_backtoplayer') == (1, 1) and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_np'
           and m.props.get((m.widgets['btn_backtoplayer'], 'style:pressed:icon')) == 'ah_nav_np_down',
           'the root list (SD, OTG, CD Library): no Select; Now Playing alone is the glass disc')
    enter(m, 'SD')
    expect(vis(m, 'btn_more') == (1, 1) and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_play' and m.props.get((m.widgets['btn_backtoplayer'], 'style:pressed:icon')) == 'ah_nav_play_down',
           'inside a storage: Select | Now Playing, Now Playing the capsule\'s right cap')
    open_select(m); m.layer = 1; m.f_list(); m.calls.clear()
    fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=ctxp, a1=0, count=900000000)
    expect(vis(m, 'btn_selall') == (0, 0) and vis(m, 'sg_bar')[0] == 0 and vis(m, 'btn_more') == (0, 0), 'select mode on when the list becomes the root: it ends, no Select')
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    m.present.update(f'/mnt/mmc/Music/{n}' for n in ('01 So What.flac', '02 Freddie Freeloader.FLAC', '03 Blue in Green.flac'))
    open_select(m)
    expect(vis(m, 'btn_more') == (0, 0) and vis(m, 'btn_backtoplayer') == (0, 0) and vis(m, 'btn_selall') == (1, 1) and vis(m, 'sg_bar') == (1, 1) and m.props.get((m.widgets['btn_play'], 'sensitive')) == 0,
           'select mode: Select and Now Playing give way to Select All and the bar; the pills stay, dead')
    blits, texts, fills = paint(m)
    marks = [b for b in blits if b[2][2] == O['SG_MARK']]
    expect(len(marks) == 4, f'a mark on the folder and each of the three audio files, none on the playlist file ({len(marks)})')
    tap_row(m, 1)
    expect(m.wtext[m.widgets['label_title']] == '1 Selected', 'a tap on a file marks it: "1 Selected"')
    click(m, 'btn_selall')
    expect(m.wtext[m.widgets['label_title']] == '4 Selected', 'Select All marks the folders and the audio files, not the playlist file')
    click(m, 'btn_selall')
    expect(m.wtext[m.widgets['label_title']] == 'Select Items', 'Select All again marks none')
    click(m, 'btn_selall'); tap_row(m, 2)
    m.confirm_yes = True; m.calls.clear()
    top = m.alloc(0x80); m.u.mem_write(top, bytes(0x80)); m.top_main = top; m.children[m.wm] = [top]   # the page under the confirm (fo_ask's dim scrim goes on it)
    seen = []; m.on_confirm = lambda mm: seen.append(list(mm.children.get(top, [])))
    calls = click(m, 'sg_del')
    made = [c[1] for c in calls if c[0] == 'view_create']
    expect(len(made) == 1 and seen and seen[0][-1] == made[0] and ('widget_set_sensitive', made[0], 0) in calls and ('widget_destroy', made[0]) in calls and made[0] not in m.children.get(top, []),
           'the folder confirm: the dim scrim is the page\'s last child while the dialog is up, insensitive, destroyed after it')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1] == 1 and bd[0][5] == 1 and bd[0][6] == [0, 1, 3] and any(c[0] == 'toast' and c[1] == 'msg_delfilesuccess' for c in calls)
           and any(c[0] == 'confirm' and c[1] == 'Delete folder and everything in it?' and c[2] == 1 for c in calls), f'Delete (a folder and files marked): the confirm (kind 1) warns about the folder, then the stock sequence, batch_delete_file(1, list, vector, 0, 1) on the marked records, the message ({bd})')
    expect(m.names().count('folder_reload') >= 1 and vis(m, 'sg_bar')[0] == 0, 'the list is read again and select mode is over')
    m2 = opened(); enter(m2, 'SD'); enter(m2, 'Music'); open_select(m2); tap_row(m2, 0)
    expect(m2.word(LAYER) == 3 and 'folder_enter' not in m2.names() and m2.wtext[m2.widgets['label_title']] == '1 Selected', 'in select mode a tap on a folder marks it instead of entering')
    tap_row(m2, 0)
    expect(m2.wtext[m2.widgets['label_title']] == 'Select Items', 'a second tap unmarks it')
    tap_row(m2, 4)
    expect(m2.wtext[m2.widgets['label_title']] == 'Select Items', 'the playlist file has no mark')
    # Delete and Add with a marked folder: the folder record goes to the stock functions, which expand it (docs/modules/folders.md)
    tap_row(m2, 0); m2.confirm_yes = True; m2.calls.clear()
    calls = click(m2, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1] == 1 and bd[0][5] == 1 and bd[0][6] == [0], f'Delete with a marked folder: the folder record is on the vector of batch_delete_file(1, ..., 0, 1), which removes it with rm -rf ({bd})')
    expect(any(c[0] == 'confirm' and c[1] == 'Delete folder and everything in it?' for c in calls), 'a lone marked folder: the folder confirm')
    m3 = opened(); enter(m3, 'SD'); enter(m3, 'Music'); m3.present.update(f'/mnt/mmc/Music/{n}' for n in ('01 So What.flac', '02 Freddie Freeloader.FLAC'))
    open_select(m3); tap_row(m3, 1); tap_row(m3, 2); m3.confirm_yes = True; m3.calls.clear()
    calls = click(m3, 'sg_del')
    expect(any(c[0] == 'confirm' and c[1] == 'msg_delfile' and c[2] == 1 for c in calls) and not any(c[0] == 'confirm' and c[1] != 'msg_delfile' for c in calls),
           'Delete with files only: the stock "Delete File?" confirm')
    m2 = opened(); enter(m2, 'SD'); enter(m2, 'Music'); open_select(m2); tap_row(m2, 0); tap_row(m2, 2); m2.calls.clear()
    calls = click(m2, 'sg_add')
    expect([c for c in calls if c[0] == 'set_selectindex'] == [('set_selectindex', 0), ('set_selectindex', 2)] and any(c[0] == 'navigator_to_with_context' and c[1] == 'playlist_page' for c in calls),
           'Add with a marked folder: its record and the file on the vector, the stock picker (batch_add_file adds the folder\'s audio files)')
    m = opened(); enter(m, 'SD'); enter(m, 'Music'); open_select(m); tap_row(m, 1)
    m.confirm_yes = False; m.calls.clear()
    calls = click(m, 'sg_del')
    expect(not any(c[0] == 'batch_delete_file' for c in calls) and vis(m, 'sg_bar')[0] == 1, 'No in the confirm dialog: nothing is deleted, select mode stays')
    m = opened(); enter(m, 'SD'); enter(m, 'Music'); open_select(m)
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'toast' and c[1] == 'msg_delfilefailed' for c in calls) and not any(c[0] == 'confirm' for c in calls), 'Delete with nothing marked: the stock "failed" message, no dialog')
    m.calls.clear(); calls = click(m, 'sg_add')
    expect(any(c[0] == 'toast' and c[1] == 'msg_addfailed' for c in calls), 'Add with nothing marked: the stock message')
    tap_row(m, 1); m.calls.clear()
    m.u.mem_write(M3U, b'/x.m3u8\0')
    m.confirm_yes = True
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'toast' and c[1] == 'msg_notsupportdel' for c in calls) and not any(c[0] == 'batch_delete_file' for c in calls), 'inside a playlist file the stock "can\'t be removed" message')
    m.u.mem_write(M3U, b'\0')
    m.calls.clear(); calls = click(m, 'sg_add')
    pk = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playlist_page']
    expect(pk and pk[0][2] == (O['PICKER_ADD'] | 1) and [c for c in calls if c[0] == 'set_selectindex'] == [('set_selectindex', 1)], f'Add: the stock playlist picker with the folder class, the marked record on the vector ({pk})')
    m.u.mem_write(NAV_TITLE, b'clobbered\0'); m.setword(G_CLASS, 0xf00b)
    fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.calls.clear(); m.call(fn, a0=ctxp, a1=0, count=900000000)
    expect(m.word(G_CLASS) == 1 and vis(m, 'sg_bar')[0] == 0 and 'folder_reload' in m.names(), 'back from the picker: the class put back, select mode over, the level read again')


def stale_tests(ctx):
    """7. A list another query replaced: nothing of it is read; the level is read again when the page is in front; a dialog closing does not reload."""
    expect = ctx.expect
    m = opened(); enter(m, 'SD'); enter(m, 'Music')
    fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.calls.clear(); m.call(fn, a0=ctxp, a1=0, count=900000000)
    expect('folder_reload' not in m.names(), 'back to the front with the list as it was: nothing is read again (select marks survive a dialog)')
    other = m.new_deque([m.record(), m.record()])
    m.setword(SHOWLIST, other)
    m.calls.clear(); paint(m)
    expect(not m.blits and not m.texts, 'a paint over a list another query replaced reads nothing of it')
    m.calls.clear(); m.call(fn, a0=ctxp, a1=0, count=900000000)
    expect('folder_reload' in m.names() and m.word(SHOWLIST) == m.shown_h, 'back to the front: folder_reload, the stock list is the folder\'s again')
    m.call(PSYMS['fo_on_destroy'], count=4000000)


def order_tests(ctx):
    """8. The \"...\" card: Select, then Name, Date Modified and Type. Folders stay first in every order; the ticked row reverses; the order is saved in folders-sort; play, row taps and Select follow the order shown."""
    expect = ctx.expect
    D = '/mnt/data/m1plus/'
    SORT = '/mnt/mmc/Sort'
    MT = {'Alpha': 100, 'beta': 300, 'zeta': 200, 'b.mp3': 500, 'A.flac': 400, '2 x.mp3': 600, 'c.FLAC': 400, '10 x.ogg': 50, 'Mix.m3u8': 700}
    FOLDERS_AZ, FILES_AZ = ['Alpha', 'beta', 'zeta'], ['2 x.mp3', '10 x.ogg', 'A.flac', 'b.mp3', 'c.FLAC', 'Mix.m3u8']
    ORDERS = {   # (sort, reversed): the rows top to bottom (folders first in each)
        (0, 0): FOLDERS_AZ + FILES_AZ, (0, 1): FOLDERS_AZ[::-1] + FILES_AZ[::-1],
        (1, 0): ['beta', 'zeta', 'Alpha', 'Mix.m3u8', '2 x.mp3', 'b.mp3', 'A.flac', 'c.FLAC', '10 x.ogg'], (1, 1): ['Alpha', 'zeta', 'beta', '10 x.ogg', 'A.flac', 'c.FLAC', 'b.mp3', '2 x.mp3', 'Mix.m3u8'],
        (2, 0): FOLDERS_AZ + ['A.flac', 'c.FLAC', 'Mix.m3u8', '2 x.mp3', 'b.mp3', '10 x.ogg'], (2, 1): FOLDERS_AZ + ['10 x.ogg', '2 x.mp3', 'b.mp3', 'Mix.m3u8', 'A.flac', 'c.FLAC'],
    }
    def fresh(saved=None, big=False):
        m = folder_machine()
        m.measure = lambda t: 60
        m.mtimes = {f'{SORT}/{n}': t for n, t in MT.items()}
        if saved is not None: m.fs[D + 'folders-sort'] = saved
        open_page(m); tap_row(m, 0, TOP_PLAIN); tap_row(m, shown(m).index('Sort'))
        for i, t in enumerate(pod_pages.FOLDERS_SORT_KEYS): m.wtext[m.widgets[f'vs_label{i}']] = t
        for i in range(4): m.wtext[m.widgets[f'vs_sub{i}']] = 'A–Z'
        m.calls.clear(); m.statx_paths.clear()
        return m
    def shown(m):
        names, vh = {}, m.props.get((m.sv, 'virtual_h'), 0) or VIEW_H
        for off in range(0, max(vh - VIEW_H, 0) + 200, 200):
            scroll_to(m, off); _, texts, _ = paint(m)
            for (t, r), s in texts:
                if s == 'label_row_title': names[r[1] + off] = t
        scroll_to(m, 0)
        return [names[y] for y in sorted(names)]
    def sub(m, k): return [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'vs_sub{k}']][-1:]
    def ticked(m): return [i for i in range(3) if dict((c[1], c[2]) for c in m.calls if c[0] == 'widget_set_visible').get(m.widgets[f'vs_tick{i}'])]
    def pick(m, row):
        click(m, 'btn_more'); m.calls.clear()
        return click(m, f'vs_item{row}')
    # the default: Name A-Z, folders first; the stock listing order is not shown
    m = fresh()
    expect(shown(m) == ORDERS[(0, 0)], f'no folders-sort: Name A-Z, folders first, digit runs by value, case folded ({shown(m)})')
    expect(m.statx_paths == [], 'Name reads no modification time')
    click(m, 'btn_more')
    expect(vis(m, 'vs_scrim') == (1, 1) and vis(m, 'vs_card') == (1, 1) and [vis(m, f'vs_item{i}') for i in (7, 0, 1, 2)] == [(1, 1)] * 4 and [vis(m, f'vs_item{i}') for i in (3, 4, 5, 6)] == [(0, 0)] * 4,
           'the \"...\" opens the card: Select, Name, Date Modified, Type; the fourth sort row, Grid, List and Search are hidden')
    expect(ticked(m) == [0] and sub(m, 0) == ['A–Z'] and all(m.props.get((m.widgets['vs_card'], f'style:{st}:bg_image')) == 'vs_glass4' for st in ('normal', 'pressed', 'over')) and vis(m, 'vs_hair')[0] == 1,
           'Name is ticked with A–Z under it; four rows in vs_glass4 with the one hairline under Select')
    # each row, then the ticked row again
    for k, (first, second) in enumerate((('A–Z', 'Z–A'), ('Newest First', 'Oldest First'), ('A–Z', 'Z–A'))):
        m = fresh()
        calls = pick(m, k)
        if k == 0:   # Name is the ticked default: its first tap reverses
            expect(m.fs.get(D + 'folders-sort') == b'a\n' and shown(m) == ORDERS[(0, 1)], 'the ticked Name again: Z–A saved as "a", the list reversed inside each group')
            calls = pick(m, 0)
            expect(m.fs.get(D + 'folders-sort') == b'0\n' and shown(m) == ORDERS[(0, 0)], 'and again: A–Z, "0"')
            continue
        expect(m.fs.get(D + 'folders-sort') == f'{k}\n'.encode() and ('rename', D + 'folders-sort.tmp', D + 'folders-sort') in calls and shown(m) == ORDERS[(k, 0)],
               f'row {k}: saved as "{k}" (atomic), shown {ORDERS[(k, 0)]}')
        click(m, 'btn_more')
        expect(ticked(m) == [k] and sub(m, k) == [first], f'row {k} is ticked with {first} under it')
        calls = pick(m, k)
        expect(m.fs.get(D + 'folders-sort') == 'abc'[k].encode() + b'\n' and shown(m) == ORDERS[(k, 1)], f'row {k} again: reversed, saved as "{"abc"[k]}", shown {ORDERS[(k, 1)]}')
        click(m, 'btn_more')
        expect(sub(m, k) == [second], f'the line under row {k} reads {second}')
    m = fresh()
    pick(m, 1)
    expect(sorted(m.statx_paths) == sorted(f'{SORT}/{n}' for n in MT), 'Date Modified: one statx per entry shown, the entry\'s path')
    # another row starts in its default direction
    m = fresh(b'c\n'); pick(m, 0)
    expect(m.fs.get(D + 'folders-sort') == b'0\n' and shown(m) == ORDERS[(0, 0)], 'from Type Z–A to Name: its default direction, A–Z')
    # the saved order at open, every level
    for data, want in ((None, (0, 0)), (b'0\n', (0, 0)), (b'1\n', (1, 0)), (b'2', (2, 0)), (b'a\n', (0, 1)), (b'b\n', (1, 1)), (b'c\n', (2, 1)), (b'x\n', (0, 0)), (b'3\n', (0, 0)), (b'd\n', (0, 0))):
        m = fresh(data)
        expect(shown(m) == ORDERS[want], f'folders-sort {data!r}: {want} {shown(m)}')
    m = fresh(b'c\n'); m.calls.clear()
    tap_row(m, shown(m).index('Alpha')); click(m, 'btn_return'); m.calls.clear()
    expect(shown(m) == ORDERS[(2, 1)], 'the saved order applies at every level: back in the folder it is Type Z–A still')
    # a failed save changes nothing
    m = fresh(); m.fail.add(('rename', D + 'folders-sort')); pick(m, 2)
    expect(shown(m) == ORDERS[(0, 0)] and D + 'folders-sort' not in m.fs, 'a save that fails changes nothing')
    # Play and the row taps follow the order shown; the queue is put in that order
    present = {f'{SORT}/{n}' for n in MT}
    for saved, order8 in ((None, ['2 x.mp3', '10 x.ogg', 'A.flac', 'b.mp3', 'c.FLAC']), (b'a\n', ['c.FLAC', 'b.mp3', 'A.flac', '10 x.ogg', '2 x.mp3']), (b'c\n', ['10 x.ogg', '2 x.mp3', 'b.mp3', 'A.flac', 'c.FLAC']),
                          (b'1\n', ['2 x.mp3', 'b.mp3', 'A.flac', 'c.FLAC', '10 x.ogg'])):
        m = fresh(saved); m.present.update(present); m.calls.clear()
        calls = click(m, 'btn_play')
        q = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.played[0]]
        expect(q == order8 and m.played[1] == 0, f'folders-sort {saved!r}: Play starts at the first file shown and the queue is the files in the order shown ({q}, {m.played[1]})')
        m = fresh(saved); m.present.update(present); m.calls.clear()
        rows = shown(m)
        calls = tap_row(m, rows.index('b.mp3'))
        q = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.played[0]]
        expect(q == order8 and q[m.played[1]] == 'b.mp3' and [c for c in calls if c[0] == 'loadSongList'][0][1] == 'b.mp3', f'folders-sort {saved!r}: the row b.mp3 plays at its place in that queue ({q}, {m.played[1]})')
    # Select and Select All use the order shown (marks by stock record), a folder's tap marks it
    m = fresh(b'a\n'); open_select(m); m.confirm_yes = True
    tap_row(m, 0)
    shown_recs = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.shown]
    calls = click(m, 'sg_del')
    expect([c[1] for c in calls if c[0] == 'set_selectindex'] == [shown_recs.index('zeta')], 'Z–A: the first row shown is zeta, the selection vector gets its stock record')
    m = fresh(b'a\n'); open_select(m); m.confirm_yes = True
    tap_row(m, 0); tap_row(m, 4)
    calls = click(m, 'sg_del')
    expect(sorted(c[1] for c in calls if c[0] == 'set_selectindex') == sorted(shown_recs.index(n) for n in ('zeta', 'c.FLAC')), 'rows 0 and 4 shown (zeta, c.FLAC; row 3 is the playlist file) are the records marked')
    # Date Modified is not offered where a level is too big to stat; the level shows by Name
    big = 2001   # one past FO_STAT_MAX (2000): the level is too big to stat
    TREE['/mnt/mmc/Big'] = [(T_FILE, f'f{i:04d}.mp3') for i in range(big - 1, -1, -1)] + [(T_DIR, 'Dir')]
    TREE['/mnt/mmc'].insert(0, (T_DIR, 'Big'))
    try:
        m = folder_machine(); m.measure = lambda t: 60
        open_page(m); enter(m, 'SD')
        for i, t in enumerate(pod_pages.FOLDERS_SORT_KEYS): m.wtext[m.widgets[f'vs_label{i}']] = t
        pick(m, 1)   # Date Modified saved (the SD level is small)
        m.statx_paths.clear(); tap_row(m, shown(m).index('Big'))
        names = shown(m)
        click(m, 'btn_more')
        expect(vis(m, 'vs_item1') == (0, 0) and [vis(m, f'vs_item{i}')[0] for i in (7, 0, 2)] == [1, 1, 1] and names[:3] == ['Dir', 'f0000.mp3', 'f0001.mp3'] and m.statx_paths == []
               and m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass3',
               f'{big} entries: no Date Modified row (three rows, vs_glass3), shown by Name, nothing stat-ed ({names[:3]})')
    finally:
        TREE['/mnt/mmc'].pop(0); del TREE['/mnt/mmc/Big']
    # the root has no card and Now Playing is the disc; a level of a playlist file has Select only and keeps its order
    m = fresh()
    expect(vis(m, 'btn_more') == (1, 1) and vis(m, 'btn_select') == (0, 0), 'inside a folder the \"...\" shows, Select does not')
    m.layer = 1; m.f_list(); m.calls.clear()
    fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=ctxp, a1=0, count=900000000)
    expect(vis(m, 'btn_more') == (0, 0) and vis(m, 'vs_card')[0] == 0 and m.props.get((m.widgets['label_title'], 'w'), 0) in (0, 260 - 58) , 'at the root: no \"...\"')
    m = fresh()
    m.u.mem_write(M3U, b'/mnt/mmc/Sort/Mix.m3u8\0')
    fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.layer = 2; m.f_list(); m.call(fn, a0=ctxp, a1=0, count=900000000)
    stock = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in m.shown]
    expect(vis(m, 'btn_select') == (1, 1) and vis(m, 'btn_more') == (0, 0) and vis(m, 'vs_card')[0] == 0 and shown(m) == stock,
           'a playlist file\'s tracks keep the file\'s order; the card would hold Select alone, so the navbar\'s Select button takes the "..." place (no card)')
    click(m, 'btn_select')
    expect(vis(m, 'sg_bar') == (1, 1) and vis(m, 'btn_selall') == (1, 1) and vis(m, 'vs_card')[0] == 0 and vis(m, 'btn_select') == (0, 0) and vis(m, 'btn_more') == (0, 0),
           'Select enters select mode at once, no card; Select is hidden there as the "..." was')
    click(m, 'btn_return')
    expect(vis(m, 'sg_bar')[0] == 0 and vis(m, 'btn_select') == (1, 1), 'leaving select mode brings Select back')


def cue_tests(ctx):
    """9. A CUE image's tracks (one path, a TITLE and a start each): shown together in the CUE's order where the image file sorts; the row tapped is the track played; the queue is the rows."""
    expect = ctx.expect
    CUE = '/mnt/mmc/Cue'
    B, A, INTRO = ['Zebra', 'Apple', 'Mango'], ['Kiwi', 'Fig'], ['01 intro.mp3']
    START = {'Zebra': 0, 'Apple': 300, 'Mango': 600, 'Kiwi': 0, 'Fig': 200, '01 intro.mp3': 0}
    ORDERS = {None: INTRO + A + B, b'a\n': B + A + INTRO,       # Name: the image's file name ("A side.flac", "B side.flac") places its tracks; Z-A keeps each image's own order
              b'1\n': B + INTRO + A, b'b\n': A + INTRO + B,     # Date Modified: the image's
              b'2\n': A + B + INTRO, b'c\n': INTRO + A + B}     # Type: the image's extension, then its name
    def shown(m):
        names, vh = {}, m.props.get((m.sv, 'virtual_h'), 0) or VIEW_H
        for off in range(0, max(vh - VIEW_H, 0) + 200, 200):
            scroll_to(m, off); _, texts, _ = paint(m)
            for (t, r), s in texts:
                if s == 'label_row_title': names[r[1] + off] = t
        scroll_to(m, 0)
        return [names[y] for y in sorted(names)]
    root = TREE['/mnt/mmc']
    TREE['/mnt/mmc'] = root[:1] + [(T_DIR, 'Cue')] + root[1:]
    try:
        for saved, files in ORDERS.items():
            for row, name in enumerate(files):
                m = folder_machine()
                m.mtimes = {f'{CUE}/Scans': 50, f'{CUE}/B side.flac': 300, f'{CUE}/01 intro.mp3': 200, f'{CUE}/A side.flac': 100}
                if saved is not None: m.fs['/mnt/data/m1plus/folders-sort'] = saved
                open_page(m); enter(m, 'SD'); tap_row(m, shown(m).index('Cue'))
                m.present.update(f'{CUE}/{n}' for n in ('A side.flac', 'B side.flac', '01 intro.mp3'))
                rows = shown(m)
                if row == 0: expect(rows == ['Scans'] + files, f'folders-sort {saved!r}: each image\'s tracks together in the CUE\'s order, placed as the image file ({rows})')
                calls = tap_row(m, 1 + row)
                ll = [c for c in calls if c[0] == 'loadSongList']
                q, idx = m.played if getattr(m, 'played', None) else ([], -1)
                qn = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in q]
                expect(ll == [('loadSongList', name, START[name], 1)] and qn == files and idx == row and m.word(q[idx] + O['REC_CUE_START']) == START[name],
                       f'folders-sort {saved!r}: a tap on {name} plays it (index {idx} of {qn}), the queue is the rows shown ({ll})')
        # Play: the first row's track
        m = opened(); enter(m, 'SD'); enter(m, 'Cue')
        m.present.update(f'{CUE}/{n}' for n in ('A side.flac', 'B side.flac', '01 intro.mp3'))
        m.calls.clear(); click(m, 'btn_play')
        q, idx = m.played if getattr(m, 'played', None) else ([], -1)
        expect(idx == 0 and [m.read_cstr(m.word(r + O['REC_NAME'])) for r in q] == ORDERS[None], f'Play: the first row, the queue in the rows\' order ({idx})')
    finally: TREE['/mnt/mmc'] = root


COVER_FLAG = pod.DATA['FOLDER_COVER'][0]
COV = dict(row=52, art=40, art_x=8, art_y=6, text_x=56, glyph_x=16, glyph_y=14, sel=30)   # the rows with stock's Folder cover switch on (patch/folders.c): the 52 px row and its text column, a 40 px cover at x 8, written out
LIB = [('/mnt/mmc/Music/01 So What.flac', 'Miles', 'Kind of Blue'), ('/mnt/mmc/Music/Kind of Blue/a.flac', 'Miles', 'Kind of Blue'),
       ('/mnt/mmc/Nested/Deep/x.flac', 'Band', 'Deep Album'), ('/mnt/mmc/Sort/b.mp3', 'Other', 'No Cover Album'), ('/mnt/mmc/Sort/A.flac', 'Other', 'No Cover Album'),
       ("/mnt/mmc/Sort/zeta/it's.flac", 'Quote', 'Quoted'), ('/mnt/mmc/Music/Mix.m3u8', 'Miles', 'Kind of Blue')]
COVERED = {'Kind of Blue': 'Miles', 'Deep Album': 'Band', 'Quoted': 'Quote'}   # the albums whose cache file holds a picture
PIX = {'Kind of Blue': 0xff112233, 'Deep Album': 0xff445566, 'Quoted': 0xff778899}


def cover_machine(flag=1, lib=LIB, covered=COVERED):
    """The folders machine over a library of tracks (the song rows of the query by path, the album rows of the cover map) with cache files for some albums."""
    m = folder_machine()
    m.u.mem_write(COVER_FLAG, bytes([flag]))
    m.class_lists[0xf001] = [m.record(album=al, artist=ar, path=p, name=p.rsplit('/', 1)[1]) for p, ar, al in lib]
    seen = []
    for _, ar, al in lib:
        if (ar, al) not in seen: seen.append((ar, al))
    m.class_lists[O['CLASS_ALBUMS']] = [m.record(album=al, artist=ar, path=f'/mnt/mmc/lib/{i}.flac', rid=900 + i) for i, (ar, al) in enumerate(seen)]
    for al, ar in covered.items():
        f = art_file(album_key(ar, al)); m.present.add(f); m.files[f] = 4096
        m.images['file://' + f] = (8, 8, struct.pack('<I', PIX[al]) * 64)
    m.cover_urls = {al: 'file://' + art_file(album_key(ar, al)) for al, ar in covered.items()}
    return m


def settle_covers(m, limit=200):
    """The loader's timer fires until it stops re-arming (one row a tick)."""
    for n in range(limit):
        m.calls.clear(); m.call(PSYMS['fo_on_load'], count=80000000)
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['fo_on_load'] for c in m.calls): return n + 1
    return limit


def enter64(m, name):
    """Tap the shown row called name on a level with covers (the rows are 52 px apart)."""
    recs = sorted((r for r in m.shown if not m.read_cstr(m.word(r + O['REC_NAME'])).startswith('.')), key=lambda r: (m.s32(r + O['REC_TYPE']) in (T_FILE, T_LIST), m.read_cstr(m.word(r + O['REC_NAME'])).lower()))
    names = [m.read_cstr(m.word(r + O['REC_NAME'])) for r in (m.shown if m.layer <= 1 else recs)]   # (the storages keep their order)
    top = TOP if any(m.s32(r + O['REC_TYPE']) == T_FILE for r in m.shown) else TOP_PLAIN
    m.calls.clear()
    y = top + names.index(name) * COV['row'] + 20
    off = max(0, y - VIEW_H + 40)   # (a row below the view: the list is scrolled first)
    if off: scroll_to(m, off)
    return tap(m, 100, y - off)


def cover_tests(ctx):
    """9. Folder / file covers (stock's Folder cover switch): off = the rows as before, no query; on = the same rows with a 40 px cover in place of the glyph, a file's album cover, a folder's cover from the first library
    track under it (a folder of sub-folders too), the glyph in the cover's box for the rest, storages and playlist files with glyphs, select mode, a library that cannot be read."""
    expect = ctx.expect
    root = TREE['/mnt/mmc']
    TREE['/mnt/mmc'] = root[:1] + [(T_DIR, 'Nested')] + root[1:]
    TREE['/mnt/mmc/Nested'] = [(T_DIR, 'Deep')]
    TREE['/mnt/mmc/Nested/Deep'] = [(T_FILE, 'x.flac')]
    TREE['/mnt/mmc/Sort/zeta'] = [(T_FILE, "it's.flac")]
    try:
        # off: the rows are the old ones, the library is never asked, no timer
        m = cover_machine(flag=0)
        open_page(m); enter(m, 'SD'); enter(m, 'Sort')
        blits, texts, fills = paint(m)
        ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
        expect(ttl[0] == ('Alpha', (TEXT_X, TOP + TEXT_Y, TEXT_END - TEXT_X, O['LIST_TITLE_H'])) and [b[2][:2] for b in blits if b[2][2] == ICON][:2] == [(ICON_X, TOP + ICON_Y), (ICON_X, TOP + ROW + ICON_Y)],
               'the switch off: the rows are the 52 px rows with the glyph at x 16 and the name at x 56')
        expect(not [c for c in m.calls if c[0] == 'toolsQueryDbTable'] and not [b for b in blits if b[2][2] == COV['art']] and not any(c[0] == 'timer_add' and c[1] == PSYMS['fo_on_load'] for c in m.calls),
               'the switch off: no library query, no cover, no loader timer')
        expect(not any(q for q in m.__dict__.get('queries', [])), 'the switch off: the database is not asked')

        # on: the SD level (Music has a track under it, Nested holds only a sub-folder, Blank / Podcasts / Sort have no cover)
        m = cover_machine()
        open_page(m); enter(m, 'SD')
        rows = ['Blank', 'Music', 'Nested', 'Podcasts', 'Sort', 'readme.mp3']
        inview = [i for i in range(len(rows)) if TOP + i * COV['row'] < VIEW_H - COV['row']]   # (the rows in view are the ones looked up)
        n = settle_covers(m)
        expect(n <= len(inview) + 1 and len(inview) >= 4, f'one row a tick: {n} ticks for {len(inview)} rows in view')
        blits, texts, fills = paint(m)
        art = {tuple(b[2][:2]): b for b in blits if b[2][2] == COV['art'] and b[2][3] == COV['art']}
        glyph = {tuple(b[2][:2]) for b in blits if b[2][2] == ICON}
        want_art = {'Music': PIX['Kind of Blue'], 'Nested': PIX['Deep Album']}
        for i, name in enumerate(rows):
            y = TOP + i * COV['row']
            if i not in inview: continue
            if name in want_art:
                expect((COV['art_x'], y + COV['art_y']) in art and (COV['glyph_x'], y + COV['glyph_y']) not in glyph, f'{name}: the 40 px cover at x 8, no glyph')
            else:
                expect((COV['art_x'], y + COV['art_y']) not in art and (COV['glyph_x'], y + COV['glyph_y']) in glyph, f'{name}: no cover, the glyph where the switch off draws it (x 16)')
        expect(len(art) == 2, f'two covers ({len(art)})')
        loads = [u for u in m.loads if u.startswith('file://')]
        expect(sorted(loads) == sorted([m.cover_urls['Kind of Blue'], m.cover_urls['Deep Album']]), f'the album\'s cache file, nothing else decoded ({loads})')
        ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
        expect(ttl[1] == ('Music', (COV['text_x'], TOP + COV['row'] + (COV['row'] - O['LIST_TITLE_H']) // 2, TEXT_END - COV['text_x'], O['LIST_TITLE_H'])), f'the name at x 56, centred in the 52 px row ({ttl[1]})')
        hair = [f_ for f_ in fills if f_[0] == O['LIST_HAIR']]
        expect(hair[0][1:] == (COV['text_x'], TOP + COV['row'] - 1, 320 - 10 - COV['text_x'], 1), f'the hairline from the text, at the 52 px row\'s foot ({hair[0]})')
        chev = [b for b in blits if b[2][2] == PF.O.get('POD_CHEV_W', 10) and b[2][3] == 16]
        expect(len(chev) >= 4 and chev[0][2][1] == TOP + (COV['row'] - 1 - 16) // 2, 'the chevron of each folder, centred in the row')
        expect(m.props.get((m.sv, 'virtual_h')) == TOP + len(rows) * COV['row'] + 24, 'the content is as tall as with the switch off')
        qs = [q for q in m.queries if q.startswith('select * ')]
        want_qs = [f"select * from songtable where fileurl>='/mnt/mmc/{d}/' and fileurl<'/mnt/mmc/{d}0' order by fileurl limit 1" for d in ('Blank', 'Music', 'Nested', 'Podcasts', 'Sort')]
        want_qs.append("select * from songtable where fileurl='/mnt/mmc/readme.mp3' limit 1")   # (every row is in view: the 52 px rows)
        expect(sorted(qs) == sorted(want_qs)
               and sum(1 for q in m.queries if q == pod.ALBUM_SQL) == 1,
               f'one lookup a row in view (a folder by the first path of its range) and ONE album query for the page ({qs})')
        expect(m.word(SHOWLIST) == m.shown_h, 'the page\'s list is untouched by the lookups')
        # a tap still enters a folder
        m.calls.clear(); tap(m, 100, TOP + 1 * COV['row'] + 30)
        expect(('folder_enter', 3, 0) in m.calls, f'a tap on the second row enters Music ({[c for c in m.calls if c[0] == "folder_enter"]})')
        # Music: a file's cover (its album), the folder under it, the playlist file and a file the library lacks
        settle_covers(m)
        blits, texts, fills = paint(m)
        names = [t for (t, r), s in texts if s == 'label_row_title']
        art = {tuple(b[2][:2]) for b in blits if b[2][2] == COV['art']}
        top = TOP
        got = [(COV['art_x'], top + i * COV['row'] + COV['art_y']) in art for i, nm in enumerate(names)][:len(inview)]
        expect(got == [True, True, False, False, False][:len(inview)],
               f'Music: the folder and the file in the library have covers; files the library lacks and the playlist file have the glyph ({got})')
        # a path with a quote; the folder of one file
        m = cover_machine(); open_page(m); enter64(m, 'SD'); enter64(m, 'Sort'); enter64(m, 'zeta'); settle_covers(m)
        expect("select * from songtable where fileurl='/mnt/mmc/Sort/zeta/it''s.flac' limit 1" in getattr(m, 'queries', []) or any("it''s" in q for q in getattr(m, 'queries', [])), 'a quote in a path is doubled')
        # storages and playlist files: no lookup
        m = cover_machine(); open_page(m)
        settle_covers(m)
        blits, texts, fills = paint(m)
        expect([b[2][:2] for b in blits if b[2][2] == ICON][:3] == [(COV['glyph_x'], TOP_PLAIN + i * COV['row'] + COV['glyph_y']) for i in range(3)] and not [b for b in blits if b[2][2] == COV['art']],
               'the storages: the glyphs at x 16 as with the switch off')
        expect(not [q for q in getattr(m, 'queries', []) if 'songtable' in q], 'the storages are never looked up')
        # select mode: the covers and glyphs move right by the mark column, the text with them
        m = cover_machine(); open_page(m); enter64(m, 'SD'); settle_covers(m)
        open_select(m)
        blits, texts, fills = paint(m)
        art = {tuple(b[2][:2]) for b in blits if b[2][2] == COV['art']}
        expect({(COV['art_x'] + COV['sel'], TOP + COV['row'] + COV['art_y']), (COV['art_x'] + COV['sel'], TOP + 2 * COV['row'] + COV['art_y'])} == art, f'select mode: the covers move right by the mark column ({art})')
        ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
        expect(ttl[0][1][0] == COV['text_x'] + COV['sel'], 'and the names with them')
        marks = [b for b in blits if b[2][2] == O['SG_MARK']]
        expect(len(marks) >= 4 and marks[0][2][1] == TOP + (COV['row'] - O['SG_MARK']) // 2, f'the marks are centred in the row ({[b[2] for b in marks[:2]]})')
        # the playing wave and the press fill keep their places
        m = cover_machine(); m.playing_dir = '/mnt/mmc/Music/x.flac'; open_page(m); enter(m, 'SD'); settle_covers(m)
        touch(m, 'down', 100, SCREEN_Y0 + TOP + COV['row'] + 20, 'fo_on_down')
        blits, texts, fills = paint(m)
        wave = [b for b in blits if b[2][0] == MARK_X_CHEV]
        expect(len(wave) == 1 and wave[0][2][1] == TOP + COV['row'] + (COV['row'] - ICON) // 2, f'the wave of the folder that plays, at x 254, centred in the row ({wave})')
        expect([f_ for f_ in fills if f_[0] == O['LIST_PRESS']] == [(O['LIST_PRESS'], 0, TOP + COV['row'], 320, COV['row'] - 1)], 'the press fill covers the row')
        # the switch turned on while the page is behind: back in front, the rows are made again
        m = cover_machine(flag=0); open_page(m); enter(m, 'SD')
        m.u.mem_write(COVER_FLAG, bytes([1]))
        fn, ctxp = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=ctxp, a1=0, count=900000000); settle_covers(m)
        expect(len([b for b in paint(m)[0] if b[2][2] == COV['art']]) == 2, 'the switch turned on elsewhere: the covers show when the page is in front again')
        # memory short / no library: the glyphs, no crash
        m = cover_machine(); open_page(m); enter64(m, 'SD'); m.calloc_fail = True; settle_covers(m)
        blits, texts, fills = paint(m)
        expect(not [b for b in blits if b[2][2] == COV['art']] and len([b for b in blits if b[2][2] == ICON]) >= 4, f'no memory for the cover map: every row keeps its glyph ({len([b for b in blits if b[2][2] == ICON])})')
        m = cover_machine(lib=[], covered={}); open_page(m); enter(m, 'SD'); settle_covers(m)
        expect(not [b for b in paint(m)[0] if b[2][2] == COV['art']], 'no library: the glyphs')
        m = cover_machine(); m.album_query_fails = True; open_page(m); enter(m, 'SD'); settle_covers(m)
        expect(not [b for b in paint(m)[0] if b[2][2] == COV['art']], 'the album query fails: the glyphs')
        # the longest path looked up, all apostrophes: the query holds it twice with every apostrophe doubled
        q = "'" * (F['FO_SQL_PATH'] - 1 - len('/mnt/mmc/Q/'))
        TREE['/mnt/mmc/Q'] = [(T_DIR, q)]; TREE['/mnt/mmc/Q/' + q] = []
        TREE['/mnt/mmc'] = TREE['/mnt/mmc'] + [(T_DIR, 'Q')]
        m = cover_machine(lib=LIB + [(f'/mnt/mmc/Q/{q}/t.flac', 'Quote', 'Quoted')]); open_page(m); enter64(m, 'SD'); enter64(m, 'Q'); settle_covers(m)
        esc = ('/mnt/mmc/Q/' + q).replace("'", "''")
        expect(f"select * from songtable where fileurl>='{esc}/' and fileurl<'{esc}0' order by fileurl limit 1" in m.queries, f'a {len(q) + 11} byte path of apostrophes is asked whole ({[len(x) for x in m.queries]})')
        expect(len([b for b in paint(m)[0] if b[2][2] == COV['art']]) == 1, 'and its cover shows')
        # a library of 20000 tracks, a level of 2000 entries: a tick looks up one row, never the whole level
        big = [(f'/mnt/mmc/Big/d{i % 2000:04d}/t{i}.flac', f'A{i % 50}', f'B{i % 50}') for i in range(2000)]
        TREE['/mnt/mmc/Big'] = [(T_DIR, f'd{i:04d}') for i in range(2000)]
        TREE['/mnt/mmc'] = TREE['/mnt/mmc'] + [(T_DIR, 'Big')]
        m = cover_machine(lib=big, covered={}); open_page(m); enter64(m, 'SD'); enter64(m, 'Big')
        settle_covers(m, limit=400)
        nq = len([q for q in m.queries if 'fileurl' in q])
        expect(nq <= 20, f'a 2000 entry level looks up only the rows in view ({nq} lookups)')
    finally:
        TREE['/mnt/mmc'] = root
        for k in [k for k in TREE if k.startswith(('/mnt/mmc/Nested', '/mnt/mmc/Sort/zeta', '/mnt/mmc/Big', '/mnt/mmc/Q'))]: TREE.pop(k, None)


SECTIONS = [asset_tests, open_tests, rows_tests, levels_tests, play_tests, select_tests, stale_tests, order_tests, cue_tests, cover_tests]   # tools/check.py runs each as its own task

"""Playlists: the menu row, the page's structure (a stock list_view > scroll_view holding the one content view, the "..." button and its popup),
the playlists read from the stock query, the mosaic of each playlist's album covers (0, 1, 2, 3, 5+ albums; one source decoded per tick; a
playlist with no songs; the library lookup for an album whose track carries another artist), the names and track counts, the tap that opens a
playlist in the stock songs page, the loader that decodes nothing while the scroll_view moves, reading again when the window comes back to
the front, the empty page, and the menu's actions routed to the stock code (create, import, export, delete)."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

SCREEN_Y0 = 30 + 50
COVER, GAP, MARGIN, COLS = O['GRID_COVER'], O['GRID_GAP'], O['GRID_MARGIN'], O['GRID_COLS']
TGAP, THEIGHT, VIEW_H, TILES = O['GRID_TITLE_GAP'], O['GRID_TITLE_H'], O['GRID_VIEW_H'], O['GRID_TILES']
RGAP, SUBH = O['GRID_ROW_GAP'], O['GRID_SUB_H']
TOP = O['SG_TITLE_H']     # the large title block (pl_title) the content starts with; the rows and cells follow it
R0 = TOP + RGAP           # the content y of the first grid row
CELL = COVER + TGAP + THEIGHT + SUBH
PITCH = CELL + RGAP
CPITCH = COVER + GAP
SVW, CW = 310, 320
SC_YOFF, SC_VH = O['SC_YOFF'], 0x7c
CARD_WIDGETS = tuple(dict.fromkeys(VS_WIDGETS + ('vs_item8', 'vs_item9', 'vs_label8', 'vs_label9', 'vs_glyph8', 'vs_glyph9')))   # the shared "..." card's widgets (btn_more among them) and the Playlists asset's two extra action rows
CARD_TEXTS = ('Name', 'Name', 'Name', 'Name', 'Grid', 'List') + tuple(pod_pages.PLAYLIST_MENU)   # vs_label0..9
A_NEW, A_IMPORT, A_EXPORT, A_DELETE, V_GRID, V_LIST = 'vs_item6', 'vs_item7', 'vs_item8', 'vs_item9', 'vs_item4', 'vs_item5'
HALF = COVER // 2
REC_DISC = O['REC_DISC']
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_playlists.bin') if WORK else None
NAV_STATUS, CLASSINFO = pod.DATA['NAVIGATION_STATUS'][0], pod.DATA['CLASSINFO'][0]
PL_FILE = '/mnt/data/m1plus/playlists-view'
GREY_DISC = 0xff404040     # the stock placeholder disc of these tests (p_default, flat)


def colour(i):
    """The flat colour of album i's cover (a 32 bit RGBA word, as the decoder leaves it)."""
    return 0xff000000 | (i * 37 % 256) | (i * 59 % 256) << 8 | (i * 83 % 256) << 16


def near(a, b, tol=2):
    return all(abs(((a >> s) & 255) - ((b >> s) & 255)) <= tol for s in (0, 8, 16, 24))


def alb(i): return f'Artist {i}', f'Album {i}'


def key_path(artist, album): return art_file(fnv(fnv(O['FNV_SEED'], artist), album) or 1)


class LabelMachine(SelectMachine):
    """The menu labels' texts (label_text: handle -> text, widget_get_text's wide string) and their widths (measure: text -> px, None: the
    measure fails and returns 0), as widget_measure_text returns them (a float in $f0)."""

    def __init__(self):
        super().__init__()
        self.label_text, self.measure, self.measured = {}, None, []
        self.db = {'/mnt/data/database.db': [100, 0, 4096]}   # path -> [mtime, nsec, size]: what __xstat answers (the page's database signature)
        for n in ('widget_get_text', 'widget_measure_text'):
            self.handlers[pod.FUNCTIONS[n][2]] = n

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1), u.reg_read(UC_MIPS_REG_A2)
        if name.startswith('fake_pl_'):
            ret = self.fake_pl(name, a0, a1, a2, u.reg_read(UC_MIPS_REG_A3), self.word(u.reg_read(UC_MIPS_REG_SP) + 16), self.word(u.reg_read(UC_MIPS_REG_SP) + 20))
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'widget_get_text':
            t, ret = self.label_text.get(a0), 0
            if t is not None:
                ret = self.alloc(4 * len(t) + 4); self.u.mem_write(ret, struct.pack(f'<{len(t) + 1}I', *map(ord, t), 0))
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == '__xstat':
            path = self.read_cstr(a1); self.calls.append(('__xstat', path))
            ret = 0xffffffff
            if path in self.db:
                self.u.mem_write(a2, bytes(144)); mt, ns, sz = self.db[path]
                self.setword(a2 + 0x40, mt); self.setword(a2 + 0x44, ns); self.setword(a2 + 0x30, sz); ret = 0
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'widget_measure_text':
            n = 0
            while self.word(a1 + 4 * n): n += 1
            t = ''.join(map(chr, struct.unpack(f'<{n}I', self.u.mem_read(a1, 4 * n)))) if n else ''
            w = float(self.measure(t)) if self.measure and t else 0.0
            self.measured.append((a0, t))
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


    FAKE = ('list', 'rec_id', 'play', 'cover', 'seconds', 'row', 'act', 'gen')

    def fake_src(self):
        """A lib_src_t of fake_pl_ functions (a `jr ra` each at a trapped address) over the machine's playlists (self.playlists, self.playlist_songs): list, rec_id, play, cover (the
        cache file by key: 1 present, 0 asked while the key is in fake_ask, else -1), gen (fake_gen). Calls land in self.fake_calls."""
        self.fake_calls, self.fake_ask, self.fake_gen = [], set(), 5
        self.top_main = self.window   # pod_is_top: the page is in front (the shared cover poll only runs then)
        self.fake_song_ret = -1   # what songs_open_src_in answers: -1 (the page did not open, the playlist plays), 0 (opened)
        self.fake_state_all = 0   # what src->state(LS_PLAYLISTS, NULL) answers (LS_ST_*)
        self.fake_no_list, self.playlist_counts = set(), {}   # playlists whose tracks are not cached yet, and the sync's songCounts
        src = self.alloc(60)
        self.u.mem_write(src, bytes(60))
        self.setword(src, self.cstr('fake'))
        for i, f in enumerate(self.FAKE):
            a = self.alloc(8); self.u.mem_write(a, struct.pack('<II', 0x03e00008, 0))
            self.handlers[a] = 'fake_pl_' + f
            self.setword(src + 4 * (i + 1), a)
        a = self.alloc(8); self.u.mem_write(a, struct.pack('<II', 0x03e00008, 0))
        self.handlers[a] = 'fake_pl_count'
        self.setword(src + 52, a)   # lib_src_t.count (offset 52, after caps)
        a = self.alloc(8); self.u.mem_write(a, struct.pack('<II', 0x03e00008, 0))
        self.handlers[a] = 'fake_pl_state'
        self.setword(src + 56, a)   # lib_src_t.state (offset 56, the last member)
        self.fake_src_ptr = src
        self.handlers[PSYMS['songs_open_src_in']] = 'fake_pl_songs'   # the playlist's Songs page: recorded, not run
        return src

    def fake_pl(self, name, a0, a1, a2, a3, s0, s1):
        if name == 'fake_pl_list':   # (s, which, scope)
            self.fake_calls.append(('list', a1, a2))
            if a1 != 3: return 0
            if not a2: return self.new_deque(self.playlists) if self.playlists else 0
            pid = self.word(a2 + REC_DISC)
            if pid in self.fake_no_list: return 0   # (not fetched yet)
            sg = self.playlist_songs.get(pid)
            return self.new_deque(sg) if sg else 0
        if name == 'fake_pl_count':   # (s, which, scope): the sync's songCount while the list is not cached
            self.fake_calls.append(('count', a1, a2))
            if a1 != 3: return 0
            return self.playlist_counts.get(self.word(a2 + REC_DISC), 0)
        if name == 'fake_pl_state':   # (s, which, scope): a playlist whose tracks are not cached is loading
            if a1 == 3 and not a2:
                self.fake_calls.append(('state', a1, a2)); return self.fake_state_all   # the whole list
            return 1 if a1 == 3 and a2 and self.word(a2 + REC_DISC) in self.fake_no_list else 0
        if name == 'fake_pl_rec_id': return self.cstr('pl%d' % self.word(a1 + REC_DISC))
        if name == 'fake_pl_gen': return self.fake_gen
        if name == 'fake_pl_cover':   # (s, rec, key, path, cap)
            p = art_file(a2)
            self.fake_calls.append(('cover', a2))
            if p in self.present:   # (the source's file: Navidrome's folder, named by the 8 hex digits of the key the page reads it back by)
                n = '/mnt/mmc/.m1plus/subsonic/covers/%08x-168.jpg' % a2
                self.present.add(n); self.files[n] = self.files.get(p, 4096)
                if 'file://' + p in self.images: self.images['file://' + n] = self.images['file://' + p]
                self.u.mem_write(a3, n.encode() + b'\0'); return 1
            return 0 if a2 in self.fake_ask else -1
        if name == 'fake_pl_play':   # (s, list, at, how, open, cls)
            self.fake_calls.append(('play', [self.read_cstr(self.word(r + O['REC_TITLE'])) for r in self.deques[a1]], a2, a3, s1))
            return 0
        if name == 'fake_pl_songs':   # songs_open_src_in (src, which, scope, title)
            self.fake_calls.append(('songs', a0 == self.fake_src_ptr, a1, self.read_cstr(self.word(a2 + O['REC_TITLE'])), self.read_cstr(a3)))
            return self.fake_song_ret
        return 0


class PM:
    """A machine with the page's widgets as widget structs (window > list_view > scroll_view > view_grid, for demo's own widget_to_local), the library's
    albums (cover files for the albums not in `missing`), and the playlists given as [(id, name, [album numbers of its songs])]."""

    def __new__(cls, lists, albums=8, missing=(), other_artist=(), window=0x20001000):
        m = LabelMachine()
        m.fs[SORT_FILE] = b'0\n'
        m.load_image = 0
        for w in ('btn_return', 'btn_backtoplayer', 'label_row_title', 'label_row_sub', 'view_grid', 'label_status', 'label_grid_title', 'label_grid_sub', 'label_title', 'pl_title', 'img_nb_fade', 'btn_selall', 'pl_bar', 'pl_del', 'btn_plactions', 'pl_spin') + CARD_WIDGETS: Machine.widget(m, w)
        m.setword(m.widgets['label_title'] + 8, O['NAV_CF_X'] - O['NAV_TITLE_X']); m.setword(m.widgets['pl_title'] + 8, O['SG_TITLE_W'])   # the labels' widths (az_fit cuts to them)
        m.label_text[m.widgets['pl_del']] = 'Delete'   # the text the asset gives the pill
        for i, text in enumerate(CARD_TEXTS): m.label_text[m.widgets[f'vs_label{i}']] = text
        for i in range(4): m.label_text[m.widgets[f'vs_sub{i}']] = 'A–Z'
        m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
        m.images = {'p_default': (24, 24, bytes((0x40, 0x40, 0x40, 255)) * (24 * 24)), 'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676),
                    'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)}
        m.lib = [m.record(album=alb(i)[1], artist=alb(i)[0], path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i in range(albums)]
        m.class_lists[O['CLASS_ALBUMS']] = m.lib
        for i in range(albums):
            if i in missing: continue
            p = key_path(*alb(i))
            m.present.add(p); m.files[p] = 4096
            c = colour(i)
            m.images['file://' + p] = (24, 24, struct.pack('<I', c) * (24 * 24))
        m.playlists, m.playlist_songs = [], {}
        for pid, name, songs in lists: PM.add(m, pid, name, songs, other_artist)
        # the page as widget structs, for the stock widget_to_local
        win, lv, sv = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180)
        m.u.mem_write(sv, bytes(0x180))
        for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
            for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
        m.setword(sv + 8, SVW)
        m.widgets['playlists_scrollview'] = sv
        view = m.widgets['view_grid']
        for off, v in ((4, 0), (8, CW), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
        m.mem_geometry, m.live_scroll = True, frozenset({sv})
        m.sv = sv
        return m

    @staticmethod
    def rec(m, pid, name, songs=0):
        rec = m.record(album='', artist='', title=name, rid=pid)
        m.setword(rec + REC_DISC, pid)
        m.setword(rec + 0x28, m.cstr('p\t\t%d\t0' % songs))   # REC_META: a source's row data, "p<TAB>cover<TAB>songs<TAB>seconds"
        return rec

    @staticmethod
    def add(m, pid, name, songs, other_artist=()):
        m.playlists.append(PM.rec(m, pid, name, len(songs)))
        m.playlist_songs[pid] = [m.record(album=alb(a)[1], artist='Other' if a in other_artist else alb(a)[0], path=f'/mnt/mmc/m/{a}/1.flac',
                                          title=f'T{k}', rid=1000 + k) for k, a in enumerate(songs)]


def open_page(m):
    m.call(PSYMS['playlists_open'], count=60000000)
    return list(m.calls)


def chevs_of(m, blits):
    """The blits of the shared chevron bitmap (POD_CHEV_W x POD_CHEV_H) among a frame's."""
    return [b for b in blits if m.bitmaps[b[0]][1:] == (10, 16)]


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts, styles) of that frame, the canvas where the scroll_view leaves it."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['pl_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(m.texts), list(m.text_styles)


def tick(m):
    m.call(PSYMS['pl_on_load'], count=40000000)
    return list(m.calls)


def settle(m, limit=200, log=None):
    """Fire the loader's timer until it stops re-arming itself; the decodes per tick (at most one), then a paint. `log` collects every tick's calls."""
    most = 0
    for _ in range(limit):
        calls = tick(m)
        if log is not None: log.extend(calls)
        most = max(most, sum(1 for c in calls if c[0] == 'widget_load_image' and c[1] not in ('p_default', 'unselect', 'selected')))
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['pl_on_load'] for c in calls):
            m.most_per_tick = most
            return paint(m)
    raise AssertionError('the page never finished loading')


def pixel(m, bmp, x, y):
    data, w, h = m.bitmaps[bmp]
    return struct.unpack('<I', m.u.mem_read(data + (y * w + x) * 4, 4))[0]


def quadrants(m, bmp, side=COVER):
    h = side // 2
    return [pixel(m, bmp, x, y) for y in (h // 2, h + h // 2) for x in (h // 2, h + h // 2)]


def scroll_to(m, v):
    """The scroll_view's offset to v, and the page told as the stock setter's EVT_SCROLL tells it."""
    m.setword(m.sv + SC_YOFF, v)
    fn, ctx = m.bound[(m.sv, O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=40000000)


def cell_blit(blits, i, off=0):
    x, y = MARGIN + (i % COLS) * CPITCH, R0 + (i // COLS) * PITCH - off
    return next((b[0] for b in blits if b[2][0] == x and b[2][1] == y and b[2][2] == COVER), None)


def want_mosaic(distinct):
    n = len(distinct)
    if n == 0: return None
    c = [colour(a) for a in distinct]
    return [c[0]] * 4 if n == 1 else [c[0], c[1], c[1], c[0]] if n == 2 else [c[0], c[1], c[2], c[0]] if n == 3 else c[:4]


def tap(m, x, y, dx=0, dy=0):
    m.touch('down', x, SCREEN_Y0 + y, 1000, fn='pl_on_down')
    m.touch('up', x + dx, SCREEN_Y0 + y + dy, 1080, fn='pl_on_up')
    return list(m.calls)


def glass_users(expect):
    """pl_glass.png (the old Playlists menu's pane) is no longer the Playlists page's: the "..." card is the shared view-sort card; the two dialogs that borrow pl_glass still use it."""
    users = []
    ui_root = os.path.join(WORK, 'rootfs', 'release/assets')
    for base, _, files in os.walk(ui_root):
        users += [os.path.relpath(os.path.join(base, f), ui_root) for f in files if f.endswith('.bin') and b'pl_glass' in open(os.path.join(base, f), 'rb').read()]
    expect(sorted(users) == ['default/raw/ui/m1plus_podcasts.bin', 'default/raw/ui/m1plus_update.bin'], f'pl_glass is used by the two dialogs that borrow its card (the Podcasts refresh, the Software Update download popup) only ({users})')


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def glyph(m):
    """What the old toggle showed: the glyph of the view a tap switches to (pod_nav_list on the grid), read off the card's tick on Grid / List."""
    m.click('btn_more'); grid = vis(m, 'vs_tick4')[0]; m.click('vs_scrim')
    return 'pod_nav_list' if grid else 'pod_nav_grid'


def switch(m, count=60000000):
    """The other view, from the card: the \"...\" opens it, the row of the view not ticked is tapped."""
    m.click('btn_more'); grid = vis(m, 'vs_tick4')[0]
    m.click(V_LIST if grid else V_GRID, count=count)


MARK, SEL_COL = O['SG_MARK'], O['SG_SEL_COL']
SEL_VEC, PDEQ_PLAYLIST = pod.DATA['SEL_VEC'][0], pod.DATA['PDEQ_PLAYLIST'][0]


def marks_of(blits):
    """The select marks painted: (x, y, bitmap) of every 26 px blit."""
    return sorted((b[2][0], b[2][1], b[0]) for b in blits if b[2][2] == MARK and b[2][3] == MARK)


def select_tests(expect, lists):
    """Delete Playlists is select mode on this page (the Songs page's manner): the navbar's x, "N Selected", Select All, a mark on every cell or row, a bar with the Delete
    pill; Delete runs the stock handler's sequence (@0x53dbcc) on the stock selection vector: the message when nothing is marked, the stock confirm dialog (Yes 0xa),
    batch_delete_file(0xf00b, *pdeq_playlist, the vector, 0, 0), the success message; the page reads again. Where the page cannot do it the stock page opens."""
    names = ('btn_return', 'btn_plactions', 'btn_more', 'btn_backtoplayer')
    # the asset: the select widgets start hidden and insensitive, the bar is the Songs page's (black, a hairline, the flat pill), the popup stays last
    tree = awtk_ui.parse(open(UI, 'rb').read())
    sa, bar, line, pill = (tree.find(n) for n in ('btn_selall', 'pl_bar', 'pl_bar_line', 'pl_del'))
    expect(sa.type == 'button' and (sa.x, sa.y, sa.w, sa.h) == (O['SG_SELALL_X'], 0, 104, O['NAV_H']) and sa.get('visible') == 'false' and sa.get('sensitive') == 'false'
           and sa in tree.find('navigationbar_view').children, 'Select All is the Songs page\'s text button in the navbar, hidden and insensitive')
    expect(bar.type == 'view' and (bar.x, bar.y, bar.w, bar.h) == (0, 450 - O['SG_BAR_H'], 320, O['SG_BAR_H']) and bar.get('visible') == 'false' and bar.get('sensitive') == 'false'
           and line in bar.children and line.get('sensitive') == 'false' and pill in bar.children
           and (pill.x, pill.y, pill.w, pill.h) == (O['SG_PILL_X0'], (O['SG_BAR_H'] - O['SG_PILL_H']) // 2, O['PL_BAR_PILL_W'], O['SG_PILL_H']) and pill.get('style:normal:icon') == 'sg_trash'
           and pill.get('style:normal:round_radius') == str(O['SG_PILL_R']), 'the bar is the Songs page\'s (64 px, a hairline) with one Delete pill across it, hidden and insensitive')
    kids = tree.children
    expect(kids.index(bar) > kids.index(tree.find('playlists_listview')) and kids.index(bar) < kids.index(tree.find('vs_scrim')), 'the bar lies over the list and under the popup')

    # entering: from the menu's Delete Playlists row (the card closes); the navbar, the bar, the title, the marks
    m = PM(lists, missing=(7,)); open_page(m)
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_create_ex' and c[1:3] == (MARK, MARK)) == 2 and ('widget_set_visible', m.widgets['pl_bar'], 1) not in m.calls,
           'select mode is off at open (the asset starts its widgets hidden and insensitive); the two marks are decoded once')
    settle(m)
    m.click('btn_plactions'); m.calls = []
    m.click('vs_item9')
    calls = list(m.calls)
    t, back = m.widgets['label_title'], m.widgets['btn_return']
    expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'btn_selall') == (1, 1) and vis(m, 'pl_bar') == (1, 1) and all(vis(m, n) == (0, 0) for n in ('btn_plactions', 'btn_more', 'btn_backtoplayer')),
           'the menu closes; Select All and the bar show; the list-plus button, "..." and Now Playing go (hidden and insensitive)')
    expect(vis(m, 'btn_return') != (0, 0) and m.props.get((back, 'style:normal:icon')) == 'ah_nav_close' and m.props.get((back, 'style:pressed:icon')) == 'ah_nav_close_down',
           'Back becomes the glass x')
    expect(('widget_set_text_utf8', t, '0 Selected') in calls and ('widget_resize', t, O['SG_SELALL_X'] - O['NAV_TITLE_X'], 22) in calls, 'the title reads 0 Selected and runs to Select All')
    expect('stock_resume' not in [c[0] for c in calls], 'the stock Playlists page is not opened')
    expect(m.props.get((m.sv, 'virtual_h')) == R0 + 3 * PITCH + O['SG_BAR_H'], 'the content is the bar\'s height longer, so the last row scrolls clear of it')
    blits, texts, styles = paint(m)
    mk = marks_of(blits)
    want = [(MARGIN + (i % COLS) * CPITCH + COVER - MARK - 6, R0 + (i // COLS) * PITCH + COVER - MARK - 6) for i in range(4)]
    expect([(x, y) for x, y, _ in mk] == sorted(want) and len({b for _, _, b in mk}) == 1, f'a mark at the bottom right of each cover in view, all the unselected image ({mk})')
    # a tap marks (and opens nothing); another unmarks; the count follows
    centre = lambda i: (MARGIN + (i % COLS) * CPITCH + 10, R0 + (i // COLS) * PITCH + 10)
    calls = tap(m, *centre(1))
    expect(('widget_set_text_utf8', t, '1 Selected') in calls and not [c for c in calls if c[0] in ('window_open', 'navigator_to_with_context')], 'a tap on a cell marks it (the title reads 1 Selected) and opens no playlist')
    tap(m, *centre(3)); calls = tap(m, *centre(0)); calls = tap(m, *centre(0))
    expect(('widget_set_text_utf8', t, '2 Selected') in calls, 'a second tap on a cell unmarks it')
    mk = {(x, y): b for x, y, b in marks_of(paint(m)[0])}
    on, off = mk[want[1]], mk[want[0]]
    expect(on != off and mk[want[3]] == on and mk[want[2]] == off and pixel(m, on, 13, 13) == 0xff2222ee and pixel(m, off, 13, 13) == 0xff111111
           and pixel(m, on, 0, 0) >> 24 == 0, 'the marked cells show the selected image, the others the unselected one (cut to its circle: no square over the cover)')
    # a drag past the threshold marks nothing
    calls = tap(m, *centre(2), dy=14)
    expect(not [c for c in calls if c[0] == 'widget_set_text_utf8' and c[1] == t], 'a drag marks nothing')
    # Select All: all, then none
    m.click('btn_selall')
    expect(('widget_set_text_utf8', t, f'{len(lists)} Selected') in m.calls, 'Select All marks every playlist')
    m.click('btn_selall')
    expect(('widget_set_text_utf8', t, '0 Selected') in m.calls, 'and a second tap marks none')
    # Back (the x) leaves select mode first; the title and navbar are restored
    tap(m, *centre(1)); m.calls = []
    m.click('btn_return')
    expect('navigator_back' not in m.names() and vis(m, 'btn_selall') == (0, 0) and vis(m, 'pl_bar') == (0, 0) and all(vis(m, n) == (1, 1) for n in names)
           and ('widget_set_tr_text', t, 'Playlists') in m.calls and ('widget_resize', t, O['NAV_CF_X'] - O['NAV_TITLE_X'], 22) in m.calls
           and m.props.get((back, 'style:normal:icon')) == 'ah_nav_back' and m.props.get((m.sv, 'virtual_h')) == R0 + 3 * PITCH,
           'Back leaves select mode (no navigation): the navbar, the title and the content are as before')
    expect(not marks_of(paint(m)[0]), 'no marks outside select mode')
    calls = tap(m, *centre(1))
    expect(('window_open', 'm1plus_songs') in calls, 'and a tap opens the playlist again')
    m.click('btn_return')
    expect('navigator_back' in m.names(), 'Back with no select mode goes back')

    # Delete: nothing marked is the message; No keeps the mode; Yes runs the stock calls in the stock order
    m = PM(lists, missing=(7,)); open_page(m); settle(m); m.setword(SEL_VEC, m.alloc(8))
    m.click('btn_plactions'); m.click('vs_item9'); m.calls = []
    m.click('pl_del')
    expect([c for c in m.calls if c[0] == 'toast'] == [('toast', 'msg_delplaylistfailed', 1, 2000)] and not [c for c in m.calls if c[0] in ('confirm', 'batch_delete_file')],
           'Delete with nothing marked: the stock message (msg_delplaylistfailed), no dialog, no delete')
    tap(m, *centre(1)); tap(m, *centre(3)); m.calls = []
    m.click('pl_del')
    expect([c for c in m.calls if c[0] == 'confirm'] == [('confirm', 'msg_delplaylist', 1)] and not [c for c in m.calls if c[0] in ('batch_delete_file', 'loadLocalClassList')]
           and vis(m, 'pl_bar') == (1, 1), 'No: the stock confirm dialog (kind 1, msg_delplaylist), nothing is deleted or read, select mode stays')
    m.confirm_yes = True; m.calls = []
    m.click('pl_del')
    order = [c for c in m.calls if c[0] in ('confirm', 'loadLocalClassList', 'select_recordinit', 'set_selectindex', 'batch_delete_file', 'toast')]
    expect([c[0] for c in order] == ['confirm', 'loadLocalClassList', 'select_recordinit', 'set_selectindex', 'set_selectindex', 'batch_delete_file', 'toast', 'loadLocalClassList'], f'Yes: confirm, the stock list read, the stock vector filled, batch_delete_file, the message, the page reads again ({[c[0] for c in order]})')
    bd = next(c for c in order if c[0] == 'batch_delete_file')
    expect(bd[:2] == ('batch_delete_file', O['CLASS_PLAYLISTS']) and bd[3] == m.word(SEL_VEC) and bd[4:] == (0, 0, [1, 3]) and order[1] == ('loadLocalClassList', O['CLASS_PLAYLISTS'])
           and order[2] == ('select_recordinit', len(lists)), f'batch_delete_file(0xf00b, the stock list, the stock vector, 0, 0) with rows 1 and 3 selected ({bd})')
    expect(order[-2] == ('toast', 'msg_delplaylistsuccess', 1, 2000) and vis(m, 'pl_bar') == (0, 0) and vis(m, 'btn_selall') == (0, 0) and all(vis(m, n) == (1, 1) for n in names),
           'then the success message, select mode is over and the page shows the playlists read again')
    # the stock list changed under the page (a playlist added elsewhere): nothing is deleted, the page reads again
    m = PM(lists, missing=(7,)); open_page(m); settle(m); m.setword(SEL_VEC, m.alloc(8)); m.confirm_yes = True
    m.click('btn_plactions'); m.click('vs_item9'); tap(m, *centre(1))
    PM.add(m, 9, 'Late', [1])
    m.calls = []
    m.click('pl_del')
    expect('batch_delete_file' not in m.names() and 'select_recordinit' not in m.names() and ('loadLocalClassList', O['CLASS_PLAYLISTS']) in m.calls and vis(m, 'pl_bar') == (0, 0),
           'a stock list that is not what the page shows (a playlist added meanwhile): nothing is deleted, the page reads again')
    m = PM(lists, missing=(7,)); open_page(m); settle(m); m.setword(SEL_VEC, m.alloc(8)); m.confirm_yes = True
    m.click('btn_plactions'); m.click('vs_item9'); tap(m, *centre(1))
    m.playlists[1], m.playlists[2] = m.playlists[2], m.playlists[1]   # the same playlists in another order
    m.calls = []
    m.click('pl_del')
    expect('batch_delete_file' not in m.names(), 'the same playlists in another order: nothing is deleted (the marks are of rows, not of ids)')
    m = PM(lists, missing=(7,)); open_page(m); settle(m); m.confirm_yes = True   # no selection vector (never made): no delete
    m.click('btn_plactions'); m.click('vs_item9'); tap(m, *centre(1)); m.calls = []
    m.click('pl_del')
    expect('batch_delete_file' not in m.names(), 'no stock selection vector: nothing is deleted')

    # list mode: a mark column left of each row, the cover and the texts 30 px to the right, taps mark
    m = PM(lists, missing=(7,)); m.fs[PL_FILE] = b'0\n'; open_page(m); settle(m)
    m.click('btn_plactions'); m.click('vs_item9')
    blits, texts, styles = settle(m)
    mk = marks_of(blits)
    expect([(x, y) for x, y, _ in mk] == [(O['LIST_ART_X'] + (SEL_COL - 6 - MARK) // 2, TOP + r * O['LIST_ROW_H'] + (O['LIST_ROW_H'] - MARK) // 2) for r in range(5)],
           f'list mode: a mark in a column left of every row ({mk})')
    covers = sorted(b[2][:4] for b in blits if b[2][2] == O['LIST_ART'])
    expect(all(c[0] == O['LIST_ART_X'] + SEL_COL for c in covers) and len(covers) == 6, 'the covers move right by the mark column')
    rows = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    expect(rows and all(r[0] == O['LIST_TEXT_X'] + SEL_COL and r[2] == O['LIST_TEXT_W'] - SEL_COL for _, r in rows), f'the texts too, 30 px narrower ({rows[:1]})')
    expect(not chevs_of(m, blits), 'no chevron in select mode (a tap marks, it opens nothing)')
    calls = tap(m, 150, TOP + 1 * O['LIST_ROW_H'] + 20)
    expect(('widget_set_text_utf8', m.widgets['label_title'], '1 Selected') in calls and not [c for c in calls if c[0] == 'window_open'], 'a tap on a row marks it')
    m.touch('down', 150, SCREEN_Y0 + TOP + 2 * O['LIST_ROW_H'] + 20, 5000, fn='pl_on_down'); paint(m)
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'a pressed row is not filled in select mode')
    m.touch('abort', 150, SCREEN_Y0 + TOP + 2 * O['LIST_ROW_H'] + 20, 5010, fn='pl_on_abort')
    m.click('btn_return')
    blits, texts, styles = settle(m)
    rows = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    expect(all(r[0] == O['LIST_TEXT_X'] and r[2] == O['LIST_TEXT_W_CHEV'] for _, r in rows) and not marks_of(blits), 'leaving select mode puts the texts back at their width (ending before the chevrons)')
    expect(len(chevs_of(m, blits)) == 6, 'and the chevrons are back on the rows')

    # fallbacks: the stock Playlists page where the page cannot do it, nothing when there is nothing to select
    for what, tweak in (('the select widgets are not in the asset', lambda m: m.widgets.pop('pl_bar')), ('the Delete pill is not in the asset', lambda m: m.widgets.pop('pl_del')),
                        ('Select All is not in the asset', lambda m: m.widgets.pop('btn_selall')), ('the marks do not decode', lambda m: m.images.pop('selected'))):
        m = PM(lists); tweak(m); open_page(m); settle(m); m.click('btn_plactions'); m.calls = []
        m.click('vs_item9')
        expect(('stock_resume', '14') in m.calls, f'{what}: Delete Playlists opens the stock Playlists page (Home id 14), as before')
    m = PM([]); open_page(m); m.click('btn_plactions'); m.calls = []
    m.click('vs_item9')
    expect(('widget_set_visible', m.widgets['pl_bar'], 1) not in m.calls and 'stock_resume' not in m.names() and vis(m, 'vs_card') == (0, 0), 'with no playlist there is nothing to select: the menu closes, nothing else')
    # the page read again (back from another window) leaves select mode
    m = PM(lists, missing=(7,)); open_page(m); settle(m)
    m.click('btn_plactions'); m.click('vs_item9'); tap(m, *centre(1))
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, a1=0, count=60000000)
    expect(vis(m, 'pl_bar') == (0, 0) and vis(m, 'btn_selall') == (0, 0) and all(vis(m, n) == (1, 1) for n in names), 'the page read again is out of select mode (the marks were of the old list)')
    # closing frees the marks
    m.call(PSYMS['pl_on_destroy'], count=400000)
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_destroy') >= 2, 'closing frees the marks')
    # the stock hit test on the asset: the bar's pill and Select All are reached where they show, nothing under the bar's top
    m = PM(lists, missing=(7,)); open_page(m); settle(m); m.click('btn_plactions'); m.click('vs_item9')
    root = asset_tree(UI)
    for n in ('btn_selall', 'pl_bar', 'pl_del'):
        if m.props.get((m.widgets[n], 'sensitive')) == 1: node(root, n).flags |= F_SENSITIVE
    for n in ('btn_plactions', 'btn_more', 'btn_backtoplayer'):
        if m.props.get((m.widgets[n], 'sensitive')) == 0: node(root, n).flags &= ~F_SENSITIVE
    node(root, 'view_grid').h = 3000
    expect(stock_target(m, root, 160, 450 - 32)[-1] == 'pl_del' and stock_target(m, root, 280, 25)[-1] == 'btn_selall' and stock_target(m, root, 240, 25)[-1] != 'btn_more' and stock_target(m, root, 190, 25)[-1] != 'btn_plactions' and stock_target(m, root, 290, 25)[-1] != 'btn_backtoplayer',
           'in select mode the pill and Select All are hit where they show, and the hidden navbar buttons take no touch')


def src_tests(ctx):
    """The page over a library source (playlists_open_src, patch/libsrc.h): the same grid fed from src->list(LS_PLAYLISTS), a mosaic of the tracks' covers via src->cover, a tap
    through so_play_src (or the playlist page hook), no stock-only action, the source's gen read again. src NULL / &lib_stock is the stock page."""
    expect = ctx.expect
    lists = [(1, 'Road', [0, 1]), (2, 'Night', [2, 2, 3, 4]), (3, 'Empty', []), (4, 'One', [5])]

    def src_page(**kw):
        m = PM(lists, **kw); src = m.fake_src()
        m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
        return m, src

    # stock unchanged: NULL is the stock page (its query, the list-plus button)
    m = PM(lists)
    m.call(PSYMS['playlists_open_src'], a0=0, count=60000000)
    expect(('loadLocalClassList', O['CLASS_PLAYLISTS']) in m.calls and vis(m, 'btn_plactions') != (0, 0), 'playlists_open_src(NULL) is the stock page: the stock query, the list-plus button')
    m = PM(lists)
    m.call(PSYMS['playlists_open_src'], a0=PSYMS['lib_stock'], count=60000000)
    expect(('loadLocalClassList', O['CLASS_PLAYLISTS']) in m.calls and vis(m, 'btn_plactions') != (0, 0), 'and so is &lib_stock')
    m = PM(lists, missing=(0, 1))
    m.call(PSYMS['playlists_open_src'], a0=0, count=60000000)
    log = []; settle(m, log=log)
    expect(not any(v[1:] == (14, 14) for v in m.bitmaps.values()) and not any(c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick'] for c in log), 'the stock page (covers missing): no cover spinner')

    # the grid from the source
    m, src = src_page(missing=(4,))
    blits, texts, styles = settle(m)
    expect(not [c for c in m.calls if c[0] == 'loadLocalClassList'] and ('list', 3, 0) in m.fake_calls, 'the playlists come from src->list(LS_PLAYLISTS, NULL), not the stock query')
    names = [tx for tx, st in sorted(((tx, r[1] * 10 + r[0]) for (tx, r), st in zip(texts, styles) if st == 'label_grid_title'), key=lambda t: t[1])]
    subs = [tx for tx, st in sorted(((tx, r[1] * 10 + r[0]) for (tx, r), st in zip(texts, styles) if st == 'label_grid_sub'), key=lambda t: t[1])]
    expect(names == ['Empty', 'Night', 'One', 'Road'] and subs == ['0 tracks', '4 tracks', '1 track', '2 tracks'], f'tiles: names (A-Z) and track counts from the source ({names}, {subs})')
    order = sorted(lists, key=lambda l: l[1])
    for i, (_, _, alb_) in enumerate(order):
        distinct = list(dict.fromkeys(a for a in alb_ if a != 4))
        want = want_mosaic(distinct)
        got = cell_blit(blits, i)
        if want: expect(got is not None and all(near(x, y) for x, y in zip(quadrants(m, got), want)), f'playlist {order[i][1]}: the mosaic is made of the tracks\' covers via src->cover')
    expect(any(c[0] == 'cover' for c in m.fake_calls), 'the cover files were asked of src->cover')

    # stock-only actions are hidden
    expect(vis(m, 'btn_plactions') == (0, 0) and vis(m, 'btn_more')[0] == 1, 'the list-plus button is hidden (New Playlist, Import, Export, Delete Playlists, Clean Up); the "..." stays')
    mi = tuple(m.props.get((m.widgets['btn_more'], f'style:{st}:icon')) for st in ('normal', 'over', 'pressed'))
    expect(mi == ('pod_nav_more', 'pod_nav_more', 'pod_nav_more_down'), f'without the list-plus cap the "..." takes the left cap\'s rounded edge ({mi})')
    sm = PM(lists); sm.call(PSYMS['playlists_open_src'], a0=0, count=60000000)
    expect(not any(sm.props.get((sm.widgets['btn_more'], f'style:{st}:icon')) for st in ('normal', 'over', 'pressed')), 'the stock page keeps the asset\'s middle piece (no icon set at run time)')
    m.click('btn_more')
    expect(vis(m, 'vs_card')[0] == 1, 'the "..." card opens (Grid, List, Name)')
    m.calls = []
    for a in (A_NEW, A_IMPORT, A_EXPORT, A_DELETE):
        m.click(a)
        m.click('btn_more') if vis(m, 'vs_card')[0] == 0 else None
    names_ = [c[0] for c in m.calls]
    expect(not {'stock_playlist_import', 'stock_playlist_export', 'confirm', 'keyboard_open'} & set(names_) and ('widget_set_visible', m.widgets['pl_bar'], 1) not in m.calls and ('widget_set_visible', m.widgets['btn_selall'], 1) not in m.calls,
           f'the stock-only rows do nothing even if reached ({sorted(set(names_))})')

    # a tap plays the playlist through the source (no page hook)
    m, src = src_page(missing=(4,)); settle(m); m.fake_calls.clear()
    tap(m, MARGIN + 10, R0 + 10)   # the first cell: Empty (A-Z) has no tracks: nothing plays
    expect(not [c for c in m.fake_calls if c[0] == 'play'], 'a playlist without tracks plays nothing')
    tap(m, MARGIN + CPITCH + 10, R0 + 10)
    plays = [c for c in m.fake_calls if c[0] == 'play']
    expect(plays == [('play', ['T0', 'T1', 'T2', 'T3'], 0, 1, plays[0][4] if plays else 0)] and not [c for c in m.calls if c[0] in ('window_open', 'navigator_to_with_context') and c[1] != 'm1plus_playlists'],
           f'a tap on Night plays its tracks in order through src->play (LS_PLAY_ORDER), no stock page ({plays})')
    # the playlist's Songs page: songs_open_src_in(src, LS_PLAYLISTS, the row, its name); the page opens, nothing plays
    m, src = src_page(missing=(4,)); settle(m); m.fake_calls.clear(); m.fake_song_ret = 0
    tap(m, MARGIN + CPITCH + 10, R0 + 10)
    expect(('songs', True, 3, 'Night', 'Night') in m.fake_calls and not [c for c in m.fake_calls if c[0] == 'play'],
           f'a tap on Night calls songs_open_src_in with the source, LS_PLAYLISTS, the row and its name, and plays nothing ({m.fake_calls})')
    # the page does not open: the playlist plays in order
    m, src = src_page(missing=(4,)); settle(m); m.fake_calls.clear(); m.fake_song_ret = -1
    tap(m, MARGIN + CPITCH + 10, R0 + 10)
    expect([c[:4] for c in m.fake_calls if c[0] == 'play'] == [('play', ['T0', 'T1', 'T2', 'T3'], 0, 1)], f'no page: Night plays its tracks in order ({m.fake_calls})')

    # a cover asked for and not there: read again by the page's poll; a gen change reads the playlists again
    m = PM(lists, missing=(0, 1)); src = m.fake_src(); m.fake_ask = {fnv(fnv(O['FNV_SEED'], alb(i)[0]), alb(i)[1]) or 1 for i in (0, 1)}
    for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)   # (the Wi-Fi page's frames as cc_decode flattens them over black)
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    log = []
    blits, _, _ = settle(m, log=log)
    road = [i for i, l in enumerate(order) if l[1] == 'Road'][0]
    # the cover spinner: Road's mosaic has no cover yet (asked, PL_SCAN_MISS), so the 14 px wf_spin frame sits centred on its disc; Night, Empty and One (no cover to wait for) have none
    def spinners(bl): return [b for b in bl if m.bitmaps[b[0]][1:] == (14, 14)]
    sp = spinners(blits)
    cx = MARGIN + (road % 2) * CPITCH + O['GRID_COVER'] // 2
    expect(len(sp) == 1 and sp[0][2][2:] == (14, 14) and abs(sp[0][2][0] + 7 - cx) <= 1, f'one spinner, on the tile whose cover is on its way, centred: {[b[2] for b in sp]} (cell centre x {cx})')
    expect(('timer_add', PSYMS['ls_cover_tick'], 250) in log, 'the spinner turns on the shared 250 ms cover poll')
    f0 = sp[0][0]
    expect(m.call(PSYMS['ls_cover_tick'], a0=0x5a5a5a50, count=60000000) == 8 and spinners(paint(m)[0])[0][0] != f0, 'a tick with a tile loading repeats (its argument is stock\'s timer_info_t: not read) and turns the frame')
    for i in (0, 1):
        pth = key_path(*alb(i)); m.present.add(pth); m.files[pth] = 4096
        m.images['file://' + pth] = (24, 24, struct.pack('<I', colour(i)) * (24 * 24))
    m.call(PSYMS['ls_cover_tick'], count=60000000)
    blits, _, _ = settle(m)
    got = cell_blit(blits, road)
    expect(got is not None and all(near(x, y) for x, y in zip(quadrants(m, got), want_mosaic([0, 1]))), 'the poll reads Road again once its covers are there: the mosaic appears')
    expect(not spinners(blits) and [m.call(PSYMS['ls_cover_tick'], count=60000000) for _ in range(3)][-1] != 8, 'the covers arrived: no spinner, and the shared poll ends')
    # the cover never lands: the shared poll gives up after LS_COVER_POLLS asks (the spinner goes, the placeholder stays); a page not on top asks nothing
    m = PM(lists, missing=(0, 1)); src = m.fake_src(); m.fake_ask = {fnv(fnv(O['FNV_SEED'], alb(i)[0]), alb(i)[1]) or 1 for i in (0, 1)}
    for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    settle(m)
    m.top_main = 0; m.fake_calls.clear()
    expect(m.call(PSYMS['ls_cover_tick'], count=60000000) == 8 and not m.fake_calls, 'not the top window: the poll waits and reads nothing')
    m.top_main = m.window
    for _ in range(1205):
        m.call(PSYMS['ls_cover_tick'], count=60000000)
        settle(m)
    expect(not spinners(paint(m)[0]) and m.call(PSYMS['ls_cover_tick'], count=60000000) != 8, 'the covers never land: after LS_COVER_POLLS asks the spinner is gone and the poll has ended')
    m.fake_gen = 6; m.playlists.pop(0); m.fake_calls.clear()
    m.call(PSYMS['pl_on_gen'], count=60000000)
    blits, texts, styles = settle(m)
    names = [tx for (tx, r), st in zip(texts, styles) if st == 'label_grid_title']
    expect(('list', 3, 0) in m.fake_calls and sorted(names) == ['Empty', 'Night', 'One'], f'a gen change reads the playlists again ({names})')
    m.fake_calls.clear(); m.call(PSYMS['pl_on_gen'], count=60000000)
    expect(('list', 3, 0) not in m.fake_calls, 'an unchanged gen reads nothing')
    # a gen move that changes nothing in the list (any fetch anywhere moves it) updates in place: no tile is made again, nothing is decoded or dropped
    m, src = src_page(missing=(4,))
    blits0, _, _ = settle(m)
    before = [cell_blit(blits0, i) for i in range(4)]
    m.fake_gen += 1; m.fake_calls.clear()
    m.call(PSYMS['pl_on_gen'], count=60000000)
    log = list(m.calls)
    blits1, _, _ = settle(m, log=log)
    churn = [c for c in log if c[0] in ('widget_load_image', 'bitmap_create_ex', 'bitmap_destroy')]
    expect(not churn and [cell_blit(blits1, i) for i in range(4)] == before and all(before), f'a gen move with the same playlists keeps every tile and decodes nothing ({churn})')
    # one new playlist: it is added without reloading the others (each keeps its tile, at its new place), only its own cover is decoded
    PM.add(m, 5, 'Alpha', [6])
    m.fake_gen += 1
    m.call(PSYMS['pl_on_gen'], count=60000000)
    log = list(m.calls)
    blits2, texts2, styles2 = settle(m, log=log)
    names2 = [tx for tx, st in sorted(((tx, r[1] * 10 + r[0]) for (tx, r), st in zip(texts2, styles2) if st == 'label_grid_title'), key=lambda t: t[1])]
    after = [cell_blit(blits2, i) for i in range(5)]
    loads = [c[1] for c in log if c[0] == 'widget_load_image']
    destroyed = [c for c in log if c[0] == 'bitmap_destroy']
    expect(names2[:4] == ['Alpha', 'Empty', 'Night', 'One'] and after[1:4] == before[:3], f'the new playlist is in; Empty, Night and One keep their tiles at their new places (Road is below the view) ({names2}, {after}, {before})')
    expect(loads == ['file:///mnt/mmc/.m1plus/subsonic/covers/%08x-168.jpg' % (fnv(fnv(O['FNV_SEED'], alb(6)[0]), alb(6)[1]) or 1)] and not destroyed and after[0] and all(near(x, y) for x, y in zip(quadrants(m, after[0]), want_mosaic([6]))),
           f'only the new playlist\'s cover is decoded, nothing is dropped ({loads}, {destroyed})')
    # a playlist whose content changed on the server (same id and name, a song more): its row is read again and shows the new count, the cover stays (same albums) with no decode;
    # the other tiles are untouched
    m, src = src_page(missing=(4,))
    blits0, _, _ = settle(m)
    before = [cell_blit(blits0, i) for i in range(4)]
    night = next(i for i, r_ in enumerate(m.playlists) if m.read_cstr(m.word(r_ + O['REC_TITLE'])) == 'Night')
    pid = m.word(m.playlists[night] + REC_DISC)
    m.playlist_songs[pid].append(m.record(album=alb(2)[1], artist=alb(2)[0], path='/mnt/mmc/m/2/1.flac', title='T9', rid=1009))
    m.playlists[night] = PM.rec(m, pid, 'Night', len(m.playlist_songs[pid]))
    m.fake_gen += 1; m.fake_calls.clear()
    m.call(PSYMS['pl_on_gen'], count=60000000)
    log = list(m.calls)
    blits1, texts1, styles1 = settle(m, log=log)
    subs = [tx for tx, st in sorted(((tx, r[1] * 10 + r[0]) for (tx, r), st in zip(texts1, styles1) if st == 'label_grid_sub'), key=lambda t: t[1])]
    churn = [c for c in log if c[0] in ('widget_load_image', 'bitmap_create_ex', 'bitmap_destroy')]
    expect(subs == ['0 tracks', '5 tracks', '1 track', '2 tracks'] and ('list', 3, m.playlists[night]) in m.fake_calls, f'same id and name, a song more: the tile reads 5 tracks and its songs are read again ({subs})')
    expect(not churn and [cell_blit(blits1, i) for i in range(4)] == before, f'the same albums: every tile keeps its picture, nothing is decoded or dropped ({churn})')
    m.fake_calls.clear(); m.fake_gen += 1
    m.call(PSYMS['pl_on_gen'], count=60000000)
    log = list(m.calls)
    settle(m, log=log)
    expect(not [c for c in m.fake_calls if c[0] == 'list' and c[2]] and not [c for c in log if c[0] in ('widget_load_image', 'bitmap_create_ex', 'bitmap_destroy')],
           'and a gen move with nothing changed after that reads no playlist and decodes nothing')
    # no playlists: the empty page
    m = PM([]); src = m.fake_src(); m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    expect(vis(m, 'label_status')[0] == 1 and vis(m, 'pl_spin')[0] == 0 and ('widget_set_tr_text', m.widgets['label_status'], 'No playlists') in m.calls, 'a source without playlists shows the empty page')
    expect(('state', 3, 0) in m.fake_calls and vis(m, 'view_grid')[0] == 1, 'it asked src->state(LS_PLAYLISTS, NULL); the large title stays')
    # the list is on its way: the one spinner and no status line; the playlists arrive: the grid, no spinner
    m = PM([]); src = m.fake_src(); m.fake_state_all = 1
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    expect(vis(m, 'pl_spin')[0] == 1 and vis(m, 'label_status')[0] == 0 and vis(m, 'view_grid')[0] == 1 and ('timer_add', PSYMS['ls_spin_tick'], 250) in m.calls, 'loading: one spinner, no status line, the title block shows')
    m.playlists = [PM.rec(m, 1, 'Road', 2)]; m.playlist_songs[1] = []; m.fake_state_all = 0; m.fake_gen += 1
    m.call(PSYMS['pl_on_gen'], count=60000000)
    expect(vis(m, 'pl_spin')[0] == 0 and vis(m, 'label_status')[0] == 0 and vis(m, 'view_grid')[0] == 1, 'the playlists arrive: the spinner goes')
    for st, text in ((2, "Can't connect to the server"), (3, 'Connect to Wi-Fi first')):
        m = PM([]); src = m.fake_src(); m.fake_state_all = st
        m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
        expect(vis(m, 'label_status')[0] == 1 and vis(m, 'pl_spin')[0] == 0 and ('widget_set_tr_text', m.widgets['label_status'], text) in m.calls, f'state {st}: {text!r}, no spinner')
    m = PM(lists); src = m.fake_src(); m.fake_state_all = 1
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    expect(('state', 3, 0) not in m.fake_calls and vis(m, 'pl_spin')[0] == 0, 'cached playlists: the state is not asked, no spinner')
    # a playlist whose tracks are not cached: the tile shows the sync's songCount from the source's record until the list arrives
    m = PM(lists, missing=(4,)); src = m.fake_src()
    night_id = next(m.word(r_ + REC_DISC) for r_ in m.playlists if m.read_cstr(m.word(r_ + O['REC_TITLE'])) == 'Night')
    m.playlist_counts = {night_id: 9}; m.fake_no_list = {night_id}
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    _, texts, styles = settle(m)
    subs = [tx[0] for tx, st in zip(texts, styles) if st == 'label_grid_sub']
    counts = [c for c in m.fake_calls if c[0] == 'count' and m.word(c[2] + REC_DISC) == night_id]
    expect('9 tracks' in subs and counts, f'a playlist not read yet: its sync songCount, not 0 ({subs}, {m.fake_calls})')
    m.fake_no_list.discard(night_id); m.fake_gen += 1
    m.call(PSYMS['pl_on_gen'], count=60000000)
    _, texts, styles = settle(m)
    subs = [tx[0] for tx, st in zip(texts, styles) if st == 'label_grid_sub']
    expect('4 tracks' in subs, f'the tracks arrive: the list\'s own count ({subs})')


def stock_tests(ctx):
    expect, page = ctx.expect, ctx.page
    row = next(i for i, r in enumerate(page.rows) if r.label == 'Playlists')
    expect(page.rows[row].action == pod_pages.ACT_PLAYLISTS, 'the menu\'s Playlists row opens our page (ACT_PLAYLISTS)')
    expect(pod_pages.PLAYLISTS in pod_pages.PAGES and pod_pages.PLAYLISTS.key == 'm1plus_playlists', 'the page is in the page table')
    on_row, rows0 = PSYMS['on_row'], PSYMS['pod_rows_0']

    # 1. The asset: the Albums page's structure with a "..." button in place of the toggles, and the hidden popup
    tree = awtk_ui.parse(open(UI, 'rb').read())
    lv, sv, grid, bar = tree.find('playlists_listview'), tree.find('playlists_scrollview'), tree.find('view_grid'), tree.find('scroll_bar_m')
    expect(lv.type == 'list_view' and sv.type == 'scroll_view' and sv.children == [grid] and lv.children[:1] == [sv] and bar in lv.children
           and (lv.x, lv.y, lv.w, lv.h) == (0, 50, 320, VIEW_H) and (sv.w, bar.x, bar.w) == (SVW, SVW, 10),
           'the body is list_view > scroll_view > view_grid with the stock mobile scroll bar, as the Albums page')
    more = tree.find('btn_more')
    import mod_icons
    plactions = tree.find('btn_plactions')
    expect(more is not None and (more.x, more.w, more.h) == (O['NAV_VIEW_X'], O['NAV_VIEW_W'], O['NAV_H']) and more.get('style') == 'img_btn_style'
           and more.get('style:normal:icon') == 'pod_nav_moremid' and more.get('style:pressed:icon') == 'pod_nav_moremid_down' and more.get('visible') != 'false'
           and plactions is not None and (plactions.x, plactions.w, plactions.h) == (O['NAV_CF_X'], O['NAV_CF_W'], O['NAV_H']) and plactions.get('style') == 'img_btn_style' and plactions.get('visible') != 'false'
           and plactions.get('style:normal:icon') == 'pod_nav_listplus' and plactions.get('style:pressed:icon') == 'pod_nav_listplus_down' and plactions.get('style:over:icon') == 'pod_nav_listplus'
           and tree.find('label_title').x + tree.find('label_title').w == plactions.x == 168 and plactions.x + plactions.w == more.x and more.x + more.w == tree.find('btn_backtoplayer').x,
           'the navbar is list-plus | "..." | Now Playing as Songs\' Search | "..." | Now Playing: the list-plus button the capsule\'s left cap (x 168), the "..." its middle piece (x 214, pod_nav_moremid), the title ends at 168')
    expect(mod_icons.NAV_VIEW['pod_nav_listplus'] == 'list-plus' and mod_icons.NAV_VIEW_POS['pod_nav_listplus'] == 'left' and tree.find('btn_plactions').get('name') == 'btn_plactions', 'the list-plus button is the Lucide list-plus (SF Symbols text.badge.plus) as a left glass piece')
    expect(tree.find('btn_albumview') is None and tree.find('btn_coverflow') is None and tree.find('pl_scrim') is None and tree.find('pl_card') is None and tree.find('pl_item0') is None
           and tree.find('btn_backtoplayer').get('style:normal:icon') == 'ah_nav_play',
           'the grid / list toggle and the old popup (pl_scrim, pl_card, pl_item0..3) are gone; Now Playing is the capsule\'s right cap')
    for nm, px, col in (('label_row_title', 21, '#FFFFFF'), ('label_row_sub', 18, '#AAAAAA')):
        w = tree.find(nm)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == 'false' and w.get('style:normal:font_size') == str(px)
               and w.get('style:normal:text_color') == col, f'{nm}: a hidden label carrying the list rows\' {px} px {col} text style')
    expect(all(os.path.isfile(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/images/xx/{n}.png')) for n in ('pod_nav_moremid', 'pod_nav_moremid_down', 'pod_nav_listplus', 'pod_nav_listplus_down')), 'the glyph images of the list-plus button and the "..." middle piece are in the tree')
    for nm, px, col in (('label_grid_title', 18, '#FFFFFF'), ('label_grid_sub', 15, '#AAAAAA')):
        w = tree.find(nm)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == 'false' and w.get('style:normal:font_size') == str(px)
               and w.get('style:normal:text_color') == col, f'{nm}: a hidden label carrying the {px} px {col} text style (the Albums grid\'s)')
    scrim, card = tree.find('vs_scrim'), tree.find('vs_card')
    expect(scrim.type == 'button' and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450) and card.type == 'view'
           and all(w.get('visible') == 'false' and w.get('sensitive') == 'false' for w in (scrim, card)),
           'the shared card\'s scrim (the whole window) and card start hidden AND insensitive (hit tests ignore visible)')
    kids = tree.children
    expect(kids.index(scrim) > kids.index(lv) and kids.index(scrim) > kids.index(tree.find('navigationbar_view')) and kids.index(card) == kids.index(scrim) + 1,
           'the scrim and the card come after the navbar and the list: they lie over everything')
    items = [tree.find(f'vs_item{i}') for i in range(10)]
    expect(all(it is not None and it.type == 'button' and it in card.children and it.w == card.w for it in items)
           and card.h == 7 * O['VS_ROW_H'] and card.y + card.h <= 450 and card.x + card.w <= 320 and card.y == O['PL_CARD_Y'] and card.x + card.w == O['PL_CARD_RIGHT'],
           'ten row buttons (the Playlists asset has the two extra action slots 8 and 9) in the 7-row 336 px card, its right edge at 311, under the navbar and above the window\'s foot (52 + 336 = 388 of 450)')
    expect(tree.find('vs_hair') is not None and tree.find('vs_glyph8') is not None and tree.find('vs_glyph9') is not None and all(tree.find(f'vs_tick{i}') is not None for i in range(6))
           and tree.find('vs_tick6') is None and tree.find('vs_tick8') is None, 'the hairline, the glyphs of the action rows and the six ticks (no tick on an action row)')
    labels = {i: next(c for c in items[i].children if c.type == 'hscroll_label') for i in range(10)}
    expect([pod_i18n.shown_english(labels[i]) for i in range(6, 10)] == list(pod_pages.PLAYLIST_MENU) == ['New Playlist', 'Import', 'Export', 'Delete Playlists']
           and [pod_i18n.shown_english(labels[i]) for i in (0, 4, 5)] == ['Name', 'Grid', 'List'],
           'the rows: New Playlist, Import, Export, Delete Playlists (slots 6..9, the list-plus button\'s card), Grid and List (4, 5), Name (0: the "..." card; the other sort slots are in the asset and never offered)')
    expect(all(c.get('sensitive') == 'false' for it in items for c in it.children if c.type != 'image' or not c.name.startswith('vs_tick')), 'the glyphs and labels in the rows are insensitive (the row button takes the tap)')
    glyphs = {i: next((c for c in items[i].children if c.type == 'image' and c.name == f'vs_glyph{i}'), None) for i in range(6, 10)}
    xx = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx')
    expect([glyphs[i] and glyphs[i].get('image') for i in range(6, 10)] == [n for n, _ in mod_icons.PL_MENU_ICONS] == ['pl_ic_new', 'pl_ic_import', 'pl_ic_export', 'pl_ic_delete']
           and [g for _, g in mod_icons.PL_MENU_ICONS] == ['list-plus', 'file-input', 'file-output', 'trash'] and mod_icons.PL_MENU_PX == O['VS_GLYPH'] == 20
           and all((glyphs[i].x, glyphs[i].y, glyphs[i].w, glyphs[i].h) == (O['VS_GLYPH_X'], (O['VS_ROW_H'] - 20) // 2, 20, 20) for i in range(6, 10))
           and all(labels[i].x == O['VS_LABEL_X_GLYPH'] for i in range(4, 10)) and labels[0].x == O['VS_LABEL_X'],
           'the four action rows keep the old card\'s glyphs (New list-plus, Import file-input, Export file-output, Delete trash) at 20 px in the glyph column, like Search and Select; the labels follow it')
    expect(all(open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() for n, _ in mod_icons.PL_MENU_ICONS),
           'the four glyph images are in the tree, the committed PNGs')
    glass_users(expect)
    # the labels fit their room in all 13 languages (18 px in the shipped font; the room after the glyph column is PL_CARD_MAX - VS_LABEL_X_GLYPH - VS_LABEL_R)
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    room = O['PL_CARD_MAX'] - O['VS_LABEL_X_GLYPH'] - O['VS_LABEL_R']
    over = [(loc, k, w) for loc in pod_i18n.LOCALES for k in pod_pages.PLAYLIST_MENU for w in [StbText(font, pod_ui.PL_LABEL_PX).layout(built[loc][k])[1]] if w > room]
    expect(not over, f'every action label fits its {room} px room in all 13 languages ({over[:4]})')
    over = [(loc, w) for loc in pod_i18n.LOCALES for w in [StbText(font, 20).layout(built[loc]['No playlists'])[1]] if w > tree.find('label_status').w]
    expect(not over, f'"No playlists" fits the status line in all languages ({over})')
    over = [(loc, w) for loc in pod_i18n.LOCALES for w in [StbText(font, 20).layout(built[loc]['Playlists'])[1]] if tree.find('label_title').x + w > plactions.x]
    expect(not over, f'the title "Playlists" ends before the list-plus button in all languages, or the label ellipsizes there ({over})')

    # 2. The menu row opens the page; a window that will not open leaves the stock Playlists page (Home id 14)
    m = PM([(1, 'Mix', [0, 1])])
    m.call(on_row, a0=rows0 + 12 * row, count=60000000)
    expect(('window_open', 'm1plus_playlists') in m.calls and 'stock_resume' not in m.names(), 'the Playlists row opens our page')
    m = PM([(1, 'Mix', [0])]); m.window = 0
    open_page(m)
    expect(('stock_resume', '14') in m.calls, 'if the window will not open the row opens the stock Playlists page')
    m = PM([(1, 'Mix', [0])])
    m.widgets.pop('vs_card')
    open_page(m)
    expect(('navigator_back',) in m.calls and not any(c[0] == 'loadLocalClassList' for c in m.calls), 'an asset that is not ours: the page leaves again')

    # 3. Opening reads the stock playlists (class 0xf00b) and the page binds its buttons; nothing is shown or decoded before the first tick
    lists = [(1, '1 Empty', []), (2, '2 One', [0]), (3, '3 Two', [1, 2, 1, 2]), (4, '4 Three', [3, 4, 5]), (5, '5 Many', [0, 1, 2, 3, 4, 5, 6]), (6, '6 Bare', [7])]   # (the names run in the stock order: the page shows them A-Z; section 14 has the other orders)
    m = PM(lists, missing=(7,))
    calls = open_page(m)
    expect(('window_open', 'm1plus_playlists') in calls and [c for c in calls if c[0] == 'loadLocalClassList'] == [('loadLocalClassList', O['CLASS_PLAYLISTS'])],
           'opening runs the playlist query once and not the song queries (those are the loader\'s, one a tick)')
    expect(all((m.widgets[n], O['EVT_CLICK']) in m.bound for n in ('btn_return', 'btn_backtoplayer', 'btn_more', 'vs_scrim', 'vs_item0', 'vs_item4', 'vs_item5', 'vs_item6', 'vs_item7', 'vs_item8', 'vs_item9'))
           and (m.widgets['view_grid'], O['EVT_AFTER_PAINT']) in m.bound and (m.window, O['EVT_WINDOW_TO_FG']) in m.bound,
           'the buttons, the paint and the window\'s to-foreground event are bound')
    expect(vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status')[0] == 0 and vis(m, 'vs_scrim') == (0, 0) and vis(m, 'vs_card') == (0, 0),
           'the grid shows; the status line, the scrim and the card are hidden and insensitive')
    h = m.word(m.widgets['view_grid'] + 0xc)
    expect(h == R0 + 3 * PITCH and m.props.get((m.sv, 'virtual_h')) == h, f'6 playlists are 3 rows: the content is {h} px and the scroll_view is told')
    expect(not [c for c in m.calls if c[0] == 'widget_load_image' and c[1] not in ('p_default', 'unselect', 'selected')], 'no cover is decoded in the open (only the placeholder disc)')

    # 4. The loader: one playlist read or one cover source decoded a tick; the mosaics (cells 4 and 5 are in the third row: scrolled to)
    blits, texts, styles = settle(m)
    expect(m.most_per_tick <= 1, f'at most one cover source decoded per tick (saw {m.most_per_tick})')
    top = m.word(m.widgets['view_grid'] + 0xc) - VIEW_H
    scroll_to(m, top)
    blits2, texts2, styles2 = settle(m)
    expect(len(m.bitmaps) <= TILES + 1 and m.most_per_tick <= 1, f'the bitmaps alive stay within the tile ring and the placeholder ({len(m.bitmaps)})')
    cover = {i: cell_blit(blits, i) for i in range(4)}
    cover.update({i: cell_blit(blits2, i, top) for i in (4, 5)})
    holder = None
    for i, (pid, name, songs) in enumerate(lists):
        distinct = []
        for a in songs:
            if a not in distinct and a != 7: distinct.append(a)
        distinct = distinct[:4]
        b = cover[i]
        expect(b is not None, f'{name}: its cover is painted')
        if b is None: continue
        q = quadrants(m, b)
        w = want_mosaic(distinct)
        if w is None:
            holder = holder or b
            expect(near(q[0], GREY_DISC) and len(set(q)) == 1 and b == holder,
                   f'{name}: {len(songs)} songs, no album with a cover: the one placeholder disc ({[hex(x) for x in q]})')
        else:
            expect(all(near(a, b2) for a, b2 in zip(q, w)), f'{name}: {len(distinct)} album(s) fill the quadrants {[f"{x:#010x}" for x in w]} (got {[f"{x:#010x}" for x in q]})')
    texts_by = {}
    for f, off in (((texts, styles), 0), ((texts2, styles2), top)):
        for (text, rect), st in zip(*f): texts_by.setdefault(st, {})[(rect[1] + off - R0) // PITCH * COLS + (rect[0] - MARGIN) // CPITCH] = text
    names = {'label_grid_title': {i: l[1] for i, l in enumerate(lists)},
             'label_grid_sub': {i: ('1 track' if len(l[2]) == 1 else f'{len(l[2])} tracks') for i, l in enumerate(lists)}}
    expect(texts_by.get('label_grid_title') == names['label_grid_title'] and texts_by.get('label_grid_sub') == names['label_grid_sub'],
           f'each cell shows the playlist\'s name and its track count ({texts_by})')
    expect(len(set(quadrants(m, cover[4]))) == 4, 'a playlist of seven albums shows its first four, all different')

    # 5. The scan reads at most PL_SCAN songs and takes the first four albums that have a cover (missing covers are skipped)
    songs = [7] * 10 + [0, 7, 1, 2, 3, 4]
    m = PM([(1, 'Skip', songs)], missing=(7,)); open_page(m)
    blits, _, _ = settle(m)
    q = quadrants(m, cell_blit(blits, 0))
    expect(all(near(a, b2) for a, b2 in zip(q, want_mosaic([0, 1, 2, 3]))), 'albums with no cover file are skipped: the first four with one fill the mosaic')
    m = PM([(1, 'Far', [7] * O['PL_SCAN'] + [0, 1])], missing=(7,)); open_page(m)
    blits, _, _ = settle(m)
    expect(near(pixel(m, cell_blit(blits, 0), 36, 36), GREY_DISC), f'only the first {O["PL_SCAN"]} songs are looked at: covers after them do not count')

    # 6. A track of a compilation carries another artist than the album's cache key: the library album of that name is found
    m = PM([(1, 'Comp', [0, 1])], other_artist=(0, 1)); open_page(m)
    blits, _, _ = settle(m)
    expect(all(near(a, b2) for a, b2 in zip(quadrants(m, cell_blit(blits, 0)), want_mosaic([0, 1]))), 'songs by another artist find their album\'s cover through the library list')
    # ... and only once per album: a song whose key was looked at already (its cover is in, or it had none) does not walk the library list again
    m = PM([(1, 'Repeat', [30] * 20 + [39] * 10)], albums=40, missing=(39,)); open_page(m)
    blits, _, _ = settle(m)
    reads = sum(n for h, n in m.deque_reads.items() if len(m.deques.get(h, [])) == 40)
    expect(reads <= 40, f'repeated albums look the library up once: one pass for the coverless album, none for the repeats ({reads} reads)')
    expect(all(near(a, b2) for a, b2 in zip(quadrants(m, cell_blit(blits, 0)), want_mosaic([30]))), 'the repeated album still fills the tile')

    # 7. Tap: the playlist opens in our Songs page (patch/songs.c songs_open_playlist; test/pod/songs.py lists_tests has the page); a Songs window that will not
    #    open leaves the stock songs page (allmusic_page, class 0xff13) with its id in classinfo[1] and its name as the title
    m = PM(lists, missing=(7,)); open_page(m); settle(m)
    calls = tap(m, MARGIN + 40, R0 + 40)
    expect(('window_open', 'm1plus_songs') in calls and not [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'allmusic_page'],
           'a tap opens the playlist in our Songs page, not the stock one')
    m = PM(lists, missing=(7,)); m.windows['m1plus_songs'] = 0; open_page(m); settle(m)
    for i in (0, 3, 5):
        x, y = MARGIN + (i % COLS) * CPITCH + 40, R0 + (i // COLS) * PITCH + 40
        calls = tap(m, x, y)
        opened = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'allmusic_page']
        expect(opened == [('navigator_to_with_context', 'allmusic_page', O['CLASS_PLAYLIST_SONGS'], lists[i][0], lists[i][1])],
               f'a tap on cell {i} opens playlist {lists[i][0]} ({lists[i][1]!r}) in the Songs page ({opened})')
    calls = tap(m, MARGIN + 40, R0 + 40, dx=O['SC_DRAG_PX'] + 2)
    expect(not [c for c in calls if c[0] == 'navigator_to_with_context'], 'a release past the drag threshold opens nothing')
    calls = tap(m, MARGIN + COVER + 3, R0 + 40)
    expect(not [c for c in calls if c[0] == 'navigator_to_with_context'], 'the gap between the columns is dead')
    m.touch('down', MARGIN + 40, SCREEN_Y0 + R0 + 40, 1000, fn='pl_on_down'); m.touch('abort', MARGIN + 40, SCREEN_Y0 + R0 + 40, 1010, fn='pl_on_abort')
    m.touch('up', MARGIN + 40, SCREEN_Y0 + R0 + 40, 1080, fn='pl_on_up')
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'the scroll_view\'s abort forgets the press')

    # 8. Nothing is decoded while the scroll_view moves
    m = PM(lists, missing=(7,)); open_page(m)
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([1, 1]))
    calls = tick(m)
    expect(not [c for c in calls if c[0] in ('widget_load_image', 'loadLocalClassList')] and any(c[0] == 'timer_add' for c in calls),
           'while a finger drags the list the loader reads and decodes nothing and keeps polling')
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([0, 0]))
    calls = tick(m)
    expect(any(c[0] == 'loadLocalClassList' for c in calls), 'and goes on the tick after')

    # 8b. Behind another window (the stock songs page of the playlist just tapped) the loader stops: a scan sets classinfo[1] and replaces
    # *pdeq_showlist, the list that page draws its rows from and plays
    m = PM(lists, missing=(7,)); open_page(m)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]
    m.call(fn, a0=c, a1=0, count=4000000)
    expect(any(c_[0] == 'timer_remove' for c_ in m.calls), 'going behind another window removes the loader\'s timer before a scan is done')
    scroll_to(m, 0)
    expect(not [c_ for c_ in m.calls if c_[0] in ('timer_add', 'loadLocalClassList')], 'a scroll event while behind (a fling ending) arms no loader')
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, a1=0, count=60000000)
    expect(any(c_[0] == 'timer_add' and c_[1] == PSYMS['pl_on_load'] for c_ in m.calls), 'back in front the page reads again and the loader runs')

    # 9. Back in the front: the playlists are read again (a playlist may have been edited in the stock page)
    m = PM(lists[:2]); open_page(m); settle(m)
    PM.add(m, 7, 'Fresh', [5, 6])
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, a1=0, count=60000000)
    expect(('loadLocalClassList', O['CLASS_PLAYLISTS']) in m.calls, 'the window coming to the front runs the playlist query again')
    blits, texts, styles = settle(m)
    titles = [t for (t, r), s in zip(texts, styles) if s == 'label_grid_title']
    expect(titles == ['1 Empty', '2 One', 'Fresh'], f'the new list is what the page shows ({titles})')
    expect(all(near(a, b2) for a, b2 in zip(quadrants(m, cell_blit(blits, 2)), want_mosaic([5, 6]))), 'and the new playlist\'s mosaic is made')
    m.playlist_songs[2] = m.playlist_songs[2][:0]
    m.db['/mnt/data/database.db'][0] += 1   # the edit wrote the database
    m.call(fn, a0=c, a1=0, count=60000000)
    blits, texts, styles = settle(m)
    subs = [t for (t, r), s in zip(texts, styles) if s == 'label_grid_sub']
    expect(subs[1:2] == ['0 tracks'] and near(quadrants(m, cell_blit(blits, 1))[0], GREY_DISC),
           f'a playlist emptied in the stock page shows 0 tracks and the placeholder after the next visit ({subs})')

    # 9b. Back in the front with nothing changed (the same playlists, the database file as it was): the scans and the tiles stay, no playlist is queried and nothing is decoded
    DB = '/mnt/data/database.db'
    m = PM(lists); open_page(m); blits0, texts0, styles0 = settle(m)
    subs0 = [t for (t, r), s in zip(texts0, styles0) if s == 'label_grid_sub']
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=c, a1=0, count=4000000)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, a1=0, count=60000000)
    classes = [c_[1] for c_ in m.calls if c_[0] == 'loadLocalClassList']
    expect(classes == [O['CLASS_PLAYLISTS']], f'to the front with nothing changed: only the playlist list is queried, no per-playlist scan ({classes})')
    blits, texts, styles = paint(m)
    expect([t for (t, r), s in zip(texts, styles) if s == 'label_grid_sub' and t] == [t for t in subs0 if t], 'the counts show at once, before any tick')
    log = []
    blits, texts, styles = settle(m, log=log)
    expect(not [c_ for c_ in log if c_[0] in ('loadLocalClassList', 'widget_load_image')], 'complete scans and mosaics (placeholder, one, two, four covers): nothing is scanned or decoded again')
    subs = [t for (t, r), s in zip(texts, styles) if s == 'label_grid_sub']
    expect(subs == subs0 and all(near(a, b2) for a, b2 in zip(quadrants(m, cell_blit(blits, 2)), want_mosaic([1, 2]))), f'the counts and the mosaics are still there ({subs})')
    # a cover file written while another page was open (the Cover Flow build), the database untouched: the playlist whose album had no file is read and composed again, the rest stay
    m = PM(lists, missing=(1, 3)); open_page(m); settle(m)
    blits, texts, styles = paint(m)
    expect(near(quadrants(m, cell_blit(blits, 2))[0], colour(2)), 'a playlist whose first album has no cache file shows the next one alone')
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=c, a1=0, count=4000000)
    for i in (1, 3):
        p = key_path(*alb(i)); m.present.add(p); m.files[p] = 4096; m.images['file://' + p] = (24, 24, struct.pack('<I', colour(i)) * (24 * 24))
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=c, a1=0, count=60000000)
    log = []
    blits, texts, styles = settle(m, log=log)
    scanned = [c_[1:] for c_ in log if c_[0] == 'loadLocalClassList']
    expect(sum(1 for c_ in log if c_[0] == 'widget_load_image' and c_[1] not in ('p_default', 'unselect', 'selected')) > 0, 'the new cover files are decoded after a Back with the database unchanged')
    expect(all(near(a, b2) for a, b2 in zip(quadrants(m, cell_blit(blits, 2)), want_mosaic([1, 2]))), 'the tile now shows the new cover composed with the other')
    expect(len(scanned) == 3, f'only the playlists that had a missing file are read again (Two, Three, Many) ({scanned})')
    # the file still missing: those playlists are read again, but their mosaics (the same albums) are not decoded again
    m = PM(lists, missing=(1, 3)); open_page(m); settle(m)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=c, a1=0, count=4000000)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=c, a1=0, count=60000000)
    log = []
    blits, texts, styles = settle(m, log=log)
    scanned = [c_[1:] for c_ in log if c_[0] == 'loadLocalClassList']
    expect(len(scanned) == 3 and not [c_ for c_ in log if c_[0] == 'widget_load_image' and c_[1] not in ('p_default', 'unselect', 'selected')],
           f'a cover file still missing: the playlists are read again, their unchanged mosaics are not decoded again ({scanned})')
    expect(near(quadrants(m, cell_blit(blits, 2))[0], colour(2)), 'and the tile still shows the album that has a file')
    # a compilation: a guest artist's track of an album already in the mosaic (its own key has no file, the library's is the one added) is no missing cover
    m = PM([(1, 'Comp', [0, 1])]); m.playlist_songs[1].append(m.record(album=alb(0)[1], artist='Guest', path='/mnt/mmc/m/0/2.flac', title='T2', rid=1002))
    open_page(m); settle(m)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=c, a1=0, count=60000000)
    log = []
    settle(m, log=log)
    expect(not [c_ for c_ in log if c_[0] in ('loadLocalClassList', 'widget_load_image')], 'a guest artist\'s track of an album whose cover is in does not make the playlist read again')
    for label, edit in (('renamed', lambda m: m.playlists.__setitem__(1, PM.rec(m, 2, 'Uno'))),
                        ('a playlist added', lambda m: PM.add(m, 7, 'Fresh', [5])),
                        ('a playlist deleted', lambda m: m.playlists.pop(0)),
                        ('reordered', lambda m: m.playlists.reverse()),
                        ('its songs changed (the database written)', lambda m: (m.playlist_songs.__setitem__(2, m.playlist_songs[2][:1]), m.db[DB].__setitem__(0, 101))),
                        ('only the size changed', lambda m: m.db[DB].__setitem__(2, 8192)),
                        ('only the WAL appeared', lambda m: m.db.__setitem__(DB + '-wal', [5, 5, 32])),
                        ('the database unreadable', lambda m: m.db.clear())):
        m = PM(lists[:3], missing=(7,)); open_page(m); settle(m)
        edit(m)
        fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
        m.call(fn, a0=c, a1=0, count=60000000)
        blits, texts, styles = paint(m)
        subs = [t for (t, r), s in zip(texts, styles) if s == 'label_grid_sub' and t]
        expect(not subs, f'{label}: the page is rebuilt (no count shows before the scans are made again: {subs})')

    # 10. The empty state: a centred line, no grid; the menu is still there
    m = PM([]); open_page(m)
    expect(vis(m, 'view_grid')[0] == 0 and vis(m, 'label_status')[0] == 1 and ('widget_set_tr_text', m.widgets['label_status'], 'No playlists') in m.calls,
           'with no playlist the grid is hidden and the status line says "No playlists"')
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1), 'the "..." menu opens on the empty page')
    m.click('vs_scrim'); m.click('btn_plactions')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_item6') == (1, 1), 'and so does the list-plus button\'s (New Playlist is what an empty page needs)')

    # 11. The menu: open, close by the button, by the scrim, by an action; the actions run the stock code
    m = PM(lists, missing=(7,)); open_page(m); settle(m)
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1), 'the "..." button shows the card and the scrim (visible and sensitive)')
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0), 'and a second tap closes them (hidden and insensitive)')
    m.click('btn_more'); m.click('vs_scrim')
    expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0), 'a tap on the scrim closes the menu')
    # the list-plus button opens its own card (the actions); one card at a time: while either is open a tap on the other button is ignored
    m.click('btn_plactions')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1) and m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass4', 'the list-plus button shows the card and the scrim')
    m.calls = []; m.click('btn_more'); m.click('btn_plactions')
    expect(vis(m, 'vs_card') == (1, 1) and not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['vs_card']], 'while the list-plus button\'s card is open a tap on the "..." or the list-plus button changes nothing (the scrim lies over them, and the handlers ignore it too)')
    m.click('vs_scrim')
    m.click('btn_more'); m.click('btn_plactions')
    expect(vis(m, 'vs_card') == (1, 1) and m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass3' and vis(m, 'vs_item6') == (0, 0) and vis(m, 'vs_item4') == (1, 1),
           'while the "..." card is open the list-plus button is ignored: it still holds Grid and List, not the actions')
    m.click('vs_scrim')
    # New playlist: our keyboard opens (stock's T9 dialog is gone); its Done calls pl_named: createPlayListItem on the freshly read stock list, then the page reads again.
    # (The keyboard's own behaviour, with this callback as its on_done, is test/pod/keyboard.py name_tests; this machine has no keyboard asset, so the open itself fails here.)
    m.click('btn_plactions'); m.calls = []
    m.click('vs_item6')
    expect(vis(m, 'vs_card') == (0, 0) and ('window_open', 'm1plus_keyboard') in m.calls and not [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'dialog/kbaddplaylist_dialog']
           and not [c for c in m.calls if c[0] in ('createPlayListItem', 'loadLocalClassList')],
           'New playlist: the menu closes and our keyboard page is opened; nothing is created and the list is not read until Done (the keyboard is not modal)')
    m.calls = []
    m.call(PSYMS['pl_named'], a0=m.cstr('Mix'), count=40000000)
    order = [c for c in m.calls if c[0] in ('loadLocalClassList', 'createPlayListItem')]
    expect([c[0] for c in order] == ['loadLocalClassList', 'createPlayListItem', 'loadLocalClassList'] and order[0][1] == order[2][1] == O['CLASS_PLAYLISTS']
           and ('createPlayListItem', 'Mix', len(lists)) in m.calls and 'stock_resume' not in m.names(),
           f'Done: the stock list is read, createPlayListItem(stock list, name) makes the playlist, the page reads again ({[c[0] for c in order]})')
    for ret, key in ((-1, 'msg_playlistfull'), (-2, 'msg_playlistexist')):
        m.create_ret = ret; m.calls = []
        m.call(PSYMS['pl_named'], a0=m.cstr('Mix'), count=40000000)
        expect([c for c in m.calls if c[0] == 'toast'] == [('toast', key, 1, 2000)], f'a playlist that cannot be made says {key} in the stock message box ({[c for c in m.calls if c[0] == "toast"]})')
    m.create_ret = 5
    # Import / Export: the stock click handlers, in the normal (not multi-select) mode, then the page reads again
    for item, handler in (('vs_item7', 'stock_playlist_import'), ('vs_item8', 'stock_playlist_export')):
        m.setword(NAV_STATUS, 1); m.calls = []
        m.click(item)
        expect([c for c in m.calls if c[0] == handler] == [(handler, 0)] and m.word(NAV_STATUS) == 0
               and ('loadLocalClassList', O['CLASS_PLAYLISTS']) in m.calls, f'{item}: the stock {handler[15:]} handler runs with the list in normal mode, then the page reads again')
    # Delete Playlists: select mode on this page (select_tests below); the stock Playlists page only where the page cannot do it
    m.calls = []
    m.click('vs_item9')
    expect('stock_resume' not in m.names() and vis(m, 'vs_card') == (0, 0) and vis(m, 'pl_bar') == (1, 1), 'Delete Playlists starts select mode on this page (select_tests); the stock page stays closed')
    select_tests(expect, lists)

    # 11b. The two cards' shape and fit to the language, the list-plus button's four rows in vs_glass4, the "..." three in vs_glass3, packed from the top. The list-plus button's: New Playlist, Import, Export, Delete Playlists, no hairline. The "...": Grid, List, one
    #      hairline (the first sort row's top border), Name; the view and the order ticked with their direction line under it. Each as wide as its widest label (or direction line) from its
    #      own x plus 16, 206..292, its right edge at 311, its top at 52
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    px = lambda t: StbText(font, 15 if t in ('A–Z', 'Z–A') else pod_ui.PL_LABEL_PX).layout(t)[1]
    def fit(m):
        moves = [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets['vs_card']]
        sizes = {n: c[2:] for c in m.calls if c[0] == 'widget_resize' for n in m.widgets if m.widgets[n] == c[1] and n.startswith('vs_')}
        return (moves[-1] if moves else None), sizes
    def card_for(loc, measure, mode=None, button='btn_more'):
        m = PM(lists)
        if mode is not None: m.fs[PL_FILE] = mode
        open_page(m)
        texts = [built[loc][k] for k in ('Name', 'Name', 'Name', 'Name', 'Grid', 'List') + tuple(pod_pages.PLAYLIST_MENU)]
        for i, t in enumerate(texts): m.label_text[m.widgets[f'vs_label{i}']] = t
        m.measure = measure; m.calls = []
        m.click(button)
        return m, texts
    def moved_of(m, rows): return [[c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'vs_item{i}']][-1] for i in rows]
    glass = lambda m: [m.props.get((m.widgets['vs_card'], f'style:{st}:bg_image')) for st in ('normal', 'pressed', 'over')]
    ACTS, MORE = (6, 7, 8, 9), (4, 5, 0)
    m, _ = card_for('en_US', px, button='btn_plactions')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1) and [vis(m, f'vs_item{i}') for i in ACTS] == [(1, 1)] * 4 and [vis(m, f'vs_item{i}') for i in (0, 1, 2, 3, 4, 5)] == [(0, 0)] * 6
           and moved_of(m, ACTS) == [(0, 48 * k) for k in range(4)] and vis(m, 'vs_hair')[0] == 0 and glass(m) == ['vs_glass4'] * 3,
           f'the list-plus button\'s card: the four actions in four rows packed from the top, no hairline, vs_glass4 ({moved_of(m, ACTS)})')
    m, _ = card_for('en_US', px)
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1) and [vis(m, f'vs_item{i}') for i in MORE] == [(1, 1)] * 3 and [vis(m, f'vs_item{i}') for i in (1, 2, 3, 6, 7, 8, 9)] == [(0, 0)] * 7
           and moved_of(m, MORE) == [(0, 48 * k) for k in range(3)] and vis(m, 'vs_hair')[0] == 0 and glass(m) == ['vs_glass3'] * 3
           and m.props.get((m.widgets['vs_item0'], 'style:normal:border_width')) in (None, 1),
           f'the "..." card: Grid, List, Name in three rows, the hairline is Name\'s top border, vs_glass3 ({moved_of(m, MORE)})')
    expect([vis(m, f'vs_tick{i}')[0] for i in (4, 5, 0)] == [1, 0, 1] and [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['vs_sub0']] == ['A–Z'],
           'the grid is ticked (the default), Name is ticked with A–Z under it')
    m, _ = card_for('en_US', px, b'0\n')
    expect([vis(m, f'vs_tick{i}')[0] for i in (4, 5)] == [0, 1], 'in the list mode the List row is ticked')
    m = PM(lists); m.fs['/mnt/data/m1plus/playlists-sort'] = b'a\n'; open_page(m); m.calls = []; m.click('btn_more')
    expect(vis(m, 'vs_tick0')[0] == 1 and [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['vs_sub0']] == ['Z–A']
           and moved_of(m, (0,)) == [(0, 96)], 'with the saved order Z–A, Name is ticked, "Z–A" under it (Name is the third row)')
    m.click('vs_scrim'); m.click('btn_plactions'); m.click('vs_scrim'); m.click('btn_more')
    expect(m.props.get((m.widgets['vs_item0'], 'style:normal:border_width')) == 1 and glass(m) == ['vs_glass3'] * 3,
           'the card offered again after the list-plus button\'s gets the hairline back (Name\'s top border) and the same glass')
    for loc in pod_i18n.LOCALES:
        m, texts = card_for(loc, px, button='btn_plactions')
        lx = O['VS_TICK_X'] + O['VS_LABEL_X_GLYPH'] - O['VS_GLYPH_X']   # no tick column: the glyph at x 14, the label 28 px after it
        w = max(O['VS_CARD_MIN'], min(O['PL_CARD_MAX'], lx + max(px(t) for t in texts[6:]) + O['VS_LABEL_R']))
        pos, sizes = fit(m)
        moved = lambda name: [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[name]][-1]
        expect(pos == (311 - w, 52) and sizes.get('vs_card') == (w, 4 * 48) and all(sizes.get(f'vs_item{i}') == (w, 48) for i in ACTS) and 206 <= w <= 292
               and all(moved(f'vs_glyph{i}') == (O['VS_TICK_X'], 14) for i in ACTS) and all(moved(f'vs_label{i}') == (lx, 0) for i in ACTS) and lx == 42,
               f'{loc}: the list-plus button\'s card {w} px wide, x {311 - w}..311, 192 px high, glyphs at x 14 and labels at x 42 (no tick column) ({pos}, {sizes.get("vs_card")})')
        m, texts = card_for(loc, px)
        w = max(O['VS_LABEL_X_GLYPH'] + max(px(t) for t in texts[4:6]), O['VS_LABEL_X'] + max(px(texts[0]), px('A–Z'))) + O['VS_LABEL_R']
        w = max(O['VS_CARD_MIN'], min(O['PL_CARD_MAX'], w))
        pos, sizes = fit(m)
        moved = lambda name: [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[name]][-1]
        expect(pos == (311 - w, 52) and sizes.get('vs_card') == (w, 3 * 48) and all(sizes.get(f'vs_item{i}') == (w, 48) for i in MORE) and 206 <= w <= 292
               and all(moved(f'vs_glyph{i}') == (O['VS_GLYPH_X'], 14) for i in (4, 5)) and moved('vs_label4') == (O['VS_LABEL_X_GLYPH'], 0),
               f'{loc}: the "..." card {w} px wide, x {311 - w}..311, 144 px high ({pos}, {sizes.get("vs_card")})')
    m, _ = card_for('en_US', lambda t: 300)
    expect(fit(m)[0] == (19, 52) and fit(m)[1].get('vs_card') == (292, 144), f'a label wider than the room keeps the widest card (292 px, its ellipsis): {fit(m)}')
    m, _ = card_for('en_US', None)
    expect(fit(m)[0] is None and vis(m, 'vs_card') == (1, 1), 'a label that cannot be measured leaves the asset\'s card (292 px), and the menu opens')
    m, _ = card_for('en_US', lambda t: 100)
    m.click('btn_more'); m.measure = lambda t: 200; m.calls = []
    m.click('btn_more')
    expect(fit(m)[1].get('vs_card') == (282, 144) and fit(m)[0] == (29, 52), f'every open measures again (a language changed meanwhile): {fit(m)}')

    # 12. Closing frees everything
    m = PM(lists, missing=(7,)); open_page(m); settle(m)
    m.calls = []
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=20000000)
    alive = len(m.bitmaps)
    expect(alive == 0, f'closing the page destroys every tile and the placeholder ({alive} left)')
    open_page(m)
    expect(('window_open', 'm1plus_playlists') in m.calls, 'and the page opens again')

    # 13. List mode (the Albums page's): 64 px rows, a 52 px mosaic (quadrants of 26 px), the name and the count in the list's two text styles
    ROW, LART, LAX, LAY = O['LIST_ROW_H'], O['LIST_ART'], O['LIST_ART_X'], O['LIST_ART_Y']
    TX, TW, TY, TH, SY, SH = O['LIST_TEXT_X'], O['LIST_TEXT_W_CHEV'], O['LIST_TITLE_Y'], O['LIST_TITLE_H'], O['LIST_SUB_Y'], O['LIST_SUB_H']
    m = PM(lists, missing=(7,)); open_page(m)
    expect(glyph(m) == 'pod_nav_list' and m.fs.get(PL_FILE) is None, 'with no setting the page opens as the grid (the toggle shows the list glyph)')
    m = PM(lists, missing=(7,)); m.fs[PL_FILE] = b'0\n'; calls = open_page(m)
    expect(glyph(m) == 'pod_nav_grid', 'the saved "0" opens the list mode: the card ticks List (the old toggle would show the grid glyph)')
    expect(('bitmap_create_ex', LART, LART) in calls and not any(c[:3] == ('bitmap_create_ex', COVER, COVER) for c in calls), 'its covers are 52 px bitmaps')
    h = m.word(m.widgets['view_grid'] + 0xc)
    expect(h == TOP + len(lists) * ROW and m.props.get((m.sv, 'virtual_h')) == h, f'the content is {len(lists)} rows of {ROW} px = {h} and the scroll_view is told')
    scroll_to(m, 60); blits_end, _, _ = settle(m)   # the last row is only partly in view at the top: its cover is checked scrolled 60 px down
    scroll_to(m, 0); blits, texts, styles = settle(m)
    for i, (pid, name, songs) in enumerate(lists):
        src, dy = (blits, 0) if i < len(lists) - 1 else (blits_end, 60)
        b = next((x[0] for x in src if x[2] == (LAX, TOP + i * ROW + LAY - dy, LART, LART)), None)
        distinct = []
        for a in songs:
            if a not in distinct and a != 7: distinct.append(a)
        w = want_mosaic(distinct[:4])
        q = quadrants(m, b, LART) if b else []
        expect(b is not None and (all(near(x, y) for x, y in zip(q, w)) if w else len(set(q)) == 1 and near(q[0], GREY_DISC)),
               f'row {i} ({name}): its 52 px cover is the {len(distinct[:4])}-album mosaic in 26 px quadrants ({[hex(x) for x in q]})')
    got = {st: {(r[1] - TOP) // ROW: t for (t, r), s in zip(texts, styles) if s == st} for st in ('label_row_title', 'label_row_sub')}
    expect(got['label_row_title'] == {i: l[1] for i, l in enumerate(lists)}
           and got['label_row_sub'] == {i: ('1 track' if len(l[2]) == 1 else f'{len(l[2])} tracks') for i, l in enumerate(lists)}, f'each row shows the name and the count ({got})')
    expect(all(r[0] == TX and r[2] == TW and ((r[1] - TOP) % ROW, r[3]) in ((TY, TH), (SY, SH)) for (t, r) in texts), 'the texts are in the list rows\' rects')
    expect(sorted(f[1:] for f in m.fills if f[0] == O['LIST_HAIR']) == [(TX, TOP + i * ROW + ROW - 1, O['LIST_HAIR_END'] - TX, 1) for i in range(5)], 'a hairline from the text to LIST_HAIR_END closes each row')
    cy = lambda i: TOP + i * ROW + (ROW - 1 - 16) // 2   # the chevron's top; the sixth row's is cut at the window's foot (its row is partly in view)
    expect(sorted(b[2] for b in chevs_of(m, blits)) == [(O['LIST_CHEV_X'], cy(i), 10, 16) for i in range(5)] + [(O['LIST_CHEV_X'], cy(5), 10, VIEW_H - cy(5))], 'and a chevron ends it')
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'a hairline closes each row, no row is pressed')
    #     a tap on a row (any x) opens its playlist; the press fills the row until the release
    m.touch('down', 300, SCREEN_Y0 + TOP + 3 * ROW + 20, 1000, fn='pl_on_down')
    blits, texts, styles = paint(m)
    expect([f for f in m.fills if f[0] == O['LIST_PRESS']] == [(O['LIST_PRESS'], 0, TOP + 3 * ROW, 320, ROW - 1)], 'a finger down fills its row with the pressed colour')
    m.windows['m1plus_songs'] = 0   # (our Songs page will not open: the stock one shows which playlist the tap opened)
    m.touch('up', 300, SCREEN_Y0 + TOP + 3 * ROW + 20, 1080, fn='pl_on_up')
    opened = [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'allmusic_page']
    expect(('window_open', 'm1plus_songs') in m.calls and opened == [('navigator_to_with_context', 'allmusic_page', O['CLASS_PLAYLIST_SONGS'], lists[3][0], lists[3][1])],
           f'a tap on row 3 opens its playlist ({opened})')
    paint(m)
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'and the fill is gone')
    calls = tap(m, 100, TOP + 5 * ROW + 70)
    expect(not [c for c in calls if c[0] == 'navigator_to_with_context'], 'below the last row nothing opens')
    m.touch('down', 40, SCREEN_Y0 + 20, 1000, fn='pl_on_down'); m.touch('abort', 40, SCREEN_Y0 + 20, 1010, fn='pl_on_abort'); paint(m)
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'the scroll_view\'s abort clears the pressed row')
    #     the toggle: both ways in place, saved, the first playlist in view kept
    many = [(i + 1, f'P{i}', [i % 7]) for i in range(12)]
    m = PM(many); open_page(m); settle(m)
    scroll_to(m, 300); first_grid = 2
    m.calls = []; switch(m)
    expect(glyph(m) == 'pod_nav_grid' and m.fs.get(PL_FILE) == b'0\n' and not [c for c in m.calls if c[0] in ('window_open', 'navigator_to_with_context', 'window_close')],
           'the toggle switches to the list in place and saves "0"')
    expect(m.word(m.sv + SC_YOFF) == TOP + first_grid * ROW and m.word(m.widgets['view_grid'] + 0xc) == TOP + 12 * ROW and m.props.get((m.sv, 'virtual_h')) == TOP + 12 * ROW,
           'the first playlist in view stays at the top; the content is 12 rows')
    blits, texts, styles = settle(m)
    expect(('bitmap_create_ex', LART, LART) in m.calls or any(m.bitmaps[b][1] == LART for b in m.bitmaps), 'the tiles were remade at 52 px')
    tiles_ = [b for b in m.bitmaps if m.bitmaps[b][1:] != (10, 16) and m.bitmaps[b][1] != MARK]   # (the two select marks are 26 px and live as long as the page)
    expect(all(m.bitmaps[b][1] == LART for b in tiles_) and len(tiles_) <= TILES + 1, 'no 144 px tile survives the switch; the ring is bounded')
    m.calls = []; switch(m)
    expect(glyph(m) == 'pod_nav_list' and m.fs.get(PL_FILE) == b'1\n' and m.word(m.sv + SC_YOFF) == TOP + first_grid // COLS * PITCH,
           'back to the grid: "1" saved, the glyph back, the first playlist in view kept')
    settle(m)
    expect(all(m.bitmaps[b][1] in (COVER, MARK) or m.bitmaps[b][1:] == (10, 16) for b in m.bitmaps), 'and the tiles are 144 px again')
    #     the choice survives a re-open, and is the Albums page's own file apart
    switch(m)
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=20000000)
    open_page(m)
    expect(glyph(m) == 'pod_nav_grid' and PL_FILE != '/mnt/data/m1plus/albums-view', 'the list mode is remembered when the page is opened again, in its own file')
    m.fs['/mnt/data/m1plus/albums-view'] = b'1\n'; m.fs[PL_FILE] = b'junk'
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=20000000)
    open_page(m)
    expect(glyph(m) == 'pod_nav_list', 'garbage in the file is the grid')
    m.fs[PL_FILE] = b'0x'
    m.call(fn, a0=c, a1=0, count=20000000)
    open_page(m)
    expect(glyph(m) == 'pod_nav_list', 'trailing junk after "0" is the grid too')
    #     the loader rules hold in the list: one step a tick, nothing while the list is dragged
    m = PM(many); m.fs[PL_FILE] = b'0\n'; open_page(m)
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([1, 1]))
    calls = tick(m)
    expect(not [c for c in calls if c[0] in ('widget_load_image', 'loadLocalClassList')], 'the list mode decodes and reads nothing while the list is dragged')
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([0, 0]))
    settle(m)
    expect(m.most_per_tick <= 1, 'and one cover source at most a tick')
    # the menu works in the list mode too
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (1, 1), 'the "..." menu opens in the list mode')

    # The navbar's fade (img_nb_fade, built hidden) is shown only while the list is scrolled; insensitive throughout; without the widget nothing happens.
    for mode in ('1', '0'):
        m = PM(many); m.fs[PL_FILE] = (mode + '\n').encode()
        fade = Machine.widget(m, 'img_nb_fade'); m.props[(fade, 'visible')] = 0
        state = lambda: (m.props.get((fade, 'visible')), m.props.get((fade, 'sensitive'), 0))
        open_page(m)
        s = [state()]
        for v in (1, 300, 0):
            scroll_to(m, v); s.append(state())
        expect(s == [(0, 0), (1, 0), (1, 0), (0, 0)], f'{"grid" if mode == "1" else "list"}: the fade is hidden at rest, shown (insensitive) when scrolled, hidden again back at 0 ({s})')
        scroll_to(m, 300); switch(m)
        expect(state() == ((1, 0) if m.word(m.sv + SC_YOFF) > 0 else (0, 0)), f'a mode switch: the fade follows the new offset ({m.word(m.sv + SC_YOFF)}, {state()})')
    m = PM(many); open_page(m); scroll_to(m, 300)
    expect(m.word(m.sv + SC_YOFF) == 300, 'no fade widget: the page opens and scrolls as before')

    # 14. The Name order (the card's last row): A-Z by default, the ticked row reverses, saved in playlists-sort ("a" Z-A); the stock list is never reordered, so the rows, the taps and the
    #     select mode's marks follow the order shown while the stock calls keep the stock positions; every playlist keeps its scan across a re-sort
    PLS = '/mnt/data/m1plus/playlists-sort'
    named = [(1, 'beta', [0]), (2, 'Alpha', [1, 2]), (3, '10 mix', [3]), (4, '2 mix', [4, 5, 6]), (5, 'Zed', [])]
    AZ, ZA = ['2 mix', '10 mix', 'Alpha', 'beta', 'Zed'], ['Zed', 'beta', 'Alpha', '10 mix', '2 mix']
    COUNT = {'beta': '1 track', 'Alpha': '2 tracks', '10 mix': '1 track', '2 mix': '3 tracks', 'Zed': '0 tracks'}
    ROW = O['LIST_ROW_H']
    def list_page(saved=None):
        m = PM(named); m.fs[PL_FILE] = b'0\n'
        if saved is not None: m.fs[PLS] = saved
        open_page(m)
        return m
    def rows(m, log=None):
        blits, texts, styles = settle(m, log=log)
        title = {(r[1] - TOP) // ROW: tx for (tx, r), st in zip(texts, styles) if st == 'label_row_title'}
        sub = {(r[1] - TOP) // ROW: tx for (tx, r), st in zip(texts, styles) if st == 'label_row_sub'}
        return [title[k] for k in sorted(title)], [sub.get(k) for k in sorted(title)]
    expect('playlists-sort' in pod_pages.SETTING_FILES and pod_pages.SETTING_FILES.index('playlists-sort') == pod_pages.SETTING_FILES.index('folders-sort') + 1 and pod_pages.SETTING_FILES.count('playlists-sort') == 1,
           'playlists-sort is on the Settings Files page, after folders-sort and before playlists-view (patch/setfiles.c has it in the same place)')
    m = list_page()
    names_, subs_ = rows(m)
    expect(names_ == AZ and subs_ == [COUNT[n] for n in AZ] and PLS not in m.fs, f'no playlists-sort: Name A-Z, digit runs by value, case folded, not the stock order ({names_}); nothing is written ({subs_})')
    m.click('btn_more')
    expect(vis(m, 'vs_tick0')[0] == 1 and [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['vs_sub0']][-1:] == ['A–Z'], 'the card ticks Name with A–Z under it')
    m.calls = []
    m.click('vs_item0')
    expect(m.fs.get(PLS) == b'a\n' and ('rename', PLS + '.tmp', PLS) in m.calls and vis(m, 'vs_card') == (0, 0), 'the ticked Name row again: Z–A saved as "a", written through the .tmp file, the card closes')
    log = []
    names_, subs_ = rows(m, log)
    expect(names_ == ZA and subs_ == [COUNT[n] for n in ZA] and not [c for c in log + list(m.calls) if c[0] == 'loadLocalClassList'],
           f'the list is reversed, each playlist with its own count, and nothing is read again: the scans went with their playlists ({names_}, {subs_})')
    m.click('btn_more'); m.click('vs_item0')
    names_, _ = rows(m)
    expect(m.fs.get(PLS) == b'0\n' and names_ == AZ, 'and again: A–Z, "0"')
    for saved, want in ((b'a\n', ZA), (b'a', ZA), (b'0\n', AZ), (b'junk', AZ), (b'ax', AZ), (b'', AZ), (b'1\n', AZ), (b'b\n', AZ)):   # (the retired Recently Added values read as A–Z)
        names_, _ = rows(list_page(saved))
        expect(names_ == want, f'playlists-sort {saved!r}: {"Z–A" if want == ZA else "A–Z"}')
    m = list_page(); rows(m); m.fail.add(('rename', PLS)); m.click('btn_more'); m.click('vs_item0')
    expect(rows(m)[0] == AZ and PLS not in m.fs, 'a save that fails changes nothing')
    m = PM(named); open_page(m)
    blits, texts, styles = settle(m)
    grid_ = {(r[1] - R0) // PITCH * COLS + (r[0] - MARGIN) // CPITCH: tx for (tx, r), st in zip(texts, styles) if st == 'label_grid_title'}
    expect([grid_[k] for k in sorted(grid_)][:4] == AZ[:4], f'the grid shows the same order ({grid_})')
    # opening follows the rows shown, not the stock positions
    for saved, want in ((None, (4, '2 mix')), (b'a\n', (5, 'Zed'))):
        m = list_page(saved); m.windows['m1plus_songs'] = 0; rows(m)
        calls = tap(m, 100, TOP + 20)
        opened = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'allmusic_page']
        expect(opened == [('navigator_to_with_context', 'allmusic_page', O['CLASS_PLAYLIST_SONGS'], *want)], f'a tap on the first row opens {want[1]!r} (id {want[0]}) ({opened})')
    # Delete: the marks are of the rows shown; the stock vector holds the stock positions
    m = list_page(); rows(m); m.setword(SEL_VEC, m.alloc(8)); m.confirm_yes = True
    m.click('btn_plactions'); m.click('vs_item9'); tap(m, 150, TOP + 0 * ROW + 20); tap(m, 150, TOP + 2 * ROW + 20); m.calls = []
    m.click('pl_del')
    bd = next((c for c in m.calls if c[0] == 'batch_delete_file'), None)
    expect([c[1] for c in m.calls if c[0] == 'set_selectindex'] == [3, 1] and bd and bd[:2] == ('batch_delete_file', O['CLASS_PLAYLISTS']) and bd[6] == [1, 3],
           f'rows 0 and 2 shown are "2 mix" and "Alpha": the stock positions 3 and 1 are selected, in the stock list ({[c[1] for c in m.calls if c[0] == "set_selectindex"]}, {bd and bd[6]})')
    # the empty page: the card is there and the order is saved
    m = PM([]); open_page(m); m.click('btn_more'); m.click('vs_item0')
    expect(m.fs.get(PLS) == b'a\n' and vis(m, 'vs_card') == (0, 0) and vis(m, 'label_status')[0] == 1, 'with no playlist the Name row still saves the order and the page stays as it was')

    # 15. The large title (pl_title, as the Albums page's): the first thing in the content, the navbar's small title hidden until the offset reaches SG_COLLAPSE,
    #     the fade while scrolled; the rows, the cells and the taps lie TOP px lower in the content, so the hits follow the scroll
    COLLAPSE = O['SG_COLLAPSE']
    tree15 = awtk_ui.parse(open(UI, 'rb').read())
    big15, grid15 = tree15.find('pl_title'), tree15.find('view_grid')
    expect(big15 is not None and grid15.children[:1] == [big15] and (big15.x, big15.y, big15.w, big15.h) == (O['SG_TITLE_X'], 0, O['SG_TITLE_W'], TOP)
           and big15.get('sensitive') == 'false' and big15.get('style:normal:font_size') == '32' and big15.get('style:normal:text_color') == '#FFFFFF',
           'the asset: pl_title, the first child of view_grid: 32 px white at SG_TITLE_X, SG_TITLE_W wide, SG_TITLE_H high, insensitive')
    expect(tree15.find('label_title').get('visible') == 'false' and tree15.find('img_nb_fade') is not None, 'the navbar\'s small title starts hidden; the fade is in the asset')
    opened = lambda calls: [c for c in calls if c[0] in ('window_open', 'navigator_to_with_context')]
    for mode, f in (('grid', b'1\n'), ('list', b'0\n')):
        m = PM(lists, missing=(7,)); m.fs[PL_FILE] = f; open_page(m)
        big, small, fade = m.widgets['pl_title'], m.widgets['label_title'], m.widgets['img_nb_fade']
        expect(('widget_set_text_utf8', big, 'Playlists') in m.calls, f'{mode}: the large title reads Playlists')
        h = m.word(m.widgets['view_grid'] + 0xc)
        expect(h == TOP + (RGAP + 3 * PITCH if mode == 'grid' else 6 * O['LIST_ROW_H']) and m.props.get((m.sv, 'virtual_h')) == h,
               f'{mode}: the content is the title block and the playlists ({h})')
        blits, _, _ = settle(m)
        first = cell_blit(blits, 0) if mode == 'grid' else next((b[0] for b in blits if b[2][:2] == (O['LIST_ART_X'], TOP + O['LIST_ART_Y'])), None)
        expect(first is not None, f'{mode}: the first playlist starts under the title block')
        expect(m.props.get((small, 'visible'), 0) == 0 and ('widget_set_visible', small, 1) not in m.calls and m.props.get((fade, 'visible'), 0) == 0,
               f'{mode}: at rest the small title and the fade are hidden')
        scroll_to(m, COLLAPSE - 1)
        expect(m.props.get((small, 'visible'), 0) == 0 and m.props.get((fade, 'visible')) == 1, f'{mode}: one px short of SG_COLLAPSE the title is still hidden, the fade shows')
        scroll_to(m, COLLAPSE)
        expect(m.props.get((small, 'visible')) == 1 and m.props.get((fade, 'sensitive')) == 0, f'{mode}: at SG_COLLAPSE the small title shows')
        # the stock scroll moves the content view with the offset: the taps are told through its place (widget_to_local)
        m.setword(m.widgets['view_grid'] + 4, (-COLLAPSE) & 0xffffffff)
        m.calls = []
        expect(not opened(tap(m, 100, TOP - 5 - COLLAPSE)), f'{mode}: a tap on the title block (scrolled up under the navbar) opens nothing')
        m.calls = []
        opened_at = opened(tap(m, MARGIN + 40, (R0 if mode == 'grid' else TOP) - COLLAPSE + 10))
        expect(opened_at, f'{mode}: scrolled to SG_COLLAPSE, a tap on the first playlist (its top {COLLAPSE} px up) opens it')
        scroll_to(m, 0); m.setword(m.widgets['view_grid'] + 4, 0)
        expect(m.props.get((small, 'visible')) == 0 and m.props.get((fade, 'visible')) == 0, f'{mode}: back at the top they go')
        m.calls = []
        expect(not opened(tap(m, 100, TOP - 5)), f'{mode}: at the top a tap on the title block opens nothing')
        m.calls = []
        expect(opened(tap(m, MARGIN + 40, R0 + 10 if mode == 'grid' else TOP + 10)), f'{mode}: a tap on the first playlist opens it, below the title')
        m2 = PM(lists, missing=(7,)); m2.fs[PL_FILE] = f; m2.widget_on_fail = frozenset({O['EVT_SCROLL']}); open_page(m2)
        expect(('widget_set_visible', m2.widgets['label_title'], 1) in m2.calls, f'{mode}: without the scroll events the navbar keeps its title')
    # select mode: the navbar reads "N Selected" (shown), the large title stays in the content; back to the list, the small title goes again
    m = PM(lists, missing=(7,)); open_page(m); settle(m)
    m.click('btn_plactions'); m.click('vs_item9')
    expect(m.props.get((m.widgets['label_title'], 'visible')) == 1 and ('widget_set_visible', m.widgets['pl_title'], 0) not in m.calls,
           'select mode: the small title shows "N Selected", the large title is not hidden')
    m.click('btn_return')
    expect(m.props.get((m.widgets['label_title'], 'visible')) == 0, 'back from select mode the small title is hidden again at the top')
    # no playlists: the title goes with the empty grid, as the Albums page's empty state
    m = PM([]); open_page(m)
    expect(vis(m, 'view_grid') == (0, 0) and m.props.get((m.widgets['label_title'], 'visible'), 0) == 0, 'the empty page hides the grid and its title; the small title stays hidden')


def run(ctx):
    for s in SECTIONS: s(ctx)


SECTIONS = [stock_tests, src_tests]

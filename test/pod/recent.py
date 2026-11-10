"""The Recently Played shelf of the menu's Home instance (patch/recent.c, tools/pod_ui.py shelf(), tools/pod_recent.py, docs/modules/recent.md): the constants
shared with patch/offsets.inc, the asset, the list file (round trip, malformed files, order, de-duplication, the cap of six, no write when nothing
changed), recording from the mini bar's tick and from Now Playing's, the shelf's start (a one-shot first, then nothing runs in the first paint), the
tiles (one cover per tick, never in paint, rounded corners, the placeholder), the texts, the rows placed below the shelf and the relayouts of demo's own
layouter (with and without the mini bar's spacer), hit tests with demo's own widget_find_target, taps and swipes through demo's own pointer code (the
scroll_view, the list gesture hook), opening the right album through the mocked stock calls, the refresh when the menu is in front again, the Settings
switch and every failure falling back to the plain menu."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import pod_recent
EX = len(pod_pages.ITEMS)   # the Extras row's index, the last of the menu's rows


pulldown, minibar, nowplaying = sibling('pulldown'), sibling('minibar'), sibling('nowplaying')

CARD = '/mnt/mmc/.m1plus'
RECENT, RECENT_TMP = '/mnt/mmc/.m1plus/recently-played', '/mnt/mmc/.m1plus/recently-played.tmp'
SHELF_SET, SHELF_TMP = '/mnt/data/m1plus/home-recent-albums', '/mnt/data/m1plus/home-recent-albums.tmp'
WIN = 0x24000000
EVT_DESTROY, EVT_AFTER_PAINT, EVT_CLICK = O['EVT_DESTROY'], O['EVT_AFTER_PAINT'], O['EVT_CLICK']
EVT_BG, EVT_FG = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']
EVT_DOWN, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
# the shelf is the Albums grid's cell geometry (GRID_* of patch/offsets.inc) in a view of its own: 2 columns, 1 or 2 rows
GRID_COVER, GRID_GAP, GRID_MARGIN, GRID_ROW_GAP, GRID_COLS = (O[k] for k in ('GRID_COVER', 'GRID_GAP', 'GRID_MARGIN', 'GRID_ROW_GAP', 'GRID_COLS'))
GRID_TITLE_GAP, GRID_TITLE_H, GRID_SUB_H = O['GRID_TITLE_GAP'], O['GRID_TITLE_H'], O['GRID_SUB_H']
CELL = GRID_COVER + GRID_TITLE_GAP + GRID_TITLE_H + GRID_SUB_H
PITCH = CELL + GRID_ROW_GAP
SH_TILES, SH_TOP, SH_R, SH_ROWS = O['SH_TILES'], O['SH_TOP'], O['GRID_R'], O['SH_ROWS']   # the shelf's corners are the Albums grid's
def SH_Hn(n): return SH_TOP + n * CELL + (n - 1) * GRID_ROW_GAP                      # n rows of covers
SH_H1, SH_H2, SH_H3 = SH_Hn(1), SH_Hn(2), SH_Hn(3)
SH_COVER = GRID_COVER
TITLE_OFF = GRID_COVER + GRID_TITLE_GAP             # the album line below a cell's top
SUB_OFF = TITLE_OFF + GRID_TITLE_H                  # and the artist line
def shh(n): return SH_Hn((n + GRID_COLS - 1) // GRID_COLS)     # the shelf's height for n albums: ceil(n / 2) rows
SH_H = SH_H2        # most tests show three albums: two rows
GREY = 0xff2b2b2b      # grid.h GRID_GREY (checked below)
assert '0xff2b2b2bu' in open(os.path.join(ROOT, 'patch', 'grid.h')).read()
ROW_H, MB_PAD = 52, O['MB_PAD']
SHELF_NAMES = pod_ui.SH_NAMES
OPEN_ALBUM = pod.FUNCTIONS['loadAlbumList'][2]




def tile_x(i): return GRID_MARGIN + i % GRID_COLS * (GRID_COVER + GRID_GAP)       # cell i's x
def cell_y(i): return SH_TOP + i // GRID_COLS * PITCH                                   # its top in the shelf


def u(s): return s.encode('utf-8').decode('latin-1')   # the model keeps a file's bytes as latin-1 characters


def entry(artist, album, path=None):
    """A list entry as the payload stores it (strings as the model reads them)."""
    return (pod_recent.identity(album), album_key(artist, album), 0, u(album), u(artist), u(path if path is not None else f'/mnt/mmc/{artist}/{album}/1.flac'))


ALBUMS = [('Miles Davis', 'Kind of Blue'), ('Nina Simone', 'Pastel Blues'), ('Boards of Canada', 'Music Has the Right to Children'),
          ('Björk', 'Homogenic'), ('Aphex Twin', 'Selected Ambient Works'), ('Portishead', 'Dummy'), ('Radiohead', 'Kid A'), ('Massive Attack', 'Mezzanine')]


def ents(n): return [entry(*ALBUMS[i]) for i in range(n)]


CUR = [None]    # the machine built last: sy() reads its scroll position


class ST(pulldown.SM):
    """The Home instance of the menu as real widget structs (window > list_view > scroll_view > [shelf, rows..., spacer]), demo's own pointer, layout and
    scroll_view code on top and the payload opened on it: the stock calls the shelf makes are mocked or the real ones, as the pulldown test has them."""
    DELIVER = True

    def __init__(self, entries=None, setting=None, bar=False, start=True, saved=b'123456j\n', hook=True, end=True):
        super().__init__(True)
        self.at_end = end            # start() scrolls the list to its end (the shelf is at the bottom) so the tiles are in view
        CUR[0] = self
        self.u.mem_write(0x97a330, struct.pack('<I', PSYMS['m1plus_scroll_event'] if hook else 0))   # the list gesture hook, as built (patch/scroll.c)
        self.build(pad=True)
        self.zv = self.alloc(0x80); self.u.mem_write(self.zv, bytes(0x80))   # a view: no vtable entries (the stock defaults)
        sv = self.sv
        self.shelf = self.widget(self.zv, 0, 0, pod_ui.SH_W, SH_H3, sv, emitter=True)   # the asset's: three rows; the payload sets the real height
        self.u.mem_write(self.shelf + 0x24, struct.pack('<H', 0x1))          # enabled, not visible, not sensitive: the asset's
        self.head = self.widget(self.zv, pod_ui.SH_HEAD_X, pod_ui.SH_HEAD_TOP, pod_ui.SH_HEAD_W, pod_ui.SH_HEAD_H, self.shelf)   # the header: visible, insensitive
        self.u.mem_write(self.head + 0x24, struct.pack('<H', 0x5))
        self.lab = [self.widget(self.zv, 0, 0, 10, 10, self.shelf) for _ in range(2)]
        for lab in self.lab: self.u.mem_write(lab + 0x24, struct.pack('<H', 0x1))
        self.kids(self.shelf, [self.head] + self.lab)
        self.kids(sv, self.rows + [self.shelf, self.pad])
        self.widgets.update({'pod_shelf': self.shelf, 'pod_sh_head': self.head, 'pod_sh_title': self.lab[0], 'pod_sh_sub': self.lab[1]})
        self.props[(sv, 'h')] = 430
        self.window = self.root
        self.load_image = 0
        self.bar_w = self.widget(self.zv, O['MB_X'], O['MB_Y'], O['MB_W'], O['MB_H'], self.root)   # the mini player bar's pill, a later sibling of the list: hidden in the asset
        self.u.mem_write(self.bar_w + 0x24, struct.pack('<H', 0x1))
        self.kids(self.root, [self.lv, self.bar_w])
        self.widgets['pod_minibar'] = self.bar_w
        self.fs[pulldown.SAVED] = saved
        if entries is not None: self.fs[RECENT] = pod_recent.dump(entries) if not isinstance(entries, bytes) else entries
        if setting is not None: self.fs[SHELF_SET] = setting
        self.placeholder()
        self.fixed = True
        self.arrange(); self.relayout()    # the menu as it opens
        if bar: self.bar_on()
        if start: self.start()

    # ---- the world
    def placeholder(self, rgb=(90, 90, 90)): self.images['p_default'] = (16, 16, bytes(rgb + (255,)) * 256)

    def cover(self, artist, album, rgb=(200, 40, 40), size=168):
        key = album_key(artist, album)
        path = art_file(key)
        self.present.add(path); self.files[path] = 4096
        self.images['file://' + path] = (size, size, bytes(rgb + (255,)) * (size * size))
        return key

    def start(self, win=None):
        self.calls = []
        self.call(PSYMS['recent_start'], a0=win or self.root, count=8000000)
        calls = list(self.calls)
        if self.at_end and self.shelf_up(): self.setword(self.sv + 0x84, max(0, self.vh() - 430))
        return calls

    def sync_props(self):
        """A shelf the stock widget_set_visible changed is read back from the struct (flags @0x24)."""
        return None

    def bar_on(self):
        """The mini player bar's spacer row shown (minibar.c mb_pad: visible, virtual_h + MB_PAD)."""
        self.call(pod.FUNCTIONS['widget_set_visible'][2], a0=self.pad, a1=1, a2=0, count=400000)
        self.setword(self.sv + 0x7c, self.vh() + MB_PAD)
        self.u.mem_write(self.bar_w + 0x24, struct.pack('<H', 0xd))

    def bar_off(self):
        self.call(pod.FUNCTIONS['widget_set_visible'][2], a0=self.pad, a1=0, a2=0, count=400000)
        self.u.mem_write(self.bar_w + 0x24, struct.pack('<H', 0x1))
        self.setword(self.sv + 0x7c, self.vh() - MB_PAD)

    def flags(self, w): return struct.unpack('<H', self.u.mem_read(w + 0x24, 2))[0]
    def is_shown(self, w): return self.flags(w) & 12 == 12
    def is_visible(self, w): return bool(self.flags(w) & 4)
    def shelf_up(self): return self.is_shown(self.shelf)
    def y_of(self, w): return self.s32(w + 4)

    def stack(self):
        """The scroll view's children in order: 'shelf', the rows by index, 'pad'."""
        arr = self.word(self.sv + 0x58); elms = self.word(arr + 8)
        return ['shelf' if c == self.shelf else 'pad' if c == self.pad else self.rows.index(c) for c in (self.word(elms + 4 * i) for i in range(self.word(arr)))]

    def paint_list(self, d=None):
        """The children scroll_view_on_paint_children paints (its hook if set, else the plain painter), by name."""
        c = self.alloc(0x40); self.u.mem_write(c, bytes(0x40))
        self.setword(c, self.s32(self.lv) + self.s32(self.sv) - self.s32(self.sv + 0x80))
        self.setword(c + 4, 30 + self.s32(self.lv + 4) + self.s32(self.sv + 4) - (self.yoff() if d is None else d))
        self.painted = []
        self.call(self.word(self.sv + 0xf4) or pulldown.PAINT_DEFAULT, a0=self.sv, a1=c, count=4000000)
        names = {v: k for k, v in self.widgets.items()}
        return [names.get(w, hex(w)) for w in self.painted]
    def row_ys(self): return {i: self.y_of(r) for i, r in enumerate(self.rows) if self.is_visible(r)}

    def first(self): return self.call(PSYMS['rc_first'], count=40000000)
    def tick(self): return self.call(PSYMS['rc_tick'], count=40000000)

    def decode_all(self, limit=10):
        """The one-shot, then ticks until the timer ends itself (it answers RET_OK): every tile has its cover. The ticks fired."""
        self.first()
        n = 1
        while self.tick() == O['RET_REPEAT'] and n < limit: n += 1
        return n + 1

    def centre(self, bmp):
        """The word of the middle pixel of a bitmap the payload made."""
        data, w, h = self.bitmaps[bmp]
        return struct.unpack_from('<I', bytes(self.u.mem_read(data, w * h * 4)), 4 * (h // 2 * w + w // 2))[0]

    def paint(self):
        e = self.alloc(0x40); self.u.mem_write(e, bytes(0x40)); self.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        self.blits.clear(); self.texts.clear(); self.measures.clear(); self.text_styles.clear()
        self.call(PSYMS['rc_on_paint'], a0=0, a1=e, count=40000000)
        return list(self.blits), list(self.texts)

    # ---- stock pointer events delivered to the handlers the payload bound
    def leaf(self, name, a0, a1, a2, a3, sp):
        if name == 'widget_invalidate_force': self.calls.append(('widget_invalidate_force', a0))
        return super().leaf(name, a0, a1, a2, a3, sp)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name == 'widget_get_prop_int':   # the scroll view's own numbers are in its struct
            a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
            prop = self.read_cstr(a1)
            if a0 == self.shelf and prop in ('y', 'h'):
                u.reg_write(UC_MIPS_REG_V0, self.word(self.shelf + {'y': 4, 'h': 0xc}[prop])); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if a0 == self.sv and prop in ('virtual_h', 'yoffset', 'h'):
                u.reg_write(UC_MIPS_REG_V0, self.word(self.sv + {'virtual_h': 0x7c, 'yoffset': 0x84, 'h': 0xc}[prop]))
                u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
        if name == 'widget_on' and u.reg_read(UC_MIPS_REG_A1) in self.on_fail:
            self.calls.append(('widget_on', u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1), u.reg_read(UC_MIPS_REG_A2), u.reg_read(UC_MIPS_REG_A3)))
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        super()._hook(u, address, size, _)

    on_fail = frozenset()

    def gesture(self, steps):
        self.fired = []; self.calls_all = []
        for s in steps:
            if s[0] == 'a': self.pointer('u', s[1], s[2], *s[3:], abort=True)    # the abort window_base sends when a dialog opens over a pressed window
            else: self.pointer(s[0], s[1], s[2], *s[3:])
        return self.calls_all

    def tap(self, x, y): return self.gesture([('d', x, y, 0), ('u', x, y, 60)])

    def opened(self):
        """The albums the stock album page was asked for: [(class, row)]."""
        return [(c[2], c[3]) for c in self.calls_all if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']

    # ---- hit tests with demo's own widget_find_target on the struct tree
    def target(self, x, y):
        w, path = self.root, ['window']
        names = {v: k for k, v in self.widgets.items()}
        while True:
            t = self.call(FIND_TARGET, a0=w, a1=x, a2=y, count=400000)
            if not t or self.flags(t) & 9 != 9: return path
            w = t; path.append(names.get(t, hex(t)))

    def sv_off(self): return self.yoff()


def utf8(s): return s.encode('latin-1').decode('utf-8')   # the model keeps the file's bytes as latin-1 characters


def cut(s, maxw=SH_COVER):
    """The text as the shelf shows it with the mocked canvas (8 px a char, 16 for the ellipsis): the longest prefix that fits with an ellipsis."""
    w = lambda t: sum(16 if ord(c) >= 0x2e80 or c == '…' else 8 for c in t)
    if w(s) <= maxw: return s
    k = max(k for k in range(len(s)) if w(s[:k] + '…') <= maxw)
    return s[:k] + '…'


def shown_texts(m):
    """The texts one paint draws, by tile: [(title, artist)], from the mocked canvas calls (tiles with no album draw none)."""
    _, texts = m.paint()
    by = {}
    for s, r in texts:
        by[(r[0], r[1])] = s
    out = []
    for i in range(SH_TILES):
        t = tuple(by[k] for k in ((tile_x(i), cell_y(i) + TITLE_OFF), (tile_x(i), cell_y(i) + SUB_OFF)) if k in by)
        if t: out.append(t)
    return out


def plain_machine():
    """A machine with no page: the recording code alone."""
    m = Machine()
    m.dirs.add('/mnt/data')
    return m


def covered(m, n=3, rgbs=((200, 40, 40), (40, 200, 90), (40, 90, 220), (200, 200, 40), (90, 40, 200), (40, 200, 200))):
    """The cache files of the first n albums, flat colours."""
    for i in range(n): m.cover(*ALBUMS[i][:2], rgb=rgbs[i])
    return m


LIB = [4, 0, 3, 1, 2, 5, 6]     # the stock album list (by title): the library's albums as indices into ALBUMS


def library(m, order=LIB, rows=None):
    """The stock album list loadLocalClassList leaves; {album index: its row} for order."""
    recs = rows if rows is not None else [(ALBUMS[i][1], ALBUMS[i][0], f'/mnt/mmc/{ALBUMS[i][0]}/{ALBUMS[i][1]}/1.flac') for i in order]
    m.showlist = [m.record(album=a, artist=r, path=p, rid=k + 1) for k, (a, r, p) in enumerate(recs)]
    return {order[k]: k for k in range(len(order))} if rows is None else {}


def cx(i): return tile_x(i) + SH_COVER // 2


def sy(c):
    """Shelf y -> window y: the list starts HOME_PAD down, the shelf is at the foot of the rows, the list is scrolled."""
    m_ = CUR[0]
    return O['HOME_PAD'] + m_.y_of(m_.shelf) - m_.yoff() + c


def file_and_layout_tests(ctx):
    """The constants, the asset, the file, recording, start and the ticks, the timer, the shelf with demo's own layouter, hit tests."""
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    menu_asset = os.path.join(raw, 'ui', 'm1plus_menu.bin')

    # ------------------------------------------------------------------ constants: patch/offsets.inc, tools/pod_ui.py and tools/pod_recent.py agree
    ui_names = ('SH_W', 'SH_TILES', 'SH_TOP', 'GRID_R', 'SH_BOTTOM', 'SH_HEAD_X', 'SH_HEAD_W', 'SH_HEAD_TOP', 'SH_HEAD_H', 'SH_HEAD_PX', 'SH_HEAD_GAP')
    expect(all(O[k] == getattr(pod_ui, k) for k in ui_names), f'patch/offsets.inc SH_* equal tools/pod_ui.py ({[k for k in ui_names if O[k] != getattr(pod_ui, k)]})')
    expect(all(getattr(pod_ui, k) == O[k] for k in ('GRID_COLS', 'GRID_COVER', 'GRID_GAP', 'GRID_MARGIN', 'GRID_ROW_GAP', 'GRID_TITLE_GAP', 'GRID_TITLE_H', 'GRID_SUB_H')),
           'tools/pod_ui.py reads the grid\'s geometry from offsets.inc: the shelf has the Albums grid\'s cells, not a copy of the numbers')
    expect((O['RC_MAX'], O['RC_STR'], O['RC_PATH'], O['RC_FILE_MAX']) == (pod_recent.MAX, pod_recent.STR, pod_recent.PATH, pod_recent.FILE_MAX) == (6, 96, 256, 3072),
           'the file model and the payload agree on the cap (6 albums), the name and path sizes and the file size')
    expect((GRID_COVER, GRID_GAP, GRID_MARGIN, GRID_COLS, GRID_TITLE_GAP, GRID_TITLE_H, GRID_SUB_H) == (144, 8, 12, 2, 4, 22, 20) and CELL == 190 and PITCH == 200,
           'the Albums grid\'s cell: 144 px cover, 4 px, the album line 22, the artist line 20 (190), rows 200 apart')
    expect(GRID_MARGIN + GRID_COLS * GRID_COVER + (GRID_COLS - 1) * GRID_GAP == 308 <= O['SH_W'] == O['PM_SV_W'] == 310 and SH_TILES == GRID_COLS * SH_ROWS == O['RC_MAX'] == 6,
           'two 144 px covers 8 px apart from x 12 end at x 308: inside the 310 px scroll view (the 10 px strip beside it holds its scroll bar), 12 px margin on the left; 2 x 3 cells = the six albums the file keeps')
    expect(SH_TOP == O['SH_HEAD_TOP'] + O['SH_HEAD_H'] + O['SH_HEAD_GAP'] == 44 and O['SH_BOTTOM'] == 0 and (SH_H1, SH_H2, SH_H3) == (234, 434, 634)
           and O['SH_HEAD_TOP'] + 3 == 20,
           'the shelf (below Settings): the header (a 22 px line box at 17, its ink 20..36: 20 px of air above), 5 px more, the first row at 44, nothing below the artist line: 234 px for one row, 434 for two, 634 for three (the asset\'s)')
    expect(O['SH_HEAD_PX'] == 20 and O['SH_HEAD_PX'] > pod_ui.GRID_ARTIST_PX and O['SH_HEAD_H'] >= O['SH_HEAD_PX'] and O['SH_HEAD_X'] + 2 == GRID_MARGIN
           and O['SH_HEAD_X'] + O['SH_HEAD_W'] == O['SH_W'] and O['SH_HEAD_W'] - 2 * 2 == 296,
           'the header is 20 px, its text (the label insets it 2 px) starts at the covers\' left edge, 12, and has 296 px up to the edge of the list')
    expect((pod_ui.SH_TITLE_PX, pod_ui.SH_SUB_PX) == (18, 15) and GRID_TITLE_H >= 18 and GRID_SUB_H >= 15, 'the album line is the grid\'s 18 px and the artist line its 15 px, in the grid\'s boxes')
    expect(SH_H2 + 7 * ROW_H + MB_PAD > 450 - 2 * O['HOME_PAD'] and O['GRID_R'] == 8 and O['GRID_R'] * 2 < GRID_COVER,
           'the covers\' corners are 8 px (the Albums grid\'s are square; Now Playing\'s are 12 px on 264, the mini bar\'s 5 px on 36)')
    expect(O['RC_FIRST_MS'] > 0 and O['RC_TICK_MS'] > 0 and O['RC_TAP_PX'] == O['SC_DRAG_PX'] == 10,
           'a one-shot before the first decode, a tick per cover, and a tap is within the scroll view\'s own drag threshold (10 px)')

    # ------------------------------------------------------------------ the asset
    ui = awtk_ui.parse(open(menu_asset, 'rb').read())
    sv_n = ui.find('pod_scrollview')
    kids = [c.name for c in sv_n.children]
    expect(kids[-3:] == ['pod_daily', 'pod_shelf', 'pod_pad'] and kids[:-3] == [f'pod_row{i}' for i in range(len(pod_pages.MENU.rows))],
           f'the rows, then the Daily Mix section, the shelf (below the last row), the spacer is last ({kids[:3]}..{kids[-3:]})')
    sh = sv_n.find('pod_shelf')
    expect(sh.type == 'view' and (sh.x, sh.y, sh.w, sh.h) == (0, 0, O['SH_W'], SH_H3) and sh.get('visible') == 'false' and sh.get('sensitive') == 'false'
           and sh.get('style:normal:bg_color') == '#000000', 'pod_shelf is a 310 x 182 view after the rows, hidden and insensitive in the asset, black')
    head, st_t, st_s = sh.find('pod_sh_head'), sh.find('pod_sh_title'), sh.find('pod_sh_sub')
    expect([c.name for c in sh.children] == ['pod_sh_head', 'pod_sh_title', 'pod_sh_sub'] and all(c.type == 'label' and c.get('visible') == 'false' and c.get('sensitive') == 'false' for c in (st_t, st_s)),
           'its children are the header and the two hidden, insensitive labels that carry the tiles\' text styles')
    expect(head.type == 'hscroll_label' and (head.x, head.y, head.w, head.h) == (pod_ui.SH_HEAD_X, pod_ui.SH_HEAD_TOP, pod_ui.SH_HEAD_W, pod_ui.SH_HEAD_H)
           and head.get('tr_text') == 'Recently Played' and head.get('text') is None and head.get('sensitive') == 'false' and head.get('visible') is None
           and head.get('ellipses') == 'true' and head.get('only_parent_focus') == 'true',
           'the header is a visible, insensitive hscroll_label with the translation key "Recently Played" (the menu item\'s, so the 13 languages are there), that never scrolls and ends in an ellipsis')
    expect(all(head.get(f'style:{st}:font_size') == '20' and head.get(f'style:{st}:text_color') == '#FFFFFF' and head.get(f'style:{st}:text_align_h') == 'left'
               and head.get(f'style:{st}:text_align_v') == 'middle' for st in ('normal', 'disable', 'focused')), 'white, 20 px, left aligned, in the states a label has')
    tt = asset_tree(menu_asset)
    expect(node(tt, 'pod_sh_head').flags & F_SENSITIVE == 0 and node(tt, 'pod_sh_head').flags & F_VISIBLE, 'asset_tree: the header is visible and insensitive (inside the hidden shelf)')
    # the header in all 13 languages, at 20 px in the font the device ships: the room is the label less the 2 px margins of an hscroll_label
    from awtk_text import Ttf, StbText
    fnt = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    widths = {loc: StbText(fnt, pod_ui.SH_HEAD_PX).layout(pod_i18n.TEXT['Recently Played'][loc])[1] for loc in pod_i18n.LOCALES}
    room = pod_ui.SH_HEAD_W - 4
    widest = max(widths, key=widths.get)
    print(f'  shelf header at {pod_ui.SH_HEAD_PX} px: widest language {widest} ({pod_i18n.TEXT["Recently Played"][widest]}) {widths[widest]} px of {room}; ' + ', '.join(f'{l} {w}' for l, w in sorted(widths.items(), key=lambda kv: -kv[1])[:4]))
    expect(len(widths) == 13 and all(0 < w <= room for w in widths.values()), f'the translated header fits the label in all 13 languages without needing the ellipsis (widest {widest}: {widths[widest]} of {room} px)')
    expect(st_t.get('style:normal:font_size') == '18' and st_t.get('style:normal:text_color') == '#FFFFFF' and st_s.get('style:normal:font_size') == '15'
           and st_s.get('style:normal:text_color') == '#AAAAAA' and st_t.get('style:normal:text_align_h') == 'left' and st_s.get('style:normal:text_align_v') == 'middle',
           'the album style is the grid\'s 18 px white, the artist style its 15 px #AAAAAA, both left aligned')
    others = [p.key for p in pod_pages.PAGES if p is not pod_pages.MENU
              and any(w.name in pod_ui.SH_NAMES for w in awtk_ui.parse(open(os.path.join(raw, 'ui', p.key + '.bin'), 'rb').read()).walk())]
    expect(not others, f'only the menu page carries the shelf ({others})')
    tree = asset_tree(menu_asset)
    expect(node(tree, 'pod_shelf').flags & (F_VISIBLE | F_SENSITIVE) == 0 and node(tree, 'pod_shelf').flags & F_ENABLE, 'asset_tree reads the shelf hidden and insensitive')

    # ------------------------------------------------------------------ the file: the model
    e3 = ents(3)
    data = pod_recent.dump(e3)
    expect(data.startswith(b'M1R2\n') and data.count(b'\n') == 4 and pod_recent.parse(data) == e3, 'the model: dump and parse are inverses')
    bad = {'no file content': b'', 'only a newline': b'\n', 'the old magic M1R1 (no compatibility)': b'M1R1\n' + data[5:], 'wrong magic': b'M1R3\n' + data[5:], 'no magic': data[5:], 'magic without newline': b'M1R2',
           'no final newline': data[:-1], 'a 7th line': pod_recent.dump(ents(7)), 'a duplicate key': pod_recent.dump([e3[0], e3[0]]),
           'key zero': b'M1R2\n00000000\tAlbum\tArtist\t/a\n', 'upper case hex': b'M1R2\n0000ABCD\tAlbum\tArtist\t/a\n', 'a short key': b'M1R2\n0000abc\tAlbum\tArtist\t/a\n',
           'a non hex key': b'M1R2\n0000abcg\tAlbum\tArtist\t/a\n', 'an empty album': b'M1R2\n0000abcd\t0000abcd\t0\t\tArtist\t/a\n', 'three fields': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\n',
           'five fields': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/a\t/b\n', 'a control byte': b'M1R2\n0000abcd\t0000abcd\t0\tAl\x01bum\tArtist\t/a\n', 'a carriage return': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/a\r\n',
           'DEL': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/a\x7f\n', 'a NUL': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArt\x00ist\t/a\n', 'a blank line': data + b'\n',
           'an album of 96 bytes': b'M1R2\n0000abcd\t0000abcd\t0\t' + b'a' * 96 + b'\tArtist\t/a\n', 'a path of 256 bytes': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/' + b'p' * 255 + b'\n',
           'more than the file size': b'M1R2\n' + b'0000abcd\t0000abcd\t0\tAlbum\tArtist\t/a\n' * 1 + b'#' * 4000, 'the key without fields': b'M1R2\n0000abcd\n',
           'a space before the key': b'M1R2\n 000abcd\tAlbum\tArtist\t/a\n', 'a tab inside the path': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/a\tb\n'}
    good = {'only the magic': b'M1R2\n', 'one album': pod_recent.dump(e3[:1]), 'three albums': data, 'six albums': pod_recent.dump(ents(6)),
            'an empty artist and path': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\t\t\n', 'an album of 95 bytes': b'M1R2\n0000abcd\t0000abcd\t0\t' + b'a' * 95 + b'\tArtist\t/a\n',
            'a path of 255 bytes': b'M1R2\n0000abcd\t0000abcd\t0\tAlbum\tArtist\t/' + b'p' * 254 + b'\n', 'UTF-8 names': pod_recent.dump([entry('Björk', 'Homogénic')])}
    expect(all(pod_recent.parse(v) == [] for v in bad.values()), f'the model refuses every malformed file ({[k for k, v in bad.items() if pod_recent.parse(v)]})')
    expect(all(len(pod_recent.parse(v)) == v.count(b'\n') - 1 for v in good.values()), f'and accepts the valid ones ({[k for k, v in good.items() if len(pod_recent.parse(v)) != v.count(chr(10).encode()) - 1]})')

    # ------------------------------------------------------------------ the payload reads the same: every file, shown or not
    differ = []
    for name, blob in list(good.items()) + list(bad.items()):
        want = pod_recent.parse(blob)
        m = ST(blob)
        got = shown_texts(m) if m.shelf_up() else []
        exp = [tuple(cut(utf8(s)) for s in (a, r) if s) for _, _, _, a, r, _ in want[:SH_TILES]]
        if not (m.shelf_up() == bool(want) and got == exp): differ.append(f'"{name}": {got} vs {exp}')
    expect(not differ, f'every one of the {len(good) + len(bad)} files: the shelf shows the albums the model reads, or no shelf when it reads none {differ}')
    m = ST(None)
    expect(not m.shelf_up(), 'no file at all: no shelf')
    m = ST(e3, start=False); m.card_mounted = False; m.start()
    expect(not m.shelf_up() and not [c for c in m.calls if c[0] == 'open' and c[1] == RECENT], 'no card: the file under the mount point is not read, no shelf')
    m = ST(e3); m.card_mounted = False; m.fire(EVT_FG); m.relayout()
    expect(not m.shelf_up(), 'the card taken out while the menu is open: the next to-foreground empties the shelf')
    m.card_mounted = True; m.fs[RECENT] = pod_recent.dump(ents(2)); m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up(), 'another card in: its list is shown')
    m2 = ST(e3, start=False); m2.fail.add(('open', RECENT)); m2.start()
    expect(not m2.shelf_up(), 'a file that cannot be opened: no shelf')

    # ------------------------------------------------------------------ recording: order, de-duplication, the cap, no write when nothing changed
    m = plain_machine()
    def track(album, artist, path=None, title='Song'):
        return m.record(album=album, artist=artist, path=path or f'/mnt/mmc/{artist}/{album}/1.flac', title=title, name='1.flac')
    def note(t):
        r = m.call(PSYMS['recent_note'], a0=t, count=3000000); return r
    tracks = [track(a, r) for r, a in ALBUMS]
    def writes(): return [c for c in m.calls if c[0] == 'rename']
    expect(note(tracks[0]) == 1 and m.fs.get(RECENT) == pod_recent.dump([entry(*ALBUMS[0])]), 'the first album is recorded: the file holds it')
    expect(writes() == [('rename', RECENT_TMP, RECENT)] and ('fsync', RECENT_TMP) in m.calls, 'written atomically (temp file, fsync, rename onto the file)')
    m.calls = []; r = note(tracks[0])
    expect(r == 0 and m.calls == [], f'the same album again: nothing changes, nothing is opened, read or written ({m.calls})')
    m.calls = []; r = note(track(ALBUMS[0][1], ALBUMS[0][0], path='/mnt/mmc/other/2.flac', title='Another song'))
    expect(r == 0 and m.calls == [] and m.fs[RECENT] == pod_recent.dump([entry(*ALBUMS[0])]), 'another track of the same album: still nothing')
    expect(note(tracks[1]) == 1 and pod_recent.parse(m.fs[RECENT]) == [entry(*ALBUMS[1]), entry(*ALBUMS[0])], 'a second album goes in front of the first')
    expect(note(tracks[0]) == 1 and [e[0] for e in pod_recent.parse(m.fs[RECENT])] == [entry(*ALBUMS[0])[0], entry(*ALBUMS[1])[0]],
           'an album already in the list moves to the front, it is not added twice')
    for i in (2, 3, 4, 5): note(tracks[i])
    want = [entry(*ALBUMS[i]) for i in (5, 4, 3, 2, 0, 1)]
    expect(pod_recent.parse(m.fs[RECENT]) == want, 'six albums are kept, the most recent first')
    note(tracks[6])
    expect([e[0] for e in pod_recent.parse(m.fs[RECENT])] == [entry(*ALBUMS[i])[0] for i in (6, 5, 4, 3, 2, 0)], 'a seventh pushes the oldest out: the list stays at six')
    note(tracks[3])
    expect([e[0] for e in pod_recent.parse(m.fs[RECENT])] == [entry(*ALBUMS[i])[0] for i in (3, 6, 5, 4, 2, 0)] and len(pod_recent.parse(m.fs[RECENT])) == 6,
           'an album from the middle of a full list moves to the front, nothing falls off')
    m.calls = []; before = m.fs[RECENT]
    expect(note(tracks[3]) == 0 and m.calls == [] and m.fs[RECENT] == before, 'and the most recent again changes nothing')
    nowrites = len([c for c in m.calls if c[0] in ('open', 'write', 'rename', 'fsync')])
    expect(nowrites == 0, 'no file call')
    untagged = track('', 'Artist')
    m.calls = []
    expect(note(untagged) == 0 and m.calls == [] and m.fs[RECENT] == before, 'an album with an empty album tag is not recorded')
    expect(m.call(PSYMS['recent_note'], a0=0, count=100000) == 0 and m.calls == [], 'no track (nothing is playing): nothing')
    # the stored fields: control bytes, cut names, paths
    m = plain_machine()
    t = m.record(album='Tab\tAlbum\nLine', artist='Arti\x01st', path='/mnt/mmc/a\tb/1.flac', title='T', name='1.flac')
    note(t)
    got = pod_recent.parse(m.fs[RECENT])
    expect(got == [(pod_recent.identity('Tab\tAlbum\nLine'), fnv(fnv(O['FNV_SEED'], 'Arti\x01st'), 'Tab\tAlbum\nLine') or 1, 0, 'Tab Album Line', 'Arti st', '/mnt/mmc/a b/1.flac')],
           f'control bytes in the tags become spaces, so the file stays valid and the key is still the album\'s ({got})')
    long_a = 'é' * 60                                    # 120 bytes: must be cut at 95 without splitting a sequence
    m = plain_machine(); t = m.record(album=long_a, artist='X', path='/p/' + 'ü' * 200, title='T', name='1.flac'); note(t)
    got = pod_recent.parse(m.fs[RECENT])
    want_a = pod_recent.field(long_a.encode('utf-8'), pod_recent.STR).decode('latin-1')
    want_p = pod_recent.field(('/p/' + 'ü' * 200).encode('utf-8'), pod_recent.PATH).decode('latin-1')
    expect(len(got) == 1 and got[0][3] == want_a and got[0][5] == want_p and len(want_a.encode('latin-1')) == 94 and utf8(want_a) == 'é' * 47,
           f'a long name is cut at 94 bytes (47 whole characters, never half of one), a long path at 255 ({len(got[0][3]) if got else None})')
    # an existing file is the start; a malformed one is replaced
    m = plain_machine(); m.fs[RECENT] = pod_recent.dump(e3); note(track('Dummy', 'Portishead'))
    expect([e[0] for e in pod_recent.parse(m.fs[RECENT])] == [entry('Portishead', 'Dummy')[0]] + [e[0] for e in e3], 'the first note reads the file: the new album joins the albums already in it')
    m = plain_machine(); m.fs[RECENT] = b'M1R2\ngarbage'; note(track('Dummy', 'Portishead'))
    expect(pod_recent.parse(m.fs[RECENT]) == [entry('Portishead', 'Dummy')], 'a malformed file reads as empty: the list starts again with this album')
    m = plain_machine(); m.fs[RECENT] = pod_recent.dump(e3); note(track(e3[0][3], e3[0][4]))
    expect(m.fs[RECENT] == pod_recent.dump(e3), 'the most recent album of a file is not written again')
    # a failed write: this entry is lost (the next change starts from the card), the file is as it was
    m = plain_machine(); m.fail.add(('write', RECENT_TMP))
    r = m.call(PSYMS['recent_note'], a0=m.record(album='A', artist='B', path='/p', title='t', name='n'), count=3000000)
    expect(r == 1 and RECENT not in m.fs and RECENT_TMP not in m.fs, 'a write that fails is no change on the card (and the temp file is gone)')
    m.fail.clear()
    m.call(PSYMS['recent_note'], a0=m.record(album='C', artist='D', path='/q', title='t', name='n'), count=3000000)
    expect([e[3] for e in pod_recent.parse(m.fs[RECENT])] == ['C'], 'the next album change writes the card\'s list with the new album')
    # the list lives on the card: every write is under CARD_DIR, nothing without a card, a swapped card's list is the new card's
    expect(RECENT.startswith(CARD) and RECENT_TMP.startswith(CARD) and ('mkdir', CARD) in m.calls, 'the file and its temp file are in the card folder, made first')
    m = plain_machine()
    r = m.call(PSYMS['recent_note'], a0=m.record(album='A', artist='B', path='http://nd.example:4533/rest/stream.view?u=x&t=y&s=z', title='t', name='n'), count=3000000)
    expect(r == 0 and RECENT not in m.fs, 'a streamed server track is never recorded (its path holds the credentials)')
    m = plain_machine(); m.card_mounted = False
    r = m.call(PSYMS['recent_note'], a0=m.record(album='A', artist='B', path='/p', title='t', name='n'), count=3000000)
    expect(r == 0 and not [c for c in m.calls if c[0] in ('open', 'write', 'rename', 'mkdir', 'fsync', 'unlink')] and not m.fs and CARD not in m.dirs, 'no card: nothing is recorded, opened or written')
    m = plain_machine(); m.fs['/mnt/data/m1plus/recently-played'] = pod_recent.dump(e3)
    m.call(PSYMS['recent_note'], a0=m.record(album='Dummy', artist='Portishead', path='/p', title='t', name='n'), count=3000000)
    expect(RECENT in m.fs and m.fs['/mnt/data/m1plus/recently-played'] == pod_recent.dump(e3) and len(pod_recent.parse(m.fs[RECENT])) == 1, 'the old flash file is neither read nor touched')
    m = plain_machine(); m.fs[RECENT] = pod_recent.dump(e3)
    t1 = m.record(album='Dummy', artist='Portishead', path='/p', title='t', name='n')
    m.call(PSYMS['recent_note'], a0=t1, count=3000000)
    other = [entry('Radiohead', 'Kid A')]
    m.fs[RECENT] = pod_recent.dump(other)            # the card in the slot is swapped for another one: it holds its own list
    m.call(PSYMS['recent_note'], a0=m.record(album='Mezzanine', artist='Massive Attack', path='/q', title='t', name='n'), count=3000000)
    got = [e[3] for e in pod_recent.parse(m.fs[RECENT])]
    expect(got == ['Mezzanine', 'Kid A'], f'a card swap: the new album joins the new card\'s list, nothing of the old card is written onto it ({got})')

    # ------------------------------------------------------------------ start: nothing decoded, one short one-shot, the shelf up with its texts
    m = covered(ST(e3, start=False))
    calls = m.start()
    wl = [c[1] for c in calls if c[0] == 'widget_lookup' and not c[1].startswith('pod_row')]
    expect(wl[:4] == ['pod_shelf', 'pod_scrollview', 'pod_sh_title', 'pod_sh_sub'], f'start looks up the shelf, the list and the two style labels ({wl[:4]})')
    ons = [(c[1], c[2], c[3]) for c in calls if c[0] == 'widget_on']
    want = [(m.root, EVT_DESTROY, PSYMS['rc_on_destroy']), (m.root, EVT_BG, PSYMS['rc_on_background']), (m.root, EVT_FG, PSYMS['rc_on_foreground']),
            (m.shelf, EVT_AFTER_PAINT, PSYMS['rc_on_paint']), (m.shelf, EVT_DOWN, PSYMS['rc_on_down']), (m.shelf, EVT_UP, PSYMS['rc_on_up']), (m.shelf, EVT_ABORT, PSYMS['rc_on_abort']), (m.sv, O['EVT_SCROLL'], PSYMS['rc_on_scroll'])]
    expect(ons == want, f'window destroy, to-background, to-foreground; the shelf\'s own paint and its pointer down, up and abort ({len(ons)} handlers)')
    expect(m.timers == [(PSYMS['rc_first'], O['RC_FIRST_MS'])] and 0 < O['RC_FIRST_MS'] <= 250, f'one short one-shot, nothing else is armed at start ({m.timers})')
    expect(not [c for c in calls if c[0] in ('bitmap_create_ex', 'widget_load_image', 'fopen', 'loadLocalClassList', 'loadAlbumList', 'canvas_draw_image', 'timer_remove')],
           'start decodes nothing, allocates no bitmap, loads no album list')
    expect(m.shelf_up() and m.row_ys()[1] == 0 and m.y_of(m.shelf) == 8 * ROW_H and m.vh() == SH_H + 8 * ROW_H, f'the shelf is up from the first paint, below the rows, which stay where they were ({m.row_ys()[1]}, shelf y {m.y_of(m.shelf)}, virtual_h {m.vh()})')
    blits, texts = m.paint()
    expect(blits == [] and len(texts) == 6, 'the first paint draws the texts and no cover (a tile has none until a tick has made it)')
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'fopen')], 'paint decodes and creates nothing')
    rects = sorted(t[1] for t in texts)
    expect(rects == sorted([(tile_x(i), cell_y(i) + TITLE_OFF, GRID_COVER, GRID_TITLE_H) for i in range(3)] + [(tile_x(i), cell_y(i) + SUB_OFF, GRID_COVER, GRID_SUB_H) for i in range(3)]),
           'the album and the artist of each cell in 144 x 22 and 144 x 20 boxes under its cover (the grid\'s, rows 200 apart)')
    expect(m.text_styles.count('pod_sh_title') == 3 and m.text_styles.count('pod_sh_sub') == 3 and m.text_styles[:3] == ['pod_sh_title'] * 3,
           'one text style at a time: the three albums in the album style, then the three artists in the artist style')

    # the one-shot and the ticks: one cover each, never in paint
    r = m.first()
    expect(m.timers[-1:] == [(PSYMS['rc_tick'], O['RC_TICK_MS'])] and r == 0, 'the one-shot arms the repeating tick (and ends itself)')
    k = album_key(*ALBUMS[0])
    expect(m.names().count('bitmap_create_ex') == 1 and m.names().count('widget_load_image') == 1 and ('widget_load_image', 'file://' + art_file(k)) in m.calls,
           'and decodes ONE cover: the first album\'s Cover Flow cache file')
    expect(('bitmap_create_ex', SH_COVER, SH_COVER) in m.calls and ('widget_invalidate_force', m.shelf) in m.calls, 'into a 144 x 144 bitmap, and the shelf is repainted')
    r = m.tick()
    expect(r == O['RET_REPEAT'] and m.names().count('widget_load_image') == 1 and m.names().count('bitmap_create_ex') == 1, 'a tick: the second cover only, the timer stays')
    r = m.tick()
    expect(r == 0 and m.names().count('widget_load_image') == 1, 'the third cover; the timer ends itself with it (RET_OK)')
    r = m.tick()
    expect(r == 0 and not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex')], 'a tick that still arrives has nothing to do')
    expect(len(m.bitmaps) == 3 and all((w, h) == (SH_COVER, SH_COVER) for _, w, h in m.bitmaps.values()) and 4 * SH_COVER * SH_COVER * 4 < 340000,
           f'three 144 x 144 RGBA bitmaps ({3 * SH_COVER * SH_COVER * 4} bytes; {4 * SH_COVER * SH_COVER * 4} for four) are all the memory the tiles use')
    blits, texts = m.paint()
    bm = list(m.bitmaps)
    expect(blits == [(bm[i], (0, 0, SH_COVER, SH_COVER), (tile_x(i), cell_y(i), SH_COVER, SH_COVER)) for i in range(3)], f'paint draws the three resident covers at (12, 44), (164, 44), (12, 244) ({[b[2] for b in blits]})')
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'fopen')], 'and still decodes nothing')
    def px(i):
        data, w, h = m.bitmaps[bm[i]]
        return bytes(m.u.mem_read(data, w * h * 4)), w
    rgbs = ((200, 40, 40), (40, 200, 90), (40, 90, 220))
    for i in range(3):
        p, w = px(i)
        c = struct.unpack_from('<I', p, 4 * (w // 2 * w + w // 2))[0]
        expect(minibar.rgb_of(c) == rgbs[i] and c >> 24 == 255, f'tile {i}: the album\'s cache picture, box-filtered from 168 to 144 px ({minibar.rgb_of(c)})')
    p, w = px(0)
    word = lambda x, y: struct.unpack_from('<I', p, 4 * (y * w + x))[0]
    cov = minibar.corner_coverage(SH_R)
    want = [tuple(ch * (255 - c) // 255 for ch in rgbs[0]) for c in cov]   # each channel kept by the coverage inside the arc: blended into black
    got = [minibar.rgb_of(word(x, y)) for y in range(SH_R) for x in range(SH_R)]
    expect(got == want and got[0] == (0, 0, 0) and got[-1] == rgbs[0] and all(word(x, y) >> 24 == 255 for y in range(SH_R) for x in range(SH_R)),
           'the corner arc is anti-aliased (radius GRID_R = 8), blended into the black behind it; every pixel stays opaque')
    mirrored = all(word(x, y) == word(w - 1 - x, w - 1 - y) == word(w - 1 - x, y) == word(x, w - 1 - y) for y in range(SH_R) for x in range(SH_R))
    corners = [minibar.rgb_of(word(x, y)) for x, y in ((0, 0), (w - 1, 0), (0, w - 1), (w - 1, w - 1))]
    mids = [minibar.rgb_of(word(x, y)) for x, y in ((w // 2, 0), (0, w // 2), (w - 1, w // 2), (w // 2, w - 1))]
    expect(mirrored and corners == [(0, 0, 0)] * 4 and mids == [rgbs[0]] * 4, 'all four corners are rounded the same, the edges between them keep the cover')
    expect(struct.unpack('<H', m.u.mem_read(bm[0] + O['BITMAP_FLAGS'], 2))[0] & 1, 'the shelf\'s tiles are flagged opaque (a plain blit, nothing blended per frame)')

    # the placeholder: no cache file, the "no art" marker, a picture that does not decode, no placeholder image
    def one_tile(prep, entries=None):
        m = ST(entries or e3[:1], start=False)
        m.cover(*ALBUMS[0][:2]); prep(m); m.start(); m.decode_all()
        data, w, h = next(iter(m.bitmaps.values()))
        p = bytes(m.u.mem_read(data, w * h * 4))
        return m, struct.unpack_from('<I', p, 4 * (w // 2 * w + w // 2))[0]
    def no_file(m): m.present.discard(art_file(album_key(*ALBUMS[0][:2]))); m.files.pop(art_file(album_key(*ALBUMS[0][:2])), None)
    m, c = one_tile(no_file)
    expect(minibar.rgb_of(c) == (90, 90, 90) and 'p_default' in m.loads and not [u_ for u_ in m.loads if u_.startswith('file://')], 'no cache file: the stock placeholder disc')
    def marker(m): m.files[art_file(album_key(*ALBUMS[0][:2]))] = 0
    m, c = one_tile(marker)
    expect(minibar.rgb_of(c) == (90, 90, 90) and not [u_ for u_ in m.loads if u_.startswith('file://')], 'the empty "no art" marker: the placeholder, the file is not opened as a picture')
    def undecodable(m): m.images.pop('file://' + art_file(album_key(*ALBUMS[0][:2])))
    m, c = one_tile(undecodable)
    expect(minibar.rgb_of(c) == (90, 90, 90), 'a picture that does not decode: the placeholder')
    def nothing(m): no_file(m); m.images.pop('p_default')
    m, c = one_tile(nothing)
    expect(c == GREY, f'no placeholder image either: flat grey ({c:#x})')
    m, c = one_tile(no_file)
    data, w, h = next(iter(m.bitmaps.values())); p = bytes(m.u.mem_read(data, w * h * 4))
    expect(struct.unpack_from('<I', p, 0)[0] == 0xff000000, 'and the placeholder\'s corners are rounded too (blended into black, opaque)')
    # a cache file that appears later (the Albums page builds the covers in the background): the placeholder tile is redone when the menu is in front again
    m = ST(e3[:1], start=False); m.start(); m.decode_all()
    expect(minibar.rgb_of(m.centre(next(iter(m.bitmaps)))) == (90, 90, 90), 'a tile starts as the placeholder when its album has no cache file yet')
    m.cover(*ALBUMS[0][:2], rgb=(10, 220, 10)); m.timers = []; m.calls = []
    m.fire(EVT_FG)
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], 'back in front the tile whose cover exists now is queued again')
    m.tick()
    expect(minibar.rgb_of(m.centre(list(m.bitmaps)[-1])) == (10, 220, 10) and len(m.bitmaps) == 2, 'and made again into a bitmap of its own (the shared disc stays for the tiles that still need it)')

    # ------------------------------------------------------------------ the timer's lifecycle
    m = covered(ST(e3)); m.first()
    m.timers = []; m.calls = []
    m.fire(EVT_BG)
    expect(('timer_remove', 0x777) in m.calls, 'to-background removes the timer')
    r = m.tick()
    expect(r == 0 and m.names() == [], 'a tick that still arrives ends itself and does nothing')
    m.calls = []; m.fire(EVT_BG)
    expect(m.names().count('timer_remove') == 0, 'a second to-background has nothing to remove')
    m.timers = []; m.calls = []
    m.fire(EVT_FG)
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])] and 'widget_load_image' not in m.names(), 'to-foreground reads the list again and arms the tick for the covers still to make (nothing is decoded in the event)')
    m.timers = []; m.fire(EVT_FG)
    expect(not m.timers, 'and not twice')
    m.tick(); m.tick()
    expect(len(m.bitmaps) == 3 and m.names().count('timer_remove') == 0, 'the remaining covers are made, the timer ends itself')
    m = covered(ST(e3)); m.fire(EVT_BG); m.timers = []; m.fire(EVT_FG)
    expect(m.timers == [(PSYMS['rc_first'], O['RC_FIRST_MS'])], 'a menu that was sent back before its one-shot ran gets the one-shot again, not a decode')
    m = covered(ST(e3)); m.fire(EVT_BG); m.timers = []; m.first()
    expect(not m.timers and 'widget_load_image' not in m.names(), 'a one-shot that fires after the window went to the back arms and decodes nothing')
    # destroy
    m = covered(ST(e3)); m.first()
    bmp = list(m.bitmaps)
    m.calls = []; m.call(PSYMS['rc_on_destroy'], a0=m.root + 0x100, a1=0)
    expect(not m.calls, 'another window\'s destroy is ignored')
    m.call(PSYMS['rc_on_destroy'], a0=m.root, a1=0)
    expect(('timer_remove', 0x777) in m.calls and [c for c in m.calls if c[0] == 'bitmap_destroy'] == [('bitmap_destroy', b) for b in bmp], 'destroy removes the timer and frees the covers')
    m.tick(); a = m.names(); m.first(); a += m.names()
    expect(a == [], f'late callbacks do nothing ({a})')
    expect(m.paint() == ([], []), 'no paint after destroy')
    nt = len(m.timers)
    m.call(PSYMS['rc_on_background'], a0=m.root, a1=0); a = m.names(); m.call(PSYMS['rc_on_foreground'], a0=m.root, a1=0)
    expect(a + m.names() == [] and len(m.timers) == nt, 'and the window events of a finished page are ignored')
    for fn in ('rc_on_down', 'rc_on_up', 'rc_on_abort'):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.call(PSYMS[fn], a0=0, a1=e)
        expect(m.names() == [], f'{fn} after the page is gone does nothing')
    # a second window before the first one's destroy: the old one's timer goes
    m = covered(ST(e3)); m.first(); m.calls = []; m.start(win=m.root + 0x100)
    expect(('timer_remove', 0x777) in m.calls and m.timers[-1:] == [(PSYMS['rc_first'], O['RC_FIRST_MS'])], 'a window started over a live one replaces the old state and timer')
    m.calls = []; m.call(PSYMS['rc_on_destroy'], a0=m.root, a1=0)
    expect(not m.calls, 'the earlier window\'s late destroy leaves the new one alone')

    # ------------------------------------------------------------------ the shelf below the rows, with demo's own layouter
    def layout_errors(m, shown, bar, shelf=True, na=3, extras=True):
        """What is wrong with the page ([]: nothing): the shown rows in order from y 0, virtual_h, the children stacked the shown rows,
        the shelf, the hidden rows, the spacer last, the shelf right below the last shown row, the spacer row after the shelf."""
        want = shown + ([18] if extras else []) + [EX]   # Settings (18) only when the saved list shows it; Extras always, last
        n, errs = len(want), []
        vh = n * ROW_H + (shh(na) if shelf else 0) + (MB_PAD if bar else 0)
        if not (m.order() == want and m.row_ys() == {i: p * ROW_H for p, i in enumerate(want)} and m.vh() == vh):
            errs.append(f'rows {m.order()}, virtual_h {m.vh()} (want {want} from y 0, {vh})')
        st = m.stack()
        if not (st[:n] == want and st[n] == 'shelf' and st[-1] == 'pad' and sorted(st[n + 1:-1]) == [i for i in range(EX + 1) if i not in want]):
            errs.append(f'stacked {st}')
        if m.y_of(m.shelf) != n * ROW_H: errs.append(f'the shelf at y {m.y_of(m.shelf)}')
        if bar and shelf and not (m.y_of(m.pad) == n * ROW_H + shh(na) and m.is_visible(m.pad)): errs.append(f'the spacer at y {m.y_of(m.pad)}')
        return errs
    # the saved lists: the default, none, a reordered one, the same without Settings (Extras follows the items, the shelf Extras);
    # the shelf's own heights for 1 to 6 albums are the grid's tests below
    for saved, shown, xs in ((b'123456j\n', [1, 2, 3, 4, 5, 6], True), (b'j\n', [], True), (b'6502j\n', [6, 5, 0, 2], True), (b'6502\n', [6, 5, 0, 2], False)):
        for bar in (False, True):
            for na in (0, 1, 6):
                m = ST(ents(na) if na else None, bar=bar, saved=saved, end=False)
                up, errs = na > 0, []
                if m.shelf_up() != up or m.is_visible(m.shelf) != up or (not up and m.flags(m.shelf) & 12): errs.append(f'the shelf up {m.shelf_up()}, flags {m.flags(m.shelf):#x}')
                errs += layout_errors(m, shown, bar, up, na, xs)
                if up:   # the stock layouter again and again, the menu's own arrangement (to-foreground), a pull-down snapshot's relayout
                    y0, vh0 = m.row_ys(), m.vh()
                    m.relayout(); m.mark(); m.relayout(); m.arrange(); m.relayout(); m.mark(); m.relayout()
                    if not (m.row_ys() == y0 and m.vh() == vh0 and m.yoff() == 0): errs.append(f'moved by the relayouts: virtual_h {m.vh()}, offset {m.yoff()}')
                    errs += [f'after the relayouts: {e}' for e in layout_errors(m, shown, bar, True, na, xs)]
                expect(not errs, f'saved {saved!r}, {"bar" if bar else "no bar"}, {na} album(s): the shelf {"up below the shown rows" if up else "hidden and insensitive"}, '
                                 f'the rows from y 0, the stacking and virtual_h, unchanged by relayouts {errs}')
    m = ST(ents(3), bar=True, end=False)
    vh_with = m.vh()
    m.bar_off(); m.relayout()
    expect(m.vh() == SH_H + 8 * ROW_H and not m.is_visible(m.pad) and m.y_of(m.shelf) == 8 * ROW_H, f'the mini bar goes: the spacer row is hidden, virtual_h is the rows and the shelf ({m.vh()})')
    m.bar_on(); m.relayout()
    expect(m.vh() == vh_with and m.y_of(m.pad) == 8 * ROW_H + SH_H, 'and comes back: the same padding below the shelf')
    m.arrange(); m.relayout()
    expect(m.vh() == vh_with and m.y_of(m.shelf) == 8 * ROW_H, 'the menu\'s arrangement keeps both')
    expect(m.word(m.sv + 0xf4) == 0, 'the plain painter paints the list (the stock hook assumes y order and stops at the first child below the canvas)')
    painted = m.paint_list(d=0)
    expect('pod_shelf' in painted and all(f'pod_row{i}' in painted for i in (1, 2)), f'the shelf (its top is in view) and the first rows are painted ({painted})')
    painted = m.paint_list(d=300)
    expect('pod_shelf' in painted and 'pod_row1' not in painted and f'pod_row{EX}' in painted, f'scrolled 300 px the shelf and the last rows are painted, the first row is not ({painted})')
    # scrolled to the end with the mini bar up: the artist line's box ends MB_GAP above the pill, as the last row did
    m = ST(ents(3), bar=True)
    list_y_of_shelf_end = m.y_of(m.shelf) + SH_H - m.yoff()
    expect(m.yoff() == m.vh() - 430 and list_y_of_shelf_end == O['MB_Y'] - O['HOME_PAD'] - O['MB_GAP'],
           f'scrolled to the end with the bar up, the shelf ends {O["MB_Y"] - O["HOME_PAD"] - list_y_of_shelf_end} px above the pill (MB_GAP {O["MB_GAP"]})')
    # no jump: the user at the top, the shelf toggled (the rows are above it and never move)
    m = ST(ents(3), end=False)
    y0 = m.row_ys()
    m.fs[SHELF_SET] = b'0\n'; m.fire(EVT_FG); m.relayout()
    expect(not m.shelf_up() and m.row_ys() == y0 and m.yoff() == 0 and m.vh() == 8 * ROW_H, 'the switch off at the top of the list: nothing moves')
    m.fs[SHELF_SET] = b'1\n'; m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up() and m.row_ys() == y0 and m.yoff() == 0 and m.vh() == 8 * ROW_H + SH_H, 'and on again: the rows stay, the list does not jump')
    m = ST(None, end=False)
    m.fs[RECENT] = pod_recent.dump(ents(1)); m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up() and m.row_ys() == y0 and m.yoff() == 0, 'the first album recorded while the menu is at the top: the shelf appears below, nothing moves')
    # the shelf coming and going with the list scrolled
    m = ST(ents(3), bar=True)
    expect(m.yoff() == m.vh() - 430 == 484, 'the list starts at its end')
    m.fs[RECENT] = pod_recent.dump(ents(0)); m.fire(EVT_FG); m.relayout()
    expect(not m.shelf_up() and m.vh() == 8 * ROW_H + MB_PAD and m.yoff() == m.vh() - 430 == 50, f'the shelf goes: the list is clamped to its new end, not thrown to the top ({m.yoff()}, virtual_h {m.vh()})')
    m.setword(m.sv + 0x84, 30)
    m.fs[RECENT] = pod_recent.dump(ents(2)); m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up() and m.yoff() == 30 and m.vh() == shh(2) + 8 * ROW_H + MB_PAD, f'the shelf comes back: the list keeps its place ({m.yoff()}, {m.vh()})')

    # ------------------------------------------------------------------ hit tests with demo's own widget_find_target (the list scrolled to its end, the shelf in view)
    m = covered(ST(ents(3)))
    top = O['HOME_PAD']       # the list starts HOME_PAD down in the window; the window's own y is not in this tree
    def scroll_to(m, content_y, margin=40):
        """The list scrolled so that content_y is `margin` px below the viewport's top (as far as the list allows); the window y of content y 0 of the shelf."""
        m.setword(m.sv + 0x84, max(0, min(content_y - margin, m.vh() - 430)))
        return top + m.y_of(m.shelf) - m.yoff()
    for i in range(3):
        sh_y = scroll_to(m, m.y_of(m.shelf) + cell_y(i))      # the cell's row brought into view: every tile is reachable when scrolled into view
        for what, cy in (('the cover', GRID_COVER // 2), ('the cover\'s corner', 2), ('the album line', TITLE_OFF + 10), ('the artist line', SUB_OFF + 9)):
            p = m.target(tile_x(i) + 72, sh_y + cell_y(i) + cy)
            expect(p[-1] == 'pod_shelf' and p[-2] == 'pod_scrollview', f'tile {i}, {what}: the touch is the shelf\'s ({p})')
    sh_y = scroll_to(m, m.y_of(m.shelf), 100)
    for x, y in ((pod_ui.SH_HEAD_X + 20, pod_ui.SH_HEAD_TOP + 11), (GRID_MARGIN + 10, pod_ui.SH_HEAD_TOP + 3), (250, pod_ui.SH_HEAD_TOP + 18)):
        p = m.target(x, sh_y + y)
        expect(p[-1] == 'pod_shelf' and 'pod_sh_head' not in p, f'the header at ({x}, {y}): the touch is the shelf\'s, not the label\'s (it is insensitive) ({p})')
    for x, y, what in ((3, SH_TOP + 60, 'the left margin'), (tile_x(0) + GRID_COVER + 3, SH_TOP + 60, 'the gap between two covers'), (160, 3, 'the air above the header'),
                       (160, SH_TOP + CELL + 4, 'the gap between the rows'), (310 - 2, SH_TOP + 60, 'the margin right of the second cover')):
        p = m.target(x, sh_y + y)
        expect(p[-1] == 'pod_shelf', f'{what}: still the shelf (its handler decides there is no tile) ({p})')
    p = m.target(160, sh_y - 1)
    expect(p[-1] == f'pod_row{EX}', f'the pixel row above the shelf is the Extras row ({p})')
    p = m.target(160, sh_y - ROW_H - 1)
    expect(p[-1] == 'pod_row18', f'and the row above it (Settings) ({p})')
    p = m.target(160, 5)
    expect(p[-1] == 'window', 'above the list (the 10 px of air) the window')
    sh_y = scroll_to(m, m.vh() - 430 + 200)       # scrolled to the end: the shelf's last pixel rows end the list
    p = m.target(160, sh_y + SH_H2 - 1)
    expect(p[-1] == 'pod_shelf' and sh_y + SH_H2 == top + 430, f'the last pixel row of the shelf is the shelf\'s, and the shelf ends the list ({p})')
    # no shelf: the rows are where they always were
    m = ST(None)
    p = m.target(tile_x(0) + 48, top + 20)
    expect(p[-1] == 'pod_row1' and 'pod_shelf' not in p, f'with nothing to show the hidden shelf takes no touch: the first row is at the top ({p})')
    m = ST(None, end=False)
    p = m.target(tile_x(0) + 48, top + 8 * ROW_H + 10)
    expect('pod_shelf' not in p, f'and nothing of it where it would be ({p})')
    # scrolled part way (the shelf's top just in view): the tiles' places follow the scroll
    m = covered(ST(ents(3), end=False))
    m.setword(m.sv + 0x84, 100)
    sh_y = m.y_of(m.shelf) - 100 + top
    p = m.target(tile_x(1) + 48, sh_y + 20)
    expect(p[-1] == 'pod_shelf', f'scrolled 100 px: the shelf\'s top is at window y {sh_y} and its header is the shelf\'s ({p})')
    p = m.target(160, sh_y - 5)
    expect(p[-1] == f'pod_row{EX}', f'with the Extras row above it ({p})')
    # the mini bar's pill still takes its area (it is a later sibling of the list); the shelf partly under it (list at the top) does not reach it
    m = covered(ST(ents(3), bar=True, end=False))
    p = m.target(160, O['MB_Y'] + O['MB_H'] // 2)
    expect(p[-1] == 'pod_minibar', f'the mini bar takes its place, the shelf (its top is under the pill when the list is at the top) does not ({p})')
    m = covered(ST(ents(3), bar=True))
    p = m.target(160, O['MB_Y'] + O['MB_H'] // 2)
    expect(p[-1] == 'pod_minibar', f'scrolled to the end the pill still takes its area ({p})')
    sh_y = m.y_of(m.shelf) - m.yoff() + top
    p = m.target(tile_x(0) + 48, sh_y + SH_TOP + 48)
    expect(p[-1] == 'pod_shelf', 'and the covers (above the pill) are the shelf\'s')
    p = m.target(160, O['MB_Y'] - 3)
    expect('pod_minibar' not in p and p[-1] in ('pod_shelf', 'pod_pad', 'pod_scrollview'), f'just above the pill the list ({p})')
    m.bar_off()
    p = m.target(160, O['MB_Y'] + O['MB_H'] // 2)
    expect('pod_minibar' not in p, f'a hidden bar takes none ({p})')


def grid_and_tap_tests(ctx):
    """The 2 x 3 grid, the covers made once the shelf is in view, taps on demo's own pointer code."""
    expect, e3 = ctx.expect, ents(3)
    # ------------------------------------------------------------------ the 2 x 3 grid: 1 to 6 albums
    COLORS = ((200, 40, 40), (40, 200, 90), (40, 90, 220), (200, 200, 40), (90, 40, 200), (40, 200, 200))
    for na in (1, 2, 3, 4, 5, 6):
        real = na in (1, 6)     # decoded covers for one and six albums; the shared placeholder disc between (the geometry is the same, the decodes are not)
        m = ST(ents(na), start=False)
        if real:
            for i in range(na): m.cover(*ALBUMS[i][:2], rgb=COLORS[i])
        m.start(); m.decode_all()
        rows, errs = (na + 1) // 2, []
        if not m.word(m.shelf + 0xc) == shh(na) == SH_Hn(rows) == 44 + rows * 190 + (rows - 1) * 10: errs.append(f'shelf {m.word(m.shelf + 0xc)} px high')
        if not (m.vh() == 8 * ROW_H + shh(na) and m.y_of(m.shelf) == 8 * ROW_H): errs.append(f'virtual_h {m.vh()}')
        blits, texts = m.paint()
        bm = list(m.bitmaps)
        if [b[2] for b in blits] != [(tile_x(i), cell_y(i), GRID_COVER, GRID_COVER) for i in range(na)]: errs.append(f'covers at {[b[2][:2] for b in blits]}')
        if not (len(texts) == 2 * na and shown_texts(m) == [(cut(ALBUMS[i][1], GRID_COVER), cut(ALBUMS[i][0], GRID_COVER)) for i in range(na)]): errs.append(f'texts {shown_texts(m)}')
        expect(not errs, f'{na} album(s): the shelf {rows} row(s) high, set before the rows are arranged; virtual_h the rows and the shelf; {na} cover(s) of {GRID_COVER} px '
                         f'filled row by row (x 12 / 164, rows 200 apart from y 44); the album and the artist under each, cut with an ellipsis to 144 px {errs}')
        if not real: continue
        expect(len(bm) == na and len(m.bitmaps) * GRID_COVER * GRID_COVER * 4 == na * 82944 <= 497664, f'{na} album(s): {na} x 82,944 B of covers (at most 497,664 B for six)')
        m.call(PSYMS['rc_on_destroy'], a0=m.root, a1=0)
        expect([c[1] for c in m.calls if c[0] == 'bitmap_destroy'] == bm, f'{na} album(s): all the covers are freed on destroy')
    m = ST(ents(6), start=False); m.start(); m.decode_all()
    expect(len(m.bitmaps) == 1, 'six albums with no cover: one shared disc bitmap, not six')
    m.call(PSYMS['rc_on_destroy'], a0=m.root, a1=0)
    expect(len([c for c in m.calls if c[0] == 'bitmap_destroy']) == 1, 'and it is freed too')
    # the shelf changes height with the list: 2 albums -> 6 -> 3 -> 5 -> 1 keeps the rows and the scroll place
    m = ST(ents(2), end=False)
    expect(m.vh() == 8 * ROW_H + SH_H1, 'two albums: one row')
    for n_, h_ in ((6, SH_H3), (3, SH_H2), (5, SH_H3), (1, SH_H1)):
        m.fs[RECENT] = pod_recent.dump(ents(n_)); m.fire(EVT_FG); m.relayout()
        expect(m.vh() == 8 * ROW_H + h_ and m.word(m.shelf + 0xc) == h_ and m.row_ys()[1] == 0, f'{n_} albums: {h_} px, the rows above it stay')
    # six albums, the list scrolled to the end: the last artist line's box ends MB_GAP above the pill
    m = ST(ents(6), bar=True)
    expect(m.yoff() == m.vh() - 430 and m.y_of(m.shelf) + SH_H3 - m.yoff() == O['MB_Y'] - O['HOME_PAD'] - O['MB_GAP'],
           f'six albums, three rows, the bar up, scrolled to the end ({m.yoff()} of {m.vh()}): the last artist line ends MB_GAP above the pill')
    expect(m.vh() == 8 * ROW_H + SH_H3 + MB_PAD, 'virtual_h: the rows, the shelf, the spacer')
    # three rows: relayouts with and without the bar's spacer change nothing
    for bar_ in (False, True):
        m = ST(ents(6), bar=bar_, end=False)
        y0, vh0, ys0 = m.row_ys(), m.vh(), m.y_of(m.shelf)
        m.relayout(); m.mark(); m.relayout(); m.arrange(); m.relayout(); m.mark(); m.relayout()
        expect(m.row_ys() == y0 and m.vh() == vh0 and m.y_of(m.shelf) == ys0 == 8 * ROW_H and m.stack()[8] == 'shelf' and m.stack()[-1] == 'pad',
               f'three rows, {"bar" if bar_ else "no bar"}: repeated relayouts and the arrangement keep the page (virtual_h {m.vh()})')
    # every cell reachable once its row is scrolled into view
    m = covered(ST(ents(6)))
    for i in range(6):
        m.setword(m.sv + 0x84, max(0, min(m.y_of(m.shelf) + cell_y(i) - 40, m.vh() - 430)))
        wy = O['HOME_PAD'] + m.y_of(m.shelf) - m.yoff() + cell_y(i)
        p = m.target(tile_x(i) + 72, wy + 72)
        expect(p[-1] == 'pod_shelf', f'cell {i} (row {i // 2}) scrolled into view: its cover is the shelf\'s ({p})')
    # the decode goes row by row, nearest the viewport (the top row) first, and a row far below the viewport waits
    m = ST(ents(6), start=False)
    for i in range(6): m.cover(*ALBUMS[i][:2], rgb=COLORS[i])
    m.start(); m.setword(m.sv + 0x84, 0)    # the list at the top: the shelf starts at 416, rows 1 and 2 are at 660 and 860
    m.first(); first = [u_ for u_ in m.loads if u_.startswith('file://')]
    m.tick(); m.tick()
    done = [u_ for u_ in m.loads if u_.startswith('file://')]
    expect(first == ['file://' + art_file(album_key(*ALBUMS[0][:2]))] and done == ['file://' + art_file(album_key(*ALBUMS[i][:2])) for i in range(2)],
           f'at the top of the list only the first row is within a row of the viewport: it is decoded first cell first, and nothing of the rows below ({len(m.loads)} loads)')
    expect(len(m.bitmaps) == 2 and m.tick() == 0, 'the tick then ends: rows 2 and 3 wait')
    fn, ctx = m.bound[(m.sv, O['EVT_SCROLL'])]
    m.timers = []; m.setword(m.sv + 0x84, 250); m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], 'scrolled so that the second row comes within a row of the viewport: the tick is armed again')
    m.tick(); m.tick()
    expect(len(m.bitmaps) == 4, 'the second row is made (two covers); the third row, 200 px further down, still waits')
    m.setword(m.sv + 0x84, m.vh() - 430); m.timers = []; m.call(fn, a0=ctx, a1=0, count=2000000); m.tick(); m.tick()
    expect(len(m.bitmaps) == 6, 'at the end of the list the third row is made: all six covers (486 KB) are resident only then')

    # ------------------------------------------------------------------ the covers are made once the shelf is in view or about to be (it is at the bottom of a long list)
    LONG = b'012345678abcdefghj\n'      # 18 shown items (Settings last) + Extras: the shelf is at y 988, far below a 430 px viewport
    EV_SCROLL = O['EVT_SCROLL']
    m = covered(ST(ents(3), saved=LONG, end=False))
    expect(m.y_of(m.shelf) == 19 * ROW_H and m.timers == [(PSYMS['rc_first'], O['RC_FIRST_MS'])], f'a long menu: the shelf is far below the viewport, the one-shot is armed as always ({m.y_of(m.shelf)}, {m.timers})')
    m.first()
    expect(not m.bitmaps and 'widget_load_image' not in m.names() and 'bitmap_create_ex' not in m.names() and not m.timers[1:], 'the one-shot decodes nothing and arms no tick while the shelf is out of reach')
    fn, ctx = m.bound[(m.sv, EV_SCROLL)]
    m.timers = []; m.setword(m.sv + 0x84, 400); m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(not m.timers and not m.bitmaps, 'scrolled to 400 (the shelf top is 588 px below the viewport\'s top, more than a row below its bottom): nothing yet')
    m.setword(m.sv + 0x84, 19 * ROW_H + SH_TOP - 430 - ROW_H + 1); m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], f'EVT_SCROLL that brings the shelf\'s top within one row of the viewport\'s bottom arms the tick ({m.timers})')
    m.timers = []; m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(not m.timers, 'a second scroll event does not arm a second timer')
    m.tick(); m.tick(); m.tick()
    expect(len(m.bitmaps) == 2, 'and the first row\'s two covers are made, one per tick (the third album is in the next row, 200 px further down: it waits)')
    # scrolled away again: a tile still to be made waits
    m = covered(ST(ents(3), saved=LONG, end=False)); m.first()
    m.setword(m.sv + 0x84, 19 * ROW_H + SH_TOP - 430 - ROW_H + 1); m.call(*[m.bound[(m.sv, EV_SCROLL)][0]], a0=m.bound[(m.sv, EV_SCROLL)][1], a1=0, count=2000000)
    m.tick(); m.setword(m.sv + 0x84, 0); m.timers = []
    r = m.tick()
    expect(r == 0 and len(m.bitmaps) == 1, f'a tick after the list went back up makes nothing more and ends ({len(m.bitmaps)} cover made)')
    m.fire(EVT_BG); m.fire(EVT_FG)
    expect(not m.timers, 'to-foreground with the shelf still out of view arms nothing')
    m.setword(m.sv + 0x84, 19 * ROW_H - 430); m.timers = []; m.fire(EVT_BG); m.fire(EVT_FG)
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], 'to-foreground with the shelf in view arms the tick (the covers still to make)')
    # a short menu (the default's 8 rows): the shelf is within a row of the viewport at the top already, so the first one-shot decodes
    m = covered(ST(ents(3), end=False)); m.first()
    expect(len(m.bitmaps) == 1, 'the default menu: the shelf starts 14 px inside the viewport, the one-shot makes the first cover')
    # no scroll event (its registration refused): the covers are made as soon as the shelf is shown, as before
    m = covered(ST(ents(3), saved=LONG, end=False, start=False)); m.on_fail = frozenset({EV_SCROLL}); m.start(); m.first()
    expect(m.shelf_up() and len(m.bitmaps) == 1, 'a refused scroll event: the shelf still shows, its covers are made after the one-shot wherever the list is')

    # ------------------------------------------------------------------ taps: demo's own pointer code (scroll_view, the list gesture hook), the payload's handlers
    ZONES = (('the cover', SH_TOP + 48), ('the cover\'s top edge', SH_TOP), ('the album line', (SH_TOP + TITLE_OFF) + 10), ('the artist line', (SH_TOP + SUB_OFF) + 9),
             ('the gap between the cover and the album line', SH_TOP + SH_COVER + 1))
    m = covered(ST(ents(3))); row_of = library(m)
    m.calls = []
    wrong = []
    for i in range(3):
        for what, c in ZONES:
            m.tap(cx(i), sy(c + cell_y(i) - SH_TOP))
            if m.opened() != [(O['CLASS_ALBUMS'], row_of[i])]: wrong.append((i, what, m.opened()))
    expect(not wrong, f'a tap on the cover, its top edge, the album line, the artist line or the gap under the cover of a tile opens that album\'s stock row {wrong}')
    m.tap(cx(0), sy(SH_TOP + 48))
    names = [c[0] for c in m.calls_all]
    expect(names.count('loadLocalClassList') == 1 and names.count('loadAlbumList') == 1 and names.count('albumcoverinfo_init') == 1 and names.count('batchadd_albumcover_task') == 1
           and names.count('deque_destroy') == 1, f'the stock list is loaded, copied and released once, then the Albums grid\'s own sequence runs ({names})')
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls_all and ('loadAlbumList', O['CLASS_ALBUMS'], 0, '') in m.calls_all, 'the library\'s albums (0xf003), the Albums page\'s sequence')
    # the row found: by the key; the title of another artist (a compilation); the case; the track path; none at all
    def lib_with(rows):
        m = covered(ST(ents(3))); library(m, rows=rows); m.calls = []; return m
    base = [(a, r, f'/mnt/mmc/{r}/{a}/1.flac') for r, a in ALBUMS[:3]]
    m = lib_with([base[1], base[0], base[2]]); m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], 1)], f'by the album key ({m.opened()})')
    m = lib_with([('Other', 'Other artist', '/x/1.flac'), ('Kind of Blue', 'Various Artists', '/y/1.flac'), base[1]]); m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], 1)], f'else by the album title, whatever the artist (a compilation lists one artist) ({m.opened()})')
    m = lib_with([('Other', 'Other artist', '/x/1.flac'), ('KIND of blue', 'Various Artists', '/y/1.flac')]); m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], 1)], f'ASCII case aside ({m.opened()})')
    m = lib_with([('Other', 'Other artist', '/x/1.flac'), ('Kind of Blue (Remastered)', 'Miles', e3[0][5])]); m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], 1)], f'else by the recorded track\'s path ({m.opened()})')
    m = lib_with([('Other', 'Other artist', '/x/1.flac'), ('Another', 'Miles', '/z/1.flac')]); m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [] and not [c for c in m.calls_all if c[0] == 'navigator_to_with_context'],
           'an album that is gone from the library: nothing opens (and nothing crashes)')
    expect(not [c for c in m.calls_all if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'batchadd_albumcover_task')], 'not even the stock sequence starts')
    m = lib_with([('Kind of Blue', 'Various', '/y/1.flac')]); m.showlist[0:1] = [m.record(album='Kind of Blue', artist='Various', path='/y/1.flac', rid=-1)]
    m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [], 'the "Unknown Album" row (id -1) is never matched by title')
    m = covered(ST(ents(3))); m.showlist = []; m.calls = []; m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [] and not [c for c in m.calls_all if c[0] == 'loadAlbumList'], 'an empty library: nothing opens')
    # dead zones
    m = covered(ST(ents(3))); library(m); m.calls = []
    for x, c, what in ((cx(0), SH_TOP + CELL + 4, 'the gap between the rows'), (cx(0), pod_ui.SH_HEAD_TOP + 11, 'the header'), (GRID_MARGIN + 30, pod_ui.SH_HEAD_TOP + 5, 'the header\'s text'), (3, SH_TOP + 48, 'the left margin'), (tile_x(0) + SH_COVER + 3, SH_TOP + 48, 'the gap between two tiles'), (cx(0), SH_TOP - 4, 'the air above the cover'),
                       (cx(3), SH_TOP + PITCH + 48, 'the fourth cell\'s place when there are three albums'), (tile_x(0) - 1, SH_TOP + 48, 'a pixel left of the first cover')):
        m.tap(x, sy(c))
        expect(m.opened() == [], f'a tap on {what} opens nothing')
    expect(not [c for c in m.calls_all if c[0] == 'loadLocalClassList'], 'and does not even load the album list')
    m.setword(m.sv + 0x84, 300); m.tap(cx(0), sy(-20))
    expect(m.opened() == [] and (f'pod_row{EX}', EVT_CLICK) in m.fired, f'a tap just above the shelf is the Extras row\'s ({m.fired})')
    m = covered(ST(ents(2))); library(m); m.tap(tile_x(1) + SH_COVER - 1, sy(SH_TOP + 48))
    expect(m.opened() != [], 'the last pixel column of a cover is the tile\'s')
    m.tap(tile_x(1) + SH_COVER, sy(SH_TOP + 48)); n_ = len(m.opened())
    expect(n_ == 0, 'the first pixel of the gap after it is not')
    # the handlers never consume an event
    m = covered(ST(ents(3)))
    for fn in ('rc_on_down', 'rc_on_up', 'rc_on_abort'):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + O['PE_X'], cx(0)); m.setword(e + O['PE_Y'], sy(60))
        expect(m.call(PSYMS[fn], a0=0, a1=e) == 0, f'{fn} answers RET_OK: the scroll view still sees the event')
    # a null event is ignored
    expect(m.call(PSYMS['rc_on_down'], a0=0, a1=0) == 0 and m.call(PSYMS['rc_on_up'], a0=0, a1=0) == 0, 'a null event is ignored')

    # swipes and flings: never an album
    def touch_steps(c, move_to, steps=6, dt=16, x=None):
        x = cx(1) if x is None else x
        y0 = sy(c)
        return [('d', x, y0, 0)] + [('m', x, y0 + (move_to - c) * i // steps, dt) for i in range(1, steps + 1)] + [('u', x, y0 + (move_to - c), dt)]
    swipes = {'a slow drag up': touch_steps(SH_TOP + 48, SH_TOP + 48 - 90, 18, 30), 'a quick drag up': touch_steps(SH_TOP + 48, SH_TOP + 48 - 120, 5, 12),
              'a drag down': touch_steps(SH_TOP + 48, SH_TOP + 48 + 90, 9),
              'a drag that starts on a caption': touch_steps((SH_TOP + SUB_OFF) + 9, (SH_TOP + SUB_OFF) + 9 - 70, 7),
              'UP 80 px away, no MOVE at all': [('d', cx(1), sy(60), 0), ('u', cx(1), sy(60) + 80, 40)],
              'UP 12 px away, no MOVE': [('d', cx(1), sy(60), 0), ('u', cx(1), sy(60) + 12, 60)],
              'a MOVE of 5 px, UP 62 px away': [('d', cx(1), sy(60), 0), ('m', cx(1), sy(60) + 5), ('u', cx(1), sy(60) + 62)],
              'a quick flick: MOVE 9 px, UP 100 px away': [('d', cx(1), sy(60), 0), ('m', cx(1), sy(60) - 9), ('u', cx(1), sy(60) - 100, 16)],
              'a horizontal drag of 40 px': [('d', cx(1), sy(60), 0), ('m', cx(1) + 20, sy(60)), ('u', cx(1) + 40, sy(60), 40)],
              'a diagonal slip of 7 px across and 10 px down': [('d', cx(1), sy(60), 0), ('u', cx(1) + 7, sy(60) + 10, 40)],
              'out 40 px and back to 3 px': [('d', cx(1), sy(60), 0), ('m', cx(1), sy(60) + 40), ('m', cx(1), sy(60) + 3), ('u', cx(1), sy(60) + 3)],
              'a finger that slides onto the next tile': [('d', cx(1), sy(60), 0), ('m', cx(2) - 4, sy(60) + 2), ('u', cx(2) - 4, sy(60) + 2, 40)]}
    opened = []
    for name, steps in swipes.items():
        m = covered(ST(ents(3))); library(m); m.calls = []
        m.gesture(steps)
        if m.opened() or [c for c in m.calls_all if c[0] == 'loadLocalClassList']: opened.append((name, m.opened()))
    expect(not opened, f'none of the {len(swipes)} swipes, flicks and slides opens an album or even loads the album list {opened}')
    m = covered(ST(ents(3))); library(m)
    m.gesture(touch_steps(SH_TOP + 48, SH_TOP + 48 - 90, 18, 30))
    expect(m.yoff() > 60, f'a vertical drag that starts on the shelf scrolls the list as on any row ({m.yoff()} px)')
    # a small slip is still a tap, 10 px is a drag (the scroll view's own threshold)
    got = {}
    for dy in (0, 3, 9, 10, 14):
        m = covered(ST(ents(3))); library(m)
        m.gesture([('d', cx(1), sy(60), 0), ('u', cx(1), sy(60) + dy, 60)])
        got[dy] = len(m.opened())
    expect(got == {0: 1, 3: 1, 9: 1, 10: 0, 14: 0}, f'a release 0, 3 or 9 px from the press opens the album, 10 or 14 px does not (px: albums opened {got})')
    # a touch that stops a coasting list presses nothing; the next touch is a tap again
    m = covered(ST(ents(3))); library(m)
    m.gesture([('d', 160, 300, 0), ('m', 160, 280), ('m', 160, 230), ('u', 160, 200, 16)])          # a flick up: the list coasts
    m.setword(m.sv + 0x84, m.vh() - 430)                                                         # (and is at its end, the shelf under the finger, as a flick down would leave it)
    expect(m.wa() != 0, 'a flick leaves a running scroll animation')
    m.gesture([('d', cx(1), sy(SH_TOP + 48), 40), ('u', cx(1), sy(SH_TOP + 48), 60)])
    expect(m.opened() == [] and m.wa() == 0 and ('rc_on_down' not in m.names()),
           f'a touch on a tile while the list coasts only stops it, nothing opens, the animation is gone ({m.opened()}, animator {m.wa():#x})')
    m.gesture([('d', cx(1), sy(SH_TOP + 48), 400), ('u', cx(1), sy(SH_TOP + 48), 60)])
    expect(m.opened() == [(O['CLASS_ALBUMS'], row_of[1])], f'and the next tap opens the album ({m.opened()})')
    # the same without the list gesture hook (what stock does): the touch that stops the list is a tap on the tile, and a quick flick released far away is one too
    m = covered(ST(ents(3), hook=False)); library(m)
    m.gesture([('d', 160, 300, 0), ('m', 160, 280), ('m', 160, 230), ('u', 160, 200, 16)]); m.setword(m.sv + 0x84, m.vh() - 430)
    m.gesture([('d', cx(1), sy(SH_TOP + 48), 40), ('u', cx(1), sy(SH_TOP + 48), 60)])
    expect(m.opened() != [], 'STOCK (no hook): the touch that stops a coasting list opens the album under the finger: the hole patch/scroll.c closes, and the shelf follows the rows')
    m = covered(ST(ents(3), hook=False)); library(m)
    m.gesture([('d', cx(1), sy(60), 0), ('u', cx(1), sy(60) + 80, 40)])
    expect(m.opened() == [], 'STOCK (no hook): UP 80 px away with no MOVE is not a tap on the shelf either: its own distance check (the rows have none)')
    # the window going to the back mid-press (the pull-down): the abort, and an up that arrives anyway is no tap
    m = covered(ST(ents(3))); library(m)
    m.gesture([('d', cx(1), sy(60), 0), ('a', cx(1), sy(60), 16), ('u', cx(1), sy(60), 20)])
    expect(m.opened() == [], 'an aborted press does not open the album when an up arrives afterwards')
    m = covered(ST(ents(3))); library(m)
    m.gesture([('d', cx(1), sy(60), 0)]); m.call(PSYMS['rc_on_background'], a0=m.root, a1=0); m.calls_all = []
    m.gesture([('u', cx(1), sy(60), 20)])
    expect(m.opened() == [], 'a press that was open when the menu went to the back is forgotten')
    # the press that began on a tile and a release on another
    m = covered(ST(ents(3))); library(m)
    m.gesture([('d', cx(1) + 40, sy(60), 0), ('u', cx(1) + 52, sy(60), 40)])
    expect(m.opened() == [], 'a press on one tile released on another opens neither')
    # an up with no down (a touch that stopped the coasting list never reached the shelf): nothing
    m = covered(ST(ents(3))); library(m)
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + O['PE_X'], cx(1)); m.setword(e + O['PE_Y'], sy(60))
    m.call(PSYMS['rc_on_up'], a0=0, a1=e)
    expect(not [c for c in m.calls if c[0] in ('loadLocalClassList', 'loadAlbumList')], 'an up that has no down opens nothing')
    # a tap while the list is scrolled: the tile under the finger by its place in the content
    m = covered(ST(ents(3))); library(m); m.setword(m.sv + 0x84, 100)
    m.tap(cx(1), sy(SH_TOP + 20))
    expect(m.opened() == [(O['CLASS_ALBUMS'], row_of[1])], f'scrolled 100 px (the shelf\'s top at list y 316), a tap on tile 1\'s cover opens its album ({m.opened()})')
    m = covered(ST(ents(3))); library(m); m.setword(m.sv + 0x84, 100); m.tap(cx(0), sy(SH_TOP + 60))
    expect(m.opened() == [(O['CLASS_ALBUMS'], row_of[0])], f'scrolled 100 px, the last rows of pixels of the cover that the list\'s bottom edge still shows are tile 0\'s ({m.opened()})')
    m = covered(ST(ents(3))); library(m); m.setword(m.sv + 0x84, 100); m.tap(cx(2), sy(SH_TOP + PITCH + 20))
    expect(m.opened() == [], 'a cell below the list\'s bottom edge (scrolled out of view) cannot be tapped: the point is outside the list')
    # taps with the mini bar up and the shelf shown: nothing changes for the shelf
    m = covered(ST(ents(3), bar=True)); library(m); m.tap(cx(1), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], row_of[1])], 'with the mini bar up a tap on a tile opens its album')



def refresh_and_fallback_tests(ctx):
    """The menu in front again, the Settings switch, every failure's fallback, the Home instance only, recording, the album's identity and cover key."""
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    row_of = {i: k for k, i in enumerate(LIB)}
    # ------------------------------------------------------------------ the menu in front again: the list and the switch are read again, only the changed tiles are redone
    def rgb_cover(m, i, rgb): m.cover(*ALBUMS[i][:2], rgb=rgb)
    def centre_of(m, bmp):
        data, w, h = m.bitmaps[bmp]
        return minibar.rgb_of(struct.unpack_from('<I', bytes(m.u.mem_read(data, w * h * 4)), 4 * (h // 2 * w + w // 2))[0])
    m = covered(ST(ents(3))); library(m)
    rgb_cover(m, 3, (250, 250, 20))
    m.decode_all()
    bm = list(m.bitmaps)
    m.fs[RECENT] = pod_recent.dump([entry(*ALBUMS[3])] + ents(2)); m.timers = []; m.calls = []
    m.fire(EVT_FG)
    expect(m.names().count('open') >= 1 and 'widget_load_image' not in m.names() and 'bitmap_create_ex' not in m.names() and m.names().count('bitmap_destroy') == 1, 'to-foreground reads the file again and decodes nothing in the event; the cover of the album that dropped out is freed')
    expect(m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], 'one tile is queued: the tick is armed')
    expect(shown_texts(m) == [(cut(ALBUMS[3][1]), cut(ALBUMS[3][0])), (cut(ALBUMS[0][1]), cut(ALBUMS[0][0])), (cut(ALBUMS[1][1]), cut(ALBUMS[1][0]))],
           'the shelf shows the new list: the album played last first')
    blits, _ = m.paint()
    expect([b[0] for b in blits] == [bm[0], bm[1]] and [b[2][:2] for b in blits] == [(tile_x(1), cell_y(1)), (tile_x(2), cell_y(2))],
           f'the two albums that moved one place keep their covers without a decode ({[hex(b[0]) for b in blits]} at {[b[2][:2] for b in blits]})')
    m.tick()
    expect(m.names().count('widget_load_image') == 1 and ('widget_load_image', 'file://' + art_file(album_key(*ALBUMS[3][:2]))) in m.calls and m.names().count('bitmap_create_ex') == 1
           and 'bitmap_destroy' not in m.names(), 'one tick decodes the new album only, into a bitmap of its own')
    blits, _ = m.paint()
    expect([b[0] for b in blits][1:] == [bm[0], bm[1]] and len(m.bitmaps) == 3 and bm[2] not in m.bitmaps, 'the two kept bitmaps and the new one are all there is')
    expect([centre_of(m, b[0]) for b in blits] == [(250, 250, 20), (200, 40, 40), (40, 200, 90)], 'the new cover first, then the two that moved right')
    # nothing changed: nothing is redone
    m.timers = []; m.calls = []; m.fire(EVT_FG)
    expect(not m.timers and 'widget_load_image' not in m.names() and 'bitmap_destroy' not in m.names() and len(m.bitmaps) == 3, 'the same list: no tile is redone')
    # fewer albums: the bitmaps of the tiles that go are freed
    m.fs[RECENT] = pod_recent.dump(ents(1)); m.calls = []; m.fire(EVT_FG)
    expect(m.names().count('bitmap_destroy') == 2 and m.shelf_up() and len(m.bitmaps) == 1, 'one album left: the shelf stays with one tile, two bitmaps are freed')
    blits, texts = m.paint()
    expect(len(blits) == 1 and len(texts) == 2 and m.y_of(m.shelf) == 8 * ROW_H, 'drawn: one cover and its two texts')
    # none: the shelf goes, the rows go up, nothing stays allocated
    m.fs[RECENT] = pod_recent.dump([]); m.calls = []; m.fire(EVT_FG); m.relayout()
    expect(not m.shelf_up() and m.flags(m.shelf) & 12 == 0 and m.row_ys()[1] == 0 and m.vh() == 8 * ROW_H and not m.bitmaps, 'no album: the shelf is hidden and insensitive, the rows are where they were without it, the bitmap is freed')
    expect(m.paint() == ([], []), 'and paints nothing')
    # an album again: the shelf is back, one tick, and the rows go down
    m.fs[RECENT] = pod_recent.dump(ents(2)); m.timers = []; m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up() and m.y_of(m.shelf) == 8 * ROW_H and m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])], 'an album again: the shelf and the rows below it are back, the covers are queued')
    # the switch (Settings > Home Screen)
    m = covered(ST(ents(3))); m.decode_all()
    m.fs[SHELF_SET] = b'0\n'; m.calls = []; m.fire(EVT_FG); m.relayout()
    expect(not m.shelf_up() and m.row_ys()[1] == 0, 'the switch off: the shelf is hidden and insensitive, the rows go back up')
    m.fs[SHELF_SET] = b'1\n'; m.calls = []; m.fire(EVT_FG); m.relayout()
    expect(m.shelf_up() and m.y_of(m.shelf) == 8 * ROW_H and 'widget_load_image' not in m.names(), 'on again: the shelf is back with its covers (kept in RAM, nothing decoded)')
    for content, up in ((b'0', False), (b'0\n', False), (b'1\n', True), (b'x', True), (b'', True), (b'00', True), (b'0x', True), (b'\n', True)):
        m = ST(ents(3), setting=content)
        expect(m.shelf_up() == up, f'switch file {content!r}: the shelf is {"up" if up else "hidden"} at start')
    m = ST(ents(3), setting=b'0\n')
    expect(m.timers == [(PSYMS['rc_first'], O['RC_FIRST_MS'])] and not m.shelf_up() and m.row_ys()[1] == 0, 'switch off at start: the page is set up (the switch can come on), the shelf is not shown, the rows are not moved')
    m.fire(EVT_FG); m.timers = []; m.first()
    expect(not m.timers and 'widget_load_image' not in m.names() and not m.bitmaps, 'and no cover is decoded for a shelf that is not shown')
    # a new album recorded under a menu that is in front (the mini bar's tick): the shelf shows it at once
    m = covered(ST(ents(3))); m.decode_all(); rgb_cover(m, 3, (250, 250, 20))
    t = m.record(album=ALBUMS[3][1], artist=ALBUMS[3][0], path='/mnt/mmc/x/1.flac', title='T', name='1.flac'); m.play([t], 0)
    r = m.call(PSYMS['recent_note'], a0=t, count=3000000)
    expect(r == 1 and pod_recent.parse(m.fs[RECENT])[0][0] == pod_recent.identity(ALBUMS[3][1]), 'the bar\'s note puts the new album first in the file')
    m.timers = []; m.calls = []; m.call(PSYMS['recent_refresh'], count=8000000)
    expect(shown_texts(m)[0] == (cut(ALBUMS[3][1]), cut(ALBUMS[3][0])) and m.timers == [(PSYMS['rc_tick'], O['RC_TICK_MS'])] and 'open' not in m.names(),
           'recent_refresh shows it without reading the file again, the cover is queued')
    m.fire(EVT_BG); m.calls = []; m.call(PSYMS['recent_refresh'], count=8000000)
    expect(m.names() == [], 'a menu that is not in front is left alone by the refresh (it reads the file when it comes back)')

    # ------------------------------------------------------------------ the Settings > Home Screen switch
    homeset = pod_pages.HOMESET_PAGE
    shelf_i = next(i for i, r in enumerate(homeset.rows) if r.action == pod_pages.ACT_SHELF)
    homeset_i = next(i for i, r in enumerate(pod_pages.SETTINGS_PAGE.rows) if r.action == pod_pages.ACT_PAGE and r.arg == pod_pages.HOMESET_PAGE_INDEX)
    expect([(r.label, r.action) for r in homeset.rows][0] == ('Recent Albums', pod_pages.ACT_SHELF) and pod_pages.ACT_SHELF in pod_pages.SWITCH_ACTIONS and pod_pages.ACT_SHELF == 16,
           'the Home Screen page has a switch row "Recent Albums", the first one')
    expect('Recent Albums' in pod_i18n.TEXT and all(pod_i18n.TEXT['Recent Albums'][l] for l in pod_i18n.LOCALES) and len(pod_i18n.TEXT['Recent Albums']) == 13,
           'with a text in all 13 languages (the shorter wording the Spanish and Ukrainian rows need)')
    hs = awtk_ui.parse(open(os.path.join(raw, 'ui', homeset.key + '.bin'), 'rb').read())
    row = next(w for w in hs.walk() if w.name == f'pod_row{shelf_i}')
    expect(row.find(f'pod_switch{shelf_i}') is not None and any(c.get('tr_text') == 'Recent Albums' for c in row.walk()), 'its asset row is a switch row with the label')
    def settings_machine(content=None, daily=None):
        sm = Machine()
        for n in ['btn_return', 'btn_backtoplayer'] + [f'pod_note{i}' for i in range(4)] + [f'pod_row{i}' for i in range(len(homeset.rows))] + [f'pod_switch{i}' for i in range(len(homeset.rows))]: sm.widget(n)
        if content is not None: sm.fs[SHELF_SET] = content
        if daily is not None: sm.fs['/mnt/data/m1plus/home-daily-mix'] = daily   # (patch/home.h DAILY_SET_FILE)
        sm.call(PSYMS['on_row'], a0=PSYMS[f'pod_rows_{pod_pages.SETTINGS_PAGE_INDEX}'] + 12 * homeset_i, count=3000000)
        return sm
    def image_of(sm, i):
        got = [c[2] for c in sm.calls if c[0] == 'image_base_set_image' and c[1] == sm.widgets[f'pod_switch{i}']]
        return got[-1] if got else None
    sm = settings_machine()
    expect(image_of(sm, shelf_i) == 'sset_on' and SHELF_SET not in sm.fs, 'no file: the page opens with the switch on (the default)')
    sm.click(f'pod_row{shelf_i}')
    expect(sm.fs.get(SHELF_SET) == b'0\n' and image_of(sm, shelf_i) == 'sset_off' and ('rename', SHELF_TMP, SHELF_SET) in sm.calls and ('fsync', SHELF_TMP) in sm.calls,
           'a tap switches it off: saved atomically, the image follows')
    sm.click(f'pod_row{shelf_i}')
    expect(sm.fs.get(SHELF_SET) == b'1\n' and image_of(sm, shelf_i) == 'sset_on', 'and on again')
    sm.fail.add(('write', SHELF_TMP)); sm.click(f'pod_row{shelf_i}')
    expect(sm.fs.get(SHELF_SET) == b'1\n' and image_of(sm, shelf_i) is None and SHELF_TMP not in sm.fs, 'a failed save changes neither the file nor the image')
    for content, on in ((b'0\n', 0), (b'0', 0), (b'1\n', 1), (b'x', 1), (b'', 1), (b'0x', 1)):
        sm = settings_machine(content)
        expect(image_of(sm, shelf_i) == ('sset_on' if on else 'sset_off'), f'file {content!r}: the page opens with the switch {"on" if on else "off"}')
    # Regenerate Daily Mix (patch/m1plus.c regen_show): hidden (card, note and row) and insensitive while no mix can be made; the Daily Mix switch updates it in place
    regen_i = next(i for i, r in enumerate(homeset.rows) if r.action == pod_pages.ACT_REGEN)
    daily_i = next(i for i, r in enumerate(homeset.rows) if r.action == pod_pages.ACT_DAILY)
    regen_state = lambda sm: tuple(sm.props.get((sm.widgets[n], k)) for n, k in ((f'pod_row{regen_i}', 'visible'), (f'pod_row{regen_i}', 'sensitive'), ('pod_note3', 'visible'), ('pod_note3', 'sensitive')))
    toasts = lambda sm: [c[1] for c in sm.calls if c[0] == 'toast']
    sm = settings_machine()
    sm.click(f'pod_row{regen_i}')
    expect(toasts(sm) == ['New mix when Home opens'], 'a tap on Regenerate Daily Mix (accepted) shows the toast')
    sm = settings_machine(daily=b'0\n')
    sm.click(f'pod_row{regen_i}')
    expect(toasts(sm) == [], 'a tap while the row is refused (Daily Mix off): no toast')
    sm = settings_machine()
    expect(regen_state(sm) == (1, 1, 1, 0), 'the Daily Mix switch on: Regenerate Daily Mix and its note are shown (the note never takes a touch) and the row tappable')
    sm.click(f'pod_row{daily_i}')
    expect(regen_state(sm) == (0, 0, 0, 0), 'the switch tapped off: the row and its note are hidden and the row insensitive at once')
    sm.click(f'pod_row{daily_i}')
    expect(regen_state(sm) == (1, 1, 1, 0), '... and back when it is on again')
    sm = settings_machine(daily=b'0\n')
    expect(regen_state(sm) == (0, 0, 0, 0), 'the page opened with the switch off: Regenerate and its note are hidden')

    # ------------------------------------------------------------------ every failure falls back to the plain menu
    plain_ys = ST(None).row_ys()
    def touched(m, calls):
        """[] when the shelf was never shown and nothing moved or made; else what was."""
        bad = [c for c in calls if c[0] in ('widget_set_visible', 'widget_set_sensitive', 'widget_move', 'widget_resize', 'bitmap_create_ex', 'timer_add') and not (c[0] == 'timer_add' and m.timer_fail)]
        return [] if not bad and not m.shelf_up() and m.row_ys() == plain_ys and m.vh() == 8 * ROW_H else [f'shown {m.shelf_up()}, {bad[:3]}']
    WHAT = 'the shelf never shown, nothing moved, also in the later callbacks'
    m = ST(ents(3), start=False); m.widgets.pop('pod_sh_head'); m.start()
    expect(m.shelf_up() and m.timers == [(PSYMS['rc_first'], O['RC_FIRST_MS'])], 'the header is the asset\'s own label: the payload never looks it up, a tree without it still shows the tiles')
    for gone in [n for n in pod_ui.SH_NAMES if n != 'pod_sh_head'] + ['pod_scrollview']:
        m = ST(ents(3), start=False); m.widgets.pop(gone); calls = m.start()
        hooked = m.timers or [c for c in calls if c[0] in ('widget_on', 'timer_add')]
        errs = touched(m, calls); m.first(); a = list(m.calls); m.tick(); errs += touched(m, a + m.calls)
        expect(not hooked and not errs, f'no {gone}: no handler, no timer, {WHAT} ({hooked}, {errs})')
    for ev in (EVT_DESTROY, EVT_BG, EVT_FG, EVT_AFTER_PAINT, EVT_DOWN, EVT_UP, EVT_ABORT):
        m = ST(ents(3), start=False); m.on_fail = frozenset({ev}); calls = m.start()
        errs = (['a timer'] if m.timers else []) + touched(m, calls)
        m.first(); a = list(m.calls); m.tick(); errs += touched(m, a + m.calls)
        # the handlers that were registered find no page of ours
        for (w, e), (fn, c) in list(m.bound.items()):
            if w in (m.root, m.shelf) and fn in (PSYMS['rc_on_destroy'], PSYMS['rc_on_background'], PSYMS['rc_on_foreground'], PSYMS['rc_on_paint'], PSYMS['rc_on_down'], PSYMS['rc_on_up'], PSYMS['rc_on_abort']):
                ev_ = m.alloc(0x40); m.u.mem_write(ev_, bytes(0x40)); m.setword(ev_ + O['EVENT_PAINT_CANVAS'], 0x22220000)
                m.call(fn, a0=c, a1=ev_, count=8000000)
                bad = [x for x in m.calls if x[0] in ('widget_set_visible', 'bitmap_create_ex', 'loadLocalClassList', 'canvas_draw_image', 'timer_add')]
                if bad: errs.append(f'the handler at {fn:#x} did {bad}')
        expect(not errs, f'a widget_on of event {ev:#x} refused: no timer, {WHAT}, and the handlers left registered do nothing ({errs})')
    m = ST(ents(3), start=False); m.timer_fail = True; calls = m.start()
    errs = touched(m, calls); m.first(); errs += touched(m, m.calls)
    expect(not errs, f'no timer: {WHAT} (a stale one-shot) ({errs})')
    m = ST(ents(3), start=False); m.widgets.pop('pod_row3'); calls = m.start()
    expect(not m.shelf_up(), 'a menu asset that is not ours (a row missing): the shelf is not shown')
    expect(not [c for c in calls if c[0] == 'widget_move'], 'and no row is moved')
    # no memory for the bitmaps: the shelf shows its texts, the tile still opens its album
    m = covered(ST(ents(3), start=False)); library(m); m.bitmap_ok = False; m.start(); m.decode_all()
    blits, texts = m.paint()
    expect(m.shelf_up() and blits == [] and len(texts) == 6 and not m.bitmaps, 'no bitmap: the texts alone')
    m.tap(cx(1), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], row_of[1])], 'and a tap still opens the album')
    # a cover that does not decode
    m = covered(ST(ents(1), start=False)); m.load_image = 1; m.images.pop('p_default'); m.start(); m.decode_all()
    expect(m.centre(next(iter(m.bitmaps))) == GREY, 'a cover that does not decode and no placeholder: flat grey, still a tile')

    # ------------------------------------------------------------------ patch/home.c starts the shelf on the Home instance only
    HOME_WIN = 0x23000000
    def home_machine(entries=True):
        m = minibar.BM()
        for n in ['navigationbar_view', 'btn_return', 'btn_backtoplayer', 'app_gesture', 'home_sview', 'home_sindicator'] + [f'pod_row{i}' for i in range(len(pod_pages.MENU.rows))] + list(pod_ui.SH_NAMES):
            m.widget(n)
        m.props[(m.widgets['pod_shelf'], 'visible')] = 0
        if entries: m.fs[RECENT] = pod_recent.dump(ents(3))
        return m
    m = home_machine()
    m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000)
    m.top_main = HOME_WIN; m.timers = []
    m.call(PSYMS['hm_open'], count=6000000)
    expect((PSYMS['rc_first'], O['RC_FIRST_MS']) in m.timers and (PSYMS['mb_first'], O['MB_FIRST_MS']) in m.timers
           and ('widget_on', m.window, EVT_DESTROY, PSYMS['rc_on_destroy'], m.window) in m.calls and ('widget_set_visible', m.widgets['pod_shelf'], 1) in m.calls,
           'the menu opened as Home starts the shelf after the bar: its one-shot is armed and the shelf is up')
    expect(not [c for c in m.calls if c[0] in ('bitmap_create_ex', 'widget_load_image', 'loadLocalClassList')], 'and the menu\'s first paint has nothing decoded or loaded')
    m = home_machine(); m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000); m.top_main = HOME_WIN; m.timers = []; m.widgets.pop('navigationbar_view')
    m.call(PSYMS['hm_open'], count=6000000)
    expect(m.names().count('window_open') == 1 and (PSYMS['rc_first'], O['RC_FIRST_MS']) not in m.timers, 'a Home instance whose list could not be laid out gets no shelf')
    m = home_machine(); m.fs['/mnt/data/m1plus-bad'] = b'1\n'                 # recovery: Tidal opens the normal instance
    m.call(PSYMS['m1plus_home_click'], a0=m.icon('1'), count=3000000)
    expect(m.names().count('window_open') == 1 and PSYMS['rc_first'] not in [t[0] for t in m.timers] and ('widget_set_visible', m.widgets['pod_shelf'], 1) not in m.calls,
           'the normal instance (grid icon, recovery): no shelf, no timer')
    m = home_machine(False)
    m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000); m.top_main = HOME_WIN; m.timers = []; m.call(PSYMS['hm_open'], count=6000000)
    expect(('widget_set_visible', m.widgets['pod_shelf'], 1) not in m.calls and (PSYMS['rc_first'], O['RC_FIRST_MS']) in m.timers, 'nothing recorded yet: the page is set up, the shelf stays hidden')

    # Both Home timers share the real shelf and its pending history.
    m = home_machine(False); m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000)
    m.top_main = HOME_WIN; m.call(PSYMS['hm_open'], count=6000000); m.screen(False)
    m.track(album='Dark A'); m.call(PSYMS['mb_first'], count=40000000)
    m.track(album='Dark B', path='/mnt/mmc/b/1.flac'); m.call(PSYMS['mb_tick'], count=40000000)
    m.call(PSYMS['rc_first'], count=40000000)
    expect([e[0] for e in pod_recent.parse(m.fs[RECENT])] == [pod_recent.identity('Dark B'), pod_recent.identity('Dark A')], 'both Home timers retain dark album transitions')
    expect(not m.props.get((m.widgets['pod_shelf'], 'visible')), 'the shelf remains unchanged while dark')
    m.screen(True); m.call(PSYMS['mb_tick'], count=40000000)
    expect(m.props.get((m.widgets['pod_shelf'], 'visible')) == 1, 'minibar wake actually shows the refreshed shelf')
    e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
    m.texts.clear(); m.call(PSYMS['rc_on_paint'], a0=0, a1=e, count=40000000)
    expect([s for s, _ in m.texts if s in ('Dark A', 'Dark B')] == ['Dark B', 'Dark A'], 'the shelf paints both dark transitions in order')
    m.call(PSYMS['mb_tick'], count=40000000)
    expect(not any(c[0] == 'widget_invalidate_force' and c[1] == m.widgets['pod_shelf'] for c in m.calls), 'a second lit tick does not refresh the shelf again')

    # ------------------------------------------------------------------ recording from the places that see the playing track
    m = minibar.BM(); m.watch[PSYMS['recent_refresh']] = 'recent_refresh'; m.screen(False)
    m.track(album='Dark A'); m.start(); m.first()
    m.track(album='Dark B', path='/mnt/mmc/b/1.flac'); m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'dark minibar tick slows its timer')
    m.tick(); expect(not any(c[0] == 'timer_modify' for c in m.calls), 'unchanged dark minibar interval is not modified again')
    expect([e[0] for e in pod_recent.parse(m.fs.get(RECENT, b''))] == [pod_recent.identity('Dark B'), pod_recent.identity('Dark A')], 'minibar records both dark album transitions')
    expect(not any(c[0].startswith('widget_') or c[0] == 'recent_refresh' for c in m.calls), 'dark minibar tick does no visual work')
    m.screen(True); m.tick()
    expect(('timer_modify', 0x777, 500) in m.calls, 'lit minibar tick restores its timer')
    expect('recent_refresh' in m.names(), 'first lit minibar tick refreshes the shelf')
    m.screen(False); m.timer_modify_fail = True; m.tick(); m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'failed minibar retime is retried')
    m.timer_modify_fail = False; m.tick(); m.tick()
    expect(not any(c[0] == 'timer_modify' for c in m.calls), 'successful minibar retry is remembered')
    m.start(); m.first(); m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'a replacement minibar retimes its fresh timer')
    m.call(PSYMS['mb_on_destroy'], a0=minibar.WIN); m.screen(False); m.tick()
    expect(not m.calls, 'a stray dark minibar tick after destroy does nothing')

    m = covered(ST(ents(3), start=False)); m.screen(False); m.start(); m.first()
    expect(m.timers[-1:] == [(PSYMS['rc_dark'], 1000)] and 'widget_load_image' not in m.names(), 'dark shelf uses a one-second wake check and does not decode')
    r = m.call(PSYMS['rc_dark'], count=40000000)
    expect(r == 0 and m.timers[-1:] == [(PSYMS['rc_dark'], 1000)] and 'widget_load_image' not in m.names(), 'each dark shelf check rearms once at one second')
    m.screen(True); m.call(PSYMS['rc_dark'], count=40000000)
    expect('widget_load_image' in m.names(), 'the first lit shelf check resumes decoding')
    ended = False
    for _ in range(10):
        if m.tick() != O['RET_REPEAT']:
            ended = True; break
    expect(ended and not any(c[0] == 'timer_add' for c in m.calls), 'the resumed shelf loader terminates when covers are complete')
    m.fire(EVT_DESTROY); m.screen(False); m.call(PSYMS['rc_dark'], count=40000000)
    expect(not m.calls, 'a stray dark shelf check after destroy does nothing')
    m = covered(ST(ents(3), start=False)); m.start(); m.first(); m.screen(False)
    r = m.tick()
    expect(r == 0 and [c for c in m.calls if c[0] == 'timer_add'] == [('timer_add', PSYMS['rc_dark'], 1000)] and 'widget_load_image' not in m.names(),
           'a lit repeating loader entering darkness retires and arms exactly one slow check')

    m = minibar.BM(); m.watch[PSYMS['recent_refresh']] = 'recent_refresh'
    m.status = 2; m.track(title='Blue in Green', artist='Miles Davis', album='Kind of Blue'); m.cover('Miles Davis', 'Kind of Blue')
    m.start(); m.first()
    expect(pod_recent.parse(m.fs.get(RECENT, b'')) == [entry('Miles Davis', 'Kind of Blue', '/mnt/mmc/a/1.flac')] and 'recent_refresh' in m.names(),
           'the mini bar\'s first work records the playing album, and tells the shelf')
    m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] in ('open', 'write', 'rename', 'read', 'fsync')] and 'recent_refresh' not in m.names(), 'the next tick on the same album: no file call, no refresh')
    m.track(title='So What', artist='Miles Davis', album='Kind of Blue', path='/mnt/mmc/a/2.flac', name='2.flac'); m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] in ('open', 'write', 'rename')] and 'recent_refresh' not in m.names(), 'another track of the same album: still nothing')
    m.track(title='Roygbiv', artist='Boards of Canada', album='Music Has the Right to Children', path='/mnt/mmc/b/1.flac', name='1.flac'); m.calls = []; m.tick()
    got = pod_recent.parse(m.fs[RECENT])
    expect([e[0] for e in got] == [pod_recent.identity('Music Has the Right to Children'), pod_recent.identity('Kind of Blue')] and m.names().count('recent_refresh') == 1,
           'another album: it goes in front, one write, the shelf is told once')
    m.track(title='x', artist='Y', album='', path='/mnt/mmc/c/x.flac', name='x.flac'); m.calls = []; m.tick()
    expect(len(pod_recent.parse(m.fs[RECENT])) == 2 and not [c for c in m.calls if c[0] in ('open', 'write', 'rename')] and 'recent_refresh' not in m.names(), 'an untagged album is not recorded')
    m.play_pos = -1; m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] in ('open', 'write', 'rename')] and 'recent_refresh' not in m.names(), 'nothing playing: nothing recorded')
    m = minibar.BM(); m.status = 2; m.track(album='Kind of Blue', artist='Miles Davis'); m.start(); m.first()
    expect(RECENT in m.fs, 'a menu without a shelf (no shelf widgets) records all the same')
    # Now Playing's tick
    m = nowplaying.NowMachine(); m.page()
    t = m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/a/1.flac', title='Blue in Green', name='1.flac'); m.play([t], 0)
    m.init()
    expect(pod_recent.parse(m.fs.get(RECENT, b'')) == [entry('Miles Davis', 'Kind of Blue', '/mnt/mmc/a/1.flac')], 'Now Playing\'s start records the playing album')
    m.tick()
    expect(not [c for c in m.calls if c[0] in ('open', 'write', 'rename')], 'its next tick on the same album: no file call')
    t2 = m.record(album='Homogenic', artist='Björk', path='/mnt/mmc/b/1.flac', title='Hunter', name='1.flac'); m.play([t2], 0)
    m.screen(False)
    m.tick()
    expect([e[0] for e in pod_recent.parse(m.fs[RECENT])] == [pod_recent.identity('Homogenic'), pod_recent.identity('Kind of Blue')], 'a track of another album: recorded on the tick, in front')
    t3 = m.record(album='', artist='Björk', path='/mnt/mmc/b/2.flac', title='Untagged', name='2.flac'); m.play([t3], 0); m.tick()
    expect(len(pod_recent.parse(m.fs[RECENT])) == 2, 'an untagged album is not recorded')
    m.play([], 0); m.play_pos = -1; m.tick()
    expect(len(pod_recent.parse(m.fs[RECENT])) == 2, 'nothing playing: nothing recorded')

    # ------------------------------------------------------------------ the album's identity: the stock list's (getAllAlbum groups by album title alone, NOCASE)
    m = plain_machine()
    comp = [m.record(album='Now That\'s What I Call Music', artist=f'Artist {i}', path=f'/mnt/mmc/comp/{i}.flac', title=f'Song {i}', name=f'{i}.flac') for i in range(5)]
    n_ = []
    for t in comp: n_.append(m.call(PSYMS['recent_note'], a0=t, count=3000000)); n_.append(len([c for c in m.calls if c[0] == 'rename']))
    got = pod_recent.parse(m.fs[RECENT])
    expect(len(got) == 1 and n_ == [1, 1, 0, 0, 0, 0, 0, 0, 0, 0], f'a compilation: 5 tracks with 5 different artists are one shelf entry and ONE file write ({n_})')
    expect(got[0][0] == pod_recent.identity('Now That\'s What I Call Music') and got[0][4] == 'Artist 0', 'its identity is the title\'s, the first track gave the artist')
    m.calls = []
    t = m.record(album='NOW THAT\'S WHAT I CALL MUSIC', artist='Someone', path='/other/1.flac', title='x', name='1.flac')
    expect(m.call(PSYMS['recent_note'], a0=t, count=3000000) == 0 and m.calls == [], 'the same title in another case is the same album (SQLite NOCASE, as the stock list groups it): nothing happens')
    other = m.record(album='Greatest Hits', artist='A', path='/a/gh/1.flac', title='x', name='1.flac'); same = m.record(album='Greatest Hits', artist='B', path='/b/gh/1.flac', title='x', name='1.flac')
    m.call(PSYMS['recent_note'], a0=other, count=3000000)
    expect(m.call(PSYMS['recent_note'], a0=same, count=3000000) == 0 and len(pod_recent.parse(m.fs[RECENT])) == 2,
           'two albums of one title in different folders: the stock list has ONE row for both (group by album), so the shelf has one entry too')
    m.call(PSYMS['recent_note'], a0=m.record(album='Greatest Hits 2', artist='A', path='/a/gh2/1.flac', title='x', name='1.flac'), count=3000000)
    expect(len(pod_recent.parse(m.fs[RECENT])) == 3, 'a different title is another album')
    # the old file format is not read
    m = plain_machine(); m.fs[RECENT] = b'M1R1\n' + b'0000abcd\tAlbum\tArtist\t/a\n'
    m.call(PSYMS['recent_note'], a0=m.record(album='X', artist='Y', path='/p', title='t', name='n'), count=3000000)
    expect(len(pod_recent.parse(m.fs[RECENT])) == 1, 'an M1R1 file reads as empty: the list starts again')

    # ------------------------------------------------------------------ the cover key from the stock album row: when the album list is loaded
    def row_machine(n=3, setting=None):
        """Three recorded albums whose tracks' artists are not the album rows' artists; the covers are the rows' cache files."""
        m = ST(ents(n), start=False)
        m.clock = 1000
        for i in range(n): m.cover('Various Artists', ALBUMS[i][1], rgb=((200, 40, 40), (40, 200, 90), (40, 90, 220))[i])
        library(m, rows=[(ALBUMS[i][1], 'Various Artists', f'/mnt/mmc/v/{i}/1.flac') for i in range(n)])
        return m
    def loads(m): return len([c for c in m.calls if c[0] == 'loadLocalClassList'])
    m = row_machine(); calls = m.start()
    expect(loads(m) == 0 and not [c for c in calls if c[0] == 'loadLocalClassList'], 'start loads no album list')
    m.first(); a = list(m.calls)
    expect(not [c for c in a if c[0] == 'loadLocalClassList'], 'nor does the first one-shot')
    # the tracks' own keys have no cache file: the placeholder; the tick order and the files
    m.decode_all()
    expect(len(m.bitmaps) == 1 and not [u_ for u_ in m.loads if u_.startswith('file://')], 'unresolved albums have no cover under the tracks\' keys: the placeholder disc (one bitmap, shared), no list load for them yet')
    m.clock = 1000 + O['RC_RESOLVE_MS'] - 1; m.calls = []; m.fire(EVT_FG)
    expect(loads(m) == 0 and not [c for c in m.calls if c[0] == 'loadLocalClassList'], 'to-foreground before RC_RESOLVE_MS after the menu opened (the boot window): no album list')
    m.clock = 1000 + O['RC_RESOLVE_MS']; m.calls = []; m.fire(EVT_FG)
    names = m.names()
    expect(names.count('loadLocalClassList') == 1 and names.count('deque_destroy') == 1, f'later, ONE album list load, released at once ({names.count("loadLocalClassList")})')
    got = pod_recent.parse(m.fs[RECENT])
    expect([e[1] for e in got] == [album_key('Various Artists', ALBUMS[0][1])] + [e[1] for e in ents(3)[1:]] and [e[2] for e in got] == [1, 0, 0] and got[0][4] == 'Various Artists',
           f'one entry (the first) took the album row\'s cover key and artist, and the file was written once ({[(hex(e[1]), e[2]) for e in got]})')
    expect(m.names().count('rename') == 1, 'one write')
    m.timers = []; m.calls = []
    m.tick()
    expect(('widget_load_image', 'file://' + art_file(album_key('Various Artists', ALBUMS[0][1]))) in m.calls, 'the tile is made again from the row\'s cache file')
    for _ in range(2):
        m.clock += 10; m.calls = []; m.fire(EVT_FG)
    got = pod_recent.parse(m.fs[RECENT])
    expect([e[2] for e in got] == [1, 1, 1], 'one more album per to-foreground: all three resolved after three')
    m.clock += 10; m.calls = []; m.fire(EVT_FG)
    expect('loadLocalClassList' not in m.names(), 'a fully resolved list never loads the album list again')
    # recent_rekey (the Home cover build's album list, patch/homecover.c): a key resolved under an earlier row rule (res 1, another artist) names a file
    # the build never makes; the list's row gives every entry its key again, the file is written once, the tile tries the row's file
    stale = [(e[0], album_key('Old Row', ALBUMS[i][1]), 1) + e[3:] for i, e in enumerate(ents(3))]
    m = row_machine(); m.fs[RECENT] = pod_recent.dump(stale); m.start(); m.first(); m.decode_all()
    expect(not [u_ for u_ in m.loads if u_.startswith('file://')], 'a stale resolved key finds no cache file: the placeholder')
    rows = m.new_deque(m.showlist); m.calls = []
    m.call(PSYMS['recent_rekey'], a0=rows, a1=0, count=40000000)
    got = pod_recent.parse(m.fs[RECENT])
    expect([e[1] for e in got] == [album_key('Various Artists', ALBUMS[i][1]) for i in range(3)] and all(e[2] == 1 and e[4] == 'Various Artists' for e in got)
           and m.names().count('rename') == 1, f'recent_rekey: every entry takes its row\'s key and artist, one write ({[hex(e[1]) for e in got]})')
    m.loads = []; m.decode_all()
    expect(all('file://' + art_file(album_key('Various Artists', ALBUMS[i][1])) in m.loads for i in range(3)), f'the tiles are made again from the rows\' cache files ({m.loads})')
    m.calls = []; m.call(PSYMS['recent_rekey'], a0=rows, a1=0, count=40000000)
    expect('rename' not in m.names(), 'keys that already match: nothing written')
    m.call(PSYMS['recent_rekey'], a0=0, a1=0, count=400000)
    # an album the library does not list: asked once, not again
    m = row_machine(); library(m, rows=[('Other', 'Y', '/o/1.flac')]); m.start(); m.clock = 1000 + O['RC_RESOLVE_MS']
    ls = []
    for _ in range(6):
        m.calls = []; m.fire(EVT_FG); ls.append(m.names().count('loadLocalClassList'))
    expect(ls == [1, 1, 1, 0, 0, 0] and all(e[2] == 0 for e in pod_recent.parse(m.fs[RECENT])), f'albums the library lacks are asked once each (3 loads, then none) and stay unresolved ({ls})')
    # the tap: the resolved cover key is the first match, a track key still works for an unresolved entry
    m = row_machine(); m.start(); m.clock = 1000 + O['RC_RESOLVE_MS']; m.fire(EVT_FG); m.decode_all(); m.calls = []
    m.tap(cx(0), sy(SH_TOP + 48))
    expect(m.opened() == [(O['CLASS_ALBUMS'], 0)], f'a tap opens the row the resolved key names ({m.opened()})')
    # a track key with a cache file (the track's artist is the row's): used while unresolved
    m = ST(ents(1), start=False); m.cover(*ALBUMS[0][:2], rgb=(9, 99, 199)); m.start(); m.decode_all()
    expect('file://' + art_file(album_key(*ALBUMS[0][:2])) in m.loads, f'an unresolved entry falls back to the track key\'s cache file ({m.loads})')
    # Now Playing's tick records the album and runs no stock query: the page under it (a stock song list: a playlist, Songs, Favourites) draws
    # its rows from *pdeq_showlist and plays from it, and the album list would replace it (folder icons, the albums played on a tap)
    m = nowplaying.NowMachine(); m.page()
    m.showlist = [m.record(album='Kind of Blue', artist='Various Artists', path='/mnt/mmc/v/1.flac', rid=1)]
    seen = []
    t = m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/a/1.flac', title='Blue in Green', name='1.flac'); m.play([t], 0)
    m.init(); seen += m.names()
    got = pod_recent.parse(m.fs[RECENT])
    expect(len(got) == 1 and got[0][2] == 0 and got[0][1] == album_key('Miles Davis', 'Kind of Blue') and got[0][4] == 'Miles Davis',
           'Now Playing\'s start records the album under the track\'s own key, unresolved')
    m.tick(); seen += m.names()
    t2 = m.record(album='Kind of Blue', artist='Somebody Else', path='/mnt/mmc/a/2.flac', title='So What', name='2.flac'); m.play([t2], 0); m.tick(); seen += m.names()
    expect(len(pod_recent.parse(m.fs[RECENT])) == 1, 'another track of the album (another artist): no new entry')
    t3 = m.record(album='Homogenic', artist='Björk', path='/mnt/mmc/b/1.flac', title='Hunter', name='1.flac'); m.play([t3], 0); m.tick(); seen += m.names()
    expect(len(pod_recent.parse(m.fs[RECENT])) == 2 and not {'loadLocalClassList', 'loadAlbumList', 'getAllAlbum'} & set(seen),
           'a new front album is recorded, and neither the start nor any tick loads a stock list')
    # the cost: the payload's own instructions of a to-foreground that resolves one entry against a library of n albums (the stock query itself is not emulated)
    cost = {}
    for n in (100, 1000, 4000):
        m = ST([entry('A', 'Last One')], start=False).count(); m.clock = 1000
        library(m, rows=[(f'Album {i}', 'V', f'/m/{i}.flac') for i in range(n - 1)] + [('Last One', 'V', '/m/z.flac')])
        m.start(); m.clock = 1000 + O['RC_RESOLVE_MS']; m.fire(EVT_FG); cost[n] = m.icount
        expect(n != 4000 or pod_recent.parse(m.fs[RECENT])[0][1] == album_key('V', 'Last One'), 'the last row of 4000 albums resolves')
    print(f'  a to-foreground resolving a cover key, payload instructions for the worst case (the last row): {cost} (+ the stock getAllAlbum query and the deque copy, not emulated)')
    expect(cost[4000] < 20000000 and cost[1000] < cost[4000], f'the payload\'s part of an album-list load is {cost[4000]} instructions for 4000 albums')


SECTIONS = [file_and_layout_tests, grid_and_tap_tests, refresh_and_fallback_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

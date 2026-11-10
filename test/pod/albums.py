"""Albums: the menu row, the page's structure (a stock list_view > scroll_view holding the one content view that paints the albums), the grid
(layout, visible cells, tiles, the window moved by the scroll offset, taps), the title ellipsis, missing cache files, a large library, the list
mode of the same page (rows, covers, two text styles, pressed row, taps), the loader that decodes nothing while the scroll_view moves, the in-place
mode toggle with its persistence, hit tests on the page, and the touch with demo's own scroll_view code (drag, fling, tap, catch a coasting list)."""
import os, struct
import mod_icons
from unicorn import mips_const
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

SCREEN_Y0 = 30 + 50     # the grid view on the screen: under the 30 px status bar and the 50 px navbar
ALBUMS_FILE, ALBUMS_TMP = '/mnt/data/m1plus/albums-view', '/mnt/data/m1plus/albums-view.tmp'
COVER, GAP, MARGIN, COLS = O['GRID_COVER'], O['GRID_GAP'], O['GRID_MARGIN'], O['GRID_COLS']
TGAP, THEIGHT, VIEW_H, TILES = O['GRID_TITLE_GAP'], O['GRID_TITLE_H'], O['GRID_VIEW_H'], O['GRID_TILES']
RGAP, SUBH = O['GRID_ROW_GAP'], O['GRID_SUB_H']
TOP = O['SG_TITLE_H']       # the large title's block: the rows start this far down the content (a page offset of TOP puts the first row at the top of the window)
CELL = COVER + TGAP + THEIGHT + SUBH       # a tile: the cover, the album, the artist
PITCH = CELL + RGAP
CPITCH = COVER + GAP
ART = O['ART_SIZE']
SVW = 310                 # the scroll_view's width: 320 less the scroll bar's 10 px strip (the content view stays 320 wide: the list_view layouter gives it the list_view's width)
CW = 320                  # the content view's width (the list_view layouter gives a child the list_view's width) and so the fills'
TAP = O['SC_DRAG_PX']     # a release closer than this to the press on both axes is a tap (AL_TAP_PX): the scroll_view's own drag threshold
SC_YOFF, SC_VH = O['SC_YOFF'], 0x7c   # the scroll_view's yoffset and virtual_h (its widget_t fields)
ROW, LART, LAX, LAY = O['LIST_ROW_H'], O['LIST_ART'], O['LIST_ART_X'], O['LIST_ART_Y']
TX, TW, TY, TH, SY, SH = O['LIST_TEXT_X'], O['LIST_TEXT_W_CHEV'], O['LIST_TITLE_Y'], O['LIST_TITLE_H'], O['LIST_SUB_Y'], O['LIST_SUB_H']
CHEV_PX = (10, 16)   # POD_CHEV_W x POD_CHEV_H (patch/common.h)
HX, HW = TX, O['LIST_HAIR_END'] - TX   # the hairline: from the text to LIST_HAIR_END


class Images(dict):
    """widget_load_image's pictures: the stock placeholder, and for any cache file a flat side x side cover
    whose colour depends on the album number (made when asked, so a library of thousands costs nothing). The
    pictures are small: the box filter's work grows with them, and so does the emulation's time."""
    def get(self, url, default=None):
        if url in self: return dict.get(self, url)
        if url.startswith('file://') and url[7:] in self.owner.cache_index:
            i, side = self.owner.cache_index[url[7:]], self.owner.side
            return side, side, bytes((i * 7 % 256, i * 13 % 256, i * 29 % 256, 255)) * (side * side)
        return default


def colour(i):
    return 0xff000000 | (i * 7 % 256) | (i * 13 % 256) << 8 | (i * 29 % 256) << 16


def albums_world(m, n=30, cached=True, missing=(), empty=(), title=lambda i: f'Album {i}', side=24, sort='album'):
    """The page's world on any machine: its named widgets (plain ones), n albums in the stock list and, unless cached is False or the album
    is in missing / empty (the zero-length "no art" marker), a cache file with a cover. sort: the order setting
    (the machines default to the stock order, 'album', which the layout tests index by album number; 'artist' is the
    setting's own default, tested in the sort tests)."""
    if sort == 'album': m.fs[SORT_FILE] = b'0\n'
    m.load_image = 0
    for w in (*VS_WIDGETS, 'btn_return', 'btn_backtoplayer', 'btn_coverflow', 'view_grid', 'label_status', 'label_row_title', 'label_row_sub',
              'label_grid_title', 'label_grid_sub', 'label_title', 'al_title', 'img_nb_fade'): Machine.widget(m, w)
    m.setword(m.widgets['label_title'] + 8, O['NAV_CF_X'] - O['NAV_TITLE_X']); m.setword(m.widgets['al_title'] + 8, O['SG_TITLE_W'])   # the labels' widths (az_fit cuts to them)
    m.canvas = m.alloc(0x80)                                # a canvas whose origin (canvas_t @4) the paint moves
    m.oy_canvas = m.canvas
    m.showlist = [m.record(album=title(i), artist=f'Artist {i}', path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i in range(n)]
    m.cache_index, m.side = {}, side
    m.images = Images(); m.images.owner = m
    m.images['p_default'] = (24, 24, bytes((0x40, 0x40, 0x40, 255)) * (24 * 24))
    for i in range(n):
        p = art_file(fnv(fnv(O['FNV_SEED'], f'Artist {i}'), title(i)) or 1)
        if cached and i not in missing:
            m.present.add(p); m.files[p] = 0 if i in empty else 4096
            if i not in empty: m.cache_index[p] = i


AZ_WIDGETS = ('label_hdr', 'label_rail', 'label_rail_on', 'sg_rail', 'sg_bubble', 'sg_bubble_letter')   # the list mode's A-Z furniture (patch/azlist.c), in the page's asset


def albums_machine(n=30, az=False, cls=Machine, **world):
    """A machine (cls) with the page's widgets (see albums_world) and the page as widget structs, for widget_to_local. az: the list mode's section letters, rail and bubble exist too."""
    m = cls()
    albums_world(m, n, **world)
    if az:
        for w in AZ_WIDGETS: Machine.widget(m, w)
    # the page as widget structs, for widget_to_local (stock's own code, which walks the parents and adds a scroll_view's offset through its
    # vtable): window (30 px under the top: the status bar) > list_view (50: under the navbar) > scroll_view (a real one's fields: demo's vtable, the
    # offsets at 0x7c / 0x84, the pressed / dragged bytes at 0xa0 / 0xa1, the animator at 0xe8) > view_grid (the content, as high as the payload sets it)
    win, lv, sv = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180)
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 0x70, SV_VT); m.setword(sv + 8, SVW)
    m.widgets['albums_scrollview'] = sv
    view = m.widgets['view_grid']
    for off, v in ((4, 0), (8, CW), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
    m.mem_geometry, m.live_scroll = True, frozenset({sv})   # widget_resize writes the widget_t; the prop setters store virtual_h / yoffset in the scroll_view
    m.win = win
    if az:   # the rail, a widget struct of its own (outside the scroll_view) the payload moves and sizes
        rail = m.widgets['sg_rail']; m.u.mem_write(rail, bytes(0x80))
        for off, v in ((0, O['SG_RAIL_X']), (4, 50), (8, O['SG_RAIL_W']), (0xc, VIEW_H), (0x44, win)): m.setword(rail + off, v)
        m.live_scroll, m.rail = frozenset({sv, rail}), rail
    return m


VS_SORTS = O['VS_SORTS']


def glyph(m):
    """The "..." card's view row glyph: the view a tap switches to (pod_nav_grid / pod_nav_list name them as the old toggle did)."""
    return 'pod_nav_grid' if m.props.get((m.widgets['vs_tick5'], 'visible'), 0) else 'pod_nav_list'   # (List ticked: the page is a list, a tap on Grid switches)


def page_mode(m):
    """1 if the open page is in list mode (the view row offers the grid), else 0."""
    return 1 if glyph(m) == 'pod_nav_grid' else 0


def open_grid(m, count=20000000):
    m.call(PSYMS['albums_open'], count=count)
    return list(m.calls)




def scroll_of(m):
    """The page's scroll offset: the scroll_view's yoffset."""
    return m.s32(m.widgets['albums_scrollview'] + SC_YOFF)


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts) of that frame. The canvas is where the stock scroll_view leaves it for its child: the
    origin (canvas_t @4) is the window's top (80) less the offset; m.oy_after is the origin after the paint, m.draw_oy the one every cover was drawn at."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - scroll_of(m)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.measures.clear(); m.fills.clear(); m.text_styles.clear(); m.draw_oy.clear()
    m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
    m.oy_after = m.s32(m.canvas + O['CANVAS_OY'])
    m.chevs = [b for b in m.blits if m.bitmaps[b[0]][1:] == CHEV_PX]   # the list rows' chevron (pod_make_chevron) is drawn with the covers: set apart
    return [b for b in m.blits if b not in m.chevs], list(m.texts)


def nbmp(m):
    """The live bitmaps but the chevron the list's rows share."""
    return sum(1 for v in m.bitmaps.values() if v[1:] != CHEV_PX)


def content_h(m):
    """The content view's height: what the payload gave it with widget_resize."""
    return m.s32(m.widgets['view_grid'] + 0xc)


def scroll_to(m, v):
    """Move the scroll_view's offset to v (clamped to [0, virtual_h - 400] as its clamp does) and tell the page, as the stock setter's EVT_SCROLL does."""
    sv = m.widgets['albums_scrollview']
    v = max(0, min(v, max(0, m.s32(sv + SC_VH) - VIEW_H)))
    m.setword(sv + SC_YOFF, v)
    fn, ctx = m.bound[(sv, O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=40000000)
    return list(m.calls)


def tick(m):
    """The loader's 16 ms timer fires once: the calls it made."""
    m.call(PSYMS['al_on_load'], count=40000000)
    return list(m.calls)


def settle(m, limit=60):
    """Fire the loader's timer until it does not re-arm itself (every cover in its window loaded), then paint; that frame."""
    for _ in range(limit):
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in tick(m)):
            return paint(m)
    raise AssertionError('the grid never finished loading')


def reference(scroll, n):
    """Independent model of what a frame at `scroll` shows: [(album, (src, dst) of the cover or None, title rect or
    None, artist rect or None)] for the cells that touch the view. Brute force over every album unless n is large
    (then a window of rows)."""
    out = []
    scroll -= TOP
    first = max(0, (scroll - RGAP - CELL) // PITCH - 1) * COLS
    for a in range(first, min(n, first + 40) if n > 200 else n):
        x, top = MARGIN + (a % COLS) * CPITCH, RGAP + (a // COLS) * PITCH - scroll
        if top >= VIEW_H or top + CELL <= 0: continue
        cut_top, cut_bottom = max(0, -top), min(COVER, VIEW_H - top)
        cover = ((0, cut_top, COVER, cut_bottom - cut_top), (x, top + cut_top, COVER, cut_bottom - cut_top)) if cut_bottom > cut_top else None
        ty = top + COVER + TGAP
        title, sub = (x, ty, COVER, THEIGHT), (x, ty + THEIGHT, COVER, SUBH)   # every cell's texts: the scroll_view's clip cuts them
        out.append((a, cover, title, sub))
    return out


def list_ref(scroll, n):
    """[(album, cover (src, dst) or None, title rect or None, artist rect or None, hairline y or None)] of a list frame."""
    out = []
    scroll -= TOP
    for a in range(n):
        top = a * ROW - scroll
        if top >= VIEW_H or top + ROW <= 0: continue
        ct, cb = max(0, -(top + LAY)), min(LART, VIEW_H - (top + LAY))
        cover = ((0, ct, LART, cb - ct), (LAX, top + LAY + ct, LART, cb - ct)) if cb > ct else None
        ok = lambda y, h: (TX, y, TW, h)   # every row's texts: the scroll_view's clip cuts them
        out.append((a, cover, ok(top + TY, TH), ok(top + SY, SH), top + ROW - 1 if 0 <= top + ROW - 1 < VIEW_H else None))
    return out


def grid_texts(m, texts):
    """The frame's texts split by style: ({album text: rect}, {artist text: rect}) of the grid."""
    t = {x[0]: x[1] for x, sty in zip(texts, m.text_styles) if sty == 'label_grid_title'}
    s = {x[0]: x[1] for x, sty in zip(texts, m.text_styles) if sty == 'label_grid_sub'}
    return t, s


def dsts(blits): return sorted(b[2] for b in blits)
def want_dsts(ref): return sorted(c[1][1] for c in ref if c[1])


HANDLER = {'down': 'al_on_down', 'up': 'al_on_up', 'abort': 'al_on_abort'}


def gesture(m, events):
    """Pointer events [(kind, x, window y, ms)] delivered one after the other to the content view's handlers, as the stock scroll_view passes them down
    (a 'move' is the scroll_view's: the content view has no handler for it); every call they made. y is where the finger is on the 400 px window."""
    calls = []
    for kind, x, y, t in events:
        if kind in HANDLER: m.touch(kind, x, SCREEN_Y0 + y, t, fn=HANDLER[kind]); calls += m.calls
    m.calls = calls
    return calls


def tap_at(m, x, y, t0=1000):
    return gesture(m, [('down', x, y, t0), ('up', x, y, t0 + 80)])


def list_machine(n=30, **kw):
    m = albums_machine(n, **kw); m.fs[ALBUMS_FILE] = b'0\n'
    open_grid(m)
    return m


def file_loads(m): return [u for u in m.loads if u.startswith('file://')]
def armed(calls): return any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in calls)


def run_loader(m):
    """Ticks until idle; the albums decoded, in order, and the most one tick decoded."""
    start, per_tick = len(m.loads), 0
    for _ in range(60):
        n0 = len(m.loads)
        calls = tick(m)
        per_tick = max(per_tick, len([u for u in m.loads[n0:] if u.startswith('file://')]))
        if not armed(calls): break
    return [m.cache_index[u[7:]] for u in m.loads[start:] if u.startswith('file://')], per_tick


def menu_row(page): return next(i for i, r in enumerate(page.rows) if r.label == 'Albums')


pulldown = sibling('pulldown')
SLOT, KILL_SD = pod.SCROLL_SLOT, '/mnt/mmc/m1plus-off'


class SA(pulldown.SM):
    """The Albums page on demo's own widget code: window > list_view > scroll_view > view_grid as real widget structs, demo's list_view layouter
    (window_manager_check_and_layout), scroll_view (drag, velocity, the fling's animator, the clamp) and pointer path (widget_on_pointer_down /
    _move / _up, hit testing, the abort a drag sends the children), the list gesture hook of patch/scroll.c in g_scroll_view_vtable (hook=False:
    the stock app), and the page's payload opened on it. Only the leaves are mocked: timers, animators (they never advance by themselves: the
    test ends one with finish_fling), the emitter (events reach the handlers the payload bound with widget_on). Window coordinates: the list
    starts 50 px down."""
    Y0 = 50
    DELIVER = True

    def __init__(self, n=300, mode='grid', hook=True, **world):
        super().__init__(True)
        albums_world(self, n, **world)
        self.handlers[0x742c90] = 'strcmp'      # the libc stubs the stock scroll_bar_is_mobile / scroll bar code call
        self.handlers[0x742850] = '__divdi3'
        self.u.mem_write(SLOT, struct.pack('<I', PSYMS['m1plus_scroll_event'] if hook else 0))
        if mode == 'list': self.fs[ALBUMS_FILE] = b'0\n'
        self.zv = self.alloc(0x80); self.u.mem_write(self.zv, bytes(0x80))     # a view's vtable: no entries (the stock defaults)
        self.root = self.win = self.widget(LI_VT, 0, 0, 320, 450)
        self.lv = self.widget(LV_VT, 0, self.Y0, 320, VIEW_H, self.root)
        # the widgets and sizes are the BUILT ASSET's (m1plus_albums.bin): a scroll bar only if the asset has one, the scroll_view as wide as it says
        tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin'), 'rb').read())
        a_sv, a_bar = tree.find('albums_scrollview'), tree.find('scroll_bar_m')
        sw = a_sv.w
        self.sv = sv = self.widget(SV_VT, 0, 0, sw, VIEW_H, self.lv, emitter=True)
        self.view = self.widget(self.zv, 0, 0, sw, VIEW_H, sv, emitter=True)
        self.bar = self.widget(0x97a1f8, a_bar.x, 0, a_bar.w, VIEW_H, self.lv) if a_bar else 0      # g_scroll_bar_mobile_vtable
        self.kids(self.root, [self.lv]); self.kids(self.lv, [sv] + ([self.bar] if a_bar else [])); self.kids(sv, [self.view])
        self.setword(self.lv + 0x88, self.bar)                                  # list_view: its scroll bar (0 when the asset has none)
        for off, v in ((0x78, sw), (0x7c, VIEW_H), (0xec, 0x611450), (0xf0, pulldown.LV_HOOK), (0xf4, pulldown.PAINT_HOOK)): self.setword(sv + off, v)
        # (xslidable / yslidable / snap are NOT set here: scroll_view_create leaves them 0 and only the list_view layouter sets them, from a mobile scroll bar)
        speed = self.word(0x759814); self.setword(sv + 0x88, speed); self.setword(sv + 0x8c, speed)
        for off, v in ((0x7c, 64), (0x84, sv)): self.setword(self.lv + off, v)  # list_view: default_item_height, its scroll_view
        lay = self.alloc(0x1c); self.u.mem_write(lay, bytes(0x1c)); self.setword(lay + 0xc, pulldown.LAYOUTER_VT); self.u.mem_write(lay + 0x1a, bytes([4]))
        self.setword(sv + 0x64, lay)                                            # "list_view(m=0,s=0)", as the layout hook installs it
        self.props[(sv, 'h')] = VIEW_H
        self.widgets['view_grid'], self.widgets['albums_scrollview'] = self.view, sv
        self.wm = self.widget(LI_VT, 0, 0, 320, 480); self.kids(self.wm, [self.root])
        self.window = self.root

    def open(self):
        self.call(PSYMS['albums_open'], count=40000000)
        opened = list(self.calls)
        self.mark(); self.relayout()      # the main loop lays the window out before its first paint
        return opened

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == '__divdi3':   # libgcc: signed 64 bit division (a1:a0 / a3:a2) -> v1:v0 (the scroll bar's value maths)
            r = [u.reg_read(x) for x in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)]
            s64 = lambda lo, hi: struct.unpack('<q', struct.pack('<II', lo, hi))[0]
            n, d = s64(r[0], r[1]), s64(r[2], r[3])
            q = int(n / d) if d else 0
            lo, hi = struct.unpack('<II', struct.pack('<q', q))
            u.reg_write(UC_MIPS_REG_V0, lo); u.reg_write(mips_const.UC_MIPS_REG_V1, hi); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        super()._hook(u, address, size, _)

    def leaf(self, name, a0, a1, a2, a3, sp):
        if name == 'widget_invalidate_force': self.calls.append(('widget_invalidate_force', a0))
        return super().leaf(name, a0, a1, a2, a3, sp)

    def play(self, steps):
        """steps: (d|m|u, x, y in the window[, ms since the last event]); every call they made."""
        self.calls_all = []
        for s in steps: self.pointer(*s)
        return self.calls_all

    def opened(self):
        """The albums the stock album page was asked for, by row: [row]."""
        return [c[3] for c in self.calls_all if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']

    def off(self): return self.yoff()
    def pressed(self): return bool(self.u.mem_read(self.sv + 0xa0, 1)[0])
    def dragged(self): return bool(self.u.mem_read(self.sv + 0xa1, 1)[0])
    def fling_target(self):
        wa = self.wa()
        return self.anims[wa]['y1'] if wa else None

    def finish_fling(self):
        """The scroll animation ends: the offset is the target, then the animator's end handler runs (stock: wa cleared, the scroll end events)."""
        wa = self.wa()
        fn, ctx = self.end[wa]
        self.setword(self.sv + SC_YOFF, self.anims[wa]['y1'] & 0xffffffff)
        self.queue = []
        self.call(fn, a0=ctx, a1=0, count=8000000)
        self.calls_all = list(self.calls)
        self.deliver()
        return self.calls_all


def layout_tests(ctx):
    """1-6: the layout, the menu row, the open, the first frame, scrolling, the content and the loader."""
    expect, page = ctx.expect, ctx.page
    row = menu_row(page)
    expect(page.rows[row].action == pod_pages.ACT_ALBUMS, 'the menu\'s Albums row opens our page (ACT_ALBUMS)')
    on_row, rows0 = PSYMS['on_row'], PSYMS['pod_rows_0']

    # 1. Layout: two 144 px covers 8 px apart, centred (12 px margins); the view is the 400 px under the navbar; the
    #    ring holds every cell a frame can touch and its bitmaps stay under today's memory.
    expect((COLS, COVER, GAP, MARGIN, RGAP, TGAP, THEIGHT, SUBH, CELL, PITCH, TILES) == (2, 144, 8, 12, 10, 4, 22, 20, 190, 200, 12),
           'the grid is 2 columns of 144 px covers, 8 px apart, 12 px margins; a tile is 190 px (cover, 4, album 22, artist 20), rows 200 px apart')
    expect(COLS * COVER + (COLS - 1) * GAP + 2 * MARGIN == pod_ui.SCREEN_W, f'{COLS} covers + gutters + margins fill the 320 px width')
    expect((TILES + 1) * COVER * COVER * 4 <= 1100000,
           f'the tile ring ({TILES} x {COVER * COVER * 4} B = {TILES * COVER * COVER * 4} B, +1 placeholder = {(TILES + 1) * COVER * COVER * 4} B) stays within 1.1 MB')
    expect(VIEW_H == pod_ui.GRID_VIEW_H == pod_ui.CLIENT_H - pod_ui.NAVBAR_H, 'the grid view is the 400 px under the navbar')
    expect(TILES >= COLS * ((VIEW_H + CELL) // PITCH + 3) + 2, f'{TILES} tiles hold the {COLS * ((VIEW_H + CELL) // PITCH + 2)} cells a frame can touch, the next row and two of history')
    expect(TILES >= VIEW_H // ROW + 2 + 2 + 2, f'and the {VIEW_H // ROW + 2} rows of the list, the next two and two of history')
    expect(THEIGHT >= pod_ui.GRID_ALBUM_PX + 4 and SUBH >= pod_ui.GRID_ARTIST_PX + 4 and (O['NAV_VIEW_X'], O['NAV_VIEW_W']) == (pod_ui.NAV_VIEW_X, pod_ui.NAV_VIEW_W),
           'the album and artist lines fit their fonts; the toggle geometry is shared with the asset')
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin')
    tree = awtk_ui.parse(open(asset, 'rb').read())
    grid = tree.find('view_grid')
    expect(grid is not None and (grid.x, grid.y, grid.w, grid.h) == (0, 0, CW, VIEW_H) and grid.type == 'view',
           'the asset has one 310x400 view_grid at the top of the scroll_view (the payload sizes it to the content)')
    expect(all(grid.get(f'style:normal:{k}') == v for k, v in (('text_color', '#FFFFFF'), ('font_size', '16'),
                                                                 ('text_align_h', 'left'), ('bg_color', '#000000'))),
           'its style is the 16 px white title text on black (what widget_prepare_text_style reads)')
    expect(not [w for w in tree.walk() if w.type in ('list_item', 'slide_menu') or (w.type == 'image' and w.name not in ('img_nb_fade', 'al_spin') and not w.name.startswith('vs_'))],
           'no widget per album: the page is a navbar, a list, the fade under the bar, a status label and the loading spinner')
    bar = tree.find('scroll_bar_m')
    expect(bar is not None and bar.type == 'scroll_bar_m' and (bar.x, bar.w) == (SVW, 10) and bar in tree.find('albums_listview').children,
           'the list_view has the stock scroll_bar_m beside the scroll_view: the list_view layouter makes the scroll_view yslidable only for a mobile bar (scroll scenario: SA)')
    lv_, sv_ = tree.find('albums_listview'), tree.find('albums_scrollview')
    expect(lv_ is not None and sv_ is not None and lv_.type == 'list_view' and sv_.type == 'scroll_view' and sv_.children == [grid] and lv_.children[:1] == [sv_]
           and (lv_.x, lv_.y, lv_.w, lv_.h) == (0, pod_ui.NAVBAR_H, 320, VIEW_H) and (sv_.x, sv_.y, sv_.w, sv_.h) == (0, 0, SVW, VIEW_H),
           'the body is list_view > scroll_view (320x400 under the navbar, the scroll_view 310 wide beside the scroll_bar_m) > view_grid, the structure of the library lists')
    # ... with the stock library list's properties: album_page.bin's scroll_view and list_view (styles black, no border, the speed scales)
    stock_ui = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs/release/assets/default/raw/ui/album_page.bin'), 'rb').read())
    s_lv, s_sv = stock_ui.find('album_listview'), stock_ui.find('album_scrollview')
    expect(s_lv is not None and s_sv is not None and all(sv_.get(k) == s_sv.get(k) for k in ('xspeed_scale', 'yspeed_scale')) and s_sv.get('yspeed_scale') == '1'
           and all(lv_.get(k) == v for k, v in s_lv.props if k.startswith('style:')),
           'its scroll_view has the stock list\'s speed scales (1, 1) and its list_view the stock list\'s black / borderless styles')
    expect(tree.find('btn_albumview') is None, 'the grid / list toggle has left the navbar (it is the "..." card\'s last row)')
    cfb, more, nb = tree.find('btn_coverflow'), tree.find('btn_more'), tree.find('btn_backtoplayer')
    expect(tree.find('btn_search') is None, 'no Search button on the navbar: Search is the "..." card\'s first row')
    expect(all(b is not None and (b.y, b.w, b.h) == (0, O['NAV_VIEW_W'], O['NAV_H']) and b.get('style') == 'img_btn_style' for b in (cfb, more))
           and [(b.x, b.get('style:normal:icon'), b.get('style:pressed:icon')) for b in (cfb, more)]
           == [(168, 'pod_nav_coverflow', 'pod_nav_coverflow_down'), (214, 'pod_nav_moremid', 'pod_nav_moremid_down')]
           and more.x + more.w == nb.x == 260 and nb.get('style:normal:icon') == 'ah_nav_play',
           'the capsule is Cover Flow 168 (left cap), "..." 214 (middle; 46 x 50) and Now Playing 260 as its right cap')
    lbl = tree.find('label_title')
    expect(lbl.x == O['NAV_TITLE_X'] == 58 and lbl.x + lbl.w == O['NAV_CF_X'] == 168 and lbl.w == 110, 'the small title runs from x 58 to where the capsule begins (168): 110 px')
    btns = (cfb, more, nb)
    expect(not [1 for a in btns for b in btns if a is not b and a.x < b.x + b.w and b.x < a.x + a.w], 'no navbar button overlaps another')
    #     list mode: the two hidden text-style labels, the geometry the rows share with the library rows
    for nm, px, col in (('label_row_title', 21, '#FFFFFF'), ('label_row_sub', 18, '#AAAAAA')):
        w = tree.find(nm)
        expect(w is not None and w.type == 'label' and w.get('visible') == 'false' and w.get('sensitive') == 'false'
               and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == col and w.get('style:normal:text_align_h') == 'left',
               f'{nm}: a hidden, insensitive label whose style is {px} px {col} (what the list rows are drawn with)')
    for nm, px, col in (('label_grid_title', 18, '#FFFFFF'), ('label_grid_sub', 15, '#AAAAAA')):
        w = tree.find(nm)
        expect(w is not None and w.type == 'label' and w.get('visible') == 'false' and w.get('sensitive') == 'false'
               and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == col and w.get('style:normal:text_align_h') == 'left',
               f'{nm}: a hidden, insensitive label whose style is {px} px {col} (the grid\'s album / artist text)')
    expect(ROW == 64 and LAX == 10 and TX == LAX + LART + 12 and LAY + LART <= ROW - 1 and TX + O['LIST_TEXT_W'] + 12 == 320 and TX + TW == 278
           and TY + TH <= SY and SY + SH <= ROW - 1 and ROW == O['LIST_ROW_H'],
           'list rows: 64 px like the library rows, 52 px cover at (10, 4), text from 74 (12 px after the cover) to a 12 px right margin, two lines and a hairline fit')
    expect(O['LIST_HAIR'] == 0xff222222 and O['LIST_PRESS'] == 0xff343333, 'hairline #222222, pressed #333334 (the other lists\' colours; one blue level off #333333 so the accent can find a pressed row)')
    expect(not [w for w in tree.walk() if w.name in ('btn_stocklist',)] and O.get('NAV_LIST_X') is None, 'no trace of the stock-list toggle')
    imgs = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx')
    expect(all(os.path.isfile(os.path.join(imgs, f'pod_nav_{k}{s}.png')) for k in ('grid', 'list', 'coverflow', 'search', 'moremid') for s in ('', '_down')),
           'the capsule pieces and the toggle glyph images are in the tree')

    # 2. The menu row: the persisted mode, the default constant when there is none (or it is garbage); "0" is the list
    #    mode of the same page, "1" the grid; never a second window or the stock list.
    m = albums_machine(3)
    m.call(on_row, a0=rows0 + 12 * row, count=20000000)
    expect(('window_open', 'm1plus_albums') in m.calls and 'stock_resume' not in m.names() and page_mode(m) == (0 if O['ALBUMS_DEFAULT_GRID'] else 1),
           'with no setting the Albums row opens our page in the default mode')
    for data, want_list in ((b'1\n', 0), (b'0\n', 1), (b'x', 1 - O['ALBUMS_DEFAULT_GRID']), (b'', 1 - O['ALBUMS_DEFAULT_GRID']),
                           (b'0x', 1 - O['ALBUMS_DEFAULT_GRID']), (b'1x', 1 - O['ALBUMS_DEFAULT_GRID'])):
        m = albums_machine(3); m.fs[ALBUMS_FILE] = data
        calls = open_grid(m)
        expect(('window_open', 'm1plus_albums') in calls and 'stock_resume' not in m.names() and page_mode(m) == want_list,
               f'setting {data!r}: the Albums row opens our page in {"list" if want_list else "grid"} mode')
    #     a page that cannot open falls back to the stock Albums list through the Home dispatcher (Albums = id 5)
    m = albums_machine(3); m.window = 0
    open_grid(m)
    expect(('stock_resume', '5') in m.calls, 'if the window will not open the Albums row opens the stock list (Home id 5)')
    for missing_label in ('label_row_sub', 'label_grid_sub', 'albums_scrollview'):
        m = albums_machine(3); del m.widgets[missing_label]
        open_grid(m)
        expect('navigator_back' in m.names() and 'stock_resume' not in m.names(), f'an asset without {missing_label} leaves the page and does not open the stock list over it')

    # 3. Opening the grid: the page's widgets bound, the album list copied, the placeholder made, nothing per album,
    #    no cache build.
    m = albums_machine(30)
    calls = open_grid(m)
    names = [c[0] for c in calls]
    expect(('window_open', 'm1plus_albums') in calls and names.count('widget_on') == 4 + 1 + 2 + 1 + 1 + 3 + 1 + 8 + 1,
           f'the window, Back, Now Playing, Search, "...", Cover Flow, the card\'s eight rows and scrim, the scroll and scroll-end events of the scroll_view, foreground, background, three pointer events (down, up, abort) and the paint are bound ({names.count("widget_on")})')
    sv0, view0 = m.widgets['albums_scrollview'], m.widgets['view_grid']
    expect(all(('widget_on', sv0, O[e], PSYMS['al_on_scroll'], 0) in calls for e in ('EVT_SCROLL', 'EVT_SCROLL_END')) and not any(c[0] == 'widget_grab' for c in calls)
           and all(('widget_on', view0, O[e], PSYMS[f], 0) in calls for e, f in (('EVT_POINTER_DOWN', 'al_on_down'), ('EVT_POINTER_UP', 'al_on_up'), ('EVT_POINTER_ABORT', 'al_on_abort'))),
           'the scroll_view\'s EVT_SCROLL / scroll end re-arm the loader; the content view takes the pointer events the scroll_view passes down, and grabs nothing')
    expect((content_h(m), m.s32(sv0 + SC_VH)) == (TOP + 10 + 15 * 200,) * 2, f'the content view is as high as the title block and the library (52 + 15 rows x 200 + 10) and the scroll_view\'s virtual_h is the same ({content_h(m)})')
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in calls and ('deque_assign', 30) in calls, 'the stock album list is copied')
    expect(not any(n in names for n in ('image_create', 'list_item_create', 'label_create', 'hscroll_label_create', 'widget_factory_create_widget')),
           'no widget is created per album')
    expect(not any(n in names for n in ('pthread_create', 'toolsGetAlbumCover', 'toolsGetExternCover', 'mkdir')),
           'opening the grid starts no worker (the background build is a timer a moment later: section 13)')
    expect(nbmp(m) == 1 and ('widget_load_image', 'p_default') in calls, 'the placeholder disc is the only bitmap before the first frame')
    expect(('widget_set_visible', m.widgets['label_status'], 0) in calls, 'the status line starts hidden')

    # 4. The first frame: the cells that touch the view, each cover blitted 1:1, titles under them; decoding is
    #    paced (two covers a frame) and the rest show the placeholder until the reload timer fills them in.
    blits, texts = paint(m)
    ref = reference(0, 30)
    expect(len(ref) == 4 and [a for a, *_ in ref] == list(range(4)) and all(c[1] for c in ref) and ref[0][1][0][3] == COVER and ref[2][1][0][3] == VIEW_H - TOP - RGAP - PITCH,
           'two rows of two are in view at the top under the title block, the second row cut by the bottom edge')
    expect(dsts(blits) == want_dsts(ref) and all(b[1] == (0, 0, COVER, COVER) or b[1][3] < COVER for b in blits),
           f'one blit per visible cell, at its place, source = the whole tile ({dsts(blits)[:3]})')
    ts, ss = grid_texts(m, texts)
    expect(ts == {f'Album {c[0]}': c[2] for c in ref if c[2]} and ss == {f'Artist {c[0]}': c[3] for c in ref if c[3]},
           'an album (144x22) and an artist (144x20) under each cover')
    expect(len(ts) == 4 and len(ss) == 4 and ts['Album 0'] == (MARGIN, TOP + RGAP + COVER + TGAP, COVER, THEIGHT) and ss['Artist 1'] == (MARGIN + CPITCH, TOP + RGAP + COVER + TGAP + THEIGHT, COVER, SUBH),
           f'album 0\'s title at ({MARGIN}, {TOP + RGAP + COVER + TGAP}), album 1\'s artist directly under its title')
    expect(m.text_styles == ['label_grid_title'] * 4 + ['label_grid_sub'] * 4, 'two text-style passes: the albums, then the artists')
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'timer_add')] and nbmp(m) == 1
           and len({b[0] for b in blits}) == 1,
           'paint never decodes, allocates a bitmap or arms a timer: every cover is the one placeholder until the loader has run')
    expect(any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] and c[2] == 16 for c in calls),
           'opening arms the page\'s loader on a 16 ms timer')
    prep = [c[1] for c in m.calls if c[0] == 'widget_prepare_text_style']
    expect(prep == [m.widgets['label_grid_title'], m.widgets['label_grid_sub']], 'the text styles are the two grid labels\': 18 px white, then 15 px #AAAAAA')
    # the canvas: the scroll_view leaves the origin at the content's top less the offset; the paint moves it back down by the offset, draws in window
    # coordinates (the top of the window is 0) and leaves it where it was
    m4 = albums_machine(30); open_grid(m4); scroll_to(m4, TOP + 100); paint(m4)
    expect(m4.draw_oy == [SCREEN_Y0] * len(m4.blits) and m4.draw_oy and m4.oy_after == SCREEN_Y0 - TOP - 100,
           f'at 100 px every cover is drawn with the canvas origin at the top of the window ({set(m4.draw_oy)}), and the canvas is as the scroll_view left it ({m4.oy_after})')
    # the loader: one cover a tick, the cell nearest the middle of the view first, the view before the row ahead
    order = []
    for _ in range(8):
        before = set(m.loads)
        calls = tick(m)
        new = [u for u in m.loads if u not in before]
        expect(len(new) <= 1 and len([c for c in calls if c[0] == 'widget_load_image' and str(c[1]).startswith('file://')]) <= 1,
               'one tick decodes at most one cover')
        order += [m.cache_index[u[7:]] for u in new]
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in calls): break
    expect(order[:4] == [0, 1, 2, 3] and sorted(order[4:]) == [4, 5] and len(order) == 6,
           f'the four cells in view first (the first row is the nearer to the middle of the view), then the next row ahead ({order})')
    blits, texts = settle(m)
    expect(len(blits) == 4 and nbmp(m) == 1 + 6, f'every visible cover is a tile of its own once loaded, and the next row is ready ({nbmp(m)} bitmaps)')
    first = m.blits[0][0]
    data, bw, bh = m.bitmaps[first]
    tile = struct.unpack(f'<{bw * bh}I', bytes(m.u.mem_read(data, bw * bh * 4)))
    R = O['GRID_R']
    in_corner = lambda x, y: min(x, bw - 1 - x) < R and min(y, bh - 1 - y) < R
    expect((bw, bh) == (COVER, COVER) and {tile[y * bw + x] for y in range(bh) for x in range(bw) if not in_corner(x, y)} == {colour(0)},
           f'album 0\'s tile is its cache picture reduced to {COVER}x{COVER}')
    corners = [tile[y * bw + x] for x, y in ((0, 0), (bw - 1, 0), (0, bh - 1), (bw - 1, bh - 1))]
    inner = [tile[y * bw + x] for x, y in ((R - 1, R - 1), (bw - R, R - 1), (R - 1, bh - R), (bw - R, bh - R))]
    expect(corners == [0xff000000] * 4 and inner == [colour(0)] * 4 and all(v >> 24 == 255 for v in tile),
           f'the grid\'s covers have the shelf\'s rounded corners (GRID_R = {R}), blended into the black page; every pixel stays opaque')
    expect(struct.unpack('<H', m.u.mem_read(first + O['BITMAP_FLAGS'], 2))[0] & 1, 'tiles are flagged opaque (a plain blit)')
    m.count(); paint(m); steady = m.icount
    expect('widget_load_image' not in m.names() and 'bitmap_create_ex' not in m.names() and not m.measures,
           'a steady frame decodes, allocates and measures nothing')
    print(f'  grid frame: {steady:,} payload instructions steady (4 cells), {TILES} tiles of {COVER}x{COVER}')
    # a real 168 px cache file (left half red, right half blue): the box filter's reduction, edge to edge
    m = albums_machine(1)
    url = 'file://' + next(iter(m.cache_index))
    half = bytes((255, 0, 0, 255)) * (ART // 2) + bytes((0, 0, 255, 255)) * (ART // 2)
    m.images[url] = (ART, ART, half * ART)
    m.count(); open_grid(m); settle(m)
    data = m.bitmaps[m.blits[0][0]][0]
    row0 = struct.unpack(f'<{COVER}I', bytes(m.u.mem_read(data + 40 * COVER * 4, COVER * 4)))
    expect(set(row0[:COVER // 2]) == {0xff0000ff} and set(row0[COVER // 2:]) == {0xffff0000},
           f'a {ART} px cache picture reduces to {COVER} px with its halves intact')
    print(f'  one {ART}->{COVER} tile: {m.icount:,} payload instructions')

    # 5. Scrolling: the scroll_view's offset moves the window over the content and clamps at both ends (its virtual_h); the frame at the new offset is the
    #    reference model (partial rows cut by hand to the view, a title only when it fits). No art: only geometry here.
    n = 15      # an odd count: eight rows, the last with one album
    m = albums_machine(n, cached=False)
    open_grid(m); settle(m)
    expect(not any(c[0] == 'widget_invalidate_force' for c in m.calls), 'painting invalidates nothing once complete')
    scroll_to(m, TOP + 100)
    blits, texts = paint(m)
    ref = reference(TOP + 100, n)
    expect(dsts(blits) == want_dsts(ref), 'after scrolling 100 px: the cells and the cut first row')
    ts, ss = grid_texts(m, texts)
    expect(ts == {f'Album {c[0]}': c[2] for c in ref if c[2]} and ss == {f'Artist {c[0]}': c[3] for c in ref if c[3]},
           'after scrolling 100 px: the albums and artists of every cell in view, cut ones too')
    top_row = [b for b in blits if b[2][1] == 0][0]
    expect(top_row[1] == (0, 90, COVER, 54) and top_row[2] == (MARGIN, 0, COVER, 54), f'the first row is cut to its last 54 px ({top_row[1]} -> {top_row[2]})')
    scroll_to(m, TOP + 165)
    ref = reference(TOP + 165, n)
    ts, ss = grid_texts(m, paint(m)[1])
    expect(ts == {f'Album {c[0]}': c[2] for c in ref if c[2]} and ss == {f'Artist {c[0]}': c[3] for c in ref if c[3]}
           and 'Album 0' in ts and 'Artist 0' in ss and ref[0][1] is None,
           'at 165 px the first row\'s cover is gone and its album (7 px cut by the top) and its artist are drawn, the clip cuts the album')
    mx = TOP + RGAP + ((n + COLS - 1) // COLS) * PITCH - VIEW_H
    expect(mx == TOP + 1210, f'fifteen albums are eight rows: 52 + 10 + 8 x 200 = 1662 px of content, {mx} px of scroll')
    scroll_to(m, 100000)
    blits, texts = paint(m)
    expect(dsts(blits) == want_dsts(reference(mx, n)), f'dragging far past the end stops at {mx} px')
    expect(max(b[2][1] + b[2][3] for b in blits) + TGAP + THEIGHT + SUBH + RGAP == VIEW_H, f'the last row ends {RGAP} px above the bottom')
    expect(sorted(b[2][0] for b in blits if b[2][1] > 150) == [MARGIN], 'the odd album sits alone in the left column of the last row')
    scroll_to(m, -5000)
    blits, texts = paint(m)
    expect(dsts(blits) == want_dsts(reference(0, n)), 'dragging past the start stops at 0')
    for cnt, top in ((2, 0), (3, 10), (4, 10), (6, 210)):   # rows: 1, 2, 2, 3 -> content 210, 410, 410, 610
        m2 = albums_machine(cnt, cached=False); open_grid(m2)
        scroll_to(m2, 100000)
        blits, _ = paint(m2)
        top = TOP + top if top else 0
        expect(dsts(blits) == want_dsts(reference(top, cnt)), f'{cnt} albums: the content scrolls by at most {top} px')

    # 6. The content: the view is as high as the library in either mode and the scroll_view's virtual_h is the same (the list_view layouter sums it again).
    #    An int height and offset: 4000 albums are 400,010 px of grid or 256,000 px of list.
    for n_, mode_ in ((1, 'grid'), (4000, 'grid'), (1, 'list'), (4000, 'list')):
        m = albums_machine(n_, cached=False)
        if mode_ == 'list': m.fs[ALBUMS_FILE] = b'0\n'
        open_grid(m)
        want_h = TOP + ((RGAP + (n_ + COLS - 1) // COLS * PITCH) if mode_ == 'grid' else n_ * ROW)
        sv_ = m.widgets['albums_scrollview']
        expect(content_h(m) == want_h and m.s32(sv_ + SC_VH) == want_h and m.word(m.widgets['view_grid'] + 8) == CW,
               f'{n_} albums, {mode_}: the content view is {CW} x {want_h} and the scroll_view\'s virtual_h is {m.s32(sv_ + SC_VH)}')
        scroll_to(m, 10 ** 9)
        end_ = max(0, want_h - VIEW_H)
        expect(scroll_of(m) == end_, f'{n_} albums, {mode_}: it scrolls to {end_} px at most')
        blits, texts = paint(m)
        if mode_ == 'grid': expect(dsts(blits) == want_dsts(reference(end_, n_)), f'{n_} albums, {mode_}: at the end the last cells are drawn where they lie')
        else: expect(dsts(blits) == sorted(c[1][1] for c in list_ref(end_, n_) if c[1]), f'{n_} albums, {mode_}: at the end the last rows are drawn where they lie')
        expect(m.oy_after == SCREEN_Y0 - end_ and set(m.draw_oy) == {SCREEN_Y0}, f'{n_} albums, {mode_}: the canvas origin is moved by {end_} px for the paint and put back')

    #     the loader: one cover a tick, nearest the middle of the view first, then the next row in the scroll direction
    m = albums_machine(300); open_grid(m)
    scroll_to(m, 1100)
    got, per = run_loader(m)
    expect(got == [12, 13, 10, 11, 14, 15, 16, 17] and per == 1,
           f'at 1100 px: the row nearest the middle, then the others in view, then the row ahead, one cover a tick ({got})')
    paint(m)
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'timer_add')], 'and a paint then decodes nothing')
    #     the reversal: back up two rows: only the rows above are decoded (the row ahead is above now), what it left is still there
    scroll_to(m, 900)
    got, per = run_loader(m)
    expect(sorted(got) == [6, 7, 8, 9] and per == 1, f'back to 900 px (towards the top): the rows above are loaded, the ones just left are reused ({got})')
    scroll_to(m, 1100)
    got, per = run_loader(m)
    expect(got == [], f'and back to 1100 px again: nothing is decoded, the history held it ({got})')
    got_urls = [u for u in m.loads if u.startswith('file://')]
    expect(len(got_urls) == len(set(got_urls)), 'no cover was decoded twice in all of that')
    expect(nbmp(m) == 1 + 12, f'the ring is full and bounded: {nbmp(m)} bitmaps')
    #     (the ring is bounded for any library: section 10)
    #     the view is redrawn only for a cover that is in it
    m = albums_machine(30); open_grid(m)
    inv = []
    for _ in range(6):
        inv.append(('widget_invalidate_force', m.widgets['albums_scrollview']) in tick(m))
    expect(inv == [True] * 4 + [False] * 2, f'a decoded cell in view redraws the window (the scroll_view\'s rectangle), one in the row ahead does not ({inv})')
    #     the loader decodes nothing while the scroll_view moves (a finger dragging it, or its scroll animator running) and resumes when it stops:
    #     on demo's own scroll_view code in section 18; here the cases only the mocked flags can set up
    def set_anim(m, state=None, owner=None):
        sv_ = m.widgets['albums_scrollview']
        if state is None: m.setword(sv_ + O['SC_WA'], 0); return
        an = m.alloc(0x80); m.u.mem_write(an, bytes(0x80)); m.setword(an + O['SC_AN_STATE'], state); m.setword(an + O['SC_AN_WIDGET'], owner or sv_)
        m.setword(sv_ + O['SC_WA'], an)
    def fire_end(m):
        fn, ctx = m.bound[(m.widgets['albums_scrollview'], O['EVT_SCROLL_END'])]
        m.call(fn, a0=ctx, a1=0, count=40000000); return list(m.calls)
    for mode in ('grid', 'list'):
        def fresh():
            m = albums_machine(300)
            if mode == 'list': m.fs[ALBUMS_FILE] = b'0\n'
            open_grid(m); return m
        # a pressed finger that has not started to drag (a tap, a hold) does not defer
        m = fresh(); m.u.mem_write(m.widgets['albums_scrollview'] + O['SC_PRESSED'], bytes([1, 0]))
        n0 = len(file_loads(m)); tick(m)
        expect(len(file_loads(m)) == n0 + 1, f'{mode}: a finger that is down but has not dragged does not defer the loader')
        # an animator that is not running, or is not this list's, is not a fling
        for st, owner in ((4, None), (O['SC_AN_RUNNING'], 0x1234)):
            m = fresh(); set_anim(m, st, owner); n0 = len(file_loads(m)); tick(m)
            expect(len(file_loads(m)) == n0 + 1, f'{mode}: an animator in state {st} of widget {owner} does not defer')
        # the scroll end re-arms a loader that stopped (the polling ended with nothing left to load, then the offset moved)
        m = fresh(); run_loader(m)
        calls = scroll_to(m, 700)
        expect(armed(calls), f'{mode}: a scroll event arms the loader when covers are missing')
        run_loader(m)
        expect(not armed(fire_end(m)) and not armed(scroll_to(m, 700)), f'{mode}: with nothing missing the scroll events arm nothing')
    m = albums_machine(30); m.widget_on_fail = frozenset({O['EVT_SCROLL']})       # the scroll events refused: the loader polls for as long as the page is up
    open_grid(m)
    expect(all(armed(tick(m)) for _ in range(20)), 'if the scroll events cannot be registered the loader keeps polling, with nothing left to load too')
    #     kill switch: with /mnt/mmc/m1plus-off the Home entry does not open the Pod menu, so the page cannot open
    m = albums_machine(3); m.present.add('/mnt/mmc/m1plus-off')
    m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(pod_pages.HOME_ENTRY)), count=200000)
    expect('window_open' not in m.names(), 'the kill switch keeps the page (and the menu) closed')


def taps_list_tests(ctx):
    """7-13f: taps, titles, missing covers, a large library, closing, an empty library, list mode."""
    expect = ctx.expect
    # 7. Taps: a cell (cover or title) opens the stock album page for its row exactly as Cover Flow does; gaps, margins,
    #    the empty tail of the last row and a tap after a drag open nothing; the mapping follows the scroll.
    n = 11      # six rows, the last with one album
    m = albums_machine(n, cached=False)
    open_grid(m); settle(m)
    def cell_xy(a, scroll=0, dy=10, dx=10):
        return MARGIN + (a % COLS) * CPITCH + dx, TOP + RGAP + (a // COLS) * PITCH - scroll + dy
    opened = lambda calls: [c for c in calls if c[0] == 'navigator_to_with_context']
    expect(not opened(tap_at(m, 30, 5)), 'a tap above the first row opens nothing')
    expect(not opened(tap_at(m, 30, TOP + RGAP + CELL + 4)), 'a tap in the gap between the first two rows opens nothing')
    #     the tile's hit area is its cover, album and artist lines (the whole 144 x 190): corners and edges of album 1 (row 0, right)
    for what, (dx, dy, want) in {'its top-left pixel': (0, 0, True), 'its cover\'s bottom-right pixel': (COVER - 1, COVER - 1, True),
                                 'the gap under the cover (above the album)': (50, COVER + 1, True), 'the album line': (50, COVER + TGAP + 5, True),
                                 'the artist line': (50, COVER + TGAP + THEIGHT + 5, True), 'the last pixel of the artist line': (COVER - 1, CELL - 1, True),
                                 'one pixel past its right edge': (COVER, 50, False), 'one pixel past the artist line': (50, CELL, False)}.items():
        x, y = cell_xy(1, 0, dy, dx)
        got = opened(tap_at(m, x, y))
        expect(bool(got) == want and (not want or got[0][3] == 1), f'a tap on {what}: ' + ('album 1' if want else 'nothing'))
    scroll_to(m, 300); settle(m)
    calls = tap_at(m, *cell_xy(4, 300))
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 4) in calls, 'a tap on album 4\'s cover opens albuminfo_page with 0xf003 | 4 << 16')
    seq = [c[0] for c in calls if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context')]
    expect(seq == ['loadAlbumList', 'albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context']
           and ('batchadd_albumcover_task', 0, 0) in calls, f'the open sequence includes the cover thread release ({seq})')
    expect(m.deques[m.opened_album[2]] == m.showlist and m.opened_album[1] == 4, 'the page reads its row from the stock list')
    calls = tap_at(m, *cell_xy(5, 300, dy=COVER + TGAP + 5))
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 5) in calls, 'a tap on a title opens its album too')
    calls = tap_at(m, *cell_xy(4, 300, dy=COVER + TGAP + THEIGHT + 5))
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 4) in calls, 'and a tap on an artist line')
    for what, (x, y) in {'the gap between columns': (MARGIN + COVER + 4, 150), 'the left margin': (4, 150), 'the right margin': (316, 150),
                         'the gap between rows': (30, TOP + RGAP + 3 * PITCH - 300 - 5)}.items():
        expect(not opened(tap_at(m, x, y)), f'a tap on {what} opens nothing')
    mx = TOP + RGAP + 6 * PITCH - VIEW_H
    scroll_to(m, 100000); settle(m)
    expect(not opened(tap_at(m, 30, VIEW_H - 3)) and not opened(tap_at(m, 30 + CPITCH, 205)) , 'the 10 px under the last row, and the empty cell beside the last album, open nothing')
    for a, want in ((10, True), (9, True), (11, False)):   # (a point above the window is not the page's: the stock hit test never delivers it)
        x, y = cell_xy(a, mx)
        got = opened(tap_at(m, x, y))
        expect(bool(got) == want and (not want or got[0][3] == a),
               f'scrolled to the end, album {a}: ' + ('opens' if want else 'nothing' + (' (the empty cell of the last row)' if a == 11 else ' (scrolled out above)')))
    x, y = cell_xy(10, mx)
    expect(opened(gesture(m, [('down', x, y, 9800), ('up', x + TAP - 1, y + TAP - 1, 9900)])), f'a release {TAP - 1} px from the press on both axes (under the scroll_view\'s {TAP} px drag threshold) is still a tap')
    expect(not opened(gesture(m, [('down', x, y, 9800), ('up', x, y + TAP, 9900)])) and not opened(gesture(m, [('down', x, y, 9800), ('up', x + TAP, y, 9900)])),
           f'a release {TAP} px away on either axis is not')
    expect(not opened(gesture(m, [('down', x, y, 9800), ('abort', x, y, 9850), ('up', x, y, 9900)])),
           'a gesture the scroll_view aborted (it took it as a drag) opens nothing, even if the up comes back to the press')
    expect(not opened(gesture(m, [('up', x, y, 9900)])), 'an up with no press opens nothing')
    # the screen offset does not matter (widget_to_local), and a stale list is queried again
    m = albums_machine(n, cached=False); open_grid(m)
    m.setword(m.win + 4, 30 + 17)
    x, y = cell_xy(3)
    m.touch('down', x, SCREEN_Y0 + 17 + y, 1000, fn='al_on_down'); m.touch('up', x, SCREEN_Y0 + 17 + y, 1080, fn='al_on_up')
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 3) in m.calls, 'taps are converted with widget_to_local (the window\'s position does not matter)')
    m.setword(pod.DATA['PDEQ_SHOWLIST'][0], m.new_deque([m.record(name='other.flac')]))
    x, y = cell_xy(2)
    m.touch('down', x, SCREEN_Y0 + 17 + y, 3000, fn='al_on_down'); m.touch('up', x, SCREEN_Y0 + 17 + y, 3080, fn='al_on_up')
    expect(m.deques[m.opened_album[2]] == m.showlist, 'the stock queries run again on every open')

    # 7b. Gestures with sparse or sideways events (audit): the release is a position and both axes count (the scroll_view's own drag, fling and catch are
    #     tested with its own code in section 18).
    def mode_machine(mode):
        m = albums_machine(300, cached=False)
        if mode == 'list': m.fs[ALBUMS_FILE] = b'0\n'
        open_grid(m)
        return m
    opened = lambda calls: [c for c in calls if c[0] == 'navigator_to_with_context']
    for mode in ('grid', 'list'):
        xa = MARGIN + 10 if mode == 'grid' else 40
        m = mode_machine(mode)
        expect(not opened(gesture(m, [('down', xa, 300, 1000), ('up', xa, 50, 1080)])),
               f'{mode}: down and up 250 px apart with no move between is a scroll, not a tap')
        m = mode_machine(mode)
        expect(not opened(gesture(m, [('down', xa, 50, 1000), ('move', 262, 50, 1040), ('up', 262, 50, 1080)])),
               f'{mode}: a horizontal swipe from one cell/row to another opens nothing')
        expect(not opened(gesture(m, [('down', xa, 50, 2000), ('up', 262, 52, 2080)])),
               f'{mode}: a horizontal release with no move opens nothing either')
        m = mode_machine(mode)
        expect(len(opened(gesture(m, [('down', xa, 100, 5000), ('up', xa, 100, 5080)]))) == 1, f'{mode}: a plain tap opens the album')

    # 8. Titles: one line, cut with an ellipsis to the cell width by the canvas' own measure; what fits is untouched.
    #    The mock font is 8 px a character, 16 for CJK and the ellipsis: 144 px hold 18 characters, or 16 and an ellipsis,
    #    or 9 wide characters, or 8 and an ellipsis. The artist line is cut by the same rule, separately.
    cw = COVER // 8
    longs = {0: 'Short', 1: 'T' * cw, 2: 'T' * (cw + 1), 3: 'A very long album title that cannot fit', 4: 'あ' * (cw // 2),
             5: 'あ' * (cw // 2 + 1), 6: '日本語のアルバム名前を長くした', 7: ''}
    def mock_w(s): return sum(16 if ord(c) >= 0x2e80 or c == '…' else 8 for c in s)
    def model_cut(s):      # the longest prefix whose width with the ellipsis fits, else the whole text when it fits
        if mock_w(s) <= COVER: return s
        k = max(k for k in range(len(s)) if mock_w(s[:k] + '…') <= COVER)
        return s[:k] + '…'
    m = albums_machine(8, cached=False, title=lambda i: longs[i]); m.fs[SORT_FILE] = b'3\n'; m.class_lists[O['CLASS_ALL_SONGS']] = []   # (Year with no song list keeps the stock rows' order, so tile i is row i)
    for i in range(8): m.setword(m.showlist[i] + O['REC_ARTIST'], m.cstr(longs[(i + 2) % 8]))
    open_grid(m)
    got_t, got_s, nmeasure = [None] * 8, [None] * 8, 0
    for top, albums_in_view in ((0, range(8)), (TOP + 200, range(8)), (TOP + 400, range(8))):
        if top: scroll_to(m, top)
        texts = paint(m)[1]
        nmeasure += len(m.measures)
        for (txt, rect), sty in zip(texts, m.text_styles):
            a = [i for i in albums_in_view if rect[0] == MARGIN + (i % COLS) * CPITCH and rect[1] - (TOP + RGAP + (i // COLS) * PITCH - top) in (COVER + TGAP, COVER + TGAP + THEIGHT)][0]
            (got_t if sty == 'label_grid_title' else got_s)[a] = txt
    want_t = [model_cut(longs[i]) if longs[i] else None for i in range(8)]
    want_s = [model_cut(longs[(i + 2) % 8]) if longs[(i + 2) % 8] else None for i in range(8)]
    expect(got_t == want_t, f'albums: what fits is whole, the rest ends in an ellipsis where text + ellipsis fits 144 px, an empty one draws nothing ({got_t})')
    expect(got_s == want_s, f'artists: the same rule, separately ({got_s})')
    expect(got_t[1] == 'T' * cw and got_t[2] == 'T' * (cw - 2) + '…' and got_t[4] == 'あ' * (cw // 2) and got_t[5] == 'あ' * (cw // 2 - 1) + '…',
           f'18 narrow / 9 wide characters fit 144 px, one more is cut (8 px a character, 16 for CJK and the ellipsis) ({got_t[1:6]})')
    expect(nmeasure <= 8 * 7, f'a text is measured about log2(48) times ({nmeasure} for 15 texts)')
    paint(m)
    expect(not m.measures, 'texts are measured once, when the tile is first drawn, never again')
    #     the same rule with the shipped font's real metrics (the text-width rule of docs/ui.md): 18 px albums and 15 px artists
    #     of every script of the 16 languages cut to 144 px, the cut the longest that fits with its ellipsis
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    for px in (18, 15):
        wid = lambda s: StbText(font, px).layout(s)[1] if s else 0
        expect(wid('…') > 0, f'the ellipsis has a glyph at {px} px ({wid("…")} px wide)')
        for name, s in {'Latin': 'The Rise and Fall of Ziggy Stardust and the Spiders from Mars', 'accents': 'Sérénade pour orchestre à cordes, Ödön Önder',
                        'Cyrillic': 'Щелкунчик, балет в двух действиях Петра Ильича Чайковского', 'Greek': 'Η Συμφωνία των Αλκυονίδων του Μίκη Θεοδωράκη',
                        'Japanese': '日本語のアルバム名前を長くしたもの、ひらがなカタカナ', 'Chinese': '周杰伦的第一张正式大型专辑重制版豪华纪念版', 'Traditional': '周杰倫的第一張正式大型專輯重製版豪華紀念版',
                        'Korean': '한국어로 된 아주 긴 앨범 이름과 가수 이름입니다', 'Vietnamese': 'Những bản tình ca bất hủ của nhạc sĩ Trịnh Công Sơn'}.items():
            assert wid(s) > COVER, name
            k = max(k for k in range(len(s)) if wid(s[:k] + '…') <= COVER)
            expect(wid(s[:k] + '…') <= COVER < wid(s[:k + 1] + '…') and k > 3, f'{px} px {name}: {k} of {len(s)} characters and an ellipsis fit 144 px ({wid(s[:k] + "…")} px)')
        expect(wid('Kind of Blue') <= COVER and wid('Miles Davis') <= COVER and wid('日本語') <= COVER, f'{px} px: ordinary short names fit whole')

    # 9. Missing cache files: no picture for them, the placeholder disc instead, no decode attempt, nothing built.
    m = albums_machine(9, missing={1, 4}, empty={2, 7})
    open_grid(m); blits, _ = settle(m)
    counts = {bm: sum(1 for b in blits if b[0] == bm) for bm in {b[0] for b in blits}}
    expect(len(blits) == 4 and sorted(counts.values()) == [1, 1, 2], f'albums 0 and 3 have a tile each, 1 (no file) and 2 (empty marker) share one bitmap ({sorted(counts.values())})')
    ph = m.bitmaps[[bm for bm, c in counts.items() if c == 2][0]]
    expect(ph[1:] == (COVER, COVER), f'the placeholder is the grid\'s {COVER}x{COVER}')
    expect(not any(n in m.names() for n in ('pthread_create', 'toolsGetAlbumCover', 'mkdir')) and not any(c[0] == 'fopen' and 'w' in c[2] for c in m.calls),
           'a missing cache file starts no build at open and writes no marker (the background build is section 13)')
    m = albums_machine(6, cached=False)
    open_grid(m); blits, texts = settle(m)
    expect(len(blits) == 4 and len({b[0] for b in blits}) == 1 and len(texts) == 8, 'with no cache at all every visible cell is the placeholder with its album and artist')
    m = albums_machine(3, cached=False); m.images.pop('p_default')
    open_grid(m); blits, _ = settle(m)
    d = m.bitmaps[blits[0][0]][0]
    mid = d + COVER * (COVER // 2) * 4   # a whole row through the middle: no corner on it
    expect(len(blits) == 3 and set(struct.unpack(f'<{COVER}I', bytes(m.u.mem_read(mid, COVER * 4)))) == {0xff2b2b2b}
           and struct.unpack('<I', bytes(m.u.mem_read(d, 4)))[0] == 0xff000000, 'without the stock disc the placeholder is flat grey, its corners rounded like the covers')
    m = albums_machine(3, cached=False); m.bitmap_ok = False
    open_grid(m); blits, texts = paint(m)
    expect(blits == [] and len(texts) == 6, 'if bitmaps cannot be made the albums and artists still show')

    # 10. A large library: the work per frame and the memory do not grow with it.
    n = 4000
    m = albums_machine(n).count()
    open_grid(m, 80000000)   # (the Title order sorts the 4000 titles at open)
    opened_cost = m.icount
    expect(sum(1 for c in m.calls if c[0] == 'calloc') <= 6, 'opening a library of 4000 allocates its list copy, one tile ring and the Title sort (order, rows, keys; the last two freed)')
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == 1, 'the open itself makes one bitmap (the placeholder)')
    settle(m)
    rows = (n + COLS - 1) // COLS
    mx = RGAP + rows * PITCH - VIEW_H
    loaded, peak = [nbmp(m)], 0
    for target in (mx // 2, mx, 0):
        scroll_to(m, target)
        blits, texts = settle(m)
        expect(dsts(blits) == want_dsts(reference(target, n)), f'4000 albums, scroll {target}: the frame is the visible cells only ({len(blits)})')
        expect(nbmp(m) <= TILES + 1, f'live bitmaps stay within {TILES} tiles + the placeholder ({nbmp(m)})')
        peak = max(peak, sum(w * h * 4 for _, w, h in m.bitmaps.values()))
        loaded.append(nbmp(m))
    expect(peak <= (TILES + 1) * COVER * COVER * 4 <= 1100000,
           f'bitmap memory peaks at {peak} B (<= {(TILES + 1) * COVER * COVER * 4} B = {TILES} tiles + the placeholder)')
    top_urls = [u for u in m.loads if u.startswith('file://')]
    expect(m.destroyed > 0 and len(top_urls) > len(set(top_urls)), f'old tiles are recycled as the view moves, and the albums back at the top are decoded again ({m.destroyed} destroyed, {len(top_urls)} loads of {len(set(top_urls))} covers)')
    m.call(PSYMS['al_on_destroy'], count=2000000)
    expect(len(m.bitmaps) == 0, f'closing the page destroys every bitmap ({nbmp(m)} left)')
    expect(any(c[0] == 'deque_destroy' for c in m.calls) and any(c[0] == 'free' for c in m.calls), 'and frees the list copy and the tile ring')
    print(f'  4000 albums: open {opened_cost:,} payload instructions, at most {max(loaded)} bitmaps live, {peak} B of bitmaps')

    # 11. Closing mid-gesture or with a reload timer pending leaves nothing behind.
    m = albums_machine(30); open_grid(m); paint(m)       # the loader's timer is pending (armed at open)
    m.touch('down', 100, SCREEN_Y0 + 100, 1000, fn='al_on_down')
    m.call(PSYMS['al_on_destroy'], count=2000000)
    expect(len([c for c in m.calls if c == ('timer_remove', 0x777)]) == 2 and not any(c[0] == 'widget_ungrab' for c in m.calls),
           'destroy removes the loader\'s and the build\'s timer (the page grabs nothing)')
    expect(len(m.bitmaps) == 0, 'and every bitmap')
    m.call(PSYMS['al_on_load'], count=1000000)
    expect('widget_invalidate_force' not in m.names() and 'timer_add' not in m.names() and 'widget_load_image' not in m.names(),
           'a late loader tick after close does nothing')
    for fn in ('al_on_up', 'al_on_down', 'al_on_abort', 'al_on_scroll'):
        m.touch('up', 100, SCREEN_Y0 + 100, 1100, fn=fn)
        expect('navigator_to_with_context' not in m.names() and 'widget_invalidate_force' not in m.names() and 'timer_add' not in m.names(), f'a late {fn} after close does nothing')

    # 12. Empty library: the status line, no view.
    m = albums_machine(0)
    open_grid(m)
    expect(('widget_set_text_utf8', m.widgets['label_status'], 'Update Local Music first') in m.calls, 'an empty library says so')
    expect(('widget_set_visible', m.widgets['view_grid'], 0) in m.calls and ('widget_set_sensitive', m.widgets['view_grid'], 0) in m.calls,
           'and hides the (insensitive) view')
    m = albums_machine(3); del m.widgets['view_grid']
    open_grid(m)
    expect('navigator_back' in m.names(), 'an asset without view_grid leaves the page')

    # 13. List mode: the same page, rows of LIST_ROW_H px (cover, album, artist, hairline), custom-drawn.
    m = list_machine(30)
    blits, texts = paint(m)
    ref = list_ref(0, 30)
    expect(len(ref) == 6, 'six rows touch the 400 px view at the top, under the title block (the last by 28 px)')
    expect(dsts(blits) == sorted(c[1][1] for c in ref if c[1]) and all(b[1][2:] == (LART, LART) or b[1][3] < LART for b in blits),
           f'one {LART} px cover per visible row at ({LAX}, row + {LAY}), the sixth cut to the view')
    want_t = sorted((f'Album {a}', t) for a, _, t, _, _ in ref if t)
    want_a = sorted((f'Artist {a}', s_) for a, _, _, s_, _ in ref if s_)
    got_t = sorted((t[0], t[1]) for t, sty in zip(texts, m.text_styles) if sty == 'label_row_title')
    got_a = sorted((t[0], t[1]) for t, sty in zip(texts, m.text_styles) if sty == 'label_row_sub')
    expect(got_t == want_t and got_a == want_a and len(texts) == len(want_t) + len(want_a),
           f'the album names in the title style and the artists in the sub style, each in its {TW} px rect; texts cut by the view drawn too ({len(want_t)} + {len(want_a)})')
    prep = [c[1] for c in m.calls if c[0] == 'widget_prepare_text_style']
    expect(prep == [m.widgets['label_row_title'], m.widgets['label_row_sub']] and m.text_styles == ['label_row_title'] * len(want_t) + ['label_row_sub'] * len(want_a),
           'two text-style switches a frame: all titles, then all artists')
    expect(sorted(f[1:] for f in m.fills if f[0] == O['LIST_HAIR']) == sorted((HX, c[4], HW, 1) for c in ref if c[4] is not None)
           and not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'a one pixel hairline under every row whose last line is in view, no pressed fill')
    expect(sorted(b[2] for b in m.chevs) == sorted((O['LIST_CHEV_X'], y, CHEV_PX[0], min(CHEV_PX[1], VIEW_H - y)) for y in (TOP + c[0] * ROW + (ROW - 1 - CHEV_PX[1]) // 2 for c in ref) if y < VIEW_H) and O['LIST_CHEV_X'] == 288,
           f'a chevron {CHEV_PX} at x {O["LIST_CHEV_X"]}, centred above the hairline, on every row it touches in view, the last cut by the bottom edge ({sorted(b[2] for b in m.chevs)})')
    expect('widget_load_image' not in m.names(), 'list paint decodes nothing either')
    blits, texts = settle(m)
    expect(len(blits) == 6 and nbmp(m) == 1 + 6 + 2, f'every visible row has its own cover once loaded, and the next two rows are ready ({nbmp(m)} bitmaps)')
    data, bw, bh = m.bitmaps[m.blits[0][0]]
    lt, LR = struct.unpack(f'<{bw * bh}I', bytes(m.u.mem_read(data, bw * bh * 4))), O['LIST_R']
    expect((bw, bh) == (LART, LART) and {lt[y * bw + x] for y in range(bh) for x in range(bw) if not (min(x, bw - 1 - x) < LR and min(y, bh - 1 - y) < LR)} == {colour(0)},
           f'row 0\'s cover is its cache picture reduced to {LART}x{LART} (its rounded corners aside)')
    m.count(); paint(m)
    expect('widget_load_image' not in m.names() and 'bitmap_create_ex' not in m.names() and not m.measures,
           'a steady list frame decodes, allocates and measures nothing')
    print(f'  list frame: {m.icount:,} payload instructions steady (6 rows)')

    # 13b. Scrolling and bounds: the content is count x 64 px; partial rows are cut by hand.
    n = 20
    m = list_machine(n, cached=False); settle(m)
    mx = TOP + n * ROW - VIEW_H
    expect(mx == 932, 'twenty rows are 52 + 1280 px of content: 932 px of scroll')
    scroll_to(m, 100)
    blits, texts = paint(m)
    ref = list_ref(100, n)
    expect(dsts(blits) == sorted(c[1][1] for c in ref if c[1]), 'after scrolling 100 px: the rows and the cut first cover')
    top_row = [b for b in blits if b[2][1] == 0][0]
    want_top = [c[1] for c in ref if c[1] and c[1][1][1] == 0][0]
    expect((top_row[1], top_row[2]) == want_top and top_row[1][1] + top_row[1][3] == LART,
           f'the first cover is cut to its last pixels ({top_row[1]} -> {top_row[2]})')
    expect(sorted(t[0] for t in texts) == sorted([f'Album {a}' for a, _, t, _, _ in ref if t] + [f'Artist {a}' for a, _, _, s_, _ in ref if s_]),
           'texts cut by the view are drawn too (the clip cuts them)')
    scroll_to(m, 100000)
    blits, texts = paint(m)
    ref = list_ref(mx, n)
    expect(dsts(blits) == sorted(c[1][1] for c in ref if c[1]), f'dragging far past the end stops at {mx} px')
    expect(m.fills and max(f[2] + f[4] for f in m.fills if f[0] == O['LIST_HAIR']) == VIEW_H, 'the last hairline is the last line of the view')
    scroll_to(m, -5000)
    blits, texts = paint(m)
    expect(dsts(blits) == sorted(c[1][1] for c in list_ref(0, n) if c[1]), 'dragging past the start stops at 0')
    m2 = list_machine(5, cached=False); scroll_to(m2, 300)
    blits, _ = paint(m2)
    expect(dsts(blits) == sorted(c[1][1] for c in list_ref(0, 5) if c[1]) and len(blits) == 5, 'five rows (52 + 320 px) cannot scroll')

    # 13b'. Overscroll (device crash, V2.1nY): while a drag pulls the list past an end, the stock scroll_view's yoffset is outside [0, max] (the gap above
    #       the first row; scroll_to above clamps, the device does not). The page draws the albums that are there, at their place, and never asks for an
    #       album before the first or after the last: list row -1 read past the album list and the app crashed. The loader and a mode switch alike.
    def over(m, v):
        sv = m.widgets['albums_scrollview']
        m.setword(sv + SC_YOFF, v & 0xffffffff)
        fn, ctx = m.bound[(sv, O['EVT_SCROLL'])]
        m.call(fn, a0=ctx, a1=0, count=40000000)
    for mode in ('list', 'grid'):
        n = 20
        m = list_machine(n, cached=False) if mode == 'list' else albums_machine(n, cached=False)
        if mode == 'grid': open_grid(m)
        settle(m)
        top = TOP + (n * ROW if mode == 'list' else RGAP + n // COLS * PITCH) - VIEW_H   # the largest offset in range
        for v in (-30, -100, -200, -399, top + 100, top + 399):
            try:
                m.calls = []
                over(m, v); seen = list(m.calls); tick(m); seen += m.calls; blits, texts = paint(m); seen += m.calls
                oob = [c for c in seen if c[0] == 'deque_at_oob']
                expect(not oob, f'{mode}, offset {v}: no album outside the list is looked up (the device crashed on album -1) ({oob[:2]})')
                names = [t[0] for t in texts]
                ok = all(s.split(' ')[1].isdigit() and 0 <= int(s.split(' ')[1]) < n for s in names)
                first_y = min((t[1][1] for t in texts if t[0] == 'Album 0'), default=None)
                low = mode != 'list' or v != -100 or (first_y is not None and first_y >= 100)   # list, 100 px gap: album 0's title is below it
                drawn = bool(blits) or v in (-399, top + 399)   # at the extremes 1 px of content is left in view: nothing whole to draw
                expect(ok and low and drawn, f'{mode}, offset {v}: only albums 0..{n - 1} are drawn, at their place below the gap ({sorted(set(names))[:3]}, Album 0 at {first_y})')
            except Exception as ex:
                expect(False, f'{mode}, offset {v}: the page survives an offset past the end ({type(ex).__name__}: {ex})')
        try:
            over(m, -150); view_switch(m, 20000000); after = scroll_of(m)
            expect(after == 0, f'{mode}: a mode switch while pulled past the top keeps the first album at the top (offset {after})')
        except Exception as ex:
            expect(False, f'{mode}: a mode switch while pulled past the top survives ({type(ex).__name__}: {ex})')

    # 13c. Taps: any x on a row opens its album (the hairline line included); below the last row nothing; the pressed row
    #      is filled while the finger is down and clears on release, on a drag and on abort.
    n = 9
    m = list_machine(n, cached=False); settle(m)
    row_xy = lambda a, scroll=0, dy=20, x=200: (x, TOP + a * ROW - scroll + dy)
    calls = tap_at(m, *row_xy(4))
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 4) in calls, 'a tap on row 4 opens its album with 0xf003 | 4 << 16')
    seq = [c[0] for c in calls if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context')]
    expect(seq == ['loadAlbumList', 'albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context'], f'the stock open sequence, as the grid\'s ({seq})')
    for what, (x, y, want) in {'its cover': (20, TOP + 2 * ROW + 20, 2), 'the right edge': (319, TOP + 2 * ROW + 5, 2), 'the hairline line': (100, TOP + 3 * ROW - 1, 2),
                               'the next row\'s first line': (100, TOP + 3 * ROW, 3), 'the title block': (100, TOP - 1, None)}.items():
        got = [c for c in tap_at(m, x, y) if c[0] == 'navigator_to_with_context']
        expect((got[0][3] if got else None) == want, f'a tap on {what}: ' + (f'album {want}' if want is not None else 'nothing'))
    expect(not [c for c in tap_at(m, 100, -1) if c[0] == 'navigator_to_with_context'], 'a tap above the view opens nothing')
    paint(m)
    m.touch('down', 100, SCREEN_Y0 + TOP + 3 * ROW + 20, 5000, fn='al_on_down')
    expect(('widget_invalidate_force', m.widgets['albums_scrollview']) in m.calls, 'touching a row redraws the window')
    paint(m)
    pf = [f for f in m.fills if f[0] == 0xff343333]
    expect(pf == [(0xff343333, 0, TOP + 3 * ROW, CW, ROW - 1)], f'the pressed row is filled #333334 over its body, above the hairline ({pf})')
    m.touch('up', 100, SCREEN_Y0 + TOP + 3 * ROW + 20, 5080, fn='al_on_up')
    paint(m)
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'and the fill is gone after the release')
    m.touch('down', 100, SCREEN_Y0 + TOP + 3 * ROW + 20, 7000, fn='al_on_down')
    m.touch('abort', 100, SCREEN_Y0 + TOP + 3 * ROW + 20, 7100, fn='al_on_abort')   # the scroll_view took the gesture as a drag: it aborts its children's press
    paint(m)
    expect(not [f for f in m.fills if f[0] == O['LIST_PRESS']], 'a drag (the scroll_view\'s abort) takes the highlight away, and so does an aborted gesture')
    m.touch('up', 100, SCREEN_Y0 + TOP + 3 * ROW + 20, 7200, fn='al_on_up')
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'and its up opens nothing')
    ms = list_machine(3, cached=False); settle(ms)
    expect(not [c for c in tap_at(ms, 100, TOP + 3 * ROW + 10) if c[0] == 'navigator_to_with_context'], 'a tap below the last row opens nothing')
    ms.touch('down', 100, SCREEN_Y0 + TOP + 3 * ROW + 10, 8000, fn='al_on_down')
    paint(ms)
    expect(not [f for f in ms.fills if f[0] == O['LIST_PRESS']], 'and a touch there highlights nothing')
    mg = albums_machine(n, cached=False); open_grid(mg); settle(mg)
    gesture(mg, [('down', 30, 20, 1000)]); paint(mg)
    expect(not mg.fills, 'the grid mode never fills a row')

    # 13d. Ellipsis: the same rule as the grid\'s, at LIST_TEXT_W, separately for the album and the artist (the mock
    #      font is 8 px a character, 16 for CJK and the ellipsis: 248 px hold 31 characters, or 29 and an ellipsis).
    fits, wide = TW // 8, TW // 16
    longs = {0: 'T' * fits, 1: 'T' * (fits + 1), 2: 'あ' * wide, 3: 'あ' * (wide + 1), 4: 'Short'}
    m = albums_machine(5, cached=False, title=lambda i: longs[i]); m.fs[SORT_FILE] = b'3\n'; m.class_lists[O['CLASS_ALL_SONGS']] = []   # (stock rows' order, as above)
    m.fs[ALBUMS_FILE] = b'0\n'
    for i in range(5): m.setword(m.showlist[i] + O['REC_ARTIST'], m.cstr(longs[(i + 1) % 5]))
    open_grid(m); texts = paint(m)[1]
    titles = {(t[1][1] - TOP) // ROW: t[0] for t, sty in zip(texts, m.text_styles) if sty == 'label_row_title'}
    artists = {(t[1][1] - TOP) // ROW: t[0] for t, sty in zip(texts, m.text_styles) if sty == 'label_row_sub'}
    expect(titles[0] == 'T' * fits and titles[1] == 'T' * (fits - 2) + '…', f'a title that fits {TW} px is whole, one more character is cut with an ellipsis ({titles[1]!r})')
    expect(titles[2] == 'あ' * wide and titles[3] == 'あ' * (wide - 1) + '…', f'wide characters count their width ({titles[2]!r}, {titles[3]!r})')
    expect(artists[0] == 'T' * (fits - 2) + '…' and artists[1] == 'あ' * wide and artists[2] == 'あ' * (wide - 1) + '…' and artists[3] == 'Short',
           f'the artist line is cut by the same rule ({artists[0]!r}, {artists[2]!r})')
    expect(len(m.measures) <= 10 * 7, f'about log2(48) measures per cut text ({len(m.measures)})')
    paint(m)
    expect(not m.measures, 'texts are measured once, never again')

    # 13e. Placeholders in the list: the stock disc at the list size, shared; flat grey without it; no bitmaps, still text.
    m = list_machine(6, cached=False); blits, texts = settle(m)
    expect(len(blits) == 6 and len({b[0] for b in blits}) == 1 and len(texts) == 12 and m.bitmaps[blits[0][0]][1:] == (LART, LART),
           'with no cache every row shows the one shared placeholder, 52x52, with both lines')
    m = albums_machine(3, cached=False); m.fs[ALBUMS_FILE] = b'0\n'; m.images.pop('p_default'); open_grid(m)
    blits, _ = settle(m); d = m.bitmaps[blits[0][0]][0]
    mid_row = d + LART * (LART // 2) * 4   # a whole row through the middle: no corner on it
    expect(set(struct.unpack(f'<{LART}I', bytes(m.u.mem_read(mid_row, LART * 4)))) == {0xff2b2b2b}, 'without the stock disc the placeholder is flat grey')
    m = albums_machine(3, cached=False); m.fs[ALBUMS_FILE] = b'0\n'; m.bitmap_ok = False; open_grid(m)
    blits, texts = paint(m)
    expect(blits == [] and len(texts) == 6, 'if bitmaps cannot be made the texts still show')

    # 13f. Corners per mode: the list's LIST_R corners cut in the alpha (the tile not opaque: a pressed row's fill shows behind them), the
    #      grid's GRID_R corners blended into black (opaque), and a switch of mode in place remakes the tiles in the new shape, both ways.
    def shape_of(m):
        blits, _ = settle(m); b = blits[0][0]; d, bw, bh = m.bitmaps[b]
        px = struct.unpack(f'<{bw * bh}I', bytes(m.u.mem_read(d, bw * bh * 4)))
        return bw, px[0], px[bh // 2 * bw + bw // 2], struct.unpack('<H', m.u.mem_read(b + O['BITMAP_FLAGS'], 2))[0] & 1
    def is_list(s): return s[0] == LART and s[1] >> 24 == 0 and s[2] >> 24 == 255 and not s[3]
    def is_grid(s): return s[0] == COVER and s[1] == 0xff000000 and s[2] >> 24 == 255 and s[3]
    m = list_machine(6); s1 = shape_of(m)
    view_switch(m, 20000000); s2 = shape_of(m)
    view_switch(m, 20000000); s3 = shape_of(m)
    expect(is_list(s1) and is_grid(s2) and is_list(s3) and O['LIST_R'] == 4,
           f'list covers: {O["LIST_R"]} px corners in the alpha, not opaque; switched to the grid: {O["GRID_R"]} px corners into black, opaque; and back ({s1}, {s2}, {s3})')
    m = albums_machine(6); open_grid(m); g1 = shape_of(m)
    view_switch(m, 20000000); l1 = shape_of(m)
    expect(is_grid(g1) and is_list(l1), f'opened as the grid and switched to the list, the list gets its own corners, not the grid\'s ({g1}, {l1})')
    m = albums_machine(4000); m.fs[ALBUMS_FILE] = b'0\n'; open_grid(m); settle(m)
    mx = 4000 * ROW - VIEW_H
    for target in (mx // 2, mx, 0):
        scroll_to(m, target); settle(m)
        expect(nbmp(m) <= TILES + 1, f'list of 4000: live bitmaps stay within {TILES} tiles + the placeholder ({nbmp(m)})')
    m.call(PSYMS['al_on_destroy'], count=2000000)
    expect(len(m.bitmaps) == 0, 'closing the list frees every bitmap')


def toggle_tests(ctx):
    """14-16b: the grid/list toggle, persistence across opens, hit tests, the Cover Flow button."""
    expect, page = ctx.expect, ctx.page
    row, on_row, rows0 = menu_row(page), PSYMS['on_row'], PSYMS['pod_rows_0']
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin')
    # 14. The toggle: switches the mode in place (no window opens or closes), saves the choice atomically, swaps the
    #     glyph, drops the tiles, keeps the first album in view.
    opened_ev = ('window_open', 'window_close', 'navigator_back', 'navigator_to_with_context', 'stock_resume', 'widget_destroy')
    m = albums_machine(60)
    open_grid(m); settle(m)
    expect(glyph(m) == 'pod_nav_list', 'the grid shows the list glyph')
    scroll_to(m, 700); paint(m)
    first_row = (700 - TOP - RGAP - CELL) // PITCH + 1
    m.calls = []
    view_switch(m, 20000000)
    calls = m.calls
    expect(not [c for c in calls if c[0] in opened_ev], f'toggling opens and closes nothing ({[c[0] for c in calls if c[0] in opened_ev]})')
    expect(m.fs.get(ALBUMS_FILE) == b'0\n' and ALBUMS_TMP not in m.fs, f'it saves "0" atomically ({m.fs.get(ALBUMS_FILE)!r})')
    expect(('fsync', ALBUMS_TMP) in calls and ('fsync', '/mnt/data/m1plus') in calls and ('rename', ALBUMS_TMP, ALBUMS_FILE) in calls,
           'temp file, fsync, rename, directory fsync (as the Start-in setting)')
    expect(glyph(m) == 'pod_nav_grid' and vis(m, 'vs_tick5')[0] == 1 and vis(m, 'vs_tick4')[0] == 0, 'the List row is ticked now and Grid is not')
    expect(('widget_invalidate_force', m.widgets['albums_scrollview']) in calls, 'and the window is redrawn')
    sv_ = m.widgets['albums_scrollview']
    expect(content_h(m) == TOP + 60 * ROW and m.s32(sv_ + SC_VH) == TOP + 60 * ROW, f'the content is now the title block and 60 rows of {ROW} px, in the view and the scroll_view ({content_h(m)})')
    expect(scroll_of(m) == TOP + first_row * ROW * COLS, f'the scroll_view is at the first album\'s row ({scroll_of(m)} = album {first_row * COLS} x {ROW})')
    expect(nbmp(m) == 1 and m.bitmaps[next(iter(m.bitmaps))][1:] == (LART, LART), 'the grid\'s covers are dropped; the placeholder is the list\'s size')
    blits, texts = paint(m)
    top = [t for t, sty in zip(texts, m.text_styles) if sty == 'label_row_title' and t[1][1] < 40]
    expect(top and top[0][0] == f'Album {first_row * COLS}', f'the first album in view stays first: Album {first_row * COLS} ({top[0][0] if top else None})')
    # and back
    m.calls = []
    view_switch(m, 20000000)
    expect(not [c for c in m.calls if c[0] in opened_ev] and m.fs.get(ALBUMS_FILE) == b'1\n' and glyph(m) == 'pod_nav_list', 'toggling back: in place, "1" saved, the row offers the list')
    blits, texts = paint(m)
    expect(min(int(t[0].split()[1]) for t in texts) == first_row * COLS, f'back in the grid the same album row is in view (Album {first_row * COLS})')
    # the tiles of the other mode are never reused: no 144 px blit in the list, no 52 px one in the grid
    blits, _ = settle(m)
    expect(all(m.bitmaps[b[0]][1:] == (COVER, COVER) for b in blits), 'grid covers are 144 px again')
    # many switches: no window churn, no leak
    seen = []
    for _ in range(8):
        view_switch(m, 20000000); seen += m.calls; settle(m); seen += m.calls
    expect(nbmp(m) <= TILES + 1, f'after many switches the live bitmaps are still bounded ({nbmp(m)})')
    expect(not [c for c in seen if c[0] in opened_ev], 'eight more switches opened and closed no window')
    # a pending reload timer and a fling are cancelled by the switch
    m = albums_machine(60); calls = open_grid(m)
    assert any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in calls)
    m.calls = []
    view_switch(m, 20000000)
    expect(('timer_remove', 0x777) in m.calls, 'the pending reload timer is removed when the mode changes')
    # list -> grid -> list keeps the position to the nearest row
    m = list_machine(60, cached=False); scroll_to(m, 5 * ROW)
    view_switch(m, 20000000)
    blits, texts = paint(m)
    expect(m.fs.get(ALBUMS_FILE) == b'1\n' and min(int(t[0].split()[1]) for t in texts) == (5 // COLS) * COLS, 'from the list at row 5 the grid shows its row 2 (albums 4, 5) first')
    # an empty library, a closed page
    m = albums_machine(0); m.fs[ALBUMS_FILE] = b'0\n'; open_grid(m); m.calls = []
    view_switch(m, 20000000)
    expect(m.fs.get(ALBUMS_FILE) == b'1\n' and glyph(m) == 'pod_nav_list', 'with an empty library the toggle still switches and saves')
    m = albums_machine(3); open_grid(m); m.call(PSYMS['al_on_destroy'], count=2000000); m.calls = []
    view_switch(m, 20000000)
    expect(not m.calls and ALBUMS_FILE not in m.fs, 'a late toggle after the page closed does nothing')

    # 15. Persistence across opens: the Albums row opens the last mode.
    m = albums_machine(3)
    open_grid(m)
    view_switch(m, 20000000)
    m.call(PSYMS['al_on_destroy'], count=2000000)
    m.calls = []; m.call(on_row, a0=rows0 + 12 * row, count=20000000)
    expect(('window_open', 'm1plus_albums') in m.calls and glyph(m) == 'pod_nav_grid' and 'stock_resume' not in m.names(), 'after switching to the list, the next Albums row opens the list')
    view_switch(m, 20000000)
    m.call(PSYMS['al_on_destroy'], count=2000000)
    m.calls = []; m.call(on_row, a0=rows0 + 12 * row, count=20000000)
    expect(('window_open', 'm1plus_albums') in m.calls and glyph(m) == 'pod_nav_list', 'and after switching back, the grid')
    m = albums_machine(3); open_grid(m)
    m.calls = []; m.call(PSYMS['albums_open'], count=20000000)
    expect('window_open' not in m.names() and 'stock_resume' not in m.names(), 'the page that is up is neither opened twice nor replaced by the stock list')

    # 16. Hit tests with demo's own widget_find_target on the page: the grid view takes touches under the navbar, the
    #     navbar buttons theirs, and the hidden status line none.
    m = albums_machine(30)
    open_grid(m)
    root = asset_tree(asset)
    for x, y, want in ((160, 60, 'view_grid'), (20, 200, 'view_grid'), (160, 449, 'view_grid'), (40, 25, 'btn_return'),
                       (142, 25, 'label_title'), (122, 25, 'label_title'), (O['NAV_CF_X'] + 20, 25, 'btn_coverflow'),
                       (O['NAV_CF_X'], 25, 'btn_coverflow'), (O['NAV_VIEW_X'] - 1, 25, 'btn_coverflow'),
                       (O['NAV_VIEW_X'] + 20, 25, 'btn_more'), (O['NAV_VIEW_X'], 25, 'btn_more'), (290, 25, 'btn_backtoplayer'), (160, 230, 'view_grid')):
        got = stock_target(m, root, x, y)
        expect(got[-1] == want, f'a touch at ({x},{y}) goes to {want} ({got})')
    expect(all(node(root, nm).flags & F_SENSITIVE == 0 for nm in ('label_status', 'label_row_title', 'label_row_sub')),
           'the status label and the two list-style labels are insensitive')

    # 16b. The Cover Flow button: bound to al_on_cover, which runs the menu row's open (coverflow_open: the playing
    #      album, else the last) over the page; nothing of the Albums page closes, so Cover Flow's Back returns to it.
    for mode in (b'1\n', b'0\n'):
        m = albums_machine(3); m.fs[ALBUMS_FILE] = mode
        for w in COVER_WIDGETS:
            if w not in m.widgets: m.widget(w)
        calls = open_grid(m)
        binds = [c for c in calls if c[0] == 'widget_on' and c[1] == m.widgets['btn_coverflow'] and c[2] == O['EVT_CLICK']]
        expect(len(binds) == 1 and binds[0][3] == PSYMS['al_on_cover'], 'the Cover Flow button is bound to al_on_cover')
        m.calls = []
        m.call(PSYMS['al_on_cover'], count=5000000)
        expect(('window_open', 'm1plus_cover') in m.calls, f'a tap opens m1plus_cover through coverflow_open (mode {mode!r})')
        expect(not [c for c in m.calls if c[0] in ('navigator_back', 'window_close', 'widget_destroy', 'stock_resume', 'navigator_to_with_context')]
               and m.fs.get(ALBUMS_FILE) == mode, 'and the Albums page stays underneath, untouched, its mode unchanged')
    m.calls = []
    m.call(PSYMS['pod_on_back'], count=2000000)
    expect(('navigator_back',) in [c[:1] for c in m.calls] and 'window_open' not in m.names(), 'Back is the navigator\'s: it returns to the page below')


def stock_widget_tests(ctx):
    """18 and 15b: the page on demo's own list_view / scroll_view code, and the navbar's fade."""
    expect = ctx.expect
    # 18. The page on demo's own widget code (SA): the list_view layouter sizes it, the scroll_view drags, flings, catches a coasting list and clamps, the
    #     content view only sees the pointer events the scroll_view passes down. Both modes.
    S = SA.Y0
    FLICK = [('d', 100, S + 300, 0), ('m', 100, S + 270), ('m', 100, S + 200), ('u', 100, S + 150)]       # a quick swipe up that leaves a fling running
    SLOW = [('d', 100, S + 300, 0), ('m', 100, S + 288, 100), ('m', 100, S + 240, 100), ('m', 100, S + 200, 100), ('u', 100, S + 200, 300)]   # a slow drag of 100 px, no fling
    for mode in ('grid', 'list'):
        def pos(a, off, dy=10):
            """A window point inside album a's cell (grid) or row (list) when the scroll view is at off."""
            if mode == 'grid': return MARGIN + (a % COLS) * CPITCH + 10, S + TOP + RGAP + (a // COLS) * PITCH - off + dy
            return 40, S + TOP + a * ROW - off + dy + 10
        def fresh(n=300, cached=False, **kw):
            m = SA(n, mode, cached=cached, **kw)
            m.open()
            return m
        def mid_album(off):
            """An album well inside the window when the list is at off."""
            return (off - TOP + 150) // ROW if mode == 'list' else ((off - TOP + 250) // PITCH) * COLS + 1
        def pressed_fill(m):
            paint(m); return [f for f in m.fills if f[0] == O['LIST_PRESS']]

        # the layouter: the content view at the top of the scroll view, 320 wide, as high as the library; virtual_h is its height (an int for 4000 albums)
        for n_ in (1, 8, 4000):
            m = fresh(n_)
            want_h = TOP + ((RGAP + (n_ + COLS - 1) // COLS * PITCH) if mode == 'grid' else n_ * ROW)
            expect((m.s32(m.view + 4), m.word(m.view + 8), m.s32(m.view + 0xc), m.vh()) == (0, CW, want_h, want_h) and m.s32(m.view) == 0,
                   f'{mode}, {n_} albums: after demo\'s own layout the content view is at (0, 0), {CW} x {want_h} and virtual_h is {m.vh()}')
        # THE REGRESSION (V2.1nX did not scroll on the device): the window's first layout, run by demo's window manager after al_open with the
        # asset's own widgets, must leave the scroll_view vertically slidable. scroll_view_create leaves xslidable / yslidable 0; the only
        # code that sets them is the list_view layouter (0x60b1c8..0x60b1f8) and only for a mobile scroll bar, so an asset without scroll_bar_m
        # never scrolls (the drag below moves nothing, and the stock fling never starts).
        m = fresh()
        expect(tuple(m.u.mem_read(m.sv + O['SC_XSLIDE'], 3)) == (0, 1, 0) and m.word(m.lv + 0x88) == m.bar != 0,
               f'{mode}: after the first layout the scroll_view is yslidable, not xslidable, not snapping (the list_view has its mobile scroll bar)')
        m.play([('d', 100, S + 300, 0), ('m', 100, S + 285, 16), ('m', 100, S + 250, 100)])
        expect(m.off() > 0 and m.dragged(), f'{mode}: the first moves of a drag scroll the list ({m.off()} px)')
        # a slow drag scrolls with the finger and ends without a fling
        m = fresh(cached=True); base = len(file_loads(m))
        calls = m.play(SLOW[:4])
        expect(m.pressed() and m.dragged() and 40 < m.off() <= 100, f'{mode}: a drag of 100 px scrolls the list with the stock drag ({m.off()} px)')
        calls = tick(m); n_dec = len(file_loads(m)) - base
        expect(n_dec == 0 and armed(calls), f'{mode}: a loader tick while the finger drags decodes nothing and polls (stock pressed and dragged flags)')
        m.play(SLOW[4:])
        expect(not m.pressed() and not m.dragged() and m.wa() == 0 and m.opened() == [], f'{mode}: the slow release is no fling and opens nothing')
        got, per = run_loader(m)
        blits, _ = paint(m)
        expect(len(got) >= 4 and per == 1 and len({b[0] for b in blits}) == len(blits), f'{mode}: after the release the loader decodes one cover a tick until every visible cover is resident')
        # a quick swipe leaves the stock fling animator: the loader waits until it ends
        m = fresh(cached=True); base = len(file_loads(m))
        m.play(FLICK)
        wa = m.wa()
        expect(wa != 0 and m.word(wa + 0x28) == 1 and m.fling_target() > m.off() > 0, f'{mode}: a quick swipe starts the scroll animation (to {m.fling_target()}, now at {m.off()})')
        for _ in range(3):
            calls = tick(m)
            expect(len(file_loads(m)) == base and armed(calls), f'{mode}: a loader tick while the animation runs decodes nothing and polls')
        calls = m.finish_fling()
        expect(m.wa() == 0 and m.off() > 0, f'{mode}: the animation ends at its target ({m.off()} px)')
        expect(armed(calls) or armed(tick(m)), f'{mode}: the scroll end re-arms the loader')
        got, per = run_loader(m)
        blits, _ = paint(m)
        expect(len(got) >= 4 and per == 1 and len({b[0] for b in blits}) == len(blits), f'{mode}: and the visible covers are decoded, one a tick')
        urls = file_loads(m)
        expect(len(urls) == len(set(urls)), f'{mode}: nothing was decoded twice')
        # taps
        for a in ((0, 1, 3) if mode == 'grid' else (0, 3, 5)):
            m = fresh()
            x, y = pos(a, 0)
            m.play([('d', x, y, 0), ('u', x, y, 60)])
            expect(m.opened() == [a], f'{mode}: a tap on album {a} opens its album ({m.opened()})')
        m = fresh()
        m.play(SLOW)
        off = m.off()
        a = mid_album(off)
        x, y = pos(a, off)
        m.play([('d', x, y, 0), ('u', x, y, 60)])
        expect(m.opened() == [a] and m.off() == off, f'{mode}: scrolled by {off} px, a tap on album {a} opens album {a}, and the list stays')
        if mode == 'grid':
            m.play([('d', 5, S + 3, 0), ('u', 5, S + 3, 60)])
            expect(m.opened() == [], f'{mode}: a tap on a margin opens nothing')
        # the pressed row (list)
        if mode == 'list':
            m = fresh()
            x, y = pos(3, 0)
            m.play([('d', x, y, 0)])
            expect(pressed_fill(m) == [(0xff343333, 0, TOP + 3 * ROW, CW, ROW - 1)], f'{mode}: a finger down on a row fills it #333334')
            m.play([('u', x, y, 60)])
            expect(not pressed_fill(m) and m.opened() == [3], f'{mode}: the release clears the fill and opens the album')
            m.play([('d', x, y, 0), ('m', x, y - 4), ('m', x, y - 8)])
            expect(pressed_fill(m), f'{mode}: a move under the scroll_view\'s drag threshold keeps the fill')
            m.play([('m', x, y - 30)])
            expect(not pressed_fill(m) and m.dragged(), f'{mode}: the drag (the scroll_view\'s abort) takes the fill away')
            m.play([('u', x, y - 30, 300)])
            expect(m.opened() == [], f'{mode}: the release after a drag opens nothing')
        # a drag never opens an album, however it ends
        for name, steps in (('a slow drag', lambda x, y: [('d', x, y, 0), ('m', x, y - 12, 100), ('m', x, y - 60, 100), ('u', x, y - 60, 300)]),
                            ('a drag back to the press', lambda x, y: [('d', x, y, 0), ('m', x, y - 40, 100), ('m', x, y, 100), ('u', x, y, 100)]),
                            ('a quick flick', lambda x, y: [('d', x, y, 0), ('m', x, y - 9, 16), ('u', x, y - 100, 16)]),
                            ('a release 60 px away with no move', lambda x, y: [('d', x, y, 0), ('u', x, y - 60, 40)]),
                            ('a sideways drag', lambda x, y: [('d', x, y, 0), ('m', x + 60, y, 100), ('u', x + 60, y, 100)])):
            m = fresh()
            x, y = pos(3, 0)
            m.play(steps(x, y))
            expect(m.opened() == [] and not pressed_fill(m), f'{mode}: {name} opens nothing and leaves nothing pressed')
        # a touch on a coasting list stops it and presses nothing (patch/scroll.c); without the hook the stock list clicks
        for hooked in (True, False):
            m = fresh(hook=hooked)
            m.play(FLICK)
            wa, before = m.wa(), m.off()
            x, y = pos(mid_album(before), before)
            m.play([('d', x, y, 100)])
            if hooked: expect(m.wa() == 0 and m.word(wa + 0x28) == 0 and not pressed_fill(m), f'{mode}: a touch on the coasting list stops it and presses nothing')
            m.play([('u', x, y, 60)])
            if hooked: expect(m.opened() == [] and m.off() == before, f'{mode}: and its release opens nothing ({m.off()} = {before})')
            else: expect(m.opened() != [], f'{mode}, stock list without the hook: the same touch opens an album (the hole patch/scroll.c closes)')
            if hooked:
                a = mid_album(m.off())
                x, y = pos(a, m.off())
                m.play([('d', x, y, 100), ('u', x, y, 60)])
                expect(m.opened() == [a], f'{mode}: the next plain tap opens its album ({a})')
        # a drag that starts on the coasting list scrolls it
        m = fresh(); m.play(FLICK); before = m.off()
        m.play([('d', 100, S + 300, 100)] + [('m', 100, S + 300 - 8 * i) for i in range(1, 12)] + [('u', 100, S + 212, 400)])
        expect(m.off() != before and m.opened() == [], f'{mode}: a drag that starts on the coasting list scrolls it from there ({before} -> {m.off()})')
        # the mode switch in place: the first album in view stays at the top, the new content size, a coasting list stopped
        m = fresh()
        m.setword(m.sv + SC_YOFF, 700)
        first_g = ((700 - TOP - RGAP - CELL) // PITCH + 1) * COLS if mode == 'grid' else (700 - TOP) // ROW
        view_switch(m, 40000000); m.relayout()
        want_off = TOP + (first_g * ROW if mode == 'grid' else first_g // COLS * PITCH)
        want_h = TOP + (300 * ROW if mode == 'grid' else RGAP + 150 * PITCH)
        expect((m.off(), m.vh(), m.s32(m.view + 0xc)) == (want_off, want_h, want_h),
               f'{mode} -> other: the first album in view (album {first_g}) stays first: offset {m.off()} = {want_off}, content {m.vh()}')
        view_switch(m, 40000000); m.relayout()
        expect(m.off() == TOP + (first_g // COLS * PITCH if mode == 'grid' else first_g * ROW) and m.vh() == TOP + (RGAP + 150 * PITCH if mode == 'grid' else 300 * ROW),
               f'and back: the same album is first ({m.off()})')
        m = fresh(); m.play(FLICK); wa = m.wa()
        view_switch(m, 40000000); m.relayout()
        expect(m.wa() == 0 and m.word(wa + 0x28) == 0, f'{mode}: the mode switch stops a coasting list')

    # 15b. The navbar's fade (img_nb_fade, built hidden) is shown only while the list is scrolled: hidden at rest, shown at any offset > 0, hidden back at 0, kept across a
    #      mode switch; it stays insensitive; without the widget nothing happens.
    for mode in ('grid', 'list'):
        m = albums_machine(60); m.fs[ALBUMS_FILE] = b'1\n' if mode == 'grid' else b'0\n'
        fade = Machine.widget(m, 'img_nb_fade'); m.props[(fade, 'visible')] = 0
        state = lambda: (m.props.get((fade, 'visible')), m.props.get((fade, 'sensitive'), 0))
        open_grid(m)
        s = [state()]
        scroll_to(m, 1); s.append(state())
        scroll_to(m, 300); s.append(state())
        scroll_to(m, 0); s.append(state())
        expect(s == [(0, 0), (1, 0), (1, 0), (0, 0)], f'{mode}: the fade is hidden at rest, shown (insensitive) when scrolled, hidden again back at 0 ({s})')
        scroll_to(m, 300); view_switch(m, 40000000)
        expect(state() == (1, 0) if scroll_of(m) > 0 else state() == (0, 0), f'{mode}: after a mode switch the fade follows the new offset ({scroll_of(m)}, {state()})')
        m.call(PSYMS['al_on_destroy'], count=2000000)
    m = albums_machine(60); looked = ('widget_lookup', 'img_nb_fade') in open_grid(m); scroll_to(m, 300)
    expect(scroll_of(m) > 0 and looked, 'no fade widget: the page opens and scrolls as before')
    m.call(PSYMS['al_on_destroy'], count=2000000)


# ---------------------------------------------------------------------------
# The background cache build (the shared worker of patch/covercache.c, started by the page a moment after it is up)

def key_of(i): return album_key(f'Artist {i}', f'Album {i}')




def scan_all(m, limit=200):
    """Fires the scan step until it stops re-arming itself; per tick: (cache files checked, re-armed, worker started)."""
    ticks = []
    for _ in range(limit):
        new = fired(m, 'al_on_build_start', 400000000)
        ticks.append((len([c for c in new if c[0] == 'access' and '.m1plus/covers' in c[1]]),
                      any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_build_start'] for c in new),
                      any(c[0] == 'pthread_create' for c in new)))
        if not ticks[-1][1]: break
    return ticks


def background_build_tests(ctx):
    expect = ctx.expect
    START, POLL = PSYMS['al_on_build_start'], PSYMS['al_on_build']

    # 17. Opening arms one one-shot timer for the build; nothing is scanned or started in the open itself.
    m = albums_machine(8, missing={2, 5}, empty={3})
    calls = open_grid(m)
    expect([c for c in calls if c[0] == 'timer_add' and c[1] == START] != [] and 'pthread_create' not in [c[0] for c in calls]
           and build_state(m)['jobs'] == 0, 'the open arms the one-shot start timer and starts no worker')
    expect(not [c for c in calls if c[0] == 'access' and '.m1plus' in str(c[1:])], 'the open does not stat the cache files (the scan waits for the timer)')

    # 17a. Only the albums with neither a picture nor the empty "no art" marker are jobs: 2 and 5 here (3 has its marker).
    new = fired(m, 'al_on_build_start')
    s, jobs = build_state(m), build_jobs(m)
    expect(count_of(m, 'pthread_create') == 1 and s['running'] == 1 and s['mode'] == 0 and s['total'] == 2 and s['done'] == 0,
           f'one worker, CC_MISSING, two jobs ({s})')
    expect(jobs == [(f'/mnt/mmc/m/{i}/1.flac', key_of(i)) for i in (2, 5)], f'the jobs are the missing albums only, 2 then 5 ({jobs})')
    expect(('mkdir', '/mnt/mmc/.m1plus/covers') in new and [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'the cache directory is made and the poll timer runs')
    expect(not [c for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_text_utf8') and c[1] == m.widgets['label_status'] and c[2] not in (0,) and isinstance(c[2], str) and 'Preparing' in c[2]],
           'no Preparing screen: the page shows the grid')

    # 17b. The tiles that showed the placeholder for want of a file pick the new one up as the done counter advances.
    for _ in range(10): tick(m)                              # the window is loaded: 2 and 5 found no file and show the placeholder
    for i in (2, 5): expect(f'file://{art_file(key_of(i))}' not in m.loads, f'album {i}: no file yet, nothing loaded')
    path2, path5 = art_file(key_of(2)), art_file(key_of(5))
    m.setword(PSYMS['cb'] + 4 * 5, 1)                       # the worker has finished album 2 ...
    m.present.add(path2); m.files[path2] = 4096; m.cache_index[path2] = 2
    new = fired(m, 'al_on_build')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == POLL] and not [c for c in new if c[0] == 'pthread_join'], 'a poll with the worker still running re-arms itself')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['al_on_load']], 'the advance re-arms the loader for the tile that had no file')
    for _ in range(6): tick(m)
    expect(f'file://{path2}' in m.loads and f'file://{path5}' not in m.loads, 'album 2\'s cover is decoded now; 5 (not built yet) is not')
    new = fired(m, 'al_on_build')
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['al_on_load']], 'a poll with no advance retries nothing')

    # 17c. The worker finishing ends the build: joined, freed, no further poll; the last cover is picked up.
    m.album_cover = 1
    m.present |= {f'/mnt/mmc/m/{i}/1.flac' for i in range(8)}   # the tracks are on the card
    m.call(PSYMS['cc_worker'], count=5000000)                # (the mock thread runs when asked: it takes up at job 1, album 5)
    m.cache_index[path5] = 5
    new = fired(m, 'al_on_build')
    s = build_state(m)
    expect(s['jobs'] == 0 and s['total'] == 0 and [c for c in new if c[0] == 'pthread_join'] and not [c for c in new if c[0] == 'timer_add' and c[1] == POLL],
           f'done: the worker is joined, the set freed and the poll ends ({s})')
    for _ in range(6): tick(m)
    expect(f'file://{path5}' in m.loads, 'and the last cover is decoded too')

    # 17d. Order: nearest the first album in view first (forward before back), not the library order.
    m = albums_machine(12, missing={0, 7, 11})
    open_grid(m)
    scroll_to(m, TOP + RGAP + CELL + 2 * PITCH)   # scrolled so that album 6 starts the first row in view
    fired(m, 'al_on_build_start')
    order = [int(t.split('/')[4]) for t, _ in build_jobs(m)]
    expect(order == [7, 11, 0], f'jobs go nearest the view first: 7, 11, 0 ({order})')
    m = albums_machine(12, missing={0, 7, 11}); open_grid(m); fired(m, 'al_on_build_start')
    expect([int(t.split('/')[4]) for t, _ in build_jobs(m)] == [0, 7, 11], 'at the top of the page: 0, 7, 11')
    m = albums_machine(12, missing={0, 7, 11}, sort='artist'); open_grid(m); fired(m, 'al_on_build_start')
    expect(sorted(int(t.split('/')[4]) for t, _ in build_jobs(m)) == [0, 7, 11], 'in the Artist order the same albums are the jobs (keys are the albums\')')

    # 17e. Cancel on destroy (the UI thread never joins a worker inside a job; the orphan is reaped after it exits) (also with the one-shot still pending); a late poll does nothing.
    m = albums_machine(8, missing={2, 5}); open_grid(m); fired(m, 'al_on_build_start')
    new = fired(m, 'al_on_destroy', 3000000)
    s = build_state(m)
    expect(not [c for c in new if c[0] == 'pthread_join'] and s['jobs'] != 0 and s['orphan'] == 1 and s['cancelled'] == 1 and s['running'] == 0 and ('timer_remove', 0x777) in new,
           f'destroy with a job in flight cancels without joining: the worker keeps the set, the timer is dropped ({s})')
    jobs_ptr = s['jobs']
    expect(m.call(PSYMS['cc_build_busy']) == 1 and m.call(PSYMS['cc_build_open'], a0=1, a1=0) == 0 and count_of(m, 'pthread_join') == 0 and build_state(m)['jobs'] == jobs_ptr,
           'while the orphan lives cc_build_busy is true and cc_build_open refuses, nothing is joined or freed')
    expect(m.call(PSYMS['cc_build_orphan']) == 1, 'cc_build_orphan says so')
    m.call(PSYMS['cc_build_stop'])
    expect(build_state(m)['jobs'] == jobs_ptr and count_of(m, 'free') == 0, 'a stop by a page that owns nothing leaves the orphan\'s set alone')
    m.present |= {f'/mnt/mmc/m/{i}/1.flac' for i in range(8)}
    m.call(PSYMS['cc_worker'], count=5000000)           # the orphan stops at its cancel flag and exits
    expect(build_state(m)['exited'] == 1 and build_state(m)['jobs'] == jobs_ptr, 'the exited worker has not freed the set itself')
    expect(m.call(PSYMS['cc_build_busy']) == 0, 'the next cc_build_busy reaps it: not busy')
    names = [c[0] for c in m.calls]
    s = build_state(m)
    expect(names.count('pthread_join') == 1 and names.count('free') >= 2 and s['jobs'] == 0 and s['orphan'] == 0 and s['cancelled'] == 0 and s['total'] == 0,
           f'joined once, the tracks and the array freed ({s})')
    expect(m.call(PSYMS['cc_build_open'], a0=1, a1=0) == 1 and build_state(m)['jobs'] != 0 and count_of(m, 'pthread_join') == 0, 'and cc_build_open succeeds again')
    m.call(PSYMS['cc_build_stop'])
    expect(build_state(m)['jobs'] == 0 and count_of(m, 'pthread_join') == 0, 'a set never started is freed without a join')
    m2 = albums_machine(8, missing={2, 5}); open_grid(m2); fired(m2, 'al_on_build_start')
    m2.setword(PSYMS['cb'] + 4 * 5, build_state(m2)['total'])   # every job is done, the thread is only returning
    fired(m2, 'al_on_destroy', 3000000)
    expect(count_of(m2, 'pthread_join') == 1 and build_state(m2)['jobs'] == 0 and build_state(m2)['orphan'] == 0, 'a worker with no job left is joined at once (it cannot be inside one)')
    new = fired(m, 'al_on_build', 1000000)
    expect(not [c for c in new if c[0] in ('timer_add', 'pthread_create', 'widget_invalidate_force')], 'a late poll after close does nothing')
    new = fired(m, 'al_on_build_start', 1000000)
    expect(not [c for c in new if c[0] in ('timer_add', 'pthread_create')], 'nor does a late start')
    m = albums_machine(8, missing={2, 5}); open_grid(m)
    new = fired(m, 'al_on_destroy', 3000000)
    expect(('timer_remove', 0x777) in new and 'pthread_create' not in [c[0] for c in new] and build_state(m)['jobs'] == 0,
           'destroy before the start timer fired removes it; no worker was ever made')

    # 17f. One worker at a time. Albums holds it: Cover Flow (the navbar button) takes it over by releasing Albums' first;
    #      Cover Flow holds it: Albums starts nothing.
    m = albums_machine(6, missing={1, 4})
    for w in COVER_WIDGETS:
        if w not in m.widgets: m.widget(w)
    open_grid(m); fired(m, 'al_on_build_start')
    expect(count_of(m, 'pthread_create') == 1 and build_state(m)['running'] == 1, 'Albums runs the worker')
    new = fired(m, 'al_on_cover', 6000000)
    names = [c[0] for c in new]
    expect('pthread_join' not in names and 'pthread_create' not in names and ('window_open', 'm1plus_cover') in new and build_state(m)['orphan'] == 1
           and [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['on_retry']],
           'the Cover Flow button orphans Albums\' worker without joining; Cover Flow shows Preparing and asks again')
    m.call(PSYMS['cc_worker'], count=5000000)           # the orphan exits
    new = fired(m, 'on_retry', 6000000)
    names = [c[0] for c in new]
    expect(names.count('pthread_join') == 1 and names.count('pthread_create') == 1 and build_state(m)['running'] == 1 and build_state(m)['orphan'] == 0,
           'the retry reaps the orphan (one join) and Cover Flow starts its own worker (one at a time)')
    m = albums_machine(6, missing={1, 4})
    for w in COVER_WIDGETS:
        if w not in m.widgets: m.widget(w)
    open_grid(m); fired(m, 'al_on_build_start'); fired(m, 'al_on_cover', 6000000)
    m.clock += 10000                                     # the worker never comes back out of its job
    new = fired(m, 'on_retry', 6000000)
    expect(m.call(PSYMS['cc_build_orphan']) == 0 and build_state(m)['orphan'] == 1 and not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['on_retry']]
           and 'view' in [c[0] for c in new],
           'a worker that stays in its job for 10 s: Cover Flow stops asking and shows the covers')
    m = albums_machine(6, missing={1, 4})
    for w in COVER_WIDGETS:
        if w not in m.widgets: m.widget(w)
    m.call(PSYMS['coverflow_open'], count=6000000)
    expect(count_of(m, 'pthread_create') == 1 and build_state(m)['running'] == 1, 'Cover Flow builds its Preparing set')
    open_grid(m)
    new = fired(m, 'al_on_build_start')
    expect(not [c for c in new if c[0] in ('pthread_create', 'mkdir', 'timer_add')],
           'with Cover Flow holding the worker, Albums starts nothing (no second thread, no poll)')
    expect(build_state(m)['total'] == 2 and build_state(m)['running'] == 1, 'and leaves Cover Flow\'s jobs alone')
    new = fired(m, 'al_on_destroy', 3000000)
    expect(not [c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] != 0, 'closing Albums does not stop a worker it does not own')

    # 17g. No space, no thread, nothing missing, no timer: no worker, nothing left held.
    m = albums_machine(8, missing={2}); m.free_mb = 2; open_grid(m); fired(m, 'al_on_build_start')
    expect(count_of(m, 'pthread_create') == 0 and build_state(m)['jobs'] == 0 and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == POLL], 'a full card: no worker')
    m = albums_machine(8, missing={2}); m.thread_ok = False; open_grid(m); fired(m, 'al_on_build_start')
    expect(build_state(m)['jobs'] == 0 and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == POLL], 'a refused thread: the set is freed')
    m = albums_machine(8); open_grid(m); fired(m, 'al_on_build_start')
    expect(count_of(m, 'pthread_create') == 0 and ('mkdir', '/mnt/mmc/.m1plus/covers') not in m.calls and build_state(m)['jobs'] == 0, 'a complete cache: nothing to do, no thread, no mkdir')
    m = albums_machine(8, missing={2}); open_grid(m)
    m.timer_fail = True; fired(m, 'al_on_build_start')
    expect(count_of(m, 'pthread_create') == 1 and count_of(m, 'pthread_join') == 0 and build_state(m)['orphan'] == 1 and build_state(m)['jobs'] != 0,
           'a poll timer that cannot be made: the worker is cancelled and orphaned, not joined')
    m = albums_machine(8, missing={2}); open_grid(m); fired(m, 'al_on_build_start')
    m.timer_fail = True; fired(m, 'al_on_build')
    expect(count_of(m, 'pthread_join') == 0 and build_state(m)['orphan'] == 1, 'a refused re-arm: cancelled and orphaned, not joined')
    m.call(PSYMS['cc_worker'], count=5000000); m.call(PSYMS['cc_build_busy'])
    expect(count_of(m, 'pthread_join') == 1 and build_state(m)['jobs'] == 0, 'once it has exited: joined and freed')

    # 17h. Back in front (Cover Flow, an album page closed): the build is offered again, once; not while one runs.
    m = albums_machine(8, missing={2}); open_grid(m)
    expect([b for b in m.calls if b[0] == 'widget_on' and b[2] == O['EVT_WINDOW_TO_FG'] and b[3] == PSYMS['al_on_fg']] != [], 'the window\'s foreground event is bound')
    fired(m, 'al_on_build_start')
    expect(not [c for c in fired(m, 'al_on_fg', 1000000) if c[0] == 'timer_add'], 'foreground while the worker runs arms nothing')
    m.call(PSYMS['cc_worker'], count=5000000)
    fired(m, 'al_on_build')
    expect([c for c in fired(m, 'al_on_fg', 1000000) if c[0] == 'timer_add' and c[1] == START], 'foreground with the worker idle arms the start again')
    expect(not [c for c in fired(m, 'al_on_fg', 1000000) if c[0] == 'timer_add'], 'and only once while it is pending')

    # 17i. List mode and a big library are bounded: the job set never exceeds CC_MAX_JOBS.
    m = albums_machine(300, cached=False); m.fs[ALBUMS_FILE] = b'0\n'; open_grid(m); scan_all(m)
    s = build_state(m)
    expect(s['total'] == 300 and s['cap'] == 300, f'300 missing albums in list mode: 300 jobs ({s})')
    m.call(PSYMS['al_on_destroy'], count=3000000)
    m = albums_machine(4100, cached=False); open_grid(m); scan_all(m)
    s = build_state(m)
    expect(s['total'] == 4000 and s['cap'] == 4000, f'4100 missing albums: the job set is bounded at CC_MAX_JOBS ({s["total"]}/{s["cap"]})')
    m.call(PSYMS['al_on_destroy'], count=3000000)

    # 17j. The scan is bounded per tick (review 1): a fully cached 1000-album library is checked 64 albums a tick, yields
    #      between ticks, finds nothing missing, starts no worker, and a return to the page does not scan again.
    BATCH = 64
    m = albums_machine(1000); open_grid(m)
    ticks = scan_all(m)
    per = [t[0] for t in ticks]
    expect(len(per) == 16 and max(per) <= BATCH and sum(per) == 1000, f'1000 cached albums: 16 ticks of at most {BATCH} file checks ({per})')
    expect(all(t[1] for t in ticks[:-1]) and not ticks[-1][1], 'every tick but the last re-arms the scan timer; the last does not')
    expect(count_of(m, 'pthread_create') == 0 and build_state(m)['jobs'] == 0, 'nothing missing: no worker, the set is freed')
    expect(not [c for c in fired(m, 'al_on_fg', 1000000) if c[0] == 'timer_add'], 'returning to the page after a complete scan arms no rescan')
    m.call(PSYMS['al_on_destroy'], count=3000000)
    open_grid(m)
    expect([c for c in m.calls if c[0] == 'timer_add' and c[1] == START], 'a new page open scans again (the library may have changed)')
    m.call(PSYMS['al_on_destroy'], count=3000000)

    # 17k. Missing albums: the order is still nearest the view first across the ticks, the worker starts after the last tick
    #      only, and a scan that found something missing is offered again on the next foreground.
    m = albums_machine(200, missing={0, 150, 199, 100}); open_grid(m)
    scroll_to(m, TOP + RGAP + CELL + 2 * PITCH)   # first album in view: 6
    ticks = scan_all(m)
    order = [int(t.split('/')[4]) for t, _ in build_jobs(m)]
    expect(order == [0, 100, 150, 199],f'jobs across ticks: nearest album 6 first ({order})')
    created = [i for i, t in enumerate(ticks) if t[2]]
    expect(created == [len(ticks) - 1], f'the worker starts in the last scan tick only ({created} of {len(ticks)})')
    m.call(PSYMS['cc_worker'], count=5000000)
    fired(m, 'al_on_build')
    expect([c for c in fired(m, 'al_on_fg', 1000000) if c[0] == 'timer_add' and c[1] == START], 'an incomplete cache is offered again at foreground')
    m.call(PSYMS['al_on_destroy'], count=3000000)

    # 17l. Destroy in the middle of a scan: the timer is removed, the set freed, no worker; a late step does nothing.
    m = albums_machine(500, missing={400}); open_grid(m)
    fired(m, 'al_on_build_start')
    new = fired(m, 'al_on_destroy', 3000000)
    expect(('timer_remove', 0x777) in new and build_state(m)['jobs'] == 0 and count_of(m, 'pthread_create') == 0, 'destroy mid-scan drops the timer and the set')
    new = fired(m, 'al_on_build_start', 1000000)
    expect(not [c for c in new if c[0] in ('timer_add', 'pthread_create', 'access')], 'a late scan step does nothing')

    # 17m. The Cover Flow button mid-scan releases the set (one worker at a time) and scans no further.
    m = albums_machine(500, missing={400}); open_grid(m)
    for w in COVER_WIDGETS:
        if w not in m.widgets: m.widget(w)
    fired(m, 'al_on_build_start')
    expect(build_state(m)['jobs'] != 0, 'a scan under way holds the job set')
    fired(m, 'al_on_cover', 6000000)
    new = fired(m, 'al_on_build_start', 1000000)
    expect(not [c for c in new if c[0] == 'access'], 'after the Cover Flow button no scan step runs')

    # 17n. The worker checks the cancel flag after taking the parser mutex: no extraction, no marker, no file.
    m = albums_machine(4, missing={1, 2}); open_grid(m); fired(m, 'al_on_build_start')
    m.present |= {f'/mnt/mmc/m/{i}/1.flac' for i in range(4)}
    m.on_lock = lambda: m.setword(PSYMS['cb'] + 4 * 7, 1)   # cancelled while the worker waits for the parser mutex
    m.call(PSYMS['cc_worker'], count=5000000)
    names = [c[0] for c in m.calls]
    expect('lock' in names and 'unlock' in names and not [c for c in m.calls if c[0] in ('toolsGetAlbumCover', 'toolsGetExternCover') or c[0] == 'fopen' and not c[1].endswith('.inflight')],
           'cancelled while waiting for the parser: unlocked, nothing extracted, no marker written')


def foreground_loader_tests(ctx):
    expect = ctx.expect
    m = albums_machine(); open_grid(m)
    m.fire(O['EVT_WINDOW_TO_BG'], m.window)
    expect(not any(c[0] in ('pthread_join', 'pthread_cancel') for c in m.calls), 'background does not join or cancel the cache worker')
    calls = tick(m)
    expect(not any(c[0] in ('widget_load_image', 'widget_invalidate_force', 'timer_add') for c in calls),
           'a stray loader callback in the background does no work and does not rearm')
    calls = fired(m, 'al_on_fg')
    expect(armed(calls), 'foreground resumes the missing tile loader')
    calls = tick(m)
    expect(any(c[0] == 'widget_load_image' for c in calls), 'the resumed loader decodes a tile')
    for ev in ('EVT_WINDOW_TO_FG', 'EVT_WINDOW_TO_BG'):
        m = albums_machine(); m.widget_on_fail = frozenset({O[ev]}); open_grid(m)
        calls = tick(m)
        expect(any(c[0] == 'widget_load_image' for c in calls), f'{ev} registration failure does not strand the loader')
        if ev == 'EVT_WINDOW_TO_FG':
            expect(m.bound[(m.window, O['EVT_WINDOW_TO_BG'])][0] == PSYMS['al_on_abort'], 'fallback only clears presses')
    m = albums_machine(); m.widget_on_fail = frozenset({O['EVT_WINDOW_TO_FG']}); open_grid(m)
    expect(m.bound.get((m.window, O['EVT_WINDOW_TO_BG']), (0,))[0] == PSYMS['al_on_abort'], 'foreground registration failure still binds the press abort')
    gesture(m, [('down', 40, 40, 1000)]); m.fire(O['EVT_WINDOW_TO_BG'], m.window)
    calls = gesture(m, [('up', 40, 40, 1080)])
    expect(not any(c[0] == 'navigator_to_with_context' for c in calls), 'fallback background abort clears the pending press')
    expect(any(c[0] == 'widget_load_image' for c in tick(m)), 'fallback background leaves loader active')

# ---------------------------------------------------------------------------
# The navbar's "..." card (patch/viewsort.c, docs/modules/albums.md "The ... card"): sort rows, view row, the saved order.
SORT_FILE, SORT_TMP = '/mnt/data/m1plus/albums-sort', '/mnt/data/m1plus/albums-sort.tmp'
# (album, artist) in the stock rows' order (the mock's own, not sorted: Title sorts them)
SORT_LIB = [('Alpha', 'Zed'), ('beta', 'Yan'), ('Gamma', 'Zed'), ('Delta', 'The Xu'), ('Epsilon', 'Wu')]
# the library's songs, newest first (time_create desc): (album, year): Gamma, Alpha 1999, a song with no album, Epsilon, Alpha 1971, Delta (no year), Beta 2005 (the names differ in case from the rows: NOCASE)
SORT_SONGS = [('gamma', 1985), ('Alpha', 1999), ('', 2020), ('EPSILON', 2010), ('Alpha', 1971), ('Delta', 0), ('Beta', 2005)]
SORT_ORDERS = {0: [0, 1, 3, 4, 2],     # Title: Alpha, beta, Delta, Epsilon, Gamma (our name keys, case folded)
               1: [4, 3, 1, 0, 2],     # Artist: Wu, Xu (the "The " ignored), Yan, Zed / Alpha, Zed / Gamma
               2: [2, 0, 4, 3, 1],     # Recently Added: by each album's newest song (Gamma, Alpha, Epsilon, Delta, beta)
               3: [4, 1, 2, 0, 3]}     # Year: newest first by the earliest year tag (Epsilon 2010, beta 2005, Gamma 1985, Alpha 1971), Delta (none) last


def sort_machine(specs=SORT_LIB, songs=SORT_SONGS, list_mode=True, cls=Machine, **files):
    m = albums_machine(0, cls=cls)
    m.showlist = [m.record(album=a, artist=r, path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i, (a, r) in enumerate(specs)]
    rows = []
    for i, (album, year) in enumerate(songs):
        r = m.record(album=album, artist='x', path=f'/mnt/mmc/s/{i}.flac', rid=100 + i)
        m.setword(r + O['REC_YEAR'], year); rows.append(r)
    m.class_lists[O['CLASS_ALL_SONGS']] = rows
    m.fs.pop(SORT_FILE, None)   # the page's world uses the stock order; here the file is missing (the default, Artist) unless a test gives it
    if list_mode: m.fs[ALBUMS_FILE] = b'0\n'
    for k, v in files.items(): m.fs[k] = v
    return m


def shown(m):
    """The album titles in the list's rows, top to bottom."""
    blits, texts = paint(m)
    return [t[0] for t, sty in sorted(zip(texts, m.text_styles), key=lambda p: p[0][1][1]) if sty == 'label_row_title']


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def ticks(m): return [vis(m, f'vs_tick{i}')[0] for i in range(VS_SORTS)]
def vticks(m): return [vis(m, f'vs_tick{i}')[0] for i in (VS_SORTS, VS_SORTS + 1)]   # Grid, List


def subs(m):
    """Each sort row's second line: its text (the last widget_set_tr_text of the call log) when shown, None when hidden."""
    out = []
    for i in range(VS_SORTS):
        said = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'vs_sub{i}']]
        out.append((utf8(said[-1]) if said else '?') if vis(m, f'vs_sub{i}')[0] else None)
    return out


# the saved file's character: the order's digit, its letter (a..d) when the direction is reversed
REV_ORDERS = {0: [2, 4, 3, 1, 0],   # Z-A
              1: [2, 0, 1, 3, 4],   # Z-A by artist
              2: [1, 3, 4, 0, 2],   # Oldest First: beta, Delta, Epsilon, Alpha, Gamma
              3: [0, 2, 1, 4, 3]}   # Oldest First: Alpha 1971, Gamma 1985, beta 2005, Epsilon 2010, Delta (no year) last
SUB_UP = {0: 'A–Z', 1: 'A–Z', 2: 'Newest First', 3: 'Newest First'}
SUB_DOWN = {0: 'Z–A', 1: 'Z–A', 2: 'Oldest First', 3: 'Oldest First'}
def rev_file(k): return (chr(ord('a') + k) + '\n').encode()
def titles(order): return [SORT_LIB[i][0] for i in order]


def card_asset_tests(ctx):
    expect = ctx.expect
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin')
    tree = awtk_ui.parse(open(asset, 'rb').read())
    scrim, card = tree.find('vs_scrim'), tree.find('vs_card')
    gw, gh, gr = mod_icons.GLASS_VIEWSORT
    expect(scrim.get('visible') == card.get('visible') == 'false' and scrim.get('enable') == 'true' and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450)
           and all(scrim.get(f'style:{st}:bg_color') == '#00000082' for st in ('normal', 'pressed', 'over')),
           'the scrim covers the window, dims it like the Playlists menu (#00000082) and starts hidden')
    expect((card.x, card.y, card.w, card.h) == (O['PL_CARD_RIGHT'] - O['PL_CARD_MAX'], O['PL_CARD_Y'], O['PL_CARD_MAX'], gh) == (19, 52, 292, 7 * 48)
           and all(card.get(f'style:{st}:bg_image') == 'vs_glass7' and card.get(f'style:{st}:bg_image_draw_type') == 'patch3_x' and card.get(f'style:{st}:bg_color') == '#00000000' for st in ('normal', 'pressed', 'over')),
           'the card is at its widest (right edge 311, top y 52), Search, Grid, List and four sorts: seven 48 px rows = 336 px high, drawn in its own glass vs_glass7 with patch3_x and no fill')
    for name, (w_, h_, r_) in (('vs_glass7', mod_icons.GLASS_VIEWSORT), ('vs_glass6', mod_icons.GLASS_VIEWSORT6), ('vs_glass5', mod_icons.GLASS_VIEWSORT5)):
        raw = open(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/images/xx/{name}.png'), 'rb').read()
        gen = mod_icons.glass_image(w_, h_, r_, fill=mod_icons.GLASS_SHEET_FILL)
        expect(raw == open(os.path.join(mod_icons.PNG, f'{name}.png'), 'rb').read() and same_pixels(raw, gen) and (w_, r_) == (72, O['PL_CARD_R']),
               f'{name}.png is the generator output pixel for pixel ({w_} x {h_}, r {r_}, the sheet\'s fill)')
    expect(mod_icons.GLASS_VIEWSORT[1] == 7 * 48 and mod_icons.GLASS_VIEWSORT6[1] == 6 * 48 and mod_icons.GLASS_VIEWSORT5[1] == 5 * 48
           and not [n for n in ('vs_glass',) if os.path.exists(os.path.join(mod_icons.PNG, n + '.png')) or os.path.exists(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/images/xx/{n}.png'))],
           'the glasses are seven rows (library), six rows (the scoped page) and five rows (the Songs library) high; the old vs_glass name is gone')
    order = (6, 4, 5, 0, 1, 2, 3)   # the rows top to bottom: Search, Grid, List, then the sorts
    items = {i: tree.find(f'vs_item{i}') for i in order}
    expect([items[i].y for i in order] == [0, 48, 96, 144, 192, 240, 288] and all(it.h == 48 and it.w == 292 and it.type == 'button' for it in items.values())
           and all(it.get('style:pressed:bg_color') == '#FFFFFF10' and it.get('style:normal:bg_color') == '#00000000' for it in items.values()),
           'seven 48 px rows, Search above the View group (Grid, List) above the Sort group: transparent, pressed 6 % white')
    hair = tree.find('vs_hair')
    expect([items[i].get('style:normal:border_width') for i in order] == ['0', '0', '0', '1', '0', '0', '0'] and items[0].get('style:normal:border_color') == '#FFFFFF22'
           and all(items[i].get('style:normal:border_color') == '#00000000' for i in (6, 4, 5, 1, 2, 3)),
           'a 13 % white hairline above the first sort row (between the View and Sort groups); none between the rows of a group')
    expect(hair is not None and hair.type == 'view' and (hair.x, hair.y, hair.w, hair.h) == (0, 48, 292, 1) and hair.get('sensitive') == 'false' and hair.get('style:normal:bg_color') == '#FFFFFF22'
           and hair in card.children and [(w.name, w.y) for w in items.values() if w.y == hair.y] == [('vs_item4', 48)],
           'the second hairline is its own insensitive 1 px widget vs_hair at y 48, under Search and above Grid (the Search row is optional: the helper hides it with the row)')
    expect(tree.find('vs_sep') is None and tree.find('vs_glyph') is None, 'no separator widget and no single view glyph')
    keys = {i: tree.find(f'vs_label{i}') for i in range(7)}
    expect([keys[i].get('tr_text') for i in range(7)] == ['Title', 'Artist', 'Recently Added', 'Year', 'Grid', 'List', 'Search Albums'] and all(k.get('sensitive') == 'false' for k in keys.values())
           and [keys[i].x for i in range(7)] == [38, 38, 38, 38, 66, 66, 66] and all(k.get('style:normal:font_size') == '18' for k in keys.values()),
           'the labels are Title, Artist, Recently Added, Year, Grid, List and Search Albums (their keys), 18 px, insensitive, from x 38 (x 66 after a glyph)')
    ticks_ = {i: tree.find(f'vs_tick{i}') for i in range(6)}
    expect(all(w.get('image') == 'sg_tick' and w.get('visible') == 'false' and (w.x, w.y, w.w) == (14, 17, 14) for w in ticks_.values()),
           'a hidden tick (the Songs card\'s image) at x 14 on every row but Search (it has none): the left column')
    expect(tree.find('vs_tick6') is None, 'the Search row has no tick')
    g = {i: tree.find(f'vs_glyph{i}') for i in (4, 5, 6)}
    expect([(g[i].x, g[i].w, g[i].get('image'), g[i].get('sensitive')) for i in (4, 5, 6)] == [(38, 20, 'pod_ic_vsgrid', 'false'), (38, 20, 'pod_ic_vslist', 'false'), (38, 20, 'pod_ic_vssearch', 'false')],
           'the View rows and the Search row carry their 20 px glyph at x 38 (10 px after the 14 px tick column)')
    subs_ = {i: tree.find(f'vs_sub{i}') for i in range(4)}
    expect(all(s.get('visible') == 'false' and s.get('sensitive') == 'false' and s.x == 38 and s.get('style:normal:font_size') == '15' and s.get('style:normal:text_color') == '#AAAAAA'
               for s in subs_.values()), 'each sort row has a hidden, insensitive 15 px grey second line (the direction) from x 38')
    expect(all(keys[i] in items[i].children and ticks_[i] in items[i].children for i in range(6)) and keys[6] in items[6].children and all(subs_[i] in items[i].children for i in range(4))
           and all(g[i] in items[i].children for i in (4, 5, 6)), 'each label, tick, glyph and second line is inside its row')
    expect(b'sg_glass' not in open(asset, 'rb').read() and b'pl_glass' not in open(asset, 'rb').read(), 'the Albums window no longer uses the Songs sort glass or the Playlists glass')
    png = os.path.join(mod_icons.PNG, 'pl_glass.png')
    expect(os.path.exists(png), 'the Playlists glass is still there for its own users')


def sort_card_tests(ctx):
    """The "..." card at run time: opening, the ticks, each order, the saved choice, the view row, Search, a late event, the fit."""
    expect = ctx.expect
    m = sort_machine(); open_grid(m)
    expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0), 'the card starts hidden and insensitive')
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_scrim') == (1, 1), 'the "..." button opens the card and the scrim')
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0), 'a second tap closes them')
    m.click('btn_more'); m.click('vs_scrim')
    expect(vis(m, 'vs_card') == (0, 0), 'the scrim closes the card')
    # a page that never chose is Artist
    m = sort_machine(); open_grid(m); m.click('btn_more')
    expect(ticks(m) == [0, 1, 0, 0] and shown(m) == titles(SORT_ORDERS[1]), 'no albums-sort file: the default, Artist, is ticked and shown')
    m = sort_machine(**{OLD_ORDER_FILE: b'0\n'}); open_grid(m); m.click('btn_more')
    expect(ticks(m) == [1, 0, 0, 0] and shown(m) == titles(SORT_ORDERS[0]) and m.fs.get(SORT_FILE) == b'0\n' and OLD_ORDER_FILE not in m.fs,
           'no albums-sort file and a retired album-order "0": moved into albums-sort once, Title is ticked and shown')
    expect(not [c for c in m.calls if c[0] == 'loadLocalClassList' and c[1] == O['CLASS_ALL_SONGS']], 'Title and Artist read no song list')
    # each order, from the saved file at open (it wins over a retired album-order file)
    for k, order in SORT_ORDERS.items():
        for data in (f'{k}\n'.encode(), f'{k}'.encode()):
            m = sort_machine(**{SORT_FILE: data, OLD_ORDER_FILE: b'0\n' if k else b'1\n'}); open_grid(m); m.click('btn_more')
            expect(shown(m) == titles(order) and ticks(m) == [int(i == k) for i in range(4)], f'albums-sort {data!r}: the order {order} and the tick on row {k}')
    for bad in (b'', b'4\n', b'x', b'-1'):
        m = sort_machine(**{SORT_FILE: bad}); open_grid(m)
        expect(shown(m) == titles(SORT_ORDERS[1]), f'a garbage albums-sort file ({bad!r}) is Artist')
    # a row sets the order: saved atomically, the list reordered from the top, the card closed, the tick moved
    m = sort_machine(); open_grid(m); settle(m)
    for k in (2, 3, 0, 1):
        m.calls = []; m.click('btn_more'); m.click(f'vs_item{k}')
        expect(m.fs.get(SORT_FILE) == f'{k}\n'.encode() and SORT_TMP not in m.fs and ('rename', SORT_TMP, SORT_FILE) in m.calls, f'row {k}: saved atomically')
        expect(vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0) and scroll_of(m) == 0, f'row {k}: the card closes, the list is at the top')
        expect(shown(m) == titles(SORT_ORDERS[k]), f'row {k}: the list is in the order {SORT_ORDERS[k]} ({shown(m)})')
        m.click('btn_more')
        expect(ticks(m) == [int(i == k) for i in range(4)], f'row {k}: the tick is on it when the card opens again'); m.click('vs_scrim')
    # Recently Added and Year read the song list once, newest first (sort_flag 3), and put the flag and the browsing class back
    m = sort_machine(); open_grid(m)
    flag0, cls0 = m.word(pod.DATA['SORT_FLAG'][0]), m.word(pod.DATA['G_CLASS_TYPE'][0])
    m.calls = []; m.click('btn_more'); m.click('vs_item2')
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ALL_SONGS']] and m.word(pod.DATA['SORT_FLAG'][0]) == flag0 and m.word(pod.DATA['G_CLASS_TYPE'][0]) == cls0,
           'Recently Added reads the library song list once, and sort_flag and the browsing class are as they were')
    m.calls = []; m.click('btn_more'); m.click('vs_item2')
    expect(m.fs.get(SORT_FILE) == b'c\n' and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ALL_SONGS']], 'the row already ticked flips its direction (saved as its letter) and the order is made again')
    # no songs: no ranks, the albums keep the stock (title) order
    m = sort_machine(songs=(), **{SORT_FILE: b'3\n'}); open_grid(m)
    expect(shown(m) == titles(range(5)), 'with no song list Year (and Recently Added) leave the stock order')
    # a tap opens the stock row of the album at that position
    m = sort_machine(**{SORT_FILE: b'2\n'}); open_grid(m)
    calls = tap_at(m, 100, TOP + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], SORT_ORDERS[2][0]) in calls, f'a tap on the first row (Gamma) opens stock row {SORT_ORDERS[2][0]}')
    calls = tap_at(m, 100, TOP + 3 * ROW + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], SORT_ORDERS[2][3]) in calls, f'a tap on the fourth row opens stock row {SORT_ORDERS[2][3]}')
    # the view row names the view a tap switches to and switches it in place, saving the mode; the order is not touched
    for start in (0, 1):   # 0: the page is a grid, 1: a list
        mk = lambda: sort_machine(**{SORT_FILE: b'2\n'})
        m = mk(); m.fs[ALBUMS_FILE] = b'0\n' if start else b'1\n'; open_grid(m); m.click('btn_more')
        expect(vticks(m) == ([0, 1] if start else [1, 0]), f'the View group ticks the current view ({"List" if start else "Grid"})')
        m.calls = []; m.click('vs_item4' if start else 'vs_item5')
        expect(m.fs.get(ALBUMS_FILE) == (b'1\n' if start else b'0\n') and m.fs.get(SORT_FILE) == b'2\n' and vis(m, 'vs_card') == (0, 0)
               and ('widget_resize', m.widgets['view_grid'], 320, TOP + (5 * ROW if not start else 3 * PITCH + RGAP)) in m.calls,
               'the other view row switches the mode in place, saves it in albums-view, leaves the order alone and closes the card')
        m.click('btn_more')
        expect(vticks(m) == ([1, 0] if start else [0, 1]), 'the tick moved to the new view')
        m = mk(); m.fs[ALBUMS_FILE] = b'0\n' if start else b'1\n'; open_grid(m); m.click('btn_more'); m.calls = []
        m.click('vs_item5' if start else 'vs_item4')
        expect(not [c for c in m.calls if c[0] in ('widget_resize', 'rename')] and m.fs[ALBUMS_FILE] == (b'0\n' if start else b'1\n') and vis(m, 'vs_card') == (0, 0),
               'a tap on the ticked view changes nothing and closes the card')
    # Search; a late card event after the page closed does nothing
    m = sort_machine(); open_grid(m)
    m.click('btn_more'); m.calls = []
    m.click('vs_item6', count=20000000)
    expect(('window_open', 'm1plus_search') in m.calls and vis(m, 'vs_card') == (0, 0) and vis(m, 'vs_scrim') == (0, 0),
           'the card\'s first row, Search Albums, closes the card and opens the search page')
    m = sort_machine(); open_grid(m); m.windows['m1plus_search'] = 0; m.click('btn_more'); m.calls = []
    m.click('vs_item6', count=20000000)
    expect(vis(m, 'vs_card') == (0, 0) and m.calls.count(('window_open', 'm1plus_search')) == 2 and m.fs.get(SORT_FILE) is None,
           'a Search page that will not open scoped falls back to the library search (search_open: a second try, as the button did), the card closed, the order untouched')
    m = sort_machine(); open_grid(m); m.call(PSYMS['al_on_destroy'], count=2000000); m.calls = []
    m.call(PSYMS['al_on_item'], a0=2, count=2000000); m.call(PSYMS['al_on_item'], a0=6, count=2000000); m.call(PSYMS['al_on_more'], count=2000000)
    expect(not m.calls and SORT_FILE not in m.fs, 'a late card event after the page closed does nothing')
    # the card's width follows the language: the widest label (or second line) + its x + 16, 206 .. 292, the right edge 311 under the glass; unmeasurable keeps the asset's width
    m = sort_machine(cls=ListMachine); open_grid(m)
    for i, t in enumerate(('Title', 'Artist', 'Recently Added', 'Year', 'Grid', 'List', 'Search Albums')): m.wtext[m.widgets[f'vs_label{i}']] = t
    for i in range(4): m.wtext[m.widgets[f'vs_sub{i}']] = 'A–Z'

    def fit(widest):
        m.measure = lambda t: widest if t == 'Recently Added' else 40
        m.calls = []; m.click('btn_more')
        card = m.widgets['vs_card']
        mv = [tuple(c[2:]) for c in m.calls if c[0] == 'widget_move' and c[1] == card]
        rs = [tuple(c[2:]) for c in m.calls if c[0] == 'widget_resize' and c[1] == card]
        lab = [c[2] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['vs_label2']]
        m.click('btn_more')
        return mv, rs, lab
    for widest, w in ((60, 206), (130, 206), (200, 254), (300, 292)):
        mv, rs, lab = fit(widest)
        expect(mv == [(311 - w, 52)] and rs == [(w, 336)] and lab == [w - 38 - 16], f'a widest label of {widest} px: a card {w} px wide (38 + the label + 16, 206 .. 292), 336 px high, right edge 311 ({mv} {rs} {lab})')
    m.measure = lambda t: 150 if t == 'Search Albums' else 40
    m.calls = []; m.click('btn_more')
    rs = [tuple(c[2:]) for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['vs_card']]
    pos = [tuple(c[2:]) for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets['vs_item6']]
    hr = [tuple(c[2:]) for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] == m.widgets['vs_hair']]
    expect(rs == [(232, 336)] and pos == [(0, 0)] and hr == [(0, 48), (232, 1)],
           f'the Search row counts, from its glyph x 66: 66 + 150 + 16 = 232 wide; it is the first row, the hairline under it at y 48 ({rs} {pos} {hr})')
    m.click('btn_more')
    m.measure = lambda t: 0
    m.calls = []; m.click('btn_more')
    expect(not [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] == m.widgets['vs_card']] and vis(m, 'vs_card') == (1, 1), 'a label that cannot be measured leaves the asset\'s width, and the card opens')


def reverse_tests(ctx):
    """Reversible sorts (docs/modules/albums.md): the ticked sort row's second line, a tap on it flips the direction, the saved letter, a new order starts in its default direction."""
    expect = ctx.expect
    for k in range(4):
        m = sort_machine(**{SORT_FILE: f'{k}\n'.encode()}); open_grid(m); m.calls = []; m.click('btn_more')
        expect(subs(m) == [SUB_UP[k] if i == k else None for i in range(4)] and ticks(m) == [int(i == k) for i in range(4)],
               f'order {k} saved with its digit: its row alone shows "{SUB_UP[k]}" ({subs(m)})')
        m = sort_machine(**{SORT_FILE: rev_file(k)}); open_grid(m); m.calls = []; m.click('btn_more')
        expect(subs(m) == [SUB_DOWN[k] if i == k else None for i in range(4)] and ticks(m) == [int(i == k) for i in range(4)] and shown(m) == titles(REV_ORDERS[k]),
               f'order {k} saved with its letter: reversed ({REV_ORDERS[k]}), its row alone shows "{SUB_DOWN[k]}" ({subs(m)}, {shown(m)})')
    m = sort_machine(); open_grid(m); m.calls = []; m.click('btn_more')
    expect(subs(m) == [None, 'A\u2013Z', None, None], 'no file: Artist, A\u2013Z')
    for bad in (b'e\n', b'A\n', b'ar', b'a\n\n'):
        m = sort_machine(**{SORT_FILE: bad}); open_grid(m)
        expect(shown(m) == titles(SORT_ORDERS[1]), f'a garbage albums-sort file ({bad!r}) is Artist, not reversed')
    # a tap on the ticked row flips, saves atomically, reorders from the top, closes the card; a second tap flips back
    m = sort_machine(); open_grid(m); settle(m)
    for k in range(4):
        m.click('btn_more'); m.click(f'vs_item{k}')
        expect(m.fs[SORT_FILE] == f'{k}\n'.encode() and shown(m) == titles(SORT_ORDERS[k]), f'row {k}: another order starts in its default direction')
        m.calls = []; m.click('btn_more'); m.click(f'vs_item{k}')
        expect(m.fs[SORT_FILE] == rev_file(k) and SORT_TMP not in m.fs and ('rename', SORT_TMP, SORT_FILE) in m.calls and shown(m) == titles(REV_ORDERS[k])
               and scroll_of(m) == 0 and vis(m, 'vs_card') == (0, 0), f'row {k}: a tap on the ticked row reverses it ({shown(m)}), saved as "{chr(ord("a") + k)}", the card closed, the list at the top')
        m.calls = []; m.click('btn_more')
        expect(subs(m) == [SUB_DOWN[k] if i == k else None for i in range(4)], f'row {k}: the second line reads "{SUB_DOWN[k]}"')
        m.click(f'vs_item{k}')
        expect(m.fs[SORT_FILE] == f'{k}\n'.encode() and shown(m) == titles(SORT_ORDERS[k]), f'row {k}: a second tap flips back to the default direction')
    # from a reversed order, another row starts in its own default direction
    m = sort_machine(**{SORT_FILE: rev_file(3)}); open_grid(m); m.click('btn_more'); m.click('vs_item0')
    expect(m.fs[SORT_FILE] == b'0\n' and shown(m) == titles(SORT_ORDERS[0]), 'Title chosen from reversed Year: Title, A\u2013Z')
    # a failed save leaves the order and the second line as they were
    m = sort_machine(**{SORT_FILE: b'2\n'}); open_grid(m); m.fail.add(('write', SORT_TMP)); m.click('btn_more'); m.click('vs_item2')
    expect(m.fs.get(SORT_FILE) == b'2\n' and shown(m) == titles(SORT_ORDERS[2]), 'a failed save changes nothing')
    # the special rows stay last: the Unknown Album row (id -1) is last in every order and direction
    lib = SORT_LIB + [('Unknown Album', '')]
    for k in range(4):
        for data in (f'{k}\n'.encode(), rev_file(k)):
            m = sort_machine(specs=lib, **{SORT_FILE: data}); m.showlist[-1] and m.setword(m.showlist[-1] + O['REC_ID'], 0xffffffff); open_grid(m)
            expect(shown(m)[-1] == 'Unknown Album' and len(shown(m)) == 6, f'albums-sort {data!r}: Unknown Album stays last')


def nextalbum_tests(ctx):
    """Continue with Next Album, phase 1 (patch/nextalbum.c): a tap on an album notes the albums in the order the page shows them (sort and direction, the Unknown Album row left out)
    just before cc_open_album; the note is dropped when the opener returns, and a page with the setting off notes nothing."""
    expect = ctx.expect
    NA = sibling('nextalbum')
    keyof = lambda i: album_key(SORT_LIB[i][1], SORT_LIB[i][0])
    row_xy = lambda a: (200, TOP + a * ROW + 20)
    stock_rows = lambda calls: [c[3] for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']
    for k in range(4):
        for data, orders in ((f'{k}\n'.encode(), SORT_ORDERS), (rev_file(k), REV_ORDERS)):
            m = NA.snap(sort_machine(**{SORT_FILE: data, NA.FILE: b'1\n'})); open_grid(m); settle(m)
            calls = tap_at(m, *row_xy(1))
            got = m.noted and m.noted['keys']
            expect(got == [keyof(i) for i in orders[k]] and m.noted['scope'] == 0 and m.noted['artist'] == 0,
                   f'albums-sort {data!r}: the note holds the keys in the order shown ({orders[k]}), no scope')
            expect(stock_rows(calls) == [orders[k][1]] and NA.state(m)['pending'] is None, f'albums-sort {data!r}: the tapped row is the stock row of the album; the note is gone once the opener returns')
    # the Unknown Album row stays out, wherever the order puts it
    lib = SORT_LIB + [('Unknown Album', '')]
    for k in (0, 1):
        m = NA.snap(sort_machine(specs=lib, **{SORT_FILE: f'{k}\n'.encode(), NA.FILE: b'1\n'})); m.setword(m.showlist[-1] + O['REC_ID'], 0xffffffff); open_grid(m); settle(m)
        tap_at(m, *row_xy(0))
        expect(m.noted and m.noted['keys'] == [keyof(i) for i in SORT_ORDERS[k]], f'order {k}: Unknown Album is not in the note')
    # a grid page notes the same way
    m = NA.snap(sort_machine(list_mode=False, **{SORT_FILE: b'0\n', NA.FILE: b'1\n'})); open_grid(m); settle(m)
    tap_at(m, 30, TOP + RGAP + 20)
    expect(m.noted and m.noted['keys'] == [keyof(i) for i in SORT_ORDERS[0]], 'the grid page: the same note')
    # the setting off (the default): nothing is noted or allocated
    m = NA.snap(sort_machine(**{SORT_FILE: b'0\n'})); open_grid(m); settle(m)
    calls = tap_at(m, *row_xy(1))
    expect(m.noted is None and NA.state(m)['pending'] is None and stock_rows(calls) == [1], 'setting off: the album opens as before, nothing is noted')


def title_tests(ctx):
    """The large title (the Songs / Artists pattern, the shared collapse rule): the first thing in the content, the navbar's small title hidden until
    the offset reaches SG_COLLAPSE, the nav fade while scrolled; the content moves down by the title block; the artist-scoped page's title is the name."""
    expect = ctx.expect
    TOP, COLLAPSE = O['SG_TITLE_H'], O['SG_COLLAPSE']
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin'), 'rb').read())
    big, grid = tree.find('al_title'), tree.find('view_grid')
    expect(big is not None and big in grid.children and (big.x, big.y, big.w, big.h) == (O['SG_TITLE_X'], 0, O['SG_TITLE_W'], TOP) and big.get('sensitive') == 'false'
           and big.get('style:normal:font_size') == '32' and big.get('style:normal:text_color') == '#FFFFFF',
           'the asset has the large title in the content view: 32 px white at x 12, insensitive, SG_TITLE_H high')
    expect(tree.find('label_title').get('visible') == 'false', 'the navbar\'s small title starts hidden')
    for mode, f in (('grid', b'1\n'), ('list', b'0\n')):
        m = albums_machine(30); m.fs[ALBUMS_FILE] = f; open_grid(m)
        t, small, fade = m.widgets['al_title'], m.widgets['label_title'], m.widgets['img_nb_fade']
        expect(('widget_set_text_utf8', t, 'Albums') in m.calls and ('widget_set_text_utf8', small, 'Albums') in m.calls, f'{mode}: both titles read Albums')
        expect(content_h(m) == TOP + (RGAP + 15 * PITCH if mode == 'grid' else 30 * ROW), f'{mode}: the content is the title block and the albums ({content_h(m)})')
        blits, _ = settle(m)
        want = TOP + (RGAP if mode == 'grid' else LAY)
        expect(min(b[2][1] for b in blits) == want, f'{mode}: the first cover is {want} px down, under the title block ({min(b[2][1] for b in blits)})')
        expect(m.props.get((small, 'visible'), 0) == 0 and ('widget_set_visible', small, 1) not in m.calls and m.props.get((fade, 'visible'), 0) == 0,
               f'{mode}: at rest the small title and the fade are hidden')
        scroll_to(m, COLLAPSE - 1)
        expect(m.props.get((small, 'visible'), 0) == 0 and m.props.get((fade, 'visible')) == 1, f'{mode}: one px short of SG_COLLAPSE the title is still hidden, the fade shows')
        scroll_to(m, COLLAPSE)
        expect(m.props.get((small, 'visible')) == 1 and m.props.get((fade, 'sensitive')) == 0, f'{mode}: at SG_COLLAPSE the small title shows')
        scroll_to(m, 0)
        expect(m.props.get((small, 'visible')) == 0 and m.props.get((fade, 'visible')) == 0, f'{mode}: back at the top they go')
        opened = lambda calls: [c for c in calls if c[0] == 'navigator_to_with_context']
        expect(not opened(tap_at(m, 100, TOP - 5)), f'{mode}: a tap on the title block opens nothing')
        expect(opened(tap_at(m, 30, TOP + (RGAP if mode == 'grid' else 0) + 10)), f'{mode}: a tap on the first row opens it')
        m2 = albums_machine(30); m2.fs[ALBUMS_FILE] = f; m2.widget_on_fail = frozenset({O['EVT_SCROLL']}); open_grid(m2)
        expect(('widget_set_visible', m2.widgets['label_title'], 1) in m2.calls, f'{mode}: without the scroll events the navbar keeps its title')
    # the artist-scoped page: the title is the artist's name (both labels)
    for mode, f in (('grid', b'1\n'), ('list', b'0\n')):
        m = artists_machine(albums_page=True); m.fs[ALBUMS_FILE] = f
        m.call(PSYMS['artists_open'], a0=0, count=20000000); m.calls = []
        m.call(PSYMS['ar_open'], a0=0, count=40000000)
        expect(('widget_set_text_utf8', m.widgets['al_title'], 'Miles Davis') in m.calls and ('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.calls,
               f'{mode}: the scoped page\'s large and small titles are the artist')
        end = O['AL_HEAD_END'] - O['PH_SHIFT']   # no photo in this card: the header without the circle and the pills end the block (PH_SHIFT higher: test/pod/artists.py scoped_plain_tests); the list's first row is RGAP under it, the grid's gap is its own
        expect(content_h(m) == end + (RGAP + 2 * PITCH if mode == 'grid' else RGAP + 4 * ROW), f'{mode}: the scoped content starts under the title and the pills ({content_h(m)})')



FAKE_PIC = '/mnt/mmc/.m1plus/subsonic/covers/fa000001-168.jpg'   # (the fake source's picture file of its artist)


class FakeAlbumsMachine(Machine):
    """A machine with a fake non-stock lib_src_t (patch/libsrc.h) in memory: its list, cover and gen are Python (the functions' addresses are trapped, named fake_albums_*).
    fake_rows: the records list() returns (a new deque each call); fake_have: the keys whose cover file is ready (cover() 1), fake_gone: keys with no cover (-1), any other key 0 (asked);
    fake_gen: what gen() returns; fake_log: ('list', which, scope) / ('cover', key) / ('gen',)."""
    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name == 'album_open_src':   # (src, cls, row): the source's album page, recorded and not run
            a0, a1, a2 = (u.reg_read(r) for r in (mips_const.UC_MIPS_REG_A0, mips_const.UC_MIPS_REG_A1, mips_const.UC_MIPS_REG_A2))
            self.calls.append(('album_open_src', a0 == self.fake_src, a1, self.read_cstr(self.word(a2 + O['REC_ALBUM']))))
            u.reg_write(mips_const.UC_MIPS_REG_V0, 0); u.reg_write(mips_const.UC_MIPS_REG_PC, u.reg_read(mips_const.UC_MIPS_REG_RA))
            return
        if name == 'search_open_src_in':   # (src, scope): the source's search page, recorded and not run
            self.calls.append(('search_open_src_in', u.reg_read(mips_const.UC_MIPS_REG_A0) == self.fake_src, u.reg_read(mips_const.UC_MIPS_REG_A1)))
            u.reg_write(mips_const.UC_MIPS_REG_V0, 0); u.reg_write(mips_const.UC_MIPS_REG_PC, u.reg_read(mips_const.UC_MIPS_REG_RA))
            return
        if not name or not name.startswith('fake_albums_'): return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (mips_const.UC_MIPS_REG_A0, mips_const.UC_MIPS_REG_A1, mips_const.UC_MIPS_REG_A2, mips_const.UC_MIPS_REG_A3))
        ret = 0
        if name == 'fake_albums_list':
            self.fake_log.append(('list', a1, a2)); ret = 0 if a1 == 2 and getattr(self, 'fake_no_songs', 0) else self.new_deque(self.fake_scoped.get(a2, self.fake_rows) if a2 else self.fake_rows)
        elif name == 'fake_albums_cover' and a2 == 0:   # key 0: an artist's picture (the page's header): fake_pic 1 the file is there (FAKE_PIC), 0 asked, -1 none
            self.fake_log.append(('pic',))
            if self.fake_pic == 1: self.u.mem_write(a3, FAKE_PIC.encode() + b'\0')
            ret = self.fake_pic
        elif name == 'fake_albums_cover':
            self.fake_log.append(('cover', a2))
            if a2 in self.fake_have: self.u.mem_write(a3, art_file(a2).encode() + b'\0'); ret = 1
            else: ret = 0xffffffff if a2 in self.fake_gone else 0
        elif name == 'fake_albums_play':   # (s, list, at, how, open, cls): how is SO_IN_ORDER (1) / SO_SHUFFLE (2)
            self.fake_log.append(('play', a2 if a2 < 0x80000000 else a2 - 0x100000000, a3)); ret = 0
        elif name == 'fake_albums_gen':
            self.fake_log.append(('gen',)); ret = self.fake_gen
        elif name == 'fake_albums_state':   # (s, which, scope): LS_ST_*
            self.fake_log.append(('state', a1, a2)); ret = self.fake_state
        u.reg_write(mips_const.UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(mips_const.UC_MIPS_REG_PC, u.reg_read(mips_const.UC_MIPS_REG_RA))


def fake_albums_machine(n=6, grid=True, cached=False, caps=7):
    """The albums page's machine with a fake source of n albums ('Fake Album i' by 'Fake Artist i') at m.fake_src; the stock library has the usual 30 'Album i'.
    caps: lib_src_t.caps (the stock-only controls the page may show: 7 is all of them)."""
    m = albums_machine(30, cls=FakeAlbumsMachine, cached=cached)
    m.fs[ALBUMS_FILE] = b'1\n' if grid else b'0\n'
    m.fake_log, m.fake_have, m.fake_gone, m.fake_gen, m.fake_scoped = [], set(), set(), 7, {}
    m.fake_rows = [m.record(album=f'Fake Album {i}', artist=f'Fake Artist {i}', path=f'nd://al{i}', rid=-3 - i) for i in range(n)]
    m.fake_state = 0   # what src->state answers (LS_ST_*)
    m.fake_pic = -1   # what src->cover answers for an artist's picture (key 0): 1 there, 0 asked, -1 none
    m.top_main = m.window   # pod_is_top: the page is in front (the shared cover poll only runs then)
    Machine.widget(m, 'al_spin')
    st = m.alloc(60)
    m.u.mem_write(st, bytes(60)); m.setword(st, m.cstr('fake')); m.setword(st + 48, caps)
    for off, nm in ((4, 'list'), (16, 'cover'), (32, 'gen'), (56, 'state')):
        addr = m.alloc(16); m.handlers[addr] = 'fake_albums_' + nm; m.setword(st + off, addr)
    m.fake_src = st
    for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)   # (the Wi-Fi page's frames as cc_decode flattens them over black)
    return m


def fkey(i): return album_key(f'Fake Artist {i}', f'Fake Album {i}')


def make_ready(m, i):
    """The fake source's cover file of fake album i exists (as a fetch finishing leaves it) and the source says so."""
    p = art_file(fkey(i))
    m.present.add(p); m.files[p] = 4096; m.cache_index[p] = i; m.fake_have.add(fkey(i))


def settle_calls(m, limit=60):
    """settle(), and every call the loader ticks made (m.calls is reset by each call)."""
    seen = []
    for _ in range(limit):
        seen += tick(m)
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in m.calls): break
    return seen, paint(m)


def src_tests(ctx):
    """albums_open_src: the same page fed by a library source. Stock (NULL, &lib_stock) is the stock page; a fake source's albums are listed, their covers come from src->cover (no cache worker), and a gen change re-reads the list."""
    expect = ctx.expect
    LS_ALBUMS = 0
    # 1. NULL and &lib_stock open the stock page: the stock albums, no source call, the cache build armed as today
    for which in (0, PSYMS['lib_stock']):
        m = albums_machine(30, cls=FakeAlbumsMachine, missing={2}); m.fake_log = []
        m.fs[ALBUMS_FILE] = b'1\n'
        m.call(PSYMS['albums_open_src'], a0=which, a1=0, count=20000000)
        blits, texts = settle(m)
        titles, _ = grid_texts(m, texts)
        expect(content_h(m) == TOP + RGAP + 15 * PITCH and 'Album 0' in titles and not m.fake_log, f'src {which:#x}: the stock page, 30 albums, no source called')
        m.calls = []; fired(m, 'al_on_build_start')
        expect(count_of(m, 'pthread_create') == 1, f'src {which:#x}: stock still builds missing covers with the cache worker')
        expect(not any(v[1:] == (14, 14) for v in m.bitmaps.values()) and not any(c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick'] for c in m.calls), f'src {which:#x}: no cover spinner on the stock page')
    # 2. a fake source: its albums, listed with LS_ALBUMS and no scope; the cache worker is never armed
    for grid in (True, False):
        m = fake_albums_machine(6, grid=grid)
        m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
        expect(('list', LS_ALBUMS, 0) in m.fake_log, f'{"grid" if grid else "list"}: the albums are src->list(LS_ALBUMS, NULL)')
        expect(content_h(m) == (TOP + RGAP + 3 * PITCH if grid else TOP + 6 * ROW), f'{"grid" if grid else "list"}: the content holds the source\'s 6 albums ({content_h(m)})')
        expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['al_on_build_start']] and 'pthread_create' not in [c[0] for c in m.calls], f'{"grid" if grid else "list"}: no cache build is armed')
        blits, texts = settle(m)
        shown = [t[0] for t, sty in zip(texts, m.text_styles) if sty in ('label_grid_title', 'label_row_title')]
        expect(len(shown) >= 4 and all(x.startswith('Fake Album ') for x in shown), f'{"grid" if grid else "list"}: the fake albums\' names are drawn ({shown})')
        expect(not any('Album 1' == x for x in shown), 'none of the stock albums')
        expect(not [c for c in m.calls if c[0] in ('cc_build_open', 'cc_build_add')], 'the cover worker is not used')
    # 3. covers come from src->cover: not ready (0) = the placeholder, asked again by the page's timer; ready = the file is decoded
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    make_ready(m, 1)
    m.fake_log.clear()
    seen, (blits, _) = settle_calls(m)
    asked = [e[1] for e in m.fake_log if e[0] == 'cover']
    expect(sorted(asked) == sorted(fkey(i) for i in range(6)), f'every album asked the source for its cover (by its key) ({len(asked)})')
    expect(f'file://{art_file(fkey(1))}' in m.loads and len([u for u in m.loads if u.startswith('file://')]) == 1, f'only the ready cover is decoded ({[u for u in m.loads if u.startswith("file://")]})')
    expect(('timer_add', PSYMS['ls_cover_tick'], 250) in seen, 'a cover that was asked for (0) arms the shared cover poll (250 ms)')
    # 3b. the cover spinner: a tile whose cover was asked for (0) shows the 14 px wf_spin frame centred on its disc, turned by a 250 ms timer; it goes with the cover (arrived or none)
    def spinners(bl): return [b for b in bl if m.bitmaps[b[0]][1:] == (14, 14)]
    sp = spinners(blits)
    expect(len(sp) == 3 and all(b[2][2:] == (14, 14) and (b[2][0] + 7 - O['GRID_MARGIN']) % (O['GRID_COVER'] + O['GRID_GAP']) == O['GRID_COVER'] // 2 for b in sp),
           f'a spinner on each of the 3 tiles in view being fetched (0, 2, 3), centred on the disc, none on the ready one (1): {[b[2] for b in sp]}')
    expect(sum(1 for c in seen if c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick']) == 1, 'the spinners turn on the same one timer')
    f0 = {b[0] for b in sp}
    expect(m.call(PSYMS['ls_cover_tick'], a0=0x5a5a5a50, count=20000000) == 8, 'a tick with tiles still loading repeats (its argument is stock\'s timer_info_t: not read)')
    expect(len(f0) == 1 and {b[0] for b in spinners(paint(m)[0])} not in (f0, set()), 'the tick moved every spinner to the next frame')
    make_ready(m, 4); m.fake_gone.add(fkey(5))
    m.fake_log.clear()
    m.call(PSYMS['ls_cover_tick'], count=20000000)
    seen, (blits, _) = settle_calls(m)
    expect(f'file://{art_file(fkey(4))}' in m.loads, 'the retry picks the cover that is ready now up')
    expect(len(spinners(blits)) == 3, 'the tiles still being fetched keep theirs')
    expect(m.fake_log.count(('cover', fkey(5))) == 1, 'a source with no cover (-1) is asked once per retry')
    expect(m.call(PSYMS['ls_cover_tick'], count=20000000) == 8, 'the rest still being fetched keep the poll')
    m.fake_gone |= {fkey(0), fkey(2), fkey(3)}; m.fake_log.clear()
    m.call(PSYMS['ls_cover_tick'], count=20000000)
    seen, _ = settle_calls(m)
    expect(len(spinners(paint(m)[0])) == 0, 'nothing left being fetched: no spinner')
    rets = [m.call(PSYMS['ls_cover_tick'], count=20000000) for _ in range(4)]
    expect(rets[-1] != 8 and not any(c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick'] for c in seen), f'nothing on its way: the shared poll ends after two quiet ticks ({rets})')
    # 3c. the poll gives up (the one rule, patch/libsrc.c): LS_COVER_POLLS asks without the cover, then the spinners go and nothing asks again; the tile asked for later starts afresh
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    settle_calls(m)
    for _ in range(1210):
        m.call(PSYMS['ls_cover_tick'], count=20000000)
        settle_calls(m)
    asks = sum(1 for e in m.fake_log if e == ('cover', fkey(0)))
    expect(1190 <= asks <= 1203 and len(spinners(paint(m)[0])) == 0 and m.call(PSYMS['ls_cover_tick'], count=20000000) != 8, f'after 1200 asks it gives up: no spinner, the poll has ended ({asks})')
    # 3d. a page that is not on top (another window over it) asks nothing and turns nothing
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000); settle_calls(m)
    m.top_main = 0; m.fake_log.clear()
    expect(m.call(PSYMS['ls_cover_tick'], count=20000000) == 8 and not m.fake_log, 'not the top window: the poll stays armed but asks nothing')
    # 4. a gen change re-reads the list; the same gen does not
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000); settle(m)
    n0 = sum(1 for e in m.fake_log if e[0] == 'list')
    m.call(PSYMS['al_on_gen'], count=20000000)
    expect(sum(1 for e in m.fake_log if e[0] == 'list') == n0 and any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_gen'] for c in m.calls), 'the same gen: no re-read, the timer re-arms')
    m.fake_rows = m.fake_rows + [m.record(album=f'Fake Album {i}', artist=f'Fake Artist {i}', path=f'nd://al{i}', rid=-3 - i) for i in range(6, 12)]
    m.fake_gen += 1
    m.call(PSYMS['al_on_gen'], count=20000000)
    expect(sum(1 for e in m.fake_log if e[0] == 'list') == n0 + 1 and content_h(m) == TOP + RGAP + 6 * PITCH, f'a new gen: the list is read again, 12 albums ({content_h(m)})')
    blits, texts = settle(m)
    scroll_to(m, 10000); blits, texts = settle(m)
    shown = [t[0] for t, sty in zip(texts, m.text_styles) if sty == 'label_grid_title']
    expect('Fake Album 11' in shown or 'Fake Album 10' in shown, f'the new albums are drawn ({shown})')
    m.fake_rows = []; m.fake_gen += 1
    m.call(PSYMS['al_on_gen'], count=20000000)
    expect(m.props.get((m.widgets['view_grid'], 'visible')) == 1 and m.props.get((m.widgets['label_status'], 'visible')) == 1 and ('widget_set_tr_text', m.widgets['label_status'], 'No albums') in m.calls,
           'an empty list shows the status line (and keeps the large title)')
    m.fake_rows = [m.record(album='Back', artist='Again', path='nd://x', rid=-2)]; m.fake_gen += 1
    m.call(PSYMS['al_on_gen'], count=20000000)
    blits, texts = settle(m)
    expect(content_h(m) == TOP + RGAP + PITCH and m.props.get((m.widgets['view_grid'], 'visible')) == 1 and 'Back' in [t[0] for t in texts], 'the list is back: the grid is shown again')
    # 4a. a moved gen with the same albums (a cover or a sync that changed nothing): the tiles stay, nothing is decoded again, a fling goes on
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    make_ready(m, 1); settle(m)
    decoded = lambda: len([u for u in m.loads if u.startswith('file://')])
    n_dec, n0 = decoded(), sum(1 for e in m.fake_log if e[0] == 'list')
    expect(n_dec == 1, f'the ready cover was decoded once ({n_dec})')
    m.fake_rows = [m.record(album=f'Fake Album {i}', artist=f'Fake Artist {i}', path=f'nd://al{i}', rid=-3 - i) for i in range(6)]
    m.fake_gen += 1
    m.calls = []
    m.call(PSYMS['al_on_gen'], count=20000000)
    names_ = [c[0] for c in m.calls]
    settle(m)
    expect(sum(1 for e in m.fake_log if e[0] == 'list') == n0 + 1 and decoded() == n_dec and 'bitmap_destroy' not in names_ and not any(c[0] == 'widget_load_image' for c in m.calls),
           f'the list is read again and found the same: no tile is dropped, no cover decoded again ({decoded()}, {sorted(set(names_))})')
    # 5. a source page that opens empty gets its handlers when the first album arrives
    m = fake_albums_machine(0)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    expect(m.props.get((m.widgets['label_status'], 'visible')) == 1 and (m.widgets['view_grid'], O['EVT_POINTER_UP']) not in m.bound, 'opened empty: the status line, no handlers')
    expect(('state', 0, 0) in m.fake_log, 'it asked src->state(LS_ALBUMS, NULL)')
    m.fake_rows = [m.record(album='First', artist='One', path='nd://f', rid=-2)]; m.fake_gen += 1
    m.call(PSYMS['al_on_gen'], count=20000000)
    blits, texts = settle(m)
    expect((m.widgets['view_grid'], O['EVT_POINTER_UP']) in m.bound and 'First' in [t[0] for t in texts], 'the first album: the grid and its handlers')
    # 5a. an artist's page on a source: list(LS_ALBUMS, the artist's record), the header of a library artist without a photo (a source has none: no circle, no placeholder;
    #     the name and the pills PH_SHIFT higher, docs/modules/albums.md), no stock query; Play and Shuffle play the source's songs of the artist
    END, CD, SH = O['AL_HEAD_END'], O['AL_PHOTO_D'], O['PH_SHIFT']
    m = fake_albums_machine(3)
    for r, y in zip(m.fake_rows, (1999, 0, 2005)): m.setword(r + O['REC_YEAR'], y)   # (a source's records carry their year)
    for w in ('btn_play', 'btn_shuffle', 'al_name'): Machine.widget(m, w)
    m.images['pod_ic_ar_art'] = (24, 24, bytes((0x8c, 0x8c, 0x8c, 255)) * (24 * 24))
    m.fake_rows.append(m.record(album='', artist='Fake Artist', path='nd://ar1', rid=-2))   # the stock All songs row, last: the artist's songs
    addr = m.alloc(16); m.handlers[addr] = 'fake_albums_play'; m.setword(m.fake_src + 12, addr)
    artist = m.record(album='', artist='Fake Artist', path='nd://ar1', title='Fake Artist', rid=-9)
    m.calls = []
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=artist, count=20000000)
    lists = [e for e in m.fake_log if e[0] == 'list']
    expect(lists and lists[0][:2] == ('list', LS_ALBUMS) and lists[0][2] and ('pic',) in m.fake_log, 'the artist page asks the source for that artist\'s albums (a record) and for the artist\'s picture')
    expect('loadAlbumList' not in m.names(), 'the artist page of a source makes no stock query')
    w = lambda n: (m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1))
    expect(('widget_set_text_utf8', m.widgets['al_name'], 'Fake Artist') in m.calls and w('al_name') == (1, 1) and w('al_title') == (0, 0)
           and ('widget_set_text_utf8', m.widgets['label_title'], 'Fake Artist') in m.calls, 'the artist\'s name is the header\'s (al_name), the large title is hidden, the navbar\'s small title is the name')
    expect(('widget_move', m.widgets['btn_play'], O['AL_PLAY_X'], O['AL_HEAD_PILL_Y'] - SH) in m.calls and ('widget_move', m.widgets['btn_shuffle'], O['AL_SHUFFLE_X'], O['AL_HEAD_PILL_Y'] - SH) in m.calls
           and w('btn_play') == (1, 1) and w('btn_shuffle') == (1, 1), 'Play and Shuffle sit under the name, shown, PH_SHIFT higher (no circle)')
    expect(content_h(m) == END - SH + RGAP + 2 * PITCH, f'3 albums and the All Songs tile under the header block ({content_h(m)})')
    blits, texts = settle(m)
    _, subs_ = grid_texts(m, texts)
    expect('1999' in subs_ and '2005' in subs_ and 'Fake Artist 0' not in subs_ and '' not in subs_, f'a source artist\'s albums show the year line like the local artist page, none for an album without one ({sorted(subs_)})')
    expect(not [b for b in blits if tuple(b[2])[2:] == (CD, CD)], 'no 88 px circle is drawn: a source\'s artist has no photo and the page shows no placeholder')
    expect(not [c for c in m.calls if c[0] == 'widget_load_image' and 'artists/' in str(c[1])] and not [c for c in m.calls if c[0] == 'pthread_create'], 'no photo file is looked for and no cover worker starts')
    for what, btn, want in (('Play', 'btn_play', (0, 1)), ('Shuffle', 'btn_shuffle', (-1, 2))):
        m.fake_log.clear(); m.calls = []
        m.click(btn, count=40000000)
        lists = [e for e in m.fake_log if e[0] == 'list' and e[1] == 2]
        expect(lists and lists[0][2] == m.fake_rows[-1], f'{what}: the source\'s songs of the artist are listed through the All Songs record')
        plays = [e for e in m.fake_log if e[0] == 'play']
        expect(len(plays) == 1 and plays[0][1:] == want, f'{what}: src->play(at {want[0]}, how {want[1]}) ({plays})')
    m.fake_no_songs = 1   # the artist's songs are not derived yet: Play says why instead of doing nothing
    for st, want in ((1, 'Loading\u2026'.encode().decode('latin-1')), (0, "Can't play")):   # (the mocked translation reads UTF-8 as latin-1)
        m.fake_state = st; m.calls = []
        m.click('btn_play', count=40000000)
        expect([c[1] for c in m.calls if c[0] == 'toast'] == [want] and not [e for e in m.fake_log if e[0] == 'play' and False], f'no songs list and the source is {"loading" if st else "not loading"}: the toast "{want}" ({[c[1] for c in m.calls if c[0] == "toast"]})')
    m.fake_no_songs = 0
    m.calls = []
    m.call(PSYMS['al_on_destroy'], count=4000000)
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_destroy') >= 1, 'closing the page frees the circle')
    # 5a2. a source artist's picture (src->cover with key 0 on the artist's record): cached = the 88 px circle exactly as a library artist with a photo; on its way = the plain header, then the circle appears in place
    #      when the shared cover poll finds the file; none = the plain header, asked once. A portrait file is cut from its top third, as the artist cache cuts it. Never a placeholder circle.
    port = b''.join(bytes((250, 250, 30, 255)) * 84 if 18 <= y < 28 else bytes((30, 30, 220, 255)) * 84 for y in range(140))   # 84 x 140; rows 18..27 yellow (the top third's first rows; a centred cut starts at 28)

    def artist_page(pic):
        mm = fake_albums_machine(3)
        for w_ in ('btn_play', 'btn_shuffle', 'al_name'): Machine.widget(mm, w_)
        mm.images['pod_ic_ar_art'] = (24, 24, bytes((0x8c, 0x8c, 0x8c, 255)) * (24 * 24))
        mm.images['file://' + FAKE_PIC] = (84, 140, port)
        mm.fake_pic = pic
        mm.fake_rows.append(mm.record(album='', artist='Fake Artist', path='nd://ar1', rid=-2))
        mm.calls = []
        mm.call(PSYMS['albums_open_src'], a0=mm.fake_src, a1=mm.record(album='', artist='Fake Artist', path='nd://ar1', title='Fake Artist', rid=-9), count=20000000)
        return mm
    circle = lambda mm_, bl: [b for b in bl if tuple(b[2])[2:] == (CD, CD)]
    pix = lambda mm_, b, x, y: struct.unpack('<I', mm_.u.mem_read(mm_.bitmaps[b[0]][0] + (y * CD + x) * 4, 4))[0]
    moved = lambda mm_, n, y: ('widget_move', mm_.widgets[n], O['PH_NAME_X'] if n == 'al_name' else (O['AL_PLAY_X'] if n == 'btn_play' else O['AL_SHUFFLE_X']), y) in mm_.calls
    m = artist_page(1)
    expect(content_h(m) == END + RGAP + 2 * PITCH and not moved(m, 'al_name', O['AL_NAME_Y'] - SH) and not moved(m, 'btn_play', O['AL_HEAD_PILL_Y'] - SH),
           f'a cached picture: the header with the circle (name and pills where a library artist with a photo has them, the rows END down) ({content_h(m)})')
    expect(not circle(m, paint(m)[0]), 'no circle before the loader has made it')
    blits, _ = settle(m)
    c = circle(m, blits)
    expect(len(c) == 1 and tuple(c[0][2][:2]) == (O['AL_PHOTO_X'], O['AL_PHOTO_Y']), f'the circle is drawn at ({O["AL_PHOTO_X"]}, {O["AL_PHOTO_Y"]}) ({[b[2] for b in c]})')
    top_, mid_ = pix(m, c[0], CD // 2, 4), pix(m, c[0], CD // 2, CD // 2)
    expect(top_ >> 24 == 255 and (top_ & 255) > 220 and (top_ >> 16 & 255) < 60 and (mid_ >> 16 & 255) > 200 and (mid_ & 255) < 60 and pix(m, c[0], 0, 0) >> 24 == 0,
           f'the portrait file is cut from its top third (yellow at the top, blue under it), as a circle with clear corners ({top_:#x}, {mid_:#x})')
    m = artist_page(0)
    expect(content_h(m) == END - SH + RGAP + 2 * PITCH and moved(m, 'al_name', O['AL_NAME_Y'] - SH) and ('timer_add', PSYMS['ls_cover_tick'], 250) in m.calls,
           'a picture on its way: the plain header (PH_SHIFT higher), the shared cover poll armed')
    blits, _ = settle(m)
    expect(not circle(m, blits) and not [b for b in blits if m.bitmaps[b[0]][1:] == (88, 88)], 'and no circle, no placeholder disc')
    m.fake_pic = 1
    m.calls = []
    m.call(PSYMS['ls_cover_tick'], a0=0x5a5a5a50, count=40000000)
    expect(moved(m, 'al_name', O['AL_NAME_Y']) and moved(m, 'btn_play', O['AL_HEAD_PILL_Y']) and moved(m, 'btn_shuffle', O['AL_HEAD_PILL_Y']) and content_h(m) == END + RGAP + 2 * PITCH,
           f'the picture arrived while the page was up: the header switches in place (name and pills PH_SHIFT lower, the content taller) ({content_h(m)})')
    blits, _ = settle(m)
    c = circle(m, blits)
    top_ = pix(m, c[0], CD // 2, 4) if c else 0
    expect(len(c) == 1 and (top_ & 255) > 220 and (top_ >> 16 & 255) < 60, 'and the circle is drawn, decoded from the arrived file')
    m.fake_log.clear()
    for _ in range(4): m.call(PSYMS['ls_cover_tick'], count=40000000)
    expect(('pic',) not in m.fake_log, 'with the circle up the poll does not ask for the picture again')
    m = artist_page(-1)
    n0 = m.fake_log.count(('pic',))
    for _ in range(6): m.call(PSYMS['ls_cover_tick'], count=40000000)
    blits, _ = settle(m)
    expect(n0 == 1 and m.fake_log.count(('pic',)) == 1 and content_h(m) == END - SH + RGAP + 2 * PITCH and not circle(m, blits), 'no picture (-1): the plain header, asked once for it though the albums\' covers are polled')
    m = artist_page(0)
    for _ in range(1210): m.call(PSYMS['ls_cover_tick'], count=40000000)
    blits, _ = settle(m)
    expect(not circle(m, blits) and content_h(m) == END - SH + RGAP + 2 * PITCH, 'a picture that never comes: the poll gives up, the plain header stays')
    m = artist_page(1)
    m.images['file://' + FAKE_PIC] = (84, 140, b'')
    m.load_image = 1
    blits, _ = settle(m)
    expect(not circle(m, blits) and content_h(m) == END - SH + RGAP + 2 * PITCH, 'a picture file that does not decode: the plain header')
    # 5b. a source without Cover Flow or Search (lib_nd's caps 0): no Cover Flow button, the "..." is the capsule's left cap and the title runs to 214;
    #     the card holds the sorts and the views, no Search row
    m = fake_albums_machine(6, caps=0)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    expect(vis(m, 'btn_coverflow') == (0, 0) and m.props.get((m.widgets['btn_more'], 'style:normal:icon')) == 'pod_nav_more'
           and m.props.get((m.widgets['btn_more'], 'style:pressed:icon')) == 'pod_nav_more_down'
           and m.word(m.widgets['label_title'] + 8) == O['NAV_VIEW_X'] - O['NAV_TITLE_X'],
           'caps 0: Cover Flow hidden, the "..." a left cap (pod_nav_more), the title to 214')
    m.click('btn_more')
    expect(vis(m, 'vs_item6') == (0, 0) and vis(m, 'vs_item4')[0] == 1 and vis(m, 'vs_item0')[0] == 1, 'its card: four sorts and Grid / List, no Search row')
    # 5c. lib_nd's caps (Search only): the card's Search row is there and opens the source's search scoped to albums
    m = fake_albums_machine(6, caps=2)
    m.handlers[PSYMS['search_open_src_in']] = 'search_open_src_in'
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    expect(vis(m, 'btn_coverflow') == (0, 0), 'caps Search only: no Cover Flow button')
    m.click('btn_more')
    expect(vis(m, 'vs_item6') == (1, 1), 'caps Search only: the card has the Search row')
    m.calls = []
    m.click('vs_item6', count=40000000)
    expect(('search_open_src_in', True, 2) in m.calls, f'the Search row opens search_open_src_in(source, SEARCH_ALBUMS) ({[c for c in m.calls if c[0] == "search_open_src_in"]})')
    m = fake_albums_machine(6)
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    expect(vis(m, 'btn_coverflow') == (1, 1) and m.props.get((m.widgets['btn_more'], 'style:normal:icon')) is None
           and m.word(m.widgets['label_title'] + 8) == O['NAV_CF_X'] - O['NAV_TITLE_X'],
           'caps all: Cover Flow shows, the "..." keeps its middle piece and the title ends at 168 (the stock page\'s bar)')
    # 6. a tap on a source's album opens the album page on the source (album_open_src, the tapped row), no stock album page
    m = fake_albums_machine(6)
    m.handlers[PSYMS['album_open_src']] = 'album_open_src'
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000); settle(m)
    calls = tap_at(m, 30, TOP + RGAP + 10)
    expect(('album_open_src', True, 0, 'Fake Album 0') in calls, f'a tap on a source album calls album_open_src with the source and that album ({calls})')
    expect(not [c for c in calls if c[0] in ('cc_open_album', 'album_open', 'navigator_to_with_context')], 'a tap on a source album opens no stock album page')
    # 7. a source's Recently Added and Year orders follow its records' own creation time and year (no song query); an album without one stays last; the reverse flips the rest
    years, created = [2001, 1990, 0, 2010, 1985, 1999], [50, 10, 0, 90, 70, 30]
    for mode, rev, want in ((3, 0, [3, 0, 5, 1, 4, 2]), (3, 1, [4, 1, 5, 0, 3, 2]), (2, 0, [3, 4, 0, 5, 1, 2]), (2, 1, [1, 5, 0, 4, 3, 2])):
        m = fake_albums_machine(6, grid=False)
        for i, r in enumerate(m.fake_rows): m.setword(r + O['REC_YEAR'], years[i]); m.setword(r + O['REC_TIME_CREATE'], created[i])
        m.fs[SORT_FILE] = (chr(ord('a' if rev else '0') + mode) + '\n').encode()
        m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000); settle(m)
        got = globals()['shown'](m)   # (src_tests has a local named shown)
        expect(got[:6] == [f'Fake Album {i}' for i in want] and not any(c[0] == 'loadLocalClassList' for c in m.calls),
               f'a source in {"Year" if mode == 3 else "Recently Added"}{" (reversed)" if rev else ""}: its own records\' order, no song query ({got})')




AZ_RAIL, AZ_HEAD = '/mnt/data/m1plus/appearance-index-rail', '/mnt/data/m1plus/appearance-headers'   # the Index Rail and Section Headers switches (both on by default)
HDR = O['SG_HDR_H']
AZ_TITLES = ['1999', 'Abbey Road', 'Aja', 'Bitches Brew', 'Blue', 'Cheap Trick', 'Dookie', 'Dookie Two', 'Zeta']   # the Title order: the sections # A B C D Z
AZ_SECS = [(0, '#'), (1, 'A'), (3, 'B'), (5, 'C'), (6, 'D'), (8, 'Z')]


def az_model(hh, secs=AZ_SECS, n=len(AZ_TITLES)):
    """(header y, row y, content height) of the list with sections of header height hh (az_hdr_y, az_row_y, az_rows_end of patch/azlist.c, the list's top TOP: the large title's block)."""
    sec_of = lambda i: max(k for k, (s, _) in enumerate(secs) if s <= i)
    return (lambda s: TOP + s * hh + secs[s][0] * ROW), (lambda i: TOP + (sec_of(i) + 1) * hh + i * ROW), TOP + len(secs) * hh + n * ROW


def az_tests(ctx):
    """The Albums list mode's A-Z furniture (patch/azlist.c) in the Title order (A-Z and Z-A): sections of the album title's initial, the pinned header, the rail and its bubble; the grid and the other orders have none; Index Rail
    and Section Headers (both on by default) in the four combinations; the header height 0 closes the rows up and the rail still jumps to each section's first row."""
    expect = ctx.expect
    n = len(AZ_TITLES)

    def opened(rail=None, heads=None, mode=b'0\n', titles=AZ_TITLES, sort_file=None, **kw):
        m = albums_machine(len(titles), az=True, title=lambda i: titles[i], **kw)
        if sort_file is not None: m.fs[SORT_FILE] = sort_file   # (the world's default is Title, '0')
        if rail is not None: m.fs[AZ_RAIL] = rail
        if heads is not None: m.fs[AZ_HEAD] = heads
        m.fs[ALBUMS_FILE] = mode
        open_grid(m)
        return m

    def vis(m, name):
        w = m.widgets[name]
        return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)

    def frame(m, off):
        scroll_to(m, off); paint(m)
        return [(t, r) for (t, r), s in zip(m.texts, m.text_styles) if s == 'label_hdr']

    def heads_of(m):
        """{content y: letter} of the headers painted in the flow (y > 0 of the window: the pinned copy at the top is not one) over the whole content."""
        out = {}
        for off in range(0, max(content_h(m) - VIEW_H, 0) + 100, 100):
            for t, (x, y, w, h) in frame(m, off):
                if y > 0: out[y + scroll_of(m)] = t   # (the offset the scroll_view clamped it to)
        return out

    def rail_touch(m, kind, i, k, t=3000):
        geo = tuple(m.props.get((m.rail, c)) for c in 'xywh')
        span = geo[3] - 2 * O['SG_RAIL_PAD']
        m.touch(kind, 300, 30 + geo[1] + O['SG_RAIL_PAD'] + int((i + 0.5) * span / k), t, fn='al_on_rail', count=40000000)
        return geo

    # 1. Rail off, headers on: the sections and the pinned header, rows 64 px apart under 28 px headers, no rail or bubble; the rows keep their layout
    m = opened(rail=b'0\n')
    hdr_y, row_y, content = az_model(HDR)
    expect(content_h(m) == content and m.props.get((m.widgets['albums_scrollview'], 'virtual_h')) == content, f'the content holds a header per section and a row per album ({content_h(m)} == {content})')
    expect(vis(m, 'sg_rail') == (0, 0), 'Index Rail off: the rail is hidden and insensitive')
    expect(heads_of(m) == {hdr_y(s): l for s, (_, l) in enumerate(AZ_SECS)}, f'a header at every section: the letters {heads_of(m)}')
    expect(frame(m, 0)[0] == ('#', (O['SG_HDR_X'], TOP, 100, HDR - 1)), 'the first header is under the large title, the Songs page\'s letter box')
    blits, texts = paint(m)
    titles = [(t, r) for (t, r), s in zip(m.texts, m.text_styles) if s == 'label_row_title']
    expect([(t, r[1]) for t, r in titles] == [(AZ_TITLES[i], row_y(i) + TY) for i in range(n) if row_y(i) < VIEW_H] and all(r[0] == TX and r[2] == TW for _, r in titles),
           f'the rows lie under their headers, the texts from x {TX} to {TX + TW}: {[(t, r[1]) for t, r in titles]}')
    hair = [f for f in m.fills if f[0] == O['LIST_HAIR']]
    expect(hair and all(f[1] == HX and f[3] == HW for f in hair) and {f[2] for f in hair} == {row_y(i) + ROW - 1 for i in range(n) if row_y(i) + ROW <= VIEW_H}, 'the hairlines run from the text to x 310, one under each row')
    expect(m.chevs and {b[2][:2] for b in m.chevs} >= {(O['LIST_CHEV_X'], row_y(0) + (ROW - 1 - CHEV_PX[1]) // 2)}, 'the chevrons stay at x 288')
    # the pinned header: the section at the window's top, the next one pushing it up
    for off, letters, fill_h in ((hdr_y(0) + 5, ['#'], HDR), (hdr_y(1) + 20, ['A'], HDR), (hdr_y(2) - 10, [], 10), (hdr_y(2) + 5, ['B'], HDR)):   # (the next header 10 px below the top pushes the pinned one up: only its last 10 px show, without its letter)
        frame(m, off)
        pin = [f for f in m.fills if f[0] == O['SG_HDR_BG']]
        got = [t for (t, r), s in zip(m.texts, m.text_styles) if s == 'label_hdr' and r[1] == 0]
        expect(pin == [(O['SG_HDR_BG'], 0, 0, 320, fill_h)] and got == letters, f'at offset {off} the pinned band is {fill_h} px high with the letters {letters}: {pin} {got}')
    frame(m, TOP - 10)
    expect(not [f for f in m.fills if f[0] == O['SG_HDR_BG']], 'while the large title is in view nothing is pinned')

    # 2. Index Rail on: the rail is the Songs page's column, one letter per section; a touch grabs it, jumps to the section's header and shows the bubble
    m = opened(rail=b'1\n')
    geo = tuple(m.props.get((m.rail, c)) for c in 'xywh')
    span = len(AZ_SECS) * O['SG_RAIL_PITCH']
    expect(vis(m, 'sg_rail') == (1, 1) and geo[0] == O['SG_RAIL_X'] and geo[2] == O['SG_RAIL_W'] and geo[3] == span + 2 * O['SG_RAIL_PAD'] and abs(geo[1] + geo[3] / 2 - (50 + VIEW_H / 2)) <= 1,
           f'the rail shows: x 284, 36 wide, the span {span} px and the margins, centred on the list ({geo})')
    expect(content_h(m) == content and heads_of(m)[hdr_y(1)] == 'A', 'the rail does not change the rows or the headers (the same positions and heights)')
    inset = O['SG_RAIL_INSET']   # the rail's footprint (patch/azlist.c az_inset): the rows leave room for it, so the hairline, the chevron and the text end move left by it
    scroll_to(m, 0); blits, texts = paint(m)
    titles = [(t, r) for (t, r), s in zip(m.texts, m.text_styles) if s == 'label_row_title']
    hair = [f for f in m.fills if f[0] == O['LIST_HAIR']]
    expect(inset == O['LIST_HAIR_END'] - O['SG_RAIL_X'] == 26 and titles and all(r[0] == TX and r[2] == TW - inset for _, r in titles) and hair and all(f[1] == HX and f[3] == HW - inset for f in hair)
           and m.chevs and {b[2][:2] for b in m.chevs} >= {(O['LIST_CHEV_X'] - inset, row_y(0) + (ROW - 1 - CHEV_PX[1]) // 2)} and not any(b[2][0] == O['LIST_CHEV_X'] for b in m.chevs),
           f'Index Rail on: the texts end {inset} px earlier (x {TX + TW - inset}), the hairlines end at x {O["LIST_HAIR_END"] - inset}, the chevrons stand at x {O["LIST_CHEV_X"] - inset}, clear of the rail (x {O["SG_RAIL_X"]})')
    for i in (2, 4):
        m.calls = []
        rail_touch(m, 'down', i, len(AZ_SECS))
        want = min(hdr_y(i), content - VIEW_H)
        expect(any(c[0] == 'widget_grab' and c[2] == m.rail for c in m.calls) and ('widget_set_prop_int', m.widgets['albums_scrollview'], 'yoffset', want) in m.calls and vis(m, 'sg_bubble')[0] == 1,
               f'a touch on the rail grabs it and jumps to section {AZ_SECS[i][1]}\'s header ({want}), the bubble shows')
        expect(('widget_set_text_utf8', m.widgets['sg_bubble_letter'], AZ_SECS[i][1]) in m.calls, 'the bubble shows the letter')
        rail_touch(m, 'up', i, len(AZ_SECS), 3100)
        expect(any(c[0] == 'widget_ungrab' and c[2] == m.rail for c in m.calls) and vis(m, 'sg_bubble')[0] == 0, 'the release lets go and hides the bubble')
    m.calls = []; rail_touch(m, 'down', 0, len(AZ_SECS))
    expect(('widget_set_prop_int', m.widgets['albums_scrollview'], 'yoffset', 0) in m.calls, 'the first section is the top of the list')
    rail_touch(m, 'up', 0, len(AZ_SECS), 3100)
    m.calls = []; rail_touch(m, 'down', 3, len(AZ_SECS)); m.call(PSYMS['al_on_bg'], count=4000000)
    expect(any(c[0] == 'widget_ungrab' and c[2] == m.rail for c in m.calls) and vis(m, 'sg_bubble')[0] == 0, 'a window put in front releases the rail')

    # 3. The grid has no rail and no headers; the View row brings them to the list and takes them away again, the rail with the Index Rail switch
    m = opened(rail=b'1\n', mode=b'1\n')
    expect(vis(m, 'sg_rail') == (0, 0) and vis(m, 'sg_bubble')[0] == 0 and not heads_of(m), 'the grid: no rail, no bubble, no section letter')
    view_switch(m, 40000000)
    expect(page_mode(m) == 1 and vis(m, 'sg_rail') == (1, 1) and content_h(m) == content and heads_of(m)[hdr_y(1)] == 'A', 'the list: the rail and the headers')
    view_switch(m, 40000000)
    expect(page_mode(m) == 0 and vis(m, 'sg_rail') == (0, 0) and not heads_of(m) and content_h(m) == TOP + RGAP + ((n + COLS - 1) // COLS) * PITCH, 'back to the grid: the rail goes, the content is the grid\'s')
    m = opened(rail=b'0\n', mode=b'1\n')
    view_switch(m, 40000000)
    expect(vis(m, 'sg_rail') == (0, 0) and heads_of(m)[hdr_y(1)] == 'A', 'rail off: the list has its headers and still no rail')

    # 4. Section Headers off: no letters, no pinned header, the rows closed up; the rail (when on) still jumps to each section's first row; the four combinations
    for rail, heads in ((b'0\n', b'0\n'), (b'1\n', b'0\n'), (b'1\n', b'1\n'), (b'0\n', b'1\n'), (b'1\n', b'x\n')):
        m = opened(rail=rail, heads=heads)
        hh = 0 if heads == b'0\n' else HDR
        hdr_y, row_y, content = az_model(hh)
        label = f'rail {rail.strip().decode()}, headers {heads.strip().decode()}'
        expect(content_h(m) == content and vis(m, 'sg_rail') == ((1, 1) if rail == b'1\n' else (0, 0)), f'{label}: the content is {content} px, the rail {"shown" if rail == b"1\n" else "hidden"}')
        if hh:
            expect(heads_of(m) and any(f[0] == O['SG_HDR_BG'] for f in (frame(m, 100) and m.fills)), f'{label}: the headers and the pinned header are there')
        else:
            letters = [frame(m, off) for off in range(0, max(content - VIEW_H, 0) + 100, 100)]
            fills_hdr = []
            for off in range(0, max(content - VIEW_H, 0) + 100, 100):
                frame(m, off); fills_hdr += [f for f in m.fills if f[0] == O['SG_HDR_BG']]
            expect(not any(letters) and not fills_hdr, f'{label}: no section letter and no pinned band at any offset')
            blits, texts = paint(m)
            frame(m, 150)
            tl = [r[1] for (t, r), s in zip(m.texts, m.text_styles) if s == 'label_row_title']
            expect(tl == [row_y(i) - 150 + TY for i in range(n) if row_y(i) - 150 + ROW > 0 and row_y(i) - 150 < VIEW_H], f'{label}: the rows lie {ROW} px apart from the top ({tl})')
        if rail == b'1\n':
            for i in (1, 2, 4):
                m.calls = []
                rail_touch(m, 'down', i, len(AZ_SECS))
                want = min(hdr_y(i), content - VIEW_H)
                expect(('widget_set_prop_int', m.widgets['albums_scrollview'], 'yoffset', want) in m.calls, f'{label}: the rail jumps to section {AZ_SECS[i][1]} at {want}' + (' (its first row)' if not hh else ' (its header)'))
                if not hh: expect(want == min(TOP + AZ_SECS[i][0] * ROW, content - VIEW_H), 'which is the section\'s first row')
                rail_touch(m, 'up', i, len(AZ_SECS), 3100)
    # a tap on a row is on the row where the closed-up geometry puts it
    m = opened(heads=b'0\n')
    tap_at(m, 100, TOP + 2 * ROW + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 2) in m.calls, 'headers off: the third row is at TOP + 128 and opens album 2')
    m = opened()
    calls = tap_at(m, 100, TOP + HDR + 2 * ROW + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 1) in calls, 'headers on: a header is dead and the rows start under it (the third row of the first two sections is album 1)')
    calls = tap_at(m, 100, TOP + 10, 5000)
    expect(not any(c[0] == 'navigator_to_with_context' for c in calls), 'a touch on a header opens nothing')
    calls = tap_at(m, 100, 10, 6000)
    expect(not any(c[0] == 'navigator_to_with_context' for c in calls), 'a touch on the title block opens nothing')

    # 5. Only the Title order has sections: Z-A mirrors them (Z first, "#" last); the Artist, Recently Added and Year orders are plain lists, rail off or on
    m = opened(rail=b'1\n', sort_file=b'a\n')
    hdr_y, row_y, content = az_model(HDR, [(0, 'Z'), (1, 'D'), (3, 'C'), (4, 'B'), (6, 'A'), (8, '#')])
    got = heads_of(m)
    expect(content_h(m) == content and [got[y] for y in sorted(got)] == ['Z', 'D', 'C', 'B', 'A', '#'], f'Title Z-A: the sections run Z..A and "#" last ({[got[y] for y in sorted(got)]}, {content_h(m)} == {content})')
    expect(vis(m, 'sg_rail') == (1, 1), 'Title Z-A: the rail shows')
    for k, name in ((b'1\n', 'Artist'), (b'2\n', 'Recently Added'), (b'3\n', 'Year'), (b'b\n', 'Artist Z-A')):
        m = opened(rail=b'1\n', sort_file=k)
        expect(content_h(m) == TOP + n * ROW and vis(m, 'sg_rail') == (0, 0) and not heads_of(m), f'{name}: a plain list, no headers, no rail ({content_h(m)})')
    m = opened(rail=b'1\n', sort_file=b'1\n')   # the sort card's Title row brings the sections back, and takes them away again
    m.call(PSYMS['al_on_item'], a0=0, count=40000000)
    expect(vis(m, 'sg_rail') == (1, 1) and heads_of(m)[az_model(HDR)[0](1)] == 'A', 'Title chosen from the card: the sections and the rail')
    m.call(PSYMS['al_on_item'], a0=1, count=40000000)
    expect(vis(m, 'sg_rail') == (0, 0) and not heads_of(m) and content_h(m) == TOP + n * ROW, 'Artist chosen from the card: a plain list again')
    # 6. The Title order is our name keys (cc_name_keys / cc_key_cmp), not stock's byte classes, so the sections agree with it: stock lists symbol-led titles after Z
    # ("÷", "=", "(What's the Story) Morning Glory?", shortened here to fit a row), kana after the Latin letters; here "#" holds digits and symbols first, すずめ is under S and Z holds only Zeta
    stock = ['Zeta', "(What's the Story)?", 'The Dark Side of the Moon', '\u00f7', 'Blue', '\u3059\u305a\u3081', '=', '1999', 'Abbey Road', 'Wall', 'Wish You Were Here']
    want = ['1999', '=', '\u00f7', 'Abbey Road', 'Blue', 'The Dark Side of the Moon', '\u3059\u305a\u3081', 'Wall', "(What's the Story)?", 'Wish You Were Here', 'Zeta']

    def rows_and_heads(m):
        rows, heads = {}, {}
        for off in range(0, max(content_h(m) - VIEW_H, 0) + 100, 100):
            scroll_to(m, off); paint(m)
            for (t, (x, y, w, h)), sty in zip(m.texts, m.text_styles):
                if y > 0 and sty == 'label_row_title': rows[y + scroll_of(m)] = t
                if y > 0 and sty == 'label_hdr': heads[y + scroll_of(m)] = t
        return [rows[y] for y in sorted(rows)], [heads[y] for y in sorted(heads)]
    for data, order, letters in ((b'0\n', want, ['#', 'A', 'B', 'D', 'S', 'W', 'Z']), (b'a\n', want[::-1], ['Z', 'W', 'S', 'D', 'B', 'A', '#'])):
        m = opened(rail=b'0\n', sort_file=data, titles=stock)
        got, heads = rows_and_heads(m)
        expect(got == order, f'Title {data!r}: our name order, symbols and digits under "#" ({got})')
        expect(heads == letters, f'Title {data!r}: the sections {letters}: Z holds only Zeta, すずめ is under S ({heads})')
    # no memory for the ranks: a plain list, no rail
    m = albums_machine(n, az=True, title=lambda i: AZ_TITLES[i]); m.fs[AZ_RAIL] = b'1\n'; m.fs[ALBUMS_FILE] = b'0\n'; m.calloc_fail_size = n
    open_grid(m)
    expect(content_h(m) == TOP + n * ROW and vis(m, 'sg_rail') == (0, 0) and not heads_of(m), 'no memory for the ranks: a plain list, no headers, no rail')
    # the Settings Files page's rows and the reads: a page reads its two files when it opens (a change shows on the next open)
    m = opened(rail=b'1\n', heads=b'0\n')
    m.fs[AZ_RAIL], m.fs[AZ_HEAD] = b'0\n', b'1\n'
    expect(content_h(m) == az_model(0)[2] and vis(m, 'sg_rail') == (1, 1), 'the switches are read when the page opens: a change meanwhile waits for the next open')



def loading_tests(ctx):
    """A source's Albums page (all, and an artist's) before its list is there: the state decides. LOADING is the one spinner and nothing else (the large title stays); FAILED / OFFLINE say why;
    READY is "No albums"; a list with rows is never asked; the rows arriving remove the spinner."""
    expect = ctx.expect
    status = lambda m: m.props.get((m.widgets['label_status'], 'visible')) == 1
    spin = lambda m: m.props.get((m.widgets['al_spin'], 'visible')) == 1
    for scoped in (False, True):
        what = 'an artist\'s albums' if scoped else 'Albums'
        for grid in (True, False):
            m = fake_albums_machine(0, grid=grid); m.fake_state = 1
            artist = m.record(album='', artist='Fake Artist', path='nd://ar1', title='Fake Artist', rid=-9) if scoped else 0
            m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=artist, count=20000000)
            expect(('state', 0, artist) in m.fake_log and spin(m) and not status(m) and m.props.get((m.widgets['view_grid'], 'visible')) == 1,
                   f'{what} ({"grid" if grid else "list"}) loading: asked src->state(LS_ALBUMS, scope), one spinner, no status line, the title block stays')
            expect(('timer_add', PSYMS['ls_spin_tick'], 250) in m.calls, f'{what}: the spinner turns on a timer')
            m.fake_rows = [m.record(album='First', artist='One', path='nd://f', rid=-2), m.record(album='Second', artist='One', path='nd://g', rid=-3)]
            m.fake_state, m.fake_gen = 0, m.fake_gen + 1
            m.fake_scoped = {artist: m.fake_rows} if scoped else {}
            m.call(PSYMS['al_on_gen'], count=20000000)
            blits, texts = settle(m)
            expect(not spin(m) and not status(m) and {'First', 'Second'} & {t[0] for t in texts}, f'{what}: the albums arrive, the spinner goes and the grid shows')
        for st, text in ((0, 'No albums'), (2, "Can't connect to the server"), (3, 'Connect to Wi-Fi first')):
            m = fake_albums_machine(0); m.fake_state = st
            artist = m.record(album='', artist='Fake Artist', path='nd://ar1', title='Fake Artist', rid=-9) if scoped else 0
            m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=artist, count=20000000)
            expect(status(m) and not spin(m) and ('widget_set_tr_text', m.widgets['label_status'], text) in m.calls, f'{what}: state {st} says {text!r}, no spinner')
    m = fake_albums_machine(4); m.fake_state = 1
    m.call(PSYMS['albums_open_src'], a0=m.fake_src, a1=0, count=20000000)
    expect(not any(e[0] == 'state' for e in m.fake_log) and not spin(m) and not status(m), 'cached rows: shown at once, the state is not asked, no spinner')


SECTIONS = [layout_tests, taps_list_tests, toggle_tests, stock_widget_tests, background_build_tests, foreground_loader_tests, card_asset_tests, sort_card_tests, reverse_tests, title_tests, az_tests, src_tests, loading_tests, nextalbum_tests]   # tools/check.py runs each as its own task

def run(ctx):
    for section in SECTIONS: section(ctx)

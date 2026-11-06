"""The Daily Mix page (patch/dailymix.c dp_*, ui/m1plus_dailymix.bin, tools/pod_dailymix.py DP_*, docs/modules/dailymix.md "The page").

The compiled payload runs under Unicorn on the Home menu (the Daily Mix card's machine, test/pod/dailymix.py DM) with a second window of real widget
structs, the page: window > list_view > scroll_view > the content view (demo's own layouter, scroll_view, hit testing and pointer code), the stock
library, playlist table and canvas mocked. The checks:
  constants    patch/offsets.inc DP_* against tools/pod_dailymix.py, the measured vertical rhythm, the asset's widgets, the images
  colours      the tint over many palettes: white text, the artist / description grey and the Updated accent at 4.5:1 or more; the tint is a 565 word
  art          the page art in C against the model, pixel for pixel; its last rows are the tint; the cost of making it at open
  open         the card's tap opens the page (window, widgets, tint on the four widgets, sizes, events, one loader timer), falls back to the stock Songs page
  paint        the header and the songs at the top and scrolled, in window coordinates, nothing decoded in paint
  loader       one cover a tick, none while the list moves, the ring
  touch        a row plays the mix from that song, Shuffle, Play, drags, aborts, a song missing on the card, the playlist gone or renamed
  texts        13 languages: every line fits, the description in two lines at most, the Updated line (today, yesterday, a date)
  free         destroy frees everything and a second open works"""
import importlib.util, os, random, struct, sys
from unicorn import mips_const
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_F0
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui, mod_icons, pod_dailymix as D, pod_mix as X, pod_i18n, ah_ink
from awtk_text import Ttf, StbText

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


dm_t, pulldown = sibling("dailymix"), sibling("pulldown")
written = dm_t.written
stock_world, key_of, b8, day_of, MIX, ART = dm_t.stock_world, dm_t.key_of, dm_t.b8, dm_t.day_of, dm_t.MIX, dm_t.ART
EVT_DOWN, EVT_UP, EVT_ABORT, EVT_BG, EVT_FG, EVT_DESTROY, EVT_PAINT, EVT_CLICK = (O[k] for k in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT', 'EVT_WINDOW_TO_BG',
                                                                                    'EVT_WINDOW_TO_FG', 'EVT_DESTROY', 'EVT_AFTER_PAINT', 'EVT_CLICK'))
EVT_SCROLL, EVT_SCROLL_END = O['EVT_SCROLL'], O['EVT_SCROLL_END']
SC_YOFF = O['SC_YOFF']
SCR = 300      # the scroll offset the song tests use: rows 0..5 are in view
ROW, VIEW_H, ROWS_Y = O['LIST_ROW_H'], O['DP_VIEW_H'], O['DP_DESC_Y'] + O['DP_DESC_LINES'] * O['DP_DESC_PITCH'] + O['DP_DESC_BELOW']
TAP = O['SC_DRAG_PX']
PAGE_WIDGETS = ('dp_listview', 'dp_scrollview', 'view_dm', 'btn_dp_shuffle', 'btn_dp_play', 'img_dp_glyph', 'btn_dp_add', 'btn_return', 'label_dp_title', 'label_dp_sub', 'label_dp_upd',
                'label_dp_desc', 'label_dp_play', 'label_dp_row', 'label_dp_artist', 'label_title')
ASSET = os.path.join('rootfs', 'release', 'assets', 'default', 'raw', 'ui', 'm1plus_dailymix.bin')
VT = {'window': LI_VT, 'list_view': LV_VT, 'scroll_view': SV_VT, 'scroll_bar_m': 0x97a1f8, 'button': BTN_VT, 'image': IMG_VT}
GREY, ACCENT = 'label_dp_artist', 'label_dp_upd'
SYSBAR_VT, SYSBAR_BOTTOM_VT = 0x97bd60, 0x97bcc0   # g_system_bar_vtable, g_system_bar_bottom_vtable (.dynsym): the status bar's and the navbar's types


def u32(v): return v & 0xffffffff


class PG(dm_t.DM):
    """The Home menu with the card (DM) and, beside it, the page's window as real widget structs built from the built asset. window_open answers with it
    once the page is wanted; widget_set_style, value_set_uint32 and widget_measure_text (the mocked canvas: 8 px a character, 16 for CJK) are recorded."""
    DELIVER_COUNT = 300000000   # a tap on the Home card opens the page, which makes its art in the same handler

    def __init__(self, tree=None, **kw):
        super().__init__(**kw)
        self.styled, self.measured, self.starts = [], [], []
        for n in ('widget_set_style', 'value_set_uint32', 'widget_measure_text'): self.handlers[pod.FUNCTIONS[n][2]] = n
        self.u.mem_map(SCRATCH + 0x900000, 0x100000)
        self.handlers[0x742c90] = 'strcmp'      # the libc stubs the stock scroll bar code calls (the Albums test's)
        self.handlers[0x742850] = '__divdi3'
        self.page = {}
        tree = tree or awtk_ui.parse(open(os.path.join(WORK, ASSET), 'rb').read())
        self.build_page(tree)
        self.canvas = self.alloc(0x80)
        self.window_home = self.window

    # ---- the page's widgets: every widget of the asset as a struct, the list as the stock structure
    def build_page(self, tree):
        def make(w, parent):
            f = 0x1 | (0x4 if w.get('visible') != 'false' else 0) | (0x8 if w.get('sensitive') != 'false' else 0)
            a = self.widget(VT.get(w.type, self.zv), w.x, w.y, w.w, w.h, parent, emitter=True)
            self.u.mem_write(a + 0x24, struct.pack('<H', f))
            if w.name: self.page[w.name] = a
            kids = [make(c, a) for c in w.children]
            if kids: self.kids(a, kids)
            return a
        self.pwin = make(tree, 0)
        for n, a in self.page.items(): self.widgets[n] = a
        lv, sv, view = self.page['dp_listview'], self.page['dp_scrollview'], self.page['view_dm']
        bar = self.page.get('scroll_bar_m', 0)
        self.psv, self.pview, self.plv = sv, view, lv
        self.setword(self.pwin + 8, 320); self.setword(self.pwin + 0xc, 450)
        self.setword(sv + 0x70, SV_VT)
        for off, v in ((0x78, self.s32(sv + 8)), (0x7c, VIEW_H), (0xec, 0x611450), (0xf0, pulldown.LV_HOOK), (0xf4, pulldown.PAINT_HOOK)): self.setword(sv + off, v)
        speed = self.word(0x759814); self.setword(sv + 0x88, speed); self.setword(sv + 0x8c, speed)
        for off, v in ((0x7c, 64), (0x84, sv)): self.setword(lv + off, v)
        lay = self.alloc(0x1c); self.u.mem_write(lay, bytes(0x1c)); self.setword(lay + 0xc, pulldown.LAYOUTER_VT); self.u.mem_write(lay + 0x1a, bytes([4]))
        self.setword(sv + 0x64, lay)
        self.setword(lv + 0x88, bar)
        self.props[(sv, 'h')] = VIEW_H
        self.pwm = self.alloc(0x80)
        self.mem_geometry, self.live_scroll = True, frozenset({sv})

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        if name == '__divdi3':   # libgcc: signed 64 bit division (a1:a0 / a3:a2) -> v1:v0 (the scroll bar's value maths)
            r = [u.reg_read(x) for x in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)]
            s64 = lambda lo, hi: struct.unpack('<q', struct.pack('<II', lo, hi))[0]
            n, d = s64(r[0], r[1]), s64(r[2], r[3])
            lo, hi = struct.unpack('<II', struct.pack('<q', int(n / d) if d else 0))
            u.reg_write(UC_MIPS_REG_V0, lo); u.reg_write(mips_const.UC_MIPS_REG_V1, hi); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        ret = lambda v=0: (u.reg_write(UC_MIPS_REG_V0, v & 0xffffffff), u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)))
        if name == 'widget_set_style':
            self.styled.append((a0, self.read_cstr(a1), self.word(a2 + 8))); return ret(0)
        if name == 'value_set_uint32':
            self.setword(a0, 7); self.setword(a0 + 8, a1); return ret(a0)
        if name == 'widget_measure_text':   # the mocked canvas' widths
            n = 0
            while self.word(a1 + 4 * n): n += 1
            t = ''.join(map(chr, struct.unpack(f'<{n}I', self.u.mem_read(a1, 4 * n)))) if n else ''
            w = float(sum(16 if ord(c) >= 0x2e80 or c == '…' else 8 for c in t))
            self.measured.append((a0, t, w))
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        super()._hook(u, address, size, _)


    # ---- the world: a library, a playlist of ours with `n` songs, a mix file, favourites
    def world(self, songs, n=12, fav=(), order=None, tones=None, names=('Radiohead', 'Björk', 'Air'), aseed=0x0badf00d, covers=(), day=None):
        """The library is `songs`; the mix is n of them (order: their indices, default the first n) and is the mix file's paths."""
        stock_world(self, songs, {}, (), set(fav))
        order = list(range(n)) if order is None else list(order)
        self.library, self.order = songs, order
        self.songs = [songs[i] for i in order]            # the mix's songs in play order
        self.tones = tones or [(70, 110, 190), (190, 90, 120), (60, 140, 150)]
        self.day = day if day is not None else day_of(self.wall, self.tz)
        self.mixfile = X.dump_mix(self.day, 0x1234abcd, aseed, 0, self.tones, list(names), [s['path'] for s in self.songs])
        self.fs[MIX] = self.mixfile
        self.aseed, self.n = aseed, len(order)
        for i in covers:
            s = self.songs[i]; self.cover(s['artist'], s['album'], (40 + i * 15 % 200, 100, 30 + 10 * i % 200), size=168)

    def boot(self, **kw):
        """The Home card up with the mix (the card's art file absent: the card shows its flat grey, the page does not use it)."""
        self.start_dm(); self.clock = 1
        self.window = self.pwin
        return self

    def card_tap(self):
        """A tap on the card: the stock pointer path, then the payload's dm_on_up. The calls it made."""
        self.scroll_to(250)
        cx, cy = self.card_xy(60, 30)
        self.tap(cx, cy)
        return self.calls_all

    # ---- the page
    def pw(self, name): return self.page[name]
    def poff(self): return self.s32(self.psv + SC_YOFF)
    def pscroll(self, y): self.setword(self.psv + SC_YOFF, u32(y))

    def paint(self, off=None):
        """One EVT_AFTER_PAINT on the content view, the canvas where the stock scroll_view leaves it (origin = the window's top 30 less the offset). Returns (blits, texts, text styles, fills)."""
        if off is not None: self.pscroll(off)
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.setword(self.canvas + O['CANVAS_OY'], u32(30 - self.poff()))
        self.blits.clear(); self.texts.clear(); self.measures.clear(); self.fills.clear(); self.text_styles.clear(); self.draw_oy.clear()
        self.oy_canvas = self.canvas
        fn, ctx = self.bound[(self.pview, EVT_PAINT)]
        self.call(fn, a0=ctx, a1=ev, count=400000000)
        self.oy_after = self.s32(self.canvas + O['CANVAS_OY'])
        return list(self.blits), list(self.texts), list(self.text_styles), list(self.fills)

    def fire_page_window(self, ev, count=20000000):
        fn, ctx = self.bound[(self.pwin, ev)]
        return self.call(fn, a0=ctx, a1=0, count=count)

    def fire_page(self, name, ev, count=40000000):
        fn, ctx = self.bound[(self.page[name], ev)]
        return self.call(fn, a0=ctx, a1=0, count=count)

    def ppointer(self, kind, x, y, dt=16, abort=False):
        """One pointer event at the page window: demo's widget_on_pointer_down / _move / _up, then the events the stock code dispatched to the handlers the payload bound."""
        self.t += dt
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, O['EVT_POINTER_ABORT'] if abort else POINTER_EVT[kind]); self.setword(e + 4, 0x30); self.setword(e + 8, self.t)
        self.setword(e + 0x18, x); self.setword(e + 0x1c, y)
        self.u.mem_write(e + 0x24, bytes([0 if kind == 'u' else 1]))
        self.queue, self.log = [], []
        self.call(POINTER_ON[kind], a0=self.pwin, a1=e, count=8000000)
        for owner, evt, raw in self.queue:
            self.fired.append((self.name_of(owner), evt))
            if (owner, evt) in self.bound:
                fn, ctx = self.bound[(owner, evt)]
                ev = self.alloc(0x30); self.u.mem_write(ev, raw)
                self.call(fn, a0=ctx, a1=ev, count=40000000)
                self.calls_all += self.calls

    def pgesture(self, steps):
        self.fired = []; self.calls_all = []
        for s in steps:
            if s[0] == 'a': self.ppointer('u', s[1], s[2], *s[3:], abort=True)
            else: self.ppointer(s[0], s[1], s[2], *s[3:])
        return self.calls_all

    def ptap(self, x, y): return self.pgesture([('d', x, y, 0), ('u', x, y, 60)])

    def ptarget(self, x, y):
        w, path = self.pwin, ['window']
        names = {v: k for k, v in self.widgets.items()}
        while True:
            t = self.call(FIND_TARGET, a0=w, a1=x, a2=y, count=400000)
            if not t or self.flags(t) & 9 != 9: return path
            w = t; path.append(names.get(t, hex(t)))

    def row_xy(self, i, dx=100, dy=30):
        """The window point inside song row i at the current scroll (the list is the whole window: window coordinates are the content's less the offset)."""
        return dx, ROWS_Y + i * ROW + dy - self.poff()

    def timer_fn(self):
        return [c for c in self.timers if c[0] == PSYMS['dp_on_load']]


def covers_of(blits):
    """The song covers of a frame: 52 px wide blits of a 52 px wide source (the last row of a view may be cut short)."""
    return [b for b in blits if b[2][2] == 52 and b[1][2] == 52]


def word_of(px): return 0xff000000 | px[0] | px[1] << 8 | px[2] << 16


def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, RAW)
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    width = lambda t, px: StbText(font, px).layout(t)[1]
    songs, rr = dm_t.library()
    seen, uniq = set(), []   # one song of each album: every row has its own cover
    for s_ in songs:
        if s_['album'] not in seen: seen.add(s_['album']); uniq.append(s_)
    tones = [(70, 110, 190), (190, 90, 120), (60, 140, 150)]

    # ===== 1. constants, the measured rhythm, the asset, the images
    names = [k for k in O if k.startswith('DP_') and hasattr(D, k)]
    expect(len(names) >= 35 and all(O[k] == getattr(D, k) for k in names), f'patch/offsets.inc DP_* equal tools/pod_dailymix.py ({[k for k in names if O[k] != getattr(D, k)]}; {len(names)} numbers)')
    expect(O['DP_ROWS_Y'] == D.DP_ROWS_Y == ROWS_Y == 371, 'the first song row starts at 371: the description is two lines high in every language')
    expect(O['DP_PILL_INK'] == D.DP_PILL_INK == 0x1e1c1c, 'the pill\'s text colour is #1C1C1E (r | g << 8 | b << 16)')
    f = ah_ink.font(WORK)
    lay = D.page_layout(f)
    expect((lay['title'][0], lay['sub'][0], lay['upd'][0], lay['btn_y'], lay['desc_y']) == (O['DP_TITLE_Y'], O['DP_SUB_Y'], O['DP_UPD_Y'], O['DP_BTN_Y'], O['DP_DESC_Y']),
           f'the vertical numbers are the measured rhythm on the shipped font ({lay})')
    caps = {px: ah_ink.cap(f, px) for px in (D.DP_TITLE_PX, D.DP_SUB_PX, D.DP_UPD_PX, D.DP_DESC_PX)}
    base = lambda key, px: ah_ink.baseline(f, px, lay[key][0], px)
    gaps = (lay['title'][0] + (24 - 24) // 2 + f.baseline(24) - caps[24] - D.DP_ART_H,
            lay['sub'][0] + f.baseline(17) - caps[17] - base('title', 24),
            lay['upd'][0] + f.baseline(14) - caps[14] - base('sub', 17),
            lay['btn_y'] + (D.DP_BTN_H - D.DP_PILL_H) // 2 - base('upd', 14),
            lay['desc_y'] + (D.DP_DESC_PITCH - D.DP_DESC_PX) // 2 + f.baseline(15) - caps[15] - (lay['btn_y'] + (D.DP_BTN_H - D.DP_PILL_H) // 2 + D.DP_PILL_H))
    expect(gaps == (16, 9, 9, 16, 16), f'ink gaps: art to title capitals 16, title baseline to subtitle capitals 9, subtitle to Updated 9, Updated baseline to the pill 16, pill to the description 16 ({gaps})')
    shuf_l, shuf_r = D.DP_SHUF_X + (D.DP_SHUF_W - D.DP_DISC) // 2, D.DP_SHUF_X + (D.DP_SHUF_W + D.DP_DISC) // 2      # the Shuffle disc as drawn
    add_l, add_r = D.DP_ADD_X + (D.DP_ADD_W - D.DP_DISC) // 2, D.DP_ADD_X + (D.DP_ADD_W + D.DP_DISC) // 2           # the Add disc as drawn
    pill_l, pill_r = D.DP_PLAY_X, D.DP_PLAY_X + D.DP_PLAY_W
    expect((shuf_l, shuf_r, pill_l, pill_r, add_l, add_r) == (34, 74, 86, 234, 246, 286) and pill_l - shuf_r == add_l - pill_r == D.DP_BTN_GAP == 12 and D.DP_ADD_W == D.DP_SHUF_W
           and shuf_l + add_r == 320 and D.DP_SHUF_X + D.DP_ADD_X + D.DP_ADD_W == 320 and D.DP_PLAY_X + pill_r == 320 and (shuf_l + add_r) // 2 == 160,
           'Shuffle disc | Play pill | Add disc are symmetric about x 160: drawn 34..74, 86..234, 246..286, equal gaps of 12 px')
    expect(D.DP_SHUF_X + D.DP_SHUF_W < D.DP_PLAY_X and D.DP_PLAY_X + D.DP_PLAY_W < D.DP_ADD_X and D.DP_ADD_X + D.DP_ADD_W <= 320 and D.DP_PLAY_W < 180, 'the touch rectangles do not overlap and the pill is shorter than the old 180')
    expect(all(O[k] == getattr(D, k) for k in ('DP_ADD_X', 'DP_ADD_W')), 'patch/offsets.inc has the Add disc\'s numbers')
    expect(D.DP_BACK_BTN >= 44 and D.DP_BACK_DISC <= D.DP_BACK_BTN and D.DP_BTN_H >= 44 and D.DP_SHUF_W >= 44 and D.DP_ADD_W >= 44 and D.DP_PLAY_W >= 44, 'every control is at least 44 px')
    tree = awtk_ui.parse(open(os.path.join(WORK, ASSET), 'rb').read())
    expect(tree.name == 'm1plus_dailymix_page' and [c.name for c in tree.children][:2] == ['dp_listview', 'btn_return'] and tree.children[1].type == 'button'
           and not [c for c in tree.children if c.type in ('view',)] and 'navigationbar_view' not in [w.name for w in tree.walk()], 'the window: the list, then the back button; no navbar')
    lv = tree.find('dp_listview'); sv = tree.find('dp_scrollview'); view = tree.find('view_dm'); back = tree.find('btn_return')
    expect((lv.x, lv.y, lv.w, lv.h) == (0, 0, 320, 450) and lv.type == 'list_view' and sv.type == 'scroll_view' and (sv.w, sv.h) == (310, 450) and view.type == 'view' and view.w == 320
           and tree.find('scroll_bar_m') is not None and tree.find('scroll_bar_m').h == 450, 'the stock list structure over the whole 450 px window: list_view > scroll_view 310 + the mobile scroll bar > one content view')
    expect((back.x, back.y, back.w, back.h) == (8, 8, 44, 44) and back.get('style:normal:icon') == 'dp_back' and back.get('style:pressed:icon') == 'dp_back_down', 'the back disc is a 44 px touch square at (8, 8) with the glass images, the window\'s last control')
    kids = [c.name for c in view.children]
    shuf, play, glyph, add = (view.find(n) for n in ('btn_dp_shuffle', 'btn_dp_play', 'img_dp_glyph', 'btn_dp_add'))
    expect(kids == ['btn_dp_shuffle', 'btn_dp_play', 'img_dp_glyph', 'btn_dp_add'] and (shuf.x, shuf.y, shuf.w, shuf.h) == (32, 263, 44, 44) and (play.x, play.y, play.w, play.h) == (86, 263, 148, 44)
           and (add.x, add.y, add.w, add.h) == (244, 263, 44, 44)
           and shuf.get('style:normal:icon') == 'ah_shuffle' and play.get('style:normal:icon') == 'dp_pill' and play.get('style:pressed:icon') == 'dp_pill_down'
           and glyph.get('sensitive') == 'false' and glyph.get('image') == 'dp_play', 'the content view holds the Shuffle disc, the Play pill and its insensitive dark glyph (the glass images of the album page and the white pill) and the Add disc')
    expect(add.get('style') == shuf.get('style') == 'img_btn_style' and add.get('enable') == 'true' and add.get('visible') != 'false' and add.get('sensitive') != 'false'
           and [add.get(f'style:{s}:icon') for s in ('normal', 'over', 'pressed')] == ['dp_add', 'dp_add', 'dp_add_down'], 'the Add disc is a visible, sensitive img_btn_style button with its own normal and pressed images, like the Shuffle disc')
    labels = {n: tree.find(n) for n in ('label_dp_title', 'label_dp_sub', 'label_dp_upd', 'label_dp_desc', 'label_dp_play', 'label_dp_row', 'label_dp_artist', 'label_title')}
    expect(all(l.get('visible') == 'false' and l.get('sensitive') == 'false' for l in labels.values())
           and [int(labels[n].get('style:normal:font_size')) for n in ('label_dp_title', 'label_dp_sub', 'label_dp_upd', 'label_dp_desc', 'label_dp_play', 'label_dp_row', 'label_dp_artist')] == [24, 17, 14, 15, 18, 21, 18]
           and labels['label_title'].get('tr_text') == 'Daily Mix', 'the text styles are hidden, insensitive labels (24 / 17 / 14 / 15 / 18 px, the rows 21 / 18 as the Albums list); label_title is the hidden page title')
    expect(all(labels[n].get('style:normal:text_color') == '#FFFFFF' for n in ('label_dp_title', 'label_dp_sub', 'label_dp_play')) and labels['label_dp_title'].get('style:normal:text_align_h') == 'center'
           and labels['label_dp_desc'].get('style:normal:text_align_h') == 'left', 'white in the asset (the payload sets the grey, the accent and the pill\'s ink from the tint); centred lines, left description')
    xx = os.path.join(raw, 'images', 'xx')
    from PIL import Image
    ref = mod_icons.album_images()
    same = lambda n: Image.open(os.path.join(xx, n + '.png')).convert('RGBA').tobytes() == ref[n].convert('RGBA').tobytes() and open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read()
    expect(all(same(n) for n in mod_icons.DPAGE), f'the page\'s seven images are in the build and equal the generator ({[n for n in mod_icons.DPAGE if not same(n)]})')
    pill = Image.open(os.path.join(xx, 'dp_pill.png')).convert('RGBA')
    expect(pill.size == (148, 40) and pill.getpixel((74, 20)) == (255, 255, 255, 255) and pill.getpixel((0, 0))[3] == 0 and Image.open(os.path.join(xx, 'dp_back.png')).size == (40, 40)
           and Image.open(os.path.join(xx, 'dp_play.png')).size == (16, 16), 'the white pill is 148 x 40 and opaque white inside, the disc 40, the glyph 16')
    a_n, a_d, s_n, s_d = (Image.open(os.path.join(xx, n + '.png')).convert('RGBA') for n in ('dp_add', 'dp_add_down', 'ah_shuffle', 'ah_shuffle_down'))
    plus_ink = lambda im: Image.eval(im.convert('L'), lambda v: 255 if v > 200 else 0).getbbox()   # the white glyph on the grey disc (0x2A / 0x44)
    expect(a_n.size == s_n.size == a_d.size == s_d.size == (40, 40) and a_n.getpixel((2, 19)) == s_n.getpixel((2, 19)) and a_d.getpixel((2, 19)) == s_d.getpixel((2, 19))
           and a_n.getchannel('A').tobytes() == s_n.getchannel('A').tobytes() and a_n.getpixel((0, 0))[3] == 0 and a_n.getpixel((5, 19)) == (0x2A, 0x2A, 0x2A, 255) and a_d.getpixel((5, 19)) == (0x44, 0x44, 0x44, 255)
           and a_n.tobytes() != s_n.tobytes() and a_d.tobytes() != a_n.tobytes(), 'the Add disc is the Shuffle disc\'s size, shape and two greys (normal 0x2A, pressed 0x44) with another glyph')
    pb, sb = plus_ink(a_n), plus_ink(s_n)
    expect(pb and sb and pb[2] - pb[0] <= sb[2] - sb[0] + 1 and pb[3] - pb[1] <= sb[3] - sb[1] + 1 and abs((pb[0] + pb[2]) - 40) <= 1 and abs((pb[1] + pb[3]) - 40) <= 1 and pb[2] - pb[0] >= 17,
           f'the plus is centred on the disc and as large as the Shuffle glyph ({pb} against {sb})')
    expect(set(mod_icons.DPAGE) <= set(mod_icons.pod_names()), 'the images are added by the build (pod_names)')

    # ===== 2. the colours over many palettes
    import preview_dailymix as P
    palettes = [t for _, t in P.PALETTES]
    palettes += [[(255, 255, 255)] * 2, [(0, 0, 0)] * 2, [(255, 255, 0), (0, 255, 255), (255, 0, 255)], [(0, 0, 255)] * 3, [(0, 255, 0)] * 2, [(255, 0, 0)] * 2, [(10, 10, 12)] * 2, [(250, 250, 210)] * 3]
    rnd = random.Random(99)
    palettes += [[tuple(rnd.randrange(256) for _ in range(3)) for _ in range(rnd.randrange(2, 5))] for _ in range(24)]
    worst = {'white': (99, None), 'grey': (99, None), 'accent': (99, None), 'press': (99, None)}
    vmin, lum_ok, snap_ok = 255, True, True
    for i, t in enumerate(palettes):
        f_ = D.field(t, 700 + i, D.DP_W, D.DP_ART_H)
        last = f_[-1]
        tint = D.tint_of(tuple(sum(px[c] for px in last) // D.DP_W for c in range(3)))
        grey, acc = D.page_colours(tint)
        press = tuple(round(c + (255 - c) * 0x33 / 255) for c in tint)
        for k, cr in (('white', D.contrast((255, 255, 255), tint)), ('grey', D.contrast(grey, tint)), ('accent', D.contrast(acc, tint)), ('press', D.contrast(grey, press))):
            if cr < worst[k][0]: worst[k] = (cr, t)
        vmin = min(vmin, max(tint)); lum_ok &= D.lum16(tint) <= D.DP_LUM_MAX; snap_ok &= tint == D.snap565(tint)
    expect(worst['white'][0] >= 4.5 and worst['grey'][0] >= 4.5 and worst['accent'][0] >= 4.5,
           f'over {len(palettes)} palettes (pale, grey, black, saturated, random) white text {worst["white"][0]:.2f}:1, the artist / description grey {worst["grey"][0]:.2f}:1 and the Updated accent {worst["accent"][0]:.2f}:1 on the tint all reach 4.5:1')
    expect(worst['press'][0] >= 3.0, f'the grey on a pressed row (20 % white over the tint) stays {worst["press"][0]:.2f}:1 (a transient: 3:1 floor)')
    expect(lum_ok and snap_ok and vmin >= D.DP_V_MIN, f'every tint is on the 565 grid, no brighter than the cap and never near black (darkest channel max {vmin})')
    expect(D.tint_of((0, 0, 0)) == D.snap565((48, 48, 48)) and D.tint_of((255, 255, 255)) != (255, 255, 255) and D.pale((0, 0, 0), 184) == (183, 183, 183), 'black lifts to a dark grey, white is darkened to the cap, the grey is the tint lightened by 184/256')
    print(f'  (tint contrast over {len(palettes)} palettes: white {worst["white"][0]:.2f}, grey {worst["grey"][0]:.2f}, accent {worst["accent"][0]:.2f}, grey on a pressed row {worst["press"][0]:.2f})')
    a, tint_a = D.page_art(tones, 7)
    b, _ = D.page_art(tones, 7); c, _ = D.page_art(tones, 8)
    expect(a == b and a != c and len(a) == D.DP_ART_H and all(len(r) == D.DP_W for r in a), 'the page art is a pure function of (tones, seed), 320 x 180')
    expect(all(px == tint_a for px in a[-1]) and all(row == a[-1] for row in a[-D.DP_HOLD:]) and D.fade_alpha(D.DP_ART_H - D.DP_HOLD - 1) == 256 and D.fade_alpha(D.DP_ART_H - D.DP_HOLD - 2) < 256 and D.fade_alpha(D.DP_ART_H - D.DP_FADE - 1) == 0 and D.fade_alpha(D.DP_ART_H - D.DP_FADE + 8) > 0,
           'the last rows are the tint\'s own word (no dither), the fade runs over the last 60 rows')
    dist = lambda row: sum(abs(px[i] - tint_a[i]) for px in row for i in range(3)) / (3 * D.DP_W)
    ds = [sum(dist(a[y + k]) for k in range(4)) / 4 for y in range(D.DP_ART_H - D.DP_FADE - 4, D.DP_ART_H - 3, 4)]
    expect(all(x >= y - 1.0 for x, y in zip(ds, ds[1:])) and dist(a[D.DP_ART_H - D.DP_FADE - 1]) - dist(a[D.DP_ART_H - D.DP_FADE]) < 3 and ds[-1] < 4, f'the fade approaches the tint smoothly, no seam at its start or its end ({[round(x, 1) for x in ds]})')
    bad_fade = []
    for i, t in enumerate(palettes[:6] + palettes[6:14:2] + palettes[-4:]):
        rows_, tint_ = D.page_art(t, 700 + i)
        ok = all(px == tint_ for px in rows_[-1])
        for ch in range(3):      # per channel the row mean moves from the art's side towards the tint and never crosses it by more than one level (a 565 step is 8 / 4)
            means = [sum(px[ch] for px in r) / D.DP_W for r in rows_[D.DP_ART_H - D.DP_FADE:]]
            head = sum(means[:8]) / 8
            sgn = 1 if head > tint_[ch] + 2 else -1 if head < tint_[ch] - 2 else 0
            if max(tint_) <= D.DP_V_MIN + 8: sgn = 0      # a near-black art lifted to the floor tint: its own falloff may cross a channel by a level or two
            blocks = [sum(abs(v - tint_[ch]) for v in means[k:k + 4]) / 4 for k in range(len(means) // 2, len(means), 4)]   # (the first half is still the art's own falloff)
            good = all((v - tint_[ch]) * sgn >= -1.0 for v in means) and all(b <= a + 1.5 for a, b in zip(blocks, blocks[1:]))
            ok &= good
        if not ok: bad_fade.append(t)
    expect(not bad_fade, f'over 14 palettes the luminance of the fade rows moves monotonically from the art towards the tint, per channel within one level, and the last row is the tint ({bad_fade[:1]})')
    expect(all(px[0] == ((px[0] >> 3) << 3 | px[0] >> 5) and px[1] == ((px[1] >> 2) << 2 | px[1] >> 6) and px[2] == ((px[2] >> 3) << 3 | px[2] >> 5) for r in a[::9] for px in r[::7]),
           'every art pixel is an RGB565 value expanded to 8 bits (the panel\'s own grid)')

    # ===== 3. the page opens from the card: the stock sequence, the widgets, the tint, the sizes, the events, one timer
    m = PG(count=PERF); m.world(uniq, 12); m.boot()
    for n in range(12): m.cover(m.songs[n]['artist'], m.songs[n]['album'], (60 + n * 10, 120, 200 - n * 8))
    before_bmps = set(m.bitmaps)
    calls = m.card_tap()
    expect([c for c in calls if c[0] == 'window_open'] == [('window_open', 'm1plus_dailymix')] and not [c for c in calls if c[0] == 'navigator_to_with_context'],
           f'a tap on the card opens ui/m1plus_dailymix.bin and not the stock Songs page ({[c[:2] for c in calls if c[0] in ("window_open", "navigator_to_with_context")]})')
    looked = [c[1] for c in calls if c[0] == 'widget_lookup']
    expect(all(n in looked for n in PAGE_WIDGETS if n != 'label_title'), 'it looks up the list, the content view, the buttons and the seven style labels by name')
    paint_arts = [(b, v) for b, v in m.bitmaps.items() if (v[1], v[2]) == (D.DP_W, D.DP_ART_H)]
    expect(len(paint_arts) == 1, 'one 320 x 180 art bitmap')
    data, w_, h_ = paint_arts[0][1]
    pxs = struct.unpack(f'<{w_ * h_}I', bytes(m.u.mem_read(data, w_ * h_ * 4)))
    mdl_rows, mdl_tint = D.page_art(m.tones, m.aseed)
    expect(list(pxs) == [word_of(px) for row in mdl_rows for px in row], 'the art the payload made at open equals pod_dailymix.page_art pixel for pixel')
    if PERF:
        cost_open = m.icount
        print(f'  (opening the page: {cost_open} instructions for the card tap, art 320 x 180 included)')
        expect(cost_open < 25_000_000, f'opening the page costs under 25 million instructions ({cost_open}; about 20 ms on the device)')
    flags = struct.unpack('<H', m.u.mem_read(paint_arts[0][0] + O['BITMAP_FLAGS'], 2))[0]
    expect(flags & 1, 'the art bitmap is flagged opaque (a plain blit)')
    tw = 0xff000000 | mdl_tint[0] | mdl_tint[1] << 8 | mdl_tint[2] << 16
    sty = lambda name, prop: [v for (w, p, v) in m.styled if w == m.page[name] and p == prop]
    expect(all(sty(n, 'normal:bg_color') == [tw] for n in ('dp_listview', 'dp_scrollview', 'view_dm')) and [v for (w, p, v) in m.styled if w == m.pwin and p == 'normal:bg_color'] == [tw],
           f'the window, the list, the scroll view and the content view all get the one solid tint ({tw:#x})')
    grey, acc = D.page_colours(mdl_tint)
    word = lambda c: 0xff000000 | c[0] | c[1] << 8 | c[2] << 16
    expect(sty('label_dp_upd', 'normal:text_color') == [word(acc)] and sty('label_dp_desc', 'normal:text_color') == [word(grey)] and sty('label_dp_artist', 'normal:text_color') == [word(grey)]
           and sty('label_dp_play', 'normal:text_color') == [word((0x1c, 0x1c, 0x1e))], 'the Updated accent, the description and artist grey and the pill\'s dark ink are set on their style labels')
    expect(m.s32(m.pview + 0xc) == ROWS_Y + 12 * ROW + O['DP_BOTTOM'] and m.word(m.psv + 0x7c) == ROWS_Y + 12 * ROW + O['DP_BOTTOM'],
           f'the content view and the scroll view\'s virtual_h are the header + 12 rows + the air under them ({m.s32(m.pview + 0xc)})')
    evs = {(w, e) for (w, e) in m.bound}
    for name, e in (('view_dm', EVT_DOWN), ('view_dm', EVT_UP), ('view_dm', EVT_ABORT), ('view_dm', EVT_PAINT), ('dp_scrollview', EVT_SCROLL), ('dp_scrollview', EVT_SCROLL_END),
                    ('btn_dp_play', EVT_CLICK), ('btn_dp_shuffle', EVT_CLICK), ('btn_return', EVT_CLICK)):
        expect((m.page[name], e) in evs, f'{name} has its handler for event {e:#x}')
    expect(all((m.pwin, e) in evs for e in (EVT_DESTROY, EVT_FG, EVT_BG)), 'the window has its destroy, to-front and to-back handlers')
    payload_fns = set(PSYMS.values())
    timers = [c for c in calls if c[0] == 'timer_add' and c[1] in payload_fns]   # the payload's (the stock list_item's 30 ms press timer, list_item_cast+0x8c, runs in the Home tap too)
    expect([t[2] for t in timers] == [O['DP_MORE_MS']] and timers[0][1] == PSYMS['dp_on_load'], f'one page timer: the cover loader, {O["DP_MORE_MS"]} ms ({timers})')
    expect(m.bound[(m.page['btn_return'], EVT_CLICK)][0] == PSYMS['pod_on_back'], 'the back disc is the stock back handler')
    ld = [c[1] for c in calls if c[0] == 'loadLocalClassList']
    dq = [c for c in calls if c[0] == 'toolsQueryDbTable']
    expect(0xf001 not in ld and ld.count(0xf00b) == 1 and not {dm_t.CLS_FAV, 0xff13} & set(ld), f'the page does not read the library (loadLocalClassList 0xf001), only the album list for the cover keys and the playlist list once (is the mix saved?), no favourites, no playlist\'s songs ({[hex(x) for x in ld]})')
    expect(len(dq) == 1 and dq[0][1] == '/mnt/data/database.db' and dq[0][2].startswith("select * from songtable where fileurl in ('") and dq[0][3] == 0x4e9058 and dq[0][4] == 0
           and all("'" + p + "'" in dq[0][2] for p in [s['path'] for s in m.songs[:12]]), f'the mix\'s 12 rows come from one stock query of just their paths ({dq})')
    expect(not written(m, [calls]), 'opening the page writes, renames and deletes nothing')
    expect(not [c for c in calls if c[0] == 'widget_load_image' and 'star' in c[1]], 'no star image is loaded')

    # ===== 4. paint: the header at the top, in window coordinates
    blits, texts, styles, fills = m.paint(0)
    art_b = [b for b in blits if b[1][2:] == (D.DP_W, D.DP_ART_H)]
    expect(len(art_b) == 1 and art_b[0][2] == (0, 0, D.DP_W, D.DP_ART_H) and art_b[0][1] == (0, 0, D.DP_W, D.DP_ART_H) and m.oy_after == 30 - 0, 'at the top the art is one blit of the whole bitmap at (0, 0), full width; the canvas origin is put back')
    want = [('Daily Mix', (16, 193, 288, 24), 'label_dp_title'), ('Made for You', (16, 218, 288, 17), 'label_dp_sub'), ('Updated today', (16, 239, 288, 14), 'label_dp_upd'),
            ('Play', (156, 265, 34, 40), 'label_dp_play')]
    got = [(t, r, s) for (t, r), s in zip(texts, styles)]
    expect(got[:4] == want, f'the title, "Made for You", the Updated line and the pill\'s text are drawn centred in their boxes, each in its own style ({got[:4]})')
    desc = [(t, r, s) for (t, r), s in zip(texts, styles) if s == 'label_dp_desc']
    expect([(r[0], r[1], r[2], r[3]) for _, r, _ in desc] == [(16, 317, 288, 20), (16, 337, 288, 20)] and ' '.join(t for t, _, _ in desc) == 'Songs you love and some to rediscover, made fresh every day.',
           f'the description wraps into two lines of 288 px at y 317 and 337 ({desc})')
    rt0 = [(t, r) for (t, r), s in zip(texts, styles) if s in ('label_dp_row', 'label_dp_artist')]
    LX, LY, LT, LW = O['LIST_ART_X'], O['LIST_ART_Y'], O['LIST_TEXT_X'], O['LIST_TEXT_W']
    expect([r for t, r in rt0] == [(LT, ROWS_Y + i * O['LIST_ROW_H'] + y, LW, h) for y, h in ((O['LIST_TITLE_Y'], O['LIST_TITLE_H']), (O['LIST_SUB_Y'], O['LIST_SUB_H'])) for i in range(2)]
           and [t for t, r in rt0] == [m.songs[i][k] for k in ('title', 'artist') for i in range(2)],
           f'at the top the first song row (y {ROWS_Y}) and the second, cut by the window (the clip cuts its texts), have their titles, then their artists at the Albums list\'s x {LT}, {LW} px wide ({rt0})')
    covers0 = covers_of(blits)
    expect(len(covers0) == 2 and covers0[0][2] == (LX, ROWS_Y + LY, 52, 52) and covers0[1][2] == (LX, ROWS_Y + ROW + LY, 52, VIEW_H - (ROWS_Y + ROW + LY)),
           f'the first cover is whole at x {LX} and the second is cut by the view\'s bottom edge ({[c[2] for c in covers0]})')
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'calloc', 'loadLocalClassList', 'timer_add')], 'paint decodes nothing, allocates nothing, reads no list, arms no timer')
    n_meas = len(m.measures)
    m.paint(0)
    expect(len(m.measures) == 0 and n_meas > 0, 'the text is laid out once (a second paint measures nothing)')
    # scrolled into the rows
    blits, texts, styles, fills = m.paint(SCR)
    cov = sorted(b[2] for b in covers_of(blits))
    expect([c for c in cov] == [(LX, ROWS_Y + ROW * i + LY - SCR, 52, 52) for i in range(6)] and not [b for b in blits if b[1][2:] == (D.DP_W, D.DP_ART_H)],
           f'scrolled {SCR}: six song rows (0..5) with their 52 px covers at x {LX}; the art is gone ({cov})')
    expect(not [b for b in blits if b[2][2:] == (14, 14)], 'no star: no row has a mark in the left margin')
    rt = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_dp_row']; at = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_dp_artist']
    expect([r for _, r in rt] == [(LT, ROWS_Y + ROW * i + O['LIST_TITLE_Y'] - SCR, LW, O['LIST_TITLE_H']) for i in range(6)] and [t for t, _ in rt] == [m.songs[i]['title'] for i in range(6)]
           and [r for _, r in at] == [(LT, ROWS_Y + ROW * i + O['LIST_SUB_Y'] - SCR, LW, O['LIST_SUB_H']) for i in range(6)] and [t for t, _ in at] == [m.songs[i]['artist'] for i in range(6)],
           f'titles (white style) and artists (grey style) at x {LT}, {LW} px wide, as the Albums list ({rt[-1:]} {at[-1:]})')
    hair = [f for f in fills if f[0] == O['DP_HAIR']]
    expect([(f[1], f[2], f[3], f[4]) for f in hair] == [(LT, ROWS_Y + ROW * i + 63 - SCR, 320 - LT, 1) for i in range(5)], f'a hairline under each row from the text\'s x ({LT}), not from the cover, to the right edge (the sixth row\'s ends past the view)')
    expect(not [f for f in fills if f[0] == O['DP_PRESS']], 'no row is pressed: no fill')
    # tint behind: the page paints no background of its own
    expect(not [f for f in fills if f[2] == 0 and f[3] >= 320 and f[4] >= 400], 'the page paints no full-window fill: the window colour is the tint')
    # overscroll above the top: the art moves down, nothing before the first row is read
    blits, texts, styles, fills = m.paint(-30)
    expect([b[2] for b in blits if b[1][2:] == (D.DP_W, D.DP_ART_H)] == [(0, 30, D.DP_W, D.DP_ART_H)], 'pulled 30 px past the top the art is drawn 30 px down')
    blits, texts, styles, fills = m.paint(m.s32(m.pview + 0xc) - VIEW_H)
    expect(len(covers_of(blits)) >= 6 and not [c for c in m.calls if c[0] == 'deque_at_oob'], 'scrolled to the end: the last rows, no read past the playlist')
    m.pscroll(0)

    # ===== 5. the loader: one cover a tick, nothing while the list moves, the ring
    def opened(n=12, fav=(), cover_rows=None, mk=None, bmp=True, **world):
        t = PG(**(mk or {})); t.world(uniq, n, fav=fav, **world); t.boot()
        t.bitmap_ok = bmp      # (the tests that do not look at pictures make none: the art is 14 million instructions)
        for i in (range(n) if cover_rows is None else cover_rows): t.cover(t.songs[i]['artist'], t.songs[i]['album'], (60 + i * 7 % 150, 120, 200 - i * 5 % 150))
        t.card_tap()
        return t

    def tick(t, count=40000000):
        t.call(PSYMS['dp_on_load'], count=count)
        return list(t.calls)

    def reopen(t):
        t.fire_page_window(EVT_DESTROY)
        t.window = t.pwin
        return t.card_tap()

    # ===== the status bar: the art's top row while the page is in front, as the album page and Now Playing (patch/dailymix.c dp_bar_*, patch/common.c pod_bar_*)
    def with_bar(t):
        """The window manager's children plus a navbar and a status bar (the stock widget_get_type runs here: a vtable, and the type property it reads), (navbar, bar)."""
        arr = t.word(t.wm + 0x58)
        old = [t.word(t.word(arr + 8) + 4 * i) for i in range(t.word(arr))] if arr else []
        nav, sbar = t.widget(SYSBAR_BOTTOM_VT, 0, 450, 320, 30, t.wm), t.widget(SYSBAR_VT, 0, 0, 320, 30, t.wm)
        t.kids(t.wm, old + [nav, sbar])
        t.props[(nav, 'type')], t.props[(sbar, 'type')] = t.cstr('system_bar_bottom'), t.cstr('system_bar')   # (widget_get_type asks widget_get_prop_str for "type")
        return nav, sbar
    def bar_model(tones, seed):
        top = D.field(tones, seed, D.DP_W, D.DP_ART_H)[0]
        r, g, b = (sum(px[i] for px in top) // D.DP_W for i in range(3))
        while 2126 * r * r + 7152 * g * g + 722 * b * b > O['NP_BAR_LUM_MAX']: r, g, b = r * 15 >> 4, g * 15 >> 4, b * 15 >> 4
        return 0xff000000 | r | g << 8 | b << 16
    t = PG(); t.world(uniq, 12); t.boot(); nav, sbar = with_bar(t)
    t.card_tap()
    bars = lambda: [s[2] for s in t.styled if s[0] == sbar]
    want = bar_model(t.tones, t.aseed)
    expect(bars() == [want] and want != O['NP_BAR_STOCK'] and nav not in [s[0] for s in t.styled],
           f'the page opens with the status bar in the art\'s top-row colour, darkened for its white glyphs ({[hex(v) for v in bars()]}, model {want:#x}); the navbar is not styled')
    t.fire_page_window(EVT_BG)
    expect(bars()[-1] == O['NP_BAR_STOCK'] and len(bars()) == 2, 'covered by another page: the stock black is back')
    t.fire_page_window(EVT_BG)
    expect(len(bars()) == 2, '... once (a second background event owes nothing)')
    t.fire_page_window(EVT_FG)
    expect(bars()[-1] == want and len(bars()) == 3, 'in front again: the art\'s colour again')
    t.fire_page_window(EVT_DESTROY)
    expect(bars()[-1] == O['NP_BAR_STOCK'] and len(bars()) == 4, 'closed: the stock black is back')
    t = PG(); t.world(uniq, 12); t.boot(); nav, sbar = with_bar(t)
    t.card_tap()
    t.call(PSYMS['pod_bar_tint'], a0=0x5a5a0000, a1=0x123456, count=200000)   # another page (Now Playing, opened by Play) takes the bar over
    n_before = len(bars())
    t.fire_page_window(EVT_BG); t.fire_page_window(EVT_DESTROY)
    expect(len(bars()) == n_before, 'a page that lost the bar to the next one (Now Playing) never puts the black back over its colour')

    m = opened(25)
    placeholder =[b for b, v in m.bitmaps.items() if (v[1], v[2]) == (52, 52)]
    expect(len(placeholder) == 1, 'the ring\'s placeholder disc, 52 px, is made at open')
    ph = placeholder[0]
    blits, texts, styles, fills = m.paint(SCR)
    rows_b = covers_of(blits)
    expect(len(rows_b) == 6 and all(b[0] == ph for b in rows_b), 'before the loader runs every visible row shows the one placeholder')
    m.pscroll(0)
    got = []
    for _ in range(8):
        cs = tick(m)
        got += [c[1] for c in cs if c[0] == 'widget_load_image']
        if 'timer_add' not in [c[0] for c in cs]: break
    want_keys = [key_of(m.songs[i]['artist'], m.songs[i]['album']) for i in range(4)]
    expect(got == ['file://' + art_file(k) for k in want_keys], f'at the top the loader decodes the rows in view and the two ahead (0, 1, 2, 3), one a tick, each from its album\'s Cover Flow cache file ({got})')
    expect('timer_add' not in [c[0] for c in cs], 'it stops when nothing is left to load')
    expect(len([b for b, v in m.bitmaps.items() if (v[1], v[2]) == (52, 52)]) == 5, 'the placeholder and the four covers are 52 px bitmaps (11 KB each)')
    # moving: nothing is decoded
    m.pscroll(SCR); m.fire_page('dp_scrollview', EVT_SCROLL)
    m.u.mem_write(m.psv + O['SC_PRESSED'], bytes([1, 1]))     # a finger is dragging the scroll view
    cs = tick(m)
    expect(not [c for c in cs if c[0] in ('widget_load_image', 'bitmap_create_ex')] and [c for c in cs if c[0] == 'timer_add'], 'a finger dragging the list: the loader decodes nothing and looks again next tick')
    m.u.mem_write(m.psv + O['SC_PRESSED'], bytes([1, 0]))     # pressed, not dragging: a tap, a hold
    cs = tick(m)
    expect([c for c in cs if c[0] == 'widget_load_image'], 'a press that has not started to drag does not defer')
    an = m.alloc(0x80); m.u.mem_write(an, bytes(0x80)); m.setword(an + O['SC_AN_STATE'], O['SC_AN_RUNNING']); m.setword(an + O['SC_AN_WIDGET'], m.psv)
    m.u.mem_write(m.psv + O['SC_PRESSED'], bytes([0, 0])); m.setword(m.psv + O['SC_WA'], an)
    cs = tick(m)
    expect(not [c for c in cs if c[0] in ('widget_load_image', 'bitmap_create_ex')] and [c for c in cs if c[0] == 'timer_add'], 'the stock scroll animator (the fling) running: nothing is decoded either')
    m.setword(m.psv + O['SC_WA'], 0)
    n_done = 0
    for _ in range(12):
        cs = tick(m); n_done += len([c for c in cs if c[0] == 'widget_load_image'])
        if 'timer_add' not in [c[0] for c in cs]: break
    expect(n_done >= 3, f'back to rest it decodes the rows in view (and the two ahead): {n_done} more covers')
    blits, texts, styles, fills = m.paint(SCR)
    rows_b = covers_of(blits)
    expect(len(rows_b) == 6 and len({b[0] for b in rows_b}) == 6 and ph not in {b[0] for b in rows_b}, 'the visible rows now show their own covers')
    # the ring: scrolling through the whole list never holds more than GRID_TILES covers
    for off in range(0, 2031 - VIEW_H, 160):
        m.pscroll(off); m.fire_page('dp_scrollview', EVT_SCROLL)
        for _ in range(12):
            cs = tick(m)
            if 'timer_add' not in [c[0] for c in cs]: break
    live = [b for b, v in m.bitmaps.items() if (v[1], v[2]) == (52, 52)]
    expect(len(live) <= O['GRID_TILES'] + 1, f'the cover ring holds at most {O["GRID_TILES"]} covers plus the placeholder over the whole list ({len(live)})')
    # a missing cache file shows the placeholder, an empty one too
    m = opened(12, cover_rows=[0, 2])
    got = []
    for _ in range(6):
        cs = tick(m); got += [c[1] for c in cs if c[0] == 'widget_load_image']
        if 'timer_add' not in [c[0] for c in cs]: break
    expect(got == ['file://' + art_file(key_of(m.songs[i]['artist'], m.songs[i]['album'])) for i in (0, 2)], f'an album with no cache file is not decoded, its row waits with the placeholder ({got})')
    blits, *_ = m.paint(300)
    ph = [b for b, v in m.bitmaps.items() if (v[1], v[2]) == (52, 52)][0]
    expect(len(covers_of(blits)) >= 3, 'rows without a cover still draw their placeholder disc')
    # scroll events refused: the loader keeps polling for as long as the page is up
    m = opened(12, mk=None)
    m2 = PG(); m2.world(uniq, 12); m2.boot(); m2.widget_on_fail = frozenset({EVT_SCROLL}); calls = m2.card_tap()
    for _ in range(12): tick(m2)
    cs = tick(m2)
    expect([c for c in cs if c[0] == 'timer_add'], 'if the scroll events cannot be registered the loader polls for as long as the page is up')

    # ===== 6. touch: the songs, Play, Shuffle
    def played_paths(t): return [t.read_cstr(t.word(r + O['REC_PATH'])) for r in t.played[0]] if t.played else None
    m = opened(12, bmp=False)
    playlist = [s['path'] for s in m.songs[:12]]
    m.pscroll(SCR)
    x, y = m.row_xy(2)
    m.pscroll(SCR)
    shown0 = m.word(pod.DATA['PDEQ_SHOWLIST'][0])
    calls = m.ptap(x, y)
    expect(m.fired[:2] == [('view_dm', EVT_DOWN), ('view_dm', EVT_UP)] or ('view_dm', EVT_UP) in m.fired, 'the content view gets the pointer down and up through demo\'s own dispatch')
    expect(m.played and played_paths(m) == playlist and m.played[1] == 2, f'a tap on song 2 plays the mix from it: the queue is the playlist\'s 12 songs in order, index 2 ({m.played and m.played[1]})')
    nav = [c for c in calls if c[0] == 'navigator_to_with_context']
    expect(nav and nav[-1][1] == 'playing_page' and ('loadSongList', m.songs[2]['name'], 0, 0xf001) in calls and m.word(pod.DATA['G_CLASS_TYPE'][0]) == 0xf001
           and not [c for c in calls if c[0] == 'mclSetPlayMode'], 'it starts as the Shuffle page does (the library 0xf001, loadSongList with that song and the class 0xf001, then Now Playing) and leaves the play mode alone')
    ld = [c[1] for c in calls if c[0] == 'loadLocalClassList']
    dq = [c for c in calls if c[0] == 'toolsQueryDbTable']
    expect(not ld and len(dq) == 1 and 'allmusic_page' not in [c[1] for c in nav], f'the queue is made from one query of the mix\'s rows: no library read (loadLocalClassList / getAllMusic) ({ld}, {len(dq)})')
    expect(m.word(pod.DATA['PDEQ_SHOWLIST'][0]) == shown0 and m.deques[m.word(pod.DATA['PDEQ_TOOLS_TMP'][0])] == [], 'the shown list pointer is put back and the query\'s deque is cleared')
    expect(not written(m, [calls]), 'playing writes nothing')
    # the same file name on every row (a duplicate name resolves to the first copy in stock): the drawn row wins
    songs_dup = [dict(s, name='01.flac') for s in uniq]
    md = PG(); md.world(songs_dup, 12); md.boot(); md.bitmap_ok = False; md.card_tap(); md.pscroll(SCR)
    x, y = md.row_xy(5); md.ptap(x, y)
    expect(md.played and md.played[1] == 5, f'songs that share a file name: the row that was tapped plays, not the first copy ({md.played and md.played[1]})')
    # pressed row: the fill while the finger is down, gone after
    m = opened(12, bmp=False); m.pscroll(SCR)
    x, y = m.row_xy(3)
    m.pgesture([('d', x, y, 0)])
    blits, texts, styles, fills = m.paint(SCR)
    press = [f for f in fills if f[0] == O['DP_PRESS']]
    expect([(f[1], f[2], f[3], f[4]) for f in press] == [(0, ROWS_Y + 3 * ROW - SCR, 320, 63)], f'the pressed row is filled 20 % white over its 63 top lines ({press})')
    m.pgesture([('u', x, y, 60)])
    blits, texts, styles, fills = m.paint(SCR)
    expect(not [f for f in fills if f[0] == O['DP_PRESS']] and m.played, 'released: the fill is gone and the song plays')
    # a drag, an abort, a release 10 px away, another row
    for steps, why in (([('d', x, y, 0), ('m', x, y - 30, 16), ('u', x, y - 30, 16)], 'a drag that moves the finger 30 px'), ([('d', x, y, 0), ('a', x, y)], 'an aborted press (the list took the drag)'),
                       ([('d', x, y, 0), ('u', x + 10, y, 16)], 'a release 10 px away'), ([('d', x, y, 0), ('u', x, y + 64, 16)], 'a release on another row'), ([('d', x, y, 0), ('u', x, y + 12, 16)], 'a release 12 px away')):
        t = opened(12, bmp=False); t.pscroll(SCR)
        t.pgesture(steps)
        blits, texts, styles, fills = t.paint(None)
        expect(t.played is None and not [f for f in fills if f[0] == O['DP_PRESS']], f'{why} plays nothing and leaves no pressed fill')
    t = opened(12, bmp=False); t.pscroll(SCR); t.pgesture([('d', x, y, 0), ('u', x + 9, y + 9, 16)])
    expect(t.played and t.played[1] == 3, 'a release 9 px away is still a tap')
    # taps that are not on a song
    t = opened(12, bmp=False); t.pscroll(0)
    for px, py, why in ((160, 205, 'the title'), (160, 100, 'the art'), (300, 285, 'beside the buttons'), (160, ROWS_Y - 5, 'the description')):
        t.ptap(px, py)
        expect(t.played is None, f'a tap on {why} plays nothing')
    t.pscroll(t.s32(t.pview + 0xc) - VIEW_H)
    t.ptap(100, VIEW_H - 8)
    expect(t.played is None, 'a tap in the air under the last row plays nothing')
    t.pscroll(0)
    # Play and Shuffle
    for before, after in ((0, 0), (1, 0), (2, 0), (3, 3)):
        t = opened(12, bmp=False); t.mode = before
        t.fire_page('btn_dp_play', EVT_CLICK)
        expect(t.played and played_paths(t) == playlist and t.played[1] == 0 and t.mode == after and (('mclSetPlayMode', after) in t.calls) == (before != after),
               f'Play plays the mix in order from its first song: mode {before} -> {after} (Shuffle and Repeat one become List play, the others are kept)')
    t = opened(12, bmp=False); t.mode = O['MODE_SHUFFLE']; t.pscroll(SCR)
    x, y = t.row_xy(2); t.pscroll(SCR); t.ptap(x, y)
    expect(t.played and t.played[1] == 2 and t.mode == O['MODE_SHUFFLE'] and not [c for c in t.calls if c[0] == 'mclSetPlayMode'], 'a song tap keeps the play mode (Shuffle stays Shuffle)')
    t = opened(12, bmp=False); t.seed = 12345
    t.fire_page('btn_dp_shuffle', EVT_CLICK)
    rng = (12345 ^ (t.clock * 2654435761 & 0xffffffff)) | 1
    rng ^= rng << 13 & 0xffffffff; rng ^= rng >> 17; rng ^= rng << 5 & 0xffffffff
    expect(t.played and played_paths(t) == playlist and t.played[1] == rng % 12 and ('mclSetPlayMode', O['MODE_SHUFFLE']) in t.calls and t.mode == O['MODE_SHUFFLE'],
           f'Shuffle sets the stock Shuffle mode and starts from a random song of the playlist (index {t.played and t.played[1]}, expected {rng % 12}); the queue is the whole mix')
    # failures and the mix against the library
    t = opened(12, bmp=False); t.present.discard(t.songs[0]['path']); t.fire_page('btn_dp_play', EVT_CLICK)
    expect(t.played and played_paths(t) == playlist[1:] and t.played[1] == 0, 'the first song is not on the card: it is left out of the queue, Play starts at the next')
    t = opened(12, bmp=False); [t.present.discard(s['path']) for s in t.songs]; t.fire_page('btn_dp_play', EVT_CLICK)
    expect(t.played is None and [c for c in t.calls if c[0] == 'toast'], 'no song of the mix is on the card: the message, nothing plays')
    t = opened(12, bmp=False); t.pscroll(SCR); t.present.discard(t.songs[2]['path']); x, y = t.row_xy(2); t.ptap(x, y)
    expect(t.played is None and [c for c in t.calls_all if c[0] == 'toast'], 'a tapped song that is missing on the card: the message, the page stays')
    t = opened(12, bmp=False); t.class_lists[0xf001] = []; t.fire_page('btn_dp_play', EVT_CLICK)
    expect(t.played is None and [c for c in t.calls if c[0] == 'toast'], 'the library has none of the mix\'s songs any more (rescanned): the message, nothing plays')
    t = opened(12, bmp=False); t.pscroll(SCR); x, y = t.row_xy(2)
    t.class_lists[0xf001] = list(reversed(t.class_lists[0xf001]))        # the library comes back in another order while the page is open
    t.ptap(x, y)
    expect(t.played and played_paths(t) == playlist and t.played[1] == 2, 'the library in another order: the song that was drawn plays, from its place in the mix (the mix\'s order is the file\'s)')
    t = opened(12, bmp=False); t.pscroll(SCR); x, y = t.row_xy(2)
    t.class_lists[0xf001] = [r for r in t.class_lists[0xf001] if t.read_cstr(t.word(r + O['REC_PATH'])) != t.songs[2]['path']]
    t.ptap(x, y)
    expect(t.played is None and [c for c in t.calls_all if c[0] == 'toast'], 'a song that left the library: the message, nothing plays')
    t = opened(12, bmp=False); t.pscroll(SCR); x, y = t.row_xy(2); t.present.discard(t.songs[4]['path'])
    t.ptap(x, y)
    expect(t.played and played_paths(t) == [p for p in playlist if p != t.songs[4]['path']] and t.played[1] == 2, 'another song of the mix is gone from the card: it is left out of the queue, the tapped one plays')
    # the mix is in the file's order, not the library's, and songs of the library that are not in the mix are not in the queue
    t = opened(12, bmp=False, order=[7, 2, 9, 0, 5, 11, 3, 8, 1, 10, 4, 6])
    t.fire_page('btn_dp_play', EVT_CLICK)
    expect(t.played and played_paths(t) == [s['path'] for s in t.songs] and played_paths(t) != sorted(played_paths(t)) and len(t.class_lists[0xf001]) > 12, 'the queue is the mix in the mix\'s order, though the library is larger and ordered differently')
    # hit tests with demo's own widget_find_target
    t = opened(12, bmp=False)
    expect(t.ptarget(30, 30)[-1] == 'btn_return' and t.ptarget(160, 285)[-1] == 'btn_dp_play' and t.ptarget(64, 285)[-1] == 'btn_dp_shuffle' and t.ptarget(270, 285)[-1] == 'btn_dp_add' and t.ptarget(240, 285)[-1] == 'view_dm' and t.ptarget(80, 285)[-1] == 'view_dm'
           and t.ptarget(300, 30)[-1] == 'view_dm' and t.ptarget(160, 100)[-1] == 'view_dm' and t.ptarget(160, 440)[-1] == 'view_dm',
           f'hit tests: the back disc, the Shuffle disc, the pill and the Add disc take their touches (the pill glyph is insensitive: the pill takes it), the top right and the art are the content view ({[t.ptarget(x_, y_)[-1] for x_, y_ in ((30, 30), (160, 285), (64, 285), (270, 285), (300, 30))]})')
    t.pscroll(200)
    expect(t.ptarget(30, 30)[-1] == 'btn_return' and t.ptarget(160, 285 - 200)[-1] == 'btn_dp_play' and t.ptarget(160, 285)[-1] != 'btn_dp_play', 'the back disc stays at the top while the list scrolls; the buttons scroll with it')
    expect(O['DP_BACK_BTN'] >= 44, 'the back disc\'s touch square is 44 px')

    # ===== 6b. the Add disc: the mix saved as a new stock playlist (dp_save)
    import datetime
    iso_day = lambda d: (datetime.date(1970, 1, 1) + datetime.timedelta(days=d)).isoformat()
    toasts = lambda t: [c[1] for c in t.calls if c[0] == 'toast']
    G, CI, NT = pod.DATA['G_CLASS_TYPE'][0], pod.DATA['CLASSINFO'][0], pod.DATA['NAV_TITLE'][0]

    def saver(n=12, **kw):
        t = opened(n, bmp=False, **kw)
        t.setword(G, 0xf001); t.setword(CI, 0xff13); t.setword(CI + 4, 9); t.u.mem_write(NT, b'My Title\0')
        t.clobber = True
        t.lib_before = [(r, t.s32(r + O['REC_ID']), t.s32(r + O['REC_DISC'])) for r in t.class_lists[0xf001]]
        return t

    def globals_back(t): return (t.word(G), t.word(CI), t.word(CI + 4), t.read_cstr(NT)) == (0xf001, 0xff13, 9, 'My Title')

    t = saver()
    base = f'Daily Mix {iso_day(t.day)}'
    paths = [s['path'] for s in t.songs]
    t.fire_page('btn_dp_add', EVT_CLICK)
    expect(t.pl_created == [(base, 5)] and [c for c in t.calls if c[0] == 'createPlayListItem'] == [('createPlayListItem', base, len(t.playlists))],
           f'a tap creates ONE stock playlist named "<Daily Mix> <the mix\'s day as YYYY-MM-DD>" from the stock list ({t.pl_created})')
    expect([c[1] for c in t.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_PLAYLISTS']], 'the only stock query is the playlist list (the page already holds the mix\'s songs)')
    expect([(r[0], r[1], r[2]) for r in t.pl_rows] == [(101 + i, 5, p) for i, p in enumerate(paths)], f'the 12 songs are added in the mix\'s order, ids from max(100, max id) + 1 up, with the new playlist\'s id ({t.pl_rows[:2]})')
    expect(toasts(t) == ['msg_addplaylistsuccess'] and globals_back(t), f'the stock success message shows and the browsing class, classinfo and the title are put back after the stock calls changed them ({toasts(t)})')
    expect(('checkPlayListExist', paths[0], 5) in t.calls and t.calls.index(('checkPlayListExist', paths[0], 5)) < t.calls.index(('addPlayList',) + t.pl_rows[0]),
           'each song is checked with checkPlayListExist before addPlayList, as the stock batch add does')
    expect([(r, i, d) for r, i, d in t.lib_before] == [(r, t.s32(r + O['REC_ID']), t.s32(r + O['REC_DISC'])) for r, _, _ in t.lib_before], 'the stock library records are not written to (the page adds copies)')
    expect(t.fs[MIX] == t.mixfile and not written(t, [t.calls]), 'the mix file is untouched and nothing is written to a file (the playlist is the stock database\'s)')
    expect(not [c for c in t.calls if c[0] in ('navigator_to_with_context',) and c[1] != 'dialog/msginfo_dialog'] and t.played is None, 'no picker, no dialog but the message; nothing plays')
    # another day of the mix: its date; the name in 13 languages (the translated "Daily Mix")
    for d in (1, 11016, 19783):
        t2 = opened(12, bmp=False, day=d); t2.fire_page('btn_dp_add', EVT_CLICK)
        expect(t2.pl_created == [(f'Daily Mix {iso_day(d)}', 5)], f'the name carries the mix\'s own day ({d}: {t2.pl_created})')
    bad = []
    for loc in D.LOCALES:
        t2 = opened(12, bmp=False); t2.set_language(loc); t2.fire_page('btn_dp_add', EVT_CLICK)
        want_ = t2.tr('Daily Mix') + ' ' + iso_day(t2.day)
        if t2.pl_created != [(want_, 5)] or len(want_) >= 96 or toasts(t2) != ['msg_addplaylistsuccess']: bad.append((loc, t2.pl_created, want_))
    expect(not bad, f'in 13 languages the playlist is "<translated Daily Mix> <date>" and short ({bad[:1]})')
    # saved once: the disc is a check (the page looks the name up in the stock playlist list at its opening and each time it comes back to the front), a tap says so
    icons = lambda t: [t.props.get((t.page['btn_dp_add'], f'style:{s}:icon')) for s in ('normal', 'over', 'pressed')]
    PLUS, CHECK = ['dp_add', 'dp_add', 'dp_add_down'], ['dp_added', 'dp_added', 'dp_added_down']
    expect(icons(t) == CHECK, f'after the tap the disc is a check ({icons(t)})')
    t.fire_page('btn_dp_add', EVT_CLICK)
    expect(t.pl_created == [(base, 5)] and not [c for c in t.calls if c[0] in ('createPlayListItem', 'loadLocalClassList', 'addPlayList')] and toasts(t) == ['msg_playlistexist'],
           f'a second tap makes no second playlist and reads nothing: the stock "Playlist Already Exists" ({toasts(t)})')

    def with_lists(*names):
        t2 = PG(); t2.world(uniq, 12); t2.boot(); t2.bitmap_ok = False
        t2.playlists = [t2.record(album='', artist='', title=nm.replace('{day}', iso_day(t2.day)), rid=7 + k) for k, nm in enumerate(names)]
        t2.card_tap()
        return t2
    t2 = saver()
    expect(icons(t2) == PLUS, f'no playlist of the mix: a plus ({icons(t2)})')
    t2 = with_lists('Road Trip', 'Daily Mix {day}')
    expect(icons(t2) == CHECK, f'the mix\'s playlist is in the stock list when the page opens: a check ({icons(t2)})')
    t2.fire_page('btn_dp_add', EVT_CLICK)
    expect(t2.pl_created == [] and not [c for c in t2.calls if c[0] in ('createPlayListItem', 'addPlayList')] and toasts(t2) == ['msg_playlistexist'], 'a tap on the check makes nothing and says the playlist exists')
    for other in ('Daily Mix {day} (2)', 'Daily Mix 1970-01-02', 'daily mix {day}', 'Daily Mix'):
        t2 = with_lists(other)
        expect(icons(t2) == PLUS, f'"{other}" is not the mix\'s playlist: a plus ({icons(t2)})')
    t2 = with_lists('Daily Mix {day}'); t2.playlists = []
    t2.calls = []; t2.fire_page_window(EVT_FG)
    expect(icons(t2) == CHECK and not [c for c in t2.calls if c[0] == 'loadLocalClassList'], 'to the front without having been behind (the opening): no second query')
    t2.fire_page_window(EVT_BG); t2.fire_page_window(EVT_FG)
    expect(icons(t2) == PLUS, f'back from another page where the playlist was deleted: a plus again ({icons(t2)})')
    t2.fire_page('btn_dp_add', EVT_CLICK)
    expect(t2.pl_created == [(base, 5)] and icons(t2) == CHECK, 'and a tap saves it again')
    t2 = saver(); t2.pl_names = {base}; t2.fire_page('btn_dp_add', EVT_CLICK)
    expect(t2.pl_created == [] and not t2.pl_rows and toasts(t2) == ['msg_playlistexist'] and icons(t2) == CHECK and globals_back(t2),
           'the name taken under a plus (-2): no playlist, the stock "Playlist Already Exists", the disc a check, nothing left changed')
    t2 = saver(); t2.create_ret = -1; t2.fire_page('btn_dp_add', EVT_CLICK)
    expect(t2.pl_created == [] and not t2.pl_rows and [c for c in t2.calls if c[0] == 'createPlayListItem'] == [('createPlayListItem', base, len(t2.playlists))] and toasts(t2) == ['msg_playlistfull'] and globals_back(t2)
           and icons(t2) == PLUS, 'the playlist table is full (-1): the stock "Playlist Is Full", nothing added, state put back, still a plus')
    # songs: files missing on the card are left out (the order is kept), songs already in the playlist are skipped, the ids follow the table
    t2 = saver(); [t2.present.discard(t2.songs[i]['path']) for i in (1, 4)]; t2.fire_page('btn_dp_add', EVT_CLICK)
    left = [s['path'] for i, s in enumerate(t2.songs) if i not in (1, 4)]
    expect([r[2] for r in t2.pl_rows] == left and [r[0] for r in t2.pl_rows] == list(range(101, 111)) and toasts(t2) == ['msg_addplaylistsuccess'], f'songs whose file is gone are skipped and the rest keep the mix\'s order and consecutive ids ({len(t2.pl_rows)} added)')
    t2 = saver(); [t2.present.discard(s['path']) for s in t2.songs]; t2.fire_page('btn_dp_add', EVT_CLICK)
    expect(not [c for c in t2.calls if c[0] in ('createPlayListItem', 'loadLocalClassList', 'addPlayList')] and toasts(t2) == ['Storage unavailable'] and globals_back(t2), 'no file of the mix is on the card: the usual message and no (empty) playlist is made')
    t2 = saver(); t2.pl_rows = [(250, 9, '/mnt/mmc/other.flac', 'o'), (160, 5, paths[0], 'x')]; t2.fire_page('btn_dp_add', EVT_CLICK)
    expect([r[2] for r in t2.pl_rows[2:]] == paths[1:] and [r[0] for r in t2.pl_rows[2:]] == list(range(251, 262)) and toasts(t2) == ['msg_addplaylistsuccess'],
           f'a song already in the new playlist (checkPlayListExist) is not added twice; ids continue after the table\'s largest ({[r[0] for r in t2.pl_rows[2:4]]})')
    # an asset without the disc is not ours: the window goes again
    t2 = PG(); t2.world(uniq, 12); t2.boot(); t2.widgets.pop('btn_dp_add'); t2.page.pop('btn_dp_add')
    calls = t2.card_tap()
    expect(('navigator_back',) in calls and not [c for c in calls if c[0] == 'navigator_to_with_context'], 'an asset without the Add disc is not ours: the window goes again, nothing opens')

    # ===== 7. the texts: 13 languages, the Updated line
    mt = opened(12, bmp=False)
    wf = lambda s: sum(16 if ord(c) >= 0x2e80 or c == '…' else 8 for c in s)
    bad = []
    for loc in D.LOCALES:
        mt.set_language(loc)
        reopen(mt)
        blits, texts, styles, fills = mt.paint(0)
        tr = lambda k: pod_i18n.TEXT[k][loc]
        got = [(t_, r) for (t_, r), s in zip(texts, styles) if s in ('label_dp_title', 'label_dp_sub', 'label_dp_upd')]
        want_ = [(D.ellipsize(wf, tr('Daily Mix'), 288), (16, 193, 288, 24)), (D.ellipsize(wf, tr('Made for You'), 288), (16, 218, 288, 17)), (D.ellipsize(wf, tr('Updated today'), 288), (16, 239, 288, 14))]
        text_ = tr('Songs you love and some to rediscover, made fresh every day.')
        lines = D.wrap(wf, text_, 288, 16) or [text_]
        if len(lines) > 2: lines = [lines[0], D.ellipsize(wf, text_[len(lines[0]):].lstrip(), 288)]
        dgot = [t_ for (t_, r), s in zip(texts, styles) if s == 'label_dp_desc']
        tw = wf(tr('Play')); tw = min(tw, 148 - 2 * 24)
        pgot = [(t_, r) for (t_, r), s in zip(texts, styles) if s == 'label_dp_play']
        gx = 86 + (148 - (24 + tw)) // 2
        pw_ = [(D.ellipsize(wf, tr('Play'), tw + 2), (gx + 24, 265, tw + 2, 40))]
        mv = (mt.s32(mt.page['img_dp_glyph']), mt.s32(mt.page['img_dp_glyph'] + 4))   # (widget_move runs demo's own code: read the struct)
        if got != want_ or dgot != lines or pgot != pw_ or mv != (gx, 263 + 14): bad.append((loc, got, want_, dgot, lines, pgot, pw_, mv))
    expect(not bad, f'in 13 languages the page draws the model\'s lines: title, subtitle, Updated, the description wrapped in at most two lines, the pill\'s text centred with its glyph ({bad[:1]})')
    mt.set_language(None); reopen(mt)
    over = []
    for loc in D.LOCALES:
        tr = lambda k: pod_i18n.TEXT[k][loc]
        for key, px, room in (('Daily Mix', 24, 288), ('Made for You', 17, 288), ('Updated today', 14, 288), ('Updated yesterday', 14, 288), ('Updated %s', 14, 288)):
            w_ = width(tr(key).replace('%s', '2026-10-26'), px)
            if w_ > room: over.append((loc, key, w_))
        if width(tr('Play'), 18) > D.DP_PLAY_W - 2 * (D.DP_PILL_GLYPH + D.DP_PILL_GAP): over.append((loc, 'Play'))
        lines = D.wrap(lambda s: width(s, 15), tr('Songs you love and some to rediscover, made fresh every day.'), 288, 2)
        if lines is None: over.append((loc, 'description', 'more than two lines'))
    expect(not over, f'in the shipped font every line fits its 288 px (the pill\'s text its room), the description takes two lines at most, in all 13 languages ({over})')
    expect(sorted(pod_i18n.DPAGE_KEYS) == sorted(k for k in pod_i18n.TEXT if k in ('Updated today', 'Updated yesterday', 'Updated %s', 'Play', 'Songs you love and some to rediscover, made fresh every day.')) and all(set(pod_i18n.TEXT[k]) == set(D.LOCALES) for k in pod_i18n.DPAGE_KEYS)
           and all(pod_i18n.TEXT['Updated %s'][l].count('%s') == 1 for l in D.LOCALES), 'five new keys in all 13 languages, the date template with one %s')
    # the Updated line
    today = m.wall // 86400
    iso = lambda d: (datetime.date(1970, 1, 1) + datetime.timedelta(days=d)).isoformat()
    for delta, want_ in ((0, 'Updated today'), (1, 'Updated yesterday'), (2, f'Updated {iso(today - 2)}'), (40, f'Updated {iso(today - 40)}'), (400, f'Updated {iso(today - 400)}'), (-3, 'Updated today')):
        t = PG(); t.world(uniq, 12, day=today - delta); t.boot(); t.bitmap_ok = False; t.card_tap()
        blits, texts, styles, fills = t.paint(0)
        expect([t_ for (t_, r), s in zip(texts, styles) if s == 'label_dp_upd'] == [want_], f'the mix made {delta} days ago reads {want_!r}')
    t = PG(); t.world(uniq, 12); t.wall = 0; t.boot(); t.bitmap_ok = False; t.card_tap()
    blits, texts, styles, fills = t.paint(0)
    expect(not t.up() or [t_ for (t_, r), s in zip(texts, styles) if s == 'label_dp_upd'] in ([], ['Updated today']), 'a clock that is not set says today (or the card is not shown at all)')
    days = [0, 1, 59, 60, 365, 11016, 11017, 18321, 19000, 20000, 20833, 21000, 25000, 30000, 36524, 47482]
    expect(all(D.civil(d) == (lambda dt: (dt.year, dt.month, dt.day))(datetime.date(1970, 1, 1) + datetime.timedelta(days=d)) for d in range(0, 40000, 7)) and all(D.civil(d)[0] > 0 for d in days),
           'the civil date algorithm of the model equals the calendar')
    for d in (1, 59, 60, 11016, 11017, 19782, 19783, 20000):   # 1970-01-02, 03-01, 03-02, 2000-02-29, 03-01, 2024-02-29, 03-01, 2024-10-04
        t = PG(); t.world(uniq, 12, day=d); t.boot(); t.bitmap_ok = False; t.card_tap()
        blits, texts, styles, fills = t.paint(0)
        expect([t_ for (t_, r), s in zip(texts, styles) if s == 'label_dp_upd'] == [f'Updated {iso(d)}'], f'day {d} is written {iso(d)} by the payload\'s civil date')

    # ===== 8. falling back, freeing
    t = PG(); t.world(uniq, 12); t.boot(); t.widgets.pop('label_dp_artist'); t.page.pop('label_dp_artist')
    calls = t.card_tap()
    expect(('navigator_back',) in calls and not [c for c in calls if c[0] == 'navigator_to_with_context'], 'an asset that is not ours (a style label missing): the window goes again, nothing else opens')
    t.widgets['label_dp_artist'] = t.page['label_dp_artist'] = t.alloc(0x80)
    t.calls_all = []; t.card_tap()
    expect([c for c in t.calls_all if c[0] == 'window_open'], 'the failed attempt left nothing behind: a later tap tries the page again')
    t = PG(); t.world(uniq, 12); t.boot(); t.window = 0
    calls = t.card_tap()
    expect(not [c for c in calls if c[0] in ('navigator_to_with_context', 'navigator_back')], 'a window that does not open: nothing happens')
    t = PG(); t.world(uniq, 12); t.boot(); t.calloc_fail = True
    calls = t.card_tap()
    expect(not [c for c in calls if c[0] in ('window_open', 'navigator_to_with_context')], 'no memory for the songs: no page, nothing opens')
    t = PG(); t.world(uniq, 12); t.boot(); t.bitmap_ok = False
    calls = t.card_tap()
    blits, texts, styles, fills = t.paint(0)
    expect([c for c in calls if c[0] == 'window_open'] and not [c for c in calls if c[0] == 'navigator_to_with_context'] and len(texts) >= 6 and not blits and sty_of(t, 'dp_listview'),
           'no memory for bitmaps: the page still opens on its tint with all its text, no art, no covers')
    t = PG(); t.world(uniq, 12); t.boot(); t.class_lists[0xf001] = [t.record(album='x', artist='y', path='/mnt/mmc/other.flac', title='z', name='other.flac')]; calls = t.card_tap()
    expect([c for c in calls if c[0] == 'toast'] and not [c for c in calls if c[0] == 'window_open'], 'none of the mix\'s songs is in the library: no page, the usual message')
    t = PG(); t.world(uniq, 12); t.boot(); [t.present.discard(s['path']) for s in t.songs]; calls = t.card_tap()
    expect([c for c in calls if c[0] == 'toast'] and not [c for c in calls if c[0] == 'window_open'], 'the card is out: no page, the usual message')
    # a mix whose songs are only partly in the library: the page lists those that are, in the mix's order
    t = PG(); t.world(uniq, 12); t.boot(); t.present.discard(t.songs[1]['path']); t.class_lists[0xf001] = [r for r in t.class_lists[0xf001] if t.read_cstr(t.word(r + O['REC_PATH'])) != t.songs[3]['path']]
    t.card_tap(); blits, texts, styles, fills = t.paint(SCR)
    rt_ = [t_ for (t_, r), s in zip(texts, styles) if s == 'label_dp_row']
    expect(rt_[:5] == [t.songs[i]['title'] for i in (0, 2, 4, 5, 6)], f'songs missing from the library or the card are skipped, the rest keep the mix\'s order ({rt_[:5]})')
    # (PERF only) the cost of opening: the library pass on a small library and on one at the cap (DM_LIB_MAX songs, the mix spread over it); no file is touched
    if PERF:
        def open_cost(lib, order):
            t = PG(count=True); t.world(lib, len(order), order=order); t.boot(); t.bitmap_ok = False
            t.card_tap()
            return t.icount, t
        c_small, _ = open_cost(uniq, list(range(12)))
        big = [dict(path=f'/mnt/mmc/B/{i // 12}/{i}.flac', artist=f'Band {i // 60}', album=f'Disc {i // 12}', title=f'Track number {i}', name=f'{i}.flac') for i in range(O['DM_LIB_MAX'])]
        c_big, tb = open_cost(big, [i * 1000 + 11 for i in range(12)])
        expect(c_big < 15_000_000 and not written(tb, [tb.calls_all]), f'opening the page on {O["DM_LIB_MAX"]} songs: {c_big} instructions without the art ({c_small} on {len(uniq)} songs), under 15 million, nothing written')
        print(f'  (page open without the art: {c_small} instructions on {len(uniq)} songs, {c_big} on {O["DM_LIB_MAX"]})')
    # freeing
    t = opened(25)
    for _ in range(12): tick(t)
    live_before = len(t.bitmaps)
    t.fire_page_window(EVT_DESTROY)
    destroyed = [c for c in t.calls if c[0] == 'bitmap_destroy']
    expect(len(set(t.bitmaps) - set(before_bmps)) == 0 and len(destroyed) >= live_before - len(before_bmps), f'closing destroys every bitmap the page made: the art, the ring ({len(destroyed)} of {live_before - len(before_bmps)})')
    expect(len([c for c in t.calls if c[0] == 'free']) >= 25 * 4 and [c for c in t.calls if c[0] == 'timer_remove'] in ([], [('timer_remove', 0x777)]), 'closing frees the 25 song copies (their strings) and removes the loader timer')
    calls = t.card_tap()
    expect([c for c in calls if c[0] == 'window_open'] and t.paint(0)[1], 'a second open works')
    t.call(PSYMS['dp_on_destroy'], a0=0x1234, a1=0, count=1000000)
    expect(t.paint(0)[1], 'the destroy event of another window leaves the open page alone')
    expect(opened(12) is not None, 'the page opens again on a fresh machine')


def sty_of(t, name): return [v for (w, p, v) in t.styled if w == t.page[name] and p == 'normal:bg_color']

"""The menu lists under the stock window manager (patch/menu.c): demo's own widget_layout, scroll_view and list_view layout code
(children_layouter_list_view), the list_view's paint-children hook, the default painter, widget_restack/visible/move and the
pointer path (widget_on_pointer_down / _move / _up with the window_base abort a dialog's TO_BACKGROUND sends) run under Unicorn on a
tree of real widget structs (window > list_view > scroll_view > list_item rows), the payload's menu_arrange and Main Menu page code
calling them. Only leaves are mocked (timers, animators, emitter, darray, the canvas and its clip, widget state).

Each scenario runs twice: "V2.1mY" is the arrangement before this change (widget_restack does nothing and the list_view's paint hook
is put back after every arrangement, so the stock code sees what the old payload left), "fixed" is the current payload.
  1. the stock list_view re-stacks its visible rows in child order at every relayout (the main loop lays out before each paint,
     whenever a widget_set_visible marked the window): a relayout put the asset's order back (the lock screen splash) -> the
     children are stacked in page order, so a relayout leaves the page as it is;
  2. the pull-down: the dialog's TO_BACKGROUND aborts the pointer, the snapshot lays the window out, the dialog closes and the page
     arranges itself again -> every step keeps the page;
  3. the list_view paint hook stops at the first child below the canvas (it assumes y order) -> page order = y order, and the plain
     painter has no early exit."""
import struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

LEAVES = {**STOCK_LEAVES, 0x6f186c: 'darray_push', 0x6f1d70: 'darray_deinit', 0x6771dc: 'window_base_set_need_relayout', 0x675bc4: 'window_base_cast',
          0x6676bc: 'widget_get_prop', 0x64352c: 'canvas_get_width', 0x643554: 'canvas_get_height',
          0x64379c: 'canvas_is_rect_in_clip_rect', 0x66dc08: 'widget_paint'}
STOCK = ('widget_move', 'widget_resize', 'widget_set_visible', 'widget_get_visible', 'widget_set_sensitive', 'widget_set_need_relayout_children',
         'widget_count_children', 'widget_get_child', 'widget_get_type')   # pinned for the payload, but here the real stock code runs
LAYOUTER_VT, LV_HOOK, PAINT_HOOK, PAINT_DEFAULT = 0x9047a0, 0x60c0fc, 0x60c164, 0x674690
CHECK_AND_LAYOUT = 0x677a80       # window_manager_check_and_layout: the main loop calls it before every paint (@0x6939f4), the snapshots too (@0x68f194)
ROW_H, ITEMS = 52, len(pod_pages.ITEMS)
MENU_ROWS, EX = ITEMS + 1, ITEMS   # the menu's rows; the Extras row is the last, its index the item count
LCD_W, LCD_H = 320, 480
SAVED = '/mnt/data/m1plus/home-menu'


class SM(StockEventMachine):
    """The machine: demo's code and data, the payload and the mocks. fixed False: the arrangement V2.1mY left (see the module doc)."""
    LEAVES = LEAVES
    EXTRA = ("widget_animator_destroy",)

    def __init__(self, fixed=True):
        super().__init__()
        self.fixed = fixed
        for n in STOCK + (("widget_restack",) if fixed else ()):
            if n in pod.FUNCTIONS: self.handlers.pop(pod.FUNCTIONS[n][2], None)
        self.win, self.painted, self.canvas_h = 0, [], LCD_H

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name == "widget_set_prop_int":   # scroll_view_set_prop's two stores (virtual_h @0x7c, yoffset @0x84; the scroll bar callback left out)
            a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
            prop = self.read_cstr(a1)
            self.log.append(("prop", prop, struct.unpack("<i", struct.pack("<I", a2))[0]))
            self.setword(a0 + {"virtual_h": 0x7c, "yoffset": 0x84}[prop], a2)
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        super()._hook(u, address, size, _)

    def leaf(self, name, a0, a1, a2, a3, sp):
        if name == "widget_get_window": return self.win
        if name == "window_base_cast": return a0
        if name == "window_base_set_need_relayout":
            self.u.mem_write(a0 + 0xcc, bytes([a1 & 1])); self.log.append(("relayout", a1))
        elif name == "widget_get_prop": return 0x10          # no layout_w / layout_h: the parent's size
        elif name == "canvas_get_width": return LCD_W
        elif name == "canvas_get_height": return self.canvas_h
        elif name == "canvas_is_rect_in_clip_rect":         # the clip is the whole screen
            sx = lambda v: struct.unpack("<i", struct.pack("<I", v))[0]
            x, y, w, h = sx(a1), sx(a2), sx(a3), sx(self.word(sp + 16))
            return int(x < LCD_W and y < LCD_H and x + w > 0 and y + h > 0)
        elif name == "widget_paint": self.painted.append(a0)
        elif name == "darray_init":
            for off, v in ((0, 0), (4, max(a1, 1)), (8, self.alloc(4 * max(a1, 1))), (0xc, 0), (0x10, 0)): self.setword(a0 + off, v)
        elif name == "darray_push":
            n, elms = self.word(a0), self.word(a0 + 8)
            self.setword(elms + 4 * n, a1); self.setword(a0, n + 1)
        else: return super().leaf(name, a0, a1, a2, a3, sp)
        return 0

    def build(self, rows=MENU_ROWS, lvy=10, lvh=430, main=False, pad=False, hdrs=False):
        """window > list_view > scroll_view > rows as m1plus_menu.bin lays them out in the Home instance (lvy 10, lvh 430); main: the
        Main Menu page's 19 rows, each with its switch image and up arrow, under a navbar (list_view at 50, 400 px)."""
        if main: rows, lvy, lvh = ITEMS, 50, 400
        self.root = self.win = self.widget(LI_VT, 0, 0, 320, 450)
        self.lv = self.widget(LV_VT, 0, lvy, 320, lvh, self.root)
        self.sv = sv = self.widget(SV_VT, 0, 0, 310, lvh, self.lv)
        self.kids(self.root, [self.lv]); self.kids(self.lv, [sv])
        self.rows = [self.widget(LI_VT, 0, i * ROW_H, 310, ROW_H, sv, emitter=True) for i in range(rows)]
        self.pad = None
        if pad:   # the menu's trailing spacer row pod_pad (the mini player bar's list padding): hidden in the asset, the last child, O['MB_PAD'] high
            self.pad = self.widget(LI_VT, 0, rows * ROW_H, 310, O['MB_PAD'], sv); self.u.mem_write(self.pad + 0x24, struct.pack('<H', 0x1))   # enabled, not visible, not sensitive
        self.hdrs = []
        if hdrs:   # the Extras page's section headers pod_hdr0..3 (tools/pod_ui.py extras_headers): hidden views HDR_H high after the rows, which the list_view layouter sums with their own heights
            self.hdrs = [self.widget(LI_VT, 0, 0, 310, pod_pages.HDR_H, sv) for _ in pod_pages.EXTRAS_GROUPS]
            for h in self.hdrs: self.u.mem_write(h + 0x24, struct.pack('<H', 0x1))
        self.kids(sv, self.rows + self.hdrs + ([self.pad] if pad else []))
        for off, v in ((0x78, 310), (0x7c, rows * ROW_H), (0xec, 0x611450), (0xf0, LV_HOOK), (0xf4, PAINT_HOOK)): self.setword(sv + off, v)   # what list_view_on_add_child leaves
        self.u.mem_write(sv + 0x90, bytes([0, 1, 0]))
        speed = self.word(0x759814); self.setword(sv + 0x88, speed); self.setword(sv + 0x8c, speed)
        for off, v in ((0x7c, ROW_H), (0x84, sv)): self.setword(self.lv + off, v)   # list_view: default_item_height 52, its scroll_view
        lay = self.alloc(0x1c); self.u.mem_write(lay, bytes(0x1c)); self.setword(lay + 0xc, LAYOUTER_VT); self.u.mem_write(lay + 0x1a, bytes([4]))
        self.setword(sv + 0x64, lay)                                                   # "list_view(m=0,s=0)", as the layout hook installs it
        self.widgets = {'pod_scrollview': sv, **{f'pod_row{i}': r for i, r in enumerate(self.rows)}, **({'pod_pad': self.pad} if pad else {}), **{f'pod_hdr{g}': h for g, h in enumerate(self.hdrs)}}
        if main:
            self.switch, self.up = [], []
            for i, r in enumerate(self.rows):
                s = self.widget(IMG_VT, 240, 12, 40, 40, r)
                self.switch.append(s); self.widgets[f'pod_switch{i}'] = s
                u_ = self.widget(BTN_VT, 191, 0, 50, ROW_H, r, emitter=True)
                self.props[(u_, 'x')], self.props[(u_, 'w')] = 191, 50   # the arrow's rectangle in the row (widget_get_prop_int)
                self.kids(r, [s, u_]); self.up.append(u_)
                self.widgets[f'pod_up{i}'] = u_
            self.props[(sv, 'h')] = lvh
        self.wm = self.widget(LI_VT, 0, 0, 320, 480); self.kids(self.wm, [self.root])

    # ---- the window manager
    def relayout(self):
        """window_manager_check_and_layout: what the main loop does before every paint (and the snapshot before it paints the page)."""
        self.log = []
        self.call(CHECK_AND_LAYOUT, a0=self.wm, count=4000000)
        return self.log

    def mark(self): self.u.mem_write(self.root + 0xcc, bytes([1]))   # window_base_set_need_relayout(window, 1)
    def marked(self): return bool(self.u.mem_read(self.root + 0xcc, 1)[0])

    def arrange(self, extras=0):
        """The payload's menu_arrange (open, and every TO_FOREGROUND via m1plus.c on_menu_fg). V2.1mY left the list_view's paint hook."""
        self.call(PSYMS['menu_arrange'], a0=self.root, a1=extras, count=4000000)
        if not self.fixed: self.setword(self.sv + 0xf4, PAINT_HOOK)

    def paint(self, d=None):
        """The rows scroll_view_on_paint_children paints: its hook (list_view's, stock) if set, else the default painter."""
        c = self.alloc(0x40); self.u.mem_write(c, bytes(0x40))
        self.setword(c, self.s32(self.lv) + self.s32(self.sv) - self.s32(self.sv + 0x80))
        self.setword(c + 4, 30 + self.s32(self.lv + 4) + self.s32(self.sv + 4) - (self.yoff() if d is None else d))   # 30: the system bar
        self.painted = []
        self.call(self.word(self.sv + 0xf4) or PAINT_DEFAULT, a0=self.sv, a1=c, count=4000000)
        return [self.rows.index(r) for r in self.painted]

    # ---- reading the page
    def yoff(self): return self.s32(self.sv + 0x84)
    def vh(self): return self.s32(self.sv + 0x7c)
    def wa(self): return self.word(self.sv + 0xe8)
    def shown(self, r): return bool(struct.unpack('<H', self.u.mem_read(r + 0x24, 2))[0] & 4)
    def order(self): return [i for _, i in sorted((self.s32(r + 4), i) for i, r in enumerate(self.rows) if self.shown(r))]
    def hdr_ys(self): return {g: self.s32(h + 4) for g, h in enumerate(self.hdrs) if self.shown(h)}
    def ys(self): return {i: self.s32(r + 4) for i, r in enumerate(self.rows) if self.shown(r)}
    def stack(self):
        arr = self.word(self.sv + 0x58); elms = self.word(arr + 8)
        return [self.rows.index(c) if c in self.rows else f'hdr{self.hdrs.index(c)}' if c in self.hdrs else 'pad' for c in (self.word(elms + 4 * i) for i in range(self.word(arr)))]


def world(saved, fixed, **kw):
    m = SM(fixed); m.build(**kw)
    if saved is not None: m.fs[SAVED] = saved
    return m


def settle(m):
    """The menu as the user sees it once it is open: arranged on open, laid out before the first paint, arranged again on TO_FOREGROUND."""
    m.arrange(); m.relayout(); m.arrange(); m.relayout()


def run(ctx):
    expect = ctx.expect
    # -- what the fix relies on is what the stock code is ---------------------------------------------------------------
    d = open(DEMO, 'rb').read(); image = bytearray(d)
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]
    for a, w, what in ((0x60c164, 0x3c1c003f, 'list_view paint hook prologue (lui gp, 0x3f)'), (0x60c168, 0x279c7d6c, 'list_view paint hook prologue (addiu gp, gp, 0x7d6c)'),
                       (0x60cd08, 0x2463c164, 'list_view_on_add_child: v1 = 0x60c164'), (0x60cd10, 0xac4300f4, 'list_view_on_add_child: sw v1, 0xf4(v0)'),
                       (0x610ed0, 0x8e7900f4, 'scroll_view_on_paint_children: lw t9, 0xf4(s3)'), (0x66dd6c, 0x8e020070, 'widget_paint: lw v0, 0x70(s0)'),
                       (0x60c0fc, 0x3c1c003f, 'list_view layout hook prologue (installed in sv + 0xf0)')):
        expect(word(a) == w, f'pinned {a:#x} ({what})')
    bal = word(0x6939f4)   # bal imm16: pc + 4 + 4 * imm
    expect(bal >> 16 == 0x0411 and 0x6939f4 + 4 + 4 * struct.unpack('<h', struct.pack('<H', bal & 0xffff))[0] == CHECK_AND_LAYOUT,
           'pinned 0x6939f4: the main loop calls window_manager_check_and_layout (0x677a80) before every window_manager_paint')
    expect('SV_VTABLE' in pod.DATA and pod.DATA['SV_VTABLE'] == (SV_VT, 'g_scroll_view_vtable') and pod.DATA['LV_PAINT_HOOK'][0] == PAINT_HOOK,
           'the payload knows the scroll_view vtable and the list_view paint hook')

    # -- 1. a relayout ----------------------------------------------------------------------------------------------------
    for name, saved in (('Cover Flow first', b'1023456j\n'), ('a shuffled order', b'2403156j\n'), ('the default', b'0123456j\n'), ('no saved list', None)):
        want = {None: [1, 2, 3, 4, 5, EX], b'0123456j\n': [0, 1, 2, 3, 4, 5, 6, 18, EX], b'1023456j\n': [1, 0, 2, 3, 4, 5, 6, 18, EX], b'2403156j\n': [2, 4, 0, 3, 1, 5, 6, 18, EX]}[saved]
        for fixed in (False, True):
            tag = 'fixed' if fixed else 'V2.1mY'
            m = world(saved, fixed)
            m.arrange()
            expect(m.order() == want and m.vh() == len(want) * ROW_H, f'{tag} {name}: the page is arranged ({m.order()}, virtual_h {m.vh()})')
            expect(m.marked(), f'{tag} {name}: hiding the other rows marks the window for a relayout (widget_set_visible @0x66c424)')
            m.relayout()
            ok = m.order() == want and m.vh() == len(want) * ROW_H and m.ys() == {i: p * ROW_H for p, i in enumerate(want)}
            if fixed or saved in (None, b'0123456j\n'):
                expect(ok, f'{tag} {name}: the first relayout leaves the rows where they were ({m.order()})')
            else:
                expect(not ok and m.order() == [0, 1, 2, 3, 4, 5, 6, 18, EX], f'{tag} {name}: the stock list_view lays the rows out in child (asset) order again ({m.order()})')
            m.relayout(); m.mark(); m.relayout()
            expect(m.order() == (want if fixed or saved in (None, b'0123456j\n') else m.order()) and m.vh() == len(want) * ROW_H and m.yoff() == 0, f'{tag} {name}: further relayouts change nothing more')
            if fixed:
                st = m.stack()
                expect(st[:len(want)] == want and sorted(st[len(want):]) == [i for i in range(MENU_ROWS) if i not in want] and len(st) == MENU_ROWS,
                       f'fixed {name}: the children are stacked in page order, the hidden rows last ({st})')
                expect(m.word(m.sv + 0xf4) == 0, 'fixed: the list_view paint hook is gone (the plain painter paints the rows)')
    # the Extras page: the fixed grouped order is child order too (restacked), so a relayout leaves it
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        m = world(b'1023456j\n', fixed, rows=ITEMS); m.arrange(extras=1); o = m.order()
        want = [i for i in pod_pages.EXTRAS_ORDER if 7 <= i < 18 or i == 19 or i >= ITEMS - 4]   # the Pod, Podcasts, Radio, Search and Navidrome are on Extras
        expect(o == want, f'{tag}: the Extras page shows the items the menu does not show in the fixed order ({o})')
        m.relayout()
        expect(m.order() == (want if fixed else list(range(7, 18)) + [19, ITEMS - 4, ITEMS - 3, ITEMS - 2, ITEMS - 1]),
               f'{tag}: the Extras page after a relayout ' + ('is the same' if fixed else f'is back in id order ({m.order()})'))
        if fixed: expect(m.stack()[:len(want)] == want and m.vh() == len(want) * ROW_H, f'fixed: the Extras children are stacked in that order ({m.stack()})')
    # the Extras page with its section headers: the stock list_view layouter keeps a child's own height (a header is HDR_H high, not 52), so after any relayout the headers
    # and the rows are where the payload put them (pod_pages.extras_display / extras_layout) and virtual_h is the sum of the heights
    for saved in (None, b'1023456j\n', b'\n', b'0123456abcdefghi\n', b'1-ab\n', b'012345678\n', b'012345678abcdefghijk\n', b'2-hi\n'):
        m = world(saved, True, rows=ITEMS, hdrs=True)
        shown, hidden = pod_pages.extras_display(*pod_pages.parse_menu_full(saved))
        lay, height = pod_pages.extras_layout(shown, ROW_H)
        want_rows = {key: y for kind, key, y in lay if kind == 'row'}
        want_hdrs = {key: y for kind, key, y in lay if kind == 'hdr'}
        want_stack = [key if kind == 'row' else f'hdr{key}' for kind, key in shown + hidden]
        m.arrange(extras=1)
        for step, act in (('arranged', lambda: None), ('relayout', m.relayout), ('mark and relayout', lambda: (m.mark(), m.relayout())), ('arranged again', lambda: (m.arrange(extras=1), m.relayout()))):
            act()
            expect(m.ys() == want_rows and m.hdr_ys() == want_hdrs and m.vh() == height and m.stack() == want_stack and m.yoff() == 0,
                   f'Extras with headers, saved {saved!r}, {step}: the rows {m.ys()}, headers {m.hdr_ys()}, virtual_h {m.vh()} (want {want_rows}, {want_hdrs}, {height})')
    # a list the payload does not know is left alone
    for what, mut in (('another vtable', lambda m: m.setword(m.sv + 0x70, LV_VT)), ('another paint hook', lambda m: m.setword(m.sv + 0xf4, 0x123456))):
        m = world(None, True); mut(m); hook = m.word(m.sv + 0xf4); m.arrange()
        expect(m.word(m.sv + 0xf4) == hook and m.order() == [1, 2, 3, 4, 5, EX], f'{what}: the paint hook word is not touched')

    # -- 2. the lock screen: the first frame after the menu is back ------------------------------------------------------
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        m = world(b'1023456j\n', fixed); settle(m)
        want = m.order(); y0 = m.ys()
        expect(want == [1, 0, 2, 3, 4, 5, 6, 18, EX] and not m.marked(), f'{tag} lock screen: the menu is settled in its saved order')
        # the screensaver (fullscreen) opens over the menu and closes; the window manager lays the menu out for the new size before it paints it
        m.mark(); m.relayout()
        first_frame = m.order()
        if fixed: expect(first_frame == want and m.ys() == y0, f'fixed lock screen: the first frame after the unlock is the saved order ({first_frame})')
        else: expect(first_frame == [0, 1, 2, 3, 4, 5, 6, 18, EX], f'V2.1mY lock screen: the first frame is the asset order, the splash ({first_frame})')
        m.arrange(); m.relayout()      # EVT_WINDOW_TO_FOREGROUND: on_menu_fg
        expect(m.order() == want and m.ys() == y0 and m.vh() == 9 * ROW_H, f'{tag} lock screen: and the saved order after the foreground event')

    # -- 3. the pull-down --------------------------------------------------------------------------------------------------
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        for saved, ys_ in ((b'0123456j\n', (34, 42)), (b'1023456j\n', (34, 42)), (b'0123456j\n', (34, 42, 58)), (b'1023456j\n', (34, 42, 58))):
            saved_tag = f'{saved!r} after {len(ys_)} moves'
            m = world(saved, fixed); settle(m)
            want = m.order(); y0 = m.ys()
            # DOWN on the first row, MOVEs: the list takes the finger (a stock drag); on the one past 10 px the window manager's touch hook
            # (0x4cd788) opens the dialog
            m.pointer('d', 100, 30, 0)
            for y in ys_: m.pointer('m', 100, y)
            expect(m.word(m.root + 0x4c) != 0 and m.word(m.lv + 0x4c) != 0, f'{tag} pull-down {saved_tag}: the list owns the finger')
            # window_base_on_event(EVT_WINDOW_TO_BACKGROUND) while pressed: the abort; the scroll_view goes back to where it was pressed
            m.pointer('u', 100, ys_[-1], 16, abort=True)
            expect(m.word(m.root + 0x4c) == 0 and m.word(m.lv + 0x4c) == 0 and m.word(m.sv + 0x4c) == 0, f'{tag} pull-down {saved_tag}: the abort ungrabs the list, the dialog gets the rest of the gesture')
            expect((m.yoff() == 0) or (m.wa() != 0 and any(a['y1'] == 0 for a in m.anims.values())), f'{tag} pull-down {saved_tag}: the scroll_view is back, or on its way back to offset 0 ({m.yoff()})')
            # the dialog's snapshot: the window manager lays the page out, whatever marked it, and paints it
            m.mark(); m.relayout()
            if fixed or saved == b'0123456j\n':
                expect(m.order() == want and m.ys() == y0 and m.vh() == 9 * ROW_H, f'{tag} pull-down {saved!r}: the snapshot shows the page as it was ({m.order()})')
            else:
                expect(m.order() != want and m.order()[0] == 0, f'{tag} pull-down {saved!r}: the snapshot shows the asset order ({m.order()})')
            snap = m.paint(d=0)
            expect(sorted(snap) == sorted(want), f'{tag} pull-down {saved!r}: and paints every shown row ({snap})')
            # the animation ends, the dialog closes: EVT_WINDOW_TO_FOREGROUND -> on_menu_fg
            m.setword(m.sv + 0x84, 0); m.arrange(); m.relayout()
            expect(m.order() == want and m.ys() == y0 and m.yoff() == 0 and m.vh() == 9 * ROW_H, f'{tag} pull-down {saved!r}: back in front the page is as before ({m.order()}, offset {m.yoff()})')
            expect(sorted(m.paint()) == sorted(want), f'{tag} pull-down {saved!r}: every row is painted')

    # -- 3b. the list_view paint hook (stock) against rows out of y order, and the plain painter ---------------------------
    # a finger that drags the list down far enough (the stock overscroll is unbounded) puts the first child's top below the canvas
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        m = world(b'1023456j\n', fixed); settle(m)
        got = m.paint(d=-420)         # 420 px of overscroll: Cover Flow (y 0) is at 460 on the 480 px screen, Now Playing (y 52) at 512
        on_screen = [i for i, y in m.ys().items() if 30 + 10 + y + 420 < LCD_H]
        if fixed: expect(sorted(got) == sorted(on_screen) and on_screen == [1], f'fixed overscroll: every row on the screen is painted ({got} of {on_screen})')
        else: expect(on_screen == [1] and got == [], f'V2.1mY overscroll: the stock hook gives up at Now Playing, which is below the screen, and loses Cover Flow, which is on it ({got})')
    bad = []
    for d in range(0, 480, 20):       # the plain painter against the geometry, with the canvas the hook would look at 480 or 240 px high
        for h in (LCD_H, 240):
            m = world(b'0123456j\n', True); settle(m); m.canvas_h = h
            got = m.paint(d=-d)
            want = [i for i, y in m.ys().items() if 40 + y + d < LCD_H and 40 + y + d + ROW_H > 0]
            if got != want: bad.append((d, h, got, want))
    expect(not bad, f'the plain painter paints exactly the rows on the screen at every overscroll ({bad[:2]})')
    # what the stock hook does when the canvas it asks is shorter than the screen: it paints the first row and gives up at the second,
    # whatever is on the screen below (Now Playing alone, the rest of the list gone)
    m = world(b'0123456j\n', False); settle(m); m.canvas_h = 240
    expect(m.paint(d=0) == [0, 1, 2, 3] and m.paint(d=-150) == [0], f'V2.1mY, a 240 px canvas: the hook paints Now Playing and nothing after it once the list is 150 px down ({m.paint(d=-150)})')
    m = world(b'0123456j\n', True); settle(m); m.canvas_h = 240
    expect(m.paint(d=-150) == [0, 1, 2, 3, 4, 5] , f'fixed, a 240 px canvas: the plain painter paints what is on the screen ({m.paint(d=-150)})')

    # -- 4. the rest of the list keeps working (stock code, arranged page) ------------------------------------------------------
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        m = world(b'1023456j\n', fixed); settle(m)
        steps = [('d', 100, 300, 0)] + [('m', 100, 300 - 12 * i) for i in range(1, 16)] + [('u', 100, 120, 400)]
        for s in steps: m.pointer(s[0], s[1], s[2], *s[3:])
        expect(m.yoff() > 100 and m.vh() == 9 * ROW_H, f'{tag}: a slow drag up scrolls the arranged page ({m.yoff()}), the virtual height stays {m.vh()}')
        m.relayout()
        expect(m.order() == [1, 0, 2, 3, 4, 5, 6, 18, EX] if fixed else True, f'{tag}: and a relayout while scrolled does not move the rows')
        y0 = m.yoff()
        m.arrange()
        expect(m.yoff() == y0, f'{tag}: arranging the page again keeps its scroll position ({y0} -> {m.yoff()})')
        m.setword(m.sv + 0x84, 0)   # scrolled back to the top for the taps below
        # a tap lands on the row under the finger: the second row of the saved order is Now Playing's id 0
        tap = lambda: [e[1] for s in (('d', 100, 20 + ROW_H, 0), ('u', 100, 20 + ROW_H, 60)) for _ in [m.pointer(s[0], s[1], s[2], *s[3:])]
                       for e in m.log if e[0] == 'emit' and e[2] == O['EVT_CLICK']]
        expect(tap() == [], f'{tag}: the first touch after the drag stops the coasting list and presses nothing (list gestures, V2.1mV)')
        clicks = tap()
        expect(clicks == [m.rows[0]], f'{tag}: a tap on the second row of the saved order clicks Now Playing ({[m.rows.index(c) for c in clicks]})')

    # -- 5. the Main Menu page: the rows are moved by hand there too --------------------------------------------------------------
    for fixed in (False, True):
        tag = 'fixed' if fixed else 'V2.1mY'
        m = world(b'3210456j\n', fixed, main=True)
        m.call(PSYMS['menu_custom_opened'], a0=m.root, count=4000000)
        if not fixed: m.setword(m.sv + 0xf4, PAINT_HOOK)
        cm_order = [3, 2, 1, 0, 4, 5, 6, 18] + list(range(7, 18)) + [19, 20, 21, 22, 23]   # Settings, id 18, is shown last in the saved list
        ys = lambda: [i for _, i in sorted((m.s32(r + 4), i) for i, r in enumerate(m.rows))]
        expect(ys() == cm_order, f'{tag} Main Menu: opened in the saved order ({ys()})')
        m.relayout()
        expect(ys() == (cm_order if fixed else list(range(ITEMS))), f'{tag} Main Menu: a relayout ' + ('keeps the order' if fixed else f'puts the asset order back ({ys()})'))
        m.relayout()
        m.click('pod_row2', x=216); order = ys()      # Albums up one place: the first row loses its arrow, the second gets one: the window is marked
        expect(order[:7] == [2, 3, 1, 0, 4, 5, 6] and m.fs[SAVED] == b'2310456j\n', f'{tag} Main Menu: an arrow moves Albums up and saves ({order}, {m.fs.get(SAVED)})')
        expect(m.marked(), f'{tag} Main Menu: the change marks the window for a relayout (the arrows are shown or hidden)')
        m.relayout()
        expect(ys() == order if fixed else ys() == list(range(ITEMS)), f'{tag} Main Menu: and the next frame ' + ('is the page as left' if fixed else 'is the asset order'))
        if fixed: expect(m.stack() == order and m.word(m.sv + 0xf4) == 0, 'fixed Main Menu: the children are in page order and the paint hook is gone')

    # -- 6. the mini player bar's list padding: a trailing spacer row (patch/minibar.c shows it with the bar) that the stock layout keeps ------------
    # list_view's layouter (0x60b12c..) puts every visible child at the running y and sums the children's own heights into virtual_h, so a visible
    # last child O['MB_PAD'] high is the bottom padding; menu_arrange moves it after the shown rows, keeps it the last child and adds its height
    pad_h = O['MB_PAD']
    show = lambda m, on: m.call(pod.FUNCTIONS['widget_set_visible'][2], a0=m.pad, a1=on, a2=0, count=400000)
    for saved, want in ((None, [1, 2, 3, 4, 5, EX]), (b'0123456j\n', [0, 1, 2, 3, 4, 5, 6, 18, EX]), (b'j\n', [18, EX]), (b'6502j\n', [6, 5, 0, 2, 18, EX])):
        m = world(saved, True, pad=True); settle(m)
        n = len(want); tag = f'pad, saved {saved!r}'
        expect(m.order() == want and m.vh() == n * ROW_H and not m.shown(m.pad) and m.stack()[-1] == 'pad', f'{tag}: hidden, the spacer adds nothing (virtual_h {m.vh()}) and is the last child')
        show(m, 1); m.relayout()
        expect(m.vh() == n * ROW_H + pad_h and m.s32(m.pad + 4) == n * ROW_H and m.order() == want,
               f'{tag}: shown, the stock relayout sums it in (virtual_h {m.vh()}) and puts it right after Settings (y {m.s32(m.pad + 4)})')
        m.arrange(); m.relayout()
        expect(m.vh() == n * ROW_H + pad_h and m.s32(m.pad + 4) == n * ROW_H and m.order() == want and m.stack()[-1] == 'pad',
               f'{tag}: menu_arrange (TO_FOREGROUND) keeps the padding and the order')
        m.mark(); m.relayout(); m.mark(); m.relayout()
        expect(m.vh() == n * ROW_H + pad_h and m.order() == want and m.s32(m.pad + 4) == n * ROW_H, f'{tag}: further relayouts (the pull-down, the lock screen) keep it')
        expect(m.word(m.sv + 0xf4) == 0, f'{tag}: (the plain painter paints the rows and the spacer)')
        show(m, 0); m.arrange(); m.relayout()
        expect(m.vh() == n * ROW_H and m.order() == want, f'{tag}: hidden again, virtual_h is the rows')
    # a menu asset without the spacer (or the Extras page) is unchanged
    m = world(None, True); settle(m)
    expect(m.vh() == 6 * ROW_H and m.order() == [1, 2, 3, 4, 5, EX], 'no spacer in the tree: the arrangement is as before')

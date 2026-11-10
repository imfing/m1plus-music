"""Now Playing's More menu (patch/playmore.c, docs/modules/playmore.md): the stock playmore_dialog as a bottom sheet with two pages.

The dialog is built from the built asset (ui/dialog/playmore_dialog.bin) as real widget structs under demo's own window
code (the pulldown test's machine): widget_move / _resize / _set_visible / _set_sensitive / _restack, the list_view layouter
(children_layouter_list_view, run by window_manager_check_and_layout), widget_find_target and the pointer path run for real;
only leaves are mocked. The stock init (dialog_playmore_dialog_init, which widget_foreach-es the stock row binder 0x478b44 over
the tree, binds the to-background and tap-above handlers and pins the sheet at y 130) is run as far as its binding goes: the
binder is called for every widget and the two handlers are registered as the stock init does, so the stock handlers are in `m.bound`
(and every registration in `m.reg`, in order) before the hook runs, exactly as on the device, and must be there unchanged afterwards;
the stock to-background (0x4789f0) and tap-above (0x478abc) handlers run as the real stock code."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_strings, awtk_style
from awtk_text import Ttf, StbText

RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
DIALOG_Y, ROW_H, SCREEN_H, SHEET_H = 130, O['PM_ROW_H'], O['PM_SCREEN_H'], O['PM_PAGE_N'] * O['PM_ROW_H']
SHEET_Y = SCREEN_H - SHEET_H                     # 180: page 1's sheet sits on the bottom of the screen
SHEET2_H = O['PM_PAGE2_N'] * ROW_H               # page 2 has six rows (the back header, Speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete) like page 1 (Cassette Mode and Vinyl Mode rows): both sheets are 300 px
SHEET2_Y = SCREEN_H - SHEET2_H                   # 180, as page 1's SHEET_Y
BINDER, SPEED_INIT = 0x478b44, 0x478fd0          # the stock widget_foreach visitor (binds a row or badge by name) and the speed badge images
STOCK_BG, STOCK_UP = 0x4789f0, 0x478abc          # the stock to-background handler (moves the dialog to y 130) and tap-above-closes handler
STOCK_CLICK = {'listitem0': 0x478f58, 'listitem2': 0x4798f0, 'listitem3': 0x4796cc, 'listitem4': 0x4795cc, 'listitem5': 0x4793ac,
               'listitem6': 0x4791f4, 'img_1x': 0x479bf4, 'img_1_25x': 0x479b20, 'img_1_5x': 0x479a4c, 'img_2x': 0x479978}
STOCK_NAMES = ['listitem0', 'listitem1', 'listitem2', 'listitem3', 'listitem4', 'listitem5', 'listitem6']
GO_ALBUM, GO_ARTIST, ADD, MORE, BACK, SPEED, AB, DELETE, SEARCH, TAPE, VINYL, GOEP, ART, SLEEP = 4, 5, 2, 7, 8, 1, 0, 6, 3, 9, 10, 11, 12, 13   # row indices (listitemN, 7 = pod_more, 8 = pod_back, 9 = pod_tape, 10 = pod_vinyl, 11 = pod_goep, 12 = pod_art, 13 = pod_sleep)
ROWS = STOCK_NAMES + ['pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep']
PAGE1, PAGE2 = [GO_ALBUM, GO_ARTIST, ADD, TAPE, VINYL, MORE], [BACK, SPEED, SLEEP, AB, ART, DELETE]
PAGE_EP = [GOEP, MORE]   # page 1 of a podcast episode
HIDDEN1, HIDDEN2, HIDDEN_EP = sorted(set(range(14)) - set(PAGE1)), sorted(set(range(14)) - set(PAGE2)), sorted(set(range(14)) - set(PAGE_EP))
VT = {'dialog': LI_VT, 'list_view': LV_VT, 'scroll_view': SV_VT, 'list_item': LI_VT, 'image': IMG_VT}
PM_TEXTS = {'More': None, 'Speed': None, 'Files below 48 kHz only': None, 'Cassette Mode': None, 'Vinyl Mode': None, 'Go to Podcasts': None, 'Cover & Lyrics': None}   # the keys the payload sets (the label each is for is in the checks)



pulldown = sibling('pulldown')


class PM(pulldown.SM):
    """The More dialog's tree from the built asset, under the window manager `wm`. tr_fail: the keys widget_set_tr_text fails for;
    bind_fail: the widget_on of the payload's that fails ('pod_more' / 'pod_back' / 'pod_tape' click, 'bg' to-background, 'destroy')."""
    EXTRA = pulldown.SM.EXTRA + ('stock_playmore_resume',)

    def __init__(self, ui=None):
        super().__init__(True)
        self.handlers[pod.PLAYMORE_INIT + 12] = 'stock_playmore_resume'
        self.handlers[0x4a9924] = 'stock_power_refresh'   # powermanager_page's static refresh: any call from OUR code is a failure (stock's own handler is modelled in switch_to)
        self.fg_bound = set()           # Power windows whose init bound EVT_WINDOW_TO_FG (0x12d) to 0x4a9b2c, which calls 0x4a9924 (pinned in pod.PLAYMORE_PINS)
        self.tr_fail, self.bind_fail = set(), None
        self.tape_ret = 0               # what tape_open returns (patch/tape.c, trapped here: test/pod/tape.py runs it)
        self.handlers[PSYMS['tape_open']] = 'tape_open'
        self.vinyl_ret = 0              # what vinyl_open returns (patch/vinyl.c, trapped here: test/pod/vinyl.py runs it)
        self.handlers[PSYMS['vinyl_open']] = 'vinyl_open'
        self.ep_ret = 0                 # what podcasts_go returns (patch/podcasts.c, trapped here: test/pod/pcsaved.py / pcdetail run it)
        self.handlers[PSYMS['podcasts_go']] = 'podcasts_go'
        self.art_ret = 0                # what onlineart_open returns (patch/onlineart.c, trapped here: test/pod/onlineartpage.py runs it)
        self.handlers[PSYMS['onlineart_open']] = 'onlineart_open'
        self.cf_ret = 0                 # what coverflow_artist returns (patch/coverflow.c, trapped here: test/pod/coverflow.py and artists.py run it)
        self.handlers[PSYMS['coverflow_artist']] = 'coverflow_artist'
        self.am_ret = 0                 # what albums_open_artist returns (patch/albums.c, trapped here: test/pod/artists.py runs it); -1 = the window will not open
        self.handlers[PSYMS['albums_open_artist']] = 'albums_open_artist'
        self.init_ret = 0
        self.nav_ret = 0                # what navigator_to returns (the stock Power page, trapped; 0 = RET_OK)
        self.navs = []                 # the navigator's stack: (name, window)
        self.no_wm = False
        self.switch_fail, self.closing = False, set()   # the restack fails / windows that are closing (not opened)
        self.no_window = False         # the navigator opens no window (the top window is not the album page)
        self.reg = []                # every widget_on, in order: (widget, event, handler, ctx)
        self.nodes = {}
        tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui/dialog/playmore_dialog.bin'), 'rb').read()) if ui is None else ui
        self.dialog = self.root = self.win = self.make(tree, 0)
        self.wm = self.widget(LI_VT, 0, 0, 320, 480)
        self.kids(self.wm, [self.dialog]); self.setword(self.dialog + 0x44, self.wm)
        self.sv, self.lv = self.nodes['playmore_scrollview'], self.nodes['playmore_listview']
        self.bar = self.nodes['scroll_bar_m']; self.glass = self.nodes['pod_glass']
        for off, v in ((0x78, 310), (0x7c, 0), (0xec, 0x611450), (0xf0, pulldown.LV_HOOK), (0xf4, pulldown.PAINT_HOOK)): self.setword(self.sv + off, v)   # what list_view_on_add_child leaves
        self.u.mem_write(self.sv + 0x90, bytes([0, 1, 0]))
        speed = self.word(0x759814); self.setword(self.sv + 0x88, speed); self.setword(self.sv + 0x8c, speed)
        for off, v in ((0x7c, ROW_H), (0x84, self.sv)): self.setword(self.lv + off, v)   # list_view: default_item_height 50, its scroll_view
        lay = self.alloc(0x1c); self.u.mem_write(lay, bytes(0x1c)); self.setword(lay + 0xc, pulldown.LAYOUTER_VT); self.u.mem_write(lay + 0x1a, bytes([4]))
        self.setword(self.sv + 0x64, lay)
        self.rows = [self.nodes[n] for n in ROWS]
        self.widgets = dict(self.nodes)
        self.setword(pod.GP - 0xa94, PSYMS['pod_lib_strcmp'])   # the GOT slot of strcmp, for the stock binder (the base machine's strcmp mock)

    def make(self, w, parent):
        a = self.widget(VT.get(w.type, LI_VT), w.x, w.y, w.w, w.h, parent, emitter=w.type in ('list_item', 'image'))
        flags = 1 | (0 if w.get('visible') == 'false' else 4) | (0 if w.get('sensitive') == 'false' else 8)
        self.setword(a + 0x24, flags)
        if w.name:
            self.nodes[w.name] = a; self.setword(a + 0x10, self.cstr(w.name))
        if w.children:
            self.kids(a, [self.make(c, a) for c in w.children])
        return a

    def page(self, name):
        """A window of the navigator's stack (a name at +0x10), pushed on top."""
        w = self.alloc(0x80); self.u.mem_write(w, bytes(0x80)); self.setword(w + 0x10, self.cstr(name))
        self.navs = getattr(self, 'navs', []) + [(name, w)]
        if name == 'powermanager_page': self.fg_bound.add(w)   # its init: widget_on(win, 0x12d, 0x4a9b2c)
        self.sync_stack()
        return w

    def sync_stack(self):
        """The window manager's children, bottom to top: the navigator's windows, then the sheet (a dialog, always above them)."""
        self.kids(self.wm, [w for _, w in self.navs] + [self.dialog])

    def to_player(self):
        """The Power page's top-right Now Playing button (on_powermanagertoplayer_onclick: navigator_switch_to_with_context("playing_page")): the player is restacked, or opened, on top and nothing is closed, the page stays under it."""
        ent = next((e for e in self.navs if e[0] == 'playing_page'), None)
        if ent: self.navs = [e for e in self.navs if e is not ent] + [ent]; self.sync_stack()
        else: self.page('playing_page')

    def stack_names(self): return [n for n, _ in self.navs]

    def _stack_hook(self, u, name, a0):
        """The navigator model: names in self.navs (the closes are at once; the window's destroy event is the test's to deliver)."""
        stack = self.navs
        ret = 0
        if name == 'navigator_window_is_exist': ret = int(self.read_cstr(a0) in [n for n, _ in stack])
        elif name == 'navigator_close':
            self.calls.append(('navigator_close', self.read_cstr(a0)))
            self.navs = [e for e in stack if e[0] != self.read_cstr(a0)]
        elif name == 'window_manager_get_top_window': ret = stack[-1][1] if stack else 0
        u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        if name in ('navigator_window_is_exist', 'navigator_close', 'window_manager_get_top_window'):
            return self._stack_hook(u, name, a0)
        if name == 'navigator_to_with_context' and self.read_cstr(a0) == 'albuminfo_page' and not self.no_window:
            self.page('albuminfo_page')   # the navigator opens the page: a window on top (before the harness records the open)
        if name == 'coverflow_artist':
            rows = [self.read_cstr(self.word(r + O['REC_TITLE'])) for r in self.deques.get(a0, [])]
            self.calls.append(('coverflow_artist', tuple(rows), a1, a2))
            if self.cf_ret == 0 and not self.no_window: self.page('m1plus_cover')
            u.reg_write(UC_MIPS_REG_V0, self.cf_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'albums_open_artist':
            rows = [self.read_cstr(self.word(r + O['REC_TITLE'])) for r in self.deques.get(a0, [])]
            self.calls.append(('albums_open_artist', tuple(rows), a1, a2))
            if self.am_ret == 0 and not self.no_window: self.page('m1plus_albums')
            u.reg_write(UC_MIPS_REG_V0, self.am_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'navigator_to' and not self.nav_ret:   # the stock navigator opens a NEW window every time (the Power page has no single_instance property)
            self.calls.append(('navigator_to', self.read_cstr(a0))); self.page(self.read_cstr(a0).split('/')[-1])
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'window_manager_switch_to':        # stock's restack: the target to the top, nothing closed
            ent = next((e for e in self.navs if e[1] == a2), None)
            self.calls.append(('switch_to', ent[0] if ent else None, a3))
            ret = 1
            if ent and not self.switch_fail and a0 == self.wm: self.navs = [e for e in self.navs if e is not ent] + [ent]; self.sync_stack(); ret = 0
            if ret == 0:                              # stock then delivers EVT_WINDOW_TO_FG (0x12d) to the restacked window; the handler its init bound (0x4a9b2c) runs the refresh
                self.calls.append(('to_fg', ent[0]))
                if a2 in self.fg_bound: self.calls.append(('fg_refresh', ent[0]))
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'window_manager' and self.no_wm:
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'widget_is_window_opened':
            u.reg_write(UC_MIPS_REG_V0, int(a0 not in self.closing)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'stock_power_refresh':             # powermanager_page's refresh from the timer words
            self.calls.append(('stock_power_refresh', next((n for n, w in self.navs if w == a0), None)))   # only ever a direct call from the payload
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'navigator_to' and self.nav_ret:   # the stock page will not open
            self.calls.append(('navigator_to', self.read_cstr(a0))); u.reg_write(UC_MIPS_REG_V0, self.nav_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'tape_open':
            self.calls.append(('tape_open',)); u.reg_write(UC_MIPS_REG_V0, self.tape_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'podcasts_go':
            self.calls.append(('podcasts_go',)); u.reg_write(UC_MIPS_REG_V0, self.ep_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'vinyl_open':
            self.calls.append(('vinyl_open',)); u.reg_write(UC_MIPS_REG_V0, self.vinyl_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'onlineart_open':
            self.calls.append(('onlineart_open',)); u.reg_write(UC_MIPS_REG_V0, self.art_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'widget_set_tr_text' and self.read_cstr(a1) in self.tr_fail:
            self.calls.append(('widget_set_tr_text', a0, self.read_cstr(a1))); u.reg_write(UC_MIPS_REG_V0, 1); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'widget_on':
            self.reg.append((a0, a1, a2, a3))
            fails = {'pod_more': (self.nodes['pod_more'], O['EVT_CLICK']), 'pod_back': (self.nodes['pod_back'], O['EVT_CLICK']), 'pod_tape': (self.nodes['pod_tape'], O['EVT_CLICK']), 'pod_vinyl': (self.nodes['pod_vinyl'], O['EVT_CLICK']), 'pod_goep': (self.nodes['pod_goep'], O['EVT_CLICK']),  'pod_art': (self.nodes['pod_art'], O['EVT_CLICK']), 'pod_sleep': (self.nodes['pod_sleep'], O['EVT_CLICK']),
                     'bg': (self.lv, O['EVT_WINDOW_TO_BG']), 'destroy': (self.dialog, O['EVT_DESTROY'])}
            if self.bind_fail and (a0, a1) == fails[self.bind_fail] and a2 != STOCK_BG:
                self.reg.pop(); self.calls.append(('widget_on', a0, a1, a2, 0)); u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        super()._hook(u, address, size, _)

    def leaf(self, name, a0, a1, a2, a3, sp):
        if name == 'stock_playmore_resume':
            self.calls.append(('stock_playmore_resume', a0, a1)); return self.init_ret
        return super().leaf(name, a0, a1, a2, a3, sp)

    # ---- what the stock init did: bind every row and badge (the widget_foreach visitor, run per widget), the speed badge images,
    # the to-background and tap-above handlers on the dialog (widget_on @0x479ce8 / 0x479d5c), the sheet at y 130 (widget_move @0x479d20)
    def stock_init(self):
        self.stock_calls, self.reg = [], []
        self.reg += [(self.dialog, O['EVT_WINDOW_TO_BG'], STOCK_BG, self.dialog)]
        for n, w in self.nodes.items():
            self.call(BINDER, a0=self.dialog, a1=w, count=200000); self.stock_calls += self.calls
        self.call(SPEED_INIT, a0=self.dialog, count=400000); self.stock_calls += self.calls
        self.reg += [(self.dialog, O['EVT_POINTER_UP'], STOCK_UP, self.dialog)]
        for w, e, fn, ctx in self.reg: self.bound[(w, e)] = (fn, ctx)
        self.stock_bound = dict(self.bound)
        self.stock_reg = list(self.reg)
        self.setword(self.dialog + 4, DIALOG_Y)       # widget_move(dialog, 0, 130)
        self.sync()

    def open(self, **kw):
        """The dialog opens: the stock init, then the payload's hook (which runs it again as its first step)."""
        self.stock_init()
        ret = self.call(PSYMS['m1plus_playmore_init'], a0=self.dialog, a1=0, count=4000000)
        self.sync()
        return ret

    def sync(self):
        """The props the mocked widget_get_prop_int answers, from the widget structs (real widget_resize / move write those)."""
        for n, w in self.nodes.items():
            for k, o in (('x', 0), ('y', 4), ('w', 8), ('h', 0xc)): self.props[(w, k)] = self.s32(w + o)

    def stock_kept(self):
        """Every handler the stock init registered is still registered, first and in order, and still the latest for its widget and event."""
        return self.stock_reg == self.reg[:len(self.stock_reg)] and all(self.bound[k] == v for k, v in self.stock_bound.items() if k not in ((self.rows[GO_ALBUM], O['EVT_CLICK']), (self.rows[GO_ARTIST], O['EVT_CLICK']), (self.rows[DELETE], O['EVT_CLICK'])))   # (Look up album, artist and Delete are ours, bound after the stock ones)
    def handlers_of(self, w, e): return [(fn, ctx) for ww, ee, fn, ctx in self.reg if (ww, ee) == (w, e)]
    def added(self): return [(self.name(w), e) for w, e, fn, ctx in self.reg[len(self.stock_reg):]]

    # ---- reading the dialog
    def name(self, w): return self.read_cstr(self.word(w + 0x10)) if w else ''
    def flags(self, w): return struct.unpack('<H', self.u.mem_read(w + 0x24, 2))[0]
    def shown_row(self, i): return bool(self.flags(self.rows[i]) & F_VISIBLE)
    def live(self, i): return (self.flags(self.rows[i]) & (F_VISIBLE | F_SENSITIVE)) == F_VISIBLE | F_SENSITIVE
    def dead(self, i): return (self.flags(self.rows[i]) & (F_VISIBLE | F_SENSITIVE)) == 0
    def shown(self): return [i for _, i in sorted((self.s32(r + 4), i) for i, r in enumerate(self.rows) if self.shown_row(i))]
    def stacked(self):
        arr = self.word(self.sv + 0x58); elms = self.word(arr + 8)
        return [self.rows.index(self.word(elms + 4 * i)) if self.word(elms + 4 * i) in self.rows else -1 for i in range(self.word(arr))]
    def ys(self): return [self.s32(self.rows[i] + 4) for i in self.shown()]
    def hs(self): return [self.s32(self.rows[i] + 0xc) for i in self.shown()]
    def size(self, w): return (self.s32(w + 8), self.s32(w + 0xc))
    def top(self): return self.s32(self.dialog + 4)
    def vh(self): return self.s32(self.sv + 0x7c)
    def hit(self, x, y):
        """The widgets the stock hit test descends through for a touch at the screen point (x, y), by demo's own widget_find_target; a hit on
        a widget the pointer path would not take (not enabled and sensitive) ends the list with a '!'."""
        w, path = self.wm, []
        while True:
            t = self.call(FIND_TARGET, a0=w, a1=x, a2=y, count=200000)
            if not t: return path
            if (self.flags(t) & 9) != 9: return path + [self.name(t) + '!']
            w = t; path.append(self.name(t))
    def row_y(self, i): return self.top() + self.ys()[self.shown().index(i)]
    def tap_row(self, i, x=160): return self.hit(x, self.row_y(i) + ROW_H // 2)
    def click_row(self, i):
        """A tap on a row of the sheet: the stock list_item turns the touch into a click; the payload's handler runs with the context it was given."""
        y = self.row_y(i) + ROW_H // 2
        self.touch_at('d', 160, y, 0); self.touch_at('u', 160, y, 60)
        clicks = [e[1] for e in self.log if e[0] == 'emit' and e[2] == O['EVT_CLICK']]
        assert clicks == [self.rows[i]], clicks
        fn, ctx = self.bound[(self.rows[i], O['EVT_CLICK'])]
        self.call(fn, a0=ctx, a1=0, count=4000000)
        self.sync()
    def click_more(self): self.click_row(MORE)
    def click_back(self): self.click_row(BACK)
    def touch_at(self, kind, x, y, dt): self.pointer(kind, x, y, dt, root=self.wm)
    def relayout_all(self):
        self.mark(); self.relayout()
        self.sync()
    def event(self, w, kind, y=0):
        """Every handler registered for (w, kind), in registration order, as the emitter runs them; the moved state is synced after each."""
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30)); self.setword(e, kind); self.setword(e + 0x1c, y)
        out = []
        for fn, ctx in self.handlers_of(w, kind):
            self.call(fn, a0=ctx, a1=e, count=400000); self.sync(); out.append((fn, self.top(), [c for c in self.calls if c[0] == 'window_close']))
        return out
    def kids_of(self, w):
        arr = self.word(w + 0x58)
        return [self.word(self.word(arr + 8) + 4 * i) for i in range(self.word(arr))] if arr else []
    def window_event(self, kind):
        """A window event to the dialog as demo dispatches it (window_manager_dispatch_window_event -> widget_dispatch_recursive, the
        words in tools/pod.py PLAYMORE_PINS): widget_foreach visits a widget, then its children if the visit returned RET_OK; a
        widget's emitter runs its handlers newest first (emitter_on_with_tag puts a new one at the head), stops at RET_STOP (0xb) and
        returns RET_OK after the last; a child's RET_DONE (0xa) or RET_STOP ends the walk. (widget name, handler, dialog y after it) per run."""
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30)); self.setword(e, kind)
        out = []
        def visit(w):
            for fn, ctx in reversed(self.handlers_of(w, kind)):
                ret = self.call(fn, a0=ctx, a1=e, count=400000); self.sync(); out.append((self.name(w), fn, self.top()))
                if ret == 0xb: return ret
            for c in self.kids_of(w):
                ret = visit(c)
                if ret in (0xa, 0xb): return ret
            return 0
        visit(self.dialog)
        return out


DIM = 130                                        # the asset's highlight alpha: the page under the sheet is black at 130/255
BACKDROPS = {'black': 0, 'white under the dim': round(255 * (255 - DIM) / 255), 'pure white (no dim)': 255}   # grey levels under the glass


def glass_checks(expect, built_ui, stock_ui, lum):
    """The glass sheet (pm_sheet): the image is the generator's output, top corners transparent and bottom corners and edge opaque; the dialog
    and every row are transparent over it, the pressed band and hairline translucent, inline in this dialog only; every label, badge and
    chevron keeps its contrast with the glass over black, over white under the dim and over pure white, at rest and on a pressed row."""
    import mod_icons
    from PIL import Image
    xx = os.path.join(WORK, RAW, 'images', 'xx')
    sheets = {}
    for name, spec in (('pm_sheet', mod_icons.GLASS_SHEET), ('pm_sheet6', mod_icons.GLASS_SHEET6)):   # pm_sheet (5 rows, 250 px: only pod_glass's first picture, a failed start's look) and pm_sheet6 (6 rows, 300 px, both pages): none a crop of the other
        gen = mod_icons.glass_image(*spec, fill=mod_icons.GLASS_SHEET_FILL, top_only=True)
        raw = open(os.path.join(xx, name + '.png'), 'rb').read()
        sheets[name] = im = Image.open(os.path.join(xx, name + '.png')).convert('RGBA')
        w, h, r = spec
        expect(raw == open(os.path.join(mod_icons.PNG, name + '.png'), 'rb').read() and same_pixels(raw, gen) and im.size == (w, h) == (built_ui.w, ROW_H * (5 if name == 'pm_sheet' else O['PM_PAGE_N'] == O['PM_PAGE2_N'] and O['PM_PAGE_N'])),
               f'{name}.png is the generator output pixel for pixel, {w}x{h} = the page\'s own sheet height, r {r}, top corners only')
        a = lambda x, y, im=im: im.getpixel((x, y))[3]
        expect(a(0, 0) == 0 and a(w - 1, 0) == 0 and a(0, h - 1) >= 0.7 * 255 and a(w - 1, h - 1) >= 0.7 * 255 and all(a(x, h - 1) >= 0.7 * 255 for x in range(w))
               and a(w // 2, 0) >= 0.7 * 255 and all(a(x, y) == 0 for x in range(2) for y in range(2)),
               f'{name}: the top corners are transparent, the bottom corners and the whole foot opaque (alpha {a(0, h - 1)})')
    gen = mod_icons.glass_image(320, 100, 18, fill=mod_icons.GLASS_SHEET_FILL, top_only=True)   # a podcast episode's page 1 (two rows) uses the Podcasts page's 100 px glass
    expect(same_pixels(open(os.path.join(xx, 'pc_sheet2.png'), 'rb').read(), gen) and Image.open(os.path.join(xx, 'pc_sheet2.png')).size == (320, 2 * ROW_H),
           'pc_sheet2.png is the generator output at the two-row sheet height (the episode page 1\'s glass)')
    sheet, sheet6 = sheets['pm_sheet'], sheets['pm_sheet6']
    # the same top edge: the first 18 rows of both are the rim and the rounded corners (a 300 px sheet is the 250 px one with 50 more rows of body)
    ea, eb = sheet.getchannel('A').crop((0, 0, 320, 24)).tobytes(), sheet6.getchannel('A').crop((0, 0, 320, 24)).tobytes()
    expect(max(abs(p - q) for p, q in zip(ea, eb)) <= 2, 'both sheets have the same top edge: the rim and the rounded corners (the alpha of their first 24 rows within 2 levels: the rim fades over the sheet\'s height)')
    expect(all(built_ui.get(f'style:{s}:bg_color') == '#00000000' and built_ui.get(f'style:{s}:border') == 'none' and built_ui.get(f'style:{s}:bg_image') is None
               and built_ui.get(f'style:{s}:round_radius') is None for s in ('normal', 'disable', 'focused')),
           'the dialog itself is transparent (no fill, no image, no top line, no radius): the glass is its first child')
    glass = built_ui.find('pod_glass')
    expect(glass is not None and glass.type == 'image' and built_ui.children[0] is glass and glass.get('sensitive') == 'false' and glass.get('image') == 'pm_sheet'
           and (glass.x, glass.y, glass.w, glass.h) == (0, 0, 320, 250) and glass.get('draw_type') == 'default',
           'pod_glass is the dialog\'s first child (under the list), an insensitive image of pm_sheet 320 x 250 (a failed start\'s look; the pages set pm_sheet6)')
    lv, sv = built_ui.find('playmore_listview'), built_ui.find('playmore_scrollview')
    expect(all(x.get(f'style:{s}:bg_color') == '#00000000' for x in (lv, sv) for s in ('normal', 'disable', 'focused')), 'the list_view and its scroll_view are transparent')
    states = ('normal', 'pressed', 'over', 'disable', 'focused')
    rows = [c for c in sv.children]
    expect(all(c.type == 'list_item' and all(c.get(f'style:{s}:bg_color') == ('#FFFFFF10' if s == 'pressed' else '#00000000') and c.get(f'style:{s}:border_color') == '#FFFFFF22' for s in states)
               for c in rows) and len(rows) == 14,
           'all fourteen rows: transparent in every state but pressed (#FFFFFF10, 6 % white), the hairline #FFFFFF22 (13 % white)')
    expect(not any('pm_sheet' in str(c.props) for c in stock_ui.walk()) and 'pm_sheet' not in str([p for w_ in built_ui.walk() if w_.name not in ('pod_glass',) for p in w_.props]),
           'only pod_glass refers to pm_sheet; the rows and every other widget carry inline styles of this dialog, no shared style name')
    # the other pages' row styles are untouched: no ui asset but this one, and no style file, mentions the image or a transparent list_item_style
    ui_root = os.path.join(WORK, RAW)
    users = []
    for base, _, files in os.walk(ui_root):
        for f in files:
            if f.endswith('.bin') and 'pm_sheet' in open(os.path.join(base, f), 'rb').read().decode('latin-1'): users.append(os.path.relpath(os.path.join(base, f), ui_root))
    expect(users == ['ui/dialog/playmore_dialog.bin'], f'pm_sheet is used by playmore_dialog.bin only ({users})')
    ths = awtk_style.parse(open(os.path.join(ui_root, 'styles', 'default.bin'), 'rb').read())
    its = ths.find('list_item', 'list_item_style')
    expect(its and all((it.get('bg_color') >> 24) == 255 or it.state in ('pressed', 'over', 'disable', 'focused', 'selected') for it in its)
           and next(it for it in its if it.state == 'normal').get('bg_color') >> 24 == 255 and next(it for it in its if it.state == 'normal').get('border_color') != 0x22FFFFFF,
           'the shared list_item_style (other pages\' rows) is still opaque with its own hairline')
    # -- contrast: composite glass (+ the pressed band) over a flat grey, test what the row draws on it
    th = awtk_style.parse(open(os.path.join(ui_root, 'styles', 'default.bin'), 'rb').read())
    tc = th.find('hscroll_label', 'srlabel_item_white_style', 'normal')[0].color('text_color')[:7]
    press = int(built_ui.find('listitem0').get('style:pressed:bg_color')[7:9], 16)
    hexrgb = lambda s: tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
    L = lambda c: lum('#%02X%02X%02X' % tuple(c))
    rat = lambda c1, c2: (max(L(c1), L(c2)) + 0.05) / (min(L(c1), L(c2)) + 0.05)
    page1_rows = ['listitem4', 'listitem5', 'listitem2', 'pod_tape', 'pod_vinyl', 'pod_more']
    def under(x, y, level, pressed, row):
        px = (sheet6 if row in page1_rows else sheet).getpixel((x, y)); al = px[3] / 255
        c = [al * px[i] + (1 - al) * level for i in range(3)]
        if pressed: c = [press / 255 * 255 + (1 - press / 255) * v for v in c]
        return tuple(round(v) for v in c)
    pos = {n: (i * ROW_H) for i, n in enumerate(page1_rows)}
    pos.update({n: (i * ROW_H) for i, n in enumerate(['pod_back', 'listitem1', 'listitem0', 'pod_art', 'listitem6'])})
    texts = {'listitem4': 'scrlabel4', 'listitem5': 'scrlabel5', 'listitem2': 'scrlabel2', 'pod_more': 'pod_more_label', 'pod_back': 'pod_back_label',
             'listitem1': 'scrlabel1', 'listitem0': 'scrlabel0', 'listitem6': 'scrlabel6', 'pod_tape': 'pod_tape_label', 'pod_vinyl': 'pod_vinyl_label', 'pod_art': 'pod_art_label'}
    def worst(row, wname, color, level, pressed, img=None):
        wd = built_ui.find(wname); y0 = pos[row]; best = 99
        for y in range(wd.y, wd.y + wd.h):
            for x in range(wd.x, min(wd.x + wd.w, 300), 2):
                if img is not None:
                    ix, iy = x - wd.x, y - wd.y
                    if ix >= img.width or iy >= img.height or img.getpixel((ix, iy))[3] < 128: continue
                    color = img.getpixel((ix, iy))[:3]
                best = min(best, rat(color, under(x, y0 + y, level, pressed, row)))
        return best
    table = {}
    for lname, level in BACKDROPS.items():
        for pressed in (False, True):
            for row, lab in texts.items():
                col = hexrgb('#FF5A4F') if lab == 'scrlabel6' else hexrgb(tc)
                table[lname, pressed, lab] = worst(row, lab, col, level, pressed)
            table[lname, pressed, 'note'] = worst('listitem1', 'label1_msg', hexrgb('#AAAAAA'), level, False)
            for badge in ('img_1x', 'img_2x'):
                bi = Image.open(os.path.join(xx, built_ui.find(badge).get('image') + '.png')).convert('RGBA')
                wd = built_ui.find(badge)
                best = 99
                for y in range(bi.height):
                    for x in range(bi.width):
                        p = bi.getpixel((x, y))
                        if p[3] >= 128: best = min(best, rat(p[:3], under(wd.x + x, pos['listitem1'] + 8 + y, level, False, 'listitem1')))
                table[lname, pressed, badge] = best
            for chev, row in (('pod_more_chev', 'pod_more'), ('pod_back_chev', 'pod_back')):
                wd = built_ui.find(chev); ci = Image.open(os.path.join(xx, wd.get('image') + '.png')).convert('RGBA')
                best = 99
                for y in range(ci.height):
                    for x in range(ci.width):
                        p = ci.getpixel((x, y))
                        if p[3] >= 128: best = min(best, rat(p[:3], under(wd.x + x, pos[row] + wd.y + y, level, pressed, row)))
                table[lname, pressed, chev] = best
    for line in sorted(set((k[0], k[1]) for k in table)):
        print('  glass contrast', line, {k[2]: round(v, 2) for k, v in table.items() if k[:2] == line})
    for lname in ('black', 'white under the dim'):
        for pressed in (False, True):
            lw = min(v for (ln, pr, lab), v in table.items() if ln == lname and pr == pressed and lab in texts.values() and lab != 'scrlabel6')
            expect(lw >= 7, f'the white row labels keep 7:1 over the glass over {lname}, pressed={pressed} ({lw:.2f})')
            # the red (lum 0.29) is the weak one: 4.5:1 at rest over both; pressed 4.5:1 over black (the stock sheet gave 4.85) and 3:1 where a pure white
            # glyph lies behind the label (a highlighter-dimmed 125 grey: a transport glyph; the tone under np_tint is at most 192 x (1 - 0.58) = 81 at window row 250, 40 after the dim)
            floor = 4.5 if (lname == 'black' or not pressed) else 3
            expect(table[lname, pressed, 'scrlabel6'] >= floor, f'the red Delete label keeps {floor}:1 over {lname}, pressed={pressed} ({table[lname, pressed, "scrlabel6"]:.2f})')
        expect(table[lname, False, 'note'] >= 4.5, f'the Speed note keeps 4.5:1 over {lname} ({table[lname, False, "note"]:.2f})')
        nf = 3 if lname == 'black' else 2.5      # the unselected badges are grey outlines by design (the selected one is white)
        expect(all(table[lname, pr, k] >= nf for pr in (False, True) for k in ('img_1x', 'img_2x', 'pod_more_chev', 'pod_back_chev')),
               f'the badges and chevrons keep {nf}:1 over {lname}: ' + str({k[2]: round(v, 2) for k, v in table.items() if k[0] == lname and k[2] in ('img_1x', 'img_2x', 'pod_more_chev', 'pod_back_chev')}))
    expect(all(table['pure white (no dim)', pr, lab] >= 7 for pr in (False,) for lab in texts.values() if lab != 'scrlabel6'),
           'the white row labels keep 7:1 even over pure white with no dim (a stress case: the highlighter always dims)')


def run(ctx):
    expect = ctx.expect
    d = open(DEMO, 'rb').read(); image = bytearray(d)
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]

    # -- 0. the hook and what it relies on -----------------------------------------------------------------------------------
    w0, w1, w2, w3 = (word(pod.PLAYMORE_INIT + 4 * i) for i in range(4))
    expect(w0 == pod.j(PSYMS['m1plus_playmore_init']) and w1 == 0 and w2 == pod.PLAYMORE_INIT_PROLOGUE[2] and w3 == 0x10800059 == pod.PLAYMORE_PINS[0][1],
           'dialog_playmore_dialog_init starts with j m1plus_playmore_init; nop; the trampoline resumes at its beqz a0')
    expect(pod.PLAYMORE_INIT == 0x479cc4 and MANIFEST['hook_playmore']['addr'] == pod.PLAYMORE_INIT and MANIFEST['hook_playmore']['target'] == PSYMS['m1plus_playmore_init'],
           'the manifest records the hook')
    gp = []
    m = PM(); m.u.hook_add(UC_HOOK_CODE, lambda u, a, s, _: gp.append(u.reg_read(UC_MIPS_REG_GP)), begin=pod.PLAYMORE_INIT + 12, end=pod.PLAYMORE_INIT + 12)
    m.open()
    expect(gp == [pod.GP], f'the trampoline restores $gp before the stock body ({[hex(g) for g in gp]})')
    expect(all(word(a) == old for a, old, _ in pod.PLAYMORE_PINS[1:]), 'every pinned stock word of the dialog init, its dispatcher, its two handlers and the window event path is as pinned')
    pins = {a: old for a, old, _ in pod.PLAYMORE_PINS}
    expect(pins.get(0x479ce0) == 0x2405012c and pins.get(0x478a1c) == 0x24060082 and pins.get(0x479d10) == 0x24060082 and pins.get(0x478ac8) == 0x8c830004,
           'the stock to-background bind (0x12c), its widget_move(dialog, 0, 130), the init\'s widget_move and the tap-above read of dialog->y are pinned')
    # the dim: the window manager sets the highlighter up from the dialog's "highlight" property when the dialog opens (0x6901c4 reads it, the
    # "default" highlighter is registered at tk init, 0x68e8bc)
    expect(word(0x6901c4) == 0x24a59a1c and word(0x68e8bc) == 0x24a5a988 and d[pod.fileoff(image, 0x749a1c):][:10] == b'highlight\0' and d[pod.fileoff(image, 0x74a988):][:8] == b'default\0',
           'the stock window manager reads the dialog\'s "highlight" property when it opens and registers the "default" highlighter')
    expect(m.calls[0] == ('stock_playmore_resume', m.dialog, 0), 'the stock init runs first, with its arguments')

    # -- 1. page 1: the order, visibility, sensitivity, geometry ----------------------------------------------------------------
    m = PM(); m.stock_init()
    stock_bound = dict(m.stock_bound)
    expect(set(STOCK_CLICK) <= {n for n, w in m.nodes.items() if (w, O['EVT_CLICK']) in stock_bound}
           and all(stock_bound[(m.nodes[n], O['EVT_CLICK'])][0] == fn for n, fn in STOCK_CLICK.items()),
           'the stock init binds listitem0, 2, 3, 4, 5, 6 and the four speed badges to the stock handlers (the reference for the checks below)')
    keys = {m.name(c[1]): c[2] for c in m.stock_calls if c[0] == 'widget_set_tr_text'}
    expect(keys.get('scrlabel4') == 'player_albuminfo' and keys.get('scrlabel5') == 'player_songerinfo' and keys.get('scrlabel6') == 'player_delete'
           and keys.get('scrlabel1') == 'player_multiple' and keys.get('scrlabel0') == 'player_abrepeat' and keys.get('label1_msg') == 'player_msgmul',
           'the stock binder gives the rows their stock texts')
    expect(m.shown() == [0, 1, 2, 3, 4, 5, 6] and m.stacked()[:7] == list(range(7)) and all(m.dead(i) for i in (MORE, BACK, TAPE, VINYL, GOEP, ART, SLEEP)) and not m.shown_row(MORE) and not m.shown_row(BACK) and not m.shown_row(TAPE) and not m.shown_row(VINYL),
           'before the hook: the stock seven rows in asset order, pod_more, pod_back, pod_tape and pod_vinyl hidden and insensitive')
    m.relayout_all()
    expect(m.shown() == list(range(7)) and m.hs() == [50, 50, 50, 50, 50, 60, 60] and m.ys() == [0, 50, 100, 150, 200, 250, 310] and m.vh() == 370,
           f'the stock list_view layouter keeps the asset\'s own 60 px for Go to artist and Delete: 370 px of rows in the 350 px sheet ({m.ys()} {m.hs()} {m.vh()})')
    m = PM(); ret = m.open()
    expect(ret == 0, 'the hook returns the stock result')
    expect(m.shown() == PAGE1, f'page 1: Look up album, Look up artist, Add to playlist, More ({m.shown()})')
    expect(m.ys() == [0, 50, 100, 150, 200, 250], f'page 1: the rows at 0, 50, 100, 150, 200, 250 ({m.ys()})')
    expect(all(m.live(i) for i in PAGE1) and all(m.dead(i) for i in HIDDEN1), 'page 1: the shown rows are visible and sensitive, the other six neither (visible=false and sensitive=false)')
    expect(m.stacked()[:6] == PAGE1 and sorted(m.stacked()[6:]) == HIDDEN1, f'page 1: the children are stacked shown rows first, hidden last ({m.stacked()})')
    expect(set(m.hs()) == {ROW_H}, f'page 1: every shown row is {ROW_H} high, Look up artist too ({m.hs()})')
    expect(m.size(m.dialog) == (320, 300) and m.size(m.lv) == (320, 300) and m.size(m.sv) == (310, 300) and m.size(m.bar) == (10, 300) and m.vh() == 300 and m.yoff() == 0
           and m.size(m.glass) == (320, 300),
           f'page 1: the sheet and its glass are 6 rows tall, 300 px ({m.size(m.dialog)}, virtual_h {m.vh()})')
    expect(m.top() == SHEET_Y == 180 and m.top() + m.size(m.dialog)[1] == SCREEN_H and m.s32(m.dialog) == 0,
           f'page 1: the sheet sits on the bottom of the screen: y {m.top()} + {m.size(m.dialog)[1]} = {m.top() + m.size(m.dialog)[1]}')
    expect(('widget_set_tr_text', m.nodes['pod_more_label'], 'More') in m.calls and ('widget_set_tr_text', m.nodes['pod_back_label'], 'More') in m.calls and ('widget_set_tr_text', m.nodes['pod_tape_label'], 'Cassette Mode') in m.calls and ('widget_set_tr_text', m.nodes['pod_vinyl_label'], 'Vinyl Mode') in m.calls,
           'the More row and the back header read "More", the Cassette Mode row "Cassette Mode" (translated by key)')
    expect(('widget_set_tr_text', m.nodes['scrlabel1'], 'Speed') in m.calls and ('widget_set_tr_text', m.nodes['label1_msg'], 'Files below 48 kHz only') in m.calls,
           'the Playback speed label reads "Speed" and the note under it its short text')
    expect([c for c in m.calls if c[0] == 'image_base_set_image'] == [('image_base_set_image', m.nodes['pod_glass'], 'pm_sheet6')], 'the More chevron is a fixed image: the only picture set is the glass (page 1\'s pm_sheet6)')
    names = [c[1] for c in m.calls if c[0] == 'widget_lookup']
    expect(all(n in names for n in ('listitem0', 'listitem6', 'pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_more_label', 'pod_back_label', 'pod_tape_label', 'pod_vinyl_label', 'scrlabel1', 'label1_msg')), 'the rows and labels are found by their names')
    expect(m.stock_kept(),
           'every stock handler is still bound to the same function and context after the hook, and still first in the order')
    expect(sorted(m.added()) == sorted([('pod_more', O['EVT_CLICK']), ('pod_back', O['EVT_CLICK']), ('pod_tape', O['EVT_CLICK']), ('pod_vinyl', O['EVT_CLICK']), ('pod_goep', O['EVT_CLICK']),  ('pod_art', O['EVT_CLICK']), ('pod_sleep', O['EVT_CLICK']), ('playmore_dialog', O['EVT_DESTROY']), ('playmore_listview', O['EVT_WINDOW_TO_BG']),
                                        ('listitem4', O['EVT_CLICK']), ('listitem5', O['EVT_CLICK']), ('listitem6', O['EVT_CLICK'])]),
           f'the hook adds the More, back, Tape, Vinyl, Find Cover & Lyrics and Sleep Timer clicks, the Look up album, artist and Delete clicks, the destroy and the to-background handlers and nothing else ({m.added()})')
    expect(not any(c[0] in ('widget_off_by_func',) for c in m.calls), 'no stock handler is taken off')

    # -- 2. hit tests on page 1: a touch reaches the row that is drawn there, a hidden row never takes it -----------------------
    m = PM(); m.open(); m.relayout_all()
    for pos, i in enumerate(PAGE1):
        path = m.tap_row(i)
        expect(path[:3] == ['playmore_dialog', 'playmore_listview', 'playmore_scrollview'] and path[3] == ROWS[i], f'page 1: a tap on row {pos} lands on {ROWS[i]} ({path})')
    above = m.hit(160, SHEET_Y - 1)
    expect(not any(n.startswith(('listitem', 'pod_')) for n in above) and m.hit(160, SHEET_Y)[-1] == 'listitem4' and m.hit(160, SCREEN_H - 1)[-1] == 'pod_more',
           f'page 1: the sheet starts at y {SHEET_Y} and reaches the bottom edge; one pixel above it there is no row to hit ({above})')
    for i in HIDDEN1:
        r = m.rows[i]
        expect(m.s32(r + 4) >= 300 and m.dead(i), f'page 1: the hidden {ROWS[i]} is parked below its page, invisible and insensitive ({m.s32(r + 4)})')
    for y in range(SHEET_Y + 2, SCREEN_H, 7):
        h = m.hit(160, y)
        expect(not h[-1].endswith('!'), f'page 1: a touch at y {y} never lands on an insensitive widget ({h})')
    # the speed badges and the A-B switch are not reachable on page 1
    for x in (166, 206, 246, 286, 270):
        for pos in range(5):
            expect(not any(n.startswith('img_') for n in m.hit(x, SHEET_Y + 25 + 50 * pos)), f'page 1: no speed badge or switch at x {x}, row {pos}')

    # -- 3. page 2 and back ---------------------------------------------------------------------------------------------------------
    m = PM(); m.open(); m.relayout_all()
    m.click_more()
    expect(m.shown() == PAGE2, f'page 2: the back header, Playback speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete ({m.shown()})')
    expect(m.ys() == [0, 50, 100, 150, 200, 250] and set(m.hs()) == {ROW_H}, f'page 2: the rows at 0, 50, 100, 150, 200, 250, {ROW_H} high ({m.ys()} {m.hs()})')
    expect(all(m.live(i) for i in PAGE2) and all(m.dead(i) for i in HIDDEN2), 'page 2: six rows live, the other eight (Online search, Cassette and Vinyl Mode included) neither visible nor sensitive')
    expect(m.stacked()[:6] == PAGE2 and sorted(m.stacked()[6:]) == HIDDEN2, f'page 2: stacked in that order, the hidden rows last ({m.stacked()})')
    expect(m.size(m.dialog) == (320, 300) and m.size(m.lv) == (320, 300) and m.size(m.sv) == (310, 300) and m.size(m.bar) == (10, 300) and m.vh() == 300 and m.size(m.glass) == (320, 300),
           f'page 2: the sheet is 6 rows tall, 300 px ({m.size(m.dialog)})')
    expect(('image_base_set_image', m.nodes['pod_glass'], 'pm_sheet6') == [c for c in m.calls if c[0] == 'image_base_set_image'][-1], 'page 2: the glass is pm_sheet6 (300 px, as page 1\'s)')
    expect(m.top() == SHEET2_Y == SHEET_Y == 180 and m.top() + m.size(m.dialog)[1] == SCREEN_H, 'page 2: the sheet is on the bottom of the screen (its top edge is page 1\'s)')
    expect(all(m.s32(m.rows[i] + 4) >= 300 for i in HIDDEN2), 'page 2: the hidden rows are parked below the sheet')
    m.relayout_all()
    expect(m.shown() == PAGE2 and m.ys() == [0, 50, 100, 150, 200, 250] and set(m.hs()) == {ROW_H} and m.vh() == 300 and m.yoff() == 0 and m.stacked()[:6] == PAGE2,
           f'page 2: a relayout keeps the order, the rows {ROW_H} high and the height ({m.shown()}, {m.hs()})')
    m.relayout_all(); m.mark(); m.relayout_all()
    expect(m.shown() == PAGE2 and m.stacked()[:6] == PAGE2, 'page 2: further relayouts change nothing')
    for pos, i in enumerate(PAGE2):
        path = m.tap_row(i)
        expect(path[3] == ROWS[i], f'page 2: a tap on row {pos} lands on {ROWS[i]} ({path})')
    badges = [m.hit(x, SHEET2_Y + 50 + 25)[-1] for x in (166, 206, 246, 286)]
    expect(badges == ['img_1x', 'img_1_25x', 'img_1_5x', 'img_2x'], f'page 2: the four speed badges are the touch targets in the Playback speed row ({badges})')
    ab_path = m.hit(270, SHEET2_Y + 150 + 25)
    expect(ab_path[-1] == 'img_switch' or ab_path[-1] == 'listitem0', f'page 2: the A-B repeat row takes the touch ({ab_path})')
    for pos in range(6):   # the page 1 rows are not reachable on page 2
        expect(not any(n in ('listitem2', 'listitem4', 'listitem5', 'pod_more', 'pod_tape', 'pod_vinyl') for n in m.hit(160, SHEET2_Y + 25 + 50 * pos)), f'page 2: row {pos} does not reach a page 1 row')
    expect(all(not m.hit(160, y)[-1].endswith('!') for y in range(SHEET2_Y + 2, SCREEN_H, 7)), 'page 2: no touch lands on a hidden widget')
    expect(not any(n in ROWS for n in m.hit(160, SHEET2_Y - 1)), f'page 2: one pixel above the sheet there is no row ({m.hit(160, SHEET2_Y - 1)})')
    expect(m.stock_kept(), 'page 2: the stock handlers are still bound')
    expect(m.handlers_of(m.rows[DELETE], O['EVT_CLICK'])[0][0] == STOCK_CLICK['listitem6'], 'page 2: Delete keeps the stock delete handler (it asks for confirmation), ours after it')
    m.click_back()
    expect(m.shown() == PAGE1 and m.size(m.dialog) == (320, 300) and m.top() == SHEET_Y and m.vh() == 300 and m.size(m.glass) == (320, 300) and all(m.dead(i) for i in HIDDEN1),
           f'the back header returns to page 1: six rows, the sheet taller again, with its own glass ({m.shown()}, {m.size(m.dialog)}, y {m.top()})')
    expect([c for c in m.calls if c[0] == 'image_base_set_image'][-1] == ('image_base_set_image', m.nodes['pod_glass'], 'pm_sheet6') and m.stacked()[:6] == PAGE1 and all(m.states.get(m.rows[i]) == 'normal' for i in (MORE, BACK)), 'page 1 again: stacked in order, the tapped rows back in their normal state')
    m.relayout_all()
    expect(m.shown() == PAGE1 and m.ys() == [0, 50, 100, 150, 200, 250] and m.stacked()[:6] == PAGE1, 'page 1 again: a relayout keeps the order')
    for _ in range(3): m.click_more(); m.click_back()
    expect(m.shown() == PAGE1 and m.vh() == 300 and m.top() == SHEET_Y, 'switching pages repeatedly ends where it began')
    m.click_more(); m.mark(); m.relayout(); m.sync()
    expect(m.shown() == PAGE2 and m.stacked()[:6] == PAGE2, 'a relayout while on page 2 (the Delete confirm opening over the dialog) keeps the rows, stacked in y order for the list_view paint hook')

    # -- 4. tap above the sheet closes it (the stock handler, on the new y); a tap on the sheet does not -----------------------------
    def up(m, y):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e, O['EVT_POINTER_UP']); m.setword(e + 0x1c, y)
        fn, c = m.bound[(m.dialog, O['EVT_POINTER_UP'])]
        m.call(fn, a0=c, a1=e, count=200000)
        return [x for x in m.calls if x[0] == 'window_close']
    for page in (1, 2):
        m = PM(); m.open()
        if page == 2: m.click_more()
        sy = SHEET2_Y if page == 2 else SHEET_Y
        expect(m.bound[(m.dialog, O['EVT_POINTER_UP'])] == (STOCK_UP, m.dialog), f'page {page}: the tap handler is still the stock one')
        expect(up(m, sy - 1) == [('window_close', m.dialog)] and up(m, 0) == [('window_close', m.dialog)] and up(m, 130) == [('window_close', m.dialog)],
               f'page {page}: a tap above the sheet (y < {sy}) closes the dialog')
        expect(up(m, sy) == [] and up(m, sy + 20) == [] and up(m, SCREEN_H - 1) == [], f'page {page}: a tap on the sheet does not')

    # -- 5. another dialog opens over the sheet: the stock handler moves it to y 130, ours (on the list_view, so after it) puts it back --
    for page in (1, 2):
        m = PM(); m.open()
        if page == 2: m.click_more()
        ran = m.window_event(O['EVT_WINDOW_TO_BG'])
        expect([(n, fn) for n, fn, _ in ran] == [('playmore_dialog', STOCK_BG), ('playmore_listview', PSYMS['pm_on_bg'])],
               f'page {page}: the stock to-background handler runs first (on the dialog), ours after it (on the list_view) ({[(n, hex(f)) for n, f, _ in ran]})')
        sy = SHEET2_Y if page == 2 else SHEET_Y
        expect([y for _, _, y in ran] == [DIALOG_Y, sy], f'page {page}: the stock one moves the sheet to y {DIALOG_Y}, ours back to {sy} ({[y for _, _, y in ran]})')
        stock_alone = PM(); stock_alone.stock_init(); stock_alone.window_event(O['EVT_WINDOW_TO_BG'])
        expect(stock_alone.top() == DIALOG_Y and stock_alone.reg == stock_alone.stock_reg, f'page {page}: the stock handler alone moves the dialog to y {DIALOG_Y} (what the hook has to undo)')
        on_dialog = PM(); on_dialog.open(); on_dialog.reg = [(on_dialog.dialog if (w, e) == (on_dialog.lv, O['EVT_WINDOW_TO_BG']) else w, e, fn, c) for w, e, fn, c in on_dialog.reg]
        on_dialog.window_event(O['EVT_WINDOW_TO_BG'])
        expect(on_dialog.top() == DIALOG_Y, f'page {page}: the same handler bound on the dialog would run before the stock one and the sheet would stay at y {DIALOG_Y} (the V2.1nN bug)')
        expect(m.top() == sy and m.size(m.dialog) == (320, SCREEN_H - sy) and m.size(m.glass) == (320, SCREEN_H - sy), f'page {page}: after both, the sheet is on the bottom again ({m.top()})')
        expect(m.shown() == (PAGE2 if page == 2 else PAGE1), f'page {page}: the rows have not moved')
        m.relayout_all()
        expect(m.top() == sy and m.shown() == (PAGE2 if page == 2 else PAGE1), f'page {page}: and a relayout keeps it')

    # -- 6. the end of the dialog, and a new one --------------------------------------------------------------------------------
    m = PM(); m.open(); m.click_more()
    fn, c = m.bound[(m.dialog, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=200000)
    m.sync(); before = m.shown(); top = m.top()
    for w, e in ((m.rows[MORE], O['EVT_CLICK']), (m.rows[BACK], O['EVT_CLICK']), (m.rows[TAPE], O['EVT_CLICK']), (m.rows[VINYL], O['EVT_CLICK']), (m.lv, O['EVT_WINDOW_TO_BG'])):
        fnm, cm = m.handlers_of(w, e)[-1]
        m.call(fnm, a0=cm, a1=0, count=400000)
        expect(m.shown() == before and m.top() == top and not any(c_[0] in ('widget_move', 'widget_resize') for c_ in m.calls), f'after the destroy the {m.name(w)} handler ({e:#x}) finds no dialog of ours and touches nothing')
    m2 = PM(); m2.open(); m2.click_more(); m2.open()
    expect(m2.shown() == PAGE1 and m2.size(m2.dialog) == (320, 300) and m2.top() == SHEET_Y, 'a dialog opened again starts on page 1')
    stale = PM(); stale.open(); stale.click_more()
    other = stale.alloc(0x80); stale.call(fn, a0=other, a1=0, count=200000)
    stale.click_back()
    expect(stale.shown() == PAGE1, 'the destroy of another dialog leaves the state alone')

    # -- 7. failures: the stock menu ------------------------------------------------------------------------------
    def untouched(m, what, inert=True):
        moves = [c for c in m.calls if c[0] in ('widget_move', 'widget_resize', 'widget_restack', 'widget_set_visible', 'widget_set_sensitive', 'image_base_set_image')]
        expect(m.shown() == list(range(7)) and m.stacked()[:7] == list(range(7)) and all(m.dead(i) for i in (MORE, BACK, TAPE, VINYL, GOEP, ART)) and m.size(m.dialog) == (320, 350) and m.top() == DIALOG_Y and not moves,
               f'{what}: the stock menu, nothing moved ({m.shown()}, {m.size(m.dialog)}, y {m.top()}, {moves[:2]})')
        expect(m.stock_kept(), f'{what}: the stock handlers are bound')
        if inert:   # whatever handler the failed start left behind does nothing
            for w, e, fn, c in m.reg[len(m.stock_reg):]:
                m.call(fn, a0=c, a1=0, count=400000)
                expect(not any(x[0] in ('widget_move', 'widget_resize', 'widget_set_visible') for x in m.calls) and m.top() == DIALOG_Y, f'{what}: its leftover {m.name(w)} handler {e:#x} calls nothing')
    m = PM(); m.init_ret = 0x10; ret = m.open()
    untouched(m, 'stock init failed'); expect(ret == 0x10 and m.names() == ['stock_playmore_resume'], 'a failed stock init: its result, nothing else')
    m = PM(); m.call(PSYMS['m1plus_playmore_init'], a0=0, a1=0, count=200000)
    expect(m.names() == ['stock_playmore_resume'], 'no dialog: nothing but the stock init')
    for missing in ('pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep', 'pod_more_label', 'pod_back_label', 'pod_tape_label', 'pod_vinyl_label', 'pod_goep_label', 'pod_art_label', 'pod_sleep_label', 'scrlabel1', 'label1_msg', 'playmore_listview', 'playmore_scrollview', 'scroll_bar_m', 'listitem3'):
        m = PM(); del m.widgets[missing]; m.open(); untouched(m, f'no {missing}')
    m = PM(); m.setword(m.rows[SEARCH] + 0x44, m.lv); m.open(); untouched(m, 'a row outside the scroll_view')
    m = PM(); m.kids(m.sv, m.rows[:7]); m.open(); untouched(m, 'seven rows in the scroll_view (an asset without pod_more)')
    m = PM(); m.kids(m.sv, m.rows[:8]); m.open(); untouched(m, 'eight rows in the scroll_view (an asset without pod_back)')
    m = PM(); m.kids(m.sv, m.rows[:9]); m.open(); untouched(m, 'nine rows in the scroll_view (an asset without pod_tape)')
    m = PM(); m.kids(m.sv, m.rows[:10]); m.open(); untouched(m, 'ten rows in the scroll_view (an asset without pod_vinyl)')
    m = PM(); m.kids(m.sv, m.rows[:12]); m.open(); untouched(m, 'twelve rows in the scroll_view (an asset without pod_art)')
    m = PM(); m.kids(m.sv, m.rows[:13]); m.open(); untouched(m, 'thirteen rows in the scroll_view (an asset without pod_sleep)')
    m = PM(); m.kids(m.sv, m.rows + [m.alloc(0x80)]); m.open(); untouched(m, 'fifteen children in the scroll_view')
    for key in list(PM_TEXTS) + ['powerm_sleep']:
        m = PM(); m.tr_fail = {key}; m.open(); untouched(m, f'the text {key!r} cannot be set')
    for which in ('pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep', 'bg', 'destroy'):
        m = PM(); m.bind_fail = which; m.open(); untouched(m, f'the {which} handler cannot be bound')
    m = PM(); m.bind_fail = 'pod_back'; m.open()
    fn, c = m.bound[(m.dialog, O['EVT_DESTROY'])]      # the destroy handler a failed start left behind does nothing
    m.call(fn, a0=c, a1=0, count=200000)
    expect(m.names() == [], 'a failed start leaves nothing to clean up: its destroy handler calls nothing')

    # -- 7a. the Tape row (patch/playmore.c pm_on_tape): the page opens first, the sheet closes once it is up, a page that will not open leaves the sheet as it was
    m = PM(); m.open()
    expect(m.handlers_of(m.rows[TAPE], O['EVT_CLICK']) == [(PSYMS['pm_on_tape'], m.dialog)] and m.bound[(m.rows[TAPE], O['EVT_CLICK'])][0] == PSYMS['pm_on_tape'], 'the Cassette Mode row has our click handler alone (it has no stock one)')
    m.calls = []; m.click_row(TAPE)
    names = [c[0] for c in m.calls]
    expect(names == ['tape_open', 'window_close'] and ('window_close', m.dialog) in m.calls, f'a tap on Cassette Mode opens the page, then closes the sheet ({names})')
    m = PM(); m.open(); m.tape_ret = -1; m.calls = []; m.click_row(TAPE)
    expect([c[0] for c in m.calls] == ['tape_open'] and m.shown() == PAGE1 and m.top() == SHEET_Y and m.size(m.dialog) == (320, 300),
           'a page that will not open: the sheet stays as it was, on page 1, nothing closed')
    m = PM(); m.open(); m.calls = []
    stale = m.alloc(0x80); m.call(PSYMS['pm_on_tape'], a0=stale, a1=0, count=100000)
    expect('tape_open' not in [c[0] for c in m.calls], 'a click handler left behind for another dialog does nothing')
    # the Vinyl row (pm_on_vinyl): the same order, the page first
    m = PM(); m.open()
    expect(m.handlers_of(m.rows[VINYL], O['EVT_CLICK']) == [(PSYMS['pm_on_vinyl'], m.dialog)], 'the Vinyl Mode row has our click handler alone (it has no stock one)')
    m.calls = []; m.click_row(VINYL)
    names = [c[0] for c in m.calls]
    expect(names == ['vinyl_open', 'window_close'] and ('window_close', m.dialog) in m.calls, f'a tap on Vinyl Mode opens the page, then closes the sheet ({names})')
    m = PM(); m.open(); m.vinyl_ret = -1; m.calls = []; m.click_row(VINYL)
    expect([c[0] for c in m.calls] == ['vinyl_open'] and m.shown() == PAGE1 and m.top() == SHEET_Y and m.size(m.dialog) == (320, 300),
           'Vinyl: a page that will not open leaves the sheet as it was, on page 1, nothing closed')
    m = PM(); m.open(); m.calls = []
    stale = m.alloc(0x80); m.call(PSYMS['pm_on_vinyl'], a0=stale, a1=0, count=100000)
    expect('vinyl_open' not in [c[0] for c in m.calls], 'a Vinyl click handler left behind for another dialog does nothing')
    # Find Cover & Lyrics (pm_on_art, page 2, between A-B repeat and Delete): the page first, the sheet closed once it is up; dimmed and insensitive while the Wi-Fi is off
    m = PM(); m.open()
    expect(m.handlers_of(m.rows[ART], O['EVT_CLICK']) == [(PSYMS['pm_on_art'], m.dialog)] and m.dead(ART), 'the Find Cover & Lyrics row has our click handler alone; on page 1 it is hidden and insensitive')
    m.click_more()
    expect(m.live(ART) and 'pod_art' in m.tap_row(ART), f'page 2: with the Wi-Fi on the row is live and a touch on it reaches it ({m.tap_row(ART)})')
    expect(m.props.get((m.rows[ART], 'opacity')) == 255, 'at full opacity')
    m.calls = []; m.click_row(ART)
    names = [c[0] for c in m.calls]
    expect(names == ['get_wifisignal', 'onlineart_open', 'window_close'] and ('window_close', m.dialog) in m.calls, f'a tap opens the page, then closes the sheet ({names})')
    m = PM(); m.open(); m.click_more(); m.art_ret = -1; m.calls = []; m.click_row(ART)
    expect([c[0] for c in m.calls] == ['get_wifisignal', 'onlineart_open'] and m.shown() == PAGE2 and m.top() == SHEET2_Y and m.size(m.dialog) == (320, 300),
           'a page that will not open leaves the sheet as it was, on page 2, nothing closed')
    m = PM(); m.wifi = -1; m.open(); m.calls = []; m.click_more()
    dim = [c for c in m.calls if c[0] == 'widget_set_opacity' and c[1] == m.rows[ART]]
    expect(dim == [('widget_set_opacity', m.rows[ART], 100)] and m.shown() == PAGE2 and not m.live(ART) and (m.flags(m.rows[ART]) & F_VISIBLE),
           f'Wi-Fi off: page 2 shows the row dimmed (opacity 100 of 255) and insensitive ({dim})')
    expect('pod_art' not in m.tap_row(ART), f'a touch on the dimmed row does not reach it ({m.tap_row(ART)})')
    m.calls = []; m.call(PSYMS['pm_on_art'], a0=m.dialog, a1=0, count=100000)
    expect('onlineart_open' not in [c[0] for c in m.calls] and ('window_close', m.dialog) not in m.calls, 'a click handler that still runs with the Wi-Fi off (a connection lost since the sheet opened) opens nothing')
    m.wifi = 4; m.click_back(); m.click_more()
    expect(m.live(ART), 'the Wi-Fi back: page 2 looked at again, the row is live')
    m = PM(); m.open(); m.click_more(); m.wifi = -1; m.click_back(); m.click_more()
    expect(not m.live(ART) and m.flags(m.rows[ART]) & F_VISIBLE, 'the Wi-Fi is looked at each time page 2 shows (lost while on page 1: dimmed on the next visit)')
    m = PM(); m.open(); m.calls = []
    stale = m.alloc(0x80); m.call(PSYMS['pm_on_art'], a0=stale, a1=0, count=100000)
    expect('onlineart_open' not in [c[0] for c in m.calls], 'a Find Cover & Lyrics click handler left behind for another dialog does nothing')

    # Sleep Timer (pm_on_sleep, page 2, under Playback speed): the stock Power page by a plain navigator_to, the page first, the sheet closed once it is up
    m = PM(); m.open()
    expect(m.handlers_of(m.rows[SLEEP], O['EVT_CLICK']) == [(PSYMS['pm_on_sleep'], m.dialog)] and m.dead(SLEEP) and ('widget_set_tr_text', m.nodes['pod_sleep_label'], 'powerm_sleep') in m.calls,
           'the Sleep Timer row has our click handler alone, the stock key powerm_sleep as its label; on page 1 it is hidden and insensitive')
    m.click_more()
    expect(m.live(SLEEP) and 'pod_sleep' in m.tap_row(SLEEP) and m.shown()[2] == SLEEP, f'page 2: Sleep Timer is the third row, live, and a touch on it reaches it ({m.tap_row(SLEEP)})')
    m.calls = []; m.click_row(SLEEP)
    expect([c[0] for c in m.calls] == ['navigator_to', 'window_close'] and m.calls[0] == ('navigator_to', 'systemset/powermanager_page') and ('window_close', m.dialog) in m.calls,
           f'a tap opens the stock Power page, then closes the sheet ({m.calls})')
    m = PM(); m.open(); m.click_more(); m.nav_ret = 1; m.calls = []; m.click_row(SLEEP)
    expect([c[0] for c in m.calls] == ['navigator_to'] and m.shown() == PAGE2 and m.top() == SHEET2_Y and m.size(m.dialog) == (320, 300),
           'a page that will not open leaves the sheet as it was, on page 2, nothing closed')
    # the window stack the way the device keeps it: navigator_to always adds a window, the to-player button restacks the player and leaves the Power page under it
    def sleep_from_player(m):
        """Now Playing on top, the More sheet open on page 2, a tap on Sleep Timer."""
        m.calls = []; m.click_more(); m.click_row(SLEEP); return [c for c in m.calls if c[0] in ('navigator_to', 'switch_to', 'to_fg', 'fg_refresh', 'stock_power_refresh', 'window_close')]
    m = PM(); m.page('home_page'); m.page('playing_page'); m.open()
    for cycle in range(5):
        calls = sleep_from_player(m)
        want = [('navigator_to', 'systemset/powermanager_page'), ('window_close', m.dialog)] if cycle == 0 else [('switch_to', 'powermanager_page', 0), ('to_fg', 'powermanager_page'), ('fg_refresh', 'powermanager_page'), ('window_close', m.dialog)]
        expect(calls == want and m.stack_names().count('powermanager_page') == 1 and m.stack_names()[-1] == 'powermanager_page',
               f'Sleep Timer cycle {cycle + 1}: {"a new Power window" if cycle == 0 else "the Power window in the stack restacked, refreshed by its own stock foreground handler"}, then the sheet closed, no direct refresh call from us; one Power window, on top ({calls}, {m.stack_names()})')
        m.to_player()
        expect(m.stack_names() == ['home_page', 'powermanager_page', 'playing_page'], f'the to-player button leaves the Power page under the player ({m.stack_names()})')
        m.open()    # the next More sheet over Now Playing
    expect(m.stack_names().count('powermanager_page') == 1 and len(m.navs) == 3, f'five cycles: still exactly one Power window ({m.stack_names()})')
    # Back from the restacked page: stock's btn_return0 stores the time and calls navigator_back (pops the top window): the player is below the Power page again
    m = PM(); m.page('home_page'); m.page('playing_page'); m.open(); sleep_from_player(m); m.to_player(); m.open(); sleep_from_player(m)
    expect(m.stack_names() == ['home_page', 'playing_page', 'powermanager_page'], f'a restacked Power page sits directly over the player, so Back (stock pops the top window) lands on Now Playing ({m.stack_names()})')
    # Power already in the stack under other windows, and not at the top: restacked from wherever it is
    m = PM(); m.page('home_page'); m.page('powermanager_page'); m.page('playing_page'); m.page('m1plus_lyrics'); m.open(); calls = sleep_from_player(m)
    expect(calls == [('switch_to', 'powermanager_page', 0), ('to_fg', 'powermanager_page'), ('fg_refresh', 'powermanager_page'), ('window_close', m.dialog)] and m.stack_names() == ['home_page', 'playing_page', 'm1plus_lyrics', 'powermanager_page'],
           f'a Power window already in the stack is reused, whatever lies above it ({calls}, {m.stack_names()})')
    # the restack fails: stock's open instead, still a closed sheet; the lookup finds a closing window: the same; the lookup finds nothing: stock's open
    m = PM(); m.page('playing_page'); m.page('powermanager_page'); m.page('playing_page'); m.open(); m.switch_fail = True; calls = sleep_from_player(m)
    expect([c[0] for c in calls] == ['switch_to', 'navigator_to', 'window_close'],
           f'a failed restack falls back to stock navigator_to and closes the sheet once it is up, no foreground event, no refresh ({calls})')
    m = PM(); m.page('powermanager_page'); m.page('playing_page'); m.open(); m.closing.add(m.navs[0][1]); calls = sleep_from_player(m)
    expect([c[0] for c in calls] == ['navigator_to', 'window_close'], f'a Power window that is closing is not restacked ({calls})')
    m = PM(); m.page('playing_page'); m.open(); m.no_wm = True; calls = sleep_from_player(m)
    expect([c[0] for c in calls] == ['navigator_to', 'window_close'], f'no window manager: stock navigator_to ({calls})')
    m = PM(); m.page('playing_page'); m.page('powermanager_page'); m.page('playing_page'); m.open(); m.switch_fail = True; m.nav_ret = 1; calls = sleep_from_player(m)
    expect([c[0] for c in calls] == ['switch_to', 'navigator_to'] and m.shown() == PAGE2 and m.size(m.dialog) == (320, 300),
           f'a failed restack and a refused page leave the sheet as it was ({calls})')
    m = PM(); m.open(); m.click_more(); m.wifi = -1; m.click_back(); m.click_more()
    expect(m.live(SLEEP), 'Sleep Timer needs no Wi-Fi: live with the Wi-Fi off')
    m = PM(); m.open(); m.calls = []
    stale = m.alloc(0x80); m.call(PSYMS['pm_on_sleep'], a0=stale, a1=0, count=100000)
    expect('navigator_to' not in [c[0] for c in m.calls], 'a Sleep Timer click handler left behind for another dialog does nothing')

    # -- 7c. an episode is playing: page 1 is Go to Podcasts and More (patch/playmore.c pm_set, pm_on_goep) ------------------------------
    EP = '/mnt/mmc/Podcasts/Show One/ep1.mp3'
    def ep_sheet(path=EP):
        m = PM(); m.play([m.record(path=path)], 0); m.open()
        return m
    m = ep_sheet(); img = [c for c in m.calls if c[0] == 'image_base_set_image']
    expect(m.shown() == PAGE_EP and all(m.live(i) for i in PAGE_EP) and all(m.dead(i) for i in HIDDEN_EP),
           f'episode: page 1 shows Go to Podcasts and More; Look up album, Look up artist, Add to playlist, Cassette Mode and Vinyl Mode are hidden and insensitive ({m.shown()})')
    expect(m.ys() == [0, 50] and set(m.hs()) == {ROW_H} and m.stacked()[:2] == PAGE_EP and sorted(m.stacked()[2:]) == HIDDEN_EP,
           f'episode: the rows close up at 0 and 50, the usual row pitch, the hidden ones stacked last ({m.ys()}, {m.stacked()})')
    expect(m.size(m.dialog) == (320, 100) and m.size(m.lv) == (320, 100) and m.size(m.sv) == (310, 100) and m.size(m.bar) == (10, 100) and m.vh() == 100 and m.size(m.glass) == (320, 100)
           and m.top() == SCREEN_H - 100 and img[-1] == ('image_base_set_image', m.glass, 'pc_sheet2'),
           f'episode: the sheet is two rows, 100 px, on the bottom of the screen, with the Podcasts page\'s 100 px glass ({m.size(m.dialog)}, y {m.top()})')
    m.relayout_all()
    for pos, i in enumerate(PAGE_EP):
        path = m.tap_row(i)
        expect(path[:3] == ['playmore_dialog', 'playmore_listview', 'playmore_scrollview'] and path[3] == ROWS[i], f'episode: a tap on row {pos} lands on {ROWS[i]} ({path})')
    expect(m.hit(160, SCREEN_H - 100 - 25) == ['playmore_dialog'] or 'pod_tape' not in m.hit(160, SCREEN_H - 125), 'episode: above the sheet is no row')
    m.window_event(O['EVT_WINDOW_TO_BG'])
    expect(m.top() == SCREEN_H - 100, f'episode: another dialog over the sheet leaves it on the bottom ({m.top()})')
    m.click_more()
    expect(m.shown() == PAGE2 and m.size(m.dialog) == (320, SHEET2_H) and m.top() == SHEET2_Y and [c for c in m.calls if c[0] == 'image_base_set_image'][-1] == ('image_base_set_image', m.glass, 'pm_sheet6'),
           'episode: More opens the same second page as for a song (300 px, the same glass)')
    m.click_back()
    expect(m.shown() == PAGE_EP and m.size(m.dialog) == (320, 100) and m.size(m.glass) == (320, 100) and all(m.dead(i) for i in HIDDEN_EP), 'episode: the back header returns to the episode\'s page 1')
    m = ep_sheet()
    expect(m.handlers_of(m.rows[GOEP], O['EVT_CLICK']) == [(PSYMS['pm_on_goep'], m.dialog)] and ('widget_set_tr_text', m.nodes['pod_goep_label'], 'Go to Podcasts') in m.calls,
           'Go to Podcasts has our click handler alone and its translated text')
    m.calls = []; m.click_row(GOEP)
    calls = [c for c in m.calls if c[0] != 'mclGetPlayPos']
    expect([c[0] for c in calls] == ['podcasts_go', 'window_close'] and ('window_close', m.dialog) in calls,
           f'a tap on Go to Podcasts opens the Podcasts page, then closes the sheet ({m.calls})')
    m = ep_sheet(); m.ep_ret = -1; m.calls = []; m.click_row(GOEP)
    expect([c[0] for c in m.calls if c[0] != 'mclGetPlayPos'] == ['podcasts_go'] and m.shown() == PAGE_EP and m.size(m.dialog) == (320, 100), 'Go to Podcasts: a page that will not open leaves the sheet as it was')
    m = ep_sheet(); m.calls = []
    stale = m.alloc(0x80); m.call(PSYMS['pm_on_goep'], a0=stale, a1=0, count=100000)
    expect('podcasts_go' not in [c[0] for c in m.calls], 'a Go to Podcasts handler left behind for another dialog does nothing')
    m = ep_sheet('/mnt/mmc/podcasts/Show One/EP1.MP3')
    expect(m.shown() == PAGE_EP, 'episode: the Podcasts folder is matched without case')
    for what, path in (('a song', '/mnt/mmc/Music/a/1.flac'), ('a file straight in the Podcasts folder', '/mnt/mmc/Podcasts/loose.mp3'), ('another folder named Podcasts', '/mnt/mmc/Music/Podcasts/Show/ep.mp3')):
        m = ep_sheet(path)
        expect(m.shown() == PAGE1 and all(m.dead(i) for i in HIDDEN1) and m.size(m.dialog) == (320, 300) and m.size(m.glass) == (320, 300), f'{what}: the sheet is the music sheet, six rows, Go to Podcasts hidden')
    m = PM(); m.open()
    expect(m.shown() == PAGE1 and m.dead(GOEP), 'nothing playing: the music sheet')

    # -- 7b. Look up album opens our album page (patch/playmore.c pm_on_lookup_album) -----------------------------------------------
    FLAG, CLICK, DESTROY = pod.DATA['SONGER_FLAG'][0], O['EVT_CLICK'], O['EVT_DESTROY']
    RET_STOP = O['RET_STOP']
    def lib(m, playing='Kind of Blue', albums=('Other', 'KIND OF BLUE', 'Zed'), flag=0, pos=0):
        """An open sheet, the library's albums (and the Unknown Album row, id -1, last), the player on a track of `playing`."""
        m.open()
        rows = [m.record(album=a, rid=i + 1) for i, a in enumerate(albums)] + [m.record(album='Unknown Album', rid=-1)]
        m.class_lists[O['CLASS_ALBUMS']] = rows
        if playing is not None: m.play([m.record(album=playing)], pos)
        m.u.mem_write(FLAG, bytes([flag]))
        m.page('playing_page')
        return rows
    def flag(m): return m.u.mem_read(FLAG, 1)[0]
    def lookup(m):
        """A tap on Look up album: the handler on the row is called with its context, as the emitter does; its result."""
        fn, c = m.bound[(m.rows[GO_ALBUM], CLICK)]
        ret = m.call(fn, a0=c, a1=0, count=4000000); m.sync()
        return ret
    def opened(m): return [c[2:] for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']
    m = PM(); lib(m)
    expect(m.handlers_of(m.rows[GO_ALBUM], CLICK) == [(STOCK_CLICK['listitem4'], m.dialog), (PSYMS['pm_on_lookup_album'], m.dialog)],
           'Look up album: the stock handler first, ours bound after it (so it runs before it)')
    ret = lookup(m)
    expect(ret == RET_STOP and opened(m) == [(O['CLASS_ALBUMS'], 1)], f'Look up album: our album page opens on the playing album\'s row, matched without case (class 0xf003, row 1), the stock handler stopped ({ret}, {opened(m)})')
    names = [c[0] for c in m.calls]
    expect(('window_close', m.dialog) in m.calls and names.index('window_close') < names.index('navigator_to_with_context'), 'Look up album: the sheet is closed before the page opens')
    expect(names.count('albumcoverinfo_init') == 1 and names.count('batchadd_albumcover_task') == 1, 'Look up album: the page is opened as the Albums grid does (cover task list, then the navigator)')
    expect(flag(m) == 1 and [n for n, _ in m.navs] == ['playing_page', 'albuminfo_page'], f'Look up album: songerinfoflag set, the album page on top of Now Playing ({flag(m)}, {[n for n, _ in m.navs]})')
    page = m.navs[-1][1]
    expect(m.bound.get((page, DESTROY), (0,))[0] == PSYMS['pm_on_album_gone'], 'Look up album: the page\'s destroy is watched')
    m.call(*(m.bound[(page, DESTROY)][0],), a0=page, a1=0, count=200000)
    expect(flag(m) == 0, 'the page\'s destroy clears songerinfoflag')
    # an albuminfo_page already in the stack is closed, the flag stays the new page's
    m = PM(); lib(m); old = m.page('albuminfo_page')
    lookup(m)
    expect(('navigator_close', 'albuminfo_page') in m.calls and [n for n, _ in m.navs] == ['playing_page', 'albuminfo_page'] and m.navs[-1][1] != old and opened(m) == [(O['CLASS_ALBUMS'], 1)],
           'an albuminfo_page already open is closed first, then the new one opens')
    new = m.navs[-1][1]
    m.call(m.bound[(new, DESTROY)][0], a0=old, a1=0, count=200000)
    expect(flag(m) == 1, 'the destroy of the older page (it arrives late) leaves the flag of the newer one')
    m.call(m.bound[(new, DESTROY)][0], a0=new, a1=0, count=200000)
    expect(flag(m) == 0, 'the newer page\'s destroy clears it')
    m.call(m.bound[(new, DESTROY)][0], a0=new, a1=0, count=200000); m.u.mem_write(FLAG, bytes([1]))
    m.call(m.bound[(new, DESTROY)][0], a0=new, a1=0, count=200000)
    expect(flag(m) == 1, 'a destroy twice does nothing the second time')
    # a flag that was already set (Look up artist, its album_page still under) stays set
    m = PM(); lib(m, flag=1); lookup(m); page = m.navs[-1][1]
    m.call(m.bound[(page, DESTROY)][0], a0=page, a1=0, count=200000)
    expect(flag(m) == 1, 'a flag set before the tap (an artist page below) is left set when the page ends')
    # two taps in a row with the first page's destroy late: the second page's end restores the byte from before the first
    m = PM(); lib(m); lookup(m); first = m.navs[-1][1]
    lookup(m); second = m.navs[-1][1]
    m.call(m.bound[(second, DESTROY)][0], a0=first, a1=0, count=200000)
    expect(flag(m) == 1, 'two taps: the first page\'s late destroy does not clear the second\'s flag')
    m.call(m.bound[(second, DESTROY)][0], a0=second, a1=0, count=200000)
    expect(flag(m) == 0, 'two taps: the second page\'s destroy restores the byte from before the first')
    # fallbacks: the stock handler runs (RET_OK), nothing changed
    def stock_runs(m, what):
        before = list(m.navs)
        ret = lookup(m)
        gone = [c for c in m.calls if c[0] in ('window_close', 'navigator_close', 'navigator_to_with_context', 'albumcoverinfo_init')]
        expect(ret == 0 and not gone and flag(m) == 0 and m.navs == before, f'{what}: the stock handler runs (RET_OK), nothing closed or opened, the flag unchanged ({ret}, {gone}, {flag(m)})')
    m = PM(); lib(m, playing=None); stock_runs(m, 'nothing playing')
    m = PM(); lib(m, playing=''); stock_runs(m, 'a track with no album')
    m = PM(); lib(m, playing='Not In The Library'); stock_runs(m, 'an album the library list lacks')
    m = PM(); lib(m, playing='Unknown Album'); stock_runs(m, 'the Unknown Album row is never matched')
    m = PM(); lib(m, albums=()); stock_runs(m, 'an empty library')
    m = PM(); lib(m, pos=5); stock_runs(m, 'a play position outside the queue')
    m = PM(); lib(m); m.no_window = True; lookup(m)
    expect(flag(m) == 0 and opened(m) == [(O['CLASS_ALBUMS'], 1)], f'no album page window to watch after the open: the flag is not left set ({flag(m)})')
    m = PM(); lib(m); m.widget_on_fail = frozenset({DESTROY}); ret = lookup(m)
    expect(ret == RET_STOP and flag(m) == 0, f'the destroy watch refused: the page is open and the flag is not left set ({ret}, {flag(m)})')

    # -- 7c. Look up artist opens our Cover Flow artist page (patch/playmore.c pm_on_lookup_artist) ------------------------------------
    CLS_ART = O['CLASS_ARTISTS']
    def alib(m, playing='Miles Davis', artists=('Other', 'MILES DAVIS', 'Zed'), flag=0, pos=0):
        """An open sheet, the library's artists (and the Unknown Artist row, id -1, last), the player on a track by `playing`."""
        m.open()
        rows = [m.record(title=a, rid=i + 1) for i, a in enumerate(artists)] + [m.record(title='Unknown Artist', rid=-1)]
        m.class_lists[CLS_ART] = rows
        if playing is not None: m.play([m.record(artist=playing)], pos)
        m.u.mem_write(FLAG, bytes([flag]))
        m.page('playing_page')
        return rows
    def artist_tap(m):
        fn, c = m.bound[(m.rows[GO_ARTIST], CLICK)]
        ret = m.call(fn, a0=c, a1=0, count=4000000); m.sync()
        return ret
    def cf_calls(m): return [c[1:] for c in m.calls if c[0] == 'albums_open_artist']
    m = PM(); alib(m)
    expect(m.handlers_of(m.rows[GO_ARTIST], CLICK) == [(STOCK_CLICK['listitem5'], m.dialog), (PSYMS['pm_on_lookup_artist'], m.dialog)],
           'Look up artist: the stock handler first, ours bound after it (so it runs before it)')
    ret = artist_tap(m)
    expect(ret == RET_STOP and cf_calls(m) == [(('MILES DAVIS',), 0, CLS_ART)],
           f'Look up artist: our scoped Albums page opens on the playing artist\'s row, matched without case, scope CLASS_ARTISTS, the stock handler stopped ({ret}, {cf_calls(m)})')
    names = [c[0] for c in m.calls]
    expect(('loadLocalClassList', CLS_ART) in m.calls, 'Look up artist: the list is the stock Artists list (getAllArtist / album artist as the setting says)')
    expect(('window_close', m.dialog) in m.calls and names.index('window_close') > names.index('albums_open_artist'), 'Look up artist: the page opens first, the sheet closes after')
    expect('deque_destroy' in names and 'navigator_to_with_context' not in names, 'Look up artist: the one-row carrier list is freed, no stock page is opened')
    expect(flag(m) == 1 and [n for n, _ in m.navs] == ['playing_page', 'm1plus_albums'], f'Look up artist: songerinfoflag set, the artist\'s Albums page on top of Now Playing ({flag(m)}, {[n for n, _ in m.navs]})')
    page = m.navs[-1][1]
    expect(m.bound.get((page, DESTROY), (0,))[0] == PSYMS['pm_on_album_gone'], 'Look up artist: the page\'s destroy is watched')
    m.call(m.bound[(page, DESTROY)][0], a0=page, a1=0, count=200000)
    expect(flag(m) == 0, 'the artist page\'s destroy clears songerinfoflag')
    m = PM(); alib(m); old = m.page('albuminfo_page'); artist_tap(m)
    expect(('navigator_close', 'albuminfo_page') in m.calls and 'albuminfo_page' not in [n for n, _ in m.navs], 'an albuminfo_page already open is closed')
    m = PM(); alib(m, flag=1); artist_tap(m); page = m.navs[-1][1]
    m.call(m.bound[(page, DESTROY)][0], a0=page, a1=0, count=200000)
    expect(flag(m) == 1, 'a flag set before the tap is left set when the page ends')
    def stock_runs_a(m, what):
        before = list(m.navs)
        ret = artist_tap(m)
        gone = [c for c in m.calls if c[0] in ('window_close', 'navigator_close', 'navigator_to_with_context')]
        expect(ret == 0 and not gone and flag(m) == 0 and m.navs == before, f'{what}: the stock handler runs (RET_OK), nothing closed or opened, the flag unchanged ({ret}, {gone}, {flag(m)})')
    m = PM(); alib(m, playing=None); stock_runs_a(m, 'artist: nothing playing')
    m = PM(); alib(m, playing=''); stock_runs_a(m, 'artist: a track with no artist')
    m = PM(); alib(m, playing='Nobody'); stock_runs_a(m, 'artist: an artist the list lacks (e.g. album artist mode)')
    m = PM(); alib(m, playing='Unknown Artist'); stock_runs_a(m, 'artist: the Unknown Artist row is never matched')
    m = PM(); alib(m, artists=()); stock_runs_a(m, 'artist: an empty library')
    m = PM(); alib(m, pos=5); stock_runs_a(m, 'artist: a play position outside the queue')
    m = PM(); alib(m); m.am_ret = -1; m.cf_ret = -1; stock_runs_a(m, 'artist: neither the Albums page nor Cover Flow opens')
    m = PM(); alib(m); m.am_ret = -2; stock_runs_a(m, 'artist: the Albums asset is not ours (left again): the stock handler')
    m = PM(); alib(m); m.am_ret = -1; ret = artist_tap(m)
    expect(ret == RET_STOP and [c[0] for c in m.calls if c[0] in ('albums_open_artist', 'coverflow_artist')] == ['albums_open_artist', 'coverflow_artist']
           and [n for n, _ in m.navs] == ['playing_page', 'm1plus_cover'] and flag(m) == 1, 'artist: the Albums window will not open: Cover Flow on the artist, the same flag and sheet handling')
    m = PM(); alib(m); m.no_window = True; ret = artist_tap(m)
    expect(flag(m) == 0 and ret == RET_STOP, f'artist: no window to watch after the open: the flag is not left set ({flag(m)}, {ret})')
    m = PM(); alib(m); m.widget_on_fail = frozenset({DESTROY}); ret = artist_tap(m)
    expect(ret == RET_STOP and flag(m) == 0, f'artist: the destroy watch refused: the page is open and the flag is not left set ({ret}, {flag(m)})')

    # -- 7d. Delete closes the sheet before the stock handler's modal confirm (patch/playmore.c pm_on_delete) -----------------------------
    m = PM(); alib(m)
    expect(m.handlers_of(m.rows[DELETE], CLICK) == [(STOCK_CLICK['listitem6'], m.dialog), (PSYMS['pm_on_delete'], m.dialog)],
           'Delete: the stock handler first in the list, ours bound after it (so ours runs before it, the emitter runs the newest first)')
    fn, c = m.bound[(m.rows[DELETE], CLICK)]
    ret = m.call(fn, a0=c, a1=0, count=200000); m.sync()
    expect(ret == 0 and m.calls.count(('window_close', m.dialog)) == 1 and 'navigator_to_with_context' not in [x[0] for x in m.calls],
           f'Delete: ours closes the sheet and returns RET_OK, so the stock handler (the modal confirm, delete only on Yes) still runs and nothing else opens ({ret})')
    m.calls.clear(); m.call(fn, a0=0x1234, a1=0, count=200000)
    expect(('window_close', m.dialog) not in m.calls, 'Delete: a click handler left behind for another dialog does nothing')
    # the other rows: Add to playlist closes the sheet itself in stock (window_close at 0x47994c, then playlist_page); Speed / A-B open no dialog; none of them gets a handler of ours
    m = PM(); alib(m)
    expect(all(m.handlers_of(m.rows[i], CLICK) == [(STOCK_CLICK[ROWS[i]], m.dialog)] for i in (ADD, AB)), 'Add to playlist and A-B repeat keep the stock handler alone (stock closes the sheet for Add to playlist itself)')

    # -- 8. the texts in every language, and the room they have ------------------------------------------------------------------------
    stock_raw = os.path.join(paths.find_stock(paths.ZIP), RAW)
    built = {f[:-4]: dict(awtk_strings.load(os.path.join(WORK, RAW, 'strings', f))) for f in sorted(os.listdir(os.path.join(WORK, RAW, 'strings')))}
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    th = awtk_style.parse(open(os.path.join(WORK, RAW, 'styles', 'default.bin'), 'rb').read())
    row_px = th.find('hscroll_label', 'srlabel_item_white_style', 'normal')[0].get('font_size')
    tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui/dialog/playmore_dialog.bin'), 'rb').read())
    more_l, back_l, more_c, back_c = (tree.find(n) for n in ('pod_more_label', 'pod_back_label', 'pod_more_chev', 'pod_back_chev'))
    tape_l, vinyl_l, goep_l, art_l, sleep_l, sleep_c = tree.find('pod_tape_label'), tree.find('pod_vinyl_label'), tree.find('pod_goep_label'), tree.find('pod_art_label'), tree.find('pod_sleep_label'), tree.find('pod_sleep_chev')
    speed_l, note_l, badges = tree.find('scrlabel1'), tree.find('label1_msg'), [tree.find(n) for n in ('img_1x', 'img_1_25x', 'img_1_5x', 'img_2x')]
    note_px = int(note_l.get('style:normal:font_size'))
    over = {'more': [], 'speed': [], 'note': [], 'tape': [], 'vinyl': [], 'goep': [], 'art': [], 'sleep': []}
    for loc in pod_i18n.ALL_TABLES:
        for key in PM_TEXTS:
            expect(built[loc][key] == pod_i18n.TEXT[key][pod_i18n.table_for(loc)], f'{loc}: {key!r} is in the table as {pod_i18n.TEXT[key][pod_i18n.table_for(loc)]!r}')
        if loc in pod_i18n.LOCALES:
            w = StbText(font, row_px).layout(built[loc]['More'])[1]
            if more_l.x + w > more_c.x - 8: over['more'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['Speed'])[1]
            if speed_l.x + w > speed_l.x + speed_l.w: over['speed'].append((loc, w))
            w = StbText(font, note_px).layout(built[loc]['Files below 48 kHz only'])[1]
            if note_l.x + w > note_l.x + note_l.w: over['note'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['Cassette Mode'])[1]
            if w > tape_l.w: over['tape'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['Vinyl Mode'])[1]
            if w > vinyl_l.w: over['vinyl'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['Go to Podcasts'])[1]
            if w > goep_l.w: over['goep'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['Cover & Lyrics'])[1]
            if w > art_l.w: over['art'].append((loc, w))
            w = StbText(font, row_px).layout(built[loc]['powerm_sleep'])[1]   # the stock key, the Power page's own row text
            if sleep_l.x + w > sleep_c.x - 8: over['sleep'].append((loc, w))
        m = PM(); m.set_language(loc)
        if loc in pod_i18n.LOCALES: m.strings['powerm_sleep'] = built[loc]['powerm_sleep']   # the stock key is in the stock table, not in pod_i18n.TEXT
        m.open()
        for key, label in (('powerm_sleep', 'pod_sleep_label'), ('More', 'pod_more_label'), ('More', 'pod_back_label'), ('Speed', 'scrlabel1'), ('Files below 48 kHz only', 'label1_msg'), ('Cassette Mode', 'pod_tape_label'), ('Vinyl Mode', 'pod_vinyl_label'), ('Go to Podcasts', 'pod_goep_label'), ('Cover & Lyrics', 'pod_art_label')):
            if key == 'powerm_sleep' and loc not in pod_i18n.LOCALES: continue   # the three CD ripper stubs carry no stock Sleep Timer
            want = (built[loc][key] if key == 'powerm_sleep' else pod_i18n.TEXT[key][pod_i18n.table_for(loc)]).encode('utf-8').decode('latin-1')
            expect(('widget_set_tr_text', m.nodes[label], key) in m.calls and ('widget_set_text_utf8', m.nodes[label], want) in m.calls, f'{loc}: {label} reads {want!r}')
    expect(not over['tape'] and tape_l.w == 200 and tape_l.x == more_l.x, f'"Cassette Mode" fits its {tape_l.w} px label (no chevron) in all 13 languages at {row_px} px ({over["tape"]})')
    expect(not over['vinyl'] and vinyl_l.w == 200 and vinyl_l.x == more_l.x, f'"Vinyl Mode" fits its {vinyl_l.w} px label (no chevron) in all 13 languages at {row_px} px ({over["vinyl"]})')
    expect(not over['goep'] and goep_l.w == 200 and goep_l.x == more_l.x, f'"Go to Podcasts" fits its {goep_l.w} px label in all 13 languages at {row_px} px ({over["goep"]})')
    expect(not over['art'] and art_l.w == 200 and art_l.x == more_l.x, f'"Cover & Lyrics" fits its {art_l.w} px label (no chevron) in all 13 languages at {row_px} px ({over["art"]})')
    expect(not over['sleep'] and sleep_l.w == 200 and sleep_l.x == more_l.x and sleep_c.x == more_c.x, f'"Sleep Timer" (the stock key powerm_sleep, the Power page\'s own text) fits between the label x {sleep_l.x} and the chevron at x {sleep_c.x} in all 13 languages at {row_px} px ({over["sleep"]})')
    expect(not over['more'] and row_px == 20, f'"More" fits between the label x {more_l.x} and the chevron at x {more_c.x} in all 13 languages at {row_px} px ({over["more"]})')
    wide = lambda key, px: max((StbText(font, px).layout(built[l][key])[1], l) for l in pod_i18n.LOCALES)
    expect(not over['speed'] and wide('Speed', row_px)[0] > 40, f'"Speed" fits the {speed_l.w} px label in all 13 languages at {row_px} px (widest {wide("Speed", row_px)}; over: {over["speed"]})')
    expect(not over['note'] and wide('Files below 48 kHz only', note_px)[0] > 80, f'the note fits its {note_l.w} px at {note_px} px in all 13 languages (widest {wide("Files below 48 kHz only", note_px)}; over: {over["note"]})')
    expect(more_l.w == 200 and more_l.x + more_l.w <= more_c.x and back_l.x >= back_c.x + back_c.w, 'the More label ends before its chevron; the back label starts after its chevron')
    expect(speed_l.x + speed_l.w <= badges[0].x and note_l.y >= speed_l.y + speed_l.h and note_l.y >= 8 + 20, 'the speed label ends before the first badge, the note sits under the label and the 20 px badge pictures')
    expect(all(a.x + a.w <= b.x for a, b in zip(badges, badges[1:])) and badges[-1].x + badges[-1].w <= 310 and note_l.x + note_l.w <= 310 and all(b.w == 36 and b.h == 50 and b.y == 0 for b in badges),
           'the four badges (36 px, 50 px high) do not overlap and end inside the 310 px row; the note too')

    # -- 9. the assets ---------------------------------------------------------------------------------------------------
    stock_ui = awtk_ui.parse(open(os.path.join(stock_raw, 'ui/dialog/playmore_dialog.bin'), 'rb').read())
    speed_names = ('scrlabel1', 'label1_msg', 'img_1x', 'img_1_25x', 'img_1_5x', 'img_2x')
    built_ui = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/dialog/playmore_dialog.bin'), 'rb').read())
    geo = lambda t: [(w.type, w.name, w.x, w.y, w.w, w.h) for w in t.walk() if not w.name.startswith(('pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep', 'pod_glass')) and w.name not in speed_names]
    expect(geo(built_ui) == geo(stock_ui), 'every stock widget but the speed row\'s keeps its type, name and rectangle (the M1+ Music ones are added)')
    expect([(w.type, w.name) for w in built_ui.walk() if w.name in speed_names] == [(w.type, w.name) for w in stock_ui.walk() if w.name in speed_names],
           'the speed row\'s widgets keep their type and name')
    expect([(built_ui.find(n).x, built_ui.find(n).y, built_ui.find(n).w, built_ui.find(n).h) for n in speed_names] ==
           [(48, 8, 96, 20), (48, 31, 262, 14), (148, 0, 36, 50), (188, 0, 36, 50), (228, 0, 36, 50), (268, 0, 36, 50)], 'the speed row\'s rectangles')
    sv = built_ui.find('playmore_scrollview')
    expect([c.name for c in sv.children] == STOCK_NAMES + ['pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_goep', 'pod_art', 'pod_sleep'], 'pod_more, pod_back, pod_tape, pod_vinyl, pod_goep, pod_art and pod_sleep are the eighth to fourteenth children of the scroll_view, after the seven stock rows')
    hl = built_ui.get('highlight')
    expect(hl is not None and hl.startswith('default(alpha=') and hl.endswith(')') and 40 <= int(hl[len('default(alpha='):-1]) <= 200, f'the dialog dims the page under it with the "default" highlighter ({hl!r})')
    imgs = {f[:-4] for f in os.listdir(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx'))}
    for name, kids in (('pod_more', ['pod_more_icon', 'pod_more_label', 'pod_more_chev']), ('pod_back', ['pod_back_chev', 'pod_back_label']), ('pod_tape', ['pod_tape_icon', 'pod_tape_label']), ('pod_vinyl', ['pod_vinyl_icon', 'pod_vinyl_label']), ('pod_goep', ['pod_goep_icon', 'pod_goep_label']), ('pod_art', ['pod_art_icon', 'pod_art_label']), ('pod_sleep', ['pod_sleep_icon', 'pod_sleep_label', 'pod_sleep_chev'])):
        row = built_ui.find(name)
        expect(row.type == 'list_item' and row.get('visible') == 'false' and row.get('sensitive') == 'false', f'{name} starts hidden and insensitive')
        expect([c.name for c in row.children] == kids and all(c.get('sensitive') == 'false' for c in row.children if c.type == 'image'), f'{name}\'s children are {kids}, the pictures insensitive')
        expect({c.get('image') for c in row.children if c.type == 'image'} <= imgs, f'the images {name} uses exist')
    expect(built_ui.find('pod_more_chev').get('image') == 'right_arrow' and built_ui.find('pod_back_chev').get('image') == 'return', 'the stock chevrons: right_arrow (grey) for More, return for the back header')
    ref = built_ui.find('listitem2')
    expect([(k, v) for k, v in built_ui.find('pod_more').props if k.startswith('style')] == [(k, v) for k, v in ref.props if k.startswith('style')], 'pod_more is styled as the Add to playlist row')
    diff = [k for k, v in built_ui.find('pod_back').props if k.startswith('style') and (k, v) not in [(a, b) for a, b in ref.props]]
    expect(diff == ['style:normal:border'] or all(k == 'style:normal:border' for k in diff), f'pod_back is styled as the Add to playlist row, but for its hairline ({diff})')
    lab = built_ui.find('scrlabel6')
    reds = {lab.get(f'style:{s}:text_color') for s in ('normal', 'pressed', 'over', 'disable', 'focused')}
    expect(reds == {'#FF5A4F'}, f'the Delete label is red in every state ({reds})')
    glass_checks(expect, built_ui, stock_ui, lum)
    expect(built_ui.find('listitem4').get('style:normal:border') == 'none' and built_ui.find('pod_back').get('style:normal:border') == 'none' and built_ui.find('pod_goep').get('style:normal:border') == 'none' and built_ui.find('listitem0').get('style:normal:border') == 'top'
           and all(built_ui.find(n).get('style:normal:border') == 'top' for n in ('listitem1', 'listitem2', 'listitem3', 'listitem5', 'listitem6', 'pod_more', 'pod_tape', 'pod_vinyl')),
           'the hairlines follow the new order (the first row of each page has none, A-B repeat has one)')
    expect(built_ui.type == 'dialog' and (built_ui.x, built_ui.y, built_ui.w, built_ui.h) == (0, 130, 320, 350),
           'the dialog is the stock 320 x 350 sheet at y 130 (a failed start shows the stock menu)')

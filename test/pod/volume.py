"""The Volume page (patch/volume.c, docs/modules/volume.md): our page for the status bar tap, running stock's own volume dialog code (refresh, - / + / slider / key handlers) on our window.

The payload and stock's handlers run under the emulator: the stock handlers' stores, saves and calls are stock's (the loudness machine of test/pod/playset.py, LM), the window manager is a stack of named windows, and the widgets'
timers are ids a test can let run (stock's 3 s auto-close callback 0x47d630 runs from the stock bytes when it comes due)."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

PS = sibling('playset')
D = pod.DATA
VOLUME, BTVOL, MAXV, HEADSET, SHOWPAGE = (D[n][0] for n in ('G_VOLUME', 'BT_VOLUME', 'MAX_VOLUME', 'HEADSET_OUTPUT', 'VOLP_SHOWPAGE'))
STOCK = {n: D[n][0] for n in ('VOLP_REFRESH', 'VOLP_STOP', 'VOLP_ADD', 'VOLP_DEC', 'VOLP_SLIDER', 'VOLP_KEY')}
NAME, ASSET = 'm1plus_volume_page', 'm1plus_volume'
EVT_CHANGING, EVT_CLICK_, EVT_KEY, EVT_FG, EVT_BG = 0x11d, 0x10c, 0x113, 0x12d, 0x12c
KEY_UP_, KEY_DOWN_, RET_STOP_ = 0xdc, 0xdd, 0xb
TIMER_CB, ADD_TIMER, SLIDER_INTERNAL = 0x47d630, 0x668c78, 0x631570   # stock's auto-close callback, widget_add_timer, slider_set_value_internal (the cap's pull-back)
MINE = {'window_manager_get_top_window', 'window_manager_switch_to', 'window_open', 'window_close', 'navigator_to_with_context', 'widget_is_window_opened', 'widget_on', 'widget_get_prop', 'widget_set_prop', 'value_uint32',
        'timer_count', 'timer_modify', 'widget_remove_timer', 'v_add_timer', 'v_slider_internal'}
WIDGETS = ('btn_return', 'btn_backtoplayer', 'vol_label', 'pod_volnum', 'pod_volinfo', 'vol_slider', 'btn_add', 'btn_dec', 'pod_volbar', 'pod_row0', 'pod_row1', 'pod_row2', 'pod_value0', 'pod_value1')
PAGES_OF = {'m1plus_volume': 'm1plus_volume_page', 'm1plus_psgain': 'm1plus_psgain_page', 'm1plus_psmaxvol': 'm1plus_psmaxvol_page', 'm1plus_peq': 'm1plus_peq_page', 'm1plus_psvolume': 'm1plus_psvolume_page', 'm1plus_settings': 'm1plus_settings_page', 'm1plus_sleeptimer': 'm1plus_sleeptimer_page', 'm1plus_playset': 'm1plus_playset_page', 'm1plus_autoeq': 'm1plus_autoeq_page'}   # the assets the page's rows open, and their windows
IMG = os.path.join('rootfs', 'release/assets/default/raw/images/xx')   # (under WORK)
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_volume.bin')


def art():
    """The bar's four images as the built tree has them (what widget_load_image decodes): name -> (w, h, RGBA bytes)."""
    from PIL import Image
    out = {}
    for n in ('pod_vol_track', 'pod_vol_fill', 'pod_vol_ink', 'pod_ci_volume'):
        im = Image.open(os.path.join(WORK, IMG, n + '.png')).convert('RGBA'); out[n] = (im.width, im.height, im.tobytes())
    return out


class VM(PS.LM):
    """Stock's volume handlers for real, the payload's page over a stack of named windows, widget timers as ids."""

    def __init__(self, stack=('home_page',), open_fail=False, **kw):
        super().__init__(**kw)
        self.stack, self.open_fail, self.win, self.bindings, self.closed = [], open_fail, None, {}, []
        self.active, self.removed, self.next_id, self.fg_pending = {}, [], 21, False
        for a, n in ((ADD_TIMER, 'v_add_timer'), (SLIDER_INTERNAL, 'v_slider_internal')): self.handlers[a] = n
        for n in WIDGETS: self.widget(n)
        self.load_image, self.images = 0, art()   # the bar's four images decode (m1_asset_rgba)
        for n in stack: self.push(n)
        self.screen(True)
        self.timer_info = self.alloc(0x60); self.u.mem_write(self.timer_info, bytes(0x60))

    def push(self, name, opener=None):
        """A window on top. opener: the name of the window it was opened from (a row tap on that page): recorded as open_page does."""
        w = self.alloc(0x40); self.u.mem_write(w, bytes(0x40)); self.setword(w + O['WIDGET_NAME'], self.cstr(name))
        self.stack.append((name, w)); self.sync()
        if opener: self.call(PSYMS['pd_note_opener'], a0=w, a1=next(h for n, h in reversed(self.stack) if n == opener))
        return w

    def tile_eq(self, tile=10):
        """A Control Center tile (10: Equalizer, 9: Settings): the tap stored pd_pending (tile id + 1) and quit the dialog; the modal navigator_to returns 0xd and pd_open_dialog runs the action."""
        self.setword(PSYMS['pd_pending'], tile + 1)
        return self.call(PSYMS['pd_open_dialog'], a0=self.cstr('dialog/dropdown_dialog'), count=6000000)

    def sync(self): self.children[self.wm] = [w for _, w in self.stack]
    def name_of(self, w): return next((n for n, h in self.stack if h == w), None)
    def names_(self): return [n for n, _ in self.stack]
    def seen(self, *names): return [c for c in self.calls if c[0] in names]

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name == 'navigator_to' and self.read_cstr(u.reg_read(UC_MIPS_REG_A0)) == 'dialog/dropdown_dialog':   # the pull-down's modal call: a tile quit it (0xd)
            u.reg_write(UC_MIPS_REG_V0, 0xd); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name not in MINE: return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = 0
        if name == 'widget_on':
            self.bindings.setdefault((a0, a1), []).append((a2, a3))
            return super()._hook(u, address, size, _)
        elif name == 'window_open':
            asset = self.read_cstr(a0)
            if asset not in PAGES_OF: return super()._hook(u, address, size, _)
            self.calls.append(('window_open', asset))
            if not self.open_fail:
                ret = self.push(PAGES_OF[asset])
                if asset == ASSET: self.win = ret
        elif name == 'window_manager_get_top_window': ret = self.stack[-1][1] if self.stack else 0
        elif name == 'window_manager_switch_to':
            self.calls.append(('switch_to', self.name_of(a1), self.name_of(a2)))
            ent = next(e for e in self.stack if e[1] == a2)
            self.stack.remove(ent); self.stack.append(ent); self.sync()
            self.fg_pending = ent[0] == NAME   # (EVT_WINDOW_TO_FG is delivered once the call is over)
        elif name == 'window_close':
            nm = self.name_of(a0); self.calls.append(('window_close', nm))
            if nm: self.closed.append(nm); self.stack.remove(next(e for e in self.stack if e[1] == a0)); self.sync()
        elif name == 'navigator_to_with_context': self.calls.append(('nav_ctx', self.read_cstr(a0), a1))
        elif name == 'widget_is_window_opened': ret = 1
        elif name == 'widget_get_prop':   # stock's value_t: the uint32 at 8; a missing property is an error result and leaves the value alone
            key = (a0, self.read_cstr(a1))
            if key in self.props: self.setword(a2 + 8, self.props[key])
            else: ret = 9
        elif name == 'widget_set_prop': self.props[(a0, self.read_cstr(a1))] = self.word(a2 + 8)
        elif name == 'value_uint32': ret = self.word(a0 + 8)
        elif name == 'timer_count': ret = len(self.active)
        elif name == 'timer_modify':   # stock's reset: a live id gets the new interval, an unknown one answers RET_NOT_FOUND (9)
            self.calls.append(('timer_modify', a0, a1)); ret = 9
            if a0 in self.active: self.active[a0] = self.active[a0][:2] + (a1,); ret = 0
        elif name == 'widget_remove_timer': self.removed.append((a0, a1)); self.active.pop(a1, None)
        elif name == 'v_add_timer':
            ret = self.next_id; self.next_id += 1; self.active[ret] = (a0, a1, a2); self.calls.append(('add_timer', a0, a1, a2))
        elif name == 'v_slider_internal': self.calls.append(('slider_internal', a0, struct.unpack('<d', struct.pack('<II', a2, a3))[0]))
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def dispatch(self, w, evt, e=0):
        """The emitter: every handler bound to (widget, event), the newest first, until one answers RET_STOP. The calls of all of them."""
        ret, acc = 0, []
        for fn, ctx in reversed(self.bindings.get((w, evt), [])):
            ret = self.call(fn, a0=ctx, a1=e, count=6000000); acc += self.calls
            if ret == RET_STOP_: break
        self.calls = acc
        return ret

    def tap(self):
        """The status bar tap: on_wm_tsup_fun's call, now vol_tap_open(name, 2); a restacked page then gets EVT_WINDOW_TO_FG."""
        self.fg_pending = False
        ret = self.call(PSYMS['vol_tap_open'], a0=self.cstr('dialog/volume_dialog'), a1=2, count=6000000)
        calls = list(self.calls)
        if self.fg_pending: self.dispatch(self.win, EVT_FG); calls += self.calls
        self.calls = calls
        return ret

    def advance(self, ms=4000):
        """Let the widget timers due within ms run: stock's callback, which closes the window it was added to; True when one did."""
        ran = False
        for tid, (w, cb, d) in sorted(self.active.items()):
            if d <= ms:
                self.setword(self.timer_info + 0x24, w); self.call(cb, a0=self.timer_info, count=2000000); ran = True
                self.active.pop(tid, None)   # (RET_REMOVE)
        return ran

    def txt(self, name): return [c[2] for c in self.calls if c[0] == 'widget_set_text_utf8' and c[1] == self.widgets[name]]
    def slider_sets(self): return [c[2] for c in self.calls if c[0] == 'slider_set_value' and c[1] == self.widgets['vol_slider']]
    def words(self): return (self.word(VOLUME), self.word(BTVOL), self.word(MAXV))
    def idle(self): return not self.active and self.props.get((self.win, 'timer_idex'), 0xffffffff) == 0xffffffff


def page(stack=('home_page',), **state):
    """A machine with the page opened by the tap."""
    m = VM(stack, **state)
    m.tap()
    return m


def act(m, what, v=0):
    """One change on the page: 'add' / 'dec' (the buttons), 'slider' (value v), 'up' / 'down' (the volume keys: the window's EVT_KEY_UP, the key's code in the event). The calls of every handler it ran; the last answer."""
    if what == 'slider':
        s = m.widgets['vol_slider']
        return m.dispatch(s, EVT_CHANGING, PS.event(m, s, v))
    if what in ('add', 'dec'): return m.dispatch(m.widgets['btn_' + what], EVT_CLICK_)
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x18, KEY_UP_ if what == 'up' else KEY_DOWN_)
    return m.dispatch(m.win, EVT_KEY, e)


def word_of(b, a): return struct.unpack_from('<I', b, pod.fileoff(b, a))[0]


def stores(m):
    """The saves and device calls a change made (stock's reset_poweroptions_timer, which every handler ends with, apart)."""
    return [c for c in PS.loud_calls(m) if c[0] != 'reset_poweroptions_timer']


def pin_tests(ctx):
    expect = ctx.expect
    stock, built = stock_demo_bytes(), built_demo_bytes()
    site = pod.VOLUME_SITE
    sw, bw = word_of(stock, site), word_of(built, site)
    expect(site == 0x4cd964 and sw == 0x041110f8 and word_of(stock, site + 4) == 0x24849a94 and word_of(stock, 0x4cd95c) == 0x24050002,
           'stock\'s status bar tap is `bal navigator_to_with_context` at 0x4cd964, a0 = "dialog/volume_dialog" in the delay slot, a1 = 2 before it')
    expect(bw >> 26 == 3 and (bw & 0x3ffffff) << 2 == PSYMS['vol_tap_open'] and word_of(built, site + 4) == 0x24849a94 and word_of(built, site + 8) == 0x8fbc0010, 'the build replaced it by `jal vol_tap_open`; the delay slot and the gp reload are stock\'s')
    expect(MANIFEST['hook_volume'] == {'addr': site, 'target': PSYMS['vol_tap_open']}, 'the manifest records the hook')
    expect(all(word_of(stock, a) == w for a, w, _ in pod.VOLUME_PINS) and all(word_of(built, a) == w for a, w, _ in pod.VOLUME_PINS if a != site), 'every pinned word is stock\'s, in the stock image and the build (the hook site apart)')
    pins = {a for a, _, _ in pod.VOLUME_PINS}
    expect(all(a in pins for a in STOCK.values()) and word_of(stock, 0x4d1d48) == 0x3c1c0053, 'the six stock entries the page binds or calls are pinned by their prologues')
    expect((D['VOLP_SHOWPAGE'], D['BT_VOLUME'], D['G_VOLUME']) == ((0x97c790, 'volume_showpage'), (0x97cb0c, 'btsource_volume'), (0x97cb10, 'volume')), 'the words are stock\'s (checked against demo\'s dynsym by the build)')
    expect(all(a in pins for a in (0x47dbc8, 0x47dc1c, 0x47dc48, 0x47dc74, 0x47dc7c, 0x47e494, 0x47e4b0)) or all(word_of(stock, a) == w for a, w in ((0x47e494, 0x24050113), (0x47e4b0, 0x24c6e330))),
           'stock\'s init binds the keys (0x113), the buttons (0x10c) and the slider (0x11d) to the handlers we run')
    expect(word_of(stock, 0x47dea8) == 0x24050bb8 and word_of(stock, 0x47dce8) == 0x24060bb8 and word_of(stock, 0x47d650) == 0x8c840024, 'the auto-close timer: 3000 ms, its callback closes the window the timer belongs to')
    expect(pod_pages.PAGES[pod_pages.VOLUME_PAGE_INDEX] is pod_pages.VOLUME_PAGE and pod_pages.VOLUME_PAGE.key == ASSET and pod_pages.VOLUME_PAGE.name == NAME and pod_pages.PAGE_ORDER[-10] == ASSET, 'the page is the tenth from last in PAGE_ORDER (the Update Library page, its folder picker, Split Genres, the three Card Script pages, Crossfade, the playlist Cover page and the Cover Flow Start At picker follow)')


def page_tests(ctx):
    """The asset as built: stock's names, the card and the room for the next phase."""
    expect = ctx.expect
    import pod_i18n
    t = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    expect(t.get('name') == NAME and t.find('label_title') is not None and t.find('label_title').get('tr_text') == 'Volume', 'the window is m1plus_volume_page, titled Volume')
    num, info, lab, s, dec, add = (t.find(n) for n in ('pod_volnum', 'pod_volinfo', 'vol_label', 'vol_slider', 'btn_dec', 'btn_add'))
    expect(all(w is not None for w in (num, info, lab, s, dec, add)), 'the number, the line and stock\'s four widgets are there')
    expect(lab.get('visible') == 'false' and lab.get('sensitive') == 'false', 'stock\'s vol_label is hidden and insensitive (its refresh writes "VOL: 42" into it)')
    expect(s.type == 'slider' and s.get('max') == '100' and s.get('step') == '1' and s.get('slide_with_bar') == 'true' and s.get('visible') == 'false' and s.get('sensitive') != 'false' and s.get('style:normal:icon') is None
           and s.get('style:normal:bg_image') is None and s.get('style:normal:fg_image') is None, 'vol_slider is a stock slider 0 .. 100 that draws nothing (invisible, still sensitive: the touch and the drag stay stock\'s)')
    expect(s.x == 22 and s.x + s.w == 298 and s.h == 52 and s.y + s.h == 168 - 12, 'the slider spans the card\'s inner width 22 .. 298, is 52 px high and ends 12 px above the 168 px card\'s bottom (the side padding)')
    bar = t.find('pod_volbar')
    expect(bar is not None and (bar.x, bar.y, bar.w, bar.h) == (s.x, s.y, s.w, s.h) and bar.get('sensitive') == 'false' and bar.get('style:normal:bg_color') == '#00000000' and t.find('pod_volume').children.index(bar) > t.find('pod_volume').children.index(s),
           'pod_volbar is an insensitive transparent view exactly over the slider, after it (painted over it)')
    miss = touch_misses(page(('home_page',)), os.path.join(WORK, UI), ('vol_slider', 'btn_dec', 'btn_add'))
    expect(not miss, f'the touch reaches the slider and both buttons through the bar ({miss})')
    expect(num.type == 'label' and num.get('sensitive') == 'false' and num.get('style:normal:font_size') == '60' and num.get('style:normal:font_name') == 'lyrics' and num.get('style:normal:text_align_h') == 'left' and num.x == 22,
           'the number is a 60 px label in the bold face at the left, insensitive')
    expect(info.type == 'label' and info.get('sensitive') == 'false' and info.get('style:normal:text_color') == '#AAAAAA' and info.y >= num.y + num.h - 2 and info.y + info.h <= s.y, 'the grey line is under the number and above the bar')
    expect(dec.type == add.type == 'button' and dec.get('text') == '−' and add.get('text') == '+' and dec.w >= 44 and add.w >= 44 and dec.h >= 44 and dec.x + dec.w <= add.x and num.x + num.w <= dec.x and add.x + add.w <= 310,
           'the round - and + buttons are touch-sized and sit at the right of the number\'s row')
    for b, dn in ((dec, 'pod_vsdisc_dec'), (add, 'pod_vsdisc_add')):
        d = t.find(dn)
        expect(d is not None and d.w == d.h == 36 and d.get('sensitive') == 'false' and 2 * d.x + d.w == 2 * b.x + b.w and 2 * d.y + d.h == 2 * b.y + b.h, f'{dn} is the faint disc centred under its button')
    expect(add.x + (add.w + 36) // 2 == 298, 'the + disc ends at the card\'s inner edge, 298')
    card = t.find('pod_volume')
    expect(card.h == 178 and [c.get('style:normal:bg_image') for c in card.children[:4]] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_bot', 'pod_cd_mid'] and all(c.get('sensitive') == 'false' for c in card.children[:4]),
           'the card is stacked card pieces (a top, a mid, a bottom and a second mid for the extra 12 px), insensitive and drawn before the controls; the item is 168 px of card and a 10 px gap')
    expect([(c.y, c.h) for c in card.children[:4]] == [(0, 52), (52, 52), (116, 52), (64, 52)], 'the pieces cover the first 168 px')
    end = t.find('pod_end')
    expect(end is not None and end.y >= card.y + card.h, 'the list ends under the second card')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Headphones', 'Line Out', 'USB DAC', 'Max', 'Bluetooth', 'Volume')), f'the page\'s texts have a translation in {loc}')


def open_tests(ctx):
    """The tap's hook: open, restack, leave alone, or stock's own call."""
    expect = ctx.expect
    m = VM(('home_page', 'playing_page'))
    m.setword(SHOWPAGE, 1)   # (a strip opened earlier left 1)
    m.tap()
    expect(m.seen('window_open') == [('window_open', ASSET)] and not m.seen('nav_ctx') and m.names_() == ['home_page', 'playing_page', NAME], f'the tap opens our page over the others and does not call stock ({m.calls[:4]}, {m.names_()})')
    expect(m.word(SHOWPAGE) == 2 and m.txt('vol_label') == ['VOL: 20'] and m.slider_sets() == [20.0], f'volume_showpage is 2 and stock\'s refresh sets the slider from the volume ({m.word(SHOWPAGE)}, {m.slider_sets()})')
    expect(m.txt('pod_volnum') == ['20'] and m.txt('pod_volinfo') == [m.tr('Headphones')], f'the number is 20 and the line names the output ({m.txt("pod_volnum")}, {m.txt("pod_volinfo")})')
    b, w, s = m.bindings, m.win, m.widgets['vol_slider']
    ours = {fn for fn, _ in b[(w, EVT_KEY)]}
    stock_fns = set(STOCK.values())
    expect(len(b[(w, EVT_KEY)]) == 1 and not ours & stock_fns and [fn for fn, _ in b[(s, EVT_CHANGING)]][1] == STOCK['VOLP_SLIDER'] and [fn for fn, _ in b[(m.widgets['btn_add'], EVT_CLICK_)]][1] == STOCK['VOLP_ADD']
           and [fn for fn, _ in b[(m.widgets['btn_dec'], EVT_CLICK_)]][1] == STOCK['VOLP_DEC'] and all(len(b[(x, e)]) == 2 and b[(x, e)][0][0] not in stock_fns and all(c == w for _, c in b[(x, e)]) for x, e in ((s, EVT_CHANGING), (m.widgets['btn_add'], EVT_CLICK_), (m.widgets['btn_dec'], EVT_CLICK_))),
           'stock\'s slider, + and - handlers are bound after ours (ours run after them) with the window as context; the key event is bound to our wrapper, not stock\'s')
    expect(all(e in (EVT_KEY, EVT_FG, EVT_CHANGING, EVT_CLICK_, 0x10c, 0x0c) or x != w for (x, e) in b) and not any(fn in (0x47dad4, 0x47dd64, 0x47dd9c, TIMER_CB) for hs in b.values() for fn, _ in hs),
           'the dialog\'s timer, to-background / to-foreground and pointer-up handlers are never bound')
    expect(m.idle(), 'no auto-close timer exists after the open')
    # a tap with our page in front: nothing
    m.tap()
    expect(not m.seen('window_open', 'switch_to', 'nav_ctx', 'window_close') and m.names_() == ['home_page', 'playing_page', NAME], f'a tap while our page is in front changes nothing ({m.calls})')
    # in the stack under the player: restacked, the player stays, the foreground refresh runs
    m = page(('home_page',)); m.push('playing_page'); m.setword(SHOWPAGE, 1)
    m.tap()
    expect(m.seen('switch_to') == [('switch_to', 'playing_page', NAME)] and not m.seen('window_open', 'nav_ctx', 'window_close') and m.names_() == ['home_page', 'playing_page', NAME], f'with the player on top the page is restacked, not opened again ({m.calls[:3]})')
    expect(m.word(SHOWPAGE) == 2 and m.slider_sets() == [20.0], 'the restacked page refreshes as it comes to the front (volume_showpage back to 2)')
    # a sub-page above it is closed first
    m = page(('home_page',)); m.push('m1plus_psvolume_page', NAME)
    m.tap()
    expect(m.closed == ['m1plus_psvolume_page'] and m.names_() == ['home_page', NAME] and not m.seen('window_open', 'nav_ctx'), f'a page opened from ours is closed and ours comes to the front ({m.closed}, {m.names_()})')
    # Settings pages the Control Center opened over it are not its sub-pages: they stay, and Back from Volume returns to them
    m = page(('home_page',)); m.push('m1plus_playset_page'); m.push('m1plus_psvolume_page')
    m.tap()
    expect(not m.closed and m.names_() == ['home_page', 'm1plus_playset_page', 'm1plus_psvolume_page', NAME] and m.seen('switch_to') and not m.seen('window_open'), f'Volume under Playback > Volume & Sound: restacked, nothing closed ({m.closed}, {m.names_()})')
    m = page(('home_page',)); m.push('m1plus_psgain_page', NAME); m.push('m1plus_playset_page'); m.push('m1plus_psvolume_page')
    m.tap()
    expect(m.closed == ['m1plus_psgain_page'] and m.names_() == ['home_page', 'm1plus_playset_page', 'm1plus_psvolume_page', NAME], f'its own Gain picker is closed, the Playback pages above stay ({m.closed}, {m.names_()})')
    # our open fails: stock's call, same arguments
    m = VM(('home_page',), open_fail=True)
    m.tap()
    expect(m.seen('nav_ctx') == [('nav_ctx', 'dialog/volume_dialog', 2)] and m.names_() == ['home_page'], f'when our page will not open stock\'s dialog call is made with its own arguments ({m.calls})')
    # Tap for Volume off: the tap does nothing, except over stock's own strip
    for stack, nav in ((('home_page',), 0), (('home_page', 'playing_page'), 0), (('home_page', 'volume_dialog'), 1)):
        m = VM(stack); m.fs['/mnt/data/m1plus/volume-tap'] = b'0\n'
        m.tap()
        expect(not m.seen('window_open', 'switch_to', 'window_close') and len(m.seen('nav_ctx')) == nav and m.names_() == list(stack), f'with Tap for Volume off the tap opens nothing over {stack}, stock only for its own strip ({m.calls})')
    for val in (b'1\n', b'2\n', b'x\n'):
        m = VM(('home_page',)); m.fs['/mnt/data/m1plus/volume-tap'] = val; m.tap()
        expect(m.names_() == ['home_page', NAME], f'with the file {val!r} the page opens: only 0 turns it off')
    # stock's strip in front: stock
    m = VM(('home_page', 'volume_dialog'))
    m.tap()
    expect(m.seen('nav_ctx') == [('nav_ctx', 'dialog/volume_dialog', 2)] and not m.seen('window_open'), 'with stock\'s own volume dialog in front the call is stock\'s')


def change_tests(ctx):
    """Stock's handlers on the page: steps, the caps, the saves, and no timer left behind."""
    expect = ctx.expect
    m = page(volume=20, maxv=100)
    # the premise: stock's handler alone leaves an auto-close timer that closes the window
    n = VM(('home_page',)); n.tap(); n.call(STOCK['VOLP_ADD'], a0=n.win, count=3000000); n.calls = n.calls
    expect(len(n.active) == 1 and n.advance(3500) and n.closed == [NAME], 'without our handler, stock\'s + leaves a 3 s timer that closes the window (the premise)')
    act(m, 'add')
    loud = PS.loud_calls(m)
    expect(m.words()[0] == 21 and [c[:2] for c in loud if c[0] != 'reset_poweroptions_timer'] == [('set_devicevolume', 21), ('write_int_config', 21)], f'+ steps the volume by 1: stored, set on the device, saved ({loud})')
    expect(m.txt('pod_volnum') == ['21'] and m.slider_sets() == [21.0, 21.0] and m.idle(), f'the number says 21 and the slider follows ({m.txt("pod_volnum")}, {m.slider_sets()}); the timer is stopped, timer_idex is -1')
    expect(not m.advance() and not m.closed and NAME in m.names_(), 'the page is still open after the 3 s the timer would have run')
    act(m, 'dec'); act(m, 'dec')
    expect(m.words()[0] == 19 and m.txt('pod_volnum') == ['19'] and m.idle() and not m.advance(), 'two - steps: 19, still open, no timer')
    # the caps
    m = page(volume=80, maxv=80)
    act(m, 'add')
    expect(m.words()[0] == 80 and m.txt('pod_volnum') in ([], ['80']) and m.idle() and not stores(m) and not m.advance(), '+ refuses at Max Volume: nothing stored, saved or set')
    m = page(volume=100, maxv=100); act(m, 'add')
    expect(m.words()[0] == 100 and not stores(m) and m.idle(), '+ refuses at 100')
    m = page(volume=0, maxv=100); act(m, 'dec')
    expect(m.words()[0] == 0 and not stores(m) and m.idle(), '- refuses at 0')
    # the slider
    m = page(volume=20, maxv=80)
    act(m, 'slider', 55)
    expect(m.words()[0] == 55 and ('set_devicevolume', 55) in [c[:2] for c in PS.loud_calls(m)] and ('write_int_config', 55, 'PLAYSET', 'VOLUME') in [c[:4] for c in PS.loud_calls(m)] and m.txt('pod_volnum') == ['55'] and m.idle() and not m.advance() and not m.closed,
           f'a slider change stores, sets and saves the volume, the number follows, no timer, the page stays ({PS.loud_calls(m)})')
    act(m, 'slider', 95)
    expect(m.words()[0] == 80 and m.seen('slider_internal') == [('slider_internal', m.widgets['vol_slider'], 80.0)] and m.txt('pod_volnum')[-1] == '80' and m.idle(), f'a drag past Max Volume is pulled back to it ({m.words()}, {m.seen("slider_internal")})')
    # the volume keys
    m = page(volume=30, maxv=100)
    r = act(m, 'up')
    expect(r == RET_STOP_ and m.words()[0] == 31 and m.txt('pod_volnum') == ['31'] and m.idle() and not m.advance() and not m.closed, f'volume up steps by 1 and is taken (RET_STOP); the number follows, no timer ({r}, {m.words()})')
    r = act(m, 'down')
    expect(r == RET_STOP_ and m.words()[0] == 30 and m.idle() and not m.advance() and not m.closed, 'volume down steps back')
    m.setword(pod.DATA['ROTATEMODE'][0], 1); act(m, 'up')
    expect(m.words()[0] == 29 and m.idle(), 'Screen Rotation swaps the keys as stock\'s handler does')
    m.setword(pod.DATA['ROTATEMODE'][0], 0)
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x18, 0x30)
    r = m.dispatch(m.win, EVT_KEY, e)
    expect(r == 0 and m.words()[0] == 29 and not m.seen('write_int_config'), 'any other key is left alone')
    m = page(volume=30, maxv=31); act(m, 'up'); act(m, 'up')
    expect(m.words()[0] == 31 and m.idle(), 'the keys stop at Max Volume too')
    # Bluetooth: the Bluetooth word, no Max Volume
    m = page(volume=20, maxv=40, headset=2)
    m.setword(BTVOL, 70); m.dispatch(m.win, EVT_FG)
    act(m, 'add'); act(m, 'up')
    expect(m.words() == (20, 72, 40) and m.txt('pod_volnum')[-1] == '72' and ('write_int_config', 72, 'PLAYSET', 'BTVOLUME') in [c[:4] for c in PS.loud_calls(m)] and m.idle(), f'on Bluetooth the buttons and keys move btsource_volume, past Max Volume ({m.words()})')
    # a strip left volume_showpage at 1: every handler of ours sets it back
    m = page(volume=20); m.setword(SHOWPAGE, 1); act(m, 'add')
    expect(m.word(SHOWPAGE) == 2 and m.slider_sets()[-1] == 21.0 and m.idle(), 'a change with volume_showpage at 1 refreshes the page\'s widgets: the word is 2 after it')


def text_tests(ctx):
    """The number and the grey line."""
    expect = ctx.expect
    for kw, want in ((dict(maxv=100), '{o}'), (dict(maxv=80), '{o} · {mx} 80'), (dict(maxv=0), '{o} · {mx} 0'), (dict(maxv=80, lineout=1), 'Line Out')):
        m = page(**kw)
        o = m.tr('Headphones') if 'lineout' not in kw else m.tr('Line Out')
        text = (want.format(o=o, mx=m.tr('Max')) if '{' in want else m.tr(want))
        if 'lineout' in kw: text += ' · %s 80' % m.tr('Max')
        expect(m.txt('pod_volinfo') == [text.encode('utf-8').decode('latin-1')], f'{kw}: the line says {text!r} ({m.txt("pod_volinfo")})')
    m = page(maxv=80, way=2)
    expect(m.txt('pod_volinfo') == [(m.tr('USB DAC') + ' · ' + m.tr('Max') + ' 80').encode('utf-8').decode('latin-1')], 'a USB DAC is named, with Max Volume')
    m = VM(('home_page',), maxv=80, headset=2, volume=20); m.setword(BTVOL, 45); m.tap()
    expect(m.txt('pod_volinfo') == [m.tr('Bluetooth')] and m.txt('pod_volnum') == ['45'], 'Bluetooth: its name alone (stock does not enforce Max Volume there), the Bluetooth volume as the number')
    m = page(maxv=80); m.setword(MAXV, 100); m.dispatch(m.win, EVT_FG)
    expect(m.txt('pod_volinfo') == [m.tr('Headphones')], 'the line follows the words each time the page comes to the front')


def kind(m, b):
    """Which of the bar's four images a blitted bitmap is, by its pixels (the payload's copies: m1_asset_rgba)."""
    data, w, h = m.bitmaps[b]
    px = bytes(m.u.mem_read(data, w * h * 4))
    if (w, h) == (O['VB_W'], O['VB_H']):
        c = (h // 2 * w + w // 2) * 4
        return 'fill' if px[c:c + 3] == b'\xff\xff\xff' else 'track'
    i = next(i for i in range(w * h) if px[i * 4 + 3] > 200)
    return 'ink' if px[i * 4] < 64 else 'glyph'


def paint(m, canvas=True):
    """pod_volbar's EVT_BEFORE_PAINT: ([(image, source rect, destination rect)], [fills (colour, x, y, w, h)])."""
    cv, ev = m.alloc(0x100), m.alloc(0x40)
    m.setword(ev + O['EVENT_PAINT_CANVAS'], cv)
    m.blits.clear(); m.fills.clear()
    m.dispatch(m.widgets['pod_volbar'], O['EVT_BEFORE_PAINT'], ev if canvas else 0)
    return [(kind(m, b), s, d) for b, s, d in m.blits], list(m.fills)


def inval(m): return [c for c in m.calls if c[0] == 'widget_invalidate_force' and c[1] == m.widgets['pod_volbar']]


def bar_tests(ctx):
    """The capsule bar: the baked art, its paint (fill edge, Max tick, split glyph) and the repaints."""
    expect = ctx.expect
    A = art()
    W_, H_, IC, CX, TW, TI, TC = (O[k] for k in ('VB_W', 'VB_H', 'VB_ICON', 'VB_ICON_CX', 'VB_TICK_W', 'VB_TICK_INSET', 'VB_TICK'))
    import mod_icons
    px = lambda n, x, y: tuple(A[n][2][(y * A[n][0] + x) * 4:(y * A[n][0] + x) * 4 + 4])
    expect((W_, H_, IC, CX, TW, TI, TC) == (mod_icons.VOLBAR_W, mod_icons.VOLBAR_H, 24, 26, 2, 12, 0xff6e6a6a) and (A['pod_vol_track'][:2], A['pod_vol_fill'][:2], A['pod_vol_ink'][:2], A['pod_ci_volume'][:2]) == ((276, 52), (276, 52), (24, 24), (24, 24)),
           'the payload\'s constants are the art\'s: a 276 x 52 capsule, 24 px glyphs centred 26 px in, a 2 px tick inset 12, #6A6A6E')
    expect(px('pod_vol_track', 138, 26) == (0x3A, 0x3A, 0x3C, 255) and px('pod_vol_fill', 138, 26) == (255, 255, 255, 255) and px('pod_vol_track', 40, 3)[:3] == (0x3A, 0x3A, 0x3C), 'the track is #3A3A3C and the fill white')
    corners = [px(n, x, y)[3] for n in ('pod_vol_track', 'pod_vol_fill') for x in (0, 275) for y in (0, 51)]
    ends = [px(n, x, 26)[3] for n in ('pod_vol_track', 'pod_vol_fill') for x in (0, 275)]
    expect(corners == [0] * 8 and all(a >= 200 for a in ends) and all(px(n, x, y)[3] == 255 for n in ('pod_vol_track', 'pod_vol_fill') for x in (26, 138, 249) for y in (0, 51)),
           'both ends are half circles: the corners are clear, the middle of each end and the straight top and bottom are solid')
    expect(all(px('pod_vol_track', 13, 6)[3] == 255 and px('pod_vol_track', 262, 6)[3] == 255 and px('pod_vol_track', 3, 5)[3] == 0 and px('pod_vol_track', 272, 5)[3] == 0 for _ in (0,)), 'the ends have radius 26 (inside the arc at (13, 6), outside at (3, 5))')
    asym = max(abs(px('pod_vol_track', x, y)[3] - px('pod_vol_track', 275 - x, y)[3]) for x in range(60) for y in range(52))
    expect(asym <= 1 and all(px('pod_vol_track', x, y)[3] == px('pod_vol_fill', x, y)[3] for x in range(0, 276, 5) for y in range(52)), f'the two ends are mirror images ({asym}) and the track and the fill have one outline')
    ink, gl = A['pod_vol_ink'], A['pod_ci_volume']
    expect(all(ink[2][i + 3] == gl[2][i + 3] and (ink[2][i:i + 3] == b'\0\0\0' or ink[2][i + 3] == 0) for i in range(0, 24 * 24 * 4, 4)) and any(gl[2][i] == 255 and gl[2][i + 3] > 200 for i in range(0, 24 * 24 * 4, 4)),
           'the dark glyph is the white one in black, the same shape')
    # the paint
    m = page(volume=42, maxv=80)
    expect(len(m.bitmaps) == 4 and [u for u in m.loads if u in A] == ['pod_vol_track', 'pod_vol_fill', 'pod_vol_ink', 'pod_ci_volume'], f'the page decodes the four images once as it opens ({m.loads})')
    bl, fl = paint(m)
    expect(bl == [('track', (0, 0, 276, 52), (0, 0, 276, 52)), ('fill', (0, 0, 115, 52), (0, 0, 115, 52)), ('ink', (0, 0, 24, 24), (14, 14, 24, 24))] and fl == [(TC, 219, 12, 2, 28)],
           f'42 with Max 80: the track, the fill cut at 42 % of 276 = 115 px, the tick at 80 % (x 219, y 12 .. 40), the whole glyph dark over the fill ({bl}, {fl})')
    m = page(volume=6, maxv=80)
    bl, fl = paint(m)
    expect(bl == [('track', (0, 0, 276, 52), (0, 0, 276, 52)), ('fill', (0, 0, 16, 52), (0, 0, 16, 52)), ('ink', (0, 0, 2, 24), (14, 14, 2, 24)), ('glyph', (2, 0, 22, 24), (16, 14, 22, 24))] and len(fl) == 1,
           f'6: a 16 px sliver of fill, the glyph split at its edge: 2 px dark, 22 px white ({bl})')
    for v, n_fill, glyph in ((0, None, (0, 24)), (5, 13, (0, 24)), (100, 276, None)):
        m = page(volume=v, maxv=100)
        bl, fl = paint(m)
        got = {k: (s, d) for k, s, d in bl}
        expect([k for k, _, _ in bl][:1] == ['track'] and (('fill' in got) == bool(n_fill)) and (not n_fill or got['fill'][0][2] == n_fill) and (('glyph' in got) == (glyph is not None)) and (glyph is None or got['glyph'][0] == (0, 0, 24, 24))
               and (glyph is not None or got['ink'][0] == (0, 0, 24, 24)) and ('ink' not in got or v == 100) and not fl, f'{v} with no Max: fill {n_fill}, glyph all {"white" if glyph else "dark"}, no tick ({bl}, {fl})')
    for mx, tx in ((50, 137), (80, 219)):
        m = page(volume=10, maxv=mx)
        _, fl = paint(m)
        expect(fl == [(TC, tx, 12, 2, 28)], f'Max {mx}: the full tick at x {tx} ({fl})')
    for mx in range(100):   # the tick never leaves the capsule outline, at either end
        m = page(volume=10, maxv=mx)
        _, fl = paint(m)
        ok = len(fl) <= 1
        for c, x, y, w, h in fl:
            ok = ok and w == 2 and 0 <= x and x + w <= W_ and all(px('pod_vol_track', xx, yy)[3] >= 200 for xx in (x, x + 1) for yy in (y, y + h - 1)) and y >= 0 and y + h <= H_ and y + h // 2 == H_ // 2
        expect(ok, f'Max {mx}: the tick {fl} lies inside the capsule')
    m = page(volume=10, maxv=0); _, fl = paint(m)
    expect(fl == [] or fl[0][4] < 28, 'Max 0: the tick is shortened to the capsule\'s end')
    m = VM(('home_page',), maxv=80, headset=2, volume=20); m.setword(BTVOL, 64); m.tap()
    bl, fl = paint(m)
    expect(not fl and [d for k, _, d in bl if k == 'fill'] == [(0, 0, 176, 52)], f'Bluetooth: the Bluetooth volume 64 sets the fill (176 px) and there is no tick even with Max 80 ({bl}, {fl})')
    expect(paint(page(volume=42), canvas=False) == ([], []), 'an event without a canvas paints nothing')
    # the repaints: every refresh invalidates the bar, and the next paint reads the new word
    m = page(volume=20, maxv=100)
    expect(inval(m), 'the page invalidates the bar as it opens')
    for what, want in (('add', 21), ('dec', 20), ('up', 21), ('down', 20)):
        act(m, what)
        iv = len(inval(m)); bl, _ = paint(m)
        expect(iv >= 1 and [d for k, _, d in bl if k == 'fill'] == [(0, 0, want * 276 // 100, 52)], f'{what}: the bar is invalidated and the next paint is at {want}')
    act(m, 'slider', 55)
    bl, _ = paint(m)
    expect(m.words()[0] == 55 and [d for k, _, d in bl if k == 'fill'] == [(0, 0, 151, 52)], 'a drag: the bar follows the volume (55 -> 151 px)')
    m.setword(VOLUME, 30); m.calls = []; m.dispatch(m.win, EVT_FG)
    iv = len(inval(m)); bl, _ = paint(m)
    expect(iv >= 1 and [d for k, _, d in bl if k == 'fill'] == [(0, 0, 82, 52)], 'coming back to the front (a picker or Volume & Sound changed the volume) invalidates the bar')
    m = page(volume=80, maxv=80); act(m, 'add')
    expect(inval(m), 'a refused step still refreshes (and repaints) the bar')
    # the images go with the window; no art (a failed decode) leaves the bar unpainted, not broken
    m = page(volume=42)
    fn, c = m.bindings[(m.win, 0x0c)][-1]
    m.calls = []; m.call(fn, a0=c, a1=0, count=1000000)
    expect(len([x for x in m.calls if x[0] == 'bitmap_destroy']) == 4 and paint(m)[0] == [], 'the window\'s destroy frees the four bitmaps; nothing is painted after')
    m = VM(('home_page',)); m.load_image = 1; m.tap()
    expect(paint(m) == ([], []) and not m.bitmaps, 'with no decodable art nothing is painted and nothing leaks')


def row_tests(ctx):
    """The second card: Max Volume, Equalizer and Volume & Sound open their pages once, with their values."""
    expect = ctx.expect
    t = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    card, rows = t.find('pod_volume'), [t.find(f'pod_row{i}') for i in range(3)]
    expect(all(r is not None and r.type == 'list_item' for r in rows) and t.find('pod_row3') is None, 'three rows, pod_row0 .. pod_row2')
    labs = [next(c for c in r.children if c.name == f'pod_label{i}') for i, r in enumerate(rows)]
    expect([l.get('tr_text') for l in labs] == ['Max Volume', 'Equalizer', 'Volume & Sound'] and [r.h for r in rows] == [52] * 3 and rows[0].y == card.y + card.h == 178 + card.y and rows[1].y == rows[0].y + 52 and rows[2].y == rows[1].y + 52,
           'Max Volume, Equalizer, Volume & Sound, 52 px each, in one card 10 px under the volume card')
    imgs = [next(c for c in r.children if c.type == 'image' and (c.get('image') or '').startswith('pod_ci_')).get('image') for r in rows]
    expect(imgs == ['pod_ci_gauge', 'pod_ci_sliders_vertical', 'pod_ci_volume_2'] and [r.get('style:normal:bg_image') for r in rows] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_bot'], f'the glyphs are the Settings rows\' (Max Volume a gauge, Volume & Sound a speaker) and the Equalizer row\'s ({imgs}); a top, a mid and a bottom piece')
    expect(t.find('pod_value0') is not None and t.find('pod_value1') is not None and t.find('pod_value2') is None, 'Max Volume and Equalizer show a value, Volume & Sound none')
    # the values
    m = page(); m.setword(MAXV, 80); m.calls = []; m.dispatch(m.win, EVT_FG)
    expect(m.txt('pod_value0')[-1:] == ['80'] and m.txt('pod_value1')[-1:] == [m.tr('Off')], f'back in front: Max Volume 80 and the Equalizer Off ({m.txt("pod_value0")}, {m.txt("pod_value1")})')
    expect(not [c for c in m.calls if c[0] in ('widget_set_opacity', 'widget_set_sensitive') and c[1] == m.widgets['pod_row0']], 'the Max Volume row is never dimmed (no Line Out rule)')
    m.setword(D['EQ_FLAG'][0], 1); m.calls = []; m.dispatch(m.win, EVT_FG)
    expect(m.txt('pod_value1')[-1:] != [m.tr('Off')] and m.txt('pod_value1'), f'back in front: the Equalizer row follows the equalizer ({m.txt("pod_value1")})')
    # each row opens its page once
    for k, asset in enumerate(('m1plus_psmaxvol', 'm1plus_peq', 'm1plus_psvolume')):
        win = PAGES_OF[asset]
        m = page(('home_page',)); m.calls = []; m.dispatch(m.widgets[f'pod_row{k}'], EVT_CLICK_)
        expect(m.seen('window_open') == [('window_open', asset)] and m.names_() == ['home_page', NAME, win], f'row {k} opens {asset} over the page ({m.seen("window_open")}, {m.names_()})')
        # in the stack under our page: the target is restacked, no second window; our page (the route the user came by) is not closed
        m = page(('home_page', win)); m.calls = []
        m.dispatch(m.widgets[f'pod_row{k}'], EVT_CLICK_)
        expect(not m.seen('window_open', 'window_close') and m.names_() == ['home_page', NAME, win], f'row {k} with {asset} already in the stack: it is restacked in front of our page, never opened twice, nothing closed ({m.calls[:5]}, {m.names_()})')
        # its own sub-page directly above it is closed, our page stays
        m = VM(('home_page', win)); m.push('m1plus_psvolume_page' if k != 2 else 'm1plus_peqlib_page', win); m.tap(); m.calls = []
        m.dispatch(m.widgets[f'pod_row{k}'], EVT_CLICK_)
        expect(m.closed and NAME not in m.closed and m.names_().count(win) == 1 and m.names_()[-1] == win and NAME in m.names_(), f'row {k}: a sub-page left above {asset} is closed, our page is not ({m.closed}, {m.names_()})')
        # under the player (a window that leaves settings): the target is brought to the front, the player and our page stay below it
        m = page(('home_page', win, 'playing_page')); m.calls = []
        m.dispatch(m.widgets[f'pod_row{k}'], EVT_CLICK_)
        expect(not m.seen('window_open') and m.names_().count(win) == 1 and m.names_()[-1] == win and 'playing_page' in m.names_(), f'row {k} with {asset} under the player: restacked, no second window ({m.names_()})')


    # the Settings route (Playback > Volume & Sound > Gain, Max Volume, Equalizer, Volume & Sound) shares the one window
    import pod_pages
    for act_, idx, asset in ((pod_pages.ACT_GAIN, pod_pages.PSGAIN_PAGE_INDEX, 'm1plus_psgain'), (pod_pages.ACT_MAXVOL, pod_pages.PSMAXVOL_PAGE_INDEX, 'm1plus_psmaxvol'), (pod_pages.ACT_PEQ, pod_pages.PEQ_PAGE_INDEX, 'm1plus_peq'), (pod_pages.ACT_PAGE, pod_pages.PSVOLUME_PAGE_INDEX, 'm1plus_psvolume')):
        win = PAGES_OF[asset]
        def settings_row(m):
            row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, act_); m.setword(row + 8, idx)
            m.calls = []; m.call(PSYMS['on_row'], a0=row, count=6000000)
        # (the page opened from the Volume page, then Control Center > Playback (> Volume & Sound) over it)
        m = VM(('home_page', NAME, win, 'm1plus_playset_page') + (('m1plus_psvolume_page',) if asset != 'm1plus_psvolume' else ()))
        before = m.names_()
        settings_row(m)
        expect(not m.seen('window_open', 'window_close') and m.names_().count(win) == 1 and m.names_()[-1] == win and sorted(m.names_()) == sorted(before), f'Settings route, {asset} already open under the Volume page: restacked, no second window, nothing closed ({m.calls[:4]}, {before} -> {m.names_()})')
        m = VM(('home_page', 'm1plus_playset_page')); settings_row(m)
        expect(m.seen('window_open') == [('window_open', asset)] and m.names_() == ['home_page', 'm1plus_playset_page', win], f'Settings route, {asset} not open: opened ({m.calls[:3]})')
        m = VM(('home_page', win)); settings_row(m)
        expect(not m.seen('window_open') and m.names_() == ['home_page', win], f'Settings route, {asset} already in front: left alone ({m.calls[:3]})')


def route_tests(ctx):
    """Back navigation across the routes to the shared pages: a window is closed only when the route that is reopening its page opened it (docs/modules/pulldown.md, opener tracking)."""
    expect = ctx.expect
    PEQ = 'm1plus_peq_page'
    # Volume (status bar tap), then Equalizer from its Control Center tile, then the status bar tap again: Equalizer is not Volume's sub-page, Back returns to it
    m = page(('home_page',)); m.tile_eq()
    expect(m.names_() == ['home_page', NAME, PEQ], f'the Equalizer tile opens the page over Volume ({m.names_()})')
    m.tap()
    expect(not m.closed and m.names_() == ['home_page', PEQ, NAME], f'Volume > EQ tile > status bar tap: Volume is restacked and the Equalizer stays under it ({m.closed}, {m.names_()})')
    # the reverse: Equalizer open, status bar tap opens Volume, the Equalizer tile again: Volume is not the Equalizer's sub-page
    m = VM(('home_page', PEQ)); m.tap(); m.tile_eq()
    expect(not m.closed and m.names_() == ['home_page', NAME, PEQ], f'EQ > status bar tap > EQ tile: the Equalizer is restacked and Volume stays under it ({m.closed}, {m.names_()})')
    # a row's page is Volume's sub-page: the status bar tap closes it, even with other windows above it
    m = page(('home_page',)); m.calls = []; m.dispatch(m.widgets['pod_row0'], EVT_CLICK_)
    m.push('m1plus_playset_page'); m.tap()
    expect(m.closed == ['m1plus_psmaxvol_page'] and m.names_() == ['home_page', 'm1plus_playset_page', NAME], f'Volume > Max Volume row > Playback over it > status bar tap: only Max Volume (opened by Volume) is closed ({m.closed}, {m.names_()})')
    # the Settings tile (pd_open_own, which closes what is above its page) keeps a Volume page the status bar opened over it, and closes what Settings opened
    m = VM(('home_page', 'm1plus_settings_page')); m.push('m1plus_display_page', 'm1plus_settings_page'); m.tap(); m.tile_eq(9)
    expect(m.closed == ['m1plus_display_page'] and m.names_() == ['home_page', NAME, 'm1plus_settings_page'], f'Settings > Display > status bar Volume > Settings tile: Display (Settings\' own) is closed, Volume stays ({m.closed}, {m.names_()})')
    # Volume's Equalizer row, the player over it, then the tile: the one Equalizer window comes to the front, Volume stays
    m = page(('home_page',)); m.dispatch(m.widgets['pod_row1'], EVT_CLICK_); m.push('playing_page'); m.tile_eq()
    expect(not m.closed and m.names_() == ['home_page', NAME, 'playing_page', PEQ], f'Volume > Equalizer row > player > tile: one Equalizer window, in front, nothing closed ({m.closed}, {m.names_()})')
    # the Playback tile over Volume, through the real routes (pd_open_settings, then the Volume & Sound row): neither Settings page is Volume's
    import pod_pages
    m = page(('home_page',)); m.call(PSYMS['pd_open_settings'], a0=m.cstr('playset/playset_page'), count=6000000)
    row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, pod_pages.ACT_PAGE); m.setword(row + 8, pod_pages.PSVOLUME_PAGE_INDEX)
    m.call(PSYMS['on_row'], a0=row, count=6000000)
    expect(m.names_() == ['home_page', NAME, 'm1plus_playset_page', 'm1plus_psvolume_page'], f'the Playback tile, then Volume & Sound, over Volume ({m.names_()})')
    m.tap()
    expect(not m.closed and m.names_() == ['home_page', 'm1plus_playset_page', 'm1plus_psvolume_page', NAME], f'Volume > Playback tile > Volume & Sound > status bar tap: both Settings pages stay ({m.closed}, {m.names_()})')
    # Equalizer > Presets > Download from AutoEq (its own window_open), then the Equalizer tile: AutoEq goes with Presets
    m = VM(('home_page',)); m.tile_eq(); m.push('m1plus_peqlib_page', PEQ)
    m.call(PSYMS['autoeq_open'], count=400000000)
    expect(m.names_() == ['home_page', PEQ, 'm1plus_peqlib_page', 'm1plus_autoeq_page'], f'AutoEq opens over Presets ({m.names_()})')
    m.push('playing_page'); m.closed = []; m.tile_eq()
    expect(m.closed == ['m1plus_autoeq_page', 'm1plus_peqlib_page'] and m.names_() == ['home_page', 'playing_page', PEQ], f'Equalizer > Presets > AutoEq > player > tile: Presets and AutoEq are closed ({m.closed}, {m.names_()})')
    # the Settings and Sleep Timer tiles over Volume: a tile's page is not the sub-page of the window that happened to be in front
    for tile, own in ((9, 'm1plus_settings_page'), (8, 'm1plus_sleeptimer_page')):
        m = page(('home_page',)); m.tile_eq(tile)
        expect(m.names_() == ['home_page', NAME, own], f'the tile opens {own} over Volume ({m.names_()})')
        m.tap()
        expect(not m.closed and m.names_() == ['home_page', own, NAME], f'Volume > {own} tile > status bar tap: Volume is restacked and the page stays under it ({m.closed}, {m.names_()})')


SECTIONS = [pin_tests, page_tests, open_tests, change_tests, text_tests, bar_tests, row_tests, route_tests]

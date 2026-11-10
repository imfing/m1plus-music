"""Our keyboard embedded in the stock Tidal > Search page (patch/tidalkb.c, docs/modules/tidalkb.md, payload hook 27, tools/pod.py TIDALKB_SITE, tools/pod_ui.py add_tidal_keyboard).

Stock's own code runs for real: the page's widget_foreach callback (0x4c1f3c, whose call to edit_set_focus is the hooked site) and the IM action handler's search routine (0x4c4740: the history
file, the result page's two calls, the empty-text warning); the keyboard is the real payload keyboard (test/pod/keyboard.py's machine) attached with keyboard_attach to the page's window. Mocked at
their stock boundary: libc, the widget calls, getFormatString, edit_set_tips, the search page's two helpers (0x4c2254, 0x4c2380) and edit_set_focus. The mock of edit_set_focus is what stock does
(pinned in TIDALKB_PINS): focusing a writable edit asks the input method, which pops stock's T9 ('t9' in the log)."""
import importlib.util, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
BIND, SEARCH = 0x4c1f3c, pod.TIDALKB_SEARCH
HISTORY = '/mnt/data/tidalhistory'
TIPS = 'Search for music,artists,albums'   # stock's own tips text, which stock's init still puts on the (hidden) edit
PAGE = 0x24010000   # the Tidal search page's window
EVT_CLICK, EVT_DESTROY, EVT_FG, EVT_BG = O['EVT_CLICK'], O['EVT_DESTROY'], O['EVT_WINDOW_TO_FG'], O['EVT_WINDOW_TO_BG']
STOCK = {0x742c90: 'strcmp', 0x742da0: 'memset', 0x742ab0: 'snprintf', 0x743870: 'stk_fopen', 0x7426b0: 'stk_fwrite', 0x742660: 'stk_fclose', 0x743570: 'stk_strcpy',
         0x667d84: 'stk_get_text', 0x4ccc18: 'stk_format', 0x6293a8: 'stk_tips', 0x4c2254: 'tidal_wait', 0x4c2380: 'tidal_start', pod.FUNCTIONS['edit_set_focus'][2]: 'edit_set_focus'}


def keyboard_module():
    """test/pod/keyboard.py as a module (its machine runs the real keyboard page); loaded once, as test/patch.py loads the others."""
    if 'podtest_keyboard' not in sys.modules:
        spec = importlib.util.spec_from_file_location('podtest_keyboard', os.path.join(HERE, 'keyboard.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['podtest_keyboard'] = mod
        spec.loader.exec_module(mod)
    return sys.modules['podtest_keyboard']


STRUCTS = {'tracks': pod.DATA['TIDAL_TRACKS'][0], 'artists': pod.DATA['TIDAL_ARTISTS'][0], 'albums': pod.DATA['TIDAL_ALBUMS'][0]}
KB = keyboard_module()
D = cdefs.defines(os.path.join(ROOT, 'patch', 'tidalkb.h'))   # the field's geometry, as the asset builder and the payload read it


class TM(ListMachine):
    """The keyboard machine plus the stock Tidal search page around the hooked call."""

    def __init__(self):
        super().__init__()
        for a, n in STOCK.items(): self.handlers[a] = n
        self.log, self.fp, self.tips, self.snaps = [], None, TIPS, []
        self.emit = {}   # (widget, event) -> [(handler, ctx)], newest first: stock's emitter_on_with_tag puts a handler at the head (TIDALKB_PINS 0x6f466c / 0x6f4670)
        self.fail_widgets = frozenset()   # widgets whose widget_on is refused

    def tidal_state(self):
        """The stock result structs { total, limit, offset, deque } (tracks, artists, albums), the rows in their deques, and the scroll offset, as they are now."""
        return ([(self.word(a), self.word(a + 4), self.word(a + 8), len(self.deques.get(self.word(a + 12), []))) for a in (STRUCTS['tracks'], STRUCTS['artists'], STRUCTS['albums'])],
                self.word(pod.DATA['TIDAL_SCROLL'][0]))

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name == 'widget_on':
            a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
            if a0 in self.fail_widgets:
                u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
            super()._hook(u, address, size, _)
            if a1 not in self.widget_on_fail: self.emit.setdefault((a0, a1), []).insert(0, (a2, a3))
            return
        if name not in ('stk_fopen', 'stk_fwrite', 'stk_fclose', 'stk_strcpy', 'stk_get_text', 'stk_format', 'stk_tips', 'tidal_wait', 'tidal_start', 'edit_set_focus'):
            return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = 0
        if name == 'edit_set_focus':
            self.log.append(('edit_set_focus', a0, a1))
            if a1: self.log.append(('t9', a0))   # stock: the focus of a writable edit asks the input method, which opens kb_default_t9
        elif name == 'stk_fopen':
            self.fp = self.read_cstr(a0); self.log.append(('fopen', self.fp, self.read_cstr(a1))); ret = self.alloc(4)
        elif name == 'stk_fwrite':
            self.fs[self.fp] = bytes(u.mem_read(a0, a1 * a2)); self.log.append(('fwrite', self.fp, a1 * a2)); ret = a2
        elif name == 'stk_fclose': self.log.append(('fclose',))
        elif name == 'stk_strcpy':
            self.u.mem_write(a0, self.read_cstr(a1).encode('latin-1') + b'\0'); ret = a0
        elif name == 'stk_get_text':   # widget_get_text_utf8(widget, buf, size)
            self.u.mem_write(a1, (self.wtext.get(a0) or '').encode('latin-1')[:a2 - 1] + b'\0')
        elif name == 'stk_format':   # getFormatString(key, buf, size): the stock table's text
            self.u.mem_write(a1, self.tips.encode() + b'\0') if self.read_cstr(a0) == 'search_tips1' else None
        elif name == 'stk_tips': self.log.append(('edit_set_tips', a0, self.read_cstr(a1)))
        elif name == 'tidal_wait': self.log.append(('wait', a0, a1))
        elif name == 'tidal_start': self.log.append(('start', a0)); self.snaps.append(self.tidal_state())
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


class TMZh(KB.PY.Engine, TM):
    """TM over demo's real pinyin engine (Settings > Keyboards > Chinese on, the dictionary there), as test/pod/keyboard.py zh_machine."""


def page(zh=False, **kw):
    """The keyboard machine (its widgets and geometry) with the Tidal search page's window, bar and edit added; the stock bind callback is NOT run yet. zh: the Chinese layer is available."""
    m = KB.keyboard_machine(TMZh({KB.PY.SYS_PATH: KB.DICT_DATA}) if zh else TM())
    if zh:
        m.fs[KB.KBZH] = b'1\n'
        m.present.add(KB.PY.SYS_PATH)
    m.page_window = PAGE
    edit = m.widget('search_edit')
    m.setword(edit + O['W_NAME'], m.cstr('search_edit'))
    m.edit = edit
    m.bar = m.widget('listitem_ssid')   # the asset: window > list_item listitem_ssid > edit search_edit, kb_field (ui/tidal/tidal_serach_page.bin)
    m.setword(m.bar + O['W_NAME'], m.cstr('listitem_ssid'))
    m.setword(edit + O['W_PARENT'], m.bar)
    m.setword(m.bar + O['W_PARENT'], PAGE)
    m.props[(edit, 'visible')] = m.props[(edit, 'sensitive')] = 1
    # stock's page init before the hooked widget_foreach: the navbar with its Search button (button_create(nav, 273, 0, 47, 50), the navbar's last child), EVT_CLICK -> 0x4c4740 with the window as context
    nav = m.widget('navigationbar_view')
    m.btn = m.widget('nav_search_btn')
    for off, v in ((0, 273), (4, 0), (8, 47), (12, 50)): m.setword(m.btn + off, v)
    m.children[nav] = [m.widget('nav_title'), m.btn]
    m.bound[(m.btn, EVT_CLICK)] = (SEARCH, PAGE); m.emit[(m.btn, EVT_CLICK)] = [(SEARCH, PAGE)]
    for k, v in kw.items(): setattr(m, k, v)
    return m


def navbtn(m):
    """A tap on the navbar's Search button, through the emitter as stock runs it: the handlers newest first, until one answers RET_STOP (11). Returns the handlers that ran."""
    ran = []
    for fn, ctx in list(m.emit.get((m.btn, EVT_CLICK), [])):
        ran.append(fn)
        if m.call(fn, a0=ctx, a1=0, count=3000000) == 11: break
    return ran


def bind(m):
    """Stock's widget_foreach callback (0x4c1f3c) for the edit: callback(window, widget)."""
    m.calls, m.log = [], []
    m.call(BIND, a0=PAGE, a1=m.edit, count=3000000)
    return m


def up(m):
    """The page's init ran: the keyboard is attached."""
    return bind(m)


def tick(m, n=1):
    """The payload's poll timer, as AWTK calls it (the callback ends with RET_OK and arms the next one itself); False when there was none."""
    for _ in range(n):
        if not m.timers: return False
        cb, ms = m.timers.pop()
        m.call(cb, a0=0, count=3000000)
    return True


def tap(m, drag=False):
    """A finger tap on the search bar, as stock delivers it (docs/modules/tidalkb.md "The tap"): widget_on_pointer_down 0x67126c / _up 0x67187c go to kb_field (the target under the finger; nothing
    of ours listens), a view has no on_event so widget_dispatch goes to its emitter and answers RET_OK, and the parent list_item's widget_dispatch runs list_item_on_event 0x60bb80, which on the up
    (no drag over 10 px) sends EVT_CLICK 0x10c to the LIST_ITEM only. A drag (pointer move >= 11 px) sets the dragged flag: no click. While the pad is up the finger over the bar still lands on kb_field."""
    for ev in (O['EVT_POINTER_DOWN'], O['EVT_POINTER_UP']):
        if (m.widgets['kb_field'], ev) in m.bound: m.fire(ev, m.widgets['kb_field'])
        if ev == O['EVT_POINTER_UP'] and not drag and (m.bar, EVT_CLICK) in m.bound: m.fire(EVT_CLICK, m.bar)


def kb_calls(m): return [c for c in m.calls if c[0] in ('window_open', 'navigator_back')]
def t9(m): return [e for e in m.log if e[0] == 't9']
def busy(m): return m.call(PSYMS['keyboard_busy'], count=100000)
def pad_on(m): return m.props.get((m.widgets['kb_pad'], 'visible')) == 1 and m.props.get((m.widgets['kb_pad'], 'sensitive')) == 1
def pad_off(m): return m.props.get((m.widgets['kb_pad'], 'visible')) == 0 and m.props.get((m.widgets['kb_pad'], 'sensitive')) == 0
def searches(m): return [e for e in m.log if e[0] == 'start']
def sent(m): return (m.wtext.get(m.edit) or '').encode('latin-1').decode('utf-8')   # the edit's text (UTF-8 bytes held as latin-1), what stock's search reads


def hook_tests(ctx):
    expect = ctx.expect
    import paths
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site = pod.TIDALKB_SITE
    expect(site == 0x4c2088 and w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['tidal_kb_focus'],
           'the build replaced stock\'s `jalr t9` (edit_set_focus) at 0x4c2088 by `jal tidal_kb_focus`')
    expect(all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old, _ in pod.TIDALKB_PINS) and len(pod.TIDALKB_PINS) >= 30,
           'every pinned word is stock\'s in the stock demo and unchanged in the build, but the site')
    expect(w(built, site - 8) == 0x8f99a8a8 and w(built, site - 4) == 0x24050001 and w(built, site + 4) == 0x02002025, 'lw t9 edit_set_focus, a1 = 1 and the delay slot (a0 = the edit) are stock\'s')
    expect(MANIFEST['hook_tidalkb'] == {'addr': site, 'target': PSYMS['tidal_kb_focus']}, 'the manifest records the hook')
    expect(pod.FUNCTIONS['edit_set_focus'][2] == 0x62a1dc and pod.TIDALKB_SEARCH == 0x4c4740 and 'tidalkb.c' in pod.SOURCES, 'the stock addresses and the source are the pinned ones')


def asset_tests(ctx):
    """The edited Tidal > Search page: the stock layout untouched, the field in the bar, the pad at the bottom of the window."""
    expect = ctx.expect
    import paths
    rel = pod_ui.TIDAL_SEARCH
    built = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', rel), 'rb').read())
    stock = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', rel), 'rb').read())
    by = {w.name: w for w in built.walk() if w.name}
    bar = by['listitem_ssid']
    expect([c.name for c in built.children] == ['navigationbar_view', 'listitem_ssid', 'view', 'tab_control', 'kb_pad', 'kb_strip', 'kb_stem', 'kb_pop'] and [c.name for c in bar.children] == ['search_edit', 'kb_field'],
           f'the window keeps the stock widgets and ends with the pad, the strip and the pop-up; the bar holds the edit then our field ({[c.name for c in built.children]})')
    # taking our widgets out gives the stock page byte for byte
    bar.children = [c for c in bar.children if c.name != 'kb_field']
    built.children = [c for c in built.children if not (c.name or '').startswith('kb_')]
    expect(awtk_ui.serialize(built) == awtk_ui.serialize(stock), 'without our widgets the page is stock\'s, byte for byte (the edit, the history and the results are untouched)')
    by = {w.name: w for w in awtk_ui.parse(open(os.path.join(WORK, 'rootfs', rel), 'rb').read()).walk() if w.name}
    bar, f = by['listitem_ssid'], by['kb_field']
    expect((f.x, f.y, f.w, f.h) == (D['TK_FIELD_X'], 0, D['TK_FIELD_W'], D['TK_FIELD_H']) and f.h == bar.h and 0 <= f.x and f.x + f.w <= bar.w and f.get('sensitive') == 'true',
           f'the field lies inside the bar ({bar.w} x {bar.h}), full height, and is sensitive (its clear button, and a tap on it reaches the bar)')
    expect(f.get('style:normal:bg_color') == '#00000000', 'the field has no fill: the stock bar shows')
    kids = {c.name: c for c in f.children}
    expect(list(kids) == ['kb_hint', 'kb_text', 'kb_caret', 'kb_clear'] and kids['kb_text'].get('style:normal:font_size') == str(D['TK_PX']) == edit_px(by) and kids['kb_hint'].get('style:normal:font_size') == str(D['TK_PX'])
           and kids['kb_text'].get('style:normal:text_color') == by['search_edit'].get('style:normal:text_color') and kids['kb_hint'].get('style:normal:text_color') == by['search_edit'].get('style:normal:tips_text_color'),
           'the text and the hint have the stock edit\'s font size and colours')
    cl, car = kids['kb_clear'], kids['kb_caret']
    expect(cl.x + cl.w == f.w and cl.w == D['TK_CLEAR_W'] and cl.get('visible') == 'false' and cl.get('sensitive') == 'false' and D['TK_TEXT_X'] + D['TK_TEXT_W'] <= cl.x and car.y == D['TK_CARET_Y'] and car.y + car.h <= f.h, 'the clear button sits at the field\'s right end, hidden and insensitive; the text room stops at it; the caret is inside the bar')
    # the hint "Search Tidal" is the same key in every language and fits the field's text room at the field's font size (the stb rule)
    from awtk_text import Ttf, StbText
    import awtk_strings, pod_i18n
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    ws = {loc: StbText(font, D['TK_PX']).layout(dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin')))['Search Tidal'])[1] for loc in pod_i18n.LOCALES}
    print('  Search Tidal widths:', ws)
    expect(max(ws.values()) <= D['TK_TEXT_W'], f'"Search Tidal" fits TK_TEXT_W {D["TK_TEXT_W"]} px at {D["TK_PX"]} px in all 13 languages (widest {max(ws.items(), key=lambda kv: kv[1])}; {ws})')
    # the pad at the bottom of the window (the 450 px client area), the same widgets as the keyboard page's
    kbt = {w.name: w for w in awtk_ui.parse(open(os.path.join(KB.RAW, 'ui', 'm1plus_keyboard.bin'), 'rb').read()).walk() if w.name}
    same = [n for n in kbt if n.startswith('kb_') and n not in ('kb_field', 'kb_mag', 'kb_hint', 'kb_text', 'kb_caret', 'kb_clear')]
    expect(all(n in by and (by[n].x, by[n].y, by[n].w, by[n].h) == (kbt[n].x, kbt[n].y, kbt[n].w, kbt[n].h) and by[n].props == kbt[n].props for n in same), 'the pad, the strip and the pop-up are the keyboard page\'s own widgets, byte for byte')
    pad = by['kb_pad']
    expect(pad.y + pad.h == KB.DEFS['KB_WIN_H'] == 450 and pad.x == 0 and pad.w == 320 and (stock_win_h(by)) == 450, 'the pad\'s bottom is the 450 px window\'s bottom (the same client area as the keyboard page)')
    expect(by['kb_strip'].get('visible') == 'false' and by['kb_strip'].get('sensitive') == 'false' and by['kb_pop'].get('sensitive') == 'false', 'the strip starts hidden and insensitive, the pop-up never takes a touch')
    # the pad covers only the history / results area, never the bar or the navbar
    nav = by['navigationbar_view']
    expect(pad.y >= nav.y + nav.h and pad.y >= bar.y + bar.h, f'the pad starts below the toolbar and the bar (y {pad.y})')


def edit_px(by): return by['search_edit'].get('style:normal:font_size')
def stock_win_h(by): return by['view'].y + by['view'].h   # the stock window: its content ends at y 450 (view: 50 + 400)


def life_tests(ctx):
    expect = ctx.expect
    # 1. stock's callback hits the hook: the pad is attached, no T9, no page of ours, the stock edit hidden; stock's own binds (action event, tips) still done
    m = page(); bind(m)
    expect(not t9(m) and not [e for e in m.log if e[0] == 'edit_set_focus'], f'the page init gives the edit no focus, so stock\'s T9 does not open ({m.log})')
    expect(not kb_calls(m) and busy(m) == 1 and pad_on(m), 'the pad is attached and shown; no window opened or closed')
    expect(KB.said(m, 'kb_hint') == 'Search Tidal' and KB.field(m) == '' and m.props.get((m.widgets['kb_caret'], 'x')) == D['TK_TEXT_X'], f'the bar\'s hint is Search Tidal ({KB.said(m, "kb_hint")!r})')
    expect(m.props[(m.edit, 'visible')] == 0 and m.props[(m.edit, 'sensitive')] == 0, 'the stock edit is hidden and insensitive (our field is the bar\'s text)')
    expect((m.bar, EVT_CLICK) in m.bound and (m.edit, EVT_CLICK) not in m.bound and (PAGE, EVT_DESTROY) in m.bound and m.timers and m.timers[-1][1] == 250, 'the click handler is on the bar\'s list_item, the destroy on the page, the poll armed')
    expect(m.bound.get((m.edit, 0x13c)) == (0x4c4990, PAGE) and ('edit_set_tips', m.edit, TIPS) in m.log, 'stock\'s own binding of the IM action (0x13c -> 0x4c4990) and the tips are done as before')
    # 2. typing shows in the bar and reaches the edit at once; the caret follows the width from the field's text x
    KB.typ(m, 'Abba')
    expect(KB.field(m) == 'Abba' and m.wtext.get(m.edit) == 'Abba', f'typed text is in the bar and in the edit ({KB.field(m)!r}, {m.wtext.get(m.edit)!r})')
    expect(KB.geo(m, 'kb_caret')[:2] == (D['TK_TEXT_X'] + KB.width('Abba', 18) + 1, D['TK_CARET_Y']), f'the caret is at the bar\'s text x plus the measured width ({KB.geo(m, "kb_caret")})')
    KB.press(m, 'kb_del')
    expect(KB.field(m) == 'Abb' and m.wtext.get(m.edit) == 'Abb', 'delete reaches the edit too')
    KB.typ(m, 'a')
    KB.run_evt(m, 'kb_clear', EVT_CLICK)
    expect(KB.field(m) == '' and m.wtext.get(m.edit) == '', 'the clear button empties the bar and the edit')
    KB.typ(m, 'Abba')
    # 3. Search: stock's routine runs once on the edit with the text, the pad gives way, no page opens or closes
    m.calls = []; m.log = []
    KB.press(m, 'kb_go')
    expect(m.wtext.get(m.edit) == 'Abba' and [e[0] for e in m.log if e[0] in ('fopen', 'fwrite', 'wait', 'start')] == ['fopen', 'fwrite', 'wait', 'start'] and ('fopen', HISTORY, 'wb+') in m.log
           and m.fs.get(HISTORY, b'')[:5] == b'Abba\0' and ('wait', PAGE, 1) in m.log and ('start', PAGE) in m.log and ('navigator_close', 'kb_default_t9') in m.calls,
           f'Search ran stock\'s routine once: history file written (newest first), the search started on the page, kb_default_t9 closed ({m.log})')
    expect(pad_off(m) and not kb_calls(m) and not t9(m), 'the pad is hidden (and takes no touch) so the results show; no page opened or closed, no T9')
    expect(KB.field(m) == 'Abba' and busy(m) == 1, 'the bar keeps showing the text; the keyboard stays attached')
    # 4. a tap on the bar AFTER the search (stock's 0x4c2254 / 0x4c2380 touch only view, tab_control, image_wait and the edit's text, so the list_item and kb_field are the same widgets):
    # the pad comes back with the text; a second tap while it is up does nothing. A drag over the bar is no click.
    tap(m, drag=True)
    expect(pad_off(m), 'a drag that starts on the bar is no click: the pad stays hidden')
    tap(m)
    expect(pad_on(m) and KB.field(m) == 'Abba' and not kb_calls(m) and not t9(m), 'a tap on the bar after the search shows the pad again with the current text')
    m.calls = []; tap(m)
    expect(pad_on(m) and not m.calls, 'a tap while the pad is up does nothing')
    # 5. a second search: a space and a letter, the history shifted by one slot; spaces at both ends are trimmed
    KB.press(m, 'kb_space'); KB.typ(m, 'x'); KB.press(m, 'kb_space'); m.log = []
    KB.press(m, 'kb_go')
    expect(m.wtext.get(m.edit) == 'Abba x' and KB.field(m) == 'Abba x' and m.fs[HISTORY][:7] == b'Abba x\0' and m.fs[HISTORY][0x100:0x105] == b'Abba\0' and [e for e in m.log if e[0] == 'start'] == [('start', PAGE)],
           f'a second search: the trimmed text in the edit and the bar, the history shifted by one slot ({m.wtext.get(m.edit)!r})')
    # 6. nothing typed (or only spaces): Search does nothing and the pad stays
    m = up(page()); m.log = []
    KB.press(m, 'kb_go')
    expect(not m.log and pad_on(m), 'Search on an empty field does nothing')
    KB.press(m, 'kb_space'); KB.press(m, 'kb_go')
    expect(not [e for e in m.log if e[0] in ('start', 'fopen')] and pad_on(m), 'and on spaces only')


def history_tests(ctx):
    """Text that stock itself puts into the edit (a tap on a history row: 0x4c2edc -> 0x4c2254 writes the keyword into search_edit and the search starts) reaches the bar and the pad gives way."""
    expect = ctx.expect
    m = up(page())
    KB.typ(m, 'Ab')
    tick(m)   # (a poll while typing changes nothing: the edit always holds what the pad has)
    expect(pad_on(m) and KB.field(m) == 'Ab', 'a poll while typing leaves the pad and the text alone')
    m.wtext[m.edit] = 'Queen'   # stock's history tap
    expect(tick(m) and KB.field(m) == 'Queen' and pad_off(m) and m.timers, 'the next poll shows the history text in the bar, hides the pad, and goes on polling')
    expect(m.wtext.get(m.edit) == 'Queen', 'the edit keeps what stock wrote')
    tap(m)
    expect(pad_on(m) and KB.field(m) == 'Queen', 'a tap shows the pad with that text')
    KB.typ(m, 'x')
    expect(KB.field(m) == 'Queenx' and m.wtext.get(m.edit) == 'Queenx', 'typing goes on from it')
    # a tap before the poll ran: the text is picked up at the tap
    m = up(page()); KB.typ(m, 'Ab'); KB.press(m, 'kb_go'); m.wtext[m.edit] = 'Jazz'
    tap(m)
    expect(pad_on(m) and KB.field(m) == 'Jazz', 'a tap before the poll ran picks the text up too')
    # a text longer than the pad takes: cut once, then quiet
    m = up(page()); m.wtext[m.edit] = 'x' * 100
    tick(m)
    expect(m.wtext.get(m.edit) == 'x' * 100 and pad_off(m), 'a history text of 100 bytes is kept whole (the field takes the stock edit\'s 127 bytes)')
    m = up(page()); m.wtext[m.edit] = 'x' * 200
    tick(m)
    expect(KB.field(m).endswith('xxxx') and m.wtext.get(m.edit) == 'x' * 127 and pad_off(m), 'a history text beyond the field\'s 127 bytes is cut in the edit once (the bar shows its end after an ellipsis)')
    tick(m); tick(m)
    expect(m.wtext.get(m.edit) == 'x' * 127, 'and stays')


def research_tests(ctx):
    """A second search starts from nothing (docs/modules/tidalkb.md "Re-search"): stock's search threads only download and its timer parses the answer onto the struct's deque, so the old rows must be gone
    (deque cleared, limit 50, offset 0, scroll 0) when stock's 0x4c2380 runs, as the tab buttons leave them. The machine records the state at that moment (m.snaps)."""
    expect = ctx.expect
    m = up(page())
    for name, a in STRUCTS.items():   # a first search has filled the three result structs (the parse set total / limit and pushed rows; the user scrolled and paged)
        m.setword(a, 123); m.setword(a + 4, 20); m.setword(a + 8, 40); m.setword(a + 12, m.new_deque([0x1000 + i for i in range(5)]))
    m.setword(pod.DATA['TIDAL_SCROLL'][0], 77)
    first = {n: m.word(a + 12) for n, a in STRUCTS.items()}
    KB.typ(m, 'B'); m.snaps = []; m.calls = []
    KB.press(m, 'kb_go')
    expect(len(m.snaps) == 1 and m.snaps[0][0] == [(123, 50, 0, 0)] * 3 and m.snaps[0][1] == 0,
           f'at the moment stock\'s 0x4c2380 runs the three deques are empty, limit 50, offset 0 and the scroll back at the top ({m.snaps})')
    expect({n: m.word(a + 12) for n, a in STRUCTS.items()} == first and len([c for c in m.calls if c[0] == 'deque_clear']) == 3, 'the deques are cleared in place (same objects, stock keeps the pointers)')
    # the order: the reset comes before stock's search (and after nothing that could re-fill it): wait, search, then the page's own start
    expect([e[0] for e in m.log if e[0] in ('wait', 'start')] == ['wait', 'start'], f'stock\'s search ran once ({m.log})')
    # the empty text does not reset (nothing searched)
    m = up(page()); a = STRUCTS['tracks']; m.setword(a + 8, 40); m.setword(a + 12, m.new_deque([1, 2])); KB.press(m, 'kb_go')
    expect(m.word(a + 8) == 40 and len(m.deques[m.word(a + 12)]) == 2 and not m.snaps, 'an empty text searches nothing and leaves the results alone')
    # no deque yet (a page whose init has not run): nothing is cleared, no crash
    m = up(page()); KB.typ(m, 'B'); KB.press(m, 'kb_go')
    expect(m.snaps and m.snaps[0][0] == [(0, 50, 0, 0)] * 3, 'a struct without a deque is only reset')


def order_tests(ctx):
    """The stock routine on an empty field (not reachable from the pad any more, but the page's own IM action still calls it)."""
    expect = ctx.expect
    m = page(); m.wtext[m.edit] = ''; m.log = []; m.calls = []
    m.call(SEARCH, a0=m.edit, a1=0, count=3000000)
    expect([c[1] for c in m.calls if c[0] == 'navigator_to_with_context'] == ['dialog/msginfo_dialog'] and not [e for e in m.log if e[0] in ('start', 'wait')],
           f'stock\'s routine on an empty field is its own "keyboard_keyword" warning, no search ({[c for c in m.calls if c[0] == "navigator_to_with_context"]})')


def fallback_tests(ctx):
    expect = ctx.expect

    def untouched(m, what):
        expect(not busy(m) and not m.timers and (m.bar, EVT_CLICK) not in m.bound and m.props.get((m.edit, 'visible'), 1) == 1 and m.props.get((m.edit, 'sensitive'), 1) == 1 and pad_off_or_never(m),
               f'{what}: nothing of ours is left (no keyboard, no timer, no handler, the stock edit as it was)')
        expect(m.log[:2] == [('edit_set_focus', m.edit, 1), ('t9', m.edit)], f'{what}: stock\'s focus (T9) ran ({m.log})')

    def pad_off_or_never(m): return ours_hidden(m)

    def ours_hidden(m):
        return all(m.props.get((w, 'visible')) == 0 and m.props.get((w, 'sensitive')) == 0 for w in (m.widgets.get(n) for n in ('kb_pad', 'kb_field')) if w)
    # an asset without our widgets (an unedited page): stock
    for gone in ('kb_text', 'kb_pad', 'kb_clear'):
        m = page(); del m.widgets[gone]; bind(m)
        untouched(m, f'an asset without {gone}')
    # a keyboard already up: stock (the page does not take it over)
    m = page(); assert KB.kopen(m, ph='x') == 0; bind(m)
    # (not ours_hidden: the mock looks widgets up by name, so this page's lookup is the other keyboard's pad; in AWTK it is this window's own)
    expect(t9(m) == [('t9', m.edit)] and (m.bar, EVT_CLICK) not in m.bound and not m.timers and m.props.get((m.edit, 'visible'), 1) == 1 and m.props.get((m.widgets['kb_pad'], 'visible')) == 0, 'another keyboard is up: stock\'s T9, that keyboard is left alone')
    # a handler that cannot be bound: the keyboard is let go again, stock
    for what, kw in (('click', dict(widget_on_fail=frozenset([EVT_CLICK]))), ('destroy', dict(widget_on_fail=frozenset([EVT_DESTROY]))), ('Search button', dict(fail_widgets=frozenset(['BTN'])))):
        m = page(); m.fail_widgets = frozenset([m.btn]) if what == 'Search button' else frozenset(); m.widget_on_fail = kw.get('widget_on_fail', frozenset())
        bind(m)
        expect(t9(m) == [('t9', m.edit)] and not busy(m) and not m.timers and m.props.get((m.edit, 'visible'), 1) == 1 and ours_hidden(m), f'{what} handler refused: the pad is detached again, our pad and field hidden, and stock\'s T9 runs')
    # the navbar without the Search button (missing, or not stock's geometry): decided before the pad is attached
    for what in ('no navbar', 'no children', 'other geometry'):
        m = page()
        if what == 'no navbar': del m.widgets['navigationbar_view']
        elif what == 'no children': m.children[m.widgets['navigationbar_view']] = []
        else: m.setword(m.btn + 8, 60)
        bind(m)
        untouched(m, what)
        expect(ours_hidden(m) and m.emit[(m.btn, EVT_CLICK)] == [(SEARCH, PAGE)], f'{what}: our pad and field are hidden, the button keeps stock\'s handler')
    # no window for the edit
    m = page(page_window=0); bind(m)
    expect(t9(m) == [('t9', m.edit)] and not busy(m) and not m.timers, 'an edit in no window: stock\'s T9 (no window, nothing to hide)')
    # no timer for the poll: the pad works all the same (only a history tap waits for the next tap on the bar)
    m = page(timer_fail=True); bind(m)
    expect(not t9(m) and busy(m) == 1 and pad_on(m), 'no timer to be had: the pad is attached all the same')
    KB.typ(m, 'Ab'); KB.press(m, 'kb_go')
    expect(('start', PAGE) in m.log, 'and searches')
    # a pinyin keyboard with Chinese on is the keyboard's own business; its strip covers the history, not the bar (see the asset test)


def navbtn_tests(ctx):
    """The navbar's Search button (stock's page init binds EVT_CLICK -> 0x4c4740 on it before the hook runs; the emitter runs the newest handler first and RET_STOP ends it): our handler takes the tap."""
    expect = ctx.expect
    m = up(page())
    hs = m.emit[(m.btn, EVT_CLICK)]
    expect(len(hs) == 2 and hs[-1] == (SEARCH, PAGE) and hs[0][0] != SEARCH and hs[0][1] == PAGE, f'our handler is bound after stock\'s, so it is first in the emitter ({hs})')
    for a in STRUCTS.values():   # a first search left rows, a page and a scroll offset behind
        m.setword(a, 123); m.setword(a + 4, 20); m.setword(a + 8, 40); m.setword(a + 12, m.new_deque([1, 2, 3]))
    m.setword(pod.DATA['TIDAL_SCROLL'][0], 77)
    KB.press(m, 'kb_space'); KB.typ(m, 'Abba'); KB.press(m, 'kb_space'); m.snaps = []; m.log = []; m.calls = []
    ran = navbtn(m)
    expect(ran == [hs[0][0]], 'stock\'s own handler does not run after ours (RET_STOP)')
    expect(pad_off(m) and m.wtext.get(m.edit) == 'Abba' and KB.field(m) == 'Abba', 'the pad is hidden and the trimmed text is in the bar and the edit')
    expect([e[0] for e in m.log if e[0] in ('fopen', 'fwrite', 'wait', 'start')] == ['fopen', 'fwrite', 'wait', 'start'] and m.fs[HISTORY][:5] == b'Abba\0', f'stock\'s search ran exactly once ({m.log})')
    expect(len(m.snaps) == 1 and m.snaps[0][0] == [(123, 50, 0, 0)] * 3 and m.snaps[0][1] == 0, f'the result structs were reset first, as the action key does ({m.snaps})')
    # an empty text: nothing happens (no history write, no warning dialog), the pad stays, stock's handler is stopped too
    m = up(page()); m.log = []; m.calls = []
    ran = navbtn(m)
    expect(len(ran) == 1 and not m.log and pad_on(m) and not [c for c in m.calls if c[0] == 'navigator_to_with_context'], f'an empty text does nothing and stock\'s handler is stopped ({m.log})')
    # a history row's text that the poll has not shown yet is what is searched
    m = up(page()); KB.typ(m, 'Ab'); m.wtext[m.edit] = 'Queen'; m.log = []
    navbtn(m)
    expect(m.fs[HISTORY][:6] == b'Queen\0' and len(searches(m)) == 1 and KB.field(m) == 'Queen' and pad_off(m), 'a history text stock wrote is searched and shown')
    # (the engine machine's libc runs the stock history file through its own in-memory files: what the search read is the edit's text when the search started)
    # pinyin pending (Chinese layer, nihao typed, no candidate picked): the button commits it first as the action key does (its first candidate) and searches that
    m = up(page(zh=True)); KB.press(m, 'kb_lang'); KB.typ(m, 'nihao')
    expect(KB.field(m) == '' and KB.strip_on(m), 'nihao is pending: the field\'s committed text is still empty')
    m.log = []
    ran = navbtn(m)
    expect(len(ran) == 1 and sent(m) == '你好' and len(searches(m)) == 1 and pad_off(m), f'the pending nihao is committed (你好) and searched, stock\'s handler stopped ({m.log})')
    m = up(page(zh=True)); KB.typ(m, 'Wo'); KB.press(m, 'kb_lang'); KB.typ(m, 'nihao'); m.log = []
    navbtn(m)
    expect(sent(m) == 'Wo你好' and len(searches(m)) == 1, 'committed text plus a pending composition: the whole text is searched, not the prefix')
    # the page's destroy: a stale tap on the button gets stock's search (the handler passes it on)
    m = up(page()); KB.typ(m, 'Ab'); m.fire(EVT_DESTROY, PAGE); m.log = []
    ran = navbtn(m)
    expect(len(ran) == 2 and ran[-1] == SEARCH, 'after the page\'s destroy our handler passes the tap to stock\'s')


def destroy_tests(ctx):
    expect = ctx.expect
    m = up(page())
    KB.typ(m, 'Ab')
    m.calls = []
    m.fire(EVT_DESTROY, PAGE)
    expect(('timer_remove', 0x777) in m.calls and not busy(m), 'the page\'s destroy removes the poll and detaches the keyboard')
    m.log = []; m.calls = []
    tick(m); tap(m)   # (the mocked timer list keeps the removed timer: a stale callback must do nothing)
    expect(not m.timers and not kb_calls(m) and not t9(m) and not busy(m), 'after the destroy a stale timer and a tap do nothing')
    # the next Tidal search page takes the keyboard again (text and state start fresh)
    m = page(); bind(m); KB.typ(m, 'Ab'); m.fire(EVT_DESTROY, PAGE)
    m.timers = []; bind(m)
    expect(busy(m) == 1 and pad_on(m) and KB.field(m) == '' and not t9(m), 'a second page after the first one\'s destroy: the pad attached again, empty')
    # a second Tidal page while the first is still up: stock's T9 for the second, the first untouched; the old window's destroy then detaches
    m = page(); bind(m)
    m.page_window = PAGE + 0x1000
    m.call(BIND, a0=PAGE + 0x1000, a1=m.edit, count=3000000)
    expect(t9(m) == [('t9', m.edit)] and busy(m) == 1, 'a page opened while one is attached: stock\'s T9 for it, the first keeps the keyboard')
    m.fire(EVT_DESTROY, PAGE)
    expect(not busy(m), 'and the first one\'s destroy lets the keyboard go')


SECTIONS = [hook_tests, asset_tests, life_tests, history_tests, research_tests, navbtn_tests, order_tests, fallback_tests, destroy_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

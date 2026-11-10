"""Now Playing: the playing_page_init hook and its timer (the tint, the remaining time, the rounded corners), the tone
formula and its contrast, the A-B marker immediates, and the geometry of the built page assets."""
import os, random, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_style, mod_icons, mod_lockscreen, mod_nowplaying as mn

INIT = pod.PLAYING_INIT                   # playing_page_init
COVER_SRC = pod.DATA['COVER_SRC'][0]
WIN = 0x24000000
EVT_DESTROY, EVT_AFTER_PAINT = O['EVT_DESTROY'], O['EVT_AFTER_PAINT']


class NowMachine(Machine):
    """Machine plus what the Now Playing code calls: the style API, the player's position, files read through stdio,
    the stock init the hook wraps."""
    FIRE_WIN = WIN

    def __init__(self):
        super().__init__()
        self.handlers[INIT + 12] = 'stock_playing_resume'
        self.handlers[pod.NP_MODE_BUTTON] = 'np_mode_button'
        self.styles = []          # (widget, "normal:bg_color", uint32)
        self.style_ret = 0
        self.pt = (30, 200, 1)    # get_playtimeandlength: pos, len, return value
        self.blobs = {}           # path -> bytes (fopen / fread / fclose)
        self.pos = {}
        self.stock_ret = 0
        self.opened = []
        self.texts = {}           # label handle -> its text (latin-1 chars of the UTF-8 bytes, as read_cstr returns)
        self.get_ret = 0          # nonzero: widget_get_text finds no text
        self.set_fail = set()     # label handles whose widget_set_text_utf8 fails (nothing stored)
        self.wide = {}            # label handle -> raw code points for widget_get_text (over texts)
        self.bar = 0              # the status bar's handle (0: the window manager has none)
        self.bar_styles = []      # (bar, "normal:bg_color", uint32)
        self.bar_style_ret = 0
        self.on_fail = set()      # event types whose widget_on returns 0 (refused)

    def with_bar(self, top=WIN):
        """The window manager with a navbar and a status bar among its children; `top` is its top normal window."""
        nav = self.alloc(0x80); self.bar = self.alloc(0x80)
        self.children[self.wm] = [nav, self.bar]; self.types[nav] = 'system_bar_bottom'; self.types[self.bar] = 'system_bar'
        self.top_main = top
        return self

    def bar_color(self): return self.bar_styles[-1][2] if self.bar_styles else None
    def bar_calls(self): return [c for c in self.calls if c[0] == 'widget_set_style' and c[1] == self.bar]
    def info_page(self, stock, quality=True):
        """The info page's labels (name -> the text stock wrote); returns {name: handle}."""
        out = {}
        for n, t in stock.items():
            out[n] = self.widget(n); self.texts[out[n]] = t.encode('utf-8').decode('latin-1')
        if quality and 'label_info' in stock: self.widget('np_quality')
        return out

    def label(self, name):
        if name == 'label_info' and self.props.get((self.widgets.get('np_quality'), 'visible')) == 1: name = 'np_quality'   # the visible quality line: np_quality while it is shown
        return self.texts[self.widgets[name]].encode('latin-1').decode('utf-8')

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'stock_playing_resume':
            self.calls.append(('stock_playing_init', a0, a1)); ret = self.stock_ret
        elif name == 'np_mode_button':   # stock 0x539888, the mode button's picture
            self.calls.append(('np_mode_button', a0)); ret = 0
        elif name == 'widget_set_style':
            v = self.word(a2 + 8); self.calls.append(('widget_set_style', a0, self.read_cstr(a1), v))
            ret = self.bar_style_ret if a0 == self.bar else self.style_ret
            if ret == 0: (self.bar_styles if a0 == self.bar else self.styles).append((a0, self.read_cstr(a1), v))
        elif name == 'widget_on' and a1 in self.on_fail:
            self.calls.append(('widget_on', a0, a1, a2, a3)); ret = 0
        elif name == 'mclGetPlayStatus':   # the player is stopped: the episode timer (pc_note) saves nothing
            ret = 0
        elif name == 'value_set_uint32':
            self.setword(a0, 7); self.setword(a0 + 8, a1); ret = a0
        elif name == 'get_playtimeandlength':
            pos, ln, r = self.pt
            self.setword(a0, pos); self.setword(a1, ln); self.calls.append(('get_playtimeandlength',)); ret = r
        elif name == 'widget_set_text_utf8':   # the labels keep their text (the info page is read back)
            t = self.read_cstr(a1); self.calls.append(('widget_set_text_utf8', a0, t)); ret = 1 if a0 in self.set_fail else 0
            if not ret: self.texts[a0] = t
        elif name == 'widget_get_text':   # the label's wide text (32 bit code points; NULL for a label without one, or while get_ret is set: a failed read); the payload encodes it (pod_text_utf8)
            t = self.texts.get(a0); self.calls.append(('widget_get_text', a0)); ret = 0
            if a0 in self.wide and not self.get_ret:   # raw code points (a test of bad ones: no surrogate survives a Python str)
                cps = self.wide[a0]; ret = self.alloc(4 * len(cps) + 4); self.u.mem_write(ret, struct.pack(f'<{len(cps) + 1}I', *cps, 0))
            elif t is not None and not self.get_ret:
                t = t.encode('latin-1').decode('utf-8'); ret = self.alloc(4 * len(t) + 4)
                self.u.mem_write(ret, struct.pack(f'<{len(t) + 1}I', *map(ord, t), 0))
        elif name == 'fopen' and self.read_cstr(a0) in self.blobs:
            path = self.read_cstr(a0); h = self.alloc(4); self.pos[h] = 0; self.fh = (h, path)
            self.opened.append(path); self.calls.append(('fopen', path, self.read_cstr(a1))); ret = h
        elif name == 'fread' and a3 in self.pos:
            data = self.blobs[self.fh[1]]; n = min(a1 * a2, len(data) - self.pos[a3])
            if n: self.u.mem_write(a0, data[self.pos[a3]:self.pos[a3] + n])
            self.pos[a3] += n; ret = n // a1; self.calls.append(('fread', n))
        elif name == 'fseek' and a0 in self.pos:
            self.calls.append(('fseek',)); ret = 0
        elif name == 'ftell' and a0 in self.pos:
            ret = len(self.blobs[self.fh[1]])
        elif name == 'fclose' and a0 in self.pos:
            ret = 0
        if ret is not None:
            self._icount += 1
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    def page(self, labels=True, art=True):
        """The widgets of the page the hook looks up."""
        for n in (('np_remaining', 'label_playlen') if labels else ()) + (('img_playcover',) if art else ()): self.widget(n)
        return self.widgets

    def src(self, v): self.setword(COVER_SRC, v)

    def init(self, win=WIN, count=6000000):
        self.calls = []; self.icount = 0
        ret = self.call(INIT, a0=win, a1=0x55, count=count)
        return ret

    def tick(self, count=6000000): self.call(PSYMS['np_tick'], count=count); return self.calls

    def jpeg(self, path, data=b'cover-bytes' * 40, pix=None, size=(4, 4)):
        """A cover file: its bytes for the key, and what the stock loader decodes it to (RGBA8888)."""
        self.blobs[path] = data; self.present.add(path)
        w, h = size
        self.images['file://' + path] = (w, h, pix if pix is not None else bytes([200, 40, 40, 255]) * (w * h))
        self.load_image = 0

    def set_texts(self): return [(c[1], c[2]) for c in self.calls if c[0] == 'widget_set_text_utf8']
    def visible(self, name): return self.props.get((self.widgets[name], 'visible'))



def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    stock = open(os.path.join(paths.find_stock() or os.path.join(os.path.dirname(WORK), 'stock'), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]

    # ------------------------------------------------------------------ the hook is installed as pinned
    hook = MANIFEST['hook_playing']
    expect(hook['addr'] == INIT == 0x53d1e4 and hook['target'] == PSYMS['m1plus_playing_init'], 'the manifest records the Now Playing hook and its target')
    expect(pod.PLAYING_INIT_PROLOGUE == (0x3c1c004c, 0x279c6cec, 0x0399e021) and tuple(word(stock, INIT + 4 * i) for i in range(3)) == pod.PLAYING_INIT_PROLOGUE,
           'stock has the three PIC prologue words the hook pins (playing_page_init)')
    expect((word(built, INIT), word(built, INIT + 4), word(built, INIT + 8)) == (pod.j(PSYMS['m1plus_playing_init']), 0, pod.PLAYING_INIT_PROLOGUE[2]),
           'the built demo has `j m1plus_playing_init; nop` over the first two prologue words')
    expect(0x4c0000 + 0x6cec + INIT == pod.GP, 'the prologue computes $gp = 0xa03ed0')
    gp = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS['stock_playing_init_trampoline'] - pod.BASE)
    expect(gp == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(INIT + 12), 0), 'the trampoline restores $gp and resumes at the 4th instruction')
    expect((COVER_SRC, O['COVER_SRC_BUSY'], O['COVER_SRC_EMBEDDED'], O['COVER_SRC_FOLDER'], O['COVER_SRC_CACHE'], O['RET_REPEAT']) == (0x97cad8, 1, 2, 3, 5, 8),
           'the cover source type word and its values, the repeat answer')

    # ------------------------------------------------------------------ A-B markers (five pinned immediates)
    edits = mn.marker_edits()
    expect(len(edits) == 5 and all(word(stock, a) == o and word(built, a) == n for a, (o, n) in edits.items()),
           'the five marker immediates are stock words in stock and the new ones in the build')
    sl = mn.SLIDER
    expect({a: n & 0xffff for a, (_, n) in edits.items()} == {mn.MARKER_X_SCALE: sl[2], mn.MARKER_X_OFFSET: sl[0], **{a: sl[1] + sl[3] // 2 + 7 for a in mn.MARKER_Y}},
           f'markers run x {sl[0]} + pos * {sl[2]} / len at y {sl[1] + sl[3] // 2 + 7} (bar centre + 7, as stock 357 + 7 = 364)')
    expect(all((word(built, a) >> 16) == (o >> 16) for a, (o, _) in edits.items()), 'only the 16-bit immediates change')
    expect(all(word(stock, a) == w and word(built, a) == w for a, w in mn.MARKER_PINS.items()), 'the two functions\' prologues and their call sites are pinned and untouched')

    # ------------------------------------------------------------------ installed hook: stock first, then ours
    m = NowMachine(); m.page(); m.src(0)
    queue_btn = m.widget('btn_queue')
    ret = m.init()
    names = m.names()
    expect(ret == 0 and m.calls[0] == ('stock_playing_init', WIN, 0x55), f'the stock init runs first, with its arguments, and its result is returned ({names[:3]})')
    destroy = [c for c in m.calls if c[0] == 'widget_on' and c[2] == EVT_DESTROY]
    expect(len(destroy) == 1 and destroy[0][1] == WIN and destroy[0][3] == PSYMS['np_on_destroy'] and destroy[0][4] == WIN,
           'EVT_DESTROY is registered once on the window with the window as its context')
    expect(m.timers == [(PSYMS['np_tick'], O['NP_TICK_MS'])] and O['NP_TICK_MS'] == 500, 'one page timer, 500 ms, created once')
    paint = [c for c in m.calls if c[0] == 'widget_on' and c[2] == EVT_AFTER_PAINT]
    expect(len(paint) == 1 and paint[0][1] == m.widgets['img_playcover'] and paint[0][3] == PSYMS['np_on_art_paint'], 'the cover widget paints its corners')
    qc = [c for c in m.calls if c[0] == 'widget_on' and c[1] == queue_btn and c[2] == O['EVT_CLICK']]
    expect(len(qc) == 1 and qc[0][3] == PSYMS['np_on_queue'], 'the queue button gets one click handler after the stock init (our Queue page, docs/modules/queue.md; it answers RET_OK where the stock drawer should open)')
    # the timer's first run is part of the init: no cover (type 0) -> the neutral tone, once
    expect(m.styles == [(WIN, 'normal:bg_color', O['NP_NEUTRAL'])], f'no cover file: the neutral tone ({[hex(x[2]) for x in m.styles]})')
    m.screen(False); m.calls = []; m.tick()
    expect(not any(c[0] == 'get_playtimeandlength' for c in m.calls), 'screen-off tick skips visual time work')
    expect(('timer_modify', 0x777, 1000) in m.calls, 'screen-off tick slows the page timer')
    m.tick(); expect(not any(c[0] == 'timer_modify' for c in m.calls), 'unchanged dark interval is not modified again')
    m.screen(True); m.calls = []; m.tick()
    expect(('timer_modify', 0x777, 500) in m.calls, 'first lit tick restores the page timer')
    expect(any(c[0] == 'get_playtimeandlength' for c in m.calls), 'first lit tick catches up')
    m.screen(False); m.timer_modify_fail = True; m.tick(); m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'a failed retime is retried')
    m.timer_modify_fail = False; m.tick(); m.tick()
    expect(not any(c[0] == 'timer_modify' for c in m.calls), 'a successful retry is remembered')
    m.screen(True)
    m.init(win=WIN + 0x100); m.screen(False); m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'a replacement page retimes its own fresh timer')
    m.init(win=WIN)

    # destroy: the timer goes, nothing runs afterwards
    m.calls = []
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(('timer_remove', 0x777) in m.calls, 'EVT_DESTROY removes the timer')
    m.calls = []; r = m.call(PSYMS['np_tick'], count=200000)
    expect(r == 0 and not m.calls, 'a late timer callback does nothing and ends itself')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(m.calls == [], 'a second destroy does nothing')
    m.call(PSYMS['np_on_art_paint'], a0=0, a1=0, count=100000)
    expect(m.fills == [], 'no paint after destroy')

    # a second page before the first one's destroy: the old timer goes, one new
    m = NowMachine(); m.page(); m.src(0)
    m.init(); m.init(win=WIN + 0x100)
    expect(sum(c[0] == 'timer_remove' for c in m.calls) == 1 and sum(c[0] == 'timer_add' for c in m.calls) == 1,
           'a page built over a live one replaces the old timer')
    m.calls = []; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(m.calls == [], 'the earlier page\'s destroy leaves the new one alone')
    m.call(PSYMS['np_on_destroy'], a0=WIN + 0x100, a1=0)
    expect(('timer_remove', 0x777) in m.calls, 'the new page\'s destroy removes its timer')

    # ------------------------------------------------------------------ fall back to stock
    m = NowMachine(); m.page(); m.stock_ret = 0x10
    ret = m.init()
    expect(ret == 0x10 and not m.timers and 'access' not in m.names(), 'a failed stock init is returned and nothing starts')
    m = NowMachine(); m.page()
    ret = m.init(win=0)
    expect(not m.timers and not m.styles, 'no window: nothing starts')
    m = NowMachine(); m.page(); m.timer_fail = True
    ret = m.init()
    expect(ret == 0 and not m.timers and not m.styles and not any(c[0] == 'widget_on' and c[2] == EVT_AFTER_PAINT for c in m.calls),
           'no timer: the page stays stock (no style, no corner painter)')
    m.calls = []; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); expect(m.calls == [], 'and its destroy handler has nothing to undo')
    # a widget of the asset missing: that part is off, the rest works
    m = NowMachine(); m.page(labels=False); m.src(0); m.pt = (10, 100, 1)
    m.init(); m.tick()
    expect(m.timers and m.styles and not m.set_texts(), 'without the labels: the tint still runs, the time does not')
    m = NowMachine(); m.page(art=False); m.src(0)
    m.init()
    expect(m.timers and not any(c[0] == 'widget_on' and c[2] == EVT_AFTER_PAINT for c in m.calls), 'without the cover widget: no corner painter')
    m = NowMachine(); m.page(); m.src(0); m.style_ret = 0x10
    m.init()
    expect(not any(c[0] == 'widget_invalidate_force' for c in m.calls), 'a style call that fails invalidates nothing')

    # ------------------------------------------------------------------ remaining time
    def fmt(pos, ln):
        mm = NowMachine(); out = mm.alloc(32)
        mm.call(PSYMS['np_format_remaining'], out, 32, count=100000, a2=pos, a3=ln)
        return mm.read_cstr(out)
    cases = {(0, 0): '-0:00', (0, 1): '-0:01', (0, 59): '-0:59', (0, 60): '-1:00', (0, 265): '-4:25', (0, 3599): '-59:59', (0, 3600): '-1:00:00',
             (0, 3723): '-1:02:03', (100, 100): '-0:00', (130, 100): '-0:00', (30, 200): '-2:50',
             (3599, 7200): '-1:00:01', (-5, 10): '-0:15', (0, 36000): '-10:00:00'}
    got = {k: fmt(*k) for k in cases}
    expect(got == cases, f'-m:ss (no leading zero) from 0:00 to over an hour, a position past the end: {[(k, got[k], v) for k, v in cases.items() if got[k] != v]}')
    m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1)
    m.init()
    expect(m.set_texts() == [(m.widgets['np_remaining'], '-2:50')], f'the label shows the time left ({m.set_texts()})')
    expect(m.visible('np_remaining') == 1 and m.visible('label_playlen') == 0, 'np_remaining shows and the stock total hides')
    m.tick(); expect(not m.set_texts(), 'an unchanged time is not set again')
    m.pt = (31, 200, 1); m.tick(); expect(m.set_texts() == [(m.widgets['np_remaining'], '-2:49')], 'the next second is')
    m.pt = (500, 200, 1); m.tick(); expect(m.set_texts() == [(m.widgets['np_remaining'], '-0:00')], 'a position past the length reads -0:00')
    m.pt = (0, 0, 1); m.tick(); expect(m.visible('np_remaining') == 0 and m.visible('label_playlen') == 1, 'a length of 0: stock\'s total shows again')
    m.pt = (10, 100, 1); m.tick(); expect(m.visible('np_remaining') == 1 and m.visible('label_playlen') == 0, 'and the remaining time comes back')
    m.pt = (10, 100, -1); m.tick(); expect(m.visible('np_remaining') == 0 and m.visible('label_playlen') == 1, 'a failed query: stock\'s total')
    m.pt = (10, 100, 1); m.tick(); m.pt = (11, -5, 1); m.tick()
    expect(m.visible('label_playlen') == 1, 'a negative length: stock\'s total')
    m.pt = (10, 100, 1)
    expect(m.props.get((m.widgets['label_playlen'], 'sensitive')) is None, 'sensitivity is the asset\'s (both labels insensitive), only visibility is toggled')

    # the elapsed time: np_elapsed shows "m:ss" from the same query and label_playtime (stock's "01:27", rewritten on stock's tick) hides,
    # so stock's text is never painted; stock's label is never written
    def elapsed(pt=(30, 200, 1), both=True):
        m = NowMachine(); m.page(); m.src(0); m.pt = pt
        if both: m.widget('np_elapsed')
        h = m.widget('label_playtime'); m.texts[h] = '00:30'
        m.init(); return m, h
    eset = lambda m: [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets.get('np_elapsed')]
    m, h = elapsed()
    expect(eset(m) == ['0:30'] and m.visible('np_elapsed') == 1 and m.visible('label_playtime') == 0, f'np_elapsed shows 0:30 and stock\'s elapsed hides ({eset(m)})')
    expect(not any(c[0] == 'widget_set_text_utf8' and c[1] == h for c in m.calls) and m.texts[h] == '00:30', 'stock\'s label is not written')
    m.calls = []; m.tick(); expect(not eset(m), 'an unchanged second is not set again')
    for pos, want in ((87, '1:27'), (600, '10:00'), (3723, '1:02:03')):
        m.pt = (pos, 7200, 1); m.calls = []; m.tick(); expect(eset(m) == [want], f'{pos} s reads {want} ({eset(m)})')
    m.pt = (9000, 7200, 1); m.calls = []; m.tick(); expect(eset(m) == ['2:00:00'], 'a position past the length reads the length')
    m.pt = (10, 100, -1); m.tick(); expect(m.visible('np_elapsed') == 0 and m.visible('label_playtime') == 1, 'a failed query: stock\'s elapsed')
    m.pt = (10, 100, 1); m.tick(); expect(m.visible('np_elapsed') == 1 and m.visible('label_playtime') == 0, 'and ours comes back')
    m, h = elapsed(both=False)
    expect(m.props.get((h, 'visible')) is None and m.visible('np_remaining') == 1, 'a page without np_elapsed: stock\'s elapsed untouched, the remaining time still ours')
    m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.widget('np_elapsed'); m.init()
    expect(not eset(m) and m.visible('np_elapsed') is None, 'a page without label_playtime: np_elapsed stays hidden')
    m, h = elapsed(); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); m.pt = (40, 200, 1); m.calls = []; m.tick()
    expect(not eset(m), 'after the page is gone a stray tick writes nothing')

    # ------------------------------------------------------------------ the info page's lines (np_info)
    from awtk_text import Ttf, StbText
    stock_en = {'label_info': 'FLAC|44.1kHz|16bit|950kbps', 'label_album': 'Album:Kid A', 'label_genre': 'Genres:Rock',
                'label_year': 'Era:1999', 'label_size': 'File Size:35.92MB', 'label_location': 'Location:SD:/Music/Kid A'}
    want_en = {'label_info': 'FLAC | 44.1 kHz | 16-bit | 950 kbps', 'label_album': 'Album: Kid A', 'label_genre': 'Genre: Rock',
               'label_year': 'Year: 1999', 'label_size': 'File Size: 35.92 MB', 'label_location': 'Location: SD:/Music/Kid A'}
    def info(stock, lang=None, quality=True, **kw):
        m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.set_language(lang) if lang else None
        for k, v in kw.items(): setattr(m, k, v)
        m.info_page(stock, quality); m.init(); return m
    sets = lambda m: [c for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] != m.widgets['np_remaining']]
    m = info(stock_en)
    expect({n: m.label(n) for n in stock_en} == want_en, f'English: "Label: value", spaced units, Genre and Year ({ {n: m.label(n) for n in stock_en} })')
    expect(len(sets(m)) == 6, f'one rewrite per line ({len(sets(m))})')
    m.calls = []; m.tick(); m.tick()
    expect(not sets(m), 'ticks after that leave the lines alone (no rewrite loop)')
    m.texts[m.widgets['label_album']] = 'Album:Kid A'            # stock writes the line again (a track change)
    m.calls = []; m.tick()
    expect(m.label('label_album') == 'Album: Kid A' and len(sets(m)) == 1, 'stock writing a line again is answered once, that line only')
    m.texts[m.widgets['label_album']] = 'Album:Other'; m.tick(); m.tick()
    expect(m.label('label_album') == 'Album: Other', 'and the next track\'s text the same way')
    # values: unknown, zero size, integer kHz, a wide DSD line, units only where they belong, the first colon only
    cases = {'label_album': {'Album:Unknown': 'Album: Unknown', 'Album:Mega 2MB': 'Album: Mega 2MB', 'Album:A: B': 'Album: A: B',
                              'Album: Already': 'Album: Already', 'Album:  two spaces': 'Album: two spaces'},
             'label_size': {'File Size:0.00MB': 'File Size: 0.00 MB', 'File Size: 7.10 MB': 'File Size: 7.10 MB'},
             'label_year': {'Era:Unknown': 'Year: Unknown', 'Era:0': 'Year: 0'},
             'label_info': {'MP3|48kHz|16bit|320kbps': 'MP3 | 48 kHz | 16-bit | 320 kbps',
                            'DSD256|11.3kHz|1bit|11289kbps': 'DSD256|11.3 kHz|1-bit|11289 kbps',
                            'FLAC|352.8kHz|32bit|22579kbps': 'FLAC|352.8 kHz|32-bit|22579 kbps',
                            'FLAC | 44.1 kHz | 16-bit | 950 kbps': 'FLAC | 44.1 kHz | 16-bit | 950 kbps', 'FLAC': 'FLAC'}}
    bad = []
    for lbl, table in cases.items():
        for before, after in table.items():
            m = info({lbl: before}); got = m.label(lbl)
            if got != after: bad.append((before, got, after))
    expect(not bad, f'value cases ({bad})')
    # the wide lines still fit the 272 px label at 18 px (a tight line when the spaced one is too wide)
    ttf = Ttf(os.path.join(raw, 'fonts', 'default.ttf')); w18 = lambda t: StbText(ttf, 18).layout(t)[1]
    li = mn.find(mn.awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read()), 'label_info')
    pcm = [f'{c}|{r}kHz|{b}bit|{k}kbps' for c in ('FLAC', 'ALAC', 'WAV', 'APE', 'AIFF', 'MP3', 'OGG') for r, b, k in
           (('44.1', 16, 950), ('48', 24, 2300), ('96', 24, 2800), ('192', 24, 9216), ('352.8', 24, 16934), ('384', 32, 24576))]
    dsd = [f'{c}|{r}kHz|1bit|{k}kbps' for c in ('DSD64', 'DSD128', 'DSD256', 'DSD512') for r, k in
           (('2822.4', 5644), ('5644.8', 11289), ('11289.6', 22579), ('22579.2', 45158))]
    over = []
    for t in pcm + dsd:
        m = info({'label_info': t}); out = m.label('label_info')
        if w18(out) > li.w: over.append((out, w18(out)))
    expect(not over and li.w == 304 and li.x == 8, f'every quality line, DSD included, fits the {li.w} px label ({over})')
    spaced = [t for t in pcm + dsd if info({'label_info': t}).label('label_info').count(' | ') == 3]
    expect(all(len(info({'label_info': t}).label('label_info')) <= O['NP_INFO_SPACED'] for t in spaced) and 'FLAC|44.1kHz|16bit|950kbps' in spaced
           and 'FLAC|192kHz|24bit|9216kbps' in spaced and not [t for t in dsd if t in spaced] and len(spaced) >= 30,
           f'the usual lines keep their spaced bars ({len(spaced)} of {len(pcm) + len(dsd)}); the DSD lines go tight')
    # every language: the stock label and value text is kept, Genre and Year are our keys in that language
    import pod_i18n
    for lang in pod_i18n.LOCALES:
        written = {'label_album': '专辑:Kid A', 'label_genre': 'X:Rock', 'label_year': 'Y:1999', 'label_size': 'Z:3.50MB', 'label_location': 'W:SD:/a'}
        m = info(written, lang)
        T = pod_i18n.TEXT
        expect(m.label('label_genre') == f'{T["Genre"][lang]}: Rock' and m.label('label_year') == f'{T["Year"][lang]}: 1999'
               and m.label('label_album') == '专辑: Kid A' and m.label('label_size') == 'Z: 3.50 MB' and m.label('label_location') == 'W: SD:/a',
               f'{lang}: Genre / Year from our table, the other labels as stock wrote them ({m.label("label_genre")}, {m.label("label_year")})')
    # anything unexpected: stock's text stays
    keep = {'label_album': 'Unknown', 'label_genre': ':Rock', 'label_size': '', 'label_location': 'x' * 600}
    m = info(keep)
    expect(all(m.label(n) == keep[n] for n in keep) and not sets(m), 'no colon, a leading colon, an empty text, a text too long to have been read whole: untouched')
    m = info({'label_info': 'A' * 600}); expect(m.visible('np_quality') is None and m.label('label_info') == 'A' * 600 and not sets(m), 'a quality text too long to read whole: stock\'s label stays visible')
    # stock's widget_get_text_utf8 ignores its size and overran the 512 byte buffer with a longer tag: the payload encodes the wide text itself and leaves one that does not fit
    for t in ('Album:' + 'x' * 600, 'Album:' + '歌' * 200, 'Title:' + '😀' * 130, 'Album:' + 'x' * 506):
        m = info({'label_album': t}); k = len(t.encode('utf-8'))
        expect(m.label('label_album') == t and not sets(m), f'a tag of {k} bytes (the buffer holds 511 and a NUL): untouched, nothing written past the buffer')
    m = info({'label_album': 'Album:' + 'x' * 505}); t = m.label('label_album')
    expect(t == 'Album: ' + 'x' * 505, 'a text of 511 bytes still fits and is rewritten')
    m = info(stock_en, get_ret=0x10)
    expect(all(m.label(n) == stock_en[n] for n in stock_en) and not sets(m), 'a failed read of the text: untouched')
    m = NowMachine(); m.page(); m.src(0); m.info_page({'label_album': 'Album:X'}); m.init()
    expect(m.label('label_album') == 'Album: X', 'an info page with only some of its labels works for those')
    # ---- the quality line: stock writes label_info on EVERY tick; the visible line is np_quality, written once per text
    QS, QF = 'FLAC|44.1kHz|16bit|950kbps', 'FLAC | 44.1 kHz | 16-bit | 950 kbps'
    qset = lambda m: [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets.get('np_quality')]
    li_set = lambda m: [c for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets['label_info']]
    m = info({'label_info': QS}); h_q, h_s = m.widgets['np_quality'], m.widgets['label_info']
    expect(m.texts[h_q] == QF and m.visible('np_quality') == 1 and m.visible('label_info') == 0 and m.props.get((h_s, 'sensitive')) == 0,
           'the formatted line is in np_quality, shown; stock\'s label_info hidden and insensitive')
    expect(not li_set(m), 'label_info itself is never written by the payload')
    m.calls = []
    for _ in range(10):
        m.texts[h_s] = QS; m.tick()     # stock rewrites the compact text on its tick
    expect(not qset(m) and not li_set(m) and m.texts[h_q] == QF and m.visible('np_quality') == 1 and m.visible('label_info') == 0,
           'stock rewriting label_info 10 times: the visible line stays the formatted text, written 0 more times, label_info untouched and hidden')
    m.texts[h_s] = 'MP3|48kHz|16bit|320kbps'; m.calls = []; m.tick()
    first = qset(m); m.tick()
    expect(first == ['MP3 | 48 kHz | 16-bit | 320 kbps'] and not qset(m), f'a quality change on a track change updates np_quality once ({qset(m)})')
    # after the takeover, any text that cannot be shown as ours gives the line back to stock (never a stale line), and
    # the next good text takes it over again
    # stock_back / ours: who shows the line, and m.label('label_info') (the visible line) is the text the screen has
    stock_back = lambda m, t: m.visible('np_quality') == 0 and m.visible('label_info') == 1 and m.label('label_info') == t
    ours = lambda m, t: m.visible('np_quality') == 1 and m.visible('label_info') == 0 and m.label('label_info') == t
    m.texts[h_s] = 'A' * 600; m.calls = []; m.tick()
    expect(not qset(m) and stock_back(m, 'A' * 600), 'an unreadable (too long) stock text after the takeover: np_quality hidden, stock label_info shown with its text')
    m.texts[h_s] = QS; m.calls = []; m.tick()
    expect(qset(m) == [QF] and ours(m, QF), 'readable again: np_quality takes the line over again')
    m.texts[h_s] = 'AAC|44.1kHz|16bit|256kbps'; m.get_ret = 1; m.calls = []; m.tick(); m.get_ret = 0
    expect(not qset(m) and stock_back(m, 'AAC|44.1kHz|16bit|256kbps'), 'a failed read after the takeover: stock label_info shown with the new text, np_quality hidden')
    m.calls = []; m.tick()
    expect(qset(m) == ['AAC | 44.1 kHz | 16-bit | 256 kbps'] and ours(m, 'AAC | 44.1 kHz | 16-bit | 256 kbps'), 'read works again: taken over again')
    m.texts[h_s] = 'MP3|48kHz|16bit|320kbps'; m.set_fail.add(h_q); m.calls = []; m.tick(); m.set_fail.clear()
    expect(stock_back(m, 'MP3|48kHz|16bit|320kbps') and m.texts[h_q].startswith('AAC'),
           f'a failed write of a new quality text: the visible line is stock\'s new MP3 text, not the hidden old AAC ({m.label("label_info")})')
    m.calls = []; m.tick()
    expect(qset(m) == ['MP3 | 48 kHz | 16-bit | 320 kbps'] and ours(m, 'MP3 | 48 kHz | 16-bit | 320 kbps'), 'the write works again: taken over again')
    m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.info_page({'label_info': QS}); m.set_fail.add(m.widgets['np_quality']); m.init(); m.tick()
    expect(m.visible('np_quality') is None and m.visible('label_info') is None and m.label('label_info') == QS, 'a write that never works: never taken over, stock as it was')
    m = info({'label_info': QS}, quality=False)
    expect(m.texts[m.widgets['label_info']] == QS and m.visible('label_info') is None and not li_set(m), 'no np_quality (creation failed): stock label_info is visible, untouched')
    m.texts[m.widgets['label_info']] = QS; m.calls = []; m.tick(); m.tick()
    expect(not li_set(m) and not any(c[0] == 'widget_set_visible' and c[1] == m.widgets['label_info'] for c in m.calls), 'and it stays stock')
    m = NowMachine(); m.page(); m.src(0); m.widget('np_quality'); m.init()
    expect(m.visible('np_quality') is None, 'no label_info: np_quality stays hidden')
    m = info({'label_info': QS}); m.calls = []; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); m.texts[m.widgets['label_info']] = 'MP3|48kHz|16bit|320kbps'; m.tick()
    expect(not qset(m), 'a stale timer after the page is destroyed writes nothing')
    m = info({'label_info': QS})
    h_q = m.widgets['np_quality']; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    m.widgets['np_quality'] = m.alloc(0x80); m.widgets['label_info'] = m.alloc(0x80); m.texts[m.widgets['label_info']] = QS.encode().decode('latin-1')
    m.init(win=WIN + 4); nq = m.widgets['np_quality']
    expect(m.texts.get(nq) == QF and m.visible('np_quality') == 1, 'leaving and re-entering the page: the new page shows its own np_quality')
    m = info(stock_en); m.calls = []; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); m.texts[m.widgets['label_album']] = 'Album:Z'; m.tick()
    expect(m.label('label_album') == 'Album:Z' and not sets(m), 'after the page is gone a stray tick touches nothing')

    # ------------------------------------------------------------------ the tone
    mm = NowMachine()
    def c_tone(r, g, b):
        v = mm.call(PSYMS['np_tone'], r, g, count=100000, a2=b)
        return v >> 24, (v & 255, v >> 8 & 255, v >> 16 & 255)
    rng = random.Random(7)
    grid = [(r, g, b) for r in range(0, 256, 51) for g in range(0, 256, 51) for b in range(0, 256, 51)]
    grid += [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(150)] + [(1, 0, 0), (0, 0, 1), (255, 254, 255)]
    bad = [(c, c_tone(*c)[1], mn.tone(*c)) for c in grid if c_tone(*c) != (255, mn.tone(*c))]
    expect(not bad, f'np_tone equals tools/mod_nowplaying.py tone on {len(grid)} colours ({bad[:2]})')
    expect(c_tone(0, 0, 0) == (255, mn.NP_NEUTRAL) and mn.tone(0, 0, 0) == mn.NP_NEUTRAL, 'black is the neutral tone')
    expect(all(max(mn.tone(*c)) <= mn.NP_V_MAX and max(mn.tone(*c)) >= mn.NP_V_MIN for c in grid if any(c)), 'the brightest channel of a tone stays between NP_V_MIN and NP_V_MAX (darkened)')
    expect(all(len(set(mn.tone(v, v, v))) == 1 for v in range(0, 256, 5)), 'a grey stays grey')
    red = mn.tone(200, 60, 60); expect(red[0] > red[1] == red[2] and red[1] > 0, f'a red cover stays red ({red})')
    expect(mn.tone(250, 250, 250)[0] > mn.tone(120, 120, 120)[0] > mn.tone(10, 10, 10)[0], 'brighter covers give brighter tones')
    expect((mn.NP_V_MIN, mn.NP_V_MAX, mn.NP_SAT_NUM, mn.NP_SAT_DEN) == tuple(O[k] for k in ('NP_V_MIN', 'NP_V_MAX', 'NP_SAT_NUM', 'NP_SAT_DEN'))
           and O['NP_NEUTRAL'] == 0xff000000 | mn.NP_NEUTRAL[0] | mn.NP_NEUTRAL[1] << 8 | mn.NP_NEUTRAL[2] << 16
           and mn.BG == '#%02X%02X%02X' % mn.NP_NEUTRAL, 'the Python tone and the payload share their constants, and the asset\'s window colour is the neutral tone')
    expect((mn.TINT_ALPHA[0], mn.TINT_ALPHA[1], mn.H, mn.ART, mn.ART_Y, mn.ART_R) == tuple(O[k] for k in ('NP_ALPHA_TOP', 'NP_ALPHA_BOTTOM', 'NP_WIN_H', 'NP_ART', 'NP_ART_Y', 'NP_ART_R')),
           'the gradient and the art constants are the payload\'s')
    # the contrast floor: white title and #AAAAAA lines over the toned window under the gradient, worst case over the colour grid
    rows = {'title': ((255, 255, 255), mn.TITLE_Y + mn.TITLE_H // 2), 'artist': ((170, 170, 170), mn.ARTIST_Y + mn.ARTIST_H // 2),
            'times': ((170, 170, 170), mn.TIMES_Y + mn.TIMES_H // 2), 'index': ((170, 170, 170), mn.TIMES_Y)}
    worst = {}
    for c in grid + [(255, 255, 255)]:
        t = mn.tone(*c)
        for n, (fg, y) in rows.items():
            keep = 255 - mn.tint_alpha(y)
            worst[n] = min(worst.get(n, 99), contrast(fg, tuple(v * keep // 255 for v in t)))
    expect(all(v >= 4.5 for v in worst.values()), f'text keeps 4.5:1 on the darkest and the brightest tone under the gradient ({ {k: round(v, 2) for k, v in worst.items()} })')

    # the progress bar: the unplayed track (white at TRACK's alpha) must show against the window on every tone, the fill against the track
    over = lambda fg, a, bg: tuple(round(b + (f - b) * a / 255) for f, b in zip(fg, bg))
    a_track, a_fill = int(mn.TRACK[7:9], 16), int(mn.FILL[7:9], 16)
    ty = mn.SLIDER[1] + mn.SLIDER[3] // 2
    tw = {'track vs window': 99, 'fill vs track': 99, 'mode glyph vs window': 99}
    for c in grid + [(255, 255, 255)]:
        bg = tuple(v * (255 - mn.tint_alpha(ty)) // 255 for v in mn.tone(*c)); tr = over((255,) * 3, a_track, bg)
        tw['track vs window'] = min(tw['track vs window'], contrast(tr, bg)); tw['fill vs track'] = min(tw['fill vs track'], contrast(over((255,) * 3, a_fill, tr), tr))
        gy = mn.ROW_Y + mn.ROW_H // 2; gbg = tuple(v * (255 - mn.tint_alpha(gy)) // 255 for v in mn.tone(*c))
        tw['mode glyph vs window'] = min(tw['mode glyph vs window'], contrast(mod_icons.NP_MID, gbg))
    expect(tw['track vs window'] >= 2.3 and tw['fill vs track'] >= 4.5 and tw['mode glyph vs window'] >= 4.5 and mod_icons.NP_MID > (0xAA,) * 3 and mod_icons.NP_OFF < (0xAA,) * 3 and a_track > 0x33,
           f'the track shows on every tone (the fill stands out of it), the mode glyphs keep 4.5:1, repeat-off stays dimmer ({ {k: round(v, 2) for k, v in tw.items()} })')

    # the lyrics and info pages: the scrim (np_scrim.png, 50 % black, soft top and bottom) sits between the tinted window and the text.
    # Lyric lines (current white-ish, the others the lighter grey) and the info labels, over every tone, rows 44..288 of the text area
    lyric_style = {i.style: i for i in awtk_style.parse(open(os.path.join(raw, 'styles', 'playing_page.bin'), 'rb').read()).items
                   if i.widget == 'list_item' and i.state == 'normal'}
    col = lambda s: tuple(int(s[k:k + 2], 16) for k in (1, 3, 5))
    cur, dim = col(lyric_style['listitem_sellyric_style'].color('text_color')), col(lyric_style['listitem_lyric_style'].color('text_color'))
    # the info page's text sits on np_scrim (50 %); the stock lyric list (what shows without the payload: kill switch, a failure) on the lighter lyrics scrim,
    # where its grey lines keep 2.5:1 and its current line 4.5:1 (our own lines are checked in test/pod/lyrics.py)
    secondary = {'stock lyric inactive': (dim, 2.5, 'l'), 'stock lyric current': (cur, 4.4, 'l'), 'info label': (col(mn.GREY), 3.0, 'i'), 'info quality line': (col(mn.FG), 4.5, 'i'), 'info location': (col(mn.GREY), 3.0, 'i')}
    sworst = {k: 99 for k in secondary}
    for c in grid + [(255, 255, 255)]:
        t = mn.tone(*c)
        for y in range(mn.LYR_Y, mn.LYR_Y + mn.LYR_H, 4):
            keep, sk = 255 - mn.tint_alpha(y), {'l': 255 - mn.lscrim_alpha(y - mn.LSCRIM[1]), 'i': 255 - mn.scrim_alpha(y - mn.SCRIM[1])}
            for k, (fg, _, which) in secondary.items():
                bg = tuple(v * keep // 255 * sk[which] // 255 for v in t)
                sworst[k] = min(sworst[k], contrast(fg, bg))
    expect(all(sworst[k] >= need for k, (_, need, _w) in secondary.items()),
           f'with the scrim the info text keeps its contrast on every tone (secondary >= 3:1, quality line >= 4.5:1) and the stock lyric list its own (inactive >= 2.5:1, current >= 4.4:1) ({ {k: round(v, 2) for k, v in sworst.items()} })')
    bare = min(contrast(dim, tuple(v * (255 - mn.tint_alpha(y)) // 255 for v in mn.tone(255, 255, 255))) for y in range(mn.LYR_Y, mn.LYR_Y + mn.LYR_H, 4))
    expect(bare < 2.5, f'(the scrim is needed: the inactive lyric over the brightest tone alone is {bare:.2f}:1)')
    expect(lum(dim) > lum(col(mn.DOWN)) and dim == col(mn.LYR_DIM), 'the inactive lyric grey is lighter than the old #8C8C8C')
    from awtk_text import Ttf as _T14, StbText as _S14
    _t14 = _T14(os.path.join(raw, 'fonts', 'default.ttf'))
    tw14 = max(_S14(_t14, mn.TIMES_PX).layout(s)[1] for s in ('-00:00:00', '00:00:00', '-88:88:88'))
    expect(mn.TIMES_PX == 14 and tw14 <= mn.TIMES_W and mn.TIMES_W - tw14 <= 14, f'the 14 px times fit their box: the widest "-hh:mm:ss" is {tw14} px in {mn.TIMES_W}')

    # ------------------------------------------------------------------ the status bar follows the page (EXPERIMENTAL)
    def bar_model(t):      # t: the window colour (r, g, b); the page's first row under the gradient, darkened for white glyphs
        keep = 255 - mn.tint_alpha(0)
        r, g, b = (v * keep // 255 for v in t)
        while 2126 * r * r + 7152 * g * g + 722 * b * b > O['NP_BAR_LUM_MAX']: r, g, b = r * 15 >> 4, g * 15 >> 4, b * 15 >> 4
        return r, g, b
    def c_bar(t):
        v = mm.call(PSYMS['np_bar_color'], t[0] | t[1] << 8 | t[2] << 16, count=100000)
        return v >> 24, (v & 255, v >> 8 & 255, v >> 16 & 255)
    tones = sorted({mn.tone(*c) for c in grid} | {mn.NP_NEUTRAL, mn.tone(255, 255, 255)})
    expect(all(c_bar(t) == (255, bar_model(t)) for t in tones), f'np_bar_color equals the model on {len(tones)} tones: the first row under the gradient, darkened to the luminance cap')
    bad = [t for t in tones if contrast((255, 255, 255), c_bar(t)[1]) < 4.5]
    wc = min(contrast((255, 255, 255), c_bar(t)[1]) for t in tones)
    expect(not bad, f'the bar\'s white glyphs and clock keep 4.5:1 on every tone (worst {wc:.2f}:1)')
    anyrgb = [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(300)] + [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    expect(all(contrast((255, 255, 255), c_bar(c)[1]) >= 4.5 for c in anyrgb), 'the cap holds for any colour, not only the tones (300 random, the primaries and white)')
    dark = [t for t in tones if bar_model(t) == tuple(v * (255 - mn.tint_alpha(0)) // 255 for v in t)]
    expect(len(dark) > 20 and mn.NP_NEUTRAL in dark and all(c_bar(t)[1] == tuple(v * (255 - mn.tint_alpha(0)) // 255 for v in t) for t in dark),
           f'a dark tone gives exactly the page\'s first row ({len(dark)} of {len(tones)} tones are not darkened)')
    seam = max(max(v * (255 - mn.tint_alpha(0)) // 255 - w for v, w in zip(t, c_bar(t)[1])) for t in tones)
    print(f'  (status bar: worst white contrast {wc:.2f}:1; largest channel step page row 0 -> bar {seam}; {len(dark)} of {len(tones)} tones undarkened)')
    expect(O['NP_BAR_STOCK'] == 0xff000000 and (O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']) == (0x12c, 0x12d), 'stock black, the two window events')

    def tinted(pix=bytes([200, 40, 40, 255]), size=(2, 2), **kw):
        m = NowMachine().with_bar(); m.page(); m.jpeg('/tmp/coverpic.jpg', pix=pix * (size[0] * size[1]), size=size); m.src(2)
        for k, v in kw.items(): setattr(m, k, v)
        m.init(); return m
    BLACK = O['NP_BAR_STOCK']
    word_of = lambda rgb: 0xff000000 | rgb[0] | rgb[1] << 8 | rgb[2] << 16
    m = tinted(bytes([40, 30, 20, 255]))
    t = mn.tone(40, 30, 20)
    expect(m.bar_styles[-1] == (m.bar, 'normal:bg_color', word_of(bar_model(t))) and ('widget_invalidate_force', m.bar) in m.calls,
           f'a dark cover: the bar gets the colour of the page\'s first row ({[hex(s[2]) for s in m.bar_styles]}) and is repainted')
    expect(bar_model(t) == tuple(v * 217 // 255 for v in t), 'which is the tone under the gradient\'s first row, alpha 38')
    expect(all(s[0] == m.bar and s[1] == 'normal:bg_color' for s in m.bar_styles) and m.styles == [(WIN, 'normal:bg_color', word_of(t))],
           'the window\'s own colour is still set once, to the plain tone')
    n = len(m.bar_styles); m.tick(); m.tick()
    expect(len(m.bar_styles) == n and not m.bar_calls(), 'ticks while nothing changes leave the bar alone (no repaint loop)')
    expect(sum(c[0] == 'widget_invalidate_force' and c[1] == m.bar for c in m.calls) == 0, 'and repaint nothing')
    m = tinted(bytes([250, 250, 250, 255]))
    expect(contrast((255, 255, 255), tuple(m.bar_color() >> s & 255 for s in (0, 8, 16))) >= 4.5 and m.bar_color() != word_of(tuple(v * 217 // 255 for v in mn.tone(250, 250, 250))),
           'a bright cover: the bar is darker than the page\'s first row, so the white glyphs stay readable')
    # the bar is found by type: the navbar is the first child and is never touched; no status bar, nothing to do
    m = tinted()
    expect(all(c[1] == m.bar for c in m.calls if c[0] == 'widget_set_style' and c[1] != WIN) and m.children[m.wm][0] not in [c[1] for c in m.calls if c[0] == 'widget_set_style'],
           'only the child of type system_bar is styled')
    m = NowMachine(); m.page(); m.src(0); m.init(); m.tick()
    expect(m.bar_styles == [] and m.styles, 'a window manager without a status bar: the page works, no bar call')
    m = NowMachine().with_bar(); m.page(); m.src(0); m.wm = 0; m.init(); m.tick()
    expect(m.bar_styles == [] and m.styles, 'no window manager: the same')

    # background / foreground
    m = tinted(); col = m.bar_color(); m.bar_styles.clear()
    m.fire(O['EVT_WINDOW_TO_BG'])
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)] and ('widget_invalidate_force', m.bar) in m.calls, 'EVT_WINDOW_TO_BACKGROUND: the bar is black again and repainted')
    m.fire(O['EVT_WINDOW_TO_BG'])
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)], 'a second one does not set it again')
    m.tick(); m.tick()
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)], 'ticks while a dialog (the pull-down) covers the page, the page still the top normal window: the bar stays black')
    m.blobs['/tmp/coverpic.jpg'] = b'next track' * 30; m.images['file://' + '/tmp/coverpic.jpg'] = (2, 2, bytes([20, 200, 20, 255]) * 4); m.tick()
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)] and len(m.styles) == 2 and [c for c in m.calls if c[0] == 'get_playtimeandlength'],
           'under a dialog the page is still seen: a new cover recolours the page (not the bar) and the time goes on')
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.bar_color() == word_of(bar_model(mn.tone(20, 200, 20))) and len(m.bar_styles) == 2 and len(m.styles) == 2,
           'EVT_WINDOW_TO_FOREGROUND: the bar takes the current cover\'s colour with one style call')
    expect(('np_mode_button', WIN) in m.calls, 'back in front the mode button\'s picture is set again from the play mode (stock sets it only in its own click handler; the Queue page changes the mode)')
    n = len(m.bar_styles); m.fire(O['EVT_WINDOW_TO_FG'])
    expect(len(m.bar_styles) == n + 1 and m.bar_color() == word_of(bar_model(mn.tone(20, 200, 20))), 'a repeated foreground event only sets the same colour again')
    n = len(m.bar_styles); m.tick(); m.tick()
    expect(len(m.bar_styles) == n, 'then ticks leave it (no loop)')
    # another page on top: the tick does nothing but the bar check; foreground catches up in the event
    m.fire(O['EVT_WINDOW_TO_BG']); m.top_main = WIN + 0x100; k = len(m.styles); m.calls = []
    m.blobs['/tmp/coverpic.jpg'] = b'third track' * 31; m.images['file://' + '/tmp/coverpic.jpg'] = (2, 2, bytes([20, 20, 200, 255]) * 4); m.tick()
    expect(len(m.styles) == k and not [c for c in m.calls if c[0] in ('fopen', 'get_playtimeandlength', 'widget_get_text')],
           'a page on top: a tick reads no cover, asks no player time and reads no info label')
    m.top_main = WIN; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.styles[-1][2] == word_of(mn.tone(20, 20, 200)) and m.bar_color() == word_of(bar_model(mn.tone(20, 20, 200))),
           'back on top: the foreground event applies the cover that changed meanwhile, page and bar')
    # a handler for another page's window does nothing
    m.fire(O['EVT_WINDOW_TO_BG']); k = len(m.bar_styles)
    fn, _ = m.bound[(WIN, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=WIN + 0x100, a1=0, count=100000)
    expect(len(m.bar_styles) == k and m.bar_color() == BLACK and not any(c[0] == 'np_mode_button' for c in m.calls), 'an event whose context is not the current window changes nothing')
    # the timer catches what the events missed
    m = tinted(); m.bar_styles.clear(); m.top_main = WIN + 0x100; m.tick()
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)], 'another normal window on top without an event: the next tick makes the bar black')
    m.tick(); expect(len(m.bar_styles) == 1, 'once')
    m.top_main = WIN; m.tick()
    expect(len(m.bar_styles) == 2 and m.bar_color() != BLACK, 'the page the top window again, still in front: the tick tints again')
    m.fire(O['EVT_WINDOW_TO_BG']); m.top_main = WIN; m.tick()
    expect(m.bar_color() == BLACK and len(m.bar_styles) == 3, 'but not while a background event stands (a dialog)')

    # every exit restores black
    m = tinted(); m.bar_styles.clear()
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)] and ('timer_remove', 0x777) in m.calls and m.calls.index(('widget_set_style', m.bar, 'normal:bg_color', BLACK)) < m.calls.index(('timer_remove', 0x777)),
           'page destroy: black first, then the timer goes')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); m.tick(); m.fire(O['EVT_WINDOW_TO_FG']); m.fire(O['EVT_WINDOW_TO_BG'])
    expect(m.bar_styles == [(m.bar, 'normal:bg_color', BLACK)], 'after the destroy: a second destroy, a stray tick and stray window events never touch the bar')
    m = tinted(); m.fire(O['EVT_WINDOW_TO_BG']); m.bar_styles.clear(); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(m.bar_styles == [], 'a destroy of a page already backgrounded has nothing to restore')
    m = tinted(); m.bar_styles.clear(); m.call(PSYMS['np_on_destroy'], a0=WIN + 0x100, a1=0)
    expect(m.bar_styles == [], 'an earlier page\'s destroy leaves the bar to the current page')
    m = tinted(); m.bar_styles.clear(); m.init(win=WIN + 0x100)
    expect([s[2] for s in m.bar_styles][:1] == [BLACK] and m.bar_color() != BLACK and sum(c[0] == 'timer_remove' for c in m.calls) == 1,
           'a page built over a live one: black for the old one, then the new one tints')
    m.calls = []; m.top_main = WIN + 0x100; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(not m.bar_calls(), 'and the old page\'s late destroy does not undo it')
    # hand-over with the album page (pod_bar_tint / pod_bar_black: only the owner restores)
    ALBUM = WIN + 0x200
    m = tinted(); m.bar_styles.clear()
    expect(m.call(PSYMS['pod_bar_tint'], a0=ALBUM, a1=0x00112233) == 1 and len(m.bar_styles) == 1, 'the album page takes the bar over from Now Playing')
    m.fire(O['EVT_WINDOW_TO_BG']); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(len(m.bar_styles) == 1 and m.bar_color() != BLACK, 'Now Playing\'s late background event and destroy (Back) leave the album page\'s colour alone')
    m = tinted(); m.bar_styles.clear(); m.call(PSYMS['pod_bar_tint'], a0=ALBUM, a1=0x00112233); m.bar_styles.clear(); m.tick(); m.tick()
    expect(not m.bar_styles, 'ticks while the album page owns the bar do not take it back (the page is not the top window)')
    m = tinted(); m.fire(O['EVT_WINDOW_TO_BG']); m.bar_styles.clear()
    m.call(PSYMS['pod_bar_tint'], a0=ALBUM, a1=0x00112233); m.fire(O['EVT_WINDOW_TO_FG'])
    expect(len(m.bar_styles) == 2 and m.bar_color() == word_of(bar_model(mn.tone(200, 40, 40))), 'and Now Playing takes it back when it comes to the front again')

    # the tone cache (patch/common.c): a changed cover of a known album is not decoded again
    def tone_run(album='Kind of Blue', playing=True):
        m = NowMachine(); m.page(); m.src(2)
        if playing: m.play([m.record(album=album, artist='Miles Davis')], 0)
        m.jpeg('/tmp/coverpic.jpg', data=b'cover one' * 30, pix=bytes([200, 40, 40, 255]) * 4, size=(2, 2)); m.init()
        return m
    def next_cover(m, rgb, data):
        m.blobs['/tmp/coverpic.jpg'] = data; m.images['file:///tmp/coverpic.jpg'] = (2, 2, bytes(rgb + (255,)) * 4)
        return [c for c in m.tick() if c[0] == 'widget_load_image']
    m = tone_run(); first = [s[2] for s in m.styles]
    expect(first == [word_of(mn.tone(200, 40, 40))], 'a new album: decoded as before, the tone set')
    expect(next_cover(m, (20, 200, 20), b'cover two' * 31) == [] and [s[2] for s in m.styles] == first * 2,
           'another cover file (a new hash) of the same album: the cached tone is used, nothing is decoded')
    m.tick(); expect(len(m.styles) == 2, 'and then ticks leave it')
    m.play([m.record(album='Other', artist='Miles Davis')], 0)
    expect(len(next_cover(m, (20, 200, 20), b'cover three' * 30)) == 1 and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)),
           'another album: decoded, and its own tone set')
    expect(next_cover(m, (30, 30, 200), b'cover four' * 30) == [] and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)), 'which is cached in turn')
    m = tone_run(playing=False)
    expect(len(next_cover(m, (20, 200, 20), b'cover two' * 31)) == 1 and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)), 'no track in the queue: no key, every new cover is decoded')
    m = tone_run(album='')
    expect(len(next_cover(m, (20, 200, 20), b'cover two' * 31)) == 1 and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)), 'an untagged track has no album key: no cache')
    expect(not [c for c in m.calls if (c[0] == 'fopen' and any(x in c[2] for x in 'wa+')) or c[0] in ('fwrite', 'write', 'open')], 'no card writes')
    # the album's 168 px cache file is decoded before the embedded picture (the tone cache is RAM only, empty after a boot)
    def cache_run(cached=True, size=(2, 2)):
        m = NowMachine(); m.page(); m.src(2)
        m.play([m.record(album='Kind of Blue', artist='Miles Davis')], 0)
        if cached: m.jpeg(art_file(album_key('Miles Davis', 'Kind of Blue')), data=b'thumb' * 20, pix=bytes([20, 200, 20, 255]) * 4, size=size)
        m.jpeg('/tmp/coverpic.jpg', data=b'cover one' * 30, pix=bytes([200, 40, 40, 255]) * 4, size=(2, 2)); m.init()
        return m
    m = cache_run()
    loads = [c[1] for c in m.calls if c[0] == 'widget_load_image']
    expect(loads == ['file://' + art_file(album_key('Miles Davis', 'Kind of Blue'))] and [s[2] for s in m.styles] == [word_of(mn.tone(20, 200, 20))],
           f'a cache file of the album: it is decoded and not /tmp/coverpic.jpg, the tone from it ({loads})')
    expect(next_cover(m, (30, 30, 200), b'cover two' * 31) == [] and len(m.styles) == 2, 'and the tone is cached for the album as before')
    m = cache_run(cached=False)
    loads = [c[1] for c in m.calls if c[0] == 'widget_load_image']
    expect(loads == ['file:///tmp/coverpic.jpg'] and [s[2] for s in m.styles] == [word_of(mn.tone(200, 40, 40))], f'no cache file: the playing cover is decoded as before ({loads})')
    m = NowMachine(); m.page(); m.src(2); m.play([m.record(album='Kind of Blue', artist='Miles Davis')], 0)
    m.blobs[art_file(album_key('Miles Davis', 'Kind of Blue'))] = b''; m.present.add(art_file(album_key('Miles Davis', 'Kind of Blue')))
    m.jpeg('/tmp/coverpic.jpg', data=b'cover one' * 30, pix=bytes([200, 40, 40, 255]) * 4, size=(2, 2)); m.init()
    expect([c[1] for c in m.calls if c[0] == 'widget_load_image'] == ['file:///tmp/coverpic.jpg'], 'the empty "no art" marker is not a cache file: the playing cover is decoded')
    # an unchanged cover is not hashed again (review 2): the cheap look is the source type, the length and the track
    def big_run():
        m = NowMachine().with_bar(); m.page(); m.src(2)
        m.play([m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/a/1.flac')], 0)
        m.jpeg('/tmp/coverpic.jpg', data=bytes(range(256)) * 256, pix=bytes([200, 40, 40, 255]) * 4, size=(2, 2)); m.init()   # 64 KiB
        return m
    def reads(m): return sum(1 for c in m.calls if c[0] == 'fopen' and c[1] == '/tmp/coverpic.jpg')
    def bytes_read(m): return sum(len(m.blobs['/tmp/coverpic.jpg']) for c in m.calls if c[0] == 'fopen')
    m = big_run().count(); n = len(m.styles)
    m.tick(count=50000000)
    steady = m.icount
    expect(len(m.styles) == n and steady < 20000 and not [c for c in m.calls if c[0] == 'fread'],
           f'an unchanged cover: a tick reads none of it (was 396,187 instructions for 64 KiB, now {steady}; no fread)')
    m.fire(O['EVT_WINDOW_TO_BG']); m.top_main = WIN + 0x100; m.calls = []
    m.tick(count=50000000)
    expect(m.icount < 3000 and not [c for c in m.calls if c[0] in ('fopen', 'fread', 'get_playtimeandlength', 'widget_get_text')],
           f'a covered page: the tick does no cover, time or info work ({m.icount} instructions)')
    # same length, another track (demo wrote a new cover): hashed; the same file again: not
    m = big_run(); n = len(m.styles)
    m.blobs['/tmp/coverpic.jpg'] = bytes(range(255, -1, -1)) * 256
    m.tick(count=50000000)
    expect(not [c for c in m.calls if c[0] == 'fread'], 'same track, same length, same source: the cheap look says unchanged (no hash)')
    m.play([m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/a/2.flac')], 0)
    m.tick(count=50000000)
    expect(not [c for c in m.calls if c[0] in ('fread', 'widget_load_image')] and len(m.styles) == n + 1,
           'another track of an album whose tone is cached: the colour is set again from the cache, the file is neither hashed nor decoded')
    m.tick(count=50000000)
    expect(not [c for c in m.calls if c[0] == 'fread'], 'and then not again')
    m.blobs['/tmp/coverpic.jpg'] = bytes(range(256)) * 255
    n = len(m.styles); m.tick(count=50000000)
    expect(len(m.styles) == n + 1 and not [c for c in m.calls if c[0] == 'fread'], 'another length: looked at again (the cached tone, no hash)')
    m.src(3); m.blobs['/tmp/externpic.jpg'] = m.blobs['/tmp/coverpic.jpg']; m.present.add('/tmp/externpic.jpg')
    m.tick(count=50000000)
    expect(len(m.styles) == n + 2 and not [c for c in m.calls if c[0] == 'fread'], 'another source type: looked at again')
    m.play([m.record(album='Other', artist='Miles Davis', path='/mnt/mmc/a/3.flac')], 0)
    m.tick(count=50000000)
    expect([c for c in m.calls if c[0] == 'fread'], 'another album with no cached tone: hashed')
    # a cover that could not be read is looked at in full every tick until it can
    m = NowMachine().with_bar(); m.page(); m.src(2); m.init()
    m.tick(); m.tick()
    expect(len([c for c in m.calls if c[0] == 'fopen']) <= 2, 'no cover file: the tick just tries to open it')
    # covered pages catch up at once on foreground: a cover that changed while covered is applied, hash included
    m = big_run(); m.fire(O['EVT_WINDOW_TO_BG']); m.top_main = WIN + 0x100
    m.blobs['/tmp/coverpic.jpg'] = bytes(range(256)) * 200; m.images['file:///tmp/coverpic.jpg'] = (2, 2, bytes([20, 200, 20, 255]) * 4)
    m.play([m.record(album='Other', artist='X', path='/mnt/mmc/a/9.flac')], 0)
    m.tick(count=50000000)
    expect(not [c for c in m.calls if c[0] in ('fopen', 'fread')], 'covered: the new cover is not even looked at')
    m.top_main = WIN; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.styles[-1][2] == word_of(mn.tone(20, 200, 20)), 'foreground: the new cover is applied in the event itself')

    # the kill switch, a refused timer, refused events, a failing style call, the cover widget missing
    m = NowMachine().with_bar(); m.page(); m.timer_fail = True; m.init()
    expect(not m.bar_styles and not m.styles and (WIN, O['EVT_WINDOW_TO_BG']) not in m.bound, 'a refused timer: the bar is never touched and no window event is registered')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(not m.bar_styles, 'and nothing later does')
    for ev in (O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']):
        m = NowMachine().with_bar(); m.page(); m.src(0); m.on_fail = {ev}; m.init(); m.tick()
        expect(not m.bar_styles and m.styles, f'event {ev:#x} refused: the page tints, the bar is never touched (it could not be restored)')
        m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); expect(not m.bar_styles, 'and the destroy has nothing to restore')
    m = NowMachine().with_bar(); m.page(); m.src(0); m.on_fail = {EVT_DESTROY}; m.init()
    expect(not m.bar_styles and not m.timers, 'no destroy handler: the page stays stock, the bar too')
    m = NowMachine().with_bar(); m.page(); m.src(0); m.bar_style_ret = 0x10; m.init(); m.tick()
    expect(not m.bar_styles and m.styles and not any(c[0] == 'widget_invalidate_force' and c[1] == m.bar for c in m.calls),
           'a failing bar style call: no repaint of the bar, the page still works')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); expect(not m.bar_styles, 'and nothing to restore at the end')
    m = NowMachine().with_bar(); m.page(art=False); m.src(0); m.init()
    expect(m.bar_color() is not None, 'without the cover widget the bar still follows')
    m = NowMachine().with_bar(); m.page(labels=False); m.src(0); m.init(); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect([s[2] for s in m.bar_styles][-1] == BLACK, 'without the labels: the bar follows and is restored')

    # ------------------------------------------------------------------ the cover: decode, average, change, corrupt, missing
    P2, P3 = '/tmp/coverpic.jpg', '/tmp/externpic.jpg'
    half = bytes([255, 0, 0, 255]) * 8 + bytes([0, 0, 255, 255]) * 8
    m = NowMachine(); m.page(); m.jpeg(P2, pix=half, size=(4, 4)); m.src(2)
    m.init()
    avg = (128, 0, 128)       # (255*8 / 16 = 127.5, 0, 127.5): the exact area average of the 4x4 cover, rounded to nearest
    expect(m.styles == [(WIN, 'normal:bg_color', 0xff000000 | mn.tone(*avg)[0] | mn.tone(*avg)[1] << 8 | mn.tone(*avg)[2] << 16)],
           f'a red/blue cover tints with the tone of its average colour ({[hex(s[2]) for s in m.styles]})')
    expect(m.loads == ['file://' + P2], 'the cover is decoded once, from the file of source type 2')
    expect(('widget_invalidate_force', WIN) in m.calls, 'the window is repainted')
    m.calls = []; m.tick()
    expect(m.loads == ['file://' + P2] and not m.styles[1:], 'an unchanged cover is not decoded again')
    m.blobs[P2] = b'another' * 50; m.images['file://' + P2] = (2, 2, bytes([0, 200, 0, 255]) * 4); m.tick()
    expect(len(m.styles) == 2 and m.styles[1][2] & 0xffffff == (lambda t: t[0] | t[1] << 8 | t[2] << 16)(mn.tone(0, 200, 0)), 'a changed file tints again')
    m.src(3); m.jpeg(P3, data=b'folder' * 20, pix=bytes([90, 90, 90, 255]) * 4, size=(2, 2)); m.tick()
    expect(len(m.styles) == 3 and 'file://' + P3 in m.loads, 'source type 3 reads /tmp/externpic.jpg')
    m.src(5); m.blobs[P3] = b'cached' * 20; m.tick()
    expect(len(m.styles) == 4, 'source type 5 does too')
    m.src(1); m.blobs[P3] = b'being written'; n = len(m.styles); m.tick()
    expect(len(m.styles) == n and not any(c[0] == 'fopen' for c in m.calls), 'type 1 (demo is replacing the file): the colour stays, nothing is read')
    m.src(4); m.tick()
    expect(m.styles[-1] == (WIN, 'normal:bg_color', O['NP_NEUTRAL']), 'a source with no JPEG file (4: random cover) is the neutral tone')
    n = len(m.styles); m.tick(); expect(len(m.styles) == n, 'and only once')
    # a file that vanished or cannot be decoded keeps the colour
    m = NowMachine(); m.page(); m.src(2); m.init()
    m.styles.clear()                          # a type 2 source, no file: not readable, no decode
    n = len(m.styles); m.tick()
    expect(len(m.styles) == n and not m.loads, 'a type 2 source whose file is missing: the colour stays, no decode')
    m.jpeg(P2, data=b'corrupt' * 30); m.load_image = 1
    m.tick(); expect(not m.styles and len(m.loads) == 1, 'a file the loader refuses keeps the colour')
    m.tick(); expect(len(m.loads) == 1, 'and is not retried until it changes')
    m.blobs[P2] = b'fixed' * 30; m.load_image = 0; m.tick()
    expect(len(m.styles) == 1, 'a changed file is tried again')
    m = NowMachine(); m.page(); m.src(2); m.jpeg(P2, pix=bytes(4 * 4 * 4), size=(4, 4)); m.init()
    expect(m.styles == [(WIN, 'normal:bg_color', O['NP_NEUTRAL'])], 'an all-black cover is the neutral tone')
    # the whole file is hashed, bounded
    m = NowMachine(); m.page(); m.src(2); big = bytes(range(256)) * 4096; m.jpeg(P2, data=big)
    k = m.call(PSYMS['np_file_key'], a0=m.cstr(P2), count=20000000)
    expect(k != 0, 'a 1 MB file hashes (at most NP_HASH_MAX bytes read)')
    m.blobs['/tmp/x'] = b''; m.present.add('/tmp/x')
    expect(m.call(PSYMS['np_file_key'], a0=m.cstr('/tmp/x'), count=100000) == 0 and m.call(PSYMS['np_file_key'], a0=m.cstr('/tmp/none'), count=100000) == 0,
           'an empty or missing file has no key')

    # ------------------------------------------------------------------ the corners: the same numbers as the model, the colour the window has there
    cov = mn.corner_alpha()
    expect(len(cov) == 144 and cov[0] == 255 and cov[-1] == 0 and cov[11 * 12 + 0] <= 2 and sum(1 for v in cov if v) >= 30, 'the corner table: a full pixel at the corner, nothing at the arc\'s inside')
    m = NowMachine(); m.page(); m.src(2); m.jpeg(P2, pix=half, size=(4, 4)); m.init()
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); canvas = 0x7000a000; m.setword(ev + O['EVENT_PAINT_CANVAS'], canvas)
    m.fills = []; m.call(PSYMS['np_on_art_paint'], a0=0, a1=ev, count=2000000)
    t = mn.tone(*avg); color = t[0] | t[1] << 8 | t[2] << 16
    want = {}
    A = mn.ART
    for k in range(4):
        for y in range(mn.ART_R):
            ly = A - 1 - y if k & 2 else y
            keep = 255 - mn.tint_alpha(mn.ART_Y + ly)
            shade = (t[0] * keep // 255) | (t[1] * keep // 255) << 8 | (t[2] * keep // 255) << 16
            for x in range(mn.ART_R):
                a = cov[y * mn.ART_R + x]
                if a: want[(A - 1 - x if k & 1 else x, ly)] = shade | a << 24
    got = {(f[1], f[2]): f[0] for f in m.fills if (f[3], f[4]) == (1, 1)}
    expect(got == want and len(m.fills) == len(want), f'the four corners are painted pixel by pixel in the window\'s colour under the gradient ({len(m.fills)} pixels)')
    m.fills = []; m.call(PSYMS['np_on_art_paint'], a0=0, a1=0, count=100000)
    expect(not m.fills, 'no canvas: nothing')
    # the colour the corners use is the one the style call set
    expect(m.styles[-1][2] & 0xffffff == color, 'the corners use the colour of the last style call')

    # ------------------------------------------------------------------ the built assets
    ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
    f = ui.find
    rect = lambda n: (f(n).x, f(n).y, f(n).w, f(n).h)
    expect(rect('img_playcover') == (28, 28, 264, 264) and mn.ART == mod_lockscreen.COVER_SIZE == 264, 'the cover is 264 px at 28, 28: the size demo writes, so it is drawn 1:1')
    lines = [rect(n) for n in ('label_info', 'label_album', 'label_genre', 'label_year', 'label_size', 'label_location')]
    expect(all(a[1] + a[3] <= b[1] for a, b in zip(lines, lines[1:])) and lines[-1][1] + lines[-1][3] <= mn.LYR_Y + mn.LYR_H
           and all(r[0] >= 0 and r[0] + r[2] <= 320 for r in lines) and lines[0][:3] == (8, 52, 304)
           and f('label_info').get('style:normal:text_color') == mn.FG and f('label_album').get('style:normal:text_color') == mn.GREY,
           f'the info page: the quality line (304 px wide) and the four lines stack without overlap, the location under them ({lines})')
    imm = [word(built, a) & 0xffff for a in mod_lockscreen.COVER_IMM]
    expect(imm == [264] * 4 and all(word(stock, a) in (0x240700fe, 0x240600fe) for a in mod_lockscreen.COVER_IMM), 'demo writes the cover file at 264 px (the four pinned words)')
    expect(rect('btn_return') == (100, 0, 120, 44) and f('btn_return').get('style') == 'img_btn_style' and f('btn_return').get('style:normal:bg_image') == 'np_grabber',
           'Back is the grabber: 120x44, the pill in its image')
    expect(rect('slide_indicator') == (145, 296, 30, 4) and f('slide_indicator').get('size') == '4', 'micro dots: 4 px, centred under the art')
    expect(rect('scrlabel_title') == (28, 305, 182, 24) and rect('scrlabel_artist') == (28, 329, 182, 22), 'title and artist in the 28 px text column left of the buttons')
    expect(mn.TITLE_PX == 20 and mn.META_PX == 18 and mn.TITLE_H >= mn.TITLE_PX + 4 and mn.ARTIST_H >= mn.META_PX + 4
           and mn.TITLE_Y + mn.TITLE_H == mn.ARTIST_Y and (mn.TITLE_Y + mn.ARTIST_Y + mn.ARTIST_H) / 2 == mn.BTN_Y + mn.BTN // 2 + 0.0
           and mn.FAV_X - mn.M >= mn.TEXT_W, 'title 20 px, artist 18 px: the 46 px block is centred on the discs (y 328) and the column ends before the star')
    from awtk_text import Ttf as _T, StbText as _S
    _t = _T(os.path.join(raw, 'fonts', 'default.ttf'))
    _w20 = lambda s: _S(_t, 20).layout(s)[1]
    expect(_w20('Hello, World') < mn.TEXT_W and _w20('A' * 40) > mn.TEXT_W and _S(_t, 20).layout('Hg')[1] > 0, 'the 20 px title measures with the pinned font: a short title fits the 182 px column, a long one is cut (ellipsis)')
    expect(rect('btn_fav') == (210, 306, 44, 44) and rect('btn_more') == (254, 306, 44, 44), 'star and More: 44x44 targets side by side, the More disc (6 px inset) ends on the 28 px margin the text starts on')
    expect(rect('slider_play') == (28, 348, 264, 30) and f('slider_play').get('bar_size') == '6' and f('slider_play').get('style:normal:icon') == '', 'progress: the stock 30 px target, a 6 px bar, no thumb')
    expect(rect('label_playtime')[:2] == (28, mn.TIMES_Y) and rect('np_remaining') == rect('label_playlen') and rect('np_elapsed') == rect('label_playtime') and rect('label_playlen')[0] + rect('label_playlen')[2] == 292,
           'times under the bar on the margins; the remaining time sits on the total')
    expect(all(f(n).get(f'style:{s}:font_size') == '14' for n in ('label_playtime', 'label_playlen', 'np_remaining', 'np_elapsed') for s in ('normal', 'disable', 'focused')), 'times are 14 px in every state')
    expect(f('view_buttons').y == 392 and f('view_buttons').y + f('view_buttons').h == 450, 'the transport row is 392..450')
    expect(all(f(n).get('visible') == 'false' for n in ('np_remaining', 'np_elapsed')) and all(f(n).get('sensitive') == 'false' for n in ('np_remaining', 'np_elapsed', 'label_playlen', 'label_playtime', 'img_np_tint')),
           'np_remaining and np_elapsed start hidden; the labels and the gradient are insensitive')
    for n in ('label_index', 'img_hr'):
        expect(rect(n)[2:] == (0, 0) and f(n).get('visible') == 'false' and f(n).get('sensitive') == 'false', f'{n} is kept, hidden and insensitive at 0x0')
    expect(f('label_album') in f('view_info').children and 'label_album' not in [c.name for c in f('view').children], 'the album line is on the info page, not under the art')
    expect(f('label_info') in f('view_info').children, 'the quality line is on the info page, not between the times')
    expect(f('img_np_tint') is ui.find('view_local').children[0] and rect('img_np_tint') == (0, 0, 320, 450), 'the gradient is the first child of view_local, window sized')
    hidden = [w.name or w.type for w in ui.walk() if w.get('visible') == 'false' and w.get('sensitive') != 'false' and w.name != 'view_dlna' and w.name != 'img_mqa']
    expect(not hidden, f'every hidden widget is also insensitive ({hidden})')
    expect(len(mn.check_touch(ui)) == len(mn.PROBES), 'check_touch: every control\'s centre reaches it, the art and the title rows reach the slide_view')
    expect(all(min(rect(n)[2:]) >= 44 for n in mn.PROBES if n != 'slider_play') and rect('slider_play')[3] == 30, 'touch targets are 44 px or the stock 30 px seek bar')
    lyr = f('view_lrc')
    expect(lyr.y >= 44 and lyr.y + lyr.h <= mn.DOTS[1] and f('view_info').children and all(c.y + c.h <= mn.DOTS[1] for c in f('view_info').children if c.name and not c.name.startswith('img_np_scrim')), 'lyrics and info text end above the dots (the scrim runs under them)')
    expect(f('view').y + f('slide_view').h <= f('view_buttons').y and f('slide_view').h == mn.SLIDE_H, 'the slide pages end above the transport row')
    # vertical rhythm
    art_end = 28 + 264
    sy = mn.SLIDER[1]
    expect(mn.DOTS[1] - art_end == 4 and mn.TITLE_Y - (mn.DOTS[1] + mn.DOTS[3]) == 5 and mn.ARTIST_Y + mn.ARTIST_H - sy <= 3 and sy + 30 <= mn.TIMES_Y
           and mn.TIMES_Y + mn.TIMES_H == mn.SVV_H and mn.SVV_H - mn.ROW_Y <= 5, 'art, dots, title, artist, bar, times and the transport row follow each other (the insensitive artist box overlaps the bar\'s 30 px target by 3 px at most)')
    # the lower half's rhythm on ink: the gaps artist -> bar -> digits -> transport glyphs are equal, the glyphs keep ~15 px from the bottom
    bar_top, bar_bot = sy + 15 - mn.BAR // 2, sy + 15 + mn.BAR // 2
    dig_top, dig_bot = mn.TIMES_Y + 3, mn.TIMES_Y + 3 + 9              # 14 px digits: ink 9 rows, 3 under the label's top (device screenshot)
    row_c = mn.ROW_Y + mn.ROW_H // 2; g_top, g_bot = row_c - 14, row_c + 14   # pause bars 28 tall, centred on the 44 px canvas
    art_bot = 344                                                       # the artist's ink bottom on the device (baseline row of "back number")
    gaps = (bar_top - art_bot, dig_top - bar_bot, g_top - dig_bot, mn.H - g_bot)
    expect(gaps == (16, 16, 16, 15), f'ink gaps artist -> bar -> times -> transport glyphs -> window bottom {gaps}')
    expect(f('view_buttons').y + rect('btn_play')[1] + rect('btn_play')[3] // 2 == row_c == 421 and all(rect(n)[3] >= 44 for n in ('btn_playmode', 'btn_prev', 'btn_play', 'btn_next', 'btn_queue')),
           'the transport slots are centred on the glyphs and stay 44 px or more')
    # the cover's shadow: an insensitive child of page 1, right over the cover and under the title; a hole where the art is
    sh = f('img_np_shadow'); page1 = f('view')
    kids = [c.name for c in page1.children]
    expect(sh in page1.children and kids.index('img_np_shadow') == kids.index('img_playcover') + 1 and kids.index('img_np_shadow') < kids.index('scrlabel_title')
           and sh.get('sensitive') == 'false' and sh.get('image') == 'np_shadow', f'the shadow follows the cover on page 1 (slides with it), before the title, insensitive ({kids})')
    expect((sh.x, sh.y, sh.w, sh.h) == (mn.ART_X - mn.SHADOW_PAD, mn.ART_Y - mn.SHADOW_PAD, mn.SHADOW_SIZE, mn.SHADOW_SIZE) and sh.x >= 0 and sh.x + sh.w <= 320
           and sh.y >= 0 and sh.y + sh.h <= mn.SLIDE_H, f'the shadow image lies inside the 320 x {mn.SLIDE_H} page ({(sh.x, sh.y, sh.w, sh.h)}): nothing clipped at the edges')
    # images
    xx = os.path.join(raw, 'images', 'xx')
    from PIL import Image
    sd = Image.open(os.path.join(xx, 'np_shadow.png')).convert('RGBA'); S, P, A_, R_ = mn.SHADOW_SIZE, mn.SHADOW_PAD, mn.ART, mn.ART_R
    sa = lambda x, y: sd.getpixel((x, y))[3]
    expect(sd.size == (S, S) and {sd.getpixel((x, y))[:3] for x in (0, 100, S - 1) for y in (0, 60, S - 1)} == {(0, 0, 0)}, f'np_shadow.png: {S} px square, black')
    top = max(sa(x, y) for y in range(S) for x in range(S))
    expect(0.35 * 255 <= top <= 0.45 * 255 and mn.SHADOW_ALPHA >= top, f'its strongest visible pixel is {top / 255:.0%} black (35..45 %; the blur at full strength {mn.SHADOW_ALPHA / 255:.0%} lies under the art)')
    expect(all(sa(P + x, P + y) == 0 for x in range(R_, A_ - R_, 7) for y in range(R_, A_ - R_, 7)) and sa(P + 130, P + 130) == 0 and sa(P + 3, P + 130) == 0 and sa(P + A_ - 1, P + 130) == 0 and sa(P + 130, P) == 0
           and sa(P + 130, P + A_ - 1) == 0, 'the art itself is a hole in the shadow (nothing over the cover)')
    expect(max(sa(x, y) for x in range(S) for y in (0, 1, S - 1, S - 2)) <= 1 and max(sa(x, y) for y in range(S) for x in (0, 1, S - 1, S - 2)) <= 1, 'the blur has faded out at the image edge (no clipping)')
    expect(all(sa(x, y) == sa(S - 1 - x, y) for x in range(S) for y in range(0, S, 9)), 'the shadow is symmetric left to right')
    col = [sa(S // 2, P + A_ + d) for d in range(0, 20)]
    expect(all(a >= b for a, b in zip(col, col[1:])) and col[0] >= 60 and col[-1] <= 2 and sa(S // 2, P - 1) < col[0] and sa(S // 2, P - 1) > 5,
           f'it falls off smoothly under the art ({col[0] / 255:.0%} at the edge, {col[10] / 255:.0%} 10 px out) and shows above it less than below')
    # the corners: the shadow darkens the notches the payload fills with the window colour, with the payload's own coverage
    cov = mn.corner_alpha()
    expect(all((sa(P + x, P + y) == 0) == (cov[y * R_ + x] == 0) for y in range(R_) for x in range(R_)), 'the hole is the art\'s rounded rectangle: the shadow shows exactly where the corner painter has coverage')
    expect(sa(P, P) > 0 and sa(P, P) == sa(P + A_ - 1, P) and sa(P, P + A_ - 1) > sa(P, P), 'the corner notches are shadowed (more at the bottom, where the shadow is shifted to)')
    expect(os.path.getsize(os.path.join(xx, 'np_shadow.png')) < 12000, f'np_shadow.png is small ({os.path.getsize(os.path.join(xx, "np_shadow.png"))} bytes)')
    t = Image.open(os.path.join(xx, 'np_tint.png')).convert('RGBA')
    expect(t.size == (320, 450) and {t.getpixel((0, y))[:3] for y in (0, 225, 449)} == {(0, 0, 0)} and (t.getpixel((7, 0))[3], t.getpixel((7, 449))[3]) == mn.TINT_ALPHA
           and all(t.getpixel((x, y))[3] == mn.tint_alpha(y) for y in range(0, 450, 17) for x in (0, 319)), 'np_tint.png: black, alpha 38 at the top to 235 at the bottom, rows as tint_alpha')
    expect(os.path.getsize(os.path.join(xx, 'np_tint.png')) < 6000, f'np_tint.png is small ({os.path.getsize(os.path.join(xx, "np_tint.png"))} bytes)')
    sc = Image.open(os.path.join(xx, 'np_scrim.png')).convert('RGBA')
    SW, SH = mn.SCRIM[2:]
    expect(sc.size == (SW, SH) and {sc.getpixel((x, y))[:3] for x in (0, 160, 319) for y in (0, 100, SH - 1)} == {(0, 0, 0)}
           and all(sc.getpixel((x, y))[3] == mn.scrim_alpha(y) for y in range(SH) for x in (0, 319)),
           'np_scrim.png: black, alpha rows as scrim_alpha')
    al = [sc.getpixel((5, y))[3] for y in range(SH)]
    expect(al[0] == 0 and al[-1] == 0 and max(al) == 128 and 0.45 <= max(al) / 255 <= 0.55 and al == al[::-1]
           and all(a == 128 for a in al[mn.SCRIM_EDGE:SH - mn.SCRIM_EDGE]) and all(x <= y for x, y in zip(al[:mn.SCRIM_EDGE], al[1:mn.SCRIM_EDGE + 1]))
           and al[mn.SCRIM_EDGE // 2] in range(60, 68), 'the scrim is 50 % black in the middle, ramps softly to 0 at the top and the bottom edge, symmetric')
    expect(sc.height == SH and mn.SCRIM[1] <= mn.LYR_Y - mn.SCRIM_EDGE and mn.LYR_Y + mn.LYR_H <= mn.SCRIM[1] + SH - mn.SCRIM_EDGE
           and all(r[1] >= mn.LYR_Y - 4 for r in lines[:1]) and os.path.getsize(os.path.join(xx, 'np_scrim.png')) < 4000,
           f'the whole text area (y {mn.LYR_Y} .. {mn.LYR_Y + mn.LYR_H}) lies in the full-strength middle of the scrim (y {mn.SCRIM[1]} .. {mn.SCRIM[1] + SH}); the file is small')
    for pg, nm, box, img in (('view_lyrics', 'img_np_scrim_lyrics', mn.LSCRIM, 'np_scrim_lyrics'), ('view_info', 'img_np_scrim_info', mn.SCRIM, 'np_scrim')):
        s = f(nm)
        expect(f(pg).children[0] is s and rect(nm) == box and s.get('sensitive') == 'false' and s.get('image') == img,
               f'{nm}: the first child of {pg} (under the text), insensitive, at {box}, image {img} (the lyrics page has its own, lighter scrim: test/pod/lyrics.py)')
    expect(all(w.name not in ('img_np_scrim_lyrics', 'img_np_scrim_info') or [p for p in ui.walk() if w in p.children][0].name in ('view_lyrics', 'view_info') for w in ui.walk() if w.name),
           'the scrim is on the lyrics and info pages only: the art page keeps the full tint')
    expect(not os.path.exists(os.path.join(xx, 'np_artmask.png')) and 'img_np_artmask' not in [w.name for w in ui.walk()], 'there is no static corner mask: the payload paints the corners (square without it)')
    sizes = {n: asset_image(n).size for n in ('np_grabber', 'np_play', 'np_pause', 'np_next', 'np_prev', 'np_fav', 'np_unfav', 'np_more', 'np_random', 'np_playqueue')}
    expect(sizes['np_grabber'] == (120, 44) and sizes['np_fav'] == sizes['np_unfav'] == sizes['np_more'] == (44, 44) and sizes['np_play'] == sizes['np_pause'] == (44, 44) and sizes['np_next'] == sizes['np_prev'] == (44, 44),
           f'glyph canvases: grabber 120x44, disc glyphs 44x44, transport 44x44 ({sizes})')
    g = asset_image('np_grabber'); bb = g.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    expect(bb == (42, 11, 78, 16) and 108 <= g.getpixel((60, 13))[3] <= 110, f'the grabber pill is 36x5 at x 42, y 11 of the button, white at 43 % ({bb})')
    for n in ('np_fav', 'np_unfav', 'np_more'):
        im = asset_image(n); dbb = im.getchannel('A').point(lambda v: 255 if v > 2 else 0).getbbox()
        expect(dbb == (6, 6, 38, 38) and im.getpixel((10, 22)) == (255, 255, 255, mod_icons.NP_DISC_ALPHA) == (255, 255, 255, 26)
               and asset_image(n + '_down' if n != 'np_fav' else 'np_unfav_down').getpixel((10, 22)) == (255, 255, 255, mod_icons.NP_DISC_ALPHA_DOWN) == (255, 255, 255, 51),
               f'{n}: a flat 32 px disc, white at #1A (pressed #33), in the 44 px target ({dbb})')
        far = [(x, y) for y in range(44) for x in range(44) if (x - 21.5) ** 2 + (y - 21.5) ** 2 > 16.6 ** 2]
        expect(all(im.getpixel(p)[3] == 0 for p in far), f'{n}: transparent outside the disc')
    # the glyph in the disc (centre 22.0, 22.0): coverage = the glyph's share of each pixel over the 26/255 disc; sub-pixel bbox edges, centroid
    def optical(n):
        im = asset_image(n); W_, H_ = im.size
        c = [[max(0.0, (im.getpixel((x, y))[3] - 26) / 229) if im.getpixel((x, y))[3] > 26 else 0.0 for x in range(W_)] for y in range(H_)]
        cols = [max(c[y][x] for y in range(H_)) for x in range(W_)]; rows = [max(r) for r in c]
        def edges(v):
            idx = [i for i, a in enumerate(v) if a > 0.02]; return idx[0] + 1 - v[idx[0]], idx[-1] + v[idx[-1]]
        (x0, x1), (y0, y1) = edges(cols), edges(rows)
        tot = sum(map(sum, c)); mx = sum((x + 0.5) * c[y][x] for y in range(H_) for x in range(W_)) / tot; my = sum((y + 0.5) * c[y][x] for y in range(H_) for x in range(W_)) / tot
        return ((x0 + x1) / 2, (y0 + y1) / 2), (mx, my)
    (fb, fc), (ub, _), (mb, mc) = optical('np_fav'), optical('np_unfav'), optical('np_more')
    d = lambda p: max(abs(p[0] - 22), abs(p[1] - 22))
    expect(d(fb) <= 0.75 and d(fc) <= 0.75 and d(((fb[0] + fc[0]) / 2, (fb[1] + fc[1]) / 2)) <= 0.25 and d(ub) <= 0.75 and abs(ub[0] - fb[0]) < 0.3 and abs(ub[1] - fb[1]) < 0.3
           and d(mb) <= 0.25 and d(mc) <= 0.25,
           f'star and More are centred in their 32 px disc (optical centre = the mean of the box centre and the centroid, within 0.25 px; each within 0.75): the filled star\'s box ({fb[0] - 22:+.2f}, {fb[1] - 22:+.2f}) and centroid ({fc[0] - 22:+.2f}, {fc[1] - 22:+.2f}), the outline\'s box ({ub[0] - 22:+.2f}, {ub[1] - 22:+.2f}) as the filled one, More ({mb[0] - 22:+.2f}, {mb[1] - 22:+.2f})')
    dwin = lambda c: tuple(v * (255 - mn.tint_alpha(mn.BTN_Y + 22)) // 255 for v in mn.tone(*c))      # the window under the star / More row
    dworst = min(contrast(mod_icons.NP_FG, tuple(round(b + (255 - b) * a / 255) for b in dwin(c)))
                 for c in grid + [(255, 255, 255), (0, 0, 0)] for a in (mod_icons.NP_DISC_ALPHA, mod_icons.NP_DISC_ALPHA_DOWN))
    expect(dworst >= 4.5, f'the off-white star / More glyph keeps 4.5:1 on the flat disc (rest or pressed fill) over the darkest and the brightest tone ({dworst:.2f}:1)')
    cov = lambda n: asset_image(n).getchannel('A').point(lambda v: 255 if v > 0 else 0).getbbox()      # any coverage: the ink with its anti-aliased rim
    half = lambda n: asset_image(n).getchannel('A').point(lambda v: 255 if v > 127 else 0).getbbox()
    near = lambda b, w, h: abs(b[2] - b[0] - w) <= 1 and abs(b[3] - b[1] - h) <= 1
    pb, qb, nb, vb = cov('np_play'), cov('np_pause'), cov('np_next'), cov('np_prev')
    expect(near(pb, 29, 31) and near(qb, 27, 28) and near(nb, 35, 24) and near(vb, 35, 24) and near(half('np_play'), 29, 31),
           f'transport ink: play 29x31, pause two 8.4x28 bars (27 wide), skip 35x24 (1.46 x its height), prev = next mirrored ({pb}, {qb}, {nb}, {vb})')
    expect(sizes['np_next'] == sizes['np_prev'] == (44, 44) and min(sizes['np_next']) >= 40, 'the skip canvases are 44x44 (>= 40 wide): the 60 px slots and the lock screen\'s 48 px targets hold them')
    cx = lambda b: (b[0] + b[2]) / 2
    expect(abs(cx(pb) - 22 - 1.5) <= 1 and abs(cx(qb) - 22) <= 1 and abs(cx(nb) - 22) <= 1 and abs(cx(vb) - 22) <= 1 and all(abs((b[1] + b[3]) / 2 - 22) <= 1 for b in (pb, qb, nb, vb)),
           'every glyph is centred in its canvas (play 1.5 px right: optical centring)')
    for n in ('np_play', 'np_pause', 'np_next', 'np_prev'):
        a = asset_image(n).getchannel('A'); part = sum(1 for v in a.getdata() if 0 < v < 255); b = cov(n)
        expect(part >= 60 and a.getpixel((b[0], b[1])) < 128 and a.getpixel((b[2] - 1, b[3] - 1)) < 128, f'{n}: anti-aliased ({part} partial pixels) with rounded corners (the bbox corners are not inked)')
        expect(max(asset_image(n).getdata(), key=lambda c: c[3])[:3] == mod_icons.NP_FG and max(asset_image(n + '_down').getdata(), key=lambda c: c[3])[:3] == mod_icons.NP_DIM, f'{n}: off-white, pressed #8C8C8C')
    pw = asset_image('np_pause').getchannel('A'); row = [pw.getpixel((x, 22)) for x in range(44)]
    runs = []; run = 0
    for v in row + [0]:
        if v > 127: run += 1
        elif run: runs.append(run); run = 0
    expect(len(runs) == 2 and all(8 <= r <= 9 for r in runs), f'pause: two bars 8-9 px wide at the middle row ({runs})')
    # the lock screen reuses play / pause / next in 48 px wide targets 56 px tall (mod_lockscreen): the canvases and the ink fit with room
    expect(mod_lockscreen.BTN_W >= sizes['np_next'][0] and mod_lockscreen.BTN_W >= sizes['np_play'][0]
           and (mod_lockscreen.BTN_W - (pb[2] - pb[0])) // 2 + (mod_lockscreen.BTN_W - (nb[2] - nb[0])) // 2 >= 12,
           'lock screen: play and next canvases fit the 48 px targets, the inks stay >= 12 px apart')
    mid = asset_image('np_random'); mb = mid.getchannel('A').point(lambda v: 255 if v > 128 else 0).getbbox()
    qg = asset_image('np_playqueue'); qgb = qg.getchannel('A').point(lambda v: 255 if v > 128 else 0).getbbox()
    expect(max(mb[2] - mb[0], mb[3] - mb[1]) <= 18 and max(qgb[2] - qgb[0], qgb[3] - qgb[1]) <= 18
           and max(c for c in mid.getdata() if c[3] > 200)[:3] == mod_icons.NP_MID, 'the mode and queue glyphs are small (18 px) and a notch dimmer than the white transport shapes (#C8C8C8)')
    expect(max(c for c in asset_image('np_order').getdata() if c[3] > 200)[:3] == mod_icons.NP_OFF, 'repeat-off is dimmer still')
    # the style swaps the app does still land on glyphs: every page-theme icon exists
    th = awtk_style.parse(open(os.path.join(raw, 'styles', 'playing_page.bin'), 'rb').read())
    icons = {s.get('icon') for s in th.items if s.widget == 'button' and (s.get('icon') or '').startswith('np_')}
    expect(icons <= set(mod_icons.np_names()) and {'np_fav', 'np_unfav', 'np_play', 'np_pause', 'np_random', 'np_cycle', 'np_cycle1', 'np_order'} <= icons,
           f'the page theme\'s np_ button icons exist as images ({sorted(icons)})')
    expect(f('btn_fav').get('style') == 'btn_imgunfav_style' and f('btn_fav').get('style:pressed:icon') == 'np_unfav_down', 'btn_fav keeps its stock style (the app swaps it) with the pressed glyph')
    by = {}
    for s in th.items:
        if s.widget == 'button' and s.style in ('btn_imgfav_style', 'btn_imgunfav_style', 'btn_imgsave_style', 'btn_imgunsave_style'): by.setdefault(s.style, {})[s.state] = s.get('icon')
    want = {'btn_imgfav_style': 'np_fav', 'btn_imgunfav_style': 'np_unfav', 'btn_imgsave_style': 'np_save', 'btn_imgunsave_style': 'np_unsave'}
    expect(all(len(by.get(n, {})) == 5 and all(i == want[n] for st, i in by[n].items()) for n in want),
           f'the favourite button\'s four styles (star filled / outline, bookmark filled / outline) have their glyph in every state ({by})')
    sv, uv = asset_image('np_save'), asset_image('np_unsave')
    bb = lambda im: im.getchannel('A').point(lambda v: 255 if v > 200 else 0).getbbox()
    expect(sv.size == uv.size == asset_image('np_fav').size == (44, 44) and bb(sv) is not None and bb(uv) is not None and sv.getpixel((22, 22))[:3] == mod_icons.NP_FG
           and uv.getpixel((22, 22))[3] < 80 and asset_image('np_unsave_down').size == (44, 44),
           'the bookmark images are 44 px: the disc and a filled (np_save) or outline (np_unsave) glyph in the star\'s off-white')
    # an episode's favourite button is a bookmark: the tick (and a click, which runs after stock's handler) maps the style stock sets, music maps it back
    ep, music = '/mnt/mmc/Podcasts/Show/e1.mp3', '/mnt/mmc/Music/a.flac'
    def fav_machine(path, style):
        mm = NowMachine(); mm.page(); mm.src(0); fav = mm.widget('btn_fav')
        mm.setword(fav + O['WIDGET_STYLE'], mm.cstr(style)); mm.props[(fav, 'style')] = style
        mm.play([mm.record(path=path)], 0); mm.init()
        return mm, fav
    for path, style, want_style in ((ep, 'btn_imgunfav_style', 'btn_imgunsave_style'), (ep, 'btn_imgfav_style', 'btn_imgsave_style'), (music, 'btn_imgunsave_style', 'btn_imgunfav_style'),
                                    (music, 'btn_imgsave_style', 'btn_imgfav_style'), (music, 'btn_imgfav_style', None), (ep, 'btn_imgsave_style', None), (ep, 'btn_imgplay_style', None)):
        mm, fav = fav_machine(path, style)
        uses = [c for c in mm.calls if c[0] == 'widget_use_style' and c[1] == fav]
        pressed = mm.props.get((fav, 'style:pressed:icon'))
        expect(uses == ([('widget_use_style', fav, want_style)] if want_style else []) and pressed == (('np_unsave_down' if 'save' in want_style else 'np_unfav_down') if want_style else None),
               f'{path.split("/")[3]} track, button on {style}: {uses}, pressed glyph {pressed}')
    mm, fav = fav_machine(ep, 'btn_imgunfav_style')
    clicks = [c for c in mm.calls if c[0] == 'widget_on' and c[1] == fav]
    expect(len(clicks) == 1 and clicks[0][2] == O['EVT_CLICK'] and clicks[0][3] == PSYMS['np_on_fav'], 'a click on the button is handled after stock\'s (registered once the stock init has run)')
    mm.setword(fav + O['WIDGET_STYLE'], mm.cstr('btn_imgfav_style')); mm.calls = []
    mm.call(PSYMS['np_on_fav'], a0=0, a1=0)
    expect([c for c in mm.calls if c[0] == 'widget_use_style'] == [('widget_use_style', fav, 'btn_imgsave_style')] and mm.props[(fav, 'style:pressed:icon')] == 'np_unsave_down', 'the click handler maps the style stock has just set, with no wait for a tick')
    mm.play([], -1); mm.setword(fav + O['WIDGET_STYLE'], mm.cstr('btn_imgsave_style')); mm.calls = []; mm.tick()
    expect([c for c in mm.calls if c[0] == 'widget_use_style'] == [('widget_use_style', fav, 'btn_imgfav_style')], 'nothing playing counts as music: the bookmark goes back to the star')
    expect(f('btn_playmode').get('style') == 'btn_imgrandom_style', 'btn_playmode keeps its stock style (the app swaps it)')

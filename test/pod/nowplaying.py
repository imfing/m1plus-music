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
        self.sbcov = {}           # server track REC_ID -> its cached cover file (None: not cached yet); sba_now_cover (patch/sbapi.c, tested in sbapi.py) answers from it
        self.handlers[PSYMS['sba_now_cover']] = 'sba_now_cover'
        self.bkcov = {}           # an audiobook part's path -> the book's cover file (bk_art_cover, patch/bkmodel.c, tested in queuepage.py and bkmodel.py); missing: the book has none
        self.handlers[PSYMS['bk_art_cover']] = 'bk_art_cover'
        self.sbtrack, self.sbsize, self.sburl = {}, {}, ''   # sba_rec_track / sba_rec_size / sba_url (patch/sbapi.c): queue record -> track id, -> server bytes, the saved address
        for n in ('sba_rec_track', 'sba_rec_size', 'sba_url'): self.handlers[PSYMS[n]] = n
        self.sbfav, self.sbgen = {}, 0   # server track REC_ID -> starred (lib_nd.row on a queue record, patch/sbsrc.c, tested in sbsrc.py); sba_gen
        for n in ('nd_row', 'ls_favorite', 'sba_gen'): self.handlers[PSYMS[n]] = n
        self.sv_refuse = 0        # how many of the next turns of the slide view (its "value" set) are refused: the page stays
        self.speed_ok, self.speed_saved = 1, 0   # pc_speed_set's answer, the mode it last saved (pc_speed_apply puts it in playspeed_mode)
        for n in ('pc_speed_set', 'pc_speed_apply', 'pod_toast'): self.handlers[PSYMS[n]] = n
        self.info = None          # mclGetInfo's record: dict(rate, bits, fmt) (the info page's badge: patch/tape.c tape_badge); None: the player has no stream
        self.handlers[pod.FUNCTIONS['mclGetInfo'][2]] = 'mclGetInfo'
        self.px = {}              # label handle -> its font size (widget_measure_text)
        self.status = 0           # mclGetPlayStatus

    def with_bar(self, top=WIN):
        """The window manager with a navbar and a status bar among its children; `top` is its top normal window."""
        nav = self.alloc(0x80); self.bar = self.alloc(0x80)
        self.children[self.wm] = [nav, self.bar]; self.types[nav] = 'system_bar_bottom'; self.types[self.bar] = 'system_bar'
        self.top_main = top
        return self

    def bar_color(self): return self.bar_styles[-1][2] if self.bar_styles else None
    def bar_calls(self): return [c for c in self.calls if c[0] == 'widget_set_style' and c[1] == self.bar]
    IW = {'np_i_scroll': 0, 'np_i_art': 0, 'np_i_title': 20, 'np_i_title2': 20, 'np_i_artist': 16, 'np_i_album': 16, 'np_i_badge_hires': 0, 'np_i_badge_dsd': 0,
          **{f'np_i_k{r}': 16 for r in range(8)}, **{f'np_i_v{r}': 16 for r in range(9)}, **{f'np_i_h{r}': 0 for r in range(8)}}
    measure_px = None         # (text, px) -> width: the real font, set by run()
    def info_page(self, stock, own=True):
        """The info page's stock labels (name -> the text stock wrote) and, with own, our widgets; returns {name: handle}."""
        out = {}
        for n, t in stock.items():
            out[n] = self.widget(n); self.texts[out[n]] = t.encode('utf-8').decode('latin-1')
        if own:
            for n, px in self.IW.items(): self.px[self.widget(n)] = px
            self.widget('slide_view')
        return out

    def label(self, name): return self.texts[self.widgets[name]].encode('latin-1').decode('utf-8')   # the text stock wrote

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'mclGetInfo':
            i = self.info
            if i: self.u.mem_write(a0, struct.pack('<iiii32si', 900000, i['rate'], 0, 0, i['fmt'].encode(), i['bits']))
            self.calls.append(('mclGetInfo',)); ret = 1 if i else 0
        elif name == 'widget_measure_text':
            t = ''.join(map(chr, self.words_until_zero(a1))); w = float(self.measure_px(t, self.px.get(a0, 16))) if t else 0.0
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        elif name == 'stock_playing_resume':
            self.calls.append(('stock_playing_init', a0, a1)); ret = self.stock_ret
        elif name == 'np_mode_button':   # stock 0x539888, the mode button's picture
            self.calls.append(('np_mode_button', a0)); ret = 0
        elif name == 'widget_set_style':
            v = self.word(a2 + 8); self.calls.append(('widget_set_style', a0, self.read_cstr(a1), v))
            ret = self.bar_style_ret if a0 == self.bar else self.style_ret
            if ret == 0: (self.bar_styles if a0 == self.bar else self.styles).append((a0, self.read_cstr(a1), v))
        elif name == 'widget_on' and a1 in self.on_fail:
            self.calls.append(('widget_on', a0, a1, a2, a3)); ret = 0
        elif name == 'sba_now_cover':
            rid = self.word(a0 + O['REC_ID']) if a0 else 0; rid = rid - (1 << 32) if rid >= 1 << 31 else rid
            self.calls.append(('sba_now_cover', rid)); p = self.sbcov.get(rid); ret = self.cstr(p) if p else 0
        elif name == 'bk_art_cover':
            p = self.read_cstr(a0); self.calls.append(('bk_art_cover', p)); f = self.bkcov.get(p)
            if f: self.u.mem_write(a1, ('file://' + f).encode() + b'\0')
            ret = a1 if f else 0
        elif name == 'sba_rec_track':
            rid = a0 - (1 << 32) if a0 >= 1 << 31 else a0; ret = self.cstr(self.sbtrack.get(rid, ''))
        elif name == 'sba_rec_size':
            rid = a0 - (1 << 32) if a0 >= 1 << 31 else a0; ret = self.sbsize.get(rid, 0)
        elif name == 'sba_url':
            ret = self.cstr(self.sburl)
        elif name == 'sba_gen':
            ret = self.sbgen
        elif name == 'nd_row':   # lib_nd.row(src, rec, out): ls_row_t {dl, pct, dsd, fav, offline}
            rid = self.word(a1 + O['REC_ID']); rid = rid - (1 << 32) if rid >= 1 << 31 else rid
            self.calls.append(('nd_row', rid)); self.u.mem_write(a2, struct.pack('<5i', 0, 0, 0, self.sbfav.get(rid, 0), 0)); ret = 0
        elif name == 'ls_favorite':   # (src, rec, was): the star toggled on the server, 0 done
            rid = self.word(a1 + O['REC_ID']); rid = rid - (1 << 32) if rid >= 1 << 31 else rid
            self.calls.append(('ls_favorite', a0 == PSYMS['lib_nd'], rid, a2)); self.sbfav[rid] = 0 if self.sbfav.get(rid) else 1; ret = 0
        elif name == 'mclGetPlayStatus':   # 0 by default (the episode timer, pc_note, saves nothing); a test sets status (3 paused: the cover shrinks)
            ret = self.status
        elif name == 'value_set_uint32':
            self.setword(a0, 7); self.setword(a0 + 8, a1); ret = a0
        elif name == 'pc_speed_set':   # (key, mode): the show's or the book's speed saved, 0 when the card refuses (patch/pcmodel.c, tested in podcasts.py)
            self.calls.append(('pc_speed_set', a0 != 0, a1)); ret = self.speed_ok
            if ret: self.speed_saved = a1
        elif name == 'pc_speed_apply':   # the saved speed into playspeed_mode (and the player)
            self.calls.append(('pc_speed_apply', a0 != 0)); self.setword(pod.DATA['PLAYSPEED_MODE'][0], self.speed_saved); ret = 0
        elif name == 'pod_toast':
            self.calls.append(('pod_toast', self.read_cstr(a0))); ret = 0
        elif name in ('save_stop_player', 'save_start_player'):
            self.calls.append((name, a0) if name == 'save_start_player' else (name,)); ret = 0
        elif name == 'widget_use_style' and a0 == self.widgets.get('btn_playmode'):   # the widget keeps the name, as AWTK's does (np_mode_sync compares it); recorded by the harness below
            self.setword(a0 + O['WIDGET_STYLE'], self.cstr(self.read_cstr(a1)))
        elif name == 'widget_set_prop_int' and self.sv_refuse and a0 == self.widgets.get('slide_view') and self.read_cstr(a1) == 'value':   # a slide view that is animating keeps its page
            self.sv_refuse -= 1; self.calls.append(('widget_set_prop_int', a0, 'value', a2)); ret = 0
        elif name == 'seek_time':   # the stock seek: the player is at the target when it returns
            self.calls.append(('seek_time', a0 - (1 << 32) if a0 >= 1 << 31 else a0)); self.pt = (a0, self.pt[1], self.pt[2]); ret = 1
        elif name == 'get_playtimeandlength':
            pos, ln, r = self.pt
            self.setword(a0, pos); self.setword(a1, ln); self.calls.append(('get_playtimeandlength',)); ret = r
        elif name == 'widget_set_text_utf8':   # the labels keep their text (the info page is read back)
            t = self.read_cstr(a1); self.calls.append(('widget_set_text_utf8', a0, t)); ret = 1 if a0 in self.set_fail else 0
            if not ret: self.texts[a0] = t
        elif name == 'widget_get_text':   # the label's wide text (32 bit code points; NULL for a label without one, or while get_ret is set: a failed read); the payload encodes it (m1_text_utf8)
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
    built = built_demo_bytes()
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

    # the track position: label_index shows "5/10" between the times, behind the Track Position setting (off by default), written by our tick from mclGetPlayPos and the queue size
    NPPOS = '/mnt/data/m1plus/nowplaying-position'
    def tpos(on, n=10, pos=4):
        m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.widget('label_index')
        if on is not None: m.fs[NPPOS] = on
        m.play([m.record(title=f't{i}', rid=i + 1) for i in range(n)], pos); m.init(); return m
    ixset = lambda m: [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets['label_index']]
    m = tpos(None); m.tick()
    expect(not ixset(m) and m.visible('label_index') is None, 'Track Position off (no file): label_index is never written or shown')
    m = tpos(b'0\n'); m.tick(); expect(not ixset(m) and m.visible('label_index') is None, 'a file with 0: off')
    m = tpos(b'1\n')
    expect(ixset(m) == ['5/10'] and m.visible('label_index') == 1, f'on: "5/10" is shown at once ({ixset(m)})')
    m.calls = []; m.tick(); m.tick(); expect(not ixset(m), 'an unchanged position is not written again')
    m.play([m.record(title=f't{i}', rid=i + 1) for i in range(11)], 4); m.calls = []; m.tick()
    expect(ixset(m) == ['5/11'], f'a track added to the queue shows on the next tick ({ixset(m)})')
    m.play([m.record(title=f't{i}', rid=i + 1) for i in range(11)], 5); m.calls = []; m.tick()
    expect(ixset(m) == ['6/11'], f'the next track: 6/11 ({ixset(m)})')
    m.play([m.record(rid=1)], 0); m.calls = []; m.tick()
    expect(m.visible('label_index') == 0 and not ixset(m), 'a queue of one hides it')
    m.play([m.record(rid=1), m.record(rid=2)], 1); m.calls = []; m.tick()
    expect(ixset(m) == ['2/2'] and m.visible('label_index') == 1, 'two tracks show 2/2 again')
    m.play([m.record(rid=1), m.record(rid=2)], 2); m.calls = []; m.tick()
    expect(m.visible('label_index') == 0, 'a position past the queue hides it')
    m.play([m.record(rid=1), m.record(rid=2)], -1); m.calls = []; m.tick()
    expect(m.visible('label_index') == 0, 'no position hides it')
    m.play([], 0); m.calls = []; m.tick(); expect(m.visible('label_index') == 0, 'an empty queue hides it')
    big = [m.record(rid=1)] * 65537
    m.play(big[:65535], 4); m.calls = []; m.tick()
    expect(ixset(m) == ['5/65535'] and m.visible('label_index') == 1, f'a large queue: 5/65535 ({ixset(m)})')
    m.play(big, 4); m.calls = []; m.tick()
    expect(ixset(m) == ['5/65537'] and m.visible('label_index') == 1, f'no size limit: 5/65537 stays shown ({ixset(m)})')
    m = tpos(b'1\n'); m.fs[NPPOS] = b'0\n'; m.calls = []; m.tick()
    expect(m.visible('label_index') == 1, 'the setting is read when the page starts or comes back, not on every tick')
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0, count=6000000)
    expect(m.visible('label_index') == 0, 'back in front with the setting off: hidden')
    m.fs[NPPOS] = b'1\n'; m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0, count=6000000)
    expect(m.visible('label_index') == 1 and ixset(m)[-1] == '5/10', 'and on again when it is switched on')
    N = pod_pages.NPSET_PAGE
    expect(('Track Position', pod_pages.ACT_NPPOS) in [(r.label, r.action) for r in N.rows] and pod_pages.ACT_NPPOS in pod_pages.SWITCH_ACTIONS and pod_pages.row_kind(next(r for r in N.rows if r.action == pod_pages.ACT_NPPOS)) == 'switch' and 'nowplaying-position' in pod_pages.SETTING_FILES and NPPOS.rsplit('/', 1)[1] == 'nowplaying-position',
           'Settings > Now Playing has the Track Position switch, saved in nowplaying-position and listed on Settings Files')
    m = NowMachine(); m.page()
    expect(m.call(PSYMS['np_pos_setting']) == 0 and m.call(PSYMS['np_pos_toggle'], count=4000000) == 1 and m.fs[NPPOS] == b'1\n' and m.call(PSYMS['np_pos_setting']) == 1
           and m.call(PSYMS['np_pos_toggle'], count=4000000) == 0 and m.fs[NPPOS] == b'0\n', 'the switch: off by default; a toggle saves 1 atomically, then 0')
    m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.fs[NPPOS] = b'1\n'
    m.play([m.record(rid=1), m.record(rid=2)], 0); m.init()
    expect('label_index' not in m.widgets and m.visible('np_remaining') == 1, 'a page without label_index: nothing is written, the rest works')

    # ------------------------------------------------------------------ the info page (np_header, np_quality, np_row)
    from awtk_text import Ttf, StbText
    import pod_i18n
    ttf = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    ms = lambda t, px: StbText(ttf, px).layout(t)[1] if t else 0
    NowMachine.measure_px = staticmethod(ms)
    stock_en = {'label_info': 'FLAC|44.1kHz|16bit|950kbps', 'label_album': 'Album:Kid A', 'label_genre': 'Genres:Rock',
                'label_year': 'Era:1999', 'label_size': 'File Size:35.92MB', 'label_location': 'Location:SD:/Music/Kid A'}
    T = lambda m, n: m.texts[m.widgets[n]].encode('latin-1').decode('utf-8')
    P = lambda m, n: tuple(m.props.get((m.widgets[n], k)) for k in 'xywh')
    shown = lambda m, n: m.props.get((m.widgets[n], 'visible')) == 1
    gone = lambda m, n: m.props.get((m.widgets[n], 'visible')) == 0 and m.props.get((m.widgets[n], 'sensitive')) == 0
    rowv = lambda m, r: (T(m, f'np_i_k{r}'), T(m, f'np_i_v{r}')) if shown(m, f'np_i_k{r}') else None
    ROW = {'label_genre': 4, 'label_year': 5, 'label_size': 6, 'label_location': 7}
    def info(stock, lang=None, own=True, rec=None, relayed=True, **kw):
        m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.set_language(lang) if lang else None
        for k, v in kw.items(): setattr(m, k, v)
        m.info_page(stock, own)
        if rec is not None: m.play([m.record(**rec)], 0)
        m.init()
        if relayed:
            for _ in range(mn.I_RELAY): m.tick()
        return m
    REC = dict(title='Money', artist='Pink Floyd', album='The Dark Side of the Moon', path='/mnt/mmc/Pink Floyd/05 Money.flac', name='05 Money.flac')
    sets = lambda m: [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_move', 'widget_resize')]
    expect(all(mn.__dict__[k] == O[v] for k, v in (('I_X', 'NPI_X'), ('I_R', 'NPI_R'), ('I_TOP', 'NPI_TOP'), ('I_ART', 'NPI_ART'), ('I_ART_Y', 'NPI_ART_Y'), ('I_ART_R', 'NPI_ART_R'),
                                                   ('I_TEXT_X', 'NPI_TEXT_X'), ('I_TEXT_W', 'NPI_TEXT_W'), ('I_TITLE_Y', 'NPI_TITLE_Y'), ('I_TITLE_PX', 'NPI_TITLE_PX'), ('I_ARTIST_Y', 'NPI_ARTIST_Y'),
                                                   ('I_ALBUM_Y', 'NPI_ALBUM_Y'), ('I_META_PX', 'NPI_META_PX'), ('I_PAD', 'NPI_PAD'), ('I_BADGE_H', 'NPI_BADGE_H'), ('I_BADGE_GAP', 'NPI_BADGE_GAP'),
                                                   ('I_ROW_Y', 'NPI_ROW_Y'), ('I_ROW_PITCH', 'NPI_ROW_PITCH'), ('I_ROW_TEXT', 'NPI_ROW_TEXT'), ('I_ROW_PX', 'NPI_ROW_PX'), ('I_KEY_GAP', 'NPI_KEY_GAP'),
                                                   ('I_ROWS', 'NPI_ROWS'), ('I_LOC_ROW', 'NPI_LOC_ROW'), ('I_LOC_Y', 'NPI_LOC_Y'), ('I_LOC_LH', 'NPI_LOC_LH'), ('I_LOC_LINES', 'NPI_LOC_LINES'), ('I_FOOT', 'NPI_FOOT'),
                                                   ('I_ROW_TAIL', 'M1_FIT_TAIL'), ('I_RELAY', 'NP_RELAY'), ('I_TITLE_LH', 'NPI_TITLE_LH'), ('I_TAP_PX', 'NPI_TAP_PX'), ('I_FADE', 'NPI_FADE'), ('I_PAGE', 'NPI_PAGE'))) and (mn.SCRIM[1], mn.SCRIM[3], mn.SCRIM_ALPHA, mn.SCRIM_EDGE) == (O['NP_SCRIM_Y'], O['NP_SCRIM_H'], O['NP_SCRIM_ALPHA'], O['NP_SCRIM_EDGE']) and mn.I_W == O['NPI_R'] - O['NPI_X'] and mn.I_TOP + O['NPI_VIEW_H'] == mn.I_BOTTOM == 288 and
           mn.I_BADGE_W == {'HI-RES': O['NPI_BADGE_HIRES_W'], 'DSD': O['NPI_BADGE_DSD_W']}, 'the payload\'s info page constants equal the asset builder\'s')

    # ---- the rows: Format, Sample Rate, Bit Depth, Bitrate (stock's quality line), Genre, Year, File Size, Location; a hairline above each, 33 px apart, a missing row leaves a gap that closes
    QS = 'FLAC|44.1kHz|16bit|950kbps'
    vhigh = lambda m: m.props.get((m.widgets['np_i_scroll'], 'virtual_h'))
    def present(m): return [shown(m, f'np_i_k{r}') for r in range(8)]
    def check_flow(m, what):
        """Every hairline, label, value, path line and the virtual height are where the shared model (mod_nowplaying.flow) puts them."""
        pr = present(m); n = 2 if shown(m, 'np_i_v8') else 1
        sh = mn.I_TITLE_LH if shown(m, 'np_i_title2') else 0
        hair, text, loc, bottom = mn.flow(pr, n, sh); bad = []
        for r in range(8):
            if shown(m, f'np_i_h{r}') != pr[r]: bad.append(('hair shown', r))
            if not pr[r]: continue
            if P(m, f'np_i_h{r}') != (16, hair[r] - 36 - m_off(m), 288, 1): bad.append(('hair', r, P(m, f'np_i_h{r}')))
            if P(m, f'np_i_k{r}')[1:] [0] + 2 != text[r] - 36 - m_off(m): bad.append(('key', r, P(m, f'np_i_k{r}')))
            if r != 7 and P(m, f'np_i_v{r}')[1] + 2 != text[r] - 36 - m_off(m): bad.append(('value', r, P(m, f'np_i_v{r}')))
        if pr[7]:
            for k, yy in enumerate(loc):
                if P(m, f'np_i_v{7 + k}')[1] + 2 != yy - 36 - m_off(m) or P(m, f'np_i_v{7 + k}')[0::2] != (16, 288): bad.append(('loc', k, P(m, f'np_i_v{7 + k}')))
        hv = max(bottom - 36, 252)
        expect(not bad and vhigh(m) == hv, f'{what}: the rows are where the model puts them, virtual_h {hv} ({bad[:2]}, {vhigh(m)})')
    m_off = lambda m: 0
    m = info({'label_info': QS})
    want = [('Format', 'FLAC'), ('Sample Rate', '44.1 kHz'), ('Bit Depth', '16 bit'), ('Bitrate', '950 kbps')]
    expect([rowv(m, r) for r in range(4)] == want and gone(m, 'label_info') and not any(present(m)[4:]), f'the four quality rows, label_info hidden and insensitive ({[rowv(m, r) for r in range(4)]})')
    check_flow(m, 'quality rows')
    expect(mn.flow([True] * 8)[0] == {r: 112 + 33 * r for r in range(8)} and mn.flow([True] * 8)[1][0] == 120 and mn.flow([True] * 8)[2] == [371, 391] and mn.flow([True] * 8)[3] == 415,
           'the model: hairlines at 112 and every 33 px, label and value 8 px under, the path lines at 371 and 391, the content ends at 415')
    ok = True
    for r in range(4):
        kx, ky, kw, kh = P(m, f'np_i_k{r}'); vx, vy, vw, vh = P(m, f'np_i_v{r}'); y = 112 + 33 * r + 8 - 36 - 2
        ok = ok and (kx, ky, kh, vy, vh) == (16, y, 20, y, 20) and kw - 4 == ms(want[r][0], 16) and vx + vw == 304 and vx == 16 + kw - 4 + mn.I_KEY_GAP
    expect(ok, 'label at x 16, value box ends at 304 and starts 14 px after the label, text tops 8 px under each row\'s hairline (boxes 2 px higher, in the scroll_view)')
    lines = [f'{c}|{r}kHz|{b}bit|{k}kbps' for c in ('FLAC', 'ALAC', 'WAV', 'APE', 'AIFF', 'MP3', 'OGG', 'DSF') for r, b, k in
             (('44.1', 16, 950), ('48', 24, 2300), ('96', 24, 2800), ('192', 24, 9216), ('352.8', 24, 16934), ('384', 32, 24576), ('2822.4', 1, 5644), ('11289.6', 1, 22579), ('22579.2', 1, 45158))]
    over = [t for t in lines if any(P(info({'label_info': t}), f'np_i_v{r}')[2] < ms(mn.qparse(t)[r], 16) for r in range(4))]
    expect(not over, f'every quality value, 22579.2 kHz DSD included, fits its value box ({over[:3]})')
    for text, want in (('FLAC|44.1kHz|0bit|950kbps', {0: 'FLAC', 1: '44.1 kHz', 3: '950 kbps'}), ('MP3|48kHz|16bit|320kbps', {0: 'MP3', 1: '48 kHz', 2: '16 bit', 3: '320 kbps'}),
                       ('FLAC|0kHz|16bit|0kbps', {0: 'FLAC', 2: '16 bit'}), ('FLAC', {0: 'FLAC'}), ('FLAC | 44.1 kHz | 16-bit | 950 kbps', {0: 'FLAC', 1: '44.1 kHz', 2: '16 bit', 3: '950 kbps'}),
                       ('DSD256|11289.6kHz|1bit|22579kbps', {0: 'DSD256', 1: '11289.6 kHz', 2: '1 bit', 3: '22579 kbps'}), ('FLAC|44.1|16bit|950kbps', {0: 'FLAC', 1: '44.1 kHz', 2: '16 bit', 3: '950 kbps'}),
                       ('|44.1kHz||', {1: '44.1 kHz'})):
        m = info({'label_info': text}); got = {r: rowv(m, r)[1] for r in range(4) if rowv(m, r)}
        expect(got == want == mn.qparse(text) and present(m)[:4] == [r in want for r in range(4)], f'{text!r}: {want} ({got}); a field with no value leaves its row out')
        check_flow(m, text)
    m = info({'label_info': 'FLAC|44.1kHz|0bit|950kbps', 'label_genre': 'G:Rock', 'label_year': 'Y:1999'})
    expect(shown(m, 'np_i_k4') and P(m, 'np_i_h4')[1] + 36 == 112 + 33 * 3 and P(m, 'np_i_h5')[1] + 36 == 112 + 33 * 4 and not shown(m, 'np_i_h2'), 'no bit depth: Genre moves up under the Bitrate row (rows below move up)')
    m = info({'label_info': QS}); m.calls = []
    for _ in range(10): m.texts[m.widgets['label_info']] = QS; m.tick()
    expect(not sets(m) and gone(m, 'label_info'), 'stock rewriting label_info every tick: nothing is laid out again, label_info stays hidden')
    m.texts[m.widgets['label_info']] = 'MP3|48kHz|16bit|320kbps'; m.calls = []; m.tick()
    expect(rowv(m, 0) == ('Format', 'MP3') and len([c for c in sets(m) if c[0] == 'widget_set_text_utf8']) == 8, 'a new quality text is laid out once (four labels, four values)')
    stock_back = lambda m, t: not any(present(m)[:4]) and m.visible('label_info') == 1 and m.label('label_info') == t
    m.texts[m.widgets['label_info']] = 'A' * 600; m.calls = []; m.tick()
    expect(stock_back(m, 'A' * 600) and not any(shown(m, f'np_i_h{r}') for r in range(4)), 'a text too long to read whole: our rows go, stock\'s label shows (never a stale line)')
    m.texts[m.widgets['label_info']] = QS; m.tick()
    expect(rowv(m, 1) == ('Sample Rate', '44.1 kHz') and gone(m, 'label_info'), 'readable again: ours again')
    # a track the player converts to the rate its output is kept at (Crossfade, patch/xfsrc.c XFOUT_FILE): the Sample Rate says so
    XFOUT, RUN = '/tmp/m1plus-xfout', pod.DATA['HCI_RUNNING'][0]
    xfo = lambda rate, magic=0x314f4658: struct.pack('<ii', magic, rate)
    def out(m, blob, running=1):
        m.blobs.pop(XFOUT, None)
        if blob is not None: m.blobs[XFOUT] = blob
        m.u.mem_write(RUN, bytes([running])); m.calls = []; m.tick()
        return (rowv(m, 1) or (None, None))[1]
    expect(out(m, xfo(96000)) == '44.1 \u2192 96 kHz' == mn.resampled('44.1 kHz', 96000)[0], f'the output kept at 96 kHz: "44.1 \u2192 96 kHz" ({rowv(m, 1)}), as the preview\'s model')
    expect(P(m, 'np_i_v1')[2] >= ms('44.1 \u2192 96 kHz', 16) and len([c for c in sets(m) if c[0] == 'widget_set_text_utf8']) == 8, 'it fits the value box, laid out once')
    m.calls = []; m.tick()
    expect(not sets(m), 'an unchanged output rate: the next tick lays nothing out')
    expect(out(m, xfo(0)) == '44.1 kHz', 'the output is the track\'s own again (the record says 0): the plain rate')
    bad = [(r, got) for r, want in ((176400, '176.4 kHz'), (48000, '48 kHz'), (22050, '22.05 kHz'), (384000, '384 kHz'), (8000, '8 kHz'))
           for got in [out(m, xfo(r))] if not got == '44.1 \u2192 ' + want == mn.resampled('44.1 kHz', r)[0]]
    expect(not bad, f'the output rate as stock writes a rate ({bad})')
    bad = [what for what, blob, run in (('the track\'s own rate', xfo(44100), 1), ('no record', None, 1), ('another magic', xfo(96000, 0x304f4658), 1), ('a short record', xfo(96000)[:7], 1),
                                       ('a rate out of range', xfo(400000), 1), ('a negative rate', xfo(-1), 1), ('the player not running', xfo(96000), 0)) if out(m, blob, run) != '44.1 kHz']
    expect(not bad, f'the plain rate otherwise ({bad})')
    m.texts[m.widgets['label_info']] = 'FLAC|0kHz|16bit|0kbps'; out(m, xfo(96000))
    expect(rowv(m, 1) is None, 'no Sample Rate from stock: no row for the output rate alone')
    m.texts[m.widgets['label_info']] = 'DSD256|11289.6kHz|1bit|22579kbps'
    expect(out(m, xfo(352800)) == '11289.6 \u2192 352.8 kHz', 'the longest pair is whole')
    # a long label (French, Polish) leaves no room for both rates: the output's alone, after the arrow; never a cut text
    short, bad, cut = [], [], []
    for lang in pod_i18n.LOCALES:
        for line, rate, full, alt in (('FLAC|44.1kHz|16bit|950kbps', 96000, '44.1 \u2192 96 kHz', '\u2192 96 kHz'), ('FLAC|352.8kHz|24bit|9000kbps', 176400, '352.8 \u2192 176.4 kHz', '\u2192 176.4 kHz')):
            mm = info({'label_info': line}, lang); got = out(mm, xfo(rate)); room = P(mm, 'np_i_v1')[2]
            want = full if ms(full, 16) <= room else alt
            if (full, alt) != mn.resampled(mn.qparse(line)[1], rate): bad.append((lang, 'model'))
            if ms(alt, 16) > room: cut.append((lang, rate, got))
            elif got != want or ms(got, 16) > room: bad.append((lang, got))
            if want == alt and rate == 96000: short.append(lang)
    expect(not bad and short == ['fr_FR', 'po_PL'], f'every language: both rates when they fit beside the label, else the output\'s alone ({bad}; 44.1 to 96 kHz short in {short})')
    expect([c[:2] for c in cut] == [('fr_FR', 176400)] and cut[0][2].startswith('\u2192 176.4') and cut[0][2].endswith('...'),
           f'only the French label leaves less than "\u2192 176.4 kHz" needs: that one is cut like any long value ({cut})')
    m.blobs.pop(XFOUT, None); m.u.mem_write(RUN, b'\0'); m.texts[m.widgets['label_info']] = QS; m.tick()
    m.texts[m.widgets['label_info']] = '||||'; m.tick()
    expect(stock_back(m, '||||'), 'a text with no field: stock\'s label')
    m.texts[m.widgets['label_info']] = QS; m.get_ret = 1; m.tick(); m.get_ret = 0
    expect(not shown(m, 'np_i_k0'), 'a failed read: ours are hidden')
    m = info({'label_info': QS}, own=False)
    expect(m.visible('label_info') is None and not sets(m), 'without our widgets the page keeps stock\'s label_info')

    m = info(stock_en)
    want = [('Format', 'FLAC'), ('Sample Rate', '44.1 kHz'), ('Bit Depth', '16 bit'), ('Bitrate', '950 kbps'), ('Genre', 'Rock'), ('Year', '1999'), ('File Size', '35.92 MB'), ('Location', 'SD:/Music/Kid A')]
    got = [rowv(m, r) for r in range(7)] + [(T(m, 'np_i_k7'), T(m, 'np_i_v7'))]
    expect(got == want and not shown(m, 'np_i_v8'), f'English rows ({got})')
    expect(all(gone(m, n) for n in ROW), 'the stock labels are hidden and insensitive while ours show')
    check_flow(m, 'all eight rows, a one line path')
    m.calls = []; m.tick(); m.tick()
    expect(not sets(m), 'ticks after that leave the page alone (no loop)')
    m.texts[m.widgets['label_year']] = 'Era:2001'; m.calls = []; m.tick()
    expect(rowv(m, 5) == ('Year', '2001') and len([c for c in sets(m) if c[0] == 'widget_set_text_utf8']) == 2, 'stock writing a line again is answered once, that row only (label and value)')
    cases = {'label_genre': {'Genres:Unknown': 'Unknown', 'Genres:  two spaces': 'two spaces', 'Genres:A: B': 'A: B', 'Genres:Mega 2MB': 'Mega 2MB'},
             'label_size': {'File Size:0.00MB': '0.00 MB', 'File Size: 7.10 MB': '7.10 MB', 'File Size:Unknown': 'Unknown'}, 'label_year': {'Era:0': '0'}}
    bad = [(b, rowv(info({lbl: b}), ROW[lbl])) for lbl, t in cases.items() for b, a in t.items() if (rowv(info({lbl: b}), ROW[lbl]) or ('', ''))[1] != a]
    expect(not bad, f'value cases ({bad})')
    # every language: the keys are ours in that language; Location is stock's word
    for lang in pod_i18n.LOCALES:
        m = info({'label_info': QS, 'label_genre': 'X:Rock', 'label_year': 'Y:1999', 'label_size': 'Z:3.50MB', 'label_location': 'W:SD:/a'}, lang)
        T2 = pod_i18n.TEXT
        keys = [T2[k][lang] for k in ('Format', 'Sample Rate', 'Bit Depth', 'Bitrate', 'Genre', 'Year', 'File Size')] + ['W']
        got = [rowv(m, r)[0] for r in range(7)] + [T(m, 'np_i_k7')]
        expect(got == keys, f'{lang}: our keys, stock\'s Location ({got})')
        kw_ = [ms(keys[r], 16) for r in range(7)]
        expect(all(P(m, f'np_i_v{r}')[2] == mn.I_W - kw_[r] - mn.I_KEY_GAP for r in range(7)), f'{lang}: each value has the room its label leaves')
        check_flow(m, lang)
    expect(pod_i18n.TEXT['File Size']['uk_UK'] == 'Розмір файлу' and pod_i18n.TEXT['File Size']['en_US'] == 'File Size', 'Ukrainian File Size is not stock\'s "Місцезнаходження"')
    # the Location: its label on a line of its own, the path under it in up to two lines of 288 px
    LW = lambda loc: mn.loc_wrap(loc, 288, lambda t: ms(t, 16))
    def loc_lines(loc):
        m = info(dict(stock_en, label_location='Location:' + loc)); return [T(m, f'np_i_v{k}') for k in (7, 8) if shown(m, f'np_i_v{k}')], m
    two = 'SD:/Music/Pink Floyd/The Dark Side of the Moon/05 Money.flac'
    four = 'SD:/Music/Hi-Res/Pink Floyd/Wish You Were Here (2011 Remastered Version)/04 Wish You Were Here.flac'
    seg = 'SD:/' + 'ABCDEFGHIJKLMNOP' * 3 + '.flac'
    cjk = 'SD:/音乐/' + '歌' * 30 + '/' + '曲' * 20 + '.flac'
    huge = 'SD:/' + 'W' * 120 + '/Album/' + 'q' * 60 + '/END.flac'
    long_loc = 'SD:/' + '/'.join(f'folder number {i}' for i in range(18)) + '/05 Money.flac'
    for name, loc, n_lines in (('short', 'SD:/Music/Kid A', 1), ('two lines, break after a slash', two, 2), ('long', four, 2), ('long segment (character break)', seg, 2), ('CJK', cjk, 2),
                               ('head cut', huge, 2), ('over 200 bytes', long_loc, 2), ('accents', 'SD:/' + 'é' * 150 + '.wav', 2)):
        got, m = loc_lines(loc)
        expect(got == LW(loc) and len(got) == n_lines and all(ms(l, 16) <= 288 for l in got) and P(m, 'np_i_k7')[0] == 16 and P(m, 'np_i_v7')[0::2] == (16, 288),
               f'{name}: {got} the model\'s {len(LW(loc))} line(s), each within 288 px, left aligned under the label')
        check_flow(m, name)
    expect(LW('SD:/Music/Kid A') == ['SD:/Music/Kid A'] and LW(two)[0].endswith('/') and ''.join(LW(two)) == two, 'rule 1 and 2: one line when it fits, else a break after a slash with nothing lost')
    l3 = LW(seg); expect(len(l3) == 2 and ''.join(l3) == seg and not l3[0].endswith('/') and ms(l3[0] + seg[len(l3[0])], 16) > 288, 'rule 3: a segment wider than a line breaks at the last character that fits')
    l4 = LW(long_loc); expect(l4[0].startswith('...') and l4[1] and long_loc.endswith(l4[1]) and (l4[0][3:] + l4[1]) in long_loc and long_loc.endswith(l4[0][3:] + l4[1]), 'rule 4: line 2 is the end of the path, line 1 "..." and the text just before it')
    l4 = LW(huge); expect(l4[0].startswith('...') and huge.endswith(l4[1]) and ms(l4[1], 16) <= 288 < ms(huge[len(huge) - len(l4[1]) - 1:], 16), 'rule 4: line 2 holds as much of the end as fits')
    expect(all(len(LW(p)) <= 2 and all(ms(l, 16) <= 288 for l in LW(p)) for p in (two, four, seg, cjk, huge, long_loc, 'a' * 300, 'W' * 300, '/' * 300, '歌' * 300)), 'every sample fits two lines of 288 px')
    # the content grows with the path
    h = lambda loc: vhigh(loc_lines(loc)[1])
    expect(h('SD:/Music/Kid A') == 415 - 36 - 20 and h(four) == 415 - 36, f'virtual_h: {h("SD:/Music/Kid A")} for one path line, {h(four)} for two')
    # a line that is not "Label:value", too long to read whole or unreadable is stock's label (never half ours)
    m = info(dict(stock_en, label_genre='Unknown', label_year=':1999', label_size='', label_location='x' * 600))
    expect(all(not shown(m, f'np_i_k{r}') for r in range(4, 8)) and all(m.visible(n) != 0 for n in ROW) and all(shown(m, f'np_i_k{r}') for r in range(4)), 'no colon, a leading colon, empty, too long: the four lines are stock\'s labels')
    check_flow(m, 'stock lines back')
    m = info(stock_en); m.texts[m.widgets['label_genre']] = 'Genres'; m.tick()
    expect(rowv(m, 4) is None and m.visible('label_genre') == 1 and rowv(m, 5) is not None, 'one bad line gives only that row back')
    check_flow(m, 'one row back')
    m.texts[m.widgets['label_genre']] = 'Genres:Jazz'; m.tick()
    expect(rowv(m, 4) == ('Genre', 'Jazz') and gone(m, 'label_genre'), 'and the next good text takes it over again')
    m = info(stock_en, get_ret=0x10)
    expect(not any(present(m)), 'a failed read: stock\'s labels stay')
    for t in ('Genres:' + 'x' * 600, 'Genres:' + '歌' * 200, 'Genres:' + 'x' * 506):
        m = info({'label_genre': t}); expect(rowv(m, 4) is None and m.visible('label_genre') != 0, f'a tag of {len(t.encode())} bytes (the buffer holds 511 and a NUL): stock\'s label')
    m = info({'label_genre': 'Genres:' + 'x' * 500}); expect(rowv(m, 4) == ('Genre', mn.end_fit('x' * 500, P(m, 'np_i_v4')[2], lambda x: ms(x, 16))) and ms(rowv(m, 4)[1], 16) <= P(m, 'np_i_v4')[2], 'a text that fits the buffer is ours (cut to its room)')
    m = info({'label_genre': 'Genres:Rock'}, own=False)
    expect(m.visible('label_genre') is None and not sets(m), 'a page without our row labels leaves stock\'s alone')
    # layout again for NP_RELAY ticks: a label measures in its own style only once the window is open (the first look can be wrong)
    placed = lambda m: [P(m, f'np_i_{k}{r}') for r in range(8) for k in 'kvh']
    m = info(stock_en, relayed=False); first = placed(m)
    NowMachine.measure_px = staticmethod(lambda t, px: 2 * ms(t, px)); m.tick()
    expect(placed(m) != first, 'the next tick lays the page out again (the measure changed)')
    NowMachine.measure_px = staticmethod(ms); m.tick(); m.tick(); m.calls = []; m.tick()
    expect(placed(m) == first and not sets(m), 'the relay ends after NP_RELAY looks: then only a new text lays out')
    # the scroll offset: one helper moves every child (phase 2 drives it)
    P = lambda m, n: tuple((v - 2**32 if v is not None and v >= 2**31 else v) for v in (m.props.get((m.widgets[n], k)) for k in 'xywh'))
    m = info(stock_en, rec=REC); at0 = {n: P(m, n) for n in m.widgets if n.startswith('np_i_') and n != 'np_i_scroll' and m.props.get((m.widgets[n], 'x')) is not None}
    expect(len(at0) >= 24 and P(m, 'np_i_art')[1] == 0 and P(m, 'np_i_h0')[1] == 112 - 36, 'at offset 0 the cover is at the scroll_view\'s top')
    m.call(PSYMS['np_info_scroll'], a0=40)
    moved = {n: P(m, n) for n in at0}
    expect(all(moved[n][1] == at0[n][1] - 40 and moved[n][0::2] == at0[n][0::2] for n in at0), f'offset 40: every widget moves up 40 px, x and size unchanged ({[n for n in at0 if moved[n][1] != at0[n][1] - 40][:3]})')
    m.call(PSYMS['np_info_scroll'], a0=10000)
    top = vhigh(m) - 252
    expect(P(m, 'np_i_art')[1] == -top, f'the offset is clamped to the content height less the view ({top})')
    m.call(PSYMS['np_info_scroll'], a0=-5)
    expect({n: P(m, n) for n in at0} == at0, 'a negative offset is the top')
    m.call(PSYMS['np_info_scroll'], a0=40); m.play([m.record(title='Next', artist='X', album='Y', path='/mnt/mmc/x/9.flac', name='9.flac', rid=9)], 0); m.tick()
    expect(P(m, 'np_i_art')[1] == 0 and P(m, 'np_i_h0')[1] == 112 - 36, 'a new track: back at the top')


    # ---- finger scrolling: a vertical drag of NPI_TAP_PX or more moves the content with the finger, clamped; a sideways one, a tap and a short wobble do nothing; the page's own listeners
    D_, MV_, UP_, AB_ = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
    def ptr(m, kind, x, y):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e, kind); m.setword(e + O['PE_X'], x); m.setword(e + O['PE_Y'], y)
        return m.call(PSYMS['np_on_info_touch'], a0=m.widgets['np_i_scroll'], a1=e, count=2000000)
    offs = lambda m: -P(m, 'np_i_art')[1]
    m = info(stock_en, rec=REC)
    on = [m.bound.get((m.widgets['np_i_scroll'], ev), (0,))[0] for ev in (D_, MV_, UP_, AB_, EVT_AFTER_PAINT)]
    expect(on == [PSYMS['np_on_info_touch']] * 4 + [PSYMS['np_on_info_fade']], f'np_i_scroll listens to DOWN, MOVE, UP, ABORT and paints the fades after its children ({on})')
    expect(m.bound[(m.widgets['slide_view'], O['EVT_VALUE_CHANGED'])][0] == PSYMS['np_on_page'], 'the slide view\'s page change is listened to')
    m.calls = []; top = vhigh(m) - 252
    r = [ptr(m, D_, 100, 200), ptr(m, MV_, 100, 195), ptr(m, MV_, 101, 191), ptr(m, UP_, 101, 191)]
    expect(r == [0] * 4 and offs(m) == 0 and not sets(m), 'a tap or a wobble under 10 px: nothing moves, RET_OK (never RET_STOP)')
    r = [ptr(m, D_, 100, 200), ptr(m, MV_, 100, 185)]
    expect(offs(m) == 0 and r == [0, O['RET_STOP']], 'the drag has begun at 10 px, the content does not jump; the MOVE that began it is stopped (the slide view gets an ABORT)')
    expect(ptr(m, MV_, 100, 165) == O['RET_STOP'] and offs(m) == 20, 'then it follows the finger up: 20 px, every MOVE stopped')
    ptr(m, MV_, 100, 175); expect(offs(m) == 10, 'and back down 10 px')
    expect(ptr(m, MV_, 140, 100) == O['RET_STOP'] and offs(m) == 85, 'a sideways wobble after the drag began does not stop it, and the slide view never sees it (RET_STOP)')
    ptr(m, MV_, 100, -300); expect(offs(m) == top, f'clamped at the content end ({top})')
    ptr(m, MV_, 100, -280); expect(offs(m) == top - 20, 'coming back moves at once (no overscroll to unwind)')
    r = [ptr(m, UP_, 100, -280), ptr(m, MV_, 100, -100)]
    expect(offs(m) == top - 20 and r == [0, 0], 'after UP a stray MOVE does nothing (UP and that MOVE answer RET_OK)')
    ptr(m, D_, 100, 50); ptr(m, MV_, 100, 70); ptr(m, MV_, 100, 400); expect(offs(m) == 0, 'dragging down clamps at the top')
    ptr(m, AB_, 100, 400)
    m.call(PSYMS['np_info_scroll'], a0=30)
    ptr(m, D_, 100, 200); ptr(m, MV_, 140, 203); ptr(m, MV_, 140, 100)
    expect(offs(m) == 30, 'a sideways drag (the page swipe) is left to the slide view: the content stays')
    r = [ptr(m, UP_, 140, 100), ptr(m, D_, 100, 200), ptr(m, MV_, 115, 188), ptr(m, MV_, 112, 150)]
    expect(r == [0] * 4, 'a sideways or diagonal swipe answers RET_OK: the slide view turns the page')
    expect(offs(m) == 30, 'a diagonal drag that is more sideways than vertical is the swipe too')
    ptr(m, AB_, 112, 150); ptr(m, D_, 100, 200); ptr(m, MV_, 100, 150); ptr(m, AB_, 100, 150); ptr(m, MV_, 100, 100)
    expect(offs(m) == 30, 'an abort ends the drag: later moves do nothing')
    expect(ptr(m, D_, 1, 1) == 0 and ptr(m, MV_, 1, 1) == 0, 'DOWN and a MOVE that is no drag answer RET_OK')
    short = info({'label_info': 'FLAC|44.1kHz|16bit|950kbps'}, rec=REC)
    ptr(short, D_, 100, 200); ptr(short, MV_, 100, 150); ptr(short, MV_, 100, 100)
    expect(vhigh(short) == 252 and offs(short) == 0, 'content that fits is not scrolled')
    # back at the top whenever the info page is entered again
    m = info(stock_en, rec=REC); sv = m.widgets['slide_view']
    m.call(PSYMS['np_info_scroll'], a0=50); m.tick()
    expect(offs(m) == 50, 'on the info page the tick leaves the offset alone')
    m.props[(sv, 'value')] = 1; m.tick()
    expect(offs(m) == 0, 'the slide view on another page: the content goes to the top (the tick)')
    m.props[(sv, 'value')] = mn.I_PAGE; m.call(PSYMS['np_info_scroll'], a0=50)
    m.props[(sv, 'value')] = 0; fn, ctx = m.bound[(sv, O['EVT_VALUE_CHANGED'])]; m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(offs(m) == 0, 'and at once by the slide view\'s value change')
    m.props[(sv, 'value')] = mn.I_PAGE; m.call(PSYMS['np_info_scroll'], a0=50); m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(offs(m) == 50, 'a value change that lands on the info page keeps it')
    m.fire(O['EVT_WINDOW_TO_FG'], WIN)
    expect(offs(m) == 0, 'Now Playing in front again: the top')

    # ---- the title: up to two lines of 212 px, a word break, a character break for CJK and one long word, an end ellipsis only when two lines are not enough; the header below moves down by 24
    TW = lambda t: mn.title_wrap(t, 212, lambda x: ms(x, 20))
    def title_page(t):
        m = info(stock_en, rec=dict(REC, title=t)); return m
    one = title_page('Money')
    expect((T(one, 'np_i_title'), T(one, 'np_i_title2')) == ('Money', '') and not shown(one, 'np_i_title2') and P(one, 'np_i_title') == (92, 0, 212, 24) and P(one, 'np_i_artist')[1] == 24 and P(one, 'np_i_album')[1] == 44 and P(one, 'np_i_h0')[1] == 76,
           'a one line title looks as before: one label, artist and album at 62 / 82, the first hairline at 112')
    tcases = {'a word break': 'Wish You Were Here (2011 Remastered Version)', 'a longer two lines': 'Bohemian Rhapsody (Remastered 2011)',
              'CJK': '夜曲' * 9, 'CJK and Latin': '夜に駆ける (YOASOBI) Official Music Video Remastered', 'one long word': 'Supercalifragilisticexpialidocious' * 2, 'ellipsis': 'Wish You Were Here ' * 6,
              'Cyrillic': 'Прекрасное далёко (из к/ф Гостья из будущего) Remastered', 'Arabic': 'مرحبا بالعالم الجميل في كل مكان ومن كل مكان', 'accents': 'Éléphant à côté de l’océan très éloigné d’ici', 'spaces': 'Hello   ' + 'W' * 30 + '   World   ' + 'x' * 20}
    for name, t in tcases.items():
        m = title_page(t); lines, cut = TW(t); got = [T(m, 'np_i_title')] + ([T(m, 'np_i_title2')] if shown(m, 'np_i_title2') else [])
        ok = got == lines and all(ms(l, 20) <= 212 for l in lines) and cut == lines[-1].endswith('...')
        expect(ok and len(lines) <= 2, f'{name}: {got} the model\'s {lines}, line 1 within 212 px, line 2 {"cut with an end ellipsis" if cut else "whole"}')
        sh = 24 if len(lines) > 1 else 0
        expect(P(m, 'np_i_art')[1] == 0 and P(m, 'np_i_title') == (92, 0, 212, 24) and (len(lines) < 2 or P(m, 'np_i_title2') == (92, 24, 212, 24)) and P(m, 'np_i_artist')[1] == 24 + sh and P(m, 'np_i_album')[1] == 44 + sh and P(m, 'np_i_h0')[1] == 76 + sh,
               f'{name}: the cover stays, artist, album and the first hairline move down {sh} px')
        check_flow(m, name)
    ls, cut = TW(tcases['a longer two lines']); expect(len(ls) == 2 and not cut and ' '.join(ls) == tcases['a longer two lines'] and ls[0] == 'Bohemian Rhapsody', f'a word break: no word is cut ({ls})')
    ls, cut = TW(tcases['a word break']); expect(ls[0] == 'Wish You Were Here' and ls[1].startswith('(2011 Remastered') and cut and ls[1].endswith('...') and ms(ls[1], 20) <= 212, f'the word break is kept even when line 2 then needs its end ellipsis ({ls})')
    ls, cut = TW('周杰伦 Jay Chou 稻香 Rice Fragrance'); expect(len(ls) == 2 and ' ' not in ls[0][-1:] and ls[0].split(' ')[-1] != '' and ''.join(ls).replace(' ', '') == '周杰伦JayChou稻香RiceFragrance' and ls[0].count(' ') >= 1, f'mixed text breaks at a space when one qualifies ({ls})')
    ls, cut = TW(tcases['CJK']); expect(len(ls) == 2 and not cut and ''.join(ls) == tcases['CJK'] and ms(ls[0], 20) <= 212 and ms(ls[0] + '夜', 20) > 212, 'CJK has no space: a character break at the last character that fits, nothing lost')
    ls, cut = TW(tcases['one long word']); expect(len(ls) == 2 and cut and ls[1].endswith('...') and tcases['one long word'].startswith(ls[0] + ls[1][:-3]) and ms(ls[0], 20) <= 212 and ms(ls[0] + ls[1][0], 20) > 212 and ms(ls[1], 20) <= 212, 'one long word breaks at the last character that fits line 1, line 2 ends in the ellipsis')
    ls, cut = TW(tcases['ellipsis']); expect(cut and len(ls) == 2 and ls[1].endswith('...') and not ls[1].endswith(' ...') and ms(ls[1], 20) <= 212 and tcases['ellipsis'].startswith(ls[0] + ' ' + ls[1][:-3]), 'more than two lines: line 2 is the longest start of the rest that fits with the ellipsis after it')
    ls, cut = TW(tcases['spaces']); expect(not ls[0].endswith(' ') and not ls[1].startswith(' '), 'the spaces round a break are dropped')
    m = title_page('Wish You Were Here (2011 Remastered Version)'); h2 = vhigh(m); h1 = vhigh(title_page('Money'))
    expect(h2 == h1 + 24, f'two lines make the content 24 px longer ({h1} -> {h2})')

    # ---- the plain labels have no ellipsis of their own: a long artist, album or value is cut to its room with "..." after it (m1_fit; tools/mod_nowplaying.py end_fit)
    EF = lambda t, room, px=16: mn.end_fit(t, room, lambda x: ms(x, px))
    for name, artist, album in (('Latin', 'The Jimi Hendrix Experience and Friends Live', 'Electric Ladyland (50th Anniversary Deluxe Edition)'), ('CJK', '久石譲' * 9, '千と千尋の神隠し サウンドトラック ' * 3),
                                ('short', 'Pink Floyd', 'The Wall'), ('a space before the cut', 'A' * 21 + '    ' + 'B' * 20, 'W' * 40)):
        m = info(stock_en, rec=dict(REC, artist=artist, album=album)); got = (T(m, 'np_i_artist'), T(m, 'np_i_album'))
        expect(got == (EF(artist, 212), EF(album, 212)) and all(ms(g, 16) <= 212 and ' ...' not in g for g in got) and (name != 'short' or got == (artist, album)) and (name == 'short' or all(g.endswith('...') for g in got)),
               f'{name}: artist and album within 212 px, the longest start that fits and "..." ({got})')
    genre = 'Progressive Rock; Psychedelic Rock; Art Rock; Experimental'
    m = info(dict(stock_en, label_genre='Genres:' + genre)); room = P(m, 'np_i_v4')[2]
    expect(T(m, 'np_i_v4') == EF(genre, room) and T(m, 'np_i_v4').endswith('...') and ms(T(m, 'np_i_v4'), 16) <= room and T(m, 'np_i_v5') == '1999', f'a value wider than its room is cut with "..." ({T(m, "np_i_v4")}, {room} px); the others stay whole')
    for genre in ('\U0001F3B5' * 50 + 'Progressive Rock', '\u200b' * 70 + 'Progressive Rock and more', 'i' * 201):
        m = info(dict(stock_en, label_genre='Genres:' + genre)); room = P(m, 'np_i_v4')[2]; got = T(m, 'np_i_v4')
        expect(got == EF(genre, room) and got.endswith('...') and ms(got, 16) <= room, f'a value over {mn.I_ROW_TAIL} bytes is never shown whole, even when its measured start fits ({len(genre.encode())} bytes -> {ms(got, 16)} of {room} px)')
    m.call(PSYMS['np_info_scroll'], a0=10000); expect(P(m, 'np_i_art')[1] == -(vhigh(m) - 252), 'the scroll range follows')
    m.play([m.record(title='Short', artist='X', album='Y', path='/mnt/mmc/x/9.flac', name='9.flac', rid=9)], 0); m.tick()
    expect(not shown(m, 'np_i_title2') and T(m, 'np_i_title2') == '' and P(m, 'np_i_artist')[1] == 24 and vhigh(m) == h1, 'the next track with a short title: one line again, the second label hidden and empty')
    for lang in pod_i18n.LOCALES:
        m = info(stock_en, lang, rec=dict(REC, title=tcases['a word break'])); l, _ = TW(tcases['a word break'])
        expect(T(m, 'np_i_title') == l[0] and shown(m, 'np_i_title2'), f'{lang}: the title wraps the same')
    m = info(stock_en, rec=REC, own=False)
    expect(not [c for c in m.calls if c[0] == 'widget_on' and c[2] == D_], 'without our widgets nothing is bound to touch')

    # ---- the header: the record's title, artist and album, the cover thumbnail, the HI-RES / DSD badge
    m = info(stock_en, rec=REC)
    expect((T(m, 'np_i_title'), T(m, 'np_i_artist'), T(m, 'np_i_album')) == ('Money', 'Pink Floyd', 'The Dark Side of the Moon'), 'title, artist and album of the playing record')
    expect(P(m, 'np_i_title') == (92, 0, 212, 24) and P(m, 'np_i_artist') == (92, 24, 212, 20) and P(m, 'np_i_album') == (92, 44, 212, 20), 'x 92, 212 wide, text tops 38 / 62 / 82 (boxes 2 px higher), in the scroll_view that starts at y 36')
    expect(gone(m, 'label_album') and not shown(m, 'np_i_badge_hires') and not shown(m, 'np_i_badge_dsd'), 'stock\'s album label is hidden and insensitive; no badge on a CD-quality track')
    expect(any(c[0] == 'widget_invalidate_force' and c[1] == m.widgets['np_i_art'] for c in m.calls) or m.bitmaps, 'the cover is drawn into its own bitmap, the view repainted')
    m.calls = []; m.tick(); m.tick()
    expect(not sets(m), 'the header is not set again while the track is the same')
    m.play([m.record(title='Other', artist='X', album='Y', path='/mnt/mmc/x/2.flac', name='2.flac', rid=2)], 0); m.tick()
    expect((T(m, 'np_i_title'), T(m, 'np_i_artist'), T(m, 'np_i_album')) == ('Other', 'X', 'Y'), 'the next track: new texts')
    m.play([m.record(title='', artist='X', album='', path='/mnt/mmc/x/3.flac', name='3 Name.flac', rid=3)], 0); m.tick()
    expect((T(m, 'np_i_title'), T(m, 'np_i_album')) == ('3 Name.flac', ''), 'no title: the file name; no album: an empty line')
    m.play([m.record(title='歌' * 100, artist='a', album='b', rid=4)], 0); m.tick()
    expect(len(m.texts[m.widgets['np_i_title']]) <= 199 and len(m.texts[m.widgets['np_i_title2']]) <= 199 and T(m, 'np_i_title2').endswith('...') and ('歌' * 66).startswith(T(m, 'np_i_title') + T(m, 'np_i_title2')[:-3]) and ms(T(m, 'np_i_title2'), 20) <= 212, 'a long title is cut at a character boundary below 200 bytes, its second line to the column with the ellipsis')
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque([])); m.tick()
    expect(T(m, 'np_i_title') == '' and not shown(m, 'np_i_badge_hires'), 'no record: an empty header')
    m = info(stock_en)
    expect(T(m, 'np_i_title') == '' and T(m, 'np_i_album') == '', 'no playing record at all: an empty header')
    m = info(stock_en, rec=REC)
    expect(all(shown(m, n) for n in ('np_i_title', 'np_i_artist', 'np_i_album')), 'the header\'s title, artist and album are visible once the page runs')
    # the badge: the cassette theme's rule (tape_badge): lossless and (over 48 kHz, or 24 bit from 44.1 kHz) is HI-RES, 1 bit is DSD, nothing for CD quality or lossy
    def badge(rate, bits, fmt, path, **kw):
        m = info(stock_en, rec=dict(REC, path=path, **kw), info=dict(rate=rate, bits=bits, fmt=fmt))
        return ('HI-RES' if shown(m, 'np_i_badge_hires') else 'DSD' if shown(m, 'np_i_badge_dsd') else ''), m
    for args, want in (((44100, 16, 'FLAC', '/m/a.flac'), ''), ((96000, 24, 'FLAC', '/m/a.flac'), 'HI-RES'), ((44100, 24, 'FLAC', '/m/a.flac'), 'HI-RES'), ((48000, 24, 'WAV', '/m/a.wav'), 'HI-RES'), ((48000, 16, 'WAV', '/m/a.wav'), ''),
                       ((48000, 16, 'FLAC', '/m/a.flac'), ''), ((88200, 16, 'ALAC', '/m/a.m4a'), 'HI-RES'), ((96000, 24, 'MP3', '/m/a.mp3'), ''), ((320000 // 8, 16, 'AAC', '/m/a.m4a'), ''),
                       ((2822400, 1, 'DSD', '/m/a.dsf'), 'DSD'), ((11289600, 1, 'DSD', '/m/a.dff'), 'DSD'), ((44100, 16, 'MP3', '/m/a.mp3'), ''), ((192000, 32, 'FLAC', '/m/a.flac'), 'HI-RES')):
        got, m = badge(*args)
        expect(got == want, f'{args}: badge {want!r} ({got!r})')
    got, m = badge(96000, 24, 'FLAC', '/m/a.flac')
    w = O['NPI_BADGE_HIRES_W']; fw = ms('FLAC', 16); ty = 112 + 8 - 36
    expect(P(m, 'np_i_badge_hires') == (304 - fw - 8 - w, ty - 1, w, 18) and P(m, 'np_i_title')[2] == 212 and P(m, 'np_i_artist')[2] == 212 and not shown(m, 'np_i_badge_dsd'),
           f'HI-RES: on the Format row, 8 px left of the right aligned value, centred on its text; the title keeps all 212 px ({P(m, "np_i_badge_hires")})')
    got, m = badge(2822400, 1, 'DSD', '/m/a.dsf'); w = O['NPI_BADGE_DSD_W']
    expect(P(m, 'np_i_badge_dsd') == (304 - fw - 8 - w, ty - 1, w, 18) and P(m, 'np_i_title')[2] == 212 and not shown(m, 'np_i_badge_hires'), 'DSD badge likewise')
    m = info({'label_info': 'FLAC|96kHz|0bit|0kbps'.replace('FLAC', 'WAV')}, rec=dict(REC, path='/m/a.wav'), info=dict(rate=96000, bits=24, fmt='WAV'))
    expect(shown(m, 'np_i_badge_hires') and P(m, 'np_i_badge_hires')[0] == 304 - ms('WAV', 16) - 8 - O['NPI_BADGE_HIRES_W'], 'the badge follows the value\'s width')
    m = info({'label_info': '|96kHz|24bit|2000kbps'}, rec=dict(REC, path='/m/a.flac'), info=dict(rate=96000, bits=24, fmt='FLAC'))
    expect(not shown(m, 'np_i_badge_hires') and not shown(m, 'np_i_k0'), 'no Format row (no format text): no badge')
    m = info(stock_en, rec=dict(REC, path='/m/a.flac'), info=dict(rate=96000, bits=24, fmt='FLAC')); m.texts[m.widgets['label_info']] = 'FLAC|96kHz|24bit|2000kbps'
    expect(shown(m, 'np_i_badge_hires') and not sets(m), 'the badge stays through ticks'); m.texts[m.widgets['label_info']] = 'A' * 600; m.tick()
    expect(not shown(m, 'np_i_badge_hires'), 'rows given back to stock: the badge goes too')
    m = info(stock_en, rec=dict(REC, path='/m/a.flac'), info=dict(rate=96000, bits=24, fmt='FLAC'))
    check_flow(m, 'with a badge')
    m.info = dict(rate=44100, bits=16, fmt='FLAC'); m.play([m.record(**dict(REC, path='/m/b.flac', rid=7))], 0); m.tick()
    expect(not shown(m, 'np_i_badge_dsd') and P(m, 'np_i_title')[2] == 212, 'the next track has none: the badge goes and the title is full width again')
    m = info(stock_en, rec=dict(REC, path='/m/a.dsf'), info=None)
    expect(shown(m, 'np_i_badge_dsd'), 'DSD by its extension while the player has no stream yet')
    # the page's end: the timer is gone, nothing is touched, the cover bitmap is freed
    m = info(stock_en, rec=REC); m.calls = []; m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(any(c[0] == 'bitmap_destroy' for c in m.calls), 'the page\'s end frees the header cover')
    m.calls = []; m.texts[m.widgets['label_genre']] = 'Genres:Z'; m.tick()
    expect(not sets(m), 'after the page is gone a stray tick touches nothing')
    m = NowMachine(); m.page(); m.src(0); m.info_page(stock_en, True); m.widgets.pop('np_i_album'); m.init()
    expect(m.visible('label_album') is None and not shown(m, 'np_i_title') and rowv(m, 4) == ('Genre', 'Rock'), 'an asset without the whole header: stock\'s album label stays, the rest works')

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
    secondary = {'stock lyric inactive': (dim, 2.5, 'l'), 'stock lyric current': (cur, 4.4, 'l'), 'info label': (col(mn.GREY), 3.0, 'i'), 'info quality line': (col(mn.TITLE_RGB), 4.5, 'i'), 'info location': (col(mn.GREY), 3.0, 'i')}
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
    # hand-over with the album page (m1_bar_tint / m1_bar_black: only the owner restores)
    ALBUM = WIN + 0x200
    m = tinted(); m.bar_styles.clear()
    expect(m.call(PSYMS['m1_bar_tint'], a0=ALBUM, a1=0x00112233) == 1 and len(m.bar_styles) == 1, 'the album page takes the bar over from Now Playing')
    m.fire(O['EVT_WINDOW_TO_BG']); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(len(m.bar_styles) == 1 and m.bar_color() != BLACK, 'Now Playing\'s late background event and destroy (Back) leave the album page\'s colour alone')
    m = tinted(); m.bar_styles.clear(); m.call(PSYMS['m1_bar_tint'], a0=ALBUM, a1=0x00112233); m.bar_styles.clear(); m.tick(); m.tick()
    expect(not m.bar_styles, 'ticks while the album page owns the bar do not take it back (the page is not the top window)')
    m = tinted(); m.fire(O['EVT_WINDOW_TO_BG']); m.bar_styles.clear()
    m.call(PSYMS['m1_bar_tint'], a0=ALBUM, a1=0x00112233); m.fire(O['EVT_WINDOW_TO_FG'])
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

    # ------------------------------------------------------------------ paused, the cover shrinks (a spring) and springs back on play
    import math
    def spring(ms, z, w):   # 1024 x the spring's remaining fraction every 10 ms (patch/nowplaying.c np_shrink_tab, np_grow_tab)
        def g(t):
            if z >= 1: return (1 + w * t) * math.exp(-w * t)
            wd = w * math.sqrt(1 - z * z); return math.exp(-z * w * t) * (math.cos(wd * t) + z / math.sqrt(1 - z * z) * math.sin(wd * t))
        return [round(1024 * g(k / 100)) for k in range(ms // 10 + 1)]
    SHRINK, GROW = spring(O['NP_SHRINK_MS'], 1.0, 22), spring(O['NP_GROW_MS'], 0.75, 18)
    def size_model(a, b, el):
        tab, ms = (GROW, O['NP_GROW_MS']) if b > a else (SHRINK, O['NP_SHRINK_MS'])
        if el <= 0: return a
        if el >= ms: return b
        i = el // 10; g = tab[i] + int((tab[i + 1] - tab[i]) * (el % 10) / 10)
        d = (a - b) * g; return b + 2 * int((d + (1024 if d >= 0 else -1024)) / 2048)   # an even number of px from the target: half on each side
    A, S_ = O['NP_ART'], O['NP_ART_SMALL']
    expect((O['NP_ART_X'], O['NP_SHADOW_PAD']) == (mn.ART_X, mn.SHADOW_PAD) and S_ == mn.ART_SMALL == 212 and abs(S_ / A - 0.80) < 0.01, 'the paused cover is 212 px (0.80), the art and shadow constants are the asset\'s')
    sm = NowMachine()
    csz = lambda a, b, el: struct.unpack('<i', struct.pack('<I', sm.call(PSYMS['np_art_size'], a0=a, a1=b, a2=el & 0xffffffff, count=20000)))[0]
    pts = [(A, S_, t) for t in range(-10, O['NP_SHRINK_MS'] + 20, 7)] + [(S_, A, t) for t in range(-10, O['NP_GROW_MS'] + 20, 7)] + [(230, A, 55), (240, S_, 133), (A, S_, O['NP_SHRINK_MS']), (S_, A, O['NP_GROW_MS'])]
    got = [csz(*p) for p in pts]
    expect(got == [size_model(*p) for p in pts], f'np_art_size equals the model (spring tables from the formula, linear between entries) ({[(p, g, size_model(*p)) for p, g in zip(pts, got) if g != size_model(*p)][:3]})')
    down, up = [csz(A, S_, t) for t in range(0, O['NP_SHRINK_MS'] + 1, 5)], [csz(S_, A, t) for t in range(0, O['NP_GROW_MS'] + 1, 5)]
    expect(all(x >= y for x, y in zip(down, down[1:])) and min(down) == S_ and down[-1] == S_, 'the shrink is critically damped: it never goes under 212 px and lands there')
    expect(max(up) == A + 2 and up[-1] == A, f'the grow bounces subtly: 2 px past 264 ({max(up)}), 1 px on each side, then lands there')
    odd = [s for s in down + up if (A - s) % 2]
    expect(not odd, f'every size of a spring is an even number of px from the full cover: it stays centred, no edge moves alone ({sorted(set(odd))[:8]})')

    NPSHRINK = '/mnt/data/m1plus/nowplaying-shrink'
    def paused_page(status=3, lit=True, on=None):   # Shrink on Pause on (the default, no file) for the springs below
        m = NowMachine(); m.page(); m.widget('img_np_shadow'); m.widget('btn_play'); m.src(0); m.status = status; m.screen(lit)
        if on is not None: m.fs[NPSHRINK] = on
        m.init(); return m
    def geo(m, n): w = m.widgets[n]; return tuple(m.props.get((w, k)) for k in ('x', 'y', 'w', 'h'))
    pad = mn.SHADOW_PAD * S_ // A; small = mn.ART_X + (A - S_) // 2
    moved = lambda m: [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] in (m.widgets['img_playcover'], m.widgets['img_np_shadow'])]

    # Shrink on Pause off (0; on is the default, as is any other text): the cover stays full size, paused, stopped or playing, and no spring runs
    m = paused_page(on=b'1\n'); expect(moved(m) and geo(m, 'img_playcover') == (small, small, S_, S_), 'a file with 1: on, as without one')
    for f in (b'0\n',):
        for st in (3, 1):
            m = paused_page(status=st, on=f)
            expect(not moved(m) and m.timers == [(PSYMS['np_tick'], O['NP_TICK_MS'])], f'off ({f}): opened with status {st}, the asset\'s cover is left as it is')
        m = paused_page(status=2, on=f); m.status = 3; m.calls = []; m.tick()
        expect(not moved(m) and not any(c[0] == 'timer_add' and c[1] == PSYMS['np_art_frame'] for c in m.calls), f'off ({f}): a pause seen by the tick starts no spring')
        m.call(PSYMS['np_on_play'], a0=0, a1=0, count=100000); m.status = 2; m.calls = []; m.call(PSYMS['np_play_check'], count=400000)
        expect(not moved(m) and not any(c[0] == 'timer_add' and c[1] == PSYMS['np_art_frame'] for c in m.calls), f'off ({f}): play after the tap starts no spring either')
    # switched while the page is behind Settings: read again when it comes back, the cover put at its size at once
    m = paused_page(on=b'0\n'); m.fire(O['EVT_WINDOW_TO_BG']); m.fs[NPSHRINK] = b'1\n'; m.calls = []
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0, count=6000000)
    expect(geo(m, 'img_playcover') == (small, small, S_, S_) and not any(c[0] == 'timer_add' and c[1] == PSYMS['np_art_frame'] for c in m.calls), 'switched on while paused: back in front the cover is small at once, no spring')
    m.fire(O['EVT_WINDOW_TO_BG']); m.fs[NPSHRINK] = b'0\n'; m.calls = []
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0, count=6000000)
    expect(geo(m, 'img_playcover') == (mn.ART_X, mn.ART_Y, A, A) and not any(c[0] == 'timer_add' and c[1] == PSYMS['np_art_frame'] for c in m.calls), 'switched off: back in front it is full size at once')
    N = pod_pages.NPSET_PAGE
    expect(('Shrink on Pause', pod_pages.ACT_NPSHRINK) in [(r.label, r.action) for r in N.rows] and pod_pages.ACT_NPSHRINK in pod_pages.SWITCH_ACTIONS and 'nowplaying-shrink' in pod_pages.SETTING_FILES,
           'Settings > Now Playing has the Shrink on Pause switch, saved in nowplaying-shrink and listed on Settings Files')
    m = NowMachine(); m.page()
    expect(m.call(PSYMS['np_shrink_setting']) == 1 and m.call(PSYMS['np_shrink_toggle'], count=4000000) == 0 and m.fs[NPSHRINK] == b'0\n' and m.call(PSYMS['np_shrink_setting']) == 0
           and m.call(PSYMS['np_shrink_toggle'], count=4000000) == 1 and m.fs[NPSHRINK] == b'1\n', 'the switch: on by default; a toggle saves 0 atomically, then 1')

    m = paused_page()
    expect(geo(m, 'img_playcover') == (small, small, S_, S_) and geo(m, 'img_np_shadow') == (small - pad, small - pad, S_ + 2 * pad, S_ + 2 * pad),
           f'opened while paused: the cover and its shadow start small, centred where the full cover is ({geo(m, "img_playcover")}, {geo(m, "img_np_shadow")})')
    expect(m.timers == [(PSYMS['np_tick'], O['NP_TICK_MS'])], 'and without a spring (no frame timer)')
    op = [c[2] for c in m.calls if c[0] == 'widget_set_opacity' and c[1] == m.widgets['img_np_shadow']]
    expect(op[-1:] == [O['NP_SHADOW_DIM']] and O['NP_SHADOW_DIM'] < 160, f'and the shadow is lighter ({op})')
    m = paused_page(status=1)
    expect(geo(m, 'img_playcover') == (small, small, S_, S_), f'opened while stopped (Wi-Fi Transfer stops the player): the cover is small too ({geo(m, "img_playcover")})')
    m = paused_page(status=2); m.status = 1; m.calls = []; m.tick()
    expect(('timer_add', PSYMS['np_art_frame'], O['NP_FRAME_MS']) in m.calls, 'a stop seen by the tick shrinks the cover like a pause')
    m = paused_page(status=2)
    expect(not moved(m), 'opened while playing: the asset\'s cover is left as it is')
    clicks = [c for c in m.calls if c[0] == 'widget_on' and c[1] == m.widgets['btn_play'] and c[2] == O['EVT_CLICK']]
    expect(len(clicks) == 1 and clicks[0][3] == PSYMS['np_on_play'], 'the play button gets one click handler (the status check)')

    # a pause seen by the tick, page lit and in front: a spring of frames (time-based), landing on 212 px
    m.clock = 1000; m.status = 3; m.calls = []; m.tick()
    expect(('timer_add', PSYMS['np_art_frame'], O['NP_FRAME_MS']) in m.calls, 'a pause starts the spring\'s 16 ms frame timer')
    seen = []
    for t in (16, 48, 100, 150, 200, O['NP_SHRINK_MS'] - 1, O['NP_SHRINK_MS']):
        m.clock = 1000 + t; r = m.call(PSYMS['np_art_frame'], count=400000); seen.append((t, geo(m, 'img_playcover')[2], r))
    expect([s for _, s, _ in seen] == [size_model(A, S_, t) for t, _, _ in seen] and [r for *_, r in seen] == [O['RET_REPEAT']] * 6 + [0],
           f'each frame sizes the cover by the time run, and the spring ends on its last ({seen})')
    expect(geo(m, 'img_playcover') == (small, small, S_, S_), 'it lands centred, 212 px')
    m.calls = []; r = m.call(PSYMS['np_art_frame'], count=100000)
    expect(r == 0 and not any(c[0] == 'widget_resize' for c in m.calls), 'a late frame after the landing does nothing')

    # play mid-shrink: the spring turns round from where the cover is, bounces past 264 and lands there
    m = paused_page(status=2); m.clock = 5000; m.status = 3; m.tick()
    m.clock = 5150; m.call(PSYMS['np_art_frame'], count=400000); mid = geo(m, 'img_playcover')[2]
    m.status = 2; m.calls = []; m.tick()
    expect(not any(c[0] == 'timer_add' and c[1] == PSYMS['np_art_frame'] for c in m.calls), 'a turn mid-spring keeps the running frame timer')
    sizes = []
    for t in range(16, O['NP_GROW_MS'] + 1, 16):
        m.clock = 5150 + t; m.call(PSYMS['np_art_frame'], count=400000); sizes.append(geo(m, 'img_playcover')[2])
    m.clock = 5150 + O['NP_GROW_MS']; m.call(PSYMS['np_art_frame'], count=400000)
    expect(S_ < mid < A and sizes[0] == size_model(mid, A, 16) and max(sizes) > A and geo(m, 'img_playcover') == (mn.ART_X, mn.ART_Y, A, A)
           and m.props.get((m.widgets['img_np_shadow'], 'opacity')) == 255,
           f'from {mid} px it grows past 264 ({max(sizes)}) and lands on the asset\'s rectangle')

    # not seen (screen dark, another page in front, the lyrics or info page shown): the cover is just put at its size
    m = paused_page(status=2); m.screen(False); m.status = 3; m.calls = []; m.tick()
    expect(not any(c[0] == 'timer_add' for c in m.calls) and geo(m, 'img_playcover')[2] == S_, 'a pause with the screen dark: small at once, no spring')
    m = paused_page(status=2); sv = m.widget('slide_view'); m.props[(sv, 'value')] = 1
    m.init(); m.status = 3; m.calls = []; m.tick()
    expect(not any(c[0] == 'timer_add' for c in m.calls) and geo(m, 'img_playcover')[2] == S_, 'a pause while the lyrics page shows: small at once, no spring')
    m = paused_page(status=2); m.timer_fail = True; m.status = 3; m.tick()
    expect(geo(m, 'img_playcover')[2] == S_, 'no frame timer: the cover is put small at once')

    # a spring that stops being seen mid-flight lands at once: the next frame (screen off, lyrics page, page in the background) or the tick (screen off)
    def mid_spring():
        m = paused_page(status=2); sv = m.widget('slide_view'); m.init(); m.clock = 7000; m.status = 3; m.tick()
        m.clock = 7100; m.call(PSYMS['np_art_frame'], count=400000)
        return m, sv
    for how in ('screen', 'lyrics', 'background'):
        m, sv = mid_spring(); before = geo(m, 'img_playcover')[2]
        if how == 'screen': m.screen(False)
        elif how == 'lyrics': m.props[(sv, 'value')] = 1
        else: m.fire(O['EVT_WINDOW_TO_BG'])
        m.clock = 7150; r = m.call(PSYMS['np_art_frame'], count=400000)
        m.clock = 7200; m.calls = []; r2 = m.call(PSYMS['np_art_frame'], count=100000)
        expect(S_ < before < A and r == 0 and geo(m, 'img_playcover') == (small, small, S_, S_) and r2 == 0 and not m.calls,
               f'{how} mid-spring: the next frame lands it small and ends the timer, later frames do nothing ({before})')
    m, sv = mid_spring(); m.screen(False); m.calls = []; m.tick()
    expect(('timer_remove', 0x777) in m.calls and geo(m, 'img_playcover')[2] == S_, 'the tick with the screen off removes the frame timer and lands the cover')
    expect([mn.shadow_opacity(s) for s in (S_ - 5, S_, S_ + 17, A, A + 2)] == [O['NP_SHADOW_DIM']] * 2 + [O['NP_SHADOW_DIM'] + (255 - O['NP_SHADOW_DIM']) * 17 // (A - S_), 255, 255]
           and mn.SHADOW_DIM == O['NP_SHADOW_DIM'], 'the shadow opacity model (preview) is the payload\'s formula and constant')

    # the play button: stock's handler runs after ours, so the status is watched every 50 ms (at most 10 times) and the cover follows its change
    m = paused_page(status=2); m.clock = 9000; m.calls = []
    m.call(PSYMS['np_on_play'], a0=0, a1=0, count=100000)
    expect(('timer_add', PSYMS['np_play_check'], O['NP_PLAY_MS']) in m.calls, 'a tap starts the 50 ms status check')
    r1 = m.call(PSYMS['np_play_check'], count=100000)
    m.status = 3; m.calls = []; r2 = m.call(PSYMS['np_play_check'], count=400000)
    expect(r1 == O['RET_REPEAT'] and r2 == 0 and ('timer_add', PSYMS['np_art_frame'], O['NP_FRAME_MS']) in m.calls, 'unchanged it checks again; paused, the spring starts and the check ends')
    m = paused_page(status=2); m.call(PSYMS['np_on_play'], a0=0, a1=0, count=100000)
    rs = [m.call(PSYMS['np_play_check'], count=100000) for _ in range(O['NP_PLAY_CHECKS'])]
    expect(rs == [O['RET_REPEAT']] * (O['NP_PLAY_CHECKS'] - 1) + [0] and geo(m, 'img_playcover')[2] is None, 'no change in ten checks: it stops, the cover stays (the tick watches on)')

    # the corners of the small cover: radius 10 (12 scaled), the window's colour under the gradient at the small cover's rows
    m = paused_page(); ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], 0x7000a000)
    m.fills = []; m.call(PSYMS['np_on_art_paint'], a0=0, a1=ev, count=2000000)
    R = (mn.ART_R * S_ + A // 2) // A; cv = mn.corner_alpha(R); t = mn.NP_NEUTRAL; want = {}
    for k in range(4):
        for y in range(R):
            ly = S_ - 1 - y if k & 2 else y
            keep = 255 - mn.tint_alpha(small + ly)
            shade = (t[0] * keep // 255) | (t[1] * keep // 255) << 8 | (t[2] * keep // 255) << 16
            for x in range(R):
                if cv[y * R + x]: want[(S_ - 1 - x if k & 1 else x, ly)] = shade | cv[y * R + x] << 24
    got = {(f[1], f[2]): f[0] for f in m.fills if (f[3], f[4]) == (1, 1)}
    expect(R == 10 and got == want and len(m.fills) == len(want), f'the small cover\'s corners: radius {R}, at its own edges and rows ({len(m.fills)} pixels)')

    # the page goes mid-spring: both timers go with it
    m = paused_page(status=2); m.status = 3; m.tick(); m.call(PSYMS['np_on_play'], a0=0, a1=0, count=100000); m.calls = []
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(sum(c[0] == 'timer_remove' for c in m.calls) == 3, 'destroy removes the page timer, the frame timer and the status check')
    m.calls = []; r = m.call(PSYMS['np_art_frame'], count=100000); r2 = m.call(PSYMS['np_play_check'], count=100000)
    expect(r == 0 and r2 == 0 and not m.calls, 'a late frame or check after the page is gone does nothing')

    # ---- the info page's edge fades: 16 rows at the top (content scrolled) and the bottom (more under the view), painted in the window's tone under the scrim and the gradient, alpha ramping to the edge
    def fades(m):
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x7000a000)
        m.fills = []; m.call(PSYMS['np_on_info_fade'], a0=0, a1=e, count=2000000)
        return {f[2]: f for f in m.fills}, len(m.fills)
    def want_fades(rgb, off, ih):
        vh = 252; out = {}
        for y in mn.fade_rows(off, ih):
            k = min(y, vh - 1 - y); out[y] = (mn.fade_color(rgb, y) | mn.fade_alpha(k) << 24, 0, y, 320, 1)
        return out
    for tint_rgb, name in (((0x20, 0x20, 0x20), 'the neutral tone'), (mn.tone(*avg), 'a cover\'s tone')):
        m = NowMachine(); m.page(); m.src(0 if name[4] == 'n' else 2)
        if name[4] != 'n': m.jpeg(P2, pix=half, size=(4, 4))
        m.info_page(stock_en); m.play([m.record(**REC)], 0); m.init()
        for _ in range(mn.I_RELAY): m.tick()
        ih = vhigh(m); top = ih - 252
        for off in (0, 1, 40, top - 1, top):
            m.call(PSYMS['np_info_scroll'], a0=off); got, n = fades(m)
            exp_ = want_fades(tint_rgb, off, ih)
            expect({y: f[:5] for y, f in got.items()} == exp_ and n == len(exp_), f'{name}, offset {off} of {top}: {sorted(got)[:1]}.. {n} fade rows ({"top" if off else ""}{" and " if off and off < top else ""}{"bottom" if off < top else ""}), colour and alpha as the model')
        m.call(PSYMS['np_info_scroll'], a0=0); got, n = fades(m)
        expect(sorted(got) == list(range(236, 252)) and all(got[236 + k][0] >> 24 == mn.fade_alpha(15 - k) for k in range(16)) and mn.fade_alpha(0) >= 240 and mn.fade_alpha(15) <= 16 and
               all(mn.fade_alpha(k) > mn.fade_alpha(k + 1) for k in range(15)), 'at the top only the bottom 16 rows fade, strongest at the edge, ramping to nothing')
        m.call(PSYMS['np_info_scroll'], a0=top)
        expect(sorted(fades(m)[0]) == list(range(16)), 'at the end only the top 16 rows')
        expect(fades(m)[0][0][0] & 0xffffff == mn.fade_color(tint_rgb, 0), 'the fade is the page colour at that row')
    m = info({'label_info': 'FLAC|44.1kHz|16bit|950kbps'}, rec=REC)
    expect(fades(m) == ({}, 0), 'content that fits has no fades')
    m = info(stock_en, rec=REC); m.fills = []; m.call(PSYMS['np_on_info_fade'], a0=0, a1=0, count=100000)
    expect(not m.fills, 'no event, no canvas: nothing')
    expect(all(mn.fade_color((255, 255, 255), y) >> 8 & 255 > 0 for y in (0, 251)) and mn.fade_color((192, 192, 192), 0) != mn.fade_color((192, 192, 192), 251), 'the model: the colour follows the scrim and the gradient row by row')

    # ------------------------------------------------------------------ the built assets
    ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
    f = ui.find
    rect = lambda n: (f(n).x, f(n).y, f(n).w, f(n).h)
    expect(rect('img_playcover') == (28, 28, 264, 264) and mn.ART == mod_lockscreen.COVER_SIZE == 264, 'the cover is 264 px at 28, 28: the size demo writes, so it is drawn 1:1')
    lines = [rect(n) for n in ('label_info', 'label_album', 'label_genre', 'label_year', 'label_size', 'label_location')]
    expect(all(r[0] >= 0 and r[0] + r[2] <= 320 for r in lines) and lines[0][:3] == (16, 120 - 36 - 2, 288) and [r[1] + 36 + 2 for r in lines[2:]] == [112 + 33 * k + 8 for k in (4, 5, 6, 7)]
           and f('label_info').get('style:normal:text_color') == mn.TITLE_RGB and f('label_album').get('style:normal:text_color') == mn.GREY,
           f'the info page: stock\'s six labels stay where their rows are (the data source, and what shows without the payload) ({lines})')
    sc = f('np_i_scroll'); vi = f('view_info')
    expect(sc.type == 'scroll_view' and (sc.x, sc.y, sc.w, sc.h) == (0, 36, 320, 252) and sc.get('floating') == 'false' and sc.get('sensitive') != 'false' and not sc.get('xslidable') and not sc.get('yslidable') and vi.children[1:] == [sc] and vi.children[0].name == 'img_np_scrim_info',
           'every widget of the info page is in one scroll_view over the text area, y 36..288 (not slidable, takes the touches); the scrim stays outside')
    expect(all(n in [c.name for c in sc.children] for n in ('label_info', 'label_album', 'label_genre', 'label_year', 'label_size', 'label_location')), 'stock\'s six labels are in it too')
    own = [w for w in sc.walk() if w.name and w.name.startswith('np_i_') and w.name != 'np_i_scroll']
    expect(len(own) == 32 and all(w.get('sensitive') == 'false' for w in own) and all(w.get('visible') == 'false' for w in own if w.name != 'np_i_art' and not w.name.startswith('np_i_h')),
           f'the information page has its own widgets (cover, title with its second line, artist, album, two badges, eight labels and nine values, eight hairlines): {len(own)}; insensitive, the payload shows them')
    hairs = [w for w in own if w.name.startswith('np_i_h')]
    expect(rect('np_i_art') == (16, 0, 64, 64) and [w.y + 36 for w in hairs] == [112 + 33 * r for r in range(8)] and all(w.get('style:normal:bg_color') == mn.HAIR and (w.x, w.w, w.h) == (16, 288, 1) for w in hairs)
           and min(w.x for w in own) >= 16 and max(w.x + w.w for w in own) <= 304,
           'cover 64 px at (16, 36); hairlines at 112 and every 33 px, 15 % white from 16 to 304; everything inside the column')
    expect(all(w.get('style:normal:font_size') == str(px) for w, px in [(f(n), 20 if n == 'np_i_title' else 16) for n in ('np_i_title', 'np_i_artist', 'np_i_album', 'np_i_v0', 'np_i_k3', 'np_i_v7', 'np_i_v8')])
           and f('np_i_title').get('style:normal:text_color') == '#FFFFFF' and f('np_i_artist').get('style:normal:text_color') == mn.GREY and f('np_i_k0').get('style:normal:text_color') == mn.GREY
           and f('np_i_v2').get('style:normal:text_align_h') == 'right' and f('np_i_v7').get('style:normal:text_align_h') == 'left' and f('np_i_v8').get('style:normal:text_align_h') == 'left'
           and f('np_i_v7').get('style:normal:text_color') == '#FFFFFF' and all(w.type == 'label' for w in own if w.name.startswith(('np_i_title', 'np_i_artist', 'np_i_album', 'np_i_k', 'np_i_v'))), 'plain labels (an hscroll_label clips to its resting place: its text was cut while the page slid); sizes and colours: title 20 px white, artist and album 16 px #AAAAAA, labels grey, values white and right aligned, the path lines left aligned')
    for text in ('HI-RES', 'DSD'):
        name = 'np_i_badge_' + ('hires' if text == 'HI-RES' else 'dsd')
        from PIL import Image as _I
        im = _I.open(os.path.join(raw, 'images', 'xx', name + '.png')).convert('RGBA'); px = im.load(); gold = tuple(int(mn.GOLD[k:k + 2], 16) for k in (1, 3, 5))
        edge = [px[x, y] for x in range(im.width) for y in range(im.height) if (x in (0, im.width - 1) or y in (0, im.height - 1)) and px[x, y][3] > 200]
        inner = px[im.width // 2, 2]
        expect(im.size == (mn.I_BADGE_W[text], 18) and edge and all(p[:3] == gold for p in edge) and inner[3] == 0 and px[0, 0][3] < 80,
               f'{name}: {im.size}, a 1 px gold outline with rounded corners and no fill')
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
    expect(rect('img_hr')[2:] == (0, 0) and f('img_hr').get('visible') == 'false' and f('img_hr').get('sensitive') == 'false', 'img_hr is kept, hidden and insensitive at 0x0')
    expect(rect('label_index') == (28 + mn.TIMES_W, mn.TIMES_Y, 320 - 2 * (28 + mn.TIMES_W), mn.TIMES_H) and f('label_index').get('visible') == 'false' and f('label_index').get('sensitive') == 'false'
           and all(f('label_index').get(f'style:{s}:font_size') == '14' and f('label_index').get(f'style:{s}:text_align_h') == 'center' for s in ('normal', 'disable', 'focused')),
           'label_index (the track position) is centred between the two times, 14 px, invisible and insensitive until the payload shows it')
    expect(f('label_album') in f('np_i_scroll').children and 'label_album' not in [c.name for c in f('view').children], 'the album line is on the info page, not under the art')
    expect(f('label_info') in f('np_i_scroll').children, 'the quality line is on the info page, not between the times')
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
           and sh.get('sensitive') == 'false' and sh.get('image') == 'np_shadow' and sh.get('draw_type') == 'scale',
           f'the shadow follows the cover on page 1 (slides with it), before the title, insensitive, drawn scaled to its box (it shrinks with the paused cover) ({kids})')
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
    sp = {}
    for s in th.items:
        if s.widget == 'button' and s.style.startswith('btn_imgspeed'): sp.setdefault(s.style, {})[s.state] = s.get('icon')
    expect(sp == {f'btn_imgspeed{i}_style': {st: f'np_speed{i}' for st in ('normal', 'pressed', 'over', 'disable', 'focused')} for i in range(O['PC_SPEEDS'])} and mn.SPEED_STYLES == O['PC_SPEEDS']
           and all(asset_image(f'np_speed{i}').size == (52, 30) and asset_image(f'np_speed{i}').getchannel('A').getbbox() is not None for i in range(O['PC_SPEEDS'])),
           f'the speed button\'s styles, one per speed, have their 52 x 30 text image in every state ({sp})')
    expect(asset_image('np_playlist').size == asset_image('np_playlist_down').size == asset_image('np_playqueue').size and asset_image('np_playlist').tobytes() != asset_image('np_playqueue').tobytes(),
           'the plain list glyph of an episode\'s queue button is the size of the music queue glyph')
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

    # a server track's star is the server's favourite: the button shows nd_row's flag, a click goes to ls_favorite (lib_nd, the row sheet's Favorite) and RET_STOP keeps stock's handler away
    # (it would write the stream record, whose address carries the login, into the local myfav table); a downloaded server track too; a local track is stock's
    def sv_machine(path, style, rid=-5, starred=0):
        mm = NowMachine(); mm.page(); mm.src(0); fav = mm.widget('btn_fav')
        mm.setword(fav + O['WIDGET_STYLE'], mm.cstr(style)); mm.props[(fav, 'style')] = style
        mm.sbtrack[rid] = 't5'; mm.sbfav[rid] = starred
        mm.play([mm.record(path=path, rid=rid)], 0); mm.init()
        return mm, fav
    stream, local_dl = 'http://nd.example:4533/rest/stream.view?id=t5&t=tok&s=salt', '/mnt/mmc/Subsonic/Song 5.flac'
    for path in (stream, local_dl):
        kind = 'streamed' if path == stream else 'downloaded'
        mm, fav = sv_machine(path, 'btn_imgunfav_style', starred=1)
        expect([c for c in mm.calls if c[0] == 'widget_use_style'] == [('widget_use_style', fav, 'btn_imgfav_style')] and mm.props[(fav, 'style:pressed:icon')] == 'np_unfav_down',
               f'a {kind} server track starred on the server: the button shows the filled star though stock\'s myfav has none ({[c for c in mm.calls if c[0] == "widget_use_style"]})')
        mm.setword(fav + O['WIDGET_STYLE'], mm.cstr('btn_imgfav_style')); mm.calls = []; mm.tick()
        expect(not [c for c in mm.calls if c[0] in ('widget_use_style', 'nd_row')], 'and a tick with the same track and cache asks nothing again')
        mm.sbfav[-5] = 0; mm.sbgen += 1; mm.calls = []; mm.tick()
        expect([c for c in mm.calls if c[0] == 'widget_use_style'] == [('widget_use_style', fav, 'btn_imgunfav_style')], 'the cache moved (sba_gen): the outline star is back (an un-star elsewhere, or a refused star)')
        mm.setword(fav + O['WIDGET_STYLE'], mm.cstr('btn_imgunfav_style')); mm.calls = []
        r = mm.call(PSYMS['np_on_fav'], a0=0, a1=0)
        expect(r == O['RET_STOP'] and [c for c in mm.calls if c[0] == 'ls_favorite'] == [('ls_favorite', True, -5, 0)], f'a click: ls_favorite(lib_nd, the record, was 0) and RET_STOP, so stock\'s star never sees the record ({r}, {mm.calls})')
        expect(mm.sbfav[-5] == 1 and [c for c in mm.calls if c[0] == 'widget_use_style'] == [('widget_use_style', fav, 'btn_imgfav_style')], 'the star is filled at once, with no wait for a tick')
        mm.calls = []
        r = mm.call(PSYMS['np_on_fav'], a0=0, a1=0)
        expect(r == O['RET_STOP'] and [c for c in mm.calls if c[0] == 'ls_favorite'] == [('ls_favorite', True, -5, 1)] and mm.sbfav[-5] == 0, 'the next click un-stars (was 1)')
    mm, fav = sv_machine('/mnt/mmc/Music/a.flac', 'btn_imgunfav_style', rid=7)
    mm.sbtrack.clear(); mm.calls = []
    r = mm.call(PSYMS['np_on_fav'], a0=0, a1=0)
    expect(r == O['RET_OK'] and not [c for c in mm.calls if c[0] in ('ls_favorite', 'nd_row')], 'a local track: the click is stock\'s (RET_OK), the source is never asked')

    # ------------------------------------------------------------------ a server track's cover is the big art (stock draws /tmp/coverpic.jpg, never written for a stream)
    SB = '/mnt/mmc/.m1plus/subsonic/covers/0123abcd-168.jpg'
    def sb_machine():
        m = NowMachine(); m.page(); m.src(0)
        m.play([m.record(album='Srv', artist='A', path='nd://t1', rid=-5)], 0); m.sbcov = {-5: None}
        m.init()
        m.ev = m.alloc(0x40); m.u.mem_write(m.ev, bytes(0x40)); m.setword(m.ev + O['EVENT_PAINT_CANVAS'], 0x7000a000)
        return m
    def art_paint(m):
        m.blits = []; m.call(PSYMS['np_on_art_paint'], a0=0, a1=m.ev, count=2000000)
        return [b for b in m.blits if b[1] == (0, 0, 264, 264)]
    m = sb_machine()
    expect(not [c for c in m.calls if c[0] == 'bitmap_create_ex'] and not art_paint(m), 'a server track whose cover is not cached yet: nothing of ours is drawn (stock\'s picture)')
    m.jpeg(SB, size=(4, 4)); m.sbcov[-5] = SB; m.calls = []; m.tick()
    expect(('bitmap_create_ex', 264, 264) in m.calls and ('widget_load_image', 'file://' + SB) in m.calls and ('widget_invalidate_force', m.widgets['img_playcover']) in m.calls,
           'the cover lands: it is decoded into a 264 px bitmap and the art is redrawn')
    expect(len(art_paint(m)) == 1, 'and drawn over the art widget')
    m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex')], 'an unchanged cover is not decoded again')
    m.play([m.record(album='Local', artist='A', path='/mnt/mmc/a/1.flac', rid=1)], 0); m.calls = []
    expect(not art_paint(m), 'a local track replaces it: the stale picture is not drawn even before the tick')
    m.tick()
    expect(('widget_invalidate_force', m.widgets['img_playcover']) in m.calls and not art_paint(m), 'a local track: the art is stock\'s again')
    m.play([m.record(album='Srv', artist='A', path='nd://t1', rid=-5)], 0); m.tick()
    expect(len(art_paint(m)) == 1, 'back on the server track: its cover is drawn again')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(any(c[0] == 'bitmap_destroy' for c in m.calls), 'the page\'s end frees the bitmap')

    # a track change keeps the previous server cover up (no stock placeholder in between) and decodes the new one at once
    SB2 = '/mnt/mmc/.m1plus/subsonic/covers/4567ef01-168.jpg'
    def once_timers(m): return [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['np_art_once']]
    recs = lambda m: [m.record(album='Srv', artist='A', path=f'nd://t{i}', rid=-5 - i) for i in range(4)] + [m.record(album='Local', artist='A', path='/mnt/mmc/a/1.flac', rid=1)]
    m = NowMachine(); m.page(); m.src(0); m.jpeg(SB, size=(4, 4)); m.jpeg(SB2, size=(4, 4), data=b'other-cover' * 40)
    m.sbcov = {-5: SB, -6: None, -7: None, -8: SB2}
    q = recs(m); m.play(q, 0); m.init()
    m.ev = m.alloc(0x40); m.u.mem_write(m.ev, bytes(0x40)); m.setword(m.ev + O['EVENT_PAINT_CANVAS'], 0x7000a000)
    expect(len(art_paint(m)) == 1 and not once_timers(m), 'the first track: drawn, no one-shot')
    m.play(q, 1); m.calls = []
    expect(len(art_paint(m)) == 1, 'the next track has no cover yet: the previous cover is still drawn, not stock\'s picture')
    expect(once_timers(m) == [('timer_add', PSYMS['np_art_once'], 30)] and m.timer_arg[PSYMS['np_art_once']] == 0, 'and the paint asks for one 30 ms one-shot (ctx 0)')
    m.play(q, 3); m.sbcov[-8] = SB2; m.calls = []
    expect(len(art_paint(m)) == 1, 'a track with a different cover: the previous one until it is decoded')
    m.call(PSYMS['np_art_once'], a0=0)
    expect(('widget_load_image', 'file://' + SB2) in m.calls and ('widget_invalidate_force', m.widgets['img_playcover']) in m.calls and len(art_paint(m)) == 1,
           'the one-shot decodes the new cover with no tick and redraws the art')
    m.calls = []; art_paint(m)
    expect(not once_timers(m), 'decoded: the paint asks for nothing more')
    m.play(q, 4); m.calls = []
    expect(not art_paint(m) and not once_timers(m), 'a local track: ours is not drawn at once, and no one-shot')
    m.tick()
    expect(('widget_invalidate_force', m.widgets['img_playcover']) in m.calls and not art_paint(m), 'a local track: the tick drops ours')
    # no cover for the new server track at all (or it never arrives): the previous cover waits NP_SB_WAIT ticks, then stock's picture
    m.play(q, 0); m.tick(); expect(len(art_paint(m)) == 1, 'back on a cached track')
    m.play(q, 1)
    for i in range(10): m.tick()
    expect(len(art_paint(m)) == 1, 'ten ticks without a cover: still the previous one')
    m.tick(); expect(not art_paint(m), 'the eleventh: stock\'s picture')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    m.calls = []; m.call(PSYMS['np_art_once'], a0=0)
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'sba_now_cover')], 'a one-shot after the page is gone does nothing')

    # an audiobook part stock has no picture of shows its book's cover (np_cover_file, the big art, the tone); stock's picture, when there is one, wins
    BK = '/mnt/mmc/Audiobooks/Book One/01.mp3'; BKF = '/mnt/mmc/.m1plus/covers/book-168.jpg'
    def bk_machine(src, path=BK, cover=BKF, **kw):
        m = NowMachine(); m.page(); m.src(src)
        if cover: m.bkcov[path] = cover; m.jpeg(cover, size=(4, 4), pix=bytes([20, 200, 20, 255]) * 16)
        m.jpeg('/tmp/coverpic.jpg', data=b'stock cover' * 40, pix=bytes([200, 40, 40, 255]) * 16, size=(4, 4))
        m.play([m.record(album='Book One', artist='N', path=path, rid=3)], 0); m.init()
        m.ev = m.alloc(0x40); m.u.mem_write(m.ev, bytes(0x40)); m.setword(m.ev + O['EVENT_PAINT_CANVAS'], 0x7000a000)
        return m
    m = bk_machine(0)
    expect(('widget_load_image', 'file://' + BKF) in m.calls and ('bitmap_create_ex', 264, 264) in m.calls and len(art_paint(m)) == 1, 'a book part with no stock picture: the book\'s cover is the big art, drawn over stock\'s')
    expect(m.styles and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)), 'and its colour is the tone of that cover')
    m.calls = []; [m.tick() for _ in range(5)]
    expect(not [c for c in m.calls if c[0] in ('bk_art_cover', 'widget_load_image', 'bitmap_create_ex')], 'later ticks: the book is asked for once, the cover decoded once')
    m.calls = []; art_paint(m)
    expect(not [c for c in m.calls if c[0] == 'bk_art_cover'], 'and the paint asks for nothing')
    m.play([m.record(album='Local', artist='A', path='/mnt/mmc/a/1.flac', rid=1)], 0); m.tick()
    expect(not art_paint(m), 'a local track that is not a part: stock\'s picture again')
    m.src(2); m.play([m.record(album='Book One', artist='N', path=BK, rid=3)], 0); m.tick()
    expect(not art_paint(m), 'the part with an embedded picture of its own: stock\'s (the part\'s) art, no overlay')
    m = bk_machine(2)
    expect(not [c for c in m.calls if c[0] == 'bk_art_cover'] and not art_paint(m) and 'file:///tmp/coverpic.jpg' in m.loads and 'file://' + BKF not in m.loads, 'a part whose stock source is embedded keeps /tmp/coverpic.jpg (the book is not asked)')
    m = bk_machine(0, cover=None)
    expect(not art_paint(m) and m.styles[-1][2] == O['NP_NEUTRAL'], 'a book with no cover at all: as before, no art of ours, the neutral tone')
    m = bk_machine(0, path='/mnt/mmc/a/1.flac')
    expect(not [c for c in m.calls if c[0] == 'bk_art_cover'] and not art_paint(m), 'a track that is not a part: the book is never asked, nothing drawn')
    # the play mode button is the speed button while an episode or an audiobook part plays: it wears the page theme's btn_imgspeed<playspeed_mode>_style, a tap saves and applies the next
    # speed and restarts a playing or paused player at its place (stock's Multiple Speed sequence), and RET_STOP keeps stock's play mode handler away; music is stock's
    PSM, EPM, MUS = pod.DATA['PLAYSPEED_MODE'][0], '/mnt/mmc/Podcasts/Show/e1.mp3', '/mnt/mmc/a/1.flac'
    def mode_machine(path, speed=0, status=2):
        mm = NowMachine(); btn = mm.widget('btn_playmode'); mm.page(); mm.src(0); mm.setword(PSM, speed); mm.speed_saved = speed; mm.status = mm.save_status = status   # the show's saved speed: pc_note applies it when the track starts
        mm.jpeg('/tmp/coverpic.jpg', data=b'stock cover' * 40, pix=bytes([200, 40, 40, 255]) * 16, size=(4, 4))
        mm.play([mm.record(album='Book One', artist='N', path=path, rid=3)], 0); mm.init()
        return mm, btn
    def mode_styles(mm, btn): return [c[2] for c in mm.calls if c[0] == 'widget_use_style' and c[1] == btn]
    def mode_tap(mm):
        mm.calls = []; r = mm.call(PSYMS['np_on_mode'], a0=0, a1=0)
        return r, [c for c in mm.calls if c[0] in ('pc_speed_set', 'pc_speed_apply', 'save_stop_player', 'save_start_player', 'pod_toast')]
    for what, path in (('an episode', EPM), ('a book part', BK)):
        for speed in range(O['PC_SPEEDS']):
            mm, btn = mode_machine(path, speed)
            expect(mode_styles(mm, btn) == [f'btn_imgspeed{speed}_style'] and not [c for c in mm.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == btn],
                   f'{what} at speed {speed}: the button wears that speed\'s style and stays shown ({mode_styles(mm, btn)})')
        binds = [c[1:] for c in mm.calls if c[0] == 'widget_on' and c[1] == btn]
        expect(binds == [(btn, O['EVT_CLICK'], PSYMS['np_on_mode'], 0)], f'{what}: one click handler on the button, after stock\'s ({binds})')
        mm.calls = []; mm.tick(); mm.tick()
        expect(not mode_styles(mm, btn), f'{what}: later ticks set no style again')
        mm.setword(btn + O['WIDGET_STYLE'], mm.cstr('btn_imgrandom_style')); mm.calls = []; mm.tick()
        expect(mode_styles(mm, btn) == ['btn_imgspeed3_style'], f'{what}: a play mode style stock put on the button is the speed again at the next tick')
        r, did = mode_tap(mm)
        expect(r == O['RET_STOP'] and did == [('pc_speed_set', True, 0), ('pc_speed_apply', True), ('save_stop_player',), ('save_start_player', 0)] and mode_styles(mm, btn) == ['btn_imgspeed0_style'],
               f'{what}, a tap at 2x while playing: 1x saved and applied, the player restarted playing, the style follows at once, RET_STOP ({r}, {did})')
    mm, btn = mode_machine(EPM, 0, status=3)
    r, did = mode_tap(mm)
    expect(r == O['RET_STOP'] and did[1:] == [('pc_speed_apply', True), ('save_stop_player',), ('save_start_player', 1)] and did[0] == ('pc_speed_set', True, 1), f'a tap while paused: the player is restarted paused ({did})')
    mm, btn = mode_machine(EPM, 1, status=1)
    r, did = mode_tap(mm)
    expect(r == O['RET_STOP'] and did == [('pc_speed_set', True, 2), ('pc_speed_apply', True)] and mode_styles(mm, btn) == ['btn_imgspeed2_style'], f'a tap while stopped: saved and applied, no restart ({did})')
    mm, btn = mode_machine(EPM, 1); mm.speed_ok = 0
    r, did = mode_tap(mm)
    expect(r == O['RET_STOP'] and did == [('pc_speed_set', True, 2), ('pod_toast', 'Storage unavailable')] and not mode_styles(mm, btn) and mm.word(PSM) == 1, f'the card refuses the speed: a toast, nothing applied or restarted ({did})')
    mm, btn = mode_machine(EPM, 7)
    expect(mode_styles(mm, btn) == ['btn_imgspeed0_style'] and mode_tap(mm)[1][0] == ('pc_speed_set', True, 1), 'a playspeed_mode out of range reads as 1x')
    mm, btn = mode_machine(MUS, 2)
    r, did = mode_tap(mm)
    expect(not mode_styles(mm, btn) and (r, did) == (O['RET_OK'], []) and not [c for c in mm.calls if c[0] == 'np_mode_button'], f'music: the play mode button is stock\'s, never touched, and a tap is stock\'s ({r}, {did})')
    mm, btn = mode_machine(EPM, 2)
    mm.play([mm.record(album='Local', artist='A', path=MUS, rid=1)], 0); mm.tick()
    back = [c for c in mm.calls if c[0] in ('np_mode_button', 'widget_use_style')]; mm.tick(); again = [c for c in mm.calls if c[0] in ('np_mode_button', 'widget_use_style')]
    expect(back == [('np_mode_button', WIN)] and not again and mode_tap(mm) == (O['RET_OK'], []),
           f'music after the episode: stock puts the play mode\'s picture back, once, and a tap is stock\'s again ({back})')
    # an episode's or a book part's prev / next buttons skip back NP_SKIP_BACK and forward NP_SKIP_FWD seconds: the tick swaps the five states' images, the click handler (bound after the
    # stock init, so it runs first) seeks and keeps stock's handler away with RET_STOP; music keeps stock's buttons
    EP1, MUSIC1 = '/mnt/mmc/Podcasts/Show/e1.mp3', '/mnt/mmc/a/1.flac'
    def skip_machine(path, pt=(100, 600, 1)):
        mm = NowMachine(); mm.page(); mm.src(0); pv, nx = mm.widget('btn_prev'), mm.widget('btn_next'); mm.widget('btn_queue')
        mm.pt = pt; mm.play([mm.record(path=path)], 0); mm.init()
        return mm, pv, nx
    def skip_look(mm, btn): return [mm.props.get((btn, f'style:{s}:bg_image')) for s in ('normal', 'disable', 'focused', 'over', 'pressed')]
    def skip_tap(mm, fwd):
        mm.calls = []; r = mm.call(PSYMS['np_on_skip'], a0=fwd, a1=0)
        return r, [c[1] for c in mm.calls if c[0] == 'seek_time']
    STOP, OK = O['RET_STOP'], O['RET_OK']
    for what, path in (('an episode', EP1), ('a book part', BK)):
        mm, pv, nx = skip_machine(path)
        expect(skip_look(mm, pv) == ['np_back15'] * 4 + ['np_back15_down'] and skip_look(mm, nx) == ['np_fwd30'] * 4 + ['np_fwd30_down'],
               f'{what}: prev and next wear the skip glyphs in every state ({skip_look(mm, pv)}, {skip_look(mm, nx)})')
        expect(skip_look(mm, mm.widgets['btn_queue']) == ['np_playlist'] * 4 + ['np_playlist_down'], f'{what}: the queue button is the plain list in every state')
        ons = [c for c in mm.calls if c[0] == 'widget_on' and c[1] in (pv, nx)]
        expect(sorted(c[1:] for c in ons) == sorted([(pv, O['EVT_CLICK'], PSYMS['np_on_skip'], 0), (nx, O['EVT_CLICK'], PSYMS['np_on_skip'], 1)]), f'{what}: one click handler on each button, after stock\'s ({ons})')
        expect(skip_tap(mm, 0) == (STOP, [85]) and skip_tap(mm, 1) == (STOP, [115]), f'{what} at 100 s: back seeks to 85, then forward to 115, both RET_STOP (stock changes no track)')
        mm.calls = []; mm.tick(); mm.tick()
        expect(not [c for c in mm.calls if c[0] == 'widget_set_prop_str' and c[1] in (pv, nx)], f'{what}: later ticks set no image again')
    for pt, fwd, want, why in (((10, 600, 1), 0, [0], 'back in the first seconds goes to the start'), ((0, 600, 1), 0, [0], 'back at the start seeks to 0'),
                               ((580, 600, 1), 1, [595], 'forward near the end stops NP_SKIP_END before it'), ((596, 600, 1), 1, [], 'forward in the last seconds does nothing'),
                               ((100, 0, 1), 1, [], 'no length yet: no seek'), ((100, 600, 0), 0, [], 'the player gives no time: no seek')):
        mm, pv, nx = skip_machine(EP1, pt)
        expect(skip_tap(mm, fwd) == (STOP, want), f'an episode at {pt}: {why}, RET_STOP')
    mm, pv, nx = skip_machine(MUSIC1)
    expect(skip_look(mm, pv) == [None] * 5 and skip_look(mm, nx) == [None] * 5 and skip_tap(mm, 0) == (OK, []) and skip_tap(mm, 1) == (OK, []), 'music: the buttons are never touched and a tap is stock\'s (RET_OK, no seek)')
    mm, pv, nx = skip_machine(EP1)
    mm.play([mm.record(path=MUSIC1)], 0); mm.tick()
    expect(skip_look(mm, pv) == ['np_prev'] * 4 + ['np_prev_down'] and skip_look(mm, nx) == ['np_next'] * 4 + ['np_next_down'] and skip_tap(mm, 1) == (OK, [])
           and skip_look(mm, mm.widgets['btn_queue']) == ['np_playqueue'] * 4 + ['np_playqueue_down'], 'music after the episode: the transport and queue glyphs are back and a tap is stock\'s')
    mm = NowMachine(); mm.page(); mm.src(0); mm.widget('btn_prev'); mm.play([mm.record(path=EP1)], 0); mm.init()
    expect(not [c for c in mm.calls if c[0] == 'widget_set_prop_str' and 'bg_image' in str(c)] and skip_tap(mm, 0) == (OK, []), 'a page without both buttons: no glyph, no handler of ours acts')
    # an episode or a book part shows the cover page alone: the slide view is turned to it, takes no touch (no swipe to lyrics or info), and the page dots are hidden; music gets both back
    def pages_machine(path, page=0):
        mm = NowMachine(); mm.page(); mm.src(0); sv, dots = mm.widget('slide_view'), mm.widget('slide_indicator'); mm.props[(sv, 'value')] = page
        mm.play([mm.record(path=path)], 0); mm.init()
        return mm, sv, dots
    def pages_did(mm, sv, dots): return [c for c in mm.calls if c[0] in ('widget_set_prop_int', 'widget_set_sensitive', 'widget_set_visible') and c[1] in (sv, dots)]
    for what, path in (('an episode', EP1), ('a book part', BK)):
        for page in (0, 1, 2):
            mm, sv, dots = pages_machine(path, page)
            turned = [c for c in mm.calls if c[0] == 'widget_set_prop_int' and c[1] == sv]
            expect(turned == ([('widget_set_prop_int', sv, 'value', 0)] if page else []) and mm.props.get((sv, 'sensitive')) == 0 and mm.props.get((dots, 'visible')) == 0 and mm.props.get((dots, 'sensitive')) == 0,
                   f'{what}, the page opened on slide {page}: the cover page, the slide view takes no touch, the dots are hidden ({turned})')
        mm.tick()
        expect(not pages_did(mm, sv, dots), f'{what}: later ticks do nothing more to the slide view or the dots ({pages_did(mm, sv, dots)})')
        mm.play([mm.record(path=MUSIC1)], 0); mm.tick()
        expect(mm.props.get((sv, 'sensitive')) == 1 and mm.props.get((dots, 'visible')) == 1 and mm.props.get((dots, 'sensitive')) == 1 and not [c for c in mm.calls if c[0] == 'widget_set_prop_int' and c[1] == sv],
               f'music after {what}: the slide view swipes again and the dots show; the page is not turned')
    mm, sv, dots = pages_machine(MUSIC1, 1)
    expect(not pages_did(mm, sv, dots), f'music: the slide view and the dots are never touched ({pages_did(mm, sv, dots)})')
    # a slide view that refuses the turn (it is animating) is not locked on the wrong page: nothing is locked until the cover page is confirmed, and every tick asks again
    mm = NowMachine(); mm.page(); mm.src(0); sv, dots = mm.widget('slide_view'), mm.widget('slide_indicator'); mm.props[(sv, 'value')] = 1; mm.sv_refuse = 2
    mm.play([mm.record(path=EP1)], 0); mm.init()
    expect(pages_did(mm, sv, dots) == [('widget_set_prop_int', sv, 'value', 0)] and (sv, 'sensitive') not in mm.props and (dots, 'visible') not in mm.props, f'an episode starting while the lyrics slide refuses the turn: asked, nothing locked ({pages_did(mm, sv, dots)})')
    mm.tick()
    expect(pages_did(mm, sv, dots) == [('widget_set_prop_int', sv, 'value', 0)] and (sv, 'sensitive') not in mm.props, 'the next tick asks again; still refused, still not locked')
    mm.tick()
    expect(mm.props[(sv, 'value')] == 0 and mm.props.get((sv, 'sensitive')) == 0 and mm.props.get((dots, 'visible')) == 0, 'once the cover page is confirmed the slide view is locked and the dots hidden')
    mm.props[(sv, 'value')] = 2; mm.tick()   # a slide that was still moving when the lock went on ends on its page
    expect(pages_did(mm, sv, dots) == [('widget_set_prop_int', sv, 'value', 0)] and mm.props[(sv, 'value')] == 0, f'a locked slide view found on another page is turned back to the cover ({pages_did(mm, sv, dots)})')
    for n in ('np_back15', 'np_fwd30', 'np_back15_down', 'np_fwd30_down'):
        im = asset_image(n); box = im.getchannel('A').point(lambda v: 255 if v > 200 else 0).getbbox()
        expect(im.size == asset_image('np_prev').size == (44, 44) and box is not None and box[2] - box[0] >= 22 and box[3] - box[1] >= 24, f'{n}: a 44 px glyph like np_prev ({im.size}, ink {box})')
    # the ring is open where the arrowhead points: its upper left on the back glyph (the upper right is ring), the mirror image on the forward one
    rr = mod_icons.SKIP_RING_D / 2; gy = round(22 + mod_icons.SKIP_DROP - rr * 0.766); gl, gr = round(22 - rr * 0.643), round(22 + rr * 0.643)   # the ring at 40 degrees either side of its top
    gaps = [[sum(asset_image(n).getchannel('A').crop((x - 2, gy - 2, x + 2, gy + 2)).getdata()) for x in (gl, gr)] for n in ('np_back15', 'np_fwd30')]
    expect(gaps[0][0] < 200 < 1000 < gaps[0][1] and gaps[1][1] < 200 < 1000 < gaps[1][0], f'the back glyph\'s ring opens at its upper left (the arrowhead points left), the forward glyph\'s at its upper right ({gaps})')
    m = bk_machine(1)
    m.calls = []; m.src(0); m.tick()
    expect(len(art_paint(m)) == 1, 'busy, then no picture: the book\'s cover')
    m = bk_machine(0, cover=None)
    m.bkcov[BK] = BKF; m.jpeg(BKF, size=(4, 4), pix=bytes([20, 200, 20, 255]) * 16); m.tick()
    expect(not art_paint(m), 'a book cover made while its part plays: the part keeps the answer it got (asked once per track)')
    m.src(1); m.tick(); m.src(0); m.tick()
    expect(len(art_paint(m)) == 1, 'the part restarting (stock busy, then no picture): the book is asked again and its new cover shows')
    m = bk_machine(0, cover=None)
    m.play([m.record(album='Local', artist='A', path='/mnt/mmc/a/1.flac', rid=1)], 0); m.tick()
    m.bkcov[BK] = BKF; m.jpeg(BKF, size=(4, 4), pix=bytes([20, 200, 20, 255]) * 16)
    m.play([m.record(album='Book One', artist='N', path=BK, rid=3)], 0); m.tick()
    expect(len(art_paint(m)) == 1, 'back to the part after another track: the book is asked again')
    for src in (2, 3, 5):   # the track between has stock art of its own, and no tick sees stock busy on either change
        m = bk_machine(0, cover=None)
        m.src(src); m.play([m.record(album='Local', artist='A', path='/mnt/mmc/a/1.flac', rid=1)], 0); m.tick()
        m.bkcov[BK] = BKF; m.jpeg(BKF, size=(4, 4), pix=bytes([20, 200, 20, 255]) * 16)
        m.src(0); m.play([m.record(album='Book One', artist='N', path=BK, rid=3)], 0); m.tick()
        expect(len(art_paint(m)) == 1, f'back to the part after a track with stock art (source {src}), stock never seen busy: the book is asked again')
    LONG = 'A Long Audiobook Name ' * 5 + 'Volume One'   # 120 bytes: a book folder name as long as BK_FILE allows (ASCII: the harness reads names as Latin-1)
    LBK, LBKF = f'/mnt/mmc/Audiobooks/{LONG}/01.mp3', f'/mnt/mmc/Audiobooks/{LONG}/cover.jpg'
    m = bk_machine(0, path=LBK, cover=LBKF)
    expect(('widget_load_image', 'file://' + LBKF) in m.calls and len(art_paint(m)) == 1 and m.styles and m.styles[-1][2] == word_of(mn.tone(20, 200, 20)),
           'a book with a long name: its cover.jpg path fits, the big art and the tone come from it')

    # the cover of the next queue record is asked for once, while a server track plays
    m = NowMachine(); m.page(); m.src(0); m.sbcov = {-5: None, -6: None, -7: None}
    q = recs(m); m.play(q, 0); m.init()
    ahead = lambda rid: [c for c in m.calls if c == ('sba_now_cover', rid)]   # (each m.call, a tick included, starts a new call list; the playing track's own ask is two calls per tick)
    expect(len(ahead(-6)) == 1 and not ahead(-7), 'the next track\'s cover is asked for once, not the one after')
    m.tick(); expect(not ahead(-6), 'a tick later it is not asked again')
    m.play(q, 1); m.tick()
    expect(len(ahead(-7)) == 1, 'one step on: the new next track\'s')
    m.tick(); expect(not ahead(-7), 'and once')
    m.play(q, 2); m.tick()
    expect(len(ahead(-8)) == 1, 'the next one')
    m.play(q, 3); m.tick()
    expect(not ahead(1) and not ahead(-9), 'a local record after it: nothing asked')
    m.play(q, 4); m.tick()
    expect([c for c in m.calls if c[0] == 'sba_now_cover' and c[1] <= -2] == [], 'a local track playing: no server ask at all')
    m.play(q[:4], 3); m.tick()
    expect({c[1] for c in m.calls if c[0] == 'sba_now_cover'} == {-8}, 'the last track of the queue: only its own cover')

    # the info page of a server stream: no stream address (token, salt) and no stock size
    URL = 'http://music.example.com:4533/rest/stream.view?id=t1&u=bob&t=0123456789abcdef&s=salty&format=raw'
    def stream_info(path=URL, rid=-5, size=36 * 1048576, url='https://music.example.com:4533/base', lang=None):
        m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1); m.set_language(lang) if lang else None
        m.sbtrack = {-5: 't1'}; m.sbsize = {-5: size}; m.sburl = url
        m.play([m.record(album='Srv', artist='A', path=path, rid=rid)], 0)
        stock = dict(stock_en, label_size='File Size:0.00MB', label_location='Location:' + path)
        m.info_page(stock, True); m.init(); return m
    m = stream_info()
    expect(rowv(m, 6) == ('File Size', '36.00 MB') and rowv(m, 7) == ('Location', 'https://music.example.com:4533') and rowv(m, 4) == ('Genre', 'Rock'),
           f'a stream: the server size and address, the other rows as before ({rowv(m, 6)}, {rowv(m, 7)})')
    expect(not any('0123456789abcdef' in t or 'salty' in t or 'bob' in t for h, t in m.texts.items() if h in [m.widgets[n] for n in m.IW]), 'no token, salt or user in the page\'s own labels (stock\'s hidden ones keep stock\'s text)')
    for _ in range(3): m.tick()
    m.calls = []; m.tick(); m.tick()
    expect(not sets(m), 'no loop')
    m.texts[m.widgets['label_size']] = 'File Size:0.00MB'; m.texts[m.widgets['label_location']] = 'Location:' + URL; m.calls = []; m.tick()
    expect(rowv(m, 6) == ('File Size', '36.00 MB') and rowv(m, 7) == ('Location', 'https://music.example.com:4533'), 'stock writes them again (a track change): ours again')
    m = NowMachine(); m.page(); m.src(0); m.pt = (30, 200, 1)
    U2 = URL.replace('t1', 't2')
    m.sbtrack = {-5: 't1', -6: 't2'}; m.sbsize = {-5: 36 * 1048576, -6: 72 * 1048576}; m.sburl = 'https://music.example.com:4533/base'
    m.play([m.record(album='Srv', artist='A', path=URL, rid=-5), m.record(album='Srv', artist='A', path=U2, rid=-6)], 0)
    m.info_page(dict(stock_en, label_size='File Size:0.00MB', label_location='Location:' + URL), True); m.init()
    for _ in range(4): m.tick()   # past the NP_RELAY ticks, which lay the rows out whatever the text
    expect(rowv(m, 6) == ('File Size', '36.00 MB'), 'first stream: 36 MB')
    m.play([m.record(album='Srv', artist='A', path=URL, rid=-5), m.record(album='Srv', artist='A', path=U2, rid=-6)], 1); m.tick()
    expect(rowv(m, 6) == ('File Size', '72.00 MB'), f'the next stream (same stock text): its own size ({rowv(m, 6)})')
    for size, want in ((0, 'Unknown'), (7444890, '7.10 MB'), (1048575, '1.00 MB'), (4000000000, '3814.70 MB')):
        expect(rowv(stream_info(size=size), 6) == ('File Size', want), f'size {size}: {want}')
    expect(rowv(stream_info(url='https://bob:secret@music.example.com/x?y=1'), 7)[1] == 'https://music.example.com', 'user info, path and query are not shown')
    expect(rowv(stream_info(url=''), 7)[1] == 'Unknown', 'no saved server: Unknown')
    m = stream_info(path='/mnt/mmc/Subsonic/a.flac')
    expect(rowv(m, 6) == ('File Size', '0.00 MB') and rowv(m, 7) == ('Location', '/mnt/mmc/Subsonic/a.flac'), 'a downloaded track plays from its own path: stock\'s lines')
    m = stream_info(rid=1)
    expect(rowv(m, 6) == ('File Size', '0.00 MB') and (rowv(m, 7)[1] + (T(m, 'np_i_v8') if shown(m, 'np_i_v8') else '')).endswith('format=raw') and len(T(m, 'np_i_v7')) < 60, 'a record outside the queue map: stock\'s lines')

    # screen-off pause & synchronous wake refresh (NP_IDLE_PINS, np_on_dark / np_on_wake / np_tick)
    stock = stock_demo_bytes(); built = built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    expect(all(word(stock, a) == old and word(built, a) == old for a, old, _ in pod.NP_IDLE_PINS), 'NP_IDLE_PINS match stock and stay untouched')
    m = NowMachine(); m.page(); m.src(0)
    m.handlers[pod.FUNCTIONS['window_manager_check_and_layout'][2]] = 'window_manager_check_and_layout'
    ti, ar = m.widget('scrlabel_title'), m.widget('scrlabel_artist')
    m.init()
    m.calls = []; m.call(PSYMS['bp_light_off'], a0=0, count=200000)
    expect(('player_timer_clear', WIN) in m.calls and ('hscroll_label_stop', ti) in m.calls and ('hscroll_label_stop', ar) in m.calls
           and ('timer_modify', 0x777, 1000) in m.calls and ('toolSetBackLight', 0) in m.calls,
           f'bp_light_off pauses stock 500 ms timer, stops title/artist marquees, slows np_tick to 1000 ms ({m.calls})')
    # second dark call is a no-op for Now Playing; dark tick does not restart anything
    m.screen(False); m.calls = []; m.tick()
    expect(not any(c[0] in ('player_timer_clear', 'player_timer_start', 'show_player_face', 'hscroll_label_stop', 'hscroll_label_start', 'get_playtimeandlength', 'timer_modify') for c in m.calls),
           f'dark np_tick is quiet after np_on_dark ({m.calls})')
    # synchronous wake via bp_light_on while BACKLIGHT_STATUS is still 0 (stock sets it after toolSetBackLight)
    m.pt = (45, 200, 1); m.calls = []; m.call(PSYMS['bp_light_on'], a0=1, count=200000)
    names = m.names()
    expect(('show_player_face', WIN, 0) in m.calls and ('player_timer_start', WIN) in m.calls
           and ('hscroll_label_start', ti) in m.calls and ('hscroll_label_start', ar) in m.calls
           and ('timer_modify', 0x777, 500) in m.calls and ('get_playtimeandlength',) in m.calls
           and names.index('show_player_face') < names.index('toolSetBackLight'),
           f'bp_light_on refreshes stock face + our times and restarts timers/marquees before toolSetBackLight ({m.calls})')
    # second wake while already lit does not double-start stock's 500 ms timer
    m.calls = []; m.call(PSYMS['bp_light_on'], a0=1, count=200000)
    expect(not any(c[0] in ('player_timer_start', 'show_player_face', 'hscroll_label_start') for c in m.calls), f'repeated wake is a no-op ({m.calls})')
    # Lock Screen wake sequence: dark on Now Playing -> Lock Screen opens (TO_BG) -> bp_light_on while covered -> unlock (TO_FG)
    # Paused strictly while dark: bp_light_on resumes stock's 500 ms timer (preserving stream disconnect checks) and marquees
    # without repainting the covered page; TO_FG refreshes our face without restarting stock's timer again
    m.call(PSYMS['bp_light_off'], a0=0, count=200000); m.screen(False)
    m.fire(O['EVT_WINDOW_TO_BG'])
    m.calls = []; m.call(PSYMS['bp_light_on'], a0=1, count=200000); m.screen(True)
    expect(('player_timer_start', WIN) in m.calls and ('hscroll_label_start', ti) in m.calls
           and ('hscroll_label_start', ar) in m.calls and ('timer_modify', 0x777, 500) in m.calls
           and 'show_player_face' not in m.names() and 'get_playtimeandlength' not in m.names(),
           f'wake while covered by lock screen resumes stock timer & marquees without repainting covered page ({m.calls})')
    m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(('get_playtimeandlength',) in m.calls and 'player_timer_start' not in m.names(),
           f'unlocking back to Now Playing catches up our face; stock timer is already running ({m.calls})')
    # Idle view covering Now Playing when screen turns off: pauses stock's hidden 500 ms timer and marquees while dark, resumes on wake
    m.fire(O['EVT_WINDOW_TO_BG'])
    m.calls = []; m.call(PSYMS['bp_light_off'], a0=0, count=200000); m.screen(False)
    expect(('player_timer_clear', WIN) in m.calls and ('hscroll_label_stop', ti) in m.calls and ('hscroll_label_stop', ar) in m.calls,
           f'screen off while covered by idle view still clears stock 500 ms timer and marquees ({m.calls})')
    m.calls = []; m.call(PSYMS['bp_light_on'], a0=1, count=200000); m.screen(True)
    expect(('player_timer_start', WIN) in m.calls and ('hscroll_label_start', ti) in m.calls and 'show_player_face' not in m.names(),
           f'waking on idle view resumes stock 500 ms timer and marquees ({m.calls})')
    # returning to foreground while still dark keeps timers paused until wake
    m.call(PSYMS['bp_light_off'], a0=0, count=200000); m.screen(False)
    m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(not any(c[0] in ('player_timer_start', 'show_player_face', 'hscroll_label_start') for c in m.calls),
           f'foreground while dark does not restart timers ({m.calls})')
    m.calls = []; m.call(PSYMS['bp_light_on'], a0=1, count=200000); m.screen(True)
    expect(('show_player_face', WIN, 0) in m.calls and ('player_timer_start', WIN) in m.calls,
           f'later wake restarts timers once lit ({m.calls})')
    # incomplete window listeners (EVT_WINDOW_TO_BG ok, EVT_WINDOW_TO_FG refused): np.fg must not stick at 0 and freeze playback timer after dark/wake
    m2 = NowMachine().with_bar(); m2.page(); m2.src(0)
    m2.handlers[pod.FUNCTIONS['window_manager_check_and_layout'][2]] = 'window_manager_check_and_layout'
    ti2, ar2 = m2.widget('scrlabel_title'), m2.widget('scrlabel_artist')
    m2.on_fail = {O['EVT_WINDOW_TO_FG']}; m2.init()
    m2.top_main = 0x24001000; m2.fire(O['EVT_WINDOW_TO_BG'])
    m2.call(PSYMS['bp_light_off'], a0=0, count=200000); m2.screen(False)
    m2.top_main = WIN; m2.calls = []; m2.call(PSYMS['bp_light_on'], a0=1, count=200000); m2.screen(True)
    expect(('show_player_face', WIN, 0) in m2.calls and ('player_timer_start', WIN) in m2.calls
           and ('hscroll_label_start', ti2) in m2.calls and ('hscroll_label_start', ar2) in m2.calls,
           f'TO_FG refused: wake still restores stock 500 ms timer and marquees ({m2.calls})')
    # after destroy, bp_light_off / bp_light_on touch nothing of Now Playing
    m.screen(True); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    m.calls = []; m.call(PSYMS['bp_light_off'], a0=0, count=200000)
    expect(m.calls == [('toolSetBackLight', 0)], f'after destroy bp_light_off touches only backlight ({m.calls})')

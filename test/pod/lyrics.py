"""The lyrics page (patch/lyrics.c): the stock rows read as they are, our label pool laid out from them (the current line anchored at 0.35 of the view,
opacity by distance, wrapped lines, the eased scroll), every fall back to the stock list, and the built assets (np_lyrics, the label styles)."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_style, awtk_ui, mod_font, mod_nowplaying as mn

nowplaying = sibling('nowplaying')
WIN = nowplaying.WIN
POOL, ANCHOR, LINE_H, GAP, VIEW_H, W = (O[k] for k in ('LY_POOL', 'LY_ANCHOR', 'LY_LINE_H', 'LY_GAP', 'LY_VIEW_H', 'LY_W'))
PITCH = LINE_H + GAP
FIT, ROW, SNAP, FRAME, SPRING, OFF_MAX = O['LY_FIT_W'], O['LY_ROW_W'], O['LY_SNAP_LINES'], O['LY_FRAME_MS'], O['LY_SPRING_MS'], O['LY_OFF_MAX']
MAXR, AMIN, AROOM, MARK = O['LY_LINES_MAX'], O['LY_ANCHOR_MIN'], O['LY_ANCHOR_ROOM'], '\u2026'


def anchor(rows, lh=LINE_H, gap=GAP):
    """The model of ly_anchor: where the top of an anchored line of `rows` rows sits. ANCHOR up to three rows; a taller line higher, the next line's first row ending
    AROOM px above the view's bottom, but not above AMIN."""
    a = VIEW_H - AROOM - lh - (rows * lh + gap)
    return ANCHOR if a >= ANCHOR else max(a, AMIN)
FADE, BROWSE = O['LY_FADE'], O['LY_BROWSE_OP']
DOT, DPITCH, DX, DPAD, DMIN, DMS, DDIM, DFADE, DBR, DBRMIN = (O[k] for k in ('LY_DOT', 'LY_DOT_PITCH', 'LY_DOT_X', 'LY_DOT_PAD', 'LY_DOT_MIN_S', 'LY_DOT_MS', 'LY_DOT_DIM', 'LY_DOT_FADE_MS', 'LY_DOT_BREATH_MS', 'LY_DOT_BREATH_MIN'))
OPACITY = (255, 115, 82, 61, 46)   # 1.0, 0.45, 0.32, 0.24, 0.18 by distance from the current line (4 and further: the last)
BOLD, CJKF = 'np_lyric_style', 'np_lyric_cjk_style'
BOLD_FILE = os.path.join(ROOT, 'assets', 'fonts', 'Inter-Bold-m1plus.ttf')


def bold_cps():
    """The code points the bold face may draw: the Inter Bold subset's cmap, less the combining marks and U+200B (patch/lyrics.c ly_bold)."""
    from fontTools.ttLib import TTFont
    return {c for c in TTFont(BOLD_FILE).getBestCmap() if not 0x2B0 <= c <= 0x36F and c != 0x200B}


BOLD_CPS = bold_cps()


def latin(text): return all(ord(c) in BOLD_CPS for c in text)
def face(text): return BOLD if latin(text) else CJKF


def edge(y, rows):
    """The model of ly_edge: the row of a label nearest an edge, by its centre, over the last FADE px: 0 on the edge, 255 from FADE px in."""
    e = min(y + rows * LINE_H - LINE_H // 2, VIEW_H - (y + LINE_H // 2))
    return 0 if e <= 0 else 255 if e >= FADE else e * 255 // FADE


def fade(op, y, rows): return op * edge(y, rows) // 255


def is_cur(s, k):
    """Whether the label of text k is the current line: the highlight is the only thing that makes a line fully opaque (before the edge factor)."""
    return s[k][1] == fade(255, s[k][0], s[k][3] // LINE_H)


def as_read(s): return s.encode('utf-8').decode('latin-1')   # what the machine's read_cstr gives for a text


class LyMachine(nowplaying.NowMachine):
    """The Now Playing machine with a stock lyric list (scroll_lrc's rows: lrc_time and text), the player's position and status, and a text measure.
    Styles as AWTK resolves them (offsets.inc WINDOW_STAGE_CREATED): the hook runs in a loaded window (stage 1); after it the window is about to open (stage 2,
    every widget's asked style resolved); widget_use_style resolves only in an opened window (stage 3 or 5), widget_update_style from stage 2. A measure is in
    the resolved style: the label default style (none resolved) measures 3/5 of the width (18 px against 30)."""

    no_dtimer = False

    def __init__(self, lines=(), measure=None):
        super().__init__()
        self.page(); self.src(0)
        self.src_w, self.view, self.box = self.widget('scroll_lrc'), self.widget('view_lrc'), self.widget('np_lyrics')
        self.msg = self.widget('label_lyricmsg')
        self.play, self.status, self.clock = 0, 2, 5000
        self.measure_fn = measure or (lambda s: 10 * len(s))
        self.set_lines(lines)
        self.seeks, self.seek_moves = [], True        # seek_time's arguments; whether the player then reads the new position
        self.setword(self.box, 28); self.setword(self.box + 4, 44)   # np_lyrics at (28, 44), no parent: widget_to_local (stock code, run for real) subtracts it
        self.resolved = {}                            # widget -> the style its measures use

    def stage(self, v, win=WIN):
        self.props[(win, 'stage')] = v
        if v == 2:   # EVT_WINDOW_WILL_OPEN: every widget's asked style is resolved
            for (w, k), st in list(self.props.items()):
                if k == 'style': self.resolved[w] = st

    def init(self, win=WIN, count=6000000, open_after=True):
        self.stage(1, win)
        ret = super().init(win, count)
        if open_after: self.stage(2, win)
        return ret

    def set_lines(self, lines):
        """Stock builds the rows again (destroy children, then one per line): new handles every time."""
        rows = []
        for t, s in lines:
            h = self.alloc(0x80); rows.append(h); self.props[(h, 'lrc_time')] = t; self.texts[h] = as_read(s)
        self.children[self.src_w] = rows
        return rows

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        if name == 'get_playtime':
            self.calls.append(('get_playtime',)); ret = self.play
        elif name == 'mclGetPlayStatus':
            ret = self.status
        elif name == 'timer_add' and self.no_dtimer and a0 == PSYMS['ly_dframe']:
            self.calls.append(('timer_add', a0, u.reg_read(UC_MIPS_REG_A2))); ret = 0   # the dots' timer refused, the others not
        elif name == 'seek_time':
            self.seeks.append(a0); ret = 1
            if self.seek_moves: self.play = a0
        elif name == 'widget_measure_text':
            n = 0
            while self.word(a1 + 4 * n): n += 1
            t = ''.join(chr(c) for c in struct.unpack(f'<{n}I', self.u.mem_read(a1, 4 * n))) if n else ''
            st = self.resolved.get(a0)
            self.calls.append(('widget_measure_text', a0, st))
            w = float(self.measure_fn(t)) * (1 if st and st.startswith(('np_lyric_style', 'np_lyric_cjk_style')) else 0.6)
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        elif name == 'widget_use_style':
            super()._hook(u, address, size, _)
            if self.props.get((WIN, 'stage')) in (3, 5): self.resolved[a0] = self.props[(a0, 'style')]
            return
        elif name == 'widget_update_style':
            super()._hook(u, address, size, _)
            if self.props.get((WIN, 'stage'), 0) >= 2 and (a0, 'style') in self.props: self.resolved[a0] = self.props[(a0, 'style')]
            return
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def pool(self): return self.children.get(self.box, [])[:POOL]
    def probe(self): return self.children[self.box][POOL]
    def dots(self): return self.children[self.box][POOL + 1:POOL + 4]

    def dot_state(self):
        """[(visible, x, y, opacity)] of the three dots."""
        s32 = lambda v: struct.unpack('<i', struct.pack('<I', v))[0]
        return [(self.props.get((h, 'visible')), s32(self.props.get((h, 'x'), 0)), s32(self.props.get((h, 'y'), 0)), self.props.get((h, 'opacity'), 255)) for h in self.dots()]

    def dot_ops(self): return [d[3] if d[0] else 0 for d in self.dot_state()]
    def dframe(self, ms=DMS):
        self.clock += ms
        return self.call(PSYMS['ly_dframe'], count=2000000)
    def dtimers(self): return [t for t in self.timers if t[0] == PSYMS['ly_dframe']]

    def label_text(self, h): return self.texts[h].encode('latin-1').decode('utf-8')

    def source_of(self, t):
        """The stock row text a label text is made from: the same without its breaks (a space or a newline), or a prefix of it (a line cut at MAXR rows, the mark after it)."""
        flat = lambda x: x.replace(' ', '').replace('\n', '')
        rows = [self.texts[h].encode('latin-1').decode('utf-8') for h in self.children[self.src_w]]
        return next((r for r in rows if r == t), next((r for r in rows if flat(r) == flat(t)), next((r for r in rows if flat(r).startswith(flat(t.removesuffix(MARK)))), t)))

    def shown(self):
        """text -> (y, opacity, style, height) of every visible label."""
        out = {}
        for h in self.pool():
            if self.props.get((h, 'visible')):
                out[self.source_of(self.label_text(h))] = (struct.unpack('<i', struct.pack('<I', self.props.get((h, 'y'))))[0], self.props.get((h, 'opacity'), 255), self.props.get((h, 'style')), self.props.get((h, 'h')))
        return out

    def ly_timers(self): return [t for t in self.timers if t[0] == PSYMS['ly_frame']]
    def frame(self, ms):
        self.clock += ms
        return self.call(PSYMS['ly_frame'], count=2000000)

    def ptr(self, kind, x, y):
        """A pointer event (screen coordinates) for the page's listener; the handler's answer."""
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30)); self.setword(e, kind); self.setword(e + O['PE_X'], x); self.setword(e + O['PE_Y'], y)
        self.calls = []
        return self.call(PSYMS['ly_on_touch'], a0=self.box, a1=e, count=4000000)
    # (box coordinates in, the screen's out: np_lyrics is at 28, 44)
    def down(self, x, y): return self.ptr(O['EVT_POINTER_DOWN'], 28 + x, 44 + y)
    def move(self, x, y): return self.ptr(O['EVT_POINTER_MOVE'], 28 + x, 44 + y)
    def up(self, x, y): return self.ptr(O['EVT_POINTER_UP'], 28 + x, 44 + y)

    def at(self, pos):
        self.play = pos; self.calls = []; self.tick(count=8000000)
        return self.calls


def break_rows(text, measure):
    """The model of ly_break and ly_wrapped: the rows (strings) a line is broken into. The line measures at most FIT: one row. Else greedy at the spaces, rows at most ROW wide,
    a word wider than a row by character, at most MAXR rows. The last of MAXR rows keeps room for MARK: what does not fit beside it is cut and MARK ends the row, unless the
    whole rest of the line fits the row without it. Widths add up (words, spaces, characters); `measure` is the width of a string."""
    if measure(text) <= FIT: return [text]
    sp, mk = measure(' '), measure(MARK)
    rows, cur, x, pos = [], None, 0, 0    # cur: the row being made, None when it has no word yet; x its width; pos the word's place in the text
    lim = lambda: ROW - mk if len(rows) == MAXR - 1 else ROW
    for wd in text.split(' '):
        tw = measure(wd) if wd else 0
        if cur is not None and x + sp + tw > lim():
            if len(rows) == MAXR - 1:
                rest = text[pos:]
                return rows + [cur + ' ' + rest if x + sp + measure(rest) <= ROW else cur + MARK]
            rows.append(cur); cur, x = None, 0
        if cur is not None: x += sp
        if x + tw <= lim():
            cur = wd if cur is None else cur + ' ' + wd; x += tw
        else:
            cur = ''
            for j, ch in enumerate(wd):
                cw = measure(ch)
                if x and x + cw > lim():
                    if len(rows) == MAXR - 1:
                        rest = text[pos + j:]
                        return rows + [cur + rest if x + measure(rest) <= ROW else cur + MARK]
                    rows.append(cur); cur, x = '', 0
                cur += ch; x += cw
        pos += len(wd) + 1
    rows.append(cur)
    return rows


def rows_of(text, measure): return len(break_rows(text, measure))


def stock_rows(t, measure, content=FIT):
    """The rows stock's label wrap draws for the text t (explicit newlines, then the helper at 0x62dbb0): a character whose row so far + itself + 1 px is over the content
    width wraps (back to the row's last space, else at the character) unless it is the text's last character, which stays on the row."""
    rows, cur, n = [], '', len(t)
    for j, ch in enumerate(t):
        if ch == '\n': rows.append(cur); cur = ''; continue
        if measure(cur) + measure(ch) + 1 > content and cur != '':
            if j == n - 1: cur += ch; continue
            k = cur.rfind(' ')
            if k >= 0: rows.append(cur[:k]); cur = cur[k + 1:] + ch
            else: rows.append(cur); cur = ch
        else: cur += ch
    rows.append(cur)
    return rows


def expect_layout(lines, cur, rem, measure):
    """The model of ly_layout: {text: (y, opacity, style, height)} for the lines that touch the view, the current line's top at its anchor + rem."""
    base = max(cur, 0); out = {}
    rows = [rows_of(s, measure) for _, s in lines]
    y = anchor(rows[base]) + rem
    for i in range(base, min(len(lines), base + POOL)):
        if y >= VIEW_H: break
        if y + rows[i] * LINE_H > 0: out[lines[i][1]] = i, y
        y += rows[i] * LINE_H + GAP
    y = anchor(rows[base]) + rem
    for i in range(base - 1, max(base - POOL, -1), -1):
        y -= rows[i] * LINE_H + GAP
        if y + rows[i] * LINE_H <= 0: break
        if y < VIEW_H: out[lines[i][1]] = i, y
    ref = -1 if cur < 0 else cur
    full = {s: (y, fade(OPACITY[min(abs(i - ref), 4)], y, rows[i]), face(s), rows[i] * LINE_H) for s, (i, y) in out.items()}
    return {s: v for s, v in full.items() if v[1]}


SONG = [(0, 'Line zero'), (5, 'Line one'), (10, 'Line two'), (15, 'Line three'), (20, 'Line four'), (25, 'Line five'), (30, 'Line six'), (35, 'Line seven'),
        (40, 'Line eight'), (45, 'Line nine'), (50, 'Line ten'), (55, 'Line eleven')]


import math as _math


def _zeta_table():
    z, wn = 0.72, 12.0
    wd = wn * _math.sqrt(1 - z * z)
    return [round(1024 * _math.exp(-z * wn * t) * (_math.cos(wd * t) + z / _math.sqrt(1 - z * z) * _math.sin(wd * t))) for t in (i * 0.01 for i in range(65))]


TAB = _zeta_table()   # the spring: 1024 x g(t) every 10 ms, zeta 0.72, wn 12 /s


def cdiv(a, b):
    """C integer division: toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def spring(o0, elapsed):
    """The model of ly_spring: the offset of a line whose spring began at o0, `elapsed` ms ago."""
    if elapsed <= 0: return o0
    if elapsed >= SPRING: return 0
    idx, fr = elapsed // 10, elapsed % 10
    g = TAB[idx] + cdiv((TAB[idx + 1] - TAB[idx]) * fr, 10)
    v = cdiv(o0 * g, 1024)
    cap = O['LY_OVERSHOOT_MAX']
    if o0 > 0 and v < -cap: v = -cap
    if o0 < 0 and v > cap: v = cap
    return v


def delay(i, c):
    """The model of ly_delay: 0 for lines above the one before the target c, then 50 ms and each step 20/21 of the one before."""
    r, d, s = min(i - (c - 1), POOL), 0, O['LY_DELAY_MS']
    while r > 0:
        d += s; s = s * 20 // 21; r -= 1
    return d


def dot_op(k, el, ln):
    """The model of ly_dot_op: dim to full as the k-th third of the gap passes, times the breath (triangle from el), times the fade out of the last DFADE ms."""
    if ln <= 0: return 0
    el = max(el, 0)
    fl = max(ln - DFADE, 1)
    f = min(max(el * 3 - k * fl, 0), fl)
    op = DDIM + (255 - DDIM) * f // fl
    tri = el % DBR
    if tri > DBR // 2: tri = DBR - tri
    op = op * (255 - (255 - DBRMIN) * tri // (DBR // 2)) // 255
    left = ln - el
    if left < DFADE: op = 0 if left <= 0 else op * left // DFADE
    return op


class Clock:
    """The model of ly_clock: the player's position in ms from whole seconds and the monotonic clock."""
    def __init__(self): self.ok, self.pos, self.pl, self.t, self.est = False, 0, False, 0, 0

    def update(self, pos, now, playing):
        dt = now - self.t; self.t = now
        if not self.ok or pos < self.pos or pos > self.pos + 1: self.est = pos * 1000 + 500
        elif pos == self.pos + 1: self.est = pos * 1000
        elif playing and self.pl and dt > 0: self.est = min(self.est + dt, pos * 1000 + 999)
        self.ok, self.pos, self.pl = True, pos, playing


class Model:
    """The page's layout and motion as the document describes them, apart from the C: lines, the anchored line, the manual offset, one spring per line."""
    def __init__(self, lines, measure):
        self.lines = lines
        self.rows = [rows_of(s, measure) for _, s in lines]
        self.n, self.base, self.man, self.cur, self.browse = len(lines), 0, 0, -1, False
        self.o0, self.ts = {}, {}
        self.gd = self.gt = self.gcur = 0
        self.pad = 0

    def pitch(self, i): return self.rows[i] * LINE_H + GAP
    def off(self, i, now): return spring(self.o0[i], (now - self.ts[i] + 2**31) % 2**32 - 2**31)

    def move(self, nb, now, pad=0):
        nb = max(0, min(nb, self.n - 1))
        if abs(nb - self.base) > SNAP:
            self.o0 = {k: 0 for k in self.o0}; self.gd = 0
        else:
            d = self.man + self.pad - pad + anchor(self.rows[self.base]) - anchor(self.rows[nb]) + sum(self.pitch(i) for i in range(self.base, nb)) - sum(self.pitch(i) for i in range(nb, self.base))
            for i in self.o0:
                self.o0[i] = max(-4 * VIEW_H, min(4 * VIEW_H, self.off(i, now) + d)); self.ts[i] = now + delay(i, nb)
            self.gd, self.gt, self.gcur = d, now, nb
        self.base, self.man, self.pad = nb, 0, pad

    def layout(self, now):
        """{text: (y, opacity, style, height)} of the lines whose place (nominal + spring) touches the view."""
        out, np_ = {}, {}
        lo0 = max(self.base - POOL // 2 + 1, 0); lo, hi = lo0, min(self.base + POOL // 2, self.n - 1)
        y = anchor(self.rows[self.base]) + self.man + self.pad; np_[self.base] = y
        for i in range(self.base, hi):
            y += self.pitch(i)
            if y > VIEW_H + OFF_MAX: hi = i; break
            np_[i + 1] = y
        y = anchor(self.rows[self.base]) + self.man + self.pad
        for i in range(self.base - 1, lo0 - 1, -1):
            y -= self.pitch(i)
            if y < -OFF_MAX - MAXR * LINE_H: lo = i + 1; break
            np_[i] = y
        ref = -1 if self.cur < 0 else self.cur
        for i in range(lo, hi + 1):
            if i not in self.o0: self.o0[i] = self.gd; self.ts[i] = self.gt + delay(i, self.gcur)
            disp = np_[i] + self.off(i, now)
            if disp + self.rows[i] * LINE_H > 0 and disp < VIEW_H:
                op = fade((255 if i == self.cur else BROWSE) if self.browse else OPACITY[min(abs(i - ref), 4)], disp, self.rows[i])
                if op: out[self.lines[i][1]] = (disp, op, face(self.lines[i][1]), self.rows[i] * LINE_H)
        return out


def asset_tests(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    stock = open(os.path.join(paths.find_stock() or os.path.join(os.path.dirname(WORK), 'stock'), 'rootfs', pod.DEMO), 'rb').read()
    built = built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
    f = ui.find
    box, lrc, page = f('np_lyrics'), f('view_lrc'), f('view_lyrics')
    expect(box.type == 'scroll_view' and (box.x, box.y, box.w, box.h) == (lrc.x, lrc.y, lrc.w, lrc.h) == (28, 44, W, VIEW_H) and box in page.children
           and page.children.index(box) == page.children.index(lrc) + 1, f'np_lyrics: a scroll_view (it clips its children) on the stock list\'s rectangle (28, 44, {W}, {VIEW_H}), right after view_lrc')
    expect(box.get('sensitive') != 'false' and not box.children and box.get('xslidable') != 'true' and box.get('yslidable') != 'true', 'np_lyrics is sensitive (it takes the touches, the payload listens) and empty, and no axis slides: the scroll_view never scrolls itself (the payload makes its labels)')
    expect(W == mn.W - 2 * mn.M and VIEW_H == mn.LYR_H and ANCHOR == round(0.35 * VIEW_H), f'the payload constants are the asset\'s: {W} px wide, {VIEW_H} high, the anchor {ANCHOR} = 0.35 of the view')
    expect(all(f(n) is not None for n in ('view_lrc', 'scroll_lrc', 'label_lyricmsg')), 'every stock widget the app looks up by name is still there')
    expect(lrc.get('visible') != 'false' and f('scroll_lrc') is not None, 'view_lrc is not hidden by the asset (without the payload the stock list shows)')
    th = awtk_style.parse(open(os.path.join(raw, 'styles', 'playing_page.bin'), 'rb').read())
    ls = {(i.style, i.state): i for i in th.items if i.widget == 'label' and i.style in mn.LYRIC_LABEL_STYLES}
    li = {i.style: i for i in th.items if i.widget == 'list_item' and i.state == 'normal'}
    expect(set(mn.LYRIC_LABEL_STYLES) == {BOLD, CJKF} and all((n, st) in ls for n in mn.LYRIC_LABEL_STYLES for st in mn.BTN_STATES),
           'two label styles in every state: np_lyric_style (the bold face) and np_lyric_cjk_style (the default font); the current line is no longer a style')
    expect(all(ls[k].color('text_color').lower().startswith('#ffffff') for k in ls) and li['listitem_lyric_style'].color('text_color').lower().startswith('#c4c4c4')
           and li['listitem_sellyric_style'].color('text_color').lower().startswith('#eeeeec'),
           'every lyric line is white, neutral (the current one is only the most opaque); the hidden stock list_item styles keep their greys')
    expect(all(ls[k].get('font_size') == mn.LYR_FONT == O['LY_FONT'] == 30 for k in ls), f'the lines are {O["LY_FONT"]} px, the same for the current and the others')
    expect(all(ls[k].get('text_align_h') == mn.LYR_LEFT == 2 for k in ls) and all(li[n].get('text_align_h') == 1 for n in li if n.startswith('listitem_')),
           'the lines are left aligned (2 in this build: the stock msgpink style; 1 is centre, as the hidden stock list keeps)')
    expect(ls[(BOLD, 'normal')].get('font_name') == mn.LYR_FACE == 'lyrics' and all(ls[(CJKF, st)].get('font_name') is None for st in mn.BTN_STATES)
           and all(ls[(BOLD, st)].get('font_name') == 'lyrics' for st in mn.BTN_STATES),
           'the bold style names the font file lyrics.ttf, the other style none (the default font): font_manager_get_font falls back to the default font when a named file is missing')
    expect(LINE_H == O['LY_FONT'] + mn.LYR_SPACER and all(ls[k].get('spacer') == mn.LYR_SPACER for k in ls) and 1.1 <= LINE_H / O['LY_FONT'] <= 1.15,
           f'tight leading: AWTK spaces the rows of a wrapped label font + `spacer` = {O["LY_FONT"]} + {mn.LYR_SPACER} = {LINE_H} px ({LINE_H / O["LY_FONT"]:.2f} x), the pitch the payload lays out with')
    expect(GAP == 12 and PITCH == LINE_H + GAP, f'{GAP} px between lines (a pitch of {PITCH} for a single row)')
    # the bold face: a stand-alone file with default.ttf's vertical metrics, the Inter Bold subset
    import io
    from fontTools.ttLib import TTFont
    lyr = open(os.path.join(raw, 'fonts', 'lyrics.ttf'), 'rb').read()
    dflt = open(os.path.join(raw, 'fonts', 'default.ttf'), 'rb').read()
    a, b = TTFont(io.BytesIO(lyr)), TTFont(io.BytesIO(dflt))
    vm = lambda f: (f['head'].unitsPerEm, f['hhea'].ascent, f['hhea'].descent, f['hhea'].lineGap)
    expect(vm(a) == vm(b) and vm(a)[0] == 256, f'lyrics.ttf has default.ttf\'s unitsPerEm and ascender / descender / lineGap {vm(a)}: a size is the same px, the baseline the same')
    expect(set(a.getBestCmap()) >= BOLD_CPS and all(a['hmtx'][a.getBestCmap()[c]][0] > 0 or 0x483 <= c <= 0x489 for c in BOLD_CPS),
           f'it has every code point the payload sends to it ({len(BOLD_CPS)}) with an advance (but the Cyrillic combining marks)')
    expect(lyr == mod_font.lyric_face(open(BOLD_FILE, 'rb').read(), dflt, mod_font.LYRIC_TRACKING) and mod_font.LYRIC_TRACKING == 16,
           'and is the committed Inter Bold subset (assets/fonts/Inter-Bold-m1plus.ttf), tracked 16 units, nothing else (tools/mod_font.py lyric_face)')
    expect(len(lyr) < 200000 and a['name'].getDebugName(1) == 'Inter', f'{len(lyr)} bytes (the rootfs has ~983 KB to spare; fwtool enforces it), the name table is Inter\'s (OFL in assets/fonts/)')
    from awtk_text import Ttf, StbText
    fonts = {BOLD: Ttf(os.path.join(raw, 'fonts', 'lyrics.ttf')), CJKF: Ttf(os.path.join(raw, 'fonts', 'default.ttf'))}
    meas = lambda t: StbText(fonts[face(t)], O['LY_FONT']).layout(t)[1]
    # the room: a three-row current line at the anchor leaves the next line a full row under it
    fits = lambda px: ANCHOR + 3 * (px + mn.LYR_SPACER) + GAP + (px + mn.LYR_SPACER) <= VIEW_H - 8   # 8 px to spare under the next line
    expect(ANCHOR + 3 * LINE_H + GAP + LINE_H <= VIEW_H - 8 and AROOM == 8, f'a three-row current line ({ANCHOR}..{ANCHOR + 3 * LINE_H}) and the next line\'s row end at {ANCHOR + 3 * LINE_H + GAP + LINE_H} <= {VIEW_H - 8}')
    # a taller current line is anchored higher: four and five rows still show the next line's row, the tallest (MAXR rows) is whole in the view from the lowest anchor
    expect([anchor(r) for r in (1, 2, 3, 4, 5, 6)] == [85, 85, 85, 54, 20, 20] and MAXR == 6 and AMIN == 20, f'the anchors by rows: {[anchor(r) for r in range(1, MAXR + 1)]}')
    expect(all(anchor(r) + r * LINE_H + GAP + LINE_H <= VIEW_H - AROOM for r in (4, 5)) and AMIN + MAXR * LINE_H <= VIEW_H - AROOM and edge(AMIN, MAXR) == 255,
           f'four and five rows keep the next line\'s row {AROOM} px inside the view; {MAXR} rows from {AMIN} end at {AMIN + MAXR * LINE_H} <= {VIEW_H - AROOM}, not faded by the top edge')
    expect(fits(O['LY_FONT']) and not fits(O['LY_FONT'] + 1), f'{O["LY_FONT"]} px is the largest size (with the {mn.LYR_SPACER} px spacer) whose three-row line and next row keep 8 px in the view')
    samples = {'Latin, one row': ('Be what you want', 1), 'Latin, 263 px': ('Be what you want to be', 2), 'Latin, 61 characters': ('I got a feeling that tonight is going to be the night that I', 3),
               'Chinese, 26 characters': ('我想要有一天能够和你一起走遍这个世界上所有美丽的地方看遍所', 4),
               'Japanese, 26 characters': ('あなたと一緒に歩いた道を今でも覚えているよ夢のように', 3), 'Latin with one CJK character': ('Hello 你好 there', 1)}
    for name, (s, want) in samples.items():
        rows = rows_of(s, meas)
        expect(rows == want and (want == 1) == (meas(s) <= FIT), f'{name} ({face(s)}) at {O["LY_FONT"]} px: {meas(s)} px = {rows} rows (cap {MAXR})')
    # contrast: the current line over every tone under the tint and scrim; the falling-off lines at their opacity (white at a lower opacity: neutral, no accent)
    grid = [(r, g, b) for r in range(0, 256, 51) for g in range(0, 256, 51) for b in range(0, 256, 51)] + [(255, 255, 255)]
    col = lambda s: tuple(int(s[k:k + 2], 16) for k in (1, 3, 5))
    white = col(mn.LYR_WHITE)
    worst = {k: 99 for k in range(5)}
    for c in grid:
        t = mn.tone(*c)
        for y in range(mn.LYR_Y, mn.LYR_Y + mn.LYR_H, 4):
            keep, sk = 255 - mn.tint_alpha(y), 255 - mn.lscrim_alpha(y - mn.LSCRIM[1])
            bg = tuple(v * keep // 255 * sk // 255 for v in t)
            for k in worst:
                mix = tuple((f * OPACITY[k] + b * (255 - OPACITY[k])) // 255 for f, b in zip(white, bg))
                worst[k] = min(worst[k], contrast(mix, bg))
    FLOOR = (4.5, 2.3, 1.8, 1.55, 1.4)
    expect(all(worst[k] >= FLOOR[k] for k in worst) and white == (255, 255, 255),
           'contrast under the scrim over every tone (large text): ' + ', '.join(f'{["current", "next line", "then", "then", "the rest"][k]} {worst[k]:.2f}:1 (floor {FLOOR[k]})' for k in worst))
    expect(mn.LSCRIM_ALPHA == 68 and 0.25 <= mn.LSCRIM_ALPHA / 255 <= 0.30, f'the lyrics scrim is {mn.LSCRIM_ALPHA / 255:.0%} black ({mn.LSCRIM_ALPHA}), the lowest alpha that holds the floors above (64 would put the next line at 2.29:1); the info page keeps its {mn.SCRIM_ALPHA / 255:.0%}')
    from PIL import Image
    xx = os.path.join(raw, 'images', 'xx')
    sc = Image.open(os.path.join(xx, 'np_scrim_lyrics.png')).convert('RGBA')
    SW, SH = mn.LSCRIM[2:]
    al = [sc.getpixel((7, y))[3] for y in range(SH)]
    expect(sc.size == (SW, SH) and {sc.getpixel((x, y))[:3] for x in (0, 160, 319) for y in (0, 100, SH - 1)} == {(0, 0, 0)} and al == [mn.lscrim_alpha(y) for y in range(SH)] and all(sc.getpixel((x, y))[3] == al[y] for y in range(0, SH, 9) for x in (0, 319)),
           'np_scrim_lyrics.png: black, alpha rows as lscrim_alpha')
    ramp = al[:mn.LSCRIM_EDGE + 1]
    expect(al[0] == 0 and al[-1] == 0 and max(al) == mn.LSCRIM_ALPHA and al == al[::-1] and all(a == mn.LSCRIM_ALPHA for a in al[mn.LSCRIM_EDGE:SH - mn.LSCRIM_EDGE]) and all(x <= y for x, y in zip(ramp, ramp[1:]))
           and ramp[1] <= 1 and mn.LSCRIM_ALPHA - ramp[-2] <= 1 and max(y - x for x, y in zip(ramp, ramp[1:])) <= 4 and al[mn.LSCRIM_EDGE // 2] == mn.LSCRIM_ALPHA // 2,
           f'the lyrics scrim: {mn.LSCRIM_ALPHA} in the middle, easing (smoothstep) to 0 over {mn.LSCRIM_EDGE} rows at both ends, symmetric: no step bigger than {max(y - x for x, y in zip(ramp, ramp[1:]))} anywhere, flat at both ends of the ramp')
    expect(mn.LSCRIM[1] <= 0 and mn.LSCRIM[1] + mn.LSCRIM_EDGE <= mn.LYR_Y and mn.LYR_Y + mn.LYR_H <= mn.LSCRIM[1] + SH - mn.LSCRIM_EDGE and mn.LSCRIM_EDGE > mn.SCRIM_EDGE and os.path.getsize(os.path.join(xx, 'np_scrim_lyrics.png')) < 4000,
           f'the text area (y {mn.LYR_Y} .. {mn.LYR_Y + mn.LYR_H}) lies in the full-strength middle (y {mn.LSCRIM[1]} .. {mn.LSCRIM[1] + SH}), the ramp is longer than the info page\'s ({mn.SCRIM_EDGE}), the file is small')
    sl = f('img_np_scrim_lyrics')
    expect(page.children[0] is sl and (sl.x, sl.y, sl.w, sl.h) == mn.LSCRIM and sl.get('image') == 'np_scrim_lyrics' and sl.get('sensitive') == 'false' and f('img_np_scrim_info').get('image') == 'np_scrim',
           'img_np_scrim_lyrics (the same name) is the first child of the page with its own image, insensitive; the info page keeps np_scrim')
    dt = Image.open(os.path.join(xx, 'np_dot.png')).convert('RGBA')
    da = [[dt.getpixel((x, y))[3] for x in range(DOT)] for y in range(DOT)]
    expect(dt.size == (DOT, DOT) == (mn.DOT, mn.DOT) and {dt.getpixel((x, y))[:3] for x in range(DOT) for y in range(DOT) if da[y][x]} == {(255, 255, 255)} and da[0][0] == 0 and da[DOT // 2][DOT // 2] == 255 and da[DOT // 2 - 1][DOT // 2 - 1] == 255
           and all(da[y][x] == da[x][y] == da[y][DOT - 1 - x] == da[DOT - 1 - y][x] for x in range(DOT) for y in range(DOT)) and 0 < da[0][DOT // 2] < 255,
           f'np_dot.png: a {DOT} px white disc, anti-aliased, symmetric, clear in the corners ({da[0][:5]})')
    dd = sum(map(sum, da)) / 255
    expect(abs(dd - 3.14159 * DOT * DOT / 4) < 1.0 and os.path.getsize(os.path.join(xx, 'np_dot.png')) < 400, f'its area is a circle\'s ({dd:.1f} px of {3.14159 * DOT * DOT / 4:.1f}); the file is small')
    expect(OPACITY[1] > OPACITY[2] > OPACITY[3] > OPACITY[4] > 0 and OPACITY[0] == 255 and BROWSE > OPACITY[1], 'the falloff recedes by distance (1.0, 0.45, 0.32, 0.24, 0.18); scrolled, the other lines are 0.6')
    # a view shows at most ceil(VIEW_H / pitch) + 1 lines of the smallest pitch; the pool holds them with the one above and one below
    expect(POOL // 2 - 1 >= SNAP + -(-ANCHOR // PITCH) and POOL // 2 >= SNAP + -(-(VIEW_H - ANCHOR) // PITCH), f'the window of {POOL} lines round the anchor holds every line a move of {SNAP} lines can still show on the old screen, above and below ({PITCH} px the smallest pitch)')
    expect(all(word(stock, a) == w for a, w, _ in pod.LYRICS_PINS) and all(word(built, a) == w for a, w, _ in pod.LYRICS_PINS), 'the stock words patch/lyrics.c relies on are pinned and untouched (get_playtime, the rows\' "lrc_time", the timer)')
    expect(pod.FUNCTIONS['get_playtime'][2] == 0x4e02e4, 'get_playtime is the stock position call the lyric timer compares "lrc_time" with')
    expect(not any(a for a in (MANIFEST.get('hook_lyrics'),)), 'no new hook: the manifest has none for the lyrics')
    expect(set(k for k in MANIFEST if k.startswith('hook')) == {'hook', 'hook_init', 'hook_playing', 'hook_bigcover', 'hook_lockscreen', 'hook_playmore', 'hook_pulldown', 'hook_pulldown_open', 'hook_id3', 'hook_query', 'hook_sorted_query', 'hook_scan', 'hook_battery', 'hook_lineout', 'hook_wifihub', 'hook_idle', 'hook_tidalkb', 'hook_playrecord', 'hook_eq_row', 'hook_next_album', 'hook_lock_row', 'hook_style_color', 'hook_style_gradient', 'hook_image_add', 'hook_setmode', 'hook_loadplaylist', 'hook_file_created', 'hook_loadclass', 'hook_loadclass_assign', 'hook_clear_queue', 'hook_display_mode', 'hook_timezone', 'hook_start_player', 'hook_save_stop', 'hook_save_start', 'hook_backtoplayer'}, 'the hook set is the one the project documents')


def start_tests(ctx):
    expect = ctx.expect
    m = LyMachine(SONG); m.init()
    expect(m.names().count('label_create') == POOL + 1 and all(c[1] for c in m.calls if c[0] == 'label_create'), f'{POOL} labels and the probe are made')
    expect(m.children[m.box] == m.pool() + [m.probe()] + m.dots() and len(m.children[m.box]) == POOL + 4 and m.names().count('image_create') == 3, 'all of them in np_lyrics, then the three dot images')
    expect([c[2] for c in m.calls if c[0] == 'image_base_set_image'] == ['np_dot'] * 3 and not any(m.dot_ops()) and all(m.props.get((h, 'visible')) == 0 for h in m.dots()), 'the dots show the asset np_dot and start hidden')
    expect(all(m.props.get((h, 'sensitive')) == 0 for h in m.children[m.box]), 'every label is insensitive: a touch goes to the slide view')
    expect(m.props.get((m.view, 'visible')) == 0 and m.props.get((m.view, 'sensitive')) == 0, 'the stock list view_lrc is hidden: visible=false and sensitive=false')
    expect(not any(c[0] in ('widget_set_visible', 'widget_set_sensitive', 'widget_destroy_children', 'widget_destroy') and c[1] in (m.src_w, m.msg) for c in m.calls)
           and m.props.get((m.src_w, 'visible')) is None, 'scroll_lrc and label_lyricmsg are not touched (stock keeps both)')
    expect([c[2] for c in m.calls if c[0] == 'widget_on' and c[1] in (m.box, m.view, m.src_w, m.msg) + tuple(m.children[m.box])] == [O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']], 'the only listeners are the four pointer events of np_lyrics')
    expect(m.timers == [(PSYMS['np_tick'], 500)], 'no timer of its own at the start (the page timer is the only one)')
    s = m.shown()
    expect(s == expect_layout(SONG, 0, 0, m.measure_fn), f'at 0:00 line zero is current at the anchor, the rest follow ({s})')
    expect(s['Line zero'][0] == ANCHOR == 85 and s['Line zero'][1] == 255 and s['Line zero'][2] == BOLD, 'the current line: top at 0.35 of the view, opacity 1.0, the bold face')
    expect([s[f'Line {n}'][1] for n in ('one', 'two', 'three')] == [fade(OPACITY[k], ANCHOR + k * PITCH, 1) for k in (1, 2, 3)] and [s[f'Line {n}'][0] for n in ('one', 'two')] == [ANCHOR + PITCH, ANCHOR + 2 * PITCH]
           and s['Line one'][1] == 115 and 0 < s['Line three'][1] < s['Line two'][1] < s['Line one'][1],
           f'then 0.45, 0.32, 0.24 times the edge factor with one pitch (LINE_H + GAP) a single line ({[s[f"Line {n}"][1] for n in ("one", "two", "three")]}): the line near the bottom edge fades out')
    expect('Line four' not in s and 'Line five' not in s, 'a line past the view is not laid out')

    # the hook's tick measures nothing: the window resolves the labels' styles only after the stock init (offsets.inc WINDOW_STAGE_CREATED), a measure before would be in
    # the label default style; the first page tick measures, each line in its own resolved style, and with lines of one row changes no label but the probe
    expect(not any(x[0] == 'widget_measure_text' for x in m.calls), 'the hook\'s tick measures nothing (the styles are not resolved yet)')
    c = m.at(0)
    meas = [x for x in c if x[0] == 'widget_measure_text']
    expect(len(meas) >= 4 and all(x[1] == m.probe() and x[2] == BOLD for x in meas) and ('widget_update_style', m.probe()) in c
           and not any(x[0] in ('widget_move', 'widget_resize', 'widget_set_text_utf8', 'widget_use_style', 'widget_set_opacity', 'widget_set_visible') and x[1] != m.probe() for x in c),
           f'the first page tick measures {len(meas)} lines in the resolved bold style and touches no label')
    # a tick that changes nothing touches nothing
    c = m.at(0)
    expect(not any(x[0] in ('widget_move', 'widget_resize', 'widget_set_text_utf8', 'widget_use_style', 'widget_set_opacity', 'widget_set_visible') for x in c), f'an unchanged tick makes no widget call ({m.names()})')
    expect(('get_playtime',) in c, 'the position is read from the stock call')

    # a second page built over a live one: the old pool is forgotten, a fresh one is made (the old window's widgets go with it)
    m.init(win=WIN + 0x100)
    expect(m.names().count('label_create') == POOL + 1, 'a page built over a live one makes its own pool')
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0); m.calls = []; m.tick(); expect(('get_playtime',) in m.calls, 'the earlier page\'s destroy leaves the new one running')

    # fall backs
    m = LyMachine(SONG); del m.widgets['np_lyrics']; m.init(); m.tick()
    expect('label_create' not in m.names() and m.props.get((m.view, 'visible')) is None and ('get_playtime',) not in m.calls, 'no np_lyrics in the asset: stock only, and no lyric work')
    m = LyMachine(SONG); del m.widgets['view_lrc']; m.init()
    expect('label_create' not in m.names(), 'no view_lrc: stock only')
    m = LyMachine(SONG); del m.widgets['scroll_lrc']; m.init()
    expect('label_create' not in m.names() and m.props.get((m.view, 'visible')) is None, 'no scroll_lrc: stock only')
    m = LyMachine(SONG); m.create_fail = {'label_create'}; m.init()
    expect(m.props.get((m.view, 'visible')) is None and ('widget_destroy_children', m.box) in m.calls and m.timers, 'a label that cannot be made: the stock list stays, what was made goes, the page still runs')
    m.calls = []; m.tick(); expect(('get_playtime',) not in m.calls, 'and the lyric tick does nothing')
    m = LyMachine(SONG); m.init(); m.set_lines([]); m.tick()
    expect(not m.shown() and m.props.get((m.view, 'visible')) == 0, 'no lyrics: no line is shown (the stock "no lyrics" label is stock\'s to show)')
    m.set_lines(SONG); m.tick(); expect(len(m.shown()) == 4, 'and they come back with the next song\'s lyrics')

    # destroy
    m = LyMachine(SONG); m.init(); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    m.calls = []; m.call(PSYMS['np_tick'], count=500000)
    expect(not m.calls, 'after the page is destroyed a stray tick does nothing')
    m.calls = []; r = m.call(PSYMS['ly_frame'], count=500000)
    expect(r == 0 and not m.calls, 'and so does a stray animation frame (it ends itself)')


def follow_tests(ctx):
    expect = ctx.expect
    # the model's own numbers: the spring table, the cap, the stagger
    mm = Machine()
    cs = lambda v, t: struct.unpack('<i', struct.pack('<I', mm.call(PSYMS['ly_spring'], a0=v & 0xffffffff, a1=t & 0xffffffff, count=50000)))[0]
    pts = [(100, 0), (100, 10), (100, 55), (100, 380), (100, 639), (100, 640), (100, 900), (-100, 380), (-100, 55), (48, 123), (116, 380), (300, 380), (-300, 380), (500, -20), (0, 100)]
    got = [cs(v, t) for v, t in pts]
    expect(got == [spring(v, t) for v, t in pts], f'ly_spring equals the model (damped spring table, linear between entries, cut at the cap) ({got})')
    expect(got[0] == 100 and got[5] == got[6] == 0 and got[3] < 0 and -4 <= got[3] and got[11] == -O['LY_OVERSHOOT_MAX'] and got[12] == O['LY_OVERSHOOT_MAX'] and got[13] == 500,
           f'it starts at the offset, overshoots a few percent, is cut at {O["LY_OVERSHOOT_MAX"]} px (300 px at the dip would be -11), ends at 0, and a line not yet started keeps all of it')
    expect(min(TAB) == -39 and TAB[0] == 1024 and TAB[-1] == -1 and max(TAB[30:]) < 0 and 100 * min(TAB) // 1024 == -4, 'the table: peak overshoot 3.8 % of the distance, settled to -0.1 % at 640 ms')
    try:
        tab = [struct.unpack('<h', mm.u.mem_read(PSYMS['ly_tab'] + 2 * k, 2))[0] for k in range(65)]
        expect(tab == TAB, 'the payload\'s table is the one the model computes from the formula')
    except KeyError:
        expect(all(cs(1024, 10 * k) == max(TAB[k], -O['LY_OVERSHOOT_MAX']) for k in range(65)), 'the payload\'s table is the one the model computes from the formula (read through ly_spring)')
    got = [mm.call(PSYMS['ly_delay'], a0=i & 0xffffffff, a1=c & 0xffffffff, count=50000) for i, c in ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (9, 1), (0, 5), (4, 5), (5, 5), (6, 5), (7, 5), (30, 5))]
    expect(got == [delay(i, c) for i, c in ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (9, 1), (0, 5), (4, 5), (5, 5), (6, 5), (7, 5), (30, 5))] and got[:5] == [0, 50, 97, 141, 182] and got[6] == 0 and got[7] == 0 and got[8] == 50,
           f'the stagger: lines above the one before the target start at once, then 50 ms and each step 20/21 of the one before ({got})')
    got = [mm.call(PSYMS['ly_opacity'], a0=d & 0xffffffff, count=50000) for d in (0, 1, 2, 3, 4, 40, -1, -2, -3, -9)]
    expect(got == [255, 115, 82, 61, 46, 46, 115, 82, 61, 46] and got[:5] == list(OPACITY), f'opacity by distance: 1.0, 0.45, 0.32, 0.24, 0.18 ({got})')
    pts = [(y, r) for y in range(-150, 300, 7) for r in (1, 2, 3)] + [(-LINE_H // 2, 1), (VIEW_H - LINE_H // 2, 1), (VIEW_H - LINE_H // 2 - FADE, 1), (LINE_H // 2 - 1 + FADE - 3 * LINE_H, 3)]
    got = [mm.call(PSYMS['ly_edge'], a0=y & 0xffffffff, a1=r, count=50000) for y, r in pts]
    expect(got == [edge(y, r) for y, r in pts] and edge(ANCHOR, 3) == 255 and edge(-LINE_H // 2, 1) == 0 and edge(VIEW_H - LINE_H // 2, 1) == 0 and 0 < edge(-LINE_H // 2 + 10, 1) < 255,
           f'the edge factor: 0 with a row\'s centre on the top or bottom edge, 255 from {FADE} px in, linear between; it is the row nearest the edge that counts ({sum(0 < g < 255 for g in got)} of {len(got)} points in the ramp)')

    # one line on: every line keeps its place, then springs up, each starting a little after the one before; the model agrees at every frame
    m = LyMachine(SONG); m.init()
    mdl = Model(SONG, m.measure_fn); mdl.cur = 0; mdl.layout(m.clock)
    m.at(5); mdl.cur = 1; mdl.move(1, m.clock)
    expect(len(m.ly_timers()) == 1 and m.ly_timers()[0][1] == FRAME == 40 and len(m.timers) == 2, f'a new current line starts one {FRAME} ms animation timer')
    s = m.shown()
    expect(is_cur(s, 'Line one') and not is_cur(s, 'Line zero'), 'the highlight moves at once')
    expect(s['Line zero'][0] == ANCHOR and s['Line one'][0] == ANCHOR + PITCH, 'the first frame is where the lines were (continuous): line zero at the anchor, line one a pitch under it')
    expect(s == mdl.layout(m.clock), 'and equals the model')
    ys, y0s, r, prog = [], [], 8, {}
    for step in range(1, 40):
        r = m.frame(40)
        s = m.shown(); want = mdl.layout(m.clock)
        expect(s == want, f'frame {step} ({40 * step} ms): the lines are where the model puts them') if step % 4 == 1 or r == 0 else ctx.expect(s == want, f'frame {step}')
        ys.append(s['Line one'][0]); y0s.append(s['Line zero'][0])
        for k in ('Line zero', 'Line one', 'Line two', 'Line three'):
            if k in s and k not in prog and s[k][0] != want[k][0]: prog[k] = step
        if r == 0: break
    expect(r == 0 and len(ys) > 15, f'the timer ends itself (RET_OK) after {len(ys)} frames, once every line is at rest')
    # stagger: after 100 ms line zero (no delay) has moved on, line one (50 ms) less, line two (97 ms) hardly
    m = LyMachine(SONG); m.init(); m.at(5); base = {k: v[0] for k, v in m.shown().items()}
    m.frame(100); s = m.shown()
    moved = {k: base[k] - s[k][0] for k in ('Line zero', 'Line one', 'Line two')}
    expect(moved['Line zero'] > moved['Line one'] > moved['Line two'] >= 0 and moved['Line zero'] > 2, f'staggered: after 100 ms the lines have moved {moved} px (earlier lines first)')
    # overshoot: line one passes its anchor by a pixel or two (48 px of travel) and settles on it; never more than the cap
    lo, hi, ys, t = 999, -999, [], 0
    m = LyMachine(SONG); m.init(); m.at(5)
    for t in range(1, 60):
        m.frame(20); y = m.shown()['Line one'][0]; ys.append(y); lo = min(lo, y); hi = max(hi, y)
    expect(ANCHOR - 4 <= lo < ANCHOR and ys[-1] == ANCHOR and hi <= ANCHOR + PITCH, f'line one overshoots the anchor to y {lo} (cap {O["LY_OVERSHOOT_MAX"]} px) and settles at {ys[-1]}')
    # a wrapped (three-row) line moves further and overshoots more, still under the cap
    wl = [(0, 'x' * 60), (5, 'next one'), (9, 'last')]
    m = LyMachine(wl); m.init(); m.at(5); lo = 999
    for t in range(1, 80):
        m.frame(20); lo = min(lo, m.shown()['next one'][0])
    expect(ANCHOR - O['LY_OVERSHOOT_MAX'] <= lo < ANCHOR - 1, f'after a three-row line the next line dips to y {lo}: more than 1 px, within the cap')

    # a second move while the first runs: nothing jumps, and the model agrees on the way
    m = LyMachine(SONG); m.init(); mdl = Model(SONG, m.measure_fn); mdl.cur = 0; mdl.layout(m.clock)
    m.at(5); mdl.cur = 1; mdl.move(1, m.clock); m.frame(120); mdl.layout(m.clock)
    before = m.shown(); m.at(10); mdl.cur = 2
    after = m.shown()
    expect({k: v[0] for k, v in before.items() if k in after} == {k: v[0] for k, v in after.items() if k in before}, 'a new current line in mid-move: every line is on the same pixel as just before')
    mdl.move(2, m.clock)
    expect(after == mdl.layout(m.clock) and len(m.ly_timers()) == 1, 'the second move adds its distance to what each line still had (one timer)')
    for step in range(60):
        r = m.frame(40)
        if m.shown() != mdl.layout(m.clock): break
        if r == 0: break
    expect(r == 0 and m.shown() == mdl.layout(m.clock) and m.shown()['Line two'][0] == ANCHOR, 'and they settle together')

    # a seek of more than the snap distance jumps; above the current line the lines are laid out too
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000)
    t = len(m.timers)
    m.at(40)   # line eight: seven lines on
    s = m.shown()
    expect(s['Line eight'][0] == ANCHOR and s['Line seven'][0] == ANCHOR - PITCH and s['Line six'][0] == ANCHOR - 2 * PITCH and 'Line five' not in s and 'Line zero' not in s,
           f'lines above the current one: one pitch up each, and none beyond the view ({sorted(s.items(), key=lambda kv: kv[1][0])[:4]})')
    expect(s == expect_layout(SONG, 8, 0, m.measure_fn) and len(m.timers) == t, f'a seek of more than {SNAP} lines jumps (no animation)')
    m.at(45); expect(len(m.timers) == t + 1, 'one line on animates again')
    m.frame(10000)
    m.at(40); s = m.shown()
    expect(s['Line eight'][0] == ANCHOR - PITCH, 'one line back: the new current line starts where it was (a pitch above the anchor) and comes down to it')
    m.frame(10000); expect(m.shown()['Line eight'][0] == ANCHOR, 'and rests at the anchor')
    m.at(100); m.frame(10000); s = m.shown()
    expect(s['Line eleven'][0] == ANCHOR and 'Line zero' not in s and s == expect_layout(SONG, 11, 0, m.measure_fn), 'the last line is current at the anchor with nothing below it')
    # before the first line: nothing highlighted, line zero waits at the anchor, dimmed as the next line
    m = LyMachine([(3, 'Intro'), (9, 'Second'), (14, 'Third')]); m.init()
    s = m.shown()
    expect(s == expect_layout([(3, 'Intro'), (9, 'Second'), (14, 'Third')], -1, 0, m.measure_fn) and s['Intro'][2] == BOLD and s['Intro'][1] == OPACITY[1] and s['Intro'][0] == ANCHOR,
           'before the first line: no line is current, the first waits at the anchor at 0.45')
    expect(not any(m.dot_ops()) and not m.dtimers(), f'a first line under {DMIN} s in: no dots, the line waits at the anchor as before')
    m.at(3); expect(m.shown()['Intro'][1] == 255 and not m.ly_timers(), 'the first line becomes current without a scroll')
    m.at(9); expect(is_cur(m.shown(), 'Second'), 'a position equal to a line\'s time is that line')
    m.frame(10000)
    m.status = 1; m.play = 14; m.at(14); expect(not is_cur(m.shown(), 'Intro') and not is_cur(m.shown(), 'Second') and ('get_playtime',) not in m.calls, 'stopped (status 1): position 0, get_playtime is not asked (as the stock timer)')
    m.status = 2; m.play = -1; m.at(-1)
    expect(not is_cur(m.shown(), 'Intro'), 'a failed position (-1) changes nothing')
    m.at(14); expect(is_cur(m.shown(), 'Third'), 'and the next good one catches up')

    # a new song's lyrics: the state is cleared, nothing of the old lines stays
    m = LyMachine(SONG); m.init(); m.at(30); m.frame(10000)
    m.set_lines([(0, 'New one'), (4, 'New two')]); m.at(1)
    s = m.shown()
    expect(set(s) == {'New one', 'New two'} and s == expect_layout([(0, 'New one'), (4, 'New two')], 0, 0, m.measure_fn), f'new lyrics replace the old lines at once ({sorted(s)})')
    m = LyMachine([]); m.init(); m.play = 52; m.tick(); expect(not m.shown(), 'no lyrics yet: nothing shown')
    t = len(m.timers); m.set_lines(SONG); m.at(52)
    expect(m.shown() == expect_layout(SONG, 10, 0, m.measure_fn) and len(m.timers) == t, 'late lyrics: the current line is at the anchor at once, no animation')
    m = LyMachine(SONG); m.init(); m.at(5); m.set_lines([(0, 'A'), (3, 'B')]); m.at(0); m.frame(40)
    expect(m.shown()['A'][0] == ANCHOR, 'a new song while the old move runs: the new first line is not pushed by the old offsets')

    # no animation timer: the lines jump
    m = LyMachine(SONG); m.init(); m.timer_fail = True; m.at(5)
    expect(m.shown() == expect_layout(SONG, 1, 0, m.measure_fn), 'the animation timer is refused: the lines jump to their place')
    # the timer goes with the page
    m = LyMachine(SONG); m.init(); m.at(5); m.calls = []
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(sum(c[0] == 'timer_remove' for c in m.calls) == 2, 'the page destroyed mid-animation removes both timers')
    m = LyMachine(SONG); m.init(); rows = m.children[m.src_w]; m.set_lines(SONG[:3]); m.calls = []; m.tick()
    expect(not any(c[0] == 'widget_get_text' and c[1] in rows for c in m.calls), 'rows that stock destroyed are not read')


def overflow_tests(ctx):
    """Stock widget_get_text_utf8 ignores its size for a wide text and a lyric line over the 256 byte stack buffer rebooted the player: m1_text_utf8 (patch/common.c) encodes the wide text bounded."""
    expect = ctx.expect
    def want(t, size):
        """The longest prefix of t's UTF-8 that is whole characters and leaves room for the NUL."""
        out = ''
        for c in t:
            if len((out + c).encode('utf-8')) >= size: break
            out += c
        return out
    m = LyMachine(); h = m.widget('probe_text')
    def run_(text=None, size=256, cps=None, pad=8):
        """m1_text_utf8 into a buffer of `size` bytes among 0xAA canaries: (result, the buffer's string, canaries intact)."""
        if text is not None: m.texts[h] = as_read(text)
        if cps is not None: m.wide[h] = cps
        buf = m.alloc(size + 2 * pad); m.u.mem_write(buf, b'\xaa' * (size + 2 * pad))
        r = m.call(PSYMS['m1_text_utf8'], h, buf + pad, a2=size, count=200000)
        raw = bytes(m.u.mem_read(buf, size + 2 * pad)); body = raw[pad:pad + size]
        z = body.find(b'\0')
        return (r if r < 1 << 31 else r - (1 << 32)), (body[:z] if z >= 0 else None), raw[:pad] + raw[pad + size:] == b'\xaa' * (2 * pad)
    cases = [('x' * 700, 256), ('x' * 255, 256), ('x' * 256, 256), ('a' + '我' * 300, 256), ('ab' + '😀' * 100, 256), ('é' * 300, 256), ('', 256), ('hello', 3), ('歌歌', 3), ('歌歌', 4), ('歌歌', 7), ('歌歌', 6), ('x', 1)]
    for text, size in cases:
        r, got, safe = run_(text, size)
        w = want(text, size)
        expect(r == len(text.encode('utf-8')) and got == w.encode('utf-8') and safe,
               f'{len(text.encode("utf-8"))} bytes into {size}: needs {len(text.encode("utf-8"))}, the buffer holds {len(w.encode("utf-8"))} bytes whole characters, NUL terminated, nothing beyond it written (got {r}, {None if got is None else len(got)}, safe {safe})')
    # the text fitted when the result is below size; the long lines are cut at a character, not in one
    r, got, safe = run_('a' + '我' * 300)
    expect(len(got) == 253 and got.decode('utf-8') == 'a' + '我' * 84 and safe, 'a CJK line cut in the middle of a character (253 of the 255 usable bytes) ends on the one before')
    r, got, safe = run_('ab' + '😀' * 100)
    expect(len(got) == 254 and got.decode('utf-8') == 'ab' + '😀' * 63 and safe, 'an emoji line (4 bytes each) too')
    # a size of 0 writes nothing; a widget without a text is -1 and an empty buffer; U+FFFD for what is not a character
    buf = m.alloc(8); m.u.mem_write(buf, b'\xaa' * 8)
    expect((m.call(PSYMS['m1_text_utf8'], h, buf, a2=0) == 0xffffffff) and bytes(m.u.mem_read(buf, 8)) == b'\xaa' * 8, 'a size of 0: -1, nothing written')
    m.u.mem_write(buf, b'\xaa' * 8)
    expect(m.call(PSYMS['m1_text_utf8'], m.alloc(8), buf, a2=8) == 0xffffffff and bytes(m.u.mem_read(buf, 2)) == b'\0\xaa', 'a widget without text: -1, an empty string')
    m.u.mem_write(buf, b'\xaa' * 8)
    expect(m.call(PSYMS['m1_text_utf8'], 0, buf, a2=8) == 0xffffffff and bytes(m.u.mem_read(buf, 2)) == b'\0\xaa', 'no widget: -1, an empty string')
    r, got, safe = run_(cps=[0x41, 0xd800, 0x110000, 0xffffffff, 0x10ffff], size=64)
    expect(got == b'A' + '\ufffd'.encode() * 3 + '\U0010ffff'.encode() and r == 1 + 9 + 4 and safe, 'a surrogate or a code point beyond U+10FFFF is U+FFFD')
    # the lyric rows: a line over the buffer is cut where the page reads it (ly_text), never written past, and what is set on the labels is whole characters
    for kind, text in (('ASCII', 'x' * 700), ('CJK', 'a' + '我' * 300), ('emoji', 'ab' + '😀' * 100), ('348 bytes (the user\'s album)', 'la ' * 116)):
        lines = [(0, 'first'), (1, text), (2, 'last')]
        m2 = LyMachine(lines, measure=lambda s: 10 * len(s)); sets = []
        m2.init(); pool = m2.pool(); sets += [c[2] for c in m2.calls if c[0] == 'widget_set_text_utf8' and c[1] in pool]
        for t in (1, 2, 0, 1): m2.at(t); sets += [c[2] for c in m2.calls if c[0] == 'widget_set_text_utf8' and c[1] in pool]
        try:
            decoded = [s.encode('latin-1').decode('utf-8') for s in sets]
        except UnicodeDecodeError:
            decoded = None
        longest = max(len(s) for s in sets)
        flat = lambda x: x.replace(' ', '').replace('\n', '')
        expect(decoded is not None and longest <= O['LY_BUF'] + MAXR + 2 and any('\n' in d for d in decoded) and all(flat(want(text, O['LY_BUF'])).startswith(flat(d.removesuffix(MARK))) or d in ('first', 'last', '') or d[0] == '-' for d in decoded),
               f'{kind}: a line of {len(text.encode("utf-8"))} bytes is set on the labels cut on a character, from the first {O["LY_BUF"] - 1} bytes and with its breaks and the mark at most {O["LY_BUF"] + MAXR + 2} bytes ({longest} bytes)')


def touch_tests(ctx):
    expect = ctx.expect
    D, MV, UP, AB = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
    # the listeners: four events on np_lyrics, nothing grabbed, no RET_STOP
    m = LyMachine(SONG); m.init()
    on = [(c[2], c[3]) for c in m.calls if c[0] == 'widget_on' and c[1] == m.box]
    expect(on == [(D, PSYMS['ly_on_touch']), (MV, PSYMS['ly_on_touch']), (UP, PSYMS['ly_on_touch']), (AB, PSYMS['ly_on_touch'])], f'np_lyrics listens to DOWN, MOVE, UP and ABORT ({on})')
    expect(all(m.props.get((h, 'sensitive')) == 0 for h in m.children[m.box]), 'its labels stay insensitive: the touch lands on np_lyrics')
    r = [m.down(100, 90), m.move(100, 70), m.move(100, 60), m.up(100, 60)]
    expect(r == [0, 0, 0, 0] and not any(c[0] in ('widget_grab', 'widget_ungrab') for c in m.calls), 'every handler answers RET_OK and nothing is grabbed (the slide view and the window manager see every event)')

    # tap on a line: the player seeks to its lrc_time and the lines move there
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000)        # line one current; line two at ANCHOR + PITCH
    y2 = m.shown()['Line two'][0]
    n_timers = len(m.ly_timers())
    m.down(50, y2 + 10); m.up(50, y2 + 10)
    expect(m.seeks == [10], f'a tap on line two seeks to its time ({m.seeks})')
    s = m.shown()
    expect(is_cur(s, 'Line two') and len(m.ly_timers()) == n_timers + 1 and s['Line two'][0] == y2, 'the highlight is there at once, the lines begin their move from where they were')
    m.frame(10000); expect(m.shown()['Line two'][0] == ANCHOR, 'and the tapped line rests at the anchor')
    # the player has not caught up (it still reads the old position): the lines are not pulled back before LY_HOLD_MS, and are after
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); m.seek_moves = False
    y2 = m.shown()['Line two'][0]; m.down(50, y2 + 10); m.up(50, y2 + 10); m.clock += 400; m.tick(count=8000000)
    expect(is_cur(m.shown(), 'Line two'), f'for {O["LY_HOLD_MS"]} ms the old player position does not move the lines back')
    m.clock += 900; m.tick(count=8000000)
    expect(is_cur(m.shown(), 'Line one'), 'after it the lines follow the player again')
    # a tap between two lines, a tap that moved, a stopped player, a tap in the first 200 ms of a move
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000)
    y2 = m.shown()['Line two'][0]
    m.down(50, y2 + LINE_H + GAP // 2 + 1 + GAP // 2); m.up(50, y2 + LINE_H + GAP // 2 + 1 + GAP // 2)   # one px past line two's half gap, above line three's
    expect(m.seeks == [15], 'a tap 1 px into line three\'s half gap above it goes to line three')
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); y2 = m.shown()['Line two'][0]
    m.down(50, y2 + 5); m.move(50, y2 + 5 + 9); m.up(50, y2 + 5 + 9)
    expect(m.seeks == [10], 'a touch that moves less than 10 px is a tap')
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); y2 = m.shown()['Line two'][0]
    m.down(50, y2 + 5); m.move(50, y2 + 5 + 12); m.up(50, y2 + 5 + 12)
    expect(m.seeks == [], 'a touch that moves 10 px or more is a drag, not a tap')
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); m.status = 1; y2 = m.shown()['Line two'][0]
    m.down(50, y2 + 5); m.up(50, y2 + 5)
    expect(m.seeks == [] and is_cur(m.shown(), 'Line one'), 'a stopped player: a tap seeks nothing and moves nothing')
    m = LyMachine(SONG); m.init(); m.at(5)           # a move has just started
    y2 = m.shown()['Line two'][0]
    m.clock += 100; m.down(50, y2 + 5); m.up(50, y2 + 5)
    expect(m.seeks == [], 'a touch within 200 ms of a move that started is no tap (gestures.md: it catches the move, it presses nothing)')
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); y2 = m.shown()['Line two'][0]
    m.at(10); m.clock += 250
    m.tick(count=8000000); s = m.shown(); y3 = s['Line three'][0]
    m.down(50, y3 + 5); m.up(50, y3 + 5)
    expect(m.seeks == [15], 'more than 200 ms after a move started (its spring still settling) a tap works')

    # a sideways swipe is the slide view's: no scroll, no tap
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000); y2 = m.shown()['Line two'][0]
    before = m.shown()
    m.down(100, y2 + 5); m.move(116, y2 + 8); m.move(150, y2 + 40); m.up(170, y2 + 45)
    expect(m.shown() == before and m.seeks == [], 'a swipe that goes sideways first never scrolls the lyrics and is no tap (the slide view turns the page)')
    m.down(100, y2 + 5); m.move(100, y2 - 30); m.ptr(AB, 100, y2 - 30)
    m.move(100, y2 - 60); m.up(100, y2 - 60)
    expect(m.shown()['Line two'][0] == y2 and m.seeks == [], 'after an ABORT (the slide view took the touch) the later events do nothing')

    # drag: the lines follow the finger (after the first 10 px), the other lines are 0.6, the current one stays 1.0
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000)
    base = {k: v[0] for k, v in m.shown().items()}
    m.down(100, 150); m.move(100, 138)
    expect({k: v[0] for k, v in m.shown().items()} == base, 'the first 10 px of a drag decide it (no scroll yet)')
    m.move(100, 120)
    s = m.shown()
    expect(all(s[k][0] == base[k] - 18 for k in s if k in base) and is_cur(s, 'Line one') and all(v[1] == fade(BROWSE, v[0], 1) for k, v in s.items() if k != 'Line one'),
           f'a drag of 18 px more moves every line 18 px; scrolled, the other lines are all at 0.6 (times the edge factor) ({[(k, v[0], v[1]) for k, v in sorted(s.items())][:3]})')
    m.move(100, 60)
    s = m.shown()
    expect(s['Line one'][0] == base['Line one'] - 78 and is_cur(s, 'Line one'), 'the lines keep following (the anchored line changes when half a pitch has passed; the layout is continuous)')
    m.up(100, 60)
    expect(m.seeks == [], 'a drag is no tap')
    # the song goes on while the user looks: the highlight moves, the lines stay
    shown = {k: v[0] for k, v in m.shown().items()}
    m.at(10)
    s = m.shown()
    expect(is_cur(s, 'Line two') and not is_cur(s, 'Line one') and {k: v[0] for k, v in s.items() if k in shown} == {k: shown[k] for k in s if k in shown},
           'the song moves on: the highlight follows it, the lines under the finger stay')
    # three seconds without a touch: back to the current line with the same moves
    m.clock += 2400; m.at(10); y_hold = {k: v[0] for k, v in m.shown().items()}
    expect({k: y_hold[k] for k in shown if k in y_hold} == {k: shown[k] for k in shown if k in y_hold}, 'before the 3 s are over the lines stay')
    m.clock += 700; t = len(m.timers); m.at(10)
    expect(len(m.timers) == t + 1 and m.shown()['Line two'][0] == shown['Line two'], f'after {O["LY_IDLE_MS"]} ms without a touch the lines start back (a move that begins where they are)')
    m.frame(10000); s = m.shown()
    expect(s['Line two'][0] == ANCHOR and s == expect_layout(SONG, 2, 0, m.measure_fn), 'and rest with the current line at the anchor, the falloff back')
    # a touch while the user is scrolling keeps the lines there
    m = LyMachine(SONG); m.init(); m.at(5); m.frame(10000)
    m.down(100, 150); m.move(100, 120); m.move(100, 100); m.up(100, 100)
    pos = {k: v[0] for k, v in m.shown().items()}
    m.clock += 2000; m.down(100, 150); m.ptr(AB, 100, 150)       # a touch the slide view takes away still counts as a touch
    m.clock += 2000; m.at(5)
    expect({k: v[0] for k, v in m.shown().items() if k in pos} == pos, 'a touch restarts the 3 s: 4 s after the drag, 2 s after the touch, the lines still stay')
    m.clock += 1100; t = len(m.timers); m.at(5)
    expect(len(m.timers) == t + 1, 'and 3 s after it they start back')
    # the bounds: the first line stops at the anchor, the last too
    m = LyMachine(SONG); m.init()
    m.down(100, 100); m.move(100, 120); m.move(100, 250)
    expect(m.shown()['Line zero'][0] == ANCHOR, 'dragged down past the start the first line stops at the anchor')
    m.up(100, 250)
    m = LyMachine(SONG); m.init(); m.at(100); m.frame(10000)
    m.down(100, 250); m.move(100, 230); m.move(100, 20)
    expect(m.shown()['Line eleven'][0] == ANCHOR, 'dragged up past the end the last line stops at the anchor')
    # no listeners without widget_on (a refusal): the lines still follow the song
    m = LyMachine(SONG); m.widget_on_fail = {D, MV, UP, AB}; m.init()
    expect(len(m.shown()) == 4, 'widget_on refused: the lyrics show and follow the song, only without touch')
    # a stray event after the page is gone
    m = LyMachine(SONG); m.init(); m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    m.down(100, 100)
    expect(not m.calls or all(c[0] != 'widget_move' for c in m.calls), 'a touch event after the page is gone does nothing')


def wrap_tests(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    from awtk_text import Ttf, StbText
    fonts = {BOLD: Ttf(os.path.join(raw, 'fonts', 'lyrics.ttf')), CJKF: Ttf(os.path.join(raw, 'fonts', 'default.ttf'))}
    real = lambda s: StbText(fonts[face(s)], O['LY_FONT']).layout(s)[1] if s else 0   # in the face the payload picks
    # the row estimate: 10 px a character
    for n, rows in ((1, 1), (26, 1), (27, 2), (50, 2), (51, 3), (75, 3), (76, 4), (125, 5), (126, 6), (150, 6), (151, 6), (200, 6)):
        text = 'x' * n
        lines = [(0, 'a'), (1, text), (2, 'b')]
        m = LyMachine(lines); m.init(); m.at(1); m.frame(10000)
        s = m.shown()
        lab = next(m.label_text(h) for h in m.pool() if h in m.texts and m.source_of(m.label_text(h)) == text)
        expect(s[text][3] == rows * LINE_H == expect_layout(lines, 1, 0, m.measure_fn)[text][3] and s[text][0] == anchor(rows) and ('b' not in s if rows == MAXR else s['b'][0] == s[text][0] + rows * LINE_H + GAP),
               f'{n} chars = {n * 10} px: {rows} row(s) from y {anchor(rows)}, the next line {rows * LINE_H + GAP} px down{" (out of the view)" if rows == MAXR else ""} ({s[text]})')
        expect(lab == '\n'.join(break_rows(text, m.measure_fn)) and lab.endswith(MARK) == (n > 150) and (n <= 150 or lab == '\n'.join(['x' * 25] * 5 + ['x' * 24 + MARK])),
               f'{n} chars: the label text is the model\'s rows, {"cut with the mark after 149 characters" if n > 150 else "whole, no mark"}')
    # the final-glyph clip (report: "time is a valueble thing") and every other way a row can overflow: the label text the page sets is drawn the way stock's wrap does it
    # (stock_rows: explicit newlines, the overflow check, the last character stays) and has to fit the rows the page gave the line, each row the content width (W less 2 x 2 px)
    sentence = 'Everybody knows that the time is a valuable thing so we all keep watching the clock '
    cases = [('time is a valueble thing', None), ('Time is a valueble thing', ['Time is a valueble', 'thing']), ('Time is a valuable thing', ['Time is a valuable', 'thing']),
             ('Unforgettable me Time is a valuable thing', None), ('time is a beautiful thing', None), ('Supercalifragilisticexpialidocious', None),
             ('这是一个没有空格的很长的中文歌词用来测试换行的效果', None), (sentence * 3, None), ('word ' * 60, None), ('a' * 26, None)]
    for text, rows_want in cases:
        m = LyMachine([(0, 'a'), (1, text), (2, 'b')], measure=real); m.init(); m.at(1); m.frame(10000)
        lab = next(h for h in m.pool() if h in m.texts and m.source_of(m.label_text(h)) == text)
        got, alloc = stock_rows(m.label_text(lab), real), m.props[(lab, 'h')] // LINE_H
        fits = real(text) <= FIT
        expect(len(got) <= alloc == len(break_rows(text, real)) <= MAXR and got == break_rows(text, real) and all(real(r) <= FIT for r in got) and (rows_want is None or got == rows_want) and (alloc > 1 or fits),
               f'{text[:28]!r} ({real(text)} px): stock draws {len(got)} row(s) of {[real(r) for r in got]} px in the {alloc} allocated, none beyond {FIT} px ({got})')
        if text == 'time is a valueble thing': expect(real(text) <= FIT and alloc == 1, 'the 260 px form fits one row and is given as it is')
    expect(real('time is a beautiful thing') > FIT and real('time is a beautiful thing') <= W, 'time is a beautiful thing: 264 px, inside the label but over the content width, takes two rows')
    # a line that measures exactly the content width stays one row (its last character is stock's to keep), one pixel more breaks it
    for n, rows in ((26, 1), (27, 2)):
        t = 'x' * n
        m = LyMachine([(0, t)], measure=lambda u: 10 * len(u)); m.init(); m.at(0)
        expect(m.label_text(m.pool()[0]) == t.replace('x' * 25, 'x' * 25 + '\n') if rows == 2 else m.label_text(m.pool()[0]) == t, f'{n * 10} px: {rows} row(s), the label text {m.label_text(m.pool()[0])!r}')
    # a full buffer (255 bytes) of words: MAXR rows, cut there with the mark, every row inside the content width
    full = ('word ' * 60)[:255]
    m = LyMachine([(0, full)], measure=real); m.init(); m.at(0)
    got = stock_rows(m.label_text(m.pool()[0]), real)
    expect(len(got) == MAXR and m.shown()[full][3] == MAXR * LINE_H and all(real(r) <= FIT for r in got) and got[-1].endswith('word' + MARK) and got == break_rows(full, real),
           f'a 255 byte line is cut at {MAXR} rows, each inside the content width, the last ending in the mark ({got[-1]!r})')
    # a measured line keeps its height: the probe measures once
    m = LyMachine(SONG); m.init()
    m.at(5); m.frame(10000); m.at(0); m.frame(10000)
    expect(m.names().count('widget_measure_text') == 0, 'a line is measured once, not on every layout')
    # a measure that comes back 0 for text is not kept: the line is one row for now and measured again by the next ticks, the layout redone when it changes
    text, fails = 'x' * 40, [True]
    def flaky(s): return 0 if fails[0] and len(s) == 40 else 10 * len(s)
    lines = [(0, 'a'), (1, text), (2, 'b')]
    m = LyMachine(lines, measure=flaky); m.init(); m.at(1)
    expect(m.shown()[text][3] == LINE_H, 'a failed measure leaves the line one row for now')
    fails[0] = False
    for _ in range(3): m.at(1)
    m.frame(10000)
    expect(m.shown() == expect_layout(lines, 1, 0, lambda s: 10 * len(s)), f'the next ticks measure it again and the layout takes its two rows ({m.shown()} vs {expect_layout(lines, 1, 0, lambda s: 10 * len(s))})')
    m.at(1); m.at(1)
    expect(m.names().count('widget_measure_text') == 0, 'once measured the line is kept: no more measures')
    # a long song whose first layouts measure nothing: the budget counts ticks, not calls, so every line (line 10 too) ends up with its modelled rows
    long_song = [(5 * k, f'{k:02d}' + 'x' * 38) for k in range(32)]
    fails = [True]
    m = LyMachine(long_song, measure=lambda s: 0 if fails[0] else 10 * len(s)); m.init(); m.at(50); m.at(50)
    fails[0] = False
    for _ in range(3): m.at(50)
    m.frame(10000)
    model = expect_layout(long_song, 10, 0, lambda s: 10 * len(s))
    expect(m.shown() == model and model[long_song[10][1]][3] == 2 * LINE_H, 'a song of 32 lines that could not be measured at first: the next ticks give every line its modelled rows')
    m.at(55); m.frame(10000); m.at(50); m.frame(10000)
    expect(m.shown() == model and m.names().count('widget_measure_text') == 0, 'and they stay (line 10 current again), measured once')
    m = LyMachine(lines, measure=lambda s: 0); m.init()
    for _ in range(40): m.at(1)
    m.at(1)
    expect(m.names().count('widget_measure_text') == 0 and m.shown()[text][3] == LINE_H, f'a probe that never measures is tried for at most {O["LY_MISS_MAX"]} tick layouts, then the lines stay one row')
    # real text in the real font
    latin = (0, 'I got a feeling that tonight is going to be the night that I will remember all my life, oh yeah')
    cjk = (1, '我想要有一天能够和你一起走遍这个世界上所有美丽的地方看遍所有的风景再回到这里')
    for long_line, kind in ((latin, 'Latin'), (cjk, 'CJK')):
        lines = [(0, long_line[1]), (1, 'Hello')]
        m = LyMachine(lines, measure=real); m.init(); m.at(0)
        s = m.shown()
        r = rows_of(long_line[1], real)
        expect(s[long_line[1]][3] // LINE_H == r >= 2 and s['Hello'][3] == LINE_H and s[long_line[1]][0] == anchor(r) and s['Hello'][0] == anchor(r) + r * LINE_H + GAP,
               f'a long {kind} line takes {r} rows ({real(long_line[1])} px of {W}) and pushes the next line down by its height')
        expect(s == expect_layout(lines, 0, 0, real), f'{kind}: the layout is the model\'s')
    # the page opened mid-song (a 1.3.0 report, Wake Up): the hook's tick lays out the lines round the playing one before the window resolves the probe's style; they
    # are measured by the next tick in the lyrics font, not kept from a measure in the label default style (18 px: "Still knee-deep..." one row, "in the" its last words)
    wake = [(60, 'Come on'), (66, "Standing with the fury that they had in '66"), (70, "And like E-Double, I'm mad"), (71, "Still knee-deep in the system's shit"),
            (73, 'Hoover, he was a body remover'), (76, 'I give a shout out to the living dead')]
    m = LyMachine(wake, measure=real); m.play = 70; m.init()
    expect(not any(c[0] == 'widget_measure_text' for c in m.calls), 'opened mid-song: the hook\'s tick measures nothing')
    m.at(70); m.frame(10000); s = m.shown()
    knee = wake[3][1]
    expect(s == expect_layout(wake, 2, 0, real) and s[knee][3] == 2 * LINE_H and s[wake[1][1]][3] == rows_of(wake[1][1], real) * LINE_H >= 2 * LINE_H,
           f'the next tick measures in the lyrics font: "{knee}" {real(knee)} px takes 2 rows, the \'66 line {rows_of(wake[1][1], real)} ({ {k: v[3] // LINE_H for k, v in s.items()} })')
    # a face change while the window opens (stage 2: widget_use_style only marks the probe) is measured in the new face, resolved by the probe itself
    m = LyMachine([(0, 'Hello there'), (1, '你好，世界'), (2, 'Back to Latin')]); m.init()
    meas = [c[2] for c in m.at(0) if c[0] == 'widget_measure_text']
    expect(meas == [BOLD, CJKF, BOLD], f'during the open animation each measure is in the line\'s own resolved face ({meas})')
    m = LyMachine([(0, 'Hello there'), (1, '你好，世界')]); m.init(open_after=False)
    for _ in range(3): m.at(0)
    expect(not any(c[0] == 'widget_measure_text' for c in m.calls) and m.shown()['你好，世界'][3] == LINE_H, 'a window that has not resolved its styles is not measured: the lines stay one row')
    m.stage(2); m.at(0)
    expect([c[2] for c in m.calls if c[0] == 'widget_measure_text'] == [BOLD, CJKF], 'and the first tick after it measures them')
    # the label wraps: line wrap and word wrap are asked for on every label
    expect(sum(c[0] == 'label_set_line_wrap' and c[2] == 1 for c in m.calls) == 0 and sum(c[0] == 'label_set_line_wrap' for c in m.calls) == 0, 'the wrap flags are set at the start, not on every layout')
    m = LyMachine(SONG); m.init()
    expect(sum(c[0] == 'label_set_line_wrap' and c[2] == 1 for c in m.calls) == POOL + 1 and sum(c[0] == 'widget_set_prop_bool' and c[2] == 'word_wrap' and c[3] == 1 for c in m.calls) == POOL + 1,
           'every label wraps (line_wrap and word_wrap)')
    # leading blanks are not drawn (stock keeps what follows the time stamp's ']', so "[00:12.34] text" is " text"): the line is measured, broken and set without them;
    # blanks inside and at the end stay
    one, two = 'Be what you want', 'one two three four five six seven eight'
    for lead in (' ', '   ', '\t', '\xa0', '\u2003', '\u200b', '\u202f', '\u3000', '\ufeff', ' \u3000\t\xa0 '):
        for body in (one, two, '你好，世界', 'Keep  inner '):
            m = LyMachine([(0, 'a'), (1, lead + body), (2, 'b')]); measured = []
            probe = lambda: [c[2].encode('latin-1').decode('utf-8') for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] not in m.pool()]
            m.init(); measured += probe(); m.at(1); measured += probe(); m.frame(10000)   # (a frame clears the calls: the measures are taken before it)
            labs =[m.label_text(h) for h in m.pool() if h in m.texts and m.props.get((h, 'visible'))]
            want_text = '\n'.join(break_rows(body, m.measure_fn))
            expect(want_text in labs and all(t in ('a', 'b', want_text) for t in labs) and (body != two or '\n' in want_text),
                   f'{lead + body!r}: the label text is {want_text!r} ({labs})')
            # (' ' alone is ly_break's measure of a space's width, made for a line of more than one row)
            expect(body in measured and lead + body not in measured and not any(s != ' ' and s.startswith(tuple(lead)) for s in measured),
                   f'{lead + body!r}: the line is measured without its leading blanks ({measured})')
    m = LyMachine([(0, 'a'), (1, ' \u3000 '), (2, 'b')]); m.init(); m.at(1); m.frame(10000)
    expect(all(m.label_text(h) in ('a', 'b', '') for h in m.pool() if h in m.texts and m.props.get((h, 'visible'))), 'a line of blanks only is an empty line')


def tall_tests(ctx):
    """Lines of more than three rows (a 1.3.2 report, The Lie Eternal from LRCLIB: several sentences under one time stamp were cut after three rows): up to MAXR rows are
    shown and the anchored line sits higher (anchor), in the layout, the moves and the drag."""
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    from awtk_text import Ttf, StbText
    fonts = {BOLD: Ttf(os.path.join(raw, 'fonts', 'lyrics.ttf')), CJKF: Ttf(os.path.join(raw, 'fonts', 'default.ttf'))}
    real = lambda s: StbText(fonts[face(s)], O['LY_FONT']).layout(s)[1] if s else 0
    lie = [(18, "I'm here tonight, the passion of your life."),
           (24, 'To up the stakes, you will be like me in time. So let me come inside, your heart, your mind.'),
           (40, 'Hell, I dare you to see yourself in a different light, where my hungry desire finds oblivion in your embrace'),
           (58, 'All mistakes forgiven in your embrace.'),
           (65, "I'm here, I'm now, arrived I fell in to your love, I fell in to your lie eternal.")]
    flat = lambda x: x.replace(' ', '').replace('\n', '')
    for pos, i, rows in ((24, 1, 4), (40, 2, 6), (65, 4, 4)):
        m = LyMachine(lie, measure=real); m.init(); m.at(pos); m.frame(10000)
        text = lie[i][1]; s = m.shown()
        lab = next(m.label_text(h) for h in m.pool() if h in m.texts and m.props.get((h, 'visible')) and m.source_of(m.label_text(h)) == text)
        got = stock_rows(lab, real)
        expect(flat(lab) == flat(text) and MARK not in lab and len(got) == rows == s[text][3] // LINE_H and all(real(r) <= FIT for r in got),
               f'{text[:24]!r}... ({real(text)} px): the whole line in {rows} rows, none beyond {FIT} px, nothing cut ({got})')
        expect(s[text][0] == anchor(rows) and s[text][1] == 255 and s[text][0] + rows * LINE_H <= VIEW_H - AROOM and s == expect_layout(lie, i, 0, real),
               f'it is current from y {s[text][0]} to {s[text][0] + rows * LINE_H}, whole in the view, opacity 1.0; the layout is the model\'s')
        if rows < MAXR and i + 1 < len(lie):
            nxt = s[lie[i + 1][1]]
            expect(nxt[0] == anchor(rows) + rows * LINE_H + GAP and nxt[0] + LINE_H <= VIEW_H - AROOM and nxt[1] > 0, f'the next line\'s first row is in the view under it (y {nxt[0]})')
    # the moves between lines of different anchors: every line starts where it was and the model agrees at every frame
    song = [(0, 'Short a'), (5, 'x' * 100), (10, 'Short b'), (15, 'x' * 140), (20, 'y' * 110), (25, 'Short c')]
    rws = [rows_of(t, lambda u: 10 * len(u)) for _, t in song]
    expect(rws == [1, 4, 1, 6, 5, 1], f'a song of 1, 4, 1, 6, 5 and 1 rows ({rws})')
    m = LyMachine(song); m.init(); mdl = Model(song, m.measure_fn); mdl.cur = 0; m.at(0); mdl.layout(m.clock)
    okm, okc, rest = True, True, []
    for k in list(range(1, len(song))) + [4, 3, 2, 1, 0]:
        before = m.shown(); m.at(song[k][0]); mdl.cur = k; mdl.move(k, m.clock)
        after = m.shown()
        okc = okc and {a: v[0] for a, v in before.items() if a in after} == {a: v[0] for a, v in after.items() if a in before}
        okm = okm and after == mdl.layout(m.clock)
        for _ in range(60):
            r = m.frame(40)
            okm = okm and m.shown() == mdl.layout(m.clock)
            if r == 0: break
        rest.append(m.shown()[song[k][1]][0])
    expect(okc, 'a new current line: at the move\'s start every line is on the pixel it was on, whatever the two lines\' anchors')
    expect(okm, 'and the moves are the model\'s at every frame (the distance has the two anchors\' difference)')
    expect(rest == [anchor(rws[k]) for k in list(range(1, len(song))) + [4, 3, 2, 1, 0]], f'each current line rests at its own anchor ({rest})')
    # the longest moves that do not snap (SNAP lines of MAXR rows, both ways): a line that was on the screen is still there, on its pixel, when the move starts and
    # leaves by scrolling (the layout's bounds, OFF_MAX, hold the whole distance)
    far = SNAP * (MAXR * LINE_H + GAP) + ANCHOR - AMIN
    expect(OFF_MAX >= far and OFF_MAX <= 4 * VIEW_H, f'the layout keeps lines up to {OFF_MAX} px outside the view: a move of {SNAP} lines of {MAXR} rows is {far} px, an offset is cut at {4 * VIEW_H}')
    six = [(5 * k, chr(97 + k) * 140) for k in range(2 * SNAP + 1)]
    for a, b in [(0, n) for n in range(1, SNAP + 1)] + [(2 * SNAP, 2 * SNAP - n) for n in range(1, SNAP + 1)] + [(1, 0), (SNAP, 1)]:
        m = LyMachine(six); m.init(); m.at(six[a][0]); m.frame(10000)
        mdl = Model(six, m.measure_fn); mdl.cur = mdl.base = a; mdl.layout(m.clock)
        before = m.shown(); m.at(six[b][0]); mdl.cur = b; mdl.move(b, m.clock); after = m.shown()
        ok = set(before) <= set(after) and all(after[t][0] == before[t][0] for t in before) and after == mdl.layout(m.clock)
        # the old current line by its own arithmetic (not the layout's bounds): its spring from where it was to its new place, shown while that touches the view
        t0, end, ys = m.clock, anchor(MAXR) + (a - b) * (MAXR * LINE_H + GAP), []
        for _ in range(60):
            r = m.frame(40); s = m.shown()
            ok = ok and s == mdl.layout(m.clock)
            y = end + spring(before[six[a][1]][0] - end, m.clock - t0 - delay(a, b))
            vis = y + MAXR * LINE_H > 0 and y < VIEW_H and fade(OPACITY[min(abs(a - b), 4)], y, MAXR) > 0
            ok = ok and (six[a][1] in s) == vis and (not vis or s[six[a][1]][0] == y)
            if vis: ys.append(y)
            if r == 0: break
        expect(ok and ys and m.shown()[six[b][1]][0] == anchor(MAXR),
               f'six-row lines, line {a} to line {b} ({abs(b - a) * (MAXR * LINE_H + GAP)} px): the old current line stays on its pixel at the start and scrolls out along its spring ({len(ys)} frames in the view), the model\'s at every frame')
    # a drag across them: every line follows the finger by exactly its distance, also when the anchored line changes to one of another anchor
    m = LyMachine(song); m.init(); m.at(5); m.frame(10000)
    m.down(100, 230); m.move(100, 215); prev, y, ok, seen = m.shown(), 215, True, set()
    while y > 20:
        y -= 7; m.move(100, y); s = m.shown()
        ok = ok and all(s[a][0] == prev[a][0] - 7 for a in s if a in prev)
        seen |= set(s); prev = s
    m.up(100, y)
    expect(ok and song[3][1] in seen, 'dragged up through the four-row and the six-row line: every line moves 7 px a step, no jump')
    m.down(100, 20); m.move(100, 35); prev, y = m.shown(), 35
    while y < 230:
        y += 7; m.move(100, y); s = m.shown()
        ok = ok and all(s[a][0] == prev[a][0] + 7 for a in s if a in prev)
        prev = s
    m.up(100, y)
    expect(ok, 'and back down the same way')
    m.clock += O['LY_IDLE_MS'] + 100; m.at(5); m.frame(10000)
    expect(m.shown() == expect_layout(song, 1, 0, m.measure_fn) and m.shown()[song[1][1]][0] == anchor(4), 'three seconds later the lines rest with the current four-row line at its anchor')
    # the bounds with tall lines: the first and the last line stop at their own anchors
    tall = [(0, 'x' * 140), (5, 'Middle'), (10, 'y' * 110)]
    m = LyMachine(tall); m.init(); m.at(0)
    m.down(100, 100); m.move(100, 120); m.move(100, 240)
    expect(m.shown()[tall[0][1]][0] == anchor(6), 'dragged down past the start a six-row first line stops at its anchor')
    m.up(100, 240)
    m = LyMachine(tall); m.init(); m.at(10); m.frame(10000)
    m.down(100, 240); m.move(100, 220); m.move(100, 20)
    expect(m.shown()[tall[2][1]][0] == anchor(5), 'dragged up past the end a five-row last line stops at its anchor')
    # a tap on a row of a tall line seeks to it
    m = LyMachine(song); m.init(); m.at(10); m.frame(10000)
    y3 = m.shown()[song[3][1]][0]; m.clock += 1000
    m.down(50, y3 + 20); m.up(50, y3 + 20); m.frame(10000)
    expect(m.seeks == [15] and m.shown()[song[3][1]][0] == anchor(6), 'a tap on the six-row line under the current one seeks there and the line comes to its anchor')
    # the cut: more than MAXR rows end in the mark inside the last row; a last word that fits only without the mark is kept
    lim = lambda u: 10 * len(u)
    for text, last in ((' '.join(['w' * 24] * 6), 'w' * 24), (' '.join(['w' * 24] * 5 + ['w' * 25]), 'w' * 25), (' '.join(['w' * 24] * 5 + ['w' * 20, 'abc']), 'w' * 20 + ' abc'),
                       (' '.join(['w' * 24] * 5 + ['w' * 20, 'abcd']), 'w' * 20 + ' abcd'), (' '.join(['w' * 24] * 5 + ['w' * 20, 'abc', 'd']), 'w' * 20 + ' abc' + MARK),
                       (' '.join(['w' * 24] * 5 + ['w' * 20, 'ab', 'cd', 'ef']), 'w' * 20 + ' ab' + MARK), (' '.join(['w' * 24] * 5) + ' ' + 'v' * 60, 'v' * 24 + MARK),
                       (' '.join(['w' * 24] * 5) + ' ' + 'v' * 25 + ' z', 'v' * 24 + MARK)):
        m = LyMachine([(0, text)], measure=lim); m.init(); m.at(0)
        lab = m.label_text(m.pool()[0]).split('\n')
        expect(len(lab) == MAXR and lab[-1] == last and lab == break_rows(text, lim) and lim(lab[-1]) <= ROW, f'{len(text)} characters ending {text[-12:]!r}: the last row is {lab[-1]!r} ({lim(lab[-1])} px)')
    cjk = '歌' * 60
    m = LyMachine([(0, cjk)], measure=lambda u: 30 * len(u)); m.init(); m.at(0)
    lab = m.label_text(m.pool()[0]).split('\n')
    expect(lab == ['歌' * 8] * 5 + ['歌' * 7 + MARK] and m.shown()[cjk][2] == CJKF, f'60 CJK characters of 30 px: five rows of 8 and one of 7 with the mark ({lab[-1]})')


def cost_tests(ctx):
    expect = ctx.expect
    long_song = [(i * 4, f'Lyric line number {i}') for i in range(400)]
    m = LyMachine(long_song); m.count(); m.init(); m.at(1000)
    m.at(1000); m.frame(10000)
    m.at(1000)
    idle = m.icount
    expect(idle < 40000, f'an idle lyric tick on 400 lines costs {idle} instructions (no layout)')
    expect(not any(c[0] in ('widget_move', 'widget_resize', 'widget_set_text_utf8') for c in m.calls), 'and touches no label')
    m.at(1004); m.frame(0)
    expect(len(m.shown()) <= POOL, f'at most {POOL} labels show')
    # a long list: the line count is capped, the page does not run off the table
    m = LyMachine([(i, f'L{i}') for i in range(2000)]); m.init(); m.at(399)
    expect(m.shown() and 'L399' in m.shown() and 'L400' not in m.shown() and m.shown()['L399'][0] == ANCHOR, f'more than {O["LY_MAX"]} lines: the first {O["LY_MAX"]} are shown, the rest ignored')
    # a frame: the labels of one animation step
    m = LyMachine(SONG); m.init(); m.at(5); m.calls = []; m.frame(40)
    moves = [c for c in m.calls if c[0] == 'widget_move']
    expect(0 < len(moves) <= POOL and not any(c[0] in ('widget_set_text_utf8', 'widget_use_style') for c in m.calls), f'an animation step only moves labels ({len(moves)} moves)')


def face_tests(ctx):
    expect = ctx.expect
    mm = Machine()
    buf = mm.alloc(0x4000)

    def latin_c(s):
        mm.u.mem_write(buf, (s.encode('utf-8', 'surrogatepass') if isinstance(s, str) else s) + b'\0')
        return mm.call(PSYMS['ly_latin'], a0=buf, count=8000000)
    # ly_latin: exactly the code points of the bold face
    every = ''.join(chr(c) for c in sorted(BOLD_CPS))
    expect(latin_c(every) == 1 and latin_c('') == 1, f'a text of all {len(BOLD_CPS)} code points of the bold face is Latin, and so is an empty one')
    edges = sorted({c + d for c in BOLD_CPS for d in (-1, 0, 1) if c - 1 not in BOLD_CPS or c + 1 not in BOLD_CPS} | set(range(0x20, 0x3000, 5)) | set(range(0x3000, 0xD800, 97)) | set(range(0xE000, 0x10000, 97)))
    bad = [c for c in edges if 0 <= c < 0x110000 and not 0xD800 <= c < 0xE000 and latin_c(chr(c)) != (c in BOLD_CPS)]
    expect(not bad, f'ly_latin equals the bold file\'s cmap at every range boundary and on a stride over the BMP ({len(edges)} code points checked; wrong: {[hex(c) for c in bad[:8]]})')
    cases = [('Hello, world', 1), ('Héllo — “quoted” … Привет Ελληνικά ₹ €5', 1), ('Hello 世界', 0), ('ひらがな', 0), ('조용히', 0), ('♪ music', 0), ('日本語', 0),
             ('smile \U0001F600'.encode(), 0), (b'caf\xc3', 0), (b'\xc0\x80', 0), (b'a\x80b', 0), (b'\xe0\x80\x80', 0), (b'\xf8\x88\x80\x80\x80', 0), (b'\xe4\xb8', 0), ('Ａ', 0)]
    got = [latin_c(s) for s, _ in cases]
    expect(got == [w for _, w in cases], f'a line of Latin, Greek and Cyrillic is the bold face\'s; CJK, kana, Hangul, symbols, emoji and malformed UTF-8 are not ({got})')
    # the page: one face a line, the probe measures in the line's own face, a label's style is set only when its face changes
    lines = [(0, 'Hello there'), (5, '你好，世界'), (10, 'Mixed 日本語 line'), (15, 'Привет мир')]
    m = LyMachine(lines); m.init(); meas = [c for c in m.at(0) if c[0] == 'widget_measure_text']; m.at(5); m.frame(10000)
    s = m.shown()
    expect({k: v[2] for k, v in s.items()} == {t: face(t) for _, t in lines} and [s[t][2] for _, t in lines] == [BOLD, CJKF, CJKF, BOLD], f'Latin lines take the bold style, lines with CJK the default font\'s ({[s[t][2] for _, t in lines]})')
    expect(len(meas) >= 4 and all(c[2] == face(t) for c, (_, t) in zip(meas, lines)) and m.props.get((m.probe(), 'style')) in (BOLD, CJKF), 'the probe measures each line in its own face (a width in the wrong font would give the wrong rows)')
    n = sum(c[0] == 'widget_use_style' for c in m.calls)
    m.at(10); m.frame(10000); m.at(5); m.frame(10000)
    expect(sum(c[0] == 'widget_use_style' for c in m.calls) - n <= len(lines), 'a style is set when a label takes a line of another face, not on every move')
    # rows: a long word or a text with no spaces breaks by character, the same in either face (16 characters of 31 px: 496 px, 8 to a 259 px row)
    w31 = lambda u: 31 * len(u)
    got = []
    for t in ('字' * 16, 'x' * 16):
        mc = LyMachine([(0, t), (1, 'b')], measure=w31); mc.init(); mc.at(0); got.append(mc.shown()[t][3] // LINE_H)
    expect(got == [2, 2] and rows_of('字' * 16, w31) == 2 and rows_of('x' * 16, w31) == 2, f'the same 496 px take {got[0]} rows in the default font and {got[1]} in the bold one')

LYRSIZE = '/mnt/data/m1plus/nowplaying-lyrics-size'
# Settings > Now Playing > Lyrics Text Size (docs/modules/lyrics.md "Text size"): size index -> (font px, row pitch, gap, style suffix)
SIZES = {0: (22, 25, 9, '_s'), 1: (26, 29, 10, '_m'), 2: (30, 34, 12, '')}


def size_tests(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    # the asset: one style pair a size, in every state: the font, the spacer (the row pitch), the face
    th = awtk_style.parse(open(os.path.join(raw, 'styles', 'playing_page.bin'), 'rb').read())
    ls = {(i.style, i.state): i for i in th.items if i.widget == 'label' and i.style.startswith('np_lyric')}
    names = {BOLD + sf for *_, sf in SIZES.values()} | {CJKF + sf for *_, sf in SIZES.values()}
    expect({k[0] for k in ls} == names == set(mn.LYRIC_SIZE_STYLES) and all((n, st) in ls for n in names for st in mn.BTN_STATES), f'six label styles in every state: the bold and the default-font style for each size ({sorted(names)})')
    ok = all(ls[(n + sf, st)].get('font_size') == px and ls[(n + sf, st)].get('spacer') == lh - px and ls[(n + sf, st)].get('text_align_h') == 2
             and ls[(n + sf, st)].color('text_color').lower().startswith('#ffffff') and ls[(n + sf, st)].get('font_name') == ('lyrics' if n == BOLD and sf != '_s' else None)
             for px, lh, gap, sf in SIZES.values() for n in (BOLD, CJKF) for st in mn.BTN_STATES)
    expect(all(mn.LYR_GAPS[sf] == gap and mn.LYR_SIZES[sf] == (px, lh - px) for px, lh, gap, sf in SIZES.values()), 'the preview and style tables (LYR_SIZES, LYR_GAPS) are the payload\'s sizes')
    expect(ok and SIZES[2][:3] == (O['LY_FONT'], O['LY_LINE_H'], O['LY_GAP']) and all(1.1 <= lh / px <= 1.15 for px, lh, *_ in SIZES.values()),
           'Small 22 / 25, Medium 26 / 29, Large 30 / 34 px (font / row pitch), left aligned, white; the bold style names lyrics.ttf (the Small one names no font, like the CJK style), the other the default font; Large is the original style')
    # stock's label paint draws a row of a wrapped label only while y + the font is at most the content area's bottom (0x62eb4c), from the top margin on: the last row of an n-row label
    # (n x the pitch high) is drawn when margin_top + margin_bottom <= spacer (device report: at Medium and Small, spacer 3 under the default 2 + 2, every wrapped line lost its last row)
    def drawn(st, px, lh, rows):
        mt, mb = (st.get(k) if st.get(k) is not None else st.get('margin') if st.get('margin') is not None else 2 for k in ('margin_top', 'margin_bottom'))
        y, n = mt, 0
        while n < rows and y + px <= rows * lh - mb: y, n = y + lh, n + 1
        return n
    lost = [(n + sf, st, r) for px, lh, gap, sf in SIZES.values() for n in (BOLD, CJKF) for st in mn.BTN_STATES for r in range(2, MAXR + 1) if drawn(ls[(n + sf, st)], px, lh, r) != r]
    side = {ls[k].get(m) for k in ls for m in ('margin', 'margin_left', 'margin_right')}
    expect(not lost and side == {None} and all(ls[(n, st)].get('margin_top') is None and ls[(n, st)].get('margin_bottom') is None for n in (BOLD, CJKF) for st in mn.BTN_STATES),
           f'at every size stock paints all 2..{MAXR} rows of a wrapped label inside its height (margin_top + margin_bottom <= spacer: Medium and Small set 1 + 1); the side margins stay the default (the {FIT} px content width) and Large sets none ({lost[:3]})')
    expect(all(AMIN <= anchor(r, lh, gap) and anchor(r, lh, gap) + r * lh <= VIEW_H - AROOM for px, lh, gap, _ in SIZES.values() for r in range(1, MAXR + 1)),
           f'at every size {MAXR} rows from their anchor end inside the view ({[[anchor(r, lh, gap) for r in range(1, MAXR + 1)] for _, lh, gap, _ in SIZES.values()]})')

    # the setting: the file, read as a digit; a missing or invalid file is Large
    mm = Machine()
    got = []
    for data in (None, b'0\n', b'0', b'1\n', b'2\n', b'3\n', b'x', b'', b'12'):
        mm.fs.pop(LYRSIZE, None)
        if data is not None: mm.fs[LYRSIZE] = data
        got.append(mm.call(PSYMS['ly_size'], count=200000))
    expect(got == [2, 0, 0, 1, 2, 2, 2, 2, 2], f'ly_size: Small "0", Medium "1", Large "2"; a missing or invalid file is Large ({got})')
    mm.fs.pop(LYRSIZE, None); mm.calls = []
    r = [mm.call(PSYMS['ly_size_set'], a0=v & 0xffffffff, count=400000) for v in (0, 1, 2)]
    expect(r == [0, 1, 2] and mm.fs.get(LYRSIZE) == b'2\n' and ('rename', LYRSIZE + '.tmp', LYRSIZE) in mm.calls and mm.call(PSYMS['ly_size'], count=200000) == 2, 'ly_size_set saves the digit atomically (a temp file renamed) and returns it')
    expect(mm.call(PSYMS['ly_size_set'], a0=3, count=400000) == 0xffffffff and mm.call(PSYMS['ly_size_set'], a0=0xffffffff, count=400000) == 0xffffffff and mm.fs.get(LYRSIZE) == b'2\n', 'a size past Large is refused and the file is as it was')

    # the page: every size lays the lines out with its own pitch, gap, anchor and style names
    long_line, four = 'x' * 70, 'y' * 100   # at the machine's 10 px a character: three and four rows
    lines = [(0, 'Line zero'), (5, 'Line one'), (10, four), (15, 'Line three'), (20, long_line), (25, '你好，世界')]
    for k, (px, lh, gap, sf) in SIZES.items():
        m = LyMachine(lines); m.fs[LYRSIZE] = f'{k}\n'.encode(); m.init(); m.at(0); m.at(0)
        sh = m.shown()
        expect(sh['Line zero'][0] == ANCHOR and sh['Line zero'][2] == BOLD + sf and sh['Line zero'][3] == lh and sh['Line one'][0] == ANCHOR + lh + gap and sh['Line one'][3] == lh,
               f'size {px}: the current line at the anchor {ANCHOR}, one row {lh} px, the next line one pitch ({lh} + {gap}) lower ({sh})')
        expect(m.props.get((m.probe(), 'style')) in (BOLD + sf, CJKF + sf), f'size {px}: the probe uses the {BOLD + sf} or {CJKF + sf} style')
        m.at(10); m.frame(10000)
        sh = m.shown()
        expect(sh[four][3] == 4 * lh and sh[four][0] == anchor(4, lh, gap) and sh['Line three'][0] == anchor(4, lh, gap) + 4 * lh + gap,
               f'size {px}: a four row line is 4 x {lh} px from its anchor {anchor(4, lh, gap)}, the next line under it ({sh[four]})')
        m.at(20); m.frame(10000)
        sh = m.shown()
        expect(sh[long_line][3] == 3 * lh and sh[long_line][0] == anchor(3, lh, gap) == ANCHOR, f'size {px}: three rows {sh[long_line][3]} px at the anchor')
        m.at(25); m.frame(10000)
        sh = m.shown()
        expect(sh['你好，世界'][2] == CJKF + sf and m.props.get((m.probe(), 'style')) == CJKF + sf, f'size {px}: the default-font line takes {CJKF + sf}, and the probe measures in it')
        # a tap on the second line seeks to it: the touch map follows the pitch and the gap
        m = LyMachine(lines); m.fs[LYRSIZE] = f'{k}\n'.encode(); m.init(); m.at(0); m.frame(10000)
        y = ANCHOR + lh + gap + lh // 2
        m.down(50, y); m.up(50, y)
        expect(m.seeks == [5], f'size {px}: a tap at y {y} seeks to the second line ({m.seeks})')
    # the intro: the lines sit one pitch of the size below the anchor, the dots centred on the anchor row
    for k, (px, lh, gap, sf) in SIZES.items():
        m = LyMachine(INTRO); m.fs[LYRSIZE] = f'{k}\n'.encode(); m.init(); m.at(0); m.at(0)
        sh = m.shown(); ds = m.dot_state()
        expect(sh['Intro line'][0] == ANCHOR + lh + gap and all(d[2] == ANCHOR + (lh - DOT) // 2 for d in ds),
               f'size {px}: the first line sits {lh + gap} px under the anchor while the dots show, the dots centred on the anchor row ({sh["Intro line"][0]}, {ds})')

    # coming back to the front: a size changed in Settings is taken, the lines laid out again, no label is made again
    m = LyMachine(lines); m.init(); m.at(5); m.frame(10000)
    expect(m.shown()['Line one'][2] == BOLD and m.shown()['Line one'][3] == LINE_H, 'the default size is Large')
    n_labels = m.names().count('label_create')
    m.fs[LYRSIZE] = b'0\n'
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0); m.tick(); m.frame(10000)
    sh = m.shown()
    expect(sh['Line one'][2] == BOLD + '_s' and sh['Line one'][3] == 25 and sh['Line one'][0] == ANCHOR and m.names().count('label_create') == n_labels
           and m.props.get((m.probe(), 'style')) in (BOLD + '_s', CJKF + '_s') and set(v[2] for v in sh.values()) <= {BOLD + '_s', CJKF + '_s'},
           f'a size picked in Settings is taken when the page is in front again: the current line Small, 25 px rows, the new styles, the probe\'s too ({sh})')
    m.calls = []; m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0); m.tick()
    expect(not any(c[0] in ('widget_use_style', 'widget_resize', 'widget_set_text_utf8') for c in m.calls), 'the same size again changes nothing')


def size_setting_tests(ctx):
    """Settings > Now Playing > Lyrics Text Size and its picker (m1plus_lyrsize): the saved size, read live; a pick saves it atomically."""
    expect, P = ctx.expect, pod_pages
    N, L = P.NPSET_PAGE, P.LYRSIZE_PAGE
    rows_n = PSYMS[f'pod_rows_{P.NPSET_PAGE_INDEX}']
    labels = [(r.label, r.action, r.arg) for r in N.rows]
    expect(labels.index(('Lyrics Text Size', P.ACT_LYRSIZE, P.LYRSIZE_PAGE_INDEX)) == labels.index(('Base', P.ACT_VTHEME, P.VTHEME_PAGE_INDEX)) + 1 == len(labels) - 2 and P.ACT_LYRSIZE in P.VALUE_ACTIONS
           and P.ACT_LYRSIZESET in P.CHECK_ACTIONS and P.VALUE_INIT[P.ACT_LYRSIZE] == 'Large', 'Settings > Now Playing: the Lyrics Text Size value row is its own card between Vinyl Mode and Idle Display; the picker\'s rows are check rows')
    expect([(r.label, r.action, r.arg) for r in L.rows] == [('Small', P.ACT_LYRSIZESET, 0), ('Medium', P.ACT_LYRSIZESET, 1), ('Large', P.ACT_LYRSIZESET, 2)] and L.title == 'Lyrics Text Size'
           and L.key == 'm1plus_lyrsize' and P.LYRSIZE_VALUES == ('Small', 'Medium', 'Large') and P.PAGES[P.LYRSIZE_PAGE_INDEX] is L, 'the picker: Small, Medium, Large, titled Lyrics Text Size')
    expect(LYRSIZE.rsplit('/', 1)[1] in P.SETTING_FILES and LYRSIZE.rsplit('/', 1)[1] == 'nowplaying-lyrics-size' and LYRSIZE.rsplit('/', 1)[1] not in ' '.join(P.RETIRED_FILES), 'the file is a Settings Files row')
    ids = [v for k, v in vars(P).items() if k.startswith('ACT_')]
    expect(len(set(ids)) == len(ids) and P.ACT_LYRSIZE == 135 and P.ACT_LYRSIZESET == 136, 'the action ids are distinct')

    def open_picker(data=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(3)] + [f'pod_check{i}' for i in range(3)])}
        if data is not None: m.fs[LYRSIZE] = data
        m.call(PSYMS['on_row'], a0=rows_n + 12 * 3, count=3000000)   # the Lyrics Text Size row (the fourth)
        return m

    def checks(m):
        out = []
        for i in range(3):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out

    m = open_picker()
    expect(('window_open', L.key) in m.calls and checks(m) == [0, 0, 1] and LYRSIZE not in m.fs, 'the row opens the picker, the check is on Large with no file, and reading writes nothing')
    expect([checks(open_picker(d)) for d in (b'0\n', b'1\n', b'2\n', b'7', b'')] == [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1], [0, 0, 1]], 'a saved Small or Medium has the check; an invalid file is Large')
    m.click('pod_row0')
    expect(m.fs.get(LYRSIZE) == b'0\n' and LYRSIZE + '.tmp' not in m.fs and ('rename', LYRSIZE + '.tmp', LYRSIZE) in m.calls and checks(m) == [1, 0, 0], 'Small: the file is written atomically and the check follows')
    m.click('pod_row1')
    expect(m.fs.get(LYRSIZE) == b'1\n' and checks(m) == [0, 1, 0], 'Medium')
    m.fail.add(('write', LYRSIZE + '.tmp')); m.calls = []
    m.click('pod_row2')
    expect(m.fs.get(LYRSIZE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a save that fails changes neither the file nor the check')


INTRO = [(10, 'Intro line'), (14, 'Second line'), (18, 'Third line'), (24, 'Fourth line')]


class Run:
    """A page in its intro with the player and the clock moving together: the player reads whole seconds of (clock - t0); every poll of the payload is mirrored in the model's Clock."""
    def __init__(self, lines=INTRO, **kw):
        self.m = LyMachine(lines, **kw); self.m.init()
        self.t0 = self.m.clock; self.ck = Clock(); self.ck.update(0, self.m.clock, True)

    def sync(self, ms):
        m = self.m
        if m.status == 3: self.t0 += ms   # paused: the position stays
        m.clock += ms; m.play = (m.clock - self.t0) // 1000; m.calls = []

    def spring(self):
        """Let the lines' spring run out (ly_frame at 40 ms); the player goes on, the dots are not polled."""
        for _ in range(40):
            self.sync(40)
            if self.m.call(PSYMS['ly_frame'], count=2000000) == 0: break

    def frame(self, ms=DMS):
        self.sync(ms)
        res = self.m.call(PSYMS['ly_dframe'], count=2000000)
        self.ck.update(self.m.play, self.m.clock, self.m.status == 2)
        return res

    def tick(self, ms=500):
        self.sync(ms)
        self.m.tick(count=8000000)
        self.ck.update(self.m.play, self.m.clock, self.m.status == 2)

    def ops(self, ln=None):
        ln = ln if ln is not None else INTRO[0][0] * 1000
        return [dot_op(k, self.ck.est, ln) for k in range(3)]


def dots_tests(ctx):
    expect = ctx.expect
    DY = ANCHOR + (LINE_H - DOT) // 2
    # the opacity function against its model: dim to full by thirds, the breath, the fade
    mm = Machine()
    pts = [(k, el, ln) for ln in (4000, 10000, 24000, 90000) for k in range(3) for el in (-5, 0, 1, 700, 1200, 2400, 3333, 4000, ln // 2, ln - 600, ln - 500, ln - 499, ln - 250, ln - 1, ln, ln + 10)]
    got = [mm.call(PSYMS['ly_dot_op'], a0=k, a1=el & 0xffffffff, a2=ln, count=50000) for k, el, ln in pts]
    expect(got == [dot_op(k, el, ln) for k, el, ln in pts] and mm.call(PSYMS['ly_dot_op'], a0=0, a1=5, a2=0, count=50000) == 0, f'ly_dot_op equals the model on {len(pts)} points (dim to full by thirds, breath, fade out)')
    ln = 24000
    peaks = [[dot_op(k, el, ln) for el in range(0, ln - DFADE, DBR)] for k in range(3)]   # el a multiple of the breath period: the breath is at its full
    expect(peaks[0][0] == peaks[1][0] == peaks[2][0] == DDIM == 64 and all(a <= b for p in peaks for a, b in zip(p, p[1:])) and peaks[0][4] == 255 and peaks[1][8] == 255
           and peaks[2][-1] >= 200 and peaks[0][2] > peaks[1][2] >= peaks[2][2] == DDIM and dot_op(2, 23400, ln) > dot_op(2, 20000, ln) > peaks[2][3],
           f'every dot starts at {DDIM} (0.25), fills to 255 in its own third of the gap (dot 0 by {ln // 3 // 1000} s, dot 1 by {2 * ln // 3 // 1000} s, dot 2 as the fade starts), in order')
    brs = [dot_op(0, el, ln) for el in range(15000, 15000 + DBR, 50)]   # dot 0 is full there: only the breath moves it
    expect(max(brs) == 255 and min(brs) == 255 * DBRMIN // 255 and DBRMIN / 255 >= 0.6 and (15000 + brs.index(min(brs)) * 50) % DBR in range(DBR // 2 - 100, DBR // 2 + 100)
           and all(abs(a - b) <= 8 for a, b in zip(brs, brs[1:])), f'the breath: the group moves between {min(brs)} and 255 ({min(brs) / 255:.2f}..1.0) over {DBR} ms, a slow triangle (at most 8 steps a 50 ms)')
    fd = [dot_op(0, 9500 + d, 10000) for d in range(0, 500, 50)]
    expect(fd[0] > fd[-1] >= 0 and all(a >= b for a, b in zip(fd, fd[1:])) and dot_op(0, 10000, 10000) == 0 and dot_op(2, 9999, 10000) <= 1, f'fades out over the last {DFADE} ms and is 0 when the first line starts ({fd})')

    # the constants
    expect(DOT == 10 and DPAD == LINE_H + GAP and DMIN == 4 and 50 <= DMS <= 100 and DDIM == 64 and DFADE == 500 and 1500 <= DBR <= 4000 and DX + 2 * DPITCH + DOT <= W and DPITCH > DOT,
           f'{DOT} px dots, {DPITCH} px apart, the lines {DPAD} px lower while they show (one pitch), for a first line at {DMIN} s or later, a {DMS} ms timer')

    # the page in its intro: the dots at the anchor row, the lines below as the upcoming ones
    r = Run(); m = r.m
    d = m.dot_state()
    expect(all(x[0] == 1 for x in d) and [x[1] for x in d] == [DX + k * DPITCH for k in range(3)] and all(x[2] == DY for x in d), f'the dots are left aligned at the text, centred on the anchor row: x {[x[1] for x in d]}, y {d[0][2]}')
    expect(m.dot_ops() == r.ops() and all(0 < o < 100 for o in m.dot_ops()) and m.dot_ops()[0] >= m.dot_ops()[1] == m.dot_ops()[2], f'all dim at the start, the first beginning to fill ({m.dot_ops()})')
    expect(m.shown() == expect_layout(INTRO, -1, DPAD, m.measure_fn) and m.shown()['Intro line'][0] == ANCHOR + DPAD and m.shown()['Intro line'][1] == fade(OPACITY[1], ANCHOR + DPAD, 1),
           'the lines sit below the dots as the upcoming ones (0.45, 0.32, ...), the first one pitch under the anchor')
    expect(m.dtimers() == [(PSYMS['ly_dframe'], DMS)] and not m.ly_timers() and all(m.props.get((h, 'sensitive')) == 0 for h in m.dots()), f'one {DMS} ms timer, and the dots are insensitive')
    ok, seen, last = True, [], []
    for step in range(1, 120):
        res = r.frame()
        ok = ok and m.dot_ops() == r.ops() and m.shown() == expect_layout(INTRO, -1, DPAD, m.measure_fn)
        seen.append(m.dot_ops())
        if step in (30, 60, 90): last.append(m.dot_ops())
        if res == 0: break
    expect(ok, f'{step} frames over the intro: the dots and the lines are where the model puts them at every one')
    expect(last[0][0] > last[0][1] >= last[0][2] and last[1][1] > last[1][2] and last[2][2] >= last[0][2], f'they fill in sequence: after 2.4 s {last[0]}, after 4.8 s {last[1]}, after 7.2 s {last[2]}')
    expect(sum(len(set(s[k] for s in seen)) for k in range(3)) > 60, 'and the opacity changes smoothly (many distinct values)')
    r2 = Run(); m2 = r2.m
    n = 0
    while m2.shown().get('Intro line', (0, 255))[1] == fade(OPACITY[1], ANCHOR + DPAD, 1) and n < 200:
        res = r2.frame(); n += 1
    expect(is_cur(m2.shown(), 'Intro line'), f'when the position reaches the first line it becomes current ({n} frames, at {m2.play} s)')
    expect(m2.play == 10 and not any(m2.dot_ops()) and all(m2.props.get((h, 'visible')) == 0 for h in m2.dots()), 'the dots are hidden by then (they have faded out)')
    expect(res == 0 and len(m2.ly_timers()) == 1, 'the dot timer ends itself (RET_OK) and the lines move up with the usual spring and stagger')
    mdl = Model(INTRO, m2.measure_fn); mdl.pad = DPAD; mdl.cur = 0; mdl.move(0, m2.clock, pad=0)
    okm = m2.shown() == mdl.layout(m2.clock)
    for _ in range(40):
        r2.sync(40)
        rr = m2.call(PSYMS['ly_frame'], count=2000000)
        okm = okm and m2.shown() == mdl.layout(m2.clock)
        if rr == 0: break
    expect(okm and m2.shown() == expect_layout(INTRO, 0, 0, m2.measure_fn) and m2.shown()['Intro line'][0] == ANCHOR, 'the first line comes up one pitch to the anchor as the model says at every frame, and rests there')
    # the last 500 ms are the fade: the dots before the first line
    r3 = Run(); m3 = r3.m
    while r3.ck.est < 9700: r3.frame()
    expect(m3.dot_ops() == r3.ops() and all(o > 0 for o in m3.dot_ops()) and max(m3.dot_ops()) < 255 * 0.6, f'300 ms before the line the dots are fading ({m3.dot_ops()} at {r3.ck.est} ms)')

    # pause: the dots freeze, the timer ends; play: they go on from where they were
    r = Run(); m = r.m
    for _ in range(20): r.frame()
    m.status = 3; res = r.frame()
    frozen = m.dot_ops()
    expect(res == 0 and not m.dtimers() or res == 0, 'a paused player: the frame ends its timer')
    n_timers = len(m.timers)
    for _ in range(3): r.tick(500)
    expect(m.dot_ops() == frozen and len(m.timers) == n_timers, f'and the page tick leaves them frozen ({frozen}), no new timer')
    m.status = 2; est0 = r.ck.est; r.t0 += 500; r.tick(500)
    expect(len(m.dtimers()) == 2 and m.dot_ops() == r.ops() and abs(r.ck.est - est0) == 0, f'playing again: the timer starts again and the position went on from where it froze (est {r.ck.est})')
    r.frame(); expect(r.ck.est == est0 + DMS and m.dot_ops() == r.ops(), 'and moves again by the clock')
    # a stopped player: the position is 0, the dots show dim and the timer does not run
    r = Run(); m = r.m; m.status = 1; m.play = 0
    for _ in range(2): r.tick(500)
    expect(len(m.dtimers()) == 1, 'stopped: the timer is not started again')
    # seeks: into the intro from a later line, within it, out of it
    r = Run(); m = r.m; r.t0 = m.clock - 15000; r.tick(0); r.spring(); r.frame()
    expect(is_cur(m.shown(), 'Second line') and not any(m.dot_ops()), 'a later line: no dots')
    nd = len(m.dtimers()); r.t0 = m.clock - 3000; r.tick(0)
    s = m.shown()
    expect(any(m.dot_ops()) and not is_cur(s, 'Second line') and len(m.dtimers()) == nd + 1, f'a seek back into the intro brings the dots back at 3.5 s ({m.dot_ops()}) with the lines on their way down under them, the dot timer starts again')
    r.spring()
    expect(m.shown() == expect_layout(INTRO, -1, DPAD, m.measure_fn) and m.dot_ops() == r.ops(), 'the lines rest one pitch under the anchor, the dots on the anchor row')
    r.t0 = m.clock - 6000; r.tick(0)
    est = r.ck.est
    expect(est == 6500 and m.dot_ops() == r.ops() and m.dot_ops()[0] > m.dot_ops()[2], f'a seek within the intro (to 6 s): the fill follows ({m.dot_ops()})')
    r.t0 = m.clock - 11000; r.tick(0)
    expect(is_cur(m.shown(), 'Intro line') and not any(m.dot_ops()) and all(m.props.get((h, 'visible')) == 0 for h in m.dots()), 'a seek out of the intro (to 11 s): the first line is current and the dots are gone at once')
    r.spring(); expect(m.shown() == expect_layout(INTRO, 0, 0, m.measure_fn), 'the lines settle at the anchor')
    res = r.frame(); expect(res == 0 and not any(m.dot_ops()), 'the dot frame after that ends its timer and shows nothing')
    # a seek back from far down the list (more than the snap distance): the lines jump under the dots, no animation
    long_song = [(12, 'Start')] + [(12 + 5 * i, f'Row {i}') for i in range(1, 30)]
    r = Run(long_song); m = r.m; r.t0 = m.clock - 100000; r.tick(0); r.spring(); r.frame()
    nd = len(m.dtimers()); r.t0 = m.clock - 1000; r.tick(0)
    expect(m.shown() == expect_layout(long_song, -1, DPAD, m.measure_fn) and len(m.dtimers()) == nd + 1 and not m.ly_timers() and all(m.dot_ops()), 'a seek from far into the intro: the lines jump under the dots (no animation), the dot timer runs')

    # the threshold: the first line at 3 s: no dots; at 4 s: dots
    for t0, want in ((3, False), (4, True), (0, False), (1, False), (10000, False), (9999, True)):
        mk = LyMachine([(t0, 'First'), (t0 + 6, 'Next')]); mk.init(); mk.at(0)
        expect(bool(any(mk.dot_ops())) == want and (mk.shown()['First'][0] == ANCHOR + (DPAD if want else 0)), f'a first line at {t0} s: {"dots" if want else "no dots"}')
    # lyrics that arrive late, or are replaced; no lyrics
    r = Run([]); m = r.m
    expect(not any(m.dot_ops()) and not m.dtimers(), 'no lyrics: no dots, no timer')
    m.set_lines(INTRO); r.tick(500)
    expect(m.shown() == expect_layout(INTRO, -1, DPAD, m.measure_fn) and any(m.dot_ops()) and len(m.dtimers()) == 1 and not m.ly_timers(), 'lyrics arriving during the intro: the dots show and the lines sit under them at once, no move')
    m.set_lines([]); r.tick(500)
    expect(not m.shown() and not any(m.dot_ops()) and all(m.props.get((h, 'visible')) == 0 for h in m.dots()), 'the lyrics go away: lines and dots are hidden')
    res = r.frame(); expect(res == 0 and not any(m.dot_ops()), 'and the dot frame ends itself')
    r = Run([]); m = r.m; r.t0 = m.clock - 52000; m.set_lines(INTRO); r.tick(0); r.spring()
    expect(not any(m.dot_ops()) and not m.dtimers() and m.shown() == expect_layout(INTRO, 3, 0, m.measure_fn), 'lyrics arriving late (52 s, the fourth line is current): no dots, the lines at the anchor')
    # a song change in the middle: new lines, the clock starts again
    r = Run(); m = r.m
    for _ in range(40): r.frame()
    m.set_lines([(6, 'New intro'), (9, 'New two')]); r.ck = Clock(); r.tick(0)
    s = m.shown()
    expect(set(s) == {'New intro', 'New two'} and s == expect_layout([(6, 'New intro'), (9, 'New two')], -1, DPAD, m.measure_fn) and m.dot_ops() == [dot_op(k, r.ck.est, 6000) for k in range(3)] and r.ck.est == m.play * 1000 + 500,
           f'a song change in the intro: the new lines sit under the dots, the fill is on the new gap\'s clock ({m.dot_ops()})')
    m.set_lines([(1, 'Quick'), (5, 'Next')]); r.tick(0)
    expect(not any(m.dot_ops()) and m.shown()['Quick'][0] == ANCHOR, 'a song change to lyrics with a first line under 4 s: no dots')
    # the timer is refused: the dots follow the page tick (twice a second), nothing is stuck
    m = LyMachine(INTRO); m.no_dtimer = True; m.init(); r = Run.__new__(Run); r.m = m; r.t0 = m.clock; r.ck = Clock(); r.ck.update(0, m.clock, True)
    expect(not m.dtimers() and any(m.dot_ops()) and m.dot_ops() == r.ops(), f'the dot timer is refused: the dots show, static ({m.dot_ops()})')
    o1 = m.dot_ops(); r.tick(500)
    expect(m.dot_ops() == r.ops() and m.dot_ops() != o1 and not m.dtimers(), 'and move on with the page tick')
    for _ in range(19): r.tick(500)
    expect(is_cur(m.shown(), 'Intro line') and not any(m.dot_ops()), 'and go when the first line starts (the page tick sets it)')
    # the dots image is refused: no dots, the page runs as before
    m = LyMachine(INTRO); m.create_fail = {'image_create'}; m.init()
    expect(m.shown() == expect_layout(INTRO, -1, 0, m.measure_fn) and not m.dtimers() and len(m.children[m.box]) == POOL + 1 and m.timers == [(PSYMS['np_tick'], 500)], 'no dot image can be made: no dots, the first line waits at the anchor, no dot timer')
    m.at(10); expect(is_cur(m.shown(), 'Intro line'), 'and the lyrics still follow the song')
    # the page destroyed during the intro: both timers removed, a stray frame does nothing
    m = LyMachine(INTRO); m.init(); m.calls = []
    m.call(PSYMS['np_on_destroy'], a0=WIN, a1=0)
    expect(sum(c[0] == 'timer_remove' for c in m.calls) == 2, 'the page destroyed during the intro removes both timers (the page\'s and the dots\')')
    m.calls = []; res = m.call(PSYMS['ly_dframe'], count=500000)
    expect(res == 0 and not m.calls, 'and a stray dot frame does nothing')
    # touch: the dots take no touch, a drag moves them with the first line, the song's first line while scrolled leaves the lines where they are
    r = Run(); m = r.m
    m.down(DX + 5, DY + 5); m.up(DX + 5, DY + 5)
    expect(m.seeks == [], 'a tap on the dots seeks nothing')
    y0 = m.shown()['Intro line'][0]
    m.down(100, 200); m.move(100, 185); m.move(100, 170)
    s = m.shown()
    expect(m.dot_state()[0][2] == DY - 15 and s['Intro line'][0] == y0 - 15, f'a drag moves the dots with the first line ({m.dot_state()[0][2]} for {s["Intro line"][0]})')
    m.up(100, 170)
    before = {k: v[0] for k, v in m.shown().items()}
    r.t0 = m.clock - 10500; r.sync(0); m.tick(count=8000000); r.ck.update(m.play, m.clock, True)
    after = m.shown()
    expect(is_cur(after, 'Intro line') and {k: v[0] for k, v in after.items() if k in before} == {k: before[k] for k in after if k in before} and not any(m.dot_ops()),
           'the first line starts while the user has scrolled: the highlight moves, the lines stay under the finger, the dots are gone')
    # cost: a dot frame
    m = LyMachine(INTRO); m.count(); m.init(); m.at(0); m.calls = []; m.icount = 0   # (the first page tick measures the lines)
    m.dframe(); n1 = m.icount
    expect(n1 < 60000, f'a dots frame costs {n1} instructions')
    expect(sum(c[0] in ('widget_move', 'widget_resize', 'widget_set_text_utf8', 'widget_use_style') for c in m.calls) == 0 and sum(c[0] == 'widget_set_opacity' for c in m.calls) <= 4, 'it only changes the three dots\' opacity (and a line\'s when it fades)')


def font_tests(ctx):
    """ly_start installs the coverage gamma (patch/textgamma.c) on the lyrics face: the first open maps it, a later open is a no-op,
    the kill switch leaves the stock slot, and no font manager means no font is asked for (test/pod/textgamma.py covers the wrapper)."""
    expect = ctx.expect
    FM, KILL, STB, TG = 0x24000000, '/mnt/mmc/m1plus-off', O['STB_GET_GLYPH'], PSYMS['tg_get_glyph']

    def lyrics_face(m):
        """The lyrics font object as font_stb_create leaves it (match, get_glyph, mono flag)."""
        f = m.malloc(0xd4); m.u.mem_write(f, bytes(0xd4))
        m.setword(f + O['FONT_MATCH'], O['STB_MATCH']); m.setword(f + O['FONT_GET_GLYPH'], STB)
        m.u.mem_write(f + O['FONT_MONO'], bytes([0]))
        m.fm, m.font = FM, f
        return f

    m = LyMachine(SONG); lyrics_face(m); m.init()
    expect(('font_manager_get_font', FM, 'lyrics', 0) in m.calls and m.word(m.font + O['FONT_GET_GLYPH']) == TG,
           'opening the lyrics page asks for the lyrics font and installs tg_get_glyph in its get_glyph slot')
    expect(('font_manager_shrink_cache', FM, 0) in m.calls, 'the install empties the glyph cache (keep 0)')
    expect(m.shown() == expect_layout(SONG, 0, 0, m.measure_fn), 'and the page lays out its lines as before')
    m.init()
    expect(m.word(m.font + O['FONT_GET_GLYPH']) == TG and not any(c[0] == 'font_manager_shrink_cache' for c in m.calls),
           'a second open is a no-op: the wrapper stays, the cache is not emptied again')

    m = LyMachine(SONG); lyrics_face(m); m.present.add(KILL); m.init()
    expect(m.word(m.font + O['FONT_GET_GLYPH']) == STB and not any(c[0] == 'font_manager_shrink_cache' for c in m.calls) and m.shown(),
           'the kill switch: the stock slot stays, and the page still shows its lines')

    m = LyMachine(SONG); m.init()
    expect(not any(c[0] == 'font_manager_get_font' for c in m.calls) and m.shown(), 'no font manager: no font is asked for, the page still works')


VH2, ANC2 = 358, 125   # the idle page's view: 0.35 x 358 (patch/idlelyrics.c)


def retarget(m, h=VH2, y=80):
    """The idle page's engine take-over: a window and a box of its own (at 28, y), the retarget's answer. m.box is the new box when it succeeded."""
    win2, box2 = m.alloc(0x80), m.alloc(0x80)
    m.setword(box2, 28); m.setword(box2 + 4, y)
    m.np_box, m.win2, m.box2 = m.box, win2, box2
    m.calls = []
    r = m.call(PSYMS['ly_retarget'], a0=win2, a1=box2, a2=h, count=2000000)
    if r == 0:
        m.box = box2; m.stage(2, win2)
    return r


def idle_at(m, pos):
    """The idle page's tick: the engine's own (Now Playing's page timer is not running under another window)."""
    m.play = pos; m.calls = []; m.call(PSYMS['ly_tick'], count=8000000)
    m.frame(10000)   # (the spring of a move settles)


def idle_ptr(m, kind, x, y): return m.ptr(kind, 28 + x, 80 + y)


def edge_vh(y, rows, lh, vh):
    e = min(y + rows * lh - lh // 2, vh - (y + lh // 2))
    return 0 if e <= 0 else 255 if e >= FADE else e * 255 // FADE


def retarget_tests(ctx):
    expect = ctx.expect
    D, MV, UP = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP']
    m = LyMachine(SONG); m.init(); m.at(10); m.frame(10000)
    before, np_box, np_pool = m.shown(), m.box, list(m.pool())
    expect(m.call(PSYMS['ly_target']) == np_box and m.call(PSYMS['ly_lines']) == len(SONG), 'ly_target is np_lyrics and ly_lines the stock rows while Now Playing has the engine')
    r = retarget(m)
    calls = m.calls
    expect(r == 0 and m.call(PSYMS['ly_target']) == m.box2, 'ly_retarget(window, box, 358) takes the engine: 0, ly_target is the page\'s box')
    expect(m.children[m.box2] == m.pool() + [m.probe()] + m.dots() and len(m.children[m.box2]) == POOL + 4 and all(m.props.get((h, 'sensitive')) == 0 for h in m.children[m.box2]),
           f'the page\'s box gets the {POOL} labels, the probe and the three dots, all insensitive')
    expect([c[2] for c in calls if c[0] == 'widget_on' and c[1] == m.box2] == [D, MV, UP, O['EVT_POINTER_ABORT']] and not any(c[0] == 'widget_on' and c[1] != m.box2 for c in calls),
           'four pointer listeners on the page\'s box and no other')
    expect(not any(len(c) > 1 and c[1] in np_pool + [np_box, m.src_w, m.view] for c in calls),
           'Now Playing\'s labels, box and the stock rows and list are not touched by the take-over')
    expect(not any(c[0] == 'timer_add' for c in calls), 'the take-over adds no timer of its own')
    idle_at(m, 10)
    s = m.shown()
    expect(s['Line two'][0] == ANC2 and s['Line two'][1] == 255 and s['Line three'][0] == ANC2 + PITCH, f'in the 358 px view the current line is at 0.35 of it, {ANC2}, and the next one pitch lower ({s})')
    idx = {t: i for i, (_, t) in enumerate(SONG)}
    bad = [(t, v) for t, v in s.items() if v[1] != OPACITY[min(abs(idx[t] - 2), 4)] * edge_vh(v[0], 1, LINE_H, VH2) // 255]
    expect(not bad and len(s) >= 6, f'opacity by distance times the edge factor of the 358 px view ({bad}, {len(s)} lines)')
    # touch: no seek on a tap; a vertical drag over 10 px browses; a touch of the other view's listener (Now Playing's ctx) does nothing
    y3 = ANC2 + PITCH + 17
    idle_ptr(m, D, 50, y3); idle_ptr(m, UP, 50, y3)
    expect(m.seeks == [], 'a tap on a line seeks nothing on the idle page')
    idle_ptr(m, D, 50, 200); idle_ptr(m, MV, 50, 190); idle_ptr(m, MV, 50, 160); idle_ptr(m, UP, 50, 160)
    s = m.shown()
    expect(s['Line two'][0] == ANC2 - 30 and m.seeks == [], f'a drag of 40 px up (the first 10 start it) moves the lines 30 px with the finger and seeks nothing ({s["Line two"]})')
    m.box = np_box; m.down(50, 100); m.move(50, 60); m.up(50, 60); m.box = m.box2
    expect(m.shown()['Line two'][0] == ANC2 - 30, 'a touch event for Now Playing\'s box is ignored while the page has the engine')
    # the engine goes back
    m.calls = []
    m.call(PSYMS['ly_release'], count=2000000)
    page_kids = set(m.children[m.box2])
    m.box = np_box
    expect(m.call(PSYMS['ly_target']) == np_box and m.shown() == {} and not any(len(c) > 1 and c[1] in page_kids for c in m.calls), 'ly_release: Now Playing\'s box is the target again, its labels are hidden, the page\'s widgets are not touched')
    m.at(10); m.frame(10000)
    expect(m.shown() == before, f'Now Playing lays the lines out exactly as before ({m.shown()} vs {before})')
    m.down(50, ANCHOR + PITCH + 17); m.up(50, ANCHOR + PITCH + 17)
    expect(m.seeks == [15], f'a tap on a line seeks again on Now Playing ({m.seeks})')
    n_make = m.names().count('label_create')
    m.calls = []; m.call(PSYMS['ly_release'], count=2000000)
    expect(m.calls == [] and m.names().count('label_create') == n_make, 'a second release does nothing')
    # taken twice, and given back by Now Playing coming to the front (ly_refresh)
    expect(retarget(m) == 0, 'the engine can be taken again')
    expect(m.call(PSYMS['ly_retarget'], a0=m.win2, a1=m.box2, a2=VH2, count=2000000) == 0xffffffff, 'a second take-over while it is taken is refused')
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0); m.box = np_box
    expect(m.call(PSYMS['ly_target']) == np_box, 'Now Playing in front again (np_on_foreground -> ly_refresh) gives the engine back')
    # every size: the anchor, the pitch, the edge fade follow the 358 px view
    for k, (px, lh, gap, sf) in SIZES.items():
        m = LyMachine(SONG); m.fs[LYRSIZE] = f'{k}\n'.encode(); m.init(); m.at(10)
        expect(retarget(m) == 0, 'taken')
        idle_at(m, 10); m.frame(10000)
        s = m.shown()
        bad = [(t, v) for t, v in s.items() if v[1] != OPACITY[min(abs(idx[t] - 2), 4)] * edge_vh(v[0], 1, lh, VH2) // 255 or v[2] != BOLD + sf]
        expect(s['Line two'][0] == ANC2 and s['Line three'][0] == ANC2 + lh + gap and not bad, f'size {px}: current line at {ANC2}, pitch {lh + gap}, the size\'s style, the 358 px edge fade ({s["Line two"]}, {bad})')
        # a line of four rows: anchored higher than 125 only when the next line would not fit the view
        idle_at(m, 20)
        m.frame(10000)
        expect(m.shown()['Line four'][0] == ANC2, f'size {px}: a one-row line stays at {ANC2}')
    # a taller current line moves up by the 358 px rule (ly_anchor: 358 - 8 - lh - (rows x lh + gap))
    long6 = 'x' * 160   # six rows at the machine's 10 px a character
    m = LyMachine([(0, 'Line zero'), (5, long6), (10, 'Line two')]); m.init(); m.at(5)
    retarget(m); idle_at(m, 5); m.frame(10000)
    sh = m.shown()
    rows = sh[long6][3] // LINE_H
    want = min(ANC2, max(AMIN, VH2 - AROOM - LINE_H - (rows * LINE_H + GAP)))
    expect(sh[long6][0] == want == 100 < ANC2, f'a {rows} row line in the 358 px view: its top at {want} ({sh[long6]})')
    # a stop while the page has the engine (Now Playing destroyed): the engine is off and nothing is held
    m.call(PSYMS['ly_stop'], count=2000000)
    expect(m.call(PSYMS['ly_target']) == 0 and m.call(PSYMS['ly_lines']) == 0, 'ly_stop while the page has the engine: stopped')
    m.calls = []; m.call(PSYMS['ly_release'], count=2000000)
    expect(m.calls == [] and m.call(PSYMS['ly_target']) == 0, 'a release after that does nothing: Now Playing\'s parked widgets are gone with the engine')
    # failures leave Now Playing's engine as it was: a refused label, a box too small, no engine at all
    m = LyMachine(SONG); m.init(); m.at(10); m.frame(10000); before = m.shown(); np_box = m.box
    m.create_fail = {'label_create'}
    expect(retarget(m) == 0xffffffff and m.call(PSYMS['ly_target']) == np_box, 'a refused label: -1, the engine still Now Playing\'s')
    m.create_fail = set()
    expect(retarget(m, h=100) == 0xffffffff and m.call(PSYMS['ly_target']) == np_box, 'a view under three rows high: refused')
    m.at(10); m.frame(10000)
    expect(m.shown() == before and m.call(PSYMS['ly_retarget'], a0=0, a1=m.box2, a2=VH2, count=2000000) == 0xffffffff, 'Now Playing still lays out the same; a null window is refused')
    m = LyMachine(SONG)   # the engine never started
    w2, b2 = m.alloc(0x80), m.alloc(0x80)
    expect(m.call(PSYMS['ly_retarget'], a0=w2, a1=b2, a2=VH2, count=2000000) == 0xffffffff and m.call(PSYMS['ly_target']) == 0, 'no engine to take: refused, nothing made')


SECTIONS = [asset_tests, size_tests, retarget_tests, size_setting_tests, start_tests, follow_tests, dots_tests, face_tests, touch_tests, wrap_tests, tall_tests, overflow_tests, cost_tests, font_tests]

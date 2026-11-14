"""The idle lyrics page (patch/idlelyrics.c, tools/pod_ui.py build_idlelyrics_page, docs/modules/idlelyrics.md): a header (the cover, the title, the artist) over the lyrics, a page of its own
over Now Playing, driven by the lyrics engine of patch/lyrics.c retargeted at the page's 372 px view (the engine's own cases are test/pod/lyrics.py retarget_tests).

What is proved, on the real compiled payload under Unicorn (the stock calls it makes mocked): the built asset (the widgets, their rectangles, which of them take a touch, the scrim picture); the
open, the page's life (open, close, reopen leave nothing held; Now Playing's lyrics pane is the engine's again and correct at every size); the header following the playing track; the lyric
layout in the 372 px view at the three text sizes; no lyrics; the touches (a tap closes, a vertical drag browses, nothing seeks); and every failure of the open leaving Now Playing as it was."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui, mod_nowplaying as mn

ly = sibling('lyrics')
WIN = ly.WIN
mb = sibling('minibar')
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_idlelyrics.bin')
NAME = 'm1plus_idlelyrics'
D, MV, UP, AB = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
DESTROY, PAINT = O['EVT_DESTROY'], O['EVT_AFTER_PAINT']
VH, ANC = O['IL_BOX_H'], O['IL_BOX_H'] * 35 // 100
SIZES = ly.SIZES
OPACITY = ly.OPACITY


class IM(ly.LyMachine):
    """Now Playing with its lyrics (LyMachine) and the page's window and widgets. open() runs idlelyrics_open_idle; the engine's view is the page's box from then on (self.box), Now Playing's is self.np_box."""

    def __init__(self, lines=ly.SONG, size=None, **kw):
        super().__init__(lines, **kw)
        self.np_box = self.box
        self.iwin = self.alloc(0x80)
        self.windows[NAME] = self.iwin
        for n in ('il_view', 'il_title', 'il_artist', 'il_lyrics', 'il_hint'): self.widget(n)
        self.ibox = self.widgets['il_lyrics']
        self.setword(self.ibox, 28); self.setword(self.ibox + 4, 96)
        self.screen(True)
        if size is not None: self.fs[ly.LYRSIZE] = f'{size}\n'.encode()

    log = ()

    def call(self, *a, **k):
        """Every call of the machine resets self.calls; the page's tests read self.log, what the calls since clear() did."""
        r = super().call(*a, **k)
        self.log = list(self.log) + self.calls
        return r

    def clear(self): self.log = []
    def lognames(self): return [c[0] for c in self.log]

    def start(self):
        self.init()
        self.at(0)

    def open(self, fn='idlelyrics_open_idle'):
        self.clear()
        r = self.call(PSYMS[fn], count=20000000) & 0xffffffff
        if r == 0 and self.call(PSYMS['ly_target']) == self.ibox:
            self.box = self.ibox; self.stage(2, self.iwin)
        return r

    def first(self):
        """The page timer's first tick (50 ms), then the 500 ms ones."""
        self.clear()
        self.call(PSYMS['il_tick'], a0=0, count=20000000)
        self.frame(10000)
        return self.log

    def itick(self, pos=None):
        if pos is not None: self.play = pos
        self.clear()
        self.clock += 500
        self.call(PSYMS['il_tick'], a0=0, count=20000000)
        self.frame(10000)
        return self.log

    def back_np(self):
        self.box = self.np_box

    def ev(self, kind, x, y):
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30)); self.setword(e, kind); self.setword(e + O['PE_X'], x); self.setword(e + O['PE_Y'], y)
        return e

    def touch(self, kind, x, y, on='il_view'):
        """A pointer event at window coordinates (x, y) for the widget `on`: its listeners in the order they were added (the engine's first on the box)."""
        e = self.ev(kind, x, y); r = []
        if on == 'il_lyrics': r.append(self.call(PSYMS['ly_on_touch'], a0=self.ibox, a1=e, count=4000000))
        r.append(self.call(PSYMS['il_on_touch'], a0=0, a1=e, count=4000000))
        return r

    def gesture(self, a, b, on='il_view', steps=()):
        self.clear()
        out = self.touch(D, *a, on=on)
        for s in steps: out += self.touch(MV, *s, on=on)
        out += self.touch(MV, *b, on=on) + self.touch(UP, *b, on=on)
        return out

    def count(self, name): return sum(c[0] == name for c in self.log)

    def record_track(self, title, artist, path):
        r = self.record(album='Album ' + title, artist=artist, path=path, title=title, name=os.path.basename(path), rid=len(path))
        Machine.play(self, [r], 0)
        return r

    def header(self):
        """[(widget, text)] the page set on the title and the artist since clear()."""
        w = (self.widgets['il_title'], self.widgets['il_artist'])
        return [(c[1], c[2]) for c in self.log if c[0] == 'widget_set_text_utf8' and c[1] in w]


def opened(lines=ly.SONG, size=None, pos=10, track=True):
    m = IM(lines, size=size); m.start()
    if track: m.record_track('Walking Down the Street', 'The Midnight Drivers', '/mnt/mmc/a/walk.flac')
    m.play = pos
    assert m.open() == 0
    m.first(); m.itick(pos)
    return m


def model(lines, cur, lh, gap, vh=VH, anc=ANC):
    """{text: (y, opacity)} of the one-row lines laid out round line `cur` (ly_anchor at 0.35 of the view, opacity by distance times the edge factor)."""
    out = {}
    for i, (_, t) in enumerate(lines):
        y = anc + (i - cur) * (lh + gap)
        e = min(y + lh - lh // 2, vh - (y + lh // 2))
        f = 0 if e <= 0 else 255 if e >= O['LY_FADE'] else e * 255 // O['LY_FADE']
        op = OPACITY[min(abs(i - cur), 4)] * f // 255
        if op and y + lh > 0 and y < vh: out[t] = (y, op)
    return out


def asset_tests(ctx):
    expect = ctx.expect
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    expect(tree.name == NAME + '_page' and tree.get('fullscreen') == 'true' and tree.get('theme') == 'playing_page' and (tree.w, tree.h) == (0, 0),
           'a fullscreen window (480 px, no status bar) that takes Now Playing\'s theme for the lyric label styles')
    expect([c.name for c in tree.children if c.name] == ['img_il_tint', 'img_il_scrim', 'il_view', 'il_title', 'il_artist', 'il_lyrics', 'il_hint', 'label_title'], 'tint, scrim, the touch view, the header texts, the lyrics view, the hint, the hidden title')
    g = lambda n: (by[n].x, by[n].y, by[n].w, by[n].h)
    expect(g('il_view') == (0, 0, 320, 480) and g('img_il_tint') == (0, 0, 320, 480) and g('img_il_scrim') == (0, 0, 320, 480), 'the view, the tint and the scrim cover the window')
    expect(g('il_title') == (O['IL_TEXT_X'], O['IL_TITLE_Y'], O['IL_TEXT_W'], O['IL_TITLE_H']) == (96, 25, 196, 24) and g('il_artist') == (96, 49, 196, 22)
           and (25 + 12) + (49 + 11) == 2 * (20 + 28) + 1 and 96 == 28 + 56 + 12 and 96 + 196 == 320 - 28,
           f'the title (96, 25, 196 x 24) and the artist (96, 49, 196 x 22): 23 px between their centres, centred on the 56 px cover at y 20 (within 1 px), 12 px right of it, ending at the lyrics\' right edge ({g("il_title")}, {g("il_artist")})')
    expect(by['il_title'].type == by['il_artist'].type == 'hscroll_label' and by['il_title'].get('ellipses') == 'true' and by['il_title'].get('sensitive') == 'false'
           and by['il_title'].get('style:normal:font_size') == '19' and by['il_artist'].get('style:normal:font_size') == '17' and by['il_title'].get('style:normal:text_color').lower() == '#ffffff'
           and by['il_artist'].get('style:normal:text_color').lower() == '#d0d0d0', 'one line each, cut with an ellipsis, 19 px white and 17 px #D0D0D0 (the mini bar\'s colours, a size up)')
    expect(g('il_lyrics') == (28, 96, 264, 372) and by['il_lyrics'].type == 'scroll_view' and 96 + 372 == 468 and O['IL_ART_X'] == 28 and O['IL_ART'] == 56 and O['IL_ART_Y'] == 20 and O['IL_ART_R'] == 8 and O['IL_HEAD_H'] == 88 == 20 + 56 + 12,
           'the lyrics view is 264 x 372 at (28, 96); the header 88 px with the cover 56 px at (28, 20), radius 8, 12 px above the header\'s end')
    h = by['il_hint']
    expect(h.get('visible') == 'false' and h.get('sensitive') == 'false' and h.get('tr_text') == 'No Lyrics Found' and h.get('style:normal:font_size') == '20' and h.get('style:normal:text_color').lower() == '#aaaaaa'
           and h.get('style:normal:text_align_h') == 'center' and g('il_hint') == g('il_lyrics'), 'the hint: hidden and insensitive, "No Lyrics Found" 20 px #AAAAAA centred in the lyrics view')
    expect(by['label_title'].get('visible') == 'false' and by['label_title'].get('tr_text') == 'Lyrics', 'label_title is the page\'s hidden name')
    root = asset_tree(os.path.join(WORK, UI)); root.h = 480
    m = Machine()
    for (x, y), want in {(160, 52): 'il_view', (10, 300): 'il_view', (5, 300): 'il_view', (100, 95): 'il_view', (100, 96): 'il_lyrics', (291, 467): 'il_lyrics', (300, 200): 'il_view', (100, 470): 'il_view'}.items():
        got = stock_target(m, root, x, y)
        expect(got[-1] == want, f'a touch at ({x}, {y}) reaches {want} ({got})')
    im = asset_image('np_scrim_idle')
    al = [im.getpixel((9, y))[3] for y in range(480)]
    expect(im.size == (320, 480) and al == [mn.lscrim_alpha(y, 480) for y in range(480)] and al == al[::-1] and max(al) == mn.LSCRIM_ALPHA == 68 and {im.getpixel((x, 5))[:3] for x in (0, 319)} == {(0, 0, 0)}
           and os.path.getsize(asset_path('np_scrim_idle')) < 4000, 'np_scrim_idle.png: the lyrics scrim (alpha 68, smoothstep edges of 44 rows) over the whole 480 px window, black, symmetric')
    im = asset_image('np_tint_idle')
    expect(im.size == (320, 480) and [im.getpixel((9, y))[3] for y in range(480)] == [mn.tint_alpha(y, 480) for y in range(480)] and mn.tint_alpha(0, 480) == 38 and mn.tint_alpha(479, 480) == 235,
           'np_tint_idle.png: the Now Playing gradient (alpha 38 .. 235) over the 480 rows of the page')


def open_tests(ctx):
    expect = ctx.expect
    m = IM(); m.start()
    np_kids = len(m.children[m.np_box])
    m.record_track('Walking Down the Street', 'The Midnight Drivers', '/mnt/mmc/a/walk.flac')
    m.play = 10
    r = m.open(); calls = list(m.log)
    expect(r == 0 and ('window_open', NAME) in calls and (m.iwin, DESTROY) in m.bound, 'the page opens its window and binds its destroy')
    expect(m.call(PSYMS['ly_target']) == m.ibox and len(m.children[m.ibox]) == O['LY_POOL'] + 4 and len(m.children[m.np_box]) == np_kids, 'the engine drives the page\'s view (its pool of labels, the probe and the dots); Now Playing\'s pool is kept')
    expect([c for c in calls if c[0] == 'timer_add'] == [('timer_add', PSYMS['il_tick'], O['IL_FIRST_MS'])], 'one page timer, 50 ms first')
    expect(all((m.widgets['il_view'], e) in m.bound for e in (D, MV, UP, AB, PAINT)) and all((m.ibox, e) in m.bound for e in (D, MV, UP, AB)), 'listeners: pointer and paint on the view, pointer on the lyrics view (the engine\'s and the page\'s)')
    expect(not any(c[0] in ('seek_time', 'widget_grab') for c in calls) and m.call(PSYMS['idlelyrics_open_idle']) == 0 and m.count('window_open') == 1, 'a second open returns 0 and opens nothing')
    m.clear()
    expect(m.call(PSYMS['idlelyrics_open_idle']) == 0 and m.count('window_open') == 0, 'the idle variant on an open page: 0, nothing opened')
    expect(m.call(PSYMS['idlelyrics_up']) == 1, 'idlelyrics_up says the page is open')
    c = m.first()
    expect(m.header() == [(m.widgets['il_title'], 'Walking Down the Street'), (m.widgets['il_artist'], 'The Midnight Drivers')], f'the header shows the title and the artist ({m.header()})')
    expect(('timer_modify', 0x777, O['IL_TICK_MS']) in c, 'after the first look the timer runs every 500 ms')
    S = O['IL_ART']
    b = next(iter(m.bitmaps)); data, bw, bh = m.bitmaps[b]
    px = bytes(m.u.mem_read(data, S * S * 4))
    alpha = [struct.unpack_from('<I', px, 4 * (y * S + x))[0] >> 24 for y in range(8) for x in range(8)]
    corners = [struct.unpack_from('<I', px, 4 * (y * S + x))[0] >> 24 for x, y in ((0, 0), (S - 1, 0), (0, S - 1), (S - 1, S - 1))]
    expect((bw, bh) == (56, 56) and len(m.bitmaps) == 1 and alpha == [255 - c for c in mb.corner_coverage(8)] and corners == [0, 0, 0, 0] and struct.unpack_from('<I', px, 4 * (S // 2))[0] >> 24 == 255,
           'one 56 px cover bitmap with the mini bar\'s anti-aliased corners at radius 8')
    pe = m.alloc(0x40); m.u.mem_write(pe, bytes(0x40)); m.setword(pe + O['EVENT_PAINT_CANVAS'], 0x22220000)
    m.blits = []; m.call(PSYMS['il_on_paint'], a0=0, a1=pe, count=2000000)
    expect(m.blits == [(b, (0, 0, 56, 56), (28, 20, 56, 56))], f'the paint draws the resident cover at (28, 20), 56 x 56 ({m.blits})')
    expect((m.iwin, 'normal:bg_color', O['NP_NEUTRAL']) in m.styles, 'the window takes Now Playing\'s colour')
    s = m.shown()
    expect(s['Line two'][0] == ANC == 130 and s['Line two'][1] == 255, f'the lyrics are laid out in the page\'s view, the current line at 130 ({s})')
    expect(m.props.get((m.widgets['il_hint'], 'visible')) in (None, 0), 'lyrics: no hint')
    # the hint follows the lyrics
    m.set_lines([]); m.itick()
    h = m.widgets['il_hint']
    expect(('widget_set_visible', h, 1) in m.log and m.props.get((h, 'sensitive')) in (None, 0) and m.call(PSYMS['ly_lines']) == 0 and m.shown() == {}, 'no lyrics: the hint shows (insensitive), no line is laid out, the header stays')
    m.clear(); m.itick()
    expect(not any(c[0] in ('widget_set_visible', 'widget_set_text_utf8') for c in m.log), 'a tick with nothing changed touches nothing')
    m.set_lines(ly.SONG); m.itick(10)
    expect(('widget_set_visible', h, 0) in m.log and 'Line two' in m.shown(), 'lyrics arriving take the hint away and fill the view')
    # a track change: the header, the cover
    n = len(m.bitmaps)
    m.record_track('Blue in Green', 'Miles Davis', '/mnt/mmc/a/blue.flac')
    m.itick()
    expect(m.header() == [(m.widgets['il_title'], 'Blue in Green'), (m.widgets['il_artist'], 'Miles Davis')] and len(m.bitmaps) == n, f'a new track: the title and the artist change, the cover is made again in the same bitmap ({m.header()})')
    m.set_lines([(0, 'New song first line'), (6, 'New song second')]); m.itick(0)
    expect('New song first line' in m.shown() and m.shown()['New song first line'][0] == ANC, 'its lyrics (new stock rows) replace the old ones')


def rows_tests(ctx):
    """ly_has_rows (the dispatcher's question, patch/bigcover.c bc_timed_open): the child count of Now Playing's scroll_lrc, read live, before any engine tick."""
    expect = ctx.expect
    m = IM(); m.start()
    expect(m.call(PSYMS['ly_has_rows']) == 1 and m.call(PSYMS['idlelyrics_up']) == 0, 'with lyric rows in scroll_lrc: 1 (before the first tick of the engine), the page is not up')
    m.set_lines([])
    expect(m.call(PSYMS['ly_has_rows']) == 0, 'the rows gone (a track without lyrics, or stock has not built them yet): 0, read live')
    m.set_lines(ly.SONG)
    expect(m.call(PSYMS['ly_has_rows']) == 1, 'rebuilt: 1 again')
    m = IM(); m.call(PSYMS['ly_stop'])
    expect(m.call(PSYMS['ly_has_rows']) == 0, 'the engine not running: 0')


def life_tests(ctx):
    expect = ctx.expect
    m = IM(); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac')
    m.play = 10; m.at(10); m.frame(10000)
    before = m.shown(); np_kids = list(m.children[m.np_box])
    for rnd in range(3):
        assert m.open() == 0
        m.first(); m.itick(10)
        expect(m.call(PSYMS['ly_target']) == m.ibox and 'Line two' in m.shown(), f'round {rnd}: open, the engine is the page\'s')
        m.clear()
        m.fire(DESTROY, win=m.iwin)
        expect(m.count('timer_remove') >= 1 and not m.bitmaps and m.call(PSYMS['ly_target']) == m.np_box, f'round {rnd}: destroy removes the timer, frees the cover bitmap and gives the engine back to Now Playing ({m.lognames()})')
        m.back_np(); m.windows[NAME] = m.iwin = m.alloc(0x80)
        m.ibox = m.alloc(0x80); m.setword(m.ibox, 28); m.setword(m.ibox + 4, 96); m.widgets['il_lyrics'] = m.ibox
        m.bound = {k: v for k, v in m.bound.items() if k[0] in (m.np_box, WIN)}
        m.at(10); m.frame(10000)
        expect(m.shown() == before and m.children[m.np_box] == np_kids and m.props.get((m.view, 'visible')) == 0, f'round {rnd}: Now Playing\'s lyrics pane is laid out as before ({m.shown()})')
        m.down(50, ly.ANCHOR + ly.PITCH + 17); m.up(50, ly.ANCHOR + ly.PITCH + 17)
        expect(m.seeks and m.seeks[-1] == 15, 'and a tap on a line seeks again there')
        m.seeks = []
    # every size: Now Playing is right after the page
    for k, (px, lh, gap, sf) in SIZES.items():
        m = IM(size=k); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); m.play = 10; m.at(10); m.frame(10000)
        before = m.shown(); assert m.open() == 0
        m.first(); m.itick(10)
        m.fire(DESTROY, win=m.iwin); m.back_np(); m.at(10); m.frame(10000)
        expect(m.shown() == before and m.shown()['Line two'][2] == ly.BOLD + sf and m.shown()['Line two'][0] == ly.ANCHOR, f'size {px}: Now Playing\'s pane is as before after the page')
    # Now Playing coming back to the front gives the engine back (np_on_foreground -> ly_refresh); the page's tick then closes the page once
    m = IM(); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); assert m.open() == 0; m.first()
    m.call(PSYMS['np_on_foreground'], a0=WIN, a1=0)
    expect(m.call(PSYMS['ly_target']) == m.np_box, 'Now Playing in front: the engine is its again')
    c = m.itick()
    expect(('window_close', m.iwin) in c and 'navigator_back' not in [x[0] for x in c], 'the idle timer closes its own window, never the window on top (Now Playing is in front here)')
    expect([x[0] for x in c].count('window_close') == 1 and not any(x[0] in ('widget_set_text_utf8', 'canvas_draw_image') for x in c) and m.call(PSYMS['ly_target']) == m.np_box, 'the page\'s tick without the engine closes it (once) and does no work')
    c = m.itick()
    expect('window_close' not in [x[0] for x in c], 'and not again')
    m.fire(DESTROY, win=m.iwin)
    expect(m.call(PSYMS['ly_target']) == m.np_box, 'the destroy after that leaves Now Playing\'s engine alone')
    # Now Playing destroyed under the page: the engine is off, the page closes
    m = IM(); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); assert m.open() == 0; m.first()
    m.fire(DESTROY, win=WIN)
    expect(m.call(PSYMS['ly_target']) == 0, 'Now Playing\'s end stops the engine, parked pool and all')
    c = m.itick()
    expect([x[0] for x in c].count('window_close') == 1, 'the page closes itself')
    m.fire(DESTROY, win=m.iwin)
    expect(not m.bitmaps and m.call(PSYMS['ly_target']) == 0, 'and its destroy frees the cover and starts nothing')
    # a dark screen: the tick does no visual work
    m = opened(); m.screen(False); c = m.itick()
    expect(not any(x[0] in ('widget_set_text_utf8', 'widget_move', 'widget_set_style', 'bitmap_create_ex') for x in c), 'screen off: no work')


def layout_tests(ctx):
    expect = ctx.expect
    lines = [(0, 'Line zero'), (5, 'Line one'), (10, 'Line two'), (15, 'Line three'), (20, 'Line four'), (25, 'Line five'), (30, 'Line six'), (35, 'Line seven'), (40, 'Line eight'), (45, 'Line nine'), (50, 'Line ten'), (55, 'Line eleven')]
    for k, (px, lh, gap, sf) in SIZES.items():
        for cur in (0, 3, 6):
            m = IM(lines, size=k); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac')
            assert m.open() == 0
            m.first(); m.itick(cur * 5)
            s = m.shown(); want = model(lines, cur, lh, gap)
            got = {t: (v[0], v[1]) for t, v in s.items()}
            expect(got == want and all(v[2] == ly.BOLD + sf and v[3] == lh for v in s.values()), f'size {px}, line {cur} current: the lines sit at 130 + n x {lh + gap}, opacity by distance times the 372 px edge fade ({got} vs {want})')
        expect(want and min(v[0] for v in want.values()) >= -lh, f'size {px}: the lines above the current one show too')
    m = IM(lines, size=2); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); assert m.open() == 0; m.first(); m.itick(5 * 5)
    expect(len(m.shown()) >= 7, f'Large: the 372 px view shows at least 7 lines round the current ({len(m.shown())})')
    # the intro dots, the anchor rule of a tall line, at the page's height
    intro = ly.INTRO
    m = IM(intro); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); assert m.open() == 0; m.first(); m.itick(0); m.itick(0)
    ds = m.dot_state()
    expect(all(d[2] == ANC + (ly.LINE_H - ly.DOT) // 2 for d in ds) and m.shown()['Intro line'][0] == ANC + ly.LINE_H + ly.GAP, f'the intro dots sit on the anchor row (130) and the first line one pitch lower ({ds}, {m.shown()})')


def touch_tests(ctx):
    expect = ctx.expect
    # a tap anywhere closes: the header, the margins, the lyrics (no seek)
    for on, pt in (('il_view', (50, 52)), ('il_view', (10, 300)), ('il_view', (5, 470)), ('il_view', (200, 20)), ('il_lyrics', (100, 130 + 96 + 17)), ('il_lyrics', (150, 200)), ('il_lyrics', (150, 100))):
        m = opened(); m.seeks = []
        r = m.gesture(pt, (pt[0] + 3, pt[1] - 2), on=on)
        expect(m.count('window_close') == 1 and not m.seeks and set(r) == {0} and not any(c[0] in ('widget_grab', 'seek_time') for c in m.log), f'a tap at {pt} on {on} closes the page: no seek, RET_OK, no grab')
    # a tap that moves 10 px or more is not a tap
    m = opened()
    m.gesture((100, 200), (100, 190), on='il_lyrics')
    expect(m.count('window_close') == 0, 'a 10 px move is a drag, not a tap')
    m = opened(); m.gesture((100, 200), (109, 200), on='il_lyrics')
    expect(m.count('window_close') == 1, 'a 9 px move is still a tap')
    m = opened(); m.gesture((100, 200), (110, 200), on='il_view')
    expect(m.count('window_close') == 0, 'a 10 px sideways move on the view is no tap either')
    # a vertical drag over the lyrics browses them as on Now Playing: the lines follow the finger after the first 10 px; no close, no seek
    m = opened(pos=10); m.seeks = []
    y0 = m.shown()['Line two'][0]
    m.gesture((150, 300), (150, 240), on='il_lyrics', steps=((150, 290), (150, 270)))
    s = m.shown()
    expect(m.count('window_close') == 0 and not m.seeks and s['Line two'][0] == y0 - 50,
           f'a vertical drag of 60 px browses: the lines move 50 px (the first 10 px start the drag), nothing closes or seeks ({s["Line two"]} from {y0})')
    expect(s['Line two'][1] == ly.fade(255, s['Line two'][0], 1) and s['Line one'][1] <= ly.fade(255, s['Line one'][0], 1), 'while browsing the current line is full')
    # after 3 s without a touch the lines return to the current one
    m.clock += 3500; m.itick(); m.itick()
    expect(m.shown()['Line two'][0] == y0, 'after the browse the lines come back to the current line')
    # a drag on the header does not close and moves nothing
    m = opened(); y0 = m.shown()['Line two'][0]
    m.gesture((150, 30), (150, 120), on='il_view')
    expect(m.count('window_close') == 0 and m.shown()['Line two'][0] == y0, 'a drag on the header closes nothing and moves no line')
    # an abort cancels the touch
    m = opened(); m.touch(D, 100, 100); m.touch(AB, 100, 100); m.clear(); m.touch(UP, 100, 100)
    expect(m.count('window_close') == 0, 'an abort ends the touch: the UP after it closes nothing')
    # the keys: nothing of the page binds a key handler; the stock ones are not touched
    m = opened()
    expect(not any(c[0] in ('widget_set_prop_int',) and c[2] == 'key' for c in m.log) and all(k[1] in (D, MV, UP, AB, PAINT, DESTROY) for k in m.bound if k[0] in (m.iwin, m.widgets['il_view'], m.ibox)),
           'the page listens to pointer, paint and destroy only: the hardware keys keep their stock actions')


def fail_tests(ctx):
    expect = ctx.expect

    def intact(m, what):
        """Now Playing as before: the engine is its own, its lines laid out and a tap seeks."""
        m.back_np(); m.play = 10; m.at(10); m.frame(10000)
        s = m.shown()
        m.seeks = []; m.down(50, ly.ANCHOR + ly.PITCH + 17); m.up(50, ly.ANCHOR + ly.PITCH + 17)
        expect(m.call(PSYMS['ly_target']) == m.np_box and s['Line two'][0] == ly.ANCHOR and m.seeks == [15] and m.props.get((m.view, 'visible')) == 0, f'{what}: Now Playing\'s lyrics pane is as it was ({s["Line two"]}, {m.seeks})')

    m = IM()   # no Now Playing page at all
    r = m.open()
    expect(r == 0xffffffff and m.count('window_open') == 0 and m.count('navigator_back') == 0 and m.count('timer_add') == 0, f'no Now Playing window: -1, nothing opened ({m.lognames()})')
    m = IM(); m.create_fail = {'label_create'}; m.init()
    r = m.open()
    expect(r == 0xffffffff and m.count('window_open') == 0 and m.call(PSYMS['ly_target']) == 0, 'Now Playing without its lyrics engine (a label was refused at its start): -1, nothing opened')
    m = IM(); m.start(); m.windows[NAME] = 0
    r = m.open()
    expect(r == 0xffffffff and m.count('navigator_back') == 0 and m.count('timer_add') == 0, 'the window cannot be opened: -1, nothing to close')
    intact(m, 'no window')
    m = IM(); m.start(); m.widget_on_fail = {DESTROY}
    r = m.open()
    expect(r == 0xffffffff and m.count('navigator_back') == 1 and m.call(PSYMS['ly_target']) == m.np_box and m.count('timer_add') == 0 and m.count('ly_retarget') == 0, 'the destroy handler is refused: -1, the window goes back, the engine untouched')
    intact(m, 'refused destroy'); m.widget_on_fail = set(); m.windows[NAME] = m.iwin
    expect(m.open() == 0, 'and a later open works (nothing stale held)')
    for missing in ('il_view', 'il_title', 'il_artist', 'il_lyrics', 'il_hint'):
        m = IM(); m.start(); del m.widgets[missing]
        r = m.open()
        expect(r == 0xffffffff and m.count('navigator_back') == 1 and m.count('timer_add') == 0 and m.call(PSYMS['ly_target']) == m.np_box, f'{missing} missing: -1, the window goes back')
        intact(m, f'{missing} missing')
    m = IM(); m.start(); m.create_fail = {'label_create'}
    r = m.open()
    expect(r == 0xffffffff and m.count('navigator_back') == 1 and m.count('timer_add') == 0 and m.call(PSYMS['ly_target']) == m.np_box, 'a label refused for the page\'s pool: -1, the window goes back')
    m.create_fail = set(); intact(m, 'refused labels')
    m = IM(); m.start(); m.timer_fail = True
    r = m.open()
    expect(r == 0xffffffff and m.count('navigator_back') == 1 and m.call(PSYMS['ly_target']) == m.np_box and not m.bitmaps, 'the page timer is refused: -1, the engine is given back, the window goes back')
    m.timer_fail = False; intact(m, 'refused timer')
    m.windows[NAME] = m.iwin
    expect(m.open() == 0, 'and a later open works')
    # the same page opened a second time over the first (a stale window): refused in the engine, not by a second pool
    m = opened(); n = len(m.children[m.ibox])
    expect(m.call(PSYMS['idlelyrics_open_idle']) == 0 and len(m.children[m.ibox]) == n, 'open on an open page: 0, no second pool')




def dreams_tests(ctx):
    """Report: at Small the line "With a head full, a head full of dreams" lost its last word on the idle page. With the fonts' real widths at 22 px the line is two rows
    on the page (the break after "full" in the default font); every row the label draws is inside the rows the engine gave it and inside the view, at every place the line can take."""
    expect = ctx.expect
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    dflt = StbText(Ttf(os.path.join(raw, 'fonts', 'default.ttf')), 22)
    real = lambda s: dflt.layout(s)[1] if s else 0
    line = 'With a head full, a head full of dreams'
    lines = [(0, 'Intro words here'), (5, 'Before the line'), (10, line), (15, 'After the line'), (20, 'And one more')]
    for cur in (1, 2, 3):
        m = IM(lines, size=0, measure=real); m.start(); m.record_track('A', 'B', '/mnt/mmc/a/a.flac'); assert m.open() == 0
        m.first(); m.itick(cur * 5); m.frame(10000)
        s = m.shown()
        h = next(h for h in m.pool() if h in m.texts and m.source_of(m.label_text(h)) == line)
        txt, rows = m.label_text(h), m.props[(h, 'h')] // 25
        expect(real(line) > O['LY_FIT_W'] and s[line][3] == 50 and rows == 2 and txt.split('\n') == ['With a head full, a head full', 'of dreams'] and all(real(r) <= O['LY_ROW_W'] for r in txt.split('\n')),
               f'line {cur} current: two rows of 25 px, the text broken after "full" ({txt!r}, {s[line]})')
        y = s[line][0]
        expect(y + 50 <= VH or s[line][1] == 0, f'line {cur}: both rows are inside the {VH} px view ({y}..{y + 50}) or the line is faded out')


SECTIONS = [asset_tests, open_tests, rows_tests, life_tests, layout_tests, touch_tests, fail_tests, dreams_tests]

"""The Tape page (patch/tape.c, tools/tape_art.py, tools/pod_ui.py build_tape_page, docs/modules/tape.md): a landscape, fullscreen cassette Now Playing page on the portrait panel.

What is proved, on the real compiled payload under Unicorn (the stock calls it makes mocked, the glyphs and bitmaps real memory):
  * the numbers of offsets.inc against tools/tape_art.py (the geometry, the text fields), the built asset (a fullscreen window, one 320 x 480 view, a hidden font label,
    the four installed pictures with the sizes the payload loads), and that the pictures are the generator's output pixel for pixel;
  * the rotation, drawing: landscape (x, y) is the frame's row x, column 319 - y: a glyph block drawn at a known landscape place lands there and nowhere else, clipped to its field's
    rectangle, and the field is restored from the shell before it is drawn again;
  * the rotation, touch: portrait pointer events become landscape taps: a tap on the top left screw (50 x 50 px, drawn darker and turned while held) closes, a tap elsewhere
    plays / pauses, nothing else does anything; no swipe, no grab, no move handler (the stock pull-down from the top edge is left alone);
  * the tape: pack radii (r_supply^2 + r_takeup^2 constant, 16 .. 66 px), the packs seen only through the holes and the clear window, the hubs turning only while playing and
    repeating every 120 degrees, the marks, an invalidate that covers only what changed;
  * the status line (VOL | format | clock | battery, 12 or 11 px, the clock dropped first, then the format) with the shipped font's real advances against tools/tape_art.py;
  * the page's life: one timer retimed with timer_modify, removed on to-background and destroy, no sound.
The emulated frames are written to out/preview/tape-emu-*.png (what the panel would show, turned back to landscape)."""
import math, os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_icons, tape_art
from PIL import Image

UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_tape.bin')
EVT_DOWN, EVT_MOVE, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
EVT_BG, EVT_FG, EVT_DESTROY, EVT_PAINT = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG'], O['EVT_DESTROY'], O['EVT_AFTER_PAINT']
WIN = 0x24200000
SYSBAR = pod.DATA['SYSTEM_BAR'][0]
THEME_FILE = '/mnt/data/m1plus/cassette-theme'
THEMES = tape_art.THEME_NAMES
W, H = O['TP_W'], O['TP_H']                       # landscape 480 x 320
FIELDS = ('title', 'artist', 'album', 'times', 'big', 'model', 'status')
OUT = os.path.join(ROOT, 'out', 'preview')


def px(landscape_xy):
    """The frame's (column, row) of a landscape point: the quarter turn the payload and tools/tape_art.py share."""
    x, y = landscape_xy
    return W_PHYS - 1 - y, x
W_PHYS = H


def land(col, row):
    """The landscape point of a frame pixel."""
    return row, H - 1 - col


def theme_of(i): return THEMES[i]


class TM(Machine):
    """The machine plus what the page calls that the shared mocks do not know: the player's status, the playing time, the quick clicks, the status bar, the font
    (real advances of the shipped font when `font` is set, else the shared block mock) and the invalidate's rectangle."""
    def __init__(self, font=None):
        super().__init__()
        self.status, self.pt, self.cmds, self.rects = 2, None, [], []
        self.window = WIN
        self.top_main = WIN
        self.load_image = 0
        self.canvas = self.canvas_mem = self.alloc(0x80)
        for w in ('tape_view', 'label_tp_font', 'pgbar_battery', 'img_battery', 'label_volume'): Machine.widget(self, w)
        self.setword(SYSBAR, self.alloc(0x80))
        self.props[(self.widgets['pgbar_battery'], 'value')] = 60
        self.battery_img, self.volume = 'bar_power', '42'
        self.wall = 1800000000 + 13 * 3600 + 7 * 60    # 21:07 at +8 (the harness' tz) is set below
        self.tz = 8 * 3600
        self.mode = 0
        self.font = font
        self.mock_ms = 1000
        self.view = self.widgets['tape_view']
        # the view as a widget struct (demo's own widget_to_local walks x, y and the parent): window (0, 0) > view (0, 0)
        win = self.alloc(0x80)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, 0)): self.setword(win + off, v)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, win)): self.setword(self.view + off, v)
        self.images = {n: self.png(n) for n in tape_art.NAMES}
        for n in ('mclGetPlayStatus', 'playpause_quick_click', 'next_quick_click', 'prev_quick_click', 'get_playtimeandlength', 'widget_get_text', 'time_now_ms'):
            self.handlers[pod.FUNCTIONS[n][2]] = n
        self.glyph_calls = 0

    def png(self, n):
        im = asset_image(n)
        return (im.width, im.height, im.tobytes())

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'mclGetPlayStatus': ret = self.status
        elif name == 'time_now_ms': ret = self.mock_ms
        elif name == 'playpause_quick_click':
            self.calls.append(('playpause_quick_click',)); self.cmds.append(('playpause',)); self.status = 2 if self.status != 2 else 3; ret = 1
        elif name in ('next_quick_click', 'prev_quick_click'):
            self.calls.append((name, a1)); self.cmds.append((name[:4], self.word(a0 + 8), a1)); ret = 1
        elif name == 'get_playtimeandlength':
            if self.pt: self.setword(a0, self.pt[0]); self.setword(a1, self.pt[1])
            ret = 1 if self.pt else 0
        elif name == 'widget_get_text':   # the volume label's wide text (pod_text_utf8 encodes it)
            ret = self.alloc(4 * len(self.volume) + 4); self.u.mem_write(ret, struct.pack(f'<{len(self.volume) + 1}I', *map(ord, self.volume), 0))
        elif name == 'widget_get_prop_str':
            prop = self.read_cstr(a1)
            ret = self.cstr(self.battery_img) if prop == 'image' else a2
        elif name == 'widget_invalidate_force':
            self.rects.append(struct.unpack('<4i', self.u.mem_read(a1, 16)) if a1 else None)
        elif name == 'font_get_vmetrics' and self.font is not None:   # the 8 byte struct through the hidden pointer in $a0: the baseline below the line top, descent, line gap
            self.u.mem_write(a0, struct.pack('<hhi', self.font.baseline(a2), -4, 2)); ret = a0
        elif name == 'font_get_glyph' and self.font is not None:   # the shipped font through the stb model (tools/stb_raster.py): bitmap, bearing and advance as AWTK's
            self.glyph_calls += 1
            g = self.font.glyph(chr(a1))
            if not g: ret = 0x10
            else:
                x0, y0, w, h, rows = self.font.bitmap(g, a2)
                data = self.malloc(max(1, w * h)); self.u.mem_write(data, bytes(v for r in rows for v in r) or b'\0')
                self.u.mem_write(a3, struct.pack('<hhHHHBBI', x0, y0, w, h, self.font.step(g, a2) - 1, 0, 0, data)); ret = 0
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    # ---- the world
    def song(self, title, artist='Artist', album='Album', path='/mnt/mmc/m/1.flac', name='1.flac', rid=1):
        return self.record(album=album, artist=artist, path=path, title=title, name=name, rid=rid)

    def playing(self, title='So What', artist='Miles Davis', album='Kind of Blue', pos=14, length=562, path='/mnt/mmc/m/so-what.flac'):
        self.play([self.song(title, artist, album, path=path, name=os.path.basename(path))], 0)
        self.pt = (pos, length)

    def open(self):
        self.calls = []
        ret = self.call(PSYMS['tape_open'], count=60000000)
        return ret & 0xffffffff

    def open_idle(self):
        self.calls = []
        return self.call(PSYMS['tape_open_idle'], count=60000000) & 0xffffffff

    def first(self):
        """The 50 ms one-shot: the first look; the page timer after it."""
        self.calls = []; self.rects = []
        self.call(PSYMS['tp_first'], a0=0, count=200000000)

    def tick(self, ms=70):
        self.mock_ms += ms
        self.calls = []; self.rects = []
        self.call(PSYMS['tp_tick'], a0=0, count=200000000)

    def paint(self):
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.blits = []
        self.call(PSYMS['tp_on_paint'], a0=0, a1=ev, count=200000000)
        return list(self.blits)

    def frame_bitmap(self):
        """(data address, w, h) of the page's frame: the last 320 x 480 bitmap it made."""
        return [v for v in self.bitmaps.values() if v[1:] == (320, 480)][-1]

    def frame(self):
        data, w, h = self.frame_bitmap()
        return bytes(self.u.mem_read(data, w * h * 4))

    def landscape(self):
        """The frame as the landscape picture it holds: turned back (rotate 90 degrees counterclockwise)."""
        return Image.frombytes('RGBA', (320, 480), self.frame()).transpose(Image.ROTATE_90)

    def pixel(self, x, y):
        """The frame's pixel at landscape (x, y) as (r, g, b, a)."""
        data, w, h = self.frame_bitmap()
        col, row = px((x, y))
        return tuple(self.u.mem_read(data + (row * w + col) * 4, 4))

    # ---- pointer events at PORTRAIT coordinates (what the panel reports)
    def ptr(self, kind, col, row, t=0):
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, {'down': EVT_DOWN, 'move': EVT_MOVE, 'up': EVT_UP, 'abort': EVT_ABORT}[kind]); self.setword(e + 8, t); self.setword(e + 0x18, col); self.setword(e + 0x1c, row)
        self.calls = []
        self.call(PSYMS['tp_on_touch'], a0=0, a1=e, count=4000000)

    def gesture(self, a, b, dt=120):
        """A finger from landscape point a to b (drawn in landscape, delivered in the panel's coordinates): the calls of the whole gesture."""
        calls = []
        (c0, r0), (c1, r1) = px(a), px(b)
        self.ptr('down', c0, r0, 1000); calls += self.calls
        for i in range(1, 5):
            self.ptr('move', c0 + (c1 - c0) * i // 4, r0 + (r1 - r0) * i // 4, 1000 + dt * i // 4); calls += self.calls
        self.ptr('up', c1, r1, 1000 + dt); self.calls = calls + self.calls
        return list(self.calls)


def machine(font=None, playing=True, status=2, theme=0, **kw):
    m = TM(font)
    m.status = status
    if theme: m.fs[THEME_FILE] = b'%d\n' % theme
    if playing: m.playing(**kw)
    return m


def opened(**kw):
    m = machine(**kw)
    assert m.open() == 0
    m.timers = []
    m.first()
    return m


def real_font():
    """The shipped font through the stb model (tools/stb_raster.py), as AWTK rasterises and measures it."""
    from stb_raster import StbFont
    return StbFont(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))


def dump(m, name):
    os.makedirs(OUT, exist_ok=True)
    m.landscape().convert('RGB').save(os.path.join(OUT, f'tape-emu-{name}.png'))


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def number_tests(ctx):
    """offsets.inc and tools/tape_art.py say the same."""
    expect = ctx.expect
    A = tape_art
    expect((O['TP_W'], O['TP_H']) == (A.W, A.H) == (480, 320), 'the landscape picture is 480 x 320')
    expect((O['TP_TOP_X'], O['TP_TOP_Y'], O['TP_TOP_X'] + O['TP_TOP_W'], O['TP_TOP_Y'] + O['TP_TOP_H']) == A.TOP_RECT, f'tape_top\'s rectangle {A.TOP_RECT}')
    expect((O['TP_REEL_X0'], O['TP_REEL_X1'], O['TP_REEL_Y']) == (*A.REEL_CX, A.REEL_CY) and O['TP_HOLE_R'] == A.HOLE_R and O['TP_HUB_R'] == A.HUB_R, 'the reels\' places, the hole and the hub')
    expect((O['TP_PACK_MIN'], O['TP_PACK_MAX'], O['TP_HUB_PX'], O['TP_SPRITES']) == (A.PACK_MIN, A.PACK_MAX, A.HUB_PX, A.SPRITES), 'the tape pack\'s radii, the hub sprite and its 12 frames')
    expect((O['TP_CLEAR_X0'], O['TP_CLEAR_Y0'], O['TP_CLEAR_X1'], O['TP_CLEAR_Y1']) == A.CLEAR and O['TP_CLEAR_R'] == 4, f'the clear window {A.CLEAR}, corners 4 px')
    expect(O['TP_MARK_PX'] == A.MARK_PX and [(O['TP_PLAY_X'], O['TP_PLAY_Y'], O['TP_PLAY_X'] + A.MARK_PX, O['TP_PLAY_Y'] + A.MARK_PX),
                                              (O['TP_REPEAT_X'], O['TP_REPEAT_Y'], O['TP_REPEAT_X'] + A.MARK_PX, O['TP_REPEAT_Y'] + A.MARK_PX),
                                              (O['TP_SCREW_X'], O['TP_SCREW_Y'], O['TP_SCREW_X'] + A.MARK_PX, O['TP_SCREW_Y'] + A.MARK_PX)] == A.mark_rects(), 'the marks\' cells, the close screw\'s the third')
    expect(THEMES == ('normal', 'chrome', 'metal') and set(A.THEMES) == set(THEMES), 'three themes in the saved order: Normal (0, the default), Chrome (1), Metal (2)')
    expect(O['TP_SCREW_X'] == A.mark_rects()[2][0] and A.CLOSE_RECT == (O['TP_CLOSE_X0'], O['TP_CLOSE_Y0'], O['TP_CLOSE_X1'], O['TP_CLOSE_Y1']), 'the close screw\'s cell and touch area')
    expect(O['TP_LUT_N'] > (2 * (A.PACK_MAX + 1)) ** 2, 'the distance table reaches a full pack')
    expect(O['TP_PLAY_MS'] < O['TP_IDLE_MS'] and 60 <= O['TP_PLAY_MS'] <= 80, 'the timer: 70 ms while playing, 500 ms paused')
    d = open(DEMO, 'rb').read(); image = bytearray(d)
    expect(all(struct.unpack_from('<I', d, pod.fileoff(image, a))[0] == old for a, old, _ in pod.TAPE_PINS) and len(pod.TAPE_PINS) == 3,
           'the stock words the page relies on are as pinned: widget_invalidate_force passes its rectangle (16 bytes, the widget\'s own coordinates) to widget_invalidate')
    # the label's fields: rectangles that do not overlap, inside the label, text boxes inside their rectangle
    rects = {n: A.TEXT[n]['rect'] for n in FIELDS}
    over = [(a, b) for i, a in enumerate(FIELDS) for b in FIELDS[i + 1:]
            if min(rects[a][2], rects[b][2]) > max(rects[a][0], rects[b][0]) and min(rects[a][3], rects[b][3]) > max(rects[a][1], rects[b][1])]
    expect(not over, f'the text fields\' rectangles do not overlap ({over})')
    lab = A.LABEL
    expect(all(lab[0] <= r[0] and r[2] <= lab[2] and lab[1] <= r[1] and r[3] <= lab[3] for r in rects.values()), 'every field is on the label')
    for n in FIELDS:
        f = A.TEXT[n]; r = f['rect']
        expect(r[1] <= f['y'] - f['px'] // 2 and f['y'] + f['px'] // 2 <= r[3] and r[0] <= f['x'] <= r[2], f'{n}: the line fits its rectangle')
    # the fields in the payload: the table in tape.c is the python one (read through what the payload draws, below); here the band stays whole
    expect(A.TEXT['big']['rect'][1] > 101 and A.TEXT['big']['rect'][3] < 191, 'the big A stays inside the band\'s edge lines')


def asset_tests(ctx):
    expect = ctx.expect
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    expect(tree.name == 'm1plus_tape_page' and tree.get('fullscreen') == 'true' and (tree.w, tree.h) == (0, 0), 'the window is fullscreen (480 px, the status bar not drawn)')
    by = {w.name: w for w in tree.walk() if w.name}
    v = by['tape_view']
    expect((v.x, v.y, v.w, v.h) == (0, 0, 320, 480) and v.get('sensitive') != 'false' and v.get('visible') != 'false', 'tape_view is the whole window and takes the touches')
    f = by['label_tp_font']
    expect(f.get('visible') == 'false' and f.get('sensitive') == 'false' and by['label_title'].get('visible') == 'false', 'the font label and the title are hidden and insensitive')
    expect(by['label_title'].get('tr_text') == 'Cassette Mode', 'label_title carries the page\'s name, Cassette Mode')
    expect([c.name for c in tree.children if c.name] == ['tape_view', 'tp_styles'], 'one view over the window, the hidden holder after it')
    root = asset_tree(os.path.join(WORK, UI)); root.h = 480
    m = Machine()
    for x, y in ((160, 240), (5, 5), (315, 475)):
        got = stock_target(m, root, x, y)
        expect(got[-1] == 'tape_view', f'a touch at ({x}, {y}) reaches tape_view ({got})')
    # the pictures: sizes the payload loads, the generator's output pixel for pixel, no image in the tree is bigger than the budget
    sizes = {'tape_top': (74, 280), 'tape_screw': (26, 26)}
    for t in THEMES: sizes.update({f'tape_shell_{t}': (320, 480), f'tape_hubs_{t}': (30, 720), f'tape_marks_{t}': (26, 78)})
    gen = tape_art.images()
    for n, size in sizes.items():
        im = asset_image(n)
        built = open(asset_path(n), 'rb').read()
        expect(im.size == size == gen[n].size and built == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() and same_pixels(built, gen[n]), f'{n}: {size}, the generator\'s PNG pixel for pixel')
    expect(set(sizes) == set(tape_art.NAMES) and len(sizes) == 11, 'the pictures: two shared (tape_top, tape_screw) and three a theme (shell, hubs, marks)')
    expect((tape_art.TOP_RECT[2] - tape_art.TOP_RECT[0], tape_art.TOP_RECT[3] - tape_art.TOP_RECT[1]) == (280, 74), 'tape_top: 280 x 74 landscape, 74 x 280 turned')
    total = sum(os.path.getsize(asset_path(n)) for n in sizes) + os.path.getsize(asset_path('pod_ic_tape'))
    per = {t: sum(os.path.getsize(asset_path(f'{n}_{t}')) for n in tape_art.PER_THEME) for t in THEMES}
    shared = sum(os.path.getsize(asset_path(n)) for n in tape_art.SHARED)
    print('  tape pictures: shared %d bytes, a theme %s (row icon %d)' % (shared, per, os.path.getsize(asset_path('pod_ic_tape'))))
    expect(total < 700000, f'the pictures add {total} bytes to the rootfs (the space step leaves 2.5 MB; fwtool enforces the stock size)')
    for t in THEMES:
        shell = asset_image(f'tape_shell_{t}')
        expect(shell.getpixel((0, 0))[3] == 255 and shell.convert('RGB').getpixel((0, 0)) != (0, 0, 0) and shell.convert('RGB').getpixel((160, 5)) != shell.convert('RGB').getpixel((160, 240)), f'{t}: the shell is opaque')
    expect(len({asset_image(f'tape_shell_{t}').tobytes() for t in THEMES}) == 3 and len({asset_image(f'tape_marks_{t}').tobytes() for t in THEMES}) == 2, 'the themes differ in their shell; the marks are in the band\'s ink (Metal\'s is gold, the others white)')
    # tape_top is transparent over the clear window's middle and the label, opaque on the gear ring
    top = asset_image('tape_top')
    expect(top.getpixel((74 - 1 - (147 - 110), 150 - 100))[3] == 0, 'tape_top: the hole\'s inside is transparent (the tape and the hub show)')
    ring = max(top.getpixel((74 - 1 - (147 - 110), x - 100))[3] for x in (104, 105, 106, 159, 160, 161))
    expect(ring > 200, f'tape_top: the gear ring is opaque (alpha {ring})')
    # the hub sprites: 24 frames of 5 degrees = one 120 degree cycle (the ring's 6 teeth repeat every 60, the drive's 3 spokes every 120), all different
    for t in THEMES:
        hubs = asset_image(f'tape_hubs_{t}')
        cell = lambda i: hubs.crop((0, i * 30, 30, i * 30 + 30)).tobytes()
        expect(len({cell(i) for i in range(24)}) == 24, f'{t}: the 24 hub frames are all different')
        marks = asset_image(f'tape_marks_{t}')
        cl = [marks.crop((0, i * 26, 26, i * 26 + 26)).tobytes() for i in range(3)]
        expect(len(set(cl)) == 3 and all(any(c[i] for i in range(3, len(c), 4)) for c in cl), f'{t}: play, pause and repeat: three different marks with ink')
    sc = asset_image('tape_screw')
    expect(any(sc.tobytes()[i] for i in range(3, 26 * 26 * 4, 4)), 'the pressed screw has ink')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# The reference model: the page's picture computed in landscape from the design (docs/modules/tape.md), pixel for pixel, to be equal to what the payload draws into the turned frame.
_CACHE = {}


def shell_land(theme='normal'):
    if ('shell', theme) not in _CACHE: _CACHE['shell', theme] = asset_image(f'tape_shell_{theme}').transpose(Image.ROTATE_90)   # the frame is the picture turned clockwise: counterclockwise gives landscape back
    return _CACHE['shell', theme].copy()


def cells(name, cell, n):
    if name not in _CACHE:
        sheet = asset_image(name)
        _CACHE[name] = [sheet.crop((0, i * cell, cell, i * cell + cell)).transpose(Image.ROTATE_90) for i in range(n)]
    return [c.copy() for c in _CACHE[name]]


def blend(v, c, a):
    """tp_mix: c over v by a (of 255), per channel floor((v (256 - w) + c w) / 256), w = a + (a >> 7); opaque."""
    w = a + (a >> 7)
    return tuple((v[i] * (256 - w) + c[i] * w) >> 8 for i in range(3)) + (255,)


def lut(d2h): return math.isqrt(d2h << 6) if d2h < O['TP_LUT_N'] else -1


def py_radii(pos, length):
    """tp_radii: the packs' radii in 1/16 px."""
    p = pos * 65536 // length if length > 0 else 0
    p = min(p, 65536)
    take2 = 16 * 16 * 256 + ((66 * 66 - 16 * 16) * p >> 8)
    return math.isqrt(66 * 66 * 256 + 16 * 16 * 256 - take2), math.isqrt(take2)   # (supply, take-up)


PK_BODY, PK_EDGE, PK_WIND, PK_LIGHT, PK_LIGHT2 = (0x24, 0x16, 0x0e, 255), (0x0c, 0x08, 0x05, 255), (0x28, 0x19, 0x10, 255), (0x6a, 0x4a, 0x30, 255), (0x3e, 0x2a, 0x1c, 255)


def py_pack(under, d, R, dx, dy):
    if d < 0 or d > R + 8: return under
    cov = min(16, R + 8 - d)
    if d >= R - 16: c = PK_EDGE
    elif R - 80 <= d < R - 48 and -1008 * dy + 178 * dx >= 0 and -887 * dx + 512 * dy >= 0: c = PK_LIGHT
    elif R - 80 <= d < R - 48 and 1008 * dy - 178 * dx >= 0 and 887 * dx - 512 * dy >= 0: c = PK_LIGHT2
    elif d >= 16 * 16 and (d - 256) % 48 < 16: c = PK_WIND
    else: c = PK_BODY
    return c if cov >= 16 else blend(under, c, cov * 255 // 16)


def py_clear(x, y):
    x0, y0, x1, y1, r = O['TP_CLEAR_X0'], O['TP_CLEAR_Y0'], O['TP_CLEAR_X1'], O['TP_CLEAR_Y1'], O['TP_CLEAR_R']
    if not (x0 <= x < x1 and y0 <= y < y1): return False
    qx = min(max(x, x0 + r), x1 - 1 - r); qy = min(max(y, y0 + r), y1 - 1 - r)
    return (x - qx) ** 2 + (y - qy) ** 2 <= r * r


class Ref:
    """The page's landscape picture for a state: the shell, the reels (packs from the position, hub frames), the marks and the text fields drawn so far."""
    def __init__(self, font, theme='normal'):
        self.theme = tape_art.THEMES[theme]; self.shell = shell_land(theme); self.img = self.shell.copy(); self.font = font
        if 'top' not in _CACHE: _CACHE['top'] = asset_image('tape_top').transpose(Image.ROTATE_90)
        self.top = _CACHE['top']
        self.hubs, self.marks = cells(f'tape_hubs_{theme}', 30, 24), cells(f'tape_marks_{theme}', 26, 3) + cells('tape_screw', 26, 1)

    def reels(self, pos, length, hub=(0, 5), rect=None):
        rs, rt = py_radii(pos, length)
        T = (O['TP_TOP_X'], O['TP_TOP_Y'], O['TP_TOP_X'] + O['TP_TOP_W'], O['TP_TOP_Y'] + O['TP_TOP_H'])
        x0, y0, x1, y1 = rect or T
        sh, im, top, cy = self.shell.load(), self.img.load(), self.top.load(), O['TP_REEL_Y']
        for x in range(x0, x1):
            for y in range(y0, y1):
                c = sh[x, y]
                clear = py_clear(x, y)
                for cx, R in ((O['TP_REEL_X0'], rs), (O['TP_REEL_X1'], rt)):
                    dx, dy = 2 * (x - cx) + 1, 2 * (y - cy) + 1
                    d = lut(dx * dx + dy * dy)
                    if clear or 0 <= d <= 16 * O['TP_HOLE_R']: c = py_pack(c, d, R, dx, dy)
                if T[0] <= x < T[2] and T[1] <= y < T[3]:
                    t = top[x - T[0], y - T[1]]
                    if t[3]: c = blend(c, t, t[3])
                im[x, y] = c
        for k, cx in enumerate((O['TP_REEL_X0'], O['TP_REEL_X1'])):
            hx, hy = cx - 15, cy - 15
            hs = self.hubs[hub[k]].load()
            for x in range(max(hx, x0), min(hx + 30, x1)):
                for y in range(max(hy, y0), min(hy + 30, y1)):
                    s = hs[x - hx, y - hy]
                    if s[3]: im[x, y] = blend(im[x, y], s, s[3])

    def marks_draw(self, playing, repeat, pressed=False):
        im, sh = self.img.load(), self.shell.load()
        for i, (mx, my) in enumerate(((O['TP_PLAY_X'], O['TP_PLAY_Y']), (O['TP_REPEAT_X'], O['TP_REPEAT_Y']), (O['TP_SCREW_X'], O['TP_SCREW_Y']))):
            cell = 3 if i == 2 else 2 if i else (0 if playing else 1)
            ms = self.marks[cell].load()
            for u in range(26):
                for v in range(26):
                    c = sh[mx + u, my + v]
                    if not ((i == 1 and not repeat) or (i == 2 and not pressed)):
                        s = ms[u, v]
                        if s[3]: c = blend(c, s, s[3])
                    im[mx + u, my + v] = c

    def field(self, name, text, size=None):
        """tp_field: the rectangle restored from the shell, the text at its place, cut to its room with an ellipsis, glyphs clipped to the rectangle."""
        f = tape_art.TEXT[name]; px_ = size or f['px']; font = self.font
        x0, y0, x1, y1 = f['rect']; im, sh = self.img.load(), self.shell.load()
        for x in range(x0, x1):
            for y in range(y0, y1): im[x, y] = sh[x, y]
        chars = list(text)[:63]
        step = lambda ch: (font.step(font.glyph(ch), px_) if font.glyph(ch) else 4)
        w = sum(step(c) for c in chars)
        if w > f['room']:
            ell = step('…'); w = 0; i = 0
            while i < len(chars) and w + step(chars[i]) + ell <= f['room']: w += step(chars[i]); i += 1
            chars = chars[:i] + ['…']; w += ell
        x = f['x'] - w if f['anchor'] == 'r' else f['x'] - w // 2 if f['anchor'] == 'm' else f['x']
        top = f['y'] - (px_ + 1) // 2; asc = font.baseline(px_)
        for pas in range(2 if f.get('bold') else 1):
            pen = x + pas
            for ch in chars:
                g = font.glyph(ch)
                if g:
                    gx0, gy0, gw, gh, rows = font.bitmap(g, px_)
                    for r in range(gh):
                        for c in range(gw):
                            a = rows[r][c]; gx, gy = pen + gx0 + c, top + gy0 + asc + r
                            if a and x0 <= gx < x1 and y0 <= gy < y1:
                                rgb = self.theme[f['colour']]
                                im[gx, gy] = blend(im[gx, gy], rgb + (255,), a)
                pen += step(ch)


def clock_of(m):
    import time as _t
    t = _t.gmtime(m.wall + m.tz); return f'{t.tm_hour:02d}:{t.tm_min:02d}'


def ref_frame(m, font, pos=14, length=562, reel_pos=None, theme='normal', playing=True, repeat=False, hub=(0, 5), title='So What', artist='Miles Davis', album='Kind of Blue', fmt='FLAC', vol=42, batt=60, charging=False, status_text=None):
    key = ('reels', theme, pos if reel_pos is None else reel_pos, length, tuple(hub), playing, repeat)   # the reels and the marks do not depend on the font: made once
    if key not in _CACHE:
        r = Ref(font, theme); r.reels(key[2], length, hub); r.marks_draw(playing, repeat); _CACHE[key] = r.img
    r = Ref(font, theme); r.img = _CACHE[key].copy()
    r.field('big', 'A'); r.field('model', r.theme['model'])
    r.field('title', title); r.field('artist', artist); r.field('album', album)
    r.field('times', tape_art.times_text(pos, length))
    text, size = status_text or tape_art.status_line(font, dict(batt=batt, charging=charging, vol=vol, fmt=fmt, clock=clock_of(m)))
    r.field('status', text, size)
    return r.img


def diff(a, b):
    """(count, first few (x, y, a, b)) of the pixels where two landscape images differ."""
    if a.tobytes() == b.tobytes(): return 0, []
    pa, pb = a.load(), b.load(); bad = []
    for x in range(a.width):
        for y in range(a.height):
            if pa[x, y] != pb[x, y]: bad.append((x, y, pa[x, y], pb[x, y]))
    return len(bad), bad[:3]


class WideFont:
    """The shipped font with `extra` more px of advance a glyph (so a status line that fits at 12 px does not): the stb model's metrics, the same bitmaps."""
    def __init__(self, font, extra): self.f, self.extra = font, extra
    def glyph(self, ch): return self.f.glyph(ch)
    def bitmap(self, g, px): return self.f.bitmap(g, px)
    def baseline(self, px): return self.f.baseline(px)
    def step(self, g, px): return self.f.step(g, px) + self.extra
    def width(self, text, px): return sum(self.step(self.glyph(c), px) for c in text)


def settle(m, paused=False):
    """The first look and the first paint of a page that was opened."""
    m.first(); m.paint()


def draw_tests(ctx):
    """The rotation of the drawing: the page's frame is, turned back, exactly the landscape picture of the design, text included."""
    expect = ctx.expect
    font = real_font()
    m = machine(font=font, status=3)
    expect(m.open() == 0, 'the page opens')
    m.timers = []
    m.paint()
    fr = m.frame()
    shell = asset_image('tape_shell_normal').tobytes()
    expect(fr[:4] == shell[:4] and sum(1 for i in range(0, len(fr), 4096) if fr[i:i + 4] != shell[i:i + 4]) < 40, 'the frame starts as the shell (before the first look, the paint draws the model and the A)')
    settle(m)
    got = m.landscape()
    want = ref_frame(m, font, playing=False)
    n, first = diff(got, want)
    expect(n == 0, f'the frame is, turned back to landscape, the design\'s picture pixel for pixel: reels, marks, title, artist, album, times, model, status ({n} pixels differ {first})')
    dump(m, '1')
    # rotation: a text pixel at landscape (x, y) is the frame's row x, column 319 - y and nowhere else
    ink = [(x, y) for x in range(*tape_art.TEXT['title']['rect'][::2]) for y in range(*tape_art.TEXT['title']['rect'][1::2]) if got.getpixel((x, y)) != shell_land().getpixel((x, y))]
    expect(len(ink) > 100, f'the title has ink ({len(ink)} pixels)')
    expect(all(m.pixel(x, y) == got.getpixel((x, y)) for x, y in ink[:200]), 'every inked landscape pixel is at the frame\'s (column 319 - y, row x)')
    raw = m.frame()
    expect(all(tuple(raw[(x * 320 + 319 - y) * 4:(x * 320 + 319 - y) * 4 + 4]) == got.getpixel((x, y)) for x, y in ink[:200]), 'in the bitmap\'s own memory: row x, column 319 - y (the quarter turn Cover Flow\'s captions use)')
    # the picture really is landscape: the title reads left to right along the frame's rows (x), the glyph tops are at the frame's right (y small -> column large)
    cols = [319 - y for x, y in ink]; rows = [x for x, y in ink]
    expect(max(cols) > 250 and min(rows) >= 43 and max(rows) <= 439, 'the title lies along the frame\'s rows near its right edge (landscape top = frame right)')
    # a long title is cut with an ellipsis to its room; nothing is drawn outside a field's rectangle; the field is restored before it is drawn again
    long = 'A very long title that cannot possibly fit on one line of the cassette label at all'
    m2 = machine(font=font, status=3, title=long, artist='Ar' * 40, album='Al ' * 40)
    m2.open(); m2.timers = []; settle(m2)
    want = ref_frame(m2, font, playing=False, title=long, artist='Ar' * 40, album='Al ' * 40)
    n, first = diff(m2.landscape(), want)
    expect(n == 0, f'long title, artist and album are cut with an ellipsis to their room, glyphs inside their rectangles ({n} {first})')
    base = shell_land().load(); l2 = m2.landscape().load()
    out = [(x, y) for x in range(480) for y in range(320) if l2[x, y] != base[x, y]
           and not any(r[0] <= x < r[2] and r[1] <= y < r[3] for r in [tape_art.TEXT[f]['rect'] for f in FIELDS] + [(100, 110, 380, 184), (410, 115, 436, 141), (410, 153, 436, 179)])]
    expect(not out, f'nothing outside the fields, the reel window and the marks differs from the shell ({out[:3]})')
    # a new track: the old text is gone
    m.play([m.song('Teardrop', 'Massive Attack', 'Mezzanine', path='/mnt/mmc/m/t.mp3', name='t.mp3')], 0); m.pt = (150, 330)
    m.tick(500); m.paint()
    want = ref_frame(m, font, pos=150, length=330, playing=False, title='Teardrop', artist='Massive Attack', album='Mezzanine', fmt='MP3')
    n, first = diff(m.landscape(), want)
    expect(n == 0, f'a new track replaces title, artist, album, format and the packs, the old text left no trace ({n} {first})')
    dump(m, '2')


def hub_frames(m, font, pos, length):
    """Which of the 24 hub frames each reel shows now: the one whose composite square (shell, packs, rings, hub) equals the frame's. [frame] when exactly one matches."""
    land = m.landscape(); out = []
    for k, cx in enumerate((O['TP_REEL_X0'], O['TP_REEL_X1'])):
        hx, hy = cx - 15, 147 - 15
        sq = land.crop((hx, hy, hx + 30, hy + 30)).tobytes()
        found = []
        r = Ref(font)
        for i in range(24):
            r.reels(pos, length, hub=(i, i), rect=(hx, hy, hx + 30, hy + 30))
            if r.img.crop((hx, hy, hx + 30, hy + 30)).tobytes() == sq: found.append(i)
        out.append(found)
    return out


def reel_tests(ctx):
    expect = ctx.expect
    font = real_font()
    # the radii: the tape's area is conserved, 16 px empty to 66 px full
    m = Machine()
    got = []
    for pos, length in ((0, 100), (1, 3), (50, 100), (562, 562), (14, 562), (99, 100), (3000, 65535), (0, 0)):
        rs, rt = m.alloc(4), m.alloc(4)
        m.call(PSYMS['tp_radii'], a0=pos, a1=length, a2=rs, a3=rt)
        got.append((pos, length, m.word(rs), m.word(rt)))
    expect(all((s, t) == py_radii(p, l) for p, l, s, t in got), f'tp_radii is the model\'s: {got[:3]}')
    expect(got[0][2:] == (66 * 16, 16 * 16) and got[3][2:] == (16 * 16, 66 * 16) and got[7][2:] == (66 * 16, 16 * 16), 'empty (or no length): supply 66 px, take-up 16 px; full: the other way round')
    area = [(s / 16) ** 2 + (t / 16) ** 2 for _, _, s, t in got[:7]]
    expect(all(abs(a - (66 ** 2 + 16 ** 2)) <= 10 for a in area), f'r_supply^2 + r_takeup^2 stays 66^2 + 16^2 = 4612 (within the 1/16 px rounding, 2 r / 16 = 8): {[round(a) for a in area]}')
    take = [t for _, _, _, t in [(0, 0, *py_radii(p, 1000)) for p in range(0, 1001, 50)]]
    expect(take == sorted(take), 'the take-up pack only grows with the position')
    expect(all(m.call(PSYMS['tp_isqrt'], a0=v) == math.isqrt(v) for v in (0, 1, 2, 3, 4, 15, 16, 17, 255, 65535, 65536, 1180672, 2 ** 31, 2 ** 32 - 1)), 'tp_isqrt is the integer square root')
    # the frame with the tape at three positions equals the model (the packs only through the holes and the clear window)
    for pos in (0, 281, 562):
        m = machine(font=font, status=3, pos=pos, length=562)
        m.open(); m.timers = []; settle(m)
        want = ref_frame(m, font, pos=pos, length=562, playing=False)
        n, first = diff(m.landscape(), want)
        expect(n == 0, f'position {pos} / 562: the packs, the rings over them, the hubs ({n} pixels differ {first})')
        if pos == 281: dump(m, '3')
        if pos == 562: dump(m, '4')
    # the tape is seen only through the holes and the window: elsewhere on the panel the picture is the shell's, and where it is not, it is the overlay's (rings, scale)
    m = machine(font=font, status=3, pos=562, length=562); m.open(); m.timers = []; settle(m)
    land, sh, top = m.landscape().load(), shell_land().load(), asset_image('tape_top').transpose(Image.ROTATE_90).load()
    T = (100, 110)
    outside = [(x, y) for x in range(100, 380) for y in range(110, 184)
               if not py_clear(x, y) and not any((2 * (x - cx) + 1) ** 2 + (2 * (y - 147) + 1) ** 2 <= (2 * 28 + 1) ** 2 for cx in (132, 348)) and not top[x - T[0], y - T[1]][3]]
    bad = [(x, y, land[x, y], sh[x, y]) for x, y in outside if land[x, y] != sh[x, y]]
    expect(len(outside) > 6000 and not bad, f'outside the holes and the window the shell shows ({len(outside)} pixels: no tape on the label; {len(bad)} differ {bad[:3]})')
    # the full take-up pack (66 px) fills the right half of the clear window up to its edge, and the empty supply pack (16 px) leaves the left part of the window clear
    expect(all(land[x, 160][:3] != sh[x, 160][:3] for x in range(286, 298)), 'the full take-up pack covers the clear window\'s right end (x 286 .. 298: 50 to 62 px from its centre)')
    expect(all(land[x, 160] == sh[x, 160] or top[x - T[0], 160 - T[1]][3] for x in range(185, 270) if (2 * (x - 132) + 1) ** 2 > (2 * 20) ** 2 * 4), 'the empty supply pack (16 px) leaves the left part of the window as the plastic shows it')
    m = machine(font=font, status=3, pos=0, length=562); m.open(); m.timers = []; settle(m)
    l0 = m.landscape().load()
    expect(all(l0[x, 160][:3] != sh[x, 160][:3] for x in range(185, 192)), 'at the start the supply pack is full (66 px): tape shows 60 px right of its centre, in the clear window')
    expect(l0[132 + 20, 160][:3] != sh[132 + 20, 160][:3], 'and inside its own hole')
    expect(l0[348 + 24, 147][:3] == sh[348 + 24, 147][:3] or top[348 + 24 - T[0], 147 - T[1]][3], 'the empty take-up pack (16 px) leaves the rest of its hole black')


def hub_tests(ctx):
    expect = ctx.expect
    font = real_font()
    m = machine(font=font, pos=14, length=562)
    m.open(); m.timers = []; settle(m)
    expect(hub_frames(m, font, 14, 562) == [[0], [5]], f'the first look turns nothing: the reels start at frames 0 and 5 ({hub_frames(m, font, 14, 562)})')
    seq = []
    for _ in range(14):
        m.tick(70); seq.append(hub_frames(m, font, 14, 562))
    expect(all(len(a) == 1 and len(b) == 1 for a, b in seq), f'every tick leaves each hub on exactly one of the 24 frames ({seq[:3]})')
    s0 = [a[0] for a, b in seq if len(a) == 1]; s1 = [b[0] for a, b in seq if len(b) == 1]
    unwrap = lambda s: [((b - a + 12) % 24) - 12 for a, b in zip(s, s[1:])]
    d0, d1 = unwrap(s0), unwrap(s1)
    expect(all(d < 0 for d in d0) and all(d < 0 for d in d1), f'both reels turn the same way, counterclockwise: the frame index falls ({d0[:6]} {d1[:6]})')
    rs, rt = py_radii(14, 562)
    want0, want1 = 70 * 1229 / rs / 80, 70 * 1229 / rt / 80      # frames a 70 ms tick: angular speed x radius is constant
    expect(abs(sum(d0) / len(d0) + want0) < 0.3 and abs(sum(d1) / len(d1) + want1) < 0.3 and want1 > 2.5 * want0,
           f'the take-up reel turns {want1:.1f} frames (5 degrees) a tick, the supply reel {want0:.1f}: measured {-sum(d1) / len(d1):.1f}, {-sum(d0) / len(d0):.1f}')
    # near the end the supply has run out: it turns fast and the take-up slowly
    m = machine(font=font, pos=550, length=562)
    m.open(); m.timers = []; settle(m)
    seq = []
    for _ in range(14):
        m.tick(70); seq.append(hub_frames(m, font, 550, 562))
    e0, e1 = unwrap([a[0] for a, b in seq]), unwrap([b[0] for a, b in seq])
    expect(sum(e0) < sum(e1) - 14, f'at the end of the tape it is the other way round ({sum(e0) / len(e0):.1f} vs {sum(e1) / len(e1):.1f})')
    # the invalidate of a tick that only turns the hubs: the two 30 px squares' bounding rectangle, in the frame's coordinates (column 320 - y1, row x0)
    m.tick(70)
    expect(m.rects == [(158, 117, 30, 246)], f'a hub tick invalidates just the hubs\' rectangle: columns 158 .. 188, rows 117 .. 363 ({m.rects})')
    # paused: the hubs stand still and a tick draws nothing
    m.status = 3; m.tick(500); m.paint()
    before = m.frame()
    m.tick(500); m.tick(500)
    expect(m.frame() == before and not any(m.rects), f'paused: no hub moves, nothing is invalidated ({m.rects})')
    # a stalled loop never jumps the reels: one tick of two seconds turns them as 250 ms would
    m2 = machine(font=font, pos=550, length=562); m2.open(); m2.timers = []; settle(m2); m3 = machine(font=font, pos=550, length=562); m3.open(); m3.timers = []; settle(m3)
    m2.tick(2000); m3.tick(250)
    expect(hub_frames(m2, font, 550, 562) == hub_frames(m3, font, 550, 562) and m2.frame() == m3.frame(), 'a tick after a stall of two seconds turns the reels as 250 ms would (a stalled loop never jumps them)')
    # the loop: the picture repeats every 120 degrees (6 ring teeth, 3 spokes), so 24 frames of 5 degrees close it seamlessly: all different, and the python model of the
    # frame for an angle agrees with the payload's (angle / 5 degrees, the angle in sixteenths modulo 1920) at every step of a full turn
    expect(len({c.tobytes() for c in cells('tape_hubs_normal', 30, 24)}) == 24, '24 distinct frames at 5 degrees cover the 120 degree cycle')
    A = tape_art
    expect(all(A.sprite_index(a) == (a % 120) // 5 for a in range(0, 720, 5)) and A.sprite_index(120) == A.sprite_index(0) == 0 and A.sprite_index(119.9) == 23 and A.sprite_index(-5) == 23,
           'the frame for an angle is (angle mod 120) / 5: the last frame (115 degrees) is followed by the first (120 = 0), nothing jumps')
    hs = cells('tape_hubs_normal', 30, 24)
    expect(hs[0].tobytes() != hs[12].tobytes() and hs[0].tobytes() != hs[8].tobytes(), 'a 60 degree turn is not the same picture (the 3 spokes only repeat every 120)')


def mark_tests(ctx):
    expect = ctx.expect
    font = real_font()
    m = machine(font=font, status=2)
    m.open(); m.timers = []; settle(m)
    mk = lambda: (m.landscape().crop((410, 115, 436, 141)).tobytes(), m.landscape().crop((410, 153, 436, 179)).tobytes())
    play, rep = mk()
    base_rep = shell_land().crop((410, 153, 436, 179)).tobytes()
    expect(rep == base_rep, 'repeat off: the band is plain where the arrow would be')
    m.status = 3; m.tick(500)
    pause, _ = mk()
    expect(pause != play, 'paused: the pause bars replace the play triangle')
    m.status = 2; m.tick(70)
    expect(mk()[0] == play, 'playing again: the triangle is back, nothing of the bars left')
    m.mode = O['MODE_REPEAT_ALL']; m.tick(70)
    expect(mk()[1] != base_rep, 'repeat all: the arrow is printed')
    m.mode = O['MODE_REPEAT_ONE']; m.tick(70)
    expect(mk()[1] != base_rep, 'repeat one: the arrow is printed')
    m.mode = O['MODE_SHUFFLE']; m.tick(70)
    expect(mk()[1] == base_rep, 'shuffle is not repeat: the arrow goes')
    m.mode = O['MODE_REPEAT_ALL']; m.status = 3; m.tick(500); m.paint()
    n, first = diff(m.landscape(), ref_frame(m, font, playing=False, repeat=True, hub=tuple(f[0] for f in hub_frames(m, font, 14, 562))))
    expect(n == 0, f'paused with repeat on, after all that: the design\'s picture ({n} {first})')
    dump(m, '5')


def status_tests(ctx):
    """The status line: VOL | format | clock | battery at 12 px, 11 px when it does not fit, the clock dropped first, then the format; the device font's own advances."""
    expect = ctx.expect
    base = real_font()
    seen = set()
    for extra in (0, 2, 3, 4, 6, 8, 14, 20):
        font = WideFont(base, extra) if extra else base
        m = machine(font=font, status=3)
        m.open(); m.timers = []; settle(m)
        for vol, batt, ch, fmt in ((42, 60, False, 'FLAC'), (100, 100, True, 'WAVE'), (0, 20, False, 'MP3'), (7, 0, True, 'M4A')):
            m.volume, m.battery_img = str(vol), 'bar_charge' if ch else 'bar_power'
            m.props[(m.widgets['pgbar_battery'], 'value')] = batt
            m.play([m.song('So What', 'Miles Davis', 'Kind of Blue', path=f'/mnt/mmc/m/x.{fmt.lower()}', name=f'x.{fmt.lower()}')], 0)
            m.tick(500); m.paint()
            text, size = tape_art.status_line(font, dict(batt=batt, charging=ch, vol=vol, fmt=fmt, clock=clock_of(m)))
            seen.add((size, text.count('|')))
            want = ref_frame(m, font, playing=False, vol=vol, batt=batt, charging=ch, fmt=fmt)
            n, first = diff(m.landscape(), want)
            expect(n == 0, f'+{extra} px a glyph: "{text}" at {size} px, as the design chooses it ({n} {first})')
    expect({(12, 3), (12, 2), (12, 1), (11, 1)} <= seen, f'the four sorts of line are all drawn: whole, no clock, no format, 11 px ({sorted(seen)})')
    # the fit itself: the full line at 12 px with the shipped font, and every drop on the way with a wider font, in the design's order
    full = tape_art.status_line(base, dict(batt=100, charging=True, vol=100, fmt='WAVE', clock='23:59'))
    expect(full == ('VOL 100 | WAVE | 23:59 | +100%', 12), f'the widest line with the shipped font fits whole at 12 px: {full}')
    outs = [tape_art.status_line(WideFont(base, e), dict(batt=60, charging=False, vol=42, fmt='FLAC', clock='21:07')) for e in range(0, 30)]
    order = [(s, t.count('|')) for t, s in outs]
    expect(order == sorted(order, key=lambda o: (-o[0], -o[1])) and order[0] == (12, 3) and order[-1][0] == 11 and (12, 2) in order and (12, 1) in order,
           f'a wider font drops the clock first, then the format, and only then goes to 11 px; the choice only gets smaller: {sorted(set(order), reverse=True)}')


def live_tests(ctx):
    """What changes on the timer: the times each second, the battery, the volume, the clock; each redraws only its own field."""
    expect = ctx.expect
    font = real_font()
    m = machine(font=font, status=3, pos=14, length=562)
    m.open(); m.timers = []; settle(m)
    land = lambda: m.landscape()
    box = lambda a, b: ImageChopsBox(a, b)
    inside = lambda bx, name: bx and all(tape_art.TEXT[name]['rect'][i] <= bx[i] if i < 2 else bx[i] <= tape_art.TEXT[name]['rect'][i] for i in range(4))
    a = land()
    m.pt = (15, 562); m.tick(500); m.paint(); b = land()
    expect(inside(box(a, b), 'times'), f'one second on, only the times field changed ({box(a, b)})')
    expect(m.rects and all(rc[0] >= 320 - tape_art.TEXT['times']['rect'][3] and rc[0] + rc[2] <= 320 - tape_art.TEXT['times']['rect'][1] and rc[1] >= 325 and rc[1] + rc[3] <= 439 for rc in m.rects),
           f'and only its rectangle was invalidated ({m.rects})')
    m.tick(500); m.paint()
    expect(land().tobytes() == b.tobytes() and not any(m.rects), 'nothing changed: nothing is redrawn or invalidated')
    m.volume = '55'; m.tick(500); m.paint(); d = land()
    expect(inside(box(b, d), 'status'), f'volume 42 -> 55: only the status line changed ({box(b, d)})')
    expect(not any(c_[0] in ('widget_set_text', 'widget_set_text_utf8', 'widget_set_value', 'widget_set_prop_int', 'widget_set_prop_str') for c_ in m.calls), 'the volume is only read: nothing in the status bar was set')
    m.props[(m.widgets['pgbar_battery'], 'value')] = 40; m.tick(500); m.paint(); e = land()
    expect(inside(box(d, e), 'status'), f'battery 60 -> 40: the status line only ({box(d, e)})')
    m.battery_img = 'bar_charge'; m.tick(500); m.paint(); f = land()
    expect(inside(box(e, f), 'status') and box(e, f), f'charging: a + before the number ({box(e, f)})')
    hubs = tuple(x[0] for x in hub_frames(m, font, 14, 562))   # (the packs keep the radii of pos 14: a change under 1/4 px is not redrawn)
    n, first = diff(f, ref_frame(m, font, pos=15, length=562, reel_pos=14, playing=False, hub=hubs, batt=40, vol=55, charging=True))
    expect(n == 0, f'and the picture is the design\'s with 15 s, volume 55, 40 % charging ({n} {first})')
    m.wall += 60; m.tick(500); m.paint(); g = land()
    expect(inside(box(f, g), 'status') and box(f, g), f'a minute later the clock in the status line moved, nothing else ({box(f, g)})')
    # no status bar at all (its window is gone): the page still draws, the line is "VOL 0" (no battery to show, no volume to read)
    m.setword(SYSBAR, 0); m.tick(500); m.paint()
    n, first = diff(land(), ref_frame(m, font, pos=15, length=562, reel_pos=14, playing=False, hub=hubs, status_text=('VOL 0', 12)))
    expect(n == 0, f'a missing status bar is survived: the status line is VOL 0 ({n} {first})')


def ImageChopsBox(a, b):
    from PIL import ImageChops
    return ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox()


def touch_tests(ctx):
    """The rotation of the touch: the panel reports portrait coordinates; taps are read in landscape. Taps only: a tap on the top left screw closes, a tap elsewhere plays / pauses."""
    expect = ctx.expect
    font = real_font()
    m = machine(font=font, pos=14, length=562)
    m.open(); m.timers = []; m.first(); m.paint()
    names = lambda c: [x[0] for x in c]
    # a tap anywhere but the screw (a short move) plays / pauses; nothing is grabbed
    for pt in ((240, 160), (100, 100), (450, 300), (60, 20), (20, 60), (49, 50)):
        m.cmds = []; calls = m.gesture(pt, (pt[0] + 3, pt[1] - 2)) if pt != (20, 60) else m.gesture(pt, (pt[0] + 3, pt[1] + 2))
        expect(m.cmds == [('playpause',)] and 'widget_grab' not in names(calls) and 'navigator_back' not in names(calls), f'a tap at landscape {pt} plays / pauses and grabs nothing ({names(calls)})')
    # the close screw: the top left one as the user sees it, a 50 x 50 area in landscape = the panel's top right corner, columns 270 .. 319, rows 0 .. 49
    A = tape_art
    expect(A.CLOSE_RECT == (O['TP_CLOSE_X0'], O['TP_CLOSE_Y0'], O['TP_CLOSE_X1'], O['TP_CLOSE_Y1']) == (0, 0, 50, 50) and A.CLOSE_RECT[2] - A.CLOSE_RECT[0] >= 48 and A.CLOSE_RECT[3] - A.CLOSE_RECT[1] >= 48
           and A.CLOSE_RECT[0] < A.SCREW_AT[0] < A.CLOSE_RECT[2] and A.CLOSE_RECT[1] < A.SCREW_AT[1] < A.CLOSE_RECT[3], 'the close area is at least 48 x 48 and contains the screw at (24, 25)')
    for pt in ((24, 25), (1, 1), (48, 48), (49, 49), (2, 47), (47, 2)):
        m.cmds = []; calls = m.gesture(pt, pt)
        expect('navigator_back' in names(calls) and not m.cmds, f'a tap at landscape {pt} (portrait column {319 - pt[1]}, row {pt[0]}) closes the page, plays nothing')
    m.cmds = []; m.ptr('down', 299, 24, 3000); m.ptr('up', 299, 24, 3050)
    expect('navigator_back' in names(m.calls) and not m.cmds, 'in the panel\'s own coordinates: a tap at column 299, row 24 (the top right corner of the portrait screen) closes')
    for pt in ((50, 25), (24, 50), (60, 60), (25, 100)):
        m.cmds = []; calls = m.gesture(pt, pt)
        expect('navigator_back' not in names(calls) and m.cmds == [('playpause',)], f'a tap at landscape {pt}, just outside the 50 x 50 area, plays / pauses')
    # pressed: the screw is drawn darker and turned while it is held, the band's picture otherwise unchanged; released: back
    ref = Ref(font)
    rect = A.mark_rects()[2]
    crop = lambda im: im.crop(rect).tobytes()
    before = m.landscape()
    m.ptr('down', 295, 20, 4000)
    held = m.landscape()
    ref.marks_draw(m.status == 2, False, pressed=True)
    expect(crop(held) == crop(ref.img) and crop(held) != crop(before) and ImageChopsBox(before, held) is not None and
           all(rect[0] <= v for v in ImageChopsBox(before, held)[:2]) and ImageChopsBox(before, held)[2] <= rect[2] and ImageChopsBox(before, held)[3] <= rect[3],
           'held: the screw is the darker, turned sprite and nothing else changed')
    expect(m.rects and m.rects[-1] is not None and m.rects[-1][0] >= 320 - rect[3] and m.rects[-1][1] >= rect[0], f'and only its rectangle was invalidated ({m.rects[-1:]})')
    pr = held.crop(rect).convert('L')
    nr = before.crop(rect).convert('L')
    expect(sum(pr.getdata()) < sum(nr.getdata()), 'the pressed screw is darker')
    m.ptr('up', 295, 20, 4050)
    expect(m.landscape().tobytes() == before.tobytes() and 'navigator_back' in names(m.calls), 'released on the screw: the normal screw is back (the page closes)')
    # the finger leaves the screw before it lifts: nothing closes, nothing plays, the screw is released; a touch that began elsewhere and ends on the screw is a tap elsewhere
    m.cmds = []; calls = m.gesture((24, 25), (200, 200))
    expect('navigator_back' not in names(calls) and not m.cmds and m.landscape().tobytes() == before.tobytes(), 'began on the screw, lifted far away: nothing closes or plays, the screw is let go')
    m.cmds = []; calls = m.gesture((200, 200), (24, 25))
    expect('navigator_back' not in names(calls) and not m.cmds, 'a drag onto the screw is not a tap anywhere')
    # swipes are gone: a long drag, in any direction, does nothing (and never skips)
    for a, b in (((300, 160), (200, 160)), ((200, 160), (300, 160)), ((240, 60), (240, 160)), ((240, 160), (240, 60)), ((200, 100), (270, 170))):
        m.cmds = []; calls = m.gesture(a, b)
        expect(not m.cmds and 'navigator_back' not in names(calls) and not any(n in ('next_quick_click', 'prev_quick_click') for n in names(calls)), f'a drag {a} -> {b} does nothing')
    # an abort (a window over the page, the pull-down opening) lets the screw go and acts on nothing; the up after it is ignored
    m.cmds = []; m.ptr('down', 295, 20, 5000); m.ptr('abort', 295, 20, 5010); m.ptr('up', 295, 20, 5020)
    expect(not m.cmds and m.landscape().tobytes() == before.tobytes() and 'navigator_back' not in names(m.calls), 'an abort releases the touch, nothing closes')
    m.cmds = []; m.ptr('up', 100, 100, 1010)
    expect(not m.cmds, 'an up without a down is ignored')
    # the pull-down: the page leaves the stock touch hook alone: no grab, no move handler, no event consumed (every handler returns RET_OK)
    expect(m.names().count('widget_grab') == 0 and (m.view, EVT_MOVE) not in m.bound and (WIN, EVT_MOVE) not in m.bound, 'the page never grabs the pointer and binds no move handler')
    ev = m.alloc(0x30); m.u.mem_write(ev, bytes(0x30)); m.setword(ev, EVT_DOWN); m.setword(ev + 0x18, 150); m.setword(ev + 0x1c, 40)
    rets = []
    for kind, y in ((EVT_DOWN, 40), (EVT_MOVE, 80), (EVT_MOVE, 160), (EVT_UP, 160), (EVT_ABORT, 160)):
        m.setword(ev, kind); m.setword(ev + 0x1c, y); rets.append(m.call(PSYMS['tp_on_touch'], a0=0, a1=ev, count=4000000))
    expect(set(rets) == {0}, f'a drag that starts at the panel\'s top edge (the pull-down zone, y <= 80) is passed on: every call returns RET_OK ({rets})')
    # a tap plays and the page looks again at once (the marks follow without waiting for the timer)
    m.status = 2; m.tick(70); m.cmds = []; calls = m.gesture((240, 160), (241, 160))
    r = Ref(font); r.marks_draw(False, False)
    expect(m.cmds == [('playpause',)] and m.status == 3 and m.landscape().crop((410, 115, 436, 141)).tobytes() == r.img.crop((410, 115, 436, 141)).tobytes(),
           'a tap pauses and the page looks again at once: the pause mark is printed before the timer\'s next tick')
    expect(('timer_modify', 0x777, O['TP_IDLE_MS']) in calls, 'and the timer goes to its paused pace')
    # the touch of a page that is not open (a handler left behind) does nothing
    m2 = machine(); m2.cmds = []
    e = m2.alloc(0x30); m2.u.mem_write(e, bytes(0x30)); m2.setword(e, EVT_DOWN)
    m2.call(PSYMS['tp_on_touch'], a0=0, a1=e, count=100000)
    expect('widget_grab' not in [c[0] for c in m2.calls] and not m2.cmds, 'no page: a touch handler that is left behind does nothing')
    expect(not any(n in ('widget_set_visible', 'widget_move', 'widget_resize') for n in names(m.calls)), 'it moves nothing in the asset')


def idle_touch_tests(ctx):
    """A page opened by Now Playing's timer (tape_open_idle): a tap anywhere closes it (docs/modules/tape.md "Touch"); a page opened from the More sheet is unchanged."""
    expect = ctx.expect
    names = lambda c: [x[0] for x in c]
    m = machine(); assert m.open_idle() == 0
    m.timers = []; m.first()
    for pt in ((240, 160), (100, 100), (450, 300), (60, 20), (50, 25), (24, 50)):
        m.cmds = []; calls = m.gesture(pt, (pt[0] + 3, pt[1] - 2))
        expect(m.cmds == [] and names(calls).count('navigator_back') == 1, f'auto-opened: a tap at landscape {pt} closes the page and plays / pauses nothing ({names(calls)})')
    for pt in ((24, 25), (1, 1), (48, 48)):
        m.cmds = []; calls = m.gesture(pt, pt)
        expect(names(calls).count('navigator_back') == 1 and not m.cmds, f'auto-opened: the screw at {pt} still closes')
    m.ptr('down', 295, 20, 4000)
    held = m.landscape()
    m.ptr('up', 200, 200, 4050)
    expect('navigator_back' not in names(m.calls) and not m.cmds and held.tobytes() != m.landscape().tobytes(), 'auto-opened: the screw still shows pressed; lifted elsewhere closes nothing')
    for a, b in (((300, 160), (200, 160)), ((240, 60), (240, 160)), ((200, 100), (270, 170)), ((24, 25), (200, 200))):
        m.cmds = []; calls = m.gesture(a, b)
        expect(not m.cmds and 'navigator_back' not in names(calls), f'auto-opened: a drag {a} -> {b} does nothing')
    m.cmds = []; m.ptr('down', 100, 100, 5000); m.ptr('abort', 100, 100, 5010); m.ptr('up', 100, 100, 5020)
    expect(not m.cmds and 'navigator_back' not in names(m.calls), 'auto-opened: an abort does nothing')
    # the timer firing on a page that is already up changes nothing: a More-opened page keeps pausing, an auto-opened one keeps closing
    m = machine(); assert m.open() == 0; m.timers = []; m.first()
    expect(m.open_idle() == 0, 'the timer on a More-opened page: 0, left alone')
    m.cmds = []; calls = m.gesture((240, 160), (243, 158))
    expect(m.cmds == [('playpause',)] and 'navigator_back' not in names(calls), 'and its tap still plays / pauses')
    m = machine(); assert m.open_idle() == 0; m.timers = []; m.first()
    expect(m.open() == 0, 'More on an auto-opened page: 0, left alone')
    m.cmds = []; calls = m.gesture((240, 160), (243, 158))
    expect(m.cmds == [] and 'navigator_back' in names(calls), 'and its tap still closes')
    # destroyed: the flag goes with the page; a later More open pauses on tap
    fn, cx = m.bound[(WIN, EVT_DESTROY)]; m.call(fn, a0=cx, a1=0, count=3000000)
    m.windows = {}; m.bound = {}
    assert m.open() == 0; m.timers = []; m.first()
    m.cmds = []; calls = m.gesture((240, 160), (243, 158))
    expect(m.cmds == [('playpause',)] and 'navigator_back' not in names(calls), 'after the auto-opened page was destroyed a More-opened page plays / pauses on tap')
    # a page that will not open: -1, no flag left for the next one
    m = machine(); del m.widgets['tape_view']
    expect(m.open_idle() == 0xffffffff, 'a page that will not open: -1')
    m = machine(); assert m.open() == 0; m.timers = []; m.first()
    m.cmds = []; calls = m.gesture((240, 160), (243, 158))
    expect(m.cmds == [('playpause',)], 'a fresh More-opened page plays / pauses')


def life_tests(ctx):
    expect = ctx.expect
    font = real_font()
    m = machine(font=font)
    m.windows['m1plus_tape'] = 0
    expect(m.open() == 0xffffffff and 'timer_add' not in m.names() and 'widget_on' not in m.names(), 'a window that will not open: -1, nothing registered, no timer, no bitmap')
    m = machine(font=font); del m.widgets['tape_view']
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and 'timer_add' not in m.names(), 'an asset that is not ours (no view): the window goes again, no timer')
    m = machine(font=font); m.load_image = 1
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and 'timer_add' not in m.names() and len(m.bitmaps) == 0, 'a picture that will not load: the window goes again, nothing stays allocated')
    m = machine(font=font); m.images['tape_screw'] = (10, 10, bytes(400))
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and len(m.bitmaps) == 0, 'a picture of another size is refused (the payload and the pictures are one build): the window goes again, bitmaps freed')
    m = machine(font=font); m.bitmap_ok = False
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and 'timer_add' not in m.names(), 'no memory for the frame: the window goes again')
    m = machine(font=font)
    expect(m.open() == 0, 'the page opens')
    c = m.calls
    on = {(a, e): (f, x) for _, a, e, f, x in (c_ for c_ in c if c_[0] == 'widget_on')}
    view = m.widgets['tape_view']
    expect(all((view, e) in on for e in (EVT_DOWN, EVT_UP, EVT_ABORT, EVT_PAINT)) and all((WIN, e) in on for e in (EVT_DESTROY, EVT_BG, EVT_FG)) and len(on) == 7,
           'the view takes pointer down, up and abort (no move) and its own paint, the window its three events: nothing else is registered')
    expect([c_[0] for c_ in c].count('timer_add') == 1 and ('timer_add', PSYMS['tp_first'], O['TP_FIRST_MS']) in c, 'one page-scoped timer, a 50 ms one-shot')
    expect(not any(n in m.names() for n in ('widget_set_visible', 'widget_move', 'widget_resize', 'widget_destroy', 'widget_set_name')), 'it moves, hides and destroys nothing in the asset')
    expect(len(m.bitmaps) == 6 and sorted(v[1:] for v in m.bitmaps.values()) == sorted([(320, 480), (320, 480), (74, 280), (30, 720), (26, 78), (26, 26)]), 'six bitmaps: the shell, the frame and the four small pictures')
    expect(m.open() == 0 and 'window_open' not in m.names(), 'opening again while it is up does nothing')
    # the first look starts the page timer; playing: 70 ms
    m.calls = []; m.call(PSYMS['tp_first'], a0=0, count=200000000)
    expect(('timer_add', PSYMS['tp_tick'], O['TP_PLAY_MS']) in m.calls, 'the one-shot starts the tick at 70 ms: a track is playing')
    expect('widget_set_prop_int' not in m.names() and 'widget_set_text' not in m.names() and 'mclSetVolume' not in m.names(), 'no stock setter is called by the look')
    # retiming: the one timer changes its interval in place
    m.status = 3; m.tick(500)
    expect(('timer_modify', 0x777, O['TP_IDLE_MS']) in m.calls and 'timer_add' not in m.names() and 'timer_remove' not in m.names(), 'paused: timer_modify to 500 ms, no second timer')
    m.status = 2; m.tick(500)
    expect(('timer_modify', 0x777, O['TP_PLAY_MS']) in m.calls and 'timer_add' not in m.names(), 'playing again: back to 70 ms, in place')
    m.tick(70)
    expect('timer_modify' not in m.names(), 'an unchanged interval is not set again')
    # idle power (the stock backlight byte, as Now Playing's timer): dark = a 1 s check and no visual work, lit again = the interval back and a catch-up look
    m.screen(False); m.tick(70)
    expect(('timer_modify', 0x777, 1000) in m.calls and not m.rects and not any(c_[0] in ('get_playtimeandlength', 'mclGetPlayStatus') for c_ in m.calls), 'screen off: the page timer slows to 1 s and the look (reels, text, invalidation) is skipped')
    m.tick(1000)
    expect('timer_modify' not in m.names() and not m.rects, 'screen off: the dark interval is not set again, still nothing drawn')
    m.pt = (m.pt[0] + 30, m.pt[1]); m.screen(True); m.tick(1000)
    expect(('timer_modify', 0x777, O['TP_PLAY_MS']) in m.calls and m.rects, 'screen on: the playing interval returns in place and the first tick draws what changed while dark')
    m.screen(False); m.calls = []; m.fire(EVT_BG, WIN); m.calls = []; m.fire(EVT_FG, WIN); m.screen(False); m.first()
    expect(('timer_add', PSYMS['tp_first'], 1000) in m.calls and not m.rects and 'timer_add' in m.names(), 'the first look with the screen off waits for the light (a 1 s one-shot, no draw)')
    m.screen(True); m.first()
    expect(('timer_add', PSYMS['tp_tick'], O['TP_PLAY_MS']) in m.calls and m.rects, 'the first look when lit draws everything and starts the tick')
    # no sound, no stock call but the ones the player's own buttons make
    expect(not any('click' in n.lower() and n not in ('playpause_quick_click', 'next_quick_click', 'prev_quick_click') for n in m.names()), 'no click sound is made')
    # to-background removes the timer, to-foreground adds the first-look one-shot again
    m.calls = []; m.fire(EVT_BG, WIN)
    expect(('timer_remove', 0x777) in m.calls, 'to the background: the timer goes')
    m.calls = []; m.fire(EVT_FG, WIN)
    expect(('timer_add', PSYMS['tp_first'], O['TP_FIRST_MS']) in m.calls, 'to the foreground: it is armed again')
    m.calls = []; m.fire(EVT_FG, WIN)
    expect('timer_add' not in m.names(), 'a second to-foreground does not add a second timer')
    # a tick that finds the page in the background (it ran just before the event) ends the timer
    m.calls = []; m.fire(EVT_BG, WIN); m.calls = []
    m.call(PSYMS['tp_tick'], a0=0, count=1000000)
    expect(not any(c_[0] in ('widget_invalidate_force', 'timer_modify') for c_ in m.calls), 'a stray tick in the background draws nothing')
    # destroy: the timer and all five bitmaps and the table go, the state is clean, another window's destroy leaves the page alone
    m.calls = []; m.fire(EVT_FG, WIN)
    fn, cx = m.bound[(WIN, EVT_DESTROY)]
    m.calls = []; m.call(fn, a0=WIN + 8, a1=0)
    expect('timer_remove' not in m.names() and 'bitmap_destroy' not in m.names(), 'a destroy of another window leaves the page alone')
    m.calls = []; m.call(fn, a0=cx, a1=0)
    expect(('timer_remove', 0x777) in m.calls and [c_[0] for c_ in m.calls].count('bitmap_destroy') == 6 and 'free' in m.names(), 'destroy: the timer is removed, the six bitmaps and the distance table freed')
    m.timers = []; m.calls = []
    expect(m.open() == 0 and ('window_open', 'm1plus_tape') in m.calls, 'the state is clean: it opens again')
    # nothing playing: the page shows Not Playing and still turns nothing
    m = machine(font=font, playing=False); m.status = 3
    m.open(); m.timers = []; settle(m)
    n, first = diff(m.landscape(), ref_frame(m, font, pos=0, length=0, playing=False, title='Not Playing', artist='', album='', fmt=''))
    expect(n == 0, f'nothing playing: the page shows Not Playing, 0:00 -0:00, full supply reel, and no format in the status line ({n} {first})')
    m.status = 2; m.tick(70); m.tick(70); m.paint()
    expect(not any(c[0] in ('next_quick_click', 'prev_quick_click', 'playpause_quick_click') for c in m.calls), 'ticks with no track change nothing in the player')


def paint_tests(ctx):
    expect = ctx.expect
    m = machine(font=real_font())
    m.open(); m.timers = []; m.first()
    b = m.paint()
    expect(len(b) == 1 and b[0][1] == (0, 0, 320, 480) and b[0][2] == (0, 0, 320, 480), f'paint copies the whole frame 1:1 in one blit (the canvas clips it to the dirty rectangle): {b}')
    expect(not any(c[0] in ('widget_load_image', 'bitmap_create_ex', 'timer_add') for c in m.calls), 'paint decodes nothing, makes no bitmap and no timer')
    c0 = m.glyph_calls; m.paint()
    expect(m.glyph_calls == c0, 'a paint with no change asks the font for nothing')
    m2 = machine(font=real_font()); m2.open()
    ev = m2.alloc(0x40); m2.u.mem_write(ev, bytes(0x40))
    m2.blits = []; m2.call(PSYMS['tp_on_paint'], a0=0, a1=ev, count=1000000)
    expect(not m2.blits, 'a paint event without a canvas draws nothing')
    m3 = machine(font=real_font())
    m3.paint()
    expect(not m3.blits, 'a paint with no page draws nothing')
    # the first rectangle covers the whole label: the picture that was blank is complete after one paint
    m4 = machine(font=real_font()); m4.open(); m4.timers = []; m4.first()
    r = m4.rects[0]
    expect(r[0] <= 320 - 220 + 1 and r[0] + r[2] >= 320 - 62 and r[1] <= 32 and r[1] + r[3] >= 439, f'the first look asks for the reels, the marks and the text fields: {r}')


def theme_tests(ctx):
    """Every theme: its pictures are the ones loaded (the shell, the hubs and the marks of the theme, the shared top and screw), the frame is the design's picture in its colours and
    model name, pixel for pixel; the saved theme is read when the page opens."""
    expect = ctx.expect
    font = real_font()
    for i, t in enumerate(THEMES):
        m = machine(font=font, status=3, theme=i)
        expect(m.open() == 0, f'{t}: the page opens')
        m.timers = []; settle(m)
        names = sorted(set(m.loads))
        want = sorted([f'tape_shell_{t}', f'tape_hubs_{t}', f'tape_marks_{t}', 'tape_top', 'tape_screw'])
        expect(names == want, f'{t}: the pictures loaded are the theme\'s three and the two shared ones ({names})')
        got = m.landscape()
        n, first = diff(got, ref_frame(m, font, theme=t, playing=False))
        expect(n == 0, f'{t}: the frame is the design\'s picture in the theme\'s colours, hubs, marks, model name {tape_art.THEMES[t]["model"]!r} ({n} {first})')
        dump(m, 'theme-' + t)
        if i:
            base = machine(font=font, status=3); base.open(); base.timers = []; settle(base)
            expect(base.landscape().tobytes() != got.tobytes(), f'{t}: differs from Normal')
    # the model names are the themes' branding and fit before the direction arrow (x 172) with the device font
    for t in THEMES:
        f = tape_art.TEXT['model']; w = sum(font.step(font.glyph(c), f['px']) for c in tape_art.THEMES[t]['model']) + 1
        expect(f['x'] + w <= tape_art.ARROW_AT[0] - 2, f'{t}: the model name {tape_art.THEMES[t]["model"]!r} is {w} px, it ends before the arrow at x {tape_art.ARROW_AT[0]}')
    # the theme is read once, at open: a change in Settings shows the next time
    m = machine(font=font, status=3, theme=1); m.open(); m.timers = []
    m.fs[THEME_FILE] = b'2\n'; m.loads.clear(); settle(m)
    expect(not any('metal' in u for u in m.loads), 'a theme saved while the page is open is not loaded under it')


def setting_tests(ctx):
    """Settings > Now Playing > Theme (m1plus_npset) and its picker Cassette Theme (m1plus_tapetheme): the value row shows Normal, Chrome or Metal and opens the picker; a tap on a picker row saves
    the theme atomically and moves the check; the Tape page reads the theme when it opens."""
    expect, P = ctx.expect, pod_pages
    C, T = P.NPSET_PAGE, P.THEME_PAGE
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    rows_n = PSYMS[f'pod_rows_{P.NPSET_PAGE_INDEX}']
    np_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.NPSET_PAGE_INDEX)
    expect(P.SETTINGS_PAGE.rows[np_i].label == 'Now Playing' and C.title == 'Now Playing' and [(r.label, r.action, r.arg) for r in C.rows][:3] == [('Theme', P.ACT_CTHEME, P.THEME_PAGE_INDEX), ('Record', P.ACT_VREC, P.RECORD_PAGE_INDEX), ('Base', P.ACT_VTHEME, P.VTHEME_PAGE_INDEX)]
           and P.ACT_CTHEME in P.VALUE_ACTIONS and P.CTHEME_VALUES == ('Normal', 'Chrome', 'Metal') and C.key == 'm1plus_npset' and any(isinstance(x, P.Hdr) and x.text == 'Cassette Mode' for x in C.layout) and any(isinstance(x, P.Hdr) and x.text == 'Vinyl Mode' for x in C.layout),
           'Settings has the Now Playing row; its page has a Cassette Mode header over the Theme value row, then a Vinyl Mode header over the Record row')
    expect([(r.label, r.action, r.arg) for r in T.rows] == [('Normal', P.ACT_THEMESET, 0), ('Chrome', P.ACT_THEMESET, 1), ('Metal', P.ACT_THEMESET, 2)] and T.title == 'Cassette Theme'
           and T.key == 'm1plus_tapetheme' and P.CTHEME_VALUES == tuple(n.capitalize() for n in THEMES), 'the picker: Normal, Chrome and Metal in the saved order, titled Cassette Theme')
    val = 'pod_value0'

    def open_page(data=None, language=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + [val])}
        if data is not None: m.fs[THEME_FILE] = data
        if language: m.set_language(language)
        m.call(PSYMS['on_row'], a0=rows_s + 12 * np_i, count=3000000)
        return m

    def label(m):
        keys = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[val]]
        return keys[-1] if keys else None

    m = open_page()
    expect(('window_open', C.key) in m.calls and ('widget_on', m.widgets['pod_row0'], O['EVT_CLICK']) in [c[:3] for c in m.calls], 'the Now Playing row opens the page and binds its row')
    expect(label(m) == 'Normal' and THEME_FILE not in m.fs, 'with nothing saved the theme is Normal, and reading writes nothing')
    for data, want in ((b'1\n', 'Chrome'), (b'1', 'Chrome'), (b'2\n', 'Metal'), (b'2', 'Metal'), (b'0\n', 'Normal'), (b'0', 'Normal'),
                       (b'3\n', 'Normal'), (b'', 'Normal'), (b'x', 'Normal'), (b'11', 'Normal'), (b'1\n\n', 'Normal'), (b'12', 'Normal'), (b' 1\n', 'Normal'), (b'\x001', 'Normal'), (b'-1', 'Normal')):
        expect(label(open_page(data)) == want, f'saved {data!r}: {want}')
    m = open_page()
    m.click('pod_row0')
    expect(('window_open', T.key) in m.calls and THEME_FILE not in m.fs, 'a tap on Theme opens the picker and saves nothing')

    def open_pick(data=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(3)] + [f'pod_check{i}' for i in range(3)])}
        if data is not None: m.fs[THEME_FILE] = data
        m.call(PSYMS['on_row'], a0=rows_n, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    m = open_pick()
    expect(('window_open', T.key) in m.calls and [shown(m, i) for i in range(3)] == [1, 0, 0], 'the picker opens with the check on Normal')
    expect([[shown(open_pick(d), i) for i in range(3)] for d in (b'1\n', b'2\n', b'9')] == [[0, 1, 0], [0, 0, 1], [1, 0, 0]], 'a saved Chrome or Metal has the check; an invalid file is Normal')
    m = open_pick()
    for want_file, k in ((b'1\n', 1), (b'2\n', 2), (b'0\n', 0), (b'1\n', 1)):
        m.click(f'pod_row{k}')
        expect(m.fs.get(THEME_FILE) == want_file and THEME_FILE + '.tmp' not in m.fs and ('rename', THEME_FILE + '.tmp', THEME_FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
               and [shown(m, i) for i in range(3)] == [int(i == k) for i in range(3)], f'a tap on {T.rows[k].label}: written atomically ({m.fs.get(THEME_FILE)!r}), the check follows')
    m = open_pick(b'1\n'); m.fail.add(('write', THEME_FILE + '.tmp')); m.click('pod_row2')
    expect(m.fs.get(THEME_FILE) == b'1\n' and THEME_FILE + '.tmp' not in m.fs and not any(c[0] == 'widget_set_visible' for c in m.calls),
           'a failed write changes neither the file nor the check')
    m = open_pick(b'2\n'); m.fail.add(('rename', THEME_FILE)); m.click('pod_row0')
    expect(m.fs.get(THEME_FILE) == b'2\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed rename changes neither')
    # the setting is what the Tape page opens with
    for data, t in ((None, 'normal'), (b'1\n', 'chrome'), (b'2\n', 'metal'), (b'7\n', 'normal'), (b'', 'normal')):
        mt = machine(font=real_font(), status=3)
        if data is not None: mt.fs[THEME_FILE] = data
        mt.open()
        expect(f'tape_shell_{t}' in mt.loads and sum(u.startswith('tape_shell_') for u in mt.loads) == 1, f'the Tape page opens with the {t} theme for a saved {data!r}')
    # localisation: the value in every language is set by key
    for loc in pod_i18n.ALL_TABLES:
        for data, key in ((None, 'Normal'), (b'1\n', 'Chrome'), (b'2\n', 'Metal')):
            expect(label(open_page(data, loc)) == key, f'{loc}: {key} is set by key')
    # the assets: the value label reads Normal until the payload sets it; the picker has the three rows with a hidden check each and the note
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_npset.bin'), 'rb').read())
    row, lab = tree.find('pod_row0'), tree.find('pod_value0')
    expect(row is not None and lab is not None and (lab.get('tr_text') or lab.get('text')) == 'Normal' and row.find('pod_icon') is not None and tree.find('label_title').get('tr_text') == 'Now Playing'
           and tree.find('pod_sec0_t').get('tr_text') == 'Cassette Mode', 'the page asset: a title Now Playing, the Cassette Mode header, one row with the cassette glyph and its value label')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_tapetheme.bin'), 'rb').read())
    expect(all(tree.find(f'pod_check{i}').get('visible') == 'false' and tree.find(f'pod_check{i}').get('sensitive') == 'false' and tree.find(f'pod_row{i}').find('pod_icon') is None for i in range(3))
           and tree.find('pod_note0_t').get('tr_text') == 'Applies the next time Cassette Mode opens.', 'the picker asset: three rows without a glyph, a hidden insensitive check each, the note')


def symmetry_tests(ctx):
    """The static art is symmetric about the cassette's centre line x 240 (479.5 in pixel terms): the label is centred (32 px of shell each side, a bug in V2.1oXTR had 25 and 39), and so
    are the panel, the window, the reels, the bottom section and its holes, the screws; the pairs and the centred parts from the layout constants, and the shell picture's own shapes."""
    expect = ctx.expect
    A = tape_art
    C = 240
    mid = lambda b: (b[0] + b[2]) / 2
    for name, b in (('the cassette', A.CASS), ('the label', A.LABEL), ('the panel', A.PANEL), ('the clear window', A.CLEAR), ('the window overlay', A.TOP_RECT), ('the label\'s frame (label +- 4)', (A.LABEL[0] - 4, 0, A.LABEL[2] + 4, 0))):
        expect(mid(b) == C, f'{name} is centred on x {C} ({b[0]} .. {b[2]})')
    expect(A.REEL_CX[0] + A.REEL_CX[1] == 2 * C and A.LABEL[0] - A.CASS[0] == A.CASS[2] - A.LABEL[2] and A.LABEL[0] - A.CASS[0] == 32, 'the reels are mirror images; the shell shows 32 px left and right of the label')
    expect(A.PANEL[0] - A.LABEL[0] == A.LABEL[2] - A.PANEL[2] and A.CLEAR[0] - A.PANEL[0] == A.PANEL[2] - A.CLEAR[2], 'the panel sits centred in the label, the window in the panel')
    expect(A.SCREW_AT[0] + (W - 1 - A.SCREW_AT[0]) == W - 1 and 24 + 456 == 2 * C, 'the corner screws are at x 24 and 456')
    # the layout on the label keeps its spacing to the label's edges on both sides: the title and the times start and end the same margin in, the marks the same distance from the right edge as before
    T = A.TEXT
    expect(T['title']['x'] - A.LABEL[0] == 10 and A.LABEL[2] - (T['title']['x'] + T['title']['room']) == 8 and A.LABEL[2] - T['times']['x'] == 8 and A.LABEL[2] - A.PLAY_AT[0] == 20 == A.LABEL[2] - A.REPEAT_AT[0],
           'text and marks keep their old spacing to the label edges (10 / 8 / 8 / 20 px)')
    expect(T['big']['rect'][0] - A.LABEL[0] == 2 and T['status']['rect'][2] <= A.LABEL[2] and A.ARROW_AT[0] + 34 < T['status']['rect'][0] and T['model']['rect'][2] < A.ARROW_AT[0], 'the A, the fine print, the arrow and the status line are on the label in their order')
    # the shell picture (every theme): the label's paper, the band and the dark panel start and end symmetrically; the bottom section's holes are mirror images
    for t in THEMES:
        sh = shell_land(t).convert('RGB').load()
        def runs(y, pred, x0=0, x1=480):
            out, start = [], None
            for x in range(x0, x1):
                if pred(sh[x, y]):
                    if start is None: start = x
                elif start is not None: out.append((start, x - 1)); start = None
            if start is not None: out.append((start, x1 - 1))
            return out
        def mirrored(rs, tol=1):
            return all(any(abs((a + b) - (479 - d + 479 - c)) <= 2 * tol for c, d in rs) for a, b in rs)
        panel = runs(110, lambda p: max(p) < 24, 60, 420)
        expect(panel and (panel[0][0] + panel[-1][1]) in (479, 480, 478), f'{t}: the dark panel spans {panel[0][0]} .. {panel[-1][1]}, centred on x 240')
        paper_t = A.THEMES[t]['paper'][0]
        near = lambda p: sum(abs(p[i] - paper_t[i]) for i in range(3)) < 60
        pr = runs(50, near, 20, 460)
        expect(pr and abs((pr[0][0] + pr[-1][1]) - 479) <= 3, f'{t}: the paper spans {pr[0][0]} .. {pr[-1][1]} (centre {(pr[0][0] + pr[-1][1]) / 2}), centred on x 240')
        band = A.THEMES[t]['band']
        if t != 'metal':   # (the Metal band is nearly the shell's colour: its paper stands for it)
            bn = runs(150, lambda p: sum(abs(p[i] - band[i]) for i in range(3)) < 30, 20, 460)
            expect(bn and abs((bn[0][0] + bn[-1][1]) - 479) <= 3 and bn[0][0] <= A.LABEL[0] + 1, f'{t}: the band spans {bn[0][0]} .. {bn[-1][1]}, the label\'s width, centred on x 240')
        dk = lambda p: max(p) < 14
        left, right = runs(290, dk, 130, 171), runs(290, dk, 309, 350)
        expect(left and right and (479 - left[-1][1], 479 - left[0][0]) == (right[0][0], right[-1][1]),
               f'{t}: the pinch-roller holes at y 290 span {left[0][0]} .. {left[-1][1]} and {right[0][0]} .. {right[-1][1]}: mirror images about x 240 (the highlight inside a hole is lit from one side by design)')
    # the body's outline: where the picture leaves the surface colour, left and right (the drop shadow is cast to the right and down by design, so look at the lit rim at y 160)
    sh = shell_land('normal').convert('RGB').load()
    lit = [x for x in range(0, 480) if sum(sh[x, 160]) > sum(A.BG) + 60]
    expect(lit and abs(lit[0] + lit[-1] - 479) <= 8, f'the body\'s lit outline at y 160 spans {lit[0]} .. {lit[-1]}: centred on x 240 (a few px of the drop shadow aside)')
    # the knurl: its cell grid is aligned the same on both sides (4 px pitch from x 0), and the unknurled rim band is as wide each side
    expect(480 % 4 == 0 and (A.CASS[0] - 5) % 4 == 0, 'the knurl grid starts at x 0 and 480 is a whole number of cells: the cells mirror about x 240')


def run(ctx):
    for fn in SECTIONS: fn(ctx)


SECTIONS = [number_tests, symmetry_tests, asset_tests, theme_tests, setting_tests, draw_tests, reel_tests, hub_tests, mark_tests, status_tests, live_tests, touch_tests, idle_touch_tests, life_tests, paint_tests]



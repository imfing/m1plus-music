"""The Vinyl page (patch/vinyl.c, tools/vinyl_art.py, tools/pod_ui.py build_vinyl_page, docs/modules/vinyl.md): a fullscreen turntable Now Playing page.

What is proved, on the real compiled payload under Unicorn (the stock calls it makes mocked, the bitmaps real memory):
  * the numbers of offsets.inc and the payload's tables against tools/vinyl_art.py (the record, the label, the pivot, the arm picture's pivot, the arm's
    turns on the groove and parked, the layers' rectangles, the key band), the built asset (a fullscreen window, one 320 x 480 view, the text labels) and that
    the pictures decode to the generator's pixels exactly (tools/png_pack.py packs them smaller, a palette with tRNS where the colours fit);
  * the picture: the frame is, pixel for pixel, a python model of the composition (the base, the label turned bilinear, the lid, the arm's shadow and the
    premultiplied arm turned bilinear, the cap, the key cells) at every state tested, and close to the approved design (tools/vinyl_art.py design);
  * the record turning at 33 1/3 rpm while playing (with its speed-up and slow-down), still when paused; the arm on the groove, following the position,
    swinging to its park on pause; what is invalidated is only what changed;
  * the text (title and its twin, artist, times, status line) set on the page's labels; the cover as the label, vinyl_label without one;
  * taps only: the chevron closes, the keys play / pause, skip back and forward through the stock quick-click functions (drawn pressed while held), a tap on
    the record plays / pauses; no swipe, no grab, no move handler;
  * the page's life: one timer retimed with timer_modify, removed on to-background and destroy, the idle power rules.
The emulated frames are written to out/preview/vinyl-emu-*.png (with the text as the labels draw it), next to the design's (vinyl-emu-*-design.png)."""
import math, os, struct
from pathlib import Path
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs
import mod_icons, vinyl_art
from PIL import Image, ImageChops

A = vinyl_art
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_vinyl.bin')
EVT_DOWN, EVT_MOVE, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
EVT_BG, EVT_FG, EVT_DESTROY, EVT_PAINT = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG'], O['EVT_DESTROY'], O['EVT_AFTER_PAINT']
WIN = 0x24200000
SYSBAR = pod.DATA['SYSTEM_BAR'][0]
REC_FILE = '/mnt/data/m1plus/vinyl-record'
THEME_FILE = '/mnt/data/m1plus/vinyl-base'
COMPOSE_MAX = 6000000   # instructions: the Cover record composed once into the base, the same on a track change (3.1 M measured, to be re-measured); not a tick's cost
COVER_MAX = 18000000   # instructions: a track change with Cover (the tint, the ring composed, the box composed again; the black case loads vinyl_base). 16.4 M measured (tint to tint 12.4 M, to black 16.4 M: only the disc written back, the grain kept), 5.5 M of it any track change
W, H = 320, 480
OUT = os.path.join(ROOT, 'out', 'preview')
LABELS = ('vn_title', 'vn_title2', 'vn_artist', 'vn_times', 'vn_status')
K_NONE, K_CLOSE, K_PREV, K_PLAY, K_NEXT, K_RECORD = range(6)


class VM(Machine):
    """The machine plus what the page calls that the shared mocks do not know: the player, the playing time, the quick clicks, the status bar, the invalidate."""
    def __init__(self):
        super().__init__()
        self.status, self.pt, self.cmds, self.rects = 2, None, [], []
        self.window = WIN
        self.load_image = 0
        self.canvas = self.alloc(0x80)
        for w in ('vinyl_view', 'pgbar_battery', 'img_battery', 'label_volume') + LABELS: Machine.widget(self, w)
        self.setword(SYSBAR, self.alloc(0x80))
        self.props[(self.widgets['pgbar_battery'], 'value')] = 60
        self.battery_img, self.volume = 'bar_power', '42'
        self.wall = 1800000000 + 13 * 3600 + 7 * 60
        self.tz = 8 * 3600
        self.mock_ms = 1000
        self.view = self.widgets['vinyl_view']
        win = self.alloc(0x80)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, 0)): self.setword(win + off, v)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, win)): self.setword(self.view + off, v)
        self.images = {n: self.png(n) for n in A.NAMES}
        for n in ('mclGetPlayStatus', 'playpause_quick_click', 'next_quick_click', 'prev_quick_click', 'get_playtimeandlength', 'widget_get_text', 'time_now_ms'):
            self.handlers[pod.FUNCTIONS[n][2]] = n

    def png(self, n):
        im = asset_image(n)
        return (im.width, im.height, im.tobytes())

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
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
            ret = self.cstr(self.battery_img) if self.read_cstr(a1) == 'image' else a2
        elif name == 'widget_invalidate_force':
            self.rects.append(struct.unpack('<4i', self.u.mem_read(a1, 16)) if a1 else None)
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def playing(self, title='Midnight City', artist='M83', album='Hurry Up', pos=200, length=243, path='/mnt/mmc/m/midnight.flac'):
        self.play([self.record(album=album, artist=artist, path=path, title=title, name=os.path.basename(path))], 0)
        self.pt = (pos, length)

    def open(self):
        self.calls = []
        return self.call(PSYMS['vinyl_open'], count=60000000) & 0xffffffff

    def open_idle(self):
        self.calls = []
        return self.call(PSYMS['vinyl_open_idle'], count=60000000) & 0xffffffff

    def first(self):
        self.calls = []; self.rects = []
        self.call(PSYMS['vn_first'], a0=0, count=400000000)

    def tick(self, ms=50):
        self.mock_ms += ms
        self.calls = []; self.rects = []
        self.call(PSYMS['vn_tick'], a0=0, count=400000000)

    def paint(self):
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.blits = []
        self.call(PSYMS['vn_on_paint'], a0=0, a1=ev, count=2000000)
        return list(self.blits)

    def frame_words(self):
        data, w, h = [v for v in self.bitmaps.values() if v[1:] == (320, 480)][-1]
        return list(struct.unpack('<%dI' % (w * h), bytes(self.u.mem_read(data, w * h * 4))))

    def frame(self):
        data, w, h = [v for v in self.bitmaps.values() if v[1:] == (320, 480)][-1]
        return Image.frombytes('RGBA', (w, h), bytes(self.u.mem_read(data, w * h * 4)))

    def cover_words(self):
        data, w, h = [v for v in self.bitmaps.values() if v[1:] == (152, 152)][-1]   # the decoded cover (made after vinyl_label)
        return list(struct.unpack('<%dI' % (w * h), bytes(self.u.mem_read(data, w * h * 4))))

    def text_of(self, name):
        t = [c[2] for c in self.calls_all if c[0] == 'widget_set_text_utf8' and c[1] == self.widgets[name]]
        return t[-1] if t else None

    def ptr(self, kind, x, y, t=0):
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, {'down': EVT_DOWN, 'move': EVT_MOVE, 'up': EVT_UP, 'abort': EVT_ABORT}[kind]); self.setword(e + 8, t); self.setword(e + 0x18, x); self.setword(e + 0x1c, y)
        self.calls = []; self.rects = []
        return self.call(PSYMS['vn_on_touch'], a0=0, a1=e, count=200000000)

    def gesture(self, a, b, t=1000):
        calls = []
        self.ptr('down', *a, t); calls += self.calls
        for i in range(1, 4):
            self.ptr('move', a[0] + (b[0] - a[0]) * i // 4, a[1] + (b[1] - a[1]) * i // 4, t + 20 * i); calls += self.calls
        self.ptr('up', *b, t + 100); self.calls = calls + self.calls
        return list(self.calls)


def machine(playing=True, status=2, cover=False, rec=0, theme=0, **kw):
    m = VM()
    m.status = status
    if theme: m.fs[THEME_FILE] = b'%d\n' % theme
    if rec: m.fs[REC_FILE] = b'%d\n' % rec
    if playing: m.playing(**kw)
    if cover:   # the album's cached cover (/mnt/mmc/.m1plus/covers/<key>-168.jpg), as the album page made it
        path = art_file(album_key(kw.get('artist', 'M83'), kw.get('album', 'Hurry Up')))
        m.files[path] = 9000
        im = A.cover(cover if isinstance(cover, str) else 'sunset', 168).convert('RGBA')
        m.images['file://' + path] = (168, 168, im.tobytes())
    return m


def opened(**kw):
    m = machine(**kw)
    assert m.open() == 0
    m.timers = []
    m.calls_all = []
    m.first(); m.calls_all += m.calls
    return m


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# The model: patch/vinyl.c's integer arithmetic in python
SIN_T = [0, 286, 572, 857, 1143, 1428, 1713, 1997, 2280, 2563, 2845, 3126, 3406, 3686, 3964, 4240, 4516, 4790, 5063, 5334, 5604, 5872, 6138, 6402, 6664, 6924, 7182, 7438, 7692, 7943, 8192,
         8438, 8682, 8923, 9162, 9397, 9630, 9860, 10087, 10311, 10531, 10749, 10963, 11174, 11381, 11585, 11786, 11982, 12176, 12365, 12551, 12733, 12911, 13085, 13255, 13421, 13583,
         13741, 13894, 14044, 14189, 14330, 14466, 14598, 14726, 14849, 14968, 15082, 15191, 15296, 15396, 15491, 15582, 15668, 15749, 15826, 15897, 15964, 16026, 16083, 16135, 16182,
         16225, 16262, 16294, 16322, 16344, 16362, 16374, 16382, 16384]


def q(t):
    i = t >> 4
    return SIN_T[90] if i >= 90 else SIN_T[i] + (((SIN_T[i + 1] - SIN_T[i]) * (t & 15)) >> 4)


def isin(a):
    t = a % 5760
    return q(t) if t < 1440 else q(2880 - t) if t < 2880 else -q(t - 2880) if t < 4320 else -q(5760 - t)


def icos(a): return isin(a + 1440)


def tdiv(a, b): return -((-a) // b) if a < 0 else a // b


def groove_at(pos, length, table):
    p = pos * 65536 // length if length > 0 else 0
    p = min(p, 65536); i, f = p >> 11, p & 2047
    return table[-1] if i >= 32 else table[i] + (((table[i + 1] - table[i]) * f) >> 11)


def lerp(p, q_, f):
    g = 256 - f
    return ((((p & 0xff00ff) * g + (q_ & 0xff00ff) * f) >> 8) & 0xff00ff) | (((((p >> 8) & 0xff00ff) * g + ((q_ >> 8) & 0xff00ff) * f)) & 0xff00ff00)


def mix(v, c, a):
    w = a + (a >> 7)
    return 0xff000000 | ((((v & 0xff00ff) * (256 - w) + (c & 0xff00ff) * w) >> 8) & 0xff00ff) | ((((v & 0xff00) * (256 - w) + (c & 0xff00) * w) >> 8) & 0xff00)


def dim(v, a):
    w = 256 - (a + (a >> 7))
    return 0xff000000 | (((v & 0xff00ff) * w >> 8) & 0xff00ff) | (((v & 0xff00) * w >> 8) & 0xff00)


def over(v, p):
    a = p >> 24; w = 256 - (a + (a >> 7))
    return 0xff000000 | ((((v & 0xff00ff) * w >> 8) & 0xff00ff) + (p & 0xff00ff)) | ((((v & 0xff00) * w >> 8) & 0xff00) + (p & 0xff00))


def words(im, pm=False):
    out = []
    for r, g, b, a in im.convert('RGBA').getdata():
        if pm: r, g, b = (r * a + 127) // 255, (g * a + 127) // 255, (b * a + 127) // 255
        out.append(r | g << 8 | b << 16 | a << 24)
    return out


_L = {}
def layers(theme='graphite'):
    """The words of every layer under a plinth theme (plain layer names)."""
    if theme not in _L:
        d = {n: words(asset_image(A.tname(n, theme)), n == 'vinyl_arm') for n in A.THEMED}
        if A.theme_grain(theme):   # the page grains its base once loaded (vn_grain)
            d['vinyl_base'] = words(A.grain_apply(asset_image(A.tname('vinyl_base', theme)), asset_image(A.tname('vinyl_grain', theme)).getchannel('R'), A.theme_grain(theme)))
        d['vinyl_label'] = words(asset_image('vinyl_label'))
        _L[theme] = d
    return _L[theme]


def sprite(img, vx, vy, c, s):
    AW, AH, PX, PY = O['VN_ARM_W'], O['VN_ARM_H'], O['VN_ARM_PX'], O['VN_ARM_PY']
    fx = ((c * vx + s * vy) >> 7) + PX * 256 - 128; fy = ((c * vy - s * vx) >> 7) + PY * 256 - 128
    ix, iy, ax, ay = fx >> 8, fy >> 8, fx & 255, fy & 255
    if ix < -1 or iy < -1 or ix >= AW or iy >= AH: return 0
    tap = lambda x, y: img[y * AW + x] if 0 <= x < AW and 0 <= y < AH else 0
    return lerp(lerp(tap(ix, iy), tap(ix + 1, iy), ax), lerp(tap(ix, iy + 1), tap(ix + 1, iy + 1), ax), ay)


def label_px(src, vx, vy, lc, ls):
    P, R = O['VN_LAB_PX'], O['VN_LAB_R']
    fx = ((lc * vx + ls * vy) >> 7) + R * 256 - 128; fy = ((lc * vy - ls * vx) >> 7) + R * 256 - 128; lim = (P - 2) * 256 + 255
    fx, fy = min(max(fx, 0), lim), min(max(fy, 0), lim)
    ix, iy, ax, ay = fx >> 8, fy >> 8, fx & 255, fy & 255
    r = iy * P + ix
    return 0xff000000 | lerp(lerp(src[r], src[r + 1], ax), lerp(src[r + P], src[r + P + 1], ax), ay)


def arm_box(a):
    AW, AH, PX, PY = O['VN_ARM_W'], O['VN_ARM_H'], O['VN_ARM_PX'], O['VN_ARM_PY']
    c, s = icos(a), isin(a); xs, ys = [], []
    for ux, uy in ((-PX, -PY), (AW - PX, -PY), (-PX, AH - PY), (AW - PX, AH - PY)):
        xs.append(O['VN_PIV_X'] + ((c * ux - s * uy) >> 14)); ys.append(O['VN_PIV_Y'] + ((s * ux + c * uy) >> 14))
    return (max(min(xs) - 2, 0), max(min(ys) - 2, 0), min(max(xs) + 3 + O['VN_SH_DX'], W), min(max(ys) + 3 + O['VN_SH_DY'], O['VN_BAND_Y0']))


def rec_base(stops, theme='graphite'):
    """The page's base for the Cover record: vinyl_base with the record composed from vinyl_rec's map by the ramp of `stops` (patch/vinyl.c vn_recolour, integer for integer): inside the rim the
    table's colour, on the rim the base's plus the colour's difference from the black record's rim by the disc's coverage."""
    base = list(layers(theme)['vinyl_base']); tab = A.ramp_table([(t, c) for t, c in stops]); x0, y0, x1, y1 = A.REC_BOX; R = O['VN_REC_R']; K = O['VN_REC_K']
    for i, (m, _, _, _) in enumerate(asset_image('vinyl_rec').convert('RGBA').getdata()):
        if not m: continue
        x, y = x0 + i % (x1 - x0), y0 + i // (x1 - x0); vx, vy = 2 * (x - O['VN_REC_X']) + 1, 2 * (y - O['VN_REC_Y']) + 1; d2 = vx * vx + vy * vy
        w = tab[m][0] | tab[m][1] << 8 | tab[m][2] << 16 | 0xff000000
        if d2 > (2 * R - 2) ** 2:
            c = 8 * R + 4 - math.isqrt(16 * d2); cov = 0 if c <= 0 else 255 if c >= 8 else c * 32; b = base[y * W + x]; out = 0xff000000
            for sh in (0, 8, 16):
                out |= max(0, min(255, (b >> sh & 255) + (((w >> sh & 255) * cov + 127) // 255) - ((K * cov + 127) // 255))) << sh
            w = out
        base[y * W + x] = w
    return base


def model(ang, arm, label_src=None, playkey=0, pressed=K_NONE, rec_base_=None, theme='graphite'):
    """The whole frame (a list of words) as the payload composes it: the label turned by ang (label_src: the cover's words, None for vinyl_label), the arm at arm."""
    L = layers(theme); base, lid, cap, armw, sh = rec_base_ or L['vinyl_base'], L['vinyl_lid'], L['vinyl_cap'], L['vinyl_arm'], L['vinyl_armsh']
    src = label_src or L['vinyl_label']
    lc, ls, ac, as_ = icos(ang), isin(ang), icos(arm), isin(arm)
    out = list(base); box = arm_box(arm)
    RX, RY, IN = O['VN_REC_X'], O['VN_REC_Y'], O['VN_LAB_IN']
    LX, LY, LP, CX, CY, CP = O['VN_LID_X'], O['VN_LID_Y'], O['VN_LID_PX'], O['VN_CAP_X'], O['VN_CAP_Y'], O['VN_CAP_PX']
    PVX, PVY, SDX, SDY = O['VN_PIV_X'], O['VN_PIV_Y'], O['VN_SH_DX'], O['VN_SH_DY']
    for y in range(O['VN_BAND_Y0']):
        for x in range(W):
            vx, vy = 2 * (x - RX) + 1, 2 * (y - RY) + 1
            inl = vx * vx + vy * vy <= 4 * IN * IN
            inlid = LX <= x < LX + LP and LY <= y < LY + LP
            inarm = box[0] <= x < box[2] and box[1] <= y < box[3]
            incap = CX <= x < CX + CP and CY <= y < CY + CP
            if not (inl or inlid or inarm or incap): continue
            c = base[y * W + x]
            if inl: c = label_px(src, vx, vy, lc, ls)
            if inlid:
                v = lid[(y - LY) * LP + x - LX]
                if v >> 24: c = mix(c, v, v >> 24)
            if inarm:
                s = sprite(sh, 2 * (x - SDX - PVX) + 1, 2 * (y - SDY - PVY) + 1, ac, as_) >> 24
                p = sprite(armw, 2 * (x - PVX) + 1, 2 * (y - PVY) + 1, ac, as_)
                if s: c = dim(c, s)
                if p >> 24: c = over(c, p)
            if incap:
                v = cap[(y - CY) * CP + x - CX]
                if v >> 24: c = mix(c, v, v >> 24)
            out[y * W + x] = c | 0xff000000
    keys = L['vinyl_keys']; KW = O['VN_KEYS_W']
    for k, x0, x1 in ((K_PREV, O['VN_PREV_X0'], O['VN_PLAY_X0']), (K_PLAY, O['VN_PLAY_X0'], O['VN_NEXT_X0']), (K_NEXT, O['VN_NEXT_X0'], O['VN_NEXT_X1'])):
        down = pressed == k
        cell = (playkey + 2 * down) * 46 if k == K_PLAY else (O['VN_CELL_PREV'] if k == K_PREV else O['VN_CELL_NEXT']) if down else -1
        for y in range(O['VN_BAND_Y0'], O['VN_BAND_Y1']):
            for x in range(x0, x1):
                out[y * W + x] = base[y * W + x] if cell < 0 else keys[(y - O['VN_BAND_Y0']) * KW + cell + x - x0]
    return out


def to_image(ws): return Image.frombytes('RGBA', (W, H), struct.pack('<%dI' % len(ws), *ws))


def ndiff(a, b):
    bad = [(i % W, i // W, hex(x), hex(y)) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return len(bad), bad[:3]


class Spin:
    """The label's turn and speed, the arm's turn, as vn_update moves them (dt in ms)."""
    def __init__(self, table):
        self.spin, self.acc, self.ang, self.arm, self.table = 0, 0, 0, None, table
        self.sw_from = self.sw_to = self.sw_t = self.sw_len = 0

    def step(self, dt, playing, pos=0, length=0, track=True, force=False):
        if playing and self.spin < 256: self.spin = min(256, self.spin + dt * 256 // O['VN_SPINUP_MS'] + 1)
        elif not playing and self.spin > 0: self.spin = max(0, self.spin - (dt * 256 // O['VN_SPINDOWN_MS'] + 1))
        if not self.spin: self.acc = 0
        self.acc += dt * self.spin; st, self.acc = self.acc // 80, self.acc % 80
        self.ang = (self.ang + st) % 5760
        to = (O['VN_PARK'] if not track else groove_at(pos, length, self.table) if playing
              else self.arm if self.spin and self.arm is not None else O['VN_PARK'])   # paused: the arm waits for the record to stop
        if force or self.arm is None: self.arm, self.sw_len = to, 0; return
        self.arm = self.arm_next(to, dt)

    def arm_next(self, to, dt):
        """vn_arm_next: a change over VN_ARM_SNAP is a smoothstep swing over VN_SWING_MS + 1 ms a 1/16 degree; a small one is drawn at VN_ARM_STEP."""
        snap, d = O['VN_ARM_SNAP'], to - self.arm
        if self.sw_len:
            if abs(to - self.sw_to) > snap: self.sw_len = 0
            else: self.sw_to = to
        if not self.sw_len:
            if abs(d) <= snap: return to if abs(d) >= O['VN_ARM_STEP'] else self.arm
            self.sw_from, self.sw_to, self.sw_t, self.sw_len = self.arm, to, 0, O['VN_SWING_MS'] + abs(d)
        self.sw_t += dt
        if self.sw_t >= self.sw_len: self.sw_len = 0; return self.sw_to
        f = self.sw_t * 256 // self.sw_len; e = (f * f * (768 - 2 * f)) >> 16
        return self.sw_from + tdiv((self.sw_to - self.sw_from) * e, 256)


def payload_groove():
    a = PSYMS['vn_groove']
    m = Machine()
    return list(struct.unpack('<33h', bytes(m.u.mem_read(a, 66))))


def side():
    import preview_icons as PI
    return PI.Side(WORK, True)


def dump(m, name, f, ang, theme='graphite'):
    """out/preview/vinyl-emu-<name>.png: the frame with the labels' text drawn as the AWTK labels draw it, and the design at the same state next to it."""
    os.makedirs(OUT, exist_ok=True)
    s = side(); im = m.frame().convert('RGBA')
    A.use(theme)
    try:
        A.text(s, im, dict(f, title=m.text_of('vn_title'), artist=m.text_of('vn_artist')), m.text_of('vn_status'), m.text_of('vn_times'))
        im.convert('RGB').save(os.path.join(OUT, f'vinyl-emu-{name}.png'))
        d = A.design(s, dict(f, angle=-ang / 16))
    finally:
        A.use('graphite')
    d.convert('RGB').save(os.path.join(OUT, f'vinyl-emu-{name}-design.png'))
    diff = ImageChops.difference(im.convert('RGB'), d.convert('RGB'))
    return sum(sum(px) for px in diff.getdata()) / (W * H * 3)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def number_tests(ctx):
    expect = ctx.expect
    expect((O['VN_W'], O['VN_H']) == (A.W, A.H) == (320, 480), 'the page is portrait 320 x 480')
    expect((O['VN_REC_X'], O['VN_REC_Y'], O['VN_REC_R'], O['VN_LAB_R'], O['VN_LAB_PX'], O['VN_LAB_IN']) == (*A.REC_C, A.REC_R, A.LAB_R, A.LAB_PX, A.LAB_IN), 'the record and its label')
    expect((O['VN_RB_X0'], O['VN_RB_Y0'], O['VN_RB_X0'] + O['VN_RB_W'], O['VN_RB_Y0'] + O['VN_RB_H']) == A.REC_BOX and O['VN_RECS'] == len(A.RECORD_NAMES) and O['VN_REC_COVER'] == A.RECORD_NAMES.index('cover'), 'vinyl_rec\'s box, and the record colours')
    expect((O['VN_PIV_X'], O['VN_PIV_Y']) == A.PIVOT and (O['VN_ARM_W'], O['VN_ARM_H'], O['VN_ARM_PX'], O['VN_ARM_PY']) == A.arm_geometry(), f'the pivot and the arm picture with its pivot {A.arm_geometry()}')
    expect((O['VN_SH_DX'], O['VN_SH_DY']) == A.ARM_SHADOW[:2], 'the arm\'s shadow offset')
    expect(O['VN_PARK'] == A.park16() and payload_groove() == A.groove_table16() and O['VN_GROOVE_N'] == A.GROOVE_N, f'the arm\'s turns: parked {A.park16()}, on the groove {A.groove_table16()[::8]}')
    g = A.groove_table16()
    expect(g == sorted(g) and g[0] > O['VN_PARK'] + 160, 'the arm turns inward as the track plays, and its park is well outside the record')
    expect((O['VN_LID_X'], O['VN_LID_Y'], O['VN_LID_X'] + O['VN_LID_PX'], O['VN_LID_Y'] + O['VN_LID_PX']) == A.LID_RECT and (O['VN_CAP_X'], O['VN_CAP_Y'], O['VN_CAP_X'] + O['VN_CAP_PX'], O['VN_CAP_Y'] + O['VN_CAP_PX']) == A.CAP_RECT,
           'the lid and the cap rectangles')
    expect((O['VN_BAND_Y0'], O['VN_BAND_Y1']) == A.BAND_Y and (O['VN_PREV_X0'], O['VN_PLAY_X0'], O['VN_NEXT_X0'], O['VN_NEXT_X1']) == (A.KEY_COLS['prev'][0], A.KEY_COLS['play'][0], A.KEY_COLS['next'][0], A.KEY_COLS['next'][1])
           and A.KEY_COLS['prev'][1] == A.KEY_COLS['play'][0] and A.KEY_COLS['play'][1] == A.KEY_COLS['next'][0], 'the key band and the keys\' columns')
    expect((O['VN_KEYS_W'], O['VN_BAND_Y1'] - O['VN_BAND_Y0']) == A.KEY_SHEET and A.KEY_CELLS[('prev', 2)] == O['VN_CELL_PREV'] and A.KEY_CELLS[('next', 2)] == O['VN_CELL_NEXT']
           and all(A.KEY_CELLS[('play', s)] == s * 46 for s in range(4)) and A.KEY_COLS['play'][1] - A.KEY_COLS['play'][0] == 46, 'the key sheet\'s cells')
    expect((O['VN_CLOSE_X1'], O['VN_CLOSE_Y1']) == A.CLOSE_RECT[2:] and A.CLOSE_RECT[:2] == (0, 0) and O['VN_TAP_PX'] == A.TAP_PX, 'the close area and the tap distance')
    expect(all(A.BAND_Y[0] <= A.KEY_Y - r - 5 and A.KEY_Y + r + 5 <= A.BAND_Y[1] for _, _, r in A.KEYS) and all(A.KEY_COLS[n][0] <= cx - r - 3 and cx + r + 3 <= A.KEY_COLS[n][1] for n, cx, r in A.KEYS),
           'each key lies inside its own columns with room for its shadow')
    expect(A.REC_C[1] + A.REC_R < A.BAND_Y[0] and arm_box(O['VN_PARK'])[3] < A.BAND_Y[0], 'the record and the parked arm stay above the key band (never composed over it)')
    expect(60 >= O['VN_PLAY_MS'] >= 40 and O['VN_IDLE_MS'] == 500, 'the timer: 50 ms while something moves, 500 ms at rest')
    m = Machine()
    for a in (0, 1, 15, 16, 400, 1439, 1440, 1441, 2000, 2880, 3000, 4320, 5000, 5759, -16, -1000, 10000):
        expect(m.call(PSYMS['vn_sin'], a0=a & 0xffffffff, count=10000) & 0xffffffff == isin(a) & 0xffffffff, f'vn_sin({a}) is the model\'s')
    import math
    expect(all(abs(isin(a) / 16384 - math.sin(math.radians(a / 16))) < 2e-4 for a in range(-5760, 5760, 37)), 'the sine table is accurate to 1/5000')
    for pos, ln in ((0, 243), (200, 243), (243, 243), (1, 3), (0, 0), (500, 243), (32000, 65535)):
        expect(m.call(PSYMS['vn_groove_at'], a0=pos, a1=ln, count=10000) == groove_at(pos, ln, g), f'vn_groove_at({pos}, {ln})')
    for a in (O['VN_PARK'], g[0], g[-1], 1800):
        b = m.alloc(16); m.call(PSYMS['vn_arm_box'], a0=a, a1=b, count=20000)
        expect(struct.unpack('<4i', bytes(m.u.mem_read(b, 16))) == arm_box(a), f'vn_arm_box({a}) is the model\'s {arm_box(a)}')
    for pt, want in (((10, 10), K_CLOSE), ((51, 43), K_CLOSE), ((52, 10), K_NONE), ((96, 196), K_RECORD), ((250, 196), K_RECORD), ((300, 300), K_NONE), ((200, 449), K_PREV),
                     ((246, 449), K_PLAY), ((292, 449), K_NEXT), ((171, 479), K_PREV), ((317, 421), K_NEXT), ((100, 449), K_NONE), ((96, 419), K_NONE)):
        expect(m.call(PSYMS['vn_hit'], a0=pt[0], a1=pt[1], count=10000) == want, f'a touch at {pt} is {want}')
    d = open(DEMO, 'rb').read(); image = bytearray(d)
    expect(all(struct.unpack_from('<I', d, pod.fileoff(image, a))[0] == old for a, old, _ in pod.TAPE_PINS + pod.IPOD_PINS), 'the stock words the page relies on (the Tape page\'s invalidate, the Pod\'s quick clicks and timer) are as pinned')


def asset_tests(ctx):
    expect = ctx.expect
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    expect(tree.name == 'm1plus_vinyl_page' and tree.get('fullscreen') == 'true', 'the window is fullscreen (480 px, the status bar not drawn)')
    by = {w.name: w for w in tree.walk() if w.name}
    v = by['vinyl_view']
    expect((v.x, v.y, v.w, v.h) == (0, 0, 320, 480) and v.get('sensitive') != 'false' and v.get('visible') != 'false' and tree.children[0] is v, 'vinyl_view is the whole window, first, and takes the touches')
    for name, field, dx in (('vn_title', 'title', 0), ('vn_title2', 'title', 1), ('vn_artist', 'artist', 0), ('vn_times', 'times', 0), ('vn_status', 'status', 0)):
        w = by[name]; x, y, bw, bh = A.label_box(field); t = A.TEXT[field]
        expect(w.type == 'hscroll_label' and (w.x, w.y, w.w, w.h) == (x + dx, y, bw, bh) and w.get('sensitive') == 'false' and w.get('ellipses') == 'true' and w.get('only_parent_focus') == 'true'
               and w.get('style:normal:font_size') == str(t['px']) and w.get('style:normal:text_color') == '#%02X%02X%02X' % t['rgb'], f'{name}: an insensitive, non-scrolling label with an ellipsis at {(x + dx, y, bw, bh)}, {t["px"]} px')
    expect(by['label_title'].get('visible') == 'false' and by['label_title'].get('sensitive') == 'false' and by['label_title'].get('tr_text') == 'Vinyl Mode', 'label_title (hidden) carries the page\'s name')
    root = asset_tree(os.path.join(WORK, UI)); root.h = 480
    for x, y in ((160, 240), (5, 5), (246, 449), (30, 392), (315, 475)):
        expect(stock_target(Machine(), root, x, y)[-1] == 'vinyl_view', f'a touch at ({x}, {y}) reaches vinyl_view (the labels are insensitive)')
    geo = A.arm_geometry()[:2]
    base_sizes = {'vinyl_base': (320, 480), 'vinyl_lid': (160, 160), 'vinyl_arm': geo, 'vinyl_armsh': geo, 'vinyl_cap': (32, 32), 'vinyl_keys': A.KEY_SHEET}
    sizes = {A.tname(n, th): z for th in A.THEME_NAMES for n, z in base_sizes.items()}
    sizes.update({'vinyl_label': (152, 152), 'vinyl_rec': (A.REC_BOX[2] - A.REC_BOX[0], A.REC_BOX[3] - A.REC_BOX[1])})
    sizes.update({n: (320, 480) for n in A.GRAINED})
    gen = A.images()
    for n, size in sizes.items():
        im = asset_image(n); built = open(asset_path(n), 'rb').read()
        expect(im.size == size == gen[n].size and built == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() and same_pixels(built, gen[n]), f'{n}: {size}, the generator\'s RGBA pixels exactly')
    expect(set(sizes) == set(A.NAMES) and len(sizes) == 6 * len(A.THEME_NAMES) + 2 + 1 and A.GRAINED == ('vinyl_grain',) and A.GRAIN == O['VN_GRAIN'] and not A.theme_grain('white'),
           'the pictures: six a plinth theme, two shared, the grain\'s weight of Graphite (VN_GRAIN; Snow has no grain)')
    gw = asset_image('vinyl_grain'); gd = list(gw.getdata())
    expect(all(px[1:] == (0, 0, 255) for px in gd) and gw.getpixel((300, 200))[0] == 255 and gw.getpixel((96, 196))[0] == 0 and gw.getpixel((246, 449))[0] == 0,
           'vinyl_grain: the weight in R (the plinth 255; the record and the keys 0), G, B 0, opaque')
    total = sum(os.path.getsize(asset_path(n)) for n in sizes) + os.path.getsize(asset_path('pod_ic_vinyl'))
    print('  vinyl pictures: %d bytes (%s)' % (total, {n: os.path.getsize(asset_path(n)) for n in sizes}))
    expect(total < 560000, f'the pictures add {total} bytes to the rootfs')
    for n in ('vinyl_base', 'vinyl_lid', 'vinyl_arm', 'vinyl_armsh', 'vinyl_cap', 'vinyl_keys'):
        expect(open(asset_path(n), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read(), f'{n} (Graphite) keeps its name')
    for th in A.THEME_NAMES:
        b = asset_image(A.tname('vinyl_base', th))
        expect(all(b.getpixel(p)[3] == 255 for p in ((0, 0), (319, 479), (96, 196))) and asset_image(A.tname('vinyl_keys', th)).getpixel((0, 0))[3] == 255, f'{th}: the base and the key cells are opaque')
    base = asset_image('vinyl_base')
    expect(all(base.getpixel(p)[3] == 255 for p in ((0, 0), (319, 479), (96, 196))) and asset_image('vinyl_keys').getpixel((0, 0))[3] == 255 and asset_image('vinyl_label').getpixel((0, 0))[3] == 255,
           'the base, the key cells and the fallback label are opaque')
    rgb = set(base.convert('RGB').getdata())
    expect(all(max(c) - min(c) <= 12 for c in rgb) and all(max(c) - min(c) <= 12 for c in asset_image('vinyl_base_white').convert('RGB').getdata()), 'neutral greys only: no colour in the Graphite and White bases')
    lid = asset_image('vinyl_lid')
    expect(lid.getpixel((80, 80))[3] > 200 and lid.getpixel((5, 5))[3] == 0 and lid.getpixel((80, 40))[3] < 60, 'the lid: the spindle opaque, the corners clear, the label under it mostly shows')
    sh = asset_image('vinyl_armsh')
    expect(set(px[:3] for px in sh.getdata()) == {(0, 0, 0)} and max(px[3] for px in sh.getdata()) <= A.ARM_SHADOW[3], 'the shadow: black, its alpha at most 150')
    rec = asset_image('vinyl_rec'); bx, by_, bx1, by1 = A.REC_BOX; rw = bx1 - bx
    expect(A.REC_BOX == (0, 34, 258, 358) and rec.size == (258, 324), 'vinyl_rec covers the record\'s box (0, 34) .. (258, 358)')
    rd = list(rec.getdata())
    expect(all((px[0] > 0) == A.rec_in_map(bx + i % rw, by_ + i // rw) and px[1:] == (0, 0, 255) for i, px in enumerate(rd)), 'the record map (the red channel) holds exactly the ring outside the label that the rim covers; 0 elsewhere; G, B 0, opaque')
    st = A.tint_stops((200, 100, 60)); tab = A.ramp_table(st)
    expect(all(tab[t] == st[k][1] for k, t in enumerate(A.RECORD_STOPS_T)) and all(tab[t][0] <= tab[t + 1][0] for t in range(255)), 'the ramp table hits its five stops exactly and rises')
    base0 = layers()['vinyl_base']; inner = [base0[y * W + x] & 255 for y in range(34, 358) for x in range(0, 258) if 156 * 4 < (2 * (x - 96) + 1) ** 2 + (2 * (y - 196) + 1) ** 2 < 160 * 4 and x > 3]
    expect(abs(sum(inner) / len(inner) - O['VN_REC_K']) < 3 and O['VN_REC_K'] == A.REC_EDGE_K, f'the black record\'s rim grey is VN_REC_K = {O["VN_REC_K"]} ({sum(inner) / len(inner):.1f} measured)')


def draw_tests(ctx):
    expect = ctx.expect
    g = A.groove_table16()
    # playing, with the album's cover: the label is the cover, the arm on the groove at 200 / 243
    m = opened(cover=True)
    want = model(0, groove_at(200, 243, g), m.cover_words(), playkey=1)
    n, first = ndiff(m.frame_words(), want)
    expect(n == 0, f'playing, first look: the frame is the model pixel for pixel: the base, the cover turned 0, the lid, the arm on the groove, the cap, the pause key ({n} differ {first})')
    f = dict(cover=A.cover('sunset', 168), title='Midnight City', artist='M83', pos=200, len=243, playing=True, fmt='FLAC', batt=60, charging=False, vol=42, clock='21:07')
    md = dump(m, 'j1', f, 0)
    expect(md < 6.0, f'and it is close to the design (tools/vinyl_art.py design, the same state): mean difference {md:.2f} of 255 a channel')
    cov = m.cover_words()
    expect(len(set(cov)) > 100 and all(w >> 24 == 255 for w in cov), f'the cover was decoded into the label (152 px, opaque; {len(set(cov))} colours)')
    expect(m.paint() and m.blits[0][1] == (0, 0, 320, 480) == m.blits[0][2], 'paint blits the whole frame 1:1 (the canvas clips it)')
    # turning: after some ticks the label is at the model's angle and nothing else moved but the label's square
    sp = Spin(g); sp.step(0, True, 200, 243, force=True)
    for _ in range(6):
        m.tick(50); sp.step(50, True, 200, 243)
    n, first = ndiff(m.frame_words(), model(sp.ang, sp.arm, cov, playkey=1))
    expect(n == 0 and sp.ang > 0, f'six ticks on: the label has turned to {sp.ang / 16:.1f} degrees, as the model ({n} differ {first})')
    md = dump(m, 'j1-turned', f, sp.ang)
    # paused, no cover: the fallback label, the arm parked, the play key
    m2 = opened(status=3)
    n, first = ndiff(m2.frame_words(), model(0, O['VN_PARK'], None, playkey=0))
    expect(n == 0, f'paused, no cover: vinyl_label, the arm parked straight down, the play glyph ({n} differ {first})')
    md2 = dump(m2, 'j2', dict(f, playing=False, cover=Image.open(asset_path('vinyl_label')).convert('RGB')), 0)
    expect(md2 < 6.0, f'paused: close to the design with the same label ({md2:.2f})')
    # nothing playing
    m3 = opened(playing=False, status=3)
    expect(m3.text_of('vn_title') == 'Not Playing' and m3.text_of('vn_artist') == '' and m3.text_of('vn_times') == '0:00  -0:00', 'nothing playing: Not Playing, 0:00 -0:00')
    expect(ndiff(m3.frame_words(), model(0, O['VN_PARK'], None))[0] == 0, 'and the arm is parked, the plain label')


def record_tests(ctx):
    """Record colours (docs/modules/vinyl.md "Record colours"): the saved colour read; Black is the installed base, untouched and as cheap as ever."""
    expect = ctx.expect
    base_m = opened(cover=True)
    expect('vinyl_rec' not in base_m.loads, 'Black (nothing saved): vinyl_rec is not even loaded')
    for data, want in ((None, 0), (b'0\n', 0), (b'1', 1), (b'1\n', 1), (b'2\n', 0), (b'3', 0), (b'9', 0), (b'12', 0), (b'1x', 0), (b'1\n\n', 0), (b'', 0), (b'\n', 0), (b'x', 0)):
        m = Machine()
        if data is not None: m.fs[REC_FILE] = data
        expect(m.call(PSYMS['vinyl_record']) == want, f'the saved record {data!r}: {want}')


def cover_record_tests(ctx):
    """The Cover colour: the record tinted from the playing track's cover (vn_tint, the python mirror A.cover_tint_px), a grey cover or none black, recomputed on a track change (and the ring composed again),
    left alone for a track of the same cover."""
    expect = ctx.expect
    g = A.groove_table16()

    def add_cover(m, artist, album, img):
        path = art_file(album_key(artist, album)); m.files[path] = 9000
        m.images['file://' + path] = (168, 168, img.convert('RGBA').tobytes())

    def words_of(m):
        w = m.cover_words(); return [(v & 255, v >> 8 & 255, v >> 16 & 255) for v in w]

    grey = Image.new('RGB', (168, 168), (120, 120, 124))
    m = machine(rec=1); add_cover(m, 'M83', 'Hurry Up', A.cover('sunset', 168)); add_cover(m, 'Grey', 'Mono', grey); add_cover(m, 'Blue', 'Sky', A.cover('blue', 168))
    assert m.open() == 0; m.timers = []; m.calls_all = []; m.first(); m.calls_all += m.calls
    tint = A.cover_tint_px(words_of(m)); stops = A.tint_stops(tint)
    expect(tint is not None and 'vinyl_rec' in m.loads, 'a colourful cover: tinted #%02X%02X%02X' % tint)
    sp = Spin(g); sp.step(0, True, 200, 243, force=True)
    n, first = ndiff(m.frame_words(), model(0, groove_at(200, 243, g), m.cover_words(), playkey=1, rec_base_=rec_base(stops)))
    expect(n == 0, f'Cover: the first frame is the model with the ring tinted from the cover ({n} differ {first})')
    f = dict(cover=A.cover('sunset', 168), title='Midnight City', artist='M83', pos=200, len=243, playing=True, fmt='FLAC', batt=60, charging=False, vol=42, clock='21:07')
    ref = A.tint_style(A.cover_tint(A.cover('sunset', 168).resize((152, 152), Image.BOX)))
    md = dump(m, 'rec-cover', dict(f, rec=ref), 0)
    expect(md < 5.0, f'Cover: close to the mock\'s tint (float): mean difference {md:.2f}; the integer tint is #%02X%02X%02X' % tint)
    # a track change to a grey cover: black again, exactly the installed base
    costs = {}
    m.playing(title='Mono', artist='Grey', album='Mono'); m.count(); m.tick(50); sp.step(50, True, 200, 243); costs['to black'] = m.icount
    cov = m.cover_words()
    expect(A.cover_tint_px(words_of(m)) is None and ndiff(m.frame_words(), model(sp.ang, sp.arm, cov, playkey=1))[0] == 0, 'a grey cover: the record is black again, the frame the plain model (the base restored)')
    m.playing(title='Sky', artist='Blue', album='Sky'); m.count(); m.tick(50); sp.step(50, True, 200, 243); costs['to tint'] = m.icount
    t2 = A.cover_tint_px(words_of(m)); s2 = A.tint_stops(t2)
    expect(t2 is not None and t2 != tint and ndiff(m.frame_words(), model(sp.ang, sp.arm, m.cover_words(), playkey=1, rec_base_=rec_base(s2)))[0] == 0, 'the next cover: the ring tinted #%02X%02X%02X, the frame the model' % t2)
    m.playing(title='Sky 2', artist='Blue', album='Sky'); m.count(); m.tick(50); sp.step(50, True, 200, 243); costs['same tint'] = m.icount
    m.tick(50); sp.step(50, True, 200, 243); m.count(); m.tick(50); sp.step(50, True, 200, 243); costs['plain tick'] = m.icount
    expect(ndiff(m.frame_words(), model(sp.ang, sp.arm, m.cover_words(), playkey=1, rec_base_=rec_base(s2)))[0] == 0, 'a track of the same cover: the same tint, the frame still the model')
    mb = machine(); add_cover(mb, 'M83', 'Hurry Up', A.cover('sunset', 168)); add_cover(mb, 'Blue', 'Sky', A.cover('blue', 168))
    assert mb.open() == 0; mb.timers = []; mb.calls_all = []; mb.first(); mb.playing(title='Sky', artist='Blue', album='Sky'); mb.count(); mb.tick(50); costs['Black record, track change'] = mb.icount
    print('  cover record, a tick that changes track: %s' % costs)
    expect(costs['to tint'] < COVER_MAX and costs['to black'] < COVER_MAX and costs['same tint'] < costs['Black record, track change'] + 500000,
           f'a track change with Cover costs {costs["to tint"]} (tinted) / {costs["to black"]} (black) instructions once (budget {COVER_MAX}), a track of the same tint nothing extra ({costs["same tint"]} against {costs["Black record, track change"]})')
    # no cover at all: black
    m = machine(rec=1); assert m.open() == 0; m.timers = []; m.calls_all = []; m.first()
    expect(ndiff(m.frame_words(), model(0, groove_at(200, 243, g), None, playkey=1))[0] == 0, 'no cover: the label is vinyl_label and the record black')
    for what, img in (('another size', (10, 10, bytes(400))), ('absent', None)):
        m = machine(cover=True, rec=1)
        if img: m.images['vinyl_rec'] = img
        else: del m.images['vinyl_rec']
        assert m.open() == 0; m.timers = []; m.calls_all = []; m.first()
        expect(ndiff(m.frame_words(), model(0, groove_at(200, 243, g), m.cover_words(), playkey=1))[0] == 0, f'vinyl_rec {what}: the page stays Black, untouched')
    # the first look with Cover costs the ring once; Black's costs nothing extra
    ml = machine(cover=True, rec=1); ml.open(); ml.timers = []; ml.count(); ml.first(); cost_cover = ml.icount
    mk = machine(cover=True); mk.open(); mk.timers = []; mk.count(); mk.first(); cost_black = mk.icount
    print('  Cover record: first look %d instructions (Black %d, so %d more)' % (cost_cover, cost_black, cost_cover - cost_black))
    expect(cost_cover - cost_black < COMPOSE_MAX, f'the first look with Cover costs {cost_cover - cost_black} instructions more than Black\'s (budget {COMPOSE_MAX})')
    mt = opened(cover=True, rec=1); mt.count(); mt.tick(50); mt.tick(50); cost_tick = mt.icount
    mb = opened(cover=True); mb.count(); mb.tick(50); mb.tick(50)
    expect(cost_tick == mb.icount, f'a playing tick with Cover costs what Black\'s does ({cost_tick} against {mb.icount})')


def cover_change_tests(ctx):
    """Cover, a track change from one tint to another: the frame (the record's rim included) is the python model of a fresh compose of the new tint on the pristine base, whatever the record held
    before (a bug of V2.1zTUKNAAAD: the rim was blended onto the previous tint's rim). Every plinth theme; A to B, A to B to A, A to grey to B."""
    expect = ctx.expect
    g = A.groove_table16()
    x0, y0, x1, y1 = A.REC_BOX
    rim = sum(1 for i, (mv, _, _, _) in enumerate(asset_image('vinyl_rec').convert('RGBA').getdata())
              if mv and (2 * (x0 + i % (x1 - x0) - O['VN_REC_X']) + 1) ** 2 + (2 * (y0 + i // (x1 - x0) - O['VN_REC_Y']) + 1) ** 2 > (2 * O['VN_REC_R'] - 2) ** 2)
    cap = cdefs.defines(str(Path(__file__).resolve().parents[2] / 'patch' / 'vinyl.c'), ['VN_RIM_MAX'])['VN_RIM_MAX']
    expect(rim <= cap, f'the rim pixels the payload keeps ({rim}) fit its buffer (VN_RIM_MAX {cap})')
    solid = lambda c: Image.new('RGB', (168, 168), c)
    covers = {'sunset': A.cover('sunset', 168), 'blue': A.cover('blue', 168), 'grey': solid((120, 120, 124)), 'green': solid((40, 170, 60)), 'red': solid((200, 40, 50))}
    for theme, tname in enumerate(('graphite', 'white')):
        m = machine(rec=1, theme=theme)
        for k, img in covers.items():
            path = art_file(album_key(k, k)); m.files[path] = 9000
            m.images['file://' + path] = (168, 168, img.convert('RGBA').tobytes())
        m.playing(title='sunset', artist='sunset', album='sunset')
        assert m.open() == 0; m.timers = []; m.calls_all = []; m.first()
        sp = Spin(g); sp.step(0, True, 200, 243, force=True)
        for step, k in enumerate(('blue', 'sunset', 'green', 'red', 'grey', 'blue', 'red', 'sunset')):
            m.playing(title=k, artist=k, album=k)
            if PERF: m.count()
            m.tick(50); sp.step(50, True, 200, 243)
            if PERF and step == 1: expect(m.icount < COVER_MAX, f'a track change from one tint to another costs {m.icount} instructions (budget {COVER_MAX})'); print('  cover record, tint to tint: %d instructions' % m.icount)
            tint = A.cover_tint_px(words_of_cover(m))
            rb = rec_base(A.tint_stops(tint), tname) if tint else None
            n, first = ndiff(m.frame_words(), model(sp.ang, sp.arm, m.cover_words(), playkey=1, rec_base_=rb, theme=tname))
            expect(n == 0, f'{tname} Cover, change {step} to {k} (tint {tint}): the frame is a fresh compose on the pristine base ({n} differ {first})')


def words_of_cover(m):
    return [(v & 255, v >> 8 & 255, v >> 16 & 255) for v in m.cover_words()]


def setting_tests(ctx):
    """Settings > Now Playing > Record (m1plus_npset) and its picker Record (m1plus_vinylrec): the value row shows the colour and opens the picker; a tap on a picker row saves it atomically and moves the
    check; the saved file is what the page opens with (the same pattern as the Cassette Theme, test/pod/tape.py)."""
    expect, P = ctx.expect, pod_pages
    C, T = P.NPSET_PAGE, P.RECORD_PAGE
    names = P.RECORD_VALUES
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    rows_n = PSYMS[f'pod_rows_{P.NPSET_PAGE_INDEX}']
    np_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.NPSET_PAGE_INDEX)
    expect(names == tuple(n.capitalize() for n in A.RECORD_NAMES[:len(names)]) and len(names) == O['VN_RECS'] and P.ACT_VREC in P.VALUE_ACTIONS and P.ACT_RECSET in P.CHECK_ACTIONS and C.rows[1].action == P.ACT_VREC
           and [(r.label, r.action, r.arg) for r in T.rows] == [(n, P.ACT_RECSET, i) for i, n in enumerate(names)] and T.title == 'Record' and T.key == 'm1plus_vinylrec' and P.VALUE_INIT[P.ACT_VREC] == 'Black',
           'the Record row (value row) and its picker: Black and Cover in the saved order (vinyl_art.RECORD_NAMES), titled Record')
    val = 'pod_value1'

    def open_page(data=None, language=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + ['pod_value0', val])}
        if data is not None: m.fs[REC_FILE] = data
        if language: m.set_language(language)
        m.call(PSYMS['on_row'], a0=rows_s + 12 * np_i, count=3000000)
        return m

    def label(m):
        keys = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[val]]
        return keys[-1] if keys else None

    m = open_page()
    expect(label(m) == 'Black' and REC_FILE not in m.fs, 'with nothing saved the record is Black, and reading writes nothing')
    for data, want in ((b'1\n', 'Cover'), (b'1', 'Cover'), (b'0\n', 'Black'), (b'2\n', 'Black'), (b'9\n', 'Black'), (b'', 'Black'), (b'x', 'Black'), (b'11', 'Black'), (b'1\n\n', 'Black'), (b' 1\n', 'Black')):
        expect(label(open_page(data)) == want, f'saved {data!r}: {want}')
    m = open_page(); m.click('pod_row1')
    expect(('window_open', T.key) in m.calls and REC_FILE not in m.fs, 'a tap on Record opens the picker and saves nothing')

    def open_pick(data=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(2)] + [f'pod_check{i}' for i in range(2)])}
        if data is not None: m.fs[REC_FILE] = data
        m.call(PSYMS['on_row'], a0=rows_n + 12 * 1, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    m = open_pick()
    expect(('window_open', T.key) in m.calls and [shown(m, i) for i in range(2)] == [1, 0], 'the picker opens with the check on Black')
    expect([[shown(open_pick(d), i) for i in range(2)] for d in (b'1\n', b'4\n', b'9')] == [[0, 1], [1, 0], [1, 0]], 'a saved Cover has the check; an invalid file is Black')
    m = open_pick()
    for k in (1, 0, 1, 1, 0):
        m.click(f'pod_row{k}')
        expect(m.fs.get(REC_FILE) == b'%d\n' % k and REC_FILE + '.tmp' not in m.fs and ('rename', REC_FILE + '.tmp', REC_FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
               and [shown(m, i) for i in range(2)] == [int(i == k) for i in range(2)], f'a tap on {T.rows[k].label}: written atomically ({m.fs.get(REC_FILE)!r}), the check follows')
    m = open_pick(b'1\n'); m.fail.add(('write', REC_FILE + '.tmp')); m.click('pod_row0')
    expect(m.fs.get(REC_FILE) == b'1\n' and REC_FILE + '.tmp' not in m.fs and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed write changes neither the file nor the check')
    m = open_pick(b'1\n'); m.fail.add(('rename', REC_FILE)); m.click('pod_row0')
    expect(m.fs.get(REC_FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed rename changes neither')
    for loc in pod_i18n.ALL_TABLES:
        for data, key in ((None, 'Black'), (b'1\n', 'Cover')):
            expect(label(open_page(data, loc)) == key, f'{loc}: the value is set by key ({key})')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_npset.bin'), 'rb').read())
    row, lab = tree.find('pod_row1'), tree.find('pod_value1')
    expect(row is not None and lab is not None and (lab.get('tr_text') or lab.get('text')) == 'Black' and row.find('pod_icon') is not None and tree.find('pod_sec1_t').get('tr_text') == 'Vinyl Mode',
           'the page asset: a Vinyl Mode header, the Record row with the turntable glyph and its value label')


def theme_tests(ctx):
    """Plinth themes (docs/modules/vinyl.md "Themes"): the saved theme read; each theme's page asset, text colours and pictures; the frame the model's under every theme, with and without the Cover record."""
    expect = ctx.expect
    g = A.groove_table16()
    for data, want in ((None, 0), (b'0\n', 0), (b'1', 1), (b'1\n', 1), (b'2', 0), (b'2\n', 0), (b'3\n', 0), (b'9', 0), (b'12', 0), (b'1x', 0), (b'1\n\n', 0), (b'', 0), (b'x', 0)):
        m = Machine()
        if data is not None: m.fs[THEME_FILE] = data
        expect(m.call(PSYMS['vinyl_theme']) == want, f'the saved theme {data!r}: {want}')
    expect(O['VN_THEMES'] == len(A.THEME_NAMES) == 2 and A.THEME_NAMES == ('graphite', 'white'), 'two themes, Graphite first (the default)')
    for k, th in enumerate(A.THEME_NAMES):
        page = (pod_pages.VINYL, pod_pages.VINYL_WHITE)[k]
        key = page.key
        tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/%s.bin' % key), 'rb').read())
        by = {w.name: w for w in tree.walk() if w.name}
        cols = [by[n].get('style:normal:text_color') for n in ('vn_title', 'vn_title2', 'vn_artist', 'vn_times', 'vn_status')]
        want = ['#%02X%02X%02X' % A.text_rgb(f, th) for f in ('title', 'title', 'artist', 'times', 'status')]
        expect(cols == want and tree.get('fullscreen') == 'true', f'{th}: the page asset {key} has the theme\'s text colours {want}')
        m = machine(cover=True, theme=k); assert m.open() == 0; opened_calls = list(m.calls); m.timers = []; m.calls_all = []; m.first(); m.calls_all += m.calls
        expect(('window_open', key) in opened_calls, f'{th}: the page opens its asset {key}')
        loaded = [u for u in m.loads if u.startswith('vinyl_') and u != 'vinyl_label']
        own = [A.tname(n, th) for n in A.THEMED] + ([A.tname('vinyl_grain', th)] if A.theme_grain(th) else [])
        expect(sorted(loaded) == sorted(own) and not any(u.endswith(x) for u in loaded for x in {'_white'} - ({'_' + th} if th != 'graphite' else set())), f'{th}: it loads its own pictures (the grain\'s weight with grain) and no other theme\'s ({sorted(loaded)})')
        n, first = ndiff(m.frame_words(), model(0, groove_at(200, 243, g), m.cover_words(), playkey=1, theme=th))
        expect(n == 0, f'{th}: the frame is the model pixel for pixel ({n} differ {first})')
        f = dict(cover=A.cover('sunset', 168), title='Midnight City', artist='M83', pos=200, len=243, playing=True, fmt='FLAC', batt=60, charging=False, vol=42, clock='21:07')
        md = dump(m, 'theme-' + th, f, 0, th)
        expect(md < 6.0, f'{th}: close to the design ({md:.2f} of 255 a channel)')
        sp = Spin(g); sp.step(0, True, 200, 243, force=True)
        for _ in range(6): m.tick(50); sp.step(50, True, 200, 243)
        expect(ndiff(m.frame_words(), model(sp.ang, sp.arm, m.cover_words(), playkey=1, theme=th))[0] == 0, f'{th}: six ticks on, the turned frame is the model')
        mc = machine(cover=True, rec=1, theme=k); assert mc.open() == 0; mc.timers = []; mc.calls_all = []; mc.first(); mc.calls_all += mc.calls
        words_ = mc.cover_words(); tint = A.cover_tint_px([(v & 255, v >> 8 & 255, v >> 16 & 255) for v in words_])
        n, first = ndiff(mc.frame_words(), model(0, groove_at(200, 243, g), words_, playkey=1, rec_base_=rec_base(A.tint_stops(tint), th), theme=th))
        expect(n == 0, f'{th} with the Cover record: the frame is the model, the rim blended into this plinth ({n} differ {first})')
        md = dump(mc, 'theme-%s-cover' % th, dict(f, rec=A.tint_style(A.cover_tint(A.cover('sunset', 168).resize((152, 152), Image.BOX)))), 0, th)
        expect(md < 6.0, f'{th} with the Cover record: close to the design ({md:.2f})')
        # the cost is the theme's own picture sizes, nothing in the tick
        mt = opened(cover=True, theme=k); mt.count(); mt.tick(50); mt.tick(50)
        mg = opened(cover=True); mg.count(); mg.tick(50); mg.tick(50)
        expect(mt.icount == mg.icount, f'{th}: a playing tick costs what Graphite\'s does ({mt.icount})')


def theme_setting_tests(ctx):
    """Settings > Now Playing > Vinyl Mode > Base (m1plus_npset, the picker m1plus_vinyltheme): the same pattern as the Record row."""
    expect, P = ctx.expect, pod_pages
    C, T = P.NPSET_PAGE, P.VTHEME_PAGE
    names = P.VTHEME_VALUES
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    rows_n = PSYMS[f'pod_rows_{P.NPSET_PAGE_INDEX}']
    np_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.NPSET_PAGE_INDEX)
    expect(names == ('Graphite', 'Snow') and len(names) == len(A.THEME_NAMES) and C.rows[2].action == P.ACT_VTHEME and C.rows[2].label == 'Base' and P.ACT_VTHEME in P.VALUE_ACTIONS and P.ACT_VTHSET in P.CHECK_ACTIONS
           and [(r.label, r.action, r.arg) for r in T.rows] == [(n, P.ACT_VTHSET, i) for i, n in enumerate(names)] and T.title == 'Base' and T.key == 'm1plus_vinyltheme' and P.VALUE_INIT[P.ACT_VTHEME] == 'Graphite',
           'the Base row (value row) and its picker: Graphite, Snow (the theme white) in the saved order (vinyl_art.THEME_NAMES)')
    val = 'pod_value2'

    def open_page(data=None, language=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + ['pod_value0', 'pod_value1', val])}
        if data is not None: m.fs[THEME_FILE] = data
        if language: m.set_language(language)
        m.call(PSYMS['on_row'], a0=rows_s + 12 * np_i, count=3000000)
        return m

    def label(m):
        keys = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[val]]
        return keys[-1] if keys else None

    expect(label(open_page()) == 'Graphite' and THEME_FILE not in open_page().fs, 'with nothing saved the base is Graphite, and reading writes nothing')
    for data, want in ((b'1\n', 'Snow'), (b'1', 'Snow'), (b'2\n', 'Graphite'), (b'2', 'Graphite'), (b'0\n', 'Graphite'), (b'3\n', 'Graphite'), (b'', 'Graphite'), (b'x', 'Graphite'), (b'11', 'Graphite'), (b' 1\n', 'Graphite')):
        expect(label(open_page(data)) == want, f'saved {data!r}: {want}')
    m = open_page(); m.click('pod_row2')
    expect(('window_open', T.key) in m.calls and THEME_FILE not in m.fs, 'a tap on Base opens the picker and saves nothing')

    def open_pick(data=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(2)] + [f'pod_check{i}' for i in range(2)])}
        if data is not None: m.fs[THEME_FILE] = data
        m.call(PSYMS['on_row'], a0=rows_n + 12 * 2, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    expect([[shown(open_pick(d), i) for i in range(2)] for d in (None, b'1\n', b'2\n', b'9')] == [[1, 0], [0, 1], [1, 0], [1, 0]], 'the picker opens with the check on the saved theme; an invalid file is Graphite')
    m = open_pick()
    for k in (1, 0, 1):
        m.click(f'pod_row{k}')
        expect(m.fs.get(THEME_FILE) == b'%d\n' % k and THEME_FILE + '.tmp' not in m.fs and ('rename', THEME_FILE + '.tmp', THEME_FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
               and [shown(m, i) for i in range(2)] == [int(i == k) for i in range(2)], f'a tap on {T.rows[k].label}: written atomically ({m.fs.get(THEME_FILE)!r}), the check follows')
    m = open_pick(b'1\n'); m.fail.add(('write', THEME_FILE + '.tmp')); m.click('pod_row0')
    expect(m.fs.get(THEME_FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed write changes neither the file nor the check')
    for loc in pod_i18n.ALL_TABLES:
        for data, key in ((None, 'Graphite'), (b'1\n', 'Snow')):
            expect(label(open_page(data, loc)) == key, f'{loc}: the value is set by key ({key})')


def motion_tests(ctx):
    expect = ctx.expect
    g = A.groove_table16()
    m = opened(pos=10, length=300)
    sp = Spin(g); sp.step(0, True, 10, 300, force=True)
    angs = []
    for i in range(20):
        m.tick(50); sp.step(50, True, 10, 300); angs.append(sp.ang)
    expect(sp.spin == 256 and angs[-1] - angs[-2] == 160, f'up to speed in {O["VN_SPINUP_MS"]} ms: 10 degrees a 50 ms tick, 200 a second (33 1/3 rpm) ({angs[:6]})')
    expect(all(b > a for a, b in zip(angs, angs[1:])) and angs[1] - angs[0] < 160, 'the label speeds up, then turns steadily, clockwise')
    expect(m.rects == [(19, 119, 155, 155)], f'a tick that only turns the label invalidates its square alone ({m.rects})')
    expect(ndiff(m.frame_words(), model(sp.ang, sp.arm, None, playkey=1))[0] == 0, 'the frame after 20 ticks is the model')
    # the arm follows the position: a quarter degree moves it, less does not
    m.pt = (150, 300); m.tick(50); sp.step(50, True, 150, 300)
    expect(sp.arm == groove_at(150, 300, g) or abs(sp.arm - groove_at(150, 300, g)) < abs(groove_at(10, 300, g) - groove_at(150, 300, g)), 'half the track on: the arm moves inward')
    m.tick(50); sp.step(50, True, 150, 300)
    for _ in range(10): m.tick(50); sp.step(50, True, 150, 300)
    expect(sp.arm == groove_at(150, 300, g) and ndiff(m.frame_words(), model(sp.ang, sp.arm, None, playkey=1))[0] == 0, 'the arm swings to the new groove and the frame is the model')
    m.count(); m.tick(50); sp.step(50, True, 150, 300); cost_play = m.icount   # a playing tick: the label turns
    # pause: the label slows to a stop, the arm swings to its park, then the timer idles
    m.status = 3; m.count()
    seq, cost = [], []
    for _ in range(80):
        m.tick(50); sp.step(50, False, 150, 300); seq.append((sp.spin, sp.arm)); cost.append(m.icount)
    swing = [c for c, s, p in zip(cost, seq, [(256, None)] + seq) if s[1] != p[1]]
    playing_tick = cost_play   # the ticks that moved the arm
    expect(len(swing) > 5 and max(swing) < 4500000 and playing_tick < 2300000, f'cost: a tick that swings the arm under 4.5 M instructions (36 M in the first build, 6 M while it shared ticks with the label: {max(swing)}), a playing tick under 2.3 M (3.2 M: {playing_tick})')
    stop = next(i for i, s in enumerate(seq) if s[0] == 0)
    expect(30 < stop < 41, f'paused: the label slows to a stop in {stop * 50} ms (VN_SPINDOWN_MS {O["VN_SPINDOWN_MS"]})')
    expect(all(s[1] == seq[0][1] != O['VN_PARK'] for s in seq[:stop]), 'while it turns the arm stays on the groove')
    expect(seq[-1] == (0, O['VN_PARK']) and all(b[1] <= a[1] for a, b in zip(seq, seq[1:])) and seq[stop + 8][1] < seq[0][1], f'then it swings out to its park ({[s[1] for s in seq[stop - 1:stop + 6]]})')
    expect(ndiff(m.frame_words(), model(sp.ang, sp.arm, None, playkey=0))[0] == 0, 'the paused frame is the model: the arm parked, the play glyph')
    m.tick(500); m.tick(500)
    expect(not m.rects, 'paused and still: nothing is drawn or invalidated')
    # paused with the arm parked, a new track plays (next from pause): the arm swings in eased, no first-tick jump, in VN_SWING_MS + 1 ms a 1/16 degree
    m = opened(status=3, pos=0, length=300)
    m.tick(500); m.tick(500)
    m.status = 2
    sp = Spin(g); sp.step(0, False, 0, 300, force=True)
    goal, turns, same = groove_at(0, 300, g), [sp.arm], True
    for i in range(40):
        m.tick(50); sp.step(50, True, 0, 300); turns.append(sp.arm)
        if i in (0, 2, 6, 39): same = same and ndiff(m.frame_words(), model(sp.ang, sp.arm, None, playkey=1))[0] == 0
    steps = [b - a for a, b in zip(turns, turns[1:])]
    dist, n = goal - O['VN_PARK'], next(i for i, t in enumerate(turns) if t == goal)
    expect(same and turns[0] == O['VN_PARK'] and turns[-1] == goal, 'next from pause: the arm swings from its park onto the groove, the frames the model\'s on the way')
    expect(abs(steps[0]) < abs(dist) // 20 and max(map(abs, steps)) > 3 * abs(steps[0]) + 1, f'it starts slowly (first tick {steps[0]} of {dist}) and speeds up (largest {max(map(abs, steps))})')
    expect(abs(n * 50 - (O['VN_SWING_MS'] + abs(dist))) <= 50 and all(s * dist >= 0 for s in steps), f'and lands in {n * 50} ms (VN_SWING_MS + {abs(dist)}), never turning back')
    # a stall mid-swing holds it: the tick after moves it as VN_DT_MAX would
    sp = Spin(g); sp.step(0, False, 0, 300, force=True)
    for _ in range(3): sp.step(50, True, 0, 300)
    before = sp.arm; sp.step(O['VN_DT_MAX'], True, 0, 300)
    expect(abs(sp.arm - before) < abs(dist) // 3, f'a stall mid-swing moves the arm only as {O["VN_DT_MAX"]} ms would ({sp.arm - before} of {dist})')
    # a stalled loop (stock's pause blocks 150 ms): one tick of 2 s turns and swings as VN_DT_MAX would
    a, b = opened(pos=10, length=300), opened(pos=10, length=300)
    a.tick(2000); b.tick(O['VN_DT_MAX'])
    expect(O['VN_DT_MAX'] == 100 and a.frame_words() == b.frame_words(), f'a tick after a 2 s stall moves things as {O["VN_DT_MAX"]} ms would')


def text_tests(ctx):
    expect = ctx.expect
    m = opened(title='So What', artist='Miles Davis', pos=14, length=562)
    expect(m.text_of('vn_title') == m.text_of('vn_title2') == 'So What' and m.text_of('vn_artist') == 'Miles Davis' and m.text_of('vn_times') == '0:14  -9:08', 'the title and its twin, the artist, the times')
    import time as _t
    tm = _t.gmtime(m.wall + m.tz); clock = f'{tm.tm_hour:02d}:{tm.tm_min:02d}'
    expect(m.text_of('vn_status') == A.status_text(42, 'FLAC', clock) == f'VOL 42 | FLAC | {clock}', f'the status line, no battery ({m.text_of("vn_status")})')
    m.pt = (15, 562); m.volume = '55'; m.battery_img = 'bar_charge'; m.props[(m.widgets['pgbar_battery'], 'value')] = 40
    m.tick(500); m.calls_all = m.calls
    expect(m.text_of('vn_times') == '0:15  -9:07' and m.text_of('vn_status') == f'VOL 55 | FLAC | {clock}' and m.text_of('vn_title') is None, 'a second on: the times and the status line (a battery change shows nothing), the title not set again')
    expect(not any(c[0] in ('widget_set_prop_int', 'widget_set_value') for c in m.calls), 'the status bar is only read')
    m.tick(500); m.calls_all = m.calls
    expect(all(m.text_of(n) is None for n in LABELS), 'nothing changed: no label is set')
    m.setword(SYSBAR, 0); m.tick(500); m.calls_all = m.calls
    expect(m.text_of('vn_status') == f'VOL 0 | FLAC | {clock}', 'no status bar: VOL 0')
    m.play([m.record(title='', name='track 07.mp3', path='/mnt/mmc/x/track 07.mp3', artist='')], 0); m.tick(500); m.calls_all = m.calls
    expect(m.text_of('vn_title') == 'track 07.mp3' and m.text_of('vn_artist') == '', 'a track without a title: its file name')
    # the widest status line fits its label at 10 px with the shipped font
    from stb_raster import StbFont
    font = StbFont(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    wide = A.status_text(100, 'WAVE', '23:59')
    expect(font.width(wide, A.TEXT['status']['px']) <= A.TEXT['status']['w'], f'"{wide}" fits the {A.TEXT["status"]["w"]} px status label')
    expect(A.TEXT['status']['x'] >= A.CLOSE_RECT[2] - 20 and A.TEXT['status']['x'] + A.TEXT['status']['w'] <= A.PLATE[0], 'the status line lies between the chevron and the arm\'s plate')
    # the cover changes with the track
    m = opened(cover=True, status=3)
    expect(ndiff(m.frame_words(), model(0, O['VN_PARK'], m.cover_words()))[0] == 0, 'paused with the album\'s cover: the cover is the label')
    m.play([m.record(title='T', album='Other', artist='Someone')], 0); m.tick(500)
    expect(ndiff(m.frame_words(), model(0, O['VN_PARK'], None))[0] == 0, 'a track of an album without a cover: vinyl_label, at once')
    m.play([m.record(title='T2', album='Hurry Up', artist='M83')], 0); m.tick(500)
    expect(ndiff(m.frame_words(), model(0, O['VN_PARK'], m.cover_words()))[0] == 0, 'back to the album with a cover: the cover again')


def touch_tests(ctx):
    expect = ctx.expect
    m = opened(status=3)
    names = lambda c: [x[0] for x in c]
    # the close chevron
    calls = m.gesture((16, 12), (18, 14))
    expect('navigator_back' in names(calls) and not m.cmds, 'a tap on the chevron closes the page')
    m.cmds = []; calls = m.gesture((16, 12), (160, 300))
    expect('navigator_back' not in names(calls) and not m.cmds, 'began on the chevron, lifted elsewhere: nothing')
    # the keys: pressed while held, the stock functions on release
    m.ptr('down', 246, 449, 3000)
    expect(ndiff(m.frame_words(), model(0, O['VN_PARK'], None, playkey=0, pressed=K_PLAY))[0] == 0 and m.rects == [(223, 420, 46, 58)], f'the play key held: drawn pressed, only its cell invalidated ({m.rects})')
    m.cmds = []; m.ptr('up', 248, 452, 3080)
    expect(m.cmds == [('playpause',)] and m.status == 2, 'released on it: play / pause (stock playpause_quick_click)')
    m.status = 3; m.tick(500); m.tick(500)
    for _ in range(30): m.tick(50)
    for k, pt, cmd in ((K_PREV, (200, 449), 'prev'), (K_NEXT, (292, 449), 'next')):
        m.cmds = []
        m.ptr('down', *pt, 5000)
        held = m.frame_words()
        m.ptr('up', pt[0] + 2, pt[1], 5060)
        expect(m.cmds == [(cmd, 5000 + 60, 0)], f'{cmd}: released on the key, {cmd}_quick_click(e, 0) with the click\'s own event (its time {m.cmds})')
        expect(held != m.frame_words(), f'{cmd}: drawn pressed while held and back on release')
    m.cmds = []; calls = m.gesture((200, 449), (292, 449))
    expect(not m.cmds, 'a drag from one key to another does nothing')
    # the record: a tap plays / pauses, a drag does nothing
    m.cmds = []; m.gesture((96, 196), (99, 194))
    expect(m.cmds == [('playpause',)], 'a tap on the record plays / pauses')
    m.cmds = []; m.gesture((96, 196), (160, 196))
    expect(not m.cmds, 'a drag across the record does nothing')
    m.cmds = []; m.gesture((300, 300), (301, 300))
    expect(not m.cmds, 'a tap beside the record does nothing')
    m.cmds = []; m.ptr('down', 246, 449, 9000); m.ptr('abort', 246, 449, 9010); m.ptr('up', 246, 449, 9020)
    expect(not m.cmds, 'an abort lets the key go; the up after it does nothing')
    # never grabs, binds no move, passes every event on
    expect((m.view, EVT_MOVE) not in m.bound and 'widget_grab' not in names(m.calls), 'no move handler, no grab')
    rets = [m.ptr(k, 150, y, 10000 + y) for k, y in (('down', 40), ('move', 80), ('move', 160), ('up', 160), ('abort', 160))]
    expect(set(rets) == {0}, f'a drag from the top edge (the pull-down) is passed on: every call returns RET_OK ({rets})')
    m2 = machine(); e = m2.alloc(0x30); m2.u.mem_write(e, bytes(0x30)); m2.setword(e, EVT_DOWN)
    m2.call(PSYMS['vn_on_touch'], a0=0, a1=e, count=100000)
    expect(not m2.cmds and 'navigator_back' not in m2.names(), 'no page: a touch handler left behind does nothing')


def idle_touch_tests(ctx):
    """A page opened by Now Playing's timer (vinyl_open_idle): a tap on the record closes it (docs/modules/vinyl.md "Touch"); the keys and chevron are unchanged; a More-opened page is unchanged."""
    expect = ctx.expect
    nm = lambda c: [x[0] for x in c]

    def auto():
        m = machine(status=3); assert m.open_idle() == 0
        m.timers = []; m.first()
        return m
    m = auto()
    m.cmds = []; calls = m.gesture((96, 196), (99, 194))
    expect(m.cmds == [] and nm(calls).count('navigator_back') == 1, 'auto-opened: a tap on the record closes the page, plays / pauses nothing')
    m = auto()
    calls = m.gesture((16, 12), (18, 14))
    expect('navigator_back' in nm(calls) and not m.cmds, 'auto-opened: the chevron still closes')
    m.ptr('down', 246, 449, 3000)
    expect(ndiff(m.frame_words(), model(0, O['VN_PARK'], None, playkey=0, pressed=K_PLAY))[0] == 0, 'auto-opened: the play key still shows pressed')
    m.cmds = []; m.ptr('up', 248, 452, 3080)
    expect(m.cmds == [('playpause',)] and 'navigator_back' not in nm(m.calls), 'auto-opened: the play key still plays / pauses')
    for pt, cmd in (((200, 449), 'prev'), ((292, 449), 'next')):
        m.cmds = []; m.ptr('down', *pt, 5000); m.ptr('up', pt[0] + 2, pt[1], 5060)
        expect(m.cmds == [(cmd, 5060, 0)] and 'navigator_back' not in nm(m.calls), f'auto-opened: {cmd} still works')
    m.cmds = []; calls = m.gesture((96, 196), (160, 196))
    expect(not m.cmds and 'navigator_back' not in nm(calls), 'auto-opened: a drag across the record does nothing')
    m.cmds = []; calls = m.gesture((300, 300), (301, 300))
    expect(not m.cmds and 'navigator_back' not in nm(calls), 'auto-opened: a tap beside the record does nothing')
    # the timer on a page that is already up changes nothing
    m = opened(status=3)
    expect(m.open_idle() == 0, 'the timer on a More-opened page: 0, left alone')
    m.cmds = []; calls = m.gesture((96, 196), (99, 194))
    expect(m.cmds == [('playpause',)] and 'navigator_back' not in nm(calls), 'and its record tap still plays / pauses')
    m = auto()
    expect(m.open() == 0, 'More on an auto-opened page: 0, left alone')
    m.cmds = []; calls = m.gesture((96, 196), (99, 194))
    expect(m.cmds == [] and 'navigator_back' in nm(calls), 'and its record tap still closes')
    # destroyed: the flag goes with the page
    fn, cx = m.bound[(WIN, EVT_DESTROY)]; m.call(fn, a0=cx, a1=0, count=3000000)
    m.windows = {}; m.bound = {}
    assert m.open() == 0; m.timers = []; m.first()
    m.cmds = []; calls = m.gesture((96, 196), (99, 194))
    expect(m.cmds == [('playpause',)] and 'navigator_back' not in nm(calls), 'after the auto-opened page was destroyed a More-opened page plays / pauses on the record tap')


def life_tests(ctx):
    expect = ctx.expect
    m = machine(); m.windows['m1plus_vinyl'] = 0
    expect(m.open() == 0xffffffff and 'timer_add' not in m.names() and 'widget_on' not in m.names(), 'a window that will not open: -1, nothing registered')
    for missing in ('vinyl_view',) + LABELS:
        m = machine(); del m.widgets[missing]
        expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and 'timer_add' not in m.names(), f'no {missing}: the window goes again, no timer')
    m = machine(); m.load_image = 1
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and len(m.bitmaps) == 0, 'a picture that will not load: the window goes again, nothing allocated')
    for n in [A.tname(x) for x in A.THEMED] + ['vinyl_label']:   # (vinyl_rec: read only for a coloured record; another theme's pictures only under that theme)
        m = machine(); m.images[n] = (10, 10, bytes(400))
        expect(m.open() == 0xffffffff and len(m.bitmaps) == 0, f'{n} of another size is refused, every bitmap freed')
    m = machine(); m.bitmap_ok = False
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names(), 'no memory: the window goes again')
    m = machine()
    expect(m.open() == 0, 'the page opens')
    on = {(a, e) for _, a, e, f, x in (c for c in m.calls if c[0] == 'widget_on')}
    expect(on == {(m.view, EVT_DOWN), (m.view, EVT_UP), (m.view, EVT_ABORT), (m.view, EVT_PAINT), (WIN, EVT_DESTROY), (WIN, EVT_BG), (WIN, EVT_FG)}, 'the view takes down, up, abort and its paint; the window its three events')
    expect(m.names().count('timer_add') == 1 and ('timer_add', PSYMS['vn_first'], O['VN_FIRST_MS']) in m.calls and len(m.bitmaps) == 9, 'one 50 ms one-shot; nine bitmaps (frame, six layers, the fallback label, the cover)')
    expect(not any(n in m.names() for n in ('widget_set_visible', 'widget_move', 'widget_resize', 'widget_destroy')), 'it moves, hides and destroys nothing in the asset')
    expect(m.open() == 0 and 'window_open' not in m.names(), 'opening again while it is up does nothing')
    m.calls = []; m.call(PSYMS['vn_first'], a0=0, count=400000000)
    expect(('timer_add', PSYMS['vn_tick'], O['VN_PLAY_MS']) in m.calls, 'playing: the tick at 50 ms')
    m.status = 3
    for _ in range(40): m.tick(50)
    m.tick(50)
    expect('timer_add' not in m.names(), 'no second timer')
    m.tick(500)
    expect(m.names().count('timer_modify') == 0 and not m.rects, 'paused and still: 500 ms, nothing drawn')
    seen = []
    m2 = opened(status=3)
    m2.tick(500); seen = [c for c in m2.calls if c[0] == 'timer_modify']
    m2.status = 2; m2.tick(500); seen += [c for c in m2.calls if c[0] == 'timer_modify']
    expect(('timer_modify', 0x777, O['VN_PLAY_MS']) in seen, f'playing again: back to 50 ms in place ({seen})')
    # idle power
    m2.screen(False); m2.tick(50)
    expect(('timer_modify', 0x777, 1000) in m2.calls and not m2.rects and not any(c[0] in ('get_playtimeandlength', 'mclGetPlayStatus', 'widget_set_text_utf8') for c in m2.calls), 'screen off: 1 s, nothing read, drawn or set')
    m2.tick(1000)
    expect('timer_modify' not in m2.names() and not m2.rects, 'dark: the interval is not set again')
    m2.screen(True); m2.tick(1000)
    expect(('timer_modify', 0x777, O['VN_PLAY_MS']) in m2.calls and m2.rects, 'lit again: the interval returns and the tick draws')
    m2.calls = []; m2.fire(EVT_BG, WIN)
    expect(('timer_remove', 0x777) in m2.calls, 'to the background: the timer goes')
    m2.calls = []; m2.call(PSYMS['vn_tick'], a0=0, count=100000)
    expect(not any(c[0] in ('widget_invalidate_force', 'timer_modify') for c in m2.calls), 'a stray tick in the background draws nothing')
    m2.screen(False); m2.calls = []; m2.fire(EVT_FG, WIN); m2.first()
    expect(('timer_add', PSYMS['vn_first'], 1000) in m2.calls and not m2.rects, 'the first look with the screen off waits for the light')
    m2.screen(True)
    fn, cx = m2.bound[(WIN, EVT_DESTROY)]
    m2.calls = []; m2.call(fn, a0=WIN + 8, a1=0)
    expect('bitmap_destroy' not in m2.names(), 'another window\'s destroy leaves the page alone')
    m2.calls = []; m2.call(fn, a0=cx, a1=0)
    expect(m2.names().count('bitmap_destroy') == 9 and len(m2.bitmaps) == 0, 'destroy: the nine bitmaps freed')
    m2.timers = []; m2.calls = []
    expect(m2.open() == 0 and ('window_open', 'm1plus_vinyl') in m2.calls, 'the state is clean: it opens again')
    expect(not any('click' in n.lower() and n not in ('playpause_quick_click', 'next_quick_click', 'prev_quick_click') for n in m2.names()), 'no click sound')


def run(ctx):
    for fn in SECTIONS: fn(ctx)


SECTIONS = [number_tests, asset_tests, draw_tests, record_tests, cover_record_tests, cover_change_tests, setting_tests, theme_tests, theme_setting_tests, motion_tests, text_tests, touch_tests, idle_touch_tests, life_tests]

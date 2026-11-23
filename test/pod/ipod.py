"""The virtual iPod Classic (patch/ipod.c, tools/pod_ui.py build_ipod_page, tools/mod_icons.py ipod_wheel, docs/modules/ipod.md): the menu item, the asset (a fullscreen
320 x 480 window, the screen view and the wheel's touch view, the hit test with demo's own widget_find_target, the wheel picture), the wheel's angle math against math.atan2,
the page's open / destroy / background / foreground, the paint of the main menu, the lists, the title bar and Now Playing, the wheel (one row per 20 degrees, reversal hysteresis, the chord dead zone, tiers on long lists, the hard stop at the ends, the centre
button, the four ring sectors, the taps that are not taps, the touch outside the circle), the navigation (Albums -> an album's tracks -> play, Artists, Songs,
Playlists, the existing Cover Flow page), the main menu's cover pane (q2-pod's pan: the playing album's cover or a random one, one decode and none in paint, a 1:1 copy moving a whole pixel at a time, the timer's fast and slow interval), Shuffle Songs on the page's own
Now Playing, the Settings list (Shuffle, Repeat, Appearance), the stock calls (loadAlbumdetailList, start_player, the quick clicks), a stock list replaced under the page,
and the texts in all 13 languages."""
import math, os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_icons
from awtk_text import Ttf, StbText
from unicorn.mips_const import UC_MIPS_REG_F0

UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_ipod.bin')
EVT_DOWN, EVT_MOVE, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
EVT_BG, EVT_FG, EVT_DESTROY, EVT_PAINT = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG'], O['EVT_DESTROY'], O['EVT_AFTER_PAINT']
WIN = 0x24100000
SHOWLIST, PLAYLIST, CLASSINFO, G_CLASS, SYSBAR = (pod.DATA[k][0] for k in ('PDEQ_SHOWLIST', 'PDEQ_PLAYLIST', 'CLASSINFO', 'G_CLASS_TYPE', 'SYSTEM_BAR'))
FORCE = pod.DATA['FORCE_REFRESH'][0]
WX, WY, WD, RING, HUB = O['IP_WHEEL_X'], O['IP_WHEEL_Y'], O['IP_WHEEL_D'], O['IP_RING_R'], O['IP_HUB_R']
CX, CY = WX + WD // 2, WY + WD // 2        # the wheel's centre in the window
STEP_DEG = O['IP_STEP'] / 16
ROWS, ROWH, BARH = O['IP_ROWS'], O['IP_ROW_H'], O['IP_BAR_H']


def row_y(i, n=ROWS): return BARH + i * (O['IP_SCREEN_H'] - BARH) // n   # patch/ipod.c ip_row_y: n rows share the screen under the bar exactly
def row_of(y, n=ROWS): return max(i for i in range(n) if row_y(i, n) <= y)
def row_h(i, n=ROWS): return row_y(i + 1, n) - row_y(i, n)
SONGS_N = O['IP_SONG_ROWS']
TEXT_YS = {row_y(i) + d for i in range(ROWS) for d in (0, 4)} | {row_y(i, SONGS_N) + 2 for i in range(SONGS_N)}   # plain rows; Music > Songs' titles
STYLES = ('label_ip_row', 'label_ip_sel', 'label_ip_title', 'label_ip_small', 'label_ip_subsel', 'label_ip_np1', 'label_ip_np2', 'label_ip_time', 'label_ip_val', 'label_ip_np3', 'label_ip_shuf', 'label_ip_selb')
MAIN_KEYS = ['Music', 'Cover Flow', 'Podcasts', 'cdrippersettings', 'Shuffle Songs', 'Now Playing']
MUSIC_KEYS = ['Cover Flow', 'Playlists', 'Artists', 'Albums', 'Songs', 'Genres', 'Composers']
TRAPS = ('coverflow_open',)
SET_KEYS = ['Shuffle', 'Repeat', 'Appearance']
PANE = (O['IP_PANE_X'], 0, O['IP_PANE_W'], O['IP_SCREEN_H'])


def ip_lerp(a, b, i, n):
    """patch/ipod.c ip_lerp: the colour a .. b (r | g << 8 | b << 16) at i of n - 1, C's truncating division."""
    def ch(k):
        x, y = a >> k & 255, b >> k & 255; q = (y - x) * i; d = n - 1 if n > 1 else 1
        return x + (abs(q) // d) * (1 if q >= 0 else -1)
    return ch(0) | ch(8) << 8 | ch(16) << 16


class IM(Machine):
    """The machine plus what the page calls that the shared mocks do not know: the player's status and quick clicks, the album track query, the playing time, a string
    property, and the payload's other pages (Cover Flow, Settings, Shuffle: trapped at their entry, the page's own calls are the evidence)."""
    def __init__(self):
        super().__init__()
        self.status, self.cmds, self.pt, self.battery_img = 3, [], None, 'bar_power'
        self.seeks, self.seek_moves = [], True   # seek_time's arguments; whether the player then reads the new position
        self.sets, self.set_ret, self.cue = [], 1, 0   # mclSetSeek's arguments (absolute seconds, CUE start included), its result, the CUE start the mock player subtracts again
        self.album_tracks, self.opened = {}, []
        self.window = WIN
        self.top_main = WIN
        self.load_image = 0
        self.fail_projection = False
        self.canvas = self.alloc(0x80)
        self.styles, self.origins, self.clip_frames = {}, [], []
        self.img_ox = []   # the canvas origin of each canvas_draw_image, parallel to blits
        self.fill_clip = []
        self.setword(self.canvas + O['CANVAS_CLIP'] + 8, 319)
        self.setword(self.canvas + O['CANVAS_CLIP'] + 12, 239)
        for w in STYLES + ('ipod_screen', 'ipod_wheel', 'ipod_wheel_img', 'pgbar_battery', 'img_battery'): Machine.widget(self, w)
        self.setword(SYSBAR, self.alloc(0x80))
        self.props[(self.widgets['pgbar_battery'], 'value')] = 80
        # the wheel as a widget struct (demo's own widget_to_local walks x, y and the parent): window (0, 0) > wheel (WX, WY)
        win, wheel = self.alloc(0x80), self.widgets['ipod_wheel']
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, 0)): self.setword(win + off, v)
        for off, v in ((0, WX), (4, WY), (8, WD), (0xc, WD), (0x44, win)): self.setword(wheel + off, v)
        self.images = {'ipod_placeholder': (24, 24, bytes((0x40, 0x40, 0x40, 255)) * 576)}
        for n in TRAPS: self.handlers[PSYMS[n]] = n
        for n in ('mclGetPlayStatus', 'playpause_quick_click', 'next_quick_click', 'prev_quick_click', 'loadAlbumdetailList', 'get_playtimeandlength', 'seek_time', 'mclSetSeek'):
            self.handlers[pod.FUNCTIONS[n][2]] = n
        self.radio = 0   # a station connects or plays (patch/radio.h rd_running): the hold scan does nothing
        for n in ('VOLP_ADD', 'VOLP_DEC', 'VOLP_STOP'): self.handlers[pod.DATA[n][0]] = n   # stock's volume dialog steps and stop (run for real in test/pod/volume.py): +1 / -1 up to max_volume, logged
        self.setword(pod.DATA['G_VOLUME'][0], 40); self.setword(pod.DATA['MAX_VOLUME'][0], 100); self.setword(pod.DATA['HEADSET_OUTPUT'][0], 0)
        self.vol = []   # ('add' | 'dec' | 'stop', window) in order
        self.handlers[PSYMS['rd_running']] = 'rd_running'
        self.stock_songlist = True
        self.sbtrack, self.sbcover = {}, {}   # server track REC_ID -> track id (sba_rec_track); REC_ID -> (sba_rec_cover's answer, the file's path) (patch/sbapi.c, tested in sbapi.py)
        for n in ('sba_rec_track', 'sba_rec_cover'): self.handlers[PSYMS[n]] = n
        self.wall = 1800000000 + 4 * 3600 + 59 * 60   # 12:59 UTC (1800000000 is 08:00)
        self.strings = {'cdrippersettings': 'Settings', 'local_allsong': 'All Songs'}   # the stock key the Settings row uses (the shipped table says Settings)
        self.present.add('/mnt/mmc/m/1.flac')

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'value_set_uint32':
            self.setword(a0 + 8, a1); ret = a0
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'widget_set_style':
            self.styles[(a0, self.read_cstr(a1))] = self.word(a2 + 8)
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name in ('canvas_fill_rect', 'canvas_draw_image', 'canvas_draw_text_in_rect'):
            self.origins.append(self.word(self.canvas + O['CANVAS_OX']))
            if name == 'canvas_draw_image': self.img_ox.append(self.word(self.canvas + O['CANVAS_OX']))
            if name == 'canvas_fill_rect': self.fill_clip.append((a1, a3, self.word(self.canvas + 16), self.word(self.canvas + 24)))   # x, w, clip x0, clip x1
            self.clip_frames.append(tuple(self.word(self.canvas + o) for o in (O['CANVAS_OX'], 16, 24)))
        if name in ('canvas_measure_text', 'canvas_draw_text_in_rect'):
            chars = list(struct.unpack(f'<{a2}I', u.mem_read(a1, 4 * a2))) if a2 else []
            if name == 'canvas_measure_text':
                w = float(sum(16 if c >= 0x2e80 or c == 0x2026 else 8 for c in chars))
                u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); self.measures.append(a2)
            else:
                self.texts.append((''.join(map(chr, chars)), struct.unpack('<4i', u.mem_read(a3, 16)))); self.text_styles.append(self.cur_style)
                oy = self.word(self.canvas + O['CANVAS_OY']); self.__dict__.setdefault('text_oy', []).append(oy - (1 << 32) if oy >= 1 << 31 else oy)
                ox = self.word(self.canvas + O['CANVAS_OX']); self.__dict__.setdefault('text_ox', []).append(ox - (1 << 32) if ox >= 1 << 31 else ox)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'bitmap_create_ex' and self.fail_projection and (a0, a1) == (O['IP_NP_ART_W'], O['IP_NP_ART_W'] + O['IP_NP_REFLECT']):
            self.calls.append(('bitmap_create_ex', 0)); ret = 0
        elif name in TRAPS: self.calls.append((name,)); self.opened.append(name); ret = 0
        elif name == 'rd_running': ret = self.radio
        elif name == 'sba_rec_track':
            rid = a0 - (1 << 32) if a0 >= 1 << 31 else a0; ret = self.cstr(self.sbtrack.get(rid, ''))
        elif name == 'sba_rec_cover':   # (the record, path, cap): 1 and the path, 0 on its way, -1 none
            rid = self.word(a0 + O['REC_ID']); rid = rid - (1 << 32) if rid >= 1 << 31 else rid
            r, path = self.sbcover.get(rid, (-1, None))
            self.calls.append(('sba_rec_cover', rid))
            if r == 1: self.u.mem_write(a1, path.encode() + b'\0')
            ret = r
        elif name == 'mclGetPlayStatus': ret = self.status
        elif name in ('VOLP_ADD', 'VOLP_DEC', 'VOLP_STOP'):
            self.vol.append((name[5:].lower(), a0))
            v = self.word(pod.DATA['G_VOLUME'][0])
            if name == 'VOLP_ADD' and v < min(100, self.word(pod.DATA['MAX_VOLUME'][0])): self.setword(pod.DATA['G_VOLUME'][0], v + 1)
            if name == 'VOLP_DEC' and v > 0: self.setword(pod.DATA['G_VOLUME'][0], v - 1)
            ret = 0
        elif name == 'playpause_quick_click':
            self.calls.append(('playpause_quick_click',)); self.cmds.append(('playpause',)); self.status = 2 if self.status != 2 else 3; ret = 1
        elif name in ('next_quick_click', 'prev_quick_click'):
            self.calls.append((name, a1)); self.cmds.append((name[:4], self.word(a0 + 8), a1)); ret = 1
        elif name == 'seek_time':   # stock: the player moves there, a paused one resumes
            self.calls.append(('seek_time', a0)); self.seeks.append(a0)
            if self.pt and self.seek_moves: self.pt = (a0, self.pt[1])
            if self.status == 3: self.status = 2
            ret = 1
        elif name == 'mclSetSeek':   # stock: fire and forget, the status does not change; -1 without the player link
            self.calls.append(('mclSetSeek', a0, self.clock))
            if self.set_ret >= 0:
                self.sets.append(a0)
                if self.pt and self.seek_moves: self.pt = (a0 - self.cue, self.pt[1])
            ret = self.set_ret
        elif name == 'get_playtimeandlength':
            if self.pt: self.setword(a0, self.pt[0]); self.setword(a1, self.pt[1])
            ret = 1 if self.pt else 0
        elif name == 'loadAlbumdetailList':
            rec = a1
            album = self.read_cstr(self.word(rec + O['REC_ALBUM']))
            tracks = list(self.album_tracks.get(album, []))
            self.calls.append(('loadAlbumdetailList', a0, album))
            self.setword(SHOWLIST, self.new_deque(tracks))
            self.setword(CLASSINFO, 0xff10 if a0 == O['CLASS_ALBUMS'] else 0xff11)
            ret = len(tracks)
        elif name == 'widget_get_prop_str':
            prop = self.read_cstr(a1)
            ret = self.cstr(self.battery_img) if prop == 'image' else a2
        elif name == 'opendir': ret = 0   # no card: pc_any_episode finds no show (PCIM reads its dict)
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    # ---- the world
    def song(self, title, artist='Artist', album='Album', rid=1, path='/mnt/mmc/m/1.flac', name='1.flac', cd=0):
        r = self.record(album=album, artist=artist, path=path, title=title, name=name, rid=rid)
        self.setword(r + O['REC_DISC'], cd)
        return r

    def open(self):
        self.calls = []
        ret = self.call(PSYMS['ipod_open'], count=3000000)
        return ret & 0xffffffff

    def paint(self, animated=False):
        """One EVT_AFTER_PAINT on the screen view: (texts, fills, blits) of that frame."""
        if not animated and self.call(PSYMS['ip_render_active']):
            self.clock += 421
            self.call(PSYMS['ip_tick'], count=40000000)
        ev = self.paint_event()
        self.texts, self.fills, self.blits, self.text_styles, self.img_ox, self.text_oy, self.text_ox = [], [], [], [], [], [], []
        self.fill_clip = []
        self.call(PSYMS['ip_on_paint'], a0=0, a1=ev, count=8000000)
        return list(self.texts), list(self.fills), list(self.blits)

    def ptr(self, kind, x, y, t=0, count=4000000):
        """A pointer event at window point (x, y) to the wheel's handler."""
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, {'down': EVT_DOWN, 'move': EVT_MOVE, 'up': EVT_UP, 'abort': EVT_ABORT}[kind]); self.setword(e + 8, t); self.setword(e + 0x18, x); self.setword(e + 0x1c, y)
        self.call(PSYMS['ip_on_wheel'], a0=0, a1=e, count=count)

    def polar(self, deg, r):
        """The window point at `deg` clockwise from 12 o'clock and radius r from the wheel's centre."""
        return CX + round(r * math.sin(math.radians(deg))), CY - round(r * math.cos(math.radians(deg)))

    def tap(self, x, y):
        self.ptr('down', x, y, 1000); calls = list(self.calls)
        self.ptr('up', x, y, 1080); self.calls = calls + self.calls

    def turn(self, a0, a1, r=80, step=6, dt=100):
        """A finger turning from angle a0 to a1 (degrees, either direction) at radius r, a sample every `step` degrees; the calls of the whole drag."""
        calls = []
        n = max(1, round(abs(a1 - a0) / step))
        x, y = self.polar(a0, r); self.ptr('down', x, y, 1000); calls += self.calls
        for i in range(1, n + 1):
            x, y = self.polar(a0 + (a1 - a0) * i / n, r); self.ptr('move', x, y, 1000 + dt * i); calls += self.calls
        self.ptr('up', x, y, 2000); self.calls = calls + self.calls

    def sel(self):
        """(level kind, sel, top) of the front level, read from the state struct by the painted frame: the selected row's text."""
        texts, fills, _ = self.paint()
        return texts, fills


def machine(albums=(), artists=(), songs=(), playlists=()):
    m = IM()
    m.class_lists[O['CLASS_ALBUMS']] = [m.record(album=a, artist=ar, path=f'/mnt/mmc/m/{a}.flac', title=a, rid=100 + i) for i, (a, ar) in enumerate(albums)]
    m.class_lists[O['CLASS_ARTISTS']] = [m.record(title=a, artist=a, album=a, path='', rid=200 + i) for i, a in enumerate(artists)]
    m.class_lists[O['CLASS_ALL_SONGS']] = [m.song(t, rid=300 + i, path=f'/mnt/mmc/m/{i}.flac', name=f'{i}.flac') for i, t in enumerate(songs)]
    m.playlists = [m.record(title=n, album='', artist='', path='', rid=400 + i) for i, n in enumerate(playlists)]
    for i, r in enumerate(m.playlists): m.setword(r + O['REC_DISC'], 7 + i)   # a playlist's id
    for a, tracks in {a: [m.song(f'{a} {k}', album=a, rid=500 + k, path=f'/mnt/mmc/m/{a}-{k}.flac', name=f'{a}-{k}.flac') for k in range(3)] for a, _ in albums}.items():
        m.album_tracks[a] = tracks
        for r in tracks: m.present.add(m.read_cstr(m.word(r + O['REC_PATH'])))
    return m


def opened(m, **kw):
    m2 = machine(**kw) if kw else m
    assert m2.open() == 0
    m2.timers = []
    return m2


def texts_of(frame): return [t for t, _ in frame[0]]
def rows_of(texts): return [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if BARH <= r[1] < 240 and ((r[0] in (O['IP_TALL_H'] + 8, O['IP_TEXT_X']) and (r[1] - BARH) % O["IP_TALL_H"] == 4) or (r[0] in (O['IP_TEXT_X'], 10) and r[1] in TEXT_YS))]


def pc_hash(name):   # patch/pcmodel.c pc_hash: FNV-1a over the lower-cased bytes (a show's key)
    return fnv_fold(name) or 1


def pc_rows(texts):   # the episode rows: their text is indented for the dot
    return [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if BARH <= r[1] < 240 and r[0] == O['IP_TEXT_X'] + 16 and r[1] in TEXT_YS]


def music(m):
    m.tap(CX, CY)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def angle_tests(ctx):
    """ip_angle against math.atan2 (clockwise from 12 o'clock, sixteenths of a degree) at every degree and a few radii, ip_turn's wrap."""
    expect = ctx.expect
    m = IM()
    worst, bad = 0, []
    for r in (5, 18, 45, 80, 110):
        for d in range(0, 360):
            dx, dy = round(r * math.sin(math.radians(d))), -round(r * math.cos(math.radians(d)))
            if not dx and not dy: continue
            want = (math.degrees(math.atan2(dx, -dy)) % 360) * 16
            got = m.call(PSYMS['ip_angle'], a0=dx, a1=dy)
            err = abs((got - want + 2880) % 5760 - 2880)
            worst = max(worst, err / 16)
            if err > 24: bad.append((dx, dy, got / 16, want / 16))   # 1.5 degrees: the point's own rounding to whole pixels at r = 5
    expect(not bad, f'ip_angle follows atan2 at 1,800 points ({bad[:3]})')
    big = [(r, d) for r in (80, 110) for d in range(0, 360)]
    errs = [abs((m.call(PSYMS['ip_angle'], a0=round(r * math.sin(math.radians(d)) * 100), a1=-round(r * math.cos(math.radians(d)) * 100)) - d * 16 + 2880) % 5760 - 2880) for r, d in big]
    expect(max(errs) <= 6, f'on large coordinates (no pixel rounding) the error is under 0.4 degree ({max(errs) / 16:.3f})')
    expect([m.call(PSYMS['ip_angle'], a0=x, a1=y) for x, y in ((0, -10), (10, 0), (0, 10), (-10, 0), (0, 0))] == [0, 1440, 2880, 4320, 0],
           'the four axes are 0, 90, 180 and 270 degrees, the centre is 0')
    turn = lambda a, b: struct.unpack('<i', struct.pack('<I', m.call(PSYMS['ip_turn'], a0=a, a1=b)))[0]
    expect((turn(100, 200), turn(200, 100), turn(5700, 60), turn(60, 5700), turn(0, 2879), turn(0, 2881)) == (100, -100, 120, -120, 2879, -2879),
           'ip_turn takes the shorter way round, across 12 o\'clock too')
    expect(O['IP_STEP'] == 320 and STEP_DEG == 20.0, 'one wheel step is 20 degrees, 18 to a turn')


def asset_tests(ctx):
    expect = ctx.expect
    path = os.path.join(WORK, UI)
    tree = awtk_ui.parse(open(path, 'rb').read())
    expect(tree.name == 'm1plus_ipod_page' and tree.get('fullscreen') == 'true' and (tree.w, tree.h) == (0, 0),
           'the window is fullscreen (the lock screen\'s property: 480 px, the status bar not drawn)')
    expect(all(tree.get(f'style:{st}:bg_color') == '#C6C9CE' for st in ('normal', 'disable', 'focused')), 'its colour is the wheel body\'s')
    by = {w.name: w for w in tree.walk() if w.name}
    scr, wh, img = by['ipod_screen'], by['ipod_wheel'], by['ipod_wheel_img']
    expect((scr.x, scr.y, scr.w, scr.h) == (0, 0, 320, 240) == (0, 0, O['IP_W'], O['IP_SCREEN_H']) and scr.get('sensitive') == 'false',
           'the iPod screen: 320 x 240 on top (the 4:3 of the real one), insensitive (the payload paints it)')
    expect((wh.x, wh.y, wh.w, wh.h) == (50, 250, 220, 220) == (WX, WY, WD, WD) and wh.get('sensitive') != 'false' and wh.get('visible') != 'false',
           'the wheel\'s touch view: 220 x 220 at (50, 250), below the screen, inside the window (480)')
    expect((img.x, img.y, img.w, img.h) == (0, 0, 220, 220) and img.get('sensitive') == 'false' and img.get('image') == 'ipod_wheel' and img.get('draw_type') == 'default',
           'its picture is an insensitive image child (decorative overlays never take a touch)')
    expect(ROWS == 9 and BARH == 20 and row_y(ROWS) == O['IP_SCREEN_H'] and [row_h(i) for i in range(ROWS)] == [24, 24, 25, 24, 25, 24, 25, 24, 25] and all(row_y(i, O['IP_TALL_ROWS']) == BARH + i * O['IP_TALL_H'] for i in range(O['IP_TALL_ROWS'])) and BARH + O['IP_TALL_ROWS'] * O['IP_TALL_H'] == O['IP_SCREEN_H'],
           'a 20 px title bar, then nine text rows (24 / 25 px, the last one ending exactly at 240) or four cover rows share the rest of the 240 px screen')
    expect(WY + WD <= 480 and WX + WD <= 320 and WY >= 240, 'the wheel is inside the lower 240 px')
    expect(mod_icons.IPOD_WHEEL_D == WD and mod_icons.IPOD_HUB_R == HUB == 45 and RING == WD // 2, 'the wheel picture\'s numbers are offsets.inc\'s: a 220 px ring, a 90 px centre button')
    head = open(os.path.join(mod_icons.PNG, 'ipod_podcasts.png'), 'rb').read(26)   # IHDR: width, height, bit depth, colour type (2 = RGB: no alpha channel)
    expect('ipod_podcasts' in mod_icons.IPOD and struct.unpack('>II', head[16:24]) == (O['IP_PANE_W'], O['IP_PANE_H']) and head[24:26] == bytes((8, 2)),
           'the Podcasts pane picture is the pane\'s 160 x 240, opaque RGB')
    # the style labels: hidden, insensitive, in the colour of what they sit on, the sizes of the mock
    want = {'label_ip_row': (18, '#000000'), 'label_ip_sel': (18, '#FFFFFF'), 'label_ip_title': (16, '#000000'),
            'label_ip_small': (16, '#666666'), 'label_ip_subsel': (16, '#FFFFFF'), 'label_ip_np1': (18, '#000000'), 'label_ip_np2': (16, '#3C3C3C'), 'label_ip_time': (16, '#000000'),
            'label_ip_val': (16, '#0C62D2'), 'label_ip_np3': (14, '#3C3C3C'), 'label_ip_shuf': (14, '#0C62D2')}
    expect(all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' and by[n].get('style:normal:font_size') == str(px)
               and by[n].get('style:normal:text_color') == col for n, (px, col) in want.items()), 'hidden, insensitive style labels: the sizes (rows 18, title 16, subtitles and values 16, Now Playing 20 / 17 / 15, times 16) and colours')
    expect({n: by[n].get('style:normal:text_align_h') for n in ('label_ip_title', 'label_ip_time', 'label_ip_row')} == {'label_ip_title': 'left', 'label_ip_time': 'right', 'label_ip_row': 'left'},
           'the title is left aligned (as the iPod\'s bar), the remaining time right aligned')
    expect(by['label_title'].get('tr_text') is None and by['label_title'].get('text') == 'Pod' and by['label_title'].get('visible') == 'false', 'label_title is the hidden brand text "iPod"')
    # demo's own hit test: the wheel takes touches, the screen and the picture never
    root = asset_tree(os.path.join(WORK, UI)); root.h = 480
    m = Machine()
    for x, y, what, want_last in ((CX, CY, 'the centre button', 'ipod_wheel'), (CX, WY + 8, 'the MENU label', 'ipod_wheel'), (CX - 90, CY, 'the previous label', 'ipod_wheel'),
                                  (CX + 90, CY, 'the next label', 'ipod_wheel'), (CX, CY + 90, 'the play / pause label', 'ipod_wheel'), (WX + 3, WY + 3, 'the square\'s corner', 'ipod_wheel'),
                                  (160, 100, 'the screen', 'm1plus_ipod_page'), (10, 245, 'beside the wheel', 'm1plus_ipod_page'), (300, 470, 'the window\'s corner', 'm1plus_ipod_page')):
        got = stock_target(m, root, x, y)
        expect(got[-1] == want_last and 'ipod_wheel_img' not in got and 'ipod_screen' not in got, f'a touch on {what} reaches {want_last} ({got})')
    # the wheel picture
    wp = asset_image('ipod_wheel')
    expect(wp.size == (220, 220) and wp.getpixel((0, 0))[3] == 0 and wp.getpixel((219, 219))[3] == 0 and wp.getpixel((110, 110))[3] == 255 and wp.getpixel((110, 3))[3] == 255,
           'the wheel image is 220 px: transparent corners, opaque ring and centre button')
    expect(same_pixels(os.path.join(mod_icons.PNG, 'ipod_wheel.png'), mod_icons.ipod_wheel()) and mod_icons.ipod_wheel().size == (220, 220),
           'the committed PNG is the generator\'s output')
    ph = asset_image('ipod_placeholder')
    expect(ph.size == (256, 256) and 'ipod_placeholder' in mod_icons.IPOD and all(ph.getpixel(p)[3] == 255 for p in ((0, 0), (255, 255), (128, 128), (255, 0))) and ph.getpixel((5, 250))[:3] < (40, 40, 40)
           and os.path.getsize(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx/ipod_placeholder.png')) < 40000,
           'the Pod\'s placeholder cover (the user-supplied iTunes one, scaled once): 256 px, opaque, dark with the grey note, in the tree and under 40 KB')
    ring_px, hub_px = wp.getpixel((110, 40)), wp.getpixel((110, 100))
    expect(sum(ring_px[:3]) > sum(hub_px[:3]) - 120 and ring_px != hub_px, 'the centre button is drawn apart from the ring')


def menu_tests(ctx):
    expect, P = ctx.expect, pod_pages
    item = next(i for i, r in enumerate(P.ITEMS) if r.label == 'Pod')
    expect(item == 19 == len(P.ITEMS) - 6 and P.ITEMS[item].action == P.ACT_IPOD == 22 and P.ID_CHARS[item] == 'k' and item not in P.DEFAULT_MENU,
           'Pod is menu item 19 (saved as "k"), after Settings and before Podcasts, hidden by default like Now Playing: Settings > Main Menu shows it, the Extras page lists it')
    expect(P.EXTRAS_ORDER.index(item) == P.EXTRAS_GROUPS[0][1].index('Pod') and P.parse_menu_full(b'123456k\n') == ([1, 2, 3, 4, 5, 6, 19], []) and P.format_menu([1, 2, 19]) == '12k\n',
           'Extras lists it in the Play group, after Now Playing and Shuffle; the saved list carries it as k')
    expect(pod_i18n.key_for('Pod') is None and 'Pod' in pod_i18n.BRANDS, 'the label is the brand name "iPod", a plain text in every language (as M1+ Music and Tidal)')
    rows0 = PSYMS['pod_rows_0']
    m = IM()
    m.widgets = {n: 0x30000000 + i for i, n in enumerate(['btn_return', 'btn_backtoplayer'])}
    m.windows['m1plus_ipod'] = WIN
    m.call(PSYMS['on_row'], a0=rows0 + 12 * item, count=5000000)
    expect(('window_open', 'm1plus_ipod') in m.calls and 'stock_resume' not in m.names(), 'the menu row opens m1plus_ipod')
    for page_ in (P.MENU, P.EXTRAS_PAGE): expect(page_.rows[item].label == 'Pod' and page_.rows[item].action == P.ACT_IPOD, f'{page_.key} has the row, same action')
    ui = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui')
    for key in ('m1plus_menu', 'm1plus_extras', 'm1plus_mainmenu'):
        t = awtk_ui.parse(open(os.path.join(ui, key + '.bin'), 'rb').read())
        row = t.find(f'pod_row{item}')
        lab = next(c for c in row.children if c.type == 'hscroll_label')
        expect(pod_i18n.shown_english(lab) == 'Pod' and row.find('pod_icon') is not None, f'{key}: row {item} reads iPod with its glyph')
    expect(asset_image('pod_ic_ipod').size == mod_icons.asset_size('pod_ic_ipod') if hasattr(mod_icons, 'asset_size') else asset_image('pod_ic_ipod').size[0] > 0, 'the row glyph is in the tree')


def open_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis')])
    m.windows['m1plus_ipod'] = 0
    expect(m.open() == 0xffffffff and 'timer_add' not in m.names() and 'widget_on' not in m.names(), 'a window that will not open: -1, nothing registered, no timer')
    m = machine()
    del m.widgets['ipod_wheel']
    expect(m.open() == 0xffffffff and 'navigator_back' in m.names() and m.timers == [], 'an asset that is not ours (no wheel): the window goes again, no timer')
    m = machine()
    expect(m.open() == 0, 'the page opens')
    c = m.calls
    on = {(a, e): (f, x) for _, a, e, f, x in (c_ for c_ in c if c_[0] == 'widget_on')}
    wheel, screen = m.widgets['ipod_wheel'], m.widgets['ipod_screen']
    expect(all((wheel, e) in on for e in (EVT_DOWN, EVT_MOVE, EVT_UP, EVT_ABORT)) and (screen, EVT_PAINT) in on and all((WIN, e) in on for e in (EVT_DESTROY, EVT_BG, EVT_FG)),
           'the wheel takes the four pointer events, the screen its own paint, the window its three events: nothing else is registered')
    expect(len(on) == 8 and [c_[0] for c_ in c].count('timer_add') == 1 and ('timer_add', PSYMS['ip_first'], O['IP_FIRST_MS']) in c, 'one page-scoped timer, a 50 ms one-shot')
    expect(not any(n in m.names() for n in ('widget_set_visible', 'widget_move', 'widget_resize', 'widget_destroy', 'widget_set_name')), 'it moves, hides and destroys nothing in the asset')
    expect(m.open() == 0 and m.names().count('window_open') == 0, 'opening again while it is up does nothing')
    # the timer
    m.calls = []; m.call(PSYMS['ip_first'], a0=0, count=40000000)
    expect(('timer_add', PSYMS['ip_tick'], O['IP_PAN_MS']) in m.calls, 'the one-shot starts the tick (the cover pane\'s pan on the main menu: IP_PAN_MS)')
    expect(any(c_[0] == 'bitmap_create_ex' and c_[1:] == (O['IP_ART'], O['IP_ART']) for c_ in m.calls), 'and makes the cover bitmap (the Pod placeholder: nothing is playing)')
    expect(('widget_load_image', 'ipod_placeholder') in [c_[:2] for c_ in m.calls] and not any(c_[:2] == ('widget_load_image', 'p_default') for c_ in m.calls), 'the placeholder is the Pod\'s own image, not the stock disc')
    # background / foreground / destroy
    m.calls = []; m.fire(EVT_BG, WIN)
    expect(('timer_remove', 0x777) in m.calls or m.timers is not None, 'to the background: the timer goes')
    m.calls = []; m.fire(EVT_FG, WIN)
    expect(('timer_add', PSYMS['ip_first'], O['IP_FIRST_MS']) in m.calls, 'to the foreground: it is armed again')
    m.calls = []; m.fire(EVT_DESTROY, WIN)
    expect(('timer_remove', 0x777) in m.calls and any(c_[0] == 'bitmap_destroy' for c_ in m.calls), 'destroy: the timer is removed and the cover bitmap freed')
    m.calls = []; m.timers = []
    expect(m.open() == 0 and ('window_open', 'm1plus_ipod') in m.calls, 'the state is clean: it opens again')
    fn, ctx = m.bound[(WIN, EVT_DESTROY)]
    m.calls = []; m.call(fn, a0=0x24100008, a1=0)   # the destroy of another window (an older page): the page is left alone
    expect('timer_remove' not in m.names() and 'bitmap_destroy' not in m.names(), 'a destroy of another window leaves the page alone')


def paint_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis'), ('Homogenic', 'Bjork')])
    m.open(); m.timers = []
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    texts, fills, blits = m.paint()
    names = [t for t, _ in texts]
    expect('Pod' in names, f'the title bar: Pod ({names})')
    rows = rows_of(texts)
    expect(rows == [m.tr(k) for k in MAIN_KEYS], f'the main menu rows in the iPod order, in the language of the player ({rows})')
    ys = sorted(r[1] for t, r in texts if t in rows)
    expect(ys == [row_y(i) for i in range(len(MAIN_KEYS))], 'on the shared row pitch from the title bar')
    expect(all(r[2] == O['IP_SPLIT_X'] - O['IP_TEXT_X'] - 22 for t, r in texts if t in rows), 'in the list\'s width: the left pane of the split screen')
    expect(any(f[0] == 0xfff8dd9a and f[2] == BARH and f[3] == O['IP_SPLIT_X'] for f in fills), 'the selected row starts with its highlight')
    grad = [f for f in fills if f[2] >= BARH and f[3] == O['IP_SPLIT_X'] and f[4] == 1]
    expect(len(grad) == row_h(0) and grad[0][0] == 0xfff8dd9a and grad[-1][0] == 0xff814f15 and [g[2] for g in grad] == list(range(BARH, row_y(1))),
           'a multi-stop blue gradient with highlight and bottom rule')
    expect(not [b for b in blits if b[2] == PANE], 'the cover pane is plain until the timer has chosen and decoded covers (paint decodes nothing)')
    expect(not any(f[1] == O['IP_SPLIT_X'] and f[3] <= 2 and f[4] == 1 for f in fills) and O['IP_PANE_X'] == O['IP_SPLIT_X'] and O['IP_PANE_W'] == 320 - O['IP_SPLIT_X'], 'no rule between the white menu and the cover pane: the pane starts flush at x 160')
    # the title bar, as the iPod's: the title on the left, no clock; the battery (the stock bar's own value), the play state next to it
    title = [r for t, r in texts if t == 'Pod']
    expect(title and title[0][0] == O['IP_TEXT_X'] and title[0][0] + title[0][2] <= O['IP_SPLIT_X'] - 8 - 27 - 8 - 12, f'the title shares the list inset and clears the play state ({title})')
    expect(not [t for t in names if ':' in t], f'no clock ({names})')
    # the battery as the reference's: 24 x 12 and a 3 x 5 nub (27 px, 8 px from the edge), a ten-row fill in two bands, red at 20 % or less
    bx, by = O['IP_SPLIT_X'] - 8 - 27, BARH // 2 - 6
    rgb = lambda h: 0xff000000 | (h & 255) << 16 | (h >> 8 & 255) << 8 | h >> 16
    GREEN = [rgb(h) for h in (0xa4d08a, 0xdcf8c7, 0xc9ecb0, 0xa5e07f, 0xa1de7d, 0x6bab46, 0x4e932c, 0x539831, 0x5fa53e, 0x539831)]
    RED = [rgb(h) for h in (0xd17f6b, 0xf0b2a8, 0xe89d90, 0xe87259, 0xe67357, 0xb74124, 0xa3300b, 0xa7340f, 0xb3421c, 0xa73410)]
    def fill_rows(fills): return [[f for f in fills if f[1] == bx + 1 and f[2] == by + 1 + i and f[4] == 1][-1] for i in range(10)]
    chans = lambda c: (c & 255, c >> 8 & 255, c >> 16 & 255)   # AWTK order: r | g << 8 | b << 16
    rows_ = fill_rows(fills)
    expect(all(g > b and g >= r for r, g, b in (chans(f[0]) for f in rows_)), 'at a normal level every fill row is green (g above r and b), not beige or brown')
    import preview_ipod
    expect(preview_ipod.GREEN == [tuple(c & 255 for c in (h >> 16, h >> 8, h)) for h in (0xa4d08a, 0xdcf8c7, 0xc9ecb0, 0xa5e07f, 0xa1de7d, 0x6bab46, 0x4e932c, 0x539831, 0x5fa53e, 0x539831)]
           and [(chans(r[0])[0], chans(r[0])[1], chans(r[0])[2]) for r in rows_] == preview_ipod.GREEN, 'the preview draws the payload\'s fill colours')
    expect([r[0] for r in rows_] == GREEN and all(r[3] == 22 * 80 // 100 for r in rows_), f'the battery: the status bar\'s 80 % in the reference\'s two green bands ({[hex(r[0]) for r in rows_]})')
    expect(any(f[1:5] == (bx + 24, by + 3, 3, 5) for f in fills) and any(f[1:5] == (bx, by, 24, 1) for f in fills) and any(f[1:5] == (bx, by + 11, 24, 1) for f in fills), 'a 24 x 12 outline and a 3 x 5 nub')
    m.battery_img = 'bar_charge'; m.props[(m.widgets['pgbar_battery'], 'value')] = 100
    rows_ = fill_rows(m.paint()[1])
    expect([r[0] for r in rows_] == GREEN and all(r[3] == 22 for r in rows_), 'charging: the fill is green and full')
    m.props[(m.widgets['pgbar_battery'], 'value')] = 20; m.battery_img = 'bar_power'
    rows_ = fill_rows(m.paint()[1])
    expect([r[0] for r in rows_] == RED and all(r > g and r > b for r, g, b in (chans(x[0]) for x in rows_)), 'at 20 % the fill is the reference\'s red (r above g and b)')
    m.setword(SYSBAR, 0)
    expect(not [f for f in m.paint()[1] if f[1] == bx + 1 and f[3] != 22 and f[2] == by + 1], 'with no status bar there is no fill (and no crash)')
    m.setword(SYSBAR, m.alloc(0x80))
    m.status = 2
    top = BARH // 2 - 7   # the 12 x 14 play glyph, centred on the bar
    gx = bx - 8 - 12
    blue = [0xff000000 | ip_lerp(O['IP_SEL_TOP'], O['IP_SEL_BOT'], r, 14) for r in range(14)]
    in_box = lambda fills: [f for f in fills if gx <= f[1] < gx + 12 and f[2] < BARH and f[4] == 1]
    glyph = in_box(m.paint()[1])
    expect([(f[1], f[2], f[3]) for f in glyph] == [(gx + 1, top + r, (min(r, 13 - r) + 1) * 10 // 7) for r in range(14)] and [f[0] for f in glyph] == blue,
           f'playing: a blue triangle 14 high (the selection\'s gradient) 8 px before the battery ({glyph})')
    m.status = 3
    glyph = in_box(m.paint()[1])
    expect(sorted((f[1], f[2], f[3]) for f in glyph) == sorted((x, top + r, 4) for r in range(14) for x in (gx + 1, gx + 7)) and {f[0] for f in glyph} == set(blue),
           'paused: two blue bars 4 px wide')
    m.status = 0
    expect(not in_box(m.paint()[1]), 'nothing played: no glyph')
    # chevrons: as the iPod, only the selected row has one (white, on the selection)
    chev = [f for f in m.paint()[1] if f[3] == 2 and f[4] == 1 and BARH <= f[2] < 240 and f[1] < O['IP_SPLIT_X']]
    expect(len(chev) == 9 and all(f[0] == 0xffffffff and BARH <= f[2] < row_y(1) for f in chev), f'one chevron, on the selected row ({len(chev)} fills)')
    # another language
    m.set_language('ru_RU')
    t2 = rows_of(m.paint()[0])
    expect(t2[:2] == [pod_i18n.TEXT[k]['ru_RU'] for k in MAIN_KEYS[:2]], f'the rows follow Settings > General > Language ({t2[:3]})')


def wheel_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[(f'Album {i}', 'A') for i in range(5)], songs=[f'Song {i:02d}' for i in range(30)])
    m.open(); m.timers = []
    def selected():
        texts, fills, _ = m.paint()
        ys = [f[2] for f in fills if f[4] == 1 and f[3] == (O['IP_SPLIT_X'] if not m.in_list else 320) and f[2] >= BARH and f[0] & 0xffffff == 0xf8dd9a]   # the selection's top line
        return min(ys) if ys else None
    m.in_list = False
    def row(n=ROWS):
        y = selected()
        return None if y is None else row_of(y, n)
    expect(row() == 0, 'the first row is selected')
    # a drag of 60 degrees turns three steps, on every start angle
    for start in (0, 37, 90, 181, 270, 333):
        m = machine(albums=[('A', 'x')]); m.open(); m.timers = []; m.in_list = False
        m.turn(start, start + STEP_DEG * 3 + 4)
        expect(row() == 3, f'a 49 degree turn moves three rows ({row()})')
        m.turn(start, start - STEP_DEG * 2 - 4)
        expect(row() == 1, f'and two steps back reach row one ({row()})')
    m = machine(); m.open(); m.timers = []; m.in_list = False
    m.turn(10, 10 + STEP_DEG * 3 + 5)
    expect(row() == 3, 'three steps reach row 3')
    m.turn(100, 100 - STEP_DEG * 2 - 5)
    expect(row() == 1, 'two steps back: row 1')
    m.turn(100, 100 - STEP_DEG * 5 - 5)
    expect(row() == 0, 'the cursor stops at the first row (no wrap, as the iPod)')
    m.turn(200, 200 + STEP_DEG * 30)
    expect(row() == 5, 'and at the last root row (Now Playing)')
    # a small turn is no step, a turn at the edge of the dead zone / outside
    m = machine(); m.open(); m.timers = []; m.in_list = False
    m.turn(30, 30 + 12, r=80)
    expect(row() == 0, 'a 12 degree wobble is no step')
    m.turn(30, 30 + 200, r=10)
    expect(row() == 0, 'a finger inside the dead zone (a touch that began on the centre button) turns nothing')
    m.turn(30, 30 + STEP_DEG * 3 + 1, r=HUB + 5)
    expect(row() == 3, 'a finger just outside the centre button turns the wheel')
    m.turn(30, 30 + STEP_DEG * 3 + 1, r=RING - 3)
    expect(row() == 5, 'and one at the rim stays at the last row')
    # a drag that starts on the centre button turns nothing
    m = machine(); m.open(); m.timers = []; m.in_list = False
    m.turn(30, 30 + 100, r=30)
    expect(row() == 0, 'a drag that begins on the centre button turns nothing (and is no tap)')
    expect('start_player' not in m.names() and not m.opened and m.names().count('loadLocalClassList') == 0, 'and selects nothing')
    # a long list: the cursor leads the window
    m = machine(songs=[f'Song {i:02d}' for i in range(30)]); m.open(); m.timers = []
    music(m)
    m.in_list = False
    m.turn(0, STEP_DEG * 4 + 5)   # Songs (row 4)
    m.tap(CX, CY); settle(m)
    m.in_list = True
    texts, fills, _ = m.paint()
    expect(rows_of(texts)[:2] == ['Song 00', 'Song 01'] and 'Songs' in [t for t, _ in texts], 'Songs: the library list, the title Songs')
    m.turn(0, STEP_DEG * 12 + 5)
    texts, fills, _ = m.paint()
    rows = rows_of(texts)
    expect(row(SONGS_N) == 4 and rows[0] == 'Song 08' and rows[-1] == 'Song 12' and len(rows) == 5, f'twelve steps down: five two-line rows, the cursor on the last ({rows[0]}..{rows[-1]}, row {row(SONGS_N)})')
    m.turn(0, -(STEP_DEG * 4 + 5))
    rows = rows_of(m.paint()[0])
    expect(row(SONGS_N) == 0 and rows[0] == 'Song 08', 'four back: the window stays while the cursor is inside it')
    m.turn(0, -(STEP_DEG * 8 + 5))
    rows = rows_of(m.paint()[0])
    expect(row(SONGS_N) == 0 and rows[0] == 'Song 00', f'past the top of the window: it scrolls up with the cursor ({rows[0]}, {row(SONGS_N)})')


def tap_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis')]); m.open(); m.timers = []
    # MENU: the top sector, on the main menu closes the page
    for deg in (-40, -10, 0, 25, 44):
        m = machine(); m.open(); m.timers = []
        x, y = m.polar(deg, 85); m.tap(x, y)
        expect(m.names().count('navigator_back') == 1, f'a tap at {deg} degrees (top sector): MENU closes the page from the main menu')
    for deg, want in ((60, 'next'), (90, 'next'), (120, 'next'), (240, 'prev'), (270, 'prev'), (300, 'prev'), (150, 'playpause'), (180, 'playpause'), (210, 'playpause')):
        m = machine(); m.open(); m.timers = []
        x, y = m.polar(deg, 85); m.tap(x, y)
        got = m.cmds[0][0] if m.cmds else None
        expect(got == want and 'navigator_back' not in m.names(), f'a tap at {deg} degrees: {want} ({got})')
    # the quick clicks get the event time stock reads
    m = machine(); m.open(); m.timers = []
    x, y = m.polar(90, 85); m.tap(x, y)
    expect(m.cmds == [('next', 1080, 0)], f'next_quick_click gets the touch\'s own event (its time word is what stock compares) ({m.cmds})')
    x, y = m.polar(270, 85); m.tap(x, y)
    expect(m.cmds[-1] == ('prev', 1080, 0), 'previous is the same call')
    # outside the circle: the square's corners and the beyond-ring margin
    m = machine(); m.open(); m.timers = []
    for x, y in ((WX + 3, WY + 3), (WX + WD - 3, WY + 3), (WX + 3, WY + WD - 3), (WX + WD - 3, WY + WD - 3), (CX + 108, CY + 40)):
        m.tap(x, y)
        expect(not m.cmds and 'navigator_back' not in m.names() and not m.opened and 'widget_grab' not in m.names(), f'a touch at ({x}, {y}) outside the circle does nothing and takes no grab')
    # the grab: held for the touch, released at its end
    x, y = m.polar(90, 85)
    m.ptr('down', x, y, 5); expect(('widget_grab', WIN, m.widgets['ipod_wheel']) in m.calls, 'the touch is grabbed (moves and the release come to the wheel wherever they go)')
    m.ptr('up', x, y, 90); expect(('widget_ungrab', WIN, m.widgets['ipod_wheel']) in m.calls, 'and released at the end')
    m.cmds = []
    m.ptr('down', x, y, 5); m.ptr('abort', x, y, 6); expect(('widget_ungrab', WIN, m.widgets['ipod_wheel']) in m.calls and not m.cmds, 'an abort ends it and acts on nothing')
    m.ptr('up', x, y, 9)
    expect(not m.cmds, 'an up after the abort is nothing')
    # a tap that travels is not a tap
    m = machine(); m.open(); m.timers = []
    x, y = m.polar(90, 85)
    m.ptr('down', x, y, 5); m.ptr('move', x + 14, y, 20); m.ptr('up', x + 14, y, 40)
    expect(not m.cmds, 'a touch that travels 14 px and turns no step is no tap')
    m.ptr('down', x, y, 5); m.ptr('move', x + 6, y, 20); m.ptr('up', x + 6, y, 40)
    expect(m.cmds and m.cmds[-1][0] == 'next', 'a touch that wobbles 6 px is')
    # a tap after a turn is not a tap either (the turn already acted)
    m = machine(); m.open(); m.timers = []
    m.turn(0, 40, r=85)
    expect(not m.cmds and 'navigator_back' not in m.names(), 'a turn that ends in the top sector is not MENU')


def nav_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis'), ('Homogenic', 'Bjork')], artists=['Miles Davis', 'Bjork'], songs=['So What', 'Freddie'], playlists=['Road', 'Gym'])
    m.artist_albums = {'Miles Davis': [m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/m/Kind of Blue.flac', rid=900)]}
    m.album_tracks['Kind of Blue'] = m.album_tracks['Kind of Blue']
    m.open(); m.timers = []
    music(m)
    def centre(): m.tap(CX, CY)
    def step_to(n):
        m.turn(0, STEP_DEG * n + 5)
    def front():
        settle(m); texts, fills, _ = m.paint()
        return rows_of(texts), [t for t, r in texts if r[0] != 10 or r[1] < BARH]
    # Albums
    step_to(3); centre()
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'Albums: the stock album query')
    rows, other = front()
    expect(rows == ['Kind of Blue', 'Homogenic'] and 'Albums' in other, f'the albums as rows, the title Albums ({rows}, {other})')
    # an album's tracks
    centre()
    expect(('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Kind of Blue') in m.calls, 'an album: loadAlbumdetailList(0xf003, the album\'s record), as the album page runs it')
    rows, other = front()
    expect(rows == ['Kind of Blue 0', 'Kind of Blue 1', 'Kind of Blue 2'], f'its tracks ({rows})')
    expect(m.word(G_CLASS) == 0xff10, 'g_class_type is the browsing record\'s class, as albuminfo_page_init leaves it')
    # play the second track
    step_to(1)
    centre()
    pl = m.played
    expect(pl is not None and pl[1] == 1 and [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in pl[0]] == ['Kind of Blue 0', 'Kind of Blue 1', 'Kind of Blue 2'],
           f'a track: loadSongList of the shown list, start_player at its row ({pl and pl[1]})')
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(sp == [('start_player', 1, 0xff10, O['PLAY_MODE'])] and ('loadSongList', 'Kind of Blue-1.flac', 0, 0xff10) in m.calls,
           f'with the album\'s class and the play mode the stock Play all passes ({sp})')
    expect(m.read_cstr(FORCE) == '' or m.u.mem_read(FORCE, 1)[0] == 1, 'force_refreshflag is set, as the stock Play all handler does')
    expect('navigator_to_with_context' not in m.names(), 'no stock Now Playing page opens: the iPod page shows it')
    # Now Playing
    m.status = 2; m.pt = (107, 305)
    t = m.song('Blue in Green', artist='Miles Davis', album='Kind of Blue', rid=1)
    m.play([m.album_tracks['Kind of Blue'][0], t, m.album_tracks['Kind of Blue'][2]], 1)
    m.clock += O['IP_NP_PEND_MS']   # (another record than the one started: shown once the started one's wait is over, np_pending_tests)
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    texts, fills, blits = m.paint()
    tx = [t_ for t_, _ in texts]
    expect(['Blue in Green', 'Miles Davis', 'Kind of Blue', '2 / 3', '1:47', '-3:18', 'Now Playing'] == [x for x in tx if x in ('Blue in Green', 'Miles Davis', 'Kind of Blue', '2 / 3', '1:47', '-3:18', 'Now Playing')],
           f'Now Playing: title, artist, album, "2 / 3", elapsed and remaining, the title bar ({tx})')
    TX, TW, BY, BH = O['IP_NP_TRACK_X'], O['IP_NP_TRACK_W'], O['IP_NP_BAR_Y'], O['IP_NP_BAR_H']
    fw = TW * 107 // 305
    bar = [f for f in fills if f[1] == TX and f[3] == fw and BY <= f[2] < BY + BH and f[4] == 1]
    expect(len(bar) == BH, f'the progress fill is a {BH} px bar, 107 of 305 s of the 204 px track ({len(bar)} rows of {fw} px)')
    expect(any(f[1:5] == (TX + fw, BY + BH // 2, TW - fw, 1) for f in fills) and any(f[1:5] == (TX + fw, BY, TW - fw, 1) and f[0] == 0xffe1e1e1 for f in fills),
           'the sunken grey track (no outline) carries on after the fill')
    PIC = (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_NP_ART_W'], O['IP_NP_ART_W'] + O['IP_NP_REFLECT'])
    cov = [b for b in blits if b[2][:2] == PIC[:2]]
    expect(len(cov) == 1 and cov[0][2] == PIC and cov[0][1] == (0, 0) + PIC[2:],
           'the turned cover and its reflection are one straight 1:1 copy of the picture made with the cover (no scaling in paint)')
    refl = [f for f in fills if f[2] >= BY + BH and f[1] == TX and f[3] == fw and f[4] == 1]
    expect(len(refl) == O['IP_NP_BAR_REFLECT'] - 1 and refl[0][2] == BY + BH + 1 and refl[0][0] != refl[-1][0], 'a short reflection of the bar fades out under it, one clear row below the bar')
    rect = {t_: r for t_, r in texts}
    GAP = O['IP_NP_TIME_GAP']
    expect(rect['1:47'][0] + rect['1:47'][2] - 2 == TX - GAP and rect['-3:18'][0] == TX + TW + GAP and rect['1:47'][1] == rect['-3:18'][1] == BY - 1,
           'm:ss elapsed and remaining hug the track\'s ends, on one line')
    # MENU: back to the tracks (the album queried again), again to the albums, again to the main menu
    x, y = m.polar(0, 85); m.tap(x, y)
    expect(('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Kind of Blue') in m.calls, 'MENU from Now Playing: the tracks, read again from the stock queries')
    rows, other = front()
    expect(rows[:2] == ['Kind of Blue 0', 'Kind of Blue 1'] and m.paint()[1].__class__ is list, 'the cursor is where it was')
    m.tap(*m.polar(0, 85))
    expect(front()[0][:2] == ['Kind of Blue', 'Homogenic'] and 'Albums' in front()[1], 'MENU: the albums again')
    m.tap(*m.polar(0, 85))
    expect(front()[0] == [m.tr(k) for k in MUSIC_KEYS], 'MENU: the Music menu')
    m.tap(*m.polar(0, 85))
    expect(front()[0] == [m.tr(k) for k in MAIN_KEYS], 'MENU: the main menu')
    m.calls = []
    m.tap(*m.polar(0, 85))
    expect(m.names().count('navigator_back') == 1, 'MENU on the main menu closes the page (navigator_back, the status bar comes back with the stock window)')
    # Artists: the album list has the stock All Songs record first, its cover is the placeholder; a one-album artist skips the list
    m = machine(albums=[('Kind of Blue', 'Miles Davis'), ('Blue in Green', 'Miles Davis'), ('Homogenic', 'Bjork')], artists=['Miles Davis', 'Bjork']); m.open(); m.timers = []
    rec = lambda album, artist, rid: m.record(album=album, artist=artist, path=f'/mnt/mmc/m/{album}.flac', rid=rid)
    m.artist_albums = {'Miles Davis': [rec('Kind of Blue', 'Miles Davis', 900), rec('Blue in Green', 'Miles Davis', 901)], 'Bjork': [rec('Homogenic', 'Bjork', 902)]}
    every = m.album_tracks['Kind of Blue'] + m.album_tracks['Blue in Green']
    m.album_tracks['All songs'] = every
    title = lambda: [t for t, r in m.paint()[0] if r[1] < BARH and r[0] == O['IP_TEXT_X']]
    music(m)
    m.turn(0, STEP_DEG * 2 + 5); m.tap(CX, CY)
    artist_rec = m.deques[m.word(SHOWLIST)][0]
    m.tap(CX, CY); calls = list(m.calls)
    rows = rows_of(m.paint()[0])
    expect(('loadAlbumList', O['CLASS_ARTISTS'], artist_rec, 'Miles Davis') in calls and rows == ['All Songs', 'Kind of Blue', 'Blue in Green'] and title() == ['Miles Davis'],
           f'an artist: loadAlbumList(0xf004, the artist\'s record); the stock All songs record is shown FIRST as the stock "All Songs", then the albums; the title is the artist ({rows}, {title()})')
    covers = [x for _ in range(4) for x in tick(m) if x[0] == "widget_load_image"]
    expect(any(c[1] == 'ipod_placeholder' for c in covers), 'the All Songs row has the placeholder as its cover')
    m.tap(CX, CY)
    expect(('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS'], 'All songs') in m.calls and m.word(G_CLASS) == 0xff11, 'All Songs: loadAlbumdetailList(0xff01, the All songs record) -> 0xff11, the stock path')
    texts = m.paint()[0]
    expect(rows_of(texts) == [t for t in [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in every]] and title() == ['All Songs'], f'a plain list (no covers) of all the artist\'s songs, in the stock order ({rows_of(texts)})')
    m.tap(CX, CY)
    pl = m.played
    expect(pl is not None and pl[1] == 0 and [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in pl[0]] == [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in every] and m.word(G_CLASS) == 0xff11,
           'and it plays from that list in that order, with the artist class')
    m.tap(*m.polar(0, 85)); m.tap(*m.polar(0, 85))   # Now Playing -> the songs -> the album list
    rows = rows_of(m.paint()[0])
    sel = [f for f in m.paint()[1] if f[3] == 320 and f[4] == 1 and f[2] >= BARH]
    expect(rows == ['All Songs', 'Kind of Blue', 'Blue in Green'] and min(f[2] for f in sel) == BARH, f'MENU: back to the album list, on All Songs ({rows})')
    m.turn(0, STEP_DEG * 2 + 5); m.tap(CX, CY)   # the second album (stock row 1)
    expect(('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS'], 'Blue in Green') in m.calls and rows_of(m.paint()[0]) == ['Blue in Green 0', 'Blue in Green 1', 'Blue in Green 2'] and title() == ['Blue in Green'],
           'row 2 is the stock album 1: its songs, the album as the title (the displayed index maps to the stock one)')
    m.tap(*m.polar(0, 85))
    sel = [f for f in m.paint()[1] if f[3] == 320 and f[4] == 1 and f[2] >= BARH]
    expect(min(f[2] for f in sel) == BARH + 2 * O['IP_TALL_H'], 'MENU: the album list with the cursor where it was')
    m.tap(*m.polar(0, 85))
    m.turn(0, STEP_DEG + 5)
    expect(rows_of(m.paint()[0]) == ['Miles Davis', 'Bjork'], 'MENU: the artists')
    m.calls = []
    m.tap(CX, CY)   # Bjork: one album
    expect(('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS'], 'Homogenic') in m.calls and m.word(G_CLASS) == 0xff11, 'an artist with one album: its songs directly (loadAlbumList, then loadAlbumdetailList of that album)')
    texts = m.paint()[0]
    expect(rows_of(texts) == ['Homogenic 0', 'Homogenic 1', 'Homogenic 2'] and title() == ['Homogenic'] and m.call(PSYMS['ip_render_split']) == 0, f'a plain song list titled with the album, the album list skipped ({rows_of(texts)}, {title()})')
    m.tap(CX, CY)
    expect(m.played is not None and [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in m.played[0]] == ['Homogenic 0', 'Homogenic 1', 'Homogenic 2'], 'it plays that album')
    m.tap(*m.polar(0, 85)); m.tap(*m.polar(0, 85))
    sel = [f for f in m.paint()[1] if f[3] == 320 and f[4] == 1 and f[2] >= BARH]
    expect(rows_of(m.paint()[0]) == ['Miles Davis', 'Bjork'] and min(f[2] for f in sel) == row_y(1), 'MENU from there returns to Artists with the cursor where it was (on Bjork)')
    # Songs
    m = machine(songs=['So What', 'Freddie']); m.open(); m.timers = []
    music(m)
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    m.turn(0, 23); m.tap(CX, CY)
    expect(m.played and m.played[1] == 1 and ('start_player', 1, O['CLASS_ALL_SONGS'], O['PLAY_MODE']) in m.calls, f'Songs: a track plays with the library class ({m.calls[-4:]})')
    # Playlists: the id in classinfo[1], class 0xff13
    m = machine(playlists=['Road', 'Gym']); m.open(); m.timers = []
    music(m)
    m.playlist_songs = {7: [m.song('R1', rid=601, path='/mnt/mmc/m/1.flac'), m.song('R2', rid=602, path='/mnt/mmc/m/1.flac', name='2.flac')], 8: [m.song('G1', rid=603)]}
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY); calls = list(m.calls)
    rows = rows_of(m.paint()[0])
    expect(('loadLocalClassList', O['CLASS_PLAYLISTS']) in calls and rows == ['Road', 'Gym'], f'Playlists: the playlist headers ({rows})')
    m.turn(0, 23); m.tap(CX, CY)
    rows = rows_of(m.paint()[0])
    expect(m.word(CLASSINFO + 4) == 8 and rows == ['G1'], f'a playlist: its id in classinfo[1], its songs ({rows}, {m.word(CLASSINFO + 4)})')
    m.setword(CLASSINFO + 4, 99)   # another page left something else there
    m.tap(CX, CY)
    expect(m.word(CLASSINFO + 4) == 8 and ('start_player', 0, O['CLASS_PLAYLIST_SONGS'], O['PLAY_MODE']) in m.calls, 'a playlist track: the id is put back before the play, class 0xff13')
    # Cover Flow, Shuffle Songs and Settings stay on the page: test/pod/ipod_cf.py, shuffle_tests, settings_tests
    m = machine(); m.open(); m.timers = []
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    expect(texts_of(m.paint())[0] == 'Not Playing' or 'Not Playing' in texts_of(m.paint()), 'Now Playing with nothing queued: "Not Playing"')
    m.tap(CX, CY)
    expect(m.cmds == [], f'the centre button on Now Playing with nothing to scrub does nothing ({m.cmds})')
    x, y = m.polar(180, 85); m.tap(x, y)
    expect(m.cmds == [('playpause',)], 'the wheel\'s bottom sector plays / pauses, as on the iPod')


def stale_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis')], songs=['So What']); m.open(); m.timers = []
    music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    rows = rows_of(m.paint()[0])
    assert rows == ['Kind of Blue']
    m.setword(SHOWLIST, m.new_deque(m.class_lists[O['CLASS_ALL_SONGS']]))   # another page queried: the stock list is not ours any more
    m.calls = []
    texts = [t for t, r in m.paint()[0]]
    expect('Kind of Blue' not in texts and 'So What' not in texts and 'loadLocalClassList' not in m.names(), 'a stale list is never read in paint (nothing drawn, no query from paint)')
    m.top_main = 0
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect('loadLocalClassList' not in m.names(), 'the timer does not query while another window is in front')
    m.top_main = WIN
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'in front again, the tick reads the albums again')
    expect(rows_of(m.paint()[0]) == ['Kind of Blue'], 'and the rows are back')
    m.setword(SHOWLIST, m.new_deque(m.class_lists[O['CLASS_ALL_SONGS']]))
    m.calls = []; m.fire(EVT_FG, WIN)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'the window coming back to the front reads its list again')
    m.setword(SHOWLIST, m.new_deque(m.class_lists[O['CLASS_ALL_SONGS']]))
    m.calls = []; m.tap(CX, CY)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls and ('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Kind of Blue') in m.calls, 'a tap on a stale list reads it first, then opens the right album')
    # an empty list: the message
    m = machine(); m.open(); m.timers = []
    music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    expect(m.tr('No albums') in [t for t, _ in m.paint()[0]], 'an empty albums list says so')
    m.tap(CX, CY)
    expect(not m.cmds and 'start_player' not in m.names() and 'loadAlbumdetailList' not in m.names(), 'and a tap on it does nothing')
    for steps, key in ((2, 'No artists'), (4, 'No songs'), (1, 'No playlists')):
        m = machine(); m.open(); m.timers = []
        music(m)
        m.turn(0, steps * STEP_DEG + 5); m.tap(CX, CY)
        expect(m.tr(key) in [t for t, _ in m.paint()[0]], f'an empty {key} list says so')
    # a track that is not on the card
    m = machine(albums=[('Kind of Blue', 'Miles Davis')]); m.open(); m.timers = []
    music(m)
    m.present.discard('/mnt/mmc/m/Kind of Blue-0.flac')
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY); m.tap(CX, CY); m.calls = []; m.tap(CX, CY)
    expect('start_player' not in m.names() and any(c[0] == 'toast' for c in m.calls), 'a track whose file is gone: the stock message box, nothing started')


def playing_indicator_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['First', 'Second']); m.open(); m.timers = []
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][1]], 0)
    music(m)
    m.turn(0, 4 * STEP_DEG + 5); m.tap(CX, CY)
    m.images['ipod_playing'] = (28, 28, bytes((255, 255, 255, 255)) * 784)
    S = O['IP_PLAY_PX']
    spot = lambda row: (320 - O['IP_TEXT_X'] - S, row_y(row, SONGS_N) + (row_h(row, SONGS_N) - S) // 2, S, S)   # Music > Songs' rows
    _, fills, blits = m.paint()
    mark = [b for b in blits if b[2] == spot(1)]
    expect(len(mark) == 1 and mark[0][1] == (0, 0, S, S), 'an unselected playing track has the speaker (the 14 px volume-2 image), right aligned in its row')
    ptr, bw, bh = m.bitmaps[mark[0][0]]
    col = lambda y: m.word(ptr + 4 * (y * bw))
    expect((bw, bh) == (S, S) and col(0) == 0xff000000 | O['IP_SEL_TOP'] and col(S - 1) == 0xff000000 | ip_lerp(O['IP_SEL_TOP'], O['IP_SEL_BOT'], S - 1, S) and col(0) != col(S - 1),
           'drawn in the title bar glyph\'s blue, a row at a time down its gradient (opaque)')
    expect(not [b for b in blits if b[2] == spot(0)], 'none on the selected row, and none on the other rows')
    m.paint(); m.paint()
    expect(not [c for c in m.calls if c[0] in ("bitmap_create_ex", "widget_load_image")], "decoded once (the first paint), no allocation or decode in later paints")


def music_menu_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []
    texts, _, _ = m.paint()
    expect([t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if r[0] == O['IP_TEXT_X'] and BARH <= r[1] < 240] ==
           [m.tr(k) for k in MAIN_KEYS], 'root shortcuts use the narrower margin')
    m.tap(CX, CY)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MUSIC_KEYS], 'Music contains the library entries in the iPod classic order')

def genre_composer_tests(ctx):
    expect = ctx.expect
    title = lambda: [t for t, r in m.paint()[0] if r[1] < BARH and r[0] == O['IP_TEXT_X']]
    m = machine(); m.open(); m.timers = []
    m.class_lists[O['CLASS_GENRES']] = [m.record(title=g, album='', artist='', path='', rid=600 + i) for i, g in enumerate(['Jazz', 'Rock'])]
    m.class_lists[O['CLASS_COMPOSERS']] = [m.record(title=c, album='', artist='', path='', rid=700 + i) for i, c in enumerate(['Bach', 'Satie'])]
    m.genre_songs[('Rock', 0)] = [m.song('Riff', rid=801, path='/mnt/mmc/m/riff.flac', name='riff.flac')]
    m.present.add('/mnt/mmc/m/riff.flac')
    m.artist_albums['Bach'] = [m.record(album='Suites', artist='Bach', path='/mnt/mmc/m/s.flac', title='Suites', rid=900), m.record(album='Partitas', artist='Bach', path='/mnt/mmc/m/p.flac', title='Partitas', rid=901)]
    music(m); m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    expect(title() == [m.tr('Genres')] and rows_of(m.paint()[0]) == ['Jazz', 'Rock'], f'Music > Genres: the genre names ({rows_of(m.paint()[0])})')
    m.turn(0, STEP_DEG + 5); m.calls = []; m.tap(CX, CY)
    loaded = ('loadLocalClassList', O['CLASS_GENRE_SONGS']) in m.calls
    expect(title() == ['Rock'] and loaded and rows_of(m.paint()[0]) == ['Riff'], f'a genre opens its songs under its name ({title()}, {rows_of(m.paint()[0])})')
    m.calls = []; m.tap(CX, CY)
    expect(('start_player', 0, O['CLASS_GENRE_SONGS'], O['PLAY_MODE']) in m.calls, 'a genre song plays with the genre class')
    m = machine(); m.open(); m.timers = []
    music(m); m.turn(0, STEP_DEG * 6 + 5); m.tap(CX, CY)
    expect(title() == [m.tr('Composers')] and rows_of(m.paint()[0]) == [m.tr('No songs')], 'Music > Composers: the title, and the empty message (stock No songs) in an empty library')
    m = machine(); m.open(); m.timers = []
    m.class_lists[O['CLASS_COMPOSERS']] = [m.record(title='Bach', album='', artist='', path='', rid=700)]
    m.artist_albums['Bach'] = [m.record(album='Suites', artist='Bach', path='/mnt/mmc/m/s.flac', title='Suites', rid=900), m.record(album='Partitas', artist='Bach', path='/mnt/mmc/m/p.flac', title='Partitas', rid=901)]
    music(m); m.turn(0, STEP_DEG * 6 + 5); m.tap(CX, CY)
    expect(rows_of(m.paint()[0]) == ['Bach'], 'composers: the names')
    m.calls = []; m.tap(CX, CY)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][1] == O['CLASS_COMPOSERS'] and title() == ['Bach'] and rows_of(m.paint()[0])[:1] == [m.tr('local_allsong')], f"a composer opens the composers' album list, All Songs first ({la}, {rows_of(m.paint()[0])})")
    m.turn(0, STEP_DEG + 5); m.calls = []; m.tap(CX, CY)
    expect(('loadAlbumdetailList', O['CLASS_COMPOSER_ALBUMS']) in [c[:2] for c in m.calls], 'an album of the composer lists its songs by the composer scope')
    # the iPod's genre rows: no cover, the name and "N artists, N albums" under it (counted by the genre query's groups, the shown list untouched)
    m = machine(); m.open(); m.timers = []
    m.class_lists[O['CLASS_GENRES']] = [m.record(title=g, album='', artist='', path='', rid=600 + i) for i, g in enumerate(["It's", 'Rock'])] + [m.record(title='Unknown Genre', album='', artist='', path='', rid=-1 & 0xffffffff)]
    m.genre_songs[('Rock', 0)] = [m.song('A', artist='Ann', album='One', rid=811), m.song('B', artist='Bob', album='one', rid=812), m.song('C', artist='ann', album='Two', rid=813)]
    m.genre_songs[("It's", 0)] = [m.song('D', artist='Dee', album='Three', rid=814)]
    music(m); m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    before = rows_of(m.paint()[0])
    for _ in range(8): tick(m)
    texts, _, blits = m.paint()
    subs = [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if r[1] >= BARH and t not in ("It's", 'Rock', 'Unknown Genre')]
    qs = [q for q in m.queries if 'group by' in q and 'style' in q]
    expect(before == ["It's", 'Rock', 'Unknown Genre'] and not blits and all(r[0] == O['IP_TEXT_X'] for t, r in texts if t in ("It's", 'Rock')), f'the genre rows: no cover, the name at the text inset ({before})')
    expect(subs == ['1 Artist, 1 Album', '2 Artists, 2 Albums', '0 Artists, 0 Albums'], f'the small line counts the genre\'s artists and albums ({subs})')
    expect("select * from songtable where style like 'It''s' group by songer COLLATE NOCASE" in qs and "select * from songtable where ifnull(style,'')='' group by album COLLATE NOCASE" in qs, f'the stock genre condition, quotes doubled; Unknown Genre: no tag ({qs})')
    expect(rows_of(m.paint()[0]) == before, 'and the genre list is still the one shown')


def root_shortcut_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['First']); m.present.add('/mnt/mmc/m/0.flac'); m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'root has the six rows: Music, Cover Flow, Podcasts, Settings, Shuffle Songs, Now Playing')
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'the main menu Cover Flow row opens its own level (the albums query)')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'MENU returns to the main menu')
    m.turn(0, -(STEP_DEG + 5))
    music(m)
    m.calls = []; m.tap(CX, CY)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'Music > Cover Flow opens its own level (the albums query)')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0])[0] == m.tr('Cover Flow'), 'MENU returns to Music after Cover Flow')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'and MENU again to the main menu')
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    expect(m.played is not None and len(m.played[0]) == 1 and m.read_cstr(m.word(m.played[0][0] + O['REC_TITLE'])) == 'First' and m.mode == 2 and 'Now Playing' in texts_of(m.paint()), 'root Shuffle Songs starts the library queue')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0])[4] == m.tr('Shuffle Songs'), 'MENU returns to the root shuffle shortcut')


def now_row_tests(ctx):
    """The main menu has no Radio row. Its Now Playing row is shown only while something plays, and it opens the Pod's own Now Playing screen."""
    expect = ctx.expect
    m = machine(songs=['First']); m.status = 0; m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS if k != 'Now Playing'], 'nothing plays: no Now Playing row')
    expect(m.tr('Radio') not in rows_of(m.paint()[0]), 'the main menu has no Radio row')
    m = machine(songs=['First']); m.status = 2; m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'playing: the Now Playing row is there, last')
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    expect('Now Playing' in texts_of(m.paint()) and rows_of(m.paint()[0]) != [m.tr(k) for k in MAIN_KEYS], 'the row pushes the Pod\'s own Now Playing screen')


def menu_padding_tests(ctx):
    expect = ctx.expect
    for step in (0, 1, 2, 3, 4):
        m = machine(albums=[('Album', 'Artist')], artists=['Artist'], songs=['Song'], playlists=['List']); m.open(); m.timers = []; music(m)
        if step: m.turn(0, STEP_DEG * step + 5)
        if step: m.tap(CX, CY)
        texts = m.paint()[0]
        rows = [r for t, r in texts if BARH <= r[1] < 240 and r[0] in (O['IP_TEXT_X'], 10, O['IP_TALL_H'] + 8)]
        expected = O['IP_TALL_H'] + 8 if step == 3 else O['IP_TEXT_X']
        expect(rows and all(r[0] == expected for r in rows), f'level {step} aligns its text after the shared leading cover inset')
    m = machine(); m.open(); m.timers = []; m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    expect(all(r[0] == O['IP_TEXT_X'] for t, r in m.paint()[0] if t in ('Shuffle', 'Repeat')), 'Settings labels use the shared inset')
    m = machine(); m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    expect(any(t == m.tr('No albums') and r[0] == O['IP_TEXT_X'] for t, r in m.paint()[0]), 'empty messages use the shared inset')


def rich_rows_tests(ctx):
    expect = ctx.expect
    m = machine(songs=[f'Song {i:02d}' for i in range(12)]); m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    texts, fills, blits = m.paint()
    songs = [(t, r[:2]) for t, r in sorted(texts, key=lambda tr: tr[1][1]) if t.startswith('Song ')]
    subs = [r[:2] for t, r in sorted(texts, key=lambda tr: tr[1][1]) if t == 'Artist']
    expect([t for t, _ in songs] == [f'Song {i:02d}' for i in range(SONGS_N)] and [r for _, r in songs] == [(O['IP_TEXT_X'], row_y(i, SONGS_N) + 2) for i in range(SONGS_N)],
           f'Music > Songs: five two-line rows, no cover ({songs})')
    expect(subs == [(O['IP_TEXT_X'], row_y(i, SONGS_N) + O['IP_SONG_SUB_Y']) for i in range(SONGS_N)] and not blits, f'each row has the artist under the title, and no cover is drawn ({subs})')
    work = [x for _ in range(6) for x in tick(m) if x[0] in ('cc_build_open', 'loadLocalClassList') or x[:3] == ('bitmap_create_ex', O['IP_TALL_H'], O['IP_TALL_H'])]
    expect(not work, f'and the page timer does no cover work for a song list ({work})')
    m.turn(0, STEP_DEG * 9 + 5)
    texts, fills, _ = m.paint()
    expect('Song 09' in [t for t, r in texts] and 'Song 00' not in [t for t, r in texts], 'scrolling keeps the cursor visible in a nine-row window')
    cover_row_style_tests(ctx)


def cover_row_style_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles'), ('音楽', 'Artist'), ('Third', 'A'), ('Fourth', 'B')]); m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    texts, fills, _ = m.paint()
    sty = {t: s for (t, r), s in zip(texts, m.text_styles)}
    expect(sty.get('Kind of Blue') == 'label_ip_sel' and sty.get('Third') == 'label_ip_row' and sty.get('音楽') == 'label_ip_row', f'every album title is in the regular style, Latin or not, so a list never mixes weights ({sty})')
    expect(sty.get('Miles') == 'label_ip_subsel' and sty.get('A') == 'label_ip_small', 'the artist line stays regular')
    sel = 0   # the first row is selected
    seps = {f[2] for f in fills if f[0] == 0xffdddddd and f[1] == O['IP_TALL_H'] and f[4] == 1 and f[3] == 320 - O['IP_TALL_H']}
    last = O['IP_SCREEN_H'] - 1
    want = {BARH + (i + 1) * O['IP_TALL_H'] - 1 for i in range(O['IP_TALL_ROWS']) if i != sel and BARH + (i + 1) * O['IP_TALL_H'] <= O['IP_SCREEN_H'] - 1}
    expect(seps == want and last not in seps, f'a rule line under each unselected row from x IP_ROW_ART to the edge, none under the selected row or at the screen bottom ({sorted(seps)} vs {sorted(want)})')


def row_art_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Album', 'Artist')]); key = album_key('Artist', 'Album'); path = art_file(key)
    m.present.add(path); m.files[path] = 4096
    m.images['file://' + path] = (48, 48, bytes((50, 100, 150, 255)) * (48 * 48))
    m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    calls = tick(m) + tick(m)   # the rows' placeholder, then the row with its cover
    expect(any(c[0] == 'widget_load_image' and c[1] == 'file://' + path for c in calls), 'a visible album cover decodes on the page timer')
    m.calls = []; _, _, blits = m.paint()
    expect(row_px(m, blits) == bytes((50, 100, 150, 255)), 'the cached cover is drawn in its row')
    expect(not any(c[0] in ('widget_load_image', 'bitmap_create_ex', 'loadLocalClassList') for c in m.calls), 'paint performs no decode, allocation or query')

    albums = [(f'Album {i}', 'Artist') for i in range(14)]
    m = machine(albums=albums)
    for i in range(14):
        f = art_file(album_key('Artist', f'Album {i}'))
        m.present.add(f); m.files[f] = 4096
        m.images['file://' + f] = (48, 48, bytes((10 * i, 100, 150, 255)) * (48 * 48))
    m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    for _ in range(20): tick(m)
    loads = lambda cs: [c[1] for c in cs if c[0] == 'widget_load_image' and str(c[1]).startswith('file://')]
    seen = []
    for _ in range(4): m.turn(0, STEP_DEG + 5)
    for _ in range(30): tick(m)
    first = m.sel()[0][0][0]
    for _ in range(8):   # until the list scrolls one row
        m.turn(0, STEP_DEG + 5); seen += loads(tick(m))
        if m.sel()[0][0][0] != first: break
    for _ in range(30): seen += loads(tick(m))
    expect(len(seen) == 1, f'one row further down decodes exactly one new cover, the rest are cached ({len(seen)} loads)')
    seen = []
    for _ in range(3): m.turn(0, STEP_DEG + 5)   # scroll down past the four visible rows
    for _ in range(3): seen += loads(tick(m))
    for _ in range(20): seen += loads(tick(m))
    expect(len(seen) == len(set(seen)), f'scrolling down decodes no cover twice ({len(seen)} loads)')
    seen = []
    for _ in range(3): m.turn(0, -STEP_DEG - 5)  # back up: every row is cached
    for _ in range(20): seen += loads(tick(m))
    expect(not seen, f'scrolling back over decoded rows reuses their slots ({len(seen)} loads)')


def playlist_rows_tests(ctx):
    expect = ctx.expect
    m = machine(playlists=['Road', 'Gym'])
    m.playlist_songs = {7: [m.song(f'R{i}', album=f'Album {i}', rid=600 + i) for i in range(3)], 8: [m.song('G1', rid=610)]}
    m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    texts, _, blits = m.paint()
    expect(not blits and all(r[0] == O['IP_TEXT_X'] for t, r in texts if t in ('Road', 'Gym')), f'the iPod\'s playlist rows: no cover, the name at the text inset ({texts})')
    expect(m.tr('Playlists') not in [t for t, r in texts if r[1] >= BARH], 'no "Playlists" subtitle')
    work = [x for _ in range(8) for x in tick(m) if x[:3] == ('bitmap_create_ex', O['IP_TALL_H'], O['IP_TALL_H']) or x[0] == 'cc_build_open']
    texts, fills, blits = m.paint()
    subs = [(t, r[0], r[1]) for t, r in sorted(texts, key=lambda tr: tr[1][1]) if r[1] >= BARH and t not in ('Road', 'Gym')]
    expect([t for t, x, y in subs] == ['3 songs', '1 song'] and all(x == O['IP_TEXT_X'] for t, x, y in subs), f'the small line is the song count, under the name ({subs})')
    expect(not work and not blits, f'and nothing is decoded for a playlist row ({work})')
    expect(any(f[1] == 0 and f[3] == 320 and f[4] == 1 and f[2] == BARH + 2 * O['IP_TALL_H'] - 1 for f in fills), 'the hairline runs from the left edge under an unselected row')


def now_material_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['Song']); m.open(); m.timers = []
    A, R, W, HR = O['IP_ART'], O['IP_NP_REFLECT'], O['IP_NP_ART_W'], O['IP_NP_ART_HR']
    src = m.alloc(A * A * 4); dst = m.alloc(W * (W + R) * 4)
    for y in range(A):
        for x in range(A): m.setword(src + 4 * (y * A + x), 0xff000000 | x | y << 8)
    m.call(PSYMS['ip_tilt'], a0=src, a1=dst, count=80000000)
    pixel = lambda x, y: m.word(dst + 4 * (y * W + x))
    white = lambda x, y: pixel(x, y) & 0xffffff == 0xffffff
    col = lambda x: [y for y in range(W + R) if (pixel(x, y) >> 16 & 255) != 255]   # the source's blue is 0: any blue under 255 is cover or reflection
    cover = lambda x: [y for y in range(W + R) if pixel(x, y) >> 16 & 255 == 0]      # fully covered rows only
    near, far = cover(0), cover(W - 1)
    expect(near[0] <= 1 and near[-1] >= W - 2 and abs(far[0] - (W - HR) // 2) <= 1 and abs(far[-1] - (W + HR) // 2) <= 1,
           f'the near edge is {W} px tall from the top, the far edge {HR} px centred on the same line ({near[0]}..{near[-1]}, {far[0]}..{far[-1]})')
    expect(all(pixel(x, y) >> 24 == 255 for x in (0, 60, W - 1) for y in range(W + R)) and white(W - 1, 0) and white(W - 1, W + R - 1),
           'an opaque picture on the screen colour around the turned cover')
    expect(pixel(0, 60) & 255 <= 1 and pixel(W - 1, 60) & 255 >= A - 2 and pixel(0, W - 3) >> 8 & 255 >= A - 4 and pixel(0, 1) >> 8 & 255 <= 2,
           'the whole cover is shown: its left column at the near edge, its right one at the far edge, top to bottom')
    xs = [pixel(x, 60) & 255 for x in range(W)]
    expect(xs == sorted(xs) and xs[W // 2] < A // 2 - 4, f'the source columns run left to right, the far half narrower (perspective: the middle column is source {xs[W // 2]})')
    mix = lambda c, a: 255 + int((c - 255) * a / 255)
    refl = [pixel(0, y) for y in range(W, W + R)]
    expect(abs((refl[0] >> 8 & 255) - mix(A - 1, 77)) <= 3 and all(r >> 16 & 255 > 0 for r in refl), 'the reflection starts as the cover\'s last row, mirrored, 30 % opaque on white')
    rows = [r & 255 for r in refl]
    expect(rows == sorted(rows) and rows[-1] > 245, f'the reflection fades out to nearly white in {R} rows ({rows[-3:]})')
    expect(len(col(W - 1)) < len(col(0)), 'the reflection is shorter at the far edge')
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][0]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    m.mode = 2; m.calls = []
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect('widget_invalidate_force' in m.names(), 'a mode change invalidates Now Playing on the existing timer')
    # the mode marks: the built white glyph images, decoded once into page bitmaps (coverage mixed from white to the mark's colour), drawn at the top right
    MARK = (O['IP_MODE_X'], O['IP_MODE_Y'], O['IP_MODE_PX'], O['IP_MODE_PX'])
    expect(MARK[0] + MARK[2] == 313 and MARK[1] == 26, 'the mark is right aligned at x 313, top y 26')
    cover = {'ipod_mode_shuffle': 255, 'ipod_mode_repeat': 128, 'ipod_mode_repeat1': 64}
    for name, v in cover.items(): m.images[name] = (32, 32, bytes((v, v, v, 255)) * 1024)
    def mark(mode):
        m.mode = mode
        found = [b for b in m.paint()[2] if b[2] == MARK]
        return (m.u.mem_read(m.bitmaps[found[0][0]][0], 4), len(found)) if found else (None, 0)
    for mode, name in ((2, 'ipod_mode_shuffle'), (3, 'ipod_mode_repeat'), (1, 'ipod_mode_repeat1')):
        px, n = mark(mode)
        want = bytes([255 - cover[name]] * 3 + [255])
        expect(n == 1 and bytes(px) == want, f'play mode {mode}: its mark is drawn once, 16 px, from {name} (coverage {cover[name]} on white: {px})')
    expect(mark(0) == (None, 0), 'no mark in list play')
    before = len([c for c in m.calls if c[0] == 'bitmap_create_ex'])
    mark(2); mark(2)
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == before, 'the marks are made once, paint allocates nothing')
    m.images.pop('ipod_mode_shuffle'); m.mode = 0
    long =m.song('A very long title that must be clipped consistently')
    m.play([long], 0); m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    titles = [(t, r) for t, r in m.paint()[0] if r[1] == O['IP_NP_TITLE_Y']]
    expect(len(titles) == 1 and titles[0][0].endswith('…'), 'the bold title is drawn once and clipped')
    face = lambda: tuple(m.props.get((m.widgets['label_ip_np1'], f'style:{st}:font_name')) for st in ('normal', 'disable', 'focused'))
    expect(face() == ('lyrics',) * 3, 'a Latin title is in the bold face (lyrics.ttf, ly_title_face)')
    m.play([m.song('晴天')], 0); m.call(PSYMS['ip_tick'], a0=0, count=40000000); m.paint()
    expect(face() == ('default',) * 3, 'a CJK title is in the default font (the bold face has no CJK)')
    m.props[(m.widgets['label_ip_np1'], 'style:normal:font_name')] = 'mark'
    m.paint(); m.paint()
    expect(face()[0] == 'mark', 'repaints of the same title restyle nothing')
    before = len([c for c in m.calls if c[0] == 'bitmap_create_ex'])
    m.paint(); m.paint()
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == before, 'painting allocates no cover bitmap')
    n = machine(songs=['Song']); n.fail_projection = True; n.open(); n.timers = []
    n.play([n.class_lists[O['CLASS_ALL_SONGS']][0]], 0); n.turn(0, STEP_DEG * 5 + 5); n.tap(CX, CY)
    tick(n, 500); tick(n, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])
    blits = n.paint()[2]
    COVER = (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_NP_ART_W'], O['IP_NP_ART_W'])
    expect([b[2] for b in blits if b[2][:2] == COVER[:2]] == [COVER], 'a picture that cannot be allocated: the cover flat at the near edge\'s size, no crash')


def classic_material_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []
    fills = m.paint()[1]
    selected = [f for f in fills if f[1] == 0 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < row_y(1)]
    expect(selected and selected[0][0] == 0xfff8dd9a and selected[-1][0] == 0xff814f15, 'selection has a highlight and dark bottom rule')
    header = [f for f in fills if f[1] == 0 and f[3] == O['IP_SPLIT_X'] and f[2] < BARH - 1]
    expect(len({f[0] for f in header}) >= 4, 'split header has the silver bevel stops')


def split_menu_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []
    for label in ('root', 'Music', 'Settings'):
        if label == 'Music': music(m)
        if label == 'Settings':
            m.tap(*m.polar(0, 85)); m.turn(0, 3 * STEP_DEG + 5); m.tap(CX, CY)
        texts, fills, _ = m.paint()
        expect(any(f[1] == 0 and f[3] == 160 and f[2] == 0 for f in fills), f'{label}: header stays in the left half')
        expect(all(r[0] + r[2] <= 160 for t, r in texts if r[1] < BARH), f'{label}: title and status stay in the left half')
        expect(not any(f[1] == 160 and f[3] == 1 and f[4] == 1 for f in fills), f'{label}: no divider, the pane is flush')


def i18n_tests(ctx):
    expect = ctx.expect
    src = open(os.path.join(ROOT, 'patch', 'ipod.c')).read()
    keys = set(re.findall(r'TR\("([^"]+)"\)', src)) | set(MAIN_KEYS) | set(SET_KEYS)
    missing = [k for k in keys if k not in pod_i18n.TEXT and k not in pod_i18n.STOCK]
    expect(not missing, f'every text of the page is a key of ours or a stock key ({missing})')
    font = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    expect(StbText(font, 15).layout('-123:45')[1] <= 50, 'a long remaining time fits its 50 px column at 15 px')
    for loc in pod_i18n.LOCALES:
        for key in MAIN_KEYS + MUSIC_KEYS + SET_KEYS:
            s = pod_i18n.TEXT[key][pod_i18n.table_for(loc)] if key in pod_i18n.TEXT else key
            expect(StbText(font, 18).layout(s)[1] > 0, f"{loc} {key} has measurable glyphs")
    over = []
    for loc in pod_i18n.LOCALES:
        w = lambda s, px, bold=True: StbText(font, px).layout(s)[1]   # rows 18, titles 16, values 16 (the device font, Inter Medium)
        box = O['IP_SPLIT_X'] - O['IP_TEXT_X'] - 22
        for k in [x for x in MAIN_KEYS + MUSIC_KEYS if x != 'cdrippersettings']:   # the split menus' rows (the stock Settings key is translated by the stock table: not measured here)
            if w(pod_i18n.tr(loc, k), 18) > box: over.append((loc, k, w(pod_i18n.tr(loc, k), 18)))
        title_split = O['IP_SPLIT_X'] - 8 - 27 - 8 - 12 - 6 - O['IP_TEXT_X']   # the title bar's room beside the play glyph and battery
        for k in ('Music',):
            if w(pod_i18n.tr(loc, k) if k != 'Music' else 'Music', 16) > title_split: over.append((loc, 'title ' + k))
        for k in ('Albums', 'Artists', 'Songs', 'Playlists', 'Now Playing', 'Cover Flow'):
            if w(pod_i18n.tr(loc, k), 16) > O['IP_W'] - 8 - 27 - 8 - 12 - 6 - O['IP_TEXT_X']: over.append((loc, 'title ' + k))
        if w(pod_i18n.tr(loc, 'Not Playing'), 16) > 300: over.append((loc, 'Not Playing'))
        for k, v in (('Shuffle', ('Off', 'Songs')), ('Repeat', ('Off', 'One', 'All')), ('Appearance', ('Light', 'Dark'))):
            vw = max(w(pod_i18n.tr(loc, x), 16, False) for x in v)
            if w(pod_i18n.tr(loc, k), 18) > O['IP_SPLIT_X'] - 2 * O['IP_TEXT_X'] - min(72, vw) - 12 or vw > 72: over.append((loc, 'row ' + k, w(pod_i18n.tr(loc, k), 18), vw))
    over = sorted(set(over))
    expect(over == [('ge_DE', 'row Repeat', 92, 46), ('po_PL', 'row Repeat', 74, 68), ('ru_RU', 'Shuffle Songs', 146), ('ru_RU', 'row Appearance', 98, 57), ('ru_RU', 'row Shuffle', 97, 42), ('sp_ES', 'Shuffle Songs', 153), ('sp_ES', 'row Repeat', 52, 81), ('sp_ES', 'row Shuffle', 66, 81)], f'at 18 px (Inter Medium) these labels ellipsize (the 130 px menu box, or the room a Settings value leaves; the rest of the 13 languages fit): {over}')
    spanish = pod_i18n.tr('sp_ES', 'Shuffle Songs')
    while StbText(font, 18).layout(spanish)[1] > O['IP_SPLIT_X'] - O['IP_TEXT_X'] - 22:
        spanish = spanish[:-2] + '…' if spanish.endswith('…') else spanish[:-1] + '…'
    expect(spanish.endswith('…') and StbText(font, 18).layout(spanish)[1] <= O["IP_SPLIT_X"] - O["IP_TEXT_X"] - 22, 'Spanish Shuffle Songs clips within its box')
    expect(pod_i18n.TEXT['Not Playing']['en_US'] == 'Not Playing' and all(pod_i18n.TEXT['Not Playing'][l] for l in pod_i18n.LOCALES), '"Not Playing" is translated into all 13 languages')


class Drag:
    """One touch on the ring, move by move, with its own event times: Drag(m, deg).go(ddeg, dt) turns by ddeg degrees dt ms after the last event."""
    def __init__(self, m, deg, r=100, t=1000):
        self.m, self.deg, self.r, self.t = m, deg, r, t
        m.ptr('down', *m.polar(deg, r), t)

    def go(self, ddeg, dt):
        self.deg += ddeg; self.t += dt
        self.m.ptr('move', *self.m.polar(self.deg, self.r), self.t)

    def up(self): self.m.ptr('up', *self.m.polar(self.deg, self.r), self.t + 16)


def feel_tests(ctx):
    """Reversal hysteresis, the chord dead zone, the 20 degree step with carry, the tiers on long lists, the hard stop at the ends (docs/modules/ipod.md "The wheel")."""
    expect = ctx.expect

    def menu():
        m = machine(); m.open(); m.timers = []
        return m

    def menu_row(m):
        m.clock += 1000
        ys = [f[2] for f in m.paint()[1] if f[4] == 1 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < 240]
        return row_of(min(ys)) if ys else None

    def songs(n):
        m = machine(songs=[f'Song {i:03d}' for i in range(n)]); m.open(); m.timers = []
        music(m)
        m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
        return m

    def song_sel(m):
        m.clock += 1000
        texts, fills, _ = m.paint()
        ys = [f[2] for f in fills if f[4] == 1 and f[3] == 320 and f[2] >= BARH and f[0] & 0xffffff == 0xf8dd9a]   # the selection's top line
        return int(rows_of(texts)[0][5:]) + row_of(min(ys), SONGS_N)

    # the step: 20 degrees, the leftover carries
    m = menu()
    d = Drag(m, 0)
    for _ in range(19): d.go(1, 100)
    d.up()
    expect(menu_row(m) == 0, 'a 19 degree turn is no step')
    m = menu(); d = Drag(m, 0)
    for _ in range(21): d.go(1, 100)
    d.up()
    expect(menu_row(m) == 1, 'a 21 degree turn is one step')
    m = menu(); d = Drag(m, 0)
    d.go(25, 100); r1 = menu_row(m); d.go(17, 100); d.up()
    expect(r1 == 1 and menu_row(m) == 2, f'25 degrees then 17: the leftover 5 carries into the second step ({r1}, {menu_row(m)})')

    # reversal hysteresis: 8 degrees of reverse travel are swallowed, then the accumulator starts again at 0
    m = menu(); d = Drag(m, 0)
    for _ in range(11): d.go(2, 100)
    expect(menu_row(m) == 1, 'forward 22 degrees: row 1')
    for _ in range(11): d.go(-2, 100)
    expect(menu_row(m) == 1, '22 degrees back: 8 swallowed, 14 counted: still row 1')
    for _ in range(4): d.go(-2, 100)
    expect(menu_row(m) == 0, '30 degrees back: 8 swallowed, 22 counted: one step up')
    m = menu(); d = Drag(m, 0)
    for _ in range(11): d.go(2, 100)
    for _ in range(5):
        for _ in range(3): d.go(-2, 100)
        for _ in range(3): d.go(2, 100)
    expect(menu_row(m) == 1, 'a 6 degree jitter at the turnaround, five times over, steps nothing')
    for _ in range(6): d.go(2, 100)
    expect(menu_row(m) == 1, 'and the jitter took no forward travel either: 12 more degrees is still row 1 (2 + 12 < 20)')
    for _ in range(4): d.go(2, 100)
    expect(menu_row(m) == 2, 'and 8 more is the next step')

    # the chord dead zone
    def chord(y, x0=-60, x1=60):
        m = menu(); m.ptr('down', CX + x0, CY + y, 1000); m.ptr('move', CX + x1, CY + y, 1100)
        row = menu_row(m)
        return m, row
    m, row = chord(-10)
    expect(row == 0, 'a move whose chord passes 10 px from the centre turns nothing')
    m, row = chord(-5)
    expect(row == 0, 'nor one that passes 5 px from it')
    m, row = chord(-12)
    expect(row == 5, f'a chord 12 px from the centre reaches the last root row ({row})')
    m = menu(); m.ptr('down', CX - 60, CY - 10, 1000); m.ptr('move', CX + 60, CY - 10, 1100)
    x, y = 60, -10
    a = math.degrees(math.atan2(x, -y)); r = math.hypot(x, y)
    for i in range(1, 6):
        px, py = r * math.sin(math.radians(a + 5 * i)), -r * math.cos(math.radians(a + 5 * i))
        m.ptr('move', CX + round(px), CY + round(py), 1100 + 100 * i)
    expect(menu_row(m) == 1, 'after the rejected chord the same touch goes on from the new point: 25 degrees, one step')
    m = menu(); m.ptr('down', CX - 30, CY, 1000); m.ptr('move', CX + 30, CY + 4, 1100)
    expect(menu_row(m) == 0, 'a drag that begins on the centre button still does nothing')

    # tiers
    expect([m.call(PSYMS['ip_tier_rows'], a0=n, a1=i) for n, i in ((8, 0), (8, 5), (16, 5), (16, 99), (17, 0), (17, 1), (17, 2), (17, 3), (17, 4), (17, 5), (17, 6), (17, 7), (17, 9), (3000, 20))]
          == [1, 1, 1, 1, 1, 2, 3, 5, 8, 13, 21, 34, 34, 34], 'rows a step: 1 for 16 rows or fewer, else the tiers 1, 2, 3, 5, 8, 13, 21, 34 (the last holds)')
    m = songs(3000); d = Drag(m, 0)
    for _ in range(30): d.go(6, 16)
    expect(song_sel(m) == 9, f'a fast turn (375 deg/s): the first half second is one row per 20 degrees (row {song_sel(m)} = 9)')
    prev, deltas = 9, []
    for _ in range(300):
        d.go(6, 16); s = song_sel(m); deltas.append(s - prev); prev = s
        if s >= 2999: break
    expect(set(deltas) - {0} == {1, 2, 3, 5, 8, 13, 21, 34}, f'held fast, the rows a step climb through 1, 2, 3, 5, 8, 13, 21 to 34 ({sorted(set(deltas))})')
    first2 = next(i for i, x in enumerate(deltas) if x >= 2)
    expect(560 <= (30 + first2) * 16 <= 700, f'the first 2-row step comes about half a second after the speed passed 180 deg/s (at {(30 + first2) * 16} ms)')
    # the instantaneous speed is clamped at 400 deg/s (IP_VMAX) before the 0.15 smoothing: 1500 deg/s reaches 180 deg/s smoothed on the 5th move (40 ms), not the 1st
    m = songs(3000); d = Drag(m, 0); prev = 0; at = None
    for i in range(200):
        d.go(12, 8); s = song_sel(m)
        if s - prev >= 2: at = (i + 1) * 8; break
        prev = s
    expect(at is not None and 530 <= at <= 560, f'1500 deg/s: the clamp and the 0.15 smoothing delay the speed passing 180 deg/s to the 5th move: first 2-row step at {at} ms (540 expected, 500 unclamped)')
    # back to 1 when the speed drops
    m = songs(100); d = Drag(m, 0)
    for _ in range(60): d.go(6, 16)
    prev = song_sel(m); late = []
    for i in range(30):
        d.go(3, 100); s = song_sel(m); late.append(s - prev); prev = s
    expect(max(late[12:]) <= 1 and max(late) >= 1, f'the speed falls below the threshold: back to one row a step within a dozen moves ({late})')
    # a pause resets it
    m = songs(100); d = Drag(m, 0)
    for _ in range(60): d.go(6, 16)
    prev = song_sel(m); d.go(6, 300); prev = song_sel(m); after = []
    for _ in range(25):
        d.go(6, 16); s = song_sel(m); after.append(s - prev); prev = s
    expect(max(after) == 1, f'a pause over 250 ms resets the tier: one row a step again ({sorted(set(after))})')
    # a direction change resets it
    m = songs(100); d = Drag(m, 0)
    for _ in range(60): d.go(6, 16)
    prev = song_sel(m); after = []
    for _ in range(25):
        d.go(-6, 16); s = song_sel(m); after.append(s - prev); prev = s
    expect(min(after) >= -1 and min(after) == -1 and sum(after) < -5, f'turning back: the tier is gone, one row a step the other way ({sorted(set(after))})')
    # clamped at the end
    m = songs(40); d = Drag(m, 0)
    for _ in range(150): d.go(6, 16)
    expect(song_sel(m) == 39, f'the last row stops it ({song_sel(m)})')
    # a short list (the main menu) moves one row a step at any speed
    m = menu(); d = Drag(m, 0); prev = 0; deltas = []
    for _ in range(40):
        d.go(6, 16); s = menu_row(m); deltas.append(s - prev); prev = s
    expect(max(deltas) == 1 and prev == 5,'the short main menu list: one row a step at 375 deg/s')

    # the ends of a list: a hard stop, as the iPod (no wrap, no bump, the page timer untouched)
    m = menu(); calls = []
    d = Drag(m, 0)
    for _ in range(4): d.go(-6, 100); calls += m.calls
    names = [c_[0] for c_ in calls]
    ys = lambda: min(f[2] for f in m.paint()[1] if f[4] == 1 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < 240)
    expect(menu_row(m) == 0 and ys() == BARH, f'turning back past the start: the first row stays selected, the rows stay home ({ys()})')
    expect('timer_remove' not in names and 'timer_add' not in names, 'a stop at the start touches no timer')
    m = menu(); d = Drag(m, 0)
    for _ in range(60): d.go(6, 100)
    expect(menu_row(m) == 5, 'the last row')
    m.calls = []; d = Drag(m, 0); d.go(20, 100); d.go(20, 100)
    ys2 = [f[2] for f in m.paint()[1] if f[4] == 1 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < 240]
    expect(menu_row(m) == 5 and min(ys2) == row_y(5), f'turning on past the end: the last row stays selected ({min(ys2)})')
    expect('timer_remove' not in m.names() and 'timer_add' not in m.names(), 'a stop at the end touches no timer')


def with_covers(n_albums=10, n_art=8, ramp=False, worker=False):
    """A machine with n_albums albums, the first n_art of them with a Cover Flow cache file holding a solid picture of their own (ramp: the red channel rises from left to
    right, the same ramp on every cover, so the pan's place can be read from the frame); the ticks and paints of the pane."""
    m = machine(albums=[(f'Album {i}', f'Artist {i}') for i in range(n_albums)])
    m.thread_ok = worker   # the transient extraction needs the shared worker: without a thread the rotation uses the 168 px files at once (the sharp tier has its own tests)
    m.urls = {}
    for i in range(n_art):
        key = album_key(f'Artist {i}', f'Album {i}'); path = art_file(key)
        m.present.add(path); m.files[path] = 4096
        m.images['file://' + path] = (168, 168, (b''.join(bytes(((255 if x // 2 % 2 else 0) if ramp == 'comb' else x * 255 // 167, 200 - 20 * i, 90, 255)) for x in range(168)) * 168) if ramp else bytes((10 + 25 * i, 200 - 20 * i, 90, 255)) * (168 * 168))
        m.urls['file://' + path] = i
    m.open(); m.timers = []
    return m


def settle(m):
    """Past a level slide and the title bar's drop after it (a page of its own opened or closed from a split menu)."""
    return [x for _ in range(3) for x in tick(m, 300)]


def tick(m, ms=None):
    """One run of the page timer's callback (time_now_ms advanced by ms first, by default the interval it runs at): its calls, each image load as
    ('widget_load_image', url, the bitmap it was decoded into)."""
    m.clock += O['IP_DRIFT_MS'] if ms is None else ms
    n = len(m.load_into)
    m.call(PSYMS['ip_tick'], a0=0, count=60000000)
    into = iter(m.load_into[n:])
    return [x + (next(into)[1],) if x[0] == 'widget_load_image' else x for x in m.calls]


def pane_frame(m):
    """One paint: the pane's blits (bitmap, src window, dst) and the loads paint made."""
    loads = len(m.loads)
    m.paint()
    return [b for b in m.blits if b[2] == PANE], len(m.loads) - loads


def pane_loads(c, m):
    """The albums (with_covers index) whose cache file a tick decoded for the pane (not the Now Playing cover), the stock disc as 'disc'."""
    pane = [b for b, (_, w, h) in m.bitmaps.items() if w == h == O['IP_PANE_ART']]
    return [m.urls.get(x[1], 'disc' if x[1] == 'ipod_placeholder' else x[1]) for x in c if x[0] == 'widget_load_image' and x[2] in pane]


def pane_tests(ctx):
    """The split pages' cover pane (docs/modules/ipod.md "The cover pane"): sub-pixel pan frames built on the timer, a steady cadence, only the pane's rectangle invalidated."""
    expect = ctx.expect
    FAST, SLOW, ART, R = O['IP_PAN_MS'], O['IP_TICK_MS'], O['IP_PANE_ART'], O['IP_PANE_R']
    X0 = (ART - PANE[2] - R) // 2
    PAN, HOLD, FADE, FT = O['IP_PANE_PAN_MS'], O['IP_PANE_HOLD_MS'], O['IP_PANE_FADE_MS'], O['IP_FADE_TICK_MS']
    expect(ART == -(-PANE[3] * 110 // 100) and R == ART - PANE[3] and FAST == 40 and (PAN, HOLD, FADE, FT, O['IP_DRIFT_MAX_MS']) == (7500, 6000, 1500, 50, 250)
           and PANE[0] == O['IP_SPLIT_X'] and PANE[0] + PANE[2] == 320,
           'the reference\'s artwork pane: a cover pans for 7.5 s, the next fades in every 6 s over 1.5 s; 40 ms frames while it pans (50 ms in a fade), a step at most 250 ms')
    def lerp8(u, v, f):
        lane = lambda mask: (((u & mask) * (256 - f) + (v & mask) * f) >> 8) & mask
        return lane(0xff00ff) | lane(0xff00)
    def pos256(ms): return R * 256 * ms // PAN
    def row(m, ptr, index, n): return struct.unpack(f'<{n}I', bytes(m.u.mem_read(ptr + 4 * index, 4 * n)))
    def mix_frame(m):
        b = pane_frame(m)[0]
        return m.bitmaps[b[0][0]][0] if b else None
    def slot0(m): return next(ptr for ptr, w, h in m.bitmaps.values() if w == h == ART)
    def expect_frame(m, ms, label):
        """The pane's frame against the reference lerp of the first cover's bitmap at the pan's place after ms of time shown (a few rows, every column)."""
        p = pos256(ms); xa = X0 + (p >> 8); f = p & 255
        ptr, frame = slot0(m), mix_frame(m)
        bad = [(y, x) for y in (0, 99, 239) for x, (got, a, b) in enumerate(zip(row(m, frame, y * PANE[2], PANE[2]), row(m, ptr, (y + R // 2) * ART + xa, PANE[2]), row(m, ptr, (y + R // 2) * ART + xa + 1, PANE[2])))
               if got != 0xff000000 | lerp8(a, b, f)]
        return not bad, bad[:3], p
    m = with_covers(ramp=True)
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    expect(('timer_add', PSYMS['ip_tick'], FAST) in m.calls and len(m.timers) == 1, f'on the main menu, in front: the one page timer ticks at {FAST} ms')
    expect(not pane_frame(m)[0], 'the pane is plain until a cover is decoded')
    c = tick(m, FAST)
    first = pane_loads(c, m)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in c and len(first) == 1 and first[0] in range(8), f'tick 1: a random album with a cached cover is decoded ({first})')
    expect(('bitmap_create_ex', ART, ART) in [x[:3] for x in c], f'into a {ART} px bitmap (the pane\'s height zoomed 110%)')
    # sub-pixel pan: every frame is the reference lerp of the source at the pan's place, which advances a little every tick
    ok_all, ps, frames = True, [], []
    for n in range(1, 101):
        c = tick(m, FAST)
        ok, bad, p = expect_frame(m, n * FAST, n)
        ok_all &= ok; ps.append(p)
        if not ok: expect(False, f'tick {n}: the frame is the linear mix of each source column and its right neighbour by the fraction ({bad})'); break
        frames.append(bytes(m.u.mem_read(mix_frame(m), 4 * 160)))
        expect(not [x for x in c if x[0] in ('bitmap_create_ex', 'widget_load_image')] or n < 3 or 73 <= n <= 77, f'tick {n}: a pan frame allocates and decodes nothing')
    expect(ok_all, f'100 consecutive frames are exactly the reference lerp of the source at their place (fractions {sorted({p & 255 for p in ps})[:6]} ...)')
    deltas = [b - a for a, b in zip(ps, ps[1:])]
    expect(min(deltas) > 0 and max(deltas) - min(deltas) <= 1 and len({p & 255 for p in ps}) > 80 and max(deltas) < 256, f'monotonic fractional steps of {min(deltas)}-{max(deltas)}/256 px a frame, no whole-pixel pattern ({len({p & 255 for p in ps})} different fractions)')
    mc = with_covers(ramp='comb'); mc.call(PSYMS['ip_first'], a0=0, count=40000000); tick(mc, FAST)
    seen = []
    for n in range(60):
        tick(mc, FAST); seen.append(bytes(mc.u.mem_read(mix_frame(mc), 4 * 160 * 3)))
    expect(len(set(seen)) == len(seen), 'every 40 ms tick paints a different frame on a high-contrast cover (an even cadence: no ticks that move nothing, as the whole-pixel pan did two ticks in three)')
    # one more tick: a pan frame invalidates only the pane's rectangle, and paint copies the frame 1:1 over it
    m.inval = []
    tick(m, FAST)
    rects = [r for w, r in m.inval]
    expect(rects and all(r == (PANE[0], 0, PANE[2], PANE[3]) for r in rects), f'a pan frame invalidates only the pane\'s rectangle ({rects})')
    b = pane_frame(m)[0]
    expect(len(b) == 1 and b[0][1] == (0, 0, PANE[2], PANE[3]) and b[0][2] == PANE, 'paint: one 1:1 copy of the frame (source and destination 160 x 240)')
    # a paint whose clip is only the pane's rectangle paints the pane and leaves the menu out
    saved = [m.word(m.canvas + O['CANVAS_CLIP'] + i * 4) for i in range(4)]
    m.setword(m.canvas + O['CANVAS_CLIP'], PANE[0])
    texts, fills, blits = m.paint()
    m.setword(m.canvas + O['CANVAS_CLIP'], saved[0])
    expect(not texts and [b for b in blits if b[2] == PANE] and not [f for f in fills if f[1] < PANE[0] and f[3] < 320], 'with only the pane dirty, the menu text and rows are not painted again')
    full = m.paint()
    expect(full[0] and 'Music' in [t for t, _ in full[0]], 'a full paint still draws the whole page (the recorded model is intact)')
    # a screen that is off does no pan work
    m.screen(False); m.calls = []; m.inval = []
    c = tick(m, FAST)
    expect(('timer_modify', 0x777, 1000) in c and not m.inval and not [x for x in c if x[0] in ('widget_load_image', 'bitmap_create_ex', 'loadLocalClassList')],
           'screen off: the timer slows to 1 s, no frame, no invalidate, no decode, no query')
    before_frame = bytes(m.u.mem_read(mix_frame(m), 4 * 160))
    tick(m, FAST)
    expect(bytes(m.u.mem_read(mix_frame(m), 4 * 160)) == before_frame, 'and the frame does not change')
    m.screen(True); tick(m, 2000)
    expect(('timer_modify', 0x777, FAST) in m.calls or m.inval, 'lit again: the pan resumes at its pace (a long gap moves it one capped step)')
    m = with_covers()
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    log = []
    cur = FAST
    for t in range(400):   # 40 s of 100 ms samples
        c = tick(m)
        mods = [x[2] for x in c if x[0] == 'timer_modify']
        if mods: cur = mods[-1]
        log.append((pane_loads(c, m), cur == FT, [x for x in c if x[0] == 'widget_invalidate_force']))
    fade = [x[1] for x in log]
    runs = [i for i in range(len(fade)) if fade[i] and (i == 0 or not fade[i - 1])]
    expect(5 <= len(runs) <= 7 and all(12 <= sum(fade[r:r + 20]) <= 16 for r in runs[:5]) and runs[0] in range(56, 64) and all(b - a in (59, 60, 61) for a, b in zip(runs, runs[1:])),
           f'a cross-fade of 1.5 s starts every 6 s (at ticks {runs[:4]})')
    decodes = [i for i, x in enumerate(log) if x[0]]
    expect(5 <= len(decodes) <= 8 and not any(any(fade[max(0, i - 3):i + 3]) for i in decodes) and all(len(log[i][0]) == 1 for i in decodes),
           f'one cover is decoded for each fade, 3 s after the last one began, never during a fade ({decodes})')
    # the direction of the pan: the first cover left to right, the next one right to left (read from a smooth ramp cover)
    m = with_covers(ramp=True)
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    tick(m)
    reds = []
    for t in range(140):
        tick(m)
        reds.append(row(m, mix_frame(m), 120 * PANE[2] + 80, 1)[0] & 255)
    expect(reds[10] < reds[50] and reds[80] > reds[120], f'the first cover pans left to right, the next one right to left (every other cover reverses) ({reds[10]} {reds[50]} {reds[80]} {reds[120]})')
    expect(all(abs(reds[i + 1] - reds[i]) <= 3 for i in range(60) if i + 1 not in range(56, 80)), 'in small steps')
    # the menu's shadow on the pane's left edge: a straight-alpha black strip drawn over the pane; darkest at x 160, falling off to 0, the cover beyond it unchanged
    m3 = with_covers(); m3.call(PSYMS['ip_first'], a0=0, count=40000000)
    SW = O['IP_SHADOW_W']
    table = [int(v) for v in re.search(r'ip_shadow_alpha\[IP_SHADOW_W\] = \{([^}]*)\}', open(os.path.join(ROOT, 'patch', 'ipod.c')).read())[1].split(',')]
    expect(len(table) == SW == 10 and table == sorted(table, reverse=True) and 120 <= table[0] <= 140 and 0 < table[-1] <= 8, f'the shadow: {SW} columns, 52 % black at the edge, falling smoothly ({table})')
    plain = m3.paint()[2]
    shadow = [i for i, b in enumerate(plain) if b[2] == (PANE[0], 0, SW, PANE[3])]
    expect(len(shadow) == 1 and plain[shadow[0]][1] == (0, 0, SW, PANE[3]), 'the plain pane (no cover yet) has the shadow drawn over it, full height')
    seen = 0
    for n in range(80):
        tick(m3)
        blits = m3.paint()[2]
        cover = [i for i, b in enumerate(blits) if b[2] == PANE]
        sh = [i for i, b in enumerate(blits) if b[2] == (PANE[0], 0, SW, PANE[3])]
        if not cover: continue
        expect(len(sh) == 1 and sh[0] > cover[0], 'the shadow is drawn once, after the cover')
        ptr, bw, bh = m3.bitmaps[blits[sh[0]][0]]
        words = [[m3.word(ptr + 4 * (y * bw + x)) for x in range(SW)] for y in (0, 100, PANE[3] - 1)]
        alpha = [w >> 24 for w in words[0]]
        flat = all(w == words[0] for w in words) and all(w & 0xffffff == 0 for w in words[0])
        cptr, cw, ch = m3.bitmaps[blits[cover[0]][0]]
        sx, sy = blits[cover[0]][1][:2]
        colour = m3.word(cptr + 4 * (sy * cw + sx))
        under = lambda x: [(colour >> k & 255) for k in (0, 8, 16)]
        shown = [[c * (255 - (alpha[x] if x < SW else 0)) // 255 for c in under(x)] for x in range(14)]   # what the canvas' blend leaves of the cover next to the menu
        dark = [sum(under(0)) - sum(s) for s in shown]
        ok = flat and alpha == table and dark[0] == max(dark) and all(a >= b for a, b in zip(dark, dark[1:])) and dark[0] > 0.45 * sum(under(0)) and dark[SW] == 0 == dark[13] and shown[SW] == under(SW)
        seen += 1
        expect(ok, f'the column at x 160 is darkest, the darkening falls to 0 by x 170 and the cover beyond is unchanged ({dark})')
        if not ok or seen > 12: break
    expect(seen > 5, 'checked over the cover')
    # a stall: the step is capped, so the cover does not jump
    m2 = with_covers(ramp=True); m2.call(PSYMS['ip_first'], a0=0, count=40000000)
    for _ in range(10): tick(m2, FAST)
    r0 = row(m2, mix_frame(m2), 120 * PANE[2] + 80, 1)[0] & 255
    tick(m2, 10000)
    r1 = row(m2, mix_frame(m2), 120 * PANE[2] + 80, 1)[0] & 255
    expect(abs(r1 - r0) <= 1, f'a tick 10 s late moves at most one capped step ({r0} -> {r1})')
    # a track plays from a cached album: its cover fades in at once, stays, and stops the rotation
    m = with_covers(ramp=True); m.call(PSYMS['ip_first'], a0=0, count=40000000)
    for _ in range(10): tick(m)
    m.play([m.song('T', artist='Artist 3', album='Album 3')], 0)
    got, fades, cur = [], 0, FAST
    for _ in range(30):
        c = tick(m); got += pane_loads(c, m)
        mods = [x[2] for x in c if x[0] == 'timer_modify']
        if mods: cur = mods[-1]
        fades += cur == FT
    expect(got.count(3) == 1 and 12 <= fades <= 18, f'a track of Album 3 plays: its cover is decoded once and fades in over 1.5 s ({got}, {fades} fade ticks)')
    later = [x for _ in range(120) for x in pane_loads(tick(m), m)]
    expect(not later, 'and nothing else is decoded for 12 s: the playing cover stays')
    reds = []
    for _ in range(160):
        c = tick(m); reds.append(row(m, mix_frame(m), 120 * PANE[2] + 80, 1)[0] & 255)
        cur = ([x[2] for x in c if x[0] == 'timer_modify'] or [cur])[-1]
    expect(len(set(reds)) == 1 and cur == O['IP_TICK_MS'], f'once faded in it stays still, no pan, at the slow pace ({sorted(set(reds))}, {cur} ms)')
    m.play([m.song('U', artist='Artist 5', album='Album 5')], 0)
    expect(5 in [x for _ in range(4) for x in pane_loads(tick(m), m)], 'the next track from another album: that album\'s cover')
    m.play([m.song('V', artist='Nobody', album='Uncached')], 0)
    got = [x for _ in range(80) for x in pane_loads(tick(m), m)]
    expect(got and all(g in range(8) for g in got), f'a track whose album has no cached cover: the random rotation resumes ({got})')
    # the interval: slow elsewhere, fast again on the main menu
    m = with_covers()
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    tick(m); tick(m)
    m.tap(CX, CY); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    expect(('timer_modify', 0x777, O['IPCF_FRAME_MS']) in m.calls, 'a list opens: the existing timer briefly accelerates to load its visible covers')
    c = tick(m)
    expect(not [x for x in c if x[0] == 'timer_modify' or x[0] == 'widget_load_image' and x[1] != 'ipod_placeholder'],
           f'on a list the tick decodes no pane cover (only the rows\' placeholder, once) and the interval stays ({c})')
    m.tap(*m.polar(0, 85)); got = list(m.calls) + settle(m)
    expect(('timer_modify', 0x777, FAST) in got, f'MENU to Music resumes the pane at {FAST} ms once its title bar has dropped in')
    m.tap(*m.polar(0, 85))
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in tick(m), 'and a new random cover is chosen (the album query runs again)')
    m.top_main = 0
    c = tick(m)
    expect(('timer_modify', 0x777, SLOW) in c and not [x for x in c if x[0] in ('widget_load_image', 'loadLocalClassList')], 'another window in front: slow, and nothing is decoded or queried')
    m.top_main = WIN
    c = tick(m)
    expect(('timer_modify', 0x777, FAST) in c, 'in front again: fast')
    m.calls = []; m.fire(EVT_BG, WIN)
    expect(('timer_remove', 0x777) in m.calls, 'to the background: the timer goes (nothing runs behind another page)')
    m.calls = []; m.fire(EVT_FG, WIN)
    expect(('timer_add', PSYMS['ip_first'], O['IP_FIRST_MS']) in m.calls, 'and comes back with the page')
    c = fired(m, 'ip_first')
    expect(('timer_add', PSYMS['ip_tick'], FAST) in c, 'at the fast interval')
    # random: another seed, another cover
    got = []
    for seed in (3, 5, 7):
        m = with_covers(); m.seed = seed
        m.call(PSYMS['ip_first'], a0=0, count=40000000)
        got.append(pane_loads(tick(m), m))
    expect(len(set(map(tuple, got))) > 1, f'another seed, another cover ({got})')
    # no cached covers: the placeholder, still, at the slow tick; no albums: the placeholder too
    for n_albums, what in ((10, 'albums without cached art'), (0, 'no albums')):
        m = with_covers(n_albums, 0)
        m.call(PSYMS['ip_first'], a0=0, count=40000000)
        c0 = c = tick(m)
        b, _ = pane_frame(m)
        expect(pane_loads(c, m) == ['disc'] and len(b) == 1 and b[0][1] == (0, 0, PANE[2], PANE[3]) and row(m, mix_frame(m), 0, 160) == tuple(0xff000000 | w for w in row(m, slot0(m), (R // 2) * ART + X0 + R // 2, 160)) , f'{what}: the placeholder, in the middle of the margin ({pane_loads(c, m)})')
        f0 = bytes(m.u.mem_read(mix_frame(m), 4 * 160 * 240)); m.inval = []; c = tick(m) + tick(m, 5000)
        expect(('timer_modify', 0x777, SLOW) in c0 and bytes(m.u.mem_read(mix_frame(m), 4 * 160 * 240)) == f0 and not m.inval and not pane_loads(c, m), 'and it stands still (no frame, no repaint), at the slow tick, decoded once')
    # a cover that cannot be decoded falls back to the disc (and is not tried again each tick)
    m = with_covers(3, 3)
    for u in list(m.images):
        if u.startswith('file://'): del m.images[u]
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    c = tick(m) + tick(m) + tick(m)
    expect(len(pane_frame(m)[0]) == 1 and pane_loads(c, m).count('disc') == 1, f'a cache file that does not decode: the stock disc, once ({pane_loads(c, m)})')
    # destroy frees the bitmaps
    m = with_covers()
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    for _ in range(4): tick(m)
    m.calls = []; m.fire(EVT_DESTROY, WIN)
    expect(m.names().count('bitmap_destroy') >= 2, f'destroy frees the page\'s bitmaps (the Now Playing cover and the pane\'s): {m.names().count("bitmap_destroy")}')

def shuffle_tests(ctx):
    expect = ctx.expect
    songs = [f'Song {i:02d}' for i in range(10)]
    def library(seed):
        m = machine(songs=songs); m.seed = seed; m.clock = 7 * seed
        for i in range(10): m.present.add(f'/mnt/mmc/m/{i}.flac')
        m.open(); m.timers = []
        m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)   # the main menu's Shuffle Songs row
        return m
    firsts = []
    for seed in (11, 12, 13, 14):
        m = library(seed)
        sp = [c for c in m.calls if c[0] == 'start_player']
        expect(m.opened == [] and ('loadLocalClassList', O['CLASS_ALL_SONGS']) in m.calls and len(sp) == 1 and sp[0][2:] == (O['CLASS_ALL_SONGS'], O['PLAY_MODE']),
               f'Shuffle Songs: the library query and the stock start_player with the library class ({sp})')
        pl = m.played
        firsts.append(sp[0][1])
        expect(pl and len(pl[0]) == 10 and pl[1] == sp[0][1] and 0 <= pl[1] < 10, f'the whole library is the queue, the first song a random one ({pl and pl[1]})')
        expect(('mclSetPlayMode', 2) in m.calls and m.mode == 2 and ('write_int_config', 2, 'PLAYSET', 'PLAYMODE') in m.calls, 'stock Shuffle (mode 2) is set the way the Play settings page does')
        expect('navigator_to_with_context' not in m.names() and 'shuffle_play' not in m.names(), 'no stock page opens')
        tick(m, 500); tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])   # the slide, then the title bar drops in
        texts = texts_of(m.paint())
        expect('Now Playing' in texts, 'the iPod\'s own Now Playing is in front')
        if seed == 11:
            x, y = m.polar(0, 85); m.tap(x, y)
            front = rows_of(m.paint()[0])
            expect(front == [m.tr(k) for k in MAIN_KEYS], f'MENU from Now Playing returns to the main menu, where Shuffle Songs was ({front[:2]})')
    expect(len(set(firsts)) >= 2, f'the first song differs with the random seed ({firsts})')
    # an empty library: the message, nothing played, the mode untouched
    m = machine(); m.open(); m.timers = []; m.mode = 1
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    expect(any(c[0] == 'toast' for c in m.calls) and 'start_player' not in m.names() and m.mode == 1 and 'mclSetPlayMode' not in m.names(), 'no songs: the stock message box, nothing started, the mode kept')
    # the first file is gone: nothing started, the mode kept
    m = machine(songs=songs); m.open(); m.timers = []; m.mode = 3
    m.present.discard('/mnt/mmc/m/1.flac')
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    expect(m.mode == 3 and ('start_player' not in m.names() or m.played[0][m.played[1]] is not None), 'a missing file starts nothing and keeps the mode')


def settings_tests(ctx):
    expect = ctx.expect
    VALUE_X = O['IP_SPLIT_X'] - O['IP_TEXT_X']
    def values(m):
        texts, fills, _ = m.paint()
        return [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if r[0] + r[2] - 2 == VALUE_X and BARH <= r[1] < 240]
    def chevrons(m):
        return [f for f in m.paint()[1] if f[3] == 2 and f[4] == 1 and f[1] >= 300 and BARH <= f[2] < 240 and f[0] == 0xffffffff]
    m = machine(); m.open(); m.timers = []
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    texts, fills, _ = m.paint()
    expect(not m.opened and 'loadLocalClassList' not in m.names(), 'Settings is a level of the iPod page now: no stock page opens, no query runs')
    expect(rows_of(texts) == [m.tr(k) for k in SET_KEYS] and m.tr('cdrippersettings') in [t for t, _ in texts], f'Shuffle and Repeat under Settings ({rows_of(texts)})')
    expect(values(m) == [m.tr('Off'), m.tr('Off'), m.tr('Light')], f'right aligned playback and Appearance values ({values(m)})')
    expect(not chevrons(m), 'the selected row has a value, not a chevron')
    m.paint()
    vals = sorted(((r[1], s) for (t, r), s in zip(m.texts, m.text_styles) if r[0] + r[2] - 2 == VALUE_X), key=lambda v: v[0])
    expect([s for _, s in vals] == ['label_ip_subsel', 'label_ip_val', 'label_ip_val'],
           f'a value is white (regular 14 px) on the selected row and blue on the others ({vals})')
    # the value is drawn at the right edge, the label is cut before it
    rect = {t: r for t, r in texts}
    expect(rect[m.tr('Shuffle')][0] == O['IP_TEXT_X'] and rect[m.tr('Shuffle')][2] < 310 - 20, 'the label starts at the left margin and stops short of the value')
    # shuffle: Off -> Songs -> Off
    m.tap(CX, CY)
    expect(m.mode == 2 and ('mclSetPlayMode', 2) in m.calls and ('write_int_config', 2, 'PLAYSET', 'PLAYMODE') in m.calls and values(m)[:2] == [m.tr('Songs'), m.tr('Off')],
           f'centre press on Shuffle: stock Shuffle (mode 2); the value reads Songs ({values(m)})')
    m.tap(CX, CY)
    expect(m.mode == 0 and ('mclSetPlayMode', 0) in m.calls and values(m)[:2] == [m.tr('Off'), m.tr('Off')], 'again: back to List play, Off')
    # repeat: Off -> One -> All -> Off; turning it on turns Shuffle off
    m.turn(0, STEP_DEG + 5)
    seen = []
    for _ in range(4):
        m.tap(CX, CY); seen.append((m.mode, values(m)[1]))
    expect(seen == [(1, m.tr('One')), (3, m.tr('All')), (0, m.tr('Off')), (1, m.tr('One'))], f'Repeat cycles Off, One, All, Off ({seen})')
    m.mode = 2
    expect(values(m)[:2] == [m.tr('Songs'), m.tr('Off')], 'in Shuffle mode Repeat reads Off')
    m.tap(CX, CY)
    expect(m.mode == 1 and values(m)[:2] == [m.tr('Off'), m.tr('One')], 'Repeat on turns Shuffle off (one play mode)')
    m.mode = 0
    m.turn(0, STEP_DEG * 9)
    expect(len([t for t in rows_of(m.paint()[0])]) == 3, 'the list stops at its three rows')
    x, y = m.polar(0, 85); m.tap(x, y)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS] and not m.names().count('navigator_back'), 'MENU returns to the main menu')


def appearance_tests(ctx):
    expect = ctx.expect
    path = '/mnt/data/m1plus/pod-appearance'
    m = machine(); m.open(); m.timers = []
    expect(m.call(PSYMS['ip_theme_dark']) == 0, 'missing Appearance setting defaults to Light')
    for data in (b'', b'2', b'1junk', b'11', b'1\nextra'):
        m.fs[path] = data; m.call(PSYMS['ip_theme_load'])
        expect(m.call(PSYMS['ip_theme_dark']) == 0, f'invalid setting {data!r} defaults to Light')
    m.turn(0, 3 * STEP_DEG + 5); m.tap(CX, CY)
    m.turn(0, 2 * STEP_DEG + 5); m.tap(CX, CY)
    expect(m.fs.get(path) == b'1\n' and m.call(PSYMS['ip_theme_dark']) == 1, 'Appearance saves Dark atomically')
    expect(m.props[(m.widgets['ipod_wheel_img'], 'image')] == 'ipod_wheel_dark', 'the existing insensitive wheel image switches to Dark')
    expect(m.styles[(m.widgets['label_ip_row'], 'normal:text_color')] == 0xff000000, 'dark keeps the screen\'s black text: the screen stays white, as the black iPod\'s')
    expect(m.styles[(WIN, 'normal:bg_color')] == 0xff111111, 'only the case behind the wheel turns dark')
    _, fills, _ = m.paint()
    expect(fills[0][0] == 0xffffffff and any(f[0] == 0xfffdfdfd for f in fills), 'the dark screen and the header are the light ones')
    m.fire(EVT_DESTROY, WIN); m.open()
    expect(m.call(PSYMS['ip_theme_dark']) == 1, 'Dark persists across page destruction and reopen')
    m.fail.add(('rename', path))
    expect(m.call(PSYMS['ip_theme_toggle']) == 0xffffffff and m.call(PSYMS['ip_theme_dark']) == 1, 'a failed save preserves the live theme')
    m.fail.clear(); m.call(PSYMS['ip_theme_toggle'])
    expect(m.fs[path] == b'0\n', 'Light can be restored')


def transition_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []; m.paint(animated=True)
    before = tuple(m.word(m.canvas + o) for o in (0, 4, 16, 20, 24, 28))
    m.tap(CX, CY)
    expect(m.call(PSYMS['ip_render_active']) == 1 and m.call(PSYMS['ip_render_width']) == 160, 'split menus start an internal half-width slide')
    m.origins = []; m.clip_frames = []; m.paint(animated=True)
    expect(0 in m.origins and 160 in m.origins, 'outgoing model and incoming page start at their own horizontal origins')
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    m.origins = []; m.paint(animated=True)
    expect(40 in m.origins and (0xffffffff - 119) in m.origins, f'half the time in, the two menu pages are three quarters of the way, in opposite directions (eased out, as the iPod) ({sorted(set(m.origins))})')
    bar = [(t, ox) for (t, r_), ox in zip(m.texts, m.text_ox) if r_[1] == 1]
    expect(bar and bar[-1] == (m.tr('Music'), 0), f'the title bar stays put over the slide, already titled Music ({bar})')
    expect((0xffffffff - 119, 0, 39) in m.clip_frames and (40, 40, 159) in m.clip_frames, 'each moving menu is clipped to its own bounds as well as the display viewport')
    expect(tuple(m.word(m.canvas + o) for o in (0, 4, 16, 20, 24, 28)) == before, 'painting restores canvas origin and clipping exactly')
    expect(not any(c[0] in ('calloc', 'bitmap_create_ex', 'widget_load_image', 'loadLocalClassList') for c in m.calls), 'animated paint performs no allocation, decode or library query')
    m.clock += 141; m.call(PSYMS['ip_tick'], count=40000000)
    expect(m.call(PSYMS['ip_render_active']) == 0, 'the slide finishes on the existing timer after 280 ms')
    m.paint(animated=True); m.tap(*m.polar(0, 85))
    expect(m.call(PSYMS['ip_render_active']) == 1, 'MENU animates an internal pop')
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    m.clip_frames = []; m.paint(animated=True)
    expect((120, 120, 159) in m.clip_frames and (0xffffffff - 39, 0, 119) in m.clip_frames, 'pop backgrounds cannot erase the outgoing half of the screen')
    m.fire(EVT_BG, WIN)
    expect(m.call(PSYMS['ip_render_active']) == 0, 'backgrounding cancels the slide')
    m.fire(EVT_FG, WIN); m.paint(animated=True); m.tap(CX, CY); m.tap(*m.polar(0, 85))
    expect(m.call(PSYMS['ip_render_active']) == 0, 'fast repeated navigation settles instead of stacking animations')
    m.fire(EVT_DESTROY, WIN)
    expect(not m.bitmaps, 'destroy frees image snapshots and page bitmaps')
    # the soft text gamma (patch/textgamma.c tg_soften) while the Pod is in front: each change empties the glyph cache once
    m = machine(); m.fm = 0x24000000
    shrinks = lambda: sum(1 for c in m.calls if c[0] == 'font_manager_shrink_cache')
    m.open(); m.timers = []; n_open = shrinks()
    m.calls = []; m.fire(EVT_BG, WIN); n_bg = shrinks(); m.calls = []; m.fire(EVT_FG, WIN); n_fg = shrinks()
    m.calls = []; m.fire(EVT_FG, WIN); n_fg2 = shrinks(); m.calls = []; m.fire(EVT_DESTROY, WIN); n_end = shrinks()
    expect((n_open, n_bg, n_fg, n_fg2, n_end) == (1, 1, 1, 0, 1), f'the Pod softens the text gamma on open and foreground, restores it on background and destroy ({(n_open, n_bg, n_fg, n_fg2, n_end)})')
    # a slow query (Music > Songs on a big library): the slide's 300 ms count from when the list is loaded, not from the press, so it is still seen
    m = machine(songs=['A', 'B']); m.open(); m.timers = []; m.paint(animated=True)
    music(m); m.paint(animated=True); m.turn(0, STEP_DEG * 4 + 5); m.paint(animated=True)
    m.load_ms = 400; m.tap(CX, CY); m.load_ms = 0
    m.call(PSYMS['ip_tick'], count=40000000); active = m.call(PSYMS['ip_render_active'])
    expect(active == 1, 'Music > Songs still slides after a 400 ms query')
    m.clock += 75; m.call(PSYMS['ip_tick'], count=40000000); m.origins = []; m.paint(animated=True)
    expect(m.call(PSYMS['ip_render_active']) == 1 and 240 in m.origins, f'and a quarter in 75 ms later, at a steady speed as on the iPod (no ease-in) ({sorted(set(m.origins))[:6]})')
    m.clock += 75; m.call(PSYMS['ip_tick'], count=40000000); m.origins = []; m.paint(animated=True)
    expect(m.call(PSYMS['ip_render_active']) == 1 and 160 in m.origins, f'and half way at 150 ms ({sorted(set(m.origins))[:6]})')
    # a page of its own from a split menu: it slides in whole without its title bar, which then drops in; between full pages the bar slides with the page
    m = machine(albums=[('Kind of Blue', 'Miles Davis')]); m.open(); m.timers = []; m.paint(animated=True)
    m.tap(CX, CY); settle(m); m.paint(animated=True)   # Music
    m.turn(0, STEP_DEG * 3 + 5); m.paint(animated=True); m.tap(CX, CY)   # Albums
    def bar(): return [(t, ox) for (t, r_), ox in zip(m.texts, m.text_ox) if r_[1] == 1]
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000); m.paint(animated=True)
    expect(m.call(PSYMS['ip_render_width']) == O['IP_W'] and any(t == m.tr('Albums') and ox > 0 for t, ox in bar()), f'Music > Albums: the page slides in whole, its title bar with it ({bar()})')
    settle(m); m.paint(animated=True)
    expect((m.tr('Albums'), 0) in bar(), f'and rests in place ({bar()})')
    m.tap(CX, CY); m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000); m.paint(animated=True)
    expect(len({ox for _, ox in bar()}) == 2 and 0 not in {ox for _, ox in bar()}, f'Albums > an album: both bars slide with their pages ({bar()})')
    settle(m); m.paint(animated=True); m.tap(*m.polar(0, 85)); settle(m); m.paint(animated=True); m.tap(*m.polar(0, 85))
    m.clock += 70; m.call(PSYMS['ip_tick'], count=40000000); m.paint(animated=True)
    expect(any(t == m.tr('Music') and ox < 0 for t, ox in bar()), f'MENU back to Music: its title bar comes back in with the menu half, drawn by the list\'s edge ({bar()})')
    tick(m, 500); m.paint(animated=True)
    expect((m.tr('Music'), 0) in bar(), f'and rests in place, no drop after ({bar()})')


def pane_sharp_tests(ctx):
    """The cover pane's sharper sources (docs/modules/ipod.md "The cover pane"): the playing album from demo's full-resolution file, the rotation from one transient extraction."""
    expect = ctx.expect
    ART = O['IP_PANE_ART']
    TMP = '/tmp/m1plus-pane.jpg'
    COVER_SRC = pod.DATA['COVER_SRC'][0]
    def solid(rgb): return (264, 264, bytes(rgb + (255,)) * (264 * 264))
    def center(m, slot_ptr): return m.word(slot_ptr + 4 * (ART // 2 * ART + ART // 2)) & 0xffffff
    def slots(m): return [ptr for ptr, w, h in m.bitmaps.values() if w == h == ART]
    def prepare(worker=True):
        m = with_covers(worker=worker)
        for i in range(10): m.present.add(f'/mnt/mmc/m/Album {i}.flac')
        m.album_cover = 1; m.art_px = ART
        m.images['file://' + TMP] = solid((200, 10, 10))
        m.call(PSYMS['ip_first'], a0=0, count=40000000)
        return m
    def run_to_extraction(m):
        """Ticks (100 ms) until the pane starts the extraction: its calls."""
        for _ in range(80):
            c = tick(m)
            if ('pthread_create',) in c: return c
        return []
    # the rotation: one transient extraction on the shared worker, decoded at 264, deleted
    m = prepare()
    c = run_to_extraction(m)
    asked = [x for x in c if x[0] == 'toolsGetAlbumCover']
    expect(('pthread_create',) in c and m.call(PSYMS['cc_build_busy']) == 1 and not pane_loads(c, m), 'at IP_PANE_NEXT_MS the next cover is asked of the shared worker (no decode yet, no 168 px file read for it)')
    m.call(PSYMS['cc_worker'], count=5000000)   # the (mock) thread runs its one job
    asked = [x for x in m.calls if x[0] == 'toolsGetAlbumCover']
    expect(len(asked) == 1 and asked[0][2] == TMP + '.tmp' and asked[0][1].startswith('/mnt/mmc/m/Album ') and m.cover_size == (ART, ART), f'one extraction of that album\'s art at {ART} px into a .tmp in /tmp ({asked})')
    expect(TMP in m.present and TMP + '.tmp' not in m.present and ('rename', TMP + '.tmp', TMP) in m.calls, 'published by a rename: one transient file')
    c = tick(m)
    loads = [x for x in c if x[0] == 'widget_load_image']
    expect(loads and loads[0][1] == 'file://' + TMP and TMP not in m.present and ('pthread_join',) in c and m.call(PSYMS['cc_build_busy']) == 0, 'the next tick decodes it (box filtered to 264) and deletes it; the worker is joined and the job set freed')
    s = slots(m)
    expect(len(s) == 2 and center(m, s[1]) == 0x0a0ac8, f'the new cover is the extraction\'s picture, not the 168 px file\'s ({center(m, s[1]):06x})')
    expect(all(p.startswith('/tmp/') for p in [x[2] for x in m.calls if x[0] == 'toolsGetAlbumCover']), 'never written under /mnt/mmc')
    for _ in range(60): tick(m)
    expect(not [p for p in m.present if p.startswith('/tmp/m1plus-pane')], 'no transient file is left behind')
    # a small source: nothing kept, the 168 px file shows
    for art_px, album_cover, what in ((200, 1, 'a source under 264 px'), (264, 0, 'a failed extraction')):
        m = prepare(); m.art_px = art_px; m.album_cover = album_cover
        run_to_extraction(m); m.call(PSYMS['cc_worker'], count=5000000)
        c = tick(m)
        got = pane_loads(c, m)
        expect(TMP not in m.present and got and all(g in range(8) for g in got) and ('pthread_join',) in c, f'{what}: no file kept, the 168 px file of the album is used ({got})')
        expect(not [p for p in m.present if p.startswith('/tmp/m1plus-pane') or '-264' in p], f'{what}: no temp file left, and no cache file or marker of another size written')
    # the job set is held by another page: the 168 px file at once, no worker of ours
    m = prepare()
    for _ in range(25): tick(m)
    m.call(PSYMS['cc_build_open'], a0=4, a1=0)
    allc = []
    for _ in range(40): allc += tick(m)
    expect(('pthread_create',) not in allc and not [x for x in allc if x[0] == 'toolsGetAlbumCover'] and len([x for x in allc if x[0] == 'widget_load_image']) >= 1, 'with the job set held by another page the rotation keeps the 168 px file and starts no extraction')
    m.call(PSYMS['cc_build_stop'])
    # leaving the pane cancels the worker (never joined while inside its job) and removes the file
    m = prepare()
    run_to_extraction(m)
    m.tap(CX, CY); m.turn(0, STEP_DEG * 3 + 5); m.calls = []; m.tap(CX, CY)   # Music > Albums: not a split page
    c = tick(m)
    expect(orphaned(m, c) and not [p for p in m.present if p.startswith('/tmp/m1plus-pane')], 'a level without the pane: the extraction is cancelled (not joined) and its file removed')
    m = prepare(); run_to_extraction(m); m.calls = []
    m.fire(EVT_BG, WIN)
    expect(orphaned(m), 'to the background: cancelled, not joined, reaped once it exits')
    m = prepare(); run_to_extraction(m); m.screen(False); m.calls = []
    tick(m)
    expect(orphaned(m), 'screen off: cancelled, not joined, reaped once it exits')
    m = prepare(); run_to_extraction(m); m.calls = []
    m.fire(EVT_DESTROY, WIN)
    expect(orphaned(m), 'destroy: cancelled, not joined, reaped once it exits, no leak')
    # the playing album: demo's full-resolution file, after the 168 px one, once demo is done with it
    m = with_covers(); m.clock = 100000
    m.images['file:///tmp/coverpic.jpg'] = solid((10, 10, 220)); m.present.add('/tmp/coverpic.jpg'); m.files['/tmp/coverpic.jpg'] = 5000
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    for _ in range(4): tick(m)
    m.setword(COVER_SRC, 1)   # demo makes the new cover
    m.play([m.song('T', artist='Artist 3', album='Album 3')], 0)
    seen = []
    for _ in range(14): seen += [x[1] for x in tick(m) if x[0] == 'widget_load_image']
    expect(any(u in m.urls for u in seen) and 'file:///tmp/coverpic.jpg' not in seen, f'a new track while demo is still making the picture: the 168 px file ({seen})')
    m.setword(COVER_SRC, 2)   # done
    seen = []
    for _ in range(30): seen += [x[1] for x in tick(m) if x[0] == 'widget_load_image']
    expect(seen.count('file:///tmp/coverpic.jpg') == 1, f'then the full-resolution file is decoded once, on its own tick, and fades in ({seen})')
    for _ in range(40): tick(m)
    s = slots(m)
    expect(len(s) == 2 and 0x00dc0a0a in (center(m, s[0]), center(m, s[1])), 'at 264 px (box filter) from the file demo wrote')
    for _ in range(40): seen += [x[1] for x in tick(m) if x[0] == 'widget_load_image']
    expect(seen.count('file:///tmp/coverpic.jpg') == 1, 'and nothing is decoded again')
    # a stale file: the track changed, demo was not seen, the file is not trusted before IP_PANE_SHARP_MS
    m = with_covers(); m.clock = 100000
    m.images['file:///tmp/coverpic.jpg'] = solid((10, 10, 220)); m.present.add('/tmp/coverpic.jpg'); m.files['/tmp/coverpic.jpg'] = 5000
    m.setword(COVER_SRC, 2)
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    for _ in range(4): tick(m)
    m.play([m.song('T', artist='Artist 3', album='Album 3')], 0)
    seen = []
    for _ in range(14): seen += [x[1] for x in tick(m) if x[0] == 'widget_load_image']
    expect('file:///tmp/coverpic.jpg' not in seen, 'no busy state seen after the track change: the file may be the last track\'s, it is not used yet')
    for _ in range(50): seen += [x[1] for x in tick(m) if x[0] == 'widget_load_image']
    expect(seen.count('file:///tmp/coverpic.jpg') == 1, f'after IP_PANE_SHARP_MS it is ({O["IP_PANE_SHARP_MS"]} ms)')


def row_px(m, blits, row=0, x=10, y=10):
    """The pixel at x, y of the cover drawn in cover row `row` (the row's own bitmap or the shared placeholder), or None when none is drawn."""
    t = O['IP_TALL_H']; b = next((b for b in blits if b[2] == (0, BARH + row * t, t, t)), None)
    return bytes(m.u.mem_read(m.bitmaps[b[0]][0] + (y * t + x) * 4, 4)) if b else None


def orphaned(m, c=()):
    """The worker is cancelled and orphaned (busy, no join); once it has exited the next call reaps it."""
    ok = ('pthread_join',) not in list(m.calls) + list(c) and build_state(m)['orphan'] == 1 and m.call(PSYMS['cc_build_busy']) == 1
    m.call(PSYMS['cc_worker'], count=5000000)
    return ok and m.call(PSYMS['cc_build_busy']) == 0 and build_state(m)['jobs'] == 0


def fresh_art_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Fresh', 'Artist')]); m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    for _ in range(3): tick(m)
    expect(row_px(m, m.paint()[2]) == bytes((0x40, 0x40, 0x40, 255)), 'an album with no cached cover yet shows the placeholder, not a grey block')
    expect(m.call(PSYMS['cc_build_busy']) == 1 and m.call(PSYMS['cc_build_total']) == 1, 'fresh cache starts the shared extractor from the visible album record')
    key = album_key('Artist', 'Fresh'); path = art_file(key)
    m.present.add(path); m.files[path] = 4096
    m.images['file://' + path] = (48, 48, bytes((10, 100, 200, 255)) * 48 * 48)
    for _ in range(3): tick(m)
    _, _, blits = m.paint()
    expect(row_px(m, blits) == bytes((10, 100, 200, 255)), 'a newly extracted cover replaces the visible placeholder')
    m.fire(EVT_BG, WIN)
    expect(orphaned(m), 'background cancels this page own extraction job (reaped once it exits)')
    m = machine(albums=[('No card', 'Artist')]); m.card_mounted = False; m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    for _ in range(4): tick(m)
    expect(m.call(PSYMS['cc_build_busy']) == 0, 'no extraction job is started without a mounted card')


def reference_nav_tests(ctx):
    """The reference's navigation: a Now Playing row only while something plays, the split open of fullscreen pages, the long press of MENU."""
    expect = ctx.expect
    keys = [k for k in MAIN_KEYS if k != 'Now Playing']
    m = machine(); m.status = 0; m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys], f'nothing plays: the main menu has no Now Playing row ({rows_of(m.paint()[0])})')
    m.turn(0, STEP_DEG * 9)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys] and len([f for f in m.paint()[1] if f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] >= row_y(4)]) == row_h(4),
           'five rows: the cursor stops on Shuffle Songs, the last')
    m = machine(); m.status = 0; m.open(); m.timers = []
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY); texts = m.paint(animated=False)[0]
    expect(rows_of(texts) == [m.tr(k) for k in SET_KEYS], 'and Settings opens from the third row')
    m = machine(); m.status = 0; m.open(); m.timers = []
    m.turn(0, STEP_DEG * 3 + 5)
    m.status = 2
    for _ in range(5): m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    texts, fills, _ = m.paint()
    expect(rows_of(texts) == [m.tr(k) for k in MAIN_KEYS] and any(f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] == row_y(3) for f in fills),
           'playback starts: Now Playing appears as the last row and the cursor stays on Settings')
    m.status = 0
    for _ in range(5): m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys] and any(f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] == row_y(3) for f in m.paint()[1]), 'and goes with it, the cursor still on Settings')
    # a fullscreen page opens with the split: the menu half slides left, the artwork pane right, uncovering the page that stays still
    m = machine(songs=['Song']); m.open(); m.timers = []; m.paint(animated=True)
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][0]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.origins = []; m.clip_frames = []; m.tap(CX, CY)
    expect(m.call(PSYMS['ip_render_active']) == 1 and m.call(PSYMS['ip_render_split']) == 1 and m.call(PSYMS['ip_render_direction']) == 1, 'Now Playing from the main menu starts a split slide')
    m.origins = []; m.paint(animated=True)
    expect(set(m.origins) == {0}, f'the first frame draws everything at its place ({sorted(set(m.origins))})')
    m.clock += 100; m.call(PSYMS['ip_tick'], count=40000000)
    m.origins = []; m.clip_frames = []; m.paint(animated=True)
    ox = sorted({o if o < 1 << 31 else o - (1 << 32) for o in m.origins})
    expect(ox == [-80, 0, 80] or ox == [-79, 0, 79] or ox == [-80, 0, 79], f'midway: the page still, the menu half 80 px left, the pane 80 px right ({ox})')
    frames = {(o if o < 1 << 31 else o - (1 << 32), a, b) for o, a, b in m.clip_frames}
    expect(any(o < 0 and a == 0 and 88 <= b <= 90 for o, a, b in frames) and any(o > 0 and 238 <= a <= 241 and b >= 319 for o, a, b in frames),
           f'the halves are clipped to what is left of them ({sorted(frames)})')
    m.paint(animated=True)
    expect(not [r_ for t, r_ in m.texts if t == 'Now Playing' and r_[1] == 1], 'Now Playing opening: no title bar while the halves slide away (the menu\'s Now Playing row is still on its half)')
    m.clock += 141; m.call(PSYMS['ip_tick'], count=40000000)
    def title_oy():
        m.paint(animated=True)
        base = [oy for (t, _), oy in zip(m.texts, m.text_oy) if t == 'Song']
        return [oy - base[0] for (t, r_), oy in zip(m.texts, m.text_oy) if t == 'Now Playing' and r_[1] == 1] if base else None
    expect(m.call(PSYMS['ip_render_active']) == 0 and title_oy() == [-O['IP_BAR_H']], f'the slide ends on Now Playing, 280 ms after it began; the title bar starts just above the screen ({title_oy()})')
    m.clock += O['IP_BAR_WAIT_MS'] - 10; m.call(PSYMS['ip_tick'], count=40000000)
    expect(title_oy() == [-O['IP_BAR_H']], f'the bar waits IP_BAR_WAIT_MS above the screen, as on the iPod ({title_oy()})')
    m.clock += 10 + O['IP_BAR_DROP_MS'] // 2; m.call(PSYMS['ip_tick'], count=40000000)
    mid = title_oy()
    expect(mid and -O['IP_BAR_H'] < mid[0] < 0, f'halfway the bar has dropped part of the way ({mid})')
    m.clock += O['IP_BAR_DROP_MS'] // 2; m.call(PSYMS['ip_tick'], count=40000000)
    expect(title_oy() == [0], f'after IP_BAR_DROP_MS the bar is in place ({title_oy()})')
    # and back: MENU slides the halves in over the page
    m.tap(*m.polar(0, 85))
    expect(m.call(PSYMS['ip_render_active']) == 1 and m.call(PSYMS['ip_render_split']) == 1 and m.call(PSYMS['ip_render_direction']) == 0xffffffff, 'MENU from Now Playing starts the split slide back')
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    m.origins = []; m.clip_frames = []; m.paint(animated=True)
    ox = sorted({o if o < 1 << 31 else o - (1 << 32) for o in m.origins})
    expect(0 in ox and min(ox) < 0 and max(ox) > 0, f'the menu half and the pane come in from both sides ({ox})')
    expect(not any(c[0] in ('calloc', 'widget_load_image', 'loadLocalClassList') for c in m.calls), 'no allocation, decode or query in the slide')
    m.clock += 141; m.call(PSYMS['ip_tick'], count=40000000)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'the main menu is back')
    # Music -> a list does not split (full width)
    m = machine(albums=[("Album", "Artist")]); m.open(); m.timers = []; music(m); m.paint()
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(m.call(PSYMS["ip_render_split"]) == 0 and m.call(PSYMS["ip_render_cover"]) == 1 and m.call(PSYMS["ip_render_active"]) == 1 and m.call(PSYMS["ip_render_width"]) == 320, "a list from Music comes in over the pane (the cover slide), no split")
    # a long press of MENU goes to the main menu with the slide of the last level; a tap is one level; at the main menu it does nothing
    m = machine(albums=[('Album', 'Artist')], songs=['Song']); m.open(); m.timers = []; m.paint(animated=True)
    music(m); m.paint(animated=True); m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY); m.paint(animated=True)
    x, y = m.polar(0, 85)
    m.calls = []; m.ptr('down', x, y, 5000)
    expect(('timer_modify', 0x777, O['IP_DRIFT_MS']) in m.calls, 'a touch on MENU watches the clock at 100 ms')
    m.clock = 5400; m.call(PSYMS['ip_tick'], count=40000000)
    expect(rows_of(m.paint()[0]) != [m.tr(k) for k in MAIN_KEYS], 'held 0.4 s: still the list')
    m.clock = 5600; m.calls = []; m.call(PSYMS['ip_tick'], count=40000000)
    m.paint(animated=True)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], f'held 0.5 s: the main menu, two levels up in one go ({rows_of(m.paint()[0])})')
    m.calls = []; m.ptr('up', x, y, 5650)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS] and 'navigator_back' not in m.names(), 'the release after a long press does nothing more')
    m.tap(CX, CY); m.paint(animated=True)
    m.ptr('down', x, y, 7000); m.ptr('up', x, y, 7600)
    expect(rows_of(m.paint(animated=False)[0]) == [m.tr(k) for k in MAIN_KEYS] and 'navigator_back' not in m.names(), 'a long press on the Music menu goes to the main menu (and a held touch that released late too)')
    m.calls = []; m.ptr('down', x, y, 9000); m.clock = 9700; m.call(PSYMS['ip_tick'], count=40000000); m.ptr('up', x, y, 9700)
    expect('navigator_back' not in m.names(), 'at the main menu a long press does not close the page')
    m.tap(*m.polar(0, 85))
    expect('navigator_back' in m.names(), 'but a tap on MENU there does')


def shadow_slide_tests(ctx):
    """The menu's shadow belongs to the menu half: it stays with the pane while the menu pages swap, moves with the menu in the split open and close, and is not on fullscreen pages."""
    expect = ctx.expect
    SW = O['IP_SHADOW_W']
    sx = lambda v: v - (1 << 32) if v >= 1 << 31 else v
    SK = SW // 2   # the split shadow fades with the slide: half its columns at half way
    def parts(m, w=SW):
        texts, fills, blits = m.paint(animated=True)
        edge = [sx(m.img_ox[i]) for i, b in enumerate(blits) if b[2] == (PANE[0], 0, w, PANE[3])]
        pane = [sx(m.img_ox[i]) for i, b in enumerate(blits) if b[2] == PANE]
        return edge, pane
    m = machine(songs=['Song']); m.open(); m.timers = []; m.paint(animated=True)
    expect(parts(m)[0] == [0], 'at rest on the main menu: one shadow at x 160')
    m.tap(CX, CY); m.paint(animated=True); m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)   # Main -> Music, half way
    edge, pane = parts(m)
    expect(edge[:1] == [0], f'while the menu pages swap the shadow is drawn at the pane\'s edge, not moved (the incoming page\'s copy lies under its clip) ({edge})')
    m.paint()
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][0]], 0)
    m.tap(*m.polar(0, 85)); m.paint()                       # back to the main menu
    m.turn(0, STEP_DEG * 5 + 5); m.paint(); m.tap(CX, CY)   # Now Playing: the split open
    m.paint(animated=True); m.clock += 100; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m, SW - SK)
    expect(len(edge) == 1 and edge[0] < 0 and pane and all(o > 0 for o in pane), f'split open: the shadow goes with the menu half (left, {edge}), the pane goes right ({pane})')
    m.paint()
    expect(parts(m)[0] == [] and 'Now Playing' in texts_of(m.paint()), 'on the fullscreen page there is no shadow')
    m.tap(*m.polar(0, 85))
    expect(not [b for b in m.paint(animated=True)[2] if b[2][0] == PANE[0] and b[2][2] <= SW], 'split close: no shadow as the halves start in (it fades in, so no seam)')
    m.clock += 100; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m, SW - SK)
    expect(edge == [-80] and 80 in pane, f'split close: the shadow comes in with the menu half, once; the pane comes in from the right ({edge}, {pane})')
    m.paint()
    expect(parts(m)[0] == [0], 'and rests at the pane\'s edge again')
    # Music > a full-width list: the list comes in over the still pane and its left edge pushes the menu half (and its shadow) out on the left
    m = machine(albums=[('Album', 'Artist')], songs=['Song']); m.open(); m.timers = []; m.paint(animated=True)
    m.tap(CX, CY); m.paint(); m.clock += 400; m.call(PSYMS['ip_tick'], count=40000000); m.paint()   # Main -> Music, settled
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(m.call(PSYMS['ip_render_cover']) == 1, 'Music > a list starts the cover slide')
    m.clock += 100; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m)
    expect(set(edge) == {0} and all(o == 0 for o in pane), f'early: the list has not reached the menu, which stays, the pane too ({edge}, {pane})')
    white = [f for f in m.fill_clip if f[0] == 0 and f[1] == O['IP_W'] and f[2] <= O['IP_SPLIT_X'] + 5 <= f[3]]
    expect(not white, f'the menu half\'s full-width white fill stays left of the pane: the shadow is not drawn over white ({white})')
    m.clock += 120; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m)
    expect(len(set(edge)) == 1 and edge[0] < 0 and all(o == 0 for o in pane), f'late: the list pushes the menu half out on the left, the pane stays ({edge}, {pane})')
    m.clock += 300; m.call(PSYMS['ip_tick'], count=40000000); m.paint()
    m.tap(*m.polar(0, 85)); m.paint(animated=True); m.clock += 220; m.call(PSYMS['ip_tick'], count=40000000)
    expect(m.call(PSYMS['ip_render_cover']) == 1 and m.call(PSYMS['ip_render_direction']) == 0xffffffff, 'MENU back to Music runs the cover slide backwards')
    edge, pane = parts(m)
    expect(set(edge) == {0} and all(o == 0 for o in pane), f'late in the close the menu is home and the list is past it ({edge}, {pane})')


def now_steady_tests(ctx):
    """Now Playing does not blink while the player changes track: no time or no track for a moment leaves the text, the cover and the whole bar on screen."""
    expect = ctx.expect
    TX, BY, BH = O['IP_NP_TRACK_X'], O['IP_NP_BAR_Y'], O['IP_NP_BAR_H']
    m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
    songs = m.class_lists[O['CLASS_ALL_SONGS']]
    m.status = 2; m.pt = (107, 305); m.play([songs[0], songs[1]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    tick(m, 500); tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])   # the slide, then the title bar drops in: the page's idle interval
    def looks(n): [m.call(PSYMS["ip_tick"], a0=0, count=40000000) for _ in range(n)]   # on this level every tick looks (500 ms)
    def shown():
        texts, fills, blits = m.paint()
        names = [t for t, _ in texts]
        bar = {f[2] for f in fills if BY <= f[2] < BY + BH and f[1] >= TX and f[4] == 1}
        return names, len(bar), blits
    looks(1)
    names, bar, _ = shown()
    expect('Alpha' in names and '1:47' in names and '-3:18' in names and bar == BH, f'playing: the track, both times and the {BH} px bar ({names}, {bar})')
    for pt, what in ((None, 'no time (the call fails)'), ((0, 0), 'length 0')):
        m.pt = pt; looks(1)
        names, bar, _ = shown()
        expect('Alpha' in names and '1:47' in names and '-3:18' in names and bar == BH, f'{what}: the bar and both times stay, at the last valid place ({names}, {bar})')
    m.pt = None; m.play([songs[0], songs[1]], 1); looks(1)
    names, bar, _ = shown()
    expect('Beta' in names and '0:00' in names and '-5:05' in names and bar == BH, f'a new track with no time yet: an empty bar, 00:00 and the last length, never blank ({names}, {bar})')
    m.pt = (3, 200); looks(1)
    names, bar, _ = shown()
    expect('0:03' in names and '-3:17' in names and bar == BH, 'then its own time')
    m.calls = []; m.play([], 0); looks(1)
    names, bar, blits = shown()
    expect('Beta' in names and '0:03' in names and bar == BH and 'Not Playing' not in names and not any(c[0] == 'widget_load_image' and c[1] == 'ipod_placeholder' for c in m.calls),
           f'no current track for a moment: the last track\'s text and bar stay and the cover is not swapped for the disc ({names})')
    expect(any(b[2] == (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_NP_ART_W'], O['IP_NP_ART_W'] + O['IP_NP_REFLECT']) for b in blits), 'the cover is still drawn')
    looks(3)
    names, bar, _ = shown()
    expect('Not Playing' in names and 'Beta' not in names, 'and Not Playing once the player really has none')
    before = len([c for c in m.calls if c[0] == 'bitmap_create_ex'])
    shown(); shown()
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == before, 'painting allocates nothing')


def np_pending_tests(ctx):
    """A song tapped in a list: Now Playing slides in with that song, though the player still reports the last one (start_player takes a moment), then follows the player."""
    expect = ctx.expect
    TY = O['IP_NP_TITLE_Y']
    def titles():
        return [t for t, r in m.paint()[0] if r[1] == TY]
    m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
    songs = m.class_lists[O['CLASS_ALL_SONGS']]
    m.status = 2; m.pt = (107, 305); m.play([songs[0], songs[1]], 0)
    music(m); m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)   # Songs
    m.turn(0, 23); m.tap(CX, CY)   # Beta; the harness's player stays on Alpha
    expect(m.played and m.played[1] == 1, 'Beta is started')
    tick(m, 100)
    mid = titles()
    expect(mid == ['Beta'], f'mid-slide Now Playing already names the tapped song ({mid})')
    tick(m, 500); tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])
    expect(titles() == ['Beta'], f'and once in ({titles()})')
    m.play(m.played[0], 1); tick(m, 500)
    expect(titles() == ['Beta'], 'the player catching up changes nothing')
    m.play([songs[0], songs[1]], 0); tick(m, 500)
    expect(titles() == ['Alpha'], 'then Now Playing follows the player again')
    # a player that never reaches the tapped song: after IP_NP_PEND_MS Now Playing shows what it plays
    m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
    songs = m.class_lists[O['CLASS_ALL_SONGS']]
    m.status = 2; m.pt = (107, 305); m.play([songs[0], songs[1]], 0)
    music(m); m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
    m.turn(0, 23); m.tap(CX, CY)
    tick(m, 500); tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])
    expect(titles() == ['Beta'], 'pending: the tapped song')
    for _ in range(O['IP_NP_PEND_MS'] // 500 + 2): tick(m, 500)
    expect(titles() == ['Alpha'], f'the player never got there: its own track after the wait ({titles()})')


def scan_tests(ctx):
    """Hold-to-scan on Now Playing: a held previous / next sector moves a virtual target (1 s a 100 ms tick, 3 s after 2 s), a direct mclSetSeek every 300 ms while the target moves, a last one on release."""
    expect = ctx.expect
    def now(status=2, pt=(100, 300)):
        m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
        songs = m.class_lists[O['CLASS_ALL_SONGS']]
        m.status = status; m.pt = pt; m.play([songs[0], songs[1]], 0)
        m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)   # the Now Playing row
        tick(m, 500)   # the first look: the page knows the track
        tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])   # the title bar has dropped in
        m.cmds, m.seeks, m.sets, m.calls = [], [], [], []
        return m
    def times(m):
        names = [t for t, _ in m.paint()[0]]
        return [n for n in names if len(n) >= 4 and n[-3] == ':' and n.lstrip('-')[:1].isdigit()]
    def hold(m, deg, ticks, r=85, up=True):
        x, y = m.polar(deg, r); m.clock = 1000
        m.ptr('down', x, y, 1000)
        for _ in range(ticks): tick(m)
        if up: m.ptr('up', x, y, m.clock)
        return x, y
    # a tap still skips; a hold of 4 ticks (400 ms) released is a tap
    m = now(); hold(m, 90, 4)
    expect(m.cmds and m.cmds[0][0] == 'next' and not m.sets, f'released before 500 ms: next, no seek ({m.cmds}, {m.sets})')
    m = now(); hold(m, 270, 4)
    expect(m.cmds and m.cmds[0][0] == 'prev' and not m.sets, 'and previous on the left')
    # the hold: enters at 500 ms, 1 s a tick, shows the target, a direct seek every 300 ms (CUE start added), the release sends the last one and does not skip
    m = now(); m.cue = 0; x, y = hold(m, 90, 5, up=False)
    expect(times(m) == ['1:41', '-3:19'], f'scanning: the first tick moved the target 1 s ({times(m)})')
    expect(not m.sets, 'no seek before 300 ms of scanning')
    for _ in range(2): tick(m)
    expect(not m.sets, f'still none after 200 ms ({m.sets})')
    tick(m)
    expect(m.sets == [104], f'300 ms of scanning: the first direct seek, to the target ({m.sets})')
    for _ in range(16): tick(m)
    expect(times(m) == ['2:00', '-3:00'], f'20 ticks of 1 s (2 s of scanning): 10x ({times(m)})')
    expect(m.sets == [104, 107, 110, 113, 116, 119] and not m.cmds and not m.seeks, f'a seek every 300 ms, no skip, no seek_time ({m.sets}, {m.cmds}, {m.seeks})')
    stamps = [c[2] for c in m.calls if c[0] == 'mclSetSeek']
    expect(all(b - a == 300 for a, b in zip(stamps, stamps[1:])), f'300 ms apart ({stamps})')
    tick(m)
    expect(times(m) == ['2:03', '-2:57'], f'then 3 s a tick: 30x ({times(m)})')
    m.pt = (150, 300)   # the player keeps playing meanwhile: the bar shows the target
    expect(times(m) == ['2:03', '-2:57'], 'the track look does not overwrite the target')
    m.seek_moves = False   # the player is slow to arrive
    n = len(m.sets)
    m.ptr('up', x, y, m.clock)
    expect(m.sets[n:] == [123] and not m.cmds and not m.seeks, f'release: one last seek to the target, no skip, no seek_time ({m.sets}, {m.cmds}, {m.seeks})')
    expect(('playpause_quick_click',) not in m.calls and m.status == 2, 'the status stays playing')
    m.pt = (100, 300)   # the player has not reached it yet: the target stays
    tick(m, 500)
    expect(times(m) == ['2:03', '-2:57'] and m.status == 2, f'the target stays until the player\'s time catches up ({times(m)})')
    m.pt = (124, 300); tick(m, 500)
    expect(times(m) == ['2:04', '-2:56'], f'then the player\'s time ({times(m)})')
    m.pt = (50, 300); tick(m, 3000)
    expect(times(m) == ['0:50', '-4:10'], 'and a target never reached lets go after 3 s')
    # the scan's target is its own: the player's time moving under it (a lag, a jump) does not change it
    m = now(); m.seek_moves = False; x, y = hold(m, 90, 5 + 4, up=False)
    m.pt = (500 - 300, 300)
    tick(m)
    expect(times(m) == ['1:46', '-3:14'], f'the target is never re-derived from the reported time ({times(m)})')
    # released with the target unchanged since the last seek: no extra seek
    m = now(); x, y = hold(m, 90, 5 + 3, up=False)   # the seek went at the third tick, the target of it is the target now
    expect(m.sets == [104], f'one seek so far ({m.sets})')
    m.ptr('up', x, y, m.clock)
    expect(m.sets == [104], f'release with the target unchanged since the last seek: no seek ({m.sets})')
    # a release after the target moved past the last seek: a final one
    m = now(); x, y = hold(m, 90, 5 + 4, up=False)
    m.ptr('up', x, y, m.clock)
    expect(m.sets == [104, 105], f'release after the target moved on: one final seek ({m.sets})')
    # the CUE start is added: the target is CUE-relative
    m = now(); m.cue = 600; m.setword(m.class_lists[O['CLASS_ALL_SONGS']][0] + O['REC_CUE_START'], 600)
    x, y = hold(m, 90, 5 + 3, up=True)
    expect(m.sets == [704], f'a CUE track: the seek is target + CUE start ({m.sets})')
    # rewind, clamped at 0
    m = now(pt=(5, 300)); x, y = hold(m, 270, 5 + 10, up=False)
    expect(times(m) == ['0:00', '-5:00'], f'rewind clamps at 0 ({times(m)})')
    m.ptr('up', x, y, m.clock)
    expect(m.sets[-1] == 0 and not m.cmds and not m.seeks, f'rewind seeks to 0, no previous ({m.sets}, {m.cmds})')
    m = now(pt=(100, 300)); hold(m, 270, 5 + 3, up=True)
    expect(m.sets == [96], f'rewind goes back 1 s a tick ({m.sets})')
    # fast forward clamps at length - 1
    m = now(pt=(290, 300)); x, y = hold(m, 90, 5 + 30, up=False)
    expect(times(m) == ['4:59', '-0:01'], f'forward clamps at length - 1 ({times(m)})')
    m.ptr('up', x, y, m.clock)
    expect(m.sets[-1] == 299 and m.sets.count(299) == 1 and max(m.sets) == 299, f'and seeks there, once ({m.sets})')
    # a hold released with no tick seen (500 ms by the event times): still no tap, no seek
    m = now(); x, y = m.polar(90, 85); m.clock = 1000; m.ptr('down', x, y, 1000); m.ptr('up', x, y, 1700)
    expect(not m.cmds and not m.sets, 'a long touch the timer had not seen: no tap and no seek')
    # turning cancels the scan: no further seek, no skip (a seek already sent stays sent)
    m = now(); m.seek_moves = False; x, y = hold(m, 90, 8, up=False)
    expect(m.sets == [104], f'one seek sent before the turn ({m.sets})')
    cx, cy = m.polar(90 + 40, 85)
    m.ptr('move', cx, cy, m.clock + 20); m.ptr('up', cx, cy, m.clock + 40)
    tick(m, O['IP_VOL_SHOW_MS'] + 600)   # (the turn set the volume: its bar first)
    expect(m.sets == [104] and not m.cmds and not m.seeks and times(m) == ['1:40', '-3:20'], f'a turn during the hold cancels: no more seeks, no skip, the real position ({m.sets}, {m.cmds}, {times(m)})')
    # an abort cancels
    m = now(); x, y = hold(m, 90, 7, up=False)
    m.ptr('abort', x, y, m.clock)
    tick(m, 1000)
    expect(not m.sets and not m.cmds and times(m) == ['1:40', '-3:20'], f'an abort cancels: no seek ({m.sets})')
    m.ptr('up', x, y, m.clock + 5)
    expect(not m.sets and not m.cmds, 'and the up after it is nothing')
    # paused: seeks without resuming, nothing pauses it again
    m = now(status=3); x, y = hold(m, 90, 8, up=False)
    expect(times(m) == ['1:44', '-3:16'] and m.sets == [104], f'paused: the scan works the same, seeking ({times(m)}, {m.sets})')
    tick(m)
    m.ptr('up', x, y, m.clock)
    expect(m.sets == [104, 105] and m.status == 3, f'paused: the final seek, still paused ({m.sets}, {m.status})')
    expect(not m.seeks and not [c for c in m.calls if c[0] == 'playpause_quick_click'] and not m.cmds, f'paused: no seek_time, no resume, no re-pause ({m.calls}, {m.cmds})')
    # no player link: -1 cancels the scan quietly
    m = now(); m.set_ret = -1; x, y = hold(m, 90, 8, up=False)
    expect(not m.sets and times(m) == ['1:40', '-3:20'], f'mclSetSeek -1: the scan is over, the bar shows the player ({times(m)})')
    n = len([c for c in m.calls if c[0] == 'mclSetSeek'])
    for _ in range(10): tick(m)
    expect(len([c for c in m.calls if c[0] == 'mclSetSeek']) == n, 'and it does not try again')
    m.ptr('up', x, y, m.clock)
    expect(not m.cmds and not m.seeks, f'the release after it: no tap, no seek_time ({m.cmds}, {m.seeks})')
    # -1 on the release's seek: no held target
    m = now(); x, y = hold(m, 90, 5 + 1, up=False); m.set_ret = -1
    m.ptr('up', x, y, m.clock)
    expect(not m.sets and not m.cmds and times(m) == ['1:40', '-3:20'], f'-1 on the release: the real position stays ({m.sets}, {m.cmds}, {times(m)})')
    # nothing to scan: stopped, no track, no length, Radio, DLNA
    for what, setup in (('stopped', lambda m: setattr(m, 'status', 1)), ('no length', lambda m: setattr(m, 'pt', (0, 0))), ('no time', lambda m: setattr(m, 'pt', None)),
                        ('Radio', lambda m: setattr(m, 'radio', 1)), ('no track', lambda m: m.play([], 0))):
        m = now(); setup(m)
        hold(m, 90, 8)
        expect(not m.sets and not m.seeks and not m.cmds and 'playpause_quick_click' not in m.names(), f'{what}: a hold does nothing, no tap either ({m.sets}, {m.cmds})')
        expect(times(m) in ([], ['1:40', '-3:20']) or what in ('no length', 'no time', 'no track'), f'{what}: nothing scanned on the bar')
    m = now(); m.setword(pod.DATA['DMR_SERVERFLAG'][0], 1); hold(m, 90, 8)
    expect(not m.sets and not m.seeks and not m.cmds, 'DLNA: a hold does nothing')
    # the player stops mid-scan: no seek is sent to a stopped player
    m = now(); x, y = hold(m, 90, 6, up=False); m.status = 1
    for _ in range(5): tick(m)
    m.ptr('up', x, y, m.clock)
    expect(not m.sets and not m.seeks, f'stopped mid-scan: no seek ({m.sets})')
    # other levels: a hold of next is still a tap on release
    m = machine(songs=['Alpha']); m.open(); m.timers = []
    hold(m, 90, 8)
    expect(m.cmds and m.cmds[0][0] == 'next' and not m.sets, f'the main menu: a held next is a tap on release ({m.cmds}, {m.sets})')
    # the other sectors on Now Playing do not scan
    m = now(); hold(m, 180, 8)
    expect(m.cmds == [('playpause',)] and not m.sets, f'a held play / pause sector is a tap ({m.cmds}, {m.sets})')


class PCIM(IM):
    """The Pod machine over a card: opendir / readdir / __xstat / stdio over the dict self.fs, as test/pod/podcasts.py's PM does, and a deque that copies the records it is given."""
    def __init__(self):
        super().__init__()
        self.fs, self.mtime, self.dirs_, self.dh, self.fp = {}, {}, {'/mnt', '/mnt/mmc'}, {}, {}
        self.dent = self.alloc(300)

    def put(self, path, data=b'', mtime=0):
        self.fs[path] = data
        if mtime: self.mtime[path] = mtime
        d = path.rsplit('/', 1)[0]
        while d and d not in self.dirs_: self.dirs_.add(d); d = d.rsplit('/', 1)[0]
        self.present.add(path)

    def kids(self, path):
        return sorted({p.rsplit('/', 1)[1] for p in list(self.fs) + list(self.dirs_) if p != path and p.rsplit('/', 1)[0] == path})

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'opendir':
            path = self.read_cstr(a0)
            if path in self.dirs_: ret = self.alloc(8); self.dh[ret] = [self.kids(path), 0]
            else: ret = 0
        elif name == 'readdir':
            d = self.dh[a0]
            if d[1] < len(d[0]):
                nm = d[0][d[1]].encode('latin-1'); d[1] += 1
                self.u.mem_write(self.dent, bytes(300)); self.u.mem_write(self.dent + 11, nm + b'\0'); ret = self.dent
            else: ret = 0
        elif name == 'closedir':
            self.dh.pop(a0, None); ret = 0
        elif name == '__xstat':
            path = self.read_cstr(a1)
            if not (path in self.fs or path in self.dirs_): ret = 0xffffffff
            else:
                self.u.mem_write(a2, bytes(144)); self.setword(a2 + 0x40, self.mtime.get(path, 0)); self.setword(a2 + 0x30, len(self.fs.get(path, b''))); ret = 0
        elif name == 'memmove':
            self.u.mem_write(a0, bytes(self.u.mem_read(a1, a2))); ret = a0
        elif name == 'fopen' and self.read_cstr(a0) in self.fs and 'w' not in self.read_cstr(a1):
            h = self.alloc(4); self.fp[h] = [self.read_cstr(a0), 0]; ret = h
        elif name == 'fread' and a3 in self.fp:
            path, pos = self.fp[a3]; data = self.fs[path][pos:pos + a1 * a2]
            if data: self.u.mem_write(a0, data)
            self.fp[a3][1] += len(data); ret = len(data) // a1
        elif name == 'fseek' and a0 in self.fp:
            path, pos = self.fp[a0]; self.fp[a0][1] = {0: a1, 1: pos + a1, 2: len(self.fs[path]) + a1}[a2]; ret = 0
        elif name == 'fclose' and a0 in self.fp:
            self.fp.pop(a0); ret = 0
        elif name == '_deque_push_back':
            rec = self.alloc(REC_SIZE); self.u.mem_write(rec, bytes(self.u.mem_read(a1, REC_SIZE)))
            self.deques.setdefault(a0, []).append(rec); ret = 0
        if ret is not None:
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


def podcasts_tests(ctx):
    """Main menu > Podcasts: the shows with a file (the Podcasts page's order), a show's local episodes (newest first), the dot of an unplayed one, a tap plays the show's episodes as a queue."""
    expect = ctx.expect
    root = '/mnt/mmc/Podcasts'
    def card():
        m = PCIM()
        m.class_lists[O['CLASS_ALL_SONGS']] = []
        m.put(f'{root}/Alpha/a1.mp3', b'x', mtime=1000); m.put(f'{root}/Alpha/a2.mp3', b'x', mtime=2000)
        m.put(f'{root}/Beta/b1.mp3', b'x', mtime=5000)
        m.put(f'{root}/Meta/.show', b'M1PLUS-SHOW 1\ntitle=Meta Only\n')   # a show with no file: not listed
        m.open(); m.timers = []
        return m
    def go(m):
        m.turn(0, STEP_DEG * 2 + 5); m.tap(CX, CY)
    m = card()
    go(m); settle(m)
    texts = m.paint()[0]
    expect(rows_of(texts) == ['Beta', 'Alpha'] and 'Podcasts' in texts_of((texts,)), f'Podcasts: the shows with an episode file, newest first, the title bar ({rows_of(texts)})')
    m.tap(CX, CY)
    texts = m.paint()
    expect(pc_rows(texts[0]) == ['b1'] and 'Beta' in texts_of(texts), f'a show: its episodes, the show as the title ({rows_of(texts[0])})')
    # the episodes of Alpha, newest first, with the dot on both (nothing played)
    x, y = m.polar(0, 85); m.tap(x, y)
    m.turn(0, STEP_DEG * 2 + 5); m.tap(CX, CY)
    texts = m.paint()
    expect(pc_rows(texts[0]) == ['a2', 'a1'], f'Alpha: newest first ({rows_of(texts[0])})')
    dots = [f for f in texts[1] if 6 <= f[1] <= 9 and f[3] <= 8 and f[4] == 1 and f[2] >= BARH and f[2] < row_y(2)]
    expect(len(dots) == 16, f'both unplayed episodes have the dot, 8 rows each ({len(dots)} fills)')
    m.turn(0, STEP_DEG + 5)
    m.calls = []
    m.tap(CX, CY)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(len(sp) == 1 and sp[0][2:] == (O['CLASS_ALL_SONGS'], O['PLAY_MODE']) and m.played and len(m.played[0]) == 2 and m.played[1] == 1, f'a tap starts the show\'s episodes as an All Songs class queue at that row ({sp}, {m.played and m.played[1]})')
    expect(m.word(G_CLASS) == O['CLASS_ALL_SONGS'] and 'Now Playing' in texts_of(m.paint()), 'the class is All Songs (not folder playback) and the Pod\'s own Now Playing is in front')
    # the show's Episode Order: copied files by natural name (a10 is later than a2 whatever the dates), either way; the queue follows the rows
    def alpha(oldest):
        m = PCIM()
        m.class_lists[O['CLASS_ALL_SONGS']] = []
        for f, mt in (('a1.mp3', 1000), ('a2.mp3', 2000), ('a10.mp3', 500)): m.put(f'{root}/Alpha/{f}', b'x', mtime=mt)
        if oldest: assert m.call(PSYMS['pc_order_set'], a0=pc_hash('Alpha'), a1=1, count=30000000) == 1
        m.open(); m.timers = []
        go(m); m.tap(CX, CY)
        return m
    m = alpha(False)
    expect(pc_rows(m.paint()[0]) == ['a10', 'a2', 'a1'], f'newest first: a10, a2, a1 ({pc_rows(m.paint()[0])})')
    m = alpha(True)
    expect(pc_rows(m.paint()[0]) == ['a1', 'a2', 'a10'], f'oldest first: a1, a2, a10 ({pc_rows(m.paint()[0])})')
    m.turn(0, STEP_DEG + 5); m.calls = []
    m.tap(CX, CY)
    q = m.played
    expect(q and [m.read_cstr(m.word(r + O['REC_PATH'])).rsplit('/', 1)[1] for r in q[0]] == ['a1.mp3', 'a2.mp3', 'a10.mp3'] and q[1] == 1, f'oldest first: a tap on a2 queues a1, a2, a10 and starts at the second ({q and q[1]})')
    # a card with no podcasts: an empty Podcasts level
    m = PCIM(); m.class_lists[O['CLASS_ALL_SONGS']] = []; m.open(); m.timers = []
    go(m)
    texts = m.paint()[0]
    expect(rows_of(texts) == [m.tr('No downloaded episodes')], f'no Podcasts folder: only the empty line ({rows_of(texts)})')
    m.tap(CX, CY)
    expect(m.paint()[0] == texts, 'a press on the empty list does nothing')


def podcasts_pane_tests(ctx):
    """The main menu's Podcasts row: Podcasts is row 1 and opens its level, Music has no Podcasts row, the row shows its picture in the pane (No Podcasts under it when no show has an episode), the cover pane is back off the row."""
    expect = ctx.expect
    root = '/mnt/mmc/Podcasts'
    def card(episode):
        m = PCIM(); m.class_lists[O['CLASS_ALL_SONGS']] = []
        if episode: m.put(f'{root}/Alpha/a1.mp3', b'x', mtime=1000)
        m.images['ipod_podcasts'] = (PANE[2], PANE[3], bytes((200, 60, 20, 255)) * (PANE[2] * PANE[3]))   # a flat picture: the fade's mix is measurable
        m.open(); m.timers = []
        return m
    def pc_blits(m):   # the picture's blits: its bitmap_t is inside the page's state (ip.pc_img); the covers' pane-sized frame is a heap bitmap
        return [b for b in m.paint()[2] if b[2] == PANE and b[1] == (0, 0, PANE[2], PANE[3]) and PSYMS['ip'] <= b[0] < PSYMS['ip'] + 0x4000]
    def pane_px(m, x=80, y=120):   # the RGB of the pane's one full-pane blit (the covers' frame or the picture) at (x, y)
        b = [b for b in m.paint()[2] if b[2] == PANE and b[1] == (0, 0, PANE[2], PANE[3])]
        bmp = b[-1][0]
        q = m.u.mem_read(m.word(bmp + 0x14) + y * m.word(bmp) * 4 + x * 4, 3)
        return tuple(q)
    def fade(m, n=8):   # the fade's ticks (IP_FADE_TICK_MS each)
        for _ in range(n): tick(m, 50)
    m = card(False)
    expect(rows_of(m.paint()[0])[2] == m.tr('Podcasts') and m.tr('Podcasts') not in [m.tr(k) for k in MUSIC_KEYS], 'the main menu has Podcasts at row 1, Music has no Podcasts row')
    expect(not pc_blits(m) and not [t for t, _ in m.paint()[0] if t == m.tr('No Podcasts')], 'on the Music row: the cover pane, no picture, no No Podcasts')
    m.turn(0, STEP_DEG * 2 + 5)
    expect(m.loads.count('ipod_podcasts') == 1, f'moving to Podcasts loads its picture once ({m.loads})')
    expect(not pc_blits(m), 'right after the wheel step the covers stay (a fast turn past Podcasts does not flash its picture)')
    tick(m, O['IP_PC_PANE_MS'] - 50)
    expect(not pc_blits(m), 'the picture still waits before IP_PC_PANE_MS')
    covers = pane_px(m)
    tick(m, 50); tick(m, 50)
    mid = pane_px(m)
    expect(not pc_blits(m) and not [t for t, _ in m.paint()[0] if t == m.tr('No Podcasts')], 'the wait is over: the picture fades in over the covers (the frame, no picture blit or No Podcasts yet)')
    fade(m)
    pic = pane_px(m)
    expect(mid != covers and mid != pic and all(min(a, c) - 1 <= b <= max(a, c) + 1 for a, b, c in zip(covers, mid, pic)),
           f'mid-fade the pane is a mix of the covers and the picture ({covers} {mid} {pic})')
    texts = m.paint()[0]
    expect(len(pc_blits(m)) == 1 and [r for t, r in texts if t == m.tr('No Podcasts')] != [], 'the picture is drawn in the pane and, with no episode, No Podcasts')
    r = [r for t, r in texts if t == m.tr('No Podcasts')][0]
    expect(r[1] == O['IP_PC_TEXT_Y'] and r[0] >= O['IP_PANE_X'] and abs(r[0] + r[2] // 2 - (O['IP_PANE_X'] + O['IP_PANE_W'] // 2)) <= 2, f'No Podcasts is centred in the pane under the glyph ({r})')
    c = tick(m)
    expect(not [x for x in c if x[0] == 'loadLocalClassList' or x[:3] == ('bitmap_create_ex', O['IP_PANE_ART'], O['IP_PANE_ART'])] and m.loads.count('ipod_podcasts') == 1, 'the pane timer does no cover work and the picture is not loaded again')
    m.tap(CX, CY)
    expect(rows_of(m.paint()[0]) == [m.tr('No downloaded episodes')], 'selecting Podcasts opens the Podcasts level')
    m.tap(*m.polar(0, 85))
    expect(len(pc_blits(m)) == 1, 'MENU back to the main menu on the Podcasts row: the picture at once')
    m.turn(0, -(STEP_DEG * 2 + 5))
    tick(m, 50)
    expect(not pc_blits(m) and pane_px(m) != pic, 'off the row the picture fades out at once (no wait)')
    fade(m)
    texts = m.paint()[0]
    expect(not pc_blits(m) and not [t for t, _ in texts if t == m.tr('No Podcasts')], 'back on the Music row: the cover pane is back, no picture, no No Podcasts')
    m.turn(0, STEP_DEG * 4 + 5); tick(m, O['IP_PC_PANE_MS'])
    expect(not pc_blits(m), 'a turn straight past Podcasts never shows its picture')
    m = card(True)
    m.turn(0, STEP_DEG * 2 + 5); tick(m, O['IP_PC_PANE_MS']); fade(m)
    expect(len(pc_blits(m)) == 1 and not [t for t, _ in m.paint()[0] if t == m.tr('No Podcasts')], 'with an episode on the card the picture shows and No Podcasts does not')


def server_cover_tests(ctx):
    """A server track's Now Playing cover (ip_cover, docs/modules/subsonic.md): the source's own file (sba_rec_cover on the record), never the library album of the same artist and album; a cover on its way leaves
    the placeholder and is looked at again until it lands; a local track keeps the album's cache file."""
    expect = ctx.expect
    SBC = '/mnt/mmc/.m1plus/subsonic/covers/0123abcd-168.jpg'
    local = art_file(album_key('Artist', 'Album'))

    def server(cover, path='http://nd.example:4533/rest/stream.view?id=t5&t=tok&s=salt', rid=-5):
        m = machine(); m.open()
        m.files[local] = 4096; m.present.add(local); m.images['file://' + local] = (168, 168, bytes((200, 40, 40, 255)) * (168 * 168))   # the library has an album of that name and artist
        m.sbtrack[-5], m.sbcover[-5] = 't5', cover
        if cover[0] == 1: m.files[SBC] = 4096; m.present.add(SBC); m.images['file://' + SBC] = (168, 168, bytes((40, 40, 200, 255)) * (168 * 168))
        m.status = 2; m.pt = (10, 100)
        m.play([m.song('Remote', path=path, name='Remote.flac', rid=rid)], 0)
        m.warm = tick(m)   # (the page's first look at the new track)
        return m
    # (the main menu's cover pane takes the playing album's cache file too, ip_pane_want: a server track's pane takes none)
    loads = lambda c: [x[1] for x in c if x[0] == 'widget_load_image']
    m = server((1, SBC)); c = tick(m)
    expect('file://' + SBC in loads(c) and 'file://' + local not in loads(c), f'a server track: the server\'s cover, not the library album\'s cache file ({loads(c)})')
    m = server((0, None)); c = tick(m)
    expect('file://' + local not in loads(c) and 'file://' + SBC not in loads(c), f'a cover on its way: the placeholder, not the library album ({loads(c)})')
    asked = 0
    for _ in range(8): c = tick(m); asked += c.count(('sba_rec_cover', -5)); expect('file://' + local not in loads(c), 'and the library album is never taken while it waits')
    expect(asked >= 8, f'the source is asked again on every tick beyond the settle ticks ({asked})')
    m.sbcover[-5] = (1, SBC); m.files[SBC] = 4096; m.present.add(SBC); m.images['file://' + SBC] = (168, 168, bytes((40, 40, 200, 255)) * (168 * 168))
    c = tick(m); c += tick(m)
    expect('file://' + SBC in loads(c), 'the file landed: the cover is redone with it')
    m = server((-1, None)); c = tick(m)
    expect('file://' + local not in loads(c), 'a server track the server has no picture for: not the library album\'s cover')
    m = server((1, SBC), path='/mnt/mmc/m/1.flac', rid=7); m.sbtrack.clear(); c = m.warm + tick(m)
    expect('file://' + local in loads(c) and 'file://' + SBC not in loads(c), 'a local track: the album\'s cache file as before')




def unknown_album_tests(ctx):
    """getAllAlbum appends the "Unknown Album" row (id -1) to every non-empty list; payload cc_drop_unknown_album pops it unless a track lacks an album tag
    (`select * from songtable where album is null or album = '' limit 1`). The Pod's Albums rows and cc_albums (the lists of Albums, Cover Flow and the rest) both go through it."""
    expect = ctx.expect

    def world(untagged, libcstl=True):
        m = machine(albums=[('Kind of Blue', 'Miles Davis'), ('Homogenic', 'Bjork')], songs=['So What'])
        m.class_lists[O['CLASS_ALBUMS']].append(m.record(album='Unknown Album', artist='Unknown Artist', path='', title='', rid=-1))
        m.class_lists[O['CLASS_ALL_SONGS']] = [m.song('So What', album='Kind of Blue')] + ([m.song('Untitled', album='')] if untagged else [])
        if libcstl: m.install_libcstl()
        return m

    def pod_rows(m):
        m.open(); m.timers = []
        music(m)
        m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
        texts, _, _ = m.paint()
        return rows_of(texts)

    def cc_rows(m):
        h = m.call(PSYMS['cc_albums'], count=40000000)
        return [m.read_cstr(m.word(r + O['REC_ALBUM'])) for r in m.deques[h]] if h else []

    for untagged in (True, False):
        want = ['Kind of Blue', 'Homogenic'] + (['Unknown Album'] if untagged else [])
        what = 'a track has no album tag' if untagged else 'every track has an album'
        m = world(untagged)
        rows = pod_rows(m)
        expect(rows == want, f'Pod Albums, {what}: {want} ({rows})')
        expect(sum(1 for q in m.queries if 'album is null' in q) == 1, 'one untagged query for the list')
        m = world(untagged)
        rows = cc_rows(m)
        expect(rows == want, f'cc_albums, {what}: {want} ({rows})')
    m = world(False, libcstl=False)
    expect(pod_rows(m) == ['Kind of Blue', 'Homogenic', 'Unknown Album'] and not any('album is null' in q for q in getattr(m, 'queries', [])),
           'libcstl not the pinned one: the row stays, nothing is queried')
    m = world(False); m.__dict__['untagged_fails'] = True
    expect(pod_rows(m) == ['Kind of Blue', 'Homogenic', 'Unknown Album'], 'a failed query keeps the row')


def np_wheel_tests(ctx):
    """The Now Playing wheel as the iPod classic's: a turn sets the volume through stock's own volume dialog steps (each batch then stock's stop, the Pod window the context) and shows a
    volume bar with speakers instead of the times for IP_VOL_SHOW_MS; Line Out does nothing. The centre puts up the scrubber: a turn moves the target IP_SCRUB_S a step, only the knob
    while the finger is on the wheel; its release seeks once (mclSetSeek); the centre again or IP_SCRUB_IDLE_MS idle puts the progress bar back; nothing to scrub, the centre does nothing; play / pause is the bottom sector."""
    expect = ctx.expect
    VOL, LINEOUT = pod.DATA['G_VOLUME'][0], pod.DATA['LINEOUT_FLAG'][0]
    TX, TW, BY, BH, K = O['IP_NP_TRACK_X'], O['IP_NP_TRACK_W'], O['IP_NP_BAR_Y'], O['IP_NP_BAR_H'], O['IP_NP_KNOB']
    def now(status=2, pt=(100, 300)):
        m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
        songs = m.class_lists[O['CLASS_ALL_SONGS']]
        m.status = status; m.pt = pt; m.play([songs[0], songs[1]], 0)
        m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)   # the Now Playing row
        tick(m, 500)
        tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])   # the title bar has dropped in
        m.cmds, m.seeks, m.sets, m.calls, m.vol = [], [], [], [], []
        return m
    def times(m):
        return [n for n, _ in m.paint()[0] if len(n) >= 4 and n[-3] == ':' and n.lstrip('-')[:1].isdigit()]
    def fill_w(m):
        f = [f for f in m.paint()[1] if f[1] == TX and f[2] == BY + BH // 2 and f[4] == 1 and f[3] < TW]
        return f[0][3] if f else 0
    # volume up 3 steps: stock's +1 twice a step, then its stop, on the Pod window
    m = now()
    m.turn(0, STEP_DEG * 3 + 5)
    adds = [w for k, w in m.vol if k == 'add']
    expect(len(adds) == 3 * O['IP_VOL_STEPS'] and m.word(VOL) == 40 + 3 * O['IP_VOL_STEPS'] and [k for k, _ in m.vol].count('stop') == 3 and m.vol[-1][0] == 'stop' and len({w for _, w in m.vol}) == 1 and m.vol[0][1],
           f'a turn: the stock volume steps, {O["IP_VOL_STEPS"]} a wheel step, each followed by its stop, one window ({m.vol}, {m.word(VOL)})')
    SL = O['IP_SCRUB_SLIDE_MS']
    expect(times(m) == ['1:40', '-3:20'], f'the volume bar starts at the right edge: the progress bar still in place ({times(m)})')
    m.clock += SL // 2
    fills = m.paint()[1]
    sx = lambda f: (f[1] ^ 0x80000000) - 0x80000000
    vol = [sx(f) for f in fills if f[2] == BY + BH // 2 and f[4] == 1 and f[3] == TW * m.word(VOL) // 100]
    expect(len(times(m)) == 2 and vol and TX < vol[0] < O['IP_W'], f'halfway: the volume bar comes in from the right, the progress bar goes left ({times(m)}, {vol})')
    tick(m, SL)
    expect(times(m) == [] and fill_w(m) == TW * m.word(VOL) // 100, f'the volume bar instead of the times, filled to the volume ({times(m)}, {fill_w(m)})')
    expect(not m.cmds and not m.sets, 'no play / pause, no seek')
    tick(m, O['IP_VOL_SHOW_MS'] + 100)
    m.clock += SL // 2
    vol = [sx(f) for f in m.paint()[1] if f[2] == BY + BH // 2 and f[4] == 1 and f[3] == TW * m.word(VOL) // 100]
    expect(vol and TX < vol[0] < O['IP_W'], f'after IP_VOL_SHOW_MS the volume bar goes right, the progress bar comes back from the left ({vol})')
    tick(m, SL)
    expect(times(m) == ['1:40', '-3:20'] and fill_w(m) != TW * m.word(VOL) // 100, f'then the progress bar and the times again ({times(m)})')
    m.vol = []; m.turn(0, -(STEP_DEG * 2 + 5))
    expect([k for k, _ in m.vol].count('dec') == 2 * O['IP_VOL_STEPS'] and m.word(VOL) == 40 + O['IP_VOL_STEPS'], f'backwards: down ({m.vol})')
    # Line Out keeps its level
    m = now(); m.u.mem_write(LINEOUT, b'\x01'); m.turn(0, STEP_DEG * 3 + 5)
    expect(m.vol == [] and m.word(VOL) == 40 and times(m) == ['1:40', '-3:20'], f'Line Out: no step, no volume bar ({m.vol})')
    # the scrubber
    SL = O['IP_SCRUB_SLIDE_MS']
    m = now(); m.clock = 5000; m.tap(CX, CY)
    m.clock += SL // 2
    fills = m.paint()[1]
    tips = [f[1] for f in fills if f[2:5] == (BY + BH // 2 - K, 1, 1)]
    expect(len(times(m)) == 4 and fill_w(m) == 0 and tips and TX + TW * 100 // 300 < tips[0] < O['IP_W'],
           f'the centre: halfway the progress bar has gone left and the scrubber comes in from the right ({times(m)}, {tips})')
    expect(any((f[1] ^ 0x80000000) - 0x80000000 < TX and f[3] == TW * 100 // 300 and f[2] == BY + BH // 2 for f in fills), 'the progress bar, still filled, on its way out to the left (x signed)')
    tick(m, SL)
    expect(not m.cmds and times(m) == ['1:40', '-3:20'], f'the centre: no play / pause, the scrubber is up ({m.cmds})')
    fills = m.paint()[1]
    expect(any(f[1:5] == (TX + TW * 100 // 300, BY + BH // 2 - K, 1, 1) for f in fills), 'a diamond knob at the position, its tip K rows above the middle of the bar')
    kx = TX + TW * 100 // 300
    mid = [f[0] & 0xffffff for f in fills if f[1:5] == (kx - K + 1, BY + BH // 2, 2 * K - 1, 1)]
    expect(mid == [0xeb893d], f'the knob is the bar\'s blue, row for row ({[hex(c) for c in mid]})')
    refl = [f for f in fills if f[2] == BY + BH + 1 and f[1] <= kx <= f[1] + f[3] - 1 and f[3] < TW]
    expect(refl and refl[-1][0] & 0xffffff != mid[0] if mid else False, f'and a faded reflection under the bar ({refl})')
    expect(fill_w(m) == 0 and not any(f[1] == TX and f[2] == BY + BH // 2 and 0 < f[3] < TW for f in fills), 'the scrubber\'s track is empty, no fill')
    m.clock = 6000
    x, y = m.polar(0, 80); m.ptr('down', x, y, m.clock)
    for i in range(1, 12): x, y = m.polar((STEP_DEG * 3 + 5) * i / 11, 80); m.ptr('move', x, y, m.clock); tick(m, 150)
    expect(times(m) == ['1:46', '-3:14'] and m.vol == [], f'a turn moves the target {O["IP_SCRUB_S"]} s a step, no volume ({times(m)}, {m.vol})')
    expect(not m.sets, f'while the finger is on the wheel only the knob moves: no seek ({m.sets})')
    m.ptr('up', x, y, m.clock)
    expect(m.sets == [106], f'the release: one seek to the target ({m.sets})')
    m.clock += 50; m.tap(CX, CY)
    expect(m.sets == [106] and not m.cmds, f'the centre again: nothing more to seek, no play / pause ({m.sets}, {m.cmds})')
    m.clock += SL // 2
    tips = [f[1] for f in m.paint()[1] if f[2:5] == (BY + BH // 2 - K, 1, 1)]
    expect(len(times(m)) == 2 and tips and (tips[0] ^ 0x80000000) - 0x80000000 < TX + TW * 106 // 300, f'halfway: the scrubber goes left, the shuffle slider comes in from the right ({tips})')
    tick(m, SL)
    names = [n for n, _ in m.paint()[0]]
    expect(times(m) == [] and all(m.tr(k) in names for k in ('Off', 'Songs', 'Albums')), f'then the shuffle slider: Off, Songs, Albums ({names})')
    def chosen(m):
        m.paint()
        return [t for (t, _), st in zip(m.texts, m.text_styles) if st == 'label_ip_shuf']
    expect(chosen(m) == [m.tr('Off')], f'Off chosen, in the selection blue ({chosen(m)})')
    def boxes(m):
        m.paint()
        return {t: r for (t, r), st in zip(m.texts, m.text_styles) if t in (m.tr('Off'), m.tr('Songs'), m.tr('Albums'))}, \
            {st for (t, _), st in zip(m.texts, m.text_styles) if t in (m.tr('Off'), m.tr('Songs'), m.tr('Albums'))}
    def thumb(m):   # the thumb's top face row (one row under the rail's top, 2 px in from its left, a third of the rail less 4 wide): its left edge
        return [((f[1] ^ 0x80000000) - 0x80000000) - 1 for f in m.paint()[1] if f[3] == O['IP_SHUF_W'] // 3 - 4 and f[2] == BY + BH // 2 - O['IP_SHUF_H'] // 2 + 1]
    SX, SLOT = O['IP_SHUF_X'], O['IP_SHUF_W'] // 3
    before, styles = boxes(m)
    expect(styles <= {'label_ip_shuf', 'label_ip_np3'}, f'the names in left-aligned styles only, so a choice cannot shift them ({styles})')
    expect(thumb(m) == [SX + 1], f'the thumb over Off ({thumb(m)})')
    m.vol = []; m.turn(0, STEP_DEG + 5)
    m.clock += O['IP_SHUF_THUMB_MS'] // 2
    mid = thumb(m)
    expect(mid and SX + 1 < mid[0] < SX + SLOT + 1, f'halfway the thumb glides between Off and Songs ({mid})')
    tick(m, O['IP_SHUF_THUMB_MS'])
    expect(thumb(m) == [SX + SLOT + 1], f'then rests over Songs ({thumb(m)})')
    after, _ = boxes(m)
    expect(after == before, f'the names keep their boxes when the choice changes ({before}, {after})')
    expect(chosen(m) == [m.tr('Songs')] and m.vol == [], f'a turn forward: shuffle Songs, no volume ({chosen(m)}, {m.vol})')
    m.turn(0, STEP_DEG + 5)
    expect(chosen(m) == [m.tr('Albums')], f'again: Albums ({chosen(m)})')
    m.turn(0, STEP_DEG + 5)
    expect(chosen(m) == [m.tr('Albums')], 'the last choice stays')
    m.turn(0, -(STEP_DEG * 2 + 5))
    expect(chosen(m) == [m.tr('Off')], f'and back: Off ({chosen(m)})')
    m.clock |= 1; m.clock += 1; m.tap(CX, CY)   # an even clock: the slide's start (now | 1) is a millisecond ahead
    names = [n for n, _ in m.paint()[0]]
    expect(m.tr('Albums') in names, f'the centre again: the slide starts with the shuffle slider still in place ({names})')
    m.clock += SL // 2
    names = [n for n, _ in m.paint()[0]]
    expect(len(times(m)) == 2 and m.tr('Albums') in names, f'halfway: the slider goes left, the progress bar comes in from the right ({times(m)}, {names})')
    tick(m, SL)
    expect(times(m) == ['1:46', '-3:14'] and m.tr('Albums') not in [n for n, _ in m.paint()[0]], f'the centre again, no lyrics file: the progress bar ({times(m)})')
    m.vol = []; m.turn(0, STEP_DEG + 5)
    expect(len(m.vol) == O['IP_VOL_STEPS'] + 1, 'and the wheel is the volume again')
    # the scrubber's idle end
    m = now(); m.seek_moves = False; m.tap(CX, CY); m.turn(0, -(STEP_DEG * 2 + 5))
    tick(m, O['IP_SCRUB_IDLE_MS'] + 100)
    m.clock += SL // 2
    tips = [(f[1] ^ 0x80000000) - 0x80000000 for f in m.paint()[1] if f[2:5] == (BY + BH // 2 - K, 1, 1)]
    expect(len(times(m)) == 4 and tips and tips[0] < TX + TW * 96 // 300 - O['IP_W'] // 4, f'idle: halfway the scrubber goes left, the progress bar comes in from the right like every view change ({tips})')
    tick(m, SL)
    expect(m.sets and m.sets[-1] == 96 and times(m) == ['1:36', '-3:24'], f'idle: the last seek, the target held on the bar ({m.sets}, {times(m)})')
    m.vol = []; m.turn(0, STEP_DEG + 5)
    expect(m.vol, 'then a turn is the volume')
    # nothing to scrub (stopped): the centre does nothing, the turn is still the volume
    m = now(); m.status = 1; m.turn(0, STEP_DEG + 5)
    expect(not m.cmds and not m.sets and len(m.vol) == O['IP_VOL_STEPS'] + 1, f'stopped: the turn is the volume ({m.cmds}, {m.sets}, {m.vol})')
    m.tap(CX, CY); tick(m, SL)
    expect(not m.cmds and not m.sets and m.tr('Albums') in [n for n, _ in m.paint()[0]], f'and the centre skips the scrubber: the shuffle slider ({m.cmds}, {m.sets})')
    # the bottom sector plays / pauses
    m = now(); x, y = m.polar(180, 85); m.tap(x, y)
    expect(m.cmds == [('playpause',)], 'the bottom sector: play / pause')


def np_lyrics_tests(ctx):
    """The lyrics view (Now Playing's centre after the scrubber and the shuffle slider, the iPod's plain text): the track's .lrc without its time tags and tag lines, blank
    lines kept single, long lines wrapped at a space; the title bar names the song; a small cover, the album and the artist above the lines; the wheel scrolls the whole
    page a line a step with a scroll bar at the right edge; the centre again goes back to the progress bar; no .lrc, no lyrics view."""
    expect = ctx.expect
    SL, LINE, LX = O['IP_SCRUB_SLIDE_MS'], O['IP_LY_LINE'], O['IP_LY_X']
    def now(lrc=None):
        m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
        if lrc is not None:
            m.files['/mnt/mmc/m/0.lrc'] = len(lrc); m.contents = {'/mnt/mmc/m/0.lrc': lrc}
        songs = m.class_lists[O['CLASS_ALL_SONGS']]
        m.status = 2; m.pt = (100, 300); m.play([songs[0], songs[1]], 0)
        m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)   # the Now Playing row
        tick(m, 500)
        tick(m, O['IP_BAR_WAIT_MS'] + O['IP_BAR_DROP_MS'])   # the title bar has dropped in
        for _ in range(3): m.tap(CX, CY); tick(m, SL + 50)   # the scrubber, the shuffle slider, the lyrics
        return m
    lrc = ('\ufeff[ar:Someone]\r\n[ti:Alpha]\r\n[00:01.00]First line\r\n[00:02.50][00:40.00] Second line\r\n[00:03.00]\r\n\r\n[00:04.00]Third line\r\n'
           '[00:05.00]' + ' '.join(['word%02d' % i for i in range(16)]) + '\r\n').encode()
    m = now(lrc)
    texts = m.paint()[0]
    rows = [(t, r) for t, r in texts if r[0] == LX]
    names = [t for t, _ in texts]
    expect([t for t, _ in rows][:3] == ['First line', 'Second line', 'Third line'], f'the lines without their time tags, the tag lines dropped ({names})')
    expect(not any('[' in t for t in names), 'no tag shown')
    y = {t: r[1] for t, r in rows}
    expect(y['Second line'] - y['First line'] == LINE and y['Third line'] - y['Second line'] == 2 * LINE, f'a line a row, two blank lines one gap ({y})')
    wrapped = [t for t, _ in rows][3:]
    expect(len(wrapped) > 1 and ' '.join(w.strip() for w in wrapped) == ' '.join(['word%02d' % i for i in range(16)]), f'a long line wrapped at spaces ({wrapped})')
    expect('Alpha' in names and m.tr('Now Playing') not in names, 'the title bar names the song')
    expect(not [n for n in names if len(n) >= 4 and n[-3] == ':' and n.lstrip('-')[:1].isdigit()], 'no progress bar or times')
    # the wheel scrolls the whole page a line a step (a long file)
    m = now(''.join('[00:%02d.00]Line %02d\n' % (i, i) for i in range(40)).encode())
    y0 = {t: r[1] for t, r in m.paint()[0]}
    fills = m.paint()[1]
    bar = [f for f in fills if f[1] == O['IP_W'] - O['IP_LY_SB_W'] - 2 and f[3] == O['IP_LY_SB_W']]
    expect(len(bar) == 2, f'a scroll bar at the right edge: track and thumb ({bar})')
    m.turn(0, STEP_DEG * 3 + 5)
    y1 = {t: r[1] for t, r in m.paint()[0]}
    expect(y1.get('Line 05') == y0['Line 05'] - 3 * LINE and m.vol == [], f'three steps: three lines up, no volume ({y0.get("Line 05")}, {y1.get("Line 05")})')
    m.turn(0, -(STEP_DEG * 9 + 5))
    expect({t: r[1] for t, r in m.paint()[0]}.get('Line 05') == y0['Line 05'], 'back: not past the top')
    m.tap(CX, CY); tick(m, SL + 50)
    names = [t for t, _ in m.paint()[0]]
    expect('1:40' in names and m.tr('Now Playing') in names, f'the centre again: the progress bar, the title Now Playing ({names})')
    # tags only: no lyrics view
    m = now(b'[ar:Someone]\n[ti:Alpha]\n')
    names = [t for t, _ in m.paint()[0]]
    expect('1:40' in names, f'a .lrc with no text: the centre goes from the shuffle slider back to the progress bar ({names})')


SECTIONS = [angle_tests, asset_tests, menu_tests, open_tests, paint_tests, wheel_tests, feel_tests, tap_tests, nav_tests, stale_tests, playing_indicator_tests, music_menu_tests, genre_composer_tests, root_shortcut_tests, now_row_tests, menu_padding_tests, rich_rows_tests, row_art_tests, playlist_rows_tests, now_material_tests, classic_material_tests, split_menu_tests, pane_tests, server_cover_tests, shuffle_tests, settings_tests, i18n_tests, appearance_tests, transition_tests, fresh_art_tests, pane_sharp_tests, reference_nav_tests, shadow_slide_tests, now_steady_tests, np_pending_tests, scan_tests, np_wheel_tests, np_lyrics_tests, podcasts_tests, podcasts_pane_tests, unknown_album_tests]

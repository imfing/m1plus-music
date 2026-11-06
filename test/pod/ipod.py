"""The virtual iPod Classic (patch/ipod.c, tools/pod_ui.py build_ipod_page, tools/mod_icons.py ipod_wheel, docs/modules/ipod.md): the menu item, the asset (a fullscreen
320 x 480 window, the screen view and the wheel's touch view, the hit test with demo's own widget_find_target, the wheel picture), the wheel's angle math against math.atan2,
the page's open / destroy / background / foreground, the paint of the main menu, the lists, the title bar and Now Playing, the wheel (one row per 15 degrees, reversal hysteresis, the chord dead zone, tiers on long lists, the hard stop at the ends, the centre
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
STYLES = ('label_ip_row', 'label_ip_sel', 'label_ip_title', 'label_ip_small', 'label_ip_subsel', 'label_ip_np1', 'label_ip_np2', 'label_ip_time', 'label_ip_val', 'label_ip_np3')
MAIN_KEYS = ['Music', 'Cover Flow', 'Podcasts', 'Radio', 'Shuffle Songs', 'Now Playing', 'cdrippersettings']
MUSIC_KEYS = ['Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Shuffle Songs']
TRAPS = ('coverflow_open',)
SET_KEYS = ['Shuffle', 'Repeat', 'Appearance']
PANE = (O['IP_PANE_X'], 0, O['IP_PANE_W'], O['IP_SCREEN_H'])


def sel_colour(rgb): return 0xff000000 | rgb


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
        self.album_tracks, self.opened = {}, []
        self.window = WIN
        self.top_main = WIN
        self.load_image = 0
        self.fail_projection = False
        self.canvas = self.alloc(0x80)
        self.styles, self.origins, self.clip_frames = {}, [], []
        self.img_ox = []   # the canvas origin of each canvas_draw_image, parallel to blits
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
        self.radio = 0   # a station connects or plays (patch/radio.h rd_running); Radio Now Playing opens (rn_open_if_active) only then
        for n in ('rd_running', 'rn_open_if_active'): self.handlers[PSYMS[n]] = n
        for n in ('mclGetPlayStatus', 'playpause_quick_click', 'next_quick_click', 'prev_quick_click', 'loadAlbumdetailList', 'get_playtimeandlength'):
            self.handlers[pod.FUNCTIONS[n][2]] = n
        self.stock_songlist = True
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
            self.clip_frames.append(tuple(self.word(self.canvas + o) for o in (O['CANVAS_OX'], 16, 24)))
        if name in ('canvas_measure_text', 'canvas_draw_text_in_rect'):
            chars = list(struct.unpack(f'<{a2}I', u.mem_read(a1, 4 * a2))) if a2 else []
            if name == 'canvas_measure_text':
                w = float(sum(16 if c >= 0x2e80 or c == 0x2026 else 8 for c in chars))
                u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); self.measures.append(a2)
            else:
                self.texts.append((''.join(map(chr, chars)), struct.unpack('<4i', u.mem_read(a3, 16)))); self.text_styles.append(self.cur_style)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'bitmap_create_ex' and self.fail_projection and (a0, a1) == (O['IP_ART'], O['IP_NP_REFLECT']):
            self.calls.append(('bitmap_create_ex', 0)); ret = 0
        elif name in TRAPS: self.calls.append((name,)); self.opened.append(name); ret = 0
        elif name == 'mclGetPlayStatus': ret = self.status
        elif name == 'rd_running': ret = self.radio
        elif name == 'rn_open_if_active': self.calls.append((name,)); ret = self.radio
        elif name == 'playpause_quick_click':
            self.calls.append(('playpause_quick_click',)); self.cmds.append(('playpause',)); self.status = 2 if self.status != 2 else 3; ret = 1
        elif name in ('next_quick_click', 'prev_quick_click'):
            self.calls.append((name, a1)); self.cmds.append((name[:4], self.word(a0 + 8), a1)); ret = 1
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
            self.clock += 301
            self.call(PSYMS['ip_tick'], count=40000000)
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.texts, self.fills, self.blits, self.text_styles, self.img_ox = [], [], [], [], []
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
def rows_of(texts): return [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if BARH <= r[1] < 240 and ((r[0] == 62 and (r[1] - BARH) % O["IP_TALL_H"] == 4) or (r[0] in (8, 10) and (r[1] - BARH) % ROWH in (0, 4)))]


def pc_rows(texts):   # the episode rows: their text is indented for the dot
    return [t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if BARH <= r[1] < 240 and r[0] == 8 + 16 and (r[1] - BARH) % ROWH == 0]


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
    expect(O['IP_STEP'] == 240 and STEP_DEG == 15.0, 'one wheel step is 15 degrees, 24 to a turn (the real wheel is about 15-20)')


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
    expect(BARH + ROWS * ROWH <= O['IP_SCREEN_H'] < BARH + (ROWS + 1) * ROWH and ROWS == 7 and ROWH == 30 and BARH == 24 and BARH + O['IP_TALL_ROWS'] * O['IP_TALL_H'] == O['IP_SCREEN_H'], 'a 24 px title bar, seven 30 px text rows (no partial row) or four 54 px cover rows fill the 240 px screen')
    expect(WY + WD <= 480 and WX + WD <= 320 and WY >= 240, 'the wheel is inside the lower 240 px')
    expect(mod_icons.IPOD_WHEEL_D == WD and mod_icons.IPOD_HUB_R == HUB == 45 and RING == WD // 2, 'the wheel picture\'s numbers are offsets.inc\'s: a 220 px ring, a 90 px centre button')
    head = open(os.path.join(mod_icons.PNG, 'ipod_podcasts.png'), 'rb').read(26)   # IHDR: width, height, bit depth, colour type (2 = RGB: no alpha channel)
    expect('ipod_podcasts' in mod_icons.IPOD and struct.unpack('>II', head[16:24]) == (O['IP_PANE_W'], O['IP_PANE_H']) and head[24:26] == bytes((8, 2)),
           'the Podcasts pane picture is the pane\'s 160 x 240, opaque RGB')
    # the style labels: hidden, insensitive, in the colour of what they sit on, the sizes of the mock
    want = {'label_ip_row': (18, '#000000'), 'label_ip_sel': (18, '#FFFFFF'), 'label_ip_title': (16, '#000000'),
            'label_ip_small': (16, '#666666'), 'label_ip_subsel': (16, '#FFFFFF'), 'label_ip_np1': (18, '#000000'), 'label_ip_np2': (16, '#666666'), 'label_ip_time': (15, '#000000'),
            'label_ip_val': (16, '#0C62D2'), 'label_ip_np3': (14, '#666666')}
    expect(all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' and by[n].get('style:normal:font_size') == str(px)
               and by[n].get('style:normal:text_color') == col for n, (px, col) in want.items()), 'ten hidden, insensitive style labels: the sizes (rows 18, title 16, subtitles and values 16, Now Playing 18 / 16 / 14, times 15) and colours')
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
    expect(item == 19 == len(P.ITEMS) - 5 and P.ITEMS[item].action == P.ACT_IPOD == 22 and P.ID_CHARS[item] == 'k' and item not in P.DEFAULT_MENU,
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
    expect(rows == [m.tr(k) for k in MAIN_KEYS], f'the eight main menu rows in the iPod order, in the language of the player ({rows})')
    ys = sorted(r[1] for t, r in texts if t in rows)
    expect(ys == [BARH + i * ROWH for i in range(len(MAIN_KEYS))], 'on a 27 px pitch from the title bar')
    expect(all(r[2] == O['IP_SPLIT_X'] - O['IP_TEXT_X'] - 22 for t, r in texts if t in rows), 'in the list\'s width: the left pane of the split screen')
    expect(any(f[0] == 0xfff8dd9a and f[2] == BARH and f[3] == O['IP_SPLIT_X'] for f in fills), 'the selected row starts with its highlight')
    grad = [f for f in fills if f[2] >= BARH and f[3] == O['IP_SPLIT_X'] and f[4] == 1]
    expect(len(grad) == ROWH and grad[0][0] == 0xfff8dd9a and grad[-1][0] == 0xff814f15 and [g[2] for g in grad] == list(range(BARH, BARH + ROWH)),
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
    expect(len(chev) == 9 and all(f[0] == 0xffffffff and BARH <= f[2] < BARH + ROWH for f in chev), f'one chevron, on the selected row ({len(chev)} fills)')
    # another language
    m.set_language('ru_RU')
    t2 = rows_of(m.paint()[0])
    expect(t2[:2] == [pod_i18n.TEXT[k]['ru_RU'] for k in MAIN_KEYS[:2]], f'the rows follow Settings > Language ({t2[:3]})')


def wheel_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[(f'Album {i}', 'A') for i in range(5)], songs=[f'Song {i:02d}' for i in range(30)])
    m.open(); m.timers = []
    def selected():
        texts, fills, _ = m.paint()
        ys = [f[2] for f in fills if f[4] == 1 and f[3] == (O['IP_SPLIT_X'] if not m.in_list else 320) and f[2] >= BARH]
        return min(ys) if ys else None
    m.in_list = False
    def row():
        y = selected()
        return None if y is None else (y - BARH) // ROWH
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
    expect(row() == 6, 'and at the last root row')
    # a small turn is no step, a turn at the edge of the dead zone / outside
    m = machine(); m.open(); m.timers = []; m.in_list = False
    m.turn(30, 30 + 12, r=80)
    expect(row() == 0, 'a 12 degree wobble is no step')
    m.turn(30, 30 + 200, r=10)
    expect(row() == 0, 'a finger inside the dead zone (a touch that began on the centre button) turns nothing')
    m.turn(30, 30 + 54 + 1, r=HUB + 5)
    expect(row() == 3, 'a finger just outside the centre button turns the wheel')
    m.turn(30, 30 + 54 + 1, r=RING - 3)
    expect(row() == 6, 'and one at the rim stays at the last row')
    # a drag that starts on the centre button turns nothing
    m = machine(); m.open(); m.timers = []; m.in_list = False
    m.turn(30, 30 + 100, r=30)
    expect(row() == 0, 'a drag that begins on the centre button turns nothing (and is no tap)')
    expect('start_player' not in m.names() and not m.opened and m.names().count('loadLocalClassList') == 0, 'and selects nothing')
    # a long list: the cursor leads the window
    m = machine(songs=[f'Song {i:02d}' for i in range(30)]); m.open(); m.timers = []
    music(m)
    m.in_list = False
    m.turn(0, STEP_DEG * 3 + 5)   # Songs (row 3)
    m.tap(CX, CY)
    m.in_list = True
    texts, fills, _ = m.paint()
    expect(rows_of(texts)[:2] == ['Song 00', 'Song 01'] and 'Songs' in [t for t, _ in texts], 'Songs: the library list, the title Songs')
    m.turn(0, STEP_DEG * 12 + 5)
    texts, fills, _ = m.paint()
    rows = rows_of(texts)
    expect(row() == 6 and rows[0] == 'Song 06' and rows[-1] == 'Song 12' and len(rows) == 7, f'twelve steps down: seven plain 30 px rows, the cursor on the last ({rows[0]}..{rows[-1]}, row {row()})')
    m.turn(0, -(STEP_DEG * 4 + 5))
    rows = rows_of(m.paint()[0])
    expect(row() == 2 and rows[0] == 'Song 06', 'four back: the window stays while the cursor is inside it')
    m.turn(0, -(STEP_DEG * 8 + 5))
    rows = rows_of(m.paint()[0])
    expect(row() == 0 and rows[0] == 'Song 00' or (rows[0] == 'Song 00' and row() == 0), f'past the top of the window: it scrolls up with the cursor ({rows[0]}, {row()})')


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
        texts, fills, _ = m.paint()
        return rows_of(texts), [t for t, r in texts if r[0] != 10 or r[1] < BARH]
    # Albums
    step_to(1); centre()
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
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    texts, fills, blits = m.paint()
    tx = [t_ for t_, _ in texts]
    expect(['Blue in Green', 'Miles Davis', 'Kind of Blue', '2 / 3', '01:47', '-03:18', 'Now Playing'] == [x for x in tx if x in ('Blue in Green', 'Miles Davis', 'Kind of Blue', '2 / 3', '01:47', '-03:18', 'Now Playing')],
           f'Now Playing: title, artist, album, "2 / 3", elapsed and remaining, the title bar ({tx})')
    TX, TW, BY, BH = O['IP_NP_TRACK_X'], O['IP_NP_TRACK_W'], O['IP_NP_BAR_Y'], O['IP_NP_BAR_H']
    fw = TW * 107 // 305
    bar = [f for f in fills if f[1] == TX and f[3] == fw and BY <= f[2] < BY + BH and f[4] == 1]
    expect(len(bar) == BH, f'the progress fill is a {BH} px bar, 107 of 305 s of the 204 px track ({len(bar)} rows of {fw} px)')
    expect(any(f[1:5] == (TX + fw, BY + BH // 2, TW - fw, 1) for f in fills) and any(f[1:5] == (TX + fw, BY, TW - fw, 1) and f[0] == 0xffc6c6c6 for f in fills),
           'the white track (edge rows in the outline colour) carries on after the fill')
    COVER, REFL = (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_ART'], O['IP_ART']), (O['IP_NP_ART_X'], O['IP_NP_ART_Y'] + O['IP_ART'], O['IP_ART'], O['IP_NP_REFLECT'])
    cov = [b for b in blits if b[2] == COVER]
    expect(len(cov) == 1 and cov[0][1] == (0, 0, O['IP_ART'], O['IP_ART']) and len([b for b in blits if b[2] == REFL]) == 1 and [b for b in blits if b[2] == REFL][0][1] == (0, 0, O['IP_ART'], O['IP_NP_REFLECT']),
           'the cover is one straight 1:1 copy of its square (every row the source row, unshifted: no tilt, no seam) and the reflection under it one copy of its bitmap')
    refl = [f for f in fills if f[2] >= BY + BH and f[1] == TX and f[3] == fw and f[4] == 1]
    expect(len(refl) == O['IP_NP_BAR_REFLECT'] and refl[0][0] != refl[-1][0], 'a short reflection of the bar fades out under it')
    rect = {t_: r for t_, r in texts}
    expect(rect['01:47'][0] == 8 and rect['-03:18'][0] + rect['-03:18'][2] - 2 == 312 and rect['01:47'][1] == rect['-03:18'][1], 'zero padded elapsed and remaining in the 50 px side columns, on one line')
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
    expect(rows_of(m.paint()[0]) == ['Miles Davis', 'Bjork'] and min(f[2] for f in sel) == BARH + ROWH, 'MENU from there returns to Artists with the cursor where it was (on Bjork)')
    # Songs
    m = machine(songs=['So What', 'Freddie']); m.open(); m.timers = []
    music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    m.turn(0, 23); m.tap(CX, CY)
    expect(m.played and m.played[1] == 1 and ('start_player', 1, O['CLASS_ALL_SONGS'], O['PLAY_MODE']) in m.calls, f'Songs: a track plays with the library class ({m.calls[-4:]})')
    # Playlists: the id in classinfo[1], class 0xff13
    m = machine(playlists=['Road', 'Gym']); m.open(); m.timers = []
    music(m)
    m.playlist_songs = {7: [m.song('R1', rid=601, path='/mnt/mmc/m/1.flac'), m.song('R2', rid=602, path='/mnt/mmc/m/1.flac', name='2.flac')], 8: [m.song('G1', rid=603)]}
    m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY); calls = list(m.calls)
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
    expect(m.cmds == [('playpause',)], 'the centre button on Now Playing plays / pauses')


def stale_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Kind of Blue', 'Miles Davis')], songs=['So What']); m.open(); m.timers = []
    music(m)
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
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
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(m.tr('No albums') in [t for t, _ in m.paint()[0]], 'an empty albums list says so')
    m.tap(CX, CY)
    expect(not m.cmds and 'start_player' not in m.names() and 'loadAlbumdetailList' not in m.names(), 'and a tap on it does nothing')
    for steps, key in ((2, 'No artists'), (3, 'No songs'), (4, 'No playlists')):
        m = machine(); m.open(); m.timers = []
        music(m)
        m.turn(0, steps * STEP_DEG + 5); m.tap(CX, CY)
        expect(m.tr(key) in [t for t, _ in m.paint()[0]], f'an empty {key} list says so')
    # a track that is not on the card
    m = machine(albums=[('Kind of Blue', 'Miles Davis')]); m.open(); m.timers = []
    music(m)
    m.present.discard('/mnt/mmc/m/Kind of Blue-0.flac')
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY); m.tap(CX, CY); m.calls = []; m.tap(CX, CY)
    expect('start_player' not in m.names() and any(c[0] == 'toast' for c in m.calls), 'a track whose file is gone: the stock message box, nothing started')


def playing_indicator_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['First', 'Second']); m.open(); m.timers = []
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][1]], 0)
    music(m)
    m.turn(0, 3 * STEP_DEG + 5); m.tap(CX, CY)
    m.images['ipod_playing'] = (28, 28, bytes((255, 255, 255, 255)) * 784)
    S = O['IP_PLAY_PX']
    spot = lambda row: (320 - O['IP_TEXT_X'] - S, BARH + row * ROWH + (ROWH - S) // 2, S, S)
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
    expect([t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if r[0] == 8 and BARH <= r[1] < 240] ==
           [m.tr(k) for k in MAIN_KEYS], 'root shortcuts use the narrower margin')
    m.tap(CX, CY)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in ('Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Shuffle Songs')], 'Music contains the library entries')


def root_shortcut_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['First']); m.present.add('/mnt/mmc/m/0.flac'); m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'root has the six shortcuts')
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect('Cover Flow' in texts_of(m.paint()), 'root Cover Flow opens its own level')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0])[1] == m.tr('Cover Flow'), 'MENU returns to root after Cover Flow')
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    expect(m.played is not None and len(m.played[0]) == 1 and m.read_cstr(m.word(m.played[0][0] + O['REC_TITLE'])) == 'First' and m.mode == 2 and 'Now Playing' in texts_of(m.paint()), 'root Shuffle Songs starts the library queue')
    m.tap(*m.polar(0, 85))
    expect(rows_of(m.paint()[0])[4] == m.tr('Shuffle Songs'), 'MENU returns to the root shuffle shortcut')


def radio_now_tests(ctx):
    """The main menu's Now Playing row while a station plays: shown (nothing local plays), and it opens Radio Now Playing instead of the Pod's own screen."""
    expect = ctx.expect
    m = machine(songs=['First']); m.status = 0; m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS if k != 'Now Playing'], 'nothing plays: no Now Playing row')
    m.radio = 1; m.timers = []
    m.call(PSYMS['ip_tick'], count=40000000)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'a station plays: the row is there')
    m.turn(0, STEP_DEG * 5 + 5); m.calls = []; m.tap(CX, CY)
    expect(('rn_open_if_active',) in m.calls, 'the row asks Radio Now Playing first')
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in MAIN_KEYS], 'and the Pod stays on its main menu (no Now Playing screen of its own)')
    m = machine(songs=['First']); m.status = 2; m.open(); m.timers = []
    m.turn(0, STEP_DEG * 5 + 5); m.calls = []; m.tap(CX, CY)
    expect(('rn_open_if_active',) in m.calls and 'Now Playing' in texts_of(m.paint()) and rows_of(m.paint()[0]) != [m.tr(k) for k in MAIN_KEYS], 'a local track and no station: the row pushes the Pod\'s Now Playing screen')


def menu_padding_tests(ctx):
    expect = ctx.expect
    for step in (0, 1, 2, 3, 4):
        m = machine(albums=[('Album', 'Artist')], artists=['Artist'], songs=['Song'], playlists=['List']); m.open(); m.timers = []; music(m)
        if step: m.turn(0, STEP_DEG * step + 5)
        if step: m.tap(CX, CY)
        texts = m.paint()[0]
        rows = [r for t, r in texts if BARH <= r[1] < 240 and r[0] in (8, 10, 62)]
        expected = 62 if step in (1, 4) else 8
        expect(rows and all(r[0] == expected for r in rows), f'level {step} aligns its text after the shared leading cover inset')
    m = machine(); m.open(); m.timers = []; m.turn(0, STEP_DEG * 6 + 5); m.tap(CX, CY)
    expect(all(r[0] == 8 for t, r in m.paint()[0] if t in ('Shuffle', 'Repeat')), 'Settings labels use the shared inset')
    m = machine(); m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(any(t == m.tr('No albums') and r[0] == 8 for t, r in m.paint()[0]), 'empty messages use the shared inset')


def rich_rows_tests(ctx):
    expect = ctx.expect
    m = machine(songs=[f'Song {i:02d}' for i in range(8)]); m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
    texts, fills, blits = m.paint()
    expect([t for t, r in sorted(texts, key=lambda tr: tr[1][1]) if t.startswith('Song ')] == [f'Song {i:02d}' for i in range(7)] and all(r[0] == O['IP_TEXT_X'] for t, r in texts if t.startswith('Song ')),
           f'Music > Songs is a plain list: seven 30 px text rows, no cover, no subtitle ({[(t, r) for t, r in texts if t.startswith("Song ")]})')
    expect(not any(t == 'Artist · Album' for t, r in texts) and not blits, 'no artist line and no cover is drawn')
    work = [x for _ in range(6) for x in tick(m) if x[0] in ('cc_build_open', 'loadLocalClassList') or x[:3] == ('bitmap_create_ex', 54, 54)]
    expect(not work, f'and the page timer does no cover work for a song list ({work})')
    m.turn(0, STEP_DEG * 7 + 5)
    texts, fills, _ = m.paint()
    expect('Song 07' in [t for t, r in texts] and 'Song 00' not in [t for t, r in texts], 'scrolling keeps the cursor visible in a seven-row window')


def row_art_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Album', 'Artist')]); key = album_key('Artist', 'Album'); path = art_file(key)
    m.present.add(path); m.files[path] = 4096
    m.images['file://' + path] = (48, 48, bytes((50, 100, 150, 255)) * (48 * 48))
    m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    m.calls = []; tick(m); tick(m)
    expect(any(c[0] == 'widget_load_image' and c[1] == 'file://' + path for c in m.calls), 'a visible album cover decodes on the page timer')
    m.calls = []; _, _, blits = m.paint()
    expect(any(b[2] == (0, BARH, 54, 54) for b in blits), 'the cached cover is drawn in its row')
    expect(not any(c[0] in ('widget_load_image', 'bitmap_create_ex', 'loadLocalClassList') for c in m.calls), 'paint performs no decode, allocation or query')


def playlist_art_tests(ctx):
    expect = ctx.expect
    quadrants = {2: (0, 1, 1, 0), 3: (0, 1, 2, 0), 4: (0, 1, 2, 3)}
    colours = [(40, 70, 100, 255), (90, 110, 130, 255), (140, 160, 180, 255), (190, 210, 230, 255)]
    for count, sources in quadrants.items():
        m = machine(playlists=['Mix'])
        m.playlist_songs = {7: [m.song(f'Song {i}', album=f'Album {i}', rid=600 + i) for i in range(count)]}
        for i in range(count):
            path = art_file(album_key('Artist', f'Album {i}'))
            m.present.add(path); m.files[path] = 4096
            m.images['file://' + path] = (24, 24, bytes(colours[i]) * 24 * 24)
        m.open(); m.timers = []; music(m); m.turn(0, STEP_DEG * 4 + 5); m.tap(CX, CY)
        for _ in range(8): tick(m)
        _, _, blits = m.paint()
        cover = next(b[0] for b in blits if b[2] == (0, BARH, 54, 54))
        pixels = m.bitmaps[cover][0]
        actual = [bytes(m.u.mem_read(pixels + (y * 54 + x) * 4, 4)) for x, y in ((10, 10), (40, 10), (10, 40), (40, 40))]
        expect(actual == [bytes(colours[i]) for i in sources], f'a {count}-album playlist fills all four mosaic quadrants')


def now_material_tests(ctx):
    expect = ctx.expect
    m = machine(songs=['Song']); m.open(); m.timers = []
    A, R = O['IP_ART'], O['IP_NP_REFLECT']
    src = m.alloc(A * A * 4); dst = m.alloc(A * R * 4)
    for y in range(A):
        for x in range(A): m.setword(src + 4 * (y * A + x), 0xff000000 | x | y << 8)
    m.call(PSYMS['ip_reflect'], a0=src, a1=dst, count=40000000)
    pixel = lambda x, y: m.word(dst + 4 * (y * A + x))
    mix = lambda c, a: 255 + int((c - 255) * a / 255)
    a0 = R * 77 // R
    expect(pixel(0, 0) & 255 == mix(0, a0) and pixel(100, 0) & 255 == mix(100, a0) and pixel(0, 0) >> 8 & 255 == mix(A - 1, a0) and pixel(0, 0) >> 24 == 255,
           'the reflection starts as the cover\'s last row, mirrored, 30 % opaque on white')
    expect(pixel(0, 5) >> 8 & 255 == mix(A - 6, (R - 5) * 77 // R), 'row d is the cover\'s row A - 1 - d')
    rows = [pixel(0, y) & 255 for y in range(R)]
    expect(rows == sorted(rows) and rows[-1] > 245 and len(rows) == 20, f'the reflection fades out to nearly white in 20 rows ({rows[-3:]})')
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][0]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    m.mode = 2; m.calls = []
    m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect('widget_invalidate_force' in m.names(), 'a mode change invalidates Now Playing on the existing timer')
    # the mode marks: the built white glyph images, decoded once into page bitmaps (coverage mixed from white to the mark's colour), drawn at the top right
    MARK = (O['IP_MODE_X'], O['IP_MODE_Y'], O['IP_MODE_PX'], O['IP_MODE_PX'])
    expect(MARK[0] + MARK[2] == 312 and MARK[1] == 28, 'the mark is right aligned at x 312, top y 28')
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
    titles = [(t, r) for t, r in m.paint()[0] if r[1] == 62]
    expect(len(titles) == 1 and titles[0][0].endswith('…'), 'the bold title is drawn once and clipped')
    before = len([c for c in m.calls if c[0] == 'bitmap_create_ex'])
    m.paint(); m.paint()
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == before, 'painting allocates no cover bitmap')
    n = machine(songs=['Song']); n.fail_projection = True; n.open(); n.timers = []
    n.play([n.class_lists[O['CLASS_ALL_SONGS']][0]], 0); n.turn(0, STEP_DEG * 5 + 5); n.tap(CX, CY)
    n.call(PSYMS['ip_tick'], a0=0, count=40000000)
    blits = n.paint()[2]
    COVER = (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_ART'], O['IP_ART'])
    expect(any(b[2] == COVER for b in blits) and not any(b[2][1] == COVER[1] + COVER[3] for b in blits), 'a reflection that cannot be allocated: the cover alone, no crash')


def classic_material_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []
    fills = m.paint()[1]
    selected = [f for f in fills if f[1] == 0 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < BARH + ROWH]
    expect(selected and selected[0][0] == 0xfff8dd9a and selected[-1][0] == 0xff814f15, 'selection has a highlight and dark bottom rule')
    header = [f for f in fills if f[1] == 0 and f[3] == O['IP_SPLIT_X'] and f[2] < BARH - 1]
    expect(len({f[0] for f in header}) >= 4, 'split header has the silver bevel stops')


def split_menu_tests(ctx):
    expect = ctx.expect
    m = machine(); m.open(); m.timers = []
    for label in ('root', 'Music', 'Settings'):
        if label == 'Music': music(m)
        if label == 'Settings':
            m.tap(*m.polar(0, 85)); m.turn(0, 6 * STEP_DEG + 5); m.tap(CX, CY)
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
    expect(over == [('ge_DE', 'row Repeat', 92, 46), ('po_PL', 'row Repeat', 74, 68), ('ru_RU', 'Shuffle Songs', 146), ('ru_RU', 'row Appearance', 98, 57), ('ru_RU', 'row Shuffle', 97, 42), ('sp_ES', 'Shuffle Songs', 153), ('sp_ES', 'row Repeat', 52, 81), ('sp_ES', 'row Shuffle', 66, 81), ('uk_UK', 'Shuffle Songs', 131)], f'at 18 px (Inter Medium) these labels ellipsize (the 130 px menu box, or the room a Settings value leaves; the rest of the 13 languages fit): {over}')
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
    """Reversal hysteresis, the chord dead zone, the 15 degree step with carry, the tiers on long lists, the hard stop at the ends (docs/modules/ipod.md "The wheel")."""
    expect = ctx.expect

    def menu():
        m = machine(); m.open(); m.timers = []
        return m

    def menu_row(m):
        m.clock += 1000
        ys = [f[2] for f in m.paint()[1] if f[4] == 1 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < 240]
        return (min(ys) - BARH) // ROWH if ys else None

    def songs(n):
        m = machine(songs=[f'Song {i:03d}' for i in range(n)]); m.open(); m.timers = []
        music(m)
        m.turn(0, STEP_DEG * 3 + 5); m.tap(CX, CY)
        return m

    def song_sel(m):
        m.clock += 1000
        texts, fills, _ = m.paint()
        ys = [f[2] for f in fills if f[4] == 1 and f[3] == 320 and f[2] >= BARH]
        return int(rows_of(texts)[0][5:]) + (min(ys) - BARH) // ROWH

    # the step: 15 degrees, the leftover carries
    m = menu()
    d = Drag(m, 0)
    for _ in range(14): d.go(1, 100)
    d.up()
    expect(menu_row(m) == 0, 'a 14 degree turn is no step')
    m = menu(); d = Drag(m, 0)
    for _ in range(16): d.go(1, 100)
    d.up()
    expect(menu_row(m) == 1, 'a 16 degree turn is one step')
    m = menu(); d = Drag(m, 0)
    d.go(20, 100); r1 = menu_row(m); d.go(10, 100); d.up()
    expect(r1 == 1 and menu_row(m) == 2, f'20 degrees then 10: the leftover 5 carries into the second step ({r1}, {menu_row(m)})')

    # reversal hysteresis: 8 degrees of reverse travel are swallowed, then the accumulator starts again at 0
    m = menu(); d = Drag(m, 0)
    for _ in range(8): d.go(2, 100)
    expect(menu_row(m) == 1, 'forward 16 degrees: row 1')
    for _ in range(11): d.go(-2, 100)
    expect(menu_row(m) == 1, '22 degrees back: 8 swallowed, 14 counted: still row 1')
    for _ in range(2): d.go(-2, 100)
    expect(menu_row(m) == 0, '26 degrees back: 8 swallowed, 18 counted: one step up')
    m = menu(); d = Drag(m, 0)
    for _ in range(8): d.go(2, 100)
    for _ in range(5):
        for _ in range(3): d.go(-2, 100)
        for _ in range(3): d.go(2, 100)
    expect(menu_row(m) == 1, 'a 6 degree jitter at the turnaround, five times over, steps nothing')
    for _ in range(6): d.go(2, 100)
    expect(menu_row(m) == 1, 'and the jitter took no forward travel either: 12 more degrees is still row 1 (1 + 12 < 15)')
    for _ in range(2): d.go(2, 100)
    expect(menu_row(m) == 2, 'and 16 more is the next step')

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
    expect(row == 6, f'a chord 12 px from the centre reaches the last root row ({row})')
    m = menu(); m.ptr('down', CX - 60, CY - 10, 1000); m.ptr('move', CX + 60, CY - 10, 1100)
    x, y = 60, -10
    a = math.degrees(math.atan2(x, -y)); r = math.hypot(x, y)
    for i in range(1, 5):
        px, py = r * math.sin(math.radians(a + 5 * i)), -r * math.cos(math.radians(a + 5 * i))
        m.ptr('move', CX + round(px), CY + round(py), 1100 + 100 * i)
    expect(menu_row(m) == 1, 'after the rejected chord the same touch goes on from the new point: 20 degrees, one step')
    m = menu(); m.ptr('down', CX - 30, CY, 1000); m.ptr('move', CX + 30, CY + 4, 1100)
    expect(menu_row(m) == 0, 'a drag that begins on the centre button still does nothing')

    # tiers
    expect([m.call(PSYMS['ip_tier_rows'], a0=n, a1=i) for n, i in ((8, 0), (8, 5), (16, 5), (16, 99), (17, 0), (17, 1), (17, 2), (17, 3), (17, 4), (17, 5), (17, 6), (17, 7), (17, 9), (3000, 20))]
          == [1, 1, 1, 1, 1, 2, 3, 5, 8, 13, 21, 34, 34, 34], 'rows a step: 1 for 16 rows or fewer, else the tiers 1, 2, 3, 5, 8, 13, 21, 34 (the last holds)')
    m = songs(3000); d = Drag(m, 0)
    for _ in range(30): d.go(6, 16)
    expect(song_sel(m) == 12, f'a fast turn (375 deg/s): the first half second is one row per 15 degrees (row {song_sel(m)} = 12)')
    prev, deltas = 12, []
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
    expect(max(deltas) == 1 and prev == 6, 'the short main menu list: one row a step at 375 deg/s')

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
    expect(menu_row(m) == 6, 'the last row')
    m.calls = []; d = Drag(m, 0); d.go(20, 100); d.go(20, 100)
    ys2 = [f[2] for f in m.paint()[1] if f[4] == 1 and f[3] == O['IP_SPLIT_X'] and BARH <= f[2] < 240]
    expect(menu_row(m) == 6 and min(ys2) == BARH + 6 * ROWH, f'turning on past the end: the last row stays selected ({min(ys2)})')
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
        tick(m); reds.append(row(m, mix_frame(m), 120 * PANE[2] + 80, 1)[0] & 255)
    expect(len(set(reds)) > 5 and reds.index(max(reds)) not in (0, len(reds) - 1), 'its pan sweeps back and forth')
    m.play([m.song('U', artist='Artist 5', album='Album 5')], 0)
    expect(5 in [x for _ in range(4) for x in pane_loads(tick(m), m)], 'the next track from another album: that album\'s cover')
    m.play([m.song('V', artist='Nobody', album='Uncached')], 0)
    got = [x for _ in range(80) for x in pane_loads(tick(m), m)]
    expect(got and all(g in range(8) for g in got), f'a track whose album has no cached cover: the random rotation resumes ({got})')
    # the interval: slow elsewhere, fast again on the main menu
    m = with_covers()
    m.call(PSYMS['ip_first'], a0=0, count=40000000)
    tick(m); tick(m)
    m.tap(CX, CY); m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    expect(('timer_modify', 0x777, O['IPCF_FRAME_MS']) in m.calls, 'a list opens: the existing timer briefly accelerates to load its visible covers')
    c = tick(m)
    expect(not [x for x in c if x[0] in ('widget_load_image', 'timer_modify')], 'on a list the tick decodes no cover and the interval stays')
    m.tap(*m.polar(0, 85))
    expect(('timer_modify', 0x777, FAST) in m.calls, f'MENU to Music resumes the pane at {FAST} ms')
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
        music(m)
        m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
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
        texts = texts_of(m.paint())
        expect('Now Playing' in texts, 'the iPod\'s own Now Playing is in front')
        if seed == 11:
            x, y = m.polar(0, 85); m.tap(x, y)
            front = rows_of(m.paint()[0])
            expect(front == [m.tr(k) for k in MUSIC_KEYS], f'MENU from Now Playing returns to Music ({front[:2]})')
    expect(len(set(firsts)) >= 2, f'the first song differs with the random seed ({firsts})')
    # an empty library: the message, nothing played, the mode untouched
    m = machine(); m.open(); m.timers = []; m.mode = 1
    music(m)
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    expect(any(c[0] == 'toast' for c in m.calls) and 'start_player' not in m.names() and m.mode == 1 and 'mclSetPlayMode' not in m.names(), 'no songs: the stock message box, nothing started, the mode kept')
    # the first file is gone: nothing started, the mode kept
    m = machine(songs=songs); m.open(); m.timers = []; m.mode = 3
    music(m)
    m.present.discard('/mnt/mmc/m/1.flac')
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
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
    m.turn(0, STEP_DEG * 6 + 5); m.tap(CX, CY)
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
    m.turn(0, 6 * STEP_DEG + 5); m.tap(CX, CY)
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
    expect(80 in m.origins and (0xffffffff - 79) in m.origins, 'midpoint slides the two menu pages in opposite directions')
    expect((0xffffffff - 79, 0, 79) in m.clip_frames and (80, 80, 159) in m.clip_frames, 'each moving menu is clipped to its own bounds as well as the display viewport')
    expect(tuple(m.word(m.canvas + o) for o in (0, 4, 16, 20, 24, 28)) == before, 'painting restores canvas origin and clipping exactly')
    expect(not any(c[0] in ('calloc', 'bitmap_create_ex', 'widget_load_image', 'loadLocalClassList') for c in m.calls), 'animated paint performs no allocation, decode or library query')
    m.clock += 141; m.call(PSYMS['ip_tick'], count=40000000)
    expect(m.call(PSYMS['ip_render_active']) == 0, 'the slide finishes on the existing timer after 280 ms')
    m.paint(animated=True); m.tap(*m.polar(0, 85))
    expect(m.call(PSYMS['ip_render_active']) == 1, 'MENU animates an internal pop')
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    m.clip_frames = []; m.paint(animated=True)
    expect((80, 80, 159) in m.clip_frames and (0xffffffff - 79, 0, 79) in m.clip_frames, 'pop backgrounds cannot erase the outgoing half of the screen')
    m.fire(EVT_BG, WIN)
    expect(m.call(PSYMS['ip_render_active']) == 0, 'backgrounding cancels the slide')
    m.fire(EVT_FG, WIN); m.paint(animated=True); m.tap(CX, CY); m.tap(*m.polar(0, 85))
    expect(m.call(PSYMS['ip_render_active']) == 0, 'fast repeated navigation settles instead of stacking animations')
    m.fire(EVT_DESTROY, WIN)
    expect(not m.bitmaps, 'destroy frees image snapshots and page bitmaps')


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
    m.tap(CX, CY); m.turn(0, STEP_DEG + 5); m.calls = []; m.tap(CX, CY)   # Music > Albums: not a split page
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


def orphaned(m, c=()):
    """The worker is cancelled and orphaned (busy, no join); once it has exited the next call reaps it."""
    ok = ('pthread_join',) not in list(m.calls) + list(c) and build_state(m)['orphan'] == 1 and m.call(PSYMS['cc_build_busy']) == 1
    m.call(PSYMS['cc_worker'], count=5000000)
    return ok and m.call(PSYMS['cc_build_busy']) == 0 and build_state(m)['jobs'] == 0


def fresh_art_tests(ctx):
    expect = ctx.expect
    m = machine(albums=[('Fresh', 'Artist')]); m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    for _ in range(3): tick(m)
    expect(m.call(PSYMS['cc_build_busy']) == 1 and m.call(PSYMS['cc_build_total']) == 1, 'fresh cache starts the shared extractor from the visible album record')
    key = album_key('Artist', 'Fresh'); path = art_file(key)
    m.present.add(path); m.files[path] = 4096
    m.images['file://' + path] = (48, 48, bytes((10, 100, 200, 255)) * 48 * 48)
    for _ in range(3): tick(m)
    _, _, blits = m.paint()
    expect(any(b[2] == (0, BARH, 54, 54) for b in blits), 'a newly extracted cover replaces the visible placeholder')
    m.fire(EVT_BG, WIN)
    expect(orphaned(m), 'background cancels this page own extraction job (reaped once it exits)')
    m = machine(albums=[('No card', 'Artist')]); m.card_mounted = False; m.open(); m.timers = []; music(m)
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    for _ in range(4): tick(m)
    expect(m.call(PSYMS['cc_build_busy']) == 0, 'no extraction job is started without a mounted card')


def reference_nav_tests(ctx):
    """The reference's navigation: a Now Playing row only while something plays, the split open of fullscreen pages, the long press of MENU."""
    expect = ctx.expect
    keys = [k for k in MAIN_KEYS if k != 'Now Playing']
    m = machine(); m.status = 0; m.open(); m.timers = []
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys], f'nothing plays: the main menu has no Now Playing row ({rows_of(m.paint()[0])})')
    m.turn(0, STEP_DEG * 9)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys] and len([f for f in m.paint()[1] if f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] >= BARH + 5 * ROWH]) == ROWH,
           'six rows: the cursor stops on Settings')
    m.tap(CX, CY); texts = m.paint(animated=False)[0]
    expect(rows_of(texts) == [m.tr(k) for k in SET_KEYS], 'and Settings opens from the sixth row')
    m = machine(); m.status = 0; m.open(); m.timers = []
    m.turn(0, STEP_DEG * 9)
    m.status = 2
    for _ in range(5): m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    texts, fills, _ = m.paint()
    expect(rows_of(texts) == [m.tr(k) for k in MAIN_KEYS] and any(f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] == BARH + 6 * ROWH for f in fills),
           'playback starts: Now Playing appears and the cursor stays on Settings')
    m.status = 0
    for _ in range(5): m.call(PSYMS['ip_tick'], a0=0, count=40000000)
    expect(rows_of(m.paint()[0]) == [m.tr(k) for k in keys] and any(f[3] == O['IP_SPLIT_X'] and f[4] == 1 and f[2] == BARH + 5 * ROWH for f in m.paint()[1]), 'and goes with it, the cursor still on Settings')
    # a fullscreen page opens with the split: the menu half slides left, the artwork pane right, uncovering the page that stays still
    m = machine(songs=['Song']); m.open(); m.timers = []; m.paint(animated=True)
    m.play([m.class_lists[O['CLASS_ALL_SONGS']][0]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.origins = []; m.clip_frames = []; m.tap(CX, CY)
    expect(m.call(PSYMS['ip_render_active']) == 1 and m.call(PSYMS['ip_render_split']) == 1 and m.call(PSYMS['ip_render_direction']) == 1, 'Now Playing from the main menu starts a split slide')
    m.origins = []; m.paint(animated=True)
    expect(set(m.origins) == {0}, f'the first frame draws everything at its place ({sorted(set(m.origins))})')
    m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    m.origins = []; m.clip_frames = []; m.paint(animated=True)
    ox = sorted({o if o < 1 << 31 else o - (1 << 32) for o in m.origins})
    expect(ox == [-80, 0, 80] or ox == [-79, 0, 79] or ox == [-80, 0, 79], f'midway: the page still, the menu half 80 px left, the pane 80 px right ({ox})')
    frames = {(o if o < 1 << 31 else o - (1 << 32), a, b) for o, a, b in m.clip_frames}
    expect(any(o < 0 and a == 0 and 88 <= b <= 90 for o, a, b in frames) and any(o > 0 and 238 <= a <= 241 and b >= 319 for o, a, b in frames),
           f'the halves are clipped to what is left of them ({sorted(frames)})')
    m.clock += 141; m.call(PSYMS['ip_tick'], count=40000000)
    expect(m.call(PSYMS['ip_render_active']) == 0 and 'Now Playing' in texts_of(m.paint()), 'the slide ends on Now Playing, 280 ms after it began')
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
    expect(m.call(PSYMS["ip_render_split"]) == 0 and m.call(PSYMS["ip_render_active"]) == 1 and m.call(PSYMS["ip_render_width"]) == 320, "a list from Music slides the whole width, no split")
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
    def parts(m):
        texts, fills, blits = m.paint(animated=True)
        edge = [sx(m.img_ox[i]) for i, b in enumerate(blits) if b[2] == (PANE[0], 0, SW, PANE[3])]
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
    m.paint(animated=True); m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m)
    expect(len(edge) == 1 and edge[0] < 0 and pane and all(o > 0 for o in pane), f'split open: the shadow goes with the menu half (left, {edge}), the pane goes right ({pane})')
    m.paint()
    expect(parts(m)[0] == [] and 'Now Playing' in texts_of(m.paint()), 'on the fullscreen page there is no shadow')
    m.tap(*m.polar(0, 85)); m.paint(animated=True); m.clock += 140; m.call(PSYMS['ip_tick'], count=40000000)
    edge, pane = parts(m)
    expect(edge == [-80] and 80 in pane, f'split close: the shadow comes in with the menu half, once; the pane comes in from the right ({edge}, {pane})')
    m.paint()
    expect(parts(m)[0] == [0], 'and rests at the pane\'s edge again')


def now_steady_tests(ctx):
    """Now Playing does not blink while the player changes track: no time or no track for a moment leaves the text, the cover and the whole bar on screen."""
    expect = ctx.expect
    TX, BY, BH = O['IP_NP_TRACK_X'], O['IP_NP_BAR_Y'], O['IP_NP_BAR_H']
    m = machine(songs=['Alpha', 'Beta']); m.open(); m.timers = []
    songs = m.class_lists[O['CLASS_ALL_SONGS']]
    m.status = 2; m.pt = (107, 305); m.play([songs[0], songs[1]], 0)
    m.turn(0, STEP_DEG * 5 + 5); m.tap(CX, CY)
    def looks(n): [m.call(PSYMS["ip_tick"], a0=0, count=40000000) for _ in range(n)]   # on this level every tick looks (500 ms)
    def shown():
        texts, fills, blits = m.paint()
        names = [t for t, _ in texts]
        bar = {f[2] for f in fills if BY <= f[2] < BY + BH and f[1] >= TX and f[4] == 1}
        return names, len(bar), blits
    looks(1)
    names, bar, _ = shown()
    expect('Alpha' in names and '01:47' in names and '-03:18' in names and bar == BH, f'playing: the track, both times and the {BH} px bar ({names}, {bar})')
    for pt, what in ((None, 'no time (the call fails)'), ((0, 0), 'length 0')):
        m.pt = pt; looks(1)
        names, bar, _ = shown()
        expect('Alpha' in names and '01:47' in names and '-03:18' in names and bar == BH, f'{what}: the bar and both times stay, at the last valid place ({names}, {bar})')
    m.pt = None; m.play([songs[0], songs[1]], 1); looks(1)
    names, bar, _ = shown()
    expect('Beta' in names and '00:00' in names and '-05:05' in names and bar == BH, f'a new track with no time yet: an empty bar, 00:00 and the last length, never blank ({names}, {bar})')
    m.pt = (3, 200); looks(1)
    names, bar, _ = shown()
    expect('00:03' in names and '-03:17' in names and bar == BH, 'then its own time')
    m.calls = []; m.play([], 0); looks(1)
    names, bar, blits = shown()
    expect('Beta' in names and '00:03' in names and bar == BH and 'Not Playing' not in names and not any(c[0] == 'widget_load_image' and c[1] == 'ipod_placeholder' for c in m.calls),
           f'no current track for a moment: the last track\'s text and bar stay and the cover is not swapped for the disc ({names})')
    expect(any(b[2] == (O['IP_NP_ART_X'], O['IP_NP_ART_Y'], O['IP_ART'], O['IP_ART']) for b in blits), 'the cover is still drawn')
    looks(3)
    names, bar, _ = shown()
    expect('Not Playing' in names and 'Beta' not in names, 'and Not Playing once the player really has none')
    before = len([c for c in m.calls if c[0] == 'bitmap_create_ex'])
    shown(); shown()
    expect(len([c for c in m.calls if c[0] == 'bitmap_create_ex']) == before, 'painting allocates nothing')


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
    go(m)
    texts = m.paint()[0]
    expect(rows_of(texts) == ['Beta', 'Alpha'] and 'Podcasts' in texts_of((texts,)), f'Podcasts: the shows with an episode file, newest first, the title bar ({rows_of(texts)})')
    m.tap(CX, CY)
    texts = m.paint()
    expect(pc_rows(texts[0]) == ['b1'] and 'Beta' in texts_of(texts), f'a show: its episodes, the show as the title ({rows_of(texts[0])})')
    # the episodes of Alpha, newest first, with the dot on both (nothing played)
    x, y = m.polar(0, 85); m.tap(x, y)
    m.turn(0, STEP_DEG + 5); m.tap(CX, CY)
    texts = m.paint()
    expect(pc_rows(texts[0]) == ['a2', 'a1'], f'Alpha: newest first ({rows_of(texts[0])})')
    dots = [f for f in texts[1] if 6 <= f[1] <= 9 and f[3] <= 8 and f[4] == 1 and f[2] >= BARH and f[2] < BARH + 2 * ROWH]
    expect(len(dots) == 16, f'both unplayed episodes have the dot, 8 rows each ({len(dots)} fills)')
    m.turn(0, STEP_DEG + 5)
    m.calls = []
    m.tap(CX, CY)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(len(sp) == 1 and sp[0][2:] == (1, O['PLAY_MODE']) and m.played and len(m.played[0]) == 2 and m.played[1] == 1, f'a tap starts the show\'s episodes as a class 1 queue at that row ({sp}, {m.played and m.played[1]})')
    expect(m.word(G_CLASS) == 1 and 'Now Playing' in texts_of(m.paint()), 'the class is the folder class and the Pod\'s own Now Playing is in front')
    # a card with no podcasts: an empty Podcasts level
    m = PCIM(); m.class_lists[O['CLASS_ALL_SONGS']] = []; m.open(); m.timers = []
    go(m)
    texts = m.paint()[0]
    expect(rows_of(texts) == [m.tr('No downloaded episodes')], f'no Podcasts folder: only the empty line ({rows_of(texts)})')
    m.tap(CX, CY)
    expect(m.paint()[0] == texts, 'a press on the empty list does nothing')


def podcasts_pane_tests(ctx):
    """The main menu's Podcasts row: Podcasts is row 2 and opens its level, Music has no Podcasts row, the row shows its picture in the pane (No Podcasts under it when no show has an episode), the cover pane is back off the row."""
    expect = ctx.expect
    root = '/mnt/mmc/Podcasts'
    def card(episode):
        m = PCIM(); m.class_lists[O['CLASS_ALL_SONGS']] = []
        if episode: m.put(f'{root}/Alpha/a1.mp3', b'x', mtime=1000)
        m.open(); m.timers = []
        return m
    def pc_blits(m): return [b for b in m.paint()[2] if b[2] == PANE and b[1] == (0, 0, PANE[2], PANE[3])]
    m = card(False)
    expect(rows_of(m.paint()[0])[2] == m.tr('Podcasts') and m.tr('Podcasts') not in [m.tr(k) for k in MUSIC_KEYS], 'the main menu has Podcasts at row 2, Music has no Podcasts row')
    expect(not pc_blits(m) and not [t for t, _ in m.paint()[0] if t == m.tr('No Podcasts')], 'on the Music row: the cover pane, no picture, no No Podcasts')
    m.turn(0, STEP_DEG * 2 + 5)
    expect(m.loads.count('ipod_podcasts') == 1, f'moving to Podcasts loads its picture once ({m.loads})')
    texts = m.paint()[0]
    expect(len(pc_blits(m)) == 1 and [r for t, r in texts if t == m.tr('No Podcasts')] != [], 'the picture is drawn in the pane and, with no episode, No Podcasts')
    r = [r for t, r in texts if t == m.tr('No Podcasts')][0]
    expect(r[1] == O['IP_PC_TEXT_Y'] and r[0] >= O['IP_PANE_X'] and abs(r[0] + r[2] // 2 - (O['IP_PANE_X'] + O['IP_PANE_W'] // 2)) <= 2, f'No Podcasts is centred in the pane under the glyph ({r})')
    c = tick(m)
    expect(not [x for x in c if x[0] == 'loadLocalClassList' or x[:3] == ('bitmap_create_ex', O['IP_PANE_ART'], O['IP_PANE_ART'])] and m.loads.count('ipod_podcasts') == 1, 'the pane timer does no cover work and the picture is not loaded again')
    m.tap(CX, CY)
    expect(rows_of(m.paint()[0]) == [m.tr('No downloaded episodes')], 'selecting Podcasts opens the Podcasts level')
    m.tap(*m.polar(0, 85)); m.turn(0, -(STEP_DEG * 2 + 5))
    texts = m.paint()[0]
    expect(not pc_blits(m) and not [t for t, _ in texts if t == m.tr('No Podcasts')], 'back on the Music row: the cover pane is back, no picture, no No Podcasts')
    m = card(True)
    m.turn(0, STEP_DEG * 2 + 5)
    expect(len(pc_blits(m)) == 1 and not [t for t, _ in m.paint()[0] if t == m.tr('No Podcasts')], 'with an episode on the card the picture shows and No Podcasts does not')


SECTIONS = [angle_tests, asset_tests, menu_tests, open_tests, paint_tests, wheel_tests, feel_tests, tap_tests, nav_tests, stale_tests, playing_indicator_tests, music_menu_tests, root_shortcut_tests, radio_now_tests, menu_padding_tests, rich_rows_tests, row_art_tests, playlist_art_tests, now_material_tests, classic_material_tests, split_menu_tests, pane_tests, shuffle_tests, settings_tests, i18n_tests, appearance_tests, transition_tests, fresh_art_tests, pane_sharp_tests, reference_nav_tests, shadow_slide_tests, now_steady_tests, podcasts_tests, podcasts_pane_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

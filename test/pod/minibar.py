"""The mini player bar of the menu's Home instance (patch/minibar.c, tools/pod_ui.py minibar()): the asset, the constants shared with
patch/offsets.inc, the glyph images, the page timer's lifecycle, what it shows (labels, cover, glyph), the stock player calls the buttons
make, hit tests with demo's own widget_find_target, the contrast of the text on the pill, and the fall-backs to the plain menu."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

KILL_SD, KILL_DATA = '/mnt/mmc/m1plus-off', '/mnt/data/m1plus-off'
WIN = 0x24000000
S = O['MB_ART']
EVT_DESTROY, EVT_AFTER_PAINT, EVT_CLICK = O['EVT_DESTROY'], O['EVT_AFTER_PAINT'], O['EVT_CLICK']
EVT_BG, EVT_FG = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']
PLAYPAUSE, NEXT, STATUS = (pod.FUNCTIONS[n][2] for n in ('playpause_quick_click', 'next_quick_click', 'mclGetPlayStatus'))
LISTS = ('pod_listview', 'pod_scrollview', 'scroll_bar_m')
HOME_LIST_H = 450 - 2 * O['HOME_PAD']


class BM(Machine):
    """Machine plus what the bar calls: the style API, the player's status and quick clicks, files read through stdio."""
    FIRE_WIN = WIN

    def __init__(self, bar=True, sb=True):
        super().__init__()
        self.styles = []          # (widget, "normal:bg_color", uint32)
        self.status = 3           # mclGetPlayStatus: 2 playing, 3 paused
        self.blobs, self.pos = {}, {}
        self.next_ret = 1
        self.on_fail = set()      # event types whose widget_on returns 0
        self.cmds = []            # ('playpause',) / ('next', time word) / the radio's ('mclSetPause',), ('mclSetResume',), ('mclStop',), ('start', url)
        self.hs = 0               # mclGetHciplayerStatus
        self.logo_busy = 0        # rd_logo_running, when a test hooks the logo worker's entry points
        names = list(pod_ui.MB_NAMES if bar else ()) + ['pod_listview', 'pod_scrollview', 'pod_pad'] + (['scroll_bar_m'] if sb else [])
        for n in names: self.widget(n)
        for n in ('pod_minibar', 'pod_mb_card') if bar else (): self.types[self.widgets[n]] = 'view' if n == 'pod_minibar' else 'button'
        self.props[(self.widgets['pod_scrollview'], 'w')] = 310
        if sb: self.props[(self.widgets['scroll_bar_m'], 'w')] = 10
        self.props[(self.widgets['pod_scrollview'], 'virtual_h')] = 9 * 52
        self.props[(self.widgets['pod_scrollview'], 'h')] = HOME_LIST_H
        self.props[(self.widgets['pod_scrollview'], 'yoffset')] = 0
        self.props[(self.widgets['pod_pad'], 'visible')] = 0   # the asset's pod_pad is hidden
        self.present.add('/tmp/ignored')

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'widget_set_style':
            v = self.word(a2 + 8); self.calls.append(('widget_set_style', a0, self.read_cstr(a1), v)); self.styles.append((a0, self.read_cstr(a1), v)); ret = 0
        elif name == 'value_set_uint32':
            self.setword(a0, 7); self.setword(a0 + 8, a1); ret = a0
        elif name == 'mclGetPlayStatus':
            self.calls.append(('mclGetPlayStatus',)); ret = self.status
        elif name == 'playpause_quick_click':
            self.calls.append(('playpause_quick_click', a0)); self.cmds.append(('playpause',))
            self.status = 2 if self.status != 2 else 3   # mclSetResume / mclSetPause store the status at once
            ret = 1
        elif name in ('mclSetPause', 'mclSetResume'):
            self.calls.append((name,)); self.cmds.append((name,)); self.status = 3 if name == 'mclSetPause' else 2; ret = 1
        elif name == 'mclGetHciplayerStatus': ret = self.hs
        elif name == 'mclGetOutputWay': ret = 0
        elif name in ('stop_player', 'set_outputchannel', 'mclSetPcmMode', 'mclSetMute', 'set_devicevolume', 'mclSetDacPwr'): ret = 1   # rd_play's calls
        elif name == 'strlen': ret = len(self.read_cstr(a0).encode('latin-1'))   # the radio engine's list parser
        elif name == 'strstr':
            h, n = self.read_cstr(a0), self.read_cstr(a1); i = h.find(n); ret = a0 + i if i >= 0 else 0
        elif name == 'strchr':
            h = self.read_cstr(a0); i = h.find(chr(a1 & 0xff)) if a1 & 0xff else len(h); ret = a0 + i if i >= 0 else 0
        elif name == 'strrchr':
            h = self.read_cstr(a0); i = h.rfind(chr(a1 & 0xff)) if a1 & 0xff else len(h); ret = a0 + i if i >= 0 else 0
        elif name == 'strncasecmp':
            x, y = self.read_cstr(a0)[:a2].lower(), self.read_cstr(a1)[:a2].lower(); ret = (x > y) - (x < y)
        elif name == 'rd_logo_running': ret = self.logo_busy   # (hooked only by the test that watches the logo worker)
        elif name == 'rd_logo_start': self.calls.append(('rd_logo_start', self.read_cstr(a0))); ret = 1
        elif name == 'mclStop': self.calls.append(('mclStop',)); self.cmds.append(('mclStop',)); ret = 0
        elif name == 'mcl_tidalStartPlayer': self.cmds.append(('start', self.read_cstr(a0))); self.calls.append(('mcl_tidalStartPlayer',)); ret = 1
        elif name == 'next_quick_click':
            self.calls.append(('next_quick_click', a1)); self.cmds.append(('next', self.word(a0 + 8), self.word(a0 + 12), a1)); ret = self.next_ret
        elif name == 'widget_on' and a1 in self.on_fail:
            self.calls.append(('widget_on', a0, a1, a2, a3)); ret = 0
        elif name == 'fopen' and self.read_cstr(a0) in self.blobs:
            path = self.read_cstr(a0); h = self.alloc(4); self.pos[h] = 0; self.fh = (h, path)
            self.calls.append(('fopen', path, self.read_cstr(a1))); ret = h
        elif name == 'fread' and a3 in self.pos:
            data = self.blobs[self.fh[1]]; n = min(a1 * a2, len(data) - self.pos[a3])
            if n: self.u.mem_write(a0, data[self.pos[a3]:self.pos[a3] + n])
            self.pos[a3] += n; ret = n // a1
        elif name == 'fclose' and a0 in self.pos:
            ret = 0
        if ret is not None:
            self._icount += 1
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    # ---- the world
    def start(self, win=WIN, count=3000000):
        self.calls = []
        self.call(PSYMS['minibar_start'], a0=win, count=count)
        return self.calls

    def first(self): return self.call(PSYMS['mb_first'], count=40000000)
    def tick(self): return self.call(PSYMS['mb_tick'], count=40000000)

    def click(self, name, e=0):
        fn, ctx = self.bound[(self.widgets[name], EVT_CLICK)]
        return self.call(fn, a0=ctx, a1=e, count=40000000)

    def track(self, title='Song', artist='Artist', album='Album', path='/mnt/mmc/a/1.flac', name='1.flac', pos=0):
        t = self.record(album=album, artist=artist, path=path, title=title, name=name)
        self.play([t], pos)
        return t

    def cover(self, artist='Artist', album='Album', rgb=(200, 40, 40), size=168):
        """The album's Cover Flow cache file with a solid picture; its key."""
        key = fnv(fnv(O['FNV_SEED'], artist), album) or 1
        path = art_file(key)
        self.present.add(path); self.files[path] = 4096
        self.images['file://' + path] = (size, size, bytes(rgb + (255,)) * (size * size))
        self.load_image = 0
        return key

    def tmp_cover(self, data=b'jpeg-bytes' * 30, rgb=(40, 40, 200), src=2, path='/tmp/coverpic.jpg'):
        """The /tmp picture demo wrote for the playing track (source type src): its bytes (the key) and what the loader decodes."""
        self.blobs[path] = data; self.present.add(path)
        self.images['file://' + path] = (8, 8, bytes(rgb + (255,)) * 64)
        self.setword(pod.DATA['COVER_SRC'][0], src)
        self.load_image = 0

    def placeholder(self, rgb=(90, 90, 90)):
        self.images['p_default'] = (16, 16, bytes(rgb + (255,)) * 256)

    def setup(self, tick=True, **kw):
        """The bar started, its first timer fired (the repeating one is armed); optionally one tick run (the bar's first work)."""
        self.start()
        self.first()
        return self

    def pixels(self):
        b = next(iter(self.bitmaps)) if self.bitmaps else 0
        data, w, h = self.bitmaps[b]
        return b, w, h, bytes(self.u.mem_read(data, w * h * 4))

    def visible(self, name): return self.props.get((self.widgets[name], 'visible'))
    def sensitive(self, name): return self.props.get((self.widgets[name], 'sensitive'))
    def shown(self, name): return bool(self.visible(name)) and bool(self.sensitive(name))
    def texts_set(self): return [(c[1], c[2]) for c in self.calls if c[0] == 'widget_set_text_utf8']
    def resizes(self): return [c[1:] for c in self.calls if c[0] in ('widget_resize', 'widget_move')]   # the list is never moved or resized by the bar

    def paint(self):
        e = self.alloc(0x40); self.u.mem_write(e, bytes(0x40)); self.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        self.blits = []
        self.call(PSYMS['mb_on_paint'], a0=0, a1=e, count=2000000)
        return self.blits



def corner_coverage(r):
    """patch/common.c pod_corner_fill: r x r bytes, the coverage (0..255) outside a quarter circle of radius r centred on the square's inner corner."""
    c, out = 16 * r, []
    for y in range(r):
        for x in range(r):
            n = sum((2 * (x * 8 + i) + 1 - c) ** 2 + (2 * (y * 8 + j) + 1 - c) ** 2 > c * c for i in range(8) for j in range(8))
            out.append((n * 255 + 32) // 64)
    return out


def centre_rgb(m):
    """The colour of the middle pixel of the cover bitmap."""
    _, w, h, px = m.pixels()
    return rgb_of(struct.unpack_from('<I', px, 4 * (h // 2 * w + w // 2))[0])


def rgb_of(word): return (word & 255, word >> 8 & 255, word >> 16 & 255)
def word_of(rgb): return 0xff000000 | rgb[0] | rgb[1] << 8 | rgb[2] << 16


def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    menu_asset = os.path.join(raw, 'ui', 'm1plus_menu.bin')

    # ------------------------------------------------------------------ constants: patch/offsets.inc and tools/pod_ui.py agree
    pairs = {'MB_X': pod_ui.MB_X, 'MB_Y': pod_ui.MB_Y, 'MB_W': pod_ui.MB_W, 'MB_H': pod_ui.MB_H, 'MB_R': pod_ui.MB_R, 'MB_GAP': pod_ui.MB_GAP,
             'MB_PAD': pod_ui.MB_PAD, 'MB_ART': pod_ui.MB_ART, 'MB_ART_X': pod_ui.MB_ART_X, 'MB_ART_Y': pod_ui.MB_ART_Y,
             'MB_ART_R': pod_ui.MB_ART_R, 'MB_TEXT_X': pod_ui.MB_TEXT_X, 'MB_TEXT_W': pod_ui.MB_TEXT_W, 'MB_TITLE_Y': pod_ui.MB_TITLE_Y,
             'MB_TITLE_H': pod_ui.MB_TITLE_H, 'MB_ARTIST_Y': pod_ui.MB_ARTIST_Y, 'MB_ARTIST_H': pod_ui.MB_ARTIST_H,
             'MB_PLAY_X': pod_ui.MB_PLAY_X, 'MB_NEXT_X': pod_ui.MB_NEXT_X, 'MB_BTN_W': pod_ui.MB_BTN_W}
    expect(all(O[k] == v for k, v in pairs.items()), f'patch/offsets.inc MB_* equal tools/pod_ui.py ({[k for k, v in pairs.items() if O[k] != v]})')
    expect(O['MB_PLAYING'] == 2 and O['MB_TICK_MS'] == 500, 'status 2 = playing, a 500 ms tick')
    expect(O['MB_PAD'] == O['WIN_H'] - O['HOME_PAD'] - (O['MB_Y'] - O['MB_GAP']) == 64,
           'the list (to y 440) scrolled to its end, with MB_PAD of padding, has its last row end MB_GAP above the pill')
    expect((O['MB_X'], O['MB_Y'], O['MB_W'], O['MB_H'], O['MB_R']) == (8, 384, 304, 56, 28) and O['MB_R'] * 2 == O['MB_H'], 'the pill: 304 x 56 at (8, 384), radius h / 2 = 28')
    expect(O['MB_Y'] + O['MB_H'] <= O['WIN_H'] and O['MB_X'] + O['MB_W'] <= O['SCREEN_W'] and O['MB_X'] * 2 + O['MB_W'] == 320 and 450 - (O['MB_Y'] + O['MB_H']) == O['HOME_PAD'] == 10 and O['MB_Y'] + O['MB_H'] == O['HOME_PAD'] + 430,
           'the pill floats inside the window with equal side margins and 8 px below')
    expect(2 * O['MB_ART_Y'] + O['MB_ART'] == O['MB_H'] and O['MB_ART_X'] > O['MB_ART_Y'] and O['MB_ART'] == 36 and O['MB_ART_X'] == 14 and O['MB_ART_R'] == 5,
           'the cover: 36 px, centred vertically, a 14 px left inset (larger than the 10 px vertical one, for the pill curve), radius 5')
    expect(O['MB_BTN_W'] >= 44 and O['MB_H'] >= 44 and O['MB_PLAY_X'] + O['MB_BTN_W'] <= O['MB_NEXT_X'] + 3 and O['MB_NEXT_X'] + O['MB_BTN_W'] <= O['MB_W']
           and O['MB_TEXT_X'] + O['MB_TEXT_W'] <= O['MB_PLAY_X'], 'play and next are 44 x 44+ targets side by side, the text ends before them')
    c_play, c_next = O['MB_PLAY_X'] + O['MB_BTN_W'] / 2, O['MB_NEXT_X'] + O['MB_BTN_W'] / 2
    expect(abs((c_next - c_play) / O['MB_H'] - 0.92) < 0.02 and abs((O['MB_W'] - c_next) / O['MB_H'] - 0.62) < 0.02 and O['MB_TEXT_X'] - (O['MB_ART_X'] + O['MB_ART']) == 10,
           f'glyph centres {c_next - c_play:.0f} px apart (0.92 h), the next centre {O["MB_W"] - c_next:.0f} px from the right end (0.62 h), the text 10 px (0.18 h) right of the cover')
    expect(O['MB_TITLE_Y'] + O['MB_TITLE_H'] <= O['MB_ARTIST_Y'] and O['MB_ARTIST_Y'] + O['MB_ARTIST_H'] <= O['MB_H'], 'title over artist, inside the pill')

    # ------------------------------------------------------------------ the asset
    ui = awtk_ui.parse(open(menu_asset, 'rb').read())
    kids = [c.name for c in ui.children]
    expect(kids == ['navigationbar_view', 'pod_listview', 'img_nb_fade', 'pod_cache_pill', 'pod_minibar'], f'the menu window: navbar, list, the fade, the cache pill, then the bar ({kids})')
    bar = ui.find('pod_minibar')
    expect((bar.x, bar.y, bar.w, bar.h) == (O['MB_X'], O['MB_Y'], O['MB_W'], O['MB_H']) and bar.get('visible') == 'false' and bar.get('sensitive') == 'false',
           'pod_minibar is the card rectangle, hidden and insensitive in the asset')
    expect([c.name for c in bar.children] == ['pod_mb_card', 'pod_mb_title', 'pod_mb_artist', 'pod_mb_play', 'pod_mb_pause', 'pod_mb_next'],
           'card first (below), then the labels and the buttons')
    card, title, artist, play, pause, nxt = (ui.find(n) for n in pod_ui.MB_NAMES[1:])
    states = ('normal', 'pressed', 'over', 'focused', 'disable', 'selected')
    expect(card.type == 'button' and (card.x, card.y, card.w, card.h) == (0, 0, O['MB_W'], O['MB_H']) and card.get('visible') is None and card.get('sensitive') is None
           and all(card.get(f'style:{st}:bg_image') == ('mb_glass_down' if st == 'pressed' else 'mb_glass') and card.get(f'style:{st}:bg_color') == '#00000000'
                   and card.get(f'style:{st}:border_width') == '0' and card.get(f'style:{st}:round_radius') is None for st in states),
           'the card is a button whose look is the glass image (mb_glass, pressed mb_glass_down), no fill, border or radius of its own, in every state')
    from PIL import Image
    dim = lambda c: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    gl = {n: Image.open(os.path.join(raw, 'images/xx', n + '.png')).convert('RGBA') for n in ('mb_glass', 'mb_glass_down')}
    kb = sum(os.path.getsize(os.path.join(raw, 'images/xx', n + '.png')) for n in gl)
    expect(all(im.size == (O['MB_W'], O['MB_H']) for im in gl.values()) and kb < 8192, f'the glass images are MB_W x MB_H, {kb} bytes together')
    def over(im, x, y, bg):   # the pixel composited over a grey level (straight alpha)
        r, g, b, a = im.getpixel((x, y)); return tuple(round((a * c + (255 - a) * bg) / 255) for c in (r, g, b))
    n_, d_ = gl['mb_glass'], gl['mb_glass_down']
    mid = O['MB_W'] // 2
    alpha_mid = n_.getpixel((mid, O['MB_H'] // 2))[3]
    expect(n_.getpixel((0, 0))[3] == 0 and n_.getpixel((O['MB_W'] - 1, O['MB_H'] - 1))[3] == 0 and 0.70 * 255 <= alpha_mid <= 0.86 * 255,
           f'translucent dark fill (alpha {alpha_mid / 255:.2f}), the pill corners fully transparent')
    sheen = [sum(n_.getpixel((x, y))[0] for x in range(40, 260)) / 220 for y in (5, 28, 50)]
    expect(sheen[0] > sheen[1] > sheen[2] and 2 <= sheen[0] - sheen[2] <= 20, f'a soft vertical sheen: lighter at the top, darker at the bottom ({[round(v, 1) for v in sheen]})')
    rim_top = max(over(n_, x, 0, 0)[0] for x in range(60, 244)); rim_bot = max(over(n_, x, O['MB_H'] - 1, 0)[0] for x in range(60, 244)); inner = over(n_, mid, 20, 0)[0]
    expect(rim_top > rim_bot > inner - 40 and rim_top - inner > 40 and 2 * (rim_bot - 20) < rim_top, f'a rim light: bright along the top arc ({rim_top}), fading at the bottom ({rim_bot}) against the body ({inner})')
    expect(over(d_, mid, 20, 0)[0] > inner and over(d_, mid, 0, 0)[0] > rim_top - 1, f'the pressed image is brighter ({over(d_, mid, 20, 0)[0]} vs {inner})')
    # the worst case behind the glass: a white row label under the translucent fill (the text sits over x 60..190, y 7..49)
    worst_w = worst_a = 99
    for im in (n_, d_):
        for y in range(7, 49):
            for x in range(O['MB_TEXT_X'], O['MB_TEXT_X'] + O['MB_TEXT_W'], 3):
                bg = over(im, x, y, 255)
                worst_w, worst_a = min(worst_w, contrast((255, 255, 255), bg)), min(worst_a, contrast(dim(pod_ui.MB_ARTIST_RGB), bg))
    print(f'  minibar glass over white: title >= {worst_w:.2f}:1, artist >= {worst_a:.2f}:1')
    expect(worst_w >= 7 and worst_a >= 4.5, f'over the worst case behind the glass (white): the white title {worst_w:.2f}:1 (>= 7), the artist {worst_a:.2f}:1 (>= 4.5)')
    over_black = [contrast(dim(pod_ui.MB_ARTIST_RGB), over(n_, x, 28, 0)) for x in range(60, 190, 10)]
    expect(min(over_black) > 9, f'and on black the artist has {min(over_black):.1f}:1')
    expect(title.type == artist.type == 'hscroll_label' and title.get('only_parent_focus') == 'true' and artist.get('only_parent_focus') == 'true'
           and title.get('ellipses') == 'true' and artist.get('ellipses') == 'true' and title.get('sensitive') == 'false' and artist.get('sensitive') == 'false',
           'title and artist are insensitive hscroll_labels that never scroll (their parent is never focused) and end in an ellipsis')
    expect((title.x, title.y, title.w, title.h) == (O['MB_TEXT_X'], O['MB_TITLE_Y'], O['MB_TEXT_W'], O['MB_TITLE_H'])
           and (artist.x, artist.y, artist.w, artist.h) == (O['MB_TEXT_X'], O['MB_ARTIST_Y'], O['MB_TEXT_W'], O['MB_ARTIST_H']), 'text boxes as the constants')
    expect(title.get('style:normal:font_size') == '17' and title.get('style:normal:text_color') == '#FFFFFF' and artist.get('style:normal:font_size') == '16'
           and artist.get('style:normal:text_color') == pod_ui.MB_ARTIST_RGB, 'title 17 px white, artist 16 px light grey')
    expect((play.x, play.w, play.h) == (O['MB_PLAY_X'], O['MB_BTN_W'], O['MB_H']) and (pause.x, pause.w) == (play.x, play.w) and (nxt.x, nxt.w) == (O['MB_NEXT_X'], O['MB_BTN_W'])
           and play.get('visible') is None and pause.get('visible') == 'false' and pause.get('sensitive') == 'false',
           'play and pause share one place (one shows), next beside it; pause starts hidden and insensitive')
    for b, icon in ((play, 'mb_play'), (pause, 'mb_pause'), (nxt, 'mb_next')):
        expect(b.get('style:normal:icon') == icon and b.get('style:pressed:icon') == icon + '_down'
               and all(os.path.exists(os.path.join(raw, 'images/xx', n + '.png')) for n in (icon, icon + '_down')),
               f'{b.name}: the {icon} glyph and its pressed image exist in the tree')
    from PIL import Image
    def ink(name):
        im = Image.open(os.path.join(raw, 'images/xx', name + '.png')).convert('RGBA'); bb = im.getchannel('A').point(lambda v: 255 if v > 100 else 0).getbbox()
        return im, bb, (bb[2] - bb[0], bb[3] - bb[1])
    (ip, bp, sp), (ia, ba, sa), (ix, bx_, sx) = ink('mb_play'), ink('mb_pause'), ink('mb_next')
    expect(sa == (22, 22) and abs(sx[0] - 30) <= 1 and abs(sx[1] - 17) <= 1 and abs(sp[1] - sa[1]) <= 1 and sp[0] < sp[1],
           f'glyph ink: pause 22 px tall ({sa}), next about 30 x 17 ({sx}), play as tall as the pause ({sp}, a triangle: narrower than tall)')
    expect(all(abs((b[0] + b[2]) / 2 - im.width / 2) <= 1.5 and abs((b[1] + b[3]) / 2 - im.height / 2) <= 1 for im, b in ((ip, bp), (ia, ba), (ix, bx_))),
           'each glyph is centred in its image (the button centres the image): the pause and next centres are the targets\' centres')
    white = all(set(px[:3] for px in im.getdata() if px[3] > 250) <= {(255, 255, 255)} for im in (ip, ia, ix))
    down = [ink(n + '_down')[0] for n in ('mb_play', 'mb_pause', 'mb_next')]
    expect(white and all(max(d.getchannel('A').getdata()) in range(135, 145) for d in down), 'bare white glyphs (no disc), pressed = 55 % alpha')
    others = [p.key for p in pod_pages.PAGES if p is not pod_pages.MENU
              and any(w.name in pod_ui.MB_NAMES for w in awtk_ui.parse(open(os.path.join(raw, 'ui', p.key + '.bin'), 'rb').read()).walk())]
    expect(not others, f'only the menu page carries the bar ({others})')
    tree = asset_tree(menu_asset)
    expect(node(tree, 'pod_minibar').flags & (F_VISIBLE | F_SENSITIVE) == 0 and node(tree, 'pod_mb_play').flags & F_SENSITIVE
           and node(tree, 'pod_mb_pause').flags & (F_VISIBLE | F_SENSITIVE) == 0, 'asset_tree reads the container and the pause button hidden and insensitive')

    # ------------------------------------------------------------------ start: nothing runs in the menu's first paint
    m = BM(); calls = m.start()
    wl = [c[1] for c in calls if c[0] == 'widget_lookup']
    expect(sorted(wl) == sorted(list(pod_ui.MB_NAMES) + ['img_nb_fade', 'pod_scrollview', 'pod_pad']), f'start looks up the fade under the (hidden) bar, the seven bar widgets, the list\'s scroll view and its spacer row ({wl})')
    expect(set(c[0] for c in calls) <= {'access', 'widget_lookup', 'widget_on', 'timer_add', 'calloc'}, f'start only looks up, registers and arms ({sorted(set(c[0] for c in calls))})')
    ons = [(c[1], c[2], c[3]) for c in calls if c[0] == 'widget_on']
    want = [(WIN, EVT_DESTROY, PSYMS['mb_on_destroy']), (WIN, EVT_BG, PSYMS['mb_on_background']), (WIN, EVT_FG, PSYMS['mb_on_foreground']),
            (m.widgets['pod_mb_card'], EVT_AFTER_PAINT, PSYMS['mb_on_paint']), (m.widgets['pod_mb_card'], EVT_CLICK, PSYMS['mb_on_card']),
            (m.widgets['pod_mb_play'], EVT_CLICK, PSYMS['mb_on_play']), (m.widgets['pod_mb_pause'], EVT_CLICK, PSYMS['mb_on_play']),
            (m.widgets['pod_mb_next'], EVT_CLICK, PSYMS['mb_on_next'])]
    blur_ons = [(m.widgets['pod_mb_card'], O['EVT_BEFORE_PAINT'], PSYMS['mb_on_before_paint']), (m.widgets['pod_scrollview'], O['EVT_SCROLL'], PSYMS['mb_on_scroll'])] + [(m.widgets[n], O[e], PSYMS['mb_on_touch']) for n in ('pod_mb_play', 'pod_mb_pause', 'pod_mb_next', 'pod_scrollview') for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT')]
    expect(ons == want + blur_ons, f'window destroy, to-background, to-foreground, the card paint, the four clicks, then the blur: before-paint on the card, press, release and abort on the buttons ({len(ons)})')
    expect(m.timers == [(PSYMS['mb_first'], O['MB_FIRST_MS'])] and 0 < O['MB_FIRST_MS'] <= 250, f'one short one-shot, nothing else is armed at start ({m.timers})')
    expect(not [c for c in calls if c[0] in ('widget_set_visible', 'widget_set_sensitive', 'widget_resize', 'widget_move', 'widget_set_style', 'bitmap_create_ex', 'mclGetPlayPos')],
           'start shows, moves, decodes and reads the player nothing')

    # ------------------------------------------------------------------ patch/home.c starts the bar on the Home instance only
    HOME_WIN = 0x23000000
    def home_machine():
        m = BM()
        for n in ['navigationbar_view', 'img_nb_fade', 'btn_return', 'btn_backtoplayer', 'app_gesture', 'home_sview', 'home_sindicator'] + [f'pod_row{i}' for i in range(len(pod_pages.MENU.rows))]:
            m.widget(n)
        return m
    m = home_machine()
    m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000)
    m.top_main = HOME_WIN; m.timers = []
    m.call(PSYMS['hm_open'], count=3000000)
    expect(m.names().count('window_open') == 1 and (PSYMS['mb_first'], O['MB_FIRST_MS']) in m.timers
           and ('widget_on', m.window, EVT_DESTROY, PSYMS['mb_on_destroy'], m.window) in m.calls,
           'the menu opened as Home starts the bar: the short one-shot is armed, nothing is shown yet')
    expect(('widget_resize', m.widgets['pod_listview'], 320, HOME_LIST_H) in m.calls, 'the list took the whole window (430 px), as before, and keeps it: the bar never resizes it')
    m = home_machine()
    m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN, a1=0x55, count=3000000)
    m.top_main = HOME_WIN; m.timers = []; m.widgets.pop('navigationbar_view')
    m.call(PSYMS['hm_open'], count=3000000)
    expect(m.names().count('window_open') == 1 and (PSYMS['mb_first'], O['MB_FIRST_MS']) not in m.timers,
           'a Home instance whose list could not be laid out (no navbar to hide) gets no bar')
    m = home_machine(); m.fs['/mnt/data/m1plus-bad'] = b'1\n'     # recovery: Tidal opens the normal instance, with its navbar
    m.call(PSYMS['m1plus_home_click'], a0=m.icon('1'), count=3000000)
    expect(m.names().count('window_open') == 1 and (PSYMS['mb_first'], O['MB_FIRST_MS']) not in m.timers and PSYMS['mb_first'] not in [t[0] for t in m.timers]
           and 'timer_add' not in m.names(), 'the normal instance (grid icon, recovery): no bar, no timer')

    # ------------------------------------------------------------------ nothing queued: the menu is exactly as it was
    m = BM(); m.start(); m.timers = []; m.play_pos = -1
    m.first()
    expect(m.timers == [(PSYMS['mb_tick'], O['MB_TICK_MS'])], 'the one-shot arms the repeating tick')
    expect(not [c for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive', 'widget_resize', 'widget_move', 'widget_set_style', 'bitmap_create_ex')],
           'with nothing queued the first work changes nothing (bar hidden, list as it was)')
    m.tick()
    expect(m.names().count('mclGetPlayPos') == 1 and not m.resizes(), 'a tick with nothing queued only asks the player')
    m = BM(); m.play([], 0); m.start(); m.first()
    expect(not m.resizes(), 'an empty queue: nothing shown')
    m = BM(); m.play_pos = 5; m.track(); m.play_pos = 5; m.start(); m.first()
    expect(not m.resizes() and not m.props.get((m.widgets['pod_minibar'], 'visible')), 'a position past the queue: nothing shown')

    # ------------------------------------------------------------------ a track is queued: bar up, list shortened
    m = BM(); m.placeholder(); m.status = 2
    m.track(title='Blue in Green', artist='Miles Davis', album='Kind of Blue')
    key = m.cover('Miles Davis', 'Kind of Blue', rgb=(200, 40, 40))
    m.start(); m.timers = []; m.first()
    bw, sw, pw = (m.widgets[n] for n in ('pod_minibar', 'pod_scrollview', 'pod_pad'))
    expect(m.shown('pod_minibar') and ('widget_set_visible', bw, 1) in m.calls and ('widget_set_sensitive', bw, 1) in m.calls,
           'the bar is shown (visible and sensitive)')
    expect(('widget_set_visible', pw, 1) in m.calls and ('widget_set_sensitive', pw, 1) not in m.calls and ('widget_set_prop_int', sw, 'virtual_h', 9 * 52 + O['MB_PAD']) in m.calls
           and not m.resizes(), f'the list keeps its place and size: its spacer row is shown (visible only, it stays insensitive) and virtual_h grows by MB_PAD ({m.resizes()})')
    expect(m.texts_set() == [(m.widgets['pod_mb_title'], 'Blue in Green'), (m.widgets['pod_mb_artist'], 'Miles Davis')], f'title and artist set ({m.texts_set()})')
    expect(len(m.bitmaps) == 1, 'one cover bitmap')
    b, bw_, bh_, px = m.pixels()
    expect((bw_, bh_) == (S, S), 'the cover bitmap is MB_ART square')
    centre = struct.unpack_from('<I', px, 4 * (S // 2 * S + S // 2))[0]
    expect(centre == 0xff2828c8 and rgb_of(centre) == (200, 40, 40), f'the cover is the album\'s cache picture box-filtered to 36 px ({centre:#x})')
    corners = [struct.unpack_from('<I', px, 4 * (y * S + x))[0] >> 24 for x, y in ((0, 0), (S - 1, 0), (0, S - 1), (S - 1, S - 1))]
    mid_edge = struct.unpack_from('<I', px, 4 * (0 * S + S // 2))[0] >> 24
    expect(corners == [0, 0, 0, 0] and mid_edge == 255 and struct.unpack_from('<I', px, 4 * (S // 2 * S))[0] >> 24 == 255,
           f'the four corner pixels are transparent, the edges between them opaque ({corners}, {mid_edge})')
    alpha = [struct.unpack_from('<I', px, 4 * (y * S + x))[0] >> 24 for y in range(O['MB_ART_R']) for x in range(O['MB_ART_R'])]
    expect(alpha == [255 - c for c in corner_coverage(O['MB_ART_R'])] and 0 < sum(alpha) / len(alpha) < 255 and alpha[0] == 0 and alpha[-1] == 255,
           'the corner arc is anti-aliased: the coverage outside a quarter circle, 8 x 8 samples a pixel, as the Now Playing corners')
    mirrored = all(struct.unpack_from('<I', px, 4 * (y * S + x))[0] >> 24 == struct.unpack_from('<I', px, 4 * ((S - 1 - y) * S + (S - 1 - x)))[0] >> 24
                   for y in range(O['MB_ART_R']) for x in range(O['MB_ART_R']))
    expect(mirrored, 'the four corners are symmetric')
    expect(not m.styles and not [c for c in m.calls if c[0] in ('widget_set_style', 'value_set_uint32')],
           'the pill is not tinted by the album: the payload never sets a style or a colour')
    expect(('widget_load_image', 'file://' + art_file(key)) in m.calls and 'file:///tmp/coverpic.jpg' not in m.loads, 'the cover came from the album\'s cache file')
    expect(m.shown('pod_mb_pause') and not m.visible('pod_mb_play'), 'playing: the pause glyph shows')
    expect(m.timers == [(PSYMS['mb_tick'], O['MB_TICK_MS'])], 'the repeating tick is armed once')
    got = m.paint()
    expect(got == [(b, (0, 0, S, S), (O['MB_ART_X'], O['MB_ART_Y'], S, S))], f'paint draws the resident cover at (14, 10), 36 x 36, nothing else ({got})')
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'fopen', 'cc_decode')], 'paint decodes and creates nothing')

    # a second tick on the same track: only the player is asked
    loads = len(m.loads)
    m.calls = []; m.tick()
    expect(not m.texts_set() and not m.styles and len(m.loads) == loads and not m.resizes() and 'bitmap_create_ex' not in m.names(),
           'an unchanged track: no label, decode, style or layout work')
    expect(m.names().count('mclGetPlayStatus') == 1 and not [c for c in m.calls if c[0] == 'widget_set_visible'], 'and the glyph stays when the state does')
    # pause from outside (hardware key, Now Playing): the glyph follows at the next tick
    m.status = 3; m.calls = []; m.tick()
    expect(m.shown('pod_mb_play') and not m.visible('pod_mb_pause') and not m.sensitive('pod_mb_pause'), 'paused: the play glyph shows, pause is hidden and insensitive')
    expect(len([c for c in m.calls if c[0] == 'widget_set_visible']) == 2, 'two visibility calls, once')
    m.status = 0; m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] == 'widget_set_visible'], 'stopped counts as not playing: no change from paused')

    # the track changes: labels, cover and colour again
    m.track(title='So What', artist='Miles Davis', album='Kind of Blue', path='/mnt/mmc/a/2.flac', name='2.flac')
    m.calls = []; m.tick()
    expect(m.texts_set() == [(m.widgets['pod_mb_title'], 'So What'), (m.widgets['pod_mb_artist'], 'Miles Davis')], 'a new track: new labels')
    expect(len(m.bitmaps) == 1 and 'bitmap_create_ex' not in m.names(), 'the one cover bitmap is reused')
    # another album: its cover
    m.track(title='Roygbiv', artist='Boards of Canada', album='Music Has the Right', path='/mnt/mmc/b/1.flac', name='1.flac')
    m.cover('Boards of Canada', 'Music Has the Right', rgb=(40, 200, 90))
    m.calls = []; m.tick()
    expect(centre_rgb(m) == (40, 200, 90) and not m.styles, 'another album: its own cover in the same bitmap, no colour change')
    m.paint()
    # an untitled track: the file name; an artist-less one: an empty line
    m.track(title='', artist='', album='', path='/mnt/mmc/c/x.flac', name='x.flac')
    m.calls = []; m.tick()
    expect(m.texts_set() == [(m.widgets['pod_mb_title'], 'x.flac'), (m.widgets['pod_mb_artist'], '')], f'no tag title: the file name; no artist: empty ({m.texts_set()})')

    # ------------------------------------------------------------------ the /tmp picture of a track without a cache file
    m = BM(); m.placeholder(); m.status = 2
    m.track(title='Live', artist='', album='')
    m.tmp_cover(rgb=(40, 40, 200))
    m.start(); m.first()
    expect(('widget_load_image', 'file:///tmp/coverpic.jpg') in m.calls, 'no cache file: the /tmp picture of the source type')
    expect(centre_rgb(m) == (40, 40, 200), 'decoded into the cover bitmap')
    n_load = len(m.loads); m.calls = []; m.tick()
    expect(len(m.loads) == n_load + 0 and m.names().count('fopen') == 1, 'a settle tick reads the file\'s hash again, and decodes nothing when it is unchanged')
    m.tmp_cover(data=b'other-bytes' * 33, rgb=(200, 200, 40))
    m.calls = []; m.tick()
    expect(('widget_load_image', 'file:///tmp/coverpic.jpg') in m.calls and centre_rgb(m) == (200, 200, 40),
           'demo wrote the new picture a moment later: the cover is redone with it')
    for _ in range(6): m.tick()
    m.calls = []; m.tick()
    expect('fopen' not in m.names(), f'after MB_SETTLE ticks the file is left alone ({O["MB_SETTLE"]})')
    # demo still making it
    m = BM(); m.placeholder(); m.status = 2
    m.track(title='Live', artist='', album=''); m.setword(pod.DATA['COVER_SRC'][0], 1)
    m.start(); m.first()
    expect(m.shown('pod_minibar') and 'fopen' not in m.names() and ('widget_load_image', 'p_default') in m.calls,
           'the file being made: the bar shows with the placeholder, nothing read')
    m.tmp_cover(); m.calls = []; m.tick()
    expect(('widget_load_image', 'file:///tmp/coverpic.jpg') in m.calls, 'and the picture is taken when it is complete')
    # source types without a JPEG file
    for src in (0, 4, 6, 7):
        m = BM(); m.placeholder(); m.load_image = 0; m.status = 2; m.track(title='Live', artist='', album=''); m.setword(pod.DATA['COVER_SRC'][0], src)
        m.start(); m.first()
        expect('file:///tmp/coverpic.jpg' not in m.loads and ('widget_load_image', 'p_default') in m.calls and centre_rgb(m) == (90, 90, 90),
               f'source type {src}: the stock placeholder disc')
    # the placeholder itself missing: flat grey, still a card
    m = BM(); m.status = 2; m.track(title='Live', artist='', album='')
    m.start(); m.first(); b, w_, h_, px = m.pixels()
    expect(struct.unpack_from('<I', px, 4 * (S // 2 * S + S // 2))[0] == O['MB_GREY'], 'no placeholder image: flat grey')

    # ------------------------------------------------------------------ nothing queued again: the bar goes, the list is back
    m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover()
    m.start(); m.first()
    sw, pw = m.widgets['pod_scrollview'], m.widgets['pod_pad']
    m.props[(sw, 'yoffset')] = 9 * 52 + O['MB_PAD'] - HOME_LIST_H   # scrolled to the end of the padded list
    m.play_pos = -1; m.calls = []; m.tick()
    bw = m.widgets['pod_minibar']
    expect(not m.visible('pod_minibar') and not m.sensitive('pod_minibar') and ('widget_set_visible', bw, 0) in m.calls,
           'the queue emptied: the bar is hidden and insensitive')
    expect(('widget_set_visible', pw, 0) in m.calls and ('widget_set_prop_int', sw, 'virtual_h', 9 * 52) in m.calls and not m.resizes(),
           'and the spacer row is hidden again: virtual_h is as it was, the list was never moved or resized')
    expect(('widget_set_prop_int', sw, 'yoffset', 9 * 52 - HOME_LIST_H) in m.calls, 'a list scrolled past the new end is brought back to it')
    m.calls = []; m.tick()
    expect(not m.resizes() and 'widget_set_visible' not in m.names(), 'and nothing more happens while nothing is queued')
    m.track(); m.calls = []; m.tick()
    expect(m.shown('pod_minibar') and ('widget_set_visible', pw, 1) in m.calls and m.texts_set(), 'a track again: the bar is back, labelled anew, the spacer shown')
    m.props[(sw, 'yoffset')] = 30; m.props[(sw, 'virtual_h')] = 9 * 52 + O['MB_PAD']; m.play_pos = -1; m.calls = []; m.tick()
    expect(('widget_set_prop_int', sw, 'yoffset', 9 * 52 - HOME_LIST_H) not in m.calls and not [c for c in m.calls if c[:3] == ('widget_set_prop_int', sw, 'yoffset')],
           'a list within its new range keeps its position')

    # ------------------------------------------------------------------ the timer's lifecycle
    m = BM(); m.status = 2; m.track(); m.start(); m.first()
    m.timers = []; m.calls = []
    m.fire(EVT_BG)
    expect(('timer_remove', 0x777) in m.calls, 'to-background removes the timer')
    r = m.tick()
    expect(r == 0 and m.names() == [], 'a tick that still arrives ends itself and does nothing')
    m.calls = []; m.fire(EVT_BG)
    expect(m.names().count('timer_remove') <= 1, 'a second to-background has nothing to remove')
    m.timers = []; m.calls = []
    m.fire(EVT_FG)
    expect(m.timers == [(PSYMS['mb_first'], O['MB_FIRST_MS'])], 'to-foreground arms the short one-shot again')
    m.timers = []; m.fire(EVT_FG)
    expect(not m.timers, 'and not twice')
    m.first()
    expect(m.timers == [(PSYMS['mb_tick'], O['MB_TICK_MS'])], 'the one-shot re-arms the tick')
    m.status = 3; m.calls = []; m.first()
    expect(m.shown('pod_mb_play'), 'back in front the state is read again (paused from elsewhere)')
    m.calls = []; m.call(PSYMS['mb_on_destroy'], a0=WIN + 0x100, a1=0)
    expect(not m.calls, 'another window\'s destroy is ignored')
    bmp = next(iter(m.bitmaps))
    m.call(PSYMS['mb_on_destroy'], a0=WIN, a1=0)
    expect(('timer_remove', 0x777) in m.calls and ('bitmap_destroy', bmp) in m.calls, 'destroy removes the timer and frees the cover')
    m.tick(); a = m.names(); m.first(); a += m.names()
    expect(a == [], f'late callbacks do nothing ({a})')
    expect(not m.paint(), 'no paint after destroy')
    nt = len(m.timers)
    m.call(PSYMS['mb_on_background'], a0=WIN, a1=0); a = m.names(); m.call(PSYMS['mb_on_foreground'], a0=WIN, a1=0)
    expect(a + m.names() == [] and len(m.timers) == nt, 'and the window events of a finished page are ignored')
    # a tick returns RET_REPEAT while it lives
    m = BM(); m.track(); m.start(); m.first()
    expect(m.tick() == O['RET_REPEAT'], 'the tick answers RET_REPEAT')
    m.fire(EVT_BG); expect(m.tick() == 0, 'out of front it answers RET_OK and ends')
    # a one-shot that fires after the window went to the back does not arm the tick
    m = BM(); m.track(); m.start(); m.fire(EVT_BG); m.timers = []; m.first()
    expect(not m.timers, 'a late one-shot after to-background arms nothing')

    # ------------------------------------------------------------------ the buttons call the stock player functions
    m = BM(); m.placeholder(); m.status = 3; m.track(); m.cover(); m.start(); m.first()
    expect(m.shown('pod_mb_play'), 'paused: play shows')
    m.calls = []; m.click('pod_mb_play')
    expect(m.cmds == [('playpause',)] and ('playpause_quick_click', 0) in m.calls, 'play calls playpause_quick_click()')
    expect(m.shown('pod_mb_pause') and not m.visible('pod_mb_play'), 'and the glyph follows at once (status 2 now)')
    m.cmds = []; m.click('pod_mb_pause')
    expect(m.cmds == [('playpause',)] and m.shown('pod_mb_play') and not m.sensitive('pod_mb_pause'), 'pause calls the same function and swaps back')
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 8, 123456); m.setword(e + 12, 7)
    m.cmds = []; m.calls = []; m.click('pod_mb_next', e=e)
    expect(m.cmds == [('next', 123456, 7, 0)] and ('next_quick_click', 0) in m.calls, 'next calls next_quick_click(the click event, 0): the event\'s time is what stock reads')
    expect(m.names().count('mclGetPlayPos') >= 1, 'and the bar looks at the player again at once')
    m.clock = 4242; m.cmds = []; m.click('pod_mb_next')
    expect(m.cmds == [('next', 4242, 0, 0)], 'without an event it hands stock one made from the clock')
    m.calls = []; m.click('pod_mb_card')
    expect(m.names() == ['on_backtoplayer_onclick'] and not m.cmds[1:], 'a tap on the card opens Now Playing as the menu row does')
    expect(O['COVER_SRC_BUSY'] == 1, 'sanity')

    # ------------------------------------------------------------------ the radio owns the output: the bar shows the station (patch/minibar.c mb_radio)
    ST_ = dict(IDLE=0, CONNECTING=1, PLAYING=2, ERROR=3, STOPPED=4, PAUSED=5)
    STAT = '#EXTM3U\n#M1+:Germany\tMP3\t128\thttp://logo.example/a.png\n#EXTINF:-1,Alpha FM\nhttp://one.example/a\n#EXTINF:-1,Beta\nhttp://two.example/b\n'
    def radio(m, st, at=0, err='', text=STAT, own=1):
        """The engine's state poked in (patch/radio.c rd: state, at, tries, fd, 5 words, rd_list_t (3628 bytes), error) and its list parsed from text."""
        l = m.call(PSYMS['rd_list'])
        b = m.malloc(len(text) + 8); m.u.mem_write(b, text.encode() + b'\0' * 8)
        if not m.word(l + 8): m.call(PSYMS['rd_list_set'], a0=l, a1=b, a2=len(text), a3=0, count=40000000)
        m.setword(l - 36, st); m.setword(l - 32, at); m.u.mem_write(l + 3628, err.encode() + b'\0'); m.setword(l + 3700, own)   # own: rd.owns, after the 72-byte error text
        expect(m.call(PSYMS['rd_state']) == st and m.call(PSYMS['rd_at']) == at and m.read_cstr(m.call(PSYMS['rd_error'])) == err, f'(the engine state {st} at {at} is in place)')
    def texts(m):
        t = dict(m.texts_set())
        def u(x):   # the payload's own strings come back twice over from the mocked translation (radio.py u8)
            for _ in range(2):
                try: x = x.encode('latin-1').decode('utf-8')
                except (UnicodeError, AttributeError): break
            return x
        return u(t.get(m.widgets['pod_mb_title'])), u(t.get(m.widgets['pod_mb_artist']))
    def nxt(m):   # 'live': visible, sensitive, the white glyphs (the asset's own until the radio changes them); 'grey': visible, insensitive, mb_next_off in all three styles
        w = m.widgets['pod_mb_next']; vis, sens = bool(m.props.get((w, 'visible'), 1)), bool(m.props.get((w, 'sensitive'), 1))
        ic = tuple(m.props.get((w, f'style:{s}:icon')) for s in ('normal', 'over', 'pressed'))
        if vis and sens and ic in ((None,) * 3, ('mb_next', 'mb_next', 'mb_next_down')): return 'live'
        if vis and not sens and ic == ('mb_next_off',) * 3: return 'grey'
        return f'wrong ({vis}, {sens}, {ic})'
    def pic(m): return tuple(m.props.get((m.widgets['pod_mb_pause'], f'style:{s}:icon')) for s in ('normal', 'over', 'pressed'))   # the pause button's icons: None = the asset's own (mb_pause)
    def started(): m = BM(); m.placeholder(); m.status = 2; m.hs = 1; m.track(title='Stale Song'); m.cover(); m.start(); m.first(); return m
    m = started()
    expect(texts(m) == ('Stale Song', 'Artist') and nxt(m) == 'live', 'the local track first')
    for st, line in ((ST_['CONNECTING'], 'Connecting…'), (ST_['PLAYING'], 'Live'), (ST_['PAUSED'], 'Paused')):
        m = started(); radio(m, st); m.status = 3 if st == ST_['PAUSED'] else 2; m.calls = []; m.tick()
        t = texts(m)
        expect(t == ('Alpha FM', line) and m.shown('pod_minibar'), f'state {st}: the station and "{line}" instead of the stale song ({t})')
        expect(nxt(m) == 'grey' and (m.shown('pod_mb_pause') if st != ST_['PAUSED'] else m.shown('pod_mb_play')), f'state {st}: the next button stays, greyed and insensitive ({nxt(m)}); Stop glyph (mb_stop) while connecting or playing, play when paused')
        if st != ST_['PAUSED']: expect(pic(m) == ('mb_stop', 'mb_stop', 'mb_stop_down'), f'state {st}: the button\'s icons are the stop square ({pic(m)})')
    m = started(); radio(m, ST_['ERROR'], err='No response'); m.status = 1; m.hs = 0; m.tick()
    expect(texts(m) == ('Alpha FM', "Can't play: No response") and m.shown('pod_mb_play') and nxt(m) == 'grey', f'Error after a session: the error text, play glyph (retry) ({texts(m)})')
    m = started(); radio(m, ST_['ERROR'], err='No response'); m.status = 2; m.hs = 1; m.tick()
    expect(texts(m) == (None, None) and nxt(m) == 'live', 'an Error left standing while a local song really plays: the song stays, nothing is relabelled')
    for st in (ST_['IDLE'], ST_['STOPPED']):   # Idle: nothing played this session; Stopped with a local track started since (the hook cleared the flag)
        m = started(); radio(m, st, own=0); m.tick()
        expect(texts(m) == (None, None) and nxt(m) == 'live' and m.shown('pod_minibar'), f'state {st}: the local logic is unchanged (the song stays, nothing relabelled)')
    m = started(); radio(m, ST_['STOPPED']); m.status = 1; m.hs = 0; m.tick()
    expect(texts(m) == ('Alpha FM', 'Stopped') and m.shown('pod_mb_play') and nxt(m) == 'grey', f'Stopped by the radio: the station stays, "Stopped", play glyph, grey next ({texts(m)})')
    m = started(); radio(m, ST_['STOPPED']); m.status = 2; m.hs = 1; m.tick()
    expect(texts(m) == (None, None) and nxt(m) == 'live', 'Stopped, but a local song really plays (a key resumed stock): the song shows')
    # no change, no redo; a change of state redoes the labels; another station the cover too
    m = started(); radio(m, ST_['PLAYING']); m.tick(); m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'bitmap_create_ex', 'widget_load_image')], 'a second tick in the same state redoes nothing')
    radio(m, ST_['PAUSED']); m.calls = []; m.tick()
    expect(texts(m)[1] == 'Paused' and not [c for c in m.calls if c[0] in ('bitmap_create_ex', 'widget_load_image')], 'Playing to Paused: the labels, not the cover')
    radio(m, ST_['PAUSED'], at=1); m.calls = []; m.tick()
    expect(texts(m) == ('Beta', 'Paused') and [c for c in m.calls if c[0] == 'widget_load_image'], 'another station: its name and a new cover')
    # back to local: the track, next visible again
    radio(m, ST_['STOPPED'], at=1); m.status = 1; m.hs = 0; m.calls = []; m.tick()
    expect(texts(m) == ('Beta', 'Stopped') and nxt(m) == 'grey', f'the radio stopped by its Stop: the station stays, grey next ({texts(m)})')
    radio(m, ST_['STOPPED'], at=1, own=0); m.tick()   # a local track started: the mclStartPlayer hook cleared rd.owns
    expect(texts(m) == ('Stale Song', 'Artist') and nxt(m) == 'live' and pic(m) == ('mb_pause', 'mb_pause', 'mb_pause_down'), f'a local track started: the track and the next button come back, white and sensitive ({nxt(m)}), the pause button its bars again ({pic(m)})')
    # the cover: the glyph without a logo (card grey), the logo when cached
    m = started(); radio(m, ST_['PLAYING'], text='#EXTM3U\n#EXTINF:-1,Plain\nhttp://p.example/a\n'); m.images['pod_ic_rd_art'] = (16, 16, bytes((255, 255, 255, 255)) * 256); m.tick()
    _, w_, h_, px_ = m.pixels(); corner = struct.unpack_from('<I', px_, 0)[0]; mid = rgb_of(struct.unpack_from('<I', px_, 4 * (h_ // 2 * w_ + w_ // 2))[0]); edge = rgb_of(struct.unpack_from('<I', px_, 4 * (h_ // 2 * w_ + 3))[0])
    expect(edge == (0x2c, 0x2c, 0x2e) and mid == (255, 255, 255) and corner >> 24 < 255, f'no logo: the radio glyph on the card grey with rounded corners (edge {edge}, middle {mid})')
    m = started(); radio(m, ST_['PLAYING'], text=STAT)
    ua = m.malloc(32); m.u.mem_write(ua, b'http://logo.example/a.png\0')
    h = m.call(PSYMS['rd_logo_hash'], a0=ua, count=100000); lp = f'/mnt/mmc/Radio/.logos/{h:08x}.jpg'
    m.present.add(lp); m.blobs[lp] = b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR' + struct.pack('>II', 192, 192)
    m.images['file://' + lp] = (8, 8, bytes((200, 30, 30, 255)) * 64); m.load_image = 0; m.tick()
    expect(centre_rgb(m) == (200, 30, 30), f'a cached logo: it is the cover ({centre_rgb(m)})')
    # a logo that is not cached: nothing is started while the worker is busy, the first tick after it is idle asks for it
    m = started(); radio(m, ST_['PLAYING'], text=STAT)
    for sym in ('rd_logo_running', 'rd_logo_start'): m.handlers[PSYMS[sym]] = sym
    m.logo_busy = 1; m.calls = []; m.tick(); m.tick()
    expect(not [c for c in m.calls if c[0] == 'rd_logo_start'], 'the logo worker busy: the mini bar starts no download')
    m.logo_busy = 0; m.calls = []; m.tick()
    expect([c for c in m.calls if c[0] == 'rd_logo_start'] == [('rd_logo_start', 'http://logo.example/a.png')], f'the worker idle: the next tick asks for the pending logo ({[c for c in m.calls if c[0] == "rd_logo_start"]})')
    # the controls
    m = started(); radio(m, ST_['PLAYING']); m.tick(); m.cmds = []; m.calls = []; m.click('pod_mb_pause')
    expect(m.cmds == [('mclStop',)] and m.call(PSYMS['rd_state']) == ST_['STOPPED'] and not [c for c in m.cmds if c[0] == 'mclSetPause'], f'Playing: the button stops the station, no pause ({m.cmds})')
    m = started(); radio(m, ST_['PAUSED']); m.status = 3; m.tick(); m.cmds = []; m.click('pod_mb_play')
    expect(m.cmds == [('mclSetResume',)] and m.shown('pod_mb_pause') and pic(m) == ('mb_stop', 'mb_stop', 'mb_stop_down'), f'Paused: play is mclSetResume, then the stop glyph ({m.cmds})')
    m = started(); radio(m, ST_['PAUSED']); m.tick(); m.cmds = []; m.wifi = -1; m.click('pod_mb_play')
    expect(m.cmds == [('mclStop',)] and m.call(PSYMS['rd_state']) == ST_['ERROR'] and m.call(PSYMS['rd_error']) != 0, f'Paused without Wi-Fi: play stops the dead stream and says No Wi-Fi, no resume ({m.cmds})')
    m = started(); radio(m, ST_['CONNECTING']); m.tick(); m.cmds = []; m.click('pod_mb_pause')
    expect(m.cmds == [('mclStop',)] and m.call(PSYMS['rd_state']) == ST_['STOPPED'], f'Connecting: the button stops too ({m.cmds})')
    m = started(); radio(m, ST_['ERROR'], err='No response'); m.status = 1; m.hs = 0; m.tick(); m.cmds = []; m.click('pod_mb_play'); tx = texts(m)
    expect(m.cmds[-1:] == [('start', 'http://one.example/a')] and m.call(PSYMS['rd_state']) == ST_['CONNECTING'] and tx == ('Alpha FM', 'Connecting…'),
           f'Error: play retries the same station ({m.cmds}, {tx})')
    m = started(); radio(m, ST_['PLAYING']); m.tick(); m.cmds = []; m.click('pod_mb_pause'); m.status = 1; m.hs = 0; m.calls = []; m.tick(); tx = texts(m)
    expect(m.call(PSYMS['rd_state']) == ST_['STOPPED'] and tx == ('Alpha FM', 'Stopped') and m.shown('pod_mb_play') and nxt(m) == 'grey', f'Stop from the bar: the bar keeps the station, Stopped, play glyph, grey next ({tx})')
    m.cmds = []; m.click('pod_mb_play'); tx = texts(m)
    expect(m.cmds[-1:] == [('start', 'http://one.example/a')] and m.call(PSYMS['rd_state']) == ST_['CONNECTING'] and tx == ('Alpha FM', 'Connecting…'), f'Stopped: play starts the same station again ({m.cmds}, {tx})')
    m.click('pod_mb_pause'); m.status = 1; m.hs = 0; m.tick(); m.calls = []; m.click('pod_mb_card')
    expect(any(c[0] == 'window_open' and 'm1plus_radionp' in str(c) for c in m.calls), 'the card opens radio Now Playing while Stopped')
    m = started(); radio(m, ST_['STOPPED']); m.status = 1; m.hs = 0; m.tick(); m.cmds = []; m.wifi = -1; m.click('pod_mb_play')
    expect(m.call(PSYMS['rd_state']) == ST_['ERROR'] and not [c for c in m.cmds if c[0] == 'start'], 'Stopped without Wi-Fi: play says No Wi-Fi, no start')
    m = started(); radio(m, ST_['PLAYING']); m.tick(); m.cmds = []; m.click('pod_mb_next')
    expect(m.cmds == [] and nxt(m) == 'grey', 'next does nothing for a station (and stays grey)')
    m = started(); radio(m, ST_['PLAYING']); m.tick(); m.calls = []; m.click('pod_mb_card')
    expect(any(c[0] == 'window_open' and 'm1plus_radionp' in str(c) for c in m.calls), f'the card opens radio Now Playing ({[c for c in m.calls if c[0] == "window_open"]})')
    m = started(); radio(m, ST_['ERROR'], err='x'); m.status = 1; m.hs = 0; m.tick(); m.calls = []; m.click('pod_mb_card')
    expect(any(c[0] == 'window_open' and 'm1plus_radionp' in str(c) for c in m.calls), 'also in Error (stock\'s entry hook only takes a running station)')

    # ------------------------------------------------------------------ hit tests with demo's own widget_find_target
    m = BM(); m.placeholder(); m.status = 3; m.track(); m.cover(); m.start(); m.first()
    def world(m):
        t = asset_tree(menu_asset)
        lv_, sv_, sb_ = (node(t, n) for n in LISTS)   # patch/home.c hm_fill_window: the list from HOME_PAD, 430 px (then the bar may shorten it)
        lv_.y = O['HOME_PAD']
        for nd in (lv_, sv_, sb_): nd.h = HOME_LIST_H
        names = {m.widgets[n]: n for n in list(pod_ui.MB_NAMES) + list(LISTS) + ['navigationbar_view', 'img_nb_fade', 'pod_pad'] if n in m.widgets}
        for h, n in names.items():
            nd = node(t, n)
            if not nd: continue
            for k in 'xywh':
                if (h, k) in m.props: setattr(nd, k, m.props[(h, k)])
            if (h, 'visible') in m.props: nd.flags = nd.flags & ~F_VISIBLE | (F_VISIBLE if m.props[(h, 'visible')] else 0)
            if (h, 'sensitive') in m.props: nd.flags = nd.flags & ~F_SENSITIVE | (F_SENSITIVE if m.props[(h, 'sensitive')] else 0)
        nb = node(t, 'navigationbar_view'); nb.flags &= ~(F_VISIBLE | F_SENSITIVE)
        # the arranged rows (patch/menu.c): a menu long enough to scroll (Cover Flow ... Shuffle, Settings, then Extras: eight rows; the default menu is shorter),
        # 52 px apart from y 0 (the Home list's first row is HOME_PAD down); the others are hidden and parked; the spacer row follows the shown rows (visible while the bar shows)
        sv = node(t, 'pod_scrollview')
        shown = [1, 2, 3, 4, 5, 6, pod_pages.SETTINGS_ID, len(pod_pages.ITEMS)]
        for i, r in enumerate(c for c in sv.children if c.name.startswith('pod_row')):
            r.y = shown.index(i) * 52 if i in shown else 0
            if i not in shown: r.flags &= ~(F_VISIBLE | F_SENSITIVE)
        node(t, 'pod_pad').y = len(shown) * 52
        return t
    def target(m, x, y, t=None):
        return stock_target(m, t or world(m), x, y)
    bx, by = O['MB_X'], O['MB_Y']
    for name, cx in (('pod_mb_play', O['MB_PLAY_X'] + O['MB_BTN_W'] // 2), ('pod_mb_next', O['MB_NEXT_X'] + O['MB_BTN_W'] // 2)):
        for cy in (by + O['MB_H'] // 2, by + 14, by + O['MB_H'] - 14):
            p = target(m, bx + cx, cy)
            expect(p[-1] == name and p[-2] == 'pod_minibar', f'{name} is reached at ({bx + cx}, {cy}) ({p})')
    for x, y, what in ((bx + 100, by + 29, 'the title'), (bx + 30, by + 29, 'the cover'), (bx + 4, by + 4, 'the corner'), (bx + 191, by + 29, 'the gap before play'),
                       (bx + 120, by + 52, 'under the artist')):
        p = target(m, x, y)
        expect(p[-1] == 'pod_mb_card', f'{what}: the card takes the tap ({p})')
    p = target(m, 160, by + O['MB_H'] + 4)
    expect('pod_minibar' not in p, f'under the card nothing of the bar ({p})')
    # the last menu row above the card
    rows_end = O['HOME_PAD'] + 7 * 52   # the 7th row's bottom
    p = target(m, 160, O['HOME_PAD'] + 6 * 52 + 26)
    expect('pod_row18' in p, f'the 7th row (Settings) (y {O["HOME_PAD"] + 6 * 52}..{rows_end}) above the card is hit ({p})')
    p = target(m, 160, O['MB_Y'] - 2)
    expect('pod_minibar' not in p and p[-1] != 'pod_mb_card', f'the strip above the card is not the card ({p})')
    last_row_bottom = O['HOME_PAD'] + HOME_LIST_H - O['MB_PAD']   # the list scrolled to the end of its padded content
    expect(last_row_bottom + O['MB_GAP'] == O['MB_Y'], 'scrolled to the end, the last row ends exactly MB_GAP above the pill')
    # the list runs to the window's bottom under the pill: a row is under it, and the pill (the later sibling) takes the touch there; the row above is reached
    p = target(m, 160, O['MB_Y'] + 14)
    expect(p[-1] == 'pod_mb_card' and f'pod_row{len(pod_pages.ITEMS)}' not in p, f'where Extras lies under the pill the pill takes the touch ({p})')
    p = target(m, 160, O['MB_Y'] - 4)
    expect(f'pod_row{len(pod_pages.ITEMS)}' in p, f'the Extras row just above the pill is reached ({p})')
    # hidden bar: the full-height list takes everything
    m = BM(); m.start(); m.first()
    t = world(m)
    p = stock_target(m, t, bx + O['MB_PLAY_X'] + 24, by + 29)
    expect('pod_minibar' not in p and 'pod_mb_play' not in p and 'pod_mb_card' not in p, f'with nothing queued the bar takes no touch ({p})')
    p = stock_target(m, t, 160, by + 29)
    expect('pod_scrollview' in p, f'and the list is under that place ({p})')
    # playing: the hidden pause button takes no touch where play is
    m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover(); m.start(); m.first()
    p = target(m, bx + O['MB_PLAY_X'] + 24, by + 29)
    expect(p[-1] == 'pod_mb_pause', f'playing: the pause button is the target at that place ({p})')
    m.status = 3; m.tick()
    p = target(m, bx + O['MB_PLAY_X'] + 24, by + 29)
    expect(p[-1] == 'pod_mb_play', f'paused: the play button is ({p})')

    # ------------------------------------------------------------------ every failure falls back to the plain menu
    for path in (KILL_SD, KILL_DATA):
        m = BM(); m.track(); m.present.add(path); calls = m.start()
        expect(not m.timers and not [c for c in calls if c[0] in ('widget_on', 'timer_add', 'widget_lookup')], f'{path}: no lookup, no handler, no timer')
    for gone in list(pod_ui.MB_NAMES) + ['pod_scrollview', 'pod_pad']:
        m = BM(); m.track()
        m.widgets.pop(gone)
        calls = m.start()
        expect(not m.timers and not [c for c in calls if c[0] in ('widget_on', 'timer_add')], f'no {gone}: no handler, no timer, no bar')
        m.first(); a = list(m.calls); m.tick(); a += m.calls
        expect(not [c for c in a if c[0] in ('widget_set_visible', 'widget_resize', 'widget_set_style')], f'no {gone}: later callbacks change nothing')
    m = BM(sb=False); m.placeholder(); m.status = 2; m.track(); m.cover(); m.start(); m.first()
    expect(m.shown('pod_minibar'), 'a menu without a scroll bar (a short list) still gets its bar')
    for ev in (EVT_DESTROY, EVT_BG, EVT_FG, EVT_AFTER_PAINT, EVT_CLICK):
        m = BM(); m.track(); m.on_fail = {ev}
        m.start()
        expect(not m.timers, f'a widget_on of event {ev:#x} refused: no timer')
        m.first(); a = list(m.calls); m.tick(); a += m.calls
        expect(not [c for c in a if c[0] in ('widget_set_visible', 'widget_resize', 'widget_set_style')], f'event {ev:#x} refused: the bar never shows')
    m = BM(); m.track(); m.timer_fail = True; m.start()
    expect(not m.timers and not m.props.get((m.widgets['pod_minibar'], 'visible')), 'no timer: no bar')
    m.first()
    expect(not m.resizes(), 'and a stale callback does not show it')
    m = BM(); m.status = 2; m.track(); m.bitmap_ok = False; m.cover(); m.start(); m.first()
    expect(m.shown('pod_minibar') and not m.paint(), 'no bitmap: the bar shows without a cover, paint draws nothing')
    m = BM(); m.status = 2; m.track(); m.placeholder(); m.load_image = 1; m.images = {}
    m.start(); m.first()
    expect(m.shown('pod_minibar') and centre_rgb(m) == rgb_of(O['MB_GREY']), 'a cover that does not decode: flat grey')
    # a second window before the first one's destroy: the old one's timer goes
    m = BM(); m.track(); m.start(); m.first(); m.calls = []; m.start(win=WIN + 0x100)
    expect(('timer_remove', 0x777) in m.calls and m.timers[-1:] == [(PSYMS['mb_first'], O['MB_FIRST_MS'])], 'a window started over a live one replaces the old timer')
    m.calls = []; m.call(PSYMS['mb_on_destroy'], a0=WIN, a1=0)
    expect(not m.calls, 'the earlier window\'s late destroy leaves the new one alone')

    # ------------------------------------------------------------------ the backdrop blur (experimental: guarded, tools/pod_blur.py is the model)
    import random, pod_blur
    FBW, FBH, OX, OY = 320, 480, O['MB_X'], 30 + O['MB_Y']     # the screen, and the pill's place on it (the window is under the 30 px system bar)
    MW, MH = O['MB_W'], O['MB_H']
    expect(pod_blur.W == MW and pod_blur.H == MH and (pod_blur.HW, pod_blur.HH) == (O['MB_HW'], O['MB_HH']) and MW == 2 * O['MB_HW'] and MH == 2 * O['MB_HH'],
           'the blur model and the payload agree on the pill and its half-resolution plane')

    # the pinned stock offsets, proved against demo's own code (offsets.inc has the addresses): canvas_translate adds to ox, oy; canvas_get_clip_rect reads
    # the clip at 0x10..0x1c; canvas_get_width goes canvas -> lcd (0x30) -> lcd_get_width (0xb0); lcd_get_height reads 0xb4; the 565 lcd's set_line_length writes 0x120
    m = Machine()
    cv = m.alloc(0x40); m.u.mem_write(cv, bytes(0x40)); lcd = m.alloc(0x160); m.u.mem_write(lcd, bytes(0x160))
    m.setword(cv + O['CANVAS_OX'], 10); m.setword(cv + O['CANVAS_OY'], 20); m.setword(cv + O['CANVAS_LCD'], lcd)
    m.call(0x6434d4, a0=cv, a1=3, a2=5)
    expect((m.word(cv + O['CANVAS_OX']), m.word(cv + O['CANVAS_OY'])) == (13, 25), 'stock canvas_translate (0x6434d4) adds to the words at CANVAS_OX / CANVAS_OY')
    for off, v in ((O['CANVAS_CLIP'], 5), (O['CANVAS_CLIP'] + 4, 6), (O['CANVAS_CLIP'] + 8, 104), (O['CANVAS_CLIP'] + 12, 65)): m.setword(cv + off, v)
    rect = m.alloc(16); m.call(0x643718, a0=cv, a1=rect)
    expect(tuple(struct.unpack('<4i', bytes(m.u.mem_read(rect, 16)))) == (5, 6, 100, 60), 'stock canvas_get_clip_rect (0x643718) reads left, top, right, bottom (inclusive) at CANVAS_CLIP..+12')
    m.setword(lcd + O['LCD_W'], 320); m.setword(lcd + O['LCD_H'], 480)
    expect(m.call(0x64352c, a0=cv) == 320 and m.call(0x643554, a0=cv) == 480 and m.call(0x658484, a0=lcd) == 320 and m.call(0x6584b0, a0=lcd) == 480,
           'stock canvas_get_width / _height go through the lcd at CANVAS_LCD and read LCD_W / LCD_H')
    m.call(0x695034, a0=lcd, a1=640)
    expect(m.word(lcd + O['LCD_LINE']) == 640 and m.word(lcd + 0x124) == 640, 'the 565 lcd\'s set_line_length (0x695034, slot 0x8c) writes LCD_LINE')
    d = open(DEMO, 'rb').read(); image = bytearray(d)
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]
    pins = ((0x695ec4, 0xae020000, 'init stores its begin_frame word at lcd + 0 (sw v0, 0(s0))'),
            (0x695eb4, 0x24420000 | (O['LCD_565_BEGIN'] & 0xffff), 'the begin_frame word is LCD_565_BEGIN, 0x69 << 16 + 0x5cb0 (addiu v0, v0, 0x5cb0)'),
            (0x695eb0, 0xae1100b0, 'init stores the width at 0xb0'), (0x695eb8, 0xae1200b4, 'and the height at 0xb4'),
            (0x695db4, 0xac850110, 'lcd_mem_set_fb stores the drawing buffer at 0x110 (sw a1, 0x110(a0))'), (0x657b60, 0x8c820000, 'lcd_begin_frame reads lcd + 0 (lw v0, 0(a0))'),
            (0x66dd98, 0x2405011f, 'widget_paint passes 0x11f (EVT_BEFORE_PAINT) to paint_event_init'), (0x66de3c, 0x24050120, 'and 0x120 (EVT_AFTER_PAINT) after the children'))
    for a, w, what in pins: expect(word(a) == w, f'pinned {a:#x} = {w:#010x}: {what} (got {word(a):#010x})')

    def blur_world(m, ox=OX, oy=OY, clip='all', pitch=2 * FBW, begin=O['LCD_565_BEGIN'], w=FBW, h=FBH, null_fb=False, seed=1, fbw=None):
        """A canvas translated to the card, in front of an lcd with a drawing buffer full of noise: returns (event, buffer address, the original bytes)."""
        rnd = random.Random(seed)
        raw = bytes(rnd.randrange(256) for _ in range(pitch * FBH))
        fb = m.alloc(len(raw) + 8); fb = (fb + 3) & ~3
        m.u.mem_write(fb, raw)
        lcd = m.alloc(0x160); m.u.mem_write(lcd, bytes(0x160))
        for off, v in ((O['LCD_BEGIN'], begin), (O['LCD_W'], w), (O['LCD_H'], h), (O['LCD_FB'], 0 if null_fb else fb), (O['LCD_LINE'], pitch)): m.setword(lcd + off, v)
        cv = m.alloc(0x40); m.u.mem_write(cv, bytes(0x40))
        l, t, r, b = clip if isinstance(clip, tuple) else {'all': (0, 0, FBW - 1, FBH - 1), 'pill': (ox, oy, ox + MW - 1, oy + MH - 1), 'half': (ox, oy, ox + MW // 2, oy + MH - 1),
                      'short': (ox, oy, ox + MW - 1, oy + MH - 2)}[clip]
        for off, v in ((O['CANVAS_OX'], ox), (O['CANVAS_OY'], oy), (O['CANVAS_CLIP'], l), (O['CANVAS_CLIP'] + 4, t), (O['CANVAS_CLIP'] + 8, r), (O['CANVAS_CLIP'] + 12, b), (O['CANVAS_LCD'], lcd)):
            m.setword(cv + off, v)
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], cv)
        return e, fb, raw

    def shown_bar(**kw):
        m = BM(**kw); m.placeholder(); m.status = 2; m.track(); m.cover(); m.start(); m.first()
        return m
    def paint_before(m, e): m.count().call(PSYMS['mb_on_before_paint'], a0=0, a1=e, count=5000000); return m.icount
    def readfb(m, fb, n): return bytes(m.u.mem_read(fb, n))
    def expected(raw, pitch=2 * FBW, ox=OX, oy=OY):
        out = bytearray(raw)
        px = lambda x, y: struct.unpack_from('<H', raw, (oy + y) * pitch + (ox + x) * 2)[0]
        for (x, y), v in pod_blur.blur(px).items(): struct.pack_into('<H', out, (oy + y) * pitch + (ox + x) * 2, v)
        return bytes(out)

    m = shown_bar()
    e, fb, raw = blur_world(m)
    n = paint_before(m, e)
    got = readfb(m, fb, len(raw)); want = expected(raw)
    changed = sum(got[i] != raw[i] for i in range(len(raw)))
    expect(got == want, f'the compiled blur equals the model bit for bit over the whole {FBW}x{FBH} frame ({changed} bytes changed)')
    corner = struct.unpack_from('<H', got, (OY + 1) * 2 * FBW + (OX + 1) * 2)[0] == struct.unpack_from('<H', raw, (OY + 1) * 2 * FBW + (OX + 1) * 2)[0]
    expect(corner and got[:OY * 2 * FBW] == raw[:OY * 2 * FBW] and got[(OY + MH) * 2 * FBW:] == raw[(OY + MH) * 2 * FBW:],
           'the pill\'s rounded ends and everything outside its rectangle are untouched')
    inside_changed = sum(got[(OY + y) * 2 * FBW + (OX + x) * 2:(OY + y) * 2 * FBW + (OX + x) * 2 + 2] != raw[(OY + y) * 2 * FBW + (OX + x) * 2:(OY + y) * 2 * FBW + (OX + x) * 2 + 2]
                         for y in range(MH) for x in range(0, MW, 4))
    expect(inside_changed > 0.9 * (MH * MW // 4) * 0.85, f'the pill\'s inside is blurred ({inside_changed} of {MH * MW // 4} sampled pixels changed)')
    # smoothness: noise in, a low-pass out: the mean absolute difference of neighbouring pixels falls by a lot
    def roughness(buf):
        return sum(abs(buf[(OY + 28) * 2 * FBW + (OX + x) * 2 + 1] - buf[(OY + 28) * 2 * FBW + (OX + x + 1) * 2 + 1]) for x in range(60, 240)) / 180
    expect(roughness(got) * 4 < roughness(raw), f'the noise behind the pill is smoothed ({roughness(raw):.0f} -> {roughness(got):.0f} per pixel)')
    print(f'  minibar blur: {n} instructions for one {MW}x{MH} pill (about {n / 1.2e9 * 1e3 / 0.8:.2f} ms at 1.2 GHz, IPC 0.8)')
    expect(n < 700000, f'one full-pill blur is {n} instructions (< 700k: well under a millisecond on the 1.2 GHz core)')
    # the second frame of a still picture: the same function on already blurred pixels runs and changes nothing structural
    n2 = paint_before(m, e)
    expect(abs(n2 - n) < 2000 and 'mclGetPlayStatus' not in m.names(), 'every frame costs the same: no allocation, no stock call')
    expect(not [c for c in m.calls if c[0] in ('calloc', 'free', 'malloc')], 'and allocates nothing per frame')

    # a flat grey stays grey (rounding: without it every pass lost a little and the 5-bit red and blue fell behind the 6-bit green: a green cast)
    for level in (0x10, 0x22, 0x40, 0x80, 0xe0):
        r5, g6 = level >> 3, level >> 2
        m = shown_bar(); e, fb, raw = blur_world(m)
        flat = struct.pack('<H', r5 << 11 | g6 << 5 | r5) * (len(raw) // 2); m.u.mem_write(fb, flat); paint_before(m, e)
        p = struct.unpack_from('<H', readfb(m, fb, len(raw)), (OY + 28) * 2 * FBW + (OX + 152) * 2)[0]
        r_, g_, b_ = p >> 11, p >> 5 & 63, p & 31
        expect(abs(r_ - b_) <= 0 and abs(g_ - 2 * r_) <= 1 and abs(r_ - (r5 - (r5 >> 3))) <= 1, f'flat grey {level:#x}: still grey, a little darker ({r5},{g6},{r5}) -> ({r_},{g_},{b_})')

    # the clip is the pill exactly, or more: the same result
    m = shown_bar(); e, fb, raw = blur_world(m, clip='pill'); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == expected(raw), 'a clip that is exactly the pill\'s rectangle blurs it')

    # guards: each refusal leaves the buffer as it was; a structural one also switches the blur off for the page
    cases = [('another lcd type (not the 565 memory lcd)', dict(begin=0x695cb4), True), ('no drawing buffer', dict(null_fb=True), True),
             ('a pitch that is not a multiple of 4', dict(pitch=642), True), ('a pitch below the width', dict(pitch=600), True),
             ('an odd x origin', dict(ox=OX + 1), True), ('the pill off the right of the screen', dict(ox=40), True), ('the pill below the screen', dict(oy=FBH - 20), True),
             ('a screen narrower than the pill', dict(w=300), True), ('a screen of 5000 rows', dict(h=5000), True), ('a negative origin', dict(ox=-8), True)]
    for what, kw, structural in cases:
        m = shown_bar(); e, fb, raw = blur_world(m, **kw); paint_before(m, e)
        same = readfb(m, fb, len(raw)) == raw
        e2, fb2, raw2 = blur_world(m); paint_before(m, e2)
        expect(same, f'{what}: nothing is read or written')
        expect(readfb(m, fb2, len(raw2)) == raw2, f'{what}: and the blur stays off for the page')
    for what, clip in (('a partial repaint (the left half of the pill)', 'half'), ('a clip one row short', 'short')):
        m = shown_bar(); e, fb, raw = blur_world(m, clip=clip); paint_before(m, e)
        expect(readfb(m, fb, len(raw)) == raw, f'{what}: not blurred (the pixels outside the clip are the last frame\'s blurred ones: no seam)')
        m.tick()
        inv = [c for c in m.calls if c[0] == 'widget_invalidate_force' and c[1] == m.widgets['pod_mb_card']]
        expect(len(inv) == 1, f'{what}: the next tick invalidates the whole pill once')
        m.tick()
        expect(not [c for c in m.calls if c[0] == 'widget_invalidate_force'], f'{what}: and not again')
        e, fb, raw = blur_world(m); paint_before(m, e)
        expect(readfb(m, fb, len(raw)) == expected(raw), f'{what}: the blur is still on for the repaint of all of it')
    m = BM(); m.placeholder(); m.track(); m.start(); m.first(); m.play_pos = -1; m.tick()
    e, fb, raw = blur_world(m); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == raw, 'a hidden bar (nothing queued) blurs nothing')
    m = BM(); m.status = 2; m.track(); m.start()
    e, fb, raw = blur_world(m); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == raw, 'before the bar is first shown: nothing')
    e0 = m.alloc(0x40); m.u.mem_write(e0, bytes(0x40)); m.call(PSYMS['mb_on_before_paint'], a0=0, a1=e0, count=100000); a = m.names()
    m.call(PSYMS['mb_on_before_paint'], a0=0, a1=0, count=100000)
    expect(a == [] and m.names() == [], 'a null canvas or event is ignored')

    # a press, a release or an abort on a button, a glyph swap, new labels and a new cover invalidate the whole pill (a partial frame would not be blurred)
    m = shown_bar()
    for n_ in ('pod_mb_play', 'pod_mb_next'):
        for ev in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
            fn, ctx = m.bound[(m.widgets[n_], O[ev])]
            m.call(fn, a0=ctx, a1=0, count=100000)
            expect(m.calls == [('widget_invalidate_force', m.widgets['pod_mb_card'])], f'{n_} {ev}: the whole pill is invalidated, the event is not consumed')
    m.status = 3; m.tick()
    expect(('widget_invalidate_force', m.widgets['pod_mb_card']) in m.calls, 'a glyph swap invalidates the whole pill')
    m.track(title='Other', album='Other album', path='/mnt/mmc/z/9.flac', name='9.flac'); m.tick()
    expect(('widget_invalidate_force', m.widgets['pod_mb_card']) in m.calls, 'new labels and a new cover invalidate the whole pill')

    # a scroll frame as it happens on the device: the scroll view invalidates its own rectangle (screen coordinates: the window is 30 px down, the list at window
    # y 10..440, x 0..309 beside the 10 px scroll bar), the dirty rectangle of the frame is the bounding box of everything invalidated, and the clip the card
    # sees is that box. The window manager paints the dirty rectangle only.
    def union(*rs): return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))
    sv_rect = (0, 30 + 10, 309, 30 + 440 - 1)
    pill_at = lambda y: (OX, 30 + y, OX + MW - 1, 30 + y + MH - 1)
    expect(pill_at(O['MB_Y'])[3] == sv_rect[3] and pill_at(O['MB_Y'])[3] + 1 == 30 + O['HOME_PAD'] + 430, 'the pill ends exactly where the list does (window y 440, screen 470)')
    expect(pill_at(386)[3] > sv_rect[3], 'regression check: the old geometry (the pill at y 386) ended below the list, so the list\'s own rectangle never covered it')
    expect(pill_at(O['MB_Y'])[2] > sv_rect[2], 'and beside the 10 px scroll bar the list\'s rectangle (x 0..309) ends left of the pill (x 8..311): it never covers the pill alone')
    # without the handler (the dirty rectangle is the list's alone): a partial clip, not blurred
    m = shown_bar(); e, fb, raw = blur_world(m, clip=sv_rect); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == raw, 'a scroll frame whose dirty rectangle is the list\'s alone is a partial clip for the pill: not blurred (the old behaviour: sharp for the whole scroll)')
    # with the handler: EVT_SCROLL on the scroll view invalidates the pill, the dirty rectangle is the union, the clip covers the pill, the blur runs
    m = shown_bar(); fn, ctx = m.bound[(m.widgets['pod_scrollview'], O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=100000)
    expect(m.calls == [('widget_invalidate_force', m.widgets['pod_mb_card'])], 'EVT_SCROLL on the list invalidates the whole pill, nothing else, and does not consume the event')
    for what, sv in (('with the scroll bar beside it (x 0..309)', sv_rect), ('a list that runs the full width (x 0..319)', (0, 40, 319, 469))):
        m = shown_bar(); e, fb, raw = blur_world(m, clip=union(sv, pill_at(O['MB_Y']))); paint_before(m, e)
        expect(readfb(m, fb, len(raw)) == expected(raw), f'a scroll frame {what}: the dirty rectangle (list + pill) covers the pill, the blur runs, bit for bit')
    # the event is not sent while the bar is hidden or the blur is off
    m = BM(); m.placeholder(); m.track(); m.start(); m.first(); m.play_pos = -1; m.tick(); fn, ctx = m.bound[(m.widgets['pod_scrollview'], O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=100000)
    expect(m.calls == [], 'a scroll with the bar hidden does nothing')
    # a press on the visible part of a row that is partly under the pill: the list gets the pointer events first and invalidates the pill with the row
    m = shown_bar()
    for ev in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        fn, ctx = m.bound[(m.widgets['pod_scrollview'], O[ev])]; m.call(fn, a0=ctx, a1=0, count=100000)
        expect(m.calls == [('widget_invalidate_force', m.widgets['pod_mb_card'])], f'{ev} on the list invalidates the whole pill (the row\'s highlight rectangle then merges with it)')
    # the row under the pill: its highlight (310 wide, window y 374..426 for Settings) lies inside the pill's rows and its left part beyond the pill
    row = (0, 30 + 374, 309, 30 + 425)
    m = shown_bar(); e, fb, raw = blur_world(m, clip=union(row, pill_at(O['MB_Y']))); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == expected(raw), 'a row press frame (row rectangle + pill): blurred, not a sharp flash')

    # the setup: the plane is allocated once and freed with the page; every way it cannot be there leaves the glass over the sharp rows
    m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover(); m.start()
    plane = [c for c in m.calls if c[0] == 'calloc']
    expect(len(plane) == 1 and plane[0][1] == 4 * O['MB_HW'] * O['MB_HH'] and plane[0][2], f'the half-resolution plane is allocated once at start ({plane})')
    m.first(); bmp = next(iter(m.bitmaps)); m.call(PSYMS['mb_on_destroy'], a0=WIN, a1=0)
    expect(('free', plane[0][2]) in m.calls and ('bitmap_destroy', bmp) in m.calls, 'and freed with the page, with the cover bitmap')
    m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover(); m.present.add('/mnt/mmc/m1plus-noblur'); m.start(); m.first()
    expect(not [c for c in m.calls if c[0] == 'calloc'] and m.shown('pod_minibar'), 'the SD file m1plus-noblur: no plane, no blur, the bar as before')
    e, fb, raw = blur_world(m); paint_before(m, e)
    expect(readfb(m, fb, len(raw)) == raw and not [c for c in m.calls if c[0] == 'widget_invalidate_force'], 'and a before-paint (should it come) changes nothing')
    m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover(); m.calloc_fail = True; m.start(); m.first()
    expect(m.shown('pod_minibar') and not [c for c in m.calls if c[0] == 'widget_on' and c[2] == O['EVT_BEFORE_PAINT']], 'no memory for the plane: no blur, the bar works')
    for ev in ('EVT_BEFORE_PAINT', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        m = BM(); m.placeholder(); m.status = 2; m.track(); m.cover(); m.on_fail = {O[ev]}; m.start(); m.first()
        e, fb, raw = blur_world(m); paint_before(m, e)
        expect(readfb(m, fb, len(raw)) == raw and m.shown('pod_minibar'), f'{ev} refused: the bar works, the pixels are untouched')

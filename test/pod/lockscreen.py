"""The lock screen's mini player layout (patch/lockscreen.c, docs/modules/lockscreen.md): the hook on screensaver_page_init and the layout it gives the stock card's widgets.

The hook runs the real compiled payload under the harness machine with the stock init mocked at its resume point. The layout is compared with the shared model (tools/mod_lockscreen.py
MINI_RECT, read from patch/offsets.inc), the stock page code's references are scanned for anything that would move the widgets again, and the touch targets are hit-tested by demo's own
widget_find_target on the built page tree with the geometry the payload's calls left."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

import mod_lockscreen as ML
import awtk_ui
import mod_icons
import pod_blur

BM = sibling('minibar').BM   # noqa: F405  (the Home bar's machine: the stock player, the cover files and the /tmp picture mocks)
MB = sibling('minibar')   # noqa: F405

INIT = pod.LOCKSCREEN_INIT
WIN = 0x24000000
KILL = '/mnt/mmc/m1plus-off'
FILE = '/mnt/data/m1plus/lockscreen-layout'
NAMES = ('view_bottomview', 'view_img_icon', 'view_scrlabel_title', 'view_scrlabel_artist', 'btn_play', 'btn_next')
STATES3 = ('normal', 'disable', 'focused')
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/screensaver_page.bin') if WORK else None


class LK(BM):
    """The Home bar's machine plus the lock page's six card widgets; the stock init is mocked (init_ret)."""
    def __init__(self, setting=b'1', names=NAMES):
        super().__init__(bar=False, sb=False)
        self.handlers[INIT + 12] = 'stock_lockscreen_resume'
        self.init_ret = 0
        self.w = {n: self.widget(n) for n in names}
        if setting is not None: self.fs[FILE] = setting
        self.log = []

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'stock_lockscreen_resume':
            self.calls.append(('stock_lockscreen_resume', u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)))
            u.reg_write(UC_MIPS_REG_V0, self.init_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        return super()._hook(u, address, size, _)

    def open(self, win=WIN):
        r = self.call(PSYMS['m1plus_lockscreen_init'], a0=win, a1=0, count=2000000)
        self.log += self.calls
        return r

    def geometry(self):
        """name -> (x, y, w, h) the payload's widget_move / widget_resize calls left (None for a coordinate never set)."""
        return {n: tuple(self.props.get((h, k)) for k in 'xywh') for n, h in self.w.items()}

    def nc(self, name): return sum(1 for c in self.log if c[0] == name)

    def first(self): return self.call(PSYMS['lk_first'], count=40000000)
    def tick(self): return self.call(PSYMS['lk_tick'], count=40000000)

    def handler(self, widget, evt, e=0):
        fn, ctx = self.bound[(widget, O[evt] if isinstance(evt, str) else evt)]
        return self.call(fn, a0=ctx, a1=e, count=40000000)

    def card(self): return self.w['view_bottomview']

    def event(self, canvas=0x22220000):
        e = self.alloc(0x40); self.u.mem_write(e, bytes(0x40)); self.setword(e + O['EVENT_PAINT_CANVAS'], canvas)
        return e

    def paint(self):
        self.blits = []
        if (self.card(), O['EVT_AFTER_PAINT']) in self.bound: self.handler(self.card(), 'EVT_AFTER_PAINT', self.event())
        return self.blits

    def sweep(self, *thunks):
        """Run each thunk (every call resets calls): the calls of all of them, and the blits."""
        out, blits = [], []
        for t in thunks:
            t(); out += self.calls; blits += self.blits
        self.calls = out
        return out

    def icons(self):
        return tuple(self.props.get((self.w['btn_play'], f'style:{st}:icon')) for st in ('normal', 'over', 'pressed'))

    def lit_track(self, status=2, cover=True, **kw):
        """A track playing (status 2) or paused (3) with the Home bar's test cover; the lock page opened and its one-shot fired."""
        self.placeholder(); self.status = status; self.track(**kw)
        if cover: self.cover()
        self.open(); self.first()
        return self


def page_tree(m):
    """The built page (the large layout) as the window manager sees it, 320 x 480, with the geometry the payload's calls left."""
    root = asset_tree(UI)
    root.h = 480
    for n, g in m.geometry().items():
        nd = node(root, n)
        if all(v is not None for v in g): nd.x, nd.y, nd.w, nd.h = g
        else: nd.x, nd.y, nd.w, nd.h = (v if v is not None else d for v, d in zip(g, (nd.x, nd.y, nd.w, nd.h)))
    return root


def target(m, root, x, y): return stock_target(m, root, x, y)[-1]


def hook_tests(ctx):
    expect = ctx.expect
    import paths
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]

    # -- 0. the hook, its pins
    expect(INIT == 0x53fd44 and pod.LOCKSCREEN_INIT_PROLOGUE == (0x3c1c004c, 0x279c418c, 0x0399e021)
           and tuple(word(stock, INIT + 4 * i) for i in range(3)) == pod.LOCKSCREEN_INIT_PROLOGUE, 'stock has the three PIC prologue words the hook pins (screensaver_page_init)')
    expect((0x4c << 16) + 0x418c + INIT == pod.GP, 'the prologue computes $gp = 0xa03ed0 from t9 = the entry')
    expect(tuple(word(built, INIT + 4 * i) for i in range(4)) == (pod.j(PSYMS['m1plus_lockscreen_init']), 0, pod.LOCKSCREEN_INIT_PROLOGUE[2], 0x10800054),
           'the build has `j m1plus_lockscreen_init; nop` over the first two prologue words; the trampoline resumes at stock\'s beqz a0')
    tramp = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS['stock_lockscreen_init_trampoline'] - pod.BASE)
    expect(tramp == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(INIT + 12), 0), 'the trampoline restores $gp and resumes at the 4th instruction')
    expect(MANIFEST['hook_lockscreen'] == {'addr': INIT, 'target': PSYMS['m1plus_lockscreen_init']}, 'the manifest records the hook')
    expect(pod.LOCKSCREEN_PINS[0][0] == INIT + 12 and all(word(stock, a) == old and word(built, a) == old for a, old, _ in pod.LOCKSCREEN_PINS), 'the resume word and the lock switch words (stock\'s handler 0x4aba34, config_init, into_standby) are stock\'s, in demo and in the build')
    expect(pod.DATA['LOCK_ON'] == (0xa05aa3, 'screensaver_mode') and [hex(a) for a, _, _ in pod.LOCKSCREEN_PINS[1:11]] == ['0x4abaa4', '0x4abaa8', '0x4ababc', '0x4abb24', '0x4abaf0', '0x4abaf8', '0x4abaf4', '0x4e615c', '0x4e779c', '0x4e77a0'],
           'the lock switch pins: the byte screensaver_mode, the handler\'s set / clear / save words, the boot load and the two readers')
    expect('lockscreen.c' in pod.SOURCES and all(not INIT - 12 < h < INIT + 12 for h in (pod.BIGCOVER_INIT, pod.PLAYING_INIT, pod.PLAYMORE_INIT, pod.HOME_INIT)), 'in the payload sources, a hook of its own')
    expect(stock[pod.fileoff(stock, 0x75218c):][:16] == b'view_bottomview\0', 'the card\'s name')

    # -- 1. stock first, its result returned; the order and the arguments
    gp = []
    m = LK(); m.u.hook_add(UC_HOOK_CODE, lambda u, a, s, _: gp.append(u.reg_read(UC_MIPS_REG_GP)), begin=INIT + 12, end=INIT + 12)
    r = m.open()
    expect(gp == [pod.GP] and r == 0 and m.calls[0] == ('stock_lockscreen_resume', WIN, 0), f'the trampoline restores $gp, the stock init runs first with its arguments ({[hex(g) for g in gp]})')
    expect(m.nc('widget_move') == 6 and m.nc('widget_resize') == 6 and m.timers == [(PSYMS['lk_first'], O['MB_FIRST_MS'])], 'setting 1: six widgets moved and resized, one short one-shot (the bar\'s page timer) armed')
    expect(not [c for c in m.calls if c[0] in ('mkdir', 'rename', 'bitmap_create_ex', 'widget_load_image')] and not any(c[0] == 'widget_set_visible' and c[1] != m.w['view_img_icon'] for c in m.calls), 'and nothing decoded or allocated at init, nothing shown or hidden but stock\'s cover')
    m = LK(); m.init_ret = 0x10; r = m.open()
    expect(r == 0x10 and m.nc('widget_move') == 0 and not [c for c in m.calls if c[0] in ('widget_lookup', 'access')], 'a stock init that fails: its result is returned, nothing looked at, nothing moved')
    m = LK(); r = m.open(win=0)
    expect(r == 0 and m.nc('widget_move') == 0 and not [c for c in m.calls if c[0] == 'widget_lookup'], 'a null window: the stock result, nothing moved')
    m = LK(); m.present.add(KILL); r = m.open()
    expect(r == 0 and m.nc('widget_move') == 0 and not [c for c in m.calls if c[0] == 'widget_lookup'] and ('access', KILL) in m.calls, 'the kill switch: the stock init only, the large card')

    # -- 2. the setting: only "1" (alone, or with a line feed) is the mini player; read, never written
    for data, mini in ((b'1', 1), (b'1\n', 1), (None, 0), (b'0', 0), (b'0\n', 0), (b'', 0), (b'2', 0), (b'11', 0), (b'1x', 0), (b'1\n\n', 0), (b'x1', 0), (b' 1', 0)):
        m = LK(setting=data); r = m.open()
        expect(r == 0 and m.nc('widget_move') == 6 * mini and m.nc('widget_resize') == 6 * mini, f'the setting {data!r}: {"mini player" if mini else "the large card"}')
        wr = [c for c in m.log if c[0] in ('rename', 'unlink', 'write', 'fsync', 'mkdir') or (c[0] == 'open' and c[2] & 3)]
        expect(not wr and m.fs.get(FILE) == data or (data is None and FILE not in m.fs), f'the setting {data!r} is only read ({wr})')

    # -- 3. a missing widget leaves the page as the asset has it (every lookup first)
    for gone in NAMES:
        m = LK(names=tuple(n for n in NAMES if n != gone)); r = m.open()
        expect(r == 0 and m.nc('widget_move') == 0 and m.nc('widget_resize') == 0 and not any(k[1].startswith('style:') for k in m.props if isinstance(k[1], str)) and not m.styles,
               f'without {gone}: the stock result, no geometry, no style changed')


def layout_tests(ctx):
    expect = ctx.expect

    # -- 4. the layout is the shared model's (tools/mod_lockscreen.py MINI_RECT: patch/offsets.inc LK_*, MB_*)
    m = LK(); m.open()
    geo = m.geometry()
    expect(geo == ML.MINI_RECT, f'the widgets take the model\'s rectangles ({geo})')
    expect(ML.MINI_RECT['view_bottomview'] == (8, 386, 304, 56) and ML.MINI_RECT['view_img_icon'] == (14, 10, 36, 36) and ML.MINI_RECT['view_scrlabel_title'] == (60, 7, 130, 22)
           and ML.MINI_RECT['view_scrlabel_artist'] == (60, 29, 130, 20) and ML.MINI_RECT['btn_play'] == (194, 0, 48, 56) and ML.MINI_RECT['btn_next'] == (245, 0, 48, 56), 'the numbers are the Home bar\'s, the card at (8, 386)')
    cx, cy, cw, ch = ML.MINI_RECT['view_bottomview']
    expect(cx >= 0 and cy >= 0 and cx + cw <= 320 and cy + ch <= 480, 'the card is inside the 320 x 480 page')
    for n in NAMES[1:]:
        x, y, w, h = ML.MINI_RECT[n]
        expect(x >= 0 and y >= 0 and x + w <= cw and y + h <= ch, f'{n} is inside the card')
    root = awtk_ui.parse(open(UI, 'rb').read())
    slide = root.find('img_slide')
    expect(cy + ch + 10 <= slide.y and cy + ch <= 452, f'the card ends {slide.y - cy - ch} px over the swipe hint (y {slide.y})')
    expect(m.props[(m.w['view_bottomview'], 'style:normal:bg_image')] == 'mb_glass' and all(m.props[(m.w['view_bottomview'], f'style:{s}:bg_image')] == 'mb_glass' for s in STATES3),
           'the card\'s background image is the Home bar\'s glass in the three states the asset sets')
    expect({k for a, k, v in m.styles if a == m.w['view_scrlabel_title']} == {f'{s}:font_size' for s in STATES3}
           and {v for a, k, v in m.styles if a == m.w['view_scrlabel_title']} == {17} and {v for a, k, v in m.styles if a == m.w['view_scrlabel_artist']} == {16}
           and {k for a, k, v in m.styles if a == m.w['view_scrlabel_artist']} == {f'{s}:font_size' for s in STATES3}, 'title 17 px and artist 16 px in the three states')
    expect(all(m.props[(m.w['view_scrlabel_artist'], f'style:{s}:text_color')] == '#D0D0D0' for s in STATES3) and not any(k[0] == m.w['view_scrlabel_title'] and 'text_color' in str(k[1]) for k in m.props),
           'the artist is #D0D0D0, the title keeps the asset\'s white')
    expect(len(m.styles) == 6 and {a for a, _, _ in m.styles} == {m.w['view_scrlabel_title'], m.w['view_scrlabel_artist']}, 'no other widget\'s style is touched')
    expect(not any(c[0] in ('widget_set_sensitive', 'widget_set_enable', 'widget_use_style', 'widget_set_text_utf8') for c in m.log) and [c for c in m.log if c[0] == 'widget_set_visible'] == [('widget_set_visible', m.w['view_img_icon'], 0)],
           'sensitivity, the page styles and the texts are stock\'s: untouched; only stock\'s own cover is hidden (ours is drawn instead)')
    expect({k[0] for k in m.props if k[1] in ('visible', 'sensitive', 'enable') and k[0] in m.w.values()} == {m.w['view_img_icon']}, 'nothing else was hidden or shown')

    # -- 5. the Python model matches the asset's widgets (the mini tree passes the touch checks the large one does)
    tree = awtk_ui.parse(open(UI, 'rb').read())
    cover = ML.apply_mini(tree)
    expect(cover == (22, 396, 36, 36), f'the model\'s cover rectangle in the window ({cover})')

    # -- 6. touch: the real hit testing on the page tree with the geometry left by the payload
    root = page_tree(m)
    play, nxt = ML.MINI_RECT['btn_play'], ML.MINI_RECT['btn_next']
    pc = (cx + play[0] + play[2] // 2, cy + play[1] + play[3] // 2)
    nc = (cx + nxt[0] + nxt[2] // 2, cy + nxt[1] + nxt[3] // 2)
    expect(target(m, root, *pc) == 'btn_play' and target(m, root, *nc) == 'btn_next', 'the centres of play and next hit the buttons through demo\'s own widget_find_target')
    for dx, dy in ((-20, -20), (20, -20), (-20, 20), (20, 20), (0, -26), (0, 26)):
        t1, t2 = target(m, root, pc[0] + dx, pc[1] + dy), target(m, root, nc[0] + dx, nc[1] + dy)
        expect(t1 in ('btn_play', 'view_bottomview', 'app_gesture') and t2 in ('btn_next', 'view_bottomview', 'app_gesture'), f'offsets ({dx},{dy}) hit a button or the card, never a stray widget ({t1}, {t2})')
    expect(target(m, root, *(pc[0] - 2, pc[1])) == 'btn_play' and target(m, root, pc[0] + 22, pc[1]) == 'btn_play', 'play is hit across its 48 px width')
    expect(target(m, root, cx + play[0] + 47, pc[1]) == 'btn_play' and target(m, root, cx + nxt[0], pc[1]) == 'btn_next', 'the buttons meet without a gap')
    for x, y in ((cover[0] + 18, cover[1] + 18), (cover[0] + 2, cover[1] + 2), (cover[0] + 33, cover[1] + 33), (cx + 192, cy + 28), (cx + 4, cy + 4), (cx + 100, cy + 28), (cx + 100, cy + 40)):
        t = stock_target(m, root, x, y)
        expect('app_gesture' in t and 'view_bottomview' in t and t[-1] not in ('btn_play', 'btn_next'), f'a touch on the cover, text or card at ({x},{y}) is not a button, inside app_gesture: a swipe unlocks ({t})')
    for x, y in ((cx - 2, cy + 28), (cx + cw + 1, cy + 28), (cx + 100, cy - 2), (cx + 100, cy + ch + 1), (160, 240), (160, 120), (160, 470)):
        t = stock_target(m, root, x, y)
        expect('view_bottomview' not in t and 'app_gesture' in t, f'a touch outside the card at ({x},{y}) stays in the swipe gesture ({t})')
    # the large layout, for contrast: the card at the stock-built place is untouched by a setting of 0
    m0 = LK(setting=b'0'); m0.open()
    root0 = page_tree(m0)
    big = node(root0, 'view_bottomview')
    expect((big.x, big.y, big.w, big.h) == (16, 108, 288, 334) and (node(root0, 'view_img_icon').w, node(root0, 'btn_play').x) == (264, 180), 'the large layout stays as the asset built it (card 288 x 334 at 16, 108; 264 px cover)')
    expect(target(m0, root0, 160, 250) == 'view_bottomview' and target(m0, root0, 16 + 180 + 24, 108 + 278 + 28) == 'btn_play', 'and its touch targets are unchanged')


def life_tests(ctx):
    expect = ctx.expect
    import paths
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    w = lambda a: struct.unpack_from('<I', stock, pod.fileoff(stock, a))[0]

    # -- 7. nothing of stock's page code moves a widget again: the refresh, the 20 ms timer, the swipe and the button handlers (0x53f1a0..0x53feac) reach no geometry or style call,
    #       so the mini layout survives every refresh round, a track change and a play / pause (which only swaps the button's own style)
    got = {}
    for a in range(0x53f1a0, 0x53feac, 4):
        x = w(a)
        if x >> 26 == 0x23 and (x >> 21) & 31 == 28:   # lw rt, off($gp)
            off = x & 0xffff; off -= 0x10000 if off & 0x8000 else 0
            try: got.setdefault(w(pod.GP + off), []).append(a)
            except Exception: pass   # noqa: BLE001 - a GOT-looking load of something not mapped
    names = {pod.FUNCTIONS[n][2]: n for n in ('widget_move', 'widget_resize', 'widget_set_prop_str', 'widget_set_prop_int', 'widget_set_style', 'widget_use_style', 'widget_set_visible')}
    names.update({0x66d268: 'widget_move_resize_ex', 0x66d408: 'widget_move_resize', 0x656e74: 'widget_set_self_layout', 0x656d5c: 'widget_layout', 0x656c2c: 'widget_layout_self', 0x66e934: 'widget_set_prop'})
    hit = {names[v]: len(a) for v, a in got.items() if v in names}
    expect(not {'widget_move', 'widget_resize', 'widget_move_resize_ex', 'widget_move_resize', 'widget_set_self_layout', 'widget_layout', 'widget_layout_self', 'widget_set_style', 'widget_set_prop_str', 'widget_set_prop_int'} & set(hit),
           f'stock\'s lock screen code never moves, resizes or restyles a widget except through widget_use_style on the play button and two widget_set_prop of its timer id ({hit})')
    expect(hit.get('widget_use_style') == 1 and hit.get('widget_set_prop') == 2, f'the one use_style (the play / pause button, 0x53f874) and the two set_prop (the timer id) ({hit})')
    expect(set(got) >= {0x66aa64, 0x66c394, 0x669320}, 'the scan sees the refresh\'s use_style, set_visible and set_enable (the card\'s hiding while nothing is queued)')

    # -- 8. hidden card: the hook neither shows nor enables it, and the stock hiding keeps working on the same widget
    m = LK()
    m.props[(m.w['view_bottomview'], 'visible')] = 0; m.props[(m.w['view_bottomview'], 'sensitive')] = 0
    m.open()
    expect(m.props[(m.w['view_bottomview'], 'visible')] == 0 and m.props[(m.w['view_bottomview'], 'sensitive')] == 0 and all(c[1] == m.w['view_img_icon'] for c in m.log if c[0] == 'widget_set_visible'),
           'a card stock hid (nothing queued) stays hidden and insensitive after the layout')
    root = asset_tree(UI); root.h = 480
    card = node(root, 'view_bottomview'); card.flags &= ~(F_ENABLE | F_SENSITIVE)
    for n, g in m.geometry().items():
        nd = node(root, n); nd.x, nd.y, nd.w, nd.h = g
    cx, cy, cw, ch = ML.MINI_RECT['view_bottomview']
    for x, y in ((cx + 220, cy + 28), (cx + 270, cy + 28), (cx + 100, cy + 28), (cx + 30, cy + 28)):
        t = stock_target(m, root, x, y)
        expect('view_bottomview' not in t and 'app_gesture' in t, f'with the card disabled a touch at ({x},{y}) falls through to the whole-screen swipe ({t})')

    # -- 9. repeated page opens (the page is rebuilt each time): the same result, and a setting changed in between applies at the next init
    m = LK(); m.open(); first = m.geometry(); m.open(win=WIN + 0x1000)
    expect(m.geometry() == first and m.nc('widget_move') == 12, 'a second open gives the same geometry')
    m.fs[FILE] = b'0'; m.log = []; m.open()
    expect(m.nc('widget_move') == 0, 'with the setting back to 0 the next open leaves the large card alone (no write, no watcher)')
    m.fs[FILE] = b'1\n'; m.log = []; m.open()
    expect(m.nc('widget_move') == 6, 'and 1 applies again at the next open')

FBW, FBH = 320, 480
OX, OY = O['LK_MINI_X'], O['LK_MINI_Y']
MW, MH = O['MB_W'], O['MB_H']
FIRST, TICK = PSYMS['lk_first'], PSYMS['lk_tick']


def blur_world(m, clip='all', seed=1, begin=None):
    """A canvas translated to the card (the lock page's: the card at (8, 386) of the 320 x 480 window) in front of an lcd whose drawing buffer is noise: (event, buffer, original bytes)."""
    import random
    rnd = random.Random(seed)
    raw = bytes(rnd.randrange(256) for _ in range(2 * FBW * FBH))
    fb = (m.alloc(len(raw) + 8) + 3) & ~3
    m.u.mem_write(fb, raw)
    lcd = m.alloc(0x160); m.u.mem_write(lcd, bytes(0x160))
    for off, v in ((O['LCD_BEGIN'], O['LCD_565_BEGIN'] if begin is None else begin), (O['LCD_W'], FBW), (O['LCD_H'], FBH), (O['LCD_FB'], fb), (O['LCD_LINE'], 2 * FBW)): m.setword(lcd + off, v)
    cv = m.alloc(0x40); m.u.mem_write(cv, bytes(0x40))
    box = {'all': (0, 0, FBW - 1, FBH - 1), 'pill': (OX, OY, OX + MW - 1, OY + MH - 1), 'short': (OX, OY, OX + MW - 1, OY + MH - 2)}[clip]
    for off, v in ((O['CANVAS_OX'], OX), (O['CANVAS_OY'], OY), (O['CANVAS_CLIP'], box[0]), (O['CANVAS_CLIP'] + 4, box[1]), (O['CANVAS_CLIP'] + 8, box[2]), (O['CANVAS_CLIP'] + 12, box[3]), (O['CANVAS_LCD'], lcd)):
        m.setword(cv + off, v)
    return m.event(cv), fb, raw


def blur_expected(raw):
    out = bytearray(raw)
    px = lambda x, y: struct.unpack_from('<H', raw, (OY + y) * 2 * FBW + (OX + x) * 2)[0]
    for (x, y), v in pod_blur.blur(px).items(): struct.pack_into('<H', out, (OY + y) * 2 * FBW + (OX + x) * 2, v)
    return bytes(out)


def bar_tests(ctx):
    """The mini layout's bar is the Home bar's: its cover (patch/minibar.c mb_art_*), glyphs and backdrop blur (mb_blur_*), driven by one page-scoped timer (patch/lockscreen.c lk_*)."""
    expect = ctx.expect
    PLAYING, PAUSED = O['MB_PLAYING'], 3
    expect(PSYMS['lk_first'] and PSYMS['lk_tick'] and 0 < O['MB_FIRST_MS'] <= 250, 'the page timer: a short one-shot, then the tick')

    # -- 10. start: what is registered, what is taken over; nothing is decoded at init
    m = LK(); m.open()
    card, play, nxt, icon, title, artist = (m.w[n] for n in ('view_bottomview', 'btn_play', 'btn_next', 'view_img_icon', 'view_scrlabel_title', 'view_scrlabel_artist'))
    ons = {(c[1], c[2], c[3]) for c in m.log if c[0] == 'widget_on'}
    want = {(WIN, O['EVT_DESTROY'], PSYMS['lk_on_destroy']), (WIN, O['EVT_WINDOW_TO_BG'], PSYMS['lk_on_background']), (WIN, O['EVT_WINDOW_TO_FG'], PSYMS['lk_on_foreground']),
            (card, O['EVT_AFTER_PAINT'], PSYMS['lk_on_paint']), (card, O['EVT_BEFORE_PAINT'], PSYMS['lk_on_before_paint'])}
    want |= {(w, O[e], PSYMS['lk_on_touch']) for w in (play, nxt) for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT')}
    expect(ons == want, f'the handlers: destroy / background / foreground on the window, the cover and the blur on the card, the press events on play and next ({ons ^ want})')
    plane = [c for c in m.log if c[0] == 'calloc']
    expect(len(plane) == 1 and plane[0][1] == 4 * O['MB_HW'] * O['MB_HH'], 'the blur plane is the one allocation, made once')
    expect(m.props[(icon, 'visible')] == 0 and not m.props.get((icon, 'sensitive'), 0), 'stock\'s cover widget is hidden (and stays insensitive)')
    expect(all(m.props[(w, k)] == 1 for w in (title, artist) for k in ('ellipses', 'only_parent_focus')), 'title and artist are the Home bar\'s one-line ellipsis labels (never scrolling)')
    expect(all(m.props[(nxt, f'style:{st}:bg_image')] == '' for st in ('normal', 'disable', 'focused', 'over', 'pressed')) and
           (m.props[(nxt, 'style:normal:icon')], m.props[(nxt, 'style:over:icon')], m.props[(nxt, 'style:pressed:icon')]) == ('mb_next', 'mb_next', 'mb_next_down'), 'next shows the Home bar\'s glyph (the page\'s np_next background cleared)')

    # -- 11. the cover: the same pixels as the Home bar's, from the album's cache file and from demo's /tmp picture, the placeholder when there is none
    for label, kw in (('the album cache file', {}), ('the /tmp picture of a track without a cache file', dict(album=''))):
        h = BM(); h.placeholder(); h.status = PLAYING; h.track(**kw)
        m = LK(); m.placeholder(); m.status = PLAYING; m.track(**kw)
        for x in (h, m):
            if kw: x.tmp_cover()
            else: x.cover()
        h.start(); h.first(); m.open(); m.first()
        hp, lp = h.pixels(), m.pixels()
        expect(hp[1:3] == (O['MB_ART'], O['MB_ART']) and lp[1:3] == (O['MB_ART'], O['MB_ART']) and lp[3] == hp[3], f'{label}: the lock bar\'s 36 px bitmap equals the Home bar\'s, pixel for pixel (rounded corners included)')
    cov = MB.corner_coverage(O['MB_ART_R'])
    px = struct.unpack_from('<I', lp[3], 0)[0]
    expect(px >> 24 == 255 - cov[0] and struct.unpack_from('<I', lp[3], 4 * (O['MB_ART'] // 2 * O['MB_ART'] + O['MB_ART'] // 2))[0] >> 24 == 255, 'the four corners are rounded in the bitmap\'s alpha, the middle is opaque')
    blits = m.paint()
    expect(len(blits) == 1 and blits[0][2] == (O['MB_ART_X'], O['MB_ART_Y'], O['MB_ART'], O['MB_ART']) and blits[0][1] == (0, 0, O['MB_ART'], O['MB_ART']), f'the card\'s after-paint draws the resident bitmap at the Home bar\'s place ({blits})')
    m = LK(); m.placeholder(); m.status = PLAYING; m.track(album=''); m.open(); m.first()
    h = BM(); h.placeholder(); h.status = PLAYING; h.track(album=''); h.start(); h.first()
    expect(m.pixels()[3] == h.pixels()[3] and ('widget_load_image', 'p_default') in m.calls, 'no art: the placeholder disc, as the Home bar has it')
    m = LK(); m.placeholder(); m.status = PLAYING; m.play_pos = -1; m.open(); m.first(); m.tick()
    expect(not m.bitmaps and not m.paint() and not [c for c in m.calls if c[0] == 'widget_load_image'], 'nothing queued (stock hides the card): no bitmap, nothing decoded, nothing drawn')
    # a track change redoes the cover; the same track does not
    m = LK().lit_track(); b0 = m.pixels()[3]
    m.calls = []; m.tick()
    expect(not [c for c in m.calls if c[0] == 'widget_load_image'], 'a tick on the same track decodes nothing')
    m.cover(artist='B', album='Other', rgb=(10, 200, 10)); m.track(artist='B', album='Other', title='Next', path='/mnt/mmc/b/2.flac', name='2.flac'); m.tick()
    b1 = m.pixels()[3]
    expect(b1 != b0 and [c for c in m.calls if c[0] == 'widget_load_image'] and any(c[0] == 'widget_invalidate_force' and c[1] == m.card() for c in m.calls), 'a new track: the cover is made again and the whole card repainted')
    # demo writes the /tmp picture a little after the track changes: the settle ticks read it again
    m = LK(); m.placeholder(); m.status = PLAYING; m.track(album=''); m.tmp_cover(data=b'a' * 100, rgb=(1, 2, 3)); m.open(); m.first()
    c0 = m.pixels()[3]
    m.tmp_cover(data=b'b' * 100, rgb=(200, 100, 50)); m.tick()
    expect(m.pixels()[3] != c0, 'the /tmp picture that arrives after the track changed is picked up by the settle ticks')

    # -- 12. the glyphs: Home's, right after every status change and every stock swap (stock calls widget_use_style only when the status changes)
    PAUSE, PLAY = ('mb_pause', 'mb_pause', 'mb_pause_down'), ('mb_play', 'mb_play', 'mb_play_down')
    m = LK().lit_track(status=PLAYING); P = m.w['btn_play']
    expect(m.icons() == PAUSE, 'playing: the Home bar\'s pause glyph')
    m.status = PAUSED; m.calls = []; m.tick()
    expect(m.icons() == PLAY and any(c[0] == 'widget_invalidate_force' and c[1] == m.card() for c in m.calls), 'paused: the play glyph, the whole card repainted')
    m.calls = []; m.tick()
    expect(m.icons() == PLAY and not [c for c in m.calls if c[0] == 'widget_set_prop_str' or c[0] == 'widget_invalidate_force'], 'an unchanged status changes nothing')
    for want_name, status, glyph in (('btn_imgpause1_style', PLAYING, PAUSE), ('btn_imgplay1_style', PAUSED, PLAY), ('btn_imgpause1_style', PLAYING, PAUSE)):
        m.status = status; m.setword(P + O['WIDGET_STYLE'], m.cstr(want_name)); m.tick()    # stock: widget_use_style(btn_play, want_name) (0x53f874)
        expect(m.icons() == glyph, f'after stock\'s swap to {want_name} the glyph is {glyph[0]}')
    # a swap that put the page's large glyph back after our tick (an AWTK that resets the widget's own overrides): the style name changed, so the glyph is made again with no status change
    for st in ('normal', 'over', 'pressed'): m.props[(P, f'style:{st}:icon')] = 'np_pause'
    m.setword(P + O['WIDGET_STYLE'], m.cstr('btn_imgplay1_style')); m.tick()
    expect(m.icons() == PAUSE, 'a stock swap that cleared our glyph is repaired on the next tick')
    expect(not any(c[0] == 'widget_use_style' for c in m.log + m.calls), 'we never swap the page style ourselves: stock\'s own name logic keeps seeing its own names')
    # a tap: the stock handlers stay (we add no click handler); the press events only repaint the whole card
    m.calls = []; m.handler(P, 'EVT_POINTER_DOWN')
    expect(any(c[0] == 'widget_invalidate_force' and c[1] == m.card() for c in m.calls) and not any(c[0] in ('playpause_quick_click', 'next_quick_click') for c in m.calls), 'a press invalidates the card and does nothing else')
    expect((P, O['EVT_CLICK']) not in m.bound and (m.w['btn_next'], O['EVT_CLICK']) not in m.bound and (m.card(), O['EVT_CLICK']) not in m.bound, 'no click handler of ours: stock\'s play, next and swipe work as before')
    # stock showing its cover again is undone
    m.props[(m.w['view_img_icon'], 'visible')] = 1; m.tick()
    expect(m.props[(m.w['view_img_icon'], 'visible')] == 0, 'stock\'s cover widget is hidden again if stock shows it')

    # -- 13. the backdrop blur: bit for bit the Home bar's model, the same guards and escape hatch
    m = LK().lit_track(); e, fb, raw = blur_world(m)
    m.count().handler(m.card(), 'EVT_BEFORE_PAINT', e)
    got = bytes(m.u.mem_read(fb, len(raw)))
    expect(got == blur_expected(raw) and got != raw, 'the compiled blur of the lock card equals tools/pod_blur.py bit for bit (the same routine as the Home bar)')
    expect(m.icount < 700000 and not [c for c in m.calls if c[0] in ('calloc', 'free', 'malloc')], f'{m.icount} instructions, nothing allocated per frame')
    m = LK().lit_track(); e, fb, raw = blur_world(m, clip='pill'); m.handler(m.card(), 'EVT_BEFORE_PAINT', e)
    expect(bytes(m.u.mem_read(fb, len(raw))) == blur_expected(raw), 'a clip that is exactly the pill blurs it')
    m = LK().lit_track(); e, fb, raw = blur_world(m, clip='short'); m.calls = []; m.handler(m.card(), 'EVT_BEFORE_PAINT', e)
    expect(bytes(m.u.mem_read(fb, len(raw))) == raw, 'a partial frame is not blurred (a seam), ...')
    m.calls = []; m.tick()
    expect(any(c[0] == 'widget_invalidate_force' and c[1] == m.card() for c in m.calls), '... and the next tick invalidates the whole card')
    m.calls = []; m.tick()
    expect(not any(c[0] == 'widget_invalidate_force' for c in m.calls), 'once')
    m = LK().lit_track(); e, fb, raw = blur_world(m, begin=0x695cb4); m.handler(m.card(), 'EVT_BEFORE_PAINT', e)
    e2, fb2, raw2 = blur_world(m)
    m.handler(m.card(), 'EVT_BEFORE_PAINT', e2)
    expect(bytes(m.u.mem_read(fb, len(raw))) == raw and bytes(m.u.mem_read(fb2, len(raw2))) == raw2, 'another lcd type: untouched, and the blur stays off for the page')
    for label, setup in (('the SD file m1plus-noblur', lambda m: m.present.add('/mnt/mmc/m1plus-noblur')), ('no memory for the plane', lambda m: setattr(m, 'calloc_fail', True))):
        m = LK(); m.placeholder(); m.status = PLAYING; m.track(); m.cover(); setup(m); m.open(); m.first()
        expect(not [c for c in m.log if c[0] == 'widget_on' and c[2] in (O['EVT_BEFORE_PAINT'], O['EVT_POINTER_DOWN'])] and m.pixels()[3] and m.props[(m.w['view_img_icon'], 'visible')] == 0, f'{label}: no blur handlers, the bar still has its cover and glyphs')
    for ev in ('EVT_BEFORE_PAINT', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        m = LK(); m.placeholder(); m.status = PLAYING; m.track(); m.cover(); m.on_fail = {O[ev]}; m.open(); m.first()
        e, fb, raw = blur_world(m)
        if (m.card(), O['EVT_BEFORE_PAINT']) in m.bound and ev != 'EVT_BEFORE_PAINT': m.handler(m.card(), 'EVT_BEFORE_PAINT', e)
        expect(bytes(m.u.mem_read(fb, len(raw))) == raw and m.icons() == PAUSE and m.props[(m.w['view_img_icon'], 'visible')] == 0, f'{ev} refused: no blur at all, the bar works')

    # -- 14. the page timer: only this window's, only while in front, gone with the page
    m = LK(); m.open()
    expect(m.timers == [(FIRST, O['MB_FIRST_MS'])], 'start arms the one-shot only')
    m.placeholder(); m.status = PLAYING; m.track(); m.cover(); m.timers = []; m.first()
    expect(m.timers == [(TICK, 100)], 'the one-shot arms a 100 ms tick (a stock glyph swap and a partial frame are repaired within it)')
    m.screen(False); m.calls = []; m.tick()
    expect(('timer_modify', 0x777, 1000) in m.calls, 'screen off: the tick slows to a second')
    m.track(artist='Z', album='Zed', title='Dark', path='/mnt/mmc/z/9.flac', name='9.flac'); m.cover(artist='Z', album='Zed', rgb=(5, 5, 250)); before = m.pixels()[3]; m.tick()
    expect(m.pixels()[3] != before, 'a track change while dark is made at once, so the cover is right when the screen wakes')
    m.screen(True); m.calls = []; m.tick()
    expect(('timer_modify', 0x777, 100) in m.calls, 'screen on: back to 100 ms')
    m.calls = []; m.handler(WIN, 'EVT_WINDOW_TO_BG')
    expect(('timer_remove', 0x777) in m.calls, 'to background: the timer goes')
    m.sweep(lambda: m.handler(WIN, 'EVT_WINDOW_TO_FG'), lambda: m.handler(WIN, 'EVT_WINDOW_TO_FG'))
    expect(m.timers[-1] == (FIRST, O['MB_FIRST_MS']) and [c for c in m.calls if c[0] == 'timer_add'] == [('timer_add', FIRST, O['MB_FIRST_MS'])], 'to foreground: the one-shot once')
    bmp = next(iter(m.bitmaps)); plane_addr = [c for c in m.log if c[0] == 'calloc'][0][2]
    m.calls = []; m.handler(WIN, 'EVT_DESTROY')
    expect(('timer_remove', 0x777) in m.calls and ('bitmap_destroy', bmp) in m.calls and ('free', plane_addr) in m.calls and not m.bitmaps, 'destroy: the timer, the cover bitmap and the blur plane go')
    ev_ = blur_world(m)[0]
    m.sweep(m.tick, m.first, m.paint, lambda: m.handler(m.card(), 'EVT_BEFORE_PAINT', ev_), lambda: m.handler(WIN, 'EVT_WINDOW_TO_FG'))
    expect(not [c for c in m.calls if c[0] not in ('timer_remove',)] and not m.blits, 'after destroy nothing of ours touches a widget, a bitmap, the buffer or a timer')
    m.calls = []; m.handler(WIN, 'EVT_DESTROY')
    expect(not m.calls, 'a second destroy does nothing')
    # a page opened over one that never said it was gone replaces its state; the earlier window's late destroy leaves the new one alone
    m = LK().lit_track(); bmp = next(iter(m.bitmaps)); m.calls = []; m.open(win=WIN + 0x100)
    expect(('timer_remove', 0x777) in m.calls and ('bitmap_destroy', bmp) in m.calls and m.timers[-1:] == [(FIRST, O['MB_FIRST_MS'])], 'a page started over a live one replaces the old state')
    m.calls = []; m.call(PSYMS['lk_on_destroy'], a0=WIN, a1=0)
    expect(not m.calls, 'the earlier window\'s late destroy leaves the new page alone')

    # -- 15. failures leave stock's bar as the layout left it (the moved stock widgets): no cover hidden, nothing taken over
    def untouched(m, label):
        icon = m.w['view_img_icon']
        expect(m.props.get((icon, 'visible'), 1) == 1 and m.nc('widget_move') == 6 and not any(k[1].startswith('style:') and k[0] in (m.w['btn_play'], m.w['btn_next']) for k in m.props if isinstance(k[1], str))
               and not any(k[1] in ('ellipses', 'only_parent_focus') for k in m.props if isinstance(k[1], str)), f'{label}: stock\'s cover stays, the glyph styles are the page\'s, the layout is the moved stock widgets')
        m.sweep(m.tick, m.paint)
        expect(not [c for c in m.calls if c[0] not in ('timer_remove',)] and not m.blits, f'{label}: every handler left behind is a no-op')
    m = LK(); m.timer_fail = True; m.open(); untouched(m, 'no timer')
    for ev in ('EVT_DESTROY', 'EVT_WINDOW_TO_BG', 'EVT_WINDOW_TO_FG', 'EVT_AFTER_PAINT'):
        m = LK(); m.on_fail = {O[ev]}; m.open(); untouched(m, f'{ev} refused')
        expect(m.timers == [], f'{ev} refused: no timer is left armed')


def setting_tests(ctx):
    """Settings > System > Appearance > Lock Screen (m1plus_appearance, the picker m1plus_lockscreen): the same pattern as the Background row, saved with home_write_atomic."""
    expect, P = ctx.expect, pod_pages
    A_, L = P.APPEARANCE_PAGE, P.LOCK_PAGE
    ai = next(i for i, r in enumerate(A_.rows) if r.label == 'Lock Screen')
    cc = next(i for i, r in enumerate(A_.rows) if r.label == 'Control Center')
    expect(P.ACT_LOCKSET == 88 and not hasattr(P, 'ACT_LOCK') and P.ACT_LOCKSET in P.CHECK_ACTIONS and P.LOCK_PAGE_INDEX == 62 and P.PAGES[62] is L
           and A_.rows[ai].action == P.ACT_PAGE and A_.rows[ai].arg == P.LOCK_PAGE_INDEX and P.row_kind(A_.rows[ai]) == P.row_kind(A_.rows[cc]) and cc == ai + 1,
           'the Lock Screen link row (Appearance, a plain page row like Control Center, no value) opens the Lock Screen page 62')
    lay = [x.label if hasattr(x, 'label') else x for x in A_.layout]
    expect(lay == ['Background', 'Accent', P.GAP, 'Lock Screen', P.GAP, 'Control Center'], f'Appearance cards: Background + Accent, Lock Screen, Control Center ({lay})')
    expect(mod_icons.CARD_GLYPHS['Lock Screen'] == 'lock' and mod_icons.card_name('lock') in mod_icons.CARD_IMAGES, 'the Lock Screen row has the lock glyph')
    SP = P.LOCKSTYLE_PAGE
    expect([(r.label, r.action, r.arg) for r in L.rows] == [('Enable', P.ACT_LOCKON, 0), ('Wallpaper', P.ACT_LOCKWP, 0), ('Show Time', P.ACT_LOCKTIME, 0), ('Player Style', P.ACT_LOCKSTYLE, P.LOCKSTYLE_PAGE_INDEX),
                                                       ('Custom Wallpaper', P.ACT_LOCKINFO, 0)]
           and L.title == 'Lock Screen' and L.key == 'm1plus_lockscreen' and [P.row_kind(r) for r in L.rows] == ['switch', 'link', 'switch', 'value', 'link'],
           'the page: Enable (a switch), Wallpaper (a link), Show Time (a switch), Player Style (a value row), the instructions (a link)')
    lay = [x.label if hasattr(x, 'label') else x.text if hasattr(x, 'text') else x for x in L.layout]
    expect(lay == ['Enable', P.GAP, 'Wallpaper', 'Show Time', P.GAP, 'Player Style', P.GAP, 'Custom Wallpaper'], f'four cards: Enable; Wallpaper + Show Time; Player Style; the instructions ({lay})')
    expect(not [r for r in L.rows if r.label == 'More Settings'] and 'More Settings' not in pod_i18n.TEXT and all(r.action != P.ACT_LOCKSET for r in L.rows), 'More Settings is gone, and the layout rows are no longer on the Lock Screen page')
    expect([(r.label, r.action, r.arg) for r in SP.rows] == [('Large Cover', P.ACT_LOCKSET, 0), ('Mini Player', P.ACT_LOCKSET, 1)] and [x.text for x in SP.layout if hasattr(x, 'text')] == ['Applies the next time the lock screen opens.']
           and SP.title == 'Player Style' and SP.key == 'm1plus_lockstyle' and P.LOCKSTYLE_PAGE_INDEX == 64 and P.PAGES[64] is SP and P.LOCKSTYLE_PAGE_INDEX == P.NEXTALBUM_PAGE_INDEX - 2 and [P.row_kind(r) for r in SP.rows] == ['check', 'check'],
           'the Player Style picker (page 64): Large Cover, Mini Player (checks) and the note')
    expect((P.ACT_LOCKSTYLE, P.ACT_LOCKTIME) == (85, 86) and P.ACT_LOCKSTYLE in P.VALUE_ACTIONS and P.ACT_LOCKTIME in P.SWITCH_ACTIONS and P.VALUE_INIT[P.ACT_LOCKSTYLE] == 'Large Cover', 'Player Style is action 85 (a value row), Show Time 86 (a switch row)')
    IP = P.LOCKINFO_PAGE
    expect(len(P.STOCK_PAGES) == 3 and not any('screensaverabout' in n for n, *_ in P.STOCK_PAGES) and not hasattr(P, 'STOCK_LOCKINFO') and P.LOCKINFO_PAGE_INDEX == 65 and P.PAGES[65] is IP and P.LOCKINFO_PAGE_INDEX == P.NEXTALBUM_PAGE_INDEX - 1
           and IP.key == 'm1plus_lockinfo' and IP.title == 'Custom Wallpaper' and IP.kind == 'relnotes' and P.row_kind(L.rows[4]) == 'link',
           'the instructions row is a link (ACT_LOCKINFO 87) to our own Release Notes page 65 (just before the Continue Playing picker, titled like the row); stock\'s screensaverabout_page is no longer a stock row')
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Show Time', 'Player Style', 'Custom Wallpaper')] == ['clock', 'square-play', 'info'] and all(mod_icons.card_name(g) in mod_icons.CARD_IMAGES for g in ('clock', 'square-play', 'info')),
           'glyphs: clock, square-play, info')
    expect(pod_i18n.key_for('Show Time') == 'Show Time' and pod_i18n.key_for('Custom Wallpaper') == 'Custom Wallpaper' and pod_i18n.key_for('Player Style') == 'Player Style' and 'screenlock_about' not in pod_i18n.STOCK, 'Show Time and Custom Wallpaper are our own short keys (stock\'s texts did not fit)')
    expect(P.SETTING_FILES.index('lockscreen-layout') == P.SETTING_FILES.index('appearance-background') + 1 and P.SETTING_FILES.count('lockscreen-layout') == 1, 'the Settings Files page lists lockscreen-layout after appearance-background')
    rows_a = PSYMS[f'pod_rows_{P.APPEARANCE_PAGE_INDEX}']
    rows_l = PSYMS[f'pod_rows_{P.LOCK_PAGE_INDEX}']
    LOCK_W = ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(5)] + ['pod_switch0', 'pod_switch2', 'pod_value3', 'pod_label3']
    STYLE_W = ['btn_return', 'btn_backtoplayer', 'pod_row0', 'pod_row1', 'pod_check0', 'pod_check1']
    ps = lambda names: {n: 0x30000000 + 0x100 * i for i, n in enumerate(names)}

    def open_lock(m=None, byte_on=None, byte_time=None):
        m = m or Machine()
        m.widgets = ps(LOCK_W)
        if byte_on is not None: m.u.mem_write(pod.DATA['LOCK_ON'][0], bytes([byte_on]))
        if byte_time is not None: m.u.mem_write(pod.DATA['LOCK_TIMESHOW'][0], bytes([byte_time]))
        m.call(PSYMS['on_row'], a0=rows_a + 12 * ai, count=3000000)
        return m

    def open_pick(data=None):
        m = Machine()
        m.widgets = ps(STYLE_W)
        if data is not None: m.fs[FILE] = data
        m.call(PSYMS['on_row'], a0=rows_l + 12 * 3, count=3000000)   # the Lock Screen page's Player Style row (its arg is the picker's page index)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    expect(('window_open', 'm1plus_lockstyle') in open_pick().calls, 'the Player Style row opens the picker page')
    expect([[shown(open_pick(d), i) for i in range(2)] for d in (None, b'1\n', b'0\n', b'9', b'')] == [[1, 0], [0, 1], [1, 0], [1, 0], [1, 0]], 'the picker opens with the check on the saved layout; a missing or invalid file is Large Cover')
    m = open_pick()
    for k in (1, 0, 1):
        m.click(f'pod_row{k}')
        expect(m.fs.get(FILE) == b'%d\n' % k and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
               and [shown(m, i) for i in range(2)] == [int(i == k) for i in range(2)], f'a tap on {SP.rows[k].label}: written atomically ({m.fs.get(FILE)!r}), the check follows')
    m = open_pick(b'1\n'); m.fail.add(('write', FILE + '.tmp')); m.click('pod_row1')
    expect(m.fs.get(FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed write changes neither the file nor the check')
    # the Player Style value row on the Lock Screen page: the saved layout's name, read when the page opens and each time it is back in front
    def style_value(m):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['pod_value3']]
        return v[-1] if v else None
    expect([style_value(open_lock(Machine())) for _ in (0,)] == ['Large Cover'], 'the Player Style row shows Large Cover with no file')
    for data, want in ((b'1\n', 'Mini Player'), (b'0\n', 'Large Cover'), (b'7', 'Large Cover')):
        m = Machine(); m.fs[FILE] = data; open_lock(m)
        expect(style_value(m) == want, f'Player Style reads {data!r}: {want}')
    m = open_lock(Machine()); m.fs[FILE] = b'1\n'; m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(style_value(m) == 'Mini Player', 'back in front after the picker the value follows the saved layout')
    # Enable: stock's own state, the byte screensaver_mode (LOCK_ON) and [SYSSET] SCREENSAVER, written byte first then the key, as stock's click handler 0x4aba34 does
    ON = pod.DATA['LOCK_ON'][0]
    expect(pod.DATA['LOCK_ON'][1] == 'screensaver_mode', 'LOCK_ON is stock\'s screensaver_mode (checked against demo\'s dynsym by the build)')

    def byte(m): return m.u.mem_read(ON, 1)[0]

    def sw_images(m, k=0): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{k}']]

    def cfg(m): return [c for c in m.calls if c[0] in ('write_int_config',)]

    for st, img in ((1, 'sset_on'), (0, 'sset_off'), (2, 'sset_on')):
        m = open_lock(byte_on=st)
        expect(sw_images(m) == [img] and byte(m) == st and not cfg(m), f'the page opens with stock\'s byte {st}: the switch {img}, nothing written')
    m = open_lock(byte_on=1)
    m.click('pod_row0')
    expect(byte(m) == 0 and [c[:4] for c in cfg(m)] == [('write_int_config', 0, 'SYSSET', 'SCREENSAVER')] and sw_images(m)[-1] == 'sset_off' and FILE not in m.fs, 'a tap turns stock\'s lock screen off: byte 0, [SYSSET] SCREENSAVER 0, the switch off, no file of ours')
    m.click('pod_row0')
    expect(byte(m) == 1 and [c[1] for c in cfg(m)] == [1] and sw_images(m) == ['sset_on'], 'and on again')
    # the Wallpaper and Show Time rows stay usable whatever the switch says (no dimming)
    m.u.mem_write(ON, b'\x00'); m.click('pod_row2')
    expect(byte(m) == 0 and [c[:4] for c in cfg(m)] == [('write_int_config', 1, 'SYSSET', 'SSAVERTIMESHOW')], 'with the lock screen off the Show Time row still works')
    expect(not [c for c in m.calls if c[0] in ('widget_set_opacity', 'widget_set_sensitive')], 'and no row is dimmed')

    # Show Time: stock's byte screensaver_timeshow (LOCK_TIMESHOW) and [SYSSET] SSAVERTIMESHOW, the byte first, then the key (stock's handler 0x4ab984 stores it xor 1 in the delay slot of write_int_config)
    TS = pod.DATA['LOCK_TIMESHOW'][0]
    expect(pod.DATA['LOCK_TIMESHOW'] == (0xa05aa2, 'screensaver_timeshow'), 'LOCK_TIMESHOW is stock\'s screensaver_timeshow (checked against demo\'s dynsym by the build)')

    class TM(Machine):
        """The byte as write_int_config sees it (stock stores before the call, so the key's save finds the new state in memory)."""
        def _hook(self, u, address, size, _):
            if self.handlers.get(address) == 'write_int_config': self.seen = u.mem_read(TS, 1)[0]
            return super()._hook(u, address, size, _)

    def tm(st, win=None):
        m = TM(); m.seen = None; m.u.mem_write(TS, bytes([st])); m.widget('img_timeswitch')
        return m

    for st in (0, 1):
        ms = tm(st); ms.call(0x4ab984, a0=0x30000000, count=400000)   # stock's own handler, run for real on the same state
        mo = tm(st); r = mo.call(PSYMS['lk_time_toggle'], count=400000)
        expect(mo.u.mem_read(TS, 1)[0] == ms.u.mem_read(TS, 1)[0] == 1 - st and mo.seen == ms.seen == 1 - st and r == 1 - st
               and [c[:4] for c in mo.calls if c[0] == 'write_int_config'] == [c[:4] for c in ms.calls if c[0] == 'write_int_config'] == [('write_int_config', 1 - st, 'SYSSET', 'SSAVERTIMESHOW')],
               f'Show Time from {st}: our toggle writes what stock\'s handler writes (byte {1 - st} before the save, [SYSSET] SSAVERTIMESHOW {1 - st}), the same calls')
    for st in (0, 1):
        m = open_lock(byte_time=st)
        expect(sw_images(m, 2) == ['sset_on' if st else 'sset_off'] and not cfg(m) and m.u.mem_read(TS, 1)[0] == st, f'the page reads the switch from stock\'s byte ({st}), writes nothing')
    m = open_lock(byte_time=0); m.click('pod_row2')
    expect(m.u.mem_read(TS, 1)[0] == 1 and sw_images(m, 2)[-1] == 'sset_on' and [c[:4] for c in cfg(m)] == [('write_int_config', 1, 'SYSSET', 'SSAVERTIMESHOW')] and FILE not in m.fs and byte(m) == m.u.mem_read(ON, 1)[0],
           'a tap turns Show Time on: byte 1, [SYSSET] SSAVERTIMESHOW 1, the switch on, no file of ours, Enable\'s byte untouched')
    m.click('pod_row2')
    expect(m.u.mem_read(TS, 1)[0] == 0 and sw_images(m, 2)[-1] == 'sset_off' and [c[:4] for c in cfg(m)] == [('write_int_config', 0, 'SYSSET', 'SSAVERTIMESHOW')], 'and off again')
    m = open_lock(byte_time=0); m.u.mem_write(ON, b'\x01'); keys = []
    for row in ('pod_row0', 'pod_row2', 'pod_row0'): m.click(row); keys += [c[3] for c in cfg(m)]
    expect(keys == ['SCREENSAVER', 'SSAVERTIMESHOW', 'SCREENSAVER'], 'Enable and Show Time save under their own keys')
    m = open_lock(byte_time=1); m.u.mem_write(TS, b'\x00'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(sw_images(m, 2) == ['sset_off'], 'back in front the switch is read again from the byte (stock\'s page may have changed it)')

    # the instructions row opens our own page, a Release Notes page (asset and painter shared with patch/relnotes.c)
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui', IP.key + '.bin'), 'rb').read())
    rtree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui', P.RELNOTES.key + '.bin'), 'rb').read())
    expect(P.ACT_LOCKINFO == 87 and P.row_kind(L.rows[4]) == 'link' and tree.get('style:normal:bg_color') == '#000000' and tree.find('label_title').get('tr_text') == 'Custom Wallpaper'
           and tree.find('btn_return') is not None and tree.find('btn_backtoplayer') is not None and tree.find('label_info1') is None,
           'the page has our navbar (Custom Wallpaper, Back, Now Playing) and no static label')
    expect([(w.name, w.type, w.x, w.y, w.w, w.h) for w in tree.walk() if w.name in ('rn_listview', 'rn_scrollview', 'rn_view')] == [(w.name, w.type, w.x, w.y, w.w, w.h) for w in rtree.walk() if w.name in ('rn_listview', 'rn_scrollview', 'rn_view')],
           'the same stock list, scroll view and content view as Release Notes')
    expect(tree.find('label_head').get('style:normal:font_size') == rtree.find('label_head').get('style:normal:font_size') == '22' and tree.find('label_head').get('style:normal:text_color') == '#FFFFFF'
           and tree.find('label_line').get('style:normal:font_size') == '20' and rtree.find('label_line').get('style:normal:font_size') == '18'
           and tree.find('label_line').get('style:normal:text_color') == rtree.find('label_line').get('style:normal:text_color') == '#E6E6E6', 'heading 22 px white as Release Notes; the text 20 px (Release Notes keeps 18 px) #E6E6E6')

    RW = 0x24500000
    PARAS = ['Copy pictures to a folder named lockscreenimage at the top level of the card.', 'JPG or PNG, exactly 320 x 480 pixels, under 1 MB each.', 'Up to 5 pictures. Choose one in Wallpaper.']

    def info_page(loc=None, win=RW, names=('rn_scrollview', 'rn_view', 'label_head', 'label_line')):
        m = open_lock()
        if loc: m.set_language(loc)
        m.windows['m1plus_lockinfo'] = win
        for n in names: m.widget(n)
        m.sv = m.alloc(0x100); m.widgets['rn_scrollview'] = m.sv
        m.canvas = m.alloc(0x80); m.calls = []
        m.click('pod_row4')
        return m

    def paint(m, off=0):
        m.setword(m.sv + 0x84, off)
        ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
        m.texts, m.text_styles = [], []
        fn_, ctx = m.bound[(m.widgets['rn_view'], O['EVT_AFTER_PAINT'])]
        m.call(fn_, a0=ctx, a1=ev, count=40000000)
        return list(zip(m.text_styles, [t for t, r in m.texts], [r for t, r in m.texts]))

    m = info_page()
    expect(('window_open', 'm1plus_lockinfo') in m.calls and not [c for c in m.calls if c[0] in ('navigator_to', 'navigator_to_with_context')], 'the instructions row opens our page m1plus_lockinfo, no stock page')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] == PSYMS['pod_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])][0] == PSYMS['pod_on_player'], 'Back goes back, Now Playing is the player')
    texts = paint(m)
    head = [t for t in texts if t[0] == 'label_head']
    lines = [t for t in texts if t[0] == 'label_line']
    expect(head == [('label_head', 'Add Your Own Pictures', (16, 12, 288, 30))], f'the heading at the top, Release Notes\' place and size ({head})')
    ys = [r[1] for _, _, r in lines]
    expect(len(lines) >= 3 and all(r[0] == 16 and r[2] == 288 and r[3] == 27 for _, _, r in lines) and ys[0] == 12 + 30 + 12 and all(r[1] + r[3] <= 400 for _, _, r in texts), f'the text below it, 288 px wide, 27 px lines inside the view ({ys})')
    steps = [b - a for a, b in zip(ys, ys[1:])]
    joined = ' '.join(t for _, t, _ in lines)
    expect(all(s in (27, 27 + 12) for s in steps) and steps.count(39) == 2 and all(w in joined for p in PARAS for w in p.split()[:3]), f'27 px between lines, a 12 px gap between the three paragraphs ({steps})')
    expect(lines[0][1].startswith('Copy pictures') and any(t.startswith('JPG or PNG') for _, t, _ in lines) and any(t.startswith('Up to 5') for _, t, _ in lines), 'the three paragraphs in order')
    m.calls = []; m.click('btn_return')
    expect(('navigator_back',) in m.calls, 'Back goes back to the Lock Screen page')
    m = info_page('zh_CN')
    texts = paint(m)
    expect([t for t in texts if t[0] == 'label_head'][0][1] == '添加自己的图片' and any(t.startswith('将图片复制到') for s_, t, _ in texts if s_ == 'label_line'), 'in Chinese the heading and the paragraphs are the translations')
    m = info_page(win=0)
    expect(('window_open', 'm1plus_lockinfo') in m.calls and ('navigator_back',) not in m.calls, 'a window that will not open: nothing happens')
    m = info_page(names=('rn_scrollview', 'rn_view', 'label_head'))
    expect(('navigator_back',) in m.calls, 'an asset without a widget the painter needs: the page goes again')
    m = info_page()
    m.calls = []; m.call(PSYMS['lockinfo_open'], count=1000000)
    expect(('window_open', 'm1plus_lockinfo') not in m.calls, 'a second open while it is up does nothing')
    # the lock screen reads what the picker wrote at its next init
    m = LK(setting=None); m.fs[FILE] = b'1\n'; m.open()
    expect(m.nc('widget_move') == 6, 'a saved 1 gives the mini layout at the next lock screen init')
    # Settings Files: the row is deletable and Reset All Settings removes the file, so the large cover returns
    k = P.SETTING_FILES.index('lockscreen-layout') + 5
    m = LK(setting=b'1\n'); m.fs['/mnt/data/m1plus/m1plus-start'] = b'1\n'
    expect(m.call(PSYMS['setfiles_delete'], a0=k) == 0 and FILE not in m.fs, 'Settings Files deletes lockscreen-layout')
    m.log = []; m.open()
    expect(m.nc('widget_move') == 0, 'after the delete the lock screen is the large cover')
    m = LK(setting=b'1\n'); m.listing['/mnt/data/m1plus'] = [('lockscreen-layout', 8)]; m.present.add('/mnt/data/m1plus')
    expect(m.call(PSYMS['setfiles_reset_all']) == 0 and FILE not in m.fs, 'Reset All Settings removes lockscreen-layout')
    m.log = []; m.open()
    expect(m.nc('widget_move') == 0, 'after the reset the lock screen is the large cover')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The Wallpaper picker (patch/lockscreen.c lkwp_*, docs/modules/lockscreen.md "Wallpaper picker")
LW_WIN = 0x24100000
LW_DIR = '/mnt/mmc/lockscreenimage/'
DEFAULT = 'screensaver_default'
CONF = ('/mnt/data/config.ini', 'SYSSET', 'SCREENSAVERPATH')
PICT, LIST = pod.DATA['LOCK_PICTURE'][0], pod.DATA['LOCK_LIST'][0]
GRID = ((12, 0), (115, 0), (218, 0), (12, 143), (115, 143), (218, 143))


class WP(Machine):
    """The picker's world: stock's picture list builder get_screensaver_image (0x4d7524) as a model (the deque pdeq_screensaverlist = the Default name, then what toolsGetScreenSaverPic accepted, at most `limit`; an
    unreadable chosen picture is set back to the default and written), stock's config writer toolsWriteConfig, and the globals screensaver_picture / pdeq_screensaverlist. accepted: the paths stock's folder scan
    accepts (the filter itself, 0x5e4b64, is stock code); a path is readable when it is in fs."""
    def __init__(self, accepted=(), chosen=DEFAULT, limit=5, readable=True):
        super().__init__()
        self.windows['m1plus_lockwall'] = LW_WIN
        for n in ['btn_return', 'btn_backtoplayer'] + [f'imgcover{i}' for i in range(6)] + [f'img_choice{i}' for i in range(6)]: self.widget(n)
        self.accepted, self.limit = list(accepted), limit
        self.list_h = self.new_deque()
        self.setword(LIST, self.list_h)
        self.set_picture(chosen)
        if readable: self.fs.update({p: b'x' for p in self.accepted})

    def set_picture(self, s):
        self.u.mem_write(PICT, bytes(256)); self.u.mem_write(PICT, s.encode())

    def picture(self): return self.read_cstr(PICT)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name == 'get_screensaver_image':
            self.calls.append(('get_screensaver_image',))
            self.deques[self.list_h] = [self.cstr(DEFAULT)] + [self.cstr(p) for p in self.accepted[:self.limit]]
            pic = self.picture()
            if pic != DEFAULT and pic not in self.fs and pic not in self.present:
                self.set_picture(DEFAULT); self.calls.append(('toolsWriteConfig',) + CONF + (DEFAULT, DEFAULT))
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'toolsWriteConfig':
            self.calls.append(('toolsWriteConfig',) + tuple(self.read_cstr(u.reg_read(r)) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)) + (self.picture(),))
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        return super()._hook(u, address, size, _)

    def open(self): return self.call(PSYMS['lkwp_open'], count=4000000)

    def cell(self, i): return self.widgets[f'imgcover{i}']

    def mark(self, i): return self.widgets[f'img_choice{i}']

    def tick(self): return self.call(PSYMS['lw_tick'], count=4000000)

    def sets(self, h): return [c[2] for c in self.calls if c[0] == 'image_base_set_image' and c[1] == h]

    def border(self, i): return self.props.get((self.cell(i), 'style:normal:border_color'))

    def writes(self): return [c for c in self.calls if c[0] == 'toolsWriteConfig']

    def stock_tap(self, i):
        """Stock's own tap handler 0x4ab52c (window, cell index), run for real: its libc calls (GOT slots of deque_size, deque_at, memset, strcmp) go to the harness's mocks, tk_snprintf is snprintf."""
        for off, nm in ((-0xce4, 'deque_size'), (-0xa8c, 'deque_at'), (-0xadc, 'memset'), (-0xa94, 'strcmp')):
            self.setword(pod.GP + off, PSYMS[f'pod_lib_{nm}'])   # (the payload's own libc stubs, trapped already)
        self.handlers[0x70f8d8] = 'snprintf'
        return self.call(0x4ab52c, a0=LW_WIN, a1=i, count=400000)


def wallpaper_tests(ctx):
    """Settings > Lock Screen > Wallpaper: stock's wallpaper grid as our page (entries, marks, the writes of a tap and their order, refusals)."""
    expect, P = ctx.expect, pod_pages
    pins = {a: w for a, w, _ in pod.LOCKSCREEN_PINS}
    imm = lambda a: pins[a] & 0xffff
    # -- the row, the page, its asset (geometry equal to the stock page's, which the pins hold)
    L = P.LOCK_PAGE
    expect(P.ACT_LOCKWP == 84 and P.LOCKWALL_PAGE_INDEX == 63 and P.PAGES[63] is P.LOCKWALL_PAGE and P.LOCKWALL_PAGE_INDEX == P.NEXTALBUM_PAGE_INDEX - 3 and P.LOCK_PAGE_INDEX == 62 and P.LOCKWALL_PAGE.kind == 'lockwall'
           and P.LOCKWALL_PAGE.key == 'm1plus_lockwall' and P.LOCKWALL_PAGE.title == 'Wallpaper' and (L.rows[1].label, L.rows[1].action) == ('Wallpaper', P.ACT_LOCKWP) and P.row_kind(L.rows[1]) == 'link'
           and mod_icons.CARD_GLYPHS['Wallpaper'] == 'image', 'the Wallpaper row (a link row with the image glyph, action 84) opens page 63, kind lockwall')
    root = pod_ui.build_page(P.LOCKWALL_PAGE)
    nav, covers = root.find('navigationbar_view'), root.find('view_covers')
    expect([c.name for c in root.children] == ['navigationbar_view', 'view_covers'] and root.name == 'm1plus_lockwall_page' and nav.find('label_title').get('tr_text') == 'Wallpaper'
           and nav.find('btn_return') is not None and nav.find('btn_backtoplayer') is not None and (covers.x, covers.y, covers.w, covers.h) == (0, 50, 320, 400), 'the page: our navbar (title Wallpaper, Back, Now Playing) over view_covers at 0,50,320,400, stock\'s name')
    cells = [covers.find(f'imgcover{i}') for i in range(6)]
    expect([c.name for c in covers.children] == [f'imgcover{i}' for i in range(6)] and [(c.x, c.y) for c in cells] == list(GRID) and all((c.w, c.h) == (90, 135) for c in cells)
           and all(c.get('draw_type') == 'scale_auto' and c.get('clickable') == 'true' and c.get('visible') == 'false' and c.get('sensitive') == 'false' for c in cells),
           'six cells, three to a row (x 12, 115, 218; y 0, 143), 90 x 135, scale_auto, clickable, hidden and insensitive until the payload shows them')
    expect(imm(0x4abed4) == 90 and imm(0x4abed0) == 135 and imm(0x4abf0c) == 103 and imm(0x4abf38) == 12 == imm(0x4abf10) and imm(0x4abefc) == 143 and imm(0x4abbd4) == 4 and imm(0x4abc48) == 26
           and [c.x for c in cells[:3]] == [12, 12 + imm(0x4abf0c), 12 + 2 * imm(0x4abf0c)] and cells[3].y == imm(0x4abefc), 'the grid numbers are the ones the pinned stock code uses (90 x 135, + 103, y 143, draw type 4 = scale_auto, 26 px marks)')
    ok = True
    for i, c in enumerate(cells):
        mk = c.find(f'img_choice{i}')
        ok = ok and mk is not None and (mk.x, mk.y, mk.w, mk.h) == (4, 4, 26, 26) and mk.get('image') == 'screensaver_unselect' and mk.get('sensitive') == 'false'
        ok = ok and all(c.get(f'style:{st}:border_width') == '2' and c.get(f'style:{st}:border_color') == '#00000000' for st in ('normal', 'disable', 'focused'))
        ic = c.find('img_defaulticon')
        ok = ok and ((ic is None) if i else (ic is not None and (ic.x, ic.y, ic.w, ic.h) == (0, 111, 24, 24) and ic.get('image') == 'screensaver_defaulticon'))
    expect(ok, 'each cell has its 26 px mark at 4,4 (screensaver_unselect) and a 2 px transparent border; cell 0 also the 24 px default icon at 0,111')

    # -- open: stock's list first, the entries shown, the marks, thumbnails one per tick
    A, B, C = LW_DIR + 'a.jpg', LW_DIR + 'b.png', LW_DIR + 'c.jpeg'
    m = WP([A, B, C], chosen=B)
    r = m.open()
    names = m.names()
    expect(r == 0 and m.calls[0] == ('window_open', 'm1plus_lockwall') and names.count('get_screensaver_image') == 1 and names.index('get_screensaver_image') < names.index('widget_set_visible'), 'open: the page window, then stock\'s list builder (once), then the cells')
    expect([(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_visible'] == [(m.cell(i), 1) for i in range(4)] and [c[1] for c in m.calls if c[0] == 'widget_set_sensitive'] == [m.cell(i) for i in range(4)]
           and not any(m.cell(i) in c[1:2] for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') for i in (4, 5)), 'the Default entry and three pictures are shown and sensitive; the other two cells are left hidden')
    expect([m.sets(m.mark(i))[-1] for i in range(4)] == ['screensaver_unselect', 'screensaver_unselect', 'screensaver_selected', 'screensaver_unselect'] and [m.border(i) for i in range(4)] == ['#00000000', '#00000000', '#EEEEEC', '#00000000']
           and all(m.props.get((m.cell(2), f'style:{st}:border_color')) == '#EEEEEC' for st in ('normal', 'disable', 'focused')), 'the mark is on the chosen picture (the accent border, Neutral here, and screensaver_selected), the others unselected')
    expect(m.sets(m.cell(0)) == [DEFAULT] and not any(m.sets(m.cell(i)) for i in (1, 2, 3)) and m.timers == [(PSYMS['lw_tick'], 40)] and all((m.cell(i), O['EVT_CLICK']) in m.bound for i in range(4))
           and not any((m.cell(i), O['EVT_CLICK']) in m.bound for i in (4, 5)), 'Default is set at once (a resource); the pictures wait for the timer (40 ms); a tap handler on each shown cell only')
    # the selected border is the accent (stock's is orange #FE7E40): every saved accent, and Neutral under the kill switch
    import palette as PAL
    for idx, ac in enumerate(PAL.ACCENTS[1:], 1):
        for kill in (False, True):
            m = WP([A, B, C], chosen=B); m.fs['/mnt/data/m1plus/appearance-accent'] = b'%d\n' % idx
            if kill: m.fs['/mnt/mmc/m1plus-off'] = b''
            m.open()
            want = '#EEEEEC' if kill else '#%02X%02X%02X' % PAL.ACCENT_RGB[ac]
            expect(m.border(2) == want and [m.border(i) for i in (0, 1, 3)] == ['#00000000'] * 3, f'accent {ac}{" (kill switch)" if kill else ""}: the chosen picture\'s border is {want} ({m.border(2)})')
    rets, got = [], {}
    for _ in range(3):
        rets.append(m.tick())
        for i in (1, 2, 3): got.setdefault(i, []).extend(m.sets(m.cell(i)))
    expect(rets == [8, 8, 0] and [got.get(i) for i in (1, 2, 3)] == [['file://' + A], ['file://' + B], ['file://' + C]], f'one picture per tick as file://<path>, the timer ends after the last ({rets})')
    m.calls = []; expect(m.tick() == 0 and not m.calls, 'a late tick does nothing')

    # -- a tap: the writes stock makes, in stock's order
    m = WP([A, B, C], chosen=B); m.open(); m.calls = []
    m.click('imgcover1')
    seq = [c for c in m.calls if c[0] in ('image_base_set_image', 'toolsWriteConfig')]
    expect(seq == [('image_base_set_image', m.mark(2), 'screensaver_unselect'), ('image_base_set_image', m.mark(1), 'screensaver_selected'), ('toolsWriteConfig',) + CONF + (A, A)],
           f'a tap on another picture: the old mark off, the new mark on, then toolsWriteConfig(config.ini, SYSSET, SCREENSAVERPATH, path), the global already the path ({seq})')
    expect(m.picture() == A and [m.border(i) for i in range(4)] == ['#00000000', '#EEEEEC', '#00000000', '#00000000'] and not {'write_int_config', 'fopen', 'rename', 'open', 'write'} & set(m.names())
           and len(m.writes()) == 1, 'screensaver_picture is the path, the border follows, the only write is that one config key')
    m.calls = []; m.click('imgcover1')
    expect(not [c for c in m.calls if c[0] in ('image_base_set_image', 'toolsWriteConfig', 'widget_use_style')] and m.picture() == A, 'a tap on the chosen picture again does nothing')
    m.calls = []; m.click('imgcover0')
    expect(m.writes() == [('toolsWriteConfig',) + CONF + (DEFAULT, DEFAULT)] and m.picture() == DEFAULT and m.border(0) == '#EEEEEC' and m.border(1) == '#00000000' and m.sets(m.mark(0)) == ['screensaver_selected'],
           'a tap on Default writes the resource name')
    m.calls = []; m.click('imgcover3')
    expect(m.writes() == [('toolsWriteConfig',) + CONF + (C, C)] and m.picture() == C, 'and on the last picture')
    long_path = LW_DIR + 'x' * (200 - len(LW_DIR) - 4) + '.jpg'
    m = WP([long_path]); m.open(); m.click('imgcover1')
    expect(len(long_path) == 200 and m.picture() == long_path and m.writes()[0][4] == long_path, 'a path of stock\'s longest length (200) is written whole')
    m = WP([A, B]); m.open(); m.deques[m.list_h] = [m.cstr(DEFAULT), m.cstr(LW_DIR + 'other.jpg')]; m.click('imgcover2')
    expect(m.picture() == B and m.writes()[0][4] == B, 'the entries are copied when the page opens: a stock page that rebuilds the list later does not change what a tap writes')

    # -- stock's own tap handler (0x4ab52c) run on the same state: the same global, the same config write, the same marks (stock restyles the cell with a style name where ours sets the border colour)
    for chosen, tap in ((DEFAULT, 2), (B, 1), (A, 0), (C, 3), (B, 3), (DEFAULT, 0), (A, 1)):
        ours, stock = WP([A, B, C], chosen=chosen), WP([A, B, C], chosen=chosen)
        ours.open(); stock.open()
        ours.calls = []; stock.calls = []
        ours.click(f'imgcover{tap}'); stock.stock_tap(tap)
        marks = lambda mm: [(i, mm.sets(mm.mark(i))) for i in range(4)]
        styles = [(i, c[2]) for c in stock.calls if c[0] == 'widget_use_style' for i in range(4) if c[1] == stock.cell(i)]
        want = [(i, 'picture_selected_style' if ours.border(i) != '#00000000' else 'picture_unselect_style') for i in range(4) if (i, 'picture_unselect_style') in styles or (i, 'picture_selected_style') in styles]
        expect(ours.picture() == stock.picture() and ours.writes() == stock.writes() and marks(ours) == marks(stock) and sorted(styles) == sorted(want) and (ours.picture() != chosen) == bool(stock.writes()),
               f'stock\'s handler and ours agree for a tap on {tap} with {chosen.rsplit("/", 1)[-1]} chosen: global {stock.picture().rsplit("/", 1)[-1]}, writes {len(stock.writes())}, marks, styles')

    # -- the list as stock builds it
    m = WP([A], chosen=LW_DIR + 'zzz.jpg'); m.fs[LW_DIR + 'zzz.jpg'] = b'x'; m.open()
    expect([m.sets(m.mark(i))[-1] for i in range(2)] == ['screensaver_unselect', 'screensaver_unselect'] and [m.border(i) for i in range(2)] == ['#00000000'] * 2, 'a readable chosen picture stock\'s list no longer has: no cell is marked')
    m.calls = []; m.click('imgcover0')
    expect(m.picture() == DEFAULT and len(m.writes()) == 1 and m.sets(m.mark(0)) == ['screensaver_selected'] and m.sets(m.mark(1)) == [], 'Default can then be chosen (stock\'s handler takes cell 0 for the old one and returns without writing)')
    m = WP([]); m.open()
    expect(m.sets(m.mark(0))[-1] == 'screensaver_selected' and m.timers == [] and [c[1] for c in m.calls if c[0] == 'widget_set_visible'] == [m.cell(0)] and m.sets(m.cell(0)) == [DEFAULT],
           'an empty or missing folder: Default alone, marked, no timer')
    m.calls = []; m.click('imgcover0')
    expect(not m.writes(), 'its tap (the chosen one) writes nothing')
    m = WP([A, B], chosen=LW_DIR + 'gone.jpg', readable=True); m.open()
    expect(m.writes() == [('toolsWriteConfig',) + CONF + (DEFAULT, DEFAULT)] and m.picture() == DEFAULT and m.sets(m.mark(0))[-1] == 'screensaver_selected' and m.sets(m.mark(1))[-1] == 'screensaver_unselect',
           'a chosen picture that can no longer be read: stock\'s builder sets Default (its one write), the picker shows Default marked and writes nothing itself')
    m = WP([LW_DIR + f'p{i}.jpg' for i in range(8)], limit=9); m.open()
    expect(len([c for c in m.calls if c[0] == 'widget_set_visible']) == 6 and m.sets(m.cell(5)) == [] and m.deques[m.list_h].__len__() == 9, 'more entries than cells: six shown')

    # -- refusals
    m = WP([A]); m.windows['m1plus_lockwall'] = 0; r = m.open()
    expect(r == 0xffffffff and not any(c[0] in ('widget_lookup', 'get_screensaver_image', 'navigator_back') for c in m.calls), 'a window that will not open: -1, nothing else')
    m = WP([A]); m.widgets.pop('imgcover3'); r = m.open()
    expect(r == 0xffffffff and ('navigator_back',) in m.calls and not any(c[0] in ('get_screensaver_image', 'timer_add') for c in m.calls), 'a missing widget: back, -1, no list built')
    m.widget('imgcover3'); m.calls = []; r = m.open()
    expect(r == 0 and ('window_open', 'm1plus_lockwall') in m.calls, 'and the next open starts clean')
    m = WP([A]); m.widget_on_fail = frozenset([O['EVT_DESTROY']]); r = m.open()
    expect(r == 0xffffffff and ('navigator_back',) in m.calls and not any(c[0] == 'get_screensaver_image' for c in m.calls), 'a refused destroy handler: back, -1')
    m = WP([A]); m.open(); n0 = m.names().count('window_open'); r = m.open()
    expect(r == 0 and m.names().count('window_open') == 0 and n0 == 1, 'opening again while it is open does nothing')
    m = WP([A, B]); m.timer_fail = True; m.open()
    expect(m.sets(m.cell(1)) == ['file://' + A] and m.sets(m.cell(2)) == ['file://' + B], 'a refused timer: every picture is set at once')
    m = WP([A, B, C], chosen=A); m.open()
    m.fire(O['EVT_WINDOW_TO_BG'], LW_WIN)
    expect(('timer_remove', 0x777) in m.calls and m.tick() == 0, 'to the background the timer is removed, a late tick does nothing')
    m.set_picture(B); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'], LW_WIN)
    expect([m.border(i) for i in range(4)] == ['#00000000', '#00000000', '#EEEEEC', '#00000000'] and any(c[0] == 'timer_add' for c in m.calls) and not m.writes(), 'back in front: the marks follow the choice (stock\'s page may have changed it), the timer picks up the rest, nothing is written')
    m.calls = []; m.fire(O['EVT_DESTROY'], LW_WIN)
    expect(('timer_remove', 0x777) in m.calls and m.tick() == 0, 'destroy: the timer is removed')
    m.calls = []; m.open()
    expect(('window_open', 'm1plus_lockwall') in m.calls, 'and the picker opens again afterwards')
    # -- the Lock Screen page's row opens it
    m = WP([A]); m.widgets.update({f'pod_row{i}': 0x30000000 + 0x100 * i for i in range(5)}); m.widgets['pod_switch0'] = 0x30001000
    m.call(PSYMS['on_row'], a0=PSYMS[f'pod_rows_{P.APPEARANCE_PAGE_INDEX}'] + 12 * next(i for i, r in enumerate(P.APPEARANCE_PAGE.rows) if r.label == 'Lock Screen'), count=3000000)
    m.calls = []; m.click('pod_row1')
    expect(('window_open', 'm1plus_lockwall') in m.calls and any(c[0] == 'get_screensaver_image' for c in m.calls), 'the Lock Screen page\'s Wallpaper row opens the picker')


def redirect_tests(ctx):
    """The Display page's Lock Screen row (stock's click handler 0x4a5c10, case 2) opens our Lock Screen page: the pinned two-word edit, the stub, the fallbacks and the Display page fresh or restacked."""
    expect = ctx.expect
    import paths
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site, stub = pod.LOCKROW, PSYMS['pod_lock_site']
    expect(site == 0x4a5ca8 and all(w(stock, a) == old and (a in (site, site + 4) or w(built, a) == old) for a, old, _ in pod.LOCKROW_PINS),
           'every pinned word of the Display page\'s lock screen case is stock\'s in the stock demo and unchanged in the build (but the two edited)')
    expect(w(stock, site) == 0x8f84a708 and w(stock, site + 4) == 0x1000fff6 and w(built, site) == pod.j(stub) and w(built, site + 4) == 0 and w(built, site + 8) == w(stock, site + 8)
           and w(built, site - 4) == w(stock, site - 4) and w(built, site + 12) == w(stock, site + 12), 'the case @0x4a5ca8: `lw a0; b navigator_to` became `j pod_lock_site; nop`, its neighbours are stock\'s')
    got = [w(built, stub + 4 * i) for i in range(11)]
    expect(got == [pod.jal(PSYMS['lk_redirect'], stub), 0, 0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, 0x14400004, 0, 0x8f84a708, pod.j(pod.LOCKROW_NAV), 0x24847d24, pod.j(pod.LOCKROW_DONE), 0],
           f'pod_lock_site: jal lk_redirect, $gp set, bnez to the epilogue jump, else stock\'s own two words (a0 = "systemset/screensaver_page") and the shared navigator_to call ({[hex(x) for x in got]})')
    expect(w(stock, 0x4a5c88) == 0x8f99a704 and w(stock, pod.LOCKROW_DONE) == 0x1000fff2 and MANIFEST['hook_lock_row'] == {'addr': site, 'target': stub}, 'the stub resumes at stock\'s navigator_to call and epilogue; the manifest lists the hook')
    # the string's other reference is the navigator's page-init dispatcher (strcmp), not a caller
    expect(w(built, 0x4d14a8) == w(stock, 0x4d14a8) and w(built, 0x4d14b4) == w(stock, 0x4d14b4), 'the page-init dispatcher\'s strcmp "systemset/screensaver_page" (@0x4d14a8) is untouched: stock\'s page still exists')

    def row(m, idx):
        """The row's click handler 0x4a5c10 run for real (a0 = the list item; its name is the row number, atoi'd)."""
        item = m.alloc(0x40); m.u.mem_write(item, bytes(0x40)); m.setword(item + 0x10, m.cstr(str(idx)))
        m.setword(pod.GP - 0xcec, PSYMS['pod_lib_atoi'])
        return m.call(0x4a5c10, a0=item, count=400000)

    def navs(m): return [c[1] for c in m.calls if c[0] == 'navigator_to']
    def opened(m): return [c[1] for c in m.calls if c[0] == 'window_open']

    m = Machine(); r = row(m, 2)
    expect(r == 0 and opened(m) == ['m1plus_lockscreen'] and navs(m) == [], 'the Lock Screen row opens our page (window m1plus_lockscreen), not systemset/screensaver_page; the handler returns 0')
    for idx, page in ((0, 'systemset/brightness_page'), (1, 'systemset/lighttime_page'), (3, 'systemset/atmosphereled_page')):
        m = Machine(); r = row(m, idx)
        expect(r == 0 and navs(m) == [page] and opened(m) == [], f'row {idx} is still stock\'s: {page}')
    m = Machine(); m.present.add(KILL); r = row(m, 2)
    expect(r == 0 and navs(m) == ['systemset/screensaver_page'] and opened(m) == [], 'the kill switch: stock\'s page opens exactly as before')
    m = Machine(); m.window = 0; r = row(m, 2)
    expect(r == 0 and opened(m) == ['m1plus_lockscreen'] and navs(m) == ['systemset/screensaver_page'], 'our page refused (window_open fails): stock\'s page opens')
    # the Display page opened fresh or restacked (the Now Playing button put the player over it): the same row, the same result
    SF = sibling('pdtiles').SF
    for label, stack in (('fresh', ['home_page']), ('restacked', ['home_page', 'display_page', 'playing_page'])):
        for kill in (False, True):
            m = SF(stack)
            if kill: m.present.add(KILL)
            m.call(PSYMS['pod_open_stock'], a0=m.cstr('systemset/display_page'), a1=m.cstr('display_page'), count=3000000)
            on_top = m.names_()[-1] == 'display_page' and m.names_().count('display_page') == 1
            m.calls = []; r = row(m, 2)
            want = (['systemset/screensaver_page'], []) if kill else ([], ['m1plus_lockscreen'])
            expect(on_top and r == 0 and (navs(m), opened(m)) == want, f'Display {label}, kill switch {"on" if kill else "off"}: one Display window in front, then the Lock Screen row gives {want[0] or want[1]}')


SECTIONS = [hook_tests, layout_tests, life_tests, bar_tests, setting_tests, wallpaper_tests, redirect_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

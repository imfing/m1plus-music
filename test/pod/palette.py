"""Light Mode (patch/palette.c, tools/palette.py, docs/modules/accent.md): the three hooks on the painter's inputs (style_get_color, style_get_gradient, image_manager_add), the flip, the image rules, the
setting and its Auto clock, the cover-tinted pages' neutral tone and the Settings row.

The C runs under Unicorn. style_get_color is stock's own code (the trampoline resumes at its fourth instruction) over a fake style object whose vtable slots are small mocks (or a small MIPS stub that
makes the style 'mutable': it asks again, through the hook, as AWTK's mutable styles do); style_get_gradient is the hook's whole leaf, called by stock's own `bal`. Every image of the built tree
that is small enough runs through the C and is compared pixel for pixel with tools/palette.py."""
import os, struct
from unicorn.mips_const import UC_MIPS_REG_RA, UC_MIPS_REG_V0, UC_MIPS_REG_A0, UC_MIPS_REG_A1
import palette as L
import awtk_ui
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

BG_FILE = '/mnt/data/m1plus/appearance-background'
ACCENT_FILE = '/mnt/data/m1plus/appearance-accent'
KILL_SD, KILL_FLASH, BAD = '/mnt/mmc/m1plus-off', '/mnt/data/m1plus-off', '/mnt/data/m1plus-bad'
WHITE, BLACK = 0xffffffff, 0xff000000
PAPER, INK = L.PAPER * 0x010101 | 0xff000000, L.INK * 0x010101 | 0xff000000
F_COLOR, F_GRAD, F_NEST = HEAP + 0x800000, HEAP + 0x800100, HEAP + 0x800200   # code addresses the mocks trap (fake style vtable slots), and the stub that asks again
EVT = {'color': 0x14, 'grad': 0x18}


def px(c):
    """color_t word (bytes r, g, b, a: a is the top byte) to a tuple (r, g, b, a)."""
    return (c & 255, c >> 8 & 255, c >> 16 & 255, c >> 24)


def word(t):
    return t[0] | t[1] << 8 | t[2] << 16 | t[3] << 24


class LM(Machine):
    """The payload with Light Mode's state: mode is the saved file's text (None: no file)."""
    keep_cache = False

    def __init__(self, mode=None, kill=False, bad=False, hook=False, acc=None):
        super().__init__()
        if mode is not None: self.fs[BG_FILE] = mode
        if acc is not None: self.fs[ACCENT_FILE] = acc
        if kill: self.present.add(KILL_SD)
        if bad: self.present.add(BAD)
        self.unloads = 0
        self.real_unload = False   # unload_all really empties the cache
        self.imm = self.alloc(0x40)   # the image manager (opaque)
        self.cache, self.destroy_flags = {}, []   # the image manager's cache (name -> (the 0x48 byte bitmap_t, its pixels' address)), filled by cache_image and by stock's add; the 0x30 / 0x31 bytes of every bitmap_destroy
        self.colors, self.grads = {}, {}     # style -> its colour / its gradient stops
        for a, n in ((F_COLOR, 'fake_color'), (F_GRAD, 'fake_grad')): self.handlers[a] = n
        self.handlers[PSYMS['stock_image_add_trampoline']] = 'stock_image_add'   # stock's image_manager_add is not run: the hook's own work is what is looked at
        if hook: self.u.hook_add(UC_HOOK_CODE, lambda u, a, s, d: None)   # (Unicorn's translator crashes on stock's style_get_color without a code hook over it; it slows the image test down 10 times, so only the style tests have one)
        self.vt = self.alloc(0x40)
        self.setword(self.vt + 0x14, F_COLOR)

    def style(self, color=None, grads=None, vt=None):
        """A fake style object: its vtable's get_color (the colour it answers) and get_gradient (the stops, or none)."""
        s = self.alloc(0x10)
        v = vt or self.alloc(0x40)
        self.setword(s, v); self.setword(v + 0x14, F_COLOR)
        self.setword(v + 0x18, F_GRAD if grads is not None else 0)
        self.colors[s] = color if color is not None else 0xff808080
        self.grads[s] = grads
        return s

    def on_top(self, name):
        """A top main window with that name (widget_t name at +0x10); the window manager's top is it."""
        w = self.alloc(0x80)
        self.setword(w + 0x10, self.cstr(name))
        self.top_main = w
        return w

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name == 'bitmap_destroy':
            self.destroy_flags.append(bytes(self.u.mem_read(u.reg_read(UC_MIPS_REG_A0) + 0x30, 2)))
        elif name == 'bitmap_create_ex':   # (as stock's: the pixels and the handle are owned)
            super()._hook(u, address, size, _)
            b = u.reg_read(UC_MIPS_REG_V0)
            if b: self.u.mem_write(b + 0x30, b'\x01\x01')
            return
        if name in ('fake_color', 'fake_grad', 'stock_image_add', 'image_manager_unload_all', 'image_manager'):
            a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
            ret = 0
            if name == 'fake_color':      # get_color(color_out, style, name, fallback)
                self.setword(a0, self.colors.get(a1, 0)); ret = a0
                self.calls.append(('get_color', a1))
            elif name == 'fake_grad':     # get_gradient(style, name, out): nr at +8, stops {color, offset} from +0xc
                stops = self.grads.get(a0)
                self.calls.append(('get_gradient', a0))
                if stops:
                    self.setword(a2 + 8, len(stops))
                    for i, c in enumerate(stops): self.setword(a2 + 0xc + 8 * i, c); self.setword(a2 + 0x10 + 8 * i, i)
                    ret = a2
            elif name == 'stock_image_add':
                nm = self.read_cstr(a1)
                self.calls.append(('stock_image_add', nm)); ret = 0
                if a2 and self.keep_cache:   # the manager's copy: the struct, and the pixels moved out of the handle's reach (bitmap_destroy gives the block back to the harness' pool)
                    st = bytes(self.u.mem_read(a2, 0x48)); n = struct.unpack('<I', st[:4])[0] * struct.unpack('<I', st[4:8])[0] * 4
                    data = self.malloc(n); self.u.mem_write(data, bytes(self.u.mem_read(struct.unpack('<I', st[0x14:0x18])[0], n)))
                    self.cache[nm] = (st[:0x14] + struct.pack('<I', data) + st[0x18:], data)
            elif name == 'image_manager_unload_all':
                self.unloads += 1; self.calls.append(('unload_all',))
                if self.real_unload: self.cache.clear()
            elif name == 'image_manager': ret = self.imm
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    def color(self, style, name='bg_color', fallback=0xff112233):
        """m1plus_style_color(out, style, name, fallback), as the hooked style_get_color is called; the colour it leaves."""
        out = self.alloc(8)
        r = self.call(PSYMS['m1plus_style_color'], a0=out, a1=style, a2=self.cstr(name), a3=fallback, count=4000)
        assert r == out, 'style_get_color returns its out pointer'
        return self.word(out)

    def gradient(self, style, name='bg_color'):
        """m1plus_style_gradient(style, name, out) called from the test (a caller that is not style_get_color); (result is out, the stops)."""
        out = self.alloc(0x60)
        self.u.mem_write(out, bytes(0x60))
        r = self.call(PSYMS['m1plus_style_gradient'], a0=style, a1=self.cstr(name), a2=out, count=4000)
        nr = self.word(out + 8)
        return (r == out if r else r), [self.word(out + 0xc + 8 * i) for i in range(min(nr, 8))]

    def nested(self, inner):
        """A style whose get_color asks again, through the hook, as a mutable style asks its default style: a stub (lui/ori a1, inner; lui/ori t9, the hook; jr t9)."""
        hook = PSYMS['m1plus_style_color']
        words = [0x3c050000 | inner >> 16, 0x34a50000 | inner & 0xffff, 0x3c190000 | hook >> 16, 0x37390000 | hook & 0xffff, 0x03200008, 0]
        self.u.mem_write(F_NEST, struct.pack('<6I', *words))
        self.u.ctl_flush_tb()   # (the stub of an earlier style may have been translated)
        s = self.alloc(0x10)
        v = self.alloc(0x40)
        self.setword(s, v); self.setword(v + 0x14, F_NEST); self.setword(v + 0x18, 0)
        return s

    def cache_image(self, name, w, h, pixels, fmt=1, premul=False):
        """An image in the manager's cache (what stock decoded and the hook let through), pixels as (r, g, b, a) rows given as stored in the channel order of fmt."""
        order = {1: (0, 1, 2, 3), 2: (3, 2, 1, 0), 3: (2, 1, 0, 3), 4: (1, 2, 3, 0)}[fmt]
        raw = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            for c in range(4): raw[i * 4 + order[c]] = p[c]
        data = self.malloc(w * h * 4); self.u.mem_write(data, bytes(raw))
        st = bytearray(0x48); struct.pack_into('<II', st, 0, w, h); struct.pack_into('<I', st, 0x14, data)
        struct.pack_into('<H', st, O['BITMAP_FORMAT'], fmt); struct.pack_into('<H', st, O['BITMAP_FLAGS'], 16 if premul else 0); st[0x30] = 1
        self.cache[name] = (bytes(st), data)

    def cached(self, name, fmt=1):
        """The pixels of a cached image as (r, g, b, a) tuples, or None."""
        if name not in self.cache: return None
        st, data = self.cache[name]; w, h = struct.unpack('<II', st[:8])
        order = {1: (0, 1, 2, 3), 2: (3, 2, 1, 0), 3: (2, 1, 0, 3), 4: (1, 2, 3, 0)}[fmt]
        raw = bytes(self.u.mem_read(data, w * h * 4))
        return [tuple(raw[i * 4 + order[c]] for c in range(4)) for i in range(w * h)]

    def image(self, name, w, h, pixels, fmt=1, premul=False):
        """image_manager_add(manager, name, bitmap) of a w x h image (pixels: (r, g, b, a) rows, straight alpha unless premul says they are given as stored) through the hook;
        the stored pixels as (r, g, b, a) tuples."""
        order = {1: (0, 1, 2, 3), 2: (3, 2, 1, 0), 3: (2, 1, 0, 3), 4: (1, 2, 3, 0)}[fmt]
        data = self.malloc(w * h * 4)
        b = self.malloc(0x48)
        self.u.mem_write(b, bytes(0x48))
        self.setword(b, w); self.setword(b + 4, h); self.setword(b + 0x14, data)
        self.u.mem_write(b + O['BITMAP_FORMAT'], struct.pack('<H', fmt))
        self.u.mem_write(b + O['BITMAP_FLAGS'], struct.pack('<H', 16 if premul else 0))
        raw = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            for c in range(4): raw[i * 4 + order[c]] = p[c]
        self.u.mem_write(data, bytes(raw))
        self.call(PSYMS['m1plus_image_add'], a0=0x23000000, a1=self.cstr(name), a2=b, count=40000000)
        out = bytes(self.u.mem_read(data, w * h * 4))
        return [tuple(out[i * 4 + order[c]] for c in range(4)) for i in range(w * h)]


def fl(pixels, neutral_only=False):
    """What the device leaves of these straight pixels: every pixel with alpha flipped (or only the neutral ones), a clear pixel as it is (its colour is not seen)."""
    return [(L.flip(p) if neutral_only else tuple(L.flip_v(v) for v in p[:3]) + (p[3],)) if p[3] else p for p in pixels]


def glyph_image(w=16, h=16):
    """A white glyph on nothing: a plus, opaque white, the rest clear."""
    return [(255, 255, 255, 255) if x == w // 2 or y == h // 2 else (255, 255, 255, 0) for y in range(h) for x in range(w)]


def disc_image(w=16, h=16):
    """A grey disc (opaque, dark) with a white mark: a surface under a glyph."""
    return [(255, 255, 255, 255) if x == w // 2 else (0x55, 0x55, 0x55, 255) for y in range(h) for x in range(w)]


def hooks_tests(ctx):
    """The three hooks: pinned words, the jumps into the payload, the trampolines, the manifest; nothing else of stock changed at those sites."""
    expect = ctx.expect
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    j = lambda a: 0x08000000 | a >> 2
    expect(pod.STYLE_COLOR == 0x659fcc and pod.IMAGE_ADD == 0x655638 and pod.STYLE_GRADIENT == 0x659f9c and pod.STYLE_COLOR_RET == O['STYLE_COLOR_GRADIENT_RET'] == 0x65a050,
           'the hook sites: style_get_color 0x659fcc, style_get_gradient 0x659f9c, image_manager_add 0x655638; the gradient call returns to 0x65a050')
    expect(all(w(stock_demo, a) == old for a, old, _ in pod.LIGHT_PINS) and all(w(built, a) == old for a, old, _ in pod.LIGHT_PINS),
           f'the {len(pod.LIGHT_PINS)} pinned words around the sites are stock\'s, in the stock demo and unchanged in the build')
    for name, a, pro in (('style_get_color', pod.STYLE_COLOR, pod.STYLE_COLOR_PROLOGUE), ('image_manager_add', pod.IMAGE_ADD, pod.IMAGE_ADD_PROLOGUE)):
        expect(tuple(w(stock_demo, a + 4 * i) for i in range(3)) == pro, f'{name}: the stock prologue is the pinned PIC one')
        low = pro[1] & 0xffff
        expect(((pro[0] & 0xffff) << 16) + (low if low < 0x8000 else low - 0x10000) + a == pod.GP, f'{name}: its prologue computes $gp = {pod.GP:#x}')
    expect(w(built, pod.STYLE_COLOR) == j(PSYMS['m1plus_style_color']) and w(built, pod.STYLE_COLOR + 4) == 0 and w(built, pod.STYLE_COLOR + 8) == w(stock_demo, pod.STYLE_COLOR + 8),
           'style_get_color starts with `j m1plus_style_color; nop`, its third word is stock\'s')
    expect(w(built, pod.IMAGE_ADD) == j(PSYMS['m1plus_image_add']) and w(built, pod.IMAGE_ADD + 4) == 0 and w(built, pod.IMAGE_ADD + 8) == w(stock_demo, pod.IMAGE_ADD + 8),
           'image_manager_add starts with `j m1plus_image_add; nop`')
    expect(tuple(w(stock_demo, pod.STYLE_GRADIENT + 4 * i) for i in range(3)) == pod.STYLE_GRADIENT_WORDS
           and w(built, pod.STYLE_GRADIENT) == j(PSYMS['m1plus_style_gradient']) and w(built, pod.STYLE_GRADIENT + 4) == 0 and w(built, pod.STYLE_GRADIENT + 8) == pod.STYLE_GRADIENT_WORDS[2],
           'style_get_gradient (a leaf: beqz a0; nop; lw v0, (a0)) starts with `j m1plus_style_gradient; nop`')
    # the trampolines restore $gp and resume at +12
    m = LM()
    for sym, at in (('stock_style_color_trampoline', pod.STYLE_COLOR + 12), ('stock_image_add_trampoline', pod.IMAGE_ADD + 12)):
        code = struct.unpack('<4I', bytes(m.u.mem_read(PSYMS[sym], 16)))
        expect(code == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, j(at), 0), f'{sym}: lui/ori $gp, then j {at:#x}')
    expect(MANIFEST['hook_style_color'] == {'addr': pod.STYLE_COLOR, 'target': PSYMS['m1plus_style_color']} and MANIFEST['hook_image_add'] == {'addr': pod.IMAGE_ADD, 'target': PSYMS['m1plus_image_add']}
           and MANIFEST['hook_style_gradient'] == {'addr': pod.STYLE_GRADIENT, 'target': PSYMS['m1plus_style_gradient']}, 'the manifest records the three hooks')
    # style_get_color is called only through the gradient bal this hook leaves unmapped, and image_manager_add only by the decoding look-up
    expect(w(built, 0x65a048) == 0x0411ffd4 and (0x65a048 + 4 + (0xffd4 - 0x10000) * 4) == pod.STYLE_GRADIENT, 'style_get_color\'s `bal` at 0x65a048 goes to style_get_gradient\'s first word (the hook\'s jump) and returns to 0x65a050')


def flip_tests(ctx):
    """The flip: black to paper, white to ink per channel, neutral only (within LIGHT_SPREAD), alpha kept, a clear colour clear; the C against tools/palette.py."""
    expect = ctx.expect
    m = LM()
    f = lambda c: m.call(PSYMS['light_flip'], a0=c, count=2000)
    n = lambda c: m.call(PSYMS['light_is_neutral'], a0=c, count=2000)
    expect(f(BLACK) == PAPER and f(WHITE) == INK and f(0x80000000 | 0x808080) == 0x80000000 | (L.flip_v(0x80) * 0x010101), f'black -> {PAPER:#x}, white -> {INK:#x}, alpha kept')
    expect(L.PAPER == 0xf4 and L.INK == 0x16 and L.SPREAD == 16 and L.CHROMA == 40 and L.GLYPH == 0xa0 and L.SURFACE == 4, 'q2-pod\'s numbers: paper F4, ink 16, spread 16, chroma 40, glyph A0, surface 4')
    bad = []
    for g in range(256):    # every grey
        c = 0xff000000 | g * 0x010101
        if f(c) != word(L.flip((g, g, g, 255))): bad.append(g)
    expect(not bad, f'every grey flips as the model flips it ({bad[:5]})')
    expect([L.flip_v(v) for v in (0, 255)] == [L.PAPER, L.INK] and all(L.flip_v(v) >= L.flip_v(v + 1) for v in range(255)), 'the flip is monotone and decreasing: dark becomes light')
    bad = []
    for r, g, b in ((0x1c, 0x1c, 0x1e), (0xaa, 0xaa, 0xaa), (0x4a, 0x4a, 0x4e), (0x77, 0x77, 0x77), (255, 80, 60), (0x20, 0x40, 0x90), (100, 100, 116), (100, 100, 117), (100, 116, 100), (100, 117, 100),
                    (0, 0, 16), (0, 0, 17), (16, 0, 0), (255, 255, 239), (255, 255, 240), (0, 17, 0), (15, 31, 31), (0, 255, 0), (255, 0, 255)):
        for a in (255, 128, 1):
            c = r | g << 8 | b << 16 | a << 24
            if f(c) != word(L.flip((r, g, b, a))) or n(c) != int(L.neutral((r, g, b))): bad.append((r, g, b, a))
    expect(not bad, f'greys with a tint, the edge of the spread and other hues: the C and the model agree ({bad[:4]})')
    expect(L.neutral((100, 100, 116)) and not L.neutral((100, 100, 117)) and f(0xff000000 | 117 << 16 | 100 << 8 | 100) == 0xff000000 | 117 << 16 | 100 << 8 | 100,
           'a colour is neutral when its channels are within 16 of each other; a hue beyond that stays as it is')
    # ui_ink: the payload's own colours
    off = LM()
    expect(off.call(PSYMS['ui_ink'], a0=BLACK, count=3000) == BLACK, 'ui_ink is the identity while Light Mode is off')
    on = LM(b'2\n')
    expect(on.call(PSYMS['ui_ink'], a0=BLACK, count=3000) == PAPER and on.call(PSYMS['ui_ink'], a0=WHITE, count=3000) == INK, 'ui_ink flips a neutral colour in Light Mode')
    expect(on.call(PSYMS['ui_ink'], a0=0x00112233, count=3000) == 0x00112233 and on.call(PSYMS['ui_ink'], a0=0x00000000, count=3000) == 0, 'a clear colour (alpha 0) stays clear: stock tests for it')
    expect(on.call(PSYMS['ui_ink'], a0=0xff2060ff, count=3000) == 0xff2060ff, 'ui_ink keeps a hue')
    # pal_map: the one entry point (background, then accent); the C against tools/palette.py map_colour
    pm = lambda mach, c: mach.call(PSYMS['pal_map'], a0=c, count=3000)
    bad = [c for c in (BLACK, WHITE, 0xff1c1c1e, 0xff333333, 0xff2060ff, 0x80808080, 0x00ffffff)
           if pm(off, c) != word(L.map_colour(px(c))) or pm(on, c) != word(L.map_colour(px(c), 'light'))]
    expect(not bad, f'pal_map(Black, Neutral) is the identity and pal_map(Light, Neutral) is the flip, as the model says ({bad[:4]})')
    expect(off.call(PSYMS['pal_active'], count=3000) == 0 and off.call(PSYMS['pal_background'], count=3000) == 0 and off.call(PSYMS['pal_accent'], count=3000) == 0
           and on.call(PSYMS['pal_active'], count=3000) == 1 and on.call(PSYMS['pal_background'], count=3000) == 1, 'the palette is inactive for Black + Neutral and active in Light Mode')
    expect(LM(b'2\n', kill=True).call(PSYMS['pal_active'], count=3000) == 0 and LM(b'2\n', bad=True).call(PSYMS['pal_active'], count=3000) == 0, 'the kill switch and the bad-boot note make it inactive')
    # the model
    expect(L.flip((0, 0, 0)) == (L.PAPER,) * 3 and L.ink((1, 2, 3, 0)) == (1, 2, 3, 0) and L.ink((0, 0, 0, 255)) == (L.PAPER,) * 3 + (255,), 'tools/palette.py: flip and ink')
    expect(L.plain('np_play') and not L.plain('file:///mnt/mmc/a.jpg') and not L.plain('images/x') and not L.plain('') and not L.plain('a:b'), 'a theme asset\'s name has no / and no :')


def style_tests(ctx):
    """style_get_color and style_get_gradient: stock's code under the hooks, over fake styles."""
    expect = ctx.expect
    # light on
    m = LM(b'2\n', hook=True)
    s = m.style(color=WHITE)
    expect(m.color(s, 'text_color') == INK and ('get_color', s) in m.calls, 'a style with no gradient: stock\'s get_color slot answers white, the hook flips it once to ink')
    expect(m.color(m.style(color=BLACK)) == PAPER, 'black becomes paper')
    expect(m.color(m.style(color=0xff2060ff)) == 0xff2060ff, 'a hue stays')
    expect(m.color(m.style(color=0x00000000)) == 0 and m.color(m.style(color=0x00ffffff)) == 0x00ffffff, 'a clear colour stays clear (Now Playing\'s dragger tests for it)')
    expect(m.color(m.style(color=WHITE), 'selected_text_color') == WHITE, '`selected_text_color` is never mapped (a text input\'s pending letter on its light blue selection)')
    expect(m.color(m.style(color=WHITE), 'text_color_selected') == INK and m.color(m.style(color=WHITE), 'highlight_text_color') == INK, 'the other text colours are')
    s = m.style(color=0xff808080, grads=[BLACK, 0xff202020])
    c = m.color(s)
    expect(c == PAPER and ('get_gradient', s) in m.calls, 'a style with a gradient: style_get_color takes its first colour, black, and the colour hook flips it once')
    expect(m.gradient(s)[1] == [PAPER, L.flip((0x20, 0x20, 0x20, 255)) and word(L.flip((0x20, 0x20, 0x20, 255)))], 'style_get_gradient called by another caller (widget_fill_rect) flips every stop')
    expect(m.gradient(s)[0] is True, 'it returns the out pointer it was given')
    grads = m.grads[s]
    m.gradient(s)
    expect(m.grads[s] == grads, 'the style\'s own data is not touched')
    expect(m.gradient(m.style(grads=None)) == (0, []) and m.gradient(0) == (0, []) and m.call(PSYMS['m1plus_style_gradient'], a0=m.alloc(8), a1=0, a2=0, count=2000) == 0,
           'style_get_gradient: a style with no get_gradient slot, a null style and a vtable-less one answer 0, as the leaf did')
    z = m.alloc(8)
    expect(m.call(PSYMS['m1plus_style_gradient'], a0=z, a1=0, a2=0, count=2000) == 0, 'a style whose vtable pointer is null: 0')
    stops = [WHITE, 0x00ffffff, 0xff2060ff] + [0xff000000] * 7    # more stops than the gradient holds: the caller's gradient_t has 8
    s = m.style(grads=stops)
    _, got = m.gradient(s)
    expect(len(got) == 8 and got[0] == INK and got[1] == 0x00ffffff and got[2] == 0xff2060ff and got[3] == PAPER, 'a gradient: neutral stops flip, a clear one and a hue stay, at most 8 stops')
    # nested: a mutable style asks again
    m = LM(b'2\n', hook=True)
    inner = m.style(color=WHITE)
    outer = m.nested(inner)
    expect(m.color(outer) == INK, 'a mutable style (its get_color asks again through the hook) is mapped once, not twice (a second flip would give E1)')
    expect(INK == 0xff161616 and word(L.flip(px(INK))) == 0xffe1e1e1, 'the flip is not idempotent: 16 would flip to E1')
    inner_g = m.style(color=0xff808080, grads=[BLACK])
    outer_g = m.nested(inner_g)
    expect(m.color(outer_g) == PAPER, f'the nested style with a gradient: the first colour of the gradient (black), flipped once ({m.color(outer_g):#x})')
    # off: every path is stock's
    for label, kw in (('no file', {}), ('"0"', {'mode': b'0\n'}), ('the kill switch', {'mode': b'2\n', 'kill': True}), ('the bad-boot note', {'mode': b'2\n', 'bad': True}), ('an unknown mode', {'mode': b'7\n'})):
        m = LM(hook=True, **kw)
        s = m.style(color=WHITE, grads=None)
        g = m.style(color=0xff808080, grads=[BLACK, WHITE])
        expect(m.color(s) == WHITE and m.color(g) == BLACK and m.gradient(g)[1] == [BLACK, WHITE], f'{label}: style_get_color and style_get_gradient answer what stock does')
    # exempt windows
    m = LM(b'2\n', hook=True)
    s = m.style(color=WHITE)
    m.on_top('screensaver_page')
    expect(m.color(s) == WHITE and m.gradient(m.style(grads=[BLACK]))[1] == [BLACK], 'the lock screen is on top: the style hooks pass through')
    for name in L.EXEMPT:
        m.on_top(name)
        expect(m.color(s) == WHITE, f'{name}: exempt')
    for name in ('home_page', 'm1plus_settings_page', 'playing_page', 'm1plus_dailymix_page', 'screensaver_page2', 'm1plus_ipod', '', 'm1plus_ipod_page2'):
        m.on_top(name)
        expect(m.color(s) == INK, f'{name!r}: not exempt')
    m.top_main = 0
    expect(m.color(s) == INK, 'no top window: not exempt')
    m.on_top('m1plus_tape_page')
    expect(m.color(s) == WHITE, 'a window that was exempt and a new one that is: found again')
    w = m.top_main
    m.setword(w + 0x10, m.cstr('home_page'))
    expect(m.color(s) == INK, 'the same window with another name pointer is looked at again')
    # costs: a style call in the default state
    m = LM(b'2\n', hook=True).count()
    s = m.style(color=WHITE)
    m.color(s)
    c1 = m.icount
    m.color(s)
    expect(c1 < 950, f'a style call costs {c1} instructions with Light Mode on (stock\'s own part included)')
    m = LM(hook=True).count()
    s = m.style(color=WHITE); m.color(s); c0 = m.icount
    expect(c0 < 650, f'and {c0} with it off')


def image_tests(ctx):
    """image_manager_add: which decoded images flip, and how; the C against tools/palette.py on the whole built tree."""
    expect = ctx.expect
    on = LM(b'2\n')
    g = glyph_image()
    out = on.image('np_play', 16, 16, g)
    expect(out == fl(g) and out[8 * 16 + 8][:3] == (L.INK,) * 3 and out[0][3] == 0,
           'a white glyph on nothing (mostly clear) flips: the glyph turns ink, the clear pixels stay clear')
    d = disc_image()
    expect(on.image('np_disc', 16, 16, d) == d, 'a grey disc under a white mark keeps its white mark (a dark plate: more than 1/4 of the area dark and opaque)')
    col = [(255, 80, 40, 255)] * 256
    expect(on.image('np_red', 16, 16, col) == col, 'an image with colour (a pixel more than LIGHT_CHROMA saturated) stays')
    expect(on.image('tape_shell_normal', 16, 16, g) == g and on.image('ipod_wheel', 16, 16, g) == g and on.image('np_shadow', 16, 16, g) == g and on.image('lk_card', 16, 16, g) == g,
           'the KEEP names (the cassette, the Pod, the cover shadow, the lock screen card) stay whatever they are')
    for nm in ('file:///mnt/mmc/.m1plus/covers/a.jpg', 'images/xx/np_play', '/tmp/coverpic.jpg', 'a:b', 'a/b'):
        expect(on.image(nm, 16, 16, g) == g, f'{nm}: a path or URL is a cover, never changed')
    plate = [(0x1c, 0x1c, 0x1c, 255)] * 256
    expect(on.image('pod_cd_single', 16, 16, plate) == fl(plate) and on.image('pod_cd_mid_down', 16, 16, plate) == fl(plate),
           'a WHOLE plate (the settings cards) flips every pixel although it is mostly dark and opaque')
    mixed = [(0x1c, 0x1c, 0x1c, 255), (255, 80, 40, 255), (255, 255, 255, 128), (0, 0, 0, 0)] * 64
    expect(on.image('pc_sheet1', 16, 16, mixed) == fl(mixed, True), 'a WHOLE image keeps a hue and flips the neutral pixels (alpha kept)')
    bgra = on.image('np_play', 16, 16, g, fmt=3)
    expect(bgra == fl(g), 'format 3 (BGRA) flips the same colour channels')
    for fmt in (2, 4):
        expect(on.image('np_play', 16, 16, g, fmt=fmt) == fl(g), f'format {fmt}')
    ss = [(200, 200, 200, 255)] * 4 + [(0, 0, 0, 0)] * 60
    expect(on.image('x_img', 8, 8, ss) == fl(ss), 'a light grey glyph also flips')
    # premultiplied alpha: the straight colour flips, the stored value follows
    half = [(100, 100, 100, 128)] * 4 + [(0, 0, 0, 0)] * 60
    got = on.image('x_half', 8, 8, half, premul=True)
    exp = round(L.flip_v(199) * 128 / 255)   # the straight colour of a stored 100 at alpha 128 is 199
    expect(abs(got[0][0] - exp) <= 1 and got[0][3] == 128 and got[4] == (0, 0, 0, 0), f'a premultiplied pixel: its straight colour flips and is stored premultiplied again ({got[0]}, wanted about {exp}), a clear one stays')
    # off
    for label, kw in (('off', {}), ('the kill switch', {'mode': b'2\n', 'kill': True})):
        m = LM(**kw)
        expect(m.image('np_play', 16, 16, g) == g, f'{label}: nothing changes')
    m = LM(b'2\n')
    m.image('np_play', 16, 16, g)
    expect(('stock_image_add', 1) not in m.calls and sum(c[0] == 'stock_image_add' for c in m.calls) == 1, 'stock\'s image_manager_add always runs, once, after the flip')
    # odd bitmaps: a null name, an unknown format, no buffer, a huge size, a short line: stock's add is called and nothing is read
    m = LM(b'2\n')
    b = m.malloc(0x48); m.u.mem_write(b, bytes(0x48))
    m.setword(b, 16); m.setword(b + 4, 16); m.u.mem_write(b + O['BITMAP_FORMAT'], struct.pack('<H', 6))   # format 6: not RGBA
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=m.cstr('np_play'), a2=b, count=40000)
    expect(sum(c[0] == 'stock_image_add' for c in m.calls) == 1 and 'bitmap_lock_buffer_for_write' not in [c[0] for c in m.calls], 'a bitmap that is not 32 bit is left alone')
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=0, a2=b, count=40000)
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=m.cstr('np_play'), a2=0, count=40000)
    expect(sum(c[0] == 'stock_image_add' for c in m.calls) == 1 and 'bitmap_lock_buffer_for_write' not in [c[0] for c in m.calls], 'a null name or a null bitmap goes straight to stock')
    m.setword(b + 0x14, 0)
    m.u.mem_write(b + O['BITMAP_FORMAT'], struct.pack('<H', 1)); m.setword(b, 5000)
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=m.cstr('np_play'), a2=b, count=40000)
    expect('bitmap_lock_buffer_for_write' not in [c[0] for c in m.calls], 'an image wider than 4096 is left alone')
    # the whole built tree: every image up to a size, the C against the model
    d = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    from PIL import Image
    names = sorted(f[:-4] for f in os.listdir(d) if f.endswith('.png'))
    bad, how, n = [], {None: 0, 'glyph': 0, 'whole': 0}, 0
    big = []
    for nm in names:
        im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
        if im.width * im.height > 40000: big.append(nm); continue
        pixels = list(im.getdata())
        want = L.flip_image(nm, im)
        kind = L.image_flips(nm, im)
        how[kind] += 1
        heap0 = on.heap   # (the emulated heap is bump-allocated: give each image's buffers back)
        got = on.image(nm, im.width, im.height, pixels)
        on.heap = heap0
        n += 1
        if got != list(want.getdata()): bad.append((nm, kind, next((i, pixels[i], got[i], want.getdata()[i]) for i in range(len(got)) if got[i] != want.getdata()[i])))
    expect(not bad, f'{n} images of the built tree through the C match tools/palette.py pixel for pixel ({bad[:6]})')
    expect(how['glyph'] > 100 and how['whole'] >= 10 and how[None] > 100, f'the tree has glyphs that flip, plates that flip whole and images that stay ({how}); {len(big)} larger ones are checked by the model only')
    # one image at 300 x 52 (a card piece) really through the C, to see its cost
    cp = Image.open(os.path.join(d, 'pod_cd_single.png')).convert('RGBA')
    m = LM(b'2\n').count()
    m.image('pod_cd_single', cp.width, cp.height, list(cp.getdata()))
    expect(m.icount < 2500000, f'a 320 x 52 card piece costs {m.icount} instructions once, when it is decoded')


def model_tests(ctx):
    """tools/palette.py against the tree: the name lists name something, the exempt names are windows, KEEP and WHOLE do not overlap."""
    expect = ctx.expect
    d = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    names = [f[:-4] for f in os.listdir(os.path.join(d, 'images', 'xx')) if f.endswith('.png')]
    for lst, label in ((L.KEEP, 'KEEP'), (L.WHOLE, 'WHOLE')):
        dead = [p for p in lst if not any(n.startswith(p) for n in names)]
        expect(not dead, f'every {label} prefix matches an image of the tree ({dead})')
    expect(not [n for n in names if n.startswith(L.KEEP) and n.startswith(L.WHOLE)], 'no image is both kept and flipped whole')
    roots = set()
    for f in os.listdir(os.path.join(d, 'ui')):
        if f.endswith('.bin'):
            root = awtk_ui.parse(open(os.path.join(d, 'ui', f), 'rb').read())
            roots.add(root.name)
    missing = [n for n in L.EXEMPT + L.COVER_PAGES if n not in roots]
    expect(not missing, f'every exempt and cover-tinted window name is the root widget of a page asset ({missing})')
    stock_h = open(os.path.join(BUILD, 'stock.h')).read()
    for macro, lst in (('LIGHT_KEEP', L.KEEP), ('LIGHT_WHOLE', L.WHOLE), ('LIGHT_EXEMPT', L.EXEMPT), ('LIGHT_COVER', L.COVER_PAGES)):
        line = next((l for l in stock_h.splitlines() if l.startswith(f'#define {macro} ')), '')
        expect(line == f'#define {macro} "' + ''.join(n + '\\0' for n in lst) + '"', f'{macro} in the generated header is tools/palette.py\'s list')
    expect(L.DAY_FROM == O['LIGHT_FROM'] == 7 and L.DAY_UNTIL == O['LIGHT_UNTIL'] == 19, 'Auto is light from 7 to 19')


def setting_tests(ctx):
    """The setting: read, saved atomically, applied at once; Auto's clock, one timer."""
    expect = ctx.expect
    mode = lambda m: m.call(PSYMS['pal_bg_mode'], count=20000)
    on = lambda m: m.call(PSYMS['pal_light'], count=20000)
    for data, want in ((None, 0), (b'0\n', 0), (b'0', 0), (b'1\n', 1), (b'1', 1), (b'2\n', 2), (b'2', 2), (b'3\n', 3), (b'3', 3), (b'4\n', 0), (b'', 0), (b'x', 0), (b'11', 0), (b'1\n\n', 0), (b'12', 0), (b' 1\n', 0), (b'\x001', 0), (b'-1', 0)):
        m = LM(data, hook=True)
        expect(mode(m) == want and m.fs.get(BG_FILE) == data, f'saved {data!r}: mode {want}, and reading writes nothing')
    m = LM(b'2\n', hook=True)
    expect(on(m) == 1 and not any(c[0] in ('write', 'rename') for c in m.calls) and m.timers == [(m.timers[0][0], O['LIGHT_TICK_MS'])], 'reading writes nothing; with the mode On there is one timer, a minute')
    expect(on(m) == 1 and len(m.timers) == 1, 'the second look reads nothing and arms nothing')
    m = LM(hook=True)
    expect(on(m) == 0 and m.timers == [] and not any(c[0] == 'timer_add' for c in m.calls), 'Off: no timer')
    expect(LM(b'2\n', kill=True).call(PSYMS['pal_light'], count=20000) == 0 and LM(b'2\n', bad=True).call(PSYMS['pal_light'], count=20000) == 0, 'the kill switch and the bad-boot note turn it off')
    k = LM(b'2\n', hook=True); k.present.add(KILL_FLASH)
    expect(on(k) == 0, 'the flash kill switch too')
    # Auto: 1800000000 is 08:00 UTC
    for hour, want in ((0, 0), (6, 0), (7, 1), (8, 1), (12, 1), (18, 1), (19, 0), (23, 0)):
        m = LM(b'3\n', hook=True); m.wall = 1800000000 + (hour - 8) * 3600 + 59 * 60
        expect(on(m) == want, f'Auto at {hour}:59: {"light" if want else "dark"}')
    m = LM(b'3\n', hook=True); m.wall = 100
    expect(on(m) == 0, 'Auto with a clock that is not set (1970): dark')
    m = LM(b'3\n', hook=True); m.tz = 3600 * 12; m.wall = 1800000000
    expect(on(m) == 0, 'Auto follows localtime, not UTC (08:00 UTC at +12 is 20:00)')
    # the tick: Auto crosses 19:00; the kill switch appears; the setting is read once only
    m = LM(b'3\n', hook=True); m.wall = 1800000000 + 10 * 3600 + 59 * 60 + 30     # 18:59:30
    expect(on(m) == 1, 'Auto at 18:59')
    cb = m.timers[0][0]
    m.calls = []; m.call(cb, a0=0, count=200000)
    expect(on(m) == 1 and m.unloads == 0, 'a tick inside the day changes nothing (no unload)')
    m.wall += 60
    r = m.call(cb, a0=0, count=200000)
    calls = list(m.calls)
    expect(r == O['RET_REPEAT'] and on(m) == 0 and m.unloads == 1 and ('widget_invalidate_force', m.wm) in calls, 'the tick at 19:00 turns it off: the cached images are dropped and the window manager repaints, the timer goes on')
    m.wall += 12 * 3600
    m.call(cb, a0=0, count=200000)
    expect(on(m) == 1 and m.unloads == 2, 'and at 7:00 it turns on again')
    m.present.add(KILL_SD)
    m.call(cb, a0=0, count=200000)
    expect(on(m) == 0 and m.unloads == 3, 'the kill switch appearing while it runs turns it off at the next tick')
    # pal_bg_set (0 Black, 1 Tinted, 2 Light, 3 Light Auto)
    m = LM(hook=True)
    r = m.call(PSYMS['pal_bg_set'], a0=2, count=2000000)
    calls = list(m.calls)
    expect(r == 2 and m.fs.get(BG_FILE) == b'2\n' and BG_FILE + '.tmp' not in m.fs and ('rename', BG_FILE + '.tmp', BG_FILE) in calls and ('fsync', '/mnt/data/m1plus') in calls,
           'pal_bg_set(2) is written atomically (temp file, fsync, rename, directory fsync)')
    expect(on(m) == 1 and mode(m) == 2 and m.unloads == 1 and ('widget_invalidate_force', m.wm) in calls and len(m.timers) == 1, 'and applied at once: the images dropped, the screen repainted, one timer')
    m.calls = []
    m.call(PSYMS['pal_bg_set'], a0=2, count=2000000)
    expect(m.unloads == 1 and len(m.timers) == 1, 'choosing the mode it is in drops nothing and arms nothing')
    r = m.call(PSYMS['pal_bg_set'], a0=3, count=2000000)
    expect(r == 3 and m.fs[BG_FILE] == b'3\n' and mode(m) == 3 and len(m.timers) == 1, 'Light Auto: saved; the timer is the one there is')
    r = m.call(PSYMS['pal_bg_set'], a0=0, count=2000000)
    calls = list(m.calls)
    expect(r == 0 and m.fs[BG_FILE] == b'0\n' and on(m) == 0 and mode(m) == 0 and m.unloads == 2 and ('timer_remove', 0x777) in calls, 'Black: saved, applied (images dropped) and the timer removed')
    r = m.call(PSYMS['pal_bg_set'], a0=2, count=2000000)
    expect(len(m.timers) == 2 and on(m) == 1, 'Light again arms a new timer')
    for bad in (-1, 4, 99):
        before = (m.fs[BG_FILE], m.unloads)
        expect(m.call(PSYMS['pal_bg_set'], a0=bad & 0xffffffff, count=2000000) == 0xffffffff and (m.fs[BG_FILE], m.unloads) == before and mode(m) == 2, f'pal_bg_set({bad}) is refused and changes nothing')
    m = LM(b'2\n', hook=True); m.fail.add(('write', BG_FILE + '.tmp'))
    expect(m.call(PSYMS['pal_bg_set'], a0=0, count=2000000) == 0xffffffff and m.fs.get(BG_FILE) == b'2\n' and BG_FILE + '.tmp' not in m.fs and mode(m) == 2 and on(m) == 1 and m.unloads == 0,
           'a failed write changes neither the file nor the mode')
    m = LM(b'2\n', hook=True); m.fail.add(('rename', BG_FILE))
    expect(m.call(PSYMS['pal_bg_set'], a0=3, count=2000000) == 0xffffffff and m.fs.get(BG_FILE) == b'2\n' and mode(m) == 2, 'a failed rename changes neither')
    m = LM(b'2\n', hook=True); m.timer_fail = True
    expect(on(m) == 1 and m.timers == [], 'a timer that cannot be made leaves the mode as read (no Auto switching, no kill switch re-check)')
    # tinted pages: the neutral tone
    off, lit = LM(hook=True), LM(b'2\n', hook=True)
    tone = 0xff203040
    expect(off.call(PSYMS['pal_tone'], a0=tone, count=2000) == tone and lit.call(PSYMS['pal_tone'], a0=tone, count=2000) == O['NP_NEUTRAL'] == 0xff202020,
           'pal_tone: the tone as it is, or in Light Mode the page\'s neutral colour (which the style hook then flips)')
    # no work at paint: with the mode Off the image hook and the style hook do not look at the window manager
    m = LM(hook=True)
    s = m.style(color=WHITE); m.color(s)
    expect(not any(c[0] == 'get_top_main_window' for c in m.calls), 'with Light Mode off the style hook never asks the window manager for its top window')


def settings_tests(ctx):
    """The Background picker (Settings > System > Appearance > Background, m1plus_background): Black and Tinted (Light stays out of the picker), a tap saves, applies and moves the check."""
    expect, P = ctx.expect, pod_pages
    B, W, V = P.BG_PAGE, P.APPEARANCE_PAGE, P.SETTINGS_PAGE
    expect(not any(r.action in (P.ACT_BG, P.ACT_BGSET) for p in P.PAGES for r in p.rows if p not in (B, W)) and 'Light Mode' not in [r.label for r in V.rows], 'only the Appearance page links the picker; no Light Mode row anywhere')
    expect(P.ACT_BG in P.VALUE_ACTIONS and P.ACT_BGSET in P.CHECK_ACTIONS and P.PAGES[P.BG_PAGE_INDEX] is B, 'the picker page and its actions')
    expect([(r.label, r.action, r.arg) for r in B.rows] == [('Black', P.ACT_BGSET, 0), ('Tinted', P.ACT_BGSET, 1)] and B.title == 'Background' and B.key == 'm1plus_background'
           and P.BG_VALUES == ('Black', 'Tinted') and all(P.row_kind(r) == 'check' for r in B.rows) and not [x for x in B.layout if isinstance(x, P.Note)],
           'the picker: Black and Tinted in the saved order, titled Background, a check each, no Light')
    expect([(r.label, r.action, r.arg) for r in W.rows][:2] == [('Background', P.ACT_BG, P.BG_PAGE_INDEX), ('Accent', P.ACT_ACCENT, P.ACCENT_PAGE_INDEX)] and P.row_kind(W.rows[0]) == 'value',
           'the Appearance page: the Background value row above the Accent one (the Control Center link follows in its own card, test/pod/pdtiles.py)')

    def open_pick(data=None, acc=None):
        m = LM(acc=acc)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(2)] + [f'pod_check{i}' for i in range(2)])}
        if data is not None: m.fs[BG_FILE] = data
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_BG); m.setword(row + 8, P.BG_PAGE_INDEX)
        m.call(PSYMS['on_row'], a0=row, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    m = open_pick()
    expect(('window_open', B.key) in m.calls and BG_FILE not in m.fs and [shown(m, i) for i in range(2)] == [1, 0], 'the picker opens with the check on Black, saving nothing')
    expect([[shown(open_pick(d), i) for i in range(2)] for d in (b'1\n', b'0\n', b'9', b'2\n')] == [[0, 1], [1, 0], [1, 0], [0, 0]], 'a saved Tinted has the check; an invalid file is Black; Light (not offered) checks neither')
    m = open_pick(acc=b'4\n')
    for want_file, k in ((b'1\n', 1), (b'0\n', 0), (b'1\n', 1)):
        n0 = m.unloads
        m.click(f'pod_row{k}')
        expect(m.fs.get(BG_FILE) == want_file and BG_FILE + '.tmp' not in m.fs and ('rename', BG_FILE + '.tmp', BG_FILE) in m.calls and [shown(m, i) for i in range(2)] == [int(i == k) for i in range(2)] and m.unloads == n0 + 1,
               f'a tap on {B.rows[k].label}: written atomically ({m.fs.get(BG_FILE)!r}), applied at once (images dropped), the check follows')
    m = open_pick(b'1\n', acc=b'4\n'); m.fail.add(('write', BG_FILE + '.tmp')); m.click('pod_row0')
    expect(m.fs.get(BG_FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls) and m.unloads == 0, 'a failed write changes neither the file, the check nor the screen')
    # the Appearance page shows the saved background and accent
    def values(data, acc):
        m = LM(acc=acc)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(2)] + [f'pod_value{i}' for i in range(2)] + [f'pod_label{i}' for i in range(2)])}
        if data is not None: m.fs[BG_FILE] = data
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.APPEARANCE_PAGE_INDEX)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return [[c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'pod_value{i}']] for i in range(2)]
    expect([values(d, a) for d, a in ((None, None), (b'1\n', b'1\n'), (b'2\n', b'6\n'), (b'7', None))] == [[['Black'], ['Neutral']], [['Tinted'], ['Red']], [['Black'], ['Champagne']], [['Black'], ['Neutral']]],
           'the Appearance rows show the saved background and accent (Black for no, invalid or Light)')
    # the assets
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    tree = awtk_ui.parse(open(os.path.join(raw, 'm1plus_background.bin'), 'rb').read())
    expect(all(tree.find(f'pod_check{i}').get('visible') == 'false' and tree.find(f'pod_check{i}').get('sensitive') == 'false' and tree.find(f'pod_row{i}').find('pod_icon') is None for i in range(2))
           and tree.find('label_title').get('tr_text') == 'Background', 'the picker asset: two rows without a glyph, a hidden insensitive check each')
    st = awtk_ui.parse(open(os.path.join(raw, 'm1plus_appearance.bin'), 'rb').read())
    expect(st.find('pod_row0').find('pod_icon').get('image') == 'pod_ci_contrast' and st.find('pod_value0').get('tr_text') == 'Black' and st.find('pod_row1').find('pod_icon').get('image') == 'pod_ci_palette'
           and st.find('pod_value1').get('tr_text') == 'Neutral', 'the Appearance page asset: Background (contrast glyph, "Black") above Accent (palette glyph, "Neutral")')


def rgba(rgb, a=255):
    return (rgb >> 16, rgb >> 8 & 255, rgb & 255, a)


ROLE_WORDS = [word(rgba(L.ROLE_PRESS_ROW)), word(rgba(L.ROLE_PRESS_ROW, 0x80)), word(rgba(L.ROLE_PROGRESS, 0xeb)), word(rgba(L.ROLE_PROGRESS)), word(rgba(L.ROLE_PROGRESS, 0)),
              word(rgba(L.ROLE_PRESS_PILL)), word(rgba(L.ROLE_PRESS_QPILL, 0x80))]
NEAR_WORDS = [word((0x33, 0x33, 0x33, 255)), word((0x33, 0x33, 0x36, 255)), word((0x3a, 0x3a, 0x3c, 255)), word((0x34, 0x33, 0x34, 255)), word((255, 255, 255, 0xeb)), word((0xff, 0xff, 0xfd, 0xeb)), word((0xee, 0xee, 0xec, 255)),
              BLACK, WHITE, 0xff1c1c1c, 0xff2060ff, 0x00000000]


def accent_map_tests(ctx):
    """pal_map and the hooks with every accent: the C against tools/palette.py; the role colours, and nothing else, change."""
    expect = ctx.expect
    expect(L.ACCENTS == ('neutral', 'red', 'orange', 'green', 'teal', 'purple', 'champagne') and O['ACC_COUNT'] == 7, 'seven accents in index order after Neutral')
    expect([L.ACCENT_RGB[a] for a in L.ACCENTS[1:]] == [(0xff, 0x45, 0x3a), (0xff, 0x9f, 0x0a), (0x30, 0xd1, 0x58), (0x40, 0xc8, 0xe0), (0xbf, 0x5a, 0xf2), (0xc8, 0xa9, 0x6a)], 'the user-approved values')
    expect(L.ROLE_PRESS_ROW == 0x333334 and L.ROLE_PROGRESS == 0xfffffe and O['LIST_PRESS'] == word(rgba(L.ROLE_PRESS_ROW)), 'the role colours: a pressed row #333334 (LIST_PRESS), the progress fill #FFFFFE')
    pal_map = lambda m, c: m.call(PSYMS['pal_map'], a0=c, count=20000)
    bad = []
    for i, ac in enumerate(L.ACCENTS):
        for bg, light in (('black', None), ('light', b'2\n')):
            m = LM(light, acc=b'%d\n' % i, hook=True)
            for c in ROLE_WORDS + NEAR_WORDS:
                want = word(L.map_colour(px(c), bg, ac))
                got = pal_map(m, c)
                if got != want: bad.append((ac, bg, hex(c), hex(got), hex(want)))
    expect(not bad, f'pal_map: every accent, both backgrounds, role and near-miss colours match the model ({bad[:4]})')
    for ac in L.ACCENTS[1:]:
        r, a = L.row_press(ac), L.ACCENT_RGB[ac]
        expect(L.map_colour((0x33, 0x33, 0x34, 255), 'black', ac) == r + (255,) and L.map_colour((255, 255, 254, 0xeb), 'black', ac) == a + (0xeb,), f'{ac}: row {r}, progress {a} (alpha kept)')
    expect(L.map_colour((0x33, 0x33, 0x34, 255), 'black', 'red') == (56, 15, 13, 255), 'Red: mix(black, #FF453A, 22 %) is #380F0D')
    expect(all(L.map_colour(px(c), 'black', 'neutral') == px(c) for c in ROLE_WORDS + NEAR_WORDS), 'Neutral maps nothing')
    # Black + Neutral: every path is stock's, the palette is not even active
    m = LM(hook=True)
    expect(m.call(PSYMS['pal_active'], count=20000) == 0 and all(pal_map(m, c) == c for c in ROLE_WORDS), 'Black + Neutral: pal_active is 0 and pal_map is the identity on the role colours')
    expect(m.color(m.style(color=ROLE_WORDS[0])) == ROLE_WORDS[0] and m.gradient(m.style(grads=[ROLE_WORDS[0]]))[1] == [ROLE_WORDS[0]], 'and the style hooks answer what stock does')
    expect(m.call(PSYMS['ui_ink'], a0=O['LIST_PRESS'], count=20000) == O['LIST_PRESS'], 'ui_ink leaves the pressed row')
    # the hooks
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        m = LM(acc=b'%d\n' % i, hook=True)
        row, prog = word(L.map_colour(px(ROLE_WORDS[0]), 'black', ac)), word(L.map_colour(px(ROLE_WORDS[2]), 'black', ac))
        s = m.style(color=ROLE_WORDS[0])
        ok = (m.call(PSYMS['pal_active'], count=20000) == 1 and m.color(s) == row and m.color(m.style(color=ROLE_WORDS[2]), 'fg_color') == prog and m.color(m.style(color=0xff333333)) == 0xff333333
              and m.gradient(m.style(grads=[ROLE_WORDS[0], WHITE]))[1] == [row, WHITE] and m.call(PSYMS['ui_ink'], a0=O['LIST_PRESS'], count=20000) == row
              and m.call(PSYMS['ui_ink'], a0=ROLE_WORDS[4], count=20000) == ROLE_WORDS[4])
        expect(ok, f'{ac}: style_get_color, style_get_gradient and ui_ink map a pressed row and the progress fill, #333333 stays, a clear colour stays clear')
    m = LM(acc=b'2\n', hook=True)
    outer = m.nested(m.style(color=ROLE_WORDS[0]))
    expect(m.color(outer) == word(L.map_colour(px(ROLE_WORDS[0]), 'black', 'orange')), 'a mutable style is mapped once with an accent too')
    # the exempt windows
    m = LM(acc=b'1\n', hook=True)
    s = m.style(color=ROLE_WORDS[0])
    for name in L.EXEMPT:
        m.on_top(name)
        expect(m.color(s) == ROLE_WORDS[0] and m.gradient(m.style(grads=[ROLE_WORDS[0]]))[1] == [ROLE_WORDS[0]], f'{name}: exempt from the accent as well')
    for name in ('playing_page', 'album_page', 'm1plus_dailymix_page', 'home_page'):
        m.on_top(name)
        expect(m.color(s) != ROLE_WORDS[0], f'{name}: takes the accent')
    # a cover tone: the page background (a chromatic dark tone of the cover, or the neutral grey) is never a role colour
    tones = [O['NP_NEUTRAL']] + [0xff000000 | (b << 16 | g << 8 | r) for r in range(0, 0x60, 0x10) for g in range(0, 0x60, 0x10) for b in range(0, 0x60, 0x10)]
    expect(not [t for t in tones if t & 0xffffff in (word(rgba(L.ROLE_PRESS_ROW)) & 0xffffff, word(rgba(L.ROLE_PROGRESS)) & 0xffffff, word(rgba(L.ROLE_PRESS_PILL)) & 0xffffff, word(rgba(L.ROLE_PRESS_QPILL)) & 0xffffff)], 'no cover-tone background (the neutral grey and a grid of dark tones) is a role colour: the pages stay as they are')
    # cost of a style call with an accent on
    m = LM(acc=b'1\n', hook=True).count()
    s = m.style(color=ROLE_WORDS[0]); m.color(s); m.color(s); c_role = m.icount   # (icount is the last call's)
    m.color(m.style(color=WHITE)); c_plain = m.icount
    expect(c_role < 900 and c_plain < 900, f'a style call costs {c_role} instructions on a role colour and {c_plain} on any other with an accent on (stock\'s own part included)')
    print(f'  style call with an accent: {c_role} (role colour), {c_plain} (other)')


def tint_check(d, names, mode, background, big=None):
    """The named tree images under every accent through the C against tools/palette.py's model:
    (mismatches, images checked, each image's instruction cost under the first accent).
    Images over big pixels are checked under the first two accents only."""
    from PIL import Image
    bad, n, costs = [], 0, {}
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        m = LM(mode, acc=b'%d\n' % i)
        for nm in names:
            im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
            if big and im.width * im.height > big and i > 2: continue
            pixels = list(im.getdata())
            heap0 = m.heap
            got = m.image(nm, im.width, im.height, pixels)
            m.heap = heap0
            if i == 1:   # (the instruction count is per machine: a fresh one per image, once)
                c = LM(mode, acc=b'1\n').count(); c.image(nm, im.width, im.height, pixels); costs[nm] = c.icount
            want = list(L.render_image(nm, im, background, ac).getdata())
            n += 1
            if got != want: bad.append((ac, nm, next((k, pixels[k], got[k], want[k]) for k in range(len(got)) if got[k] != want[k])))
    return bad, n, costs


def accent_image_tests(ctx):
    """The image hook with an accent: the tinted names pixel for pixel against the model, every other image untouched."""
    expect = ctx.expect
    from PIL import Image
    d = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    GLYPHS = tuple(sorted(f[:-4] for f in os.listdir(d) if f.startswith(L.ACCENT_GLYPH) and f.endswith('.png') and f[:-4] not in L.ACCENT_GLYPH_NOT)) + L.ACCENT_GLYPH_STOCK   # (the row glyphs, tinted by prefix, and the More sheet's stock ones by name)
    expect(len(GLYPHS) >= 60 and sum(g.startswith('pod_ci_') for g in GLYPHS) >= 30, f'{len(GLYPHS)} pod_ic_/fo_ic_/pod_ci_ glyph images in the tree ({sum(g.startswith("pod_ci_") for g in GLYPHS)} Settings card glyphs)')
    expect(not [g for g in GLYPHS if g.startswith('pod_sw')] and all(L.accent_kind(f'pod_sw{k}') is None for k in range(7)), 'the accent swatches pod_sw* are not glyphs (never tinted)')
    expect({'fo_ic_sd', 'fo_ic_usb', 'fo_ic_file'} <= set(GLYPHS), 'the Folders list\'s own glyphs are in the tinted set')
    expect(all(g in GLYPHS and os.path.exists(os.path.join(d, g + '.png')) for g in L.ACCENT_GLYPH_STOCK) and not {'pc_ic_unsub', 'selected'} & set(GLYPHS) and {'pc_ic_trash', 'pl_ic_delete', 'p_delete'} <= set(GLYPHS),
           'every stock glyph named for the accent is an image of the tree and in the tinted set, the delete rows\' glyphs too; the red unsubscribe glyph and the stock selected check are not')
    bad, n, costs = tint_check(d, L.ACCENT_ALL + GLYPHS, None, 'black')
    expect(not bad, f'{n} tinted images (every accent) through the C match tools/palette.py pixel for pixel ({bad[:4]})')
    worst = max(costs, key=costs.get)
    expect(costs[worst] < 12000000, f'the dearest tint ({worst}, {Image.open(os.path.join(d, worst + ".png")).size}) costs {costs[worst]:,} instructions once, when it is decoded')
    print('  accent image tint cost, instructions: ' + ', '.join(f'{k} {v:,}' for k, v in sorted(costs.items(), key=lambda kv: -kv[1])))
    # the tint is what the design says
    sw = Image.open(os.path.join(d, 'sset_on.png')).convert('RGBA')
    out = L.render_image('sset_on', sw, 'black', 'green')
    cx = [p for p in out.getdata() if p[3] == 255]
    expect((0x30, 0xd1, 0x58, 255) in cx and (255, 255, 255, 255) in cx and not any(p[:3] == (0xee, 0xee, 0xec) for p in cx), 'the switch on: an accent track and a white knob')
    for ac in L.ACCENTS[1:]:   # an ON tile: the white disc is the accent, the #141414 glyph stays dark (not white), the cut-out glyph of drop_wifiopen keeps its alpha
        px = {p[:3] for p in L.render_image('drop_btopen', Image.open(os.path.join(d, 'drop_btopen.png')), 'black', ac).getdata() if p[3] == 255}
        expect(L.ACCENT_RGB[ac] in px and (20, 20, 20) in px and (255, 255, 255) not in px, f'the ON tile under {ac}: the disc is the accent, the glyph stays #141414')
    pc = L.render_image('pod_cd_mid_down', Image.open(os.path.join(d, 'pod_cd_mid_down.png')), 'black', 'red')
    expect({p[:3] for p in pc.getdata() if p[3]} == {L.card_press('red')}, 'the pressed card piece is one colour, the card tinted')
    # names: all in the tree, none kept or flipped by Light's lists, no overlap
    names = {f[:-4] for f in os.listdir(d) if f.endswith('.png')}
    expect(all(nm in names for nm in L.ACCENT_ALL) and len(set(L.ACCENT_ALL)) == len(L.ACCENT_ALL), 'every accent image name is an image of the tree, once')
    expect(not [nm for nm in L.ACCENT_ALL if nm.startswith(L.KEEP)], 'no accent image is in KEEP')
    # everything else is untouched with an accent on, Light off and on
    for light in (None, b'2\n'):
        on = LM(light, acc=b'3\n')
        bad = []
        for nm in sorted(names - set(L.ACCENT_ALL) - set(GLYPHS)):
            im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
            if im.width * im.height > 4000: continue
            px_ = list(im.getdata())
            heap0 = on.heap
            got = on.image(nm, im.width, im.height, px_)
            on.heap = heap0
            want = list((L.flip_image(nm, im) if light else im).getdata())
            if got != want: bad.append(nm)
        expect(not bad, f'an accent on, Light {"on" if light else "off"}: the other images are as without the accent (flipped or not by Light alone) ({bad[:4]})')
    on = LM(b'2\n', acc=b'2\n')
    g = glyph_image()
    expect(on.image('np_play', 16, 16, g) == fl(g), 'Light + accent: a glyph still flips')
    # Black + Neutral: nothing is touched, whatever the name
    off = LM()
    im = Image.open(os.path.join(d, 'vol_progress.png')).convert('RGBA')
    px_ = list(im.getdata())
    expect(off.image('vol_progress', im.width, im.height, px_) == px_ and 'bitmap_lock_buffer_for_write' not in [c[0] for c in off.calls], 'Black + Neutral: a tinted name is not even locked')
    # premultiplied, formats, odd bitmaps
    half = [(238, 238, 236, 128)] * 4 + [(0, 0, 0, 0)] * 60
    m = LM(acc=b'1\n')
    got = m.image('np_row_playing', 8, 8, half, premul=True)
    exp = round(0xff * 128 / 255)   # the accent's red 255 at alpha 128, premultiplied
    expect(abs(got[0][0] - exp) <= 1 and got[0][3] == 128 and got[4] == (0, 0, 0, 0), f'a premultiplied pixel: tinted from its straight colour and stored premultiplied again ({got[0]})')
    g = [(238, 238, 236, 255)] * 4 + [(0, 0, 0, 0)] * 12
    want = L.accent_pixel('fill', g[0], 'red')
    for fmt in (1, 2, 3, 4):
        expect(LM(acc=b'1\n').image('pod_check', 4, 4, g, fmt=fmt)[0] == want, f'format {fmt}: the same tint')
    m = LM(acc=b'1\n')
    b = m.malloc(0x48); m.u.mem_write(b, bytes(0x48))
    m.setword(b, 16); m.setword(b + 4, 16); m.u.mem_write(b + O['BITMAP_FORMAT'], struct.pack('<H', 6))
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=m.cstr('pod_check'), a2=b, count=40000)
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=0, a2=b, count=40000)
    m.call(PSYMS['m1plus_image_add'], a0=1, a1=m.cstr('pod_check'), a2=0, count=40000)
    expect('bitmap_lock_buffer_for_write' not in [c[0] for c in m.calls], 'a bitmap that is not 32 bit, a null name and a null bitmap are left alone')
    # the cost of the hook on a name it does not tint (3600: the Equalizer's tall card pieces pod_cdl_* joined the lists, ~3500)
    m = LM(acc=b'1\n').count()
    n0 = m.icount; m.image('np_play', 2, 2, [(0, 0, 0, 0)] * 4); c = m.icount - n0
    expect(c < 3600, f'an image the accent does not tint costs {c} instructions through the hook (the name lists)')
    print(f'  hook on an untinted image: {c} instructions')


def accent_setting_tests(ctx):
    """The saved accent: read, saved atomically, applied at once, the kill switch and the bad-boot note, one timer."""
    expect = ctx.expect
    saved = lambda m: m.call(PSYMS['pal_accent_saved'], count=20000)
    eff = lambda m: m.call(PSYMS['pal_accent'], count=20000)
    for data, want in ((None, 0), (b'0\n', 0), (b'0', 0), (b'1\n', 1), (b'3', 3), (b'6\n', 6), (b'7\n', 0), (b'9', 0), (b'', 0), (b'x', 0), (b'33', 0), (b'3\n\n', 0), (b' 3\n', 0), (b'-1', 0), (b'\x003', 0)):
        m = LM(acc=data, hook=True)
        expect(saved(m) == want and eff(m) == want and m.fs.get(ACCENT_FILE) == data and not any(c[0] in ('write', 'rename') for c in m.calls), f'saved {data!r}: accent {want}, and reading writes nothing')
    m = LM(acc=b'2\n', hook=True)
    expect(m.timers == [] and eff(m) == 2 and m.timers == [(m.timers[0][0], O['LIGHT_TICK_MS'])] and eff(m) == 2 and len(m.timers) == 1, 'an accent arms the one timer (the kill switch is looked at each tick), once')
    expect(LM(hook=True).timers == [] and not any(c[0] == 'timer_add' for c in LM(hook=True).calls), 'Neutral: no timer')
    k = LM(acc=b'2\n', kill=True, hook=True); b = LM(acc=b'2\n', bad=True, hook=True); f = LM(acc=b'2\n', hook=True); f.present.add(KILL_FLASH)
    expect(eff(k) == 0 and eff(b) == 0 and eff(f) == 0 and saved(k) == 2 and k.call(PSYMS['pal_active'], count=20000) == 0, 'the SD kill switch, the flash one and the bad-boot note give Neutral (the saved choice stays)')
    expect(k.color(k.style(color=ROLE_WORDS[0])) == ROLE_WORDS[0], 'and the hooks are stock\'s')
    # pal_accent_set
    m = LM(hook=True)
    r = m.call(PSYMS['pal_accent_set'], a0=3, count=2000000)
    calls = list(m.calls)
    expect(r == 3 and m.fs.get(ACCENT_FILE) == b'3\n' and ACCENT_FILE + '.tmp' not in m.fs and ('rename', ACCENT_FILE + '.tmp', ACCENT_FILE) in calls and ('fsync', '/mnt/data/m1plus') in calls,
           'pal_accent_set(3) is written atomically (temp file, fsync, rename, directory fsync)')
    expect(saved(m) == 3 and eff(m) == 3 and m.unloads == 1 and ('widget_invalidate_force', m.wm) in calls and len(m.timers) == 1, 'and applied at once: the images dropped, the screen repainted, one timer')
    expect(m.color(m.style(color=ROLE_WORDS[0])) == word(L.map_colour(px(ROLE_WORDS[0]), 'black', 'green')), 'the next style call answers with the new accent')
    m.call(PSYMS['pal_accent_set'], a0=3, count=2000000)
    expect(m.unloads == 1 and len(m.timers) == 1, 'choosing the accent it is in drops nothing and arms nothing')
    r = m.call(PSYMS['pal_accent_set'], a0=6, count=2000000)
    expect(r == 6 and m.fs[ACCENT_FILE] == b'6\n' and eff(m) == 6 and m.unloads == 2 and len(m.timers) == 1, 'another accent: saved, applied, the timer is the one there is')
    r = m.call(PSYMS['pal_accent_set'], a0=0, count=2000000)
    calls = list(m.calls)
    expect(r == 0 and m.fs[ACCENT_FILE] == b'0\n' and eff(m) == 0 and m.unloads == 3 and ('timer_remove', 0x777) in calls, 'Neutral: saved, applied (images dropped) and the timer removed')
    expect(m.color(m.style(color=ROLE_WORDS[0])) == ROLE_WORDS[0] and m.call(PSYMS['pal_active'], count=20000) == 0, 'and the palette is inactive again')
    for bad in (-1, 7, 99):
        before = (m.fs[ACCENT_FILE], m.unloads)
        expect(m.call(PSYMS['pal_accent_set'], a0=bad & 0xffffffff, count=2000000) == 0xffffffff and (m.fs[ACCENT_FILE], m.unloads) == before and saved(m) == 0, f'pal_accent_set({bad}) is refused and changes nothing')
    m = LM(acc=b'1\n', hook=True); m.fail.add(('write', ACCENT_FILE + '.tmp'))
    expect(m.call(PSYMS['pal_accent_set'], a0=4, count=2000000) == 0xffffffff and m.fs.get(ACCENT_FILE) == b'1\n' and ACCENT_FILE + '.tmp' not in m.fs and saved(m) == 1 and eff(m) == 1 and m.unloads == 0,
           'a failed write changes neither the file nor the accent')
    m = LM(acc=b'1\n', hook=True); m.fail.add(('rename', ACCENT_FILE))
    expect(m.call(PSYMS['pal_accent_set'], a0=4, count=2000000) == 0xffffffff and m.fs.get(ACCENT_FILE) == b'1\n' and saved(m) == 1, 'a failed rename changes neither')
    # a round trip: what one boot saved the next reads
    m = LM(hook=True)
    m.call(PSYMS['pal_accent_set'], a0=5, count=2000000)
    n = LM(acc=m.fs[ACCENT_FILE], hook=True)
    expect(saved(n) == 5 and eff(n) == 5 and n.color(n.style(color=ROLE_WORDS[0])) == word(L.map_colour(px(ROLE_WORDS[0]), 'black', 'purple')) and n.call(PSYMS['pal_accent_color'], a0=5, count=2000) == word(rgba(0xbf5af2)),
           'a saved accent is the accent of the next boot')
    expect([m.call(PSYMS['pal_accent_color'], a0=i, count=2000) for i in (0, 1, 6, 7, 0xffffffff)] == [0xffeceeee, 0xff3a45ff, 0xff6aa9c8, 0xffeceeee, 0xffeceeee], 'pal_accent_color: opaque swatch words, Neutral and out-of-range give #EEEEEC')
    expect(m.call(PSYMS['pal_fill'], count=2000) == word(rgba(0xbf5af2)) and LM(hook=True).call(PSYMS['pal_fill'], count=2000) == 0xffeceeee, 'pal_fill: the accent, or Neutral\'s #EEEEEC')
    # the tick: the kill switch appears while an accent is on
    m = LM(acc=b'2\n', hook=True)
    expect(eff(m) == 2, 'accent 2')
    cb = m.timers[0][0]
    m.calls = []; m.call(cb, a0=0, count=200000)
    expect(eff(m) == 2 and m.unloads == 0, 'a tick changes nothing while nothing changed')
    m.present.add(KILL_SD)
    r = m.call(cb, a0=0, count=200000)
    calls = list(m.calls)
    expect(r == O['RET_REPEAT'] and eff(m) == 0 and m.unloads == 1 and ('widget_invalidate_force', m.wm) in calls, 'the kill switch appearing turns the accent off at the next tick: images dropped, repaint, the timer goes on')
    m.present.discard(KILL_SD)
    m.call(cb, a0=0, count=200000)
    expect(eff(m) == 2 and m.unloads == 2, 'and it comes back when the switch goes')
    # Light and the accent together: one timer, each setting can end without ending the other's
    m = LM(b'2\n', acc=b'4\n', hook=True)
    expect(eff(m) == 4 and m.call(PSYMS['pal_light'], count=20000) == 1 and len(m.timers) == 1, 'Light On + an accent: one timer')
    m.call(PSYMS['pal_bg_set'], a0=0, count=2000000)
    expect(len(m.timers) == 1 and ('timer_remove', 0x777) not in m.calls, 'Light Off keeps the timer for the accent')
    m.call(PSYMS['pal_accent_set'], a0=0, count=2000000)
    expect(('timer_remove', 0x777) in m.calls, 'and the accent Neutral then ends it')


def roles_tests(ctx):
    """The unique role colours: in the built theme and the payload they appear only in their role (the hooks see a colour, not the style it came from)."""
    expect = ctx.expect
    import re, awtk_style
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets')
    roles = {L.ROLE_PRESS_ROW: 'row', L.ROLE_PROGRESS: 'progress'}
    found = {k: [] for k in roles}
    for theme in sorted(os.listdir(raw)):
        sd = os.path.join(raw, theme, 'raw', 'styles')
        for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
            th = awtk_style.parse(open(os.path.join(sd, f), 'rb').read())
            for it in th.items:
                for k, t, v in it.props:
                    rgb = (v & 255) << 16 | (v >> 8 & 255) << 8 | (v >> 16 & 255) if t == awtk_style.T_UINT32 else None
                    if rgb in roles and awtk_style.is_color_key(k): found[rgb].append((theme, f, it.widget, it.style, it.state, k))
        ud = os.path.join(raw, theme, 'raw', 'ui')
        for f in sorted(f for f in os.listdir(ud) if f.endswith('.bin')) if os.path.isdir(ud) else []:
            root = awtk_ui.parse(open(os.path.join(ud, f), 'rb').read())
            for w in root.walk():
                for k, v in w.props:
                    if isinstance(v, str) and 'color' in k and re.fullmatch(r'#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?', v) and int(v[1:7], 16) in roles:
                        found[int(v[1:7], 16)].append((theme, f, w.name, k, v))
    rows = {r for r in found[L.ROLE_PRESS_ROW]}
    row_styles = sorted({(t, f, w, s, st) for t, f, w, s, st, k in rows})
    ok_styles = {('list_item', 'list_item_style'), ('list_item', 'list_itemsort_style'), ('button', 'btn_tablerow_style'), ('button', 'kb_btn1_style'), ('button', 'kb_btn2_style')}
    expect(all(t == 'default' and st == 'pressed' for t, f, w, s, st in row_styles) and all(k == 'bg_color' for *_, k in rows) and ok_styles <= {(w, s) for t, f, w, s, st in row_styles if f == 'default.bin'},
           f'#333334 is in the built styles only as the pressed background (the list rows, the table rows, the two keyboard keys, the Playlists page\'s row, the Search tabs) ({row_styles})')
    prog = found[L.ROLE_PROGRESS]
    expect(prog and all(p[2] == 'slider_play' and p[3].endswith(':fg_color') for p in prog) and {p[:2] for p in prog} == {('default', 'playing_page.bin')},
           f'#FFFFFE is in the built pages only as the Now Playing progress bar\'s fill ({prog})')
    # the payload's and the tools' sources: the colour words / literals appear only where they define the role
    srcs = {}
    for d in ('patch', 'tools'):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(('.c', '.h', '.inc', '.py')) and not f.startswith('preview'): srcs[f'{d}/{f}'] = open(os.path.join(ROOT, d, f)).read()
    pats = {'row': (r'0x[0-9a-fA-F]{2}343333u?\b', r'#333334'), 'progress': (r'0x[0-9a-fA-F]{2}feffffu?\b', r'#FFFFFE')}
    hits = {k: [(f, m.group(0)) for f, s in srcs.items() for p in v for m in re.finditer(p, s, re.I)] for k, v in pats.items()}
    allowed_row = {'patch/offsets.inc', 'tools/mod_theme.py', 'tools/pod_search.py', 'tools/palette.py', 'patch/palette.c'}
    allowed_prog = {'tools/mod_nowplaying.py', 'tools/palette.py', 'patch/palette.c'}
    for k, p, allowed in (('pill', r'0x[0-9a-fA-F]{2}353333u?\b|#333335', {'patch/offsets.inc', 'tools/pod_ui.py', 'tools/palette.py'}), ('qpill', r'0x[0-9a-fA-F]{2}3d3a3au?\b|#3A3A3D', {'patch/offsets.inc', 'tools/pod_ui.py', 'tools/palette.py'})):
        h = sorted({f for f, s in srcs.items() for _ in re.finditer(p, s, re.I)})
        expect(set(h) <= allowed, f'in the sources the {k} role colour is only where it is defined ({h})')
    expect({f for f, _ in hits['row']} <= allowed_row and {f for f, _ in hits['progress']} <= allowed_prog, f'in the sources the role colours are only where they are defined ({hits})')
    expect(O['LIST_PRESS'] == 0xff343333 and not [f for f, s in srcs.items() if re.search(r'LIST_PRESS\s*=|0xff333333u?', s) and f.endswith(('.c', '.h'))], 'the payload\'s own pressed rows use LIST_PRESS and no other grey spelling of it')
    # the other greys that are not roles: #333333 is the hairline, the track, the pill and the tile; nothing maps it
    expect(L.map_colour((0x33, 0x33, 0x33, 255), 'black', 'red') == (0x33, 0x33, 0x33, 255) and L.map_colour((0x2c, 0x2c, 0x2e, 255), 'black', 'red') == (0x2c, 0x2c, 0x2e, 255), 'hairlines, tracks, pills and tiles (#333333) and the old pressed card colour stay')
    # the generated header
    stock_h = open(os.path.join(BUILD, 'stock.h')).read()
    for macro, lst in (('ACCENT_FILL', L.ACCENT_FILL), ('ACCENT_SWITCH', L.ACCENT_SWITCH), ('ACCENT_PRESS', L.ACCENT_PRESS), ('ACCENT_DISC', L.ACCENT_DISC), ('ACCENT_GLYPH', L.ACCENT_GLYPH), ('ACCENT_GLYPH_NOT', L.ACCENT_GLYPH_NOT), ('ACCENT_TILE', L.ACCENT_TILE), ('ACCENT_GLYPH_STOCK', L.ACCENT_GLYPH_STOCK)):
        line = next((l for l in stock_h.splitlines() if l.startswith(f'#define {macro} ')), '')
        expect(line == f'#define {macro} "' + ''.join(n + '\\0' for n in lst) + '"', f'{macro} in the generated header is tools/palette.py\'s list')


def accent_picker_tests(ctx):
    """The Accent picker (Settings > System > Accent, m1plus_accent): the row, the page, a swatch per row, the check, a tap saves and applies at once."""
    expect, P = ctx.expect, pod_pages
    A, V, W = P.ACCENT_PAGE, P.SETTINGS_PAGE, P.APPEARANCE_PAGE
    names = ['Neutral', 'Red', 'Orange', 'Green', 'Teal', 'Purple', 'Champagne']
    row_i = next(i for i, r in enumerate(V.rows) if r.label == 'Appearance')
    expect([(r.label, r.action, r.arg) for r in A.rows] == [(n, P.ACT_ACCENTSET, i) for i, n in enumerate(names)] and A.title == 'Accent' and A.key == 'm1plus_accent' and P.ACCENT_VALUES == tuple(names)
           and tuple(n.capitalize() for n in L.ACCENTS) == tuple(names) and P.PAGES[P.ACCENT_PAGE_INDEX] is A and all(P.row_kind(r) == 'check' for r in A.rows),
           'the picker: Neutral and the six accents in the saved order, titled Accent, a check each')
    expect(V.rows[row_i].arg == P.APPEARANCE_PAGE_INDEX and V.rows[row_i].action == P.ACT_PAGE and P.row_kind(V.rows[row_i]) == 'link' and [r.label for r in V.rows[row_i - 1:row_i + 2]] == ['Display', 'Appearance', 'Keyboards']
           and 'Light Mode' not in [r.label for r in V.rows] and 'Accent' not in [r.label for r in V.rows], 'Settings > System: an Appearance link (a chevron, no value) between Display and Keyboards; the Light row still hidden')
    expect([(r.label, r.action, r.arg) for r in W.rows][1:2] == [('Accent', P.ACT_ACCENT, P.ACCENT_PAGE_INDEX)] and P.row_kind(W.rows[1]) == 'value' and W.title == 'Appearance' and W.key == 'm1plus_appearance'
           and P.PAGES[P.APPEARANCE_PAGE_INDEX] is W and P.APPEARANCE_PAGE_INDEX == 39 and P.PAGES[41:] == [P.RADIO, P.RADIONP, P.RADIOINFO, P.SONGINFO, P.REGION_PAGE, P.WIFI_PAGE, P.WIFIINFO_PAGE, P.WIFIPASS_PAGE, P.WIFIOTHER_PAGE, P.WIFISEC_PAGE, P.PEQ_PAGE, P.PEQP_PAGE, P.PEQLIB_PAGE, P.TENBAND_PAGE, P.TENCURVE_PAGE, P.TENPREAMP_PAGE, P.AUTOEQ_PAGE, P.PEQBAND_PAGE, P.SUBSONIC_PAGE], 'the Appearance page (PAGES[39]): an Accent value row opening the picker, the Radio pages after the Pull-down page')

    def open_pick(data=None):
        m = LM(acc=data)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(7)] + [f'pod_check{i}' for i in range(7)])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_ACCENT); m.setword(row + 8, P.ACCENT_PAGE_INDEX)
        m.call(PSYMS['on_row'], a0=row, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    m = open_pick()
    expect(('window_open', A.key) in m.calls and ACCENT_FILE not in m.fs and [shown(m, i) for i in range(7)] == [1, 0, 0, 0, 0, 0, 0], 'the picker opens with the check on Neutral, saving nothing')
    expect([[shown(open_pick(d), i) for i in range(7)] for d in (b'3\n', b'6', b'9', b'')] == [[int(i == k) for i in range(7)] for k in (3, 6, 0, 0)], 'a saved accent has the check; an invalid or empty file is Neutral')
    m = open_pick()
    for k in (2, 5, 0, 6, 1):
        n0 = m.unloads
        m.click(f'pod_row{k}')
        expect(m.fs.get(ACCENT_FILE) == b'%d\n' % k and ACCENT_FILE + '.tmp' not in m.fs and ('rename', ACCENT_FILE + '.tmp', ACCENT_FILE) in m.calls and [shown(m, i) for i in range(7)] == [int(i == k) for i in range(7)]
               and m.unloads == n0 + 1, f'a tap on {names[k]}: written atomically, applied at once (the cached images dropped), the check follows')
    m = open_pick(b'1\n'); m.fail.add(('write', ACCENT_FILE + '.tmp')); m.click('pod_row3')
    expect(m.fs.get(ACCENT_FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls) and m.unloads == 0, 'a failed write changes neither the file, the check nor the screen')
    # the Settings row shows the saved accent's name
    def settings_value(data):
        m = LM(acc=data)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(W.rows))] + [f'pod_value{i}' for i in range(len(W.rows))] + [f'pod_label{i}' for i in range(len(W.rows))])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.APPEARANCE_PAGE_INDEX)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['pod_value1']]
    expect([settings_value(d) for d in (None, b'1\n', b'6\n', b'8')] == [['Neutral'], ['Red'], ['Champagne'], ['Neutral']], 'the Appearance Accent row shows the saved accent, Neutral for no or an invalid file')
    # the assets: a swatch (never a glyph) where a row's glyph goes, hidden insensitive checks
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw')
    tree = awtk_ui.parse(open(os.path.join(raw, 'ui/m1plus_accent.bin'), 'rb').read())
    ok = True
    for i in range(7):
        r = tree.find(f'pod_row{i}'); sw = r.find('pod_swatch'); ck = tree.find(f'pod_check{i}')
        ok &= sw is not None and sw.get('image') == f'pod_sw{i}' and sw.get('sensitive') == 'false' and r.find('pod_icon') is None and ck.get('visible') == 'false' and ck.get('sensitive') == 'false'
    expect(ok and tree.find('label_title').get('tr_text') == 'Accent', 'the picker asset: a pod_swatch image pod_sw<i> in each row (not a pod_icon), a hidden insensitive check each')
    from PIL import Image
    imgs = {i: Image.open(os.path.join(raw, f'images/xx/pod_sw{i}.png')).convert('RGBA') for i in range(7)}
    cols = {i: {p[:3] for p in im.getdata() if p[3] == 255} for i, im in imgs.items()}
    want = [L.NEUTRAL_FILL] + [L.ACCENT_RGB[a] for a in L.ACCENTS[1:]]
    expect(all(im.size == (24, 24) and cols[i] == {tuple(want[i])} and im.getpixel((12, 12))[3] == 255 and im.getpixel((0, 0))[3] == 0 and im.getpixel((12, 3))[3] == 255 for i, im in imgs.items()),
           'the swatches: a 20 px round disc in each accent\'s colour (Neutral #EEEEEC) on a 24 px canvas')
    expect(all(L.image_flips(f'pod_sw{i}.png', imgs[i]) is None for i in range(7)) and all(L.accent_kind(f'pod_sw{i}') is None for i in range(7)), 'a swatch is never flipped by Light nor tinted by an accent')
    st = awtk_ui.parse(open(os.path.join(raw, 'ui/m1plus_appearance.bin'), 'rb').read())
    expect(st.find('pod_row1') is not None and st.find('pod_row1').find('pod_icon').get('image') == 'pod_ci_palette' and st.find('pod_value1').get('tr_text') == 'Neutral' and st.find('label_title').get('tr_text') == 'Appearance',
           'the Appearance page: the Accent row with the palette glyph, the value "Neutral" before the payload sets it')
    st = awtk_ui.parse(open(os.path.join(raw, 'ui/m1plus_settings.bin'), 'rb').read())
    expect(st.find(f'pod_row{row_i}').find('pod_icon').get('image') == 'pod_ci_palette' and st.find(f'pod_value{row_i}') is None, 'the Settings Appearance row: the palette glyph, no value')


def tinted_tests(ctx):
    """The Tinted background (Appearance > Background): pal_map, the three hooks, the surface images, the cover-tinted pages' tones and the setting, against tools/palette.py."""
    expect = ctx.expect
    from PIL import Image
    expect(L.WASH == 12 == O['ACC_WASH'] and L.DARK == 0x40 == O['ACC_DARK'] and L.BACKGROUNDS == ('black', 'tinted', 'light'), 'the wash is 12 % of the accent on dark neutrals (<= #404040); backgrounds black, tinted, light')
    blacks = {a: L.map_colour((0, 0, 0, 255), 'tinted', a)[:3] for a in L.ACCENTS}
    expect(blacks['neutral'] == (0, 0, 0) and blacks['teal'] == (0x08, 0x18, 0x1B) and blacks['red'] == (0x1F, 0x08, 0x07) and blacks['purple'] == (0x17, 0x0B, 0x1D) and blacks['champagne'] == (0x18, 0x14, 0x0D),
           'the page black: Neutral #000000 (Black), Teal #08181B, Red #1F0807, Purple #170B1D, Champagne #18140D')
    expect(L.row_press('teal', 'tinted') == L.mix_tint(blacks['teal'], L.ACCENT_RGB['teal']) and L.card_press('red', 'tinted') == L.mix_tint(L.wash(L.CARD, 'red'), L.ACCENT_RGB['red']),
           'the pressed role tint is mix(tinted surface, accent, 22 %)')
    expect(L.wash((0x8c, 0x8c, 0x8c), 'red') == (0x8c,) * 3 and L.wash((0x41, 0x41, 0x41), 'red') == (0x41,) * 3 and L.wash((0x40, 0x40, 0x40), 'red') != (0x40,) * 3 and L.wash((0x20, 0x20, 0x40), 'red') == (0x20, 0x20, 0x40)
           and L.wash((255, 255, 255, 255), 'red') == (255, 255, 255, 255), 'only a dark neutral colour (<= #404040, spread <= 16) is tinted: secondary greys, text and hues stay')
    words = [BLACK, 0xff1c1c1c, 0xff1e1c1c, 0xff222222, 0xff333333, 0xff2e2c2c, 0xff404040, 0xff414141, 0xff8c8c8c, 0xffaaaaaa, WHITE, 0xff2060ff, 0x80000000, 0x801c1c1c, 0x00000000, 0xff202020, 0xff101a10, 0xff202040] + ROLE_WORDS
    bad = []
    for i, ac in enumerate(L.ACCENTS):
        m = LM(b'1\n', acc=b'%d\n' % i, hook=True)
        for c in words:
            got, want = m.call(PSYMS['pal_map'], a0=c, count=20000), word(L.map_colour(px(c), 'tinted', ac))
            if got != want: bad.append((ac, hex(c), hex(got), hex(want)))
    expect(not bad, f'pal_map(Tinted) for Neutral and the six accents matches the model on {len(words)} colours ({bad[:4]})')
    m = LM(b'1\n', hook=True)
    expect(m.call(PSYMS['pal_active'], count=20000) == 0 and m.call(PSYMS['pal_background'], count=20000) == 0 and all(m.call(PSYMS['pal_map'], a0=c, count=20000) == c for c in words)
           and m.color(m.style(color=BLACK)) == BLACK and m.timers != [], 'Tinted + Neutral is Black: inactive, every colour as it is (the setting is still saved: one timer)')
    # the hooks
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        m = LM(b'1\n', acc=b'%d\n' % i, hook=True)
        blk, card = word(L.map_colour((0, 0, 0, 255), 'tinted', ac)), word(L.map_colour((0x1c,) * 3 + (255,), 'tinted', ac))
        ok = (m.call(PSYMS['pal_active'], count=20000) == 1 and m.call(PSYMS['pal_background'], count=20000) == 2 and m.color(m.style(color=BLACK)) == blk and m.color(m.style(color=0xff1c1c1c)) == card
              and m.color(m.style(color=WHITE)) == WHITE and m.color(m.style(color=0xff8c8c8c)) == 0xff8c8c8c and m.color(m.style(color=0x00000000)) == 0
              and m.gradient(m.style(grads=[BLACK, WHITE, 0xff1c1c1c]))[1] == [blk, WHITE, card] and m.call(PSYMS['ui_ink'], a0=BLACK, count=20000) == blk and m.call(PSYMS['ui_ink'], a0=0, count=20000) == 0
              and m.color(m.style(color=ROLE_WORDS[0])) == word(L.map_colour(px(ROLE_WORDS[0]), 'tinted', ac)))
        expect(ok, f'{ac}: style_get_color, style_get_gradient and ui_ink tint a dark neutral colour; white, grey text and a clear colour stay')
    m = LM(b'1\n', acc=b'4\n', hook=True)
    expect(m.color(m.nested(m.style(color=BLACK))) == word(L.map_colour((0, 0, 0, 255), 'tinted', 'teal')), 'a mutable style is tinted once')
    s = m.style(color=BLACK)
    for name in L.EXEMPT:
        m.on_top(name)
        expect(m.color(s) == BLACK, f'{name}: exempt from the Tinted background')
    m.on_top('home_page')
    expect(m.color(s) != BLACK, 'and any other page is tinted')
    for lab, kw in (('the kill switch', {'kill': True}), ('the bad-boot note', {'bad': True})):
        k = LM(b'1\n', acc=b'4\n', hook=True, **kw)
        expect(k.call(PSYMS['pal_active'], count=20000) == 0 and k.color(k.style(color=BLACK)) == BLACK, f'{lab}: Black + Neutral')
    # the cover-tinted pages: left alone by window, not by colour
    tone = 0xff363432
    teal = lambda c, cover: word(L.map_colour(px(c), 'tinted', 'teal', cover=cover))
    m = LM(b'1\n', acc=b'4\n', hook=True)
    m.on_top('home_page')
    expect(m.color(m.style(color=tone)) == teal(tone, False) != tone and m.color(m.style(color=0xff202020)) == teal(0xff202020, False) != 0xff202020, 'on any other page a dark neutral tone and #202020 are tinted like any colour')
    cover_words = [tone, 0xff202020, 0xff333333, BLACK, 0xff1c1c1c, 0xff0a0b0c, WHITE, 0xff8c8c8c] + ROLE_WORDS
    for name in ('playing_page', 'm1plus_dailymix_page'):
        m.on_top(name)
        got = [(m.color(m.style(color=c)), m.call(PSYMS['pal_map'], a0=c, count=20000), m.call(PSYMS['ui_ink'], a0=c, count=20000)) for c in cover_words]
        want = [(teal(c, True) if c >> 24 else c, teal(c, True), teal(c, True) if c >> 24 else c) for c in cover_words]   # (a clear colour: the hooks and ui_ink skip it, pal_map does not)
        expect(got == want and m.color(m.style(color=BLACK)) == BLACK and m.color(m.style(color=0xff202020)) == 0xff202020, f'{name}: the Tinted wash leaves every background alone; the accent roles still apply ({[hex(g[0]) for g in got[:4]]})')
        expect(m.color(m.style(color=ROLE_WORDS[0])) != ROLE_WORDS[0] and m.color(m.style(color=ROLE_WORDS[2]), 'fg_color') == word(L.map_colour(px(ROLE_WORDS[2]), 'tinted', 'teal')), f'{name}: pressed rows and the progress fill take the accent')
        expect(m.gradient(m.style(grads=[BLACK, ROLE_WORDS[0]]))[1] == [BLACK, teal(ROLE_WORDS[0], True)], f'{name}: gradient stops follow the same rule')
    for name in ('m1plus_album_page', 'm1plus_podcasts_page'):   # (not showing a cover's tone: the album page before its tone, the Shows list; ab_has_tone / pg_has_tone are 1 with a tone, tested with their pages)
        m.on_top(name)
        expect(m.color(m.style(color=BLACK)) == teal(BLACK, False) != BLACK, f'{name}: with no cover tone shown it is tinted like any page')
    m.on_top('playing_page'); m.color(m.style(color=BLACK))
    m.on_top('home_page')
    expect(m.color(m.style(color=BLACK)) == teal(BLACK, False), 'a window opened over (or back to) another page follows its own name')
    # the surface images
    d = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    names = sorted(f[:-4] for f in os.listdir(d) if f.endswith('.png'))
    surf = [n for n in names if n.startswith(L.TINT_SURFACE)]
    expect(L.TINT_SURFACE == ('pod_cd_', 'pod_cdl_', 'pc_sheet', 'pm_sheet', 'mb_glass', 'nb_fade') and len(surf) >= 8 and not [n for n in surf if n.startswith(L.KEEP)], f'{len(surf)} surface images in the tree, none in KEEP')
    stock_h = open(os.path.join(BUILD, 'stock.h')).read()
    line = next((l for l in stock_h.splitlines() if l.startswith('#define TINT_SURFACE ')), '')
    expect(line == '#define TINT_SURFACE "' + ''.join(n + '\\0' for n in L.TINT_SURFACE) + '"', 'TINT_SURFACE in the generated header is the model\'s list')
    bad, n_img, costs = tint_check(d, surf, b'1\n', 'tinted', big=20000)
    expect(not bad, f'{n_img} surface images (cards, sheets, glass, the navbar fade) through the C match the model pixel for pixel ({bad[:3]})')
    changed = [nm for nm in surf if L.render_image(nm, Image.open(os.path.join(d, nm + '.png')), 'tinted', 'teal').getdata() != Image.open(os.path.join(d, nm + '.png')).convert('RGBA').getdata()]
    expect('nb_fade' in changed and 'pod_cd_mid' in changed, 'the model really changes the card pieces and the fade')
    worst = max(costs, key=costs.get)
    expect(costs[worst] < 16000000, f'the dearest surface ({worst}) costs {costs[worst]:,} instructions once, when it is decoded')
    print('  tinted surface image cost, instructions: ' + ', '.join(f'{k} {v:,}' for k, v in sorted(costs.items(), key=lambda kv: -kv[1])))
    # untouched: cover fades, other images, covers, KEEP
    m = LM(b'1\n', acc=b'4\n')
    dark = [(0, 0, 0, 255), (0x1c, 0x1c, 0x1c, 255), (0, 0, 0, 120), (255, 255, 255, 255)] * 4
    for nm in ('np_tint', 'np_scrim', 'ah_tint', 'np_play', 'ah_nav_back', 'tape_body', 'ipod_wheel', 'lk_card', '/mnt/mmc/pod_cd_x.jpg', 'file:pc_sheet'):
        expect(m.image(nm, 4, 4, dark) == dark, f'{nm}: untouched by the Tinted background')
    got = m.image('pod_cd_mid', 4, 4, dark)
    expect(got[:3] == [tuple(L.wash(p, 'teal')) for p in dark[:3]] and got[3] == (255, 255, 255, 255) and [p[3] for p in got] == [p[3] for p in dark], 'a card piece: dark neutral pixels tinted, white and every alpha as they were')
    pr = m.image('pod_cd_mid_down', 4, 4, dark)
    expect({p[:3] for p in pr} == {L.card_press('teal', 'tinted')}, 'the pressed card piece is the tinted card, tinted by the pressed role')
    half = [(0x1c, 0x1c, 0x1c, 128)] * 16
    got = m.image('nb_fade', 4, 4, half, premul=True)
    st = [(0x1c * 128 // 255,) * 3 + (128,)] * 16   # (pixels given as stored: premultiplied)
    sg = m.image('nb_fade', 4, 4, st, premul=True)
    want = L.wash((0x1c, 0x1c, 0x1c), 'teal')
    expect(all(abs(p[k] - want[k] * 128 // 255) <= 1 for p in sg for k in range(3)) and all(p[3] == 128 for p in sg), 'premultiplied pixels are converted, tinted and converted back')
    for fmt in (2, 3, 4):
        expect(LM(b'1\n', acc=b'4\n').image('nb_fade', 4, 4, dark, fmt=fmt)[:2] == [tuple(L.wash(p, 'teal')) for p in dark[:2]], f'format {fmt}: the same tint')
    off = LM(acc=b'4\n')
    expect(off.image('nb_fade', 4, 4, dark) == dark and 'bitmap_lock_buffer_for_write' not in [c[0] for c in off.calls], 'Black + an accent: a surface is not even locked')
    # cost of the hook calls
    m = LM(b'1\n', acc=b'4\n', hook=True).count()
    s = m.style(color=BLACK); m.color(s); m.color(s); c_dark = m.icount
    m.color(m.style(color=WHITE)); c_other = m.icount
    expect(c_dark < 1200 and c_other < 1000, f'a style call costs {c_dark} instructions on a dark colour and {c_other} on any other with Tinted on (stock\'s own part included)')
    print(f'  style call, Tinted: {c_dark} (dark neutral), {c_other} (other)')
    c = LM(b'1\n', acc=b'4\n').count(); c.image('np_play', 4, 4, dark); c_miss = c.icount
    expect(c_miss < 4000, f'an image that is not a surface costs {c_miss} instructions through the hook with Tinted on')
    print(f'  image hook, Tinted: {c_miss} on a non-surface name, {costs.get("pod_cd_mid", 0):,} to tint pod_cd_mid')
    # the setting: applies at once, persists, the kill switch
    m = LM(acc=b'4\n', hook=True)
    m.color(m.style(color=BLACK))
    r = m.call(PSYMS['pal_bg_set'], a0=1, count=2000000)
    expect(r == 1 and m.fs[BG_FILE] == b'1\n' and m.unloads == 1 and m.color(m.style(color=BLACK)) == word(L.map_colour((0, 0, 0, 255), 'tinted', 'teal')) and m.call(PSYMS['pal_background'], count=20000) == 2, 'Tinted chosen with an accent: saved, the images dropped, the next colour is tinted at once')
    n = LM(m.fs[BG_FILE], acc=m.fs[ACCENT_FILE], hook=True)
    expect(n.color(n.style(color=BLACK)) == word(L.map_colour((0, 0, 0, 255), 'tinted', 'teal')), 'the next boot reads Tinted + Teal')
    m.call(PSYMS['pal_accent_set'], a0=0, count=2000000)
    expect(m.unloads == 2 and m.call(PSYMS['pal_active'], count=20000) == 0 and m.call(PSYMS['pal_bg_mode'], count=20000) == 1 and m.color(m.style(color=BLACK)) == BLACK, 'Neutral picked while Tinted is saved: back to Black at once, Tinted stays saved')
    m.call(PSYMS['pal_accent_set'], a0=3, count=2000000)
    expect(m.unloads == 3 and m.color(m.style(color=BLACK)) == word(L.map_colour((0, 0, 0, 255), 'tinted', 'green')), 'and an accent again tints at once')
    m.present.add(KILL_SD)
    m.call(m.timers[0][0], a0=0, count=200000)
    expect(m.unloads == 4 and m.call(PSYMS['pal_active'], count=20000) == 0 and m.color(m.style(color=BLACK)) == BLACK, 'the kill switch appearing: Black + Neutral at the next tick')
    m.present.discard(KILL_SD)
    m.call(m.timers[0][0], a0=0, count=200000)
    expect(m.call(PSYMS['pal_active'], count=20000) == 1, 'and taking it away brings the saved choice back')


def rest_glyph_tests(ctx):
    """Every row glyph (pod_ic_*, fo_ic_*, the Settings cards' pod_ci_*) in the accent at rest: tinted when they are decoded (the image hook, kind GLYPH), pixel for pixel as tools/palette.py; a decode
    after an eviction or an accent change tints again, Neutral leaves them, the two tiles and the swatches stay as they are; a press swaps nothing (no binding exists), and nothing runs on a timer."""
    expect = ctx.expect
    glyph = [(255, 255, 255, a) for a in (0, 40, 128, 200, 255, 255, 90, 0)] * 8
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        for bg in (None, b'1\n', b'2\n'):
            for fmt in (1, 2, 3, 4):
                m = LM(bg, acc=b'%d\n' % i)
                got = m.image('pod_ic_songs', 8, 8, glyph, fmt)
                want = [L.accent_pixel('glyph', p, ac) for p in glyph]
                if got != want: expect(False, f'{ac}, background {bg}, format {fmt}: pod_ic_songs is the accent, alpha kept ({got[:3]} vs {want[:3]})')
    expect(L.accent_kind('pod_ic_songs') == 'glyph' and all(L.accent_kind(t) == 'tile' for t in L.ACCENT_TILE) and L.accent_kind('pod_ci_wifi') == 'glyph' and L.accent_kind('fo_ic_usb') == 'glyph' and L.accent_kind('pod_sw3') is None and L.accent_kind('pod_chev') is None and L.accent_kind('pod_check') == 'fill', 'the model: pod_ic_*, fo_ic_* and pod_ci_* are glyphs, the two tiles, the swatches and the chevron are not')
    m = LM(acc=b'2\n')
    got = m.image('pod_ic_shuffle', 8, 8, [(p[3], p[3], p[3], p[3]) for p in glyph], premul=True)
    want = [L.glyph_image_px(p, 'orange', True) for p in glyph]
    expect(all(g[3] == w[3] and all(abs(g[c] - w[c]) <= 1 for c in range(3)) for g, w in zip(got, want)), 'premultiplied pixels: the accent scaled by the alpha, stored premultiplied')
    # decoded again (evicted from the cache, or after an accent change): tinted each time, in the colour then chosen
    m = LM(acc=b'1\n'); m.real_unload = True
    a1 = m.image('pod_ic_songs', 8, 8, glyph)
    a2 = m.image('pod_ic_songs', 8, 8, glyph)
    expect(a1 == a2 == [L.accent_pixel('glyph', p, 'red') for p in glyph], 'an image decoded again after an eviction is tinted again')
    m.fs[ACCENT_FILE] = b'4\n'; m.call(PSYMS['pal_accent_set'], a0=4, count=4000000)
    expect(m.unloads == 1 and m.image('pod_ic_songs', 8, 8, glyph) == [L.accent_pixel('glyph', p, 'teal') for p in glyph], 'after an accent change the cache is dropped and the next decode has the new colour')
    # Neutral, the tiles and the other pages' glyphs
    m = LM()
    expect(m.image('pod_ic_songs', 8, 8, glyph) == glyph and 'bitmap_lock_buffer_for_write' not in [c[0] for c in m.calls], 'Neutral: a pod_ic_ glyph is not even locked')
    expect(all(LM().image(nm, 8, 8, glyph) == glyph for nm in ('fo_ic_sd', 'fo_ic_usb', 'fo_ic_file')), 'Neutral: the Folders glyphs are untouched')
    expect(all(LM(acc=b'%d\n' % i).image(nm, 8, 8, glyph) == [L.accent_pixel('glyph', p, ac) for p in glyph] for i, ac in enumerate(L.ACCENTS[1:], 1) for nm in ('fo_ic_sd', 'fo_ic_usb', 'fo_ic_file')), 'each accent: the Folders glyphs are the accent')
    m = LM(acc=b'1\n')
    expect(L.accent_kind('pod_ic_rd_art') is None and all(LM(acc=b'%d\n' % i).image('pod_ic_rd_art', 8, 8, glyph) == glyph for i in range(1, 7)), 'the Radio placeholder art pod_ic_rd_art stays neutral under every accent')
    expect(all(m.image(nm, 8, 8, glyph) == glyph for nm in ('pod_sw0', 'pod_sw3', 'pod_chev')), 'the swatches and the chevron stay as they are at rest')
    # the Library tiles: the #1E1E1E square stays exactly, white is the accent, the antialiased glyph edge and the square's alpha edge blend
    tp = [(30, 30, 30, 255), (255, 255, 255, 255), (142, 142, 142, 255), (30, 30, 30, 90), (30, 30, 30, 0), (255, 255, 255, 128), (31, 31, 31, 255), (200, 200, 200, 255)]
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        for nm in L.ACCENT_TILE:
            got = LM(acc=b'%d\n' % i).image(nm, 8, 1, tp)
            expect(got == [L.accent_pixel('tile', p, ac) for p in tp] and got[0] == (30, 30, 30, 255) and got[3] == (30, 30, 30, 90) and got[1] == L.ACCENT_RGB[ac] + (255,) and got[5][:3] == L.ACCENT_RGB[ac], f'{nm} under {ac}: the square stays #1E1E1E, white is the accent, alpha kept ({got[:3]})')
    expect(all(LM().image(nm, 8, 1, tp) == tp for nm in L.ACCENT_TILE), 'Neutral: the Library tiles render exactly as before')
    expect(LM(acc=b'1\n').image('pod_ic_dltile', 8, 1, tp, premul=True) is not None and LM(b'2\n', acc=b'1\n').image('pod_ic_dltile', 8, 1, tp) == [L.accent_pixel('tile', p, 'red') for p in tp], 'a tile is tinted instead of flipped (accent over Light)')
    expect(all(LM(acc=b'%d\n' % i).image('pod_ci_wifi', 8, 8, glyph) == [L.accent_pixel('glyph', p, ac) for p in glyph] for i, ac in enumerate(L.ACCENTS[1:], 1)), 'each accent: a Settings card glyph (pod_ci_*) is the accent at rest')
    expect(LM().image('pod_ci_wifi', 8, 8, glyph) == glyph, 'Neutral: the Settings card glyphs are untouched')
    m = LM(b'2\n')
    expect(m.image('pod_ic_songs', 8, 8, glyph) == fl(glyph), 'Light with Neutral: a pod_ic_ glyph flips as before')
    m = LM(b'1\n', acc=b'1\n'); d = disc_image()
    expect(m.image('pod_ic_x', 16, 16, d) == [L.accent_pixel('glyph', p, 'red') for p in d], 'Tinted background: the glyph kind is the accent, not the surface wash')
    # no timer with an accent: only the palette\'s own
    m = LM(acc=b'1\n'); m.image('pod_ic_songs', 8, 8, glyph); m.image('pod_ci_wifi', 8, 8, glyph)
    m.call(PSYMS['pal_accent_set'], a0=2, count=4000000)
    expect(all(ms == O['LIGHT_TICK_MS'] for _, ms in m.timers) and len(m.timers) <= 1, f'no keep-alive timer exists with an accent set ({m.timers})')
    # the pressed-glyph machinery is gone: no binding, no copy, nothing to look up (a pressed Settings row is the 22 % tint with the accent glyph already on it)
    expect(not [n for n in ('pal_glyph_bind', 'glyph_down', 'glyph_make') if n in PSYMS] and not any(c[0] in ('image_base_set_image', 'bitmap_create_ex') for c in m.calls), 'no pressed-glyph binding or copy exists')
    for ac in L.ACCENTS[1:]:
        expect(L.card_press(ac) != L.ACCENT_RGB[ac] and L.accent_pixel('glyph', (255, 255, 255, 255), ac)[:3] == L.ACCENT_RGB[ac], f'{ac}: a pressed Settings row is the tinted card with the accent glyph on it')
    # cost of the tint per decode
    m = LM(acc=b'1\n').count(); n0 = m.icount; m.image('pod_ic_songs', 24, 24, [(255, 255, 255, 255)] * 576); c = m.icount - n0
    expect(c < 400000, f'the glyph tint costs {c:,} instructions per 24 x 24 decode')
    print(f'  glyph tint (24 x 24, once per decode): {c:,} instructions')


def findings_tests(ctx):
    """Review findings of the Tinted background, written against the numbers only (no model API): a cover tone is never a role colour, and the cover pages' corners and the colours of other pages
    do not depend on the cover."""
    expect = ctx.expect
    teal = lambda c: word(L.map_colour(px(c), 'tinted', 'teal'))   # a page that is not a cover page
    # finding 3: a grey cover tone must not change unrelated pages
    m = LM(b'1\n', acc=b'4\n', hook=True)
    grey = m.call(PSYMS['pal_tone'], a0=0xff333333, count=20000)
    m.on_top('playing_page')
    m.on_top('home_page')
    expect(grey == 0xff333333 and m.color(m.style(color=0xff333333)) == teal(0xff333333) != 0xff333333 and m.color(m.style(color=0xff1c1c1c)) == teal(0xff1c1c1c), 'a cover averaging grey #333333 does not keep that colour on other pages (the Settings separators stay tinted)')
    # finding 1: a cover tone is never a role colour
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        for bgmode in (b'0\n', b'1\n'):
            m = LM(bgmode, acc=b'%d\n' % i, hook=True)
            m.on_top('playing_page')
            row, prog = word(rgba(L.ROLE_PRESS_ROW)), word(rgba(L.ROLE_PROGRESS))
            t1, t2 = m.call(PSYMS['pal_tone'], a0=row, count=20000), m.call(PSYMS['pal_tone'], a0=prog, count=20000)
            ok = (t1 == 0xff333333 and t2 == 0xffffffff and m.color(m.style(color=t1)) == t1 and m.color(m.style(color=t2)) == t2
                  and m.call(PSYMS['pal_tone'], a0=0xff363432, count=20000) == 0xff363432)
            expect(ok, f'{ac} {bgmode!r}: the tone #333334 stays a tone (#333333), not the pressed row; #FFFFFE stays white-ish; others as they are ({t1:#x} {t2:#x})')
    m = LM(b'1\n', acc=b'1\n', hook=True)
    m.on_top('playing_page')
    expect(m.call(PSYMS['pod_shade'], a0=0x343333, a1=0, a2=0, a3=0, count=20000) == 0x333333 and m.call(PSYMS['pod_bar_color'], a0=0xff343333, count=20000) == 0xff333333,
           'pod_shade and pod_bar_color (the corners, the status bar) never answer a role colour either')
    # finding 2: the corners
    def corners(page, ac, bg):
        """pod_corners(canvas, tab, r 2, side 4, colour 0x191919, row0 0, a_top 0, a_bot 0, rows 100) over a page: the fill colours it paints (a full-coverage 2 x 2 corner at each of the four corners)."""
        c = LM(bg, acc=ac, hook=True)
        t = c.alloc(16); c.u.mem_write(t, bytes([255] * 16))
        for k, v in enumerate((0x191919, 0, 0, 0, 100)): c.setword(STACK + 16 + 4 * k, v)
        c.on_top(page); c.fills = []
        c.call(PSYMS['pod_corners'], a0=0x7000a000, a1=t, a2=2, a3=4, count=200000)
        return [f[0] for f in c.fills]
    raw = 0xff191919
    expect(corners('playing_page', b'4\n', b'1\n') == [raw] * 16, 'Tinted + Teal on Now Playing: the corners are painted in the unwashed shade (they match the cover tone behind them)')
    wash19 = teal(raw)
    expect(wash19 != raw and corners('home_page', b'4\n', b'1\n') == [wash19] * 16, 'on any other page the same call is washed like the page it sits on')
    expect(corners('playing_page', b'4\n', b'0\n') == [raw] * 16 and corners('playing_page', b'0\n', b'1\n') == [raw] * 16, 'Black + Teal and Tinted + Neutral: raw')


def press_tests(ctx):
    """The pressed Play / Shuffle buttons: the dark pills (a role colour, the rest colour tinted), the Queue's off buttons, the album page's Shuffle disc and the white Play pills (images), against the numbers."""
    expect = ctx.expect
    from PIL import Image
    d = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    expect(L.ROLE_PRESS_PILL == 0x333335 == O['ROLE_PRESS_PILL'] and L.ROLE_PRESS_QPILL == 0x3a3a3d == O['ROLE_PRESS_QPILL'] and O['QP_PILL_OFF_DOWN'] == word(rgba(L.ROLE_PRESS_QPILL)),
           'the roles: the pressed Play / Shuffle pill #333335, the Queue off button pressed #3A3A3D (QP_PILL_OFF_DOWN)')
    # the dark pills and the Queue's off buttons: mix(rest colour, accent, 22 %), alpha kept; Tinted: the tinted rest colour first
    pill, qp = word(rgba(L.ROLE_PRESS_PILL)), word(rgba(L.ROLE_PRESS_QPILL, 0x80))
    mix = lambda base, a: tuple((b * 78 + c * 22 + 50) // 100 for b, c in zip(base, a))
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        a = L.ACCENT_RGB[ac]
        for bg, mode, wsh in (('black', b'0\n', lambda c: c), ('tinted', b'1\n', lambda c: L.wash(c, ac))):
            m = LM(mode, acc=b'%d\n' % i, hook=True)
            want = (word(mix(wsh((0x1e, 0x1e, 0x1e)), a) + (255,)), word(mix(wsh((0x2c, 0x2c, 0x2e)), a) + (0x80,)))
            got = (m.call(PSYMS['pal_map'], a0=pill, count=20000), m.call(PSYMS['pal_map'], a0=qp, count=20000))
            expect(got == want and got == (word(L.map_colour(px(pill), bg, ac)), word(L.map_colour(px(qp), bg, ac))), f'{ac} {bg}: the pressed pill is mix(#1E1E1E, accent, 22 %), the Queue off button mix(#2C2C2E, accent, 22 %) ({got[0]:#x} {got[1]:#x})')
    expect(all(L.map_colour(px(c), 'black', 'neutral') == px(c) for c in (pill, qp)) and LM(hook=True).call(PSYMS['pal_map'], a0=pill, count=20000) == pill, 'Neutral: the pressed pill colours pass through (#333335 and #3A3A3D are one blue level off today\'s greys)')
    expect(L.not_role((0x33, 0x33, 0x35, 255)) == (0x33, 0x33, 0x36, 255) and L.not_role((0x3a, 0x3a, 0x3d, 255)) == (0x3a, 0x3a, 0x3e, 255), 'a cover colour equal to a pill role moves one blue level off it')
    m = LM(acc=b'1\n', hook=True); m.on_top('playing_page')
    expect(m.call(PSYMS['pal_tone'], a0=pill, count=20000) == 0xff363333 and m.call(PSYMS['pal_tone'], a0=word(rgba(L.ROLE_PRESS_QPILL)), count=20000) == 0xff3e3a3a, 'pal_tone never answers a pill role either')
    # the Shuffle disc pressed: the #444444 disc becomes mix(#2A2A2A, accent, 22 %), the white glyph stays white, the edge blends; alpha kept
    im = Image.open(os.path.join(d, 'ah_shuffle_down.png')).convert('RGBA')
    px_ = {p[:3] for p in im.getdata() if p[3] == 255}
    expect((0x44, 0x44, 0x44) in px_ and (255, 255, 255) in px_ and L.accent_kind('ah_shuffle_down') == 'shufdown' and L.accent_kind('ah_shuffle') is None, 'ah_shuffle_down is a #444444 disc with a white glyph; only the pressed disc is tinted')
    for ac in L.ACCENTS[1:]:
        for bg in ('black', 'tinted'):
            out = L.render_image('ah_shuffle_down', im, bg, ac)
            cols = {p[:3] for p in out.getdata() if p[3] == 255}
            disc = L.press_of(L.SHUF, ac, bg)
            expect(disc in cols and (255, 255, 255) in cols and (0x44, 0x44, 0x44) not in cols and [p[3] for p in out.getdata()] == [p[3] for p in im.getdata()], f'{ac} {bg}: the pressed Shuffle disc is {disc}, the glyph white, alpha kept')
    # the white Play pills pressed: solid accent (one colour in, one colour out)
    for nm, rgb in (('ah_pill_down', (0xbe,) * 3), ('dp_pill_down', (0xd6, 0xd6, 0xd8))):
        im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
        expect({p[:3] for p in im.getdata() if p[3] == 255} == {rgb} and L.accent_kind(nm) == 'glyph', f'{nm} is one solid grey ({rgb}), tinted as a glyph: the accent')
        for ac in L.ACCENTS[1:]:
            out = L.render_image(nm, im, 'black', ac)
            expect({p[:3] for p in out.getdata() if p[3] == 255} == {L.ACCENT_RGB[ac]}, f'{nm} under {ac} is the solid accent')
    expect(L.accent_kind('ah_pill') is None and L.accent_kind('dp_pill') is None and L.accent_kind('dp_add_down') is None, 'the pills at rest and the Add disc are not tinted')
    # the C against the model, on the images and on every background; Neutral untouched
    for i, ac in enumerate(L.ACCENTS[1:], 1):
        for mode, bg in ((b'0\n', 'black'), (b'1\n', 'tinted')):
            for nm in ('ah_shuffle_down', 'ah_pill_down', 'dp_pill_down'):
                im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
                pixels = list(im.getdata())
                got = LM(mode, acc=b'%d\n' % i).image(nm, im.width, im.height, pixels)
                expect(got == list(L.render_image(nm, im, bg, ac).getdata()), f'{nm}: the C matches the model under {ac}, {bg}')
    for nm in ('ah_shuffle_down', 'ah_pill_down', 'dp_pill_down'):
        im = Image.open(os.path.join(d, nm + '.png')).convert('RGBA')
        pixels = list(im.getdata())
        expect(LM().image(nm, im.width, im.height, pixels) == pixels, f'Neutral: {nm} is as before')
    # the built assets carry the roles where the buttons are
    import awtk_ui
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui')
    hits = {}
    for f in sorted(os.listdir(raw)):
        if not f.endswith('.bin'): continue
        for w in awtk_ui.parse(open(os.path.join(raw, f), 'rb').read()).walk():
            for k, v in w.props:
                if isinstance(v, str) and v.upper().startswith(('#333335', '#3A3A3D')) and 'color' in k: hits.setdefault(v[:7].upper(), set()).add((f, w.name))
    plays = {w for _, w in hits.get('#333335', ())}
    expect(plays == {'btn_play', 'btn_shuffle'} and {w for _, w in hits.get('#3A3A3D', ())} == {'btn_shuffle', 'btn_repeat'}, f'#333335 only on the Play / Shuffle pills, #3A3A3D only on the Queue buttons ({hits})')


SECTIONS = [hooks_tests, flip_tests, style_tests, image_tests, model_tests, setting_tests, settings_tests, accent_map_tests, accent_image_tests, accent_setting_tests, accent_picker_tests, roles_tests, press_tests, tinted_tests, findings_tests, rest_glyph_tests]

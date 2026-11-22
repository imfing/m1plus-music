"""The pull-down's tiles (patch/pulldown.c, docs/modules/pulldown.md): the hook on dialog_dropdown_dialog_init, the saved file and the Settings > Appearance > Control Center page.

The hook runs the real compiled payload under the harness machine with the stock init mocked at its resume point (the dialog's handlers
and the tiles' clicks are bound by stock code, which the hook never touches); the dialog's geometry is the built asset's own
(ui/dialog/dropdown_dialog.bin). The page is the Main Menu page's twin and is tested the way menu.py tests that one."""
import os, random, struct
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_S0
import palette
import cdefs
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

FILE, TMP = '/mnt/data/m1plus/pulldown-tiles', '/mnt/data/m1plus/pulldown-tiles.tmp'
LABELS_FILE, LABELS_TMP = '/mnt/data/m1plus/pulldown-labels', '/mnt/data/m1plus/pulldown-labels.tmp'
IMG = ('img_wifiswitch', 'img_btswitch', 'img_keylockswitch', 'img_gainswitch', 'img_usbmode', 'img_outputswitch', 'img_playset', 'img_sysset', 'pod_tile_sleep', 'pod_tile_settings', 'pod_tile_eq', 'pod_tile_power', 'pod_tile_airplay', 'pod_tile_dlna', 'pod_tile_transfer', 'pod_tile_shot')
LAB = ('label_wifi', 'label_bt', 'label_lock', 'label_gain', 'label_usbmode', 'label_outputway', 'label_playset', 'label_sysset', 'pod_cap_sleep', 'pod_cap_settings', 'pod_cap_eq', 'pod_cap_power', 'pod_cap_airplay', 'pod_cap_dlna', 'pod_cap_transfer', 'pod_cap_shot')
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin')
N = 8    # the stock tiles (and the slots: the pull-down holds eight)
NT = 16  # every tile: the stock ones and the eight of ours


def geometry():
    """name -> (x, y, w, h) of the built dialog's tiles and captions."""
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    return {n: (tree.find(n).x, tree.find(n).y, tree.find(n).w, tree.find(n).h) for n in IMG + LAB}


class PD(Machine):
    """The dialog's thirty widgets (the tiles and captions, at the built asset's places; ours hidden and insensitive as the asset has them) and the stock init's resume point."""

    def __init__(self, fs=None, gone=()):
        super().__init__()
        self.handlers[pod.PULLDOWN_INIT + 12] = 'stock_pulldown_resume'
        self.geo = geometry()
        self.dlg = self.alloc(0x80)
        for n, (x, y, w, h) in self.geo.items():
            if n in gone: continue
            hd = self.widget(n); self.props[(hd, 'x')], self.props[(hd, 'y')] = x, y
            if n.startswith(('pod_tile_', 'pod_cap_')): self.props[(hd, 'visible')] = self.props[(hd, 'sensitive')] = 0
        if fs is not None: self.fs[FILE] = fs

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'stock_pulldown_resume':
            self.calls.append(('stock_pulldown_resume', u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)))
            u.reg_write(UC_MIPS_REG_V0, self.init_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        super()._hook(u, address, size, _)

    def open(self, dlg=None):
        return self.call(PSYMS['m1plus_pulldown_init'], a0=self.dlg if dlg is None else dlg, a1=0, count=3000000)

    def pos(self, n): return (self.props[(self.widgets[n], 'x')], self.props[(self.widgets[n], 'y')])
    def hidden(self, n): return self.props.get((self.widgets[n], 'visible'), 1) == 0 and self.props.get((self.widgets[n], 'sensitive'), 1) == 0
    def touched(self): return [c for c in self.calls if c[0] in ('widget_move', 'widget_set_visible', 'widget_set_sensitive', 'widget_restack', 'widget_resize', 'widget_destroy')]


def want(geo, shown):
    """The layout the saved order calls for, from the stock places: name -> (x, y) of the shown tiles and captions, and the set of hidden names."""
    pos, hide = {}, set()
    for k, t in enumerate(shown):
        ix, iy = geo[IMG[k]][:2]
        pos[IMG[t]] = (ix, iy)
        pos[LAB[t]] = (ix + geo[LAB[t]][0] - geo[IMG[t]][0], iy + geo[LAB[t]][1] - geo[IMG[t]][1])
    for t in range(NT):
        if t not in shown: hide |= {IMG[t], LAB[t]}
    return pos, hide


def check_layout(m, shown):
    """None, or what differs: the shown tiles and captions at the slots (captions at their stock offset), the others hidden and insensitive, nothing else moved."""
    pos, hide = want(m.geo, shown)
    for n in IMG + LAB:
        if n in hide:
            if not m.hidden(n): return f'{n} is not hidden and insensitive'
            if m.pos(n) != m.geo[n][:2]: return f'{n} was moved'
        else:
            if m.pos(n) != pos[n]: return f'{n} at {m.pos(n)}, wanted {pos[n]}'
            if m.props.get((m.widgets[n], 'visible'), 1) != 1 or m.props.get((m.widgets[n], 'sensitive'), 1) != 1: return f'{n} lost its visibility or sensitivity'
    return None


def hook_tests(ctx):
    expect, P = ctx.expect, pod_pages
    d = built_demo_bytes(); image = bytearray(d)
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]

    # -- 0. the hook and what it relies on ---------------------------------------------------------------------------
    w0, w1, w2, w3 = (word(pod.PULLDOWN_INIT + 4 * i) for i in range(4))
    expect(pod.PULLDOWN_INIT == 0x475f04 and pod.PULLDOWN_INIT_PROLOGUE == (0x3c1c0059, 0x279cdfcc, 0x0399e021)
           and w0 == pod.j(PSYMS['m1plus_pulldown_init']) and w1 == 0 and w2 == pod.PULLDOWN_INIT_PROLOGUE[2] and w3 == 0x1080003c == pod.PULLDOWN_PINS[0][1],
           'dialog_dropdown_dialog_init starts with j m1plus_pulldown_init; nop; the trampoline resumes at its beqz a0')
    expect(MANIFEST['hook_pulldown']['addr'] == pod.PULLDOWN_INIT and MANIFEST['hook_pulldown']['target'] == PSYMS['m1plus_pulldown_init'], 'the manifest records the hook')
    expect(all(word(a) == old for a, old, _ in pod.PULLDOWN_PINS[1:]), 'every pinned stock word of the dialog init, its dispatcher and its handlers is as pinned')
    expect([a for a, _, _ in pod.PULLDOWN_PINS][1:4] == [0x4d1c70, 0x4d1c7c, 0x4d1c84] and word(0x4d1c70) == 0x24a59a4c,
           'the navigator\'s dialog-init dispatcher (strcmp "dialog/dropdown_dialog", then the GOT call of the init) is pinned')
    expect(d[pod.fileoff(image, 0x749a4c):][:23] == b'dialog/dropdown_dialog\0', 'the dispatcher compares with the dialog\'s name')
    expect(pod.PULLDOWN_INIT not in range(pod.PLAYMORE_INIT - 12, pod.PLAYMORE_INIT + 12) and 'pulldown.c' in pod.SOURCES, 'a hook of its own, in the payload sources')
    gp = []
    m = PD(); m.u.hook_add(UC_HOOK_CODE, lambda u, a, s, _: gp.append(u.reg_read(UC_MIPS_REG_GP)), begin=pod.PULLDOWN_INIT + 12, end=pod.PULLDOWN_INIT + 12)
    m.open()
    expect(gp == [pod.GP], f'the trampoline restores $gp before the stock body ({[hex(g) for g in gp]})')
    expect(m.calls[0] == ('stock_pulldown_resume', m.dlg, 0), 'the stock init runs first, with its arguments')

    # -- 1. the assets: the eight tiles on the stock grid, the captions at one offset from their tile --------------------
    g = geometry()
    slots = [g[n][:2] for n in IMG]
    expect(slots[:N] == [(21, 11), (95, 11), (169, 11), (243, 11), (21, 111), (95, 111), (169, 111), (243, 111)]
           and all(g[n][2:] == (56, 56) for n in IMG), 'the tiles are 56 x 56 round the stock centres: four columns 74 px apart (x 21 ..), rows at y 11 and 111 (stock 50 x 50, rows 14 and 114)')
    offs = {(g[LAB[t]][0] - g[IMG[t]][0], g[LAB[t]][1] - g[IMG[t]][1]) for t in range(NT)}
    expect(offs == {(-7, 61)} and all(g[n][2:] == (71, 36) for n in LAB), f'every caption is 71 x 36, centred 5 px under its tile\'s disc, at the same offset ({offs})')
    caps = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    marg = {(n, p[0].split(':')[-1], p[1]) for n in LAB for p in caps.find(n).props if p[0].split(':')[-1].startswith('margin')}
    expect(marg == {(n, m, '0') for n in LAB for m in ('margin_left', 'margin_right', 'margin_bottom')},
           f'every caption draws two 16 px rows: AWTK wraps to the box less its left / right margins (0) and drops a row ending under the bottom margin (0); top margin 2 + 16 + spacer 2 + 16 = 36 ({sorted(marg)[:4]})')
    cards = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read()); v = cards.find('view_switchs'); grab = cards.find('pod_grabber')
    expect(cards.find('pod_card') is None and not [c for c in v.children if c.name.startswith('pod_card')], 'no card under the tiles: the discs sit on the panel')
    expect(cards.children[-1] is grab and (grab.x, grab.y, grab.w, grab.h) == (142, 328, 36, 5) and grab.get('sensitive') == 'false' and grab.type == 'image' and grab.get('image') == 'drop_grabber' and grab.get('style:normal:bg_color') is None, 'the grabber is the dialog\'s last child, an image of the baked pill (drop_grabber, 36 x 5) at the bottom centre, insensitive')
    bl = cards.find('view_backlight')
    expect((bl.x, bl.y, bl.w, bl.h) == (10, 265, 300, 52) and cards.get('style:normal:bg_color') == '#000000EB' and (cards.w, cards.h) == (320, 340) and 40 + max(g[LAB[t]][1] for t in range(NT)) + 2 + 16 + 2 + 16 <= bl.y - 17 and bl.y + bl.h + 8 <= grab.y,
           'the panel is black at 92 % (#000000EB), 340 high; the brightness card is 300 x 52 at y 265 .. 317 with room above (the last row of a two-row caption ends 17 px or more over it: top margin 2, rows 16 + 2 + 16) and below (the grabber at 328)')
    sl, lo, hi = bl.find('slider_backlight'), bl.find('image0'), bl.find('image1')
    expect(bl.children == [lo, hi, sl] and all(bl.get(f'style:{st}:bg_color') == '#1C1C1E' and bl.get(f'style:{st}:round_radius') == '26' and bl.get(f'style:{st}:bg_image') is None for st in ('normal', 'disable', 'focused'))
           and bl.get('style:normal:border_width') == '0', 'view_backlight is the brightness card: flat #1C1C1E, radius 26, no pill image')
    expect((lo.x, lo.y, lo.w, lo.h) == (14, 16, 20, 20) and (hi.x, hi.y, hi.w, hi.h) == (266, 16, 20, 20) and (sl.x, sl.y, sl.w, sl.h) == (48, 1, 200, 50) and bl.y + sl.y == 266 and bl.y + sl.y + sl.h == 316
           and sl.get('bar_size') == '6' and sl.get('max') is None and sl.get('value') == '60' and {v for k, v in sl.props if k.endswith(':icon')} == {'pod_sl_thumb'}
           and sl.get('style:normal:bg_image') == 'drop_bg' and sl.get('style:normal:fg_image') == 'drop_fg',
           'the stock slider (name, value, no range of its own) keeps its screen y 266 .. 316 and is laid out as the Display page\'s: suns at x 14 and 266, slider x 48 .. 248 in the card, 6 px track and fill, the capsule thumb')
    expect(all(cards.find(n).get(f'style:{st}:font_size') == '16' and cards.find(n).get(f'style:{st}:text_color') == ('#555555' if st == 'disable' else '#AAAAAA') and cards.find(n).get(f'style:{st}:text_align_v') == 'top' for n in LAB[:8] for st in ('normal', 'disable', 'focused')),
           'every stock caption is 16 px #AAAAAA (disabled #555555), top aligned')

    # -- 2. the stock layout: no file, a bad file, the default, a missing widget, a failed stock init ------
    default = list(range(N))
    for name, fs in (('no file', None), ('the default file', b'01234567\n'), ('without the newline', b'01234567'), ('the default with an empty hidden part', b'01234567-\n'), ('the default with ours listed as hidden', b'01234567-89abcdef\n')):
        m = PD(fs=fs); ret = m.open()
        expect(ret == 0 and m.touched() == [] and check_layout(m, default) is None, f'{name}: the stock layout, nothing moved, hidden or restacked (stock\'s result {ret})')
    for name, fs in (('an unknown character', b'0123456x\n'), ('an id twice', b'0120\n'), ('an id twice across the parts', b'01-1\n'), ('a second dash', b'0-1-2\n'),
                     ('an empty file', b''), ('too long', b'01234567-0123\n'), ('upper case', b'ABC\n'), ('a character out of range', b'g\n'), ('nine tiles shown', b'012345678\n'), ('nine shown, the rest listed', b'012345678-9a\n'), ('a space', b'01 2\n'), ('a second line', b'01\n23\n')):
        m = PD(fs=fs); m.open()
        expect(m.touched() == [] and check_layout(m, default) is None, f'{name} ({fs!r}): the stock layout')
    m = PD(fs=b'3210\n'); m.init_ret = 0x10; ret = m.open()
    expect(ret == 0x10 and m.touched() == [] and ('widget_lookup', IMG[0]) not in m.calls, 'a stock init that fails: its result is returned and nothing is arranged')
    m = PD(fs=b'3210\n'); ret = m.open(dlg=0)
    expect(ret == 0 and m.touched() == [] and not [c for c in m.calls if c[0] == 'widget_lookup'], 'a null dialog: the stock result, nothing looked up')
    for gone in IMG + LAB:
        m = PD(fs=b'3210\n', gone=(gone,)); ret = m.open()
        expect(ret == 0 and m.touched() == [], f'no {gone} in the asset: the stock layout, nothing moved or hidden')

    # -- 3. an order, hidden tiles, all hidden --------------------------------------------------------------------------
    cases = [('reversed', b'76543210\n', list(range(7, -1, -1))), ('two swapped', b'10234567\n', [1, 0, 2, 3, 4, 5, 6, 7]),
             ('the second row first', b'45670123\n', [4, 5, 6, 7, 0, 1, 2, 3]), ('some hidden, the rest in the file\'s order', b'5130-2467\n', [5, 1, 3, 0]),
             ('hidden tiles listed in any order', b'6-5740132\n', [6]), ('without the hidden part', b'72\n', [7, 2]), ('one tile', b'3\n', [3]),
             ('the default order with the hidden part empty and tile 7 hidden', b'0123456-7\n', [0, 1, 2, 3, 4, 5, 6]), ('no newline', b'201', [2, 0, 1])]
    for name, fs, order in cases:
        m = PD(fs=fs); ret = m.open()
        err = check_layout(m, order)
        expect(ret == 0 and err is None and P.parse_pulldown(fs) == order, f'{name} ({fs!r}): {order} shown in that order at the first places ({err})')
    for name, fs in (('a bare newline', b'\n'), ('a bare dash', b'-'), ('all listed as hidden', b'-01234567\n'), ('all hidden, any order', b'-76543210')):
        m = PD(fs=fs); m.open()
        expect(check_layout(m, []) is None and all(m.hidden(n) for n in IMG + LAB) and P.parse_pulldown(fs) == [], f'{name} ({fs!r}): all eight tiles and captions hidden and insensitive, none moved')
    m = PD(fs=b'3-0\n'); m.open()
    expect(check_layout(m, [3]) is None and [c[1] for c in m.calls if c[0] == 'widget_set_visible'] == [m.widgets[n] for n in (IMG[0], LAB[0], IMG[1], LAB[1], IMG[2], LAB[2], IMG[4], LAB[4], IMG[5], LAB[5], IMG[6], LAB[6], IMG[7], LAB[7], IMG[8], LAB[8], IMG[9], LAB[9], IMG[10], LAB[10], IMG[11], LAB[11], IMG[12], LAB[12], IMG[13], LAB[13], IMG[14], LAB[14], IMG[15], LAB[15])]
           and all(c[2] == 0 for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive')),
           'every tile not listed is hidden, ours too (a listed hidden id adds nothing)')
    lookups = {c[1] for c in m.calls if c[0] == 'widget_lookup'}
    expect(lookups - {'view_bar_left', 'pod_sleep', 'bar_dclock'} == set(IMG + LAB) and not any(c[0] in ('widget_destroy_children', 'widget_set_prop_str', 'widget_set_text_utf8', 'widget_set_tr_text') for c in m.calls),
           'only the thirty tiles and captions (and the bar refresh: view_bar_left, pod_sleep; the 12 h clock: bar_dclock) are looked up; nothing is renamed, destroyed or re-labelled')

    # -- 3b. the bar copy at the dialog's init: the Battery Percentage and the EQ mark are there in the first frame, not one timer tick later ---------
    bp, lo = (cdefs.defines(os.path.join(ROOT, 'patch', f), strings=True) for f in ('battery.h', 'lineout.h'))

    def bar_machine(pct=b'87\n', eq=1, digital=0, kill=False):
        m = PD(); m.fs[bp['BP_FILE']] = b'1\n'; m.fs[bp['BP_GAUGE']] = pct
        m.lbl = m.widget(bp['BP_LABEL_DD']); m.props[(m.lbl, 'visible')] = 0
        m.bg = m.widget(bp['BP_BG_DD']); m.props[(m.bg, 'visible')] = 0
        m.left = m.widget(lo['LO_GROUP']); m.eq = m.widget(lo['EQ_IND']); m.props[(m.eq, 'visible')] = 0
        m.dig = m.widget(lo['EQ_DIGITAL']); m.props[(m.dig, 'visible')] = digital   # what stock's face call left of the glyph
        m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([eq]))
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        m.open()
        return m

    shown = lambda m, h: [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == h]
    m = bar_machine()
    expect([c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.lbl] == ['87'] and shown(m, m.lbl) == [1] and shown(m, m.bg) == [1] and shown(m, m.eq) == [1],
           'the init shows the Battery Percentage (the bare number and its backdrop) and the EQ mark at once (Equalizer on, the digital-out glyph hidden by stock\'s face)')
    m = bar_machine(digital=1)
    expect(shown(m, m.eq) == [] and shown(m, m.lbl) == [1], 'the digital-out glyph still shows: the mark stays hidden, the percentage is there')
    m = bar_machine(eq=0)
    expect(shown(m, m.eq) == [] and shown(m, m.lbl) == [1], 'Equalizer off: no mark')
    m = bar_machine(pct=b'x')
    expect(shown(m, m.lbl) == [] and shown(m, m.bg) == [] and not [c for c in m.calls if c[0] == 'widget_set_text_utf8'], 'a bad gauge: the label and its backdrop stay hidden')
    m = bar_machine(kill=True)
    expect(shown(m, m.lbl) == [] and shown(m, m.bg) == [] and shown(m, m.eq) == [] and not [c for c in m.calls if c[0] == 'widget_set_text_utf8'] and 'view_bar_left' not in {c[1] for c in m.calls if c[0] == 'widget_lookup'},
           'kill switch: nothing of this happens')

    # -- 3c. the bar copy's clock follows 24-Hour Time as the real bar does (patch/pulldown.c pd_clock): stock's change_time24h_12h formats only the real bar
    C = cdefs.defines(os.path.join(ROOT, 'patch', 'offsets.inc'), strings=True)
    CLOCK, H24 = C['PD_CLOCK_NAME'], pod.DATA['TIME_24H'][0]
    def clocked(byte, kill=False, widget=True):
        m = PD()
        if widget: m.clock = m.widget(CLOCK)
        m.u.mem_write(H24, bytes([byte]))
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        m.open()
        return [c for c in m.calls if c[0] == 'digit_clock_set_format' and widget and c[1] == m.clock]
    sets = clocked(0)
    expect(pod.DATA['TIME_24H'] == (0xa05ab0, 'time24hflag') and CLOCK == 'bar_dclock' and awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read()).find(CLOCK).get('format') == 'hh:mm'
           and len(sets) == 1 and sets[0][2] == C['PD_CLOCK_12H'] == 'HH:TT', '24-Hour Time off: the bar copy\'s clock takes the real bar\'s 12 h format "HH:TT", once')
    expect(not clocked(1) and not clocked(0, kill=True) and not clocked(0, widget=False), '24-Hour Time on, the kill switch, or no clock widget: the asset\'s "hh:mm" stays')

    # -- 4. the parser: the payload against the Python model on random files --------------------------------------------
    rnd = random.Random(11)
    for _ in range(600):
        n = rnd.choice((0, 1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 15, 16, 17, 19, 20))
        pool = b'0123456789abcdef\n -x' if rnd.random() < 0.3 else b'0123456789abcdef-' if rnd.random() < 0.6 else b'01234567'
        data = bytes(rnd.choice(pool) for _ in range(n))
        if rnd.random() < 0.5:   # a valid-looking permutation with at most one '-'
            ids = list(b'0123456789abcdef'); rnd.shuffle(ids); ids = ids[:rnd.randrange(0, 17)]
            if rnd.random() < 0.8: ids.insert(rnd.randrange(0, len(ids) + 1), ord('-'))
            data = bytes(ids) + rnd.choice((b'', b'\n'))
        m = PD(fs=data); m.open()
        order = P.parse_pulldown(data)
        err = check_layout(m, order)
        if err: expect(False, f'parser model differs for {data!r}: {err}'); break
    else: expect(True, 'the payload reads 600 random files as the Python model does (shown tiles in order at the slots, the rest hidden; more than eight shown is the default)')
    expect(P.parse_pulldown(None) == default and P.parse_pulldown(b'') == default and P.parse_pulldown(b'01234567\n') == default and P.parse_pulldown(b'\n') == [] and P.parse_pulldown(b'-') == []
           and P.parse_pulldown(b'20-1') == [2, 0] and P.parse_pulldown(b'0-0') == default and P.parse_pulldown(b'0-1-2') == default and P.parse_pulldown(b'8') == [8]
           and P.parse_pulldown(b'a') == [10] and P.parse_pulldown(b'a98-01234567') == [10, 9, 8] and P.parse_pulldown(b'b') == [11] and P.parse_pulldown(b'c') == [12] and P.parse_pulldown(b'dc') == [13, 12] and P.parse_pulldown(b'e') == [14] and P.parse_pulldown(b'g') == default and P.parse_pulldown(b'0123456-7890') == default and P.parse_pulldown('31\n') == [3, 1]
           and P.parse_pulldown(b'01234567a') == default and P.parse_pulldown(b'0123456a') == [0, 1, 2, 3, 4, 5, 6, 10] and P.parse_pulldown(b'01234567-89a\n') == default
           and P.parse_pulldown(b'-0123456789abcdef') == [] and P.parse_pulldown(b'0123456789abcdef-') == default and P.parse_pulldown(b'a' * 16) == default,
           'the Python model: "<shown>[-<hidden>]" over the ids 0-9 and a-e, a bare newline or dash hides all, an invalid file (or more than eight shown) is the default')
    expect(P.format_pulldown(default) == '01234567-89abcdef\n' and P.format_pulldown([]) == '-0123456789abcdef\n' and P.format_pulldown([3, 1]) == '31-02456789abcdef\n' and P.format_pulldown([10, 8]) == 'a8-012345679bcdef\n'
           and all(P.parse_pulldown(P.format_pulldown(o)) == o for o in ([], [0], [7, 6], [4, 0, 2], list(range(7, -1, -1)), [10, 9, 8, 0, 1, 2, 3, 4], [8], [11, 10, 9, 8, 7, 6, 5, 4], [13, 12, 11, 10, 9, 8, 7, 6])) and len(P.format_pulldown([3, 1])) < P.PULLDOWN_FILE_MAX
           and P.PULLDOWN_FILE_MAX == 20 and len(P.format_pulldown([])) < P.PULLDOWN_FILE_MAX and P.PULLDOWN_SLOTS == 8 and len(P.PULLDOWN_TILES) == 16 and P.PULLDOWN_CHARS == '0123456789abcdef',
           'what the page saves is what the parser reads, and fits the file cap')


# ---------------------------------------------------------------------------------------------------------------------------------
# The Settings > Appearance > Control Center page (patch/pulldown.c pulldown_page_opened), tested as menu.py tests the Main Menu page

def page_tests(ctx):
    expect, P = ctx.expect, pod_pages
    n, S = NT, N   # fourteen tiles, eight slots
    DEF_ON, DEF_UP = [True] * S + [False] * (n - S), [False] + [True] * (S - 1) + [False] * (n - S)
    ROW_H = pod_ui.ROW_H
    items = list(P.PULLDOWN_TILES)
    ZX, ZW = 191, 50
    rows_s = PSYMS[f'pod_rows_{P.APPEARANCE_PAGE_INDEX}']
    s_i = next(i for i, r in enumerate(P.APPEARANCE_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.PULLDOWN_PAGE_INDEX)
    sysrows = [r.label for r in P.SETTINGS_PAGE.rows]
    a_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.APPEARANCE_PAGE_INDEX)
    expect(P.SETTINGS_PAGE.rows[a_i].label == 'Appearance' and sysrows[sysrows.index('Display') + 1] == 'Appearance' and sysrows[sysrows.index('Display') + 2] == 'Buttons & Power'
           and P.PAGES[P.APPEARANCE_PAGE_INDEX] is P.APPEARANCE_PAGE and P.APPEARANCE_PAGE.title == 'Appearance' and [r.label for r in P.APPEARANCE_PAGE.rows] == ['Background', 'Accent', 'Control Center', 'Control Labels']
           and P.PAGES[P.PULLDOWN_PAGE_INDEX] is P.PULLDOWN_PAGE and P.PULLDOWN_PAGE.title == 'Control Center' and P.PULLDOWN_PAGE.rows == [] and P.PULLDOWN_PAGE.kind == 'pdcfg',
           'Settings has an Appearance link row after Display; its page has Background and Accent, then Control Center and Control Labels in the second card (Lock Screen is on Display)')
    arrow = lambda m, i: m.click(f'pod_row{i}', x=ZX + ZW // 2)

    def open_page(data=None):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch', 'up') for i in range(n)]
        m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names)}
        m.widgets['pod_scrollview'] = m.alloc(0x180)
        for i in range(n):
            m.widgets[f'pod_row{i}'] = m.alloc(0x180); m.u.mem_write(m.widgets[f'pod_row{i}'], bytes(0x180))
            m.props[(m.widgets[f'pod_up{i}'], 'x')], m.props[(m.widgets[f'pod_up{i}'], 'w')] = ZX, ZW
        m.props[(m.widgets['pod_scrollview'], 'h')] = 398
        if data is not None: m.fs[FILE] = data
        m.call(PSYMS['on_row'], a0=rows_s + 12 * s_i, count=3000000)
        m.log = list(m.calls)
        return m

    def state(m):
        pos = sorted((m.props.get((m.widgets[f'pod_row{i}'], 'y'), i * ROW_H), i) for i in range(n))
        sw = lambda i: [c[2] for c in m.log if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']]
        up = lambda i: bool(m.props.get((m.widgets[f'pod_up{i}'], 'visible'), 1))
        return ([items[i] for _, i in pos], [sw(i)[-1] == 'sset_on' if sw(i) else None for _, i in pos], [up(i) for _, i in pos])

    def run(m, fn):
        log = getattr(m, 'log', [])
        fn()
        m.log = log + m.calls

    m = open_page()
    expect(('window_open', P.PULLDOWN_PAGE.key) in m.calls, 'the Control Center row opens m1plus_pulldown')
    labels, on, up = state(m)
    expect(labels == items and on == DEF_ON and up == DEF_UP, f'default: the eight stock tiles in stock order on, ours after them off, an arrow on each shown row but the first ({labels}, {on}, {up})')
    expect(all(('widget_on', m.widgets['pod_row3'], O[e]) in [c[:3] for c in m.calls] for e in ('EVT_CLICK', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'))
           and not any(c[0] == 'widget_on' and c[1] == m.widgets['pod_up3'] for c in m.calls) and m.names().count('widget_on') == 2 + 4 * n + 1,
           'each row is bound (click, pointer down, up, abort), no arrow is (and the window destroy)')
    expect([c[2] for c in m.calls if c[0] == 'widget_restack'] == list(range(n)), 'the children are restacked in page order')
    m = open_page(b'6502-1347\n')
    labels, on, up = state(m)
    expect(labels == [items[i] for i in (6, 5, 0, 2, 1, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15)] and on == [True] * 4 + [False] * 12 and up == [False, True, True, True] + [False] * 12,
           f'a saved file is laid out as saved: the shown tiles first, the hidden after them ({labels}, {on})')
    for bad in (b'xx', b'0120\n', b'012345678\n', b''):
        m = open_page(bad)
        expect(state(m)[0] == items and state(m)[1] == DEF_ON, f'an invalid file ({bad!r}): the default')
    m = open_page(b'8a\n')
    expect(state(m)[0][:2] == [items[8], items[10]] and state(m)[1][:3] == [True, True, False] and state(m)[2][:3] == [False, True, False], 'a file with ours: Sleep Timer and Equalizer shown first, an arrow on the second')
    m = open_page(b'\n')
    expect(state(m)[1] == [False] * n and not any(state(m)[2]) and state(m)[0] == items, 'a bare newline: every tile off, no arrow')

    # a row's tap shows or hides; saved atomically; shown joins the end
    m = open_page()
    run(m, lambda: m.click('pod_row1'))
    expect(m.fs.get(FILE) == b'0234567-189abcdef\n' and ('rename', TMP, FILE) in m.calls and TMP not in m.fs, f'hide Bluetooth: saved atomically ({m.fs.get(FILE)!r})')
    labels, on, up = state(m)
    expect(labels == [items[i] for i in (0, 2, 3, 4, 5, 6, 7, 1, 8, 9, 10, 11, 12, 13, 14, 15)] and on == [True] * 7 + [False] * 9 and up == [False] + [True] * 6 + [False] * 9, f'it moves to the hidden group, its switch off ({labels}, {on})')
    run(m, lambda: m.click('pod_row1'))
    expect(m.fs.get(FILE) == b'02345671-89abcdef\n' and state(m)[0][7] == 'Bluetooth' and state(m)[1][7] is True, 'and shown again it joins the end')
    for i in range(n): run(m, lambda i=i: m.click(f'pod_row{i}') if P.PULLDOWN_CHARS[i].encode() in m.fs[FILE].split(b'-')[0] else None)
    expect(m.fs.get(FILE) == b'-0123456789abcdef\n' and state(m)[1] == [False] * n and not any(state(m)[2]), 'every tile can be hidden: "-0123456789abcdef", no arrow shows')
    for i in (7, 3, 0): run(m, lambda i=i: m.click(f'pod_row{i}'))
    expect(m.fs.get(FILE) == b'730-1245689abcdef\n' and state(m)[0][:3] == [items[7], items[3], items[0]], f'shown again in the order tapped ({m.fs.get(FILE)!r})')
    m = open_page(); m.fail.add(('write', TMP))
    run(m, lambda: m.click('pod_row1'))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[1] == DEF_ON and TMP not in m.fs, 'a failed save is undone: the file, the order and the switches are as they were')
    m = open_page(); m.fail.add(('rename', FILE))
    run(m, lambda: m.click('pod_row1'))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[1] == DEF_ON, 'a failed rename is undone too')

    # ours: shown at the end like any tile; the ninth is refused with a toast, nothing saved or moved
    m = open_page(b'0123456-789abcdef\n')
    run(m, lambda: m.click('pod_row10'))
    expect(m.fs.get(FILE) == b'0123456a-789bcdef\n' and state(m)[0][7] == items[10] and state(m)[1][7] is True, f'Equalizer is shown at the end (the eighth) ({m.fs.get(FILE)!r})')
    for i in (8, 9): run(m, lambda i=i: m.click(f'pod_row{i}'))
    toasts = [c[1] for c in m.log if c[0] == 'toast']
    expect(toasts == ['Up to 8 controls'] * 2 and m.fs.get(FILE) == b'0123456a-789bcdef\n' and state(m)[1] == [True] * 8 + [False] * 8,
           f'turning on a ninth tile (Sleep Timer, then Settings) is refused with the toast "Up to 8 controls": the file, the order and the switches stay ({toasts})')
    nine = P.format_pulldown([8, 9, 10, 0, 1, 2, 3, 4]).encode()
    m = open_page(nine)
    run(m, lambda: m.click('pod_row5'))
    expect(m.fs.get(FILE) == nine and [c[1] for c in m.log if c[0] == 'toast'] == ['Up to 8 controls'], 'eight shown, ours among them: a ninth is refused there too')
    run(m, lambda: m.click('pod_row9'))
    expect(P.parse_pulldown(m.fs[FILE]) == [8, 10, 0, 1, 2, 3, 4], 'a tile of ours is hidden like any other')
    run(m, lambda: m.click('pod_row5'))
    expect(P.parse_pulldown(m.fs[FILE]) == [8, 10, 0, 1, 2, 3, 4, 5], 'and the room it frees is usable: Playback joins the end of the eight')
    run(m, lambda: m.click('pod_row6'))
    expect(len([c for c in m.log if c[0] == 'toast']) == 2 and P.parse_pulldown(m.fs[FILE]) == [8, 10, 0, 1, 2, 3, 4, 5], 'a failed turn-on saves nothing')
    m = open_page(nine); m.fail.add(('write', TMP))
    run(m, lambda: m.click('pod_row9'))
    expect(m.fs.get(FILE) == nine, 'a failed save of a tile of ours is undone like any other')

    # the arrow: one place up among the shown; saved at once; the first has none and its zone toggles
    m = open_page()
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'01324567-89abcdef\n' and state(m)[0][:4] == [items[i] for i in (0, 1, 3, 2)], f'Gain up: swaps with Buttons lock ({m.fs.get(FILE)!r})')
    run(m, lambda: arrow(m, 3)); run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'30124567-89abcdef\n' and state(m)[2][:2] == [False, True], 'up to the top: the arrow goes away and the next row gets one')
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'0124567-389abcdef\n', 'the top row has no arrow: a tap on that spot is a toggle')
    m = open_page(b'2-01\n')
    run(m, lambda: arrow(m, 5))
    expect(m.fs.get(FILE) == b'25-01346789abcdef\n', f'a hidden row has no arrow: a tap on that spot shows it at the end ({m.fs.get(FILE)!r})')
    m = open_page(); m.fail.add(('write', TMP))
    run(m, lambda: arrow(m, 5))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[2] == DEF_UP, 'a failed save of a move is undone')
    m = open_page(); m.fail.add(('write', TMP)); arrow(m, 3)
    expect(m.names().count('widget_move') == 0 and 'image_base_set_image' not in m.names() and 'widget_invalidate_force' not in m.names(), 'a failed save: the page is not touched')
    m = open_page()
    expect(all((m.widgets[f'pod_up{i}'], 0) in [c[1:3] for c in m.calls if c[0] == 'widget_set_visible'] for i in (0,)) and
           all(m.props[(m.widgets[f'pod_up{i}'], 'sensitive')] == 0 for i in range(n)), 'the first arrow is hidden and every arrow insensitive (a picture; the row decides)')

    # what the page saved is what the hook shows
    m = open_page()
    run(m, lambda: m.click('pod_row2')); run(m, lambda: arrow(m, 6)); run(m, lambda: arrow(m, 6)); saved = m.fs[FILE]
    pm = PD(fs=saved); pm.open()
    expect(saved == b'0136457-289abcdef\n' and check_layout(pm, [0, 1, 3, 6, 4, 5, 7]) is None, f'the pull-down after the page ({saved!r}): the saved tiles in the saved order, Buttons lock hidden')
    again = open_page(saved)
    expect(state(again)[0][:7] == [items[i] for i in P.parse_pulldown(saved)], 'and the page opens with it again')

    # a page that is not ours is left as it is
    for gone in ('pod_scrollview', 'pod_row3', 'pod_up10', 'pod_switch0'):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch', 'up') for i in range(n)]
        m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names) if x != gone}
        m.call(PSYMS['on_row'], a0=rows_s + 12 * s_i, count=3000000)
        expect(('window_open', P.PULLDOWN_PAGE.key) in m.calls and (gone == 'pod_scrollview' or not any(c[0] in ('widget_move', 'widget_set_visible', 'image_base_set_image') for c in m.calls)),
               f'no {gone}: the page opens as the asset has it, nothing moved or bound')

    # -- the assets -----------------------------------------------------------------------------------------------------
    path = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui', P.PULLDOWN_PAGE.key + '.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    rows = [w for w in tree.walk() if w.type == 'list_item']
    expect([r.name for r in rows] == [f'pod_row{i}' for i in range(n)] and [pod_i18n.shown_english(next(c for c in r.children if c.type == 'hscroll_label')) for r in rows] == items,
           'fourteen rows pod_row0..13: the tiles in id order (the stock ones in stock order, then ours), captioned with their short texts')
    for i, r in enumerate(rows):
        swi, upb = r.find(f'pod_switch{i}'), r.find(f'pod_up{i}')
        lab = next(c for c in r.children if c.type == 'hscroll_label')
        expect(swi.get('image') == ('sset_on' if i < S else 'sset_off') and (swi.w, swi.h) == (57, 28) and swi.get('sensitive') == 'false' and swi.x + swi.w == r.w - 12
               and upb.type == 'button' and upb.get('sensitive') == 'false' and (upb.x, upb.w, upb.h) == (ZX, ZW, ROW_H) and upb.x + upb.w == swi.x and lab.x + lab.w <= upb.x,
               f'row {i}: the switch (on for the stock tiles, off for ours), insensitive, 12 px from the right; the arrow zone left of it; the label clear of both')
    keys = {pod_i18n.key_for(t) or t for t in items}   # (AirPlay and DLNA are brands: no key, the same text in every language)
    expect(keys == {'Wi-Fi', 'Bluetooth', 'Button Lock', 'Gain', 'USB Mode', 'Output', 'Playback', 'System', 'powerm_sleep', 'Settings', 'Equalizer', 'Power Off', 'AirPlay', 'DLNA', 'Transfer', 'Screenshot'} and len(keys) == n,
           f'the row labels are our own short texts (Sleep Timer: the stock powerm_sleep), one per tile: {sorted(keys)}')


# ---------------------------------------------------------------------------------------------------------------------------------
# The Settings Files page lists the new file like home-menu

def files_tests(ctx):
    expect, P = ctx.expect, pod_pages
    expect(P.SETTING_FILES.index('pulldown-tiles') == P.SETTING_FILES.index('home-menu') + 1 and P.SETTING_FILES.count('pulldown-tiles') == 1, 'the Settings Files page lists pulldown-tiles right after home-menu (patch/setfiles.c has it in the same place)')
    src = open(os.path.join(ROOT, 'patch', 'setfiles.c')).read()
    expect('{PULLDOWN_FILE, K_MENU}' in src and src.index('{MENU_FILE, K_MENU}') < src.index('{PULLDOWN_FILE, K_MENU}') < src.index('{KBZH_FILE, K_CHAR}'),
           'and shows its first 12 characters like home-menu (the seeded value is checked in homecover.py files_tests)')


# ---------------------------------------------------------------------------------------------------------------------------------
# The "inside settings" flags (stock syssetinto_flag / playsetinto_flag): a settings page left through the top-right Now Playing button stays in the window stack behind
# the player with its flag set, which disables and unbinds its pull-down tile. The hook reconciles the flags with the window stack before the stock init reads them, and
# the call site that opens the page after a tile tap restacks the page that is still there.

SYS, PLAY = pod.DATA['SYSSET_FLAG'][0], pod.DATA['PLAYSET_FLAG'][0]
NAV = {'sysset_page': 'systemset/sysset_page', 'playset_page': 'playset/playset_page'}
FLAG = {'sysset_page': SYS, 'playset_page': PLAY}


# What the stock pages' handlers start and stop (disassembled; docs/modules/settings.md "Stock pages"): page -> event -> (resources started, resources stopped).
# Bluetooth: init 0x4a411c starts discovery (btStartSearch, when Bluetooth is on) and the list timer, 0x12c handler 0x4a2a20 removes the timer and calls btStopSearch, 0x12d handler 0x4a3a28 only rebuilds the list and restores the timer.
# Wi-Fi: init 0x4b1048.. scans (wifi_scan, when Wi-Fi is on) on every open and adds the poll timer, 0x12c handler 0x4afec8 clears the scan countdown and removes the timer, 0x12d handler 0x4b0a34 rebuilds the list and restores the timer.
# Display: a list built once, no 0x12c / 0x12d handler.
STOCK_LIFE = {'bluetooth_page': {'init': (('bt_search', 'bt_timer'), ()), 'bg': ((), ('bt_search', 'bt_timer')), 'fg': (('bt_timer',), ())},
              'wifi_page': {'init': (('wifi_scan', 'wifi_timer'), ()), 'bg': ((), ('wifi_timer',)), 'fg': (('wifi_timer',), ())},
              'display_page': {}}


class SF(PD):
    """The window manager's children as a stack of named windows (the name at +0x10, as the payload reads it), the two flags, and the stock calls the page opening makes."""

    def __init__(self, stack=(), sys=0, play=0, **kw):
        super().__init__(**kw)
        self.stack, self.nav_fail, self.switch_fail, self.seen = [], False, False, None
        self.open_fail = True   # our own page (window_open) will not open: the older tests below run the stock route; playtile_tests opens it (SFO)
        self.run, self.life, self.bt_on, self.wifi_on = set(), [], False, True   # what the stock pages have started (STOCK_LIFE), the events they got, Bluetooth and Wi-Fi enabled
        self.did = []   # every resource start, in order: what init does per open ('wifi_scan', 'bt_search') shows up once per open
        for n in stack: self.push(n)
        self.setword(SYS, sys); self.setword(PLAY, play)

    def push(self, name):
        w = self.alloc(0x40); self.u.mem_write(w, bytes(0x40)); self.setword(w + O['WIDGET_NAME'], self.cstr(name))
        self.stack.append((name, w)); self.sync()

    def sync(self):
        self.children[self.wm] = [w for _, w in self.stack]
        main = [w for n, w in self.stack if 'dialog' not in n]
        self.top_main = main[-1] if main else 0

    def event(self, page, ev):
        """One stock lifecycle event of a stock page (STOCK_LIFE): init on a new open, 'bg' = EVT_WINDOW_TO_BG (0x12c), 'fg' = EVT_WINDOW_TO_FG (0x12d)."""
        self.life.append((page, ev))
        if page not in STOCK_LIFE or ev not in STOCK_LIFE[page]: return
        start, stop = STOCK_LIFE[page][ev]
        start = [r for r in start if (r != 'bt_search' or self.bt_on) and (r != 'wifi_scan' or self.wifi_on)]
        self.did += start
        self.run |= set(start)
        self.run -= set(stop)

    def names_(self): return [n for n, _ in self.stack if 'dialog' not in n]
    def flags(self): return (self.word(SYS), self.word(PLAY))
    def name_of(self, w): return next((n for n, h in self.stack if h == w), None)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        if name == 'stock_pulldown_resume':
            self.seen = self.flags()   # what the stock init's tile visitor reads
            return super()._hook(u, address, size, _)
        elif name == 'window_manager_get_top_window':
            ret = self.stack[-1][1] if self.stack else 0
        elif name == 'window_manager_switch_to':
            self.calls.append(('switch_to', self.name_of(a1), self.name_of(a2), a3))
            ret = 1
            if not self.switch_fail and a0 == self.wm:
                ent = next(e for e in self.stack if e[1] == a2); old = self.name_of(a1)
                self.stack.remove(ent); self.stack.append(ent); self.sync(); ret = 0
                self.event(old, 'bg')   # window_manager_switch_to with a3 0 (0x678a04): EVT_WINDOW_TO_BG (0x12c) to the window left, then the old window is not closed
                self.calls.append(('to_fg', ent[0])); self.event(ent[0], 'fg')   # and EVT_WINDOW_TO_FG (0x12d) (0x6789e8) to the restacked window
        elif name == 'window_open' and self.read_cstr(a0).startswith(('m1plus_playset', 'm1plus_ps')):   # (other assets: the base machine's)
            asset = self.read_cstr(a0); self.calls.append(('window_open', asset)); ret = 0
            if not self.open_fail:   # a Playback Settings page of ours: its window is named by the asset's root (<asset>_page), stacked on top
                self.push(asset + '_page'); ret = self.stack[-1][1]
        elif name == 'window_close' and self.name_of(a0):   # a window of the stack: it leaves the stack
            self.calls.append(('window_close', self.name_of(a0))); ret = 0
            self.stack.remove(next(e for e in self.stack if e[1] == a0)); self.sync()
        elif name == 'navigator_to':
            page = self.read_cstr(a0); self.calls.append(('navigator_to', page)); ret = 0x10
            if not self.nav_fail:
                short = page.split('/')[-1]; self.push(short); ret = 0; self.event(short, 'init')   # a new window: its init runs
                if short in FLAG: self.setword(FLAG[short], 1)   # the page's init
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def pulldown(self):
        """The swipe: the dialog is built over the stack (flags reconciled, then the stock init reads them)."""
        self.push('dropdown_dialog'); self.open(); self.seen_now = self.seen
        self.stack = [e for e in self.stack if e[0] != 'dropdown_dialog']; self.sync()   # the modal dialog quits
        return self.seen

    def tap(self, page):
        """A tile tap on a tile the stock handler took: flag 2, dialog quit; the caller's call opens the page."""
        self.setword(FLAG[page], 2)
        return self.call(PSYMS['pd_open_settings'], a0=self.cstr(NAV[page]), count=3000000)

    def back(self):
        """The page's Back handler: clears a positive flag, closes the front window."""
        n, _ = self.stack[-1]
        if n in FLAG and self.word(FLAG[n]) > 0: self.setword(FLAG[n], 0)
        self.stack.pop(); self.sync()


def flags_tests(ctx):
    expect = ctx.expect
    P, S, R, H = 'playing_page', 'sysset_page', 'playset_page', 'home_page'
    RN = 'm1plus_radionp'

    def seen(stack, sys=0, play=0, **kw):
        m = SF(stack, sys, play, **kw); return m.pulldown(), m

    # -- the stock init reads the reconciled flags
    f, _ = seen([H, S, P], sys=1)
    expect(f == (0, 0), f'System Settings behind the player: its flag is 0 when the stock init binds the tile ({f})')
    f, _ = seen([H, R, P], play=1)
    expect(f == (0, 0), f'Playback Settings behind the player: flag 0 ({f})')
    f, _ = seen([H, S, RN], sys=1)
    expect(f == (0, 0), f'behind Radio Now Playing: flag 0 ({f})')
    f, _ = seen([H, S], sys=1)
    expect(f == (1, 0), f'the settings page in front: stock, its flag stays 1 and the tile stays disabled ({f})')
    f, _ = seen([H, R], play=1)
    expect(f == (0, 1), f'Playback Settings in front: flag stays 1 ({f})')
    f, _ = seen([H, S, 'display_page'], sys=1)
    expect(f == (1, 0), f'a sub-page over the settings page: still inside settings, flag stays 1 ({f})')
    f, _ = seen([H, S, R], sys=1, play=1)
    expect(f == (1, 1), f'System Settings -> Playback sub-page: both flags stay 1 ({f})')
    f, _ = seen([H, S, R, P], sys=1, play=1)
    expect(f == (0, 0), f'System Settings -> Playback sub-page -> Now Playing leaves both flags 1 in stock; both pages are behind the player now, both 0 ({f})')
    f, _ = seen([H, S, R], sys=0, play=0)
    expect(f == (1, 1), f'back from the player to the sub-page: both pages are live again, both 1 ({f})')
    f, _ = seen([H, S], sys=0)
    expect(f == (1, 0), f'back from the player to the settings page: flag 1 again, the tile disabled as stock ({f})')
    f, _ = seen([H], sys=1, play=1)
    expect(f == (0, 0), f'no settings window at all (a stale flag): both 0 ({f})')
    f, _ = seen([H], sys=2, play=2)
    expect(f == (0, 0), f'a flag left at 2 by a page that failed to open: 0 ({f})')
    f, _ = seen([H, S], sys=2)
    expect(f == (1, 0), f'a flag at 2 with the page in front: 1 ({f})')
    f, _ = seen([S, H], sys=1)
    expect(f == (0, 0), f'a settings window left under Home: not inside settings, 0 ({f})')
    f, _ = seen([S, H], sys=0)
    expect(f == (0, 0), f'and it is not revived under Home ({f})')
    f, _ = seen([H, S, P, 'albuminfo_page'], sys=1)
    expect(f == (0, 0), f'the player between the settings page and the front: 0 ({f})')
    m = SF([H, S], sys=1); m.home_opened = 0; m.pulldown()
    expect(m.seen == (0, 0), 'a settings window that is not (or no longer) opened, still closing after Back, is not inside settings')
    m = SF([H, S, P], sys=1); m.init_ret = 5; m.pulldown()
    expect(m.seen == (0, 0), 'a stock init that fails is still run with the reconciled flags')

    # -- the tile tap opens the page
    for page in (S, R):
        m = SF([H, page, P]); fl = FLAG[page]
        r = m.tap(page)
        sw = [c for c in m.calls if c[0] == 'switch_to']
        expect(r == 0 and sw == [('switch_to', P, page, 0)] and not [c for c in m.calls if c[0] == 'navigator_to'] and m.names_() == [H, P, page] and m.word(fl) == 1,
               f'{page} behind the player: its window is restacked in front (switch_to, nothing closed), no second page, flag 1 ({sw}, {m.names_()}, {m.word(fl)})')
        m.back()
        expect(m.names_() == [H, P] and m.word(fl) == 0, f'Back from it: stock clears the flag and returns to the player ({m.names_()})')
        m = SF([H], 0, 0); r = m.tap(page)
        expect(r == 0 and [c for c in m.calls if c[0] in ('navigator_to', 'switch_to')] == [('navigator_to', NAV[page])] and m.names_() == [H, page] and m.word(fl) == 1,
               f'{page} gone: opened fresh by the stock call')
        m = SF([H], 0, 0); m.nav_fail = True; r = m.tap(page)
        expect(r == 0x10 and m.word(fl) == 0, f'{page} that will not open: the failure is returned and the flag is not left at 2 ({r:#x}, {m.word(fl)})')
        m = SF([H, page, P]); m.switch_fail = True; r = m.tap(page)
        expect(r == 0 and [c[0] for c in m.calls if c[0] in ('switch_to', 'navigator_to')] == ['switch_to', 'navigator_to'] and m.word(fl) == 1,
               'a restack that fails falls back to the stock open')
    m = SF([H]); r = m.call(PSYMS['pd_open_settings'], a0=m.cstr('systemset/display_page'), count=3000000)
    expect(r == 0 and [c for c in m.calls if c[0] in ('navigator_to', 'switch_to')] == [('navigator_to', 'systemset/display_page')] and m.flags() == (0, 0),
           'any other page is the stock call, flags untouched')

    # -- repeated cycles: page -> Now Playing -> pull-down -> tile -> Back, in both visit orders, never a second window
    for first, second in ((S, R), (R, S)):
        m = SF([H])
        m.call(PSYMS['pd_open_settings'], a0=m.cstr(NAV[first]), count=3000000)   # (flag 1 by the page's init)
        m.push(second); m.setword(FLAG[second], 1)                                 # the other settings page opened from it
        m.push(P)                                                                  # top-right Now Playing: switch_to with nothing closed
        for cycle in range(3):
            f = m.pulldown()
            expect(f == (0, 0), f'cycle {cycle} ({first} then {second}): both tiles enabled behind the player ({f})')
            m.tap(first)
            expect(m.names_()[-1] == first and sorted(m.names_()) == sorted([H, first, second, P]) and m.word(FLAG[first]) == 1,
                   f'cycle {cycle}: the first page is in front, the stack unchanged in size ({m.names_()}, {m.flags()})')
            f = m.pulldown()
            expect(f[0 if first == S else 1] == 1, f'cycle {cycle}: with the page in front its own tile is disabled again ({f})')
            m.back()   # to the player
            expect(m.names_()[-1] == P, f'Back returns to the player ({m.names_()})')
        m.tap(second)
        expect(m.names_() == [H, P, second] and m.word(FLAG[second]) == 1, f'{second}, still behind the player, comes forward too ({m.names_()})')

    # -- the build
    d = built_demo_bytes(); image = bytearray(d)
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]
    stock = stock_demo_bytes()
    sw = lambda a: struct.unpack_from('<I', stock, pod.fileoff(stock, a))[0]
    jal = 0x0c000000 | (PSYMS['pd_open_settings'] >> 2)
    sites = pod.PULLDOWN_OPEN_SITES
    expect(sites == (0x4cd894, 0x4cd8bc) and [sw(a) for a in sites] == [0x0411113a, 0x04111130] and [word(a) for a in sites] == [jal] * 2,
           'the two navigator_to calls after the pull-down dialog quits (flag 2) are jal pd_open_settings in the build; stock has bal navigator_to')
    expect([word(a + 4) for a in sites] == [0x24849a64, 0x24849a7c] and word(0x4cd878) == 0x8f82a95c and word(0x4cd888) == 0x8f82a96c,
           'their delay slots (a0 = "playset/playset_page", "systemset/sysset_page") and the flag loads around them are stock\'s')
    expect(MANIFEST['hook_pulldown_open'] == {'sites': [hex(a) for a in sites], 'target': PSYMS['pd_open_settings']}, 'the manifest records the call sites')
    expect(pod.DATA['SYSSET_FLAG'] == (0xa05a48, 'syssetinto_flag') and pod.DATA['PLAYSET_FLAG'] == (0xa05a4c, 'playsetinto_flag'), 'the flags are stock\'s two words')
    expect(all(word(a) == old for a, old, _ in pod.PULLDOWN_PINS) and any(a == 0x4754f4 for a, _, _ in pod.PULLDOWN_PINS) and any(a == 0x475584 for a, _, _ in pod.PULLDOWN_PINS),
           'the tile handlers\' flag tests (they reject a nonzero flag; stock is untouched) are pinned with the rest')


def playtile_tests(ctx):
    """The Playback tile opens our Playback Settings page (m1plus_playset_page), not stock's list; the flag follows our page, its sub-pages and stock's list; the System tile is as before."""
    expect = ctx.expect

    def SFO(*a, **kw):
        m = SF(*a, **kw); m.open_fail = False; return m
    P, S, R, H, O = 'playing_page', 'sysset_page', 'playset_page', 'home_page', 'm1plus_playset_page'
    own = lambda m: [c for c in m.calls if c[0] in ('window_open', 'navigator_to', 'switch_to')]
    seen = lambda stack, **kw: (lambda m: (m.pulldown(), m))(SFO(stack, **kw))

    m = SFO([H]); r = m.tap(R)
    expect(r == 0 and own(m) == [('window_open', 'm1plus_playset')] and m.names_() == [H, O] and m.word(PLAY) == 1,
           f'no page open: the Playback tile opens our page, stock\'s list is not asked for ({own(m)}, {m.names_()}, {m.word(PLAY)})')
    m.back()
    m = SFO([H, O, P]); r = m.tap(R)
    expect(r == 0 and own(m) == [('switch_to', P, O, 0)] and m.names_() == [H, P, O] and m.word(PLAY) == 1,
           f'ours behind Now Playing: restacked, not opened twice ({own(m)}, {m.names_()})')
    closed = lambda m: [c[1] for c in m.calls if c[0] == 'window_close']
    m = SFO([H, O, 'm1plus_psmode_page', P]); r = m.tap(R)
    expect(r == 0 and own(m) == [('switch_to', P, O, 0)] and closed(m) == ['m1plus_psmode_page'] and m.names_() == [H, P, O],
           f'a picker of ours below the player: closed, then our page restacked, so the picker cannot be opened twice ({closed(m)}, {m.names_()})')
    m = SFO([H, O, 'm1plus_psbootvol_page', P, 'lyric_page']); r = m.tap(R)
    expect(r == 0 and closed(m) == ['m1plus_psbootvol_page'] and m.names_() == [H, P, 'lyric_page', O],
           f'a slider page below the player: closed, the windows above the player are left ({closed(m)}, {m.names_()})')
    m = SFO([H, O, 'm1plus_psmode_page', 'm1plus_psx_page', P]); r = m.tap(R)
    expect(closed(m) == ['m1plus_psx_page', 'm1plus_psmode_page'] and m.names_() == [H, P, O], f'two sub-pages: both closed, the topmost first ({closed(m)})')
    m = SFO([H, O, 'm1plus_psvolume_page', 'm1plus_psmaxvol_page', P]); r = m.tap(R)
    expect(closed(m) == ['m1plus_psmaxvol_page', 'm1plus_psvolume_page'] and m.names_() == [H, P, O], f'Volume & Sound and a slider page below the player: both closed, the hub restacked ({closed(m)}, {m.names_()})')
    m = SFO([H, O, P]); r = m.tap(R)
    expect(closed(m) == [], f'no sub-page: nothing is closed ({closed(m)})')
    m = SFO([H, S, 'display_page', P]); r = m.tap(S)
    expect(closed(m) == [] and m.names_() == [H, 'display_page', P, S], f'System: stock\'s sub-pages are left as before ({closed(m)}, {m.names_()})')
    m = SFO([H]); m.open_fail = True; r = m.tap(R)
    expect(r == 0 and own(m) == [('window_open', 'm1plus_playset'), ('navigator_to', NAV[R])] and m.names_() == [H, R] and m.word(PLAY) == 1,
           f'our page that will not open: the stock call, as before ({own(m)})')
    m = SFO([H]); m.open_fail = True; m.nav_fail = True; r = m.tap(R)
    expect(r == 0x10 and m.word(PLAY) == 0, f'neither opens: the failure is returned and the flag is not left at 2 ({r:#x}, {m.word(PLAY)})')
    m = SFO([H, R, P]); r = m.tap(R)
    expect(r == 0 and own(m) == [('window_open', 'm1plus_playset')] and m.names_() == [H, R, P, O],
           f'stock\'s list left behind the player (reached from stock Home): the tile opens ours ({m.names_()})')

    # -- the flag
    f, _ = seen([H, O], play=0)
    expect(f == (0, 1), f'our page in front: flag 1, the tile disabled ({f})')
    f, _ = seen([H, O, 'm1plus_psmode_page'])
    expect(f == (0, 1), f'a picker of ours in front: flag 1 ({f})')
    f, _ = seen([H, O, 'm1plus_psmaxvol_page'])
    expect(f == (0, 1), f'a slider page of ours in front: flag 1 ({f})')
    f, _ = seen([H, O, 'm1plus_psvolume_page', 'm1plus_psmaxvol_page'])
    expect(f == (0, 1), f'a slider page over Volume & Sound over the hub: flag 1, the tile stays disabled on the sub-pages too ({f})')
    f, _ = seen([H, O, 'm1plus_psoutput_page'])
    expect(f == (0, 1), f'the Output page in front: flag 1 ({f})')
    f, _ = seen([H, O, 'm1plus_psoutput_page', P], play=1)
    expect(f == (0, 0), f'the player above Output: flag 0, the tile live ({f})')
    f, _ = seen([H, O, P], play=1)
    expect(f == (0, 0), f'the player above our page: flag 0, the tile live ({f})')
    f, _ = seen([H, O, 'm1plus_psmode_page', 'm1plus_radionp'])
    expect(f == (0, 0), f'Radio Now Playing above our picker: 0 ({f})')
    f, _ = seen([O, H])
    expect(f == (0, 0), f'our page left under Home: 0 ({f})')
    f, _ = seen([H, R], play=1)
    expect(f == (0, 1), f'stock\'s list reached from stock Home: flag 1 as before ({f})')
    f, _ = seen([H, R, P], play=1)
    expect(f == (0, 0), f'stock\'s list behind the player: 0 ({f})')
    f, _ = seen([H, R, P, O])
    expect(f == (0, 1), f'stock\'s list under the player with ours in front: 1 ({f})')
    f, _ = seen([H, O, P, R])
    expect(f == (0, 1), f'ours under the player with stock\'s list in front: 1 ({f})')
    m = SFO([H, O], play=1); m.home_opened = 0; m.pulldown()
    expect(m.seen == (0, 0), 'our page that is not opened (closing after Back) is not inside settings')
    f, _ = seen([H, S, O], sys=1)
    expect(f == (1, 1), f'System Settings -> our Playback page: both flags 1 ({f})')
    f, _ = seen([H, S, O, P], sys=1)
    expect(f == (0, 0), f'both behind the player: 0, 0 ({f})')

    # -- the System tile is as before
    m = SFO([H]); r = m.tap(S)
    expect(r == 0 and own(m) == [('navigator_to', NAV[S])] and m.names_() == [H, S] and m.word(SYS) == 1, 'System: no page open, the stock call')
    m = SFO([H, S, P]); r = m.tap(S)
    expect(r == 0 and own(m) == [('switch_to', P, S, 0)] and m.names_() == [H, P, S], 'System: restacked behind the player')


# ---------------------------------------------------------------------------------------------------------------------------------
# The tiles of ours (Sleep Timer, Settings, Equalizer): the widgets in the asset, their place, and what a tap does (docs/modules/pulldown.md "Tiles of ours")

OWN = (('pod_tile_sleep', 'pod_cap_sleep', 'drop_sleep', 'Sleep Timer', 8), ('pod_tile_settings', 'pod_cap_settings', 'drop_settings', 'Settings', 9), ('pod_tile_eq', 'pod_cap_eq', 'drop_equalizer', 'Equalizer', 10), ('pod_tile_power', 'pod_cap_power', 'drop_power', 'Power Off', 11), ('pod_tile_transfer', 'pod_cap_transfer', 'drop_transfer', 'Wi-Fi Transfer', 14), ('pod_tile_shot', 'pod_cap_shot', 'drop_shot', 'Screenshot', 15))
QUIT = 0xd


class PT(SF):
    """A pull-down with a tap: dialog_quit and airplayGetFlag are mocked, and the modal navigator_to of the dialog returns dialog_ret (0xd: a tile quit it)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.quit_ret, self.airplay, self.dialog_ret = 0, 0, QUIT
        self.open_fail = False

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0 = u.reg_read(UC_MIPS_REG_A0)
        if name == 'dialog_quit':
            self.calls.append(('dialog_quit', a0, u.reg_read(UC_MIPS_REG_A1))); ret = self.quit_ret
        elif name == 'airplayGetFlag': ret = self.airplay
        elif name in ('stop_player', 'switch_wifitransport'): self.calls.append((name, a0)); ret = 0   # (the Wi-Fi Transfer page's init: wt_opened)
        elif name in ('airplay_switch', 'dlna_switch'):   # stock's own switch: flip the setting byte (the ini write is its tail call, not modelled)
            addr = pod.DATA['AIRPLAY_FLAG' if name == 'airplay_switch' else 'DLNA_FLAG'][0]
            self.calls.append((name,)); self.u.mem_write(addr, bytes([self.u.mem_read(addr, 1)[0] ^ 1])); ret = 0
        elif name == 'awake_screen': self.calls.append(('awake_screen', self.word(pod.DATA['STANDBY_MODE'][0]))); ret = 0   # (standby_mode as it is when the screen is lit)
        elif name == 'getFormatString':
            self.calls.append(('getFormatString', self.read_cstr(a0), u.reg_read(UC_MIPS_REG_A2))); self.u.mem_write(u.reg_read(UC_MIPS_REG_A1), b'Confirm Shutdown?\0'); ret = 0
        elif name == 'navigator_to' and self.read_cstr(a0) == 'dialog/dropdown_dialog':
            self.calls.append(('navigator_to', 'dialog/dropdown_dialog')); ret = self.dialog_ret
        else: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def swipe(self, shown):
        """The pull-down built with the file `shown` saved."""
        self.fs[FILE] = shown; self.pulldown()

    def tap(self, name):
        """The click on the tile's image, as AWTK runs the handler the payload bound: the calls of the handler alone."""
        self.click(name); return list(self.calls)

    def modal(self):
        """What on_wm_tsmove_fun's navigator_to("dialog/dropdown_dialog") now runs: the stock call, then the pending action. Its calls and result."""
        ret = self.call(PSYMS['pd_open_dialog'], a0=self.cstr('dialog/dropdown_dialog'), count=3000000); return ret, list(self.calls)


def own_tests(ctx):
    expect, P = ctx.expect, pod_pages
    # -- the asset: ours are in view_switchs, hidden and insensitive, in the stock tile's size and the caption's look
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    view, ref = tree.find('view_switchs'), tree.find('label_playset')
    for img, cap, pic, key, _ in OWN:
        wi, wc = tree.find(img), tree.find(cap)
        smaller = key == 'Screenshot'   # (15 px: the word is 74 px wide at 16 in the 71 px text width, tools/mod_pulldown.py CAPTION_OWN_PX)
        skip = lambda p: p[0].endswith(':font_size') and smaller
        same = [p for p in ref.props if p[0] != 'name' and not skip(p)] == [p for p in wc.props if p[0] not in ('name', 'tr_text', 'text', 'visible', 'sensitive') and not skip(p)]
        if smaller: expect({p[1] for p in wc.props if p[0].endswith(':font_size')} == {'15'}, 'the Screenshot caption is 15 px')
        expect(wi in view.children and wc in view.children and (wi.w, wi.h) == (56, 56) and wi.get('image') == pic and wi.get('clickable') == 'true' and (wi.get('visible'), wi.get('sensitive')) == ('false', 'false')
               and (wc.w, wc.h) == (71, 36) and (wc.x - wi.x, wc.y - wi.y) == (-7, 61) and (wc.get('visible'), wc.get('sensitive')) == ('false', 'false') and wc.get('tr_text') == pod_i18n.key_for(key) and same,
               f'{img}: a hidden, insensitive 56 x 56 clickable image of {pic} and a caption {key!r} (71 x 36, -7 / +61, the style of the stock captions) in view_switchs')
        expect(asset_image(pic).size == (56, 56), f'{pic}.png is a 56 x 56 disc image')
    expect({pod_i18n.key_for(t) for t in ('Sleep Timer', 'Settings', 'Equalizer', 'Power Off')} == {'powerm_sleep', 'Settings', 'Equalizer', 'Power Off'}, 'the captions are keys of ours (Sleep Timer: the stock powerm_sleep): translated in every language')

    # -- the slots: a shown tile of ours takes its slot with its caption, is visible, sensitive and bound; the others of ours stay hidden
    for fs, order in ((b'8\n', [8]), (b'a9\n', [10, 9]), (b'0123456a\n', [0, 1, 2, 3, 4, 5, 6, 10]), (b'a-01234567\n', [10]), (b'9831a-0\n', [9, 8, 3, 1, 10]), (b'7654321a-089\n', [7, 6, 5, 4, 3, 2, 1, 10])):
        m = PD(fs=fs); m.open()
        err = check_layout(m, order)
        bound = {n for n in IMG[8:] if (m.widgets[n], O['EVT_CLICK']) in m.bound}
        expect(err is None and bound == {IMG[t] for t in order if t >= 8}, f'{fs!r}: {order} shown at the slots, ours visible and bound, the others of ours hidden ({err}, {sorted(bound)})')
        expect(not any(c[0] == 'widget_on' and c[1] == m.widgets[IMG[t]] for c in m.calls for t in range(2, 8)), f'{fs!r}: no stock tile besides Wi-Fi/BT hold is bound again (stock bound them)')
    m = PD(fs=None); m.open()
    expect(m.touched() == [] and {c[1] for c in m.calls if c[0] == 'widget_on' and c[2] == O['EVT_CLICK']} == {m.widgets[IMG[0]], m.widgets[IMG[1]]},
           'the default: nothing moved, ours stay hidden as the asset has them, only Wi-Fi and Bluetooth get the hold click guard')
    m = PD(fs=b'9\n'); m.widget_on_fail = frozenset({O['EVT_CLICK']}); m.open()
    expect(m.hidden(IMG[9]) and m.hidden(LAB[9]), 'a tile of ours whose tap cannot be bound is hidden, not shown dead')
    for gone in ('pod_tile_eq', 'pod_cap_settings'):
        m = PD(fs=b'a\n', gone=(gone,)); m.open()
        expect(m.touched() == [], f'an asset without {gone} (not our dialog): the stock layout, nothing moved')

    # -- a tap quits the dialog the way stock's tile handlers do (dialog_quit(dialog, 0xd)); the page opens after the modal call returns
    H, P_, SET, PEQ, SL = 'home_page', 'playing_page', 'm1plus_settings_page', 'm1plus_peq_page', 'm1plus_sleeptimer_page'
    pages = lambda c: [x for x in c if x[0] in ('window_open', 'navigator_to', 'switch_to', 'window_close')]
    for img, _, _, _, tid in OWN:
        m = PT([H]); m.swipe(b'0123456' + P.PULLDOWN_CHARS[tid].encode() + b'\n')
        calls = m.tap(img)
        expect(calls == [('dialog_quit', m.dlg, QUIT)], f'{img}: the tap quits the dialog with 0xd and opens nothing itself ({calls})')
    m = PT([H]); m.swipe(b'8\n'); m.tap('pod_tile_sleep'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_sleeptimer')],
           f'Sleep: after the modal call our Sleep Timer page opens (open_page(POD_SLEEPTIMER_PAGE)), never the stock Power page ({pages(calls)})')
    # Sleep Timer tile lit art: drop_sleepopen while a timer runs (sleepflag != 0 and sleep_time > 0), drop_sleep otherwise; still opens the page on tap
    expect(asset_image('drop_sleepopen').size == (56, 56) and 'drop_sleepopen' in palette.ACCENT_DISC and 'drop_sleep' not in palette.ACCENT_DISC,
           'drop_sleepopen.png is a 56 x 56 disc image and takes the accent disc like the other lit tiles')
    a = asset_image('drop_sleepopen').convert('RGBA'); b = asset_image('drop_sleep').convert('RGBA')
    expect(a.getpixel((28, 4))[:3] == (255, 255, 255) and a.getpixel((28, 4))[3] == 255 and b.getpixel((28, 4))[:3] == (0x2C, 0x2C, 0x2E) and b.getpixel((28, 4))[3] == 255,
           'drop_sleepopen: flat white disc; drop_sleep: flat #2C2C2E disc')
    for flag, secs, want_pic in ((0, 0, 'drop_sleep'), (1, 0, 'drop_sleep'), (0, 900, 'drop_sleep'), (1, 900, 'drop_sleepopen')):
        m = PT([H]); m.u.mem_write(pod.DATA['SLEEP_FLAG'][0], bytes([flag])); m.setword(pod.DATA['SLEEP_TIME'][0], secs)
        m.swipe(b'8\n')
        art = [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets['pod_tile_sleep']]
        expect(art == [want_pic], f'Sleep Timer ({flag}, {secs}): tile image is {want_pic} ({art})')
    ret, calls = m.modal()   # (still an action: tapping the lit tile opens the Sleep Timer page)
    m = PT([H]); m.u.mem_write(pod.DATA['SLEEP_FLAG'][0], b'\1'); m.setword(pod.DATA['SLEEP_TIME'][0], 900); m.swipe(b'8\n'); m.tap('pod_tile_sleep'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_sleeptimer')], 'tapping the lit Sleep Timer tile still opens the Sleep Timer page')
    ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'the action runs once: the next modal call (a stock tile) opens nothing of ours')
    m = PT([H, SL, P_]); m.swipe(b'8\n'); m.tap('pod_tile_sleep'); ret, calls = m.modal()
    expect(pages(calls)[1:] == [('switch_to', P_, SL, 0)] and m.names_() == [H, P_, SL], f'a Sleep Timer page left behind the player is brought to the front, not stacked twice ({pages(calls)})')
    m = PT([H, SL]); m.swipe(b'8\n'); m.tap('pod_tile_sleep'); ret, calls = m.modal()
    expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')] and m.names_() == [H, SL], 'the Sleep Timer page already in front is left alone')
    m = PT([H]); m.swipe(b'8\n'); m.windows = {'m1plus_sleeptimer': 0}; m.tap('pod_tile_sleep'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_sleeptimer')] and m.names_() == [H], 'a Sleep Timer page that will not open: nothing else happens, the result is the dialog\'s')
    WT = 'm1plus_wifitransfer_page'
    m = PT([H]); m.swipe(b'e\n'); m.net = 1; m.tap('pod_tile_transfer'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_wifitransfer')], f'Wi-Fi Transfer: with Wi-Fi up our Wi-Fi Transfer page opens, its init stops the player and starts the server once ({pages(calls)})')
    expect([c[0] for c in calls if c[0] in ('stop_player', 'switch_wifitransport')] == ['stop_player', 'switch_wifitransport'], f'the page init ran once ({calls})')
    m = PT([H]); m.swipe(b'e\n'); m.net = 0; m.tap('pod_tile_transfer'); ret, calls = m.modal()
    expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')] and toasts(m) == ['Connect to Wi-Fi first'], f'Wi-Fi Transfer without Wi-Fi: the toast, no page ({pages(calls)})')
    m = PT([H, WT, P_]); m.swipe(b'e\n'); m.net = 1; m.tap('pod_tile_transfer'); ret, calls = m.modal()
    expect(pages(calls)[1:] == [('switch_to', P_, WT, 0)] and m.names_() == [H, P_, WT], f'a Wi-Fi Transfer page left behind the player is brought to the front, not stacked twice ({pages(calls)})')
    expect(not [c for c in calls if c[0] == 'stop_player'], 'a restacked page does not run wt_opened (stop_player) again')
    m = PT([H, WT]); m.swipe(b'e\n'); m.net = 1; m.tap('pod_tile_transfer'); ret, calls = m.modal()
    expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'the Wi-Fi Transfer page already in front is left alone')
    m = PT([H]); m.swipe(b'f\n'); m.tap('pod_tile_shot'); ret, calls = m.modal()
    expect(ret == QUIT and ('confirm', 'Take a screenshot?', 5) in calls and [c for c in calls if c[0] == 'navigator_to_with_context'] and not [c for c in pages(calls) if c[0] == 'window_open'], f'Screenshot: shot_start asks "Take a screenshot?", the Developer row\'s confirm, and opens no page ({calls})')
    # the Network Services row and the tile share one window: the tile opens it, Now Playing comes in front (the server stops), the row restacks it (no second open, wt_opened once) and the server is up again
    m = PT([H]); m.swipe(b'e\n'); m.net = 1; m.widgets['btn_backtoplayer'] = 0x31000000; m.tap('pod_tile_transfer'); m.modal(); log = list(m.calls)
    m.push(WT)   # (the harness's window_open does not stack the page: an entry of that name stands for it)
    m.click('btn_backtoplayer'); log += m.calls; m.push(P_)   # Now Playing: wt_on_player stops the server
    row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, pod_pages.ACT_NETTRANS); m.setword(row + 8, pod_pages.WIFITRANSFER_PAGE_INDEX)
    m.call(PSYMS['on_row'], a0=row, count=6000000); calls = list(m.calls); log += calls   # (each call starts a fresh list)
    expect(m.names_().count(WT) == 1 and m.names_() == [H, P_, WT] and ('window_open', 'm1plus_wifitransfer') not in calls and ('switch_to', P_, WT, 0) in pages(calls),
           f'Network Services > Wi-Fi Transfer with the page behind the player: restacked, never a second window ({pages(calls)}, {m.names_()})')
    expect([c[0] for c in log].count('stop_player') == 1 and not [c for c in calls if c[0] in ('stop_player', 'switch_wifitransport')], 'wt_opened ran once (the player is not stopped again by the restack)')
    m.fire(0x12d, m.window); log += m.calls   # the window manager's EVT_WINDOW_TO_FG to the restacked page
    sw = [c for c in log if c[0] == 'switch_wifitransport']
    expect(sw == [('switch_wifitransport', 1), ('switch_wifitransport', 0), ('switch_wifitransport', 1)], f'the file server is up again after the restack (wt_front) ({sw})')
    m = PT([H]); m.swipe(b'9\n'); m.tap('pod_tile_settings'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_settings')], f'Settings: our Settings page is opened (open_page(POD_SETTINGS_PAGE)) ({pages(calls)})')
    m = PT([H, SET, 'm1plus_display_page', P_]); m.swipe(b'9\n'); m.tap('pod_tile_settings'); ret, calls = m.modal()
    expect(pages(calls)[1:] == [('window_close', 'm1plus_display_page'), ('switch_to', P_, SET, 0)] and m.names_() == [H, P_, SET],
           f'Settings already in the stack: its sub-pages are closed, then it is brought to the front (never a second instance) ({pages(calls)})')
    m = PT([H, SET]); m.swipe(b'9\n'); m.tap('pod_tile_settings'); ret, calls = m.modal()
    expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'Settings already in front: left alone')
    m = PT([H]); m.swipe(b'a\n'); m.tap('pod_tile_eq'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_peq')], f'Equalizer: the Equalizer page the All Playback Settings row opens ({pages(calls)})')
    m = PT([H, PEQ, 'm1plus_peqp_page', P_]); m.swipe(b'a\n'); m.tap('pod_tile_eq')
    h = {n: w for n, w in m.stack}; m.call(PSYMS['pd_note_opener'], a0=h['m1plus_peqp_page'], a1=h[PEQ])   # (opened from the Equalizer page, as open_page notes it)
    ret, calls = m.modal()
    expect(pages(calls)[1:] == [('window_close', 'm1plus_peqp_page'), ('switch_to', P_, PEQ, 0)], f'Equalizer already in the stack: the sub-pages it opened are closed, brought to the front ({pages(calls)})')
    m = PT([H, PEQ, 'm1plus_peqp_page', P_]); m.swipe(b'a\n'); m.tap('pod_tile_eq'); ret, calls = m.modal()
    expect(pages(calls)[1:] == [('switch_to', P_, PEQ, 0)] and 'm1plus_peqp_page' in m.names_(), f'a window above the Equalizer that it did not open is not closed ({pages(calls)})')
    m = PT([H]); m.swipe(b'a\n'); m.windows = {'m1plus_peq': 0}; m.tap('pod_tile_eq'); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', 'm1plus_peq')], 'a page of ours that will not open: no further call, no crash')
    # the same conditions as stock's tile handlers (0x4754c8): a tile does nothing while they hold
    for what, setup in (('DROPDOWN_BUSY is 2', lambda m: m.setword(pod.DATA['DROPDOWN_BUSY'][0], 2)), ('POWER_USBSTATE is 2', lambda m: m.setword(pod.DATA['POWER_USBSTATE'][0], 2)),
                        ('AirPlay is 2', lambda m: setattr(m, 'airplay', 2))):
        m = PT([H]); m.swipe(b'9\n'); setup(m); calls = m.tap('pod_tile_settings'); ret, c2 = m.modal()
        expect(calls == [] and pages(c2) == [('navigator_to', 'dialog/dropdown_dialog')], f'{what}: the tap does nothing, the dialog stays')
    m = PT([H]); m.swipe(b'9\n'); m.quit_ret = 1; calls = m.tap('pod_tile_settings'); ret, c2 = m.modal()
    expect(calls == [('dialog_quit', m.dlg, QUIT)] and pages(c2) == [('navigator_to', 'dialog/dropdown_dialog')], 'a dialog that cannot be quit: no action is left pending')
    m = PT([H]); m.swipe(b'9\n'); m.tap('pod_tile_settings'); m.dialog_ret = 0; ret, calls = m.modal()
    expect(ret == 0 and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'a dialog that ended any other way than a tile (0xd): nothing opens, and the pending tap is dropped')
    m.dialog_ret = QUIT; ret, calls = m.modal()
    expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'dropped for good')
    m = PT([H]); ret, calls = m.modal()
    expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'a stock tile (no pending action): the stock result, nothing else')

    # -- Power Off: what the power key's long press does (on_wm_keylong_fun 0x4cdd9c), after the dialog is gone; shutdown itself is stock's poweroff_page
    STANDBY, KEYBLK = pod.DATA['STANDBY_MODE'][0], pod.DATA['POWERKEY_BLOCK'][0]
    opened = lambda c: [x for x in c if x[0] in ('awake_screen', 'getFormatString', 'confirm', 'navigator_to', 'system', 'reboot')]

    def power(answer=None, setup=None, nav_fail=False):
        m = PT([H]); m.swipe(b'b\n'); m.confirm_yes = answer == 'yes'
        if answer == 'back': m.confirm_answer = 4
        m.nav_fail = nav_fail
        if setup: setup(m)
        m.tap('pod_tile_power'); ret, calls = m.modal()
        return m, ret, opened(calls)
    DLG = ('navigator_to', 'dialog/dropdown_dialog')
    m, ret, c = power('yes')
    expect(ret == QUIT and c == [DLG, ('awake_screen', 0), ('getFormatString', 'msg_poweroff', 0x200), ('confirm', 'Confirm Shutdown?', 1), ('navigator_to', 'poweroff_page')] and m.word(STANDBY) == 1 and m.names_() == [H, 'poweroff_page'],
           f'Power Off, Yes: the screen is lit, the confirm asks the text of msg_poweroff (kind 1, as the key), then poweroff_page opens; standby_mode stays 1 for it to take over ({c}, {m.word(STANDBY)})')
    expect(not any(x[0] in ('system', 'reboot', 'device_reboot') for x in m.calls), 'nothing powers the player off from our code (poweroff_page does it, after the resume record is saved)')
    for how in ('no', 'back'):
        m, ret, c = power(how)
        expect(c == [DLG, ('awake_screen', 0), ('getFormatString', 'msg_poweroff', 0x200), ('confirm', 'Confirm Shutdown?', 1)] and m.word(STANDBY) == 0 and m.names_() == [H],
               f'Power Off, {how}: nothing is opened and standby_mode is back to 0 ({c}, {m.word(STANDBY)})')
    m, ret, c = power('yes', nav_fail=True)
    expect(c[-1] == ('navigator_to', 'poweroff_page') and m.word(STANDBY) == 0 and m.names_() == [H], 'a poweroff_page that will not open: standby_mode is released (the player is not left ignoring the key)')
    for what, setup in (('standby_mode 1 (a confirm is up)', lambda m: m.setword(STANDBY, 1)), ('standby_mode 2 (poweroff_page ran)', lambda m: m.setword(STANDBY, 2)), ('the key block word 2', lambda m: m.setword(KEYBLK, 2))):
        m, ret, c = power('yes', setup)
        expect(c == [DLG] and m.names_() == [H], f'Power Off with {what}: ignored, as the key is (no light, no dialog, no page)')
    m, ret, c = power('yes', lambda m: m.setword(KEYBLK, 1))
    expect(c[-1] == ('navigator_to', 'poweroff_page'), 'the key block word is only checked for 2')
    for what, setup in (('DROPDOWN_BUSY is 2', lambda m: m.setword(pod.DATA['DROPDOWN_BUSY'][0], 2)), ('POWER_USBSTATE is 2', lambda m: m.setword(pod.DATA['POWER_USBSTATE'][0], 2)), ('AirPlay is 2', lambda m: setattr(m, 'airplay', 2))):
        m = PT([H]); m.swipe(b'b\n'); setup(m); calls = m.tap('pod_tile_power'); ret, c2 = m.modal()
        expect(calls == [] and opened(c2) == [DLG], f'Power Off, {what}: the tap does nothing, the dialog stays')
    m, ret, c = power('yes'); ret, c2 = m.modal(); m.setword(STANDBY, 0)
    expect(opened(c2) == [DLG], 'the action runs once: the next modal call (a stock tile) does not ask again')
    m = PT([H]); m.swipe(b'b\n'); m.confirm_yes = True; m.tap('pod_tile_power'); m.dialog_ret = 0; ret, c = m.modal(); c = opened(c)
    expect(c == [DLG] and m.word(STANDBY) == 0, 'a dialog that ended any other way than a tile (0xd): no confirm, and the pending tap is dropped')

    # -- AirPlay and DLNA (ids c and d): switches, not actions. The tap calls stock's own switch and the picture follows the byte; the dialog stays open
    SW = (('pod_tile_airplay', 'pod_cap_airplay', 'drop_airplay', 'drop_airplayopen', 'AirPlay', 12, 'AIRPLAY_FLAG', 'airplay_switch'), ('pod_tile_dlna', 'pod_cap_dlna', 'drop_dlna', 'drop_dlnaopen', 'DLNA', 13, 'DLNA_FLAG', 'dlna_switch'))
    expect(pod.FUNCTIONS['airplay_switch'][2] == 0x5076a8 and pod.FUNCTIONS['dlna_switch'][2] == 0x507674 and pod.DATA['AIRPLAY_FLAG'][0] == 0xa05abd and pod.DATA['DLNA_FLAG'][0] == 0xa05abe
           and pod_pages.PULLDOWN_TILES[12:14] == ('AirPlay', 'DLNA') and pod_pages.PULLDOWN_CHARS[12:14] == 'cd', 'the switches and setting bytes are stock\'s (0x5076a8 / 0xa05abd, 0x507674 / 0xa05abe); ids c and d are AirPlay and DLNA')
    for img, cap, off, on, label, tid, flag, fn in SW:
        wi, wc = tree.find(img), tree.find(cap)
        expect(wi in view.children and wc in view.children and (wi.w, wi.h) == (56, 56) and wi.get('image') == off and wi.get('clickable') == 'true' and (wi.get('visible'), wi.get('sensitive')) == ('false', 'false')
               and (wc.w, wc.h) == (71, 36) and (wc.x - wi.x, wc.y - wi.y) == (-7, 61) and wc.get('text') == label and wc.get('tr_text') is None and (wc.get('visible'), wc.get('sensitive')) == ('false', 'false'),
               f'{img}: a hidden, insensitive 56 x 56 clickable image of {off} and a caption {label!r} (a brand: the same text in every language) in view_switchs')
        expect(asset_image(off).size == (56, 56) and asset_image(on).size == (56, 56) and on in palette.ACCENT_DISC and off not in palette.ACCENT_DISC,
               f'{off}.png and {on}.png are 56 x 56 disc images; the lit one takes the accent disc like the stock lit tiles')
        a = asset_image(on).convert('RGBA'); b = asset_image(off).convert('RGBA')
        expect(a.getpixel((28, 4))[:3] == (255, 255, 255) and a.getpixel((28, 4))[3] == 255 and b.getpixel((28, 4))[:3] == (0x2C, 0x2C, 0x2E) and b.getpixel((28, 4))[3] == 255 and b.getpixel((0, 0))[3] == 0, f'{on}: a flat white disc, {off} a flat #2C2C2E disc (no ring)')
        addr = pod.DATA[flag][0]
        for byte in (0, 1):
            m = PT([H]); m.u.mem_write(addr, bytes([byte])); m.swipe(P.PULLDOWN_CHARS[tid].encode() + b'\n')
            art = [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[img]]
            expect(art == [on if byte else off] and (m.widgets[img], O['EVT_CLICK']) in m.bound and not m.hidden(img), f'{label}, setting byte {byte}: the tile is built {"lit" if byte else "unlit"} ({art})')
        m = PT([H]); m.net = 1; m.swipe(P.PULLDOWN_CHARS[tid].encode() + b'\n'); m.calls.clear()
        calls = m.tap(img)
        expect([c for c in calls if c[0] in ('dialog_quit', 'navigator_to', 'window_open')] == [] and calls[:1] == [(fn,)] and m.u.mem_read(addr, 1)[0] == 1
               and [c[2] for c in calls if c[0] == 'image_base_set_image'] == [on] and ('widget_invalidate_force', m.widgets[img]) in calls and toasts(m) == [],
               f'{label}: a tap calls stock\'s {fn}, the byte is 1 and the tile is lit again in place; the dialog is not quit, no page is opened, no toast with Wi-Fi up ({calls})')
        m.calls.clear(); calls = m.tap(img)
        expect(calls[:1] == [(fn,)] and m.u.mem_read(addr, 1)[0] == 0 and [c[2] for c in calls if c[0] == 'image_base_set_image'] == [off] and toasts(m) == [], f'{label}: the second tap turns it off and unlit, no toast')
        ret, c2 = m.modal()
        expect(ret == QUIT and pages(c2) == [DLG] and not [c for c in c2 if c[0] in (fn, 'toast')], f'{label}: nothing is pending after a tap (the modal call opens nothing and runs nothing)')
        m = PT([H]); m.net = 0; m.swipe(P.PULLDOWN_CHARS[tid].encode() + b'\n'); m.calls.clear(); calls = m.tap(img)
        expect(m.u.mem_read(addr, 1)[0] == 1 and [c[2] for c in calls if c[0] == 'image_base_set_image'] == [on] and toasts(m) == ['Connect to Wi-Fi first'],
               f'{label}: turned on with no Wi-Fi the preference is kept (lit) and the toast says to connect first ({toasts(m)})')
        m.calls.clear(); m.tap(img)
        expect(m.u.mem_read(addr, 1)[0] == 0 and toasts(m) == [], f'{label}: turned off with no Wi-Fi: no toast')
        for what, setup in (('DROPDOWN_BUSY is 2', lambda m: m.setword(pod.DATA['DROPDOWN_BUSY'][0], 2)), ('POWER_USBSTATE is 2', lambda m: m.setword(pod.DATA['POWER_USBSTATE'][0], 2)), ('an AirPlay session is playing', lambda m: setattr(m, 'airplay', 2))):
            m = PT([H]); m.swipe(P.PULLDOWN_CHARS[tid].encode() + b'\n'); setup(m); m.calls.clear(); calls = m.tap(img)
            expect(calls == [] and m.u.mem_read(addr, 1)[0] == 0, f'{label}, {what}: the tap does nothing (the guard of stock\'s tiles), the setting is not changed')
    m = PT([H]); m.swipe(b'cd\n'); both = m.tap('pod_tile_airplay') + m.tap('pod_tile_dlna')
    expect([c[0] for c in both if c[0] in ('airplay_switch', 'dlna_switch')] == ['airplay_switch', 'dlna_switch'] and m.u.mem_read(pod.DATA['AIRPLAY_FLAG'][0], 1)[0] == 1 == m.u.mem_read(pod.DATA['DLNA_FLAG'][0], 1)[0],
           f'both switches shown together each flip their own byte ({both})')
    expect(not any(c[0] in ('system', 'airplay_start', 'dmr_serverstart', 'popen') for c in both), 'our code starts and stops no service: the stock network-status timer does, to match the byte')
    # the stock timer that follows the byte (on_wm_timer_networkstatus 0x4cfd94) is as the tile relies on it (pinned)
    d = built_demo_bytes(); image = bytearray(d)
    expect(all(struct.unpack_from('<I', d, pod.fileoff(image, a))[0] == w for a, w in ((0x5076b4, 0x8f82afc0), (0x5076d0, 0x38840001), (0x5076d8, 0xa0440000), (0x507680, 0x8f82afbc), (0x50769c, 0x38840001), (0x5076a4, 0xa0440000), (0x4cfde4, 0x8f99b470), (0x4cfde8, 0x0320f809), (0x4cfe18, 0x8f99b474), (0x4cfe1c, 0x0320f809)))
           and all(a in [x for x, _, _ in pod.PULLDOWN_PINS] for a in (0x5076b4, 0x5076d0, 0x5076d8, 0x507680, 0x50769c, 0x5076a4, 0x4cfde4, 0x4cfde8, 0x4cfe18, 0x4cfe1c)),
           'airplay_switch and dlna_switch flip one byte each; the network-status timer calls airplay_start and dmr_serverstart (pinned)')

    # -- the build: the call that opens the dialog is the hook's, the words around it are stock's
    d = built_demo_bytes(); image = bytearray(d); stock = stock_demo_bytes()
    word = lambda a: struct.unpack_from('<I', d, pod.fileoff(image, a))[0]
    sw = lambda a: struct.unpack_from('<I', stock, pod.fileoff(stock, a))[0]
    site = pod.PULLDOWN_DIALOG_SITE
    expect(site == 0x4cd864 and sw(site) == 0x04111146 and word(site) == 0x0c000000 | (PSYMS['pd_open_dialog'] >> 2) and word(site + 4) == 0x24849a4c == sw(site + 4),
           'on_wm_tsmove_fun\'s modal navigator_to("dialog/dropdown_dialog") is jal pd_open_dialog in the build (stock: bal navigator_to), its delay slot (a0 = the name) is stock\'s')
    expect(word(0x4cd86c) == 0x2403000d and word(0x4cd870) == 0x14430014 and word(0x475530) == 0x2405000d and word(0x475534) == 0x0320f809,
           'stock\'s code after it only goes on for the result 0xd, which the tile handlers quit the dialog with (dialog_quit(a0, 0xd))')
    expect(MANIFEST['hook_pulldown_dialog'] == {'site': hex(site), 'target': PSYMS['pd_open_dialog']}, 'the manifest records the call site')
    expect(pod.FUNCTIONS['awake_screen'][2] == 0x4e721c and pod.FUNCTIONS['getFormatString'][2] == 0x4ccc18 and pod.DATA['STANDBY_MODE'][0] == 0xa059e0 and pod.DATA['POWERKEY_BLOCK'][0] == 0xa059dc
           and [(a, w) for a, w, _ in pod.PULLDOWN_PINS if 0x4cdd9c < a < 0x4cdea8] == [(0x4cddc4, 0x8f91b33c), (0x4cddcc, 0x1043002d), (0x4cddd4, 0x8f84b068), (0x4cdddc, 0x10830029), (0x4cde0c, 0xae320000), (0x4cde10, 0x04116502), (0x4cde3c, 0xafb20018), (0x4cde30, 0x24060200),
                                                                                              (0x4cde48, 0x0411fb73), (0x4cde4c, 0x24849ae0), (0x4cde60, 0x04110fb9), (0x4cde64, 0x24844570), (0x4cde6c, 0x1443000c), (0x4cde7c, 0x04110fc0), (0x4cde80, 0x2484412c), (0x4cdea4, 0xae200000)]
           and d[pod.fileoff(image, 0x749ae0):][:13] == b'msg_poweroff\0' and d[pod.fileoff(image, 0x74412c):][:14] == b'poweroff_page\0' and d[pod.fileoff(image, 0x744570):][:26] == b'dialog/confirminfo_dialog\0',
           'the power key\'s long press (on_wm_keylong_fun) is as the Power Off tile copies it: its guards, the light, the confirm\'s context, the strings and Yes -> poweroff_page (pinned)')
    expect(pod.FUNCTIONS['dialog_quit'][2] == 0x64f378 and pod.FUNCTIONS['airplayGetFlag'][2] == 0x5cfc4c and pod.DATA['DROPDOWN_BUSY'][0] == 0xa05a00
           and all(word(a) == old for a, old, _ in pod.PULLDOWN_PINS), 'the stock functions and word the tap uses are the ones the tile handlers use (pinned)')


def stockopen_tests(ctx):
    """m1_open_stock (patch/common.c), which the Settings ACT_STOCK rows, the Wi-Fi row of the All System Settings hub (wifi_hub_open) and the Sleep Timer link use: a stock page
    that has no single_instance property is restacked when its window is still in the stack (the top-right Now Playing button leaves it there under the player), else opened by
    navigator_to. The model: navigator_to always adds a window, the Now Playing button restacks the player, a restack delivers EVT_WINDOW_TO_FG."""
    expect, P = ctx.expect, pod_pages
    H, PL = 'home_page', 'playing_page'

    def to_player(m):
        """The top-right Now Playing button: the player is restacked (EVT_WINDOW_TO_BG to the page it leaves, EVT_WINDOW_TO_FG to the player), or opened."""
        old = m.stack[-1][0] if m.stack else None
        ent = next((e for e in m.stack if e[0] == PL), None)
        if ent: m.stack.remove(ent); m.stack.append(ent); m.sync(); m.event(old, 'bg'); m.event(PL, 'fg')
        else: m.push(PL); m.event(old, 'bg'); m.event(PL, 'init')

    def open_(m, path, window):
        return m.call(PSYMS['m1_open_stock'], a0=m.cstr(path), a1=m.cstr(window) if window else 0, count=3000000)

    kinds = lambda m: [c for c in m.calls if c[0] in ('navigator_to', 'switch_to', 'to_fg')]
    names = [(path, window) for path, _, window in P.STOCK_PAGES]
    fresh = {'systemset/bluetooth_page', 'systemset/wifi_page'}
    expect(len(names) == 4 and {p for p, w in names if w is None} == fresh and {w for p, w in names if w} == {'usbset_page', 'synclink_page'},
           'the stock pages a Settings row opens: Bluetooth (its background handler stops discovery and only init restarts it), Wi-Fi (init scans on every open, the foreground handler only rebuilds the list) are opened afresh each time; the two pages of the USB Mode and SyncLink rows (no window event bound) are restacked')
    for path, window in names + [('systemset/display_page', 'display_page')]:   # (a page that names its window, the last component of its path: stock\'s Display list, which no row of ours opens now, as the model of the restack)
        if window is None: continue
        m = SF([H, PL])
        for cycle in range(5):
            m.calls = []; r = open_(m, path, window)
            if cycle == 0: R0 = set(m.run)
            if cycle == 0: ok = kinds(m) == [('navigator_to', path)]
            else: ok = [c[0] for c in kinds(m)] == ['switch_to', 'to_fg'] and kinds(m)[1] == ('to_fg', window) and kinds(m)[0][2:] == (window, 0)
            expect(r == 0 and ok and m.names_().count(window) == 1 and m.names_()[-1] == window,
                   f'{window} cycle {cycle}: {"opened by navigator_to" if cycle == 0 else "restacked, nothing opened, its foreground event delivered"}; one window, in front ({kinds(m)}, {m.names_()})')
            expect(m.run == R0 and m.life.count((window, 'init')) == 1 and m.life.count((window, 'fg')) == cycle,
                   f'{window} cycle {cycle}: what init started is running (the restack runs no init, a new open does): {sorted(m.run)} against {sorted(R0)}, {m.life.count((window, "init"))} init(s)')
            to_player(m)
            expect(m.names_()[-1] == PL and m.names_().count(window) == 1 and m.life.count((window, 'bg')) == cycle + 1, f'{window} cycle {cycle}: the Now Playing button leaves the page under the player, its background event delivered')
            expect(m.run == R0, f'{window} cycle {cycle}: the background event stops nothing ({sorted(m.run)})')
        m = SF([H, window, 'albuminfo_page', PL, 'allmusic_page']); m.calls = []; r = open_(m, path, window)
        expect(r == 0 and [c[0] for c in kinds(m)] == ['switch_to', 'to_fg'] and m.names_() == [H, 'albuminfo_page', PL, 'allmusic_page', window], f'{window} deep in the stack is brought to the front, the others keep their order ({m.names_()})')
        m = SF([H, window]); m.switch_fail = True; m.calls = []; r = open_(m, path, window)
        expect(r == 0 and [c[0] for c in kinds(m)] == ['switch_to', 'navigator_to'], f'{window}: a restack that stock refuses falls back to navigator_to')
        m = SF([H, window]); m.home_opened = 0; m.calls = []; r = open_(m, path, window)
        expect(r == 0 and [c[0] for c in kinds(m)] == ['navigator_to'] and m.names_().count(window) == 2, f'{window} that is closing is not restacked: navigator_to')
        m = SF([H, window]); m.wm = 0; m.calls = []; r = open_(m, path, window)
        expect(r == 0 and [c[0] for c in kinds(m)] == ['navigator_to'], f'{window}: no window manager, navigator_to')
        m = SF([H]); m.nav_fail = True; m.calls = []; r = open_(m, path, window)
        expect(r == 0x10 and [c[0] for c in kinds(m)] == ['navigator_to'] and m.names_() == [H], f'{window} that will not open: the navigator_to result is returned ({r:#x})')
        m = SF([H, window]); m.nav_fail = True; m.calls = []; r = open_(m, path, window)
        expect(r == 0 and [c[0] for c in kinds(m)] == ['switch_to', 'to_fg'], f'{window} in the stack: opened though navigator_to would refuse')

    # -- Bluetooth: its background handler stops discovery and only init restarts it, so the page is opened afresh, init (btStartSearch) running each time
    bt = next(p for p, w, win in P.STOCK_PAGES if p.endswith('bluetooth_page')); bwin = dict(names)[bt]
    for enabled in (True, False):
        m = SF([H, PL]); m.bt_on = enabled
        for cycle in range(3):
            m.calls = []; r = open_(m, bt, bwin)
            expect(r == 0 and kinds(m) == [('navigator_to', bt)] and m.names_().count('bluetooth_page') == cycle + 1 and m.names_()[-1] == 'bluetooth_page'
                   and m.life.count(('bluetooth_page', 'init')) == cycle + 1 and ('bt_search' in m.run) == enabled and 'bt_timer' in m.run,
                   f'Bluetooth ({"on" if enabled else "off"}) reopened after the Now Playing button, cycle {cycle}: a fresh window, init ran again, discovery is {"running" if enabled else "not started"} ({kinds(m)}, {sorted(m.run)})')
            to_player(m)
            expect('bt_search' not in m.run and m.names_()[-1] == PL, f'Bluetooth cycle {cycle}: the background handler stopped discovery')
    m = SF([H, 'bluetooth_page', PL]); m.bt_on = True; m.event('bluetooth_page', 'init'); m.event('bluetooth_page', 'bg'); m.calls = []; r = open_(m, bt, bwin)
    expect(r == 0 and kinds(m) == [('navigator_to', bt)] and 'bt_search' in m.run, 'a Bluetooth window deeper in the stack is not restacked: a new one is opened and discovery runs')

    # -- every page: what init does per open (STOCK_LIFE: wifi_scan with Wi-Fi on, btStartSearch with Bluetooth on) has happened again after open, Now Playing button, reopen,
    #    whether through a fresh init or through the foreground handler
    per_open = {'wifi_page': 'wifi_scan', 'bluetooth_page': 'bt_search', 'usbset_page': None, 'synclink_page': None}
    for path, _, window in P.STOCK_PAGES:
        page = path.split('/')[-1]
        m = SF([H, PL]); m.bt_on = True
        for cycle in range(3):
            open_(m, path, window); to_player(m)
        assert page in per_open
        eff = per_open[page]
        expect(eff is None or m.did.count(eff) == 3, f'{page}: {eff} ran once for each of the three opens, one open, Now Playing button, reopen apart ({m.did})')
    wp = next(p for p, w, win in P.STOCK_PAGES if p.endswith('wifi_page'))
    m = SF([H, PL]); m.wifi_on = False; open_(m, wp, None); to_player(m); open_(m, wp, None)
    expect('wifi_scan' not in m.did and m.names_().count('wifi_page') == 2, 'Wi-Fi off: no scan on either open')

    # -- the stock Wi-Fi page from the Settings row (our page refused) and from the hub row (kill switch): a fresh window and a scan on every reopen
    def settings_row(m): return open_(m, wp, None)   # the ACT_STOCK row's call (patch/m1plus.c) with the window of POD_STOCK
    def hub_row(m): return m.call(PSYMS['wifi_hub_open'], a0=m.cstr(wp), count=30000000)
    for name, opener, kill in (('Settings row', settings_row, False), ('hub row', hub_row, True)):
        m = SF([H, PL])
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        for cycle in range(4):
            m.calls = []; r = opener(m)
            expect(r == 0 and kinds(m) == [('navigator_to', wp)] and m.names_().count('wifi_page') == cycle + 1 and m.names_()[-1] == 'wifi_page'
                   and m.life.count(('wifi_page', 'init')) == cycle + 1 and m.did.count('wifi_scan') == cycle + 1 and 'wifi_timer' in m.run,
                   f'Wi-Fi {name}, Wi-Fi on, cycle {cycle}: a fresh window, init ran and scanned again ({kinds(m)}, {m.did})')
            to_player(m)
        m = SF([H, 'wifi_page', PL]); m.wifi_on = True
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        m.event('wifi_page', 'init'); m.event('wifi_page', 'bg'); m.calls = []; r = opener(m)
        expect(r == 0 and kinds(m) == [('navigator_to', wp)] and m.did.count('wifi_scan') == 2, f'Wi-Fi {name}: a stock window deeper in the stack is not restacked, a new one scans')
    m = SF([H]); m.present.add('/mnt/mmc/m1plus-off'); m.nav_fail = True
    r = m.call(PSYMS['wifi_hub_open'], a0=m.cstr('systemset/wifi_page'), count=30000000)
    expect(r == 0x10, 'hub Wi-Fi row: a page that will not open returns the navigator_to result, as before')


# ---------------------------------------------------------------------------------------------------------------------------------
# The swipe's gates (docs/modules/pulldown.md "Swipe gates and the window stack"): stock's on_wm_tsmove_fun opens the pull-down only while lockscreen_pageflag is not 1 and dropdown_menu_state is 0;
# a window that goes away without its EVT_WINDOW_CLOSE leaves the word set. The real stock on_wm_tsdown_fun / on_wm_tsmove_fun run under the emulator, once from the stock bytes and once from the built image.

TSDOWN, TSMOVE = pod.TSDOWN, 0x4cd788
LOCKW, STATEW, PRESSW = pod.DATA['LOCK_PAGEFLAG'][0], pod.DATA['DROPDOWN_STATE'][0], 0xa05a30
USBW, EXTW, PENDB, CHECK_USB = 0xa059f4, 0xa059f8, 0xa041b1, 0x4ce1e8   # usblink_status, usbdet_value, the USB page's pending byte, check_usb_status (TSDOWN_PINS)
SYSTEM_STUB, SETPCLINK, GETPCLINK = 0x7436e0, 0x5e5fe4, 0x5e5f2c   # stock's lazy stub for system (its GOT slot 0xa03198 holds it), toolsSetpclinkStatus, toolsGetpclinkStatus: the poll's calls, trapped
SCAN = 'scanmusic_dialog'   # Auto Update's modal scan dialog (opened inside the response timer)
KILL_SD_ = '/mnt/mmc/m1plus-off'


class TG(SF):
    """The window stack (SF) with stock's two touch handlers run for real; stock=True restores stock's bytes over both functions (the build's hook and its two page-opening call sites)."""

    def __init__(self, stack, lock=0, state=0, stock=False):
        super().__init__(stack)
        if stock:
            s = stock_demo_bytes(); self.u.mem_write(TSDOWN, s[pod.fileoff(s, TSDOWN):][:0x4cd8dc - TSDOWN])
            self.u.mem_write(pod.USBPOLL_SITE, s[pod.fileoff(s, pod.USBPOLL_SITE):][:4])   # the idle pass's check_usb_status call
            self.u.mem_write(pod.USBTAKE_SITE, s[pod.fileoff(s, pod.USBTAKE_SITE):][:8])   # the response timer's read of the USB page request
        for a in (0xa059e0, 0xa06d00, 0xa059dc, 0xa059f4, 0xa05abc, 0xa045e5, 0x97cae0, 0xa05a34): self.setword(a, 0)   # tsdown's / tsmove's other gates: open
        self.handlers[0x5cfc4c] = 'airplayGetFlag'; self.handlers.pop(CHECK_USB, None)   # (check_usb_status runs for real)
        self.setword(LOCKW, lock); self.setword(STATEW, state); self.setword(PRESSW, 0x90); self.pclink = 1   # (a stale press point: only this touch's own store lets the swipe through)
        self.writes = []
        self.write_hooks = [self.u.hook_add(UC_HOOK_MEM_WRITE, lambda u, t, a, s, v, d: self.writes.append((a, v & 0xffffffff)), begin=w, end=w + 3) for w in (LOCKW, STATEW)]

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'airplayGetFlag':
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        name = self.handlers.get(address)
        if name == 'toolsGetpclinkStatus':   # the host's answer (pc_check)
            self.calls.append((name,)); u.reg_write(UC_MIPS_REG_V0, self.pclink); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'toolsSetpclinkStatus':   # pc_check written: the kernel keeps 1 after an enumeration until firmware writes it
            self.pclink = u.reg_read(UC_MIPS_REG_A0)
        if name in ('awake_screen', 'system', 'toolsSetpclinkStatus'):   # check_usb_status's unplug calls (the idle poll, run for real)
            a0 = u.reg_read(UC_MIPS_REG_A0); self.calls.append((name, self.read_cstr(a0) if name == 'system' else a0))
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        super()._hook(u, address, size, _)

    def pev(self, y):
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30)); self.setword(e + 0x1c, y); return e

    def down(self, y=20):
        """A touch down on the status bar: on_wm_tsdown_fun. Returns the calls and the writes it made to the two words."""
        self.writes = []
        self.call(TSDOWN, a0=0, a1=self.pev(y), count=2000000)
        return list(self.calls), list(self.writes)

    def move(self, y=60):
        """The move: on_wm_tsmove_fun. True when it called navigator_to("dialog/dropdown_dialog")."""
        self.call(TSMOVE, a0=0, a1=self.pev(y), count=2000000)
        return ('navigator_to', 'dialog/dropdown_dialog') in self.calls

    def _usb_mocks(self):
        self.handlers[SYSTEM_STUB], self.handlers[SETPCLINK], self.handlers[GETPCLINK] = 'system', 'toolsSetpclinkStatus', 'toolsGetpclinkStatus'; self.u.mem_write(0xa05aa6, b'\0')   # (0xa05aa6 0: the poll runs)
        self.calls, self._icount, self.limit = [], 0, 4000000

    def poll(self):
        """The idle pass's USB step, from the call site's own words (0x4cef04 .. 0x4cef10): stock's check_usb_status, or the build's pd_usb_poll then it. Returns the calls."""
        self._usb_mocks()
        self.u.reg_write(UC_MIPS_REG_SP, STACK); self.u.reg_write(UC_MIPS_REG_GP, pod.GP)
        self.u.emu_start(pod.USBPOLL_SITE - 4, pod.USBPOLL_SITE + 8)
        assert self.u.reg_read(UC_MIPS_REG_PC) == pod.USBPOLL_SITE + 8, 'the poll did not return to its call site'
        return list(self.calls)

    def take(self):
        """The response timer's USB page step, from its read of the request (0x4cf254) to the next check (0x4cf2cc), both paths: stock's read, or the build's stub and pd_usb_take. Returns the calls."""
        self._usb_mocks()
        sp = STACK - 0x4c0   # (the timer's own frame: its saved gp at 0x18)
        self.u.reg_write(UC_MIPS_REG_SP, sp); self.setword(sp + 0x18, pod.GP); self.u.reg_write(UC_MIPS_REG_GP, pod.GP); self.u.reg_write(UC_MIPS_REG_V0, 0xa00000)
        reached = []   # (a code hook at the next check: unicorn's PC register can still read the block's start when an end address stops it)
        h = self.u.hook_add(UC_HOOK_CODE, lambda u, a, sz, d: (reached.append(u.reg_read(UC_MIPS_REG_S0)), u.emu_stop()), begin=pod.USBTAKE_SKIP, end=pod.USBTAKE_SKIP)
        try: self.u.emu_start(pod.USBTAKE_SITE, 0, count=1000000)
        finally: self.u.hook_del(h)
        assert reached == [0xa00000], f'the timer did not reach its next check with s0 the page: {reached}, {self.calls}'
        return list(self.calls)

    def swipe(self):
        c, w = self.down(); self.after_down = (self.word(LOCKW), self.word(STATEW), self.word(PRESSW))   # (the move itself stores state 1 when it opens)
        return self.move(), c, w


def gate_tests(ctx):
    expect = ctx.expect
    H, LOCK, USB, VOL, DLG = 'home_page', 'screensaver_page', 'usbmode_page', 'volume_dialog', 'dropdown_dialog'

    def run(stack, lock=0, state=0, stock=False):
        m = TG(stack, lock, state, stock); opened, calls, writes = m.swipe()
        return (opened,) + m.after_down + (calls, writes)

    # -- the reproducer: stale words (stock refuses for ever, the build clears them and opens, with this touch's press point)
    for tag, stack, lock, state in (('a lock flag with no lock page', [H], 1, 0),
                                    ('a lock flag with only other pages in the stack', [H, USB], 1, 0),
                                    ('dropdown_menu_state 1 with no dialog', [H], 0, 1), ('dropdown_menu_state 2 with no dialog', [H], 0, 2), ('dropdown_menu_state 3 with no dialog', [H], 0, 3),
                                    ('dropdown_menu_state 3 with no dialog under a page', [H, USB], 0, 3),
                                    ('both words stale', [H, USB], 1, 2)):
        o, lk, st, pr, _, _ = run(stack, lock, state, stock=True)
        expect(not o and (lk, st) == (lock, state), f'STOCK, {tag}: no pull-down, the words stay ({o}, {lk}, {st})')
        o, lk, st, pr, _, w = run(stack, lock, state)
        expect(o and (lk, st) == (0, 0) and pr == 20, f'BUILT, {tag}: the words are cleared and the pull-down opens with this touch\'s press point ({o}, {lk}, {st}, {pr})')
        expect(all(v == 0 for _, v in w) and {a for a, _ in w} <= {LOCKW, STATEW}, f'BUILT, {tag}: the hook only stores 0 ({w})')
        m = TG(stack, lock, state); c, _ = m.down()
        expect([n for n, _ in m.stack] == stack and not [x for x in c if x[0] in ('window_close', 'navigator_to', 'switch_to', 'widget_destroy')], f'BUILT, {tag}: the hook opens, closes and restacks nothing')

    # -- the words that are true stay (the stack says so): stock and build agree
    for tag, stack, lock, state in (('the lock page on top', [H, LOCK], 1, 0), ('the lock page with only a dialog above it', [H, LOCK, VOL], 1, 0),
                                    ('the pull-down on top, state 1', [H, DLG], 0, 1), ('the pull-down on top, state 3', [H, DLG], 0, 3), ('the pull-down on top, state 2', [H, USB, DLG], 0, 2),
                                    ('the pull-down above a dialog', [H, USB, DLG, VOL], 0, 1),
                                    ('a lock page under another page', [H, LOCK, USB], 1, 0), ('a dropdown_dialog under a page', [H, DLG, USB], 0, 1),
                                    ('a dropdown_dialog under a page, state 3', [H, DLG, USB], 0, 3), ('both windows under a page', [H, LOCK, DLG, USB], 1, 2),
                                    ('a lock page under a page, the dialog gone', [H, LOCK, USB], 1, 0)):
        for stock in (True, False):
            o, lk, st, _, _, w = run(stack, lock, state, stock)
            expect(not o and (lk, st) == (lock, state) and not w, f'{"STOCK" if stock else "BUILT"}, {tag}: blocked, the words and the stores unchanged ({o}, {lk}, {st}, {w})')

    # -- a window under another page keeps its word, so its gate still holds when the page above closes (its init does not run again): no pull-down over the lock screen, no second pull-down
    for tag, stack, lock, state in (('the lock page', [H, LOCK, USB], 1, 0), ('the pull-down, state 3', [H, DLG, USB], 0, 3), ('the pull-down, state 1', [H, DLG, USB], 0, 1)):
        m = TG(stack, lock, state)
        covered = m.swipe()[0]
        m.stack.pop(); m.sync(); m.calls.clear()   # the page above closes: the window is in front again
        o = m.swipe()[0]
        expect(not covered and not o and (m.word(LOCKW), m.word(STATEW)) == (lock, state), f'BUILT, {tag} covered by a page and then uncovered: blocked both times, the word kept ({covered}, {o}, {m.word(LOCKW)}, {m.word(STATEW)})')
    for tag, stack, lock, state, part in (('the lock page gone under a page, the dialog still there', [H, DLG, USB], 1, 3, (0, 3)), ('the dialog gone, the lock page still there', [H, LOCK, USB], 1, 2, (1, 0))):
        o, lk, st, _, _, w = run(stack, lock, state)
        expect(not o and (lk, st) == part, f'BUILT, {tag}: only the word with no window is cleared ({o}, {lk}, {st})')

    # -- both words 0: the same swipe as stock, and the hook does nothing else
    for stack in ([H], [H, USB], [H, LOCK]):
        os_, *_ = run(stack, stock=True)
        o, lk, st, pr, calls, w = run(stack)
        expect(os_ and o and (lk, st, pr) == (0, 0, 20) and not w, f'both words 0 {stack}: opens as stock, the hook stores nothing ({o}, {w})')
        names = [c[0] for c in calls]
        expect(set(names) <= {'reset_poweroptions_timer'}, f'both words 0 {stack}: no window manager, kill switch or other call from the hook ({names})')
    m = TG([H]); m.down()
    expect(not [c for c in m.calls if c[0] in ('get_top_main_window', 'access')], 'no lookup on a touch with both words 0')

    # -- the kill switch: stock behaviour, read once, only when a word is nonzero
    for kill in (KILL_SD_, '/mnt/data/m1plus-off'):
        m = TG([H], lock=1); m.present.add(kill)
        o = m.swipe()[0]
        expect(not o and m.word(LOCKW) == 1, f'kill switch {kill}: the stale lock flag is stock\'s ({o})')
        m = TG([H], state=2); m.present.add(kill)
        expect(not m.swipe()[0] and m.word(STATEW) == 2, f'kill switch {kill}: the stale state is stock\'s')
    m = TG([H], lock=1); seen = []
    c, _ = m.down(); seen += [x for x in c if x[0] == 'access']
    expect(seen == [('access', KILL_SD_), ('access', '/mnt/data/m1plus-off')] and m.word(LOCKW) == 0, f'the first touch with a stale word reads the kill switch, both files ({seen})')
    m.setword(LOCKW, 1)
    c, _ = m.down()
    expect(not [x for x in c if x[0] == 'access'] and m.word(LOCKW) == 0, 'and never again (the answer is kept)')
    m = TG([H]); m.down(); m.setword(STATEW, 1)
    c, _ = m.down()
    expect(len([x for x in c if x[0] == 'access']) == 2 and m.word(STATEW) == 0, 'a touch with both words 0 does not read it: the first stale word does')

    # -- the third gate, usblink_status 2 (a computer has the card): left at 2 by a USB page that never opened or closed without usbmode_exit (the report: a reconnect during Auto Update's scan, whose
    # modal dialog runs inside the response timer, so the page's pending byte stays 1 until the scan returns)
    def usb(stack, ext=0, pending=0, stock=False, kill=None):
        m = TG(stack, stock=stock); m.setword(USBW, 2); m.setword(EXTW, ext); m.u.mem_write(PENDB, bytes([pending]))
        if kill: m.present.add(kill)
        return m
    pend = lambda m: m.u.mem_read(PENDB, 1)[0]
    stop = ('system', 'storage_config.sh stop')

    def plug(m, pc):
        """A cable in: stock's state-0 branch (storage_config.sh start, then 1; not run here), and for a PC a new enumeration latching pc_check 1."""
        m.setword(EXTW, 1); m.setword(USBW, m.word(USBW) or 1)
        if pc: m.pclink = 1
    for pending, tag in ((0, 'no page pending'), (1, 'the USB page still pending (the scan held the response timer)')):
        m = usb([H], pending=pending, stock=True); c = m.poll(); o = m.swipe()[0]
        expect(not o and m.word(USBW) == 2 and pend(m) == pending and stop not in c, f'STOCK, state 2 with no cable, {tag}, no USB page: the poll leaves it, no pull-down ({o}, {m.word(USBW)}, {pend(m)})')
        m = usb([H], pending=pending); c = m.poll()
        expect(m.word(USBW) == 0 and pend(m) == 0 and stop in c, f'BUILT, the same: the poll drops the page and runs stock\'s own unplug: storage_config.sh stop, state 0 ({m.word(USBW)}, {pend(m)}, {c})')
        o = m.swipe()[0]
        expect(o and m.after_down[2] == 20, f'BUILT, then the pull-down opens ({o})')
    # over Auto Update's scan dialog: stock's own scan (after a USB page's close, or from Settings) runs with the state 0 or 3, so its swipe is open; the build unplugs a stale 2 there too
    m = TG([H, SCAN], stock=True); o = m.swipe()[0]
    expect(o, f'STOCK, state 0 over the scan dialog: the pull-down opens ({o})')
    m = usb([H, SCAN], pending=1); c = m.poll()
    expect(m.word(USBW) == 0 and pend(m) == 0 and stop in c and m.pclink == 0, f'BUILT, state 2 with no cable over the scan dialog: the page dropped, stock\'s unplug (stop, pc_check 0, state 0) ({m.word(USBW)}, {c})')
    # replugs during the same scan run through stock's own 0 -> 1 -> 2: a PC asks for the page (opened once the scan returns), a charger leaves 1
    plug(m, 1); m.poll()
    expect(m.word(USBW) == 2 and pend(m) == 1, f'BUILT, the PC back during the scan: stock\'s start and host check, state 2 and the page asked for ({m.word(USBW)}, {pend(m)})')
    m.setword(EXTW, 0); c = m.poll()
    expect(m.word(USBW) == 0 and pend(m) == 0 and stop in c and m.pclink == 0, f'BUILT, a second unplug over the scan: unplugged again, pc_check cleared again ({m.word(USBW)}, {c})')
    plug(m, 0); m.poll(); m.stack = [x for x in m.stack if x[0] != SCAN]; m.sync(); m.poll(); c = m.take()   # (a charger: pc_check as firmware left it)
    expect(m.word(USBW) == 1 and pend(m) == 0 and not [x for x in c if x[0] == 'navigator_to'], f'BUILT, a charger after it, the scan closed: state 1, no USB Storage ({m.word(USBW)}, {c})')
    m = usb([H, SCAN], pending=1); m.poll(); plug(m, 1); m.poll(); m.stack = [x for x in m.stack if x[0] != SCAN]; m.sync(); c = m.take()
    expect(('navigator_to', 'usbmode_page') in c, f'BUILT, the PC back during the scan, the scan closed: the response timer opens USB Storage ({c})')
    m = usb([H, SCAN], ext=1, pending=1, stock=True); m.poll(); m.setword(EXTW, 0); m.poll(); m.setword(EXTW, 1); m.stack = [x for x in m.stack if x[0] != SCAN]; m.sync(); m.poll()
    expect(m.word(USBW) == 2 and pend(m) == 1, f'STOCK, the same unplug and replug: the old request is all there is ({m.word(USBW)}, {pend(m)})')
    # a normal unplug of a USB session: usbmode_page's own close (usbmode_exit, then stock's unplug) is left to run, nothing written meanwhile
    for pending in (0, 1):
        m = usb([H, USB], pending=pending); c = m.poll()
        expect(m.word(USBW) == 2 and not [x for x in c if x[0] in ('system', 'toolsSetpclinkStatus')], f'BUILT, state 2 with no cable and the USB page open, pending {pending}: the state and pc_check kept for usbmode_exit ({c})')
    # the timer first after the unplug: the request dropped and the state unplugged at once, so a cable back before the next poll meets stock's 0 -> 1 -> 2
    m = usb([H], pending=1); c = m.take()
    expect(m.word(USBW) == 0 and pend(m) == 0 and stop in c and m.pclink == 0 and not [x for x in c if x[0] == 'navigator_to'], f'BUILT, the timer takes a request with no cable: dropped, stock\'s unplug at once ({m.word(USBW)}, {c})')
    plug(m, 1); m.poll()
    expect(m.word(USBW) == 2 and pend(m) == 1 and ('navigator_to', 'usbmode_page') in m.take(), f'BUILT, then the PC back: the host asked, USB Storage opens ({m.word(USBW)})')
    m = usb([H], pending=1); m.take(); plug(m, 0); m.poll(); c = m.take()   # (a charger)
    expect(m.word(USBW) == 1 and not [x for x in c if x[0] == 'navigator_to'], f'BUILT, or a charger: state 1, no USB Storage ({m.word(USBW)}, {c})')
    # the response timer before the poll: the request is read with the cable already gone
    for stock in (True, False):
        m = usb([H], pending=1, stock=stock); c = m.take()
        expect((('navigator_to', 'usbmode_page') in c) == stock and pend(m) == 0,
               f'{"STOCK" if stock else "BUILT"}, the timer takes the request with no cable: ' + ('USB Storage opens' if stock else 'dropped, nothing opens') + f' ({c})')
    m = usb([H, LOCK], pending=1); c = m.take()
    expect(not [x for x in c if x[0] in ('navigator_to', 'navigator_close', 'window_manager')] and m.names_() == [H, LOCK],
           f'BUILT, the same over the lock page: the top window is not even asked for, so stock does not close the lock page for the page ({c})')
    for stock in (True, False):
        m = usb([H], ext=1, pending=1, stock=stock); c = m.take()
        expect(('navigator_to', 'usbmode_page') in c and pend(m) == 0, f'{"STOCK" if stock else "BUILT"}, the timer takes the request with the cable in: USB Storage opens ({c})')
        m = usb([H], ext=1, stock=stock); c = m.take()
        expect(not [x for x in c if x[0] == 'navigator_to'], f'{"STOCK" if stock else "BUILT"}, nothing pending: nothing opens ({c})')
    m = usb([H], pending=1, kill=KILL_SD_); c = m.take()
    expect(('navigator_to', 'usbmode_page') in c, f'kill switch: the timer is stock\'s ({c})')
    for tag, stack in (('the USB page in the stack', [H, USB]), ('the USB page under the lock page', [H, USB, LOCK])):
        m = usb(stack, pending=1); m.poll(); c = m.take()
        expect(m.word(USBW) == 2 and pend(m) == 0 and not [x for x in c if x[0] in ('navigator_to', 'system')], f'BUILT, state 2 with no cable and {tag}: the timer drops the page request, the state kept for usbmode_exit ({m.word(USBW)}, {pend(m)}, {c})')
    for stock in (True, False):
        m = usb([H], ext=1, stock=stock); c = m.poll()
        expect(m.word(USBW) == 2 and pend(m) == 0 and not [x for x in c if x[0] in ('widget_count_children', 'access')],
               f'{"STOCK" if stock else "BUILT"}, state 2 with the cable in: the poll changes nothing and walks no window stack ({m.word(USBW)}, {c})')
    # the cable still in: a touch asks for the lost page again
    for stock in (True, False):
        m = usb([H], ext=1, stock=stock); o = m.swipe()[0]
        expect(not o and m.word(USBW) == 2 and pend(m) == (0 if stock else 1),
               f'{"STOCK" if stock else "BUILT"}, state 2 with the cable in, no page pending and no USB page: blocked, ' + ('nothing pending' if stock else 'the page pending again (the next response tick opens it)') + f' ({o}, {pend(m)})')
    for tag, stack, pending in (('the page pending (its first 500 ms, or the scan holds the timer)', [H], 1), ('the USB page in the stack (a USB session)', [H, USB], 0),
                                ('the USB page under the lock page', [H, USB, LOCK], 0)):
        for stock in (True, False):
            m = usb(stack, 1, pending, stock); o = m.swipe()[0]
            expect(not o and m.word(USBW) == 2 and pend(m) == pending, f'{"STOCK" if stock else "BUILT"}, state 2, the cable in, {tag}: blocked, all kept ({o}, {m.word(USBW)}, {pend(m)})')
    m = usb([H], 1, 1); c, _ = m.down()
    expect(not [x for x in c if x[0] in ('widget_count_children', 'access')], 'state 2 with the cable in and the page pending: no window stack walk, no kill switch read')
    for kill in (KILL_SD_, '/mnt/data/m1plus-off'):
        m = usb([H], 0, 1, kill=kill); c = m.poll()
        expect(m.word(USBW) == 2 and pend(m) == 1 and stop not in c, f'kill switch {kill}, no cable: the poll is stock\'s ({m.word(USBW)}, {pend(m)})')
        m = usb([H], 1, kill=kill); o = m.swipe()[0]
        expect(not o and pend(m) == 0, f'kill switch {kill}, cable in: the touch is stock\'s ({o}, {pend(m)})')

    # -- the build
    stock, built = stock_demo_bytes(), built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    expect(pod.DATA['POWER_USBSTATE'][0] == USBW and pod.DATA['POWER_EXT'][0] == EXTW and pod.DATA['USB_PAGE_PENDING'][0] == PENDB, 'the USB words the hooks read are the pinned ones')
    expect(word(stock, pod.USBPOLL_SITE) == 0x0411fcb7 and word(built, pod.USBPOLL_SITE) == pod.jal(PSYMS['pd_usb_poll'], pod.USBPOLL_SITE) and pod.FUNCTIONS['check_usb_status'][2] == CHECK_USB
           and MANIFEST['hook_usbpoll'] == {'addr': pod.USBPOLL_SITE, 'target': PSYMS['pd_usb_poll']}, 'the idle pass calls pd_usb_poll where stock calls check_usb_status (hook 38)')
    expect((word(stock, pod.USBTAKE_SITE), word(stock, pod.USBTAKE_SITE + 4)) == (0x904341b1, 0x1060001c) and (word(built, pod.USBTAKE_SITE), word(built, pod.USBTAKE_SITE + 4)) == (pod.j(PSYMS['pod_usb_site']), 0)
           and MANIFEST['hook_usbtake'] == {'addr': pod.USBTAKE_SITE, 'target': PSYMS['pod_usb_site']}, 'the response timer reads the USB page request through pod_usb_site (hook 39)')
    expect(TSDOWN == 0x4cd6e8 and pod.TSDOWN_PROLOGUE == (0x3c1c0053, 0x279c67e8, 0x0399e021) and tuple(word(stock, TSDOWN + 4 * i) for i in range(3)) == pod.TSDOWN_PROLOGUE,
           'stock has the three PIC prologue words the hook pins (on_wm_tsdown_fun)')
    expect((0x53 << 16) + 0x67e8 + TSDOWN == pod.GP, 'the prologue computes $gp = 0xa03ed0 from t9 = the entry')
    expect(tuple(word(built, TSDOWN + 4 * i) for i in range(4)) == (pod.j(PSYMS['m1plus_tsdown']), 0, pod.TSDOWN_PROLOGUE[2], 0x27bdffe0),
           'the build has `j m1plus_tsdown; nop` over the first two prologue words; the trampoline resumes at the addiu sp')
    tramp = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS['stock_tsdown_trampoline'] - pod.BASE)
    expect(tramp == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(TSDOWN + 12), 0), 'the trampoline restores $gp and resumes at the 4th instruction')
    expect(MANIFEST['hook_tsdown'] == {'addr': TSDOWN, 'target': PSYMS['m1plus_tsdown']}, 'the manifest records the hook')
    expect(pod.DATA['LOCK_PAGEFLAG'] == (0xa059fc, 'lockscreen_pageflag') and pod.DATA['DROPDOWN_STATE'] == (0xa05a2c, 'dropdown_menu_state'), 'the two words are stock\'s dynsym names')
    expect(len(pod.TSDOWN_PINS) >= 20 and all(word(stock, a) == old and word(built, a) == old for a, old, _ in pod.TSDOWN_PINS) and set(pod.TSDOWN_PINS) <= set(pod.PULLDOWN_PINS),
           'the words the reasoning relies on (tsdown\'s press point, tsmove\'s two gates, the writers of the two words) are pinned and stock in the build')
    expect(all(not TSDOWN - 12 < h < TSDOWN + 12 for h in (pod.PULLDOWN_INIT, pod.PLAYMORE_INIT, pod.LOCKSCREEN_INIT, pod.BIGCOVER_INIT, pod.HOME_INIT)), 'a hook of its own')


CLOSE_STOCK, SLIDE_CB, ADD_TIMER, REFRESH_ID_W, SLIDE_ID, REFRESH_ID, EVT_CLOSE = 0x4750ec, 0x47535c, 0x668c78, 0x97c750, 21, 22, 0x12e
DIRW = 0xa05a34


class CG(TG):
    """TG with the pull-down dialog's close event and its pending slide timer: stock's real close handler (0x4750ec) and slide callback (0x47535c) run from the stock bytes, the payload's handler as the build binds it.
    The timers are ids (widget_add_timer / widget_remove_timer); a removed timer does not fire; the dialog's property "timer_idex" is stock's uint32 value_t."""

    def __init__(self, y, slide=SLIDE_ID, stock=False):
        super().__init__(['home_page'], 0, 1, stock)
        for h in self.write_hooks: self.u.hook_del(h)   # (a write hook on the state store in stock's branch delay slot, 0x4754c4, breaks the branch under unicorn)
        self.mem_geometry = True
        from disasm import Bin   # (tools/ is on the path: the harness imports pod)
        for slot, nm in Bin(DEMO).got.items():   # stock's GOT slots for the calls the callbacks make (libc and the mocked widget calls)
            hit = [a for a, n in self.handlers.items() if n == nm]
            if hit: self.setword(slot, hit[0])
        for nm, off in (('widget_get_prop', 0x57bc), ('widget_set_prop', 0x57b0), ('value_uint32', 0x57ac), ('widget_remove_timer', 0x57a4), ('cg_add_timer', 0x57b8), ('timer_count', 0x57a8), ('value_set_uint32', 0x57b4)):
            self.handlers[self.word(pod.GP - off)] = nm   # stock's GOT slots (the callbacks reach these by $gp, 0xa03ed0)
        self.removed, self.active, self.nexttimer = [], {REFRESH_ID: 'refresh'}, 23
        self.handlers[ADD_TIMER] = 'cg_add_timer'
        self.dialog = self.alloc(0x120); self.u.mem_write(self.dialog, bytes(0x120)); self.setword(self.dialog + 4, y & 0xffffffff)
        self.timer = self.alloc(0x60); self.u.mem_write(self.timer, bytes(0x60)); self.setword(self.timer + 0x24, self.dialog)
        self.props[(self.dialog, 'timer_idex')] = slide
        if slide != 0xffffffff: self.active[slide] = 'slide'
        self.setword(REFRESH_ID_W, REFRESH_ID); self.setword(STATEW, 1); self.setword(DIRW, 1)
        self.bound_close = [(CLOSE_STOCK, self.dialog)]   # the handlers of EVT_WINDOW_CLOSE in bind order: stock's init binds its own first

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('widget_get_prop', 'widget_set_prop', 'value_uint32', 'timer_count', 'widget_remove_timer', 'cg_add_timer'):
            return super()._hook(u, address, size, _)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        ret = 0
        if name == 'widget_get_prop': self.setword(a2 + 8, self.props.get((a0, self.read_cstr(a1)), 0xffffffff))
        elif name == 'widget_set_prop': self.props[(a0, self.read_cstr(a1))] = self.word(a2 + 8)
        elif name == 'value_uint32': ret = self.word(a0 + 8)
        elif name == 'timer_count': ret = len(self.active)
        elif name == 'widget_remove_timer':
            self.removed.append((a0, a1)); self.active.pop(a1, None)
        else:
            ret = self.nexttimer; self.nexttimer += 1; self.active[ret] = 'refresh'
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def build_init(self, fail=False):
        """The payload's init hook over this dialog (stock's init mocked): the EVT_WINDOW_CLOSE handlers it binds join the dialog's."""
        if fail: self.widget_on_fail = frozenset({EVT_CLOSE})
        ret = self.call(PSYMS['m1plus_pulldown_init'], a0=self.dialog, a1=0, count=3000000)
        self.bound_close += [(a2, a3) for n, a0, a1, a2, a3 in (c for c in self.calls if c[0] == 'widget_on' and len(c) == 5) if a0 == self.dialog and a1 == EVT_CLOSE and a1 not in self.widget_on_fail]
        return ret

    def close(self):
        """EVT_WINDOW_CLOSE: every bound handler, in order (the event struct is not read)."""
        for fn, ctx in self.bound_close: self.call(fn, a0=ctx, a1=0, count=2000000)

    def tick(self):
        """The 10 ms slide timer, when it still exists: stock's callback. True when it ran."""
        if SLIDE_ID not in self.active: return False
        self.call(SLIDE_CB, a0=self.timer, count=2000000)
        return True


def close_tests(ctx):
    expect = ctx.expect
    stock, built = stock_demo_bytes(), built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]

    def run(y, ours, stock_tsdown, slide=SLIDE_ID):
        """close, one late slide tick if the timer is still there, then a touch down at y 20 and a move to y 60 with the dialog gone. (state after the tick, ran, opens, the machine)"""
        m = CG(y, slide, stock_tsdown)
        if ours: m.build_init()
        m.close()
        ran = m.tick() if slide != 0xffffffff else False
        state = m.word(STATEW)
        opened = m.swipe()[0]
        return state, ran, opened, m

    # -- the reproducer: stock's close handler alone (the slide timer outlives the dialog) against the build's handler too
    for y in (-60, -40, 0):
        state, ran, opened, m = run(y, False, True)
        expect(ran and state == 3 and not opened and m.removed == [(m.dialog, REFRESH_ID)], f'STOCK handlers, y {y}: the close removes only the refresh timer, the late tick stores state 3, the swipe is refused ({ran}, {state}, {opened}, {m.removed})')
        state, ran, opened, m = run(y, True, False)
        expect(m.removed == [(m.dialog, REFRESH_ID), (m.dialog, SLIDE_ID)] and m.props[(m.dialog, 'timer_idex')] == 0xffffffff and not ran and state == 0 and opened,
               f'BUILT, y {y}: the slide timer is removed at the close, timer_idex is -1, no tick runs, the state stays 0, the swipe opens ({m.removed}, {ran}, {state}, {opened})')
        state, ran, opened, m = run(y, False, False)
        expect(ran and state == 3 and opened,
               f'hook 30 without our close handler, y {y}: the late tick still fires and the swipe still opens (the two fixes are independent) ({ran}, {state}, {opened})')
    for y in (-340, -120):
        state, ran, opened, m = run(y, False, True)
        expect(ran and state == 0 and opened, f'STOCK handlers, y {y}: a late tick before the last frame leaves state 0 ({ran}, {state}, {opened})')
        state, ran, opened, m = run(y, True, False)
        expect(not ran and state == 0 and opened and m.removed == [(m.dialog, REFRESH_ID), (m.dialog, SLIDE_ID)], f'BUILT, y {y}: the timer is removed, state 0, opens ({ran}, {state}, {opened}, {m.removed})')

    # -- no slide timer pending: ours removes nothing (stock's own refresh removal only); no timer left at all: ours removes nothing either
    state, ran, opened, m = run(-60, True, False, slide=0xffffffff)
    expect(m.removed == [(m.dialog, REFRESH_ID)] and m.props[(m.dialog, 'timer_idex')] == 0xffffffff and state == 0 and opened, f'BUILT, timer_idex -1: only stock\'s refresh timer is removed ({m.removed}, {state}, {opened})')
    m = CG(-60, SLIDE_ID); m.build_init(); m.active.clear(); m.close()
    expect(m.removed == [(m.dialog, REFRESH_ID)], f'BUILT, no timer alive: ours removes no id ({m.removed})')
    expect((m.dialog, SLIDE_ID) not in m.removed and m.props[(m.dialog, 'timer_idex')] == SLIDE_ID, 'BUILT, no timer alive: the property is left alone')

    # -- the bind: one more handler on the dialog's EVT_WINDOW_CLOSE after stock's; a refused bind leaves the rest of the init as stock
    m = CG(-60); m.build_init()
    expect(len(m.bound_close) == 2 and m.bound_close[1][1] == m.dialog and m.bound_close[1][0] != CLOSE_STOCK, f'the build binds one more handler on the close event, context the dialog ({m.bound_close})')
    m = CG(-60); r = m.build_init(fail=True)
    expect(r == 0 and len(m.bound_close) == 1 and ('stock_pulldown_resume', m.dialog, 0) in m.calls, f'a refused bind: stock\'s result and no extra handler ({r}, {m.bound_close})')
    m = CG(-60); m.close()
    expect(m.word(STATEW) == 0, 'stock close handler alone: state 0')

    # -- pins: the words the reasoning relies on are stock in both images
    pins = [p for p in pod.TSDOWN_PINS if 0x475114 <= p[0] <= 0x475fb0 or 0x4754bc <= p[0] <= 0x4754c4]
    expect(len(pins) >= 18 and all(word(stock, a) == old and word(built, a) == old for a, old, _ in pins), 'the close handler\'s bind, its one timer removal, the slide callback\'s state 3 store and stock\'s cancel sequence are pinned and stock in the build')
    expect(word(stock, 0x475f94) == 0x2405012e and word(stock, 0x475fb0) == 0x24c60000 | 0x50ec, 'init binds 0x4750ec to 0x12e')


class PH(PT):
    """Pull-down with Wi-Fi and Bluetooth tile long press: supports opening our Wi-Fi and Bluetooth pages and dispatching pointer / click events on their tiles."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.u.mem_write(pod.DATA['WIFI_FLAG'][0], b'\0')
        self.u.mem_write(pod.DATA['BT_FLAG'][0], b'\0')

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        if name == 'window_open' and self.read_cstr(a0) in ('m1plus_wifi', 'm1plus_bluetooth'):
            asset = self.read_cstr(a0); self.calls.append(('window_open', asset))
            if self.windows.get(asset, 1) == 0:
                ret = 0
            else:
                self.push(asset + '_page'); ret = self.stack[-1][1]
        elif name == 'widget_lookup' and a0 != self.dlg:
            nm = self.read_cstr(a1); self.calls.append(('widget_lookup', nm))
            ret = self.lookups.get((a0, nm)) or self.widgets.get(nm) or self.widget(nm)
        elif name == 'widget_get_prop':
            ret = 1   # no slide timer_idex in PH (close_tests covers the slide timer)
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def send(self, name, ev, x=49, y=65):
        """Dispatch event `ev` (pointer or click) to the payload listener on widget `name`; returns the listener's return code."""
        w = self.widgets[name]
        fn, ctx = self.bound[(w, ev)]
        e = self.alloc(0x28); self.u.mem_write(e, bytes(0x28))
        self.setword(e, ev); self.setword(e + O['PE_X'], x); self.setword(e + O['PE_Y'], y)
        return self.call(fn, a0=ctx, a1=e, count=3000000)

    def fire_hold(self):
        """Fire the armed long-press timer callback (pd_on_hold_fire)."""
        return self.call(PSYMS['pd_on_hold_fire'], a0=0, count=3000000)


def hold_tests(ctx):
    """Long press on the Wi-Fi and Bluetooth pull-down tiles (patch/pulldown.c, docs/modules/pulldown.md): same RM_LONG_MS hold and SC_DRAG_PX move limit as Home Screen pins."""
    expect = ctx.expect
    H, P_ = 'home_page', 'playing_page'
    WIFI, BT = 'm1plus_wifi_page', 'm1plus_bluetooth_page'
    PDOWN_Y = pod.DATA['PRESSDOWN_Y'][0]
    pages = lambda c: [x for x in c if x[0] in ('window_open', 'navigator_to', 'switch_to', 'window_close')]
    EVS = (O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT'], O['EVT_CLICK'])

    # -- bindings: only shown Wi-Fi / BT tiles; failed early bind skips DOWN so no timer can start
    m = PD(fs=None); m.open()
    for t in (0, 1):
        expect(all((m.widgets[IMG[t]], ev) in m.bound for ev in EVS), f'default layout: {IMG[t]} binds hold pointer + click events')
    for fs, want_t in ((b'0\n', {0}), (b'1\n', {1}), (b'2345\n', set()), (b'910\n', {0, 1})):
        m = PD(fs=fs); m.open()
        got_t = {t for t in (0, 1) if (m.widgets[IMG[t]], O['EVT_POINTER_DOWN']) in m.bound}
        expect(got_t == want_t, f'{fs!r}: hold bound only on shown Wi-Fi/BT tiles ({got_t} == {want_t})')
    for fail_ev in (O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT'], O['EVT_CLICK']):
        m = PD(fs=None); m.widget_on_fail = frozenset({fail_ev}); m.open()
        expect(all((m.widgets[IMG[t]], O['EVT_POINTER_DOWN']) not in m.bound for t in (0, 1)),
               f'when bind of {fail_ev:#x} fails, DOWN is not bound (no un-cancellable timer)')

    # -- short tap: DOWN arms RM_LONG_MS timer, UP removes it, CLICK returns RET_OK so stock's toggle runs
    for img in ('img_wifiswitch', 'img_btswitch'):
        m = PH([H]); m.swipe(b'01234567\n'); m.calls.clear()
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65)
        armed = [c for c in m.calls if c[0] == 'timer_add']
        expect(armed == [('timer_add', PSYMS['pd_on_hold_fire'], O['RM_LONG_MS'])], f'{img}: DOWN arms {O["RM_LONG_MS"]} ms hold timer ({armed})')
        m.calls.clear()
        m.send(img, O['EVT_POINTER_UP'], 49, 65)
        expect([c for c in m.calls if c[0] in ('timer_remove', 'dialog_quit')] == [('timer_remove', 0x777)], f'{img}: early UP cancels timer without quitting')
        r = m.send(img, O['EVT_CLICK'], 49, 65)
        expect(r == O['RET_OK'], f'{img}: CLICK after short tap returns RET_OK so stock toggle runs ({r})')

    # -- drag cancellation (SC_DRAG_PX): move < 10 px keeps timer; move >= 10 px on x or y cancels it; ABORT and close cancel it
    for dx, dy, cancel in ((9, 0, False), (0, 9, False), (10, 0, True), (0, 10, True), (-10, 0, True), (0, -10, True)):
        m = PH([H]); m.swipe(b'01234567\n')
        m.send('img_wifiswitch', O['EVT_POINTER_DOWN'], 49, 65); m.calls.clear()
        m.send('img_wifiswitch', O['EVT_POINTER_MOVE'], 49 + dx, 65 + dy)
        removed = [c for c in m.calls if c[0] == 'timer_remove']
        expect((len(removed) == 1) == cancel, f'move ({dx},{dy}): {"cancels" if cancel else "keeps"} hold timer ({removed})')
    m = PH([H]); m.swipe(b'01234567\n')
    m.send('img_btswitch', O['EVT_POINTER_DOWN'], 123, 65); m.calls.clear()
    m.send('img_btswitch', O['EVT_POINTER_ABORT'], 123, 65)
    expect([c for c in m.calls if c[0] == 'timer_remove'] == [('timer_remove', 0x777)], 'ABORT cancels armed hold timer')
    m = PH([H]); m.swipe(b'01234567\n')
    m.send('img_wifiswitch', O['EVT_POINTER_DOWN'], 49, 65); m.calls.clear()
    fn, ctx_c = m.bound[(m.dlg, O['EVT_WINDOW_CLOSE'])]
    m.call(fn, a0=ctx_c, a1=0, count=3000000)
    expect([c for c in m.calls if c[0] == 'timer_remove'] == [('timer_remove', 0x777)], 'dialog EVT_WINDOW_CLOSE cancels armed hold timer')

    # -- long press fires: quits dialog with 0xd, resets PRESSDOWN_Y >= 81, suppresses stock CLICK with RET_STOP, opens our page after modal returns
    for img, asset, page_win, stock_nav, sub_win in (
        ('img_wifiswitch', 'm1plus_wifi', WIFI, 'systemset/wifi_page', 'm1plus_wifiinfo_page'),
        ('img_btswitch', 'm1plus_bluetooth', BT, 'systemset/bluetooth_page', 'm1plus_btdevice_page'),
    ):
        m = PH([H]); m.swipe(b'01234567\n'); m.setword(PDOWN_Y, 65); m.calls.clear()
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65)
        m.calls.clear()
        m.fire_hold()
        expect([c for c in m.calls if c[0] == 'dialog_quit'] == [('dialog_quit', m.dlg, QUIT)] and m.word(PDOWN_Y) >= 81,
               f'{img}: hold quits dialog with 0xd and resets pressdown_y >= 81 ({m.calls}, {m.word(PDOWN_Y)})')
        r_click = m.send(img, O['EVT_CLICK'], 49, 65)
        expect(r_click == O['RET_STOP'], f'{img}: CLICK on release after hold returns RET_STOP so stock toggle does not run ({r_click})')
        ret, calls = m.modal()
        expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', asset)] and m.names_() == [H, page_win],
               f'{img}: modal return opens our {asset} page, not stock ({pages(calls)}, {m.names_()})')
        ret2, calls2 = m.modal()
        expect(ret2 == QUIT and pages(calls2) == [('navigator_to', 'dialog/dropdown_dialog')], f'{img}: pending action runs once')

        # already in front: left alone
        m = PH([H, page_win]); m.swipe(b'01234567\n')
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold()
        ret, calls = m.modal()
        expect(ret == QUIT and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')] and m.names_() == [H, page_win],
               f'{img}: {page_win} already in front is left alone ({pages(calls)})')

        # behind playing_page with a sub-page opened from it: sub-page closed, main page restacked (never opened twice)
        m = PH([H, page_win, sub_win, P_]); m.swipe(b'01234567\n')
        h = {n: w for n, w in m.stack}; m.call(PSYMS['pd_note_opener'], a0=h[sub_win], a1=h[page_win])
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold()
        ret, calls = m.modal()
        expect(pages(calls)[1:] == [('window_close', sub_win), ('switch_to', P_, page_win, 0)] and m.names_() == [H, P_, page_win],
               f'{img}: behind player with {sub_win}, closes sub-page and restacks {page_win} ({pages(calls)}, {m.names_()})')

        # our page fails to open: falls back to stock page
        m = PH([H]); m.swipe(b'01234567\n'); m.windows = {asset: 0}
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold()
        ret, calls = m.modal()
        expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('window_open', asset), ('navigator_to', stock_nav)],
               f'{img}: failed open of {asset} falls back to stock {stock_nav} ({pages(calls)})')

        # kill switch: falls back to stock page without opening ours
        m = PH([H]); m.present.add('/mnt/mmc/m1plus-off'); m.swipe(b'01234567\n')
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold()
        ret, calls = m.modal()
        expect(pages(calls) == [('navigator_to', 'dialog/dropdown_dialog'), ('navigator_to', stock_nav)],
               f'{img}: kill switch opens stock {stock_nav}, not {asset} ({pages(calls)})')

    # -- shared window across Control Center long press and Settings > Wi-Fi / Bluetooth rows
    for img, asset, page_win, stock_arg in (
        ('img_wifiswitch', 'm1plus_wifi', WIFI, pod_pages.STOCK_WIFI),
        ('img_btswitch', 'm1plus_bluetooth', BT, pod_pages.STOCK_BLUETOOTH),
    ):
        m = PH([H]); m.swipe(b'01234567\n')
        m.send(img, O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold(); m.modal()
        m.push(P_)
        row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, pod_pages.ACT_STOCK); m.setword(row + 8, stock_arg)
        m.calls.clear()
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        expect(m.names_() == [H, P_, page_win] and ('switch_to', P_, page_win, 0) in pages(m.calls) and ('window_open', asset) not in m.calls,
               f'{img}: Settings row restacks the {page_win} opened by long press instead of opening a second ({pages(m.calls)}, {m.names_()})')

    # -- guards: DROPDOWN_BUSY == 2, POWER_USBSTATE == 2, airplayGetFlag() == 2 block hold both at DOWN and at fire
    for what, setup in (('DROPDOWN_BUSY is 2', lambda m: m.setword(pod.DATA['DROPDOWN_BUSY'][0], 2)),
                        ('POWER_USBSTATE is 2', lambda m: m.setword(pod.DATA['POWER_USBSTATE'][0], 2)),
                        ('AirPlay is 2', lambda m: setattr(m, 'airplay', 2))):
        m = PH([H]); m.swipe(b'01234567\n'); setup(m); m.calls.clear()
        m.send('img_wifiswitch', O['EVT_POINTER_DOWN'], 49, 65)
        expect(not [c for c in m.calls if c[0] == 'timer_add'], f'hold DOWN with {what}: no timer armed')
        m = PH([H]); m.swipe(b'01234567\n')
        m.send('img_btswitch', O['EVT_POINTER_DOWN'], 123, 65); setup(m); m.calls.clear()
        m.fire_hold(); ret, calls = m.modal()
        expect(not [c for c in m.calls if c[0] == 'dialog_quit'] and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')],
               f'hold fire with {what}: no quit, no page opened')

    # -- dialog_quit failure: pending action cleared, CLICK still suppressed (RET_STOP) so release does not toggle
    m = PH([H]); m.swipe(b'01234567\n'); m.quit_ret = 1; m.setword(PDOWN_Y, 65)
    m.send('img_wifiswitch', O['EVT_POINTER_DOWN'], 49, 65); m.fire_hold()
    r_click = m.send('img_wifiswitch', O['EVT_CLICK'], 49, 65)
    ret, calls = m.modal()
    expect(r_click == O['RET_STOP'] and m.word(PDOWN_Y) == 65 and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')],
           f'failed dialog_quit: pending dropped, pressdown_y untouched, release CLICK still suppressed ({r_click}, {pages(calls)})')

    # -- dialog ended without 0xd: pending action dropped
    m = PH([H]); m.swipe(b'01234567\n')
    m.send('img_btswitch', O['EVT_POINTER_DOWN'], 123, 65); m.fire_hold()
    m.dialog_ret = 0; ret, calls = m.modal()
    expect(ret == 0 and pages(calls) == [('navigator_to', 'dialog/dropdown_dialog')], 'non-0xd dialog end drops pending hold')

    # -- pins: on_wm_tsmove_fun pressdown_y < 81 check is pinned in PULLDOWN_PINS
    stock, built = stock_demo_bytes(), built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    p = [(a, old) for a, old, _ in pod.PULLDOWN_PINS if 0x4cd828 <= a <= 0x4cd834]
    expect(pod.DATA['PRESSDOWN_Y'][0] == 0xa05a30 and len(p) == 4 and all(word(stock, a) == old and word(built, a) == old for a, old in p),
           f'pressdown_y (0xa05a30) and the < 81 threshold words in on_wm_tsmove_fun are pinned and stock ({p})')


def labels_tests(ctx):
    """Settings > Appearance > Control Labels (ACT_PDLABELS, /mnt/data/m1plus/pulldown-labels): on by default; off hides every tile caption while keeping the discs in place."""
    expect, P = ctx.expect, pod_pages
    A = P.APPEARANCE_PAGE
    li = next(i for i, r in enumerate(A.rows) if r.action == P.ACT_PDLABELS)
    expect(P.ACT_PDLABELS == 209 and P.ACT_PDLABELS in P.SWITCH_ACTIONS and P.row_kind(A.rows[li]) == 'switch'
           and A.rows[li].label == 'Control Labels' and A.rows[li - 1].label == 'Control Center'
           and 'pulldown-labels' in P.SETTING_FILES,
           'Control Labels switch (ACT_PDLABELS 209) sits under Control Center on Appearance and is listed in Settings Files')
    src = open(os.path.join(ROOT, 'patch', 'setfiles.c')).read()
    expect('{PDLABELS_FILE, K_CHAR}' in src, 'patch/setfiles.c lists PDLABELS_FILE as K_CHAR')

    # -- pull-down init with stock order: off hides the 8 stock captions without moving any disc; default/1/invalid keeps labels shown
    for name, val in (('0 with newline', b'0\n'), ('bare 0', b'0')):
        m = PD(); m.fs[LABELS_FILE] = val; ret = m.open()
        expect(ret == 0 and not [c for c in m.calls if c[0] == 'widget_move']
               and all(m.hidden(n) for n in LAB)
               and all(m.pos(n) == m.geo[n][:2] and not m.hidden(n) for n in IMG[:N])
               and all(m.hidden(n) for n in IMG[N:]),
               f'stock order, labels off ({name}): all captions hidden and insensitive, stock discs unmoved and visible')
    for name, val in (('missing', None), ('1', b'1\n'), ('invalid', b'x\n'), ('empty', b'')):
        m = PD()
        if val is not None: m.fs[LABELS_FILE] = val
        ret = m.open()
        expect(ret == 0 and m.touched() == [] and check_layout(m, list(range(N))) is None,
               f'stock order, labels on ({name}): stock layout untouched')

    # -- custom order including our tiles: discs move to slots and show; all 16 captions stay hidden and unmoved
    order = [8, 10, 0, 1]
    m = PD(fs=b'8a01\n'); m.fs[LABELS_FILE] = b'0\n'; ret = m.open()
    want_pos = {IMG[t]: m.geo[IMG[k]][:2] for k, t in enumerate(order)}
    expect(ret == 0
           and all(m.pos(IMG[t]) == want_pos[IMG[t]] and m.props.get((m.widgets[IMG[t]], 'visible'), 1) == 1 and m.props.get((m.widgets[IMG[t]], 'sensitive'), 1) == 1 for t in order)
           and all(m.hidden(IMG[t]) and m.pos(IMG[t]) == m.geo[IMG[t]][:2] for t in range(NT) if t not in order)
           and all(m.hidden(n) and m.pos(n) == m.geo[n][:2] for n in LAB),
           'custom order with our tiles, labels off: shown discs moved and visible, hidden discs and all 16 captions hidden and unmoved')

    # -- Appearance page switch row: default on, saved off, toggle off/on atomically, failed save keeps state
    def open_appearance(saved=None):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer'] + [f'pod_{k}{i}' for k in ('row', 'value', 'label', 'switch') for i in range(len(A.rows))]
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(names)}
        if saved is not None: m.fs[LABELS_FILE] = saved
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.APPEARANCE_PAGE_INDEX)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    sw_img = lambda m: [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{li}']]
    m = open_appearance()
    expect(sw_img(m)[-1:] == ['sset_on'] and LABELS_FILE not in m.fs, 'Appearance opens with Control Labels on by default, writing nothing')
    m = open_appearance(b'0\n')
    expect(sw_img(m)[-1:] == ['sset_off'], 'Appearance shows Control Labels off when file has 0')
    m = open_appearance()
    m.click(f'pod_row{li}')
    expect(m.fs.get(LABELS_FILE) == b'0\n' and LABELS_TMP not in m.fs and ('rename', LABELS_TMP, LABELS_FILE) in m.calls and sw_img(m)[-1:] == ['sset_off'],
           'tapping Control Labels turns it off atomically')
    m.click(f'pod_row{li}')
    expect(m.fs.get(LABELS_FILE) == b'1\n' and LABELS_TMP not in m.fs and sw_img(m)[-1:] == ['sset_on'],
           'tapping again turns it back on')
    m = open_appearance(b'0\n'); m.fail.add(('write', LABELS_TMP))
    m.click(f'pod_row{li}')
    expect(m.fs.get(LABELS_FILE) == b'0\n' and LABELS_TMP not in m.fs and sw_img(m) == [], 'failed save leaves file and switch unchanged')


SECTIONS = [hook_tests, page_tests, labels_tests, files_tests, own_tests, hold_tests, flags_tests, playtile_tests, stockopen_tests, gate_tests, close_tests]

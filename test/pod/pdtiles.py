"""The pull-down's tiles (patch/pulldown.c, docs/modules/pulldown.md): the hook on dialog_dropdown_dialog_init, the saved file and the Settings > System > Appearance > Control Center page.

The hook runs the real compiled payload under the harness machine with the stock init mocked at its resume point (the dialog's handlers
and the tiles' clicks are bound by stock code, which the hook never touches); the dialog's geometry is the built asset's own
(ui/dialog/dropdown_dialog.bin). The page is the Main Menu page's twin and is tested the way menu.py tests that one."""
import os, random, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

FILE, TMP = '/mnt/data/m1plus/pulldown-tiles', '/mnt/data/m1plus/pulldown-tiles.tmp'
IMG = ('img_wifiswitch', 'img_btswitch', 'img_keylockswitch', 'img_gainswitch', 'img_usbmode', 'img_outputswitch', 'img_playset', 'img_sysset')
LAB = ('label_wifi', 'label_bt', 'label_lock', 'label_gain', 'label_usbmode', 'label_outputway', 'label_playset', 'label_sysset')
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin')
N = 8


def geometry():
    """name -> (x, y, w, h) of the built dialog's tiles and captions."""
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    return {n: (tree.find(n).x, tree.find(n).y, tree.find(n).w, tree.find(n).h) for n in IMG + LAB}


class PD(Machine):
    """The dialog's sixteen widgets (the tiles and captions, at the built asset's places) and the stock init's resume point."""

    def __init__(self, fs=None, gone=()):
        super().__init__()
        self.handlers[pod.PULLDOWN_INIT + 12] = 'stock_pulldown_resume'
        self.geo = geometry()
        self.dlg = self.alloc(0x80)
        for n, (x, y, w, h) in self.geo.items():
            if n in gone: continue
            hd = self.widget(n); self.props[(hd, 'x')], self.props[(hd, 'y')] = x, y
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
    for t in range(N):
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
    d = open(DEMO, 'rb').read(); image = bytearray(d)
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
    expect(slots == [(24, 14), (98, 14), (172, 14), (246, 14), (24, 114), (98, 114), (172, 114), (246, 114)]
           and all(g[n][2:] == (50, 50) for n in IMG), 'the tiles are 50 x 50 on the stock grid of four columns, 74 px apart, rows at y 14 and 114')
    offs = {(g[LAB[t]][0] - g[IMG[t]][0], g[LAB[t]][1] - g[IMG[t]][1]) for t in range(N)}
    expect(offs == {(-10, 54)} and all(g[n][2:] == (71, 40) for n in LAB), f'every caption is 71 x 40 at the same offset from its tile ({offs})')

    # -- 2. the stock layout: no file, a bad file, the default, a missing widget, a failed stock init ------
    default = list(range(N))
    for name, fs in (('no file', None), ('the default file', b'01234567\n'), ('without the newline', b'01234567'), ('the default with an empty hidden part', b'01234567-\n')):
        m = PD(fs=fs); ret = m.open()
        expect(ret == 0 and m.touched() == [] and check_layout(m, default) is None, f'{name}: the stock layout, nothing moved, hidden or restacked (stock\'s result {ret})')
    for name, fs in (('an unknown character', b'0123456x\n'), ('an id twice', b'0120\n'), ('an id twice across the parts', b'01-1\n'), ('a second dash', b'0-1-2\n'),
                     ('an empty file', b''), ('too long', b'01234567-0123\n'), ('lower case', b'abc\n'), ('a digit out of range', b'8\n'), ('a space', b'01 2\n'), ('a second line', b'01\n23\n')):
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
    expect(check_layout(m, [3]) is None and [c[1] for c in m.calls if c[0] == 'widget_set_visible'] == [m.widgets[n] for n in (IMG[0], LAB[0], IMG[1], LAB[1], IMG[2], LAB[2], IMG[4], LAB[4], IMG[5], LAB[5], IMG[6], LAB[6], IMG[7], LAB[7])]
           and all(c[2] == 0 for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive')),
           'every tile not listed is hidden (a listed hidden id adds nothing)')
    lookups = {c[1] for c in m.calls if c[0] == 'widget_lookup'}
    expect(lookups == set(IMG + LAB) and not any(c[0] in ('widget_destroy_children', 'widget_set_prop_str', 'widget_set_text_utf8', 'widget_set_tr_text') for c in m.calls),
           'only the sixteen tiles and captions are looked up; nothing is renamed, destroyed or re-labelled')

    # -- 4. the parser: the payload against the Python model on random files --------------------------------------------
    rnd = random.Random(11)
    for _ in range(300):
        n = rnd.choice((0, 1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 15))
        pool = b'0123456789\n -a' if rnd.random() < 0.3 else b'01234567-' if rnd.random() < 0.6 else b'01234567'
        data = bytes(rnd.choice(pool) for _ in range(n))
        if rnd.random() < 0.5:   # a valid-looking permutation with at most one '-'
            ids = list(b'01234567'); rnd.shuffle(ids); ids = ids[:rnd.randrange(0, 9)]
            if rnd.random() < 0.8: ids.insert(rnd.randrange(0, len(ids) + 1), ord('-'))
            data = bytes(ids) + rnd.choice((b'', b'\n'))
        m = PD(fs=data); m.open()
        order = P.parse_pulldown(data)
        err = check_layout(m, order)
        if err: expect(False, f'parser model differs for {data!r}: {err}'); break
    else: expect(True, 'the payload reads 300 random files as the Python model does (shown tiles in order at the stock places, the rest hidden)')
    expect(P.parse_pulldown(None) == default and P.parse_pulldown(b'') == default and P.parse_pulldown(b'01234567\n') == default and P.parse_pulldown(b'\n') == [] and P.parse_pulldown(b'-') == []
           and P.parse_pulldown(b'20-1') == [2, 0] and P.parse_pulldown(b'0-0') == default and P.parse_pulldown(b'0-1-2') == default and P.parse_pulldown(b'8') == default
           and P.parse_pulldown(b'a') == default and P.parse_pulldown(b'0123456-7890') == default and P.parse_pulldown('31\n') == [3, 1],
           'the Python model: "<shown>[-<hidden>]", a bare newline or dash hides all, an invalid file is the default')
    expect(P.format_pulldown(default) == '01234567\n' and P.format_pulldown([]) == '-01234567\n' and P.format_pulldown([3, 1]) == '31-024567\n'
           and all(P.parse_pulldown(P.format_pulldown(o)) == o for o in ([], [0], [7, 6], [4, 0, 2], list(range(7, -1, -1)))) and len(P.format_pulldown([3, 1])) < P.PULLDOWN_FILE_MAX
           and P.PULLDOWN_FILE_MAX == 12 and len(P.format_pulldown([])) < P.PULLDOWN_FILE_MAX, 'what the page saves is what the parser reads, and fits the file cap')


# ---------------------------------------------------------------------------------------------------------------------------------
# The Settings > System > Appearance > Control Center page (patch/pulldown.c pulldown_page_opened), tested as menu.py tests the Main Menu page

def page_tests(ctx):
    expect, P = ctx.expect, pod_pages
    n = N
    ROW_H = pod_ui.ROW_H
    items = list(P.PULLDOWN_TILES)
    ZX, ZW = 191, 50
    rows_s = PSYMS[f'pod_rows_{P.APPEARANCE_PAGE_INDEX}']
    s_i = next(i for i, r in enumerate(P.APPEARANCE_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.PULLDOWN_PAGE_INDEX)
    sysrows = [r.label for r in P.SETTINGS_PAGE.rows]
    a_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.APPEARANCE_PAGE_INDEX)
    expect(P.SETTINGS_PAGE.rows[a_i].label == 'Appearance' and sysrows[sysrows.index('Display') + 1:sysrows.index('Display') + 4] == ['Sample Rate RGB', 'Appearance', 'Keyboards']
           and P.SETTINGS_PAGE.rows[sysrows.index('Sample Rate RGB')].action == P.ACT_SAMPLERGB
           and P.PAGES[P.APPEARANCE_PAGE_INDEX] is P.APPEARANCE_PAGE and P.APPEARANCE_PAGE.title == 'Appearance' and [r.label for r in P.APPEARANCE_PAGE.rows] == ['Background', 'Accent', 'Control Center']
           and P.PAGES[P.PULLDOWN_PAGE_INDEX] is P.PULLDOWN_PAGE and P.PULLDOWN_PAGE.title == 'Control Center' and P.PULLDOWN_PAGE.rows == [] and P.PULLDOWN_PAGE.kind == 'pdcfg',
           'Settings > System has an Appearance link row right after Display; its page has Background and Accent, then the Control Center row in a card of its own, which opens the page of that title')
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
    expect(labels == items and on == [True] * n and up == [False] + [True] * (n - 1), f'default: the eight tiles in stock order, all on, an arrow on each but the first ({labels}, {on}, {up})')
    expect(all(('widget_on', m.widgets['pod_row3'], O[e]) in [c[:3] for c in m.calls] for e in ('EVT_CLICK', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'))
           and not any(c[0] == 'widget_on' and c[1] == m.widgets['pod_up3'] for c in m.calls) and m.names().count('widget_on') == 2 + 4 * n + 1,
           'each row is bound (click, pointer down, up, abort), no arrow is (and the window destroy)')
    expect([c[2] for c in m.calls if c[0] == 'widget_restack'] == list(range(n)), 'the children are restacked in page order')
    m = open_page(b'6502-1347\n')
    labels, on, up = state(m)
    expect(labels == [items[i] for i in (6, 5, 0, 2, 1, 3, 4, 7)] and on == [True] * 4 + [False] * 4 and up == [False, True, True, True] + [False] * 4,
           f'a saved file is laid out as saved: the shown tiles first, the hidden after them ({labels}, {on})')
    for bad in (b'xx', b'0120\n', b'8\n', b''):
        m = open_page(bad)
        expect(state(m)[0] == items and state(m)[1] == [True] * n, f'an invalid file ({bad!r}): the default')
    m = open_page(b'\n')
    expect(state(m)[1] == [False] * n and not any(state(m)[2]) and state(m)[0] == items, 'a bare newline: all eight off, no arrow')

    # a row's tap shows or hides; saved atomically; shown joins the end
    m = open_page()
    run(m, lambda: m.click('pod_row1'))
    expect(m.fs.get(FILE) == b'0234567-1\n' and ('rename', TMP, FILE) in m.calls and TMP not in m.fs, f'hide Bluetooth: saved atomically ({m.fs.get(FILE)!r})')
    labels, on, up = state(m)
    expect(labels == [items[i] for i in (0, 2, 3, 4, 5, 6, 7, 1)] and on == [True] * 7 + [False] and up == [False] + [True] * 6 + [False], f'it moves to the hidden group, its switch off ({labels}, {on})')
    run(m, lambda: m.click('pod_row1'))
    expect(m.fs.get(FILE) == b'02345671\n' and state(m)[0][7] == 'Bluetooth' and state(m)[1][7] is True, 'and shown again it joins the end')
    for i in range(n): run(m, lambda i=i: m.click(f'pod_row{i}') if str(i).encode() in m.fs[FILE].split(b'-')[0] else None)
    expect(m.fs.get(FILE) == b'-01234567\n' and state(m)[1] == [False] * n and not any(state(m)[2]), 'every tile can be hidden: "-01234567", no arrow shows')
    for i in (7, 3, 0): run(m, lambda i=i: m.click(f'pod_row{i}'))
    expect(m.fs.get(FILE) == b'730-12456\n' and state(m)[0][:3] == [items[7], items[3], items[0]], f'shown again in the order tapped ({m.fs.get(FILE)!r})')
    m = open_page(); m.fail.add(('write', TMP))
    run(m, lambda: m.click('pod_row1'))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[1] == [True] * n and TMP not in m.fs, 'a failed save is undone: the file, the order and the switches are as they were')
    m = open_page(); m.fail.add(('rename', FILE))
    run(m, lambda: m.click('pod_row1'))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[1] == [True] * n, 'a failed rename is undone too')

    # the arrow: one place up among the shown; saved at once; the first has none and its zone toggles
    m = open_page()
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'01324567\n' and state(m)[0][:4] == [items[i] for i in (0, 1, 3, 2)], f'Gain up: swaps with Buttons lock ({m.fs.get(FILE)!r})')
    run(m, lambda: arrow(m, 3)); run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'30124567\n' and state(m)[2][:2] == [False, True], 'up to the top: the arrow goes away and the next row gets one')
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(FILE) == b'0124567-3\n', 'the top row has no arrow: a tap on that spot is a toggle')
    m = open_page(b'2-01\n')
    run(m, lambda: arrow(m, 5))
    expect(m.fs.get(FILE) == b'25-013467\n', f'a hidden row has no arrow: a tap on that spot shows it at the end ({m.fs.get(FILE)!r})')
    m = open_page(); m.fail.add(('write', TMP))
    run(m, lambda: arrow(m, 5))
    expect(FILE not in m.fs and state(m)[0] == items and state(m)[2] == [False] + [True] * 7, 'a failed save of a move is undone')
    m = open_page(); m.fail.add(('write', TMP)); arrow(m, 3)
    expect(m.names().count('widget_move') == 0 and 'image_base_set_image' not in m.names() and 'widget_invalidate_force' not in m.names(), 'a failed save: the page is not touched')
    m = open_page()
    expect(all((m.widgets[f'pod_up{i}'], 0) in [c[1:3] for c in m.calls if c[0] == 'widget_set_visible'] for i in (0,)) and
           all(m.props[(m.widgets[f'pod_up{i}'], 'sensitive')] == 0 for i in range(n)), 'the first arrow is hidden and every arrow insensitive (a picture; the row decides)')

    # what the page saved is what the hook shows
    m = open_page()
    run(m, lambda: m.click('pod_row2')); run(m, lambda: arrow(m, 6)); run(m, lambda: arrow(m, 6)); saved = m.fs[FILE]
    pm = PD(fs=saved); pm.open()
    expect(saved == b'0136457-2\n' and check_layout(pm, [0, 1, 3, 6, 4, 5, 7]) is None, f'the pull-down after the page ({saved!r}): the saved tiles in the saved order, Buttons lock hidden')
    again = open_page(saved)
    expect(state(again)[0][:7] == [items[i] for i in P.parse_pulldown(saved)], 'and the page opens with it again')

    # a page that is not ours is left as it is
    for gone in ('pod_scrollview', 'pod_row3', 'pod_up7', 'pod_switch0'):
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
           'eight rows pod_row0..7: the tiles in stock order, captioned with their stock texts')
    for i, r in enumerate(rows):
        swi, upb = r.find(f'pod_switch{i}'), r.find(f'pod_up{i}')
        lab = next(c for c in r.children if c.type == 'hscroll_label')
        expect(swi.get('image') == 'sset_on' and (swi.w, swi.h) == (57, 28) and swi.get('sensitive') == 'false' and swi.x + swi.w == r.w - 12
               and upb.type == 'button' and upb.get('sensitive') == 'false' and (upb.x, upb.w, upb.h) == (ZX, ZW, ROW_H) and upb.x + upb.w == swi.x and lab.x + lab.w <= upb.x,
               f'row {i}: the switch on, insensitive, 12 px from the right; the arrow zone left of it; the label clear of both')
    keys = {pod_i18n.key_for(t) for t in items}
    expect(keys == {'Wi-Fi', 'Bluetooth', 'Button Lock', 'Gain', 'USB Mode', 'Output', 'Playback', 'System'} and len(keys) == n,
           f'the row labels are our own short texts, one per tile: {sorted(keys)}')


# ---------------------------------------------------------------------------------------------------------------------------------
# The Settings Files page lists the new file like home-menu

def files_tests(ctx):
    expect, P = ctx.expect, pod_pages
    expect(P.SETTING_FILES.index('pulldown-tiles') == P.SETTING_FILES.index('home-menu') + 1 and P.SETTING_FILES.count('pulldown-tiles') == 1, 'the Settings Files page lists pulldown-tiles right after home-menu (patch/setfiles.c has it in the same place)')
    src = open(os.path.join(ROOT, 'patch', 'setfiles.c')).read()
    expect('{PULLDOWN_FILE, K_MENU}' in src and src.index('{MENU_FILE, K_MENU}') < src.index('{PULLDOWN_FILE, K_MENU}') < src.index('{KBZH_FILE, K_CHAR}'),
           'and shows its first 12 characters like home-menu (the seeded value is checked in homecover.py files_tests)')


SECTIONS = [hook_tests, page_tests, files_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

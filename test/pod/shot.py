"""Screenshot (patch/shot.c): the Settings row, the 5 s countdown with the status bar camera, the frame buffer read in every
format the driver can report, the BMP bytes, numbering, the card checks, every failure path, double taps, the kill switch."""
import os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DEFS = {}
for _line in open(os.path.join(ROOT, 'patch', 'shot.h')).read().replace('\\\n', ' ').splitlines():
    _m = re.match(r'#define\s+(\w+)\s+("[^"]*"|\w+)\s*(?:/\*.*)?$', _line.strip())
    if _m: DEFS[_m.group(1)] = _m.group(2).strip('"') if _m.group(2).startswith('"') else int(_m.group(2), 0)
DIR, TMP, FB = DEFS['SHOT_DIR'], DEFS['SHOT_TMP'], DEFS['SHOT_FB']
RET_REPEAT, KILL = 8, '/mnt/mmc/m1plus-off'

# format name -> (bytes per pixel, (red offset, length), (green), (blue)): what the driver reports in fb_var_screeninfo
FORMATS = {
    'rgb565': (2, (11, 5), (5, 6), (0, 5)),     # AWTK's lcd_mem_bgr565 (blue in the low bits)
    'bgr565': (2, (0, 5), (5, 6), (11, 5)),
    'bgra5551': (2, (10, 5), (5, 5), (0, 5)),   # lcd_mem_bgra5551, the first branch of lcd_linux_fb_create
    'bgra8888': (4, (16, 8), (8, 8), (0, 8)),
    'rgba8888': (4, (0, 8), (8, 8), (16, 8)),
    'rgb888': (3, (16, 8), (8, 8), (0, 8)),
}


def expand(c, n): return c if n == 8 else (c << (8 - n)) | (c >> (2 * n - 8))


def make_frame(w, h, fmt, pad=0, pages=1, page=0, seed=1):
    """(memory, rows): the frame buffer the driver maps (pages screens of rows `line` bytes apart, the visible one `page`; the
    others and the row padding are garbage) and the picture it shows, rows of (r, g, b)."""
    bytes_, red, green, blue = FORMATS[fmt]
    line = w * bytes_ + pad
    state = [seed]
    def rnd():
        state[0] = (state[0] * 1103515245 + 12345) & 0x7fffffff
        return state[0]
    mem = bytearray(line * h * pages)
    rows = []
    for p in range(pages):
        for y in range(h):
            row = []
            for x in range(w):
                r, g, b = (rnd() >> 7 & ((1 << n) - 1) for _, n in (red, green, blue))
                px = rnd() & ((1 << (8 * bytes_)) - 1)                      # the unused bits (alpha) are noise
                for (off, n), c in ((red, r), (green, g), (blue, b)):
                    px = px & ~(((1 << n) - 1) << off) | c << off
                at = (p * h + y) * line + x * bytes_
                mem[at:at + bytes_] = px.to_bytes(bytes_, 'little')
                if p == page: row.append(tuple(expand(c, n) for c, (_, n) in zip((r, g, b), (red, green, blue))))
            if p == page: rows.append(row)
            for i in range(pad): mem[(p * h + y) * line + w * bytes_ + i] = rnd() & 255
    return bytes(mem), rows


def bmp_bytes(rows):
    h, w = len(rows), len(rows[0])
    stride = (w * 3 + 3) & ~3
    head = b'BM' + struct.pack('<IHHI', 54 + stride * h, 0, 0, 54) + struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, stride * h, 2835, 2835, 0, 0)
    return head + b''.join(bytes(c for r, g, b in row for c in (b, g, r)) + bytes(stride - 3 * w) for row in reversed(rows))


def set_fb(m, w, h, fmt, pad=0, pages=1, page=0, seed=1, **over):
    """m.fb as the driver answers FBIOGET_VSCREENINFO / FSCREENINFO; over: fields to corrupt (xres, yoffset, bpp, red_len ...)."""
    mem, rows = make_frame(w, h, fmt, pad, pages, page, seed)
    bytes_, red, green, blue = FORMATS[fmt]
    var, fix = [0] * DEFS['FBV_WORDS'], [0] * DEFS['FBF_WORDS']
    var[DEFS['FBV_XRES']], var[DEFS['FBV_YRES']], var[2], var[DEFS['FBV_YRES_VIRTUAL']] = w, h, w, h * pages
    var[DEFS['FBV_YOFFSET']], var[DEFS['FBV_BPP']] = page * h, 8 * bytes_
    for key, (off, n) in (('FBV_RED', red), ('FBV_GREEN', green), ('FBV_BLUE', blue)): var[DEFS[key]], var[DEFS[key] + 1] = off, n
    fix[DEFS['FBF_SMEM_LEN']], fix[DEFS['FBF_LINE_LENGTH']] = len(mem), w * bytes_ + pad
    for k, v in over.items():
        if k in ('smem_len', 'line_length'): fix[DEFS['FBF_' + k.upper()]] = v
        elif k == 'bpp': var[DEFS['FBV_BPP']] = v
        elif k == 'red_len': var[DEFS['FBV_RED'] + 1] = v
        elif k == 'blue_off': var[DEFS['FBV_BLUE']] = v
        else: var[DEFS['FBV_' + k.upper()]] = v
    m.fb = {'var': var, 'fix': fix, 'mem': mem}
    return rows


def shot_machine(**kw):
    m = Machine()
    m.ind = m.widget('pod_shot')            # the camera in the system bar's right group
    m.confirm_yes = True                    # Yes in the Cancel dialog (the No tests clear it)
    m.confirm_answers = {'Take a screenshot in:': DEFS['SHOT_QUIT_SHORT']}   # the Take dialog: its left button, 5 s (tests set another code)
    m.rows = set_fb(m, kw.pop('w', 320), kw.pop('h', 480), kw.pop('fmt', 'rgb565'), **kw)
    return m


class Run:
    """One tap and what follows it: every call, in order, with the step that made it."""
    def __init__(self, m):
        self.m, self.log, self.steps = m, [], []

    def step(self, name, fn, count=400000000):
        v = self.m.call(PSYMS[fn], count=count)
        self.steps.append((name, v)); self.log += [(name,) + tuple(c) for c in self.m.calls]
        return v

    def toasts(self): return [c[2] for c in self.log if c[1] == 'toast']

    def index(self, *key):
        """The position in the log of the first call that starts with key: (step, call, args ..) or, when the first word
        is not the name of a step, (call, args ..)."""
        named = key[0] in {s[0] for s in self.steps} | {'tap', 'tick', 'grab'}
        return next((i for i, c in enumerate(self.log) if (c[:len(key)] if named else c[1:1 + len(key)]) == key), None)

    def has(self, *key): return self.index(*key) is not None

    def full(self, ticks=5):
        """Tap, the countdown's ticks, the grab."""
        self.step('tap', 'shot_start')
        for _ in range(ticks): self.step('tick', 'shot_tick')
        return self.step('grab', 'shot_grab')


def lang(m, loc):
    """The machine speaks loc; its Take dialog's text is translated, so the answer (the 5 s button) is keyed by that text."""
    m.set_language(loc); m.confirm_answers = {tr_of(loc)('Take a screenshot in:'): DEFS['SHOT_QUIT_SHORT']}


def files(m): return {p: d for p, d in m.fs.items() if p.startswith(DIR)}


def run(ctx):
    expect = ctx.expect
    P = pod_pages
    tick_ms, settle_ms = DEFS['SHOT_TICK_MS'], DEFS['SHOT_SETTLE_MS']
    TICK, GRAB = PSYMS['shot_tick'], PSYMS['shot_grab']
    ASK1, ASK, CANCEL = 'Take a screenshot?', 'Take a screenshot in:', 'Cancel the screenshot?'
    def adds(r): return sum(1 for c in r.log if c[1] == 'timer_add' and c[2] in (TICK, GRAB))
    def asked(r): return [c[2] for c in r.log if c[1] == 'confirm' and c[2] != ASK1]   # the delay and Cancel dialogs (step 1 has its own tests)

    # 1. What is pinned. The format is learned the way stock learns it: lcd_linux_fb_create opens /dev/fb0 and issues
    #    ioctl 0x4602 and 0x4600 (`addiu $a1, $zero, 0x4602` @0x63953c, 0x4600 @0x639558), then mmaps the node.
    m = Machine()
    word = lambda a: struct.unpack('<I', bytes(m.u.mem_read(a, 4)))[0]
    expect(word(0x63953c) == 0x24054602 | 0 and word(0x639558) == 0x24054600, 'stock lcd_linux_fb_create issues FBIOGET_FSCREENINFO 0x4602 then FBIOGET_VSCREENINFO 0x4600')
    expect(DEFS['FBIOGET_VSCREENINFO'] == 0x4600 and DEFS['FBIOGET_FSCREENINFO'] == 0x4602, 'the payload issues the same two ioctls')
    expect(bytes(m.u.mem_read(0x74b3d8, 9)) == b'/dev/fb0\0' and DEFS['SHOT_FB'] == '/dev/fb0', 'the node is stock\'s /dev/fb0 @0x74b3d8')
    expect(all(n in pod.LIBC for n in ('ioctl', 'mmap', 'munmap')) and len(pod.got_slots(DEMO, ['ioctl', 'mmap', 'munmap'])) == 3,
           'ioctl, mmap and munmap are imports of demo, reached through its own GOT slots')
    expect(DEFS['FBV_WORDS'] * 4 == 160 and DEFS['FBF_WORDS'] * 4 == 68 and DEFS['FBF_SMEM_LEN'] == 5 and DEFS['FBF_LINE_LENGTH'] == 11
           and (DEFS['FBV_RED'], DEFS['FBV_GREEN'], DEFS['FBV_BLUE'], DEFS['FBV_BPP'], DEFS['FBV_YOFFSET']) == (8, 11, 14, 6, 5),
           'the field indexes are those of linux/fb.h (fb_var_screeninfo 160 bytes, fb_fix_screeninfo 68; stock reads bpp @0x68, red @0x70, blue @0x88 of its copy)')
    expect(DEFS['SHOT_SECONDS'] == 5 and tick_ms == 1000 and settle_ms >= 50 and DEFS['SHOT_MAX_NUM'] == 9999, '5 s in 1 s ticks, a settle of at least three frames, numbers up to 9999')

    # 2. The Developer row: the only row of Settings > Developer, bound to ACT_SHOT; a tap asks first.
    S = P.DEVELOPER_PAGE
    item = 2
    expect(S.key == 'm1plus_developer' and [r.label for r in S.rows] == ['Boot to M1+ Music', 'Open Shanling Home', 'Screenshot', 'Cover Cache', 'Clear Track Durations', 'Settings Files', 'System Update'] and S.rows[item].action == P.ACT_SHOT == 14 and P.PAGES[P.DEVELOPER_PAGE_INDEX] is S,
           'Screenshot is the third row of the Developer page (under Startup; System Update next)')
    expect(not [r for page in P.PAGES if page is not S for r in page.rows if r.action == P.ACT_SHOT],
           'no other page has a Screenshot row (menu, Extras and Main Menu page have none)')
    rows_s = PSYMS[f'pod_rows_{P.DEVELOPER_PAGE_INDEX}']
    m = shot_machine()
    expect((m.read_cstr(m.word(rows_s + 12 * item)), m.word(rows_s + 12 * item + 4)) == ('pod_row2', P.ACT_SHOT), 'the payload row table binds pod_row2 of the Developer page to ACT_SHOT')
    m.call(PSYMS['on_row'], a0=rows_s + 12 * item)
    expect([c[1:] for c in m.calls if c[0] == 'confirm'] == [(ASK1, O['CONFIRM_KIND_WRAP']), (ASK, O['CONFIRM_KIND_WRAP'])] and ('timer_add', TICK, tick_ms) in m.calls
           and 'toast' not in m.names() and 'window_open' not in m.names() and 'stock_resume' not in m.names(),
           'tapping the row asks in the stock confirm dialog (kind 5, wrapped); Yes starts the countdown: a 1 s timer, no toast, no page opens')
    ui = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui')
    tree = awtk_ui.parse(open(os.path.join(ui, 'm1plus_developer.bin'), 'rb').read())
    row = tree.find(f'pod_row{item}')
    expect(row is not None and pod_i18n.shown_english(next(c for c in row.children if c.type == 'hscroll_label')) == 'Screenshot'
           and next(c for c in row.children if c.name == 'pod_icon').get('image') == 'pod_ci_camera', 'the Developer row reads Screenshot, with the camera glyph')
    for key in ('m1plus_extras', 'm1plus_menu', 'm1plus_mainmenu', 'm1plus_settings'):
        t = awtk_ui.parse(open(os.path.join(ui, key + '.bin'), 'rb').read())
        expect(not [w for w in t.walk() if w.type == 'hscroll_label' and pod_i18n.shown_english(w) == 'Screenshot'],
               f'{key} has no Screenshot row')

    # 3. The status bar camera: a hidden, insensitive image at the end of the right-aligned icon group, the image the icon step adds.
    bar = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    cam, group = bar.find(DEFS['SHOT_IND']), bar.find('view_bar_right')
    expect(cam is not None and group.children[-1] is cam and cam.get('visible') == 'false' and cam.get('sensitive') == 'false' and cam.get('image') == 'pod_bar_shot'
           and sum(w.name == 'pod_shot' for w in bar.walk()) == 1, 'pod_shot is the last child of view_bar_right, hidden and insensitive, showing pod_bar_shot')
    expect([c.name for c in group.children[:-2] if c.name != 'pod_sync'] == ['img_btclass', 'img_synclink', 'img_wifi'] and group.children[-2].name == 'pod_pct',
           'the stock icons of the group are untouched and in order, then the hidden battery percentage (test/pod/battery.py)')
    expect(os.path.isfile(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx/pod_bar_shot.png')), 'the camera image is in the tree')
    stock_bar = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    expect({w.name for w in stock_bar.walk()} == {w.name for w in bar.walk()} - {'pod_shot', 'pod_pct', 'pod_lo', 'pod_sync'}, 'no stock widget is renamed or removed')
    # layout: the group's icons are laid out right-aligned from its right edge, the camera last, 4 px between; in the worst case
    # (Bluetooth 47, SyncLink 16, Wi-Fi 24 and the camera 16 at 4 px) the boxes start 111 px before the battery gap, but the
    # Bluetooth image is right-aligned art (its ink is the right 11 of 47 px), so every icon's ink starts right of the clock's text
    # at both clock settings
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts/default.ttf'))
    clock = bar.find('bar_dclock')
    clock_px = int(clock.get('style:normal:font_size'))
    sizes = {w.name: w.w for w in group.children if w.name not in ('pod_pct', 'pod_sync')}   # (the battery percentage and the sync icon are hidden here; their layout is test/pod/battery.py's and test/pod/lineout.py's)
    from PIL import Image
    imgs = {'img_btclass': 'bar_bt', 'img_synclink': 'bar_synclink', 'img_wifi': 'bar_wifi0', 'pod_shot': 'pod_bar_shot'}
    ink_left = {n: Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', f'{f}.png')).convert('RGBA').getchannel('A').getbbox()[0]
                for n, f in imgs.items()}       # each image is drawn 1:1 in a box of its own width (scale_auto / center)
    spans, edge = {}, group.x + group.w
    for name in reversed(list(sizes)):
        spans[name] = (edge - sizes[name], edge); edge -= sizes[name] + 4
    clock_end = {text: clock.x + (clock.w + StbText(font, clock_px).layout(text)[1]) // 2 for text in ('12:59', '12:59 PM', '10:59 AM', '12:59 AM')}
    gaps = {name: spans[name][0] + ink_left[name] for name in spans}   # where each icon's ink starts
    expect(spans['pod_shot'] == (group.x + group.w - 16, group.x + group.w) and group.x + group.w + 4 == bar.find('img_battery').x,
           'the camera sits against the right end of the group, 4 px before the battery outline')
    expect(all(gaps[n] >= max(clock_end.values()) + 4 for n in ('img_btclass', 'img_synclink', 'img_wifi', 'pod_shot')),
           f'every icon\'s ink, camera shown with Bluetooth, SyncLink and Wi-Fi all lit, starts clear of the 12 h and 24 h clock ({gaps}, clock ends {clock_end})')

    # 4. A capture, byte for byte, in every format; row padding, a visible buffer other than the first (double buffering).
    for fmt in FORMATS:
        for pad, pages, page in ((0, 1, 0), (12, 2, 1)):
            m = shot_machine(w=37, h=23, fmt=fmt, pad=pad, pages=pages, page=page, seed=3 + page)
            r = Run(m); r.full()
            got = files(m)
            expect(got == {f'{DIR}/shot-0001.bmp': bmp_bytes(m.rows)}, f'{fmt} pad {pad} page {page}: shot-0001.bmp is exactly the visible frame as a 24 bit BMP ({len(got)} files, {[len(v) for v in got.values()]})')
    mem, rows = make_frame(320, 480, 'rgb565', seed=9)
    m = shot_machine(); r = Run(m); r.full()
    out = files(m)[f'{DIR}/shot-0001.bmp']
    expect(len(out) == 54 + 960 * 480 and out == bmp_bytes(m.rows) and out[:2] == b'BM' and struct.unpack_from('<iiH', out, 18)[0:2] == (320, 480),
           f'320x480 RGB565: {len(out)} bytes, the exact frame, bottom-up')
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(out)); im.load()
    expect(im.format == 'BMP' and im.size == (320, 480) and list(im.convert('RGB').getdata()) == [px for row in m.rows for px in row],
           'an independent reader (Pillow, as tools/pull_shots.py) opens the file and sees the same 320x480 picture')
    expect(r.toasts() == ['Screenshot saved'], f'toasts: {r.toasts()}')
    expect(r.has('grab', 'munmap') and [c for c in r.log if c[1] == 'mmap'][0][3:5] == (1, 1),
           'the frame buffer is mapped read-only and shared, and unmapped')
    # the sequence: camera on at the tap, shown through the countdown; the last tick hides it and arms the grab; the grab opens the frame buffer
    # only after the hide, and the toast comes after the file is written
    shown, hidden = r.index('tap', 'widget_set_visible', m.ind, 1), r.index('tick', 'widget_set_visible', m.ind, 0)
    expect(shown is not None and r.steps == [('tap', 0), ('tick', RET_REPEAT), ('tick', RET_REPEAT), ('tick', RET_REPEAT), ('tick', RET_REPEAT), ('tick', 0), ('grab', 0)],
           f'the camera is shown at the tap; four ticks repeat, the fifth ends its timer ({r.steps})')
    expect([c[0] for c in r.log if c[1] == 'widget_set_visible'] == ['tap', 'tick', 'grab'] and [(c[3]) for c in r.log if c[1] == 'widget_set_visible'] == [1, 0, 0],
           'widget_set_visible: shown at the tap, hidden at the last tick, hidden again when the capture ends')
    open_fb = r.index('grab', 'open', FB)
    arm = r.index('tick', 'timer_add', GRAB, settle_ms)
    expect(arm is not None and hidden < arm < open_fb and ('tap', 'timer_add', TICK, tick_ms) in r.log,
           'order: the camera is hidden, then the grab timer is armed (120 ms), then /dev/fb0 is opened: the camera is never in the picture')
    expect(not any(c[0] == 'tick' and c[1] in ('open', 'mmap') for c in r.log) and not files(m).get(TMP), 'nothing is read or written before the grab')
    rn = r.index('grab', 'rename', TMP, f'{DIR}/shot-0001.bmp')
    ts = r.index('grab', 'toast')
    expect(rn is not None and open_fb < rn < ts and r.index('grab', 'fsync', TMP) < rn and ('grab', 'mkdir', DIR) in r.log,
           'the file is written to a temp name, fsynced, renamed; the directory is created; the toast comes after')
    expect(m.props[(m.ind, 'visible')] == 0 and TMP not in m.fs and DIR in m.present and not m.fds, 'afterwards: camera hidden, no temp file, no descriptor left open')
    expect(not any(c[1] == 'timer_remove' for c in r.log), 'no timer is removed by hand: the tick ends by its return value, the grab is one-shot')

    # 5. Numbering: the first free number, bounded.
    m = shot_machine(w=8, h=4)
    for n in (1, 2, 4): m.present.add(f'{DIR}/shot-{n:04d}.bmp')
    r = Run(m); r.full()
    expect(f'{DIR}/shot-0003.bmp' in m.fs and len(files(m)) == 1, 'with 0001, 0002 and 0004 taken the next file is shot-0003.bmp')
    r = Run(m); r.full()
    expect(f'{DIR}/shot-0003.bmp' in m.fs and any(p.endswith('shot-0005.bmp') for p in m.fs) is True and len(files(m)) == 2, 'then the next free one, 0005')
    m = shot_machine(w=8, h=4)
    m.present.update(f'{DIR}/shot-{n:04d}.bmp' for n in range(1, 10000))
    r = Run(m); r.full()
    acc = [c for c in r.log if c[1] == 'access' and 'shot-' in c[2]]
    expect(not files(m) and r.toasts()[-1] == 'Screenshot failed' and len(acc) == 9999, f'all 9999 numbers taken: a failure toast, no file, a bounded scan ({len(acc)} probes)')
    m = shot_machine(w=8, h=4); m.present.add(f'{DIR}/shot-9998.bmp'); m.present.update(f'{DIR}/shot-{n:04d}.bmp' for n in range(1, 9998))
    r = Run(m); r.full()
    expect(f'{DIR}/shot-9999.bmp' in m.fs, 'the last number, 9999, is usable')

    # 6. The card: mounted, room, writable directory. Failures toast "Storage unavailable", leave nothing and read no frame.
    def failing(setup, toast, why, ticks=5):
        m = shot_machine(w=16, h=8); setup(m)
        r = Run(m); r.full(ticks)
        expect(r.toasts()[-1] == toast and not files(m) and TMP not in m.fs and m.props[(m.ind, 'visible')] == 0 and not m.fds,
               f'{why}: toast {toast!r}, no file, no temp, camera hidden, no descriptor left ({r.toasts()}, {sorted(files(m))})')
        return m, r
    def unmounted(m): m.card_mounted = False
    m, r = failing(unmounted, 'Storage unavailable', 'no card')
    expect(not r.has('mkdir') and not r.has('open', TMP, 0x301), 'no card: no directory is made, nothing is opened for writing')
    for free, ok in ((0, False), (16, False), (17, True)):
        m = shot_machine(w=320, h=480); m.free_mb = free
        r = Run(m); r.full()
        expect(bool(files(m)) == ok and r.toasts()[-1] == ('Screenshot saved' if ok else 'Storage unavailable'),
               f'{free} MB free: {"saved" if ok else "refused"} (16 MB stay free, plus the 460854 byte file)')
    failing(lambda m: m.fail.add(('mkdir', DIR)), 'Storage unavailable', 'the directory cannot be made')
    failing(lambda m: m.fail.add(('statfs', DIR)), 'Storage unavailable', 'statfs fails')
    failing(lambda m: m.fail.add(('open', TMP)), 'Storage unavailable', 'the temp file cannot be created')
    # write failures: no partial file, the temp removed
    m, r = failing(lambda m: m.fail.add(('write', TMP)), 'Screenshot failed', 'a write fails')
    expect(r.has('grab', 'unlink', TMP), 'the temp file is unlinked')
    failing(lambda m: m.fail.add(('fsync', TMP)), 'Screenshot failed', 'fsync fails')
    failing(lambda m: m.fail.add(('rename', f'{DIR}/shot-0001.bmp')), 'Screenshot failed', 'the rename fails')
    m = shot_machine(w=16, h=8); r = Run(m); r.step('tap', 'shot_start')
    m.fail.add(('write', TMP))
    for _ in range(5): r.step('tick', 'shot_tick')
    r.step('grab', 'shot_grab')
    expect(not files(m) and r.toasts()[-1] == 'Screenshot failed', 'a write that fails after the header went out (the first row) leaves no file either')

    # 7. The frame buffer: absent, failing, or not in a form that can be read exactly: a failure toast, no file, mapping released.
    def fbfail(setup, why, mapped=False):
        m = shot_machine(w=16, h=8); setup(m)
        r = Run(m); r.full()
        expect(r.toasts()[-1] == 'Screenshot failed' and not files(m) and not r.has('grab', 'rename') and not m.fds and r.has('grab', 'munmap') == mapped,
               f'{why}: Screenshot failed, no file, descriptor closed, mapping {"released" if mapped else "never made"} ({r.toasts()})')
    fbfail(lambda m: setattr(m, 'fb', None), 'no /dev/fb0')
    fbfail(lambda m: m.fail.add(('ioctl', 0x4600)), 'FBIOGET_VSCREENINFO fails')
    fbfail(lambda m: m.fail.add(('ioctl', 0x4602)), 'FBIOGET_FSCREENINFO fails')
    fbfail(lambda m: m.fail.add(('mmap',)), 'mmap fails')
    for what, over in (('8 bits per pixel', {'bpp': 8}), ('a 64 bit pixel', {'bpp': 64}), ('a 3 bit channel', {'red_len': 3}),
                       ('a channel past the pixel', {'blue_off': 14}), ('no width', {'xres': 0}), ('a frame wider than 1024', {'xres': 1025}),
                       ('a visible buffer past the virtual screen', {'yoffset': 5}), ('a line shorter than the row', {'line_length': 30}),
                       ('a mapping shorter than the visible buffer', {'smem_len': 100})):
        fbfail(lambda m, over=over: set_fb(m, 16, 8, 'rgb565', **over), what)
    m = shot_machine(w=16, h=8); set_fb(m, 16, 8, 'rgb565', pages=2, page=1); m.fb['var'][DEFS['FBV_YOFFSET']] = 9
    r = Run(m); r.full()
    expect(not files(m) and r.toasts()[-1] == 'Screenshot failed', 'a yoffset that puts the screen past the memory is refused, not read')

    # 8. One capture at a time. A tap while one is pending (counting or waiting for the grab) does nothing at all; after it, taps work again.
    m = shot_machine(w=8, h=4); r = Run(m)
    r.step('tap', 'shot_start'); m.confirm_yes = False
    r.step('tap2', 'shot_start')
    expect([n for n in m.names() if n != 'access'] == ['navigator_to_with_context', 'confirm'] and asked(r)[-1] == CANCEL,
           f'a second tap during the countdown only asks whether to cancel (no new timer, toast or camera call) ({m.names()})')
    for _ in range(5): r.step('tick', 'shot_tick')
    r.step('tap3', 'shot_start'); expect(set(m.names()) <= {'access'}, 'nor while the grab is pending (no dialog either)')
    m.confirm_yes = True
    r.step('grab', 'shot_grab')
    expect(r.toasts() == ['Screenshot saved'] and len(files(m)) == 1 and adds(r) == 2, 'one countdown, one grab, one file')
    r = Run(m); r.full()
    expect(len(files(m)) == 2 and r.toasts() == ['Screenshot saved'], 'a tap after the capture starts the next one (shot-0002)')
    m = shot_machine(w=8, h=4); m.timer_fail = True
    r = Run(m); r.step('tap', 'shot_start')
    expect(r.toasts() == ['Screenshot failed'] and not r.has('widget_set_visible'), 'no timer at the tap: a failure toast, the camera never shown')
    m.timer_fail = False; r.step('tap', 'shot_start')
    expect(r.has('timer_add', TICK, tick_ms) and m.props[(m.ind, 'visible')] == 1, 'and the next tap can start (nothing was left pending)')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    for _ in range(4): r.step('tick', 'shot_tick')
    m.timer_fail = True; r.step('tick', 'shot_tick')
    expect(r.toasts()[-1] == 'Screenshot failed' and m.props[(m.ind, 'visible')] == 0 and not files(m), 'no timer for the grab: the camera is hidden again and a failure toast shows')
    m.timer_fail = False; r.step('tap', 'shot_start'); expect(m.props[(m.ind, 'visible')] == 1, 'and the machine is idle again')
    m = shot_machine(w=8, h=4); del m.widgets['pod_shot']
    r = Run(m); r.full()
    expect(not r.has('widget_set_visible') and len(files(m)) == 1, 'no pod_shot in the window tree: the capture still works, without the camera')

    # 9. The kill switch: nothing starts; one that appears mid-way stops the sequence, camera hidden, nothing read or written.
    m = shot_machine(w=8, h=4); m.present.add(KILL)
    r = Run(m); r.step('tap', 'shot_start')
    expect(not m.calls or m.names() == ['access'] * len(m.names()), f'kill switch present: the tap does nothing but look for it ({m.names()})')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start'); m.present.add(KILL)
    for _ in range(2): r.step('tick', 'shot_tick')
    expect(r.steps[-1] == ('tick', 0) and m.props[(m.ind, 'visible')] == 0 and not r.has('timer_add', GRAB), 'the kill switch during the countdown: the tick ends, the camera is hidden, no grab is armed')
    r.step('tap', 'shot_start'); expect(r.toasts() == [] and not any(c[1] == 'timer_add' for c in r.log[-4:]), 'and with it still there no new countdown starts')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    for _ in range(5): r.step('tick', 'shot_tick')
    m.present.add(KILL); r.step('grab', 'shot_grab')
    expect(not r.has('grab', 'open', FB) and not files(m) and m.props[(m.ind, 'visible')] == 0 and r.toasts() == [], 'the kill switch just before the grab: nothing is read, written or shown')
    m.present.discard(KILL); r.step('tap', 'shot_start'); expect(m.props[(m.ind, 'visible')] == 1, 'removed again, the next tap starts normally')

    # 10. Every text goes through the stock translation: the row, the countdown and both outcomes, in all 16 tables.
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        m = shot_machine(w=8, h=4); lang(m, loc); r = Run(m); r.full()
        expect(r.toasts() == [T('Screenshot saved')], f'{loc}: the success toast reads {T("Screenshot saved")!r}')
        m = shot_machine(w=8, h=4); lang(m, loc); m.fb = None; r = Run(m); r.full()
        expect(r.toasts()[-1] == T('Screenshot failed'), f'{loc}: the failure toast')
        m = shot_machine(w=8, h=4); lang(m, loc); m.free_mb = 1; r = Run(m); r.full()
        expect(r.toasts()[-1] == T('Storage unavailable'), f'{loc}: the storage toast')

        m = shot_machine(w=8, h=4); lang(m, loc); r = Run(m); r.step('tap', 'shot_start'); r.step('tap2', 'shot_start')
        expect([c[2] for c in r.log if c[1] == 'confirm'] == [T(ASK1), T(ASK), T(CANCEL)], f'{loc}: the three dialogs read {T(ASK1)!r} / {T(ASK)!r} / {T(CANCEL)!r}')

    # 11. Confirm and cancel. The tap asks first; only Yes starts. While counting, a tap asks to cancel; Yes removes the tick timer.
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = 0; r = Run(m); r.step('tap', 'shot_start')
    expect(asked(r) == [ASK] and not r.has('timer_add', TICK, tick_ms) and not r.has('widget_set_visible') and not r.toasts() and not r.has('timer_remove'), 'No: nothing starts, no timer, no camera, no toast')
    m.confirm_answers[ASK] = 4; r.step('tap', 'shot_start')
    expect(asked(r) == [ASK, ASK] and r.has('tap', 'timer_add', TICK, tick_ms) and m.props[(m.ind, 'visible')] == 1, 'and the next tap can still start (nothing was left pending)')
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = 0x14; r = Run(m); r.step('tap', 'shot_start')
    expect(not r.has('timer_add', TICK, tick_ms) and not r.toasts(), 'any answer but the two buttons (the back key, the dialog failing to open) does nothing')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start'); r.step('tick', 'shot_tick'); r.step('tick', 'shot_tick')
    m.confirm_yes = False; r.step('tap2', 'shot_start')
    expect(asked(r) == [ASK, CANCEL] and not r.has('timer_remove') and m.props[(m.ind, 'visible')] == 1, 'No to Cancel: the countdown goes on, camera still shown')
    for _ in range(3): r.step('tick', 'shot_tick')
    r.step('grab', 'shot_grab')
    expect(len(files(m)) == 1 and r.toasts() == ['Screenshot saved'], 'and it completes as normal')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start'); r.step('tick', 'shot_tick'); r.step('tick', 'shot_tick')
    r.step('tap2', 'shot_start')
    expect(asked(r) == [ASK, CANCEL] and r.has('tap2', 'timer_remove', 0x777) and m.props[(m.ind, 'visible')] == 0 and not r.toasts(), 'Yes to Cancel: the tick timer is removed, the camera hidden, no toast')
    n = len(r.log); r.step('tap3', 'shot_start')
    expect(asked(r)[-1] == ASK and r.has('tap3', 'timer_add', TICK, tick_ms) and m.props[(m.ind, 'visible')] == 1 and not files(m), 'back to idle: a tap asks to take again and can start; no file was written')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start'); r.step('tick', 'shot_tick'); r.step('tap2', 'shot_start'); r.step('tap3', 'shot_start')
    expect(asked(r) == [ASK, CANCEL, ASK] and adds(r) == 2, 'a second countdown after a cancel is a normal one')
    for _ in range(5): r.step('tick', 'shot_tick')
    r.step('grab', 'shot_grab')
    expect(len(files(m)) == 1 and r.toasts() == ['Screenshot saved'], 'and takes its picture')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    for _ in range(5): r.step('tick', 'shot_tick')
    n = len(asked(r)); r.step('tap2', 'shot_start')
    expect(len(asked(r)) == n and not r.has('tap2', 'timer_remove') and set(m.names()) <= {'access'}, 'a tap during the settle phase (capture committed) shows no dialog and removes nothing')
    r.step('grab', 'shot_grab'); expect(len(files(m)) == 1, 'the capture completes')
    # kill switch at the tap (each tick and the grab are in section 9)
    m = shot_machine(w=8, h=4); m.present.add(KILL); r = Run(m); r.step('tap', 'shot_start')
    expect(not asked(r), 'kill switch present: the tap shows no dialog')

    # 12. The choice is on the confirm dialog: its left button (btn_cancel, quits with 4) is 5 s, its right (btn_enter, 0xa) is 10 s.
    #     Stock: btn_cancel's click handler 0x473230 is `addiu $a1, $zero, 4` into dialog_quit, btn_enter returns CONFIRM_YES.
    expect(DEFS['SHOT_QUIT_SHORT'] == 4 and DEFS['SHOT_QUIT_LONG'] == O['CONFIRM_YES'] == 0xa and DEFS['SHOT_SECONDS_LONG'] == 10
           and word(0x473230 + 20) == 0x24050004 and (DEFS['SHOT_DIALOG'], DEFS['SHOT_BTN_SHORT'], DEFS['SHOT_BTN_LONG']) == ('confirminfo_dialog', 'btn_cancel', 'btn_enter'),
           'btn_cancel quits with 4 (stock @0x473230), btn_enter with 0xa; the dialog and button names are stock\'s')
    expect(bytes(m.u.mem_read(0x744044, 11)) == b'btn_cancel\0' and bytes(m.u.mem_read(0x744030, 10)) == b'btn_enter\0', 'the names are the strings stock binds (0x744044, 0x744030)')
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = DEFS['SHOT_QUIT_LONG']; r = Run(m); r.step('tap', 'shot_start')
    expect(asked(r) == [ASK] and r.has('tap', 'timer_add', TICK, tick_ms), 'the right button (10 s) starts the countdown')
    rets = [r.step('tick', 'shot_tick') for _ in range(10)]
    expect(rets[:9] == [RET_REPEAT] * 9 and rets[9] == 0 and adds(r) == 2 and m.props[(m.ind, 'visible')] == 0, 'nine ticks repeat, the tenth ends the timer, hides the camera and arms the grab')
    r.step('grab', 'shot_grab'); expect(len(files(m)) == 1 and r.toasts() == ['Screenshot saved'], 'and takes its picture')
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = DEFS['SHOT_QUIT_LONG']; r = Run(m); r.step('tap', 'shot_start')
    for _ in range(5): r.step('tick', 'shot_tick')
    expect(m.props[(m.ind, 'visible')] == 1 and adds(r) == 1, 'after 5 ticks the 10 s countdown still runs (camera shown, no grab)')
    r.step('tap2', 'shot_start'); expect(asked(r) == [ASK, CANCEL], 'a tap then asks to cancel (Yes / No as before)')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    for _ in range(5): r.step('tick', 'shot_tick')
    expect(adds(r) == 2, 'the left button (4): 5 ticks and the grab is armed')
    for answer in (0, 0x10, 0x14, 1, 7):
        m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = answer; r = Run(m); r.step('tap', 'shot_start')
        expect(not r.has('timer_add', TICK, tick_ms) and not r.toasts() and m.props.get((m.ind, 'visible'), 0) == 0, f'result {answer:#x} (back key, closed, failed): no countdown')
    # the relabel timer: started just before the dialog opens, it relabels the buttons once the dialog is found and then ends
    RELABEL = PSYMS['shot_relabel']
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    expect(r.index('tap', 'timer_add', RELABEL, DEFS['SHOT_RELABEL_MS']) is not None and r.index('tap', 'timer_add', RELABEL, DEFS['SHOT_RELABEL_MS']) < r.index('tap', 'confirm', ASK, O['CONFIRM_KIND_WRAP']),
           'the relabel timer is added before the dialog opens')
    m = shot_machine(w=8, h=4); b_short, b_long = m.widget('confirminfo_dialog') and m.widget('btn_cancel'), m.widget('btn_enter')
    v = m.call(RELABEL)
    texts = [(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8']
    expect(v == 0 and texts == [(b_short, '5 s'), (b_long, '10 s')], 'with the dialog up the timer sets "5 s" on btn_cancel and "10 s" on btn_enter and ends')
    for loc in pod_i18n.ALL_TABLES:
        m = shot_machine(w=8, h=4); lang(m, loc); m.widget('confirminfo_dialog'); b1, b2 = m.widget('btn_cancel'), m.widget('btn_enter'); m.call(RELABEL)
        T = tr_of(loc)
        expect([(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8'] == [(b1, T('5 s')), (b2, T('10 s'))], f'{loc}: the buttons read {T("5 s")!r} / {T("10 s")!r}')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    vs = [m.call(RELABEL) for _ in range(DEFS['SHOT_RELABEL_TRIES'])]
    expect(vs[:-1] == [RET_REPEAT] * (DEFS['SHOT_RELABEL_TRIES'] - 1) and vs[-1] == 0 and not any(c[0] == 'widget_set_text_utf8' for c in m.calls),
           'no dialog: the timer repeats SHOT_RELABEL_TRIES times, then ends, touching nothing')
    m = shot_machine(w=8, h=4); m.timer_fail = True; r = Run(m); r.step('tap', 'shot_start')
    expect(asked(r) == [ASK] and r.has('timer_add', RELABEL, DEFS['SHOT_RELABEL_MS']) and r.toasts() == ['Screenshot failed'],
           'a refused relabel timer is ignored (the buttons stay Yes / No); the refused tick timer is the usual failure')

    # 13. Two steps (the back key does not close confirminfo_dialog on the device): a plain Yes / No first, then the delay dialog.
    def raw_asked(r): return [c[2] for c in r.log if c[1] == 'confirm']
    for answer in (0, 4, 0x14):   # No, the other button's code, anything else: nothing starts and the delay is not asked
        m = shot_machine(w=8, h=4); m.confirm_answers[ASK1] = answer; r = Run(m); r.step('tap', 'shot_start')
        expect(raw_asked(r) == [ASK1] and not r.has('timer_add') and not r.toasts() and not r.has('widget_set_visible'), f'step 1 answered {answer:#x}: nothing starts, no delay dialog, no relabel timer')
    m = shot_machine(w=8, h=4); r = Run(m); r.step('tap', 'shot_start')
    i1, it, i2 = r.index('tap', 'confirm', ASK1, O['CONFIRM_KIND_WRAP']), r.index('tap', 'timer_add', RELABEL, DEFS['SHOT_RELABEL_MS']), r.index('tap', 'confirm', ASK, O['CONFIRM_KIND_WRAP'])
    expect(raw_asked(r) == [ASK1, ASK] and None not in (i1, it, i2) and i1 < it < i2 and adds(r) == 1,
           'Yes at step 1: the delay dialog follows, its relabel timer added after step 1 and before it opens; its short button starts a countdown')
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK1] = 0; r = Run(m); r.step('tap', 'shot_start'); m.confirm_answers[ASK1] = 0xa; r.step('tap', 'shot_start')
    expect(raw_asked(r) == [ASK1, ASK1, ASK] and r.has('timer_add', TICK, tick_ms), 'after a No the next tap asks from step 1 again')
    m = shot_machine(w=8, h=4); m.confirm_answers[ASK] = 0; r = Run(m); r.step('tap', 'shot_start')
    expect(raw_asked(r) == [ASK1, ASK] and not r.has('timer_add', TICK, tick_ms) and not r.toasts(), 'step 2 answered with any other code: no shot')
    m = shot_machine(w=8, h=4); m.present.add(KILL); r = Run(m); r.step('tap', 'shot_start')
    expect(not raw_asked(r), 'kill switch present: neither dialog opens')

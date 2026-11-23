"""Battery Percentage (patch/battery.c, docs/modules/battery.md "The percentage"): the one hook at show_sysbar_face's call of get_battery_capacity (0x5450f8), run against the
mocked stock function; the Settings switch; the hidden number labels and their backdrops (status bar, pull-down, lock screen) inside the battery body."""
import os, struct
import paths
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'battery.h'), strings=True)
FILE, GAUGE, KILL = DEFS['BP_FILE'], DEFS['BP_GAUGE'], '/mnt/mmc/m1plus-off'
LABEL, LABEL_DD, LABEL_LK = DEFS['BP_LABEL'], DEFS['BP_LABEL_DD'], DEFS['BP_LABEL_LK']
BG, BG_DD, BG_LK = DEFS['BP_BG'], DEFS['BP_BG_DD'], DEFS['BP_BG_LK']
LEVEL, LEVEL_DD, LEVEL_LK = DEFS['BP_LEVEL'], DEFS['BP_LEVEL_DD'], DEFS['BP_LEVEL_LK']
BOLT, BOLT_DD, BOLT_LK = DEFS['BP_BOLT'], DEFS['BP_BOLT_DD'], DEFS['BP_BOLT_LK']
BOLT_S, BOLT_S_DD, BOLT_S_LK = DEFS['BP_BOLT_S'], DEFS['BP_BOLT_S_DD'], DEFS['BP_BOLT_S_LK']
W, W_CHG = int(DEFS['BP_W']), int(DEFS['BP_W_CHG'])
INK, INK_CHG = DEFS['BP_INK'], DEFS['BP_INK_CHG']
STOCK_CAP = 40


class BM(Machine):
    COUNT = True   # the instruction count (icount) the cost tests read


def machine(setting=b'1\n', gauge=b'87\n', labels=True, cap=STOCK_CAP):
    """A machine with the status bar's label and the pull-down's twin and their backdrops, the setting file, the gauge file and stock's capacity."""
    m = BM()
    m.mem_geometry = True
    m.stock_cap = cap
    if setting is not None: m.fs[FILE] = setting
    if gauge is not None: m.fs[GAUGE] = gauge
    if labels:
        for name in (LABEL, BG, LABEL_DD, BG_DD): m.widget(name)
    for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG'): m.setword(pod.DATA[k][0], 0)   # on battery (the demo's data starts with its own values)
    bar = m.alloc(0x80); m.setword(pod.DATA['SYSTEM_BAR'][0], bar)
    return m


def tick(m):
    return m.call(PSYMS['bp_capacity'], count=200000)


def power(m): return m.s32(pod.DATA['POWER_CAPACITY'][0])


def texts(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8']


def vis_calls(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_visible']


def pair_vis(m, *names):
    """The widget_set_visible calls in the order bp_label makes them: for each name its backdrop, then its label, all with `v`."""
    return [(m.widgets[n], v) for n, v in names]


def run(ctx):
    expect = ctx.expect
    stock_demo = stock_demo_bytes()
    built = built_demo_bytes()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    P = pod_pages

    # 1. The hook: one call-site word, everything around it stock's.
    site = pod.BATTERY_SITE
    expect(site == 0x5450f8 and w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['bp_capacity'],
           'the build replaced stock\'s `jalr t9` (get_battery_capacity) at 0x5450f8 by `jal bp_capacity`')
    expect(all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old, _ in pod.BATTERY_PINS),
           'every pinned word (show_sysbar_face, get_battery_capacity, the widget_t fields) is stock\'s in the stock demo and unchanged in the build, but the site')
    expect(w(built, 0x5450fc) == 0 and w(built, 0x5450f0) == 0x8fbc0010 and w(built, 0x545104) == 0x8fbc0010, 'the delay slot is still a nop and $gp is still reloaded from the stack after the call')
    expect(MANIFEST['hook_battery'] == {'addr': site, 'target': PSYMS['bp_capacity']}, 'the manifest records the hook')
    expect(pod.DATA['POWER_CAPACITY'][0] == 0xa059ec and pod.FUNCTIONS['get_battery_capacity'][2] == 0x4e6dd8, 'power_capacity and get_battery_capacity are the pinned addresses')
    expect(DEFS['BP_FILE'] == '/mnt/data/m1plus/battery-percentage' and DEFS['BP_GAUGE'] == '/sys/class/power_supply/battery/capacity'
           and (BG, BG_DD, BG_LK) == ('pod_pct_bg', 'pod_pct_bg_dd', 'pod_pct_bg_lk'), 'the two files and the backdrops\' names')

    # 2. Off (the default): stock's value, no label touched, no gauge read.
    for setting in (None, b'0\n', b'x', b''):
        m = machine(setting=setting)
        v = tick(m)
        expect(v == STOCK_CAP and power(m) == STOCK_CAP and texts(m) == [] and vis_calls(m) == []
               and ('open', GAUGE, 0) not in m.calls and not any(c[0] == 'widget_lookup' for c in m.calls),
               f'setting {setting!r}: stock\'s capacity ({STOCK_CAP}) returned and left in power_capacity, no label touched, no lookup, the gauge not read')
    m = machine(setting=None); tick(m); m.calls = []; tick(m)
    expect(m.names() == ['get_battery_capacity', 'access'] and m.icount < 400, f'off, steady state: stock\'s function and the kill switch test only ({m.names()}, {m.icount} instructions)')

    # 3. On with a valid gauge: the real percentage, in power_capacity and the return value; the label shows the bare number "N" over its shown backdrop.
    for text, pct in ((b'87\n', 87), (b'87', 87), (b'5\n', 5), (b'6\n', 6), (b'10\n', 10), (b'99\n', 99), (b'100\n', 100), (b'007\n', 7)):
        m = machine(gauge=text)
        v = tick(m)
        want = f'{pct}'
        stored = 0 if pct <= DEFS['BP_LOW'] else pct   # on battery, at most BP_LOW: 0, stock's red bar_lowpower
        expect(v == stored and power(m) == stored and [t for _, t in texts(m)] == [want, want] and vis_calls(m) == pair_vis(m, (BG, 1), (LABEL, 1), (BG_DD, 1), (LABEL_DD, 1)),
               f'on, gauge {text!r}: {stored} returned and stored, "{want}" (no % sign) shown with its backdrop in the bar\'s label and the pull-down\'s ({texts(m)})')
    m = machine(gauge=b'87\n'); tick(m)
    expect(('open', GAUGE, 0) in m.calls and ('access', KILL) in m.calls and m.calls.index(('access', KILL)) > m.calls.index(('get_battery_capacity',)),
           'stock\'s function runs first, then the kill switch is tested, then the gauge read')
    # charging: stock's animation (a +10 counter in power_capacity) is replaced by the gauge's value on every tick, the picture logic is not touched
    m = machine(gauge=b'63\n', cap=70); tick(m)
    expect(power(m) == 63, 'charging (stock leaves its animation value): the real percentage is stored')
    # low battery: 5% or less on battery, or stock's own bucket 0, is stored as 0 (red); a charging picture keeps the real value
    ext, usb, flag, dac = (pod.DATA[k][0] for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG'))
    for text, cap, want in ((b'6\n', 40, 6), (b'5\n', 40, 0), (b'1\n', 40, 0), (b'30\n', 0, 0), (b'30\n', 40, 30)):
        m = machine(gauge=text, cap=cap); v = tick(m)
        expect(v == want and power(m) == want, f'on battery, gauge {text!r}, stock bucket {cap}: {want} stored ({power(m)})')
    for text, cap, want in ((b'3\n', 40, 3), (b'1\n', 0, 1), (b'30\n', 0, 30)):
        m = machine(gauge=text, cap=cap); m.setword(ext, 1)   # external power, USB state not 2: stock draws the charging picture
        v = tick(m)
        expect(v == want and power(m) == want, f'charging (stock draws bar_charge), gauge {text!r}, stock bucket {cap}: the real value {want} stored ({power(m)})')
    m = machine(gauge=b'3\n'); m.setword(ext, 1); m.setword(usb, 2); m.u.mem_write(flag, b'\x01')
    expect(tick(m) == 0 and power(m) == 0, 'external power but stock\'s test falls through to the low / normal picture: 3% is stored as 0')
    m = machine(gauge=b'3\n'); m.setword(ext, 1); m.setword(usb, 2); m.u.mem_write(flag, b'\x01'); m.setword(dac, 1)
    expect(tick(m) == 3 and power(m) == 3, 'external power with the DAC charge flag set: the charging picture, the real value')

    # a zero gauge (issue 19): believed only when the battery voltage is below stock's empty level, else unreadable (power_capacity is no witness: stock's charging animation wraps to 0)
    VOLT, EMPTY = DEFS['BP_VOLT'], DEFS['BP_EMPTY_UV']
    expect(VOLT == '/sys/class/power_supply/battery/voltage_now' and EMPTY == 0x35f099, 'the voltage file and stock\'s empty level (0x35f099 µV)')
    for volt, charging, cap, shown in ((b'3400000\n', 0, 0, True), (str(EMPTY - 1).encode(), 0, 40, True), (str(EMPTY).encode() + b'\n', 0, 0, False),
                                       (b'4100000\n', 0, 0, False), (b'4100000\n', 1, 0, False), (b'4100000\n', 1, 70, False),
                                       (None, 0, 0, False), (b'', 0, 0, False), (b'abc\n', 0, 0, False), (b'3400000x\n', 0, 0, False), (b'12345678\n', 0, 0, False)):
        m = machine(gauge=b'0\n', cap=cap)
        if volt is not None: m.fs[VOLT] = volt
        if charging: m.setword(ext, 1)
        v = tick(m)
        if shown:
            expect(v == 0 and power(m) == 0 and [t for _, t in texts(m)] == ['0', '0'], f'gauge 0, voltage {volt!r}: 0 stored, "0" shown ({texts(m)})')
        else:
            expect(v == cap and power(m) == cap and texts(m) == [], f'gauge 0, voltage {volt!r}, charging {charging}, stock {cap}: stock\'s value, no label ({texts(m)})')
    m = machine(gauge=b'87\n'); m.fs[VOLT] = b'3400000\n'; tick(m)
    expect(('open', VOLT, 0) not in m.calls, 'a non-zero gauge never reads the voltage')

    # 4. On, but no valid gauge: stock's value; the label hidden (and not shown before: nothing to hide)
    for text in (None, b'', b'0\n', b'00\n',b'\n', b'abc', b'101\n', b'-5\n', b'+5\n', b'12x\n', b'1234\n', b' 50\n', b'5 0\n', b'50\n50\n', b'1.5\n', b'0x10\n'):
        m = machine(gauge=text)
        v = tick(m)
        expect(v == STOCK_CAP and power(m) == STOCK_CAP and texts(m) == [] and vis_calls(m) == [], f'on, gauge {text!r}: stock\'s capacity, no label shown')
    m = machine(gauge=b'87\n'); tick(m)
    m.fs[GAUGE] = b'garbage'; m.calls = []
    v = tick(m)
    expect(v == STOCK_CAP and power(m) == STOCK_CAP and vis_calls(m) == pair_vis(m, (BG, 0), (LABEL, 0), (BG_DD, 0), (LABEL_DD, 0))
           and not any(c[0] in ('widget_set_sensitive', 'widget_resize') for c in m.calls),
           'the gauge goes bad after a good reading: stock\'s value again, both labels and their backdrops hidden')
    m.calls = []; tick(m)
    expect(not any(c[0] == 'widget_lookup' for c in m.calls), 'and once hidden nothing is looked up again')
    # kill switch
    m = machine(gauge=b'87\n'); tick(m)
    m.present.add(KILL); m.calls = []
    v = tick(m)
    expect(v == STOCK_CAP and power(m) == STOCK_CAP and len(vis_calls(m)) == 4 and not any(a for _, a in vis_calls(m)) and ('open', GAUGE, 0) not in m.calls,
           '/mnt/mmc/m1plus-off: stock\'s value, the labels and backdrops hidden, the gauge not read')
    m = machine(gauge=b'87\n'); m.present.add(KILL)
    expect(tick(m) == STOCK_CAP and vis_calls(m) == [] and ('open', FILE, 0) not in m.calls, 'the kill switch from the start: stock, nothing touched, the setting not even read')
    # no label widgets (an asset from another build): the value is still the real one, nothing else happens
    m = machine(gauge=b'87\n', labels=False)
    expect(tick(m) == 87 and power(m) == 87 and texts(m) == [], 'no label in the window tree: the percentage still fills the battery, nothing is shown')
    m = machine(gauge=b'87\n'); m.setword(pod.DATA['SYSTEM_BAR'][0], 0)
    expect(tick(m) == 87 and [t for _, t in texts(m)] == ['87'], 'no status bar window: the pull-down\'s label is still set')
    # the setting is cached: a file edited behind the payload's back is read after a restart, a switch tap applies at once
    m = machine(setting=b'1\n', gauge=b'87\n'); tick(m)
    m.fs[FILE] = b'0\n'; m.calls = []
    expect(tick(m) == 87 and ('open', FILE, 0) not in m.calls, 'the setting is read once, at the first tick')

    # 4b. The lock screen's label (pod_pct_lk): the same tick sets it, in its fixed box; bp_lock sets it at the page's init
    keep = m   # section 5 goes on with the machine above

    def lock_machine(**kw):
        m = machine(**kw); h = m.widget(LABEL_LK); m.widget(BG_LK)
        return m, h
    for text in (b'5\n', b'87\n', b'100\n'):
        m, lk = lock_machine(gauge=text); tick(m)
        expect((lk, text.decode().strip()) in texts(m) and (lk, 1) in vis_calls(m) and (m.widgets[BG_LK], 1) in vis_calls(m)
               and not any(c[0] in ('widget_resize', 'widget_set_need_relayout_children') for c in m.calls),
               f'gauge {text!r}: the tick shows the bare number and the backdrop in the lock screen\'s label too, no resize or relayout')
    m, lk = lock_machine(gauge=b'87\n'); tick(m)
    m.fs[GAUGE] = b'garbage'; m.calls = []; tick(m)
    expect((lk, 0) in vis_calls(m) and (m.widgets[BG_LK], 0) in vis_calls(m), 'the gauge goes bad: the lock screen\'s label and backdrop are hidden with the others')
    win = 0x33000000
    m, lk = lock_machine(gauge=b'42\n'); m.call(PSYMS['bp_lock'], a0=win, count=200000)
    expect(texts(m) == [(lk, '42')] and vis_calls(m) == [(m.widgets[BG_LK], 1), (lk, 1)] and ('widget_lookup', LABEL_LK) in m.calls and not any(c[0] == 'widget_resize' for c in m.calls)
           and power(m) != 42, 'bp_lock (the lock screen\'s init): the gauge\'s number in the page\'s label at once; power_capacity is the tick\'s business')
    m.fs[GAUGE] = b'garbage'; m.calls = []; tick(m)
    expect((lk, 0) in vis_calls(m), 'a label bp_lock showed is hidden by the next tick when the gauge is bad')
    for kw, why in ((dict(setting=b'0\n'), 'the setting off'), (dict(setting=None), 'no setting file'), (dict(gauge=b'x'), 'a bad gauge'), (dict(gauge=None), 'no gauge')):
        m, lk = lock_machine(**kw); m.call(PSYMS['bp_lock'], a0=win, count=200000)
        expect(texts(m) == [] and vis_calls(m) == [] and not any(c[0] == 'widget_lookup' for c in m.calls), f'bp_lock with {why}: nothing looked up, the label stays hidden as the asset has it')
    m = machine(gauge=b'42\n'); m.call(PSYMS['bp_lock'], a0=win, count=200000)
    expect(texts(m) == [] and vis_calls(m) == [], 'bp_lock without the label in the page: nothing shown')
    # The charging look: while stock's faces show the charging picture (external power, not the USB DAC's no-charge case, not full) the green level with the capacity's
    # value, and a bolt: the middle one without the number, the small one right of a number of one or two digits (its label BP_W_CHG wide then).
    D = lambda k: pod.DATA[k][0]
    def chg_machine(ext=1, usb=0, flag=0, dac=0, pmu=1, **kw):
        m = machine(**kw)
        for n in (LEVEL, BOLT, BOLT_S): m.widget(n)
        if LABEL in m.widgets: m.setword(m.widgets[LABEL] + 8, W); m.setword(m.widgets[LABEL] + 12, 15)
        m.setword(D('POWER_EXT'), ext); m.setword(D('POWER_USBSTATE'), usb); m.u.mem_write(D('POWER_FLAG'), bytes([flag])); m.setword(D('USBDAC_CHARGEFLAG'), dac); m.setword(D('PMUCHARGE_STATUS'), pmu)
        return m
    def look(m):
        """(level shown, its value, middle bolt, small bolt, the label's width) after the calls so far; None for a widget never touched."""
        last = lambda n: next((v for h, v in reversed(vis_calls(m)) if h == m.widgets[n]), None)
        val = next((c[3] for c in reversed(m.calls) if c[0] == 'widget_set_prop_int' and c[1] == m.widgets[LEVEL] and c[2] == 'value'), None)
        return last(LEVEL), val, last(BOLT), last(BOLT_S), m.s32(m.widgets[LABEL] + 8)
    def ink(m): return [c for h, k, c in getattr(m, 'styled', []) if h == m.widgets[LABEL] and k == 'normal:text_color']
    def bg_shown(m): return next((v for h, v in reversed(vis_calls(m)) if h == m.widgets[BG]), None)
    for kw, want, why in ((dict(), (1, 87, 0, 1, W_CHG), 'charging at 87: green level 87, the small bolt, the narrow label'),
                          (dict(gauge=b'5\n'), (1, 5, 0, 1, W_CHG), 'charging at 5: the same (and not the low picture\'s 0)'),
                          (dict(gauge=b'100\n'), (1, 100, 0, 0, W), 'charging at 100: green level, no bolt (no room), the full label'),
                          (dict(usb=2, flag=1, dac=1), (1, 87, 0, 1, W_CHG), 'charging as a USB DAC'),
                          (dict(setting=None), (1, STOCK_CAP, 1, 0, W), 'charging with the setting off: green level at stock\'s capacity, the middle bolt'),
                          (dict(gauge=b'x'), (1, STOCK_CAP, 1, 0, W), 'charging with a bad gauge: the same'),
                          (dict(pmu=2), (0, None, 0, 0, W), 'full (stock shows bar_power): white level, no bolt'),
                          (dict(ext=0), (0, None, 0, 0, W), 'on battery'), (dict(usb=2, flag=1, dac=0), (0, None, 0, 0, W), 'a USB DAC that does not charge')):
        m = chg_machine(**kw); tick(m)
        expect(look(m) == want and not any(c[0] == 'widget_set_sensitive' for c in m.calls), f'{why} ({look(m)})')
    m = chg_machine(); tick(m)
    expect(ink(m) == [INK_CHG] and bg_shown(m) == 0, f'charging with the number: white digits, the lighter backdrop hidden ({ink(m)}, {bg_shown(m)})')
    m2 = chg_machine(ext=0); tick(m2); tick(m2)
    expect(ink(m2) == [] and bg_shown(m2) == 1, 'on battery: the label\'s colour is never set (the asset\'s black), the lighter backdrop shown')
    m.calls = []; tick(m)
    expect(look(m) == (1, 87, 0, 1, W_CHG) and not any(c[0] == 'widget_resize' for c in m.calls), 'the next charging tick keeps the look and does not resize the label again')
    m.setword(D('POWER_EXT'), 0); m.calls = []; tick(m)
    expect(look(m) == (0, None, 0, 0, W) and [t for _, t in texts(m)][:1] == ['87'] and ink(m)[-1] == INK and bg_shown(m) == 1, 'unplugged: the next tick hides the green level and the bolt, the label is full width again, the number stays')
    m = chg_machine(setting=None); tick(m); m.setword(D('POWER_EXT'), 0); m.calls = []; tick(m)
    expect(look(m)[:4] == (0, None, 0, 0), 'unplugged with the setting off: the next tick hides the green level and the bolt')
    m.calls = []; tick(m)
    expect(m.names() == ['get_battery_capacity', 'access'], f'and the tick after is stock\'s function and the kill switch test only again ({m.names()})')
    m = chg_machine(setting=None); tick(m); m.present.add(KILL); m.calls = []; tick(m)
    expect(look(m)[:4] == (0, None, 0, 0), 'the kill switch while charging: the green level and the bolt are hidden')
    m = chg_machine(setting=None); m.present.add(KILL); tick(m)
    expect(vis_calls(m) == [] and not any(c[0] == 'widget_lookup' for c in m.calls), 'the kill switch from the start: charging touches nothing')
    # issue 19: unplugging (or reaching full) while the label is hidden (setting off, bad gauge or kill switch) must still reset its white charging ink to black when it next shows on battery
    m = chg_machine(gauge=b'100\n'); tick(m)   # charging at 100: pod_pct turns white
    m.call(PSYMS['battpct_toggle'], count=4000000); tick(m)   # setting off while still charging
    m.setword(D('POWER_EXT'), 0); tick(m)   # unplugged while setting is off
    m.call(PSYMS['battpct_toggle'], count=4000000); m.calls = []; m.styled = []; tick(m)   # back on, on battery at 100
    expect(ink(m) == [INK] and bg_shown(m) == 1 and look(m)[4] == W, f'unplugged while setting off, then turned back on: black digits restored ({ink(m)}, {look(m)})')
    m.styled = []; tick(m)
    expect(ink(m) == [], f'and once black again the next tick does not restyle ({ink(m)})')
    m = chg_machine(gauge=b'87\n'); tick(m)   # narrow white label while charging
    m.fs[GAUGE] = b'garbage'; tick(m)   # bad gauge hides it
    m.setword(D('PMUCHARGE_STATUS'), 2); tick(m)   # charging finishes while hidden
    m.fs[GAUGE] = b'100\n'; m.styled = []; tick(m)
    expect(ink(m) == [INK] and look(m)[4] == W, f'full while gauge bad, then readable: black digits and full width restored ({ink(m)}, {look(m)})')
    for sym, names in (('bp_lock', (LABEL_LK, LEVEL_LK, BOLT_LK, BOLT_S_LK)), ('bp_pulldown', (LABEL_DD, LEVEL_DD, BOLT_DD, BOLT_S_DD))):
        for setting, want in ((None, [1, 1, 0]), (b'1\n', [1, 0, 1])):
            m = chg_machine(setting=setting)
            for n in names: m.widget(n)
            m.call(PSYMS[sym], a0=win, count=200000)
            got = [next((v for h, v in reversed(vis_calls(m)) if h == m.widgets[n]), None) for n in names[1:]]
            expect(got == want, f'{sym} while charging, setting {setting!r}: the page\'s green level and its bolt are shown at its init ({got})')
            if setting:
                m.styled = []
                m.call(PSYMS[sym], a0=win, count=200000)   # reopened while still charging: a fresh widget starts black and must still turn white
                expect([c for h, k, c in getattr(m, 'styled', []) if h == m.widgets[names[0]] and k == 'normal:text_color'] == [INK_CHG],
                       f'{sym} reopened while still charging: white digits set again on the fresh label')
    m = keep

    # 5. The Settings switch
    expect(m.call(PSYMS['battpct_setting'], count=2000000) == 0, 'battpct_setting reads the file: 0 now')
    for saved, on in ((None, 0), (b'1\n', 1), (b'1', 1), (b'0\n', 0), (b'', 0), (b'x', 0), (b'1x', 0), (b'11', 0), (b'\n1', 0)):
        m = machine(setting=saved)
        expect(m.call(PSYMS['battpct_setting'], count=2000000) == on, f'saved {saved!r}: the setting reads {on}')
    m = machine(setting=None, gauge=b'87\n')
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 1 and m.fs[FILE] == b'1\n' and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls,
           'the first toggle writes "1" atomically (a temp file, fsync, rename) and turns it on')
    expect(tick(m) == 87 and [t for _, t in texts(m)] == ['87', '87'], 'the next tick shows the percentage at once (the cache follows the switch)')
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 0 and m.fs[FILE] == b'0\n', 'and off again')
    m.calls = []
    expect(tick(m) == STOCK_CAP and len(vis_calls(m)) == 4 and not any(a for _, a in vis_calls(m)), 'the next tick is stock\'s again and hides the labels and backdrops')
    m = machine(setting=b'1\n', gauge=b'87\n'); m.fail.add(('write', FILE + '.tmp'))
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 0xffffffff and m.fs[FILE] == b'1\n' and FILE + '.tmp' not in m.fs and tick(m) == 87,
           'a failed save: -1, the file and the behaviour are unchanged')

    # 6. The row: Settings > Battery > Battery Percentage (a switch, off by default)
    H = P.BATTERY_PAGE
    lay = lambda pg: [type(x).__name__ + (':' + x.label if isinstance(x, P.Row) else ':' + x.text if hasattr(x, 'text') else '') for x in pg.layout]
    layout = lay(H)
    bp_i = next(i for i, r in enumerate(H.rows) if r.action == P.ACT_BATTPCT)
    expect(H.rows[bp_i].label == 'Battery Percentage' and P.ACT_BATTPCT == 36 and P.ACT_BATTPCT in P.SWITCH_ACTIONS and P.row_kind(H.rows[bp_i]) == 'switch'
           and layout == ['Row:Battery Percentage', 'Note:The exact charge beside the battery icon', 'Row:Charge Limit', 'Note:Applies while the player is on', 'Row:Battery History'] and bp_i == 0,
           f'the Battery page lists the Battery Percentage switch row and its note, then Charge Limit and the Battery History row (its page: test/pod/batthist.py) ({layout})')
    expect(not any(r.action == P.ACT_BATTPCT for r in P.HOMESET_PAGE.rows) and 'Hdr:Status Bar' not in lay(P.HOMESET_PAGE) and lay(P.HOMESET_PAGE)[-2:] == ['Row:Regenerate Daily Mix', 'Note:A new mix the next time Home opens'],
           'the Home Screen page has no Status Bar header or Battery Percentage row; Regenerate Daily Mix stays last')
    S = P.SETTINGS_PAGE
    hs_i = next(i for i, r in enumerate(S.rows) if r.action == P.ACT_PAGE and r.arg == P.BATTERY_PAGE_INDEX)
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']; on_row = PSYMS['on_row']

    def open_home(saved=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))] + [f'pod_switch{bp_i}'])}
        if saved is not None: m.fs[FILE] = saved
        m.call(on_row, a0=rows_s + 12 * hs_i, count=3000000)
        return m

    def images(m): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{bp_i}']]

    m = open_home()
    expect(('window_open', H.key) in m.calls and images(m) == ['sset_off'] and FILE not in m.fs, 'the page opens with nothing saved: the switch is off and nothing is written (the default)')
    for data, on in ((b'1\n', 1), (b'0\n', 0), (b'', 0)):
        expect(images(open_home(data)) == [('sset_on' if on else 'sset_off')], f'saved {data!r}: the switch opens {"on" if on else "off"}')
    m = open_home()
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'1\n' and images(m)[-1] == 'sset_on', 'a tap on the row turns it on (saved, the switch on)')
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'0\n' and images(m)[-1] == 'sset_off', 'and off again')
    m = open_home(b'1\n'); m.fail.add(('write', FILE + '.tmp'))
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'1\n' and images(m) == [], 'a failed save changes neither the file nor the switch')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Battery Percentage', 'The exact charge beside the battery icon')), f'the row and note have a text in {loc}')

    # 7. The assets: the hidden number and its backdrops inside the battery of the system bar and the pull-down
    import awtk_ui, statusbar, battery_art
    from PIL import Image
    expect((W, W_CHG) == (battery_art.STATUS.body[2], battery_art.PCT_W_CHG) and battery_art.BOLT_SMALL[0] < W_CHG < battery_art.BOLT_SMALL[0] + battery_art.BOLT_SMALL[2], 'BP_W and BP_W_CHG are the art\'s: the body, and a box reaching into the small bolt\'s (the digits\' ink sits left of its centre)')
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    stock_bar = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    bar = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    bars = [('system_bar', bar, '')]
    dd = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), 'rb').read())
    bars.append(('pull-down', dd.find('view_sysbar'), '_dd'))
    body = battery_art.STATUS.body
    for what, root, sfx in bars:
        group, img, pg = root.find('view_bar_right'), root.find('img_battery'), root.find('pgbar_battery')
        owner = next(w for w in root.walk() if pg in w.children)
        names = [c.name for c in owner.children if c in owner.children]
        seq = ['pod_bat_bg' + sfx, 'pod_pct_bg' + sfx, 'pgbar_battery', LEVEL + sfx, 'img_battery', BOLT + sfx, BOLT_S + sfx, 'pod_pct' + sfx]
        order = [c.name for c in owner.children if c.name in seq]
        bg, bgp, lab = root.find('pod_bat_bg' + sfx), root.find('pod_pct_bg' + sfx), root.find('pod_pct' + sfx)
        expect(order == seq and lab not in group.children and root.find(LABEL + sfx) is lab and all(sum(c.name == n for c in root.walk()) == 1 for n in seq),
               f'{what}: the battery\'s parent paints pod_bat_bg, pod_pct_bg, the level, the green level, the picture, the two bolts, then the number, once each, none in the right group ({names})')
        lvl, white, bm, bs, pic = root.find(LEVEL + sfx), root.find('pgbar_battery'), root.find(BOLT + sfx), root.find(BOLT_S + sfx), root.find('img_battery')
        same = [(k, v) for k, v in lvl.props if k not in ('name', 'visible', 'sensitive') and 'fg_color' not in k] == [(k, v) for k, v in white.props if k not in ('name', 'visible', 'sensitive') and 'fg_color' not in k]
        expect(lvl.type == 'progress_bar' and (lvl.x, lvl.y, lvl.w, lvl.h) == (white.x, white.y, white.w, white.h) and same and lvl.get('visible') == 'false' and lvl.get('sensitive') == 'false'
               and all(lvl.get(f'style:{st}:fg_color') == statusbar.CHG_GREEN == '#%02X%02X%02X' % battery_art.CHARGE for st in statusbar.STATES),
               f'{what}: {LEVEL + sfx} is stock\'s level bar again, hidden and insensitive, in the charging green')
        expect(all(b.type == 'image' and b.get('visible') == 'false' and b.get('sensitive') == 'false' and b.get('image') == f and (b.x - pic.x, b.y - pic.y, b.w, b.h) == box
                   and Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', f + '.png')).size == box[2:]
                   for b, f, box in ((bm, statusbar.CHG_IMAGE, battery_art.BOLT_MID), (bs, statusbar.CHG_S_IMAGE, battery_art.BOLT_SMALL)))
               and (statusbar.CHG_WIDGET, statusbar.CHG_S_WIDGET, statusbar.CHG_LEVEL) == (BOLT, BOLT_S, LEVEL),
               f'{what}: the two bolts are hidden, insensitive images of their pictures\' size over the body')
        expect(all((w.x, w.y, w.w, w.h) == (pg.x, pg.y, pg.w, pg.h) for w in (bg, bgp)) and bg.type == bgp.type == 'view'
               and bg.get('style:normal:bg_color') == battery_art.EMPTY and bgp.get('style:normal:bg_color') == battery_art.EMPTY_PCT
               and bg.get('visible') is None and bgp.get('visible') == 'false' and bg.get('sensitive') == bgp.get('sensitive') == 'false'
               and all(pg.get(f'style:{st}:bg_color') == '#00000000' for st in statusbar.STATES),
               f'{what}: the backdrops sit on the level\'s box, the empty grey shown and the lighter grey hidden, both insensitive, and the level itself is transparent')
        sty = {st: (lab.get(f'style:{st}:text_color'), lab.get(f'style:{st}:font_size'), lab.get(f'style:{st}:font_name'), lab.get(f'style:{st}:text_align_h'), lab.get(f'style:{st}:text_align_v')) for st in statusbar.STATES}
        expect(lab.type == 'label' and lab.get('visible') == 'false' and lab.get('sensitive') == 'false' and (lab.x, lab.y, lab.w, lab.h) == (img.x + body[0], img.y + body[1] + statusbar.PCT_DY, body[2], statusbar.PCT_PX)
               and all(v == (statusbar.PCT_RGB, str(statusbar.PCT_PX), statusbar.PCT_FACE, 'center', 'middle') for v in sty.values()) and statusbar.PCT_RGB == '#000000' and statusbar.PCT_FACE == 'lyrics',
               f'{what}: pod_pct{sfx} is a hidden, insensitive label over the battery body ({body[2]} px wide, PCT_PX high, PCT_DY below its top), black {statusbar.PCT_PX} px {statusbar.PCT_FACE} text, centred in every state')
    expect({n.name for n in stock_bar.walk()} == {n.name for n in bar.walk()} - {'pod_bat_bg', 'pod_pct_bg', 'pod_pct', LEVEL, BOLT, BOLT_S, 'pod_shot', 'pod_lo', 'pod_sync', 'pod_sleep', 'pod_eq'},
           'no stock widget is renamed or removed (the battery\'s three widgets and the other marks are the only additions)')
    # layout: the group is right-aligned from its right edge (4 px before the outline); the number is inside the battery, so it takes no room in the group. Every icon's ink must stay clear of the clock.
    from PIL import Image
    group, clock = bar.find('view_bar_right'), bar.find('bar_dclock')
    clock_px = int(clock.get('style:normal:font_size'))
    clock_end = max(clock.x + (clock.w + StbText(font, clock_px).layout(t)[1]) // 2 for t in ('12:59', '12:59 PM', '10:59 AM', '12:59 AM'))
    imgs = {'img_btclass': 'bar_bt', 'img_synclink': 'bar_synclink', 'img_wifi': 'bar_wifi0', 'pod_shot': 'pod_bar_shot'}
    ink_left = {n: Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', f'{f}.png')).convert('RGBA').getchannel('A').getbbox()[0] for n, f in imgs.items()}
    sizes = {c.name: c.w for c in group.children}
    edge = group.x + group.w
    expect(edge + statusbar.BAT_GAP == bar.find('img_battery').x, 'the group ends BAT_GAP px before the battery outline')
    # spacing by shape: every mark's ink ends at its box's right edge; Wi-Fi and the camera start at the left edge (RGAP from the mark before), the sync arrows 1 px and the moon 3 px in
    for n, f, pad in (('pod_sync', 'pod_bar_sync', 1), ('pod_sleep', 'pod_bar_sleep', 3), ('img_wifi', 'bar_wifi0', 0), ('img_wifi', 'bar_wifi4', 0), ('pod_shot', 'pod_bar_shot', 0)):
        im_ = Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', f'{f}.png')).convert('RGBA'); bb_ = im_.getchannel('A').getbbox()
        expect(im_.width == sizes[n] and (bb_[0], bb_[2]) == (pad, im_.width), f'{f} is as wide as {n}, its ink from {pad} px to the right edge ({im_.size}, {bb_}, box {sizes[n]})')
    # the number's ink: AWTK puts the baseline int(ascender * scale) below the line's top; the digits' ink is centred in the body within half a pixel
    bold = Ttf(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts', statusbar.PCT_FACE + '.ttf')); lab_ = bar.find('pod_pct'); img_ = bar.find('img_battery')
    base_ = lab_.y + (lab_.h - statusbar.PCT_PX) // 2 + int(bold.asc * statusbar.PCT_PX / bold.units); top_ = base_ - max(bold.ink(c)[1] for c in '0123456789') * statusbar.PCT_PX / bold.units
    mid_ = img_.y + battery_art.STATUS.body[1] + battery_art.STATUS.body[3] / 2
    expect(abs((top_ + base_) / 2 - mid_) <= 0.5 and StbText(bold, statusbar.PCT_PX).layout('100')[1] <= battery_art.STATUS.fill[2],
           f'the digits\' ink ({top_:.2f} .. {base_}) is centred on the body ({mid_}) within half a pixel, and "100" fits inside the rim')

    def spans(visible):
        out, e = {}, edge
        for n in reversed([c.name for c in group.children]):
            if n in visible: out[n] = (e - sizes[n], e); e -= sizes[n] + statusbar.RGAP
        return out

    expect('pod_pct' not in sizes, 'the number takes no part in the group\'s layout')
    s_ = spans(['img_btclass', 'img_synclink', 'img_wifi'])
    gaps = {n: s_[n][0] + ink_left[n] for n in s_}
    expect(all(g >= clock_end + 3 for g in gaps.values()), f'Bluetooth, SyncLink and Wi-Fi all lit: every icon\'s ink starts at least 3 px clear of the 12 h and 24 h clock ({gaps}, clock ends {clock_end})')
    s_ = spans(['img_btclass', 'img_wifi', 'pod_shot'])
    expect(s_['pod_shot'] == (edge - 16, edge) and all(s_[n][0] + ink_left[n] >= clock_end + 3 for n in ('img_btclass', 'img_wifi')),
           'with the Screenshot camera too (against the outline), Bluetooth and Wi-Fi lit, the ink is still at least 3 px clear of the clock')

    # 8. The lock screen: the status bar's gauge (pictures, size, fill, right edge, the fill under the picture) with the hidden number in it, clear of the date
    from awtk_text import awtk_width, worst_case_text
    lock = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/screensaver_page.bin'), 'rb').read())
    view, limg, lpg, lab, date = (lock.find(n) for n in ('view_timeinfo', 'img_battery', 'pgbar_battery', LABEL_LK, 'dclock_date'))
    simg, spg = bar.find('img_battery'), bar.find('pgbar_battery')
    xx = os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx')
    same = all(open(os.path.join(xx, a + '.png'), 'rb').read() == open(os.path.join(xx, b + '.png'), 'rb').read()
               for a, b in (('screens_battery', 'bar_power'), ('screens_charge', 'bar_charge'), ('screens_lowbattery', 'bar_lowpower')))
    expect(same and (limg.w, limg.h, lpg.w, lpg.h) == (simg.w, simg.h, spg.w, spg.h) and (lpg.x - limg.x, lpg.y - limg.y) == (spg.x - simg.x, spg.y - simg.y),
           'the lock screen\'s gauge is the status bar\'s: the same three pictures, size and fill box')
    kids = [c.name for c in view.children]
    order = [n for n in kids if n in ('pod_bat_bg_lk', 'pod_pct_bg_lk', 'pgbar_battery', LEVEL_LK, 'img_battery', BOLT_LK, BOLT_S_LK, LABEL_LK)]
    expect(order == ['pod_bat_bg_lk', 'pod_pct_bg_lk', 'pgbar_battery', LEVEL_LK, 'img_battery', BOLT_LK, BOLT_S_LK, LABEL_LK] and [c.name for c in bar.walk() if c.name in ('pgbar_battery', 'img_battery')] == ['pgbar_battery', 'img_battery'],
           'the backdrops and the fill are drawn under the picture on both (the rim stays whole), the bolts and the number over it')
    sty = {st: (lab.get(f'style:{st}:text_color'), lab.get(f'style:{st}:font_size'), lab.get(f'style:{st}:font_name'), lab.get(f'style:{st}:text_align_h'), lab.get(f'style:{st}:text_align_v')) for st in statusbar.STATES}
    expect(lab is not None and lab.type == 'label' and lab in view.children and lab.get('visible') == 'false' and lab.get('sensitive') == 'false' and sum(c.name == LABEL_LK for c in lock.walk()) == 1
           and all(v == (statusbar.PCT_RGB, str(statusbar.PCT_PX), statusbar.PCT_FACE, 'center', 'middle') for v in sty.values()), f'{LABEL_LK} is one hidden, insensitive label of the time block, the status bar label\'s text style')
    lbg = lock.find('pod_pct_bg_lk')
    expect((lab.x, lab.y, lab.w, lab.h) == (limg.x + body[0], limg.y + body[1] + statusbar.PCT_DY, body[2], statusbar.PCT_PX) and (lbg.x, lbg.y, lbg.w, lbg.h) == (lpg.x, lpg.y, lpg.w, lpg.h) and lbg.get('visible') == 'false',
           f'its box is over the gauge\'s body ({body[2]} px wide, PCT_PX high, PCT_DY below its top), its backdrop the fill box, hidden with it')
    date_px = int(date.get('style:normal:font_size'))
    date_w = awtk_width(font, worst_case_text(date.get('format'), font), date_px)
    expect(date.x + (date.w + date_w) // 2 + 4 <= limg.x, f'the widest date ({date_w} px, centred) ends at least 4 px before the gauge ({limg.x})')

    # 9. The backlight hooks: screen_action's two `jalr toolSetBackLight` (0x4e71cc on, 0x4e71fc off) become `jal bp_light_on` / `jal bp_light_off`
    stock_demo, built = stock_demo_bytes(), built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    for s_, name in ((pod.LIGHT_ON_SITE, 'bp_light_on'), (pod.LIGHT_OFF_SITE, 'bp_light_off')):
        expect(word(stock_demo, s_) == 0x0320f809 and word(built, s_) >> 26 == 3 and (word(built, s_) & 0x3ffffff) << 2 == PSYMS[name],
               f'the build replaced screen_action\'s `jalr t9` (toolSetBackLight) at {s_:#x} by `jal {name}`')
    expect((pod.LIGHT_ON_SITE, pod.LIGHT_OFF_SITE) == (0x4e71cc, 0x4e71fc) and all(word(stock_demo, a) == old and (a in (pod.LIGHT_ON_SITE, pod.LIGHT_OFF_SITE) or word(built, a) == old) for a, old, _ in pod.BACKLIGHT_PINS)
           and word(built, 0x4e71d0) == 0x24840001 and word(built, 0x4e7200) == 0, 'every pinned word of screen_action is stock\'s in the stock demo and unchanged in the build, but the two sites (delay slots intact)')
    expect(MANIFEST['hook_light_on'] == {'addr': pod.LIGHT_ON_SITE, 'target': PSYMS['bp_light_on']} and MANIFEST['hook_light_off'] == {'addr': pod.LIGHT_OFF_SITE, 'target': PSYMS['bp_light_off']}, 'the manifest records both hooks')

    def lm(kill=False):
        mm = machine(); mm.wm = mm.alloc(0x80)
        mm.handlers[pod.FUNCTIONS['window_manager_check_and_layout'][2]] = 'window_manager_check_and_layout'   # trapped and recorded here (the harness runs it for real)
        if kill: mm.present.add(KILL)
        return mm

    PAINT = ['access', 'show_sysbar_face', 'widget_invalidate_force', 'window_manager_check_and_layout', 'window_manager_paint', 'toolSetBackLight']
    m = lm(); m.call(PSYMS['bp_light_on'], 7, count=200000)
    expect(m.names() == ['toolSetBackLight'] and ('toolSetBackLight', 7) in m.calls, f'on without a prior off (lit already): only toolSetBackLight ({m.names()})')
    m.call(PSYMS['bp_light_off'], 0, count=200000)
    expect(m.names() == ['toolSetBackLight'] and ('toolSetBackLight', 0) in m.calls, f'off: only toolSetBackLight ({m.names()})')
    m.call(PSYMS['bp_light_on'], 5, count=200000)
    expect(m.names() == PAINT and ('toolSetBackLight', 5) in m.calls and ('show_sysbar_face', 0) in m.calls and ('widget_invalidate_force', m.wm) in m.calls and ('window_manager_check_and_layout', m.wm) in m.calls and ('window_manager_paint', m.wm) in m.calls,
           f'off then on: the bar refresh and the paint, then toolSetBackLight with the same argument ({m.names()})')
    m.call(PSYMS['bp_light_on'], 5, count=200000)
    expect(m.names() == ['toolSetBackLight'], f'a second on paints nothing ({m.names()})')
    # the screen off: the tick still sets stock's capacity (and runs the Charge Limit) but looks up and writes no label; the first lit tick shows the new number
    m = lm(); tick(m)
    m.call(PSYMS['bp_light_off'], 0, count=200000); m.screen(0)
    m.fs[GAUGE] = b'86\n'
    cap = tick(m)
    expect(cap == 86 and power(m) == 86 and not texts(m) and not vis_calls(m) and 'widget_lookup' not in m.names(), f'dark: capacity 86, no label work ({m.names()})')
    m.screen(1); tick(m)
    expect(texts(m) == [(m.widgets[LABEL], '86'), (m.widgets[LABEL_DD], '86')], f'lit by another path (no bp_light_on): the labels follow on the next tick ({texts(m)})')
    m.call(PSYMS['bp_light_off'], 0, count=200000); m.screen(0)
    m.call(PSYMS['bp_light_on'], 5, count=200000); m.fs[GAUGE] = b'85\n'
    tick(m)
    expect(texts(m) == [(m.widgets[LABEL], '85'), (m.widgets[LABEL_DD], '85')], f'after bp_light_on the tick (show_sysbar_face\'s, with the byte still 0) shows the labels ({texts(m)})')
    m = lm(kill=True); m.call(PSYMS['bp_light_off'], 0, count=200000); m.call(PSYMS['bp_light_on'], 5, count=200000)
    expect(m.names() == ['access', 'toolSetBackLight'] and ('toolSetBackLight', 5) in m.calls, f'with the kill switch present no paint ({m.names()})')

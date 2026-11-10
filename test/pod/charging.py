"""Charge Limit (patch/charging.c, docs/modules/charging.md): the controller bp_capacity runs on the status bar's tick (hold at the limit, release CHG_RESUME
lower, stock's USB DAC choice, unplug, kill switch, bad gauge, failed writes, the CHG_PERIOD rate), the saved limit, and Settings > System > Battery with its picker."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs
import awtk_ui

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'charging.h'), strings=True)
BDEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'battery.h'), strings=True)
FILE, SWITCH, GAUGE, BP_FILE, KILL = DEFS['CHG_FILE'], DEFS['CHG_SWITCH'], BDEFS['BP_GAUGE'], BDEFS['BP_FILE'], '/mnt/mmc/m1plus-off'
PERIOD = DEFS['CHG_PERIOD']


class CM(Machine):
    COUNT = True


def machine(limit=b'0\n', gauge=b'80\n', ext=1, switch=b'1\n', battpct=None):
    """The status bar's tick with a saved limit (b'0\\n' = 80 %), the gauge, external power (POWER_EXT) and the driver's switch file."""
    m = CM()
    m.stock_cap = 40
    if limit is not None: m.fs[FILE] = limit
    if gauge is not None: m.fs[GAUGE] = gauge
    if switch is not None: m.fs[SWITCH] = switch
    if battpct is not None: m.fs[BP_FILE] = battpct
    for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG'): m.setword(pod.DATA[k][0], 0)
    m.setword(pod.DATA['POWER_EXT'][0], ext)
    m.setword(pod.DATA['SYSTEM_BAR'][0], 0)
    return m


def tick(m, dt=PERIOD):
    """One status bar tick dt seconds after the last; the switch file then holds the last value written (a sysfs attribute, not an appended file)."""
    m.wall += dt
    m.calls = []
    m.call(PSYMS['bp_capacity'], count=400000)
    w = writes(m)
    if w and ('write', SWITCH) not in m.fail: m.fs[SWITCH] = w[-1]
    return w


def writes(m): return [c[2] for c in m.calls if c[0] == 'write' and c[1] == SWITCH]


def opened(m, p): return any(c[0] == 'open' and c[1] == p for c in m.calls)


def gauge(m, pct): m.fs[GAUGE] = f'{pct}\n'.encode()


def dac_off(m, on=True):
    """Stock's USB DAC mode with its charging choice off (show_sysbar_face's test, patch/battery.c): USB state 2, the flag byte 1, usbdac_chargeflag 0."""
    m.setword(pod.DATA['POWER_USBSTATE'][0], 2 if on else 0)
    m.u.mem_write(pod.DATA['POWER_FLAG'][0], b'\x01' if on else b'\x00')
    m.setword(pod.DATA['USBDAC_CHARGEFLAG'][0], 0)


def limit_tests(ctx):
    """The saved limit and the picker's save."""
    expect = ctx.expect
    expect(FILE == '/mnt/data/m1plus/battery-charge-limit' and SWITCH == '/sys/class/power_supply/battery/charger' and GAUGE == '/sys/class/power_supply/battery/capacity'
           and (DEFS['CHG_MIN'], DEFS['CHG_STEP'], DEFS['CHG_OFF'], DEFS['CHG_RESUME'], PERIOD) == (80, 5, 100, 5, 5), 'the files and the constants')
    for saved, want in ((None, 100), (b'0\n', 80), (b'1\n', 85), (b'2', 90), (b'3\n', 95), (b'4\n', 100), (b'9\n', 100), (b'x', 100), (b'', 100), (b'00', 100), (b'80\n', 100), (b'0\n\n', 100)):
        m = machine(limit=saved)
        expect(m.call(PSYMS['chg_limit'], count=200000) == want, f'saved {saved!r}: the limit is {want}')
    m = machine(limit=None)
    for lim, ch in ((80, b'0\n'), (95, b'3\n'), (100, b'4\n'), (85, b'1\n')):
        expect(m.call(PSYMS['chg_set'], a0=lim, count=4000000) == lim and m.fs[FILE] == ch and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls
               and m.call(PSYMS['chg_limit'], count=200000) == lim, f'chg_set({lim}) writes {ch!r} atomically and the limit follows')
    for bad in (79, 82, 101, 0, -5, 105):
        m.calls = []
        expect(m.call(PSYMS['chg_set'], a0=bad & 0xffffffff, count=4000000) == 0xffffffff and m.fs[FILE] == b'1\n' and not any(c[0] == 'open' for c in m.calls),
               f'chg_set({bad}): -1, nothing written')
    m = machine(limit=b'2\n'); m.fail.add(('write', FILE + '.tmp'))
    expect(m.call(PSYMS['chg_set'], a0=80, count=4000000) == 0xffffffff and m.fs[FILE] == b'2\n' and m.call(PSYMS['chg_limit'], count=200000) == 90,
           'a failed save: -1, the file and the limit unchanged')


def hold_tests(ctx):
    """Hold at the limit, release CHG_RESUME lower, the rate, stock enabling charging again."""
    expect = ctx.expect
    # no limit (the default): nothing beyond Battery Percentage's own steady state
    for saved in (None, b'4\n', b'x'):
        m = machine(limit=saved, gauge=b'100\n')
        tick(m)
        expect(writes(m) == [] and not opened(m, SWITCH) and not opened(m, GAUGE), f'limit file {saved!r}: no limit, the switch and the gauge untouched')
        tick(m)
        expect(m.names() == ['get_battery_capacity', 'access'] and m.icount < 400, f'and the steady state is stock\'s call and the kill switch test ({m.names()}, {m.icount} instructions)')
    # the cycle at 80 %
    m = machine(gauge=b'79\n')
    expect(tick(m) == [] and opened(m, GAUGE) and not opened(m, SWITCH), '79 % on external power: read the gauge, no write')
    gauge(m, 80)
    expect(tick(m) == [b'0\n'], 'the gauge reaches 80 %: "0" written (the hold)')
    for pct in (90, 79, 76):
        gauge(m, pct)
        expect(tick(m) == [] and opened(m, SWITCH), f'held at {pct} %: the switch is read (still "0"), nothing written')
    gauge(m, 75)
    expect(tick(m) == [b'1\n'], '75 %: "1" written (the release)')
    for pct in (76, 79):
        gauge(m, pct)
        expect(tick(m) == [] and not opened(m, SWITCH), f'released at {pct} %: below the limit, nothing written, the switch not read')
    gauge(m, 81)
    expect(tick(m) == [b'0\n'], 'over the limit again: held again')
    # stock writes "1" behind our back (the USB page's exit, the DAC toggle): the next check holds again
    m.fs[SWITCH] = b'1\n'
    expect(tick(m) == [b'0\n'], 'held, the switch reads "1": "0" written again')
    m.fs[SWITCH] = b'?'
    expect(tick(m) == [b'0\n'], 'held, the switch unreadable: "0" written again')
    del m.fs[SWITCH]
    expect(tick(m) == [], 'held, no switch file: nothing to write to (open fails)')
    # the rate: at most one check per CHG_PERIOD seconds; a clock that went back checks at once
    m = machine(gauge=b'70\n'); tick(m)
    for dt in (1, 1, 1, 1):
        tick(m, dt)
        expect(m.names() == ['get_battery_capacity', 'access'], f'within {PERIOD} s of the last check: no file read ({m.names()}; the mock does not log time())')
    tick(m, 1)
    expect(opened(m, GAUGE), f'{PERIOD} s after it: checked')
    gauge(m, 85)
    expect(tick(m, -3600) == [b'0\n'], 'the clock went back an hour: checked at once')
    # the limit's levels
    for saved, lim in ((b'1\n', 85), (b'2\n', 90), (b'3\n', 95)):
        m = machine(limit=saved, gauge=f'{lim - 1}\n'.encode())
        a = tick(m); gauge(m, lim); b = tick(m); gauge(m, lim - 4); c = tick(m); gauge(m, lim - 5); d = tick(m)
        expect((a, b, c, d) == ([], [b'0\n'], [], [b'1\n']), f'limit {lim}: no hold at {lim - 1}, hold at {lim}, still held at {lim - 4}, released at {lim - 5}')
    # Battery Percentage on: the gauge it read is used, not read twice
    m = machine(gauge=b'85\n', battpct=b'1\n')
    w = tick(m)
    expect(w == [b'0\n'] and sum(1 for c in m.calls if c[0] == 'open' and c[1] == GAUGE) == 1, 'with Battery Percentage on, one gauge read serves both')
    # a failed hold is tried again at the next check
    m = machine(gauge=b'85\n'); m.fail.add(('write', SWITCH))
    expect(tick(m) == [b'0\n'] and m.fs[SWITCH] == b'1\n', 'the hold\'s write fails: the switch keeps "1"')   # (the mock records the attempt)
    m.fail.clear()
    expect(tick(m) == [b'0\n'], 'and is written again at the next check (not held: the gauge decides again)')
    gauge(m, 70)
    expect(tick(m) == [b'1\n'], 'then released normally')


def release_tests(ctx):
    """Every way out releases only our own hold: no limit, kill switch, unplug, bad gauge, stock's DAC choice."""
    expect = ctx.expect

    def held(**kw):
        m = machine(gauge=b'85\n', **kw)
        assert tick(m) == [b'0\n']
        return m
    # unplugged
    m = held(); m.setword(pod.DATA['POWER_EXT'][0], 0)
    expect(tick(m) == [b'1\n'], 'unplugged while held: released')
    expect(tick(m) == [] and not opened(m, GAUGE) and not opened(m, SWITCH), 'on battery, not held: nothing read or written')
    m.setword(pod.DATA['POWER_EXT'][0], 1)
    expect(tick(m) == [b'0\n'], 'plugged in again at 85 %: held again at the next check')
    m = machine(gauge=b'95\n', ext=0)
    expect(tick(m) == [], 'on battery over the limit: no hold (nothing to stop)')
    # a bad gauge
    for bad in (b'', b'abc', b'101\n', None):
        m = held()
        if bad is None: del m.fs[GAUGE]
        else: m.fs[GAUGE] = bad
        expect(tick(m) == [b'1\n'], f'held, gauge {bad!r}: released')
        expect(tick(m) == [], 'and nothing more while it stays bad')
    # the kill switch: at once (within the period), and nothing read while not held
    m = held(); m.present.add(KILL)
    expect(tick(m, 1) == [b'1\n'], '/mnt/mmc/m1plus-off while held: released at the next tick, without waiting for the period')
    expect(tick(m) == [] and not opened(m, GAUGE) and not opened(m, FILE), 'and then nothing at all')
    m = machine(gauge=b'95\n'); m.present.add(KILL)
    expect(tick(m) == [] and not opened(m, FILE) and not opened(m, GAUGE), 'the kill switch from the start: the limit file not even read')
    # stock's USB DAC mode with charging off: stock owns the switch
    m = held(); dac_off(m)
    expect(tick(m) == [] and not opened(m, SWITCH), 'USB DAC with charging off: nothing written, the switch not read (stock wrote "0" itself)')
    m.fs[SWITCH] = b'1\n'; dac_off(m, False)   # the mode ends: stock's exit handler writes "1"
    expect(tick(m) == [b'0\n'], 'the mode ends at 85 %: a new hold of our own')
    gauge(m, 70); dac_off(m)
    expect(tick(m) == [], 'in DAC mode the hold was forgotten: no "1" written over the user\'s choice even at 70 %')
    m = held(); m.setword(pod.DATA['USBDAC_CHARGEFLAG'][0], 1); m.setword(pod.DATA['POWER_USBSTATE'][0], 2); m.u.mem_write(pod.DATA['POWER_FLAG'][0], b'\x01')
    m.fs[SWITCH] = b'1\n'
    expect(tick(m) == [b'0\n'], 'USB DAC with charging on: the limit applies (stock\'s "1" is held again)')
    # every release path while stock's DAC charging-off choice owns the switch: the hold forgotten, never "1" written (the user switched DAC charging off while we held)
    def kill(m): m.present.add(KILL)
    def off(m): m.call(PSYMS['chg_set'], a0=100, count=4000000)
    def unplug(m): m.setword(pod.DATA['POWER_EXT'][0], 0)
    def bad(m): m.fs[GAUGE] = b'abc'
    def low(m): gauge(m, 70)
    for name, how, dt in (('the kill switch', kill, 1), ('limit 100%', off, 0), ('unplugged', unplug, PERIOD), ('a bad gauge', bad, PERIOD), ('70 % (the resume level)', low, PERIOD)):
        m = held(); dac_off(m); how(m)
        a = tick(m, dt)
        b = tick(m)
        expect(a == [] and b == [] and m.fs[SWITCH] == b'0\n', f'held, then DAC charging off and {name}: nothing written at the next ticks (the switch stays "0", stock\'s)')
        if how is kill: m.present.discard(KILL)
        if how is off: m.call(PSYMS['chg_set'], a0=80, count=4000000)
        if how is unplug: m.setword(pod.DATA['POWER_EXT'][0], 1)
        gauge(m, 70); dac_off(m, False); m.fs[SWITCH] = b'1\n'   # the mode ends (stock's exit writes "1"), below the limit
        expect(tick(m) == [] and tick(m) == [], f'after {name}, the DAC mode ending at 70 %: no stale hold, nothing written')
    m = held(); dac_off(m); m.present.add(KILL)
    m.fail.add(('write', SWITCH))
    tick(m, 1); m.fail.clear(); dac_off(m, False)
    expect(tick(m, 1) == [], 'kill switch with DAC charging off: the hold is dropped at once, so the DAC mode ending later writes nothing either')
    # the limit changed in Settings: applied at the next tick
    m = held()
    expect(m.call(PSYMS['chg_set'], a0=100, count=4000000) == 100 and tick(m, 0) == [b'1\n'], 'limit set to 100 % while held: released at the next tick, in the same second')
    expect(tick(m) == [] and m.names() == ['get_battery_capacity', 'access'], 'then no limit: stock\'s steady state')
    m = held()
    expect(m.call(PSYMS['chg_set'], a0=90, count=4000000) == 90 and tick(m, 0) == [b'1\n'], 'limit raised to 90 % at 85 %: released (85 is 90 - 5)')
    m = held()
    expect(m.call(PSYMS['chg_set'], a0=85, count=4000000) == 85 and tick(m, 0) == [], 'limit 85 % at 85 %: still held')
    # a failed release is tried again, even with no limit
    m = held(); m.fail.add(('write', SWITCH)); m.call(PSYMS['chg_set'], a0=100, count=4000000)
    tick(m, 0); m.fs[SWITCH] = b'0\n'; m.fail.clear()
    expect(tick(m) == [b'1\n'], 'a failed release with the limit off: written again at the next check')
    expect(tick(m) == [], 'and then nothing')


def settings_tests(ctx):
    """Settings > System > Battery, the Charge Limit picker, the Settings Files row, the assets."""
    expect, P = ctx.expect, pod_pages
    V, B, L = P.SETTINGS_PAGE, P.BATTERY_PAGE, P.CHGLIMIT_PAGE
    labels = [r.label for r in V.rows]
    expect(labels[labels.index('Keyboards') + 1] == 'Battery' and labels[labels.index('Battery') + 1] == 'About' and V.rows[labels.index('Battery')].action == P.ACT_PAGE and V.rows[labels.index('Battery')].arg == P.BATTERY_PAGE_INDEX,
           'Settings > System: Battery between Keyboards and About')
    expect(P.PAGES[P.BATTERY_PAGE_INDEX] is B and P.PAGES[P.CHGLIMIT_PAGE_INDEX] is L and B.title == 'Battery' and L.title == 'Charge Limit'
           and [(r.label, r.action, r.arg) for r in B.rows] == [('Battery Percentage', P.ACT_BATTPCT, 0), ('Charge Limit', P.ACT_CHGLIM, P.CHGLIMIT_PAGE_INDEX)]
           and [P.row_kind(r) for r in B.rows] == ['switch', 'value'],
           'the Battery page: the Battery Percentage switch, then the Charge Limit value row')
    expect([(r.label, r.action, r.arg) for r in L.rows] == [(f'{p}%', P.ACT_CHGLIMSET, p) for p in (80, 85, 90, 95, 100)] and all(P.row_kind(r) == 'check' for r in L.rows)
           and P.CHGLIMIT_VALUES == tuple(range(DEFS['CHG_MIN'], DEFS['CHG_OFF'] + 1, DEFS['CHG_STEP'])), 'the picker: 80 .. 100 % in 5 % steps, a check each')
    expect((P.ACT_CHGLIM, P.ACT_CHGLIMSET) == (80, 81) and P.ACT_CHGLIM in P.VALUE_ACTIONS and P.ACT_CHGLIMSET in P.CHECK_ACTIONS and 'battery-charge-limit' in P.SETTING_FILES,
           'the actions and the Settings Files row')
    import pod_i18n
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in ('Battery', 'Charge Limit', B.layout[1].text, B.layout[3].text, L.layout[-1].text)), f'the page texts have a translation in {loc}')

    def page(index, saved, nrows, value=False):
        m = CM()
        if saved is not None: m.fs[FILE] = saved
        kinds = ['pod_value', 'pod_label'] if value else ['pod_check', 'pod_label']
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ['pod_row'] + kinds for i in range(nrows)])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, index)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    def checks(m):
        out = []
        for i in range(5):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out
    for saved, want in ((None, [0, 0, 0, 0, 1]), (b'0\n', [1, 0, 0, 0, 0]), (b'3\n', [0, 0, 0, 1, 0]), (b'z', [0, 0, 0, 0, 1])):
        m = page(P.CHGLIMIT_PAGE_INDEX, saved, 5)
        expect(('window_open', L.key) in m.calls and checks(m) == want, f'saved {saved!r}: the picker\'s check {checks(m)}')
    m = page(P.CHGLIMIT_PAGE_INDEX, None, 5)
    m.click('pod_row1')
    expect(m.fs.get(FILE) == b'1\n' and checks(m) == [0, 1, 0, 0, 0], 'a tap on 85%: saved, the check follows')
    m.fail.add(('write', FILE + '.tmp')); m.calls = []; m.click('pod_row0')
    expect(m.fs.get(FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed save: neither the file nor the check change')
    for saved, want in ((None, '100%'), (b'0\n', '80%'), (b'2\n', '90%')):
        m = page(P.BATTERY_PAGE_INDEX, saved, 2, value=True)
        got = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets['pod_value1']]
        expect(got == [want], f'saved {saved!r}: the Charge Limit row shows {got}')
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    tree = awtk_ui.parse(open(os.path.join(raw, 'm1plus_chargelimit.bin'), 'rb').read())
    expect(all(tree.find(f'pod_check{i}').get('visible') == 'false' and tree.find(f'pod_check{i}').get('sensitive') == 'false' for i in range(5))
           and tree.find('label_title').get('tr_text') == 'Charge Limit', 'the picker asset: five rows, a hidden insensitive check each')
    bt = awtk_ui.parse(open(os.path.join(raw, 'm1plus_battery.bin'), 'rb').read())
    st = awtk_ui.parse(open(os.path.join(raw, 'm1plus_settings.bin'), 'rb').read())
    expect(bt.find('pod_row0').find('pod_icon').get('image') == 'pod_ci_battery_charging' and bt.find('pod_row1').find('pod_icon').get('image') == 'pod_ci_battery_medium' and bt.find('label_title').get('tr_text') == 'Battery'
           and st.find(f'pod_row{labels.index("Battery")}').find('pod_icon').get('image') == 'pod_ci_battery_full', 'the glyphs: battery-full on Settings, battery-charging on Battery Percentage, battery-medium on Charge Limit')


SECTIONS = [limit_tests, hold_tests, release_tests, settings_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

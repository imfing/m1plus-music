"""External power (patch/power.c, docs/modules/charging.md "External power"): the shared reading and its precedence, the raw GPIO read, Battery History counting charging from
a source other than the status text, and the Charge Limit worker (holds at the limit without the status bar's tick; the lock, kill switch and DAC rules of patch/charging.c)."""
import importlib.util, os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'power.h'), strings=True)
STATUS, USB, AC, GPIO_DEV = DEFS['PWR_STATUS'], DEFS['PWR_ONLINE_USB'], DEFS['PWR_ONLINE_AC'], DEFS['PWR_GPIO_DEV']
REQ = DEFS['PWR_GPIO_GET']
KILL = '/mnt/mmc/m1plus-off'
HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    """Another feature's test module, for its machine and helpers (loaded under its own name for this module)."""
    spec = importlib.util.spec_from_file_location(f'power_{name}', os.path.join(HERE, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sources(m, status=None, usb=None, ac=None, gpio=None):
    """Fake the sources: a text for each file (None: the file does not exist), PD17's level (None: /dev/gpio missing; 'err': the ioctl fails)."""
    for path, v in ((STATUS, status), (USB, usb), (AC, ac)):
        if v is None: m.fs.pop(path, None)
        else: m.fs[path] = v
    m.fs.pop(GPIO_DEV, None); m.gpio = {}
    if gpio is not None:
        m.fs[GPIO_DEV] = b''
        if gpio == 'err': m.fail.add(('ioctl', REQ))
        else: m.gpio = {'PD17': gpio}


def external(m): return m.call(PSYMS['pwr_external'], count=400000) & 0xffffffff


def pwr_tests(ctx):
    """The precedence: any source saying external wins; battery only from a source saying so; no source is unknown."""
    expect = ctx.expect
    expect(STATUS == '/sys/class/power_supply/battery/status' and USB == '/sys/class/power_supply/usb/online' and AC == '/sys/class/power_supply/ac/online' and GPIO_DEV == '/dev/gpio'
           and DEFS['PWR_GPIO_NAME'] == 'PD17' and REQ == 0x2000477a, 'the paths and constants')
    U = 0xffffffff
    cases = [
        (dict(), U, 'no source at all: unknown'),
        (dict(status=b'Unknown\n'), U, 'Unknown status alone: unknown'),
        (dict(status=b'\n'), U, 'an empty status: unknown'),
        (dict(status=b'Charging\n'), 1, 'Charging'), (dict(status=b'Full\n'), 1, 'Full'), (dict(status=b'Not charging\n'), 1, 'Not charging (a hold of ours)'),
        (dict(status=b'Discharging\n'), 0, 'Discharging: battery'),
        (dict(status=b'Unknown\n', usb=b'1\n'), 1, 'Unknown status + usb online 1: external'),
        (dict(status=b'Unknown\n', ac=b'1\n'), 1, 'Unknown status + ac online 1: external'),
        (dict(status=b'Discharging\n', usb=b'1\n'), 1, 'Discharging but usb online 1: external wins'),
        (dict(status=b'Charging\n', usb=b'0\n'), 1, 'Charging with usb online 0: external wins'),
        (dict(usb=b'0\n'), 0, 'usb online 0 alone: battery'), (dict(usb=b'x\n'), U, 'a garbled online file: unknown'),
        (dict(gpio=0), 1, 'PD17 low alone: external (stock usb_detect)'), (dict(gpio=1), 0, 'PD17 high alone: battery'),
        (dict(status=b'Unknown\n', gpio=0), 1, 'Unknown status + PD17 low: external'),
        (dict(status=b'Discharging\n', gpio=0), 1, 'Discharging but PD17 low: external wins'),
        (dict(status=b'Discharging\n', gpio=1), 0, 'Discharging + PD17 high: battery'),
        (dict(status=b'Discharging\n', gpio='err'), 0, 'a failed ioctl is no vote: the status says battery'),
        (dict(status=b'Unknown\n', gpio='err'), U, 'a failed ioctl and Unknown status: unknown'),
        (dict(status=b'Discharging\n'), 0, 'no /dev/gpio: no vote'),
        (dict(status=b'Charging\n', usb=b'0\n', ac=b'0\n', gpio=1), 1, 'every other source says battery, the status says Charging: external'),
    ]
    for kw, want, what in cases:
        m = CM(); sources(m, **kw)
        expect(external(m) == want, f'{what} ({kw})')
    m = CM(); sources(m, status=b'Unknown\n', gpio=1)
    external(m)
    opens = [c for c in m.calls if c[0] == 'open']
    expect(('open', GPIO_DEV, 2) in opens and ('ioctl', GPIO_DEV, REQ) in m.calls and ('close', GPIO_DEV) in m.calls and not [c for c in m.calls if c[0] == 'write'],
           'PD17 is read with open(O_RDWR) / ioctl(0x2000477a, "PD17") / close, and nothing is written')
    expect(('open', STATUS, 0) in opens and ('open', USB, 0) in opens and ('open', AC, 0) in opens and len(opens) == 4, 'four fixed paths, no directory walk')
    expect(not any(c[0] in ('readdir', 'opendir') for c in m.calls), 'no directory is read')


def pins_tests(ctx):
    """The binary assumptions: usb_detect's words and string in the stock demo, libhardware2's words."""
    expect = ctx.expect
    stock = stock_demo_bytes()
    word = lambda a: struct.unpack_from('<I', stock, pod.fileoff(stock, a))[0]
    mine = [p for p in pod.BATTERY_PINS if 0x4d6f30 <= p[0] < 0x4d6f60]
    expect(len(mine) == 7 and all(word(a) == w for a, w, _ in mine), 'usb_detect (0x4d6f30): the pinned words are stock\'s')
    expect(stock[pod.fileoff(stock, pod.GPIO_NAME_ADDR):][:5] == b'PD17\0', 'the string usb_detect passes is "PD17"')
    lib = open(os.path.join(WORK, 'rootfs', pod.GPIO_LIB), 'rb').read()
    pod.check_gpio_lib_bytes(lib)
    pod.check_gpio_lib(os.path.join(WORK, 'rootfs', pod.DEMO))
    for why, off in (('the O_RDWR flag of gpio_open', 0x5580), ('the ioctl request high half', 0x57d4), ('the ioctl request low half', 0x57e8)):
        bad = bytearray(lib); bad[off] ^= 1
        try: pod.check_gpio_lib_bytes(bytes(bad)); ok = False
        except ValueError: ok = True
        expect(ok, f'build pin: {why} changed -> the build fails')
    expect(b'/dev/gpio\0' in lib, 'libhardware2 opens /dev/gpio')


class CM(Machine):
    COUNT = True


def worker_machine(limit=b'0\n', gauge=80, status=b'Charging\n', ext=0, **kw):
    """A Charge Limit machine (80 %, test/pod/charging.py's) whose external power comes from the sources, POWER_EXT as given."""
    cm = sibling('charging')
    m = cm.machine(limit=limit, gauge=f'{gauge}\n'.encode(), ext=ext)
    m.wall = 1800000000
    sources(m, status=status, **kw)
    m.cm = cm
    return m


def run_worker(m, hook, count=40000000):
    """chg_main until it returns; hook(k, m) runs at its k-th sleep (the switch file follows our writes, as a sysfs attribute does)."""
    cm = m.cm
    def on_sleep(k):
        w = cm.writes(m)
        if w: m.fs[cm.SWITCH] = w[-1]
        hook(k, m)
    m.on_sleep = on_sleep
    m.call(PSYMS['chg_main'], count=count)
    return cm.writes(m)


def worker_tests(ctx):
    """The worker holds at the limit from its own loop (no status bar tick, no POWER_EXT needed) and never writes "1": the release is the status bar tick's, on stock's UI thread; the kill switch ends it."""
    expect = ctx.expect
    cm = sibling('charging')
    SW, GAUGE = cm.SWITCH, cm.GAUGE
    seen = {}

    def hook(k, m):
        if k == 1: seen['w1'] = list(cm.writes(m)); m.fs[GAUGE] = b'70\n'
        if k == 2: seen['w2'] = list(cm.writes(m)); m.fs[GAUGE] = b'85\n'; m.fs[SW] = b'1\n'   # stock enabled charging again
        if k == 3: seen['w3'] = list(cm.writes(m)); m.present.add(KILL)
    m = worker_machine(gauge=85)
    w = run_worker(m, hook)
    sl = [c for c in m.calls if c[0] == 'sleep']
    expect(seen['w1'] == [b'0\n'] and seen['w2'] == [b'0\n'] and seen['w3'] == [b'0\n', b'0\n'] and w == [b'0\n', b'0\n'],
           f'POWER_EXT 0, status Charging, no status bar tick: held at 85; at 70 no "1" (the tick releases); stock\'s "1" held again; the kill switch ends it ({w})')
    expect(sl == [('sleep', cm.PERIOD)] * 3 and 'get_battery_capacity' not in m.names() and not [c for c in m.calls if c[0] == 'widget_set_visible'], 'it sleeps CHG_PERIOD between checks and never calls stock or the UI')
    # the sources: any one saying external is enough; unknown status; PD17; POWER_EXT 1 alone
    for kw, ext, what in ((dict(status=b'Unknown\n', usb=b'1\n'), 0, 'Unknown status + usb online 1'), (dict(status=b'Unknown\n', gpio=0), 0, 'Unknown status + PD17 low'),
                          (dict(status=b'Discharging\n', ac=b'1\n'), 0, 'Discharging + ac online 1'), (dict(status=b'Unknown\n'), 1, 'POWER_EXT 1 alone (the old input)')):
        m = worker_machine(gauge=85, ext=ext, **kw)
        w = run_worker(m, lambda k, m: m.present.add(KILL))
        expect(w[:1] == [b'0\n'], f'{what}: the hold is written')
    for kw, what in ((dict(status=b'Discharging\n', gpio=1), 'Discharging + PD17 high'), (dict(status=b'Unknown\n'), 'Unknown status, nothing else'), (dict(status=None), 'no source at all')):
        m = worker_machine(gauge=95, **kw)
        w = run_worker(m, lambda k, m: m.present.add(KILL) if k == 2 else None)
        expect(w == [], f'{what}, POWER_EXT 0: no hold and, never held, "1" is never written')
    # plugged in later: the hold follows the source
    m = worker_machine(gauge=90, status=b'Discharging\n', gpio=1)
    def plug(k, m):
        if k == 1: m.fs[STATUS] = b'Unknown\n'; m.fs[USB] = b'1\n'
        if k == 3: m.fs[USB] = b'0\n'
        if k == 5: m.present.add(KILL)
    w = run_worker(m, plug)
    expect(w == [b'0\n'], f'plugged in (usb online) at 90 %: held; unplugged: no "1" from the worker ({w})')
    # no limit and no hold: the worker ends at once
    for saved in (None, b'4\n'):
        m = worker_machine(limit=saved, gauge=99)
        w = run_worker(m, lambda k, m: None)
        expect(w == [] and not [c for c in m.calls if c[0] == 'sleep'], f'limit file {saved!r}: no check, no sleep')
    # the kill switch from the start: nothing written, the worker ends
    m = worker_machine(gauge=95); m.present.add(KILL)
    w = run_worker(m, lambda k, m: None)
    expect(w == [] and not [c for c in m.calls if c[0] == 'sleep'], 'kill switch, no hold: the worker ends')
    # DAC mode with charging off owns the switch: forgotten, nothing written, "1" never written over the user's choice
    m = worker_machine(gauge=85)
    def dac(k, m):
        if k == 1: cm.dac_off(m); m.fs[GAUGE] = b'60\n'
        if k == 3: m.present.add(KILL)
    w = run_worker(m, dac)
    expect(w == [b'0\n'], f'held, then USB DAC with charging off: the hold is forgotten, no "1" ({w})')
    # a hold of ours is released by the kill switch at once, the DAC state respected
    m = worker_machine(gauge=85)
    def killed(k, m): m.present.add(KILL)
    w = run_worker(m, killed)
    expect(w == [b'0\n'] and [c for c in m.calls if c[0] == 'sleep'] == [('sleep', cm.PERIOD)], f'a hold and then the kill switch: the worker ends at the next check, nothing written ({w})')
    expect(cm.tick(m) == [b'1\n'], 'the next status bar tick releases the hold')
    # on battery the worker sleeps CHG_IDLE; once a check sees external power it is back to CHG_PERIOD
    m = worker_machine(gauge=85, status=b'Discharging\n', usb=b'0\n', ac=b'0\n', gpio=1)
    def plug(k, m):
        if k == 2: m.fs[STATUS] = b'Charging\n'
        if k == 3: m.present.add(KILL)
    w = run_worker(m, plug)
    sl = [c[1] for c in m.calls if c[0] == 'sleep']
    expect(sl == [cm.IDLE, cm.IDLE, cm.PERIOD] and w == [b'0\n'], f'on battery: sleeps of CHG_IDLE, nothing written; plugged in: held at 85, then CHG_PERIOD ({sl}, {w})')
    # the worker's checks never postpone the tick's release: a tick 1 s after a worker check at the resume level releases
    m = worker_machine(gauge=85)
    def resume(k, m):
        if k == 1: m.fs[GAUGE] = b'70\n'
        if k == 2: m.present.add(KILL)
    w = run_worker(m, resume)
    m.present.discard(KILL); m.wall -= cm.PERIOD   # (back to the worker's check at 70 %: its last sleep advanced the clock)
    expect(w == [b'0\n'] and cm.tick(m, dt=1) == [b'1\n'], f'held, then 70 %: the worker leaves the release to the next tick, which does not wait CHG_PERIOD ({w})')
    # a failed write is tried again
    m = worker_machine(gauge=85); m.fail.add(('write', SW))
    def failing(k, m):
        if k == 1: m.fail.clear()
        if k == 2: m.present.add(KILL)
    w = run_worker(m, failing)
    expect(w[:2] == [b'0\n', b'0\n'], f'a failed hold write is repeated at the next check ({w})')


def start_tests(ctx):
    """The worker exists only while a limit under 100 or a hold does; chg_set and the status bar tick start it once."""
    expect = ctx.expect
    cm = sibling('charging')

    def creates(m): return m.names().count('pthread_create')
    m = worker_machine(limit=None)
    cm.tick(m); cm.tick(m)
    expect(creates(m) == 0, 'no limit: no thread')
    m.calls = []
    expect(m.call(PSYMS['chg_set'], a0=100, count=4000000) == 100 and creates(m) == 0, 'chg_set(100): no thread')
    m.calls = []
    expect(m.call(PSYMS['chg_set'], a0=90, count=4000000) == 90 and creates(m) == 1 and ('pthread_detach', 0x1234) in m.calls, 'chg_set(90) starts the worker (detached)')
    m.calls = []
    cm.tick(m); m.call(PSYMS['chg_set'], a0=85, count=4000000)
    expect(creates(m) == 0, 'and nothing starts a second one while it runs')
    m = worker_machine()
    m.calls = []; m.call(PSYMS['bp_capacity'], count=400000)
    expect(creates(m) == 1, 'a status bar tick with a limit set starts it')
    m.calls = []; m.call(PSYMS['bp_capacity'], count=400000)
    expect(creates(m) == 0, 'once')
    m = worker_machine(); m.present.add(KILL)
    m.calls = []; m.call(PSYMS['bp_capacity'], count=400000)
    expect(creates(m) == 0, 'the kill switch: no thread')
    # a failed thread is tried again after 30 ticks
    m = worker_machine(); m.thread_ok = False
    tries = 0
    for _ in range(70):
        m.calls = []; m.call(PSYMS['bp_capacity'], count=400000); tries += creates(m)
    expect(tries == 3, f'a failed thread is tried again after 30 ticks ({tries} tries in 70 ticks)')
    # the worker ended (no limit, no hold): a later limit starts a new one
    m = worker_machine(limit=None)
    m.on_sleep = lambda k: None
    m.call(PSYMS['chg_main'], count=400000)
    m.calls = []
    m.call(PSYMS['chg_set'], a0=80, count=4000000)
    expect(creates(m) == 1, 'after the worker ended, the next limit makes a new one')


def history_tests(ctx):
    """Battery History counts charging from any source: an Unknown status with another source saying external is a charge, and the run stops counting."""
    expect = ctx.expect
    bt = sibling('batthist')
    # control: Unknown status and no other source keeps the last state (battery), as before
    m = bt.machine(status=b'Discharging\n')
    bt.step(m, 0)
    bt.step(m, 15, status=b'Unknown\n')
    v = bt.view(m)
    expect(v['sc_total'] == 15 and not bt.last(m)[1] & bt.CHG, 'control: Unknown status, no other source: still battery, the run counts')
    # Unknown status + usb online 1: external
    m = bt.machine(status=b'Discharging\n')
    bt.step(m, 0)
    bt.step(m, 15)
    expect(bt.view(m)['sc_total'] == 15, 'on battery 15 s')
    m.fs[USB] = b'1\n'
    bt.step(m, 15, status=b'Unknown\n')
    bt.step(m, 15)
    v = bt.view(m)
    expect(bt.last(m)[1] & bt.CHG and v['sc_total'] == 15, 'Unknown status + usb online 1: the bucket is flagged charging and the run stands still')
    m.fs.pop(USB)
    m.fs[STATUS] = b'Discharging\n'
    t = v['unplug_at']
    bt.step(m, 15)
    v2 = bt.view(m)
    expect(v2['unplug_at'] > t and v2['sc_total'] == 0, 'unplugged: a new run starts (counters at 0)')
    # Unknown status + PD17 low
    m = bt.machine(status=b'Discharging\n')
    bt.step(m, 0)
    m.fs[GPIO_DEV] = b''; m.gpio = {'PD17': 0}
    bt.step(m, 15, status=b'Unknown\n')
    bt.step(m, 15)
    expect(bt.last(m)[1] & bt.CHG and bt.view(m)['sc_total'] == 0, 'Unknown status + PD17 low: charging')
    # recording starts on the charger with an Unknown status: no run yet, flagged
    m = bt.machine(status=b'Unknown\n')
    m.fs[AC] = b'1\n'
    bt.step(m, 0)
    bt.step(m, 15)
    expect(bt.last(m)[1] & bt.CHG and bt.view(m)['unplug_at'] == 0, 'a first sample with only ac online 1: charging, no run')


def cpumem_tests(ctx):
    """Hook 41 (check_cpumem @ 0x50b810): skips stock's 6 s drop_caches=3 thread unless the kill switch is present."""
    expect = ctx.expect
    stock = stock_demo_bytes(); built = built_demo_bytes()
    word = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    A = pod.CHECK_CPUMEM
    expect(A == 0x50b810 and pod.CHECK_CPUMEM_PROLOGUE == (0x3c1c0050, 0x279c86c0, 0x0399e021)
           and tuple(word(stock, A + 4 * i) for i in range(3)) == pod.CHECK_CPUMEM_PROLOGUE, 'stock check_cpumem prologue matches pin')
    expect((0x50 << 16) + (0x86c0 - 0x10000) + A == pod.GP, 'check_cpumem prologue computes $gp = 0xa03ed0')
    expect(tuple(word(built, A + 4 * i) for i in range(3)) == (pod.j(PSYMS['m1plus_check_cpumem']), 0, pod.CHECK_CPUMEM_PROLOGUE[2]),
           'built demo has j m1plus_check_cpumem; nop over the first two prologue words')
    tramp = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS['stock_check_cpumem_trampoline'] - pod.BASE)
    expect(tramp == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(A + 12), 0), 'trampoline restores $gp and resumes at +12')
    expect(MANIFEST['hook_check_cpumem'] == {'addr': A, 'target': PSYMS['m1plus_check_cpumem']}, 'manifest records hook_check_cpumem')
    expect(all(word(stock, a) == w and word(built, a) == w for a, w, _ in pod.CHECK_CPUMEM_PINS), 'CHECK_CPUMEM_PINS match stock and stay untouched')

    class CPU(CM):
        def __init__(self):
            super().__init__()
            self.gp_seen = []
            self.handlers[A + 12] = 'stock_check_cpumem_resume'

        def _hook(self, u, address, size, _):
            if self.handlers.get(address) == 'stock_check_cpumem_resume':
                self.gp_seen.append(u.reg_read(UC_MIPS_REG_GP))
                self.calls.append(('stock_check_cpumem_resume', u.reg_read(UC_MIPS_REG_A0)))
                u.reg_write(UC_MIPS_REG_V0, 0x42); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
            return super()._hook(u, address, size, _)

    m = CPU()
    r = m.call(PSYMS['m1plus_check_cpumem'], a0=0x1234, count=200000)
    expect(r == 0 and m.calls == [('access', KILL), ('sleep', 15), ('access', KILL)],
           f'normal boot: checks kill switch, re-checks after 15 s (async SD mount), exits NULL without calling stock ({r}, {m.calls})')
    m = CPU(); m.present.add(KILL)
    r = m.call(PSYMS['m1plus_check_cpumem'], a0=0x1234, count=200000)
    expect(r == 0x42 and m.gp_seen == [pod.GP] and m.calls == [('access', KILL), ('stock_check_cpumem_resume', 0x1234)],
           f'kill switch present at boot: restores $gp and delegates immediately without sleeping ({r:#x}, {m.gp_seen}, {m.calls})')
    m = CPU(); m.on_sleep = lambda k: m.present.add(KILL)
    r = m.call(PSYMS['m1plus_check_cpumem'], a0=0x1234, count=200000)
    expect(r == 0x42 and m.gp_seen == [pod.GP] and ('sleep', 15) in m.calls and ('stock_check_cpumem_resume', 0x1234) in m.calls,
           f'kill switch appears while SD mounts during sleep(15): delegates to stock check_cpumem ({r:#x}, {m.gp_seen}, {m.calls})')


def watchdog_tests(ctx):
    """Lightweight /usr/bin/checkappprocess.sh (tools/mod_watchdog.py): SHA pin, syntax, fallback and built rootfs."""
    import subprocess
    import mod_watchdog
    expect = ctx.expect
    stock_path = os.path.join(WORK, 'rootfs', mod_watchdog.REL)
    built_sh = open(stock_path, 'rb').read()
    expect(built_sh == mod_watchdog.WATCHDOG_SH, 'built rootfs carries the lightweight watchdog script')
    expect(os.stat(stock_path).st_mode & 0o111 != 0, 'watchdog script keeps executable permission')
    r = subprocess.run(['sh', '-n'], input=built_sh, capture_output=True)
    expect(r.returncode == 0, f'watchdog script passes sh -n ({r.stderr.decode("utf-8", "replace")})')
    expect(b'/proc/$DEMO_PID/comm' in built_sh and b'pgrep "/release/bin/demo"' in built_sh and b'reboot' in built_sh,
           'watchdog caches PID via /proc/$DEMO_PID/comm and keeps stock pgrep fallback + reboot')
    try: mod_watchdog.patch(b'not stock'); refused = False
    except ValueError: refused = True
    expect(refused, 'mod_watchdog.patch refuses unpinned stock bytes')


SECTIONS = [pwr_tests, pins_tests, worker_tests, start_tests, history_tests, cpumem_tests, watchdog_tests]

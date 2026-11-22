"""Battery History (patch/batthist.c, docs/modules/batthist.md): the recorder's samples run against fake sysfs, clocks and stock words: buckets and the ring, the since-charge counters, the attribution of a
gauge drop, charging, standby and reboot gaps, the wall clock jumping, the file (fixed size, validated), the switch and the thread's end, and the Settings row."""
import os, struct
import calendar, time as _time
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs
import batthist_model as HM
import pod_settings as ST

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'batthist.h'), strings=True)
BDEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'battery.h'), strings=True)
FILE, DATA, STATUS, GAUGE = DEFS['BH_FILE'], DEFS['BH_DATA'], DEFS['BH_STATUS'], BDEFS['BP_GAUGE']
TMP, DTMP = FILE + '.tmp', DATA + '.tmp'
N, SECS, KILL = DEFS['BH_BUCKETS'], DEFS['BH_SECS'], '/mnt/mmc/m1plus-off'
GAP, CHG = DEFS['BH_F_GAP'], DEFS['BH_F_CHG']
NONE = DEFS['BH_NONE']
HDR = 52
FILE_SIZE = HDR + 8 * N         # magic, version, count, head, unplug_at, unplug_lvl, sc_play, sc_on, sc_total, sc_d_on, sc_d_play, sc_d_idle, since_on, sum, the ring
VIEW_SIZE = 4 + 8 * N + 11 * 4
T0 = 1800000000                 # a quarter hour edge: T0 // 900 = 2000000
assert T0 % SECS == 0


class BM(Machine):
    COUNT = True


def machine(on=True, gauge=80, status=b'Discharging\n', wall=T0 + 60):
    """The player with the setting on (the recorder's thread made, but not run), the gauge, the screen off, nothing playing, clocks at 1000 s."""
    m = BM()
    if on: m.fs[FILE] = b'1\n'
    m.fs[GAUGE] = f'{gauge}\n'.encode()
    m.fs[STATUS] = status
    m.wall = wall
    m.clock_ids = {1: 1000, 7: 1000}
    m.screen(False)
    m.play_status = 1
    m.call(PSYMS['bh_poll'], count=200000)
    return m


def step(m, dt=15, dmono=None, dboot=None, lit=None, play=None, status=None, gauge=None):
    """One sample dt seconds on: MONOTONIC moves dmono (dt), BOOTTIME dboot (dmono); the screen, the play state, the status text and the gauge as given."""
    dmono = dt if dmono is None else dmono
    dboot = dmono if dboot is None else dboot
    m.wall += dt
    m.clock_ids[1] += dmono
    m.clock_ids[7] += dboot
    if lit is not None: m.screen(lit)
    if play is not None: m.play_status = play
    if status is not None: m.fs[STATUS] = status
    if gauge is not None: m.fs[GAUGE] = f'{gauge}\n'.encode()
    m.calls = []
    m.call(PSYMS['bh_sample'], count=4000000)


def view(m):
    """bh_snapshot: None when it says 0, else a dict with the buckets as tuples (level, flags, on, play, cov, d_on, d_play, d_idle), oldest first."""
    buf = m.alloc(VIEW_SIZE)
    r = m.call(PSYMS['bh_snapshot'], a0=buf, count=2000000)
    raw = bytes(m.u.mem_read(buf, VIEW_SIZE))
    head, b, *rest = struct.unpack('<I%dsi10I' % (8 * N), raw)
    if not r:
        assert raw == bytes(VIEW_SIZE), 'a refused snapshot leaves the view zeroed'
        return None
    keys = ('unplug_at', 'unplug_lvl', 'since_on', 'chg', 'level', 'sc_play', 'sc_on', 'sc_total', 'sc_d_on', 'sc_d_play', 'sc_d_idle')
    bk = [struct.unpack_from('8B', b, 8 * i) for i in range(N)]
    live = [k for k in bk if not k[1] & GAP and not k[1] & CHG]   # the buckets' own totals (what the ring attributes): with data, off the charger
    tot = dict(t_on=sum(k[2] * 8 for k in live), t_idle=sum(max(0, k[4] - k[2] - k[3]) * 8 for k in live), d_on=sum(k[5] for k in live), d_play=sum(k[6] for k in live), d_idle=sum(k[7] for k in live),
               act_on=sum(k[2] * 8 for k in bk if not k[1] & GAP))
    return dict(zip(keys, rest), head=head, b=bk, **tot)


def last(m): return view(m)['b'][-1]
def real(v): return [k for k in v['b'] if not k[1] & GAP]
def total(v, f): return sum(k[f] for k in v['b'] if not k[1] & GAP)


def renames(m): return [c for c in m.calls if c[0] == 'rename' and c[2] == DATA]


def constants_tests(ctx):
    """The files, the sizes and the layout the module doc gives."""
    expect = ctx.expect
    expect(FILE == '/mnt/data/m1plus/battery-history' and DATA == FILE + '.bin' and TMP == FILE + '.tmp' and DTMP == DATA + '.tmp' and STATUS == '/sys/class/power_supply/battery/status',
           'the files')
    expect((N, SECS, DEFS['BH_PERIOD'], DEFS['BH_GAUGE'], DEFS['BH_SUSP'], DEFS['BH_SUSP_DROP'], DEFS['BH_JUMP'], GAP, CHG, NONE) == (96, 900, 15, 60, 5, 30, 120, 2, 1, 255),
           '96 buckets of 15 minutes (24 h), a sample per 15 s, the gauge per minute')
    m = machine()
    step(m, 0)
    step(m, 900)
    expect(len(m.fs[DATA]) == FILE_SIZE == 820 < 1024, f'the file is {len(m.fs[DATA])} bytes')
    expect(m.fs[DATA][:4] == b'BHS1' and struct.unpack_from('<HH', m.fs[DATA], 4) == (4, N) and struct.unpack_from('<I', m.fs[DATA], 8)[0] == (T0 + 960) // SECS, 'magic, version, count, the newest bucket')


def sample_tests(ctx):
    """Buckets, the states, the gauge's rate, the play state and the status text."""
    expect = ctx.expect
    m = machine(wall=T0 + 10)
    expect(view(m) is None, 'the thread is made but has not sampled: no view')
    step(m, 0)
    v = view(m)
    expect(v['head'] == (T0 + 10) // SECS and v['b'][-1] == (80, 0, 0, 0, 0, 0, 0, 0) and len(real(v)) == 1 and all(k[1] == GAP and k[0] == NONE for k in v['b'][:-1]),
           'the first sample opens the bucket with the gauge level and no time; the 95 before it have no data')
    # 40 samples of 15 s with the screen on: 600 s = 75 units
    gauge_reads = 0
    for i in range(40):
        step(m, 15, lit=True)
        gauge_reads += sum(1 for c in m.calls if c[0] == 'open' and c[1] == GAUGE)
    expect(last(m) == (80, 0, 75, 0, 75, 0, 0, 0), f'600 s screen on in one bucket: on 75, known 75 ({last(m)})')
    expect(gauge_reads == 10, f'the gauge is read once a minute, not every sample ({gauge_reads} reads in 600 s)')
    # playing with the screen off, paused, idle
    step(m, 120, lit=False, play=2)
    expect(last(m)[2:5] == (75, 15, 90), 'playing with the screen off: play time, not screen time')
    step(m, 60, play=3)
    step(m, 60, play=1)
    expect(last(m)[2:5] == (75, 15, 105), 'paused and stopped with the screen off: known time only (idle)')
    step(m, 8, lit=True, play=2)
    expect(last(m)[2] == 76 and last(m)[3] == 15, 'the screen on wins over playing')
    # the status text: unreadable or odd keeps the last answer; Not charging / Full are external power
    for text, want in ((b'Charging\n', CHG), (b'', CHG), (b'Unknown\n', CHG), (b'Discharging\n', CHG), (b'Not charging\n', CHG), (b'Full\n', CHG)):
        m = machine(); step(m, 0); step(m, 60, status=b'Charging\n')
        step(m, 60, status=text)
        expect((last(m)[1] & CHG) == want, f'status {text!r} after Charging: the bucket is flagged charging')
    m = machine(status=b'Unknown\n'); step(m, 0); step(m, 60)
    expect(not last(m)[1] & CHG, 'an unknown status from the start is battery')
    m = machine(status=b'Not charging\n'); step(m, 0)
    expect(last(m)[1] & CHG, 'Not charging (the Charge Limit holding the charger) is external power')
    m = machine(); m.fs.pop(STATUS); step(m, 0); step(m, 60, lit=True)
    expect(not last(m)[1] & CHG and last(m)[2] == 7, 'no status file: battery, the sample still counts')
    # a gauge that cannot be read: the level stays, the time counts
    m = machine(); step(m, 0); m.fs.pop(GAUGE); step(m, 60, lit=True); step(m, 60, lit=True)
    expect(last(m)[0] == 80 and last(m)[2] == 15, 'no gauge: the last level, time still counted')
    # no BOOTTIME: MONOTONIC stands in, a long step is a clock set forward and never standby
    m = machine(); step(m, 0); m.fail.add(('clock_gettime', 7))
    m.wall += 600; m.clock_ids[1] += 15; m.calls = []; m.call(PSYMS['bh_sample'], count=4000000)
    expect(total(view(m), 4) <= 2 and last(m)[4] <= 2, 'BOOTTIME missing: no standby is invented from a long step')
    # an unset RTC: nothing recorded, and the first valid time is a baseline
    m = machine(wall=1000); step(m, 0); step(m, 60, lit=True)
    expect(view(m) is None and DATA not in m.fs, 'wall clock before 2020: nothing recorded')
    m.wall = T0 + 61; m.clock_ids[1] += 10; m.clock_ids[7] += 10; step(m, 0)
    expect(view(m) is not None and last(m)[4] == 0, 'the clock is set: a baseline, no time for the time before it')


def attribution_tests(ctx):
    """A gauge drop goes to the state with the most seconds since the last drop; charging attributes nothing."""
    expect = ctx.expect

    def run(phases):
        m = machine(); step(m, 0)
        for dt, kw in phases: step(m, dt, **kw)
        v = view(m)
        return m, (v['d_on'], v['d_play'], v['d_idle'])
    on, play, idle = dict(lit=True, play=1), dict(lit=False, play=2), dict(lit=False, play=1)
    _, d = run([(60, dict(on, gauge=80))] * 5 + [(60, dict(on, gauge=79))])
    expect(d == (1, 0, 0), f'screen on, the gauge falls 1: screen on ({d})')
    _, d = run([(60, dict(play, gauge=80))] * 3 + [(60, dict(play, gauge=79))])
    expect(d == (0, 1, 0), f'playing with the screen off: playing ({d})')
    _, d = run([(60, dict(idle, gauge=80))] * 3 + [(60, dict(idle, gauge=79))])
    expect(d == (0, 0, 1), f'screen off, nothing playing: idle ({d})')
    _, d = run([(60, dict(on, gauge=80))] * 2 + [(60, dict(play, gauge=80))] + [(60, dict(play, gauge=79))])
    expect(d == (1, 0, 0), f'a tie (120 s each... screen on and playing): the screen on ({d})')
    _, d = run([(60, dict(on, gauge=80))] + [(60, dict(play, gauge=80))] * 2 + [(60, dict(play, gauge=79))])
    expect(d == (0, 1, 0), f'1 minute screen on, 3 minutes playing: playing ({d})')
    _, d = run([(60, dict(on, gauge=80))] + [(60, dict(idle, gauge=80))] * 3 + [(60, dict(idle, gauge=77))])
    expect(d == (0, 0, 3), f'a drop of 3 % is attributed whole ({d})')
    _, d = run([(60, dict(on, gauge=80))] * 3 + [(60, dict(on, gauge=79))] + [(60, dict(idle, gauge=79))] * 3 + [(60, dict(idle, gauge=78))])
    expect(d == (1, 0, 1), f'the seconds count from the last drop: screen on first, then idle ({d})')
    _, d = run([(60, dict(on, gauge=80))] * 2 + [(60, dict(on, gauge=81))] + [(60, dict(on, gauge=81))])
    expect(d == (0, 0, 0), 'a rise in the gauge attributes nothing')
    # the gauge's own cadence: a 15 s step that does not read the gauge cannot see the drop yet
    m = machine(); step(m, 0); step(m, 15, lit=True, gauge=79)
    expect(total(view(m), 5) == 0 and last(m)[0] == 80, 'the gauge is not read before a minute has passed')
    step(m, 45, lit=True)
    v = view(m)
    expect(v['d_on'] == 1 and last(m)[0] == 79, 'a minute later the drop is seen and goes to the screen')
    # charging: the bucket is flagged, the level follows, nothing attributed, and the totals leave it out
    m = machine(); step(m, 0); step(m, 60, lit=True, gauge=80)
    step(m, 60, lit=True, gauge=79, status=b'Charging\n')
    step(m, 60, lit=True, gauge=78)
    v = view(m)
    expect(last(m)[1] & CHG and last(m)[0] == 78 and (v['d_on'], v['d_play'], v['d_idle']) == (0, 0, 0), 'charging: flagged, the level follows the gauge, no drop attributed')
    expect(v['t_on'] == 0 and v['act_on'] > 0 and v['t_idle'] == 0, 'the rates leave the charging bucket out, the activity totals keep its screen time')
    step(m, 900, lit=False, status=b'Discharging\n', gauge=77)
    step(m, 60, lit=False, gauge=77)
    expect(not last(m)[1] & CHG and view(m)['b'][-2][1] & CHG, 'unplugged: the next bucket is not flagged, the one before keeps it')
    step(m, 60, lit=False, gauge=76)
    expect(view(m)['d_idle'] == 1, 'and drops count again on battery')
    # on the charger a fall that comes from the charger being unplugged is not a drop of the first minutes on battery: the sums start over
    m = machine(); step(m, 0); step(m, 60, lit=True, gauge=80, status=b'Charging\n'); step(m, 60, lit=True, gauge=80, status=b'Discharging\n')
    step(m, 60, lit=False, play=1, gauge=79)
    expect(view(m)['d_on'] == 0 or view(m)['d_idle'] == 0, 'the minute of the unplugging does not count for either side')


def ring_tests(ctx):
    """Rollover, the ring's wrap, a constant file, the write rate."""
    expect = ctx.expect
    m = machine(); step(m, 0)
    first = (T0 + 60) // SECS
    sizes, writes = set(), 0
    for i in range(1, 100 * 3 + 1):
        step(m, 300, lit=bool(i & 1), gauge=max(0, 80 - i // 10))
        writes += len(renames(m))
        sizes.add(len(m.fs[DATA]))
    v = view(m)
    expect(v['head'] == (T0 + 60 + 300 * 300) // SECS == first + 100 and not any(k[1] & GAP for k in v['b']) and len(v['b']) == N,
           'a hundred buckets later the ring holds the last 96, none a gap, head moved with the clock')
    expect(v['b'][-1][0] == max(0, 80 - 300 // 10) and v['b'][0][4] > 0, 'the newest bucket has the level, the oldest still has time')
    expect(sizes == {FILE_SIZE} and writes == 100 + 1 - 1 + 0 and TMP not in m.fs and DTMP not in m.fs, f'the file is {sizes} bytes, written {writes} times in 100 buckets, no temporary file stays')
    # a bucket per quarter hour of wall clock: the edge is the wall clock's, whatever the sample times
    m = machine(wall=T0 + 899); step(m, 0)
    h = view(m)['head']
    step(m, 1)
    w = len(renames(m))
    expect(view(m)['head'] == h + 1 and w == 1, 'the bucket changes on the wall clock edge, and the file is written then')
    step(m, 15)
    expect(len(renames(m)) == 0, 'and not at the next sample')
    # one write per bucket; nothing written while no bucket opens
    m = machine(); step(m, 0)
    n = 0
    for i in range(50):
        step(m, 15, lit=True)
        n += len(renames(m))
    expect(n == 0, 'twelve minutes of samples inside one bucket write nothing')


def gap_tests(ctx):
    """Standby, a reboot, the wall clock jumping."""
    expect = ctx.expect
    # standby: the thread sleeps 15 s of MONOTONIC while BOOTTIME runs 30 minutes; the gauge falls across it
    m = machine(); step(m, 0)
    for i in range(4): step(m, 60, lit=True, gauge=80)
    step(m, 1800, dmono=15, dboot=1800, lit=False, gauge=79)
    v = view(m)
    expect((v['d_on'], v['d_play'], v['d_idle']) == (0, 0, 1), f'the drop across a standby is the standby\'s, whatever the screen did before ({v["d_on"]}, {v["d_play"]}, {v["d_idle"]})')
    expect(v['head'] == (T0 + 60 + 240 + 1800) // SECS and not any(k[1] & GAP for k in v['b'][-3:]), 'the buckets the standby covered are not gaps')
    cov, on = total(v, 4), total(v, 2)
    expect(abs(cov - (240 + 1800) // 8) <= 1 and on == 30, f'known time = the screen minutes + the standby ({cov} units), screen time only the 240 s ({on})')
    expect(v['b'][-3][4] > 0 and v['b'][-3][2] == 0 or v['b'][-2][2] == 0, 'a bucket that was only standby has known time and no screen time')
    # a drop after a short pause in the thread (a 3 s hiccup) is not a standby
    m = machine(); step(m, 0)
    for i in range(3): step(m, 60, lit=True, gauge=80)
    step(m, 60, dmono=55, dboot=60, lit=True, gauge=79)
    expect(view(m)['d_on'] == 1, 'under BH_SUSP seconds of difference between the clocks: not a standby')
    # a drop with 40 s of standby and 4 minutes of screen goes to the standby (30 s or more since the last read), 20 s does not
    for susp, want in ((40, (0, 0, 1)), (20, (1, 0, 0))):
        m = machine(); step(m, 0)
        for i in range(3): step(m, 60, lit=True, gauge=80)
        step(m, 60, dmono=60 - susp, dboot=60, lit=True, gauge=79)
        v = view(m)
        expect((v['d_on'], v['d_play'], v['d_idle']) == want, f'{susp} s of standby since the last read: {want}')
    # the gauge is read at once after a standby
    m = machine(); step(m, 0); step(m, 20, lit=True)
    step(m, 100, dmono=15, dboot=100, gauge=79)
    expect(any(c[0] == 'open' and c[1] == GAUGE for c in m.calls) and last(m)[0] == 79, 'the gauge is read when the thread wakes from a standby, before a minute is up')
    # a reboot: the file's newest bucket is older than now; the buckets between are gaps, the older ones kept
    m = machine(); step(m, 0)
    for i in range(1, 8): step(m, 300, lit=True, gauge=80)
    head = view(m)['head']
    old = view(m)['b']
    saved = m.fs[DATA]
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
    m2.wall = (head + 6) * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    v = view(m2)
    expect(v['head'] == head + 6, 'after the reboot the newest bucket is the current one')
    got = v['b']
    expect(got[-1][0] == 70 and all(k[1] == GAP and k[0] == NONE for k in got[-6:-1]), 'the five buckets between are gaps with no level')
    # the file's newest bucket was saved when it opened: its content is the file's
    expect(got[-8] == old[-2] and not got[-7][1] & GAP, 'the buckets the file had are as it had them (the newest as of its write)')
    expect(any(k[1] & GAP == 0 and k[4] > 0 for k in got[:-6]), 'the history before the power off is still there')
    # the same bucket (a quick reboot): no gap
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
    m2.wall = head * SECS + 10; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    expect(view(m2)['head'] == head and not any(k[1] & GAP for k in view(m2)['b'][-3:]) and last(m2)[0] == 70, 'a reboot inside the same bucket: it goes on, no gap')
    # the wall clock before the file's newest bucket: a clock that went back, the history is dropped
    for back in (2 * SECS, 3600, 10 * 24 * 3600):
        m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
        m2.wall = head * SECS - back; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
        m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
        v = view(m2)
        expect(len(real(v)) == 1 and v['head'] == (head * SECS - back) // SECS, f'the file is {back} s ahead of the clock: dropped, a fresh ring')
    # the wall clock set back while running: dropped; a small step back: kept
    m = machine(); step(m, 0)
    for i in range(1, 8): step(m, 300, lit=True)
    n = len(real(view(m)))
    step(m, -30, dmono=15)
    expect(len(real(view(m))) == n, 'the clock stepped back 45 s against BOOTTIME: the history stays')
    step(m, -3600, dmono=15)
    v = view(m)
    expect(len(real(v)) == 1 and v['head'] == m.wall // SECS, 'the clock set back an hour: the history is dropped, a new bucket')
    # set forward 2 hours (BOOTTIME did not move): the buckets in between are gaps, not standby
    m = machine(); step(m, 0)
    for i in range(1, 4): step(m, 300, lit=True)
    before = view(m)
    step(m, 7200, dmono=15)
    v = view(m)
    gaps = v['head'] - before['head'] - 1
    expect(gaps >= 7 and all(k[1] == GAP for k in v['b'][-1 - gaps:-1]) and total(v, 4) == total(before, 4) + 2 or total(v, 4) == total(before, 4) + 1,
           f'the clock set forward: {gaps} gap buckets, only the 15 s of the step counted')
    expect(any(k[4] > 0 for k in v['b'][:-gaps - 1]), 'and the history before it stays')
    # more than a day of gap: all gaps but the newest
    step(m, 3 * 24 * 3600, dmono=15)
    v = view(m)
    expect(len(real(v)) == 1, 'a three day jump: only the new bucket has data')
    # a clock that went back inside the run (BOOTTIME smaller): a new baseline, the ring is kept
    m = machine(); step(m, 0)
    for i in range(1, 5): step(m, 60, lit=True)
    cov = last(m)[4]
    m.clock_ids = {1: 5, 7: 5}
    step(m, 15, lit=True)
    expect(last(m)[4] == cov, 'a monotonic clock that went back: a new baseline, no time made up')


def corrupt_tests(ctx):
    """A file this build did not write, or a damaged one, is dropped; a good one is read."""
    expect = ctx.expect
    m = machine(); step(m, 0)
    for i in range(1, 8): step(m, 300, lit=True)
    good = m.fs[DATA]
    head = view(m)['head']

    def reload(data, size_ok=True):
        m2 = BM(); m2.fs = {FILE: b'1\n', GAUGE: b'70\n', STATUS: b'Discharging\n'}
        if data is not None: m2.fs[DATA] = data
        m2.wall = head * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
        m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
        return m2

    def known(m2): return total(view(m2), 4)
    expect(known(reload(good)) > 0, 'control: the good file is read')
    flip = lambda i, to=None: good[:i] + bytes([(good[i] ^ 0x55) if to is None else to]) + good[i + 1:]
    struct_head = lambda v: good[:8] + struct.pack('<I', v) + good[12:]
    cases = {'missing': None, 'empty': b'', 'truncated': good[:-1], 'too long': good + b'\0', 'magic': flip(0), 'version': flip(4), 'count': flip(6), 'a byte of a bucket (the checksum)': flip(100),
             'the checksum': flip(48), 'the since-charge counters (the checksum)': flip(20), 'a version 3 file (the old size and version)': None, 'play over the total with a matching checksum': None, 'screen on and playing together over the total with a matching checksum': None, 'a level over 100 with a matching checksum': None, 'head far in the past': struct_head(1), 'zeros': bytes(FILE_SIZE), 'text': b'1\n' * 400}
    # a file with every field checked but a wrong value and a right checksum
    def resum(f):
        h = struct.unpack_from('<10I', f, 8)
        sm = (h[0] * 2654435761 + h[1] * 31 + h[2] + h[3] * 7 + h[4] * 13 + h[5] * 17 + h[6] * 19 + h[7] * 23 + h[8] * 29 + h[9] * 37) & 0xffffffff
        for b in f[HDR:]: sm = (sm * 31 + b) & 0xffffffff
        struct.pack_into('<I', f, 48, sm)
        return bytes(f)
    f = bytearray(good)
    f[HDR] = 150
    cases['a level over 100 with a matching checksum'] = resum(f)
    f = bytearray(good)
    struct.pack_into('<4I', f, 12, (head - 1) * SECS, 80, 500, 100)
    struct.pack_into('<I', f, 28, 400)
    cases['play over the total with a matching checksum'] = resum(f)
    f = bytearray(good)
    struct.pack_into('<4I', f, 12, (head - 1) * SECS, 80, 300, 300)
    struct.pack_into('<I', f, 28, 500)
    cases['screen on and playing together over the total with a matching checksum'] = resum(f)
    f = bytearray(good)
    struct.pack_into('<4I', f, 12, (head - 1) * SECS, 80, 300, 100)
    struct.pack_into('<I', f, 28, 600)
    m2 = reload(resum(f))
    expect(len(real(view(m2))) > 1 and (view(m2)['unplug_at'], view(m2)['unplug_lvl'], view(m2)['sc_play'], view(m2)['sc_on'], view(m2)['sc_total']) == ((head - 1) * SECS, 80, 300, 100, 600),
           'control: a file with since-charge counters is read')
    f = bytearray(good)
    struct.pack_into('<4I', f, 12, (head - 1) * SECS, 80, 300, 100)
    struct.pack_into('<5I', f, 28, 600, 20, 10, 5, 1)
    m2 = reload(resum(f)); v2 = view(m2)
    expect(len(real(v2)) > 1 and (v2['sc_d_on'], v2['sc_d_play'], v2['sc_d_idle'], v2['since_on']) == (20, 10, 5, 1), 'control: a file with drops and since_on 1 is read')
    f = bytearray(good)
    f[4:6] = struct.pack('<H', 3)
    cases['a version 3 file (the old size and version)'] = resum(f)
    cases['a version 3 file (the old size and version)'] = cases['a version 3 file (the old size and version)'][:36 + 8 * N]
    for name, put in (('since_on 2', (2, 0, 0, 0)), ('sc_d_on 101', (1, 101, 0, 0)), ('sc_d_play 101', (1, 0, 101, 0)), ('sc_d_idle 101', (1, 0, 0, 101))):
        f = bytearray(good)
        struct.pack_into('<4I', f, 12, (head - 1) * SECS, 80, 300, 100)
        struct.pack_into('<5I', f, 28, 600, put[1], put[2], put[3], put[0])
        cases[f'{name} with a matching checksum'] = resum(f)
    for name, off in (('sc_d_on', 32), ('sc_d_idle', 40), ('since_on', 44)):
        f = bytearray(good)
        struct.pack_into('<4I', f, 12, 0, NONE, 0, 0)
        struct.pack_into('<5I', f, 28, 0, 0, 0, 0, 0)
        struct.pack_into('<I', f, off, 1)
        cases[f'{name} without an unplug_at (matching checksum)'] = resum(f)
    for name, data in cases.items():
        m2 = reload(data)
        v = view(m2)
        expect(len(real(v)) == 1 and known(m2) == 0, f'{name}: dropped, a fresh ring')
        expect(len(m2.fs[DATA]) == FILE_SIZE, f'{name}: the next write is a good file')
    m2 = reload(good)
    m2.call(PSYMS['bh_load'], count=2000000)
    expect(known(m2) > 0, 'reading twice changes nothing')
    # the file of a clock that is ahead (head in the future, valid checksum) is dropped when the wall clock is read
    m2 = BM(); m2.fs = {FILE: b'1\n', GAUGE: b'70\n', STATUS: b'Discharging\n', DATA: good}
    m2.wall = (head - 50) * SECS; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False)
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    expect(len(real(view(m2))) == 1, 'a newest bucket in the future: dropped')


def switch_tests(ctx):
    """The setting, the thread's start and end, the kill switch, the files."""
    expect = ctx.expect
    # off (the default): no thread, no file, nothing but a cached compare
    m = BM(); m.fs[GAUGE] = b'80\n'
    m.call(PSYMS['bh_poll'], count=200000)
    expect(('pthread_create',) not in m.calls and not [c for c in m.calls if c[0] in ('open', 'rename')][1:] and view(m) is None, 'setting off: no thread')
    m.calls = []
    m.call(PSYMS['bh_poll'], count=200000)
    expect(m.names() == [] and m.icount < 60, f'and then the cached flag only ({m.names()}, {m.icount} instructions)')
    # the switch on: the file, one thread, none more
    expect(m.call(PSYMS['bh_toggle'], count=4000000) == 1 and m.fs[FILE] == b'1\n' and m.names().count('pthread_create') == 1 and ('pthread_detach', 0x1234) in m.calls,
           'the switch on: "1" saved, the thread made and detached')
    expect(m.call(PSYMS['bh_setting'], count=200000) == 1, 'bh_setting says on')
    m.calls = []
    for i in range(5): m.call(PSYMS['bh_poll'], count=200000)
    expect('pthread_create' not in m.names(), 'ticks while it runs make no second thread')
    # a thread that cannot be made: the next try comes later, and is made once it can
    m = BM(); m.fs[FILE] = b'1\n'; m.thread_ok = False
    tries = 0
    for i in range(70):
        m.calls = []; m.call(PSYMS['bh_poll'], count=200000); tries += m.names().count('pthread_create')
    expect(tries == 3 and ('pthread_detach', 0x1234) not in m.calls, f'a failed thread is tried again after 30 ticks ({tries} tries in 70 ticks)')
    m.thread_ok = True
    for i in range(31):
        m.calls = []; m.call(PSYMS['bh_poll'], count=200000)
        if 'pthread_create' in m.names(): break
    expect('pthread_detach' in m.names(), 'and then made')
    # the kill switch: bp_capacity (the status bar tick) starts nothing
    for kill, want in ((True, 0), (False, 1)):
        m = BM(); m.fs[FILE] = b'1\n'; m.fs[GAUGE] = b'50\n'; m.stock_cap = 40
        for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG', 'SYSTEM_BAR'): m.setword(pod.DATA[k][0], 0)
        if kill: m.present.add(KILL)
        m.call(PSYMS['bp_capacity'], count=400000)
        expect(m.names().count('pthread_create') == want, f'the status bar tick, kill switch {"there" if kill else "absent"}: {want} thread')
    # the switch off: the setting '0', the data and its temporary file gone, no view
    m = machine(); step(m, 0); step(m, 900)
    expect(DATA in m.fs and view(m) is not None, 'recording: the file is there')
    m.fs[DTMP] = b'x'
    expect(m.call(PSYMS['bh_toggle'], count=4000000) == 0 and m.fs[FILE] == b'0\n' and DATA not in m.fs and DTMP not in m.fs and view(m) is None, 'off: "0" saved, the data deleted, no view')
    m.call(PSYMS['bh_toggle'], count=4000000)
    expect(m.fs[FILE] == b'1\n' and view(m) is None, 'on again: a fresh ring (no view before the first sample)')
    step(m, 0)
    expect(len(real(view(m))) == 1, 'and one bucket after the first sample')
    # a failed save of the setting changes nothing
    m = machine(); step(m, 0); m.fail.add(('write', FILE + '.tmp'))
    expect(m.call(PSYMS['bh_toggle'], count=4000000) == 0xffffffff and m.fs[FILE] == b'1\n' and view(m) is not None, 'a failed save: -1, still recording')
    # a write that was running when the setting went off deletes its file again (the state word, bh + 4, is what bh_toggle flips under the lock)
    m = machine(); step(m, 0)
    m.on_fsync = lambda p: m.setword(PSYMS['bh'] + 4, 1) if p == DTMP else None
    step(m, 900)
    expect(DATA not in m.fs and DTMP not in m.fs, 'the setting went off while the file was being written: the file is deleted again')
    # the thread: samples every 15 s while the setting is on, ends when it is off, leaves nothing
    m = BM(); m.fs[FILE] = b'1\n'; m.fs[GAUGE] = b'80\n'; m.fs[STATUS] = b'Discharging\n'; m.wall = T0 + 60; m.clock_ids = {1: 1000, 7: 1000}; m.screen(True); m.play_status = 1
    m.call(PSYMS['bh_poll'], count=200000)
    seen = []

    def on_sleep(k):
        m.wall += 1; m.clock_ids[1] += 1; m.clock_ids[7] += 1
        seen.append(k)
        if k == 45: m.fs[FILE] = b'0\n'
    m.on_sleep = on_sleep
    m.call(PSYMS['bh_main'], count=20000000)
    sleeps = [c for c in m.calls if c[0] == 'sleep']
    expect(sleeps == [('sleep', 1)] * 45 and m.names().count('clock_gettime') == 6, f'the thread waited 15 s in 1 s steps three times and took a sample before each ({len(sleeps)} sleeps, {m.names().count("clock_gettime")} clock reads)')
    expect(DATA not in m.fs and DTMP not in m.fs and view(m) is None, 'the setting went off: the thread ended, the data is gone, no view')
    m.calls = []
    m.call(PSYMS['bh_poll'], count=200000)
    expect('pthread_create' not in m.names(), 'and nothing starts it again while the setting is off')
    # a request from the History page ends the wait at the next step: the sample comes early
    m = BM(); m.fs[FILE] = b'1\n'; m.fs[GAUGE] = b'80\n'; m.fs[STATUS] = b'Discharging\n'; m.wall = T0 + 60; m.clock_ids = {1: 1000, 7: 1000}; m.screen(True); m.play_status = 1
    m.call(PSYMS['bh_poll'], count=200000)
    probe = BM(); b0 = bytes(probe.u.mem_read(PSYMS['bh'], 0x60)); probe.call(PSYMS['bh_request'], count=200000)
    flag = [i for i, (x, y) in enumerate(zip(b0, probe.u.mem_read(PSYMS['bh'], 0x60))) if x != y][0]   # (the request flag's byte in bh, found by running bh_request)

    def on_sleep3(k):
        m.wall += 1; m.clock_ids[1] += 1; m.clock_ids[7] += 1
        if k == 4: m.u.mem_write(PSYMS['bh'] + flag, b'\1\0\0\0')
        if k == 19: m.fs[FILE] = b'0\n'
    m.on_sleep = on_sleep3
    m.call(PSYMS['bh_main'], count=20000000)
    sleeps = [c for c in m.calls if c[0] == 'sleep']
    expect(len(sleeps) == 19 and m.names().count('clock_gettime') == 4, f'a request after 4 s: the wait ends at once, the next sample is taken early (4 s, not 15) and a full wait follows ({len(sleeps)} sleeps, {m.names().count("clock_gettime") // 2} samples before the end)')
    # the sample count the page's timer follows: one per sample
    m = machine(); n0 = m.call(PSYMS['bh_seq'], count=200000); step(m, 0); step(m, 15)
    expect(m.call(PSYMS['bh_seq'], count=200000) == n0 + 2, 'bh_seq counts the samples')
    # Reset All Settings deletes the setting file without the switch: the thread ends the same way
    m = BM(); m.fs[FILE] = b'1\n'; m.fs[GAUGE] = b'80\n'; m.fs[STATUS] = b'Discharging\n'; m.wall = T0 + 60; m.clock_ids = {1: 1000, 7: 1000}; m.screen(True); m.play_status = 1
    m.call(PSYMS['bh_poll'], count=200000)

    def on_sleep2(k):
        m.wall += 900; m.clock_ids[1] += 900; m.clock_ids[7] += 900
        if k == 2: m.fs.pop(FILE)
    m.on_sleep = on_sleep2
    m.call(PSYMS['bh_main'], count=20000000)
    expect(DATA not in m.fs and view(m) is None, 'the setting file deleted behind our back: the thread ends and the data goes')


def settings_tests(ctx):
    """Settings > Battery > Battery History: the row on the Battery page, the page's switch, its note, the History items after it, the files and the action numbers."""
    expect, P = ctx.expect, pod_pages
    B, H = P.BATTERY_PAGE, P.BATTHIST_PAGE
    expect(P.ACT_BATTHIST == 188 and P.ACT_BATTHIST in P.SWITCH_ACTIONS and 'battery-history' in P.SETTING_FILES and FILE.rsplit('/', 1)[1] == 'battery-history'
           and P.SETTING_FILES.index('battery-history') == P.SETTING_FILES.index('battery-charge-limit') + 1 and P.ACT_BHPAGE == 190 and not hasattr(P, 'ACT_BHROW'), 'ACT 188 (a switch) and 190 (the Battery page\'s value row), listed on Settings Files')
    expect([(r.label, r.action, r.arg) for r in B.rows] == [('Battery Percentage', P.ACT_BATTPCT, 0), ('Charge Limit', P.ACT_CHGLIM, P.CHGLIMIT_PAGE_INDEX), ('Battery History', P.ACT_BHPAGE, P.BATTHIST_PAGE_INDEX)]
           and P.row_kind(B.rows[2]) == 'value' and P.ACT_BHPAGE in P.VALUE_ACTIONS and P.VALUE_INIT[P.ACT_BHPAGE] == 'Off' and not any(getattr(x, 'start_hidden', 0) for x in B.layout)
           and P.PAGES[P.BATTHIST_PAGE_INDEX] is H and H.title == 'Battery History' and P.BATTHIST_PAGE_INDEX == P.CHGLIMIT_PAGE_INDEX + 1, 'the Battery page: a Battery History value row opening its page, no hidden items')
    expect([(r.label, r.action) for r in H.rows] == [('Battery History', P.ACT_BATTHIST)] and P.row_kind(H.rows[0]) == 'switch' and H.layout[1].text == 'Keeps the last 24 hours of battery level and use. Turning it off deletes them.'
           and H.layout[2].text == 'Turning it off deletes the history.' and H.layout[1].lines == 2 and H.layout[2].lines == 1, 'the Battery History page: the switch with its two notes (off: the long one, on: the short one)')
    kinds = [type(x).__name__ + (':' + x.kind if isinstance(x, P.HistChart) else '') for x in H.layout[2:]]
    expect(kinds == ['Note', 'Hdr', 'HistSummary', 'Note', 'Hdr', 'HistChart:level', 'Hdr', 'HistChart:activity', 'Note'] and all(x.start_hidden for x in H.layout[2:]) and not any(getattr(x, 'start_hidden', 0) for x in H.layout[:2]),
           f'after the long note the short note and the History items, all hidden at the start ({kinds})')
    expect([x.text for x in H.layout[2:] if isinstance(x, P.Hdr)] == ['Since Last Charge', 'Last 24 Hours', 'Activity'] and H.layout[5].text == 'Estimated from the battery gauge.', 'the section headers and the gauge note under the card')
    import pod_i18n
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in ('Battery History', H.layout[1].text, 'Since Last Charge', 'Unplugged %s, %s', 'Unplugged %s', 'Recording since %s, %s', 'Recording since %s', 'Charging, %s', 'Charging', 'yesterday %s', '%s left', 'Last 24 Hours', 'Activity', 'Screen On', 'Playing, Screen Off', 'Standby',
                                                  '%d h %d min', '%d h', '%d min', H.layout[2].text, H.layout[5].text, H.layout[-1].text)), f'the page texts have a translation in {loc}')
    expect(not any(k in pod_i18n.TEXT for k in ('Last charged to %s', 'By Activity', 'Total on Battery', '%s an hour', 'On Battery', 'Unplugged at %s, %s', 'Unplugged at %s')), 'the strings of the old page are gone')


def sc_tests(ctx):
    """Since Last Charge: the run starts when the charger is removed, counts playing with the screen off, screen on and the total with idle and standby (the three exclusive), stands still on the charger, and outlives the ring and a reboot."""
    expect = ctx.expect
    sc = lambda v: (v['sc_play'], v['sc_on'], v['sc_total'])
    # nothing counts before a run exists: recording that starts on the charger, or with an unreadable status, has none
    for name, kw in (('on the charger', dict(status=b'Charging\n')), ('with an unreadable status', dict(status=b'Weird\n'))):
        m = machine(**kw); step(m, 0)
        for i in range(8): step(m, 15, lit=True, play=2)
        v = view(m)
        expect(v['unplug_at'] == 0 and sc(v) == (0, 0, 0) and (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle'], v['since_on']) == (0, 0, 0, 0), f'started {name}: no run yet, nothing counts')
    m = machine(); m.fs.pop(STATUS); step(m, 0); step(m, 15, lit=True)
    expect(view(m)['unplug_at'] == 0 and view(m)['since_on'] == 0, 'started with no status file: no run')
    # a status that reads later: the run begins at the first sample that says Discharging, with the last gauge reading; the time and the drop before it are not the run's
    m = machine(status=b'Weird\n', gauge=80); step(m, 0)
    for i in range(4): step(m, 15, lit=True)
    step(m, 60, lit=True, gauge=78, status=b'Discharging\n')
    v = view(m)
    expect(v['unplug_at'] == T0 + 60 + 120 and v['since_on'] == 1 and v['unplug_lvl'] == 78 and sc(v) == (0, 0, 0) and (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle']) == (0, 0, 0),
           f'the status reads Discharging after being unreadable: a run begins there ({v["unplug_at"] - T0}, {v["since_on"]}, {v["unplug_lvl"]}, {sc(v)})')
    step(m, 15, lit=True); step(m, 60, lit=False, play=2, gauge=77)
    v = view(m)
    expect(sc(v) == (60, 15, 75) and v['sc_d_play'] == 1 and v['unplug_at'] == T0 + 180, f'and counts from then on ({sc(v)}, {v["sc_d_play"]})')
    # the seconds before the run do not attribute its drops: six minutes of screen on with no status, the run begins at the same gauge, then a minute of playing with the screen off falls 1 %
    m = machine(status=b'Weird\n', gauge=80); step(m, 0)
    for i in range(6): step(m, 60, lit=True)
    step(m, 15, lit=True, status=b'Discharging\n')
    v = view(m)
    expect(v['since_on'] == 1 and v['unplug_lvl'] == 80 and sc(v) == (0, 0, 0), f'the run begins with the gauge unchanged ({v["unplug_lvl"]}, {sc(v)})')
    step(m, 60, lit=False, play=2, gauge=79)
    v = view(m)
    expect(sc(v) == (60, 0, 60) and (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle']) == (0, 1, 0), f'its drop is the playing\'s, not the screen\'s of before the run ({sc(v)}, {(v["sc_d_on"], v["sc_d_play"], v["sc_d_idle"])})')
    m = machine(status=b'Weird\n'); step(m, 0); step(m, 15, lit=True); step(m, 15, status=b'Charging\n'); step(m, 15, status=b'Discharging\n')
    expect(view(m)['since_on'] == 0 and view(m)['unplug_at'] == T0 + 60 + 45, 'unreadable, then the charger, then battery: the charger\'s removal begins the run')
    m = machine(status=b'Charging\n'); step(m, 0)
    for g in (79, 78, 77): step(m, 60, lit=True, gauge=g)
    expect(view(m)['unplug_at'] == 0 and view(m)['sc_d_on'] == 0, 'drops on external power are not counted')
    # recording started on battery: the first sample starts a run (since_on 1, the gauge then)
    m = machine(gauge=80); step(m, 0)
    v = view(m)
    expect(v['unplug_at'] == m.wall and v['unplug_lvl'] == 80 and v['since_on'] == 1 and sc(v) == (0, 0, 0) and (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle']) == (0, 0, 0), f'started on battery: a run from the first sample ({v["unplug_at"]}, {v["unplug_lvl"]}, {v["since_on"]})')
    # drops since the run began land where the bucket's drops do
    for g in (79, 78): step(m, 60, lit=True, gauge=g)
    step(m, 60, lit=False, play=2, gauge=78); step(m, 60, lit=False, play=2, gauge=77)
    for g in (77, 77, 77, 76): step(m, 60, lit=False, play=1, gauge=g)
    v = view(m)
    dd = (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle'])
    expect(dd[0] == 2 and dd[1] + dd[2] == 2 and sum(dd) == 4 and (v['d_on'], v['d_play'], v['d_idle']) == dd and v['since_on'] == 1, f'the run\'s drops are the buckets\' ({dd}, since_on {v["since_on"]})')
    # the charger on, off: a new run, the drops zeroed, since_on 0
    step(m, 60, status=b'Charging\n', gauge=90); step(m, 60, lit=True, gauge=89)
    expect(tuple(view(m)[k] for k in ('sc_d_on', 'sc_d_play', 'sc_d_idle')) == dd, 'on external power the drops stand still')
    step(m, 60, lit=True, status=b'Discharging\n', gauge=88)
    v = view(m)
    expect(v['since_on'] == 0 and v['unplug_at'] == m.wall and (v['sc_d_on'], v['sc_d_play'], v['sc_d_idle']) == (0, 0, 0), 'the charger removed: a new run, since_on 0, drops 0')
    step(m, 60, lit=True, gauge=87)
    expect(view(m)['sc_d_on'] == 1, 'and it counts the drop after it')
    # they are saved and read back
    for i in range(8): step(m, 300, lit=True, gauge=87)
    saved = m.fs[DATA]; v = view(m)
    expect(struct.unpack_from('<4I', saved, 32) == (1, 0, 0, 0) and len(saved) == FILE_SIZE, 'the file holds the drops and since_on')
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
    m2.wall = (v['head'] + 1) * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    v2 = view(m2)
    expect((v2['sc_d_on'], v2['sc_d_play'], v2['sc_d_idle'], v2['since_on']) == (1, 0, 0, 0) and v2['unplug_at'] == v['unplug_at'], 'a reboot keeps the run and its drops; the new baseline starts no other')
    # a since_on run round-trips too, and a reboot keeps it
    m = machine(gauge=60); step(m, 0)
    for g in (59, 59): step(m, 60, lit=True, gauge=g)
    for i in range(8): step(m, 300, lit=False, play=1, gauge=59)
    saved = m.fs[DATA]; v = view(m)
    expect(struct.unpack_from('<4I', saved, 32)[3] == 1 and struct.unpack_from('<I', saved, 12)[0] == T0 + 60, 'since_on 1 in the file')
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'50\n', STATUS: b'Discharging\n'}
    m2.wall = (v['head'] + 1) * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    v2 = view(m2)
    expect(v2['since_on'] == 1 and v2['unplug_at'] == T0 + 60 and v2['unplug_lvl'] == 60 and v2['sc_d_on'] == 1, f'a reboot keeps a since_on run as it was ({v2["since_on"]}, {v2["unplug_at"]})')
    # the charger removed: a new run, counters 0, the time and the level noted; this step's time is still the charger's
    m = machine(gauge=77, status=b'Charging\n'); step(m, 0)
    for i in range(4): step(m, 15, lit=True, play=2)
    expect(view(m)['unplug_at'] == 0 and sc(view(m)) == (0, 0, 0), 'on the charger: nothing counts')
    step(m, 15, lit=True, play=2, status=b'Discharging\n')
    v = view(m)
    expect(v['unplug_at'] == m.wall and v['unplug_lvl'] == 77 and v['level'] == 77 and sc(v) == (0, 0, 0), f'unplugged: unplug_at is the sample\'s wall time, the gauge 77 ({v["unplug_at"]}, {v["unplug_lvl"]})')
    # the states: screen on, playing with the screen off, both, idle, standby
    step(m, 60, lit=True, play=1)
    expect(sc(view(m)) == (0, 60, 60), 'screen on, not playing: on and total')
    step(m, 60, lit=False, play=2)
    expect(sc(view(m)) == (60, 60, 120), 'playing with the screen off: play and total')
    step(m, 60, lit=True, play=2)
    expect(sc(view(m)) == (60, 120, 180), 'playing with the screen on: the screen on wins, as in the bucket (never both)')
    step(m, 60, lit=False, play=1)
    expect(sc(view(m)) == (60, 120, 240), 'idle: the total only')
    step(m, 1800, dmono=15, dboot=1800, lit=False, play=1)
    expect(sc(view(m)) == (60, 120, 240 + 1800), 'standby (15 s awake, the rest suspended): all of it in the total, none in play or screen on')
    # on the charger again the counters stand still, with the screen on and playing; a second unplug starts over
    step(m, 60, lit=True, play=2, status=b'Charging\n')
    step(m, 600, lit=True, play=2); step(m, 1800, dmono=15, dboot=1800, lit=False, gauge=100)
    v = view(m)
    expect(sc(v) == (60, 120, 240 + 1800) and v['unplug_lvl'] == 77, f'charging: frozen ({sc(v)})')
    t = m.wall
    step(m, 15, status=b'Discharging\n')
    step(m, 15, lit=True, play=2)
    v = view(m)
    expect(v['unplug_at'] == t + 15 and sc(v) == (0, 15, 15) and v['unplug_lvl'] == 100, f'unplugged again: a new run ({sc(v)}, {v["unplug_lvl"]})')
    # an unreadable status keeps the answer: no new run from a status that fails to read
    m.fs.pop(STATUS); step(m, 60, lit=True)
    expect(sc(view(m)) == (0, 75, 75), 'no status file: still on battery, still counting')
    # the run outlives the 24 hour ring and a ring dropped by a clock set back
    m = machine(status=b'Charging\n'); step(m, 0); step(m, 15, status=b'Discharging\n')
    for i in range(100): step(m, 900, lit=True, play=2)
    v = view(m)
    expect(sc(v) == (0, 900 * 100, 900 * 100) and v['unplug_at'] == T0 + 75 and v['b'][0][1] & GAP == 0, f'more than 24 hours: {sc(v)} s, the ring holds only the last 96 buckets')
    step(m, -7200, dmono=15)
    v = view(m)
    expect(len(real(v)) == 1 and sc(v) == (0, 900 * 100, 900 * 100), 'a clock set back drops the ring but not the counters (seconds, not wall time)')
    # and its file reads back after a reboot: the unplug time is then after the newest bucket, which is no reason to drop the file
    m = machine(status=b'Charging\n'); step(m, 0); step(m, 15, status=b'Discharging\n')
    for i in range(4): step(m, 300, lit=True)
    step(m, -7200, dmono=15)
    for i in range(4): step(m, 300, lit=True)
    saved, head = m.fs[DATA], view(m)['head']
    expect(struct.unpack_from('<I', saved, 12)[0] == T0 + 75 and struct.unpack_from('<I', saved, 12)[0] > (head + 1) * SECS, 'the file of a clock set back before the unplug: unplug_at after the head')
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
    m2.wall = (head + 1) * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(False); m2.play_status = 1
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    v2 = view(m2)
    expect(v2['unplug_at'] == T0 + 75 and sc(v2) == (struct.unpack_from('<I', saved, 20)[0], struct.unpack_from('<I', saved, 24)[0], struct.unpack_from('<I', saved, 28)[0]) and v2['sc_total'] > 0,
           f'and a reboot keeps the counters ({sc(v2)})')
    # the file: a reboot reads them back (as of the last bucket opened), a power loss costs up to 15 minutes of them
    m = machine(status=b'Charging\n'); step(m, 0); step(m, 15, status=b'Discharging\n')
    for i in range(1, 8): step(m, 300, lit=True, play=2)
    saved = m.fs[DATA]
    v = view(m)
    expect(struct.unpack_from('<I', saved, 12)[0] == T0 + 75 and struct.unpack_from('<I', saved, 16)[0] == 80 and 0 < struct.unpack_from('<I', saved, 28)[0] <= v['sc_total'] and len(saved) == FILE_SIZE,
           'the file holds the run (written when a bucket opened, so up to 15 minutes behind)')
    head = v['head']
    m2 = BM(); m2.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'70\n', STATUS: b'Discharging\n'}
    m2.wall = (head + 6) * SECS + 100; m2.clock_ids = {1: 7, 7: 7}; m2.screen(True); m2.play_status = 2
    m2.call(PSYMS['bh_poll'], count=200000); m2.call(PSYMS['bh_load'], count=2000000); step(m2, 0)
    v2 = view(m2)
    expect(sc(v2) == (struct.unpack_from('<I', saved, 20)[0], struct.unpack_from('<I', saved, 24)[0], struct.unpack_from('<I', saved, 28)[0]) and v2['unplug_at'] == T0 + 75,
           'after a reboot (an hour and a half later): the file\'s counters, the time the player was off is not counted')
    step(m2, 60, lit=False, play=2)
    expect(view(m2)['sc_total'] == v2['sc_total'] + 60 and view(m2)['sc_play'] == v2['sc_play'] + 60, 'and it counts on from there')
    # a reboot on the charger and an unplug after it starts a new run
    m3 = BM(); m3.fs = {FILE: b'1\n', DATA: saved, GAUGE: b'60\n', STATUS: b'Charging\n'}
    m3.wall = (head + 6) * SECS + 100; m3.clock_ids = {1: 7, 7: 7}; m3.screen(False); m3.play_status = 1
    m3.call(PSYMS['bh_poll'], count=200000); m3.call(PSYMS['bh_load'], count=2000000); step(m3, 0); step(m3, 60)
    expect(view(m3)['sc_total'] == v2['sc_total'] - 0 and view(m3)['unplug_at'] == T0 + 75, 'a reboot on the charger keeps the old run, frozen')
    step(m3, 15, status=b'Discharging\n')
    expect(view(m3)['unplug_at'] == m3.wall and sc(view(m3)) == (0, 0, 0), 'and the unplug starts a new one')
    # the setting off deletes the run with the rest
    m.call(PSYMS['bh_toggle'], count=4000000); m.call(PSYMS['bh_toggle'], count=4000000); step(m, 0)
    expect(view(m)['unplug_at'] == m.wall and view(m)['since_on'] == 1 and sc(view(m)) == (0, 0, 0), 'the setting off and on again: the old run is gone, a new one starts on battery')


# ---- the History page (patch/bhpage.c, tools/batthist_model.py)
HEAD = T0 // SECS + 3          # 08:45 UTC
NAMES = ('pod_sec0 pod_sec1 pod_sec2 pod_note0 pod_note1 pod_note2 pod_note3 pod_hist0 pod_hist1 pod_hist2 pod_hs_cap pod_hs_dur pod_hs_left pod_hs_d0 pod_hs_d1 pod_hs_d2 pod_hs_p0 pod_hs_p1 pod_hs_p2 '
         'pod_ha_a0 pod_ha_a1 pod_ha_a2 ' + ' '.join(f'pod_h{k}_t{i}' for k in 'la' for i in range(4))).split()
ITEMS = 'pod_note0 pod_note1 pod_sec0 pod_hist0 pod_note2 pod_sec1 pod_hist1 pod_sec2 pod_hist2 pod_note3'.split()
SC = {'pod_sec0', 'pod_hist0', 'pod_note2'}   # the Since Last Charge header, card and its note: only with an unplug_at
SHOWN = {'off': {'pod_note0'}, 'empty': {'pod_note1', 'pod_note3'}, 'data': set(ITEMS) - {'pod_note0', 'pod_note3'} - SC}
DEMO_SC = (HEAD * SECS - 100000, 100, 3 * 3600 + 53 * 60, 2 * 3600 + 12 * 60, 31 * 3600 + 20 * 60, 6, 12, 10, 0)   # unplug_at, unplug_lvl, sc_play, sc_on, sc_total, sc_d_on, sc_d_play, sc_d_idle, since_on
ON_PX, PLAY_PX, STBY_PX, CARD_PX = 0xffe6e6e6, 0xff7c7878, 0xff5c5858, 0xff1e1c1c   # (alpha, blue, green, red)


def u8(s): return s.encode('latin-1').decode('utf-8')


def fake_ring():
    """96 buckets oldest first (tuples of struct bh_bucket): a gap run at the start, a discharge with screen and playing time, a middle gap, a charge, a discharge down below 20 %, an unknown level, the open bucket."""
    b = []
    for i in range(96):
        if i < 8 or i in (20, 21): b.append((NONE, GAP, 0, 0, 0, 0, 0, 0)); continue
        if 40 <= i < 56: lev, fl = 40 + (i - 40) * 4, CHG
        elif i < 40: lev, fl = 95 - (i - 8), 0
        else: lev, fl = max(8, 99 - 3 * (i - 56)), 0
        on, play = (i * 7) % 60, (i * 3) % 30
        b.append((NONE if i == 70 else lev, fl, on, play, on + play + 10, i % 3, i % 2, (i + 1) % 2))
    return b


def file_bytes(buckets, head, sc=(0, NONE, 0, 0, 0, 0, 0, 0, 0)):
    """sc: unplug_at, unplug_lvl, sc_play, sc_on, sc_total, sc_d_on, sc_d_play, sc_d_idle, since_on."""
    ring = bytearray(8 * N)
    for i, k in enumerate(buckets):
        pos = 8 * ((head - (N - 1) + i) % N)
        ring[pos:pos + 8] = bytes(k)
    sc = tuple(sc) + (0,) * (9 - len(sc))
    f = bytearray(b'BHS1') + struct.pack('<HHI10I', 4, N, head, *sc, 0) + ring
    sm = (head * 2654435761 + sc[0] * 31 + sc[1] + sc[2] * 7 + sc[3] * 13 + sc[4] * 17 + sc[5] * 19 + sc[6] * 23 + sc[7] * 29 + sc[8] * 37) & 0xffffffff
    for x in f[HDR:]: sm = (sm * 31 + x) & 0xffffffff
    struct.pack_into('<I', f, 48, sm)
    return bytes(f)


def page(buckets=None, tz=0, h24=1, on=True, sc=(0, NONE, 0, 0, 0), head=HEAD):
    """The player with the setting on and a ring read from a file, the Battery History page's widgets registered, bhpage_show run once."""
    buckets = fake_ring() if buckets is None else buckets
    m = BM(); m.fs = {GAUGE: b'70\n', STATUS: b'Discharging\n'}
    if on: m.fs[FILE] = b'1\n'; m.fs[DATA] = file_bytes(buckets, head, sc)
    m.wall = head * SECS + 100; m.clock_ids = {1: 7, 7: 7}; m.tz = tz; m.screen(False); m.play_status = 1
    m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([h24]))
    m.call(PSYMS['bh_poll'], count=200000); m.call(PSYMS['bh_load'], count=2000000)
    for n in NAMES: m.widget(n)
    m.win = m.alloc(0x80)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    m.shown_calls = list(m.calls)   # (a later call of the machine starts its own list)
    return m


def local5(t, tz):
    """The local (year, month, day, hour, minute) of the wall time t in a zone tz seconds ahead of UTC."""
    g = _time.gmtime(t + tz)
    return g.tm_year, g.tm_mon, g.tm_mday, g.tm_hour, g.tm_min


def shown(m): return {n for n in ITEMS if m.props.get((m.widgets[n], 'visible')) == 1}
def texts(m, name): return [u8(c[2]) for c in m.shown_calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[name]]
def bmp(m, k):
    """The bitmap k (0 the Since Last Charge card, 1 the level chart, 2 the activity chart) in the order they were made; the card's only exists with an unplug_at."""
    got = sorted(m.bitmaps.items())   # (by handle: the order they were made)
    b, (data, w, h) = got[k - (3 - len(got))]
    return b, w, h, struct.unpack(f'<{w * h}I', m.u.mem_read(data, w * h * 4))
def off_pixels(px, w, h, model):
    return [(x, y) for y in range(h) for x in range(w) if any(abs(a - c) > 1 for a, c in zip((px[y * w + x] >> 24, px[y * w + x] & 255, px[y * w + x] >> 8 & 255, px[y * w + x] >> 16 & 255), model[y][x]))]


def history_tests(ctx):
    """The bitmaps against the model: charging bars green, a level of 20 % or less red, gaps blank, the charger's band, the stacked activity, the card's corners, the Since Last Charge card's bar and marks."""
    expect = ctx.expect
    m = page(sc=DEMO_SC)
    ring = fake_ring()
    expect(shown(m) == SHOWN['data'] | SC, f'a ring with closed buckets and an unplug: every item but the long note and the empty note shows ({sorted(shown(m) ^ (SHOWN["data"] | SC))})')
    expect([c for c in m.calls if c[0] == 'bitmap_create_ex'] == [('bitmap_create_ex', 300, HM.SCARD), ('bitmap_create_ex', 300, 150), ('bitmap_create_ex', 300, 150)] and len(m.bitmaps) == 3, 'three bitmaps: the card 300 x 292, the two charts 300 x 150')
    (b2, w2, h2, px2), (b0, w0, h0, px0), (b1, w1, h1, px1) = bmp(m, 0), bmp(m, 1), bmp(m, 2)
    v = view(m)
    expect(v['b'] == ring and len(v['b']) == 96, 'the view is the ring that was read')
    bad = off_pixels(px2, w2, h2, HM.render_summary(DEMO_SC[3], DEMO_SC[2], DEMO_SC[4]))
    expect(not bad, f'the Since Last Charge card is the model\'s pixel for pixel ({len(bad)} differ: {bad[:3]})')
    bad = off_pixels(px0, w0, h0, HM.render_level(ring, HEAD, 0))
    expect(not bad, f'the level chart is the model\'s pixel for pixel ({len(bad)} differ: {bad[:3]})')
    bad = off_pixels(px1, w1, h1, HM.render_activity(ring, HEAD, 0))
    expect(not bad, f'the activity chart is the model\'s pixel for pixel ({len(bad)} differ: {bad[:3]})')
    # the card: the bar split by the seconds, the marks, the hairlines
    expect((HM.SROW_H, HM.SCARD, HM.OFF['BHS_H'], HM.SMARK_CY, HM.OFF['BHS_SUB_CY'], HM.OFF['BHS_PCT_CY']) == (60, 292, 302, 20, 42, 30), 'the card: 60 px rows, 292 high in a 302 px item, mark and name on 20, duration on 42, percent on 30')
    e1, e2 = HM.bar_edges(DEMO_SC[3], DEMO_SC[2], DEMO_SC[4])
    by = HM.SBAR_Y + HM.SBAR_H // 2
    expect(e1 == (276 * 7920 + 56400) // 112800 and e2 == (276 * (7920 + 13980) + 56400) // 112800 and 0 < e1 < e2 < 276, f'the bar\'s edges: screen on {e1} px, playing {e2 - e1} px, the rest standby ({e1}, {e2})')
    row = lambda x: px2[by * 300 + HM.SPAD + x]
    expect(row(e1 - 1) == ON_PX and row(e1) == PLAY_PX and row(e2 - 1) == PLAY_PX and row(e2) == STBY_PX and row(2) == ON_PX and row(270) == STBY_PX, 'the bar: screen on, playing with the screen off, standby, left to right')
    expect(px2[HM.SBAR_Y * 300 + HM.SPAD] == CARD_PX and px2[(HM.SBAR_Y + 9) * 300 + HM.SPAD + 275] == CARD_PX and px2[by * 300 + HM.SPAD - 1] == CARD_PX, 'the bar\'s ends are rounded (its corners are the card\'s)')
    for k, want in enumerate((ON_PX, PLAY_PX, STBY_PX)):
        cy = HM.SROW0 + HM.SROW_H * k + 20   # on the name's line, not the row's middle
        expect(px2[cy * 300 + HM.SMARK_X + 5] == want and px2[(cy - 5) * 300 + HM.SMARK_X] == CARD_PX and px2[(cy - 5) * 300 + HM.SMARK_X + 5] == want, f'row {k}: a 10 px mark of the kind\'s colour with rounded corners')
        expect(px2[(HM.SROW0 + HM.SROW_H * k + 30) * 300 + HM.SMARK_X + 5] == CARD_PX, f'row {k}: nothing at the row\'s middle (the mark is on the name\'s line)')
        expect(px2[(HM.SROW0 + HM.SROW_H * k) * 300 + 100] == (0xff333333 if k else CARD_PX), f'row {k}: {"a hairline above it" if k else "no hairline above the first"}')
    z = [HM.bar_edges(0, 0, 0), HM.bar_edges(10, 20, 30), HM.bar_edges(9 << 20, 3 << 20, 18 << 20)]
    expect(z == [(0, 0), (92, 276), (138, 184)], f'the bar\'s edges: no time, all of it; a long run is scaled before it is divided ({z})')
    cols = {c for c in (px0[y * 300 + x] for y in range(HM.LPY0, HM.LPY0 + HM.LPH) for x in range(300))}
    GREEN, RED, GREY = 0xff59c734, 0xff4814ff, 0xffa5a5a5
    expect({GREEN, RED, GREY} <= cols, 'the level chart has green (charging), red (20 % or less) and grey bars')
    bars = HM.level_bars(ring)
    for j, bar in enumerate(bars):
        c = px0[(HM.LPY0 + HM.LPH - 1) * 300 + HM.PX0 + HM.LPITCH * j + 1]
        want = None if not bar or bar[0] == 0 else GREEN if bar[1] else RED if bar[0] <= 20 else GREY
        expect(want is None and c not in (GREEN, RED, GREY) or c == want, f'bar {j} ({bar}): the bottom row is {c:#x}, wanted {want}')
    expect(bars[0] is None and bars[3] is None and bars[10] is None and bars[4] and bars[35] and bars[24][1] and not bars[40][1] and bars[47][0] <= 20, 'gaps have no bar; the charging bars are marked; the last is low')
    gap = [px0[(HM.LPY0 + HM.LPH - 1) * 300 + HM.PX0 + HM.LPITCH * j + 1] for j in range(4)]
    expect(all(g >> 24 == 255 and g & 255 <= 62 for g in gap), 'a bar with no data (gap buckets) leaves the plot empty: the dotted baseline at most')
    # the charger's band (activity chart only): #2A2A2C behind the bars of the buckets 40 .. 55, the plot's height, not below the axis, none elsewhere; the level chart has none (its green bars say it)
    BANDPX = 0xff2c2a2a
    gapx = lambda i: HM.PX0 + 10 * (i // 4) + 9   # a column between two hourly bars, inside bucket i
    ap = lambda x, y: px1[y * 300 + x]
    expect(BANDPX not in set(px0), 'the level chart has no band')
    expect(ap(gapx(44), HM.APY0) == BANDPX and ap(gapx(44), HM.APY0 + HM.APH - 1) == BANDPX and ap(gapx(39), HM.APY0 + 1) == CARD_PX and ap(gapx(56), HM.APY0 + 1) == CARD_PX and ap(gapx(36), HM.APY0 + 1) == CARD_PX,
           'the activity chart: a faint band behind the charging hours only, the plot\'s full height')
    expect(ap(gapx(44), HM.APY0 + HM.APH + 1) == CARD_PX and ap(gapx(44), HM.APY0 - 1) == CARD_PX, 'the band spans the plot height: nothing below the axis, nothing above the top line')
    expect(ap(HM.tick_x(40), HM.APY0 + 1) != CARD_PX and ap(HM.tick_x(40) - 1, HM.APY0 + 1) == CARD_PX and ap(HM.tick_x(56) - 1, HM.APY0 + 1) in (BANDPX, 0xff1e1c1c) and ap(gapx(55), HM.APY0 + 1) == BANDPX,
           'the band starts at the first charging bucket\'s left edge and ends at the last one\'s right edge')
    expect(GREEN not in set(px1) and px1[(HM.APY0 + 1) * 300 + HM.PX0 + 119] == BANDPX and px1[(HM.APY0 + 1) * 300 + HM.PX0 + 99] == CARD_PX, 'the activity chart has the same band between its bars (no green)')
    # corners
    expect(px0[0] >> 24 == 0 and px0[299] >> 24 == 0 and px0[139 * 300] >> 24 == 0 and px0[140 * 300] == 0 and px0[70 * 300] >> 24 == 255 and px0[70 * 300] == 0xff1e1c1c, 'the card: four corners cut in the alpha, the surface #1C1C1E, nothing under it')
    # stacked activity: light at the bottom, mid grey above it, never taller than the plot
    st = HM.activity_bars(ring)
    for mth, (on, play) in enumerate(st):
        x = HM.PX0 + HM.APITCH * mth + 3
        col = [px1[y * 300 + x] for y in range(HM.APY0, HM.APY0 + HM.APH)]
        n_on, n_play = col.count(ON_PX), col.count(PLAY_PX)
        want_on = (on * HM.APH + 1800) // 3600
        expect(n_on == want_on and n_play == min((play * HM.APH + 1800) // 3600, HM.APH - want_on), f'hour {mth}: {n_on} rows of screen on and {n_play} of playing (wanted {want_on})')
        if on and play and n_on and n_play:
            ys = [y for y in range(HM.APY0, HM.APY0 + HM.APH) if px1[y * 300 + x] in (ON_PX, PLAY_PX)]
            expect(px1[ys[-1] * 300 + x] == ON_PX and px1[ys[0] * 300 + x] == PLAY_PX, f'hour {mth}: playing is stacked on the screen on')
    expect(px1[HM.ALEG * 300 + 19] == ON_PX and px1[HM.ALEG * 300 + 129] == PLAY_PX and px1[(HM.ALEG - 5) * 300 + 14] == 0 and px1[(HM.ALEG - 5) * 300 + 124] == 0 and px1[(HM.ALEG - 5) * 300 + 19] == ON_PX,
           'the legend\'s two marks (under the card, on the page): 10 px, rounded corners, the colours of the bar')
    # painted by one blit each in the views' before-paint, the bitmaps leave with the window
    canvas, ev = m.alloc(0x100), m.alloc(0x40)
    m.setword(ev + O['EVENT_PAINT_CANVAS'], canvas)
    for name, b, h in (('pod_hist0', b2, HM.SCARD), ('pod_hist1', b0, 150), ('pod_hist2', b1, 150)):
        fn, c = m.bound[(m.widgets[name], O['EVT_BEFORE_PAINT'])]
        m.blits.clear(); m.calls = []
        m.call(fn, a0=c, a1=ev, count=1 << 22)
        expect(m.blits == [(b, (0, 0, 300, h), (10, 0, 300, h))] and m.names() == ['canvas_draw_image'], f'{name}: one blit of the whole bitmap at the card\'s x ({m.blits})')
    m.calls = []; m.call(fn, a0=c, a1=0, count=1 << 22)
    expect(m.names() == [], 'an event without a canvas paints nothing')
    fn, c = m.bound[(m.win, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 22)
    expect(not m.bitmaps and not [x for x in m.bound if x[1] == O['EVT_SCROLL']] and not m.timers, 'destroy: the bitmaps go; no timer and no scroll handler')
    m.blits.clear(); fn, c = m.bound[(m.widgets['pod_hist1'], O['EVT_BEFORE_PAINT'])]; m.call(fn, a0=c, a1=ev, count=1 << 22)
    expect(not m.blits, 'a paint after the destroy draws nothing')
    m = page()
    expect(len(m.bitmaps) == 2 and shown(m) == SHOWN['data'], 'no unplug_at: the card has no bitmap and its items stay hidden')


def texts_tests(ctx):
    """The labels: ticks in local time across zones and both clocks (the same text on both charts), the Since Last Charge card's texts (the caption's day word, Recording since, the percents), the axis, the notes."""
    expect = ctx.expect
    for tz, h24 in ((0, 1), (19800, 1), (-12600, 0), (3600 * 9, 0)):
        m = page(tz=tz, h24=h24)
        tk = HM.ticks(HEAD, tz)
        expect(len(tk) == 4 and all(h % 6 == 0 for _, h in tk), f'tz {tz}: four ticks, at local multiples of six hours ({tk})')
        for k, chart in ((0, 'level'), (1, 'activity')):
            name = 'la'[k]
            got = [(texts(m, f'pod_h{name}_t{i}'), [(c[2], c[3]) for c in m.shown_calls if c[0] == 'widget_move' and c[1] == m.widgets[f'pod_h{name}_t{i}']]) for i in range(4)]
            want = [([HM.hour_text(h, h24)], [(10 + 12 + 5 * i // 2 - 22, (128 if k == 0 else 104) - 9)]) for i, h in tk]
            expect(got == want, f'tz {tz}, {"24" if h24 else "12"} h, {chart} chart: the labels and their places ({got[:2]})')
    m = page()
    expect([texts(m, f'pod_ha_t{i}') for i in range(4)] == [texts(m, f'pod_hl_t{i}') for i in range(4)] and texts(m, 'pod_hl_t0')[0].endswith(':00'), 'the activity chart\'s hour ticks read as the level chart\'s ("18:00")')
    expect(texts(m, 'pod_ha_a0') == ['60 min'] and texts(m, 'pod_ha_a1') == ['30 min'] and texts(m, 'pod_ha_a2') == ['0'], 'the activity axis: 60 min, 30 min, 0')
    face = lambda mm, w: mm.props.get((mm.widgets[w], 'style:normal:font_name'))
    # Since Last Charge: hidden without an unplug_at, else the card's texts (the caption, the total, the percent left, the three durations and percents)
    names = ('pod_hs_cap', 'pod_hs_dur', 'pod_hs_left', 'pod_hs_d0', 'pod_hs_d1', 'pod_hs_d2', 'pod_hs_p0', 'pod_hs_p1', 'pod_hs_p2')
    expect(not SC & shown(m) and not any(texts(m, n) for n in names), 'no unplug_at: the Since Last Charge section is hidden and nothing is written to it')
    unplug = HEAD * SECS - 100000
    for tz, h24, lvl in ((0, 1, 82), (19800, 1, 100), (-12600, 0, 5), (3600 * 9, 0, 255)):
        mm = page(tz=tz, h24=h24, sc=(unplug, lvl, 5 * 3600 + 12 * 60, 3 * 3600 + 30 * 60, 30 * 3600 + 29 * 60 + 29, 3, 5, 7, 0))
        v = view(mm)
        now = HEAD * SECS + 100
        cap = HM.caption_text(HM.when_text(local5(unplug, tz), local5(now, tz), h24), lvl, 0)
        expect(SC <= shown(mm) and shown(mm) == set(ITEMS) - {'pod_note0', 'pod_note3'} and texts(mm, 'pod_hs_cap') == [cap] and cap.startswith('Unplugged yesterday '), f'tz {tz}, {"24" if h24 else "12"} h, level {lvl}: the card shows with "{cap}" ({texts(mm, "pod_hs_cap")})')
        left = [f'{v["level"]}% left'] if v['level'] <= 100 else []
        expect(texts(mm, 'pod_hs_left') == (left or ['']) and v['level'] == 8, f'the percent left is the gauge now ({texts(mm, "pod_hs_left")})')
    expect([texts(mm, n) for n in ('pod_hs_dur', 'pod_hs_d0', 'pod_hs_d1', 'pod_hs_d2')] == [['30 h 29 min'], ['3 h 30 min'], ['5 h 12 min'], ['21 h 47 min']],
           f'the total 30 h 29 min, Screen On 3 h 30 min, Playing 5 h 12 min, Standby the rest 21 h 47 min (rounded to the minute) ({[texts(mm, n) for n in ("pod_hs_dur", "pod_hs_d0", "pod_hs_d1", "pod_hs_d2")]})')
    expect([texts(mm, f'pod_hs_p{k}') for k in range(3)] == [['~3%'], ['~5%'], ['~7%']], 'the percents the gauge fell, per kind, from the run')
    expect(face(mm, 'pod_hs_dur') == 'lyrics' and face(mm, 'pod_hs_cap') is None and all(face(mm, f'pod_hs_p{k}') == 'lyrics' for k in range(3)) and all(face(mm, f'pod_hs_d{k}') is None for k in range(3)),
           'the total and the percents are in the bold face, the caption and the durations are not')
    # the caption's time: the clock the same day, "yesterday" with the clock the day before, MM-DD and the clock before that; Recording since when the run began with the recording; no level when unknown
    now = HEAD * SECS + 100   # 2027-01-15 08:46 UTC
    for tz, h24, ago, want in ((0, 1, 3 * 3600, 'Unplugged 05:46, 100%'), (0, 1, 8 * 3600 + 46 * 60, 'Unplugged 00:00, 100%'), (0, 1, 8 * 3600 + 47 * 60, 'Unplugged yesterday 23:59, 100%'), (0, 0, 8 * 3600 + 47 * 60, 'Unplugged yesterday 11:59 PM, 100%'),
                               (0, 1, 32 * 3600 + 46 * 60, 'Unplugged yesterday 00:00, 100%'),
                               (0, 1, 32 * 3600 + 47 * 60, 'Unplugged 01-13 23:59, 100%'), (0, 0, 3 * 86400, 'Unplugged 01-12 8:46 AM, 100%'), (19800, 1, 3 * 3600, 'Unplugged 11:16, 100%'),
                               (-12600, 1, 5 * 3600 + 16 * 60, 'Unplugged 00:00, 100%'), (-12600, 1, 5 * 3600 + 17 * 60, 'Unplugged yesterday 23:59, 100%'), (0, 1, 400 * 86400, 'Unplugged 12-11 08:46, 100%')):
        mm = page(tz=tz, h24=h24, sc=(now - ago, 100, 0, 0, 3600, 0, 0, 0, 0))
        expect(texts(mm, 'pod_hs_cap') == [want], f'tz {tz}, {ago} s ago: "{want}" ({texts(mm, "pod_hs_cap")})')
        expect(texts(mm, 'pod_hs_cap') == [HM.caption_text(HM.when_text(local5(now - ago, tz), local5(now, tz), h24), 100, 0)], f'the model says the same ({want})')
    # across a month and a year boundary: 2027-01-01 00:16 UTC, the day before is Dec 31
    nyh = calendar.timegm((2027, 1, 1, 0, 15, 0)) // SECS
    ny = nyh * SECS + 100
    for ago, want in ((5 * 60, 'Unplugged 00:11, 100%'), (17 * 60, 'Unplugged yesterday 23:59, 100%'), (86400 + 17 * 60, 'Unplugged 12-30 23:59, 100%'), (-86400, 'Unplugged 01-02 00:16, 100%')):
        mm = page(sc=(ny - ago, 100, 0, 0, 3600, 0, 0, 0, 0), head=nyh)
        expect(texts(mm, 'pod_hs_cap') == [want], f'across the year end, {ago} s ago: "{want}" ({texts(mm, "pod_hs_cap")})')
    # a day with a DST step (New York, 2026-11-01: 25 hours, EDT until 06:00 UTC, then EST): the day before is still "yesterday", in the morning and in the evening; and the 23 hour day (2027-03-14)
    for step_at, before, after, cases in ((calendar.timegm((2026, 11, 1, 6, 0, 0)), -4, -5, (((2026, 11, 1, 15, 0, 0), (2026, 11, 1, 1, 25, 0), 'Unplugged yesterday 21:25, 100%'), ((2026, 11, 1, 6, 30, 0), (2026, 10, 31, 4, 0, 0), 'Unplugged yesterday 00:00, 100%'),
                                                                                             ((2026, 11, 2, 4, 45, 0), (2026, 11, 1, 4, 30, 0), 'Unplugged 00:30, 100%'), ((2026, 11, 2, 5, 15, 0), (2026, 11, 2, 4, 30, 0), 'Unplugged yesterday 23:30, 100%'))),
                                          (calendar.timegm((2027, 3, 14, 7, 0, 0)), -5, -4, (((2027, 3, 14, 15, 0, 0), (2027, 3, 14, 2, 25, 0), 'Unplugged yesterday 21:25, 100%'), ((2027, 3, 15, 3, 45, 0), (2027, 3, 14, 5, 30, 0), 'Unplugged 00:30, 100%'),
                                                                                            ((2027, 3, 15, 4, 15, 0), (2027, 3, 13, 5, 0, 0), 'Unplugged 03-13 00:00, 100%')))):
        zone = lambda t, s=step_at, b=before, a=after: (b if t < s else a) * 3600
        for at, unplugged, want in cases:
            h = calendar.timegm(at) // SECS
            mm = page(tz=zone, sc=(calendar.timegm(unplugged), 100, 0, 0, 3600, 0, 0, 0, 0), head=h)
            expect(texts(mm, 'pod_hs_cap') == [want], f'DST step {before} to {after}, {at[1:5]} UTC: "{want}" ({texts(mm, "pod_hs_cap")})')
    mm = page(sc=(now - 3 * 3600, 85, 0, 0, 3 * 3600, 0, 0, 0, 1))
    expect(texts(mm, 'pod_hs_cap') == ['Recording since 05:46, 85%'] and texts(mm, 'pod_hs_cap') == [HM.caption_text('05:46', 85, 1)], 'a run that began with the recording: "Recording since 05:46, 85%"')
    mm = page(sc=(now - 100000, 85, 0, 0, 3 * 3600, 0, 0, 0, 1))
    expect(texts(mm, 'pod_hs_cap') == ['Recording since yesterday 05:00, 85%'], f'and yesterday ({texts(mm, "pod_hs_cap")})')
    ring = fake_ring()[:-1] + [(NONE, 0, 0, 0, 0, 0, 0, 0)]
    for since_on, want in ((0, 'Unplugged yesterday 04:58'), (1, 'Recording since yesterday 04:58')):
        mm = page(ring, sc=(unplug, NONE, 0, 0, 3600, 0, 0, 0, since_on))
        expect(texts(mm, 'pod_hs_cap') == [want] and texts(mm, 'pod_hs_cap') == [HM.caption_text('yesterday 04:58', NONE, since_on)] and texts(mm, 'pod_hs_left') == [''], f'an unknown level: no ", N%" in the caption ("{want}") and nothing left to say ({texts(mm, "pod_hs_cap")})')
    mm = page(sc=(HEAD * SECS - 100, 90, 0, 0, 0, 0, 0, 0, 0))
    expect(SC <= shown(mm) and [texts(mm, n) for n in ('pod_hs_dur', 'pod_hs_d0', 'pod_hs_d1', 'pod_hs_d2')] == [['0 min']] * 4 and [texts(mm, f'pod_hs_p{k}') for k in range(3)] == [['~0%']] * 3, 'a run just begun: the card shows, 0 min and ~0% each')
    expect(set(bmp(mm, 0)[3]) >= {STBY_PX}, 'and its bar is the standby track alone')
    # the caption fits its 276 px box in every language, in the longest cases (a day word or a date, the 12-hour clock, the level)
    import pod_i18n
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))
    width = lambda text: StbText(font, ST.NOTE_PX).layout(text)[1]
    room, over = ST.CARD_W - 2 * HM.SPAD, []
    for loc in pod_i18n.LOCALES:
        T = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        for head in ('Unplugged %s, %s', 'Recording since %s, %s'):
            for when in (T('yesterday %s') % '12:25 PM', '12-28 12:25 PM'):
                text = T(head) % (when, '100%')
                if width(text) > room: over.append((loc, text, width(text)))
        for k in ('Turning it off deletes the history.', 'Estimated from the battery gauge.'):
            if width(T(k)) > ST.HDR_W - 4: over.append((loc, k, width(T(k))))
    expect(not over, f'the caption (276 px) and the one-line notes fit in all 13 languages at {ST.NOTE_PX} px ({over})')


def timer_tests(ctx):
    """The page's refresh timer (modelled on the Sleep Timer page's): added when the window opens, a request for a sample, a redraw only when a sample landed, stopped in the background and with the window."""
    expect = ctx.expect
    m = machine(); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([1]))
    for n in NAMES: m.widget(n)
    m.win = m.alloc(0x80); m.window = m.win
    step(m, 0); step(m, 900); step(m, 900, lit=True)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    m.setword(PSYMS['pod_fg'] + 4 * pod_pages.BATTHIST_PAGE_INDEX, m.win)   # the page is the foreground window of its index (page_refresh's pod_fg)
    before = bytes(m.u.mem_read(PSYMS['bh'], 0x60))
    m.calls = []; m.call(PSYMS['bhpage_opened'], a0=m.win, a1=pod_pages.BATTHIST_PAGE_INDEX, count=400000)
    after = bytes(m.u.mem_read(PSYMS['bh'], 0x60))
    tick = [t for t in m.timers if t[1] == 1000]
    expect(len(tick) == 1 and ('timer_add', tick[0][0], 1000) in m.calls and before != after, f'opened: one 1 s timer, and a sample asked for ({m.timers})')
    m.calls = []; m.call(tick[0][0], a0=0, count=3000000)
    expect('widget_set_visible' not in m.names(), 'a tick with no new sample redraws nothing')
    step(m, 60, lit=True)
    m.calls = []; again = m.call(tick[0][0], a0=0, count=4000000)
    expect('widget_set_visible' in m.names() and again != 0, 'a tick after a new sample redraws, and asks to repeat')
    m.calls = []; m.call(tick[0][0], a0=0, count=3000000)
    expect('widget_set_visible' not in m.names(), 'and the next tick, with no further sample, does not')
    m.calls = []; m.fire(O['EVT_WINDOW_TO_BG'])
    expect(m.names().count('timer_remove') == 1 and 'timer_add' not in m.names(), 'in the background the timer is removed')
    m.calls = []; m.call(PSYMS['bhpage_front'], count=400000)
    added = m.names().count('timer_add')
    m.calls = []; m.call(PSYMS['bhpage_front'], count=400000)
    expect(added == 1 and 'timer_add' not in m.names(), f'back in front it is added once, a second event adds none ({added})')
    m.calls = []; m.call(PSYMS['bhpage_gone'], count=400000)
    expect(m.names().count('timer_remove') == 1, 'with the window it is removed')
    m.calls = []; m.call(PSYMS['bhpage_front'], count=400000)
    expect('timer_add' not in m.names(), 'a page that is gone adds no timer')


def visibility_tests(ctx):
    """The items are there only while the switch is on; the switch's two notes; the empty state; the switch updates the page in place."""
    expect = ctx.expect
    m = page(on=False)
    expect(shown(m) == {'pod_note0'} and not m.bitmaps and not [c for c in m.calls if c[0] in ('bitmap_create_ex', 'widget_set_text_utf8')], 'the switch off: the long note alone, nothing drawn or written')
    expect(all(m.props.get((m.widgets[n], 'visible')) == (1 if n == 'pod_note0' else 0) for n in ITEMS), 'each item is told to show or hide (not left to the asset)')
    m = page()
    expect('pod_note0' not in shown(m) and 'pod_note1' in shown(m), 'the switch on: the short note instead of the long one')
    # recording that starts on battery has a run from its first sample: the card shows as soon as a bucket has closed, "Recording since"
    m = machine(); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([1]))
    for n in NAMES: m.widget(n)
    m.win = m.alloc(0x80)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['empty'] and not m.bitmaps, 'the switch on, no sample yet: the short note and the empty note')
    step(m, 0)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['empty'] and not m.bitmaps, 'one open bucket: still the empty state')
    step(m, 900); step(m, 900, lit=True)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['data'] | SC and len(m.bitmaps) == 3, 'started on battery, a bucket closed: the Since Last Charge card, its note and the charts show')
    m.shown_calls = []; m.calls = []
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000); m.shown_calls = list(m.calls)
    expect(texts(m, 'pod_hs_cap') and texts(m, 'pod_hs_cap')[0].startswith('Recording since ') and texts(m, 'pod_hs_cap')[0].endswith(', 80%'), f'the caption says Recording since ({texts(m, "pod_hs_cap")})')
    # on the charger the caption says Charging with the gauge now; the card is otherwise the frozen last run; unplugged, the old caption
    step(m, 15, status=b'Charging\n')
    m.shown_calls = []; m.calls = []
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000); m.shown_calls = list(m.calls)
    expect(texts(m, 'pod_hs_cap') == ['Charging, 80%'] == [HM.charging_text(80)] and SC <= shown(m), f'on the charger: "Charging, 80%" and the card stays ({texts(m, "pod_hs_cap")})')
    step(m, 15, status=b'Discharging\n')
    m.shown_calls = []; m.calls = []
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000); m.shown_calls = list(m.calls)
    expect(texts(m, 'pod_hs_cap') and texts(m, 'pod_hs_cap')[0].startswith('Unplugged '), f'unplugged again: the old caption ({texts(m, "pod_hs_cap")})')
    # recording that starts on the charger, or with an unreadable status: no run, no card until the charger is removed
    for name, status in (('on the charger', b'Charging\n'), ('with an unreadable status', b'Weird\n')):
        m = machine(status=status); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([1]))
        for n in NAMES: m.widget(n)
        m.win = m.alloc(0x80)
        step(m, 0); step(m, 900); step(m, 900, lit=True)
        m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
        expect(shown(m) == SHOWN['data'] and len(m.bitmaps) == 2, f'recording started {name}: the charts show, no Since Last Charge card or note')
        ids = set(m.bitmaps)
        m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
        expect(set(m.bitmaps) == ids and 'bitmap_create_ex' not in m.names() and len(m.bitmaps) == 2, 'shown again: the same two bitmaps drawn in place')
    m = machine(status=b'Charging\n'); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([1]))
    for n in NAMES: m.widget(n)
    m.win = m.alloc(0x80)
    step(m, 0); step(m, 900); step(m, 900, lit=True)
    step(m, 60, lit=True, status=b'Charging\n'); step(m, 60, lit=True, status=b'Discharging\n')
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['data'] | SC and len(m.bitmaps) == 3, 'the charger removed: the Since Last Charge card and its note appear in place')
    # the switch turned off: the long note comes back and the rest hides (and the bitmaps stay for a later turn-on; the data is gone)
    m.call(PSYMS['bh_toggle'], count=4000000)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['off'], 'turned off: the long note alone')
    m.call(PSYMS['bh_toggle'], count=4000000)
    m.call(PSYMS['bhpage_show'], a0=m.win, count=4000000)
    expect(shown(m) == SHOWN['empty'], 'turned on again: the empty state (the ring was deleted), the short note')
    # a page the payload does not know (a missing widget): nothing happens
    m2 = page(on=True); m2.widgets.pop('pod_hist1'); m2.call(PSYMS['bhpage_show'], a0=m2.alloc(0x80), count=4000000)
    expect(True, 'a window without our widgets is left alone')
    # the page's heights and names: the asset
    import awtk_ui as AU
    root = AU.parse(open(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui', pod_pages.BATTHIST_PAGE.key + '.bin'), 'rb').read())
    sv = root.find('pod_scrollview')
    got = [(c.name, c.h, c.get('visible') == 'false') for c in sv.children]
    want = [('pod_top', ST.CM, False)] + [(n, h, hd) for n, h, hd in [
        ('pod_row0', 52, False), ('pod_note0', 55, False), ('pod_note1', ST.NOTE_H, True),
        ('pod_sec0', ST.HDR_H, True), ('pod_hist0', 302, True), ('pod_note2', ST.NOTE_H, True), ('pod_sec1', ST.HDR_H, True), ('pod_hist1', 150, True), ('pod_sec2', ST.HDR_H, True), ('pod_hist2', 150, True),
        ('pod_note3', ST.NOTE_H + ST.WRAP_LINE, True)]] + [('pod_end', ST.END_H, False)]
    expect(got == want, f'the asset: the switch and its notes, the History items hidden at the start (only the long note shows), in order ({[g for g, w_ in zip(got, want) if g != w_][:3]})')
    names = {w.name for w in root.walk()}
    expect(all(n in names for n in NAMES + ['pod_ha_l0', 'pod_ha_l1', 'pod_hl_a0', 'pod_hl_a1', 'pod_hl_a2', 'pod_hs_n0', 'pod_hs_n1', 'pod_hs_n2']) and not [n for n in names if n.startswith(('pod_sub', 'pod_value', 'pod_mark')) or n == 'pod_sec3'],
           'every widget the payload looks up is in the asset, and no On Battery rows')
    expect([r.name for r in sv.children if r.type == 'list_item'] == ['pod_row0'], 'the switch is the page\'s only row')
    expect({n.name: n.get('text') for n in root.walk() if n.name in ('pod_hl_a0', 'pod_hl_a1', 'pod_hl_a2')} == {'pod_hl_a0': '100%', 'pod_hl_a1': '50%', 'pod_hl_a2': '0%'}, 'the level chart\'s axis: 100%, 50%, 0%')
    import pod_i18n
    hs = {w.name: w for w in root.walk() if w.name.startswith('pod_hs_')}
    box = lambda n: (hs[n].x, hs[n].y, hs[n].w, hs[n].h)
    expect([pod_i18n.shown_english(hs[f'pod_hs_n{k}']) for k in range(3)] == ['Screen On', 'Playing, Screen Off', 'Standby']
           and [box(f'pod_hs_n{k}') for k in range(3)] == [(10 + 34, 108 + 60 * k + 20 - 12, 170, 24) for k in range(3)]
           and [box(f'pod_hs_d{k}') for k in range(3)] == [(10 + 34, 108 + 60 * k + 42 - 10, 170, 20) for k in range(3)]
           and [box(f'pod_hs_p{k}') for k in range(3)] == [(10 + 300 - 12 - 60, 108 + 60 * k + 30 - 12, 60, 24) for k in range(3)],
           'a row: the name centred on 20 under the row\'s top after the mark, the duration under it on 42, the percent at the right on 30')
    expect(all(hs[f'pod_hs_n{k}'].x + hs[f'pod_hs_n{k}'].w < hs[f'pod_hs_p{k}'].x and hs[f'pod_hs_d{k}'].x + hs[f'pod_hs_d{k}'].w < hs[f'pod_hs_p{k}'].x for k in range(3)), 'the name and duration boxes end before the percent\'s')
    expect(hs['pod_hs_dur'].get('style:normal:font_size') == '28' and hs['pod_hs_cap'].get('style:normal:font_size') == '15' and hs['pod_hs_left'].get('style:normal:text_align_h') == 'right'
           and all(hs[f'pod_hs_d{k}'].get('style:normal:text_align_h') == 'left' and hs[f'pod_hs_d{k}'].get('style:normal:font_size') == '16' and hs[f'pod_hs_n{k}'].get('style:normal:font_size') == '18'
                   and hs[f'pod_hs_p{k}'].get('style:normal:text_align_h') == 'right' and hs[f'pod_hs_p{k}'].get('style:normal:font_size') == '17' for k in range(3))
           and hs['pod_hs_p0'].get('style:normal:text_color') != hs['pod_hs_d0'].get('style:normal:text_color') and hs['pod_hs_p0'].x + hs['pod_hs_p0'].w == 10 + 300 - HM.SPAD and hs['pod_hs_left'].x + hs['pod_hs_left'].w == 10 + 300 - HM.SPAD,
           'the big total (28 px), the caption (15 px), the percent left, the grey durations on the left and the white percents on the right at the bar\'s right edge')
    sens = {w.name: w.get('sensitive') for w in root.walk() if w.name in ('pod_hist0', 'pod_hist1', 'pod_hist2')}
    expect(set(sens.values()) == {'false'}, 'the History charts never take a touch')


SECTIONS = [constants_tests, sample_tests, attribution_tests, ring_tests, gap_tests, corrupt_tests, switch_tests, sc_tests, settings_tests, history_tests, texts_tests, timer_tests, visibility_tests]

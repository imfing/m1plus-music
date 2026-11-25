"""Card script runner tests: the runner, the Card Script pages, status, log and the external audio hold, against made-up files."""
import os, signal, stat, subprocess, tempfile, time
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_cardrun as mc
import awtk_ui
import paths



def stub(path, body):
    open(path, 'w').write('#!/bin/sh\n' + body); os.chmod(path, 0o755)


def run(ctx):
    expect = ctx.expect
    root = os.path.join(WORK, 'rootfs')
    stock = os.path.join(paths.find_stock(), 'rootfs')
    initd = os.path.join(root, 'etc', 'init.d')
    built = open(os.path.join(root, mc.REL), 'rb').read()

    # ---- the file in the tree ----
    expect(mc.added_rels() == ['usr/bin/m1plus-run'], 'the step adds one file')
    expect(built == open(mc.SRC, 'rb').read() and stat.S_IMODE(os.stat(os.path.join(root, mc.REL)).st_mode) == 0o755, 'it is the pinned script, executable')
    for n in os.listdir(os.path.join(stock, 'etc', 'init.d')):
        if n == 'S11logo_display_shell': continue   # the card logo's splash script (test/pod/bootlogo.py)
        expect(open(os.path.join(initd, n), 'rb').read() == open(os.path.join(stock, 'etc', 'init.d', n), 'rb').read(), f'stock {n} is unchanged')
    expect(sorted(os.listdir(initd)) == sorted(os.listdir(os.path.join(stock, 'etc', 'init.d'))), 'nothing in /etc/init.d: rcS never starts it')
    text = built.decode()

    # ---- the runner under the host shell, its fixed paths pointed into a scratch directory ----
    extra = {}

    def run_script(script='echo ran in $(pwd)\n', pidfile=None, exitfile=None):
        with tempfile.TemporaryDirectory() as t:
            mmc, tmp = (os.path.join(t, d) for d in ('mmc', 'tmp'))
            for d in (mmc, tmp): os.mkdir(d)
            if pidfile is not None: open(os.path.join(tmp, 'm1plus-run.pid'), 'w').write(pidfile)
            if exitfile is not None: open(os.path.join(tmp, 'm1plus-run.exit'), 'w').write(exitfile)
            if script is not None: open(os.path.join(mmc, 'm1plus-run.sh'), 'w').write(script)
            s = text
            for a, b in (('/mnt/mmc', mmc), ('/tmp/', tmp + '/')): s = s.replace(a, b)
            path = os.path.join(t, 'm1plus-run'); open(path, 'w').write(s)
            syntax = subprocess.run(['sh', '-n', path], capture_output=True).returncode
            r = subprocess.run(['sh', path], env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=30)
            read = lambda p: open(p).read() if os.path.exists(p) else None
            extra.update(pid=read(os.path.join(tmp, 'm1plus-run.pid')), exit=read(os.path.join(tmp, 'm1plus-run.exit')))
            return syntax, r.returncode, r.stdout + r.stderr, read(os.path.join(tmp, 'm1plus-run.log')), read(os.path.join(tmp, 'm1plus-run.sh')), sorted(os.listdir(mmc))

    sy, rc, out, log, copy, files = run_script()
    expect(sy == 0 and rc == 0 and out == b'' and log == 'ran in /\n' and copy == 'echo ran in $(pwd)\n', f'the card\'s script runs as a copy in /tmp, from /, its output in /tmp: {rc} {out!r} {log!r}')
    expect(files == ['m1plus-run.sh'], f'the runner writes nothing to the card: {files}')
    expect(extra['exit'] == '0\n' and extra['pid'] is None, f'a run ends with its exit status in /tmp/m1plus-run.exit and no pid file: {extra}')
    expect('/etc/init.d' not in text and '$1' not in text and 'm1plus-off' not in text.replace('# ', '').split('\n\n')[-1], 'no start, boot or argument path, no kill switch')
    sy, rc, out, log, copy, _ = run_script(script='echo out; echo err >&2; echo end; exit 3\n')
    expect(rc == 0 and log == 'out\nerr\nend\n' and extra['exit'] == '3\n' and extra['pid'] is None, f'a failing script: both streams in the log, the runner still returns 0, the status is kept: {rc} {log!r} {extra}')
    sy, rc, out, log, copy, _ = run_script(script=None)
    expect(rc == 0 and out == b'' and log is None and copy is None and extra['pid'] is None, 'no script on the card: nothing runs, nothing is left')
    sy, rc, out, log, copy, _ = run_script(pidfile=f'{os.getpid()}\n', exitfile='5\n')
    expect(rc == 0 and log is None and copy is None and extra['pid'] == f'{os.getpid()}\n' and extra['exit'] == '5\n', 'while the pid file names a live process: refused, the record is untouched')
    dead = subprocess.Popen(['true']); dead.wait()
    sy, rc, out, log, copy, _ = run_script(pidfile=f'{dead.pid}\n')
    expect(rc == 0 and log == 'ran in /\n' and extra['exit'] == '0\n', 'a pid file of a process that is gone does not stop the run')
    sy, rc, out, log, copy, _ = run_script(script='echo pid=$(cat $(dirname $0)/m1plus-run.pid) shell=$PPID\n', exitfile='9\n')
    expect(log.split('pid=')[1].split()[0] == log.split('shell=')[1].strip() and extra['exit'] == '0\n', f'the pid file names the shell that runs the script, the old exit status is replaced: {log!r}')
    sy, rc, out, log, copy, _ = run_script(pidfile='\n')
    expect(log == 'ran in /\n', 'an empty pid file does not stop the run')
    # Stop: the page signals the group of a run it started (its own session, so the group is the pid); the shell outlives the script and records the end
    with tempfile.TemporaryDirectory() as t:
        mmc, tmp = os.path.join(t, 'mmc'), os.path.join(t, 'tmp'); os.mkdir(mmc); os.mkdir(tmp)
        open(os.path.join(mmc, 'm1plus-run.sh'), 'w').write('echo up\nsleep 30\necho late\n')
        s_ = text
        for a, b in (('/mnt/mmc', mmc), ('/tmp/', tmp + '/')): s_ = s_.replace(a, b)
        path = os.path.join(t, 'm1plus-run'); open(path, 'w').write(s_)
        pidf, exitf, logf = (os.path.join(tmp, f'm1plus-run.{e}') for e in ('pid', 'exit', 'log'))
        proc = subprocess.Popen(['sh', path], env={'PATH': '/usr/bin:/bin'}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            if os.path.exists(logf) and 'up' in open(logf).read(): break
            time.sleep(0.05)
        pid = int(open(pidf).read())
        expect(pid == proc.pid and os.getpgid(pid) == pid, f'a run started in its own session: the pid file names the group leader ({pid}, {proc.pid})')
        os.killpg(pid, signal.SIGTERM)
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        expect(open(exitf).read() == '143\n' and not os.path.exists(pidf) and 'late' not in open(logf).read(), 'SIGTERM to the group ends the script, the shell records 143 and removes the pid file')

    # ---- the Developer page (patch/cardrun.c): Settings > Developer > Tools > Card Script ----
    import mod_icons, pod_i18n
    P = pod_pages
    page, logpage = P.CARDRUN_PAGE, P.CARDLOG_PAGE
    expect([(r.label, r.action, P.row_kind(r)) for r in page.rows] == [('Status', P.ACT_INFO, 'info'), ('Run Now', 210, 'action'), ('View Script', 214, 'link'), ('View Log', 212, 'link')]
           and page.key == 'm1plus_cardrun' and page.title == 'Card Script' and P.PAGES[P.CARDRUN_PAGE_INDEX] is page and page.rows[0].arg == P.INFO_CRSTATUS == P.INFO_DUR + 7,
           'the page: Status (a value), Run Now (an action row, Stop while a run is alive), View Script and View Log (links)')
    expect([x if x == P.GAP else type(x).__name__ for x in page.layout] == ['Row', P.GAP, 'Row', P.GAP, 'Row', 'Row', 'Note'] and page.layout[-1].text == P.CR_NOTE == "Put m1plus-run.sh in the card's root folder. It runs as root; View Log shows its output."
           and set(P.NOGLYPH_ACTIONS) >= {210, 212, 214} and P.ACT_CRRUN in P.ACTION_ACTIONS and not hasattr(P, 'ACT_CRSTOP') and P.ACT_CRLOG not in P.ACTION_ACTIONS,
           'cards: Status, [Run Now], [View Script, View Log], then one note; no glyphs; Run Now has no chevron')
    expect(not hasattr(P, 'ACT_CRBOOT') and 'cardrun-boot' not in P.SETTING_FILES and 'cr_boot_setting' not in PSYMS and 'cr_boot_toggle' not in PSYMS, 'no Run at Boot: no switch, no setting file, no payload code')
    expect(P.PAGE_ORDER[-6:-3] == ['m1plus_cardrun', 'm1plus_cardlog', 'm1plus_cardsrc'] and P.PAGES[-5] is logpage and P.PAGES[-4] is P.CARDSRC_PAGE and logpage.kind == P.CARDSRC_PAGE.kind == 'relnotes' and logpage.title == 'Card Script Log' and P.CARDSRC_PAGE.title == 'm1plus-run.sh',
           'both pages are at the end of PAGE_ORDER (before m1plus_psxfade, m1plus_plcover and m1plus_cfstart); the log is a Release Notes page')
    tools = [x.label for x in P.DEVELOPER_PAGE.layout if hasattr(x, 'label')]
    expect(tools[tools.index('Settings Files') + 1] == 'Card Script' and P.DEVELOPER_PAGE.rows[tools.index('Card Script')].arg == P.CARDRUN_PAGE_INDEX
           and mod_icons.CARD_GLYPHS['Card Script'] == 'memory-stick' and mod_icons.card_name('memory-stick') in mod_icons.CARD_IMAGES, 'Developer > Tools: Card Script follows Settings Files')
    expect(all(k in pod_i18n.TEXT for k in ('Card Script', 'Card Script Log', 'View Script', 'm1plus-run.sh', 'Run Now', 'Stop', 'View Log', 'No Script', 'Ready', 'Running', 'Done', 'Stopped', 'Failed', 'No log yet', P.CR_NOTE)),
           'the strings are in every language table')

    rows = PSYMS[f'pod_rows_{P.CARDRUN_PAGE_INDEX}']
    SCRIPT, PIDF, EXITF, LOGF = '/mnt/mmc/m1plus-run.sh', '/tmp/m1plus-run.pid', '/tmp/m1plus-run.exit', '/tmp/m1plus-run.log'

    def mk(script=True, pid=None, alive=True, exit_=None, log=None):
        m = Machine()
        if script: m.fs[SCRIPT] = b'echo hi\n'
        if pid is not None: m.fs[PIDF] = f'{pid}\n'.encode(); m.alive = {pid} if alive else set()
        if exit_ is not None: m.fs[EXITF] = f'{exit_}\n'.encode()
        if log is not None: m.fs[LOGF] = log
        return m

    def status(m):
        buf = m.alloc(64); m.u.mem_write(buf, bytes(64)); m.call(PSYMS['cardrun_status_text'], a0=buf, a1=64, count=3000000); return m.read_cstr(buf)

    def tap(m, row): m.calls = []; m.call(PSYMS['on_row'], a0=rows + 12 * row, count=20000000)
    def toasts_(m): return [c[1] for c in m.calls if c[0] == 'toast']

    # Status
    def status_at(m, now=1000, mtime=None):
        m.wall = now
        m.mtimes = {} if mtime is None else {PIDF: mtime}
        return status(m)
    expect([status(mk(script=False)), status(mk()), status(mk(exit_=0)), status(mk(exit_=3)), status(mk(exit_=255)), status(mk(exit_=143)), status(mk(exit_=137)), status(mk(script=False, exit_=0)),
            status(mk(pid=4300, alive=False)), status(mk(pid=4300, alive=False, exit_=1)), status(mk(pid=1))]
           == ['No Script', 'Ready', 'Done', 'Failed (3)', 'Failed (255)', 'Stopped', 'Stopped', 'No Script', 'Ready', 'Failed (1)', 'Ready'],
           'Status: No Script, Ready, Done (0), Failed (N), Stopped (143 or 137), a stale pid file is not a run')
    expect([status_at(mk(pid=4300), 1012, 1000), status_at(mk(pid=4300, exit_=3), 1000, 1000), status_at(mk(pid=4300), 1000 + 754, 1000), status_at(mk(pid=4300), 990, 1000), status_at(mk(pid=4300), 1000, None), status_at(mk(script=False, pid=4300), 1005, 1000)]
           == ['Running 0:12', 'Running 0:00', 'Running 12:34', 'Running 0:00', 'Running 0:00', 'Running 0:05'],
           'Running m:ss from the pid file\'s mtime, never negative, 0:00 when it cannot be read; a run beats the old exit status')
    # the page: values and dims follow the state
    def open_page(m):
        n = len(page.rows)
        m.widgets = {nm: 0x30000000 + 0x100 * i for i, nm in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row', 'pod_value', 'pod_switch', 'pod_check', 'pod_label') for i in range(n)])}
        row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.CARDRUN_PAGE_INDEX)
        m.mtimes = {PIDF: 1000}; m.wall = 1012; m.calls = []
        m.call(PSYMS['on_row'], a0=row, count=20000000)
        return m

    def run_label(m):
        t = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets['pod_label1']]
        return t[-1] if t else None
    for case, m, want in (('no script', mk(script=False), 'Run Now'), ('a script', mk(), 'Run Now'), ('a run', mk(pid=4300, log=b''), 'Stop'), ('a run, no script', mk(script=False, pid=4300, log=b''), 'Stop')):
        open_page(m)
        expect(run_label(m) == want, f'{case}: the Run Now row reads {want}: {run_label(m)}')
        expect(not [c for c in m.calls if c[0] in ('widget_set_opacity', 'widget_set_sensitive') and c[1] in [m.widgets[f'pod_row{i}'] for i in range(len(page.rows))]], f'{case}: no Card Script row is dimmed or made insensitive')
    m = open_page(mk(pid=4300, log=b'')); vals = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets['pod_value0']]
    expect(vals and vals[-1] == 'Running 0:12' and [c for c in m.calls if c[0] == 'timer_add'], f'the page shows the status with the elapsed time and, with a run alive, starts the 500 ms tick: {vals}')
    m = open_page(mk()); expect(not [c for c in m.calls if c[0] == 'timer_add'], 'no run: the page starts no timer')
    # Run Now
    m = mk(); tap(m, 1)
    expect(toasts_(m) == [] and ('fork',) in m.calls and [c for c in m.calls if c[0] == 'timer_add'], 'Run Now: starts the runner and the tick, no toast')
    m = mk(); m.fork_seq = [-1]; tap(m, 1)
    expect(toasts_(m) == ['Storage unavailable'] and not [c for c in m.calls if c[0] in ('waitpid', 'usleep', 'execl', 'timer_add')], 'a fork that fails: a toast')
    m = mk(); m.fork_seq = [0, 777]; tap(m, 1)
    expect([c for c in m.calls if c[0] in ('fork', 'setsid', 'execl') or c[0] == 'kill' and c[2]][:3] == [('fork',), ('fork',), ('kill', 4300, 9)] and ('setsid',) not in m.calls and not [c for c in m.calls if c[0] == 'execl'],
           'the first child forks the runner and ends at once, before setsid or exec')
    m = mk(); m.fork_seq = [0, 0]; m.blind_close = []; tap(m, 1)
    calls = [c for c in m.calls if c[0] in ('fork', 'kill', 'setsid', 'execl') or c[0] == 'open' and c[1] == '/dev/null']
    ex = ('execl', '/usr/bin/m1plus-run', 'm1plus-run')
    expect(calls[:7] == [('fork',), ('fork',), ('setsid',), ('open', '/dev/null', 2), ('open', '/dev/null', 2), ('open', '/dev/null', 2), ex]
           and calls[7] == ('kill', 4300, 9) and sorted(m.blind_close) == list(range(1024)) and m.calls.index(('setsid',)) < m.calls.index(ex),
           f'the runner: setsid, every descriptor to 1023 closed, 0-2 reopened on /dev/null, exec of /usr/bin/m1plus-run without an argument; a failed exec ends the child: {calls[:8]}')
    # Stop
    m = mk(pid=4300); tap(m, 1)
    expect([c for c in m.calls if c[0] == 'kill' and c[2]] == [('kill', -4300, 15), ('kill', 4300, 15)] and toasts_(m) == [] and not [c for c in m.calls if c[0] == 'usleep'],
           'Stop (the Run Now row during a run): SIGTERM to the group, then the pid; no toast, no wait, no new run' and ('fork',) not in m.calls)
    m = mk(script=False); tap(m, 1)
    expect(toasts_(m) == ['No m1plus-run.sh on the card'] and ('fork',) not in m.calls and not [c for c in m.calls if c[0] == 'timer_add'], 'Run Now with no script: a toast, nothing started')

    # External audio hold: Run Now starts the 500 ms timer; the tick takes the DAC for a new want file, holds the timers, releases when the file is gone
    WANT, READY, YIELD = '/tmp/m1plus-extaudio', '/tmp/m1plus-extaudio.ready', '/tmp/m1plus-extaudio.yield'
    tick = lambda m: m.call(PSYMS['cr_tick'], a0=0, count=40000000)
    HOLD = ('stop_player', 'set_outputchannel', 'mclSetPcmMode', 'mclSetMute', 'set_devicevolume', 'mclSetDacPwr', 'mclStop')

    class HM(Machine):   # the stock player and DAC calls the take makes: recorded in m.cmds
        def _hook(self, u, address, size, _):
            name = self.handlers.get(address, '')
            if name in HOLD:
                self.cmds.append((name,) + ((u.reg_read(UC_MIPS_REG_A0),) if name in ('set_outputchannel', 'mclSetMute') else ())); u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            else: super()._hook(u, address, size, _)

    def mkh(**kw):
        m = mk(**kw); m.__class__ = HM; m.cmds = []; return m
    m = mk(); m.alive = set(); tap(m, 1)
    expect(('timer_add', PSYMS['cr_tick'], 500) in m.calls, 'Run Now starts the hold timer, every 500 ms')
    m = mkh(pid=4300); m.cmds.clear(); m.calls = []
    expect(tick(m) == 8 and not m.cmds and READY not in m.fs, 'a live run and no want file: the timer repeats, nothing is taken')
    m.alive = set()
    expect(tick(m) == 0, 'the run is gone and no want file: the timer ends')
    # the tick refreshes the open page while a run is alive and once when it ends, and not otherwise
    refreshes = lambda m: [c for c in m.calls if c[0] == 'cardrun_refresh']

    class RM(Machine):
        def _hook(self, u, address, size, _):
            if self.handlers.get(address) == 'cardrun_refresh':
                self.calls.append(('cardrun_refresh',)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
            return super()._hook(u, address, size, _)
    m = mk(pid=4300); m.__class__ = RM; m.handlers[PSYMS['cardrun_refresh']] = 'cardrun_refresh'; m.calls = []
    r = [tick(m), len(refreshes(m))]; m.alive = set(); r += [tick(m), len(refreshes(m))]; r += [tick(m), len(refreshes(m))]
    expect(r == [8, 1, 0, 1, 0, 0], f'a live run: the page is refreshed each tick; when it ends, once more and the timer stops; then nothing: {r}')
    m = mk(); m.__class__ = RM; m.handlers[PSYMS['cardrun_refresh']] = 'cardrun_refresh'; m.calls = []; m.alive = set(); tap(m, 1); m.calls = []
    r = [tick(m), len(refreshes(m))]
    expect(r == [0, 1], f'a run too short for a tick to see it still gets its end shown: {r}')
    m = mkh(pid=4300); m.fs[WANT] = b''; m.play_status = 2; m.cmds.clear(); m.calls = []
    expect(tick(m) == 8 and ('stop_player',) in m.cmds and ('set_outputchannel', 0) in m.cmds and ('mclSetPcmMode',) in m.cmds and ('mclSetMute', 0) in m.cmds and READY in m.fs
           and m.cmds.index(('stop_player',)) < m.cmds.index(('mclSetPcmMode',)), f'a new want file: local music stopped, the DAC readied, the ready file made: {m.cmds}')
    m.cmds.clear(); m.calls = []; tick(m)
    expect(m.cmds == [] and ('reset_poweroptions_timer', 1, 1, 0) in m.calls, f'held: the timers are reset, the DAC is not taken again: {m.cmds}')
    m.fs[YIELD] = b''; del m.fs[WANT]; m.alive = set(); m.calls = []
    expect(tick(m) == 0 and READY not in m.fs and YIELD not in m.fs and not m.cmds, 'the want file gone: ready and yield removed, the DAC left as it is, the timer ends')
    m = mkh(pid=4300); m.fs[WANT] = b''; m.play_status = 1; m.cmds.clear(); tick(m)
    expect(('stop_player',) not in m.cmds and READY in m.fs, 'nothing playing locally: no stop')
    # cr_ext_yield
    m = mk(); m.calls = []; m.call(PSYMS['cr_ext_yield'], count=3000000)
    expect(YIELD not in m.fs and not [c for c in m.calls if c[0] == 'usleep'], 'no hold: nothing is created and nothing waits')
    m = mk(); m.fs[WANT] = b''; m.calls = []
    m.on_usleep = lambda n: m.fs.pop(WANT, None) if n == 3 else None
    m.call(PSYMS['cr_ext_yield'], count=3000000)
    expect(YIELD in m.fs and [c for c in m.calls if c[0] == 'usleep'] == [('usleep', 20000)] * 3, 'a hold: the yield file is made and the call returns when the want file goes')
    m = mk(); m.fs[WANT] = b''; m.calls = []; m.call(PSYMS['cr_ext_yield'], count=6000000)
    expect(YIELD in m.fs and [c for c in m.calls if c[0] == 'usleep'] == [('usleep', 20000)] * 100, 'a script that never lets go: the wait ends after 2 s')

    # the log page
    RW = 0x24500000

    def log_page(log=None):
        m = mk(log=log); m.windows['m1plus_cardlog'] = RW
        for n in ('btn_return', 'btn_backtoplayer', 'rn_scrollview', 'rn_view', 'label_head', 'label_line'): m.widget(n)
        m.sv = m.alloc(0x100); m.widgets['rn_scrollview'] = m.sv; m.canvas = m.alloc(0x80)
        tap(m, 3)
        return m

    def paint(m, off=0):
        m.setword(m.sv + 0x84, off); ev = m.paint_event(); m.texts, m.text_styles = [], []
        fn_, ctx_ = m.bound[(m.widgets['rn_view'], O['EVT_AFTER_PAINT'])]
        m.call(fn_, a0=ctx_, a1=ev, count=60000000)
        return list(zip(m.text_styles, [t for t, r in m.texts], [r for t, r in m.texts]))

    def tail(m, n=16385):
        buf = m.alloc(n); m.u.mem_write(buf, bytes(n)); r = m.call(PSYMS['cardrun_log'], a0=buf, a1=n, count=80000000); return r, bytes(m.u.mem_read(buf, r)).decode()

    m = log_page()
    expect(('window_open', 'm1plus_cardlog') in m.calls and m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] == PSYMS['m1_on_back'], 'View Log opens our page m1plus_cardlog; Back goes back')
    tx = paint(m)
    expect([t[:2] for t in tx] == [('label_line', 'No log yet')] and tx[0][2][1] == 12, f'no log: "No log yet" alone, no heading, at the top ({tx})')
    expect([t[1] for t in paint(log_page(b''))] == ['No log yet'], 'an empty log reads the same')
    tx = paint(log_page(b'first\nsecond\n\nthird\n'))
    lines = [t for t in tx if t[0] == 'label_line']
    expect([t[1] for t in lines] == ['first', 'second', 'third'] and all(t[2][0] == 16 and t[2][2] == 288 and t[2][3] == 20 for t in lines) and [t[2][1] for t in lines] == [12, 32, 64], f'a short log: its lines in order, 20 px apart from y 12, a gap at the empty line ({lines})')
    # long lines wrap inside the 288 px column; nothing leaves the 400 px view
    longlog = b''.join(b'%03d ' % i + b'abcdefghij klmnopqrstuvwxyz 0123456789 ' * 4 + b'end\n' for i in range(60))
    m = log_page(longlog)
    tx = paint(m)
    lines = [t for t in tx if t[0] == 'label_line']
    expect(len(lines) > 12 and all(t[2][2] == 288 and t[2][1] + t[2][3] <= 400 for t in tx) and lines[0][1].startswith('000 abcdefghij'), f'170-character lines wrap in the column and stay in the view ({len(lines)} lines)')
    far = paint(m, 400)
    expect(far and far != tx and not [t for t in tx if t[0] == 'label_head'], 'scrolled down, the page shows later lines; no page paints a heading')
    # the text: the tail, from a line start
    m = mk(log=b'')
    expect(tail(m) == (0, ''), 'an empty log: nothing')
    m = mk(); expect(tail(m) == (0, ''), 'no log: nothing')
    m = mk(log=b'a\tb\r\n\xc3\xa9x\x01\n'); r, t = tail(m)
    expect(t == 'a    b \n??x ', f'a tab is four spaces, other control bytes one, bytes over 0x7e a "?", the last newline is dropped ({t!r})')
    big = b''.join(b'row %05d %s\n' % (i, b'x' * (i % 90)) for i in range(2000))
    m = mk(log=big); r, t = tail(m)
    cut = big[-16384:]; cut = cut[cut.index(b'\n') + 1:]
    want = cut.decode().rstrip('\n').split('\n')[-300:]
    expect(r == len('\n'.join(want)) and t == '\n'.join(want) and t.endswith('row 01999 ' + 'x' * (1999 % 90)) and t.startswith('row '), f'a log over 16 KiB: the tail from a line start, the last 300 lines ({r} bytes)')
    mid = b''.join(b'%05d %s\n' % (i, b'y' * 150) for i in range(400)); m = mk(log=mid); r, t = tail(m)
    cut = mid[-16384:]; cut = cut[cut.index(b'\n') + 1:]
    expect(t == cut.decode().rstrip('\n') and r < 16384 and len(t.split('\n')) < 300, f'the 16 KiB cut leaves whole lines ({r} bytes, {len(t.split(chr(10)))} lines)')
    m = mk(log=b'x' * 40000); r, t = tail(m)
    expect(r == 16384 - 0 and set(t) == {'x'}, 'a log with no newline at all: the last 16 KiB as it is')
    ml = log_page(b'z\n' * 5000)
    expect(len([t for t in paint(ml) if t[0] == 'label_line']) > 5, 'thousands of short lines open the page too')

    # the script page: the start of the card's own file (not the copy in /tmp)
    def src_page(script):
        m = mk(script=False); m.windows['m1plus_cardsrc'] = RW
        if script is not None: m.fs[SCRIPT] = script
        m.fs['/tmp/m1plus-run.sh'] = b'the copy in /tmp\n'
        for n in ('btn_return', 'btn_backtoplayer', 'rn_scrollview', 'rn_view', 'label_head', 'label_line'): m.widget(n)
        m.sv = m.alloc(0x100); m.widgets['rn_scrollview'] = m.sv; m.canvas = m.alloc(0x80)
        tap(m, 2)
        return m

    def head(script, n=16385):
        m = mk(script=False); m.fs[SCRIPT] = script
        buf = m.alloc(n); m.u.mem_write(buf, bytes(n)); r = m.call(PSYMS['cardrun_src'], a0=buf, a1=n, count=80000000); return r, bytes(m.u.mem_read(buf, r)).decode()

    m = src_page(None); opened = ('window_open', 'm1plus_cardsrc') in m.calls
    tx = paint(m)
    expect(opened and [t[:2] for t in tx] == [('label_line', 'No m1plus-run.sh on the card')], f'no script on the card: the page says so ({tx})')
    tx = paint(src_page(b'#!/bin/sh\necho hi\n'))
    expect([t[1] for t in tx if t[0] == 'label_line'] == ['#!/bin/sh', 'echo hi'], 'a short script: its lines, read from the card (not the copy in /tmp)')
    expect(head(b'if x; then\n\techo y\n\t\tz\nfi\n') == (len('if x; then\n    echo y\n        z\nfi'), 'if x; then\n    echo y\n        z\nfi'), 'tabs are four spaces')
    expect(head(b'') == (0, '') and head(b'one\r\n') == (4, 'one '), 'an empty script: nothing; a CR is a space')
    big = b''.join(b'line %05d %s\n' % (i, b'x' * (i % 90)) for i in range(2000))
    r, t = head(big)
    cut = big[:16384]; cut = cut[:cut.rindex(b'\n')]
    want = cut.decode().split('\n')[:300]
    expect(t == '\n'.join(want) and r == len(t) and t.startswith('line 00000') and len(want) == 300, f'a script over 16 KiB: the head, whole lines, the first 300 ({r} bytes)')
    big = b''.join(b'%05d %s\n' % (i, b'y' * 150) for i in range(400)); r, t = head(big)
    cut = big[:16384]; cut = cut[:cut.rindex(b'\n')]
    expect(t == cut.decode() and r < 16384 and t.endswith('y' * 150), f'the 16 KiB cut ends at a line end ({r} bytes)')
    tabs = b'\t\tx' * 3 + b'\n'; big = tabs * 5000; r, t = head(big)
    expect(0 < r <= 16384 and t.endswith('x') and {len(l) for l in t.split('\n')} == {27}, f'tabs that grow the text past 16 KiB: still whole lines ({r} bytes)')
    m = mk(script=False); m.fs[SCRIPT] = b'x' * 40000; buf = m.alloc(16385); r = m.call(PSYMS['cardrun_src'], a0=buf, a1=16385, count=80000000)
    expect(r == 16384, 'no newline at all: the first 16 KiB as it is')

    # the log page's navbar: the stock one, as on the other text pages
    RAWD = os.path.join('rootfs', 'release', 'assets', 'default', 'raw', 'ui')
    def navbar_of(key):
        tree = awtk_ui.parse(open(os.path.join(WORK, RAWD, key + '.bin'), 'rb').read())
        return {w.name: w for w in tree.walk() if w.name}
    lg, ls, lk, rn = (navbar_of(k) for k in ('m1plus_cardlog', 'm1plus_cardsrc', 'm1plus_lockinfo', 'm1plus_relnotes'))
    expect(all('btn_refresh' not in d and d['btn_backtoplayer'].get('visible') != 'false' and d['btn_backtoplayer'].get('sensitive') != 'false' and d['btn_backtoplayer'].get('style:normal:icon') == 'ah_nav_np' for d in (lg, ls, lk, rn)),
           'the log, script, Custom Wallpaper and Release Notes pages all keep the stock Now Playing button, no refresh button')

    sz = lambda d: d['label_line'].get('style:normal:font_size') or d['label_line'].get('font_size')
    expect(str(sz(lg)) == str(sz(ls)) == '15' and str(sz(lk)) == '20' and str(sz(rn)) == '18', f'label sizes: card pages 15, Custom Wallpaper 20, Release Notes 18 ({sz(lg)}, {sz(ls)}, {sz(lk)}, {sz(rn)})')

    # the log is read once when the page opens
    def yoffsets(m): return [c for c in m.calls if c[0] == 'widget_set_prop_int' and c[2] == 'yoffset']
    m = log_page(b'first\n')
    expect(('widget_set_prop_int', m.sv, 'virtual_h', 400) in m.calls and not yoffsets(m), 'a short log opens at the top (nothing to scroll)')
    m = log_page(b''.join(b'line %03d\n' % i for i in range(60)))
    ys = yoffsets(m)
    expect(len(ys) == 1 and ys[0][3] > 0, f'a long log opens scrolled to its end ({ys})')

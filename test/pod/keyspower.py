"""Settings > System > Buttons & Power (patch/keyspower.c, docs/modules/keyspower.md): our page for stock's key lock, Tap to Wake, Auto-Standby and Auto-Shutdown. Every state is stock's own and is written the way
stock's own pages write it, which the tests check by running stock's click handlers under the emulator on the same state and comparing the stored values, the saves and the countdown calls, in order, with ours."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

FLAG, MODE, TAP, STANDBY, SHUTDOWN = (pod.DATA[n][0] for n in ('KEY_LOCK_FLAG', 'KEY_LOCK_MODE', 'TAP_WAKE', 'STANDBY_FLAG', 'SHUTDOWN_MODE'))
LOCK_SWITCH, LOCK_CHOICE = 0x4a7a04, {1: 0x4a7a7c, 2: 0x4a7ab8, 3: 0x4a7af4}   # stock's systemset/keylock_page click handlers (the window in a0)
SYSSET_CLICK = 0x4ad7b0                                                       # stock's shared sysset list click handler (the row item in a0; its name is the row's number)
STANDBY_SWITCH, SHUTDOWN_SWITCH = 0x4a97c4, 0x4a966c                           # stock's systemset/powermanager_page switches
SHUTDOWN_CHOICE = {1: 0x4a9cb4, 2: 0x4a9c50, 3: 0x4a9bec, 4: 0x4a9b88}        # ... and its four durations (1, 3, 5, 10 min)
WIN = 0x30000000
LEAVES = {0x742da0: 'memset', 0x70f8d8: 'tk_snprintf', 0x7435b0: 'atoi'}   # (the PLT stubs stock's code calls through)
STOCK_WIDGETS = ('img_switch', 'listitem1', 'listitem2', 'listitem3', 'listitem4', 'img_choice1', 'img_choice2', 'img_choice3', 'img_doublewake7', 'imgswitch_standby', 'imgswitch_saver',
                 'standby_listitem2', 'standby_listitem3', 'standby_listitem4', 'standby_listitem5', 'standby_listitem6') + tuple(f'standby_imgchoice{i}' for i in range(1, 6))   # the widgets stock's refreshes look up
KINDS = ('pod_value', 'pod_label', 'pod_switch', 'pod_check')


class KM(Machine):
    """Stock's handlers and refreshes run for real, with the leaves above mocked. Every save and every countdown call records the four state words as they are at that moment: the order of the stores and the saves."""
    def __init__(self, flag=0, mode=1, tap=0, standby=0, shutdown=0):
        super().__init__()
        for a, n in LEAVES.items(): self.handlers[a] = n
        self.snap = []
        self.u.mem_write(FLAG, bytes([flag])); self.setword(MODE, mode)
        self.u.mem_write(TAP, bytes([tap])); self.u.mem_write(STANDBY, bytes([standby])); self.setword(SHUTDOWN, shutdown)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name in ('write_int_config', 'reset_poweroptions_timer'): self.snap.append(self.state())
        if name != 'tk_snprintf': return super()._hook(u, address, size, _)
        a0, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        text = self.read_cstr(a2) % a3
        u.mem_write(a0, text.encode() + b'\0')
        u.reg_write(UC_MIPS_REG_V0, len(text)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]
    def state(self): return (self.byte(FLAG), self.word(MODE), self.byte(TAP), self.byte(STANDBY), self.word(SHUTDOWN))
    def stock_widgets(self):
        for n in STOCK_WIDGETS: self.widget(n)
        return self


def saves(m):
    """What reaches stock's state: the saves and the countdown calls, in order."""
    return [c[:4] for c in m.calls if c[0] in ('write_int_config', 'reset_poweroptions_timer')]


def run_stock(m, *handlers):
    calls = []
    for h in handlers:
        m.call(h, a0=WIN, count=3000000)   # (a call starts the machine's call list again: the clicks' calls are put together here)
        calls += m.calls
    m.calls = calls
    return m


def same(expect, mo, ms, what):
    """Ours against stock's: the final state, the saves and calls in order, and the state at each of them."""
    expect(mo.state() == ms.state() and saves(mo) == saves(ms) and mo.snap == ms.snap, f'{what}: state {mo.state()} / {ms.state()}, calls {saves(mo)} / {saves(ms)}, at each call {mo.snap} / {ms.snap}')


def lock_tests(ctx):
    """kp_lock / kp_lock_set against stock's switch and the three choices, run for real on the same state."""
    expect = ctx.expect
    expect((FLAG, MODE) == (0xa05aa0, 0x97caec) and pod.DATA['KEY_LOCK_FLAG'][1] == 'keylock_flag' and pod.DATA['KEY_LOCK_MODE'][1] == 'keylock_mode', 'the byte and the word are stock\'s (checked against demo\'s dynsym by the build)')
    pins = {a: w for a, w, _ in pod.KEYSPOWER_PINS}
    expect(all(a in pins for a in (0x4a7a38, 0x4a7a40, 0x4a7a5c, 0x4a7a60, 0x4a7900, 0x4a7980, 0x4a7984, 0x4a7988, 0x4a7aa4, 0x4a7ae0, 0x4a7b1c, 0x47e3b0, 0x4cda6c, 0x4cdc2c, 0x4e6318, 0x4e6380)),
           'the switch\'s store and save, the mode store and save, the three choices, the three key gates and config_init\'s clamps are pinned')
    for flag, mode, want in ((0, 1, 0), (0, 3, 0), (1, 1, 1), (1, 2, 2), (1, 3, 3), (1, 0, 1), (1, 4, 1), (1, -1, 1)):
        expect(KM(flag=flag, mode=mode).call(PSYMS['kp_lock'], count=200000) == want, f'flag {flag}, mode {mode}: the lock is {want}')
    # every change the picker can make, from every state stock's page can be in, as the stock clicks it takes (the switch, then the choice)
    for flag in (0, 1):
        for mode in (1, 2, 3):
            for new in range(4):
                ms = KM(flag=flag, mode=mode).stock_widgets()
                if new == 0: run_stock(ms, *([LOCK_SWITCH] if flag else []))
                else: run_stock(ms, *([LOCK_SWITCH] if not flag else []), LOCK_CHOICE[new])
                mo = KM(flag=flag, mode=mode); r = mo.call(PSYMS['kp_lock_set'], a0=new, count=2000000)
                expect(r == 0, f'flag {flag} mode {mode} -> {new}: answers 0')
                same(expect, mo, ms, f'flag {flag}, mode {mode} -> {new}')
    for flag, mode, new, want in ((1, 2, 0, [('write_int_config', 0, 'SYSSET', 'LOCKFLAG')]), (0, 2, 3, [('write_int_config', 1, 'SYSSET', 'LOCKFLAG'), ('write_int_config', 3, 'SYSSET', 'LOCKMODE')]),
                                  (0, 2, 2, [('write_int_config', 1, 'SYSSET', 'LOCKFLAG')]), (1, 2, 1, [('write_int_config', 1, 'SYSSET', 'LOCKMODE')]), (1, 2, 2, []), (0, 1, 0, [])):
        m = KM(flag=flag, mode=mode); m.call(PSYMS['kp_lock_set'], a0=new, count=2000000)
        expect(saves(m) == want and not [c for c in m.calls if c[0] in ('reset_poweroptions_timer', 'system', 'popen')], f'flag {flag}, mode {mode} -> {new}: the saves {saves(m)}, no countdown, no other call')
    m = KM(flag=1, mode=3); m.call(PSYMS['kp_lock_set'], a0=0, count=2000000)
    expect(m.state()[:2] == (0, 3), 'Off keeps the mode, as stock\'s page does')
    for bad in (-1, 4, 99):
        m = KM(flag=1, mode=2)
        expect(m.call(PSYMS['kp_lock_set'], a0=bad & 0xffffffff, count=200000) == 0xffffffff and m.state()[:2] == (1, 2) and not saves(m), f'choice {bad}: refused, nothing written')


def tap_tests(ctx):
    """kp_tap / kp_tap_toggle against the case of stock's sysset click handler for the Tap to Wake row."""
    expect = ctx.expect
    expect(pod.DATA['TAP_WAKE'] == (0xa05aa1, 'doublewake_flag'), 'the byte is stock\'s (checked against demo\'s dynsym by the build)')
    pins = {a: w for a, w, _ in pod.KEYSPOWER_PINS}
    expect(all(a in pins for a in (0x4ad930, 0x4ad944, 0x4ad948, 0x4ad954, 0x4ad958, 0x4ad95c, 0x4e62b8, 0x4e62d0, 0x4e62d8)), 'the case\'s byte, xor, key, save and store, and config_init\'s clamp are pinned')
    for st in (0, 1):
        ms = KM(tap=st).stock_widgets()
        node = ms.alloc(0x40); ms.setword(node + 0x10, ms.cstr('7'))   # the row item: its name is the row's number
        expect(ms.word(0x97c8c0 + 4 * 7) == 7, 'the sysset list\'s table maps the row number 7 to the case 7 (Tap to Wake)')
        ms.call(SYSSET_CLICK, a0=node, count=3000000)
        mo = KM(tap=st); r = mo.call(PSYMS['kp_tap_toggle'], count=2000000)
        expect(r == 1 - st and mo.byte(TAP) == ms.byte(TAP) == 1 - st and saves(mo) == saves(ms) == [('write_int_config', 1 - st, 'SYSSET', 'DOUBLEWAKE')], f'Tap to Wake from {st}: the byte and the one save are stock\'s ({saves(mo)} / {saves(ms)})')
        same(expect, mo, ms, f'Tap to Wake from {st}')
        expect(len(mo.calls) == 1 or [c for c in mo.calls if c[0] != 'write_int_config'] == [], 'ours calls nothing but the save (no sysfs write, no system())')
        expect(KM(tap=st).call(PSYMS['kp_tap'], count=200000) == st, f'the byte {st}: the switch shows {st}')
    for v, want in ((2, 0), (3, 1), (0xff, 1)):
        expect(KM(tap=v).call(PSYMS['kp_tap'], count=200000) == want, f'the byte {v}: the switch shows {want} (the low bit, as the toggle)')


def power_tests(ctx):
    """kp_standby / kp_standby_toggle / kp_shutdown / kp_shutdown_set against stock's two switches and four durations."""
    expect = ctx.expect
    expect(pod.DATA['STANDBY_FLAG'] == (0xa05a8c, 'standbyflag') and pod.DATA['SHUTDOWN_MODE'] == (0xa05a84, 'savepowermode'), 'the byte and the word are stock\'s (checked against demo\'s dynsym by the build)')
    pins = {a: w for a, w, _ in pod.KEYSPOWER_PINS}
    expect(all(a in pins for a in (0x4a97f8, 0x4a9800, 0x4a980c, 0x4a981c, 0x4a988c, 0x4a9910, 0x4a9918, 0x4a9854, 0x4a9790, 0x4a97b0, 0x4a971c, 0x4a9764, 0x4a95a8, 0x4a9524, 0x4a9bd8, 0x4a9bac,
                                 0x4a9cd4, 0x4a9c70, 0x4a9c0c, 0x4e5fd4, 0x4e5fec, 0x4e6034)),
           'both switches\' stores, saves and countdown arguments, the duration refresh and the four duration handlers, and config_init\'s clamps are pinned')
    states = [(0, w) for w in range(5)] + [(1, 0)]   # (Auto-Standby, Auto-Shutdown): the two are never both on
    for sb, sh in states:
        ms = run_stock(KM(standby=sb, shutdown=sh).stock_widgets(), STANDBY_SWITCH)
        mo = KM(standby=sb, shutdown=sh); r = mo.call(PSYMS['kp_standby_toggle'], count=2000000)
        expect(r == mo.byte(STANDBY) == 1 - sb, f'Auto-Standby from ({sb}, {sh}): answers the new state')
        same(expect, mo, ms, f'Auto-Standby from ({sb}, {sh})')
        expect(not (mo.byte(STANDBY) and mo.word(SHUTDOWN)) and saves(mo)[-1] == ('reset_poweroptions_timer', 1, 1, 0), f'Auto-Standby from ({sb}, {sh}): never both on; ends with reset_poweroptions_timer(1, 1, 0)')
    for sb, sh in states:
        for new in range(5):
            ms = KM(standby=sb, shutdown=sh).stock_widgets()
            if new == 0: run_stock(ms, *([SHUTDOWN_SWITCH] if sh else []))
            else: run_stock(ms, *([SHUTDOWN_SWITCH] if not sh else []), SHUTDOWN_CHOICE[new])
            mo = KM(standby=sb, shutdown=sh); r = mo.call(PSYMS['kp_shutdown_set'], a0=new, count=2000000)
            expect(r == 0, f'Auto-Shutdown ({sb}, {sh}) -> {new}: answers 0')
            same(expect, mo, ms, f'Auto-Shutdown ({sb}, {sh}) -> {new}')
            expect(not (mo.byte(STANDBY) and mo.word(SHUTDOWN)) and mo.word(SHUTDOWN) == new, f'Auto-Shutdown ({sb}, {sh}) -> {new}: never both on, the word is {new}')
    # the calls spelled out (the argument orders the comparison above proves against stock)
    S, T = 'SYSSET', 'reset_poweroptions_timer'
    for (sb, sh, op, arg), want in {
            (0, 3, 'standby', None): [('write_int_config', 0, S, 'SAVEPOWERMODE'), ('write_int_config', 1, S, 'STANDBYMODE'), (T, 1, 1, 0)],
            (1, 0, 'standby', None): [('write_int_config', 0, S, 'STANDBYMODE'), (T, 1, 1, 0)],
            (0, 0, 'standby', None): [('write_int_config', 1, S, 'STANDBYMODE'), (T, 1, 1, 0)],
            (1, 0, 'shutdown', 3): [('write_int_config', 0, S, 'STANDBYMODE'), ('write_int_config', 1, S, 'SAVEPOWERMODE'), (T, 1, 1, 0), ('write_int_config', 3, S, 'SAVEPOWERMODE'), (T, 0, 1, 0)],
            (0, 0, 'shutdown', 1): [('write_int_config', 1, S, 'SAVEPOWERMODE'), (T, 1, 1, 0)],
            (0, 2, 'shutdown', 4): [('write_int_config', 4, S, 'SAVEPOWERMODE'), (T, 0, 1, 0)],
            (0, 2, 'shutdown', 2): [],
            (0, 2, 'shutdown', 0): [('write_int_config', 0, S, 'SAVEPOWERMODE'), (T, 1, 1, 0)],
            (0, 0, 'shutdown', 0): []}.items():
        m = KM(standby=sb, shutdown=sh)
        m.call(PSYMS['kp_standby_toggle'] if op == 'standby' else PSYMS['kp_shutdown_set'], a0=arg or 0, count=2000000)
        expect(saves(m) == want, f'({sb}, {sh}) {op} {arg}: {saves(m)}')
    for sb, want in ((0, 0), (1, 1), (2, 0), (3, 1)):
        expect(KM(standby=sb).call(PSYMS['kp_standby'], count=200000) == want, f'the byte {sb}: Auto-Standby {want}')
    for sh, want in ((0, 0), (1, 1), (4, 4), (5, 0), (-1, 0), (0x7fffffff, 0)):
        expect(KM(shutdown=sh).call(PSYMS['kp_shutdown'], count=200000) == want, f'the word {sh}: Auto-Shutdown {want}')
    for bad in (-1, 5, 100):
        m = KM(shutdown=2)
        expect(m.call(PSYMS['kp_shutdown_set'], a0=bad & 0xffffffff, count=200000) == 0xffffffff and m.word(SHUTDOWN) == 2 and not saves(m), f'duration {bad}: refused, nothing written')


def settings_tests(ctx):
    """The Settings row, the page, its two pickers, the switches, the value texts, the refresh on return and the assets."""
    expect, P = ctx.expect, pod_pages
    V, K, L, S = P.SETTINGS_PAGE, P.KEYSPOWER_PAGE, P.KEYLOCK_PAGE, P.SHUTDOWN_PAGE
    labels = [r.label for r in V.rows]
    ki = labels.index('Buttons & Power')
    expect(V.rows[ki].action == P.ACT_PAGE and V.rows[ki].arg == P.KEYSPOWER_PAGE_INDEX and P.PAGES[P.KEYSPOWER_PAGE_INDEX] is P.KEYSPOWER_PAGE and P.row_kind(V.rows[ki]) == 'link' and labels[ki - 1] == 'Display' and labels[ki + 1] == 'Appearance',
           'Settings > System > Buttons & Power: after Display, opens our page')
    expect(P.PAGES[P.KEYSPOWER_PAGE_INDEX] is K and P.PAGES[P.KEYLOCK_PAGE_INDEX] is L and P.PAGES[P.SHUTDOWN_PAGE_INDEX] is S and (P.KEYLOCK_PAGE_INDEX, P.SHUTDOWN_PAGE_INDEX) == (74, 75)
           and (K.key, K.title, L.key, L.title, S.key, S.title) == ('m1plus_keyspower', 'Buttons & Power', 'm1plus_keylock', 'Button Lock', 'm1plus_shutdown', 'Auto-Shutdown'), 'the three pages')
    expect([(r.label, r.action, r.arg) for r in K.rows] == [('Button Lock', P.ACT_KEYLOCK, P.KEYLOCK_PAGE_INDEX), ('Tap to Wake', P.ACT_TAPWAKE, 0), ('Auto-Standby', P.ACT_STANDBY, 0),
                                                           ('Auto-Shutdown', P.ACT_SHUTDOWN, P.SHUTDOWN_PAGE_INDEX)] and [P.row_kind(r) for r in K.rows] == ['value', 'switch', 'switch', 'value'], 'the page\'s rows and their kinds')
    kl = [x.label if isinstance(x, P.Row) else x.text if isinstance(x, P.Note) else x for x in K.layout]
    expect(kl == ['Button Lock', 'Only effective when the screen is off', 'Tap to Wake', P.GAP, 'Auto-Standby', 'Auto-Shutdown', 'Only one of Auto-Standby and Auto-Shutdown is on at a time'],
           f'three cards: Button Lock with its note; Tap to Wake; Auto-Standby + Auto-Shutdown with its note ({kl})')
    expect([(r.label, r.action, r.arg) for r in L.rows] == [('Off', P.ACT_KEYLOCKSET, 0), ('Lock Volume Only', P.ACT_KEYLOCKSET, 1), ('Lock Buttons Only', P.ACT_KEYLOCKSET, 2), ('Lock Volume & Buttons', P.ACT_KEYLOCKSET, 3)]
           and all(P.row_kind(r) == 'check' for r in L.rows) and [x.text for x in L.layout if isinstance(x, P.Note)] == ['Only effective when the screen is off'] and P.KEYLOCK_VALUES == ('Off', 'Volume', 'Buttons', 'Both'),
           'the Button Lock picker: Off and stock\'s three modes in stock\'s numbers, the note repeated')
    expect([(r.label, r.action, r.arg) for r in S.rows] == [(t, P.ACT_SHUTDOWNSET, i) for i, t in enumerate(('Off', '1min', '3min', '5min', '10min'))] and all(P.row_kind(r) == 'check' for r in S.rows)
           and P.SHUTDOWN_VALUES == ('Off', '1min', '3min', '5min', '10min'), 'the Auto-Shutdown picker: Off and stock\'s four durations, the argument is stock\'s word')
    expect((P.ACT_KEYLOCK, P.ACT_KEYLOCKSET, P.ACT_TAPWAKE, P.ACT_STANDBY, P.ACT_SHUTDOWN, P.ACT_SHUTDOWNSET) == (102, 103, 104, 105, 106, 107) and {P.ACT_TAPWAKE, P.ACT_STANDBY} <= set(P.SWITCH_ACTIONS)
           and {P.ACT_KEYLOCK, P.ACT_SHUTDOWN} <= set(P.VALUE_ACTIONS) and {P.ACT_KEYLOCKSET, P.ACT_SHUTDOWNSET} <= set(P.CHECK_ACTIONS), 'the actions')
    expect(not any(r.action == P.ACT_STOCK for r in K.rows) and not any(n.split('/')[-1] in ('keylock_page', 'powermanager_page', 'sysset_page') for n, *_ in P.STOCK_PAGES), 'no row opens a stock page')
    import pod_i18n
    import mod_icons
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in ('Buttons & Power', 'Button Lock', 'Tap to Wake', 'Auto-Standby', 'Auto-Shutdown', 'Off', 'Volume', 'Buttons', 'Both', 'Lock Volume Only', 'Lock Buttons Only',
                                                    'Lock Volume & Buttons', 'Only effective when the screen is off', 'Only one of Auto-Standby and Auto-Shutdown is on at a time')), f'the page texts have a translation in {loc}')
    expect(all(pod_i18n.key_for(t) is None for t in ('1min', '3min', '5min', '10min')) and pod_i18n.TEXT['Tap to Wake']['en_US'] == 'Tap to Wake' and pod_i18n.key_for('Tap to Wake') == 'Tap to Wake',
           'the times are plain texts; Tap to Wake is our own short key, not stock\'s long text')
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Buttons & Power', 'Button Lock', 'Tap to Wake', 'Auto-Standby', 'Auto-Shutdown')] == ['power', 'lock-keyhole', 'pointer', 'moon', 'power'], 'the glyphs')

    def page(index, nrows, kinds=('pod_check', 'pod_label'), **state):
        m = KM(**state)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row',) + tuple(kinds) for i in range(nrows)])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, index)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    def checks(m, n):
        out = []
        for i in range(n):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out
    # the Button Lock picker: the check follows the flag and the mode; a tap saves as stock's switch and choice do
    for flag, mode, want in ((0, 2, 0), (0, 1, 0), (1, 1, 1), (1, 2, 2), (1, 3, 3)):
        m = page(P.KEYLOCK_PAGE_INDEX, 4, flag=flag, mode=mode)
        expect(('window_open', L.key) in m.calls and checks(m, 4) == [int(i == want) for i in range(4)] and not saves(m), f'flag {flag}, mode {mode}: the picker\'s check {checks(m, 4)}, nothing written')
    m = page(P.KEYLOCK_PAGE_INDEX, 4, flag=0, mode=1)
    m.click('pod_row3')
    expect(m.state()[:2] == (1, 3) and saves(m) == [('write_int_config', 1, 'SYSSET', 'LOCKFLAG'), ('write_int_config', 3, 'SYSSET', 'LOCKMODE')] and checks(m, 4) == [0, 0, 0, 1], 'a tap on Lock Volume & Buttons: the flag, the mode, the check follows')
    m.calls = []; m.click('pod_row3')
    expect(not saves(m), 'a tap on the chosen row writes nothing')
    m.click('pod_row0')
    expect(m.state()[:2] == (0, 3) and saves(m) == [('write_int_config', 0, 'SYSSET', 'LOCKFLAG')] and checks(m, 4) == [1, 0, 0, 0], 'Off: the flag only, the mode stays')
    # the Auto-Shutdown picker
    for sh in range(5):
        m = page(P.SHUTDOWN_PAGE_INDEX, 5, shutdown=sh)
        expect(('window_open', S.key) in m.calls and checks(m, 5) == [int(i == sh) for i in range(5)] and not saves(m), f'the word {sh}: the picker\'s check {checks(m, 5)}, nothing written')
    m = page(P.SHUTDOWN_PAGE_INDEX, 5, standby=1, shutdown=0)
    m.click('pod_row4')
    expect(m.state()[3:] == (0, 4) and saves(m) == [('write_int_config', 0, 'SYSSET', 'STANDBYMODE'), ('write_int_config', 1, 'SYSSET', 'SAVEPOWERMODE'), ('reset_poweroptions_timer', 1, 1, 0),
                                                    ('write_int_config', 4, 'SYSSET', 'SAVEPOWERMODE'), ('reset_poweroptions_timer', 0, 1, 0)] and checks(m, 5) == [0, 0, 0, 0, 1], f'a tap on 10min from Off with Auto-Standby on: stock\'s two clicks ({saves(m)})')
    # the page: the values, the switches, the pickers' rows
    PK = ('pod_value', 'pod_label', 'pod_switch')

    def value(m, i):
        got = [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_tr_text') and c[1] == m.widgets[f'pod_value{i}']]
        return got, [t for n, t in got if n == 'widget_set_tr_text']

    def sw_images(m, i): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']]
    for flag, mode, want in ((0, 3, 'Off'), (1, 1, 'Volume'), (1, 2, 'Buttons'), (1, 3, 'Both'), (1, 9, 'Volume')):
        got, tr = value(page(P.KEYSPOWER_PAGE_INDEX, 4, PK, flag=flag, mode=mode), 0)
        expect(tr == [want], f'flag {flag}, mode {mode}: the Button Lock row shows {tr}')
    for sh, want in ((0, ['Off']), (1, []), (4, [])):
        got, tr = value(page(P.KEYSPOWER_PAGE_INDEX, 4, PK, shutdown=sh), 3)
        expect(tr == want and got[-1][1] == ('Off' if sh == 0 else ('1min', '3min', '5min', '10min')[sh - 1]), f'the word {sh}: the Auto-Shutdown row shows {got}')
    for tap, sb, img_t, img_s in ((0, 0, 'sset_off', 'sset_off'), (1, 1, 'sset_on', 'sset_on')):
        m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK, tap=tap, standby=sb)
        expect(sw_images(m, 1) == [img_t] and sw_images(m, 2) == [img_s] and not saves(m), f'the switches open {img_t} / {img_s} with the bytes ({tap}, {sb}), nothing written')
    m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK, tap=0)
    m.click('pod_row1')
    expect(m.byte(TAP) == 1 and saves(m) == [('write_int_config', 1, 'SYSSET', 'DOUBLEWAKE')] and sw_images(m, 1)[-1] == 'sset_on', 'a tap turns Tap to Wake on: the byte, the save, the switch')
    m.click('pod_row1')
    expect(m.byte(TAP) == 0 and sw_images(m, 1)[-1] == 'sset_off', 'and off again')
    # Auto-Standby on while Auto-Shutdown is on: the shutdown row shows Off at once (the page reads the words again after the tap)
    m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK, standby=0, shutdown=3)
    m.click('pod_row2')
    got, tr = value(m, 3)
    expect(m.state()[3:] == (1, 0) and sw_images(m, 2)[-1] == 'sset_on' and got[-1][1] == 'Off' and tr[-1] == 'Off', f'Auto-Standby on turns Auto-Shutdown off: the words and the row follow ({m.state()}, {got[-2:]})')
    m.click('pod_row2')
    expect(m.state()[3:] == (0, 0) and sw_images(m, 2)[-1] == 'sset_off', 'Auto-Standby off')
    m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK)
    m.calls = []; m.click('pod_row0')
    expect([c[1] for c in m.calls if c[0] == 'window_open'] == [L.key] and 'navigator_to' not in m.names(), 'the Button Lock row opens our picker')
    m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK); m.calls = []; m.click('pod_row3')
    expect([c[1] for c in m.calls if c[0] == 'window_open'] == [S.key] and 'navigator_to' not in m.names(), 'the Auto-Shutdown row opens our picker')
    # back in front: the words are read again (the Control Center's Button Lock tile writes the byte; stock's pages write all of them)
    m = page(P.KEYSPOWER_PAGE_INDEX, 4, PK, flag=0, mode=2, tap=0, standby=0, shutdown=0)
    m.u.mem_write(FLAG, b'\1'); m.u.mem_write(TAP, b'\1'); m.u.mem_write(STANDBY, b'\1')
    m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    got, tr = value(m, 0)
    expect(tr == ['Buttons'] and sw_images(m, 1) == ['sset_on'] and sw_images(m, 2) == ['sset_on'] and not saves(m), f'back in front: the lock, both switches follow the state ({tr}, {sw_images(m, 1)}, {sw_images(m, 2)}), nothing written')
    m.setword(SHUTDOWN, 2); m.u.mem_write(STANDBY, b'\0'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    got, tr = value(m, 3)
    expect(got[-1][1] == '3min' and sw_images(m, 2) == ['sset_off'], 'back in front: Auto-Shutdown shows the word stock\'s page set')
    m = page(P.KEYLOCK_PAGE_INDEX, 4, flag=1, mode=1)
    m.u.mem_write(FLAG, b'\0'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(checks(m, 4) == [1, 0, 0, 0], 'the picker follows the tile too: Off checked after the byte was cleared')
    # the assets
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    kt = awtk_ui.parse(open(os.path.join(raw, 'm1plus_keyspower.bin'), 'rb').read())
    lt = awtk_ui.parse(open(os.path.join(raw, 'm1plus_keylock.bin'), 'rb').read())
    st = awtk_ui.parse(open(os.path.join(raw, 'm1plus_shutdown.bin'), 'rb').read())
    se = awtk_ui.parse(open(os.path.join(raw, 'm1plus_settings.bin'), 'rb').read())
    expect([kt.find(f'pod_row{i}').find('pod_icon').get('image') for i in range(4)] == ['pod_ci_lock_keyhole', 'pod_ci_pointer', 'pod_ci_moon', 'pod_ci_power'] and kt.find('label_title').get('tr_text') == 'Buttons & Power'
           and se.find(f'pod_row{ki}').find('pod_icon').get('image') == 'pod_ci_power', 'the page asset: the four glyphs and the title; the Settings row\'s glyph')
    expect([kt.find(f'pod_label{i}').get('tr_text') for i in range(4)] == ['Button Lock', 'Tap to Wake', 'Auto-Standby', 'Auto-Shutdown'], 'the row labels are our short keys')
    for tree, n, title, first in ((lt, 4, 'Button Lock', 'Off'), (st, 5, 'Auto-Shutdown', 'Off')):
        expect(all(tree.find(f'pod_check{i}').get('visible') == 'false' and tree.find(f'pod_check{i}').get('sensitive') == 'false' for i in range(n)) and tree.find('label_title').get('tr_text') == title
               and tree.find('pod_label0').get('tr_text') == first, f'the {title} picker asset: {n} rows, a hidden insensitive check each')
    expect([st.find(f'pod_label{i}').get('text') for i in range(1, 5)] == ['1min', '3min', '5min', '10min'] and [lt.find(f'pod_label{i}').get('tr_text') for i in range(4)] == ['Off', 'Lock Volume Only', 'Lock Buttons Only', 'Lock Volume & Buttons'],
           'the durations as stock writes them; the lock choices translated')


SECTIONS = [lock_tests, tap_tests, power_tests, settings_tests]

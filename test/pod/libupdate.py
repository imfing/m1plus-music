"""Settings > Library > Update Library (patch/libupdate.c, docs/modules/libupdate.md): our page for stock's systemset/updatemusic_page. Auto Update is stock's own byte (autoscan_flag, [SYSSET] AUTOSCAN): stock's toggle
(0x4af0bc), Update Now (0x4af070) and Choose Folders (0x4af1f4) run under the emulator beside ours and the bytes, the ini write and the calls are compared. Last Updated is the card record the hook at the scan
dialog's finish (payload hook 34) writes: stock's own timer callback (0x47bab0) runs through the hook with the worker's states, and only a finished scan that was not cancelled leaves a record."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

AUTO, STATE = (pod.DATA[n][0] for n in ('AUTOSCAN_FLAG', 'SCAN_STATE'))
TOGGLE, UPDATE_NOW, FOLDERS, TIMER, REFRESH = 0x4af0bc, 0x4af070, 0x4af1f4, 0x47bab0, 0x47b604
REC = '/mnt/mmc/.m1plus/library-updated'
NO_CARD = 'Insert a TF card'


class LU(Machine):
    """The stock calls the page and the stock handlers make: a card that is or is not there, the song count, the scan's stop flag, the dialog's refresh (recorded); the ini writes keep their value."""
    def __init__(self, auto=0, card=True, songs=4812, stop=0, state=0):
        super().__init__()
        self.handlers[REFRESH] = 'scan_refresh'
        self.u.mem_write(AUTO, bytes([auto])); self.setword(STATE, state)
        self.card_mounted, self.songs, self.stop, self.mount = card, songs, stop, card
        self.contexts = []
        self.exec_rc = 0   # what sqlite3_exec returns (0 SQLITE_OK, 5 SQLITE_BUSY)
        self.present.add('/mnt/mmc/.m1plus') if card else None

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in ('toolsCheckMount', 'toolsGetUserStop', 'toolsGetDbTableNumber', 'getFormatString', 'scan_refresh', 'navigator_to_with_context', 'toolsDatabaseCommit', 'sqlite3_exec'):
            return super()._hook(u, address, size, _)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        if name == 'navigator_to_with_context':
            if self.read_cstr(a0) == 'dialog/scanmusic_dialog': self.contexts.append([self.word(a1 + 4 * i) for i in range(4)])
            return super()._hook(u, address, size, _)
        ret = 0
        if name == 'toolsCheckMount': self.calls.append((name, self.read_cstr(a0))); ret = int(self.mount)
        elif name == 'toolsGetUserStop': ret = self.stop
        elif name == 'toolsGetDbTableNumber': self.calls.append((name, self.read_cstr(a0), self.read_cstr(a1))); ret = self.songs & 0xffffffff
        elif name == 'getFormatString': self.calls.append((name, self.read_cstr(a0))); self.u.mem_write(a1, NO_CARD.encode() + b'\0')
        elif name == 'toolsDatabaseCommit': self.calls.append((name,))
        elif name == 'sqlite3_exec': self.calls.append((name, a0, self.read_cstr(a1))); self.exec_args = (u.reg_read(UC_MIPS_REG_A3), self.word(u.reg_read(UC_MIPS_REG_SP) + 0x10)); ret = self.exec_rc
        else: self.calls.append((name, a0, a1))
        u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]
    def text(self, fn, n=64):
        buf = self.alloc(n); self.u.mem_write(buf, bytes(n)); self.call(PSYMS[fn], a0=buf, a1=n, count=3000000); return self.read_cstr(buf)


def state_tests(ctx):
    """Auto Update, Update Now and Choose Folders against stock's handlers; the pins."""
    expect = ctx.expect
    expect(pod.DATA['AUTOSCAN_FLAG'][0] == 0xa05aa9 and pod.DATA['SCAN_STATE'][0] == 0xa03a40 and pod.FUNCTIONS['toolsGetDbTableNumber'][2] == 0x5efb68 and pod.FUNCTIONS['toolsGetUserStop'][2] == 0x5ed954
           and pod.FUNCTIONS['toolsCheckMount'][2] == 0x5e25b0, 'the byte, the scan state word and the three stock calls are pinned addresses')
    m0 = Machine()
    expect(all(m0.word(a) == w for a, w, _ in pod.LIBUPDATE_PINS if a != pod.LIBUPDATE_SITE and a not in pod.LIBUPDATE_COMMIT_SITES + (pod.LIBUPDATE_BATCH_SITE,)) and len(pod.LIBUPDATE_PINS) > 55, f'every pinned stock word is demo\'s ({len(pod.LIBUPDATE_PINS)} pins)')
    pins = {a for a, _, _ in pod.LIBUPDATE_PINS}
    expect({0x4af0a4, 0x4af100, 0x4af104, 0x4af214, 0x4af24c, pod.LIBUPDATE_SITE, 0x47bb00, 0x47b460, 0x47b4c0, 0x5ed950, 0x5ed968, 0x5efcfc, 0x47bca0, 0x47b604} <= pins, 'the handlers\' calls, the scan state\'s writers and readers, the stop byte and the hook site are pinned')
    # Auto Update: from both states, stock's toggle and ours leave the same byte and the same ini write, and the image follows the byte
    for auto in (0, 1):
        ms = LU(auto=auto); ms.widget('img_autoswitch'); ms.call(TOGGLE, a0=ms.window, count=3000000)
        mo = LU(auto=auto); r = mo.call(PSYMS['lu_auto_toggle'], count=3000000)
        wr = lambda m: [c for c in m.calls if c[0] == 'write_int_config']
        expect(ms.byte(AUTO) == mo.byte(AUTO) == 1 - auto and wr(ms) == wr(mo) == [('write_int_config', 1 - auto, 'SYSSET', 'AUTOSCAN')] and r == 1 - auto,
               f'Auto Update from {auto}: stock\'s toggle and ours leave the byte {mo.byte(AUTO)} and write [SYSSET] AUTOSCAN = {1 - auto}')
        expect(any(c[0] == 'image_base_set_image' and c[2] == ('sset_on' if auto == 0 else 'sset_off') for c in ms.calls), f'stock\'s toggle shows sset_{"on" if auto == 0 else "off"} (the generic switch does the same)')
        expect(mo.call(PSYMS['lu_auto'], count=100000) == mo.byte(AUTO), 'the shown state is the byte')
    mo = LU(auto=1); mo.call(PSYMS['lu_auto_toggle'], count=3000000); w1 = [c for c in mo.calls if c[0] == 'write_int_config']; mo.call(PSYMS['lu_auto_toggle'], count=3000000)
    expect(mo.byte(AUTO) == 1 and w1 == [('write_int_config', 0, 'SYSSET', 'AUTOSCAN')] and [c for c in mo.calls if c[0] == 'write_int_config'] == [('write_int_config', 1, 'SYSSET', 'AUTOSCAN')], 'two taps are back where they started, each written')
    # Update Now: stock's handler and ours open the dialog with the same context of four zero words, and nothing else
    ms = LU(); ms.call(UPDATE_NOW, a0=ms.window, count=3000000)
    mo = LU(); mo.call(PSYMS['lu_update_now'], count=3000000)
    nav = lambda m: [c for c in m.calls if c[0] == 'navigator_to_with_context']
    expect(ms.contexts == mo.contexts == [[0, 0, 0, 0]] and [c[1] for c in nav(ms)] == [c[1] for c in nav(mo)] == ['dialog/scanmusic_dialog'] and len(nav(mo)) == 1,
           'Update Now: navigator_to_with_context("dialog/scanmusic_dialog", four zero words), as stock\'s handler')
    expect(not any(c[0] in ('toolsCheckMount', 'stop_player', 'navigator_to') for c in mo.calls), 'Update Now checks no card and starts nothing else (stock\'s handler does not either)')
    # Choose Folders: the card check, then stock's page, or stock's message box
    for card in (True, False):
        mo = LU(card=card); mo.call(PSYMS['lu_folders'], count=3000000)
        key = lambda m: [c for c in m.calls if c[0] in ('toolsCheckMount', 'navigator_to', 'getFormatString', 'toast')]
        if card:   # (stock's no-card branch calls libc through demo's GOT, which the emulator does not map: that branch is pinned, LIBUPDATE_PINS)
            ms = LU(card=card); ms.call(FOLDERS, a0=ms.window, count=3000000)
            expect(key(ms)[:1] == key(mo)[:1] == [('toolsCheckMount', '/mnt/mmc')] and ('window_open', 'm1plus_lupick') in mo.calls and ('navigator_to', 'systemset/specfolder_page') not in mo.calls,
                   f'Choose Folders with a card: stock\'s handler and ours check the card first; ours opens the picker, not stock\'s page ({key(mo)})')
            mf = LU(card=card); mf.windows = {'m1plus_lupick': 0}; mf.call(PSYMS['lu_folders'], count=3000000)
            expect(('navigator_to', 'systemset/specfolder_page') in mf.calls, 'a picker window that will not open: stock\'s page')
        else: expect(key(mo)[0] == ('toolsCheckMount', '/mnt/mmc') and key(mo)[1] == ('getFormatString', 'msg_nottf') and key(mo)[2] == ('toast', NO_CARD, 1, 2000) and len(key(mo)) == 3, 'no card: stock\'s msg_nottf box (kind 1, 2000 ms), no page')
    # the Songs text
    for n, want in ((0, '0'), (7, '7'), (999, '999'), (1000, '1,000'), (4812, '4,812'), (12345, '12,345'), (123456, '123,456'), (1234567, '1,234,567'), (-1, '')):
        m = LU(songs=n)
        expect(m.text('lu_songs_text') == want and (n < 0 or ('toolsGetDbTableNumber', 'songtable', '/mnt/data/database.db') in m.calls), f'{n} songs read "{want}"')


def hook_tests(ctx):
    """The hook at the scan dialog's finish, through stock's own timer callback, and the record's text."""
    expect = ctx.expect
    stock_demo, built = stock_demo_bytes(), built_demo_bytes()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site = pod.LIBUPDATE_SITE
    expect(site == 0x47baec and w(stock_demo, site) == 0x0411fec5 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['lu_scan_finish'], 'the build replaced stock\'s `bal 0x47b604` at 0x47baec by `jal lu_scan_finish`')
    expect(all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old, _ in pod.LIBUPDATE_PINS if 0x47bad0 <= a <= 0x47bb08) and w(built, site + 4) == 0x02002025 and w(built, 0x47bb80) == 0x0411fea0,
           'the callback around the site is stock\'s: the delay slot (a0 = the dialog), the state increment and the other call of the refresh (still scanning)')
    sites = pod.LIBUPDATE_COMMIT_SITES
    expect(sites == (0x4e9e70, 0x4e9f9c) and all(w(stock_demo, a) == 0x0320f809 and w(stock_demo, a + 4) == 0 and w(stock_demo, a - 4) == 0x8f99ba54 for a in sites), 'stock: both scan functions end in `jalr t9` (toolsDatabaseCommit, GOT load before, nop after)')
    expect(all(w(built, a) >> 26 == 3 and (w(built, a) & 0x3ffffff) << 2 == PSYMS['lu_commit'] and w(built, a + 4) == 0 and w(built, a - 4) == 0x8f99ba54 for a in sites), 'the build replaced both by `jal lu_commit`')
    expect({0x4e9e3c, 0x4e9ee4} <= {a for a, _, _ in pod.LIBUPDATE_PINS} and pod.DATA['DB_TX'][0] == 0xa0b080 and pod.DATA['DB_HANDLE'][0] == 0xa0ac74, 'a failed toolsInitDatabase skipping the commit is pinned; the transaction word and the handle are pinned addresses')
    expect(MANIFEST['hook_libupdate'] == {'addr': site, 'target': PSYMS['lu_scan_finish']} and MANIFEST['hook_libupdate_commit'] == {'addr': sites[0], 'target': PSYMS['lu_commit']} and MANIFEST['hook_libupdate_commit_spec'] == {'addr': sites[1], 'target': PSYMS['lu_commit']}, 'the manifest records the hooks')

    def tick(state, stop=0, card=True, wall=1800000000, commit=True, rc=0, tx=3, batch_rc=None, batch_sql='COMMIT;'):
        """Stock's timer callback 0x47bab0 on a dialog widget, with the worker's state word."""
        m = LU(state=state, stop=stop, card=card); m.wall = wall; m.exec_rc = rc
        m.setword(pod.DATA['DB_TX'][0], tx); m.setword(pod.DATA['DB_HANDLE'][0], 0x1234)
        m.commit_calls = []
        if batch_rc is not None:   # stock's batch COMMIT (every 100 rows), through the hook, before the scan's own commit
            m.exec_rc = batch_rc; m.call(PSYMS['lu_batch_exec'], a0=0x1234, a1=m.cstr(batch_sql), count=100000); m.exec_rc = rc
        if commit: m.call(PSYMS['lu_commit'], count=100000); m.commit_calls = list(m.calls)   # the scan function's toolsDatabaseCommit, through the hook
        dlg = m.alloc(0x40); win = m.alloc(0x40); m.setword(win + 0x24, dlg)
        m.widget('img_animation')
        m.call(TIMER, a0=win, count=3000000)
        return m, dlg
    # a finished, not cancelled scan: the refresh first (stock's, with done = 1), then the record, once (state 1; the second tick has state 2)
    m, dlg = tick(1)
    names = m.names()
    expect(('scan_refresh', dlg, 1) in m.calls and m.fs.get(REC) == b'1800000000\n' and m.u.mem_read(STATE, 4) == struct.pack('<I', 2), 'a finished scan: the dialog\'s refresh, the time on the card, the state 2')
    expect(names.index('scan_refresh') < min(i for i, c in enumerate(m.calls) if c[0] in ('open', 'rename')), 'stock\'s refresh runs before the record is written')
    m2 = LU(state=2); m2.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(('scan_refresh', 0x1000, 1) in m2.calls and REC not in m2.fs, 'the second finished tick (state 2): the refresh, no second record')
    m, dlg = tick(1, stop=1)
    expect(('scan_refresh', dlg, 1) in m.calls and REC not in m.fs, 'a cancelled scan (toolsGetUserStop): the refresh, no record')
    m, dlg = tick(1)
    expect(m.commit_calls == [('sqlite3_exec', 0x1234, 'COMMIT;'), ('toolsDatabaseCommit',)] and m.word(pod.DATA['DB_TX'][0]) == 0,
           'lu_commit runs the COMMIT on the handle, clears the transaction word, then stock\'s commit')
    m, dlg = tick(1, rc=5)
    expect(m.commit_calls == [('sqlite3_exec', 0x1234, 'COMMIT;'), ('toolsDatabaseCommit',)] and REC not in m.fs, 'a COMMIT that fails (SQLITE_BUSY): stock\'s commit still closes, Last Updated is not written')
    m, dlg = tick(1, batch_rc=5)
    expect(REC not in m.fs, 'a failed batch COMMIT (every 100 rows), then a clean final COMMIT: Last Updated is not written')
    m, dlg = tick(1, batch_rc=5, tx=0)
    expect(REC not in m.fs, 'a failed batch COMMIT and the transaction word at 0 at the end: not written')
    m, dlg = tick(1, batch_rc=0, batch_sql='ROLLBACK;')
    expect(REC not in m.fs, 'the insert-error path\'s ROLLBACK through the same call, even when it succeeds: not written (rows were lost)')
    m, dlg = tick(1, batch_rc=0)
    expect(m.fs.get(REC) == b'1800000000\n', 'a batch COMMIT that succeeds: recorded')
    m, dlg = tick(1, batch_rc=5)
    m.fs.pop(REC, None); m.setword(STATE, 1); m.call(PSYMS['lu_commit'], count=100000); m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(m.fs.get(REC) == b'1800000000\n', 'the failure flag is cleared at the finish: the next clean scan records')
    ma = LU(); ma.exec_rc = 5; ma.setword(STACK + 0x10, 0x5eed); r = ma.call(PSYMS['lu_batch_exec'], a0=0x1234, a1=ma.cstr('COMMIT;'), a3=0x77, count=100000)
    expect(ma.calls == [('sqlite3_exec', 0x1234, 'COMMIT;')] and r == 5 and ma.exec_args == (0x77, 0x5eed), 'lu_batch_exec runs the same sqlite3_exec call: the result back, the fourth argument and the stack-passed fifth as the caller set them')
    expect(w(built, pod.LIBUPDATE_BATCH_SITE) >> 26 == 3 and (w(built, pod.LIBUPDATE_BATCH_SITE) & 0x3ffffff) << 2 == PSYMS['lu_batch_exec'] and w(stock_demo, pod.LIBUPDATE_BATCH_SITE) == 0x0320f809 and w(built, pod.LIBUPDATE_BATCH_SITE + 4) == 0 and w(built, 0x5ee084) == 0xafa20010
           and MANIFEST['hook_libupdate_batch'] == {'addr': pod.LIBUPDATE_BATCH_SITE, 'target': PSYMS['lu_batch_exec']}, 'toolsInsertDbTable\'s batch COMMIT call became jal lu_batch_exec; the fifth argument\'s store stays')
    m, dlg = tick(1, tx=0)
    expect(m.commit_calls == [('toolsDatabaseCommit',)] and m.fs.get(REC) == b'1800000000\n', 'no open transaction (word 0): no COMMIT run, the scan counts as committed')
    m, dlg = tick(1, commit=False)
    expect(('scan_refresh', dlg, 1) in m.calls and REC not in m.fs, 'a scan whose database did not open (no commit; both workers still set state 1): the refresh, no record')
    m, dlg = tick(1, stop=1)
    m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000); m.stop = 0; m.setword(STATE, 1); m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(REC not in m.fs, 'a cancelled scan consumed its commit flag: the next finish without a commit records nothing')
    m, dlg = tick(1)
    m.fs.pop(REC, None); m.setword(STATE, 1); m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(REC not in m.fs, 'the commit flag is cleared when a finish consumes it')
    m, dlg = tick(0)
    expect(('scan_refresh', dlg, 0) in m.calls and REC not in m.fs, 'still scanning (state 0): the refresh with done = 0, no record')
    m, dlg = tick(1, card=False)
    expect(('scan_refresh', dlg, 1) in m.calls and REC not in m.fs and not any(c[0] == 'open' and 'library-updated' in str(c[1:]) for c in m.calls), 'no card: nothing is written')
    m, dlg = tick(1, wall=1000)
    expect(REC not in m.fs, 'a clock that was never set: no record')
    # the first record of a card makes the folder; a later one replaces the record atomically
    m = LU(state=1, card=True); m.present.discard('/mnt/mmc/.m1plus'); m.dirs.discard('/mnt/mmc/.m1plus')
    m.call(PSYMS['lu_commit'], count=100000); m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(m.fs.get(REC) == b'1800000000\n' and ('mkdir', '/mnt/mmc/.m1plus') in m.calls, 'a card without the folder: it is made, then the record written')
    m.wall = 1800086400; m.setword(STATE, 1); m.call(PSYMS['lu_commit'], count=100000); m.call(PSYMS['lu_scan_finish'], a0=0x1000, a1=1, count=3000000)
    expect(m.fs.get(REC) == b'1800086400\n' and not [p for p in m.fs if p.endswith('.tmp')], 'the next scan replaces the record; no temp file is left')
    # the text of Last Updated: 24-hour or 12-hour by 24-Hour Time, Today / Yesterday / a date, nothing with no record
    HR = pod.DATA['TIME_24H'][0]

    def when(rec, wall=1800000000, tz=0, h24=1, lang=None):
        m = LU(); m.wall, m.tz = wall, tz; m.u.mem_write(HR, bytes([h24]))
        if rec is not None: m.fs[REC] = rec
        return m.text('lu_when_text')
    # 1800000000 = 2027-01-15 08:00:00 UTC
    now = 1800000000
    expect(when(None) == '' and when(b'') == '' and when(b'abc\n') == '' and when(b'12\n') == '' and when(b'1800000000x') == '', 'no record, an empty or a bad one, or one before the clock existed: empty (the row shows "-")')
    expect(when(b'1799995200\n') == 'Today 06:40', f'earlier today, 24-hour: {when(b"1799995200")!r}')
    expect(when(b'1799995200\n', h24=0) == 'Today 6:40 AM' and when(b'1800014400\n', h24=0, wall=1800015000) == 'Today 12:00 PM', 'the 12-hour clock: 6:40 AM, 12:00 PM')
    expect(when(b'1799931600\n') == 'Yesterday 13:00', f'yesterday: {when(b"1799931600")!r}')
    expect(when(b'1799280000\n') == 'Jan 8 00:00' or when(b'1799280000\n').startswith('Jan '), f'older this year: {when(b"1799280000")!r}')
    expect(when(b'1799995200\n', tz=8 * 3600) == 'Today 14:40' and when(b'1799995200\n', wall=now + 20 * 3600, tz=8 * 3600) == 'Yesterday 14:40', 'local time: the zone moves the clock and the day')
    expect(when(b'1760000000\n') == '2025-10-09', f'another year: the date alone ({when(b"1760000000")!r})')
    expect(when(b'1800000000\n', wall=1000) == '', 'a clock that is not set: no text')


def entry_tests(ctx):
    """Every way into Update Library: Settings > Library, the menu item, the Home grid's tile; and the page's rows."""
    expect, P = ctx.expect, pod_pages
    def row_machine(action, arg):
        m = LU(); m.widgets.update({n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row', 'pod_label', 'pod_value', 'pod_check', 'pod_switch') for i in range(6)])})
        r = m.alloc(12); m.setword(r, m.cstr('pod_row0')); m.setword(r + 4, action); m.setword(r + 8, arg)
        m.call(PSYMS['on_row'], a0=r, count=30000000)
        return m
    m = row_machine(P.ACT_PAGE, P.LIBUPDATE_PAGE_INDEX)
    expect(('window_open', 'm1plus_libupdate') in m.calls and not [c for c in m.calls if c[0] in ('navigator_to', 'navigator_to_with_context')], 'the Library page\'s row (a page link) opens our page')
    m = row_machine(P.ACT_HOME, P.HOME_UPDATE)
    expect(('window_open', 'm1plus_libupdate') in m.calls and not [c for c in m.calls if c[0] in ('navigator_to', 'navigator_to_with_context', 'stock_resume')], 'the menu / Extras item (a Home destination, id 2) opens our page, not stock\'s')
    m = LU(); m.windows = {'m1plus_libupdate': 0}; r = m.alloc(12); m.setword(r, m.cstr('pod_row0')); m.setword(r + 4, P.ACT_HOME); m.setword(r + 8, P.HOME_UPDATE)
    m.call(PSYMS['on_row'], a0=r, count=30000000)
    expect(('stock_resume', 0x1) not in m.calls and any(c[0] == 'stock_resume' for c in m.calls), 'a page that will not open: stock\'s dispatcher takes the id')
    # the stock grid's tile (payload hook 1): our page; the kill switch and a failing page leave stock's tile
    for kill, bad, want in ((False, False, 'ours'), (True, False, 'stock'), (False, True, 'stock')):
        m = LU()
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        if bad: m.windows = {'m1plus_libupdate': 0}
        r = m.call(PSYMS['m1plus_home_click'], a0=m.icon('2'), count=3000000)
        expect(any(c[0] == 'stock_resume' for c in m.calls) == (want == 'stock') and (('window_open', 'm1plus_libupdate') in m.calls) == (want == 'ours' or bad), f'the grid tile (kill {kill}, page fails {bad}): {want}\'s page')
    # the page's rows: Update Now and Choose Folders through the row tap; the generic switch for Auto Update
    m = row_machine(P.ACT_LUNOW, 0)
    expect(m.contexts == [[0, 0, 0, 0]], 'the Update Now row opens the scan dialog with the zero context')
    m = row_machine(P.ACT_LUFOLDERS, 0)
    expect(('window_open', 'm1plus_lupick') in m.calls and ('navigator_to', 'systemset/specfolder_page') not in m.calls, 'the Choose Folders row opens our folder picker')


def slot_tests(ctx):
    """Two Update Library windows (Home tile, then Settings > Library after Now Playing): closing the newer one leaves the older one refreshing."""
    expect, P = ctx.expect, pod_pages
    m = LU(); m.widgets.update({n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row', 'pod_label', 'pod_value', 'pod_check', 'pod_switch') for i in range(6)])})
    r = m.alloc(12); m.setword(r, m.cstr('pod_row0')); m.setword(r + 4, P.ACT_PAGE); m.setword(r + 8, P.LIBUPDATE_PAGE_INDEX)
    A, B = 0x31000000, 0x32000000
    DEST = O['EVT_DESTROY']
    for w in (A, B):
        m.windows = {'m1plus_libupdate': w}; m.call(PSYMS['on_row'], a0=r, count=30000000)
    expect((A, DEST) in m.bound and (B, DEST) in m.bound, 'both windows bound their destroy')
    refresh = lambda: (m.calls.clear(), m.call(PSYMS['pod_page_refresh'], a0=P.LIBUPDATE_PAGE_INDEX, count=30000000), any(c[0] == 'widget_set_text_utf8' and c[2] == '4,812' for c in m.calls))[2]
    expect(refresh(), 'two windows open: the page refreshes')
    fn, ctx_ = m.bound[(B, DEST)]; m.call(fn, a0=ctx_, a1=0, count=3000000)
    expect(refresh(), 'the newer window closed: the older one still refreshes (Songs and Last Updated)')
    fn, ctx_ = m.bound[(A, DEST)]; m.call(fn, a0=ctx_, a1=0, count=3000000)
    expect(not refresh(), 'the last window closed: nothing is refreshed')
    m.windows = {'m1plus_libupdate': B}; m.call(PSYMS['on_row'], a0=r, count=30000000)
    expect(refresh(), 'the page opened again is refreshed')


def page_tests(ctx):
    """The page as cards, its texts, the row kinds; the asset."""
    expect, P = ctx.expect, pod_pages
    LP = P.LIBUPDATE_PAGE
    expect((LP.key, LP.title, LP.kind) == ('m1plus_libupdate', 'Update Library', 'cards') and P.PAGE_ORDER[-8:-6] == ['m1plus_libupdate', 'm1plus_lupick'], 'the page, its title, then the picker after it in PAGE_ORDER')
    expect([(r.label, r.action) for r in LP.rows] == [('Songs', P.ACT_INFO), ('Last Updated', P.ACT_INFO), ('Update Now', P.ACT_LUNOW), ('Choose Folders', P.ACT_LUFOLDERS), ('Auto Update', P.ACT_LUAUTO)]
           and (P.ACT_LUNOW, P.ACT_LUFOLDERS, P.ACT_LUAUTO) == (193, 194, 195) and (LP.rows[0].arg, LP.rows[1].arg) == (P.INFO_LUSONGS, P.INFO_LUWHEN) and P.INFO_LUWHEN == P.INFO_LUSONGS + 1, 'the five rows and their actions')
    expect([P.row_kind(r) for r in LP.rows] == ['info', 'info', 'action', 'link', 'switch'], 'two info rows (no touch), the action row, the link and the switch')
    lay = LP.layout
    expect([type(x).__name__ if x is not P.GAP else 'GAP' for x in lay] == ['Row', 'Row', 'GAP', 'Row', 'Row', 'Note', 'Row', 'Note'] and lay[5].text == P.LU_NOTE1 and lay[7].text == P.LU_NOTE2 and lay[5].lines == lay[7].lines == 2,
           'card 1 (info), a gap, card 2 with its note, then the switch with its note')
    expect(P.LU_NOTE1 == 'Choose Folders only adds new music. To remove deleted songs, use Update Now.' and P.LU_NOTE2 == 'Updates after a card is inserted or USB transfer ends.', 'the two notes')
    lib = P.LIBRARY_PAGE.rows[0]
    expect((lib.label, lib.action, lib.arg) == ('Update Library', P.ACT_PAGE, P.LIBUPDATE_PAGE_INDEX) and P.row_kind(lib) == 'link' and P.SETTINGS_PAGE.rows and not any(r.action == P.ACT_HOME and r.arg == P.HOME_UPDATE for pg in P.PAGES if pg.kind == 'cards' for r in pg.rows),
           'Settings > Library: Update Library is a link to our page (a chevron); no settings page opens stock\'s')
    expect(P.ITEMS[P.ITEM_IDS.index('Update Library')].arg == P.HOME_UPDATE, 'the menu item keeps its frozen id (the payload redirects id 2)')
    expect(P.NOGLYPH_ACTIONS[:3] == (P.ACT_LUNOW, P.ACT_LUFOLDERS, P.ACT_LUAUTO) and P.ACT_LUAUTO in P.SWITCH_ACTIONS and P.ACT_LUNOW in P.ACTION_ACTIONS, 'the rows have no glyph; the switch and the action row are in their kind lists')
    import pod_i18n
    keys = ('Last Updated', 'Update Now', 'Choose Folders', 'Auto Update', P.LU_NOTE1, P.LU_NOTE2)
    expect(all(k in pod_i18n.TEXT and all(pod_i18n.TEXT[k][loc] for loc in pod_i18n.LOCALES) for k in keys), 'every text has a translation in all 13 languages')
    expect(pod_i18n.key_for('Update Library') == 'sset_updatemusic', 'the title and the Library row are stock\'s sset_updatemusic')
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    t = awtk_ui.parse(open(os.path.join(raw, 'm1plus_libupdate.bin'), 'rb').read())
    expect(t.find('label_title').get('tr_text') == 'sset_updatemusic' or t.find('label_title').get('tr_text') == 'Update Library', 'the asset: the title')
    labels = [t.find(f'pod_label{i}').get('tr_text') or t.find(f'pod_label{i}').get('text') for i in range(5)]
    expect(labels == ['Songs', 'Last Updated', 'Update Now', 'Choose Folders', 'Auto Update'], f'the asset: the row labels ({labels})')
    expect(not any(c.name == 'pod_icon' for i in range(5) for c in t.find(f'pod_row{i}').children), 'no glyph on any row')
    expect(t.find('pod_note0_t').get('tr_text') == P.LU_NOTE1 and t.find('pod_note1_t').get('tr_text') == P.LU_NOTE2, 'the asset: the notes')
    expect(all(c.get('sensitive') == 'false' for c in (t.find('pod_row0'), t.find('pod_row1'))) and t.find('pod_switch4') is not None and t.find('pod_chevron') is not None, 'the info rows take no touch, the switch and the chevron are there')
    # the value texts fit their column: the longest (a 12-hour "Yesterday 12:00 PM", "Sep 30 12:00 PM") in the info value face
    from awtk_text import Ttf, awtk_width
    fon = Ttf(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts/default.ttf')) if os.path.exists(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts/default.ttf')) else None
    import pod_settings as ST
    if fon:
        worst = max(awtk_width(fon, s, ST.INFO_PX) for s in ('Yesterday 12:00 PM', 'Today 12:00 PM', 'Sep 30 12:00 PM', '1,234,567'))
        label = max(awtk_width(fon, s, 21) for s in ('Last Updated', 'Songs'))
        expect(worst <= ST.INFO_MAX and worst + label + 60 <= 310, f'the longest value is {worst} px in the info column ({ST.INFO_MAX}) and fits beside the 21 px label ({label} px) in the card')





# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The folder picker (patch/lupick.c): the page on a fake card.
FO = sibling('folders')
D, F_, L_, U_ = 4, 8, 10, 0   # d_type: directory, file, link, unknown
LP_WIDGETS = ('view_grid', 'btn_return', 'btn_selall', 'lp_scan', 'label_title', 'label_status', 'label_row_title', 'label_row_dim', 'label_cap', 'lp_bar', 'img_nb_fade')
SCREEN_Y0, ROW, VIEW_H = FO.SCREEN_Y0, pod_ui.ROW_H, O['GRID_VIEW_H']
CARD = {
    '/mnt/mmc': [('Hi-Res', D), ('.m1plus', D), ('lost+found', D), ('System Volume Information', D), ('RECYCLER', D), ('$RECYCLE.BIN', D), ('.LOST.DIR', D), ('.fseventsd', D), ('.Spotlight-V100', D), ('.Trashes', D),
                 ('lockscreenimage', D), ('._hidden', D), ('Android', D), ('readme.mp3', F_), ('Linked', L_), ('Weird', U_), ('NotADir', U_), ('Downloads', D), ('10 Ten', D), ('2 Two', D), ('album', D), ('Albums', D), ('Classical', D)],
    '/mnt/mmc/Hi-Res': [('DSD', D), ('FLAC 24-96', D), ('FLAC 24-192', D), ('MQA', D), ('x.flac', F_)],
    '/mnt/mmc/Hi-Res/DSD': [('Mastered', D)], '/mnt/mmc/Hi-Res/DSD/Mastered': [('deep', D)], '/mnt/mmc/Hi-Res/DSD/Mastered/deep': [],
    '/mnt/mmc/Hi-Res/FLAC 24-96': [('a.flac', F_)], '/mnt/mmc/Hi-Res/FLAC 24-192': [], '/mnt/mmc/Hi-Res/MQA': [('b.mqa', F_), ('.hid', D)],
    '/mnt/mmc/Albums': [('Rock', D), ('Pop', D)], '/mnt/mmc/Albums/Rock': [('Deep', D)], '/mnt/mmc/Albums/Pop': [], '/mnt/mmc/Albums/Rock/Deep': [],
    '/mnt/mmc/Android': [('data', D)], '/mnt/mmc/Android/data': [('com.example', D)],
    '/mnt/mmc/Linked': [('k', D)], '/mnt/mmc/Weird': [('w', D)], '/mnt/mmc/Downloads': [], '/mnt/mmc/Classical': [('Bach', D)], '/mnt/mmc/10 Ten': [], '/mnt/mmc/2 Two': [], '/mnt/mmc/album': [],
}
ROOT_ORDER = ['2 Two', '10 Ten', 'album', 'Albums', 'Android', 'Classical', 'Downloads', 'Hi-Res', 'Linked', 'Weird']   # (cc_key_cmp: digit runs by value, case folded: "album" is shorter than "Albums")


class PM(FO.FM):
    """The picker's machine: the folders machine's page, the fake card, the scan dialog's context and the strings pushed on the deque."""
    def __init__(self):
        super().__init__()
        self.pushed, self.ctxs, self.nav = [], [], []

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('_deque_push_back', 'readdir', 'navigator_to_with_context', 'navigator_back', 'toolsCheckMount', 'stop_player'): return super()._hook(u, address, size, _)
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        if name == '_deque_push_back': self.pushed.append(self.read_cstr(a1))
        if name == 'readdir':   # one dirent buffer, reused (the picker copies a name at once; a 4000-entry folder would use the heap up)
            ent = self.open_dirs.get(a0); ret = 0
            if ent:
                nm, typ = ent.pop(0)
                if not hasattr(self, 'dirent'): self.dirent = self.alloc(280)
                self.u.mem_write(self.dirent + 10, bytes([typ]) + nm.encode('latin-1') + b'\0'); ret = self.dirent
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if name == 'navigator_to_with_context' and self.read_cstr(a0) == 'dialog/scanmusic_dialog':
            self.ctxs.append([self.word(a1 + 4 * i) for i in range(4)]); self.nav.append(('dialog', len(self.pushed)))
        if name == 'navigator_back': self.nav.append(('back',))
        if name in ('toolsCheckMount', 'stop_player'):
            self.calls.append((name,)); u.reg_write(UC_MIPS_REG_V0, 1); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        return super()._hook(u, address, size, _)


def picker(card=None):
    m = PM()
    m.mtimes, m.statx_paths, m.copy_queue = {}, [], True
    m.window, m.load_image = 0x20001000, 0
    m.layer, m.path, m.offs, m.shown = 0, '', [], []
    m.listing = {k: list(v) for k, v in (card or CARD).items()}
    for w in LP_WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.images = {'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)}
    win, lv, sv, view = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_grid']
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['lupick_scrollview'] = sv
    for off, v in ((4, 0), (8, 320), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
    m.setword(m.widgets['label_title'] + 8, 156)
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    m.sv, m.view = sv, view
    m.call(PSYMS['lupick_open'], count=900000000)
    return m


def lp_paint(m):
    ev = m.paint_event()
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - m.word(m.sv + O['SC_YOFF'])) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['lp_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(zip(m.texts, m.text_styles)), list(m.fills)


def lp_probe(m):
    for _ in range(40): m.call(PSYMS['lp_on_probe'], a0=0, count=40000000)


def lp_tap(m, r, x=150, top=44):
    m.calls.clear()
    y = top + r * ROW + 20
    m.touch('down', x, SCREEN_Y0 + y, 1000, fn='lp_on_down'); m.touch('up', x, SCREEN_Y0 + y, 1080, fn='lp_on_up')


def lp_sweep(m, n):
    """Scroll through the level, probing and painting each stretch: (names by row, the rows with a chevron)."""
    rows, chev = {}, set()
    top = 44 if m.wtext.get(m.widgets['label_title']) == 'Choose Folders' else 10
    for off in range(0, top + n * ROW + 90, 150):
        m.setword(m.sv + O['SC_YOFF'], off); lp_probe(m)
        blits, texts, fills = lp_paint(m)
        for (t, r), s in texts:
            if s in ('label_row_title', 'label_row_dim'): rows[(r[1] + off - top) // ROW if isinstance(r, (tuple, list)) else len(rows)] = t
        for b in blits:
            if (b[2][2], b[2][3]) == (10, 16): chev.add((b[2][1] + off - top - (ROW - 1 - 16) // 2) // ROW)
    m.setword(m.sv + O['SC_YOFF'], 0)
    return [rows[i] for i in sorted(rows)], sorted(chev)


def lp_state(m, r): return m.call(PSYMS['lp_state'], a0=r, count=4000000)
def lp_states(m, n): return [lp_state(m, r) for r in range(n)]
def lp_click(m, name): m.click(name, count=400000000)
def lp_back(m): m.calls.clear(); lp_click(m, 'btn_return')
def pill(m): return m.wtext[m.widgets['lp_scan']], vis(m, 'lp_scan')[1]
def sa(m): return m.wtext[m.widgets['btn_selall']], vis(m, 'btn_selall')[1], m.props.get((m.widgets['btn_selall'], 'enable'), 1)   # label, sensitive, enable


def picker_tests(ctx):
    """The folder picker: the listing and its filter, the toggle and enter rules, covered descendants, Select All per level, the count, Back, the scan."""
    expect = ctx.expect
    m = picker()
    expect(('window_open', 'm1plus_lupick') in m.calls and m.u.mem_read(m.view, 1) is not None, 'lupick_open opens the window m1plus_lupick')
    rows, chev = lp_sweep(m, len(ROOT_ORDER))
    expect(rows == ROOT_ORDER, f'the root lists the card\'s folders in the lists\' name order, without dot names, junk names, files or the lockscreen folder ({rows})')
    expect([t for (t, r), s in lp_paint(m)[1] if s == 'label_cap'] == ['MUSIC CARD'], 'the root has the caption MUSIC CARD')
    expect(chev == [ROOT_ORDER.index(n) for n in ('Albums', 'Android', 'Classical', 'Hi-Res', 'Linked', 'Weird')],
           f'a chevron on the folders that hold a folder (a link and an unknown type are probed by opendir; Android shows one, its data folder is empty): {chev}')
    m2 = picker({'/mnt/mmc': [('Android', D), ('Pics', D)], '/mnt/mmc/Android': [('data', D)], '/mnt/mmc/Android/data': [('com.x', D)], '/mnt/mmc/Pics': [('p', D)]})
    lp_sweep(m2, 2); lp_tap(m2, 0, 150, 44)
    expect(lp_sweep(m2, 1) == (['data'], []), 'Android > data: listed, but with no chevron (stock lists nothing inside /mnt/mmc/Android/data)')
    m2.listing['/mnt/mmc/Android/data'] = []; lp_tap(m2, 0, 150, 10)
    expect(lp_state(m2, 0) == 1, 'a row with no chevron toggles, it is not entered (a tap on Android/data selects it)')
    lp_back(m2); lp_tap(m2, 1, 150, 44); m2.listing['/mnt/mmc/Pics/p'] = []
    expect(lp_sweep(m2, 1) == (['p'], []), 'Pics > p')
    m3 = picker({'/mnt/mmc': [('Pics', D)], '/mnt/mmc/Pics': [('p', D)]})
    lp_sweep(m3, 1); m3.listing['/mnt/mmc/Pics'] = [('x.mp3', F_)]; lp_tap(m3, 0, 150, 44)
    expect(not lp_sweep(m3, 0)[0] and m3.wtext[m3.widgets['label_status']] == 'No folders' and vis(m3, 'label_status')[0] == 1 and vis(m3, 'view_grid')[0] == 0, 'a level with no folder says "No folders"')
    # the pill and the tap rules
    expect(pill(m) == ('Scan Folders', 0), f'nothing chosen: "Scan Folders", dimmed and inert ({pill(m)})')
    m.calls.clear(); lp_click(m, 'lp_scan')
    expect(not m.ctxs and 'stop_player' not in m.names(), 'the dimmed pill starts nothing')
    ix = ROOT_ORDER.index
    lp_tap(m, ix('Downloads'), 150)
    expect(lp_state(m, ix('Downloads')) == 1 and pill(m) == ('Scan 1 Folder', 1), f'a tap on a row with no subfolders toggles it: "Scan 1 Folder", live ({pill(m)})')
    lp_tap(m, ix('Albums'), 30)
    expect(lp_state(m, ix('Albums')) == 1 and pill(m)[0] == 'Scan 2 Folders', 'a tap on the circle of a row with subfolders toggles it')
    lp_tap(m, ix('Albums'), 30)
    expect(lp_state(m, ix('Albums')) == 0 and pill(m)[0] == 'Scan 1 Folder', 'a second tap on the circle clears it')
    lp_tap(m, ix('Hi-Res'), 150)
    expect(m.wtext[m.widgets['label_title']] == 'Hi-Res' and lp_sweep(m, 4)[0] == ['DSD', 'FLAC 24-96', 'FLAC 24-192', 'MQA'] and pill(m)[0] == 'Scan 1 Folder', 'a tap on the rest of a row with subfolders opens it; the title is its name; the count stays')
    lp_tap(m, 0, 30, 10); lp_tap(m, 1, 30, 10)
    expect(pill(m)[0] == 'Scan 3 Folders' and lp_states(m, 4) == [1, 1, 0, 0], 'the selection is kept across levels and counted over all of them')
    lp_tap(m, 0, 150, 10)
    expect(m.wtext[m.widgets['label_title']] == 'DSD' and lp_sweep(m, 1)[0] == ['Mastered'], 'DSD has a folder inside: the rest of its row opens it')
    lp_back(m)
    expect(m.wtext[m.widgets['label_title']] == 'Hi-Res' and lp_states(m, 4) == [1, 1, 0, 0], 'Back pops one level, the marks as they were')
    lp_back(m)
    expect(m.wtext[m.widgets['label_title']] == 'Choose Folders' and 'navigator_back' not in m.names() and lp_state(m, ix('Downloads')) == 1, 'Back at Hi-Res returns to the root')
    lp_back(m)
    expect('navigator_back' in m.names(), 'Back at the root leaves the page')
    # covered descendants and dedupe
    m = picker()
    lp_tap(m, ix('Hi-Res'), 150); lp_tap(m, 0, 30, 10); lp_tap(m, 3, 30, 10); lp_back(m)
    expect(pill(m)[0] == 'Scan 2 Folders', 'DSD and MQA chosen inside Hi-Res')
    lp_tap(m, ix('Hi-Res'), 30)
    expect(lp_state(m, ix('Hi-Res')) == 1 and pill(m)[0] == 'Scan 1 Folder', 'choosing Hi-Res takes its chosen folders out of the set: nothing is scanned twice')
    lp_tap(m, ix('Hi-Res'), 150)
    expect(lp_states(m, 4) == [2, 2, 2, 2], 'inside a chosen folder every row is selected, dimmed and covered')
    lp_tap(m, 1, 30, 10)
    expect(lp_states(m, 4) == [2, 2, 2, 2] and pill(m)[0] == 'Scan 1 Folder', 'a covered row cannot be toggled')
    blits, texts, fills = lp_paint(m)
    expect([s for (t, r), s in texts] == ['label_row_dim'] * 4 and any(f[0] == 0xa01e1c1c for f in fills), 'covered rows have the dimmed name and a dimmed mark')
    lp_tap(m, 0, 150, 10); lp_tap(m, 0, 150, 10)
    expect(m.wtext[m.widgets['label_title']] == 'Mastered' and lp_states(m, 1) == [2], 'a covered folder with subfolders can still be opened, its rows covered too')
    # Select All: the rows of this level only
    m = picker()
    lp_click(m, 'btn_selall')
    expect(lp_states(m, 10) == [1] * 10 and pill(m)[0] == 'Scan 10 Folders', 'Select All chooses every row of the level')
    expect(m.wtext[m.widgets['btn_selall']] == 'Deselect All', 'with every row chosen the button reads Deselect All')
    lp_tap(m, ix('Hi-Res'), 150); lp_click(m, 'btn_selall')
    expect(lp_states(m, 4) == [2] * 4 and pill(m)[0] == 'Scan 10 Folders', 'inside a chosen folder Select All has nothing to add (everything is covered)')
    expect(sa(m) == ('Deselect All', 0, 0), f'inside a chosen folder the button does nothing, so it is dimmed and inert ({sa(m)})')
    lp_back(m); lp_click(m, 'btn_selall')
    expect(lp_states(m, 10) == [0] * 10 and pill(m) == ('Scan Folders', 0), 'Select All with every row chosen clears the level')
    expect(m.wtext[m.widgets['btn_selall']] == 'Select All', 'and reads Select All again')
    lp_tap(m, ix('Hi-Res'), 150); lp_tap(m, 0, 30, 10); lp_click(m, 'btn_selall')
    expect(lp_states(m, 4) == [1] * 4 and pill(m)[0] == 'Scan 4 Folders', 'Select All inside a level: its folders only (nothing from the root)')
    lp_back(m); lp_click(m, 'btn_selall')
    expect(lp_state(m, ix('Hi-Res')) == 1 and pill(m)[0] == 'Scan 10 Folders', 'Select All at the root chooses the rest; Hi-Res takes its chosen folders in')
    # the scan: stock's btn_startscan
    m = picker()
    lp_tap(m, ix('Downloads'), 150); lp_tap(m, ix('Albums'), 30); lp_tap(m, ix('Hi-Res'), 150); lp_tap(m, 1, 30, 10)
    m.calls.clear(); lp_click(m, 'lp_scan')
    names_ = m.names()
    expect(m.pushed == ['/mnt/mmc/Downloads', '/mnt/mmc/Albums', '/mnt/mmc/Hi-Res/FLAC 24-96'] or sorted(m.pushed) == sorted(['/mnt/mmc/Downloads', '/mnt/mmc/Albums', '/mnt/mmc/Hi-Res/FLAC 24-96']),
           f'the deque holds the chosen full paths ({m.pushed})')
    i = {n: names_.index(n) for n in ('stop_player', '_create_deque', 'navigator_back', 'navigator_to_with_context')}
    expect(i['stop_player'] < i['_create_deque'] < i['navigator_back'] < i['navigator_to_with_context'] and ('_create_deque', 'char*') in m.calls and 'deque_destroy' not in names_,
           'stop_player, the char* deque, navigator_back (so the dialog returns to Update Library), then the dialog; the deque is not destroyed while the worker reads it')
    dq = m.ctxs[0][0]
    expect(len(m.ctxs) == 1 and m.ctxs[0][1:] == [0, 1, 0] and dq in m.deques and len(m.deques[dq]) == 3, f'the dialog\'s context is {{deque, 0, 1, 0}}, as stock\'s btn_startscan ({m.ctxs})')
    m.call(PSYMS['lp_scan_done'], count=400000)
    expect('deque_destroy' in m.names() and dq not in m.deques, 'the deque is destroyed at the first finished tick (lp_scan_done, called by lu_scan_finish)')
    m.calls.clear(); m.call(PSYMS['lp_scan_done'], count=400000)
    expect('deque_destroy' not in m.names(), 'and only once')
    # Select All with more folders than the set holds (256): the first tap fills it and says so, the second clears the level
    m = picker({'/mnt/mmc': [('f%03d' % i, D) for i in range(257)]})
    lp_click(m, 'btn_selall'); said = toasts(m)
    held = lambda: sum(lp_state(m, r) == 1 for r in range(257))
    expect(held() == 256 and pill(m)[0] == 'Scan 256 Folders' and said == ['You can choose up to 256 folders.'], f'257 folders: Select All chooses 256 and says why ({held()}, {said})')
    expect(sa(m) == ('Deselect All', 1, 1), f'the set is full and the last row cannot go in: the next tap clears, so the button reads Deselect All ({sa(m)})')
    lp_click(m, 'btn_selall')
    expect(held() == 0 and pill(m) == ('Scan Folders', 0), 'a second tap clears the level (it could not add the last one)')
    # at the limit, choosing a parent that replaces its chosen folders is allowed: the size after the replacement counts (size - dropped + 1)
    tree = {'/mnt/mmc': [('Music', D), ('Other', D)], '/mnt/mmc/Music': [('s%03d' % i, D) for i in range(256)]}
    for how in ('tap', 'selall'):
        m = picker(tree)
        lp_tap(m, 0, 150); lp_click(m, 'btn_selall'); lp_back(m)
        expect(pill(m)[0] == 'Scan 256 Folders', 'the 256 subfolders of Music are chosen')
        if how == 'tap': lp_tap(m, 0, 30)
        else: lp_click(m, 'btn_selall')
        said = toasts(m)
        expect(lp_state(m, 0) == 1 and pill(m)[0] == ('Scan 2 Folders' if how == 'selall' else 'Scan 1 Folder') and said == [], f'at the limit, {how} on the parent replaces its 256 chosen folders ({pill(m)}, {said})')
    m = picker({'/mnt/mmc': [('Music', D), ('Other', D)], '/mnt/mmc/Music': [('s%03d' % i, D) for i in range(255)] + [('x', D)], '/mnt/mmc/Other': []})
    lp_tap(m, 1, 30); lp_tap(m, 0, 150); lp_click(m, 'btn_selall'); lp_back(m)
    lp_tap(m, 0, 30); said = toasts(m)
    expect(pill(m)[0] == 'Scan 2 Folders' and lp_state(m, 0) == 1, 'a full set (255 + 1 elsewhere) still lets the parent replace its 255')
    # Select All at the limit takes the folders that fit: a parent whose chosen descendants free room first, then the siblings
    for kids, case in ((256, 'A: 256 chosen under Music, Alpha before it'), (255, 'B: 255 chosen under Music and Alpha')):
        m = picker({'/mnt/mmc': [('Alpha', D), ('Music', D)], '/mnt/mmc/Music': [('s%03d' % i, D) for i in range(kids)], '/mnt/mmc/Alpha': []})
        if kids == 255: lp_tap(m, 0, 30)
        lp_tap(m, 1, 150); lp_click(m, 'btn_selall'); lp_back(m)
        expect(pill(m)[0] == 'Scan 256 Folders', f'case {case}: the set is full')
        toasts(m); lp_click(m, 'btn_selall'); said = toasts(m)
        expect(lp_states(m, 2) == [1, 1] and pill(m)[0] == 'Scan 2 Folders' and said == [], f'case {case}: Select All at the root chooses both rows, Music replacing its folders ({lp_states(m, 2)}, {pill(m)}, {said})')
    # more than fits: the rows that free room go in first, the rest in order until full, the limit is told; a further tap clears
    m = picker({'/mnt/mmc': [('Alpha', D), ('Beta', D), ('Music', D)], '/mnt/mmc/Music': [('s%03d' % i, D) for i in range(256)], '/mnt/mmc/Alpha': [], '/mnt/mmc/Beta': []})
    lp_tap(m, 2, 150); lp_click(m, 'btn_selall'); lp_back(m); toasts(m)
    lp_click(m, 'btn_selall'); said = toasts(m)
    expect(lp_states(m, 3) == [1, 1, 1] and said == [], 'a freed Music leaves room for both siblings')
    m = picker({'/mnt/mmc': [('f%03d' % i, D) for i in range(260)] + [('zMusic', D)], '/mnt/mmc/zMusic': [('s%03d' % i, D) for i in range(250)]})
    lp_tap(m, 260, 150); lp_click(m, 'btn_selall'); lp_back(m); toasts(m)
    lp_click(m, 'btn_selall'); said = toasts(m)
    n_sel = sum(lp_state(m, r) == 1 for r in range(261))
    expect(lp_state(m, 260) == 1 and n_sel == 256 and said == ['You can choose up to 256 folders.'] and pill(m)[0] == 'Scan 256 Folders', f'too many: the parent that frees room first, then the first siblings to 256 ({n_sel}, {said})')
    # no memory for a path is not the limit: Select All stops and keeps what is chosen
    m = picker({'/mnt/mmc': [('A', D), ('Bb', D)], '/mnt/mmc/A': [], '/mnt/mmc/Bb': []})
    lp_tap(m, 0, 30); m.calloc_fail_size = len('/mnt/mmc/Bb') + 1; toasts(m)
    lp_click(m, 'btn_selall'); said = toasts(m)
    expect(lp_states(m, 2) == [1, 0] and said == [], f'Select All when a path cannot be allocated: the chosen folder stays, no limit message ({lp_states(m, 2)}, {said})')
    # a folder whose first folder comes after 4000 files is still browsable
    m = picker({'/mnt/mmc': [('Big', D)], '/mnt/mmc/Big': [('t%04d.mp3' % i, F_) for i in range(4000)] + [('Late', D)], '/mnt/mmc/Big/Late': []})
    rows, chev = lp_sweep(m, 1)
    expect(rows == ['Big'] and chev == [0], f'a probe that gave up after 4000 entries still shows the chevron ({chev})')
    lp_tap(m, 0, 150, 44)
    expect(lp_states(m, 0) == [] and lp_sweep(m, 1)[0] == ['Late'], 'and the tap opens it')
    # the pill: dimmed through the enable flag too (the style's disable state follows it, not sensitive)
    m = picker()
    en = lambda: m.props.get((m.widgets['lp_scan'], 'enable'), 1)
    expect(en() == 0 and pill(m)[1] == 0, 'no folder chosen: the pill is disabled and insensitive')
    lp_tap(m, 0, 30, 44)
    expect(en() == 1 and pill(m)[1] == 1, 'a folder chosen: enabled and sensitive')
    lp_tap(m, 0, 30, 44)
    expect(en() == 0 and pill(m)[1] == 0, 'and none again: disabled')
    # a long level: every row reachable, the list bounded
    big = {'/mnt/mmc': [('d%04d' % i, D) for i in range(2000)]}
    m = picker(big)
    rows, chev = lp_sweep(m, 1500)
    expect(len(rows) == 1500 and rows[0] == 'd0000' and rows[-1] == 'd1499' and chev == [], 'a level is read up to 1500 folders (LP_MAX), in order; none holds a folder here')


def picker_asset_tests(ctx):
    """The picker's asset and texts."""
    expect, P = ctx.expect, pod_pages
    pg = P.LUPICK_PAGE
    expect((pg.key, pg.title, pg.kind) == ('m1plus_lupick', 'Choose Folders', 'lupick') and P.PAGES[P.page_index('m1plus_lupick')] is pg, 'the page m1plus_lupick, titled Choose Folders, in the page table')
    t = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_lupick.bin'), 'rb').read())
    expect(t.name == 'm1plus_lupick_page' and all(t.find(n) is not None for n in LP_WIDGETS + ('lupick_scrollview', 'lupick_listview')), 'every widget the payload looks up is in the asset')
    nb = {c.name: c for c in t.find('navigationbar_view').children}
    expect((nb['btn_selall'].x + nb['btn_selall'].w, nb['btn_selall'].y, nb['btn_selall'].h) == (O['SG_SELALL_R'], 4, 42) and nb['btn_selall'].get('visible') != 'false' and nb['btn_selall'].get('sensitive') != 'false' and nb['btn_backtoplayer'].get('visible') == 'false' and nb['btn_backtoplayer'].get('sensitive') == 'false' and nb['label_title'].w == O['SG_SELALL_X'] - 58,
           'the navbar: Back, the title to the Select All glass pill (right edge 311, shown), Now Playing hidden')
    bar, sc = t.find('lp_bar'), t.find('lp_scan')
    expect(bar.y == 450 - O['SG_BAR_H'] and sc.get('style:normal:bg_color') == '#E5E5EA' and sc.get('style:normal:text_color') == '#000000' and sc.get('style:disable:bg_color') == '#2C2C2E' and sc.get('style:disable:text_color') == '#98989D',
           'the bottom pill: light grey with black text live, dark grey with grey text dimmed')
    import pod_i18n
    keys = ('Scan %d Folders', 'Scan 1 Folder', 'Scan Folders', 'MUSIC CARD', 'No folders', 'You can choose up to 256 folders.')
    expect(all(k in pod_i18n.TEXT and all(pod_i18n.TEXT[k][loc] for loc in pod_i18n.LOCALES) for k in keys), 'every picker text is translated in all 13 languages')
    expect(all(pod_i18n.TEXT['Scan %d Folders'][loc].count('%d') == 1 for loc in pod_i18n.LOCALES), 'the count goes where %d is')


SECTIONS = [state_tests, hook_tests, entry_tests, slot_tests, page_tests, picker_tests, picker_asset_tests]

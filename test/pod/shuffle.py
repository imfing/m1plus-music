"""Shuffle: the page rows, Songs / Albums / Folders, errors."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


# ======================= Shuffle (patch/shuffle.c) =======================
def song(m, path, album='', track=0, disc=0, cue=0, kind=8):
    """A songtable row as getAllMusic's callback leaves it (@0x4e9058)."""
    name = path.rsplit('/', 1)[1]
    r = m.record(album=album, path=path, title=name, name=name)
    m.setword(r + O['REC_TRACK'], track); m.setword(r + O['REC_DISC'], disc)
    m.setword(r + O['REC_CUE_START'], cue); m.setword(r + O['REC_TYPE'], kind)
    return r


FLAG_FILE = '/mnt/data/m1plus/playback-shuffle'
STR_FIELDS = ('REC_PATH', 'REC_TITLE', 'REC_ALBUM', 'REC_ARTIST', 'REC_NAME')
flag_on = lambda m: m.fs.get(FLAG_FILE) == b'1\n'   # the Shuffle flag as saved


class HookedMachine(Machine):
    """The build's hook on mclSetPlayMode in the loop: a call of stock's function runs sh_set_mode first, as the patched prologue does (the trampoline is the harness's
    stock_setmode). mclLoadPlayList's hook is run by the test itself (start_player is not emulated).

    Two "threads" (spawn / run_thread below) can share the machine: each is a saved CPU context on its own stack, and the scheduler is the test. With `sched` on, the
    payload mutex is modelled (pthread_mutex_lock of a held mutex stops the caller where it is, to be retried when it is resumed) and a thread can be paused by
    the mocks themselves: after `yield_at` memcpy calls of thread `yield_thread` (mid-permutation) or right after stock's loader trampoline (`pause_load`)."""
    sched = False
    owner, cur, blocked, yield_thread, yield_at, copies, pause_load, pause_clear = None, '', None, '', 0, 0, False, False
    pop_stop = 0   # pause the running thread right after the pop_back that makes the machine's pop counter this (Clear paused mid-removal)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name == 'mclSetPlayMode':
            self.calls.append(('mclSetPlayMode', u.reg_read(UC_MIPS_REG_A0)))
            u.reg_write(UC_MIPS_REG_PC, PSYMS['sh_set_mode'])
            return
        if self.sched:
            if name == 'pthread_mutex_lock':
                if self.owner not in (None, self.cur):   # held by the other thread: wait here (the instruction is retried on resume)
                    self.blocked = self.cur; u.emu_stop(); return
                self.owner = self.cur
            elif name == 'pthread_mutex_unlock': self.owner = None
            elif name == 'stock_loadplaylist': self.loads_held.append(self.owner == self.cur)
            elif name == 'deque_clear': self.clears_held.append(self.owner == self.cur)
            self.events.append((self.cur, name))
        super()._hook(u, address, size, _)
        if self.sched and ((name == 'stock_loadplaylist' and self.pause_load) or (name == 'deque_clear' and self.pause_clear) or (name == 'memcpy' and self.cur == self.yield_thread and self.yield_at)):
            if name == 'memcpy': self.copies += 1
            if name in ('stock_loadplaylist', 'deque_clear') or self.copies == self.yield_at: u.emu_stop()
        if self.sched and name == 'cstl_pop_back' and self.pops == self.pop_stop: u.emu_stop()


def shuffle_machine(rows, mode=0, clock=1, present=True, flag=False):
    """A library (rows of song() arguments) that loadLocalClassList(0xf001) loads, and a stock
    loadSongList that copies it as the Songs page's row handler gets it."""
    m = HookedMachine()
    if flag: m.fs[FLAG_FILE] = b'1\n'
    m.stock_songlist = True
    m.mode, m.clock = mode, clock
    m.showlist = [song(m, *r) for r in rows]
    if present:
        for r in m.showlist: m.present.add(m.read_cstr(m.word(r + O['REC_PATH'])))
    return m


def field(m, r, off): return m.read_cstr(m.word(r + off))


def runs(q, key):
    """The queue as consecutive runs of equal key(record)."""
    out = []
    for r in q:
        k = key(r)
        if not out or out[-1][0] != k: out.append((k, []))
        out[-1][1].append(r)
    return out


def shuffle_page():
    """(index, page) of the page holding the Shuffle rows: the Shuffle page the menu's one Shuffle
    row opens (q2-pod's Library > Shuffle)."""
    return next((i, p) for i, p in enumerate(pod_pages.PAGES)
                if any(r.action == pod_pages.ACT_SHUFFLE for r in p.rows))


def shuffle_tests(ctx):
    expect, menu = ctx.expect, ctx.page
    play = PSYMS['shuffle_play']
    spi, page = shuffle_page()
    rows0 = PSYMS[f'pod_rows_{spi}']
    K = {pod_pages.SHUFFLE_SONGS: 'Songs', pod_pages.SHUFFLE_ALBUMS: 'Albums', pod_pages.SHUFFLE_FOLDERS: 'Folders'}
    COUNT = 50000000

    # 26. The rows: one per kind, stock-styled, no chevron (they play, as Now Playing's row), and the payload's
    #     own row table binds them to ACT_SHUFFLE and the kind. Stage H: the menu has one Shuffle row, with a
    #     chevron, opening the Shuffle page, whose rows are the three, in that order.
    import awtk_ui
    at = [i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_SHUFFLE]
    if spi == 0:
        cover = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_COVER)
        expect(at == [cover + 1, cover + 2, cover + 3] and [page.rows[i].arg for i in at] == sorted(K),
               f'Shuffle Songs, Albums, Folders follow Cover Flow ({at})')
    else:
        shuffle_page_tests(expect, menu, spi, page)
        expect(at == [0, 1, 2] and [page.rows[i].arg for i in at] == sorted(K) and len(page.rows) == 3,
               f'the Shuffle page lists Shuffle Songs, Albums, Folders ({at})')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/ui/{page.key}.bin'), 'rb').read())
    items = {w.name: w for w in tree.walk() if w.type == 'list_item'}
    for i in at:
        w = items.get(f'pod_row{i}')
        labs = [pod_i18n.shown_english(c) for c in w.children if c.type == 'hscroll_label'] if w else []
        expect(labs == [page.rows[i].label] and not any(c.type == 'image' and c.name != 'pod_icon' for c in w.children) and
               all(c.get('sensitive') == 'false' for c in w.children if c.name == 'pod_icon'),
               f'{page.key} row {i} reads "{page.rows[i].label}", no chevron ({labs})')
        m = Machine()
        name, action, arg = (m.word(rows0 + 12 * i + o) for o in (0, 4, 8))
        expect((m.read_cstr(name), action, arg) == (f'pod_row{i}', pod_pages.ACT_SHUFFLE, page.rows[i].arg),
               f'the payload row table binds pod_row{i} to ACT_SHUFFLE {page.rows[i].arg}')

    lib = [(f'/mnt/mmc/m/{d}/{t:02d}.flac', f'Album {d}', t) for d in 'ABCDE' for t in range(1, 4)]

    # 27. Shuffle Songs from its menu row: the Songs page's stock sequence with its class, the play
    #     mode set to Shuffle the way the Play settings page sets it, then Now Playing.
    m = shuffle_machine(lib)
    m.call(PSYMS['on_row'], a0=rows0 + 12 * at[0], count=COUNT)
    n = m.names()
    seq = [c for c in n if c in ('loadLocalClassList', '_create_deque', 'loadSongList', 'access', 'mclSetPlayMode',
                                 'notifyPlayMode', 'dmrSendPlayMode', 'write_int_config',
                                 'navigator_to_with_context', 'deque_destroy')]
    seq = [c for i, c in enumerate(seq) if c != 'access' or 'access' not in seq[:i]]   # (the hook's kill switch checks add accesses: the first one is the song's)
    expect(seq == ['loadLocalClassList', '_create_deque', 'loadSongList', 'access', 'mclSetPlayMode', 'notifyPlayMode',
                   'dmrSendPlayMode', 'write_int_config', 'navigator_to_with_context', 'deque_destroy'],
           f'Shuffle Songs runs the stock sequence in order ({seq})')
    expect(('loadLocalClassList', O['CLASS_ALL_SONGS']) in m.calls, "the library is the Songs page's query (0xf001)")
    ls = [c for c in m.calls if c[0] == 'loadSongList']
    expect(ls and ls[0][3] == O['CLASS_ALL_SONGS'], f'loadSongList with the Songs class ({ls})')
    expect(('mclSetPlayMode', O['MODE_SHUFFLE']) in m.calls and ('dmrSendPlayMode', O['MODE_SHUFFLE']) in m.calls
           and ('write_int_config', O['MODE_SHUFFLE'], 'PLAYSET', 'PLAYMODE') in m.calls and m.mode == O['MODE_ORDER'] and flag_on(m),
           'the request for Shuffle is asked as Play settings asks it (saved as [PLAYSET] PLAYMODE=2) and the hook turns it into the flag on with stock in List play')
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    q, idx = m.played
    expect(len(nav) == 1 and nav[0][1] == 'playing_page' and nav[0][3] == O['CLASS_ALL_SONGS']
           and nav[0][4] == O['PLAY_MODE'], f'Now Playing opens with {{queue, index, 0xf001, 2}} ({nav})')
    expect([field(m, r, O['REC_PATH']) for r in q] == [r[0] for r in lib],
           "the queue is the whole library in the library's order (stock Shuffle draws the play order)")
    expect(0 <= idx < len(lib) and nav[0][2] == idx, f'it starts on a song of the library ({idx})')
    expect(all(m.word(r + O['REC_CLASS']) == O['CLASS_ALL_SONGS'] for r in q), 'every queued song carries the class')
    expect(m.word(pod.DATA['G_CLASS_TYPE'][0]) == O['CLASS_ALL_SONGS'], 'g_class_type is the Songs class')
    expect(not any(c in n for c in ('timer_add', 'pthread_create', 'widget_on', 'window_open')),
           'a shuffle leaves nothing behind: no timer, thread, handler or page of its own')
    starts = set()
    for clock in range(1, 41):
        m = shuffle_machine(lib, clock=clock * 7919)
        m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT)
        starts.add(m.played[1])
    expect(len(starts) >= 8, f'the first song is drawn at random ({sorted(starts)})')
    m = shuffle_machine(lib)
    firsts = []
    for _ in range(6):   # taps in a row keep drawing (the generator is seeded once)
        m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT); firsts.append(m.played[1])
    expect(len(set(firsts)) >= 3, f'repeated taps start on different songs ({firsts})')

    # 28. Duplicate file names (01.flac in every album): loadSongList's match by name would always
    #     give the first; the drawn song itself plays.
    dup = [(f'/mnt/mmc/m/{d}/01.flac', f'Album {d}', 1) for d in 'ABCDEFGH']
    starts = set()
    for clock in range(1, 31):
        m = shuffle_machine(dup, clock=clock * 104729)
        m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT)
        starts.add(m.played[1])
    expect(len(starts) >= 4, f'with duplicate names the start is still random ({sorted(starts)})')

    # 29. Already in Shuffle: nothing is written; Shuffle on over Repeat all becomes List play under it.
    m = shuffle_machine(lib, flag=True)
    m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT)
    expect(not any(c[0] in ('mclSetPlayMode', 'write_int_config') for c in m.calls) and m.played,
           'Shuffle Songs with Shuffle on plays without touching the setting')
    m = shuffle_machine(lib, mode=O['MODE_REPEAT_ALL'], flag=True)
    m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT)
    expect(m.mode == O['MODE_ORDER'] and flag_on(m) and ('write_int_config', O['MODE_SHUFFLE'], 'PLAYSET', 'PLAYMODE') in m.calls and m.played,
           'Shuffle Songs with Shuffle on and Repeat all: the flag stays, stock goes to List play')

    # 30. Shuffle Albums: every album once, as one run, in a random order; each album in the stock
    #     album page's order (disc, then track), untagged ones by file name; album names grouped as
    #     the stock Albums list groups them (NOCASE); from the first album's first track.
    albums = [('/mnt/mmc/x/kob/03.flac', 'Kind of Blue', 3), ('/mnt/mmc/x/ar/02.flac', 'Abbey Road', 2),
              ('/mnt/mmc/x/u/b.mp3', '', 0), ('/mnt/mmc/x/kob/01.flac', 'Kind of Blue', 1),
              ('/mnt/mmc/x/dbl/cd2/01.flac', 'Double', 1, 2), ('/mnt/mmc/x/ar/01.flac', 'abbey road', 1),
              ('/mnt/mmc/x/u/a.mp3', '', 0), ('/mnt/mmc/x/dbl/cd1/02.flac', 'Double', 2, 1),
              ('/mnt/mmc/x/kob/02.flac', 'Kind of Blue', 2), ('/mnt/mmc/x/dbl/cd1/01.flac', 'Double', 1, 1),
              ('/mnt/mmc/x/ar/03.flac', 'ABBEY ROAD', 3)]
    want = {'kind of blue': ['/mnt/mmc/x/kob/01.flac', '/mnt/mmc/x/kob/02.flac', '/mnt/mmc/x/kob/03.flac'],
            'abbey road': ['/mnt/mmc/x/ar/01.flac', '/mnt/mmc/x/ar/02.flac', '/mnt/mmc/x/ar/03.flac'],
            '': ['/mnt/mmc/x/u/a.mp3', '/mnt/mmc/x/u/b.mp3'],
            'double': ['/mnt/mmc/x/dbl/cd1/01.flac', '/mnt/mmc/x/dbl/cd1/02.flac', '/mnt/mmc/x/dbl/cd2/01.flac']}
    orders, good = set(), True
    for clock in range(1, 25):
        m = shuffle_machine(albums, mode=O['MODE_REPEAT_ALL'], clock=clock * 2654435)
        v = m.call(play, a0=pod_pages.SHUFFLE_ALBUMS, count=COUNT)
        q, idx = m.played
        got = runs(q, lambda r: field(m, r, O['REC_ALBUM']).lower())
        good &= (v == 0 and idx == 0 and len(got) == 4 and len(q) == len(albums)
                 and all([field(m, r, O['REC_PATH']) for r in rs] == want[k] for k, rs in got))
        orders.add(tuple(k for k, _ in got))
    expect(good, 'Shuffle Albums queues each album once, contiguous, in album order, from its first track')
    expect(len(orders) >= 6, f'the albums come in a random order ({len(orders)} orders in 24 taps)')
    expect(not any(c[0] in ('mclSetPlayMode', 'write_int_config') for c in m.calls), 'Shuffle Albums keeps Repeat all')
    expect(m.names().count('calloc') == 2 and m.names().count('free') == 2, 'its index and the group ranks are freed')
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    expect(nav and nav[0][1:] == ('playing_page', 0, O['CLASS_ALL_SONGS'], O['PLAY_MODE']),
           f"Now Playing opens on the first album's first track ({nav})")
    expect(sorted(field(m, r, O['REC_PATH']) for r in m.played[0]) == sorted(a[0] for a in albums)
           and sorted(field(m, r, O['REC_NAME']) for r in m.played[0]) == sorted(a[0].rsplit('/', 1)[1] for a in albums),
           'the in-place reorder moved whole records: every song is there exactly once')
    for start, end in ((O['MODE_SHUFFLE'], O['MODE_ORDER']), (O['MODE_REPEAT_ONE'], O['MODE_ORDER']),
                       (O['MODE_ORDER'], None), (O['MODE_REPEAT_ALL'], None)):
        m = shuffle_machine(albums, mode=start)
        m.call(play, a0=pod_pages.SHUFFLE_ALBUMS, count=COUNT)
        if end is None:
            expect(not any(c[0] == 'mclSetPlayMode' for c in m.calls) and m.played, f'Shuffle Albums keeps mode {start}')
        else:
            expect(('mclSetPlayMode', end) in m.calls and ('write_int_config', end, 'PLAYSET', 'PLAYMODE') in m.calls,
                   f'Shuffle Albums turns mode {start} into List play')

    # 31. Shuffle Folders: by folder (a subfolder is its own), each in file-name order.
    folders = [('/mnt/mmc/B/2.flac',), ('/mnt/mmc/A/b.flac',), ('/mnt/mmc/B/sub/1.flac',),
               ('/mnt/mmc/A/a.flac',), ('/mnt/mmc/B/1.flac',), ('/mnt/mmc/C/x.flac', 'Abbey Road', 1)]
    orders, good = set(), True
    for clock in range(1, 13):
        m = shuffle_machine(folders, clock=clock * 31337)
        m.call(play, a0=pod_pages.SHUFFLE_FOLDERS, count=COUNT)
        q, idx = m.played
        got = runs(q, lambda r: field(m, r, O['REC_PATH']).rsplit('/', 1)[0])
        paths = [[field(m, r, O['REC_PATH']) for r in rs] for _, rs in got]
        good &= (idx == 0 and sorted(k for k, _ in got) == ['/mnt/mmc/A', '/mnt/mmc/B', '/mnt/mmc/B/sub', '/mnt/mmc/C']
                 and all(p == sorted(p) for p in paths))
        orders.add(tuple(k for k, _ in got))
    expect(good, 'Shuffle Folders queues each folder once, contiguous, in file-name order')
    expect(len(orders) >= 4, f'the folders come in a random order ({len(orders)} seen)')

    # 32. An empty library: the stock message box, nothing copied, nothing played, the mode untouched.
    for kind in K:
        m = shuffle_machine([])
        v = m.call(play, a0=kind, count=COUNT)
        expect(v == 0xffffffff and ('toast', 'Update Local Music first', O['MSGINFO_KIND'], O['MSGINFO_MS']) in m.calls
               and not m.played and '_create_deque' not in m.names() and 'mclSetPlayMode' not in m.names(),
               f'an empty library: Shuffle {K[kind]} says "Update Local Music first" and plays nothing')

    # 33. The first song is not on the card (card out, stale library): a message, no play, no mode
    #     change, the queue freed.
    for kind in K:
        m = shuffle_machine(lib, present=False)
        v = m.call(play, a0=kind, count=COUNT)
        expect(v == 0xffffffff and any(c[0] == 'toast' and c[1] == 'Storage unavailable' for c in m.calls)
               and not m.played and 'mclSetPlayMode' not in m.names() and 'deque_destroy' in m.names(),
               f'Shuffle {K[kind]} with the card missing says so and plays nothing')
        m = shuffle_machine(lib, present=False); m.present.add('/tmp/mmc_add')
        v = m.call(play, a0=kind, count=COUNT)
        expect(v == 0xffffffff and [c[1] for c in m.calls if c[0] == 'toast'] == ['File not found'] and not m.played,
               f'Shuffle {K[kind]} with the card in and the first file gone says "File not found" (patch/songops.c so_missing)')

    # 34. No memory for the album index: a message, the queue freed, nothing played.
    m = shuffle_machine(albums); m.calloc_fail = True
    v = m.call(play, a0=pod_pages.SHUFFLE_ALBUMS, count=COUNT)
    expect(v == 0xffffffff and any(c[0] == 'toast' and 'memory' in c[1] for c in m.calls) and not m.played
           and 'deque_destroy' in m.names() and 'mclSetPlayMode' not in m.names(),
           'no memory for the index: Shuffle Albums says so and plays nothing')

    # 35. A huge library: Albums/Folders refuse past SHUFFLE_MAX songs before copying anything;
    #     Songs is the stock Songs path and has no cap of its own.
    m = shuffle_machine([]).count()   # the step limit stops a sort past the cap
    one = song(m, '/mnt/mmc/big/01.flac', 'Big', 1)
    m.present.add('/mnt/mmc/big/01.flac')
    big = O['SHUFFLE_MAX']
    m.showlist = [one] * (big + 1)
    for kind in (pod_pages.SHUFFLE_ALBUMS, pod_pages.SHUFFLE_FOLDERS):
        try: v = m.call(play, a0=kind, count=COUNT)
        except AssertionError: v = None   # still sorting at the step limit: the cap did not hold
        expect(v == 0xffffffff and any(c[0] == 'toast' and c[1] == 'Too many songs to shuffle' for c in m.calls)
               and '_create_deque' not in m.names() and 'calloc' not in m.names(),
               f'{big + 1} songs: Shuffle {K[kind]} refuses before copying the library')
    # exactly SHUFFLE_MAX passes the cap and goes on to allocate the index (refused here, so the
    # harness need not sort 65,536 songs)
    m.played = None
    m.showlist = [one] * big
    m.calloc_fail = True
    v = m.call(play, a0=pod_pages.SHUFFLE_ALBUMS, count=COUNT)
    expect(v == 0xffffffff and ('calloc', 16 * big, 0) in m.calls
           and not any(c[0] == 'toast' and c[1] == 'Too many songs to shuffle' for c in m.calls),
           f'{big} songs pass the cap: the {16 * big}-byte index is the only extra allocation')
    m.calloc_fail = False
    # (PERF only) the cost on a real-shaped library: 128 albums of 16 tracks, every album intact
    if PERF:
        m2 = shuffle_machine([(f'/mnt/mmc/l/{a:03d}/{t:02d}.flac', f'Album {a:03d}', 16 - t) for a in range(128)
                              for t in range(16)]).count()
        v = m2.call(play, a0=pod_pages.SHUFFLE_ALBUMS, count=2000000000)
        got = runs(m2.played[0], lambda r: field(m2, r, O['REC_ALBUM'])) if m2.played else []
        expect(v == 0 and len(got) == 128 and all(len(rs) == 16 and [m2.word(r + O['REC_TRACK']) for r in rs]
                                                  == list(range(1, 17)) for _, rs in got),
               '2048 songs in 128 albums: every album once, tracks 1-16 in order')
        print(f'  Shuffle Albums over 2048 songs (128 albums): {m2.icount:,} payload instructions')
        # Shuffle Folders on the same size: the folder length is kept per song, not found again in every comparison
        FOLDER_COST = {}
        deep = '/mnt/mmc/Music/Library/Collection/Artist'
        for tag, prefix in (('short', '/mnt/mmc/l'), ('long', deep)):
            m3 = shuffle_machine([(f'{prefix}/{a:03d}/{t:02d}.flac', f'Album {a:03d}', 16 - t) for a in range(128) for t in range(16)]).count()
            v = m3.call(play, a0=pod_pages.SHUFFLE_FOLDERS, count=2000000000)
            got = runs(m3.played[0], lambda r: field(m3, r, O['REC_PATH']).rsplit('/', 1)[0]) if m3.played else []
            expect(v == 0 and len(got) == 128 and len({k for k, _ in got}) == 128
                   and all(len(rs) == 16 and [field(m3, r, O['REC_PATH']) for r in rs] == sorted(field(m3, r, O['REC_PATH']) for r in rs) for _, rs in got),
                   f'2048 songs in 128 {tag}-path folders: every folder once, contiguous, in file-name order')
            print(f'  Shuffle Folders over 2048 songs ({tag} paths, {len(m3.played[0] and field(m3, m3.played[0][0], O["REC_PATH"]))} bytes): {m3.icount:,} payload instructions')
            FOLDER_COST[tag] = m3.icount
        expect(FOLDER_COST['short'] < 14000000 and FOLDER_COST['long'] < 30000000,
               f'the folder length is found once per song: {FOLDER_COST["short"]:,} / {FOLDER_COST["long"]:,} instructions (26.4 M / 59.1 M before)')
    m.showlist = [one] * (big + 1)
    v = m.call(play, a0=pod_pages.SHUFFLE_SONGS, count=COUNT)
    expect(v == 0 and m.played and len(m.played[0]) == big + 1, 'Shuffle Songs plays a library of any size')

    # 36. An unknown kind does nothing at all; the kill switch keeps the whole menu (and so every
    #     shuffle) away.
    m = shuffle_machine(lib)
    expect(m.call(play, a0=7, count=COUNT) == 0xffffffff and not m.calls, 'an unknown kind does nothing')
    m = shuffle_machine(lib); m.present.add('/mnt/mmc/m1plus-off')
    m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(pod_pages.HOME_ENTRY)), count=COUNT)
    expect('stock_resume' in m.names() and 'loadLocalClassList' not in m.names() and 'window_open' not in m.names(),
           'kill switch: the entry icon is stock again, no menu, no shuffle')

def apple_machine(n=12, pos=3, mode=0, flag=False, boot=True):
    """A HookedMachine with the player on n songs at pos (07 = Album 1 track 3 ...). boot: stock's own first mclSetPlayMode (config_init) has run: the hook's
    session-first call keeps the flag as the file has it, so the tests that are about later requests pass it by."""
    m = HookedMachine()
    m.mode = mode
    if flag: m.fs[FLAG_FILE] = b'1\n'
    recs = [song(m, f'/mnt/mmc/q/{i:02d}.flac', f'Album {i // 4}', i % 4 + 1) for i in range(n)]
    m.play(recs, pos)
    if boot: m.call(PSYMS['sh_set_mode'], a0=mode, count=900000000)
    m.calls = []
    return m


def queue_of(m): return m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])]
def order(m): return [field(m, r, O['REC_PATH']) for r in queue_of(m)]
def strings(m): return sorted(m.word(r + O[f]) for r in queue_of(m) for f in STR_FIELDS)
def hook(m, mode): return m.call(PSYMS['sh_set_mode'], a0=mode, count=900000000)
def load(m, h, pos, cls=0xf001): return m.call(PSYMS['sh_load_playlist'], a0=h, a1=pos, a2=cls, count=900000000)


def apple_tests(ctx):
    expect = ctx.expect
    SH, OR, RO, RA = O['MODE_SHUFFLE'], O['MODE_ORDER'], O['MODE_REPEAT_ONE'], O['MODE_REPEAT_ALL']
    GAPLESS, GSET = pod.DATA['MCL_PRELOAD'][0], pod.DATA['MCL_GAPLESS'][0]   # the preload state word, the Gapless setting byte

    # 40. Shuffle on (a request for 2): our flag on, stock List play; the songs after the playing one are permuted in place, the rest stays; every string keeps one owner.
    for clock in (1, 90, 4099):
        m = apple_machine()
        m.clock = clock
        before, owned = order(m), strings(m)
        hook(m, SH)
        after = order(m)
        expect(flag_on(m) and m.mode == OR and ('stock_setmode', OR) in m.calls and m.fs.get(FLAG_FILE) == b'1\n', f'clock {clock}: a request for Shuffle is "flag on" and stock List play')
        expect(after[:4] == before[:4] and sorted(after[4:]) == sorted(before[4:]) and m.play_pos == 3,
               f'clock {clock}: the playing song (and the ones before it) stay at their slots, the eight after it are a permutation ({after[4:]})')
        expect(strings(m) == owned and len(set(strings(m))) == len(owned), f'clock {clock}: every record still owns its own strings (no copy, none lost)')
        if clock == 90: moved = after != before
    expect(moved, 'the shuffle moved songs')
    ranks = set()
    for clock in range(1, 30):
        m = apple_machine(); m.clock = clock * 7919; hook(m, SH); ranks.add(tuple(order(m)))
    expect(len(ranks) >= 25, f'different draws give different orders ({len(ranks)} of 29)')

    # 41. Shuffle off: the original order is back, the same song keeps playing and the songs that followed it originally come next.
    m = apple_machine(); before = order(m); owned = strings(m); hook(m, SH)
    shuffled = order(m); m.play_pos = 7   # the player moved on inside the shuffled queue
    playing = shuffled[7]
    hook(m, OR)
    back = order(m)
    expect(not flag_on(m) and back == before and back[m.play_pos] == playing, f'Shuffle off: the original order, the playing song at its own place ({m.play_pos})')
    expect(back[m.play_pos + 1:] == before[before.index(playing) + 1:] and ('mclSetPlayPos', before.index(playing)) in m.calls, 'the songs that follow it in the original order come next')
    expect(strings(m) == owned and len(set(strings(m))) == 5 * len(back), 'every string still has one owner')
    hook(m, SH); hook(m, RA)
    expect(not flag_on(m) and order(m) == before and m.mode == RA and ('stock_setmode', RA) in m.calls, 'any other request (Repeat all) is flag off and that stock mode, the order restored')
    m = apple_machine(); before = order(m); hook(m, SH)
    m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])].pop()   # a song was deleted: the saved order no longer matches
    shuffled = order(m); hook(m, OR)
    expect(not flag_on(m) and order(m) == shuffled and not [c for c in m.calls if c[0] == 'mclSetPlayPos'], 'a queue whose size changed keeps its order (nothing to restore from), the flag still goes off')

    # 42. A queue loaded while Shuffle is on (a tap, Play, the stock folder browser, the resume): the song at the index first, the rest shuffled, playing at slot 0.
    songs = lambda m: [song(m, f'/mnt/mmc/q/{i:02d}.flac', f'Album {i // 4}', i % 4 + 1) for i in range(12)]
    m = apple_machine(n=2, pos=0, flag=True)
    recs = songs(m); h = m.new_deque(recs); before = [field(m, r, O['REC_PATH']) for r in recs]; owned = sorted(m.word(r + O[f]) for r in recs for f in STR_FIELDS)
    load(m, h, 5)
    got = order(m)
    expect(('stock_loadplaylist', 5, 0xf001) in m.calls and m.names().index('stock_loadplaylist') < m.names().index('mclSetPlayPos'), 'stock loads the queue first (the trampoline), then the hook reorders it')
    expect(got[0] == before[5] and sorted(got) == sorted(before) and got != before and m.play_pos == 0 and ('mclSetPlayPos', 0) in m.calls, f'the tapped song is first and playing, the rest a permutation ({got[:4]})')
    expect(strings(m) == owned, 'the records own their strings')
    m.play_pos = 4; playing = got[4]; hook(m, OR)
    expect(order(m) == before and order(m)[m.play_pos] == playing, 'turning Shuffle off afterwards restores the loaded order around the song that is playing')
    m = apple_machine(n=2, pos=0)
    recs = songs(m); h = m.new_deque(recs); load(m, h, 5)
    expect(order(m) == [field(m, r, O['REC_PATH']) for r in recs] and m.play_pos == 5 and not [c for c in m.calls if c[0] == 'mclSetPlayPos'], 'with Shuffle off the loaded queue is left alone')
    m = apple_machine(n=2, pos=0, flag=True); h = m.new_deque(songs(m)[:1]); load(m, h, 0)
    expect(m.play_pos == 0 and len(order(m)) == 1 and not [c for c in m.calls if c[0] == 'calloc'], 'a one-song queue needs no shuffle (and allocates nothing)')
    m = apple_machine(n=2, pos=0, flag=True); h = m.new_deque(songs(m)); load(m, h, 99)
    expect(order(m)[0] == '/mnt/mmc/q/00.flac' and sorted(order(m)) == sorted(f'/mnt/mmc/q/{i:02d}.flac' for i in range(12)), 'an index outside the queue starts from the first song')
    m = apple_machine(n=2, pos=0, flag=True); m.present.add('/mnt/mmc/m1plus-off'); h = m.new_deque(songs(m)); load(m, h, 5)
    expect(order(m) == [f'/mnt/mmc/q/{i:02d}.flac' for i in range(12)] and m.play_pos == 5, 'kill switch: stock\'s own load')

    # 43. Limits: more than SHUFFLE_MAX songs or no memory leave the queue alone with the flag off; the buttons say so.
    big = O['SHUFFLE_MAX']
    m = apple_machine(n=2, pos=0, flag=True); one = song(m, '/mnt/mmc/big/1.flac', 'Big', 1)
    h = m.new_deque([one] * (big + 1)); before = list(m.deques[h]); load(m, h, 7)
    expect(not flag_on(m) and queue_of(m) == before and m.play_pos == 7 and not [c for c in m.calls if c[0] == 'calloc'], f'{big + 1} songs: the queue is as loaded, the flag is off, nothing allocated')
    m = apple_machine(n=2, pos=0); m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])] = [one] * (big + 1)
    hook(m, SH)
    expect(not flag_on(m) and m.mode == OR and not [c for c in m.calls if c[0] == 'calloc'], f'{big + 1} songs: a request for Shuffle leaves the flag off (stock List play)')
    m = apple_machine(); m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])] = [one] * (big + 1); m.call(PSYMS['pod_set_shuffle'], a0=1, count=900000000)
    expect(not flag_on(m) and ('toast', 'Too many songs to shuffle', O['MSGINFO_KIND'], O['MSGINFO_MS']) in m.calls, 'the Queue page\'s button shows "Too many songs to shuffle"')
    m = apple_machine(); before = order(m); m.calloc_fail = True; m.call(PSYMS['pod_set_shuffle'], a0=1, count=900000000)
    expect(not flag_on(m) and order(m) == before and ('toast', 'Not enough memory', O['MSGINFO_KIND'], O['MSGINFO_MS']) in m.calls, 'no memory: the queue stays, the flag stays off, "Not enough memory"')
    m = apple_machine(n=2, pos=0, flag=True); m.calloc_fail = True; h = m.new_deque(songs(m)); before = [m.read_cstr(m.word(r + O['REC_PATH'])) for r in m.deques[h]]; load(m, h, 5)
    expect(not flag_on(m) and order(m) == before and m.play_pos == 5, 'no memory at a load: the queue is as stock loaded it, the flag is off')
    # bounded memory: the shuffle holds one array of 4 bytes a song (and frees its temporaries)
    m = apple_machine(); hook(m, SH)
    allocs = [c[1] for c in m.calls if c[0] == 'calloc']
    expect(allocs == [4 * 12, 2] and len([c for c in m.calls if c[0] == 'free' and c[1]]) == 1, f'the in-place shuffle allocates one array of 4 bytes a song (the identity, its tail permuted in place, then kept as the original order) and a bitmap, and frees the bitmap ({allocs})')
    m = apple_machine(); before = order(m); m.calloc_fail_size = 2; hook(m, SH)
    expect(not flag_on(m) and order(m) == before and len([c for c in m.calls if c[0] == 'free' and c[1]]) == 1 and not [c for c in m.calls if c[0] == 'mclSetPlayPos'],
           'no memory for the bitmap: the array is freed, the queue untouched, the flag stays off')

    # 44. The mode choke point.
    m = apple_machine(mode=RA, flag=False)
    hook(m, SH)
    expect(flag_on(m) and ('stock_setmode', OR) in m.calls and m.mode == OR, 'a request for 2 maps to our flag, stock mode 0 (also from Repeat all)')
    m.calls = []; hook(m, SH)
    expect('stock_setmode' not in m.names() and not [c for c in m.calls if c[0] in ('mclSetPlayPos', 'calloc')], 'asked again while on (stock\'s boot restore of the mode shown, config_mplayer): nothing changes')
    for req in (OR, RO, RA):
        m = apple_machine(flag=True); hook(m, req)
        expect(not flag_on(m) and m.mode == req and ('stock_setmode', req) in m.calls, f'a request for {req} is flag off and that mode')
    m = apple_machine(mode=RA, flag=True)
    m.call(PSYMS['pod_set_repeat'], a0=RO, count=900000000)
    expect(flag_on(m) and m.mode == RO and ('write_int_config', RO, 'PLAYSET', 'PLAYMODE') in m.calls and ('mclSetPlayMode', RO) in m.calls, 'the Queue page\'s Repeat keeps the flag')
    m = apple_machine(mode=RA, flag=True, boot=False)   # stock's boot restore is the first call: flag and mode as the files have them
    hook(m, RA)
    expect(flag_on(m) and m.mode == RA, 'boot: the stock mode comes from the config, the flag stays on')
    m = apple_machine(mode=RA, flag=True, boot=False); hook(m, SH)
    expect(flag_on(m) and m.mode == OR, 'boot with [PLAYSET] PLAYMODE=2 (saved by stock, or by an older build): flag on, stock List play')
    m = apple_machine(mode=RA, flag=False, boot=False); hook(m, SH)
    expect(flag_on(m) and m.mode == OR and m.fs.get(FLAG_FILE) == b'1\n', 'boot with PLAYMODE=2 and no flag file: the flag turns on (an upgrade keeps Shuffle)')
    m = apple_machine(mode=OR, flag=False, boot=False); hook(m, RA)
    expect(not flag_on(m), 'boot with no flag: off')
    m = apple_machine(flag=True); m.present.add('/mnt/mmc/m1plus-off'); hook(m, SH)
    expect(m.mode == SH and ('stock_setmode', SH) in m.calls and not [c for c in m.calls if c[0] in ('calloc', 'mclSetPlayPos', 'write')], 'kill switch: stock\'s own mode 2, no flag, no reorder, nothing written')
    # the display: what the stock sites show and send (2 while the flag is on)
    for flag, raw, want in ((True, OR, SH), (True, RA, SH), (False, RA, RA), (False, OR, OR), (False, RO, RO)):
        m = apple_machine(mode=raw, flag=flag)
        expect(m.call(PSYMS['sh_display_mode'], count=100000) == want, f'display mode with the flag {"on" if flag else "off"} and stock mode {raw}: {want}')
    # the gapless preload of the old next song is closed after a reorder (and only then)
    m = apple_machine(); m.u.mem_write(GSET, b'\1'); m.setword(GAPLESS, 1); hook(m, SH)
    seq = [c for c in m.calls if c[0] in ('mclSetGaplessMode', 'closegapless', 'stock_setmode')]
    expect(m.names().count('closegapless') == 1 and m.s32(GAPLESS) == -1 and m.mode == OR and m.u.mem_read(GSET, 1)[0] == 1, 'a preload is closed after the reorder and the Gapless setting is back')
    expect(seq == [('stock_setmode', OR), ('mclSetGaplessMode', 0), ('closegapless',), ('mclSetGaplessMode', 1)], f'the one cancel helper: the Gapless setter with 0, then the old value; the stock mode word is never Repeat one ({seq})')
    m = apple_machine(); m.u.mem_write(GSET, b'\1'); hook(m, SH); m.setword(GAPLESS, 1); m.calls = []; hook(m, OR)
    expect(m.names().count('closegapless') == 1 and m.mode == OR and ('mclSetGaplessMode', 1) in m.calls and ('stock_setmode', RO) not in m.calls, 'and after the order is restored')
    m = apple_machine(); hook(m, SH)
    expect('closegapless' not in m.names(), 'no preload open: nothing to close')

    # 45. Now Playing's own button: stock's picture function (0x539888) and click handler (0x53b5fc) run under emulation with the display sites patched as built.
    STYLES = {OR: 'btn_imgorder_style', RO: 'btn_imgcycle1_style', SH: 'btn_imgrandom_style', RA: 'btn_imgcycle_style'}

    def np_machine(mode, flag):
        m = apple_machine(mode=mode, flag=flag)
        m.widget('btn_playmode')
        m.win = m.alloc(0x40)
        return m

    def style(m):
        m.call(0x539888, a0=m.win, count=900000000)
        return next(c[2] for c in m.calls if c[0] == 'widget_use_style')
    for mode, flag, want in ((OR, False, OR), (RO, False, RO), (RA, False, RA), (OR, True, SH), (RA, True, SH), (RO, True, SH)):
        m = np_machine(mode, flag)
        expect(style(m) == STYLES[want], f'the Now Playing button with stock mode {mode} and Shuffle {"on" if flag else "off"} shows {STYLES[want]}')
    m = np_machine(OR, False)
    seen = []
    for _ in range(5):
        m.call(0x53b5fc, a0=m.win, count=900000000)
        seen.append((next(c[2] for c in m.calls if c[0] == 'widget_use_style'), flag_on(m), m.mode))
    expect(seen == [(STYLES[RO], False, RO), (STYLES[SH], True, OR), (STYLES[RA], False, RA), (STYLES[OR], False, OR), (STYLES[RO], False, RO)],
           f'the stock 4-step cycle: Repeat one, Shuffle (flag on, stock 0), Repeat all (flag off), List play ({seen})')
    m = np_machine(RA, True)
    m.call(0x53b5fc, a0=m.win, count=900000000)
    expect(not flag_on(m) and m.mode == RA and next(c[2] for c in m.calls if c[0] == 'widget_use_style') == STYLES[RA], 'Shuffle plus Repeat all (set from the Queue page): the button shows Shuffle; its next step is Repeat all with Shuffle off')

    # 46. The hooks and display sites in the build: pinned words, the jal to sh_display_mode, the prologue jumps.
    stock_demo = stock_demo_bytes()
    built = built_demo_bytes()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    sites = {a for a, _ in pod.MODE_SITES}
    expect(len(sites) == 19 and all(w(stock_demo, a) == 0x0320f809 and w(built, a) == pod.jal(PSYMS['sh_display_mode'], a) for a in sites), 'the 19 display sites: stock `jalr mclGetPlayMode` became `jal sh_display_mode`')
    cs = pod.CLEAR_SITE
    expect(all(w(stock_demo, a) == old and (a in sites or a == cs or w(built, a) == old) for a, old, _ in pod.SHUFFLE_PINS), 'every pinned word is stock\'s in the stock demo and unchanged in the build (but the sites)')
    expect(w(stock_demo, cs) == 0x0320f809 and w(stock_demo, cs + 4) == 0x8c440000 and w(built, cs) == pod.jal(PSYMS['sh_clear_queue'], cs) and w(built, cs + 4) == 0x8c440000 and w(built, cs - 4) == w(stock_demo, cs - 4)
           and MANIFEST['hook_clear_queue'] == {'addr': cs, 'target': PSYMS['sh_clear_queue']}, 'dmr_serverstart @0x5089e4: `jalr deque_clear` became `jal sh_clear_queue`, the delay slot `lw a0, (v0)` is stock\'s')
    expect(w(built, 0x5d3628) == w(stock_demo, 0x5d3628) and w(built, 0x5d363c) == w(stock_demo, 0x5d363c), 'mclGetPlayMode itself is not hooked (change_music and the mcl core read the raw mode)')
    for nm, at, tr in (('sh_set_mode', pod.SETMODE, 'stock_setmode_trampoline'), ('sh_load_playlist', pod.LOADPL, 'stock_loadplaylist_trampoline')):
        expect(w(built, at) == pod.j(PSYMS[nm]) and w(built, at + 4) == 0 and w(built, at + 8) == w(stock_demo, at + 8) == pod.SETMODE_PROLOGUE[2], f'{nm}: the prologue is `j {nm}; nop`')
        gp = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS[tr] - pod.BASE)
        expect(gp == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(at + 12), 0), f'{tr}: restores $gp and resumes at the 4th instruction')
    expect(MANIFEST['hook_setmode'] == {'addr': pod.SETMODE, 'target': PSYMS['sh_set_mode']} and MANIFEST['hook_loadplaylist'] == {'addr': pod.LOADPL, 'target': PSYMS['sh_load_playlist']}
           and MANIFEST['hook_display_mode']['target'] == PSYMS['sh_display_mode'], 'the manifest records the hooks')

    # 47. Shuffle off needs no memory: the records go back by following the cycles of the saved order.
    for n, pos in ((12, 3), (40, 0), (40, 39), (2, 0), (3, 1)):
        for clock in (1, 90, 4099):
            m = apple_machine(n=n, pos=pos); m.clock = clock; before, owned = order(m), strings(m); hook(m, SH)
            shuffled = order(m); at = min(n - 1, pos + 1 + (clock % max(1, n - pos - 1))) if n > 1 else 0; m.play_pos = at
            playing = shuffled[at]; m.calloc_fail = True; m.calls = []; hook(m, OR)
            expect(not flag_on(m) and order(m) == before and strings(m) == owned and order(m)[m.play_pos] == playing and not [c for c in m.calls if c[0] == 'calloc'],
                   f'{n} songs from {pos}, clock {clock}: Shuffle off with every allocation refused restores the order, keeps the playing song and allocates nothing')
    m = apple_machine(); before = order(m); hook(m, SH); m.calloc_fail = True; m.play_pos = 7; playing = order(m)[7]
    m.call(PSYMS['pod_set_shuffle'], a0=0, count=900000000)
    expect(not flag_on(m) and order(m) == before and order(m)[m.play_pos] == playing and not [c for c in m.calls if c[0] == 'toast'], 'the Queue page\'s Shuffle off restores with no memory and shows no message')

    # 48. A queue that is about to be replaced is not reordered: Shuffle Songs, Play and the other paths of ours set the flag only; sh_load_playlist shuffles the new queue.
    big = O['SHUFFLE_MAX']
    m = apple_machine(); one = song(m, '/mnt/mmc/big/1.flac', 'Big', 1)
    qh = m.word(pod.DATA['PLAY_QUEUE'][0]); m.deques[qh] = [one] * (big + 1); old = list(m.deques[qh]); m.calls = []
    m.call(PSYMS['pod_set_mode_for_queue'], a0=SH, count=900000000)
    expect(flag_on(m) and m.fs.get(FLAG_FILE) == b'1\n' and m.deques[qh] == old and m.mode == OR and not [c for c in m.calls if c[0] in ('calloc', 'mclSetPlayPos')],
           f'{big + 1} songs playing, Shuffle Songs: the flag is on, the old queue is not touched and nothing is allocated (no "Too many songs")')
    recs = songs(m); h = m.new_deque(recs[:8]); before = [field(m, r, O['REC_PATH']) for r in recs[:8]]; load(m, h, 3)
    expect(flag_on(m) and order(m)[0] == before[3] and sorted(order(m)) == sorted(before) and m.play_pos == 0, 'the 8-song replacement queue is shuffled, the chosen song first')
    m = apple_machine(n=2048, pos=5); before = order(m); m.calls = []
    m.call(PSYMS['pod_set_mode_for_queue'], a0=SH, count=900000000)
    expect(flag_on(m) and order(m) == before and not [c for c in m.calls if c[0] in ('calloc', 'mclSetPlayPos') or c[0] == 'free' and c[1]], '2048 songs to a Shuffle queue: the old queue is not reordered (no record copied, no allocation)')
    recs = [song(m, f'/mnt/mmc/n/{i:02d}.flac', 'N', i + 1) for i in range(16)]; h = m.new_deque(recs); load(m, h, 0)
    expect(flag_on(m) and len(order(m)) == 16 and order(m)[0] == '/mnt/mmc/n/00.flac' and sorted(order(m)) == sorted(f'/mnt/mmc/n/{i:02d}.flac' for i in range(16)), 'the 16-song queue arrives shuffled')
    # Play before a new queue: the flag goes off, the old queue keeps its (shuffled) order
    m = apple_machine(); hook(m, SH); shuffled = order(m); m.calls = []
    m.call(PSYMS['pod_set_in_order_for_queue'], count=900000000)
    expect(not flag_on(m) and m.fs.get(FLAG_FILE) == b'0\n' and order(m) == shuffled and not [c for c in m.calls if c[0] in ('calloc', 'mclSetPlayPos')],
           'Play before a queue load: the flag goes off, the old queue is not restored')
    m = apple_machine(n=2, pos=0, flag=True); m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])] = [one] * (big + 1); h = m.new_deque(songs(m)[:3]); m.call(PSYMS['pod_set_in_order_for_queue'], count=900000000); load(m, h, 1)
    expect(not flag_on(m) and len(order(m)) == 3 and order(m)[1] == '/mnt/mmc/q/01.flac', 'Play over an oversized shuffled queue is not blocked and loads in order')
    m = apple_machine(mode=RO, flag=True); m.call(PSYMS['pod_set_in_order_for_queue'], count=900000000)
    expect(not flag_on(m) and m.mode == OR, 'Play for a queue also turns Repeat one into List play')
    # the paths that load no queue still reorder
    m = apple_machine(); before = order(m); m.call(PSYMS['pod_set_mode'], a0=SH, count=900000000)
    expect(flag_on(m) and order(m) != before and sorted(order(m)) == sorted(before), 'pod_set_mode (no queue load follows) shuffles the current queue')
    m.call(PSYMS['pod_set_in_order'], count=900000000)
    expect(not flag_on(m) and order(m) == before, 'pod_set_in_order restores the current queue')
    m = apple_machine(); before = order(m); m.call(PSYMS['pod_set_shuffle'], a0=1, count=900000000)
    expect(flag_on(m) and order(m) != before, 'the Queue page\'s Shuffle button shuffles the current queue')

    # 49. The payload lock: taken and released in pairs on every path (early returns included), one at a time, never across a stock mode / load call.
    def locked(m):
        depth, addrs, bad = 0, set(), ''
        for c in m.calls:
            if c[0] == 'lock':
                depth += 1; addrs.add(c[1])
                if depth > 1: bad = 'taken twice'
            elif c[0] == 'unlock':
                depth -= 1; addrs.add(c[1])
                if depth < 0: bad = 'released unheld'
            elif depth and c[0] in ('stock_setmode', 'mclSetPlayMode', 'closegapless', 'toast', 'write_int_config'):
                bad = f'{c[0]} under the lock'
            elif c[0] == 'stock_loadplaylist' and depth != 1:   # stock's loader clears the deque a reorder may be walking: only ever with the lock held
                bad = 'stock_loadplaylist without the lock'
        return not bad and depth == 0 and len(addrs) <= 1, bad or f'depth {depth}, {len(addrs)} addresses'
    done_paths = []
    def case(name, m, fn):
        m.calls = []; fn(m); ok, why = locked(m)
        done_paths.append(name)
        expect(ok and any(c[0] == 'lock' for c in m.calls), f'lock path "{name}": balanced ({why})')
    def pc(m, sym, **kw): return lambda m: m.call(PSYMS[sym], count=900000000, **kw)
    case('request Shuffle', apple_machine(), lambda m: hook(m, SH))
    case('Shuffle off', apple_machine(flag=True), lambda m: hook(m, OR))
    case('Shuffle on, one-song queue', apple_machine(n=1, pos=0), lambda m: hook(m, SH))
    case('Shuffle off, stale order', apple_machine(), lambda m: (hook(m, SH), queue_of(m).pop(), hook(m, OR)))
    mb = apple_machine(); one = song(mb, '/mnt/mmc/big/1.flac', 'Big', 1); mb.deques[mb.word(pod.DATA['PLAY_QUEUE'][0])] = [one] * (big + 1)
    case('Shuffle on, too many songs', mb, lambda m: hook(m, SH))
    mm = apple_machine(); mm.calloc_fail = True
    case('Shuffle on, no memory', mm, lambda m: hook(m, SH))
    case('Queue page Shuffle', apple_machine(), pc(None, 'pod_set_shuffle', a0=1))
    case('Queue page Shuffle, no memory', mm, pc(None, 'pod_set_shuffle', a0=1))
    case('Shuffle for a queue', apple_machine(), pc(None, 'pod_set_mode_for_queue', a0=SH))
    case('Play for a queue', apple_machine(flag=True), pc(None, 'pod_set_in_order_for_queue'))
    mk = apple_machine(flag=True); mk.present.add('/mnt/mmc/m1plus-off')
    case('kill switch, mode', mk, lambda m: hook(m, SH))
    ml = apple_machine(n=2, pos=0, flag=True)
    case('load, flag on', ml, lambda m: load(m, m.new_deque(songs(m)), 5))
    case('load, flag off', apple_machine(n=2, pos=0), lambda m: load(m, m.new_deque(songs(m)), 5))
    ml = apple_machine(n=2, pos=0, flag=True); ml.calloc_fail = True
    case('load, no memory', ml, lambda m: load(m, m.new_deque(songs(m)), 5))
    ml = apple_machine(n=2, pos=0, flag=True); ml.present.add('/mnt/mmc/m1plus-off')
    case('load, kill switch', ml, lambda m: load(m, m.new_deque(songs(m)), 5))
    ml = apple_machine(n=2, pos=0, flag=True)
    case('load, one song', ml, lambda m: load(m, m.new_deque(songs(m)[:1]), 0))

    # 50. Queue replacement and reordering exclude each other for the whole operation (the DLNA thread vs. the UI thread). The emulator has no threads, so the test is the
    #     scheduler: a "thread" is a saved CPU context on its own stack; the mocks model the payload mutex (a lock of a held mutex stops the caller until it is
    #     resumed) and pause a thread at a chosen point (after N memcpy of the reorder = mid-permutation, with duplicates in the queue; or right after stock's loader
    #     trampoline). Events record who did what in what order.
    from unicorn.mips_const import UC_MIPS_REG_PC as PC_, UC_MIPS_REG_SP as SP_, UC_MIPS_REG_RA as RA_, UC_MIPS_REG_T9 as T9_
    PLAYQ = pod.DATA['PLAY_QUEUE'][0]
    def sched(m): m.sched, m.events, m.loads_held, m.clears_held, m.limit, m.calls = True, [], [], [], 10 ** 9, []
    def spawn(m, name, sym, sp, a0=0, a1=0, a2=0):
        u = m.u
        for r, v in ((SP_, sp), (RA_, RET), (T9_, PSYMS[sym]), (UC_MIPS_REG_A0, a0), (UC_MIPS_REG_A1, a1), (UC_MIPS_REG_A2, a2), (PC_, PSYMS[sym])): u.reg_write(r, v & 0xffffffff)
        return {'name': name, 'ctx': u.context_save(), 'done': False}
    def go(m, th):
        m.cur, m.blocked = th['name'], None
        m.u.context_restore(th['ctx']); m.u.emu_start(m.u.reg_read(PC_), RET)
        th['ctx'] = m.u.context_save(); th['done'] = m.u.reg_read(PC_) == RET
    def fresh(m): return [song(m, f'/mnt/mmc/n/{i}.flac', 'New', i + 1) for i in range(5)]
    NEW = [f'/mnt/mmc/n/{i}.flac' for i in range(5)]
    # (a) DLNA's reorder holds the lock and is paused mid-permutation; the UI thread's load must wait: stock's loader (which frees the deque's blocks) does not run
    #     and the deque is not touched until the reorder has released the lock.
    m = apple_machine(n=12, pos=3); sched(m); before, owned, q0 = order(m), strings(m), m.word(PLAYQ)
    h = m.new_deque(fresh(m))
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=SH); m.yield_thread, m.yield_at = 'dlna', 2
    go(m, dl); mid = order(m)
    expect(not dl['done'] and m.owner == 'dlna' and len(set(mid)) < len(mid), f'interleaving A: the reorder is paused mid-permutation, lock held, records duplicated ({len(set(mid))} distinct of {len(mid)})')
    ui = spawn(m, 'ui', 'sh_load_playlist', STACK - 0x4000, a0=h, a1=2, a2=0xf001)
    go(m, ui)
    expect(m.blocked == 'ui' and not ui['done'] and 'stock_loadplaylist' not in m.names() and m.word(PLAYQ) == q0 and order(m) == mid,
           'interleaving A: the load waits at the lock; stock\'s loader has not run and the deque is untouched')
    m.yield_at = 0; go(m, dl)
    expect(dl['done'] and m.owner is None and sorted(order(m)) == sorted(before) and order(m) != before and strings(m) == owned and flag_on(m),
           'interleaving A: the reorder finishes whole (a permutation, every record owning its strings) and releases the lock')
    go(m, ui)
    ev = m.events; unl = max(i for i, e in enumerate(ev) if e == ('dlna', 'pthread_mutex_unlock')); ld = ev.index(('ui', 'stock_loadplaylist'))
    expect(ui['done'] and unl < ld and m.loads_held == [True] and sorted(order(m)) == NEW and order(m)[0] == NEW[2] and m.owner is None,
           f'interleaving A: stock\'s loader runs only after the reorder released the lock, under the lock; the new queue is shuffled with the load index first ({order(m)})')
    # (b) the reverse: the load holds the lock (paused right after stock's loader), a restore request arrives: it waits, then restores the NEW queue's order from the
    #     NEW order, never the old one's.
    m = apple_machine(n=12, pos=3); hook(m, SH); sched(m)
    recs = fresh(m); h = m.new_deque(recs)
    ui = spawn(m, 'ui', 'sh_load_playlist', STACK - 0x4000, a0=h, a1=2, a2=0xf001); m.pause_load = True
    go(m, ui); loaded = order(m)
    expect(not ui['done'] and m.owner == 'ui' and loaded == NEW and m.loads_held == [True], 'interleaving B: the load is paused inside stock\'s loader with the lock held')
    m.pause_load = False
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=OR); go(m, dl)
    expect(m.blocked == 'dlna' and not dl['done'] and order(m) == NEW and flag_on(m) and ('mclSetPlayPos',) not in m.calls,
           'interleaving B: the restore request waits at the lock; the queue is the loaded one, the old order is not applied to it')
    go(m, ui)
    expect(ui['done'] and m.owner is None and sorted(order(m)) == NEW and order(m)[0] == NEW[2], f'interleaving B: the load finishes and shuffles ({order(m)})')
    go(m, dl)
    expect(dl['done'] and m.owner is None and order(m) == NEW and not flag_on(m), f'interleaving B: the restore then puts the new queue back in load order ({order(m)})')


    # 51. dmr_serverstart's own deque_clear of the playing queue (patched call site -> sh_clear_queue) takes the same lock.
    N12 = [f'/mnt/mmc/n/{i}.flac' for i in range(12)]
    def fresh12(m): return m.new_deque([song(m, p, 'New', i + 1) for i, p in enumerate(N12)])
    # (a) a reorder paused mid-permutation holds the lock: the clear waits, the deque is neither freed nor changed until the reorder is done; the order is dropped after.
    m = apple_machine(n=12, pos=3); sched(m); before, owned, q0 = order(m), strings(m), m.word(PLAYQ)
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=SH); m.yield_thread, m.yield_at = 'dlna', 2
    go(m, dl); mid = order(m)
    expect(not dl['done'] and m.owner == 'dlna' and len(set(mid)) < len(mid), 'clear A: the reorder is paused mid-permutation, lock held')
    ui = spawn(m, 'ui', 'sh_clear_queue', STACK - 0x4000, a0=q0); go(m, ui)
    expect(m.blocked == 'ui' and not ui['done'] and 'deque_clear' not in m.names() and m.word(PLAYQ) == q0 and order(m) == mid and m.deques[q0] is not None and len(m.deques[q0]) == 12,
           'clear A: the clear waits at the lock; the deque is not freed and not changed')
    m.yield_at = 0; go(m, dl)
    expect(dl['done'] and m.owner is None and sorted(order(m)) == sorted(before) and strings(m) == owned and flag_on(m) and 'deque_clear' not in m.names(), 'clear A: the reorder finishes whole and releases the lock, still no clear')
    go(m, ui)
    unl = max(i for i, e in enumerate(m.events) if e == ('dlna', 'pthread_mutex_unlock')); cl = m.events.index(('ui', 'deque_clear'))
    expect(ui['done'] and unl < cl and m.clears_held == [True] and m.owner is None and ('deque_clear', q0) in m.calls and m.deques[q0] == [], 'clear A: the clear runs after the reorder released the lock, under the lock, on the same deque as stock\'s call')
    m.setword(PLAYQ, fresh12(m)); hook(m, OR)
    expect(order(m) == N12 and not flag_on(m), 'clear A: the saved order was dropped by the clear (a same-size queue loaded after it is not permuted by a restore)')
    # (b) the reverse: the clear holds the lock (paused inside deque_clear), a reorder request waits and then finds no saved order.
    m = apple_machine(n=12, pos=3); hook(m, SH); sched(m); q0 = m.word(PLAYQ)
    ui = spawn(m, 'ui', 'sh_clear_queue', STACK - 0x4000, a0=q0); m.pause_clear = True; go(m, ui)
    expect(not ui['done'] and m.owner == 'ui' and m.clears_held == [True], 'clear B: the clear is paused inside stock\'s deque_clear with the lock held')
    m.pause_clear = False; m.setword(PLAYQ, fresh12(m)); m.calls = []
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=OR); go(m, dl)
    expect(m.blocked == 'dlna' and not dl['done'] and order(m) == N12 and flag_on(m) and ('mclSetPlayPos',) not in m.calls, 'clear B: the restore request waits at the lock, the queue is untouched')
    go(m, ui); go(m, dl)
    expect(ui['done'] and dl['done'] and m.owner is None and order(m) == N12 and not flag_on(m) and ('mclSetPlayPos',) not in m.calls, 'clear B: after the clear the restore finds no saved order and leaves the queue as it is')

    # 52. The Queue page's Clear (pod_clear_upnext: libcstl's deque_pop_back under the same lock) against the other threads' reorders and loads: whole-operation exclusion both ways.
    #     Stock's readers take no lock and are not hooked (docs/modules/queue.md "Clear engine"); this is what the lock does cover.
    def clear_machine(n=12, pos=3, **kw):
        m = apple_machine(n=n, pos=pos, **kw); m.install_libcstl(); return m
    freed_of = lambda m: sorted(c[1] for c in m.calls if c[0] == 'free' and c[1])
    pops_of = lambda m: [c for c in m.calls if c[0] == 'pop_back']
    # (a) Clear is paused after 3 of its 8 pops (lock held, the queue partly shortened): a Shuffle request on the DLNA thread waits at the lock, sees the finished queue afterwards.
    m = clear_machine(); sched(m); q0 = m.word(PLAYQ); before = queue_of(m)[:]; kept, tail = before[:4], before[4:]
    kept_s = sorted(m.word(r + O[f]) for r in kept for f in STR_FIELDS); tail_s = sorted(m.word(r + O[f]) for r in tail for f in STR_FIELDS)
    ui = spawn(m, 'ui', 'pod_clear_upnext', STACK - 0x4000); m.yield_thread, m.pop_stop = 'ui', m.pops + 3
    go(m, ui)
    expect(not ui['done'] and m.owner == 'ui' and len(pops_of(m)) == 3 and queue_of(m) == before[:9], 'clear A: Clear is paused after 3 of 8 pops with the lock held, the queue is 9 long')
    m.pop_stop = 0
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=SH); go(m, dl)
    expect(m.blocked == 'dlna' and not dl['done'] and queue_of(m) == before[:9] and not flag_on(m), 'clear A: the Shuffle request waits at the lock; the queue is untouched by it')
    go(m, ui)
    expect(ui['done'] and m.owner is None and queue_of(m) == kept and len(pops_of(m)) == 8 and freed_of(m) == tail_s and not set(freed_of(m)) & set(kept_s), 'clear A: Clear finishes whole: records 0..pos in place, the 8 tail records destroyed once each')
    go(m, dl)
    ev = m.events; unl = max(i for i, e in enumerate(ev) if e == ('ui', 'pthread_mutex_unlock')); lk = min(i for i, e in enumerate(ev) if e == ('dlna', 'pthread_mutex_lock'))
    expect(dl['done'] and m.owner is None and unl < lk and queue_of(m) == kept and flag_on(m) and sorted(m.word(r + O[f]) for r in queue_of(m) for f in STR_FIELDS) == kept_s,
           'clear A: the request runs after Clear released the lock, on the shortened queue (nothing after the position to shuffle), the kept records untouched')
    # (b) the reverse: a reorder paused mid-permutation holds the lock; Clear waits (no pop), then removes the tail of the permuted queue; the retained records are the reorder's untouched ones.
    m = clear_machine(); sched(m); q0 = m.word(PLAYQ); before = queue_of(m)[:]
    dl = spawn(m, 'dlna', 'sh_set_mode', STACK, a0=SH); m.yield_thread, m.yield_at = 'dlna', 2
    go(m, dl); mid = queue_of(m)[:]
    ui = spawn(m, 'ui', 'pod_clear_upnext', STACK - 0x4000); go(m, ui)
    expect(m.blocked == 'ui' and not ui['done'] and not pops_of(m) and queue_of(m) == mid and len(mid) == 12, 'clear B: Clear waits at the lock while the reorder is mid-permutation: no pop, the deque untouched')
    m.yield_at = 0; go(m, dl); done = queue_of(m)[:]
    expect(dl['done'] and m.owner is None and done[:4] == before[:4] and sorted(done) == sorted(before) and not pops_of(m), 'clear B: the reorder finishes whole (a permutation; records 0..pos where they were) and releases the lock')
    tail_s = sorted(m.word(r + O[f]) for r in done[4:] for f in STR_FIELDS)
    go(m, ui)
    expect(ui['done'] and m.owner is None and queue_of(m) == done[:4] and [c[2] for c in pops_of(m)] == done[:3:-1] and sorted(c[1] for c in m.calls if c[0] == 'free' and c[1] in tail_s) == tail_s,
           'clear B: Clear then removes the 8 records that are the tail of the permuted queue, each string freed once')
    hook(m, OR)
    expect(not flag_on(m) and queue_of(m) == done[:4] and ('mclSetPlayPos',) not in m.calls, 'clear B: Shuffle off afterwards finds no saved order (dropped by Clear) and leaves the queue as it is')
    # (c) a queue load waits for a Clear paused mid-removal, then replaces the queue; nothing of the load runs inside the removal
    m = clear_machine(); sched(m); recs_new = fresh(m); h = m.new_deque(recs_new)
    ui = spawn(m, 'ui', 'pod_clear_upnext', STACK - 0x4000); m.yield_thread, m.pop_stop = 'ui', m.pops + 5
    go(m, ui); m.pop_stop = 0
    ld = spawn(m, 'dlna', 'sh_load_playlist', STACK, a0=h, a1=2, a2=0xf001); go(m, ld)
    expect(not ui['done'] and m.blocked == 'dlna' and 'stock_loadplaylist' not in m.names() and len(queue_of(m)) == 7, 'clear C: the load waits at the lock while Clear is 5 pops in; stock\'s loader has not run')
    go(m, ui); go(m, ld)
    ev = m.events; unl = max(i for i, e in enumerate(ev) if e == ('ui', 'pthread_mutex_unlock')); ldi = ev.index(('dlna', 'stock_loadplaylist'))
    expect(ui['done'] and ld['done'] and unl < ldi and m.loads_held == [True] and len(pops_of(m)) == 8 and sorted(order(m)) == NEW and m.owner is None, 'clear C: the load runs after Clear released the lock, under the lock, and fills the queue anew')


def shuffle_page_tests(expect, menu, spi, page):
    """Stage H: the menu's one Shuffle row (q2-pod's Library > Shuffle) opens the Shuffle page."""
    import awtk_ui
    rows0 = PSYMS['pod_rows_0']
    i = next(k for k, r in enumerate(menu.rows) if r.action == pod_pages.ACT_PAGE and r.arg == spi)
    expect(menu.rows[i].label == 'Shuffle' and not any(r.action == pod_pages.ACT_SHUFFLE for r in menu.rows),
           f'the menu has one Shuffle row (row {i} of the default order, after Playlists), opening the page, and no shuffle rows of its own')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_menu.bin'), 'rb').read())
    w = next((x for x in tree.walk() if x.type == 'list_item' and x.name == f'pod_row{i}'), None)
    labs = [pod_i18n.shown_english(c) for c in w.children if c.type == 'hscroll_label'] if w else []
    expect(labs == ['Shuffle'] and any(c.type == 'image' and c.get('image') == 'right_arrow' for c in w.children),
           f'the Shuffle menu row reads "Shuffle" and has the chevron ({labs})')
    m = Machine()
    name, action, arg = (m.word(rows0 + 12 * i + o) for o in (0, 4, 8))
    expect((m.read_cstr(name), action, arg) == (f'pod_row{i}', pod_pages.ACT_PAGE, spi),
           f'the payload row table binds pod_row{i} to ACT_PAGE {spi}')
    # a tap opens the page by name and binds its navbar and its three rows to their table entries
    m = Machine()
    m.widgets = {n: 0x30000000 + k for k, n in enumerate(['btn_return', 'btn_backtoplayer'] +
                                                          [f'pod_row{k}' for k in range(len(page.rows))])}
    m.call(PSYMS['on_row'], a0=rows0 + 12 * i, count=200000)
    ons = [c for c in m.calls if c[0] == 'widget_on']
    expect(('window_open', page.key) in m.calls and 'stock_resume' not in m.names(),
           f'the Shuffle row opens {page.key}')
    srows = PSYMS[f'pod_rows_{spi}']
    expect(len(ons) == 2 + len(page.rows) and
           [(c[1], c[2], c[4]) for c in ons[2:]] == [(m.widgets[f'pod_row{k}'], O['EVT_CLICK'], srows + 12 * k)
                                                    for k in range(len(page.rows))],
           f'it binds Back, Now Playing and pod_row0..{len(page.rows) - 1} to the Shuffle page\'s row table')
    back = next((c for c in ons if c[1] == m.widgets['btn_return']), None)
    if back:
        m2 = Machine(); m2.call(back[3], count=200000)
        expect(m2.names() == ['navigator_back'], 'Back on the Shuffle page is navigator_back (to the menu)')
    else:
        expect(False, 'Back on the Shuffle page is bound')
    # the page: the M1+ Music navbar titled Shuffle, stock-styled rows exactly like the menu's, no chevrons
    st = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/ui/{page.key}.bin'), 'rb').read())
    title = next((x for x in st.walk() if x.name == 'label_title'), None)
    items = [x for x in st.walk() if x.type == 'list_item']
    menu_item = next(x for x in tree.walk() if x.type == 'list_item')
    sig = lambda x: (x.get('style'), x.h, [(c.type, c.get('style'), c.x, c.y, c.h) for c in x.children if c.type == 'hscroll_label'])
    expect(title is not None and pod_i18n.shown_english(title) == 'Shuffle' and
           any(x.name == 'btn_return' for x in st.walk()) and any(x.name == 'btn_backtoplayer' for x in st.walk()),
           'the Shuffle page has the M1+ Music navbar: Shuffle, Back, Now Playing')
    expect([x.name for x in items] == ['pod_row0', 'pod_row1', 'pod_row2'] and
           [[pod_i18n.shown_english(c) for c in x.children if c.type == 'hscroll_label'] for x in items] ==
           [['Shuffle Songs'], ['Shuffle Albums'], ['Shuffle Folders']] and
           all(sig(x) == sig(menu_item) for x in items) and not any(c.type == 'image' and c.name != 'pod_icon' for x in items for c in x.children) and
           all(c.get('sensitive') == 'false' for x in items for c in x.children if c.name == 'pod_icon'),
           'its rows: Shuffle Songs / Albums / Folders, styled as the menu rows, no chevrons')
    root = asset_tree(os.path.join(WORK, 'rootfs', f'release/assets/default/raw/ui/{page.key}.bin'))
    hits = [stock_target(Machine(), root, x, pod_ui.NAVBAR_H + k * pod_ui.ROW_H + pod_ui.ROW_H // 2)
            for k in range(3) for x in (160, 32)]   # 32: on the row icon, when it has one
    expect(all(f'pod_row{i // 2}' in h for i, h in enumerate(hits)), f'a tap on each row (and on its icon) reaches that row ({hits})')


SECTIONS = [shuffle_tests, apple_tests]

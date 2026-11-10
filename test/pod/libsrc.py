"""The library source seam (patch/libsrc.c, patch/libsrc.h, patch/songops.c so_play_src; docs/modules/subsonic.md "The seam"): lib_stock returns the lists the stock queries give (albums, songs, artists,
an album's tracks) as copies, plays through so_play exactly (so_play_src with NULL, with &lib_stock and lib_stock.play start the same queue with the same calls), reports the cache
file of a cover, the durations table's seconds, and nothing for the extras. The compiled payload runs under Unicorn on the album page's machine."""
import importlib.util, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


AP = sibling('albumpage')
F_LIST, F_RECID, F_PLAY, F_COVER, F_SECONDS, F_ROW, F_ACT, F_GEN = (4 * i for i in range(1, 9))
LS_ALBUMS, LS_ARTISTS, LS_SONGS, LS_PLAYLISTS, LS_FAVORITES, LS_DOWNLOADED = range(6)
ALBUMS, ARTISTS, ALL = O['CLASS_ALBUMS'], O['CLASS_ARTISTS'], O['CLASS_ALL_SONGS']


def machine(**kw):
    m = AP.album_machine(**kw)
    m.class_lists[ARTISTS] = [m.record(album='', artist=f'Artist {i}', path='', title=f'Artist {i}', rid=i + 1) for i in range(3)]
    m.class_lists[ALL] = list(m.songs)
    return m


def lib(m): return PSYMS['lib_stock']
def fn(m, off): return m.word(lib(m) + off)


def texts(m, handle, off=None):
    off = O['REC_TITLE'] if off is None else off
    return [m.read_cstr(m.word(r + off)) for r in m.deques.get(handle, [])]


def call(m, f, a0=0, a1=0, a2=0, a3=0, s0=0, s1=0):
    """f with up to six arguments (the fifth and sixth on the stack, o32)."""
    m.u.mem_write(STACK + 16, struct.pack('<II', s0 & 0xffffffff, s1 & 0xffffffff))
    return m.call(f, a0=a0, a1=a1, a2=a2, a3=a3, count=900000000)


def list_tests(ctx):
    """1. list: the same rows as the calls the pages make today, copied."""
    expect = ctx.expect
    m = machine()
    expect(m.read_cstr(m.word(lib(m))) == 'stock', 'lib_stock is named "stock"')
    h = call(m, fn(m, F_LIST), lib(m), LS_ALBUMS, 0)
    expect(h and texts(m, h) == [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in m.class_lists[ALBUMS]] and ('loadLocalClassList', ALBUMS) in m.calls, 'albums: the stock album query, copied')
    h = call(m, fn(m, F_LIST), lib(m), LS_ARTISTS, 0)
    expect(texts(m, h) == [f'Artist {i}' for i in range(3)] and ('loadLocalClassList', ARTISTS) in m.calls, 'artists: the stock artist query, copied')
    h = call(m, fn(m, F_LIST), lib(m), LS_SONGS, 0)
    expect(h and len(m.deques[h]) == len(m.songs) and ('loadLocalClassList', ALL) in m.calls, 'songs: the stock all-songs query, copied')
    m = machine()
    h = call(m, fn(m, F_LIST), lib(m), LS_SONGS, m.row)
    expect(h and texts(m, h) == [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in m.songs] and ('loadAlbumdetailList', ALBUMS, m.row) in m.calls and m.word(AP.CI) == AP.LIB,
           f'an album\'s tracks: loadAlbumdetailList on the row (the browsing record left as the album page needs it): {m.calls}')
    m.album_tracks = {}
    expect(call(m, fn(m, F_LIST), lib(m), LS_SONGS, m.row) == 0, 'an album without tracks: NULL')
    expect(call(m, fn(m, F_LIST), lib(m), LS_FAVORITES, 0) == 0 and call(m, fn(m, F_LIST), lib(m), LS_DOWNLOADED, 0) == 0 and call(m, fn(m, F_LIST), lib(m), LS_ARTISTS, m.row) == 0,
           'Favorites, Downloaded and a scoped artist list are not the stock library\'s: NULL')


def extras_tests(ctx):
    """2. rec_id, cover, seconds, row, act, gen."""
    expect = ctx.expect
    m = machine()
    expect(m.read_cstr(call(m, fn(m, F_RECID), lib(m), m.row)) == '', 'rec_id of a stock record is ""')
    path = m.cover_path
    buf = m.alloc(128)
    expect(call(m, fn(m, F_COVER), lib(m), m.row, m.key, buf, 128 - 1) == 1 and m.read_cstr(buf) == path, f'cover: the cache file is there: {m.read_cstr(buf)} {path}')
    m.present.discard(path); m.files.pop(path, None)
    expect(call(m, fn(m, F_COVER), lib(m), m.row, m.key, buf, 127) & 0xffffffff == 0xffffffff, 'cover: no file is -1 (the page\'s own worker makes it)')
    rec = m.songs[0]
    m.files['/mnt/mmc/m/0.flac'] = 1000
    m.setword(rec + O['REC_CUE_START'], 10); m.setword(rec + O['REC_CUE_END'], 95)
    expect(call(m, fn(m, F_SECONDS), lib(m), rec) == 85, 'seconds: a CUE track with both ends is end - start (the durations table\'s dur_song)')
    expect(call(m, fn(m, F_SECONDS), lib(m), m.songs[1]) == 0, 'seconds: a track not in the table is unknown (0)')
    out = m.alloc(32); m.u.mem_write(out, b'\xff' * 32)
    call(m, fn(m, F_ROW), lib(m), rec, out)
    expect(bytes(m.u.mem_read(out, 20)) == bytes(20) and bytes(m.u.mem_read(out + 20, 12)) == b'\xff' * 12, 'row: ls_row_t cleared (five ints), nothing beyond')
    expect(fn(m, 40) == 0, 'playing (lib_src_t, offset 40): NULL for the stock source, the pages keep today\'s is_playing test')
    expect(fn(m, 48) == 7 and fn(m, 52) == 0, 'caps (offset 48): Cover Flow, Search and Select (LS_CAP_ALL); count (52): NULL, the stock queries answer at once')
    fake = m.alloc(56); m.u.mem_write(fake, bytes(56)); m.setword(fake + 48, 2)
    expect([m.call(PSYMS['ls_caps'], a0=a, count=2000000) for a in (0, lib(m), fake)] == [7, 7, 2], 'ls_caps: LS_CAP_ALL for NULL and &lib_stock, the source\'s own caps otherwise')
    expect(call(m, fn(m, F_ACT), lib(m), rec, 1) & 0xffffffff == 0xffffffff and call(m, fn(m, F_GEN), lib(m)) == 0, 'act: unsupported (-1); gen: 0')


def run_play(how_call, at, how, mode, drop_file=False):
    """One play on a fresh machine: (the result, the calls, (the queue's paths, the index) or None, the play mode, the class left)."""
    m = machine(); m.mode = mode; m.seed = 7
    if drop_file: m.present.discard('/mnt/mmc/m/%d.flac' % at)
    lst = m.new_deque(m.songs)
    m.setword(AP.SHOWLIST, lst)   # (the shown list loadSongList reads, as the page left it)
    m.played = None
    ret = how_call(m, lst, at, how)
    played = None if m.played is None else ([m.read_cstr(m.word(r + O['REC_PATH'])) for r in m.played[0]], m.played[1])
    return ret & 0xffffffff, list(m.calls), played, m.mode, m.word(AP.G_CLASS)


def play_tests(ctx):
    """3. play: so_play, so_play_src(NULL), so_play_src(&lib_stock) and lib_stock.play are one path."""
    expect = ctx.expect
    OPEN = PSYMS['pod_open_player']

    def direct(m, lst, at, how):   # so_play(cls, list, at, how, open)
        return call(m, PSYMS['so_play'], AP.LIB, lst, at, how, OPEN)

    def src(which):   # so_play_src(src, cls, list, at, how, open)
        return lambda m, lst, at, how: call(m, PSYMS['so_play_src'], which(m), AP.LIB, lst, at, how, OPEN)

    def via_ptr(m, lst, at, how):   # lib_stock.play(s, list, at, how, open, cls)
        return call(m, fn(m, F_PLAY), lib(m), lst, at, how, OPEN, AP.LIB)

    for at, how, mode, label in ((2, 0, 0, 'a row tap'), (0, 1, 2, 'Play'), (-1, 2, 0, 'Shuffle')):
        ref = run_play(direct, at, how, mode)
        expect(ref[2] is not None and ref[0] == 0, f'{label}: so_play starts a queue and returns 0 ({ref[2] and ref[2][1]})')
        for nm, f in (('so_play_src(NULL)', src(lambda m: 0)), ('so_play_src(&lib_stock)', src(lib)), ('lib_stock.play', via_ptr)):
            got = run_play(f, at, how, mode)
            expect(got == ref, f'{label}: {nm} is so_play: {got} vs {ref}')
    ref = run_play(direct, 1, 0, 0, drop_file=True)
    got = run_play(via_ptr, 1, 0, 0, drop_file=True)
    expect(ref[0] == 0xffffffff and ref[2] is None and got == ref and any(c[0] == 'toast' and c[1] == 'Storage unavailable' for c in got[1]),
           f'a track not on the card: -1, "Storage unavailable", nothing starts, the same through the seam: {got}')


def poll_machine():
    """The album machine with three page callbacks written as MIPS code in memory (ask, spin, giveup): each counts its calls in m.cpmem (word 2k) and returns the word after it (spin: m.spin_n);
    and a page's ls_cpoll_t (m.cp, 8 words). (A trapped address cannot be called from m.call, so the callbacks are real code.)"""
    m = machine()
    m.top_main = m.window
    m.cp = m.alloc(32)
    m.u.mem_write(m.cp, bytes(32))
    m.cpmem = m.alloc(32)
    m.u.mem_write(m.cpmem, bytes(32))
    m.cbs = {}
    for k, nm in enumerate(('ask', 'spin', 'giveup')):
        ctr = m.cpmem + 8 * k
        hi, lo = ((ctr + 0x8000) >> 16) & 0xffff, ctr & 0xffff
        code = [0x3c090000 | hi, 0x8c000000 | 9 << 21 | 8 << 16 | lo, 0x24000000 | 8 << 21 | 8 << 16 | 1, 0xac000000 | 9 << 21 | 8 << 16 | lo,
                0x8c000000 | 9 << 21 | 2 << 16 | ((lo + 4) & 0xffff), 0x03e00008, 0]
        m.cbs[nm] = m.alloc(32)
        m.u.mem_write(m.cbs[nm], b''.join(struct.pack('<I', w) for w in code))
    return m


def cp_count(m, nm):
    return m.word(m.cpmem + 8 * ('ask', 'spin', 'giveup').index(nm))


def cp_reset(m):
    spin = m.word(m.cpmem + 12)
    m.u.mem_write(m.cpmem, bytes(32))
    m.setword(m.cpmem + 12, spin)


def poll(m):
    """The page saw a cover answer 0: ls_cover_poll(cp, win, ask, spin, giveup)."""
    call(m, PSYMS['ls_cover_poll'], m.cp, m.window, m.cbs['ask'], m.cbs['spin'], s0=m.cbs['giveup'])


def tick(m):
    return m.call(PSYMS['ls_cover_tick'], a0=0x5a5a5a50, count=900000000)


def poll_tests(ctx):
    """4. The shared cover poll (ls_cover_poll / ls_cover_tick / ls_cover_end): one 250 ms timer; a pending page is asked and spun only while it is the top window with the screen lit; two quiet ticks end it;
    LS_COVER_POLLS asks without the cover is the one give-up (the page's giveup runs, nothing asks again); a page that polls again afterwards starts a fresh count; ls_cover_end removes the timer."""
    expect = ctx.expect
    RET_REPEAT = 8
    n = lambda m: (cp_count(m, 'ask'), cp_count(m, 'spin'), cp_count(m, 'giveup'))
    m = poll_machine()
    poll(m)
    timers = [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick']]
    poll(m)
    expect(len(timers) == 1 and timers[0][2] == 250 and not [c for c in m.calls if c[0] == 'timer_add'], f'a pending cover arms one 250 ms timer, a second call adds none ({timers})')
    # a page that is not on top, or a dark screen: the timer stays, nothing is asked or turned
    m.top_main = 0
    expect(tick(m) == RET_REPEAT and n(m) == (0, 0, 0), f'not the top window: the poll waits ({n(m)})')
    m.top_main = m.window; m.screen(0)
    expect(tick(m) == RET_REPEAT and n(m) == (0, 0, 0), 'the screen dark: the poll waits')
    m.screen(1)
    expect(tick(m) == RET_REPEAT and n(m) == (1, 1, 0), f'on top and lit: asked, then the spinners turn ({n(m)})')
    # nothing pending again: two quiet ticks end it (a spinner count of 0)
    expect(tick(m) == RET_REPEAT and n(m) == (1, 2, 0), 'a quiet tick only turns the spinners')
    expect(tick(m) != RET_REPEAT and n(m) == (1, 3, 0), f'the second quiet tick ends the poll, no give-up when no spinner is left ({n(m)})')
    # a spinner still turning when the poll ends is stale: cleared through giveup
    m = poll_machine(); m.setword(m.cpmem + 12, 3)
    poll(m); tick(m); tick(m)
    expect(tick(m) != RET_REPEAT and n(m)[2] == 1, f'a spinner left after two quiet ticks is cleared ({n(m)})')
    # the give-up rule: LS_COVER_POLLS (1200) asks of a cover that never lands
    m = poll_machine()
    for _ in range(1200):
        poll(m)
        tick(m)
    expect(n(m)[0] == 1200 and n(m)[2] == 0, f'1200 asks without the cover: still asking ({n(m)})')
    poll(m); cp_reset(m)
    expect(tick(m) != RET_REPEAT and n(m) == (0, 0, 1), f'the next ask is the give-up: the page clears its spinners, nothing is asked, the poll ends ({n(m)})')
    # a file that lands later: the page asks again (a tile loaded, a gen re-read) and the count starts afresh
    poll(m)
    expect(any(c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick'] for c in m.calls), 'polling again after the give-up arms the timer again')
    cp_reset(m)
    for _ in range(300):
        tick(m); poll(m)
    expect(n(m)[0] == 300 and n(m)[2] == 0, f'and asks afresh ({n(m)})')
    # the page's end
    call(m, PSYMS['ls_cover_end'], m.cp)
    expect(any(c[0] == 'timer_remove' for c in m.calls) and tick(m) != RET_REPEAT, 'ls_cover_end removes the timer with the last page')
    # two pages stacked: the top one is asked, the one below waits
    m = poll_machine()
    cp2 = m.alloc(32); m.u.mem_write(cp2, bytes(32))
    poll(m)
    call(m, PSYMS['ls_cover_poll'], cp2, 0x20009999, m.cbs['ask'], m.cbs['spin'], s0=m.cbs['giveup'])
    expect(tick(m) == RET_REPEAT and n(m) == (1, 1, 0), f'two pages polling: only the one on top is asked ({n(m)})')


SECTIONS = [list_tests, extras_tests, play_tests, poll_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

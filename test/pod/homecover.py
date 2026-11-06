"""Home cover build (patch/homecover.c, docs/modules/homecover.md): the progress line "Preparing covers n/m" above the Home list while the shared worker builds the
albums that have no cache file. Hidden when nothing is missing and after the build; the list moves down by HC_H while it shows; the worker stops in the background
and on destroy and is offered again at the next foreground; it never starts while another set (Cover Flow, Albums) holds the worker."""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

import pod_recent
import pod_i18n

CFSORT_FILE = '/mnt/data/m1plus/album-order'
RECENT = '/mnt/mmc/.m1plus/recently-played'
HC_X, HC_Y, HC_W, HC_H, HOME_PAD, WIN_H = (O[k] for k in ('HC_X', 'HC_Y', 'HC_W', 'HC_H', 'HOME_PAD', 'WIN_H'))
START_MS, POLL_MS, RESUME_MS = O['RC_RESOLVE_MS'], 500, 1000   # (HC_RESUME_MS is a #define of homecover.c, not an offset)


def key_of(i): return album_key(f'Artist {i}', f'Album {i}')


REQ = '/mnt/data/m1plus/covers-rebuild'
STAMP, DB = '/mnt/mmc/.m1plus/cache-stamp', '/mnt/data/database.db'


def hash_of(n): return sum(key_of(i) for i in range(n)) & 0xffffffff


def stamp_text(n, covers=True, tracks=True, h=None):
    h = hash_of(n) if h is None else h
    return (f'covers {n} {h:08x}\n' if covers else '') + (f'tracks {n} {h:08x}\n' if tracks else '')


def home_machine(n=8, missing=(), empty=(), rebuild=False, stamp='stale', start=True, songs=False):
    """The Home instance's widgets (plain ones: the line, the list_view, the scroll view and its bar) and n albums in the stock list, each with a cache
    file unless it is in missing (no file) or empty (the zero-length 'no art' marker). stamp: the card's stamp text; 'stale' (the default) a stamp of another library, so the pill
    shows when the scan begins (the first open since the boot reads the library); None: no stamp (the waiting pill shows at once)."""
    m = Machine()
    m.fs[CFSORT_FILE] = b'0\n'
    if stamp == 'stale': stamp = stamp_text(n, h=hash_of(n) ^ 0x10)
    if stamp is not None: m.fs[STAMP] = stamp.encode()
    m.dirs.add('/mnt/mmc/.m1plus')
    m.db = {DB: [100, 0, 4096]}
    if rebuild: m.fs[REQ] = b'1\n'   # Settings > Library > Rebuild Covers was confirmed
    m.window = m.widget('home_window')
    for w in ('pod_cache_pill', 'pod_cover_prog', 'pod_cache_fill', 'pod_cache_x', 'pod_listview', 'pod_scrollview', 'scroll_bar_m'): m.widget(w)
    m.props[(m.widgets['pod_scrollview'], 'w')] = 310
    m.props[(m.widgets['scroll_bar_m'], 'w')] = 10
    song = m.record(path='/mnt/mmc/m/0/1.cue', rid=1000); m.setword(song + O['REC_CUE_START'], 1); m.setword(song + O['REC_CUE_END'], 2)
    m.class_lists[O['CLASS_ALL_SONGS']] = [song] if songs else []   # songs: one CUE track with both ends (nothing to measure); else the list is empty, which with albums reads as a failed query (the song pass writes no tracks line)
    m.showlist = [m.record(album=f'Album {i}', artist=f'Artist {i}', path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i in range(n)]
    m.present |= {f'/mnt/mmc/m/{i}/1.flac' for i in range(n)}
    for i in range(n):
        if i not in missing:
            p = art_file(key_of(i))
            m.present.add(p); m.files[p] = 0 if i in empty else 4096
    if start: m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    return m


def label(m): return m.widgets['pod_cover_prog']
def pill(m): return m.widgets['pod_cache_pill']
def lv(m): return m.widgets['pod_listview']


def shown_calls(m, calls=None):
    """[(visible, sensitive)] changes of the pill in the given calls."""
    calls = m.calls if calls is None else calls
    return [(c[0], c[2]) for c in calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == pill(m)]


def pill_up(m, calls=None):
    """The pill is shown now (the last visibility change on it was to visible; m.calls holds only the last call's, so the stored property is read)."""
    return bool(m.props.get((pill(m), 'visible'), 0))


def list_down(m, calls=None):
    """The list was last moved down by the pill (a move to HOME_PAD + HC_H after the last move back)."""
    v = [c[3] for c in (m.calls if calls is None else calls) if c[0] == 'widget_move' and c[1] == lv(m)]
    return bool(v and v[-1] != HOME_PAD)


def texts(m, calls=None, waiting=False):
    """The pill's text changes; the waiting texts ("Checking library." and its dots) only when asked (a count never ends in a dot)."""
    return [c[2] for c in (m.calls if calls is None else calls) if c[0] == 'widget_set_text_utf8' and c[1] == label(m) and (waiting or not c[2].endswith('.'))]


def adds(calls):
    """The timer_add calls other than the waiting text's dot timer."""
    return [c for c in calls if c[0] == 'timer_add' and c[1] != PSYMS['hc_on_dots']]


def scan(m, limit=100):
    """The start timer's callback until it stops re-arming itself (the scan steps, then the worker starts)."""
    for _ in range(limit):
        new = fired(m, 'hc_on_start', 400000000)
        if not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['hc_on_start']]: return new
    raise AssertionError('the scan did not end')


def hook(m, fn, win=None, count=6000000):
    """A window handler (ctx = the window) runs: the calls it made."""
    m.call(PSYMS[fn], a0=m.window if win is None else win, a1=0, count=count)
    return list(m.calls)


def finish_worker(m, files):
    """The worker finishes the given album numbers: their cache files appear and the done counter moves."""
    for i in files:
        p = art_file(key_of(i)); m.present.add(p); m.files[p] = 4096
    m.call(PSYMS['cc_worker'], count=5000000)


def tests(ctx):
    expect = ctx.expect
    START, POLL = PSYMS['hc_on_start'], PSYMS['hc_on_poll']

    # 1. Start: the window's events are bound and one one-shot is armed HC_START_MS out; nothing is scanned, shown or moved yet.
    m = home_machine(6, missing={2, 4})
    binds = {c[2] for c in m.calls if c[0] == 'widget_on' and c[1] == m.window}
    expect({O['EVT_DESTROY'], O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']} <= binds, 'destroy, to-background and to-foreground are bound')
    expect(adds(m.calls) == [('timer_add', START, START_MS)], f'one start timer, {START_MS} ms out')
    expect(not shown_calls(m) and build_state(m)['jobs'] == 0 and 'pthread_create' not in m.names(), 'the line is hidden and nothing is scanned at start')
    expect(not [c for c in m.calls if c[0] == 'access' and '.m1plus' in str(c[1])], 'start stats no cache file')

    # 2. The scan queues the albums with neither a picture nor the marker, in the list's order; the worker starts after the last step; the line shows 0/2
    #    and the list makes room for it.
    new = scan(m)
    s = build_state(m)
    expect(s['running'] == 1 and s['mode'] == 0 and s['total'] == 2 and [t for t, _ in build_jobs(m)] == ['/mnt/mmc/m/2/1.flac', '/mnt/mmc/m/4/1.flac'],
           f'one CC_MISSING worker, the jobs are the missing albums in the list order ({s})')
    expect(shown_calls(m, new) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)], 'the line is shown: visible and sensitive together')
    expect(texts(m, new) == ['Preparing covers 0/2'], f'the line reads "Preparing covers 0/2" ({texts(m, new)})')
    expect(('widget_move', lv(m), 0, HOME_PAD + HC_H) in new and ('widget_resize', lv(m), 320, WIN_H - 2 * HOME_PAD - HC_H) in new,
           'the list moves down by the line and shrinks by it')
    expect(('widget_resize', m.widgets['pod_scrollview'], 310, WIN_H - 2 * HOME_PAD - HC_H) in new and ('widget_resize', m.widgets['scroll_bar_m'], 10, WIN_H - 2 * HOME_PAD - HC_H) in new,
           'and so do its scroll view and bar')
    expect(HC_Y == HOME_PAD and O['HC_PH'] + 8 == HC_H and HC_X == 12 and HC_W == 296, 'the pill lies above the first row; the list starts a pill and 8 px of air lower')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == POLL] == [('timer_add', POLL, POLL_MS)], 'the poll runs every 500 ms')

    # 3. The poll shows n/m as the done counter advances and lets the Recently Played tiles retry; the end hides the line, restores the list and stops the worker.
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    new = fired(m, 'hc_on_poll')
    expect(texts(m, new) == ['Preparing covers 1/2'] and not shown_calls(m, new) and [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'half done: "1/2", the line stays, the poll re-arms')
    new = fired(m, 'hc_on_poll')
    expect(not texts(m, new), 'a poll with no advance rewrites nothing')
    finish_worker(m, (2, 4))
    new = fired(m, 'hc_on_poll', 40000000)
    s = build_state(m)
    expect(shown_calls(m, new) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'done: the line is hidden and insensitive')
    expect(('widget_move', lv(m), 0, HOME_PAD) in new and ('widget_resize', lv(m), 320, WIN_H - 2 * HOME_PAD) in new, 'the list is back where it was')
    expect(s['jobs'] == 0 and [c for c in new if c[0] == 'pthread_join'] and not adds(new), f'the worker is joined, the set freed, the poll ends ({s})')
    expect(not [c for c in fired(m, 'hc_on_poll', 1000000) if c[0] in ('timer_add', 'widget_set_text_utf8')], 'a late poll does nothing')

    # 3b. Recently Played's albums are queued first, most recent first (the shelf's placeholders go first); a stale shelf key is corrected from the list.
    m = home_machine(6, missing={1, 3, 5})
    m.fs[RECENT] = pod_recent.dump([(pod_recent.identity(f'Album {i}'), album_key('Old Row', f'Album {i}'), 1, f'Album {i}', 'Old Row', f'/x/{i}.flac') for i in (5, 3, 0)])
    scan(m)
    expect([t for t, _ in build_jobs(m)] == ['/mnt/mmc/m/5/1.flac', '/mnt/mmc/m/3/1.flac', '/mnt/mmc/m/1/1.flac'] and build_state(m)['total'] == 3,
           f'the shelf\'s missing albums first, in its order, then the rest, each once ({build_jobs(m)})')
    expect([e[1] for e in pod_recent.parse(m.fs[RECENT])] == [key_of(5), key_of(3), key_of(0)], 'the shelf\'s stale keys are the rows\' now')
    m = home_machine(6, missing={1, 3, 5}); m.fs[CFSORT_FILE] = b'1\n'
    m.fs[RECENT] = pod_recent.dump([(pod_recent.identity('Album 3'), key_of(3), 1, 'Album 3', 'Artist 3', '/x/3.flac')])
    scan(m)
    expect([t for t, _ in build_jobs(m)][0] == '/mnt/mmc/m/3/1.flac' and build_state(m)['total'] == 3, f'with the artist order too ({build_jobs(m)})')

    # 4. Nothing missing (a picture or the marker for every album): never shown, no worker, no list move; the next foreground scans again.
    m = home_machine(8, empty={3}, stamp=stamp_text(8, covers=False))
    new = scan(m)
    expect(not pill_up(m, new) and not texts(m, new) and 'pthread_create' not in [c[0] for c in new] and build_state(m)['jobs'] == 0
           and not list_down(m, new), 'a complete cache: the waiting pill is gone, no count, no worker, the list back')
    expect(m.fs.get(STAMP, b'').decode().startswith('covers 8 ') and 'tracks 8 ' in m.fs[STAMP].decode(), 'and the covers line is written beside the tracks one')
    expect(not [c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add' or (c[0] == 'access' and '.m1plus/covers' in str(c[1]))], 'the next foreground (stamp current, database untouched) arms nothing and looks at no cache file')
    # an empty library
    m = home_machine(0); new = scan(m)
    expect(not pill_up(m, new) and 'pthread_create' not in [c[0] for c in new] and 'covers 0 ' in m.fs[STAMP].decode(), 'no albums: nothing, the stamp of an empty library')

    # 5. The scan is bounded per step (64 albums a tick) and the line appears only after the last one.
    m = home_machine(300, missing={250})
    steps = 0
    for _ in range(20):
        new = fired(m, 'hc_on_start', 400000000)
        steps += 1
        expect(len([c for c in new if c[0] == 'access' and '.m1plus/covers' in str(c[1])]) <= 128, 'at most 64 albums, two cache files each (picture, .bad), checked a step')
        if not [c for c in new if c[0] == 'timer_add' and c[1] == START]: break
        expect(not texts(m, new) and pill_up(m), 'no count while the scan runs (the waiting pill is up)')
    expect(steps == 5 and texts(m, new) == ['Preparing covers 0/1'] and build_state(m)['total'] == 1, f'300 albums: five steps, then the line ({steps})')
    # a destroy in the middle of a scan drops the set
    m = home_machine(300, missing={250}); fired(m, 'hc_on_start', 400000000)
    hook(m, 'hc_on_destroy')
    expect(build_state(m)['jobs'] == 0 and ('timer_remove', 0x777) in m.calls and 'pthread_create' not in m.names(), 'destroy mid-scan: the timer is removed, the set freed')

    # 6. Background: the worker is cancelled and joined, the line hidden, the list restored, the timer gone; the foreground offers the build again.
    m = home_machine(6, missing={2, 4}); scan(m)
    hook(m, 'hc_on_background')
    s = build_state(m)
    expect(count_of(m, 'pthread_join') == 0 and s['orphan'] == 1 and s['cancelled'] == 1 and ('timer_remove', 0x777) in m.calls, f'background cancels the worker without joining it and removes the poll ({s})')
    expect(shown_calls(m)[-2:] == [('widget_set_visible', 0), ('widget_set_sensitive', 0)] and ('widget_move', lv(m), 0, HOME_PAD) in m.calls, 'and hides the line and restores the list')
    expect(not [c for c in fired(m, 'hc_on_poll', 1000000) + fired(m, 'hc_on_start', 1000000) if c[0] in ('timer_add', 'pthread_create', 'access')], 'late timers in the background do nothing')
    new = hook(m, 'hc_on_foreground')
    expect(adds(new) == [('timer_add', START, RESUME_MS)], 'the foreground arms the start again (1 s: the pill was up when Home left)')
    expect(not [c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add'], 'and only once while it is pending')
    new = fired(m, 'hc_on_start', 400000000)
    expect(adds(new) == [('timer_add', START, 500)] and build_state(m)['orphan'] == 1 and 'pthread_create' not in [c[0] for c in new],
           'the orphan still inside its job: the start asks again later, nothing starts')
    m.present |= {f'/mnt/mmc/m/{i}/1.flac' for i in range(6)}
    m.call(PSYMS['cc_worker'], count=5000000)       # the orphan exits
    scan(m)
    expect(build_state(m)['running'] == 1 and pill_up(m), 'the build resumes and shows the line again')
    expect(not [c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add'], 'foreground while the worker runs arms nothing')

    # 7. Destroy: cancelled and joined, line hidden; a late callback does nothing.
    m = home_machine(6, missing={2, 4}); scan(m)
    hook(m, 'hc_on_destroy')
    expect(count_of(m, 'pthread_join') == 0 and build_state(m)['orphan'] == 1 and ('timer_remove', 0x777) in m.calls, 'destroy cancels the worker without joining and removes the poll')
    expect(not [c for c in fired(m, 'hc_on_poll', 1000000) + fired(m, 'hc_on_start', 1000000) if c[0] in ('timer_add', 'pthread_create', 'access')], 'late callbacks after destroy do nothing')
    m = home_machine(6, missing={2}); hook(m, 'hc_on_destroy')
    expect(('timer_remove', 0x777) in m.calls and not shown_calls(m), 'destroy before the start fired removes the one-shot')
    m = home_machine(6, missing={2}); hook(m, 'hc_on_destroy', win=0x1234)
    expect(('timer_remove', 0x777) not in m.calls, 'another window\'s destroy is ignored')

    # 8. The worker belongs to one owner at a time: held by Cover Flow / Albums (any set), Home starts nothing and shows nothing; its set is left alone.
    m = home_machine(6, missing={2, 4})
    m.call(PSYMS['cc_build_open'], a0=6, a1=0, count=2000000)
    new = fired(m, 'hc_on_start', 4000000)
    expect(not shown_calls(m, new) and not [c for c in new if c[0] in ('pthread_create', 'timer_add', 'widget_move')] and build_state(m)['jobs'] != 0, 'a held worker: nothing starts')
    hook(m, 'hc_on_background')
    expect(build_state(m)['jobs'] != 0 and not [c for c in m.calls if c[0] == 'pthread_join'], 'background does not stop a set Home does not own')
    expect([c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add'], 'and the foreground offers again')

    # 9. No space, no thread, no timer: Home unchanged, nothing held.
    m = home_machine(6, missing={2}); m.free_mb = 2; new = scan(m)
    expect(not pill_up(m, new) and 'pthread_create' not in [c[0] for c in new] and build_state(m)['jobs'] == 0 and not list_down(m, new), 'a full card: the pill hides, no worker')
    expect(f'covers 6 {hash_of(6):08x}' not in m.fs[STAMP].decode(), 'and the covers line is not written (Home asks again)')
    m = home_machine(6, missing={2}); m.thread_ok = False; new = scan(m)
    expect(not pill_up(m, new) and build_state(m)['jobs'] == 0 and not list_down(m, new), 'a refused thread: the pill hides, the set freed')
    m = home_machine(6, missing={2}); m.timer_fail = True; fired(m, 'hc_on_start', 400000000)
    expect(build_state(m)['orphan'] == 1 and count_of(m, 'pthread_join') == 0 and shown_calls(m)[-2:] == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'a poll timer that cannot be made: stopped, hidden')
    m = Machine(); m.widget('home_window'); m.window = m.widgets['home_window']
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    expect('timer_add' not in m.names(), 'an asset without the line (not ours): nothing is armed')
    m = Machine(); m.timer_fail = True
    for w in ('home_window', 'pod_cache_pill', 'pod_cover_prog', 'pod_cache_fill', 'pod_cache_x', 'pod_listview'): m.widget(w)
    m.call(PSYMS['homecover_start'], a0=m.widgets['home_window'], count=2000000)
    new = fired(m, 'hc_on_start', 4000000)
    expect(not [c for c in new if c[0] in ('pthread_create', 'access')], 'a start timer that cannot be made: Home never builds')


def rebuild_tests(ctx):
    """A requested Rebuild Covers (REBUILD_FILE): the scan opens a CC_REBUILD set with every album, the line reads Rebuilding covers, the request ends with the set."""
    expect = ctx.expect
    OLD = 111
    START = PSYMS['hc_on_start']

    def machine(n=3, **kw):
        m = home_machine(n, rebuild=True, **kw)
        for i in range(n):
            p = art_file(key_of(i)); m.files[p] = OLD
        return m

    # 1. A complete cache is queued whole, in CC_REBUILD mode; the line says Rebuilding covers 0/3.
    m = machine(); new = scan(m); s = build_state(m)
    expect(s['running'] == 1 and s['mode'] == 1 and s['total'] == 3 and [k for _, k in build_jobs(m)] == [key_of(i) for i in range(3)], f'every album is a job, CC_REBUILD ({s})')
    expect(texts(m, new) == ['Rebuilding covers 0/3'] and pill_up(m), f'the line reads Rebuilding covers 0/3 ({texts(m, new)})')
    expect(REQ in m.fs, 'the request stays while the rebuild runs')

    # 2. The worker replaces each file (temp, rename), a marker too; the request ends only when the set is done.
    dst = [art_file(key_of(i)) for i in range(3)]
    m.files[dst[1]] = 0
    m.album_cover = 1
    m.setword(PSYMS['cb'] + 4 * 5, 1)   # album 0 is done (the mock worker takes up at job 1)
    new = fired(m, 'hc_on_poll')
    expect(texts(m, new) == ['Rebuilding covers 1/3'] and REQ in m.fs, 'part way: 1/3, the request stays')
    m.call(PSYMS['cc_worker'], count=5000000)
    renames = [c for c in m.calls if c[0] == 'rename' and c[2].endswith('.jpg')]
    expect([c[2] for c in renames] == dst[1:] and all(c[1] == c[2] + '.tmp' for c in renames) and m.files[dst[0]] == OLD and all(m.files[p] == 4096 for p in dst[1:]),
           'each cover is extracted to a temp file and renamed over the old one, the marker replaced by the new picture')
    new = fired(m, 'hc_on_poll', 40000000)
    expect(REQ not in m.fs and ('unlink', REQ) in new and [c for c in new if c[0] == 'pthread_join'] and shown_calls(m, new)[-2:] == [('widget_set_visible', 0), ('widget_set_sensitive', 0)],
           'done: the request file is removed, the worker joined, the line hidden')
    m2 = home_machine(3)
    scan(m2)
    expect(build_state(m2)['total'] == 0 and 'pthread_create' not in m2.names(), 'without a request the complete cache is not touched again')

    # 2b. A stalled set reads as finished but did not rebuild every album: the request stays, the next foreground resumes it.
    m = home_machine(3, rebuild=True); scan(m)
    m.setword(PSYMS['cb'] + 4 * 13, key_of(0)); m.setword(PSYMS['cb'] + 4 * 15, 1)   # album 0 hangs inside its extraction (cur, began)
    m.clock += 10000
    new = fired(m, 'hc_on_poll', 40000000)
    expect(REQ in m.fs and ('unlink', REQ) not in new and build_state(m)['orphan'] == 1 and m.call(PSYMS['cc_build_stalled']) == 1 and shown_calls(m, new)[-2:] == [('widget_set_visible', 0), ('widget_set_sensitive', 0)],
           'a stall during Rebuild Covers keeps the request; the line ends')
    m.call(PSYMS['cc_worker'], count=5000000)       # the hung job returns
    for mode in (2, 0):   # other sets come and go before the foreground
        assert m.call(PSYMS['cc_build_open'], a0=4, a1=mode) == 1
        m.call(PSYMS['cc_build_stop'])
    new = hook(m, 'hc_on_foreground')
    new = scan(m)
    expect(build_state(m)['mode'] == 1 and build_state(m)['total'] == 2 and REQ in m.fs and (art_file(key_of(0)) + '.bad' in m.fs or art_file(key_of(0)) + '.bad' in m.files), 'the next foreground resumes the rebuild without the hung album (its .bad)')
    m.call(PSYMS['cc_worker'], count=5000000)
    fired(m, 'hc_on_poll', 40000000)
    expect(REQ not in m.fs, 'and the resumed rebuild completes: the request is removed')

    # 3. Interrupted (background, destroy): the request stays, the worker is stopped; the next foreground starts the rebuild again from the first album.
    m = machine(); scan(m)
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    fired(m, 'hc_on_poll')
    hook(m, 'hc_on_background')
    expect(REQ in m.fs and build_state(m)['orphan'] == 1 and count_of(m, 'pthread_join') == 0, 'background mid-way: stopped, the request stays')
    m.call(PSYMS['cc_worker'], count=5000000)       # the orphan exits
    new = hook(m, 'hc_on_foreground')
    expect(adds(new) == [('timer_add', START, RESUME_MS)], 'the foreground arms the scan again (1 s: the pill was up)')
    new = scan(m)
    expect(build_state(m)['mode'] == 1 and build_state(m)['total'] == 3 and texts(m, new) == ['Rebuilding covers 0/3'], 'and the rebuild starts again from the beginning')
    hook(m, 'hc_on_destroy')
    expect(REQ in m.fs and build_state(m)['orphan'] == 1, 'destroy mid-way: the request stays')

    # 4. A held worker: nothing starts, the request stays; no space or no thread likewise.
    m = machine(); m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=2000000)
    new = fired(m, 'hc_on_start', 4000000)
    expect(not pill_up(m, new) and REQ in m.fs and not [c for c in new if c[0] == 'pthread_create'], 'a held worker: the pill hides, nothing starts, the request stays')
    m = machine(); m.free_mb = 2; scan(m)
    expect(REQ in m.fs and build_state(m)['jobs'] == 0 and 'pthread_create' not in m.names(), 'a full card: the request stays')

    # 4b. More albums than one set holds: every chunk is a rebuild, the request stays until the cursor reaches the end of the list.
    cap = 4000   # CC_MAX_JOBS
    m = home_machine(cap + 2, rebuild=True); scan(m, 200)
    expect(build_state(m)['mode'] == 1 and build_state(m)['total'] == cap and REQ in m.fs, 'a rebuild of 4002 albums: the first chunk holds 4000')
    m.setword(PSYMS['cb'] + 4 * 5, cap)
    new = fired(m, 'hc_on_poll', 400000000)
    expect(REQ in m.fs and ('unlink', REQ) not in new and ('timer_add', START, 20) in new, 'the first chunk ended: the request stays, the next chunk is chained')
    scan(m, 200)
    expect(build_state(m)['mode'] == 1 and build_state(m)['total'] == 2 and [t for t, _ in build_jobs(m)][0] == f'/mnt/mmc/m/{cap}/1.flac', 'the second chunk is a rebuild too, of the two left')
    m.setword(PSYMS['cb'] + 4 * 5, 2)
    new = fired(m, 'hc_on_poll', 400000000)
    expect(REQ not in m.fs and ('timer_add', START, 20) not in new and m.fs[STAMP].decode().startswith(f'covers {cap + 2} '), 'the end of the list: the request is removed, the line written, no third chunk')
    m = home_machine(cap + 2, rebuild=True); scan(m, 200)
    m.setword(PSYMS['cb'] + 4 * 5, cap); fired(m, 'hc_on_poll', 400000000); scan(m, 200)
    hook(m, 'hc_on_background'); m.call(PSYMS['cc_worker'], count=5000000)
    expect(REQ in m.fs, 'Home leaves in the second chunk: the request stays')
    hook(m, 'hc_on_foreground'); scan(m, 200)
    expect(build_state(m)['mode'] == 1 and build_state(m)['total'] == 2, 'the next foreground resumes the rebuild at the second chunk, not at the first album')

    # 5. No album has a track path: nothing to extract, nothing to wait for.
    m = home_machine(2, rebuild=True)
    for r in m.showlist: m.setword(r + O['REC_PATH'], 0)
    scan(m)
    expect(REQ not in m.fs and 'pthread_create' not in m.names(), 'nothing to extract: the request is dropped')


def resume_tests(ctx):
    """Back on Home after leaving it with the pill up (a build or its wait in progress): the start is armed HC_RESUME_MS out, not HC_START_MS; a silent probe, a stopped or a finished build keep the usual delay."""
    expect = ctx.expect
    START = PSYMS['hc_on_start']

    def starts(calls): return [c for c in calls if c[0] == 'timer_add' and c[1] == START]

    # 1. First open: 5 s. Leave mid-build and return: 1 s, and the build continues from there.
    m = home_machine(6, missing={2}, stamp=None)
    expect(starts(m.calls) == [('timer_add', START, START_MS)], 'first open: the start is 5 s out')
    scan(m)
    expect(pill_up(m), 'the build is running')
    hook(m, 'hc_on_background')
    new = hook(m, 'hc_on_foreground')
    expect(starts(new) == [('timer_add', START, RESUME_MS)], 'back mid-build: the start is 1 s out')
    m.call(PSYMS['cc_worker'], count=5000000)       # the orphan exits
    new = scan(m)
    expect(pill_up(m) and texts(m, new) == ['Preparing covers 0/1'], 'and the build continues')
    # 2. Leave during the 5 s wait with the pill shown: 1 s on return.
    m = home_machine(6, missing={2}, stamp=None)
    expect(pill_up(m), 'waiting pill up')
    hook(m, 'hc_on_background')
    expect(starts(hook(m, 'hc_on_foreground')) == [('timer_add', START, RESUME_MS)], 'left during the wait: 1 s on return')
    # 3. A silent probe (no pill): the full 5 s.
    m = home_machine(6, missing={1}, stamp=stamp_text(6), songs=True)
    expect(not pill_up(m), 'probe: no pill')
    hook(m, 'hc_on_background')
    expect(starts(hook(m, 'hc_on_foreground')) == [('timer_add', START, START_MS)], 'silent probe left and back: still 5 s')
    # 4. After the x: no restart.
    m = home_machine(6, missing={2}, stamp=None); scan(m)
    hook(m, 'hc_on_stop')
    hook(m, 'hc_on_background')
    expect(not starts(hook(m, 'hc_on_foreground')) and not pill_up(m), 'after the x: no restart')
    # 5. A finished build hides the pill: a later leave and return is the 5 s path (a changed database arms the silent probe).
    m = home_machine(6, missing={2}, stamp=None); scan(m)
    finish_worker(m, [2]); fired(m, 'hc_on_poll', 40000000); fired(m, 'hc_on_dscan')
    expect(not pill_up(m), 'the build finished: the pill is gone')
    hook(m, 'hc_on_background'); m.db[DB] = [101, 0, 4096]
    expect(starts(hook(m, 'hc_on_foreground')) == [('timer_add', START, START_MS)], 'after a finished build: 5 s')


def clear_tests(ctx):
    """Settings > Developer > Clear Cover Cache (clear_ask / homecover_clear): the confirm, then every file in the cache folder is removed in bounded steps."""
    expect = ctx.expect
    ART = '/mnt/mmc/.m1plus/covers'
    CONFIRM = 'Delete all cached covers? They will be made again on Home.'
    BUSY, DONE = 'Covers are being made, try later', 'Cover cache cleared'

    def machine(n=100, yes=True, loc=None):
        m = Machine()
        m.confirm_yes = yes
        if loc: m.set_language(loc)
        names = ['album'] + [f'r{i:08x}-168.jpg' for i in range(n)] + ['r000000aa-168.jpg.tmp', f'{0x1234:08x}-168.jpg', f'f{0x1234:08x}-168.jpg', 'r000000bb-168.jpg']
        m.listing[ART] = [('.', 4), ('..', 4)] + [(nm, 8) for nm in names]
        for nm in names:
            m.present.add(ART + '/' + nm); m.files[ART + '/' + nm] = 0 if nm == 'r000000bb-168.jpg' else 4096   # (the last is a no-art marker)
        m.fs[REQ] = b'1\n'
        return m, [ART + '/' + nm for nm in names]

    def unlinks(m): return [c[1] for c in m.calls if c[0] == 'unlink' and c[1] not in (REQ, STAMP)]
    def toasts(m): return [c[1] for c in m.calls if c[0] == 'toast']

    # Yes: the confirm, the request dropped at once, then ticks of at most 32 unlinks; the toast at the end.
    m, paths = machine()
    m.call(PSYMS['clear_ask'], count=3000000)
    expect([c[1] for c in m.calls if c[0] == 'confirm'] == [CONFIRM] and REQ not in m.fs and not toasts(m), 'the confirm is asked, the pending rebuild request is dropped, no toast yet')
    seen, ticks = [], 0
    while [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['cl_tick']] and ticks < 20:
        m.call(PSYMS['cl_tick'], count=4000000); ticks += 1
        seen.append(len(unlinks(m)))
        if not [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['cl_tick']]: break
    gone = [p for p in paths if p not in m.present]
    expect(set(gone) == set(paths), 'every file is deleted (pictures, markers, .tmp, unprefixed and f files, the old Cover Flow position file album)')
    expect(ticks >= 4 and all(n <= 32 for n in seen), f'bounded: {ticks} ticks of at most 32 unlinks ({seen})')
    expect(toasts(m) == [DONE] and not [c for c in m.calls if c[0] == 'unlink' and c[1] in ('.', '..')], 'the toast reads Cover cache cleared at the end')
    expect(m.open_dirs == {} , 'the directory handle is closed')

    # No (or a failed dialog): nothing at all.
    m, paths = machine(yes=False)
    m.call(PSYMS['clear_ask'], count=3000000)
    expect(not unlinks(m) and not toasts(m) and REQ in m.fs and 'timer_add' not in m.names() and 'opendir' not in m.names(), 'No: nothing is touched, the request stays')

    # The cover worker busy: refused with a toast before the dialog; nothing is deleted.
    m, paths = machine(); m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=2000000)
    m.call(PSYMS['clear_ask'], count=3000000)
    expect(toasts(m) == [BUSY] and 'confirm' not in m.names() and not unlinks(m) and REQ in m.fs and build_state(m)['jobs'] != 0, 'a busy worker: the toast, no dialog, nothing deleted, the set untouched')
    # a build that starts between the ticks stops the clearing (no toast)
    m, paths = machine(); m.call(PSYMS['clear_ask'], count=3000000)
    m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=2000000)
    m.call(PSYMS['cl_tick'], count=4000000)
    expect(not unlinks(m) and not toasts(m) and not adds(m.calls), 'a build started meanwhile: the clearing stops quietly')

    # No cache folder: nothing to delete, still the toast. A second ask while one runs starts no second timer.
    m = Machine(); m.confirm_yes = True; m.call(PSYMS['clear_ask'], count=3000000)
    expect(toasts(m) == [DONE] and not unlinks(m), 'no cache folder: nothing to delete, the toast')
    m, paths = machine(); m.call(PSYMS['clear_ask'], count=3000000); m.call(PSYMS['clear_ask'], count=3000000)
    expect(count_of(m, 'opendir') == 0 and not unlinks(m), 'a second ask while the clearing runs opens nothing')

    # All 13 languages: the confirm and the toasts.
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        m, _ = machine(n=3, loc=loc); m.call(PSYMS['clear_ask'], count=3000000)
        asked = [c[1] for c in m.calls if c[0] == 'confirm']
        m.call(PSYMS['cl_tick'], count=4000000)   # (a short listing ends in the first tick)
        expect(asked == [T(CONFIRM)] and toasts(m) == [T(DONE)], f'{loc}: confirm and done toast translated')
        m, _ = machine(n=3, loc=loc); m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=2000000); m.call(PSYMS['clear_ask'], count=3000000)
        expect(toasts(m) == [T(BUSY)], f'{loc}: busy toast translated')


def cache_tests(ctx):
    """Settings > Developer > Cover Cache (homecover_cache_open / homecover_stat): the counts in bounded steps, the Status line, the timers, the refresh after a clear."""
    expect = ctx.expect
    ART = '/mnt/mmc/.m1plus/covers'
    PAGE = 29
    ELL = '\xe2\x80\xa6'
    TICK, POLL = PSYMS['cp_tick'], PSYMS['cp_poll']

    def stat(m, idx):
        buf = m.alloc(64)
        m.call(PSYMS['homecover_stat'], a0=idx, a1=buf, a2=64)
        return m.read_cstr(buf)

    def values(m): return [stat(m, i) for i in range(7)]

    def machine(pictures=3, markers=2, old=3, albums=8, folder=True, big=0):
        """A Home machine (n albums, none with a cache file of the album's own name) plus a mixed cache folder: `pictures` r<key> files (400000 bytes; the keys of albums 0..),
        `markers` empty r files (the last is no album's), `old` stale files (unprefixed, f-prefixed, .tmp: 100000 bytes), `big` tiny pictures."""
        m = home_machine(albums, missing=set(range(albums)))
        names = [(f'r{key_of(i):08x}-168.jpg', 400000) for i in range(pictures)]
        names += [(f'r{key_of(pictures + i):08x}-168.jpg', 0) for i in range(markers - 1)] + [('r000000aa-168.jpg', 0)]
        names += [(f'{0x1234:08x}-168.jpg', 100000), (f'f{0x1234:08x}-168.jpg', 100000), (f'r{key_of(0):08x}-168.jpg.tmp', 100000)][:old]
        names += [(f'r{0x7000 + i:08x}-168.jpg', 10) for i in range(big)]
        for nm, size in names if folder else ():
            m.present.add(f'{ART}/{nm}'); m.files[f'{ART}/{nm}'] = size
        if folder: m.listing[ART] = [('.', 4), ('..', 4)] + [(nm, 8) for nm, _ in names]
        m.watch[PSYMS['pod_page_refresh']] = 'pod_page_refresh'
        return m, names

    def open_page(m):
        m.call(PSYMS['homecover_cache_open'], a0=m.window, a1=PAGE, count=3000000)
        return list(m.calls)

    def count_all(m, limit=60):
        """cp_tick until it stops re-arming: the files and albums looked at in each tick."""
        per = []
        for _ in range(limit):
            new = fired(m, 'cp_tick', 40000000)
            per.append(max(len([c for c in new if c[0] == 'fopen']), len([c for c in new if c[0] == 'access' and '/r' in str(c[1]) and not str(c[1]).endswith('.bad')])))
            if not [c for c in new if c[0] == 'timer_add' and c[1] == TICK]: return per
        raise AssertionError('the count did not end')

    # 1. Opening: events bound, the two timers armed, every count an ellipsis (Status is read at once); the open itself reads no file.
    m, names = machine()
    new = open_page(m)
    binds = {c[2] for c in new if c[0] == 'widget_on' and c[1] == m.window}
    expect({O['EVT_DESTROY'], O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']} <= binds, 'destroy, background and foreground are bound')
    expect([c for c in new if c[0] == 'timer_add' and c[1] in (TICK, POLL)] == [('timer_add', TICK, 20), ('timer_add', POLL, 500)], 'the count tick and the 500 ms poll are armed')
    expect(values(m)[:6] == [ELL] * 6 and values(m)[6] == 'Idle' and not [c for c in new if c[0] == 'fopen'], 'before counting every count is an ellipsis and Status is Idle')

    # 2. Counted: pictures, markers (the dot entries excluded), old files, albums, missing albums, size.
    count_all(m)
    tenths = ((3 * 400000 + 3 * 100000) // 1024 * 10 + 512) // 1024
    expect(values(m) == ['8', '3', '2', '4', '3', f'{tenths // 10}.{tenths % 10} MB', 'Idle'],
           f'Albums 8, Covers 3, No art 2, Missing 4 (albums 0..3 have their files in the folder), Old files 3, Size {tenths / 10} MB ({values(m)})')
    m, names = machine(old=0)
    for i in range(4):   # albums 0..2 have their pictures and 3 a marker (the cache files of their own keys)
        p = art_file(key_of(i)); m.present.add(p); m.files[p] = 400000 if i < 3 else 0
    open_page(m); count_all(m)
    expect(stat(m, 3) == '4' and stat(m, 4) == '0' and stat(m, 0) == '8', 'Missing = albums with neither a picture nor a marker by the CC_MISSING rule (albums 4..7)')
    m, names = machine(old=0)
    for i in range(4): m.present.add(art_file(key_of(i)))
    m.present.add(art_file(key_of(4)) + '.bad')
    open_page(m); count_all(m)
    expect(stat(m, 3) == '3', f'an album with a .bad marker is not missing: CC_MISSING never queues it ({stat(m, 3)})')

    # 3. Bounded: 143 pictures and 130 albums in steps of at most 64; the size has a decimal under 10 MB and none above.
    m, names = machine(albums=130, big=140)
    open_page(m); per = count_all(m)
    expect(len(per) >= 4 and max(per) <= 64, f'bounded steps: {len(per)} ticks of at most 64 files or albums ({per})')
    expect(stat(m, 1) == '143' and stat(m, 0) == '130' and stat(m, 5) == '1.4 MB' and m.open_dirs == {}, f'the counts after many ticks ({values(m)}), the directory is closed')
    m, _ = machine(pictures=0, markers=1, old=1); m.files[f'{ART}/{0x1234:08x}-168.jpg'] = 12 * 1024 * 1024
    open_page(m); count_all(m)
    expect(stat(m, 5) == '12 MB', f'from 10 MB up the size has no decimal ({stat(m, 5)})')

    # 4. No folder: zeros, Status Idle, every album missing; an empty library too.
    m, _ = machine(folder=False)
    open_page(m); count_all(m)
    expect(values(m) == ['8', '0', '0', '8', '0', '0.0 MB', 'Idle'], f'no cache folder: zeros and every album missing ({values(m)})')
    m = home_machine(0); open_page(m); count_all(m)
    expect(values(m)[:5] == ['0'] * 5, 'an empty library and no folder: all zeros')

    # 5. Status: Idle, Rebuild requested, Building (another page's set, n/m with jobs), Clearing, Preparing n/m and Rebuilding n/m (Home's own set).
    m, _ = machine(); open_page(m)
    expect(stat(m, 6) == 'Idle', 'Idle')
    m.fs[REQ] = b'1\n'
    expect(stat(m, 6) == 'Rebuild requested', 'Rebuild requested: the request file exists and nothing builds')
    del m.fs[REQ]
    m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=2000000)
    expect(stat(m, 6) == 'Building', 'Building (another page holds the worker, no jobs yet)')
    trk = m.alloc(32); m.u.mem_write(trk, b'/mnt/mmc/m/1/1.flac\0')
    m.call(PSYMS['cc_build_add'], a0=trk, a1=0x4321, count=2000000)
    expect(stat(m, 6) == 'Building 0/1', f'Building n/m ({stat(m, 6)})')
    m.call(PSYMS['cc_build_stop'], count=2000000)
    m, _ = machine(); m.confirm_yes = True; open_page(m)
    m.call(PSYMS['clear_ask'], count=3000000)
    expect(stat(m, 6) == 'Clearing', 'Clearing while the files are being deleted')
    m, _ = machine(); open_page(m); scan(m)
    expect(stat(m, 6) == 'Preparing 0/4', f'Preparing n/m while Home builds the missing covers ({stat(m, 6)})')
    m, _ = machine(); m.fs[REQ] = b'1\n'; open_page(m); scan(m)
    expect(stat(m, 6) == 'Rebuilding 0/8', f'Rebuilding n/m while Home rebuilds ({stat(m, 6)})')

    # 6. The poll refreshes the page when the Status changed, not otherwise, and re-arms itself.
    m, _ = machine(); open_page(m)
    new = fired(m, 'cp_poll', 2000000)
    expect(('pod_page_refresh', PAGE) not in new and [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'an unchanged Status: no refresh, the poll re-arms')
    m.fs[REQ] = b'1\n'
    new = fired(m, 'cp_poll', 2000000)
    expect(('pod_page_refresh', PAGE) in new and [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'a changed Status: the page is refreshed')
    expect(('pod_page_refresh', PAGE) not in fired(m, 'cp_poll', 2000000), 'and only once')

    # 7. Background and destroy: both timers removed, the directory closed, the album copy freed, late callbacks do nothing; the foreground counts again from nothing.
    m, _ = machine(albums=130, big=140); open_page(m); fired(m, 'cp_tick', 40000000)
    hook(m, 'cp_on_background')
    expect(len([c for c in m.calls if c[0] == 'timer_remove']) == 2 and m.open_dirs == {}, 'background removes the tick and the poll and closes the directory')
    late = fired(m, 'cp_tick', 4000000) + fired(m, 'cp_poll', 4000000)
    expect(not [c for c in late if c[0] in ('timer_add', 'readdir', 'fopen')], 'late callbacks in the background do nothing')
    new = hook(m, 'cp_on_foreground')
    expect([c for c in new if c[0] == 'timer_add' and c[1] in (TICK, POLL)] == [('timer_add', TICK, 20), ('timer_add', POLL, 500)] and stat(m, 1) == ELL, 'the foreground counts again from nothing')
    count_all(m)
    expect(stat(m, 1) == '143' and stat(m, 0) == '130', 'and gets the same counts')
    new = hook(m, 'cp_on_destroy')
    expect(len([c for c in new if c[0] == 'timer_remove']) == 1 and stat(m, 0) == ELL, 'destroy removes the poll (the count had ended) and forgets the counts')
    expect(not [c for c in fired(m, 'cp_tick', 4000000) + fired(m, 'cp_poll', 4000000) if c[0] in ('timer_add', 'readdir', 'fopen')], 'nothing runs after destroy')
    m, _ = machine(albums=130, big=140); open_page(m)
    for _ in range(5): fired(m, 'cp_tick', 40000000)      # the directory is done, the albums are under way
    hook(m, 'cp_on_destroy')
    expect(m.open_dirs == {} and [c for c in m.calls if c[0] == 'timer_remove'], 'destroy mid-count: the timers go')
    expect(not [c for c in hook(m, 'cp_on_foreground') if c[0] == 'timer_add'], 'a foreground for a window already gone does nothing')
    m, _ = machine(); m.widget_on_fail = frozenset({O['EVT_WINDOW_TO_BG']}); open_page(m)
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] == TICK], 'a refused event registration: nothing is counted')

    # 8. A clear finishing refreshes the counts (page in front); with no page open nothing of the page is armed.
    m, _ = machine(); m.confirm_yes = True; open_page(m); count_all(m)
    expect(stat(m, 1) == '3', 'counted before the clear')
    m.call(PSYMS['clear_ask'], count=3000000)
    new = fired(m, 'cl_tick', 4000000)
    expect([c for c in new if c[0] == 'timer_add' and c[1] == TICK] and ('pod_page_refresh', PAGE) in new, 'the clear ends: the page counts again')
    m.listing[ART] = [e for e in m.listing[ART] if e[1] == 4 or f'{ART}/{e[0]}' in m.present]   # (the mock directory forgets what was unlinked; the count that began inside the tick listed the old one: count again)
    hook(m, 'cp_on_foreground')
    count_all(m)
    expect(values(m) == ['8', '0', '0', '8', '0', '0.0 MB', 'Idle'], f'and finds an empty folder ({values(m)})')
    m, _ = machine(); m.confirm_yes = True
    m.call(PSYMS['clear_ask'], count=3000000)
    fired(m, 'cl_tick', 4000000)
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] in (TICK, POLL)], 'no Cover Cache page open: a clear arms no count')


def covlist_tests(ctx):
    """The No art / Missing rows of the Cover Cache page open a plain list (patch/covlist.c): tappable only when counted and not zero, the rows are the albums with an empty marker /
    with no file in the album list's order, a tap opens that album, the empty state, everything freed with the window."""
    expect = ctx.expect
    ART = '/mnt/mmc/.m1plus/covers'
    PAGE = 29

    def world(albums=8, marker=(3, 5), have=(0, 1), folder=True, sort=None):
        """A Home machine with `albums` albums; albums in `have` have a picture, those in `marker` an empty marker; the rest are missing. The cache folder lists exactly those files."""
        m = home_machine(albums, missing=set(range(albums)))
        if sort: m.fs[CFSORT_FILE] = sort
        files = [(f'r{key_of(i):08x}-168.jpg', 4096) for i in have] + [(f'r{key_of(i):08x}-168.jpg', 0) for i in marker]
        for nm, size in files:
            m.present.add(f'{ART}/{nm}'); m.files[f'{ART}/{nm}'] = size
        if folder: m.listing[ART] = [('.', 4), ('..', 4)] + [(nm, 8) for nm, _ in files]
        m.watch[PSYMS['pod_page_refresh']] = 'pod_page_refresh'
        # the list page's widgets as the Albums page's are: real widget structs for widget_to_local (window > list_view > scroll_view > view_grid)
        win, lv, sv = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180)
        m.u.mem_write(sv, bytes(0x180))
        for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, 400, win), (sv, 0, 400, lv)):
            for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
        m.setword(sv + 0x70, SV_VT); m.setword(sv + 8, 310)
        m.windows = {'m1plus_covlist': win}
        for w in ('btn_return', 'btn_backtoplayer', 'label_title', 'label_status', 'label_row_title', 'label_row_sub', 'view_grid'): m.widget(w)
        m.widgets['covlist_scrollview'] = sv
        view = m.widgets['view_grid']
        for off, v in ((4, 0), (8, 320), (0xc, 400), (0x44, sv)): m.setword(view + off, v)
        m.mem_geometry, m.live_scroll = True, frozenset({sv})
        m.cl_win = win
        return m

    def count(m):
        m.call(PSYMS['homecover_cache_open'], a0=m.window, a1=PAGE, count=3000000)
        for _ in range(30):
            new = fired(m, 'cp_tick', 40000000)
            if not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['cp_tick']]: return

    def tappable(m, idx):
        return bool(m.call(PSYMS['homecover_tappable'], a0=idx, count=100000))

    def paint(m):
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], m.alloc(0x80))
        m.texts.clear()
        m.call(PSYMS['cv_on_paint'], a0=0, a1=e, count=40000000)
        return [t for t, _ in m.texts]

    def open_list(m, idx):
        m.call(PSYMS['homecover_list_open'], a0=idx, count=6000000)
        return list(m.calls)

    # 1. Tappable only once counted and not zero: not while the page shows an ellipsis; the zero rows do nothing.
    m = world()
    m.call(PSYMS['homecover_cache_open'], a0=m.window, a1=PAGE, count=3000000)
    expect(not tappable(m, 2) and not tappable(m, 3), 'while counting neither row is tappable')
    open_list(m, 3)
    expect('window_open' not in m.names(), 'a tap while counting opens nothing')
    while True:
        new = fired(m, 'cp_tick', 40000000)
        if not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['cp_tick']]: break
    expect(tappable(m, 2) and tappable(m, 3), 'counted and not zero: both rows are tappable')
    m = world(marker=(), folder=True); count(m)
    open_list(m, 2)
    expect(not tappable(m, 2) and tappable(m, 3) and 'window_open' not in m.names(), 'no art 0: that row does nothing; Missing 6 still opens')
    m = world(have=(0, 1, 2, 3, 4, 5, 6, 7), marker=()); count(m)
    expect(not tappable(m, 2) and not tappable(m, 3), 'nothing missing, no marker: neither row opens')

    # 2. The lists: No Art = the albums with an empty marker, Missing = no file at all; each in the album list's order (stock order here and the Artist order below).
    m = world(); count(m)
    new = open_list(m, 3)
    expect(('window_open', 'm1plus_covlist') in new and ('widget_set_tr_text', m.widgets['label_title'], 'Missing Covers') in new, 'Missing Covers opens the plain list page with its title')
    texts = paint(m)
    expect(texts == ['Album 2', 'Album 4', 'Album 6', 'Album 7', 'Artist 2', 'Artist 4', 'Artist 6', 'Artist 7'], f'the missing albums in order, titles then artists ({texts})')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)
    m = world(); count(m)
    new = open_list(m, 2)
    expect(('widget_set_tr_text', m.widgets['label_title'], 'No Art') in new and paint(m) == ['Album 3', 'Album 5', 'Artist 3', 'Artist 5'], 'No Art lists the albums with an empty marker only (3 and 5)')
    # a tap on a row opens that album, as the Albums page does
    SCREEN_Y0 = 30 + 50

    def tap(m, x, y):
        for kind, t in (('down', 1000), ('up', 1080)):
            m.touch(kind, x, SCREEN_Y0 + y, t, fn='cv_on_' + kind)
        return list(m.calls)
    calls = tap(m, 100, 64 + 20)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 5) in calls, 'a tap on the second row opens that album (stock row 5)')
    m.touch('down', 100, SCREEN_Y0 + 20, 1000, fn='cv_on_down'); m.touch('up', 100, SCREEN_Y0 + 20 + 40, 1080, fn='cv_on_up')
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'a release far from the press (a drag) opens nothing')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)
    # the Artist order: display position d is stock row order[d]
    m = world(sort=b'1\n'); count(m)
    open_list(m, 2)
    rows = paint(m)
    m.touch('down', 100, SCREEN_Y0 + 20, 1000, fn='cv_on_down'); m.touch('up', 100, SCREEN_Y0 + 20, 1080, fn='cv_on_up')
    opened = [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']
    expect(len(rows) == 4 and opened and opened[0][3] == int(rows[0][len('Album '):]), f'in the Artist order the tap opens the stock row of the album shown ({rows}, {opened})')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)

    # 3. Empty after all (the list page opened with nothing: the build made them meanwhile): No albums, no view.
    m = world(); count(m)
    m.call(PSYMS['covlist_open'], a0=1, a1=0, a2=0, count=6000000)
    expect(('widget_set_tr_text', m.widgets['label_status'], 'No albums') in m.calls and ('widget_set_visible', m.widgets['view_grid'], 0) in m.calls, 'an empty list shows "No albums" and hides the view')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)

    # 4. Memory: the album copy, the order and the rows are freed with the window; a second open after the destroy works; a second open while one is up is refused.
    m = world(); count(m)
    open_list(m, 3)
    allocs_before = len([c for c in m.calls if c[0] == 'free'])
    expect(m.call(PSYMS['homecover_list_open'], a0=3, count=6000000) == 0xffffffff, 'a second list while one is up is refused')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)
    freed = [c for c in m.calls if c[0] in ('free', 'deque_destroy')]
    expect(len(freed) >= 3 and allocs_before >= 0, f'destroy frees the rows, the order and the album copy ({[c[0] for c in freed]})')
    open_list(m, 3)
    expect(('window_open', 'm1plus_covlist') in m.calls, 'a list can be opened again after the first closed')
    m.call(PSYMS['cv_on_destroy'], a0=0, a1=0, count=3000000)


def files_tests(ctx):
    """Settings > Developer > Tools > Settings Files (patch/setfiles.c): opens from Developer, every row's label, the values of a seeded file system, and no file read after the page opened."""
    expect, P = ctx.expect, pod_pages
    FP = P.FILES_PAGE
    d_i = next(i for i, r in enumerate(P.DEVELOPER_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.FILES_PAGE_INDEX)
    expect(P.DEVELOPER_PAGE.rows[d_i].label == 'Settings Files' and FP.title == 'Settings Files', 'Developer > Tools has a Settings Files link row that opens the page of that title')
    labels = [r.label for r in FP.rows]
    expect(labels == list(P.GUARD_FILES) + [P.FOLDER_LABEL] + list(P.SETTING_FILES) and all(r.action == P.ACT_INFO for r in FP.rows),
           'the rows: the four guard files, the folder, the setting files; all information rows')
    expect(sorted(r.arg for r in FP.rows) == list(range(P.INFO_SF, P.INFO_SF + len(FP.rows))), 'their kinds are unique and consecutive')
    D = '/mnt/data/'
    S = D + 'm1plus/'
    m = Machine()
    for n in ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(FP.rows))] + [f'pod_value{i}' for i in range(len(FP.rows))] + [f'pod_label{i}' for i in range(len(FP.rows))]:
        m.widget(n)
    m.fs[D + 'm1plus-start'], m.fs[D + 'm1plus-bad'] = b'1\n', b''
    m.present.add(S.rstrip('/'))
    m.fs.update({S + 'albums-view': b'1', S + 'playlists-view': b'0\n', S + 'recently-added-view': b'1\n', S + 'home-menu': b'6502\n', S + 'pulldown-tiles': b'2013-4567\n', S + 'cassette-theme': b'12', S + 'search-history': b'a\nb\nc\n',
                 S + 'covers-rebuild': b'1\n', S + 'battery-percentage': b'1'})
    m.call(PSYMS['on_row'], a0=PSYMS[f'pod_rows_{P.DEVELOPER_PAGE_INDEX}'] + 12 * d_i, count=6000000)
    expect(('window_open', FP.key) in m.calls, 'the link row opens m1plus_files')
    want = {'m1plus-start': '1', 'm1plus-run': 'missing', 'm1plus-bad': 'present', 'm1plus-off': 'missing', P.FOLDER_LABEL: 'present', 'albums-view': '1', 'playlists-view': '0', 'recently-added-view': '1',
            'album-order': 'missing', 'cassette-theme': 'other', 'home-menu': '6502', 'pulldown-tiles': '2013-4567', 'battery-percentage': '1', 'search-history': '3', 'covers-rebuild': 'present',
            'keyboard-pinyin': 'missing'}
    got = {r.label: next((c[2] for c in reversed(m.calls) if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[f'pod_value{i}']), None) for i, r in enumerate(FP.rows)}
    expect(all(got[k] == v for k, v in want.items()), f'the seeded values: {[(k, got[k], v) for k, v in want.items() if got[k] != v]}')
    del m.fs[S + 'albums-view']
    m.call(PSYMS['on_page_fg'], a0=P.FILES_PAGE_INDEX, a1=0, count=3000000)
    expect(not [c for c in m.calls if c[0] in ('open', 'read', 'access', 'timer_add')] and any(c[0] == 'widget_set_text_utf8' for c in m.calls),
           'a refresh of the page (foreground) shows the values it read at open and reads no file, adds no timer')


def dots_tests(ctx):
    """The waiting text's dots: one timer (hc_on_dots) cycles 1, 2, 3 dots after the translated text without its ellipsis; it ends with the waiting state."""
    expect = ctx.expect
    DOTS, REPEAT = PSYMS['hc_on_dots'], 8
    ELL = '\xe2\x80\xa6'   # (the harness reads C strings as latin-1 characters)

    def home(loc=None, **kw):
        m = home_machine(6, missing={2}, stamp=None, start=False, **kw)
        m.set_language(loc)
        m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
        return m

    def tick(m):
        ret = m.call(DOTS, count=400000)
        return ret, texts(m, waiting=True)

    def removes(m): return len([c for c in m.calls if c == ('timer_remove', 0x777)])

    # 1. Every language, both waiting texts: the label starts with one dot and the ticks cycle 2, 3, 1, 2 (the timer repeats).
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        for key, rebuild in (('Checking library…', False), ('Rebuilding covers…', True)):
            m = home(loc, rebuild=rebuild)
            base = T(key)[:-len(ELL)]
            expect(texts(m, waiting=True) == [base + '.'] and [c for c in m.calls if c == ('timer_add', DOTS, 400)], f'{loc} {key}: one dot at once, the dot timer armed at 400 ms')
            got = []
            for _ in range(4):
                ret, t = tick(m)
                got.append((ret, t))
            expect(got == [(REPEAT, [base + d]) for d in ('..', '...', '.', '..')], f'{loc} {key}: the dots cycle on the timer ({got})')
    # 2. The count takes over: the timer goes, a late tick does nothing and is not repeated.
    m = home(); scan(m)
    expect(removes(m) == 1 and texts(m) == ['Preparing covers 0/1'], 'the first count removes the dot timer')
    ret, t = tick(m)
    expect(ret == 0 and not t, 'a stale tick: nothing written, the timer ends')
    # 3. Background and destroy remove it (with the start timer); no timer is left, none is added by a late tick.
    m = home(); hook(m, 'hc_on_background')
    expect(removes(m) == 2, 'background removes the start timer and the dot timer')
    ret, t = tick(m)
    expect(ret == 0 and not t, 'a late tick in the background does nothing')
    new = hook(m, 'hc_on_foreground')
    expect([c for c in new if c == ('timer_add', DOTS, 400)] and texts(m, new, waiting=True) == ['Checking library.'], 'the foreground waits again: one dot, the timer armed once more')
    expect(len([c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add']) == 0, 'and not twice')
    m = home(); hook(m, 'hc_on_destroy')
    expect(removes(m) == 2, 'destroy removes both timers')
    # 4. The x ends the wait and the timer; a pill that hides at 5 s with nothing to do (a complete cache) leaves the timer to end itself on its next tick.
    m = home(); hook(m, 'hc_on_stop')
    expect(removes(m) == 2, 'the x removes the start timer and the dot timer')
    m = home_machine(6, stamp=stamp_text(6), start=False); m.db = {DB: [100, 0, 4096]}
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] == DOTS], 'no waiting pill: no dot timer')


def pill_tests(ctx):
    """The cache pill: its widgets in the asset, the bar fill, the x (stops Home's pass, suppresses it until Rebuild Covers), the worker's niceness."""
    expect = ctx.expect
    import os, awtk_ui
    O_ = O
    ui = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_menu.bin'), 'rb').read())
    p = ui.find('pod_cache_pill')
    expect(p is not None and (p.x, p.y, p.w, p.h) == (12, 10, 296, 40) and p.get('visible') == 'false' and p.get('sensitive') == 'false' and ui.find('pod_cover_prog') is not None
           and [c.name for c in p.children] == ['pod_cover_prog', 'pod_cache_track', 'pod_cache_fill', 'pod_cache_x'], 'the pill is a hidden, insensitive 296 x 40 capsule at (12, 10) with the label, the track, the fill and the x')
    expect(all(p.get(f'style:{s}:bg_color') == '#1C1C1C' and p.get(f'style:{s}:round_radius') == '20' for s in ('normal', 'pressed', 'disable')), 'fill #1C1C1C, fully rounded')
    lab, tr, fl, x = p.children
    expect(lab.get('style:normal:font_size') == '15' and lab.get('style:normal:text_color') == '#AAAAAA' and tr.get('style:normal:bg_color') == '#FFFFFF33' and fl.get('style:normal:bg_color') == '#EBEBEB'
           and (tr.w, tr.h, fl.h, fl.x, fl.y) == (O_['HC_BW'], 4, 4, tr.x, tr.y) and x.type == 'button' and x.get('style:normal:icon') == 'pod_cache_x' and x.get('style:pressed:icon') == 'pod_cache_x_down'
           and x.x + x.w == p.w and tr.x + tr.w <= x.x, '15 px #AAAAAA text, a 4 px bar (track #FFFFFF33, fill #EBEBEB), the x button at the right end clear of the bar')
    for n in ('pod_cache_x', 'pod_cache_x_down'):
        expect(os.path.isfile(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx', n + '.png')), f'{n}.png is in the tree')

    # the fill follows done/total (at least 4 px), the pill stays until the end
    m = home_machine(6, missing={2, 4}); new = scan(m)
    fill, x = m.widgets['pod_cache_fill'], m.widgets['pod_cache_x']
    resizes = lambda calls: [c[2:] for c in calls if c[0] == 'widget_resize' and c[1] == fill]
    expect(resizes(new) == [(4, 4)], f'0/2: the fill is 4 px ({resizes(new)})')
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    expect(resizes(fired(m, 'hc_on_poll')) == [(O_['HC_BW'] // 2, 4)], '1/2: half of the track')
    expect(m.bound.get((x, O['EVT_CLICK'])) is not None, 'the x is bound to a click')

    # the x: Home's pass stops (the worker is cancelled, not joined), the pill and the poll go, nothing starts again this boot
    new = hook(m, 'hc_on_stop')
    s = build_state(m)
    expect(shown_calls(m, new)[-2:] == [('widget_set_visible', 0), ('widget_set_sensitive', 0)] and s['orphan'] == 1 and s['cancelled'] == 1 and count_of(m, 'pthread_join') == 0 and ('timer_remove', 0x777) in new,
           f'x: pill hidden, worker cancelled without a join, poll removed ({s})')
    expect(('widget_move', lv(m), 0, HOME_PAD) in new, 'the list is back')
    m.call(PSYMS['cc_worker'], count=5000000)   # the orphan exits
    expect(not [c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add'], 'the next foreground arms nothing')
    expect(not [c for c in fired(m, 'hc_on_start', 4000000) if c[0] in ('timer_add', 'pthread_create', 'access')], 'a start that is still due does nothing')
    # a Home rebuilt later (the menu destroyed and opened again) builds nothing either
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    expect(not adds(m.calls), 'a new Home window arms nothing after the x')
    # Rebuild Covers (explicit) clears it
    m.call(PSYMS['homecover_rebuild_asked'])
    m.fs[REQ] = b'1\n'
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    new = scan(m)
    expect(build_state(m)['running'] == 1 and build_state(m)['mode'] == 1 and pill_up(m), 'after Rebuild Covers the pass runs again (CC_REBUILD) and the pill shows')
    # a window that is not ours is ignored; a press before the start stops it from starting
    m = home_machine(6, missing={2}); hook(m, 'hc_on_stop', win=0x1234)
    scan(m)
    expect(build_state(m)['running'] == 1, 'a click bound to another window changes nothing')
    m = home_machine(6, missing={2}); hook(m, 'hc_on_stop')
    expect(not [c for c in fired(m, 'hc_on_start', 4000000) if c[0] in ('pthread_create', 'access')], 'x before the start: it does not start')
    # the x also ends the durations pass
    m = home_machine(0); m.fs['/mnt/mmc/.m1plus/durations'] = b''
    hook(m, 'hc_on_stop')
    expect(not [c for c in fired(m, 'hc_on_start', 4000000) if c[0] in ('pthread_create', 'cc_build_open')], 'no pass of either kind after the x')

    # the worker lowers its own priority: setpriority(PRIO_PROCESS, 0, 10), once, before the first job
    m = home_machine(6, missing={2, 4}); scan(m)
    m.sys = []
    m.call(PSYMS['cc_worker'], count=5000000)
    expect(m.sys == [(4097, 0, 0, 10)], f'the worker calls setpriority(0, 0, 10) first ({m.sys})')


def check_tests(ctx):
    """The cheap check (the stamp and the database file's state): the waiting pill at once when work is expected, nothing at all when not; the stamp written at the end of a pass."""
    expect = ctx.expect
    START = PSYMS['hc_on_start']
    WAIT, WAIT_R = 'Checking library.', 'Rebuilding covers.'   # (the first dot phase)

    def reads_nothing(calls):
        return not [c for c in calls if c[0] in ('loadLocalClassList', 'timer_add', 'pthread_create') or (c[0] == 'access' and '.m1plus/covers' in str(c[1]))]

    # 1. No stamp: the waiting pill shows at once (text, no count, empty bar), the list makes room; the scan starts only at HC_START_MS.
    m = home_machine(6, missing={2}, stamp=None)
    expect(pill_up(m) and texts(m, waiting=True) == [WAIT] and ('widget_move', lv(m), 0, HOME_PAD + HC_H) in m.calls, 'no stamp: the pill is up at once, "Checking library…", the list moved down')
    expect(('widget_set_visible', m.widgets['pod_cache_fill'], 0) in m.calls and adds(m.calls) == [('timer_add', START, START_MS)], 'the bar is empty (the fill hidden) and the start is still 5 s out')
    expect(not [c for c in m.calls if c[0] in ('loadLocalClassList', 'pthread_create') or (c[0] == 'access' and '.m1plus/covers' in str(c[1]))], 'nothing is queried, scanned or started yet')
    expect(not any(c[0] == 'sync_icon' for c in m.calls), 'the sync icon is the worker\'s: not touched by the waiting state')
    new = scan(m)
    expect(texts(m, new) == ['Preparing covers 0/1'] and pill_up(m) and ('widget_set_visible', m.widgets['pod_cache_fill'], 1) in new, 'at 5 s the scan and the worker run: the real count and the bar take over')
    # only the tracks line missing: the waiting text names the tracks
    m = home_machine(6, stamp=stamp_text(6, tracks=False))
    expect(pill_up(m) and texts(m, waiting=True) == [WAIT], 'only the tracks line missing: the same general "Checking library…"')
    # a pending Rebuild Covers is work too
    m = home_machine(6, rebuild=True, stamp=stamp_text(6))
    expect(pill_up(m) and texts(m, waiting=True) == [WAIT_R], 'a pending Rebuild Covers request: "Rebuilding covers…", the pill is up at once, whatever the stamp says')

    # 2. A scan that finds nothing missing: the stamp is written and the pill hidden.
    m = home_machine(6, stamp=stamp_text(6, covers=False))
    expect(pill_up(m), 'waiting')
    new = scan(m)
    expect(not pill_up(m) and not texts(m, new) and 'pthread_create' not in m.names() and m.fs[STAMP].decode() == stamp_text(6), f'nothing missing: the pill hides, the stamp holds both lines ({m.fs.get(STAMP)})')

    # 3. Stamp matches and the database is untouched since the library was read: no pill, no scan, no query. The first open after the boot reads the library once (no pill), then it is known.
    m = home_machine(6, missing={1}, stamp=stamp_text(6), songs=True)
    expect(not pill_up(m) and adds(m.calls) == [('timer_add', START, START_MS)], 'first open since the boot: no pill, the library is asked at 5 s')
    new = fired(m, 'hc_on_start', 400000000)
    expect(not pill_up(m) and not texts(m, new, waiting=True) and 'pthread_create' not in m.names() and not [c for c in new if c[0] == 'access' and '.m1plus/covers' in str(c[1])] and not adds(new),
           'the library matches the stamp: no pill, no album scanned (an album with no file is not looked at), no worker')
    new = hook(m, 'hc_on_background')
    new = hook(m, 'hc_on_foreground')
    expect(reads_nothing(new) and [c for c in new if c[0] == '__xstat'] and not pill_up(m), 'foreground, stamp current, database as it was: no pill, no timer, no query, no scan (only the database file\'s state is looked at)')

    # 4. The database changed (a play, an import): no pill, the start is armed silently; at 5 s the library is read; the same albums: nothing shown, no scan; a new album: the pill appears and the scan runs.
    m.db[DB] = [101, 0, 4096]
    new = hook(m, 'hc_on_foreground')
    expect(not pill_up(m) and not texts(m, new, waiting=True) and adds(new) == [('timer_add', START, START_MS)], 'database changed: no pill (a play changes it too), the start armed silently')
    new = fired(m, 'hc_on_start', 400000000)
    expect(not pill_up(m) and not texts(m, new, waiting=True) and not [c for c in new if c[0] == 'access' and '.m1plus/covers' in str(c[1])] and 'pthread_create' not in m.names(), 'the library is the same: the pill never showed, no album scan')
    new = hook(m, 'hc_on_background'); new = hook(m, 'hc_on_foreground')
    expect(not pill_up(m) and reads_nothing(new), 'and the new database state is remembered: the next foreground is quiet')
    m.db[DB] = [102, 0, 4096]
    m.showlist.append(m.record(album='Album 6', artist='Artist 6', path='/mnt/mmc/m/6/1.flac', rid=7)); m.present.add('/mnt/mmc/m/6/1.flac')
    new = hook(m, 'hc_on_background'); new = hook(m, 'hc_on_foreground')
    expect(not pill_up(m), 'database changed again: still silent')
    new = scan(m)
    expect(pill_up(m) and build_state(m)['total'] == 2 and texts(m, new) == ['Preparing covers 0/2'], 'a library with one more album: the scan queues it (and album 1, which has no file), the count takes over')
    m.db[DB] = [100, 0, 8192]
    expect('covers 6 ' in m.fs[STAMP].decode() and 'covers 7 ' not in m.fs[STAMP].decode(), 'the stamp is not written while the worker runs')
    finish_worker(m, [1, 6])
    new = fired(m, 'hc_on_poll', 40000000)
    new += fired(m, 'hc_on_dscan')   # (the songs: one CUE track, nothing to measure)
    expect(m.fs[STAMP].decode().startswith('covers 7 ') and 'tracks 7 ' in m.fs[STAMP].decode() and not pill_up(m), 'the pass done: the stamp holds the new count and hash for both parts, the pill hidden')

    # 5. The size of the -wal file counts too.
    m = home_machine(4, stamp=stamp_text(4)); m.db[DB + '-wal'] = [5, 0, 100]
    fired(m, 'hc_on_start', 400000000)
    hook(m, 'hc_on_background'); m.db[DB + '-wal'] = [5, 0, 200]
    expect(pill_up(m) is False and [c for c in hook(m, 'hc_on_foreground') if c[0] == 'timer_add'] and not pill_up(m), 'a changed WAL file is a change (the start is armed, silently)')

    # 6. The x in the waiting state cancels the pending timer, hides the pill and suppresses until Rebuild Covers; no stamp is written.
    m = home_machine(6, missing={2}, stamp=None)
    new = hook(m, 'hc_on_stop')
    expect(('timer_remove', 0x777) in new and not pill_up(m) and STAMP not in m.fs and ('widget_move', lv(m), 0, HOME_PAD) in new, 'x while waiting: the 5 s timer is removed, the pill hides, the list is back, no stamp')
    expect(not [c for c in hook(m, 'hc_on_foreground') if c[0] in ('timer_add', '__xstat')] and not pill_up(m), 'and the next foreground waits for nothing')
    # x during the build: no stamp either
    m = home_machine(6, missing={2}, stamp=None); scan(m)
    hook(m, 'hc_on_stop')
    expect(STAMP not in m.fs, 'x during the build writes no stamp (the pill comes back after a reboot)')

    # 7. A stalled set: the hung album has its .bad but the rest of the pass may not have been looked at: no covers line (the next foreground scans again).
    m = home_machine(3, stamp=None, missing={0}); scan(m)
    m.setword(PSYMS['cb'] + 4 * 13, key_of(0)); m.setword(PSYMS['cb'] + 4 * 15, 1)
    m.clock += 10000
    fired(m, 'hc_on_poll', 40000000)
    expect(m.call(PSYMS['cc_build_stalled']) == 1 and 'covers' not in m.fs.get(STAMP, b'').decode(), 'a stalled set: no covers line')

    # 7b. A truncated pass (more albums missing than CC_MAX_JOBS): no covers line, another pass follows at once, and the stamp comes when one finishes untruncated.
    cap = 4000   # CC_MAX_JOBS
    m = home_machine(cap + 2, stamp=None, missing=range(cap + 2))
    scan(m, 200)
    expect(build_state(m)['total'] == cap and m.call(PSYMS['cc_build_truncated']) == 1, 'more albums missing than one set holds: the set is full and truncated')
    for i in range(cap): m.present.add(art_file(key_of(i))); m.files[art_file(key_of(i))] = 4096
    m.setword(PSYMS['cb'] + 4 * 5, cap)
    new = fired(m, 'hc_on_poll', 400000000)
    expect('covers' not in m.fs.get(STAMP, b'').decode() and ('timer_add', START, 20) in new, 'a truncated pass is not stamped and chains a second pass')
    scan(m, 200)
    expect(build_state(m)['total'] == 2 and m.call(PSYMS['cc_build_truncated']) == 0, 'the second pass queues the two that did not fit')
    finish_worker(m, [cap, cap + 1])
    fired(m, 'hc_on_poll', 400000000)
    expect(m.fs[STAMP].decode().startswith(f'covers {cap + 2} '), 'the pass that ends untruncated writes the covers line')

    # 7c. A failed copy is not an empty library: no line, the pill hides. Stock answers empty to a failed query too, so empty is made safe instead (7e).
    m = home_machine(3, stamp=None); m.deque_fail = True
    scan(m)
    expect(STAMP not in m.fs and not pill_up(m) and 'pthread_create' not in m.names(), 'the album list could not be copied: nothing is stamped, the pill hides')
    m = home_machine(3, stamp=stamp_text(3, tracks=False)); scan(m)
    expect('tracks' not in m.fs[STAMP].decode() and not pill_up(m), 'no songs although there are albums: a failed read, no tracks line, the pill hides')
    m = home_machine(3, stamp=stamp_text(3, tracks=False), songs=True); m.deque_fail = False; scan(m); fired(m, 'hc_on_dscan')
    expect(m.fs[STAMP].decode() == stamp_text(3), 'songs read: the tracks line is written')

    # 7d. A chain of chunks resumes from a cursor: 4002 albums missing, the first 4000 tracks gone (the worker leaves no file): the second chunk queues the other two, then the line is written, no third pass.
    m = home_machine(cap + 2, missing=range(cap + 2))   # (the default stamp is of another library: it has a covers line)
    m.present -= {f'/mnt/mmc/m/{i}/1.flac' for i in range(cap)}
    scan(m, 200)
    expect(build_state(m)['total'] == cap and 'covers' not in m.fs[STAMP].decode(), 'the first chunk is full and drops the covers line of the stale stamp (a matching line would skip the chain)')
    m.setword(PSYMS['cb'] + 4 * 5, cap)   # the worker finished them all and made no file
    new = fired(m, 'hc_on_poll', 400000000)
    expect(('timer_add', START, 20) in new and 'covers' not in m.fs[STAMP].decode(), 'chunk one ended: no line, the next chunk is chained')
    scan(m, 200)
    expect(build_state(m)['total'] == 2 and [t for t, _ in build_jobs(m)] == [f'/mnt/mmc/m/{cap}/1.flac', f'/mnt/mmc/m/{cap + 1}/1.flac'] and m.call(PSYMS['cc_build_truncated']) == 0,
           'the second chunk resumes at the album that did not fit: the two left, not the 4000 gone ones again')
    finish_worker(m, [cap, cap + 1])
    new = fired(m, 'hc_on_poll', 400000000)
    expect(m.fs[STAMP].decode().startswith(f'covers {cap + 2} ') and ('timer_add', START, 20) not in new and build_state(m)['jobs'] == 0, 'the scan reached the end: the line is written, no third pass')

    # 7d2. Home leaves in the middle of the second chunk: the next foreground resumes at the chunk's start (not from 0, not skipped by the stamp); another album order starts again from 0.
    def chain_to_chunk_two():
        m = home_machine(cap + 2, missing=range(cap + 2))
        scan(m, 200)
        m.setword(PSYMS['cb'] + 4 * 5, cap)
        fired(m, 'hc_on_poll', 400000000)
        scan(m, 200)
        return m
    m = chain_to_chunk_two()
    expect(build_state(m)['total'] == 2, 'chunk two is running')
    hook(m, 'hc_on_background')
    m.call(PSYMS['cc_worker'], count=5000000)   # the orphan exits
    expect('covers' not in m.fs[STAMP].decode(), 'interrupted: still no covers line')
    new = hook(m, 'hc_on_foreground')
    expect(pill_up(m) and adds(new) == [('timer_add', START, RESUME_MS)], 'the next foreground waits with the pill, 1 s out (nothing says the covers are done)')
    scan(m, 200)
    expect(build_state(m)['total'] == 2 and [t for t, _ in build_jobs(m)][0] == f'/mnt/mmc/m/{cap}/1.flac', 'and the chunk is redone from its start')
    m = chain_to_chunk_two()
    hook(m, 'hc_on_background'); m.call(PSYMS['cc_worker'], count=5000000)
    m.fs[CFSORT_FILE] = b'1\n'   # Albums lists by artist now: Home's scan keeps the stored order, so the chain resumes
    hook(m, 'hc_on_foreground'); scan(m, 200)
    expect(build_state(m)['total'] == 2 and [t for t, _ in build_jobs(m)][0] == f'/mnt/mmc/m/{cap}/1.flac', 'Album Order changed: the scan order is not the display order, the chain resumes at its chunk')

    # 7d3. A reorder that keeps the album at the cursor: albums 0 and cap + 1 swap (a sort change can do that). The chain starts again from 0, so album cap + 1 is processed before any line is written.
    m = home_machine(cap + 2, missing=range(cap + 2))
    scan(m, 200)
    m.setword(PSYMS['cb'] + 4 * 5, cap)
    fired(m, 'hc_on_poll', 400000000)
    m.showlist[0], m.showlist[cap + 1] = m.showlist[cap + 1], m.showlist[0]
    scan(m, 200)
    expect(build_state(m)['total'] == cap and [t for t, _ in build_jobs(m)][0] == f'/mnt/mmc/m/{cap + 1}/1.flac' and 'covers' not in m.fs[STAMP].decode(),
           'two albums swapped around an unchanged cursor album: the chain starts again from the first, album 4001 is queued, no line yet')

    # 7d3b. The shelf's order cannot be made for the next chunk (no memory): not scanned in the stored order (the cursor fits only the shelf's), deferred; the next foreground resumes it.
    m = home_machine(cap + 2, missing=range(cap + 2))
    m.fs[RECENT] = pod_recent.dump([(pod_recent.identity(f'Album {cap + 1}'), key_of(cap + 1), 1, f'Album {cap + 1}', f'Artist {cap + 1}', '/x/a.flac')])
    scan(m, 200)
    expect([t for t, _ in build_jobs(m)][:2] == [f'/mnt/mmc/m/{cap + 1}/1.flac', '/mnt/mmc/m/0/1.flac'], 'the shelf album first, then the stored order')
    m.setword(PSYMS['cb'] + 4 * 5, cap)
    m.calloc_fail_size = 4 * (cap + 2)
    fired(m, 'hc_on_poll', 400000000); scan(m, 200)
    expect(build_state(m)['jobs'] == 0 and not pill_up(m) and 'covers' not in m.fs[STAMP].decode(), 'no memory for the shelf order: no chunk in another order, no line, the pill hides')
    m.calloc_fail_size = 0
    hook(m, 'hc_on_background'); hook(m, 'hc_on_foreground'); scan(m, 200)
    expect(sorted(t for t, _ in build_jobs(m)) == sorted([f'/mnt/mmc/m/{cap - 1}/1.flac', f'/mnt/mmc/m/{cap}/1.flac']), f'the next foreground resumes in the shelf order: albums {cap - 1} and {cap}, none skipped ({build_jobs(m)[:3]})')

    # 7d4. The UI thread's cost: the first hc_on_start callback of a chunk (album query + copy + signature + order + the first HC_BATCH step), a later scan step, and the silent probe (hc_expect, then the same query at HC_START_MS).
    for n in (1000, 4000):
        m = home_machine(n, start=False, missing=range(n)); m.fs[CFSORT_FILE] = b'1\n'   # Album Order by artist: Home does not sort
        m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
        m.count(); fired(m, 'hc_on_start', 900000000); first = m.icount
        fired(m, 'hc_on_start', 900000000); later = m.icount
        m = home_machine(n, stamp=stamp_text(n), start=False); m.count()
        m.call(PSYMS['homecover_start'], a0=m.window, count=2000000); armed = m.icount
        fired(m, 'hc_on_start', 900000000); probe = m.icount
        print(f'  Home, {n} albums: first chunk callback {first:,}, later scan step {later:,}, probe {probe:,} (arming it {armed:,}) payload instructions')
        expect(first < 400 * n and later < 50000 and probe < 400 * n, f'{n} albums: one UI-thread callback stays bounded ({first:,} / {later:,} / {probe:,})')
    # ... and a truncated chunk: the heaviest scan step (the last, which fingerprints the order) and the next chunk's first callback (query, copy, fingerprint check)
    n = cap + 2
    m = home_machine(n, missing=range(n)); m.fs[CFSORT_FILE] = b'1\n'; m.count()
    steps = []
    for _ in range(200):
        new = fired(m, 'hc_on_start', 900000000); steps.append(m.icount)
        if not [c for c in new if c[0] == 'timer_add' and c[1] == START]: break
    m.setword(PSYMS['cb'] + 4 * 5, cap)
    fired(m, 'hc_on_poll', 400000000)
    fired(m, 'hc_on_start', 900000000); resume = m.icount
    print(f'  Home, {n} albums truncated: last scan step {steps[-1]:,}, heaviest step {max(steps):,}, next chunk first callback {resume:,} payload instructions')
    expect(build_state(m)['total'] == 2 and max(steps) < 400 * n and resume < 400 * n, f'a truncated chunk and its resume stay bounded ({max(steps):,} / {resume:,})')

    # 7e. An empty album list may be a failed query (stock cannot tell): stamped as 0 albums (no real library matches it) and asked again, silently, at every foreground.
    m = home_machine(0, stamp=None); scan(m)
    expect(m.fs[STAMP].decode() == 'covers 0 00000000\ntracks 0 00000000\n' and not pill_up(m), 'an empty library is stamped 0/0 and the pill hides')
    for _ in range(2):
        hook(m, 'hc_on_background'); new = hook(m, 'hc_on_foreground')
        expect(not pill_up(m) and adds(new) == [('timer_add', START, START_MS)], 'the next foreground asks again, without the pill')
        new = fired(m, 'hc_on_start', 400000000)
        expect(not pill_up(m) and not texts(m, new, waiting=True) and 'pthread_create' not in m.names() and not adds(new), 'a still empty library: no pill, no scan, nothing more')
    m = home_machine(3, missing={0, 1, 2}, start=False)
    albums, m.showlist = m.showlist, []
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    scan(m)
    expect(m.fs[STAMP].decode().startswith('covers 0 ') and not pill_up(m), 'the album query failed (empty): stamped 0/0, no pill')
    m.showlist = albums
    hook(m, 'hc_on_background'); new = hook(m, 'hc_on_foreground')
    expect(not pill_up(m) and adds(new) == [('timer_add', START, START_MS)], 'the next foreground asks again silently')
    new = scan(m)
    expect(pill_up(m) and build_state(m)['total'] == 3 and texts(m, new) == ['Preparing covers 0/3'], 'the albums are there now: 0/0 matches no library, the pill shows and the covers are built')

    # 8. Background in the waiting state: the timer goes, the pill hides; the foreground shows it again.
    m = home_machine(6, stamp=None)
    new = hook(m, 'hc_on_background')
    expect(('timer_remove', 0x777) in new and not pill_up(m), 'background while waiting: timer removed, pill hidden')
    new = hook(m, 'hc_on_foreground')
    expect(pill_up(m) and adds(new) == [('timer_add', START, RESUME_MS)], 'foreground: waiting again, 1 s out')

    # 9. The held worker at 5 s: the pill hides (the next foreground offers again).
    m = home_machine(6, stamp=None)
    m.call(PSYMS['cc_build_open'], a0=6, a1=0, count=2000000)
    fired(m, 'hc_on_start', 4000000)
    expect(not pill_up(m), 'a held worker: the waiting pill hides')

    # 10. No card: nothing is expected.
    m = Machine(); m.card_mounted = False
    for w in ('home_window', 'pod_cache_pill', 'pod_cover_prog', 'pod_cache_fill', 'pod_cache_x', 'pod_listview'): m.widget(w)
    m.call(PSYMS['homecover_start'], a0=m.widgets['home_window'], count=2000000)
    expect(not [c for c in m.calls if c[0] in ('timer_add', 'widget_set_visible')], 'no card: no pill, no timer')

    # 11. Clear Cover Cache forgets the covers line, Clear Track Durations the tracks line; the pill is waiting at the next Home open.
    m = home_machine(3, stamp=stamp_text(3), start=False)
    m.call(PSYMS['homecover_stamp_drop'], a0=1, count=2000000)
    expect(m.fs[STAMP].decode() == stamp_text(3, covers=False), 'drop(1) keeps the tracks line only')
    m.call(PSYMS['homecover_stamp_drop'], a0=2, count=2000000)
    expect(STAMP not in m.fs, 'drop(2) leaves no line: the file goes')
    m = home_machine(2, stamp=stamp_text(2), start=False)
    m.fs['/mnt/mmc/.m1plus/covers'] = b''
    m.call(PSYMS['homecover_clear'], count=2000000)
    expect(m.fs[STAMP].decode() == stamp_text(2, covers=False), 'Clear Cover Cache drops the covers line')
    m = home_machine(2, stamp=stamp_text(2), start=False); m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect(m.fs[STAMP].decode() == stamp_text(2, tracks=False), 'Clear Track Durations drops the tracks line')


SECTIONS = [tests, dots_tests, pill_tests, rebuild_tests, check_tests, resume_tests, clear_tests, cache_tests, covlist_tests, files_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

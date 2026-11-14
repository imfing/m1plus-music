"""Podcast episode downloads (patch/pcnet.c pn_dl_*, patch/podcasts.c, docs/modules/podcasts.md "Downloads") against a scripted libcurl: the queue and its guards, the request's options, the
512 KB chunks (open, write, fsync, close), the .part file and the rename, a Range resume (206) and a server that answers 200, the stall limit, the retries after 10, 20 and 40 s, the failures that
end at once (404, a web page, a full card, the 32 MB margin), Cancel and the pause for a refresh, the refresh and the downloads never running together, the keep-awake call (only from the page's
timer, only while a download runs), the rows' state lines and their widths in the 13 languages, and malformed answers. The compiled payload runs under Unicorn; the card is a dict of paths."""
import os
import pod_show
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


PCN, PF = sibling('pcnet'), sibling('pcshows')
PCP = PCN.PCP
PN, RP, CA = PCN.PN, PCN.ROOT_DIR, PCN.CA
PN.update(CARDFULL=13, NOTAUDIO=14, QFULL=15)
ROW = PCP.ROW
NOW = PF.NOW
SHOW = f'{RP}/Show'
O_APPEND_FLAGS = 1 | 0x100 | 0x8      # O_WRONLY | O_CREAT | O_APPEND
O_TRUNC_FLAGS = 1 | 0x100 | 0x200     # O_WRONLY | O_CREAT | O_TRUNC
KB = 1024
MARGIN_MB, CHUNK = 32, 512 * KB
DL_STATE = dict(NONE=0, WAIT=1, ACTIVE=2, FAILED=3)

# the status record (patch/pcnet.c): the fields after `fail` (the tests of pcdialog.py know the ones before)
K = 20 + 12 * O['PC_MAX_SHOWS'] + 28
KIND, DBUSY, DWAIT, DKEY, DGOT, DTOTAL, DGEN, DSTEP, DSEQ, NFAIL = (K + 4 * i for i in range(10))
DROOT = K + 40
Q0, QSIZE = DROOT + 148, 268
FAILS = Q0 + 32 * QSIZE


QS = dict(FREE=0, WAIT=1, ACTIVE=2, STOPPING=3, DROPPING=4, PUBLISHED=5)   # a slot's state: the life of its download (patch/pcnet.c PN_Q_*)


def slot_states(m): return [m.word(pn_at(Q0 + i * QSIZE)) for i in range(32)]


def flagged(m):
    """The states of the downloads the page has paused (STOPPING) or dropped (DROPPING) and the thread has not let go yet."""
    return [s for s in slot_states(m) if s in (QS['STOPPING'], QS['DROPPING'])]


def run_state(m, key):
    """The state of the taken-up download of key (ACTIVE and later), 0 when none."""
    return next((s for i, s in enumerate(slot_states(m)) if s >= QS['ACTIVE'] and m.word(pn_at(Q0 + i * QSIZE + 8)) == key), 0)


def stop(m, key, drop=False):
    """What pn_dl_cancel (pn_dl_drop) does to the running download of key."""
    for i, s in enumerate(slot_states(m)):
        if s in (QS['ACTIVE'], QS['STOPPING']) and m.word(pn_at(Q0 + i * QSIZE + 8)) == key: m.setword(pn_at(Q0 + i * QSIZE), QS['DROPPING' if drop else 'STOPPING'])


def unstop(m):
    """The pause is taken back (a test goes on with the download still running)."""
    for i, s in enumerate(slot_states(m)):
        if s == QS['STOPPING']: m.setword(pn_at(Q0 + i * QSIZE), QS['ACTIVE'])


def pn_at(off): return PSYMS['pn'] + off


def key_of(folder, f): return PCN.pc_hash(f'{folder}/{f}')


def eps_text(entries):
    return (PCP.EPS_HEAD + ''.join(f'g={g}\tp={NOW - 100 * i}\td=600\tl={l}\tf={f}\tt={f}\tu={u}\n' for i, (g, f, l, u) in enumerate(entries))).encode()


URL_A = 'https://cdn.example/a.mp3?sig=abc&exp=99'
DATA = body(1300000)


def entries(n=3, length=len(DATA)):
    return [(f'g{i}', f'{"abcdefgh"[i]}.mp3', length, URL_A.replace('/a.', f'/{"abcdefgh"[i]}.')) for i in range(n)]


def machine(site=None, ents=None, **kw):
    m = PCN.machine(site=site, **kw)
    PCN.sub(m, 'Show', 'https://feeds.example/show', title='Show', checked=1)
    m.put(f'{SHOW}/.episodes', eps_text(ents if ents is not None else entries()))
    return m


def lanes():
    """A machine for both lanes: Show's episodes download from the episode server, the feed of a second show (Other) answers a refresh."""
    feed, dl = PCN.feed_bytes('wsj-3items.xml'), server(DATA)
    m = machine(site=lambda url, o: {'body': feed} if url == 'https://feeds.example/other' else dl(url, o))
    PCN.sub(m, 'Other', 'https://feeds.example/other', title='Other')
    return m


def server(data, log=None, ctype='audio/mpeg', chunk=65536, honour=True):
    """A server for one file: Range answered with 206 (honour) or ignored with 200; log gets (url, start, options)."""
    def site(url, o):
        rng = o.get(10007)
        start = int(rng.rstrip('-')) if rng else 0
        if log is not None: log.append((url, start, dict(o)))
        r = dict(chunk=chunk, ctype=ctype)
        if start and honour: return dict(r, code=206, body=data[start:], length=len(data) - start)
        return dict(r, code=200, body=data, length=len(data))
    return site


def add(m, f='a.mp3', folder='Show'):
    """pn_dl_add on the UI thread: (result, the thread it started)."""
    m.thread = None
    r = m.call(PSYMS['pn_dl_add'], a0=m.cstr(RP), a1=m.cstr(folder), a2=m.cstr(f), count=1 << 40)
    return r, m.thread


def state(m, f='a.mp3', folder='Show'):
    code, got, total = m.alloc(4), m.alloc(4), m.alloc(4)
    st = m.call(PSYMS['pn_dl_state'], a0=key_of(folder, f), a1=code, a2=got, a3=total, count=2000000)
    return st, m.word(code), m.word(got), m.word(total)


def fn(m, name, **kw): return m.call(PSYMS[name], count=2000000, **kw)


def part_of(m, f='a.mp3'): return m.fs.get(f'{SHOW}/{f}.part')


def sleeps(calls): return [c[1] for c in calls if c[0] == 'sleep']


def opens(calls, path=None): return [c for c in calls if c[0] == 'open' and (path is None or c[1] == path)]


def left_over(m):
    return sorted(p.rsplit('/', 1)[1] for p in m.fs if p.startswith(SHOW + '/') and not p.endswith(('.episodes', '.show')))


def poke_slot(m, i, folder, f, st, seq=1):
    a = pn_at(Q0 + i * QSIZE)
    m.setword(a, st); m.setword(a + 4, seq); m.setword(a + 8, key_of(folder, f))
    m.u.mem_write(a + 12, folder.encode() + b'\0'); m.u.mem_write(a + 140, f.encode() + b'\0')


FAIL_SIZE = 4 + 4 + 2 * O['PC_FILE']   # a failure record: key, code, dir, file


def poke_fail(m, i, folder, f, code):
    a = pn_at(FAILS + FAIL_SIZE * i)
    m.setword(a, key_of(folder, f)); m.setword(a + 4, code)
    m.u.mem_write(a + 8, folder.encode() + b'\0'); m.u.mem_write(a + 8 + O['PC_FILE'], f.encode() + b'\0')


def queue_tests(ctx):
    """The queue: guards, duplicates, the path limit, the cap; one worker thread, never beside a refresh."""
    expect = ctx.expect
    m = machine(site=server(DATA))
    for msg, setup, want in (('no card', lambda: setattr(m, 'card_mounted', False), 'STORAGE'), ('no Wi-Fi', lambda: setattr(m, 'wifi', -1), 'NOWIFI'),
                             ('a clock that was never set', lambda: setattr(m, 'wall', 1700000000), 'NOCLOCK'), ('no CA bundle', lambda: m.present.discard(CA), 'NOCERT')):
        m.card_mounted, m.wifi, m.wall = True, 4, 1800000000; m.present.add(CA)
        setup()
        r, th = add(m)
        expect(r == PN[want] and th is None and fn(m, 'pn_dl_count') == 0 and state(m)[0] == DL_STATE['NONE'], f'{msg}: pn_dl_add says {want}, nothing is queued, no thread')
    m.card_mounted, m.wifi, m.wall = True, 4, 1800000000; m.present.add(CA)
    r, th = add(m)
    names = [c[0] for c in m.calls]
    expect(r == 0 and th and th[0] == PSYMS['pn_dmain'] and names.count('pthread_create') == 1 and names.count('pthread_detach') == 1 and ('curl_global_init', 3) in m.calls,
           'a download: curl initialised on the UI thread, one detached worker')
    expect(fn(m, 'pn_dl_count') == 1 and fn(m, 'pn_dl_waiting') == 1 and fn(m, 'pn_dl_running') == 1 and fn(m, 'pn_busy') == 0 and state(m)[0] == DL_STATE['WAIT'],
           'queued and waiting; the thread is a download thread (pn_busy is the refresh\'s)')
    r2, th2 = add(m)
    expect(r2 == 0 and th2 is None and fn(m, 'pn_dl_count') == 1, 'the same episode again: left as it is')
    r3, th3 = add(m, 'b.mp3')
    expect(r3 == 0 and th3 is None and fn(m, 'pn_dl_count') == 2, 'another one while the thread runs: queued, no second thread')
    calls = work(m, th)
    expect(fn(m, 'pn_dl_count') == 0 and fn(m, 'pn_dl_running') == 0 and f'{SHOW}/a.mp3' in m.fs and f'{SHOW}/b.mp3' in m.fs, 'the thread drains the queue (two episodes) and ends')
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(reqs == [URL_A, URL_A.replace('/a.', '/b.')], f'in the order they were asked, the stored enclosure urls ({reqs})')
    # long paths, the cap
    m = machine(site=server(DATA))
    long_name = 'x' * 100 + '.mp3'
    m.put(f'{SHOW}/.episodes', eps_text([('g', long_name, 5, URL_A)]))
    r, th = add(m, long_name)
    expect(r == 0, 'a path of 17 + 5 + 104 + 5 bytes is within 240')
    r, th = add(m, 'y' * 230 + '.mp3')
    expect(r == PN['STORAGE'] and th is None, 'a path over 240 bytes with its .part: PN_STORAGE, not queued')
    m = machine(site=server(DATA), ents=[(f'g{i}', f'ep{i}.mp3', 5, URL_A) for i in range(34)])
    for i in range(32): r, th = add(m, f'ep{i}.mp3')
    expect(fn(m, 'pn_dl_count') == 32, 'the queue holds 32')
    r, th = add(m, 'ep32.mp3')
    expect(r == PN['QFULL'] and fn(m, 'pn_dl_count') == 32, 'the 33rd: PN_QFULL')
    r, th = add(m, 'ep5.mp3')
    expect(r == 0, 'one that is queued already is no new entry even when the queue is full')
    # two lanes: a job (a refresh) and the download thread run side by side
    m = lanes()
    r, th = add(m); add(m, 'b.mp3')
    expect(r == 0 and fn(m, 'pn_dl_running') == 1 and fn(m, 'pn_busy') == 0, 'a download thread is pending (pn_busy is the jobs\' lane only)')
    r, thr = PCN.start(m, ['Other'])
    expect(r == 0 and thr and thr[0] == PSYMS['pn_main'] and fn(m, 'pn_busy') == 1 and m.word(pn_at(KIND)) == 1 and fn(m, 'pn_dl_running') == 1 and fn(m, 'pn_dl_count') == 2 and fn(m, 'pn_dl_waiting') == 2,
           'a refresh while the download thread runs starts at once (0, not PN_BUSY): its own thread is created, the download thread still runs, the queue is untouched')
    r2, thr2 = PCN.start(m, ['Other'])
    expect(r2 == PN['BUSY'] and thr2 is None and fn(m, 'pn_dl_running') == 1, 'a second job is still PN_BUSY (one job at a time)')
    calls = work(m, th)
    expect(fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_busy') == 1 and m.word(pn_at(KIND)) == 1 and m.word(pn_at(0)) == 1 and fn(m, 'pn_dl_count') == 0 and m.fs.get(f'{SHOW}/a.mp3') == DATA and m.fs.get(f'{SHOW}/b.mp3') == DATA,
           'the download thread ends first: the job is still busy with its own kind, the episodes are files')
    PCN.work(m, thr)
    expect(fn(m, 'pn_busy') == 0 and m.word(pn_at(KIND)) == 0 and PCN.status(m, 'https://feeds.example/other') is not None and PCN.status(m, 'https://feeds.example/other')[0] == 0 and fn(m, 'pn_dl_running') == 0,
           'then the refresh thread runs to its end and completes normally')
    # the reverse order: the job ends first, the download thread goes on and completes
    m = lanes()
    r, thr = PCN.start(m, ['Other'])
    r, th = add(m); add(m, 'b.mp3')
    expect(r == 0 and th and th[0] == PSYMS['pn_dmain'] and fn(m, 'pn_busy') == 1 and fn(m, 'pn_dl_running') == 1, 'a download asked while a refresh runs starts its own thread in the same call (no waiting for the refresh)')
    PCN.work(m, thr)
    expect(fn(m, 'pn_busy') == 0 and fn(m, 'pn_dl_running') == 1 and fn(m, 'pn_dl_count') == 2 and PCN.status(m, 'https://feeds.example/other')[0] == 0, 'the job ends first: pn_dl_running is still 1, the queue is untouched')
    work(m, th)
    expect(fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_dl_count') == 0 and m.fs.get(f'{SHOW}/a.mp3') == DATA and m.fs.get(f'{SHOW}/b.mp3') == DATA, 'then the download thread completes both episodes')
    # pn_dl_start: nothing when the thread is there, one thread when it is not
    m = machine(site=server(DATA))
    r, th = add(m); add(m, 'b.mp3')
    m.thread = None
    expect(fn(m, 'pn_dl_start') == 0 and m.thread is None and 'pthread_create' not in [c[0] for c in m.calls[-5:]], 'pn_dl_start with the download thread running (dbusy 1) creates no thread')
    m.setword(pn_at(DBUSY), 0)   # the thread could not be made (or has ended)
    expect(fn(m, 'pn_dl_start') == 0 and m.thread and m.thread[0] == PSYMS['pn_dmain'] and fn(m, 'pn_dl_running') == 1, 'with dbusy 0 and downloads waiting pn_dl_start creates the thread and takes dbusy')
    m.thread = None
    expect(fn(m, 'pn_dl_start') == 0 and m.thread is None, 'a second pn_dl_start finds the thread there: exactly one thread')
    work(m, th)
    expect(fn(m, 'pn_dl_count') == 0 and fn(m, 'pn_dl_running') == 0 and m.fs.get(f'{SHOW}/b.mp3') == DATA, 'the one thread drains the queue')
    # pn_cancel is scoped: a page stops only the kinds of job it starts (PN_K_*, patch/pcnet.h)
    K_REFRESH, K_PODCASTS, K_ART, K_UPDATE, K_EQ = 1 << 1, 1 << 3 | 1 << 4 | 1 << 8 | 1 << 10, 3 << 5, 1 << 7, 1 << 9
    m = machine(site=server(DATA))
    m.setword(pn_at(0), 1); m.setword(pn_at(KIND), 1)   # a refresh holds the job slot
    for mask, who in ((K_PODCASTS, 'a search or chart leaving'), (K_ART, 'Find Cover & Lyrics closing'), (K_UPDATE, 'Software Update closing'), (K_EQ, 'AutoEq closing')):
        fn(m, 'pn_cancel', a0=mask)
        expect(fn(m, 'pn_cancelling') == 0, f'{who} does not stop a running refresh')
    fn(m, 'pn_cancel', a0=K_REFRESH)
    expect(fn(m, 'pn_cancelling') == 1, 'the refresh dialog\'s Cancel does')
    m = machine(site=server(DATA))
    m.setword(pn_at(0), 1); m.setword(pn_at(KIND), 10)   # the archive fetch of a show
    fn(m, 'pn_cancel', a0=K_ART | K_UPDATE | K_EQ | K_REFRESH)
    m.setword(pn_at(KIND), 1)
    expect(fn(m, 'pn_cancelling') == 0, 'another page\'s Cancel leaves a Podcasts job (the archive fetch) alone')
    m.setword(pn_at(KIND), 10); fn(m, 'pn_cancel', a0=K_PODCASTS); m.setword(pn_at(KIND), 1)
    expect(fn(m, 'pn_cancelling') == 1, 'the Podcasts page\'s own Cancel stops it')
    m = machine(site=server(DATA))
    fn(m, 'pn_cancel', a0=0xffffffff)
    m.setword(pn_at(0), 1); m.setword(pn_at(KIND), 1)
    expect(fn(m, 'pn_cancelling') == 0, 'a Cancel with no job running leaves no flag behind for the next job')
    # the guards fail later: every waiting download fails with their words
    m = machine(site=server(DATA))
    r, th = add(m); r, th2 = add(m, 'b.mp3')
    m.wifi = -1
    expect(fn(m, 'pn_dl_start') == 0 and fn(m, 'pn_dl_running') == 1, 'a running thread: pn_dl_start is a no-op')
    work(m, th)
    m = machine(site=server(DATA))
    add(m); add(m, 'b.mp3')
    m.setword(pn_at(DBUSY), 0)   # the thread is gone with the queue left waiting
    m.wifi = -1
    expect(fn(m, 'pn_dl_start') == PN['NOWIFI'] and fn(m, 'pn_dl_count') == 0 and state(m)[0:2] == (DL_STATE['FAILED'], PN['NOWIFI']) and state(m, 'b.mp3')[0:2] == (DL_STATE['FAILED'], PN['NOWIFI']),
           'a start that finds no Wi-Fi: the waiting downloads fail at once with "No Wi-Fi" (they must not keep the device awake for nothing)')
    m.wifi = 4
    m.setword(pn_at(DBUSY), 0)
    r, th = add(m)
    expect(r == 0 and state(m)[0] == DL_STATE['WAIT'], 'asking again clears the failure and queues it')


def transfer_tests(ctx):
    """One download, whole: the request, the chunks, the file."""
    expect = ctx.expect
    log = []
    m = machine(site=server(DATA, log))
    r, th = add(m)
    gen0 = fn(m, 'pn_gen')
    progress = []
    base_site = m.curl_site

    def site(url, o):
        out = base_site(url, o)
        out['xfer'] = lambda u, sent, total: progress.append((m.word(pn_at(DGOT)), m.word(pn_at(DTOTAL)), m.word(pn_at(DKEY)), m.word(pn_at(DBUSY)), m.word(pn_at(0)), m.word(pn_at(KIND))))
        return out
    m.curl_site = site
    calls = work(m, th)
    o = log[0][2]
    expect(log[0][0] == URL_A and log[0][1] == 0, 'the url is the one stored in .episodes, with its query, as the feed gave it')
    expect(o[10065] == CA and o[52] == 1 and o[68] == 16 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[99] == 1 and o[78] == 20 and 64 not in o and 81 not in o and 10007 not in o,
           'the request: the firmware CA bundle, redirects (8) limited to http(s), fail on HTTP errors, no signals, verification never switched off, no Range for a fresh file')
    expect(o[19] == 1 and o[20] == 60 and o[13] == 0 and o[10102] == 'identity', 'a stall is 1 byte a second for 60 s; no limit on the whole transfer; no content encoding')
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None and left_over(m) == ['a.mp3'], 'the finished file is the whole body, renamed into the show folder, no .part left')
    sync = [c for c in calls if c[0] == 'fsync' and c[1] == f'{SHOW}/a.mp3.part']
    writes = [c for c in calls if c[0] == 'write' and c[1] == f'{SHOW}/a.mp3.part']
    opn = opens(calls, f'{SHOW}/a.mp3.part')
    expect(len(sync) == 3 and [len(w[2]) for w in writes] == [CHUNK, CHUNK, len(DATA) - 2 * CHUNK] and len(opn) == 4 and all(c[2] == O_APPEND_FLAGS for c in opn[1:]),
           f'three chunks (512 KB, 512 KB, the rest), each opened for append, written, fsynced and closed ({[len(w[2]) for w in writes]}, {len(sync)} fsyncs)')
    names = [c[0] for c in calls if c[1:2] == (f'{SHOW}/a.mp3.part',) or c[0] == 'rename']
    expect(names[-3:] == ['fsync', 'close', 'rename'] and ('rename', f'{SHOW}/a.mp3.part', f'{SHOW}/a.mp3') in calls, 'the last chunk is fsynced and closed, then the file is renamed')
    order = [c[0] for c in calls if c[0] in ('open', 'write', 'fsync', 'close') and c[1] == f'{SHOW}/a.mp3.part']
    expect(order == ['open', 'close'] + ['open', 'write', 'fsync', 'close'] * 3, 'the size of the .part is asked first (open, close), then open, write, fsync, close for every chunk: the card is held busy for a moment only')
    expect(not any(c[0] in ('utime', 'utimes') for c in calls), 'no mtime call (demo imports neither utime nor utimes)')
    got = [p[0] for p in progress]
    expect(got == sorted(got) and got[-1] == len(DATA) and all(p[1] == len(DATA) for p in progress[1:]) and all(p[2] == key_of('Show', 'a.mp3') and p[3] == 1 and p[4] == 0 and p[5] == 0 for p in progress),
           'progress: the bytes got only grow to the whole, the total is the server\'s length, the current key and the download flag are set meanwhile, the job lane (busy, kind) stays untouched')
    expect(fn(m, 'pn_dl_count') == 0 and fn(m, 'pn_dl_running') == 0 and m.word(pn_at(DBUSY)) == 0 and m.word(pn_at(KIND)) == 0 and m.word(pn_at(0)) == 0 and fn(m, 'pn_gen') > gen0 and fn(m, 'pn_dl_gen') > 0
           and m.word(pn_at(DKEY)) == 0, 'at the end: nothing queued or running, the generation and the progress generation moved')
    expect(state(m)[0] == DL_STATE['NONE'], 'no state for an episode that is a file now (the model says local)')
    expect(not [c for c in calls if c[0] == 'get_wifisignal' or c[0] == 'reset_poweroptions_timer' or c[0].startswith('widget') or c[0] == 'toast' or c[0] == 'timer_add'],
           'the worker never calls a stock function (not get_wifisignal, not reset_poweroptions_timer, no widget, no timer)')
    expect(len(m.curl) == 0 and ('curl_global_init', 3) not in calls, 'every easy handle cleaned up')
    # a small file below one chunk; unknown length
    small = body(5000)
    m = machine(site=server(small), ents=[('g', 'a.mp3', 0, URL_A)])
    r, th = add(m); calls = work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == small and [c[1] for c in calls if c[0] == 'fsync'] == [f'{SHOW}/a.mp3.part', SHOW], 'a file under one chunk: one chunk write, one fsync; then the folder is synced after the rename (patch/net.c net_publish)')
    # whole-file chunking at the exact multiple
    exact = body(2 * CHUNK)
    m = machine(site=server(exact, chunk=CHUNK), ents=[('g', 'a.mp3', len(exact), URL_A)])
    r, th = add(m); calls = work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == exact and len([c for c in calls if c == ('fsync', f'{SHOW}/a.mp3.part')]) == 2, 'exactly two chunks: two fsyncs, no empty third write')
    # the file is already there: nothing is fetched, a leftover .part goes
    log = []
    m = machine(site=server(DATA, log)); m.put(f'{SHOW}/a.mp3', b'whole'); m.put(f'{SHOW}/a.mp3.part', b'junk')
    r, th = add(m); work(m, th)
    expect(not log and m.fs[f'{SHOW}/a.mp3'] == b'whole' and part_of(m) is None, 'an episode that is on the card already is not fetched again; its leftover .part is removed')


def resume_tests(ctx):
    """Range, 206 and 200; the stall and the retries; the failures that end at once."""
    expect = ctx.expect
    log = []
    m = machine(site=server(DATA, log))
    m.put(f'{SHOW}/a.mp3.part', DATA[:123456])
    expect(state(m)[0] == 0, 'a .part from an earlier run (Paused on the page) is no state of the queue')
    r, th = add(m); calls = work(m, th)
    expect(log[0][1] == 123456 and log[0][2][10007] == '123456-' and m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None,
           'a .part of 123456 bytes: the request has Range "123456-", the 206 answer is appended, the file is whole')
    expect(all(c[2] == O_APPEND_FLAGS for c in opens(calls, f'{SHOW}/a.mp3.part')[1:]) and not [c for c in opens(calls) if c[2] == O_TRUNC_FLAGS], 'the resume appends (O_APPEND); the file is not truncated')
    log = []
    m = machine(site=server(DATA, log, honour=False)); m.put(f'{SHOW}/a.mp3.part', DATA[:5000])
    r, th = add(m); calls = work(m, th)
    expect(log[0][1] == 5000 and m.fs.get(f'{SHOW}/a.mp3') == DATA and [c for c in opens(calls, f'{SHOW}/a.mp3.part') if c[2] == O_TRUNC_FLAGS],
           'a server that answers 200 to the Range: the file starts again (truncated), the result is the body once, not the .part plus the body')
    # a break in the middle (a network error after some bytes): the bytes are on the card, the retry resumes from them after 10 s
    log = []
    script = [dict(rc=56, code=200, partial=True, body=DATA[:700000], ctype='audio/mpeg', length=len(DATA)), None]
    base = server(DATA, log)
    m = machine(site=lambda url, o: script.pop(0) or base(url, o) if script else base(url, o))
    r, th = add(m); calls = work(m, th)
    expect([x[1] for x in log] == [700000] and m.fs.get(f'{SHOW}/a.mp3') == DATA and sleeps(calls) == [1] * 10,
           f'a break after 700000 bytes: waits 10 s (ten one-second sleeps, so Cancel is heard), then resumes at 700000 and finishes ({[x[1] for x in log]}, {len(sleeps(calls))} sleeps)')
    # the retry schedule: 10, 20, 40 s, then it fails
    reqs = []
    m = machine(site=lambda url, o: (reqs.append(o.get(10007)), dict(rc=56, code=0))[1])
    r, th = add(m); calls = work(m, th)
    expect(len(reqs) == 4 and len(sleeps(calls)) == 70 and set(sleeps(calls)) == {1} and state(m)[0:2] == (DL_STATE['FAILED'], PN['NET']) and part_of(m) is None and m.wall == 1800000070,
           f'a connection that never comes: four attempts, 10 + 20 + 40 seconds of waiting, then "Can\'t connect"; no empty .part ({len(reqs)}, {len(sleeps(calls))})')
    reqs = []
    m = machine(site=lambda url, o: (reqs.append(o.get(10007)), dict(rc=28, code=0))[1])
    r, th = add(m); calls = work(m, th)
    expect(len(reqs) == 4 and state(m)[0:2] == (DL_STATE['FAILED'], PN['NET']), 'a stall (rc 28, the low-speed time-out) is a network failure: retried, then failed')
    # an attempt that got bytes starts the count again
    reqs, n = [], [0]

    def flaky(url, o):
        start = int(o[10007].rstrip('-')) if o.get(10007) else 0
        reqs.append(start)
        n[0] += 1
        code = 206 if start else 200
        if n[0] <= 6: return dict(rc=56, code=code, partial=True, body=DATA[start:start + 1000], ctype='audio/mpeg', length=len(DATA) - start)
        return dict(code=code, body=DATA[start:], ctype='audio/mpeg', length=len(DATA) - start)
    m = machine(site=flaky)
    r, th = add(m); calls = work(m, th)
    expect(reqs == [0, 1000, 2000, 3000, 4000, 5000, 6000] and m.fs.get(f'{SHOW}/a.mp3') == DATA and set(sleeps(calls)) == {1} and len(sleeps(calls)) == 6 * 10,
           f'six breaks that each got bytes: the waiting starts at 10 s every time, and the file is finished ({reqs}, {len(sleeps(calls))} s)')
    # 5xx is retried; other HTTP errors are not
    for code, want, tries in ((404, 'GONE', 1), (410, 'GONE', 1), (403, 'HTTP', 1), (401, 'HTTP', 1), (500, 'HTTP', 4), (503, 'HTTP', 4), (429, 'HTTP', 4), (408, 'HTTP', 4)):
        reqs = []
        m = machine(site=lambda url, o, code=code: (reqs.append(1), dict(rc=22, code=code))[1])
        r, th = add(m); calls = work(m, th)
        expect(len(reqs) == tries and state(m)[0:2] == (DL_STATE['FAILED'], PN[want]) and part_of(m) is None and not sleeps(calls) == (tries > 1),
               f'HTTP {code}: {tries} request(s), then {want}')
    reqs = []
    m = machine(site=lambda url, o: (reqs.append(1), dict(rc=22, code=404))[1])
    r, th = add(m); calls = work(m, th)
    expect(len(reqs) == 1 and not sleeps(calls) and m.wall == 1800000000, 'a 404 fails at once: one request, no waiting')
    for rc, want in ((60, 'CERT'), (35, 'CERT'), (51, 'CERT'), (77, 'NOCERT')):
        reqs = []
        m = machine(site=lambda url, o, rc=rc: (reqs.append(1), dict(rc=rc, code=0))[1])
        r, th = add(m); calls = work(m, th)
        expect(len(reqs) == 1 and not sleeps(calls) and state(m)[0:2] == (DL_STATE['FAILED'], PN[want]), f'curl error {rc}: {want} at once')
    # 416: the .part is longer than the file (or changed): once from the start
    log = []

    def gone_range(url, o):
        start = int(o[10007].rstrip('-')) if o.get(10007) else 0
        log.append(start)
        if start: return dict(rc=22, code=416)
        return dict(code=200, body=DATA, ctype='audio/mpeg', length=len(DATA))
    m = machine(site=gone_range); m.put(f'{SHOW}/a.mp3.part', b'z' * 4000)
    r, th = add(m); calls = work(m, th)
    expect(log == [4000, 0] and m.fs.get(f'{SHOW}/a.mp3') == DATA and not sleeps(calls), 'a 416 for the Range: the .part is dropped and the file starts again, once, without waiting')
    log.clear()
    m = machine(site=lambda url, o: (log.append(1), dict(rc=22, code=416))[1]); m.put(f'{SHOW}/a.mp3.part', b'z' * 4000)
    r, th = add(m); calls = work(m, th)
    expect(len(log) == 2 and state(m)[0:2] == (DL_STATE['FAILED'], PN['HTTP']), 'a second 416 after the restart is a failure (no loop)')
    log.clear()
    m = machine(site=lambda url, o: (log.append(1), dict(rc=33, code=0))[1]); m.put(f'{SHOW}/a.mp3.part', b'z' * 4000)
    r, th = add(m); work(m, th)
    expect(len(log) == 2, 'curl\'s range error (33) is treated the same way')
    # the response's headers (patch/net.c net_head_line): a 206 for another part of the file than the one asked for is not appended
    log = []

    def head(m, o, *lines):
        for text in lines + ('',):
            buf = m.alloc(len(text) + 3); m.u.mem_write(buf, (text + '\r\n').encode())
            m.nested(o[20079], buf, 1, len(text) + 2, o[10029])

    def wrong_part(url, o):
        start = int(o[10007].rstrip('-')) if o.get(10007) else 0
        log.append((start, o.get(10023)))
        if start:
            head(m, o, 'HTTP/1.1 206 Partial Content', f'Content-Range: bytes 0-{len(DATA) - 1}/{len(DATA)}')
            return dict(code=206, body=DATA, ctype='audio/mpeg', length=len(DATA))
        head(m, o, 'HTTP/1.1 200 OK')
        return dict(code=200, body=DATA, ctype='audio/mpeg', length=len(DATA))
    m = machine(site=wrong_part); m.put(f'{SHOW}/a.mp3.part', b'z' * 4000)
    r, th = add(m); calls = work(m, th)
    expect([x[0] for x in log] == [4000, 0] and m.fs.get(f'{SHOW}/a.mp3') == DATA and not sleeps(calls),
           f'a 206 whose Content-Range starts at 0 for the Range "4000-": nothing is appended, the file starts again, once ({log})')
    expect(log[0][1] is None, 'a .part from an earlier run has no ETag: its Range carries no If-Range')
    log.clear()

    def right_part(url, o):
        start = int(o[10007].rstrip('-')) if o.get(10007) else 0
        log.append(start)
        head(m, o, 'HTTP/1.1 206 Partial Content', f'content-range: BYTES {start}-{len(DATA) - 1}/{len(DATA)}')
        return dict(code=206, body=DATA[start:], ctype='audio/mpeg', length=len(DATA) - start)
    m = machine(site=right_part); m.put(f'{SHOW}/a.mp3.part', DATA[:4000])
    r, th = add(m); work(m, th)
    expect(log == [4000] and m.fs.get(f'{SHOW}/a.mp3') == DATA, 'a 206 whose Content-Range starts where the Range asked is appended')
    # If-Range: an attempt of this run got its bytes with a strong ETag, so the retry asks for the rest of that same file
    for etag, want in (('"v1"', 'If-Range: "v1"'), ('W/"v1"', None), (None, None)):
        log = []

        def tagged(url, o, etag=etag):
            start = int(o[10007].rstrip('-')) if o.get(10007) else 0
            log.append((start, m.read_cstr(m.word(o[10023])) if o.get(10023) else None))
            tag = [f'ETag: {etag}'] if etag else []
            if not start:
                head(m, o, 'HTTP/1.1 200 OK', *tag)
                return dict(rc=56, code=200, partial=True, body=DATA[:700000], ctype='audio/mpeg', length=len(DATA))
            head(m, o, 'HTTP/1.1 206 Partial Content', *tag, f'Content-Range: bytes {start}-{len(DATA) - 1}/{len(DATA)}')
            return dict(code=206, body=DATA[start:], ctype='audio/mpeg', length=len(DATA) - start)
        m = machine(site=tagged)
        r, th = add(m); work(m, th)
        expect(log == [(0, None), (700000, want)] and m.fs.get(f'{SHOW}/a.mp3') == DATA, f'ETag {etag}: the retry after a break carries {want} ({log})')
    # the file changed on the server between two attempts: the If-Range gets the whole file (200), which replaces the bytes of the old one
    log = []
    NEW = bytes(reversed(DATA))

    def changed(url, o):
        start = int(o[10007].rstrip('-')) if o.get(10007) else 0
        log.append(start)
        if not start:
            head(m, o, 'HTTP/1.1 200 OK', 'ETag: "v1"')
            return dict(rc=56, code=200, partial=True, body=DATA[:700000], ctype='audio/mpeg', length=len(DATA))
        head(m, o, 'HTTP/1.1 200 OK', 'ETag: "v2"')
        return dict(code=200, body=NEW, ctype='audio/mpeg', length=len(NEW))
    m = machine(site=changed)
    r, th = add(m); work(m, th)
    expect(log == [0, 700000] and m.fs.get(f'{SHOW}/a.mp3') == NEW, 'a file that changed on the server: the 200 to the If-Range replaces the old bytes, the result is the new file alone')


def failure_tests(ctx):
    """A web page, a full card, the margin, a card that cannot be written; malformed answers."""
    expect = ctx.expect
    for ctype in ('text/html', 'text/html; charset=UTF-8', 'TEXT/HTML', 'text/plain'):
        m = machine(site=server(b'<html>Sign in to the Wi-Fi</html>', ctype=ctype))
        r, th = add(m); calls = work(m, th)
        expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['NOTAUDIO']) and left_over(m) == [] and not sleeps(calls) and len([c for c in calls if c[0] == 'curl_perform']) == 1 and not [c for c in calls if c[0] == 'write'],
               f'Content-Type {ctype}: "Not audio" at once, nothing written, no .part left')
    m = machine(site=server(b'<html></html>', ctype='text/html')); m.put(f'{SHOW}/a.mp3.part', b'earlier')
    r, th = add(m); work(m, th)
    expect(part_of(m) == b'earlier' and state(m)[1] == PN['NOTAUDIO'], 'a web page does not destroy the .part that was there')
    for ctype in ('audio/mpeg', 'audio/x-m4a', 'application/octet-stream', 'video/mp4', None):
        m = machine(site=server(body(3000), ctype=ctype), ents=[('g', 'a.mp3', 3000, URL_A)])
        r, th = add(m); work(m, th)
        expect(m.fs.get(f'{SHOW}/a.mp3') == body(3000), f'Content-Type {ctype}: accepted')
    # a card without room, before anything is fetched
    log = []
    m = machine(site=server(DATA, log), free_mb=MARGIN_MB + 1)
    r, th = add(m); calls = work(m, th)
    expect(not log and state(m)[0:2] == (DL_STATE['FAILED'], PN['CARDFULL']) and left_over(m) == [] and not sleeps(calls), 'a 1.24 MB episode with 33 MB free: the margin of 32 MB would be eaten, "Card is full", no request')
    for free, ok in ((MARGIN_MB + 2, True), (MARGIN_MB + 1, False)):
        log = []
        m = machine(site=server(DATA, log), free_mb=free, ents=[('g', 'a.mp3', len(DATA), URL_A)])
        r, th = add(m); work(m, th)
        expect((m.fs.get(f'{SHOW}/a.mp3') == DATA) == ok, f'{free} MB free for a 1.24 MB file: {"fits" if ok else "does not fit"} (it must leave 32 MB)')
    m = machine(site=server(DATA, log), free_mb=MARGIN_MB, ents=[('g', 'a.mp3', 0, URL_A)])
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['CARDFULL']) and part_of(m) is None, 'the length unknown and exactly 32 MB free: the first chunk would eat into the margin; nothing is written')
    m = machine(site=server(DATA), free_mb=MARGIN_MB + 3, ents=[('g', 'a.mp3', 0, URL_A)])
    r, th = add(m); work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA, 'the length unknown, 35 MB free: 1.24 MB fits')
    # the card fills up in the middle: the next chunk is refused, the first stays as a .part
    m = machine(site=server(DATA, chunk=65536), free_mb=MARGIN_MB + 100, ents=[('g', 'a.mp3', 0, URL_A)])
    base = m.curl_site

    def filling(url, o):
        out = base(url, o)
        out['xfer'] = lambda u, sent, total: setattr(m, 'free_mb', MARGIN_MB) if sent >= CHUNK + 1 else None   # (the second chunk finds no room)
        return out
    m.curl_site = filling
    r, th = add(m); calls = work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['CARDFULL']) and part_of(m) == DATA[:CHUNK] and not sleeps(calls) and len([c for c in calls if c[0] == 'curl_perform']) == 1,
           'the card fills up after the first chunk: the second is refused at once ("Card is full"), the first chunk stays as the .part, no retry')
    m.free_mb = 500
    m.curl_site = server(DATA)
    r, th = add(m); work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None, 'with room again, a tap resumes from that .part and finishes')
    # statfs fails; the .part cannot be opened; a write that fails; a rename that fails
    m = machine(site=server(DATA)); m.fail.add(('statfs', f'{SHOW}'))
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['STORAGE']), 'statfs that fails: "Storage unavailable"')
    m = machine(site=server(DATA)); m.fail.add(('open', f'{SHOW}/a.mp3.part'))
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['STORAGE']) and not [c for c in m.calls if c[0] == 'curl_perform'], 'a .part that cannot be opened: "Storage unavailable", nothing fetched')
    m = machine(site=server(DATA)); m.fail.add(('write', f'{SHOW}/a.mp3.part'))
    r, th = add(m); calls = work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['STORAGE']) and not sleeps(calls) and len(m.curl) == 0, 'a write that fails: "Storage unavailable" at once')
    m = machine(site=server(DATA)); m.fail.add(('fsync', f'{SHOW}/a.mp3.part'))
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['STORAGE']) and m.fs.get(f'{SHOW}/a.mp3') is None, 'an fsync that fails: the data is not trusted, no rename')
    m = machine(site=server(DATA)); m.fail.add(('rename', f'{SHOW}/a.mp3'))
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['STORAGE']) and part_of(m) == DATA, 'a rename that fails: "Storage unavailable", the finished .part stays (a tap renames it after a check)')
    # malformed answers and entries
    log = []
    m = machine(site=server(b'', log), ents=[('g', 'a.mp3', 0, URL_A)])
    r, th = add(m); work(m, th)
    expect(state(m)[0:2] == (DL_STATE['FAILED'], PN['HTTP']) and left_over(m) == [], 'a 200 with no bytes: not an episode ("Server error"), no empty file')
    for bad in ('ftp://x.example/a.mp3', 'file:///etc/passwd', 'javascript:1', '', 'x.example/a.mp3'):
        log = []
        m = machine(site=server(DATA, log), ents=[('g', 'a.mp3', 5, bad)])
        r, th = add(m); work(m, th)
        expect(not log and state(m)[0:2] == (DL_STATE['FAILED'], PN['GONE']), f'an enclosure address of {bad!r}: nothing is requested, "Not found"')
    log = []
    m = machine(site=server(DATA, log), ents=[('g', 'other.mp3', 5, URL_A)])
    r, th = add(m, 'a.mp3'); work(m, th)
    expect(not log and state(m)[1] == PN['GONE'], 'no line for the file in .episodes (a refresh dropped it): "Not found"')
    log = []
    m = machine(site=server(DATA, log)); del m.fs[f'{SHOW}/.episodes']
    r, th = add(m); work(m, th)
    expect(not log and state(m)[1] == PN['GONE'], 'no .episodes at all: "Not found"')
    m = machine(site=server(DATA, log), ents=[('g', 'a.mp3', 'x9', URL_A)])
    r, th = add(m); work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA, 'a length that is not a number is read as unknown')
    m = machine(site=server(DATA, log), ents=[('g', 'a.mp3', 99999999999999999999, URL_A)])
    r, th = add(m); work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA, 'a length of 20 digits is read as unknown (no overflow); it only sizes the free-space check')
    # a server that sends more than it said, and a transfer that ends early without an error
    m = machine(site=lambda url, o: dict(code=200, body=DATA, ctype='audio/mpeg', length=1000), ents=[('g', 'a.mp3', 1000, URL_A)])
    r, th = add(m); work(m, th)
    expect(m.fs.get(f'{SHOW}/a.mp3') == DATA, 'a body longer than the announced length is taken whole (libcurl decides what is complete, the length is only for the display)')


def control_tests(ctx):
    """Cancel, the pause for a refresh, and a refresh after it; the queue's order."""
    expect = ctx.expect
    # The life of a download, the whole table (pn_q_after): every state under every event; -1: the event does not apply, nothing moves
    F, W, A, S, D, P = (QS[k] for k in ('FREE', 'WAIT', 'ACTIVE', 'STOPPING', 'DROPPING', 'PUBLISHED'))
    table = dict(ADD={F: W}, CLAIM={W: A}, CANCEL={W: F, A: S}, DROP={W: F, A: D, S: D}, RESUME={S: A}, PUBLISH={A: P, S: P}, END={A: F, S: F, D: F, P: F}, HALT={A: W, S: F, D: F})
    m = machine()
    got = {ev: {st: v for st in range(6) if (v := m.call(PSYMS['pn_q_after'], a0=st, a1=i, count=10000)) < 6} for i, ev in enumerate(table)}
    expect(got == table, f'the state table: a waiting download leaves on a cancel or a drop; a running one pauses (STOPPING, undone by an add, still published by a rename) or is dropped (DROPPING: no way back, never '
           f'published); a published one hears neither; every taken-up one ends free, but a run halted for a pause that was taken back (HALT on ACTIVE) waits again ({got})')
    # Cancel the running one: the transfer is aborted at once, the bytes so far stay
    m = machine(site=server(DATA, chunk=65536))
    r, th = add(m)
    base = m.curl_site
    key = key_of('Show', 'a.mp3')

    def cancelling(url, o):
        out = base(url, o)
        out['xfer'] = lambda u, sent, total: stop(m, key) if sent >= 600000 else None
        return out
    m.curl_site = cancelling
    calls = work(m, th)
    kept = part_of(m)
    expect(fn(m, 'pn_dl_count') == 0 and m.fs.get(f'{SHOW}/a.mp3') is None and kept is not None and 600000 <= len(kept) < len(DATA) and kept == DATA[:len(kept)] and not sleeps(calls)
           and state(m)[0] == DL_STATE['NONE'] and not flagged(m) and fn(m, 'pn_dl_running') == 0,
           f'a cancel in the middle: the transfer stops, the {len(kept or b"")} bytes got stay as the .part (a prefix of the file), the queue is empty, no failure, no waiting')
    m.curl_site = server(DATA)
    log = []
    m.curl_site = server(DATA, log)
    r, th = add(m); work(m, th)
    expect(log[0][1] == len(kept) and m.fs.get(f'{SHOW}/a.mp3') == DATA, 'a later tap resumes from the .part')
    # Cancel and delete (pn_dl_drop: Remove Download, Delete, Unsubscribe): the page unlinks the .part at once; the thread writes none of the bytes it still holds
    for at, what in ((600000, 'with a chunk on the card and bytes in memory'), (100000, 'before the first chunk'), (len(DATA), 'at the last byte')):
        m = machine(site=server(DATA, chunk=65536))
        r, th = add(m)
        base = m.curl_site
        hit = []

        def dropping(url, o, at=at, m=m, hit=hit):
            out = base(url, o)

            def xfer(u, sent, total):
                if sent >= at and not hit:
                    hit.append(len(part_of(m) or b''))
                    stop(m, key, drop=True)   # what pn_dl_drop sets for the running one
                    m.fs.pop(f'{SHOW}/a.mp3.part', None)                                 # the page's unlink
            out['xfer'] = xfer
            return out
        m.curl_site = dropping
        work(m, th)
        expect(len(hit) == 1 and (at != 600000 or hit[0] == CHUNK) and left_over(m) == [] and fn(m, 'pn_dl_count') == 0 and state(m)[0] == DL_STATE['NONE']
               and not flagged(m),
               f'a drop {what}: the thread leaves no .part and no file behind (no piece of the middle to resume from), no failure, the flags are cleared')
        log = []
        m.curl_site = server(DATA, log)
        r, th = add(m); work(m, th)
        expect(log and log[0][1] == 0 and 10007 not in log[0][2] and m.fs.get(f'{SHOW}/a.mp3') == DATA, 'and the next download of it starts at byte 0 and is the whole file')
    # a drop that comes with the transfer already done: the file the thread publishes after it is taken away too
    m = machine(site=server(DATA))
    r, th = add(m)
    base = m.curl_site
    done = []

    def finishing(url, o):
        out = base(url, o)
        out['xfer'] = lambda u, sent, total: done.append(1) if sent >= len(DATA) else None
        return out
    m.curl_site = finishing
    m.on_statfs = lambda p: (stop(m, key, drop=True), m.fs.pop(f'{SHOW}/a.mp3.part', None)) if done else None   # (the last flush asks for the room)
    calls = work(m, th)
    m.on_statfs = None
    expect(done and [c for c in calls if c[0] == 'curl_perform'] and left_over(m) == [] and state(m)[0] == DL_STATE['NONE'] and not flagged(m) and fn(m, 'pn_dl_count') == 0,
           'a drop between the last byte and the rename: nothing stays on the card, no failure is shown')
    # a drop that comes after the rename, while the thread syncs the folder: the episode is downloaded, the drop flags nothing and the thread leaves the file alone
    for what in ('drop', 'unsubscribe'):
        m = machine(site=server(DATA))
        r, th = add(m)
        root, show = m.cstr(RP), sibling('pcarchive').show_addr(m, 'Show')
        seen = []

        def syncing(p, m=m, what=what, seen=seen):
            if p != SHOW or seen: return
            seen.append(m.fs.get(f'{SHOW}/a.mp3') == DATA)
            if what == 'drop': m.nested(PSYMS['pn_dl_drop'], key)
            else: seen.append(m.nested(PSYMS['pn_unsubscribe_show'], root, show))
            seen.append(len(flagged(m))); seen.append(run_state(m, key) == QS['PUBLISHED']); seen.append(len(flagged(m)))
        m.on_fsync = syncing
        work(m, th)
        m.on_fsync = None
        expect(seen[:1] == [True] and seen[-2] is True and seen[-1] == 0 and m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None and slot_states(m) == [0] * 32 and fn(m, 'pn_dl_count') == 0 and state(m)[0] == DL_STATE['NONE'],
               f'{what} while the folder is synced after the rename: the downloaded file stays whole, nothing is flagged or left flagged')
        if what == 'unsubscribe':
            expect(seen[1] == 1 and f'{SHOW}/.show' in m.fs and f'{SHOW}/.episodes' in m.fs, 'and Unsubscribe counts it as an episode on the card: the show and its files stay (1)')
    # a drop where a waiting download turns into the running one: the thread takes a download up under the mutex the drop holds, so the drop sees it waiting or running, never between
    m = machine(site=server(DATA))
    r, th = add(m)
    log, once = [], []
    m.curl_site = server(DATA, log)

    def before_claim():   # the thread waits for the mutex to take the download up: the drop has it first
        if once: return
        once.append(1); m.nested(PSYMS['pn_dl_drop'], key); m.fs.pop(f'{SHOW}/a.mp3.part', None)
    m.on_lock = before_claim
    work(m, th)
    m.on_lock = None
    expect(once and not log and left_over(m) == [] and fn(m, 'pn_dl_count') == 0 and not flagged(m),
           'a drop that gets the mutex before the thread takes the download up: it leaves the queue and is never fetched')
    # the slot is emptied and filled with another episode while the thread waits to take it up: it is taken up as that episode (its key), so that one's drop is heard
    m = machine(site=server(DATA, chunk=65536))
    r, th = add(m)
    root, folder, bname, key_b = m.cstr(RP), m.cstr('Show'), m.cstr('b.mp3'), key_of('Show', 'b.mp3')
    log, base, once, later = [], m.curl_site, [], []

    def reuse():   # Remove Download on a, then a tap on b: b gets a's slot
        if once: return
        once.append(1); m.nested(PSYMS['pn_dl_drop'], key)
        once.append(m.nested(PSYMS['pn_dl_add'], root, folder, bname)); once.append(m.word(pn_at(Q0 + 8)))

    def drop_b(url, o):
        log.append(url)
        out = base(url, o)

        def xfer(u, sent, total):
            if sent >= 600000 and not later:
                later.append(m.word(pn_at(DKEY))); m.nested(PSYMS['pn_dl_drop'], key_b); m.fs.pop(f'{SHOW}/b.mp3.part', None)
        out['xfer'] = xfer
        return out
    m.on_lock, m.curl_site = reuse, drop_b
    work(m, th)
    m.on_lock = None
    expect(once == [1, 0, key_b] and later == [key_b] and log == [URL_A.replace('/a.', '/b.')] and left_over(m) == [] and fn(m, 'pn_dl_count') == 0
           and not flagged(m) and state(m, 'b.mp3')[0] == DL_STATE['NONE'],
           'a removed, its slot filled with b, b removed under its transfer: b ran under its own key, its drop stopped it, no file and no flag is left')
    m = machine(site=server(DATA, chunk=65536))
    r, th = add(m)
    base, once = m.curl_site, []

    def after_claim(url, o):   # the thread took it up while the drop waited for the mutex: the drop finds it running, with bytes in memory
        out = base(url, o)

        def xfer(u, sent, total):
            if sent >= 600000 and not once:
                once.append(1); m.nested(PSYMS['pn_dl_drop'], key); m.fs.pop(f'{SHOW}/a.mp3.part', None)
        out['xfer'] = xfer
        return out
    m.curl_site = after_claim
    work(m, th)
    expect(once and left_over(m) == [] and fn(m, 'pn_dl_count') == 0 and state(m)[0] == DL_STATE['NONE'] and not flagged(m),
           'a drop of a download the thread has just taken up (pn_dl_drop itself, run under the transfer): flagged as a drop, no .part comes back')
    m = machine(site=server(DATA))
    r, th = add(m)
    held = []

    def claiming():   # the page's drop waits for the mutex while the thread takes the download up
        if held: return
        held.append(1); poke_slot(m, 0, 'Show', 'a.mp3', 2)
    m.on_lock = claiming
    m.call(PSYMS['pn_dl_drop'], a0=key, count=2000000)
    m.on_lock = None
    expect(held and flagged(m) == [QS['DROPPING']] and fn(m, 'pn_dl_count') == 1,
           'a download taken up while the drop waited for the mutex is found running: both flags are set (not a pause)')
    # a tap again on a download being paused, while the thread ends it (END against RESUME): the add looks and queues in one hold of the mutex, so the ended download is queued as a new one
    m = machine(site=server(DATA, chunk=65536))
    r, th = add(m)
    base, log, once = m.curl_site, [], []

    def pausing(url, o):
        log.append(o.get(10007))
        out = base(url, o)
        if len(log) == 1: out['xfer'] = lambda u, sent, total: stop(m, key) if sent >= 600000 else None
        return out

    def ending():   # the thread is at END's lock with the slot STOPPING: the page's add comes in, and the thread's END wins the mutex before the add's hold
        if not once and run_state(m, key) == QS['STOPPING'] and len(log) == 1:
            once.append(1)
            once.append(m.nested(PSYMS['pn_dl_add'], root_a, folder_a, name_a))
        elif len(once) == 1:
            once.append(2); m.setword(pn_at(Q0), QS['FREE'])   # (what END does to the slot)
    root_a, folder_a, name_a = m.cstr(RP), m.cstr('Show'), m.cstr('a.mp3')
    m.curl_site, m.on_lock = pausing, ending
    work(m, th)
    m.on_lock = None
    expect(once == [1, 2, 0] and len(log) == 2 and log[1] and int(log[1].rstrip('-')) >= CHUNK and m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None
           and fn(m, 'pn_dl_count') == 0 and fn(m, 'pn_dl_running') == 0,
           f'a resume that loses the mutex to the download\'s end is not dropped: the episode is queued again, the same thread resumes it from the .part and the file is whole (requests from {log})')
    # the other order (RESUME before END), at two moments after the thread stopped the transfer: at the lock of the run's end, and during the last flush (before the attempt reads the slot again). The
    # pause is taken back, the transfer is not: the run ends in HALT, the episode waits again and the same thread goes on with it from the .part, with no wait for the network between
    for moment in ('lock', 'statfs'):
        m = machine(site=server(DATA, chunk=65536))
        r, th = add(m)
        base, log, once = m.curl_site, [], []

        def pausing(url, o, m=m, base=base, log=log):
            log.append(o.get(10007))
            out = base(url, o)
            if len(log) == 1: out['xfer'] = lambda u, sent, total: stop(m, key) if sent >= 600000 else None
            return out

        def resuming(*a, m=m, log=log, once=once):
            if not once and run_state(m, key) == QS['STOPPING'] and len(log) == 1:
                once.append(1)
                once.append(m.nested(PSYMS['pn_dl_add'], m.cstr(RP), m.cstr('Show'), m.cstr('a.mp3')))
                once.append(run_state(m, key))
        m.curl_site = pausing
        setattr(m, 'on_' + moment, resuming)
        calls = work(m, th)
        setattr(m, 'on_' + moment, None)
        expect(once == [1, 0, QS['ACTIVE']] and len(log) == 2 and log[1] and int(log[1].rstrip('-')) >= CHUNK and m.fs.get(f'{SHOW}/a.mp3') == DATA and part_of(m) is None
               and not sleeps(calls) and state(m)[0] == DL_STATE['NONE'] and fn(m, 'pn_dl_count') == 0 and fn(m, 'pn_dl_running') == 0,
               f'a resume that takes the mutex before the end of a stopped run ({moment}) is kept: the run ends in HALT, the episode waits again and is fetched from the .part at once, no failure and '
               f'no wait (add {once}, requests from {log}, sleeps {sleeps(calls)})')
    # pn_dl_drop on the UI thread: the running one is flagged for both, a waiting one only leaves the queue
    m = machine(site=server(DATA))
    r, th = add(m); add(m, 'b.mp3')
    poke_slot(m, 0, 'Show', 'a.mp3', 2); m.setword(pn_at(DKEY), key)
    m.call(PSYMS['pn_dl_drop'], a0=key_of('Show', 'b.mp3'), count=2000000)
    expect(not flagged(m) and fn(m, 'pn_dl_count') == 1, 'dropping a waiting download takes it out of the queue and flags nothing')
    m.call(PSYMS['pn_dl_drop'], a0=key, count=2000000)
    expect(flagged(m) == [QS['DROPPING']] and state(m)[0] == DL_STATE['NONE'], 'dropping the running one flags the drop and the cancel; its row stops saying Downloading')
    r, th2 = add(m)
    expect(r == 0 and flagged(m) == [QS['DROPPING']] and fn(m, 'pn_dl_count') == 2 and fn(m, 'pn_dl_waiting') == 1 and state(m)[0] == DL_STATE['WAIT'],
           'a tap again before the thread took the drop does not undo it (the .part is gone): the episode is queued afresh behind the dropped one')
    # pn_dl_cancel from the UI: a waiting one is taken out; the running one is flagged
    m = machine(site=server(DATA))
    r, th = add(m); add(m, 'b.mp3'); add(m, 'c.mp3')
    m.call(PSYMS['pn_dl_cancel'], a0=key_of('Show', 'b.mp3'), count=2000000)
    expect(fn(m, 'pn_dl_count') == 2 and state(m, 'b.mp3')[0] == DL_STATE['NONE'], 'cancelling a waiting download takes it out of the queue')
    log = []
    m.curl_site = server(DATA, log)
    work(m, th)
    expect([x[0] for x in log] == [URL_A, URL_A.replace('/a.', '/c.')] and f'{SHOW}/b.mp3' not in m.fs, 'it is never fetched; the others are, in order')
    m = machine(site=server(DATA))
    r, th = add(m)
    poke_slot(m, 0, 'Show', 'a.mp3', 2); m.setword(pn_at(DKEY), key)
    m.call(PSYMS['pn_dl_cancel'], a0=key, count=2000000)
    expect(flagged(m) == [QS['STOPPING']] and state(m)[0] == DL_STATE['NONE'], 'cancelling the running one flags it (the worker aborts and drops it); its row stops saying Downloading')
    r, th2 = add(m)
    expect(r == 0 and not flagged(m) and state(m)[0] == DL_STATE['ACTIVE'], 'a tap again before the worker took the cancel undoes it')
    # a refresh pending beside the downloads: nothing pauses them, the job's thread and the download thread each run to the end
    m = lanes()
    r, th = add(m); add(m, 'b.mp3')
    r, thr = PCN.start(m, ['Other'])
    base = m.curl_site
    queued = []

    def late(url, o):
        out = base(url, o)
        if url.endswith('/b.mp3') or '/b.mp3?' in url:   # during the last transfer a third episode is queued (a tap on its row)
            out['xfer'] = lambda u, sent, total: (poke_slot(m, 2, 'Show', 'c.mp3', 1, seq=9), queued.append(1)) if sent >= 600000 and not queued else None
        return out
    m.curl_site = late
    m.calls = []
    calls = work(m, th)
    expect(len(queued) == 1 and f'{SHOW}/a.mp3' in m.fs and f'{SHOW}/b.mp3' in m.fs and m.fs.get(f'{SHOW}/c.mp3') == DATA and len([c for c in calls if c[0] == 'curl_perform']) == 3 and 'pthread_create' not in [c[0] for c in calls]
           and fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_dl_count') == 0 and not sleeps(calls) and part_of(m) is None,
           'an episode queued during the last transfer is downloaded by the same thread run (no second thread, nothing paused, no .part left)')
    expect(fn(m, 'pn_busy') == 1 and m.word(pn_at(KIND)) == 1, 'and the refresh is still pending on its own lane meanwhile')
    PCN.work(m, thr)
    expect(fn(m, 'pn_busy') == 0 and PCN.status(m, 'https://feeds.example/other')[0] == 0, 'the refresh thread then completes its own result')
    # a cancel that comes in while the job waits to retry is heard within a second (the wait is one-second sleeps)
    key = key_of('Show', 'a.mp3')
    hit = []
    m = machine(site=lambda url, o: (hit.append(1), dict(rc=56, code=0))[1])
    r, th = add(m)
    m.on_sleep = lambda n, m=m: stop(m, key) if n == 3 else None
    calls = work(m, th)
    m.on_sleep = None
    expect(len(hit) == 1 and len(sleeps(calls)) == 3 and state(m)[0] == DL_STATE['NONE'] and fn(m, 'pn_dl_running') == 0 and part_of(m) is None,
           'a cancel during the first wait: heard at the third second, one request, dropped')


def sweep_tests(ctx):
    """The page's actions at every step of the download thread. One download whose first transfer breaks (so the wait and a second request are steps too) is run once to count the thread's steps
    (each lock and unlock of the mutex, each look at the card's room, each sync, each second of the wait, each chunk of a transfer); then it is run again for every step with each action there,
    and for every pair of steps with one action at each. Nothing is said about how a run goes: only what must hold when the thread has ended."""
    expect = ctx.expect
    key, FILE, PART = key_of('Show', 'a.mp3'), f'{SHOW}/a.mp3', f'{SHOW}/a.mp3.part'
    CH = 262144

    def run(plan):
        """plan: {step: the actions there}. Returns (the steps' kinds, the actions done, why the end is wrong or None)."""
        m = machine()
        good = server(DATA, chunk=CH)
        st = dict(busy=False, kinds=[], done=[], reqs=0, kept=None, ret=0)

        def act(name):
            if name == 'cancel': m.nested(PSYMS['pn_dl_cancel'], key)
            elif name == 'drop':   # (as the pages do it: the drop, then the .part is unlinked; a file in place by then is a downloaded episode)
                m.nested(PSYMS['pn_dl_drop'], key)
                st['kept'] = FILE in m.fs
                m.fs.pop(PART, None)
            else: st['ret'] = m.nested(PSYMS['pn_dl_add'], m.cstr(RP), m.cstr('Show'), m.cstr('a.mp3'))
            st['done'].append(name)

        def tick(kind):
            if st['busy']: return   # (a step of the action itself)
            i = len(st['kinds']); st['kinds'].append(kind)
            st['busy'] = True
            for name in plan.get(i, ()): act(name)
            st['busy'] = False

        def site(url, o):
            st['reqs'] += 1
            out = (dict(rc=56, code=200, partial=True, body=DATA[:700000], ctype='audio/mpeg', chunk=CH, length=len(DATA)) if st['reqs'] == 1 else good(url, o))
            out['xfer'] = lambda *a: tick('xfer')
            return out
        m.curl_site = site
        r, th = add(m)
        for h in ('lock', 'unlock', 'statfs', 'fsync', 'sleep'): setattr(m, 'on_' + h, lambda *a, h=h: tick(h))
        m.thread = None
        work(m, th)
        while m.thread:   # (an add after the thread's last look at the queue starts another)
            th, m.thread = m.thread, None
            work(m, th)
        for h in ('lock', 'unlock', 'statfs', 'fsync', 'sleep'): setattr(m, 'on_' + h, None)
        file, part, last = m.fs.get(FILE), m.fs.get(PART), (st['done'] or ['add'])[-1]
        why = None
        if any(slot_states(m)) or fn(m, 'pn_dl_count') or fn(m, 'pn_dl_running'): why = f'the queue is not empty ({[s for s in slot_states(m) if s]})'
        elif file is not None and file != DATA: why = f'the file in place is not the episode ({len(file)} bytes)'
        elif part is not None and (file is not None or not DATA.startswith(part)): why = f'the .part is not a start of the episode, or is beside the file ({len(part)} bytes)'
        elif state(m)[0] == DL_STATE['FAILED']: why = 'a failure is kept'
        elif st['ret']: why = f'an add failed ({st["ret"]})'
        elif last == 'add' and file is None: why = 'the episode asked for last is not downloaded'
        elif last == 'drop' and (part is not None or (file is not None) != st['kept']): why = f'after a drop: .part {part is not None}, file {file is not None} (in place at the drop: {st["kept"]})'
        return st['kinds'], st['done'], why
    kinds, _, why = run({})
    n = len(kinds)
    expect(why is None and set(kinds) == {'lock', 'unlock', 'statfs', 'fsync', 'sleep', 'xfer'} and n >= 30,
           f'the download alone: whole, and its {n} steps are of every kind ({why}; {sorted(set(kinds))})')
    bad, runs = [], 0
    for i in range(n):
        for acts in (('cancel',), ('drop',), ('cancel', 'add'), ('drop', 'add'), ('cancel', 'drop'), ('cancel', 'add', 'cancel'), ('cancel', 'add', 'drop')):
            k, done, why = run({i: acts})
            runs += 1
            if why: bad.append((i, kinds[i], acts, why))
    expect(not bad, f'each action at each of the {n} steps ({runs} runs): the queue ends empty, the file is whole or not there, a .part is a start of the file, a drop leaves no .part and no file but one '
           f'in place before it, the episode asked for last is downloaded ({len(bad)} wrong: {bad[:6]})')
    bad, runs = [], 0
    for i in range(n):
        for first, second in (('cancel', 'add'), ('cancel', 'drop'), ('drop', 'add'), ('drop', 'cancel')):
            j = i + 1
            while True:   # (the steps after the first action are that run's own: j goes on until the run has no such step)
                k, done, why = run({i: (first,), j: (second,)})
                if len(done) < 2: break
                runs += 1
                if why: bad.append((i, k[i], first, j, k[j], second, why))
                j += 1
    expect(not bad and runs > 500, f'two actions at two steps ({runs} runs): the same holds ({len(bad)} wrong: {bad[:6]})')


def refresh_tests(ctx):
    """.episodes keeps the line of a .part across a refresh; the states a refresh reads."""
    expect = ctx.expect
    wsj = PCN.feed_bytes('wsj-3items.xml')
    m = machine(site=lambda url, o: {'body': wsj}, ents=[('old-guid', 'old file.mp3', 7, 'https://x.example/old.mp3'), ('gone-guid', 'gone.mp3', 7, 'https://x.example/gone.mp3')])
    m.put(f'{SHOW}/old file.mp3.part', b'half')
    r, th = PCN.start(m, ['Show']); PCN.work(m, th)
    text = m.fs[f'{SHOW}/.episodes'].decode()
    expect('f=old file.mp3' in text and 'old-guid' in text and 'gone.mp3' not in text, 'a refresh keeps the line of an episode that has only a .part (the feed no longer lists it); one with no file at all goes')
    shows, arr = m.shows()
    eps = m.episodes(arr + [s['dir'] for s in shows].index('Show') * O['PC_SHOW_SIZE'])
    byfile = {e['file']: e for e in eps}
    expect(byfile['old file.mp3']['state'] == O['PC_PART'] and byfile['old file.mp3']['hash'] == 0 and sum(e['state'] == O['PC_REMOTE'] for e in eps) == 3, 'the model: PC_PART for it, the feed\'s three are PC_REMOTE')
    # an item the feed lists keeps its file name (so its .part is found again), the guid matching the old line
    m = machine(site=lambda url, o: {'body': wsj}, ents=[('x', 'x.mp3', 1, 'https://x/x.mp3')])
    r, th = PCN.start(m, ['Show']); PCN.work(m, th)
    lines = [dict(f.split('=', 1) for f in ln.split('\t')) for ln in m.fs[f'{SHOW}/.episodes'].decode().split('\n')[1:] if ln]
    first = lines[2]
    m.put(f'{SHOW}/{first["f"]}.part', b'1234')
    r, th = PCN.start(m, ['Show']); PCN.work(m, th)
    again = [dict(f.split('=', 1) for f in ln.split('\t')) for ln in m.fs[f'{SHOW}/.episodes'].decode().split('\n')[1:] if ln]
    expect(first['f'] in [a['f'] for a in again] and first['u'] in [a['u'] for a in again], 'a listed item keeps its file name and its enclosure url across refreshes: the .part is still its own')
    # a downloaded file survives a refresh and stays an episode
    m = machine(site=server(DATA), ents=[(lines[2]['g'], lines[2]['f'], len(DATA), 'https://x/x.mp3')])
    r, th = add(m, lines[2]['f']); work(m, th)
    m.curl_site = lambda url, o: {'body': wsj}
    r, th = PCN.start(m, ['Show']); PCN.work(m, th)
    shows, arr = m.shows()
    eps = m.episodes(arr + [s['dir'] for s in shows].index('Show') * O['PC_SHOW_SIZE'])
    expect(sum(e['state'] == O['PC_LOCAL'] for e in eps) == 1 and m.fs[f'{SHOW}/{lines[2]["f"]}'] == DATA, 'a downloaded episode is a local file after the next refresh')


def card(m):
    """Sub One: two episodes not on the card (urls), Sub Two: a third; the .part of one."""
    PF.card(m)
    m.put(f'{RP}/Sub One/.episodes', (PCP.EPS_HEAD + f'g=s1\tp={NOW - 5000}\td=600\tl={len(DATA)}\tf=a.mp3\tt=Remote A\tu=https://e.example/a.mp3\ng=s2\tp={NOW - 9000}\td=1200\tl=0\tf=b.mp3\tt=Remote B\tu=https://e.example/b.mp3\n'
                                      f'g=s3\tp={NOW - 9500}\td=60\tf=c.mp3\tt=Remote C\tu=https://e.example/c.mp3\n').encode())


def page(extra=None):
    m = PCP.opened(lambda mm: (card(mm), extra(mm) if extra else None), PCN.NM)
    m.curl_site = server(DATA)
    return m


def open_sub_one(m):
    PCP.tap_show(m, 'Sub One')

def lines(m):
    """[(cell, label)] of the Show page's state pills in the frames that show its cells."""
    return sorted((i, c['pill']) for i, c in PCP.all_cells(m).items())


def dates(m):
    return sorted((i, c['date']) for i, c in PCP.all_cells(m).items())


def titles(m):
    """[(cell, title, style)]: a played episode's title is in the grey style."""
    return sorted((i, ' '.join(c['title']), 'label_ps_cdim' if c['played'] else 'label_ps_ctitle') for i, c in PCP.all_cells(m).items())


def tick(m, name='pg_tick'):
    m.screen(True)
    return m.call(PSYMS[name], a0=0, count=40000000)


def page_tests(ctx):
    """The Show level opened from Feeds: a tap queues, a tap cancels, the lines say what is going on; the Downloads row; the refresh pausing the downloads."""
    expect = ctx.expect
    m = page()
    open_sub_one(m)
    before = [t for _, t in lines(m)]
    expect(dates(m)[0][1] == '1h ago' and before == [f'{(len(DATA) + 1048575) >> 20} MB', 'Download', 'Download'], f'a plain remote episode: its date line and a download pill with the feed\'s size, "Download" without one ({dates(m)[0]}, {before})')
    m.calls = []; m.thread = None
    PCP.act(m, 0)
    expect(m.thread and m.thread[0] == PSYMS['pn_dmain'] and toasts(m) == [] and ('timer_add', PSYMS['pg_awake_tick'], 1000) in m.calls and fn(m, 'pn_dl_count') == 1,
           'a tap on an episode that is not on the card queues it: the worker starts and the page arms its 1 s downloads timer')
    expect(dict(lines(m))[0] == 'Waiting' and dict(lines(m))[1] == before[1], 'its pill says Waiting (the ring at 0); the others are unchanged')
    expect(titles(m)[0][2] == 'label_ps_ctitle', 'the title stays bright: an episode not on the card is unplayed')
    bl, *_ = PCP.paint(m)
    expect(not [b for b in bl if tuple(b[2][2:]) == (O['PA_BADGE_PX'], O['PA_BADGE_PX'])], 'and it has no on-the-card badge')
    m.calls = []
    PCP.act(m, 0)
    expect(fn(m, 'pn_dl_count') == 0 and dict(lines(m))[0] == before[0] and 'pthread_create' not in [c[0] for c in m.calls],
           'a tap on a queued cell\'s pill takes it out of the queue; the pill is the size again (there is no .part)')
    PCP.act(m, 0)
    th = m.thread
    # running: the status record says it
    key_a = key_of('Sub One', 'a.mp3')
    poke_slot(m, 0, 'Sub One', 'a.mp3', 2)
    m.setword(pn_at(DKEY), key_a); m.setword(pn_at(DGOT), len(DATA) * 42 // 100); m.setword(pn_at(DTOTAL), len(DATA)); m.setword(pn_at(DGEN), 5); m.setword(pn_at(DBUSY), 1)
    tick(m)
    expect(dict(lines(m))[0] == '42%', f'a running download: the ring and "42%" ({dict(lines(m))[0]})')
    m.setword(pn_at(DTOTAL), 0); m.setword(pn_at(DGOT), 12 * 1048576 + 5); m.setword(pn_at(DGEN), 6)
    tick(m)
    expect(dict(lines(m))[0] == '12 MB', 'the length unknown: "12 MB"')
    m.setword(pn_at(DTOTAL), 1000); m.setword(pn_at(DGOT), 5000); m.setword(pn_at(DGEN), 7)
    tick(m)
    expect(dict(lines(m))[0].endswith('MB'), 'a length that is smaller than the bytes got was wrong: read as unknown (MB)')
    m.setword(pn_at(DGOT), 100); m.setword(pn_at(DTOTAL), len(DATA)); m.setword(pn_at(DGEN), 8)
    tick(m)
    expect(dict(lines(m))[0] == '0%', 'under one percent: 0%')
    m.setword(pn_at(DGOT), len(DATA)); m.setword(pn_at(DGEN), 9)
    tick(m)
    expect(dict(lines(m))[0] == '100%', '100%')
    m.screen(False); m.setword(pn_at(DGOT), len(DATA) // 2); m.setword(pn_at(DGEN), 11); m.calls = []
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_text_utf8', 'grid_drop')],
           'screen off: a step of progress does no visual work (the first lit tick paints it)')
    tick(m)
    expect(dict(lines(m))[0] == '49%', 'the screen is back: the pill is right again')
    m.setword(pn_at(DWAIT), 1); m.setword(pn_at(DGEN), 10)
    tick(m)
    expect(dict(lines(m))[0] == 'Waiting', 'waiting for a retry: Waiting')
    m.setword(pn_at(DWAIT), 0)
    # a failure, with the .part kept
    m.setword(pn_at(DBUSY), 0); poke_slot(m, 0, 'Sub One', 'a.mp3', 0)
    words = {PN['NOWIFI']: 'No Wi-Fi', PN['NOCLOCK']: 'Set the date first', PN['NOCERT']: 'Certificates missing', PN['CERT']: 'Certificate problem', PN['NET']: "Can't connect",
             PN['GONE']: 'Not found', PN['HTTP']: 'Server error', PN['STORAGE']: 'Storage unavailable', PN['MEM']: 'Not enough memory', PN['CARDFULL']: 'Card is full', PN['NOTAUDIO']: 'Not audio'}
    for gen, (code, word) in enumerate(words.items(), 20):
        poke_fail(m, 0, 'Sub One', 'a.mp3', code); m.setword(pn_at(0 + 12), gen)
        tick(m)
        expect(dict(lines(m))[0] == 'Retry', f'failure {code} ({word}): the pill reads Retry ({dict(lines(m))[0]}); the reason is on the Downloads level')
    # Paused: a .part with no state of the queue
    poke_fail(m, 0, 'Sub One', 'a.mp3', 0); m.setword(pn_at(12), 60)
    m.put(f'{RP}/Sub One/b.mp3.part', b'x' * 100)
    tick(m)
    expect(dict(lines(m))[1] == 'Paused', 'an incomplete .part and nothing queued (after a reboot): Paused')
    PCP.act(m, 1)
    expect(fn(m, 'pn_dl_count') >= 1 and state(m, 'b.mp3', 'Sub One')[0] == DL_STATE['WAIT'] and dict(lines(m))[1] == 'Waiting', 'a tap on a Paused row queues it again (it resumes from the .part)')
    # a tap with no Wi-Fi: the toast, nothing queued
    m = page(); open_sub_one(m); m.wifi = -1; m.calls = []; m.thread = None
    PCP.act(m, 0)
    expect(toasts(m) == ['No Wi-Fi'] and m.thread is None and fn(m, 'pn_dl_count') == 0, 'a tap with no Wi-Fi: the toast says so, nothing is queued')
    m.wifi = 4; m.wall = 1700000000; m.calls = []
    PCP.act(m, 0)
    expect(toasts(m) == ['Set the date first'], 'a clock that was never set: "Set the date first"')
    # the whole thing through the real worker: the tap, the thread, the page's tick, the local row
    m = page(); open_sub_one(m); m.thread = None
    PCP.act(m, 0)
    th = m.thread
    work(m, th)
    tick(m)
    expect(f'{RP}/Sub One/a.mp3' in m.fs and dates(m)[0][1] == '1h ago' and dict(lines(m))[0] == '10m', f'the download ends: the page reads the episodes again, the cell is a local episode (its pill {dict(lines(m))[0]})')
    t = titles(m)
    expect(t[0][2] == 'label_ps_ctitle' and t[1][2] == 'label_ps_ctitle', 'the titles are all unplayed (bright)')
    bl, *_ = PCP.paint(m)
    expect(len([b for b in bl if tuple(b[2][2:]) == (O['PA_BADGE_PX'], O['PA_BADGE_PX'])]) == 1, 'and the finished one has the on-the-card badge')
    m.calls = []
    PCP.act(m, 0)
    q, idx = m.played
    paths = [m.read_cstr(m.word(rec + O['REC_PATH'])) for rec in q]
    expect(paths == [f'{RP}/Sub One/a.mp3'] and idx == 0, f'a tap on it plays it like any local episode, the queue of the files only ({paths})')
    # a second, on the Shows level: the Downloads row
    m = page(); open_sub_one(m)
    PCP.act(m, 0); PCP.act(m, 1)
    PCP.click(m, 'btn_return')
    _, texts, styles, _ = PCP.paint_bottom(m)
    got = sorted(((t, s) for (t, (x, y, w, h)), s in zip(texts, styles)))
    expect(('Downloaded', 'label_row_title') in got and ('2 waiting', 'label_row_sub') in got, f'the Shows level: the Downloads row, in the plain title style, says "2 waiting" ({got[:6]})')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(4, True, 0)['h'], 'the row is always there: the content is the same height as with nothing queued')
    poke_slot(m, 0, 'Sub One', 'a.mp3', 2); m.setword(pn_at(DKEY), key_a); m.setword(pn_at(DGOT), len(DATA) // 4); m.setword(pn_at(DTOTAL), len(DATA)); m.setword(pn_at(DGEN), 77)
    tick(m)
    _, texts, styles, _ = PCP.paint_bottom(m)
    got = sorted((t for (t, (x, y, w, h)), s in zip(texts, styles)))
    expect('Downloading 24%' in got, f'the Downloads row shows the one running ({got})')
    poke_slot(m, 0, 'Sub One', 'a.mp3', 0); poke_slot(m, 1, 'Sub One', 'b.mp3', 0); m.setword(pn_at(DKEY), 0); m.setword(pn_at(12), 90)
    tick(m)
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(4, True, 0)['h'] and 'Downloading 24%' not in [t for (t, _), s in zip(*PCP.paint(m)[1:3])], 'when nothing is queued the row stays and the running line goes')


def refresh_page_tests(ctx):
    """Refresh All while downloads run: the refresh starts at once beside the download thread, nothing pauses or restarts."""
    expect = ctx.expect
    m = page(lambda mm: mm.put(f'{RP}/Sub One/a.mp3.part', DATA[:1000])); open_sub_one(m)   # (it had begun: the refresh keeps the line of an episode with a .part)
    PCP.act(m, 0)
    th = m.thread
    PCP.click(m, 'btn_return')
    m.calls = []; m.thread = None
    PCP.refresh_all(m)   # Refresh All
    rthr = m.thread
    _, texts, styles, _ = PCP.paint(m)
    got = {t for (t, r) in texts}
    expect(rthr and rthr[0] == PSYMS['pn_main'] and rthr != th and fn(m, 'pn_busy') == 1 and fn(m, 'pn_dl_running') == 1 and fn(m, 'pn_dl_waiting') + fn(m, 'pn_dl_count') >= 1
           and PF.flags(m, 'pod_pd_scrim') == (1, 1) and PF.flags(m, 'pod_pd_cancel') == (1, 1),
           'Refresh All while a download runs: the refresh thread is created in the same tap, the download thread keeps running, the queue is untouched, the dialog opens at once')
    expect('Waiting' not in got and any(t.startswith('Refreshing') for t in got), 'the refresh line says Refreshing, never Waiting')
    m.thread = None; m.calls = []
    tick(m)
    expect(m.thread is None and 'pthread_create' not in [c[0] for c in m.calls] and fn(m, 'pn_dl_running') == 1, 'the next tick starts nothing more: no second refresh, no restart of the downloads')
    m.curl_site = lambda url, o: {'body': PCN.feed_bytes('headlines-3items.xml')} if 'f.example' in url else server(DATA)(url, o)
    work(m, th)
    expect(fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_dl_count') == 0 and m.fs.get(f'{RP}/Sub One/a.mp3') == DATA and fn(m, 'pn_busy') == 1, 'the download thread runs to its end beside the pending refresh: the episode is a file (resumed from its .part)')
    work(m, rthr)
    expect(fn(m, 'pn_busy') == 0 and fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_dl_count') == 0 and m.fs.get(f'{RP}/Sub One/a.mp3') == DATA, 'then the refresh ends too: both results are there')
    m.thread = None; m.calls = []
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(m.thread is None and 'pthread_create' not in [c[0] for c in m.calls], 'when the dialog closes no download is restarted (none was stopped)')
    # the screen off or the page away while a download runs: the refresh is not held up for it, the downloads go on
    m = page(); open_sub_one(m); PCP.act(m, 0); th = m.thread
    PCP.click(m, 'btn_return')
    m.screen(False); m.thread = None; m.calls = []
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(m.thread is None and 'pthread_create' not in [c[0] for c in m.calls] and fn(m, 'pn_dl_running') == 1, 'screen off with a download running: the timer starts nothing (the thread is there)')
    work(m, th)
    expect(fn(m, 'pn_dl_running') == 0, 'and the thread finishes its queue')


def awake_tests(ctx):
    """reset_poweroptions_timer: only from the page's timer on the UI thread, only while a download runs, with (1, 1, 0)."""
    expect = ctx.expect
    addr = pod.FUNCTIONS['reset_poweroptions_timer'][2]
    expect(addr == 0x4d7874 and pod.FUNCTIONS['reset_poweroptions_timer'][1] == 'int, int, int' and any(a == 0x4d7874 for a, *_ in pod.PODCAST_PINS), 'reset_poweroptions_timer is stock 0x4d7874, pinned')
    m = page(); open_sub_one(m)
    m.calls = []
    r = m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(r == 0 and not [c for c in m.calls if c[0] == 'reset_poweroptions_timer'], 'the timer with nothing queued: no call, and it ends')
    PCP.act(m, 0)
    th = m.thread
    m.calls = []
    r = m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(r == O['RET_REPEAT'] and [c for c in m.calls if c[0] == 'reset_poweroptions_timer'] == [('reset_poweroptions_timer', 1, 1, 0)],
           'a download thread running: the timer calls reset_poweroptions_timer(1, 1, 0) once (standby and auto power-off; not the screen) and goes on')
    calls = work(m, th)
    expect(not [c for c in calls if c[0] == 'reset_poweroptions_timer'], 'the worker thread never calls it')
    m.calls = []
    r = m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(r == 0 and not [c for c in m.calls if c[0] == 'reset_poweroptions_timer'], 'the download is done: no call, the timer ends')
    # a queue that waits (no thread running): no call
    m = page(); open_sub_one(m)
    PCP.act(m, 0)
    m.setword(pn_at(DBUSY), 0)   # the thread could not be created
    m.thread = None; m.calls = []
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'reset_poweroptions_timer'] and m.thread and m.thread[0] == PSYMS['pn_dmain'], 'a queue with no thread: the timer starts the worker (a tap that raced its end); it keeps nothing awake before it runs')
    # the refresh's thread does not keep the device awake
    m = page(); open_sub_one(m)
    m.setword(pn_at(KIND), 1); m.setword(pn_at(0), 1)   # a refresh's job thread runs, no download
    m.calls = []
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'reset_poweroptions_timer'], 'only a download thread keeps the device awake (a job running alone, the refresh dialog, is its own thing)')
    m.setword(pn_at(DBUSY), 1)   # a download beside the job
    m.calls = []
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect([c for c in m.calls if c[0] == 'reset_poweroptions_timer'] == [('reset_poweroptions_timer', 1, 1, 0)], 'a download thread beside a job: kept awake (the job does not matter)')
    # screen off: the same call, no widget work; in the background too
    m = page(); open_sub_one(m)
    PCP.act(m, 0)
    m.screen(False); m.calls = []
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect([c[0] for c in m.calls if c[0] == 'reset_poweroptions_timer'] == ['reset_poweroptions_timer'] and not [c for c in m.calls if c[0].startswith(('widget', 'canvas', 'grid', 'label', 'toast'))],
           'screen off: the call is made, nothing visual is touched')
    fn_, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]
    m.calls = []; m.call(fn_, a0=ctx_, a1=0, count=4000000)
    m.calls = []
    r = m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(r == O['RET_REPEAT'] and [c[0] for c in m.calls if c[0] == 'reset_poweroptions_timer'], 'in the background the downloads timer keeps going (the window still exists)')
    expect(m.props.get((m.widgets['pod_pd_scrim'], 'visible'), 0) == 0, 'no dialog')
    # destroy: its timer goes, the download goes on
    m2 = page(); open_sub_one(m2)
    m2.calls = []; fn_, ctx_ = m2.bound[(m2.window, O['EVT_DESTROY'])]; m2.call(fn_, a0=ctx_, a1=0, count=4000000)
    n0 = len([c for c in m2.calls if c[0] == 'timer_remove'])
    m2 = page(); open_sub_one(m2); PCP.act(m2, 0)
    m2.calls = []; fn_, ctx_ = m2.bound[(m2.window, O['EVT_DESTROY'])]; m2.call(fn_, a0=ctx_, a1=0, count=4000000)
    n1 = len([c for c in m2.calls if c[0] == 'timer_remove'])
    expect(n1 == n0 + 1 and fn(m2, 'pn_dl_count') == 1 and fn(m2, 'pn_dl_running') == 1, 'destroying the window removes the downloads timer and nothing else is done: the queue and the thread are left alone (the device may sleep; the next start resumes from the .part)')
    m2.calls = []
    expect(m2.call(PSYMS['podcasts_open'], count=40000000) == 0 and ('timer_add', PSYMS['pg_awake_tick'], 1000) in m2.calls, 'opening the page again while a download is queued arms the timer')
    # one hook per download timer: no global timer, no hook (this payload adds only the page's timer)
    expect(sum(1 for c in m2.calls if c[0] == 'timer_add' and c[1] == PSYMS['pg_awake_tick']) == 1, 'exactly one downloads timer')


def width_tests(ctx):
    """The state lines in every language, in the real font: the room is the 274 px of a row's grey line (PG_TEXT_W)."""
    expect = ctx.expect
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))
    st = StbText(font, O['LIST_SUB_PX'] if 'LIST_SUB_PX' in O else 18)
    reasons = ["No Wi-Fi", "Set the date first", "Certificates missing", "Certificate problem", "Can't connect", "Not found", "Server error", "Storage unavailable", "Card is full", "Not audio"]
    worst = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, t=t: pod_i18n.TEXT[key][t]
        cands = {'Downloading 100%': f'{tr("Downloading")} 100%', 'Downloading 9999 MB': f'{tr("Downloading")} 9999 MB', 'Waiting': tr('Waiting'), 'Paused': tr('Paused')}
        cands.update({f'Failed: {r}': f'{tr("Failed")}: {tr(r)}' for r in reasons})
        w = {k: round(st.layout(v)[1]) for k, v in cands.items()}
        top = max(w, key=w.get)
        worst.append((loc, w[top], top))
        title_w = round(st.layout(f'{tr("Downloaded")} (32)')[1])
        expect(title_w <= 274 - 0, f'{loc}: the Downloads row title fits ({title_w})')
    print('  widest state line a language needs (px, room 274):', [(a, b) for a, b, _ in worst])
    over = [(loc, w, k) for loc, w, k in worst if w > 274]
    expect(not over, f'every state line fits 274 px in every language ({over})')


SECTIONS = [queue_tests, transfer_tests, resume_tests, failure_tests, control_tests, sweep_tests, refresh_tests, page_tests, refresh_page_tests, awake_tests, width_tests]

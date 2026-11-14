"""Navidrome downloads (patch/sbdl.c, docs/modules/subsonic.md "Data and cache"): the queue and its guards, the worker (one detached thread, one file at a time), progress and the
generation counter, the .part file and the Range resume, the stall limit and the free-space floor (sbnet's options), a file that is on the card already (never overwritten), the
manifest dl.idx (written atomically, read back offline, dropped when a file was deleted by hand), delete, the folder layout (artist/album/file), the waiting queue the card keeps
(dlq.idx: a reboot, the stop at a lost Wi-Fi, the resume), and the library scan of a finished album's folder. The compiled payload runs
under Unicorn against a scripted libcurl (no network); the card is a dict of paths. sbapi.c's real guard and login run (the conf file, Wi-Fi level and card state are set up, not a forced answer)."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


PCN = sibling('pcnet')
SA = sibling('sbapi')
SBA = dict(OK=0, NOCONF=1, NOWIFI=2, NOCLOCK=3, NOCERT=4, CERT=5, NET=6, AUTH=7, NOTFOUND=8, HTTP=9, PARSE=10, STORAGE=11, MEM=12, QFULL=13, CARDFULL=14, NOTAUDIO=15, WRITE=16, CANCELLED=17)
DL = dict(NONE=0, WAIT=1, ACTIVE=2, DONE=3, FAILED=4)
MUSIC, IDX, QUEUE = '/mnt/mmc/Subsonic', '/mnt/mmc/.m1plus/subsonic/dl.idx', '/mnt/mmc/.m1plus/subsonic/dlq.idx'
ALBUM_DIR = MUSIC + '/An Artist/An Album'
TRACK = struct.Struct('<64s192s192s192s64s64s12s9IB3x')
SIZE = TRACK.size
assert SIZE == 820


DATA = body(1300000)


def name_of(t, variant=0, artist=None):
    """The file of a track under MUSIC: <artist>/<album>/<nn> <title>.<suffix> (patch/sbdl.c sbd_file_name)."""
    num = (f'{t["disc"]}-' if t['disc'] > 1 else '') + f'{t["track"]:02d} ' if t['track'] else ''
    return f'{artist or t["artist"]}/{t["album"]}/{num}{t["title"].replace("/", "_")}' + (f' ({variant + 1})' if variant else '') + '.' + t['suffix']


def queued(m):
    """The track ids dlq.idx holds, in order."""
    return [line.split('\t')[0][2:] for line in m.fs.get(QUEUE, b'').decode().split('\n') if line.startswith('i=')]


def resume(m):
    """sba_dl_resume on the UI thread: (the number waiting, the thread it started)."""
    m.thread = None
    r = m.call(PSYMS['sba_dl_resume'], count=1 << 40)
    return r, m.thread


def reboot(m, site=None):
    """A new machine with the same card: nothing of the queue or the manifest is in memory."""
    n = machine(site)
    n.fs.update(m.fs); n.dirs.update(m.dirs); n.present.update(m.present)
    if site is None: n.curl_site = server(n)
    return n


def track(i='tr-1', title='Song One', suffix='flac', size=len(DATA), **kw):
    return dict(id=i, title=title, artist='An Artist', album='An Album', album_id='al-1', cover='cv-1', suffix=suffix, seconds=245, track=3, disc=1, year=2020, size=size,
                bitrate=900, sample_rate=44100, bit_depth=16, created=1700000000, starred=1, **kw)


def pack(t):
    return TRACK.pack(t['id'].encode(), t['title'].encode(), t['artist'].encode(), t['album'].encode(), t['album_id'].encode(), t['cover'].encode(), t['suffix'].encode(),
                      t['seconds'], t['track'], t['disc'], t['year'], t['size'], t['bitrate'], t['sample_rate'], t['bit_depth'], t['created'], t['starred'])


def unpack(raw):
    f = TRACK.unpack(raw)
    z = lambda b: b.split(b'\0')[0].decode()
    keys = ('seconds', 'track', 'disc', 'year', 'size', 'bitrate', 'sample_rate', 'bit_depth', 'created', 'starred')
    return dict(id=z(f[0]), title=z(f[1]), artist=z(f[2]), album=z(f[3]), album_id=z(f[4]), cover=z(f[5]), suffix=z(f[6]), **dict(zip(keys, f[7:])))


class DM(PCN.NM):
    """The card machine plus stock's library scan (scanSpecFolder), which the worker calls after a DSD file."""
    scans = ()
    on_step = None   # sweep_tests: called with the name before each card call of STEP_CALLS (a place where the UI thread may run between two steps of the worker)
    STEP_CALLS = frozenset(('open', 'write', 'rename', 'unlink', 'statfs', 'fsync', 'scanSpecFolder'))

    def _hook(self, u, address, size, _):
        if self.on_step and self.handlers.get(address, '') in self.STEP_CALLS: self.on_step(self.handlers[address])
        if self.handlers.get(address, '') == 'scanSpecFolder':
            a0, a1 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1))
            self.scans = (*self.scans, (self.read_cstr(a0), a1))
            if getattr(self, 'on_scan', None): self.on_scan()   # a test's way to act after a transfer's answer, before the worker has handled it (the scan before a pause)
            u.reg_write(UC_MIPS_REG_V0, 1); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if self.handlers.get(address, '') == 'snprintf' and self.read_cstr(u.reg_read(UC_MIPS_REG_A2)) == '%lld-':   # sbnet's Range text: the 64-bit offset is in the stack words after a3's padding
            sp = u.reg_read(UC_MIPS_REG_SP)
            lo, hi = struct.unpack('<II', bytes(u.mem_read(sp + 16, 8)))
            text = f'{lo | hi << 32}-'.encode()
            u.mem_write(u.reg_read(UC_MIPS_REG_A0), text + b'\0')
            u.reg_write(UC_MIPS_REG_V0, len(text)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


ETAG = '"v1"'


def reply_head(m, o, code, ctype=None, etag=None, lines=()):
    """The header lines libcurl hands the payload for one response: the status line, Content-Type, ETag, the extra lines and the blank line that ends them."""
    def head(text):
        buf = m.alloc(len(text) + 1)
        m.u.mem_write(buf, text.encode())
        m.nested(o[20079], buf, 1, len(text), o[10029])
    head(f'HTTP/1.1 {code} X\r\n')
    if ctype: head(f'Content-Type: {ctype}\r\n')
    if etag: head(f'ETag: {etag}\r\n')
    for line in lines: head(line + '\r\n')
    head('\r\n')


def server(m, data=DATA, log=None, honour=True, ctype='audio/mpeg', chunk=65536, etag=ETAG, range_etag=None, bad_range=None, **extra):
    """A scripted download server: Range answered with 206 and a Content-Range header (honour) or ignored with 200; an If-Range that is not the ETag gets the whole file (200). log gets
    (url, start, options + 'if_range'); etag is sent on every answer (None: none); range_etag the ETag of a 206 when it differs; bad_range replaces the Content-Range value."""
    def site(url, o):
        rng = o.get(10007)
        start = int(rng.rstrip('-')) if rng else 0
        if_range = m.read_cstr(m.word(o[10023])) if o.get(10023) else None
        if log is not None: log.append((url, start, dict(o, if_range=if_range)))
        if start and honour and (if_range is None or if_range == f'If-Range: {etag}'):
            reply_head(m, o, 206, ctype, range_etag or etag, [f'Content-Range: bytes {bad_range or f"{start}-{len(data) - 1}/{len(data)}"}'])
            return {'chunk': chunk, 'ctype': ctype, 'code': 206, 'body': data[start:], 'length': len(data) - start, **extra}
        reply_head(m, o, 200, ctype, etag)
        return {'chunk': chunk, 'ctype': ctype, 'code': 200, 'body': data, 'length': len(data), **extra}
    return site


def part_record(m, final, etag=ETAG, track_id='tr-1'):
    """The resume record sbnet saves next to a .part file (<part>.etag): magic, the identity (server, user, track) and the ETag."""
    ident = f'http://nd.example:4533\nalice\n{track_id}'.encode()
    m.put(f'{final}.part.etag', b'SBRES1\0\0' + ident.ljust(544, b'\0') + etag.encode().ljust(128, b'\0'))


def machine(site=None, **kw):
    m = DM()
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(PCN.CA)
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    m.put('/mnt/mmc/.m1plus/subsonic.conf', b'http://nd.example:4533|alice|secret')
    m.curl_site = site or (lambda url, o: {'rc': 6})
    for k, v in kw.items(): setattr(m, k, v)
    return m


def guard(m, code):
    """Put the conditions sbapi.c's real sba_guard checks into the state it answers `code` for (0, NOWIFI or NOCONF; a missing card is set by the caller)."""
    m.card_mounted = True
    m.wifi = -1 if code == SBA['NOWIFI'] else 4
    configured = m.call(PSYMS['sba_configured'], count=2000000)
    if code == SBA['NOCONF']:
        if configured: m.call(PSYMS['sba_conf_clear'], count=1 << 40)
    elif not configured:
        for fnm, v in (('sba_conf_url_set', 'http://nd.example:4533'), ('sba_conf_user_set', 'alice'), ('sba_conf_password_set', 'secret')):
            assert m.call(PSYMS[fnm], a0=m.cstr(v), count=2000000) == 0


def add(m, t):
    """sba_dl_add on the UI thread: (result, the thread it started)."""
    m.thread = None
    buf = m.alloc(SIZE)
    m.u.mem_write(buf, pack(t))
    r = m.call(PSYMS['sba_dl_add'], a0=buf, count=1 << 40)
    return r, m.thread


def state(m, i='tr-1', inside=False):
    """(state, code, got, total); inside: from a libcurl callback (the payload is mid-call there: nested, not a new call)."""
    code, got, total = m.alloc(4), m.alloc(4), m.alloc(4)
    args = (m.cstr(i), code, got, total)
    st = m.nested(PSYMS['sba_dl_state'], *args) if inside else m.call(PSYMS['sba_dl_state'], a0=args[0], a1=code, a2=got, a3=total, count=2000000)
    return st, m.word(code), m.word(got), m.word(total)


def take(m):
    """The worker takes the messages the UI thread posted, as it does at the top of its loop and inside a transfer (patch/sbdl.c sbd_drain). For a worker that was started and has not run yet."""
    m.call(PSYMS['sbd_drain'], count=1 << 40)


def failure(m):
    """sba_dl_failure: (the code nobody was told of yet, its HTTP status). Taking it clears it."""
    status = m.alloc(4)
    code = m.call(PSYMS['sba_dl_failure'], a0=status, count=2000000)
    return code, m.word(status)


def fn(m, name, **kw): return m.call(PSYMS[name], count=2000000, **kw)


def cancel(m, i):
    """sba_dl_cancel on the UI thread: (result, the thread it started: none while a worker runs)."""
    m.thread = None
    r = m.call(PSYMS['sba_dl_cancel'], a0=m.cstr(i), count=2000000)
    return r, m.thread


def path_of(m, i='tr-1'):
    buf = m.alloc(256)
    r = m.call(PSYMS['sba_dl_path'], a0=m.cstr(i), a1=buf, a2=256, count=2000000)
    return m.read_cstr(buf) if r else None


def listing(m):
    out = m.alloc(8)
    n = m.call(PSYMS['sba_downloaded'], a0=out, count=1 << 40)
    v = m.word(out + 4)
    assert n == m.word(out)
    return [unpack(bytes(m.u.mem_read(v + i * SIZE, SIZE))) for i in range(n)]


def waiting(m):
    """sba_dl_queue: the tracks still to come, as rows."""
    out = m.alloc(8)
    n = m.call(PSYMS['sba_dl_queue'], a0=out, count=1 << 40)
    v = m.word(out + 4)
    assert n == m.word(out)
    return [unpack(bytes(m.u.mem_read(v + i * SIZE, SIZE))) for i in range(n)]


def sleeps(calls): return [c for c in calls if c[0] == 'sleep']


def queue_tests(ctx):
    """sba_dl_add: guards, free space, duplicates, the order, the cap, one worker."""
    expect = ctx.expect
    m = machine()
    m.curl_site = server(m)
    for msg, setup, want in (('no Wi-Fi', lambda: guard(m, SBA['NOWIFI']), 'NOWIFI'), ('no server saved', lambda: guard(m, SBA['NOCONF']), 'NOCONF'),
                             ('no card', lambda: setattr(m, 'card_mounted', False), 'STORAGE')):
        guard(m, 0); m.card_mounted = True
        setup()
        r, th = add(m, track())
        expect(r == SBA[want] and th is None and state(m)[0] == DL['NONE'] and not fn(m, 'sba_dl_busy'), f'{msg}: sba_dl_add says {want}, nothing queued, no thread')
    guard(m, 0); m.card_mounted = True
    m.free_mb = 32
    r, th = add(m, track('c1', size=0))
    expect(r == SBA['CARDFULL'] and th is None, 'a card with only the 32 MB reserve free takes no download: SBA_CARDFULL')
    m.free_mb = 36
    r, th = add(m, track('c2', size=5 << 20))
    expect(r == SBA['CARDFULL'] and th is None, 'a 5 MB track on a card with 36 MB free would eat into the 32 MB reserve: SBA_CARDFULL')
    m.free_mb = 1024
    r, th = add(m, track())
    names = [c[0] for c in m.calls]
    expect(r == 0 and th and names.count('pthread_create') == 1 and names.count('pthread_detach') == 1, 'a download starts one detached worker')
    expect(state(m)[0] == DL['WAIT'] and fn(m, 'sba_dl_busy') == 1, 'queued and waiting; the worker is marked busy')
    g0 = fn(m, 'sba_dl_gen')
    r2, th2 = add(m, track())
    expect(r2 == 0 and th2 is None, 'the same track again: left as it is, no second worker')
    r3, th3 = add(m, track('tr-2', 'Song Two'))
    expect(r3 == 0 and th3 is None and state(m, 'tr-2')[0] == DL['WAIT'], 'another track while the worker is busy: queued, no second thread')
    expect(fn(m, 'sba_dl_gen') != g0, 'the generation moved when the queue changed')
    calls = work(m, th)
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(len(reqs) == 2 and 'id=tr-1' in reqs[0] and 'id=tr-2' in reqs[1] and all('/rest/download.view?' in u for u in reqs), f'one file at a time, in the order asked ({reqs})')
    expect(state(m)[0] == DL['DONE'] and state(m, 'tr-2')[0] == DL['DONE'] and not fn(m, 'sba_dl_busy'), 'both done; the worker ended')
    m.thread = None
    r, th = add(m, track())
    expect(r == 0 and th is None and state(m)[0] == DL['DONE'], 'a track already on the card: SBA_OK and DONE, no worker')
    # the cap: 1024 waiting or running (1022 come from the card's queue file, as after a reboot)
    m = machine(); m.curl_site = server(m)
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    m.put(QUEUE, ''.join(f'i=q{k}\tt=q{k}\tx=flac\tp=\n' for k in range(1022)).encode())
    r, th = add(m, track('t0', 't0'))
    expect(r == 0 and th and state(m, 'q0')[0] == DL['WAIT'] and state(m, 'q1021')[0] == DL['WAIT'], 'the rows the card kept wait again; an add starts the worker for all of them')
    r, _ = add(m, track('t1', 't1'))
    expect(r == 0, 'the queue holds 1024')
    r, _ = add(m, track('t2', 't2'))
    expect(r == SBA['QFULL'] and state(m, 't2')[0] == DL['NONE'] and 't2' not in queued(m), 'the 1025th: SBA_QFULL, nothing written')
    # a thread that cannot be made
    m = machine(thread_ok=False)
    r, th = add(m, track())
    expect(r == SBA['MEM'] and state(m)[0] == DL['NONE'] and not fn(m, 'sba_dl_busy'), 'no thread: SBA_MEM, not queued, not busy')
    # the card refuses the queue file
    m = machine(); m.fail.add(('open', QUEUE))
    r, th = add(m, track())
    shown = state(m)[0]
    calls = work(m, th)
    expect(r == 0 and shown == DL['WAIT'] and state(m)[0] == DL['NONE'] and failure(m) == (SBA['STORAGE'], 0) and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy'),
           f'a queue row the card does not take: the add is posted, the worker finds out, the track is not queued and the page is told SBA_STORAGE ({r}, {shown})')
    # a track without an id
    r, th = add(m, track(''))
    expect(r == SBA['PARSE'] and th is None, 'a track with no id is refused')


def cap_tests(ctx):
    """A full queue (1024) with messages in the box: what the UI thread answers by itself and what it leaves to the worker (patch/sbdl.c sbd_room). Slow: a queue file of 1024 rows is rewritten twice."""
    expect = ctx.expect
    # a track that has its slot and a message in the box at once (asked twice; or the worker is at its row) is one track, not two
    m = machine(); m.curl_site = server(m)
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    m.put(QUEUE, ''.join(f'i=q{k}\tt=q{k}\tx=flac\tp=\n' for k in range(1022)).encode())
    add(m, track('t0', 't0')); take(m)
    r0, _ = add(m, track('t0', 't0')); ra, _ = add(m, track('t1', 't1')); rb, _ = add(m, track('t1', 't1')); r2, _ = add(m, track('t2', 't2'))
    expect((r0, ra, rb, r2) == (0, 0, 0, SBA['QFULL']), f'1023 queued, one of them asked again: the 1024th still fits (also asked twice), the 1025th does not ({r0}, {ra}, {rb}, {r2})')
    # full, one cancelled and added again before the worker has taken the cancel: it needs no new place
    take(m)
    rc, _ = cancel(m, 'q5'); r5, _ = add(m, track('q5', 'q5'))
    expect((rc, r5) == (0, 0) and state(m, 'q5')[0] == DL['WAIT'], f'a full queue, a track cancelled and asked again at once: taken ({rc}, {r5})')
    take(m)
    expect(state(m, 'q5')[0] == DL['WAIT'] and state(m, 't1')[0] == DL['WAIT'] and failure(m) == (0, 0) and fn(m, 'sba_dl_pending') == 1024, 'and it waits, with the other 1023')
    # with a cancel in the box the UI thread cannot count: the add is posted and the worker says what did not fit
    cancel(m, 'q6'); r8, _ = add(m, track('t8', 't8')); r9, _ = add(m, track('t9', 't9'))
    take(m)
    expect((r8, r9) == (0, 0) and state(m, 't8')[0] == DL['WAIT'] and state(m, 't9')[0] == DL['NONE'] and failure(m) == (SBA['QFULL'], 0) and 't9' not in queued(m),
           f'one place freed, two tracks asked: the first has it, the second is refused by the worker (SBA_QFULL through sba_dl_failure) ({r8}, {r9})')


def transfer_tests(ctx):
    """One download: the request, the file, the manifest, progress, the generation."""
    expect = ctx.expect
    m = machine(); log = []
    m.curl_site = server(m, log=log)
    t = track()
    final = f'{MUSIC}/{name_of(t)}'
    states, gens = [], []

    def tick(url, sent, total):
        st, _, got, tot = state(m, inside=True)
        states.append((sent, st, got, tot)); gens.append(m.nested(PSYMS['sba_dl_gen']))
    # the callback runs before the payload's own, so a state read at call k shows call k-1's numbers
    site = m.curl_site
    m.curl_site = lambda url, o: dict(site(url, o), xfer=tick)
    r, th = add(m, t)
    calls = work(m, th)
    o = log[0][2]
    expect(o[10002].startswith('http://nd.example:4533/rest/download.view?u=alice&t=') and '&id=tr-1&' in o[10002] + '&' or '&id=tr-1' in o[10002], 'the request is the authenticated download.view of the track id')
    expect('secret' not in o[10002], 'the password is not in the URL')
    expect(not o.get(10007), 'no Range on a fresh download')
    expect(o.get(19) == 512 and o.get(20) == 45 and o.get(10065) == PCN.CA and o.get(64, 1) == 1 and o.get(81, 2) == 2, 'sbnet\'s stall limit (512 B/s for 45 s), CA bundle and verification are on')
    expect(64 not in o and 81 not in o and o[99] == 1 and o[52] == 1 and o[68] == 5 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[78] == 12 and o[10018].startswith('M1PlusMusic/') and o.get(10102) is None,
           'the request is made by the shared layer (patch/net.c): verification left at libcurl\'s defaults, no signals, 5 hops to http(s), an HTTP error fails, the app\'s user agent, no Accept-Encoding')
    expect(m.fs.get(final) == DATA and f'{final}.part' not in m.fs, 'the file is complete under its name (<artist>/<album>/<nn> <title>.<suffix>) and the .part file is gone')
    expect(final == ALBUM_DIR + '/03 Song One.flac' and [c[1] for c in calls if c[0] == 'mkdir' and c[1].startswith(MUSIC)] == [MUSIC, MUSIC + '/An Artist', ALBUM_DIR],
           f'the artist and album folders are made for it ({final})')
    expect(('rename', f'{final}.part', final) in calls, 'finished by a rename of the .part file')
    seen = [s for s in states if s[1] == DL['ACTIVE']]
    expect(seen and seen[-1][3] == len(DATA) and all(s[2] <= s[0] for s in seen), 'while it runs the state is ACTIVE with the bytes got and the size the server gave')
    expect(len(set(gens)) > 10 and len(set(gens)) <= 60, f'the generation moves about every 2 % ({len(set(gens))} values over 1.3 MB)')
    st, code, got, total = state(m)
    expect((st, got, total) == (DL['DONE'], len(DATA), len(DATA)), 'afterwards DONE with the file size')
    expect(path_of(m) == final, 'sba_dl_path is the file')
    text = m.fs[IDX].decode()
    expect(text.startswith('M1PLUS-DL 1\n') and text.count('\n') == 2 and f'p={name_of(t)}' in text and f'w={len(DATA)}' in text, 'dl.idx has the head line and one row with the file name and size')
    expect(not [p for p in m.fs if p.endswith('.tmp')], 'no temp file is left')
    rows = listing(m)
    expect(rows == [t], f'sba_downloaded returns the whole track row ({rows})')
    # offline: a fresh start (the memory copy forgotten) reads the same
    fs, dirs = dict(m.fs), set(m.dirs)
    m = machine(); m.fs.update(fs); m.dirs.update(dirs)   # (a new machine: nothing of dl.idx is in memory)
    m.wifi = -1; guard(m, SBA['NOWIFI'])
    expect(state(m)[0] == DL['DONE'] and listing(m) == [t] and path_of(m) == final, 'with Wi-Fi off and a fresh read of dl.idx: still Downloaded, listed and playable')
    # the length unknown: the size is 0 until the end
    m = machine()
    st = []
    s0 = server(m)
    m.curl_site = lambda url, o: dict(s0(url, o), length=0, clen=-1, xfer=lambda u, s, tt: st.append(state(m, inside=True)[2:]))
    r, th = add(m, t); work(m, th)
    expect(st and all(x[1] == 0 for x in st[:-1]), 'a server that gives no length: total 0 (unknown) while it runs')
    expect(m.fs.get(final) == DATA, 'and the file is still complete')


def resume_tests(ctx):
    """A .part file is continued with a Range request; a server that ignores Range starts over."""
    expect = ctx.expect
    t = track()
    final = f'{MUSIC}/{name_of(t)}'
    m = machine(); log = []
    m.curl_site = server(m, log=log)
    m.put(f'{final}.part', DATA[:400000]); part_record(m, final)
    firsts = []
    s0 = m.curl_site
    m.curl_site = lambda url, o: dict(s0(url, o), xfer=lambda u, s, tt: firsts.append(state(m, inside=True)[2]) if len(firsts) < 3 else None)
    r, th = add(m, t); work(m, th)
    expect(log and log[0][1] == 400000 and log[0][2][10007] == '400000-', 'the request resumes at the size of the .part file (Range: 400000-)')
    expect(m.fs.get(final) == DATA, 'the finished file is the whole thing, no byte repeated or lost')
    expect(firsts[-1] >= 400000, f'progress counts the bytes already on the card ({firsts})')
    # the server answers 200 to the Range: the file starts again
    m = machine(); log = []
    m.curl_site = server(m, log=log, honour=False)
    m.put(f'{final}.part', DATA[:400000]); part_record(m, final)
    r, th = add(m, t); work(m, th)
    expect(len(log) == 2 and log[0][1] == 400000 and log[1][1] == 0 and m.fs.get(final) == DATA, 'a server that ignores Range (200): the request is repeated from the start and the file is whole')
    # a failure part-way keeps the .part for the next try
    m = machine()
    base = server(m)
    m.curl_site = lambda url, o: dict(base(url, o), body=DATA[:300000], partial=True, rc=28, code=200)
    r, th = add(m, t); work(m, th)
    st, code, _, _ = state(m)
    expect(st == DL['FAILED'] and code == SBA['NET'] and len(m.fs.get(f'{final}.part', b'')) == 300000 and final not in m.fs, 'a time-out after 300 KB: FAILED (network), the .part file kept')
    m.curl_site = server(m)
    r, th = add(m, t)
    expect(r == 0 and th and state(m)[0] == DL['WAIT'], 'asked again, a failed track is queued again (not stuck failed)')
    log = []
    m.curl_site = server(m, log=log); work(m, th)
    expect(log[0][1] == 300000 and m.fs.get(final) == DATA and state(m)[0] == DL['DONE'], 'and it continues at 300000')
    # a resume answered 503 (no body written) keeps the .part and its record; the next try resumes at the same offset
    m = machine()
    m.put(f'{final}.part', DATA[:400000]); part_record(m, final)
    rec = m.fs[f'{final}.part.etag']
    m.curl_site = lambda url, o: (reply_head(m, o, 503), dict(rc=22, code=503, body=b'', length=0))[1]
    r, th = add(m, t); work(m, th)
    expect(state(m)[0] == DL['FAILED'] and m.fs.get(f'{final}.part') == DATA[:400000] and m.fs.get(f'{final}.part.etag') == rec, 'a resume answered 503: FAILED, the .part and its record stay as they were')
    log = []
    m.curl_site = server(m, log=log)
    r, th = add(m, t); work(m, th)
    expect(log and log[0][1] == 400000 and m.fs.get(final) == DATA, 'the next attempt resumes at the same offset and finishes')


def validator_tests(ctx):
    """Safe resume: a Range only with a strong ETag recorded for this track (If-Range), a 206 accepted only for exactly the missing bytes with the same ETag, else the file starts again."""
    expect = ctx.expect
    t = track()
    final = f'{MUSIC}/{name_of(t)}'

    def run(setup=None, **kw):
        m = machine(); log = []
        m.curl_site = server(m, log=log, **kw)
        m.put(f'{final}.part', DATA[:400000])
        if setup: setup(m)
        r, th = add(m, t); work(m, th)
        return m, log

    m, log = run(lambda m: part_record(m, final))
    expect(log[0][1] == 400000 and log[0][2]['if_range'] == f'If-Range: {ETAG}' and m.fs.get(final) == DATA and f'{final}.part.etag' not in m.fs,
           f'a strong ETag on record: Range 400000- with If-Range {ETAG}, the file whole, the record gone ({[(x[1], x[2]["if_range"]) for x in log]})')
    expect(len(log) == 1, 'and one request is enough')
    m, log = run()
    expect(log[0][1] == 0 and log[0][2]['if_range'] is None and len(log) == 1 and m.fs.get(final) == DATA, 'a .part file with no record: no Range, the file starts again')
    m, log = run(lambda m: part_record(m, final, track_id='other'))
    expect(log[0][1] == 0 and m.fs.get(final) == DATA, 'a record for another track: no Range, the file starts again')
    m, log = run(lambda m: part_record(m, final, etag='W/"v1"'))
    expect(log[0][1] == 0 and m.fs.get(final) == DATA, 'a weak ETag in the record is not a validator: no Range')
    m, log = run(lambda m: part_record(m, final, etag='"v0"'))
    expect(len(log) == 2 and log[0][1] == 400000 and log[0][2]['if_range'] == 'If-Range: "v0"' and log[1][1] == 0 and m.fs.get(final) == DATA and f'{final}.part.etag' not in m.fs,
           'the file changed on the server (If-Range not matched, 200): asked again from the start, the file whole')
    # a 206 that does not fit the saved bytes starts the file again
    for msg, kw in (('another start', dict(bad_range=f'1000-{len(DATA) - 1}/{len(DATA)}')), ('an end short of the file', dict(bad_range=f'400000-{len(DATA) - 2}/{len(DATA)}')),
                    ('no total', dict(bad_range='400000-1299999/*')), ('another ETag', dict(range_etag='"v2"')), ('no ETag', dict(range_etag='W/"x"'))):
        m, log = run(lambda m: part_record(m, final), **kw)
        expect(len(log) == 2 and log[0][1] == 400000 and log[1][1] == 0 and m.fs.get(final) == DATA, f'a 206 with {msg}: not appended, asked again from the start, the file whole ({[x[1] for x in log]})')
    # a text type is never audio, whatever the status
    m, log = run(lambda m: part_record(m, final), ctype='text/html')
    st, code, _, _ = state(m)
    expect((st, code) == (DL['FAILED'], SBA['NOTAUDIO']) and final not in m.fs and f'{final}.part' not in m.fs and f'{final}.part.etag' not in m.fs, 'a resumed answer of text/html: FAILED (not audio), no file, no .part, no record')
    m, log = run(ctype='application/json; charset=utf-8')
    expect(state(m)[:2] == (DL['FAILED'], SBA['NOTAUDIO']) and final not in m.fs, 'application/json with a charset is text too')
    # the record is saved with the first body byte; a failure after it keeps the .part for a resume
    m = machine(); log = []
    base = server(m, log=log)
    m.curl_site = lambda url, o: dict(base(url, o), body=DATA[:300000], partial=True, rc=28, code=200)
    r, th = add(m, t); work(m, th)
    rec = m.fs.get(f'{final}.part.etag', b'')
    expect(len(m.fs.get(f'{final}.part', b'')) == 300000 and rec[:8] == b'SBRES1\0\0' and rec[8:8 + len(b'http://nd.example:4533\nalice\ntr-1')] == b'http://nd.example:4533\nalice\ntr-1' and rec[552:552 + 4] == b'"v1"',
           'a time-out after 300 KB: the .part file and a record (identity, ETag) are kept')
    m.curl_site = server(m, log=(log := []))
    r, th = add(m, t); work(m, th)
    expect(log[0][1] == 300000 and log[0][2]['if_range'] == f'If-Range: {ETAG}' and m.fs.get(final) == DATA, 'and the next try continues at 300000 under If-Range')
    # no usable ETag: nothing is kept after a failure
    for msg, etag in (('a weak ETag', 'W/"v1"'), ('no ETag', None), ('an unquoted ETag', 'v1')):
        m = machine()
        base = server(m, etag=etag)
        m.curl_site = lambda url, o: dict(base(url, o), body=DATA[:300000], partial=True, rc=28, code=200)
        r, th = add(m, t); work(m, th)
        expect(state(m)[:2] == (DL['FAILED'], SBA['NET']) and f'{final}.part' not in m.fs and f'{final}.part.etag' not in m.fs, f'{msg}: a failure part-way keeps no .part (it could not be resumed safely)')
    m = machine()
    m.curl_site = server(m, etag=None)
    r, th = add(m, t); work(m, th)
    expect(m.fs.get(final) == DATA, 'a server without ETags still delivers the whole file')
    # deleting the track removes its leftovers
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t); work(m, th)
    m.put(f'{final}.part', b'x'); part_record(m, final)
    m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-1'), count=1 << 40)
    expect(final not in m.fs and f'{final}.part' not in m.fs and f'{final}.part.etag' not in m.fs, 'Remove Download drops the .part file and its record too')


def report_tests(ctx):
    """The failure codes the card side and the server give, and sba_dl_failure (what a page is told once)."""
    expect = ctx.expect
    t = track()
    final = f'{MUSIC}/{name_of(t)}'

    m = machine(); m.curl_site = server(m); m.fail.add(('write', f'{final}.part'))
    r, th = add(m, t); work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['WRITE']) and f'{final}.part' not in m.fs, 'a write the card refuses: FAILED, SBA_WRITE (not "storage" or "network"), no .part')
    expect(failure(m) == (SBA['WRITE'], 0) and failure(m)[0] == 0, 'sba_dl_failure tells it once, then nothing')
    m = machine(); m.curl_site = lambda url, o: (reply_head(m, o, 503), dict(rc=22, code=503, body=b'', length=0))[1]
    r, th = add(m, t); work(m, th)
    expect(failure(m) == (SBA['HTTP'], 503), 'an HTTP 503: SBA_HTTP with the status 503')
    m = machine(); m.curl_site = lambda url, o: (reply_head(m, o, 404), dict(rc=22, code=404, body=b'', length=0))[1]
    r, th = add(m, t); work(m, th)
    expect(failure(m) == (SBA['NOTFOUND'], 0), 'HTTP 404: SBA_NOTFOUND')
    m = machine(); m.curl_site = server(m, ctype='text/html')
    r, th = add(m, t); work(m, th)
    expect(failure(m)[0] == SBA['NOTAUDIO'], 'a page instead of the file: SBA_NOTAUDIO')
    m = machine(); m.curl_site = server(m, length=1000)   # (announced length that the body does not match)
    base = m.curl_site
    m.curl_site = lambda url, o: dict(base(url, o), body=DATA[:1000], length=len(DATA))
    r, th = add(m, t); work(m, th)
    expect(failure(m)[0] == SBA['NOTAUDIO'] and final not in m.fs, 'fewer bytes than announced, no error from libcurl: SBA_NOTAUDIO (an unreadable answer), nothing kept as the file')
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t); work(m, th)
    expect(failure(m)[0] == 0, 'a download that worked leaves nothing to tell')
    m = machine(); m.curl_site = lambda url, o: dict(rc=7, code=0, body=b'', length=0)
    r, th = add(m, t); work(m, th)
    m.wall += 100
    expect(failure(m)[0] == 0, 'a failure nobody asked about for over 30 s is not news')


def failure_tests(ctx):
    """What goes wrong, and the words the page shows."""
    expect = ctx.expect
    t = track()
    final = f'{MUSIC}/{name_of(t)}'
    cases = (('HTTP 404', dict(rc=22, code=404, body=b''), 'NOTFOUND'), ('HTTP 401', dict(rc=22, code=401, body=b''), 'AUTH'), ('HTTP 500', dict(rc=22, code=500, body=b''), 'HTTP'),
             ('a refused certificate', dict(rc=60, code=0, body=b''), 'CERT'), ('no connection', dict(rc=7, code=0, body=b''), 'NET'),
             ('a web page', dict(ctype='text/html', code=200, body=b'<html>login</html>', rc=0), 'NOTAUDIO'),
             ('a JSON error answer', dict(ctype='application/json', code=200, body=b'{"subsonic-response":{"status":"failed"}}', rc=0), 'NOTAUDIO'))
    for msg, kw, want in cases:
        m = machine(); m.curl_site = lambda url, o, kw=kw: (reply_head(m, o, kw['code'], kw.get('ctype', 'audio/mpeg'), ETAG), {'chunk': 65536, 'ctype': 'audio/mpeg', 'length': len(kw['body']), **kw})[1]
        r, th = add(m, t); work(m, th)
        st, code, _, _ = state(m)
        expect((st, code) == (DL['FAILED'], SBA[want]) and final not in m.fs and f'{final}.part' not in m.fs, f'{msg}: FAILED with SBA_{want}, no file and no .part')
    m = machine(); m.curl_site = server(m)
    guard(m, 0)
    r, th = add(m, t)
    guard(m, SBA['NOWIFI'])
    calls = work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['NOWIFI']) and 'curl_perform' not in [c[0] for c in calls], 'Wi-Fi lost before the worker got to it: FAILED with the guard\'s words, no request')
    expect(queued(m) == ['tr-1'] and not fn(m, 'sba_dl_busy'), 'its row stays on the card for a later start')
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t)
    m.free_mb = 20
    calls = work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['CARDFULL']) and 'curl_perform' not in [c[0] for c in calls], 'the card filled up before the worker started: FAILED, SBA_CARDFULL, no request')
    # the card full during the transfer (sbnet\'s 32 MB floor stops the write)
    m = machine(); base = server(m)
    m.curl_site = lambda url, o: dict(base(url, o), rc=23, body=DATA[:100000], partial=True)
    r, th = add(m, t)
    m.free_mb = 1024

    def low(*_):
        m.free_mb = 20
    m.curl_site = lambda url, o: (low(), dict(base(url, o), rc=23, body=DATA[:100000], partial=True))[1]
    work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['CARDFULL']), 'a write refused with the card under its reserve: SBA_CARDFULL')
    # the failed row stays until it is cancelled
    m = machine(); m.curl_site = lambda url, o: dict(rc=22, code=404, body=b'', length=0)
    r, th = add(m, t); work(m, th)
    expect(state(m)[0] == DL['FAILED'], 'a failure stays visible')
    cancel(m, 'tr-1')
    expect(state(m)[0] == DL['NONE'], 'sba_dl_cancel clears a failed entry')


def control_tests(ctx):
    """Cancel (waiting and running), cancel all, delete."""
    expect = ctx.expect
    t1, t2, t3 = track(), track('tr-2', 'Song Two'), track('tr-3', 'Song Three')
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3)
    expect(QUEUE not in m.fs and [state(m, i)[0] for i in ('tr-1', 'tr-2', 'tr-3')] == [DL['WAIT']] * 3, 'an add is a message: the page shows the track waiting at once, the card is the worker\'s to write')
    take(m)
    expect(queued(m) == ['tr-1', 'tr-2', 'tr-3'], 'each add appends the track\'s row to dlq.idx')
    rc, th2 = cancel(m, 'tr-2')
    expect(rc == 0 and th2 is None and state(m, 'tr-2')[0] == DL['NONE'] and queued(m) == ['tr-1', 'tr-2', 'tr-3'], 'a cancel is a message too: gone for the page at once, no second thread')
    take(m)
    expect(state(m, 'tr-2')[0] == DL['NONE'] and queued(m) == ['tr-1', 'tr-3'], 'a waiting download leaves the queue, and the card')
    calls = work(m, th)
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(len(reqs) == 2 and 'id=tr-1' in reqs[0] and 'id=tr-3' in reqs[1] and state(m, 'tr-2')[0] == DL['NONE'], 'the cancelled one is never fetched')
    expect(QUEUE not in m.fs and QUEUE + '.tmp' not in m.fs, 'with the queue drained dlq.idx is gone')
    # cancel the running one from inside the transfer
    m = machine(); base = server(m)
    hits = []

    def stop(u, sent, total):
        if sent >= 300000 and not hits:
            hits.append(sent); cancel_in(m, 'tr-1')
    m.curl_site = lambda url, o: dict(base(url, o), xfer=stop)
    r, th = add(m, t1); add(m, t2)
    work(m, th)
    final = f'{MUSIC}/{name_of(t1)}'
    expect(hits and state(m)[0] == DL['NONE'] and final not in m.fs and 'tr-1' not in m.fs.get(IDX, b'').decode(), 'cancelling the running download stops it: no file, no manifest row, not failed')
    expect(state(m, 'tr-2')[0] == DL['DONE'], 'the next track in the queue still downloads')
    expect(QUEUE not in m.fs, 'and nothing waits on the card')
    # cancelled and added again before the worker has seen the cancel: the cancel is withdrawn, and on the card the track's row is written again after the cancel's line
    m = machine(); base = server(m)
    hits = []

    def again(u, sent, total):
        if sent >= 300000 and not hits:
            hits.append(sent); cancel_in(m, 'tr-1')
            buf = m.alloc(SIZE); m.u.mem_write(buf, pack(t1))
            hits.append(m.nested(PSYMS['sba_dl_add'], buf)); hits.append(state(m, inside=True)[0])
        elif len(hits) == 3 and sent >= 600000:
            hits.append(bytes(m.fs.get(QUEUE, b'')))   # (the worker has taken both messages by now: the transfer-info hook)
    m.curl_site = lambda url, o: dict(base(url, o), xfer=again)
    r, th = add(m, t1)
    work(m, th)
    lines = hits[3].decode().split('\n') if len(hits) == 4 else []
    reqs = [c for c in m.calls if c[0] == 'curl_perform']
    expect(len(hits) == 4 and hits[1] == 0 and hits[2] == DL['WAIT'] and len(reqs) == 1 and state(m)[0] == DL['DONE'] and [x.split('\t')[0] for x in lines] == ['i=tr-1', ''],
           f'the download goes on and finishes in the one request; the worker took the cancel and the add in the order asked and left the track\'s row alone in dlq.idx ({hits[:3]}, {lines})')
    m2 = machine(); m2.dirs.add('/mnt/mmc/.m1plus/subsonic'); m2.put(QUEUE, hits[3] if len(hits) == 4 else b'')
    expect(state(m2)[0] == DL['WAIT'], 'a restart at that moment: the track still waits')
    # the same, but the transfer has already stopped for the cancel when the add comes (the worker has not handled it yet): the add is told yes, so the track is fetched again
    m = machine(); base = server(m)
    hits = []

    def stop_only(u, sent, total):
        if sent >= 300000 and not hits:
            hits.append(sent); cancel_in(m, 'tr-1')

    def late(p):
        if len(hits) == 1 and any(c[0] == 'curl_perform' and c[2] == 42 for c in m.calls):
            hits.append(0)   # (the add asks for the free space too)
            buf = m.alloc(SIZE); m.u.mem_write(buf, pack(t1))
            hits[1] = m.nested(PSYMS['sba_dl_add'], buf)
    m.curl_site = lambda url, o: dict(base(url, o), xfer=stop_only)
    m.on_statfs = late
    r, th = add(m, t1)
    calls = work(m, th)
    reqs = [c for c in calls if c[0] == 'curl_perform' and 'id=tr-1' in c[1]]
    expect(len(hits) == 2 and hits[1] == 0 and [c[2] for c in reqs] == [42, 0] and state(m)[0] == DL['DONE'] and m.fs.get(f'{MUSIC}/{name_of(t1)}') == DATA and QUEUE not in m.fs,
           f'added again after the transfer stopped, before the worker dropped it: fetched a second time and complete ({hits}, {[c[2] for c in reqs]}, {state(m)[0]})')
    # cancelled after the transfer ended with a network fault and the worker has its answer, before it has marked the track failed (the folder scan before a pause is that moment):
    # the cancel is told yes, so the track does not come back when the network does
    m = machine(); base = server(m)
    m.curl_site = lambda url, o: base(url, o) if 'id=tr-2' not in url else dict(rc=7, code=0, body=b'', length=0)
    hits = []

    def late_cancel():
        if not hits and any(c[0] == 'curl_perform' and c[2] == 7 for c in m.calls):
            hits.append(None)   # (the cancel may come here again)
            hits[0] = m.nested(PSYMS['sba_dl_cancel'], m.cstr('tr-2'))
    m.on_scan = late_cancel
    r, th = add(m, t1); add(m, t2)
    work(m, th)
    m.on_scan = None
    expect(hits == [0] and state(m)[0] == DL['DONE'] and state(m, 'tr-2')[0] == DL['NONE'] and queued(m) == [], f'a cancel between the network fault and its handling: SBA_OK and the track is out ({hits}, {state(m, "tr-2")[0]}, {queued(m)})')
    m.curl_site = base
    n, th = resume(m)
    calls = work(m, th) if th else []
    expect(n == 0 and not [c for c in calls if c[0] == 'curl_perform'] and state(m, 'tr-2')[0] == DL['NONE'], f'the network is back: nothing is fetched ({n})')
    # the same, with a card that takes no row: the cancel stands
    m = machine(); base = server(m)
    hits = []

    def refused(u, sent, total):
        if sent >= 300000 and not hits:
            hits.append(sent); cancel_in(m, 'tr-1')
            m.fail.add(('write', QUEUE))
            buf = m.alloc(SIZE); m.u.mem_write(buf, pack(t1))
            hits.append(m.nested(PSYMS['sba_dl_add'], buf))
    m.curl_site = lambda url, o: dict(base(url, o), xfer=refused)
    r, th = add(m, t1)
    work(m, th)
    expect(len(hits) == 2 and hits[1] == 0 and state(m)[0] == DL['NONE'] and f'{MUSIC}/{name_of(t1)}' not in m.fs and failure(m) == (SBA['STORAGE'], 0),
           f'the row cannot be written: the cancel stands and the page is told SBA_STORAGE ({hits})')
    # a card that takes neither the cancel's line nor the rewrite: the download stops for this run and the answer says the card did not take it
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); take(m)
    m.fail.add(('write', QUEUE)); m.fail.add(('read', QUEUE))
    r, _ = cancel(m, 'tr-2'); take(m)
    expect(r == 0 and state(m, 'tr-2')[0] == DL['NONE'] and failure(m) == (SBA['STORAGE'], 0), f'a cancel the card does not take: the track is out of this run\'s queue and the page is told SBA_STORAGE ({r})')
    m.fail.clear()
    r1, _ = cancel(m, 'tr-1'); r2, _ = cancel(m, 'nope'); take(m)
    expect(r1 == 0 and r2 == 0 and failure(m) == (0, 0) and queued(m) == [], 'a cancel that is written, and one of a track that is not queued: SBA_OK, nothing to tell')
    # no thread can be made: no worker runs, so the cancel is applied where it is asked (an add says SBA_MEM)
    m = machine(); m.dirs.add('/mnt/mmc/.m1plus/subsonic'); m.put(QUEUE, b'i=k1\tt=One\tx=flac\tp=\ni=k2\tt=Two\tx=flac\tp=\n')
    m.thread_ok = False
    r, th = cancel(m, 'k1')
    expect(r == 0 and th is None and state(m, 'k1')[0] == DL['NONE'] and queued(m) == ['k2'] and not fn(m, 'sba_dl_busy'), f'a cancel with no thread to be had: done at once, on the card too ({r}, {queued(m)})')
    # cancel all
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3)
    take(m)
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    expect(all(state(m, i)[0] == DL['NONE'] for i in ('tr-1', 'tr-2', 'tr-3')) and fn(m, 'sba_dl_pending') == 0, 'cancel all: nothing waits for the page from that moment')
    calls = work(m, th)
    expect(QUEUE not in m.fs, 'cancel all: the queue file goes')
    expect(all(state(m, i)[0] == DL['NONE'] for i in ('tr-1', 'tr-2', 'tr-3')) and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy'), 'cancel all: nothing is fetched, the worker ends')
    # cancel all needs no memory (its message is not allocated), and one asked again while the first is still in the box covers what came between
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2)
    m.calloc_fail = True
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    m.calloc_fail = False
    expect(state(m)[0] == DL['NONE'] and state(m, 'tr-2')[0] == DL['NONE'] and fn(m, 'sba_dl_pending') == 0, 'cancel all with no memory to be had: asked all the same')
    r3, _ = add(m, t3)
    expect(r3 == 0 and state(m, 'tr-3')[0] == DL['WAIT'], 'an add after it waits')
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    expect(state(m, 'tr-3')[0] == DL['NONE'] and fn(m, 'sba_dl_pending') == 0, 'a second cancel all, the first not yet taken: the add between them is gone too')
    r1, _ = add(m, t1)
    calls = work(m, th)
    expect(r1 == 0 and [c[1].split('id=')[1].split('&')[0] for c in calls if c[0] == 'curl_perform'] == ['tr-1'] and state(m)[0] == DL['DONE'] and state(m, 'tr-3')[0] == DL['NONE']
           and QUEUE not in m.fs and not fn(m, 'sba_dl_busy'), 'the worker fetches only what was added after the last cancel all')
    m.thread = None
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    r2, th = add(m, t2)
    th = th or m.thread
    work(m, th)
    expect(r2 == 0 and state(m, 'tr-2')[0] == DL['DONE'], 'and cancel all is there again for the next time (its message is used over)')
    # cancel all with no worker running and a queue on the card that was never read this run (Sign Out after a restart)
    m = machine(); m.dirs.add('/mnt/mmc/.m1plus/subsonic'); m.put(QUEUE, b'i=k1\tt=One\tx=flac\tp=\n')
    m.thread = None
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    calls = work(m, m.thread) if m.thread else []
    expect(QUEUE not in m.fs and state(m, 'k1')[0] == DL['NONE'] and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy'), 'cancel all after a restart: the queue the card kept goes, nothing is fetched')
    m = machine(); m.thread = None
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    expect(m.thread is None, 'cancel all with nothing queued anywhere: no thread is made')
    # delete
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); work(m, th)
    r, th = add(m, t2); work(m, th)
    f1 = f'{MUSIC}/{name_of(t1)}'
    m.put(f1 + '.part', b'x')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-1'), count=1 << 40) == 0 and f1 not in m.fs and f1 + '.part' not in m.fs, 'delete: the file (and a leftover .part) go')
    tried = ('rmdir', ALBUM_DIR) in m.calls
    expect(state(m)[0] == DL['NONE'] and [r['id'] for r in listing(m)] == ['tr-2'] and path_of(m) is None, 'and the manifest row')
    expect(ALBUM_DIR in m.dirs and tried, 'the album folder stays while another download is in it')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-2'), count=1 << 40) == 0 and ALBUM_DIR not in m.dirs and MUSIC + '/An Artist' not in m.dirs and MUSIC in m.dirs
           and ('rmdir', MUSIC) not in m.calls, 'deleting the last one removes the empty album and artist folders (never the Subsonic folder)')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('nope'), count=1 << 40) == 0, 'deleting a track that was never downloaded is fine')
    # deleting by hand: the row goes when the path or the list is asked for
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); work(m, th)
    r, th = add(m, t2); work(m, th)
    del m.fs[f1]
    expect(state(m)[0] == DL['DONE'], 'a file deleted by hand still shows as done until it is looked for (the state is read from memory)')
    expect(path_of(m) is None and state(m)[0] == DL['NONE'] and 'tr-1' not in m.fs[IDX].decode(), 'sba_dl_path drops the row of a file that is gone')
    del m.fs[f'{MUSIC}/{name_of(t2)}']
    expect(listing(m) == [] and 'tr-2' not in m.fs[IDX].decode(), 'sba_downloaded does not list it and drops its row')
    m.card_mounted = False
    m.put(f1, b'x')
    expect(listing(m) == [], 'with the card out nothing is listed and the manifest is not rewritten')
    # downloading again after a hand deletion
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); work(m, th)
    del m.fs[f1]
    r, th = add(m, t1)
    expect(r == 0 and th and state(m)[0] == DL['WAIT'], 'a track whose file was deleted by hand downloads again when asked')
    work(m, th)
    expect(m.fs.get(f1) == DATA, 'and arrives')


def cancel_in(m, i):
    m.nested(PSYMS['sba_dl_cancel'], m.cstr(i))


def add_in(m, t):
    buf = m.alloc(SIZE); m.u.mem_write(buf, pack(t))
    return m.nested(PSYMS['sba_dl_add'], buf)


def order_tests(ctx):
    """The queue is the worker's: what the UI thread asks while a file comes is applied in the order asked, whatever the mix, and the page sees the outcome at once."""
    expect = ctx.expect
    t1, t2, t3 = track(), track('tr-2', 'Song Two'), track('tr-3', 'Song Three')
    f1, f2, f3 = (f'{MUSIC}/{name_of(t)}' for t in (t1, t2, t3))

    def during(steps, tracks=(t1,), at=300000):
        """Download `tracks`; when the first file has `at` bytes the UI thread does `steps` in one go. (machine, requests, what the page saw right after the steps)."""
        m = machine(); base = server(m)
        seen = []

        def hook(u, sent, total):
            if sent >= at and not seen:
                seen.append(None)
                for op, t in steps: (cancel_in(m, t['id']) if op == '-' else add_in(m, t))
                seen[0] = {t['id']: state(m, t['id'], inside=True)[0] for t in (t1, t2, t3)}
        m.curl_site = lambda url, o: dict(base(url, o), xfer=hook)
        th = None
        for t in tracks:
            r, started = add(m, t)
            th = th or started
        calls = work(m, th)
        return m, [(c[1].split('id=')[1].split('&')[0], c[2]) for c in calls if c[0] == 'curl_perform'], seen[0] if seen else {}

    m, reqs, saw = during([('-', t1), ('+', t1), ('-', t1)])
    expect(saw['tr-1'] == DL['NONE'] and reqs == [('tr-1', 42)] and state(m)[0] == DL['NONE'] and f1 not in m.fs and queued(m) == [] and failure(m) == (0, 0),
           f'cancel, add, cancel of the running track: the last word is the cancel; the transfer stops and nothing of the track waits ({saw}, {reqs})')
    m, reqs, saw = during([('-', t1), ('+', t1), ('-', t1), ('+', t1)])
    expect(saw['tr-1'] == DL['WAIT'] and reqs == [('tr-1', 0)] and state(m)[0] == DL['DONE'] and m.fs.get(f1) == DATA and QUEUE not in m.fs,
           f'and with an add last the one transfer goes on to its end ({saw}, {reqs})')
    m, reqs, saw = during([('+', t2), ('-', t2), ('+', t3)])
    expect(saw['tr-2'] == DL['NONE'] and saw['tr-3'] == DL['WAIT'] and [r[0] for r in reqs] == ['tr-1', 'tr-3'] and state(m, 'tr-2')[0] == DL['NONE'] and m.fs.get(f3) == DATA and f2 not in m.fs,
           f'other tracks added and cancelled while a file comes: the file is not disturbed, the cancelled one is never fetched, the added one is next ({saw}, {reqs})')
    m, reqs, saw = during([('-', t2), ('+', t2)], tracks=(t1, t2, t3))
    expect(saw['tr-2'] == DL['WAIT'] and [r[0] for r in reqs] == ['tr-1', 'tr-3', 'tr-2'] and all(state(m, i)[0] == DL['DONE'] for i in ('tr-1', 'tr-2', 'tr-3')),
           f'a waiting track cancelled and added again: it waits anew, behind the others ({saw}, {reqs})')
    # what is asked while a file comes is on the card before the file is done (a restart then keeps it)
    m = machine(); base = server(m)
    snap = []

    def hook2(u, sent, total):
        if sent >= 300000 and not snap: snap.append(None); add_in(m, t2)
        elif sent >= 600000 and len(snap) == 1: snap.append(queued(m))
    m.curl_site = lambda url, o: dict(base(url, o), xfer=hook2)
    r, th = add(m, t1); work(m, th)
    expect(len(snap) == 2 and snap[1] == ['tr-1', 'tr-2'] and state(m, 'tr-2')[0] == DL['DONE'], f'an add made while a file comes has its row on the card within the transfer ({snap[1:]})')
    # the page's count follows the messages
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3)
    n3 = fn(m, 'sba_dl_pending'); cancel(m, 'tr-2'); n2 = fn(m, 'sba_dl_pending')
    take(m)
    expect((n3, n2, fn(m, 'sba_dl_pending')) == (3, 2, 2), f'sba_dl_pending counts the adds and cancels not yet taken, and the same once they are ({n3}, {n2})')
    # a worker that has ended leaves nothing behind: the next message starts a new one
    work(m, th)
    r, th2 = add(m, t2)
    expect(r == 0 and th2 and state(m, 'tr-2')[0] == DL['WAIT'] and fn(m, 'sba_dl_busy') == 1, 'after the worker ended, an add starts a new one')
    work(m, th2)
    expect(state(m, 'tr-2')[0] == DL['DONE'] and not fn(m, 'sba_dl_busy') and QUEUE not in m.fs, 'which fetches it and ends')


def sweep_runner():
    """The page's actions at every step of the download worker (as pcdl/sweep_tests does for the episode queue). Two tracks are asked for; the first transfer of tr-1 breaks in the middle
    (the worker stops there and the queue waits), then the page resumes, as it does when the network is back. A run's steps are the worker's card calls of DM.STEP_CALLS
    and the transfer-info calls of its transfers (the message box's spin lock is inline and held over no call, so every such place is outside it); sweep_tests runs it for every step with each
    action there, sweep_pair_tests for pairs of steps with one action at each. An action is the UI thread's whole call (sba_dl_add, _cancel, _cancel_all, _resume, _delete of tr-1); while the worker holds
    the file lock (sbd.mf) a Delete is left out, since the UI thread would wait there for the lock (the later steps are that case). Nothing is said about how a run goes: only what must hold
    when the worker has stopped for the fault (the card's queue is the memory's) and when it has ended after the resume. Returns run(plan)
    -> (the steps' kinds, the actions done, why the end is wrong or None); plan is {step: the actions there}."""
    T = {'tr-1': track(), 'tr-2': track('tr-2', 'Song Two')}
    F = {i: f'{MUSIC}/{name_of(t)}' for i, t in T.items()}
    CH, MF, HEAD = 524288, PSYMS['sbd'] + 24, PSYMS['sbd'] + 8   # (patch/sbdl.c sbd: job {lock, busy, head, tail}, all {next, op}, mf)

    def on_card(m):
        """The tracks dlq.idx holds: the last line of a track counts (a row, or a cancel's "-=<id>")."""
        ids = {}
        for line in m.fs.get(QUEUE, b'').decode().split('\n'):
            if line.startswith('i='): ids[line.split('\t')[0][2:]] = True
            elif line.startswith('-='): ids[line[2:]] = False
        return sorted(i for i, v in ids.items() if v)

    def run(plan):
        m = machine(); good = server(m, chunk=CH)
        st = dict(busy=True, kinds=[], done=[], broke=False, ret=0, last={i: 'add' for i in T}, was_done=False, after={i: [0, 0] for i in T})   # after: the requests started and the transfer-info calls made for a track since the last action on it

        def act(name):
            if name == 'delete' and m.word(MF): return
            if name == 'cancel': cancel_in(m, 'tr-1')
            elif name == 'all': m.nested(PSYMS['sba_dl_cancel_all'])
            elif name == 'resume': m.nested(PSYMS['sba_dl_resume'])
            elif name == 'add': st['ret'] = st['ret'] or add_in(m, T['tr-1'])
            else:
                st['was_done'] = state(m, inside=True)[0] == DL['DONE']
                m.nested(PSYMS['sba_dl_delete'], m.cstr('tr-1'))
            if name != 'resume':
                for i in (T if name == 'all' else ('tr-1',)): st['last'][i], st['after'][i] = 'cancel' if name == 'all' else name, [0, 0]
            st['done'].append(name)

        def tick(kind):
            if st['busy']: return   # (a step of the action itself, or of the test's own calls)
            i = len(st['kinds']); st['kinds'].append(kind + ('+mf' if m.word(MF) else ''))
            st['busy'] = True
            for name in plan.get(i, ()): act(name)
            st['busy'] = False

        def site(url, o):
            tid = url.split('id=')[1].split('&')[0]

            def xfer(*a):   # (the step first: a cancel made at this call is taken by it, so the call counts after the cancel; the counters are looked up each time, an action replaces them)
                tick('xfer')
                st['after'][tid][1] += 1
            st['after'][tid][0] += 1
            out = dict(good(url, o), xfer=xfer)
            if 'id=tr-1' in url and not st['broke']:
                st['broke'] = True
                out.update(rc=28, partial=True, body=out['body'][:2 * CH])
            return out
        m.curl_site = site
        m.on_step = tick
        r, th = add(m, T['tr-1']); add(m, T['tr-2'])
        why = None

        def drive(th):
            while th:
                st['busy'] = False
                m.thread = None
                work(m, th)
                st['busy'] = True
                th = m.thread
        drive(th)
        # the worker has stopped (at the fault, or with nothing left): what waits on the card is what waits in memory, and a restart would find the same
        mem = sorted(i for i in T if state(m, i)[0] in (DL['WAIT'], DL['FAILED']))
        if m.word(HEAD) or fn(m, 'sba_dl_busy') or m.word(MF): why = 'at the stop: a message, a worker or the file lock is left'
        elif on_card(m) != mem or fn(m, 'sba_dl_pending') != len(mem): why = f'at the stop: the card\'s queue {on_card(m)} is not the memory\'s {mem} ({fn(m, "sba_dl_pending")} pending)'
        elif not plan and sorted(t['id'] for t in waiting(reboot(m))) != mem: why = f'at the stop: a restart would queue {[t["id"] for t in waiting(reboot(m))]}, not {mem}'   # (the plain run only: on_card reads the file as the loader does, persist_tests)
        left = [i for i in mem if st['last'][i] != 'add']
        if not why and left: why = f'at the stop: {left} still wait after a cancel'
        for _ in range(3):   # the network is back: the page resumes (a second time when an action left a track stopped behind the first resume)
            n, th = resume(m)
            if not th: break
            drive(th)
        m.on_step = None
        idx = m.fs.get(IDX, b'').decode()
        for i in T:
            if why: break
            file, part, s, last = m.fs.get(F[i]), m.fs.get(F[i] + '.part'), state(m, i)[0], st['last'][i]
            if s not in (DL['NONE'], DL['DONE']): why = f'{i} is left in the queue (state {s})'
            elif file is not None and file != DATA: why = f'the file of {i} is not the track ({len(file)} bytes)'
            elif part is not None and (file is not None or not DATA.startswith(part)): why = f'the .part of {i} is not a start of the track, or is beside the file ({len(part)} bytes)'
            elif (file is not None) != (f'i={i}\t' in idx) or (file is not None) != (s == DL['DONE']): why = f'{i}: file {file is not None}, manifest row {f"i={i}" in idx}, state {s}'
            elif last == 'add' and file is None: why = f'{i} was asked for last and is not downloaded'
            elif last == 'delete' and st['was_done'] and file is not None: why = f'{i} was deleted when it was downloaded and is on the card'
            elif last != 'add' and st['after'][i][1] and file is not None: why = f'{i} is downloaded though a transfer-info call of its transfer came after its cancel'
            elif last != 'add' and (st['after'][i][0] > 1 or st['after'][i][1] > 1):   # (the one call is the one that takes the cancel and stops the transfer, the one request that of a track taken up
                why = f'{i} went on after its cancel ({st["after"][i][0]} requests, {st["after"][i][1]} transfer-info calls)'   # before the cancel, stopped at its first call with no byte; a file whose last call was before the cancel is done)
        if why: pass
        elif m.word(HEAD) or fn(m, 'sba_dl_busy') or m.word(MF): why = 'a message, a worker or the file lock is left'
        elif QUEUE in m.fs or fn(m, 'sba_dl_pending'): why = f'the queue is not empty ({on_card(m)}, {fn(m, "sba_dl_pending")} pending)'
        elif st['ret']: why = f'an add failed ({st["ret"]})'
        elif failure(m)[0] not in (0, SBA['NET']): why = 'a failure other than the broken transfer\'s is kept'
        return st['kinds'], st['done'], why
    return run


SWEEP_ONE = (('cancel',), ('all',), ('delete',), ('cancel', 'add'), ('all', 'add'), ('cancel', 'add', 'cancel'))
SWEEP_TWO = (('cancel', 'add'), ('all', 'add'), ('add', 'delete'))
SWEEP_HOLDS = ('nothing is left in the box or the queue, a file is whole and has its manifest row or is not there, a .part is a start of the file, the card\'s queue is the memory\'s at the stop, '
               'the track asked for last is downloaded, one deleted when downloaded is gone, one cancelled last does not wait at the stop, and gets no byte after the transfer-info call that takes the cancel')


def sweep_tests(ctx):
    """One place: each action, and each sequence of actions, at every step of the worker (sweep_runner)."""
    expect = ctx.expect
    run = sweep_runner()
    kinds, _, why = run({})
    n = len(kinds)
    seen = {k.split('+')[0] for k in kinds}
    expect(why is None and seen == {*DM.STEP_CALLS, 'xfer'} and 'open+mf' in kinds and n >= 60,
           f'the two downloads alone, the break and the resume: both whole, and the {n} steps are of every kind, some under the file lock ({why}; {sorted(seen)})')
    bad, runs = [], 0
    for i in range(n):
        for acts in SWEEP_ONE + ((('resume',),) if i % 6 == 0 else ()):   # (sba_dl_resume does nothing while a worker runs: looked at every 6th step only)
            k, done, why = run({i: acts})
            runs += 1
            if why: bad.append((i, kinds[i], acts, why))
    expect(not bad and runs > 500, f'each action at each of the {n} steps ({runs} runs): {SWEEP_HOLDS} ({len(bad)} wrong: {bad[:6]})')


def sweep_pair_tests(ctx):
    """Two places: one action at a step and another at a later one. Every pair of steps would be some 20,000 runs, so the second step is the next one (the two actions on both sides of whatever
    the worker does between two steps) for every first step, and for the steps further apart both are taken from every 6th step."""
    expect = ctx.expect
    run = sweep_runner()
    n = len(run({})[0])
    far = range(0, n, 6)
    pairs = [(i, i + 1) for i in range(n)] + [(i, j) for i in far for j in far if j > i]
    bad, runs = [], 0
    for first, second in SWEEP_TWO:
        for i, j in pairs:
            if (j - i > 1) and first == 'add': continue   # (the far pairs: the two that start with a cancel)
            k, done, why = run({i: (first,), j: (second,)})
            if why: bad.append((i, k[i], first, j, k[j] if j < len(k) else None, second, done, why))
            runs += len(done) == 2   # (not counted: the run had no such step after the first action, or the Delete met the file lock)
    expect(not bad and runs > 400, f'two actions at two steps ({runs} runs of {len(pairs)} pairs): {SWEEP_HOLDS} ({len(bad)} wrong: {bad[:6]})')


def collision_tests(ctx):
    """A file on the card is never overwritten."""
    expect = ctx.expect
    t = track()
    final = f'{MUSIC}/{name_of(t)}'
    # the file is there but the manifest does not know it: adopted as it is, nothing fetched
    m = machine(); m.curl_site = server(m)
    m.put(final, b'mine, from an earlier run')
    r, th = add(m, t)
    calls = work(m, th)
    expect(m.fs[final] == b'mine, from an earlier run' and 'curl_perform' not in [c[0] for c in calls], 'an existing file of that name is kept and not fetched again')
    st, _, got, total = state(m)
    expect(st == DL['DONE'] and path_of(m) == final and f'w={len(b"mine, from an earlier run")}' in m.fs[IDX].decode(), 'it becomes the track\'s download (manifest row with its real size)')
    # the name belongs to another track in the manifest: a numbered name
    m = machine(); log = []; m.curl_site = server(m, log=log)
    row = (f'i=other-id\tt=Song One\tx=flac\tw=5\tp={name_of(t)}\n').encode()
    m.put(IDX, b'M1PLUS-DL 1\n' + row); m.put(final, b'other')
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    r, th = add(m, t); work(m, th)
    alt = f'{MUSIC}/{name_of(t, 1)}'
    expect(m.fs[final] == b'other' and m.fs.get(alt) == DATA and len(log) == 1, 'a file of that name owned by another track is not touched: the download gets "(2)"')
    expect(path_of(m) == alt and path_of(m, 'other-id') == final, 'each track has its own file')
    expect(sorted(r['id'] for r in listing(m)) == ['other-id', 'tr-1'], 'both are listed')
    # the card folds the case of names: a name another track owns in other letters is the same file, never taken (and never adopted: the mock card, like a Linux one, has no such file)
    m = machine(); log = []; m.curl_site = server(m, log=log)
    row = (f'i=other-id\tt=SONG ONE\tx=flac\tw=5\tp={name_of(t).upper()}\n').encode()
    m.put(IDX, b'M1PLUS-DL 1\n' + row); m.put(f'{MUSIC}/{name_of(t).upper()}', b'other')
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    r, th = add(m, t); work(m, th)
    expect(path_of(m) == alt and m.fs.get(alt) == DATA and final not in m.fs and len(log) == 1, f'a name that differs only in case from another track\'s file: the download gets "(2)" ({path_of(m)})')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-1'), count=20000000) == 0 and m.fs.get(f'{MUSIC}/{name_of(t).upper()}') == b'other', 'and removing it leaves the other track\'s file')
    # a card that folds the case of every script (exFAT's own table): a name that differs from another track's in the case of a letter outside ASCII IS that track's file; the card says so
    # (one inode) and the names do not
    cafe, CAFE = track('c1', 'Café'), track('c2', 'CAFÉ')
    m = machine(); m.nocase = True; log = []; m.curl_site = server(m, log=log)
    r, th = add(m, cafe); work(m, th)
    r, th = add(m, CAFE); work(m, th)
    p1, p2 = path_of(m, 'c1'), path_of(m, 'c2')
    expect(p1 and p2 and p1.casefold() != p2.casefold() and len(log) == 2 and m.fs.get(p1) == DATA and m.fs.get(p2) == DATA, f'two titles that differ in the case of a letter outside ASCII: two files, two downloads ({p1}, {p2})')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('c2'), count=20000000) == 0 and m.fs.get(p1) == DATA and path_of(m, 'c1') == p1, 'removing the second leaves the first one\'s file')
    # the same card, a file the manifest does not know and nobody else's: still adopted (in whatever case it is on the card)
    m = machine(); m.nocase = True; m.curl_site = server(m)
    shout = final.rsplit('/', 1)[0] + '/' + final.rsplit('/', 1)[1].upper()
    m.put(shout, b'mine, from an earlier run')
    r, th = add(m, t); calls = work(m, th)
    expect(state(m)[0] == DL['DONE'] and 'curl_perform' not in [c[0] for c in calls] and m.fs.get(shout) == b'mine, from an earlier run', 'a file of nobody else is adopted on such a card too')
    # characters that cannot be in a name
    m = machine(); m.curl_site = server(m)
    odd = track('x1', 'AC/DC: Back "in" <Black>?')
    r, th = add(m, odd); work(m, th)
    p = path_of(m, 'x1')
    expect(p == ALBUM_DIR + '/03 AC_DC_ Back _in_ _Black__.flac', f'unsafe characters in a title become underscores ({p})')


def scan_tests(ctx):
    """Stock's library learns the downloads: one scan of an album's folder when the worker leaves it or ends."""
    expect = ctx.expect
    m = machine(); m.curl_site = server(m)
    d = track('dsd-1', 'Big DSD', suffix='dsf')
    r, th = add(m, d); work(m, th)
    expect(m.scans == ((ALBUM_DIR, 0),) and state(m, 'dsd-1')[0] == DL['DONE'], f'after a download stock scans the album\'s folder (drop 0: nothing is removed from the library) ({m.scans})')
    r, th = add(m, track()); work(m, th)
    expect(len(m.scans) == 2, 'a FLAC download scans too')
    m = machine(); m.curl_site = server(m)
    other = dict(track('o1', 'Else'), album='Other Album')
    r, th = add(m, track()); add(m, track('tr-2', 'Song Two')); add(m, other); add(m, dict(track('o2', 'More'), album='Other Album'))
    work(m, th)
    expect(m.scans == ((ALBUM_DIR, 0), (MUSIC + '/An Artist/Other Album', 0)), f'four tracks of two albums: each folder is scanned once, when its last track is there ({m.scans})')
    m = machine(); m.curl_site = lambda url, o: dict(rc=22, code=404, body=b'', length=0)
    r, th = add(m, d); work(m, th)
    expect(m.scans == (), 'a failed download does not scan')
    # the worker stops (Wi-Fi lost): what is on the card by then is scanned
    m = machine(); m.curl_site = server(m)
    r, th = add(m, track()); add(m, track('tr-2', 'Song Two'))
    site = m.curl_site
    m.curl_site = lambda url, o: (setattr(m, 'wifi', -1), site(url, o))[1]
    work(m, th)
    expect(m.scans == ((ALBUM_DIR, 0),) and state(m)[0] == DL['DONE'] and state(m, 'tr-2')[:2] == (DL['FAILED'], SBA['NOWIFI']), 'a queue that stops half-way scans the folder of what arrived')


def layout_tests(ctx):
    """The file of a track: <artist>/<album>/<nn> <title>.<suffix>, the artist being the album's."""
    expect = ctx.expect

    def got(t, seed=None):
        m = machine(); m.curl_site = server(m)
        if seed: seed(m)
        r, th = add(m, t); work(m, th)
        p = path_of(m, t['id'])
        return p[len(MUSIC) + 1:] if p and m.fs.get(p) == DATA else p

    expect(got(track()) == 'An Artist/An Album/03 Song One.flac', 'artist, album, the two-digit track number and the title')
    expect(got(dict(track(), disc=2)) == 'An Artist/An Album/2-03 Song One.flac', 'a second disc carries its number')
    expect(got(dict(track(), track=0)) == 'An Artist/An Album/Song One.flac', 'no track number: the title alone')
    expect(got(dict(track(), track=112)) == 'An Artist/An Album/112 Song One.flac', 'a three-digit track number')
    expect(got(dict(track(), artist='', album='', title='')) == 'Unknown Artist/Unknown Album/03 Track.flac', 'empty tags have stand-in names')
    expect(got(dict(track(), artist='  AC/DC ', album='...And Justice.', title='What?')) == 'AC_DC/_..And Justice/03 What_.flac',
           'no slash, no leading dot, no leading or trailing space and no trailing dot in a folder name')
    long = got(dict(track(), artist='\u6b4c' * 40, album='B' * 90, title='T' * 150))
    a, b, c = long.encode('latin-1').decode().split('/')   # (read_cstr shows bytes as latin-1 characters)
    expect(a == '\u6b4c' * 21 and b == 'B' * 64 and c == '03 ' + 'T' * 100 + '.flac', f'long names are cut (64 bytes a folder, 100 the title) at a character ({len(a.encode())}, {len(b)}, {len(c)})')
    albums = lambda m: SA.seed(m, '/mnt/mmc/.m1plus/subsonic/albums.idx', 'album', [dict(id='zz', name='Else', artist='Nobody'), dict(id='al-1', name='An Album', artist='Various Artists')])
    expect(got(dict(track(), artist='Guest feat. Someone'), albums) == 'Various Artists/An Album/03 Song One.flac', 'the folder is the ALBUM\'s artist when the cache knows the album (a compilation stays together)')
    expect(got(dict(track(), album_id='nope'), albums) == 'An Artist/An Album/03 Song One.flac', 'an album the cache does not have: the track\'s artist')


def persist_tests(ctx):
    """The waiting queue is on the card: it outlives a reboot, stops at a failure that is not the track's, and goes on with sba_dl_resume."""
    expect = ctx.expect
    t1, t2, t3 = track(), track('tr-2', 'Song Two'), track('tr-3', 'Song Three')
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3); take(m)
    rows = m.fs[QUEUE].decode().split('\n')
    expect(queued(m) == ['tr-1', 'tr-2', 'tr-3'] and 't=Song One' in rows[0] and 'a=An Artist' in rows[0] and 'n=3' in rows[0] and f'z={len(DATA)}' in rows[0], 'dlq.idx has the whole row of each waiting track')
    # a reboot before the worker ran: the three wait again, nothing runs until asked
    m = reboot(m)
    expect([state(m, i)[0] for i in ('tr-1', 'tr-2', 'tr-3')] == [DL['WAIT']] * 3 and not fn(m, 'sba_dl_busy') and m.thread is None, 'after a reboot the queue is read back: waiting, no worker yet')
    r, th = resume(m)
    expect(r == 3 and th and fn(m, 'sba_dl_busy') == 1, 'sba_dl_resume starts the worker for the three')
    r2, th2 = resume(m)
    expect(r2 == 0 and th2 is None, 'again while it runs: nothing')
    calls = work(m, th)
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(len(reqs) == 3 and ['id=tr-1' in reqs[0], 'id=tr-2' in reqs[1], 'id=tr-3' in reqs[2]] == [True] * 3 and [r['id'] for r in listing(m)] == ['tr-1', 'tr-2', 'tr-3'],
           'they download in the order asked, with their whole rows in the manifest')
    expect(listing(m)[1] == t2 and QUEUE not in m.fs, 'the row read back from the card is the track as it was queued; the drained queue leaves no file')
    expect(resume(m) == (0, None), 'nothing waiting: sba_dl_resume does nothing')
    # a reboot half-way: the downloaded one is not fetched again
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2)
    site = m.curl_site; seen = []

    def one(url, o):
        if seen: raise KeyboardInterrupt   # (the power goes during the second file)
        seen.append(url)
        return site(url, o)
    m.curl_site = one
    try: work(m, th)
    except KeyboardInterrupt: pass
    m = reboot(m)
    expect(state(m)[0] == DL['DONE'] and state(m, 'tr-2')[0] == DL['WAIT'] and queued(m) == ['tr-1', 'tr-2'], 'power lost during the second file: the first is Downloaded, the second waits (its row is still on the card)')
    log = []
    m.curl_site = server(m, log=log)
    r, th = resume(m); work(m, th)
    expect(r == 1 and len(log) == 1 and 'id=tr-2' in log[0][0] and state(m, 'tr-2')[0] == DL['DONE'] and QUEUE not in m.fs, 'the resume fetches only the second')
    # the worker stops at a failure that is not the track's: the rest keeps waiting
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3)
    guard(m, SBA['NOWIFI'])
    calls = work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['NOWIFI']) and [state(m, i)[0] for i in ('tr-2', 'tr-3')] == [DL['WAIT']] * 2 and not fn(m, 'sba_dl_busy')
           and 'curl_perform' not in [c[0] for c in calls], 'Wi-Fi lost: the first fails with the reason, the others keep waiting, the worker ends without a request')
    expect(queued(m) == ['tr-1', 'tr-2', 'tr-3'], 'all three rows stay on the card')
    expect(resume(m) == (0, None), 'sba_dl_resume without Wi-Fi: nothing')
    r, th = add(m, t2)
    expect(r == SBA['NOWIFI'] and th is None, 'asking for a waiting one without Wi-Fi says why it does not start')
    guard(m, 0)
    r, th = resume(m)
    expect(r == 3 and th and state(m)[0] == DL['WAIT'], 'Wi-Fi back: the one it stopped at waits again with the others')
    calls = work(m, th)
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(len(reqs) == 3 and 'id=tr-2' in reqs[0] and 'id=tr-3' in reqs[1] and 'id=tr-1' in reqs[2] and all(state(m, i)[0] == DL['DONE'] for i in ('tr-1', 'tr-2', 'tr-3')),
           f'all three arrive, the one it stopped at last ({[u.split("id=")[1][:4] for u in reqs]})')
    # an add of a waiting track starts a stopped queue too
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2)
    guard(m, SBA['NOWIFI']); work(m, th); guard(m, 0)
    r, th = add(m, t2)
    expect(r == 0 and th and fn(m, 'sba_dl_busy') == 1, 'asking again for a waiting track starts the worker')
    work(m, th)
    expect(state(m, 'tr-2')[0] == DL['DONE'] and state(m)[:2] == (DL['FAILED'], SBA['NOWIFI']) and queued(m) == ['tr-1'], 'it arrives; the one the worker stopped at stays failed, its row kept for a resume')
    # a failure of the track itself does not stop the queue, and its row is not kept
    m = machine(); base = server(m)
    m.curl_site = lambda url, o: (reply_head(m, o, 404), dict(rc=22, code=404, body=b'', length=0))[1] if 'id=tr-1' in url else base(url, o)
    r, th = add(m, t1); add(m, t2)
    work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['NOTFOUND']) and state(m, 'tr-2')[0] == DL['DONE'] and QUEUE not in m.fs, 'a 404 on one track: the next still downloads, and the failed one is not queued again after a reboot')
    # a row with no line on the card (the file was removed under it)
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); take(m)
    del m.fs[QUEUE]
    calls = work(m, th)
    expect(state(m)[:2] == (DL['FAILED'], SBA['PARSE']) and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy'), 'a waiting track whose row is gone from the card fails without a request')
    # odd lines in the queue file
    m = machine(); m.curl_site = server(m)
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    m.put(QUEUE, b'garbage\ni=\n\ni=k1\tt=One\tx=flac\tp=\ni=k1\tt=One\tx=flac\tp=\ni=k2\tt=Two\tx=mp3\tn=2\tp=\n')
    r, th = resume(m)
    expect(r == 2 and th, 'bad lines are skipped and a track listed twice waits once')
    work(m, th)
    expect(path_of(m, 'k1') == MUSIC + '/Unknown Artist/Unknown Album/One.flac' and path_of(m, 'k2') == MUSIC + '/Unknown Artist/Unknown Album/02 Two.mp3', 'and they download')


def qread_tests(ctx):
    """A queue file that cannot be read is the card's failure, not the track's: the worker stops, the row is kept and the next start downloads it."""
    expect = ctx.expect
    m = machine(); log = []; m.curl_site = server(m, log=log)
    t1, t2 = track('q1', 'One'), track('q2', 'Two')
    r, th = add(m, t1)
    add(m, t2)
    m.fail.add(('read', QUEUE))
    work(m, th)
    st1, code1 = state(m, 'q1')[:2]
    expect(st1 == DL['FAILED'] and code1 == SBA['STORAGE'] and state(m, 'q2')[0] == DL['WAIT'] and not log and not m.call(PSYMS['sba_dl_busy'], count=2000000),
           f'the queue file will not read: the track fails as a card failure, the next one waits, the worker ends, nothing is fetched ({st1}, {code1})')
    expect(sorted(queued(m)) == ['q1', 'q2'], f'both rows are still on the card ({queued(m)})')
    m.fail.discard(('read', QUEUE))
    m.thread = None
    n, th = resume(m)
    work(m, th)
    expect(n == 2 and state(m, 'q1')[0] == DL['DONE'] and state(m, 'q2')[0] == DL['DONE'] and len(log) == 2 and QUEUE not in m.fs, f'the next start reads it and downloads both ({n}, {len(log)})')
    # the first read of the run fails: no queue is taken as loaded (an empty one would be compacted away), and the next use reads it
    rows = b'i=k1\tt=One\tx=flac\tp=\ni=k2\tt=Two\tx=flac\tp=\n'
    m = machine(); m.curl_site = server(m)
    m.dirs.add('/mnt/mmc/.m1plus/subsonic'); m.put(QUEUE, rows)
    m.fail.add(('read', QUEUE))
    expect(state(m, 'k1')[0] == DL['NONE'] and resume(m) == (0, None) and m.fs.get(QUEUE) == rows, 'the queue file will not read at the first use: nothing waits yet, nothing starts, the file is untouched')
    r, th = add(m, track('k3', 'Three'))
    expect(r == SBA['STORAGE'] and th is None and m.fs.get(QUEUE) == rows, f'and nothing is added on top of rows that were not seen: SBA_STORAGE ({r})')
    m.fail.discard(('read', QUEUE))
    expect(state(m, 'k1')[0] == DL['WAIT'] and state(m, 'k2')[0] == DL['WAIT'], 'the next use reads it: both wait')
    # a read that fails while a waiting track is cancelled: the file is not rewritten from nothing (the other track's row stays)
    m.fail.add(('read', QUEUE))
    r, th = cancel(m, 'k1')
    calls = work(m, th) if th else []
    expect(r == 0 and th and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy') and failure(m) == (0, 0), 'a cancel while no worker runs starts one for the card\'s side; it fetches nothing (the queue was not started) and ends')
    expect(m.fs.get(QUEUE) == rows + b'-=k1\n' and state(m, 'k2')[0] == DL['WAIT'], 'a compaction that cannot read the file leaves its rows as they are; the cancel is one line appended (no read needed)')
    m.fail.discard(('read', QUEUE))
    m2 = reboot(m)
    expect(state(m2, 'k1')[0] == DL['NONE'] and state(m2, 'k2')[0] == DL['WAIT'], 'a restart before any compaction: the cancelled track does not wait again, the other does')
    r, th = add(m2, track('k1', 'One')); take(m2)
    m3 = reboot(m2)
    expect(r == 0 and state(m3, 'k1')[0] == DL['WAIT'] and state(m3, 'k2')[0] == DL['WAIT'], 'added again after the cancel: its new row counts')
    n, th = resume(m); work(m, th)
    expect(state(m, 'k2')[0] == DL['DONE'] and state(m, 'k1')[0] == DL['NONE'] and QUEUE not in m.fs, 'the track that still waited downloads; the cancelled one does not come back, and the drained queue\'s file goes')


def qlast_tests(ctx):
    """The queue file is a log: the last row of a track is the track's. A row before a cancel's line that a failed rewrite left behind is never the one downloaded or kept."""
    expect = ctx.expect
    m = machine(); m.curl_site = server(m)
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    m.put(QUEUE, b'i=k1\tt=Old Title\tx=flac\tp=\n-=k1\ni=k2\tt=Two\tx=flac\tp=\n')
    expect(state(m, 'k1')[0] == DL['NONE'] and state(m, 'k2')[0] == DL['WAIT'], 'a row, its cancel and another row on the card: only the other track waits')
    r, th = add(m, track('k1', 'New Title'))
    cancel(m, 'k2'); take(m)
    text = m.fs.get(QUEUE, b'').decode()
    expect(r == 0 and text.count('i=k1\t') == 1 and 'New Title' in text and 'Old Title' not in text and '-=' not in text and 'k2' not in text,
           f'added again with another title, then a rewrite: the file holds the new row alone ({text!r})')
    m.put(QUEUE, b'i=k1\tt=Old Title\tx=flac\tp=\n-=k1\n' + m.fs[QUEUE])   # (as a failed rewrite would have left it)
    work(m, th)
    p = path_of(m, 'k1')
    expect(p and p.endswith('New Title.flac'), f'the worker downloads the track as its last row says ({p})')


def qlist_tests(ctx):
    """sba_dl_queue and sba_dl_rows (the Downloaded page's Downloading section): the tracks still to come with their whole rows in the worker's order, and a number that moves with the rows of
    that page (the queue's and the manifest's) and never with a transfer's progress."""
    expect = ctx.expect
    t1, t2, t3 = track(), track('tr-2', 'Song Two'), track('tr-3', 'Song Three')
    m = machine(); m.curl_site = server(m)
    expect(waiting(m) == [] and QUEUE not in m.fs, 'nothing queued: no rows (and no file made)')
    s0 = fn(m, 'sba_dl_rows')
    r, th = add(m, t1); take(m)   # (the list is the slots': a row shows once the worker has taken its message)
    s1 = fn(m, 'sba_dl_rows')
    add(m, t2); add(m, t3); take(m)
    s3 = fn(m, 'sba_dl_rows')
    expect(waiting(m) == [t1, t2, t3], f'three queued: their whole rows, in the order asked ({[t["id"] for t in waiting(m)]})')
    expect(len({s0, s1, s3}) == 3 and fn(m, 'sba_dl_rows') == s3, 'sba_dl_rows moves with every track that joins, and stands still otherwise')
    # a cancel takes the row out; the same track added again goes to the end
    cancel(m, 'tr-2'); take(m)
    s4 = fn(m, 'sba_dl_rows')
    expect([t['id'] for t in waiting(m)] == ['tr-1', 'tr-3'] and s4 != s3, 'a cancelled track is not listed, and the number moved')
    add(m, t2); take(m)
    expect(waiting(m) == [t1, t3, t2], 'added again: at the end, its row whole')
    # a reboot: the list is the card's
    m = reboot(m)
    expect(waiting(m) == [t1, t3, t2] and m.thread is None, 'after a reboot the rows the card kept are listed (no worker is started by the read)')
    # while the first runs: it is still the first row and progress does not move the number; when it lands the number moves and the row leaves
    seen = []
    site = server(m)

    def watch(url, o):
        if not seen: seen.append(([t['id'] for t in waiting_in(m)], m.nested(PSYMS['sba_dl_rows'])))
        return site(url, o)
    def waiting_in(m):
        out = m.alloc(8)
        n = m.nested(PSYMS['sba_dl_queue'], out)
        v = m.word(out + 4)
        return [unpack(bytes(m.u.mem_read(v + i * SIZE, SIZE))) for i in range(n)]
    m.curl_site = watch
    before = fn(m, 'sba_dl_rows')
    r, th = resume(m)
    work(m, th)
    expect(seen and seen[0][0] == ['tr-1', 'tr-3', 'tr-2'] and seen[0][1] == before, f'the running download is the first row, and starting it does not move the number ({seen})')
    expect(waiting(m) == [] and fn(m, 'sba_dl_rows') != before and [t['id'] for t in listing(m)] == ['tr-1', 'tr-3', 'tr-2'], 'all landed: no rows wait, the number moved, the manifest has the three')
    # a delete of a finished download moves the number too (the Downloaded rows changed)
    s5 = fn(m, 'sba_dl_rows')
    m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-3'), count=1 << 40)
    expect(fn(m, 'sba_dl_rows') != s5, 'a removed download moves the number')
    # the worker stopped at a lost Wi-Fi: the track it stopped at and the ones behind it are still to come
    m = machine(); m.curl_site = lambda url, o: {'rc': 6}
    r, th = add(m, t1); add(m, t2)
    work(m, th)
    expect(state(m)[0] == DL['FAILED'] and [t['id'] for t in waiting(m)] == ['tr-1', 'tr-2'] and not fn(m, 'sba_dl_busy'), f'a stopped worker: both tracks are still listed ({state(m)}, {[t["id"] for t in waiting(m)]})')
    # cancel all: none
    m.thread = None; s6 = fn(m, 'sba_dl_rows')
    fn(m, 'sba_dl_cancel_all')
    expect(waiting(m) == [] and fn(m, 'sba_dl_rows') != s6, 'sba_dl_cancel_all: nothing is listed from that moment (the worker has not run yet), and the number moved')
    work(m, m.thread)
    expect(waiting(m) == [] and QUEUE not in m.fs, 'and the queue file is gone once the worker has taken it')
    # a queue file that cannot be read: no rows (the tracks still wait)
    m = machine(); m.curl_site = server(m)
    add(m, t1); take(m)
    m.fail.add(('read', QUEUE))
    expect(waiting(m) == [] and state(m)[0] == DL['WAIT'], 'a queue file that will not read: no rows listed, the track still waits')


def manifest_tests(ctx):
    """dl.idx: replaced whole, tolerant of bad lines, rows with tabs and odd text."""
    expect = ctx.expect
    t = track(title='Tab\tand\nline')
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t); work(m, th)
    rows = listing(m)
    expect(len(rows) == 1 and rows[0]['title'] == 'Tab and line' and rows[0]['artist'] == 'An Artist', 'a tab or newline in a title is a space in the manifest (the row stays one line)')
    expect(IDX + '.tmp' not in m.fs and IDX in m.fs, 'the manifest is replaced through a temp file')
    # bad lines are skipped
    m = machine()
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    good = track('g1', 'Good')
    gf = name_of(good)
    bad = ('../../etc/passwd', 'A/../../x.flac', '/etc/passwd', 'A//x.flac', 'A/.hidden/x.flac', '.x.flac', 'A/B/', 'A\\x.flac')
    m.put(IDX, ('M1PLUS-DL 1\n' 'garbage\n' 'i=\n' 'i=noPath\tt=x\n' + ''.join(f'i=esc{k}\tt=x\tp={b}\n' for k, b in enumerate(bad)) + f'i=g1\tt=Good\tx=flac\tp={gf}\tw=3\n' '\n').encode())
    m.put(f'{MUSIC}/{gf}', b'abc'); m.put('/etc/passwd', b'x'); m.put(MUSIC + '/A/x.flac', b'x'); m.put('/mnt/mmc/x.flac', b'x'); m.put(MUSIC + '/.x.flac', b'x'); m.put(MUSIC + '/A/.hidden/x.flac', b'x')
    expect([r['id'] for r in listing(m)] == ['g1'], 'lines with no id, no file name or a path out of the folder (.., an absolute path, an empty or hidden part, a backslash) are skipped')
    expect(all(state(m, f'esc{k}')[0] == DL['NONE'] for k in range(len(bad))) and state(m, 'g1')[0] == DL['DONE'], 'and are not Downloaded')
    # another download keeps the earlier rows and replaces an older row of the same track
    m.curl_site = server(m)
    r, th = add(m, track('t9', 'Nine')); work(m, th)
    ids = [r['id'] for r in listing(m)]
    expect(ids == ['g1', 't9'], f'a new download is appended to the manifest ({ids})')
    # unreadable / absent manifest
    m = machine()
    expect(listing(m) == [] and state(m)[0] == DL['NONE'], 'no manifest: nothing downloaded')
    m.put(IDX, b'\xff\xfe\x00\x01')
    expect(listing(m) == [], 'a binary file is not a manifest')
    # a manifest over the size cap is not overwritten by the next edit
    m = machine()
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    big = b'M1PLUS-DL 1\n' + b'x' * (4 * 1024 * 1024 + 16)
    m.put(IDX, big); m.curl_site = server(m)
    r, th = add(m, track('t9', 'Nine')); work(m, th)
    expect(m.fs.get(IDX) == big, 'an oversized manifest is kept, not replaced by one row')


SECTIONS = [queue_tests, cap_tests, transfer_tests, resume_tests, validator_tests, failure_tests, report_tests, control_tests, order_tests, sweep_tests, sweep_pair_tests, collision_tests, scan_tests, layout_tests, persist_tests, qread_tests, qlast_tests, qlist_tests, manifest_tests]

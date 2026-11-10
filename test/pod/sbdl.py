"""Navidrome downloads (patch/sbdl.c, docs/modules/subsonic.md "Data and cache"): the queue and its guards, the worker (one detached thread, one file at a time), progress and the
generation counter, the .part file and the Range resume, the stall limit and the free-space floor (sbnet's options), a file that is on the card already (never overwritten), the
manifest dl.idx (written atomically, read back offline, dropped when a file was deleted by hand), delete, and the library scan after a DSD download. The compiled payload runs
under Unicorn against a scripted libcurl (no network); the card is a dict of paths. sbapi.c's real guard and login run (the conf file, Wi-Fi level and card state are set up, not a forced answer)."""
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


PCN = sibling('pcnet')
SBA = dict(OK=0, NOCONF=1, NOWIFI=2, NOCLOCK=3, NOCERT=4, CERT=5, NET=6, AUTH=7, NOTFOUND=8, HTTP=9, PARSE=10, STORAGE=11, MEM=12, QFULL=13, CARDFULL=14, NOTAUDIO=15, WRITE=16, CANCELLED=17)
DL = dict(NONE=0, WAIT=1, ACTIVE=2, DONE=3, FAILED=4)
MUSIC, IDX = '/mnt/mmc/Subsonic', '/mnt/mmc/.m1plus/subsonic/dl.idx'
TRACK = struct.Struct('<64s192s192s192s64s64s12s9IB3x')
SIZE = TRACK.size
assert SIZE == 820


def fnv(s):
    h = 2166136261
    for c in s.encode():
        h = ((h ^ c) * 16777619) & 0xffffffff
    return h


def body(n):
    """n bytes that are different everywhere (a resume that is off by one shows)."""
    return bytes((i * 7 + i // 251 + i // 65536) & 255 for i in range(n))


DATA = body(1300000)


def name_of(t, variant=0):
    title = t['title'].replace('/', '_')
    return f'{fnv(t["id"]):08x}-{title}' + (f' ({variant + 1})' if variant else '') + '.' + t['suffix']


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

    def _hook(self, u, address, size, _):
        if self.handlers.get(address, '') == 'scanSpecFolder':
            a0, a1 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1))
            self.scans = (*self.scans, (self.read_cstr(a0), a1))
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


def work(m, th):
    m.call(th[0], a0=th[1], count=1 << 40)
    return list(m.calls)


def state(m, i='tr-1', inside=False):
    """(state, code, got, total); inside: from a libcurl callback (the payload is mid-call there: nested, not a new call)."""
    code, got, total = m.alloc(4), m.alloc(4), m.alloc(4)
    args = (m.cstr(i), code, got, total)
    st = m.nested(PSYMS['sba_dl_state'], *args) if inside else m.call(PSYMS['sba_dl_state'], a0=args[0], a1=code, a2=got, a3=total, count=2000000)
    return st, m.word(code), m.word(got), m.word(total)


def fn(m, name, **kw): return m.call(PSYMS[name], count=2000000, **kw)


def cancel(m, i): m.call(PSYMS['sba_dl_cancel'], a0=m.cstr(i), count=2000000)


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
    # the cap: 32 waiting or running
    m = machine(); m.curl_site = server(m)
    r, th = add(m, track('t0', 't0'))
    for k in range(1, 32): r = add(m, track(f't{k}', f't{k}'))[0]
    expect(r == 0, 'the queue holds 32')
    r, _ = add(m, track('t32', 't32'))
    expect(r == SBA['QFULL'] and state(m, 't32')[0] == DL['NONE'], 'the 33rd: SBA_QFULL')
    # a thread that cannot be made
    m = machine(thread_ok=False)
    r, th = add(m, track())
    expect(r == SBA['MEM'] and state(m)[0] == DL['NONE'] and not fn(m, 'sba_dl_busy'), 'no thread: SBA_MEM, not queued, not busy')
    # a track without an id
    r, th = add(m, track(''))
    expect(r == SBA['PARSE'] and th is None, 'a track with no id is refused')


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
    expect(m.fs.get(final) == DATA and f'{final}.part' not in m.fs, 'the file is complete under its name (<id hash>-<title>.<suffix>) and the .part file is gone')
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

    def failure(m):
        status, code = m.alloc(4), None
        code = m.call(PSYMS['sba_dl_failure'], a0=status, count=2000000)
        return code, m.word(status)

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
    cancel(m, 'tr-2')
    expect(state(m, 'tr-2')[0] == DL['NONE'], 'a waiting download leaves the queue')
    calls = work(m, th)
    reqs = [c[1] for c in calls if c[0] == 'curl_perform']
    expect(len(reqs) == 2 and 'id=tr-1' in reqs[0] and 'id=tr-3' in reqs[1] and state(m, 'tr-2')[0] == DL['NONE'], 'the cancelled one is never fetched')
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
    # cancel all
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); add(m, t2); add(m, t3)
    m.call(PSYMS['sba_dl_cancel_all'], count=2000000)
    calls = work(m, th)
    expect(all(state(m, i)[0] == DL['NONE'] for i in ('tr-1', 'tr-2', 'tr-3')) and 'curl_perform' not in [c[0] for c in calls] and not fn(m, 'sba_dl_busy'), 'cancel all: nothing is fetched, the worker ends')
    # delete
    m = machine(); m.curl_site = server(m)
    r, th = add(m, t1); work(m, th)
    r, th = add(m, t2); work(m, th)
    f1 = f'{MUSIC}/{name_of(t1)}'
    m.put(f1 + '.part', b'x')
    expect(m.call(PSYMS['sba_dl_delete'], a0=m.cstr('tr-1'), count=1 << 40) == 0 and f1 not in m.fs and f1 + '.part' not in m.fs, 'delete: the file (and a leftover .part) go')
    expect(state(m)[0] == DL['NONE'] and [r['id'] for r in listing(m)] == ['tr-2'] and path_of(m) is None, 'and the manifest row')
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
    # characters that cannot be in a name
    m = machine(); m.curl_site = server(m)
    odd = track('x1', 'AC/DC: Back "in" <Black>?')
    r, th = add(m, odd); work(m, th)
    p = path_of(m, 'x1')
    expect(p and p.startswith(MUSIC + '/') and p.count('/') == 4 and not any(c in p.rsplit('/', 1)[1] for c in ':"<>?*|\\'), f'unsafe characters in a title become underscores ({p})')


def dsd_tests(ctx):
    """A DSD file is added to stock's library after the download; a PCM file is not."""
    expect = ctx.expect
    m = machine(); m.curl_site = server(m)
    d = track('dsd-1', 'Big DSD', suffix='dsf')
    r, th = add(m, d); work(m, th)
    expect(m.scans == ((MUSIC, 0),) and state(m, 'dsd-1')[0] == DL['DONE'], 'after a DSD download stock scans the Navidrome folder (drop 0: nothing is removed from the library)')
    r, th = add(m, track()); work(m, th)
    expect(len(m.scans) == 1, 'a FLAC download does not scan')
    m = machine(); m.curl_site = lambda url, o: dict(rc=22, code=404, body=b'', length=0)
    r, th = add(m, d); work(m, th)
    expect(m.scans == (), 'a failed DSD download does not scan')


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
    m.put(IDX, ('M1PLUS-DL 1\n' 'garbage\n' 'i=\n' f'i=noPath\tt=x\n' f'i=esc\tt=x\tp=../../etc/passwd\n' f'i=g1\tt=Good\tx=flac\tp={gf}\tw=3\n' '\n').encode())
    m.put(f'{MUSIC}/{gf}', b'abc'); m.put('/etc/passwd', b'x')
    expect([r['id'] for r in listing(m)] == ['g1'], 'lines with no id, no file name or a path out of the folder are skipped')
    expect(state(m, 'esc')[0] == DL['NONE'] and state(m, 'g1')[0] == DL['DONE'], 'and are not Downloaded')
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


SECTIONS = [queue_tests, transfer_tests, resume_tests, validator_tests, failure_tests, report_tests, control_tests, collision_tests, dsd_tests, manifest_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

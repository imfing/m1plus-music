"""Track durations (patch/durations.c, patch/covercache.c CC_DURATIONS, patch/homecover.c, patch/albumpage.c; docs/modules/album-page.md "Album length"): the table file (format, lookup by
bisection, corrupt files, merge, prune, a changed size), the CUE math, the TagLib measurement through the worker, the duration text, the album page's total (known, measured in the
background, worker busy, unreadable) and Home's "Measuring tracks" line (phases, saves, stop, resume). The compiled payload runs under Unicorn."""
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


HC, AP = sibling('homecover'), sibling('albumpage')
DUR, TMP = '/mnt/mmc/.m1plus/durations', '/mnt/mmc/.m1plus/durations.tmp'
MAGIC = 0x4e4c314d


def key(path): return fnv(O['FNV_SEED'], path) or 1


def table(entries, magic=MAGIC, count=None, check=None, sort=True):
    """The file's bytes for [(path or key, size, seconds)]: sorted by key unless sort=False (sort=False)."""
    ents = [((key(p) if isinstance(p, str) else p), s, t) for p, s, t in entries]
    if sort: ents.sort()
    body = b''.join(struct.pack('<III', *e) for e in ents)
    h = 2166136261
    for c in body: h = (h ^ c) * 16777619 & 0xffffffff
    return struct.pack('<III', magic, len(ents) if count is None else count, h if check is None else check) + body


def parse(data):
    """[(key, size, seconds)] of a table file, or None when it is not valid."""
    if len(data) < 12 or (len(data) - 12) % 12: return None
    magic, n, check = struct.unpack_from('<III', data)
    body = data[12:]
    h = 2166136261
    for c in body: h = (h ^ c) * 16777619 & 0xffffffff
    ents = [struct.unpack_from('<III', body, 12 * i) for i in range(len(body) // 12)]
    ok = magic == MAGIC and n == len(ents) and check == h and all(ents[i][0] < ents[i + 1][0] for i in range(len(ents) - 1))
    return ents if ok else None


def seeded(entries=(), **kw):
    m = Machine()
    if entries or kw: m.fs[DUR] = table(entries, **kw)
    return m


def fn(m, name, *args, count=40000000):
    return m.call(PSYMS[name], a0=args[0] if args else 0, a1=args[1] if len(args) > 1 else 0, a2=args[2] if len(args) > 2 else 0, a3=args[3] if len(args) > 3 else 0, count=count)


def lookup(m, path, size):
    r = fn(m, 'dur_file', m.cstr(path), size)
    return r - (1 << 32) if r >= 1 << 31 else r


def merge(m, rows):
    a = m.alloc(12 * len(rows) + 4)
    m.u.mem_write(a, b''.join(struct.pack('<III', (key(p) if isinstance(p, str) else p), s, t) for p, s, t in rows))
    r = fn(m, 'dur_merge', a, len(rows))
    return r - (1 << 32) if r >= 1 << 31 else r


def song(m, path, start=0, end=0):
    r = m.record(path=path)
    m.setword(r + O['REC_CUE_START'], start); m.setword(r + O['REC_CUE_END'], end)
    return r


def song_len(m, rec):
    p = m.alloc(4); m.setword(p, 0)
    r = fn(m, 'dur_song', rec, p)
    return (r - (1 << 32) if r >= 1 << 31 else r), m.word(p)


def text_of(m, sec):
    out = m.alloc(160)
    fn(m, 'dur_text', out, 160, sec)
    return m.read_cstr(out)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def table_tests(ctx):
    """1. The file, lookups by bisection, corrupt files, merging, pruning, a changed size."""
    expect = ctx.expect
    paths = [f'/mnt/mmc/lib/{i:04d}.flac' for i in range(2000)]
    rows = sorted((key(p), 1000 + i, 120 + i % 500) for i, p in enumerate(paths))
    m = Machine().count()
    m.fs[DUR] = table(rows)
    fn(m, 'dur_acquire')
    hits = [lookup(m, p, 1000 + i) == 120 + i % 500 for i, p in enumerate(paths)]
    expect(all(hits), 'every one of 2000 entries is found by its path with its size')
    lookup(m, paths[1234], 2234)
    expect(m.icount < 1200, f'a lookup in 2000 entries is a bisection, not a scan ({m.icount} instructions)')
    expect(lookup(m, paths[5], 999) == -1 and lookup(m, '/mnt/mmc/lib/none.flac', 1) == -1 and lookup(m, '', 1) == -1, 'a different size, an unknown path and an empty path are missing (-1)')
    expect(len([c for c in m.calls if c[0] == 'read']) == 0, 'a lookup reads no file (the table was read whole at acquire)')
    fn(m, 'dur_release')

    # a file read once at the first acquire and freed with the last release (acquire/release nest)
    m = seeded([('/a.flac', 10, 100)])
    fn(m, 'dur_acquire'); new = len([c for c in m.calls if c[0] == 'open'])
    fn(m, 'dur_acquire'); new2 = len([c for c in m.calls if c[0] == 'open'])
    expect(new == 1 and new2 == 0 and lookup(m, '/a.flac', 10) == 100, 'the table is read by the first acquire only')
    fn(m, 'dur_release'); expect(lookup(m, '/a.flac', 10) == 100, 'one release of two keeps it')
    fn(m, 'dur_release'); expect(lookup(m, '/a.flac', 10) == -1, 'the last release frees it')

    # corrupt files are ignored: nothing is found, the next merge replaces the file
    good = [(key('/a.flac'), 10, 100), (key('/b.flac'), 20, 200), (key('/c.flac'), 30, 300)]
    sg = sorted(good)
    bad = {
        'wrong magic': table(sg, magic=0x12345678),
        'count mismatch': table(sg, count=2),
        'wrong checksum': table(sg, check=1),
        'unsorted': table(list(reversed(sg)), sort=False),
        'duplicate key': table([sg[0], sg[0]], sort=False),
        'truncated': table(sg)[:-5],
        'cut to the header': table(sg)[:8],
        'garbage': b'\xff' * 100,
        'text': b'1\n',
    }
    for what, data in bad.items():
        m = Machine(); m.fs[DUR] = data
        fn(m, 'dur_acquire')
        expect(all(lookup(m, p, s) == -1 for p, s, _ in [('/a.flac', 10, 0), ('/b.flac', 20, 0), ('/c.flac', 30, 0)]), f'{what}: ignored, every lookup is a miss')
        r = merge(m, [('/z.flac', 5, 77)])
        expect(r == 0 and parse(m.fs[DUR]) == [(key('/z.flac'), 5, 77)], f'{what}: the next merge writes a valid file with only the new entry')
        fn(m, 'dur_release')
    m = Machine(); m.fs[DUR] = table([])
    fn(m, 'dur_acquire'); expect(lookup(m, '/a.flac', 1) == -1, 'a valid empty table is empty'); fn(m, 'dur_release')

    # merge: sorted, deduped, replaces by key, atomic (tmp, fsync, rename)
    m = seeded([('/a.flac', 10, 100), ('/b.flac', 20, 200)])
    fn(m, 'dur_acquire')
    r = merge(m, [('/d.flac', 4, 40), ('/c.flac', 3, 30), ('/a.flac', 11, 111), ('/d.flac', 4, 40)])
    got = parse(m.fs[DUR])
    want = sorted([(key('/a.flac'), 11, 111), (key('/b.flac'), 20, 200), (key('/c.flac'), 3, 30), (key('/d.flac'), 4, 40)])
    expect(r == 0 and got == want, f'merge: sorted, a key twice is one entry, an old entry is replaced by the new measurement ({got})')
    order = [c[0] for c in m.calls if c[0] in ('open', 'write', 'fsync', 'close', 'rename')]
    expect(order == ['open', 'write', 'write', 'fsync', 'close', 'rename', 'open', 'fsync', 'close'] and ('rename', TMP, DUR) in m.calls and TMP not in m.fs, f'written to the .tmp, synced, closed, renamed over the table and the folder synced ({order})')
    expect(lookup(m, '/a.flac', 11) == 111 and lookup(m, '/a.flac', 10) == -1 and lookup(m, '/c.flac', 3) == 30, 'the table in memory has them')
    expect(merge(m, []) == 0 and parse(m.fs[DUR]) == want, 'merging nothing writes nothing')
    # a failed write: -1, the old file stays, no .tmp left, the table in memory still serves this session
    m.fail.add(('fsync', TMP))
    r = merge(m, [('/e.flac', 5, 50)])
    expect(r == -1 and parse(m.fs[DUR]) == want and TMP not in m.fs and lookup(m, '/e.flac', 5) == 50, 'a failed write returns -1, leaves the old file and no .tmp, and the session still has the entry')
    m.fail.clear()
    m.fail.add(('rename', DUR))
    expect(merge(m, [('/f.flac', 6, 60)]) == -1 and parse(m.fs[DUR]) == want and TMP not in m.fs, 'a failed rename likewise')
    fn(m, 'dur_release')
    # no card folder yet: it is made
    m = Machine()
    fn(m, 'dur_acquire'); merge(m, [('/a.flac', 1, 1)]); fn(m, 'dur_release')
    expect('/mnt/mmc/.m1plus' in m.dirs and parse(m.fs.get(DUR, b'')) == [(key('/a.flac'), 1, 1)], 'the first merge makes /mnt/mmc/.m1plus and writes the file')

    # prune: entries no library song names go; an empty pass proves nothing
    m = seeded([('/a.flac', 1, 10), ('/b.flac', 2, 20), ('/c.flac', 3, 30), ('/d.flac', 4, 40)])
    fn(m, 'dur_acquire'); fn(m, 'dur_pass_begin')
    for p in ('/b.flac', '/d.flac', '/unknown.flac'): fn(m, 'dur_pass_seen', m.cstr(p))
    gone = fn(m, 'dur_pass_end')
    expect(gone == 2 and parse(m.fs[DUR]) == sorted([(key('/b.flac'), 2, 20), (key('/d.flac'), 4, 40)]), f'a pass that named b and d drops a and c and writes ({gone})')
    expect(lookup(m, '/a.flac', 1) == -1 and lookup(m, '/b.flac', 2) == 20, 'and the table in memory agrees')
    before = m.fs[DUR]
    fn(m, 'dur_pass_begin'); gone = fn(m, 'dur_pass_end')
    expect(gone == 0 and m.fs[DUR] == before and not [c for c in m.calls if c[0] in ('open', 'write', 'rename')], 'a pass that named no song (a library that did not load) prunes nothing and writes nothing')
    fn(m, 'dur_pass_begin')
    for p in ('/b.flac', '/d.flac'): fn(m, 'dur_pass_seen', m.cstr(p))
    expect(fn(m, 'dur_pass_end') == 0 and not [c for c in m.calls if c[0] == 'write'], 'a pass that names every entry changes nothing and writes nothing')
    fn(m, 'dur_release')

    # a size that changed is a miss: the entry is replaced by the new measurement; an unreadable file (0 seconds) is a hit until its size changes
    m = seeded([('/mnt/mmc/x/1.flac', 5000, 0), ('/mnt/mmc/x/2.flac', 6000, 200)])
    fn(m, 'dur_acquire')
    expect(lookup(m, '/mnt/mmc/x/1.flac', 5000) == 0, 'an unreadable file is stored as 0 seconds and found as 0, not as missing')
    expect(lookup(m, '/mnt/mmc/x/1.flac', 5001) == -1 and lookup(m, '/mnt/mmc/x/2.flac', 6001) == -1, 'its size changing makes it missing again (measured again)')
    for path, size in (('/mnt/mmc/x/1.flac', 5001), ('/mnt/mmc/x/2.flac', 6001)):
        m.files[path] = size; m.present.add(path)
        expect(song_len(m, song(m, path)) == (-1, size), f'{path}: dur_song says missing and hands back the size to measure with')
    merge(m, [('/mnt/mmc/x/2.flac', 6001, 210)])
    expect(song_len(m, song(m, '/mnt/mmc/x/2.flac')) == (210, 0) and lookup(m, '/mnt/mmc/x/2.flac', 6000) == -1, 're-measured: the new size and seconds replace the old entry')
    fn(m, 'dur_release')


def card_tests(ctx):
    """1b. The table lives on the card (/mnt/mmc/.m1plus/durations): nothing is read, written, measured or deleted while the card is out (missing, or held by the computer in USB mode: the player unmounts it); Clear deletes the card's files."""
    expect = ctx.expect
    rows = [('/a.flac', 10, 100), ('/b.flac', 20, 200)]
    touched = lambda m: [c for c in m.calls if c[0] in ('open', 'write', 'rename', 'unlink', 'mkdir', 'fsync')]
    m = Machine(); m.fs[DUR] = table(rows)
    fn(m, 'dur_acquire')
    expect(any(c[:2] == ('open', DUR) for c in m.calls) and lookup(m, '/a.flac', 10) == 100 and not [c for c in m.calls if '/mnt/data' in str(c)],
           'the card present: the table is read from /mnt/mmc/.m1plus/durations (nothing in the internal flash)')
    fn(m, 'dur_release')
    m = Machine(); m.fs[DUR] = table(rows); m.card_mounted = False
    fn(m, 'dur_acquire')
    expect(lookup(m, '/a.flac', 10) == -1 and not touched(m), 'no card or USB mode: no table, the file is not opened')
    expect(merge(m, [('/c.flac', 5, 50)]) == -1 and not touched(m) and m.fs[DUR] == table(rows), 'and a merge writes nothing (no folder made, no .tmp)')
    fn(m, 'dur_clear')
    expect(not touched(m) and DUR in m.fs, 'and Clear deletes nothing under the mount point')
    fn(m, 'dur_release')
    # the album page: no card, no duration and no measuring
    m = album_with_files(); known(m); m.card_mounted = False
    AP.open_album(m)
    expect(foot(m) == '' and 'pthread_create' not in m.names() and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['ab_on_dur']], 'the album page without the card shows no duration and measures nothing')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # Clear: the card's table and its .tmp
    m = Machine(); m.fs[DUR] = table(rows); m.fs[TMP] = b'x'
    fn(m, 'dur_clear')
    expect(DUR not in m.fs and TMP not in m.fs and ('unlink', DUR) in m.calls, 'Clear Track Durations deletes the card file and its .tmp')


def cue_tests(ctx):
    """2. A track's seconds: a CUE track with both ends is end - start without the file; the last one is the file's length less its start; ordinary files; unusable ones are 0."""
    expect = ctx.expect
    m = seeded([('/mnt/mmc/img.flac', 9000, 1500), ('/mnt/mmc/one.flac', 100, 240), ('/mnt/mmc/bad.flac', 77, 0), ('/mnt/mmc/short.flac', 55, 30)])
    for p, s in (('/mnt/mmc/img.flac', 9000), ('/mnt/mmc/one.flac', 100), ('/mnt/mmc/bad.flac', 77), ('/mnt/mmc/short.flac', 55), ('/mnt/mmc/new.flac', 4242)):
        m.files[p] = s; m.present.add(p)
    fn(m, 'dur_acquire')
    expect(song_len(m, song(m, '/mnt/mmc/one.flac')) == (240, 0), 'an ordinary file: its length')
    expect(song_len(m, song(m, '/mnt/mmc/img.flac', 0, 300)) == (300, 0) and song_len(m, song(m, '/mnt/mmc/img.flac', 300, 800)) == (500, 0), 'a CUE track with both ends: end - start')
    unmeasured = song(m, '/mnt/mmc/never.flac', 10, 70)   # no such file: not even looked at
    expect(song_len(m, unmeasured) == (60, 0) and not [c for c in m.calls if c[0] == 'fopen'], 'and it needs neither the table nor the file (nothing is opened)')
    expect(song_len(m, song(m, '/mnt/mmc/img.flac', 1200, 0)) == (300, 0), 'the last CUE track (no end): the file\'s length less its start')
    expect(song_len(m, song(m, '/mnt/mmc/img.flac', 1500, 0)) == (0, 0) and song_len(m, song(m, '/mnt/mmc/img.flac', 1600, 0)) == (0, 0), 'a start at or past the end of the file: 0 (no usable length)')
    expect(song_len(m, song(m, '/mnt/mmc/img.flac', 900, 900)) == (600, 0), 'an end equal to the start is not a CUE end: the file\'s length less the start')
    expect(song_len(m, song(m, '/mnt/mmc/bad.flac')) == (0, 0), 'a file TagLib could not read (0 seconds): 0, and it is not asked for again')
    expect(song_len(m, song(m, '/mnt/mmc/gone.flac')) == (0, 0) and song_len(m, song(m, '')) == (0, 0), 'a file that is not there and an empty path: 0')
    expect(song_len(m, song(m, '/mnt/mmc/new.flac')) == (-1, 4242), 'a file the table lacks: missing, with its size')
    expect(song_len(m, song(m, '/mnt/mmc/short.flac', 40, 0)) == (0, 0), 'a CUE start past a 30 s file: 0')
    fn(m, 'dur_release')


def probe_tests(ctx):
    """3. TagLib's length through the worker: taglib_file_new(path, 1), taglib_file_audioproperties, AudioProperties::length() by the vtable (slot 3), taglib_file_free."""
    expect = ctx.expect
    m = Machine()
    m.durations = {'/mnt/mmc/a.flac': 213, '/mnt/mmc/noprops.mp3': 0, '/mnt/mmc/huge.wav': 100 * 3600 + 5, '/mnt/mmc/disc.iso': 4000, '/mnt/mmc/DISC.ISO': 4000}
    probe = lambda p: fn(m, 'dur_probe', m.cstr(p))
    expect(probe('/mnt/mmc/a.flac') == 213, 'a readable file: its length in seconds')
    c = m.calls
    expect(('taglib_file_new', '/mnt/mmc/a.flac', 1) in c and 'taglib_length' in m.names() and m.names().count('taglib_file_free') == 1,
           'taglib_file_new(path, 1) with the audio properties, length() through the vtable, and the file freed')
    expect(probe('/mnt/mmc/noprops.mp3') == 0 and m.names().count('taglib_file_free') == 1 and 'taglib_length' not in m.names(), 'no audio properties: 0, the file still freed')
    expect(probe('/mnt/mmc/unreadable.xyz') == 0 and 'taglib_file_free' not in m.names(), 'taglib_file_new fails: 0, nothing to free')
    expect(probe('/mnt/mmc/huge.wav') == 0, 'an absurd length (over 100 hours) is not recorded as a length')
    expect(probe('/mnt/mmc/disc.iso') == 0 and probe('/mnt/mmc/DISC.ISO') == 0 and 'taglib_file_new' not in m.names(), 'a disc image (.iso, any case) is never opened, as stock never reads its properties')
    expect(probe('') == 0 and probe('a') == 0, 'an empty or one letter path is safe')

    # through the shared worker: a CC_DURATIONS set measures its files, writes nothing to the card, and one file is one job
    m = Machine()
    m.durations = {'/mnt/mmc/a.flac': 100, '/mnt/mmc/b.flac': 200, '/mnt/mmc/c.flac': 0}
    fn(m, 'cc_build_open', 10, 2)
    adds = [fn(m, 'cc_build_add_dur', m.cstr(p), key(p), s) for p, s in (('/mnt/mmc/a.flac', 11), ('/mnt/mmc/b.flac', 22), ('/mnt/mmc/c.flac', 33), ('/mnt/mmc/a.flac', 11), ('/mnt/mmc/gone.flac', 44))]
    expect(adds == [1, 1, 1, 0, 1], f'one job per file (a second add of a path is refused: {adds})')
    expect(fn(m, 'cc_build_add', m.cstr('/mnt/mmc/a.flac'), 7) == 0, 'a cover job cannot join a durations set')
    expect(fn(m, 'cc_build_start') == 1 and 'statfs' not in m.names() and not [c for c in m.calls if c[0] == 'mkdir'] and build_state(m)['mode'] == 2, 'it starts without the card: no free space check, no cache folder made')
    m.call(PSYMS['cc_worker'], count=20000000)
    expect(build_durs(m) == [('/mnt/mmc/a.flac', key('/mnt/mmc/a.flac'), 11, 100), ('/mnt/mmc/b.flac', key('/mnt/mmc/b.flac'), 22, 200), ('/mnt/mmc/c.flac', key('/mnt/mmc/c.flac'), 33, 0),
                            ('/mnt/mmc/gone.flac', key('/mnt/mmc/gone.flac'), 44, 0)], 'seconds per job: measured, 0 for a file TagLib reads no properties of, 0 for one it cannot open')
    s = build_state(m)
    expect(s['done'] == 4 and s['total'] == 4, 'the done counter reached the total')
    out = [m.alloc(4) for _ in range(3)]
    expect(fn(m, 'cc_build_dur', 1, *out) == 1 and [m.word(o) for o in out] == [key('/mnt/mmc/b.flac'), 22, 200] and fn(m, 'cc_build_dur', 4, *out) == 0, 'a finished job is read back (key, size, seconds); one that is not finished is refused')
    fn(m, 'cc_build_stop')
    # a cover set refuses durations jobs; a full set says so
    fn(m, 'cc_build_open', 1, 0)
    expect(fn(m, 'cc_build_add_dur', m.cstr('/x.flac'), 5, 1) == 0, 'a cover set refuses a length job')
    fn(m, 'cc_build_stop')
    fn(m, 'cc_build_open', 1, 2)
    expect(fn(m, 'cc_build_add_dur', m.cstr('/x.flac'), 5, 1) == 1 and (fn(m, 'cc_build_add_dur', m.cstr('/y.flac'), 6, 1) & 0xffffffff) == 0xffffffff, 'a full set: -1')
    fn(m, 'cc_build_stop')


def text_tests(ctx):
    """4. "49 minutes", "1 hour, 12 minutes": rounded to the minute, Apple's singular and plural, translated."""
    expect = ctx.expect
    m = Machine()
    cases = [(0, '1 minute'), (29, '1 minute'), (30, '1 minute'), (89, '1 minute'), (90, '2 minutes'), (49 * 60, '49 minutes'), (49 * 60 + 29, '49 minutes'), (49 * 60 + 30, '50 minutes'),
             (59 * 60, '59 minutes'), (59 * 60 + 29, '59 minutes'), (59 * 60 + 30, '1 hour'), (3600, '1 hour'), (3600 + 12 * 60, '1 hour, 12 minutes'), (3600 + 60, '1 hour, 1 minute'),
             (2 * 3600, '2 hours'), (2 * 3600 + 60, '2 hours, 1 minute'), (2 * 3600 + 25 * 60, '2 hours, 25 minutes'), (25 * 3600, '25 hours')]
    bad = [(s, text_of(m, s), w) for s, w in cases if text_of(m, s) != w]
    expect(not bad, f'English: {bad}')
    out = m.alloc(8); fn(m, 'dur_text', out, 8, 3600 + 12 * 60)
    expect(m.read_cstr(out) == '1 hour,' or len(m.read_cstr(out)) < 8, 'a small buffer is cut, not overrun')
    # the track count and the duration in one phrase: the translation puts the number and the text where the language wants them
    o = m.alloc(64)

    def subst(m, name, out, size, f, n, s1, s2):   # six arguments: the last two are on the stack (o32: sp + 16, sp + 20)
        m.setword(STACK + 16, s1); m.setword(STACK + 20, s2)
        return m.call(PSYMS[name], a0=out, a1=size, a2=f, a3=n, count=2000000)
    for f, want in (('%d tracks, %s', '13 tracks, 49 minutes'), ('%d 首歌曲，%s', '13 首歌曲，49 minutes'), ('Utwory: %d, %s', 'Utwory: 13, 49 minutes'), ('no placeholders', 'no placeholders'), ('%s only', '49 minutes only')):
        subst(m, 'dur_subst', o, 64, m.cstr(f), 13, m.cstr('49 minutes'), 0)
        expect(m.read_cstr(o).encode('latin-1').decode('utf-8') == want, f'dur_subst({f!r}) = {want!r}')
    subst(m, 'dur_subst', o, 64, m.cstr('%d, %s, %s'), 7, m.cstr('a'), m.cstr('b'))
    expect(m.read_cstr(o) == '7, a, b', 'the second %s is the second string')
    subst(m, 'dur_subst', o, 6, m.cstr('%d tracks, %s'), 13, m.cstr('49 minutes'), 0)
    expect(m.read_cstr(o) == '13 tr', 'cut at the buffer')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
SIZES = [10_000_000 + 1000 * i for i in range(8)]
SECS = [200, 300, 400, 500, 250, 350, 450, 291]   # 2745 s = 45.75 minutes = 46


def album_with_files(n=8, cover='file', **kw):
    m = AP.album_machine(n=n, cover=cover, **kw)
    for i in range(n):
        m.files[f'/mnt/mmc/m/{i}.flac'] = SIZES[i]
    return m


def known(m, secs=SECS, n=8):
    m.fs[DUR] = table([(f'/mnt/mmc/m/{i}.flac', SIZES[i], secs[i]) for i in range(n)])


def meta(m): return AP.utf(m.wtext[m.widgets['ab_meta']])


def foot(m):
    """The footer's text while it is shown ('' when hidden)."""
    w = m.widgets['ab_foot']
    return AP.utf(m.wtext.get(w, '')) if m.props.get((w, 'visible'), 1) else ''


def both(m): return f'{meta(m)}|{foot(m)}'


def album_tests(ctx):
    """5. The album page: the total when every length is known, the missing ones measured by the worker in the background, the worker busy, an unreadable track."""
    expect = ctx.expect
    DURS = PSYMS['ab_on_dur']

    # every length known: the total is in the line at once, no worker
    m = album_with_files(); known(m)
    AP.open_album(m)
    expect(both(m) == '1959 · 8 tracks|8 tracks, 46 minutes', f'known durations: "year · N tracks, M minutes" ({both(m)})')
    expect('pthread_create' not in m.names() and build_state(m)['jobs'] == 0 and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == DURS], 'and nothing is measured')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a long album: hours; one track: singular
    m = album_with_files(); known(m, secs=[1300] * 8)
    m.measure = lambda t: 6 * len(t)
    AP.open_album(m); expect(both(m) == '1959 · 8 tracks|8 tracks, 2 hours, 53 minutes', f'10400 s: hours and minutes ({both(m)})'); m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = album_with_files(n=1); known(m, n=1)
    AP.open_album(m); expect(both(m) == '1959 · 1 track|1 track, 3 minutes', f'one track: singular ({both(m)})'); m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = album_with_files(year=0); known(m)
    AP.open_album(m); expect(both(m) == '8 tracks|8 tracks, 46 minutes', f'no year: "{both(m)}"'); m.call(PSYMS['ab_on_destroy'], count=4000000)

    # CUE tracks with both ends add up without the table; the last one is the file's length less its start
    m = album_with_files(n=3)
    for i, (s, e) in enumerate(((0, 600), (600, 1500), (1500, 0))): m.setword(m.songs[i] + O['REC_CUE_START'], s); m.setword(m.songs[i] + O['REC_CUE_END'], e); m.setword(m.songs[i] + O['REC_PATH'], m.cstr('/mnt/mmc/m/0.flac'))
    m.files['/mnt/mmc/m/0.flac'] = 777
    m.fs[DUR] = table([('/mnt/mmc/m/0.flac', 777, 2100)])
    AP.open_album(m)
    expect(both(m) == '1959 · 3 tracks|3 tracks, 35 minutes', f'CUE image of 2100 s in three tracks: 600 + 900 + 600 s = 35 minutes ({both(m)})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = album_with_files(n=3)
    for i, (s, e) in enumerate(((0, 600), (600, 1500), (1500, 0))): m.setword(m.songs[i] + O['REC_CUE_START'], s); m.setword(m.songs[i] + O['REC_CUE_END'], e); m.setword(m.songs[i] + O['REC_PATH'], m.cstr('/mnt/mmc/m/0.flac'))
    m.files['/mnt/mmc/m/0.flac'] = 777; m.durations['/mnt/mmc/m/0.flac'] = 2100
    AP.open_album(m)
    jobs = build_durs(m)
    expect(build_state(m)['mode'] == 2 and len(jobs) == 1 and jobs[0][0] == '/mnt/mmc/m/0.flac', f'only the last CUE track needs the file: one job for the image ({jobs})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # nothing known: one durations set for this album, polled; the line has no duration until all are measured
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    AP.open_album(m)
    s, jobs = build_state(m), build_durs(m)
    expect(s['mode'] == 2 and s['running'] == 1 and s['total'] == 8 and [(j[0], j[2]) for j in jobs] == [(f'/mnt/mmc/m/{i}.flac', SIZES[i]) for i in range(8)], f'a CC_DURATIONS set with the 8 files and their sizes ({s}, {jobs[:2]})')
    expect(both(m) == '1959 · 8 tracks|' and any(c[0] == 'timer_add' and c[1] == DURS and c[2] == 400 for c in m.calls), 'no duration yet; polled every 400 ms')
    new = fired(m, 'ab_on_dur')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == DURS] and not [c for c in new if c[0] == 'pthread_join'] and both(m) == '1959 · 8 tracks|', 'a poll with the worker running re-arms itself and changes nothing')
    m.call(PSYMS['cc_worker'], count=40000000)
    new = fired(m, 'ab_on_dur', 80000000)
    expect([c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] == 0 and not [c for c in new if c[0] == 'timer_add' and c[1] == DURS], 'the worker done: joined, the set freed, no more polls')
    expect(both(m) == '1959 · 8 tracks|8 tracks, 46 minutes', f'the line now has the total ({both(m)})')
    ents = parse(m.fs[DUR])
    expect(ents is not None and len(ents) == 8 and sorted((k, sz, t) for k, sz, t in ents) == sorted((key(f'/mnt/mmc/m/{i}.flac'), SIZES[i], SECS[i]) for i in range(8)), 'and the measured durations were saved to the table')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # the next visit finds them: no worker
    m.present |= set(); m.calls = []
    m2 = album_with_files(); m2.fs[DUR] = m.fs[DUR]
    AP.open_album(m2)
    expect(both(m2) == '1959 · 8 tracks|8 tracks, 46 minutes' and 'pthread_create' not in m2.names(), 'opened again: the total at once, nothing measured')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)

    # only the missing tracks are measured; a track whose size changed is missing
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    m.fs[DUR] = table([(f'/mnt/mmc/m/{i}.flac', SIZES[i] + (1 if i == 3 else 0), SECS[i] + 99) for i in range(8) if i != 5])
    AP.open_album(m)
    jobs = build_durs(m)
    expect(sorted(j[0] for j in jobs) == ['/mnt/mmc/m/3.flac', '/mnt/mmc/m/5.flac'], f'one track absent, one with another size: just those two ({[j[0] for j in jobs]})')
    m.call(PSYMS['cc_worker'], count=40000000); fired(m, 'ab_on_dur', 80000000)
    ents = {k: (sz, t) for k, sz, t in parse(m.fs[DUR])}
    expect(both(m) == f'1959 · 8 tracks|8 tracks, {(sum(SECS[i] + (99 if i not in (3, 5) else 0) for i in range(8)) + 30) // 60} minutes' and ents[key('/mnt/mmc/m/3.flac')] == (SIZES[3], SECS[3]) and ents[key('/mnt/mmc/m/0.flac')] == (SIZES[0], SECS[0] + 99),
           f'the two were measured, the others kept ({both(m)})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # the worker busy (another page's set): no duration, nothing started, nothing left behind
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    fn(m, 'cc_build_open', 3, 0)
    AP.open_album(m)
    expect(both(m) == '1959 · 8 tracks|' and 'pthread_create' not in m.names() and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == DURS] and build_state(m)['total'] == 0, 'the worker is held by another set: the duration is omitted, the held set is untouched')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(build_state(m)['jobs'] != 0, 'closing the page leaves the other owner\'s set alone')
    fn(m, 'cc_build_stop')

    # an unreadable track: the total is omitted for good (and the file is not measured again while its size is the same)
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}; m.durations['/mnt/mmc/m/6.flac'] = 0
    AP.open_album(m); m.call(PSYMS['cc_worker'], count=40000000); fired(m, 'ab_on_dur', 80000000)
    expect(both(m) == '1959 · 8 tracks|' and build_state(m)['jobs'] == 0 and dict((k, t) for k, _, t in parse(m.fs[DUR]))[key('/mnt/mmc/m/6.flac')] == 0, 'one track TagLib cannot read: no duration, and its 0 is in the table')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    m2 = album_with_files(); m2.fs[DUR] = m.fs[DUR]
    AP.open_album(m2)
    expect(both(m2) == '1959 · 8 tracks|' and 'pthread_create' not in m2.names(), 'opened again: still no duration, and nothing is measured again')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # a track without a file (storage unplugged): nothing to measure, no duration
    m = album_with_files(); del m.files['/mnt/mmc/m/2.flac']
    AP.open_album(m)
    expect(both(m) == '1959 · 8 tracks|' and 'pthread_create' not in m.names(), 'a track whose file cannot be opened: no duration, nothing started')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # the cover first: the worker makes the cover, then (the poll that sees it done) the durations
    m = album_with_files(cover=None); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    AP.open_album(m)
    expect(build_state(m)['mode'] == 0 and build_state(m)['total'] == 1 and not [c for c in m.calls if c[0] == 'timer_add' and c[1] == DURS], 'a missing cover is the worker\'s first job; durations wait')
    m.present.add(m.cover_path); m.files[m.cover_path] = 4096
    m.images['file://' + m.cover_path] = (168, 168, bytes(AP.RED + (255,)) * (168 * 168))
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    new = fired(m, 'ab_on_cover', 200000000)
    expect(build_state(m)['mode'] == 2 and build_state(m)['total'] == 8 and [c for c in new if c[0] == 'timer_add' and c[1] == DURS], 'the cover done: the durations set starts at once')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # leaving the page mid-measurement: the worker is cancelled without a join (it keeps the set until it exits); what finished is not saved by the page (the next visit measures again)
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    AP.open_album(m)
    m.call(PSYMS['ab_on_destroy'], count=8000000)
    expect(build_state(m)['orphan'] == 1 and 'pthread_join' not in m.names(), 'destroyed mid-measurement: cancelled, orphaned, not joined')
    expect(not [c for c in fired(m, 'ab_on_dur') if c[0] in ('timer_add', 'widget_set_text_utf8')], 'a late poll does nothing')


def footer_tests(ctx):
    """6. The footer under the last row: asset, geometry, scroll height, hidden while unknown, appearing without moving the list, inert in select mode, the same grey as the header, fit and wording in every language."""
    expect = ctx.expect
    HDR, ROW = O['AH_HDR_H'], O['LIST_ROW_H']
    # the asset: a hidden, insensitive 15 px #AAAAAA left-aligned label in the content view
    tree = AP.ui()
    node = tree.find('ab_foot')
    expect(node is not None and node.type == 'label' and node.get('visible') == 'false' and node.get('sensitive') == 'false' and node.get('style:normal:font_size') == '15'
           and node.get('style:normal:text_color') == '#AAAAAA' and node.get('style:normal:text_align_h') == 'left' and node.get('style:normal:text_align_v') == 'middle', 'ab_foot: a hidden and insensitive 15 px #AAAAAA label')
    expect(tree.find('ab_foot_date') is None, 'there is no year label')
    expect(tree.find('ab_meta').get('style:normal:text_color') == '#9C9C9C' and O['AB_FOOT_PX'] == 15 and O['AB_FOOT_GAP'] + O['AB_FOOT_TEXT_H'] + O['AB_FOOT_PAD'] == 52, 'the header\'s line is as it was; the footer is 14 + 20 + 18 = 52 px of content')
    rows_end = HDR + 8 * ROW
    GAP, LINE, PAD, X = O['AB_FOOT_GAP'], O['AB_FOOT_TEXT_H'], O['AB_FOOT_PAD'], O['AB_NUM_X']
    vh = lambda m: m.props[(m.sv, 'virtual_h')]

    # known: the count line from the number column's left edge (x 12), 14 px under the last row; the content is 52 px longer
    m = album_with_files(); known(m)
    AP.open_album(m)
    f = m.widgets['ab_foot']
    expect(foot(m) == '8 tracks, 46 minutes' and meta(m) == '1959 · 8 tracks', f'the footer reads "8 tracks, 46 minutes", the header line is as before ({foot(m)!r}, {meta(m)!r})')
    expect(('widget_move', f, X, rows_end + GAP) in m.calls and ('widget_resize', f, 320 - X - 10, LINE) in m.calls, f'at x {X} (the number column), {GAP} px under the last row, {LINE} px high')
    expect(vh(m) == rows_end + GAP + LINE + PAD, f'the scroll height includes it and the {PAD} px under it ({vh(m)})')
    expect(('widget_set_sensitive', f, 1) not in m.calls and m.props.get((f, 'visible')) == 1, 'it is shown and never made sensitive')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # three digit numbers do not move it
    m = AP.album_machine(n=130)
    for i in range(130): m.files[f'/mnt/mmc/m/{i}.flac'] = 10_000_000 + i
    m.fs[DUR] = table([(f'/mnt/mmc/m/{i}.flac', 10_000_000 + i, 200) for i in range(130)])
    AP.open_album(m)
    expect(('widget_move', m.widgets['ab_foot'], X, HDR + 130 * ROW + GAP) in m.calls and foot(m) == '130 tracks, 7 hours, 13 minutes', f'130 tracks: the footer is still at x {X} ({foot(m)!r})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # unknown (the worker is held by another owner): no footer, no band
    m = album_with_files()
    fn(m, 'cc_build_open', 3, 0)
    AP.open_album(m)
    expect(foot(m) == '' and m.props.get((m.widgets['ab_foot'], 'visible'), 0) == 0 and vh(m) == rows_end, 'duration unknown: the footer is hidden and the content ends at the last row (no empty band)')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    fn(m, 'cc_build_stop')

    # it appears when the background measurement ends, without moving the list
    m = album_with_files(); m.durations = {f'/mnt/mmc/m/{i}.flac': SECS[i] for i in range(8)}
    AP.open_album(m)
    AP.scroll_to(m, 120)
    m.call(PSYMS['cc_worker'], count=40000000)
    fired(m, 'ab_on_dur', 80000000)
    expect(foot(m) == '8 tracks, 46 minutes' and AP.off_of(m) == 120 and vh(m) == rows_end + GAP + LINE + PAD, 'measured in the background: the footer appears, the content grows, the scroll offset stays')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # select mode: the footer takes no touch, no mark, no press, is not counted by All, and does not shift
    m = album_with_files(); known(m)
    AP.open_album(m)
    AP.click(m, 'btn_select')
    AP.scroll_to(m, 150)
    AP.tap(m, 30, rows_end + GAP + 10 - 150); AP.tap(m, 60, rows_end + 3 - 150)
    blits, texts, fills = AP.paint(m)
    marks = [b for b in blits if b[2][2] == O['SG_MARK']]
    expect(marks and len({b[0] for b in marks}) == 1 and not any(f_[0] == O['AB_PRESS'] for f_ in fills), 'a tap on the footer or the air above it marks nothing and presses nothing')
    AP.click(m, 'btn_selall')
    calls = AP.click(m, 'sg_add')
    expect([c[1] for c in calls if c[0] == 'set_selectindex'] == list(range(8)), f'All selects the eight tracks and nothing else ({[c[1] for c in calls if c[0] == "set_selectindex"]})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # fit and wording, every language, with the built font: the footer's label is 268 px wide from x 42 (258 from x 52)
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    px = lambda t: StbText(font, 15).layout(t)[1]
    widest = {}
    for loc in pod_i18n.LOCALES:
        for h, mi in ((0, 59), (1, 1), (2, 59), (9, 59), (24, 59), (1, 12)):
            for n in (9, 99, 999):
                widest[loc] = max(widest.get(loc, 0), px(phrase(built[loc], n, h, mi)))
    room = 320 - O['AB_NUM_X'] - O['AB_FOOT_R']
    expect(max(widest.values()) <= room, f'"999 tracks, 24 hours, 59 minutes" fits the 298 px footer line in all 13 languages (widest {max(widest.values()):.0f} of {room} px: {max(widest, key=widest.get)})')
    expect(foot_words(built['zh_CN']) == ('13 首歌，49 分钟', '1 首歌，2 分钟', '13 首歌，1 小时 12 分钟') and foot_words(built['zh_HK']) == ('13 首歌，49 分鐘', '1 首歌，2 分鐘', '13 首歌，1 小時 12 分鐘')
           and foot_words(built['ja_JP']) == ('13曲、49分', '1曲、2分', '13曲、1時間12分') and foot_words(built['ko_KR']) == ('13곡, 49분', '1곡, 2분', '13곡, 1시간 12분'),
           f'Chinese, Japanese and Korean read as Apple writes them, each with its own hours-and-minutes join ({foot_words(built["zh_CN"])}, {foot_words(built["ja_JP"])}, {foot_words(built["ko_KR"])})')
    expect(foot_words(built['en_US']) == ('13 tracks, 49 minutes', '1 track, 2 minutes', '13 tracks, 1 hour, 12 minutes') and foot_words(built['fr_FR'])[2] == '13 titres, 1 heure, 12 minutes' and foot_words(built['ge_DE'])[2] == '13 Titel, 1 Stunde, 12 Minuten',
           'the Latin languages keep the comma')
    # and through the payload in a CJK language: the compiled text equals the model
    m = Machine(); m.set_language('zh_CN')
    expect(text_of(m, 3600 + 12 * 60) == '1 小时 12 分钟'.encode('utf-8').decode('latin-1') and text_of(m, 49 * 60) == '49 分钟'.encode('utf-8').decode('latin-1'), 'dur_text in zh_CN: "1 小时 12 分钟", "49 分钟"')
    m.set_language('ja_JP')
    expect(text_of(m, 3600 + 12 * 60) == '1時間12分'.encode('utf-8').decode('latin-1'), 'dur_text in ja_JP: "1時間12分"')


def phrase(b, n, h, mi):
    """The footer's text as the payload builds it from the language table b."""
    one = lambda k1, k2, v: b[k1 if v == 1 else k2].replace('%d', str(v))
    if not h: dur = one('%d minute', '%d minutes', mi)
    elif not mi: dur = one('%d hour', '%d hours', h)
    else:
        key = ('%d hour' if h == 1 else '%d hours') + ', ' + ('%d minute' if mi == 1 else '%d minutes')
        dur = b[key].replace('%d', str(h), 1).replace('%d', str(mi), 1)
    return b['%d track, %s' if n == 1 else '%d tracks, %s'].replace('%d', str(n)).replace('%s', dur)


def foot_words(b): return phrase(b, 13, 0, 49), phrase(b, 1, 0, 2), phrase(b, 13, 1, 12)


def home_tests(ctx):
    """7. Home: after the covers, "Measuring tracks n/m" for the library songs the table lacks; saved as it goes; stops on background and destroy; pruned; resumes."""
    expect = ctx.expect
    LSCAN, LPOLL, START = PSYMS['hc_on_dscan'], PSYMS['hc_on_dpoll'], PSYMS['hc_on_start']
    paths = lambda n: [f'/mnt/mmc/m/{i}/1.flac' for i in range(n)]

    def machine(n=6, missing=(), seed=(), **kw):
        m = HC.home_machine(n, missing=missing, **kw)
        m.durations = {}
        m.class_lists.pop(O['CLASS_ALL_SONGS'], None)   # the albums' records double as the library's songs
        for i, p in enumerate(paths(n)):
            m.files[p] = 5_000_000 + i; m.durations[p] = 100 + i
        if seed: m.fs[DUR] = table(seed)
        return m

    def lscan(m, limit=60):
        for _ in range(limit):
            new = fired(m, 'hc_on_dscan', 400000000)
            if not [c for c in new if c[0] == 'timer_add' and c[1] == LSCAN]: return new
        raise AssertionError('the song scan did not end')

    def finish(m, n):
        m.call(PSYMS['cc_worker'], count=200000000)

    # 1. Covers complete, the table empty: the song pass starts where the cover scan found nothing; the line shows Measuring tracks 0/6
    m = machine(6)
    new = HC.scan(m)
    expect([c for c in new if c[0] == 'timer_add' and c[1] == LSCAN] and 'pthread_create' not in [c[0] for c in new], 'a complete cover cache: no cover worker, the song scan is armed')
    expect(HC.pill_up(m) and HC.texts(m, new, waiting=True)[-1:] == ['Checking library.'] and not HC.texts(m, new), 'while the songs are only looked up the pill waits: "Checking library…", no count')
    new = lscan(m)
    s = build_state(m)
    expect(s['mode'] == 2 and s['running'] == 1 and s['total'] == 6 and [j[0] for j in build_durs(m)] == paths(6), f'a CC_DURATIONS worker with the six songs ({s})')
    expect(HC.pill_up(m) and HC.texts(m, new) == ['Measuring tracks 0/6'], f'"Measuring tracks 0/6" is shown ({HC.texts(m, new)})')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == LPOLL and c[2] == 500], 'polled every 500 ms')

    # 2. The poll shows n/m; the end saves, hides, restores, joins
    m.setword(PSYMS['cb'] + 4 * 5, 3)
    new = fired(m, 'hc_on_dpoll')
    expect(HC.texts(m, new) == ['Measuring tracks 3/6'] and [c for c in new if c[0] == 'timer_add' and c[1] == LPOLL] and not HC.shown_calls(m, new), 'part way: "3/6", the poll re-arms')
    expect(not [c for c in fired(m, 'hc_on_dpoll') if c[0] == 'widget_set_text_utf8'], 'a poll with no advance rewrites nothing')
    m.setword(PSYMS['cb'] + 4 * 5, 0)
    finish(m, 6)
    new = fired(m, 'hc_on_dpoll', 80000000)
    ents = parse(m.fs[DUR])
    expect(ents is not None and sorted(ents) == sorted((key(p), 5_000_000 + i, 100 + i) for i, p in enumerate(paths(6))), 'done: every measured length was merged into the table and written')
    expect(HC.shown_calls(m, new) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)] and ('widget_move', HC.lv(m), 0, O['HOME_PAD']) in new and build_state(m)['jobs'] == 0 and 'pthread_join' in [c[0] for c in new]
           and not [c for c in new if c[0] == 'timer_add'], 'the line is hidden and insensitive, the list is back, the worker joined, the set freed, no more timers')

    # 3. A complete table: nothing is queued, nothing is shown, and the next foreground does not read the library again
    m = machine(6, seed=[(p, 5_000_000 + i, 100 + i) for i, p in enumerate(paths(6))])
    HC.scan(m); new = lscan(m)
    expect(build_state(m)['jobs'] == 0 and not HC.pill_up(m) and 'pthread_create' not in [c[0] for c in new], 'every song in the table: no worker, no line')
    new = HC.hook(m, 'hc_on_foreground'); new = HC.scan(m)
    expect('loadLocalClassList' not in [c[0] for c in new if c[1:] == (O['CLASS_ALL_SONGS'],)], 'a library found complete is not read again at the next foreground')
    # ... until the library changed (another album count) or the table was cleared
    m.showlist.append(m.record(album='Album 99', artist='Artist 99', path='/mnt/mmc/m/99/1.flac', rid=99)); m.present.add('/mnt/mmc/m/99/1.flac')
    m.files[art_file(album_key('Artist 99', 'Album 99'))] = 4096; m.present.add(art_file(album_key('Artist 99', 'Album 99'))); m.files[HC.artist_file('Artist 99')] = 0; m.present.add(HC.artist_file('Artist 99'))
    m.files['/mnt/mmc/m/99/1.flac'] = 123; m.durations['/mnt/mmc/m/99/1.flac'] = 99
    HC.hook(m, 'hc_on_foreground'); new = HC.scan(m)
    expect([c for c in new if c[0] == 'loadLocalClassList' and c[1] == O['CLASS_ALL_SONGS']], 'a new album: the songs are read again')
    new = lscan(m)
    expect([j[0] for j in build_durs(m)] == ['/mnt/mmc/m/99/1.flac'], 'and only the song the table lacks is queued')
    HC.hook(m, 'hc_on_background')
    # ... and also when one album was replaced by another (the same count, another key sum)
    m = machine(6, seed=[(p, 5_000_000 + i, 100 + i) for i, p in enumerate(paths(6))])
    HC.scan(m); lscan(m)
    m.showlist[0] = m.record(album='Album 98', artist='Artist 98', path='/mnt/mmc/m/98/1.flac', rid=98); m.present.add('/mnt/mmc/m/98/1.flac')
    m.files[art_file(album_key('Artist 98', 'Album 98'))] = 4096; m.present.add(art_file(album_key('Artist 98', 'Album 98'))); m.files[HC.artist_file('Artist 98')] = 0; m.present.add(HC.artist_file('Artist 98'))
    m.files['/mnt/mmc/m/98/1.flac'] = 123; m.durations['/mnt/mmc/m/98/1.flac'] = 98
    HC.hook(m, 'hc_on_foreground'); new = HC.scan(m)
    expect([c for c in new if c[0] == 'loadLocalClassList' and c[1] == O['CLASS_ALL_SONGS']], 'an album replaced (same count): the songs are read again')
    lscan(m)
    expect([j[0] for j in build_durs(m)] == ['/mnt/mmc/m/98/1.flac'], 'and the new album\'s song is queued, not stamped unmeasured')
    HC.hook(m, 'hc_on_background')

    # 4. A song whose entry has another size is not re-measured by Home (it costs no stat per song); an entry with 0 seconds is not tried again
    m = machine(4, seed=[(paths(4)[0], 1, 50), (paths(4)[1], 5_000_001, 0)])
    HC.scan(m); lscan(m)
    expect([j[0] for j in build_durs(m)] == paths(4)[2:], 'songs in the table (any size, also 0 seconds) are not queued: Home only fills what is absent')
    expect(not [c for c in m.calls if c[0] == 'fopen' and c[1] in paths(4)[:2]], 'and their files are not stat\'ed')

    # 5. Prune: entries of songs the library no longer has go (from the in-memory list only), before measuring
    gone = '/mnt/mmc/old/deleted.flac'
    m = machine(4, seed=[(gone, 9, 90)] + [(p, 5_000_000 + i, 100 + i) for i, p in enumerate(paths(4))])
    HC.scan(m); new = lscan(m)
    ents = parse(m.fs[DUR])
    expect(ents is not None and key(gone) not in [e[0] for e in ents] and len(ents) == 4, 'the entry of a file no song names is pruned and the table rewritten')
    expect(not [c for c in m.calls if c[0] == 'fopen' and c[1] == gone] and not [c for c in m.calls if c[0] in ('access', 'unlink') and c[1] == gone], 'pruning touches no file: only the library list')

    # 6. CUE tracks: both ends is no job; the same image once
    m = machine(4)
    for i in (0, 1): m.setword(m.showlist[i] + O['REC_CUE_START'], 100 * i); m.setword(m.showlist[i] + O['REC_CUE_END'], 100 * i + 100)
    m.setword(m.showlist[3] + O['REC_PATH'], m.cstr(paths(4)[2]))
    HC.scan(m); lscan(m)
    expect([j[0] for j in build_durs(m)] == [paths(4)[2]], f'two CUE tracks with both ends are not measured; two songs of one file are one job ({[j[0] for j in build_durs(m)]})')
    HC.hook(m, 'hc_on_background')

    # 7. Background mid-run: what the worker finished is saved, the worker joined, the line hidden; the foreground starts again and finds the rest
    m = machine(6)
    HC.scan(m); lscan(m)
    finish(m, 6); m.setword(PSYMS['cb'] + 4 * 5, 2)   # two of the six are done
    new = HC.hook(m, 'hc_on_background', count=80000000)
    ents = parse(m.fs[DUR])
    expect(ents is not None and sorted(e[0] for e in ents) == sorted(key(p) for p in paths(6)[:2]), 'to the background: the two finished durations are saved')
    expect([c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] == 0 and HC.shown_calls(m, new) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'and the worker is joined, the set freed, the line hidden')
    new = HC.hook(m, 'hc_on_foreground')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == START], 'the next foreground offers the scan again')
    HC.scan(m); lscan(m)
    expect([j[0] for j in build_durs(m)] == paths(6)[2:], f'and only the four songs not yet measured are queued ({[j[0] for j in build_durs(m)]})')
    HC.hook(m, 'hc_on_destroy', count=80000000)
    expect(build_state(m)['orphan'] == 1 and 'pthread_join' not in m.names(), 'destroy stops the worker too (orphaned, not joined)')
    expect(not [c for c in fired(m, 'hc_on_dpoll') if c[0] in ('timer_add', 'widget_set_text_utf8')], 'a late poll does nothing')

    # 8. Saved as it goes: every HC_LSAVE finished songs
    n = 700
    m = machine(n)
    HC.scan(m); lscan(m, 200)
    finish(m, n)
    m.setword(PSYMS['cb'] + 4 * 5, 499)
    fired(m, 'hc_on_dpoll', 80000000)
    expect(DUR not in m.fs, '499 finished: not saved yet')
    m.setword(PSYMS['cb'] + 4 * 5, 600)
    fired(m, 'hc_on_dpoll', 200000000)
    ents = parse(m.fs.get(DUR, b''))
    expect(ents is not None and len(ents) == 600, f'600 finished: saved ({len(ents or [])} entries)')
    m.setword(PSYMS['cb'] + 4 * 5, n)
    fired(m, 'hc_on_dpoll', 200000000)
    expect(len(parse(m.fs[DUR])) == n, 'at the end the rest is merged')

    # 9. After the covers: the covers are built first (the cover line), then the song pass
    m = machine(4, missing={1})
    HC.scan(m)
    expect(build_state(m)['mode'] == 0 and build_state(m)['total'] == 1, 'covers missing: the cover worker comes first')
    HC.finish_worker(m, (1,))
    new = fired(m, 'hc_on_poll', 80000000)
    expect([c for c in new if c[0] == 'timer_add' and c[1] == LSCAN] and HC.shown_calls(m, new) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'the cover set done: the cover line is hidden and the song scan armed')
    new = lscan(m)
    expect(HC.texts(m, new) == ['Measuring tracks 0/4'] and build_state(m)['mode'] == 2, 'then "Measuring tracks 0/4"')
    HC.hook(m, 'hc_on_background')

    # 10. Another owner holds the worker: nothing is started; a library with no songs; no card is needed
    m = machine(4)
    HC.scan(m)
    fn(m, 'cc_build_stop')   # release ours so a foreign set can be held
    HC.hook(m, 'hc_on_background')
    m = machine(4)
    fn(m, 'cc_build_open', 5, 0)
    new = HC.scan(m)
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] == LSCAN] and not HC.shown_calls(m, new), 'a held worker: nothing starts (the next foreground offers again)')
    m = machine(0); new = HC.scan(m)
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] == LSCAN], 'no albums, no songs: nothing')
    m = machine(4); m.card_mounted = False; m.free_mb = 1
    new = HC.scan(m)
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] == LSCAN] and 'pthread_create' not in m.names(), 'no card: the song pass does not start (the table is on the card)')
    HC.hook(m, 'hc_on_background')


def clear_tests(ctx):
    """8. Settings > Developer > Cache > Clear Track Durations, and the Settings Files row."""
    expect, P = ctx.expect, pod_pages
    d = P.CACHE_PAGE
    labels = [r.label for r in d.rows]
    expect(labels.index('Clear Track Durations') == labels.index('Clear Cover Cache') + 4 and d.rows[labels.index('Clear Track Durations')].action == P.ACT_CLEARDUR == 44 and labels[-1] == 'Clear Track Durations', 'Cache has Clear Track Durations as its last row, in the Track Durations section after Measured Tracks and the Artist Photos card (action 44; the ids of the others unchanged)')
    expect('Clear Track Durations' not in [r.label for r in P.DEVELOPER_PAGE.rows], 'Developer has no Clear Track Durations row')
    expect(P.ACT_CLEARCACHE == 42 and P.ACT_CCLIST == 43 and not [s for s in P.SETTING_FILES if 'durations' in s or 'lengths' in s], 'the earlier action ids are as they were; the Settings Files page lists no durations row (the table is on the card)')
    CONFIRM = 'Delete all measured track durations? They will be measured again on Home.'
    toasts = lambda m: [c[1] for c in m.calls if c[0] == 'toast']
    m = Machine(); m.fs[DUR] = table([('/a.flac', 1, 10)])
    m.confirm_yes = False
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect([c[1] for c in m.calls if c[0] == 'confirm'] == [CONFIRM] and DUR in m.fs and 'unlink' not in m.names() and not toasts(m), 'the confirm is asked; No: the table stays, no toast')
    m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect(DUR not in m.fs and ('unlink', DUR) in m.calls and toasts(m) == ['Track durations cleared'], 'Yes: the table is deleted and the toast says so')
    m.set_language('zh_CN')
    expect(m.tr('Track durations cleared') != 'Track durations cleared' and m.tr(CONFIRM) != CONFIRM and m.tr('Clear Track Durations') != 'Clear Track Durations', 'the three texts are translated')
    # the table held by an open album page is emptied too, and a later merge starts over
    m = album_with_files(); known(m)
    AP.open_album(m)
    expect(both(m).endswith('46 minutes'), 'the page has its total')
    fn(m, 'dur_clear')
    expect(lookup(m, '/mnt/mmc/m/0.flac', SIZES[0]) == -1 and DUR not in m.fs, 'cleared while held: the lookups miss and the file is gone')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(fn(m, 'dur_epoch') == 1, 'the clear is counted (Home reads the library again)')


def measured_tests(ctx):
    """8b. Settings > Developer > Cache: the Covers and Track Durations sections; Measured Tracks (dur_stat) is the table header's count and the file's size, read once as the page opens (dur_stat_open) and again after a clear, never by a refresh."""
    expect, P = ctx.expect, pod_pages
    lay = P.CACHE_PAGE.layout
    shape = [x.text if isinstance(x, P.Hdr) else 'gap' if x == P.GAP else x.label for x in lay]
    expect(shape == ['Covers', 'Albums', 'Covers', 'No art', 'Missing', 'Old files', 'Size', 'gap', 'Status', 'gap', 'Clear Cover Cache', 'Artist Photos', 'Photos', 'None', 'Track Durations', 'Measured Tracks', 'Clear Track Durations'], f'the Cache page: a Covers section (the counts, Status and Clear Cover Cache, the gaps kept), an Artist Photos section (Photos, None), then a Track Durations section ({shape})')
    expect(P.CACHE_PAGE.key == 'm1plus_cache' and P.CACHE_PAGE.title == 'Cache' and P.CACHE_PAGE_INDEX == 32, 'the page keeps its key and index; its title is Cache')
    expect([r.label for r in P.DEVELOPER_PAGE.rows if r.action == P.ACT_PAGE and r.arg == P.CACHE_PAGE_INDEX] == ['Cache'], 'the Developer row reads Cache')
    mt = next(r for r in P.CACHE_PAGE.rows if r.label == 'Measured Tracks')
    expect(mt.action == P.ACT_INFO and mt.arg == P.INFO_DUR == P.INFO_SFOLD + 1 and P.INFO_DUR > P.INFO_CC_STATUS, 'Measured Tracks is an info row with its own kind, after the Settings Files kinds')

    def stat(m):
        buf = m.alloc(64)
        fn(m, 'dur_stat', buf, 64)
        return m.read_cstr(buf)
    expect(stat(Machine()) == '0', 'no table on the card: Measured Tracks reads 0')
    m = seeded([(i + 1, 10, 5) for i in range(1234)])
    fn(m, 'dur_stat_open')
    expect(stat(m) == '1234 \xc2\xb7 14 KB', f'a valid table: its header count and size ({stat(m)!r})')   # (read_cstr is latin-1: the middle dot is its two UTF-8 bytes)
    m = seeded([(i + 1, 10, 5) for i in range(1234)], magic=0x1234)
    fn(m, 'dur_stat_open')
    expect(stat(m) == '0', 'a file with a bad magic reads 0')
    m = seeded([(i + 1, 10, 5) for i in range(1234)]); m.card_mounted = False
    fn(m, 'dur_stat_open')
    expect(stat(m) == '0', 'no card mounted: nothing is read, 0')
    m = seeded([(i + 1, 10, 5) for i in range(1234)])
    fn(m, 'dur_stat_open')
    opens = len([c for c in m.calls if c[0] == 'open' and c[1] == DUR])
    n = len(m.calls)
    stat(m); stat(m)
    expect(opens == 1 and not [c for c in m.calls[n:] if c[0] == 'open' and c[1] == DUR], 'the header is read once as the page opens; a refresh (dur_stat) reads no file')
    m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect(stat(m) == '0' and DUR not in m.fs, 'Clear Track Durations, Yes: the file is gone and Measured Tracks reads 0')


SECTIONS = [table_tests, card_tests, cue_tests, probe_tests, text_tests, album_tests, footer_tests, home_tests, clear_tests, measured_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

"""Artist photos (patch/artistphoto.c, cc_build_add_artist in patch/covercache.c; docs/modules/artists.md "Artist photos"): the pictures a user keeps beside the music (artist.jpg, folder.jpg) are
found by walking up from each album's track folder, judged by the purity check on a snapshot of the library's albums, and cached at 168 and 44 px in /mnt/mmc/.m1plus/artists with an empty -44 file
for "no photo". The compiled payload runs under Unicorn on the cover test's card machine."""
import importlib.util, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


CA = sibling('coverart')

AP = '/mnt/mmc/.m1plus/artists'
MUSIC = '/mnt/mmc/Music'


def key(m, name): return m.call(PSYMS['ap_key'], a0=m.cstr(name), count=1 << 40)


def f168(k): return f'{AP}/a{k:08x}-168.jpg'
def f44(k): return f'{AP}/a{k:08x}-44.jpg'
def fsrc(k): return f'{AP}/a{k:08x}.src'
def ftry(k): return f'{AP}/a{k:08x}.try'
def fpick(k): return f'{AP}/a{k:08x}.pick'


def library(files=None, albums=(), extra=None):
    """A card with the albums' first tracks ((artist, track path) pairs) and the picture files (path -> bytes) beside them."""
    m = CA.CM()
    m.dirs.update({'/mnt/mmc/.m1plus', '/tmp'})
    for _, track in albums: m.put(track, b'x')
    for path, data in (files or {}).items(): m.put(path, data)
    for path, data in (extra or {}).items(): m.fs[path] = data
    return m


def run_set(m, albums, force=0, mode=0, start=True):
    """One cover-cache set with the artist jobs the Home scan would queue; the list of cc_build_add_artist answers. The worker runs to its end."""
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=max(2 * len(albums), 1), a1=mode, count=1 << 40) == 1
    ans = [m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(a), a2=force, count=1 << 40) for a, t in albums]
    ans = [a - (1 << 32) if a >= 1 << 31 else a for a in ans]
    if start:
        started = m.call(PSYMS['cc_build_start'], count=1 << 40)
        if started:
            m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
            calls = m.calls
            m.call(PSYMS['cc_build_stop'], count=1 << 40)
            m.calls = calls
    return ans


def size_of(m, path):
    return CA.decoded(m.fs[path]).size if m.fs.get(path) else None


def found(m, k): return bool(m.fs.get(f44(k))) and bool(m.fs.get(f168(k)))
def marked(m, k): return f44(k) in m.fs and m.fs[f44(k)] == b'' and f168(k) not in m.fs


def key_tests(ctx):
    expect = ctx.expect
    m = library()
    k = lambda s: key(m, s)
    expect(k('Beatles') == k('The Beatles') == k('  THE   beatles ') == k('the beatles'), 'a leading "The ", case and surrounding space do not change the key')
    expect(k('Theodore') != k('odore') and k('The') != 0 and k('The') != k(''), '"Theodore" keeps its "The"; a name that is only "The" is a name')
    expect(k('') == 0 and k('   ') == 0, 'a blank name has no key')
    expect(k('Beyonce') != k('Beyoncé') and k('A feat. B') != k('A') and k('Simon & Garfunkel') != k('Simon'), 'no accent folding and no splitting of feat. or &')
    expect(k('Abba') != k('Queen'), 'different names, different keys')


def discovery_tests(ctx):
    expect = ctx.expect
    photo, _ = CA.picture(600, 400)
    wide, _ = CA.picture(900, 450)
    sq, _ = CA.picture(500, 500)

    # 1. Artist/Album: artist.jpg in the artist folder (above the album folders); the other artist has none: an empty marker, nothing else.
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac'), ('Abba', f'{MUSIC}/Abba/Waterloo/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
    ans = run_set(m, albums)
    calls = m.calls
    ka, kq = key(m, 'Abba'), key(m, 'Queen')
    m.calls = calls
    expect(ans == [1, 0, 1], f'one job per artist, the second Abba album only joins the snapshot ({ans})')
    expect(size_of(m, f168(ka)) == (168, 168) and size_of(m, f44(ka)) == (44, 44), f'Abba: 168 and 44 px files ({size_of(m, f168(ka))}, {size_of(m, f44(ka))})')
    expect(marked(m, kq), 'Queen: the empty -44 marker, no -168 file')
    src = m.fs.get(fsrc(ka), b'').decode()
    expect(src.startswith('m1plus artist 1\nsrc: ' + f'{MUSIC}/Abba/artist.jpg\n') and 'size: ' in src and 'mtime: ' in src and src.endswith('end\n'), f'.src names the source, its size and mtime ({src!r})')
    expect(fsrc(kq) not in m.fs and not [p for p in m.fs if p.startswith(AP) and p.endswith(('.tmp', '.try'))], 'no .src for a marker; no temporary or .try file left')
    order = [c[1] for c in m.calls if c[0] == 'rename' and c[2].startswith(AP)]
    expect(order and order[-1].endswith('-44.jpg.tmp'), f'the -44 file is published last ({order})')

    # 2. Genre/Artist/Album: a picture in Rock/ is rejected (two artists under it); the artist folder's own is taken.
    albums = [('Abba', f'{MUSIC}/Rock/Abba/Arrival/01.flac'), ('Queen', f'{MUSIC}/Rock/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Rock/artist.jpg': photo, f'{MUSIC}/Rock/Abba/artist.png': sq}, albums)
    run_set(m, albums)
    expect(found(m, ka) and size_of(m, f168(ka)) == (168, 168) and marked(m, kq), f'Rock/artist.jpg is not a photo of anyone; Rock/Abba/artist.png is Abba\'s ({size_of(m, f168(ka))})')

    # 3. Flat "Artist - Album" folders in one Music folder: the album folder's own artist.jpg counts, Music/artist.jpg does not.
    albums = [('Abba', f'{MUSIC}/Abba - Arrival/01.flac'), ('Queen', f'{MUSIC}/Queen - News/01.flac')]
    m = library({f'{MUSIC}/Abba - Arrival/artist.jpg': photo, f'{MUSIC}/artist.jpg': wide}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168) and marked(m, kq), 'flat folders: the album folder\'s artist.jpg is Abba\'s, the shared Music/artist.jpg nobody\'s')
    m = library({f'{MUSIC}/Abba - Arrival/artist.jpg': photo}, albums + [('Abba', f'{MUSIC}/Abba - Live/01.flac')])
    run_set(m, albums + [('Abba', f'{MUSIC}/Abba - Live/01.flac')])
    expect(found(m, ka), '"Abba - Live" is not under "Abba - Arrival": the second album does not matter to the first one\'s folder')

    # 4. Multi-disc: Artist/Album/CD1: the disc folder is stepped over, so Artist/artist.jpg and Album/artist.jpg are found.
    for disc in ('CD1', 'CD 2', 'Disc 1', 'Disk2', 'disc-03', 'cd_1'):
        albums = [('Abba', f'{MUSIC}/Abba/Arrival/{disc}/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
        m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
        run_set(m, albums)
        expect(found(m, ka), f'{disc}: Abba/artist.jpg is found from the disc folder')
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/CD1/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Abba/Arrival/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(found(m, ka), 'Abba/Arrival/artist.jpg is found from Abba/Arrival/CD1 (the album folder after the step up)')
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/CD1/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Abba/Arrival/CD1/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(marked(m, ka), 'a file inside the disc folder itself is not looked at')
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/Discography/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(marked(m, ka), 'a folder that merely starts with the letters of disc is an album folder: its parent is Arrival, not Abba')

    # 5. Various Artists/: not one artist's folder.
    albums = [('Abba', f'{MUSIC}/Various Artists/Hits/01.flac'), ('Queen', f'{MUSIC}/Various Artists/More/01.flac')]
    m = library({f'{MUSIC}/Various Artists/artist.jpg': photo, f'{MUSIC}/Various Artists/folder.jpg': photo}, albums)
    run_set(m, albums)
    expect(marked(m, ka) and marked(m, kq), 'Various Artists/artist.jpg and folder.jpg are nobody\'s')

    # 6. A flat folder of many artists, and a library of one artist: its top folder is that artist's.
    albums = [('Abba', f'{MUSIC}/a.flac'), ('Queen', f'{MUSIC}/b.flac')]
    m = library({f'{MUSIC}/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(marked(m, ka) and marked(m, kq), 'a flat folder of two artists: no artist.jpg for either')
    albums = [('Abba', f'{MUSIC}/Arrival/01.flac')]
    m = library({f'{MUSIC}/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(found(m, ka), 'a library of one artist: Music/ above the album folder is that artist\'s')

    # 7. folder.jpg in the parent: only when the folder is named for the artist (key compare: "The", case); never in the album folder.
    albums = [('The Beatles', f'{MUSIC}/Beatles/Help/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    kb = key(m, 'The Beatles')
    m = library({f'{MUSIC}/Beatles/folder.jpg': photo}, albums)
    run_set(m, albums)
    expect(found(m, kb) and marked(m, kq), 'Beatles/folder.jpg is the photo of "The Beatles" (the folder name matches the key)')
    m = library({f'{MUSIC}/Misc/folder.jpg': photo}, [('Abba', f'{MUSIC}/Misc/Arrival/01.flac')])
    run_set(m, [('Abba', f'{MUSIC}/Misc/Arrival/01.flac')])
    expect(marked(m, ka), 'a folder.jpg in a folder not named for the artist is not a photo')
    m = library({f'{MUSIC}/Abba/Arrival/folder.jpg': photo}, [('Abba', f'{MUSIC}/Abba/Arrival/01.flac')])
    run_set(m, [('Abba', f'{MUSIC}/Abba/Arrival/01.flac')])
    expect(marked(m, ka), 'the album folder\'s folder.jpg is the album cover, never the artist photo')
    m = library({f'{MUSIC}/Rock/folder.jpg': photo}, [('Rock', f'{MUSIC}/Rock/Hits/01.flac'), ('Abba', f'{MUSIC}/Rock/Abba/x/01.flac')])
    run_set(m, [('Rock', f'{MUSIC}/Rock/Hits/01.flac'), ('Abba', f'{MUSIC}/Rock/Abba/x/01.flac')])
    expect(marked(m, key(m, 'Rock')), 'an artist named like a genre folder that holds another artist too: impure, rejected')

    # 8. Priority: parent artist.* > album-folder artist.* > parent folder.*; and jpg, jpeg, png, any case.
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac')]
    files = {f'{MUSIC}/Abba/artist.jpg': photo, f'{MUSIC}/Abba/Arrival/artist.jpg': wide, f'{MUSIC}/Abba/folder.jpg': sq}
    m = library(files, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168) and m.fs[fsrc(ka)].decode().split('\n')[1] == f'src: {MUSIC}/Abba/artist.jpg', 'the parent folder\'s artist.jpg wins')
    del files[f'{MUSIC}/Abba/artist.jpg']
    m = library(files, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168), 'then the album folder\'s artist.jpg')
    del files[f'{MUSIC}/Abba/Arrival/artist.jpg']
    m = library(files, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168), 'then the parent folder\'s folder.jpg (named for the artist)')
    m = library({f'{MUSIC}/Abba/ARTIST.PNG': sq, f'{MUSIC}/Abba/Artist.Jpeg': photo, f'{MUSIC}/Abba/artist.JPG': wide}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168), 'any case; .jpg before .jpeg before .png')
    m = library({f'{MUSIC}/Abba/artist.jpg': b'\xff\xd8\xff\xe0garbage' * 20, f'{MUSIC}/Abba/Arrival/artist.jpg': wide}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168), 'a file that is not a picture is passed over for the next candidate')
    m = library({f'{MUSIC}/Abba/artist.txt': b'x', f'{MUSIC}/Abba/artist.jpg.bak': photo}, albums)
    run_set(m, albums)
    expect(marked(m, ka), 'only artist.jpg, .jpeg and .png count')

    # 9. Every candidate of a folder is tried before the next folder or tier: a corrupt artist.jpg does not hide a valid artist.png (or .jpeg) beside it.
    bad = b'\xff\xd8\xff\xe0garbage' * 20
    m = library({f'{MUSIC}/Abba/artist.jpg': bad, f'{MUSIC}/Abba/artist.png': sq}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168) and m.fs[fsrc(ka)].decode().split('\n')[1] == f'src: {MUSIC}/Abba/artist.png', 'a corrupt artist.jpg: the valid artist.png beside it is used')
    m = library({f'{MUSIC}/Abba/artist.jpg': bad, f'{MUSIC}/Abba/Artist.JPEG': bad, f'{MUSIC}/Abba/ARTIST.PNG': photo, f'{MUSIC}/Abba/Arrival/artist.jpg': wide}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168), 'two corrupt files (.jpg, .jpeg, any case): the .png, still before the next tier')
    m = library({f'{MUSIC}/Abba/artist.jpg': bad, f'{MUSIC}/Abba/artist.png': bad, f'{MUSIC}/Abba/Arrival/artist.jpg': wide}, albums)
    run_set(m, albums)
    expect(size_of(m, f168(ka)) == (168, 168) and m.fs[fsrc(ka)].decode().split('\n')[1] == f'src: {MUSIC}/Abba/Arrival/artist.jpg', 'every candidate of the folder corrupt: the next tier')
    m = library({f'{MUSIC}/Abba/artist.jpg': bad, f'{MUSIC}/Abba/artist.png': bad}, albums)
    run_set(m, albums)
    expect(marked(m, ka), 'all corrupt and nothing else: the empty marker')


def request_tests(ctx):
    expect = ctx.expect
    photo, _ = CA.picture(600, 400)
    wide, _ = CA.picture(900, 450)
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
    ka, kq = key(m, 'Abba'), key(m, 'Queen')

    # Missing only: an artist with any result is not queued again; a new one is; nothing is looked at again.
    run_set(m, albums)
    expect(found(m, ka) and marked(m, kq), 'first pass')
    m.put(f'{MUSIC}/Queen/artist.jpg', wide)
    del m.fs[f'{MUSIC}/Abba/artist.jpg']
    ans = run_set(m, albums, start=False)
    expect(ans == [0, 0], f'missing-only set: artists with a result (a photo or the marker) are not queued ({ans})')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    expect(found(m, ka) and marked(m, kq), 'and their results stand even though the files changed')

    # A rebuild request (force) checks every artist again, found ones too: Abba's photo is gone, Queen's has appeared.
    ans = run_set(m, albums, force=1)
    expect(ans == [1, 1], f'force queues every artist ({ans})')
    expect(marked(m, ka) and found(m, kq) and fsrc(ka) not in m.fs, 'a removed photo becomes the empty marker (168 and .src gone), a new one is found')
    expect(size_of(m, f168(kq)) == (168, 168), 'Queen\'s new photo')

    # A manual pick (.pick, reserved) is never replaced by an automatic build, not even by a rebuild.
    m.fs[fpick(kq)] = b''
    m.fs[f44(kq)] = b'picked'
    m.fs[f168(kq)] = b'picked168'
    run_set(m, albums, force=1)
    expect(m.fs[f44(kq)] == b'picked' and m.fs[f168(kq)] == b'picked168', '.pick keeps the files')

    # An artist whose last attempt died or hung (.try) gets the empty marker, not another attempt.
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums, extra={ftry(ka): b''})
    run_set(m, albums)
    expect(marked(m, ka) and ftry(ka) not in m.fs, 'a leftover .try: the marker, and the strike is cleared')
    run_set(m, albums, force=1)
    expect(found(m, ka), 'a rebuild then looks again')

    # Storage gone: no marker (the next pass retries). An album with no artist name is skipped.
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
    del m.fs[albums[0][1]]
    ans = run_set(m, albums)
    expect(not m.fs.get(f44(ka)) and f44(ka) not in m.fs, 'a track that is gone: no marker')
    ans = run_set(m, [('', f'{MUSIC}/x/01.flac')], start=False)
    expect(ans == [0], 'a blank artist is not an artist')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)

    # The set's capacity: an artist that does not fit answers -1.
    m = library({}, albums)
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=1 << 40) == 1
    a = [m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(n), a2=0, count=1 << 40) for n, t in albums]
    expect([x - (1 << 32) if x >= 1 << 31 else x for x in a] == [1, -1], f'a full set answers -1 ({a})')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)


def purity_snapshot_tests(ctx):
    expect = ctx.expect
    photo, _ = CA.picture(600, 400)
    # Albums that were not queued as jobs still count for purity: Queen has a result already, but its album under Rock/ keeps Rock/artist.jpg from Abba.
    albums = [('Abba', f'{MUSIC}/Rock/Abba/Arrival/01.flac'), ('Queen', f'{MUSIC}/Rock/Queen/News/01.flac')]
    m = library({f'{MUSIC}/Rock/artist.jpg': photo}, albums, extra={})
    kq = key(m, 'Queen')
    m.fs[f44(kq)] = b''
    ans = run_set(m, albums)
    expect(ans == [1, 0] and marked(m, key(m, 'Abba')), f'the Queen album that is not a job still makes Rock/ impure ({ans})')
    # An album with no artist (blank, or the library's "Unknown Artist") joins the snapshot and conflicts with every artist, so a shared folder is nobody's; it gets no job.
    for blank in ('', '   ', 'Unknown Artist', 'unknown artist'):
        albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac'), ('Abba', f'{MUSIC}/Abba/Waterloo/01.flac'), (blank, f'{MUSIC}/Abba/Untagged/01.flac')]
        m = library({f'{MUSIC}/Abba/artist.jpg': photo, f'{MUSIC}/Abba/folder.jpg': photo}, albums)
        ka = key(m, 'Abba')
        ans = run_set(m, albums)
        expect(ans == [1, 0, 0] and marked(m, ka), f'{blank!r}: Abba albums beside an untagged one do not own Abba/artist.jpg or folder.jpg ({ans})')
        m = library({f'{MUSIC}/Abba/Arrival/artist.jpg': photo}, albums)
        run_set(m, albums)
        expect(found(m, ka), f'{blank!r}: the album folder\'s own artist.jpg still works')
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac'), ('', f'{MUSIC}/Other/01.flac')]
    m = library({f'{MUSIC}/Abba/artist.jpg': photo}, albums)
    run_set(m, albums)
    expect(found(m, key(m, 'Abba')), 'an untagged album in another folder does not matter')
    # More albums than the snapshot holds: the artist jobs write nothing.
    big = [(f'Artist {i}', f'{MUSIC}/Artist {i}/Album/01.flac') for i in range(8001)]
    m = library({f'{MUSIC}/Artist 0/artist.jpg': photo}, big[:3])
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=40, a1=0, count=1 << 40) == 1
    for n, t in big: m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(n), a2=0, count=1 << 40)
    expect(m.call(PSYMS['cc_build_artist_ok'], count=1 << 40) == 0, 'over AP_LIB_MAX albums the snapshot is not usable')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)


def home_tests(ctx):
    """Home's cover pass queues the artist photos after the covers (patch/homecover.c): the pill text, the set, the requests and the stamp."""
    expect = ctx.expect
    HC = sibling('homecover')
    AREQ = '/mnt/data/m1plus/artists-rebuild'

    def machine(n=3, artists=False, **kw):
        m = HC.home_machine(n, **kw)
        if not artists:
            for i in range(n): m.present.discard(HC.artist_file(f'Artist {i}')); m.files.pop(HC.artist_file(f'Artist {i}'), None)
        return m
    jobs = lambda m: [(k, s) for _, k, s, _ in build_jobs_art(m)]

    # 0. Upgrade: the covers and tracks lines match, there is no artists line (an older stamp): the pass queues the artist jobs alone, writes the artists line, and a second foreground does nothing.
    m = machine(stamp=HC.stamp_text(3, artists=False))
    expect(HC.pill_up(m), 'a stamp with no artists line: the pill is up at once')
    new = HC.scan(m); s = build_state(m)
    expect(s['mode'] == 0 and s['total'] == 3 and sorted(k for k, _ in jobs(m)) == sorted(key(m, f'Artist {i}') for i in range(3)) and HC.texts(m, new) == ['Preparing artist photos 0/3'], f'only the three artist jobs, no cover ({s["total"]}, {HC.texts(m, new)})')
    covers = {p: v for p, v in m.files.items() if '/artists/' not in p}
    m.call(PSYMS['cc_worker'], count=50000000)
    HC.fired(m, 'hc_on_poll', 40000000)
    expect(m.fs[HC.STAMP].decode() == HC.stamp_text(3) and not HC.pill_up(m) and covers == {p: v for p, v in m.files.items() if '/artists/' not in p}, f'done: the artists line is written beside the others, the album covers untouched ({m.fs.get(HC.STAMP)})')
    HC.hook(m, 'hc_on_background'); new = HC.hook(m, 'hc_on_foreground')
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] != PSYMS['hc_on_dots']] and not HC.pill_up(m), 'the next foreground does nothing')
    # a stalled artist pass is not stamped (the next foreground runs it again)
    m = machine(stamp=HC.stamp_text(3, artists=False)); HC.scan(m)
    m.setword(PSYMS['cb'] + 4 * 13, key(m, 'Artist 0')); m.setword(PSYMS['cb'] + 4 * 15, 1)
    m.clock += 10000
    HC.fired(m, 'hc_on_poll', 40000000)
    expect(m.call(PSYMS['cc_build_stalled']) == 1 and 'artists' not in m.fs[HC.STAMP].decode() and 'covers 3 ' in m.fs[HC.STAMP].decode(), 'a stalled artist pass leaves the artists line unwritten (the covers line stays)')
    # a library change runs both parts again
    m = machine(missing={1}, stamp=HC.stamp_text(3, h=HC.hash_of(3) ^ 0x10))
    new = HC.scan(m)
    expect(build_state(m)['total'] == 4 and HC.texts(m, new) == ['Preparing covers 0/4'], f'a changed library: the missing cover and the three artists ({HC.texts(m, new)})')
    HC.finish_worker(m, [1])
    HC.fired(m, 'hc_on_poll', 40000000)
    stamp = m.fs[HC.STAMP].decode()
    expect('covers 3 ' in stamp and 'artists 3 ' in stamp and f'artists 3 {HC.hash_of(3):08x}' in stamp, f'both lines follow the new library ({stamp!r})')

    # 1. Covers complete, no artist has a result: the scan queues one job per artist, the pill counts them, the stamp comes with the end of the set.
    m = machine(); new = HC.scan(m); s = build_state(m)
    expect(s['running'] == 1 and s['mode'] == 0 and s['total'] == 3 and HC.texts(m, new) == ['Preparing artist photos 0/3'] and HC.pill_up(m), f'three artists, three jobs ({s["total"]}, {HC.texts(m, new)})')
    expect(sorted(k for k, _ in jobs(m)) == sorted(key(m, f'Artist {i}') for i in range(3)) and all(f == 0 for _, f in jobs(m)), 'one job each, not forced')
    expect(('fopen', PUR + '.tmp', 'w') in new, 'the scan writes the purity map when its snapshot is whole (before the worker starts; this machine\'s stdio does not keep the bytes)')
    m.call(PSYMS['cc_worker'], count=50000000)
    new = HC.fired(m, 'hc_on_poll', 40000000)
    expect(not HC.pill_up(m) and m.fs.get(HC.STAMP, b'').decode().startswith('covers 3 '), f'done: the line is hidden and the covers line written ({m.fs.get(HC.STAMP)})')
    expect(all(m.files.get(HC.artist_file(f'Artist {i}')) == 0 and HC.artist_file(f'Artist {i}') in m.present for i in range(3)), 'every artist has its (empty) marker')

    # 2. Missing covers first: the count reads covers, then artist photos from the first artist job on.
    m = machine(missing={1}); new = HC.scan(m)
    expect(build_state(m)['total'] == 4 and HC.texts(m, new) == ['Preparing covers 0/4'], f'one cover and three artists in one set ({HC.texts(m, new)})')
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    new = HC.fired(m, 'hc_on_poll')
    expect(HC.texts(m, new) == ['Preparing artist photos 0/3'], f'after the cover the line counts the artists ({HC.texts(m, new)})')
    m.setword(PSYMS['cb'] + 4 * 5, 2)
    new = HC.fired(m, 'hc_on_poll')
    expect(HC.texts(m, new) == ['Preparing artist photos 1/3'], f'({HC.texts(m, new)})')

    # 3. A pending artists-rebuild request: the waiting text, every artist forced, the request ends with the set; Rebuild Covers first when both are pending.
    m = machine(artists=True, stamp=HC.stamp_text(3)); m.fs[AREQ] = b'1\n'
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    expect(HC.pill_up(m) and HC.texts(m, waiting=True)[-1:] == ['Rebuilding artist photos.'], f'the waiting pill says Rebuilding artist photos ({HC.texts(m, waiting=True)})')
    m = machine(artists=True, stamp=HC.stamp_text(3), rebuild=True); m.fs[AREQ] = b'1\n'
    m.call(PSYMS['homecover_start'], a0=m.window, count=2000000)
    expect(HC.texts(m, waiting=True)[-1:] == ['Rebuilding covers.'], 'both pending: covers first')
    m = machine(artists=True, stamp=HC.stamp_text(3)); m.fs[AREQ] = b'1\n'
    new = HC.scan(m); s = build_state(m)
    expect(s['total'] == 3 and all(f == 1 for _, f in jobs(m)) and HC.texts(m, new) == ['Rebuilding artist photos 0/3'] and AREQ in m.fs, f'every artist is a forced job; the request stays while it runs ({HC.texts(m, new)})')
    m.call(PSYMS['cc_worker'], count=50000000)
    new = HC.fired(m, 'hc_on_poll', 40000000)
    expect(AREQ not in m.fs and not HC.pill_up(m), 'done: the request is removed')
    m = machine(artists=True, stamp=HC.stamp_text(3)); m.fs[AREQ] = b'1\n'
    m.showlist = [m.record(album=f'Album {i}', artist='', path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i in range(3)]
    HC.scan(m)
    expect(AREQ not in m.fs and all(sec == 0 for _, _, _, sec in build_jobs_art(m)), 'no artist to check: the request ends at once')
    m = machine(artists=True, stamp=HC.stamp_text(3)); m.fs[AREQ] = b'1\n'
    HC.scan(m)
    new = HC.hook(m, 'hc_on_background')
    expect(AREQ in m.fs, 'left before the end: the request stays for the next foreground')


def build_jobs_art(m):
    """The queued jobs as (track, key, size, sec): the job array's four words each."""
    s = build_state(m)
    return [(m.read_cstr(m.word(s['jobs'] + 16 * i)), m.word(s['jobs'] + 16 * i + 4), m.word(s['jobs'] + 16 * i + 8), m.word(s['jobs'] + 16 * i + 12)) for i in range(s['total'])] if s['jobs'] else []


def lead_tests(ctx):
    """The lead artist of "A feat. B" (phase 2's fallback): the name before the earliest of the separators, any case; the key of the full name is not touched."""
    expect = ctx.expect
    m = library()
    buf = m.alloc(300)
    def lead(name, n=260):
        ok = m.call(PSYMS['ap_lead'], a0=m.cstr(name), a1=buf, a2=n, count=1 << 40)
        return m.read_cstr(buf) if ok else None
    for name, want in (('Adele feat. Someone', 'Adele'), ('Adele FEAT. Someone', 'Adele'), ('Adele ft. Someone', 'Adele'), ('Adele Ft. Someone', 'Adele'), ('Adele featuring Someone', 'Adele'),
                       ('Adele FeaturingSomeone', None), ('Simon & Garfunkel', 'Simon'), ('Mark X Mark', 'Mark'), ('Mark x Mark', 'Mark'), ('Tyler, The Creator', 'Tyler'),
                       ('Tom; Jerry', 'Tom'), ('Tom;Jerry', None), ('Beyoncé feat. Jay-Z & Kanye', 'Beyoncé'.encode().decode('latin-1')), ('A & B feat. C', 'A'), ('A feat. B & C', 'A'), ('Abba', None),
                       ('Maxx', None), ('Fox', None), ('Adele ft.', None), ('feat. X', None), ('Prince and the Revolution', None), ('Earth, Wind & Fire', 'Earth')):
        expect(lead(name) == want, f'lead of {name!r}: {want!r} (got {lead(name)!r})')
    expect(lead('x' * 300 + ' & B') is None and lead('Longer than the buffer & B', 6) is None, 'a lead that does not fit gives none')
    expect(key(m, 'Adele feat. Someone') != key(m, 'Adele') and key(m, 'The Weeknd & Drake') != key(m, 'Weeknd'), 'ap_key itself never splits')


def lookup_tests(ctx):
    """ap_lookup (UI thread): the name's own file, else the lead artist's; the empty marker is "none", a missing file "unknown"; the -44 and the -168 sizes."""
    expect = ctx.expect
    m = library()
    url = m.alloc(100)
    PHOTO, LEAD, NONE, UNKNOWN = 1, 3, 2, 0
    def look(name, size=44):
        r = m.call(PSYMS['ap_lookup'], a0=m.cstr(name), a1=size, a2=url, count=1 << 40)
        return r, (m.read_cstr(url) if r in (PHOTO, LEAD) else None)
    def put(name, size=44, data=b'x'):
        k = key(m, name); m.put(f44(k) if size == 44 else f168(k), data); return k
    a = put('Adele'); put('Adele', 168)
    expect(look('Adele') == (PHOTO, 'file://' + f44(a)) and look('adele ') == (PHOTO, 'file://' + f44(a)) and look('The Adele') == (PHOTO, 'file://' + f44(a)), 'the name\'s own -44 file (case, space and "The" folded as ap_key does)')
    expect(look('Adele', 168) == (PHOTO, 'file://' + f168(a)), 'the -168 file for the header')
    expect(look('Adele feat. Someone') == (LEAD, 'file://' + f44(a)) and look('Adele & Co', 168) == (LEAD, 'file://' + f168(a)) and look('Adele, Co') [0] == LEAD, 'no file of its own: the lead artist\'s (-44 and -168)')
    s = put('Adele feat. Someone', 44)
    expect(look('Adele feat. Someone') == (PHOTO, 'file://' + f44(s)), 'the full name\'s own photo wins over the lead\'s')
    m.put(f44(s), b'')
    expect(look('Adele feat. Someone') == (LEAD, 'file://' + f44(a)), 'the full name\'s empty marker: the lead\'s photo')
    put('Beck', 44, b'')
    expect(look('Beck') == (NONE, None) and look('Beck feat. Zed') == (UNKNOWN, None), 'a marker is "none"; a name whose own file is missing and whose lead has a marker only is unknown')
    put('Cher', 44, b''); put('Cher & Sonny', 44, b'')
    expect(look('Cher & Sonny') == (NONE, None), 'both markers: none')
    put('Dido', 44, b'')
    expect(look('Dido feat. Zed') == (UNKNOWN, None) and look('Nobody') == (UNKNOWN, None), 'files missing: unknown (looked for again later)')
    expect(look('') == (NONE, None) and look('   ') == (NONE, None), 'a blank name has no photo')


def circle_tests(ctx):
    """ap_circle: the alpha is the circle's coverage (antialiased edge), the colour untouched; ap_placeholder: #333333 circle with the glyph."""
    expect = ctx.expect
    m = library()
    for d in (40, 160):
        buf = m.alloc(d * d * 4)
        m.u.mem_write(buf, b''.join(struct.pack('<I', 0xff102030) for _ in range(d * d)))
        m.call(PSYMS['ap_circle'], a0=buf, a1=d, count=1 << 40)
        px = struct.unpack(f'<{d * d}I', bytes(m.u.mem_read(buf, d * d * 4)))
        a = [p >> 24 for p in px]
        total = sum(a) / 255
        expect(abs(total - 3.14159265 * (d / 2) ** 2) < 0.004 * d * d, f'{d} px: the covered area is the circle\'s ({total:.1f} vs {3.14159265 * (d / 2) ** 2:.1f})')
        expect(a[0] == 0 and a[(d // 2) * d + d // 2] == 255 and all(p & 0xffffff == 0x102030 for p in px), f'{d} px: corners clear, the middle opaque, the colour untouched')
        sym = all(a[y * d + x] == a[x * d + y] == a[y * d + d - 1 - x] == a[(d - 1 - y) * d + x] for y in range(0, d, 3) for x in range(0, d, 3))
        expect(sym, f'{d} px: the edge is symmetric')
        edge = [v for v in a if 0 < v < 255]
        expect(len(edge) > 2 * d and len(edge) < 6 * d, f'{d} px: a one-pixel antialiased edge ({len(edge)} partial pixels)')


PUR = AP + '/purity'


def fh(path):
    """The purity map's key for a folder (patch/artistphoto.c: FNV of the path, never 0)."""
    h = fnv(O['FNV_SEED'], path)
    return h or 1


def purity_map(m):
    """The saved map as {folder hash: key} after a header check, or None."""
    b = m.fs.get(PUR)
    if not b or len(b) < 12: return None
    magic, n, check = struct.unpack('<3I', b[:12])
    if magic != 0x31555041 or len(b) != 12 + 8 * n: return None
    ent = struct.unpack(f'<{2 * n}I', b[12:])
    c = n
    for i in range(n):
        h, k = ent[2 * i], ent[2 * i + 1]
        c = ((c << 1 | c >> 31) & 0xffffffff) ^ ((h * 3 + k) & 0xffffffff)
    return dict(zip(ent[0::2], ent[1::2])) if c == check else None


def recheck(m, name, tracks, run=True):
    """ap_recheck from the UI thread; the worker (if it started) runs to its end and the set is released. Returns ap_recheck's answer."""
    m.thread = None
    r = m.call(PSYMS['ap_recheck'], a0=m.cstr(name), a1=m.cstr(''.join(t + '\n' for t in tracks)), count=1 << 40)
    if r and run and m.thread:
        m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
        calls = m.calls
        m.call(PSYMS['cc_build_stop'], count=1 << 40)
        m.calls = calls
    return r


def epoch(m): return m.call(PSYMS['ap_epoch'], count=1 << 40)


def snapshot(m): return {p: bytes(v) for p, v in m.fs.items() if p.startswith(AP)}


def purity_tests(ctx):
    """The Home pass keeps the snapshot's purity map on the card (ap_lib_save) for the re-check of one artist: every folder that holds an album or has one below, with the one artist under it (0 = more than one)."""
    expect = ctx.expect
    photo, _ = CA.picture(600, 400)
    albums = [('Abba', f'{MUSIC}/Rock/Abba/Arrival/01.flac'), ('Queen', f'{MUSIC}/Rock/Queen/News/01.flac'), ('Abba', f'{MUSIC}/Abba - Live/01.flac'), ('', f'{MUSIC}/Misc/x/01.flac')]
    m = library({}, albums)
    ka, kq = key(m, 'Abba'), key(m, 'Queen')
    run_set(m, albums, start=False)
    expect(m.call(PSYMS['ap_lib_save'], count=1 << 40) == 1, 'the whole snapshot is saved')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    pm = purity_map(m)
    expect(pm is not None and PUR + '.tmp' not in m.fs, 'a header (magic, count, check) and the entries; written through a temporary file')
    want = {fh(f'{MUSIC}/Rock/Abba/Arrival'): ka, fh(f'{MUSIC}/Rock/Abba'): ka, fh(f'{MUSIC}/Rock/Queen'): kq, fh(f'{MUSIC}/Rock'): 0, fh(MUSIC): 0, fh(f'{MUSIC}/Abba - Live'): ka,
            fh(f'{MUSIC}/Misc'): 0, fh(f'{MUSIC}/Misc/x'): 0}
    expect(pm and all(pm.get(h) == k for h, k in want.items()) and fh(f'{MUSIC}/Abba') not in pm, f'each folder with its one artist, 0 where two artists (or an untagged album) share it ({sorted(want.items()) == sorted((h, pm.get(h)) for h in want)})')
    # an unusable snapshot removes the file: it described another library
    m.put(PUR, b'old')
    big = [(f'Artist {i}', f'{MUSIC}/Artist {i}/Album/01.flac') for i in range(8001)]
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=40, a1=0, count=1 << 40) == 1
    for n, t in big: m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(n), a2=0, count=1 << 40)
    expect(m.call(PSYMS['ap_lib_save'], count=1 << 40) == 0 and PUR not in m.fs, 'a snapshot that overflowed: no file (the old one goes)')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m.put(PUR, b'old')
    m.call(PSYMS['ap_lib_drop'], count=1 << 40)
    expect(PUR not in m.fs, 'ap_lib_drop removes it (a pass with no snapshot)')


def recheck_tests(ctx):
    """The re-check of one artist when its page opens (patch/artistphoto.c ap_recheck, on the cover worker): nothing but one stat when the source is as it was; a changed, removed or newly added picture is found; no
    marker and no removal from the album-folder tier alone; a pick, a busy worker and a strike are respected."""
    expect = ctx.expect
    photo, _ = CA.picture(600, 400)
    wide, _ = CA.picture(900, 450)
    sq, _ = CA.picture(500, 500)
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac'), ('Abba', f'{MUSIC}/Abba/Waterloo/01.flac'), ('Queen', f'{MUSIC}/Queen/News/01.flac')]
    abba = [a[1] for a in albums[:2]]
    src = f'{MUSIC}/Abba/artist.jpg'

    def base(files=None, save=True, extra=None):
        m = library({src: photo, **(files or {})}, albums, extra=extra)
        m.thread = None
        assert m.call(PSYMS['cc_build_open'], a0=6, a1=0, count=1 << 40) == 1
        for a, t in albums: m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(a), a2=0, count=1 << 40)
        if save: assert m.call(PSYMS['ap_lib_save'], count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_start'], count=1 << 40)
        m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
        m.call(PSYMS['cc_build_stop'], count=1 << 40)
        m.calls = []
        return m
    m = base()
    ka, kq = key(m, 'Abba'), key(m, 'Queen')
    expect(found(m, ka) and marked(m, kq) and purity_map(m), 'setup: a pass made Abba\'s photo, Queen\'s marker and the map')

    # 1. Unchanged source: the worker runs, one stat, nothing written
    before, e0 = snapshot(m), epoch(m)
    expect(recheck(m, 'Abba', abba) == 1, 'ap_recheck starts the worker')
    calls = list(m.calls)
    changes = [c for c in calls if c[0] in ('rename', 'unlink', 'fwrite') or (c[0] == 'fopen' and c[2] not in ('rb', 'r'))]
    expect(snapshot(m) == before and epoch(m) == e0 and not changes and [c for c in calls if c[0] == '__xstat' and src in c],
           f'unchanged: no file touched, the epoch stays, the source stat\'ed ({changes[:3]})')
    expect(not [c for c in calls if c[0] in ('opendir', 'readdir')], 'and no folder is listed')

    # 2. A changed modification time, and a changed size: the photo is made again from the new file
    m.mtime[src] = 777
    expect(recheck(m, 'Abba', abba) == 1 and epoch(m) == e0 + 1 and size_of(m, f168(ka)) == (168, 168), 'a new modification time: the photo is made again, the epoch counts it')
    expect('mtime: 777\n' in m.fs[fsrc(ka)].decode(), '.src has the new time')
    e1 = epoch(m)
    expect(recheck(m, 'Abba', abba) == 1 and epoch(m) == e1, 'and the next re-check finds it as it was')
    m.put(src, wide)
    expect(recheck(m, 'Abba', abba) == 1 and epoch(m) == e1 + 1 and size_of(m, f168(ka)) == (168, 168), 'a new file of another size: the new picture')

    # 3. The source is gone: nothing found anywhere = the empty marker (the whole library was weighed)
    e2 = epoch(m)
    del m.fs[src]
    expect(recheck(m, 'Abba', abba) == 1 and marked(m, ka) and fsrc(ka) not in m.fs and epoch(m) == e2 + 1, 'a removed source: the empty marker, 168 and .src removed')
    # ... or a picture elsewhere takes its place (the album folder)
    m = base()
    del m.fs[src]
    m.put(f'{MUSIC}/Abba/Arrival/artist.jpg', sq)
    e = epoch(m)
    expect(recheck(m, 'Abba', abba) == 1 and size_of(m, f168(ka)) == (168, 168) and m.fs[fsrc(ka)].decode().split('\n')[1] == f'src: {MUSIC}/Abba/Arrival/artist.jpg' and epoch(m) == e + 1,
           'the source moved to the album folder: found there')
    # 4. The empty marker and a new artist.jpg: found; with nothing new: nothing changes
    m = base()
    e = epoch(m)
    snap = snapshot(m)
    expect(recheck(m, 'Queen', [albums[2][1]]) == 1 and snapshot(m) == snap and epoch(m) == e, 'a marker and nothing new: nothing changes')
    m.put(f'{MUSIC}/Queen/artist.jpg', wide)
    expect(recheck(m, 'Queen', [albums[2][1]]) == 1 and found(m, kq) and size_of(m, f168(kq)) == (168, 168) and epoch(m) == e + 1, 'a marker and a new artist.jpg in the artist\'s folder: found')
    # 5. .pick
    m = base()
    m.fs[fpick(kq)] = b''
    snap = snapshot(m)
    m.put(f'{MUSIC}/Queen/artist.jpg', wide)
    expect(recheck(m, 'Queen', [albums[2][1]]) == 1 and snapshot(m) == snap, '.pick: the files are not touched, even with a new picture')
    m.fs[f44(ka)] = b'picked'; m.fs[fpick(ka)] = b''; m.mtime[src] = 5
    expect(recheck(m, 'Abba', abba) == 1 and m.fs[f44(ka)] == b'picked', '.pick on a photo whose source changed: kept as it is')
    # 6. A strike (.try): the last attempt hung: the marker, the strike cleared
    m = base(extra={})
    m.fs[ftry(ka)] = b''
    e = epoch(m)
    recheck(m, 'Abba', abba)
    expect(marked(m, ka) and ftry(ka) not in m.fs and epoch(m) == e + 1, 'a leftover .try: the empty marker, the strike cleared')
    # 7. Storage gone (the first track is not there): no conclusion
    m = base()
    snap = snapshot(m)
    del m.fs[abba[0]]
    del m.fs[src]
    expect(recheck(m, 'Abba', abba) == 1 and snapshot(m) == snap, 'the first track is gone: nothing is concluded')

    # 8. The map is missing, cut or does not check: only the album folders are looked in, and nothing is concluded from that
    for how in ('missing', 'bad', 'cut'):
        m = base(save=False)
        if how == 'bad': m.put(PUR, struct.pack('<3I', 0x31555041, 1, 5) + struct.pack('<2I', 1, 2))
        if how == 'cut': m.put(PUR, struct.pack('<3I', 0x31555041, 3, 5) + struct.pack('<2I', 1, 2))
        e = epoch(m)
        snap = snapshot(m)
        del m.fs[src]
        expect(recheck(m, 'Abba', abba) == 1 and f44(ka) in m.fs and m.fs[f44(ka)] == snap[f44(ka)] and f168(ka) in m.fs and epoch(m) == e, f'{how} map: a removed source is not concluded from (no marker, the photo stays)')
        m.put(f'{MUSIC}/Abba/Arrival/artist.png', sq)
        expect(recheck(m, 'Abba', abba) == 1 and size_of(m, f168(ka)) == (168, 168) and epoch(m) == e + 1, f'{how} map: artist.* in the album folder is still found')
        m = base(save=False)
        m.fs.pop(f44(kq), None)
        m.put(f'{MUSIC}/Queen/artist.jpg', wide)
        e = epoch(m)
        recheck(m, 'Queen', [albums[2][1]])
        expect(f44(kq) not in m.fs and epoch(m) == e, f'{how} map: a picture in the folder above the album (it needs the purity check) is not used, and no marker is written for it')
    # with the map the parent picture is used
    m = base()
    m.fs.pop(f44(kq), None)
    m.put(f'{MUSIC}/Queen/artist.jpg', wide)
    recheck(m, 'Queen', [albums[2][1]])
    expect(found(m, kq), 'with the map the folder above the album is judged pure and used')
    m = base()
    m.fs.pop(f44(kq), None)
    recheck(m, 'Queen', [albums[2][1]])
    expect(marked(m, kq), 'with the map and no picture anywhere, a missing result becomes the marker')
    # a folder two artists share is nobody's, the map knows
    albums2 = albums + [('Queen', f'{MUSIC}/Abba/Queen Tribute/01.flac')]
    m = library({src: photo}, albums2)
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=8, a1=0, count=1 << 40) == 1
    for a, t in albums2: m.call(PSYMS['cc_build_add_artist'], a0=m.cstr(t), a1=m.cstr(a), a2=0, count=1 << 40)
    m.call(PSYMS['ap_lib_save'], count=1 << 40); m.call(PSYMS['cc_build_stop'], count=1 << 40)
    recheck(m, 'Abba', abba)
    expect(marked(m, ka), 'Music/Abba holds a Queen album too: its artist.jpg is not Abba\'s')

    # 9. The worker is busy: nothing starts, nothing waits
    m = base()
    assert m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=1 << 40) == 1
    m.thread = None
    r = m.call(PSYMS['ap_recheck'], a0=m.cstr('Abba'), a1=m.cstr(abba[0] + '\n'), count=1 << 40)
    expect(r == 0 and m.thread is None and build_state_total(m) == 0, 'another set holds the worker: ap_recheck answers 0 and starts nothing')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    r = [m.call(PSYMS['ap_recheck'], a0=m.cstr(n), a1=m.cstr(t), count=1 << 40) for n, t in (('', abba[0] + '\n'), ('   ', abba[0] + '\n'), ('Unknown Artist', abba[0] + '\n'), ('Abba', ''))]
    expect(r == [0, 0, 0, 0], f'no key, Unknown Artist, no albums: nothing to do ({r})')


def build_state_total(m):
    return m.word(PSYMS['cb'] + 4 * 6)


def settings_tests(ctx):
    """Settings > Library > Rebuild Artist Photos: under Rebuild Covers; the stock confirm, then the request file Home's pass acts on and a toast; the covers' rebuild is untouched."""
    expect, P = ctx.expect, pod_pages
    C = P.LIBRARY_PAGE
    cv = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_REBUILD)
    rb = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_AREBUILD)
    expect(rb == cv + 1 and C.rows[rb].label == 'Rebuild Artist Photos' and P.row_kind(C.rows[rb]) == 'action' and P.ACT_AREBUILD == 92, 'the row is directly under Rebuild Covers and acts in place (no chevron)')
    on_row, rows_s = PSYMS['on_row'], PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    cf_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.LIBRARY_PAGE_INDEX)
    KEY, AREQ, REQ = 'Rebuild all artist photos? This may take a few minutes.', '/mnt/data/m1plus/artists-rebuild', '/mnt/data/m1plus/covers-rebuild'

    def machine(language=None, yes=False, fail=False):
        m = cover_machine(albums=3)
        for n in ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + [f'pod_switch{i}' for i in range(len(C.rows))]:
            if n not in m.widgets: m.widget(n)
        if language: m.set_language(language)
        m.confirm_yes = yes
        if fail: m.fail.add(('write', AREQ + '.tmp'))
        m.call(on_row, a0=rows_s + 12 * cf_i, count=3000000)
        m.click(f'pod_row{rb}', count=6000000)
        return m
    m = machine()
    confirms = [c for c in m.calls if c[0] == 'confirm']
    expect(confirms == [('confirm', KEY, O['CONFIRM_KIND_WRAP'])], f'a tap asks first, in the stock confirm dialog (wrapped) ({confirms})')
    expect(not any(n in m.names() for n in ('window_open', 'pthread_create', 'mkdir', 'rename', 'unlink', 'fopen', 'toast')) and AREQ not in m.fs, 'No: nothing happens at all')
    m = machine(yes=True)
    expect(m.fs.get(AREQ) == b'1\n' and AREQ + '.tmp' not in m.fs and ('rename', AREQ + '.tmp', AREQ) in m.calls and [c[1] for c in m.calls if c[0] == 'toast'] == ['Artist photos will rebuild on Home'],
           'Yes writes the request file atomically and shows the toast')
    expect(REQ not in m.fs and not any(n in m.names() for n in ('window_open', 'pthread_create', 'unlink')) and ('opendir', '/mnt/mmc/.m1plus/covers') not in m.calls,
           'the covers\' rebuild is not requested and no .bad is cleared; the page stays, no worker')
    m = machine(yes=True, fail=True)
    expect(AREQ not in m.fs and [c[1] for c in m.calls if c[0] == 'toast'] == ['Storage unavailable'], 'storage that refuses the write: the "Storage unavailable" toast, no request')
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        m = machine(language=loc, yes=True)
        expect([c[1] for c in m.calls if c[0] == 'toast'] == [T('Artist photos will rebuild on Home')], f'{loc}: the toast is translated')
        m = machine(language=loc)
        expect([c[1] for c in m.calls if c[0] == 'confirm'] == [T(KEY)], f'{loc}: the confirm message reads {T(KEY)!r}')
    expect(all(len(pod_i18n.TEXT[k][loc].encode()) > 0 for k in ('Rebuild Artist Photos', 'Artist Photos', 'Photos', KEY, 'Artist photos will rebuild on Home') for loc in pod_i18n.TEXT[KEY]) and len(pod_i18n.TEXT[KEY]) == 13,
           'every new string has all 13 languages')
    # the pass honours the request (home_tests above): the file's name is the one Settings Files lists
    expect('artists-rebuild' in P.SETTING_FILES, 'the request is listed on Settings > Developer > Tools > Settings Files')


def counts_tests(ctx):
    """Settings > Developer > Cache: the Artist Photos card counts the pictures (non-empty a<key>-44.jpg) and the artists with none (empty ones) in the artists cache."""
    expect, P = ctx.expect, pod_pages
    CP, D = P.CACHE_PAGE, P.DEVELOPER_PAGE
    shape = [x.text if isinstance(x, P.Hdr) else 'gap' if x == P.GAP else x.label for x in CP.layout]
    i = shape.index('Artist Photos')
    expect(shape[i:i + 3] == ['Artist Photos', 'Photos', 'None'] and shape[i - 1] == 'Clear Cover Cache' and shape[i + 3] == 'Track Durations', f'the card sits between the Covers and Track Durations sections ({shape})')
    ph = next(r for r in CP.rows if r.label == 'Photos')
    no = next(r for r in CP.rows if r.label == 'None')
    expect(ph.action == no.action == P.ACT_INFO and (ph.arg, no.arg) == (P.INFO_DUR + 1, P.INFO_DUR + 2) and P.INFO_APHOTOS == P.INFO_DUR + 1, 'two info rows with kinds after Measured Tracks (frozen ids: appended)')
    ph_i, no_i = CP.rows.index(ph), CP.rows.index(no)
    cc_i = next(i for i, r in enumerate(D.rows) if r.action == P.ACT_PAGE and r.arg == P.CACHE_PAGE_INDEX)
    m = cover_machine(albums=4, cached=False)
    for n in ['btn_return', 'btn_backtoplayer', 'pod_chevron'] + [f'pod_row{k}' for k in range(len(CP.rows))] + [f'pod_value{k}' for k in range(len(CP.rows))]:
        if n not in m.widgets: m.widget(n)
    names = [f'a{k:08x}-44.jpg' for k in (0x11, 0x22, 0x33, 0x44)]
    ents = [('.', 4)] + [(n, 8) for n in names] + [('a00000011-168.jpg', 8), ('a00000011.src', 8), ('a00000055-44.jpg.tmp', 8), ('purity', 8), ('r00000001-44.jpg', 8), ('a1234-44.jpg', 8)]
    m.listing[AP] = ents
    for n, size in zip(names, (900, 0, 1200, 0)): m.files[f'{AP}/{n}'] = size; m.present.add(f'{AP}/{n}')
    for n in ('a00000011-168.jpg', 'a00000011.src', 'a00000055-44.jpg.tmp', 'purity', 'r00000001-44.jpg', 'a1234-44.jpg'): m.files[f'{AP}/{n}'] = 77; m.present.add(f'{AP}/{n}')
    m.call(PSYMS['on_row'], a0=PSYMS[f'pod_rows_{P.DEVELOPER_PAGE_INDEX}'] + 12 * cc_i, count=6000000)
    first = list(m.calls)
    expect(('widget_set_text_utf8', m.widgets[f'pod_value{ph_i}'], '\xe2\x80\xa6') in first and ('widget_set_text_utf8', m.widgets[f'pod_value{no_i}'], '\xe2\x80\xa6') in first, 'while counting: an ellipsis')
    seen = []
    for _ in range(60):
        seen += fired(m, 'cp_tick', 40000000)
        if not [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['cp_tick']]: break
    expect(('widget_set_text_utf8', m.widgets[f'pod_value{ph_i}'], '2') in seen and ('widget_set_text_utf8', m.widgets[f'pod_value{no_i}'], '2') in seen,
           'counted: two pictures and two empty markers; the 168 file, .src, temporary files, the map and strangers are not counted')


def crop_tests(ctx):
    """The cache files are squares cut from the photo: landscape centred, portrait from a third of the extra height down, small photos cropped but not enlarged."""
    import io
    from PIL import Image
    expect = ctx.expect
    albums = [('Abba', f'{MUSIC}/Abba/Arrival/01.flac')]
    cols = [(220, 30, 30), (30, 200, 30), (30, 30, 220), (230, 220, 30), (200, 30, 200), (30, 200, 200)]

    def bands(w, h, vertical, fmt='JPEG', step=100):
        im = Image.new('RGB', (w, h))
        for i in range(0, (w if vertical else h) // step + 1):
            box = (i * step, 0, (i + 1) * step, h) if vertical else (0, i * step, w, (i + 1) * step)
            im.paste(cols[i % 6], box)
        b = io.BytesIO(); im.save(b, fmt)
        return b.getvalue()

    def made(data, name='artist.jpg'):
        m = library({f'{MUSIC}/Abba/{name}': data}, albums)
        run_set(m, albums)
        k = key(m, 'Abba')
        return m, k

    def near(im, x, y, c): return all(abs(a - b) <= 28 for a, b in zip(im.convert('RGB').getpixel((x, y)), c))

    # portrait 300 x 600 (extra 300, so the square starts at y 100): bands of 100 rows, the output shows rows 100..399 = bands 1, 2, 3
    for fmt, name in (('JPEG', 'artist.jpg'), ('PNG', 'artist.png')):
        m, k = made(bands(300, 600, False, fmt), name)
        big, small = CA.decoded(m.fs[f168(k)]), CA.decoded(m.fs[f44(k)])
        expect(big.size == (168, 168) and small.size == (44, 44), f'portrait {fmt}: square 168 and 44 files ({big.size}, {small.size})')
        expect(near(big, 84, 10, cols[1]) and near(big, 84, 84, cols[2]) and near(big, 84, 158, cols[3]), f'portrait {fmt}: the square starts a third of the extra height down (bands 1, 2, 3)')
        expect(near(small, 22, 3, cols[1]) and near(small, 22, 40, cols[3]), f'portrait {fmt}: the 44 px file shows the same part')

    # landscape 600 x 300 (extra 300, the square starts at x 150): bands of 50 columns, the output shows columns 150..449 = bands 3..8
    m, k = made(bands(600, 300, True, step=50))
    big, small = CA.decoded(m.fs[f168(k)]), CA.decoded(m.fs[f44(k)])
    expect(big.size == (168, 168) and small.size == (44, 44), f'landscape: square files ({big.size}, {small.size})')
    expect(near(big, 5, 84, cols[3]) and near(big, 162, 84, cols[2]), 'landscape: centred across the width (columns 150 to 449)')

    # square: unchanged
    m, k = made(bands(400, 400, False))
    expect(size_of(m, f168(k)) == (168, 168) and size_of(m, f44(k)) == (44, 44) and near(CA.decoded(m.fs[f168(k)]), 84, 5, cols[0]), 'square: the whole picture')

    # smaller than 168: cropped to the short side, not enlarged; the 44 px file is made from that square
    for w, h, side, y0 in ((120, 80, 80, 0), (80, 120, 80, 13), (168, 100, 100, 0), (100, 168, 100, 22), (40, 90, 40, 16)):
        m, k = made(bands(w, h, False, step=10))
        big, small = size_of(m, f168(k)), size_of(m, f44(k))
        want_small = (44, 44) if side > 44 else (side, side)
        expect(big == (side, side) and small == want_small, f'{w} x {h}: a {side} px square, not enlarged ({big}, {small})')
        if side >= 80:
            expect(near(CA.decoded(m.fs[f168(k)]), side // 2, 1, cols[(y0 // 10) % 6]), f'{w} x {h}: the square starts at row {y0}')


SECTIONS = [key_tests, discovery_tests, crop_tests, request_tests, purity_snapshot_tests, purity_tests, recheck_tests, home_tests, lead_tests, lookup_tests, circle_tests, settings_tests, counts_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

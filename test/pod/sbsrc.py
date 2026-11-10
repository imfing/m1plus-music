"""The Navidrome library source (patch/sbsrc.c, patch/sbsrc.h, docs/modules/subsonic.md "The seam"): lib_nd's lists as stock-shaped records built from the cache files of sbapi.c (what the
pages read from them, the id round trip, the requests a missing list starts), the Songs list's windowed read, cap and memory, `complete`, `gen`, `cover`, `seconds`, the row extras and
the row-menu actions, and the play queue (stream address or local file, DSD, the 64 cap, the playing marker). The compiled payload runs under Unicorn against the card of the download
tests and a scripted libcurl; the stock deque copies the record and every string it holds (the push hook below models that and counts the heap a list costs). Sections: lists, songs,
play, extras, trackcover (a track shows its album's cover file), sheet, awake, messages, queue_star (everything, or `sbsrc/<section>`)."""
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


SA = sibling('sbapi')
SD = sibling('sbdl')
PCN = SA.PCN
ND = SA.ND
LS_ALBUMS, LS_ARTISTS, LS_SONGS, LS_PLAYLISTS, LS_FAVORITES, LS_DOWNLOADED = range(6)
F_LIST, F_RECID, F_PLAY, F_COVER, F_SECONDS, F_ROW, F_ACT, F_GEN, F_COMPLETE = (4 * i for i in range(1, 10))
F_CAPS, F_COUNT = 48, 52   # lib_src_t.caps and .count, after queue_row (44)
ACT_DOWNLOAD, ACT_DELETE, ACT_FAVORITE, ACT_UNFAVORITE, ACT_DOWNLOAD_ALL = 1, 2, 3, 5, 6
REC_ID, REC_NAME, REC_PATH, REC_TITLE, REC_ALBUM, REC_ARTIST, REC_META, REC_YEAR, REC_TYPE, REC_CLASS, REC_TRACK, REC_DISC, REC_CREATED = (0, 8, 0xc, 0x10, 0x14, 0x18, 0x28, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x50)
SONGS_MAX = 10000
OPEN = PSYMS['pod_open_player']
LIB = PSYMS['lib_nd']
S32 = lambda v: v - (1 << 32) if v >= 1 << 31 else v


def chunk(n):
    """A malloc chunk for n bytes on the device's 32-bit libc: 4 bytes of header, 8 aligned, 16 at least."""
    return max(16, (n + 4 + 7) & ~7)


class SM(SD.DM):
    """The download tests' card machine plus the stock deque's copy: _deque_push_back copies the 0x58 byte record and strdups every string at +4..+0x2c (the stSongInfo copy function,
    docs/modules/addresses.md), and counts what that costs on the device's heap (`heap_cost`: per deque handle)."""
    def __init__(self):
        super().__init__()
        self.heap_cost = {}

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name in ('strlen', 'strchr', 'strrchr'):   # (libc string calls the stock mocks leave out)
            a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
            text = self.read_cstr(a0).encode('latin-1')
            if name == 'strlen':
                ret = len(text)
            else:
                i = (text + b'\0').find(a1 & 0xff) if name == 'strchr' else (text + b'\0').rfind(a1 & 0xff)
                ret = a0 + i if i >= 0 else 0
            u.reg_write(UC_MIPS_REG_V0, ret)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == '_deque_push_back':
            a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
            rec = bytearray(bytes(u.mem_read(a1, 0x58)))
            cost = 0x58
            for off in range(4, 0x30, 4):
                p = struct.unpack_from('<I', rec, off)[0]
                if p:
                    s = self.read_cstr(p).encode('latin-1')
                    a = self.malloc(len(s) + 1)
                    u.mem_write(a, s + b'\0')
                    struct.pack_into('<I', rec, off, a)
                    cost += chunk(len(s) + 1)
            c = self.malloc(0x58)
            u.mem_write(c, bytes(rec))
            self.deques.setdefault(a0, []).append(c)
            self.heap_cost[a0] = self.heap_cost.get(a0, 0) + cost
            self.calls.append(('_deque_push_back', a0, c))
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


def machine(site=None, conf=True, **kw):
    m = SM()
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(PCN.CA)
    m.reuse_heap = True
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    if conf:
        m.put(SA.CONF, b'http://nd.example:4533|alice|secret')
    m.curl_site = site or quiet_site()
    m.card_mounted = True
    m.wifi = 4
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def quiet_site(**routes):
    """A scripted server that answers the views in routes and fails every other request (the cache files the test seeded stay as they are)."""
    site = SA.Site(**routes)
    site.default = {'rc': 6}
    return site


def member(m, off): return m.word(LIB + off)


def call(m, off, *args):
    """lib_nd's member at off with up to six arguments (the fifth and sixth on the stack, o32); the C int result."""
    regs = {f'a{i}': (m.cstr(v) if isinstance(v, str) else v) for i, v in enumerate(args[:4])}
    m.u.mem_write(STACK + 16, struct.pack('<II', *(((args[4:] + (0, 0))[:2]))))
    return S32(m.call(member(m, off), count=1 << 40, **regs))


def rec(m, r):
    def s(off):
        p = m.word(r + off)
        return m.read_cstr(p) if p else None
    return dict(id=S32(m.word(r + REC_ID)), name=s(REC_NAME), path=s(REC_PATH), title=s(REC_TITLE), album=s(REC_ALBUM), artist=s(REC_ARTIST), meta=s(REC_META), year=m.word(r + REC_YEAR),
                type=m.word(r + REC_TYPE), cls=m.word(r + REC_CLASS), track=m.word(r + REC_TRACK), disc=m.word(r + REC_DISC), created=m.word(r + REC_CREATED))


def rows(m, h): return [rec(m, r) for r in m.deques.get(h, [])] if h else []


def listing(m, which, scope=0, run=True):
    """(the list handle, its records, the views the server was asked for): the worker a request started is run to its end (a failing server unless the test scripted the view)."""
    before = len(m.curl_site.urls)
    m.thread = None
    h = call(m, F_LIST, LIB, which, scope) & 0xffffffff
    if run and m.thread:
        SA.drain(m, m.thread)
    return h, rows(m, h), m.curl_site.views()[before:]


def rid(m, r): return m.read_cstr(call(m, F_RECID, LIB, r) & 0xffffffff)


def trk(i, **kw):
    d = dict(id=f't{i}', title=f'Song {i}', artist='An Artist', album='An Album', album_id='al1', cover=f'cv-t{i}', suffix='flac', seconds=100 + i, track=i, disc=1, year=2001, size=5000 + i,
             bitrate=900, sample_rate=44100, bit_depth=16, created=1700000000 + i, starred=0)
    d.update(kw)
    return d


def alb(i, **kw):
    d = dict(id=f'al{i}', name=f'Album {i}', artist='An Artist', artist_id='r1', cover=f'cv-al{i}', year=2000 + i, songs=3, seconds=600, created=1690000000 + i, starred=0)
    d.update(kw)
    return d


def seed(m, rel, kind, items, flags=0):
    SA.seed(m, f'{ND}/{rel}', kind, items, flags)


def big_songs(m, n, flags=0):
    """songs.idx of n rows with the longest realistic texts (36 character ids, 48 character cover ids, 28 character titles), packed without the slow generic row()."""
    out = bytearray(b'SBA1' + struct.pack('<3I', SA.KIND['track'], struct.calcsize(SA.TRACK), flags))
    for i in range(n):
        ident = f'{i:08x}-1111-2222-3333-{i:012x}'
        out += struct.pack(SA.TRACK, ident.encode(), f'Track number {i} of the album'.encode(), b'The Example Quartet', b'An Album With A Fairly Long Name', b'al-' + ident.encode(), f'mf-{ident}_66aa11bb'.encode(), b'flac',
                           200 + i % 100, i % 20 + 1, 1, 2000, 30000000, 900, 44100, 16, 1700000000, 0)
    m.put(f'{ND}/songs.idx', bytes(out))


def signed_id(text): return S32(int(text))


def deque_row(m, h, i): return m.deques[h][i]


def albums_rows(m, items):
    seed(m, 'albums.idx', 'album', items)
    return listing(m, LS_ALBUMS)[0]


def lists(ctx):
    expect = ctx.expect
    m = machine()
    expect(m.read_cstr(m.word(LIB)) == 'navidrome', 'lib_nd is named "navidrome"')
    expect(m.word(LIB + F_CAPS) == 2 and member(m, F_COUNT) != 0, 'lib_nd: caps LS_CAP_SEARCH only (its pages show Search, no Cover Flow or Select yet); a count member')
    expect(m.call(PSYMS['lib_navidrome'], count=2000000) == LIB and machine(conf=False).call(PSYMS['lib_navidrome'], count=2000000) == 0, 'lib_navidrome(): the source while a server is saved, NULL otherwise')
    # albums
    seed(m, 'albums.idx', 'album', [alb(1), alb(2, name='Zed', artist='Other')])
    h, rs, asked = listing(m, LS_ALBUMS)
    a = rs[0]
    expect(len(rs) == 2 and (a['title'], a['album'], a['artist'], a['year'], a['type'], a['created'], a['path']) == ('Album 1', 'Album 1', 'An Artist', 2001, 4, 1690000001, 'nd://al1')
           and a['id'] <= -3 and a['name'] is None and rs[1]['artist'] == 'Other', f'albums: title, album, artist, year, creation time, path nd://id, a synthetic REC_ID <= -3: {a}')
    expect(rid(m, deque_row(m, h, 0)) == 'al1' and rid(m, deque_row(m, h, 1)) == 'al2', 'rec_id returns the server id of a record')
    expect(asked == ['getAlbumList2'], f'no sync yet: the list is returned and a sync is asked for ({asked})')
    asked = listing(m, LS_ALBUMS)[2]
    expect(asked == [], 'a second read soon after does not ask again (a failing server cannot be hammered)')
    m.clock += 11000
    expect(listing(m, LS_ALBUMS)[2] == ['getAlbumList2'], 'after 10 s it is asked for again')
    # artists, an artist's albums
    m = machine(site=quiet_site(getArtist={'body': SA.ok_json(artist={'id': 'r1', 'album': [{'id': 'al1', 'name': 'Album 1'}]})}))
    seed(m, 'artists.idx', 'artist', [dict(id='r1', name='An Artist', cover='cv-r1', albums=2)])
    h, rs, asked = listing(m, LS_ARTISTS)
    expect(len(rs) == 1 and (rs[0]['title'], rs[0]['artist'], rs[0]['path'], rs[0]['type']) == ('An Artist', 'An Artist', 'nd://r1', 4), f'artists: the name in title and artist: {rs}')
    artist_row = deque_row(m, h, 0)
    expect(listing(m, LS_ARTISTS, artist_row)[0] == 0, 'artists has no scope')
    h, rs, asked = listing(m, LS_ALBUMS, artist_row)
    expect(h == 0 and asked == ['getArtist'], f'an artist\'s albums not cached: no list, getArtist asked for ({asked})')
    seed(m, 'ar/r1.idx', 'album', [alb(1), alb(2)])
    h, rs, asked = listing(m, LS_ALBUMS, artist_row)
    expect([r['title'] for r in rs[:2]] == ['Album 1', 'Album 2'] and len(rs) == 3 and rs[2]['id'] == -2 and rs[2]['type'] == 4 and rs[2]['artist'] == 'An Artist' and rid(m, deque_row(m, h, 2)) == 'r1',
           f'an artist\'s albums with the stock All songs row last (REC_ID -2, the artist\'s id): {[r["title"] for r in rs]}')
    expect(asked == [], 'the artist was asked for in this run and its list is cached: not asked again')
    # an album's tracks
    m = machine(site=quiet_site(getAlbum={'body': SA.ok_json(album={'id': 'al1', 'song': [{'id': 't9', 'title': 'N'}]})}))
    album_row = deque_row(m, albums_rows(m, [alb(1)]), 0)
    h, rs, asked = listing(m, LS_SONGS, album_row)
    expect(h == 0 and asked == ['getAlbum'], f'an album\'s tracks not cached: NULL and getAlbum asked for ({asked})')
    seed(m, 'al/al1.idx', 'track', [trk(3, disc=1), trk(1, disc=2), trk(2, disc=1), trk(5, starred=1, suffix='dsf')])
    h, rs, asked = listing(m, LS_SONGS, album_row)
    expect([r['title'] for r in rs] == ['Song 2', 'Song 3', 'Song 5', 'Song 1'], f'album tracks come in disc then track order: {[r["title"] for r in rs]}')
    r0 = rs[0]
    expect((r0['title'], r0['artist'], r0['album'], r0['track'], r0['disc'], r0['year'], r0['type'], r0['path'], r0['created']) == ('Song 2', 'An Artist', 'An Album', 2, 1, 2001, 8, 'nd://t2', 1700000002)
           and r0['id'] <= -3 and r0['name'] is None, f'a track record: texts, numbers, REC_PATH nd://id, REC_TYPE 8: {r0}')
    expect(rid(m, deque_row(m, h, 0)) == 't2' and rid(m, 0) == '', 'rec_id of a track; "" for NULL')
    expect(len(set(r['id'] for r in rs)) == 4, 'the synthetic ids differ')
    expect(asked == [], 'the album was asked for in this run: not asked again')
    m = machine(site=quiet_site(getAlbum={'body': SA.ok_json(album={'id': 'al1', 'song': [{'id': 't9', 'title': 'N'}]})}))
    seed(m, 'al/al1.idx', 'track', [trk(1)])
    album_row = deque_row(m, albums_rows(m, [alb(1)]), 0)
    h, rs, asked = listing(m, LS_SONGS, album_row)
    expect(len(rs) == 1 and asked == ['getAlbum'], f'a cached album shows at once and is refreshed once in a run ({asked})')
    expect(listing(m, LS_SONGS, album_row)[2] == [], 'and not again')
    # a playlist's tracks
    m = machine()
    seed(m, 'playlists.idx', 'playlist', [dict(id='p1', name='Mix', cover='cv-p1', songs=2, seconds=300)])
    h, rs, asked = listing(m, LS_PLAYLISTS)
    expect(len(rs) == 1 and (rs[0]['title'], rs[0]['path'], rs[0]['type']) == ('Mix', 'nd://p1', 4), f'playlists: {rs}')
    prow = deque_row(m, h, 0)
    expect(call(m, F_COUNT, LIB, LS_PLAYLISTS, prow) == 2 and call(m, F_COUNT, LIB, LS_PLAYLISTS, 0) == 0 and call(m, F_COUNT, LIB, LS_SONGS, prow) == 0,
           'count: a playlist\'s sync songCount until its tracks are read (2); no record or another list: 0')
    seed(m, 'pl/p1.idx', 'track', [trk(7), trk(4)])
    h, rs, asked = listing(m, LS_PLAYLISTS, prow)
    expect([r['title'] for r in rs] == ['Song 7', 'Song 4'] and asked == ['getPlaylist'], f'a playlist\'s tracks keep the playlist\'s own order: {[r["title"] for r in rs]}')
    expect(call(m, F_COUNT, LIB, LS_PLAYLISTS, prow) == 2, 'a getPlaylist that failed (the test server\'s answer): the sync count still stands')
    m = machine(site=quiet_site(getPlaylist={'body': SA.ok_json(playlist={'id': 'p1', 'songCount': 2, 'entry': []})}))
    seed(m, 'playlists.idx', 'playlist', [dict(id='p1', name='Mix', cover='cv-p1', songs=2, seconds=300)])
    prow = deque_row(m, listing(m, LS_PLAYLISTS)[0], 0)
    h, rs, asked = listing(m, LS_PLAYLISTS, prow)
    expect(h == 0 and asked == ['getPlaylist'] and call(m, F_COUNT, LIB, LS_PLAYLISTS, prow) == 0, 'an empty answer from the server is final: count 0, not the sync\'s 2')
    # the Playlists page's scan of 20 cached playlists (more than the 16 requests nl_may_ask remembers) asks for none of them, however often the page opens
    m = machine(site=quiet_site())
    seed(m, 'playlists.idx', 'playlist', [dict(id=f'p{i}', name=f'Mix {i}', cover=f'cv-p{i}', songs=1, seconds=100) for i in range(20)])
    for i in range(20): seed(m, f'pl/p{i}.idx', 'track', [trk(i)])
    ph = listing(m, LS_PLAYLISTS)[0]
    before = len(m.curl_site.urls); m.thread = None
    for _ in range(3):
        for i in range(20):
            sh = m.call(PSYMS['sbs_playlist_scan'], a0=LIB, a1=deque_row(m, ph, i), count=2000000) & 0xffffffff
            expect(sh and [r['title'] for r in rows(m, sh)] == [f'Song {i}'], f'the scan reads the cached tracks of playlist {i}')
    expect(m.curl_site.urls[before:] == [] and m.thread is None, f'the scan of 20 cached playlists asks the server for none, however many times the page opens ({m.curl_site.urls[before:]}, {m.thread})')
    seed(m, 'playlists.idx', 'playlist', [dict(id='px', name='New', cover='cv-px', songs=1, seconds=100)])
    nh = listing(m, LS_PLAYLISTS)[0]
    expect(m.call(PSYMS['sbs_playlist_scan'], a0=LIB, a1=deque_row(m, nh, 0), count=2000000) == 0 and m.thread is not None, 'a playlist that is not cached is still asked for by the scan')
    # favourites and downloaded
    seed(m, 'starred.idx', 'track', [trk(1, starred=1), trk(2, starred=1)])
    h, rs, asked = listing(m, LS_FAVORITES)
    expect([r['title'] for r in rs] == ['Song 1', 'Song 2'] and rs[0]['meta'].split('\t')[3] == '1', 'Favorites: the starred tracks, flagged as favourites')
    expect(listing(m, LS_FAVORITES, deque_row(m, h, 0))[0] == 0, 'Favorites has no scope')
    m = machine()
    dl_two_tracks(m, [SD.track('d1', 'One', 'flac'), SD.track('d2', 'Two', 'mp3')])
    seed(m, 'starred.idx', 'track', [trk(9, id='d2', starred=1)])   # (starred after it was downloaded)
    m.wifi = -1
    h, rs, asked = listing(m, LS_DOWNLOADED)
    expect([r['title'] for r in rs] == ['One', 'Two'] and asked == [], f'Downloaded: the manifest rows, read with Wi-Fi off and no request: {[r["title"] for r in rs]}')
    expect(rs[0]['meta'].split('\t')[2] == 'flac' and rs[0]['year'] == 2020 and rid(m, deque_row(m, h, 1)) == 'd2', 'with the track\'s own data')
    expect([r['meta'].split('\t')[3] for r in rs] == ['0', '1'], f'Downloaded: the hearts are the Favorites list\'s, not the manifest\'s of the day of the download ({[r["meta"].split(chr(9))[3] for r in rs]})')
    # an artist's all songs: the albums' tracks that are cached, the other albums asked for
    m = machine(site=quiet_site(getAlbum={'body': SA.ok_json(album={'id': 'al2', 'song': [{'id': 'x', 'title': 'x'}]})}))
    seed(m, 'artists.idx', 'artist', [dict(id='r1', name='An Artist', albums=2)])
    seed(m, 'ar/r1.idx', 'album', [alb(1), alb(2)])
    seed(m, 'al/al1.idx', 'track', [trk(1), trk(2)])
    ah = listing(m, LS_ARTISTS)[0]
    h, rs, asked = listing(m, LS_ALBUMS, deque_row(m, ah, 0))
    allrow = deque_row(m, h, 2)
    h, rs, asked = listing(m, LS_SONGS, allrow)
    expect([r['title'] for r in rs] == ['Song 1', 'Song 2'] and 'getAlbum' in asked, f'the artist\'s All Songs row: the cached albums\' tracks, the other album asked for: {[r["title"] for r in rs]} {asked}')
    # nothing for a scope the source does not know
    expect(listing(m, LS_SONGS, m.alloc(0x58))[0] == 0, 'a record that is not ours as scope: NULL')


def songs(ctx):
    expect = ctx.expect
    # a library bigger than the cap: the first SBS_SONGS_MAX rows only, read a window at a time
    m = machine()
    big_songs(m, 50000)
    h, rs, asked = listing(m, LS_SONGS)
    callocs = [c[1] for c in m.calls if c[0] == 'calloc']
    cost = m.heap_cost.get(h, 0)
    expect(len(rs) == SONGS_MAX and rs[0]['title'] == 'Track number 0 of the album' and rs[-1]['title'] == f'Track number {SONGS_MAX - 1} of the album', f'50,000 cached: the first {SONGS_MAX} rows ({len(rs)})')
    expect(asked == [], 'the list is at its cap: no page is asked for')
    expect(callocs and max(callocs) <= 32 * 820 + 4096, f'songs.idx is read 32 rows at a time (largest calloc {max(callocs)} bytes, not the 41 MB file)')
    print(f'  Songs list at the cap: {len(rs)} rows, heap model {cost / 1048576:.2f} MiB ({cost / len(rs):.0f} bytes a row), largest transient {max(callocs) / 1024:.0f} KiB')
    expect(cost < 4 * 1048576, f'the Songs list at the cap holds under 4 MiB of heap ({cost / 1048576:.2f} MiB)')
    expect(call(m, F_COMPLETE, LIB, LS_SONGS) == 1, 'complete: the list is at its cap, it will not grow')
    expect(call(m, F_COMPLETE, LIB, LS_ALBUMS) == 1, 'every other list is always complete')
    # a part: more to come
    m = machine(site=quiet_site(search3={'body': SA.ok_json(searchResult3={'song': [{'id': 'n1', 'title': 'N'}]})}))
    big_songs(m, 500, flags=1)
    h, rs, asked = listing(m, LS_SONGS, run=False)
    expect(len(rs) == 500 and call(m, F_COMPLETE, LIB, LS_SONGS) == 0 and SA.state(m, SA.K['SONGS'])[0] == SA.ST['LOAD'], 'a full page cached: the list holds it, the next page is asked for, complete is 0')
    SA.drain(m, m.thread)
    q = m.curl_site.query(0)
    expect(q['songOffset'] == '500' and q['songCount'] == '100', f'the next page starts at the rows cached: {q}')
    h, rs, asked = listing(m, LS_SONGS)
    expect(len(rs) == 501 and rs[500]['title'] == 'N', 'the page that arrived is in the next read (a short page: nothing more is asked)')
    expect(asked == [] and call(m, F_COMPLETE, LIB, LS_SONGS) == 1, 'and the list is complete')
    # a failed page is retried only after 10 s
    m = machine()
    big_songs(m, 500, flags=1)
    expect(listing(m, LS_SONGS)[2] == ['search3'], 'the next page fails')
    expect(listing(m, LS_SONGS)[2] == [] and call(m, F_COMPLETE, LIB, LS_SONGS) == 0, 'not asked again at once, still not complete')
    m.clock += 11000
    expect(listing(m, LS_SONGS)[2] == ['search3'], 'asked again after 10 s')
    # a short last page: complete
    m = machine()
    big_songs(m, 300, flags=0)
    h, rs, asked = listing(m, LS_SONGS)
    expect(len(rs) == 300 and asked == [] and call(m, F_COMPLETE, LIB, LS_SONGS) == 1, 'a short page ends the list: nothing asked, complete is 1')
    # nothing cached: asked for, empty and not complete while it runs
    m = machine(site=quiet_site(search3={'body': SA.ok_json(searchResult3={'song': []})}))
    h, rs, asked = listing(m, LS_SONGS, run=False)
    expect(h == 0 and call(m, F_COMPLETE, LIB, LS_SONGS) == 0, 'no songs.idx: NULL, page 0 asked for, not complete while it loads')
    SA.drain(m, m.thread)
    h, rs, asked = listing(m, LS_SONGS)
    expect(h == 0 and asked == [] and call(m, F_COMPLETE, LIB, LS_SONGS) == 1, 'a server with no songs: nothing again, complete')
    # the window reader itself
    m = machine()
    big_songs(m, 700)
    buf = m.alloc(820 * 4)
    got = S32(m.call(PSYMS['sba_songs_window'], a0=498, a1=4, a2=buf, count=1 << 30))
    ids = [SA.unrow('track', bytes(m.u.mem_read(buf + 820 * i, 820)))[0] for i in range(got)]
    expect(got == 4 and ids[0].startswith('000001f2') and ids[3].startswith('000001f5'), f'sba_songs_window(498, 4): rows 498..501 ({ids})')
    expect(S32(m.call(PSYMS['sba_songs_window'], a0=698, a1=4, a2=buf, count=1 << 30)) == 2 and S32(m.call(PSYMS['sba_songs_window'], a0=700, a1=4, a2=buf, count=1 << 30)) == 0
           and S32(m.call(PSYMS['sba_songs_window'], a0=0, a1=0, a2=buf, count=1 << 30)) == 0, 'a window is cut at the end; past the end and an empty window read 0')
    expect(S32(machine().call(PSYMS['sba_songs_window'], a0=0, a1=4, a2=buf, count=1 << 30)) == 0, 'no file: 0')


def queue_of(m):
    """(the paths, the ids, the names, the titles, the first index) of the queue the last play opened, or None."""
    if not getattr(m, 'played', None):
        return None
    rs = [rec(m, r) for r in m.played[0]]
    return rs


def play_setup(m, items):
    seed(m, 'al/al1.idx', 'track', items)
    ah = albums_rows(m, [alb(1)])
    return listing(m, LS_SONGS, deque_row(m, ah, 0))[0]


def playit(m, h, at, how=0, cls=0xf003):
    m.played = None
    m.mode = 0
    r = call(m, F_PLAY, LIB, h, at, how, OPEN, cls)
    return r, queue_of(m)


def play(ctx):
    expect = ctx.expect
    m = machine()
    h = play_setup(m, [trk(i) for i in range(1, 8)])
    r, q = playit(m, h, 2)
    expect(r == 0 and q and [x['title'] for x in q] == [f'Song {i}' for i in range(1, 8)] and m.played[1] == 2, f'a row tap: the list in its own order, opened at the tapped track\'s index ({r}, {q and [x["title"] for x in q]}, {m.played and m.played[1]})')
    x = q[2]
    expect(x['path'].startswith('http://nd.example:4533/rest/stream.view?') and 'id=t3' in x['path'] and 'format=raw' in x['path'] and 'secret' not in x['path'], f'the queue record\'s REC_PATH is the stream address (raw): {x["path"]}')
    expect((x['name'], x['title'], x['album'], x['artist'], x['track'], x['disc'], x['type'], x['cls']) == ('Song 3.flac', 'Song 3', 'An Album', 'An Artist', 3, 1, 8, 0), f'name, texts, numbers, type 8, class 0: {x}')
    ids = [S32(m.word(r_ + REC_ID)) for r_ in m.played[0]]
    expect(all(i <= -2 for i in ids) and len(set(ids)) == 7 and ids[2] == -((SA.fnv('t3') & 0x3fffffff) + 2), f'queue REC_IDs are the synthetic ids of sba_queue_note ({ids})')
    expect(m.read_cstr(m.call(PSYMS['sba_rec_track'], a0=ids[3] & 0xffffffff, count=2000000)) == 't4', 'sba_rec_track maps the queue id back to the track')
    # the playing marker: a queue record's id maps to the page's server id
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque(m.played[0]))
    m.play_pos = 3
    expect(m.call(PSYMS['sbs_playing'], a0=m.cstr('t4'), count=2000000) == 1 and m.call(PSYMS['sbs_playing'], a0=m.cstr('t3'), count=2000000) == 0 and m.call(PSYMS['sbs_playing'], a0=m.cstr(''), count=2000000) == 0,
           'sbs_playing(id): the stock player is on the Navidrome track with that id')
    F_PLAYING = 40   # lib_src_t.playing, the last member (after complete at 36)
    expect([call(m, F_PLAYING, LIB, r_) for r_ in m.deques[h][:5]] == [0, 0, 0, 1, 0], 'lib_nd.playing(rec): the page row whose server id the player is on (row 3, id t4), not a REC_PATH compare')
    m.play_pos = -1
    expect(m.call(PSYMS['sbs_playing'], a0=m.cstr('t4'), count=2000000) == 0, 'nothing playing: 0')
    expect(call(m, F_PLAYING, LIB, m.deques[h][3]) == 0, 'lib_nd.playing: nothing playing, 0')
    # Play and Shuffle set the mode; a row tap keeps it
    r, q = playit(m, h, 0, 1)
    expect(r == 0 and m.mode == 0, f'Play starts in order ({m.mode})')
    r, q = playit(m, h, 0, 2)
    expect(m.mode == 2, f'Shuffle sets stock\'s shuffle mode ({m.mode})')
    m.seed = 3
    r, q = playit(m, h, -1)
    expect(r == 0 and q and q[0]['title'].startswith('Song '), 'at -1 starts a random track')
    expect(playit(m, h, 99)[0] == -1 and playit(m, h, 7)[0] == -1, 'a position outside the list: -1')
    # the 64 cap
    m = machine()
    h = play_setup(m, [trk(i, track=i) for i in range(1, 101)])
    r, q = playit(m, h, 10)
    expect(r == 0 and len(q) == 64 and q[0]['title'] == 'Song 11' and q[-1]['title'] == 'Song 74' and m.played[1] == 0, f'a queue is a window of 64 tracks from the tapped one, opened at 0 ({len(q)})')
    r, q = playit(m, h, 90)
    expect(len(q) == 64 and q[0]['title'] == 'Song 37' and q[-1]['title'] == 'Song 100' and m.played[1] == 54 and q[54]['title'] == 'Song 91', 'near the end the window still holds 64 rows (it starts at count - 64) and opens at the tapped one')
    m.seed = 5
    r, q = playit(m, h, -1, 2)
    ts = [x['title'] for x in q]
    ns = [int(t.split()[1]) for t in ts]
    expect(r == 0 and len(q) == 64 and len(set(ts)) == 64, f'Shuffle on 100 queues 64 distinct tracks ({len(q)}, {len(set(ts))})')
    expect(any((b - a) % 100 != 1 for a, b in zip(ns, ns[1:])), f'and they are not one contiguous run ({ns[:12]})')
    m = machine()
    h = play_setup(m, [trk(i, track=i) for i in range(1, 13)])
    m.seed = 9
    r, q = playit(m, h, -1, 2)
    ts = [x['title'] for x in q]
    expect(r == 0 and len(q) == 12 and len(set(ts)) == 12, f'Shuffle on 12 queues all 12 once ({ts})')
    r, q = playit(m, h, 4)
    expect(r == 0 and [x['title'] for x in q] == [f'Song {i}' for i in range(1, 13)] and m.played[1] == 4, 'tapping row 5 of 12 queues the 12 in list order and opens at index 4')
    # Shuffle on every length 1..70: no hang (the stride search is bounded; count 6 has no coprime stride in 2..4), every row once up to the queue's size
    for n in range(1, 71):
        m = machine()
        h = play_setup(m, [trk(i, track=i) for i in range(1, n + 1)])
        m.seed = 11 + n
        r, q = playit(m, h, -1, 2)
        ts = [x['title'] for x in q] if q else []
        if not (r == 0 and len(ts) == min(n, 64) and len(set(ts)) == len(ts) and m.played[1] == 0):
            expect(False, f'Shuffle on {n} rows: {min(n, 64)} distinct tracks opened at 0 ({r}, {len(ts)}, {len(set(ts))})')
            break
    else:
        expect(True, 'Shuffle plays lists of every length 1..70 without hanging, with distinct rows')
    # a build that fails leaves the playing stream's map alone
    m = machine()
    h = play_setup(m, [trk(1), trk(2)])
    r, q = playit(m, h, 0)
    t1 = m.played[0][0]
    tid = S32(m.word(t1 + REC_ID))
    expect(m.read_cstr(m.call(PSYMS['sba_rec_track'], a0=tid & 0xffffffff, count=2000000)) == 't1', 'the first play noted its map')
    seed(m, 'al/al2.idx', 'track', [trk(7, album_id='al2')])
    h2 = listing(m, LS_SONGS, deque_row(m, albums_rows(m, [alb(1), alb(2)]), 1))[0]
    m.call(PSYMS['sba_conf_clear'], count=2000000)   # no stream address can be made now
    r, q = playit(m, h2, 0)
    id7 = -((SA.fnv('t7') & 0x3fffffff) + 2) & 0xffffffff
    expect(r == -1 and m.read_cstr(m.call(PSYMS['sba_rec_track'], a0=tid & 0xffffffff, count=2000000)) == 't1'
           and m.read_cstr(m.call(PSYMS['sba_rec_track'], a0=id7, count=2000000)) == '', 'a failed build ("Can\'t play") leaves the playing queue\'s map in place, the new one is not kept')
    # a track whose stream address cannot be made (the server is not configured): "Can't play", not "Not enough memory"
    m = machine(conf=False)
    h = play_setup(m, [trk(1)])
    r, q = playit(m, h, 0)
    expect(r == -1 and q is None and [c[1] for c in m.calls if c[0] == 'toast'] == ["Can't play"], f'no stream address: "Can\'t play" ({[c for c in m.calls if c[0] == "toast"]})')
    # DSD: skipped in the queue, a tapped one not on the card answers -2
    m = machine()
    h = play_setup(m, [trk(1), trk(2, suffix='dsf'), trk(3), trk(4, suffix='DFF'), trk(5)])
    r, q = playit(m, h, 0)
    expect(r == 0 and [x['title'] for x in q] == ['Song 1', 'Song 3', 'Song 5'], f'DSD tracks that are not downloaded are left out of the queue ({[x["title"] for x in q]})')
    r, q = playit(m, h, 4)
    expect(r == 0 and m.played[1] == 2 and q[2]['title'] == 'Song 5', f'the index is the tapped track\'s place among the rows that went in ({m.played and m.played[1]})')
    r, q = playit(m, h, 1)
    expect(r == -2 and q is None and not any(c[0] == 'toast' for c in m.calls), 'the tapped track is DSD and not on the card: -2, nothing starts, no message (the page asks)')
    # a downloaded track plays its local file, DSD included
    m = machine()
    ts = [SD.track('d1', 'One', 'flac'), SD.track('d2', 'Dsd Two', 'dsf')]
    dl_two_tracks(m, ts)
    h = play_setup(m, [trk(1, id='d1', title='One', suffix='flac'), trk(2, id='d2', title='Dsd Two', suffix='dsf'), trk(3)])
    r, q = playit(m, h, 0)
    f1, f2 = f'{SD.MUSIC}/{SD.name_of(ts[0])}', f'{SD.MUSIC}/{SD.name_of(ts[1])}'
    expect(r == 0 and [x['path'] for x in q][:2] == [f1, f2] and q[0]['name'] == SD.name_of(ts[0]) and q[2]['path'].startswith('http'),
           f'a downloaded track is queued as its local file (the DSD one too); the rest stream: {[x["path"][:50] for x in q]}')
    r, q = playit(m, h, 1)
    expect(r == 0 and q[1]['path'] == f2 and m.played[1] == 1, 'a downloaded DSD track plays when tapped')
    # offline: only downloaded tracks are queued; a tapped one that is not says so
    m.wifi = -1
    r, q = playit(m, h, 0)
    expect(r == 0 and [x['path'] for x in q] == [f1, f2], 'Wi-Fi off: the downloaded tracks play, the streams are left out')
    r, q = playit(m, h, 2)
    expect(r == -1 and q is None and any(c[0] == 'toast' and c[1] == 'Connect to Wi-Fi first' for c in m.calls), 'Wi-Fi off and the tapped track is not downloaded: "Connect to Wi-Fi first", nothing starts')
    # the Play pill (LS_PLAY_ORDER) is not a row: it starts at the first row that can play
    m = machine()
    dl_two_tracks(m, ts)
    h = play_setup(m, [trk(3, track=1), trk(1, id='d1', title='One', suffix='flac', track=2), trk(2, id='d2', title='Dsd Two', suffix='dsf', track=3)])
    m.wifi = -1
    m.calls = []
    r, q = playit(m, h, 0, 1)
    expect(r == 0 and [x['path'] for x in q] == [f1, f2] and m.played[1] == 0 and not any(c[0] == 'toast' for c in m.calls), f'Play with Wi-Fi off and the first track not on the card: the downloaded ones play from the first of them, no message ({r})')
    r, q = playit(m, h, 0)
    expect(r == -1 and q is None, f'a tap on that first row still refuses ({r}, {q and [x["path"][:40] for x in q]})')
    m = machine()
    h = play_setup(m, [trk(1, suffix='dsf'), trk(2), trk(3)])
    r, q = playit(m, h, 0, 1)
    expect(r == 0 and [x['title'] for x in q] == ['Song 2', 'Song 3'] and m.played[1] == 0, 'Play on a list whose first track is DSD and not on the card: it starts at the next one, no question')
    m = machine()
    h = play_setup(m, [trk(1, suffix='dsf'), trk(2, suffix='dsf')])
    expect(playit(m, h, 0, 1)[0] == -2, 'Play with nothing that can play: the first row\'s own answer (DSD: -2, the page asks)')
    # a page copy of the list plays too (the records carry their own data)
    m = machine()
    h = play_setup(m, [trk(1, cover='mf-x'), trk(2)])
    copy = m.new_deque(list(m.deques[h]))
    r, q = playit(m, copy, 0)
    expect(r == 0 and len(q) == 2, 'a list handed back as the page holds it plays')
    cover = f'{SA.COVERS}/{SA.fnv("cv-al1"):08x}-168.jpg'
    m.put(cover, SA.JPEG)
    expect(m.read_cstr(m.call(PSYMS['sba_now_cover'], a0=m.played[0][0], count=2000000)) == cover, 'Now Playing\'s cover map is filled from the records (the playing track\'s album cover file, not its own mf-x)')


def dl_two_tracks(m, ts):
    m.dirs.add('/mnt/mmc/.m1plus/subsonic')
    lines = ['M1PLUS-DL 1']
    for t in ts:
        name = SD.name_of(t)
        m.put(f'{SD.MUSIC}/{name}', b'abc')
        lines.append('\t'.join(f'{k}={v}' for k, v in (('i', t['id']), ('t', t['title']), ('a', t['artist']), ('b', t['album']), ('p', name), ('w', 3), ('x', t['suffix']), ('c', t['cover']), ('n', t['album_id']),
                                                              ('l', t['seconds']), ('k', t['track']), ('d', t['disc']), ('y', t['year']), ('s', t['size']), ('r', t['bitrate']), ('h', t['sample_rate']), ('q', t['bit_depth']),
                                                              ('e', t['created']), ('f', t['starred']))))
    m.put(SD.IDX, ('\n'.join(lines) + '\n').encode())


def extras(ctx):
    expect = ctx.expect
    m = machine()
    items = [trk(1, starred=1), trk(2, suffix='dsf', album_id='zz'), trk(3, cover='', album_id='zz')]   # (r2 and r3: an album that is not in albums.idx, so their own cover ids count)
    h = play_setup(m, items)
    r1, r2, r3 = (m.deques[h][i] for i in range(3))
    # seconds
    expect([call(m, F_SECONDS, LIB, r) for r in (r1, r2)] == [101, 102] and call(m, F_SECONDS, LIB, 0) == 0, 'seconds: the track\'s length from the record')
    ah = listing(m, LS_ALBUMS)[0]
    expect(call(m, F_SECONDS, LIB, deque_row(m, ah, 0)) == 600, 'seconds of an album row: the album\'s')
    # gen
    g0 = call(m, F_GEN, LIB)
    expect(g0 == (SA.call(m, 'sba_gen') + m.call(PSYMS['sba_dl_gen'], count=100000)) & 0xffffffff, 'gen is sba_gen + sba_dl_gen')
    m.curl_site = quiet_site(getAlbum={'body': SA.ok_json(album={'id': 'al1', 'song': [{'id': 't1', 'title': 'A'}]})})
    SA.run_one(m, 'sba_fetch_album', 'al1')
    g1 = call(m, F_GEN, LIB)
    expect(g1 != g0, 'gen moves when a request finishes')
    m2 = machine(site=SD.server(machine()))
    guard_ok(m2)
    g0 = call(m2, F_GEN, LIB)
    r, th = SD.add(m2, SD.track('d9', 'Nine'))
    expect(r == 0 and call(m2, F_GEN, LIB) != g0, 'and when a download is queued')
    # cover
    path = f'{SA.COVERS}/{SA.fnv("cv-al1"):08x}-168.jpg'
    m.put(path, SA.JPEG)
    buf = m.alloc(256)
    expect(call(m, F_COVER, LIB, r1, 0, buf, 256) == 1 and m.read_cstr(buf) == path, f'cover: a track shows its album\'s file (cv-al1, not its own cv-t1) -> 1 and its path ({m.read_cstr(buf)})')
    m.put(f'{SA.COVERS}/{SA.fnv("cv-t2"):08x}-168.jpg', b'')
    expect(call(m, F_COVER, LIB, r2, 0, buf, 256) == -1, 'an empty marker file (the server has no art): -1')
    expect(call(m, F_COVER, LIB, r3, 0, buf, 256) == -1, 'a track with no cover id (and an album that is not known): -1')
    m.fs.pop(path)
    expect(call(m, F_COVER, LIB, r1, 0, buf, 256) == 0 and SA.state(m, SA.K['COVER'], 'cv-al1')[0] == SA.ST['LOAD'] and SA.state(m, SA.K['COVER'], 'cv-t1')[0] == SA.ST['NONE'], 'a cover not on the card: 0 and the ALBUM\'s cover is queued, not the track\'s own')
    SA.drain(m, m.thread)
    expect(call(m, F_COVER, LIB, r1, 0, buf, 256) == -1, 'the request failed (the scripted server has no picture): -1, not asked again')
    m.wifi = -1
    arow = deque_row(m, ah, 0)
    expect(call(m, F_COVER, LIB, arow, 0, buf, 256) == -1, 'Wi-Fi off and no file: -1 (nothing to poll for)')
    m.wifi = 4
    # an artist row: its own picture (getArtists' coverArt id, an ar- id), the file by that id, never an album's
    seed(m, 'artists.idx', 'artist', [dict(id='r1', name='With Picture', cover='ar-r1', albums=2), dict(id='r2', name='No Id', cover='', albums=1), dict(id='r3', name='No Art', cover='ar-r3', albums=1), dict(id='r4', name='Not Yet', cover='ar-r4', albums=1)])
    ah2, ars, _ = listing(m, LS_ARTISTS)
    apath = f'{SA.COVERS}/{SA.fnv("ar-r1"):08x}-168.jpg'
    m.put(apath, SA.JPEG)
    m.put(f'{SA.COVERS}/{SA.fnv("ar-r3"):08x}-168.jpg', b'')
    ar_ = [deque_row(m, ah2, i) for i in range(4)]
    expect(call(m, F_COVER, LIB, ar_[0], 0, buf, 256) == 1 and m.read_cstr(buf) == apath, 'an artist with a picture file: 1 and the path')
    expect(call(m, F_COVER, LIB, ar_[1], 0, buf, 256) == -1 and call(m, F_COVER, LIB, ar_[2], 0, buf, 256) == -1, 'an artist with no coverArt id, or whose file is the empty marker: -1 (the placeholder)')
    expect(call(m, F_COVER, LIB, ar_[3], 0, buf, 256) == 0 and SA.state(m, SA.K['COVER'], 'ar-r4')[0] == SA.ST['LOAD'], 'an artist whose picture is not on the card: 0 and that picture is queued')
    # row extras
    out = m.alloc(20)

    def rowx(r):
        call(m, F_ROW, LIB, r, out)
        return tuple(S32(m.word(out + 4 * i)) for i in range(5))   # dl, pct, dsd, fav, offline
    expect(rowx(r1) == (0, 0, 0, 1, 0) and rowx(r2) == (0, 0, 1, 0, 0), f'row: favourite and DSD flags ({rowx(r1)} {rowx(r2)})')
    m.wifi = -1
    expect(rowx(r1)[4] == 1, 'row: not downloaded and no Wi-Fi: offline')
    m.wifi = 4
    expect(rowx(deque_row(m, ah, 0)) == (0, 0, 0, 0, 0), 'row: an album row has no extras')
    # downloaded / waiting / active
    m = machine()
    dl_two_tracks(m, [SD.track('t1', 'Song 1', 'flac')])
    h = play_setup(m, [trk(1), trk(2)])
    r1, r2 = m.deques[h][0], m.deques[h][1]
    m.wifi = -1
    expect(rowx(r1) == (3, 0, 0, 0, 0), f'row: a downloaded track is DONE and not offline even without Wi-Fi ({rowx(r1)})')
    m.wifi = 4
    m.curl_site = SD.server(m)
    guard_ok(m)
    r, th = SD.add(m, SD.track('t2', 'Song 2'))
    expect(r == 0 and rowx(r2)[0] == 1, 'row: a queued download is WAIT')
    seen = []
    base = m.curl_site
    m.curl_site = lambda url, o: dict(base(url, o), xfer=lambda u, s, tt: seen.append(rowx_nested(m, r2)))
    SD.work(m, th)
    pcts = [x for x in seen if x[0] == 2]
    vals = [p[1] for p in pcts if p[1] >= 0]
    expect(pcts and pcts[0][1] in (-1, 0) and vals == sorted(vals) and vals[-1] >= 90 and vals[-1] <= 100, f'row: an active download is ACTIVE; the percent is -1 until the size is known, then grows to the end ({vals[::max(1, len(vals) // 8)]})')
    expect(rowx(r2)[0] == 3, 'and DONE after')
    # actions
    m = machine(site=quiet_site(star={'body': SA.ok_json()}, unstar={'body': SA.ok_json()}))
    h = play_setup(m, [trk(1), trk(2, starred=1)])
    SA.seed(m, f'{ND}/starred.idx', 'track', [dict(id='t2', starred=1)])   # (Favorites is the truth for a heart: the starred track is in it)
    r1, r2 = m.deques[h][0], m.deques[h][1]
    m.thread = None
    expect(call(m, F_ACT, LIB, r1, ACT_FAVORITE) == 0 and m.thread is not None, 'Favorite on a track: sba_star asked, 0')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'star' and m.curl_site.query()['id'] == 't1', 'star.view for the track')
    expect(any(r[0] == 't1' for r in SA.read_rows(m, f'{ND}/starred.idx', 'track')), 'the starred list gained the track')
    m.thread = None
    expect(call(m, F_ACT, LIB, r2, ACT_UNFAVORITE) == 0, 'Undo Favorite on a favourite track unstars')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'unstar', 'unstar.view')
    # the wish travels with the action: a stale cache row (starred on the server by another client, the album file still says 0) must not flip it
    m.thread = None
    expect(call(m, F_ACT, LIB, r1, ACT_UNFAVORITE) == 0, 'Undo Favorite on a row the cache holds unstarred')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'unstar' and m.curl_site.query()['id'] == 't1', 'sends unstar, not a toggle of the cached flag')
    m.thread = None
    expect(call(m, F_ACT, LIB, r2, ACT_FAVORITE) == 0, 'Favorite on a row the cache holds starred')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'star' and m.curl_site.query()['id'] == 't2', 'sends star, not a toggle of the cached flag')
    m.wifi = -1
    expect(call(m, F_ACT, LIB, r1, ACT_FAVORITE) == SA.R['NOWIFI'] and any(c[0] == 'toast' and c[1] == 'Connect to Wi-Fi first' for c in m.calls), 'Wi-Fi off: the reason is shown and returned')
    m.wifi = 4
    guard_ok(m)
    m.curl_site = SD.server(m)
    m.thread = None
    expect(call(m, F_ACT, LIB, r1, ACT_DOWNLOAD) == 0 and m.thread is not None, 'Download: the track is queued')
    SD.work(m, m.thread)
    expect(SD.state(m, 't1')[0] == SD.DL['DONE'], 'and downloaded')
    rows_ = SD.listing(m)
    expect(rows_ and rows_[0]['id'] == 't1' and rows_[0]['size'] == 5001 and rows_[0]['bitrate'] == 900, f'the manifest has the whole row, the sizes from the cached album file ({rows_})')
    expect(call(m, F_ACT, LIB, r1, ACT_DELETE) == 0 and SD.state(m, 't1')[0] == SD.DL['NONE'], 'Delete download: the file and the manifest row go')
    expect(call(m, F_ACT, LIB, r1, 99) == -1 and call(m, F_ACT, LIB, 0, ACT_DOWNLOAD) == -1, 'an unknown action or no record: -1')


def rowx_nested(m, r):
    out = m.alloc(20)
    m.nested(member(m, F_ROW), LIB, r, out)
    return tuple(S32(m.word(out + 4 * i)) for i in range(5))


def guard_ok(m):
    SD.guard(m, 0)


F_QUEUE_ROW = 44   # lib_src_t.queue_row, the last member
ACT_CANCEL_DL = 4


def sheet(ctx):
    """The row sheet's source side (ND-14): queue_row (the stream address or the local file as a queue record whose id the queue map knows, nothing for an offline or DSD row), the map growing past a
    play's 64, Cancel Download through act, the DSD confirm (text, Download, Cancel, a long title) and the random Shuffle start that skips an undownloaded DSD row."""
    expect = ctx.expect
    m = machine()
    h = play_setup(m, [trk(1), trk(2, suffix='dsf', size=182_400_000), trk(3)])
    r1, r2, r3 = (m.deques[h][i] for i in range(3))

    def queue_row(r):
        m.calls = []
        q = call(m, F_QUEUE_ROW, LIB, r) & 0xffffffff
        return q, rows(m, q) if q else []
    q, rs = queue_row(r1)
    x = rs[0] if rs else {}
    expect(len(rs) == 1 and x['path'].startswith('http://nd.example:4533/rest/stream.view?') and 'id=t1' in x['path'] and 'format=raw' in x['path'] and 'secret' not in x['path']
           and (x['name'], x['title'], x['album'], x['artist'], x['track'], x['type'], x['cls']) == ('Song 1.flac', 'Song 1', 'An Album', 'An Artist', 1, 8, 0), f'queue_row: the stream address (raw) and the texts of the row: {x}')
    expect(x['id'] <= -2 and m.read_cstr(m.call(PSYMS['sba_rec_track'], a0=x['id'] & 0xffffffff, count=2000000)) == 't1' and not any(c[0] == 'toast' for c in m.calls),
           f'its REC_ID is the map\'s synthetic id (the playing marker and Now Playing\'s cover find the track): {x.get("id")}')
    q2, rs2 = queue_row(r1)
    expect(rs2 and rs2[0]['id'] == x['id'], 'the same track queued again keeps its id')
    # the map grows past a play's 64 and keeps the play's ids
    m2 = machine()
    items = [trk(i) for i in range(1, 91)]
    h2 = play_setup(m2, items)
    r, q = playit(m2, h2, 0)
    before = [S32(m2.word(r_ + REC_ID)) for r_ in m2.played[0]]
    ids = []
    for i in range(64, 90):
        qh = call(m2, F_QUEUE_ROW, LIB, m2.deques[h2][i]) & 0xffffffff
        ids.append(S32(m2.word(m2.deques[qh][0] + REC_ID)) if qh else None)
    ok = all(i is not None for i in ids) and len(set(ids + before)) == 64 + 26
    expect(ok and all(m2.read_cstr(m2.call(PSYMS['sba_rec_track'], a0=i & 0xffffffff, count=2000000)) == f't{k + 65}' for k, i in enumerate(ids))
           and m2.read_cstr(m2.call(PSYMS['sba_rec_track'], a0=before[5] & 0xffffffff, count=2000000)) == 't6', 'Play Next / After add to the map past the 64 of a play: every id resolves, the play\'s too, no two alike')
    # DSD and offline
    q, rs = queue_row(r2)
    expect(q == 0 and any(c[0] == 'toast' and c[1] == 'Connect to Wi-Fi first' for c in m.calls), 'an undownloaded DSD row cannot be queued (the page asks to download first): nothing, the toast')
    m.wifi = -1
    q, rs = queue_row(r1)
    expect(q == 0 and [c[1] for c in m.calls if c[0] == 'toast'] == ['Connect to Wi-Fi first'], 'offline and not downloaded: nothing queued, "Connect to Wi-Fi first"')
    # a downloaded track queues its local file, offline too, DSD included
    m = machine()
    ts = [SD.track('d1', 'One', 'flac'), SD.track('d2', 'Dsd Two', 'dsf')]
    dl_two_tracks(m, ts)
    h = play_setup(m, [trk(1, id='d1', title='One', suffix='flac'), trk(2, id='d2', title='Dsd Two', suffix='dsf')])
    m.wifi = -1
    for k in (0, 1):
        q, rs = queue_row(m.deques[h][k])
        f = f'{SD.MUSIC}/{SD.name_of(ts[k])}'
        expect(rs and rs[0]['path'] == f and rs[0]['name'] == SD.name_of(ts[k]) and not any(c[0] == 'toast' for c in m.calls), f'a downloaded track queues its local file even offline ({rs and rs[0]["path"]})')
    # Cancel Download: a waiting download leaves the queue
    m = machine()
    h = play_setup(m, [trk(1), trk(2)])
    r1 = m.deques[h][0]
    guard_ok(m)
    m.curl_site = SD.server(m)
    m.thread = None
    expect(call(m, F_ACT, LIB, r1, ACT_DOWNLOAD) == 0 and SD.state(m, 't1')[0] == SD.DL['WAIT'], 'Download queues the track (waiting)')
    expect(call(m, F_ACT, LIB, r1, ACT_CANCEL_DL) == 0 and SD.state(m, 't1')[0] == SD.DL['NONE'], 'Cancel Download takes a waiting track out of the queue')
    expect(call(m, F_ACT, LIB, 0, ACT_CANCEL_DL) == -1, 'Cancel Download without a record: -1')
    # the DSD confirm
    DSD = lambda m_, h_, at: S32(m_.call(PSYMS['ls_dsd_confirm'], a0=LIB, a1=h_, a2=at & 0xffffffff, count=1 << 30))
    m = machine()
    h = play_setup(m, [trk(1), trk(2, suffix='dsf', size=182_400_000), trk(3, suffix='dsf', title='T' * 90, size=0)])
    guard_ok(m)
    m.curl_site = SD.server(m)
    m.confirm_yes = False
    m.calls = []
    ret = DSD(m, h, 1)
    ask = list(c for c in m.calls if c[0] == 'confirm')
    timers = [c for c in m.calls if c[0] == 'timer_add']
    expect(ret == 0 and not SD.state(m, 't2')[0], 'Cancel: nothing is downloaded')
    expect(len(ask) == 1 and ask[0][1] == 'Download to Play?\nDSD tracks play from the card. Song 2, 182 MB.' and ask[0][2] == O['CONFIRM_KIND_WRAP'], f'the text: the title, the track and its size in MB ({[a[1:] for a in ask]})')
    expect(any(c[2] == 10 for c in timers), f'the buttons are relabelled by a timer ({timers})')
    m.confirm_yes = True
    m.thread = None
    expect(DSD(m, h, 1) == 1 and SD.state(m, 't2')[0] == SD.DL['WAIT'], 'Download: the file is queued through the source (waiting)')
    m.calls = []
    m.confirm_yes = False
    DSD(m, h, 2)
    ask = [c for c in m.calls if c[0] == 'confirm']
    expect(len(ask) == 1 and '...' in ask[0][1] and len(ask[0][1]) < 120 and ', ? MB.' in ask[0][1], f'a long title is cut with an ellipsis, an unknown size is "?" ({ask[0][1]!r})')
    m.calls = []
    expect(DSD(m, h, 7) == 0 and DSD(m, 0, 0) == 0 and not [c for c in m.calls if c[0] == 'confirm'], 'a row outside the list or no list: 0 and no dialog')
    # a random Shuffle start never lands on an undownloaded DSD file while something else can play; when nothing can, -2 and the confirm asks for the row that was picked
    m = machine()
    h = play_setup(m, [trk(1, suffix='dsf'), trk(2), trk(3, suffix='dsf'), trk(4)])
    starts = set()
    for seed_ in range(8):
        m.seed = seed_
        r, q = playit(m, h, -1)
        starts.add(q[0]['title'] if r == 0 and q else r)
    expect(starts <= {'Song 2', 'Song 4'} and starts, f'a random start skips the DSD rows ({starts})')
    m = machine()
    h = play_setup(m, [trk(1, suffix='dsf'), trk(2, suffix='flac', id='t2')])
    m.wifi = -1
    m.seed = 1
    r, q = playit(m, h, -1)
    expect(r == -1 and not q, 'offline with nothing downloaded: a random start is refused (-1)')
    m = machine()
    h = play_setup(m, [trk(1, suffix='dsf'), trk(2, suffix='dsf')])
    m.seed = 1
    r, q = playit(m, h, -1)
    m.confirm_yes = False
    m.calls = []
    DSD(m, h, -1)
    ask = [c for c in m.calls if c[0] == 'confirm']
    expect(r == -2 and len(ask) == 1 and 'Song 2' in ask[0][1], f'only DSD rows: Shuffle answers -2 and the confirm is for the row it picked ({r}, {[a[1] for a in ask]})')


def awake(ctx):
    """Keep awake: reset_poweroptions_timer(1, 1, 0) from the keep-awake tick only while a Navidrome stream is playing (status 2)."""
    expect = ctx.expect
    m = machine()
    h = play_setup(m, [trk(i) for i in range(1, 4)])
    m.calls = []
    r, q = playit(m, h, 0)
    expect(r == 0 and sum(1 for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['nl_awake_tick']) == 1, 'a play arms the keep-awake timer once')
    m.calls = []
    playit(m, h, 1)
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque(m.played[0]))
    m.play_pos = 0
    tick = lambda: (m.call(PSYMS['nl_awake_tick'], a0=0, count=2000000), len([c for c in m.calls if c[0] == 'reset_poweroptions_timer']))
    m.clock += 60000
    m.calls = []
    m.status = 2
    r, n = tick()
    expect(r == O['RET_REPEAT'] and [c for c in m.calls if c[0] == 'reset_poweroptions_timer'] == [('reset_poweroptions_timer', 1, 1, 0)], f'a stream playing: reset_poweroptions_timer(1, 1, 0) and the timer goes on ({r})')
    m.calls = []
    m.status = 3
    r, n = tick()
    expect(r == O['RET_REPEAT'] and n == 0, 'paused: no call, the timer stays')
    m.status = 1
    r, n = tick()
    expect(r == 0 and n == 0, 'stopped after the grace: no call, the timer ends')
    # a download running keeps the device awake too, and a queued download arms the timer
    m = machine()
    h = play_setup(m, [trk(1)])
    SD.guard(m, 0)
    m.curl_site = SD.server(m)
    m.calls = []
    m.thread = None
    r = call(m, F_ACT, LIB, deque_row(m, h, 0), ACT_DOWNLOAD)
    expect(r == 0 and sum(1 for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['nl_awake_tick']) == 1, 'a queued download arms the keep-awake timer')
    m.status = 1
    m.play_pos = -1
    m.clock += 60000
    m.calls = []
    r, n = tick()
    expect(r == O['RET_REPEAT'] and [c for c in m.calls if c[0] == 'reset_poweroptions_timer'] == [('reset_poweroptions_timer', 1, 1, 0)], f'a download running, nothing playing: the call is made and the timer goes on ({r})')
    SD.work(m, m.thread)
    m.calls = []
    r, n = tick()
    expect(r == 0 and n == 0, 'the download finished and nothing plays: no call, the timer ends')
    # a downloaded (local) track playing: no call
    m = machine()
    ts = [SD.track('d1', 'One', 'flac')]
    dl_two_tracks(m, ts)
    h = play_setup(m, [trk(1, id='d1', title='One', suffix='flac'), trk(2)])
    playit(m, h, 0)
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque(m.played[0]))
    m.play_pos = 0; m.status = 2; m.clock += 60000; m.calls = []
    r, n = tick()
    expect(r == O['RET_REPEAT'] and n == 0, 'a downloaded file playing: no call (the queue is ours, the timer stays for the next track)')
    m.play_pos = 1; m.calls = []
    r, n = tick()
    expect(r == O['RET_REPEAT'] and n == 1, 'the next track streams: one call')
    # another source's track playing: no call, the timer ends
    stock = m.alloc(0x58)
    m.setword(stock + REC_ID, 5); m.setword(stock + REC_PATH, m.cstr('/mnt/mmc/x.flac'))
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque([stock]))
    m.play_pos = 0; m.calls = []
    r, n = tick()
    expect(r == 0 and n == 0, 'a stock track playing: no call, the timer ends')


def messages(ctx):
    """sbs_message: one short line for each failure; a download that failed is toasted once, by the page's gen read; a refused request names its cause."""
    expect = ctx.expect
    m = machine()
    msg = lambda code, status=0: m.read_cstr(m.call(PSYMS['sbs_message'], a0=code, a1=status, count=2000000))
    R = SA.R
    want = {'NOCONF': 'Add a server first', 'NOWIFI': 'Connect to Wi-Fi first', 'NOCLOCK': 'Set the date and time first', 'CERT': 'Server certificate not trusted', 'NOCERT': 'Server certificate not trusted',
            'AUTH': 'Incorrect username or password', 'NOTFOUND': 'Song not found on the server', 'NOTAUDIO': 'Unexpected server response', 'STORAGE': 'Storage unavailable',
            'CARDFULL': 'Card is full', 'WRITE': 'Write failed', 'QFULL': 'Queue is full', 'MEM': 'Not enough memory', 'NET': 'Download interrupted', 'PARSE': "Can't connect to the server"}
    bad = {k: msg(R[k]) for k, v in want.items() if msg(R[k]) != v}
    expect(not bad, f'every failure code has its own words ({bad})')
    req = lambda code, status=0: m.read_cstr(m.call(PSYMS['sbs_request_message'], a0=code, a1=status, count=2000000))
    expect(req(R['NET']) == "Can't connect to the server" and req(R['HTTP'], 503) == 'Server error 503' and req(R['NOWIFI']) == 'Connect to Wi-Fi first', 'a request\'s SBA_NET is "Can\'t connect to the server"; the other codes read as for a download')
    expect(msg(R['HTTP'], 503) == 'Server error 503' and msg(R['HTTP'], 0) == 'Server error', 'an HTTP error shows its status when there is one')
    # a download that failed is toasted once by the next gen read, as the cause says
    t = SD.track('f1', 'Failing')
    SD.guard(m, 0)
    m.curl_site = lambda url, o: (SD.reply_head(m, o, 503), dict(rc=22, code=503, body=b'', length=0))[1]
    r, th = SD.add(m, t); SD.work(m, th)
    m.calls = []
    call(m, F_GEN, LIB)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Server error 503'], f'the failed download is told on the page: {[c[1] for c in m.calls if c[0] == "toast"]}')
    m.calls = []
    call(m, F_GEN, LIB)
    expect(not [c for c in m.calls if c[0] == 'toast'], 'and only once')
    # a refused download request says why
    m = machine(); SD.guard(m, 0)
    h = play_setup(m, [trk(1)])
    m.free_mb = 20
    m.calls = []
    r = call(m, F_ACT, LIB, deque_row(m, h, 0), ACT_DOWNLOAD)
    expect(r == R['CARDFULL'] and [c[1] for c in m.calls if c[0] == 'toast'] == ['Card is full'], 'a card with no room: "Card is full" (not "Storage unavailable")')
    m = machine(); SD.guard(m, 0)
    h = play_setup(m, [trk(i) for i in range(1, 36)])
    m.thread = None
    rs = [call(m, F_ACT, LIB, deque_row(m, h, i), ACT_DOWNLOAD) for i in range(34)]
    q = [c[1] for c in m.calls if c[0] == 'toast']
    expect(R['QFULL'] in rs and q and set(q) == {'Download queue is full'}, f'a full download queue says "Download queue is full" ({set(q)})')
    m = machine(); SD.guard(m, 0)
    h = play_setup(m, [trk(1)])
    m.card_mounted = False
    m.calls = []
    r = call(m, F_ACT, LIB, deque_row(m, h, 0), ACT_DOWNLOAD)
    expect(r == R['STORAGE'] and [c[1] for c in m.calls if c[0] == 'toast'] == ['Storage unavailable'], 'no card: "Storage unavailable"')


def queue_star(ctx):
    """A queue record (what the player holds, Now Playing's star) is a track of the source too: row reads its favourite flag from the cache, act toggles the server favourite
    (sbs_track through the queue map), for a streamed and a downloaded record alike; the queue map keeps the album id and the suffix for it."""
    expect = ctx.expect
    m = machine(site=quiet_site(star={'body': SA.ok_json()}, unstar={'body': SA.ok_json()}))
    h = play_setup(m, [trk(1), trk(2, starred=1), trk(3, id='t3', album_id='')])
    SA.seed(m, f'{ND}/starred.idx', 'track', [dict(id='t2', starred=1)])
    r, q = playit(m, h, 0)
    q1, q2, q3 = m.played[0]
    out = m.alloc(20)

    def rowq(r_):
        call(m, F_ROW, LIB, r_, out)
        return tuple(S32(m.word(out + 4 * i)) for i in range(5))
    expect(r == 0 and rowq(q1)[3] == 0 and rowq(q2)[3] == 1, f'row on a queue record: the favourite flag is the cache\'s ({rowq(q1)} {rowq(q2)})')
    expect(rowq(q1)[2] == 0 and rowq(q1)[0] == 0, 'row on a queue record: the suffix and the download state are the map\'s and the manifest\'s')
    m.thread = None
    expect(call(m, F_ACT, LIB, q1, ACT_FAVORITE) == 0 and m.thread is not None, 'Favorite on a queue record: sba_star asked, 0')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'star' and m.curl_site.query()['id'] == 't1' and rowq(q1)[3] == 1, 'star.view for the record\'s track, and the record reads starred now')
    m.thread = None
    expect(call(m, F_ACT, LIB, q2, ACT_UNFAVORITE) == 0, 'Undo Favorite on a starred queue record unstars')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'unstar' and m.curl_site.query()['id'] == 't2' and rowq(q2)[3] == 0, 'unstar.view, and the record reads unstarred')
    expect(not any(q_['path'].startswith('nd://') for q_ in queue_of(m)), 'the queue records keep their stream addresses (the source never rewrites them)')
    # a track listed without an album: the Favorites list says whether it is starred
    seed(m, 'starred.idx', 'track', [trk(3, id='t3', album_id='', starred=1)])
    expect(rowq(q3)[3] == 1, 'a queue record with no album row: starred when the Favorites list has it')
    # a record that is not the source's
    local = m.alloc(0x60)
    m.u.mem_write(local, bytes(0x60))
    m.setword(local + REC_TYPE, 8)
    m.setword(local + REC_ID, 7)
    expect(rowq(local) == (0, 0, 0, 0, 0) and call(m, F_ACT, LIB, local, ACT_FAVORITE) == -1, 'a local record: no extras, and Favorite is not ours (-1)')
    # a downloaded track plays its local file; its record is the source's track all the same
    m = machine(site=quiet_site(star={'body': SA.ok_json()}, unstar={'body': SA.ok_json()}))
    dl_two_tracks(m, [SD.track('d1', 'One', 'flac')])
    h = play_setup(m, [trk(1, id='d1', title='One', suffix='flac', starred=1)])
    r, q = playit(m, h, 0)
    d1 = m.played[0][0]
    out = m.alloc(20)
    expect(q[0]['path'].startswith(SD.MUSIC) and rowq(d1)[0] == 3 and rowq(d1)[3] == 1, f'a downloaded queue record: DONE, and its favourite flag is the cache\'s ({rowq(d1)})')
    m.thread = None
    expect(call(m, F_ACT, LIB, d1, ACT_UNFAVORITE) == 0 and m.curl_site.views() is not None, 'Undo Favorite on the downloaded record is the server\'s too')
    SA.drain(m, m.thread)
    expect(m.curl_site.views()[-1] == 'unstar' and m.curl_site.query()['id'] == 'd1', 'unstar.view for the downloaded track')


def trackcover(ctx):
    """A server track shows its ALBUM's cover file (the one the Background fill fetched), docs/modules/subsonic.md "Caching": Navidrome gives a song with embedded art its own coverArt id ("mf-..."),
    which must not cost one more file per song. Song rows (cover), the play queue (sba_rec_cover: Now Playing, Queue, mini bar, vinyl, bigcover), Get Info and a playlist's mosaic."""
    expect = ctx.expect
    site = quiet_site(getCoverArt={'body': SA.JPEG})
    m = machine(site=site)
    m.wifi = 4
    mf = lambda i: f'mf-t{i}_66aa'
    items = [trk(1, cover=mf(1)), trk(2, cover=mf(2)), trk(3, cover=mf(3)), trk(4, cover=mf(4), album_id='zz'), trk(5, cover=mf(5), album_id=''), trk(6, cover=mf(6), album_id='al3'), trk(7, cover='', album_id='zz')]
    seed(m, 'al/al1.idx', 'track', items)
    ah = albums_rows(m, [alb(1, cover='al-al1_5f'), alb(2, cover='al-al2_5f'), alb(3, cover='')])
    h = listing(m, LS_SONGS, deque_row(m, ah, 0))[0]
    r = [m.deques[h][i] for i in range(len(items))]
    buf = m.alloc(256)
    file = lambda cover: f'{SA.COVERS}/{SA.fnv(cover):08x}-168.jpg'
    asked = lambda: [site.query(i)['id'] for i, v in enumerate(site.views()) if v == 'getCoverArt']

    def cover(rec): return call(m, F_COVER, LIB, rec, 0, buf, 256)

    def rec_cover(rec): return SA.call(m, 'sba_rec_cover', rec, buf, 256)
    # nothing cached: a song row asks for its album's cover and only that, whatever its own id
    m.thread = None
    expect(cover(r[0]) == 0 and m.thread, 'a song row whose album cover is not cached: 0, asked for')
    SA.drain(m, m.thread)
    expect(asked() == ['al-al1_5f'] and SA.state(m, SA.K['COVER'], mf(1))[0] == SA.ST['NONE'], f'the request is the ALBUM\'s cover id, not the song\'s own mf- id ({asked()})')
    # the album's file is there (the Background fill): every song of the album answers 1 with it, no further request
    n0 = len(site.urls)
    got = [(cover(x), m.read_cstr(buf)) for x in (r[0], r[1], r[2])]
    expect(got == [(1, file('al-al1_5f'))] * 3 and len(site.urls) == n0, f'songs 1..3 (own covers {mf(1)}..{mf(3)}) all answer the album\'s file and nothing is requested ({got})')
    # the play queue: Now Playing, the Queue page, the mini bar, vinyl and the big cover page all read sba_rec_cover on the queue record
    q = playit(m, h, 0)[1]
    recs = m.played[0]
    got = [(rec_cover(x), m.read_cstr(buf)) for x in recs[:3]]
    expect(len(q) >= 3 and got == [(1, file('al-al1_5f'))] * 3 and len(site.urls) == n0, f'queue records of the album: 1 with the album\'s file, no request ({got})')
    expect(m.read_cstr(m.call(PSYMS['sba_now_cover'], a0=recs[1], count=2000000)) == file('al-al1_5f'), 'Now Playing (sba_now_cover) shows the album\'s file too')
    # an unknown album, no album id, an album with no coverArt: the song's own cover
    m.thread = None
    expect(cover(r[3]) == 0 and SA.state(m, SA.K['COVER'], mf(4))[0] == SA.ST['LOAD'], 'a song of an album that is not in albums.idx: its own cover is asked for')
    SA.drain(m, m.thread)
    m.thread = None
    expect(cover(r[4]) == 0 and SA.state(m, SA.K['COVER'], mf(5))[0] == SA.ST['LOAD'] and cover(r[6]) == -1, 'no album id: its own cover; an unknown album and no cover id at all: -1')
    SA.drain(m, m.thread)
    m.thread = None
    expect(rec_cover(recs[5]) == 0 and SA.state(m, SA.K['COVER'], mf(6))[0] == SA.ST['LOAD'], 'an album with no coverArt: the song\'s own cover (the queue record too)')
    SA.drain(m, m.thread)
    # an album the server has no picture for: -1 for its songs, and their own covers are not tried
    m.put(file('al-al2_5f'), b'')
    seed(m, 'al/al2.idx', 'track', [trk(8, cover=mf(8), album_id='al2')])
    h2 = listing(m, LS_SONGS, deque_row(m, ah, 1))[0]
    n1 = len(site.urls)
    expect(cover(m.deques[h2][0]) == -1 and len(site.urls) == n1 and SA.state(m, SA.K['COVER'], mf(8))[0] == SA.ST['NONE'], 'an album with an empty marker (no art): -1, no request for the song\'s id')
    # Get Info reads the album's file and never asks
    t = SA.call(m, 'sba_track_cover', 'al1', mf(1), buf, 256, 0)
    expect(t == 1 and m.read_cstr(buf) == file('al-al1_5f'), 'sba_track_cover without ask (Get Info): the album\'s file')
    # a playlist's mosaic: the songs of one album make one quadrant, not one per song
    key = m.alloc(16)
    n = m.call(PSYMS['sbs_mosaic_keys'], a0=LIB, a1=h, a2=key, a3=0, count=1 << 30)
    expect(n == 1 and m.word(key) == SA.fnv('al-al1_5f'), f'a playlist of songs of one album: one mosaic file, the album\'s ({n}, {m.word(key):08x})')


def dlalbum(ctx):
    """Download Album (LS_ACT_DOWNLOAD_ALL, rec = the page's list): the tracks not on the card and not queued are queued in list order with one toast; the four outcomes."""
    expect = ctx.expect
    R = SA.R
    toasts = lambda m: [c[1] for c in m.calls if c[0] == 'toast']
    def setup(items, on_card=()):
        m = machine(); guard_ok(m)
        if on_card: dl_two_tracks(m, [SD.track(i, i, 'flac') for i in on_card])
        h = play_setup(m, items)
        m.curl_site = SD.server(m)
        return m, h
    # a mixed album: d1 on the card, t3 already waiting, a DSD track included
    m, h = setup([trk(1, id='d1', title='d1', suffix='flac'), trk(2), trk(3), trk(4), trk(5, suffix='dsf')], on_card=('d1',))
    m.thread = None
    expect(call(m, F_ACT, LIB, deque_row(m, h, 2), ACT_DOWNLOAD) == 0, 'a track queued on its own first')
    th = m.thread
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    expect(r == 0 and toasts(m) == ['Downloading 3 songs'], f'three tracks queued (the card one and the queued one skipped, the DSD one included): one toast ({r}, {toasts(m)})')
    expect([SD.state(m, i)[0] for i in ('d1', 't2', 't3', 't4', 't5')] == [SD.DL['DONE'], SD.DL['WAIT'], SD.DL['WAIT'], SD.DL['WAIT'], SD.DL['WAIT']], 'all but the card one wait')
    reqs = [c[1] for c in SD.work(m, th) if c[0] == 'curl_perform']
    ids = [u.split('id=')[1].split('&')[0] for u in reqs]
    expect(ids == ['t3', 't2', 't4', 't5'], f'in list order after the one already waiting ({ids})')
    # one new track: the singular toast and the keep-awake timer
    m, h = setup([trk(1), trk(2, id='d1', title='d1', suffix='flac')], on_card=('d1',))
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    expect(r == 0 and toasts(m) == ['Downloading 1 song'] and sum(1 for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['nl_awake_tick']) == 1, f'one track: "Downloading 1 song", the keep-awake timer armed once ({toasts(m)})')
    # nothing to do
    m, h = setup([trk(1, id='d1', title='d1', suffix='flac'), trk(2)], on_card=('d1',))
    call(m, F_ACT, LIB, deque_row(m, h, 1), ACT_DOWNLOAD)
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    expect(r == 0 and toasts(m) == ['Already downloaded'] and not any(c[0] == 'timer_add' for c in m.calls), f'all on the card or queued: "Already downloaded" ({toasts(m)})')
    # a guard refuses the first
    m, h = setup([trk(1), trk(2)])
    SD.guard(m, R['NOWIFI'])
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    expect(r == R['NOWIFI'] and toasts(m) == ['Connect to Wi-Fi first'] and SD.state(m, 't1')[0] == SD.DL['NONE'] and SD.state(m, 't2')[0] == SD.DL['NONE'], f'no Wi-Fi: its message, nothing queued ({toasts(m)})')
    m, h = setup([trk(1)])
    m.card_mounted = False
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    expect(r == R['STORAGE'] and toasts(m) == ['Storage unavailable'], f'no card: its message ({toasts(m)})')
    # the queue fills
    m, h = setup([trk(i) for i in range(1, 35)])
    m.calls = []
    r = call(m, F_ACT, LIB, h, ACT_DOWNLOAD_ALL)
    said = toasts(m)
    states = [SD.state(m, f't{i}')[0] for i in range(1, 35)]
    expect(r == R['QFULL'] and said == ['Downloading 32, queue full'] and states == [SD.DL['WAIT']] * 32 + [SD.DL['NONE']] * 2, f'a full queue: the 32 that fit wait, one toast "Downloading 32, queue full" ({r}, {said}, {states})')
    expect(call(m, F_ACT, LIB, 0, ACT_DOWNLOAD_ALL) == -1, 'no list: -1')


SECTIONS = [lists, songs, play, extras, trackcover, sheet, awake, messages, queue_star, dlalbum]


def run(ctx):
    for section in SECTIONS:
        section(ctx)

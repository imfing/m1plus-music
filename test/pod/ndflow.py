"""Navidrome pages against the public demo server's real responses (test/data/navidrome: getAlbum, getAlbumList2, getStarred2 and a search3 sample, fetched from demo.navidrome.org).
The pages run on the compiled payload under Unicorn with lib_nd (patch/sbsrc.c) and the data layer's worker (patch/sbapi.c) behind a scripted libcurl; the worker is run by the test (SA.drain).
Sections: artist_pl (the real getArtists / getPlaylists lists: an artist tapped on the Artists page, the artist's albums page, a playlist tapped, its Songs page; each with the queue empty and full of covers), album (the album page opened on an Albums row after the Albums page queued its covers: tracks, the header cover, and a request that failed, was refused by the full queue or by the Wi-Fi guard
is made again), gen (a cover does not move the list generation; a cover generation of its own does), songs (the Songs paging against a real server's response size), state (lib_nd's state for the whole-library lists)."""
import importlib.util, json, os, sys
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


SS = sibling('sbsrc')
AP = sibling('albumpage')
SA = SS.SA
SG = AP.SG
AL = sibling('albums')
AR = sibling('artists')
DATA = os.path.join(os.path.dirname(HERE), 'data', 'navidrome')
LS_ALBUMS, LS_SONGS = SS.LS_ALBUMS, SS.LS_SONGS
ALBUM_INDEX = 34   # "netBloc Vol. 42", 11 songs: its row in the album list fixture
COVER_ID = 'al-6dGMsiesuYw9lti9yGIGWY_ebbb154f246c04a5'
RESPONSE_MAX = 4 << 20   # SBN_RESPONSE_MAX
RED = (190, 50, 55)


def fixture(name):
    with open(os.path.join(DATA, name), 'rb') as f:
        return f.read()


def cover_file(cover=COVER_ID): return '%s/%08x-168.jpg' % (SA.COVERS, SA.fnv(cover))


class NAM(AP.AM, SS.SM):
    """The album page's machine (stock lists, widgets) with the Navidrome card machine of sbsrc (the stock deque copy, the scripted libcurl, the cache dir)."""


def demo_site(**routes):
    base = dict(getAlbumList2={'body': fixture('albumlist.json')}, getArtists={'body': SA.ok_json(artists={'index': []})}, getPlaylists={'body': SA.ok_json(playlists={})},
                getStarred2={'body': fixture('starred.json')}, getAlbum={'body': fixture('album.json')}, getCoverArt={'body': SA.JPEG})
    base.update(routes)
    site = SA.Site(**base)
    site.default = {'rc': 6}
    return site


class NSM(SG.SongsMachine, SS.SM):
    """The Songs page's machine with the Navidrome card machine of sbsrc."""


def songs_page_machine(site=None):
    """The Songs page's machine (the stock lists' widgets) with a saved server, the card, Wi-Fi and the demo site."""
    saved = SG.SongsMachine
    SG.SongsMachine = NSM
    try:
        m = SG.list_machine(['Stock'])
    finally:
        SG.SongsMachine = saved
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(SA.PCN.CA)
    m.reuse_heap = True
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    m.put(SA.CONF, b'http://nd.example:4533|alice|secret')
    m.curl_site = site or demo_site()
    m.card_mounted = True
    m.wifi = 4
    m.heap_cost = {}
    m.top_main = m.window
    return m


class NARM(SS.SM, ListMachine):
    """The Artists page's machine with the Navidrome card machine of sbsrc."""


def artists_page_machine(site=None):
    """The Artists page's machine (with the Albums page's widgets, so a tap opens the artist's albums) with a saved server, the card, Wi-Fi and the demo site."""
    m = artists_machine(cls=NARM, albums_page=True)
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(SA.PCN.CA)
    m.reuse_heap = True
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    m.put(SA.CONF, b'http://nd.example:4533|alice|secret')
    m.curl_site = site or demo_site()
    m.card_mounted = True
    m.wifi = 4
    m.heap_cost = {}
    m.fs[AL.ALBUMS_FILE] = b'1\n'
    return m


def albums_page_machine(site=None):
    """The Albums page's machine (also an artist's albums) with a saved server, the card, Wi-Fi and the demo site."""
    m = AL.albums_machine(30, cls=SS.SM)
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(SA.PCN.CA)
    m.reuse_heap = True
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    m.put(SA.CONF, b'http://nd.example:4533|alice|secret')
    m.curl_site = site or demo_site()
    m.card_mounted = True
    m.wifi = 4
    m.heap_cost = {}
    m.fs[AL.ALBUMS_FILE] = b'1\n'
    return m


def page_machine(site=None):
    """An album page machine with a saved server (conf, card, Wi-Fi) and the demo site."""
    saved = AP.AM
    AP.AM = NAM
    try:
        m = AP.album_machine(n=1, cover=None)
    finally:
        AP.AM = saved
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.present.add(SA.PCN.CA)
    m.reuse_heap = True
    m.fs['/dev/urandom'] = bytes(range(1, 65))
    m.put(SA.CONF, b'http://nd.example:4533|alice|secret')
    m.curl_site = site or demo_site()
    m.card_mounted = True
    m.wifi = 4
    m.heap_cost = {}
    m.images['file://' + cover_file()] = (168, 168, bytes(RED + (255,)) * (168 * 168))   # (what the decoder makes of the JPEG the server sent)
    return m


def synced(m):
    """Sync Now, run to its end: albums.idx and the rest of the root's lists on the card."""
    r, th = SA.ask(m, 'sba_sync')
    assert r == 0 and th, f'sync not queued ({r})'
    SA.drain(m, th)


def album_row(m, index=ALBUM_INDEX):
    h = SS.listing(m, LS_ALBUMS)[0]
    return m.deques[h][index]


def open_nd(m, row):
    """The Albums page's tap: album_open_src(&lib_nd, ...) on the row; the worker thread it started is kept in m.thread."""
    m.thread = None
    m.calls = []
    return m.call(PSYMS['album_open_src'], a0=SS.LIB, a1=AP.ALBUMS, a2=row, count=900000000)


def tick(m):
    """The page's gen timer once; the worker thread a request started is kept in m.thread."""
    m.thread = None
    m.top_main = m.window   # pod_is_top: the page re-reads its list only while it is in front
    m.call(PSYMS['ab_on_gen'], count=900000000)


def shows(m): return AP.vis(m, 'view_grid')[0], AP.vis(m, 'label_status')[0]   # (the track list, the "No songs" line)
def meta(m): return AP.utf(m.wtext[m.widgets['ab_meta']])


def titles(m):
    texts = AP.paint(m)[1]
    return [t for (t, r), st in texts if st == 'label_row_title']


def views(m, name): return m.curl_site.views().count(name)


def drain_all(m, th):
    if th: SA.drain(m, th)


def album(ctx):
    expect = ctx.expect
    # 1. the realistic sequence: the Albums page queued its covers (the queue takes six), then a tap
    m = page_machine()
    synced(m)
    row = album_row(m)
    m.thread = None
    asked = [SA.call(m, 'sba_cover', f'cv-{i}') for i in range(10)]
    th0 = m.thread
    expect(asked == [0] * 6 + [SA.R['QFULL']] * 4 and th0, f'the Albums page\'s covers fill six queue slots, the rest are refused ({asked})')
    r = open_nd(m, row)
    th = m.thread or th0
    expect(r == 0 and shows(m) == (1, 0) and AP.vis(m, 'ab_spin')[0] == 1, f'the page opens with its header and the spinner, not "No songs", while the album is on its way ({r}, {shows(m)})')
    expect(SA.state(m, SA.K['ALBUM'], '6dGMsiesuYw9lti9yGIGWY')[0] == SA.ST['LOAD'], 'getAlbum is queued behind the covers')
    drain_all(m, th)
    expect(m.curl_site.views().index('getAlbum') < m.curl_site.views().index('getCoverArt'), f'the worker takes the list before the covers ({m.curl_site.views()[-9:]})')
    tick(m)
    expect(shows(m) == (1, 0) and meta(m) == '2013 \xb7 11 tracks', f'the album page lists the 11 tracks of the demo album ({shows(m)}, {meta(m)!r})')
    expect('Feij\xe3o' in titles(m), f'the first track is drawn ({titles(m)[:3]})')
    expect(views(m, 'getAlbum') == 1, 'one request for the album')
    # 2. the header cover: the file the source names is decoded (a demo cover id, the Navidrome folder)
    expect(cover_file() not in m.fs and SA.state(m, SA.K['COVER'], COVER_ID)[0] == SA.ST['LOAD'] and m.thread, 'the page\'s own cover (refused behind the six covers) was asked for when the page read again')
    drain_all(m, m.thread)
    m.top_main = m.window   # pod_is_top: the shared cover poll only runs for the page in front
    m.call(PSYMS['ls_cover_tick'], count=80000000)
    expect(cover_file() in m.fs, f'the cover was fetched into the Navidrome folder ({cover_file()})')
    blits = AP.paint(m)[0]
    expect(any(b[2][2] == O['AH_ART'] and b[0] in m.bitmaps for b in blits) and m.win_colors(), 'the header shows the cover picture and the page is tinted from it')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # 3. a request that failed once is made again 10 seconds later, without anything else moving the generation
    calls = [0]

    def flaky(url, o):
        calls[0] += 1
        return {'rc': 6} if calls[0] == 1 else {'body': fixture('album.json')}
    m = page_machine(demo_site(getAlbum=flaky))
    synced(m)
    open_nd(m, album_row(m))
    drain_all(m, m.thread)
    tick(m)
    expect(shows(m) == (0, 1) and views(m, 'getAlbum') == 1 and SA.state(m, SA.K['ALBUM'], '6dGMsiesuYw9lti9yGIGWY')[0] == SA.ST['FAIL'], 'the first request failed: "No songs", the status is FAIL')
    tick(m)
    expect(m.thread is None, 'not asked again at once')
    m.clock += 11000
    tick(m)
    expect(m.thread is not None, 'ten seconds on the page reads again and asks again')
    drain_all(m, m.thread)
    tick(m)
    expect(shows(m) == (1, 0) and meta(m) == '2013 \xb7 11 tracks' and views(m, 'getAlbum') == 2, f'and the tracks appear ({shows(m)}, {meta(m)!r})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # 4. a full queue refuses the request: it is asked for again a moment later
    m = page_machine()
    synced(m)
    row = album_row(m)
    for i in range(8): SA.call(m, 'sba_fetch_album', f'other{i}')
    th = m.thread
    open_nd(m, row)
    expect(SA.state(m, SA.K['ALBUM'], '6dGMsiesuYw9lti9yGIGWY')[0] == SA.ST['NONE'] and shows(m) == (1, 0), 'eight requests wait: the album is refused (QFULL), asked again at the next read: the spinner, not "No songs"')
    drain_all(m, th)
    m.clock += 2000
    tick(m)
    expect(m.thread is not None, 'a second and a half on, the page reads again and asks')
    drain_all(m, m.thread)
    tick(m)
    expect(shows(m) == (1, 0) and meta(m) == '2013 \xb7 11 tracks', f'the tracks appear ({shows(m)})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # 5. no Wi-Fi when the album was tapped: the guard refuses it; when the Wi-Fi is back the next read asks
    m = page_machine()
    synced(m)
    row = album_row(m)
    m.wifi = -1
    open_nd(m, row)
    expect(m.thread is None and shows(m) == (0, 1), 'no Wi-Fi: nothing asked, "No songs"')
    m.wifi = 4
    m.clock += 11000
    tick(m)
    expect(m.thread is not None, 'the Wi-Fi is back: the next read asks')
    drain_all(m, m.thread)
    tick(m)
    expect(shows(m) == (1, 0), 'and the tracks appear')
    m.call(PSYMS['ab_on_destroy'], count=4000000)

    # 6. an album the server answers with no songs is final: it is not asked for again and again
    empty = json.loads(fixture('album.json'))
    empty['subsonic-response']['album']['song'] = []
    m = page_machine(demo_site(getAlbum={'body': json.dumps(empty).encode()}))
    synced(m)
    open_nd(m, album_row(m))
    drain_all(m, m.thread)
    tick(m)
    m.clock += 60000
    for _ in range(4): tick(m)
    expect(shows(m) == (0, 1) and views(m, 'getAlbum') == 1, f'an answer with no songs is not asked for again ({views(m, "getAlbum")} requests)')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


def gen(ctx):
    expect = ctx.expect
    m = page_machine()
    synced(m)
    g0, c0, n0 = SA.call(m, 'sba_gen'), SA.call(m, 'sba_cover_gen'), SS.call(m, SS.F_GEN, SS.LIB)
    # a cover asked for and fetched
    m.thread = None
    expect(SA.call(m, 'sba_cover', 'cv-ok') == 0, 'a cover is queued')
    expect(SA.call(m, 'sba_gen') == g0 and SS.call(m, SS.F_GEN, SS.LIB) == n0, 'asking for a cover does not move the list generation (the Albums page would drop every tile)')
    SA.drain(m, m.thread)
    expect(m.fs.get(cover_file('cv-ok')) is not None and SA.call(m, 'sba_gen') == g0 and SS.call(m, SS.F_GEN, SS.LIB) == n0 and SA.call(m, 'sba_cover_gen') != c0,
           'the cover arrived: the list generation is where it was, the cover generation moved')
    # no art: the server's 404 leaves an empty marker
    c1 = SA.call(m, 'sba_cover_gen')
    m.curl_site.routes['getCoverArt'] = {'rc': 22, 'code': 404}
    SA.run_one(m, 'sba_cover', 'cv-none')
    expect(m.fs.get(cover_file('cv-none')) == b'' and SA.call(m, 'sba_gen') == g0 and SA.call(m, 'sba_cover_gen') != c1, 'a 404 (no art): the empty marker, no list change')
    # a failed cover
    c2 = SA.call(m, 'sba_cover_gen')
    m.curl_site.routes['getCoverArt'] = {'rc': 6}
    SA.run_one(m, 'sba_cover', 'cv-bad')
    expect(SA.state(m, SA.K['COVER'], 'cv-bad')[0] == SA.ST['FAIL'] and SA.call(m, 'sba_gen') == g0 and SA.call(m, 'sba_cover_gen') != c2, 'a failed cover: no list change, the cover generation moves')
    # a list does move it
    SA.run_one(m, 'sba_fetch_album', '6dGMsiesuYw9lti9yGIGWY')
    expect(SA.call(m, 'sba_gen') != g0 and SS.call(m, SS.F_GEN, SS.LIB) != n0, 'an album that arrived moves the list generation')


def songs(ctx):
    expect = ctx.expect
    real = json.loads(fixture('search3-songs.json'))['subsonic-response']['searchResult3']['song']

    def page(offset, n):
        out = []
        for i in range(offset, offset + n):
            s = dict(real[i % len(real)])
            s['id'] = f'{s["id"][:-4]}{i:04d}'
            out.append(s)
        return json.dumps({'subsonic-response': {'status': 'ok', 'version': '1.16.1', 'searchResult3': {'song': out}}}).encode()
    per_song = len(page(0, 100)) / 100
    expect(per_song * 100 < RESPONSE_MAX // 2, f'a page of the Songs paging is under half of what one response may be ({int(per_song * 100)} of {RESPONSE_MAX} bytes)')
    expect(len(page(0, 4000)) > RESPONSE_MAX, f'a page of 4000 songs ({len(page(0, 4000))} bytes) is over what one response may be')

    def serve(url, o):
        q = SA.parse_qs(SA.urlparse(url).query)
        return {'body': page(int(q['songOffset'][0]), int(q['songCount'][0]))}
    m = page_machine(demo_site(search3=serve))
    h, rs, asked = SS.listing(m, LS_SONGS)
    q = m.curl_site.query(0)
    expect(asked == ['search3'] and q['songCount'] == '100' and q['songOffset'] == '0', f'the Songs list asks for 100 songs a page ({asked}, {q})')
    expect(SA.state(m, SA.K['SONGS']) == (SA.ST['OK'], 0), 'the first page arrived')
    h, rs, asked = SS.listing(m, LS_SONGS)
    expect(len(rs) == 100 and asked == ['search3'] and rs[0]['title'], f'the list shows the 100 songs and asks for the next page ({len(rs)}, {asked})')
    h, rs, asked = SS.listing(m, LS_SONGS)
    expect(len(rs) == 200 and SS.call(m, SS.F_COMPLETE, SS.LIB, LS_SONGS) == 0, f'the second page is appended, and there is more ({len(rs)})')
    # a response over the limit fails the request and leaves the list as it was
    m = page_machine(demo_site(search3={'body': page(0, 4000), 'chunk': 65536}))
    h, rs, asked = SS.listing(m, LS_SONGS)
    expect(SA.state(m, SA.K['SONGS'])[0] == SA.ST['FAIL'] and h == 0, 'a response over 4 MiB fails')


def artist_pl(ctx):
    expect = ctx.expect
    ARTIST_ID, PL_ID = '04HrSORpypcLGNUdQp37gn', '1C0i7qMeWcdTy2mrbA91Gi'

    def site(): return demo_site(getArtists={'body': fixture('artists.json')}, getPlaylists={'body': fixture('playlists.json')}, getArtist={'body': fixture('artist.json')},
                                 getPlaylist={'body': fixture('playlist.json')})

    def row_named(m, which, name):
        h, rs, _ = SS.listing(m, which)
        i = [r['title'] for r in rs].index(name)
        return m.deques[h][i]
    for covers in (0, 10):
        # the Artists page's tap: the artist's albums, then (the worker has run) again from the gen timer
        m = page_machine(site())
        synced(m)
        arow = row_named(m, SS.LS_ARTISTS, 'Back On Earth')
        m.thread = None
        asked = [SA.call(m, 'sba_cover', f'cv-{i}') for i in range(covers)]
        th0 = m.thread
        g0 = SA.call(m, 'sba_gen')
        h, rs, asked = SS.listing(m, LS_ALBUMS, arow, run=False)
        th = m.thread or th0
        expect(h != 0 and len(rs) == 4 and rs[3]['id'] == -2 and SA.state(m, SA.K['ARTIST'], ARTIST_ID)[0] == SA.ST['LOAD'] and th,
               f'covers={covers}: getArtist is not answered yet and is queued; the albums of the sync that name the artist show at once ({SA.state(m, SA.K["ARTIST"], ARTIST_ID)}, {[r["title"] for r in rs]})')
        drain_all(m, th)
        expect('getArtist' in m.curl_site.views(), f'covers={covers}: getArtist reached the server ({m.curl_site.views()[-4:]})')
        expect(SA.state(m, SA.K['ARTIST'], ARTIST_ID)[0] == SA.ST['OK'] and SA.call(m, 'sba_gen') != g0, f'covers={covers}: the answer was stored and moved the gen ({SA.state(m, SA.K["ARTIST"], ARTIST_ID)})')
        h, rs, asked = SS.listing(m, LS_ALBUMS, arow)
        expect(len(rs) == 4 and rs[3]['id'] == -2, f'covers={covers}: three albums and the All Songs row ({[r["title"] for r in rs]})')
        # the Artists page on the real list, a tap on the artist's row
        m = artists_page_machine(site())
        synced(m)
        m.call(PSYMS['artists_open_src'], a0=SS.LIB, count=60000000)
        names = AR.shown(m)
        expect('Back On Earth' in names, f'covers={covers}: the Artists page lists the real artists ({len(names)}, {names[:3]})')
        m.thread = None
        for i in range(covers): SA.call(m, 'sba_cover', f'cv-{i}')
        th0 = m.thread
        m.thread = None
        AR.artists_tap(m, names.index('Back On Earth'), starts=[st for st, _ in AR.Model(names).secs])
        th = m.thread or th0
        expect(('window_open', 'm1plus_albums') in m.calls and th, f'covers={covers}: the tap opens the albums page and starts getArtist ({m.names()[-6:]}, {th})')
        drain_all(m, th)
        m.call(PSYMS['al_on_gen'], count=900000000)
        expect(AL.vis(m, 'view_grid')[0] == 1 and AL.vis(m, 'label_status')[0] == 0 and AL.content_h(m) == O['AL_HEAD_END'] - O['PH_SHIFT'] + AL.RGAP + 2 * AL.PITCH,
               f'covers={covers}: three albums and All Songs (two grid rows) under the artist header (name, pills; a source artist has no circle) from the Artists page\'s tap ({AL.vis(m, "view_grid")}, {AL.vis(m, "label_status")}, {AL.content_h(m)})')
        # the artist's albums page (the Artists page's tap): opened empty, the worker runs, the page's gen timer reads it again
        m = albums_page_machine(site())
        synced(m)
        arow = row_named(m, SS.LS_ARTISTS, 'Back On Earth')
        m.thread = None
        for i in range(covers): SA.call(m, 'sba_cover', f'cv-{i}')
        th0 = m.thread
        m.thread = None
        r = m.call(PSYMS['albums_open_src'], a0=SS.LIB, a1=arow, count=900000000)
        th = m.thread or th0
        expect(r == 0 and AL.vis(m, 'label_status')[0] == 0, f'covers={covers}: the artist page opens with the sync\'s albums of the artist, no empty line ({r})')
        drain_all(m, th)
        m.call(PSYMS['al_on_gen'], count=900000000)
        blits, texts = AL.settle(m)
        titles_, _ = AL.grid_texts(m, texts)
        expect(len(titles_) == 4,
               f'covers={covers}: the page shows three albums and All Songs after the gen timer ({sorted(titles_)}, {AL.vis(m, "label_status")})')
        m.call(PSYMS['al_on_destroy'], count=4000000)
        # a playlist's tap
        m = page_machine(site())
        synced(m)
        prow = row_named(m, SS.LS_PLAYLISTS, 'On Repeat')
        m.thread = None
        asked = [SA.call(m, 'sba_cover', f'cv-{i}') for i in range(covers)]
        th0 = m.thread
        h, rs, asked = SS.listing(m, SS.LS_PLAYLISTS, prow, run=False)
        th = m.thread or th0
        drain_all(m, th)
        expect(SA.state(m, SA.K['PLAYLIST'], PL_ID)[0] == SA.ST['OK'], f'covers={covers}: getPlaylist stored ({SA.state(m, SA.K["PLAYLIST"], PL_ID)}, {m.curl_site.views()[-4:]})')
        h, rs, asked = SS.listing(m, SS.LS_PLAYLISTS, prow)
        expect(len(rs) == 40, f'covers={covers}: the playlist lists its 40 tracks ({len(rs)})')
        # the playlist's Songs page (the Playlists page's tap): opened empty, the worker runs, the page's gen timer reads it again
        m = songs_page_machine(site())
        synced(m)
        prow = row_named(m, SS.LS_PLAYLISTS, 'On Repeat')
        m.thread = None
        for i in range(covers): SA.call(m, 'sba_cover', f'cv-{i}')
        th0 = m.thread
        m.thread = None
        r = m.call(PSYMS['songs_open_src_in'], a0=SS.LIB, a1=SS.LS_PLAYLISTS, a2=prow, a3=m.cstr('On Repeat'), count=900000000)
        th = m.thread or th0
        expect(r == 0 and SG.vis(m, 'label_status')[0] == 0 and SG.vis(m, 'view_grid')[0] == 1 and SG.vis(m, 'sg_spin')[0] == 1, f'covers={covers}: the playlist page opens with the spinner, not the empty line ({r})')
        drain_all(m, th)
        m.call(PSYMS['sg_on_gen'], count=900000000)
        expect(SG.vis(m, 'view_grid')[0] == 1 and m.word(m.sv + SG.SC_VH) > 40 * SG.ROW, f'covers={covers}: the page shows the 40 tracks after the gen timer ({SG.vis(m, "view_grid")}, {m.word(m.sv + SG.SC_VH)})')
        m.call(PSYMS['sg_on_destroy'], count=4000000)
    # sbn_urlenc leaves no terminator: with a dirty stack (the request URL is a stack buffer) the id-only requests must still be exactly the expected URLs
    site_ = site()
    m = page_machine(site_)
    synced(m)
    arow, prow = row_named(m, SS.LS_ARTISTS, 'Back On Earth'), row_named(m, SS.LS_PLAYLISTS, 'On Repeat')
    m.u.mem_write(STACK - 0x20000, b'A' * 0x20000)
    for which, row_, ident in ((LS_ALBUMS, arow, ARTIST_ID), (SS.LS_PLAYLISTS, prow, PL_ID)):
        m.thread = None
        SS.listing(m, which, row_, run=False)
        drain_all(m, m.thread)
    ids = [(u.split('/rest/')[1].split('.view')[0], u.split('&id=')[1]) for u in site_.urls if '&id=' in u]
    expect(('getArtist', ARTIST_ID) in ids and ('getPlaylist', PL_ID) in ids, f'a dirty stack: getArtist and getPlaylist URLs end with exactly the id ({ids})')
    # the artist page's All Songs tile hands the source its own record (ID_ALL_SONGS, the artist's id in the path): the artist's songs, never getAlbum(artist id)
    site_ = site()
    m = albums_page_machine(site_)
    synced(m)
    arow = row_named(m, SS.LS_ARTISTS, 'Back On Earth')
    m.thread = None
    r = m.call(PSYMS['albums_open_src'], a0=SS.LIB, a1=arow, count=900000000)
    th = m.thread
    drain_all(m, th)
    m.call(PSYMS['al_on_gen'], count=900000000)
    AL.settle(m)
    scopes = []
    m.u.hook_add(UC_HOOK_CODE, lambda u, a, sz, _: scopes.append(u.reg_read(UC_MIPS_REG_A2)), begin=PSYMS['songs_open_src_in'], end=PSYMS['songs_open_src_in'])
    n0 = len(site_.urls)
    m.thread = None
    AL.tap_at(m, 250, AL.TOP + AL.RGAP + AL.PITCH + 10)
    rec = scopes[0] if scopes else 0
    got = (m.word(rec + O['REC_ID']) - (1 << 32), m.read_cstr(m.word(rec + O['REC_PATH']))) if rec else None
    expect(got == (-2, 'nd://' + ARTIST_ID), f'the All Songs tile opens the Songs page on its own record, ID_ALL_SONGS with the artist\'s id in the path ({got})')
    drain_all(m, m.thread or th)
    SS.listing(m, SS.LS_SONGS, rec)
    drain_all(m, m.thread or th)
    asked = [(u.split('/rest/')[1].split('.view')[0], u.split('&id=')[1] if '&id=' in u else '') for u in site_.urls[n0:] if 'getCoverArt' not in u]
    expect(len(asked) == 3 and ('getAlbum', ARTIST_ID) not in asked and all(v == 'getAlbum' for v, _ in asked),
           f'the artist\'s songs are the albums\' tracks (getAlbum of each album), never getAlbum(artist id) ({asked})')


def state(ctx):
    """lib_nd's state for the whole-library lists (scope NULL: Albums, Artists, Playlists, Favorites come with the sync, Songs with its own paging): LOADING before and while a request runs, OFFLINE with no
    Wi-Fi and nothing cached, FAILED after a failed request, READY once the server answered, even with nothing in the list."""
    expect = ctx.expect
    F_STATE = 56
    LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES = 1, 3, 4
    lists = (LS_ALBUMS, LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES, LS_SONGS)
    st = lambda m, which: SS.call(m, F_STATE, SS.LIB, which, 0)
    LOADING, FAILED, OFFLINE = 1, 2, 3
    m = page_machine()
    expect([st(m, w) for w in lists] == [LOADING] * 5, f'nothing asked, Wi-Fi up: every list is on its way ({[st(m, w) for w in lists]})')
    m.wifi = -1
    expect([st(m, w) for w in lists] == [OFFLINE] * 5, f'nothing asked and no Wi-Fi: OFFLINE ({[st(m, w) for w in lists]})')
    m.wifi = 4
    # a failing server: the list read asks, the state is LOADING while it runs and FAILED after it
    m = page_machine(demo_site(getAlbumList2={'rc': 6}, getArtists={'rc': 6}, getPlaylists={'rc': 6}, getStarred2={'rc': 6}))
    m.thread = None
    SS.call(m, SS.F_LIST, SS.LIB, LS_ARTISTS, 0)
    expect(m.thread and [st(m, w) for w in (LS_ALBUMS, LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES)] == [LOADING] * 4, 'the sync is running: LOADING')
    SA.drain(m, m.thread)
    expect([st(m, w) for w in (LS_ALBUMS, LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES)] == [FAILED] * 4, f'the sync failed: FAILED ({[st(m, w) for w in (LS_ALBUMS, LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES)]}, {SA.state(m, SA.K["SYNC"])})')
    # a request that failed for want of Wi-Fi says so
    m = page_machine()
    m.wifi = -1
    SS.call(m, SS.F_LIST, SS.LIB, LS_ARTISTS, 0)
    expect(st(m, LS_ARTISTS) == OFFLINE, 'no Wi-Fi: OFFLINE')
    # a sync that finished: READY, also for the lists the server has none of
    m = page_machine()
    synced(m)
    expect([st(m, w) for w in (LS_ALBUMS, LS_ARTISTS, LS_PLAYLISTS, LS_FAVORITES)] == [0] * 4 and not SS.listing(m, LS_PLAYLISTS)[1], 'the sync finished: READY, even for the empty Playlists')
    # the songs list: asked by the list read, FAILED when the server does not answer
    m = page_machine(demo_site(search3={'rc': 6}))
    m.thread = None
    SS.call(m, SS.F_LIST, SS.LIB, LS_SONGS, 0)
    expect(m.thread and st(m, LS_SONGS) == LOADING, 'the Songs list is asked for: LOADING')
    SA.drain(m, m.thread)
    expect(st(m, LS_SONGS) == FAILED, 'and FAILED when the server did not answer')


SECTIONS = [album, gen, songs, artist_pl, state]


def run(ctx):
    for f in SECTIONS: f(ctx)

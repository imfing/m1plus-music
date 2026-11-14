"""Find Cover & Lyrics, the network side (patch/pcnet.c "Find Cover & Lyrics", patch/pcjson.c pj_deezer / pj_lrc_each, patch/covercache.c's .pick marker; docs/modules/onlineart.md): the three
services' answers taken apart (fixtures in test/data/onlineart, Python's json module as the oracle), the requests (URL-encoded UTF-8 with spaces, & and CJK; the libcurl options; the user agent
LRCLIB asks for), the order of the job (iTunes, Deezer, the thumbnails, LRCLIB's get and search), the lyrics candidates (the exact match first, the rest by the closeness of their length, repeats dropped, the cap,
their files), every failure, Cancel and the single-thread rule, the larger picture fetched for the confirmation and the picked cover (the larger picture's address, the cache files, the .pick marker,
the folder picture), a lyrics candidate's save, and Rebuild Covers leaving a picked cover alone."""
import json, os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'test', 'data', 'onlineart')
SEARCH_DATA = os.path.join(ROOT, 'test', 'data', 'search')


PCS, PCJ = sibling('pcsearch'), sibling('pcjson')
PCN, fn = PCS.PCN, PCS.fn


def machine(*a, **kw):
    """The Podcasts tests' machine, writing down each second the worker sleeps (a wait is slept a second at a time: m.slept is a list of 1s)."""
    m = PCS.machine(*a, **kw)
    m.slept = []
    m.on_sleep = lambda k, m=m: m.slept.append(1)
    return m

PN = dict(PCN.PN, CANCELLED=12, NOFEED=16, NOLYRICS=17, OVERLOAD=18)
ART_DIR, COVERS = '/mnt/mmc/.m1plus/art', '/mnt/mmc/.m1plus/covers'
ITUNES = 'https://itunes.apple.com/search?media=music&entity=album&limit=8&term='
DEEZER = 'https://api.deezer.com/search/album?limit=8&q='
LRCLIB = 'https://lrclib.net/api/'
JPG = open(os.path.join(SEARCH_DATA, 'art100.jpg'), 'rb').read()
DEFS = {**cdefs.defines(os.path.join(ROOT, 'patch', 'artistphoto.h'), strings=True), **cdefs.defines(os.path.join(ROOT, 'patch', 'pcnet.h'), strings=True)}
PN_SRC = dict(ITUNES=0, DEEZER=1, NETEASE=2)   # patch/pcnet.h PN_SRC_*


def data(name): return open(os.path.join(DATA, name), 'rb').read()


def enc(s):
    from urllib.parse import quote
    return quote(s, safe='-_.~')


class Rec:
    """pj_result_t as the payload lays it out."""
    NAME, AUTHOR, URL, ART = 80, 56, 320, 320
    SIZE = 4 + NAME + AUTHOR + URL + 2 * ART

    @classmethod
    def parse(cls, raw, n):
        cs = lambda b: b.split(b'\0')[0].decode('utf-8')
        out = []
        for i in range(n):
            r = raw[i * cls.SIZE:(i + 1) * cls.SIZE]
            out.append((int.from_bytes(r[:4], 'little'), cs(r[4:84]), cs(r[84:140]), cs(r[140:460]), cs(r[460:620])))
        return out


def json_tests(ctx):
    """pj_results on the store's album answer and pj_deezer against json.loads (pj_lrc_each is tested through the job, lyrics_tests)."""
    expect = ctx.expect
    m = Machine()
    for base in (0x30000000, 0x30100000): m.u.mem_map(base, 0x40000)

    def call(name, raw, mx=8):
        src, dst = 0x30000000 + 0x40000 - len(raw), 0x30100000
        m.u.mem_write(src, raw)
        n = fn(m, name, src, len(raw), dst, mx)
        n = n - (1 << 32) if n >= 1 << 31 else n
        return n, Rec.parse(bytes(m.u.mem_read(dst, mx * Rec.SIZE)), max(n, 0))
    itunes, dz = data('itunes_album.json'), data('deezer_album.json')
    n, got = call('pj_results', itunes)
    want = [(r['collectionId'], r['collectionName'], r['artistName'], '', r.get('artworkUrl100', '')) for r in json.loads(itunes)['results']]
    expect(n == 5 and got == want, f'the store\'s album answer: five albums, id, name, artist and artwork as json.loads has them (the one without a picture too: {n})')
    expect(got[2][1] == '葉惠美' and got[2][2] == '周杰倫' and got[3][2] == 'Sigur Rós & Friends "Live"' and got[3][1] == 'Ágætis byrjun', 'CJK, accents, & and an escaped quote come through as they are')
    n, got = call('pj_deezer', dz)
    d = json.loads(dz)['data']
    want = [(r['id'], r['title'], r['artist']['name'], '', r.get('cover_medium', '')) for r in d]
    expect(n == 4 and got == want, f'Deezer\'s album answer: id, title, artist.name (a nested object) and cover_medium ({n})')
    expect(got[0][4].endswith('/250x250-000000-80-0-0.jpg') and got[2][2] == '周杰倫' and got[3][4] == '', 'the 250 px cover; the artist\'s name wherever its key stands in the nested object; no cover: empty')
    n, got = call('pj_deezer', dz, 2)
    expect(n == 2 and got[1][1] == 'Random Access Memories', 'room for two: the first two')
    expect(call('pj_deezer', itunes)[0] == -1 and call('pj_results', dz)[0] == -1, 'each extractor wants its own array ("data" / "results"): the other service\'s answer is not one')
    expect(call('pj_deezer', b'{"error":{"type":"Exception","message":"Quota limit exceeded","code":4}}')[0] == -1 and call('pj_deezer', b'{"data":[],"total":0}')[0] == 0, 'an error object is not an answer; an empty "data" is 0 results')
    n, got = call('pj_deezer', b'{"data":[{"id":5,"title":"T","artist":{"name":"A\\u00e9\\ud83c\\udfb5","id":1},"cover_medium":"https://c/250x250-1.jpg"}]}')
    expect(n == 1 and got[0][2] == 'Aé\U0001f3b5', 'escapes in the artist\'s name are decoded')
    n, got = call('pj_deezer', b'{"data":[{"id":5,"title":"T","artist":"flat","cover_medium":null}]}')
    expect(n == 1 and got[0][2] == '' and got[0][4] == '', 'an artist that is not an object and a null cover are empty')

def state(m):
    return dict(state=fn(m, 'pn_art_state'), code=fn(m, 'pn_art_code'), count=fn(m, 'pn_art_count'), gen=fn(m, 'pn_art_gen'), busy=fn(m, 'pn_job_busy'),
                lstate=fn(m, 'pn_lyr_state'), lcode=fn(m, 'pn_lyr_code'), lcount=fn(m, 'pn_lyr_count'))


def start(m, artist='Radiohead', album='OK Computer', title='Karma Police', secs=261):
    m.thread = None
    r = fn(m, 'pn_art', m.cstr(artist), m.cstr(album), m.cstr(title), secs)
    return r, m.thread


def thumb_path(m, i):
    buf = m.alloc(200)
    return m.read_cstr(buf) if fn(m, 'pn_art_thumb', i, buf, 200) else None


def cstr(raw): return raw.split(b'\0')[0].decode('utf-8')


def cands(m):
    """The lyrics candidates in display order, as pn_lyr_t lays them out (title 80, artist 56, album 80, secs, synced)."""
    out = []
    for i in range(fn(m, 'pn_lyr_count')):
        raw = bytes(m.u.mem_read(fn(m, 'pn_lyr_get', i), 224))
        out.append(dict(title=cstr(raw[:80]), artist=cstr(raw[80:136]), album=cstr(raw[136:216]), secs=int.from_bytes(raw[216:220], 'little'), synced=int.from_bytes(raw[220:224], 'little')))
    return out


def ltext(m, i):
    """Candidate i's text (pn_lyr_text: malloc'd), None when there is none."""
    nb = m.alloc(8)
    p = fn(m, 'pn_lyr_text', i, nb)
    return bytes(m.u.mem_read(p, m.word(nb))).decode('utf-8') if p else None


def info(m, i):
    """pn_art_name, pn_art_artist and pn_art_source of cover i."""
    return (m.read_cstr(fn(m, 'pn_art_name', i)).encode('latin-1').decode('utf-8'), m.read_cstr(fn(m, 'pn_art_artist', i)).encode('latin-1').decode('utf-8'), fn(m, 'pn_art_source', i))


class Site:
    """The three services on one scripted server: every request is logged; each service can be told to fail."""
    def __init__(self, **over):
        self.reqs, self.over = [], over

    def __call__(self, url, o):
        self.reqs.append((url, dict(o)))
        for prefix, r in self.over.items():
            if url.startswith(prefix): return r(url, o) if callable(r) else r
        if url.startswith(ITUNES): return {'body': data('itunes_album.json')}
        if url.startswith(DEEZER): return {'body': data('deezer_album.json')}
        if url.startswith(LRCLIB + 'get?'): return {'body': data('lrclib_get.json')}
        if url.startswith(LRCLIB + 'search?'): return {'body': data('lrclib_search.json')}
        if url.startswith(NETEASE_ARTIST): return {'body': NETEASE_NONE}
        if 'mzstatic' in url or 'dzcdn' in url or 'music.126.net' in url: return {'body': JPG, 'chunk': 5500}
        return {'rc': 22, 'code': 404}

    def urls(self): return [u for u, _ in self.reqs]


def wanted_art():
    """The pictures the job offers from the fixtures: the store's first six albums that have one, then Deezer's up to twelve in all."""
    it, dz = json.loads(data('itunes_album.json'))['results'], json.loads(data('deezer_album.json'))['data']
    a = [r['artworkUrl100'] for r in it if r.get('artworkUrl100')][:6]
    return a + [r['cover_medium'] for r in dz if r.get('cover_medium')][:12 - len(a)], len(a)


def job_tests(ctx):
    expect = ctx.expect
    site = Site()
    m = machine(site=site)
    r, th = start(m, 'Radiohead', 'OK Computer & Co', 'Karma Police', 261)
    names = [c[0] for c in m.calls]
    expect(r == 0 and th and th[0] == PSYMS['pn_amain'] and names.count('pthread_create') == 1 and names.count('pthread_detach') == 1 and ('curl_global_init', 3) in m.calls,
           'a lookup starts one detached worker, curl initialised on the UI thread first')
    st = state(m)
    expect(st['state'] == 1 and st['busy'] == 1 and fn(m, 'pn_busy') == 0 and st['lstate'] == 0, f'the cover queries run: state 1, a job is busy, a refresh is not, no lyrics yet ({st})')
    expect(start(m)[0] == PN['BUSY'] and fn(m, 'pn_art_pick', 0, 0, 1, 0) == PN['NOFEED'] and fn(m, 'pn_art_fetch', 0) == PN['NOFEED'] and fn(m, 'pn_search', m.cstr('x')) == PN['BUSY'],
           'a second job while one runs: PN_BUSY (a pick or a fetch of a cover that is not there: refused)')
    expect(fn(m, 'pn_dl_start') == 0 and fn(m, 'pn_dl_running') == 0, 'the downloads do not start while the lookup runs')
    gen0 = st['gen']
    PCN.work(m, th)
    st = state(m)
    want_art, n_it = wanted_art()
    N = len(want_art)
    expect(N == 7 and n_it == 4, f'the fixtures offer four albums of the store and three of Deezer ({n_it}, {N})')
    expect(st['state'] == 3 and st['code'] == 0 and st['count'] == N and st['busy'] == 0 and st['gen'] > gen0 and st['lstate'] == 1 and st['lcode'] == 0 and st['lcount'] == 3, f'the worker ends: covers done, OK, {N} covers; lyrics answered, three candidates ({st})')
    urls = site.urls()
    expect(urls[0] == ITUNES + 'Radiohead%20OK%20Computer%20%26%20Co', f'the first request is the store\'s with "artist album" URL-encoded (space %20, & %26): {urls[0]}')
    expect(urls[1] == DEEZER + 'Radiohead%20OK%20Computer%20%26%20Co', f'then Deezer\'s with the same term: {urls[1]}')
    expect(urls[2:2 + N] == want_art, 'the thumbnails are fetched one by one in order: the store\'s albums that have a picture, then Deezer\'s until there are twelve in all')
    expect(urls[2 + N] == LRCLIB + 'get?track_name=Karma%20Police&artist_name=Radiohead&album_name=OK%20Computer%20%26%20Co&duration=261', f'then LRCLIB\'s get with the track, artist, album and length: {urls[2 + N]}')
    expect(urls[3 + N] == LRCLIB + 'search?track_name=Karma%20Police&artist_name=Radiohead' and len(urls) == 4 + N, f'and its search for the title and artist, always (the candidates): {len(urls)} requests')
    for u, o in site.reqs:
        expect(o[10065] == PCN.CA and o[52] == 1 and o[68] == 16 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[99] == 1 and o[78] == 20 and 64 not in o and 81 not in o, f'{u[:40]}: the firmware CA bundle, verification never switched off, 16 redirects limited to http(s), fail on HTTP error')
    ua = site.reqs[0][1][10018]
    expect(ua.startswith('M1PlusMusic/') and 'github.com/imfing/m1plus-mod' in ua, f'a user agent that names the app and its address (LRCLIB asks for it): {ua}')
    paths = [thumb_path(m, i) for i in range(N)]
    expect(paths == [f'{ART_DIR}/a{i}.jpg' for i in range(N)] and all(m.fs.get(p) == JPG for p in paths), 'each thumbnail is a<n>.jpg in the art directory, whole')
    expect(thumb_path(m, N) is None and thumb_path(m, -1) is None and fn(m, 'pn_art_thumb_state', 0) == 1 and fn(m, 'pn_art_thumb_state', 12) == 0, 'no thumbnail past the last')
    expect(not [p for p in m.fs if p.endswith(('.src', '.tmp'))] and len(m.curl) == 0, 'no temp file, every handle cleaned up')
    expect(ART_DIR in m.dirs and '/mnt/mmc/.m1plus' in m.dirs, 'the directories are made')
    # each cover's text: album, artist, source
    it, dz = json.loads(data('itunes_album.json'))['results'], json.loads(data('deezer_album.json'))['data']
    it_ok = [r for r in it if r.get('artworkUrl100')][:6]
    dz_ok = [r for r in dz if r.get('cover_medium')][:12 - len(it_ok)]
    want_info = [(r['collectionName'], r['artistName'], 0) for r in it_ok] + [(r['title'], r['artist']['name'], 1) for r in dz_ok]
    expect([info(m, i) for i in range(N)] == want_info, f'pn_art_name / artist / source: the album, the artist and where it came from (0 the store, 1 Deezer): {info(m, 0)} ... {info(m, N - 1)}')
    expect(info(m, 2)[:2] == ('葉惠美', '周杰倫') and fn(m, 'pn_art_source', 3) == 0 and fn(m, 'pn_art_source', 4) == 1 and m.read_cstr(fn(m, 'pn_art_name', 99)) == '', 'CJK as it is; the fifth cover is Deezer\'s; out of range: empty')
    # the candidates: the exact match first, then by closeness of the length to 261 s
    cs = cands(m)
    g = json.loads(data('lrclib_get.json'))
    expect([c['title'] for c in cs] == [g['trackName'], 'Both', 'Plain Only'] and [c['synced'] for c in cs] == [1, 1, 0] and [c['secs'] for c in cs] == [259, 201, 200],
           f'the exact match (api/get) first, then the search\'s by the closeness of their length to 261 s (the instrumental record has no lyrics and is not one): {[(c["title"], c["secs"]) for c in cs]}')
    expect(cs[0]['artist'] == 'Queen' and cs[0]['album'] == 'The Works (Remastered 2011)' and cs[1]['album'] == 'Somewhere', 'artist and album come with each')
    expect(ltext(m, 0) == g['syncedLyrics'].replace('\r', '') and ltext(m, 1) == '[00:01.00] 歌词第一行\n[00:05.50] 第二行\n' and ltext(m, 2) == 'First plain line\nSecond plain line\nThird — plain line' and ltext(m, 3) is None and ltext(m, -1) is None,
           'each candidate\'s text is its synced lyrics (else plain), carriage returns dropped, held in a file of its own until the page saves one')
    expect(sorted(p[len(ART_DIR):] for p in m.fs if p.startswith(ART_DIR + '/l')) == ['/l0.txt', '/l1.txt', '/l2.txt'] and fn(m, 'pn_lyr_get', 3) == 0, 'the files are l<slot>.txt in the art directory')
    # the larger picture's address
    buf = m.alloc(300)
    for thumb, big in ((want_art[0], want_art[0].replace('100x100bb', '600x600bb')), (want_art[4], want_art[4].replace('250x250-', '500x500-')), ('https://x.example/p.jpg', 'https://x.example/p.jpg')):
        ok = fn(m, 'pn_art_full', m.cstr(thumb), buf, 300)
        expect(ok == 1 and m.read_cstr(buf) == big, f'pn_art_full: {thumb[-30:]} -> {big[-30:]}')
    expect(fn(m, 'pn_art_full', m.cstr(want_art[0]), buf, 10) == 0, 'an address that does not fit the buffer: 0')
    # a new lookup removes the old files and results at once
    m.calls = []
    r, th = start(m, 'A', 'B', 'C')
    expect(r == 0 and state(m)['count'] == 0 and state(m)['lstate'] == 0 and state(m)['lcount'] == 0 and thumb_path(m, 0) is None and not [p for p in m.fs if p.startswith(ART_DIR + '/l')] and state(m)['state'] == 1,
           'a new lookup clears the covers, the lyrics and the files before it starts')
    PCN.work(m, th)

    # CJK, no album, no length
    site = Site()
    m = machine(site=site)
    r, th = start(m, '周杰倫', '', '晴天', 0); PCN.work(m, th)
    urls = site.urls()
    expect(urls[0] == ITUNES + enc('周杰倫 晴天'), f'with no album tag the title is searched with the artist: {urls[0]}')
    expect([u for u in urls if u.startswith(LRCLIB)] == [LRCLIB + 'get?track_name=' + enc('晴天') + '&artist_name=' + enc('周杰倫'), LRCLIB + 'search?track_name=' + enc('晴天') + '&artist_name=' + enc('周杰倫')],
           'no album_name and no duration in LRCLIB\'s get when they are not known')
    site = Site()
    m = machine(site=site)
    r, th = start(m, '周杰倫', '葉惠美', '晴天', 269); PCN.work(m, th)
    expect(site.urls()[0] == ITUNES + enc('周杰倫 葉惠美') and site.urls()[0].count('%') == 3 * 6 + 1, 'CJK terms are URL-encoded UTF-8 (three bytes a character, %XX each, and the space)')
    expect(any(u == LRCLIB + 'get?track_name=' + enc('晴天') + '&artist_name=' + enc('周杰倫') + '&album_name=' + enc('葉惠美') + '&duration=269' for u in site.urls()), 'and in LRCLIB\'s get too')
    # a query field is cut at 95 bytes on a character boundary
    site = Site()
    m = machine(site=site)
    r, th = start(m, '中' * 40, 'é' * 60, 'x' * 100, 0); PCN.work(m, th)
    expect(site.urls()[0] == ITUNES + enc('中' * 31) + '%20' + enc('é' * 47), f'a field longer than 95 bytes is cut before the character that does not fit: {site.urls()[0][-40:]}')
    expect(state(m)['code'] == 0, 'the long query still goes through (the request buffer holds three encoded fields)')


def body(*recs): return json.dumps(list(recs), ensure_ascii=False).encode('utf-8')


def rec(title, secs=None, synced=None, plain=None, artist='Queen', album='Greatest'):
    return dict(trackName=title, artistName=artist, albumName=album, duration=secs, instrumental=False, plainLyrics=plain, syncedLyrics=synced)


def lyrics_tests(ctx):
    expect = ctx.expect
    NO = {'rc': 22, 'code': 404}
    # get 404: the search's records are the candidates
    site = Site(**{LRCLIB + 'get?': NO})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    ls = [u for u in site.urls() if u.startswith(LRCLIB)]
    st = state(m)
    expect(ls == [LRCLIB + 'get?track_name=Karma%20Police&artist_name=Radiohead&album_name=OK%20Computer&duration=261', LRCLIB + 'search?track_name=Karma%20Police&artist_name=Radiohead'], f'get and then search ({ls})')
    cs = cands(m)
    expect(st['lcode'] == 0 and [c['title'] for c in cs] == ['Both', 'Plain Only'] and ltext(m, 0) == '[00:01.00] 歌词第一行\n[00:05.50] 第二行\n', 'a 404 from get: the search\'s records with lyrics (the instrumental one has none)')
    # get with plain only, the search with the same record: one candidate, not two
    plain_rec = rec('Karma Police', 261, plain='One\nTwo\nThree', artist='Radiohead', album='OK Computer')
    site = Site(**{LRCLIB + 'get?': {'body': json.dumps(plain_rec).encode()}, LRCLIB + 'search?': {'body': body(plain_rec, rec('Karma Police (Live)', 270, synced='[00:01.00] live\n', artist='Radiohead'))}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    cs = cands(m)
    expect([(c['title'], c['synced']) for c in cs] == [('Karma Police', 0), ('Karma Police (Live)', 1)] and ltext(m, 0) == 'One\nTwo\nThree', 'a record that api/search repeats from api/get is one candidate (the get\'s, first)')
    # the same record, plain and synced as two records, are two
    site = Site(**{LRCLIB + 'get?': NO, LRCLIB + 'search?': {'body': body(rec('Same', 261, plain='p'), rec('Same', 261, synced='[00:01.00] s\n'))}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect([c['synced'] for c in cands(m)] == [1, 0], 'two records alike in every field but the kind are two candidates, the synced one first among equals')
    # the search failing after a plain get: the get's candidate is still found
    site = Site(**{LRCLIB + 'get?': {'body': json.dumps(plain_rec).encode()}, LRCLIB + 'search?': {'rc': 6}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['lcode'] == 0 and st['lcount'] == 1 and ltext(m, 0) == 'One\nTwo\nThree', 'the search failing after a get that found something: that candidate, the lookup is OK')
    # the order: the closeness of the length (261 s), a synced one before a plain one among equals, a record without a length last
    recs = [rec('A', 100, plain='a'), rec('B', 259, synced='[00:01.00] b\n'), rec('C', 259, plain='c'), rec('D', 262, synced='[00:01.00] d\n'), rec('E', None, plain='e')]
    site = Site(**{LRCLIB + 'get?': NO, LRCLIB + 'search?': {'body': body(*recs)}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect([c['title'] for c in cands(m)] == ['D', 'B', 'C', 'A', 'E'], f'by the length\'s distance to the track\'s: {[c["title"] for c in cands(m)]}')
    expect([ltext(m, i) for i in range(5)] == ['[00:01.00] d\n', '[00:01.00] b\n', 'c', 'a', 'e'], 'and each keeps its own text (the files are by arrival, the order is a table)')
    m = machine(site=Site(**{LRCLIB + 'get?': NO, LRCLIB + 'search?': {'body': body(*recs)}}))
    r, th = start(m, secs=0); PCN.work(m, th)
    expect([c['title'] for c in cands(m)] == ['B', 'D', 'A', 'C', 'E'], 'with no length for the track: arrival order, synced first')
    # the exact match stays first whatever its length
    site = Site(**{LRCLIB + 'get?': {'body': json.dumps(rec('Exact', 30, plain='x')).encode()}, LRCLIB + 'search?': {'body': body(rec('Near', 261, plain='n'))}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect([c['title'] for c in cands(m)] == ['Exact', 'Near'], 'the exact match (api/get) first even when another length is closer')
    # at most PN_LYR_MAX (20) candidates
    site = Site(**{LRCLIB + 'get?': NO, LRCLIB + 'search?': {'body': body(*[rec(f'T{i}', 200 + i, plain=f'p{i}') for i in range(25)])}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect(len(cands(m)) == 20 and fn(m, 'pn_lyr_get', 20) == 0 and ltext(m, 19) is not None and len([p for p in m.fs if p.startswith(ART_DIR + '/l')]) == 20, 'twenty candidates at most, twenty files')
    # a text over the cap ends at its last whole line, never in a character
    lines = ''.join(f'[00:{i % 60:02d}.00] 行{i}\n' for i in range(3000))
    site = Site(**{LRCLIB + 'get?': {'body': json.dumps(rec('Long', 261, synced=lines), ensure_ascii=False).encode()}, LRCLIB + 'search?': {'body': b'[]'}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    t = ltext(m, 0)
    expect(t is not None and 40000 < len(t.encode()) <= 49152 and t.endswith('\n') and lines.startswith(t), f'a text over 48 KB ends at its last whole line ({len(t.encode())} bytes of {len(lines.encode())})')
    # an answer cut inside a record: the records before it
    raw = data('lrclib_search.json')
    cut = raw[:raw.index(b'"Both"') + 30]
    site = Site(**{LRCLIB + 'get?': NO, LRCLIB + 'search?': {'body': cut}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect([c['title'] for c in cands(m)] == ['Plain Only'], 'an answer cut inside the third record: the record before it is a candidate, the cut one is not')
    site = Site(**{LRCLIB + 'get?': {'body': data('lrclib_get.json')[:200]}, LRCLIB + 'search?': {'body': b'[]'}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect(state(m)['lcode'] == PN['NOLYRICS'], 'a get answer cut inside its lyrics: none')
    site = Site(**{LRCLIB + 'get?': {'body': b'{"syncedLyrics":"\\u00zz\\ud83c x\\n","trackName":"T"}'}, LRCLIB + 'search?': {'body': b'[]'}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect(state(m)['lstate'] == 1, 'bad escapes do not fault')
    # nothing anywhere: not found
    for label, getr, searchr in (('both 404', NO, NO), ('get 404, empty search', NO, {'body': b'[]'}),
                                 ('instrumental', {'body': json.dumps({'instrumental': True, 'plainLyrics': None, 'syncedLyrics': None}).encode()}, {'body': b'[]'}),
                                 ('not JSON', {'body': b'<html>'}, {'body': b'<html>'})):
        site = Site(**{LRCLIB + 'get?': getr, LRCLIB + 'search?': searchr})
        m = machine(site=site)
        r, th = start(m); PCN.work(m, th)
        st = state(m)
        expect(st['lstate'] == 1 and st['lcode'] == PN['NOLYRICS'] and st['lcount'] == 0 and not [p for p in m.fs if p.startswith(ART_DIR + '/l')] and ltext(m, 0) is None and st['code'] == 0 and st['count'] == 7,
               f'{label}: PN_NOLYRICS, no file, the covers unaffected ({st})')
    # failures of the lyrics service do not touch the covers, and are told apart
    for label, getr, code in (('no connection', {'rc': 6}, PN['NET']), ('a certificate error', {'rc': 60}, PN['CERT']), ('HTTP 500', {'rc': 22, 'code': 500}, PN['HTTP'])):
        site = Site(**{LRCLIB: getr})
        m = machine(site=site)
        r, th = start(m); PCN.work(m, th)
        st = state(m)
        expect(st['lcode'] == code and st['lstate'] == 1 and st['lcount'] == 0 and st['count'] == 7 and st['code'] == 0 and st['busy'] == 0, f'LRCLIB: {label}: code {code}, covers fine ({st})')
    m = machine(site=Site(**{LRCLIB + 'get?': {'rc': 6}}))
    r, th = start(m); PCN.work(m, th)
    expect(not [u for u in m.curl_site.urls() if u.startswith(LRCLIB + 'search')], 'a network failure of get does not try the search (it would fail the same way)')
    # texts that cannot be written: not candidates; none written: storage
    m = machine(site=Site())
    m.fail = {('write', f'{ART_DIR}/lyrics.tmp')}
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['lcode'] == PN['STORAGE'] and st['lcount'] == 0, f'no text could be written: PN_STORAGE ({st})')
    # Save: atomically, over the lyrics' file
    site = Site()
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    lrc = '/mnt/mmc/Music/Radiohead/OK Computer/02 Karma Police.lrc'
    m.dirs.add('/mnt/mmc/Music/Radiohead/OK Computer')
    m.fs[lrc] = b'old lyrics'
    expect(m.fs[lrc] == b'old lyrics', 'finding lyrics never touches an .lrc that is there')
    ok = fn(m, 'pn_lyr_save', 1, m.cstr(lrc))
    expect(ok == 1 and m.fs[lrc] == '[00:01.00] 歌词第一行\n[00:05.50] 第二行\n'.encode() and lrc + '.tmp' not in m.fs and ('rename', lrc + '.tmp', lrc) in m.calls,
           'pn_lyr_save of candidate 1 writes a temp file and renames it over the .lrc (the user chose Replace)')
    m.card_mounted = False
    expect(fn(m, 'pn_lyr_save', 0, m.cstr(lrc + '2')) == 0 and lrc + '2' not in m.fs, 'no card mounted: nothing written')
    m.card_mounted = True
    m.fail = {('write', lrc + '3.tmp')}
    expect(fn(m, 'pn_lyr_save', 0, m.cstr(lrc + '3')) == 0 and lrc + '3' not in m.fs and lrc + '3.tmp' not in m.fs, 'a write that fails leaves no file and no temp file')
    m.fail = set()
    expect(fn(m, 'pn_lyr_save', 7, m.cstr(lrc + '4')) == 0 and fn(m, 'pn_lyr_save', -1, m.cstr(lrc + '5')) == 0, 'a candidate that is not there: nothing to save')
    del m.fs[f'{ART_DIR}/l2.txt']
    expect(fn(m, 'pn_lyr_save', 1, m.cstr(lrc + '6')) == 0, 'its file gone: nothing to save')


def failure_tests(ctx):
    expect = ctx.expect
    for label, over, code in (('no connection', {ITUNES: {'rc': 6}, DEEZER: {'rc': 6}}, PN['NET']), ('a certificate error', {ITUNES: {'rc': 60}, DEEZER: {'rc': 60}}, PN['CERT']),
                              ('both HTTP 500', {ITUNES: {'rc': 22, 'code': 500}, DEEZER: {'rc': 22, 'code': 500}}, PN['HTTP']),
                              ('an HTML page from both', {ITUNES: {'body': b'<html>x</html>'}, DEEZER: {'body': b'<html>x</html>'}}, PN['HTTP'])):
        m = machine(site=Site(**over))
        r, th = start(m); PCN.work(m, th)
        st = state(m)
        expect(r == 0 and st['state'] == 3 and st['code'] == code and st['count'] == 0 and st['busy'] == 0 and st['lstate'] == 1, f'{label}: covers done with code {code} and no cover; the lyrics still ran ({st})')
    # one service down: the other's covers are offered
    m = machine(site=Site(**{ITUNES: {'rc': 22, 'code': 500}}))
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['code'] == 0 and st['count'] == 3 and thumb_path(m, 0) and thumb_path(m, 2), f'the store failing: Deezer\'s three covers are offered ({st})')
    m = machine(site=Site(**{DEEZER: {'rc': 6}}))
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['code'] == 0 and st['count'] == 4, f'Deezer failing: the store\'s four covers ({st})')
    # an answer with no album: OK with 0 covers (the page says No results)
    m = machine(site=Site(**{ITUNES: {'body': b'{"resultCount":0,"results":[]}'}, DEEZER: {'body': b'{"data":[],"total":0}'}}))
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['code'] == 0 and st['count'] == 0 and st['state'] == 3 and st['lcount'] == 3, f'no result from either: OK with 0 covers, the lyrics still found ({st})')
    # results without any picture are not offered
    m = machine(site=Site(**{ITUNES: {'body': b'{"results":[{"collectionName":"A","artistName":"B"}]}'}, DEEZER: {'body': b'{"data":[{"id":1,"title":"A"}]}'}}))
    r, th = start(m); PCN.work(m, th)
    expect(state(m)['count'] == 0, 'an album without a picture address is not offered')
    # more albums than the cap: six of the store, twelve in all
    many_it = json.dumps({'results': [{'collectionId': i + 1, 'collectionName': f'S{i}', 'artistName': 'X', 'artworkUrl100': f'https://is1-ssl.mzstatic.com/image/thumb/Music/{i}/100x100bb.jpg'} for i in range(8)]}).encode()
    many_dz = json.dumps({'data': [{'id': i + 1, 'title': f'D{i}', 'artist': {'name': 'Y'}, 'cover_medium': f'https://cdns-images.dzcdn.net/images/cover/{i}/250x250-000000-80-0-0.jpg'} for i in range(8)]}).encode()
    m = machine(site=Site(**{ITUNES: {'body': many_it}, DEEZER: {'body': many_dz}}))
    r, th = start(m); PCN.work(m, th)
    expect(state(m)['count'] == 12 and [info(m, i)[0] for i in range(12)] == [f'S{i}' for i in range(6)] + [f'D{i}' for i in range(6)] and fn(m, 'pn_art_source', 5) == 0 and fn(m, 'pn_art_source', 6) == 1, 'the store\'s first six, Deezer\'s until there are twelve')
    # a thumbnail that is missing or not a picture: the placeholder stays, the rest arrive
    def thumbs(u, o):
        if '/b6/5a' in u: return {'rc': 22, 'code': 404}
        if 'Music117' in u: return {'body': b'<html>nope</html>'}
        return {'body': JPG}
    site2 = Site(**{'https://is1-ssl.mzstatic.com': thumbs})
    m = machine(site=site2)
    r, th = start(m); PCN.work(m, th)
    states = [fn(m, 'pn_art_thumb_state', i) for i in range(7)]
    expect(states == [2, 2, 1, 1, 1, 1, 1] and thumb_path(m, 0) is None and not [p for p in m.fs if p.endswith('.src')], f'a thumbnail that is missing or not a picture is marked failed (the placeholder), the others arrive ({states})')
    # guards
    for label, kw, code in (('no Wi-Fi', dict(wifi=-1), PN['NOWIFI']), ('no card', dict(card_mounted=False), PN['STORAGE']), ('a clock never set', dict(wall=1700000000), PN['NOCLOCK'])):
        m = machine(site=Site(), **kw)
        r, th = start(m)
        expect(r == code and th is None and 'curl_global_init' not in [c[0] for c in m.calls] and fn(m, 'pn_art_state') == 0, f'{label}: the guard answers {code}, nothing starts')
    m = machine(site=Site(), ca=False)
    expect(start(m)[0] == PN['NOCERT'], 'no CA bundle: PN_NOCERT')
    m = machine(site=Site(), thread_ok=False)
    r, th = start(m)
    expect(r == PN['MEM'] and state(m)['busy'] == 0 and state(m)['state'] == 0, 'a thread that cannot be made: PN_MEM, not busy, state idle')
    m = machine(site=Site()); m.calloc_fail = True
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['code'] == PN['MEM'] and st['busy'] == 0 and st['lstate'] == 1 and st['lcode'] == PN['MEM'], f'no memory for the answer buffer: PN_MEM for both parts, the worker ends ({st})')


def cancel_tests(ctx):
    expect = ctx.expect
    cancel = PCS.cancel
    m = machine(site=lambda u, o: {'body': data('itunes_album.json'), 'xfer': lambda url, sent, total: cancel(m)})
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['state'] == 3 and st['code'] == PN['CANCELLED'] and st['count'] == 0 and st['busy'] == 0 and st['lstate'] == 1 and st['lcode'] == PN['CANCELLED'], f'cancelled during the first query: done, PN_CANCELLED for both parts ({st})')
    got = []

    def site(u, o):
        got.append(u)
        if len(got) == 4: cancel(m2)
        return Site()(u, o)
    m2 = machine(site=site)
    r, th = start(m2); PCN.work(m2, th)
    st = state(m2)
    expect(len(got) == 4 and st['count'] == 7 and st['busy'] == 0 and fn(m2, 'pn_art_thumb_state', 0) == 1 and fn(m2, 'pn_art_thumb_state', 1) == 2 and fn(m2, 'pn_art_thumb_state', 2) == 0 and st['lcode'] == PN['CANCELLED'] and st['lcount'] == 0,
           f'cancelled during the second thumbnail (it is cut off), no more are asked for ({len(got)} requests), the lyrics are not asked for, the worker ended ({st})')
    expect(fn(m2, 'pn_dl_start') == 0 and fn(m2, 'pn_job_busy') == 0, 'afterwards the downloads may start again')


def pick_tests(ctx):
    expect = ctx.expect
    key0, key1 = 0x1234abcd, 0x0badf00d
    folder = '/mnt/mmc/Music/Radiohead/OK Computer'
    site = Site()
    m = machine(site=site)
    m.dirs.update({folder, COVERS})
    r, th = start(m); PCN.work(m, th)
    n0 = len(site.reqs)
    # fetch: the larger picture for the confirmation page
    buf = m.alloc(200)
    expect(fn(m, 'pn_art_full_path', 0, buf, 200) == 0, 'before a fetch there is no larger picture')
    m.thread = None
    r = fn(m, 'pn_art_fetch', 0)
    expect(r == 0 and m.thread and m.thread[0] == PSYMS['pn_kmain'] and fn(m, 'pn_pick_state') == 1 and fn(m, 'pn_job_busy') == 1, 'a fetch starts the worker (the pick job, state 1)')
    expect(fn(m, 'pn_art_fetch', 1) == PN['BUSY'] and fn(m, 'pn_art_pick', 1, m.cstr(folder), key0, 0) == PN['BUSY'], 'a second fetch or a pick while one runs: PN_BUSY')
    PCN.work(m, m.thread)
    big = site.urls()[2].replace('100x100bb', '600x600bb')
    expect(site.urls()[n0:] == [big] and fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == 0 and fn(m, 'pn_job_busy') == 0, f'the larger picture (600x600bb) is fetched: OK ({site.urls()[n0:]})')
    expect(fn(m, 'pn_art_full_path', 0, buf, 200) == 1 and m.read_cstr(buf) == f'{ART_DIR}/full.jpg' and m.fs.get(f'{ART_DIR}/full.jpg') == JPG and fn(m, 'pn_art_full_path', 1, buf, 200) == 0 and fn(m, 'pn_art_full_path', 99, buf, 200) == 0,
           'full.jpg holds it, for cover 0 only')
    expect(not [p for p in m.fs if p.startswith(COVERS)] and f'{folder}/cover.jpg' not in m.fs, 'a fetch writes nothing to the cover cache or the folder: nothing changes until the user says')
    # the pick takes the picture that was fetched: no second download
    n1 = len(site.reqs)
    m.thread = None
    r = fn(m, 'pn_art_pick', 0, m.cstr(folder), key0, key1)
    expect(r == 0 and m.thread and m.thread[0] == PSYMS['pn_kmain'] and fn(m, 'pn_pick_state') == 1, 'the pick starts the worker (state 1)')
    PCN.work(m, m.thread)
    expect(len(site.reqs) == n1 and fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == 0 and fn(m, 'pn_job_busy') == 0, f'the picture already held is used: no request ({len(site.reqs) - n1}), OK')
    for key in (key0, key1):
        cache = f'{COVERS}/r{key:08x}-168.jpg'
        expect(cache in m.fs and len(m.fs[cache]) > 100 and m.fs[cache][:2] == b'\xff\xd8' and f'{cache}.tmp' not in m.fs, f'the cover cache file of key {key:08x} is a JPEG, written through a temp file')
        expect(f'{cache}.pick' in m.fs, 'and the .pick marker beside it')
    expect(m.fs.get(f'{folder}/cover.jpg') == JPG and f'{folder}/.cover.tmp' not in m.fs, 'the original JPEG is the folder picture: cover.jpg next to the track, atomically')
    expect(not [p for p in m.fs if p.startswith(ART_DIR) and p.endswith('pick.src')], 'the download file is removed')
    m.call(PSYMS['pn_art_full_drop'], count=100000)
    expect(f'{ART_DIR}/full.jpg' not in m.fs and fn(m, 'pn_art_full_path', 0, buf, 200) == 0, 'pn_art_full_drop removes the held picture')
    # a pick of a cover whose larger picture was not fetched downloads it (and one of another cover than the fetched one does too)
    m.thread = None
    fn(m, 'pn_art_fetch', 1); PCN.work(m, m.thread)
    n2 = len(site.reqs)
    m.thread = None
    fn(m, 'pn_art_pick', 2, m.cstr(folder), key0, 0); PCN.work(m, m.thread)
    expect(site.urls()[n2:] == [site.urls()[4].replace('100x100bb', '600x600bb')] and fn(m, 'pn_pick_code') == 0, 'a pick of a cover other than the fetched one downloads its own picture')
    expect(fn(m, 'pn_art_full_path', 1, buf, 200) == 0, 'and the fetched picture is dropped (the held one is of the cover the fetch was for, and that was replaced)')
    # an existing folder picture is replaced (stock reads folder.jpg before cover.jpg); an existing folder.png is left alone
    site = Site()
    m = machine(site=site)
    m.dirs.update({folder, COVERS})
    m.fs[f'{folder}/folder.jpg'] = b'old'; m.fs[f'{folder}/cover.jpg'] = b'older'
    r, th = start(m); PCN.work(m, th)
    r = fn(m, 'pn_art_pick', 4, m.cstr(folder), key0, 0); PCN.work(m, m.thread)
    expect(site.urls()[-1] == site.urls()[6].replace('250x250-', '500x500-') and m.fs[f'{folder}/folder.jpg'] == JPG and m.fs[f'{folder}/cover.jpg'] == b'older', 'Deezer\'s cover: its 500 px picture; the existing folder.jpg (the one stock reads first) is replaced, cover.jpg untouched')
    expect(f'{COVERS}/r{key0:08x}-168.jpg' in m.fs and f'{COVERS}/{0:08x}-168.jpg' not in m.fs, 'a zero key is no key: one cache file')
    # no folder: cache only; the card root is never made a folder
    site = Site(); m = machine(site=site); m.dirs.add(COVERS)
    r, th = start(m); PCN.work(m, th)
    fn(m, 'pn_art_pick', 1, 0, key0, 0); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == 0 and f'{COVERS}/r{key0:08x}-168.jpg' in m.fs and not [p for p in m.fs if p.endswith(('cover.jpg', 'folder.jpg'))], 'no folder given: the cache only')
    # failures: download fails, not a picture, cache cannot be written
    for label, bad, code in (('a download that fails', {'rc': 22, 'code': 404}, PN['NET']), ('an answer that is not a picture', {'body': b'<html>x</html>'}, PN['NOTFEED'])):
        site = Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': lambda u, o, bad=bad: bad if '600x600bb' in u else {'body': JPG}})
        m = machine(site=site); m.dirs.update({folder, COVERS})
        r, th = start(m); PCN.work(m, th)
        fn(m, 'pn_art_pick', 0, m.cstr(folder), key0, 0); PCN.work(m, m.thread)
        expect(fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == code and not [p for p in m.fs if p.startswith(COVERS)] and f'{folder}/cover.jpg' not in m.fs, f'{label}: code {code}, nothing written')
        m.thread = None
        fn(m, 'pn_art_fetch', 0); PCN.work(m, m.thread)
        expect(fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == code and fn(m, 'pn_art_full_path', 0, m.alloc(200), 200) == 0 and f'{ART_DIR}/full.jpg' not in m.fs and f'{ART_DIR}/pick.src' not in m.fs,
               f'{label}: a fetch says {code} too and holds nothing')
    site = Site(); m = machine(site=site); m.dirs.update({folder, COVERS})
    r, th = start(m); PCN.work(m, th)
    m.fail = {('rename', f'{COVERS}/r{key0:08x}-168.jpg')}
    fn(m, 'pn_art_pick', 0, m.cstr(folder), key0, 0); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and f'{COVERS}/r{key0:08x}-168.jpg.tmp' not in m.fs and f'{folder}/cover.jpg' not in m.fs, 'a cache file that cannot be published: PN_STORAGE, no temp file, no folder picture')
    # a PNG answer: the fetch keeps it as full.png, the pick shrinks it into the cache and writes no folder picture
    import zlib, struct
    def png(w, h):
        raw = b''.join(b'\0' + bytes([(x * 7 + y) % 256, 100, 50]) * w for x, y in ((0, y) for y in range(h)))
        chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
    P = png(40, 40)
    site = Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': lambda u, o: {'body': P if '600x600bb' in u else JPG}})
    m = machine(site=site); m.dirs.update({folder, COVERS})
    r, th = start(m); PCN.work(m, th)
    m.thread = None
    fn(m, 'pn_art_fetch', 0); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == 0 and m.fs.get(f'{ART_DIR}/full.png') == P and fn(m, 'pn_art_full_path', 0, buf, 200) == 1 and m.read_cstr(buf) == f'{ART_DIR}/full.png', 'a PNG answer is held as full.png')
    m.thread = None
    fn(m, 'pn_art_pick', 0, m.cstr(folder), key0, 0); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == 0 and f'{COVERS}/r{key0:08x}-168.jpg' in m.fs and f'{folder}/cover.jpg' not in m.fs, 'and picked into the cache only (no folder picture of a PNG)')
    # a cancelled fetch holds nothing
    site = Site(); m = machine(site=site); m.dirs.update({folder, COVERS})
    r, th = start(m); PCN.work(m, th)
    m.thread = None
    fn(m, 'pn_art_fetch', 0)
    PCS.cancel(m)
    PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == PN['CANCELLED'] and fn(m, 'pn_art_full_path', 0, buf, 200) == 0 and fn(m, 'pn_job_busy') == 0, 'a cancelled fetch: PN_CANCELLED, no picture held')
    # a pick and a fetch need their guards and a thumbnail that is there
    m = machine(site=Site())
    r, th = start(m); PCN.work(m, th)
    m.wifi = -1
    expect(fn(m, 'pn_art_pick', 0, 0, key0, 0) == PN['NOWIFI'] and fn(m, 'pn_art_fetch', 0) == PN['NOWIFI'] and fn(m, 'pn_pick_state') == 0, 'no Wi-Fi: PN_NOWIFI, no worker')
    m.wifi = 2
    expect(fn(m, 'pn_art_pick', 99, 0, key0, 0) == PN['NOFEED'] and fn(m, 'pn_art_pick', -1, 0, key0, 0) == PN['NOFEED'] and fn(m, 'pn_art_pick', 0, 0, 0, 0) == PN['NOFEED'] and fn(m, 'pn_art_fetch', 99) == PN['NOFEED'], 'a cover that is not there, or no key: refused')
    site = Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': {'rc': 22, 'code': 404}})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    expect(fn(m, 'pn_art_pick', 0, 0, key0, 0) == PN['NOFEED'] and fn(m, 'pn_art_fetch', 0) == PN['NOFEED'], 'a cover whose thumbnail failed cannot be picked or fetched (the user never saw it)')
    # a new lookup resets the pick and the held picture
    m = machine(site=Site()); m.dirs.update({folder, COVERS})
    r, th = start(m); PCN.work(m, th)
    m.thread = None
    fn(m, 'pn_art_fetch', 0); PCN.work(m, m.thread)
    r, th = start(m)
    expect(fn(m, 'pn_pick_state') == 0 and f'{ART_DIR}/full.jpg' not in m.fs, 'a new lookup forgets the earlier pick and removes the held picture')


def rebuild_tests(ctx):
    """Rebuild Covers (covercache.c build_art, CC_REBUILD) leaves an album with a .pick marker alone; an album without one is extracted again."""
    expect = ctx.expect
    src = open(os.path.join(ROOT, 'patch', 'covercache.c')).read()
    i = src.index('static void build_art')
    body = src[i:src.index('static void *cc_worker')]
    expect('cc_path(pick, sizeof pick, j->key, ".pick")' in body and body.index('".pick"') < body.index('art_make('), 'build_art looks for the .pick marker before it extracts')
    expect('if (!access(pick, F_OK) && !access(dst, F_OK))\n        return;' in body, 'a marker with its cache file present ends the job: no extraction, no marker, no replacement (a marker whose cache file is gone does not)')


def sleeps(m): return m.slept


def busy_tests(ctx):
    """No automatic retry: a busy answer (HTTP 503 or 429) is PN_OVERLOAD at once, from one request, with no waiting."""
    expect = ctx.expect
    BUSY = {'rc': 22, 'code': 503}
    for label, code in (('503', 503), ('429', 429)):
        site = Site(**{LRCLIB: {'rc': 22, 'code': code}})
        m = machine(site=site)
        r, th = start(m); PCN.work(m, th)
        st = state(m)
        lr = [u for u in site.urls() if u.startswith(LRCLIB)]
        expect(st['lcode'] == PN['OVERLOAD'] and st['lstate'] == 1 and st['lcount'] == 0 and len(lr) == 1 and lr[0].startswith(LRCLIB + 'get?') and not sleeps(m) and st['code'] == 0 and st['count'] == 7 and st['busy'] == 0,
               f'HTTP {label} from get: one request, no search, no waiting, PN_OVERLOAD, the covers unaffected ({len(lr)} requests, {sleeps(m)}, {st})')
    # a get that fails otherwise does not skip the search
    for label, res in (('HTTP 500', {'rc': 22, 'code': 500}), ('HTTP 404', {'rc': 22, 'code': 404})):
        site = Site(**{LRCLIB + 'get?': res, LRCLIB + 'search?': {'body': b'[]'}})
        m = machine(site=site)
        r, th = start(m); PCN.work(m, th)
        lr = [u for u in site.urls() if u.startswith(LRCLIB)]
        expect(len(lr) == 2 and lr[1].startswith(LRCLIB + 'search?') and not sleeps(m), f'{label} from get: the search still runs, no waiting')
    # a busy search after an answered get: the get's candidates stay, no error
    site = Site(**{LRCLIB + 'search?': BUSY})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['lcode'] == 0 and st['lcount'] >= 1 and not sleeps(m), f'a busy search after a good get: the candidates of the get are offered ({st})')
    # Cancel (Back) while the busy answer is on its way: PN_CANCELLED, no further request, the worker ends
    site = Site(**{LRCLIB: lambda u, o: (m.nested(PSYMS['pn_cancel'], 3 << 5), BUSY)[1]})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    lr = [u for u in site.urls() if u.startswith(LRCLIB)]
    expect(len(lr) == 1 and st['lcode'] == PN['CANCELLED'] and st['busy'] == 0 and st['lstate'] == 1, f'Cancel with a busy get: one request, PN_CANCELLED, the worker ended ({len(lr)} requests, {st})')
    # covers: a busy store still lets Deezer run; busy is reported only when neither gave an answer
    site = Site(**{ITUNES: BUSY})
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    st = state(m)
    expect(st['code'] == 0 and st['count'] == 3 and any(u.startswith(DEEZER) for u in site.urls()) and not sleeps(m), f'only the store busy: Deezer\'s covers are offered, no error, one request to the store ({st})')
    for label, over in (('503', {ITUNES: BUSY, DEEZER: BUSY}), ('429', {ITUNES: {'rc': 22, 'code': 429}, DEEZER: {'rc': 22, 'code': 429}})):
        site = Site(**over)
        m = machine(site=site)
        r, th = start(m); PCN.work(m, th)
        st = state(m)
        cv = [u for u in site.urls() if u.startswith(ITUNES) or u.startswith(DEEZER)]
        expect(st['code'] == PN['OVERLOAD'] and st['count'] == 0 and st['state'] == 3 and st['lcode'] == 0 and len(cv) == 2 and not sleeps(m), f'covers, both {label}: PN_OVERLOAD from one request each, the lyrics ran ({st})')
    # one part again: pn_art_again looks up only that part, with the query of the last pn_art; the other part's results stay
    site = Site()
    m = machine(site=site)
    r, th = start(m); PCN.work(m, th)
    n0, files0 = len(site.reqs), sorted(p for p in m.fs if p.startswith(ART_DIR))
    m.thread = None
    r = fn(m, 'pn_art_again', 2)
    expect(r == 0 and m.thread and m.thread[0] == PSYMS['pn_amain'] and state(m)['lstate'] == 0 and state(m)['state'] == 3 and state(m)['count'] == 7 and fn(m, 'pn_art_again', 1) == PN['BUSY'], 'the lyrics again: a worker starts, the lyrics wait to be answered, the covers stay (and a second job is refused)')
    PCN.work(m, m.thread)
    urls = [u for u, _ in site.reqs[n0:]]
    st = state(m)
    expect(urls == [LRCLIB + 'get?track_name=Karma%20Police&artist_name=Radiohead&album_name=OK%20Computer&duration=261', LRCLIB + 'search?track_name=Karma%20Police&artist_name=Radiohead'] and st['lcode'] == 0 and st['lcount'] == 3 and st['count'] == 7,
           f'only LRCLIB is asked, with the same query; three candidates again, the seven covers still held ({urls})')
    expect(sorted(p for p in m.fs if p.startswith(ART_DIR)) == files0, 'the same files: the thumbnails stayed, the texts were written again')
    n0 = len(site.reqs); m.thread = None
    r = fn(m, 'pn_art_again', 1)
    st = state(m)
    expect(r == 0 and st['state'] == 1 and st['count'] == 0 and st['lstate'] == 1 and st['lcount'] == 3, f'the covers again: they restart, the lyrics stay ({st})')
    PCN.work(m, m.thread)
    urls = [u for u, _ in site.reqs[n0:]]
    st = state(m)
    expect(urls[0].startswith(ITUNES) and urls[1].startswith(DEEZER) and not [u for u in urls if u.startswith(LRCLIB)] and st['count'] == 7 and st['lcount'] == 3 and ltext(m, 0) is not None, f'only the covers\' services and the thumbnails are asked ({len(urls)} requests); the lyrics are untouched')
    expect(fn(m, 'pn_art_again', 0) == PN['MEM'] and fn(m, 'pn_art_again', 3) == PN['MEM'], 'not a part: refused')
    m = machine(site=Site(), wifi=-1)
    expect(fn(m, 'pn_art_again', 2) == PN['NOWIFI'], 'the guards run for a part too')


DEEZER_ARTIST = 'https://api.deezer.com/search/artist?limit=25&q='
AP = '/mnt/mmc/.m1plus/artists'
NETEASE_ARTIST = 'https://music.163.com/api/search/get?type=100&limit=10&s='
NETEASE_NONE = b'{"result":{"hasMore":false,"artistCount":0},"code":200}'   # NetEase's answer when it finds nothing: the scripted server's, unless a test says otherwise


def artist_tests(ctx):
    """Find Artist Photo (pn_artist, pn_artist_pick, pj_deezer_artists, ap_pick; docs/modules/onlineart.md "Artist photos"): Deezer's artist search (NetEase finds nothing here; both services: source_tests), the artists that have a picture of their own with the most followed
    first, and the picked picture as the artist's photo in the artists cache with its .pick marker."""
    expect = ctx.expect
    raw = data('deezer_artist.json')
    d = json.loads(raw)['data']
    # the extractor against json.loads
    m = Machine()
    for base in (0x30000000, 0x30100000): m.u.mem_map(base, 0x40000)

    def call(name, text, mx=8):
        src, dst = 0x30000000 + 0x40000 - len(text), 0x30100000
        m.u.mem_write(src, text)
        n = fn(m, name, src, len(text), dst, mx)
        n = n - (1 << 32) if n >= 1 << 31 else n
        return n, Rec.parse(bytes(m.u.mem_read(dst, mx * Rec.SIZE)), max(n, 0))
    n, got = call('pj_deezer_artists', raw)
    expect(n == 6 and got == [(r['nb_fan'], r['name'], '', r['name'], r['picture_medium'] or '') for r in d], f'Deezer\'s artist answer: nb_fan as the id, the name (in the feed field too, where it is not cut), no author, picture_medium ({n})')
    long = [{'name': nm, 'nb_fan': 1, 'picture_medium': None} for nm in ('n' * 79, 'n' * 80, '汉' * 27, 'n' * 319, 'n' * 320)]
    lgot = call('pj_deezer_artists', json.dumps({'data': long}).encode())[1]
    expect([(g[1], g[3]) for g in lgot] == [('n' * 79,) * 2, ('n' * 79, 'n' * 80), ('汉' * 26, '汉' * 27), ('n' * 79, 'n' * 319)], f'a long name: cut at 79 bytes on a character as the name, whole beside it; one of 320 bytes is no artist ({len(lgot)})')
    expect(got[0][1] == '陈奕迅' and got[4][1] == 'Eason & Friends "Duo"' and got[5][4] == '', 'CJK, & and an escaped quote as they are; a null picture is empty')
    expect(call('pj_deezer_artists', data('itunes_album.json'))[0] == -1 and call('pj_deezer_artists', b'{"data":[],"total":0}')[0] == 0, 'the store\'s answer is not one; an empty "data" is 0 artists')
    expect([g[1] for g in call('pj_deezer_artists', data('deezer_album.json'))[1]] == [], 'an album answer has no artist names at its top level: nothing is kept')

    # the job: Deezer's request (NetEase's finds nothing), the artists with a picture, the most followed first
    def site_for(**over):
        return Site(**{DEEZER_ARTIST: {'body': raw}, **over})

    def begin(m, name='陈奕迅'):
        m.thread = None
        return fn(m, 'pn_artist', m.cstr(name)), m.thread
    def cmachine(site):
        """The lookup's machine on the cover tests' card machine (ftell over a file's bytes: ap_make sizes its source), set up as machine() does."""
        m = sibling('coverart').CM()
        m.dirs.update({PCN.ROOT_DIR, '/mnt/mmc/.m1plus', '/mnt/mmc'})
        m.present.add(PCN.CA)
        m.curl_site = site
        m.jinit()
        m.slept = []
        m.on_sleep = lambda k, m=m: m.slept.append(1)
        return m
    site = site_for()
    m = cmachine(site)
    r, th = begin(m)
    st = state(m)
    expect(r == 0 and th and th[0] == PSYMS['pn_amain'] and st['state'] == 1 and st['busy'] == 1, f'pn_artist starts the lookup\'s worker ({st})')
    expect(begin(m)[0] == PN['BUSY'] and start(m)[0] == PN['BUSY'], 'a second lookup while it runs: PN_BUSY')
    PCN.work(m, th)
    st = state(m)
    urls = site.urls()
    want = [d[0], d[1], d[4]]   # the entry of the very name (178 followers), then the others: 8879 twice (the service's order between them); the blank, the repeated picture and the null one are not offered
    expect(urls[:2] == [DEEZER_ARTIST + enc('陈奕迅'), NETEASE_ARTIST + enc('陈奕迅')] and urls[2:] == [r['picture_medium'] for r in want], f'Deezer\'s artist search with the name URL-encoded, NetEase\'s, then the thumbnails of the artists offered: {urls}')
    expect(not [u for u in urls if u.startswith((ITUNES, LRCLIB, DEEZER))], 'no album search and no lyrics request')
    expect(st['state'] == 3 and st['code'] == 0 and st['count'] == 3 and st['busy'] == 0, f'three photos: an artist with the service\'s blank picture (an empty picture id), a picture already offered and a null picture are left out ({st})')
    expect([info(m, i) for i in range(3)] == [(r['name'], '', 1) for r in want], f'the very name first, then the most followed, equal counts in the service\'s order; the name, no second line, the source Deezer: {[info(m, i)[0] for i in range(3)]}')
    expect([thumb_path(m, i) for i in range(3)] == [f'{ART_DIR}/a{i}.jpg' for i in range(3)], 'the thumbnails are the lookup\'s a<n>.jpg')
    for u, o in site.reqs:
        expect(o[10065] == PCN.CA and o[52] == 1 and 64 not in o and 81 not in o and o[10018].startswith('M1PlusMusic/'), f'{u[:40]}: the CA bundle, verification on, the app\'s user agent')
    # a loose answer: the entries of the very name first, at most PN_ARTIST_OTHER others, PN_ARTIST_MAX in all
    def offered(asked, names):
        rows = [{'name': nm, 'nb_fan': fans, 'picture_medium': f'https://cdn-images.dzcdn.net/images/artist/{i:032x}/250x250-000000-80-0-0.jpg'} for i, (nm, fans) in enumerate(names)]
        mm = cmachine(site_for(**{DEEZER_ARTIST: {'body': json.dumps({'data': rows}).encode()}}))
        PCN.work(mm, begin(mm, asked)[1])
        return [info(mm, i)[0] for i in range(state(mm)['count'])]
    loose = [(f'Beatles Tribute {i}', 9000 - i) for i in range(6)]
    expect(offered('The Beatles', loose) == [nm for nm, _ in loose[:4]], 'no entry of the very name: the four most followed of the others')
    got = offered('The Beatles', loose[:3] + [('beatles', 5), (' THE BEATLES ', 7), ('The Beatles', 6)] + loose[3:])
    expect(got == [' THE BEATLES ', 'The Beatles', 'beatles'] + [nm for nm, _ in loose[:3]], f'the very name (the case, the spaces around it and "The " apart) before the more followed others, six in all: {got}')
    got = offered('Beatles', [(f'Other {i}', 99) for i in range(3)] + [('The Beatles', 10 + i) for i in range(8)])
    expect(got == ['The Beatles'] * 6, f'six entries of the very name leave no room for the others: {got}')
    for nm in ('n' * 79, 'n' * 80, '汉' * 27, 'n' * 95, 'The ' + 'n' * 100):   # the name kept is 79 bytes and the query 95: the match is on the whole names
        got = offered(nm.upper(), loose[:5] + [(nm, 1)])
        expect(got[0] == nm.encode()[:79].decode(errors='ignore') and len(got) == 5, f'a name of {len(nm.encode())} bytes is still the very name: first, before four more followed others ({got[0][:12]}, {len(got)})')
    # Try Again: the covers part only, the same search
    expect(fn(m, 'pn_art_again', 2) == PN['MEM'], 'there is no lyrics part to ask again')
    n0 = len(site.reqs)
    m.thread = None
    r = fn(m, 'pn_art_again', 1); PCN.work(m, m.thread)
    expect(r == 0 and site.urls()[n0] == DEEZER_ARTIST + enc('陈奕迅') and state(m)['count'] == 3, 'pn_art_again(covers) asks the artist search again')
    # the pick: the 500 px picture into the artists cache, with the marker
    key = fn(m, 'ap_key', m.cstr('陈奕迅'))
    ep0 = fn(m, 'ap_epoch')
    expect(key and fn(m, 'ap_picked', key) == 0 and fn(m, 'pn_artist_pick', 0, 0) == PN['NOFEED'] and fn(m, 'pn_artist_pick', 7, key) == PN['NOFEED'], 'no key, or a photo that is not there: refused')
    m.thread = None
    fn(m, 'pn_art_fetch', 0); PCN.work(m, m.thread)
    big = want[0]['picture_medium'].replace('250x250-', '500x500-')
    expect(site.urls()[-1] == big and fn(m, 'pn_pick_code') == 0 and not [p for p in m.fs if p.startswith(AP)], f'the confirmation\'s larger picture is the 500 px one; a fetch writes nothing to the artists cache: {site.urls()[-1][-40:]}')
    n1 = len(site.reqs)
    m.thread = None
    r = fn(m, 'pn_artist_pick', 0, key)
    expect(r == 0 and m.thread and m.thread[0] == PSYMS['pn_kmain'] and fn(m, 'pn_pick_state') == 1, 'the pick starts the worker')
    PCN.work(m, m.thread)
    f168, f44 = f'{AP}/a{key:08x}-168.jpg', f'{AP}/a{key:08x}-44.jpg'
    expect(len(site.reqs) == n1 and fn(m, 'pn_pick_state') == 2 and fn(m, 'pn_pick_code') == 0, 'the picture already held is used: no request, OK')
    expect(all(p in m.fs and m.fs[p][:2] == b'\xff\xd8' for p in (f168, f44)) and f'{AP}/a{key:08x}.pick' in m.fs, 'both cache files of the artist are JPEGs and the .pick marker is beside them')
    expect(sorted(p for p in m.fs if p.startswith(AP)) == sorted([f168, f44, f'{AP}/a{key:08x}.pick']), f'nothing else: no .src (the source was a scratch file), no temp file ({sorted(p for p in m.fs if p.startswith(AP))})')
    expect(fn(m, 'ap_picked', key) == 1 and fn(m, 'ap_epoch') == ep0 + 1 and not [p for p in m.fs if p.startswith(COVERS)], 'ap_picked says so, the epoch moved (the pages read the photo again), the album cover cache is untouched')
    # a second pick replaces the first; one that cannot be written leaves it
    old = m.fs[f168]
    m.fail = {('rename', f168)}
    m.thread = None
    fn(m, 'pn_artist_pick', 1, key); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and m.fs[f168] == old and fn(m, 'ap_picked', key) == 1 and fn(m, 'ap_epoch') == ep0 + 1 and not [p for p in m.fs if p.endswith('.tmp')],
           'a photo that cannot be published: PN_STORAGE, the old photo and its marker stay, no temp file')
    expect(site.urls()[-1] == want[1]['picture_medium'].replace('250x250-', '500x500-'), 'a pick of another photo than the fetched one downloads its own 500 px picture')
    m.fail = set()
    m.thread = None
    fn(m, 'pn_artist_pick', 1, key); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == 0 and fn(m, 'ap_epoch') == ep0 + 2 and f168 in m.fs, 'the next pick replaces it')
    # the save is whole or not at all: a -44 file that cannot be published leaves BOTH old files (the -168 file was already replaced when it failed), and a marker that cannot be written is no pick
    old168, old44 = m.fs[f168], m.fs[f44]
    m.fail = {('rename', f44)}
    m.thread = None
    fn(m, 'pn_artist_pick', 0, key); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and m.fs[f168] == old168 and m.fs[f44] == old44 and fn(m, 'ap_picked', key) == 1 and fn(m, 'ap_epoch') == ep0 + 2,
           'the list file cannot be published: PN_STORAGE, the header photo is the old one again, the epoch did not move')
    expect(sorted(p for p in m.fs if p.startswith(AP)) == sorted([f168, f44, f'{AP}/a{key:08x}.pick']), f'and nothing is left behind (no set-aside or temporary file): {sorted(p for p in m.fs if p.startswith(AP))}')
    k2 = fn(m, 'ap_key', m.cstr('Somebody Else'))
    m.fail = {('fopen', f'{AP}/a{k2:08x}.pick')}
    m.thread = None
    fn(m, 'pn_artist_pick', 0, k2); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and not [p for p in m.fs if p.startswith(f'{AP}/a{k2:08x}')] and fn(m, 'ap_picked', k2) == 0 and fn(m, 'ap_epoch') == ep0 + 2,
           f'the marker cannot be written: PN_STORAGE, no photo is saved without it, the epoch did not move ({sorted(p for p in m.fs if p.startswith(AP))})')
    m.fs[f'{AP}/a{k2:08x}-168.jpg'] = b'auto168'; m.fs[f'{AP}/a{k2:08x}-44.jpg'] = b'auto44'; m.fail = {('rename', f'{AP}/a{k2:08x}-44.jpg')}
    m.thread = None
    fn(m, 'pn_artist_pick', 0, k2); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and m.fs[f'{AP}/a{k2:08x}-168.jpg'] == b'auto168' and m.fs[f'{AP}/a{k2:08x}-44.jpg'] == b'auto44' and f'{AP}/a{k2:08x}.pick' not in m.fs,
           'a first pick over an automatic photo that fails: the automatic photo stays and gets no marker')
    m.fail = {('rename', f'{AP}/a{k2:08x}-44.jpg'), ('open', f'{AP}/a{k2:08x}-168.jpg.old')}   # ... and the old header cannot be written back either
    m.thread = None
    fn(m, 'pn_artist_pick', 0, k2); PCN.work(m, m.thread)
    expect(fn(m, 'pn_pick_code') == PN['STORAGE'] and m.fs.get(f'{AP}/a{k2:08x}-168.jpg', b'')[:2] == b'\xff\xd8' and m.fs[f'{AP}/a{k2:08x}-44.jpg'] == b'auto44' and fn(m, 'ap_epoch') == ep0 + 2,
           'the old header cannot be written back: the header path still names a whole photo (the new one), the list file is the old one, the save failed')
    expect(sorted(p for p in m.fs if p.startswith(f'{AP}/a{k2:08x}')) == [f'{AP}/a{k2:08x}-168.jpg', f'{AP}/a{k2:08x}-44.jpg'], f'and nothing is left behind, no marker: {sorted(p for p in m.fs if p.startswith(AP))}')
    m.fail = set()
    # an album lookup after an artist's is the album's again
    n2 = len(site.reqs)
    r, th = start(m); PCN.work(m, th)
    expect(site.urls()[n2].startswith(ITUNES) and state(m)['lstate'] == 1, 'pn_art after pn_artist asks the store, Deezer\'s albums and the lyrics as ever')
    # nothing found, failures
    site = Site(**{DEEZER_ARTIST: {'body': b'{"data":[],"total":0}'}})
    m = machine(site=site)
    r, th = begin(m, 'Nobody'); PCN.work(m, th)
    expect(state(m)['state'] == 3 and state(m)['code'] == 0 and state(m)['count'] == 0 and len(site.reqs) == 2, 'no artist: OK with no photos, a request to each service')
    for label, bad, code in (('a busy service', {'rc': 22, 'code': 503}, PN['OVERLOAD']), ('an answer that is not the service\'s', {'body': b'<html>'}, PN['HTTP']), ('no connection', {'rc': 7}, PN['NET'])):
        site = Site(**{DEEZER_ARTIST: bad, NETEASE_ARTIST: bad})
        m = machine(site=site)
        r, th = begin(m); PCN.work(m, th)
        expect(state(m)['state'] == 3 and state(m)['code'] == code and state(m)['count'] == 0 and len(site.reqs) == 2, f'{label} (both services): code {code} ({state(m)["code"]})')
    # the name is URL-encoded like any query field
    site = site_for()
    m = machine(site=site)
    r, th = begin(m, 'Sigur Rós & Co'); PCN.work(m, th)
    expect(site.urls()[0] == DEEZER_ARTIST + 'Sigur%20R%C3%B3s%20%26%20Co', f'space, accent and & are escaped: {site.urls()[0]}')


def source_tests(ctx):
    """Find Artist Photo's two services (pj_netease_artists, pn_artist; docs/modules/onlineart.md "Artist photos"): NetEase's answer, and what is offered from Deezer and NetEase together and when one of them fails."""
    expect = ctx.expect
    THUMB, BLANK = DEFS['PN_NETEASE_THUMB'], 'https://p1.music.126.net/6y-UleORITEDbvrOLV0Q8A==' + DEFS['PN_NETEASE_BLANK']
    expect(NETEASE_ARTIST == DEFS['PN_ART_NETEASE_ARTIST'] and DEFS['PN_ARTIST_NETEASE'] == 2 and DEFS['PN_NETEASE_MAX'] == 10,
           'NetEase\'s artist search; at most two of NetEase\'s ten are offered')
    # the extractor against json.loads
    raw = data('netease_artist.json')
    d = json.loads(raw)['result']['artists']
    m = Machine()
    for base in (0x30000000, 0x30100000): m.u.mem_map(base, 0x40000)

    def call(text, mx=10):
        src, dst = 0x30000000 + 0x40000 - len(text), 0x30100000
        m.u.mem_write(src, text)
        n = fn(m, 'pj_netease_artists', src, len(text), dst, mx)
        n = n - (1 << 32) if n >= 1 << 31 else n
        return n, Rec.parse(bytes(m.u.mem_read(dst, mx * Rec.SIZE)), max(n, 0))
    n, got = call(raw)
    expect(n == len(d) == 10 and got == [(r['fansSize'], r['name'], '', r['name'], r['img1v1Url']) for r in d], f'NetEase\'s answer: fansSize as the id, the name (in the feed field too), no author, img1v1Url ({n})')
    expect(got[0][1] == 'The Beatles' and len([g for g in got if g[4].endswith(DEFS['PN_NETEASE_BLANK'])]) == 5 and [r['picUrl'] for r in d].count(None) == 5, 'the fixture has artists with the service\'s blank picture and a null picUrl')
    expect(call(raw, 3)[0] == 3, 'no more than asked for')
    expect(call(b'{"result":{"hasMore":false,"artistCount":0},"code":200}')[0] == 0, 'a "result" with no "artists" (nothing found): 0 artists')
    expect(call(b'{"code":-460,"msg":"Cheating"}')[0] == -1 and call(data('deezer_artist.json'))[0] == -1 and call(b'<html>')[0] == -1, 'an error answer, Deezer\'s answer and a page are not one')
    expect(call(b'{"artists":[{"name":"x"}],"result":{"artists":[{"name":"y"}]}}')[1][0][1] == 'y', 'the "artists" of "result", not one beside it')
    long = [{'name': nm, 'fansSize': 1, 'img1v1Url': None} for nm in ('n' * 80, '汉' * 27, 'n' * 320)]
    lgot = call(json.dumps({'result': {'artists': long}}).encode())[1]
    expect([(g[1], g[3]) for g in lgot] == [('n' * 79, 'n' * 80), ('汉' * 26, '汉' * 27)], f'a long name: cut as the name, whole beside it, as Deezer\'s ({len(lgot)})')

    # the job
    def dz(names):
        return json.dumps({'data': [{'name': nm, 'nb_fan': fans, 'picture_medium': f'https://cdn-images.dzcdn.net/images/artist/{i:032x}/250x250-000000-80-0-0.jpg'} for i, (nm, fans) in enumerate(names)]}).encode()

    def ne(names):
        """(name, picture or None for the service's blank[, picUrl])"""
        rows = []
        for i, t in enumerate(names):
            rows.append({'id': i, 'name': t[0], 'img1v1Url': BLANK if t[1] is None else t[1], 'picUrl': t[2] if len(t) > 2 else None, 'fansSize': 100 - i})
        return json.dumps({'result': {'artists': rows, 'artistCount': len(rows)}, 'code': 200}).encode()

    def pic(k, host='https'): return f'{host}://p1.music.126.net/k{k}==/{1000 + k}.jpg'

    def run(asked, dzr, ner):
        """The lookup for asked with the two services' answers (bytes, or a reply dict): the machine, the site."""
        site = Site(**{DEEZER_ARTIST: dzr if isinstance(dzr, dict) else {'body': dzr}, NETEASE_ARTIST: ner if isinstance(ner, dict) else {'body': ner}})
        mm = machine(site=site)
        mm.thread = None
        fn(mm, 'pn_artist', mm.cstr(asked)); PCN.work(mm, mm.thread)
        return mm, site

    def offered(mm): return [(info(mm, i)[0], info(mm, i)[2]) for i in range(state(mm)['count'])]
    D, N = PN_SRC['DEEZER'], PN_SRC['NETEASE']
    loose = [(f'Tribute {i}', 9000 - i) for i in range(6)]
    mm, site = run('The Beatles', dz(loose[:2] + [('The Beatles', 5), ('beatles', 9)] + loose[2:]), ne([('The Beatles', pic(1)), ('Paul', pic(2)), ('the beatles', pic(3)), ('THE BEATLES', pic(4))]))
    urls = site.urls()
    expect(urls[:2] == [DEEZER_ARTIST + enc('The Beatles'), NETEASE_ARTIST + enc('The Beatles')], f'both services: Deezer\'s artist search, then NetEase\'s, the name URL-encoded: {urls[:2]}')
    got = offered(mm)
    expect(got == [('beatles', D), ('The Beatles', D), ('The Beatles', N), ('the beatles', N)] + [(nm, D) for nm, _ in loose[:2]],
           f'Deezer\'s of the very name, NetEase\'s of the very name (two at most, in its order), then Deezer\'s others, six in all: {got}')
    expect(urls[4:6] == [pic(1) + THUMB, pic(3) + THUMB] and len(urls) == 8, f'NetEase\'s thumbnail is the square picture at 250 px: {urls[4:6]}')
    expect(state(mm)['code'] == 0 and [thumb_path(mm, i) for i in range(6)] == [f'{ART_DIR}/a{i}.jpg' for i in range(6)], 'OK; every photo has its thumbnail')
    mm.thread = None
    fn(mm, 'pn_art_fetch', 2); PCN.work(mm, mm.thread)
    expect(site.urls()[-1] == pic(1) + '?param=500y500' and fn(mm, 'pn_pick_code') == 0, f'NetEase\'s larger picture is the 500 px one: {site.urls()[-1]}')
    # NetEase has no entry of the very name: its first one alone
    mm, site = run('BTS', dz([('BTS', 9)]), ne([('BTS (防弹少年团)', pic(1)), ('Jung Kook', pic(2)), ('SUGA', pic(3))]))
    expect(offered(mm) == [('BTS', D), ('BTS (防弹少年团)', N)], f'no NetEase entry of the very name: its first one (the best match), not the people after it: {offered(mm)}')
    mm, site = run('BTS', dz([('BTS', 9)]), ne([('BTS (防弹少年团)', None), ('Jung Kook', pic(2))]))
    expect(offered(mm) == [('BTS', D)], f'... and none when the first has the service\'s blank picture: {offered(mm)}')
    mm, site = run('Mayday', dz([]), ne([('Mayday', None, pic(7)), ('mayday', None), ('MAYDAY', pic(8, 'http'))]))
    expect(offered(mm) == [('Mayday', N), ('MAYDAY', N)] and site.urls()[2:] == [pic(7) + THUMB, pic(8, 'http') + THUMB],
           f'a blank square picture: the other picture (picUrl) is used; an entry with neither is left out; an http address is taken: {offered(mm)}')
    # room is kept for NetEase's; with none of its own, Deezer's fill the page
    six = [('The Beatles', 50 - i) for i in range(8)]
    mm, site = run('Beatles', dz(six), ne([('Beatles', pic(1)), ('The Beatles', pic(2))]))
    expect(offered(mm) == [('The Beatles', D)] * 4 + [('Beatles', N), ('The Beatles', N)], f'eight Deezer entries of the very name: four of them, then NetEase\'s two: {offered(mm)}')
    mm, site = run('Beatles', dz(six), ne([]))
    expect(offered(mm) == [('The Beatles', D)] * 6 and state(mm)['code'] == 0, 'NetEase finds nothing: Deezer\'s six')
    # one service fails: the other's photos, no error
    for label, bad in (('busy', {'rc': 22, 'code': 503}), ('not its answer', {'body': b'{"code":-460,"msg":"Cheating"}'}), ('unreachable', {'rc': 7})):
        mm, site = run('The Beatles', dz([('The Beatles', 5)]), bad)
        expect(offered(mm) == [('The Beatles', D)] and state(mm)['code'] == 0 and len(site.reqs) == 3, f'NetEase {label}: Deezer\'s photos, OK ({state(mm)["code"]})')
        mm, site = run('The Beatles', bad if 'rc' in bad else {'body': b'<html>'}, ne([('The Beatles', pic(1))]))
        expect(offered(mm) == [('The Beatles', N)] and state(mm)['code'] == 0 and len(site.reqs) == 3, f'Deezer {label}: NetEase\'s photo, OK ({state(mm)["code"]})')
    mm, site = run('The Beatles', {'rc': 22, 'code': 503}, {'rc': 7})
    expect(state(mm)['code'] == PN['OVERLOAD'] and state(mm)['count'] == 0 and len(site.reqs) == 2, f'both fail: the first failure\'s code ({state(mm)["code"]})')
    mm, site = run('Nobody', dz([]), {'rc': 7})
    expect(state(mm)['code'] == 0 and state(mm)['count'] == 0, 'Deezer answers with no artist and NetEase fails: OK with no photos')
    for u, o in site.reqs:
        expect(o[10065] == PCN.CA and o[52] == 1 and o[10018].startswith('M1PlusMusic/'), 'NetEase is asked as the other services: the CA bundle, verification on, the app\'s user agent')
    # the real answer
    mm, site = run('The Beatles', dz([]), raw)
    expect(offered(mm) == [('The Beatles', N)] and site.urls()[2] == d[0]['img1v1Url'] + THUMB, f'the fixture: the one entry of the very name: {offered(mm)}')

SECTIONS = [json_tests, job_tests, lyrics_tests, failure_tests, busy_tests, cancel_tests, pick_tests, rebuild_tests, artist_tests, source_tests]

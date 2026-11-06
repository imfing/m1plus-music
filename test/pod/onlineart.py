"""Find Cover & Lyrics, the network side (patch/pcnet.c "Find Cover & Lyrics", patch/pcjson.c pj_deezer / pj_lrc_each, patch/covercache.c's .pick marker; docs/modules/onlineart.md): the three
services' answers taken apart (fixtures in test/data/onlineart, Python's json module as the oracle), the requests (URL-encoded UTF-8 with spaces, & and CJK; the libcurl options; the user agent
LRCLIB asks for), the order of the job (iTunes, Deezer, the thumbnails, LRCLIB's get and search), the lyrics candidates (the exact match first, the rest by the closeness of their length, repeats dropped, the cap,
their files), every failure, Cancel and the single-thread rule, the larger picture fetched for the confirmation and the picked cover (the larger picture's address, the cache files, the .pick marker,
the folder picture), a lyrics candidate's save, and Rebuild Covers leaving a picked cover alone."""
import importlib.util, json, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'test', 'data', 'onlineart')
SEARCH_DATA = os.path.join(ROOT, 'test', 'data', 'search')


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCS, PCJ = sibling('pcsearch'), sibling('pcjson')
PCN, fn = PCS.PCN, PCS.fn


def machine(*a, **kw):
    """The Podcasts tests' machine, writing down each second the worker sleeps (a wait is slept a second at a time: m.slept is a list of 1s)."""
    m = PCS.machine(*a, **kw)
    m.slept = []
    m.on_sleep = lambda k, m=m: m.slept.append(1)
    return m

PN = dict(PCN.PN, CANCELLED=12, NOFEED=17, NOLYRICS=18, OVERLOAD=19)
ART_DIR, COVERS = '/mnt/mmc/.m1plus/art', '/mnt/mmc/.m1plus/covers'
ITUNES = 'https://itunes.apple.com/search?media=music&entity=album&limit=8&term='
DEEZER = 'https://api.deezer.com/search/album?limit=8&q='
LRCLIB = 'https://lrclib.net/api/'
JPG = open(os.path.join(SEARCH_DATA, 'art100.jpg'), 'rb').read()
CACHE_SIZE = 192   # PV_SIZE: the cover cache file's longer side (pv_shrink; never upscaled)


def data(name): return open(os.path.join(DATA, name), 'rb').read()


def enc(s):
    from urllib.parse import quote
    return quote(s, safe='-_.~')


class Rec:
    """pj_result_t as the payload lays it out."""
    NAME, AUTHOR, URL, ART = 80, 56, 320, 160
    SIZE = 4 + NAME + AUTHOR + URL + ART

    @classmethod
    def parse(cls, raw, n):
        cs = lambda b: b.split(b'\0')[0].decode('utf-8')
        out = []
        for i in range(n):
            r = raw[i * cls.SIZE:(i + 1) * cls.SIZE]
            out.append((int.from_bytes(r[:4], 'little'), cs(r[4:84]), cs(r[84:140]), cs(r[140:460]), cs(r[460:])))
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
        if 'mzstatic' in url or 'dzcdn' in url: return {'body': JPG, 'chunk': 5500}
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
    site = Site(**{LRCLIB: lambda u, o: (m.nested(PSYMS['pn_cancel']), BUSY)[1]})
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


def run(ctx):
    for f in (json_tests, job_tests, lyrics_tests, failure_tests, busy_tests, cancel_tests, pick_tests, rebuild_tests): f(ctx)

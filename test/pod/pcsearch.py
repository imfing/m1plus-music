"""Podcast search, the worker side (patch/pcnet.c "Search", docs/modules/podcasts.md "Search"): what the field's text is (a search term, a feed address, an Apple Podcasts link), the request (the
store's URL with the term URL-encoded, the country a constant, the same libcurl options as a feed's), the answer taken apart by the extractor, the artwork fetched one by one, every failure,
the 96 KB cap, the single-thread rule and Cancel; the preview (a feed address, an Apple link's lookup, the held parser, the picture) and Subscribe against an import and its first refresh."""
import io, json, os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'test', 'data', 'search')


PCN = sibling('pcnet')
PN, CA, ROOT_DIR = dict(PCN.PN, CANCELLED=12, NOFEED=16), PCN.CA, PCN.ROOT_DIR
SDIR = '/mnt/mmc/.m1plus/podcasts/search'
SEARCH = 'https://itunes.apple.com/search?media=podcast&entity=podcast&limit=25&country=US&term='
LOOKUP = 'https://itunes.apple.com/lookup?id='
F_WSJ = 'https://feeds.example/wsj'
ART = open(os.path.join(DATA, 'art100.jpg'), 'rb').read()


def cancel(m): m.setword(PSYMS['pn'] + 20 + 12 * O['PC_MAX_SHOWS'] + 12, 1)   # (patch/pcnet.c: the status record's cancel word, after the statuses, part, base, span)


def data(name): return open(os.path.join(DATA, name), 'rb').read()


def fn(m, name, *a, count=1 << 40):
    for i, v in enumerate(a[4:]): m.setword(STACK + 16 + 4 * i, v)   # o32: the fifth argument on is on the stack, above the callee's home space
    return m.call(PSYMS[name], **dict(zip(('a0', 'a1', 'a2', 'a3'), a)), count=count)


def machine(site=None, **kw):
    m = PCN.machine(site=site, **kw)
    m.jinit()
    m.dirs.add('/mnt/mmc')
    return m


def classify(m, text):
    idp = m.alloc(16)
    r = fn(m, 'pn_classify', m.cstr(text), idp, 16)
    return r, m.read_cstr(idp)


def state(m):
    return dict(state=fn(m, 'pn_search_state'), code=fn(m, 'pn_search_code'), count=fn(m, 'pn_search_count'), gen=fn(m, 'pn_search_gen'), busy=fn(m, 'pn_job_busy'))


def result(m, i):
    p = fn(m, 'pn_search_result', i)
    if not p: return None
    raw = bytes(m.u.mem_read(p, 4 + 80 + 56 + 320 + 320))   # id, name, author, feed (PC_URL), art (PJ_ART)
    cs = lambda b: b.split(b'\0')[0].decode('utf-8')
    return (int.from_bytes(raw[:4], 'little'), cs(raw[4:84]), cs(raw[84:140]), cs(raw[140:460]), cs(raw[460:]))


def thumb(m, i):
    buf = m.alloc(200)
    return m.read_cstr(buf) if fn(m, 'pn_search_thumb', i, buf, 200) else None


def start_search(m, term):
    m.thread = None
    r = fn(m, 'pn_search', m.cstr(term))
    return r, m.thread


def classify_tests(ctx):
    expect, m = ctx.expect, Machine()
    for text, want in (('jazz', (0, '')), ('播客 news', (0, '')), ('', (0, '')), ('httpx://a', (0, '')), ('ftp://a.b/c', (0, '')), ('www.example.com/feed', (0, '')),
                       ('http://a.example/rss', (1, '')), ('HTTPS://A.Example/RSS.xml?x=1', (1, '')), ('https://feeds.megaphone.fm/ADL1234', (1, '')),
                       ('https://podcasts.apple.com/us/podcast/the-daily/id1200361736', (2, '1200361736')), ('https://podcasts.apple.com/us/podcast/the-daily/id1200361736?i=1000', (2, '1200361736')),
                       ('https://podcasts.apple.com/us/podcast/new-show/id6811931105', (2, '6811931105')),   # (ids pass 32 bits)
                       ('HTTPS://PODCASTS.APPLE.COM/us/podcast/x/ID42', (2, '42')), ('http://podcasts.apple.com:443/us/podcast/x/id77#a', (2, '77')),
                       ('https://podcasts.apple.com/us/browse', (1, '')), ('https://podcasts.apple.com/us/podcast/x/idabc', (1, '')), ('https://podcasts.apple.com/us/podcast/x/id', (1, '')),
                       ('https://podcasts.apple.com/us/podcast/x/id0', (1, '')), ('https://podcasts.apple.com/us/podcast/x/id1234567890123456', (1, '')),
                       ('https://notpodcasts.apple.com.evil.example/x/id5', (1, '')), ('https://evil.example/podcasts.apple.com/id5', (1, '')),
                       ('https://podcasts.apple.com.evil.example/id5', (1, '')), ('https://podcasts.apple.com/us/podcast/id1/id2', (2, '1'))):
        r, i = classify(m, text)
        expect((r, i) == want, f'{text!r}: {want}, got {(r, i)}')


def request_tests(ctx):
    """The URL, the options, the answer, the artwork."""
    expect = ctx.expect
    reqs = []
    raw = data('all_in_us.json')
    docs = json.loads(raw)

    def site(url, o):
        reqs.append((url, dict(o)))
        return {'body': ART, 'chunk': 5500} if 'mzstatic' in url or 'is1-ssl' in url or 'image' in url else {'body': raw}
    m = machine(site=site)
    r, th = start_search(m, '播客 a&b/c~d_e-f.g')
    expect(r == 0 and th and th[0] == PSYMS['pn_smain'] and ('curl_global_init', 3) in m.calls and [c[0] for c in m.calls].count('pthread_create') == 1, 'a search starts one detached worker, curl initialised on the UI thread first')
    expect(state(m)['state'] == 1 and state(m)['busy'] == 1 and fn(m, 'pn_busy') == 0, 'the query runs: state 1, a job is busy, a refresh is not')
    expect(fn(m, 'pn_search', m.cstr('again')) == PN['BUSY'] and fn(m, 'pn_preview', m.cstr('https://x.example/'), m.cstr(''), m.cstr('')) == PN['BUSY'], 'a second job while one runs: PN_BUSY')
    expect(fn(m, 'pn_refresh', m.cstr(ROOT_DIR), m.shows()[1], m.alloc(4), 1) == PN['BUSY'] and fn(m, 'pn_dl_start') == 0 and fn(m, 'pn_dl_running') == 0, 'a refresh is refused and the downloads do not start while the search runs')
    gen0 = state(m)['gen']
    PCN.work(m, th)
    st = state(m)
    expect(st['state'] == 3 and st['code'] == 0 and st['count'] == 25 and st['busy'] == 0 and st['gen'] > gen0, f'the worker ends: done, OK, 25 results ({st})')
    url, o = reqs[0]
    want = SEARCH + '%E6%92%AD%E5%AE%A2%20a%26b%2Fc~d_e-f.g'
    expect(url == want, f'the term is URL-encoded UTF-8 (a space is %20, & and / are escaped, - _ . ~ stay): {url}')
    expect('country=US' in url and 'limit=25' in url and 'media=podcast' in url and 'entity=podcast' in url, 'media=podcast, entity=podcast, limit 25, country US')
    expect(o[10065] == CA and o[52] == 1 and o[68] == 16 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[99] == 1 and o[78] == 20 and o[13] == 120 and o[10018].startswith('M1PlusMusic/')
           and 64 not in o and 81 not in o, 'the same libcurl options as a feed\'s: the firmware CA bundle, verification never switched off, 16 redirects, fail on HTTP error, time-outs, a user agent')
    want_res = [(min(r_.get('collectionId', 0), 0xffffffff), r_['collectionName'][:79], r_['artistName'][:55], r_.get('feedUrl', ''), r_['artworkUrl100']) for r_ in docs['results'] if r_.get('collectionName')]
    got = [result(m, i) for i in range(25)]
    expect(len(want_res) == 25 and [g[1] for g in got] == [w[1] for w in want_res] and [g[3] for g in got] == [w[3] for w in want_res] and [g[0] for g in got] == [w[0] for w in want_res], 'every result\'s id, name and feed')
    expect(result(m, 25) is None and result(m, -1) is None, 'no result past the last')
    art_reqs = [u for u, _ in reqs[1:]]
    expect(art_reqs == [g[4] for g in got], 'the artwork of each result fetched one by one, in order, after the query')
    paths = [thumb(m, i) for i in range(25)]
    expect(all(p == f'{SDIR}/t{i}.jpg' for i, p in enumerate(paths)) and all(m.fs.get(p) == ART for p in paths), 'each picture is in the cache directory as t<n>.jpg, whole')
    expect(len(m.curl) == 0 and not [p for p in m.fs if p.endswith('.src')], 'every handle cleaned up, no download file left')
    expect(all(d in m.dirs for d in ('/mnt/mmc/.m1plus', '/mnt/mmc/.m1plus/podcasts', SDIR)), 'the directories are made')
    # a new search removes the old pictures and results at once
    m.calls = []
    r, th = start_search(m, 'second')
    expect(r == 0 and state(m)['count'] == 0 and not [p for p in m.fs if p.startswith(SDIR + '/t')] and thumb(m, 0) is None and state(m)['state'] == 1, 'a new search clears the results and the cache before it starts')
    PCN.work(m, th)
    # the same term, a CJK-only term
    reqs.clear()
    r, th = start_search(m, '日谈公园'); PCN.work(m, th)
    expect(reqs[0][0] == SEARCH + '%E6%97%A5%E8%B0%88%E5%85%AC%E5%9B%AD', 'a CJK term')
    r, th = start_search(m, 'x' * 63 + '中'); PCN.work(m, th)
    expect(state(m)['code'] == 0, 'a 64 byte term fits the request buffer')
    expect(fn(m, 'pn_search', m.cstr('中' * 200)) == PN['MEM'] and state(m)['busy'] == 0, 'a term too long to encode into the buffer: PN_MEM, nothing started')


def failure_tests(ctx):
    expect = ctx.expect
    raw = data('top_of_japan_us.json')

    def run(site, **kw):
        m = machine(site=site, **kw)
        r, th = start_search(m, 'jazz')
        if th: PCN.work(m, th)
        return m, r

    for label, site, code in (('no connection', lambda u, o: {'rc': 6}, PN['NET']), ('a time-out', lambda u, o: {'rc': 28}, PN['NET']), ('a certificate error', lambda u, o: {'rc': 60}, PN['CERT']),
                              ('HTTP 403', lambda u, o: {'rc': 22, 'code': 403}, PN['HTTP']), ('HTTP 429 (rate limit)', lambda u, o: {'rc': 22, 'code': 429}, PN['HTTP']),
                              ('HTTP 404', lambda u, o: {'rc': 22, 'code': 404}, PN['HTTP']), ('an HTML page', lambda u, o: {'body': b'<html>blocked</html>'}, PN['HTTP']),
                              ('an empty answer', lambda u, o: {'body': b''}, PN['HTTP']), ('JSON without results', lambda u, o: {'body': b'{"errorMessage":"x"}'}, PN['HTTP'])):
        m, r = run(site)
        st = state(m)
        expect(r == 0 and st['state'] == 3 and st['code'] == code and st['count'] == 0 and st['busy'] == 0 and result(m, 0) is None, f'{label}: state done, code {code}, no result ({st})')
    m, r = run(lambda u, o: {'body': b'{"resultCount":0,"results":[]}'})
    expect(state(m)['code'] == 0 and state(m)['count'] == 0, 'no result: OK with 0 (the page says No results)')
    for label, kw, code in (('no Wi-Fi', dict(wifi=-1), PN['NOWIFI']), ('no card', dict(card_mounted=False), PN['STORAGE']), ('a clock never set', dict(wall=1700000000), PN['NOCLOCK'])):
        m = machine(site=lambda u, o: {'body': raw}, **kw)
        r, th = start_search(m, 'x')
        expect(r == code and th is None and 'curl_global_init' not in [c[0] for c in m.calls] and state(m)['state'] == 0, f'{label}: the guard answers {code}, nothing starts')
    m = machine(site=lambda u, o: {'body': raw}, ca=False)
    r, th = start_search(m, 'x')
    expect(r == PN['NOCERT'] and th is None, 'no CA bundle: PN_NOCERT')
    m = machine(site=lambda u, o: {'body': raw}, thread_ok=False)
    r, th = start_search(m, 'x')
    expect(r == PN['MEM'] and state(m)['busy'] == 0 and state(m)['state'] == 0, 'a thread that cannot be made: PN_MEM, not busy')
    m = machine(site=lambda u, o: {'body': raw}); m.calloc_fail = True
    r, th = start_search(m, 'x'); PCN.work(m, th)
    expect(state(m)['code'] == PN['MEM'] and state(m)['busy'] == 0, 'no memory for the answer: PN_MEM')
    # the 96 KB cap: an answer that goes on is cut at 98304 bytes and the results complete before the cut are kept
    items = ','.join(json.dumps({'collectionId': i + 1, 'collectionName': f'Show {i}', 'artistName': 'A', 'feedUrl': f'https://f.example/{i}', 'artworkUrl100': '', 'pad': 'x' * 9000}) for i in range(14))
    big = ('{"resultCount":14,"results":[' + items + ']}').encode()
    seen = []
    def site(u, o):
        seen.append(u); return {'body': big, 'chunk': 16384}
    m, r = run(site)
    st = state(m)
    expect(len(big) > 98304 and st['code'] == 0 and st['count'] == 10 and result(m, 9)[1] == 'Show 9' and result(m, 10) is None, f'an answer over 96 KB is cut there: the ten results that were whole ({st["count"]} of 14)')
    # not a picture, a failing picture, no picture address
    docs = [{'collectionName': f'S{i}', 'feedUrl': f'https://f.example/{i}', 'artworkUrl100': f'https://art.example/{i}.jpg'} for i in range(5)]
    docs[4]['artworkUrl100'] = ''
    body = json.dumps({'resultCount': 5, 'results': docs}).encode()
    def site2(u, o):
        if u.startswith(SEARCH): return {'body': body}
        i = int(u.rsplit('/', 1)[1].split('.')[0])
        return [{'body': ART}, {'rc': 22, 'code': 404}, {'body': b'<html>not a picture</html>'}, {'body': b'\x89PNG\r\n\x1a\n' + bytes(8)}][i]
    m, r = run(site2)
    expect([thumb(m, i) for i in range(5)] == [f'{SDIR}/t0.jpg', None, None, None, None] and not [p for p in m.fs if p.endswith('.src')], 'a picture that is missing, not a picture, too short to be one, or has no address leaves the placeholder, and no download file')
    expect(state(m)['state'] == 3 and m.fs.get(f'{SDIR}/t0.jpg') == ART, 'the others still arrive and the worker ends')


def cancel_tests(ctx):
    expect = ctx.expect
    raw = data('top_of_japan_us.json')
    # Cancel while the query transfers: aborted, nothing kept
    def site(u, o):
        return {'body': raw, 'xfer': lambda url, sent, total: cancel(m) if not url.startswith('https://is') else None}
    m = machine(site=site)
    r, th = start_search(m, 'x'); PCN.work(m, th)
    st = state(m)
    expect(st['state'] == 3 and st['code'] == PN['CANCELLED'] and st['count'] == 0 and st['busy'] == 0, f'cancelled during the query: done, PN_CANCELLED, no result ({st})')
    # Cancel after the third picture: the rest are not fetched and the worker ends
    got = []
    def site2(u, o):
        got.append(u)
        if u.startswith(SEARCH): return {'body': raw}
        if len(got) == 3: cancel(m2)
        return {'body': ART, 'chunk': 5500}
    m2 = machine(site=site2)
    r, th = start_search(m2, 'x'); PCN.work(m2, th)
    expect(len(got) == 3 and state(m2)['count'] == 3 and state(m2)['busy'] == 0, f'cancelled during the second picture: the query and two pictures were asked for ({len(got)} requests), the worker ended')
    expect(thumb(m2, 0) and thumb(m2, 1) is None and thumb(m2, 2) is None, 'the picture that came stays; the one cut off and the rest are none')
    # a refresh and the downloads can start once it ended
    expect(fn(m2, 'pn_job_busy') == 0 and fn(m2, 'pn_dl_start') == 0, 'afterwards the downloads may start again')


def preview_tests(ctx):
    expect = ctx.expect
    WSJ = PCN.feed_bytes('wsj-3items.xml')
    reqs = []

    def picture():
        from PIL import Image
        im = Image.new('RGB', (1400, 1400), (200, 30, 30)); b = io.BytesIO(); im.save(b, 'JPEG'); return b.getvalue()
    JPG = picture()

    def site(u, o):
        reqs.append((u, dict(o)))
        if u == F_WSJ: return {'body': WSJ}
        if u.startswith(LOOKUP): return {'body': data('lookup_1493503146.json')}
        if u == 'https://feed.xyzfm.space/cv4bkgpuglwp': return {'body': WSJ}
        if u.startswith('https://image.simplecastcdn.com/'): return {'body': JPG}
        return {'rc': 22, 'code': 404}

    def go(m, url, id='', art=''):
        m.thread = None
        r = fn(m, 'pn_preview', m.cstr(url), m.cstr(id), m.cstr(''))
        if m.thread: PCN.work(m, m.thread)
        return r

    m = machine(site=site)
    m.thread = None
    r = fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr(''))
    expect(r == 0 and m.thread and m.thread[0] == PSYMS['pn_pmain'] and fn(m, 'pn_preview_state') == 1 and fn(m, 'pn_job_busy') == 1 and fn(m, 'pn_busy') == 0, 'a preview starts the worker')
    PCN.work(m, m.thread)
    expect(fn(m, 'pn_preview_state') == 2 and fn(m, 'pn_preview_code') == 0 and fn(m, 'pn_job_busy') == 0, 'it ends: done, OK')
    p = fn(m, 'pn_preview_parser')
    expect(p and fn(m, 'pf_items', p) == 3 and fn(m, 'pf_is_feed', p) == 1 and m.read_cstr(fn(m, 'pn_preview_feed')) == F_WSJ, 'the parser is held with the three episodes and the feed address')
    expect(fn(m, 'pn_preview_cover') == 1 and f'{SDIR}/preview.jpg' in m.fs and Image_size(m.fs[f'{SDIR}/preview.jpg']) == (192, 192), 'the feed\'s picture is shrunk to 192 px into the cache directory')
    expect(not [p_ for p_ in m.fs if p_.startswith(ROOT_DIR)] and not [p_ for p_ in m.dirs if p_.startswith(ROOT_DIR + '/')], 'no show folder, no file under Podcasts')
    expect(reqs[0][0] == F_WSJ and reqs[0][1][10065] == CA and reqs[0][1][45] == 1 and 64 not in reqs[0][1], 'fetched as a refresh does: the bundle, verification on')
    expect(not [p_ for p_ in m.fs if p_.endswith(('.src', '.tmp'))], 'no download or temp file left')
    fn(m, 'pn_preview_drop')
    expect(fn(m, 'pn_preview_parser') == 0 and fn(m, 'pn_preview_cover') == 0 and fn(m, 'pn_preview_state') == 0, 'dropping it frees the parser and removes the picture')
    # an Apple Podcasts link: the lookup names the feed
    reqs.clear()
    go(m, '', '1493503146')
    expect([u for u, _ in reqs][:2] == [LOOKUP + '1493503146', 'https://feed.xyzfm.space/cv4bkgpuglwp'] and fn(m, 'pn_preview_code') == 0 and m.read_cstr(fn(m, 'pn_preview_feed')) == 'https://feed.xyzfm.space/cv4bkgpuglwp',
           f'an id: the lookup first, then the feed it names ({[u for u, _ in reqs]})')
    # failures create nothing and hold nothing
    for label, s, code in (('a lookup that finds no feed address', lambda u, o: {'body': b'{"resultCount":1,"results":[{"collectionName":"Gone"}]}'}, PN['NOFEED']),
                           ('a lookup with no result', lambda u, o: {'body': b'{"resultCount":0,"results":[]}'}, PN['NOFEED']),
                           ('a lookup that fails', lambda u, o: {'rc': 6}, PN['NET'])):
        m = machine(site=s); go(m, '', '5')
        expect(fn(m, 'pn_preview_code') == code and fn(m, 'pn_preview_parser') == 0 and fn(m, 'pn_preview_state') == 2, f'{label}: code {code}, nothing held')
    for label, s, code in (('HTTP 403', lambda u, o: {'rc': 22, 'code': 403}, PN['HTTP']), ('HTTP 404', lambda u, o: {'rc': 22, 'code': 404}, PN['GONE']),
                           ('an HTML page', lambda u, o: {'body': b'<html>x</html>'}, PN['NOTFEED']), ('a certificate error', lambda u, o: {'rc': 60}, PN['CERT']), ('no connection', lambda u, o: {'rc': 6}, PN['NET'])):
        m = machine(site=s); go(m, 'https://x.example/rss')
        expect(fn(m, 'pn_preview_code') == code and fn(m, 'pn_preview_parser') == 0 and not [p_ for p_ in m.fs if p_.startswith(ROOT_DIR)] and not [p_ for p_ in m.dirs if p_.startswith(ROOT_DIR + '/')],
               f'{label}: code {code}, no parser held, no folder or file made')
    m = machine(site=site); m.wifi = -1
    expect(fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')) == PN['NOWIFI'] and fn(m, 'pn_preview_state') == 0, 'the guards first')
    # a feed with no picture: the preview holds, with no picture file
    m = machine(site=lambda u, o: {'body': WSJ} if u == F_WSJ else {'rc': 22, 'code': 404}); go(m, F_WSJ)
    expect(fn(m, 'pn_preview_code') == 0 and fn(m, 'pn_preview_cover') == 0 and fn(m, 'pn_preview_parser') != 0, 'a picture that cannot be fetched leaves a preview without it')
    # Cancel while the feed transfers: nothing held
    m = machine(site=lambda u, o: {'body': WSJ, 'xfer': lambda url, sent, total: cancel(m)}); go(m, F_WSJ)
    expect(fn(m, 'pn_preview_code') == PN['CANCELLED'] and fn(m, 'pn_preview_parser') == 0 and fn(m, 'pn_job_busy') == 0, 'cancelled: nothing held')


def Image_size(b):
    from PIL import Image
    return Image.open(io.BytesIO(b)).size


def subscribe_tests(ctx):
    """Subscribe makes what an import and its first refresh make: the same bytes."""
    expect = ctx.expect
    WSJ = PCN.feed_bytes('wsj-3items.xml')
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (1400, 1400), (30, 30, 200)).save(b, 'JPEG'); JPG = b.getvalue()
    def site(u, o):
        if u == F_WSJ: return {'body': WSJ}
        if u.startswith('https://image.simplecastcdn.com/'): return {'body': JPG}
        return {'rc': 22, 'code': 404}
    # the import and its first refresh
    a = machine(site=site)
    a.put(f'{ROOT_DIR}/subscriptions.txt', (F_WSJ + '\n').encode())
    shows, arr = a.shows()
    fn(a, 'pn_import', a.cstr(ROOT_DIR), arr, len(shows))
    r, th = PCN.start(a, [s['dir'] for s in a.shows()[0] if s['feed'] == F_WSJ])
    PCN.work(a, th)
    folder_a = [p for p in a.fs if p.endswith('/.show')]
    expect(len(folder_a) == 1, 'the import and refresh made one show')
    dir_a = folder_a[0].rsplit('/', 1)[0]
    files_a = {p.rsplit('/', 1)[1]: v for p, v in a.fs.items() if p.startswith(dir_a + '/')}
    # the preview and Subscribe
    m = machine(site=site)
    m.thread = None
    fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')); PCN.work(m, m.thread)
    shows, arr = m.shows()
    out = m.alloc(PCN.PCP.PM_DIR if hasattr(PCN.PCP, 'PM_DIR') else 160)
    m.calls = []
    r = fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), arr, len(shows), out, 128)
    dir_b = f'{ROOT_DIR}/{m.read_cstr(out)}'
    files_b = {p.rsplit('/', 1)[1]: v for p, v in m.fs.items() if p.startswith(dir_b + '/')}
    expect(r == 0 and dir_b == dir_a == f'{ROOT_DIR}/WSJ Minute Briefing', f'Subscribe returns the folder named from the feed\'s title ({dir_b})')
    expect(sorted(files_b) == sorted(files_a) == ['.episodes', '.notes', '.show', 'cover.jpg'], f'the same files: .episodes, .notes, .show, cover.jpg ({sorted(files_b)})')
    expect(files_b['.episodes'] == files_a['.episodes'] and files_b['.show'] == files_a['.show'], 'and the same .episodes and .show, byte for byte (feed, title, image, author, category, description)')
    expect(Image_size(files_b['cover.jpg']) == Image_size(files_a['cover.jpg']) == (192, 192) and f'{SDIR}/preview.jpg' not in m.fs, 'cover.jpg is the preview\'s picture moved into the folder')
    expect(fn(m, 'pn_preview_parser') == 0 and not [p for p in m.fs if p.endswith('.tmp')], 'the preview is dropped, no temp file is left')
    s = next(x for x in m.shows()[0] if x['dir'] == 'WSJ Minute Briefing')
    expect(s['feed'] == F_WSJ and s['title'] == 'WSJ Minute Briefing' and s['author'] and s['checked'] == 1800000000 and s['cover'] == 'cover.jpg', 'the model reads the new show')
    # nothing held: nothing to subscribe to
    expect(fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), arr, 1, out, 128) == PN['NOTFEED'], 'no preview held: PN_NOTFEED')
    # a name that is taken: the import\'s name
    m = machine(site=site)
    m.put(f'{ROOT_DIR}/WSJ Minute Briefing/mine.mp3', b'x')
    m.thread = None; fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')); PCN.work(m, m.thread)
    shows, arr = m.shows()
    r = fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), arr, len(shows), out, 128)
    expect(r == 0 and m.read_cstr(out) == f'feeds.example-{PCN.pc_hash(F_WSJ):08x}' and f'{ROOT_DIR}/WSJ Minute Briefing/mine.mp3' in m.fs and f'{ROOT_DIR}/WSJ Minute Briefing/.show' not in m.fs,
           'a folder of the title\'s name that someone else owns is left alone: the import\'s name (host and hash)')
    # a write that fails leaves nothing behind
    for what in ('.episodes.tmp', '.show.tmp'):
        m = machine(site=site)
        m.thread = None; fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')); PCN.work(m, m.thread)
        m.fail.add(('open', f'{ROOT_DIR}/WSJ Minute Briefing/{what}'))
        shows, arr = m.shows()
        r = fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), arr, len(shows), out, 128)
        left = [p for p in list(m.fs) + list(m.dirs) if p.startswith(f'{ROOT_DIR}/WSJ Minute Briefing')]
        expect(r == PN['STORAGE'] and not [p for p in left if p.startswith(f'{ROOT_DIR}/WSJ Minute Briefing/')] and fn(m, 'pn_preview_parser') != 0, f'{what} cannot be written: PN_STORAGE, no file left, the preview still held ({left})')
    m = machine(site=site); m.card_mounted = False
    m.thread = None
    expect(fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')) == PN['STORAGE'] and m.thread is None, 'no card: PN_STORAGE, nothing starts')
    # a full list of shows
    m = machine(site=site)
    m.thread = None; fn(m, 'pn_preview', m.cstr(F_WSJ), m.cstr(''), m.cstr('')); PCN.work(m, m.thread)
    expect(fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), m.shows()[1], O['PC_MAX_SHOWS'], out, 128) == PN['STORAGE'] and fn(m, 'pn_preview_parser') != 0, 'PC_MAX_SHOWS shows already: PN_STORAGE, nothing written (the page says Too many shows before it asks)')


def fallback_tests(ctx):
    """Apple's 600 x 600 picture (artworkUrl600) stands in when the feed's own cannot be decoded: a progressive JPEG of 2.38 MP is refused (PC_COVER_MAX_PX, 2.1 MP). It comes with a search result, or from
    the lookup of an Apple id; a typed address has none. Subscribe keeps the preview's picture as cover.jpg, and a later refresh never replaces a cover."""
    expect = ctx.expect
    from PIL import Image
    WSJ = PCN.feed_bytes('wsj-3items.xml')
    b = io.BytesIO(); Image.new('RGB', (1700, 1400), (200, 30, 30)).save(b, 'JPEG', progressive=True); BIG = b.getvalue()
    b = io.BytesIO(); Image.new('RGB', (600, 600), (30, 200, 30)).save(b, 'JPEG'); SMALL = b.getvalue()
    lookup = json.loads(data('lookup_1611374685.json'))
    ART6 = lookup['results'][0]['artworkUrl600']
    reqs = []

    def site(feed_img):
        def f(u, o):
            reqs.append(u)
            if u == F_WSJ or u == lookup['results'][0]['feedUrl']: return {'body': WSJ}
            if u.startswith(LOOKUP): return {'body': data('lookup_1611374685.json')}
            if u == ART6: return {'body': SMALL}
            if u.startswith('https://image.simplecastcdn.com/') and feed_img is not None: return {'body': feed_img}
            return {'rc': 22, 'code': 404}
        return f

    def go(m, url, id='', art=''):
        m.thread = None
        reqs.clear()
        r = fn(m, 'pn_preview', m.cstr(url), m.cstr(id), m.cstr(art))
        PCN.work(m, m.thread)
        return r

    def cover(m):
        f = m.fs.get(f'{SDIR}/preview.jpg')
        return f and Image_size(f)

    m = machine(site=site(BIG)); go(m, F_WSJ, '', ART6)
    expect(fn(m, 'pn_preview_code') == 0 and cover(m) == (192, 192) and m.fs[f'{SDIR}/preview.jpg'] != b'' and ART6 in reqs and not [p for p in m.fs if p.endswith(('.src', '.tmp'))],
           'a search result whose feed picture is progressive and over 2.1 MP: the preview takes artworkUrl600, shrunk to 192 px, no download file left')
    m = machine(site=site(BIG)); go(m, F_WSJ)
    expect(fn(m, 'pn_preview_code') == 0 and cover(m) is None and fn(m, 'pn_preview_parser') != 0, 'a typed address has no artworkUrl600: the same feed has no picture, as before')
    m = machine(site=site(None)); go(m, F_WSJ, '', ART6)
    expect(cover(m) == (192, 192), 'a feed picture that cannot be fetched at all falls back too')
    m = machine(site=site(SMALL)); go(m, F_WSJ, '', ART6)
    expect(cover(m) == (192, 192) and ART6 not in reqs, 'a feed picture that decodes is used: the fallback is not even fetched')
    m = machine(site=site(BIG)); go(m, '', '1611374685')
    expect(reqs[:2] == [LOOKUP + '1611374685', lookup['results'][0]['feedUrl']] and ART6 in reqs and cover(m) == (192, 192), 'an Apple id (link or chart row): the lookup brings artworkUrl600')
    m = machine(site=lambda u, o: {'body': SMALL} if u == ART6 else site(BIG)(u, o)); go(m, '', '1611374685'); go(m, F_WSJ, '', 'https://art.example/' + 'x' * 200)
    expect(fn(m, 'pn_preview_code') == 0 and cover(m) is None, 'an artworkUrl600 that does not fit its field is none')
    # Subscribe keeps the fallback as the first cover.jpg; a refresh whose feed picture fails does not delete or replace it
    m = machine(site=site(BIG)); go(m, F_WSJ, '', ART6)
    shows, arr = m.shows()
    out = m.alloc(160)
    expect(fn(m, 'pn_subscribe', m.cstr(ROOT_DIR), arr, len(shows), out, 128) == 0, 'Subscribe')
    cj = f'{ROOT_DIR}/{m.read_cstr(out)}/cover.jpg'
    first = m.fs.get(cj)
    expect(first and Image_size(first) == (192, 192) and f'{SDIR}/preview.jpg' not in m.fs, 'the show\'s first cover.jpg is the fallback picture')
    r, th = PCN.start(m, [m.read_cstr(out)]); PCN.work(m, th)
    expect(m.fs.get(cj) == first and not [p for p in m.fs if p.endswith(('.src', '.tmp')) and p.startswith(ROOT_DIR)], 'a refresh whose feed picture is refused leaves cover.jpg as it is')


SECTIONS = [classify_tests, request_tests, failure_tests, cancel_tests, preview_tests, fallback_tests, subscribe_tests]

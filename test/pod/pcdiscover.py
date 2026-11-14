"""Podcasts Discover (patch/pcjson.c pj_chart, patch/pcnet.c "Charts", patch/podcasts.c "Discover", docs/modules/podcasts.md "Discover"): Apple's top 25 shows and top 25 episodes of the Podcast Region.
The extractor against Python's json module on the sample answers (test/data/discover, fetched 2026-11-05), the worker (the request for each region, the retries, the 404 / empty fall back to the United States, the held
answers, the artwork one by one, Cancel, the guards, the lookup in the chart's store), and the level: geometry against tools/pod_show.py discover_layout, the Shows | Episodes control, the grey line under the title,
the lazy fetch of each chart, a tap on a row (show or episode: the lookup, the preview, Back to the chart), Not available, every failure in the page's words, the magnifier, the navbar, the screen-off rule and the
strings in 13 languages. The compiled payload runs under Unicorn; the card is a dict of paths and libcurl is scripted."""
import json, os, random, re
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


SU, SE = sibling('pcsearchui'), sibling('pcsearch')
PCS, PCP, PCN = SU.PCS, SU.PCP, SU.PCN
import pcregion, pod_i18n, pod_show   # noqa: E402

PN = SE.PN
SC_YOFF = O['SC_YOFF']
DATA = SU.DATA_DC
CHART, LOOKUP, SDIR = SU.CHART, SU.LOOKUP, SU.SDIR
REGION_FILE = pcregion.FILE
NAME, AUTHOR, ART = 80, 56, 320
ID = 16
REC = ID + NAME + AUTHOR + ART + ID   # (pj_chart_t: the episode's own id last)
REGION, SIZE = 0x30000000, 0x40000
SHOWS, EPISODES = open(os.path.join(DATA, 'top-shows-us-50.json'), 'rb').read(), open(os.path.join(DATA, 'top-episodes-us-50.json'), 'rb').read()
# The episode rows' matching (docs/modules/podcasts.md "Discover"): a trimmed Top Episodes answer (GB, 3 rows), the episode lookup of its first row's show (The Rest Is Politics, 3 episodes),
# the show's feed (5 items) and the show's lookup (test/data/search); all as the store answered them on 2026-11-06.
EP_CHART = open(os.path.join(DATA, 'episodes-gb-top3.json'), 'rb').read()
EP_LOOKUP_BODY = open(os.path.join(DATA, 'lookup-episodes-1611374685.json'), 'rb').read()
FEED_RIP = open(os.path.join(DATA, 'feed-rest-is-politics-5items.xml'), 'rb').read()
SHOW_RIP = open(os.path.join(DATA, '..', 'search', 'lookup_1611374685.json'), 'rb').read()
RIP_ID, RIP_FEED = '1611374685', 'https://feeds.megaphone.fm/GLT9190936013'
RIP_SHOW_URL = LOOKUP + RIP_ID + '&country=US'
EP_URL = LOOKUP + RIP_ID + '&entity=podcastEpisode&limit=20&country=US'
EP_ROW0 = '1000799787173'   # the first row: "586. Can the Democrats...", the feed's item 0 (its enclosure is the lookup's episodeUrl)
EP_DESC0 = 'Why did Trump concede'   # the start of that episode's description (the episode page's text)
LOOKUP_DAILY = open(os.path.join(DATA, 'lookup-1200361736.json'), 'rb').read()
FEED_DAILY = 'https://feeds.simplecast.com/Sl5CSM3S'
FEED_WSJ = SU.WSJ
NYT_OPINION = 1548604447   # the show of the first episode of the sample Top Episodes (its url is .../id1548604447?i=1000799878707)


def oracle(raw, episodes):
    """[(id, name, author, art)] the documented way, by json.loads: the show's "id" (digits, a string), or for an episode the digits after /id in its url; "" for none; strings cut at their field's size."""
    out = []
    for r in json.loads(raw)['feed']['results']:
        if episodes:
            mm = re.search(r'/id(\d+)', r.get('url', ''))
            ident = mm.group(1) if mm and 0 < len(mm.group(1)) <= 15 and int(mm.group(1)) else ''
        else:
            ident = r['id'] if r.get('id', '').isdigit() and len(r['id']) <= 15 and int(r['id']) else ''
        name, art = cut(r.get('name', ''), NAME), r.get('artworkUrl100', '')
        art = art if len(art.encode('utf-8')) <= ART - 1 else ''
        if name: out.append((ident, name, cut(r.get('artistName', ''), AUTHOR), art))
    return out


class PJC:
    """pj_chart under Unicorn: the input ends at the end of a mapped region (an unmapped page follows), the output array too."""
    def __init__(self):
        self.m = Machine()
        for base in (REGION, REGION + 0x100000):
            self.m.u.mem_map(base, SIZE)

    def run(self, data, episodes=0, mx=50):
        m = self.m
        src = REGION + SIZE - len(data)
        m.u.mem_write(src, data)
        dst = REGION + 0x100000 + SIZE - mx * REC
        m.u.mem_write(dst, bytes([0xAA]) * (mx * REC))
        n = self.call(src, len(data), episodes, dst, mx)
        n = n - (1 << 32) if n >= 1 << 31 else n
        raw = bytes(m.u.mem_read(dst, mx * REC))
        res = []
        for i in range(max(n, 0)):
            r = raw[i * REC:(i + 1) * REC]
            f = lambda off, size: r[off:off + size].split(b'\0')[0].decode('utf-8')
            res.append((f(0, ID), f(ID, NAME), f(ID + NAME, AUTHOR), f(ID + NAME + AUTHOR, ART)))
        return n, res

    def call(self, src, n, episodes, dst, mx):
        m = self.m
        for i, v in enumerate((mx,)): m.setword(STACK + 16 + 4 * i, v)   # o32: the fifth argument is on the stack, above the callee's home space
        return m.call(PSYMS['pj_chart'], a0=src, a1=n, a2=episodes, a3=dst, count=1 << 40)


def doc(*objs, feed=True, tail=''):
    body = '"results":[%s]%s' % (','.join(objs), tail)
    return ('{"feed":{"title":"Top","country":"us",%s}}' % body if feed else '{%s}' % body).encode('utf-8')


def o(**kw): return json.dumps(kw, ensure_ascii=False)


def json_tests(ctx):
    """The two sample answers as json.loads has them; the show chart's id is a string of digits, the episode chart's is the show's in the url; escapes, cuts, missing members, nesting, truncation and fuzzing."""
    expect, P = ctx.expect, PJC()
    for raw, ep, label in ((SHOWS, 0, 'Top Shows'), (EPISODES, 1, 'Top Episodes')):
        want = oracle(raw, ep)
        n, res = P.run(raw, ep)
        expect(n == len(want) == 50 and res == want, f'{label} ({len(raw)} bytes): {n} rows, every id, name, author and artwork as json.loads has them')
        n3, res3 = P.run(raw, ep, 3)
        expect(n3 == 3 and res3 == want[:3], f'{label}: with room for three it keeps the first three')
    n, res = P.run(SHOWS, 0)
    expect(res[0] == ('1200361736', 'The Daily', 'The New York Times', res[0][3]) and res[0][3].endswith('/100x100bb.png') and res[1][1] == 'Pod Save America', 'the first show: The Daily, id 1200361736')
    n, res = P.run(EPISODES, 1)
    expect(res[0][0] == str(NYT_OPINION) and res[0][1] == 'The End of Trumpism' and res[0][2] == 'New York Times Opinion', 'the first episode: its title, its show as the grey line, the show\'s id from the url (not the episode\'s 13 digit one)')
    expect(all(r[0] for r in res) and len({r[0] for r in res}) > 10, 'every episode has a show id')
    # members and shapes
    n, res = P.run(doc(o(id='12', name='a', artistName='b', artworkUrl100='https://x/y.png', url='https://podcasts.apple.com/us/podcast/a/id99?i=5')))
    expect(res == [('12', 'a', 'b', 'https://x/y.png')], 'a show: the "id" string')
    n, res = P.run(doc(o(id='1000000000001', name='a', url='https://podcasts.apple.com/us/podcast/a/id99?i=5')), 1)
    expect(res == [('99', 'a', '', '')], 'an episode: the digits after /id in its url, not its own id')
    for text, want in (('12', '12'), ('4294967295', '4294967295'), ('6804845033', '6804845033'), ('123456789012345', '123456789012345'), ('1234567890123456', ''), ('99999999999999999999', ''), ('0', ''), ('000', ''),
                       ('-5', ''), ('12a', ''), ('', '')):
        n, res = P.run(doc(o(id=text, name='x')))
        expect(n == 1 and res[0][0] == want, f'show id {text!r} is {want!r} (ids pass 32 bits)')
    n, res = P.run(b'{"feed":{"results":[{"id":77,"name":"numeric"}]}}')
    expect(res == [('77', 'numeric', '', '')], 'an id given as a number')
    for url, want in (('https://podcasts.apple.com/us/podcast/x/id1?i=2', '1'), ('https://podcasts.apple.com/us/podcast/x/id', ''), ('https://podcasts.apple.com/us/podcast/x/idabc', ''), ('https://podcasts.apple.com/us/podcast/x', ''),
                      ('https://podcasts.apple.com/us/podcast/x/id6804845033?i=1000799877086', '6804845033'), ('https://podcasts.apple.com/us/podcast/x/id1234567890123456', ''), ('https://podcasts.apple.com/us/podcast/id5/id6?i=1', '5'), ('', '')):
        n, res = P.run(doc(o(name='e', url=url)), 1)
        expect(n == 1 and res[0][0] == want, f'episode url {url!r}: show id {want!r}')
    n, res = P.run(doc(o(id='1', name='a'), o(id='2'), o(id='3', name=''), o(id='4', name='d')))
    expect([r[1] for r in res] == ['a', 'd'], 'a row with no name is not kept')
    n, res = P.run(doc(o(id='1', name='first', artistName='A'), o(id='1', name='second')).replace(b'"first"', b'"first","name":"last"'))
    expect(res[0][1] == 'last', 'a member given twice: the last one')
    n, res = P.run(doc(o(id='1', name='n', genres=[{'name': 'Politics', 'url': 'https://itunes.apple.com/us/genre/id1324', 'genreId': '1324'}], kind='podcasts', url='https://itunes.apple.com/x')))
    expect(res == [('1', 'n', '', '')], 'nested members (genres with their own name and url) are not the row\'s')
    n, res = P.run(doc(o(id='1', name='n', artworkUrl100='https://x/' + 'y' * 310)))
    expect(res[0][3] == '', 'an artwork address that does not fit is none')
    n, res = P.run(doc(o(id='1', name='é' * 60, artistName='中' * 30)))
    expect(len(res[0][1].encode()) <= NAME - 1 and res[0][1] == 'é' * 39 and len(res[0][2].encode()) <= AUTHOR - 1 and res[0][2] == '中' * 18, 'names are cut on a character boundary')
    n, res = P.run(('{"feed":{"results":[{"id":"1","name":"Caf\\u00e9 \\ud83c\\udf99 \\u0026 \\"q\\""}]}}').encode())
    expect(res[0][1] == 'Café \U0001f399 & "q"', 'escapes: \\u, a surrogate pair, \\u0026 and \\"')
    n, res = P.run(b' \n{ "a" : 1 , "feed" : { "x" : [ 1, "]}" ], "results" : [ 1, "s", null, { "id":"7", "name" : "ok" } ] } , "b":3 } ')
    expect(res == [('7', 'ok', '', '')], 'white space, members before the feed, a feed with other members first, a results array of mixed values')
    n, res = P.run(b'{"results":[{"id":"1","name":"top level"}]}')
    expect(n == -1, 'results outside a feed object are not the chart')
    n, res = P.run(b'{"feed":{"results":[]}}')
    expect(n == 0, 'an empty results array is no row')
    for text in (b'', b'  ', b'[]', b'{}', b'{"feed":{}}', b'{"feed":[]}', b'{"feed":{"results":3}}', b'{"feed":3,"results":[{"name":"x"}]}', b'null', b'<html>', b'{"feed":{"results"', b'{"feed":{', b'{"feed"', b'"feed"'):
        n, _ = P.run(text)
        expect(n == -1, f'no feed.results array: {text[:30]!r} is -1')
    n, res = P.run(doc(o(id='1', name='a')), 0, 0)
    expect(n == -1, 'no room: -1')
    n, res = P.run(doc(o(id='1', name='a'), o(id='2', name='b'), o(id='3', name='c')), 0, 2)
    expect(n == 2 and [r[1] for r in res] == ['a', 'b'], 'at most max rows; the output array is not written past it (it ends at an unmapped page)')
    # truncation: a text cut anywhere gives the rows complete before the cut, never a partial one
    want = oracle(SHOWS, 0)
    bad = []
    for cutat in range(0, len(SHOWS) + 1, 53):
        n, res = P.run(SHOWS[:cutat])
        if n >= 0 and res != want[:n]: bad.append((cutat, n))
        if n > 0 and res[-1][1] != want[n - 1][1]: bad.append((cutat, 'last'))
    expect(not bad, f'cut at every 53rd byte: only rows that were whole, as the oracle has them ({bad[:4]})')
    # fuzz: byte flips and cuts never fault
    rnd = random.Random(7)
    for _ in range(300):
        b = bytearray(EPISODES[:12000])
        for _ in range(rnd.randrange(1, 6)): b[rnd.randrange(len(b))] = rnd.randrange(256)
        P.run(bytes(b[:rnd.randrange(len(b))]), rnd.randrange(2))
    expect(True, 'random byte flips and cuts: no read or write outside the buffers (300 runs)')


# ---------------------------------------------------------------------------
def fn(m, name, *a, count=1 << 40):
    for i, v in enumerate(a[4:]): m.setword(STACK + 16 + 4 * i, v)
    return m.call(PSYMS[name], **dict(zip(('a0', 'a1', 'a2', 'a3'), a)), count=count)


def machine(site=None, region=None, **kw):
    m = PCN.machine(site=site, **kw)
    m.jinit()
    m.dirs.add('/mnt/mmc')
    m.slept = []
    m.on_sleep = lambda k, m=m: m.slept.append(1)
    if region: m.fs[REGION_FILE] = region
    return m


def start(m, kind):
    m.thread = None
    r = fn(m, 'pn_chart', kind)
    return r, m.thread


def status(m, kind):
    return dict(state=fn(m, 'pn_chart_state', kind), code=fn(m, 'pn_chart_code', kind), count=fn(m, 'pn_chart_count', kind), held=fn(m, 'pn_chart_held', kind),
                pending=fn(m, 'pn_chart_pending', kind), gen=fn(m, 'pn_chart_gen'), busy=fn(m, 'pn_job_busy'))


def country(m, kind): return m.read_cstr(fn(m, 'pn_chart_country', kind))


def item(m, kind, i):
    p = fn(m, 'pn_chart_item', kind, i)
    if not p: return None
    raw = bytes(m.u.mem_read(p, REC))
    f = lambda off, size: raw[off:off + size].split(b'\0')[0].decode('utf-8')
    return (f(0, ID), f(ID, NAME), f(ID + NAME, AUTHOR), f(ID + NAME + AUTHOR, ART))


def thumb(m, kind, i):
    buf = m.alloc(200)
    return m.read_cstr(buf) if fn(m, 'pn_chart_thumb', kind, i, buf, 200) else None


def chart_site(log=None, **extra):
    """A scripted store: the two sample charts for any region's address, pictures; extra: url -> reply."""
    log = [] if log is None else log

    def site(url, opts):
        log.append((url, dict(opts)))
        if url in extra: return extra[url](url, opts) if callable(extra[url]) else extra[url]
        if re.fullmatch(r'https://rss\.marketingtools\.apple\.com/api/v2/[a-z]{2}/podcasts/top/25/podcasts\.json', url): return {'body': SHOWS, 'chunk': 8192}
        if re.fullmatch(r'https://rss\.marketingtools\.apple\.com/api/v2/[a-z]{2}/podcasts/top/25/podcast-episodes\.json', url): return {'body': EPISODES, 'chunk': 8192}
        if url.startswith('https://is1-ssl.mzstatic.com/'): return {'body': SE.ART, 'chunk': 1500}   # (the harness' scratch is 1 MB: each request takes its chunk)
        return {'rc': 22, 'code': 404}
    site.log = log
    return site


def urls(site): return [u if isinstance(u, str) else u[0] for u in site.log]


def net_tests(ctx):
    """The request for each region and chart, the options, the answer, the artwork one by one, the held answer, a changed region."""
    expect = ctx.expect
    site = chart_site()
    m = machine(site)
    r, th = start(m, 0)
    expect(r == 0 and th and th[0] == PSYMS['pn_cmain'] and ('curl_global_init', 3) in m.calls and [c[0] for c in m.calls].count('pthread_create') == 1, 'a chart starts one detached worker, curl initialised on the UI thread first')
    expect(status(m, 0)['state'] == 1 and status(m, 0)['busy'] == 1 and fn(m, 'pn_busy') == 0 and fn(m, 'pn_job_busy') == 1, 'while it fetches: state 1, a job is busy, a refresh is not')
    expect(fn(m, 'pn_chart', 1) == PN['BUSY'] and fn(m, 'pn_search', m.cstr('x')) == PN['BUSY'] and fn(m, 'pn_dl_start') == 0 and fn(m, 'pn_dl_running') == 0, 'a second job while one runs: PN_BUSY; the downloads do not start')
    gen0 = status(m, 0)['gen']
    PCN.work(m, th)
    st = status(m, 0)
    expect(st['state'] == 2 and st['code'] == 0 and st['count'] == 25 and st['held'] == 1 and st['busy'] == 0 and st['gen'] > gen0 and st['pending'] == 0, f'the worker ends: answered, OK, 25 rows, held, every picture tried ({st})')
    url, opts = site.log[0]
    expect(url == CHART + 'podcasts.json' and country(m, 0) == 'US', f'the Top Shows request: the default region (en_US, the stock time zone) is the United States ({url})')
    expect(opts[10065] == PCN.CA and opts[52] == 1 and opts[68] == 16 and opts[181] == 3 and opts[182] == 3 and opts[45] == 1 and opts[99] == 1 and opts[78] == 20 and opts[13] == 20 and opts[10018].startswith('M1PlusMusic/')
           and 64 not in opts and 81 not in opts, 'the same libcurl options as a feed\'s (the firmware CA bundle, verification never off, 16 redirects, fail on HTTP error), a 20 second time-out for the chart')
    want = oracle(SHOWS, 0)[:25]
    expect([item(m, 0, i) for i in range(25)] == want and item(m, 0, 25) is None and item(m, 0, -1) is None and item(m, 1, 0) is None, 'the 25 rows are the oracle\'s, in rank order; none past the last; the other chart has none yet')
    art = [u for u in urls(site)[1:]]
    expect(art == [w[3] for w in want], 'the artwork of each row fetched one by one in order, after the answer')
    paths = [thumb(m, 0, i) for i in range(25)]
    expect(all(p == f'{SDIR}/c0_{i}.jpg' for i, p in enumerate(paths)) and all(m.fs.get(p) == SE.ART for p in paths) and not [p for p in m.fs if p.endswith('.src')] and len(m.curl) == 0,
           'each picture is c0_<n>.jpg in the search directory, whole; no download file and no handle left')
    expect(thumb(m, 1, 0) is None and thumb(m, 0, 25) is None, 'no picture for the other chart or past the end')
    # held: asking again fetches nothing of the answer, and (every picture tried) no picture either
    site.log.clear()
    r, th = start(m, 0); PCN.work(m, th)
    expect(r == 0 and not site.log and status(m, 0)['held'] == 1, 'a chart that is held is not fetched again')
    # the episodes: their own request, show ids from the urls
    r, th = start(m, 1); PCN.work(m, th)
    expect(urls(site)[0] == CHART + 'podcast-episodes.json' and status(m, 1)['count'] == 25 and [item(m, 1, i) for i in range(25)] == oracle(EPISODES, 1)[:25] and status(m, 0)['count'] == 25, 'Top Episodes: its own address, 25 rows, the show ids of the urls; the shows stay held')
    # a changed region asks again: the address has the region's two letters in lower case
    for region, cc in ((b'GB\n', 'gb'), (b'JP\n', 'jp'), (b'ZA\n', 'za')):
        site.log.clear(); m.fs[REGION_FILE] = region
        expect(status(m, 0)['held'] == 0, f'{region[:2].decode()}: the held answer is of another region: no longer held')
        r, th = start(m, 0); PCN.work(m, th)
        expect(urls(site)[0] == f'https://rss.marketingtools.apple.com/api/v2/{cc}/podcasts/top/25/podcasts.json' and country(m, 0) == region[:2].decode() and status(m, 0)['count'] == 25,
               f'{region[:2].decode()}: the request has it in lower case and the answer is of it')
    # the pictures that were not tried (the job was cancelled) are the next job's
    site2 = chart_site()
    m = machine(site2)
    r, th = start(m, 0)
    got = []
    orig = site2

    def stopper(url, opts):
        if url.startswith('https://is1-ssl'):
            got.append(url)
            if len(got) == 3: SE.cancel(m)
        return orig(url, opts)
    m.curl_site = stopper
    PCN.work(m, th)
    st = status(m, 0)
    expect(len(got) == 3 and st['held'] == 1 and st['pending'] == 22 and st['busy'] == 0 and thumb(m, 0, 2) is None, f'Cancel during the pictures: the third is not kept, 22 rows have none tried ({st})')
    m.curl_site = orig
    orig.log.clear()
    r, th = start(m, 0); PCN.work(m, th)
    expect(status(m, 0)['pending'] == 0 and CHART + 'podcasts.json' not in urls(orig) and len([u for u in urls(orig) if 'mzstatic' in u]) == 22, 'the next job fetches only the pictures that were not tried (the answer is held): 22')
    # clean: the files go, the answers stay, the pictures are untried
    fn(m, 'pn_chart_clean')
    expect(not [p for p in m.fs if p.startswith(SDIR + '/c')] and status(m, 0)['held'] == 1 and status(m, 0)['pending'] == 25 and thumb(m, 0, 0) is None, 'pn_chart_clean: the picture files are removed, the answers stay, every picture is untried again')


def failure_tests(ctx):
    """The retries, the fall back to the United States, every failure, the guards, Cancel while asking, the lookup in the chart's store."""
    expect = ctx.expect
    sleeps = lambda m: m.slept
    # the shows chart was seen to fail with timeouts and 502: asked again, up to three requests
    n = {'k': 0}

    def flaky(url, o_):
        n['k'] += 1
        return {'rc': 22, 'code': 502} if n['k'] <= 2 else {'body': SHOWS}
    m = machine(chart_site(**{CHART + 'podcasts.json': flaky}))
    r, th = start(m, 0); PCN.work(m, th)
    expect(n['k'] == 3 and status(m, 0)['code'] == 0 and status(m, 0)['count'] == 25 and len(sleeps(m)) == 2, f'two 502s then the answer: three requests, a second between them, the chart is there ({n["k"]} requests, {len(sleeps(m))} waits)')
    n['k'] = -100
    m = machine(chart_site(**{CHART + 'podcasts.json': {'rc': 22, 'code': 503}}))
    r, th = start(m, 0); PCN.work(m, th)
    st = status(m, 0)
    expect(st['state'] == 2 and st['code'] == PN['HTTP'] and st['count'] == 0 and st['held'] == 0 and len([u for u, _ in m.curl_site.log if 'podcasts.json' in u]) == 3 and len(sleeps(m)) == 2,
           f'three 503s: Server error after three requests, no rows ({st})')
    for label, reply, want, tries in (('a time-out', {'rc': 28}, PN['NET'], 3), ('no connection', {'rc': 6}, PN['NET'], 3), ('a certificate error', {'rc': 60}, PN['CERT'], 1),
                                      ('an HTML page', {'body': b'<html>x</html>'}, PN['HTTP'], 3), ('a 404 for the United States', {'rc': 22, 'code': 404}, PN['GONE'], 1)):
        m = machine(chart_site(**{CHART + 'podcasts.json': reply}))
        r, th = start(m, 0); PCN.work(m, th)
        k = len([u for u, _ in m.curl_site.log if 'podcasts.json' in u])
        expect(status(m, 0)['code'] == want and status(m, 0)['count'] == 0 and k == tries, f'{label}: code {want}, {tries} request(s) ({k})')
    # a retry that helps is not repeated after the answer; the next ask after a failure fetches again
    m = machine(chart_site(**{CHART + 'podcasts.json': {'rc': 6}}))
    r, th = start(m, 0); PCN.work(m, th)
    m.curl_site.log.clear(); m.curl_site = chart_site()
    r, th = start(m, 0)
    expect(r == 0 and status(m, 0)['state'] == 1, 'asked again after a failure: it fetches again')
    PCN.work(m, th)
    expect(status(m, 0)['held'] == 1, 'and the chart is there')
    # the fall back: a storefront with no such chart (404) or an empty one answers with the United States', silently, and says so
    log = []
    gb = 'https://rss.marketingtools.apple.com/api/v2/gb/podcasts/top/25/podcasts.json'
    m = machine(chart_site(log, **{gb: {'rc': 22, 'code': 404}}), region=b'GB\n')
    r, th = start(m, 0); PCN.work(m, th)
    st = status(m, 0)
    expect([u for u in urls(m.curl_site) if 'podcasts.json' in u] == [gb, CHART + 'podcasts.json'] and st['code'] == 0 and st['count'] == 25 and country(m, 0) == 'US' and st['held'] == 1,
           f'a 404 for GB: the United States\' chart is asked next and its 25 rows shown, the answer says US ({st}, {country(m, 0)})')
    expect(status(m, 0)['held'] == 1, 'the answer is held for the region asked (GB): it is not asked for again')
    jp = 'https://rss.marketingtools.apple.com/api/v2/jp/podcasts/top/25/podcasts.json'
    m = machine(chart_site(**{jp: {'body': json.dumps({'feed': {'results': []}}).encode()}}), region=b'JP\n')
    r, th = start(m, 0); PCN.work(m, th)
    expect([u for u in urls(m.curl_site) if 'podcasts.json' in u] == [jp, CHART + 'podcasts.json'] and status(m, 0)['count'] == 25 and country(m, 0) == 'US', 'an answer with no rows for JP: the United States\' chart too')
    m = machine(chart_site(**{jp: {'rc': 22, 'code': 500}}), region=b'JP\n')
    r, th = start(m, 0); PCN.work(m, th)
    expect([u for u in urls(m.curl_site) if 'podcasts.json' in u] == [jp] * 3 and status(m, 0)['code'] == PN['HTTP'] and status(m, 0)['count'] == 0, 'a server error for JP is not a missing chart: three requests, the error, no fall back')
    m = machine(chart_site(**{CHART + 'podcasts.json': {'body': json.dumps({'feed': {'results': []}}).encode()}}))
    r, th = start(m, 0); PCN.work(m, th)
    expect(status(m, 0)['state'] == 2 and status(m, 0)['code'] == 0 and status(m, 0)['count'] == 0 and status(m, 0)['held'] == 0, 'an empty United States chart: answered OK with no rows (the page says No results)')
    # the guards
    for label, setup, code in (('no Wi-Fi', lambda m: setattr(m, 'wifi', -1), PN['NOWIFI']), ('a clock never set', lambda m: setattr(m, 'wall', 1700000000), PN['NOCLOCK']),
                               ('no CA bundle', lambda m: m.present.discard(PCN.CA), PN['NOCERT']), ('no card', lambda m: setattr(m, 'card_mounted', False), PN['STORAGE'])):
        m = machine(chart_site()); setup(m)
        r, th = start(m, 0)
        expect(r == code and th is None and status(m, 0)['state'] == 0, f'{label}: pn_chart returns {code}, no worker, no state')
    # Cancel while asking: nothing is held, the state is none (the page asks again)
    m = machine(chart_site())
    r, th = start(m, 0)
    SE.cancel(m)
    PCN.work(m, th)
    expect(status(m, 0)['state'] == 0 and status(m, 0)['held'] == 0 and status(m, 0)['busy'] == 0 and not [u for u, _ in m.curl_site.log if 'mzstatic' in u], 'Cancel while asking: state none, no picture fetched')
    # the lookup of a chart row is made in the store the chart is of
    site = chart_site(**{LOOKUP + '1200361736&country=US': {'body': LOOKUP_DAILY}, LOOKUP + '1200361736': {'body': LOOKUP_DAILY}, FEED_DAILY: {'body': FEED_WSJ}})
    m = machine(site)
    m.thread = None
    r = fn(m, 'pn_preview_chart', m.cstr('1200361736'), m.cstr('US'), m.cstr(''))
    PCN.work(m, m.thread)
    expect(r == 0 and urls(site)[:2] == [LOOKUP + '1200361736&country=US', FEED_DAILY] and fn(m, 'pn_preview_state') == 2 and fn(m, 'pn_preview_code') == 0, f'pn_preview_chart: the lookup has &country=US, then the feed it names ({urls(site)[:2]})')
    m.thread = None
    r = fn(m, 'pn_preview', m.cstr(''), m.cstr('1200361736'), m.cstr(''))
    PCN.work(m, m.thread)
    expect([u for u in urls(site) if u in (LOOKUP + '1200361736', FEED_DAILY)][1:] == [LOOKUP + '1200361736', FEED_DAILY], f'an Apple link\'s lookup (pn_preview) is as before: no country ({urls(site)})')


# ---------------------------------------------------------------------------
# The level
O_ = O


def disc_site(**extra): return SU.site_for(**extra)


def level(**kw):
    """The Podcasts page on the Shows level with a scripted store, the Discover level open and its Shows chart in (the pictures decoded by the loader)."""
    m = SU.opened(site=kw.pop('site', None) or disc_site(**kw))
    return m


def rows(m, off=0):
    return SU.level_rows(m, off)


def texts_style(m, style, off=0):
    return [(PCS.fixed(t), r) for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == style]


def seg_tap(m, k, off=0):
    PCP.tap(m, O_['DC_SEG_X'] + (O_['DC_SEG_W'] // 4 if k == 0 else 3 * O_['DC_SEG_W'] // 4), O_['DC_SEG_Y'] + O_['DC_SEG_H'] // 2, off=off)


def line_text(m):
    return [t for t, r in texts_style(m, 'label_ps_meta')]


def layout_tests(ctx):
    """The level against tools/pod_show.py discover_layout: the large title, the grey line, the control (track and selected pill, labels), the rank, the cover, the text, the chevron, the hairline."""
    expect = ctx.expect
    m = level()
    SU.discover(m)
    L = pod_show.discover_layout(25)
    expect(SU.at_disc(m) and m.props.get((m.sv, 'virtual_h')) == L['h'] and not SU.hint(m), f'the level: large title Discover, no status line, the content is {L["h"]} px (title and control, 25 rows)')
    expect(O_['DC_TOP'] == 128 and L['seg'] == (12, 80, 296, 36) and L['rows'][:2] == [128, 192] and L['h'] == 128 + 25 * 64 + 10, 'the numbers: the control at y 80 (the Downloads page\'s first block), 36 px high, the rows from 128')
    blits, texts, styles, fills = PCP.paint(m, 0)
    ln = [(PCS.fixed(t), r) for (t, r), s in zip(texts, styles) if s == 'label_ps_meta']
    expect(ln and ln[0][0] == 'Top 25 Shows in United States' and ln[0][1][:3] == (O_['PP_LINE_X'], L['line_y'], 320 - 2 * O_['PP_LINE_X']) and ln[0][1][3] == O_['PP_LINE_H'],
           f'the grey line under the title is the Downloads storage line\'s (15 px grey, x {O_["PP_LINE_X"]}, y {L["line_y"]}): "Top 25 Shows in United States" ({ln})')
    sx, sy, sw, sh = L['seg']
    S0, S1 = L['sel']
    fset = set(fills)
    expect(S0['track'] == (12, 80, 296, 36, 18) and S0['thumb'] == (15, 83, 145, 30, 15) and S1['thumb'] == (160, 83, 145, 30, 15) and S0['seps'] == [] and S1['seps'] == [],
           f'the control: a capsule track 296 x 36 (radius 18) at x 12, the thumb a capsule 145 x 30 (radius 15) floating 3 px inside, no separator between two segments ({S0})')
    track, thumb = pod_show.capsule(*S0['track'][:4], S0['track'][4], O_['SEG_TRACK']), pod_show.capsule(*S0['thumb'][:4], S0['thumb'][4], O_['SEG_THUMB'])
    expect(all(f in fset for f in track) and all(f in fset for f in thumb) and len(track) > 40, f'the track (#1C1C1E) and the thumb (#D1D1D6) are painted as the model says: every corner row inset by the circle, smoothed ends ({len(track)} + {len(thumb)} fills)')
    expect(not [f for f in fills if f[0] == O_['SEG_THUMB'] and f[1] >= 160], 'the thumb is on the Shows half only')
    edge = [f for f in track if (f[0] >> 24) not in (0, 0xff)]
    expect(edge and all(f[3] == 1 and f[4] == 1 for f in edge), 'the corners\' ends are single pixels of partial cover (alpha), the rest full')
    lab = {PCS.fixed(t): (r, s) for (t, r), s in zip(texts, styles) if s in ('label_ps_latest', 'label_ps_latestw')}
    expect(lab['Shows'][1] == 'label_ps_latest' and lab['Episodes'][1] == 'label_ps_latestw' and lab['Shows'][0][1] == sy + (sh - O_['SEG_LABEL_H']) // 2, 'the selected label is dark (label_ps_latest), the other white (label_ps_latestw), centred vertically')
    sw_ = PCS.sw().font()
    for k, name in enumerate(('Shows', 'Episodes')):
        w = sw_.width(name, 18)
        expect(abs(lab[name][0][0] + w / 2 - (S0['segs'][k][0] + S0['segs'][k][1] / 2)) <= 1.5, f'the label {name} is centred in its segment ({lab[name][0][0]} + {w} / 2)')
    # the rows: the list painter shifted for the rank
    covers = [tuple(b[2]) for b in blits if tuple(b[2][2:]) == (O_['LIST_ART'], O_['LIST_ART'])]
    expect(covers[:3] == [(L['art_x'], L['rows'][i] + O_['LIST_ART_Y'], O_['LIST_ART'], O_['LIST_ART']) for i in range(3)] and L['art_x'] == 36, f'the covers: {O_["LIST_ART"]} px at x 36 ({covers[:3]})')
    tt = [(PCS.fixed(t), r) for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    ss = [(PCS.fixed(t), r) for (t, r), s in zip(texts, styles) if s == 'label_row_sub']
    expect([t for t, _ in tt[:2]] == ['The Daily', 'Pod Save America'] and tt[0][1][0] == L['text_x'] == 100 and tt[0][1][2] == L['text_end'] - L['text_x'] == 178 and tt[0][1][1] == L['rows'][0] + O_['LIST_TITLE_Y'],
           f'the title at x 100, 178 wide (the text ends at 278), at the list\'s title y ({tt[:2]})')
    gray = [(t, r) for t, r in ss if r[0] == L['text_x']]
    expect([t for t, _ in gray[:2]] == ['The New York Times', 'Pod Save America'] and gray[0][1][1] == L['rows'][0] + O_['LIST_SUB_Y'], f'the grey line: the show\'s author ({gray[:2]})')
    ranks = [(t, r) for t, r in ss if r[0] < 36]
    expect([t for t, _ in ranks[:3]] == ['1', '2', '3'] and all(r[1] == L['rows'][i] + (O_['PC_ROW_H'] - 1 - O_['LIST_SUB_H']) // 2 for i, (t, r) in enumerate(ranks[:3])), f'the ranks 1, 2, 3 in the grey 18 px style, centred on the row above its hairline ({ranks[:3]})')
    sw18 = PCS.sw().font()
    expect(all(abs(r[0] + sw18.width(t, 18) - L['rank_end']) <= 1.5 for t, r in ranks[:9]), 'a rank is right aligned: its text ends at x 28, the single digits and (below) the two digit ones')
    chev = [tuple(b[2]) for b in blits if tuple(b[1]) == (0, 0, 10, 16)]
    expect(chev[:2] == [(L['chev_x'], L['rows'][i] + (O_['PC_ROW_H'] - 1 - 16) // 2, 10, 16) for i in range(2)], f'the shared list chevron at x 288 on each row ({chev[:2]})')
    hair = [f for f in fills if f[0] == O_['LIST_HAIR']]
    expect((O_['LIST_HAIR'], L['text_x'], L['rows'][0] + O_['PC_ROW_H'] - 1, O_['LIST_HAIR_END'] - L['text_x'], 1) in hair, 'the hairline runs from the text (x 100) to x 310')
    # scrolled to the end: ranks 20 to 25 whole, two digits right aligned
    end = L['h'] - 400
    _, texts2, styles2, _ = PCP.paint(m, end)
    rk = [PCS.fixed(t) for (t, r), s in zip(texts2, styles2) if s == 'label_row_sub' and r[0] < 36]
    expect(rk[-1] == '25' and '20' in rk, f'the end of the list: ranks up to 25 ({rk})')
    r2 = [(PCS.fixed(t), r) for (t, r), s in zip(texts2, styles2) if s == 'label_row_sub' and r[0] < 36 and len(PCS.fixed(t)) == 2]
    expect(r2 and all(abs(r[0] + sw18.width(t, 18) - L['rank_end']) <= 1.5 for t, r in r2), 'two digit ranks end at x 28 too')
    # the subtitle follows the tab; the Episodes tab: its own rows, the show under each title
    seg_tap(m, 1)
    work_all(m)
    ln = line_text(m)
    expect(ln and ln[0] == 'Top 25 Episodes in United States', f'the line under the title follows the control: "{ln[:1]}"')
    _, texts3, styles3, fills3 = PCP.paint(m, 0)
    expect(all(f in set(fills3) for f in pod_show.capsule(*S1['thumb'][:4], S1['thumb'][4], O_['SEG_THUMB'])) and not [f for f in fills3 if f[0] == O_['SEG_THUMB'] and f[1] < 160], 'the thumb is on the Episodes half now')
    t3 = [PCS.fixed(t) for (t, r), s in zip(texts3, styles3) if s == 'label_row_title'][:2]
    s3 = [PCS.fixed(t) for (t, r), s in zip(texts3, styles3) if s == 'label_row_sub' and r[0] == L['text_x']][:2]
    expect(t3 == ['The End of Trumpism', 'Blue Tsunami!'] and s3 == ['New York Times Opinion', 'Pod Save America'], f'Top Episodes: the episode title, and its show in grey ({t3}, {s3})')


def on_disc(m):
    """The Discover level is showing (at any offset: the navbar's small title may be in)."""
    return flags(m, 'pg_big')[0] == 1 and SU.text(m, 'pg_big') == 'Discover' and flags(m, 'ps_field')[0] == 0


def work_all(m):
    """Ticks and worker runs until the Discover level is quiet (the harness' threads run when told)."""
    for _ in range(6):
        SU.tick(m)
        if m.thread: SU.work(m)
        else: break
    SU.tick(m)
    SU.settle(m)


def flags(m, n): return SU.flags(m, n)


def segmented_tests(ctx):
    """The shared painter (patch/common.c m1_segmented, m1_capsule) for any number of segments: the track and the thumb of each selection against tools/pod_show.py segmented / capsule, a hairline between two segments
    that are both unselected and none beside the thumb, the labels centred in their segments (dark on the thumb), nothing painted outside the view's rows."""
    expect = ctx.expect
    m = SU.opened()
    PCS.style_px(m)
    words = ['D', 'W', 'M', '6M', 'Y']
    lbl, lens = m.alloc(4 * len(words)), m.alloc(4 * len(words))
    for k, wd in enumerate(words):
        buf = m.alloc(16); m.u.mem_write(buf, b''.join(bytes([ord(c), 0, 0, 0]) for c in wd) + bytes(4))
        m.setword(lbl + 4 * k, buf); m.setword(lens + 4 * k, len(wd))
    on, off = m.widgets['label_ps_latest'], m.widgets['label_ps_latestw']
    x, y, w, h = 16, 40, 288, 36
    for sel in range(5):
        for a, v in enumerate((w, h, 5, sel, on, off, lbl, lens)): m.setword(STACK + 16 + 4 * a, v)
        m.fills.clear(); m.texts.clear(); m.text_styles.clear()
        m.call(PSYMS['m1_segmented'], a0=m.canvas, a1=400, a2=x, a3=y, count=40000000)
        S = pod_show.segmented(x, y, w, h, 5, sel)
        fset = set(m.fills)
        track, thumb = pod_show.capsule(*S['track'][:4], S['track'][4], O_['SEG_TRACK']), pod_show.capsule(*S['thumb'][:4], S['thumb'][4], O_['SEG_THUMB'])
        seps = [f for f in m.fills if f[0] == O_['SEG_SEP']]
        want = [(O_['SEG_SEP'],) + sp for sp in S['seps']]
        expect(all(f in fset for f in track) and all(f in fset for f in thumb), f'five segments, thumb on {sel}: the track and the thumb as the model has them')
        expect(seps == want and [s_[0] for s_ in S['seps']] == [x + 3 + k * 56 for k in range(1, 5) if k - 1 != sel and k != sel] and all(s_[3] == h // 2 and s_[1] == y + h // 4 for s_ in S['seps']),
               f'thumb on {sel}: a {h // 2} px hairline between two unselected segments only, none beside the thumb ({[s_[0] for s_ in S["seps"]]})')
        got = {PCS.fixed(t): (r, st) for (t, r), st in zip(m.texts, m.text_styles)}
        ok = all(got[wd][1] == ('label_ps_latest' if k == sel else 'label_ps_latestw') for k, wd in enumerate(words))
        expect(ok and len(got) == 5, f'thumb on {sel}: the selected label in the dark style, the others in the light one')
    # the last thumb takes what is left of the track (the width does not divide by five)
    S = pod_show.segmented(x, y, 292, h, 5, 4)
    expect(S['thumb'][0] + S['thumb'][2] == x + 292 - 3, 'the last thumb ends 3 px inside the track whatever the width')
    # a view that ends inside the shape: no row outside it is painted
    for a, v in enumerate((w, h, 5, 2, on, off, lbl, lens)): m.setword(STACK + 16 + 4 * a, v)
    m.fills.clear(); m.texts.clear()
    m.call(PSYMS['m1_segmented'], a0=m.canvas, a1=y + 20, a2=x, a3=y, count=40000000)
    expect(m.fills and all(f[2] + f[4] <= y + 20 for f in m.fills) and not m.texts, 'rows below view_h are cut: no fill ends past it, and a label that is not wholly inside is not drawn')
    m.fills.clear()
    for a, v in enumerate((w, h, 5, 2, on, off, lbl, lens)): m.setword(STACK + 16 + 4 * a, v)
    m.call(PSYMS['m1_segmented'], a0=m.canvas, a1=400, a2=x, a3=-20, count=40000000)
    expect(m.fills and all(f[2] >= 0 for f in m.fills), 'rows above the view are cut too')


def switch_tests(ctx):
    """The control: a tap on a half shows that chart; each chart is fetched on its first view only and kept for the session; the offset of each chart is kept; Back from a chart; the small title in the navbar."""
    expect = ctx.expect
    site = chart_site()
    m = SU.opened(site=site)
    PCP.tap_discover(m)
    expect(SU.at_disc(m) and not site.log and SU.hint(m) and SU.hint(m) == 'Loading…', 'a tap on the Discover row: the level opens with Loading... and asks nothing before its first tick')
    SU.tick(m)
    expect(m.thread is not None and m.thread[0] == PSYMS['pn_cmain'], 'the first tick starts the chart job (the Shows chart)')
    SU.work(m); SU.tick(m)
    expect([u for u in urls(site) if 'marketingtools' in u] == [CHART + 'podcasts.json'] and not SU.hint(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.discover_layout(25)['h'],
           'the Shows chart only: the Episodes chart is not fetched until it is viewed; the rows are in')
    SU.settle(m, 8)
    expect(len([u for u in m.loads if u.startswith(f'file://{SDIR}/c0_')]) >= 6, 'the pictures in view are decoded from the search directory, one a tick')
    # a tap on the Episodes half: it is asked for (the first view)
    m.thread = None
    seg_tap(m, 1)
    expect(SU.hint(m) and SU.hint(m) == 'Loading…' and m.props.get((m.sv, 'virtual_h')) == pod_show.discover_layout(0)['h'] and line_text(m)[0] == 'Top 25 Episodes in United States',
           'the Episodes half: Loading..., no rows, its own line under the title')
    SU.tick(m)
    expect(m.thread is not None, 'the next tick starts its job')
    SU.work(m); SU.tick(m)
    expect([u for u in urls(site) if 'marketingtools' in u] == [CHART + 'podcasts.json', CHART + 'podcast-episodes.json'] and not SU.hint(m) and len(rows(m)) >= 4, f'the Episodes chart is fetched once and shown ({[u for u in urls(site) if "marketingtools" in u]}, {SU.hint(m)}, {len(rows(m))}, {status(m, 1)}, {SU.text(m, "label_status")})')
    # scroll the episodes, back to Shows (held: no request), its own offset
    site.log.clear()
    m.setword(m.sv + SC_YOFF, 700); m.props[(m.sv, 'yoffset')] = 700
    seg_tap(m, 0, off=700)
    expect(m.thread is None and not site.log and m.props.get((m.sv, 'yoffset')) == 0 and len(rows(m)) >= 4 and line_text(m)[0] == 'Top 25 Shows in United States', 'back to Shows: the chart is held, nothing is asked, it is at its own offset (the top)')
    m.setword(m.sv + SC_YOFF, 300); m.props[(m.sv, 'yoffset')] = 300
    seg_tap(m, 1, off=300)
    expect(m.props.get((m.sv, 'yoffset')) == 700 and not site.log and m.thread is None, 'and Episodes again: the offset it was left at (700), nothing asked')
    seg_tap(m, 1)
    expect(not site.log, 'a tap on the selected half does nothing')
    # navbar: the magnifier and Now Playing cap; the small title once the large one is gone; Back to the Shows level
    NP = lambda st='normal': m.props[(m.widgets['btn_backtoplayer'], f'style:{st}:icon')]
    expect(flags(m, 'btn_search') == (1, 1) and flags(m, 'btn_more') == (0, 0) and (NP(), NP('pressed')) == ('ah_nav_play', 'ah_nav_play_down'), 'the navbar: Back, the magnifier, Now Playing (its capsule cap)')
    SU.PCP.paint(m, 0)
    m.setword(m.sv + SC_YOFF, 10); fn(m, 'pg_on_scroll', 0, 0, count=4000000)
    expect(flags(m, 'label_title')[0] == 0, 'near the top: no small title')
    m.setword(m.sv + SC_YOFF, O_['SG_COLLAPSE']); fn(m, 'pg_on_scroll', 0, 0, count=4000000)
    expect(flags(m, 'label_title')[0] == 1 and SU.text(m, 'label_title') == 'Discover', 'scrolled past the large title: the navbar says Discover, as the other levels do')
    m.setword(m.sv + SC_YOFF, 0); fn(m, 'pg_on_scroll', 0, 0, count=4000000)
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and flags(m, 'btn_search') == (0, 0) and SU.has_row(m), 'Back: the Shows level (no magnifier), the Discover row there')
    # entering again: the chart is held, no request, the Shows chart at the top
    site.log.clear()
    PCP.tap_discover(m); SU.tick(m)
    expect(not site.log and m.thread is None and len(rows(m)) >= 4 and line_text(m)[0] == 'Top 25 Shows in United States', 'the Discover row again: the held chart at once, nothing fetched (kept for the session)')
    PCP.click(m, 'btn_return')
    # a chart of another region (changed in Settings meanwhile) is asked for again
    m.fs[REGION_FILE] = b'GB\n'
    PCP.tap_discover(m); SU.tick(m)
    expect(m.thread is not None, 'the region changed: the held chart is of another one, it is asked for again')
    SU.work(m); SU.tick(m)
    expect([u for u in urls(site) if 'podcasts.json' in u] == ['https://rss.marketingtools.apple.com/api/v2/gb/podcasts/top/25/podcasts.json'] and line_text(m)[0] == 'Top 25 Shows in UK', 'the request has gb and the line names the UK')


def tap_tests(ctx):
    """A tap on a show row: the lookup of its id (in the chart's store), the feed, the preview; an episode row: the show's id from its url; Back returns to the chart, where it was; Subscribe; already subscribed."""
    expect = ctx.expect
    site = disc_site(**{LOOKUP + '1200361736&country=US': {'body': LOOKUP_DAILY}, FEED_DAILY: {'body': FEED_WSJ}})
    m = SU.opened(site=site)
    SU.discover(m)
    L = pod_show.discover_layout(25)
    m.setword(m.sv + SC_YOFF, 130); m.props[(m.sv, 'yoffset')] = 130
    PCP.tap(m, 150, L['rows'][0] + 30, off=130)
    expect(m.thread is not None and m.thread[0] == PSYMS['pn_pmain'] and not SU.hint(m), 'a tap on the first show: the preview job starts (the status line is not used)')
    sub = [(t, r) for t, r in texts_style(m, 'label_row_sub', 130) if r[0] == L['text_x']]
    expect(sub and sub[0][0] == 'Loading…', f'its grey line reads Loading... meanwhile ({sub[:1]})')
    m.thread, th = None, m.thread
    PCN.work(m, th)
    expect(urls(site)[:2] == [LOOKUP + '1200361736&country=US', FEED_DAILY], f'the lookup of its Apple id in the chart\'s store (US), then the feed it names ({urls(site)[:2]})')
    expect(not [u for u in urls(site) if 'podcastEpisode' in u], 'a show row makes no episode lookup')
    SU.tick(m)
    expect(SU.text(m, 'label_title') == 'WSJ Minute Briefing' and flags(m, 'btn_more') == (0, 0) and flags(m, 'btn_search') == (0, 0) and m.props.get((m.sv, 'yoffset'), 0) == 0, 'the preview opens (the Show page with Subscribe, no "..." and no magnifier)')
    PCP.click(m, 'btn_return')
    expect(on_disc(m) and m.props.get((m.sv, 'yoffset')) == 130 and len(rows(m, 130)) >= 4 and m.call(PSYMS['pn_preview_parser'], count=2000) == 0 and line_text(m)[0] == 'Top 25 Shows in United States',
           'Back: the Discover level, the same chart at the offset it was left (130), the held feed let go')
    sub = [(t, r) for t, r in texts_style(m, 'label_row_sub', 130) if r[0] == L['text_x']]
    expect(sub and sub[0][0] != 'Loading…', 'the row is not Loading any more')
    # Subscribe makes the show; its Back returns to the chart
    m.thread = None
    PCP.tap(m, 150, L['rows'][0] + 30, off=130); SU.work(m); SU.tick(m)
    hdr = PCP.paint(m, 0)
    y_latest = [r[1] for (t, r), s in zip(hdr[1], hdr[2]) if s == 'label_ps_latest'][0]
    PCP.tap(m, 160, y_latest + 10)
    shows, _ = m.shows()
    expect(any(s['feed'] == FEED_DAILY for s in shows) and SU.text(m, 'label_title') == 'WSJ Minute Br…' and flags(m, 'btn_more') == (1, 1), 'Subscribe: the show is made from the preview and the page is its real Show page in place')
    PCP.click(m, 'btn_return')
    expect(on_disc(m), 'Back from it: the chart')
    # the subscribed show opens its real page at once, with no request
    site.log.clear(); m.thread = None
    PCP.tap(m, 150, L['rows'][0] + 30, off=130); SU.work(m); SU.tick(m)
    expect(SU.text(m, 'label_title') == 'WSJ Minute Br…' and flags(m, 'btn_more') == (1, 1), 'a show that is subscribed already: its real Show page after the lookup (nothing is previewed)')
    PCP.click(m, 'btn_return')
    expect(on_disc(m), 'Back: the chart')
    # an episode: the show's id from the url
    m = SU.opened(site=disc_site(**{LOOKUP + f'{NYT_OPINION}&country=US': {'body': LOOKUP_DAILY}, FEED_DAILY: {'body': FEED_WSJ}}))
    SU.discover(m)
    seg_tap(m, 1); work_all(m)
    site = m.curl_site; site.log.clear()
    PCP.tap(m, 150, L['rows'][0] + 30)
    SU.work(m)
    expect(urls(site)[:2] == [LOOKUP + f'{NYT_OPINION}&country=US', FEED_DAILY], f'a tap on an episode: the lookup of its show\'s id {NYT_OPINION} (from the url), not the episode\'s ({urls(site)[:2]})')
    SU.tick(m)
    expect(SU.text(m, 'label_title') == 'WSJ Minute Briefing', 'then the show\'s preview')
    PCP.click(m, 'btn_return')
    expect(SU.at_disc(m) and line_text(m)[0] == 'Top 25 Episodes in United States', 'Back: the Episodes chart (the tab it was left on)')
    # the lookup went to the store the chart is of: a fall back chart (GB asked, US shown) looks up in US
    gb = 'https://rss.marketingtools.apple.com/api/v2/gb/podcasts/top/25/podcasts.json'
    m = SU.opened(site=disc_site(**{gb: {'rc': 22, 'code': 404}, LOOKUP + '1200361736&country=US': {'body': LOOKUP_DAILY}, FEED_DAILY: {'body': FEED_WSJ}}))
    m.fs[REGION_FILE] = b'GB\n'
    SU.discover(m)
    expect(line_text(m)[0] == 'Top 25 Shows in United States', 'a region with no chart: the line names the United States, the store the rows are of')
    site = m.curl_site; site.log.clear()
    PCP.tap(m, 150, L['rows'][0] + 30); SU.work(m)
    expect(urls(site)[0] == LOOKUP + '1200361736&country=US', 'and the lookup of a row is made there too')


EPU, EPD = O['PC_URL'], 32   # pj_ep_t: the url, the release date
REC_E = ID + EPU + NAME + EPD


class PJE:
    """pj_episodes under Unicorn (as PJC): the records with a trackId, the output array at the end of a mapped region."""
    def __init__(self):
        self.m = Machine()
        for base in (REGION, REGION + 0x100000):
            self.m.u.mem_map(base, SIZE)

    def run(self, data, mx=50):
        m = self.m
        src = REGION + SIZE - len(data)
        m.u.mem_write(src, data)
        dst = REGION + 0x100000 + SIZE - mx * REC_E
        m.u.mem_write(dst, bytes([0xAA]) * (mx * REC_E))
        n = m.call(PSYMS['pj_episodes'], a0=src, a1=len(data), a2=dst, a3=mx, count=1 << 40)
        n = n - (1 << 32) if n >= 1 << 31 else n
        raw = bytes(m.u.mem_read(dst, mx * REC_E))
        res = []
        for i in range(max(n, 0)):
            r = raw[i * REC_E:(i + 1) * REC_E]
            f = lambda off, size: r[off:off + size].split(b'\0')[0].decode('utf-8')
            res.append((f(0, ID), f(ID, EPU), f(ID + EPU, NAME), f(ID + EPU + NAME, EPD)))
        return n, res


def episode_json_tests(ctx):
    """The store's episode lookup (pj_episodes) as json.loads has it: the records with a trackId (the show's own too), their fields, nesting, wrong members, cuts, room."""
    expect, P = ctx.expect, PJE()

    def want_of(raw):
        out = []
        for r in json.loads(raw)['results']:
            if 'trackId' not in r: continue
            url = r.get('episodeUrl', '')
            out.append((str(r['trackId']) if str(r['trackId']).isdigit() else '', url if len(url.encode('utf-8')) < EPU else '', cut(r.get('trackName', ''), NAME), cut(r.get('releaseDate', ''), EPD)))
        return [w for w in out if w[0]]
    n, res = P.run(EP_LOOKUP_BODY)
    want = want_of(EP_LOOKUP_BODY)
    expect(n == len(want) == 4 and res == want, f'the fixture: {n} records, the show and three episodes, each as json.loads has them ({res[:1]})')
    expect(res[1][0] == EP_ROW0 and res[1][1] == 'https://pdst.fm/e/traffic.megaphone.fm/GLT8924049806.mp3' and res[1][2] == "Can the Democrats Capitalise on Trump's Midterm Disaster?" and res[1][3] == '2026-11-04T13:17:00Z',
           'the first episode: its trackId, its enclosure (the feed\'s), its title and its releaseDate')
    cases = [
        ([{'trackId': 5, 'trackName': 'y'}, {'trackName': 'no id'}, {'trackId': 0, 'trackName': 'zero'}, {'trackId': '6', 'trackName': 's'}], [('5', '', 'y', ''), ('6', '', 's', '')]),
        ([{'trackId': 9, 'trackName': 'n', 'genres': [{'trackId': 10, 'trackName': 'inner'}]}], [('9', '', 'n', '')]),
        ([{'trackId': 1, 'episodeUrl': 'https://x/' + 'y' * 400}], [('1', '', '', '')]),
        ([{'trackId': 12345678901234567890, 'trackName': 'big'}], []),
        ([{'trackId': 3, 'trackName': 'Café \U0001f399', 'releaseDate': '2026-11-04T13:17:00Z'}], [('3', '', 'Café \U0001f399', '2026-11-04T13:17:00Z')]),
    ]
    for objs, want_case in cases:
        n, res = P.run(json.dumps({'resultCount': len(objs), 'results': objs}, ensure_ascii=False).encode('utf-8'))
        expect(n == len(want_case) and res == want_case, f'records {json.dumps(objs, ensure_ascii=False)[:60]}: {res} (want {want_case})')
    for text, want_n in ((b'{"resultCount":0}', -1), (b'{"results":3}', -1), (b'', -1), (b'[]', -1), (b'{"results":[]}', 0), (b'{"results":[{"trackId":1,"trackName"', 0)):
        n, _ = P.run(text)
        expect(n == want_n, f'{text[:30]!r}: {n}')
    bad = []
    for cutat in range(0, len(EP_LOOKUP_BODY) + 1, 97):
        n, res = P.run(EP_LOOKUP_BODY[:cutat])
        if n >= 0 and res != want[:n]: bad.append((cutat, n))
    expect(not bad, f'cut at every 97th byte: only whole records, as json.loads has them ({bad[:3]})')
    n, res = P.run(EP_LOOKUP_BODY, 2)
    expect(n == 2 and res == want[:2], 'at most max records; the output array is not written past it')


def pf_iso_tests(ctx):
    """pf_iso: the store's releaseDate (ISO 8601 with Z or none, seconds optional), seconds since 1970; anything else is 0."""
    import calendar
    expect, m = ctx.expect, machine()
    t = calendar.timegm((2026, 11, 4, 13, 17, 0))
    for text, want in (('2026-11-04T13:17:00Z', t), ('2026-11-04T13:17:00', t), ('2026-11-04T13:17Z', t), ('2026-11-04 13:17:00', t), ('1970-01-01T00:00:00Z', 0),
                       ('1969-12-31T23:59:59Z', 0), ('2026-13-01T00:00:00Z', 0), ('2026-11-04', 0), ('2026-11-04T13:17:00+01:00', 0), ('Wed, 04 Nov 2026 13:17:00 -0000', 0), ('', 0)):
        got = fn(m, 'pf_iso', m.cstr(text))
        expect(got == want, f'pf_iso {text!r}: {got} (want {want})')


def ep_site(reply=None, extra=None):
    """The scripted store for a Top Episodes row of The Rest Is Politics: the trimmed answers, the episode lookup as reply (default: the fixture)."""
    site = {CHART + 'podcast-episodes.json': {'body': EP_CHART}, RIP_SHOW_URL: {'body': SHOW_RIP}, RIP_FEED: {'body': FEED_RIP}, EP_URL: reply or {'body': EP_LOOKUP_BODY}}
    site.update(extra or {})
    return disc_site(**site)


def ep_open(site, row=0, box=None):
    """Discover > Top Episodes > a tap on row; its preview's worker runs and the tick opens the show's preview (and the episode page on top, when the row matches one)."""
    m = SU.opened(site=site)
    if box is not None: box.append(m)
    SU.discover(m)
    seg_tap(m, 1); work_all(m)
    L = pod_show.discover_layout(25)
    m.curl_site.log.clear()
    PCP.tap(m, 150, L['rows'][row] + 30)
    SU.work(m); SU.tick(m)
    return m


def all_texts(m):
    """(style, text) of everything the page paints, frame by frame (a text is drawn only wholly inside the view)."""
    h = m.props[(m.sv, 'virtual_h')]
    seen = set()
    for off in range(0, max(h - O['GRID_VIEW_H'], 0) + 100, 100):
        seen.update((s, t) for (t, r), s in zip(*PCP.paint(m, off)[1:3]))
    return seen


def on_ep(m): return any(s == 'label_ps_sec' and t.startswith(EP_DESC0) for s, t in all_texts(m))


def match_of(m):
    v = fn(m, 'pn_preview_match')
    return v - (1 << 32) if v >= 1 << 31 else v


def tap_ep_show_row(m):
    PD = pod_show.PD
    y = next(r[1] for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_meta' and r[0] == PD['PD_SHOW_TEXT_X'])
    PCP.tap(m, 150, y + PD['PD_SHOW_TEXT_H'] // 2)


def episode_tests(ctx):
    """A Top Episodes row opens its show's preview and then the episode's page on top: the store's episode lookup (after the feed), then the feed item it is (enclosure, pubDate minute, title);
    no match, a failed lookup or a Cancel leave the show's preview alone; Back goes page, preview, Discover; the show row of the page goes back to the preview."""
    expect = ctx.expect

    def record(**edit):
        d = json.loads(EP_LOOKUP_BODY)
        for r in d['results']:
            if str(r.get('trackId')) == EP_ROW0: r.update(edit)
        return {'body': json.dumps(d, ensure_ascii=False).encode('utf-8')}
    other = 'https://pdst.fm/e/elsewhere.example/other.mp3'
    cases = [
        ({}, 0, 'by enclosure: the lookup\'s episodeUrl is the feed item\'s'),
        (dict(releaseDate='2001-01-01T00:00:00Z', trackName='Something else'), 0, 'by enclosure before date and title'),
        (dict(episodeUrl=other, trackName='Something else'), 0, 'no enclosure: by pubDate to the minute'),
        (dict(episodeUrl=other, trackName='Something else', releaseDate='2026-11-04T13:17:59Z'), 0, 'the same minute (13:17:59) is a date match'),
        (dict(episodeUrl=other, releaseDate='2001-01-01T00:00:00Z'), 0, 'no enclosure, no date: by title, "586. " dropped and the case and spaces ignored'),
        (dict(episodeUrl=other, trackName='Something else', releaseDate='2026-11-04T13:18:00Z'), -1, 'no rule: the show\'s preview alone'),
    ]
    for edit, want, label in cases:
        m = ep_open(ep_site(record(**edit)))
        got = match_of(m)
        expect(got == want and on_ep(m) == (want >= 0) and SU.text(m, 'label_title') == 'The Rest Is Politics' and fn(m, 'pn_preview_code') == 0,
               f'{label}: match {got}, the episode page {"open" if on_ep(m) else "not open"}, the show\'s preview under it')
    # the lookup failing, an answer without the episode, a Cancel during the lookup
    for reply, label in (({'rc': 22, 'code': 500}, 'a failed lookup (HTTP 500)'), ({'body': b'{"resultCount":0,"results":[]}'}, 'an answer with no record of the episode')):
        m = ep_open(ep_site(reply))
        expect(fn(m, 'pn_preview_code') == 0 and match_of(m) == -1 and not on_ep(m) and SU.text(m, 'label_title') == 'The Rest Is Politics',
               f'{label}: the show\'s preview as before, no error')
    box = []

    def cancel_lookup(url, opts):
        SE.cancel(box[0])
        return {'body': EP_LOOKUP_BODY}
    m = ep_open(ep_site(cancel_lookup), box=box)
    expect(fn(m, 'pn_preview_code') == PN['CANCELLED'] and fn(m, 'pn_preview_parser') == 0 and not on_ep(m) and fn(m, 'pn_job_busy') == 0,
           'a Cancel during the episode lookup: the preview is cancelled, nothing is held')
    # the page and the chart's preview: Back goes page, preview, Discover; the show row goes back to the preview
    m = ep_open(ep_site())
    PCP.click(m, 'btn_return')
    expect(not on_ep(m) and SU.text(m, 'label_title') == 'The Rest Is Politics' and fn(m, 'pn_preview_parser') != 0, 'Back from the episode page: the show\'s preview, its feed still held')
    PCP.click(m, 'btn_return')
    expect(on_disc(m) and fn(m, 'pn_preview_parser') == 0, 'Back from the preview: Discover, the feed let go')
    m = ep_open(ep_site())
    tap_ep_show_row(m)
    expect(not on_ep(m) and SU.text(m, 'label_title') == 'The Rest Is Politics' and fn(m, 'pn_preview_parser') != 0 and not on_disc(m),
           f'the show row of the episode page: back to the show\'s preview, not to Discover (page {on_ep(m)}, title {SU.text(m, "label_title")!r}, held {fn(m, "pn_preview_parser") != 0}, disc {on_disc(m)})')
    PCP.click(m, 'btn_return')
    expect(on_disc(m), 'and Back from that preview: Discover')
    # a show row (no episode id) makes no episode lookup and opens no page
    site = ep_site()
    m = SU.opened(site=site)
    SU.discover(m)
    L = pod_show.discover_layout(25)
    PCP.tap(m, 150, L['rows'][0] + 30)
    SU.work(m); SU.tick(m)
    expect(not [u for u in urls(site) if 'podcastEpisode' in u] and match_of(m) == -1, 'a show row: no episode lookup')


def notavail_tests(ctx):
    """A show whose lookup has no feed: its row says Not available, dimmed, no chevron, takes no tap, no toast; a lookup that fails is the toast and the row as it was."""
    expect = ctx.expect
    L = pod_show.discover_layout(25)
    nofeed = {'body': b'{"resultCount":1,"results":[{"collectionName":"No Feed"}]}'}
    m = SU.opened(site=disc_site(**{LOOKUP + '1200361736&country=US': nofeed}))
    SU.discover(m)
    m.calls = []
    PCP.tap(m, 150, L['rows'][0] + 30); SU.work(m); SU.tick(m)
    toasts = SU.toasts(m)
    sub = [(t, r) for t, r in texts_style(m, 'label_row_sub') if r[0] == L['text_x']]
    blits, texts, styles, fills = PCP.paint(m, 0)
    chev = [tuple(b[2]) for b in blits if tuple(b[1]) == (0, 0, 10, 16)]
    expect(sub[0][0] == 'Not available' and sub[1][0] == 'Pod Save America' and (O_['PQ_DIM'], 0, L['rows'][0], 320, O_['PC_ROW_H'] - 1) in fills and not [f for f in fills if f[0] == O_['PQ_DIM'] and f[2] == L['rows'][1]],
           f'the row of the show with no feed: its grey line reads Not available and it is dimmed; the next is not ({sub[:2]})')
    expect(chev[0][1] > L['rows'][1] and (L['chev_x'], L['rows'][1] + (O_['PC_ROW_H'] - 1 - 16) // 2, 10, 16) in chev and not [c for c in chev if L['rows'][0] <= c[1] < L['rows'][1]], f'no chevron on the dimmed row, one on the others ({chev[:2]})')
    expect(not toasts and SU.at_disc(m) and m.thread is None and not SU.hint(m), 'no toast, the level stays')
    m.thread = None; m.calls = []
    PCP.tap(m, 150, L['rows'][0] + 30)
    expect(m.thread is None and SU.at_disc(m), 'a tap on the dimmed row does nothing')
    PCP.tap(m, 150, L['rows'][1] + 30)
    expect(m.thread is not None, 'the next row still opens')
    # the same show in the other chart is dimmed too (the Apple id is what is remembered); its first row (episodes of another show) is not
    # a lookup that fails: the toast, the row as it was
    m = SU.opened(site=disc_site(**{LOOKUP + '1200361736&country=US': {'rc': 22, 'code': 500}}))
    SU.discover(m)
    PCP.tap(m, 150, L['rows'][0] + 30); SU.work(m); SU.tick(m)
    toasts = SU.toasts(m)
    sub = [t for t, r in texts_style(m, 'label_row_sub') if r[0] == L['text_x']]
    expect(toasts == ["Can't subscribe: Server error"] and SU.at_disc(m) and sub[0] == 'The New York Times', f'a failed lookup: the toast says why, the row is as it was ({toasts})')
    PCP.tap(m, 150, L['rows'][0] + 30)
    expect(m.thread is not None, 'and a later tap tries again')
    m = SU.opened(site=disc_site(**{LOOKUP + '1200361736&country=US': {'body': LOOKUP_DAILY}, FEED_DAILY: {'rc': 22, 'code': 404}}))
    SU.discover(m)
    PCP.tap(m, 150, L['rows'][0] + 30); SU.work(m); SU.tick(m)
    expect(SU.toasts(m) == ["Can't subscribe: Feed not found"] and SU.at_disc(m), 'a feed that is gone: Can\'t subscribe: Feed not found, the level stays')
    # no id: a row of the Episodes chart whose url has none is dimmed from the start
    odd = json.dumps({'feed': {'results': [{'id': '1', 'name': 'No Show Id', 'artistName': 'X', 'url': 'https://podcasts.apple.com/us/podcast/x'}, {'id': '2', 'name': 'Has One', 'artistName': 'Y', 'url': 'https://podcasts.apple.com/us/podcast/y/id5?i=2'}]}}).encode()
    m = SU.opened(site=disc_site(**{CHART + 'podcast-episodes.json': {'body': odd}}))
    SU.discover(m)
    seg_tap(m, 1); work_all(m)
    sub = [t for t, r in texts_style(m, 'label_row_sub') if r[0] == L['text_x']]
    expect(sub[:2] == ['Not available', 'Y'], f'an episode whose url names no show is Not available from the start ({sub[:2]})')


def state_tests(ctx):
    """The failure states in the page's words; asking again; No results; the magnifier and Back; the downloads that pause; the refresh that is waited for; leaving while the worker fetches; the screen-off rule."""
    expect = ctx.expect
    for label, reply, word in (('no connection', {'rc': 6}, "Can't connect"), ('a certificate error', {'rc': 60}, 'Certificate problem'), ('HTTP 500', {'rc': 22, 'code': 500}, 'Server error'),
                               ('an HTML page', {'body': b'<html>x</html>'}, 'Server error'), ('a 404', {'rc': 22, 'code': 404}, 'Feed not found')):
        m = SU.opened(site=disc_site(**{CHART + 'podcasts.json': reply}))
        SU.discover(m)
        expect(SU.hint(m) == word and SU.hint(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.discover_layout(0)['h'] and SU.at_disc(m), f'{label}: "{word}" under the control, no rows')
    L0, off = pod_show.discover_layout(0), 30
    d0, d1 = texts_style(m, 'label_ps_cdim', 0), texts_style(m, 'label_ps_cdim', off)
    expect(d0 and d1 and d0[0][1][1] == L0['hint_y'] and d1[0][1][1] == L0['hint_y'] - off, f'the status text is painted in the content, in the middle of the room under the control, and moves with the scroll offset ({d0[:1]}, {d1[:1]})')
    expect(L0['h'] == O_['GRID_VIEW_H'] and O_['DC_TOP'] + 8 + 4 * O_['PS_TITLE_PITCH'] < L0['h'] and m.props.get((m.sv, 'virtual_h')) == L0['h'] and O_['DC_TOP'] < L0['hint_y'] < L0['h'] - O_['PS_TITLE_PITCH'],
           'the content is the view\'s height (the hint\'s room runs to its bottom: nothing to scroll), the text inside it')
    expect(flags(m, 'label_status')[0] == 0, 'the status label is not used on the Discover level')
    # the failed chart is not asked again every tick; switching the control and back (or entering again) asks again
    m = SU.opened(site=disc_site(**{CHART + 'podcasts.json': {'rc': 6}}))
    SU.discover(m)
    m.thread = None; m.calls = []
    SU.tick(m); SU.tick(m)
    expect(m.thread is None and SU.hint(m) == "Can't connect", 'a failed chart is not asked for again by the ticks')
    m.curl_site = disc_site()
    seg_tap(m, 1); work_all(m)
    seg_tap(m, 0); SU.tick(m)
    expect(m.thread is not None, 'a tap on its half asks for it again')
    SU.work(m); SU.tick(m)
    expect(not SU.hint(m) and len(rows(m)) >= 4, 'and its rows come')
    for label, setup, word in (('no Wi-Fi', lambda m: setattr(m, 'wifi', -1), 'No Wi-Fi'), ('a clock never set', lambda m: setattr(m, 'wall', 1700000000), 'Set the date first'),
                               ('no CA bundle', lambda m: m.present.discard(PCN.CA), 'Certificates missing'), ('no card', lambda m: setattr(m, 'card_mounted', False), 'Storage unavailable')):
        m = SU.opened()
        setup(m)
        PCP.tap_discover(m); SU.tick(m)
        expect(m.thread is None and SU.hint(m) == word, f'{label}: the guard\'s words "{word}", no worker')
    # no results
    m = SU.opened(site=disc_site(**{CHART + 'podcasts.json': {'body': json.dumps({'feed': {'results': []}}).encode()}}))
    SU.discover(m)
    expect(SU.hint(m) == 'No results' and SU.hint(m), 'a chart with no rows: No results')
    # the magnifier: the search level; Back returns to the chart; Back again to the Shows level
    m = SU.opened()
    SU.discover(m)
    m.setword(m.sv + SC_YOFF, 200); m.props[(m.sv, 'yoffset')] = 200
    calls = SU.magnifier(m)
    expect(('window_open', 'm1plus_keyboard') in calls and SU.at_search(m) and flags(m, 'btn_search') == (0, 0), 'the magnifier opens the search level (Apple Podcasts, the keyboard asked for), unchanged')
    PCP.click(m, 'btn_return')
    expect(on_disc(m) and m.props.get((m.sv, 'yoffset')) == 200 and len(rows(m, 200)) >= 4 and flags(m, 'label_title')[0] == 1, 'Back from the search: the chart at the offset it was left (the small title shows: the large one is scrolled away)')
    SU.magnifier(m); SU.submit(m, 'all in'); SU.work(m); SU.tick(m)
    expect(len(SU.level_rows(m)) >= 5 and SU.at_search(m), 'a search from here works as from before')
    PCP.click(m, 'btn_return')
    expect(on_disc(m), 'Back from its results: the chart too')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and SU.has_row(m), 'and Back from the chart: the Shows level')
    # a search started from the Shows level path does not exist any more: the keyboard's Back with nothing typed returns to the chart
    # downloads that run go on beside the chart; the refresh in progress is waited for
    DL = sibling('pcdl')
    m = SU.opened()
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 2, seq=1)
    m.setword(DL.pn_at(DL.DKEY), DL.key_of('Sub One', 'a.mp3')); m.setword(DL.pn_at(DL.DBUSY), 1); m.setword(DL.pn_at(DL.DSEQ), 10)
    PCP.tap_discover(m); SU.tick(m)
    expect(m.thread is not None and m.thread[0] == PSYMS['pn_cmain'] and DL.fn(m, 'pn_dl_running') == 1 and SU.hint(m) == 'Loading…',
           'a download runs: the chart thread is created at once (Loading...), the download thread keeps running, nothing is asked to pause')
    SU.work(m); SU.tick(m)
    m.thread = None; m.calls = []; SU.tick(m)
    expect(m.thread is None and 'pthread_create' not in [c[0] for c in m.calls] and DL.fn(m, 'pn_dl_running') == 1, 'afterwards the tick starts nothing: the downloads were never stopped')
    m = SU.opened()
    m.setword(PSYMS['pn'], 1); m.setword(PSYMS['pn'] + 4, 0); m.setword(PSYMS['pn'] + 8, 3)   # a refresh in progress (kind 0)
    PCP.tap_discover(m); SU.tick(m)
    expect(m.thread is None and m.word(SU.SE_CANCEL()) == 0, 'a refresh in progress: the chart waits and does not cancel it')
    # Back while the worker fetches: told to stop, nothing is held, asked again at the next visit
    m = SU.opened()
    PCP.tap_discover(m); SU.tick(m)
    th = m.thread
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and m.word(SU.SE_CANCEL()) == 1, 'Back while the chart is being fetched: the Shows level, the worker is asked to stop')
    m.thread = None; PCN.work(m, th)
    expect(status(m, 0)['state'] == 0 and status(m, 0)['held'] == 0, 'it ends with nothing held')
    PCP.tap_discover(m); SU.tick(m)
    expect(m.thread is not None, 'the next visit asks again')
    # the window destroyed: the pictures go, the worker is told to stop, the answers stay (a new window finds them)
    SU.work(m); SU.tick(m)
    expect(any(p.startswith(SDIR + '/c0_') for p in m.fs), 'the pictures are in the cache directory')
    fn_, ctx_ = m.bound[(m.window, O_['EVT_DESTROY'])]
    m.call(fn_, a0=ctx_, a1=0, count=40000000)
    expect(not [p for p in m.fs if p.startswith(SDIR + '/')] and status(m, 0)['held'] == 1 and status(m, 0)['pending'] == 25, 'the window destroyed: the picture files are gone, the answer is kept')
    m = SU.opened()
    PCP.tap_discover(m); SU.tick(m)
    fn_, ctx_ = m.bound[(m.window, O_['EVT_DESTROY'])]
    m.call(fn_, a0=ctx_, a1=0, count=40000000)
    expect(m.word(SU.SE_CANCEL()) == 1, 'destroyed while the worker runs: it is told to stop')
    # the screen-off rule
    m = SU.opened()
    PCP.tap_discover(m); SU.tick(m); SU.work(m)
    m.screen(False); m.calls = []
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_visible', 'widget_resize', 'widget_invalidate_force', 'widget_set_prop_int')] and status(m, 0)['state'] == 2,
           'the answer is in while the screen is off: the tick does no widget work')
    m.calls = []
    m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'widget_load_image'], 'and the loader decodes nothing in the dark')
    SU.tick(m)
    expect(len(rows(m)) >= 4, 'at the first lit tick the rows are there')


def width_tests(ctx):
    """The strings in 13 languages: the line under the title fits one line for the longest storefront name; the control's labels fit their half; the new Settings strings have a text."""
    expect = ctx.expect
    font = PCS.sw().font()
    names = sorted(pcregion.NAMES, key=lambda n: -font.width(n, 15))[:3]
    worst = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda k, t=t: pod_i18n.TEXT[k][t]
        for key in ('Top 25 Shows in %s', 'Top 25 Episodes in %s'):
            for name in names:
                w = font.width(tr(key).replace('%s', name), 15)
                worst.append((w, loc, key, name))
                expect(w <= 320 - 2 * O_['PP_LINE_X'], f'{loc}: "{tr(key) % name}" ({w} px) fits the line ({320 - 2 * O_["PP_LINE_X"]} px)')
        for key in ('Shows', 'Episodes'):
            w = font.width(tr(key), 18)
            expect(w <= O_['DC_SEG_W'] // 2 - 2 * O_['SEG_PAD'] - 8, f'{loc}: the label "{tr(key)}" ({w} px) fits its half of the control')
        expect(all(tr(k) for k in ('Podcast Region', 'Automatic', 'Search words go to the chosen directory.', 'Podcasts')) and '%s' in tr('Top 25 Shows in %s') and '%s' in tr('Top 25 Episodes in %s'), f'{loc}: the strings have a text, the line\'s keep their %s')
    print('  widest Discover line (px, max %d):' % (320 - 2 * O_['PP_LINE_X']), max(worst))


def asset_tests(ctx):
    """The page's asset: the magnifier is the Radio page's Search button (214, 46, the glass piece pod_nav_search), hidden at first; Now Playing's cap is set by the payload."""
    expect = ctx.expect
    import awtk_ui
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui', 'm1plus_podcasts.bin'), 'rb').read())
    b = tree.find('btn_search')
    expect(b is not None and (b.x, b.w) == (214, 46) and b.get('style:normal:icon') == 'pod_nav_search' and b.get('style:pressed:icon') == 'pod_nav_search_down' and b.get('visible') == 'false' and tree.find('btn_globe') is not None and tree.find('btn_globe').get('visible') == 'false',
           'the Podcasts page has btn_search at x 214, 46 wide, the Radio page\'s glyph, hidden until the Discover level shows it; the Shows level\'s globe is a button of its own')


def spin_tests(ctx):
    """The status line's spinner (patch/podcasts.c pg_hint_busy): the See All row's 14 px frame before Loading… while the chart is asked for, turned by pg_spin_tick; none beside a failure or the rows."""
    expect = ctx.expect
    PCP = SU.PCP
    spin = lambda m: [b for b in PCP.paint(m, 0)[0] if m.bitmaps[b[0]][1:] == (14, 14)]
    dim = lambda m: texts_style(m, 'label_ps_cdim', 0)
    adds = lambda m: [t for t in m.timers if t[0] == SU.PSYMS['pg_spin_tick']]
    L0 = pod_show.discover_layout(0)

    def opened(site):
        m = SU.opened(site=site)
        for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)
        return m
    m = opened(disc_site())
    PCP.tap_discover(m)
    SU.tick(m)
    sp, d = spin(m), dim(m)
    HL = pod_show.hint_layout(O_['DC_TOP'], [SU.PCS.sw().hint_w(m, 'Loading…')], busy=True)
    expect(SU.hint(m) == 'Loading…' and len(sp) == 1 and tuple(sp[0][2][:2]) == HL['spin'] and tuple(d[0][1][:2]) == HL['lines'][0] and HL['lines'][0][0] == HL['spin'][0] + 14 + O_['PS_SPIN_GAP']
           and HL['lines'][0][1] == L0['hint_y'] and HL['spin'][0] > O_['PP_LINE_X'] and abs(HL['spin'][0] - (320 - (HL['lines'][0][0] + SU.PCS.sw().hint_w(m, 'Loading…')))) <= 1,
           f'the chart is asked for: one 14 px spinner and Loading… after it, the two centred as one group across the page and in the room under the control ({[b[2] for b in sp]}, {d[:1]}, {HL})')
    expect(len(adds(m)) == 1, 'one spinner timer')
    a = sp[0][0]
    expect(m.call(SU.PSYMS['pg_spin_tick'], a0=0, count=40000000) == O_['RET_REPEAT'] and spin(m)[0][0] != a, 'the timer turns the frame while the line is busy')
    SU.work(m); SU.tick(m)
    expect(not SU.hint(m) and spin(m) == [] and m.call(SU.PSYMS['pg_spin_tick'], a0=0, count=40000000) != O_['RET_REPEAT'], 'the rows came: no spinner, the timer ends itself')
    m = opened(disc_site(**{CHART + 'podcasts.json': {'rc': 6}}))
    SU.discover(m)
    d = dim(m)
    HL = pod_show.hint_layout(O_['DC_TOP'], [SU.PCS.sw().hint_w(m, "Can't connect")])
    expect(SU.hint(m) == "Can't connect" and spin(m) == [] and tuple(d[0][1][:2]) == HL['lines'][0] and HL['spin'] is None, f'a failure: no spinner, the words centred where the busy line was ({d[:1]}, {HL})')


SECTIONS = [spin_tests, json_tests, episode_json_tests, pf_iso_tests, net_tests, failure_tests, layout_tests, segmented_tests, switch_tests, tap_tests, episode_tests, notavail_tests, state_tests, width_tests, asset_tests]

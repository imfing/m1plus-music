"""Podcast Directory, the worker side (patch/pcnet.c pn_search, pn_pmain; docs/modules/podcasts.md "Podcast Directory"): the search and the lookup of a result's or a link's id go to the chosen directory and to
no other. Apple Podcasts (the default) is the store's search and lookup and never a request to Podcast Index; Podcast Index (file podcast-directory "1") is api.podcastindex.org only, no request to the store, no country,
every request with the app's User-Agent, the same failure and empty states; Discover's charts and a chart row's lookup are the store's whatever is chosen. The picker row and page are tested in test/pod/menu.py
pcdir_row_tests, the search level's title in test/pod/pcsearchui.py directory_tests."""
import json, os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

PCS = sibling('pcsearch')   # noqa: F821  (sibling: the harness helper of the pod tests)
PCN, PN, CA, SEARCH, LOOKUP, F_WSJ = PCS.PCN, PCS.PN, PCS.CA, PCS.SEARCH, PCS.LOOKUP, PCS.F_WSJ
machine, start_search, state, result, fn = PCS.machine, PCS.start_search, PCS.state, PCS.result, PCS.fn
IDX_SEARCH = 'https://api.podcastindex.org/search?limit=25&term='
IDX_LOOKUP = 'https://api.podcastindex.org/lookup?entity=podcast&id='
UA = 'M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)'
DIR_FILE = '/mnt/data/m1plus/podcast-directory'
TERM = '%E6%92%AD%E5%AE%A2%20x'   # the term the tests search for, URL-encoded
OPTS = lambda o: o[10018] == UA and o[10065] == CA and o[52] == 1 and o[45] == 1 and 64 not in o and 81 not in o   # noqa: E731  (the User-Agent, the CA bundle, redirects, fail on error, verification never off)


def rec(i, name, feed='', art=''):
    d = {'collectionId': i, 'trackId': i, 'collectionName': name, 'artistName': 'A', 'artworkUrl100': art}
    if feed: d['feedUrl'] = feed
    return d


def doc(*rs): return json.dumps({'resultCount': len(rs), 'results': list(rs)}).encode()


def search(apple, index, choice=b'1\n'):
    """One search of a term: the store answers apple, Podcast Index index; choice is the file's content (None: no file)."""
    reqs = []

    def site(u, o):
        reqs.append((u, dict(o)))
        if u.startswith(SEARCH): return apple
        if u.startswith(IDX_SEARCH): return index
        return {'rc': 22, 'code': 404}
    m = machine(site=site)
    if choice is not None: m.fs[DIR_FILE] = choice
    r, th = start_search(m, '播客 x')
    if th: PCN.work(m, th)
    return m, r, reqs, state(m)


def apple_tests(ctx):
    expect = ctx.expect
    pi = {'body': doc(rec(11, 'Idx One', 'https://feeds.example/one'))}
    good = {'body': doc(rec(1, 'Apple One', 'https://feeds.example/a1'), rec(2, 'Apple Two', 'https://feeds.example/a2'))}
    for label, choice in (('no file (the default)', None), ('"0"', b'0\n'), ('an empty file', b''), ('"x"', b'x\n'), ('"11"', b'11\n')):
        m, r, reqs, st = search(good, pi, choice)
        expect([u for u, _ in reqs] == [SEARCH + TERM] and st['code'] == 0 and st['count'] == 2 and result(m, 0)[1] == 'Apple One', f'{label}: the store only, the term as ever ({[u for u, _ in reqs]})')
    # every failure and empty state is the store's, and Podcast Index is never asked as a second chance
    for label, ap, code, count in (('no connection', {'rc': 6}, PN['NET'], 0), ('a time-out', {'rc': 28}, PN['NET'], 0), ('HTTP 403', {'rc': 22, 'code': 403}, PN['HTTP'], 0), ('HTTP 429', {'rc': 22, 'code': 429}, PN['HTTP'], 0),
                                   ('an HTML page', {'body': b'<html>x</html>'}, PN['HTTP'], 0), ('no results', {'body': doc()}, 0, 0), ('a result with no feed', {'body': doc(rec(1, 'No Feed'))}, 0, 1)):
        m, r, reqs, st = search(ap, pi, None)
        expect(len(reqs) == 1 and not [u for u, _ in reqs if 'podcastindex' in u] and st['state'] == 3 and st['code'] == code and st['count'] == count and st['busy'] == 0,
               f'Apple Podcasts chosen, {label}: code {code}, {count} result(s), no request to Podcast Index ({st})')


def index_tests(ctx):
    expect = ctx.expect
    ap = {'body': doc(rec(1, 'Apple One', 'https://feeds.example/a1'))}
    pi = {'body': doc(rec(11, 'Idx One', 'https://feeds.example/one'), rec(12, 'Idx Two', 'https://feeds.example/two'))}
    m, r, reqs, st = search(ap, pi)
    expect(r == 0 and [u for u, _ in reqs] == [IDX_SEARCH + TERM] and st['state'] == 3 and st['code'] == 0 and st['count'] == 2 and st['busy'] == 0,
           f'Podcast Index chosen: one request, to api.podcastindex.org with the term encoded, no country, none to the store ({[u for u, _ in reqs]}, {st})')
    expect(result(m, 0)[1] == 'Idx One' and result(m, 0)[3] == 'https://feeds.example/one' and result(m, 1)[3] == 'https://feeds.example/two' and result(m, 2) is None, 'its results show, in its order, with their feeds')
    expect(all(OPTS(o) for _, o in reqs), 'the request has the User-Agent naming the app and its address, the CA bundle, redirects followed and verification never switched off')
    expect(not m.curl and not [p for p in m.fs if p.endswith('.src')], 'no handle left')
    # its failures and empty answers are the normal states
    for label, ix, code, count in (('no connection', {'rc': 6}, PN['NET'], 0), ('a time-out', {'rc': 28}, PN['NET'], 0), ('a certificate error', {'rc': 60}, PN['CERT'], 0),
                                   ('HTTP 403 (a User-Agent it refuses)', {'rc': 22, 'code': 403}, PN['HTTP'], 0), ('HTTP 429', {'rc': 22, 'code': 429}, PN['HTTP'], 0),
                                   ('an HTML page', {'body': b'<html>x</html>'}, PN['HTTP'], 0), ('JSON without results', {'body': b'{"status":"false"}'}, PN['HTTP'], 0),
                                   ('no results', {'body': doc()}, 0, 0), ('a result with no feed', {'body': doc(rec(5, 'No Feed'))}, 0, 1)):
        m, r, reqs, st = search(ap, ix)
        expect([u for u, _ in reqs] == [IDX_SEARCH + TERM] and st['state'] == 3 and st['code'] == code and st['count'] == count and st['busy'] == 0 and not m.curl,
               f'Podcast Index chosen, {label}: code {code}, {count} result(s), the store is not asked ({st})')
    m, r, reqs, st = search(ap, pi, b'1')
    expect([u for u, _ in reqs] == [IDX_SEARCH + TERM], 'the file without its line feed is the same')
    m = machine(site=lambda u, o: pi)
    m.fs[DIR_FILE] = b'1\n'
    expect(PCS.fn(m, 'pn_search', m.cstr('中' * 200)) == PN['MEM'] and state(m)['busy'] == 0, 'a term too long to encode into the request buffer: PN_MEM, nothing started')


def thumbs_tests(ctx):
    """A Podcast Index result's artwork is the feed's own picture (a long address, often 3000 x 3000 and hundreds of KB): fetched up to PN_INDEX_THUMB_CAP (2 MiB) and shrunk to 192 px as a show's cover is.
    The store's artwork keeps its 256 KB cap and is never shrunk."""
    expect = ctx.expect
    import io
    from PIL import Image

    def pic(size, fmt='JPEG', pad=0, **kw):
        b = io.BytesIO(); Image.new('RGB', size, (200, 30, 30)).save(b, fmt, **kw)
        return b.getvalue() + bytes(pad)   # (bytes after the end of the picture: only the size of the download)
    LONG = 'https://image.example/' + 'a' * 220 + '.jpg'   # 246 bytes: over the former 160-byte field
    pics = {LONG: pic((3000, 3000)), 'https://i.example/pad.jpg': pic((1400, 1400), pad=600000), 'https://i.example/big.png': pic((1500, 1000), 'PNG'),
            'https://i.example/small.jpg': PCS.ART, 'https://i.example/prog.jpg': pic((1700, 1400), progressive=True), 'https://i.example/over.jpg': pic((1400, 1400), pad=2200000),
            'https://i.example/' + 'b' * 310 + '.jpg': PCS.ART, 'https://i.example/text.jpg': b'<html>not a picture</html>'}
    rows = [rec(20 + i, f'Show {i}', f'https://feeds.example/{i}', u) for i, u in enumerate(pics)]
    reqs = []

    def site(u, o):
        reqs.append(u)
        if u.startswith((SEARCH, IDX_SEARCH)): return {'body': doc(*rows)}
        return {'body': pics[u], 'chunk': 65536} if u in pics else {'rc': 22, 'code': 404}

    def run(choice):
        reqs.clear()
        m = machine(site=site)
        if choice: m.fs[DIR_FILE] = choice
        r, th = start_search(m, 'x')
        PCN.work(m, th)
        return m, [PCS.thumb(m, i) for i in range(len(rows))]
    m, th = run(b'1\n')
    size = lambda p: p and PCS.Image_size(m.fs[p])   # noqa: E731
    expect(result(m, 0)[4] == LONG and reqs[1] == LONG, 'an artwork address of 246 bytes is kept and asked for')
    expect(th[0] == f'{PCS.SDIR}/t0.jpg' and size(th[0]) == (192, 192) and len(m.fs[th[0]]) < 30000, f'a 3000 x 3000 JPEG is shrunk to 192 px ({size(th[0])})')
    expect(size(th[1]) == (192, 192), 'a picture of over 256 KB is taken (up to 2 MiB) and shrunk')
    expect(th[2] == f'{PCS.SDIR}/t2.jpg' and size(th[2]) == (192, 128), f'a PNG is shrunk to a JPEG, its aspect kept ({size(th[2])})')
    expect(th[3] == f'{PCS.SDIR}/t3.jpg' and m.fs[th[3]] == PCS.ART, 'a picture already small is kept as it is')
    expect(th[4] is None, 'a progressive JPEG of over 2.1 MP has the placeholder')
    expect(th[5] is None, 'a picture of over 2 MiB is refused')
    expect(result(m, 6)[4] == '' and th[6] is None, 'an address of 320 bytes or more is no address')
    expect(th[7] is None, 'an answer that is not a picture has the placeholder')
    expect(PCS.state(m)['state'] == 3 and not m.curl and not [p for p in m.fs if p.endswith(('.src', '.tmp'))], 'the worker ends; no handle, download or temporary file is left')
    # the store's artwork: the 256 KB cap, never shrunk
    m, th = run(None)
    expect(th[3] == f'{PCS.SDIR}/t3.jpg' and m.fs[th[3]] == PCS.ART and th[1] is None and th[0] is None, 'Apple Podcasts chosen: a small picture as it is; one over 256 KB or over 2.1 MP is refused, as before')


def lookup_tests(ctx):
    expect = ctx.expect
    WSJ = PCN.feed_bytes('wsj-3items.xml')

    def run(choice, apple, index, cc=''):
        reqs = []

        def site(u, o):
            reqs.append((u, dict(o)))
            if u.startswith(LOOKUP): return apple
            if u.startswith(IDX_LOOKUP): return index
            if u == F_WSJ: return {'body': WSJ}
            return {'rc': 22, 'code': 404}
        m = machine(site=site)
        if choice is not None: m.fs[DIR_FILE] = choice
        m.thread = None
        if cc: fn(m, 'pn_preview_chart', m.cstr('42'), m.cstr(cc), m.cstr(''))
        else: fn(m, 'pn_preview', m.cstr(''), m.cstr('42'), m.cstr(''))
        if m.thread: PCN.work(m, m.thread)
        return m, reqs

    ok = {'body': doc(rec(42, 'Show', F_WSJ))}
    # an id of a result or a pasted link: the chosen directory's lookup, and only that
    m, reqs = run(b'1\n', {'body': doc(rec(42, 'Wrong', 'https://wrong.example/'))}, ok)
    expect([u for u, _ in reqs][:2] == [IDX_LOOKUP + '42', F_WSJ] and not [u for u, _ in reqs if u.startswith(LOOKUP)] and fn(m, 'pn_preview_code') == 0 and m.read_cstr(fn(m, 'pn_preview_feed')) == F_WSJ and OPTS(reqs[0][1]),
           f'Podcast Index chosen: the id is looked up there, the store is not asked, the feed it names is fetched ({[u for u, _ in reqs]})')
    for choice in (None, b'0\n'):
        m, reqs = run(choice, ok, {'body': doc(rec(42, 'Wrong', 'https://wrong.example/'))})
        expect([u for u, _ in reqs][:2] == [LOOKUP + '42', F_WSJ] and not [u for u, _ in reqs if 'podcastindex' in u] and fn(m, 'pn_preview_code') == 0, f'Apple Podcasts chosen ({choice!r}): the store\'s lookup, none to Podcast Index')
    for label, ix, code in (('no feed', {'body': doc(rec(42, 'Show'))}, PN['NOFEED']), ('no result', {'body': doc()}, PN['NOFEED']), ('a failure', {'rc': 6}, PN['NET']),
                            ('HTTP 429', {'rc': 22, 'code': 429}, PN['HTTP']), ('an HTML page', {'body': b'<html>'}, PN['NOFEED'])):
        m, reqs = run(b'1\n', ok, ix)
        expect(len(reqs) == 1 and fn(m, 'pn_preview_code') == code and fn(m, 'pn_preview_parser') == 0 and fn(m, 'pn_job_busy') == 0, f'Podcast Index chosen, its lookup gives {label}: code {code}, nothing held, the store is not asked as a second chance')
    # a chart row: the store's lookup (in the chart's country) and its episode match, whatever is chosen
    for choice in (None, b'1\n'):
        m, reqs = run(choice, ok, {'body': doc(rec(42, 'Wrong', 'https://wrong.example/'))}, cc='JP')
        expect(reqs[0][0] == LOOKUP + '42&country=JP' and not [u for u, _ in reqs if 'podcastindex' in u] and fn(m, 'pn_preview_code') == 0, f'a chart row (choice {choice!r}): the store\'s lookup in the chart\'s country, none to Podcast Index ({[u for u, _ in reqs][:2]})')


def charts_tests(ctx):
    """Discover's charts are the store's alone: the chart job asks rss.marketingtools.apple.com, never Podcast Index, with either choice."""
    expect = ctx.expect
    chart = open(os.path.join(ROOT, 'test', 'data', 'discover', 'top-shows-us-50.json'), 'rb').read()
    for choice in (None, b'1\n'):
        reqs = []

        def site(u, o):
            reqs.append(u)
            return {'body': chart, 'chunk': 8192} if 'marketingtools' in u else {'rc': 22, 'code': 404}
        m = machine(site=site)
        if choice is not None: m.fs[DIR_FILE] = choice
        m.thread = None
        r = fn(m, 'pn_chart', 0)
        if m.thread: PCN.work(m, m.thread)
        expect(r == 0 and reqs and all('marketingtools.apple.com' in u or u.startswith('https://is') for u in reqs) and not [u for u in reqs if 'podcastindex' in u], f'the shows chart (choice {choice!r}): only the store\'s address ({reqs[:2]})')


SECTIONS = [apple_tests, index_tests, thumbs_tests, lookup_tests, charts_tests]

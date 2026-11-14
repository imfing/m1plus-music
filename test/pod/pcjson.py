"""The JSON extractor for the iTunes search and lookup answers (patch/pcjson.c, docs/modules/podcasts.md "Search"): three real answers (the store's own, cut to the fields the payload keeps by
Python's json module as the oracle), escapes and \\u surrogate pairs, UTF-8 cuts, missing fields, nesting, truncation and the 96 KB cap, and fuzzing: random cuts and byte flips never crash
or read or write outside the buffers (the input ends at an unmapped page, the output array too)."""
import json, os, random, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DATA = os.path.join(ROOT, 'test', 'data', 'search')
NAME, AUTHOR, URL, ART = 80, 56, 320, 320
REC = 4 + NAME + AUTHOR + URL + 2 * ART
REGION, SIZE = 0x30000000, 0x40000   # the input and the output each get a mapped region ending where a page is unmapped


def oracle(text, cap=None):
    """[(id, name, author, feed, art)] the documented way: the results that have a name or a feed, strings cut at their field's size (a url that does not fit is none)."""
    d = json.loads(text)
    out = []
    for r in d['results']:
        name, author = cut(r.get('collectionName', ''), NAME), cut(r.get('artistName', ''), AUTHOR)
        feed, art = r.get('feedUrl', ''), r.get('artworkUrl100', '')
        feed = feed if len(feed.encode('utf-8')) <= URL - 1 else ''
        art = art if len(art.encode('utf-8')) <= ART - 1 else ''
        if name or feed: out.append((min(r.get('collectionId', 0), 0xffffffff), name, author, feed, art))
    return out


class PJ:
    """pj_results under Unicorn: the input ends at the end of a mapped region (an unmapped page follows), so a read past it faults; so does the output array's end."""
    def __init__(self):
        self.m = Machine()
        for base in (REGION, REGION + 0x100000):
            self.m.u.mem_map(base, SIZE)

    def run(self, data, mx=25):
        m = self.m
        src = REGION + SIZE - len(data)
        m.u.mem_write(src, data)
        dst = REGION + 0x100000 + SIZE - mx * REC
        m.u.mem_write(dst, bytes([0xAA]) * (mx * REC))
        n = m.call(PSYMS['pj_results'], a0=src, a1=len(data), a2=dst, a3=mx, count=1 << 40)
        n = n - (1 << 32) if n >= 1 << 31 else n
        raw = bytes(m.u.mem_read(dst, mx * REC))
        res = []
        for i in range(mx):
            r = raw[i * REC:(i + 1) * REC]
            f = lambda off, size: r[off:off + size].split(b'\0')[0]
            res.append((struct.unpack('<I', r[:4])[0], f(4, NAME), f(4 + NAME, AUTHOR), f(4 + NAME + AUTHOR, URL), f(4 + NAME + AUTHOR + URL, ART), r, f(4 + NAME + AUTHOR + URL + ART, ART)))
        return n, res[:max(n, 0)], raw


def kept(res):
    """The first n results as text: (id, name, author, feed, art)."""
    return [(r[0], r[1].decode('utf-8'), r[2].decode('utf-8'), r[3].decode('utf-8'), r[4].decode('utf-8')) for r in res]


def obj(**kw):
    return json.dumps(kw, ensure_ascii=False)


def doc(*objs, tail=''):
    return ('{"resultCount": %d, "results": [%s]%s}' % (len(objs), ', '.join(objs), tail)).encode('utf-8')


def real_tests(ctx):
    """The store's answers: every result's five members as the oracle (json.loads) has them; one is a result with no feedUrl; the lookup answer."""
    expect, P = ctx.expect, PJ()
    files = sorted(f for f in os.listdir(DATA) if f.endswith('.json') and f.startswith(('all_in', 'gushi', 'top_of')))
    assert len(files) == 3
    for f in files:
        raw = open(os.path.join(DATA, f), 'rb').read()
        want = oracle(raw.decode('utf-8'))
        n, res, _ = P.run(raw)
        expect(n == len(want) == min(len(json.loads(raw)['results']), 25) and kept(res) == want, f'{f} ({len(raw)} bytes): {n} results, every id, name, author, feed and artwork as json.loads has them')
        n3, res3, raw3 = P.run(raw, 3)
        expect(n3 == 3 and kept(res3) == want[:3] and len(raw3) == 3 * REC, f'{f}: with room for three it keeps three, the first three')
    raw = open(os.path.join(DATA, 'lookup_1493503146.json'), 'rb').read()
    n, res, _ = P.run(raw, 1)
    expect(n == 1 and res[0][0] == 1493503146 and res[0][1].decode() == '忽左忽右' and res[0][3].decode() == 'https://feed.xyzfm.space/cv4bkgpuglwp', 'the lookup answer: the id, the name and the feed address')
    # artworkUrl600 (The Rest Is Politics, fetched 2026-11-06; its 600 x 600 picture is a baseline JPEG of about 100 KB): kept beside artworkUrl100
    raw = open(os.path.join(DATA, 'lookup_1611374685.json'), 'rb').read()
    want = json.loads(raw)['results'][0]
    n, res, _ = P.run(raw, 1)
    expect(n == 1 and res[0][0] == 1611374685 and res[0][4].decode() == want['artworkUrl100'] and res[0][6].decode() == want['artworkUrl600'] and res[0][6].endswith(b'/600x600bb.jpg'),
           'the lookup answer of a show whose feed picture is progressive: artworkUrl600 is kept (144 bytes) beside artworkUrl100')
    n, res, _ = P.run(doc(obj(collectionName='L', artworkUrl600='https://i/' + 'b' * 310), obj(collectionName='M', artworkUrl600='https://i/' + 'b' * 309), obj(collectionName='N')))
    expect(n == 3 and [r[6] for r in res] == [b'', b'https://i/' + b'b' * 309, b''], 'artworkUrl600: one byte too long is none, one that fills the field is kept, a missing one is empty (and never lands in artworkUrl100)')


def string_tests(ctx):
    """Escapes, \\u with surrogate pairs, raw UTF-8, controls, cuts on character boundaries."""
    expect, P = ctx.expect, PJ()

    def name_of(raw_name):
        n, res, _ = P.run(('{"results":[{"collectionName":"%s"}]}' % raw_name).encode('utf-8') if isinstance(raw_name, str) else b'{"results":[{"collectionName":"' + raw_name + b'"}]}')
        return res[0][1] if n == 1 else None
    expect(name_of(r'a\"b\\c\/d') == b'a"b\\c/d', 'the escapes \\" \\\\ \\/')
    expect(name_of(r'a\nb\tc\rd\be\ff') == b'a b c d e f', 'the control escapes are spaces')
    expect(name_of(r'café 中文 €') == 'café 中文 €'.encode(), '\\uXXXX to UTF-8 in one, two and three bytes')
    expect(name_of(r'🎙 mic') == '\U0001f399 mic'.encode() and name_of(r'x🎙y') == 'x\U0001f399y'.encode(), 'a surrogate pair is one four byte character (either case of the hex digits)')
    expect(name_of(r'a\ud83cb') == b'ab' and name_of(r'a\udf99b') == b'ab' and name_of(r'a\ud83cAb') == b'aAb' and name_of(r'a\ud83c') == b'a', 'a lone surrogate is dropped (a high one before an ordinary \\u too)')
    expect(name_of(r'a\u0000b') == b'ab' and name_of(r'a\u0007b') == b'a b' and name_of(r'a\u12b') == b'a12b' and name_of(r'a\uZZZZb') == b'aZZZZb', '\\u0000 is dropped, another control is a space, a \\u without four hex digits is dropped')
    expect(name_of(r'a\qb') == b'aqb' and name_of('x\\é') == 'xé'.encode(), 'an unknown escape is its character; a backslash before a multi-byte character leaves the character')
    expect(name_of('tab\there') == b'tab here' and name_of('new\nline') == b'new line' and name_of(bytes([0x61, 0x01, 0x62])) == b'a b', 'a raw control character is a space')
    expect(name_of(b'a\xc3b') == b'ab' and name_of(b'a\xff\xfeb') == b'ab' and name_of(b'a\xc0\x80b') == b'ab' and name_of(b'a\xed\xa0\x80b') == b'ab' and name_of(b'a\xf4\x90\x80\x80b') == b'ab'
           and name_of(b'a\xe4\xb8') == b'a', 'bytes that are not UTF-8 (a lone lead, 0xff, an overlong, a surrogate, past U+10FFFF) are dropped')
    expect(name_of('日本語のポッドキャスト') == '日本語のポッドキャスト'.encode(), 'raw UTF-8 as it is')
    long_cjk = '中' * 40
    got = name_of(long_cjk)
    expect(got == ('中' * 26).encode() and len(got) == 78, f'a 120 byte name is cut at 79 bytes on a character boundary (26 characters, {len(got)} bytes)')
    got = name_of('é' * 60)
    expect(got == ('é' * 39).encode(), 'two byte characters: 39 of them (78 bytes)')
    got = name_of('x' * 79 + '中')
    expect(got == b'x' * 79, 'the cut character is not half-written')
    got = name_of('\U0001f399' * 30)
    expect(got == ('\U0001f399' * 19).encode(), 'four byte characters: 19 of them (76 bytes)')
    got = name_of('x' * 10 + ''.join('\\u%04x' % ord(c) for c in '中' * 40))
    expect(got == b'x' * 10 + ('中' * 23).encode(), 'an escaped character that does not fit is cut as whole')
    n, res, raw = P.run(doc(obj(collectionName='n', artistName='中' * 30)))
    expect(res[0][2] == ('中' * 18).encode(), 'the author is cut at 55 bytes the same way (18 characters)')
    # the key is compared decoded: an escaped key is the key; a key that is longer is none
    n, res, _ = P.run(b'{"results":[{"collection\\u004eame":"esc","collectionNameXXXXXXXXXXXXXXXXXXXXXXXXXX":"no"}]}')
    expect(n == 1 and res[0][1] == b'esc', 'a key with an escape is the key; a longer key is not')


def field_tests(ctx):
    """Missing fields, long addresses, ids, order and duplicate members."""
    expect, P = ctx.expect, PJ()
    n, res, _ = P.run(doc(obj(collectionName='A', feedUrl='https://f/a'), obj(collectionName='B'), obj(feedUrl='https://f/c'), obj(artistName='nobody'), obj(collectionId=5)))
    expect(n == 3 and kept(res) == [(0, 'A', '', 'https://f/a', ''), (0, 'B', '', '', ''), (0, '', '', 'https://f/c', '')], 'an object is kept with a name or a feed; the missing fields are empty; one with neither is no result')
    n, res, _ = P.run(doc(obj(collectionName='L', feedUrl='https://f/' + 'a' * 309, artworkUrl100='https://i/' + 'b' * 309)))
    expect(n == 1 and len(res[0][3]) == 319 and len(res[0][4]) == 319, 'an address that fills its field (319 bytes each) is kept')
    n, res, _ = P.run(doc(obj(collectionName='L', feedUrl='https://f/' + 'a' * 310, artworkUrl100='https://i/' + 'b' * 310)))
    expect(n == 1 and res[0][3] == b'' and res[0][4] == b'' and res[0][1] == b'L', 'an address one byte too long is none (a cut address is no address), the result stays')
    for text, want in (('1493503146', 1493503146), ('4294967295', 4294967295), ('4294967296', 0xffffffff), ('99999999999999999999', 0xffffffff), ('-5', 0), ('12.7', 12), ('1e3', 1), ('0', 0)):
        n, res, _ = P.run(('{"results":[{"collectionName":"x","collectionId":%s}]}' % text).encode())
        expect(n == 1 and res[0][0] == want, f'collectionId {text} is {want:#x}')
    n, res, _ = P.run(b'{"results":[{"collectionName":"x","collectionId":"77"}]}')
    expect(n == 1 and res[0][0] == 0, 'an id given as a string is none')
    n, res, _ = P.run(b'{"results":[{"collectionName":"first","collectionName":"second","feedUrl":"https://a","feedUrl":"https://b"}]}')
    expect(n == 1 and kept(res) == [(0, 'second', '', 'https://b', '')], 'a member given twice: the last one')
    n, res, _ = P.run(b'{"results":[{"collectionName":5,"artistName":["x"],"feedUrl":{"a":1},"artworkUrl100":null,"collectionId":true}]}')
    expect(n == 0, 'members of the wrong type are skipped (nothing left: no result)')
    n, res, _ = P.run(b'{"results":[{"collectionName":"n","artistName":{"nested":{"collectionName":"inner","feedUrl":"https://inner"}},"x":[1,[2,{"feedUrl":"https://deep"}]]}]}')
    expect(n == 1 and kept(res) == [(0, 'n', '', '', '')], 'members of nested values are not the object\'s: only its own five count')
    n, res, _ = P.run(b' \n\t{ "a" : "x]}[{" , "results" : [ 1, "s", [ {"collectionName": "skip me"} ], null, { "collectionName" : "ok" , "feedUrl":"https://f" } ] , "b":3 } ')
    expect(n == 1 and kept(res) == [(0, 'ok', '', 'https://f', '')], 'white space, strings that hold brackets, a results array of mixed values: only the object counts')
    n, res, _ = P.run(b'{"resultCount":0,"results":[]}')
    expect(n == 0, 'an empty results array is no result')
    for text in (b'', b'  ', b'[]', b'{}', b'{"resultCount":0}', b'{"results":3}', b'{"results":{"a":1}}', b'{"results":"[]"}', b'null', b'<html>', b'{"results"', b'{"results":', b'{"x":[1,2', b'"results"'):
        n, _, _ = P.run(text)
        expect(n == -1, f'no results array: {text[:30]!r} is -1')
    n, res, _ = P.run(b'{"results":[{"collectionName":"a"}]}', 0)
    expect(n == -1, 'no room: -1, and nothing is written')
    n, res, raw = P.run(b'{"results":[{"collectionName":"a"},{"collectionName":"b"},{"collectionName":"c"}]}', 2)
    expect(n == 2 and kept(res) == [(0, 'a', '', '', ''), (0, 'b', '', '', '')], 'at most max results; the output array is not written past it (it ends at an unmapped page)')


def depth_tests(ctx):
    """Nesting is skipped without recursion up to 32 deep; deeper ends the walk, keeping what was found."""
    expect, P = ctx.expect, PJ()
    deep = lambda k: '[' * k + ']' * k
    n, res, _ = P.run(('{"results":[{"collectionName":"a","x":%s}]}' % deep(32)).encode())
    expect(n == 1, 'a member nested 32 deep is skipped')
    n, res, _ = P.run(('{"results":[{"collectionName":"a"},{"collectionName":"b","x":%s},{"collectionName":"c"}]}' % deep(33)).encode())
    expect(n == 1 and res[0][1] == b'a', 'one nested 33 deep ends the walk: the results before it stay, the object it is in does not')
    n, _, _ = P.run(('{"junk":%s,"results":[{"collectionName":"a"}]}' % deep(40)).encode())
    expect(n == -1, 'a top-level member that is too deep ends the walk (no results array found)')
    n, _, _ = P.run(b'{"results":[' + b'{"a":' * 5000)
    expect(n == 0, 'five thousand unclosed objects: no result, no stack use (the walk is iterative)')


def truncation_tests(ctx):
    """A text cut anywhere gives exactly the results that were complete before the cut; the 96 KB cap (the worker's) cuts mid-object."""
    expect, P = ctx.expect, PJ()
    raw = open(os.path.join(DATA, 'top_of_japan_us.json'), 'rb').read()
    full = oracle(raw.decode())
    ends, depth, instr, esc, start = [], 0, False, False, raw.index(b'[', raw.index(b'"results"'))
    for i in range(start, len(raw)):
        c = raw[i]
        if instr:
            if esc: esc = False
            elif c == 0x5c: esc = True
            elif c == 0x22: instr = False
        elif c == 0x22: instr = True
        elif c in b'{[': depth += 1
        elif c in b'}]':
            depth -= 1
            if depth == 1 and c == 0x7d: ends.append(i + 1)
    bad = []
    for cutat in range(0, len(raw) + 1, 7):
        n, res, _ = P.run(raw[:cutat])
        k = sum(e <= cutat for e in ends)
        if raw[:cutat].find(b'"results"') < 0 or raw[:cutat].find(b'[', raw[:cutat].find(b'"results"')) < 0: want = -1
        else: want = k
        if n != want or kept(res) != full[:max(want, 0)]: bad.append((cutat, n, want))
    expect(not bad, f'cut at every 7th byte: the results complete before the cut and no others ({bad[:5]})')
    pad = 'x' * 50000
    big = doc(obj(collectionName='one', note=pad), obj(collectionName='two', note='y' * 60000), obj(collectionName='three'))
    n, res, _ = P.run(big[:98304])
    expect(len(big) > 98304 and n == 1 and res[0][1] == b'one', f'a 96 KB cap in the middle of the second result (of {len(big)} bytes) keeps the first only')
    n, res, _ = P.run(big)
    expect(n == 3, 'and the whole text all three')


def fuzz_tests(ctx):
    """Random cuts and byte flips over the real answers (and a hand-made nasty one): nothing faults (the input and the output end at unmapped pages), the count is within max, every string is
    terminated inside its field and valid UTF-8, and a cut text gives a prefix of the whole text's results."""
    expect, P = ctx.expect, PJ()
    rnd = random.Random(20261031)
    seeds = [open(os.path.join(DATA, f), 'rb').read()[:9000] for f in ('all_in_us.json', 'gushi_fm_us.json', 'top_of_japan_us.json')]
    seeds.append(r'{"results":[{"collectionName":"🎙 中文 \"q\"","artistName":"é","feedUrl":"https://a/b","collectionId":12,"n":[[{"a":"\\"}]]},{"collectionName":"b"}]}'.encode())
    bad, runs, flips = [], 0, 0
    for _ in range(260):
        data = bytearray(rnd.choice(seeds))
        mode = rnd.choice(('cut', 'flip', 'both', 'junk'))
        if mode in ('flip', 'both'):
            for _ in range(rnd.randint(1, 12)):
                data[rnd.randrange(len(data))] = rnd.choice((rnd.randrange(256), ord('"'), ord('\\'), ord('{'), ord('}'), ord('['), ord(']'), ord(','), ord(':'), 0xff, 0xc3, 0xe4))
                flips += 1
        if mode in ('cut', 'both'): data = data[:rnd.randrange(len(data) + 1)]
        if mode == 'junk': data = bytearray(rnd.randrange(256) for _ in range(rnd.randint(0, 300)))
        mx = rnd.choice((25, 25, 1, 3, 7))
        try:
            n, res, raw = P.run(bytes(data), mx)
        except Exception as ex:   # noqa: BLE001 - an emulation fault is the failure
            bad.append((mode, len(data), str(ex)[:60]))
            continue
        runs += 1
        if not -1 <= n <= mx: bad.append((mode, 'count', n))
        for r in res:
            for off, size, v in ((4, NAME, r[5][4:4 + NAME]), (4 + NAME, AUTHOR, r[5][4 + NAME:4 + NAME + AUTHOR]), (4 + NAME + AUTHOR, URL, r[5][4 + NAME + AUTHOR:4 + NAME + AUTHOR + URL]),
                                 (4 + NAME + AUTHOR + URL, ART, r[5][4 + NAME + AUTHOR + URL:4 + NAME + AUTHOR + URL + ART]), (4 + NAME + AUTHOR + URL + ART, ART, r[5][4 + NAME + AUTHOR + URL + ART:])):
                if 0 not in v: bad.append((mode, 'unterminated', off)); continue
                try: v.split(b'\0')[0].decode('utf-8')
                except UnicodeDecodeError: bad.append((mode, 'not utf-8', off))
                if any(b < 0x20 for b in v.split(b'\0')[0]): bad.append((mode, 'control', off))
    expect(runs >= 250 and not bad, f'{runs} fuzzed texts ({flips} flipped bytes): no fault, a count within max, every string terminated, valid UTF-8, without control bytes ({bad[:4]})')
    # cuts of one whole answer: a prefix of the results of the whole
    raw = seeds[2]
    n0, res0, _ = P.run(raw)
    whole = kept(res0)
    prefix_ok = True
    for _ in range(80):
        n, res, _ = P.run(raw[:rnd.randrange(len(raw))])
        if n >= 0 and kept(res) != whole[:n]: prefix_ok = False
    expect(prefix_ok, 'a text cut anywhere gives a prefix of the whole text\'s results')


SECTIONS = [real_tests, string_tests, field_tests, depth_tests, truncation_tests, fuzz_tests]

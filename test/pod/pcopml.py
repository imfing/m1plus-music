"""OPML import and export of the Podcasts subscriptions (patch/pcopml.c, patch/pcnet.c pn_import / pn_export, docs/modules/podcasts.md "Subscriptions and OPML").

The scanner po_next: three realistic exports (in the style of Apple Podcasts, Pocket Casts and Overcast: test/data/opml) against Python's xml.etree as the oracle, then the syntax cases (nesting,
entities, quotes, attribute order and case, missing attributes, comments / CDATA / DOCTYPE, a '>' inside a quote, cut tags, every cut of every sample) and fuzzing: the input ends at an unmapped
page and so does the item, so any overrun faults. The import of subscriptions.txt and OPML together (the PC_MAX_SHOWS cap, duplicates, the rename to .imported, a dot file, a failed write) and the export
(escaping, order, the atomic write, a failed write, a round trip through the scanner)."""
import os, random
import xml.etree.ElementTree as ET
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'test', 'data', 'opml')
URL, TITLE = 320, 96
ITEM = URL + TITLE
REGION, SIZE = 0x30000000, 0x40000   # the text, the item and the scanner state each end where a page is unmapped


PCN = sibling('pcnet')
ROOT_DIR, CARD = PCN.ROOT_DIR, '/mnt/mmc'


def sample(name): return open(os.path.join(DATA, name), 'rb').read()


def collapse(s): return ' '.join(s.replace('\xa0', ' ').split())


def url_ok(u): return u.startswith(('http://', 'https://')) and len(u) > (7 if u.startswith('http:') else 8) and ' ' not in u and len(u.encode()) <= URL - 1


def oracle(raw):
    """[(url, title)] of the outlines of a well formed document the documented way (the text attribute, else title; white space collapsed; the title cut at 95 bytes)."""
    out = []
    for el in ET.fromstring(raw).iter():
        if el.tag != 'outline': continue
        u = el.get('xmlUrl', '').strip()
        if not url_ok(u): continue
        t = collapse(el.get('text', '')) or collapse(el.get('title', ''))
        out.append((u, cut(t, TITLE)))
    return out


class PO:
    """po_open / po_next under Unicorn: the text, the item and the scanner state each end at the end of a mapped region (an unmapped page follows)."""
    def __init__(self):
        self.m = Machine()
        for base in (REGION, REGION + 0x100000, REGION + 0x200000):
            self.m.u.mem_map(base, SIZE)

    def scan(self, data, limit=5000, raw=False):
        m = self.m
        src = REGION + SIZE - len(data)
        m.u.mem_write(src, data)
        st = REGION + 0x200000 + SIZE - 8
        item = REGION + 0x100000 + SIZE - ITEM
        m.call(PSYMS['po_open'], a0=st, a1=src, a2=len(data), count=2000)
        out = []
        for _ in range(limit):
            m.u.mem_write(item, bytes([0xAA]) * ITEM)
            if not m.call(PSYMS['po_next'], a0=st, a1=item, count=1 << 40): break
            b = bytes(m.u.mem_read(item, ITEM))
            u, t = b[:URL], b[URL:]
            assert 0 in u and 0 in t, 'url and title are terminated inside their fields'
            out.append((u.split(b'\0')[0], t.split(b'\0')[0]) if raw else (u.split(b'\0')[0].decode('utf-8'), t.split(b'\0')[0].decode('utf-8')))
        else: raise AssertionError('po_next does not end')
        return out


def real_tests(ctx):
    """The three exports: every outline with a feed address, the names, in order, equal to the oracle's; the apple one has an entity in a title and in a url, a Chinese name; Overcast's single quotes, a folder with no address, a title only."""
    expect, P = ctx.expect, PO()
    got = {}
    for f in ('apple_podcasts.opml', 'pocketcasts.opml', 'overcast.opml'):
        raw = sample(f)
        got[f] = P.scan(raw)
        want = oracle(raw)
        expect(got[f] == want and len(want) >= 6, f'{f}: {len(want)} feeds, as xml.etree reads them ({[x for x in got[f] if x not in want][:2]})')
    a = dict((t, u) for u, t in got['apple_podcasts.opml'])
    expect(a['Reply All & Friends'] == 'https://feeds.megaphone.fm/replyall?x=1&y=2' and '日谈公园' in a, 'entities in a name and in an address; a Chinese name')
    o = dict((t, u) for u, t in got['overcast.opml'])
    expect(len(got['overcast.opml']) == 6 and o['Only A Title'] == 'https://example.org/only-title.xml' and o['Under the Radar'] == 'https://www.relay.fm/radar/feed' and 'All Episodes' not in o,
           'Overcast: single quotes, the playlist folder and its outline without an address are not feeds, a title with no text attribute names the show')
    p = dict((t, u) for u, t in got['pocketcasts.opml'])
    expect(p['Podcast "Quoted" Name'] == 'http://example.com/feed.rss?a=1&b=2' and "Conan O'Brien Needs a Friend" in p, 'Pocket Casts: &quot; and &apos; in a name, &amp; in an address')


CASES = [   # (name, text, [(url, title)])
    ('nested', b'<opml><body><outline text="A"><outline text="B"><outline type="rss" text="X" xmlUrl="http://x/1"/></outline></outline><outline text="X2" xmlUrl="https://x/2"></outline></body></opml>',
     [('http://x/1', 'X'), ('https://x/2', 'X2')]),
    ('quotes', b"<outline xmlUrl='http://a/1' text=\"O'Brien\"/><outline xmlUrl=\"http://a/2\" text='say \"hi\"'/>", [('http://a/1', "O'Brien"), ('http://a/2', 'say "hi"')]),
    ('unquoted', b'<outline text=Foo xmlUrl=http://a/1 /><outline xmlUrl=http://a/2>', [('http://a/1', 'Foo'), ('http://a/2', '')]),
    ('order and case', b'<OUTLINE XMLURL="http://a/1" TEXT="T"/><Outline text="U" XmlUrl="http://a/2"/><outline title="V" xmlurl="http://a/3"/>', [('http://a/1', 'T'), ('http://a/2', 'U'), ('http://a/3', 'V')]),
    ('entities', b'<outline xmlUrl="http://a/1" text="a &amp; b &lt;c&gt; &quot;d&quot; &apos;e&apos; &#65;&#x42;&#x1F600; &unknown; &amp"/>', [('http://a/1', 'a & b <c> "d" \'e\' AB\U0001F600 &unknown; &amp')]),
    ('bad numeric entities', b'<outline xmlUrl="http://a/1" text="&#0;|&#xD800;|&#x110000;|&#;|&#x;|&#12a;|&#99999999999;"/>', [('http://a/1', '�|�|�|&#;|&#x;|&#12a;|&#99999999999;')]),
    ('double escaped', b'<outline xmlUrl="http://a/?x=1&amp;amp;y=2" text="&amp;amp;"/>', [('http://a/?x=1&amp;y=2', '&amp;')]),
    ('url trimmed', b'<outline xmlUrl="  http://a/1  " text="T"/>', [('http://a/1', 'T')]),
    ('url with a space', b'<outline xmlUrl="http://a/1 2" text="T"/><outline xmlUrl="http://a/ok" text="U"/>', [('http://a/ok', 'U')]),
    ('url with a tab', b'<outline xmlUrl="http://a/1&#9;2" text="T"/>', []),
    ('not http', b'<outline xmlUrl="ftp://a/1"/><outline xmlUrl="file:///a"/><outline xmlUrl="//a/b"/><outline xmlUrl="http://"/><outline xmlUrl="https://"/><outline xmlUrl="http:/x"/><outline xmlUrl="HTTP://A/1"/>'
     b'<outline xmlUrl=""/><outline xmlUrl/><outline text="no url"/><outline htmlUrl="http://a/1"/><outline url="http://a/1"/>', []),
    ('title fallback', b'<outline xmlUrl="http://a/1" title="Only Title"/><outline xmlUrl="http://a/2" text="" title="T2"/><outline xmlUrl="http://a/3" text="T3" title="Other"/><outline xmlUrl="http://a/4"/>',
     [('http://a/1', 'Only Title'), ('http://a/2', 'T2'), ('http://a/3', 'T3'), ('http://a/4', '')]),
    ('white space', b'<outline xmlUrl="http://a/1" text="  a \t\n\r b   c  "/><outline xmlUrl="http://a/2" text="   "/>', [('http://a/1', 'a b c'), ('http://a/2', '')]),
    ('last wins', b'<outline xmlUrl="http://a/1" xmlUrl="http://a/2" text="A" text="B"/>', [('http://a/2', 'B')]),
    ('comment', b'<!-- <outline xmlUrl="http://no/1"/> --><outline xmlUrl="http://a/1"/><!-- unterminated <outline xmlUrl="http://no/2"/>', [('http://a/1', '')]),
    ('cdata and pi', b'<![CDATA[ <outline xmlUrl="http://no/1"/> ]]><?pi <outline xmlUrl="http://no/2"/> ?><outline xmlUrl="http://a/1"/>', [('http://a/1', '')]),
    ('doctype', b'<!DOCTYPE opml [ <!ENTITY e "x>y"> <!-- > --> ]><opml><outline xmlUrl="http://a/1" text="&e;"/></opml>', [('http://a/1', '&e;')]),
    ('greater than in a quote', b'<head note="a>b"><outline xmlUrl="http://a/1" text="x>y"/>', [('http://a/1', 'x>y')]),
    ('stray attributes', b'<outline foo bar="1" xmlUrl="http://a/1" baz = "2" "q" = />', [('http://a/1', '')]),
    ('end tags and text', b'junk </outline> text <outline xmlUrl="http://a/1"> more </outline> </opml>', [('http://a/1', '')]),
    ('other tag names', b'<outlinex xmlUrl="http://a/1"/><outline-x xmlUrl="http://a/2"/><opml:outline xmlUrl="http://a/3"/><outlines xmlUrl="http://a/4"/>', []),
    ('bom', b'\xef\xbb\xbf<?xml version="1.0"?><outline xmlUrl="http://a/1"/>', [('http://a/1', '')]),
    ('utf-16', '<?xml version="1.0"?><outline xmlUrl="http://a/1"/>'.encode('utf-16'), []),
    ('cut tag', b'<outline xmlUrl="http://a/1" text="T"', []),
    ('cut value', b'<outline xmlUrl="http://a/1" text="T', []),
    ('cut after equals', b'<outline xmlUrl=', []),
    ('cut name', b'<outline xmlUr', []),
    ('cut before', b'<outline xmlUrl="http://a/1"/><outline', [('http://a/1', '')]),
    ('empty', b'', []),
    ('no tags', b'just text', []),
    ('lone <', b'<', []),
    ('invalid utf-8', b'<outline xmlUrl="http://a/1" text="a\xffb\xc3(c\xe4\xb8d\xed\xa0\x80e"/>', [('http://a/1', 'ab(cde')]),
    ('url non-ascii', '<outline xmlUrl="http://a/日本"/>'.encode(), [('http://a/日本', '')]),
]


def syntax_tests(ctx):
    expect, P = ctx.expect, PO()
    bad = []
    for name, text, want in CASES:
        got = P.scan(text)
        if got != want: bad.append((name, got, want))
    expect(not bad, f'{len(CASES)} syntax cases: {bad[:3]}')


def limit_tests(ctx):
    """The bounds: an address of 319 bytes fits and 320 does not (none, the outline is not a feed); a name is cut at 95 bytes before a split character (3 and 4 byte ones); many outlines."""
    expect, P = ctx.expect, PO()
    u319 = 'http://a/' + 'p' * (319 - 9)
    got = P.scan(f'<outline xmlUrl="{u319}" text="t"/><outline xmlUrl="{u319}p" text="u"/><outline xmlUrl="http://a/ok"/>'.encode())
    expect(got == [(u319, 't'), ('http://a/ok', '')], 'an address of 319 bytes is kept, one of 320 is not a feed')
    got = P.scan(f'<outline xmlUrl="http://a/1" text="{"日" * 40}"/><outline xmlUrl="http://a/2" text="{chr(0x1F600) * 30}"/><outline xmlUrl="http://a/3" text="{"a" * 200}"/>'.encode())
    expect(got == [('http://a/1', '日' * 31), ('http://a/2', chr(0x1F600) * 23), ('http://a/3', 'a' * 95)], 'a name is cut at 95 bytes on a character boundary (31 CJK, 23 emoji, 95 ASCII)')
    many = ''.join(f'<outline xmlUrl="http://a/{i}" text="s{i}"/>' for i in range(600)).encode()
    got = P.scan(many)
    expect(len(got) == 600 and got[599] == ('http://a/599', 's599'), '600 outlines are scanned (the caller stops at PC_MAX_SHOWS shows)')
    big = b'<!--' + b'x' * 200000 + b'-->' + b'<outline xmlUrl="http://a/1"/>'
    expect(P.scan(big) == [('http://a/1', '')], 'a 200 kB comment is skipped')
    expect(P.scan(b'<outline ' + b'a="1" ' * 40000 + b'xmlUrl="http://a/1"/>') == [('http://a/1', '')], '40000 attributes on one tag')
    deep = b'<outline text="x">' * 12000 + b'<outline xmlUrl="http://a/1"/>'
    expect(P.scan(deep) == [('http://a/1', '')], 'nesting 12000 deep: nothing recursive')


def cuts_tests(ctx):
    """Every sample cut at every 3rd byte: exactly the outlines that were whole before the cut (a tag is one when its '>' came), as the oracle reads the prefix with its complete tags."""
    expect, P = ctx.expect, PO()
    raw = sample('overcast.opml')
    full = P.scan(raw)
    ends = [i + 1 for i in range(len(raw)) if raw[i:i + 1] == b'>' and b'xmlUrl' in raw[raw.rfind(b'<', 0, i):i]]
    bad = []
    for at in range(0, len(raw) + 1, 3):
        got = P.scan(raw[:at])
        k = sum(e <= at for e in ends)
        if got != full[:k]: bad.append((at, len(got), k))
    expect(not bad, f'cut at every 3rd byte: the outlines complete before the cut ({bad[:4]})')


def fuzz_tests(ctx):
    """Random flips, cuts and junk over the samples and a nasty text: no fault (the text, the item and the state end at unmapped pages), url and title terminated, valid UTF-8, no control byte, an
    address that is http(s) without a byte under 33, and the scan always ends."""
    expect, P = ctx.expect, PO()
    rnd = random.Random(20261101)
    seeds = [sample(f) for f in ('apple_podcasts.opml', 'pocketcasts.opml', 'overcast.opml')]
    seeds.append(b'<!DOCTYPE x [ <!ENTITY a "b"> ]><!--c--><![CDATA[d]]><?p q?><o><outline text="\xe4\xb8\xad &amp; &#x1F600; &#12; \'q\'" xmlUrl=\'http://a/b?c=1&amp;d\' a=b c d="e>f"/></o>')
    bad, runs, flips, items = [], 0, 0, 0
    alphabet = (ord('<'), ord('>'), ord('"'), ord("'"), ord('&'), ord(';'), ord('='), ord('/'), ord('!'), ord('-'), ord('?'), ord('['), ord(']'), 0xff, 0xc3, 0xe4, 0x80, 0, 10, 32)
    for _ in range(400):
        data = bytearray(rnd.choice(seeds))
        mode = rnd.choice(('cut', 'flip', 'both', 'junk'))
        if mode in ('flip', 'both'):
            for _ in range(rnd.randint(1, 20)):
                data[rnd.randrange(len(data))] = rnd.choice((rnd.randrange(256),) + alphabet)
                flips += 1
        if mode in ('cut', 'both'): data = data[:rnd.randrange(len(data) + 1)]
        if mode == 'junk': data = bytearray(rnd.choice(alphabet + (ord('o'), ord('x'), ord('l'))) for _ in range(rnd.randint(0, 400)))
        try:
            got = P.scan(bytes(data), raw=True)
        except Exception as ex:   # noqa: BLE001 - an emulation fault is the failure
            bad.append((mode, len(data), str(ex)[:60]))
            continue
        runs += 1
        items += len(got)
        for u, t in got:
            try:
                u.decode('utf-8'); t.decode('utf-8')
            except UnicodeDecodeError: bad.append((mode, 'not utf-8', u[:20], t[:20])); continue
            if not url_ok(u.decode()) or any(b <= 32 or b == 127 for b in u): bad.append((mode, 'url', u[:30]))
            if any(b < 32 or b == 127 for b in t) or t != t.strip() or b'  ' in t: bad.append((mode, 'title', t[:30]))
            if len(u) > URL - 1 or len(t) > TITLE - 1: bad.append((mode, 'size'))
    expect(runs >= 390 and items > 200 and not bad, f'{runs} fuzzed texts ({flips} flipped bytes, {items} outlines found): no fault, strings terminated, valid UTF-8, clean addresses and names ({bad[:4]})')


# ---- the import and export on the card
F = lambda i: f'https://feeds.example/{i}'
MAXS = O['PC_MAX_SHOWS']


def card(m, files):
    for path, data in files.items(): m.put(path, data if isinstance(data, bytes) else data.encode())


def import_(m):
    shows, arr = m.shows()
    n = m.call(PSYMS['pn_import'], a0=m.cstr(ROOT_DIR), a1=arr, a2=len(shows), count=1 << 40)
    return n - (1 << 32) if n >= 1 << 31 else n


def opml(*pairs, extra=''):
    return ('<?xml version="1.0"?><opml version="2.0"><body>' + ''.join(f'<outline type="rss" text="{t}" xmlUrl="{u}"/>' for u, t in pairs) + extra + '</body></opml>').encode()


def feeds_of(m): return sorted(s['feed'] for s in m.shows()[0])


def import_tests(ctx):
    expect = ctx.expect
    # txt and OPML together; the OPML names the shows; duplicates across the sources and with a show already there
    m = PCN.machine()
    PCN.sub(m, 'Existing', F('old'))
    card(m, {f'{ROOT_DIR}/subscriptions.txt': f'{F(1)}\n{F(2)}\n{F("old")}\n',
             f'{ROOT_DIR}/subscriptions.opml': opml((F(2), 'Two'), (F(3), 'Three & Co'), (F('old'), 'Old'), (F(4), '')),
             f'{CARD}/podcasts.opml': opml((F(5), 'Five'), (F(3), 'again'), ('ftp://no.example/x', 'No'))})
    n = import_(m)
    shows = {s['feed']: s for s in m.shows()[0]}
    expect(n == 5 and sorted(shows) == sorted([F('old'), F(1), F(2), F(3), F(4), F(5)]), f'subscriptions.txt, Podcasts/subscriptions.opml and the card root\'s podcasts.opml together: 5 new, none twice ({sorted(shows)})')
    expect(shows[F(2)]['title'] == 'feeds.example' and shows[F(3)]['title'] == 'Three & Co' and shows[F(4)]['title'] == 'feeds.example' and shows[F(5)]['title'] == 'Five',
           'the first source that has an address names the folder; a line of text has the host as its title, an outline its name (an empty name: the host)')
    expect(shows[F(3)]['dir'] == 'feeds.example-%08x' % PCN.pc_hash(F(3)) and shows[F(3)]['checked'] == 0, 'the folder is <host>-<hash8>, exactly as the text import makes it; checked=0')
    expect(f'{ROOT_DIR}/subscriptions.opml' not in m.fs and f'{ROOT_DIR}/subscriptions.opml.imported' in m.fs and f'{CARD}/podcasts.opml' not in m.fs and f'{CARD}/podcasts.opml.imported' in m.fs
           and f'{ROOT_DIR}/subscriptions.txt' in m.fs, 'both OPML files are renamed <name>.imported; subscriptions.txt stays')
    expect(import_(m) == 0, 'imported again: nothing new (the renamed files are not read, subscriptions.txt has nothing new)')
    expect(not [p for p in m.fs if p.endswith('.tmp')], 'no temp file left')
    # an OPML alone; a source that is only .imported or a dot file
    m = PCN.machine()
    card(m, {f'{CARD}/._podcasts.opml': opml((F(1), 'x')), f'{CARD}/old.opml.imported': opml((F(2), 'x')), f'{CARD}/notes.txt': b'x', f'{CARD}/sub/inner.opml': opml((F(3), 'x'))})
    expect(import_(m) == -1 and not m.shows()[0], 'a macOS ._ file, a .opml.imported file and an OPML in a folder are no source: -1')
    expect(m.call(PSYMS['pn_import_found'], a0=m.cstr(ROOT_DIR), count=1 << 40) == 0, 'pn_import_found: 0')
    card(m, {f'{CARD}/Mine.OPML': opml((F(1), 'One'))})
    expect(m.call(PSYMS['pn_import_found'], a0=m.cstr(ROOT_DIR), count=1 << 40) == 1, 'pn_import_found: an OPML in the card root counts (any case of the extension)')
    card(m, {f'{ROOT_DIR}/subscriptions.txt': F(9) + '\n', f'{ROOT_DIR}/subscriptions.opml': opml((F(8), 'e'))})
    expect(m.call(PSYMS['pn_import_found'], a0=m.cstr(ROOT_DIR), count=1 << 40) == 3, 'pn_import_found: three sources now')
    expect(import_(m) == 3 and f'{CARD}/Mine.OPML.imported' in m.fs, 'the three are imported; the root file is renamed whatever the case of its extension')
    # no show in the file, a file that is not OPML: nothing renamed
    m = PCN.machine()
    card(m, {f'{CARD}/empty.opml': b'<opml><body></body></opml>', f'{CARD}/junk.opml': b'not xml at all', f'{CARD}/bad.opml': opml(('ftp://x/y', 'x'))})
    expect(import_(m) == 0 and all(f'{CARD}/{n}.opml' in m.fs for n in ('empty', 'junk', 'bad')), 'files with no usable outline are read (0 added) and left where they are (nothing was imported)')
    # the cap: PC_MAX_SHOWS shows; a file the cap stops is kept for later, one that was seen whole is renamed
    m = PCN.machine()
    card(m, {f'{CARD}/big.opml': opml(*[(F(i), f'S{i}') for i in range(MAXS + 20)]), f'{CARD}/small.opml': opml((F(100), 'x'))})
    n = import_(m)
    expect(n == MAXS and len(m.shows()[0]) == MAXS, f'{MAXS + 20} outlines: {MAXS} shows at most ({n})')
    expect(f'{CARD}/big.opml' in m.fs and f'{CARD}/small.opml' in m.fs, 'the cap stopped the import: the files stay for a later one')
    m = PCN.machine()
    for i in range(MAXS - 1): PCN.sub(m, f'f{i}', F(f'f{i}'))
    card(m, {f'{CARD}/dup.opml': opml((F('f1'), 'dup'), (F(1), 'new'), (F('f2'), 'dup'))})
    expect(import_(m) == 1 and f'{CARD}/dup.opml.imported' in m.fs, 'room for one: a duplicate after it does not count as left over, the file is renamed')
    # two sources, the cap in the second
    m = PCN.machine()
    card(m, {f'{ROOT_DIR}/subscriptions.txt': ''.join(F(i) + '\n' for i in range(MAXS - 10)), f'{CARD}/b.opml': opml(*[(F(1000 + i), 'x') for i in range(20)])})
    expect(import_(m) == MAXS and f'{CARD}/b.opml' in m.fs, 'text lines and an OPML share the cap: the file the cap stopped stays')
    # a write that fails: that show is not counted and the file is not renamed away silently? (it was seen: renamed)
    m = PCN.machine()
    card(m, {f'{CARD}/w.opml': opml((F(1), 'a'), (F(2), 'b'))})
    m.fail.add(('open', f'{ROOT_DIR}/feeds.example-{PCN.pc_hash(F(1)):08x}/.show.tmp'))
    expect(import_(m) == 1 and feeds_of(m) == [F(2)], 'a show file that cannot be written: that outline is not counted')
    # a rename that fails does not matter; a large file is read up to its cap
    m = PCN.machine()
    card(m, {f'{CARD}/r.opml': opml((F(1), 'a'))}); m.fail.add(('rename', f'{CARD}/r.opml.imported'))
    expect(import_(m) == 1 and f'{CARD}/r.opml' in m.fs, 'a rename that fails: the import counted, the file stays')
    m = PCN.machine()
    big = b'<opml><body>' + b'<!-- ' + b'x' * 530000 + b' -->' + b'<outline xmlUrl="http://a/late"/></body></opml>'
    card(m, {f'{CARD}/c.opml': big})
    expect(import_(m) == 0, 'only the first 512 kB (PO_FILE_MAX) of a file are read: an outline after them is not seen')


def read_export(m):
    return m.fs.get(f'{ROOT_DIR}/subscriptions-export.opml')


def export_(m):
    shows, arr = m.shows()
    count = m.alloc(4)
    ok = m.call(PSYMS['pn_export'], a0=m.cstr(ROOT_DIR), a1=arr, a2=len(shows), a3=count, count=1 << 40)
    return ok, m.word(count)


def export_tests(ctx):
    expect, P = ctx.expect, PO()
    m = PCN.machine()
    titles = {'a': 'Zebra "Q" & <Co>', 'b': "the Apple's", 'c': 'The Banana', 'd': '日本語', 'e': 'cherry', 'f': 'Ünï'}
    for i, (k, t) in enumerate(titles.items()): PCN.sub(m, f'dir{k}', F(f'{k}?x=1&y=2'), title=t)
    PCN.sub(m, 'nofeed', '', title='Local only'); m.put(f'{ROOT_DIR}/nofeed/a.mp3', b'x')
    ok, n = export_(m)
    raw = read_export(m)
    expect(ok == 1 and n == 6 and raw is not None, f'six subscriptions exported ({ok}, {n}); the show with no feed address is not')
    root = ET.fromstring(raw)
    outs = [(o.get('text'), o.get('title'), o.get('xmlUrl'), o.get('type')) for o in root.iter('outline')]
    expect(root.tag == 'opml' and root.get('version') == '2.0' and raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n'), 'OPML 2.0 with its XML declaration (it parses as XML)')
    expect([o[0] for o in outs] == ["the Apple's", 'The Banana', 'cherry', 'Zebra "Q" & <Co>', 'Ünï', '日本語'], f'by title, a leading "The " and the case aside ({[o[0] for o in outs]})')
    expect(all(o[0] == o[1] and o[3] == 'rss' for o in outs) and outs[0][2].startswith('https://feeds.example/'), 'each outline has type rss, text = title, the xmlUrl')
    z = next(o for o in outs if o[0].startswith('Zebra'))
    expect(z[2] == F('a?x=1&y=2') and b'&amp;' in raw and b'&lt;Co&gt;' in raw and b'&quot;Q&quot;' in raw and b'&apos;s' in raw, 'the text, the title and the address are XML-escaped (& < > " \')')
    expect(P.scan(raw) == [(o[2], o[0]) for o in outs], 'the scanner reads the export back: the same addresses and names, in order')
    expect(f'{ROOT_DIR}/.subscriptions-export.opml.tmp' not in m.fs and not [p for p in m.fs if p.endswith('.tmp')], 'written atomically: no temp file left')
    first = raw
    ok, n = export_(m)
    expect(ok == 1 and read_export(m) == first, 'exported again: the same file (replaced whole, deterministic)')
    # a failed write leaves the old file; nothing else
    m.put(f'{ROOT_DIR}/subscriptions-export.opml', b'OLD')
    m.fail.add(('open', f'{ROOT_DIR}/.subscriptions-export.opml.tmp'))
    ok, n = export_(m)
    expect(ok == 0 and n == 0 and read_export(m) == b'OLD' and not [p for p in m.fs if p.endswith('.tmp')], 'a temp file that cannot be written: 0, the old export is untouched, no temp file')
    m.fail.discard(('open', f'{ROOT_DIR}/.subscriptions-export.opml.tmp'))
    m.fail.add(('rename', f'{ROOT_DIR}/subscriptions-export.opml'))
    ok, n = export_(m)
    expect(ok == 0 and read_export(m) == b'OLD' and not [p for p in m.fs if p.endswith('.tmp')], 'a rename that fails: 0, the old export stays, the temp file is removed')
    m.fail.clear()
    m.card_mounted = False
    ok, n = export_(m)
    expect(ok == 0 and read_export(m) == b'OLD', 'no card: nothing is written')
    m.card_mounted = True
    # nothing to export: a valid empty OPML
    m = PCN.machine()
    ok, n = export_(m)
    root = ET.fromstring(read_export(m))
    expect(ok == 1 and n == 0 and not list(root.iter('outline')), 'no subscription: a valid OPML with no outline')
    # the largest: PC_MAX_SHOWS shows of the worst escaping fit the buffer
    m = PCN.machine()
    for i in range(MAXS): PCN.sub(m, f'd{i}', 'https://h.example/' + '&' * 301, title='"' * 95)
    ok, n = export_(m)
    expect(ok == 1 and n == MAXS and len(read_export(m)) > 2500 * MAXS and len(ET.fromstring(read_export(m)).findall('.//outline')) == MAXS, f'{MAXS} shows of the worst escaping ({len(read_export(m))} bytes) fit the buffer (PO_EXPORT_MAX)')
    # the largest round trip: PC_MAX_SHOWS distinct feeds of the worst escaping, exported, are all imported again (PO_FILE_MAX is not under PO_EXPORT_MAX)
    m = PCN.machine()
    feeds = sorted('https://h.example/' + '&' * 298 + f'{i:03d}' for i in range(MAXS))
    for i, u in enumerate(feeds): PCN.sub(m, f'd{i}', u, title='"' * 95)
    ok, n = export_(m)
    raw = read_export(m)
    m2 = PCN.machine()
    card(m2, {f'{CARD}/back.opml': raw})
    n2 = import_(m2)
    expect(ok == 1 and n == MAXS and len(raw) > 262144 and n2 == MAXS and feeds_of(m2) == feeds and f'{CARD}/back.opml.imported' in m2.fs, f'the largest export ({len(raw)} bytes, {MAXS} feeds) is imported whole: {n2} shows, the file renamed')
    # control bytes are left out; titles that are only a folder name
    m = PCN.machine()
    m.put(f'{ROOT_DIR}/c/.show', b'M1PLUS-SHOW 1\ntitle=a\x01b\x7fc\nfeed=https://x.example/f\n')
    ok, n = export_(m)
    t = ET.fromstring(read_export(m)).find('.//outline').get('text')
    expect(ok == 1 and t.replace(' ', '') == 'abc' and all(32 <= ord(c) < 127 for c in t), f'no control byte reaches the file ({t!r})')


SECTIONS = [real_tests, syntax_tests, limit_tests, cuts_tests, fuzz_tests, import_tests, export_tests]

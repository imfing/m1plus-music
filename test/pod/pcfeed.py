"""Podcast feeds, the reader (patch/pcfeed.c, docs/modules/podcasts.md "Feeds"): the RSS push parser, the dates and durations, the file names and the writers of .episodes / .show.
The compiled payload runs under Unicorn. The oracle is Python's own XML parser (xml.etree) on real feeds: the three feeds of the project, cut to three items (committed in
test/data/feeds) and, when work/feeds has them, whole (4 MB, 441-600 items), each fed to the C parser in chunks of several sizes; the model (pc_parse_eps / pc_parse_show) reads back what
the writers wrote."""
import calendar, datetime, email.utils, os, re, struct
import xml.etree.ElementTree as ET
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DATA = os.path.join(ROOT, 'test', 'data', 'feeds')
BIG = os.path.join(ROOT, 'work', 'feeds')   # optional, not committed: the three whole feeds (docs/modules/podcasts.md "Feeds" says how to fetch them)
KEEP, TITLE, GUID, URL = 20, 96, 128, 640
ITUNES = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'


def norm(s, cap):
    """pf_norm: white space (bytes up to 0x20) runs one space, trimmed, cut at cap - 1 bytes on a character boundary."""
    b = re.sub(rb'[\x00-\x20]+', b' ', s.encode('utf-8')).strip()
    if len(b) <= cap - 1: return b.decode('utf-8')
    c = b[:cap - 1]
    if b[cap - 1] & 0xc0 == 0x80:   # the cut splits a character
        while c and c[-1] & 0xc0 == 0x80: c = c[:-1]
        c = c[:-1]
    return c.decode('utf-8').rstrip()


def civil(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)


CONTENT = '{http://purl.org/rss/1.0/modules/content/}'
DESC_CUT, AUTHOR, CAT = 200, 64, 48
BOUNDARY = {'p', 'br', 'li', 'ul', 'ol', 'div', 'tr', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'blockquote'}
NAMED = {'amp': 38, 'lt': 60, 'gt': 62, 'quot': 34, 'apos': 39, 'nbsp': 160}
# The description oracle: whole-string regular expressions, one left-to-right pass (a comment, a tag, an entity), then white space and the cut.
# It is deliberately not the C code's byte machine: a different way to the same documented text.
TOKEN = re.compile(r'(<!--.*?-->|<!--.*\Z)|(<[A-Za-z/!?](?:"[^"]*(?:"|\Z)|\'[^\']*(?:\'|\Z)|[^>"\'])*(?:>|\Z))|(&[#A-Za-z0-9]{0,10};)', re.S)


def ent_cp(e):
    if e in NAMED: return NAMED[e]
    m = re.fullmatch(r'#(\d+)|#[xX]([0-9a-fA-F]+)', e)
    if not m: return None
    v = int(m.group(1)) if m.group(1) else int(m.group(2), 16)
    return v if 0 < v <= 0x10ffff and not 0xd800 <= v < 0xe000 else None


def cut_utf8(s, cap):
    """At most cap bytes of s, never inside a character, no trailing space."""
    b = s.encode('utf-8')
    if len(b) > cap:
        c = b[:cap]
        if b[cap] & 0xc0 == 0x80:
            while c and c[-1] & 0xc0 == 0x80: c = c[:-1]
            c = c[:-1]
        b = c
    return b.decode('utf-8').rstrip(' ')


UNI_WS = re.compile('[\xa0\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]')  # the Unicode spaces the sink takes as white space
ZERO_W = re.compile('[\u200b\u2060\ufeff]')  # the zero width characters it drops


def plain(s):
    """The documented plain text of a description (what xml.etree gives it): tags dropped (a boundary tag is a space), entities decoded once more, white space and U+00A0 one space, trimmed, at most 200 bytes."""
    def rep(m):
        if m.group(1): return ''
        if m.group(2):
            return ' ' if re.match(r'</?([A-Za-z0-9]*)', m.group(2)).group(1).lower() in BOUNDARY else ''
        cp = ent_cp(m.group(3)[1:-1])
        return chr(cp) if cp else m.group(3)
    t = UNI_WS.sub(' ', ZERO_W.sub('', TOKEN.sub(rep, s)))
    return cut_utf8(re.sub(r'[\x00-\x20]+', ' ', t).strip(' '), DESC_CUT)


def item_desc(it):
    for tag in (ITUNES + 'summary', 'description', CONTENT + 'encoded'):
        d = plain(it.findtext(tag) or '')
        if d: return d
    return ''


def oracle_show(root):
    """(author, first category, channel summary) as the documented rules give them, by xml.etree."""
    ch = root.find('channel')
    inside = {id(e) for it in ch.findall('item') for e in it.iter()}
    authors = [norm(a.text or '', AUTHOR) for a in ch.findall(ITUNES + 'author')]
    cats = [norm(c.get('text') or '', CAT) for c in ch.iter(ITUNES + 'category') if id(c) not in inside]
    summary = plain(ch.findtext(ITUNES + 'summary') or '') or plain(ch.findtext('description') or '')
    return next((a for a in authors if a), ''), next((c for c in cats if c), ''), summary


def oracle(path_or_bytes):
    """What the parser should find: (channel title, image, kept items [(guid, pub, dur, length, type, title, url, desc)], items seen), by xml.etree."""
    root = ET.fromstring(path_or_bytes) if isinstance(path_or_bytes, bytes) else ET.parse(path_or_bytes).getroot()
    ch = root.find('channel')
    title = norm(ch.findtext('title') or '', TITLE)
    img = ch.find(ITUNES + 'image')
    image = (img.get('href') if img is not None else None) or (ch.findtext('image/url') or '')
    items = []
    for it in ch.findall('item'):
        enc = it.find('enclosure')
        if enc is None or not enc.get('url') or (enc.get('type') or ' ')[0] in 'it': continue
        url = norm(enc.get('url'), URL)
        guid = norm(it.findtext('guid') or '', GUID) or norm(url, GUID)
        pd = it.findtext('pubDate')
        pub = int(email.utils.parsedate_to_datetime(pd).timestamp()) if pd else 0
        dur = pf_duration(it.findtext(ITUNES + 'duration') or '')
        items.append((guid, pub, dur, int(enc.get('length') or 0), norm(enc.get('type') or '', 32), norm(it.findtext('title') or '', TITLE), url, item_desc(it)))
    kept = sorted(items, key=lambda x: -x[1])[:KEEP]
    return title, norm(image, 320), kept, len(items)


def pf_duration(s):
    """The documented reading of itunes:duration: seconds, MM:SS or HH:MM:SS; a fraction dropped; anything else 0."""
    s = s.strip().split('.')[0]
    if not re.fullmatch(r'\d+(:\d+){0,2}', s): return 0
    n = [int(x) for x in s.split(':')]
    return sum(v * 60 ** i for i, v in enumerate(reversed(n)))


class Feeds:
    """The parser under Unicorn: one machine, one parser per feed."""
    def __init__(self, m=None):
        self.m = m or Machine()   # instruction counting is opt-in (m.count()); a 4 MB feed is a lot of blocks
        self.buf, self.out, self.old, self.fresh = (self.m.alloc(n) for n in (1 << 17, 1 << 17, 1 << 17, 8))   # the chunk, the text made, the old file, *fresh: reused by every call

    def call(self, fn, *a):
        args = dict(zip(('a0', 'a1', 'a2', 'a3'), a))
        for i, v in enumerate(a[4:]): self.m.setword(STACK + 16 + 4 * i, v)   # o32: the fifth argument on is on the stack, above the callee's home space
        return self.m.call(PSYMS[fn], count=1 << 40, **args)

    def parse(self, data, chunk=0):
        """A parser fed data in chunks of `chunk` bytes (0: all at once); returns its handle."""
        m = self.m
        p = self.call('pf_new')
        step = chunk or len(data) or 1
        assert step <= 1 << 17
        for i in range(0, len(data), step):
            part = data[i:i + step]
            m.u.mem_write(self.buf, part)
            self.call('pf_push', p, self.buf, len(part))
        return p

    def render(self, p, dir='/mnt/mmc/Podcasts/Show', old=None, cap=65536):
        m = self.m
        ob = self.old if old is not None else 0
        if old is not None: m.u.mem_write(ob, old)
        n = self.call('pf_render_episodes', p, m.cstr(dir), ob, len(old) if old is not None else 0, self.out, cap, self.fresh)
        return bytes(m.u.mem_read(self.out, n)).decode('utf-8'), m.word(self.fresh)

    def title(self, p): return self.m.read_cstr(self.call('pf_title', p)).encode('latin-1').decode('utf-8')
    def image(self, p): return self.m.read_cstr(self.call('pf_image', p)).encode('latin-1').decode('utf-8')
    def author(self, p): return self.m.read_cstr(self.call('pf_author', p)).encode('latin-1').decode('utf-8')
    def category(self, p): return self.m.read_cstr(self.call('pf_category', p)).encode('latin-1').decode('utf-8')
    def summary(self, p): return self.m.read_cstr(self.call('pf_summary', p)).encode('latin-1').decode('utf-8')

    def shown(self, title, feed, image, checked, author='', category='', desc='', modified=0):
        """pf_render_show's text."""
        m = self.m
        out = m.alloc(2048)
        n = self.call('pf_render_show', m.cstr(title), m.cstr(feed), m.cstr(image), checked, modified, m.cstr(author), m.cstr(category), m.cstr(desc), out, 2048)
        return bytes(m.u.mem_read(out, n)).decode('utf-8')


def lines_of(text):
    return [dict(f.split('=', 1) for f in ln.split('\t')) for ln in text.split('\n')[1:] if ln]


def fname(pub, title, ext='mp3'):
    """The documented file name: "YYYY-MM-DD Title.ext", forbidden characters '-', at most 100 bytes."""
    t = norm(title, TITLE)
    t = re.sub(r'[/\\:*?"<>|]', '-', t)
    t = t.lstrip('.- ')
    date = civil(pub).strftime('%Y-%m-%d ') if pub else ''
    room = 100 - len(date) - len(ext) - 1
    b = t.encode('utf-8')
    if len(b) > room:
        c = b[:room]
        if b[room] & 0xc0 == 0x80:
            while c and c[-1] & 0xc0 == 0x80: c = c[:-1]
            c = c[:-1]
        b = c
    t = b.decode('utf-8').rstrip('. ')
    return f'{date}{t or "episode"}.{ext}'


def run(ctx):
    expect = ctx.expect
    F = Feeds()
    m = F.m

    # 1. Real feeds, cut to three items: whole and in chunks of 1, 7, 64 and 1000 bytes against the oracle
    for name in sorted(os.listdir(DATA)):
        raw = open(os.path.join(DATA, name), 'rb').read()
        title, image, kept, seen = oracle(raw)
        sh = oracle_show(ET.fromstring(raw))
        expect(any(x[7] for x in kept) and all(sh), f'{name}: the oracle finds descriptions, an author, a category and a channel summary to compare ({sh[0]!r}, {sh[1]!r}, {sh[2][:40]!r}...)')
        for chunk in (0, 1, 7, 64, 1000):
            p = F.parse(raw, chunk)
            text, fresh = F.render(p)
            got = lines_of(text)
            ok = (F.title(p), F.image(p), F.call('pf_is_feed', p), F.call('pf_items', p), F.call('pf_seen', p)) == (title, image, 1, len(kept), seen)
            ok = ok and [(g['g'], int(g['p']), int(g['d']), int(g['l']), g['t'], g['u']) for g in got] == [(x[0], x[1], x[2], x[3], x[5], x[6]) for x in kept]
            expect(ok and fresh == len(kept), f'{name} in chunks of {chunk or "all"}: channel title, picture, {len(kept)} items with guid, date, duration, size, title and url as the xml.etree oracle has them')
            expect([g.get('x', '') for g in got] == [x[7] for x in kept], f'{name} in chunks of {chunk or "all"}: every item\'s description (x=) is the oracle\'s plain text')
            expect((F.author(p), F.category(p), F.summary(p)) == sh, f'{name} in chunks of {chunk or "all"}: the channel\'s author, first category and summary as the oracle has them')
            F.call('pf_free', p)
    assert any(f.endswith('.xml') for f in os.listdir(DATA)), 'the fixtures are there'

    # 2. The whole feeds (4 MB, 441-600 items), when this checkout has them: the oracle's 20 newest, in 64 KB chunks the way libcurl delivers them
    for name in ('allin', 'headlines', 'wsj'):
        path = os.path.join(BIG, name + '.xml')
        if not os.path.exists(path): continue
        raw = open(path, 'rb').read()
        title, image, kept, seen = oracle(raw)
        p = F.parse(raw, 16384)
        got = lines_of(F.render(p)[0])
        expect((F.title(p), F.image(p), F.call('pf_items', p), F.call('pf_seen', p)) == (title, image, len(kept), seen)
               and [(g['g'], int(g['p']), g['t'], g['u'], g.get('x', '')) for g in got] == [(x[0], x[1], x[5], x[6], x[7]) for x in kept]
               and (F.author(p), F.category(p), F.summary(p)) == oracle_show(ET.fromstring(raw)),
               f'the whole {name} feed ({len(raw) >> 10} kB, {seen} items): the 20 newest of them with their descriptions, the channel, its author, category and summary and the item count as the oracle')
        F.call('pf_free', p)

    # 3. Edge cases of the markup
    def one(xml, chunk=0):
        p = F.parse(xml.encode('utf-8') if isinstance(xml, str) else xml, chunk)
        return p, lines_of(F.render(p)[0])
    item = lambda t='T', g='g1', d='Thu, 01 Jan 2026 10:00:00 GMT', u='https://e.example/a.mp3', extra='', ty='audio/mpeg': (
        f'<item><title>{t}</title><guid>{g}</guid><pubDate>{d}</pubDate><enclosure url="{u}" length="123" type="{ty}"/>{extra}</item>')
    wrap = lambda body, head='<title>Show</title>': f'<?xml version="1.0"?><rss version="2.0"><channel>{head}{body}</channel></rss>'
    p, ls = one(wrap(item('A &amp; B &lt;c&gt; &quot;d&quot; &apos;e&apos; &#233; &#x1F600; &unknown; &', 'x')))
    expect(ls and ls[0]['t'] == 'A & B <c> "d" \'e\' é \U0001F600 &unknown; &', 'entities: the five named, decimal and hex numbers (a four byte character), an unknown one and a lone & stay as written')
    p, ls = one(wrap(item('<![CDATA[Caf\u00e9 <b>bold</b> & more]]>', 'g')))
    expect(ls and ls[0]['t'] == 'Café <b>bold</b> & more', 'CDATA: kept as is, no entity decoding, the "]]" before ">" dropped')
    p, ls = one(wrap(item('  Spaced \n\t out\r\n title  ', 'g')))
    expect(ls and ls[0]['t'] == 'Spaced out title', 'white space: runs collapse to one space, the ends are trimmed (no tab or newline can reach the file)')
    p, ls = one(wrap('<!-- <item><title>no</title></item> -->' + item('Real') + '<!DOCTYPE x [ <!ENTITY y "z"> ]>'))
    expect([l['t'] for l in ls] == ['Real'] and F.call('pf_seen', p) == 1, 'comments and declarations are skipped (an item inside a comment is no item)')
    p, ls = one(wrap(item('One') + '<item><title>No audio</title><guid>n</guid></item>' + item('Img', ty='image/jpeg', u='https://e.example/i.jpg') + item('Two', g='g2', ty='')))
    expect([l['t'] for l in ls] == ['One', 'Two'] and F.call('pf_seen', p) == 2, 'an item without an enclosure, or with a picture as its enclosure, is no episode; an enclosure with no type is one')
    p, ls = one(wrap('<item><title>No guid</title><pubDate>Thu, 01 Jan 2026 10:00:00 GMT</pubDate><enclosure url="https://e.example/z.m4a" length="9"/></item>'))
    expect(ls and ls[0]['g'] == 'https://e.example/z.m4a' and ls[0]['f'].endswith('.m4a'), 'no guid: the enclosure url is the guid; the file takes the url\'s audio extension')
    p, ls = one(wrap(item('Q', u='https://cdn.example/x?a=1&amp;b=2&amp;c=%20d', g='gg')))
    expect(ls and ls[0]['u'] == 'https://cdn.example/x?a=1&b=2&c=%20d' and ls[0]['f'].endswith('.mp3'), 'an enclosure url with &amp; is decoded; no extension in it: mp3')
    p, ls = one(wrap(item('Q', u="https://cdn.example/x.mp3?a='1'", g='g')).replace('url="', "url='").replace('" length', "' length").replace("'1'", '"1"'))
    expect(ls and ls[0]['u'] == 'https://cdn.example/x.mp3?a="1"', 'single quoted attributes, a double quote inside one')
    p, ls = one(wrap(item('Long', u='https://cdn.example/' + 'a' * 700 + '.mp3')))
    expect(ls and ls[0]['u'].startswith('https://cdn.example/aaaa') and len(ls[0]['u']) <= URL - 1, 'a url longer than the buffer is cut, not overrun')
    for case, xml, want in (
            ('the picture is the itunes:image', wrap(item(), '<title>S</title><image><url>https://img/a.png</url></image><itunes:image href="https://img/b.jpg"/>'), 'https://img/b.jpg'),
            ('the picture falls back to <image><url>', wrap(item(), '<title>S</title><image><title>NOT THE SHOW</title><url>https://img/a.png</url></image>'), 'https://img/a.png'),
            ('no picture', wrap(item()), ''),
            ('an episode\'s own itunes:image is not the show\'s', wrap(item(extra='<itunes:image href="https://img/ep.jpg"/>')), '')):
        p, _ = one(xml)
        expect(F.image(p) == want, case)
    p, _ = one(wrap(item(), '<image><title>NOT THE SHOW</title></image><title>The Show</title>'))
    expect(F.title(p) == 'The Show', 'the channel\'s title is not the <image>\'s title or an item\'s')
    p, _ = one('<rss><channel><title>Only</title></channel></rss>')
    expect(F.call('pf_is_feed', p) == 1 and F.call('pf_items', p) == 0 and F.title(p) == 'Only', 'a feed with no item is still a feed')
    for junk in ('<html><body>Not a feed</body></html>', '', '{"json": true}', '<feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'):
        p, _ = one(junk)
        expect(F.call('pf_is_feed', p) == 0 and F.call('pf_items', p) == 0, f'not a feed: {junk[:30]!r}')
    p, ls = one(wrap(item('A') + '<item><title>B</title><guid>b</guid><pubDate>garbage</pubDate><enclosure url="https://e/b.mp3"/></item>'))
    expect([(l['t'], l['p']) for l in ls] == [('A', str(calendar.timegm((2026, 1, 1, 10, 0, 0)))), ('B', '0')], 'a pubDate that is not a date gives 0 and sorts last')
    big = '<title>' + 'x' * 5000 + '</title>'
    p, ls = one(wrap('<item><title>' + 'y' * 5000 + '</title><guid>g</guid><enclosure url="https://e/b.mp3"/></item>', big))
    expect(len(ls[0]['t']) == TITLE - 1 and len(F.title(p)) == TITLE - 1, 'a 5000 byte title is cut to 95 bytes')
    p, ls = one(wrap('<item><title>' + '\u00e9' * 100 + '</title><guid>g</guid><enclosure url="https://e/b.mp3"/></item>'))
    expect(ls[0]['t'].encode('utf-8') == ('\u00e9' * 47).encode('utf-8'), 'the cut never splits a UTF-8 character (47 two byte characters, not 47 and a half)')
    p, ls = one(wrap('<item><title>x</title><guid>' + 'g' * 300 + '</guid><enclosure url="https://e/b.mp3"/></item>'))
    expect(len(ls[0]['g']) == GUID - 1, 'a guid is cut to 127 bytes')
    desc = '<description>' + '<![CDATA[' + 'blah ' * 20000 + ']]></description>' + '<content:encoded><![CDATA[<p>' + 'z' * 70000 + '</p>]]></content:encoded>'
    p, ls = one(wrap(item('Heavy', extra=desc) + item('After', g='g2')), 4096)
    expect([l['t'] for l in ls] == ['Heavy', 'After'], 'a 170 kB description inside an item is skipped, the next item still read')
    giant = '<item><title>Tag</title><guid>t</guid><enclosure url="https://e/b.mp3" length="1" type="audio/mpeg" ' + 'data-x="' + 'q' * 3000 + '"/></item>'
    p, ls = one(wrap(giant + item('Next', g='n')))
    expect([l['t'] for l in ls] == ['Next', 'Tag'], 'a tag longer than the tag buffer keeps its first bytes (the enclosure url is in them) and the parser carries on (Next has a date, Tag none)')
    p, ls = one(wrap(''.join(item(f'E{i:02}', g=f'g{i}', d=email.utils.formatdate(1700000000 + 3600 * (i if i % 2 else 100 - i), usegmt=True)) for i in range(60))))
    want = sorted(range(60), key=lambda i: -(i if i % 2 else 100 - i))[:KEEP]
    expect([l['g'] for l in ls] == [f'g{i}' for i in want] and F.call('pf_seen', p) == 60, 'sixty items in no order: the twenty newest, newest first')
    p, ls = one(wrap(''.join(item(f'E{i:02}', g=f'g{i}', d='') .replace('<pubDate></pubDate>', '') for i in range(30))))
    expect([l['g'] for l in ls] == [f'g{i}' for i in range(KEEP)], 'items with no date keep the feed\'s order and the first twenty')
    for name, xml in (('item with attributes', wrap('<item xml:lang="en"><title>A</title><guid isPermaLink="false">g</guid><enclosure url="https://e/b.mp3"/></item>')),
                      ('prefix titles ignored', wrap('<item><media:title>NO</media:title><itunes:title>NO</itunes:title><title>YES</title><guid>g</guid><enclosure url="https://e/b.mp3"/></item>')),
                      ('empty elements', wrap('<item><title/><guid/><enclosure url="https://e/b.mp3"/></item>', '<title/>'))):
        p, ls = one(xml)
        expect(len(ls) == 1 and (ls[0]['t'] in ('A', 'YES', '')), name)
    p, ls = one(wrap('<item><title>A</title><guid>g</guid><enclosure url="https://e/b.mp3"/></item>', '<title>Chan</title>'))
    expect(F.title(p) == 'Chan', 'the first channel title wins')
    p, _ = one(wrap(item(), '<title>First</title>') .replace('</channel>', '<title>Second</title></channel>'))
    expect(F.title(p) == 'First', 'a later channel level title does not replace it')

    # 3b. Descriptions: HTML stripped, entities decoded, white space collapsed, cut at 200 bytes; the author, the first category, the channel summary
    NS = 'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"'
    wrapn = lambda body, head='<title>Show</title>': f'<?xml version="1.0"?><rss version="2.0" {NS}><channel>{head}{body}</channel></rss>'
    CHUNKS = (0, 1, 3, 64)

    def desc_of(extra, want, what, head='<title>Show</title>'):
        """The first item's x= for the item element(s) `extra`, in every chunking, against the expected text and the oracle's."""
        xml = wrapn(item(extra=extra), head)
        oracle_x = item_desc(ET.fromstring(xml).find('channel/item'))
        for chunk in CHUNKS:
            p, ls = one(xml, chunk)
            got = ls[0].get('x', '') if ls else None
            expect(got == want and oracle_x == want and '\t' not in (got or '') and '\n' not in (got or ''), f'description, {what} (chunks of {chunk or "all"}): {want[:50]!r}' if got == want == oracle_x else f'description, {what} (chunks of {chunk or "all"}): got {got!r}, want {want!r}, oracle {oracle_x!r}')
    desc_of('<itunes:summary>Hello &lt;b&gt;bold&lt;/b&gt; &lt;i&gt;it&lt;/i&gt;alic</itunes:summary>', 'Hello bold italic', 'inline tags vanish without a space')
    desc_of('<description>&lt;div&gt;&lt;p&gt;One &lt;a href="x?a&gt;b" title=\'q&gt;\'&gt;link&lt;/a&gt;&lt;/p&gt;&lt;ul&gt;&lt;li&gt;A&lt;/li&gt;&lt;li&gt;B&lt;/li&gt;&lt;/ul&gt;&lt;/div&gt;</description>',
            'One link A B', 'escaped HTML: nested tags, attributes with > inside quotes, p / li / ul / div boundaries are spaces')
    desc_of('<description><![CDATA[<p>Line one<br>two<br/>three</p><P>Para</P><!-- a > comment --><script>x</script><3 &#233;&eacute;]]></description>',
            'Line one two three Para x<3 é&eacute;', 'CDATA HTML: br, br/, upper case P, a comment with > inside, a "<" that starts no tag, an unknown named entity stays')
    desc_of('<description>5 &amp;amp; 6 &amp;lt;b&amp;gt; a&amp;nbsp;b &amp;#8217; &amp;#x2019; &amp;quot;q&amp;apos; &amp;unknown; AT&amp;T &amp;#0; &amp;#xD800; &amp;AMP; &amp;#x110000;</description>',
            '5 & 6 <b> a b ’ ’ "q\' &unknown; AT&T &#0; &#xD800; &AMP; &#x110000;', 'double-encoded entities: named, numeric (decimal and hex), nbsp as a space, unknown, invalid and a lone & stay as written; a decoded < is no tag')
    desc_of('<description>  a \n\t b\r\n\r\n c &#160; d &amp;#160; e  </description>', 'a b c d e', 'white space runs, tabs, newlines, U+00A0 from a character, an entity and the feed: one space, trimmed')
    desc_of('<description>\ufeff\u3000a\u3000\u2009b\u200bc\u2028d &amp;#8203;&amp;#12288;e\u2060 f、g\u200dh\u3000</description>', 'a bc d e f、g\u200dh',
            'Unicode spaces (U+3000, U+2009, U+2028) are white space, the zero width U+FEFF, U+200B (also from an entity) and U+2060 go; their neighbours U+3001 and U+200D stay')
    desc_of('<itunes:summary>\ufeff&lt;p&gt;\u3000&lt;/p&gt;\u200b</itunes:summary><description>Fallback</description>', 'Fallback', 'a summary with only invisible characters is empty: the description is used')
    desc_of('<description>x&lt;br&gt;y</description><itunes:summary></itunes:summary>', 'x y', 'an empty itunes:summary is not present: the description is used')
    desc_of('<itunes:summary> <b></b> \n </itunes:summary><description>Fallback</description>', 'Fallback', 'a summary with only tags and blanks is empty: the description is used')
    desc_of('<content:encoded><![CDATA[<p>Only <b>content</b></p>]]></content:encoded>', 'Only content', 'content:encoded alone')
    desc_of('<content:encoded>C</content:encoded><description>D</description><itunes:summary>S</itunes:summary>', 'S', 'preference: itunes:summary, then description, then content:encoded, whatever the order in the item')
    desc_of('<content:encoded>C</content:encoded><description>D</description>', 'D', 'preference: description over content:encoded')
    desc_of('', '', 'an item with no description has no x=')
    desc_of('<itunes:author>Ignored</itunes:author><itunes:summary>Real</itunes:summary>', 'Real', 'an item\'s own itunes:author is no description')
    for k in range(4):   # a 3 byte character (CJK) and a 4 byte one (emoji) around the cut at 200 bytes
        for ch, label in (('日', 'CJK'), ('\U0001F600', 'emoji')):
            text = 'a' * k + ch * 100
            b = text.encode('utf-8')
            c = b[:200]
            if b[200] & 0xc0 == 0x80:   # the cut splits a character: its first bytes go too
                while c[-1] & 0xc0 == 0x80: c = c[:-1]
                c = c[:-1]
            want = c.decode('utf-8')
            desc_of(f'<description>{text}</description>', want, f'{label} text after {k} ASCII bytes cut on a character boundary ({len(want.encode("utf-8"))} bytes)')
            expect(len(want.encode('utf-8')) <= 200 and len(want.encode('utf-8')) >= 197, f'{label} after {k}: the cut keeps 197 to 200 bytes')
    desc_of('<description>' + 'word ' * 100 + '</description>', ('word ' * 40).rstrip(), 'plain text of 500 bytes: 199 (the next word does not fit with its space), no trailing space')
    desc_of('<description>' + 'x' * 198 + ' é more</description>', 'x' * 198, 'a space and a two byte character at the cut: the half character and the space go')
    desc_of('<description>' + 'x' * 199 + 'é</description>', 'x' * 199, 'the second byte of a two byte character is past the cut: the character goes whole')
    desc_of('<description>' + 'x' * 200 + 'é</description>', 'x' * 200, 'a character just after the cut')
    desc_of('<description>&lt;p&gt;' + 'long ' * 5000 + '&lt;/p&gt;</description><itunes:summary>' + '<![CDATA[<div>' + 'Q' * 100000 + '</div>]]></itunes:summary>', 'Q' * 200, 'a 100 kB summary: 200 bytes kept, the rest passes')
    desc_of('<description>tail &lt;b att="never closed &amp;amp; text</description>', 'tail', 'an unterminated tag and quote swallows the rest')
    desc_of('<description>a &lt; b &amp;&amp; c &lt;3 d&lt;/</description>', 'a < b && c <3 d', 'a "<" before a space or a digit is text; "</" at the very end opens a tag that never ends')
    desc_of('<description><![CDATA[x]] ]> ]]]]]]><![CDATA[y]]>&amp;z</description>', 'x]] ]> ]]]]y&z', 'CDATA: "]]" and "]>" inside are text, only "]]>" ends it; two sections and an entity after them')
    p, ls = one(wrapn(item(extra='<description>One</description>') + item('B', g='g2', d='Wed, 31 Dec 2025 10:00:00 GMT') + item('C', g='g3', d='Tue, 30 Dec 2025 10:00:00 GMT', extra='<description>Three</description>')))
    expect([l.get('x') for l in ls] == ['One', None, 'Three'], 'each item has its own description: none carries over to the next')
    # the show: author (channel only), first category (entity decoded, a sub-category does not replace it), summary else description
    for chunk in CHUNKS:
        head = ('<title>S</title><itunes:author>Chan &amp; Nel</itunes:author><itunes:category text="Business &amp; Tech"><itunes:category text="Sub"/></itunes:category>'
                '<itunes:category text="Second"/><itunes:owner><itunes:name>Owner</itunes:name></itunes:owner><managingEditor>me@example.com (Editor)</managingEditor>'
                '<image><url>https://i/a.png</url><description>NOT THE SHOW</description></image><description>Plain &lt;b&gt;description&lt;/b&gt;</description>')
        item_extra = '<itunes:author>Item author</itunes:author><itunes:category text="Item category"/><itunes:summary>Item summary</itunes:summary>'
        p, ls = one(wrapn(item(extra=item_extra), head), chunk)
        expect((F.author(p), F.category(p), F.summary(p)) == ('Chan & Nel', 'Business & Tech', 'Plain description'), f'the channel\'s author, first category and description (chunks of {chunk or "all"}); not the item\'s, the <image>\'s, the owner\'s or managingEditor')
        expect(ls[0]['x'] == 'Item summary', f'the item\'s description is its own (chunks of {chunk or "all"})')
        p, _ = one(wrapn(item(), head + '<itunes:summary>Chan summary</itunes:summary>'), chunk)
        expect(F.summary(p) == 'Chan summary', f'the channel summary: itunes:summary over description (chunks of {chunk or "all"})')
    p, _ = one(wrapn(item(extra='<itunes:author>Item author</itunes:author><itunes:category text="Item cat"/>'), '<title>S</title><itunes:category text=""><itunes:category text="Later"/></itunes:category>'))
    expect((F.author(p), F.category(p), F.summary(p)) == ('', 'Later', ''), 'no channel author: ""; an empty first category text is no category; an item\'s author and category are ignored; no summary: ""')
    p, _ = one(wrapn(item(), '<title>S</title><itunes:author>' + 'é' * 40 + '</itunes:author><itunes:category text="' + '日' * 20 + '"/>'))
    expect((F.author(p), F.category(p)) == ('é' * 31, '日' * 15), 'an author is cut at 63 bytes and a category at 47, on character boundaries')
    p, _ = one(wrapn(item(), '<title>S</title><itunes:author>  A \n B  </itunes:author><itunes:category text=" Arts \t Film "/>'))
    expect((F.author(p), F.category(p)) == ('A B', 'Arts Film'), 'author and category: white space collapsed (no tab or newline reaches the file)')

    # 4. Dates and durations
    T = lambda *a: calendar.timegm(a)
    for d, want in (('Thu, 30 Oct 2026 11:00:00 GMT', T(2026, 10, 30, 11, 0, 0)), ('Fri, 30 Oct 2026 16:17:00 +0000', T(2026, 10, 30, 16, 17, 0)), ('30 Oct 2026 07:00 -0400', T(2026, 10, 30, 11, 0, 0)),
                    ('Mon, 5 Jan 2026 09:05:03 +0530', T(2026, 1, 5, 3, 35, 3)), ('Tue, 01 Dec 2026 23:59:59 EST', T(2026, 12, 2, 4, 59, 59)), ('Sun, 29 Feb 2028 12:00:00 PDT', T(2028, 2, 29, 19, 0, 0)),
                    ('Wed, 15 Mar 2023 00:00:00 UT', T(2023, 3, 15, 0, 0, 0)), ('Sat, 2 Jul 2022 6:07:08 Z', T(2022, 7, 2, 6, 7, 8)), ('Mon, 1 Jan 24 00:00:00 GMT', T(2024, 1, 1, 0, 0, 0)),
                    ('Thu, 1 Jan 1970 00:00:01 GMT', 1), ('Tue, 31 Dec 2024 23:59 CST', T(2025, 1, 1, 5, 59, 0)), ('Fri, 30 October 2026 11:00:00 GMT', T(2026, 10, 30, 11, 0, 0)),
                    ('Thu, 30 Oct 2026 11:00:00 +01:00', T(2026, 10, 30, 10, 0, 0)), ('Thu, 30-Oct-2026 11:00:00 GMT', T(2026, 10, 30, 11, 0, 0)), ('Mon, 31 Dec 2029 23:59:59 GMT', T(2029, 12, 31, 23, 59, 59))):
        expect(F.call('pf_rfc822', m.cstr(d)) == want, f'pubDate {d!r} = {want}')
    for d in ('Thu, 30 Oct 2026 11:00:00 GMT', 'Fri, 30 Oct 2026 16:17:00 +0000', 'Mon, 5 Jan 2026 09:05:03 +0530', 'Sun, 29 Feb 2028 12:00:00 -0700', 'Wed, 28 Feb 2001 23:59:59 GMT'):
        expect(F.call('pf_rfc822', m.cstr(d)) == int(email.utils.parsedate_to_datetime(d).timestamp()), f'{d!r} is what Python\'s email.utils says')
    for bad in ('', 'yesterday', 'Thu, 99 Oct 2026 11:00:00 GMT', 'Thu, 30 Foo 2026 11:00:00 GMT', 'Thu, 30 Oct 2026 25:00:00 GMT', '2026-10-30T11:00:00Z', 'Thu, 30 Oct 1969 11:00:00 GMT'):
        expect(F.call('pf_rfc822', m.cstr(bad)) == 0, f'not a date: {bad!r}')
    for s, want in (('1234', 1234), ('12:34', 754), ('1:02:03', 3723), ('00:01:15', 75), ('93.5', 93), ('', 0), ('abc', 0), ('1:2:3:4', 0), (' 45 ', 45), ('0', 0), ('3600', 3600)):
        expect(F.call('pf_duration', m.cstr(s)) == want == pf_duration(s), f'itunes:duration {s!r} = {want} s')

    # 5. File names
    p, ls = one(wrap(''.join([
        item('Same day, same title', g='a', d='Thu, 01 Jan 2026 10:00:00 GMT'), item('Same day, same title', g='b', d='Thu, 01 Jan 2026 11:00:00 GMT'),
        item('Same day, same title', g='c', d='Thu, 01 Jan 2026 12:00:00 GMT'),
        item('What? A "title": &lt;1/2&gt; | 3*4\\5', g='d', d='Fri, 02 Jan 2026 10:00:00 GMT'), item('...Leading dots and trailing.. ', g='e', d='Sat, 03 Jan 2026 10:00:00 GMT'),
        item('', g='f', d='Sun, 04 Jan 2026 10:00:00 GMT'), item('Caf\u00e9 \U0001F600 ' + 'long ' * 40, g='h', d='Mon, 05 Jan 2026 10:00:00 GMT'),
        item('Ogg', g='i', d='Tue, 06 Jan 2026 10:00:00 GMT', u='https://e/x.OGG?z=1'), item('Mp4 type', g='j', d='Wed, 07 Jan 2026 10:00:00 GMT', u='https://e/redirect', ty='audio/x-m4a'),
        item('Page', g='k', d='Thu, 08 Jan 2026 10:00:00 GMT', u='https://e/dl.php')])))
    fs = {l['g']: l['f'] for l in ls}
    expect(fs['c'] == '2026-01-01 Same day, same title.mp3' and fs['b'] == '2026-01-01 Same day, same title (2).mp3' and fs['a'] == '2026-01-01 Same day, same title (3).mp3',
           'two or three items of one day and one title get (2), (3) before the extension, the newest (written first) the plain name')
    expect(fs['d'] == '2026-01-02 What- A -title-- -1-2- - 3-4-5.mp3', 'forbidden characters become "-" (the card is ExFAT)')
    expect(fs['e'] == '2026-01-03 Leading dots and trailing.mp3', 'leading dots and dashes and trailing dots and spaces are dropped')
    expect(fs['f'] == '2026-01-04 episode.mp3', 'no title: "episode"')
    expect(fs['h'] == fname(calendar.timegm((2026, 1, 5, 10, 0, 0)), 'Caf\u00e9 \U0001F600 ' + 'long ' * 40) and len(fs['h'].encode('utf-8')) <= 100, 'a long title: at most 100 bytes with the date and extension, no split character')
    expect(fs['i'].endswith('.ogg') and fs['j'].endswith('.m4a') and fs['k'].endswith('.mp3'), 'the extension: the url path\'s audio one (lower-cased), else the MIME type\'s, else mp3')
    expect(all(f.encode('utf-8').__len__() <= 100 for f in fs.values()), 'every name is at most 100 bytes')
    for pub, title in ((1767262800, 'Plain'), (0, 'No date')):
        p, ls = one(wrap(f'<item><title>{title}</title><guid>x</guid>' + (f'<pubDate>{email.utils.formatdate(pub, usegmt=True)}</pubDate>' if pub else '') + '<enclosure url="https://e/a.mp3"/></item>'))
        expect(ls[0]['f'] == fname(pub, title), f'a name: {fname(pub, title)!r}')

    # 6. The writers: the old file's names kept, the old lines whose file is there carried, the model reads it back
    xml = wrapn(item('New one', g='gn', d='Fri, 30 Oct 2026 10:00:00 GMT', extra='<description>&lt;p&gt;Brand &amp;amp; new&lt;/p&gt;</description>')
                + item('Kept one', g='gk', d='Thu, 29 Oct 2026 10:00:00 GMT', extra='<itunes:summary>Fresh text</itunes:summary>')
                + item('Renamed upstream', g='gr', d='Wed, 28 Oct 2026 10:00:00 GMT'))
    old = ('M1PLUS-EPISODES 1\n'
           'g=gk\tp=1\td=1\tl=1\tf=my own name.mp3\tt=Old title\tu=https://old/1.mp3\tx=stale text\n'
           'g=gr\tp=1\tf=ep7.mp3\tt=Was\tu=https://old/2.mp3\tx=old text kept: the feed has none now\n'
           'g=ggone\tp=5\td=9\tl=7\tf=downloaded long ago.mp3\tt=Out of the window\tu=https://old/3.mp3\tx=a description\n'
           'g=gpart\tp=4\tf=half.mp3\tt=Part\tu=https://old/4.mp3\n'
           'g=gmissing\tp=3\tf=deleted.mp3\tt=File is gone\tu=https://old/5.mp3\n'
           '# a comment\n'
           'g=gnofile\tp=2\tt=Never had a file\tu=https://old/6.mp3\n')
    dirp = '/mnt/mmc/Podcasts/Show'
    m.present.update({dirp + '/downloaded long ago.mp3', dirp + '/half.mp3.part', dirp + '/my own name.mp3'})
    p = F.parse(xml.encode())
    text, fresh = F.render(p, dirp, old.encode())
    ls = lines_of(text)
    expect(text.startswith('M1PLUS-EPISODES 1\n') and fresh == 1, 'the header; one item is new (the other two had an old line)')
    got = {l['g']: l for l in ls}
    expect(got['gk']['f'] == 'my own name.mp3' and got['gr']['f'] == 'ep7.mp3' and got['gn']['f'] == '2026-10-30 New one.mp3', 'an item with an old line keeps that line\'s file name (the downloaded file stays the episode\'s); a new one gets a new name')
    expect(got['gk']['t'] == 'Kept one' and got['gk']['u'] == 'https://e.example/a.mp3', 'its title and url are the feed\'s now')
    expect('ggone' in got and got['ggone']['x'] == 'a description' and 'gpart' in got, 'an old entry outside the window whose file (or .part) is on the card is carried as it was written, x= and all')
    expect(got['gn']['x'] == 'Brand & new' and got['gk']['x'] == 'Fresh text' and got['gr']['x'] == 'old text kept: the feed has none now' and 'x' not in got['gpart'],
           'x=: a new item takes the feed\'s description (stripped), a kept item\'s old one is replaced by a new one, and kept when the feed gives none now')
    expect('gmissing' not in got and 'gnofile' not in got and '# a comment' not in text, 'an entry whose file is gone, or never was, is dropped; so is a comment')
    expect([l['g'] for l in ls] == ['gn', 'gk', 'gr', 'ggone', 'gpart'], 'the feed\'s items first, then the carried lines')
    # the model's reader: pc_parse_eps on the text the writer made
    buf = m.cstr(text)
    outp = m.alloc(300 * O['PC_EP_SIZE'])
    n = F.call('pc_parse_eps', buf, len(text.encode()), outp, 300)
    eps, descs = [], []
    for i in range(n):
        raw = bytes(m.u.mem_read(outp + i * O['PC_EP_SIZE'], O['PC_EP_SIZE']))
        eps.append((raw[:128].split(b'\0')[0].decode(), raw[128:224].split(b'\0')[0].decode(), *struct.unpack_from('<3I', raw, O['PC_EP_GUID'] + 4)))
        descs.append(raw[O['PC_EP_DESC']:O['PC_EP_SIZE']].split(b'\0')[0].decode())
    expect(n == 5 and eps[0][:2] == ('2026-10-30 New one.mp3', 'New one') and eps[0][2:] == (calendar.timegm((2026, 10, 30, 10, 0, 0)), 0, 123), 'the model reads the new text: file, title, date, duration, length')
    expect(descs == ['Brand & new', 'Fresh text', 'old text kept: the feed has none now', 'a description', ''], 'the model reads x= into pc_ep_t.desc (empty without one), the carried lines\' too')
    big = 'é' * 100   # 200 bytes: the longest description the writer makes; the model keeps all of it
    pbig = F.parse(wrapn(item('Big', g='gb', extra=f'<description>{big}</description>')).encode())
    tbig, _ = F.render(pbig)
    m.u.mem_write(outp, bytes(2 * O['PC_EP_SIZE']))
    F.call('pc_parse_eps', m.cstr(tbig), len(tbig.encode()), outp, 300)
    expect(m.read_cstr(outp + O['PC_EP_DESC']).encode('latin-1').decode('utf-8') == big and lines_of(tbig)[0]['x'] == big, 'a 200 byte description survives the writer and the model whole')
    m.u.mem_write(outp, bytes(O['PC_EP_SIZE']))
    hand = 'M1PLUS-EPISODES 1\ng=a\tx=' + 'y' * 300 + '\n'
    F.call('pc_parse_eps', m.cstr(hand), len(hand), outp, 300)
    expect(len(m.read_cstr(outp + O['PC_EP_DESC'])) == O['PC_DESC'] - 1, 'a longer x= in a hand-written file is cut to the field (207 bytes), never overrun')
    # the same refresh twice changes nothing
    p2 = F.parse(xml.encode())
    text2, fresh2 = F.render(p2, dirp, text.encode())
    expect(text2 == text and fresh2 == 0, 'a second refresh of the same feed against its own output gives the same text and no new item')
    text3, fresh3 = F.render(p2, dirp, None)
    expect(fresh3 == 3 and [l['g'] for l in lines_of(text3)] == ['gn', 'gk', 'gr'], 'with no old file every item is new')
    tiny, _ = F.render(p, dirp, old.encode(), cap=300)
    expect(len(tiny.encode()) < 300 and tiny.startswith('M1PLUS-EPISODES 1\n') and tiny.endswith('\n'), 'a small output buffer is never overrun (the text ends at a whole line)' if tiny.endswith('\n') else 'small buffer')
    # tabs and newlines in values
    p, ls = one(wrap('<item><title>A\tB\nC</title><guid>g\th</guid><enclosure url="https://e/a.mp3"/></item>'))
    expect(ls and ls[0]['t'] == 'A B C' and ls[0]['g'] == 'g h', 'no tab or newline reaches the file')

    # 7. The show file and the folder name
    show = F.shown
    s = show('The Show', 'https://f.example/rss', 'https://i.example/a.jpg', 1793000000)
    expect(s == 'M1PLUS-SHOW 1\ntitle=The Show\nfeed=https://f.example/rss\nimage=https://i.example/a.jpg\nchecked=1793000000\n', 'the .show text')
    sh = m.alloc(O['PC_SHOW_SIZE']); m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    sb = m.cstr(s)
    expect(F.call('pc_parse_show', sb, len(s), sh) == 1 and (lambda d: d['title'] == 'The Show' and d['feed'] == 'https://f.example/rss' and d['image'] == 'https://i.example/a.jpg' and d['checked'] == 1793000000)(
        dict(title=m.read_cstr(sh + O['PC_SH_TITLE']), feed=m.read_cstr(sh + O['PC_SH_FEED']), image=m.read_cstr(sh + O['PC_SH_IMAGE']), checked=m.word(sh + O['PC_SH_CHECKED']))), 'the model reads the show file back, the checked time too')
    longurl = 'https://f.example/' + 'p' * 290
    s = show('T\nitle', longurl, '', 0)
    sb = m.cstr(s); m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    F.call('pc_parse_show', sb, len(s), sh)
    expect(m.read_cstr(sh + O['PC_SH_FEED']) == longurl and m.read_cstr(sh + O['PC_SH_TITLE']) == 'T itle' and s.count('\n') == 5, 'a 308 byte feed url survives the round trip (PC_URL is 320); a newline in the title becomes a space')
    # the descriptive keys: written only when not empty, read back by the model into author / category / desc
    s = show('The Show', 'https://f.example/rss', 'https://i.example/a.jpg', 5, 'Jane é Doe', 'Arts', 'Line\none\ttwo ' + 'é' * 50)
    expect(s == 'M1PLUS-SHOW 1\ntitle=The Show\nfeed=https://f.example/rss\nimage=https://i.example/a.jpg\nchecked=5\nauthor=Jane é Doe\ncategory=Arts\ndesc=Line one two ' + 'é' * 50 + '\n',
           'the .show text with author=, category= and desc= after checked (no tab or newline in a value)')
    sb = m.cstr(s); m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    F.call('pc_parse_show', sb, len(s.encode()), sh)
    rd = lambda off: m.read_cstr(sh + O[off]).encode('latin-1').decode('utf-8')
    expect((rd('PC_SH_AUTHOR'), rd('PC_SH_CAT'), rd('PC_SH_DESC')) == ('Jane é Doe', 'Arts', 'Line one two ' + 'é' * 50) and rd('PC_SH_TITLE') == 'The Show' and m.word(sh + O['PC_SH_CHECKED']) == 5,
           'the model reads author=, category= and desc= back next to the old keys')
    s = show('T', 'https://f/x', '', 0, '', '', '')
    expect(s == 'M1PLUS-SHOW 1\ntitle=T\nfeed=https://f/x\nimage=\nchecked=0\n', 'empty author, category and desc write no key')
    m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    F.call('pc_parse_show', m.cstr(s), len(s), sh)
    expect(rd('PC_SH_AUTHOR') == rd('PC_SH_CAT') == rd('PC_SH_DESC') == '' and m.word(sh + O['PC_SH_MODIFIED']) == 0, 'a show file without them reads empty fields, modified 0')
    # modified=: the server's Last-Modified, written only when not 0, read back by the model
    s = show('T', 'https://f/x', '', 7, 'A', '', '', modified=1700000123)
    expect(s == 'M1PLUS-SHOW 1\ntitle=T\nfeed=https://f/x\nimage=\nchecked=7\nmodified=1700000123\nauthor=A\n', 'modified= is written after checked when not 0')
    m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    F.call('pc_parse_show', m.cstr(s), len(s), sh)
    expect(m.word(sh + O['PC_SH_MODIFIED']) == 1700000123 and rd('PC_SH_AUTHOR') == 'A' and m.word(sh + O['PC_SH_CHECKED']) == 7, 'the model reads modified= back')
    longs = 'M1PLUS-SHOW 1\nauthor=' + 'a' * 100 + '\ncategory=' + 'c' * 100 + '\ndesc=' + 'd' * 400 + '\n'
    F.call('pc_parse_show', m.cstr(longs), len(longs), sh)
    expect((len(rd('PC_SH_AUTHOR')), len(rd('PC_SH_CAT')), len(rd('PC_SH_DESC'))) == (O['PC_AUTHOR'] - 1, O['PC_CAT'] - 1, O['PC_DESC'] - 1), 'over-long values in a hand-written file are cut to their fields, never overrun')
    # the whole chain on a feed: parser, then the writer with the show's old values as the fallback (what a refresh passes)
    p, _ = one(wrapn(item(), '<title>S</title><itunes:author>New Author</itunes:author><itunes:summary>New &lt;b&gt;summary&lt;/b&gt;</itunes:summary>'))
    s = show('S', 'https://f/x', '', 9, F.author(p) or 'Old author', F.category(p) or 'Old category', F.summary(p) or 'Old desc')
    expect(s.endswith('author=New Author\ncategory=Old category\ndesc=New summary\n'), 'a refresh: the feed\'s author and summary replace the old ones, an empty category keeps the old value')
    for title, want in (('The Show', 'The Show'), ('A: B / C?', 'A- B - C-'), ('...', ''), ('   ', ''), ('Caf\u00e9', 'Caf\u00e9'), ('x' * 150, 'x' * 100), ('Show.', 'Show'), ('\u00e9' * 80, '\u00e9' * 50)):
        out = m.alloc(128)
        F.call('pf_folder_name', out, 128, m.cstr(title))
        got = m.read_cstr(out).encode('latin-1').decode('utf-8')
        expect(got == want, f'folder name of {title[:20]!r} is {want[:20]!r}')

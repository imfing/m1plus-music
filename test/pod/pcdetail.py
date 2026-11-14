"""The Podcasts episode page and its long descriptions (patch/pcdetail.c, patch/pcnotes.c, patch/pcfeed.c, patch/podcasts.c, docs/modules/podcasts.md "The episode page", "The notes file").
Parser: an item's long plain text (up to 4 KB: HTML to paragraphs, entities, CDATA, the cut on a UTF-8 boundary, the element preferred) against an independent oracle on synthetic feeds and the real
fixtures. The notes file: its format, the atomic write, only the kept items, old notes dropped, the bounded read of one episode. The page: opened from a subscribed show, a local show and a search preview,
its layout against tools/pod_show.py, the pill and the sheet working on it, Back keeping the list's place, the strings' widths and kinsoku, and the screen-off rule. The compiled payload runs under Unicorn."""
import os, re, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))


PF, PCS = sibling('pcfeed'), sibling('pcshow')
PCP, DL = PCS.PCP, PCS.DL
import pod_show, pod_i18n   # noqa: E402

O = PCS.O
RP, DEEP, NOW = PCS.RP, PCS.DEEP, PCS.NOW
NOTE_MAX = 4096
PD = pod_show.PD
BOUNDARY_NOT_TD = PF.BOUNDARY - {'td'}




# ---------------------------------------------------------------------------
# The oracle: the documented long text of a description, by regular expressions and one pass, not the C byte machine.

def note_oracle(s):
    """The documented long plain text: tags dropped (p br li ul ol div tr h1-h6 hr blockquote make a paragraph break, td a space), entities decoded once more, runs of white space (and U+00A0) one space or, when the run
    holds a break tag or a blank line (two newlines), one paragraph break, the ends trimmed, at most 4096 bytes cut before a split UTF-8 character."""
    def rep(m):
        if m.group(1): return ''
        if m.group(2):
            nm = re.match(r'</?([A-Za-z0-9]*)', m.group(2)).group(1).lower()
            return ' ' if nm == 'td' else '\x01' if nm in BOUNDARY_NOT_TD else ''
        cp = PF.ent_cp(m.group(3)[1:-1])
        return chr(cp) if cp else m.group(3)
    t = PF.TOKEN.sub(rep, s)
    out, pending, nl = [], 0, 0
    for ch in PF.ZERO_W.sub('', t):
        if ch == '\x01' or ord(ch) <= 32 or PF.UNI_WS.match(ch):
            if not out: continue
            lvl = 2 if ch in '\x01\u2028\u2029' else 1
            if ch == '\n':
                nl += 1
                if nl >= 2: lvl = 2
            pending = max(pending, lvl)
        else:
            if pending: out.append('\n' if pending == 2 else ' ')
            pending, nl = 0, 0
            out.append(ch)
    return PF.cut_utf8(''.join(out), NOTE_MAX).rstrip(' \n')


def item_note(it):
    """The note of an item as the oracle has it: the first of itunes:summary, description, content:encoded whose 200 byte text is not empty (the choice x= makes)."""
    for tag in (PF.ITUNES + 'summary', 'description', PF.CONTENT + 'encoded'):
        raw = it.findtext(tag) or ''
        if PF.plain(raw): return note_oracle(raw)
    return ''


def flat(note):
    """x= from a note: its paragraph breaks are spaces, at most 200 bytes cut before a split character."""
    return PF.cut_utf8(note.replace('\n', ' '), 200)


def feed(*items, show='Show'):
    """A feed whose items are (guid, pubDate, description xml) tuples."""
    body = ''.join(f'<item><title>T {g}</title><guid>{g}</guid><pubDate>{d}</pubDate><enclosure url="https://x.example/{g}.mp3" length="9" type="audio/mpeg"/>{x}</item>' for g, d, x in items)
    return ('<?xml version="1.0"?><rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            f'<channel><title>{show}</title>{body}</channel></rss>').encode()


DATE = 'Thu, 30 Oct 2025 11:00:00 GMT'


class Notes:
    """The parser under Unicorn (test/pod/pcfeed.py's Feeds) with the long text's accessors."""
    def __init__(self):
        self.F = PF.Feeds()
        self.m = self.F.m

    def parse(self, data, chunk=0): return self.F.parse(data, chunk)
    def note(self, p, i): return utf8(self.m.read_cstr(self.F.call('pf_note', p, i)))

    def x_of(self, p):
        return [g.get('x', '') for g in PF.lines_of(self.F.render(p)[0])]


# ---------------------------------------------------------------------------

def parser_tests(ctx):
    """An item's long description: HTML to paragraphs, entities, CDATA, white space, the 4 KB cut, the element preferred, real feeds against the oracle, x= unchanged."""
    expect = ctx.expect
    N = Notes()

    def one(desc_xml, chunk=0):
        p = N.parse(feed(('g1', DATE, desc_xml)), chunk)
        assert N.F.call('pf_items', p) == 1
        return N.note(p, 0), N.x_of(p)[0]

    html = '<p>One &amp; two</p><p>Second<br/>third <a href="http://a.example/x?y=1&amp;z=2">link</a></p><ul><li>a</li><li>b</li></ul>'
    for chunk in (0, 1, 7):
        n, x = one(f'<description><![CDATA[{html}]]></description>', chunk)
        expect(n == 'One & two\nSecond\nthird link\na\nb' and x == 'One & two Second third link a b', f'CDATA HTML: paragraphs for p, br and li, a link keeps its text, entities decoded, x= the same text on one line (chunk {chunk}): {n!r} / {x!r}')
    n, x = one('<description>&lt;p&gt;A&lt;/p&gt;&lt;p&gt;B &amp;amp; C&lt;/p&gt;</description>')
    expect(n == 'A\nB & C' and x == 'A B & C', f'escaped HTML (the usual feed): the same paragraphs, a double-encoded entity decoded once more ({n!r})')
    n, x = one('<itunes:summary>Line one\nstill one\n\nPara two\n \n \nPara three</itunes:summary>')
    expect(n == 'Line one still one\nPara two\nPara three' and x == 'Line one still one Para two Para three', f'plain text: a single newline is a space, a blank line a paragraph break ({n!r})')
    n, _ = one('<description>a&nbsp;&nbsp;b &#160; c&#x1F600;d <b>bold</b>x</description>')
    expect(n == 'a b c\U0001F600d boldx', f'U+00A0 and its entities are one space, an emoji from a numeric entity, an inline tag is nothing ({n!r})')
    for chunk in (0, 1, 7):
        for d in ('ZBOMFirstZLSSecond', 'First\nZIDS\nSecond', 'First\nZZWS\nSecond', 'First\n&#160;\n ZIDS Second', 'First\n\xa0ZIDS\r\nSecond', '<![CDATA[<p>ZIDS</p><p>First</p><p>&#8203;</p><p>ZIDSZIDSSecondZPS</p>]]>', '&lt;p&gt;ZZWS&lt;/p&gt;FirstZPSZWJSecond&lt;br&gt;ZBOM'):
            for k, v in (('ZBOM', 0xfeff), ('ZLS', 0x2028), ('ZPS', 0x2029), ('ZIDS', 0x3000), ('ZZWS', 0x200b), ('ZWJ', 0x2060)): d = d.replace(k, chr(v))
            n, x = one(f'<description>{d}</description>', chunk)
            expect(n == 'First\nSecond' and x == 'First Second', f'no blank first line from a BOM or a paragraph of an ideographic or zero width space; a paragraph\'s indent goes, U+2028 and U+2029 are breaks (chunk {chunk}): {n!r} / {x!r}')
    n, _ = one('<description><![CDATA[<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>]]></description>')
    expect(n == 'a b\nc', f'a table row is a paragraph, a cell a space ({n!r})')
    n, _ = one('<description><![CDATA[<!-- a comment <p> -->only<p></p><p></p>this]]></description>')
    expect(n == 'only\nthis', f'a comment is skipped whole, empty paragraphs make one break ({n!r})')
    n, x = one('<description>an <b>XHTML</b> child <p>of the element</p></description>')
    expect(n == 'an XHTML child of the element', f'an element nested in the description is not a boundary: its text is joined ({n!r})')
    n, _ = one('<description>   </description><itunes:summary>S</itunes:summary>')
    expect(n == 'S', 'an empty element is not a description')
    # the element: itunes:summary, else description, else content:encoded (the choice x= makes; the same element gives the note)
    s_, d_, c_ = '<itunes:summary>S sum</itunes:summary>', '<description>D desc</description>', '<content:encoded><![CDATA[<p>C one</p><p>C two</p>]]></content:encoded>'
    for order in ((c_, d_, s_), (s_, d_, c_), (d_, c_, s_)):
        expect(one(''.join(order))[0] == 'S sum', 'all three: itunes:summary wins in any order')
    expect(one(c_ + d_)[0] == 'D desc' and one(d_ + c_)[0] == 'D desc', 'no summary: description wins over content:encoded in any order')
    n, x = one(c_)
    expect(n == 'C one\nC two' and x == 'C one C two', 'only content:encoded: its paragraphs')
    expect(one('<itunes:summary> </itunes:summary>' + d_)[0] == 'D desc', 'a blank summary falls to the next element')
    # the 4 KB cut: bytes, never inside a character
    for name, unit in (('Latin', 'word '), ('CJK (3 bytes)', '汉'), ('emoji (4 bytes)', '\U0001F600'), ('mixed 1 and 3 bytes', 'a汉')):
        text = unit * (6000 // len(unit.encode()) + 10)
        n, x = one(f'<description>{text}</description>', 997)
        b = n.encode()
        expect(len(b) <= NOTE_MAX and len(b) >= NOTE_MAX - 4 and b.decode('utf-8') == text.rstrip(' ')[:len(n)] and n == note_oracle(text), f'{name}: cut at {len(b)} bytes (at most {NOTE_MAX}) on a character boundary, a prefix of the text')
        expect(x == flat(n) and len(x.encode()) <= 200 and x == PF.plain(text), f'{name}: x= is its first 200 bytes ({len(x.encode())})')
    para = '<p>' + '</p><p>'.join(f'Paragraph {i} ' + 'word ' * 30 for i in range(80)) + '</p>'
    n, _ = one(f'<description><![CDATA[{para}]]></description>', 5000)
    expect(len(n.encode()) <= NOTE_MAX and n == note_oracle(para) and n.count('\n') > 20 and not n.endswith(('\n', ' ')), 'a long text with 80 paragraphs: cut at 4 KB, no trailing break')
    huge = '<p>' + 'lorem ipsum dolor <b>sit</b> amet &amp; more </p>' * 6000   # 300 KB in one element
    n, x = one(f'<description><![CDATA[{huge}]]></description>', 60000)
    expect(len(n.encode()) <= NOTE_MAX and n.startswith('lorem ipsum dolor sit amet & more\nlorem') and x == flat(n), 'an element of 300 KB costs nothing after the cut: the first 4 KB are kept')
    # the kept items own their notes: items arrive oldest first, the 20 newest stay, each with its own text
    items = [(f'g{i:02d}', email_date(i), f'<description><![CDATA[note-{i:02d} <p>x</p>y{i}]]></description>') for i in range(30)]
    p = N.parse(feed(*items), 100)
    got = [N.note(p, i) for i in range(N.F.call('pf_items', p))]
    expect(N.F.call('pf_items', p) == PF.KEEP and got == [f'note-{i:02d}\nx\ny{i}' for i in range(29, 9, -1)], f'30 items oldest first: the 20 newest kept, newest first, each with its own note ({got[:2]}...)')
    expect(N.note(p, 20) == '' and N.note(p, -1) == '', 'no note outside the kept items')
    # the real fixtures: every kept item's note and x= against the oracle, in chunks
    longest = 0
    for name in sorted(os.listdir(PF.DATA)):
        raw = open(os.path.join(PF.DATA, name), 'rb').read()
        _, _, kept, _ = PF.oracle(raw)
        root = PF.ET.fromstring(raw)
        its = {}
        for it in root.find('channel').findall('item'):
            enc = it.find('enclosure')
            if enc is None or not enc.get('url') or (enc.get('type') or ' ')[0] in 'it': continue
            guid = PF.norm(it.findtext('guid') or '', PF.GUID) or PF.norm(PF.norm(enc.get('url'), PF.URL), PF.GUID)
            its[guid] = it
        want = [item_note(its[k[0]]) for k in kept]
        longest = max([longest] + [len(w.encode()) for w in want])
        for chunk in (0, 1, 64, 1000):
            p = N.parse(raw, chunk)
            have = [N.note(p, i) for i in range(N.F.call('pf_items', p))]
            xs = N.x_of(p)
            expect(have == want and xs == [k[7] for k in kept] and all(x == flat(h) for x, h in zip(xs, have)),
                   f'{name} in chunks of {chunk or "all"}: {len(kept)} notes equal the oracle\'s and x= stays what it was ({sum(1 for w in want if w)} with a note)')
    expect(longest > 200, f'the real feeds have descriptions longer than the cells\' 200 bytes ({longest})')


def email_date(i):
    import datetime, email.utils
    return email.utils.format_datetime(datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=i))


# ---------------------------------------------------------------------------

def decode_note_line(line):
    """The text of a .notes line as a reader gives it: \\\\ is a backslash, \\n a paragraph break."""
    guid, text = line.split('\t', 1)
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            out.append('\n' if text[i + 1] == 'n' else text[i + 1]); i += 2
        else:
            out.append(c); i += 1
    return guid[2:], ''.join(out)


def notes_file_tests(ctx):
    """.notes: the format, the atomic write, only the kept items, old notes dropped, the bounded read of one episode, a missing or damaged file."""
    expect = ctx.expect
    N = Notes()
    m, F = N.m, N.F
    path, tmp = '/mnt/mmc/Podcasts/S/.notes', '/mnt/mmc/Podcasts/S/.notes.tmp'

    def save(p, pth=path, t=tmp): return F.call('pno_save', m.cstr(pth), m.cstr(t), p)

    def read(guid, cap=NOTE_MAX + 1, pth=path):
        out = m.alloc(cap + 8)
        n = F.call('pno_read', m.cstr(pth), PCS.PCP.guid_hash(guid), out, cap)
        return n, utf8(m.read_cstr(out)) if n else ''

    items = [(f'guid-{i}', email_date(i), f'<description><![CDATA[Item {i}: back\\slash and <p>paragraph two of {i}</p><p>汉字 {i}</p>]]></description>') for i in range(24)]
    p = N.parse(feed(*items), 300)
    m.calls = []
    expect(save(p) == 1, 'pno_save: written')
    text = m.fs[path].decode('utf-8')
    lines = text.split('\n')
    expect(lines[0] == 'M1PLUS-NOTES 1' and lines[-1] == '' and len(lines) == 2 + PF.KEEP and all(l.count('\t') == 1 for l in lines[1:-1]) and '\r' not in text,
           f'the format: the header, then one line per kept item (20 of 24), one tab each, no raw newline inside a text ({len(lines) - 2} lines)')
    dec = [decode_note_line(l) for l in lines[1:-1]]
    want = [(f'guid-{i}', f'Item {i}: back\\slash and\nparagraph two of {i}\n汉字 {i}') for i in range(23, 3, -1)]
    expect(dec == want and 'back\\\\slash' in lines[1] and '\\n' in lines[1], 'the kept items only, newest first; a backslash is written \\\\ and a paragraph break \\n; the text decodes back')
    expect('guid-0\t' not in text and 'guid-3\t' not in text, 'the items the feed window dropped have no line')
    c = m.calls
    iw = [i for i, x in enumerate(c) if x[0] == 'open' and x[1] == tmp]
    ifs = [i for i, x in enumerate(c) if x[0] == 'fsync' and x[1] == tmp]
    ir = [i for i, x in enumerate(c) if x[0] == 'rename' and x[1] == tmp and x[2] == path]
    expect(iw and ifs and ir and iw[0] < ifs[0] < ir[0] and tmp not in m.fs, 'atomic: a temp file is written and fsynced, then renamed over .notes; none is left')
    # failures leave the old file alone and no temp file
    before = m.fs[path]
    p2 = N.parse(feed(('new-1', DATE, '<description>new</description>')))
    for what in (('open', tmp), ('write', tmp), ('fsync', tmp), ('rename', path)):
        m.fail.add(what)
        expect(save(p2) == 0 and m.fs[path] == before and tmp not in m.fs, f'{what[0]} fails: nothing is written, the old file stays, no temp file')
        m.fail.discard(what)
    # old notes are dropped with their lines: a refresh whose items are others writes only those
    expect(save(p2) == 1 and m.fs[path].decode() == 'M1PLUS-NOTES 1\ng=new-1\tnew\n', 'a second write replaces the file: the old items\' notes are gone')
    p3 = N.parse(feed(('plain-1', DATE, '')))
    expect(save(p3) == 1 and path not in m.fs, 'a feed with no description for any kept item: the old file is removed')
    expect(read('new-1')[0] == 0, 'a missing file: no note')
    # the bounded read of one episode
    big = [(f'big-{i}', email_date(i), f'<description>{"w" * 3 + chr(0x6c49) * 1300 if i % 2 else "latin " * 700}{i}</description>') for i in range(20)]
    p4 = N.parse(feed(*big), 4000)
    save(p4)
    size = len(m.fs[path])
    for gid in ('big-19', 'big-10', 'big-0'):
        m.calls = []
        n, t = read(gid)
        i = int(gid[4:])
        reads = len([c for c in m.calls if c[0] == 'read'])
        at = m.fs[path].find(b'\ng=' + gid.encode() + b'\t')
        end = m.fs[path].find(b'\n', at + 1 + 3)
        expect(n == len(t.encode()) and t == N.note(p4, 19 - i) and reads == end // 1024 + 1,
               f'{gid}: its note ({n} bytes) is read with {reads} reads of 1 KB of a {size} byte file: up to the end of its line ({end}), no further')
    m.calls = []
    n, t = read('big-1', cap=100)
    expect(0 < n < 100 and len(t.encode()) == n and t == N.note(p4, 18).encode()[:n].decode('utf-8', 'ignore') and N.note(p4, 18).encode().startswith(t.encode()), f'a small buffer: the note is cut on a character boundary ({n} bytes)')
    n, t = read('big-1', cap=2)
    expect(n <= 1, 'a buffer of two bytes: one byte at most')
    expect(read('no-such-guid')[0] == 0, 'a guid with no line: no note')
    m.fs[path] = b'not a notes file\ng=big-1\tx\n'
    expect(read('big-1')[0] == 0, 'a file with another header: no note')
    m.fs[path] = b'M1PLUS-NOTES 1\njunk line\ng=a\tfirst\ng=a\tsecond\ng=b\nno tab\n\ng=c\tlast with no newline'
    expect(read('a') == (5, 'first') and read('b')[0] == 0 and read('c') == (20, 'last with no newline'), 'damaged lines are skipped, the first line of a guid wins, a last line without a newline is read')
    m.fs[path] = b'M1PLUS-NOTES 1\ng=e\ta\\\\b\\nc\\xd\n'
    expect(read('e') == (7, 'a\\b\nc' + 'xd'), 'escapes: \\\\ is a backslash, \\n a break, another escaped character is itself')
    # a file longer than the scan limit is not read past it
    m.fs[path] = b'M1PLUS-NOTES 1\n' + b'g=pad\t' + b'x' * 300000 + b'\ng=late\ttext\n'
    m.calls = []
    expect(read('late')[0] == 0 and len([c for c in m.calls if c[0] == 'read']) <= 256 + 1, 'a line past 256 KB is not looked for (the scan is bounded)')


# ---------------------------------------------------------------------------
# The page

NOTE_EN = '\n'.join([
    'Chamath, Jason, Sacks and Friedberg break down the week\'s biggest stories: the market\'s reaction to the Fed, what the next move means for tech valuations, and why the shutdown is dragging on.',
    'Topics: 0:00 intro; 4:10 Nvidia hits five trillion; 22:45 the AI bubble debate; 41:30 tariffs and the supreme court; 58:00 closing thoughts and what we are watching next week in the markets.',
    'Follow the besties on social media, subscribe to the newsletter and send us your questions for the next episode. Thank you for listening, and see you next week.'])
NOTE_ZH = '\n'.join([
    '本期节目中，几位主持人讨论了本周最重要的新闻：市场对美联储降息的反应、科技股估值的变化，以及政府停摆为何迟迟没有结束。他们还谈到了关税、人工智能泡沫和英伟达的五万亿美元时刻。',
    '时间线：0:00 开场；4:10 英伟达市值突破五万亿美元（这是一个历史性的时刻）；22:45 人工智能泡沫之争；41:30 关税与最高法院；58:00 结语。',
    '欢迎在社交媒体上关注我们，订阅新闻简报，并把您的问题发给我们！“谢谢收听”，下周再见。'])


def notes_blob(pairs):
    out = 'M1PLUS-NOTES 1\n'
    for g, t in pairs: out += f'g={g}\t' + t.replace('\\', '\\\\').replace('\n', '\\n') + '\n'
    return out.encode()


def mark(m, cell_h=None):
    """Remember the list's geometry while the list is showing: where its cells start and the content's height (the page is the other height)."""
    m.hdr_h, m.list_h, m.cell_h = PCP.hdr(m), m.props[(m.sv, 'virtual_h')], cell_h or O['PS_CELL_H']
    return m


def shown_with_notes(pairs=(('g0', NOTE_EN), ('g3', NOTE_ZH)), **kw):
    m = PCS.shown(**kw)
    if pairs: m.put(f'{RP}/{DEEP}/.notes', notes_blob(pairs))
    return mark(m)


def delta(got, want):
    """What differs between two sets of drawn texts, for a failure's message."""
    return f'extra {sorted(got - want)[:3]} missing {sorted(want - got)[:3]}'


def page_texts(m):
    """{(style, text, x, content y)} of the whole episode page: frames 100 px apart (a text is drawn only wholly inside the view)."""
    h = m.props[(m.sv, 'virtual_h')]
    seen = set()
    for off in range(0, max(h - O['GRID_VIEW_H'], 0) + 100, 100):
        _, texts, styles, _ = PCP.paint(m, off)
        for (t, r), s in zip(texts, styles): seen.add((s, t, r[0], r[1] + off))
    return seen


def open_ep(m, i, off=0, **kw):
    """A tap on the date line (the body) of cell i of the list."""
    PCP.tap(m, 150, m.hdr_h + i * m.cell_h + 12, off=off, **kw)


def is_page(m):
    return m.props[(m.sv, 'virtual_h')] != m.list_h


def expected_page(m, i, desc, has_pill=True, hint=False):
    """pod_show.detail_layout for episode i of the Deep show as the page should have it: (layout, the set of texts it should draw)."""
    L = pod_show.detail_layout(PCS.font(), (PF.cut_utf8(PCS.LONG_TITLE, 95) if i == 0 else f'Episode {i}'), PCS.SHOW_TITLE, desc, has_pill=has_pill)
    want = {('label_ps_head', t, PD['PD_X'], L['y_title'] + k * PD['PD_TITLE_PITCH']) for k, t in enumerate(L['title'])}
    want.add(('label_ps_meta', L['show'], PD['PD_SHOW_TEXT_X'], L['y_show'] + (PD['PD_SHOW_H'] - PD['PD_SHOW_TEXT_H']) // 2))
    want |= {('label_ps_meta' if L['hint'] else 'label_ps_sec', t, PD['PD_X'], y) for t, y in L['desc']}
    return L, want


def page_tests(ctx):
    """The page from a subscribed show: the layout against the model, the grey line, the date's badges, the pill and the sheet, Back."""
    expect = ctx.expect
    m = shown_with_notes()
    expect(not is_page(m), 'the list first')
    m.calls = []
    open_ep(m, 0)
    expect(is_page(m) and not [c for c in m.calls if c[0] in ('navigator_to_with_context', 'pthread_create')], 'a tap on a cell\'s body opens the page (nothing plays, nothing is queued)')
    L, want = expected_page(m, 0, NOTE_EN)
    seen = page_texts(m)
    got = {t for t in seen if t[0] in ('label_ps_head', 'label_ps_meta', 'label_ps_sec')}
    expect(got == want and m.props.get((m.sv, 'virtual_h')) == L['h'], f'the title ({len(L["title"])} lines), the show name "{L["show"]}" and the description ({len(L["desc"])} lines) are where tools/pod_show.py puts them; the content is {L["h"]} px ({delta(got, want)})')
    expect(len(L['title']) >= 3 and len(L['desc']) > 12 and L['h'] > O['GRID_VIEW_H'] + 150, f'the page scrolls as a whole: {L["h"]} px of content for a 400 px view')
    expect(L['show'].startswith('All-In') and PCS.font().width(L['show'], 15) <= PD['PD_SHOW_TEXT_W'], f'the show row\'s name fits its room: {L["show"]!r}')
    date = [t for t in seen if t[0] == 'label_ps_date']
    expect(len(date) == 1 and date[0][3] == L['y_date'] and date[0][2] == PD['PD_X'] + O['PS_BADGE_DISC_W'] and date[0][1].endswith('ago · 48 MB') and L['y_date'] == PD['PD_TOP'], f'the date line is the first thing: the downloaded badge, the cell\'s date and the size ({date})')
    bl, texts, styles, _ = PCP.paint(m, 0)
    ry = L['y_show'] + (PD['PD_SHOW_H'] - PD['PD_COVER']) // 2
    expect(not [b for b in bl if tuple(b[2][2:]) == (O['PS_ART'], O['PS_ART'])] and [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (PD['PD_COVER'], PD['PD_COVER'])] == [(PD['PD_X'], ry, 32, 32)], 'no big cover: the show row has the show\'s cover, 32 px at the text edge')
    chev = [b for b in bl if tuple(b[1]) == (0, 0, 10, 16)]   # the shared chevron bitmap (POD_CHEV_W x POD_CHEV_H)
    expect(len(chev) == 1 and tuple(chev[0][2]) == (PD['PD_CHEV_X'], L['y_show'] + (PD['PD_SHOW_H'] - 16) // 2, 10, 16) and PD['PD_CHEV_X'] == O['LIST_CHEV_X'] and PD['PD_SHOW_TEXT_X'] + PD['PD_SHOW_TEXT_W'] == O['LIST_CHEV_X'] - 10, 'and the shared chevron at the row\'s right (x 288, the name ends at 278)')
    expect(L['y_title'] == L['y_date'] + PD['PD_DATE_H'] + PD['PD_GAP_DATE'] and L['y_pill'] == L['y_show'] + PD['PD_SHOW_H'] + PD['PD_GAP_SHOW'] and L['y_desc'] == L['y_pill'] + PD['PD_PILL_ROW'] + PD['PD_GAP_PILL'], 'top to bottom: the date line, the title, the show row, the pill row, the description')
    ypill = L['y_pill']
    pill = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_ps_pill']
    expect(pill and pill[0][0] == '72m' and pill[0][1][1] == ypill and pill[0][1][0] == PD['PD_X'] + O['PS_PILL_PADL'] + O['PA_G_PX'] + O['PS_PILL_GAP'], f'the state pill of the cell (the play pill with the length) at the page\'s pill row ({pill})')
    dots = [b for b in bl if tuple(b[1]) == (0, O['PA_DOTS_Y'], O['PA_DOTS_PX'], O['PA_DOTS_PX'])]
    expect(len(dots) == 1 and tuple(dots[0][2][:2]) == (O['PS_DOTS_CX'] - 10, ypill + 5), 'and the cell\'s "..." at its right')
    expect(flags(m, 'btn_more') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np' and m.props.get((m.widgets['label_title'], 'visible'), 0) == 0,
           'the navbar: Back and the Now Playing disc (no "...", no title)')
    # the second paragraph of the zh note, a remote episode: another page
    PCP.click(m, 'btn_return')
    expect(not is_page(m), 'Back: the list')
    open_ep(m, 3)
    L3, want3 = expected_page(m, 3, NOTE_ZH)
    got3 = {t for t in page_texts(m) if t[0] in ('label_ps_head', 'label_ps_meta', 'label_ps_sec')}
    expect(got3 == want3, f'a remote episode with a Chinese note: {len(L3["desc"])} lines, wrapped between any two characters, as the model has them ({delta(got3, want3)})')
    ls = [t for t, y in L3['desc']]
    bad_start = [l for l in ls if l[0] in '，。、！？；：）”’》」』】…—,.!?;:)']
    bad_end = [l for l in ls if l[-1] in '“‘（《「『【(']
    expect(not bad_start and not bad_end and any('）' in l or '”' in l for l in ls), f'kinsoku: no line starts with closing punctuation or ends with an opening bracket ({bad_start} {bad_end})')
    f = PCS.font()
    expect(all(f.width(l, 16) <= PD['PD_W'] for l in ls), f'every line fits {PD["PD_W"]} px')
    ds = [t for t in page_texts(m) if t[0] == 'label_ps_date']
    expect(len(ds) == 1 and ds[0][2] == PD['PD_X'], 'a remote episode has no badge: the date starts at the text edge')
    PCP.click(m, 'btn_return')


def flags(m, n): return m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1)


def tap_show_row(m, off=0):
    """A tap in the middle of the page's show row (its name is drawn at y_show + 9 in a 22 px line)."""
    y = next(r[1] for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == 'label_ps_meta' and r[0] == PD['PD_SHOW_TEXT_X'])
    PCP.tap(m, 150, y + PD['PD_SHOW_TEXT_H'] // 2, off=off)


def show_row_tests(ctx):
    """The show row: a tap opens the show's own page (the list, at the offset it had; Back goes on to the Shows level); in a search preview it goes back to that preview (see preview_tests)."""
    expect = ctx.expect
    m = shown_with_notes()
    open_ep(m, 5, off=800)
    expect(is_page(m), 'an episode page, opened from the list scrolled to 800')
    m.calls = []
    tap_show_row(m)
    expect(not is_page(m) and m.props.get((m.sv, 'yoffset')) == 800 and m.props[(m.sv, 'virtual_h')] == m.list_h and not [c for c in m.calls if c[0] in ('navigator_to_with_context', 'pthread_create')],
           'a tap on the show row: the show\'s page, the list at the offset it had (from the Show page that is going back to it)')
    expect(flags(m, 'btn_more') == (1, 1), 'its navbar is the list\'s again ("..." | Now Playing)')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts', 'Back from the list: the Shows level, as before')
    # a tap above the row (the title) or below it (the description) does nothing
    m = shown_with_notes()
    open_ep(m, 0)
    L, _ = expected_page(m, 0, NOTE_EN)
    PCP.tap(m, 150, L['y_title'] + 10)
    PCP.tap(m, 150, L['y_show'] - 3)
    PCP.tap(m, 150, L['y_show'] + PD['PD_SHOW_H'] + 1)
    expect(is_page(m), 'a tap on the title, just above or just below the row: the page stays')


def tint_page_tests(ctx):
    """The page is plain black: no cover tint, the status bar black, the plain fade under the navbar; Back brings the Show page's tint and the bar's colour back; the window's events do not tint it."""
    expect = ctx.expect
    import mod_nowplaying as mn
    word, tone = PCS.tone_word(PCS.RED), mn.tone(*PCS.RED)
    BG, FG = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']
    m = PCS.machine()
    m.with_bar()
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.put(f'{RP}/{DEEP}/.notes', notes_blob([('g0', NOTE_EN), ('g3', NOTE_ZH)]))
    PCS.open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    mark(m)
    img = m.widgets['img_ah_tint']
    win = lambda: [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(win()[-1][2] == word and m.props.get((img, 'visible')) == 1 and m.bar_styles()[-1] == PCS.bar_model(tone), 'the Show page is tinted: the window, the gradient and the status bar')
    open_ep(m, 0)
    for _ in range(3): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(win()[-1][2] == 0xff000000 and m.props.get((img, 'visible')) == 0 and m.bar_styles()[-1] == PCS.BAR_BLACK, 'the episode page: the window is black, the gradient hidden and the status bar black')
    fn_ev = lambda ev: m.call(m.bound[(m.window, ev)][0], a0=m.bound[(m.window, ev)][1], a1=0, count=2000000)
    fn_ev(BG); fn_ev(FG)
    expect(m.bar_styles()[-1] == PCS.BAR_BLACK and win()[-1][2] == 0xff000000, 'the window to the background and back: the bar stays black, the page is not tinted')
    fn_, ctx_ = m.bound[(m.sv, O['EVT_SCROLL'])]
    fade = m.widgets['img_nb_fade']
    expect(m.props.get((fade, 'visible'), 0) == 0 and not [f for f in PCP.paint(m, 0)[3] if f[1] == 0 and f[3] == 320 and f[4] == 1 and f[2] < 20], 'at rest: no fade')
    m.props[(m.sv, 'yoffset')] = 200; m.setword(m.sv + PCP.SC_YOFF, 200)
    m.call(fn_, a0=ctx_, a1=0, count=4000000)
    expect(m.props.get((fade, 'visible')) == 1 and not [f for f in PCP.paint(m, 200)[3] if f[1] == 0 and f[3] == 320 and f[4] == 1 and f[2] < 20] and m.props.get((m.widgets['label_title'], 'visible'), 0) == 0,
           'scrolled: the plain black fade of our other pages (the stock fade shows), not the page\'s tinted one; still no navbar title')
    PCP.click(m, 'btn_return')
    expect(win()[-1][2] == word and m.props.get((img, 'visible')) == 1 and m.bar_styles()[-1] == PCS.bar_model(tone) and m.props.get((fade, 'visible'), 0) == 0,
           'Back: the Show page\'s tint, the gradient and the status bar colour are back, the stock fade hidden')
    # the page opened before the tint was known (a cover still loading): the tint arrives under the page without showing
    m = PCS.machine()
    m.with_bar()
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.put(f'{RP}/{DEEP}/.notes', notes_blob([('g0', NOTE_EN)]))
    PCS.open_show(m)
    mark(m)
    open_ep(m, 0)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    win = [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(is_page(m) and (not win or win[-1][2] == 0xff000000) and not [b for b in m.bar_styles() if b != PCS.BAR_BLACK] and m.props.get((m.widgets['img_ah_tint'], 'visible'), 0) == 0,
           'the cover finishes loading under the page: the tone is kept but nothing is tinted')
    PCP.click(m, 'btn_return')
    win = [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(win and win[-1][2] == word and m.bar_styles()[-1] == PCS.bar_model(tone), 'Back: the tint that arrived meanwhile shows')


def pill_tests(ctx):
    """The pill and the "..." of the page do what the cell's do; Back closes the sheet first and keeps the list's place."""
    expect = ctx.expect
    m = shown_with_notes()
    def pill_of(mm):
        return [t for (t, r), s in zip(*PCP.paint(mm, 0)[1:3]) if s == 'label_ps_pill']

    def tap_pill(mm):
        PCP.tap(mm, 30, page_y(mm) + O['PS_PILL_H'] // 2)

    # local: the pill plays it with the queue of the files
    open_ep(m, 0)
    m.calls = []
    tap_pill(m)
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    q, idx = m.played
    expect(len(nav) == 1 and idx == 0 and [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q] == [f'{RP}/{DEEP}/e{i}.mp3' for i in range(3)], 'the page\'s play pill plays the episode with the files that follow')
    PCP.click(m, 'btn_return')
    # remote: a tap downloads, the pill shows Waiting, a second tap takes it out of the queue
    open_ep(m, 3)
    m.thread = None
    expect(pill_of(m) == ['48 MB'], f'a remote episode: the download pill ({pill_of(m)})')
    tap_pill(m)
    expect(DL.state(m, 'e3.mp3', DEEP)[0] == 1 and pill_of(m) == ['Waiting'], f'the pill queues the download; the page paints Waiting ({pill_of(m)})')
    tap_pill(m)
    expect(DL.state(m, 'e3.mp3', DEEP)[0] == 0 and pill_of(m) == ['48 MB'], 'a second tap takes it out of the queue')
    # the "..." opens the cell's sheet: Download and Mark as Played
    PCP.tap(m, O['PS_DOTS_CX'], page_y(m) + O['PS_PILL_H'] // 2)
    rows = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}')[0] == 1]
    expect(flags(m, 'pg_sh_card') == (1, 1) and rows == ['dl', 'mark'], f'the "..." opens the cell\'s sheet: Download and Mark as Played ({rows})')
    PCP.click(m, 'btn_return')
    expect(flags(m, 'pg_sh_card')[0] == 0 and is_page(m), 'Back closes the sheet first and stays on the page')
    PCP.tap(m, O['PS_DOTS_CX'], page_y(m) + O['PS_PILL_H'] // 2)
    PCP.click(m, 'pg_sh_dl')
    expect(DL.state(m, 'e3.mp3', DEEP)[0] == 1 and flags(m, 'pg_sh_card')[0] == 0 and pill_of(m) == ['Waiting'], 'Download in the sheet queues it')
    PCP.tap(m, O['PS_DOTS_CX'], page_y(m) + O['PS_PILL_H'] // 2)
    PCP.click(m, 'pg_sh_mark')
    bl = PCP.paint(m, 0)[0]
    expect([b for b in bl if tuple(b[1]) == (O['PA_CHECK'] * O['PA_G_PX'], O['PA_G_Y'], O['PA_G_PX'], O['PA_G_PX'])], 'Mark as Played: the date line has the check badge')
    PCP.click(m, 'btn_return')
    # a started and a failed episode, on the page
    open_ep(m, 2)
    expect(pill_of(m) == ['35m left'], f'a started episode: the resume pill ({pill_of(m)})')
    PCP.click(m, 'btn_return')
    open_ep(m, 7)
    m.thread = None
    expect(pill_of(m) == ['Retry'], 'a failed episode: Retry')
    tap_pill(m)
    expect(DL.state(m, 'e7.mp3', DEEP)[0] == 1, 'Retry tries again')
    PCP.click(m, 'btn_return')
    # Remove Download on the page: the page stays, the episode is a download cell again
    open_ep(m, 1)
    expect(pill_of(m) and pill_of(m)[0].endswith('m'), 'a played episode on the card')
    PCP.tap(m, O['PS_DOTS_CX'], page_y(m) + O['PS_PILL_H'] // 2)
    PCP.click(m, 'pg_sh_rm')
    expect(is_page(m) and f'{RP}/{DEEP}/e1.mp3' not in m.fs and pill_of(m) == ['48 MB'], f'Remove Download on the page: the file goes, the page stays on its episode ({pill_of(m)})')
    PCP.click(m, 'btn_return')
    # Back keeps the list's place
    off = 800
    open_ep(m, 5, off=off)
    expect(is_page(m) and m.props.get((m.sv, 'yoffset')) == 0, 'opened from a list scrolled to 800: the page starts at its top')
    PCP.click(m, 'btn_return')
    expect(not is_page(m) and m.props.get((m.sv, 'yoffset')) == off and m.props[(m.sv, 'virtual_h')] == m.hdr_h + 8 * O['PS_CELL_H'] + O['PS_MORE_H'] + 20, 'Back: the list at the same scroll offset (800)')
    # a drag or a tap off the cell opens nothing
    m.calls = []
    open_ep(m, 5, off=off, move=40)
    expect(not is_page(m), 'a drag on a cell opens nothing')


def page_y(m):
    """The content y of the open page's pill row: where the pill's label is drawn."""
    return next(y for (s, t, x, y) in sorted(page_texts(m)) if s == 'label_ps_pill')


def local_tests(ctx):
    """A local show and a feed refreshed before the notes existed: x= (or the hint)."""
    expect = ctx.expect
    # x= for a feed with no .notes
    m = mark(PCS.shown())
    open_ep(m, 1)
    L, want = expected_page(m, 1, 'About episode 1.')
    got = {t for t in page_texts(m) if t[0] in ('label_ps_head', 'label_ps_meta', 'label_ps_sec')}
    expect(got == want, f'no .notes file (a feed refreshed before this change): the description is x= until the next refresh ({delta(got, want)})')
    PCP.click(m, 'btn_return')
    # a note for another guid only: x= again
    m.put(f'{RP}/{DEEP}/.notes', notes_blob([('other', NOTE_EN)]))
    open_ep(m, 1)
    got = {t for t in page_texts(m) if t[0] in ('label_ps_head', 'label_ps_meta', 'label_ps_sec')}
    expect(got == want, 'a .notes with no line for the episode: x=')
    PCP.click(m, 'btn_return')
    # a local show: no feed, no guids; x= when the folder has it, else the hint
    es = [PCS.entry(i, g='') for i in range(3)]
    es[1]['x'] = ''
    m = mark(PCS.shown(feed=False, entries=es, files=(0, 1, 2)))
    open_ep(m, 0)
    L, want = expected_page(m, 0, 'About episode 0.')
    expect(is_page(m) and not [t for t in page_texts(m) if t[0] == 'label_ps_head' and t[1] == 'x'], 'a local show\'s page opens')
    got = {t for t in page_texts(m) if t[0] in ('label_ps_meta', 'label_ps_sec')}
    expect(any(t[0] == 'label_ps_sec' and t[1] == 'About episode 0.' for t in got), 'a local show with x= in its .episodes: that text')
    PCP.click(m, 'btn_return')
    open_ep(m, 1)
    seen = page_texts(m)
    expect([t[1] for t in seen if t[0] == 'label_ps_meta' and t[1] == 'No description'] == ['No description'] and not [t for t in seen if t[0] == 'label_ps_sec'], 'no note, no x=: "No description" in the grey line\'s style')
    PCP.click(m, 'btn_return')


def preview_tests(ctx):
    """A search preview's episode: the page from the held feed's notes (no pill, no \"...\"); Back to the preview; Subscribe writes the .notes an import and a refresh write."""
    expect = ctx.expect
    import json
    SU = sibling('pcsearchui')
    first = json.loads(SU.ALL_IN)['results'][0]['feedUrl']
    site = SU.site_for(**{first: {'body': SU.WSJ}})
    m = SU.opened(site=site)
    SU.stage(m, 'all in')
    L0 = pod_show.search_layout(25)
    PCP.tap(m, 150, L0['rows'][0] + 30)
    SU.work(m); SU.tick(m)
    mark(m, O['PS_PCELL_H'])
    open_ep(m, 0)
    expect(is_page(m) and not [t for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_pill'] and flags(m, 'btn_more') == (0, 0), 'a tap on a preview cell opens the page: no pill, no "...", no "..." in the navbar')
    p = N_wsj()
    seen = page_texts(m)
    desc = [t for t in seen if t[0] == 'label_ps_sec']
    note0 = p['notes'][0]
    L = pod_show.detail_layout(PCS.font(), p['titles'][0], 'WSJ Minute Briefing', note0, has_pill=False)
    expect(sorted((t[1], t[3]) for t in desc) == sorted(L['desc']) and m.props[(m.sv, 'virtual_h')] == L['h'], f'the description is the held feed\'s note for that item ({len(L["desc"])} lines) {sorted((t[1][:12], t[3]) for t in desc)[:2]} {sorted((t[:12], y) for t, y in L["desc"])[:2]} {m.props[(m.sv, "virtual_h")]} {L["h"]}')
    m.thread = None
    PCP.tap(m, 30, 200); PCP.tap(m, O['PS_DOTS_CX'], 300)
    chev = [b for b in PCP.paint(m, 0)[0] if tuple(b[1]) == (0, 0, 10, 16)]
    expect(not m.thread and m.props.get((m.widgets['pg_sh_card'], 'visible'), 0) == 0 and is_page(m) and len(chev) == 1 and tuple(chev[0][2])[0] == PD['PD_CHEV_X'],
           'nothing on the page starts a download or a sheet; the show row has the list chevron')
    tap_show_row(m)
    expect(not is_page(m) and [t for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_latest'], 'a tap on the show row: back to the preview\'s list with its Subscribe pill')
    open_ep(m, 0)
    expect(is_page(m), 'the episode page again')
    PCP.click(m, 'btn_return')
    expect(not is_page(m) and [t for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_latest'], 'Back: the preview\'s list with its Subscribe pill')
    open_ep(m, 1)
    expect(is_page(m), 'the second episode too')
    PCP.click(m, 'btn_return')
    # Subscribe: .notes beside .episodes, the same bytes an import and a refresh write
    _, texts, styles, _ = PCP.paint(m, 0)
    y_latest = [r[1] for (t, r), s in zip(texts, styles) if s == 'label_ps_latest'][0]
    PCP.tap(m, 160, y_latest + 10)
    folder = f'{RP}/WSJ Minute Briefing'
    notes = m.fs.get(f'{folder}/.notes', b'')
    expect(notes.startswith(b'M1PLUS-NOTES 1\ng=') and notes.count(b'\n') == 1 + len(p['notes']) - p['notes'].count(''), f'Subscribe writes .notes ({notes.count(b"\n") - 1} lines)')
    # the real page of the new show reads it
    mark(m)
    open_ep(m, 0)
    seen = page_texts(m)
    expect(is_page(m) and sorted((t[1], t[3]) for t in seen if t[0] == 'label_ps_sec') == sorted(pod_show.detail_layout(PCS.font(), p['titles'][0], 'WSJ Minute Briefing', note0, has_pill=True)['desc']),
           'the subscribed show\'s page reads the note from the file')


def N_wsj():
    """The WSJ fixture's three items as the oracle has them: titles, durations, lengths and notes."""
    raw = PCS.PCN.feed_bytes('wsj-3items.xml')
    _, _, kept, _ = PF.oracle(raw)
    root = PF.ET.fromstring(raw)
    its = {}
    for it in root.find('channel').findall('item'):
        enc = it.find('enclosure')
        guid = PF.norm(it.findtext('guid') or '', PF.GUID) or PF.norm(PF.norm(enc.get('url'), PF.URL), PF.GUID)
        its[guid] = it
    return dict(titles=[k[5] for k in kept], dur=[k[2] for k in kept], len=[k[3] for k in kept], notes=[item_note(its[k[0]]) for k in kept])


# ---------------------------------------------------------------------------

def width_tests(ctx):
    """The date line (the longest date, a year and the size, after both badges) and the hint in the 13 languages, in the real font: one line each."""
    expect = ctx.expect
    fnt = pod_show.Font(pod_show.font_path(WORK))
    worst = {}
    months = ('Jan %d', 'Feb %d', 'Mar %d', 'Apr %d', 'May %d', 'Jun %d', 'Jul %d', 'Aug %d', 'Sep %d', 'Oct %d', 'Nov %d', 'Dec %d')
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, *n, t=t: _fmt(pod_i18n.TEXT[key][t], n)
        dates = [tr(k, 30) + tr(', %d', 2025) for k in months] + [tr('Just now')] + [tr(k, 59) for k in ('%dm ago', '%dh ago', '%dd ago')]
        lines = [pod_show.detail_date(d, 999 << 20, pod_i18n.TEXT['%d MB'][t]) for d in dates]
        worst[loc] = dict(date=max(fnt.width(x, 15) for x in lines), hint=fnt.width(tr('No description'), 15))
    print('  widest per language (px):', {k: max(v[k] for v in worst.values()) for k in worst['en_US']}, 'in', {k: max(worst, key=lambda loc: worst[loc][k]) for k in worst['en_US']})
    bad = lambda k, room: [(loc, w[k]) for loc, w in worst.items() if w[k] > room]
    room = PD['PD_W'] - O['PS_BADGE_CHECK_W'] - O['PS_BADGE_DISC_W']
    expect(not bad('date', room), f'the date line ("Dec 30, 2025 · 999 MB") fits after both badges ({room} px) in every language ({bad("date", room)})')
    expect(not bad('hint', PD['PD_W']), f'"No description" fits a line in every language ({bad("hint", PD["PD_W"])})')


def _fmt(s, nums):
    for n in nums: s = s.replace('%d', str(n), 1)
    return s


def screen_off_tests(ctx):
    """The page does no visual work in the dark: the tick that reads the episodes again, the loader; no timer of its own."""
    expect = ctx.expect
    m = shown_with_notes()
    open_ep(m, 3)
    timers = [c for c in m.calls if c[0] == 'timer_add']
    m.calls = []
    m.screen(False)
    DL.poke_slot(m, 0, DEEP, 'e5.mp3', 2, seq=1)
    m.setword(DL.pn_at(12), 4242); m.setword(DL.pn_at(DL.DGEN), 4242)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_text_utf8', 'widget_set_visible', 'widget_resize', 'widget_move', 'widget_set_style', 'bitmap_create_ex', 'widget_load_image')] and is_page(m) is not None,
           'screen off: a tick with the worker moved on does no widget, bitmap or style work with the page open')
    m.screen(True)
    m.calls = []
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(is_page(m) and any(c[0] == 'widget_invalidate_force' for c in m.calls), 'the screen is back: the first tick reads the episodes again and the page is still on its episode')
    expect(not [c for c in m.calls if c[0] == 'timer_add'] and not timers, 'the page adds no timer of its own')


def goto_tests(ctx):
    """Go to Podcasts (Now Playing's More sheet, patch/podcasts.c podcasts_go): no Podcasts page in the stack: it opens at the Shows level; one below Now Playing: Now Playing is closed over it and no
    second page opens (V2.1zCQUGAAAE closed the old page and refused while AWTK had not destroyed it yet: the row did nothing)."""
    expect = ctx.expect
    def go(m): return m.call(PSYMS['podcasts_go'], count=80000000)
    m = PCS.machine(up=False)
    expect(go(m) == 0 and ('window_open', 'm1plus_podcasts') in m.calls and PCP.title_text(m) == 'Podcasts', 'Go to Podcasts: the page opens at the Shows level')
    m = PCS.machine(); m.windows = {'playing_page'}; m.calls = []
    expect(go(m) == 0 and ('navigator_close', 'playing_page') in m.calls and ('window_open', 'm1plus_podcasts') not in m.calls and ('navigator_close', 'm1plus_podcasts') not in m.calls,
           f'a Podcasts page below Now Playing: Now Playing is closed, the page is kept as it was ({m.calls})')
    m = PCS.machine(); m.calls = []
    expect(go(m) == 0 and not [c for c in m.calls if c[0] in ('navigator_close', 'window_open')], 'a Podcasts page in front already: nothing is closed or opened')


SECTIONS = [parser_tests, notes_file_tests, page_tests, pill_tests, show_row_tests, tint_page_tests, local_tests, preview_tests, width_tests, screen_off_tests, goto_tests]

"""AutoEq download (patch/autoeq.c, patch/pcnet.c "AutoEq", patch/peq_ui.c peq_select, patch/peq.c; docs/modules/peq.md "AutoEq download"), on the real compiled payload under Unicorn with the worker
thread run by the test and the AutoEq site scripted (fixture test/data/autoeq/INDEX.md: 60 real lines of results/INDEX.md).

Proved: the index line parser against a Python split of every fixture line (name, source, target, kind, path) and the lines it must refuse; the search (every word a case-insensitive substring of the name, the tiers, the
file's order, the cap of 20, every source and no filter, lines too long, CRLF) against a Python oracle; the job against a scripted libcurl (the two URLs, https only, verification on, the index only renamed into place when it starts
with the project's heading, the date written, every failure leaving the old files, Cancel, one worker at a time, a bad preset path never asked for); the page (opening with and without the list, the list's progress and
failure and its retry, the background refresh of an old list, a result's states, the download and what is installed, the names of a taken name, "Tap to use", a file that does not parse, the Wi-Fi lost, the slot busy,
destroy while a job runs); the glyphs' pixels."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
from unicorn.mips_const import UC_MIPS_REG_CP0_STATUS

ROW = 52   # AE_ROW_H

S, PCN, PEQ = sibling('search'), sibling('pcnet'), sibling('peq')
AE_LIST_Y = 98   # patch/autoeq.c AE_LIST_Y: the bar (50) and Radio's search list top (48)
AE_ASSET = os.path.join(os.path.dirname(S.ASSET), 'm1plus_autoeq.bin')   # ui/m1plus_autoeq.bin: its own window (tools/pod_ui.py build_autoeq_page)
LIST_Y0 = S.LIST_Y0 - S.D['SE_LIST_Y'] + AE_LIST_Y   # the list's top on the screen: the status bar (30) and the list's y
DATA = os.path.join(ROOT, 'test', 'data', 'autoeq')
INDEX = open(os.path.join(DATA, 'INDEX.md'), 'rb').read()
DIR, IDX, PART, STAMP, PRESET = '/mnt/mmc/.m1plus/autoeq', '/mnt/mmc/.m1plus/autoeq/index.md', '/mnt/mmc/.m1plus/autoeq/index.part', '/mnt/mmc/.m1plus/autoeq/updated', '/mnt/mmc/.m1plus/autoeq/preset.part'
EQ, STATE = '/mnt/mmc/EQ', '/mnt/data/m1plus/playback-eq'
BASE = 'https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/'
RET_REPEAT = 8
PN = dict(PCN.PN, CANCELLED=12, CARDFULL=13, NOFEED=16)
E = dict(IDLE=0, RUNNING=1, DONE=2, FAILED=3)
HD600 = 'oratory1990/over-ear/Sennheiser%20HD%20600'
HD600_RTINGS = 'Rtings/Bruel%20&%20Kjaer%205128%20over-ear/Sennheiser%20HD%20600'
PRESET_TXT = PEQ.AUTOEQ
WALL = 1_800_000_000
ENT = struct.Struct('<64s24s24sBB200s')   # ae_ent: name, src, tgt, form, tier, path


def purl(path):
    return BASE + path + '/' + path.rsplit('/', 1)[1] + '%20ParametricEQ.txt'


class AM(PCN.NM):
    """The AutoEq window's widgets (m1plus_autoeq, built on the Search page's widgets: test/pod/search.py), the card, the Wi-Fi, the stock Equalizer's state, the scripted AutoEq site."""


def machine(site=None, index=True, stamp=WALL, **kw):
    m = AM()
    m.u.reg_write(UC_MIPS_REG_CP0_STATUS, m.u.reg_read(UC_MIPS_REG_CP0_STATUS) | PEQ.FR)
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus', DIR, EQ})
    m.present.add(PCN.CA)
    m.curl_site = site or (lambda url, o: {'rc': 6})
    m.jinit()
    m.wall = WALL
    if index is True: index = INDEX
    if index is not False and index is not None: m.fs[IDX] = index
    if index is not False and index is not None and stamp is not None: m.fs[STAMP] = f'{stamp}\n'.encode()
    S.search_widgets(m, asset=AE_ASSET, key='m1plus_autoeq', list_y=AE_LIST_Y)
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([0])); m.setword(pod.DATA['EQ_MODE'][0], 4)
    for k, v in kw.items(): setattr(m, k, v)
    return m


def site(index=INDEX, presets=None, log=None, index_over=None):
    """The scripted AutoEq site: results/INDEX.md, the presets by url (bytes, or a dict for the scripted libcurl), a 404 for anything else."""
    presets = presets or {}

    def f(url, o):
        if log is not None: log.append((url, dict(o)))
        if url == BASE + 'INDEX.md': return {'body': index, **(index_over or {})}
        if url in presets:
            v = presets[url]
            return v if isinstance(v, dict) else {'body': v}
        return {'rc': 22, 'code': 404}
    return f


def jobs(m):
    """Run the pending worker (the thread the payload started) to its end."""
    n = 0
    while m.thread and n < 4:
        th, m.thread = m.thread, None
        PCN.work(m, th); n += 1
    return n


def st(m): return (m.call(PSYMS['pn_eq_state'], count=1 << 30), m.call(PSYMS['pn_eq_code'], count=1 << 30), m.call(PSYMS['pn_eq_mode'], count=1 << 30))


def start_index(m):
    m.thread = None
    return m.call(PSYMS['pn_eq_index'], count=1 << 30)


def start_get(m, path, stamp='# AutoEq: x'):
    m.thread = None
    return m.call(PSYMS['pn_eq_get'], a0=m.cstr(path), a1=m.cstr(stamp), count=1 << 30)


# ---- the index line parser
def py_parse(line):
    """The oracle: a split of the line at its fixed marks."""
    name, rest = line[3:].split('](./', 1)
    path, by = rest.split(') by ', 1)
    src, _, tgt = by.partition(' on ')
    kind = path.split('/')[1]
    form = 1 if kind.endswith('over-ear') else 2 if kind.endswith('in-ear') else 3 if kind.endswith('earbud') else 0
    return cut(name), src, tgt, form, path


def cut(name):
    """The name the page keeps: at most 63 bytes, cut at a character boundary."""
    b = name.encode()[:63]
    return b.decode('utf-8', 'ignore')


def ae_parse(m, raw):
    buf, out = m.alloc(len(raw) + 1), m.alloc(ENT.size + 8)
    m.u.mem_write(buf, raw + b'\0'); m.u.mem_write(out, b'\xaa' * ENT.size)
    r = m.call(PSYMS['ae_parse'], a0=buf, a1=len(raw), a2=out, count=2000000)
    name, src, tgt, form, tier, path = ENT.unpack(bytes(m.u.mem_read(out, ENT.size)))
    cs = lambda b: b.split(b'\0')[0].decode('utf-8')
    return r, (cs(name), cs(src), cs(tgt), form, cs(path)), tier


def parse_tests(ctx):
    expect = ctx.expect
    m = machine()
    lines = [l for l in INDEX.decode().split('\n') if l.startswith('- [')]
    bad = []
    for l in lines:
        r, got, _ = ae_parse(m, l.encode())
        if r != 1 or got != py_parse(l): bad.append((l[:60], got))
    expect(len(lines) == 60 and not bad, f'{len(lines)} real index lines parse as a split at their marks says (name, source, target, kind, path): {bad[:2]}')
    expect(ae_parse(m, lines[0].encode() + b'\r')[0] == 1 and ae_parse(m, lines[0].encode() + b'\r')[1] == py_parse(lines[0]), 'a CR at the end (a CRLF index) is dropped')
    # a name with parentheses and a source with a space, a target with an ampersand
    l = '- [Fischer Audio Oldskool RPM 33 1-3 (Zeppelin & Co Limited Edition)](./crinacle/GRAS%2043AG-7%20over-ear/Fischer%20Audio%20Oldskool%20RPM%2033%201-3%20(Zeppelin%20&%20Co%20Limited%20Edition)) by crinacle on GRAS 43AG-7'
    r, got, _ = ae_parse(m, l.encode())
    expect(r == 1 and got[0] == cut('Fischer Audio Oldskool RPM 33 1-3 (Zeppelin & Co Limited Edition)') and got[1:3] == ('crinacle', 'GRAS 43AG-7') and got[4].endswith('%20(Zeppelin%20&%20Co%20Limited%20Edition)'),
           'a name with parentheses, "&" and a path with its own ")": the first ") by " ends the path; the name is cut at 63 bytes')
    l = '- [Sennheiser HD 25](./Rtings/Bruel%20&%20Kjaer%205128%20over-ear/Sennheiser%20HD%2025) by Rtings on Bruel & Kjaer 5128'
    expect(ae_parse(m, l.encode())[1][1:3] == ('Rtings', 'Bruel & Kjaer 5128'), 'a target with an ampersand')
    for kind, form in (('over-ear', 1), ('in-ear', 2), ('earbud', 3), ('HMS%20II.3%20earbud', 3), ('711%20in-ear', 2), ('misc', 0), ('over-earx', 0)):
        got = ae_parse(m, f'- [N](./S/{kind}/N) by S'.encode())
        expect(got[0] == 1 and got[1][3] == form, f'the directory "{kind}" is kind {form}')
    for what, l in (('the heading', '# Index'), ('the prose', 'This is a list of all equalization profiles. Target is in parentheses if there are results with multiple targets'), ('an empty line', ''),
                    ('no source', '- [N](./S/over-ear/N)'), ('an empty name', '- [](./S/over-ear/N) by S'), ('a path with one level', '- [N](./S/N) by S'), ('a path with three levels', '- [N](./S/a/b/N) by S'),
                    ('an empty source', '- [N](./S/over-ear/N) by '), ('a path of 200 bytes', f'- [N](./S/over-ear/{"x" * 190}) by S'), ('a source of 24 bytes', f'- [N](./S/over-ear/N) by {"s" * 24}'),
                    ('a target of 24 bytes', f'- [N](./S/over-ear/N) by S on {"t" * 24}'), ('no link', '- N by S'), ('no ./', '- [N](S/over-ear/N) by S'), ('too short', '- [a](./b)')):
        expect(ae_parse(m, l.encode())[0] == 0, f'{what} is not a result')
    expect(ae_parse(m, f'- [N](./S/over-ear/{"x" * 180}) by S'.encode())[0] == 1, 'a path of 188 bytes fits')
    name = '周杰倫' * 30
    r, got, _ = ae_parse(m, f'- [{name}](./S/over-ear/N) by S'.encode())
    expect(r == 1 and name.startswith(got[0]) and 0 < len(got[0].encode()) <= 63 and len(got[0].encode()) >= 60, f'a name over 63 bytes is cut at a character boundary ({len(got[0].encode())} bytes)')


# ---- the page
def settle(m, limit=80):
    """The page's timer run to its end (a tick that answers RET_REPEAT keeps it), the worker run whenever the payload started one. The ticks run."""
    n = 0
    while n < limit:
        n += 1
        r = m.call(PSYMS['ae_tick'], a0=0, count=900000000)
        if m.thread: jobs(m)
        elif r != RET_REPEAT: break
    return n


def opened(site_=None, **kw):
    m = machine(site_, **kw)
    assert m.call(PSYMS['autoeq_open'], count=400000000) == 0
    return m


def typed(m, text):
    m.call(PSYMS['ae_on_text'], a0=m.cstr(text), count=2000000)
    settle(m)


def paint(m):
    ev = m.paint_event()
    m.setword(m.canvas + O['CANVAS_OY'], (LIST_Y0 - m.word(m.sv + S.SC_YOFF)) & 0xffffffff)
    m.texts.clear(); m.text_styles.clear(); m.fills.clear(); m.blits.clear()
    m.call(PSYMS['ae_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.texts), list(m.blits), list(m.fills)


def shown(m, off=0):
    """The rows as painted with the list scrolled `off` px: {row: (title, grey line)} of the rows in view."""
    m.setword(m.sv + S.SC_YOFF, off); m.props[(m.sv, 'yoffset')] = off
    texts, _, _ = paint(m)
    rows = {}
    for t, rect in texts:
        r, y = divmod(rect[1] + off, ROW)
        rows.setdefault(r, {})['title' if y == 3 else 'sub'] = t
    m.setword(m.sv + S.SC_YOFF, 0); m.props[(m.sv, 'yoffset')] = 0
    return {r: (v.get('title'), v.get('sub')) for r, v in rows.items()}


def all_rows(m, n=20):
    """Every row, scrolled into view a screen at a time: [(title, grey line)]."""
    out = {}
    for off in range(0, ROW * n, 300):
        for r, (a, b) in shown(m, off).items():
            o = out.get(r, (None, None))
            out[r] = (o[0] or a, o[1] or b)
    return [out[r] for r in sorted(out)]


def tap_row(m, r):
    m.calls = []
    y = r * ROW + ROW // 2
    m.touch('down', 100, LIST_Y0 + y, 1000, fn='ae_on_down', count=30000000)
    calls = list(m.calls)
    m.touch('up', 100, LIST_Y0 + y, 1080, fn='ae_on_up', count=30000000)
    m.calls = calls + m.calls
    return m.calls


def said(m, name='label_status'): return S.said(m, name)
def vis_prop(m, name): return m.props.get((m.widgets[name], 'visible'))


def oracle(lines, query, cap=20):
    """The results the page must show: every word a substring of the name (ASCII case folded), from any source, ordered by tier (0 the name is the query, 1 it starts with the first word, 2) then the file's order."""
    words = query.lower().split()
    out = []
    for l in lines:
        name, src, tgt, form, path = py_parse(l)
        n = name.lower()
        if not words or not all(w in n for w in words): continue
        tier = 0 if n == ' '.join(words) else 1 if n.startswith(words[0]) else 2
        out.append((tier, len(out), name, src, tgt, form, path))
    out.sort(key=lambda t: (t[0], t[1]))
    return [(name, src, tgt, form, path) for _, _, name, src, tgt, form, path in out[:cap]]


def sub_of(src, tgt, form):
    return ' · '.join([src] + ([{1: 'Over-ear', 2: 'In-ear', 3: 'Earbud'}[form]] if form else []) + ([tgt] if tgt else []))


def same(got, want):
    """A painted text is the wanted one, or its start and an ellipsis (the grid cuts a text to its width)."""
    return got == want or (got is not None and got.endswith('…') and want.startswith(got[:-1]))


def search_tests(ctx):
    expect = ctx.expect
    lines = [l for l in INDEX.decode().split('\n') if l.startswith('- [')]
    m = opened(site())
    expect(vis_prop(m, 'se_listview') == 0 and vis_prop(m, 'label_status') == 0 and not paint(m)[0], 'open with the list on the card: no rows, no state line')
    bad = []
    queries = ('hd 600', 'HD 6', 'sennheiser hd 650', 'airpods pro', 'k371', 'zeppelin', '2020', '  hd   600 ', 'hd', 'aero', 'sennheiser', 'hd 600 (2020)', 'SENNHEISER HD 600', 'sennheiser hd 600')
    for q in queries:
        typed(m, q)
        want = oracle(lines, q)
        got = all_rows(m)
        if len(got) != len(want) or not all(same(g[0], w[0]) and same(g[1], sub_of(*w[1:4])) for g, w in zip(got, want)): bad.append((q, got[:2], want[:2]))
    expect(not bad, f'the rows of {len(queries)} queries (every source) are the oracle\'s: every word a substring of the name, the tiers, the file\'s order, "Source · Kind · Target": {bad[:2]}')


def enc(s):
    from urllib.parse import quote
    return quote(s, safe='&()+,-._')


def line(name, src='oratory1990', kind='over-ear', tgt=''):
    return f'- [{name}](./{enc(src)}/{enc((tgt + " " if tgt else "") + kind)}/{enc(name)}) by {src}' + (f' on {tgt}' if tgt else '')


def synth(lines, eol='\n'):
    return (eol.join(['# Index', 'This is a list.', ''] + lines) + eol).encode()


def with_index(body): return opened(None, index=body)


def titles(m, n=20): return [r[0] for r in all_rows(m, n)]


def search2_tests(ctx):
    expect = ctx.expect
    # the tiers: the name is the query, the name starts with it, the rest; the file's order inside a tier; case folded on both sides
    m = with_index(synth([line('Zed Foo'), line('Foo Bar'), line('Foo'), line('Bar Foo'), line('foo', src='Rtings'), line('FOO BAR 2'), line('Fool')]))
    typed(m, 'foo')
    expect(titles(m) == ['Foo', 'foo', 'Foo Bar', 'FOO BAR 2', 'Fool', 'Zed Foo', 'Bar Foo'], f'tier 0 (the name is the query, any case), then names that start with it, then the rest, each in the file\'s order ({titles(m)})')
    typed(m, 'FOO bar')
    expect(titles(m) == ['Foo Bar', 'FOO BAR 2', 'Bar Foo'], f'two words: both must be in the name, in any order; "Foo Bar" is the whole query, "FOO BAR 2" starts with the first word ({titles(m)})')
    typed(m, 'bar foo')
    expect(titles(m) == ['Bar Foo', 'Foo Bar', 'FOO BAR 2'], f'the words the other way round: "Bar Foo" is the whole query now, the rest start with the second word, so tier 2 in the file\'s order ({titles(m)})')
    typed(m, '')
    expect(titles(m, 1) == [] and vis_prop(m, 'se_listview') == 0 and vis_prop(m, 'label_status') == 0, 'an emptied field: nothing is listed, no state line')
    typed(m, 'nothing')
    expect(titles(m, 1) == [] and said(m) == 'No Results' and vis_prop(m, 'label_status') == 1, 'a query nothing matches: "No Results"')
    typed(m, 'foo')
    expect(vis_prop(m, 'label_status') == 0, 'and the state line goes when something matches')
    # the cap of 20, and a better tier replacing the worst once the rows are full
    m = with_index(synth([line(f'Foo {i:02d}') for i in range(100)]))
    typed(m, 'foo')
    expect(titles(m, 30) == [f'Foo {i:02d}' for i in range(20)], 'a hundred matches: the first 20 of the file')
    m = with_index(synth([line(f'X Foo {i:02d}') for i in range(30)] + [line('Foo Late'), line('Foo')]))
    typed(m, 'foo')
    expect(titles(m, 30) == ['Foo', 'Foo Late'] + [f'X Foo {i:02d}' for i in range(18)], f'twenty results of tier 2 are full: a later tier 0 and tier 1 come before them and push the last out ({titles(m, 30)[:4]})')
    # lines too long are not results, and the line after is (the over-long flag is cleared); an index with CRLF; no trailing line feed; a result on the last line
    long_line = line('Foo Long ' + 'x' * 260)
    m = with_index(synth([line('Foo A'), long_line, line('Foo B')]).rstrip(b'\n'))
    typed(m, 'foo')
    expect(len(long_line) > 255 and titles(m) == ['Foo A', 'Foo B'], 'a line over 255 bytes is skipped as a whole, the next one read; the last line needs no line feed')
    m = with_index(synth([line('Foo A'), line('Foo B', src='Rtings')], eol='\r\n'))
    typed(m, 'foo')
    expect(titles(m) == ['Foo A', 'Foo B'] and [r[1] for r in all_rows(m)] == ['oratory1990 · Over-ear', 'Rtings · Over-ear'], 'an index with CRLF line ends')
    # a query of more words than the page takes: the first four
    m = with_index(synth([line('a b c d e')]))
    typed(m, 'a b c d zzz')
    expect(titles(m) == ['a b c d e'], 'words past the fourth are not looked at')
    # every row's grey line: the source, the kind, the target
    m = with_index(synth([line('H1', kind='in-ear', tgt='711'), line('H2', src='Rtings', kind='earbud'), line('H3', kind='misc')]))
    typed(m, 'h')
    expect([r[1] for r in all_rows(m)] == ['oratory1990 · In-ear · 711', 'Rtings · Earbud', 'oratory1990'], 'Source · Kind · Target, the kind only when the directory says one')
    # the keyboard's text only counts when it changes, and only a ready page searches
    n = m.call(PSYMS['ae_on_text'], a0=m.cstr('h'), count=2000000)
    expect(not [c for c in m.calls if c[0] == 'timer_add'] and n is not None, 'the same text again changes nothing')
    # the file is read in pieces, never held: no allocation beyond the page's own
    mall = [c for c in m.calls if c[0] in ('malloc', 'calloc')]
    expect(not mall, 'a repeat of the text allocates nothing')


def net_tests(ctx):
    expect = ctx.expect
    # the list: the url, https only, verification on (the CA bundle, no switch off), the part file renamed over index.md, the date written
    log = []
    m = machine(site(log=log), index=False)
    r = start_index(m)
    expect(r == 0 and st(m) == (E['RUNNING'], 0, 0) and m.thread, 'pn_eq_index starts the worker; the state is running, the list\'s job')
    jobs(m)
    o = log[0][1]
    expect(len(log) == 1 and log[0][0] == BASE + 'INDEX.md' and o[181] == 2 and o[182] == 2 and o[10065] == PCN.CA and 64 not in o and 81 not in o and o[10018].startswith('M1PlusMusic/') and o[45] == 1,
           f'one request, results/INDEX.md of the project, https only (also after a redirect), the firmware CA bundle, verification never switched off, the app\'s user agent ({log[0][0]})')
    expect(st(m) == (E['DONE'], 0, 0) and m.fs.get(IDX) == INDEX and PART not in m.fs and m.fs.get(STAMP) == f'{WALL}\n'.encode(), 'the list is renamed over index.md, no part file left, the day it came written')
    expect(m.call(PSYMS['pn_job_busy'], count=1 << 30) == 0, 'the slot is free again')
    m.call(PSYMS['pn_eq_reset'], count=1 << 30)
    expect(st(m)[0] == E['IDLE'], 'pn_eq_reset forgets a finished job')
    # failures keep what is there
    old = b'# Index\nthe list from before\n'
    for what, resp, code in (('no network', {'rc': 6}, 'NET'), ('a certificate the bundle lacks', {'rc': 60}, 'CERT'), ('a time-out (the Wi-Fi lost)', {'rc': 28}, 'NET'), ('HTTP 404', {'rc': 22, 'code': 404}, 'GONE'),
                             ('HTTP 500', {'rc': 22, 'code': 500}, 'HTTP'), ('a web page', {'body': b'<html>Not the list</html>'}, 'NOTFEED'), ('an empty answer', {'body': b''}, 'NOTFEED'),
                             ('a list that stops in the middle', {'body': INDEX[:2000], 'rc': 18, 'partial': True}, 'NET'), ('a list past 3 MB', {'body': INDEX + b'x' * 3200000}, 'NOTFEED')):
        m = machine(site(index=b'', index_over=resp), index=old, stamp=None)
        r = start_index(m)
        jobs(m)
        expect(r == 0 and st(m) == (E['FAILED'], PN[code], 0) and m.fs.get(IDX) == old and PART not in m.fs and STAMP not in m.fs, f'{what}: failed with {code}, the old list stays, no part file, no date')
    # the heading may arrive in pieces: checked as the bytes come
    for what, sizes in (('1+6', [1, 6, 16384]), ('3+4', [3, 4, 16384]), ('one byte at a time', [1])):
        m = machine(site(index=b'', index_over={'body': INDEX, 'chunk': sizes}), index=old, stamp=None)
        start_index(m); jobs(m)
        expect(st(m) == (E['DONE'], 0, 0) and m.fs.get(IDX) == INDEX and PART not in m.fs, f'the heading split {what}: the list is taken whole')
    for what, body, sizes, code in (('a wrong byte in the second piece (1+6)', b'# Indey' + INDEX[7:], [1, 6, 16384], 'NOTFEED'), ('a wrong byte in the second piece (3+4)', b'# I' + b'NDEX' + INDEX[7:], [3, 4, 16384], 'NOTFEED'),
                                    ('a wrong first piece', b'<ht' + INDEX[3:], [3, 16384], 'NOTFEED'), ('a body that ends inside the heading', b'# Ind', [16384], 'NOTFEED'), ('a body that ends inside the heading, in pieces', b'# Ind', [2, 3], 'NOTFEED')):
        m = machine(site(index=b'', index_over={'body': body, 'chunk': sizes}), index=old, stamp=None)
        start_index(m); jobs(m)
        expect(st(m) == (E['FAILED'], PN[code], 0) and m.fs.get(IDX) == old and PART not in m.fs and STAMP not in m.fs, f'{what}: {code}, the old list stays, no part file, no date')
    m = machine(site(), index=False, wifi=-1)
    expect(start_index(m) == PN['NOWIFI'] and st(m) == (E['FAILED'], PN['NOWIFI'], 0) and not m.thread, 'the Wi-Fi off: PN_NOWIFI at once, in the state too, no thread')
    m = machine(site(), index=False, wall=1000)
    expect(start_index(m) == PN['NOCLOCK'], 'a clock never set: PN_NOCLOCK')
    m = machine(site(), index=False); m.present.discard(PCN.CA)
    expect(start_index(m) == PN['NOCERT'], 'no CA bundle: PN_NOCERT')
    m = machine(site(), index=False, card_mounted=False)
    expect(start_index(m) == PN['STORAGE'], 'no card: PN_STORAGE')
    m = machine(site(), index=False)
    start_index(m)
    th = m.thread
    expect(start_index(m) == PN['BUSY'] and not m.thread and st(m)[0] == E['RUNNING'] and start_get(m, HD600) == PN['BUSY'], 'one job at a time: a second is PN_BUSY, and the running one is left as it is')
    m.thread = th; jobs(m)
    # Cancel: the transfer is aborted, nothing is kept
    m = machine(site(index_over={'xfer': lambda url, sent, total: None}), index=False)
    start_index(m)
    m.call(PSYMS['pn_cancel'], a0=1 << 9, count=1 << 30)   # PN_K_EQ
    jobs(m)
    expect(st(m) == (E['FAILED'], PN['CANCELLED'], 0) and IDX not in m.fs and PART not in m.fs, 'Cancel before the first byte: PN_CANCELLED, nothing written')
    # storage
    m = machine(site(), index=False)
    m.fail.add(('open', PART))
    start_index(m); jobs(m)
    expect(st(m) == (E['FAILED'], PN['STORAGE'], 0) and IDX not in m.fs, 'a part file that cannot be made: PN_STORAGE')
    m = machine(site(), index=old, stamp=None)
    m.fail.add(('rename', IDX))
    start_index(m); jobs(m)
    expect(st(m) == (E['FAILED'], PN['STORAGE'], 0) and m.fs.get(IDX) == old and PART not in m.fs, 'a rename that fails: PN_STORAGE, the old list stays, the part file is removed')
    m = machine(site(), index=False)
    m.fail.add(('write', PART))
    start_index(m); jobs(m)
    expect(st(m)[0] == E['FAILED'] and st(m)[1] in (PN['STORAGE'], PN['CARDFULL']) and PART not in m.fs and IDX not in m.fs, 'a write that fails (the card full): a storage code, no part file')

    # a preset: the address below the base, the stamp line first, the file left for the page at preset.part
    log = []
    m = machine(site(presets={purl(HD600): PRESET_TXT}, log=log), index=False)
    r = start_get(m, HD600, '# AutoEq: ' + HD600)
    expect(r == 0 and st(m) == (E['RUNNING'], 0, 1), 'pn_eq_get starts the worker; the job is a preset\'s')
    jobs(m)
    expect(log[0][0] == purl(HD600) and log[0][0].endswith('Sennheiser%20HD%20600/Sennheiser%20HD%20600%20ParametricEQ.txt') and log[0][1][181] == 2 and 64 not in log[0][1] and 81 not in log[0][1],
           f'the address: results/<path>/<name> ParametricEQ.txt, https only, verification on ({log[0][0]})')
    expect(st(m) == (E['DONE'], 0, 1) and m.fs.get(PRESET) == b'# AutoEq: ' + HD600.encode() + b'\n' + PRESET_TXT and IDX not in m.fs, 'the stamp line, a line feed and the file as the project has it, at preset.part; the list untouched')
    log = []
    m = machine(site(presets={purl(HD600_RTINGS): PRESET_TXT}, log=log), index=False)
    start_get(m, HD600_RTINGS); jobs(m)
    expect(log[0][0] == BASE + 'Rtings/Bruel%20&%20Kjaer%205128%20over-ear/Sennheiser%20HD%20600/Sennheiser%20HD%20600%20ParametricEQ.txt' and st(m)[0] == E['DONE'], 'a path with "&" and a target in its directory goes as the index has it')
    for what, resp, code in (('a 404', {'rc': 22, 'code': 404}, 'GONE'), ('no network', {'rc': 6}, 'NET'), ('an empty file', {'body': b''}, 'NOTFEED'), ('a file past 16 KB', {'body': b'x' * 16373}, 'NOTFEED')):
        m = machine(site(presets={purl(HD600): resp}), index=False)
        start_get(m, HD600); jobs(m)
        expect(st(m)[:2] == (E['FAILED'], PN[code]) and PRESET not in m.fs, f'{what}: {code}, no preset.part left')
    m = machine(site(presets={purl(HD600): {'body': b'x' * 16372}}), index=False)
    start_get(m, HD600); jobs(m)
    expect(st(m)[0] == E['DONE'], 'a file that is 16384 bytes with its stamp line is taken (the parser reads at most that; it decides)')
    m = machine(site(presets={purl(HD600): PRESET_TXT}), index=False)
    m.fail.add(('write', PRESET))
    start_get(m, HD600); jobs(m)
    expect(st(m)[:2] in ((E['FAILED'], PN['STORAGE']), (E['FAILED'], PN['CARDFULL'])) and PRESET not in m.fs, 'a write that fails: a storage code, no preset.part left')
    for what, path in (('an empty path', ''), ('a parent directory', '../x/y/z'), ('two levels', 'a/b'), ('four levels', 'a/b/c/d'), ('an address', 'http://x/y/z'), ('a space', 'a/b c/d'), ('a dot segment', 'a/./c'),
                       ('a double dot', 'a/b/..'), ('an empty segment', 'a//c'), ('a query', 'a/b/c?x=1'), ('a fragment', 'a/b/c#x'), ('a quote', 'a/b/c"d'), ('a backslash', 'a/b/c\\d'), ('a control character', 'a/b/c\x01'),
                       ('a leading slash', '/a/b/c'), ('a trailing slash', 'a/b/c/'), ('a colon first', ':a/b/c'), ('non ASCII', 'a/b/c\u00e9'), ('too long', 'a/b/' + 'c' * 400)):
        m = machine(site(), index=False)
        r = start_get(m, path)
        expect(r == PN['NOFEED'] and not m.thread, f'{what} is never asked for (PN_NOFEED)')
    for p_ in ('a/.b/c', 'a/b/c.d', 'a/..b/c', 'oratory1990/over-ear/Foo%20(2020,%20worn)'):
        m = machine(site(), index=False)
        expect(start_get(m, p_) == 0, f'{p_!r} is a fine path')
    m = machine(site(), index=False)
    expect(start_get(m, HD600, 'x' * 400) == PN['NOFEED'], 'a stamp too long for the record is refused')
    m = machine(site(), index=False, wifi=-1)
    expect(start_get(m, HD600) == PN['NOWIFI'] and st(m) == (E['FAILED'], PN['NOWIFI'], 1), 'a preset with the Wi-Fi off: the guard\'s code, in the state too')


KB = sibling('keyboard')


def kb_up(m): return KB.shown(m, 'kb_pad') == (1, 1)
def eq_files(m): return sorted(k.rsplit('/', 1)[1] for k in m.fs if k.startswith(EQ + '/'))
def requests(m): return [c[1] for c in m.calls if c[0] == 'curl_perform']


def list_tests(ctx):
    """The list on the card: downloaded when the page opens without it, retried after a failure, refreshed in the background when it is old."""
    expect = ctx.expect
    log = []
    m = opened(site(log=log), index=False)
    m = machine(site(log=log), index=False)
    m.call(PSYMS['autoeq_open'], count=400000000)
    expect(said(m) == 'Downloading List…' and vis_prop(m, 'label_status') == 1 and not kb_up(m) and [c for c in m.calls if c[0] == 'timer_add'], 'no list on the card: "Downloading List…", no keyboard (nothing to type into yet), the timer')
    expect(not log, 'nothing is asked for before the first tick (the page is shown first)')
    settle(m)
    expect([u for u, _ in log] == [BASE + 'INDEX.md'] and m.fs.get(IDX) == INDEX and vis_prop(m, 'label_status') == 0 and kb_up(m), 'the list comes: one request, the state line goes, the keyboard comes up')
    typed(m, 'hd 600')
    expect(len(all_rows(m)) == 13 and m.call(PSYMS['ae_tick'], a0=0, count=900000000) != RET_REPEAT, 'and the page searches it (13 results); the timer ended')
    # a failure: the word, the list shown for "Try Again", a tap asks again (and so does the action key)
    for what, resp, word in (('the Wi-Fi off', None, 'No Wi-Fi'), ('no network', {'rc': 6}, "Can't connect"), ('a time-out (the Wi-Fi lost)', {'rc': 28}, "Can't connect"), ('a certificate', {'rc': 60}, 'Certificate problem'),
                             ('HTTP 404', {'rc': 22, 'code': 404}, 'Server error'), ('a web page', {'body': b'<html></html>'}, 'Server error')):
        m = machine(site(index_over=resp or {}), index=False, wifi=-1 if resp is None else 4)
        m.call(PSYMS['autoeq_open'], count=400000000)
        n = settle(m)
        expect(said(m) == word and vis_prop(m, 'label_status') == 1 and vis_prop(m, 'se_listview') == 1 and not kb_up(m) and n < 10, f'{what}: "{word}", the page is not left on its progress state (the timer ended after {n} ticks)')
        texts, _, _ = paint(m)
        expect([t for t, _ in texts] == ['Try Again'] and 0 < texts[0][1][0] < 200, 'under it a grey "Try Again", centred')
        m.wifi, m.curl_site = 4, site()
        m.calls = []
        m.touch('down', 100, LIST_Y0 + 100, 1000, fn='ae_on_down', count=30000000); m.touch('up', 100, LIST_Y0 + 100, 1080, fn='ae_on_up', count=30000000)
        expect(said(m) == 'Downloading List…' and [c for c in m.calls if c[0] == 'timer_add'], 'a tap on the page asks again')
        settle(m)
        expect(m.fs.get(IDX) == INDEX and vis_prop(m, 'label_status') == 0 and kb_up(m) and vis_prop(m, 'se_listview') == 0, 'and the list comes this time')
    m = machine(site(index_over={'rc': 6}), index=False)
    m.call(PSYMS['autoeq_open'], count=400000000); settle(m)
    m.curl_site = site()
    m.call(PSYMS['ae_on_go'], count=900000000); settle(m)
    expect(m.fs.get(IDX) == INDEX and kb_up(m), 'the keyboard\'s action key asks again too')
    # another job holds the slot: the list waits for it, the page does not hang
    m = machine(site(), index=False)
    m.call(PSYMS['autoeq_open'], count=400000000)
    m.thread = None
    m.call(PSYMS['pn_eq_get'], a0=m.cstr(HD600), a1=m.cstr('# x'), count=1 << 30)
    held = m.thread
    m.thread = None
    m.call(PSYMS['ae_tick'], a0=0, count=900000000)
    expect(not m.thread and said(m) == 'Downloading List…', 'the slot busy: the list waits')
    m.thread = held; jobs(m)
    settle(m)
    expect(m.fs.get(IDX) == INDEX and kb_up(m), 'the other job ends, the list is asked for')
    # a list on the card: no request, no timer
    m = machine(site(log=(log := [])))
    m.call(PSYMS['autoeq_open'], count=400000000)
    expect(not log and not [c for c in m.calls if c[0] == 'timer_add'] and kb_up(m) and vis_prop(m, 'label_status') == 0, 'a recent list: offline works, no request, no timer, the keyboard up')
    # a list that is old: asked for again in the background; the old one serves meanwhile
    new = INDEX + line('Zzz Brand New').encode() + b'\n'
    for what, stamp, wall, again in (('30 days and a second', WALL - 30 * 86400 - 1, WALL, True), ('30 days', WALL - 30 * 86400, WALL, False), ('a day', WALL - 86400, WALL, False), ('no date', None, WALL, True),
                                     ('a date in the future', WALL + 5000, WALL, True), ('a clock never set', None, 1000, False)):
        log = []
        m = machine(site(index=new, log=log), stamp=stamp, wall=wall)
        m.call(PSYMS['autoeq_open'], count=400000000)
        expect(vis_prop(m, 'label_status') == 0 and kb_up(m), f'{what}: the page opens as it is, with the old list, the keyboard up')
        typed(m, 'hd 600')
        n = len(all_rows(m))
        typed(m, 'zzz')
        expect(bool(log) == again and (titles(m) == ['Zzz Brand New']) == again and n == 13, f'{what}: {"the list is downloaded again and used" if again else "no request"}')
        if again: expect(m.fs[IDX] == new and m.fs[STAMP] == f'{wall}\n'.encode(), 'the new list and its day are on the card')
    for resp in ({'rc': 6}, {'body': b'<html></html>'}):
        m = machine(site(index_over=resp), stamp=None)
        m.call(PSYMS['autoeq_open'], count=400000000); settle(m)
        typed(m, 'hd 600')
        expect(said(m) != 'Can\'t connect' and vis_prop(m, 'label_status') == 0 and kb_up(m) and m.fs[IDX] == INDEX and len(all_rows(m)) == 13, 'a refresh that fails is silent: the page, the old list and the keyboard are as they were')
    m = machine(site(), wifi=-1, stamp=None)
    m.call(PSYMS['autoeq_open'], count=400000000); settle(m)
    typed(m, 'hd 600')
    expect(vis_prop(m, 'label_status') == 0 and len(all_rows(m)) == 13, 'a refresh with the Wi-Fi off is silent too: offline works')
    # the list is gone from the card while the page is open: it is asked for again
    m = machine(site())
    m.call(PSYMS['autoeq_open'], count=400000000)
    del m.fs[IDX]
    typed(m, 'hd')
    expect(m.fs.get(IDX) == INDEX and len(all_rows(m)) > 5, 'a list that disappeared is downloaded again and the query answered')
    # a page already open: autoeq_open refuses
    m = machine(site())
    m.call(PSYMS['autoeq_open'], count=400000000)
    expect(m.call(PSYMS['autoeq_open'], count=400000000) == 0xffffffff, 'a second page is refused')


HD600_CRINACLE = 'crinacle/GRAS%2043AG-7%20over-ear/Sennheiser%20HD%20600'
PRESETS = {purl(p_): PRESET_TXT for p_ in (HD600, HD600_RTINGS, HD600_CRINACLE)}


def rows_tests(ctx):
    """A result: its states, the download and what is installed, the names, Tap to use."""
    expect = ctx.expect
    log = []
    m = opened(site(presets=PRESETS, log=log))
    typed(m, 'hd 600')
    r0 = all_rows(m)[0]
    expect(r0 == ('Sennheiser HD 600', 'oratory1990 · Over-ear'), 'a result that is not on the card: its name and where it is from')
    _, blits, _ = paint(m)
    expect(not [b for b in blits if b[2][2] == 44] and len([b for b in blits if b[2][2] == 22]) == 7 and {b[0] for b in blits if b[2][2] == 22} and len({b[0] for b in blits if b[2][2] == 22}) == 1,
           'no row has a tile, every one the download glyph (22 px, one bitmap for them all)')
    tap_row(m, 0)
    expect(all_rows(m)[0] == ('Sennheiser HD 600', 'Downloading…') and not log, 'a tap: the row says "Downloading…" at once (the worker has not run)')
    texts, blits, _ = paint(m)
    ring = [b for b in blits if b[2][2] == 22 and b[2][1] < ROW]
    expect(len(ring) == 1, 'and shows the ring instead of the download glyph')
    settle(m)
    expect([u for u, _ in log] == [purl(HD600)] and eq_files(m) == ['Sennheiser HD 600.txt'] and PRESET not in m.fs, f'the file of the project is asked for, and /mnt/mmc/EQ holds "Sennheiser HD 600.txt", no part file ({eq_files(m)})')
    f = m.fs[EQ + '/Sennheiser HD 600.txt']
    expect(f == b'# AutoEq: ' + HD600.encode() + b'\n' + PRESET_TXT, 'its first line is the stamp (the result\'s path in the index), then the file as the project has it')
    expect(all_rows(m)[0] == ('Sennheiser HD 600', 'In use') and [c for c in m.calls if c[0] == 'toast'] == [], 'the row: "In use" (the download plays at once), no message box')
    expect(PEQ.NAME_OF(m.fs[STATE]) == b'Sennheiser HD 600.txt' and struct.unpack_from('<i', m.fs[STATE], 8)[0] == 1, 'the state record holds the downloaded preset as the playing file')
    _, blits, _ = paint(m)
    expect(len({b[0] for b in blits if b[2][2] == 22 and b[2][1] < ROW}) == 1 and ring[0][0] != [b for b in blits if b[2][2] == 22 and b[2][1] < ROW][0][0], 'the check replaces the ring')
    # the same headphone from another source: its own name; a second file of the same name from the same source and a user\'s own file
    tap_row(m, 5); settle(m)
    expect(eq_files(m) == ['Sennheiser HD 600 (Rtings).txt', 'Sennheiser HD 600.txt'] and all_rows(m)[5][1] == 'In use' and all_rows(m)[0][1] == 'Saved to EQ · Tap to use', f'the name is taken by another source\'s file: "Sennheiser HD 600 (Rtings).txt", which plays ({eq_files(m)})')
    tap_row(m, 1); settle(m)
    expect('Sennheiser HD 600 (crinacle).txt' in eq_files(m), 'and the third: "(crinacle)"')
    # the page remembers by the stamp: a new search shows them saved, the others not
    typed(m, 'hd 650'); typed(m, 'hd 600')
    want = ['Saved to EQ · Tap to use', 'In use', 'Super Review · Over-ear', 'Auriculares Argentina · Over-ear', 'Filk · Over-ear', 'Saved to EQ · Tap to use']   # the crinacle one came last: it plays
    expect(all(same(g[1], w) for g, w in zip(all_rows(m), want)), f'a new search finds the saved ones by their stamp ({[r[1] for r in all_rows(m)][:6]})')
    expect(len(log) == 3 and [u for u, _ in log].count(purl(HD600)) == 1, f'and asked for nothing again ({len(log)} requests)')
    # Tap to use: peq_select, as a tap on the Equalizer page\'s row does
    m.calls = []
    tap_row(m, 0)
    rec = m.fs.get(STATE, b'')
    seq = [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
    expect(len(rec) == PEQ.STATE_SIZE and struct.unpack_from('<i', rec, 8)[0] == 1 and PEQ.NAME_OF(rec) == b'Sennheiser HD 600.txt', 'a tap on a saved result: the state record holds PEQ_FILE and the file\'s name')
    expect(seq == [('set_equalizer_value', 4, 1)], f'the Equalizer went on with the download: the player told again ({seq})')
    rows = all_rows(m)
    expect(rows[0][1] == 'In use' and rows[1][1] == 'Saved to EQ · Tap to use' and rows[5][1] == 'Saved to EQ · Tap to use', 'the row that plays says "In use", the others stay saved')
    m.calls = []
    tap_row(m, 5)
    seq = [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
    rec = m.fs[STATE]
    expect(seq == [('set_equalizer_value', 4, 1)] and PEQ.NAME_OF(rec) == b'Sennheiser HD 600 (Rtings).txt' and all_rows(m)[5][1] == 'In use' and all_rows(m)[0][1] == 'Saved to EQ · Tap to use',
           'another: only the gains sent again; the mark moves')
    expect(PEQ.unpack_preset(rec[16:16 + 992])['count'] == 4 and abs(PEQ.unpack_preset(rec[16:16 + 992])['preamp'] + 6.2) < 1e-9, 'the record holds the preset parsed from the file (the stamp line is a comment)')
    # a file that went bad on the card: the message box, nothing changes
    m.fs[EQ + '/Sennheiser HD 600.txt'] = b'# AutoEq: ' + HD600.encode() + b'\nnot a preset\n'
    m.calls = []
    tap_row(m, 0)
    expect(toasts(m) == ['Cannot read this preset'] and m.fs[STATE] == rec and not [c for c in m.calls if c[0] == 'set_equalizer_value'], 'a saved file that no longer parses: "Cannot read this preset", the record as it was')
    # back in front: the record may have changed on the Equalizer page
    m.fs[STATE] = PEQ.pack_state(0, PEQ.pack_preset([]))
    fn_, c_ = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn_, a0=c_, count=900000000)
    expect(all_rows(m)[5][1] == 'Saved to EQ · Tap to use', 'back in front: "In use" is read again from the record')
    # a Save over the download marks it edited: the page no longer finds it saved, a tap downloads the original to the next free name and leaves the edited file alone
    edited = b'# AutoEq edited: ' + HD600.encode() + b'\nPreamp: -1 dB\n' + PRESET_TXT
    m.fs[EQ + '/Sennheiser HD 600.txt'] = edited
    typed(m, 'hd 650'); typed(m, 'hd 600')
    expect(all_rows(m)[0][1] != 'Saved to EQ · Tap to use' and all_rows(m)[0][1] != 'In use', f'an edited file is not the saved result ({all_rows(m)[0][1]})')
    before = set(eq_files(m))
    tap_row(m, 0); settle(m)
    new = sorted(set(eq_files(m)) - before)
    expect(len(new) == 1 and new[0].startswith('Sennheiser HD 600 (') and m.fs[EQ + '/Sennheiser HD 600.txt'] == edited and m.fs[EQ + '/' + new[0]] == b'# AutoEq: ' + HD600.encode() + b'\n' + PRESET_TXT,
           f'the original is saved under the next free name ({new}); the edited file is untouched')
    # a gap: the downloaded copy sits past a free name, the page still finds it by its stamp (every variant is looked at, not only up to the first free one)
    stamped = b'# AutoEq: ' + HD600.encode() + b'\n' + PRESET_TXT
    for n in new: del m.fs[EQ + '/' + n]
    far = EQ + '/Sennheiser HD 600 (oratory1990 3).txt'
    m.fs[far] = stamped
    typed(m, 'hd 650'); typed(m, 'hd 600')
    expect(all_rows(m)[0][1] in ('Saved to EQ · Tap to use', 'In use'), f'a stamped copy past a free variant name is the saved result ({all_rows(m)[0][1]})')
    before = set(eq_files(m)); m.calls = []
    tap_row(m, 0); settle(m)
    expect(set(eq_files(m)) == before and not requests(m), 'a tap uses that file, nothing is downloaded again')


def names_tests(ctx):
    expect = ctx.expect
    lines = [line('Foo'), line('Foo', src='Rtings', tgt='HMS II.3'), line('Foo', src='Rtings', tgt='GRAS RA0045'), line('Foo', src='Rtings', tgt='711'), line('A/B: C*?"<>|', src='x'), line('.Hidden'), line('Bar.  '),
             line('a' * 58 + 'é' * 3, src='x'), line('X' * 70, src='Super Review')]
    pre = {purl(l.split('](./')[1].split(') by ')[0]): PRESET_TXT for l in lines}
    m = opened(site(presets=pre), index=synth(lines))
    typed(m, 'foo')
    for r in range(4): tap_row(m, r); settle(m)
    expect(eq_files(m) == ['Foo (Rtings 2).txt', 'Foo (Rtings 3).txt', 'Foo (Rtings).txt', 'Foo.txt'], f'the same name from one source: "(Rtings)", "(Rtings 2)", "(Rtings 3)" ({eq_files(m)})')
    typed(m, 'foo')
    expect([r[1] for r in all_rows(m)] == ['Saved to EQ · Tap to use'] * 3 + ['In use'], 'each is found again by its stamp; the last one downloaded plays')
    expect(m.fs[EQ + '/Foo (Rtings).txt'].split(b'\n')[0].endswith(b'Rtings/HMS%20II.3%20over-ear/Foo') and m.fs[EQ + '/Foo (Rtings 2).txt'].split(b'\n')[0].endswith(b'GRAS%20RA0045%20over-ear/Foo')
           and m.fs[EQ + '/Foo (Rtings 3).txt'].split(b'\n')[0].endswith(b'Rtings/711%20over-ear/Foo'), 'the stamps keep the entries apart')
    for q in ('a/b', 'hidden', 'bar', 'aaaaa', 'xxx'):
        typed(m, q); tap_row(m, 0); settle(m)
    names = [n for n in eq_files(m) if not n.startswith('Foo')]
    expect(all(len(n.encode()) < 64 and n.endswith('.txt') and not n.startswith('.') and not any(c in n for c in '/\\:*?"<>|') for n in names) and len(names) == 5, f'FAT-safe names under 64 bytes, no leading dot ({names})')
    expect('A-B- C------.txt' in names and '_Hidden.txt' in names and 'Bar.txt' in names, f'forbidden characters become "-", a leading dot "_", trailing dots and spaces go ({names})')
    long_ = [n for n in names if n.startswith('X')][0]
    acc = [n for n in names if n.startswith('aaa')][0]
    expect(long_ == 'X' * 59 + '.txt' and acc == 'a' * 58 + '.txt', f'a long name is cut to fit (59 bytes and ".txt"; {long_}, {acc}); a character is never cut in two (the 59th byte is the first of an "é")')
    typed(m, 'xxx')
    expect(all_rows(m)[0][1] == 'In use', 'the cut name is found again by its stamp (it was the last downloaded, so it plays)')
    # a name taken nine times over (other people\'s files): nothing is asked for, the message box
    m = opened(site(presets=pre), index=synth([line('Foo')]))
    names9 = ['Foo.txt'] + ['Foo (oratory1990).txt'] + [f'Foo (oratory1990 {k}).txt' for k in range(2, 9)]
    for n in names9: m.put(f'{EQ}/{n}', b'Filter: ON PK Fc 100 Hz Gain 1 dB Q 1\n')
    typed(m, 'foo')
    m.calls = []
    tap_row(m, 0)
    expect(toasts(m) == ['Storage unavailable'] and not m.thread and all_rows(m)[0][1] == 'oratory1990 · Over-ear', 'nine files of that name that are not this result\'s: no request, "Storage unavailable"')
    # a user's file of the plain name that has no stamp is not overwritten
    m = opened(site(presets=pre), index=synth([line('Foo')]))
    m.put(f'{EQ}/Foo.txt', b'Filter: ON PK Fc 100 Hz Gain 1 dB Q 1\n')
    typed(m, 'foo'); tap_row(m, 0); settle(m)
    expect(m.fs[f'{EQ}/Foo.txt'] == b'Filter: ON PK Fc 100 Hz Gain 1 dB Q 1\n' and f'{EQ}/Foo (oratory1990).txt' in m.fs, 'a file of that name that the user made is kept: the download is "Foo (oratory1990).txt"')
    # no EQ folder yet: made with the first preset
    m = opened(site(presets=pre), index=synth([line('Foo')]))
    m.dirs.discard(EQ); m.present.discard(EQ)
    typed(m, 'foo'); tap_row(m, 0); settle(m)
    expect(f'{EQ}/Foo.txt' in m.fs, 'the card has no EQ folder: it is made and the file is in it')


def fail_tests(ctx):
    expect = ctx.expect
    for what, resp, word in (('no network', {'rc': 6}, "Can't connect"), ('a time-out (the Wi-Fi lost mid request)', {'rc': 28}, "Can't connect"), ('a certificate', {'rc': 60}, 'Certificate problem'),
                             ('HTTP 404', {'rc': 22, 'code': 404}, 'Server error'), ('an empty file', {'body': b''}, 'Server error')):
        m = opened(site(presets={purl(HD600): resp}))
        typed(m, 'hd 600'); tap_row(m, 0)
        n = settle(m)
        expect(toasts(m) == [word] and eq_files(m) == [] and PRESET not in m.fs and all_rows(m)[0][1] == 'oratory1990 · Over-ear' and n < 10, f'{what}: the message box says "{word}", nothing is saved, the row is as it was, the timer ended ({n} ticks)')
        m.curl_site = site(presets=PRESETS)
        tap_row(m, 0); settle(m)
        expect(eq_files(m) == ['Sennheiser HD 600.txt'], 'and the row can be tried again')
    m = opened(site(presets=PRESETS), wifi=-1)
    typed(m, 'hd 600'); m.calls = []; tap_row(m, 0)
    expect(toasts(m) == [] and all_rows(m)[0][1] == 'Downloading…', 'the Wi-Fi off: the tap is taken, the guard says so on the next tick')
    settle(m)
    expect(toasts(m) == ['No Wi-Fi'] and all_rows(m)[0][1] == 'oratory1990 · Over-ear', 'and then the message box, the row as it was')
    m = opened(site(presets=PRESETS))
    typed(m, 'hd 600'); m.wifi = -1; tap_row(m, 0); m.calls = []
    settle(m)
    expect(toasts(m) == ['No Wi-Fi'] and all_rows(m)[0][1] == 'oratory1990 · Over-ear' and eq_files(m) == [], 'no Wi-Fi: "No Wi-Fi", the row as it was, not stuck on its progress')
    # the bytes of a file that does not parse, or has nothing for the engine, are never installed
    for what, body in (('text', b'hello\n'), ('a file of filters the engine has not', b'Filter 1: ON LP Fc 12000 Hz\nFilter 2: ON HP Fc 20 Hz\n'), ('a range error', b'Filter: ON PK Fc 30000 Hz Gain 3 dB Q 1\n'),
                       ('only OFF filters', b'Filter: OFF PK Fc 100 Hz Gain 3 dB Q 1\n')):
        m = opened(site(presets={purl(HD600): body}))
        typed(m, 'hd 600'); tap_row(m, 0); settle(m)
        expect(toasts(m) == ['Cannot read this preset'] and eq_files(m) == [] and PRESET not in m.fs and all_rows(m)[0][1] == 'oratory1990 · Over-ear', f'{what}: "Cannot read this preset", no file in EQ, no part file, the row as it was')
    m = opened(site(presets={purl(HD600): b'Preamp: -3 dB\nDevice: x\nFilter 1: ON PK Fc 100 Hz Gain 2 dB Q 1\nFilter 2: ON LP Fc 12000 Hz\n'}))
    typed(m, 'hd 600'); tap_row(m, 0); settle(m)
    expect(eq_files(m) == ['Sennheiser HD 600.txt'] and toasts(m) == [], 'a file with a line the engine skips and a band it has is accepted (the lenient parser)')
    # storage
    m = opened(site(presets=PRESETS))
    typed(m, 'hd 600'); m.fail.add(('rename', EQ + '/Sennheiser HD 600.txt')); tap_row(m, 0); settle(m)
    expect(toasts(m) == ['Storage unavailable'] and eq_files(m) == [] and PRESET not in m.fs and all_rows(m)[0][1] == 'oratory1990 · Over-ear', 'a rename into the EQ folder that fails: "Storage unavailable", the part file removed')
    # another job holds the slot: the row waits, shows its progress, and the job starts when the slot frees
    m = opened(site(presets=PRESETS))
    typed(m, 'hd 600')
    m.thread = None
    m.call(PSYMS['pn_eq_index'], count=1 << 30)
    held = m.thread; m.thread = None
    tap_row(m, 0)
    m.call(PSYMS['ae_tick'], a0=0, count=900000000)
    expect(not m.thread and all_rows(m)[0][1] == 'Downloading…', 'the slot busy: the row says "Downloading…" and waits')
    m.thread = held; jobs(m)
    settle(m)
    expect(eq_files(m) == ['Sennheiser HD 600.txt'], 'the other job ends: the row\'s job runs and its file is installed')
    # one at a time: a second tap while a row downloads does nothing; a tap on the busy row neither
    log = []
    m = opened(site(presets=PRESETS, log=log))
    typed(m, 'hd 600'); tap_row(m, 0); tap_row(m, 0); tap_row(m, 5)
    settle(m)
    expect(eq_files(m) == ['Sennheiser HD 600.txt'] and [u for u, _ in log] == [purl(HD600)], 'a second tap while the first downloads (and a tap on the same row) asks for nothing')
    # the query changes while a download runs: the row is found again by its path, and the file still lands
    m = opened(site(presets=PRESETS))
    typed(m, 'hd 600'); tap_row(m, 0)
    typed(m, 'sennheiser hd 600')
    settle(m)
    expect(eq_files(m) == ['Sennheiser HD 600.txt'] and all_rows(m)[0][1] == 'In use', 'the field changed while the file came: it is installed, plays, and the row says so')
    # destroy while a job runs: cancelled, the timer and bitmaps gone, nothing left behind
    m = opened(site(presets={purl(HD600): {'body': PRESET_TXT, 'xfer': lambda u, sent, total: None}}))
    typed(m, 'hd 600'); tap_row(m, 0)
    m.call(PSYMS['ae_tick'], a0=0, count=900000000)   # the worker is started (the test runs it later)
    m.calls = []
    fn_, c_ = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn_, a0=c_, count=900000000)
    expect(any(c[0] == 'timer_remove' for c in m.calls), 'the page\'s destroy removes its timer')
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_destroy') == 3 and not m.bitmaps, 'its three bitmaps go')
    th = m.thread; m.thread = None
    PCN.work(m, th)
    expect(eq_files(m) == [] and PRESET not in m.fs and st(m)[:2] == (E['FAILED'], PN['CANCELLED']), 'the running worker was asked to stop: it ends cancelled and leaves nothing in EQ')
    expect(m.call(PSYMS['autoeq_open'], count=400000000) == 0 and all_rows(m) == [], 'a new page opens fresh')
    # a download waiting for the Podcasts' downloads to pause (pn_dl_*): not simulated here (the slot rule above is the same code)


def bitmap(m, w):
    """The pixels of the n-th bitmap of a size the payload made, as rows of (alpha, grey)."""
    got = [(d, bw, bh) for d, bw, bh in m.bitmaps.values() if bw == w]
    return got


def px(m, data, w, x, y):
    v = struct.unpack('<I', bytes(m.u.mem_read(data + 4 * (y * w + x), 4)))[0]
    return v >> 24, v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff


def glyph_tests(ctx):
    expect = ctx.expect
    m = opened(site())
    small = bitmap(m, 22)
    expect(len(small) == 3 and not bitmap(m, 44), "three bitmaps: the download glyph, the check and the ring, and no tile")
    d, c, r = (b[0] for b in small)
    expect(px(m, d, 22, 11, 8)[0] > 230 and px(m, d, 22, 11, 19)[0] > 200 and px(m, d, 22, 1, 1)[0] == 0 and px(m, d, 22, 20, 1)[0] == 0, 'the download glyph: the arrow\'s shaft and the tray, empty corners')
    expect(px(m, d, 22, 11, 8)[1:] == (0xaa, 0xaa, 0xaa), 'in the neutral grey of the list\'s secondary controls')
    expect(px(m, c, 22, 13, 10)[0] > 200 and px(m, c, 22, 6, 13)[0] > 200 and px(m, c, 22, 1, 1)[0] == 0 and px(m, c, 22, 20, 20)[0] == 0 and px(m, c, 22, 11, 10)[1:] == (255, 255, 255), 'the check: both strokes, white')
    ring0 = [px(m, r, 22, x, y)[0] for x, y in ((11, 2), (2, 11), (5, 17), (17, 5), (16, 16), (11, 11))]
    expect(ring0[:4] == [255] * 4 and ring0[4] in range(60, 80) and ring0[5] == 0,
           f'the ring: a track (alpha 70) all round and the arc on it, a quarter turn open at the lower right in its first frame, hollow ({ring0})')
    # the ring turns: a tap starts it, each three ticks a frame; the quarter that is open moves a step (45 degrees)
    typed(m, 'hd 600'); tap_row(m, 0)
    gaps = []
    for _ in range(8):
        for _ in range(3): m.call(PSYMS['ae_tick'], a0=0, count=900000000)
        gaps.append(tuple(px(m, r, 22, x, y)[0] for x, y in ((17, 17), (5, 17), (5, 5), (17, 5))))
    expect(len(set(gaps)) >= 3, f'the ring turns, a frame every three ticks: the open quarter moves ({len(set(gaps))} different frames of 8)')
    m.thread = None
    expect(m.call(PSYMS['ae_tick'], a0=0, count=900000000) == RET_REPEAT, 'the timer runs while a job does')


def ui_tests(ctx):
    expect = ctx.expect
    m = opened(site(presets=PRESETS))
    texts, _, _ = paint(m)
    LY = AE_LIST_Y; LH = S.D['SE_LIST_H'] + S.D['SE_LIST_Y'] - LY
    pr = lambda w, k: m.props.get((w, k))
    expect((pr(m.widgets['se_listview'], 'y'), pr(m.widgets['se_listview'], 'h'), pr(m.sv, 'h')) == (LY, LH, LH) and LY + LH == 450,
           f'the list sits under the bar, its rows from Radio\'s 48 below it: y {LY}, {LH} high')
    expect((m.widgets['btn_backtoplayer'], O['EVT_CLICK']) in m.bound, 'Now Playing\'s disc is bound')
    # touch: the pressed row is lit, a drag is not a tap, the gaps and air are dead, the keyboard goes with the scroll and comes back with the field
    typed(m, 'hd 600')
    m.touch('down', 100, LIST_Y0 + 90, 1000, fn='ae_on_down', count=30000000)
    _, _, fills = paint(m)
    expect(any(f[0] == O["LIST_PRESS"] and f[2] == ROW for f in fills), 'a press lights the row under the finger')
    m.touch('up', 100, LIST_Y0 + 90 + 20, 1080, fn='ae_on_up', count=30000000)
    expect(eq_files(m) == [] and not m.thread, 'a drag (the finger moved 20 px) is not a tap')
    m.touch('down', 100, LIST_Y0 + 20 * ROW + 10, 1000, fn='ae_on_down', count=30000000); m.touch('up', 100, LIST_Y0 + 20 * ROW + 10, 1080, fn='ae_on_up', count=30000000)
    expect(eq_files(m) == [] and not m.thread, 'air under the rows does nothing')
    expect(kb_up(m), 'the keyboard is up')
    m.call(PSYMS['ae_on_go'], count=900000000)
    expect(not kb_up(m), 'the action key puts it away')
    fn_, c_ = m.bound[(m.widgets['kb_field'], O['EVT_POINTER_UP'])]
    e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e, O['EVT_POINTER_UP'])
    m.call(fn_, a0=c_, a1=e, count=900000000)
    expect(kb_up(m), 'a tap on the field brings it back')
    m.touch('down', 100, LIST_Y0 + 30, 1000, fn='ae_on_down', count=30000000)
    fn_, c_ = m.bound[(m.view, O['EVT_POINTER_ABORT'])]
    m.call(fn_, a0=c_, a1=0, count=900000000)
    expect(not kb_up(m) and not eq_files(m), 'the list taking the gesture as a scroll puts the keyboard away and acts on nothing')
    # the page goes behind another: the press is let go
    m.touch('down', 100, LIST_Y0 + 30, 1000, fn='ae_on_down', count=30000000)
    fn_, c_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]
    m.call(fn_, a0=c_, count=900000000)
    m.touch('up', 100, LIST_Y0 + 30, 1080, fn='ae_on_up', count=30000000)
    expect(not m.thread and eq_files(m) == [], 'a press let go by the page going behind another does not tap')
    # the glass Back (Radio's search level's) is what the round X was: it closes the page
    expect((m.widgets['btn_return'], O['EVT_CLICK']) in m.bound, 'Back is bound')

    # another language: the rows and the state line are translated; a failure\'s hint too
    m = machine(site(presets=PRESETS), index=False, wifi=-1)
    m.set_language('ge_DE')
    m.call(PSYMS['autoeq_open'], count=400000000)
    expect(said(m) == 'Liste wird geladen…', f'German: the state line ({said(m)})')
    settle(m)
    expect(said(m) == 'Kein WLAN' and [t for t, _ in paint(m)[0]] == ['Wiederholen'], 'a failure and its hint in German')
    m = machine(site(presets=PRESETS))
    m.set_language('ge_DE')
    m.call(PSYMS['autoeq_open'], count=400000000)
    typed(m, 'hd 600'); tap_row(m, 0); settle(m)
    expect(all_rows(m)[0] == ('Sennheiser HD 600', 'In Gebrauch') and all_rows(m)[1][1].startswith('crinacle · Over-Ear'), f'German: the saved row and the kind ({all_rows(m)[:2]})')
    tap_row(m, 0)
    expect(all_rows(m)[0][1] == 'In Gebrauch', 'German: "In Gebrauch"')


def perf_tests(ctx):
    if not PERF: return
    lines = []
    for i in range(8850):
        src = ('crinacle', 'Innerfidelity', 'Super Review', 'Rtings', 'oratory1990', 'ToneDeafMonk')[i % 6]
        lines.append(line(f'Brand{i // 20} Model {i} Pro', src=src, tgt='GRAS 43AG-7' if i % 3 == 0 else ''))
    body = synth(lines)
    for q, what in (('model 1', 'a short query that matches hundreds'), ('zzzz', 'a query nothing matches'), ('brand4 model 8', 'two words')):
        m = opened(site(), index=body)
        m.count()
        m.call(PSYMS['ae_on_text'], a0=m.cstr(q), count=2000000)
        n = 0
        while m.call(PSYMS['ae_tick'], a0=0, count=900000000) == RET_REPEAT and n < 60: n += 1
        cost = m.icount
        print(f'PERF autoeq {what} ({len(body) // 1000} KB, {len(lines)} lines): {cost / 1e6:.1f} M instructions')
        ctx.expect(cost < 160e6, f'{what}: one scan of the whole list stays under 160 M instructions ({cost / 1e6:.1f} M)')


SECTIONS = [parse_tests, search_tests, search2_tests, net_tests, list_tests, rows_tests, names_tests, fail_tests, glyph_tests, ui_tests, perf_tests]

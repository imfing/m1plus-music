"""Search inside one show (patch/pcfind.c, docs/modules/podcasts.md "Search inside a show"): the Show page's search button, the title matcher (patch/search.c search_titles_*: terms, case, the whole-number
rule for digits, Chinese initials), the results' rows, the tap on a result (the episode page opens on the Show page, Back opens the search again with its text and scroll), the play queue in the show's
order, and the page's asset. The compiled payload runs under Unicorn against the Podcasts page's machine (test/pod/pcshow.py) with the new page's widgets added."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

PSH = sibling('pcshow')
PCP = PSH.PCP
PCD = sibling('pcdetail')
S = sibling('search')
SEL = sibling('pcsel')
ASSET = os.path.join(S.RAW, 'ui', 'm1plus_pcfind.bin')
ROW, LIST_H, LIST_Y = 60, 398, 52
LIST_Y0 = 30 + LIST_Y
KB_H = 180


def flags(m, n): return m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1)
def icon(m, n): return m.props.get((m.widgets[n], 'style:normal:icon'))
def moves(m, n): return [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[n]]


def titles_of(texts):
    return [f'Ep {i}' for i in texts]


def show(titles, **kw):
    """The Show page of a show whose episodes carry these titles (in the show's order, newest first), all on the card."""
    es = [PSH.entry(i, t=t) for i, t in enumerate(titles)]
    m = PSH.machine(entries=es, files=range(len(es)), **kw)
    PSH.open_show(m)
    return m


def find_widgets(m):
    """The search page's widgets (pf_*, the keyboard's) on machine m, the list's widget chain, and the window m1plus_pcfind opens; the Show page's own list is kept in m.psv / m.pview."""
    sibling('keyboard').keyboard_machine(m)
    m.psv, m.pview = m.sv, m.view
    m.list_h = m.props[(m.sv, 'virtual_h')]   # (the Show page's list; PCD.is_page compares with it)
    for w in awtk_ui.parse(open(ASSET, 'rb').read()).walk():
        if not w.name: continue
        h = m.widget(w.name)
        m.px[h] = int(w.get('style:normal:font_size') or 18)
        if w.name not in ('kb_pad', 'kb_strip', 'kb_cands', 'pf_scrollview'): m.rect(h, w.x, w.y, w.w, w.h)
        m.props[(h, 'visible')] = 0 if w.get('visible') == 'false' else 1
        m.props[(h, 'sensitive')] = 0 if w.get('sensitive') == 'false' else 1
    win, lv, sv, view = m.alloc(0x80), m.widgets['pf_listview'], m.alloc(0x180), m.widgets['pf_view']
    for w in (lv, view): m.u.mem_write(w, bytes(0x80))
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, LIST_Y, LIST_H, win), (sv, 0, LIST_H, lv), (view, 0, LIST_H, sv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['pf_scrollview'] = sv
    m.live_scroll = frozenset(m.live_scroll) | {sv}
    m.fsv, m.fview = sv, view
    m.windows['m1plus_pcfind'] = 0x20003000
    return m


def click_find(m):
    m.calls = []
    PCP.click(m, 'btn_search')
    return m


def typed(m, text):
    m.call(PSYMS['pf_on_text'], a0=m.cstr(text), count=400000000)


def fpaint(m, off=0):
    m.setword(m.fsv + O['SC_YOFF'], off); m.props[(m.fsv, 'yoffset')] = off
    ev = m.paint_event()
    m.setword(m.canvas + O['CANVAS_OY'], (LIST_Y0 - off) & 0xffffffff)
    m.texts.clear(); m.text_styles.clear(); m.fills.clear(); m.blits.clear()
    fn, ctx = m.bound[(m.fview, O['EVT_AFTER_PAINT'])]
    m.call(fn, a0=ctx, a1=ev, count=400000000)
    return list(zip(m.texts, m.text_styles))


def is_more(t): return t == 'Search All Episodes' or t.startswith('Loading…') or t.endswith('Tap to Retry')


def rows(m, n=30, more=False):
    """The results: [(title, grey line, title style)] row by row (the list scrolled a screen at a time); the Search All Episodes row at the end (whatever it reads) only with more=True."""
    out = {}
    for off in range(0, ROW * n, 300):
        for (t, r), s in fpaint(m, off):
            row, y = divmod(r[1] + off, ROW)
            d = out.setdefault(row, {})
            if s in ('label_row_title', 'label_row_dim'): d['t'], d['s'] = t, s
            else: d['g'] = t
    m.setword(m.fsv + O['SC_YOFF'], 0); m.props[(m.fsv, 'yoffset')] = 0
    return [(d.get('t'), d.get('g'), d.get('s')) for _, d in sorted(out.items()) if more or not is_more(d.get('t') or '')]


def found(m, q): typed(m, q); return [t for t, _, _ in rows(m)]


def tap_row(m, r, off=0):
    y = LIST_Y0 + r * ROW + ROW // 2 - off
    m.setword(m.fsv + O['SC_YOFF'], off); m.setword(m.fview + 4, -off & 0xffffffff)
    m.touch('down', 100, y, 1000, fn='pf_on_down', count=30000000)
    m.touch('up', 100, y, 1080, fn='pf_on_up', count=80000000)


def nav_tests(ctx):
    """The Show page's magnifier: [Search | ... | Now Playing] on a subscribed show and a show of copied files; not on the Shows level, the Discover level's own place, a preview, the episode page or select mode."""
    expect = ctx.expect
    X, W = O['NAV_VIEW_X'], O['NAV_VIEW_W']
    m = show([f'Ep {i}' for i in range(12)])
    m.calls = []
    PCP.click(m, 'btn_return'); PCP.click(m, 'btn_return')
    expect(flags(m, 'btn_search') == (0, 0), 'the Shows level: no magnifier (the globe is the Apple search)')
    m = show([f'Ep {i}' for i in range(12)])
    expect(flags(m, 'btn_search') == (1, 1) and flags(m, 'btn_more') == (1, 1) and icon(m, 'btn_more') == 'pod_nav_moremid' and flags(m, 'btn_globe') == (0, 0), 'a subscribed show: the magnifier shows and the "..." is the middle piece')
    expect(moves(m, 'btn_search') and moves(m, 'btn_search')[-1][0] == X - W, 'the magnifier is 46 px left of the "..." (right-aligned to Now Playing as the Shows level\'s globe)')
    expect(m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play', 'Now Playing is the capsule\'s right cap')
    m2 = PSH.machine(feed=False)
    PSH.open_show(m2)
    expect(flags(m2, 'btn_search') == (1, 1), 'a show of copied files (no feed): the magnifier shows')
    SEL.start_select(m)
    expect(flags(m, 'btn_search') == (0, 0) and flags(m, 'btn_more') == (0, 0), 'select mode: hidden as the other pieces are')
    m = show([f'Ep {i}' for i in range(12)])
    PCP.tap(m, 150, PCP.hdr(m) + 12)
    expect(flags(m, 'btn_search') == (0, 0), 'the episode page: hidden')
    PCP.click(m, 'btn_return')
    expect(flags(m, 'btn_search') == (1, 1) and flags(m, 'btn_more') == (1, 1), 'and back on the list the magnifier is back')
    expect(len([t for t in ('pf_listview', 'pf_close') if t]) == 2 and os.path.exists(ASSET), 'the page\'s asset is built')


def match_tests(ctx):
    """The matcher: terms, case, whole numbers, Chinese initials, order."""
    expect = ctx.expect
    TITLES = ['Ep 37: Tariffs', 'ep 137', 'Episode 2037', '#37 Rates', 'EP037 reprise', 'Ep 370', '第37集', 'Ep 3.7', 'Interview with Jay', 'Interview 12 with Amy', 'Ep 0', 'Ep 00', 'Part 3 7']
    m = S.page_machine(pinyin=S.PINYIN)
    assert m.call(PSYMS['search_titles_open'], count=2000000) == 0
    m.call(PSYMS['search_titles_hold'], count=40000000)
    def q(text, titles=TITLES):
        m.call(PSYMS['search_titles_query'], a0=m.cstr(text), count=2000000)
        return [t for t in titles if m.call(PSYMS['search_titles_match'], a0=m.cstr(t), count=2000000)]
    expect(q('37') == ['Ep 37: Tariffs', '#37 Rates', 'EP037 reprise', '第37集'], f'37 is a whole number: Ep 37, #37, EP037 (leading zeros) and 第37集, not 137, 2037, 370 ({q("37")})')
    expect(q('137') == ['ep 137'] and q('2037') == ['Episode 2037'] and q('370') == ['Ep 370'] and q('3') == ['Ep 3.7', 'Part 3 7'], f'the others by their own number; 3 is the 3 of 3.7 and of "Part 3 7" ({q("3")})')
    expect(q('037') == q('37') and q('0') == ['Ep 0', 'Ep 00'] and q('00') == ['Ep 0', 'Ep 00'], 'leading zeros in the term count the same; zero is zero')
    expect(q('ep 37') == ['Ep 37: Tariffs', 'EP037 reprise'] and q('37 ep') == q('ep 37'), 'every term must match, in any order: a word and a number')
    expect(q('INTERVIEW amy') == ['Interview 12 with Amy'] and q('interview 12') == ['Interview 12 with Amy'] and q('interview 1') == [], 'case-insensitive substrings; a digit term is a whole number even beside words')
    expect(q('terview') == ['Interview with Jay', 'Interview 12 with Amy'] and q('xyz') == [] and q('   ') == [], 'a substring anywhere; no match and a blank query match nothing')
    zh = ['周杰伦 访谈', '晴天 第12期', '银行 与 行走', 'Jay Chou Mix', '歌 大']
    expect(q('zjl', zh) == ['周杰伦 访谈'] and q('qt', zh) == ['晴天 第12期'] and q('yh', zh) == ['银行 与 行走'] and q('周杰伦', zh) == ['周杰伦 访谈'], 'Chinese titles match by pinyin initials as the library search does (a polyphone by any reading), and by their characters')
    expect(q('12', zh) == ['晴天 第12期'] and q('1', zh) == [], 'a number inside a Chinese title is a whole number too')
    expect(q('zjl 访谈', ['周杰伦 访谈']) == ['周杰伦 访谈'] and q('zhou', zh) == [], 'a term of initials and one of letters: the initials key serves both; a syllable is not initials')
    m.call(PSYMS['search_titles_close'], count=2000000)


def flow_tests(ctx):
    """Open, type, the rows, a tap, Back, Back; the queue; the keyboard."""
    expect = ctx.expect
    T = [f'Ep {i}: {w}' for i, w in enumerate(['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine'])] + [f'Special {i}' for i in range(30)]
    m = find_widgets(show(T))
    click_find(m)
    expect(('window_open', 'm1plus_pcfind') in m.calls, 'a tap on the magnifier opens the search page')
    expect(rows(m) == [] and flags(m, 'pf_status') == (0, 0) and m.props.get((m.widgets['pf_listview'], 'visible')) == 0, 'an empty field: no rows, no hint (no recent searches)')
    expect(found(m, 'zzzz') == [] and flags(m, 'pf_status') == (1, 1) and m.wtext.get(m.widgets['pf_status']) == 'No results', 'no match: the page\'s dim "No results"')
    expect(found(m, 'special') == [f'Special {i}' for i in range(30)], 'results stay in the show\'s order')
    r = rows(m)
    expect(r[0][0] == 'Special 0' and r[0][1] and r[0][1].endswith('· Downloaded') and r[0][2] == 'label_row_title', f'a row: the title and the grey line with the date and the Downloaded mark ({r[0]})')
    expect(m.props[(m.fsv, 'virtual_h')] == 31 * ROW + KB_H, 'the content is the rows, the Search All Episodes row (the show has a feed and no archive) and the keyboard\'s height while it is up')
    expect(found(m, 'five') == ['Ep 5: Five'] and found(m, 'ep 5') == ['Ep 5: Five'] and found(m, '5') == ['Ep 5: Five', 'Special 5'], 'a word; a word and a number; a number alone (both of its titles, in order)')
    # a tap on a result: the episode page opens on the Show page, the search page closes (Back); Back there opens it again with its text
    m.calls = []
    tap_row(m, 0)
    expect(any(c[0] == 'navigator_back' for c in m.calls), 'the tap closes the search page')
    m.call(PSYMS['pf_on_destroy'], count=2000000)   # (the harness's navigator_back destroys nothing)
    m.sv, m.view = m.psv, m.pview
    expect(PCD.is_page(m), 'the episode page is open on the Show page')
    m.calls = []
    PCP.click(m, 'btn_return')
    expect(('window_open', 'm1plus_pcfind') in m.calls and not PCD.is_page(m), 'Back from the episode page opens the search again over the list')
    m.sv, m.view = m.psv, m.pview
    expect(m.wtext.get(m.widgets['kb_text']) is not None, 'the keyboard is attached again')
    expect([t for t, _, _ in rows(m)] == ['Ep 5: Five', 'Special 5'], 'the text is kept: the same results')
    expect(not (m.props.get((m.widgets['kb_pad'], 'visible'), 1)), 'the keyboard is down')
    m.calls = []
    typed(m, 'special')
    m.setword(m.fsv + O['SC_YOFF'], 300); m.props[(m.fsv, 'yoffset')] = 300
    tap_row(m, 6, off=300)   # row 6 of the results = Special 6, shown at offset 300
    m.call(PSYMS['pf_on_destroy'], count=2000000)
    m.sv, m.view = m.psv, m.pview
    expect(PCD.is_page(m), 'a result deep in the list opens its episode page')
    PCP.click(m, 'btn_return')
    m.sv, m.view = m.psv, m.pview
    off = m.props.get((m.fsv, 'yoffset'), m.word(m.fsv + O['SC_YOFF']))
    expect(off == 300, f'Back keeps the scroll ({off})')
    # leaving the search returns to the Show page where it was
    m.calls = []
    PCP.click(m, 'pf_close')
    expect(any(c[0] == 'navigator_back' for c in m.calls), 'the X closes the page (Back: the Show page under it)')


def queue_tests(ctx):
    """Playing from a result queues the show's order from that episode down, not the results."""
    expect = ctx.expect
    T = [f'Ep {i}' for i in range(10)]
    m = find_widgets(show(T))
    click_find(m)
    typed(m, '3')
    expect([t for t, _, _ in rows(m)] == ['Ep 3'], 'one result')
    tap_row(m, 0)
    m.call(PSYMS['pf_on_destroy'], count=2000000)
    m.sv, m.view = m.psv, m.pview
    m.calls = []
    PCP.tap(m, 30, PCD.page_y(m) + O['PS_PILL_H'] // 2)
    q, idx = m.played
    paths = [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q]
    expect(paths[idx] == f'{PSH.RP}/{PSH.DEEP}/e3.mp3' and paths[idx:] == [f'{PSH.RP}/{PSH.DEEP}/e{i}.mp3' for i in range(3, 10)], f'the queue is the show\'s own order from Ep 3 on, not the single result ({[p.rsplit("/", 1)[1] for p in paths]}, at {idx})')


def asset_tests(ctx):
    expect = ctx.expect
    tree = awtk_ui.parse(open(ASSET, 'rb').read())
    names = {w.name for w in tree.walk() if w.name}
    expect({'pf_listview', 'pf_scrollview', 'pf_view', 'pf_status', 'pf_close', 'kb_field', 'kb_pad', 'label_row_title', 'label_row_dim', 'label_row_sub', 'label_title'} <= names, 'the page\'s widgets by name')
    h = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'patch', 'pcfind.h')).read()
    import re
    d = {k: int(v) for k, v in re.findall(r'#define (PF_\w+)\s+(\d+)', h)}
    expect(d['PF_LIST_Y'] == LIST_Y and d['PF_LIST_H'] == LIST_H and d['PF_ROW_H'] == ROW, 'the header and this test agree on the geometry')
    lv = next(w for w in tree.walk() if w.name == 'pf_listview')
    expect(lv.y == LIST_Y and lv.h == 450 - LIST_Y, 'the list starts under the field and runs to the window\'s bottom')


ARC = sibling('pcarchive')
TITLES5 = [f'Alpha {i}' for i in range(5)]
MORE_IDLE, MORE_RETRY = 'Search All Episodes', "Can't connect \u00b7 Tap to Retry"


def more_tests(ctx):
    """The Search All Episodes row: when it is there, the tap that starts the Show page's job, Loading… and the count, the end picked up by the page's own timer (the list read again, the query run anew), a failure and its retry,
    a download that goes on beside the job, leaving the page and the episode page while the job runs, Chinese titles in the archive, the Filter."""
    expect = ctx.expect
    tick = lambda m: m.call(PSYMS['pf_tick'], a0=0, count=400000000)
    atick = lambda m: m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    last = lambda m: rows(m, 60, more=True)[-1]
    feed_xml = ARC.feed([ARC.item(100 + i, title=f'Alpha Old {i}') for i in range(40, 0, -1)])
    dead = lambda u, o: {'rc': 6}

    def opened(**kw):
        m = find_widgets(show(TITLES5, **kw))
        click_find(m)
        return m

    def go(m, site):
        """Type alpha, tap the row (the one after the five results): the worker thread of the job."""
        typed(m, 'alpha')
        m.curl_site = site
        m.thread = None
        tap_row(m, 5)
        return m.thread

    # 1. Presence: a feed show with no archive and a text; not an empty field, not a show of copied files, not one with an archive
    m = opened()
    expect(rows(m, more=True) == [], 'an empty field: no rows, no Search All Episodes')
    typed(m, 'alpha')
    r = rows(m, more=True)
    expect(len(r) == 6 and r[-1] == (MORE_IDLE, None, 'label_row_title') and not is_more(r[0][0]) and rows(m) == r[:5], f'with results the row ends them, in the title style, no grey line ({r[-1]})')
    expect(m.props[(m.fsv, 'virtual_h')] == 6 * ROW + KB_H and flags(m, 'pf_status') == (0, 0), 'the row is a compact row of the results\' height')
    typed(m, 'zzzz')
    expect(rows(m, more=True) == [(MORE_IDLE, None, 'label_row_title')] and flags(m, 'pf_status') == (1, 1) and m.wtext.get(m.widgets['pf_status']) == 'No results', 'no match: the row stands alone at the top, "No results" under it')
    typed(m, '')
    expect(rows(m, more=True) == [] and flags(m, 'pf_status') == (0, 0), 'the field emptied: the row goes')
    m = opened(feed=False)
    typed(m, 'alpha')
    expect(len(rows(m, more=True)) == 5, 'a show of copied files has no feed: no row')
    es = [PSH.entry(i, t=t) for i, t in enumerate(TITLES5)]
    m = find_widgets(PSH.machine(card=lambda mm: (PSH.deep_card(mm, entries=es, files=range(5)), mm.put(f'{PSH.RP}/{PSH.DEEP}/.archive', ARC.eps_text(dict(g='a', p=1, f='a.mp3', t='Alpha Z', u='u'))))))
    PSH.open_show(m)
    click_find(m)
    typed(m, 'alpha')
    expect(len(rows(m, more=True)) == 6 and not any(is_more(t) for t, _, _ in rows(m, more=True)), 'a show that has an archive: no row')

    # 2. A tap starts the job; Loading… and the count; taps on the row and on the results go on; the end is the page's own timer's
    m = opened()
    th = go(m, lambda u, o: {'body': feed_xml})
    expect(th and th[0] == PSYMS['pn_armain'] and ARC.state(m)[0] == ARC.AR['RUNNING'], 'a tap on the row starts the archive job as the Show page does')
    expect(last(m) == ('Loading…', None, 'label_row_dim'), f'the row reads Loading… in the dim style ({last(m)})')
    m.thread = None
    tap_row(m, 5)
    expect(m.thread is None and last(m)[0] == 'Loading…', 'a tap on the row while it loads does nothing')
    m.setword(ARC.count_addr(m), 340)
    tick(m)
    expect(last(m)[0] == 'Loading… 340', f'the count follows the job ({last(m)})')
    typed(m, 'alpha 2')
    expect([t for t, _, _ in rows(m, more=True)] == ['Alpha 2', 'Loading… 340'], 'typing goes on while it runs: the row stays at the end')
    typed(m, 'alpha')
    ARC.PCN.work(m, th)
    m.setword(m.fsv + O['SC_YOFF'], 120); m.props[(m.fsv, 'yoffset')] = 120
    atick(m)
    expect(ARC.state(m)[0] == ARC.AR['IDLE'], 'the downloads\' timer ended the job (the Show page\'s tick is stopped)')
    tick(m)
    r = rows(m, 60, more=True)
    expect(len(r) == 45 and not any(is_more(t) for t, _, _ in r) and r[0][0] == 'Alpha 0' and r[-1][0].startswith('Alpha Old'), f'the archive is in: the same query finds more, in the show\'s order, no row ({len(r)})')
    expect(m.props[(m.fsv, 'yoffset')] == 0 and m.props[(m.fsv, 'virtual_h')] == 45 * ROW + KB_H, 'the list starts at the top')
    expect(m.props[(m.psv, 'virtual_h')] < 40 * PCP.CELL and f'{PSH.RP}/{PSH.DEEP}/.archive' in m.fs, 'the Show page under it was read again with the archive: still its 20 rows and the See All row (the search holds the complete list)')
    typed(m, 'old 7')
    expect([t for t, _, _ in rows(m, 60, more=True)] == ['Alpha Old 7'], 'the matcher is over the new list')

    # 3. A failure: the reason and Tap to Retry on the row; a tap retries; a cancel shows nothing
    m = opened()
    th = go(m, dead)
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    expect(last(m) == (MORE_RETRY, None, 'label_row_title') and ARC.state(m)[0] == ARC.AR['IDLE'], f'a failure: the reason and the hint on the row ({last(m)})')
    m.curl_site = lambda u, o: {'body': feed_xml}
    m.thread = None
    tap_row(m, 5)
    expect(m.thread and m.thread[0] == PSYMS['pn_armain'] and last(m)[0] == 'Loading…', 'a tap retries: Loading… again')
    th = m.thread
    m.call(PSYMS['pg_srch_leave'], count=2000000)   # (another job cancels it)
    m.curl_site = lambda u, o: dict({'body': feed_xml, 'chunk': 200}, xfer=lambda url, sent, total: None)
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    expect(ARC.state(m)[0] == ARC.AR['IDLE'] and last(m)[0] in (MORE_IDLE, 'Loading…') and MORE_RETRY not in str(rows(m, more=True)), 'a cancelled job shows no failure')

    # 4. A running download goes on beside the job: the job starts at the tap, nothing is paused or started again
    m = opened()
    typed(m, 'alpha')
    m.curl_site = lambda u, o: dict({'body': feed_xml, 'chunk': 200}, xfer=lambda url, sent, total: None)
    r, dth = ARC.DL.add(m, 'e5.mp3', PSH.DEEP)
    m.thread = None
    tap_row(m, 5)
    ath = m.thread
    expect(ath and ath[0] == PSYMS['pn_armain'] and last(m)[0] == 'Loading…' and ARC.state(m)[0] == ARC.AR['RUNNING'] and ARC.DL.fn(m, 'pn_dl_running') == 1 and ARC.DL.fn(m, 'pn_dl_waiting') == 1,
           'with a download running the job starts at the tap (Loading…); the download thread and its queue are left alone')
    m.curl_site = lambda u, o: {'body': feed_xml}
    ARC.PCN.work(m, ath)
    m.thread = None
    atick(m)
    expect(m.thread is None and ARC.DL.fn(m, 'pn_dl_running') == 1, 'at the job\'s end no thread is started: the download thread is still the one that runs')
    m.call(dth[0], a0=dth[1], count=1 << 40)
    expect(ARC.DL.fn(m, 'pn_dl_running') == 0 and ARC.DL.fn(m, 'pn_dl_count') == 0, 'the download thread then drains its queue and ends')
    tick(m)
    expect(len(rows(m, 60, more=True)) == 45, 'and the search has the archive')

    # 5. Leaving the search while it runs: the job goes on and the Show page shows the count; an episode page and Back: the row shows the state
    m = opened()
    th = go(m, lambda u, o: {'body': feed_xml})
    m.setword(ARC.count_addr(m), 12)
    PCP.click(m, 'pf_close')
    m.call(PSYMS['pf_on_destroy'], count=2000000)
    m.sv, m.view = m.psv, m.pview
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    bottom = max(0, m.props[(m.sv, 'virtual_h')] - 400)
    live = [t for (t, r), s in zip(*PCP.paint(m, bottom)[1:3]) if s == 'label_ps_cdim']
    expect(ARC.state(m)[0] == ARC.AR['RUNNING'] and live[-1:] == ['Loading… 12'], f'the job went on; the Show page shows its count ({live})')
    m = opened()
    th = go(m, lambda u, o: {'body': feed_xml})
    typed(m, 'alpha 3')
    tap_row(m, 0)
    m.call(PSYMS['pf_on_destroy'], count=2000000)
    m.sv, m.view = m.psv, m.pview
    expect(PCD.is_page(m), 'an episode page opened from a result while the job runs')
    m.setword(ARC.count_addr(m), 77)
    PCP.click(m, 'btn_return')
    m.sv, m.view = m.psv, m.pview
    expect(last(m) == ('Loading… 77', None, 'label_row_dim'), f'Back to the search: the row shows the job as it is ({last(m)})')
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    typed(m, 'alpha')
    expect(len(rows(m, 60, more=True)) == 45, 'and the end is picked up there')

    # 6. Chinese titles in the archive: the initials work after the reload (the engine is held then)
    zh_feed = ARC.feed([ARC.item(100 + i, title=f'\u5468\u6770\u4f26 \u7cbe\u9009 {i}') for i in range(10, 0, -1)])
    m = opened()
    m.present.add(S.PY_DICT_PATH); m.py_dict = S.PINYIN; m.py_ids = {}; m.handlers.update({0x5c01a4: 'py_lemma_id', 0x5bffd4: 'py_splids', 0x5c922c: 'py_spelling'})
    th = go(m, lambda u, o: {'body': zh_feed})
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    typed(m, 'zjl')
    expect(len(rows(m, more=True)) == 10 and rows(m)[0][0].startswith('\u5468\u6770\u4f26'), f'zjl finds the Chinese titles the archive brought ({len(rows(m, more=True))})')

    # 7. The Filter and its index array are the Show page's own after a reload from here
    FL = sibling('pcfilter')
    m = PSH.machine(entries=[PSH.entry(i) for i in range(3)], files=(0, 1)); PSH.open_show(m)
    find_widgets(m)
    FL.to_filter(m, 2)
    click_find(m)
    m.curl_site = lambda u, o: {'body': ARC.feed([ARC.item(100 + i, title=f'Episode Old {i}') for i in range(40, 0, -1)])}
    typed(m, 'episode')
    m.thread = None
    tap_row(m, 3)
    ARC.PCN.work(m, m.thread)
    atick(m)
    tick(m)
    expect(len(rows(m, 60, more=True)) == 43, 'the search sees every episode, the Filter ignored, after the reload too')
    PCP.click(m, 'pf_close')
    m.call(PSYMS['pf_on_destroy'], count=2000000)
    m.sv, m.view = m.psv, m.pview
    expect(FL.ids(m) == [0, 1], f'the Show page keeps its Filter (Downloaded: the two on the card) over the long list ({FL.ids(m)[:5]})')


def spin_tests(ctx):
    """The Search All Episodes row's spinner (patch/pcfind.c pf_spin_*): the 14 px frame before the dim text while the job loads, turned by a 250 ms timer of the page; none when the row is idle, failed or the job ended; the timer
    ends with the row and is removed with the page."""
    expect = ctx.expect
    tick = lambda m, fn='pf_tick': m.call(PSYMS[fn], a0=0, count=400000000)
    atick = lambda m: m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    feed_xml = ARC.feed([ARC.item(100 + i, title=f'Alpha Old {i}') for i in range(40, 0, -1)])
    RR = O['RET_REPEAT']
    adds = lambda m: [t for t in m.timers if t[0] == PSYMS['pf_spin_tick']]

    def spin(m):
        fpaint(m, 0)
        return [b for b in m.blits if m.bitmaps[b[0]][1:] == (14, 14)]

    def opened():
        m = find_widgets(show(TITLES5))
        for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)   # (the Wi-Fi page's frames as cc_decode flattens them over black)
        click_find(m)
        typed(m, 'alpha')
        return m

    def go(m, site):
        m.curl_site = site
        m.thread = None
        tap_row(m, 5)
        return m.thread

    m = opened()
    expect(spin(m) == [] and not adds(m), 'the idle row: no spinner, no timer')
    th = go(m, lambda u, o: {'body': feed_xml})
    sp = spin(m)
    txt = [r for (t, r), st in fpaint(m, 0) if t == 'Loading…']
    expect(len(sp) == 1 and sp[0][2][0] == 16 and sp[0][2][2:] == (14, 14) and sp[0][2][1] == 5 * ROW + (ROW - 14) // 2 and txt and txt[0][0] == 16 + 14 + O['PS_SPIN_GAP'],
           f'Loading…: the spinner centred in the row, the text after it ({[b[2] for b in sp]}, {txt})')
    expect(len(adds(m)) == 1 and (PSYMS['pf_spin_tick'], O['PS_SPIN_MS']) in m.timers, 'one 250 ms timer')
    seen = [sp[0][0]]
    for _ in range(8):
        expect(tick(m, 'pf_spin_tick') == RR, 'the timer goes on while it loads')
        seen.append(spin(m)[0][0])
    expect(len(set(seen[:8])) == 8 and seen[8] == seen[0], 'each tick shows the next frame')
    m.setword(ARC.count_addr(m), 340)
    tick(m)
    expect(len(adds(m)) == 1 and len(spin(m)) == 1, 'the 1 s tick (the count moved) adds no second timer')
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    expect(spin(m) == [] and tick(m, 'pf_spin_tick') != RR, 'the job ended: no spinner (the row is gone), the timer ends')

    m = opened()
    th = go(m, lambda u, o: {'rc': 6})
    expect(len(spin(m)) == 1, 'a job that is going to fail: the spinner meanwhile')
    ARC.PCN.work(m, th)
    atick(m)
    tick(m)
    expect(spin(m) == [] and tick(m, 'pf_spin_tick') != RR, 'a failure: Tap to Retry, no spinner, the timer ended')
    expect(any(t.endswith('Tap to Retry') and r[0] == 16 for (t, r), st in fpaint(m, 0)), 'the failure text starts at the row\'s text edge')

    def removes(m):
        m.calls = []
        fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
        m.call(fn, a0=c, a1=0, count=40000000)
        return len([c for c in m.calls if c[0] == 'timer_remove'])
    m = opened(); go(m, lambda u, o: {'body': feed_xml})
    live = removes(m)
    m = opened(); go(m, lambda u, o: {'body': feed_xml})
    tick(m, 'pf_spin_tick')
    m.setword(ARC.count_addr(m), 0)
    m.call(PSYMS['pg_srch_leave'], count=2000000)
    ARC.PCN.work(m, m.thread)
    atick(m)
    tick(m)
    tick(m, 'pf_spin_tick')
    expect(live == removes(m) + 1, 'closing the page removes the spinner timer while the row loads')


SECTIONS = [nav_tests, match_tests, flow_tests, queue_tests, asset_tests, more_tests, spin_tests]

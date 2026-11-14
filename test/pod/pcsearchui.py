"""Podcast search on the Podcasts page (patch/podcasts.c, docs/modules/podcasts.md "Search"): the Discover row on the Shows page (there while Podcast Discover is on, the default) and the navbar's shapes; the search level, reached from the
Discover level's magnifier (the field that opens our keyboard, Searching..., the rows, No results, every failure in the page's words, a result with no feed shown as Not available and dimmed, thumbnails arriving,
leaving while the worker fetches, Back returning to Discover), what is typed (a term, a feed address, an Apple Podcasts link), the preview of a show (the Show page with its Subscribe pill, the episodes greyed, no
sheets), Subscribe (what an import makes, already subscribed, a failed fetch makes nothing), the downloads pausing for a job, the screen-off rule and the strings' widths in 13 languages (test/pod/pcdiscover.py has
the Discover level itself). The compiled payload runs under Unicorn; the card is a dict of paths and libcurl is scripted."""
import io, json, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


PCS, SE = sibling('pcshows'), sibling('pcsearch')
PCP, PCN = PCS.PCP, PCS.PCN
import pod_i18n, pod_show   # noqa: E402

RP, SDIR = PCP.ROOT, SE.SDIR
DATA_DC = os.path.join(ROOT, 'test', 'data', 'discover')
CHART = 'https://rss.marketingtools.apple.com/api/v2/us/podcasts/top/25/'
SEARCH, LOOKUP = SE.SEARCH, SE.LOOKUP
F_WSJ = SE.F_WSJ
NOW = PCS.NOW
ALL_IN = SE.data('all_in_us.json')
ART = SE.ART
WSJ = PCN.feed_bytes('wsj-3items.xml')
PQ = {k: v for k, v in O.items() if k.startswith('PQ_')}


def card_for(imp=False, subs=True, setting=None):
    def card(m):
        if setting is not None: m.put('/mnt/data/m1plus/podcast-online-search', setting)
        (PCS.card if subs else PCP.page_card)(m)   # (subs: the card has subscriptions, so the "..." always has the Subscriptions row)
        if imp: m.put(f'{RP}/subscriptions.txt', b'https://x.example/rss\n')
    return card


def chart(kind):
    """The sample chart answers (Apple's rss.marketingtools.apple.com, country us, top 25, fetched 2026-11-05)."""
    return open(os.path.join(DATA_DC, f'top-{kind}-us-50.json'), 'rb').read()


def site_for(**extra):
    """A scripted store and feed: the search answer (ALL_IN), pictures, the WSJ feed and its picture; extra: url -> a reply dict, or a function."""
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (1400, 1400), (30, 30, 200)).save(b, 'JPEG'); big = b.getvalue()
    log = []

    def site(url, o):
        log.append(url)
        if url in extra: return extra[url](url, o) if callable(extra[url]) else extra[url]
        if url.startswith(SEARCH): return {'body': ALL_IN}
        if url == CHART + 'podcasts.json': return {'body': chart('shows'), 'chunk': 8192}
        if url == CHART + 'podcast-episodes.json': return {'body': chart('episodes'), 'chunk': 8192}
        if url.startswith(LOOKUP + '1200361736'): return {'body': open(os.path.join(DATA_DC, 'lookup-1200361736.json'), 'rb').read()}
        if url.startswith('https://is1-ssl.mzstatic.com/'): return {'body': ART, 'chunk': 1500}
        if url == F_WSJ: return {'body': WSJ}
        if url.startswith('https://image.simplecastcdn.com/'): return {'body': big}
        return {'rc': 22, 'code': 404}
    site.log = log
    return site


def opened(imp=False, site=None, subs=True, setting=None):
    m = PCS.opened(cardf=card_for(imp, subs, setting))
    m.windows['m1plus_keyboard'] = 0   # (keyboard_open finds no window: the test calls the callbacks the keyboard would)
    m.setword(m.widgets['ps_text'] + 8, O['PQ_TEXT_W']); m.setword(m.widgets['ps_hint'] + 8, O['PQ_TEXT_W'])   # (the labels' widths: the text is cut to them)
    m.curl_site = site or site_for()
    m.px[m.widgets['ps_text']] = m.px[m.widgets['ps_hint']] = 18
    return m


def flags(m, n): return m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1)
def icon(m, n, st='normal'): return m.props.get((m.widgets[n], f'style:{st}:icon'))
def moves(m, n): return [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[n]]


def text(m, n): return undo(m.wtext.get(m.widgets[n], ''))
def at_search(m): return flags(m, 'ps_field')[0] == 1 and flags(m, 'pg_big')[0] == 0 and flags(m, 'label_title')[0] == 1 and text(m, 'label_title') == 'Apple Podcasts'   # (the search level's title is the navbar's Apple Podcasts, no large one)


def hint(m, off=0): return PCP.hint(m, off)   # (the status text painted in the content under the field)
def tick(m): return PCS.tick(m)


def work(m):
    """The worker the page started runs to its end."""
    th, m.thread = m.thread, None
    assert th, 'a worker was started'
    PCN.work(m, th)


def at_disc(m): return flags(m, 'pg_big')[0] == 1 and flags(m, 'label_title')[0] == 0 and text(m, 'pg_big') == 'Discover' and flags(m, 'ps_field')[0] == 0


def discover(m):
    """A tap on the Discover row: the Discover level opens, its first tick asks for the Shows chart, the worker (the harness runs it when told) answers and fetches the pictures, the tick takes them in. The scripted
    store's log is emptied: what follows is the test's own."""
    PCP.tap_discover(m)
    tick(m)
    if m.thread: work(m)
    tick(m)
    getattr(m.curl_site, 'log', []).clear()


def magnifier(m):
    """The Discover level's magnifier: the search level opens on Apple Podcasts and (nothing typed) the keyboard is asked for."""
    n = len(m.calls)
    PCP.click(m, 'btn_search')
    return [c for c in m.calls[n:] if c[0] == 'window_open']


def enter(m):
    """The Discover level, then its magnifier."""
    discover(m)
    return magnifier(m)


def submit(m, term):
    """What the keyboard calls when its Search key is pressed: the page is in front already."""
    m.call(PSYMS['pg_srch_done'], a0=m.cstr(term), count=40000000)


def level_rows(m, off=0):
    """[(title, sub)] of the result rows drawn in a frame, top to bottom."""
    _, texts, styles, _ = PCP.paint(m, off)
    t = {r[1]: x for (x, r), s in zip(texts, styles) if s == 'label_row_title'}
    s = {r[1]: x for (x, r), s_ in zip(texts, styles) if s_ == 'label_row_sub'}
    rows = []
    for y in sorted(t):
        rows.append((t[y], next((v for k, v in s.items() if k - y == O['LIST_SUB_Y'] - O['LIST_TITLE_Y']), None)))
    return [(PCS.fixed(a), PCS.fixed(b) if b else b) for a, b in rows]


def same(shown, full):
    """A text as a row shows it: whole, or cut with an ellipsis."""
    return shown == full or (shown.endswith('…') and full.startswith(shown[:-1]))


def settle(m, rounds=6):
    """The loader runs until it has nothing to decode (the harness' timers never fire by themselves)."""
    for _ in range(rounds): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)


def stage(m, term='all in'):
    """Enter the level, submit a term, the worker answers, the tick takes the answer in."""
    enter(m)
    submit(m, term)
    work(m)
    tick(m)


# ---------------------------------------------------------------------------
def has_row(m):
    """Does the Shows level have a Discover row (its title is drawn in some frame)?"""
    try:
        PCP.lib_row_at(m, 'Discover')
    except AssertionError:
        return False
    return True


def entry_tests(ctx):
    """The entry: the Discover row of the Shows level's Library rows (a tile, Discover, Apple Podcasts in grey, the list chevron and hairline), directly above Downloads, there while Podcast Discover is on (the default; hidden when the setting file says 0); the navbar's shapes on the Shows level (the globe while Podcast Discover is on, the \"...\" only when Import is possible, then Now Playing); the Show level is unchanged; a tap opens the Discover level, not the keyboard."""
    expect = ctx.expect
    NP = lambda m, st='normal': m.props[(m.widgets['btn_backtoplayer'], f'style:{st}:icon')]
    X, W = O['NAV_VIEW_X'], O['NAV_VIEW_W']
    shapes = ((False, False, 'Now Playing disc', []),
              (True, False, 'globe | Now Playing', [('btn_globe', X)]),
              (False, True, '... | Now Playing', [('btn_more', X)]),
              (True, True, 'globe | ... | Now Playing', [('btn_globe', X - W), ('btn_more', X)]))
    for on, imp, name, slots in shapes:
        m = opened(imp=imp, subs=False, setting=None if on else b'0\n')   # (no show with a feed: the "..." is Import's alone; with one it holds Refresh All too)
        shown = {n for n in ('btn_globe', 'btn_more') if flags(m, n) == (1, 1)}
        np_icon = ('ah_nav_play', 'ah_nav_play_down') if slots else ('ah_nav_np', 'ah_nav_np_down')
        expect(shown == {n for n, _ in slots} and flags(m, 'btn_search') == (0, 0) and (NP(m), NP(m, 'pressed')) == np_icon, f'{name}: exactly those pieces show (no magnifier on the Shows level), Now Playing is the right cap of a capsule or the plain disc')
        for n, x in slots:
            if n != 'btn_more': expect(moves(m, n)[-1] == (x, 0), f'{name}: {n} is on slot {x} ({moves(m, n)[-1:]})')
        expect(icon(m, 'btn_more') == ('pod_nav_moremid' if on and imp else 'pod_nav_more'), f'{name}: the "..." is the middle piece beside the globe, else the left cap')
        expect(icon(m, 'btn_more', 'pressed') == ('pod_nav_moremid_down' if on and imp else 'pod_nav_more_down'), f'{name}: and its pressed picture')
        w = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['label_title']]
        right = min([x for _, x in slots] or [X + W])
        expect(w and w[-1][2:] == (right - O['NAV_TITLE_X'], 22) and flags(m, 'label_title')[0] == 0 and PCP.title_text(m) == 'Podcasts', f'{name}: the small title is hidden at rest and ends before the leftmost piece; the large heading is the title')
        xs = [x for _, x in slots]
        expect(all(b - a == W for a, b in zip(xs, xs[1:])) and (not xs or xs[-1] == X), f'{name}: the glyphs are 46 apart (the glass capsule rules)')
    # the globe: Apple Podcasts search straight from the Shows level (Back returns to the Shows level); Discover's magnifier returns to Discover
    m = opened()
    m.calls = []
    PCP.click(m, 'btn_globe')
    expect(('window_open', 'm1plus_keyboard') in m.calls and at_search(m) and flags(m, 'btn_globe') == (0, 0) and flags(m, 'btn_search') == (0, 0), 'a tap on the globe: the search level opens (keyboard asked for), the globe goes')
    m.call(PSYMS['pg_srch_cancel'], count=4000000)
    expect(not at_disc(m) and not at_search(m) and PCP.title_text(m) == 'Podcasts' and flags(m, 'btn_globe') == (1, 1), 'the keyboard\'s Back from the globe\'s search: the Shows level, the globe is back')
    discover(m)
    expect(flags(m, 'btn_globe') == (0, 0) and flags(m, 'btn_search') == (1, 1), 'on the Discover level: the magnifier, no globe')
    m = opened(setting=b'0\n')
    n = len(m.calls)
    PCP.click(m, 'btn_globe')
    expect(not at_search(m) and ('window_open', 'm1plus_keyboard') not in m.calls[n:], 'off: the globe does nothing (hidden, and the handler refuses)')
    m.fs['/mnt/data/m1plus/podcast-online-search'] = b'1\n'
    PCS.refg(m)
    expect(flags(m, 'btn_globe') == (1, 1), 'switched on in Settings while the page was behind: the globe is there when the page is back in front')
    m.fs['/mnt/data/m1plus/podcast-online-search'] = b'0\n'
    PCS.refg(m)
    expect(flags(m, 'btn_globe') == (0, 0), 'and gone again when switched off')
    # the row follows Settings > Library > Podcasts > Podcast Discover: on with no file (the default), on with anything but "0", off with "0"
    SETTING = '/mnt/data/m1plus/podcast-online-search'
    m = opened()
    expect(has_row(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(4, True, 0)['h'], 'no setting file: Podcast Discover is on, the Discover row is there')
    for body in (b'1\n', b'x'):
        m = opened(setting=body)
        expect(has_row(m), f'a setting file of {body!r}: on, the row is there')
    m = opened(setting=b'0\n')
    expect(not has_row(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(4, True, 0, discover=False)['h'], 'a setting file of 0: the Discover row is hidden and the Library rows close up (Downloads first)')
    m.fs[SETTING] = b'1\n'
    PCS.refg(m)
    expect(has_row(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(4, True, 0)['h'], 'switched on in Settings: the row is back when the page is in front again')
    m = opened()
    discover(m)
    m.fs[SETTING] = b'0\n'
    PCS.refg(m)
    expect(not at_disc(m) and not at_search(m) and PCP.title_text(m) == 'Podcasts' and not has_row(m), 'switched off in Settings while on Discover: the page returns to the Shows level, without the row')
    m = opened()
    enter(m)
    m.fs[SETTING] = b'0\n'
    PCS.refg(m)
    expect(not at_disc(m) and not at_search(m) and PCP.title_text(m) == 'Podcasts' and not has_row(m), 'and while on the search level')
    m = opened(setting=b'0\n')
    n = len(m.calls)
    PCP.click(m, 'btn_search')
    expect(not at_disc(m) and not at_search(m) and ('window_open', 'm1plus_keyboard') not in m.calls[n:], 'off: the magnifier does nothing on the Shows level (hidden, and the handler refuses)')
    m = opened(setting=b'0\n')
    m.call(PSYMS['pg_load_disc'], a0=1, count=40000000)
    expect(not at_disc(m) and PCP.title_text(m) == 'Podcasts', 'off: the Discover level cannot be opened (the loader lands on the Shows level)')
    m = opened(setting=b'0\n')
    m.call(PSYMS['pg_load_search'], a0=1, count=40000000)
    expect(not at_search(m) and PCP.title_text(m) == 'Podcasts', 'off: the search level cannot be opened (the loader lands on the Shows level)')
    m = opened()
    expect(m.call(PSYMS['pcsearch_setting'], count=2000000) == 1 and m.call(PSYMS['pcsearch_toggle'], count=4000000) == 0 and m.fs[SETTING] == b'0\n'
           and m.call(PSYMS['pcsearch_setting'], count=2000000) == 0 and m.call(PSYMS['pcsearch_toggle'], count=4000000) == 1 and m.fs[SETTING] == b'1\n',
           'pcsearch_setting reads 1 with no file; a toggle writes 0, then 1, atomically')
    o = O
    lay = pod_show.shows_layout(4, True, 0)
    expect(m.props.get((m.sv, 'virtual_h')) == lay['h'] and lay['y_srch'] + o['PC_ROW_H'] == lay['y_dl'] and lay['y_dl'] + o['PC_ROW_H'] == lay['y_sub'], 'the Discover row is the first Library row, directly above Downloads; the layout has it always')
    ys, yd = PCP.lib_row_at(m, 'Discover'), PCP.lib_row_at(m, 'Downloaded')
    expect(ys[0] + o['PC_ROW_H'] == yd[0] and ys[0] - o['LIST_TITLE_Y'] - o['LIST_TITLE_H'] // 2 == lay['y_srch'], f'Discover is drawn PC_ROW_H above Downloads, at the layout\'s top ({ys[0]}, {yd[0]})')
    off = max(0, m.props.get((m.sv, 'virtual_h'), 0) - 400)
    blits, texts, styles, fills = PCP.paint(m, off)
    title = [r for (t, r), s in zip(texts, styles) if s == 'label_row_title' and t == 'Discover']
    sub = [r for (t, r), s in zip(texts, styles) if s == 'label_row_sub' and t == 'Apple Podcasts']
    expect(len(title) == 1 and len(sub) == 1 and title[0][0] == o['PP_DL_TEXT_X'] and title[0][2] == o['PP_DL_TEXT_W'] and sub[0][0] == o['PP_DL_TEXT_X'] and sub[0][1] - title[0][1] == o['LIST_SUB_Y'] - o['LIST_TITLE_Y'],
           f'the row\'s texts are the Downloads row\'s: Discover at x {o["PP_DL_TEXT_X"]}, {o["PP_DL_TEXT_W"]} wide (ends at 278), Apple Podcasts in grey under it ({title}, {sub})')
    # a tap on the row opens the Discover level: no keyboard, the magnifier is the navbar's left cap beside Now Playing
    m.calls = []
    PCP.tap_discover(m)
    expect(('window_open', 'm1plus_keyboard') not in m.calls and at_disc(m) and flags(m, 'btn_search') == (1, 1) and flags(m, 'btn_more') == (0, 0)
           and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play', 'a tap on the Discover row opens the Discover level (no keyboard): large title Discover, the magnifier shows, Now Playing is the capsule\'s right cap')
    # a show opened: "... | Now Playing" (the middle piece is only for the Shows level), the globe gone; back on the Shows level the row, the globe and the middle "..." are there again
    m = opened(imp=True)
    PCP.tap_show(m, 'Alpha')
    expect(flags(m, 'btn_globe') == (0, 0) and flags(m, 'btn_more') == (1, 1) and flags(m, 'btn_search') == (1, 1) and icon(m, 'btn_more') == 'pod_nav_moremid', 'on a Show page: "Search | ... | Now Playing" (the search inside the show: test/pod/pcfind.py), no globe')
    PCP.click(m, 'btn_return')
    expect(has_row(m) and flags(m, 'btn_globe') == (1, 1) and icon(m, 'btn_more') == 'pod_nav_moremid', 'back on the Shows level: the Discover row, the globe and the middle "..."')
    # the assets
    from mod_icons import NAV_VIEW, NAV_VIEW_POS
    import mod_icons
    expect(NAV_VIEW['pod_nav_moremid'] == 'ellipsis' and NAV_VIEW_POS['pod_nav_moremid'] == 'middle'
           and NAV_VIEW['pod_nav_globe'] == 'globe' and NAV_VIEW_POS['pod_nav_globe'] == 'left', 'the "..." is a middle piece beside the globe, the globe the left cap (Lucide globe)')
    pics = {n: asset_image(n) for n in ('pod_nav_moremid', 'pod_nav_moremid_down', 'pod_nav_globe', 'pod_nav_globe_down')}
    for n in ('pod_nav_moremid', 'pod_nav_moremid_down', 'pod_nav_globe', 'pod_nav_globe_down', 'pod_ic_discovertile'):
        path = os.path.join(mod_icons.PNG, n + '.png')
        expect(os.path.isfile(path) and (n == 'pod_ic_discovertile' or open(path, 'rb').read() == open(asset_path(n), 'rb').read()), f'{n}.png is committed' + ('' if n == 'pod_ic_discovertile' else ' and is the file the build ships'))
    expect('pod_ic_discovertile' in mod_icons.PODCASTS, 'the Discover row\'s tile is generated')
    globe, mid = pics['pod_nav_globe'], pics['pod_nav_moremid']
    white = lambda im: {(x, y) for y in range(im.height) for x in range(im.width) if im.getpixel((x, y))[:3] == (255, 255, 255) and im.getpixel((x, y))[3] > 200}
    gw = white(globe)
    cx = globe.width // 2 + 7
    gy = sorted(y for x, y in gw if x == cx)
    expect(len(gw) > 60 and gy and gy[-1] - gy[0] >= 15 and pics['pod_nav_globe_down'].tobytes() != globe.tobytes() and globe.width == mid.width,
           f'the globe piece draws a 24 px globe glyph ({len(gw)} white pixels, {gy[-1] - gy[0] if gy else None} px tall) and has a pressed picture')
    dots = [x for x in range(mid.width) if mid.getpixel((x, 21))[:3] == (255, 255, 255) and mid.getpixel((x, 21))[3] > 200]
    expect(len(dots) >= 3, 'the middle piece still draws the ellipsis glyph')


def search_tests(ctx):
    """The level: the keyboard asked for, Searching..., the rows, the thumbnails, No results, every failure, Not available, leaving mid-fetch."""
    expect = ctx.expect
    site = site_for()
    m = opened(site=site)
    calls = enter(m)
    expect(('window_open', 'm1plus_keyboard') in calls and at_search(m) and flags(m, 'ps_field')[0] == 1 and flags(m, 'pg_big')[0] == 0
           and m.props.get((m.widgets['label_title'], 'visible')) == 1 and text(m, 'label_title') == 'Apple Podcasts', 'a tap on Search: the level opens with the navbar title Apple Podcasts (no large one: the field keeps the keyboard page\'s place), the field (insensitive widgets), the keyboard is asked for at once; the Shows level\'s large title and buttons go')
    expect(('widget_set_tr_text', m.widgets['ps_hint'], 'Search Apple Podcasts') in m.calls or text(m, 'ps_hint') == 'Search Apple Podcasts', 'the field\'s hint reads Search Apple Podcasts')
    expect(m.props.get((m.sv, 'virtual_h')) == O['PQ_TOP'] and not hint(m), 'no results yet: the content is the field\'s height, no status line')
    # the keyboard's Back with nothing typed: the Shows level
    m.call(PSYMS['pg_srch_cancel'], count=4000000)
    expect(at_disc(m) and flags(m, 'ps_field')[0] == 0, 'the keyboard\'s Back with nothing typed: back on the Discover level it was entered from')
    magnifier(m)
    # a tap on the field opens the keyboard again
    m.calls = []
    PCP.tap(m, 150, O['PQ_FIELD_Y'] + O['PQ_FIELD_H'] // 2)
    expect(('window_open', 'm1plus_keyboard') in m.calls, 'a tap on the field opens the keyboard')
    # submit
    submit(m, 'all in')
    expect(m.thread is not None and hint(m) == 'Searching…' and hint(m) and text(m, 'ps_text') == 'all in' and flags(m, 'ps_hint')[0] == 0 and flags(m, 'ps_text')[0] == 1,
           'submit: one worker, the status line says Searching..., the field shows the term (the hint goes)')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.search_layout(0)['h'], 'while it searches: no rows')
    work(m)
    expect(site.log[0] == SEARCH + 'all%20in', f'the request: the term encoded ({site.log[0]})')
    tick(m)
    rows = level_rows(m)
    docs = json.loads(ALL_IN)['results']
    names = [d['collectionName'] for d in docs]
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.search_layout(25)['h'] and not hint(m), f'the answer: 25 rows ({m.props.get((m.sv, "virtual_h"))}), the status line gone')
    expect(flags(m, 'label_title')[0] == 1 and text(m, 'label_title') == 'Apple Podcasts' and flags(m, 'pg_big')[0] == 0, 'with the results shown the title Apple Podcasts is still there, as before the search')
    expect(all(same(r[0], n) for r, n in zip(rows, names)) and same(rows[0][1], docs[0]['artistName']) and len(rows) >= 5, f'rows: the show name and its author in grey ({rows[:2]})')
    # geometry of the first rows against the model
    _, texts, styles, fills = PCP.paint(m, 0)
    L = pod_show.search_layout(25)
    ttl = [r for (t, r), s in zip(texts, styles) if s == 'label_row_title'][:3]
    expect([r[1] for r in ttl] == [L['rows'][i] + O['LIST_TITLE_Y'] for i in range(3)] and ttl[0][0] == O['LIST_TEXT_X'], f'rows are the Downloads rows\' geometry from PQ_TOP ({ttl})')
    bl = PCP.paint(m, 0)[0]
    covers = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]
    expect(covers[:3] == [(O['LIST_ART_X'], L['rows'][i] + O['LIST_ART_Y'], O['LIST_ART'], O['LIST_ART']) for i in range(3)], f'a {O["LIST_ART"]} px cover at each row\'s place ({covers[:3]})')
    # thumbnails arrive one by one: the loader decodes the ones that came
    for i in range(25): m.images[f'file://{SDIR}/t{i}.jpg'] = (100, 100, bytes((i * 9 % 256, 80, 160, 255)) * 10000)
    settle(m)
    expect(len([u for u in m.loads if u.startswith(f'file://{SDIR}/t')]) >= 6 and all(u.startswith(f'file://{SDIR}/t') for u in m.loads if 'file://' in u and 'Podcasts' not in u), 'the thumbnails in view are decoded from the cache directory, one a tick')
    # a result with no feed address: Not available, dimmed, not tappable
    dead = dict(docs[0]); dead.pop('feedUrl'); dead['collectionName'] = 'Gone Show'
    ans = json.dumps({'resultCount': 2, 'results': [docs[1], dead]}).encode()
    m = opened(site=site_for(**{SEARCH + 'x': {'body': ans}}))
    stage(m, 'x')
    rows = level_rows(m)
    bl, texts, styles, fills = PCP.paint(m, 0)
    L = pod_show.search_layout(2)
    chev = [tuple(b[2]) for b in bl if tuple(b[1]) == (0, 0, 10, 16)]   # the shared chevron bitmap
    expect(chev == [(O['LIST_CHEV_X'], L['rows'][0] + (O['PC_ROW_H'] - 1 - 16) // 2, 10, 16)],
           f'a chevron on the available result only, none on the dimmed Not available row, which opens nothing ({chev})')
    expect(len(rows) == 2 and same(rows[0][0], names[1]) and same(rows[0][1], docs[1]['artistName']) and rows[1] == ('Gone Show', 'Not available') and (O['PQ_DIM'], 0, L['rows'][1], 320, O['PC_ROW_H'] - 1) in fills and not [f for f in fills if f[0] == O['PQ_DIM'] and f[2] == L['rows'][0]],
           f'a result with no feed: its grey line reads Not available and the row is dimmed; the other is not ({rows})')
    m.calls = []; m.thread = None
    PCP.tap(m, 150, L['rows'][1] + 30)
    expect(m.thread is None and at_search(m), 'a tap on the dimmed row does nothing')
    # no results
    m = opened(site=site_for(**{SEARCH + 'zzz': {'body': b'{"resultCount":0,"results":[]}'}}))
    stage(m, 'zzz')
    expect(hint(m) == 'No results' and hint(m) and m.props.get((m.sv, 'virtual_h')) == pod_show.search_layout(0)['h'], 'no results: the status line says so')
    # every failure, in the existing words
    for label, reply, word in (('no connection', {'rc': 6}, "Can't connect"), ('a certificate error', {'rc': 60}, 'Certificate problem'), ('HTTP 403', {'rc': 22, 'code': 403}, 'Server error'),
                               ('an HTML page', {'body': b'<html>x</html>'}, 'Server error')):
        m = opened(site=site_for(**{SEARCH + 'q': reply}))
        stage(m, 'q')
        expect(hint(m) == word and m.props.get((m.sv, 'virtual_h')) == pod_show.search_layout(0)['h'], f'{label}: "{word}"')
    for label, setup, word in (('no Wi-Fi', lambda m: setattr(m, 'wifi', -1), 'No Wi-Fi'), ('a clock never set', lambda m: setattr(m, 'wall', 1700000000), 'Set the date first'),
                               ('no CA bundle', lambda m: m.present.discard(PCN.CA), 'Certificates missing'), ('no card', lambda m: setattr(m, 'card_mounted', False), 'Storage unavailable')):
        m = opened()
        setup(m)
        enter(m); submit(m, 'q')
        expect(m.thread is None and hint(m) == word, f'{label}: the guard\'s words "{word}", no worker')
    # a failed search is asked again: the new answer replaces the words
    m = opened(site=site_for(**{SEARCH + 'q': {'rc': 6}}))
    stage(m, 'q')
    m.curl_site = site_for()
    submit(m, 'all in'); work(m); tick(m)
    expect(not hint(m) and len(level_rows(m)) >= 5, 'another search after a failure shows its rows')
    # Back leaves the level; the worker is told to stop; the thumbnails that were not fetched are not
    m = opened()
    enter(m); submit(m, 'all in')
    th = m.thread
    PCP.click(m, 'btn_return')
    expect(at_disc(m) and flags(m, 'ps_field')[0] == 0 and m.word(SE_CANCEL()) == 1, 'Back from the level while the worker runs: the Discover level, the worker is asked to stop')
    m.thread = th; work(m)
    expect(m.call(PSYMS['pn_search_state'], count=2000) == 3 and m.call(PSYMS['pn_search_code'], count=2000) == 12, 'the worker ends cancelled')
    # leaving after the answer came, mid-thumbnails: the thumbs stop at the cancel
    site = site_for()
    got = []
    def thumbs(url, o):
        got.append(url)
        if len(got) == 3: SE.cancel(m)
        return {'body': ART, 'chunk': 5500}
    m = opened(site=site_for(**{u: thumbs for u in [d['artworkUrl100'] for d in docs]}))
    enter(m); submit(m, 'all in'); th = m.thread
    m.thread = None
    m.call(th[0], a0=th[1], count=1 << 40)
    expect(len(got) == 3 and m.call(PSYMS['pn_job_busy'], count=2000) == 0 and not m.call(PSYMS['pn_search_thumb'], a0=2, a1=m.alloc(200), a2=200, count=100000), 'leaving mid-fetch: the fetching stops there, the third picture is none')
    # coming back to the level after a visit: the answer and the thumbnails that came are still there
    m = opened()
    stage(m, 'all in')
    PCP.click(m, 'btn_return'); magnifier(m)
    expect(len(level_rows(m)) >= 5 and text(m, 'ps_text') == 'all in' and not [c for c in m.calls if c == ('window_open', 'm1plus_keyboard')], 'Search again: the term and the rows of the last answer, no keyboard')
    # the window destroyed (the hardware Back key): the thumbnails and the held preview go, a running worker is told to stop
    expect(any(p.startswith(SDIR + '/t') for p in m.fs), 'the thumbnails are in the cache directory')
    fn_, ctx_ = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn_, a0=ctx_, a1=0, count=40000000)
    expect(not [p for p in m.fs if p.startswith(SDIR + '/')] and m.call(PSYMS['pn_search_count'], count=2000) == 0, 'the window destroyed: the cache directory is empty and the results are forgotten')
    m = opened()
    enter(m); submit(m, 'all in')
    fn_, ctx_ = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn_, a0=ctx_, a1=0, count=40000000)
    expect(m.word(SE_CANCEL()) == 1, 'destroyed while the worker runs: it is told to stop')


def SE_CANCEL():
    return PSYMS['pn'] + 20 + 12 * O['PC_MAX_SHOWS'] + 12


def input_tests(ctx):
    """What is typed: a term (URL-encoded UTF-8, CJK too), a feed address (the preview directly), an Apple Podcasts link (the lookup, then the preview)."""
    expect = ctx.expect
    site = site_for()
    m = opened(site=site)
    enter(m); submit(m, '日谈公园 a&b'); work(m)
    expect(site.log[0] == SEARCH + '%E6%97%A5%E8%B0%88%E5%85%AC%E5%9B%AD%20a%26b' and 'country=US' in site.log[0], f'a CJK term: the request has it percent-encoded ({site.log[0]})')
    # a feed address: no search, the feed is fetched
    for k in ('https://feeds.example/wsj', ):
        site = site_for()
        m = opened(site=site)
        enter(m); submit(m, k)
        expect(hint(m) == 'Loading…' and text(m, 'ps_text') == k and m.thread is not None, 'a feed address: Loading..., the worker is the preview\'s')
        work(m)
        expect(site.log[0] == F_WSJ and not [u for u in site.log if u.startswith(SEARCH)], 'the feed itself is requested, no search')
        tick(m)
        expect(text(m, 'label_title') == 'WSJ Minute Briefing' and flags(m, 'ps_field')[0] == 0, 'and its preview opens (the Show page)')
    # an Apple Podcasts link
    site = site_for(**{LOOKUP + '1493503146': {'body': SE.data('lookup_1493503146.json')}, 'https://feed.xyzfm.space/cv4bkgpuglwp': {'body': WSJ}})
    m = opened(site=site)
    enter(m); submit(m, 'https://podcasts.apple.com/us/podcast/x/id1493503146?i=5'); work(m)
    expect(site.log[:2] == [LOOKUP + '1493503146', 'https://feed.xyzfm.space/cv4bkgpuglwp'], f'an Apple link: the lookup of its id, then the feed it names ({site.log[:2]})')
    tick(m)
    expect(text(m, 'label_title') == 'WSJ Minute Briefing', 'then the preview')
    # a link whose show has no feed address
    m = opened(site=site_for(**{LOOKUP + '77': {'body': b'{"resultCount":1,"results":[{"collectionName":"No Feed"}]}'}}))
    enter(m); submit(m, 'https://podcasts.apple.com/us/podcast/x/id77'); work(m); tick(m)
    expect(toasts(m) == ["Can't subscribe: Not available"] and at_search(m) and not hint(m), f'a link with no feed: "Can\'t subscribe: Not available", the level stays ({toasts(m)})')
    # a feed address that fails
    for label, reply, word in (('a 404', {'rc': 22, 'code': 404}, 'Feed not found'), ('a 403', {'rc': 22, 'code': 403}, 'Server error'), ('an HTML page', {'body': b'<html>x</html>'}, 'Not a podcast feed'),
                               ('no connection', {'rc': 6}, "Can't connect")):
        m = opened(site=site_for(**{'https://bad.example/rss': reply}))
        enter(m); submit(m, 'https://bad.example/rss'); work(m); tick(m)
        got = toasts(m)
        shows, _ = m.shows()
        expect(got == [f"Can't subscribe: {word}"] and at_search(m) and len(shows) == 4 and not [d for d in m.dirs if d.startswith(RP + '/') and d.count('/') == 4 and 'bad' in d],
               f'{label}: "Can\'t subscribe: {word}", no folder was made ({got})')
    # a long feed address (the keyboard's KB_LONG takes up to 255 bytes): the preview fetches it whole; the field shows its start cut with an ellipsis
    site = site_for()
    m = opened(site=site)
    long = 'https://feeds.example/' + 'x' * 200
    enter(m); submit(m, long)
    expect(m.thread is not None and m.thread[0] == PSYMS['pn_pmain'] and text(m, 'ps_text').endswith('…') and text(m, 'ps_text').startswith('https://feeds'), 'a 222 byte address is taken: the preview starts, the field shows the start of it cut with an ellipsis')
    work(m)
    expect(site.log[0] == long, 'and the feed is requested at the whole address')


def preview_tests(ctx):
    """A result opens the Show page as a preview: the header, the greyed episodes, Subscribe; no sheets; Back returns to the results; Subscribe makes the show; already subscribed; the first fetch fails."""
    expect = ctx.expect
    first = json.loads(ALL_IN)['results'][0]['feedUrl']
    site = site_for(**{first: {'body': WSJ}})
    m = opened(site=site)
    stage(m, 'all in')
    L = pod_show.search_layout(25)
    PCP.tap(m, 150, L['rows'][0] + 30)
    expect(m.thread is not None and hint(m) == 'Loading…' and m.props.get((m.sv, 'virtual_h')) == pod_show.search_layout(0)['h'], 'a tap on a result: Loading..., the rows go while the preview is fetched')
    work(m)
    expect(site.log[-2] == first or first in site.log, 'the result\'s feed is fetched')
    tick(m)
    shows_before, _ = m.shows()
    expect(text(m, 'label_title') == 'WSJ Minute Briefing' and m.props.get((m.sv, 'yoffset'), 0) == 0 and flags(m, 'btn_more') == (0, 0)
           and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np' and not [d for d in m.dirs if d.startswith(RP + '/.pv')], 'the preview is the Show page: the show\'s title, no "..." (no sheets), no folder')
    h = PCP.hdr(m)
    _, texts, styles, fills = PCP.paint(m, 0)
    sub = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_ps_latest']
    font = PCS.sw().font()
    w, tx = pod_show.subscribe_pill(font, 'Subscribe')
    expect(sub and sub[0][0] == 'Subscribe' and sub[0][1][0] == (320 - w) // 2 + tx, f'the Latest Episode pill is Subscribe: its label centred in the pill ({sub})')
    names = [t for (t, r), s in zip(texts, styles) if s == 'label_ps_name']
    expect(names and names[0].startswith('WSJ'), 'the header: the show\'s name')
    # the episodes look like normal cells without the pill row: the date, the title in the normal colour, the description, no pill, no "...", no badge, no dimming, and they are shorter
    bl, texts2, styles2, fills = PCP.paint(m, h - 60)
    dots = [b for b in bl if b[1] == (0, O['PA_DOTS_Y'], O['PA_DOTS_PX'], O['PA_DOTS_PX'])]
    badges = [b for b in bl if b[1][2:] == (O['PA_BADGE_PX'], O['PA_BADGE_PX']) or b[1][:2] == (O['PA_CHECK'] * O['PA_G_PX'], O['PA_G_Y'])]
    by = {}
    for (t, r), s in zip(texts2, styles2): by.setdefault(s, []).append((t, r))
    ch = O['PS_PCELL_H']
    expect(not dots and not badges and not [f for f in fills if f[0] == O['PQ_DIM']] and 'label_ps_pill' not in by, 'no "...", no badge, no pill, no dimming')
    expect(by.get('label_ps_date') and by.get('label_ps_ctitle') and by.get('label_ps_cdesc') and not by.get('label_ps_cdim'), f'a date line, a title in the normal (not the played grey) style and a description: {sorted(by)}')
    ys = sorted(r[1] for t, r in by['label_ps_date'])
    expect(len(ys) >= 2 and all(b - a == ch for a, b in zip(ys, ys[1:])) and ch < O['PS_CELL_H'] and ch == O['PS_CDESC_Y'] + 2 * O['PS_CDESC_PITCH'] + 14, f'the cells are PS_PCELL_H = {ch} px apart, shorter than a normal cell ({O["PS_CELL_H"]}): no empty band ({ys})')
    expect(m.props.get((m.sv, 'virtual_h')) == h + 3 * ch + 20, 'the content is the header, three short cells and the air under them')
    # a tap on a cell, its right edge (the "..." place) and the pill's place do nothing
    m.thread = None; m.calls = []
    PCP.tap(m, 150, h + 12)
    expect(m.thread is None and not [c for c in m.calls if c[0] in ('pthread_create', 'navigator_to_with_context')] and ('widget_set_visible', m.widgets['pg_sh_card'], 1) not in m.calls
           and [t for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_head'], 'a tap on an episode opens its episode page (no pill, no "...": nothing to start, no sheet; pcdetail.py has the page)')
    PCP.tap(m, O['PS_DOTS_CX'], 300); PCP.tap(m, 30, 340)
    expect(m.thread is None and not [c for c in m.calls if c[0] in ('pthread_create', 'navigator_to_with_context')] and ('widget_set_visible', m.widgets['pg_sh_card'], 1) not in m.calls, 'on the preview\'s page the pill and "..." places are nothing: no download, no sheet')
    PCP.click(m, 'btn_return')   # Back: the list
    # Back: the results are as they were
    PCP.click(m, 'btn_return')
    expect(at_search(m) and len(level_rows(m)) >= 5 and text(m, 'ps_text') == 'all in' and m.call(PSYMS['pn_preview_parser'], count=2000) == 0, 'Back: the search level with its rows, the held feed let go')
    # Subscribe
    PCP.tap(m, 150, L['rows'][0] + 30); work(m); tick(m)
    hdr = PCP.paint(m, 0)
    y_latest = [r[1] for (t, r), s in zip(hdr[1], hdr[2]) if s == 'label_ps_latest'][0]
    PCP.tap(m, 160, y_latest + 10)
    shows, _ = m.shows()
    s = next((x for x in shows if x['feed'] == first), None)
    expect(s and s['dir'] == 'WSJ Minute Briefing' and f'{RP}/WSJ Minute Briefing/.episodes' in m.fs and f'{RP}/WSJ Minute Briefing/.show' in m.fs and f'{RP}/WSJ Minute Briefing/cover.jpg' in m.fs
           and not [p for p in m.fs if p.endswith('.tmp')], 'Subscribe makes the show: its folder named from the feed\'s title with .episodes, .show and cover.jpg')
    expect(text(m, 'label_title') == 'WSJ Minute Br…' and flags(m, 'btn_more') == (1, 1) and [t for (t, r), st in zip(*PCP.paint(m, 0)[1:3]) if st in ('label_ps_latest', 'label_ps_latestw')][0].startswith('Latest Episode'),
           'the page is now the normal Show page, in place: the "..." is back and the pill says Latest Episode')
    hh = PCP.hdr(m)
    _, t3, s3, f3 = PCP.paint(m, hh - 60)
    pills = [t for t, s in zip((t for t, r in t3), s3) if s == 'label_ps_pill']
    expect(pills and all(p.endswith('MB') or p == 'Download' for p in pills) and m.props.get((m.sv, 'virtual_h')) == hh + 3 * O['PS_CELL_H'] + O['PS_MORE_H'] + 20, f'the real cells: the download pills ({pills}) and the full cell height (and the See All row under them: the show has a feed)')
    PCP.click(m, 'btn_return')
    expect(at_search(m) and len(level_rows(m)) >= 5, 'its Back returns to the search results')
    PCP.click(m, 'btn_return')
    expect(at_disc(m), 'and the next Back to the Discover level')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and has_row(m), 'and the next to the Shows level')
    # already subscribed
    # a feed the card has already (a typed address, and a result): the real Show page of that show at once, nothing fetched, Back returns to the results
    site3 = site_for()
    m3 = opened(site=site3)
    enter(m3); submit(m3, 'https://f.example/alpha')
    expect(m3.thread is None and text(m3, 'label_title') == 'Alpha Show' and flags(m3, 'btn_more') == (1, 1) and not site3.log and not [p for p in m3.fs if p.startswith(f'{RP}/WSJ')],
           'a typed address of a show that is subscribed: its real Show page opens at once, no request, nothing created')
    hh = PCP.hdr(m3)
    lat = [t for (t, r), s in zip(*PCP.paint(m3, 0)[1:3]) if s in ('label_ps_latest', 'label_ps_latestw')]
    expect(not lat or lat[0].startswith('Latest Episode') and 'Subscribe' not in lat[0], f'its header pill is the normal Latest Episode pill, never Subscribe or Subscribed ({lat})')
    PCP.click(m3, 'btn_return')
    expect(at_search(m3), 'Back returns to the search level')
    sub_feed = PCS.F['alpha']
    ans = json.dumps({'resultCount': 1, 'results': [{'collectionName': 'Alpha Result', 'artistName': 'A', 'feedUrl': sub_feed, 'artworkUrl100': ''}]}).encode()
    m6 = opened(site=site_for(**{SEARCH + 'alpha': {'body': ans}}))
    stage(m6, 'alpha')
    m6.thread = None; m6.calls = []
    PCP.tap(m6, 150, pod_show.search_layout(1)['rows'][0] + 30)
    expect(m6.thread is None and text(m6, 'label_title') == 'Alpha Show' and flags(m6, 'btn_more') == (1, 1),
           'a result that is a show already opens the real Show page of that show without a fetch')
    d = PCP.hdr(m6)
    pl = [t for (t, r), s in zip(*PCP.paint(m6, d - 60)[1:3]) if s in ('label_ps_pill',)]
    expect(flags(m6, 'btn_more') == (1, 1), f'with the "..." (and the cells\' pills {pl})')
    PCP.click(m6, 'btn_return')
    expect(at_search(m6) and len(level_rows(m6)) == 1, 'Back: the results')
    # an Apple link that turns out to be a show already: after the lookup, the real page too
    site7 = site_for(**{sub_feed: {'body': WSJ}, LOOKUP + '77': {'body': json.dumps({'resultCount': 1, 'results': [{'collectionName': 'Alpha', 'feedUrl': sub_feed}]}).encode()}})
    m7 = opened(site=site7)
    enter(m7); submit(m7, 'https://podcasts.apple.com/us/podcast/x/id77'); work(m7); tick(m7)
    expect(text(m7, 'label_title') == 'Alpha Show' and flags(m7, 'btn_more') == (1, 1) and m7.call(PSYMS['pn_preview_parser'], count=2000) == 0, 'an Apple link of a show that is subscribed: the lookup, then its real page, the held feed dropped')
    # a failed first fetch makes nothing: no folder, the toast
    m4 = opened(site=site_for(**{first: {'rc': 22, 'code': 403}}))
    stage(m4, 'all in')
    PCP.tap(m4, 150, L['rows'][0] + 30); work(m4); tick(m4)
    expect(toasts(m4) == ["Can't subscribe: Server error"] and at_search(m4) and len(level_rows(m4)) >= 5 and not [p for p in m4.fs if p.startswith(f'{RP}/') and 'Briefing' in p],
           f'a 403 on the first fetch: "Can\'t subscribe: Server error", the results stay, no folder ({toasts(m4)})')
    # a failed write at Subscribe makes nothing
    m5 = opened(site=site_for(**{first: {'body': WSJ}}))
    stage(m5, 'all in')
    PCP.tap(m5, 150, L['rows'][0] + 30); work(m5); tick(m5)
    m5.fail.add(('open', f'{RP}/WSJ Minute Briefing/.show.tmp'))
    hdr = PCP.paint(m5, 0)
    PCP.tap(m5, 160, [r[1] for (t, r), s in zip(hdr[1], hdr[2]) if s == 'label_ps_latest'][0] + 10)
    expect(toasts(m5) == ["Can't subscribe: Storage unavailable"] and text(m5, 'label_title') == 'WSJ Minute Briefing' and not [p for p in list(m5.fs) + list(m5.dirs) if p.startswith(f'{RP}/WSJ')],
           f'a write that fails: "Can\'t subscribe: Storage unavailable", the preview stays, nothing is left on the card ({toasts(m5)})')


def job_tests(ctx):
    """One job at a time: a download that runs goes on beside the search; a refresh is waited for; a newer search cancels the running one."""
    expect = ctx.expect
    DL = sibling('pcdl')
    m = opened()
    # a download is running
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 2, seq=1)
    m.setword(DL.pn_at(DL.DKEY), DL.key_of('Sub One', 'a.mp3')); m.setword(DL.pn_at(DL.DBUSY), 1); m.setword(DL.pn_at(DL.DSEQ), 10)
    enter(m); submit(m, 'all in')
    expect(m.thread is not None and m.thread[0] == PSYMS['pn_smain'] and m.word(DL.pn_at(DL.DBUSY)) == 1 and DL.fn(m, 'pn_dl_running') == 1 and m.word(PSYMS['pn']) == 1 and hint(m) == 'Searching…',
           'a download runs: the search thread is created in the same submit ("Searching..."), the download thread keeps running, nothing is asked to pause')
    work(m); tick(m)
    expect(len(level_rows(m)) >= 5 and DL.fn(m, 'pn_dl_running') == 1, 'its rows come, the download thread still running')
    m.thread = None; m.calls = []
    tick(m)
    expect(m.thread is None and 'pthread_create' not in [c[0] for c in m.calls] and DL.fn(m, 'pn_dl_running') == 1, 'afterwards the tick starts nothing and stops nothing: the downloads were never paused')
    # a refresh in progress: the job waits, nothing is cancelled
    m = opened()
    m.setword(PSYMS['pn'], 1); m.setword(PSYMS['pn'] + 4, 0); m.setword(PSYMS['pn'] + 8, 3)   # busy (kind 0 counts as a refresh)
    enter(m); submit(m, 'q')
    expect(m.thread is None and m.word(SE_CANCEL()) == 0, 'a refresh in progress: the search waits and does not cancel it')
    # a newer search while one runs: the first is cancelled, the second starts at the next tick
    m = opened()
    enter(m); submit(m, 'first'); first = m.thread
    submit(m, 'second')
    expect(m.word(SE_CANCEL()) == 1 and hint(m) == 'Searching…', 'a new search while one runs: the running one is told to stop')
    m.thread = None; m.call(first[0], a0=first[1], count=1 << 40)
    tick(m)
    expect(m.thread is not None, 'and the new one starts at the next tick')


def off_tests(ctx):
    """The screen-off rule: no visual work while dark, the worker goes on; the level catches up at the first lit tick."""
    expect = ctx.expect
    m = opened()
    enter(m); submit(m, 'all in'); work(m)
    m.screen(False)
    m.calls = []
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_visible', 'widget_resize', 'widget_invalidate_force', 'widget_set_prop_int')]
           and m.call(PSYMS['pn_search_state'], count=2000) == 3, 'the answer is in while the screen is off: the tick does no widget work')
    m.calls = []
    m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'widget_load_image'], 'and the loader decodes nothing in the dark')
    tick(m)
    expect(len(level_rows(m)) >= 5, 'at the first lit tick the rows are there')
    # a job started and the screen turned off: the pending start waits for light, the finished one needs none
    m = opened()
    enter(m)
    m.screen(False)
    submit(m, 'q')
    expect(m.thread is not None, 'a search submitted starts at once (no light needed)')
    # preview: ready in the dark, opened when lit
    m = opened(site=site_for(**{F_WSJ: {'body': WSJ}}))
    enter(m); submit(m, F_WSJ); work(m)
    m.screen(False); m.calls = []
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(at_search(m), 'a preview that came in the dark is not opened in the dark')
    tick(m)
    expect(text(m, 'label_title') == 'WSJ Minute Briefing', 'and is at the first lit tick')


def width_tests(ctx):
    """The new strings in 13 languages: Subscribe / Subscribed pills fit the Latest Episode pill's room; the status words fit a line; Not available fits under a name."""
    expect = ctx.expect
    font = PCS.sw().font()
    px_latest = pod_show.PX['label_ps_latest']
    worst = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda k, t=t: pod_i18n.TEXT[k][t]
        for key in ('Subscribe',):
            w, tx = pod_show.subscribe_pill(font, tr(key))
            worst.append((w, loc, key))
            expect(w <= O['PS_LATEST_MAX'], f'{loc}: the {key} pill ({w} px) fits PS_LATEST_MAX')
        w = font.width(tr('Apple Podcasts'), 20)
        expect(w <= 200, f'{loc}: the keyboard page\'s title "Apple Podcasts" ({w} px of the 200 px title, 20 px) fits')
        for key in ('Search Apple Podcasts', 'Search Podcast Index'):
            w = font.width(tr(key), 18)
            expect(w + 4 <= O['PQ_TEXT_W'], f'{loc}: the field\'s hint "{tr(key)}" ({w} px + the label\'s 2 px margins) fits the {O["PQ_TEXT_W"]} px text room')
        w = font.width(tr('Podcast Index'), 20)
        expect(w <= 200, f'{loc}: the title "Podcast Index" ({w} px of the 200 px title, 20 px) fits')
        for key in ('Searching…', 'No results', 'Loading…', 'Not available'):
            w = font.width(tr(key), 18)
            expect(w <= 280, f'{loc}: "{tr(key)}" fits the status line ({w} px of 280)')
        w = font.width(tr('Not available'), O['LIST_SUB_PX'] if 'LIST_SUB_PX' in O else 18)
        expect(w <= O['LIST_TEXT_W'], f'{loc}: Not available fits the grey line of a row ({w} px of {O["LIST_TEXT_W"]})')
        for key in ('Storage unavailable', 'Certificates missing', 'Not a podcast feed', 'Feed not found', 'Certificate problem', 'Set the date first', 'Not available'):
            full = f"{tr(chr(67) + 'an' + chr(39) + 't subscribe')}: {tr(key)}"
            w = font.width(full, 18)
            w = w if w <= 300 else font.width(tr(key), 18)   # (the page drops the first half where it does not fit)
            w = w if w <= 300 else font.width(tr(chr(67) + 'an' + chr(39) + 't subscribe'), 18)   # (and then the second)
            expect(w <= 300, f'{loc}: the "Can\'t subscribe" toast for "{tr(key)}" fits one line ({w} px)')
    print('  widest Subscribe pill (px, max %d):' % O['PS_LATEST_MAX'], max(worst))
    assert px_latest


def field_tests(ctx):
    """The search fields: the level's field is the keyboard page's (the same rectangles, so the magnifier does not move when the keyboard page opens over it and the clear button appears); the
    magnifier is never moved or resized by the payload whatever the clear button does, in either field; the clear button's x is centred in its disc (measured on the committed picture)."""
    expect = ctx.expect
    import awtk_ui
    KB = sibling('keyboard')

    def tree(n): return awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui', n + '.bin'), 'rb').read())
    kb, ps = tree('m1plus_keyboard'), tree('m1plus_podcasts')
    box = lambda t, n: (t.find(n).x, t.find(n).y, t.find(n).w, t.find(n).h)
    kf, pf = kb.find('kb_field'), ps.find('ps_field')
    expect((kf.x, kf.w, kf.h) == (pf.x, pf.w, pf.h) and kf.y == O['PG_LIST_Y'] + pf.y, f'the level\'s field is the keyboard page\'s on the screen: x, width, height and y (window row {kf.y} = {O["PG_LIST_Y"]} + {pf.y})')
    expect(box(kb, 'kb_mag') == box(ps, 'ps_mag') and box(kb, 'kb_hint') == box(ps, 'ps_hint') and box(kb, 'kb_text') == box(ps, 'ps_text'), 'the magnifier, the hint and the text have the same rectangles in the field')
    kc = kb.find('kb_clear')
    expect(box(ps, 'ps_clear') == (kc.x + (kc.w - 16) // 2, (kc.h - 16) // 2, 16, 16) and ps.find('ps_clear').get('image') == 'qk_clear' and ps.find('ps_clear').get('sensitive') == 'false', 'the level\'s clear disc is where the keyboard page\'s is')
    pk = sys.modules['podtest_keyboard'].PK if 'podtest_keyboard' in sys.modules else None
    expect(pk is None or (pk.FIELD_X, pk.FIELD_W, pk.FIELD_MAG_X, pk.FIELD_TEXT_X, pk.FIELD_TEXT_W, pk.FIELD_CLEAR_X, pk.FIELD_CLEAR_W) == (O['PQ_FIELD_X'], O['PQ_FIELD_W'], O['PQ_MAG_X'], O['PQ_TEXT_X'], O['PQ_TEXT_W'], O['PQ_CLEAR_X'], O['PQ_CLEAR_W']),
           'patch/offsets.inc PQ_* are tools/pod_keyboard.py FIELD_*')
    # the keyboard page: typing (the clear button shows), deleting (it goes): the magnifier is never touched
    m = KB.opened()
    log = []
    for c in 'A':
        KB.typ(m, c); log += m.calls
    KB.typ(m, 'a'); log += m.calls
    KB.run_evt(m, 'kb_clear', O['EVT_CLICK']); log += m.calls
    mag = m.widgets['kb_mag']
    flips = [c for c in log if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == m.widgets['kb_clear']]
    expect(flips and not [c for c in log if len(c) > 1 and c[1] == mag and c[0] in ('widget_move', 'widget_resize', 'widget_set_visible', 'widget_set_prop_int', 'widget_set_prop_str', 'widget_set_text_utf8')],
           f'keyboard page: the clear button shows and hides ({len(flips)} calls) and nothing is ever done to the magnifier (its rectangle is the asset\'s, with and without the clear button)')
    # the level: a text (the clear disc shows), cleared by a tap on it (it goes), the magnifier untouched
    m = opened()
    enter(m)
    log = []
    submit(m, 'all in'); log += m.calls
    work(m); tick(m); log += m.calls
    expect(flags(m, 'ps_clear')[0] == 1 and flags(m, 'ps_hint')[0] == 0, 'the level: with a text the clear disc shows and the hint goes')
    m.thread = None
    PCP.tap(m, O['PQ_FIELD_X'] + O['PQ_CLEAR_X'] + 18, O['PQ_FIELD_Y'] + 18); log += m.calls
    expect(flags(m, 'ps_clear')[0] == 0 and flags(m, 'ps_hint')[0] == 1 and text(m, 'ps_text') == '' and m.props.get((m.sv, 'virtual_h')) == O['PQ_TOP']
           and any(c == ('window_open', 'm1plus_keyboard') for c in m.calls), 'a tap on the clear disc empties the field, drops the rows and opens the keyboard on the empty field')
    mag = m.widgets['ps_mag']
    expect(not [c for c in log if len(c) > 1 and c[1] == mag and c[0] in ('widget_move', 'widget_resize', 'widget_set_visible', 'widget_set_prop_int', 'widget_set_prop_str')], 'the level: nothing is done to the magnifier in either state')
    # a tap on the field's text (left of the clear disc) still opens the keyboard with the text
    m = opened(); stage(m, 'all in'); m.calls = []
    PCP.tap(m, 100, O['PQ_FIELD_Y'] + 18)
    expect(('window_open', 'm1plus_keyboard') in m.calls and text(m, 'ps_text') == 'all in', 'a tap on the text opens the keyboard and keeps the text')
    # the clear button's x in its disc, from the committed picture: the ink's centre against the disc's, within half a pixel, in x and y
    from PIL import Image
    import mod_icons
    path = os.path.join(mod_icons.PNG, 'qk_clear.png')
    im = Image.open(path).convert('RGBA')
    fill = mod_icons.KB_CLEAR[5]
    sx = sy = tot = 0.0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            if a < 250: continue
            w = max(0, fill[0] - r) / (fill[0] - 0x1c)
            sx += w * (x + .5); sy += w * (y + .5); tot += w
    cx, cy = sx / tot, sy / tot
    expect(open(path, 'rb').read() == open(asset_path('qk_clear'), 'rb').read() and tot > 5 and abs(cx - im.width / 2) <= 0.5 and abs(cy - im.height / 2) <= 0.5,
           f'qk_clear.png is committed and its x is centred in the disc: ink centre ({cx:.2f}, {cy:.2f}) against ({im.width / 2}, {im.height / 2})')


def directory_tests(ctx):
    """Podcast Directory (docs/modules/podcasts.md "Podcast Directory") on the search level: with Podcast Index chosen the navbar title, the field's hint and the keyboard's title say Podcast Index, and the request goes to
    api.podcastindex.org only; with Apple Podcasts (the default) they say Apple Podcasts and the request is the store's. The Discover row's grey Apple Podcasts stays (the charts are the store's)."""
    expect = ctx.expect
    IDX = 'https://api.podcastindex.org/search?limit=25&term='
    for choice, title, hint_, first in ((b'1\n', 'Podcast Index', 'Search Podcast Index', IDX + 'all%20in'), (b'0\n', 'Apple Podcasts', 'Search Apple Podcasts', SEARCH + 'all%20in'), (None, 'Apple Podcasts', 'Search Apple Podcasts', SEARCH + 'all%20in')):
        site = site_for(**{IDX + 'all%20in': {'body': ALL_IN}})
        m = opened(site=site)
        if choice is not None: m.fs['/mnt/data/m1plus/podcast-directory'] = choice
        calls = enter(m)
        expect(('window_open', 'm1plus_keyboard') in calls and flags(m, 'ps_field')[0] == 1 and text(m, 'label_title') == title and ('widget_set_tr_text', m.widgets['ps_hint'], hint_) in m.calls, f'{choice!r}: the level opens with the title {title} and the hint {hint_}')
        submit(m, 'all in'); work(m); tick(m)
        expect(site.log[0] == first and len([u for u in site.log if u.startswith((SEARCH, IDX))]) == 1 and text(m, 'label_title') == title, f'{choice!r}: only the chosen directory is asked, the title stays {title} ({site.log[:2]})')


def dirchange_tests(ctx):
    """The directory changes (Settings > Library > Podcasts > Directory) while the search level has an answer: coming back to the level in place, or leaving it and entering it again, shows the new directory's title and
    hint, drops the old answer and asks the chosen directory once for the same text (none to the old one); a job still running for the old one never lands as the new one's rows."""
    expect = ctx.expect
    IDX = 'https://api.podcastindex.org/search?limit=25&term='
    ONLY = json.dumps({'resultCount': 1, 'results': [{'collectionId': 9, 'collectionName': 'Idx Only', 'artistName': 'A', 'feedUrl': 'https://feeds.example/idx', 'artworkUrl100': ''}]}).encode()
    F = '/mnt/data/m1plus/podcast-directory'
    names = {'Apple Podcasts': (b'0\n', SEARCH), 'Podcast Index': (b'1\n', IDX)}

    def fg(m): m.fire(O['EVT_WINDOW_TO_FG'])

    def setup(first):
        site = site_for(**{IDX + 'all%20in': {'body': ONLY}})
        m = opened(site=site)
        m.fs[F] = names[first][0]
        enter(m)
        submit(m, 'all in'); work(m); tick(m)
        return m, site

    for first, second in (('Apple Podcasts', 'Podcast Index'), ('Podcast Index', 'Apple Podcasts')):
        for how in ('in place', 'leave and enter'):
            m, site = setup(first)
            expect(site.log[0] == names[first][1] + 'all%20in' and text(m, 'label_title') == first, f'{first}: the first search is its own')
            m.fs[F] = names[second][0]
            site.log.clear()
            if how == 'in place': fg(m)
            else:
                PCP.click(m, 'btn_return'); tick(m); magnifier(m)
            expect(text(m, 'label_title') == second and ('widget_set_tr_text', m.widgets['ps_hint'], 'Search ' + second) in m.calls or text(m, 'ps_hint') == 'Search ' + second,
                   f'{first} -> {second}, {how}: the title and the hint follow')
            expect(hint(m) == 'Searching…' and m.thread is not None and not [r for r in level_rows(m)], f'{first} -> {second}, {how}: the old rows are gone and the same text is searched again')
            work(m); tick(m)
            asked = [u for u in site.log if u.startswith((SEARCH, IDX))]
            expect(asked == [names[second][1] + 'all%20in'], f'{first} -> {second}, {how}: exactly one request, to {second}, for the same term ({asked})')
            rows = level_rows(m)
            expect(text(m, 'ps_text') == 'all in' and (rows[0][0] == 'Idx Only' if second == 'Podcast Index' else bool(rows) and rows[0][0] != 'Idx Only'), f'{first} -> {second}, {how}: the rows are {second}\'s ({rows[:1]})')
    # a job that still runs for the old directory
    for first, second in (('Apple Podcasts', 'Podcast Index'), ('Podcast Index', 'Apple Podcasts')):
        site = site_for(**{IDX + 'all%20in': {'body': ONLY}})
        m = opened(site=site)
        m.fs[F] = names[first][0]
        enter(m)
        submit(m, 'all in')
        old, m.thread = m.thread, None
        m.fs[F] = names[second][0]
        fg(m)
        PCN.work(m, old)   # the old worker ends with its answer
        for _ in range(3):
            tick(m)
            if m.thread: work(m)
        tick(m)
        rows = level_rows(m)
        expect(text(m, 'label_title') == second and (rows and rows[0][0] == 'Idx Only' if second == 'Podcast Index' else bool(rows) and rows[0][0] != 'Idx Only') and [u for u in site.log if u.startswith((SEARCH, IDX))][-1].startswith(names[second][1]),
               f'{first} -> {second} while the first search runs: its answer is not shown, the rows are {second}\'s ({rows[:1]}, {site.log[:3]})')


def dirchange_url_tests(ctx):
    """A feed address or an Apple Podcasts link in the field is no directory term: a change of Directory behind its preview (Back) or behind the level (to-foreground), or while its feed is fetched, cancels,
    fetches and reopens nothing; the level shows as it did, with the title and hint of the new choice."""
    expect = ctx.expect
    ILOOK = 'https://api.podcastindex.org/lookup?entity=podcast&id='
    F = '/mnt/data/m1plus/podcast-directory'
    names = {'Apple Podcasts': b'0\n', 'Podcast Index': b'1\n'}
    link = 'https://podcasts.apple.com/us/podcast/x/id1493503146?i=5'
    lookup = {'body': SE.data('lookup_1493503146.json')}
    extra = {LOOKUP + '1493503146': lookup, ILOOK + '1493503146': lookup, 'https://feed.xyzfm.space/cv4bkgpuglwp': {'body': WSJ}}

    def fg(m): m.fire(O['EVT_WINDOW_TO_FG'])

    for first, second in (('Apple Podcasts', 'Podcast Index'), ('Podcast Index', 'Apple Podcasts')):
        for text_ in (F_WSJ, link):
            site = site_for(**extra)
            m = opened(site=site)
            m.fs[F] = names[first]
            enter(m); submit(m, text_); work(m); tick(m)
            expect(text(m, 'label_title') == 'WSJ Minute Briefing' and flags(m, 'ps_field')[0] == 0, f'{first}: {text_[:30]}: the preview is open')
            m.fs[F] = names[second]
            site.log.clear()
            PCP.click(m, 'btn_return'); tick(m)
            expect(not site.log and m.thread is None and flags(m, 'ps_field')[0] == 1 and text(m, 'label_title') == second and text(m, 'ps_text') == (text_ if len(text_) < 40 else text(m, 'ps_text'))
                   and (('widget_set_tr_text', m.widgets['ps_hint'], 'Search ' + second) in m.calls or text(m, 'ps_hint') == 'Search ' + second),
                   f'{first} -> {second}, Back from the preview of {text_[:30]}: the level, the new title and hint, no request, nothing started ({site.log})')
            fg(m); tick(m)
            expect(not site.log and m.thread is None and text(m, 'label_title') == second, 'and a to-foreground again does nothing more')
            # to-foreground in place, the level in front with the address in the field
            site = site_for(**extra)
            m = opened(site=site)
            m.fs[F] = names[first]
            enter(m); submit(m, text_); work(m); tick(m)
            PCP.click(m, 'btn_return'); tick(m)
            site.log.clear()
            m.fs[F] = names[second]
            fg(m); tick(m)
            expect(not site.log and m.thread is None and flags(m, 'ps_field')[0] == 1 and text(m, 'label_title') == second, f'{first} -> {second}, to-foreground in place with {text_[:30]} in the field: no request, the new title')
        # the feed is being fetched when the choice changes: it is not cancelled
        site = site_for(**extra)
        m = opened(site=site)
        m.fs[F] = names[first]
        enter(m); submit(m, F_WSJ)
        m.fs[F] = names[second]
        fg(m)
        work(m); tick(m)
        expect(site.log[:1] == [F_WSJ] and text(m, 'label_title') == 'WSJ Minute Briefing', f'{first} -> {second}: a feed fetch that runs when the choice changes is not cancelled, the preview opens')


def dirchange_table_tests(ctx):
    """The invariant of the search level (patch/podcasts.c pg_srch_dir_sync): its rows are the chosen directory's answer or there are none. Driven as a table: the held rows (none, or a term's from directory A) x the
    field's text when the level comes back (empty, the same term, a feed address, an Apple Podcasts link) x how it comes back (Back from the preview, to-foreground in place, leave and enter again) x the direction.
    After each: the title and hint are B's, no row of A's answer is shown, one search to B for a term and no request at all otherwise, no preview reopened; then the old term typed again searches B once."""
    expect = ctx.expect
    IDX = 'https://api.podcastindex.org/search?limit=25&term='
    ILOOK = 'https://api.podcastindex.org/lookup?entity=podcast&id='
    F = '/mnt/data/m1plus/podcast-directory'
    ONLY = json.dumps({'resultCount': 1, 'results': [{'collectionId': 9, 'collectionName': 'Idx Only', 'artistName': 'A', 'feedUrl': 'https://feeds.example/idx', 'artworkUrl100': ''}]}).encode()
    link = 'https://podcasts.apple.com/us/podcast/x/id1493503146?i=5'
    lookup = {'body': SE.data('lookup_1493503146.json')}
    extra = {IDX + 'all%20in': {'body': ONLY}, LOOKUP + '1493503146': lookup, ILOOK + '1493503146': lookup, 'https://feed.xyzfm.space/cv4bkgpuglwp': {'body': WSJ}}
    dirs = {'Apple Podcasts': (b'0\n', SEARCH), 'Podcast Index': (b'1\n', IDX)}

    def fg(m): m.fire(O['EVT_WINDOW_TO_FG'])

    def settle(m):
        for _ in range(3):
            tick(m)
            if m.thread: work(m)
        tick(m)

    def searches(site): return [u for u in site.log if u.startswith((SEARCH, IDX))]

    def own(rows, name):   # the rows are B's answer: Index has one row, Apple's has the first of the sample
        return bool(rows) and (rows[0][0] == 'Idx Only') == (name == 'Podcast Index')

    for A, B in (('Apple Podcasts', 'Podcast Index'), ('Podcast Index', 'Apple Podcasts')):
        for held in ('none', 'rows'):
            for now in ('empty', 'term', 'feed', 'link'):
                for how in ('back', 'fg', 'reenter'):
                    if (held == 'none' and now == 'term') or (held == 'rows' and now == 'empty') or (how == 'back' and now in ('empty', 'term')): continue
                    tag = f'{A} -> {B}, held {held}, field {now}, return {how}'
                    site = site_for(**extra)
                    m = opened(site=site)
                    m.fs[F] = dirs[A][0]
                    enter(m)
                    if held == 'rows':
                        submit(m, 'all in'); settle(m)
                        expect(own(level_rows(m), A), f'{tag}: the rows are {A}\'s to begin with')
                    if now in ('feed', 'link'):
                        submit(m, F_WSJ if now == 'feed' else link); settle(m)
                        expect(text(m, 'label_title') == 'WSJ Minute Briefing', f'{tag}: the preview is open')
                        if how != 'back': PCP.click(m, 'btn_return'); tick(m)
                    m.fs[F] = dirs[B][0]
                    site.log.clear()
                    if how == 'back': PCP.click(m, 'btn_return')
                    elif how == 'fg': fg(m)
                    else:
                        PCP.click(m, 'btn_return'); tick(m)
                        site.log.clear()
                        magnifier(m)
                    settle(m)
                    rows = level_rows(m)
                    want = 1 if now == 'term' else 0
                    expect(text(m, 'label_title') == B and (('widget_set_tr_text', m.widgets['ps_hint'], 'Search ' + B) in m.calls or text(m, 'ps_hint') == 'Search ' + B or now != 'empty'),
                           f'{tag}: the title is {B}')
                    expect(not (rows and not (now == 'term' and own(rows, B))) and 'No results' != hint(m), f'{tag}: no row of {A}\'s answer is shown ({rows[:1]}, {hint(m)})')
                    asked = searches(site)
                    expect(asked == ([dirs[B][1] + 'all%20in'] if want else []) and not [u for u in site.log if u == F_WSJ or u.endswith('cv4bkgpuglwp') or '/lookup' in u],
                           f'{tag}: {"one search to " + B if want else "no request"} ({site.log[:3]})')
                    expect(flags(m, 'ps_field')[0] == 1, f'{tag}: the level is shown, no preview reopened')
                    # the old term typed again asks B, once
                    site.log.clear()
                    submit(m, 'all in'); settle(m)
                    expect(searches(site) == [dirs[B][1] + 'all%20in'] and own(level_rows(m), B), f'{tag}: the term typed again searches {B} once ({searches(site)})')
    # the exact sequence of the finding: a term on A, a feed address (its preview), the choice changed, Back
    site = site_for(**extra)
    m = opened(site=site)
    m.fs[F] = b'0\n'
    enter(m); submit(m, 'all in'); settle(m)
    submit(m, F_WSJ); settle(m)
    m.fs[F] = b'1\n'
    PCP.click(m, 'btn_return'); settle(m)
    expect(text(m, 'label_title') == 'Podcast Index' and not level_rows(m), 'the finding: the Apple rows are not shown under Podcast Index after Back from the feed\'s preview')
    # a term search still running when the choice changes is cancelled and never shown; a feed fetch is not
    for A, B in (('Apple Podcasts', 'Podcast Index'), ('Podcast Index', 'Apple Podcasts')):
        site = site_for(**extra)
        m = opened(site=site)
        m.fs[F] = dirs[A][0]
        enter(m); submit(m, 'all in')
        old, m.thread = m.thread, None
        m.fs[F] = dirs[B][0]
        fg(m)
        PCN.work(m, old)
        settle(m)
        expect(own(level_rows(m), B) and searches(site)[-1].startswith(dirs[B][1]), f'{A} -> {B}: a term search in flight is stopped, its answer is never shown')
        site = site_for(**extra)
        m = opened(site=site)
        m.fs[F] = dirs[A][0]
        enter(m); submit(m, 'all in'); settle(m)
        submit(m, F_WSJ)
        m.fs[F] = dirs[B][0]
        fg(m); settle(m)
        expect(F_WSJ in site.log and text(m, 'label_title') == 'WSJ Minute Briefing', f'{A} -> {B}: a feed fetch in flight is not cancelled')


SECTIONS = [entry_tests, search_tests, input_tests, preview_tests, job_tests, off_tests, width_tests, field_tests, directory_tests, dirchange_tests, dirchange_url_tests, dirchange_table_tests]

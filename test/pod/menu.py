"""The entry hook and the M1+ Music menu: the Home icon dispatcher, the kill switch, the row actions, hit tests on the menu."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


def entry_tests(ctx):
    expect, page = ctx.expect, ctx.page
    entry = PSYMS['m1plus_home_click']
    binds = 3 + len(page.rows)                  # btn_return, btn_backtoplayer, each row, and the foreground handler that arranges the menu again
    # 1. Entry icon, kill switch absent: opens the entry page, binds its widgets, no stock.
    m = Machine()
    m.widgets = {n: 0x30000000 + i for i, n in enumerate(
        ['btn_return', 'btn_backtoplayer', 'label_info'] + [f'pod_row{i}' for i in range(len(page.rows))])}
    v = m.call(entry, a0=m.icon(str(pod_pages.HOME_ENTRY)))
    names = m.names()
    expect(('window_open', page.key) in m.calls, f'entry opens {page.key}')
    expect('stock_resume' not in names, 'entry does not fall through to stock')
    expect(names.count('widget_on') == binds, f'binds navbar + {len(page.rows)} rows + the foreground handler (got {names.count("widget_on")})')
    expect('widget_set_text_utf8' not in names, 'the menu sets no info text')
    expect(v == 0, 'entry returns 0 (handled)')

    # 2. Non-entry icons: straight to stock through the trampoline, no page opened. id 0 is the
    #    HiFi store (Simplified Chinese only) and must no longer trigger M1+ Music.
    for other in ('5', '0'):
        if other == str(pod_pages.HOME_ENTRY): continue
        m = Machine()
        m.call(entry, a0=m.icon(other))
        expect(('stock_resume', other) in m.calls, f'non-entry id {other} falls through to stock')
        expect('window_open' not in m.names(), f'non-entry id {other} opens no page')

    # 3. Kill switch present: entry icon falls through to stock.
    m = Machine(); m.present = {'/mnt/mmc/m1plus-off'}
    m.call(entry, a0=m.icon(str(pod_pages.HOME_ENTRY)))
    expect('stock_resume' in m.names(), 'kill switch -> stock')
    expect('window_open' not in m.names(), 'kill switch opens no page')

    # 4. window_open fails: entry icon falls through to stock.
    m = Machine(); m.window = 0
    m.call(entry, a0=m.icon(str(pod_pages.HOME_ENTRY)))
    expect(('window_open', page.key) in m.calls, 'page open attempted')
    expect('stock_resume' in m.names(), 'open failure -> stock')

    # 5. Empty / null name: no crash, straight to stock.
    m = Machine(); m.call(entry, a0=m.icon(''))
    expect('window_open' not in m.names(), 'empty name opens no page')
    m = Machine(); m.call(entry, a0=0)
    expect('window_open' not in m.names() and 'stock_resume' in m.names(), 'null icon falls through to stock')

    # 6. A menu row: ACT_HOME row opens the stock destination via the trampoline with its id.
    on_row = PSYMS['on_row']; rows0 = PSYMS['pod_rows_0']
    by_action = {}
    for i, r in enumerate(page.rows): by_action.setdefault(r.action, i)
    genres = next(i for i, r in enumerate(page.rows)
                  if r.action == pod_pages.ACT_ARTISTS and r.arg == pod_pages.HOME_GENRE)
    m = artists_machine()
    m.call(on_row, a0=rows0 + 12 * genres, count=5000000)
    expect(('window_open', 'm1plus_artists') in m.calls and 'stock_resume' not in m.names(), 'Genres row opens our Artists page (test/pod/artists.py), not its stock Home id')
    comp = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_ARTISTS and r.arg == pod_pages.HOME_COMPOSER)
    m = artists_machine()
    m.call(on_row, a0=rows0 + 12 * comp, count=5000000)
    expect(('window_open', 'm1plus_artists') in m.calls and 'stock_resume' not in m.names(), 'Composers row opens our Artists page too')
    m = Machine()
    m.call(on_row, a0=rows0 + 12 * by_action[pod_pages.ACT_PLAYER])
    expect('on_backtoplayer_onclick' in m.names(), 'Now Playing row calls the player')

    # 7. The menu: every row is hit by a touch on it, through the list_view/scroll_view.
    m = Machine()
    menu = asset_tree(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_menu.bin'))
    sv = node(menu, 'pod_scrollview')
    rows = [c for c in sv.children if c.name.startswith('pod_row')] if sv else []   # (the menu also has the spacer row pod_pad, patch/minibar.c)
    lv = node(menu, 'pod_listview')
    visible = [r for r in rows if 50 + r.y + r.h // 2 < CLIENT_H]
    for i, r in enumerate(visible):
      for x in (160, 32):     # 32: on the row icon, when it has one (insensitive: the touch goes to the row)
        got = stock_target(m, menu, x, 50 + r.y + r.h // 2)
        expect(f'pod_row{i}' in got and 'pod_scrollview' in got and 'pod_icon' not in got,
               f'menu row {i} is hit through the scroll view ({got})')
    expect(len(rows) == len(page.rows), 'every menu row is in the scroll view')
    expect(lv and lv.y + lv.h == CLIENT_H, 'the menu list ends at the window bottom (450), not off-screen')
    content = max(r.y + r.h for r in rows)
    expect(content > sv.h and len(visible) < len(rows),
           f'{len(rows)} 52 px rows ({content} px) overflow the 400 px list, so it scrolls')
    expect(node(menu, 'scroll_bar_m') is not None, 'the stock scroll bar is there when the list scrolls')

    # 8. Extras (iPod style): one menu row before Settings opens a page of the stock Home tiles the menu does not
    #    repeat. Each row opens its stock destination through the dispatcher with its Home id, as Songs does.
    P = pod_pages
    labels = [r.label for r in page.rows]
    expect(labels[-7:] == ['Settings', 'Pod', 'Podcasts', 'Search', 'Radio', 'Navidrome', 'Extras'] and labels.index('Artists') < labels.index('Extras'),
           'the menu ends with Settings, Pod, Podcasts, Search, Radio, Navidrome, Extras; the library rows come first')
    ex_i = labels.index('Extras')
    ex = P.EXTRAS_PAGE
    n_items = 9    # the menu items proper; the nine stock Home tiles follow them among the items
    expect(len(P.ITEMS) == 24 and len(page.rows) == 25 and ex_i == 24 and P.ITEMS[P.SETTINGS_ID].label == 'Settings' and not any(r.label == 'Screenshot' for r in P.ITEMS),
           'twenty-four items (nine menu items, nine stock tiles, Settings, Pod, Podcasts, Search, Radio, Navidrome; no Screenshot), then Extras')
    expect(page.rows[ex_i].action == P.ACT_PAGE and P.PAGES[page.rows[ex_i].arg] is ex, 'the Extras row opens the Extras page')
    want = [('Favorites', 10), ('Recently Added', 13), ('Recently Played', 12), ('Most Played', 11), ('Composers', 8),
            ('Hi-Res', 9), ('Update Library', 2), ('Tidal', 1), ('CD Ripper', 15)]
    stock = ex.rows[n_items:n_items + 9]
    lists = ('Favorites', 'Recently Added', 'Recently Played', 'Most Played', 'Hi-Res')   # the song lists: our Songs page (ACT_LIST), the tile its fallback
    expect([(r.label, r.arg) for r in stock] == want and all(r.action == (P.ACT_LIST if r.label in lists else P.ACT_ARTISTS if r.label == 'Composers' else P.ACT_HOME) for r in stock),
           'the items after the menu\'s own nine are the nine stock Home tiles by id (the five song lists on our Songs page, Composers on our Artists page)')
    expect([(r.label, r.action, r.arg) for r in ex.rows] == [(r.label, r.action, r.arg) for r in P.ITEMS]
           and [(r.label, r.action, r.arg) for r in page.rows[:24]] == [(r.label, r.action, r.arg) for r in P.ITEMS],
           'Extras and the menu have a row for every item (same labels and actions), so an item opens the same way from either')
    homes = [r.arg for r in P.ITEMS if r.action in (P.ACT_HOME, P.ACT_LIST) or (r.action == P.ACT_ARTISTS and r.arg)] + [r.arg for r in P.SETTINGS_PAGE.rows if r.action == P.ACT_HOME]
    expect(len(set(homes)) == len(homes) and len(homes) + 6 == 18,
           'no tile is twice (Albums, id 5, Artists, id 6, Songs, id 3, Folders, id 4, and Playlists, id 14, are the payload pages; HiFi, id 0, is left out)')
    m = Machine()
    m.widgets = {n: 0x30000000 + i for i, n in enumerate(['btn_return', 'btn_backtoplayer', 'btn_settings'] + [f'pod_row{i}' for i in range(len(ex.rows))])}
    m.call(on_row, a0=rows0 + 12 * ex_i)
    expect(('window_open', ex.key) in m.calls and m.names().count('widget_on') == 4 + len(ex.rows),
           'the Extras row opens m1plus_extras and binds the navbar (Back, Now Playing, Settings), its twenty rows and the destroy handler that tells Shanling Home it is gone (home_extras_opened)')
    # the navbar's Settings button opens the Settings page, as the Settings row of the menu does (open_page, so Shanling Home's exit knows the page)
    cust_w = m.widgets['btn_settings']
    expect((cust_w, O['EVT_CLICK']) in m.bound, 'the Extras page binds a click on btn_settings')
    m.calls = []
    fn, fctx = m.bound[(cust_w, O['EVT_CLICK'])]
    m.call(fn, a0=fctx, a1=0, count=5000000)
    expect(('window_open', P.SETTINGS_PAGE.key) in m.calls and m.names().count('window_open') == 1 and m.names().count('widget_on') >= 2 + len(P.SETTINGS_PAGE.rows),
           'a tap on the Settings button opens m1plus_settings and binds its navbar and rows')
    m2 = Machine(); m2.widgets = {n: 0x30000000 + i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(ex.rows))])}
    m2.call(on_row, a0=rows0 + 12 * ex_i)
    expect(('window_open', ex.key) in m2.calls and 'btn_settings' not in m2.widgets and m2.names().count('widget_on') == 3 + len(ex.rows),
           'an Extras asset without the button (not ours) opens as before, nothing else bound (stock-safe)')
    rows_ex = PSYMS[f'pod_rows_{P.EXTRAS_PAGE_INDEX}']
    for i, (name, hid) in enumerate(want):
        m = Machine()
        m.call(on_row, a0=rows_ex + 12 * (n_items + i), count=5000000)
        if name in lists or name == 'Composers':
            win = 'm1plus_artists' if name == 'Composers' else 'm1plus_songs'
            expect(('window_open', win) in m.calls and (win == 'm1plus_songs' or 'window_open' in m.names()), f'Extras > {name} opens our {"Artists" if name == "Composers" else "Songs"} page')
            m = Machine(); m.windows[win] = 0
            m.call(on_row, a0=rows_ex + 12 * (n_items + i), count=5000000)
            expect(('stock_resume', str(hid)) in m.calls, f'Extras > {name}: a window that will not open leaves Home id {hid}')
        else:
            expect(('stock_resume', str(hid)) in m.calls and 'window_open' not in m.names(), f'Extras > {name} opens Home id {hid}')
    m = Machine(); m.present = {'/mnt/mmc/m1plus-off'}
    m.call(entry, a0=m.icon(str(P.HOME_ENTRY)))
    expect('window_open' not in m.names(), 'kill switch: neither the menu nor Extras opens')
    path = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_extras.bin')
    asset = asset_tree(path)
    ex_rows = [c for c in node(asset, 'pod_scrollview').children if c.name.startswith('pod_row')]   # (and the four section headers, pod_hdr0..3)
    icons = [r for r in awtk_ui.parse(open(path, 'rb').read()).walk() if r.name == 'pod_icon']
    expect(len(ex_rows) == 24 and len(icons) == 24, 'twenty-four Extras rows, each with its icon disc')
    header_asset_tests(ctx, awtk_ui.parse(open(path, 'rb').read()), 'Extras')
    m = Machine()
    for i, r in enumerate([c for c in ex_rows if 50 + c.y + c.h // 2 < CLIENT_H]):
        got = stock_target(m, asset, 160, 50 + r.y + r.h // 2)
        expect(f'pod_row{i}' in got and 'pod_icon' not in got, f'Extras row {i} is hit through the scroll view ({got})')


def addresses():
    """(entry, on_row, rows0): the payload's Home click, row handler and menu row table."""
    return PSYMS['m1plus_home_click'], PSYMS['on_row'], PSYMS['pod_rows_0']


# ---------------------------------------------------------------------------
# The customisable menu (patch/menu.c): the saved list, the arrangement of the stock list's rows, the Main Menu page.
MENU_FILE, MENU_TMP = '/mnt/data/m1plus/home-menu', '/mnt/data/m1plus/home-menu.tmp'
UI = os.path.join('rootfs', 'release/assets/default/raw/ui')


def page_machine(rows, extra=(), hdrs=True):
    """A machine whose window has the navbar buttons, the stock list and `rows` pod_row widgets (and `extra` names)."""
    m = Machine()
    names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_row{i}' for i in range(rows)] + list(extra) + (HDRS if hdrs else [])
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(names)}
    m.widgets['pod_scrollview'] = m.alloc(0x180)   # the payload looks at the scroll_view's vtable word and paint hook (zeros: not a list_view's)
    return m


HDRS = [f'pod_hdr{g}' for g in range(len(pod_pages.EXTRAS_GROUPS))]   # the Extras pages' section headers


def extras_state(m, row_ids):
    """[(kind, key, y)] of the shown children of an Extras-style page top to bottom, as the payload's calls left them: a header shown is visible, a row visible and sensitive."""
    out = []
    for g, name in enumerate(HDRS):
        h = m.widgets.get(name)
        if h is not None and m.props.get((h, 'visible')): out.append(('hdr', g, m.props.get((h, 'y'), 0)))
    for i in row_ids:
        h = m.widgets.get(f'pod_row{i}')
        if h is not None and m.props.get((h, 'visible')) and m.props.get((h, 'sensitive'), 1): out.append(('row', i, m.props.get((h, 'y'), 0)))
    return sorted(out, key=lambda t: t[2])


def extras_ok(m, data, cfg=False):
    """The Extras page (cfg False) or Settings > Extras (cfg True) the payload arranged for the saved list `data` against the Python model (pod_pages.extras_display /
    extras_layout): the shown children and their y, the hidden ones (headers and rows) hidden, insensitive and parked at y 0, every header insensitive, the children
    stacked shown first then the hidden headers then the hidden rows, and virtual_h. Returns '' or what differs."""
    P = pod_pages
    ids, off = P.parse_menu_full(data)
    shown, hidden = P.extras_display(ids, off, cfg)
    lay, height = P.extras_layout(shown, pod_ui.ROW_H)
    row_ids = [i for i in range(len(P.ITEMS)) if not (cfg and i == P.SETTINGS_ID)]
    name = lambda kind, key: f'pod_hdr{key}' if kind == 'hdr' else f'pod_row{key}'
    got = extras_state(m, row_ids)
    if got != lay: return f'children {got} != {lay}'
    for kind, key in hidden:
        h = m.widgets[name(kind, key)]
        if (m.props.get((h, 'visible')), m.props.get((h, 'sensitive')), m.props.get((h, 'y'))) != (0, 0, 0): return f'{name(kind, key)} not hidden, insensitive and parked'
    for g in range(len(HDRS)):
        if m.props.get((m.widgets[HDRS[g]], 'sensitive')) != 0: return f'{HDRS[g]} is sensitive'
    stack = [c for c in m.calls if c[0] == 'widget_restack']
    want = [('widget_restack', m.widgets[name(kind, key)], k) for k, (kind, key) in enumerate(shown + hidden)]
    if stack != want: return f'stack {[s[2] for s in stack]} for {len(want)} children differs'
    if ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', height) not in m.calls: return f'virtual_h is not {height}'
    return ''


def arranged(m, rows):
    """{row index: (y, shown)} as the payload's calls left the page; a row it never touched is absent."""
    out = {}
    for i in range(rows):
        h = m.widgets[f'pod_row{i}']
        if (h, 'visible') in m.props: out[i] = (m.props.get((h, 'y'), 0), bool(m.props[(h, 'visible')]) and bool(m.props.get((h, 'sensitive'), 1)))
    return out


MENU_ROWS = 25   # twenty-four items, Extras
# The Extras page's fixed order, written out (pod_pages.EXTRAS_GROUPS, English labels): four titled groups, not alphabetical
EXTRAS_PLAY = ['Now Playing', 'Shuffle', 'Pod']
EXTRAS_LIB = ['Albums', 'Artists', 'Songs', 'Playlists', 'Cover Flow', 'Genres', 'Composers', 'Folders', 'Podcasts', 'Radio', 'Search', 'Navidrome']
EXTRAS_COLL = ['Favorites', 'Recently Played', 'Recently Added', 'Most Played', 'Hi-Res']
EXTRAS_TOOLS = ['Update Library', 'CD Ripper', 'Tidal']   # Settings is in no group: the Extras page's navbar button opens it
EXTRAS_TITLES = ['Play', 'Library', 'Collections', 'Tools']
# what the Extras page lists for the default menu (Cover Flow, Albums, Artists, Songs, Playlists): everything else but Settings (never listed)
DEF_EXTRAS = ['Now Playing', 'Shuffle', 'Pod', 'Genres', 'Composers', 'Folders', 'Podcasts', 'Radio', 'Search', 'Navidrome', 'Favorites', 'Recently Played', 'Recently Added', 'Most Played', 'Hi-Res',
              'Update Library', 'CD Ripper', 'Tidal']


def open_menu(data=None, rows=MENU_ROWS, present=(), count=False):
    m = page_machine(rows)
    if count: m.count()
    if data is not None: m.fs[MENU_FILE] = data
    m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(pod_pages.HOME_ENTRY)), count=3000000)
    return m


def extras_open(data=None, rows=len(pod_pages.ITEMS)):
    """The Extras page opened by the Extras menu row: (machine, labels of the listed rows top to bottom, {row: (y, shown)})."""
    m = page_machine(rows)
    if data is not None: m.fs[MENU_FILE] = data
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * len(pod_pages.ITEMS), count=3000000)
    a = arranged(m, rows)
    return m, [pod_pages.EXTRAS_PAGE.rows[i].label for _, i in sorted((y, i) for i, (y, on) in a.items() if on)], a


def extras(data=None):
    return extras_open(data, len(pod_pages.ITEMS))


def shown_order(m, rows=MENU_ROWS):
    """The labels of the shown rows of the page, top to bottom, from the arrangement."""
    a = arranged(m, rows)
    return [pod_pages.MENU.rows[i].label for _, i in sorted((y, i) for i, (y, on) in a.items() if on)]


def arrange_tests(ctx):
    expect, P = ctx.expect, pod_pages
    entry, on_row, rows0 = addresses()
    items = [r.label for r in P.ITEMS]
    default = ['Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Extras']
    ROW_H = pod_ui.ROW_H

    # 9. The default menu: Cover Flow, Albums, Artists, Songs, Playlists (saved string "12345"), then Extras; Now Playing (the mini player bar opens it), Shuffle,
    #    Settings and all the others are hidden by default and on the Extras page; Extras is always last.
    NI = len(P.ITEMS)
    CU = P.SETTINGS_ID
    items18 = items[:18]   # the items but Settings
    expect(items[:9] == ['Now Playing', 'Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Shuffle', 'Genres', 'Folders'] and items[CU] == 'Settings' and items[NI - 5] == 'Pod' and items[NI - 4] == 'Podcasts' and items[NI - 3] == 'Search' and items[NI - 2] == 'Radio' and items[NI - 1] == 'Navidrome' and CU == NI - 6
           and P.DEFAULT_MENU == [1, 2, 3, 4, 5] and P.parse_menu(None) == P.DEFAULT_MENU and P.parse_menu(b'12345\n') == P.DEFAULT_MENU,
           'the asset order is the item order; the default menu is items 1..5 (Cover Flow ... Playlists), Now Playing, Shuffle and Settings hidden')
    m = open_menu()
    expect(shown_order(m) == default, f'no saved list: the default menu, unchanged by the Extras items ({shown_order(m)})')
    a = arranged(m, MENU_ROWS)
    expect(all(a[i] == ((i - 1) * ROW_H, True) for i in range(1, 6)) and a[NI] == (5 * ROW_H, True),
           f'the shown rows are consecutive 52 px steps from y 0, Extras right after them ({a})')
    expect(all(a[i] == (0, False) for i in [0] + list(range(6, NI))), 'Now Playing, Shuffle, Genres, Folders, the nine Extras items, Settings, the Pod and Podcasts are hidden (and insensitive) and parked at y 0')
    expect(('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', 6 * ROW_H) in m.calls
           and not [c for c in m.calls if c[:3] == ('widget_set_prop_int', m.widgets['pod_scrollview'], 'yoffset')],
           'the list scrolls over exactly the shown rows (virtual_h 6 x 52), from the asset\'s top (the offset is not touched)')
    expect(not any(c[0] in ('write', 'rename', 'unlink') for c in m.calls) and
           [c[1] for c in m.calls if c[0] == 'open'] == [MENU_FILE], 'opening the menu reads the list file and writes nothing')

    # 10. Saved lists: order, subsets, none at all
    for data, want in ((b'6543210\n', ['Shuffle', 'Playlists', 'Songs', 'Artists', 'Albums', 'Cover Flow', 'Now Playing']),
                       (b'078\n', ['Now Playing', 'Genres', 'Folders']), (b'3\n', ['Artists']), (b'0123456', items[:7]),
                       (b'876543210\n', items[8::-1]), (b'\n', []),
                       (b'a\n', ['Favorites']), (b'0ei\n', ['Now Playing', 'Composers', 'CD Ripper']), (b'0123456ad\n', items[:7] + ['Favorites', 'Most Played']),
                       (b'ihgfedcba876543210\n', items18[::-1]), (b'012345678abcdefghi', items18), (b'012345678abcdefgh', items18[:-1]),
                       (b'i0\n', ['CD Ripper', 'Now Playing']), (b'j\n', ['Settings']), (b'0j\n', ['Now Playing', 'Settings']), (b'j0', ['Settings', 'Now Playing']),
                       (b'012345678abcdefghijklmno\n', items), (b'onmlkjihgfedcba876543210', items[::-1]), (b'k\n', ['Pod']), (b'l\n', ['Podcasts']), (b'm\n', ['Search']), (b'n\n', ['Radio']), (b'o\n', ['Navidrome']), (b'0m\n', ['Now Playing', 'Search']), (b'1j2\n', ['Cover Flow', 'Settings', 'Albums'])):
        for off in (b'', b'-', b'-0', b'-a\n', b'-bd'):   # the part after '-' (items turned off Extras) never changes the menu; an item both shown and off is invalid
            d = (data.rstrip(b'\n') + off).rstrip(b'\n') + b'\n' if off else data
            m = open_menu(d)
            if set(off.strip(b'-\n')) & set(data): w = default   # invalid: the default menu
            else: w = want + ['Extras']
            expect(shown_order(m) == w, f'saved {d!r}: {w}')
            a = arranged(m, MENU_ROWS)
            n = len(w) - 1
            expect(a[NI] == (n * ROW_H, True), f'saved {d!r}: Extras is shown, right after the items, last ({a[NI]})')
            expect(('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', (n + 1) * ROW_H) in m.calls, f'saved {d!r}: virtual_h follows')

    # 10b. The stock list_view lays its visible rows out again in child order at every relayout (test/pod/pulldown.py runs that code):
    #      the children are stacked in page order, hidden rows last (widget_restack child, index), and the plain painter replaces the
    #      list_view's paint hook (only the exact stock hook on a scroll_view)
    for data, shown in ((None, P.DEFAULT_MENU), (b'6502\n', [6, 5, 0, 2]), (b'\n', []), (b'i0\n', [17, 0]), (b'12345\n', P.DEFAULT_MENU),
                        (b'6502-ab\n', [6, 5, 0, 2]), (b'j\n', [CU]), (b'j0-a\n', [CU, 0])):
        m = open_menu(data)
        expect(P.parse_menu(data) == shown, f'saved {data!r}: the model shows {shown}')
        want = shown + [NI] + [i for i in range(NI) if i not in shown]
        got = [c for c in m.calls if c[0] == 'widget_restack']
        expect(got == [('widget_restack', m.widgets[f'pod_row{r}'], k) for k, r in enumerate(want)],
               f'saved {data!r}: the rows are restacked in page order (Extras after the shown items), the hidden ones last ({[g[2] for g in got]} for rows {want})')
    hook = 0x60c164
    for what, vt, hk, cleared in (('a list_view scroll_view', 0x97a298, hook, True), ('another widget', 0x97a018, hook, False),
                                  ('another hook', 0x97a298, 0x60c0fc, False), ('a plain scroll_view', 0x97a298, 0, False)):
        m = page_machine(MENU_ROWS)
        sv = m.widgets['pod_scrollview']; m.setword(sv + 0x70, vt); m.setword(sv + 0xf4, hk)
        m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(pod_pages.HOME_ENTRY)), count=3000000)
        expect(m.word(sv + 0xf4) == (0 if cleared else hk), f'{what}: the paint-children hook word is ' + ('cleared' if cleared else 'left alone'))
        expect(m.word(sv + 0x70) == vt, f'{what}: the vtable word is left alone')
    m = page_machine(MENU_ROWS)   # the Extras page
    sv = m.widgets['pod_scrollview']; m.setword(sv + 0x70, 0x97a298); m.setword(sv + 0xf4, hook)
    m.call(PSYMS['menu_arrange'], a0=m.window, a1=1, count=3000000)
    expect(m.word(sv + 0xf4) == 0, 'the Extras page: the plain painter')
    got = [c for c in m.calls if c[0] == 'widget_restack']
    expect(extras_ok(m, None) == '' and len(got) == len(P.ITEMS) + len(HDRS), f'the Extras page: the children (rows and headers) are restacked in the Extras order, the hidden ones last ({extras_ok(m, None)})')
    m = page_machine(MENU_ROWS)   # turned-off items are among the hidden ones, last
    m.fs[MENU_FILE] = b'12345-ab\n'
    m.call(PSYMS['menu_arrange'], a0=m.window, a1=1, count=3000000)
    expect(extras_ok(m, b'12345-ab') == '', f'the Extras page: the items turned off are restacked with the hidden ones, last ({extras_ok(m, b'12345-ab')})')



def arrange_invalid_tests(ctx):
    expect, P = ctx.expect, pod_pages
    entry, on_row, rows0 = addresses()
    default = ['Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Extras']
    # 11. Anything invalid is the default list: unknown ids, duplicates, too long, empty, binary, text after the list
    bad = [b'9\n', b'0129\n', b'00\n', b'01234567801\n', b'0123456789\n', b'', b'01 2\n', b'01\n\n',
           # 'x' was the Extras row's character: unknown now, so an old file with it is invalid (no compatibility)
           b'x1\n', b'1x2\n', b'123456x\n', b'123456x', b'123456xx\n', b'xx', b'x\nx', b'x\n', b'x\n\n', b'0x1', b'123456x ', b'123456 x', b'X', b'012345678abcdefghix\n',
           b'012345678abcdefghi0x\n', b'0123456789abcdefghx\n', b'x0\n', b'0x0\n', b'\nx', b'\n\n', b'0\r\n',
           b'0123456780123456', b'a' * 200, bytes(range(256)), b'01\x002\n', b'0123456789012345678901234567890123456789\n', b'0' * 1000000,
           # the item characters: unknown ones, duplicates, an uppercase letter, one too many, over the file cap
           b'ihgfedcba876543210\n\n', b'p\n', b'oo\n', b'mm\n', b'm0m\n', b'aa\n', b'A\n', b'0a0\n', b'012345678abcdefghijkoo\n', b'012345678abcdefghijk0\n', b'012345678abcdefghijklmm\n', b'012345678abcdefghija\n',
           b'012345678abcdefghij\n\n', b'0123456789abcdefgh\n', b'z', b'0123456789abcdefghijklmn', b'0123456789abcdefghijklm', b'0123456789abcdefghijklmn',
           # the turned-off part: '-' once, no id in both parts, and Settings (j) never in it
           b'1-2-3\n', b'1--2\n', b'--', b'--\n', b'-\n-', b'1-1\n', b'1-21\n', b'12-1', b'0-0', b'-j\n', b'1-j\n', b'12345-j\n', b'1-2j\n', b'j-j', b'-1-\n', b'1-2\n\n',
           b'1-2 \n', b'1-x\n', b'1-9\n', b'-0123456789', b'012345678-abcdefghij\n', b'012345678-abcdefgh0\n', b'0123456-abcdefghij1\n', b'012345678-abcdefghi-\n',
           b'0123456789-abcdefghij', b'012345678abcdefghi-j\n', b'012345678abcdefghij-\n\n']
    for data in bad:
        m = open_menu(data, count=PERF)
        expect(shown_order(m) == default and P.parse_menu(data) == P.DEFAULT_MENU
               and P.parse_menu_full(data) == (P.DEFAULT_MENU, []), f'saved {data[:20]!r} ({len(data)} bytes): the default menu, nothing turned off')
        if PERF: expect(m.icount < 200000, f'saved {len(data)} bytes: read is bounded, the open stays cheap ({m.icount} instructions)')
        _, ex, _ = extras_open(data)
        expect(ex == DEF_EXTRAS, f'saved {data[:20]!r}: the default Extras page, nothing turned off ({ex})')


def arrange_model_tests(ctx):
    expect, P = ctx.expect, pod_pages
    items = [r.label for r in P.ITEMS]
    ROW_H = pod_ui.ROW_H
    NI = len(P.ITEMS)
    # the Python model of the parser (tools/pod_pages.py parse_menu_full, which the docs and previews use) agrees with the payload, for the
    # menu and for what the Extras page lists
    import random
    rnd = random.Random(7)
    for _ in range(400):
        n = rnd.choice((0, 1, 2, 5, 9, 10, 11, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25))
        pool = b'0123456789\n -jxA' if rnd.random() < 0.3 else (P.ID_CHARS + '-').encode() if rnd.random() < 0.5 else b'012345678'
        data = bytes(rnd.choice(pool) for _ in range(n))
        if rnd.random() < 0.5:   # a valid-looking permutation with at most one '-', so the accepted case is exercised too
            ids = list(P.ID_CHARS.encode()); rnd.shuffle(ids); ids = ids[:rnd.randrange(0, len(P.ID_CHARS) + 1)]
            ids.insert(rnd.randrange(0, len(ids) + 1), ord('-')) if rnd.random() < 0.8 else None
            data = bytes(ids) + rnd.choice((b'', b'\n'))
        ids, off = P.parse_menu_full(data)
        m = open_menu(data)
        want = [P.MENU.rows[i].label for i in ids] + ['Extras']
        if shown_order(m) != want: expect(False, f'parser model differs for {data!r}: {shown_order(m)} vs {want}'); break
        mx, ex, _ = extras_open(data)
        want = [P.ITEMS[i].label for i in P.EXTRAS_ORDER if i != P.SETTINGS_ID and i not in ids and i not in off]
        if ex != want: expect(False, f'parser model differs for the Extras page, {data!r}: {ex} vs {want}'); break
        err = extras_ok(mx, data)   # headers, y positions, stacking and virtual_h against pod_pages.extras_display / extras_layout
        if err: expect(False, f'Extras page, saved {data!r}: {err}'); break
    else: expect(True, 'the payload reads 400 random lists as the Python model does (the menu and the Extras page with its section headers, positions and stacking)')
    expect(P.parse_menu(b'0123456\n') == list(range(7)) == P.parse_menu(b'0123456') and P.parse_menu(b'0e8a\n') == [0, 13, 8, 9]
           and P.parse_menu(b'012345678abcdefghi\n') == list(range(18)) and P.parse_menu(b'012345678abcdefghijk\n') == list(range(20)) and P.parse_menu(b'012345678abcdefghijkl\n') == list(range(21)) and P.parse_menu(b'012345678abcdefghijklm\n') == list(range(22)) and P.parse_menu(b'012345678abcdefghijklmn\n') == list(range(23)) and P.parse_menu(b'012345678abcdefghijklmno\n') == list(range(24)) and P.parse_menu(b'm\n') == [21] and P.parse_menu(b'n\n') == [22] and P.parse_menu(b'o\n') == [23]
           and P.parse_menu(b'0j\n') == [0, 18] and P.parse_menu(b'x\n') == P.DEFAULT_MENU,
           'the Python model: ids 0..8 use digits and ids 9..23 use a..o, preserving Settings and existing items; x is unknown')
    expect(P.OFF_CHAR == '-' and P.DEFAULT_OFF == [] and P.format_menu(P.DEFAULT_MENU) == '12345\n' and P.format_menu(P.DEFAULT_MENU, P.DEFAULT_OFF) == '12345\n'
           and P.parse_menu_full(b'12345\n') == (P.DEFAULT_MENU, []) and P.parse_menu_full(b'12345') == (P.DEFAULT_MENU, []) and P.parse_menu_full(None) == (P.DEFAULT_MENU, [])
           and P.parse_menu_full(b'\n') == ([], []) and P.parse_menu_full(b'-\n') == ([], []) and P.parse_menu_full(b'0ea\n') == ([0, 13, 9], [])
           and P.parse_menu_full(b'12345-ab\n') == (P.DEFAULT_MENU, [9, 10]) and P.parse_menu_full(b'0-1') == ([0], [1]) and P.parse_menu_full(b'-0\n') == ([], [0])
           and P.parse_menu_full(b'0-j\n') == (P.DEFAULT_MENU, []) and P.parse_menu_full(b'0-1-2\n') == (P.DEFAULT_MENU, []) and P.parse_menu_full(b'0-0\n') == (P.DEFAULT_MENU, [])
           and P.format_menu([1, 2, 3], [10, 9]) == '123-ab\n' and P.format_menu([1], [17, 0, 13]) == '1-0ei\n'
           and P.format_menu([], []) == '\n' and P.format_menu(list(range(24))) == '012345678abcdefghijklmno\n'
           and len(P.format_menu(list(range(10)), list(range(10, 18)) + [19, 20, 21, 22, 23])) < P.MENU_FILE_MAX and len(P.format_menu([], list(range(18)) + [19, 20, 21, 22, 23])) < P.MENU_FILE_MAX,
           'the Python model: "<shown>[-<off>]", the default 12345, the off part in the Extras order, Settings never off, the longest list fits the file cap')
    m = open_menu(b'0\n'); m.fs[MENU_FILE] = b'0\n'
    expect(m.fs[MENU_FILE] == b'0\n', 'a valid list is never rewritten by reading it')
    m = open_menu(b'nmlkjihgfedcba876543210\n', count=PERF)
    if PERF: expect(m.icount < 200000, f'the longest valid list: arranging twenty-four rows stays cheap ({m.icount} instructions)')
    m = open_menu(b'876543210-abcdefghi\n', count=PERF)
    if PERF: expect(m.icount < 200000, f'a long list with a long off part: arranging stays cheap ({m.icount} instructions)')

    # 11b. A page that is not ours (a row or the list missing) is left exactly as the asset has it
    for gone in ('pod_scrollview', 'pod_row5', 'pod_row12', 'pod_row18', 'pod_row19'):
        m = page_machine(MENU_ROWS); m.widgets.pop(gone); m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(P.HOME_ENTRY)), count=3000000)
        expect(('window_open', P.MENU.key) in m.calls and not any(c[0] in ('widget_move', 'widget_set_visible', 'widget_set_sensitive') for c in m.calls),
               f'no {gone}: the menu opens as the asset has it, nothing moved or hidden')

    # 11c. An Extras asset without the section headers (not ours, or an older one): the rows stack as before, nothing else is touched
    m = page_machine(MENU_ROWS, hdrs=False)
    m.call(PSYMS['menu_arrange'], a0=m.window, a1=1, count=3000000)
    a = arranged(m, MENU_ROWS)
    on_ = [i for _, i in sorted((y, i) for i, (y, on) in a.items() if on and i < NI)]
    expect([items[i] for i in on_] == DEF_EXTRAS and [a[i][0] for i in on_] == [k * ROW_H for k in range(len(on_))]
           and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', len(on_) * ROW_H) in m.calls, 'no headers in the asset: Extras stacks its rows from y 0 as before')



def arrange_extras_tests(ctx):
    expect, P = ctx.expect, pod_pages
    entry, on_row, rows0 = addresses()
    items = [r.label for r in P.ITEMS]
    default = ['Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Extras']
    ROW_H = pod_ui.ROW_H
    NI = len(P.ITEMS)
    CU = P.SETTINGS_ID
    # 12. Extras: every item the menu does not show, in id order (the hidden menu items, then the stock tiles)
    # The fixed order, the same in every language (the English labels): four titled groups in a deliberate order, each with a section header
    # (pod_hdr<group>, HDR_H high, a plain view that is never a touch target) above its first shown row; Settings, when the menu does not show it, is a Tool.
    hdr_h = P.HDR_H
    full = EXTRAS_PLAY + EXTRAS_LIB + EXTRAS_COLL + EXTRAS_TOOLS
    expect(P.EXTRAS_GROUPS == tuple(zip(EXTRAS_TITLES, map(tuple, (EXTRAS_PLAY, EXTRAS_LIB, EXTRAS_COLL, EXTRAS_TOOLS)))) and P.EXTRAS_TITLES == EXTRAS_TITLES
           and sorted(full + ['Settings']) == sorted(items) and [items[i] for i in P.EXTRAS_ORDER] == full + ['Settings'] and 0 < hdr_h < ROW_H
           and [P.EXTRAS_GROUP_OF[i] for i in P.EXTRAS_ORDER] == [0] * 3 + [1] * 12 + [2] * 5 + [3] * 3 + [4] and P.EXTRAS_GROUP_OF[CU] == len(P.EXTRAS_GROUPS),
           f'the Extras order is Play, Library, Collections, Tools, each item once, in the written order, then Settings (in no group) ({[items[i] for i in P.EXTRAS_ORDER]})')
    left = lambda shown: [x for x in full if x not in shown]
    m, order, a = extras()
    want_ex = left([items[i] for i in P.DEFAULT_MENU])
    expect(order == want_ex == DEF_EXTRAS, f'default: Now Playing, Shuffle (Play), Genres, Composers, Folders (Library), the collections, the Tools; no Settings ({order})')
    expect(all(a[i] == (0, False) for i in P.DEFAULT_MENU) and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', len(want_ex) * ROW_H + 4 * hdr_h) in m.calls,
           'the items the menu shows are hidden here, the list is the sixteen others and four headers long')
    ys = [y for y, i in sorted((y, i) for i, (y, on) in a.items() if on)]
    err = extras_ok(m, None)
    expect(not err, f'default: the arrangement is the Python model\'s (pod_pages.extras_display / extras_layout) ({err})')
    expect(extras_state(m, range(NI)) == [('hdr', 0, 0), ('row', 0, 40), ('row', 6, 92), ('row', 19, 144), ('hdr', 1, 196), ('row', 7, 236), ('row', 13, 288), ('row', 8, 340), ('row', 20, 392), ('row', 22, 444), ('row', 21, 496), ('row', 23, 548),
                                           ('hdr', 2, 600), ('row', 9, 640), ('row', 11, 692), ('row', 10, 744), ('row', 12, 796), ('row', 14, 848),
                                           ('hdr', 3, 900), ('row', 15, 940), ('row', 17, 992), ('row', 16, 1044)] and hdr_h == 40,
           'default: the headers and rows at their y (40 px headers, 52 px rows), written out')
    expect(ys[0] == hdr_h and ys == sorted(ys) and ys[1] - ys[0] == ROW_H and ys[3] - ys[2] == hdr_h + ROW_H, 'the shown rows are in display order; a header (40 px) lies between the groups, none between rows')
    m, order, a = extras(b'\n')
    expect(order == full, 'every item hidden: the twenty-three but Settings are in Extras, in the fixed order')
    m, order, a = extras(b'012345678\n')
    expect(order == left(items[:9]) and all(a[i] == (0, False) for i in range(9)), 'Genres and Folders in the menu too: Extras is the other nine')
    m, order, a = extras(b'0345\n')
    expect(order == left([items[i] for i in (0, 3, 4, 5)]), f'a hidden item is in Extras whatever order it had: {order}')
    m, order, a = extras(b'zz')
    expect(order == DEF_EXTRAS, 'an invalid list: the default split')
    # an Extras item shown in the menu leaves the Extras page (and the page shortens); the rest stay, in order
    m, order, a = extras(b'0123456ad\n')
    want_ex = left(items[:7] + ['Favorites', 'Most Played'])
    expect(order == want_ex and a[9] == (0, False) and a[12] == (0, False) and extras_ok(m, b'0123456ad\n') == '',
           f'Favorites and Most Played shown in the menu are hidden (and insensitive) on Extras, which is ten rows long, the others in place ({order})')
    ys = [y for y, i in sorted((y, i) for i, (y, on) in a.items() if on)]
    expect(all(b - a_ in (ROW_H, ROW_H + hdr_h) for a_, b in zip(ys, ys[1:])) and ys[0] == hdr_h,
           'the remaining Extras rows are 52 px apart, 92 where a header lies between two groups')
    m, order, a = extras(b'012345678abcdefghiklmno\n')
    expect(order == [] and all(a[i] == (0, False) for i in range(NI)), 'every item but Settings shown in the menu: Extras is empty (Settings is never listed)')
    m, order, a = extras(b'012345678abcdefghijklmno\n')
    expect(order == [] and all(a[i] == (0, False) for i in range(NI)) and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', 0) in m.calls,
           'every item shown in the menu: Extras is empty (its menu row stays)')
    m, order, a = extras(b'i0\n')
    expect(order == left(['CD Ripper', 'Now Playing']), f'a shown last tile and a shown first item both leave Extras ({order})')
    m, order, a = extras(b'j\n')
    expect(order == full, f'Settings alone in the menu: Extras has the other twenty-three ({order})')
    # Settings hidden from the menu (the default) is not on Extras either: its row stays hidden (the navbar button opens Settings)
    m, order, a = extras(b'123456\n')
    expect(order == [x for x in DEF_EXTRAS if x != 'Shuffle'] and a[CU] == (0, False),
           f'Settings hidden from the menu is not on the Extras page: its row is hidden and insensitive ({order})')
    mm = open_menu(b'123456\n')
    expect(shown_order(mm) == default[:5] + ['Shuffle', 'Extras'], 'and the menu then ends with the Shuffle, Extras rows')
    # the items turned off ('-' part) are not on the Extras page; the others in the fixed order; Settings hidden is always there
    m, order, a = extras(b'123456-ab\n')
    expect(order == [x for x in DEF_EXTRAS if x not in ('Shuffle', 'Favorites', 'Recently Added')] and a[9] == (0, False) and a[10] == (0, False),
           f'Favorites and Recently Added turned off: not listed, hidden and insensitive; Settings (hidden from the menu) is not listed either ({order})')
    m, order, a = extras(b'12345j-ab\n')
    expect(order == [x for x in DEF_EXTRAS if x not in ('Settings', 'Favorites', 'Recently Added')] and extras_ok(m, b'12345j-ab') == '', f'the same with Settings shown ({order})')
    m, order, a = extras(b'-' + P.ID_CHARS.replace('j', '').encode() + b'\n')
    expect(order == [] and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', 0) in m.calls and all(a[i] == (0, False) for i in range(NI)),
           'every item but Settings turned off (nothing shown): Extras is empty')
    m, order, a = extras(b'0-0\n')
    expect(order == DEF_EXTRAS, 'an item both shown and off is invalid: the default menu, nothing off')
    m, order, a = extras(b'0-j\n')
    expect(order == DEF_EXTRAS, 'Settings in the off part is invalid: the default menu, nothing off')
    # an item shown in the menu keeps no off flag: only items the menu does not show can be off, so the off part never hides a shown row
    m, order, a = extras(b'12-ab\n')
    expect('Favorites' not in order and 'Now Playing' in order and 'Settings' not in order, f'a file with an off part: the shown items are not on Extras either way ({order})')
    # the children are stacked in that order (a stock relayout lays visible rows out in child order), the hidden ones last
    for data in (None, b'\n', b'0123456ad\n', b'3\n', b'3-0a\n'):
        m, order, a = extras(data)
        shown, off = P.parse_menu_full(data)
        err = extras_ok(m, data)
        expect(not err, f'saved {data!r}: Extras restacks its headers and rows in display order, the hidden headers then the hidden rows last ({err})')
    # no item is ever in neither place, in any saved list without a turned-off part
    for data in (None, b'\n', b'8\n', b'0123\n', b'87654321\n', b'0123456\n', b'a\n', b'ie0\n', b'j\n', b'0123456abcdefghi\n', b'012345678abcdefghi\n', b'012345678abcdefghij\n'):
        mm = open_menu(data)
        _, ex_order, _ = extras(data)
        in_menu = set(shown_order(mm)) - {'Extras'}
        expect(in_menu | set(ex_order) >= set(items) - {'Settings'} and not in_menu & set(ex_order), f'saved {data!r}: every item is in exactly one of the menu and Extras')
    # a tap on a hidden item's row in Extras does what the menu row would
    rows_x = PSYMS[f'pod_rows_{P.EXTRAS_PAGE_INDEX}']
    for i, r in enumerate(P.ITEMS):
        m = Machine()
        m.call(on_row, a0=rows_x + 12 * i)
        mm = Machine()
        mm.call(on_row, a0=rows0 + 12 * i)
        expect([c for c in m.calls if c[0] != 'widget_on'] == [c for c in mm.calls if c[0] != 'widget_on'], f'Extras > {r.label} acts as the menu row')



def arrange_hit_tests(ctx):
    expect, P = ctx.expect, pod_pages
    entry, on_row, rows0 = addresses()
    ROW_H = pod_ui.ROW_H
    # 13. Hit testing on the arranged menu, by demo's own code: a touch in the middle of every shown row reaches that row, one
    #     over the place a hidden row was parked reaches the row that is there, and none below the last row hits any
    def apply_arrangement(m, tree):
        for row in [c for c in node(tree, 'pod_scrollview').children if c.name.startswith(('pod_row', 'pod_hdr'))]:
            h = m.widgets[row.name]
            if (h, 'y') in m.props: row.y = m.props[(h, 'y')]
            if (h, 'visible') in m.props: row.flags = (row.flags & ~F_VISIBLE) | (F_VISIBLE if m.props[(h, 'visible')] else 0)
            if (h, 'sensitive') in m.props: row.flags = (row.flags & ~F_SENSITIVE) | (F_SENSITIVE if m.props[(h, 'sensitive')] else 0)
    # the Extras page, arranged for a list that shows some Extras items in the menu: every shown row is hit, no hidden row is
    for data in (None, b'0123456ad\n', b'ai\n', b'\n', b'1-bc\n'):
        m, order, a = extras(data)
        tree = asset_tree(os.path.join(WORK, UI, 'm1plus_extras.bin'))
        apply_arrangement(m, tree)
        shown = sorted((y, i) for i, (y, on) in a.items() if on)
        hidden = {f'pod_row{i}' for i, (y, on) in a.items() if not on} | {f'pod_hdr{g}' for g in range(len(HDRS))}
        mx = Machine()
        lay, height = P.extras_layout(P.extras_display(*P.parse_menu_full(data))[0], ROW_H)
        for kind, key, y in lay:
            h = ROW_H if kind == 'row' else P.HDR_H
            for ty in (y + 1, y + h // 2, y + h - 1):   # the first, middle and last pixel of the child
                if ty >= 400: continue
                got = stock_target(mx, tree, 160, 50 + ty)
                if kind == 'row': expect(f'pod_row{key}' in got and not hidden & set(got), f'Extras, saved {data!r}: a touch on row {key} (y {ty}) reaches it ({got})')
                else: expect(not [g for g in got if g.startswith(('pod_row', 'pod_hdr'))] and 'pod_scrollview' in got,
                             f'Extras, saved {data!r}: a touch on the header of group {key} (y {ty}) reaches no row and no header, only the list ({got})')
        got = stock_target(mx, tree, 160, 50 + 1)
        expect(not hidden & set(got), f'Extras, saved {data!r}: where the hidden children are parked (y 0) they take no touch ({got})')
        if height + 10 < 400:
            got = stock_target(mx, tree, 160, 50 + height + 10)
            expect(not [g for g in got if g.startswith(('pod_row', 'pod_hdr'))], f'Extras, saved {data!r}: below the last row nothing is hit ({got})')
    for data in (None, b'6543210\n', b'\n', b'01234\n', b'a0ei\n', b'012345678abcdefghij\n', b'1j-a\n'):
        m = open_menu(data)
        tree = asset_tree(os.path.join(WORK, UI, 'm1plus_menu.bin'))
        apply_arrangement(m, tree)
        a = arranged(m, MENU_ROWS)
        shown = sorted((y, i) for i, (y, on) in a.items() if on)
        hidden = {f'pod_row{i}' for i, (y, on) in a.items() if not on}
        mx = Machine()
        for y, i in shown:
            if y + ROW_H // 2 >= 400: continue
            got = stock_target(mx, tree, 160, 50 + y + ROW_H // 2)
            expect(f'pod_row{i}' in got and not hidden & set(got), f'saved {data!r}: a touch on row {i} reaches it ({got})')
        got = stock_target(mx, tree, 160, 50 + ROW_H // 2)
        expect(f'pod_row{shown[0][1]}' in got and not hidden & set(got), f'saved {data!r}: where hidden rows are parked the first shown row takes the touch ({got})')
        if len(shown) * ROW_H + 10 < 400:
            got = stock_target(mx, tree, 160, 50 + len(shown) * ROW_H + 10)
            expect(not [g for g in got if g.startswith('pod_row')], f'saved {data!r}: below the last row nothing is hit ({got})')

    # 14. The menu arranges again when it is back in front (after the Main Menu page changed the list)
    m = open_menu()
    fg = [c for c in m.calls if c[0] == 'widget_on' and c[2] == 0x12d]   # EVT_WINDOW_FG (patch/home.h)
    expect(len(fg) == 1, 'the menu registers one to-foreground handler')
    sw = m.widgets['pod_scrollview']
    m.fs[MENU_FILE] = b'012345678abcd\n'   # 13 items + Extras: 728 px in a 400 px list
    m.props[(sw, 'h')] = 400; m.props[(sw, 'yoffset')] = 200; m.calls = []
    m.call(fg[0][3], a0=fg[0][4], count=3000000)
    expect(m.props[(sw, 'yoffset')] == 200 and not [c for c in m.calls if c[:3] == ('widget_set_prop_int', sw, 'yoffset')],
           f'back in front (from a page it opened) the list stays where it was scrolled (yoffset {m.props[(sw, "yoffset")]})')
    m.props[(sw, 'yoffset')] = 380
    m.fs[MENU_FILE] = b'4\n'
    m.call(fg[0][3], a0=fg[0][4], count=3000000)
    expect(shown_order(m) == ['Songs', 'Extras'], f'back in front it shows the new list ({shown_order(m)})')
    expect(m.props[(sw, 'yoffset')] == 0, f'a list now shorter than its window is back at the top (yoffset {m.props[(sw, "yoffset")]})')


def settings_tests(ctx):
    expect, P = ctx.expect, pod_pages
    _, on_row, rows0 = addresses()
    S = P.SETTINGS_PAGE
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    cf_i = next(i for i, r in enumerate(S.rows) if r.action == P.ACT_PAGE and r.arg == P.LIBRARY_PAGE_INDEX)
    settings_i = next(i for i, r in enumerate(P.MENU.rows) if r.action == P.ACT_PAGE and r.arg == P.SETTINGS_PAGE_INDEX)

    def open_settings():
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(
            ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))])}
        m.call(on_row, a0=rows0 + 12 * settings_i, count=3000000)
        return m

    # 15. Settings (cards): the stock Wi-Fi and Bluetooth pages, our pages, Playback (Play Mode, EQ, the stock list), System (Display, Accent, Keyboards, About, the stock list), Developer
    expect([r.label for r in S.rows] == ['Wi-Fi', 'Bluetooth', 'Home Screen', 'Library', 'Now Playing', 'Play Mode', 'EQ', 'All Playback Settings',
                                         'Display', 'Appearance', 'Keyboards', 'About', 'All System Settings', 'Developer'],
           'the Settings page lists Wi-Fi, Bluetooth, Home Screen, Library, Now Playing, Play Mode, EQ, All Playback Settings, Display, Accent, Keyboards, About, All System Settings, Developer')
    pb = next(r for r in S.rows if r.label == 'All Playback Settings'); ss = next(r for r in S.rows if r.label == 'All System Settings')
    expect((pb.action, pb.arg) == (P.ACT_HOME, P.HOME_PLAYSET) and (ss.action, ss.arg) == (P.ACT_HOME, P.HOME_SYSSET),
           'All Playback Settings opens the stock Play settings list, All System Settings the stock one')
    expect([r.label for r in P.HOMESET_PAGE.rows][-4:] == ['Main Menu', 'Extras', 'Battery Percentage', 'Regenerate Daily Mix'] and P.HOMESET_PAGE.title == 'Home Screen', 'Home Screen ends with Main Menu, Extras, Battery Percentage and Regenerate Daily Mix')
    ex_r, cu_r = len(P.ITEMS), P.SETTINGS_ID
    expect(P.MENU.rows[cu_r].label == 'Settings' and (P.MENU.rows[cu_r].action, P.MENU.rows[cu_r].arg) == (P.ACT_PAGE, P.SETTINGS_PAGE_INDEX)
           and P.MENU.rows[ex_r].label == 'Extras' and P.MENU.rows[-1] is P.MENU.rows[ex_r], 'the menu\'s Settings row opens the Settings page; Extras is the last row')
    for data in (None, b'\n', b'0123456\n', b'87\n', b'zz', b'ihgfedcba876543210\n', b'012345678abcdefghi\n', b'a\n', b'0123456abcdefghi8\n', b'j\n', b'012345678abcdefghij\n', b'1-a\n'):
        m = open_menu(data)
        a = arranged(m, MENU_ROWS)
        ids, off = P.parse_menu_full(data)
        expect(a[ex_r][1] and a[ex_r][0] == len(ids) * pod_ui.ROW_H, f'saved {data!r}: the Extras row is shown, right after the shown items')
        expect(a[cu_r][1] == (cu_r in ids), f'saved {data!r}: Settings is a normal item: shown only when the list shows it')
        expect(('widget_on', m.widgets[f'pod_row{cu_r}'], O['EVT_CLICK']) in [c[:3] for c in m.calls]
               and ('widget_on', m.widgets[f'pod_row{ex_r}'], O['EVT_CLICK']) in [c[:3] for c in m.calls], f'saved {data!r}: the Settings and Extras rows are bound')
    m = open_settings()
    expect(('window_open', S.key) in m.calls and m.names().count('widget_on') == 2 + len(S.rows) + 2, 'the menu row opens the Settings page and binds its rows, and its foreground and destroy events (the values refresh)')

    # 16. Settings > Library: the row opens the sub-page (Update Library, Album Order, the landscape switch, Rebuild Covers); the generic page open binds its rows
    m = Machine()
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))])}
    m.call(on_row, a0=rows_s + 12 * cf_i, count=3000000)
    expect(('window_open', P.LIBRARY_PAGE.key) in m.calls, 'the Library row on the Settings page opens m1plus_library')
    library_tests(ctx, on_row)
    keyboards_tests(ctx, on_row, rows_s)
    pcsearch_row_tests(ctx, on_row, rows_s)


def mainmenu_section(ctx):
    expect, P = ctx.expect, pod_pages
    _, on_row, _ = addresses()
    rows_me = PSYMS[f'pod_rows_{P.HOMESET_PAGE_INDEX}']
    mm_i = next(i for i, r in enumerate(P.HOMESET_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.MENUCFG_PAGE_INDEX)
    # 17. The Main Menu row (on Menu & Extras) opens the customise page (the generic page open: navbar bound, no row table)
    m = Machine()
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'])}
    m.call(on_row, a0=rows_me + 12 * mm_i, count=3000000)
    expect(('window_open', P.MENUCFG_PAGE.key) in m.calls and P.MENUCFG_PAGE.rows == [], 'the Main Menu row opens the Main Menu page')
    mainmenu_tests(ctx, on_row, rows_me, mm_i)


def extrascfg_section(ctx):
    _, on_row, _ = addresses()
    extrascfg_tests(ctx, on_row, PSYMS[f'pod_rows_{pod_pages.HOMESET_PAGE_INDEX}'])


def extrascfg_tests(ctx, on_row, rows_s):
    """Settings > Extras (m1plus_extrascfg): a switch row per item but Settings, only the items the menu does not show, on = listed on Extras."""
    expect, P = ctx.expect, pod_pages
    n, CU, ROW_H = len(P.ITEMS), P.SETTINGS_ID, pod_ui.ROW_H
    items = [r.label for r in P.ITEMS]
    ids = [i for i in range(n) if i != CU]
    ex_i = next(i for i, r in enumerate(P.HOMESET_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.EXTRASCFG_PAGE_INDEX)
    hdr_h, full = P.HDR_H, EXTRAS_PLAY + EXTRAS_LIB + EXTRAS_COLL + EXTRAS_TOOLS
    CFG_DEF = [x for x in DEF_EXTRAS if x != 'Settings']   # the default menu's hidden items, but Settings (no row on this page), in the Extras order
    expect(P.HOMESET_PAGE.rows[ex_i].label == 'Extras' and P.PAGES[P.EXTRASCFG_PAGE_INDEX] is P.EXTRASCFG_PAGE and P.EXTRASCFG_PAGE.kind == 'extrascfg',
           'Home Screen has an Extras row that opens the Settings > Extras page')

    def open_page(data=None):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch') for i in ids] + HDRS
        m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names)}
        m.widgets['pod_scrollview'] = m.alloc(0x180)
        if data is not None: m.fs[MENU_FILE] = data
        m.call(on_row, a0=rows_s + 12 * ex_i, count=3000000)
        return m

    def listed(m):
        """(labels of the shown rows top to bottom, {row: y}) as the payload arranged the page."""
        out = {}
        for i in ids:
            h = m.widgets.get(f'pod_row{i}')
            if h is not None and (h, 'visible') in m.props and m.props[(h, 'visible')] and m.props.get((h, 'sensitive'), 1): out[i] = m.props.get((h, 'y'), 0)
        return [items[i] for i, _ in sorted(out.items(), key=lambda kv: kv[1])], out

    def hidden_ok(m):
        """Every row not listed is hidden and insensitive, parked at y 0."""
        _, out = listed(m)
        return all(m.props.get((m.widgets[f'pod_row{i}'], 'visible')) == 0 and m.props.get((m.widgets[f'pod_row{i}'], 'sensitive')) == 0
                   and m.props.get((m.widgets[f'pod_row{i}'], 'y')) == 0 for i in ids if i not in out)

    def switches(m):
        return {i: [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']] for i in ids}

    # opens: the menu's hidden items, in the Extras order, every switch on by default
    m = open_page()
    labels, ys = listed(m)
    expect(('window_open', P.EXTRASCFG_PAGE.key) in m.calls and labels == CFG_DEF and hidden_ok(m) and extras_ok(m, None, cfg=True) == ''
           and sorted(ys.values())[:3] == [hdr_h, hdr_h + ROW_H, hdr_h + 2 * ROW_H], f'default menu: the items it hides, in the Extras order, under their group headers ({labels}, {extras_ok(m, None, cfg=True)})')
    expect([k for k, key, y in extras_state(m, ids)].count('hdr') == 4 and extras_state(m, ids)[-4][:2] == ('hdr', 3) and len(extras_state(m, ids)) == len(CFG_DEF) + 4,
           'four headers shown: the Tools header too, for its three rows without Settings (which has no row here)')
    expect(all(v == ['sset_on'] for i, v in switches(m).items() if items[i] in labels) and 'Settings' not in labels,
           'every switch is on (listed on Extras); Settings has no row')
    expect(m.names().count('widget_on') == 2 + len(ids) + 1 and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', len(labels) * ROW_H + 4 * hdr_h) in m.calls,
           'a click handler per row and a destroy handler; the list scrolls over exactly the rows and headers shown')
    expect(len([c for c in m.calls if c[0] == 'widget_restack']) == len(ids) + len(HDRS), 'the rows and the headers are restacked in display order, the hidden ones last (extras_ok)')
    m = open_page(b'\n')
    expect(listed(m)[0] == [x for x in full if x != 'Settings'] and len(listed(m)[0]) == 23 and extras_ok(m, b'\n', cfg=True) == '',
           'nothing shown in the menu: all twenty-three rows (Settings has none)')
    m = open_page(b'012345678abcdefghijklmno\n')
    expect(listed(m)[0] == [] and hidden_ok(m) and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', 0) in m.calls and extras_state(m, ids) == []
           and extras_ok(m, b'012345678abcdefghijklmno\n', cfg=True) == '', 'everything shown in the menu: no row and no header')
    import random
    rnd = random.Random(11)
    for _ in range(300):   # random saved lists (valid and not): the page is the Python model's, headers, y positions, stacking and virtual_h
        k = rnd.randrange(0, 22)
        pool = list(P.ID_CHARS); rnd.shuffle(pool)
        data = (''.join(pool[:k]) + ('-' + ''.join(rnd.sample(P.ID_CHARS.replace('j', ''), rnd.randrange(0, 5))) if rnd.random() < 0.5 else '') + chr(10)).encode()
        err = extras_ok(open_page(data), data, cfg=True)
        if err: expect(False, f'Settings > Extras, saved {data!r}: {err}'); break
    else: expect(True, 'the page is the Python model\'s for 300 random saved lists (headers shown iff their group has a row, y positions, stacking, virtual_h)')
    m = open_page(b'012345678abcdefghjklmno\n')   # everything shown in the menu but CD Ripper: its group's header shows with it, and no other
    expect(extras_ok(m, b'012345678abcdefghjklmno\n', cfg=True) == '' and listed(m)[0] == ['CD Ripper'] and [t[:2] for t in extras_state(m, ids)] == [('hdr', 3), ('row', 17)],
           'only CD Ripper left: the Tools header and the row')
    m = open_page(b'1-0a\n')
    labels, _ = listed(m)
    sw = switches(m)
    expect(labels[:3] == ['Now Playing', 'Shuffle', 'Pod'] and 'Cover Flow' not in labels and sw[0] == ['sset_off'] and sw[9] == ['sset_off'] and sw[10] == ['sset_on'],
           f'a saved list with off items: their switches are off, the others on, the menu\'s items have no row ({labels[:3]})')
    expect(extras_ok(m, b'1-0a\n', cfg=True) == '', 'and the headers, positions and stacking are the model\'s (the turned-off ones still listed here)')
    for bad in (b'1-1\n', b'0-j\n', b'1-2-3\n', b'x\n'):
        m = open_page(bad)
        expect(listed(m)[0] == CFG_DEF and all(v == ['sset_on'] for i, v in switches(m).items() if items[i] in listed(m)[0]), f'saved {bad!r}: invalid, the default (nothing off)')

    # a tap on a row turns the item off Extras (saved at once, atomically) and on again; Settings hidden from the menu is not on this page
    m = open_page()
    m.click('pod_row9')
    expect(m.fs.get(MENU_FILE) == b'12345-a\n' and ('rename', MENU_TMP, MENU_FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls and MENU_TMP not in m.fs
           and switches(m)[9] == ['sset_off'], f'Favorites off: saved atomically with the off part, the switch follows ({m.fs.get(MENU_FILE)!r})')
    expect(not any(c[0] == 'widget_move' for c in m.calls) and listed(m)[0] == CFG_DEF, 'the row stays where it is (the page does not re-arrange)')
    m.click('pod_row0')
    expect(m.fs.get(MENU_FILE) == b'12345-0a\n', f'Now Playing off too: the off part is in the Extras order ({m.fs.get(MENU_FILE)!r})')
    m.click('pod_row9')
    expect(m.fs.get(MENU_FILE) == b'12345-0\n' and switches(m)[9] == ['sset_on'], 'Favorites on again')
    m.click('pod_row0')
    expect(m.fs.get(MENU_FILE) == b'12345\n' and switches(m)[0] == ['sset_on'], 'and the last on: no "-" part')
    m.click('pod_row1')   # Cover Flow: shown in the menu, the row is hidden (and insensitive): a stray event changes nothing
    expect(m.fs.get(MENU_FILE) == b'12345\n' and not any(c[0] in ('rename', 'image_base_set_image') for c in m.calls), 'a row of an item the menu shows does nothing')
    m = open_page(b'2301j\n')
    m.click('pod_row10'); m.click('pod_row17')
    expect(m.fs.get(MENU_FILE) == b'2301j-bi\n', f'the shown part and its order are kept ({m.fs.get(MENU_FILE)!r})')
    # the Extras page and the menu follow the file
    _, order, _ = extras_open(m.fs[MENU_FILE])
    expect('Recently Added' not in order and 'CD Ripper' not in order and 'Favorites' in order, f'Extras then omits the two ({order})')
    expect(shown_order(open_menu(m.fs[MENU_FILE])) == ['Albums', 'Artists', 'Now Playing', 'Cover Flow', 'Settings', 'Extras'], 'and the menu is unchanged')
    # Settings hidden from the menu: on the Extras page, never off
    m = open_page(b'123456\n')
    expect(listed(m)[0] == [x for x in CFG_DEF if x != 'Shuffle'] and 'pod_row%d' % CU not in m.widgets, 'Settings hidden from the menu has no row here')
    _, order, _ = extras_open(b'123456-0\n')
    expect('Settings' not in order and 'Now Playing' not in order, f'it is not on the Extras page either ({order})')
    # a failed save is undone: the file, the switch and the next tap
    m = open_page(); m.fail.add(('write', MENU_TMP))
    m.click('pod_row9')
    expect(MENU_FILE not in m.fs and MENU_TMP not in m.fs and not any(c[0] == 'image_base_set_image' and c[2] == 'sset_off' for c in m.calls), 'a failed write: no file, the switch stays on')
    m.fail.clear()
    m.click('pod_row10')
    expect(m.fs.get(MENU_FILE) == b'12345-b\n', f'and the failed change left no flag behind ({m.fs.get(MENU_FILE)!r})')
    m = open_page(); m.fail.add(('rename', MENU_FILE))
    m.click('pod_row9')
    expect(MENU_FILE not in m.fs and not any(c[0] == 'image_base_set_image' and c[2] == 'sset_off' for c in m.calls), 'a failed rename: the same')
    # a page that is not ours is left as it is
    for gone in ('pod_scrollview', 'pod_row5', 'pod_switch12'):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch') for i in ids]
        m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names)}
        m.widgets.pop(gone)
        m.call(on_row, a0=rows_s + 12 * ex_i, count=3000000)
        expect(('window_open', P.EXTRASCFG_PAGE.key) in m.calls and not any(c[0] in ('widget_move', 'widget_set_visible', 'widget_restack') for c in m.calls)
               and m.names().count('widget_on') == 2, f'no {gone}: the page opens as the asset has it, nothing moved or bound')

    # the asset: a stock list of switch rows, one per item but Settings, all on, no arrows
    path = os.path.join(WORK, UI, P.EXTRASCFG_PAGE.key + '.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    rows = [w for w in tree.walk() if w.type == 'list_item']
    expect([r.name for r in rows] == [f'pod_row{i}' for i in ids] and [pod_i18n.shown_english(next(c for c in r.children if c.type == 'hscroll_label')) for r in rows] == [items[i] for i in ids],
           'twenty-one rows pod_row0..17, 19, 20, 21 (no Settings) in the item order')
    expect(all(r.find(f'pod_switch{i}') is not None and r.find(f'pod_switch{i}').get('image') == 'sset_on' and r.find(f'pod_switch{i}').get('sensitive') == 'false'
               and (r.find(f'pod_switch{i}').w, r.find(f'pod_switch{i}').h) == (57, 28) and r.find('pod_icon') is not None and not [w for w in r.walk() if w.name.startswith('pod_up')]
               for i, r in zip(ids, rows)), 'each row: the stock 57x28 switch image (on), the icon disc, no up arrow')
    lv = tree.find('pod_listview')
    expect(lv.type == 'list_view' and lv.children[0].type == 'scroll_view' and tree.find('scroll_bar_m') is not None and lv.y + lv.h == CLIENT_H
           and max(r.y + r.h for r in rows) == len(ids) * ROW_H, 'stock list_view > scroll_view + scroll bar, ending at the window bottom')
    m = Machine()
    for i, r in enumerate([c for c in node(asset_tree(path), 'pod_scrollview').children if c.name.startswith('pod_row')]):
        y = 50 + r.y + r.h // 2
        if y >= CLIENT_H: continue
        for x in (100, 290):
            got = stock_target(m, asset_tree(path), x, y)
            expect(f'pod_row{ids[i]}' in got and not any(g.startswith('pod_switch') for g in got), f'row {ids[i]}: a touch at x {x} (on the switch too) goes to the row ({got})')
    header_asset_tests(ctx, tree, 'Settings > Extras')
    # an asset without the headers (not ours, or an older one): the rows are arranged as before, one after the other, nothing else touched
    m = Machine()
    names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch') for i in ids]
    m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names)}
    m.widgets['pod_scrollview'] = m.alloc(0x180)
    m.call(on_row, a0=rows_s + 12 * ex_i, count=3000000)
    labels, ys = listed(m)
    expect(labels == CFG_DEF and sorted(ys.values()) == [k * ROW_H for k in range(len(labels))] and hidden_ok(m)
           and ('widget_set_prop_int', m.widgets['pod_scrollview'], 'virtual_h', len(labels) * ROW_H) in m.calls, 'no headers in the asset: the rows stack from y 0 as before')


def header_asset_tests(ctx, tree, what):
    """The section headers of an Extras-style asset (tools/pod_ui.py extras_headers): pod_hdr0..3, plain views HDR_H high holding the group's title as a small grey label, hidden and
    insensitive in the asset, none of them a list_item, and a touch on one reaches no row and not the header."""
    expect, P = ctx.expect, pod_pages
    sv = tree.find('pod_scrollview')
    hdrs = [c for c in sv.children if c.name.startswith('pod_hdr')]
    expect([h.name for h in hdrs] == HDRS and all(h.type == 'view' and h.h == P.HDR_H < pod_ui.ROW_H and h.w == sv.w for h in hdrs), f'{what}: four header views pod_hdr0..3, {P.HDR_H} px high, as wide as the list')
    expect(all(h.get('visible') == 'false' and h.get('sensitive') == 'false' for h in hdrs), f'{what}: the headers start hidden and insensitive')
    expect([pod_i18n.shown_english(h.children[0]) for h in hdrs] == EXTRAS_TITLES and [pod_i18n.key_for(t) for t in EXTRAS_TITLES] == EXTRAS_TITLES,
           f'{what}: they show Play, Library, Collections and Tools (translated by their keys)')
    expect(all(len(h.children) == 1 and h.children[0].type == 'hscroll_label' and h.children[0].get('sensitive') == 'false' and h.children[0].x == pod_ui.HDR_X == pod_ui.SH_HEAD_X == 10
               and h.children[0].get('style:normal:font_size') == str(pod_ui.HDR_PX) == str(pod_ui.SH_HEAD_PX) == '20'
               and h.children[0].get('style:normal:text_color') == pod_ui.HDR_RGB == pod_ui.SH_SUB_RGB
               and 0 < h.children[0].y and h.children[0].y + h.children[0].h <= h.h for h in hdrs),
           f'{what}: the caption is in the style of the Home menu\'s "Made for You" heading (x 10, 20 px) in the secondary grey, inside the strip, insensitive')
    expect(not [w for h in hdrs for w in h.walk() if w.type in ('list_item', 'image', 'button')], f'{what}: no list_item, chevron, icon or button in a header (no press visual)')
    expect(sv.children[-4:] == hdrs and len([c for c in sv.children if c.name.startswith('pod_row')]) == len(sv.children) - 4, f'{what}: the headers follow the rows')


def keyboards_tests(ctx, on_row, rows_s):
    """Settings > Keyboards (m1plus_keyboards): English always on and not switchable, Chinese (Pinyin) a switch saved in /mnt/data/m1plus/keyboard-pinyin, off by default."""
    expect, P = ctx.expect, pod_pages
    K = P.KEYBOARDS_PAGE
    FILE = '/mnt/data/m1plus/keyboard-pinyin'
    kb_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.KEYBOARDS_PAGE_INDEX)
    expect([(r.label, r.action) for r in K.rows] == [('English', P.ACT_KB_EN), ('Chinese (Pinyin)', P.ACT_KB_ZH)] and K.title == 'Keyboards' and K.key == 'm1plus_keyboards'
           and P.ACT_KB_EN in P.SWITCH_ACTIONS and P.ACT_KB_ZH in P.SWITCH_ACTIONS and P.PAGES[P.KEYBOARDS_PAGE_INDEX] is K and P.SETTINGS_PAGE.rows[kb_i].label == 'Keyboards',
           'Settings has a Keyboards row (after Cassette Mode); its page has two switch rows: English and Chinese (Pinyin)')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_keyboards.bin'), 'rb').read())
    expect(all(tree.find(f'pod_row{i}') is not None and tree.find(f'pod_switch{i}') is not None for i in range(2)) and not [w for w in tree.walk() if w.name.startswith('pod_value')],
           'the asset has the two rows, each with a switch image, no value label')

    def open_kb(saved=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(
            ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + ['pod_switch0', 'pod_switch1'])}
        if saved is not None: m.fs[FILE] = saved
        m.call(on_row, a0=rows_s + 12 * kb_i, count=3000000)
        return m

    def images(m, i): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']]

    m = open_kb()
    expect(('window_open', K.key) in m.calls and images(m, 0) == ['sset_on'] and images(m, 1) == ['sset_off'], 'the row opens the page: English shows on, Chinese (Pinyin) off with nothing saved')
    expect(('widget_set_opacity', m.widgets['pod_row0'], 153) in m.calls and ('widget_set_sensitive', m.widgets['pod_row0'], 0) in m.calls
           and (m.widgets['pod_row0'], O['EVT_CLICK']) not in m.bound and (m.widgets['pod_row1'], O['EVT_CLICK']) in m.bound,
           'English is dimmed and takes no tap (nothing is bound on it); the Chinese row is bound')
    expect(FILE not in m.fs, 'English has nothing to save: no file')
    for data, on in ((b'1\n', 1), (b'1', 1), (b'0\n', 0), (b'', 0), (b'x', 0), (b'11', 0), (b'1x', 0), (b'\n1', 0)):
        got = images(open_kb(data), 1)
        expect(got == [('sset_on' if on else 'sset_off')], f'saved {data!r}: the Chinese switch opens {"on" if on else "off"} (exactly "1" or "1\\n" is on, anything else off)')
    m = open_kb()
    m.click('pod_row1')
    expect(m.fs.get(FILE) == b'1\n' and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls and images(m, 1)[-1] == 'sset_on',
           'a tap turns Chinese (Pinyin) on: written atomically, the switch on')
    expect(m.call(PSYMS['kb_zh_setting']) == 1, 'kb_zh_setting reads it')
    m.click('pod_row1')
    expect(m.fs.get(FILE) == b'0\n' and images(m, 1)[-1] == 'sset_off' and m.call(PSYMS['kb_zh_setting']) == 0, 'and off again')
    m = open_kb(b'1\n'); m.fail.add(('write', FILE + '.tmp'))
    m.click('pod_row1')
    expect(m.fs.get(FILE) == b'1\n' and FILE + '.tmp' not in m.fs and images(m, 1) == [] and m.call(PSYMS['kb_zh_setting']) == 1, 'a failed write changes neither the file nor the switch')
    expect(m.call(PSYMS['kb_zh_setting']) == 1 and Machine().call(PSYMS['kb_zh_setting']) == 0, 'no file: off')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Keyboards', 'English', 'Chinese (Pinyin)')), f'the three strings have a text in {loc}')


def pcsearch_row_tests(ctx, on_row, rows_s):
    """Settings > Library > Podcasts > Podcast Search (docs/modules/settings.md): a switch row, off by default, saved as "1" in /mnt/data/m1plus/podcast-online-search (the first byte), written atomically; a failed
    save changes neither the file nor the switch; the Podcasts page reads it with pcsearch_setting."""
    expect, P = ctx.expect, pod_pages
    C = P.LIBRARY_PAGE
    FILE = '/mnt/data/m1plus/podcast-online-search'
    cf_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.LIBRARY_PAGE_INDEX)
    ps_i = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_PCSEARCH)
    layout = [type(x).__name__ + (':' + x.label if isinstance(x, P.Row) else ':' + x.text if hasattr(x, 'text') else '') for x in C.layout]
    expect(C.rows[ps_i].label == 'Podcast Search' and P.ACT_PCSEARCH in P.SWITCH_ACTIONS and P.row_kind(C.rows[ps_i]) == 'switch'
           and layout[-3:] == ['Hdr:Podcasts', 'Row:Podcast Search', 'Note:Search words are sent to Apple.'], f'the Library page ends with a Podcasts header, the Podcast Search switch row and its note ({layout[-3:]})')

    def open_lib(saved=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + [f'pod_switch{ps_i}'])}
        if saved is not None: m.fs[FILE] = saved
        m.call(on_row, a0=rows_s + 12 * cf_i, count=3000000)
        return m

    def images(m): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{ps_i}']]

    m = open_lib()
    expect(images(m) == ['sset_off'] and FILE not in m.fs and m.call(PSYMS['pcsearch_setting'], count=2000000) == 0, 'opened with nothing saved: the switch is off, nothing is written, the setting reads 0 (the default)')
    for data, on in ((b'1\n', 1), (b'1', 1), (b'0\n', 0), (b'', 0), (b'x', 0), (b'1x', 0), (b'11', 0), (b'\n1', 0)):
        expect(images(open_lib(data)) == [('sset_on' if on else 'sset_off')], f'saved {data!r}: the switch opens {"on" if on else "off"}')
    m = open_lib()
    m.click(f'pod_row{ps_i}')
    expect(m.fs.get(FILE) == b'1\n' and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls and images(m)[-1] == 'sset_on'
           and m.call(PSYMS['pcsearch_setting'], count=2000000) == 1, 'a tap turns it on: written atomically (a temp file, fsync, rename), the switch on')
    m.click(f'pod_row{ps_i}')
    expect(m.fs.get(FILE) == b'0\n' and images(m)[-1] == 'sset_off' and m.call(PSYMS['pcsearch_setting'], count=2000000) == 0, 'and off again')
    m = open_lib(b'1\n'); m.fail.add(('write', FILE + '.tmp'))
    m.click(f'pod_row{ps_i}')
    expect(m.fs.get(FILE) == b'1\n' and FILE + '.tmp' not in m.fs and images(m) == [] and m.call(PSYMS['pcsearch_setting'], count=2000000) == 1, 'a failed save changes neither the file nor the switch')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Podcast Search', 'Podcasts', 'Search words are sent to Apple.')), f'the row, its header and its note have a text in {loc}')


def library_tests(ctx, on_row):
    """Settings > Library (m1plus_library): Update Library, Album Order (a value row opening the picker page), the Landscape switch and Rebuild Covers; the picker Album Order."""
    expect, P = ctx.expect, pod_pages
    C = P.LIBRARY_PAGE
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']
    rows_c = PSYMS[f'pod_rows_{P.LIBRARY_PAGE_INDEX}']
    cf_i = next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.LIBRARY_PAGE_INDEX)
    LAND, SORT = '/mnt/data/m1plus/coverflow-landscape', CFSORT_FILE
    land_i = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_LANDSCAPE)
    sort_i = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_SORT)
    sw, val = f'pod_switch{land_i}', f'pod_value{sort_i}'
    expect([(r.label, r.action) for r in C.rows] == [('Update Library', P.ACT_HOME), ('Rebuild Covers', P.ACT_REBUILD), ('Album Order', P.ACT_SORT), ('Landscape', P.ACT_LANDSCAPE), ('Podcast Search', P.ACT_PCSEARCH)]
           and C.title == 'Library' and C.rows[0].arg == P.HOME_UPDATE and C.rows[sort_i].arg == P.SORT_PAGE_INDEX and P.row_kind(C.rows[0]) == 'action' and P.row_kind(C.rows[sort_i]) == 'value',
           'the Library page: one card of Update Library (the stock page, no chevron), Rebuild Covers and Album Order (a value, a chevron, its picker), then Landscape (switch) under Cover Flow, and Podcast Search (switch)')

    def open_lib(land=None, sort=None, language=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(
            ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + [sw, val])}
        if land is not None: m.fs[LAND] = land
        if sort is not None: m.fs[SORT] = sort
        if language: m.set_language(language)
        m.call(on_row, a0=rows_s + 12 * cf_i, count=3000000)
        return m

    def label(m):
        """The last key the sort value was set to, and the text it shows."""
        keys = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[val]]
        return keys[-1] if keys else None

    m = open_lib()
    expect(('window_open', C.key) in m.calls and all(('widget_on', m.widgets[f'pod_row{i}'], O['EVT_CLICK']) in [c[:3] for c in m.calls] for i in range(len(C.rows))),
           'the Library row opens the page and binds every row')
    # Landscape: the switch writes the setting Cover Flow reads, atomically, the image follows
    expect(('image_base_set_image', m.widgets[sw], 'sset_off') in m.calls, 'Landscape is off with nothing saved')
    m = open_lib(b'1\n')
    expect(('image_base_set_image', m.widgets[sw], 'sset_on') in m.calls, 'saved landscape: the switch opens on')
    for data in (b'x', b'', b'0\n'):
        m = open_lib(data)
        expect(('image_base_set_image', m.widgets[sw], 'sset_off') in m.calls, f'saved {data!r}: the switch opens off')
    m = open_lib()
    m.click(f'pod_row{land_i}')
    expect(m.fs.get(LAND) == b'1\n' and LAND + '.tmp' not in m.fs and ('rename', LAND + '.tmp', LAND) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
           and ('image_base_set_image', m.widgets[sw], 'sset_on') in m.calls, 'a tap turns it on: written atomically, the switch on')
    m.click(f'pod_row{land_i}')
    expect(m.fs.get(LAND) == b'0\n' and ('image_base_set_image', m.widgets[sw], 'sset_off') in m.calls, 'and off again')
    expect(SORT not in m.fs, 'the landscape switch does not touch the sort file')
    m = open_lib(b'1\n'); m.fail.add(('write', LAND + '.tmp'))
    m.click(f'pod_row{land_i}')
    expect(m.fs.get(LAND) == b'1\n' and not any(c[0] == 'image_base_set_image' for c in m.calls) and LAND + '.tmp' not in m.fs,
           'a failed write changes neither the file nor the switch')

    # Album Order: Artist by default, the value in the row's grey label (set by key, so the language follows)
    expect(label(open_lib()) == 'Artist', 'with nothing saved the order is Artist')
    expect(label(open_lib(sort=b'0\n')) == 'album', 'saved "0": Album (the stock key album)')
    for data in (b'1\n', b'1', b'', b'x', b'00', b'0x', b'0\n\n', b'2\n', b' 0\n', b'\x000'):
        expect(label(open_lib(sort=data)) == 'Artist', f'saved {data!r}: invalid or Artist, the label reads Artist')
    expect(label(open_lib(sort=b'0')) == 'album', 'saved "0" without a newline is Album too')
    m = open_lib()
    m.click(f'pod_row{sort_i}')
    expect(('window_open', P.SORT_PAGE.key) in m.calls, 'a tap on Album Order opens the picker page (m1plus_albumorder), it does not change the order')
    expect(SORT not in m.fs, 'opening the picker saves nothing')
    # the picker: a check on the chosen row, a tap on the other saves it atomically and the checks follow
    S = P.SORT_PAGE
    expect([(r.label, r.action, r.arg) for r in S.rows] == [('Artist', P.ACT_SORTSET, 1), ('Album', P.ACT_SORTSET, 0)] and S.title == 'Album Order' and all(P.row_kind(r) == 'check' for r in S.rows),
           'the picker: Artist and Album, check rows')

    def open_pick(sort=None, language=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(
            ['btn_return', 'btn_backtoplayer', 'pod_row0', 'pod_row1', 'pod_check0', 'pod_check1'])}
        if sort is not None: m.fs[SORT] = sort
        if language: m.set_language(language)
        m.call(on_row, a0=rows_c + 12 * sort_i, count=3000000)
        return m

    def shown(m, i):
        v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
        return v[-1] if v else None

    m = open_pick()
    expect(('window_open', S.key) in m.calls and shown(m, 0) == 1 and shown(m, 1) == 0, 'the picker opens with the check on Artist (nothing saved)')
    m = open_pick(b'0\n')
    expect(shown(m, 0) == 0 and shown(m, 1) == 1, 'saved Album: the check is on Album')
    m = open_pick()
    m.click('pod_row1')
    expect(m.fs.get(SORT) == b'0\n' and SORT + '.tmp' not in m.fs and ('rename', SORT + '.tmp', SORT) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls
           and shown(m, 0) == 0 and shown(m, 1) == 1, 'a tap on Album: written atomically, the check follows')
    m.click('pod_row0')
    expect(m.fs.get(SORT) == b'1\n' and shown(m, 0) == 1 and shown(m, 1) == 0, 'and back to Artist')
    expect(LAND not in m.fs, 'the picker does not touch the landscape file')
    m = open_pick(b'0\n'); m.fail.add(('write', SORT + '.tmp'))
    m.click('pod_row0')
    expect(m.fs.get(SORT) == b'0\n' and shown(m, 0) is None and shown(m, 1) is None and SORT + '.tmp' not in m.fs, 'a failed write changes neither the file nor the check (no check is touched)')
    m = open_pick(); m.fail.add(('rename', SORT))
    m.click('pod_row1')
    expect(SORT not in m.fs and shown(m, 0) is None and shown(m, 1) is None, 'a failed rename changes neither')
    # localisation: the value is the translation in every language
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        m = open_lib(language=loc)
        expect(label(m) == 'Artist' and T('Artist'), f'{loc}: Artist is set by key')
        m = open_lib(sort=b'0\n', language=loc)
        expect(label(m) == 'album', f'{loc}: Album is the stock key album')
    # Rebuild Covers: the row asks first (the stock confirm dialog, a wrapped message), and only Yes opens the rebuild
    rb_i = next(i for i, r in enumerate(C.rows) if r.action == P.ACT_REBUILD)
    KEY = 'Rebuild all covers? This may take a few minutes.'

    def rebuild_machine(language=None, yes=False, bad=None):
        m = cover_machine(albums=3)
        if bad: m.fs[bad] = b''; m.present.add(bad); m.listing[bad.rsplit('/', 1)[0]] = [('.', 4), ('r00000001-168.jpg', 8), (bad.rsplit('/', 1)[1], 8)]
        for n in ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(P.SETTINGS_PAGE.rows))] + [sw, val]:
            if n not in m.widgets: m.widget(n)
        if language: m.set_language(language)
        m.confirm_yes = yes
        m.call(on_row, a0=rows_s + 12 * cf_i, count=3000000)
        m.click(f'pod_row{rb_i}', count=6000000)
        return m

    m = rebuild_machine()
    confirms = [c for c in m.calls if c[0] == 'confirm']
    expect(confirms == [('confirm', KEY, O['CONFIRM_KIND_WRAP'])], f'a tap on Rebuild Covers asks first, in the stock confirm dialog, kind 5 (wrapped) ({confirms})')
    expect(('navigator_to_with_context', 'dialog/confirminfo_dialog') == m.calls[[c[0] for c in m.calls].index('navigator_to_with_context')][:2]
           if 'navigator_to_with_context' in m.names() else False, 'through navigator_to_with_context(dialog/confirminfo_dialog)')
    REQ = '/mnt/data/m1plus/covers-rebuild'
    expect(not any(n in m.names() for n in ('window_open', 'pthread_create', 'mkdir', 'rename', 'unlink', 'fopen', 'toast')) and build_state(m)['jobs'] == 0 and REQ not in m.fs,
           'No (or the dialog closed): nothing happens at all, no page, no thread, no file, no toast')
    BAD = '/mnt/mmc/.m1plus/covers/r00000001-168.jpg.bad'
    m = rebuild_machine(yes=True, bad=BAD)
    expect(('unlink', BAD) in m.calls and [c for c in m.calls if c[0] == 'unlink'] == [('unlink', BAD)] and ('opendir', '/mnt/mmc/.m1plus/covers') in m.calls, 'Yes clears the .bad markers: each album gets one retry')
    m = rebuild_machine(yes=True)
    expect(m.fs.get(REQ) == b'1\n' and [c[1] for c in m.calls if c[0] == 'toast'] == ['Covers will rebuild on Home'],
           'Yes writes the request file and shows the toast')
    expect(not any(n in m.names() for n in ('window_open', 'pthread_create')) and 'coverflow_rebuild' not in str(m.calls) and build_state(m)['jobs'] == 0,
           'and stays on Settings: no Cover Flow, no worker')
    for loc in pod_i18n.ALL_TABLES:
        m = rebuild_machine(language=loc, yes=True)
        expect([c[1] for c in m.calls if c[0] == 'toast'] == [tr_of(loc)('Covers will rebuild on Home')], f'{loc}: the toast is translated')
    for loc in pod_i18n.ALL_TABLES:
        T = tr_of(loc)
        m = rebuild_machine(language=loc)
        expect([c[1] for c in m.calls if c[0] == 'confirm'] == [T(KEY)], f'{loc}: the confirm message reads {T(KEY)!r}')
    # Developer > Cover Cache: the No art / Missing rows are value rows whose chevron and tap exist only for a counted, non-zero count
    D, CP = P.DEVELOPER_PAGE, P.CACHE_PAGE
    cc_i = next(i for i, r in enumerate(D.rows) if r.action == P.ACT_PAGE and r.arg == P.CACHE_PAGE_INDEX)
    na_i, ms_i = (next(i for i, r in enumerate(CP.rows) if r.action == P.ACT_CCLIST and r.arg == a) for a in (P.INFO_CC_NOART, P.INFO_CC_MISSING))
    m = cover_machine(albums=4, cached=False)
    for n in ['btn_return', 'btn_backtoplayer', 'pod_chevron'] + [f'pod_row{i}' for i in range(len(CP.rows))] + [f'pod_value{i}' for i in range(len(CP.rows))]:
        if n not in m.widgets: m.widget(n)
    m.call(on_row, a0=PSYMS[f'pod_rows_{P.DEVELOPER_PAGE_INDEX}'] + 12 * cc_i, count=6000000)
    first = list(m.calls)
    expect(('widget_set_visible', m.widgets['pod_chevron'], 0) in first and ('widget_set_sensitive', m.widgets[f'pod_row{ms_i}'], 0) in first
           and ('widget_set_text_utf8', m.widgets[f'pod_value{ms_i}'], '\xe2\x80\xa6') in first, 'while counting: no chevron, the row takes no touch, the value is an ellipsis')
    seen = []
    for _ in range(30):
        seen += fired(m, 'cp_tick', 40000000)
        if not [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['cp_tick']]: break
    row_calls = lambda i: [c for c in seen if c[0] == 'widget_set_sensitive' and c[1] == m.widgets[f'pod_row{i}']]
    expect(row_calls(ms_i)[-1:] == [('widget_set_sensitive', m.widgets[f'pod_row{ms_i}'], 1)] and row_calls(na_i)[-1:] == [('widget_set_sensitive', m.widgets[f'pod_row{na_i}'], 0)],
           'counted: Missing (4) takes touches, No art (0) still does not')
    expect(('widget_set_text_utf8', m.widgets[f'pod_value{ms_i}'], '4') in seen and ('widget_set_text_utf8', m.widgets[f'pod_value{na_i}'], '0') in seen, 'and the values are the counts')
    cache_tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui', CP.key + '.bin'), 'rb').read())
    sizes = {int(cache_tree.find(f'pod_value{i}').get('style:normal:font_size')) for i in range(len(CP.rows)) if cache_tree.find(f'pod_value{i}') is not None}
    expect(sizes == {18}, f'the Cover Cache values are the standard 18 px value size, as Library\'s Album Order value ({sizes})')
    expect(not [c for c in cache_tree.find(f'pod_row{na_i}').children if c.name.startswith('pod_icon')] and [c for c in cache_tree.find(f'pod_row{na_i}').children if c.name == 'pod_chevron'], 'No art: no glyph, a chevron the payload shows when there is a list')
    # the built asset: a value label that takes no touch, a chevron, the row takes the tap
    path = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui', C.key + '.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    row, value = tree.find(f'pod_row{sort_i}'), tree.find(val)
    expect(value is not None and value.get('sensitive') == 'false' and value.get('tr_text') == 'Artist'
           and [c for c in row.children if c.name == 'pod_chevron'], 'the Album Order row: an insensitive value label (tr_text Artist) and the chevron')
    expect(tree.find(f'pod_switch{land_i}') is not None and tree.find(f'pod_switch{land_i}').get('sensitive') == 'false'
           and not [c for c in tree.find(f'pod_row{land_i}').children if c.name == val], 'the Landscape row: its switch image, no value')
    node_tree = asset_tree(path)
    mm = Machine()
    for r in range(len(C.rows)):
        y = 50 + tree.find(f'pod_row{r}').y + pod_ui.ROW_H // 2
        for x in (100, 290):
            got = stock_target(mm, node_tree, x, y)
            expect(f'pod_row{r}' in got and not any(n.startswith('pod_value') or n.startswith('pod_switch') for n in got), f'a tap at x {x} on row {r} reaches the row ({got})')


def mainmenu_tests(ctx, on_row, rows_s, mm_i):
    expect, P = ctx.expect, pod_pages
    n = len(P.ITEMS)
    CU = P.SETTINGS_ID
    ROW_H = pod_ui.ROW_H
    items = [r.label for r in P.ITEMS]
    ZX, ZW = 191, 50   # the arrow's rectangle in the row (the asset's pod_up button, checked in 22); the tap of an arrow is a click on its row in this zone
    arrow = lambda m, i: m.click(f'pod_row{i}', x=ZX + ZW // 2)

    def open_page(data=None):
        m = Machine()
        names = ['btn_return', 'btn_backtoplayer', 'pod_scrollview'] + [f'pod_{k}{i}' for k in ('row', 'switch', 'up') for i in range(n)]
        m.widgets = {x: 0x30000000 + 0x100 * i for i, x in enumerate(names)}
        m.widgets['pod_scrollview'] = m.alloc(0x180)   # real memory: the payload reads its vtable word and paint hook
        for i in range(n):   # a row is a zeroed widget_t (x 0, y 0, no parent): widget_to_local, stock's own code, turns the tap's x into the row's
            m.widgets[f'pod_row{i}'] = m.alloc(0x180); m.u.mem_write(m.widgets[f'pod_row{i}'], bytes(0x180))
            m.props[(m.widgets[f'pod_up{i}'], 'x')], m.props[(m.widgets[f'pod_up{i}'], 'w')] = ZX, ZW
        m.props[(m.widgets['pod_scrollview'], 'h')] = 398   # the list's window: 7.6 rows of 19
        if data is not None: m.fs[MENU_FILE] = data
        m.call(on_row, a0=rows_s + 12 * mm_i, count=3000000)
        return m

    def state(m):
        """(labels top to bottom, shown flags, arrow flags, switch images) as the page was left."""
        pos = sorted((m.props.get((m.widgets[f'pod_row{i}'], 'y'), i * ROW_H), i) for i in range(n))
        sw = lambda i: [c[2] for c in m.log if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']]
        up = lambda i: bool(m.props.get((m.widgets[f'pod_up{i}'], 'visible'), 1))   # the arrow is a picture: shown or not
        return ([items[i] for _, i in pos], [sw(i)[-1] == 'sset_on' if sw(i) else None for _, i in pos], [up(i) for _, i in pos])

    def run(m, fn):
        """Call fn and keep the whole log: the machine forgets its calls at each call."""
        log = getattr(m, 'log', [])
        fn()
        m.log = log + m.calls

    # 18. The page lays out the saved list: the shown items first, in order, then the hidden ones; arrows on the shown ones but the first
    D = P.DEFAULT_MENU
    dflt = [items[i] for i in D] + [items[i] for i in range(n) if i not in D]   # the default menu, then the hidden items in default order
    m = open_page(); m.log = list(m.calls)
    labels, on, up = state(m)
    DN = len(D)   # 5 shown by default
    expect(labels == dflt and labels[0] == 'Cover Flow' and labels[4] == 'Playlists' and labels[5] == 'Now Playing' and on == [True] * DN + [False] * (n - DN)
           and up == [False] + [True] * (DN - 1) + [False] * (n - DN),
           f'default: the five items on top, Now Playing, Shuffle, Genres, Folders, the nine Extras items and Settings off below, an arrow on each shown item but the first ({labels}, {on}, {up})')
    expect(all(('widget_on', m.widgets['pod_row3'], O[e]) in [c[:3] for c in m.calls] for e in ('EVT_CLICK', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'))
           and not any(c[0] == 'widget_on' and c[1] == m.widgets['pod_up3'] for c in m.calls)
           and m.names().count('widget_on') == 2 + 4 * n + 1, 'each row is bound (click, pointer down, up, abort), no arrow is (and the window destroy); the page has no Extras row')
    m = open_page(b'6502\n'); m.log = list(m.calls)
    labels, on, up = state(m)
    expect(labels[:4] == ['Shuffle', 'Playlists', 'Now Playing', 'Albums'] and labels[4:] == ['Cover Flow', 'Artists', 'Songs', 'Genres', 'Folders'] + items[9:]
           and on == [True] * 4 + [False] * (n - 4) and up == [False, True, True, True] + [False] * (n - 4), f'a saved list is laid out as saved ({labels}, {on})')
    stack = lambda m: [next(i for i in range(n) if m.widgets[f'pod_row{i}'] == c[1]) for c in m.calls if c[0] == 'widget_restack']
    expect(stack(m) == [6, 5, 0, 2, 1, 3, 4] + list(range(7, n)), f'the rows are restacked in page order (a relayout keeps it): {stack(m)}')
    m = open_page(b'xx'); m.log = list(m.calls)
    expect(state(m)[0] == dflt and state(m)[1][:DN] == [True] * DN and state(m)[1][DN] is False, 'a corrupt list: the defaults')
    expect([c[2] for c in m.calls if c[0] == 'widget_restack'] == list(range(n)), 'and the children index follows the page order')
    m = open_page(b'e0i\n'); m.log = list(m.calls)
    labels, on, up = state(m)
    expect(labels[:3] == ['Composers', 'Now Playing', 'CD Ripper'] and labels[3:] == [x for x in items if x not in labels[:3]]
           and on == [True] * 3 + [False] * (n - 3) and up == [False, True, True] + [False] * (n - 3),
           f'Extras items in a saved list come first in their place, the rest follow in default order ({labels[:5]})')
    m = open_page(b'012345678abcdefghijklmno\n'); m.log = list(m.calls)
    labels, on, up = state(m)
    expect(labels == items and all(on) and up == [False] + [True] * (n - 1), 'all twenty-four shown: an arrow on every row but the first')
    m = open_page(b'0123456x\n'); m.log = list(m.calls)
    labels, on, up = state(m)
    expect(labels == dflt and on == [True] * DN + [False] * (n - DN), 'a saved list with the retired x (the Extras row): the defaults')
    m = open_page(b'12345-ab\n'); m.log = list(m.calls)
    labels, on, up = state(m)
    expect(labels == dflt and on == [True] * DN + [False] * (n - DN), 'a list with items turned off: the page shows the same shown items (the off part is the Extras page\'s)')

    # 19. A switch (the row's tap) hides an item (it leaves the list) or shows it (it joins the end); saved at once, atomically
    m = open_page(); m.log = list(m.calls)
    run(m, lambda: m.click('pod_row1'))   # Cover Flow off
    expect(m.fs.get(MENU_FILE) == b'2345\n' and ('rename', MENU_TMP, MENU_FILE) in m.calls and MENU_TMP not in m.fs, f'hide Cover Flow: saved atomically ({m.fs.get(MENU_FILE)!r})')
    labels, on, up = state(m)
    expect(labels == items[2:6] + items[:2] + items[6:] and on == [True] * 4 + [False] * 20
           and up == [False] + [True] * 3 + [False] * 20, f'it moves to the hidden group (default order after the shown ones), its switch off ({labels}, {on})')
    run(m, lambda: m.click('pod_row8'))   # Folders on
    expect(m.fs.get(MENU_FILE) == b'23458\n', f'show Folders: it joins the end ({m.fs.get(MENU_FILE)!r})')
    labels, on, up = state(m)
    expect(labels[:5] == ['Albums', 'Artists', 'Songs', 'Playlists', 'Folders'] and labels[5:8] == ['Now Playing', 'Cover Flow', 'Shuffle']
           and on == [True] * 5 + [False] * 19, f'and is the last shown row ({labels})')
    run(m, lambda: m.click('pod_row0'))   # Now Playing, hidden by default, on: it joins the end
    expect(m.fs.get(MENU_FILE) == b'234580\n' and state(m)[0][5] == 'Now Playing' and state(m)[1][5] is True, 'show Now Playing (hidden by default): it joins the end')
    run(m, lambda: m.click('pod_row0'))   # hide it
    run(m, lambda: m.click('pod_row0'))   # show it again: it is last
    expect(m.fs.get(MENU_FILE) == b'234580\n', 'hide and show again: the item goes to the end')
    # an Extras item (Favorites, id 9, character 'a') is shown like any other: it joins the end, in the saved file as 'a'
    run(m, lambda: m.click('pod_row9'))
    expect(m.fs.get(MENU_FILE) == b'234580a\n' and state(m)[0][6] == 'Favorites' and state(m)[1][6] is True and state(m)[2][6] is True,
           f'show Favorites: it joins the end as "a", with its switch on and an arrow ({m.fs.get(MENU_FILE)!r})')
    run(m, lambda: arrow(m, 9))
    expect(m.fs.get(MENU_FILE) == b'23458a0\n' and state(m)[0][5] == 'Favorites', 'its arrow moves it up one place, past Now Playing')
    run(m, lambda: m.click('pod_row17'))   # CD Ripper
    expect(m.fs.get(MENU_FILE) == b'23458a0i\n' and state(m)[0][7] == 'CD Ripper', 'the last Extras tile, CD Ripper, saves as "i"')
    run(m, lambda: m.click('pod_row9'))
    expect(m.fs.get(MENU_FILE) == b'234580i\n' and state(m)[1][:7] == [True] * 7 and state(m)[1][7] is False and 'Favorites' not in state(m)[0][:7],
           'and hidden again, it goes back to the hidden group')
    for i in range(n): run(m, lambda i=i: m.click(f'pod_row{i}') if P.ID_CHARS[i].encode() in m.fs[MENU_FILE].rstrip(b'\n') else None)
    expect(m.fs.get(MENU_FILE) == b'\n' and all(x is False for x in state(m)[1]) and not any(state(m)[2]),
           'every item can be hidden (Settings too; Extras stays on the menu): the list is empty, no arrow shows')
    for i in range(n): run(m, lambda i=i: m.click(f'pod_row{i}'))
    expect(m.fs.get(MENU_FILE) == b'012345678abcdefghijklmno\n' and all(state(m)[1]) and len(m.fs[MENU_FILE]) < P.MENU_FILE_MAX,
           'and every item, all twenty-four, can be shown again: the longest list fits the file cap')
    run(m, lambda: arrow(m, 17))
    expect(m.fs.get(MENU_FILE) == b'012345678abcdefgihjklmno\n', 'arrows work down at the end of the long list (the page scrolls)')
    m = open_page(); m.fail.add(('write', MENU_TMP)); m.log = list(m.calls)
    run(m, lambda: m.click('pod_row1'))
    expect(MENU_FILE not in m.fs and state(m)[0] == dflt and state(m)[1][:DN] == [True] * DN and MENU_TMP not in m.fs,
           'a failed save is undone: the file, the order and the switches are as they were')

    # 19b. Settings is an item like the others: hidden it leaves the list (and shows on the Extras page), shown it joins the end, it moves up
    m = open_page(); m.log = list(m.calls)
    run(m, lambda: m.click(f'pod_row{CU}'))
    expect(m.fs.get(MENU_FILE) == b'12345j\n' and state(m)[0][:6] == dflt[:5] + ['Settings'] and state(m)[1][:7] == [True] * 6 + [False] and state(m)[2][5] is True,
           f'showing Settings (hidden by default): it joins the end of the menu list, with an arrow ({m.fs.get(MENU_FILE)!r})')
    run(m, lambda: m.click(f'pod_row{CU}'))
    expect(m.fs.get(MENU_FILE) == b'12345\n' and state(m)[0][:5] == dflt[:5] and state(m)[1][:6] == [True] * 5 + [False] and 'Settings' in state(m)[0][5:],
           'and hiding it again: it leaves the menu list (and is on the Extras page)')
    run(m, lambda: m.click(f'pod_row{CU}'))
    run(m, lambda: arrow(m, CU))
    expect(m.fs.get(MENU_FILE) == b'1234j5\n' and state(m)[0][4] == 'Settings', 'its arrow moves it up one place')

    # 19c. The off flags: showing an item clears its flag; hiding keeps the others; a hidden item the list turned off stays off (and a shown one is never off)
    m = open_page(b'12345-ab\n'); m.log = list(m.calls)
    run(m, lambda: m.click('pod_row9'))   # Favorites (off): shown
    expect(m.fs.get(MENU_FILE) == b'12345a-b\n', f'showing an item that was turned off clears its flag ({m.fs.get(MENU_FILE)!r})')
    run(m, lambda: m.click('pod_row9'))   # hidden again: not off any more
    expect(m.fs.get(MENU_FILE) == b'12345-b\n', f'hidden again it is on Extras (its flag stays clear): {m.fs.get(MENU_FILE)!r}')
    run(m, lambda: m.click('pod_row1'))   # Cover Flow hidden: not off
    expect(m.fs.get(MENU_FILE) == b'2345-b\n', f'hiding a shown item keeps the others\' flags ({m.fs.get(MENU_FILE)!r})')
    run(m, lambda: m.click('pod_row10'))   # Recently Added (off): shown
    expect(m.fs.get(MENU_FILE) == b'2345b\n', f'showing the last turned-off item leaves no "-" part ({m.fs.get(MENU_FILE)!r})')
    m = open_page(b'12345-ab\n'); m.log = list(m.calls)
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(MENU_FILE) == b'13245-ab\n', f'moving an item keeps the off part ({m.fs.get(MENU_FILE)!r})')
    m = open_page(b'-ab\n'); m.log = list(m.calls)
    expect(state(m)[0][:3] == ['Now Playing', 'Cover Flow', 'Albums'] and state(m)[1] == [False] * n, 'an empty shown part with an off part: nothing shown')
    run(m, lambda: m.click('pod_row10'))
    expect(m.fs.get(MENU_FILE) == b'b-a\n', f'show Recently Added (off): joins the end, "-a" is kept ({m.fs.get(MENU_FILE)!r})')
    m = open_page(b'-ab\n'); m.fail.add(('write', MENU_TMP)); m.log = list(m.calls)
    run(m, lambda: m.click('pod_row9'))
    expect(m.fs.get(MENU_FILE) == b'-ab\n' and state(m)[1] == [False] * n, 'a failed save of the first change leaves the file and the flags (the next change still sees them)')
    m.fail.clear()
    run(m, lambda: m.click('pod_row10'))
    expect(m.fs.get(MENU_FILE) == b'b-a\n', f'and the next change keeps the flag the failed one did not clear ({m.fs.get(MENU_FILE)!r})')


    # 20. The up arrow: one place up among the shown items; saved at once
    m = open_page(); m.log = list(m.calls)
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(MENU_FILE) == b'13245\n', f'Artists up: swaps with Albums ({m.fs.get(MENU_FILE)!r})')
    labels, on, up = state(m)
    expect(labels[:5] == ['Cover Flow', 'Artists', 'Albums', 'Songs', 'Playlists'], f'the rows moved ({labels})')
    for _ in range(1): run(m, lambda: arrow(m, 3))
    expect(m.fs.get(MENU_FILE) == b'31245\n' and state(m)[0][0] == 'Artists' and state(m)[2][0] is False and state(m)[2][1] is True,
           'up again: to the top, where the arrow goes away and the next row gets one')
    run(m, lambda: arrow(m, 3))
    expect(m.fs.get(MENU_FILE) == b'1245\n', 'the top row has no arrow: a tap on that spot is a toggle (it never moves a first item)')
    m = open_page(); m.log = list(m.calls); m.fail.add(('rename', MENU_FILE))
    run(m, lambda: arrow(m, 5))
    expect(MENU_FILE not in m.fs and state(m)[0] == dflt and state(m)[2] == [False] + [True] * 4 + [False] * 19, 'a failed save of a move is undone too')
    m = open_page()
    h = {x: m.widgets[x] for x in m.widgets if x.startswith('pod_up')}
    expect(all((h[f'pod_up{i}'], 0) in [c[1:3] for c in m.calls if c[0] == 'widget_set_visible'] and (h[f'pod_up{i}'], 0) in [c[1:3] for c in m.calls if c[0] == 'widget_set_sensitive']
               for i in (1, 0, 7, 8, 9, 17)), 'the arrows of the first shown and of the hidden items are hidden and insensitive (hidden widgets still hit-test)')

    # 20b. In place, at once: every change re-arranges the page (no reopen), repaints it whole, keeps the moved row in view
    def moves(m): return [c for c in m.calls if c[0] == 'widget_move']
    sv = lambda m: m.widgets['pod_scrollview']
    m = open_page(); m.log = list(m.calls)
    expect(('widget_invalidate_force', m.window) in m.calls, 'the page lays itself out and repaints whole at open')
    arrow(m, 3)
    expect(('widget_invalidate_force', m.window) in m.calls and len(moves(m)) >= 2 and 'image_base_set_image' in m.names(),
           'an arrow tap re-arranges (moves the rows, sets the switches) and invalidates the whole window')
    expect(m.props[(m.widgets['pod_row3'], 'y')] == 1 * ROW_H and m.props[(m.widgets['pod_row2'], 'y')] == 2 * ROW_H,
           'the tapped row is at its new place at once, and the one it passed is at its old one')
    # hit-testing: the arrow of the row now first is hidden and insensitive; the one under it shows
    arrow(m, 3)
    h = lambda x: m.widgets[x]
    expect(m.props[(h('pod_row3'), 'y')] == 0 and m.props[(h('pod_up3'), 'visible')] == 0 and m.props[(h('pod_up3'), 'sensitive')] == 0
           and m.props[(h('pod_up1'), 'visible')] == 1 and m.props[(h('pod_up1'), 'sensitive')] == 0,
           'to the top: its arrow is hidden, the next row shows one; every arrow is insensitive (a picture, the row takes the tap)')
    # the click contexts are item ids: the arrow of an item that moved still moves that item
    run(m, lambda: arrow(m, 1))
    expect(m.fs[MENU_FILE] == b'13245\n', f'an arrow still moves its own item after rows moved ({m.fs[MENU_FILE]!r})')
    # a failed save changes nothing on the page (no move, no repaint)
    m = open_page(); m.fail.add(('write', MENU_TMP)); m.log = list(m.calls)
    arrow(m, 3)
    expect(m.names().count('widget_move') == 0 and 'image_base_set_image' not in m.names() and 'widget_invalidate_force' not in m.names(),
           'a failed save: the page is not touched')
    # the scroll position follows the moved row
    m = open_page()
    for i in range(9, 17): m.click(f'pod_row{i}')   # Favorites .. Tidal on: positions 5..12
    m.props[(sv(m), 'yoffset')] = 0
    m.click('pod_row17')   # CD Ripper joins at position 13 (y 676): the window scrolls down to it
    off = m.props[(sv(m), 'yoffset')]
    expect(off <= 13 * ROW_H and off + 398 >= 14 * ROW_H and off <= n * ROW_H - 398, f'a row shown far below scrolls into view (yoffset {off})')
    for _ in range(13):
        arrow(m, 17)
        off = m.props[(sv(m), 'yoffset')]
        top = m.props[(m.widgets['pod_row17'], 'y')]
        expect(off <= top and top + ROW_H <= off + 398 and off >= 0, f'an arrow keeps the moved row in view (row y {top}, yoffset {off})')
    expect(m.props[(m.widgets['pod_row17'], 'y')] == 0 and m.props[(sv(m), 'yoffset')] == 0, 'up to the top: the list is scrolled back to the top')

    # 21. What the page saved is what the menu shows, and the persistence survives a reboot (a new machine with the file)
    m = open_page(); m.log = list(m.calls)
    run(m, lambda: m.click('pod_row2')); run(m, lambda: m.click('pod_row6')); run(m, lambda: arrow(m, 6)); run(m, lambda: m.click('pod_row7'))
    saved = m.fs[MENU_FILE]
    expect(saved == b'134657\n', f'hide Albums, show Shuffle and move it up, show Genres: {saved!r}')
    run(m, lambda: m.click('pod_row11')); run(m, lambda: m.click('pod_row13')); saved = m.fs[MENU_FILE]
    expect(saved == b'134657ce\n', f'and show Recently Played and Composers: {saved!r}')
    want = [P.ITEMS[i].label for i in P.parse_menu(saved)] + ['Extras']
    mm = open_menu(saved)
    expect(shown_order(mm) == want and 'Albums' not in want, f'the menu after the page ({want})')
    again = open_page(saved); again.log = list(again.calls)
    expect(state(again)[0][:len(want) - 1] == want[:-1], 'and the page opens with it again')

    # 22. The assets: a row per item in the default order, each with an up arrow and a switch; the page is the stock list
    path = os.path.join(WORK, UI, 'm1plus_mainmenu.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    rows = [w for w in tree.walk() if w.type == 'list_item']
    expect([pod_i18n.shown_english(next(c for c in r.children if c.type == 'hscroll_label')) for r in rows] == items
           and [r.name for r in rows] == [f'pod_row{i}' for i in range(n)],
           'twenty rows named pod_row0..19: the items in the default order (the menu\'s Extras row is not on this page)')
    lv = tree.find('pod_listview')
    expect(lv.type == 'list_view' and lv.children[0].type == 'scroll_view' and tree.find('scroll_bar_m') is not None and lv.y + lv.h == CLIENT_H
           and max(r.y + r.h for r in rows) == n * ROW_H > lv.h,
           'stock list_view > scroll_view + scroll bar (twenty 52 px rows scroll), ending at the window bottom')
    for i, r in enumerate(rows):
        swi, upb = r.find(f'pod_switch{i}'), r.find(f'pod_up{i}')
        lab = next(c for c in r.children if c.type == 'hscroll_label')
        expect(swi.type == 'image' and swi.get('image') == ('sset_on' if i in P.DEFAULT_MENU else 'sset_off') and (swi.w, swi.h) == (57, 28)
               and swi.get('sensitive') == 'false' and swi.y == (ROW_H - 28) // 2 and swi.x + swi.w == r.w - 12,
               f'row {i}: the stock 57x28 switch image, insensitive, 12 px from the right')
        expect(upb.type == 'button' and upb.get('style:normal:icon') == 'expansion_2' and upb.get('style:pressed:icon') == 'expansion_2_down' and upb.get('sensitive') == 'false'
               and upb.x + upb.w == swi.x and upb.h == ROW_H and (upb.x, upb.w) == (ZX, ZW) and upb.w >= 44,
               f'row {i}: the stock chevron-up art on an insensitive button (a picture) right of the label, left of the switch; its rectangle is the arrow zone')
        ic = r.find('pod_icon')
        expect(ic is not None and ic.get('sensitive') == 'false' and lab.x + lab.w <= upb.x, f'row {i}: icon disc, label clear of the arrow')
    m = Machine()
    tree_n = asset_tree(path)
    for i, r in enumerate(node(tree_n, 'pod_scrollview').children):
        y = 50 + r.y + r.h // 2
        if y >= CLIENT_H: continue
        for x in (160, r.x + 220, r.x + 270):
            got = stock_target(m, asset_tree(path), x, y)
            expect(f'pod_row{i}' in got and (got[-1] == f'pod_row{i}' or x == 160), f'row {i}: a touch at x {x} goes to the row ({got}): the arrow is a picture, the row decides by the position')


SECTIONS = [entry_tests, arrange_tests, arrange_invalid_tests, arrange_model_tests, arrange_extras_tests, arrange_hit_tests, settings_tests, mainmenu_section, extrascfg_section]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

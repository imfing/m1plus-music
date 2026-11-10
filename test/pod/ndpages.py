"""The Navidrome pages (milestone 2, docs/modules/subsonic.md). Section `server` (task ND-12): the Server page (patch/ndserver.c, tools/pod_ndserver.py), on the real compiled payload under
Unicorn with the data layer (patch/sbapi.c) and its worker run by the test.

Proved: the built asset (the stock navbar, two cards of five rows at the Settings numbers, no glyph, a value and a chevron on the three field rows and none on the two actions, the page last in
the page table, no row table for patch/m1plus.c), the rows' words from the conf file (the host without scheme or path, the user, four dots for a password and nothing for none, the value taking
the room its text needs), each field row opening the Sign In page (tools/pod_ndserver.py build_login: the embedded keyboard on that row, Next / Sign In, the dots and the eye, the saved login in the rows, a saved password kept), a sign-in going through sba_conf_*_set and a ping with a spinner,
the page going back on a good answer and showing the reason under the card on a bad one (wrong password, no answer, certificate, clock, no Wi-Fi, an unwritable conf), a typed character ending a wait, Sync Now (confirm first, then the sync; nothing without a server or on a
No), Sign Out (confirm first, then the conf and the cache go, the downloaded music and its manifest stay), the strings in 13 languages, and the page's life (one open, destroy clears).

Section `root` (task ND-11): the root page (patch/ndroot.c, tools/pod_nd.py): the built asset (the large title, the grey status line under it with its glyph and spinner, the six rows, the footer, the navbar's "..." on the 214 slot and its card, the hidden
empty state, the page last in the table), the large title's collapse on both pages (the small title from SG_COLLAPSE, the fade while scrolled), the "..." card (Sync Now, Server Settings), each row's open (the library pages' openers trapped: albums_open_src, artists_open_src, songs_open_src, playlists_open_src), the card's Server Settings row and the Add Server pill
opening the Server page (nd_server_open), the status line per state (the glyph and "Synced 5m ago", Syncing... with the spinner, offline, Not Connected, "Not synced yet"), the footer's count, the empty state with no server saved
(list hidden, no sync asked), Downloaded with the Wi-Fi off, the sync asked on open (only when due), the page's refresh on the status record's counter, its life, the menu entry and the strings in 13 languages."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui
import pod_pages, pod_i18n, pod_ndserver, pod_nd
import pod_settings as ST

SB = sibling('sbapi')   # noqa: F821  (sibling: the harness helper of the pod tests)
RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
WIN = 0x24400000
EVT_DESTROY, EVT_CLICK, EVT_FG = O['EVT_DESTROY'], O['EVT_CLICK'], O['EVT_WINDOW_TO_FG']
LABELS = ('Server URL', 'Username', 'Password', 'Sync Now', 'Sign Out')
KEYS = ('Server', 'Server URL', 'Username', 'Password', 'Sync Now', 'Sign Out', 'Sync your Subsonic library now?', 'Sign out of Subsonic? Downloaded songs stay on the card.',
        'Enter a valid server address', 'Enter a valid username', 'Enter a valid password', 'Could not save settings', 'Add a server first', 'Connect to Wi-Fi first',
        'Syncing…', 'Sign In', 'Next', 'Connecting…', 'Incorrect username or password', "Can't connect to the server", 'Server certificate not trusted', 'Set the date and time first')
MUSIC, DLIDX = '/mnt/mmc/Subsonic/ab12cd34-Song.flac', SB.ND + '/dl.idx'
DOTS = '•' * 4
KB_PASS_MAX_ = 127   # patch/keyboard.h KB_PASS_MAX


def undo(s):
    """A mocked text as the user reads it: UTF-8 bytes read as latin-1 (the payload's own strings come back twice over from the mocked translation)."""
    for _ in range(2):
        try: s = s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError): break
    return s


def opened(conf=True, **kw):
    """The page open over a card with the PR's conf file (or none)."""
    m = SB.machine(conf=conf)
    m.window = WIN
    m.windows['m1plus_keyboard'] = 0   # (keyboard_open finds no window: the test calls the callbacks the keyboard would)
    for k, v in kw.items(): setattr(m, k, v)
    m.widgets['pod_scrollview'] = m.alloc(0x100)
    names = ['btn_return', 'btn_backtoplayer', 'label_title', 'img_nb_fade'] + [f'pod_{k}{i}' for i in range(5) for k in ('row', 'label')] + [f'pod_value{i}' for i in range(4)] + ['ns_spin', 'pod_gap0']
    for n in names: Machine.widget(m, n)   # noqa: F821
    for i, t in enumerate(LABELS): m.wtext[m.widgets[f'pod_label{i}']] = t
    for i in range(4): m.props[(m.widgets[f'pod_value{i}'], 'y')] = 0; m.props[(m.widgets[f'pod_value{i}'], 'h')] = ST.ROW_H
    for i in range(5): m.props[(m.widgets[f'pod_label{i}'], 'h')] = ST.ROW_H
    m.confirm_yes = True
    m.calls = []
    rc = m.call(PSYMS['nd_server_open'], count=20000000) & 0xffffffff
    assert rc == 0, f'nd_server_open returned {rc}'
    return m


def text(m, n): return undo(m.wtext.get(m.widgets[n], ''))
def toasts(m): return [undo(c[1]) for c in m.calls if c[0] == 'toast']
def confirms(m): return [undo(c[1]) for c in m.calls if c[0] == 'confirm']
def keyboards(m): return [c for c in m.calls if c == ('window_open', 'm1plus_keyboard')]


def click(m, i):
    """A tap on row i; the worker thread a request started is kept in m.thread."""
    fn_, ctx = m.bound[(m.widgets[f'pod_row{i}'], EVT_CLICK)]
    m.thread = None
    m.calls = []
    m.call(fn_, a0=ctx, a1=0, count=200000000)


def done(m, fn, s):
    """What the keyboard's Done key does: the page's callback with the text."""
    m.thread = None
    m.calls = []
    m.call(PSYMS[fn], a0=m.cstr(s), count=200000000)


def box(m, i):
    """(x, w) of the value label and the label's width after the last fit."""
    w = m.widgets[f'pod_value{i}']
    mv = [c for c in m.calls if c[0] == 'widget_move' and c[1] == w]
    rs = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == w]
    return (mv[-1][2], rs[-1][2]) if mv and rs else None


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def server_asset(ctx):
    """The built page: two cards of five rows at the Settings numbers, no glyph, a value and a chevron on the field rows, the page last in the table with no rows for patch/m1plus.c."""
    expect = ctx.expect
    P = pod_pages
    pg = P.NDSERVER_PAGE
    expect(P.PAGES[-2] is pg and P.PAGES[-1] is P.NDROOT_PAGE and pg.key == 'm1plus_ndserver' and pg.name == 'm1plus_ndserver_page' and pg.title == 'Server' and pg.kind == 'ndserver' and pg.rows == [],
           'the Server page is next to last of the page table (the root page follows), m1plus_ndserver, titled Server, and has no rows for the Settings binder (it binds its own)')
    expect([r.label for r in pg.layout if isinstance(r, P.Row)] == list(LABELS) and [P.row_kind(r) for r in pg.layout if isinstance(r, P.Row)] == ['value'] * 3 + ['action'] * 2
           and pg.layout[3] is P.GAP and P.ACT_NDVALUE in P.VALUE_ACTIONS and P.ACT_NDACT in P.ACTION_ACTIONS and P.VALUE_INIT[P.ACT_NDVALUE] == '',
           'Server URL, Username and Password are value rows, a gap, then Sync Now and Sign Out as action rows; a value starts empty')
    tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', 'm1plus_ndserver.bin'), 'rb').read())   # noqa: F821
    expect(tree.name == 'm1plus_ndserver_page' and tree.find('label_title') is not None and tree.find('btn_return') is not None and tree.find('btn_backtoplayer') is not None,
           'the stock navbar: title, Back and Now Playing')
    expect(pod_i18n.shown_english(tree.find('label_title')) == 'Server', 'the navbar reads Server')
    sv = tree.find('pod_row0')
    expect(sv is not None, 'pod_row0 exists')
    column = [w for w in tree.walk() if w.name in ('pod_top', 'pod_end', 'pod_gap0') or w.name.startswith('pod_row')]
    ys = {w.name: w.y for w in column}
    placed = dict((k, y) for k, y in [(w.name, y) for w, y in zip(column, [ys[w.name] for w in column])])
    B = pod_ndserver.BIG_H
    expect(placed['pod_top'] == 0 and placed['pod_row0'] == B and placed['pod_row1'] == B + ST.ROW_H and placed['pod_row2'] == B + 2 * ST.ROW_H
           and placed['pod_gap0'] == B + 3 * ST.ROW_H and placed['pod_row3'] == B + 3 * ST.ROW_H + ST.GAP_H and placed['pod_row4'] == B + 4 * ST.ROW_H + ST.GAP_H
           and placed['pod_end'] == B + 5 * ST.ROW_H + ST.GAP_H and placed['pod_end'] + ST.END_H <= 400 + O['SG_COLLAPSE'] + pod_ndserver.END_MARGIN, f'the column: the large title\'s item, three rows, a gap, two rows, the end spacer ({placed})')
    end = placed['pod_end'] + [w for w in column if w.name == 'pod_end'][0].h
    expect(end - 400 >= O['SG_COLLAPSE'] and end - 400 == O['SG_COLLAPSE'] + pod_ndserver.END_MARGIN, f'the end spacer pads the 350 px of content to the list plus the collapse offset and 10 px, so the page can scroll the title away ({end} px)')
    big = tree.find('pod_big')
    expect(big is not None and big.get('tr_text') == 'Server' and big.x == O['SG_TITLE_X'] and big.w == O['SG_TITLE_W'] and big.h == O['PP_TITLE_H'] and big.get('sensitive') == 'false'
           and big.get('style:normal:font_size') == str(O['PP_TITLE_PX']) and big.get('style:normal:text_color') == '#FFFFFF', 'the large title: the shared Podcasts heading (12, 296 wide, 52 high, 32 px white), insensitive')
    small = tree.find('label_title')
    expect(small.get('visible') == 'false' and small.get('sensitive') == 'false', 'the navbar\'s small title is hidden at rest (it fades in when the large one has scrolled away)')
    expect(tree.find('img_nb_fade') is not None and tree.find('img_nb_fade').get('visible') == 'false' and tree.find('pod_scrollview') is not None, 'the fade under the bar (hidden at rest) and the scroll view are there')
    for i, lab in enumerate(LABELS):
        row = tree.find(f'pod_row{i}')
        l = tree.find(f'pod_label{i}')
        kids = {c.name for c in row.children}
        expect(pod_i18n.shown_english(l) == lab and l.get('tr_text') == lab, f'row {i} reads {lab}')
        expect('pod_icon' not in kids and 'pod_swatch' not in kids, f'row {i} has no glyph')
        expect(('pod_chevron' in kids) == (i < 3) and (f'pod_value{i}' in kids) == (i < 4) and ('ns_spin' in kids) == (i == 3) and not ({f'pod_switch{i}', f'pod_check{i}'} & kids),
               f'row {i}: the chevron on the field rows only; a value label on them and on Sync Now, which also has the spinner')
        expect(l.x == ST.CM + ST.PAD, f'row {i}: the label starts at the card text edge, no glyph column')
        if i == 3:
            sp = tree.find('ns_spin')
            expect(sp.get('visible') == 'false' and sp.get('image') == 'wf_spin0' and sp.w == pod_ndserver.SYNC_SPIN_PX == 14 and tree.find('pod_value3').get('text') == '' and tree.find('pod_value3').x + tree.find('pod_value3').w == pod_ndserver.VALUE_RIGHT,
                   'Sync Now: the spinner (the Wi-Fi page\'s frame, hidden) and an empty grey value ending where the field rows\' values do')
        if i < 3:
            v = tree.find(f'pod_value{i}')
            expect(v.get('text') == '' and v.x + v.w == pod_ndserver.VALUE_RIGHT, f'row {i}: an empty value label ending at the chevron\'s gap')
    expect(pod_ndserver.VALUE_RIGHT == 280 and pod_ndserver.LABEL_X == 24, 'the payload\'s NS_VALUE_RIGHT 280 and NS_LABEL_X 24 are the asset\'s numbers')
    src = open(os.path.join(ROOT, 'patch', 'ndserver.c'), encoding='utf-8').read()   # noqa: F821
    expect('#define NS_VALUE_RIGHT 280' in src and '#define NS_LABEL_X 24' in src, 'ndserver.c repeats those numbers')
    bad = [w.name for w in tree.walk() if w.get('tr_text') is None and w.get('text') not in (None, '')]
    expect(not bad, f'every text is a tr_text key ({bad})')


def server_rows(ctx):
    """The values from the conf file; the fit; a page with no server."""
    expect = ctx.expect
    m = opened()
    expect([text(m, f'pod_value{i}') for i in range(3)] == ['nd.example:4533', 'alice', DOTS], 'rows read the host (no scheme, no path), the user and four dots for the password; never the password')
    expect(SB.PASSWORD not in ''.join(m.wtext.values()), 'the password text is on no widget')
    x, w = box(m, 0)
    expect(x + w == 280 and w == 8 * len('nd.example:4533') + 6, f'the value takes the room its text needs, right aligned at 280 (x {x}, w {w})')
    lab = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['pod_label0']][-1]
    expect(lab[2] == 280 - w - 8 - 24, 'the label gets the rest')
    m = opened(conf=False)
    expect([text(m, f'pod_value{i}') for i in range(3)] == ['', '', ''], 'no server: three empty values')
    m = opened()
    m.call(PSYMS['sba_conf_user_set'], a0=m.cstr('zed'), count=20000000)
    m.calls = []
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(text(m, 'pod_value1') == 'zed', 'coming back to the page (EVT_WINDOW_TO_FG) reads the login again')
    long = 'a-very-long-server-name.example.org'
    m = SB.machine(conf=False); m.put(SB.CONF, f'https://{long}|alice|pw'.encode())
    m.window = WIN
    for n in [f'pod_{k}{i}' for i in range(5) for k in ('row', 'label')] + [f'pod_value{i}' for i in range(3)] + ['btn_return', 'btn_backtoplayer']: Machine.widget(m, n)   # noqa: F821
    for i, t in enumerate(LABELS): m.wtext[m.widgets[f'pod_label{i}']] = t
    m.call(PSYMS['nd_server_open'], count=20000000)
    x, w = box(m, 0)
    expect(x + w == 280 and x >= 24 + 8 * len('Server URL') + 6 + 10, f'a long host is cut to the room the label leaves (x {x}, w {w})')
    # one open; the destroy clears the state
    expect(m.call(PSYMS['nd_server_open'], count=20000000) == 0 and not [c for c in m.calls if c[0] == 'window_open'], 'a second open does nothing (0)')
    fn_, ctx_ = m.bound[(m.window, EVT_DESTROY)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    m.calls = []
    expect(m.call(PSYMS['nd_server_open'], count=20000000) == 0 and ('window_open', 'm1plus_ndserver') in m.calls, 'after the destroy the page opens again')
    m = SB.machine(); m.window = 0
    expect(m.call(PSYMS['nd_server_open'], count=20000000) & 0xffffffff == 0xffffffff, 'a window that will not open: -1')


UI_LOGIN = os.path.join(RAW, 'ui', 'm1plus_ndlogin.bin')
WIN_LOGIN = 0x24500000
EVT_PDOWN, EVT_PUP = O['EVT_POINTER_DOWN'], O['EVT_POINTER_UP']


def login(conf=True, row=0, **kw):
    """The Server page open, then a tap on its field row `row`: the Sign In page and its embedded keyboard (m.hist keeps every call since)."""
    m = opened(conf=conf, **kw)
    m.windows['m1plus_ndlogin'] = WIN_LOGIN
    for w in awtk_ui.parse(open(os.path.join(WORK, UI_LOGIN), 'rb').read()).walk():   # noqa: F821
        if w.name: m.setword(Machine.widget(m, w.name) + O['W_W'], w.w)   # noqa: F821  (az_fit reads the label's width from the widget)
    m.hist = []
    click(m, row)
    m.hist += m.calls
    return m


def rec(m, fn, **kw):
    m.thread = None
    m.call(fn, count=200000000, **kw)
    m.hist += m.calls


NL_TIMER = 6 * 4 + 6 * 4 + 3 * (KB_PASS_MAX_ + 1) + 8 * 4   # patch/ndserver.c nl: six widgets, v[3] and h[3], three field texts, eight ints, then the timer


def live(m):
    """1 while the Sign In page's timer is running (its id is in the page's state)."""
    return 1 if m.word(PSYMS['nl'] + NL_TIMER) else 0


def kclick(m, name):
    fn_, c = m.bound[(m.widgets[name], EVT_CLICK)]
    rec(m, fn_, a0=c, a1=0)


def ktap(m, name): kclick(m, name)


def hit(m, i):
    kclick(m, f'nl_hit{i}')


def kkeys(m):
    """The labels of the char keys shown now."""
    return {text(m, f'kb_k{i}'): i for i in range(26) if m.props.get((m.widgets[f'kb_k{i}'], 'visible'), 1) and text(m, f'kb_k{i}')}


def ktype(m, s):
    for c in s:
        if c == ' ':
            kclick(m, 'kb_space'); continue
        ks = kkeys(m)
        if c not in ks:
            kclick(m, 'kb_mode'); ks = kkeys(m)
        assert c in ks, f'no key for {c!r}'
        kclick(m, f'kb_k{ks[c]}')


def kdel(m, n=1):
    for _ in range(n):
        have = len(m.timers)
        for ev in (EVT_PDOWN, EVT_PUP):
            e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e, ev)
            fn_, c = m.bound[(m.widgets['kb_del'], ev)]
            rec(m, fn_, a0=c, a1=e)
        del m.timers[have:]


def last(m, kind, name, pos=2):
    for c in reversed(m.hist):
        if c[0] == kind and c[1] == m.widgets[name]: return c[pos]
    return None


def key(m): return last(m, 'widget_set_tr_text', 'kb_go')


def go_on(m):
    st = last(m, 'widget_set_state', 'kb_go')
    return m.props.get((m.widgets['kb_go'], 'sensitive')) == 1 and st == 'normal'


def shown(m, n): return m.props.get((m.widgets[n], 'visible'), 1)
def fld(m): return (m.props.get((m.widgets['kb_field'], 'x')), m.props.get((m.widgets['kb_field'], 'y')))
def said(m, n): return undo(last(m, 'widget_set_text_utf8', n) or '')
def closed(m): return sum(1 for c in m.hist if c[0] == 'navigator_back')
def settle(m, site, ticks=1):
    """The worker's request run against the scripted site, then the page's timer ticks."""
    m.curl_site = site
    if m.thread: SB.drain(m, m.thread); m.thread = None
    for _ in range(ticks):
        if live(m): rec(m, PSYMS['nl_tick'], a0=0)


def server_login_asset(ctx):
    """The Sign In page's built asset: registered, the card and its rows at the Join Wi-Fi Network page's measures, the field, the eye, the line under the card, everything above the candidate strip, no accent."""
    expect = ctx.expect
    import re
    import pod_keyboard as PK
    from awtk_text import Ttf, StbText
    pg = pod_pages.NDLOGIN_PAGE
    expect(pg in pod_pages.PAGES and pod_pages.PAGES[-3] is pg and pg.kind == 'ndlogin' and pg.key == 'm1plus_ndlogin' and pg.title == 'Sign In' and pg.rows == [], 'the Sign In page is registered (before the Server page), titled Sign In')
    tree = awtk_ui.parse(open(os.path.join(WORK, UI_LOGIN), 'rb').read())   # noqa: F821
    by = {w.name: w for w in tree.walk() if w.name}
    expect(tree.name == pg.name and by['label_title'].get('tr_text') == pod_i18n.key_for('Sign In'), 'the stock navbar reads Sign In')
    need = ('btn_return', 'btn_backtoplayer', 'nl_card', 'nl_hair0', 'nl_hair1', 'kb_field', 'kb_hint', 'kb_text', 'kb_caret', 'kb_clear', 'nl_eye', 'nl_spin', 'nl_busy', 'nl_err', 'kb_pad', 'kb_strip', 'kb_stem', 'kb_pop', 'kb_go') + \
        tuple(f'nl_{k}{i}' for i in range(3) for k in ('v', 'h', 'hit'))
    expect(all(n in by for n in need) and all(f'kb_k{i}' in by for i in range(26)), f'the page\'s and the keyboard\'s widgets are there: {[n for n in need if n not in by]}')
    box = lambda n: (by[n].x, by[n].y, by[n].w, by[n].h)
    expect(box('nl_card') == (10, 56, 300, 144) and by['nl_card'].get('style:normal:bg_color') == ST.CARD_RGB and by['nl_card'].get('sensitive') == 'false' and box('nl_hair0')[1] == 103 and box('nl_hair1')[1] == 151
           and box('nl_hair0')[0] == 24 and box('nl_hair0')[2] == 286, 'one Settings card of three 48 px rows (y 56, 104, 152) with the hairlines between them')
    f = by['kb_field']
    expect((f.x, f.y, f.w, f.h) == (24, 56, 272, 48) and by['kb_text'].w == f.w and by['kb_clear'].x == 272 - 36 and by['kb_caret'].y == 13 and f.get('style:normal:bg_color') == '#00000000', 'the keyboard\'s field starts on the first row, ink edge to ink edge')
    expect([box(f'nl_hit{i}') for i in range(3)] == [(10, 56, 300, 48), (10, 104, 300, 48), (10, 152, 254, 48)] and box('nl_eye') == (264, 152, 46, 48) and by['nl_eye'].get('style:normal:icon') == 'wf_eyeoff'
           and all(by[f'nl_hit{i}'].get('enable') == 'true' for i in range(3)), 'three buttons take the row taps (the Password row ends at the eye); the eye starts as eye-off')
    expect(all(box(f'nl_v{i}') == (24, 56 + 48 * i, 272, 48) == box(f'nl_h{i}') for i in range(3)) and [by[f'nl_h{i}'].get('tr_text') for i in range(3)] == [pod_i18n.key_for(k) for k in ('Server URL', 'Username', 'Password')]
           and all(by[f'nl_{k}{i}'].get('visible') == 'false' and by[f'nl_{k}{i}'].get('sensitive') == 'false' for i in range(3) for k in ('v', 'h')) and all(by[f'nl_h{i}'].get('style:normal:text_color') == PK.KB_GREY and by[f'nl_v{i}'].get('style:normal:text_color') == PK.KB_INK for i in range(3)),
           'the static labels sit where the field text does: the ink value and the grey placeholder (the row\'s name), hidden and insensitive')
    expect(box('nl_spin') == (24, 211, 14, 14) and by['nl_busy'].get('tr_text') == pod_i18n.key_for('Connecting…') and box('nl_busy')[:2] == (46, 208) and box('nl_err')[:2] == (24, 208) and by['nl_err'].get('style:normal:text_color') == ST.GREY
           and all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' for n in ('nl_spin', 'nl_busy', 'nl_err')), 'under the card one 20 px line: the spinner and "Connecting...", or the grey error text; all start hidden')
    ends = {n: by[n].y + by[n].h for n in ('nl_card', 'nl_eye', 'nl_hit2', 'nl_err', 'nl_busy', 'kb_field')}
    names = [c.name for c in tree.children]
    expect(all(v <= PK.STRIP_Y for v in ends.values()) and by['kb_strip'].y == PK.STRIP_Y and names.index('kb_field') > names.index('nl_hit2') and names[-4:] == ['kb_pad', 'kb_strip', 'kb_stem', 'kb_pop'],
           f'everything ends above the candidate strip (y {PK.STRIP_Y}): {ends}; the field is over the row buttons, the pad ends the page')
    cols = [v for w in tree.walk() for k, v in w.props if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6,8}', v) and 'color' in k]
    neutral = lambda c: (lambda r, g, b: max(r, g, b) - min(r, g, b) <= 12)(*(int(c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)))
    expect(all(neutral(c) for c in cols), 'no accent colour')
    src = open(os.path.join(ROOT, 'patch', 'ndserver.c'), encoding='utf-8').read()   # noqa: F821
    expect('#define NL_Y0 56' in src and '#define NL_PITCH 48' in src and '#define NL_X 24' in src and '#define NL_TW 232' in src and '#define NL_CY 13' in src and pod_ndserver.NL_TW == 232 and pod_ndserver.NL_Y0 == 56 and pod_ndserver.NL_ROW_H == 48,
           'ndserver.c repeats the asset\'s numbers')
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))   # noqa: F821
    for loc in pod_i18n.LOCALES:
        tx = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        w = lambda t, px: StbText(font, px).layout(t)[1]
        bad = [k for k, px, room in (('Sign In', 20, by['label_title'].w), ('Server URL', 18, 232), ('Username', 18, 232), ('Password', 18, 232), ('Next', 15, PK.KB_MODE_W - 8), ('Sign In', 15, PK.KB_MODE_W - 8),
                                      ('Connecting…', 16, by['nl_busy'].w)) + tuple((k, 16, by['nl_err'].w) for k in LOGIN_ERRORS) if w(tx(k), px) > room]
        expect(not bad, f'{loc}: the title, the placeholders, the action keys and the lines under the card fit their rooms ({bad})')


LOGIN_ERRORS = ('Incorrect username or password', "Can't connect to the server", 'Server certificate not trusted', 'Set the date and time first', 'Connect to Wi-Fi first', 'Could not save settings',
                'Enter a valid server address', 'Enter a valid username', 'Enter a valid password')


def server_login_open(ctx):
    """Each field row opens the Sign In page with the keyboard on that row; the saved login is in the rows (the password as four dots, never the text); a first setup starts at http://."""
    expect = ctx.expect
    for i in range(3):
        m = login(row=i)
        expect(('window_open', 'm1plus_ndlogin') in m.hist and not keyboards(m) and fld(m) == (24, 56 + 48 * i), f'row {i} opens the Sign In page, no keyboard page, the field on row {i}')
        expect(m.bound[(m.widgets['btn_return'], EVT_CLICK)][0] == PSYMS['pod_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], EVT_CLICK)][0] == PSYMS['pod_on_player'], 'Back (cancel) and Now Playing are the stock ones')
    m = login(row=0)
    expect(text(m, 'kb_text') == SB.URL, 'the address row shows the saved address')
    expect(shown(m, 'nl_v1') == 1 and said(m, 'nl_v1') == 'alice' and shown(m, 'nl_h1') == 0 and shown(m, 'nl_v2') == 1 and said(m, 'nl_v2') == DOTS and SB.PASSWORD not in ''.join(m.wtext.values()),
           'the other rows show the user and four dots; the password text is on no widget')
    expect(key(m) == 'Sign In' and go_on(m), 'a saved login is valid: the action key reads Sign In and works')
    m = login(row=1)
    expect(text(m, 'kb_text') == 'alice' and shown(m, 'nl_v0') == 1 and shown(m, 'nl_v1') == 0, 'the user row: the field has the name, the address is a label')
    m = login(row=2)
    expect(text(m, 'kb_text') in ('', None) and shown(m, 'nl_v2') == 0 and shown(m, 'nl_h2') == 0 and key(m) == 'Sign In' and go_on(m), 'the password row starts empty (the saved one is kept unless typed over), Sign In works')
    # nothing saved: http:// , grey placeholders, Next dimmed
    m = login(conf=False, row=0)
    expect(text(m, 'kb_text') == 'http://' and key(m) == 'Next' and not go_on(m) and shown(m, 'nl_h1') == 1 and shown(m, 'nl_h2') == 1 and shown(m, 'nl_v1') == 0 and shown(m, 'nl_v0') == 0,
           'a first setup: the address starts as http://, Next is dimmed, the other rows show their grey placeholders')
    # the mode of each field
    m = login(row=0)
    expect(not kkeys(m).get('Q') and 'q' in kkeys(m), 'the address row is the English lowercase layout (KB_PASSWORD), unmasked')
    expect(text(m, 'kb_text') == SB.URL, 'and shows the address as text, not dots')
    hit(m, 2)
    expect(set(text(m, 'kb_text') or '') <= {'•'}, 'the password row masks')


def server_login_flow(ctx):
    """A first setup field by field: Next moves on when the field is valid, Sign In saves and pings, the page waits with a spinner and goes back on a good answer."""
    expect = ctx.expect
    m = login(conf=False, row=0)
    ktype(m, 'nd.example:4533')
    expect(text(m, 'kb_text') == 'http://nd.example:4533' and key(m) == 'Next' and go_on(m), 'a valid address: Next works')
    kdel(m, 20)
    expect(not go_on(m), 'an emptied address: Next dimmed')
    ktype(m, 'ftp://x'); kdel(m, 20)
    ktype(m, 'http://')
    expect(not go_on(m), 'http:// alone is no address: dimmed')
    ktype(m, 'a b')
    expect(not go_on(m), 'a space in it: dimmed')
    kdel(m, 3)
    ktype(m, 'nd')
    kclick(m, 'kb_go')
    expect(fld(m) == (24, 104) and text(m, 'kb_text') in ('', None) and shown(m, 'nl_v0') == 1 and said(m, 'nl_v0') == 'http://nd' and key(m) == 'Next' and not go_on(m) and not m.fs.get(SB.CONF),
           'Next moves the field to the Username row, the address becomes a label, nothing is saved yet, Next is dimmed on the empty name')
    ktype(m, 'Bob')
    expect(go_on(m) and key(m) == 'Next', 'a name: Next works')
    kclick(m, 'kb_go')
    expect(fld(m) == (24, 152) and key(m) == 'Next' and not go_on(m), 'the password row: the login is not whole, Next is dimmed')
    ktype(m, 'pw1')
    expect(key(m) == 'Sign In' and go_on(m) and text(m, 'kb_text') == '•••', 'a password (dots): the key reads Sign In and works')
    # tapping rows moves the field and keeps the values
    hit(m, 0)
    expect(fld(m) == (24, 56) and text(m, 'kb_text') == 'http://nd' and said(m, 'nl_v2') == '•••' and key(m) == 'Sign In', 'a tap on the address row: the field is there with its text, the password row shows three dots')
    hit(m, 2)
    # the eye
    fn_, c = m.bound[(m.widgets['nl_eye'], EVT_CLICK)]
    rec(m, fn_, a0=c, a1=0)
    expect(text(m, 'kb_text') == 'pw1' and [m.props.get((m.widgets['nl_eye'], f'style:{s}:icon')) for s in ('normal', 'over', 'pressed')] == ['wf_eye'] * 3, 'the eye shows the password and turns open')
    hit(m, 0)
    expect(said(m, 'nl_v2') == 'pw1', 'with the eye open the label shows the text too')
    hit(m, 2)
    rec(m, fn_, a0=c, a1=0)
    expect(text(m, 'kb_text') == '•••', 'the eye closes again')
    # Sign In
    m.thread = None
    kclick(m, 'kb_go')
    expect(SB.CONF not in m.fs and m.thread is not None and closed(m) == 0, 'Sign In asks for a ping and saves nothing yet; the page stays')
    expect(shown(m, 'nl_busy') == 1 and shown(m, 'nl_spin') == 1 and shown(m, 'nl_err') == 0 and not go_on(m) and live(m) == 1 and ('timer_add', PSYMS['nl_tick'], 250) in m.calls and ('timer_add', PSYMS['ls_spin_tick'], 250) in m.calls,
           'the spinner and Connecting... show, the action key is dimmed, the page\'s 250 ms timer and the shared spinner timer run')
    f0 = len([c for c in m.hist if c[0] == 'image_base_set_image' and c[1] == m.widgets['nl_spin']])
    th = m.thread; rec(m, PSYMS['ls_spin_tick'], a0=0x5a5a5a50); m.thread = th
    f1 = [c for c in m.hist if c[0] == 'image_base_set_image' and c[1] == m.widgets['nl_spin']]
    expect(len(f1) == f0 + 1 and undo(f1[-1][2]) == 'wf_spin1', 'the shared ls_spin timer turns the frame (called with stock\'s timer_info_t: the argument is not read)')
    rec(m, PSYMS['nl_tick'], a0=0); m.thread = th
    expect(len([c for c in m.hist if c[0] == 'image_base_set_image' and c[1] == m.widgets['nl_spin']]) == f0 + 1, 'the page\'s own tick no longer steps the frames')
    site = ok_site()
    settle(m, site, 0)
    expect(site.views()[:1] == ['ping'], 'the request is the ping')
    spins = [c for c in m.hist if c[0] == 'image_base_set_image' and c[1] == m.widgets['nl_spin']]
    settle(m, site, 1)
    expect(closed(m) == 1 and site.views().count('ping') >= 1 and SB.conf_is(m.fs[SB.CONF], 'http://nd', 'Bob', 'pw1'), 'a good answer: the login is saved and the page goes back')
    expect(m.thread is not None or SB.busy(m), 'and the library sync is asked')
    SB.drain(m, m.thread) if m.thread else None
    expect(site.views()[:2] == ['ping', 'getAlbumList2'], f'the ping goes first, then the sync ({site.views()[:3]})')
    expect(not spins or all(str(undo(s[2])).startswith('wf_spin') for s in spins), 'the spinner frames are the Wi-Fi page\'s')
    # the end of the page wipes it
    fn_, c = m.bound[(WIN_LOGIN, EVT_DESTROY)]
    rec(m, fn_, a0=c, a1=0)
    expect(live(m) == 0 and m.call(PSYMS['nd_server_open'], count=20000000) == 0, 'the destroy removes the timer')
    expect(set(m.u.mem_read(PSYMS['nl'], NL_TIMER + 4)) == {0}, 'and wipes the page\'s state with the typed password')


def server_login_fail(ctx):
    """The ping's failures are a grey line under the card; the page stays with its fields; an edit clears the line; a refusal and the missing conditions are the line too."""
    expect = ctx.expect
    def attempt(site, wifi=1, conf=True, edit=None):
        m = login(conf=conf, row=2)
        m.wifi = wifi
        SB.seed(m, SB.ND + '/albums.idx', 'album', [dict(id='a1', name='One')])
        m.old_conf = m.fs.get(SB.CONF)
        ktype(m, 'x')   # (a changed password: the typo)
        if edit: edit(m)
        m.thread = None
        kclick(m, 'kb_go')
        if m.thread: settle(m, site, 1)
        return m
    cases = (('a wrong user or password (Subsonic 40)', SB.Site(ping={'body': SB.err_json(40)}), 'Incorrect username or password'),
             ('an unreachable server', SB.Site(ping={'rc': 7, 'code': 0}), "Can't connect to the server"),
             ('a web page', SB.Site(ping={'body': b'<html>proxy</html>'}), "Can't connect to the server"),
             ('HTTP 404', SB.Site(ping={'rc': 22, 'code': 404}), "Can't connect to the server"))
    for what, site, msg in cases:
        m = attempt(site)
        expect(m.fs.get(SB.CONF) == m.old_conf and SB.ND + '/albums.idx' in m.fs, f'{what}: the saved login and the cache are untouched')
        expect(said(m, 'nl_err') == msg and shown(m, 'nl_err') == 1 and shown(m, 'nl_busy') == 0 and shown(m, 'nl_spin') == 0 and closed(m) == 0 and go_on(m) and not live(m),
               f'{what}: "{msg}" under the card, no spinner, the page stays, Sign In works again, no timer')
    m = attempt(SB.Site(ping={'body': SB.err_json(40)}))
    ktype(m, 'x')
    expect(shown(m, 'nl_err') == 0, 'a typed character clears the line')
    m = attempt(None, wifi=0)
    expect(said(m, 'nl_err') == 'Connect to Wi-Fi first' and m.thread is None and not live(m) and shown(m, 'nl_busy') == 0, 'no Wi-Fi: the line says so, nothing is queued, no timer; the saved login stays')
    # a good login after a failure (the same page)
    m = login(row=2)
    m.curl_site = SB.Site(ping={'body': SB.err_json(40)})
    m.thread = None; kclick(m, 'kb_go'); settle(m, m.curl_site, 1)
    ktype(m, 'z')
    m.thread = None; kclick(m, 'kb_go')
    expect(SB.conf_pw(m.fs[SB.CONF], SB.PASSWORD) and m.thread is not None, 'a new password after a failure: asked again, not saved yet')
    settle(m, ok_site(), 1)
    expect(closed(m) == 1 and SB.conf_pw(m.fs[SB.CONF], 'z'), 'and on a good answer it is saved and the page goes back')
    m = login(row=2)
    m.present.discard(SB.CA)
    m.thread = None; kclick(m, 'kb_go')
    expect(said(m, 'nl_err') == 'Server certificate not trusted' and m.thread is None and not live(m), 'https without the CA bundle: the certificate line, nothing asked')
    m = login(row=2)
    m.wall = 1700000000
    m.thread = None; kclick(m, 'kb_go')
    expect(said(m, 'nl_err') == 'Set the date and time first' and m.thread is None and not live(m), 'https with the clock never set: the date line, nothing asked')
    # edits while waiting
    m = login(row=2)
    m.thread = None; kclick(m, 'kb_go')
    expect(shown(m, 'nl_busy') == 1, 'waiting')
    ktype(m, 'q')
    expect(shown(m, 'nl_busy') == 0 and not live(m) and closed(m) == 0, 'a character typed while waiting stops the wait (the login on screen is not the one asked)')
    m = login(row=2)
    m.thread = None; kclick(m, 'kb_go')
    for _ in range(170):
        if live(m): rec(m, PSYMS['nl_tick'], a0=0)
    expect(said(m, 'nl_err') == "Can't connect to the server" and not live(m), 'no answer in 40 s: the line, the timer gone')
    # sign in with A, edit while A's ping is in flight, sign in with B: B is pinged on its own and only B's answer saves B
    def resign(answers):
        m = login(row=2)
        ktype(m, 'x')
        m.thread = None; kclick(m, 'kb_go')
        th = m.thread
        ktype(m, 'y')
        m.thread = None; kclick(m, 'kb_go')
        seen = []
        def ping(url, opts):
            seen.append(SB.parse_qs(SB.urlparse(url).query)['t'][0])
            return answers[len(seen) - 1]
        m.curl_site = SB.Site(ping=ping, **{k: v for k, v in ok_site().routes.items() if k != 'ping'})
        SB.drain(m, th)
        m.thread = None
        for _ in range(3):
            if live(m): rec(m, PSYMS['nl_tick'], a0=0)
        return m, seen
    good, bad = {'body': SB.ok_json()}, {'body': SB.err_json(40)}
    m, seen = resign([good, good])
    expect(len(seen) == 2 and seen[0] != seen[1], 'A, an edit, then B: two pings go out (B is not folded into A\'s)')
    expect(SB.conf_pw(m.fs[SB.CONF], 'xy') and closed(m) == 1, 'B answered: B is saved (the verified login)')
    m, seen = resign([good, bad])
    expect(len(seen) == 2 and SB.conf_pw(m.fs[SB.CONF], SB.PASSWORD) and closed(m) == 0 and said(m, 'nl_err') == 'Incorrect username or password',
           'A answered OK but B failed: nothing is saved, the old login stays, the line says why')
    # the saved conf cannot be written
    m = login(row=1)
    ktype(m, 'x')
    old = m.fs[SB.CONF]
    m.fail.add(('open', SB.CONF + '.tmp'))
    m.thread = None; kclick(m, 'kb_go')
    settle(m, ok_site(), 1)
    m.fail.discard(('open', SB.CONF + '.tmp'))
    expect(said(m, 'nl_err') == 'Could not save settings' and not live(m) and closed(m) == 0 and m.fs[SB.CONF] == old, 'a good ping but a conf that cannot be written: its line, the page stays, the old login stays')
    # the password left empty keeps the saved one; typing and emptying does not
    m = login(row=0)
    kdel(m, 40)
    ktype(m, 'https://other.example')
    expect(text(m, 'kb_text') == 'https://other.example', 'the address is edited')
    SB.seed(m, SB.ND + '/albums.idx', 'album', [dict(id='a1', name='One')])
    old = m.fs[SB.CONF]
    m.thread = None; kclick(m, 'kb_go')
    expect(m.fs[SB.CONF] == old and SB.ND + '/albums.idx' in m.fs and m.thread is not None, 'a new address: nothing is saved and the cache stays until the ping answers')
    settle(m, ok_site(), 1)
    expect(m.fs[SB.CONF] == b'https://other.example|alice|' + SB.secret(SB.PASSWORD).encode() and SB.ND + '/albums.idx' not in m.fs and closed(m) == 1,
           'a good answer: the secret of the password left alone stays in the file, the other server\'s cache goes')
    # the same server and user (a password edit): the cache stays
    m = login(row=2)
    SB.seed(m, SB.ND + '/albums.idx', 'album', [dict(id='a1', name='One')])
    ktype(m, 'z')
    m.thread = None; kclick(m, 'kb_go')
    settle(m, ok_site(), 1)
    expect(SB.conf_is(m.fs[SB.CONF], SB.URL, 'alice', 'z') and SB.ND + '/albums.idx' in m.fs and closed(m) == 1, 'the same server and user: the new password is saved and the cache is kept')
    m = login(row=2)
    ktype(m, 'a'); kdel(m, 1)
    expect(not go_on(m) and key(m) == 'Next', 'a password typed and emptied is empty: not the saved one any more, the key is dimmed')


def server_login(ctx):
    for f in (server_login_asset, server_login_open, server_login_flow, server_login_fail): f(ctx)


def signin_direct(conf=False):
    """The Sign In page opened the way the root's Add Server does it (nd_signin_open): no Server page under it."""
    m = SB.machine(conf=conf)
    m.window = WIN
    m.windows['m1plus_keyboard'] = 0
    m.windows['m1plus_ndlogin'] = WIN_LOGIN
    for w in awtk_ui.parse(open(os.path.join(WORK, UI_LOGIN), 'rb').read()).walk():   # noqa: F821
        if w.name: m.setword(Machine.widget(m, w.name) + O['W_W'], w.w)   # noqa: F821
    m.confirm_yes = True
    m.hist = []
    m.calls = []
    rc = m.call(PSYMS['nd_signin_open'], count=20000000) & 0xffffffff
    assert rc == 0, f'nd_signin_open returned {rc}'
    m.hist += m.calls
    return m


def server_signin(ctx):
    """Signed out, Add Server is the Sign In page itself; a good sign-in goes back to the page it came from (the root), which then shows Syncing...; signed in, a field edit returns to the Server page as before."""
    expect = ctx.expect
    m = signin_direct()
    expect(('window_open', 'm1plus_ndlogin') in m.hist and ('window_open', 'm1plus_ndserver') not in m.hist and fld(m) == (24, 56) and text(m, 'kb_text') == 'http://', 'nd_signin_open: the Sign In page on the Server URL row, no Server page opened')
    ktype(m, 'nd.example:4533'); kclick(m, 'kb_go')
    ktype(m, 'Bob'); kclick(m, 'kb_go')
    ktype(m, 'pw1')
    m.thread = None
    kclick(m, 'kb_go')
    site = ok_site()
    settle(m, site, 1)
    expect(closed(m) == 1 and SB.conf_is(m.fs[SB.CONF], 'http://nd.example:4533', 'Bob', 'pw1') and ('window_open', 'm1plus_ndserver') not in m.hist,
           'a good sign-in from the signed-out state: the login is saved and the page goes back once, to the root (the Server page was never opened)')
    st, code = SB.state(m, SB.K['SYNC'])
    expect(st == SB.ST['LOAD'] or m.thread is not None or SB.busy(m), 'and the sync is asked: the root, coming to the front, reads it as running (Syncing...)')
    m = opened(conf=False)
    sh = lambda n: m.props.get((m.widgets[n], 'visible'))
    expect(sh('pod_row3') == 0 and sh('pod_row4') == 0 and sh('pod_gap0') == 0 and m.props.get((m.widgets['pod_row3'], 'sensitive')) == 0 and text(m, 'pod_value3') == '',
           'the Server page with no server saved shows the three rows only: Sync Now, Sign Out and the gap are hidden')
    m = opened()
    expect(sh('pod_row3') == 1 and sh('pod_row4') == 1 and sh('pod_gap0') == 1, 'with a server saved they are shown')


def server_sync(ctx):
    """Sync Now's row on the Server page: Syncing... with the spinner while it runs (inactive and grey), then the grey "Synced just now"; re-read on a timer; the root's status line is Syncing... at once."""
    expect = ctx.expect
    m = opened()
    tm = [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['ns_tick']]
    expect(len(tm) == 1 and tm[0][2] == 500, 'the page re-reads the sync state on a 500 ms timer')
    expect(text(m, 'pod_value3') == 'Not synced yet' and m.props.get((m.widgets['ns_spin'], 'visible')) in (None, 0), 'at rest with nothing synced: the grey "Not synced yet", no spinner')
    site = SB.Site(); m.curl_site = site
    click(m, 3)
    expect(confirms(m) == ['Sync your Subsonic library now?'] and m.thread is not None and text(m, 'pod_value3') == 'Syncing…' and m.props.get((m.widgets['ns_spin'], 'visible')) == 1
           and ('timer_add', PSYMS['ls_spin_tick'], 250) in m.calls, 'after the confirm the row shows Syncing... at once, with the spinner on the shared spinner timer')
    expect(m.props.get((m.widgets['pod_row3'], 'sensitive')) == 0 and m.props.get((m.widgets['pod_label3'], 'style:normal:text_color')) == '#6C6C70', 'and it is inactive and grey while the sync runs')
    mv = [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets['ns_spin']]
    expect(mv and mv[-1][2] < 280 - 8 * len('Syncing…') , 'the spinner sits before the text')
    SB.drain(m, m.thread)
    m.calls = []
    m.call(PSYMS['ns_tick'], a0=0, count=20000000)
    expect(text(m, 'pod_value3') == 'Synced just now' and m.props.get((m.widgets['ns_spin'], 'visible')) == 0 and m.props.get((m.widgets['pod_row3'], 'sensitive')) == 1
           and m.props.get((m.widgets['pod_label3'], 'style:normal:text_color')) == '#FFFFFF', 'when it is done the timer writes the grey "Synced just now" and the row is active again, the spinner gone')
    m = opened(); m.confirm_yes = False
    click(m, 3)
    expect(text(m, 'pod_value3') == 'Not synced yet' and m.thread is None, 'No: the row shows no run')
    m = opened(); m.wifi = 0
    click(m, 3)
    expect(toasts(m) == ['Connect to Wi-Fi first'] and text(m, 'pod_value3') == 'Not synced yet', 'a refusal is the toast and the row shows no run')
    m = opened()
    m.put(SB.ND + '/sync.txt', b'1799999700 2431 0')
    m.call(PSYMS['ns_tick'], a0=0, count=20000000)
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(text(m, 'pod_value3').startswith('Synced'), f'a synced library reads "Synced ..." ({text(m, "pod_value3")})')
    fn_, ctx_ = m.bound[(m.window, EVT_DESTROY)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(any(c[0] == 'timer_remove' for c in m.calls), 'the destroy removes the timer')


def server_actions(ctx):
    """Sync Now: confirm, then the sync. Sign Out: confirm, then the conf and the cache go; the downloads stay."""
    expect = ctx.expect
    m = opened()
    site = SB.Site(); m.curl_site = site
    click(m, 3)
    expect(confirms(m) == ['Sync your Subsonic library now?'] and m.thread is not None and not toasts(m), 'Sync Now asks first, then queues the sync')
    SB.drain(m, m.thread)
    expect(site.views()[0] == 'getAlbumList2' and 'ping' not in site.views()[:1], 'the request is the sync (getAlbumList2 ...)')
    st, code = SB.state(m, SB.K['SYNC'])
    expect(st in (SB.ST['OK'], SB.ST['FAIL']), 'the sync ran to a result')
    m = opened(); m.confirm_yes = False
    click(m, 3)
    expect(confirms(m) == ['Sync your Subsonic library now?'] and m.thread is None, 'No: nothing is queued')
    m = opened(conf=False)
    click(m, 3)
    expect(toasts(m) == ['Add a server first'] and not confirms(m) and m.thread is None, 'no server: a toast, no question, no request')
    m = opened(); m.wifi = 0
    click(m, 3)
    expect(not confirms(m) and toasts(m) == ['Connect to Wi-Fi first'] and m.thread is None, 'no Wi-Fi: the Wi-Fi toast at once, no question, nothing queued')
    # Sign Out
    m = opened()
    SB.seed(m, SB.ND + '/albums.idx', 'album', [dict(id='a1', name='One')])
    m.put(MUSIC, b'music'); m.put(DLIDX, b'manifest'); m.dirs.add('/mnt/mmc/Subsonic')
    click(m, 4)
    expect(confirms(m) == ['Sign out of Subsonic? Downloaded songs stay on the card.'], 'Sign Out asks first')
    expect(SB.CONF not in m.fs and SB.ND + '/albums.idx' not in m.fs, 'the conf and the cache are gone')
    expect(any(c[0] == 'navigator_back' for c in m.calls), 'and the page goes back to the root (its empty state), never a Server page with no server')
    expect(m.fs.get(MUSIC) == b'music' and m.fs.get(DLIDX) == b'manifest', 'the downloaded music and its manifest stay')
    expect(m.thread is None and m.call(PSYMS['sba_configured']) == 0, 'nothing is queued; no longer configured')
    # Sign Out cancels the downloads that wait
    m = opened()
    SDL = sibling('sbdl')   # noqa: F821
    r, th = SDL.add(m, SDL.track('d1', 'One'))
    expect(r == 0 and SDL.state(m, 'd1')[0] != 0, f'a download is queued before the sign-out ({r})')
    click(m, 4)
    expect(SDL.state(m, 'd1')[0] == 0, 'Sign Out: the waiting download leaves the queue')
    click(m, 4)
    expect(toasts(m) == ['Add a server first'] and not confirms(m), 'Sign Out with nothing saved: a toast, no question')
    m = opened(); m.confirm_yes = False
    click(m, 4)
    expect(m.fs.get(SB.CONF) and text(m, 'pod_value1') == 'alice', 'No: nothing is signed out')
    m = opened(conf=False)
    m.call(PSYMS['sba_conf_url_set'], a0=m.cstr('https://x.example'), count=20000000)
    click(m, 4)
    expect(confirms(m) and SB.CONF not in m.fs, 'a half-saved login (an address only) can still be signed out')
    # the row taps are on every row; Back and Now Playing are bound
    m = opened()
    expect(all((m.widgets[f'pod_row{i}'], EVT_CLICK) in m.bound for i in range(5)) and (m.widgets['btn_return'], EVT_CLICK) in m.bound and (m.widgets['btn_backtoplayer'], EVT_CLICK) in m.bound,
           'the five rows, Back and Now Playing are bound')


def server_strings(ctx):
    """The Server page's strings: a text in every language, the product name left alone, the toasts' and the confirmations' keys used by the page."""
    expect = ctx.expect
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        expect(all(pod_i18n.TEXT[k][t] for k in KEYS), f'{loc}: every key of the Server page has a text')
    for k in ('Sync your Subsonic library now?', 'Sign out of Subsonic? Downloaded songs stay on the card.'):
        expect(all('Subsonic' in pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for loc in pod_i18n.LOCALES), f'"Navidrome" is not translated in {k!r}')
    src = open(os.path.join(ROOT, 'patch', 'ndserver.c'), encoding='utf-8').read()   # noqa: F821
    used = set(__import__('re').findall(r'TR\("((?:[^"\\]|\\.)*)"\)', src))
    expect(used <= set(KEYS) and {'Add a server first', 'Could not save settings', 'Server URL'} <= used, f'every TR() key of ndserver.c is one of the page\'s ({sorted(used - set(KEYS))})')


def server_collapse(ctx):
    """The Server page's large title scrolls away and the navbar's small title takes over from SG_COLLAPSE; the fade shows while scrolled; no scroll events: the title stays."""
    expect = ctx.expect
    SC_YOFF = O['SC_YOFF']
    lit = lambda m, n: m.props.get((m.widgets[n], 'visible'), 0) == 1
    m = opened()
    sv = m.widgets['pod_scrollview']
    fn_, ctx_ = m.bound[(sv, O['EVT_SCROLL'])]
    expect(not lit(m, 'label_title') and not lit(m, 'img_nb_fade'), 'at rest: the small title and the fade are hidden')
    m.setword(sv + SC_YOFF, O['SG_COLLAPSE'] - 1)
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(not lit(m, 'label_title') and lit(m, 'img_nb_fade'), 'one px short of SG_COLLAPSE: no small title yet, the fade shows')
    m.setword(sv + SC_YOFF, O['SG_COLLAPSE'])
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(lit(m, 'label_title'), 'at SG_COLLAPSE the small title shows')
    fn2, ctx2 = m.bound[(sv, O['EVT_SCROLL_END'])]
    m.setword(sv + SC_YOFF, 0)
    m.call(fn2, a0=ctx2, a1=0, count=20000000)
    expect(not lit(m, 'label_title') and not lit(m, 'img_nb_fade'), 'back at the top: both go')
    m = opened(widget_on_fail={O['EVT_SCROLL']})
    expect(lit(m, 'label_title'), 'no scroll events: the navbar keeps its title')


def server(ctx):
    for f in (server_asset, server_rows, server_collapse, server_login, server_signin, server_actions, server_sync, server_strings): f(ctx)


ROOT_LABELS = ('Albums', 'Artists', 'Songs', 'Playlists', 'Favorites', 'Downloaded')
ROOT_NAMES = ('btn_return', 'btn_backtoplayer', 'btn_more', 'btn_search', 'nd_list', 'nd_status', 'nd_st_icon', 'nd_st_spin', 'nd_foot', 'pod_scrollview', 'label_title', 'img_nb_fade', 'vs_scrim', 'vs_card', 'vs_hair', 'nd_es_big', 'nd_es_icon', 'nd_es_title', 'nd_es_text', 'nd_es_pill', 'nd_es_dl') + tuple(f'pod_row{i}' for i in range(6)) + tuple(f'vs_item{i}' for i in range(8)) + tuple(f'vs_label{i}' for i in range(8)) + tuple(f'vs_sub{i}' for i in range(4)) + tuple(f'vs_tick{i}' for i in range(6)) + tuple(f'vs_glyph{i}' for i in range(4, 8))
ROOT_KEYS = ('Subsonic', 'Albums', 'Artists', 'Songs', 'Playlists', 'Favorites', 'Downloaded', 'Not Connected', 'Syncing…', 'Updating library… %d/%d', 'Loading covers… %d/%d', 'Loading artist images… %d/%d', 'Synced %s', 'Synced just now', 'Not synced yet', '%d song', '%d songs', 'Sync Now', 'Server Settings',
             'Navidrome, Gonic, Airsonic and other Subsonic servers', 'Add Server', 'Just now', '%dm ago', '%dh ago', '%dd ago')
F_CAPS = 48   # lib_src_t.caps (test/pod/sbsrc.py F_CAPS)
LS = dict(ALBUMS=0, ARTISTS=1, SONGS=2, PLAYLISTS=3, FAVORITES=4, DOWNLOADED=5)
OPENERS = ('albums_open_src', 'artists_open_src', 'songs_open_src', 'playlists_open_src', 'nd_server_open', 'nd_signin_open', 'search_open_src')


def trap(m, names=OPENERS):
    """The library pages' openers (and the Server page's) mocked: each call is recorded as (name, source, list, title) and answers 0."""
    orig = m._hook
    for n in names: m.handlers[PSYMS[n]] = 'nd_trap_' + n   # noqa: F821
    def hook(u, address, size, d):
        name = m.handlers.get(address, '')
        if not name.startswith('nd_trap_'): return orig(u, address, size, d)
        from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        fn = name[8:]
        m.calls.append((fn, a0, a1, undo(m.read_cstr(a2)) if fn == 'songs_open_src' and a2 else None))
        u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
    m._hook = hook


def root_opened(conf=True, fresh=False, caps=None, **kw):
    """The root page open over a card with the PR's conf file (or none). fresh: a finished sync of 5 minutes ago (nothing is due)."""
    m = SB.machine(conf=conf)
    m.window = WIN
    for k, v in kw.items(): setattr(m, k, v)
    m.widgets['pod_scrollview'] = m.alloc(0x100)   # (a scroll_view: its yoffset is read at SC_YOFF)
    for n in ROOT_NAMES: Machine.widget(m, n)   # noqa: F821
    for i, t in enumerate(ROOT_LABELS): m.wtext[m.widgets[f'pod_row{i}']] = t
    if fresh: m.put(SB.ND + '/sync.txt', b'1799999700 2431 0')
    trap(m)
    if caps is not None: m.setword(PSYMS['lib_nd'] + F_CAPS, caps)   # lib_src_t.caps: the source's controls (LS_CAP_SEARCH = 2)
    m.calls = []
    m.thread = None
    rc = m.call(PSYMS['nd_root_open'], count=20000000) & 0xffffffff   # noqa: F821
    assert rc == 0, f'nd_root_open returned {rc}'
    m.nd_timer = ([c[1] for c in m.calls if c[0] == 'timer_add'] or [0])[-1]
    return m


def tick(m):
    """The page's timer firing once."""
    assert m.nd_timer, 'no timer'
    m.calls = []
    m.call(m.nd_timer, a0=0, count=20000000)


def vis(m, n):
    """The last visibility set on widget n (None: never set)."""
    v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[n]]
    return v[-1] if v else None


def root_click(m, i):
    fn_, ctx_ = m.bound[(m.widgets[f'pod_row{i}'], EVT_CLICK)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)


def ok_site():
    from urllib.parse import parse_qs, urlparse   # noqa: F401
    return SB.Site(getAlbumList2={'body': SB.ok_json(albumList2={'album': [{'id': f'a{i}', 'name': f'A{i}', 'songCount': 10} for i in range(3)]})},
                   getArtists={'body': SB.ok_json(artists={'index': []})}, getPlaylists={'body': SB.ok_json(playlists={'playlist': []})},
                   getStarred2={'body': SB.ok_json(starred2={})}, ping={'body': SB.ok_json()},
                   search3=lambda url, o: {'body': SB.songs_json(['s0'])})   # (a library that has songs: an empty first page would fail the fill)


def root_asset(ctx):
    expect = ctx.expect
    P = pod_pages
    pg = P.NDROOT_PAGE
    expect(P.PAGES[-1] is pg and P.PAGES[-2] is P.NDSERVER_PAGE and pg.key == 'm1plus_ndroot' and pg.name == 'm1plus_ndroot_page' and pg.title == 'Subsonic' and pg.kind == 'ndroot' and pg.rows == [],
           'the root page is the last of the page table (after the PR\'s page and the Server page), m1plus_ndroot, titled Navidrome, no rows for the Settings binder')
    tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', 'm1plus_ndroot.bin'), 'rb').read())   # noqa: F821
    f = tree.find
    st = f('btn_more')
    expect(tree.name == 'm1plus_ndroot_page' and f('btn_return') is not None and f('btn_backtoplayer') is not None and f('label_title') is not None and f('label_title').get('visible') == 'false'
           and f('btn_settings') is None, 'the stock navbar: Back and Now Playing; the small title is kept but hidden until the large one has scrolled away; no Settings button any more')
    se = f('btn_search')
    expect(se is not None and (se.x, se.y, se.w, se.h) == (O['NAV_CF_X'], 0, 46, 50) and se.get('visible') == 'false' and se.get('sensitive') == 'false' and se.get('style:normal:icon') == 'pod_nav_search'
           and se.get('style:pressed:icon') == 'pod_nav_search_down', 'Search: the capsule\'s left cap at the Songs page\'s slot (x 168, pod_nav_search), built hidden and insensitive (the payload shows it)')
    expect(st is not None and (st.x, st.y, st.w, st.h) == (214, 0, 46, 50) and st.get('style') == 'img_btn_style' and st.get('enable') == 'true'
           and st.get('style:normal:icon') == st.get('style:over:icon') == 'pod_nav_more' and st.get('style:pressed:icon') == 'pod_nav_more_down'
           and f('btn_backtoplayer').get('style:normal:icon') == 'ah_nav_play' and f('label_title').x + f('label_title').w == 214,
           'the navbar\'s "..." capsule: btn_more on the 214 slot with the pod_nav_more pieces (the left cap; the payload makes it the middle piece pod_nav_moremid when Search shows), Now Playing the capsule\'s right cap, the title ends at 214')
    sv = f('pod_scrollview')
    expect(sv is not None and f('img_nb_fade').get('visible') == 'false' and f('img_nb_fade').get('sensitive') == 'false', 'the scroll view is there and the fade under the bar starts hidden')
    expect(all(f(n) is not None for n in ROOT_NAMES), 'every widget the payload looks up is in the asset')
    expect(f('nd_host') is None and f('nd_footer') is None and f('nd_value') is None and f('pod_row6') is None and f('pod_label6') is None and f('nd_gap') is None,
           'no Server row, no gap, no host line, no footer: the status line is the only text under the title')
    col, end = pod_nd.column()
    ys = {w.name: w.y for w in tree.walk() if w.name in {n for n, _, _ in col}}
    expect(all(ys[n] == y for n, y, _ in col) and end <= 400 + 120, f'the column the layouter stacks: {[(n, y) for n, y, _ in col]}')
    rows = [(n, y, h) for n, y, h in col if n.startswith('pod_row')]
    expect([r[2] for r in rows] == [52] * 6 and rows[0][1] == pod_nd.BIG_H and end == pod_nd.BIG_H + 6 * 52 + pod_nd.FOOT_H and pod_nd.FOOT_H == O['SG_FOOT_H'] + 12, 'the top item (the title and the status line) then six menu rows, 52 px high, and the footer\'s item (SG_FOOT_H and 12 px)')
    expect(end - 400 >= O['SG_COLLAPSE'], f'the column ({end} px) is longer than the list (400 px) by at least the collapse offset: the page scrolls far enough for the title to go')
    big = f('nd_big')
    expect(big.get('tr_text') == 'Subsonic' and big.x == O['SG_TITLE_X'] and big.w == O['SG_TITLE_W'] and big.h == O['PP_TITLE_H'] and big.get('style:normal:font_size') == str(O['PP_TITLE_PX']), 'the large title: the shared heading')
    sl, ic, sp = f('nd_status'), f('nd_st_icon'), f('nd_st_spin')
    tx = O['SG_TITLE_X'] + 14 + 6
    expect((sl.x, sl.y, sl.w, sl.h) == (tx, O['PP_LINE_Y'], O['SG_TITLE_X'] + O['SG_TITLE_W'] - tx, O['PP_LINE_H']) and sl.get('text') == '' and sl.get('style:normal:text_color') == '#AAAAAA'
           and sl.get('style:normal:font_size') == '15' and sl.get('style:normal:text_align_h') == 'left' and sl.get('ellipses') == 'true',
           'the status line: under the large title (the refresh line\'s place), after the 14 px glyph and a 6 px gap, grey #AAAAAA (the 4.5:1 grey), 15 px, cut with an ellipsis; empty until the payload sets it')
    expect((ic.x, ic.y, ic.w, ic.h) == (O['SG_TITLE_X'], O['PP_LINE_Y'] + 3, 14, 14) and ic.get('image') == 'nd_st_ok' and ic.get('sensitive') == 'false'
           and (sp.x, sp.y, sp.w, sp.h) == (ic.x, ic.y, 14, 14) and sp.get('image') == 'wf_spin0' and sp.get('visible') == 'false' and sp.get('sensitive') == 'false',
           'the status glyph (the check circle) and the spinner (the Wi-Fi frames, hidden) share one 14 px place before the text')
    ft = f('nd_foot')
    expect((ft.x, ft.y, ft.w, ft.h) == (O['SG_HDR_X'], O['SG_FOOT_GAP'], 320 - 2 * O['SG_HDR_X'], O['SG_FOOT_TEXT_H']) and ft.get('style:normal:font_size') == str(O['SG_FOOT_PX'])
           and ft.get('style:normal:text_color') == '#9C9C9C' and ft.get('text') == '' and ft.get('sensitive') == 'false' and 'nd_foot' in {c.name for c in f('nd_end').children},
           'the footer: the library\'s song-count label (x SG_HDR_X, 15 px #9C9C9C) in the last item under the rows, empty until a sync')
    sc, cd = f('vs_scrim'), f('vs_card')
    expect(sc.get('visible') == 'false' and cd.get('visible') == 'false' and f('vs_label6').get('tr_text') == 'Sync Now' and f('vs_label7').get('tr_text') == 'Server Settings'
           and f('vs_glyph6').get('image') == 'pod_ic_vsrefresh' and f('vs_glyph7').get('image') == 'pod_ic_vsserver' and f('vs_item8') is None,
           'the "..." card: hidden, two action rows (Sync Now with refresh-cw, Server Settings with server)')
    expect(f('nd_es_big').get('tr_text') == 'Subsonic' and f('nd_es_big').y == 50, 'the empty state has its own large title at the list\'s top')
    icons = ['pod_ic_albums', 'pod_ic_artists', 'pod_ic_songs', 'pod_ic_playlists', 'pod_ic_fav', 'pod_sb_download']
    for i, lab in enumerate(ROOT_LABELS):
        row, l, ic, ch = f(f'pod_row{i}'), f(f'pod_label{i}'), f(f'pod_icon{i}'), f(f'pod_chev{i}')
        expect(l.get('tr_text') == lab and l.x == 56 and ic.get('image') == icons[i] and (ic.x, ic.w, ic.h) == (16, 24, 24) and ch.get('image') == 'right_arrow' and ch.x == 285 and row.get('style') == 'list_item_style',
               f'row {i}: {lab}, the glyph at x 16, the label at 56, the shared chevron, the stock row style')
        hair = f(f'pod_hair{i}')
        expect((hair is not None) == (i < 5) and (hair is None or (hair.x, hair.w, hair.h) == (56, 254, 1)), f'row {i}: the hairline runs from the label to 310, none under the last of a group')
    for n in ('nd_es_big', 'nd_es_icon', 'nd_es_title', 'nd_es_text', 'nd_es_pill', 'nd_es_dl'):
        expect(f(n).get('visible') == 'false' and f(n).get('sensitive') == 'false', f'{n} starts hidden')
    expect(f('nd_es_icon').get('image') == 'pod_es_plug' and f('nd_es_title').get('tr_text') == 'Not Connected' and f('nd_es_text').get('tr_text') == 'Navidrome, Gonic, Airsonic and other Subsonic servers' and f('nd_es_pill').get('tr_text') == 'Add Server',
           'the empty state: the plug, Not Connected, the sentence, the Add Server pill')
    expect(f('nd_es_dl').get('tr_text') == 'Downloaded' and f('nd_es_dl').y == f('nd_es_pill').y + 36 + 12, 'the Downloaded pill sits under the Add Server pill')
    iy, ty, xy, py = __import__('pod_ui').oa_es_layout('pod_es_plug', 'text', True)
    expect((f('nd_es_icon').y, f('nd_es_title').y, f('nd_es_text').y, f('nd_es_pill').y) == (iy, ty, xy, py), 'the block stacks as the shared one (Find Cover & Lyrics) does')
    bad = [w.name for w in tree.walk() if w.get('tr_text') is None and w.get('text') not in (None, '')]
    expect(not bad, f'every text is a tr_text key ({bad})')


def root_rows(ctx):
    expect = ctx.expect
    m = root_opened(fresh=True)
    lib = m.symbol('lib_nd') if hasattr(m, 'symbol') else PSYMS['lib_nd']   # noqa: F821
    want = [('albums_open_src', lib, 0, None), ('artists_open_src', lib, None, None), ('songs_open_src', lib, LS['SONGS'], 'Songs'), ('playlists_open_src', lib, None, None),
            ('songs_open_src', lib, LS['FAVORITES'], 'Favorites'), ('songs_open_src', lib, LS['DOWNLOADED'], 'Downloaded')]
    for i, w in enumerate(want):
        root_click(m, i)
        got = [c for c in m.calls if c[0] in OPENERS]
        ok = len(got) == 1 and got[0][0] == w[0] and (w[1] is None or got[0][1] == w[1]) and (w[2] is None or got[0][2] == w[2]) and (w[3] is None or got[0][3] == w[3])
        expect(ok, f'row {i} ({ROOT_LABELS[i]}) opens {w[0]}' + (f' on lib_nd, list {w[2]} titled {w[3]!r}' if w[2] is not None and w[3] else ' on lib_nd' if w[1] else '') + f' (got {got})')
    for n in ('vs_item7', 'nd_es_pill'):
        fn_, ctx_ = m.bound[(m.widgets[n], EVT_CLICK)]
        m.calls = []
        m.call(fn_, a0=ctx_, a1=0, count=20000000)
        expect([c[0] for c in m.calls if c[0] in OPENERS] == ['nd_server_open'], f'{n} opens the Server page (nd_server_open)')
    expect(all((m.widgets[f'pod_row{i}'], EVT_CLICK) in m.bound for i in range(6)) and (m.widgets['btn_return'], EVT_CLICK) in m.bound and (m.widgets['btn_backtoplayer'], EVT_CLICK) in m.bound
           and (m.widgets['nd_es_pill'], EVT_CLICK) in m.bound and (m.widgets['btn_more'], EVT_CLICK) in m.bound and (m.widgets['vs_item6'], EVT_CLICK) in m.bound, 'the six rows, the "..." button, the card\'s rows, the pill, Back and Now Playing are bound')


def glyph(m):
    """The image the status glyph shows now (the last image_base_set_image on it)."""
    p = m.props.get((m.widgets['nd_st_icon'], 'image'))
    return m.read_cstr(p) if p else None


def lit(m, n):
    """Widget n is shown: set visible and never hidden since (a widget the page never touched counts as hidden, as the asset builds them)."""
    return m.props.get((m.widgets[n], 'visible'), 0) == 1


def root_status(ctx):
    """The status line per state: a glyph (the check circle connected, the unplugged plug offline or not connected, the spinner while a sync runs), then "Synced 5m ago", "Syncing…" or "Not Connected"."""
    expect = ctx.expect
    m = root_opened(fresh=True)
    expect(text(m, 'nd_status') == 'Synced 5m ago' and glyph(m) == 'nd_st_ok' and not lit(m, 'nd_st_spin'), f'a fresh sync and nothing asked: the check circle and the age ({text(m, "nd_status")!r}, {glyph(m)})')
    expect(m.thread is None, 'a fresh cache (5 minutes old): opening asks for nothing')
    # no sync yet: opening asks, the line is Syncing... with the spinner, then the check circle and the age
    m = root_opened()
    expect(m.thread is not None and vis(m, 'nd_list') == 1 and text(m, 'nd_status') == 'Syncing…' and lit(m, 'nd_st_spin') and not lit(m, 'nd_st_icon'),
           'no sync yet: opening asks for one; the line says Syncing… with the spinner in the glyph\'s place')
    expect(('timer_add', PSYMS['ls_spin_tick'], 250) in m.calls, 'the spinner turns on the shared timer (ls_spin)')
    site = ok_site(); m.curl_site = site
    SB.drain(m, m.thread)
    tick(m)
    expect(text(m, 'nd_status') == 'Synced just now' and glyph(m) == 'nd_st_ok' and lit(m, 'nd_st_icon') and not lit(m, 'nd_st_spin') and 'getAlbumList2' in site.views(),
           'the sync finished: the next tick says Synced just now with the check circle, the spinner gone (the page re-read the status on the counter)')
    m.calls = []
    tick(m)
    expect(not [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'image_base_set_image')], 'nothing moved: a tick writes no text and no glyph')
    # Wi-Fi off
    m.wifi = -1
    for _ in range(8): tick(m)
    expect(text(m, 'nd_status') == 'Synced just now' and glyph(m) == 'nd_st_off', 'Wi-Fi off: the unplugged plug, the line still tells the sync (found within a few seconds without a counter)')
    m.wifi = 4
    for _ in range(8): tick(m)
    expect(text(m, 'nd_status') == 'Synced just now' and glyph(m) == 'nd_st_ok', 'Wi-Fi back: the check circle')
    # Wi-Fi coming back while the page is up asks for the sync that was due (once)
    m = root_opened(wifi=-1)
    expect(m.thread is None, 'opened with the Wi-Fi off: nothing asked')
    tick(m)
    expect(m.thread is None, 'still off after a tick: nothing asked')
    m.wifi = 4
    tick(m)
    expect(m.thread is not None, 'the Wi-Fi came back (guard NOWIFI to OK): the due sync is asked for')
    SB.drain(m, m.thread)
    m.thread = None
    tick(m)
    expect(m.thread is None, 'and not again on the next tick')
    # any refusal ending does the same, not only NOWIFI (an https server: Wi-Fi up but the clock not set yet, then set)
    m = root_opened(card_mounted=False)
    tick(m)
    expect(m.thread is None, 'the card out (guard STORAGE): nothing asked')
    m.card_mounted = True
    tick(m)
    expect(m.thread is not None, 'the refusal ended (guard STORAGE to OK): the due sync is asked for')
    # a refused sync: Not Connected alone
    m = root_opened()
    m.curl_site = SB.Site(getAlbumList2={'body': SB.err_json(40)})
    SB.drain(m, m.thread)
    tick(m)
    expect(text(m, 'nd_status') == 'Not Connected' and glyph(m) == 'nd_st_off' and not lit(m, 'nd_st_spin'), 'a server that refuses the login: Not Connected with the unplugged plug')
    # no Wi-Fi at open: nothing queued, the plug and Not synced yet
    m = root_opened(wifi=-1)
    expect(m.thread is None and text(m, 'nd_status') == 'Not synced yet' and glyph(m) == 'nd_st_off', 'opened with the Wi-Fi off: no request, the plug, Not synced yet')
    # the Server page changed the login: read again on coming back to the front, the old cache is not shown
    m = root_opened(fresh=True)
    m.call(PSYMS['sba_conf_url_set'], a0=m.cstr('http://music.example:9000'), count=20000000)
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(text(m, 'nd_status') != 'Synced 5m ago', f'back from the Server page (EVT_WINDOW_TO_FG): read again ({text(m, "nd_status")!r})')


def root_progress(ctx):
    """The status line while the background fill runs (phase 2 of the sync, docs/modules/subsonic.md "Background fill"): the spinner and "Updating library… N/M" for the songs, "Loading covers… N/M" for the covers, "Loading artist images… N/M" for the artists' pictures, then
    the age again; Sync Now stays active; every language fits the line."""
    expect = ctx.expect
    site, songs, ids = SB.bg_lib()
    site.routes['getArtists'] = {'body': SB.ok_json(artists={'index': [{'name': 'A', 'artist': [dict(id=f'r{i}', name=f'Artist {i}', albumCount=1, **({} if i == 2 else {'coverArt': f'ar-r{i}'})) for i in range(4)]}]})}
    m = root_opened()
    m.curl_site = site
    seen = {}
    page_inner, cover_inner = site.routes['search3'], site.routes['getCoverArt']

    def sample(key):
        m.nested(m.nd_timer, 0)   # the page's own tick, from inside the worker's request
        seen.setdefault(key, []).append((text(m, 'nd_status'), lit(m, 'nd_st_spin'), glyph(m), item_ok(m, 6)))

    def search(url, o):
        sample('songs')
        return page_inner(url, o)

    def cover(url, o):
        sample('artists' if 'id=ar-' in url else 'covers')
        return cover_inner
    site.routes['search3'], site.routes['getCoverArt'] = search, cover
    SB.drain(m, m.thread)
    expect([s[0] for s in seen['songs']] == ['Updating library… 0/230', 'Updating library… 100/230', 'Updating library… 200/230'], f'the songs: {[s[0] for s in seen["songs"]]}')
    expect([s[0] for s in seen['covers']] == ['Loading covers… 0/3', 'Loading covers… 1/3', 'Loading covers… 2/3'], f'then the covers: {[s[0] for s in seen["covers"]]}')
    expect([s[0] for s in seen['artists']] == ['Loading artist images… 0/3', 'Loading artist images… 1/3', 'Loading artist images… 2/3'], f'then the artist pictures (the artist with no id left out): {[s[0] for s in seen["artists"]]}')
    expect(all(s[1] and s[2] != 'nd_st_ok' for k in seen for s in seen[k]) and all(s[3] == (1, '#FFFFFF') for k in seen for s in seen[k]),
           'the spinner turns in the glyph\'s place and Sync Now stays active all along (only a sync greys it)')
    tick(m)
    expect(text(m, 'nd_status') == 'Synced just now' and glyph(m) == 'nd_st_ok' and not lit(m, 'nd_st_spin'), f'the fill is over: the age and the check circle again ({text(m, "nd_status")!r})')
    # the strings fit the line (the label at the status font) in all 13 languages, with the largest numbers the caps allow
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))   # noqa: F821
    room = __import__('pod_ui').OFFSETS['SG_TITLE_W'] - pod_nd.SPIN_PX - pod_nd.SPIN_GAP
    wide = []
    for loc in pod_i18n.LOCALES:
        for key in ('Updating library… %d/%d', 'Loading covers… %d/%d', 'Loading artist images… %d/%d'):
            w = StbText(font, pod_nd.STATUS_PX).layout(pod_i18n.TEXT[key][pod_i18n.table_for(loc)].replace('%d/%d', '50000/50000'))[1]
            if w > room: wide.append((loc, key, w))
    expect(not wide and room > 200, f'all three progress lines fit the {room} px status line at {pod_nd.STATUS_PX} px in all 13 languages with 50000/50000 ({wide})')


def root_footer(ctx):
    """The sync's line ("Synced 5m ago", "Synced just now", "Not synced yet") and the footer under the rows (the library's "N songs", the totals of the sync's albums)."""
    expect = ctx.expect
    m = root_opened(fresh=True, wall=1799999700 + 20)
    expect(text(m, 'nd_status') == 'Synced just now', f'under a minute: Synced just now ({text(m, "nd_status")!r})')
    expect(text(m, 'nd_foot') == '2431 songs', f'the footer: the sync\'s total ({text(m, "nd_foot")!r})')
    m = root_opened(fresh=True)
    m.wall += 3 * 3600
    for _ in range(8): tick(m)
    expect(text(m, 'nd_status') == 'Synced 3h ago', f'the age grows with the clock, read again within a few seconds ({text(m, "nd_status")!r})')
    m = root_opened(wifi=-1)
    expect(text(m, 'nd_status') == 'Not synced yet' and text(m, 'nd_foot') == '', 'no sync yet: Not synced yet and no footer')
    m = root_opened()
    m.curl_site = ok_site()
    SB.drain(m, m.thread)
    tick(m)
    expect(text(m, 'nd_status') == 'Synced just now' and text(m, 'nd_foot') == '30 songs', f'after the sync: the totals of the three albums in the footer ({text(m, "nd_foot")!r})')
    m = root_opened(fresh=True)
    m.put(SB.ND + '/sync.txt', b'1799999700 1 0')
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(text(m, 'nd_foot') == '1 song', 'a library of one song: the singular key')


def root_collapse(ctx):
    """The large title scrolls away and the navbar's small title takes over from SG_COLLAPSE (pod_title_gone); the fade shows while scrolled; no scroll events: the title stays; no server: no collapse."""
    expect = ctx.expect
    SC_YOFF = O['SC_YOFF']
    m = root_opened(fresh=True)
    sv = m.widgets['pod_scrollview']
    fn_, ctx_ = m.bound[(sv, O['EVT_SCROLL'])]
    fn2, ctx2 = m.bound[(sv, O['EVT_SCROLL_END'])]
    expect(not lit(m, 'label_title') and not lit(m, 'img_nb_fade'), 'at rest: the small title and the fade are hidden')
    def at(off, end=False):
        m.setword(sv + SC_YOFF, off)
        m.calls = []
        a, b = (fn2, ctx2) if end else (fn_, ctx_)
        m.call(a, a0=b, a1=0, count=20000000)
    at(O['SG_COLLAPSE'] - 1)
    expect(not lit(m, 'label_title') and lit(m, 'img_nb_fade'), 'one px short of SG_COLLAPSE: no small title yet, the fade shows')
    at(O['SG_COLLAPSE'])
    expect(lit(m, 'label_title'), 'at SG_COLLAPSE the small title shows')
    at(0, True)
    expect(not lit(m, 'label_title') and not lit(m, 'img_nb_fade'), 'back at the top (EVT_SCROLL_END): the small title and the fade go')
    expect(pod_nd.FOOT_H and (80 + 6 * 52 + pod_nd.FOOT_H - 400) >= O['SG_COLLAPSE'], 'the column scrolls at least SG_COLLAPSE px, so the heading can go')
    m = root_opened(fresh=True, widget_on_fail={O['EVT_SCROLL']})
    expect(lit(m, 'label_title'), 'no scroll events: the navbar keeps its title')
    m = root_opened(conf=False)
    sv = m.widgets['pod_scrollview']
    m.setword(sv + SC_YOFF, 100)
    fn_, ctx_ = m.bound[(sv, O['EVT_SCROLL'])]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(not lit(m, 'label_title') and not lit(m, 'img_nb_fade'), 'the empty state has its own large title: no small one, no fade')


def root_search(ctx):
    """The navbar's Search: the capsule [Search | ... | Now Playing] with a server saved and a source that searches; [... | Now Playing] otherwise (no server, or lib_nd without LS_CAP_SEARCH); it opens the source's search."""
    expect = ctx.expect
    icon = lambda m: m.props.get((m.widgets['btn_more'], 'style:normal:icon'))
    title_w = lambda m: [c[2] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['label_title']]
    m = root_opened(fresh=True, caps=2)
    expect(lit(m, 'btn_search') and m.props.get((m.widgets['btn_search'], 'sensitive'), 1) == 1 and icon(m) == 'pod_nav_moremid' and m.props.get((m.widgets['btn_more'], 'style:pressed:icon')) == 'pod_nav_moremid_down'
           and title_w(m) == [O['NAV_CF_X'] - 58], 'a server saved on a source that searches: Search is the left cap, the "..." its middle piece, the small title ends at 168')
    fn_, ctx_ = m.bound[(m.widgets['btn_search'], EVT_CLICK)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    got = [c for c in m.calls if c[0] in OPENERS]
    expect(len(got) == 1 and got[0][0] == 'search_open_src' and got[0][1] == PSYMS['lib_nd'], f'Search opens the library search on the source (search_open_src(lib_nd)): {got}')   # noqa: F821
    m = root_opened(fresh=True)
    expect(lit(m, 'btn_search') and icon(m) == 'pod_nav_moremid' and title_w(m) == [168 - 58], f'lib_nd as built (LS_CAP_SEARCH): Search shows, the "..." is the middle piece, the title runs to 168 ({title_w(m)})')
    m = root_opened(conf=False, caps=2)
    expect(not lit(m, 'btn_search') and icon(m) == 'pod_nav_more', 'no server saved: no Search, the "..." is the left cap')
    m.call(PSYMS['sba_conf_url_set'], a0=m.cstr('https://nd.example:4533'), count=20000000)
    m.call(PSYMS['sba_conf_user_set'], a0=m.cstr('alice'), count=20000000)
    m.call(PSYMS['sba_conf_password_set'], a0=m.cstr('pw'), count=20000000)
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(lit(m, 'btn_search') and icon(m) == 'pod_nav_moremid', 'a server saved while the Server page was up: Search appears')
    m.call(PSYMS['sba_conf_clear'], count=20000000)
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(not lit(m, 'btn_search') and icon(m) == 'pod_nav_more', 'signed out: Search goes')
    expect((m.widgets['btn_search'], EVT_CLICK) in m.bound, 'the button is bound')


def item_ok(m, i):
    return m.props.get((m.widgets[f'vs_item{i}'], 'sensitive'), 1), m.props.get((m.widgets[f'vs_label{i}'], 'style:normal:text_color'))


def root_more(ctx):
    """The navbar's "...": the card with Sync Now (asks first like the Server page's, then syncs; inactive while one runs; the Wi-Fi toast when there is none) and Server Settings (the Server page)."""
    expect = ctx.expect
    card_on = lambda m: lit(m, 'vs_card') and lit(m, 'vs_scrim')
    m = root_opened(fresh=True)
    expect(m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass2' and lit(m, 'vs_item6') and lit(m, 'vs_item7') and not card_on(m), 'a server saved: the two-row card, closed')
    fn_, ctx_ = m.bound[(m.widgets['btn_more'], EVT_CLICK)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(card_on(m), 'the "..." opens the card')
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(not card_on(m), 'the "..." again closes it')
    fn_, ctx_ = m.bound[(m.widgets['vs_scrim'], EVT_CLICK)]
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(not card_on(m), 'a tap on the scrim closes it')
    # Sync Now
    m = root_opened(fresh=True)
    site = ok_site(); m.curl_site = site
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    expect(item_ok(m, 6)[0] == 1, 'Sync Now is active when no sync runs')
    m.thread = None; m.confirm_yes = False
    root_click_item(m, 6)
    expect(confirms(m) == ['Sync your Subsonic library now?'] and m.thread is None and not card_on(m), 'Sync Now asks first (the Server page\'s question); No queues nothing and closes the card')
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    m.confirm_yes = True
    root_click_item(m, 6)
    expect(confirms(m) == ['Sync your Subsonic library now?'] and m.thread is not None and not card_on(m) and not toasts(m) and text(m, 'nd_status') == 'Syncing…' and lit(m, 'nd_st_spin'),
           'Yes: the card closes and the sync is asked; the status line says Syncing… at once')
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    expect(item_ok(m, 6) == (0, '#6C6C70'), f'while the sync runs Sync Now is inactive: not sensitive, grey ({item_ok(m, 6)})')
    SB.drain(m, m.thread)
    tick(m)
    expect(item_ok(m, 6) == (1, '#FFFFFF') and 'getAlbumList2' in site.views() and text(m, 'nd_status') == 'Synced just now', 'the sync finished: Sync Now is active again and the line tells the sync')
    # no Wi-Fi: the toast, nothing queued
    m = root_opened(fresh=True, wifi=-1); m.confirm_yes = True
    root_click_item(m, 6)
    expect(toasts(m) == ['Connect to Wi-Fi first'] and m.thread is None and not card_on(m), 'no Wi-Fi: Sync Now says so in a toast and queues nothing')
    # Server Settings
    m = root_opened(fresh=True)
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    root_click_item(m, 7)
    expect([c[0] for c in m.calls if c[0] in OPENERS] == ['nd_server_open'] and not card_on(m), 'Server Settings opens the Server page and closes the card')
    # no server: Server Settings alone
    m = root_opened(conf=False)
    expect(m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass1' and not lit(m, 'vs_item6') and lit(m, 'vs_item7'), 'no server saved: the card holds Server Settings alone')
    m.call(m.bound[(m.widgets['btn_more'], EVT_CLICK)][0], a0=0, a1=0, count=20000000)
    root_click_item(m, 7)
    expect([c[0] for c in m.calls if c[0] in OPENERS] == ['nd_signin_open'], 'and, with no server saved, it opens the Sign In page straight away (no Server page with Sync Now before the sign-in)')
    # a server saved while the Server page was up: the second row is back
    m.call(PSYMS['sba_conf_url_set'], a0=m.cstr('https://nd.example:4533'), count=20000000)
    m.call(PSYMS['sba_conf_user_set'], a0=m.cstr('alice'), count=20000000)
    m.call(PSYMS['sba_conf_password_set'], a0=m.cstr('pw'), count=20000000)
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(m.props.get((m.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass2' and lit(m, 'vs_item6'), 'a server saved: the two-row card is back')


def root_click_item(m, i):
    fn_, ctx_ = m.bound[(m.widgets[f'vs_item{i}'], EVT_CLICK)]
    m.calls = []
    m.thread = None
    m.call(fn_, a0=ctx_, a1=0, count=200000000)


def root_empty(ctx):
    expect = ctx.expect
    m = root_opened(conf=False)
    expect(vis(m, 'nd_list') == 0 and all(vis(m, n) == 1 for n in ('nd_es_big', 'nd_es_icon', 'nd_es_title', 'nd_es_text', 'nd_es_pill', 'nd_es_dl')), 'no server saved: the list is hidden and the empty state shown')
    expect(m.thread is None and not [c for c in m.calls if c[0] in OPENERS], 'nothing is asked and nothing opened')
    m.calls = []
    fn_, ctx_ = m.bound[(m.widgets['nd_es_pill'], EVT_CLICK)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect([c[0] for c in m.calls if c[0] in OPENERS] == ['nd_signin_open'], 'the Add Server pill opens the Sign In page, not the Server page')
    m.calls = []
    fn_, ctx_ = m.bound[(m.widgets['nd_es_dl'], EVT_CLICK)]
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    op = [c for c in m.calls if c[0] == 'songs_open_src']
    expect(len(op) == 1 and op[0][2] == LS['DOWNLOADED'] and not [c for c in m.calls if c[0] == 'nd_server_open'], f'with no server the Downloaded pill opens the downloaded songs: {op}')
    # a server saved while the Server page was up: the page switches to the list on coming back
    m.call(PSYMS['sba_conf_url_set'], a0=m.cstr('https://nd.example:4533'), count=20000000)
    m.call(PSYMS['sba_conf_user_set'], a0=m.cstr('alice'), count=20000000)
    m.call(PSYMS['sba_conf_password_set'], a0=m.cstr('pw'), count=20000000)
    fn_, ctx_ = m.bound[(m.window, EVT_FG)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(vis(m, 'nd_list') == 1 and vis(m, 'nd_es_pill') == 0 and vis(m, 'nd_es_dl') == 0 and text(m, 'nd_status') != '', 'coming back with a server saved: the list is back, the empty state hidden, the status line set')
    # Sign Out (the conf goes while the page is under the Server page): back to the empty state
    m.call(PSYMS['sba_conf_clear'], count=20000000)
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(vis(m, 'nd_list') == 0 and vis(m, 'nd_es_pill') == 1 and vis(m, 'nd_es_dl') == 1, 'signed out: the empty state again')


def root_offline(ctx):
    expect = ctx.expect
    m = root_opened(fresh=True, wifi=-1)
    m.put(SB.ND + '/dl.idx', b'')
    for i in (0, 1, 2, 3, 4, 5):
        root_click(m, i)
        expect([c[0] for c in m.calls if c[0] in OPENERS] != [] and m.thread is None and not [c for c in m.calls if c[0] == 'toast'], f'Wi-Fi off: row {i} opens its page, no request, no toast')
    root_click(m, 5)
    got = [c for c in m.calls if c[0] == 'songs_open_src']
    expect(got and got[0][2] == LS['DOWNLOADED'], 'Downloaded opens with the Wi-Fi off')
    expect(m.call(PSYMS['sba_guard']) & 0xffffffff == SB.R['NOWIFI'], 'the guard says no Wi-Fi: the rows need none of it (the list reads the manifest)')


def root_life(ctx):
    expect = ctx.expect
    m = root_opened(fresh=True)
    expect(sum(1 for c in m.calls if c[0] == 'timer_add') == 1, 'the page has one timer')
    expect(m.call(PSYMS['nd_root_open'], count=20000000) == 0 and not [c for c in m.calls if c[0] == 'window_open'], 'a second open does nothing (0)')
    fn_, ctx_ = m.bound[(m.window, EVT_DESTROY)]
    m.calls = []
    m.call(fn_, a0=ctx_, a1=0, count=20000000)
    expect(any(c[0] == 'timer_remove' for c in m.calls), 'the destroy removes the timer')
    m.calls = []
    expect(m.call(PSYMS['nd_root_open'], count=20000000) == 0 and ('window_open', 'm1plus_ndroot') in m.calls, 'after the destroy the page opens again')
    m = SB.machine(); m.window = 0
    expect(m.call(PSYMS['nd_root_open'], count=20000000) & 0xffffffff == 0xffffffff, 'a window that will not open: -1')
    m = SB.machine()
    m.window = WIN
    m.calls = []
    expect(m.call(PSYMS['nd_root_open'], count=20000000) & 0xffffffff == 0xffffffff and any(c[0] == 'navigator_back' for c in m.calls), 'an asset without our widgets: -1 and the page goes back')
    src = open(os.path.join(ROOT, 'patch', 'm1plus.c'), encoding='utf-8').read()   # noqa: F821
    expect('row->action == ACT_SUBSONIC)\n        nd_root_open();' in src and 'open_page(POD_SUBSONIC_PAGE' not in src, 'the menu row Navidrome opens the root page (ACT_SUBSONIC keeps its id)')
    pod = open(os.path.join(ROOT, 'tools', 'pod.py'), encoding='utf-8').read()   # noqa: F821
    keep = pod[pod.index('ND_KEEP = ['):].split('\n')[0]
    expect("'nd_server_open'" not in keep and "'--undefined=songs_open_src'" not in pod and "'--undefined=lib_nd'" not in pod, 'the keeps that now have callers are gone (nd_server_open, songs_open_src, lib_nd)')
    ar = open(os.path.join(ROOT, 'patch', 'artists.c'), encoding='utf-8').read()   # noqa: F821
    expect('retain' not in ar.split('int artists_open_src')[0].split('\n')[-1], 'artists_open_src has no retain attribute')


def root_strings(ctx):
    expect = ctx.expect
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        expect(all(pod_i18n.TEXT[k][t] for k in ROOT_KEYS), f'{loc}: every key of the root page has a text')
    expect(all(pod_i18n.TEXT['Subsonic'][pod_i18n.table_for(loc)] == 'Subsonic' for loc in pod_i18n.LOCALES), '"Subsonic" is not translated')
    expect(all('Navidrome' in pod_i18n.TEXT['Navidrome, Gonic, Airsonic and other Subsonic servers'][pod_i18n.table_for(loc)] for loc in pod_i18n.LOCALES), 'the product name stays in the sentence')
    expect(all('%s' in pod_i18n.TEXT['Synced %s'][pod_i18n.table_for(loc)] for loc in pod_i18n.LOCALES), 'the sync line\'s key has its %s in every language')
    expect(all(k not in pod_i18n.TEXT for k in ('Connected', 'Offline', 'Synced %d songs')), 'the words the glyphs replaced are gone')
    src = open(os.path.join(ROOT, 'patch', 'ndroot.c'), encoding='utf-8').read()   # noqa: F821
    used = set(__import__('re').findall(r'TR\("((?:[^"\\]|\\.)*)"\)', src))
    expect(used <= set(ROOT_KEYS) and {'Syncing…', 'Not Connected', 'Not synced yet', 'Synced %s', 'Synced just now'} <= used and '"%d song" : "%d songs"' in src, f'every TR() key of ndroot.c is one of the page\'s ({sorted(used - set(ROOT_KEYS))})')


def root(ctx):
    for f in (root_asset, root_rows, root_status, root_progress, root_footer, root_collapse, root_more, root_search, root_empty, root_offline, root_life, root_strings): f(ctx)



SECTIONS = [server, root]


def run(ctx):
    for f in SECTIONS: f(ctx)

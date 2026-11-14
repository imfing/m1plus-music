"""The ListenBrainz settings (patch/scrobpage.c, docs/modules/scrobble.md "Settings"): the Scrobbling page's (Settings > Library > Scrobbling) ListenBrainz and Upload Scrobbles rows and the ListenBrainz page (Account,
Sign Out), on the compiled payload under Unicorn with the upload and the account of patch/scrobup.c under them (the thread's routine run by the test, libcurl the scripted service).

Proved: the rows, ids, page and built assets; the values (Not Set, the user name, Invalid Token, Checking…, nothing for a token no check confirmed); no token entry on the device (the
token comes only from the card's scrobble.ini: no Token row, no keyboard, no setter in the payload); the card's scrobble.ini read again when a page opens (and an unconfirmed token checked);
every Upload Scrobbles branch in its order and every final toast; whose result a poll is (a check while an upload is expected and the other way round, the automatic upload's job:
watched, collected silently when it is over, never toasted); the Auto Upload switch in its own card;
the timer's life (only with a page and a job, nothing but the poll with the screen dark, removed on destroy); Sign Out behind its confirm; the strings in 13 languages."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui
import pod_pages as P, pod_i18n, mod_icons
import pod_settings as ST

SU = sibling('scrobup')   # noqa: F821
UI = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui')   # noqa: F821
EVT_DESTROY, EVT_CLICK, EVT_FG = O['EVT_DESTROY'], O['EVT_CLICK'], O['EVT_WINDOW_TO_FG']   # noqa: F821
TOKEN, INI, LOG = SU.TOKEN, SU.INI, SU.LOG
LIB_ROWS = len(P.SCROBBLING_PAGE.rows)
R_SW, R_LB, R_LF, R_AUTO, R_UP = range(5)   # the Scrobbling page's switch, ListenBrainz, Last.fm, Auto Upload and Upload Scrobbles rows
R_ACCT = 0   # the one row of the ListenBrainz page and of the Last.fm page
TICK_MS = 500
TOASTS = ('Already uploading', 'Set up an account first', 'Not available in USB mode', 'Connect to Wi-Fi first',
          'Uploading scrobbles', 'Scrobbles sent: %d', 'Nothing to upload', '%d sent, %d rejected', 'Card error, %d sent', 'Upload failed, %d sent', 'Storage unavailable')
KEYS = ('ListenBrainz', 'Last.fm', 'Upload Scrobbles', 'Account', 'Not Set', 'Invalid Token', 'Sign-in Failed', 'Checking…', P.LB_NOTE, P.LF_NOTE, 'Auto Upload', P.LB_AUTO_NOTE) + TOASTS
# patch/scrobpage.c lbs: timer, ticks, pages, job, done
LBS = {n: 4 * i for i, n in enumerate(('timer', 'ticks', 'pages', 'job', 'done'))}
AUTO_FILE = '/mnt/data/m1plus/scrobble-auto'   # patch/home.h SCROBBLE_AUTO_FILE


def machine(token=TOKEN, name=None, log=None, answers=None, raw=None, wifi=4):
    """A machine with an account in the card's scrobble.ini (token: None for no file; name: the user name a check wrote; raw: the file as a user wrote it), a log, and the widgets of both pages (the rows share their names:
    pod_row0..2 are bound by the page that opened last, the Library page's two rows have numbers of their own)."""
    m = SU.machine(log=log, token=token, name=name, raw=raw, answers=answers)
    m.wifi = wifi
    for n in ['btn_return', 'btn_backtoplayer'] + [f'pod_{k}{i}' for i in range(len(P.LIBRARY_PAGE.rows)) for k in ('row', 'label', 'value', 'switch')] + [f'pod_note{i}_t' for i in range(5)]:
        Machine.widget(m, n)   # noqa: F821
    m.windows.update({'m1plus_library': m.alloc(0x100), 'm1plus_scrobbling': m.alloc(0x100), 'm1plus_listenbrainz': m.alloc(0x100), 'm1plus_lastfm': m.alloc(0x100)})
    m.job = None
    return m


def run(m, fn, **kw):
    """One call of the payload: its calls (also added to m.log)."""
    m.thread = None
    r = SU.call(m, fn, count=1 << 30, **kw)
    if m.thread: m.job = m.thread
    return r


def open_page(m, page):
    row = m.alloc(12)
    m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.PAGES.index(page))
    run(m, PSYMS['on_row'], a0=row)   # noqa: F821
    return list(m.calls)


def library(**kw):
    m = machine(**kw)
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    return m


def lbpage(lib=True, **kw):
    """The ListenBrainz page (over the Library page, as on the device, or alone)."""
    m = library(**kw) if lib else machine(**kw)
    m.opened = open_page(m, P.LB_PAGE)
    return m


def retoken(m, token=TOKEN):
    """The only way to set a token: the card's scrobble.ini written on a computer (here with the ListenBrainz page closed), then the page opened again."""
    event(m, 'm1plus_listenbrainz', EVT_DESTROY)
    m.fs[INI] = ini(token)
    m.opened = open_page(m, P.LB_PAGE)


def click(m, i):
    fn_, ctx = m.bound[(m.widgets[f'pod_row{i}'], EVT_CLICK)]
    run(m, fn_, a0=ctx, a1=0)
    return list(m.calls)


def tick(m):
    """One tick of the pages' timer: its result; m.tc keeps its calls."""
    r = run(m, PSYMS['lb_tick'], a0=0)   # noqa: F821
    m.tc = list(m.calls)
    return r


def work(m):
    """The worker thread's routine, to its end."""
    SU.call(m, m.job[0], a0=m.job[1], count=1 << 40)


def event(m, win, evt):
    fn_, ctx = m.bound[(m.windows[win], evt)]
    run(m, fn_, a0=ctx, a1=0)


def toasts(m, calls=None): return [undo(c[1]) for c in (m.calls if calls is None else calls) if c[0] == 'toast']   # noqa: F821
def text(m, n): return undo(m.wtext.get(m.widgets[n], ''))   # noqa: F821
def value(m, i): return text(m, f'pod_value{i}')
def lbs(m, n): return SU.s32(m.word(PSYMS['lbs'] + LBS[n]))   # noqa: F821
def timers(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'timer_add']


def invalid(m):
    """scrobup_invalid (Invalid Token, the account layer's RAM state); m.calls is left as it was."""
    keep = m.calls; r = m.call(PSYMS['scrobup_invalid'], count=10000); m.calls = keep   # noqa: F821
    return r


def sens(m, i): return m.props.get((m.widgets[f'pod_row{i}'], 'sensitive'), 1)
def token_file(m): return m.fs.get(INI)
def ini(token=TOKEN, name=None): return SU.ini(token, name).encode()
def log_text(n): return SU.HEADER + ''.join(SU.line(i) for i in range(n))


def pages_tests(ctx):
    """The rows, the ids, the pages and the built assets."""
    expect = ctx.expect
    L, S, B, F = P.LIBRARY_PAGE, P.SCROBBLING_PAGE, P.LB_PAGE, P.LF_PAGE
    expect((P.ACT_LB, P.ACT_SCROBUP, P.ACT_LBAUTO, P.ACT_LF, P.ACT_SCROBPAGE) == (108, 109, 112, 113, 139) and max(P._ACTS) == 139 and 110 not in P._ACTS and 111 not in P._ACTS and not hasattr(P, 'ACT_LBTOKEN') and not hasattr(P, 'ACT_LBOUT')
           and (P.INFO_LBACCT, P.INFO_LFACCT) == (P.INFO_DUR + 3, P.INFO_DUR + 4) == (68, 69),
           'the actions 108, 109, 112, 113 and 139 (110 was the Token row, 111 Sign Out: gone, their ids not reused); the Account rows are INFO_DUR + 3 and + 4')
    expect(P.PAGES[P.LB_PAGE_INDEX] is B and P.PAGES[P.LF_PAGE_INDEX] is F and P.PAGES[P.SCROBBLING_PAGE_INDEX] is S
           and (B.key, B.name, B.title) == ('m1plus_listenbrainz', 'm1plus_listenbrainz_page', 'ListenBrainz') and (F.key, F.name, F.title) == ('m1plus_lastfm', 'm1plus_lastfm_page', 'Last.fm')
           and (S.key, S.name, S.title) == ('m1plus_scrobbling', 'm1plus_scrobbling_page', 'Scrobbling'), 'the Scrobbling, ListenBrainz and Last.fm pages are in the page table under their keys')
    lay = [x.label if isinstance(x, P.Row) else x.text if isinstance(x, P.Note) else x for x in L.layout]
    expect(lay[-2:] == ['Podcasts', 'Scrobbling'],
           f'the Library page ends with a card of two rows, Podcasts and Scrobbling ({lay[-2:]})')
    expect([(r.label, r.action, r.arg, P.row_kind(r)) for r in L.rows[-1:]] == [('Scrobbling', P.ACT_SCROBPAGE, P.SCROBBLING_PAGE_INDEX, 'value')] and P.ACT_SCROBPAGE in P.VALUE_ACTIONS and P.VALUE_INIT[P.ACT_SCROBPAGE] == 'Off'
           and not {P.ACT_SCROBBLE, P.ACT_LB, P.ACT_LF, P.ACT_LBAUTO, P.ACT_SCROBUP} & {r.action for r in L.rows} and len(L.rows) == 10 and ST.pieces(L.layout)[-2:] == ['top', 'bot'],
           'a value row (Off at rest) opening the Scrobbling page, the second row of the last card (under Podcasts); no account, upload or switch rows left on the Library page')
    slay = [x.label if isinstance(x, P.Row) else x.text if isinstance(x, P.Note) else x for x in S.layout]
    expect(slay == ['Scrobbling', 'Saved to .scrobbler.log on the card.', 'ListenBrainz', 'Last.fm', P.GAP, 'Auto Upload', 'Upload Scrobbles', P.LB_AUTO_NOTE] and ST.pieces(S.layout) == ['single', 'top', 'bot', 'top', 'bot'],
           f'the Scrobbling page: the switch and its note, the two accounts, Auto Upload and Upload Scrobbles with their note ({slay})')
    expect([(r.label, r.action, r.arg, P.row_kind(r)) for r in S.rows] == [('Scrobbling', P.ACT_SCROBBLE, 0, 'switch'), ('ListenBrainz', P.ACT_LB, P.LB_PAGE_INDEX, 'value'), ('Last.fm', P.ACT_LF, P.LF_PAGE_INDEX, 'value'),
                                                                           ('Auto Upload', P.ACT_LBAUTO, 0, 'switch'), ('Upload Scrobbles', P.ACT_SCROBUP, 0, 'action')] and LIB_ROWS == 5,
           'a switch, two value rows opening their pages, a switch, an action row; five rows')
    for G, info, note, lines in ((B, P.INFO_LBACCT, P.LB_NOTE, 3), (F, P.INFO_LFACCT, P.LF_NOTE, 5)):
        expect([(r.label, r.action, r.arg, P.row_kind(r)) for r in G.rows] == [('Account', P.ACT_INFO, info, 'info')] and [type(x) for x in G.layout] == [P.Row, P.Note]
               and G.layout[1].text == note and G.layout[1].lines == lines and G.wrap_notes() == 1 and ST.pieces(G.layout) == ['single'],
               f'the {G.title} page: one card of one row, Account (no Token row, no Sign Out: the account is the card\'s file), and the wrapping note under it')
    expect(P.LB_AUTO_NOTE == 'Uploads on Wi-Fi while music plays.' and P.ACT_LBAUTO in P.SWITCH_ACTIONS and P.ACT_SCROBBLE in P.SWITCH_ACTIONS, 'both switches are switch rows')
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Scrobbling', 'ListenBrainz', 'Last.fm', 'Upload Scrobbles', 'Auto Upload')] == ['list-music', '+musicbrainz:filled', '+lastdotfm:filled', 'upload', 'clock'], 'the glyphs: list-music, the MusicBrainz and Last.fm marks (filled, one colour), upload and clock')
    lt = awtk_ui.parse(open(os.path.join(UI, L.key + '.bin'), 'rb').read())
    r_sc = lt.find(f'pod_row{len(L.rows) - 1}')
    expect(r_sc.find('pod_icon').get('image') == 'pod_ci_list_music' and r_sc.find('pod_chevron') is not None and r_sc.find(f'pod_value{len(L.rows) - 1}').get('tr_text') == 'Off'
           and r_sc.find(f'pod_label{len(L.rows) - 1}').get('tr_text') == 'Scrobbling' and r_sc.find(f'pod_switch{len(L.rows) - 1}') is None,
           'the Library asset: the Scrobbling row has its glyph, a value (Off at rest) and the chevron, no switch')
    st = awtk_ui.parse(open(os.path.join(UI, S.key + '.bin'), 'rb').read())
    r_sw, r_lb, r_lf, r_au, r_up = (st.find(f'pod_row{i}') for i in range(5))
    expect(r_sw.find('pod_icon').get('image') == 'pod_ci_list_music' and r_sw.find(f'pod_switch{R_SW}') is not None and r_sw.find('pod_chevron') is None and r_sw.find(f'pod_label{R_SW}').get('tr_text') == 'Scrobbling',
           'the Scrobbling switch: its glyph and the switch, no chevron')
    for r, i, label, glyph in ((r_lb, R_LB, 'ListenBrainz', 'musicbrainz'), (r_lf, R_LF, 'Last.fm', 'lastdotfm')):
        expect(r.find('pod_icon').get('image') == 'pod_ci_' + glyph and r.find('pod_chevron') is not None and r.find(f'pod_value{i}').get('tr_text') == 'Not Set'
               and r.find(f'pod_label{i}').get('tr_text') == label, f'the Scrobbling asset: the {label} row has its glyph, a value (Not Set at rest) and the chevron')
    expect(r_up.find('pod_icon').get('image') == 'pod_ci_upload' and r_up.find('pod_chevron') is None and r_up.find(f'pod_value{R_UP}') is None and r_up.find(f'pod_label{R_UP}').get('tr_text') == 'Upload Scrobbles',
           'the Upload Scrobbles row has its glyph and no accessory')
    expect(r_au.find('pod_icon').get('image') == 'pod_ci_clock' and r_au.find(f'pod_switch{R_AUTO}') is not None and r_au.find('pod_chevron') is None and r_au.find(f'pod_value{R_AUTO}') is None
           and r_au.find(f'pod_label{R_AUTO}').get('tr_text') == 'Auto Upload', 'Auto Upload: its glyph and the switch, no value, no chevron')
    expect({r.h for r in (r_lb, r_lf, r_up, r_au)} == {ST.ROW_H} and r_lf.y - r_lb.y == r_up.y - r_au.y == ST.ROW_H and r_au.y - r_lf.y > ST.ROW_H and r_lb.y - r_sw.y > ST.ROW_H,
           'the account rows are one card and Auto Upload with Upload Scrobbles another, a row apart; the switch is a card of its own above')
    notes = [w.get('tr_text') for w in st.walk() if w.name.startswith('pod_note') and w.name.endswith('_t')]
    expect(notes == ['Saved to .scrobbler.log on the card.', P.LB_AUTO_NOTE], f'the two notes ({notes})')
    expect(all(r.get('sensitive') != 'false' for r in (r_sw, r_lb, r_lf, r_au, r_up)), 'no row of the page is dimmed in the asset (a log already on the card can be uploaded with Scrobbling off)')
    for G, note, lines in ((B, P.LB_NOTE, 3), (F, P.LF_NOTE, 5)):
        bt = awtk_ui.parse(open(os.path.join(UI, G.key + '.bin'), 'rb').read())
        row = bt.find('pod_row0')
        expect(row is not None and row.h == ST.ROW_H and row.find('pod_icon') is None and bt.find('pod_row1') is None and bt.find('label_title').get('tr_text') == G.title, f'the {G.title} asset: one row, no glyph, the title')
        expect(row.find('pod_chevron') is None and row.get('sensitive') == 'false' and row.find('pod_value0').get('text') in ('', None) and not [w for w in bt.walk() if w.name == 'pod_chevron']
               and row.find('pod_label0').get('tr_text') == 'Account' and row.find('pod_label0').x == ST.CM + ST.PAD and not {'Token', 'Sign Out'} & {w.get('tr_text') for w in bt.walk()},
               'Account: a value, no chevron, no touch; nothing on the page opens anything; no Token and no Sign Out label')
        nt = bt.find('pod_note0_t')
        expect(nt is not None and nt.get('tr_text') == note and nt.h >= lines * 16 and bt.find('pod_note1_t') is None, f'the note under the card, {lines} lines high ({nt.h if nt is not None else None})')
        colours = {v.upper() for w in bt.walk() for k, v in w.props if k.endswith('_color') and isinstance(v, str) and v.startswith('#')}
        expect(colours <= {'#000000', '#FFFFFF', '#00000000', ST.GREY.upper(), '#1C1C1E', '#333333'} | {c.upper() for c in (ST.CARD_RGB, ST.CARD_HAIR_RGB)}, f'neutral colours only ({sorted(colours)})')
    png = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx', 'pod_ci_upload.png')   # noqa: F821
    from PIL import Image
    im = Image.open(png).convert('RGBA')
    ref = Image.open(os.path.join(os.path.dirname(png), 'pod_ci_headphones.png'))
    ink = {p[:3] for p in im.getdata() if p[3]}
    expect(im.size == ref.size and ink <= {(255, 255, 255)}, f'the upload glyph: a white card glyph of the set\'s size ({im.size})')


def strings_tests(ctx):
    """Every string in 13 languages, the format strings with their numbers."""
    expect = ctx.expect
    for k in KEYS:
        by = pod_i18n.TEXT.get(k)
        expect(by is not None and all(by.get(loc) for loc in pod_i18n.LOCALES), f'{k!r} has a text in the 13 languages')
        if by: expect(all(t.count('%d') == k.count('%d') for t in by.values()), f'{k!r}: as many %d in every language')
    expect(set(pod_i18n.TEXT['ListenBrainz'].values()) == {'ListenBrainz'} and all('scrobble.ini' in t for t in pod_i18n.TEXT[P.LB_NOTE].values())
           and all('listenbrainz.org' in t for t in pod_i18n.TEXT[P.LB_NOTE].values()) and P.LB_NOTE == 'Put your token from listenbrainz.org in scrobble.ini on the card.'
           and set(pod_i18n.TEXT['Last.fm'].values()) == {'Last.fm'} and all(all(w in t for w in ('scrobble.ini', '[LASTFM]', 'USER', 'PASSWORD', 'API_KEY', 'API_SECRET', 'last.fm/api')) for t in pod_i18n.TEXT[P.LF_NOTE].values())
           and not [k for k in pod_i18n.TEXT if k.startswith('Sign out of ListenBrainz') or k in ('Invalid token', 'Set up ListenBrainz first')]
           and not [k for k in pod_i18n.TEXT if 'listenbrainz-token' in k or k in ('Token imported', 'Token', 'Set', 'Not a valid token') or k.startswith('Type the token')],
           'ListenBrainz, the site and the file name stay as they are; the note names the file only, and the strings of the token entry are gone')
    two = pod_i18n.TEXT['%d sent, %d rejected']
    expect(all(t.index('%d') < t.rindex('%d') for t in two.values()), 'sent comes before rejected in every language (the arguments\' order)')
    src = open(os.path.join(ROOT, 'patch', 'scrobpage.c')).read()   # noqa: F821
    import re
    used = set(re.findall(r'TR\("((?:[^"\\]|\\.)*)"\)', src))
    expect(used and used <= set(pod_i18n.TEXT) and set(TOASTS) <= used, f'every TR() key of patch/scrobpage.c is in the tables ({sorted(used - set(pod_i18n.TEXT))})')
    expect(not any('q2' in t.lower() for k in KEYS for t in pod_i18n.TEXT[k].values()), 'no text names another project')
    expect('keyboard' not in src and 'pod_confirm' not in src and not [s for s in ('lb_token_tap', 'lb_token_done', 'lb_token_text', 'scrobup_token_set', 'lb_signout', 'lb_out_show', 'scrobup_token_clear', 'scrobup_lastfm_clear') if s in PSYMS],   # noqa: F821
           'no account entry and no sign-out on the device: patch/scrobpage.c has nothing of the keyboard or a confirm, and the payload no Token row routine, no token setter and no sign-out')


def value_tests(ctx):
    """What the rows say in each state of the account."""
    expect = ctx.expect
    m = lbpage(token=None)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('Not Set', 'Not Set') and value(m, R_LF) == 'Not Set',
           f'no token: Not Set on the Library rows and the Account row ({value(m, R_LB)!r}, {value(m, R_ACCT)!r})')
    expect(not [c for c in m.log if c[0] == 'pthread_create'] and not m.site.reqs and not toasts(m, m.log) and lbs(m, 'timer') == 0 and not [c for c in m.log if c[0] == 'timer_add'],
           'opening the pages without an account starts nothing: no thread, no request, no toast, no timer')
    m = lbpage(name=None, wifi=-1)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('', ''),
           f'a token no check confirmed: nothing on the Library row, no name on the Account row ({value(m, R_LB)!r}, {value(m, R_ACCT)!r})')
    expect(not [c for c in m.log if c[0] == 'pthread_create'] and not m.site.reqs, 'opening the pages without Wi-Fi checks nothing')
    m = lbpage(name='rob')
    expect((value(m, R_LB), value(m, R_ACCT)) == ('rob', 'rob'), f'a checked token: the user name on both pages ({value(m, R_LB)!r}, {value(m, R_ACCT)!r})')
    shown = [c[2] for c in m.log if c[0] == 'widget_set_text_utf8']
    expect(not any(TOKEN in undo(t) or TOKEN[:8] in undo(t) for t in shown), 'the token itself is never put in a widget')   # noqa: F821
    m = lbpage(name='ロブ' * 9)
    expect(value(m, R_ACCT) == 'ロブ' * 9 == value(m, R_LB), 'a name that is not ASCII is shown as it is')
    # the value fits beside its label: the Library row from the glyph column
    m = library(name='rob')
    lw = [c for c in m.log if c[0] == 'widget_resize' and c[1] == m.widgets[f'pod_label{R_LB}']]
    expect(lw and lw[-1][2] > 0, 'the Library row fits its value and gives the label the rest')
    # Invalid Token is remembered in RAM, the token kept
    m = lbpage(name='rob', answers=[SU.answer(valid=False)])
    retoken(m, TOKEN + 'x')
    expect(value(m, R_ACCT) == 'Checking…' and value(m, R_LB) == '' and SU.kind(m) == SU.CHECK, f'while the check runs the Account row says Checking… ({value(m, R_ACCT)!r})')
    work(m); tick(m)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('Invalid Token', 'Invalid Token') and token_file(m) == ini(TOKEN + 'x') and invalid(m) == 1 and not toasts(m),
           f'a refused token: Invalid Token on both pages, the token kept, no toast ({value(m, R_LB)!r}, {value(m, R_ACCT)!r}, {token_file(m)!r})')
    event(m, 'm1plus_listenbrainz', EVT_DESTROY); event(m, 'm1plus_scrobbling', EVT_DESTROY)
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(value(m, R_LB) == 'Invalid Token' and INI in m.fs and m.thread is None, 'it is still Invalid Token when the page opens again (this boot)')
    m.site.answers = [SU.answer('rob')]
    open_page(m, P.LB_PAGE)
    retoken(m)
    expect(value(m, R_ACCT) == 'Checking…' and invalid(m) == 0, 'another token in the file forgets it and is checked')
    work(m); tick(m)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('rob', 'rob') and token_file(m) == ini(name='rob'), f'a valid check: the user name ({value(m, R_LB)!r}, {token_file(m)!r})')
    # a check that fails says nothing and leaves the token unchecked
    m = lbpage(token=None, answers=[{'rc': 7, 'code': 0}])
    retoken(m)
    work(m); tick(m)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('', '') and invalid(m) == 0 and not toasts(m, m.log) and lbs(m, 'timer') == 0,
           f'no answer: the token stays, unchecked, nothing is said ({value(m, R_ACCT)!r})')


def open_tests(ctx):
    """A page that opens reads the card's scrobble.ini again (a file written on a computer needs no reboot) and checks a token no check has confirmed; never from the timer."""
    expect = ctx.expect
    pc = '[listenbrainz]\r\ntoken = ' + TOKEN + '\r\n'
    for opener, what in ((library, 'the Library page'), (lambda **kw: lbpage(lib=False, **kw), 'the ListenBrainz page')):
        m = opener(raw=pc, answers=[SU.answer('rob')])
        expect(not toasts(m, m.opened) and m.job is not None and SU.kind(m) == SU.CHECK and [(c[1], c[2]) for c in m.opened if c[0] == 'timer_add'] == [(PSYMS['lb_tick'], TICK_MS)],   # noqa: F821
               f'{what} opens with a token written on a computer (no USER): it is checked at once, without a toast')
        work(m); tick(m)
        expect(account_name(m) == 'rob' and token_file(m) == (pc + 'USER=rob\r\n').encode() and not toasts(m, m.log), f'{what}: the check writes the user name into the file, behind the token ({token_file(m)!r})')
        m = opener(raw=pc, wifi=-1)
        expect(not toasts(m, m.opened) and getattr(m, 'job', None) is None and not [c for c in m.opened if c[0] == 'timer_add'] and token_file(m) == pc.encode(), f'{what}, no Wi-Fi: not checked, the file untouched')
        m = opener(raw=pc + 'user = rob\r\n')
        expect(not toasts(m, m.opened) and getattr(m, 'job', None) is None and not [c for c in m.opened if c[0] == 'timer_add'] and not m.site.reqs and account_name(m) == 'rob',
               f'{what}, a USER line in the file: the name is shown without a request (after a reboot too)')
        m = opener(raw='[LISTENBRAINZ]\nTOKEN=this is not a token\n')
        expect(not toasts(m, m.opened) and getattr(m, 'job', None) is None and account_name(m) is None and not [c for c in SU.wrote(m) if c[1].startswith(INI)], f'{what}, a file that holds no token: Not Set, no toast, the file left alone')
        m = opener(token=None)
        expect(not toasts(m, m.opened) and getattr(m, 'job', None) is None and not [c for c in m.opened if c[0] == 'timer_add'] and INI not in m.fs, f'{what}, no file: nothing, and none is made')
        m = opener(name='rob'); m.card_mounted = False
        event(m, 'm1plus_listenbrainz' if what.startswith('the ListenBrainz') else 'm1plus_scrobbling', EVT_DESTROY)
        m.opened = open_page(m, P.LB_PAGE if what.startswith('the ListenBrainz') else P.SCROBBLING_PAGE)
        expect(account_name(m) is None and not [c for c in m.opened if c[0] == 'open' and c[1].startswith('/mnt/mmc')], f'{what}, no card: Not Set, nothing under the mount point is opened')
    # the rows follow what the file holds when the page opens
    m = library(raw=pc, wifi=-1)
    expect(value(m, R_LB) == '' and lbs(m, 'pages') == 1, 'a token without a name: the Library row is empty')
    event(m, 'm1plus_scrobbling', EVT_DESTROY)
    m.fs[INI] = SU.ini('typed-on-a-pc', 'bob').encode()
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(value(m, R_LB) == 'bob' and not m.site.reqs, 'the file changed on a computer while the page was closed: the row shows it when the page opens, no reboot')
    m.fs[INI] = SU.ini('changed-again', 'eve').encode()
    m.calls = []; n = len(m.log)
    for _ in range(3): tick(m)
    event(m, 'm1plus_scrobbling', EVT_FG)
    run(m, PSYMS['pod_lb_refresh'])   # noqa: F821
    expect(not [c for c in m.log[n:] if c[0] in ('open', 'statfs') and c[1].startswith('/mnt/mmc')] and value(m, R_LB) == 'bob', 'the card is not read from the timer, when the page comes back in front, or by a refresh of the rows')
    m.opened = open_page(m, P.LB_PAGE)
    expect(value(m, R_ACCT) == 'eve' and value(m, R_LB) == 'eve', 'the next page that opens reads it')
    # a token the service refused is not asked again by a page that opens; a check that fails is tried again by the next one
    m = lbpage(answers=[SU.answer(valid=False)])
    work(m); tick(m)
    expect(value(m, R_ACCT) == 'Invalid Token' and len(m.site.reqs) == 1, '(a token written on a computer that the service refuses: Invalid Token)')
    event(m, 'm1plus_listenbrainz', EVT_DESTROY); m.job = None
    m.opened = open_page(m, P.LB_PAGE)
    expect(m.job is None and len(m.site.reqs) == 1 and value(m, R_ACCT) == 'Invalid Token', 'the page opens again: no second check of the refused token')
    m.fs[INI] = SU.ini('fixed-on-a-pc').encode(); m.site.answers = [SU.answer('rob')]
    event(m, 'm1plus_listenbrainz', EVT_DESTROY)
    m.opened = open_page(m, P.LB_PAGE)
    expect(m.job is not None and value(m, R_ACCT) == 'Checking…' and invalid(m) == 0, 'another token written on a computer: not invalid any more, checked when the page opens')
    work(m); tick(m)
    expect(value(m, R_ACCT) == 'rob' and m.site.reqs[-1]['heads'] == ['Authorization: Token fixed-on-a-pc'], 'and confirmed')
    m = lbpage(lib=False, answers=[{'rc': 7, 'code': 0}, SU.answer('rob')])
    work(m); tick(m)
    expect(value(m, R_ACCT) == '' and not toasts(m, m.log), '(a check that gets no answer: nothing said)')
    event(m, 'm1plus_listenbrainz', EVT_DESTROY)
    m.opened = open_page(m, P.LB_PAGE); work(m); tick(m)
    expect(value(m, R_ACCT) == 'rob' and len(m.site.reqs) == 2, 'the next page that opens asks again')


def library_tests(ctx):
    """The Library page's one Scrobbling row: On or Off as the switch on the Scrobbling page, a tap opens that page, and the value is right when the page is in front again."""
    expect = ctx.expect
    R = len(P.LIBRARY_PAGE.rows) - 1
    m = machine(name='rob', log=log_text(2))
    m.opened = open_page(m, P.LIBRARY_PAGE)
    expect(value(m, R) == 'Off' and not [c for c in m.opened if c[0] == 'timer_add'] and lbs(m, 'pages') == 0 and not m.site.reqs and getattr(m, 'job', None) is None,
           'the Library page: Off at rest; it starts no timer and no check (the accounts are the Scrobbling page\'s)')
    calls = click(m, R)
    expect(('window_open', P.SCROBBLING_PAGE.key) in calls, 'a tap on the row opens the Scrobbling page')
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(lbs(m, 'pages') == 1 and value(m, R_LB) == 'rob', 'the Scrobbling page registers with the scrobble timer logic and shows the account')
    click(m, R_SW)   # (the switch is bound to the page's row 0)
    expect(m.fs.get('/mnt/data/m1plus/scrobbling') == b'1\n', 'the page\'s switch saves the setting')
    event(m, 'm1plus_scrobbling', EVT_DESTROY)
    event(m, 'm1plus_library', EVT_FG)
    expect(value(m, R) == 'On', f'back on the Library page: the row says On ({value(m, R)!r})')
    click(m, R)
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    click(m, R_SW)
    event(m, 'm1plus_scrobbling', EVT_DESTROY)
    event(m, 'm1plus_library', EVT_FG)
    expect(value(m, R) == 'Off' and m.fs.get('/mnt/data/m1plus/scrobbling') == b'0\n', 'and Off again after the switch is turned off')
    # Scrobbling off: the rows below stay active
    m = machine(name='rob', log=log_text(2)); m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(all(sens(m, i) == 1 for i in (R_LB, R_LF, R_AUTO, R_UP)), 'with Scrobbling off the account rows, Auto Upload and Upload Scrobbles are not dimmed')
    expect(start_upload(m) == ['Uploading scrobbles'], 'and Upload Scrobbles still uploads the log')


def front_tests(ctx):
    """Back in front, the Scrobbling page watches scrobble.ini like the account pages (lb_on_front): the timer is set again for a job that ended while the page was covered."""
    expect = ctx.expect
    m = library(name='rob', log=log_text(3))
    start_upload(m)
    event(m, 'm1plus_scrobbling', EVT_FG)
    expect(lbs(m, 'timer') != 0 and lbs(m, 'job') != 0, 'the foreground event of the Scrobbling page keeps the watch on its job')


def account_name(m):
    r, name = SU.account(m)
    return name.decode('utf-8') if r else None


def start_upload(m):
    calls = click(m, R_UP)
    return toasts(m, calls)


def upload_tests(ctx):
    """Upload Scrobbles: each refusal in its order, the start, and each final toast."""
    expect = ctx.expect
    # the order: a running job, USB mode, no card, no token, no Wi-Fi
    for kw in (dict(token=None), dict(name='rob')):
        m = library(wifi=-1, log=log_text(3), **kw); m.windows['usbmode_page'] = 1; m.card_mounted = False
        expect(start_upload(m) == ['Not available in USB mode'] and m.thread is None, 'USB mode comes first (the computer has the card, and the token with it): Not available in USB mode')
    m = library(name='rob', wifi=-1, log=log_text(3)); m.card_mounted = False
    expect(start_upload(m) == ['Storage unavailable'] and m.thread is None, 'no card comes before the token and Wi-Fi: Storage unavailable, not "Set up an account first"')
    m = library(token=None, wifi=-1, log=log_text(3))
    expect(start_upload(m) == ['Set up an account first'] and m.thread is None, 'no account comes before Wi-Fi: Set up an account first')
    m = library(raw='[LISTENBRAINZ]\nTOKEN=\n', log=log_text(3))
    expect(start_upload(m) == ['Set up an account first'] and m.thread is None, 'an empty TOKEN= is no token')
    m = library(raw=SU.lf_ini(), log=log_text(3), wifi=-1); m.site.answers = SU.Lastfm(); m.wifi = 4
    expect(start_upload(m) == ['Uploading scrobbles'] and m.thread, 'a Last.fm account alone is an account (either service counts): the upload starts')
    m = library(name='rob', wifi=-1, log=log_text(3))
    expect(start_upload(m) == ['Connect to Wi-Fi first'] and m.thread is None and not m.site.reqs and SU.log_of(m) == log_text(3), 'no Wi-Fi: Connect to Wi-Fi first, nothing starts')
    m = library(token=None, log=log_text(3), wifi=4); m.fs[INI] = ini()   # (written after the page opened: the tap reads the file again)
    t = start_upload(m)
    expect(t == ['Uploading scrobbles'] and token_file(m) == ini() and value(m, R_LB) == '', f'a scrobble.ini that appeared since the page opened is read by the tap, and the upload starts ({t})')
    m = library(name='rob', log=log_text(3))
    t = start_upload(m); tm = timers(m)
    expect(t == ['Uploading scrobbles'] and m.thread is not None and SU.kind(m) == SU.UPLOAD and SU.busy(m) == 1 and tm == [(PSYMS['lb_tick'], TICK_MS)] and lbs(m, 'job') == 1,   # noqa: F821
           f'with a token and Wi-Fi: the upload starts, Uploading scrobbles, the 500 ms timer ({t}, {tm})')
    expect(start_upload(m) == ['Already uploading'] and m.thread is None and not timers(m) and len([c for c in m.log if c[0] == 'pthread_create']) == 1, 'a second tap while it runs: Already uploading, no second thread or timer')
    expect(tick(m) == O['RET_REPEAT'] and not toasts(m) and SU.busy(m) == 1, 'a tick while it runs: nothing, the timer goes on')   # noqa: F821
    work(m)
    r = tick(m)
    expect(r == O['RET_OK'] and toasts(m, m.tc) == ['Scrobbles sent: 3'] and SU.busy(m) == 0 and lbs(m, 'timer') == 0 and lbs(m, 'job') == 0 and SU.log_of(m) == SU.HEADER,   # noqa: F821
           f'the end: one toast, Scrobbles sent: 3, the timer ends, the log is empty ({toasts(m)})')
    expect(tick(m) == O['RET_OK'] and not toasts(m), 'the toast comes once')   # noqa: F821
    expect(start_upload(m) == ['Uploading scrobbles'], 'another upload can start after it')
    work(m); tick(m)
    expect(toasts(m) == ['Nothing to upload'], f'an empty log: Nothing to upload ({toasts(m)})')
    # a check running is a job too
    m = lbpage(token=None, log=log_text(3), answers=[SU.answer('rob')])
    retoken(m)
    expect(start_upload(m) == ['Already uploading'] and SU.kind(m) == SU.CHECK and lbs(m, 'job') == 2, 'while the token is being checked: Already uploading, the check goes on')
    work(m); tick(m)
    expect(value(m, R_LB) == 'rob' and start_upload(m) == ['Uploading scrobbles'], 'after the check the upload starts')
    # the Scrobbling switch off does not block it
    m = library(name='rob', log=log_text(2)); m.fs['/mnt/data/m1plus/scrobbling'] = b'0\n'
    expect(start_upload(m) == ['Uploading scrobbles'], 'the Scrobbling switch off does not block an upload')
    # no card: nothing starts
    m = library(name='rob', log=log_text(2)); m.card_mounted = False
    t = start_upload(m)
    expect(t == ['Storage unavailable'] and m.thread is None and lbs(m, 'job') == 0 and not timers(m), f'no card: Storage unavailable, nothing starts ({t})')
    # the final toasts
    sixty = log_text(60)
    for what, kw, want, check in (
            ('two batches taken', dict(answers=[{}]), 'Scrobbles sent: 60', None),
            ('a batch refused for good', dict(answers=[{}, {'code': 400}]), '50 sent, 10 rejected', None),
            ('every batch refused', dict(answers=[{'code': 400}]), '0 sent, 60 rejected', None),
            ('a 401', dict(answers=[{'code': 401}]), 'ListenBrainz: Invalid Token', 'Invalid Token'),
            ('a 401 after a batch', dict(answers=[{}, {'code': 401}]), 'ListenBrainz: Invalid Token', 'Invalid Token'),
            ('a 500 after a batch', dict(answers=[{}, {'code': 500}]), 'Upload failed, 50 sent', 'rob'),
            ('no connection', dict(answers=[{'rc': 7, 'code': 0}]), 'Upload failed, 0 sent', 'rob'),
            ('a 429', dict(answers=[{'code': 429}]), 'Upload failed, 0 sent', 'rob')):
        m = library(name='rob', log=sixty, **kw)
        start_upload(m); work(m); tick(m)
        expect(toasts(m) == [want] and lbs(m, 'timer') == 0, f'{what}: {want} ({toasts(m)})')
        if check: expect(value(m, R_LB) == check and token_file(m) == ini(name='rob'), f'{what}: the ListenBrainz row says {check}, the token is kept ({value(m, R_LB)!r})')
    m = library(name='rob', log=sixty); m.fail.add(('rename', LOG))
    start_upload(m); work(m); tick(m)
    expect(toasts(m) == ['Card error, 60 sent'] and SU.log_of(m) == sixty, f'the card does not take the new log: Card error, 60 sent ({toasts(m)})')
    # Invalid Token shows on the ListenBrainz page too, and a later good upload clears it
    m = lbpage(name='rob', log=sixty, answers=[{'code': 401}])
    start_upload(m); work(m); tick(m)
    expect(value(m, R_ACCT) == 'Invalid Token' and value(m, R_LB) == 'Invalid Token', 'after a 401 the Account row says Invalid Token')
    m.site.answers = [{}]
    start_upload(m); work(m); tick(m)
    expect(toasts(m) == ['Scrobbles sent: 60'] and value(m, R_LB) == 'rob' and invalid(m) == 0, 'listens taken with the token: it is not invalid any more')


def owner_tests(ctx):
    """Whose result a poll is, the dark screen, and the timer's life."""
    expect = ctx.expect
    # the automatic upload's job (patch/scrobble.c): watched while it runs, never polled as ours, collected without a word once it is over
    m = machine(name='rob', log=log_text(3))
    expect(SU.start(m, SU.AUTO) == 1, 'an automatic upload runs')
    foreign = m.thread
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect([(c[1], c[2]) for c in m.opened if c[0] == 'timer_add'] == [(PSYMS['lb_tick'], TICK_MS)] and lbs(m, 'job') == 0 and SU.busy(m) == 1, 'a page that opens while it runs watches it (the timer), and does not own it')   # noqa: F821
    expect(start_upload(m) == ['Already uploading'] and m.thread is None, 'Upload Scrobbles then: Already uploading')
    m.log = []
    r = [tick(m) for _ in range(3)]
    expect(r == [O['RET_REPEAT']] * 3 and SU.busy(m) == 1 and 'pthread_join' not in SU.names(m) and not toasts(m, m.log) and not [c for c in m.log if c[0] == 'reset_poweroptions_timer'],   # noqa: F821
           'while it runs our ticks only watch: no poll, no toast, no keep-awake for a job the user did not start')
    SU.call(m, foreign[0], a0=foreign[1], count=1 << 40)
    m.log = []
    r = tick(m)
    expect(r == O['RET_OK'] and SU.busy(m) == 0 and 'pthread_join' in SU.names(m) and not toasts(m, m.log) and lbs(m, 'timer') == 0 and lbs(m, 'done') == 0 and SU.log_of(m) == SU.HEADER,   # noqa: F821
           'over: the next tick collects it (scrobble_auto_collect), silently: no toast, and the timer ends')
    expect(start_upload(m) == ['Uploading scrobbles'], 'and the user\'s own upload can start')
    work(m); tick(m)
    expect(toasts(m) == ['Nothing to upload'], f'with its own toast ({toasts(m)})')
    # an automatic upload that ended with no page up and no music (nobody collected it) does not block the user
    m = library(name='rob', log=log_text(3))
    expect(SU.start(m, SU.AUTO) == 1, '(an automatic upload starts ...)')
    foreign = m.thread
    SU.call(m, foreign[0], a0=foreign[1], count=1 << 40)
    m.fs[LOG] += SU.line(7).encode()
    t = start_upload(m)
    expect(t == ['Uploading scrobbles'] and m.thread is not None and lbs(m, 'job') == 1 and SU.owner(m) == SU.UI, f'... and is over, not collected: a tap collects it silently and starts the user\'s upload at once ({t})')
    work(m); tick(m)
    expect(toasts(m) == ['Scrobbles sent: 1'], f'whose toast counts its own listens only ({toasts(m)})')
    m = machine(name='rob', log=log_text(3))
    SU.start(m, SU.AUTO); foreign = m.thread
    SU.call(m, foreign[0], a0=foreign[1], count=1 << 40)
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(SU.busy(m) == 0 and not toasts(m, m.opened) and not [c for c in m.opened if c[0] == 'timer_add'] and lbs(m, 'done') == 0, 'a page that opens after it ended collects it: no toast, no timer')
    # a token the automatic upload found refused: Invalid Token on the rows, still no toast
    m = lbpage(name='rob', log=log_text(3), answers=[{'code': 401}])
    SU.start(m, SU.AUTO); foreign = m.thread
    SU.call(m, foreign[0], a0=foreign[1], count=1 << 40)
    event(m, 'm1plus_listenbrainz', EVT_FG)
    m.log = []; tick(m)
    expect((value(m, R_LB), value(m, R_ACCT)) == ('Invalid Token', 'Invalid Token') and invalid(m) == 1 and not toasts(m, m.log) and SU.busy(m) == 0,
           f'an automatic upload answered 401, collected by the page: both rows say Invalid Token, nothing is toasted ({value(m, R_LB)!r}, {value(m, R_ACCT)!r})')
    # an automatic upload running where our upload was expected: the same kind, another owner
    m = library(name='rob', log=log_text(3), answers=[{}])
    start_upload(m); work(m)
    expect(SU.poll(m) == (SU.OK, 3), '(another caller polls our upload)')
    m.fs[LOG] = log_text(2).encode()
    expect(SU.start(m, SU.AUTO) == 1, '(and an automatic upload starts)')
    other = m.thread
    m.log = []
    r = tick(m)
    expect(r == O['RET_REPEAT'] and lbs(m, 'job') == 0 and 'pthread_join' not in SU.names(m) and not toasts(m), 'an automatic upload runs where ours was expected: not polled as ours (the owner is asked), our claim dropped')   # noqa: F821
    SU.call(m, other[0], a0=other[1], count=1 << 40)
    m.log = []
    r = tick(m)
    expect(r == O['RET_OK'] and SU.busy(m) == 0 and not toasts(m, m.log) and lbs(m, 'done') == 0, 'its end is collected silently: never a toast for a job the user did not start')   # noqa: F821
    # our upload's result taken by another caller, and a check running in its place: nothing of the check is read as an upload
    m = library(name='rob', log=log_text(3), answers=[{}])
    start_upload(m); work(m)
    expect(SU.poll(m) == (SU.OK, 3), '(another caller polls our upload)')
    m.site.answers = [SU.answer(valid=False)]
    expect(SU.check_start(m) == 1, '(and starts a check)')
    other = m.thread
    m.log = []
    r = tick(m)
    expect(r == O['RET_REPEAT'] and lbs(m, 'job') == 0 and 'pthread_join' not in SU.names(m) and not toasts(m), 'a check runs where our upload was expected: not polled, no toast, our claim dropped')   # noqa: F821
    SU.call(m, other[0], a0=other[1], count=1 << 40)
    tick(m)
    expect(SU.busy(m) == 1 and not toasts(m, m.log) and invalid(m) == 0 and value(m, R_LB) == 'rob', 'its result is not read here: no toast, no Invalid Token from somebody else\'s check')
    expect(SU.poll(m) == (SU.AUTH, 0), 'the check\'s owner still gets its result')
    # the other way round: our check's result taken, an upload running in its place
    m = lbpage(token=None, log=log_text(3), answers=[SU.answer('rob')])
    retoken(m)
    work(m)
    expect(SU.poll(m) == (SU.OK, 0) and SU.start(m) == 1, '(another caller polls our check and starts an upload)')
    other = m.thread
    SU.call(m, other[0], a0=other[1], count=1 << 40)
    m.log = []
    r = tick(m)
    expect(r == O['RET_REPEAT'] and lbs(m, 'job') == 0 and not toasts(m) and 'pthread_join' not in SU.names(m), 'an upload is over where our check was expected: not polled, no toast')   # noqa: F821
    expect(SU.poll(m) == (SU.OK, 3) and tick(m) == O['RET_OK'] and value(m, R_ACCT) == 'rob', 'the upload\'s owner gets it; the rows then show the name the check stored')   # noqa: F821
    # our result gone and nothing running
    m = library(name='rob', log=log_text(3))
    start_upload(m); work(m); SU.poll(m)
    expect(tick(m) == O['RET_OK'] and not toasts(m) and lbs(m, 'job') == 0 and lbs(m, 'timer') == 0, 'our result went to another caller and nothing runs: the timer ends, nothing is said')   # noqa: F821
    # the screen dark: the poll and nothing else, the toast at the first lit tick
    m = library(name='rob', log=log_text(3))
    start_upload(m); work(m)
    m.screen(0); m.log = []
    r = tick(m)
    expect(r == O['RET_REPEAT'] and SU.busy(m) == 0 and 'pthread_join' in SU.names(m) and not toasts(m, m.tc) and not [c for c in m.tc if c[0].startswith('widget_')],   # noqa: F821
           'dark: the tick polls the result (the thread is joined) and touches no widget, shows no toast')
    r = tick(m)
    expect(r == O['RET_REPEAT'] and not toasts(m, m.tc) and not [c for c in m.tc if c[0].startswith('widget_') or c[0] in ('open', 'access', 'get_wifisignal', 'pthread_join')], 'still dark: the tick does nothing')   # noqa: F821
    m.screen(1)
    expect(tick(m) == O['RET_OK'] and toasts(m) == ['Scrobbles sent: 3'] and lbs(m, 'timer') == 0, f'lit again: the toast, once, and the timer ends ({toasts(m)})')   # noqa: F821
    # while our job runs the standby countdown is set again once a second, and only then
    m = library(name='rob', log=log_text(3))
    start_upload(m); m.log = []
    for _ in range(4): tick(m)
    keep = [c for c in m.log if c[0] == 'reset_poweroptions_timer']
    expect(len(keep) == 2, f'four ticks of a running upload: the standby countdown set again twice ({len(keep)})')
    work(m); tick(m); m.log = []
    tick(m)
    expect(not [c for c in m.log if c[0] == 'reset_poweroptions_timer'], 'and not after it')
    # the timer's life: removed when the last page goes, the job polled when one opens again
    m = lbpage(name='rob', log=log_text(3))
    start_upload(m)
    event(m, 'm1plus_listenbrainz', EVT_DESTROY)
    expect(not [c for c in m.calls if c[0] == 'timer_remove'] and lbs(m, 'timer') and lbs(m, 'pages') == 1, 'the ListenBrainz page goes, the Library page is still up: the timer stays')
    event(m, 'm1plus_scrobbling', EVT_DESTROY)
    expect([c for c in m.calls if c[0] == 'timer_remove'] == [('timer_remove', 0x777)] and lbs(m, 'timer') == 0 and lbs(m, 'pages') == 0, 'the Library page goes: the timer is removed')
    expect(tick(m) == O['RET_OK'] and SU.busy(m) == 1, 'a stray tick with no page polls nothing')   # noqa: F821
    work(m)
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(SU.busy(m) == 0 and [(c[1], c[2]) for c in m.opened if c[0] == 'timer_add'] == [(PSYMS['lb_tick'], TICK_MS)] and not toasts(m, m.opened), 'the page opens again: the finished upload is polled, its toast is due')   # noqa: F821
    expect(tick(m) == O['RET_OK'] and toasts(m) == ['Scrobbles sent: 3'], f'and comes at the first tick ({toasts(m)})')   # noqa: F821
    # ... or at an Upload Scrobbles tap, which then starts nothing
    m = library(name='rob', log=log_text(3))
    start_upload(m); event(m, 'm1plus_scrobbling', EVT_DESTROY); work(m)
    m.fs[LOG] = log_text(1).encode()
    open_page(m, P.SCROBBLING_PAGE)
    t = start_upload(m)
    expect(t == ['Scrobbles sent: 3'] and m.thread is None, f'a tap before that tick shows the result and starts nothing ({t})')
    # opening a page with nothing running arms nothing; coming back in front with a job arms the timer again
    m = library(name='rob')
    expect(not [c for c in m.log if c[0] == 'timer_add'], 'no job: no timer')
    m.timer_fail = True
    start_upload(m)
    expect(lbs(m, 'timer') == 0 and lbs(m, 'job') == 1, '(a timer that could not be added)')
    m.timer_fail = False
    event(m, 'm1plus_scrobbling', EVT_FG)
    expect(timers(m) == [(PSYMS['lb_tick'], TICK_MS)], 'the page back in front: the timer is armed for the job that runs')   # noqa: F821


def auto_tests(ctx):
    """The Auto Upload switch (the Scrobbling page's second card, for both services): off by default, a tap saves it; it starts nothing and says nothing. Its Settings Files row."""
    expect = ctx.expect

    def images(m, calls): return [undo(c[2]) if isinstance(c[2], str) else c[2] for c in calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{R_AUTO}']]   # noqa: F821
    m = library(name='rob', log=log_text(3))
    expect(images(m, m.opened)[-1:] == ['sset_off'] and AUTO_FILE not in m.fs, f'off by default: the switch shows off, no file ({images(m, m.opened)})')
    calls = click(m, R_AUTO)
    expect(images(m, calls) == ['sset_on'] and m.fs.get(AUTO_FILE) == b'1\n' and ('rename', AUTO_FILE + '.tmp', AUTO_FILE) in calls, f'a tap: on, saved atomically as "1" ({images(m, calls)}, {m.fs.get(AUTO_FILE)!r})')
    expect(not toasts(m, calls) and m.thread is None and not [c for c in calls if c[0] in ('timer_add', 'get_wifisignal', 'pthread_create')] and SU.log_of(m) == log_text(3), 'the tap starts nothing and says nothing: the uploads come from the poll of the playing track')
    calls = click(m, R_AUTO)
    expect(images(m, calls) == ['sset_off'] and m.fs.get(AUTO_FILE) == b'0\n', 'again: off, saved as "0"')
    m = machine(name='rob'); m.fs[AUTO_FILE] = b'1\n'
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(images(m, m.opened)[-1:] == ['sset_on'], 'the page opens with the saved state')
    m = lbpage(token=None)
    calls = click(m, R_AUTO)
    expect(images(m, calls) == ['sset_on'] and sens(m, R_AUTO) == 1 and not toasts(m, calls), 'without an account the switch still works (it waits for a token)')
    m = lbpage(name='rob'); m.fail.add(('write', AUTO_FILE + '.tmp'))
    calls = click(m, R_AUTO)
    expect('sset_on' not in images(m, calls) and AUTO_FILE not in m.fs, 'a save that fails: the switch stays off')
    # Settings Files: one row after the account's, showing the character
    S = P.SETTING_FILES
    idx = 5 + S.index('scrobble-auto')
    row = next(r for r in P.FILES_PAGE.rows if r.label == 'scrobble-auto')
    expect(S.index('scrobble-auto') == S.index('scrobbling') + 1 and AUTO_FILE == '/mnt/data/m1plus/' + S[idx - 5] and row.action == P.ACT_SFDEL and row.arg == P.INFO_SF + idx,
           'the Settings Files row scrobble-auto follows scrobbling (the account has no row: it is on the card) and is the file\'s name')
    expect(len(S) == 44 and P.INFO_SFOLD - P.INFO_SF == 49 and P.INFO_DUR == 65, '44 setting files: INFO_SFOLD = INFO_SF + 49, INFO_DUR 65')

    def stat(m):
        buf = m.alloc(24)
        SU.call(m, PSYMS['setfiles_stat'], a0=idx, a1=buf, a2=24, count=1 << 20)   # noqa: F821
        return m.read_cstr(buf)
    m = machine(name='rob')
    SU.call(m, PSYMS['setfiles_open'], count=1 << 26)   # noqa: F821
    expect(stat(m) == 'missing', f'no file: missing ({stat(m)})')
    m = machine(name='rob'); m.fs[AUTO_FILE] = b'1\n'
    SU.call(m, PSYMS['setfiles_open'], count=1 << 26)   # noqa: F821
    expect(stat(m) == '1', f'on: the row shows the file\'s character ({stat(m)})')


def lfpage(lib=True, **kw):
    """The Last.fm page (over the Library page, or alone), the services SU.Lastfm unless given."""
    svc = kw.pop('svc', None)
    m = machine(token=None, **kw)
    m.lf = m.site.answers = svc or SU.Lastfm()
    if lib: m.opened = open_page(m, P.SCROBBLING_PAGE)
    m.opened = open_page(m, P.LF_PAGE)
    return m


def lf_state(m):
    keep = m.calls; r = SU.lastfm(m); m.calls = keep
    return r[0]


def lastfm_tests(ctx):
    """The Last.fm row and page: the values in each state, the check when a page opens, the refusal's toast with its service; no sign-out on either page."""
    expect = ctx.expect
    both = SU.ini(name='bob') + SU.lf_ini()
    m = lfpage(raw=SU.ini(name='bob'))
    expect((value(m, R_LF), value(m, R_ACCT)) == ('Not Set', 'Not Set') and value(m, R_LB) == 'bob' and m.job is None and not m.site.reqs and not toasts(m, m.log), 'no [LASTFM] section: Not Set on the Library row and the Account row, nothing started')
    m = lfpage(raw='[LASTFM]\nUSER=rob\nPASSWORD=\nAPI_KEY=' + SU.LF_KEY + '\nAPI_SECRET=' + SU.LF_SECRET + '\n')
    expect(value(m, R_LF) == 'Not Set' and m.job is None, 'a key without a value: Not Set')
    m = lfpage(raw=both, wifi=-1)
    expect((value(m, R_LF), value(m, R_ACCT)) == ('rob', 'rob') and m.job is None and not m.site.reqs and lbs(m, 'pages') == 5, 'no Wi-Fi: the file\'s USER on both rows, no check')
    # the Library page opens: the account is asked of the service once
    m = library(token=None, raw=both); m.site.answers = SU.Lastfm()
    expect(m.job is not None and SU.kind(m) == SU.LFCHECK and value(m, R_LF) == 'rob' and value(m, R_LB) == 'bob' and not toasts(m, m.opened), 'the Library page opens with credentials not asked yet: a Last.fm check starts, without a toast')
    m.opened = open_page(m, P.LF_PAGE)
    expect(value(m, R_ACCT) == 'Checking…' and value(m, R_LF) == 'rob', f'while it runs the Account row says Checking… ({value(m, R_ACCT)!r})')
    work(m); tick(m)
    expect((value(m, R_LF), value(m, R_ACCT)) == ('rob', 'rob') and lf_state(m) == SU.LF_IN and SU.methods(m) == ['getMobileSession'] and not toasts(m, m.log) and m.fs[INI] == both.encode() and lbs(m, 'timer') == 0,
           'signed in: the name, no toast, the file not written, the timer gone')
    event(m, 'm1plus_lastfm', EVT_DESTROY); m.job = None
    m.opened = open_page(m, P.LF_PAGE)
    expect(m.job is None and len(m.site.reqs) == 1, 'the page opens again: not asked a second time')
    # refused credentials
    m = lfpage(raw=both, svc=SU.Lastfm(auth=4))
    expect(SU.kind(m) == SU.LFCHECK and m.job is not None, '(the Last.fm page opens: its check)')
    work(m); tick(m)
    expect((value(m, R_LF), value(m, R_ACCT)) == ('Sign-in Failed', 'Sign-in Failed') and value(m, R_LB) == 'bob' and not toasts(m, m.log) and m.fs[INI] == both.encode(), f'refused: Sign-in Failed on both rows, ListenBrainz as it was, no toast, the file kept ({value(m, R_ACCT)!r})')
    event(m, 'm1plus_lastfm', EVT_DESTROY); m.job = None; n = len(m.site.reqs)
    m.opened = open_page(m, P.LF_PAGE)
    expect(m.job is None and len(m.site.reqs) == n and value(m, R_ACCT) == 'Sign-in Failed', 'refused credentials are not asked again by a page that opens')
    event(m, 'm1plus_lastfm', EVT_DESTROY)
    m.fs[INI] = (SU.ini(name='bob') + SU.lf_ini(pw='another')).encode(); m.lf.auth = None
    m.opened = open_page(m, P.LF_PAGE)
    expect(m.job is not None and value(m, R_ACCT) == 'Checking…', 'another password in the file: asked again')
    work(m); tick(m)
    expect(value(m, R_ACCT) == 'rob' and lf_state(m) == SU.LF_IN, 'and signed in')
    # both accounts unconfirmed: the page's own first, Last.fm after the ListenBrainz check
    m = machine(token=None, raw=SU.ini() + SU.lf_ini()); m.site.answers = SU.Lastfm(lb=SU.answer('bob'))
    m.opened = open_page(m, P.SCROBBLING_PAGE)
    expect(m.job is not None and SU.kind(m) == SU.CHECK, 'the Library page, a token without a name and Last.fm not asked: the ListenBrainz check first')
    work(m); tick(m)
    expect(value(m, R_LB) == 'bob' and m.job is not None and SU.kind(m) == SU.LFCHECK and lbs(m, 'timer') != 0, 'its result is shown and the Last.fm check follows')
    work(m); tick(m)
    expect(lf_state(m) == SU.LF_IN and value(m, R_LF) == 'rob' and lbs(m, 'timer') == 0 and not toasts(m, m.log), 'then Last.fm is signed in; nothing was said')
    # an upload a service refuses names the service
    m = library(token=None, raw=SU.lf_ini(), log=log_text(3)); m.site.answers = SU.Lastfm(auth=4)
    work(m); tick(m)
    m.fs[INI] = SU.lf_ini(pw='again').encode()
    expect(start_upload(m) == ['Uploading scrobbles'], '(an upload with a password the service refuses)')
    work(m); tick(m)
    expect(toasts(m, m.tc) == ['Last.fm: Sign-in Failed'] and value(m, R_LF) == 'Sign-in Failed' and SU.log_of(m) == log_text(3), f'the toast names Last.fm, the row says Sign-in Failed, the log is kept ({toasts(m, m.tc)})')
    # no sign-out: the pages have one row, and the file is the user's
    m = lfpage(raw=both)
    work(m); tick(m)
    expect(not SU.wrote(m), 'the pages write nothing to the card')
    event(m, 'm1plus_lastfm', EVT_DESTROY); event(m, 'm1plus_scrobbling', EVT_DESTROY)
    m.fs[INI] = SU.ini(name='bob').encode()
    open_page(m, P.SCROBBLING_PAGE); open_page(m, P.LF_PAGE)
    expect((value(m, R_LF), value(m, R_ACCT)) == ('Not Set', 'Not Set') and value(m, R_LB) == 'bob', 'the section taken out of the file on a computer: Not Set when the pages open again (that is the sign-out)')
    del m.fs[INI]
    event(m, 'm1plus_lastfm', EVT_DESTROY); event(m, 'm1plus_scrobbling', EVT_DESTROY)
    open_page(m, P.SCROBBLING_PAGE); open_page(m, P.LB_PAGE)
    expect((value(m, R_LB), value(m, R_ACCT), value(m, R_LF)) == ('Not Set', 'Not Set', 'Not Set'), 'the file deleted: both accounts Not Set')
    expect(start_upload(m) == ['Set up an account first'], 'Upload Scrobbles then: Set up an account first')


SECTIONS = [library_tests, front_tests, pages_tests, strings_tests, value_tests, open_tests, upload_tests, owner_tests, auto_tests, lastfm_tests]   # tools/check.py runs each as its own task

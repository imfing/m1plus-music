"""Continue with Next Album (patch/nextalbum.c, docs/modules/nextalbum.md). Phase 1: the setting, the note an opener makes of the albums as shown, the page taking it, the
arm / load / disarm sequence that keeps or drops the source, and the next key. Phase 2 (end_tests .. pin_tests): hook 26 on mclNextSong's List play end branch, with stock's
own mclNextSong words executed through it. The other modules' tests (albums, coverflow, albumpage, shuffle, settings) check their own side of it with the helpers below."""
import os
import cdefs
import pod_i18n
import pod_pages
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'nextalbum.h'), strings=True)
FILE, TMP = DEFS['NA_FILE'], DEFS['NA_TMP']
KILL = '/mnt/mmc/m1plus-off'
CMAP_MAX = cdefs.defines(os.path.join(ROOT, 'patch', 'covercache.h'), ['CC_CMAP_MAX'])['CC_CMAP_MAX']
CARD, UNKNOWN = 0xfffffffe, 0xffffffff   # REC_ID of the All songs card and the Unknown Album row


def u32(m, a): return m.word(a)


def c(m, name, **k): return m.call(PSYMS[name], count=9000000, **k)   # (m.call resets the machine's call log: a check after c() looks at that call only)


def src(m, p):
    """The source block at p (patch/nextalbum.c struct na_src: ref, n, scope, own, cur, artist, keys[])."""
    if not p: return None
    n = u32(m, p + 4)
    return dict(ref=u32(m, p), n=n, scope=u32(m, p + 8), own=u32(m, p + 12), cur=u32(m, p + 16), artist=u32(m, p + 20), keys=[u32(m, p + 24 + 4 * i) for i in range(n)], ptr=p)


def state(m):
    """The module's state (struct na: loaded, on, armed, then the four slots)."""
    b = PSYMS['na.0']   # (the linker keeps a struct's members apart: na.0 is the first byte, the rest follow in the layout)
    return dict(on=m.u.mem_read(b + 1, 1)[0], armed=m.u.mem_read(b + 2, 1)[0], pending=src(m, u32(m, b + 4)), page=src(m, u32(m, b + 8)), active=src(m, u32(m, b + 12)), prev=src(m, u32(m, b + 16)))


def snap(m):
    """Make m record what an opener noted: na_note_drop is the call right after cc_open_album returns, so the pending note at that moment is the one album_open could take
    (m.noted: its keys, scope, artist copy and that copy's rows, or None). Returns m."""
    orig = m._hook
    m.noted = None

    def hook(u, address, size, d):
        if address == PSYMS['na_note_drop']:
            m.noted = state(m)['pending']
            if m.noted: m.noted['artist_rows'] = list(m.deques.get(m.noted['artist'], []))   # (the copy is destroyed with the note)
        return orig(u, address, size, d)
    m._hook = hook
    m.watch[PSYMS['na_note_drop']] = 'na_note_drop'
    return m


def on(m): m.fs[FILE] = b'1\n'; return m


def machine(setting=True):
    m = Machine()
    if setting: on(m)
    return m


def albums(m, specs):
    """A deque of album rows from (album, artist[, id]); the rows' keys."""
    rows = [m.record(album=a, artist=r, path=f'/mnt/mmc/m/{i}.flac', rid=rest[0] if rest else i + 1) for i, (a, r, *rest) in enumerate(specs)]
    return m.new_deque(rows)


def key(a, r): return album_key(r, a)


def note(m, d, order=None, n=None, scope=0, artist=0):
    """na_note_albums over the deque d; order a list of row numbers (None: stock order)."""
    ord_p = 0
    if order is not None:
        ord_p = m.alloc(4 * len(order))
        for i, v in enumerate(order): m.setword(ord_p + 4 * i, v)
    cnt = n if n is not None else (len(order) if order is not None else len(m.deques[d]))
    m.setword(STACK + 16, artist)   # the fifth argument, on the stack
    c(m, 'na_note_albums', a0=d, a1=ord_p, a2=cnt, a3=scope)


SPEC = [('Alpha', 'Zed'), ('Beta', 'Yan'), ('Gamma', 'Zed'), ('Delta', 'Xu'), ('Epsilon', 'Wu')]
KEYS = [key(a, r) for a, r in SPEC]


def setting_tests(ctx):
    """The mode: Off by default, na_set saves atomically and persists, a failed save or a mode that does not exist changes nothing; Off or under the kill switch records nothing."""
    expect = ctx.expect
    m = machine(False)
    expect(c(m, 'na_setting') == 0, 'no file: off')
    expect(DEFS['NA_OFF'] == 0 and DEFS['NA_ALBUMS'] == 1, 'the modes: Off 0, Next Albums 1')
    expect(c(m, 'na_set', a0=1) == 1 and m.fs[FILE] == b'1\n' and ('rename', TMP, FILE) in m.calls and TMP not in m.fs and c(m, 'na_setting') == 1, 'Next Albums: written atomically')
    expect(c(m, 'na_set', a0=0) == 0 and m.fs[FILE] == b'0\n' and c(m, 'na_setting') == 0, 'and Off again')
    expect(c(m, 'na_set', a0=2) == 0xffffffff and c(m, 'na_set', a0=0xffffffff) == 0xffffffff and m.fs[FILE] == b'0\n', 'a mode that does not exist (Auto Mix is not offered yet): -1, nothing written')
    for data, want in ((b'1', 1), (b'1\n', 1), (b'0\n', 0), (b'2\n', 0), (b'', 0), (b'11', 0)):
        m = machine(False); m.fs[FILE] = data
        expect(c(m, 'na_setting') == want, f'file {data!r}: {want}')
    m = machine(False); m.fail.add(('write', TMP))
    expect(c(m, 'na_set', a0=1) == 0xffffffff and FILE not in m.fs and c(m, 'na_setting') == 0, 'a failed save: -1, nothing changed')
    d = None
    m = machine(False); d = albums(m, SPEC); note(m, d)
    expect(state(m)['pending'] is None and not any(c[0] == 'calloc' for c in m.calls), 'off: a note records nothing and allocates nothing')
    m = machine(); m.present.add(KILL); d = albums(m, SPEC); note(m, d)
    expect(state(m)['pending'] is None, 'under the kill switch: nothing is recorded')
    m = machine(); d = albums(m, SPEC); note(m, d)
    expect(state(m)['pending'] is not None, 'on: the note is recorded')
    c(m, 'na_set', a0=0)
    d2 = albums(m, SPEC); c(m, 'na_note_drop'); note(m, d2)
    expect(state(m)['pending'] is None, 'turned off: recorded nothing again')


def note_tests(ctx):
    """na_note_albums: the keys in the order shown, the cards left out, the cap, the scope and artist copy, a new note replacing the old, no memory."""
    expect = ctx.expect
    m = machine(); d = albums(m, SPEC); note(m, d)
    p = state(m)['pending']
    expect(p and p['keys'] == KEYS and p['ref'] == 1 and p['scope'] == 0 and p['artist'] == 0, f'stock order: the album keys as cc_album_key makes them ({p and [hex(k) for k in p["keys"]]})')
    note(m, d, order=[4, 3, 1, 0, 2])
    p = state(m)['pending']
    expect(p['keys'] == [KEYS[i] for i in (4, 3, 1, 0, 2)], 'a sorted view: the keys follow the order array, not the stock rows')
    note(m, d, order=[2, 0, 1, 3, 4][::-1])
    expect(state(m)['pending']['keys'] == [KEYS[i] for i in (4, 3, 1, 0, 2)], 'a reversed view: the reversed order')
    old = state(m)['pending']['ptr']
    note(m, d, n=2)
    p = state(m)['pending']
    expect(p['keys'] == KEYS[:2] and ('free', old) in m.calls, 'a new note replaces the old one (its block freed); n rows only')
    # the All songs card and the Unknown Album row are not albums
    m = machine(); d = albums(m, SPEC + [('Zeta', 'Vo', UNKNOWN), ('All songs', 'Zed', CARD)])
    note(m, d)
    expect(state(m)['pending']['keys'] == KEYS, 'Unknown Album and the All songs card are skipped')
    note(m, d, order=[6, 5, 0, 1, 2, 3, 4])
    expect(state(m)['pending']['keys'] == KEYS, 'also where the order puts them first')
    m = machine(); d = albums(m, [('Zeta', 'Vo', UNKNOWN), ('All songs', 'Zed', CARD)]); note(m, d)
    expect(state(m)['pending'] is None, 'nothing left: no source')
    # n larger than the list
    m = machine(); d = albums(m, SPEC); note(m, d, n=50)
    expect(state(m)['pending']['keys'] == KEYS, 'n past the list: the list')
    # the cap
    m = machine(); big = [(f'Album {i}', f'Artist {i % 7}') for i in range(CMAP_MAX + 5)]
    d = albums(m, big); note(m, d)
    p = state(m)['pending']
    expect(p['n'] == CMAP_MAX and p['keys'][0] == key('Album 0', 'Artist 0') and p['keys'][-1] == key(f'Album {CMAP_MAX - 1}', f'Artist {(CMAP_MAX - 1) % 7}'), f'at most CC_CMAP_MAX ({CMAP_MAX}) keys, the first ones')
    # a scoped page: the artist row is copied, the scope kept
    m = machine(); d = albums(m, SPEC); art = m.new_deque([m.record(album='', artist='Zed', path='/mnt/mmc/a.flac', rid=7)])
    note(m, d, scope=O['CLASS_ARTISTS'], artist=art)
    p = state(m)['pending']
    expect(p['scope'] == O['CLASS_ARTISTS'] and p['artist'] and p['artist'] != art and m.deques[p['artist']] == m.deques[art], 'scoped: the scope and a copy of the artist row (not the page\'s deque)')
    note(m, d, scope=O['CLASS_COMPOSERS'], artist=art)
    expect(state(m)['pending']['scope'] == O['CLASS_COMPOSERS'], 'a composer\'s albums: its scope')
    old = state(m)['pending']['artist']
    note(m, d)
    expect(state(m)['pending']['artist'] == 0 and old not in m.deques, 'replaced by a library note: the artist copy is destroyed')
    # no memory: no source, no crash
    m = machine(); d = albums(m, SPEC); m.calloc_fail = True; note(m, d)
    expect(state(m)['pending'] is None, 'no memory: no source')
    m = machine(); d = albums(m, SPEC); note(m, d); m.calloc_fail = True; note(m, d)
    expect(state(m)['pending'] is None, 'no memory for a new note: the old one is gone too (never a stale order)')
    # na_note (the raw interface)
    m = machine(); ks = m.alloc(12)
    for i, v in enumerate((11, 22, 33)): m.setword(ks + 4 * i, v)
    c(m, 'na_note', a0=ks, a1=3, a2=0, a3=0)
    expect(state(m)['pending']['keys'] == [11, 22, 33], 'na_note takes keys as given')
    c(m, 'na_note', a0=0, a1=3, a2=0, a3=0)
    expect(state(m)['pending'] is None, 'no keys: no source')


def page_tests(ctx):
    """na_page_open takes the note when the album is in it; every other open has no order; the page closing releases it."""
    expect = ctx.expect
    m = machine(); d = albums(m, SPEC); note(m, d)
    p = state(m)['pending']['ptr']
    c(m, 'na_page_open', a0=KEYS[2])
    s = state(m)
    expect(s['pending'] is None and s['page'] and s['page']['ptr'] == p and s['page']['own'] == KEYS[2] and s['page']['keys'] == KEYS and s['page']['ref'] == 1, 'the note moves to the page with the album\'s own key')
    c(m, 'na_page_open', a0=KEYS[3])
    expect(state(m)['page'] is None and ('free', p) in m.calls, 'a later open with no note: the page has no order (the old one freed)')
    d = albums(m, SPEC); note(m, d)
    c(m, 'na_page_open', a0=0x1234)
    expect(state(m)['page'] is None and state(m)['pending'] is None, 'an album that is not in the note: not opened from that list, the note dropped')
    d = albums(m, SPEC); note(m, d); c(m, 'na_note_drop')
    c(m, 'na_page_open', a0=KEYS[0])
    expect(state(m)['page'] is None, 'a note the opener dropped (cc_open_album did not reach the page) is never taken later')
    d = albums(m, SPEC); note(m, d); c(m, 'na_page_open', a0=KEYS[0])
    pp = state(m)['page']['ptr']
    c(m, 'na_page_close')
    expect(state(m)['page'] is None and ('free', pp) in m.calls, 'the page closing frees its order')
    # a scoped source frees its artist copy with the last holder
    m = machine(); d = albums(m, SPEC); art = m.new_deque([m.record(album='', artist='Zed', path='/mnt/mmc/a.flac', rid=7)])
    note(m, d, scope=O['CLASS_ARTISTS'], artist=art); cp = state(m)['pending']['artist']
    c(m, 'na_page_open', a0=KEYS[0]); c(m, 'na_arm'); c(m, 'na_on_load'); c(m, 'na_page_close')
    expect(cp in m.deques and state(m)['active']['artist'] == cp, 'the page closing does not free what plays: the active source keeps its artist copy')
    c(m, 'na_on_load')
    expect(state(m)['active'] is None and cp not in m.deques, 'the next other load drops it: the copy is destroyed with the last holder')


def arm_tests(ctx):
    """Play arms the page's order around the load: the load keeps it, any other load drops it, a play that loads nothing leaves the old source."""
    expect = ctx.expect

    def page(m, specs=SPEC, at=0):
        d = albums(m, specs); note(m, d); c(m, 'na_page_open', a0=key(*specs[at]))
    m = machine(); page(m)
    expect(state(m)['active'] is None and not state(m)['armed'], 'nothing plays from it yet: no source')
    c(m, 'na_arm')
    s = state(m)
    expect(s['armed'] == 1 and s['active'] and s['active']['ptr'] == s['page']['ptr'] and s['active']['ref'] == 2 and s['active']['cur'] == KEYS[0], 'armed: the page\'s order is the active source, the album playing is the page\'s')
    c(m, 'na_on_load')
    s = state(m)
    expect(s['armed'] == 0 and s['active'] and s['active']['keys'] == KEYS, 'the armed load keeps the source')
    c(m, 'na_disarm')
    expect(state(m)['active'] and state(m)['armed'] == 0, 'disarm after the load changes nothing')
    c(m, 'na_on_load')
    expect(state(m)['active'] is None and state(m)['page'] and state(m)['page']['ref'] == 1, 'any other load (Songs, a playlist, a folder, DLNA...) drops the source; the page keeps its own')
    c(m, 'na_on_load')
    expect(state(m)['active'] is None, 'a load with no source is harmless')
    # a play that loaded nothing (a missing file): the old source is back
    c(m, 'na_arm'); c(m, 'na_on_load')
    old = state(m)['active']['ptr']
    d = albums(m, SPEC[2:]); note(m, d); c(m, 'na_page_open', a0=key(*SPEC[2]))
    c(m, 'na_arm')
    expect(state(m)['active']['ptr'] != old and state(m)['prev']['ptr'] == old, 'a second page armed: the new order is active, the old one held aside')
    c(m, 'na_disarm')
    s = state(m)
    expect(s['active']['ptr'] == old and s['prev'] is None and s['armed'] == 0, 'no load came: the old queue plays on with its old source')
    c(m, 'na_arm'); c(m, 'na_on_load')
    expect(state(m)['active']['keys'] == KEYS[2:] and state(m)['prev'] is None and ('free', old) in m.calls, 'a load that came: the new source stays and the old one is freed')
    # arm with a page that has no order (opened from elsewhere): armed, but no source; the old one is gone once the load arrives
    m = machine(); page(m); c(m, 'na_arm'); c(m, 'na_on_load')
    c(m, 'na_page_open', a0=KEYS[1])
    c(m, 'na_arm')
    expect(state(m)['active'] is None and state(m)['armed'] == 1, 'a page with no order arms nothing')
    c(m, 'na_on_load')
    expect(state(m)['active'] is None and state(m)['prev'] is None and ('free', state(m)['page'] and 0) not in m.calls, 'and its load leaves no source (the old order is not kept)')
    # Play again on the same page starts from the page's own album
    m = machine(); page(m, at=1); c(m, 'na_arm'); c(m, 'na_on_load')
    c(m, 'na_set_cur', a0=KEYS[3])
    expect(c(m, 'na_cur') == KEYS[3], 'phase 2 moves the album playing on')
    c(m, 'na_arm'); c(m, 'na_on_load')
    expect(c(m, 'na_cur') == KEYS[1], 'Play again on the page: it starts from the page\'s own album')
    c(m, 'na_on_load')
    expect(c(m, 'na_cur') == 0 and c(m, 'na_active') == 0, 'no source: no album playing')
    # the setting turned off drops the source
    m = machine(); page(m); c(m, 'na_arm'); c(m, 'na_on_load')
    expect(c(m, 'na_active') == 1, 'a source is held')
    c(m, 'na_set', a0=0)
    expect(c(m, 'na_active') == 0, 'set to Off: nothing continues')


def next_tests(ctx):
    """na_next_key: the key after the current one in the order shown; the last has none (no wrap); an album that is not in the list has none."""
    expect = ctx.expect
    m = machine(); d = albums(m, SPEC); note(m, d, order=[4, 3, 1, 0, 2]); c(m, 'na_page_open', a0=KEYS[1]); c(m, 'na_arm'); c(m, 'na_on_load')
    order = [KEYS[i] for i in (4, 3, 1, 0, 2)]
    out = m.alloc(8)
    for i in range(len(order) - 1):
        r = c(m, 'na_next_key', a0=order[i], a1=out)
        expect(r == 1 and m.word(out) == order[i + 1], f'after position {i}: position {i + 1}')
    expect(c(m, 'na_next_key', a0=order[-1], a1=out) == 0, 'the last album: none, no wrap to the first')
    expect(c(m, 'na_next_key', a0=0x1234, a1=out) == 0, 'an album that is not in the list: none')
    expect(c(m, 'na_next_key', a0=order[0], a1=0) == 0, 'no output pointer: none')
    c(m, 'na_on_load')
    expect(c(m, 'na_next_key', a0=order[0], a1=out) == 0, 'no source: none')
    # one album only
    m = machine(); d = albums(m, SPEC[:1]); note(m, d); c(m, 'na_page_open', a0=KEYS[0]); c(m, 'na_arm'); c(m, 'na_on_load')
    expect(c(m, 'na_next_key', a0=KEYS[0], a1=out) == 0, 'a list of one: none')
    # a pending note or a page order is not a source: only an armed load makes one
    m = machine(); d = albums(m, SPEC); note(m, d); c(m, 'na_page_open', a0=KEYS[0])
    expect(c(m, 'na_next_key', a0=KEYS[0], a1=out) == 0, 'an opened page that has not played is no source')


def row_tests(ctx):
    """Settings > Playback: the Continue Playing value row after EQ, its picker (Off, Next Albums, a check on the chosen one, the hint), the setting file in Settings Files, the
    action ids, the texts in 13 languages."""
    expect = ctx.expect
    P = pod_pages
    S, N = P.SETTINGS_PAGE, P.NEXTALBUM_PAGE
    labels = [r.label for r in S.rows]
    i = labels.index('Continue Playing')
    expect(labels[i - 1:i + 2] == ['EQ', 'Continue Playing', 'All Playback Settings'] and 'Play Next Album' not in labels,
           'the Playback card: EQ, Continue Playing, All Playback Settings')
    expect((P.ACT_NEXTALBUM, P.ACT_NASET) == (90, 91) and S.rows[i].action == 90 and S.rows[i].arg == P.NEXTALBUM_PAGE_INDEX == 66 and 90 in P.VALUE_ACTIONS and 90 not in P.SWITCH_ACTIONS
           and P.row_kind(S.rows[i]) == 'value' and P.VALUE_INIT[90] == 'Off', 'ACT_NEXTALBUM 90, a value row opening page 66; ACT_NASET 91')
    expect(P.PAGES[P.NEXTALBUM_PAGE_INDEX] is N and N.title == 'Continue Playing' and [(r.label, r.action, r.arg) for r in N.rows] == [('Off', 91, DEFS['NA_OFF']), ('Next Albums', 91, DEFS['NA_ALBUMS'])]
           and all(P.row_kind(r) == 'check' for r in N.rows) and 91 in P.CHECK_ACTIONS and N.layout[-1].text.startswith('Plays the next album'), 'the picker: Off, Next Albums, a check each, the hint under them')
    expect(P.SETTING_FILES.index('playback-next-album') == P.SETTING_FILES.index('playback-eq') + 1 and FILE == '/mnt/data/m1plus/playback-next-album', 'the setting file follows playback-eq in Settings Files')
    expect(len(P.SETTING_FILES) == 40 and P.INFO_SFOLD - P.INFO_SF == 45 and P.INFO_DUR == P.INFO_SFOLD + 1 == 61, 'Settings Files: 40 setting files (artists-rebuild too), INFO_SFOLD = INFO_SF + 45, INFO_DUR 61')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Continue Playing', 'Next Albums', 'Albums', 'Off', N.layout[-1].text)), f'the texts have a translation in {loc}')
    menu_i = next(k for k, r in enumerate(P.MENU.rows) if r.action == P.ACT_PAGE and r.arg == P.SETTINGS_PAGE_INDEX)

    def open_page(row_p, saved, names):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * k for k, n in enumerate(['btn_return', 'btn_backtoplayer'] + names)}
        if saved is not None: m.fs[FILE] = saved
        m.call(PSYMS['on_row'], a0=row_p, count=6000000)
        return m

    def open_settings(saved=None):
        return open_page(PSYMS['pod_rows_0'] + 12 * menu_i, saved, [f'pod_{k}{n}' for k in ('row', 'value', 'switch', 'label') for n in range(len(S.rows))])

    def open_picker(saved=None):
        m = Machine()
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.NEXTALBUM_PAGE_INDEX)
        m.widgets = {n: 0x30000000 + 0x100 * k for k, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_{k}{n}' for k in ('row', 'check', 'label') for n in range(2)])}
        if saved is not None: m.fs[FILE] = saved
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    def shown(m): return [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'pod_value{i}']]

    def checks(m):
        out = []
        for k in range(2):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{k}']]
            out.append(v[-1] if v else None)
        return out
    for saved, want in ((None, 'Off'), (b'1\n', 'Albums'), (b'0\n', 'Off'), (b'2\n', 'Off'), (b'', 'Off')):
        m = open_settings(saved)
        expect(('window_open', S.key) in m.calls and shown(m) == [want], f'saved {saved!r}: the Continue Playing row shows {shown(m)}')
    m = open_settings()
    m.click(f'pod_row{i}')
    expect(('window_open', N.key) in m.calls, 'a tap on the row opens the picker')
    for saved, want in ((None, [1, 0]), (b'1\n', [0, 1]), (b'0\n', [1, 0]), (b'2\n', [1, 0])):
        m = open_picker(saved)
        expect(('window_open', N.key) in m.calls and checks(m) == want and (saved is not None or FILE not in m.fs), f'saved {saved!r}: the picker\'s check {checks(m)}')
    m = open_picker()
    m.click('pod_row1')
    expect(m.fs.get(FILE) == b'1\n' and ('rename', TMP, FILE) in m.calls and checks(m) == [0, 1], 'a tap on Next Albums: saved atomically, the check follows')
    m.click('pod_row0')
    expect(m.fs.get(FILE) == b'0\n' and checks(m) == [1, 0], 'and Off again')
    m = open_picker(b'1\n'); m.fail.add(('write', TMP)); m.calls = []
    m.click('pod_row0')
    expect(m.fs.get(FILE) == b'1\n' and not any(c[0] == 'widget_set_visible' for c in m.calls), 'a failed save changes neither the file nor the check')


def load_tests(ctx):
    """Hook 14 (patch/shuffle.c sh_load_playlist) tells the module about every queue load: the armed load of an album page keeps the source, any other (Songs, a playlist, a
    folder, DLNA, the boot resume ...) drops it; the load itself is the shuffle module's, unchanged."""
    expect = ctx.expect
    SH = sibling('shuffle')

    def new_queue(m): return m.new_deque([SH.song(m, f'/mnt/mmc/n/{i:02d}.flac', 'N', i + 1) for i in range(8)])

    def playing(flag=False):
        m = SH.apple_machine(flag=flag); on(m)
        d = albums(m, SPEC); note(m, d); c(m, 'na_page_open', a0=KEYS[1])
        return m, new_queue(m)
    m, h = playing()
    c(m, 'na_arm')
    SH.load(m, h, 3)
    s = state(m)
    expect(s['active'] and s['active']['keys'] == KEYS and s['armed'] == 0 and s['prev'] is None, 'an armed load keeps the source and clears the armed flag')
    c(m, 'na_disarm')
    expect(state(m)['active'] is not None, 'and the disarm after it changes nothing')
    h2 = new_queue(m)
    SH.load(m, h2, 0)
    expect(state(m)['active'] is None and state(m)['armed'] == 0, 'the next load (nothing armed: a Songs row, a playlist, a folder, DLNA, the boot resume) drops it')
    SH.load(m, h2, 0)
    expect(state(m)['active'] is None, 'a load with no source is harmless')
    # with Shuffle on the load shuffles as before, and the source is kept all the same
    m, h = playing(flag=True)
    c(m, 'na_arm'); before = sorted(SH.order(m))
    SH.load(m, h, 3)
    expect(SH.flag_on(m) and state(m)['active'] and state(m)['active']['keys'] == KEYS and len(SH.order(m)) == 8 and SH.order(m) != before, 'Shuffle on: the loaded queue is shuffled by the hook as before and the source stays')
    # the order of the calls: the module is told first, the stock load happens under the shuffle module's own lock as before
    m, h = playing()
    c(m, 'na_arm'); m.watch[PSYMS['na_on_load']] = 'na_on_load'; m.calls = []
    SH.load(m, h, 1)
    names = [x[0] for x in m.calls]
    expect(names and names[0] == 'na_on_load', f'sh_load_playlist calls na_on_load before anything else ({names[:3]})')


# ======================= Phase 2: the end of the queue (hook 26) =======================
UP = sibling('upnext')
SHM = sibling('shuffle')
POSW, MODEW, CLSW, SOCKW, GAPW, PREW = 0xa0abdc, 0xa0abe0, 0xa0abd8, 0xa0abec, pod.DATA['MCL_GAPLESS'][0], pod.DATA['MCL_PRELOAD'][0]   # mclNextSong's words: position, raw mode, class, hciplayer socket, Gapless byte, preload state
NEXT_SONG = 0x5d5800
ALBUM_CLS = O['CLASS_ALBUM_TRACKS']
ORDERSTOP = '{mcl-orderstop\\null}'
SHOWLIST, CLASSINFO = pod.DATA['PDEQ_SHOWLIST'][0], pod.DATA['CLASSINFO'][0]
ALBUM_GETTERS = ('getAlbumByAlbumArtist', 'getAlbumByArtist', 'getAlbumByComposer')
TRACK_GETTERS = ('getMusicByAlbum', 'getMusicByAlbumAndAlbumSonger', 'getMusicByAlbumAndSonger', 'getMusicByAlbumAndComposer')


class EM(UP.UM):
    """The Up Next machine plus what mclNextSong calls (mclStop, the hciplayer send, mclStartPlayer behind its hook's trampoline) and the album page's own stock getters, which leave
    their rows in *tools_pdeq_directory exactly as stock's do (lists: (getter, who) -> album rows, tracks: (getter, album, who) -> track rows in the page's order)."""

    def __init__(self):
        super().__init__()
        self.handlers[PSYMS['stock_start_player_trampoline']] = 'stock_start_player'
        for off, nm, at in ((0xce4, 'deque_size', 0x743600), (0xa8c, 'deque_at', 0x743604), (0x9bc, 'send', 0x743608)):   # mclNextSong's GOT slots of the libcstl / libc calls (the image holds lazy stubs): bound to trapped addresses
            self.setword(pod.GP - off, at); self.handlers[at] = nm
        self.lists, self.tracks, self.getcalls, self.bad = {}, {}, [], set()
        self.shown = {}   # the list pointers a test compares before and after

    def put_tmp(self, rows):
        tmp = pod.DATA['PDEQ_TOOLS_TMP'][0]
        if not self.word(tmp): self.setword(tmp, self.new_deque())
        self.deques[self.word(tmp)] = list(rows)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('mclStop', 'send', 'stock_start_player') + ALBUM_GETTERS + TRACK_GETTERS: return super()._hook(u, address, size, _)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        ret = 0
        if name == 'mclStop': self.calls.append(('mclStop',))
        elif name == 'send': self.calls.append(('send', self.read_cstr(a1)))
        elif name == 'stock_start_player':
            q = self.deques[self.word(pod.DATA['PLAY_QUEUE'][0])]; pos = self.word(POSW)
            self.calls.append(('mclStartPlayer', pos, self.read_cstr(self.word(q[pos] + O['REC_PATH']))))
            ret = 1
        elif name in ALBUM_GETTERS:
            who = self.read_cstr(a0) if a0 else None
            self.getcalls.append((name, who)); self.calls.append(('getter', name)); rows = self.lists.get((name, who))
            self.put_tmp(rows if rows is not None and name not in self.bad else []); ret = len(rows) if rows is not None and name not in self.bad else -1
        else:
            alb, who = self.read_cstr(a0), self.read_cstr(a1) if a1 and name != 'getMusicByAlbum' else None
            self.getcalls.append((name, alb, who, a2 if name != 'getMusicByAlbum' else 0)); self.calls.append(('getter', name)); rows = self.tracks.get((name, alb, who))
            self.put_tmp(rows if rows is not None and name not in self.bad else []); ret = len(rows) if rows is not None and name not in self.bad else -1
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def tracks_of(m, album, n=3):
    """The rows a track getter leaves for an album, in the page's order."""
    return [SHM.song(m, f'/mnt/mmc/{album}/{k + 1}.flac', album, k + 1, 1) for k in range(n)]


def world(spec=SPEC, n=3, start=0, scope=0, artist_type=0, order=None, setting=True, mode=0, gapless=1, sock=5, boot=True):
    """The player on the last track of spec[start] (n tracks, class 0xff10) with the album page's order as the source: the library's (scope 0), an artist's (CLASS_ARTISTS) or a
    composer's (CLASS_COMPOSERS) albums. order: the shown order as row numbers. Returns (machine, the albums deque, the shown keys)."""
    m = EM()
    if setting: on(m)
    rows = [m.record(album=a, artist=r, path=f'/mnt/mmc/m/{i}.flac', rid=i + 1) for i, (a, r) in enumerate(spec)]
    d = m.new_deque(rows)
    art = 0
    if scope:
        artist = m.record(album='', artist='Zed', path='/mnt/mmc/a.flac', rid=7)
        m.setword(artist + O['REC_TITLE'], m.cstr('Zed')); m.setword(artist + 0x24, m.cstr('Zed AA')); m.setword(artist + 0x20, m.cstr('Zed Comp'))
        art = m.new_deque([artist])
        who = {CLASSES['composer']: 'Zed Comp'}.get(scope, 'Zed AA' if artist_type == 1 else 'Zed')
        get = {CLASSES['composer']: 'getAlbumByComposer'}.get(scope, 'getAlbumByAlbumArtist' if artist_type == 1 else 'getAlbumByArtist')
        trk = {CLASSES['composer']: 'getMusicByAlbumAndComposer'}.get(scope, 'getMusicByAlbumAndAlbumSonger' if artist_type == 1 else 'getMusicByAlbumAndSonger')
        m.lists[(get, who)] = rows + [m.all_songs('Zed')]
    else:
        who, trk = None, 'getMusicByAlbum'
        m.class_lists[O['CLASS_ALBUMS']] = rows
    for a, _ in spec:
        m.tracks[(trk, a, who)] = tracks_of(m, a)
        m.present.update(m.read_cstr(m.word(r + O['REC_PATH'])) for r in m.tracks[(trk, a, who)])
    m.setword(pod.DATA['ARTIST_TYPE'][0], artist_type)
    shown = list(range(len(spec))) if order is None else order
    note(m, d, order=order, scope=scope, artist=art)
    c(m, 'na_page_open', a0=KEYS[start]); c(m, 'na_arm'); c(m, 'na_on_load')
    play(m, start, n, mode, gapless, sock)
    m.shown_getter = (trk, who)
    return m, d, [KEYS[i] for i in shown]


CLASSES = {'artist': O['CLASS_ARTISTS'], 'composer': O['CLASS_COMPOSERS']}


def play(m, album, n=3, mode=0, gapless=1, sock=5):
    """The queue holds spec[album]'s n tracks (copies of the page's rows, stamped 0xff10), the last one playing."""
    rows = []
    for r in tracks_of(m, SPEC[album][0], n):
        cp = m.alloc(REC_SIZE); m.u.mem_write(cp, bytes(m.u.mem_read(r, REC_SIZE))); m.setword(cp + O['REC_CLASS'], ALBUM_CLS); rows.append(cp)
    m.present.update(m.read_cstr(m.word(r + O['REC_PATH'])) for r in rows)
    m.play(rows, n - 1)
    m.setword(POSW, n - 1); m.setword(MODEW, mode); m.setword(CLSW, ALBUM_CLS); m.setword(SOCKW, sock); m.mode = mode
    m.u.mem_write(GAPW, bytes([gapless])); m.setword(PREW, 0)


def queue(m): return [m.read_cstr(m.word(r + O['REC_PATH'])) for r in m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])]]


def advance(m, auto=1):
    """Stock's mclNextSong(auto), its words executed through hook 26; the calls that matter (mclStop, send, mclStartPlayer), in order."""
    m.calls = []; m.getcalls = []
    m.call(NEXT_SONG, a0=auto, count=60000000)
    return [x for x in m.calls if x[0] in ('mclStop', 'send', 'mclStartPlayer')]


def stock_end(auto, mode=0):
    """What stock does at the end of a 3 song queue with nothing hooked in: the machine with no source."""
    m, d, ks = world(setting=False, mode=mode)
    return advance(m, auto), queue(m), m.word(POSW)


def snap_q(m):
    q = queue(m)
    return len(q), q[:3], q[-3:]


def untouched(m):
    return (m.word(SHOWLIST), bytes(m.u.mem_read(CLASSINFO, O['CLASSINFO_SIZE'])))


def end_tests(ctx):
    """The library source: the automatic end and a manual Next on the last song both play the next album's first track; the queue gets its tracks after the playing one."""
    expect = ctx.expect
    for auto in (1, 0):
        m, d, ks = world()
        m.setword(SHOWLIST, m.new_deque([m.record(album='Page', path='/mnt/mmc/x.flac')])); m.u.mem_write(CLASSINFO, b'page-state' + bytes(O['CLASSINFO_SIZE'] - 10))
        before = untouched(m); shown = list(m.deques[m.word(SHOWLIST)])
        got = advance(m, auto)
        beta = [f'/mnt/mmc/Beta/{k}.flac' for k in (1, 2, 3)]
        expect(got == [('mclStartPlayer', 3, beta[0])], f'{"automatic end" if auto else "manual Next on the last song"}: the next album\'s first track plays, no stop, no orderstop ({got})')
        expect(queue(m) == [f'/mnt/mmc/Alpha/{k}.flac' for k in (1, 2, 3)] + beta and m.word(POSW) == 3, f'the queue is the playing album plus the next one in the page\'s track order, position 3 ({queue(m)})')
        q = m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])]
        expect(all(m.word(r + O['REC_CLASS']) == ALBUM_CLS for r in q), 'every row has the playing album\'s class (stamped from the playing row)')
        expect(untouched(m) == before and m.deques[m.word(SHOWLIST)] == shown, 'the show list and the browsing record are not touched')
        expect(not any(x[0] in ('loadLocalClassList', 'loadAlbumList', 'loadAlbumdetailList') for x in m.calls), 'none of the page-state loaders is called')
        expect(m.getcalls == [('getMusicByAlbum', 'Beta', None, 0)] and ('toolsQueryDbTable', '/mnt/data/database.db', pod.ALBUM_SQL, 0x4e93c8, 0) in m.calls, f'one album list query, then the album page\'s own track getter ({m.getcalls})')
        expect(c(m, 'na_cur') == KS(1) and not m.deques.get(m.word(pod.DATA['PDEQ_TOOLS_TMP'][0])), 'the album playing is now Beta, the query scratch deque is cleared')
    # the order of the page is followed (Z-A), not the library's
    m, d, ks = world(order=[4, 3, 2, 1, 0], start=4)
    got = advance(m)
    expect(got == [('mclStartPlayer', 3, '/mnt/mmc/Delta/1.flac')] and c(m, 'na_cur') == KEYS[3], f'a reversed page: Epsilon is followed by Delta ({got})')


def KS(i): return KEYS[i]


def chain_tests(ctx):
    """A, then B, then C: each end appends the next; the last album of the page ends as stock does; Previous goes back through the albums."""
    expect = ctx.expect
    m, d, ks = world(spec=SPEC[:3], n=2)
    for i, (album, at) in enumerate((('Beta', 2), ('Gamma', 5)), start=1):
        got = advance(m)
        expect(got == [('mclStartPlayer', at, f'/mnt/mmc/{album}/1.flac')], f'end {i}: {album} follows ({got})')
        expect(c(m, 'na_cur') == KEYS[i], f'{album} is the album playing')
        m.setword(POSW, len(queue(m)) - 1); m.play_pos = len(queue(m)) - 1   # the last track of the new album plays
    expect(len(queue(m)) == 8 and queue(m)[-3:] == [f'/mnt/mmc/Gamma/{k}.flac' for k in (1, 2, 3)], f'three albums in the queue ({queue(m)})')
    got = advance(m)
    stock, q, pos = stock_end(1)
    expect(got == [('mclStop',), ('send', ORDERSTOP)] and got == stock and c(m, 'na_cur') == KEYS[2] and len(queue(m)) == 8, f'the last album of the page: stock\'s end, {{mcl-orderstop}} ({got})')
    got = advance(m, 0)
    expect(got == [('mclStop',), ('mclStartPlayer', 7, '/mnt/mmc/Gamma/3.flac')] and len(queue(m)) == 8, f'a manual Next on the last album\'s last song: stock restarts it ({got})')
    # not at the end of a chain: the ordinary pos + 1 never reaches the hook
    m, d, ks = world(spec=SPEC[:3], n=2); m.setword(POSW, 0); m.play_pos = 0
    got = advance(m)
    expect(got == [('mclStartPlayer', 1, '/mnt/mmc/Alpha/2.flac')] and not m.getcalls and not any(x[0] == 'toolsQueryDbTable' for x in m.calls), 'a song that is not the last: the next track plays, no query, no append')
    # a source of one album, and the playing album that is not in the order
    m, d, ks = world(spec=SPEC[:1]); got = advance(m)
    expect(got == [('mclStop',), ('send', ORDERSTOP)] and not m.getcalls, 'a page of one album: stock\'s end')
    m, d, ks = world(spec=SPEC[:3], n=2); c(m, 'na_set_cur', a0=0x1234)
    got = advance(m)
    expect(got == [('mclStop',), ('send', ORDERSTOP)] and not m.getcalls, 'an album that is not in the order: stock\'s end')


def scoped_tests(ctx):
    """An artist's or a composer's albums page: the stock list and track getters of the browsing record's fields, never the class loaders."""
    expect = ctx.expect
    for artist_type in (0, 1):
        m, d, ks = world(scope=CLASSES['artist'], artist_type=artist_type)
        before = untouched(m)
        got = advance(m)
        trk = 'getMusicByAlbumAndAlbumSonger' if artist_type else 'getMusicByAlbumAndSonger'
        who = 'Zed AA' if artist_type else 'Zed'
        expect(got == [('mclStartPlayer', 3, '/mnt/mmc/Beta/1.flac')], f'artist (album-artist switch {artist_type}): Beta plays ({got})')
        expect(m.getcalls == [('getAlbumByAlbumArtist' if artist_type else 'getAlbumByArtist', who), (trk, 'Beta', who, 0)] or m.getcalls[-1:] == [(trk, 'Beta', who, 0)], f'the artist\'s albums getter, then {trk}({who}) ({m.getcalls})')
        expect(untouched(m) == before and c(m, 'na_cur') == KEYS[1], 'browsing record untouched, Beta is playing')
    m, d, ks = world(scope=CLASSES['composer'])
    got = advance(m)
    expect(got == [('mclStartPlayer', 3, '/mnt/mmc/Beta/1.flac')] and m.getcalls[-1] == ('getMusicByAlbumAndComposer', 'Beta', 'Zed Comp', 0), f'composer: getAlbumByComposer, getMusicByAlbumAndComposer ({m.getcalls})')
    # the Unknown Artist row passes no name (stock's flag at +0xa)
    m, d, ks = world(scope=CLASSES['artist'])
    ar = m.deques[[k for k, v in m.deques.items() if v and m.word(v[0] + O['REC_ID']) == 7][0]][0]
    m.setword(ar + O['REC_ID'], 0xffffffff)
    for k in list(m.lists): m.lists[(k[0], None)] = m.lists.pop(k)
    for k in list(m.tracks): m.tracks[(k[0], k[1], None)] = m.tracks.pop(k)
    got = advance(m)
    expect(got == [('mclStartPlayer', 3, '/mnt/mmc/Beta/1.flac')] and m.getcalls[-1][2] is None, f'the Unknown Artist row: the getters get no name ({m.getcalls})')
    # the All Songs card and a missing album in the artist's list
    m, d, ks = world(scope=CLASSES['artist']); m.lists[('getAlbumByArtist', 'Zed')] = [m.all_songs('Zed')]
    expect(advance(m) == [('mclStop',), ('send', ORDERSTOP)], 'the artist\'s list no longer holds the next album: stock\'s end')


def refusal_tests(ctx):
    """Every condition that is not met, and every failure, gives exactly stock's end: same calls, same queue, same position; nothing asked of the database where it need not be."""
    expect = ctx.expect

    def case(label, prep, auto=1, mode=0, asked=False, **kw):
        m, d, ks = world(mode=mode, **kw)
        prep(m)
        before = untouched(m)
        got = advance(m, auto)
        b, _, _ = world(mode=mode, **dict(kw, setting=False)); prep(b)
        want = advance(b, auto)
        expect(got == want and snap_q(m) == snap_q(b) and m.word(POSW) == b.word(POSW), f'{label}: stock\'s end ({got} vs {want})')
        expect(untouched(m) == before, f'{label}: show list and browsing record untouched')
        expect(asked or not (m.getcalls or any(x[0] == 'toolsQueryDbTable' for x in m.calls)), f'{label}: the database is not asked')
        expect(not m.deques.get(m.word(pod.DATA['PDEQ_TOOLS_TMP'][0])), f'{label}: nothing left in the scratch deque')
        return m
    nothing = lambda m: None
    for auto in (1, 0):
        case(f'setting off (auto {auto})', nothing, auto, setting=False)
        case(f'kill switch (auto {auto})', lambda m: m.present.add(KILL), auto)
        case(f'no source (auto {auto})', lambda m: c(m, 'na_on_load'), auto)
        case(f'Shuffle on (auto {auto})', lambda m: m.fs.__setitem__(SHM.FLAG_FILE, b'1\n'), auto)
        case(f'DLNA running (auto {auto})', lambda m: m.setword(pod.DATA['DMR_SERVERFLAG'][0], 1), auto)
        case(f'a query failure (auto {auto})', lambda m: m.__dict__.update(album_query_fails=True), auto, asked=True)
        case(f'the track getter fails (auto {auto})', lambda m: m.bad.add('getMusicByAlbum'), auto, asked=True)
        case(f'the album is gone from the list (auto {auto})', lambda m: m.class_lists.__setitem__(O['CLASS_ALBUMS'], m.class_lists[O['CLASS_ALBUMS']][:1]), auto, asked=True)
        case(f'the album has no tracks (auto {auto})', lambda m: m.tracks.__setitem__(('getMusicByAlbum', 'Beta', None), []), auto, asked=True)
        case(f'a track file is missing (auto {auto})', lambda m: m.present.discard('/mnt/mmc/Beta/2.flac'), auto, asked=True)
        case(f'a Radio station runs (auto {auto})', lambda m: setattr(m, 'radio', 1), auto, asked=True)
        case(f'a stream play type (auto {auto})', lambda m: setattr(m, 'ptype', 2), auto, asked=True)
        case(f'the queue would pass the cap (auto {auto})', lambda m: UP_full(m), auto, asked=True)
        case(f'the position is not the last (auto {auto})', lambda m: m.__dict__.update(play_pos=1), auto)
    # repeat modes never reach the hook at all (raw mode 1 and 3 branch before the end test)
    for mode in (1, 3):
        m, d, ks = world(mode=mode)
        got = advance(m)
        want, q, pos = stock_end(1, mode)
        expect(got == want and queue(m) == q and not m.getcalls and not any(x[0] == 'toolsQueryDbTable' for x in m.calls), f'repeat mode {mode}: stock\'s own handling, the hook is not reached ({got})')
    # na_end itself refuses a repeat mode too (a call straight into the hook)
    for mode in (1, 3):
        m, d, ks = world(mode=mode)
        expect(c(m, 'na_end') == 0 and not m.getcalls and not any(x[0] == 'toolsQueryDbTable' for x in m.calls), f'na_end with the repeat mode {mode}: refused without a query')
    # DLNA's own thread calls mclNextSong too: na_end refuses before doing any work (no allocation, no query, no lock)
    m, d, ks = world(); m.setword(pod.DATA['DMR_SERVERFLAG'][0], 1); m.calls = []
    expect(c(m, 'na_end') == 0, 'DLNA: na_end answers 0')
    expect(not any(x[0] in ('lock', 'calloc', 'malloc', 'toolsQueryDbTable', 'getter') for x in m.calls), 'DLNA: before any work: no lock, no allocation, no query')
    # nothing is held across the insert: the payload mutex is balanced and na_end holds none of its own
    m, d, ks = world(); advance(m)
    names = m.names()
    lk, ul = names.index('lock'), names.index('unlock')
    expect(names.count('lock') == names.count('unlock') == 1 and lk < ul and lk > max(i for i, n in enumerate(names) if n in ('getter', 'toolsQueryDbTable')) and not [n for n in names[lk:ul] if n in ('getter', 'toolsQueryDbTable', 'mclStop', 'access')],
           f'the payload lock is taken once, by the insert, after the queries and released before the player starts ({names})')


def UP_full(m):
    """A queue so long that the added tracks pass SHUFFLE_MAX: one shared record, the last one playing."""
    r = m.deques[m.word(pod.DATA['PLAY_QUEUE'][0])][-1]
    m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque([r] * (O['SHUFFLE_MAX'] - 1)))
    m.setword(POSW, O['SHUFFLE_MAX'] - 2); m.play_pos = O['SHUFFLE_MAX'] - 2


def gapless_tests(ctx):
    """Gapless on and off, with the preload closed (the usual state at the last song) or cancelled: the appended album starts the same way."""
    expect = ctx.expect
    for gapless in (1, 0):
        for pre in (0, 0xffffffff):
            m, d, ks = world(gapless=gapless); m.setword(PREW, pre)
            got = advance(m)
            expect(got == [('mclStartPlayer', 3, '/mnt/mmc/Beta/1.flac')] and not any(x[0] in ('closegapless', 'mclSetGaplessMode') for x in m.calls), f'Gapless {gapless}, preload state {pre:#x}: Beta plays, a preload that is not open is not touched ({got})')


def pin_tests(ctx):
    """The hook's words: stock's in the stock demo, only the two site words changed in the build, the stub as designed, the manifest, and a changed word differs from its pin."""
    expect = ctx.expect
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site = pod.NEXTALBUM_SITE
    expect(site == 0x5d5988 and pod.NEXTALBUM_AGAIN == 0x5d5950 and pod.NEXTALBUM_RESUME == 0x5d5990, 'the site is 0x5d5988, the end test 0x5d5950, the resume 0x5d5990')
    expect(all(w(stock_demo, a) == old and (a in (site, site + 4) or w(built, a) == old) for a, old, _ in pod.NEXTALBUM_PINS), f'all {len(pod.NEXTALBUM_PINS)} pinned words are stock\'s in the stock demo and unchanged in the build (but the two edited)')
    expect((w(stock_demo, site), w(stock_demo, site + 4)) == pod.NEXTALBUM_DISPLACED and w(built, site) == pod.j(PSYMS['pod_na_site']) and w(built, site + 4) == 0, 'the two words became `j pod_na_site; nop`')
    expect(w(built, site + 8) == w(stock_demo, site + 8) and w(built, site - 4) == w(stock_demo, site - 4), 'their neighbours are stock\'s')
    stub = PSYMS['pod_na_site']
    words = [w(built, stub + 4 * i) for i in range(13)]
    expect(words[:2] == [pod.jal(PSYMS['na_end'], stub), 0] and words[2] >> 16 == 0x3c1c and words[4] >> 26 == 5 and words[8] == pod.j(0x5d5990) and words[10] == pod.j(0x5d5950), 'the stub: jal na_end, $gp set, bnez to `j 0x5d5950`, else the displaced words and `j 0x5d5990`')
    expect(words[6:8] == list(pod.NEXTALBUM_DISPLACED), 'the stub re-executes the displaced words')
    expect(MANIFEST['hook_next_album'] == {'addr': site, 'target': stub}, 'the manifest lists the hook')
    pins = {a: old for a, old, _ in pod.NEXTALBUM_PINS}
    for a in (0x5d5950, 0x5d5974, 0x5d5984, 0x5d5994, 0x5d59d8, 0x4ee83c, 0x4ee874, 0x4ecb5c, 0x4ed008):
        img = bytearray(stock_demo); struct.pack_into('<I', img, pod.fileoff(img, a), w(stock_demo, a) ^ 0x100)
        expect(a in pins and struct.unpack_from('<I', img, pod.fileoff(img, a))[0] != pins[a], f'a changed word at {a:#x} differs from its pin, which pod.py checks before writing')
    expect({0x5d5950, 0x5d5974, 0x5d5984, 0x5d5990, 0x5d5920, 0x5d59d4, 0x5d5910} <= set(pins), 'the end test, the mode branch, pos + 1 and the fallback are all pinned')
    expect(set(n for n in ('getAlbumByAlbumArtist', 'getAlbumByArtist', 'getAlbumByComposer', 'getMusicByAlbum', 'getMusicByAlbumAndAlbumSonger', 'getMusicByAlbumAndSonger', 'getMusicByAlbumAndComposer') if pod.FUNCTIONS[n][2] in pins) ==
           {'getAlbumByAlbumArtist', 'getAlbumByArtist', 'getAlbumByComposer', 'getMusicByAlbum', 'getMusicByAlbumAndAlbumSonger', 'getMusicByAlbumAndSonger', 'getMusicByAlbumAndComposer'}, 'every stock getter na_end calls has its prologue pinned')


SECTIONS = [setting_tests, row_tests, note_tests, page_tests, arm_tests, next_tests, load_tests, end_tests, chain_tests, scoped_tests, refusal_tests, gapless_tests, pin_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

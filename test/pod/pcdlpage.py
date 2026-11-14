"""The Podcasts Downloads page (patch/podcasts.c, docs/modules/podcasts.md "The Downloaded page"): the storage line, the two sections (In Progress: what the worker holds, the failed and the paused; Downloaded: every episode
file of every show, the newest download first, sliced scan, capped), the rows' grey lines and played check, the taps (an In Progress row pauses, resumes or retries; a Downloaded row opens the episode's page and Back
returns to the same place), the "..." sheet (Select, Delete Played Episodes), select mode and its Delete across both sections, Delete Played with the playing episode protected and its toast, the empty state, the
screen-off rule and the strings in 13 languages measured in the real font. The compiled payload runs under Unicorn; the card is a dict of paths."""
import os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))


PCS, SEL, DL = sibling('pcshows'), sibling('pcsel'), sibling('pcdl')
import mod_icons, pod_i18n, pod_show, pod_ui   # noqa: E402
PCP, PCN = PCS.PCP, PCS.PCN
RP, NOW, DAY, PN = PCS.RP, PCS.NOW, PCS.DAY, PCS.PN
ROW, TY, SY = O['PC_ROW_H'], O['LIST_TITLE_Y'], O['LIST_SUB_Y']
SG_MARK = O['SG_MARK']
A1, A2 = f'{RP}/Alpha Show/ep1.mp3', f'{RP}/Alpha Show/ep2.mp3'
B1, B2, B3 = (f'{RP}/bravo/b{i}.mp3' for i in (1, 2, 3))
SA, SB = f'{RP}/Sub One/a.mp3', f'{RP}/Sub One/b.mp3'
MT = {SA: NOW - 3600, B3: NOW - 2 * DAY, A1: NOW - 3 * DAY, B1: NOW - 4 * DAY, A2: NOW - 10 * DAY, B2: NOW - 20 * DAY, SB: NOW - 40 * DAY}   # the files' dates (when they were downloaded)
SIZE = {SA: 48 << 20, B3: 7 << 20, A1: 100 << 20, B1: 5 << 20, A2: 50 << 20, B2: 6 << 20, SB: 1 << 20}
ORDER = [SA, B3, A1, B1, A2, B2, SB]
TITLES = ['Ep A', 'Bravo 3', 'ep1', 'Bravo 1', 'ep2', 'Bravo 2', 'Ep B']
GREY = ['Sub One · 1h ago · 48 MB', 'bravo · Nov 17, 2023 · 7 MB', 'Alpha Show · 3d ago · 100 MB', 'bravo · Nov 15, 2023 · 5 MB', 'Alpha Show · Jan 5 · 50 MB', 'bravo · Nov 16, 2023 · 6 MB', 'Sub One · 1h ago · 1 MB']


def card(m):
    """Alpha Show (ep1, ep2 on the card, a feed), bravo (three files, no feed), Sub One (a, b on the card, c to f not, d half downloaded), Sub Two (a feed, nothing): seven episodes on the card with dates and sizes."""
    SEL.card(m)
    for p, t in MT.items(): m.mtime[p] = t
    m.sizes.update(SIZE)
    m.free_mb = 18 * 1024


_ATLAS = []


def atlas():
    """The committed pc_atlas as the page's image loader gives it (the download ring's cells are cut from it)."""
    if not _ATLAS:
        from PIL import Image
        im = Image.open(os.path.join(mod_icons.PNG, 'pc_atlas.png')).convert('RGBA')
        _ATLAS.append((im.width, im.height, im.tobytes()))
    return _ATLAS[0]


def marks_images(mm): mm.images.update({'pc_atlas': atlas(),'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)})


def page(extra=None, cardf=card):
    """The Shows page's machine (real font widths) on this card, opened."""
    m = PCS.opened(lambda mm: (marks_images(mm), extra(mm) if extra else None), cardf)
    m.curl_site = DL.server(DL.DATA)
    m.confirm_yes = True
    return m


def flags(m, n): return PCS.flags(m, n)
def toasts_fixed(m): return [PCS.fixed(c[1]) for c in m.calls if c[0] == 'toast']
def confirms(m): return [c[1] for c in m.calls if c[0] == 'confirm']
def unlinks(m): return [c[1].replace(RP + '/', '') for c in m.calls if c[0] == 'unlink']
def title(m): return PCP.title_text(m)
def settle(m, n=80): PCS.settle(m, n)


def to_page(m, done=True):
    """The Shows page's Downloads row; the loader's ticks (the covers, then one show a tick) when done."""
    PCS.tap_row(m, 'Downloaded')
    if done: settle(m)


def rows(m):
    """{row top: [title, grey line]} of every row, from frames scrolled 100 px apart (a text is drawn only wholly inside the view)."""
    out = {}
    for off in range(0, max(m.props.get((m.sv, 'virtual_h'), 0) - 300, 100), 100):
        _, texts, styles, _ = PCP.paint(m, off)
        for (t, r), s in zip(texts, styles):
            if s == 'label_row_title': out.setdefault(r[1] + off - TY, [None, None])[0] = PCS.fixed(t)
            elif s == 'label_row_sub': out.setdefault(r[1] + off - SY, [None, None])[1] = PCS.fixed(t)
    return [tuple(v) for _, v in sorted(out.items())]


def tops(m): return sorted(rows_y(m))


def rows_y(m):
    out = set()
    for off in range(0, max(m.props.get((m.sv, 'virtual_h'), 0) - 300, 100), 100):
        out |= {r[1] + off - TY for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == 'label_row_title'}
    return out


def texts_at(m, style, off=0): return [(PCS.fixed(t), r) for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == style]


def tap_row(m, i, n_ip, n_dl, **kw):
    """A tap on display row i of the page (the model's top for it)."""
    y = pod_show.downloads_layout(n_ip, n_dl)['rows'][i]
    off = max(0, y - 150)
    PCP.tap(m, 150, y + 20, off=off, **kw)


def lay(n_ip, n_dl, select=False): return pod_show.downloads_layout(n_ip, n_dl, select)


def page_tests(ctx):
    """The page from the Downloads row: the title, the storage line, the Downloaded section's rows (the newest download first, each with its show, date and size), the section header and every row's place."""
    expect = ctx.expect
    m = page()
    PCS.tap_row(m, 'Downloaded')
    expect(title(m) == 'Downloaded' and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1 and flags(m, 'btn_more') == (0, 0), f'a tap on the Downloads row: the page opens ({title(m)}), the scan has not run yet: nothing listed, no "..."')
    expect(texts_at(m, 'label_ps_meta')[0][0] == '18 GB free', f'the storage line says the free space until the scan has counted ({texts_at(m, "label_ps_meta")})')
    settle(m)
    got = rows(m)
    expect(got[0] == ('Ep D', 'Paused'), f'In Progress: the paused .part the card has ({got[:1]})')
    got = got[1:]
    expect([t for t, _ in got] == TITLES and [g for _, g in got] == GREY, f'Downloaded: the seven files, the newest download first (file date), "show · date · size" ({got})')
    L = lay(1, 7)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and sorted(rows_y(m)) == L['rows'], f'the content and every row\'s top are the model\'s ({m.props.get((m.sv, "virtual_h"))} against {L["h"]})')
    heads = [(t, r) for t, r in texts_at(m, 'label_ps_sech')]
    expect(heads == [('In Progress', (O['PP_SHOWS_X'], L['y_ip'], 320 - 2 * O['PP_SHOWS_X'], O['PP_HEAD_H']))] and L['rows'][1] == L['rows'][0] + ROW + O['PP_SEC_GAP'], f'the In Progress header at the model\'s place and no Downloaded header: the downloaded rows follow PP_SEC_GAP under the In Progress row ({heads}, {L["rows"][:2]})')
    line = texts_at(m, 'label_ps_meta')
    expect(line == [('7 episodes · 217 MB · 18 GB free', (O['PP_LINE_X'], O['PDL_LINE_Y'], 320 - 2 * O['PP_LINE_X'], O['PP_LINE_H']))], f'the storage line: the count, their size and the free space ({line})')
    expect(flags(m, 'btn_more') == (1, 1) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play', 'the "..." is there once there are rows (the capsule: "..." | Now Playing)')
    bl, *_ = PCP.paint(m, 0)
    covers = [b for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]
    expect(len(covers) == sum(1 for y in L['rows'] if y + O['LIST_ART_Y'] + O['LIST_ART'] <= 400) and all(b[2][0] == O['LIST_ART_X'] for b in covers), f'a 52 px cover at x 10 on each row in view (the show\'s) ({len(covers)})')
    # a played episode has the check before its grey line; one half played says what is left instead of the date
    m = page()
    m.call(PSYMS['pc_mark'], a0=PCP.pc_hash(SA), a1=1, count=2000000)
    PCS.progress(m, B3, 600, 3600)
    to_page(m)
    got = dict(zip(ORDER, rows(m)[1:]))
    expect(got[SA][1] == 'Sub One · 1h ago · 48 MB' and got[B3][1] == 'bravo · 50m left · 7 MB', f'a place of 10 min in a 60 min episode: "50m left" for the date ({got[B3]})')
    bl, *_ = PCP.paint(m, 0)
    checks = [tuple(b[2]) for b in bl if tuple(b[1]) == (O['PA_CHECK'] * O['PA_G_PX'], O['PA_G_Y'], O['PA_G_PX'], O['PA_G_PX'])]
    expect(checks == [(O['LIST_TEXT_X'] - 1, L['rows'][1] + SY + O['LIST_SUB_H'] // 2 - 8, 16, 16)], f'the played one (the newest) has the check before its grey line ({checks})')
    subs_x = [r[0] for t, r in texts_at(m, 'label_row_sub')]
    expect(subs_x[1] == O['LIST_TEXT_X'] + O['PS_BADGE_CHECK_W'] and set(subs_x[:1] + subs_x[2:]) == {O['LIST_TEXT_X']}, f'its grey line starts after the check; the others do not ({subs_x})')


def big_card(m):
    """40 shows of 300 episode files each (.episodes with titles and dates), the files' dates interleaved so that the newest 300 of the whole card are seven or eight of each show."""
    m.free_mb = 18 * 1024
    m.images['p_default'] = (16, 16, bytes((90, 90, 90, 255)) * 256); m.load_image = 0
    for i in range(40):
        d = f'S{i:02d}'
        m.put(f'{RP}/{d}/.show', f'M1PLUS-SHOW 1\ntitle={d} Show\nfeed=https://f.example/{d}\nchecked=0\n'.encode())
        lines = ''.join(f'g={d}-{k}\tp={NOW - 100 * k}\td=600\tl=1000\tf=e{k:03d}.mp3\tt=S{i:02d} E{k:03d}\tu=https://e.example/{d}/{k}\n' for k in range(300))
        m.put(f'{RP}/{d}/.episodes', (PCP.EPS_HEAD + lines).encode())
        for k in range(300): m.put(f'{RP}/{d}/e{k:03d}.mp3', b'', NOW - 100000 - (k * 40 + i) * 10)


def scan_tests(ctx):
    """The Downloaded scan: one show a tick of the loader, the order across shows, the cap, what a slice costs with 40 shows of 300 episodes, nothing in the dark."""
    expect = ctx.expect
    m = page()
    PCS.tap_row(m, 'Downloaded')
    per, shown = [], []
    for _ in range(14):
        m.call(PSYMS['pg_on_load'], a0=0, count=400000000)
        per.append([c[1].rsplit('/', 1)[1] for c in m.calls if c[0] == 'opendir' and c[1].startswith(RP + '/')])
        shown.append(m.props.get((m.sv, 'virtual_h')))
    scanned = [p[0] for p in per if p]
    expect(all(len(p) <= 1 for p in per) and scanned == ['Sub One', 'Alpha Show', 'bravo', 'Sub Two'], f'one show a tick, in the Shows page\'s order (the most recently updated first), each once ({scanned})')
    grown = [h for h, p in zip(shown, per) if p]
    expect(grown == sorted(grown) and grown[0] < grown[-1], f'the content grows with the slices: {grown}')
    expect(per[-1] == [] and not [c for c in m.calls if c[0] in ('opendir', 'open')], 'when the shows are done a tick reads nothing')
    if PERF:   # the cap and the order across shows, the cost of a slice: 40 shows of 300 episodes (stress scale)
        m = page(lambda mm: setattr(mm, 'reuse_heap', True), cardf=big_card)
        m.count()
        PCS.tap_row(m, 'Downloaded')
        cost, reads = [], []
        for _ in range(80):
            m.call(PSYMS['pg_on_load'], a0=0, count=400000000)
            r = [c[1] for c in m.calls if c[0] == 'opendir' and c[1].startswith(RP + '/S')]
            reads += r
            if r: cost.append(m.icount)
        expect(len(reads) == 40 and len(set(reads)) == 40 and all(len([1 for c in m.calls if c[0] == 'opendir']) <= 1 for _ in [0]), f'40 shows, one a tick, each once ({len(reads)})')
        L = lay(0, 300)
        expect(m.props.get((m.sv, 'virtual_h')) == L['h'], f'12000 files on the card, 300 rows: the content is {L["h"]} px')
        got = rows(m)
        want = [f'S{i:02d} E{k:03d}' for k, i in (divmod(n, 40) for n in range(300))]
        expect([t for t, _ in got] == want, f'the newest 300 of all shows by file date, interleaved ({[t for t, _ in got][:5]} ... {[t for t, _ in got][-2:]})')
        line = texts_at(m, 'label_ps_meta')[0][0]
        expect(line == '12000 episodes · 18 GB free', f'the storage line counts every file, past the cap too (no sizes here) ({line})')
        print(f'  Downloaded scan: a slice (300 episodes: read, parse, merge, sort, 300 stats and the sorted insert into 300 rows) costs {min(cost)}..{max(cost)} instructions (the first slice includes the page\'s own read of the shows); {len(cost)} slices in all')
        expect(max(cost) < 8_000_000, f'a slice stays under 8 million instructions ({max(cost)}): about 10 ms at the X2000\'s speed plus the card reads')
    # the screen off: the loader reads nothing; the first lit tick starts it again
    m = page()
    PCS.tap_row(m, 'Downloaded')
    m.screen(False); m.calls = []
    m.call(PSYMS['pg_on_load'], a0=0, count=400000000)
    expect(not [c for c in m.calls if c[0] in ('opendir', 'open', '__xstat')], 'dark: the loader reads no show')
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('opendir', 'open', '__xstat', 'widget_invalidate_force')], 'dark: the tick does no work for the page either')
    PCS.tick(m)
    expect(any(c[0] == 'timer_add' for c in m.calls), 'the first lit tick')
    m.call(PSYMS['pg_on_load'], a0=0, count=400000000)
    expect([c for c in m.calls if c[0] == 'opendir'], 'lit: the scan goes on')


def ip_state(m):
    """The worker's record as it is while Sub One's e.mp3 downloads, c.mp3 waits and f.mp3 has failed (d.mp3 is half on the card)."""
    SEL.running(m)
    DL.poke_slot(m, 1, 'Sub One', 'c.mp3', 1, seq=2)
    DL.poke_fail(m, 0, 'Sub One', 'f.mp3', PN['NET'])
    m.setword(DL.pn_at(12), 4)


def inprogress_tests(ctx):
    """The In Progress section: the worker's rows in queue order, then the failed one, then the paused .part; titles from the shows; the taps; the lists kept up to date from the worker without reading the shows again."""
    expect = ctx.expect
    m = page(ip_state)
    to_page(m)
    got = rows(m)
    expect(got[:4] == [('Ep E', '42%'), ('Ep C', 'Waiting'), ('Ep F', "Failed: Can't connect"), ('Ep D', 'Paused')] and [t for t, _ in got[4:]] == TITLES,
           f'In Progress: the running and waiting ones in queue order, the failed one, the paused .part; then the Downloaded rows ({got[:5]})')
    L = lay(4, 7)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and sorted(rows_y(m)) == L['rows'], 'the rows are at the model\'s places: In Progress, PP_SEC_GAP, Downloaded')
    # taps: the running one is paused, the waiting one leaves, the failed one is tried again, the paused one resumes
    m.calls = []; m.thread = None
    tap_row(m, 0, 4, 7)
    expect(DL.run_state(m, DL.key_of('Sub One', 'e.mp3')) == DL.QS['STOPPING'] and toasts_fixed(m) == [], 'a tap on the running one pauses it (the worker is told to cancel it; the .part stays)')
    DL.unstop(m)
    tap_row(m, 1, 4, 7)
    expect(DL.fn(m, 'pn_dl_count') == 1 and DL.state(m, 'c.mp3', 'Sub One')[0] == 0, 'a tap on a waiting one takes it out of the queue')
    got = rows(m)
    expect([t for t, _ in got[:3]] == ['Ep E', 'Ep F', 'Ep D'] and lay(3, 7)['h'] == m.props.get((m.sv, 'virtual_h')), f'its row is gone, the page is one row shorter ({[t for t, _ in got[:3]]})')
    tap_row(m, 1, 3, 7)
    expect(DL.state(m, 'f.mp3', 'Sub One')[0] == 1 and DL.fn(m, 'pn_dl_count') == 2 and dict(rows(m)).get('Ep F') == 'Waiting', 'a tap on a failed one tries it again (queued)')
    tap_row(m, 2, 3, 7)
    expect(DL.state(m, 'd.mp3', 'Sub One')[0] == 1 and dict(rows(m)).get('Ep D') == 'Waiting', 'a tap on a paused one resumes it (queued)')
    # no show is read again for those taps
    expect(not [c for c in m.calls if c[0] == 'opendir'], 'none of the taps read a show again')
    # the worker finishes e.mp3 (the file is there, the slot is free) and cancels f.mp3: the rows follow from the worker's state and the card
    m = page(ip_state)
    to_page(m)
    SEL_E = f'{RP}/Sub One/e.mp3'
    m.put(SEL_E, b'done', NOW - 5); m.sizes[SEL_E] = 3 << 20
    DL.poke_slot(m, 0, 'Sub One', 'e.mp3', 0)
    m.setword(DL.pn_at(DL.DKEY), 0); m.setword(DL.pn_at(DL.DBUSY), 0)
    m.setword(DL.pn_at(12), 500)
    m.calls = []
    PCS.tick(m)
    reads = [c[1].rsplit('/', 1)[1] for c in m.calls if c[0] == 'opendir' and c[1].startswith(RP + '/')]
    got = rows(m)
    expect([t for t, _ in got[:3]] == ['Ep C', 'Ep F', 'Ep D'] and got[3][0] == 'Ep E' and got[3][1] == 'Sub One · 1h ago · 3 MB' and len(got) == 11 and reads == ['Sub One'],
           f'a finished download leaves In Progress and is the newest Downloaded row; only its show is read (for its date), not the whole card ({[t for t, _ in got[:4]]}, {reads})')
    line = texts_at(m, 'label_ps_meta')[0][0]
    expect(line == '8 episodes · 220 MB · 18 GB free', f'the storage line counts it ({line})')
    # a paused one: the worker lets go of the running one, its .part stays: the row says Paused
    m = page(ip_state)
    m.put(f'{RP}/Sub One/e.mp3.part', b'x' * 10)
    to_page(m)
    DL.poke_slot(m, 0, 'Sub One', 'e.mp3', 0)
    m.setword(DL.pn_at(DL.DKEY), 0); m.setword(DL.pn_at(DL.DBUSY), 0)
    m.setword(DL.pn_at(12), 501)
    PCS.tick(m)
    got = rows(m)
    expect(('Ep E', 'Paused') in got[:4] and len(got) == 11, f'a cancelled download whose .part is on the card becomes a paused row ({got[:4]})')
    # the cap of the section: 32 queued and 16 failed make 40 rows at most
    m = page()
    for i in range(32): DL.poke_slot(m, i, 'Sub One', f'q{i}.mp3', 1, seq=i + 1)
    for i in range(16): DL.poke_fail(m, i, 'Sub One', f'z{i}.mp3', PN['HTTP'])
    to_page(m)
    expect(m.props.get((m.sv, 'virtual_h')) == lay(40, 7)['h'], 'at most 40 In Progress rows: 32 queued, 16 failed, the rest left out (the paused one too)')
    # progress changes a line, not the rows
    m = page(lambda mm: SEL.running(mm, got=100000))
    to_page(m)
    expect(rows(m)[0][1] == '9%', f'{rows(m)[0]}')
    m.setword(DL.pn_at(DL.DGOT), 500000); m.setword(DL.pn_at(DL.DGEN), 9)
    m.calls = []
    PCS.tick(m)
    expect(rows(m)[0][1] == '50%' and not [c for c in m.calls if c[0] in ('opendir', '__xstat')], 'a step of progress: the line is made again, the card is not read')


def ip_marks(m, n_ip, n_dl, off=0):
    """{row: [atlas cells]} of the download ring blits (a 14 px square at the grey line's middle), {row: dst x} of the "..." glyph blits, from a frame at scroll off."""
    L = lay(n_ip, n_dl)['rows']
    px, dots = O['PA_DL_PX'], (O['PA_DOTS_PX'],) * 2
    rings, dts = {}, {}
    for b in PCP.paint(m, off)[0]:
        for i, y in enumerate(L):
            if tuple(b[2][2:]) == (px, px) and b[2][1] == y - off + SY + O['LIST_SUB_H'] // 2 - px // 2:
                rings.setdefault(i, []).append((b[1][0] // px + (b[1][1] - O['PA_DSD_H']) // px * O['PA_DL_COLS'], b[2][0]))
            if tuple(b[2][2:]) == dots and tuple(b[1]) == (0, O['PA_DOTS_Y'], *dots) and b[2][1] == y - off + (ROW - 1) // 2 - dots[0] // 2:
                dts[i] = b[2][0]
    return rings, dts


def sheet_rows(m): return [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]


def tap_dots(m, i, n_ip, n_dl):
    y = lay(n_ip, n_dl)['rows'][i] + (ROW - 1) // 2
    PCP.tap(m, O['PS_DOTS_CX'], y, off=max(0, y - 150))


def ring_tests(ctx):
    """The In Progress rows' download ring and "...": the ring (the Subscription pages' cells: step, stop square or arrow) before the grey line of a running or waiting download, none on a failed or paused one or a Downloaded row;
    the text without "Downloading"; the "..." on the four states and its sheet (Pause / Resume / Retry, Cancel Download); none in select mode."""
    expect = ctx.expect
    STOP, ARROW = O['PA_DL_STOP'], O['PA_DL_ARROW']
    m = page(ip_state)
    to_page(m)
    L = lay(4, 7)['rows']
    rings, dts = ip_marks(m, 4, 7)
    x0 = O['LIST_TEXT_X']
    expect(rings == {0: [(5, x0), (STOP, x0)], 1: [(0, x0), (ARROW, x0)]}, f'a running download (42% = step 5, the stop square over it) and a waiting one (the empty ring, the arrow) have the ring at the text column; the failed, the paused and the Downloaded rows none ({rings})')
    expect(sorted(dts) == [0, 1, 2, 3] and set(dts.values()) == {O['PS_DOTS_CX'] - O['PA_DOTS_PX'] // 2}, f'the "..." on each of the four In Progress rows, none on a Downloaded row ({dts})')
    fr = [(off, PCP.paint(m, off)[1:3]) for off in (0, 200)]
    sub = {r[1] + off: (t, (r[0], r[1] + off, *r[2:])) for off, (tx, st) in fr for (t, r), s in zip(tx, st) if s == 'label_row_sub'}
    ttl = {r[1] + off: (r[0], r[1] + off, *r[2:]) for off, (tx, st) in fr for (t, r), s in zip(tx, st) if s == 'label_row_title'}
    w = O['LIST_TEXT_W_CHEV']
    expect(sub[L[0] + SY] == ('42%', (x0 + 20, L[0] + SY, w - 20, O['LIST_SUB_H'])) and sub[L[1] + SY][1][0] == x0 + 20 and sub[L[1] + SY][0] == 'Waiting'
           and sub[L[2] + SY][1][:3] == (x0, L[2] + SY, w) and sub[L[3] + SY][1][:3] == (x0, L[3] + SY, w) and sub[L[4] + SY][1][2] == O['LIST_TEXT_W']
           and all(ttl[L[i] + TY][2] == w for i in range(4)) and ttl[L[4] + TY][2] == O['LIST_TEXT_W'],
           f'the grey line of a ring row starts a ring and a gap right (42%, no "Downloading"); every In Progress row\'s lines stop short of the "..."; the Downloaded rows keep their width ({sub[L[0] + SY]})')
    # the ring follows the progress, read at paint
    m.setword(DL.pn_at(DL.DGOT), 500000); m.setword(DL.pn_at(DL.DGEN), 9)
    PCS.tick(m)
    rings, _ = ip_marks(m, 4, 7)
    expect(rings[0] == [(6, x0), (STOP, x0)] and rows(m)[0][1] == '50%', f'50% = step 6 ({rings.get(0)}, {rows(m)[0]})')
    m = page(lambda mm: SEL.running(mm, got=5 << 20, total=0))
    to_page(m)
    rings, _ = ip_marks(m, 1, 7)
    expect(rows(m)[0][1] == '5 MB' and rings.get(0) == [(0, x0), (STOP, x0)], f'a length that is not known: "5 MB", the empty ring with the stop square ({rows(m)[0]}, {rings})')
    # the sheet: the first row by the state, then Cancel Download (the labels are the asset's)
    lab = {r[0]: r[2] for r in pod_ui.PS_SHEET_ROWS}
    expect([lab[r] for r in ('dlpause', 'dlresume', 'dlretry', 'dlcancel')] == ['Pause', 'Resume', 'Retry', 'Cancel Download'], 'the sheet rows\' labels')
    m = page(ip_state)
    to_page(m)
    for i, want in ((0, ['dlpause', 'dlcancel']), (1, ['dlpause', 'dlcancel']), (2, ['dlretry', 'dlcancel']), (3, ['dlresume', 'dlcancel'])):
        tap_dots(m, i, 4, 7)
        expect(sheet_rows(m) == want and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet2' and title(m) == 'Downloaded', f'row {i}: the sheet has {want} ({sheet_rows(m)})')
        PCP.click(m, 'pg_sh_scrim')
    tap_row(m, 0, 4, 7)
    expect(flags(m, 'pg_sh_card') == (0, 0), 'a tap on the row body opens no sheet (it pauses)')
    tap_dots(m, 4, 4, 7)
    expect(flags(m, 'pg_sh_card') == (0, 0) and title(m) != 'Downloaded', f'a Downloaded row has no "...": the same place opens its episode ({title(m)})')
    # Pause, Retry, Resume
    m = page(ip_state)
    to_page(m)
    key = DL.key_of('Sub One', 'e.mp3')
    m.calls = []
    tap_dots(m, 0, 4, 7)
    PCP.click(m, 'pg_sh_dlpause')
    u = unlinks(m)
    expect(DL.run_state(m, key) == DL.QS['STOPPING'] and flags(m, 'pg_sh_card') == (0, 0) and u == [], 'Pause on the running one: the worker is told to cancel it, the .part stays, the sheet closes')
    tap_dots(m, 2, 4, 7)
    PCP.click(m, 'pg_sh_dlretry')
    expect(DL.state(m, 'f.mp3', 'Sub One')[0] == 1 and dict(rows(m)).get('Ep F') == 'Waiting', 'Retry on the failed one queues it')
    tap_dots(m, 3, 4, 7)
    PCP.click(m, 'pg_sh_dlresume')
    expect(DL.state(m, 'd.mp3', 'Sub One')[0] == 1 and dict(rows(m)).get('Ep D') == 'Waiting', 'Resume on the paused one queues it')
    # Cancel Download, no confirm: the paused one, the failed one, the waiting one, the running one
    m = page(ip_state)
    to_page(m)
    m.calls = []
    tap_dots(m, 3, 4, 7)
    PCP.click(m, 'pg_sh_dlcancel')
    u, c = unlinks(m), confirms(m)
    got = rows(m)
    expect(u == ['Sub One/d.mp3.part'] and c == [] and [t for t, _ in got[:4]] == ['Ep E', 'Ep C', 'Ep F', 'Ep A'] and lay(3, 7)['h'] == m.props.get((m.sv, 'virtual_h')) and f'{RP}/Sub One/d.mp3.part' not in m.fs,
           f'Cancel Download on a paused row: its .part is unlinked, no confirm, the row is gone ({u}, {c}, {[t for t, _ in got[:4]]})')
    m.calls = []
    tap_dots(m, 2, 3, 7)
    PCP.click(m, 'pg_sh_dlcancel')
    expect(DL.state(m, 'f.mp3', 'Sub One')[0] == 0 and [t for t, _ in rows(m)[:3]] == ['Ep E', 'Ep C', 'Ep A'], 'Cancel Download on a failed one: its failure is forgotten, the row is gone')
    m.calls = []
    tap_dots(m, 1, 2, 7)
    PCP.click(m, 'pg_sh_dlcancel')
    u = unlinks(m)
    expect(DL.state(m, 'c.mp3', 'Sub One')[0] == 0 and DL.fn(m, 'pn_dl_count') == 1 and u == ['Sub One/c.mp3.part'] and [t for t, _ in rows(m)[:2]] == ['Ep E', 'Ep A'], f'Cancel Download on a waiting one: it leaves the queue ({u})')
    m.put(f'{RP}/Sub One/e.mp3.part', b'x' * 10)
    m.calls = []
    tap_dots(m, 0, 1, 7)
    PCP.click(m, 'pg_sh_dlcancel')
    u = unlinks(m)
    expect(DL.run_state(m, key) == DL.QS['DROPPING'] and u == ['Sub One/e.mp3.part'] and f'{RP}/Sub One/e.mp3.part' not in m.fs and [t for t, _ in rows(m)[:1]] != ['Ep E'],
           f'Cancel Download on the running one: the worker is told to drop it, its .part goes and the row is gone ({u}, {rows(m)[:1]})')
    # select mode: no "..." and no rings' dots
    m = page(ip_state)
    to_page(m)
    start_select(m)
    rings, dts = ip_marks(m, 4, 7)
    expect(dts == {} and sorted(rings) == [0, 1] and flags(m, 'pg_sh_card') == (0, 0), f'select mode: no "..." on any row ({dts})')


def open_tests(ctx):
    """A tap on a Downloaded row opens the episode's page (the Show page's, its pill plays); Back returns to the Downloads page at the same place, with the rows as they were and no show read again."""
    expect = ctx.expect
    m = page()
    to_page(m)
    L = lay(1, 7)
    m.calls = []
    tap_row(m, 3, 1, 7)   # the third Downloaded row: ep1 of Alpha Show
    heads = [PCS.fixed(t) for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_head']
    expect(heads == ['ep1'] and m.props.get((m.sv, 'virtual_h')) != L['h'] and not [c for c in m.calls if c[0] in ('navigator_to_with_context', 'pthread_create')],
           f'a tap on a row opens that episode\'s page (its title ep1; nothing plays, nothing is queued) ({heads})')
    expect(flags(m, 'btn_more') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np', 'the page: Back and the Now Playing disc')
    pill = [(PCS.fixed(t), r) for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_pill']
    expect(pill and pill[0][0].endswith('m') or pill[0][0] == 'Play', f'its pill is the episode\'s play pill ({pill})')
    m.calls = []
    PCP.tap(m, 30, pill[0][1][1] + 15)
    q, idx = m.played
    paths = [m.read_cstr(m.word(rec + O['REC_PATH'])) for rec in q]
    expect(A1 in paths and paths[idx] == A1, f'the page\'s pill plays it (the Alpha Show queue, at ep1) ({paths}, {idx})')
    m.calls = []
    # the page's show row opens the show's page; Back from it is still the Downloads page
    m.calls = []
    y = next(r[1] for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_meta' and r[0] == pod_show.PD['PD_SHOW_TEXT_X'])
    PCP.tap(m, 150, y + 11)
    heads = [PCS.fixed(t) for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_head']
    expect(heads != ['ep1'] and flags(m, 'btn_more') == (1, 1) and m.props.get((m.sv, 'virtual_h')) != L['h'], f'a tap on the show row: the Alpha Show page, its list with its "..." (not the episode page) ({heads})')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Downloaded' and [t for t, _ in rows(m)[1:]] == TITLES and m.props.get((m.sv, 'virtual_h')) == L['h'], 'Back from the show\'s page: the Downloads page with the same rows')
    tap_row(m, 3, 1, 7)
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Downloaded' and [t for t, _ in rows(m)[1:]] == TITLES and m.props.get((m.sv, 'virtual_h')) == L['h'], 'Back: the Downloads page with the same rows')
    expect(m.props.get((m.sv, 'yoffset')) == max(0, L['rows'][3] - 150), f'at the offset the tap left ({m.props.get((m.sv, "yoffset"))} against {max(0, L["rows"][3] - 150)})')
    expect(not [c for c in m.calls if c[0] == 'opendir'] and not [c for c in m.calls if c[0] == 'open' and c[1].endswith('/.episodes')], 'no show was read again')
    # a deeper row, scrolled: the same place comes back
    m = page(lambda mm: setattr(mm, 'reuse_heap', True), cardf=big_card)
    PCS.tap_row(m, 'Downloaded')
    settle(m, 120)
    tap_row(m, 200, 0, 300)
    PCP.click(m, 'btn_return')
    y = lay(0, 300)['rows'][200]
    expect(title(m) == 'Downloaded' and m.props.get((m.sv, 'yoffset')) == y - 150, f'a row 200 rows down: Back returns to the same scroll position ({m.props.get((m.sv, "yoffset"))} against {y - 150})')
    # Back from the page goes on to the Shows level where it was
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Podcasts' and m.props.get((m.sv, 'yoffset')) > 0, 'Back again: the Shows level, scrolled to the Library rows where it was left')
    # a file that is gone since the scan: its row goes, no page opens
    m = page()
    to_page(m)
    del m.fs[B3]
    tap_row(m, 2, 1, 7)
    heads = [t for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_head']
    expect(title(m) == 'Downloaded' and not heads and len(rows(m)) == 7, f'an episode whose file has gone: the row leaves, nothing opens ({len(rows(m))} rows)')
    # an episode removed on its own page: Back returns without it
    m = page()
    to_page(m)
    tap_row(m, 2, 1, 7)   # Bravo 3
    dots = [b for b in PCP.paint(m, 0)[0] if tuple(b[1]) == (0, O['PA_DOTS_Y'], O['PA_DOTS_PX'], O['PA_DOTS_PX'])]
    PCP.tap(m, O['PS_DOTS_CX'], dots[0][2][1] + 10)
    PCP.click(m, 'pg_sh_rm')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Downloaded' and [t for t, _ in rows(m)[1:]] == [t for t in TITLES if t != 'Bravo 3'] and B3 not in m.fs, f'Remove Download on the episode\'s page: Back, and its row is gone ({[t for t, _ in rows(m)[1:]]})')


def marks_of(m, n_ip, n_dl):
    """{row index: image} of the select marks, from frames scrolled 100 px apart (a mark is drawn only wholly inside the view)."""
    tops_ = lay(n_ip, n_dl, True)['rows']
    out = {}
    for off in range(0, max(m.props.get((m.sv, 'virtual_h'), 0) - 300, 100), 100):
        bl, *_ = PCP.paint(m, off)
        for b in bl:
            if tuple(b[2][2:]) == (SG_MARK, SG_MARK):
                y = b[2][1] + off - (ROW - SG_MARK) // 2
                if y in tops_: out.setdefault(tops_.index(y), (b[2][0], b[0]))
    return out


def start_select(m):
    PCP.click(m, 'btn_more')
    PCP.click(m, 'pg_sh_select')


def select_tests(ctx):
    """The page's select mode across both sections: marks on every row but the running one, the confirm, what Delete does to each kind of row, the playing episode kept, the totals."""
    expect = ctx.expect
    m = page(ip_state)
    to_page(m)
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    expect(shown == ['select'] and PCS.fixed(m.wtext.get(m.widgets['pg_sh_select_tx'], '')) == 'Select' and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1',
           f'the "..." sheet: Select (nothing is played yet, so no Delete Played Episodes) ({shown})')
    PCP.click(m, 'pg_sh_select')
    t = m.widgets['label_title']
    expect(title(m) == '0 Selected' and flags(m, 'btn_selall') == (1, 1) and flags(m, 'pg_bar') == (1, 1) and flags(m, 'btn_more') == (0, 0) and flags(m, 'pg_sh_card') == (0, 0)
           and m.props.get((m.widgets['btn_return'], 'style:normal:icon')) == 'ah_nav_close', 'Select: the x, 0 Selected, Select All, the bar; the sheet closes')
    L = lay(4, 7, True)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'], 'the content is the bar\'s height longer')
    mk = marks_of(m, 4, 7)
    expect(sorted(mk) == [1, 2, 3] + list(range(4, 11)) and len({b for _, b in mk.values()}) == 1 and all(x == O['LIST_ART_X'] + (O['SG_SEL_COL'] - 6 - SG_MARK) // 2 for x, _ in mk.values()),
           f'a mark on every row but the running one, in the mark column ({sorted(mk)})')
    # taps mark; the running one cannot be marked; a drag marks nothing
    m.calls = []
    tap_row(m, 0, 4, 7)
    expect(not [c for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == t], 'the running row cannot be marked')
    tap_row(m, 4, 4, 7)
    tap_row(m, 1, 4, 7)
    tap_row(m, 3, 4, 7)
    expect(title(m) == '3 Selected', f'a Downloaded row, the waiting one and the paused one marked ({title(m)})')
    tap_row(m, 4, 4, 7, move=40)
    expect(title(m) == '3 Selected', 'a drag marks nothing')
    PCP.click(m, 'btn_selall'); PCP.click(m, 'btn_selall')
    expect(title(m) == '0 Selected', 'Select All twice: all, then none')
    PCP.click(m, 'btn_selall')
    expect(title(m) == '10 Selected', 'Select All marks the ten rows that can be marked')
    PCP.click(m, 'btn_selall')
    # No in the confirm keeps the marks; In Progress rows alone: the downloads confirm
    tap_row(m, 1, 4, 7); tap_row(m, 3, 4, 7)
    m.confirm_yes = False; m.calls = []
    PCP.click(m, 'pg_del')
    expect(confirms(m) == ['Remove the selected downloads?'] and not unlinks(m) and title(m) == '2 Selected' and flags(m, 'pg_bar') == (1, 1), 'two In Progress rows: "Remove the selected downloads?"; No: nothing is deleted, the marks stay')
    m.confirm_yes = True; m.calls = []
    PCP.click(m, 'pg_del')
    expect(sorted(unlinks(m)) == sorted(['Sub One/c.mp3.part', 'Sub One/d.mp3.part']) and DL.state(m, 'c.mp3', 'Sub One')[0] == 0 and f'{RP}/Sub One/a.mp3' in m.fs, f'a waiting one leaves the queue and a paused one loses its .part; no file of an episode goes ({unlinks(m)})')
    expect(flags(m, 'pg_bar') == (0, 0) and title(m) == 'Downloaded' and [t for t, _ in rows(m)[:2]] == [('Ep E'), ('Ep F')] and m.props.get((m.sv, 'virtual_h')) == lay(2, 7)['h'], 'the mode ended; the rows left the lists (no show read again)')
    # a Downloaded row and an In Progress one together: the files go, the played mark is forgotten, the line stays
    m = page(ip_state)
    to_page(m)
    h = PCP.pc_hash(SB)
    m.call(PSYMS['pc_mark'], a0=h, a1=1, count=2000000)
    start_select(m)
    tap_row(m, 4, 4, 7); tap_row(m, 10, 4, 7); tap_row(m, 3, 4, 7)   # SA, SB (played), the paused one
    m.calls = []
    PCP.click(m, 'pg_del')
    expect(confirms(m) == ['Delete the selected episodes?'], f'a Downloaded row among the marks: "Delete the selected episodes?" ({confirms(m)})')
    expect(sorted(unlinks(m)) == sorted(['Sub One/a.mp3', 'Sub One/a.mp3.part', 'Sub One/b.mp3', 'Sub One/b.mp3.part', 'Sub One/d.mp3.part']), f'each Downloaded file and its .part, and the paused .part ({unlinks(m)})')
    expect(m.state(h)[0] == 0 and b'f=a.mp3' in m.fs[f'{RP}/Sub One/.episodes'] and b'f=b.mp3' in m.fs[f'{RP}/Sub One/.episodes'], 'the played mark is forgotten, the .episodes lines stay (the episodes are remote again)')
    got = rows(m)
    expect([t for t, _ in got] == ['Ep E', 'Ep C', 'Ep F'] + ['Bravo 3', 'ep1', 'Bravo 1', 'ep2', 'Bravo 2'] and not toasts_fixed(m), f'the rows are gone from both sections ({[t for t, _ in got]})')
    line = texts_at(m, 'label_ps_meta')[0][0]
    expect(line == '5 episodes · 168 MB · 18 GB free', f'the storage line is the new totals ({line})')
    # the playing episode is never deleted
    m = page()
    to_page(m)
    m.track(SA)
    start_select(m)
    PCP.click(m, 'btn_selall')
    m.calls = []
    PCP.click(m, 'pg_del')
    files = [('Alpha Show', 'ep1.mp3'), ('Alpha Show', 'ep2.mp3'), ('bravo', 'b1.mp3'), ('bravo', 'b2.mp3'), ('bravo', 'b3.mp3'), ('Sub One', 'b.mp3')]
    expect(sorted(unlinks(m)) == sorted([f'{d}/{f}' for d, f in files] + [f'{d}/{f}.part' for d, f in files] + ['Sub One/d.mp3.part']), f'everything marked but the playing a.mp3 ({unlinks(m)})')
    said = toasts_fixed(m)
    expect(said == ['The playing episode was kept'], f'the toast says the playing episode was kept ({said})')
    left = [t for t, _ in rows(m)]
    expect(SA in m.fs and left == ['Ep A'], f'it stays, alone in the list ({left})')
    # leaving select mode: the x; a download that finishes while rows are marked does not move the lists
    m = page(ip_state)
    to_page(m)
    start_select(m)
    tap_row(m, 4, 4, 7)
    m.setword(DL.pn_at(12), 900)
    PCS.tick(m)
    expect(title(m) == '1 Selected' and len(marks_of(m, 4, 7)) == 10, 'the worker moves while rows are marked: the rows and the marks stay as they are')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Downloaded' and flags(m, 'pg_bar') == (0, 0) and flags(m, 'btn_more') == (1, 1), 'the x leaves select mode')


def played_tests(ctx):
    """Delete Played Episodes: the sheet row appears once the scan is done and a Downloaded episode is played; the confirm; every played file goes except the playing one; the toast; the played marks are forgotten."""
    expect = ctx.expect
    m = page()
    for p in (A1, B1, B2): m.call(PSYMS['pc_mark'], a0=PCP.pc_hash(p), a1=1, count=2000000)
    PCS.tap_row(m, 'Downloaded')
    settle(m, 3)   # (the first show or two: rows, but the scan is not done)
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if m.props.get((m.widgets[f'pg_sh_{r}'], 'visible'), 0) == 1]
    expect(shown == ['select'], f'while the scan is going on the sheet has Select alone: no Delete Played Episodes row yet ({shown})')
    PCP.click(m, 'pg_sh_scrim')
    settle(m)
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    expect(shown == ['select', 'delplayed'] and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet2'
           and PCS.fixed(m.wtext.get(m.widgets['pg_sh_delplayed_tx'], '')) in ('Delete Played Episodes', ''), f'once it has: Select and Delete Played Episodes on the two-row glass ({shown})')
    ys = {r: [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'pg_sh_{r}']][-1][3] for r in shown}
    expect(ys == {'select': 0, 'delplayed': O['PM_ROW_H']}, f'Select on top ({ys})')
    # No: nothing; Yes with the playing episode among the played ones
    m.confirm_yes = False; m.calls = []
    PCP.click(m, 'pg_sh_delplayed')
    expect(confirms(m) == ['Delete all played episodes?'] and not unlinks(m) and not toasts_fixed(m) and flags(m, 'pg_sh_card') == (0, 0), f'the confirm; No: nothing happens ({confirms(m)})')
    m.confirm_yes = True
    m.track(B2)   # the playing one is a played episode too
    PCP.click(m, 'btn_more'); m.calls = []
    PCP.click(m, 'pg_sh_delplayed')
    expect(sorted(unlinks(m)) == sorted(['Alpha Show/ep1.mp3', 'bravo/b1.mp3']), f'every played episode but the playing one is deleted ({unlinks(m)})')
    expect(toasts_fixed(m) == ['2 deleted, 105 MB freed'], f'the toast says how many and how much space ({toasts_fixed(m)})')
    expect(A1 not in m.fs and B1 not in m.fs and B2 in m.fs and b'f=b1.mp3' in m.fs[f'{RP}/bravo/.episodes'], 'the files are gone, the playing one stays, the .episodes line stays')
    expect(m.state(PCP.pc_hash(A1))[0] == 0 and m.state(PCP.pc_hash(B1))[0] == 0 and m.state(PCP.pc_hash(B2))[0] == 2, 'the played marks of the deleted ones are forgotten; the one that stayed is still played')
    got = rows(m)
    expect([t for t, _ in got[1:]] == ['Ep A', 'Bravo 3', 'ep2', 'Bravo 2', 'Ep B'] and m.props.get((m.sv, 'virtual_h')) == lay(1, 5)['h'], f'the rows left the list ({[t for t, _ in got[1:]]})')
    line = texts_at(m, 'label_ps_meta')[0][0]
    expect(line == '5 episodes · 112 MB · 18 GB free', f'the storage line follows ({line})')
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    expect(shown == ['select', 'delplayed'], 'the playing episode is played still: the row stays')
    m.calls = []
    PCP.click(m, 'pg_sh_delplayed')
    expect(not unlinks(m) and toasts_fixed(m) == ['The playing episode was kept'], f'only the playing one is left to delete: it is kept, with the toast ({toasts_fixed(m)})')
    # nothing played: no row
    m = page()
    to_page(m)
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    expect(shown == ['select'], f'nothing played: the sheet has Select alone ({shown})')
    # the empty page: no rows, no "..."
    m = page(lambda mm: mm.put(f'{RP}/Fresh/.show', f'M1PLUS-SHOW 1\ntitle=Fresh\nfeed={PCS.F["three"]}\nimage=\nchecked=0\n'.encode()), lambda mm: None)
    to_page(m)
    expect(flags(m, 'label_status')[0] == 0 and flags(m, 'btn_more') == (0, 0) and m.props.get((m.view, 'visible')) == 1 and 'No downloads' in PCP.hint(m), 'nothing downloaded and nothing under way: the header and storage line stay, "No downloads" is painted under them, no "..."')
    expect(m.props.get((m.sv, 'virtual_h'), 0) <= 400, 'and the empty page fits the view: it does not scroll')


def heads_tests(ctx):
    """The section headers: drawn (and given height) only when both In Progress and Downloaded have rows. Alone, a section has no header (the page would read Downloads, then Downloaded) and its rows start where the
    first header would have; the hit testing, the select marks and the heights follow the model."""
    expect = ctx.expect
    heads = lambda m: list(dict.fromkeys(t for off in range(0, max(m.props.get((m.sv, 'virtual_h'), 0) - 300, 100), 100) for t, _ in texts_at(m, 'label_ps_sech', off)))
    no_part = lambda mm: (card(mm), [mm.fs.pop(p) for p in [p for p in mm.fs if p.endswith('.part')]])
    no_files = lambda mm: (card(mm), [mm.fs.pop(p) for p in [p for p in mm.fs if p.endswith('.mp3')]])
    # both: headers as before
    m = page(ip_state)
    to_page(m)
    L = lay(4, 7)
    expect(heads(m) == ['In Progress'] and L['y_ip'] == O['PDL_LINE_PITCH'] and 'y_dh' not in L and L['rows'][4] == L['rows'][3] + ROW + O['PP_SEC_GAP'] and sorted(rows_y(m)) == L['rows'],
           f'both sections: the In Progress header alone (the title Downloaded is the downloaded rows\' header), the downloaded rows PP_SEC_GAP under the last In Progress row ({heads(m)}, {sorted(rows_y(m))[3:5]})')
    # only Downloaded
    m = page(cardf=no_part)
    to_page(m)
    L = lay(0, 7)
    got = rows(m)
    expect([t for t, _ in got] == TITLES and heads(m) == [] and L['y_ip'] is None, f'only downloaded rows: no section header, the seven rows ({heads(m)}, {[t for t, _ in got]})')
    expect(sorted(rows_y(m)) == L['rows'] and L['rows'][0] == O['PDL_LINE_PITCH'] and m.props.get((m.sv, 'virtual_h')) == L['h'] == O['PDL_LINE_PITCH'] + 7 * ROW + O['PP_BOTTOM'],
           f'the rows start where the first header started, y {O["PDL_LINE_PITCH"]}; the height is the rows and PP_BOTTOM ({L["rows"][0]}, {m.props.get((m.sv, "virtual_h"))})')
    expect(texts_at(m, 'label_ps_meta')[0][1][1] == O['PDL_LINE_Y'] and title(m) == 'Downloaded', 'the storage line and the large title are where they are with headers')
    m.calls = []
    tap_row(m, 2, 0, 7)
    opened = [PCS.fixed(t) for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_head']
    expect(opened == ['ep1'], f'a tap on the third row opens its episode page, ep1, at the model\'s place ({opened})')
    PCP.click(m, 'btn_return')
    start_select(m)
    mk = marks_of(m, 0, 7)
    expect(sorted(mk) == list(range(7)) and m.props.get((m.sv, 'virtual_h')) == lay(0, 7, True)['h'], f'select mode: a mark on each of the seven rows at the model\'s places ({sorted(mk)})')
    tap_row(m, 2, 0, 7)
    expect(title(m) == '1 Selected', f'a tap on the third row marks it ({title(m)})')
    m.calls = []
    PCP.click(m, 'pg_del')
    expect(unlinks(m) == [A1.replace(RP + '/', ''), A1.replace(RP + '/', '') + '.part'], f'Delete takes the marked row\'s file, ep1 ({unlinks(m)})')
    # only In Progress
    m = page(ip_state, cardf=no_files)
    to_page(m)
    L = lay(4, 0)
    got = rows(m)
    expect([t for t, _ in got] == ['Ep E', 'Ep C', 'Ep F', 'Ep D'] and heads(m) == [] and L['y_ip'] is None, f'only in-progress rows: no section header ({heads(m)}, {[t for t, _ in got]})')
    expect(sorted(rows_y(m)) == L['rows'] and L['rows'][0] == O['PDL_LINE_PITCH'] and m.props.get((m.sv, 'virtual_h')) == L['h'], f'the rows start at y {O["PDL_LINE_PITCH"]} ({sorted(rows_y(m))[:1]})')
    m.calls = []; m.thread = None
    tap_row(m, 1, 4, 0)
    expect(DL.fn(m, 'pn_dl_count') == 0 or DL.state(m, 'c.mp3', 'Sub One')[0] == 0, 'a tap on the waiting row takes it out of the queue (the model\'s place)')
    # the headers come when the other section gets a row: a download finishing
    m = page(ip_state, cardf=no_files)
    to_page(m)
    f = f'{RP}/Sub One/e.mp3'
    m.put(f, b'done', NOW - 5); m.sizes[f] = 3 << 20
    DL.poke_slot(m, 0, 'Sub One', 'e.mp3', 0)
    m.setword(DL.pn_at(DL.DKEY), 0); m.setword(DL.pn_at(DL.DBUSY), 0)
    m.setword(DL.pn_at(12), 500)
    PCS.tick(m)
    expect(heads(m) == ['In Progress'] and sorted(rows_y(m)) == lay(3, 1)['rows'], f'a finished download gives the page both sections: the In Progress header comes ({heads(m)})')
    # the empty page has no header either
    m = page(cardf=lambda mm: (card(mm), [mm.fs.pop(p) for p in [p for p in mm.fs if p.endswith(('.part', '.mp3'))]]))
    to_page(m)
    expect(heads(m) == [] and 'No downloads' in ' '.join(t for t, _ in texts_at(m, 'label_ps_cdim')), f'nothing: the hint only ({heads(m)}, {PCP.hint(m)!r})')


def off_tests(ctx):
    """The screen-off rule on this page: a dark tick makes no list and reads nothing; a lit one does; no new timer."""
    expect = ctx.expect
    m = page(ip_state)
    to_page(m)
    before = rows(m)
    m.screen(False); m.calls = []
    m.setword(DL.pn_at(12), 700)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(rows(m) == before and not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'opendir', '__xstat', 'widget_set_tr_text')], 'dark: a tick does not read the worker or the card, and repaints nothing')
    PCS.tick(m)
    expect([c for c in m.calls if c[0] == '__xstat'], 'the next lit tick brings the lists up to date')
    m = page()
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] not in (PSYMS['pg_tick'], PSYMS['pg_on_load'])], 'the page adds only its tick and the loader (page-scoped)')
    to_page(m, done=False)
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] not in (PSYMS['pg_tick'], PSYMS['pg_on_load'])], 'the Downloads page adds no timer of its own')


def fill(s, *n):
    for v in n: s = s.replace('%d', str(v), 1)
    return s


def width_tests(ctx):
    """The page's strings in the 13 languages in the real font: the Library rows' grey lines, the storage line (and its shorter forms), the headers, the sheet's labels, the confirm and the toast."""
    expect = ctx.expect
    fnt = PCS.sw().font()
    worst = {}
    row = O['PS_SHEET_VALUE_R'] - O['PS_SHEET_TEXT_X']
    confirms = []
    shows = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        T = lambda key, t=t: pod_i18n.TEXT[key][t]
        tr = lambda key, *n, t=t: fill(pod_i18n.TEXT[key][t], *n)
        w18 = lambda s: fnt.width(s, 18)
        w15 = lambda s: fnt.width(s, 15)
        gb = tr('%d GB', 125)
        free = T('%s free').replace('%s', gb)
        cnt = tr('%d episodes', 12000)
        chain = [' · '.join([cnt, tr('%d MB', 999), free]), ' · '.join([tr('%d MB', 999), free]), free]
        storage = next((w15(s) for s in chain if w15(s) <= 288), w15(chain[-1]))
        lib_full = cnt.replace('12000', '999') + ' · ' + tr('%d.%d GB', 9, 9)
        lib_cnt = tr('%d episodes', 999)
        tail = ' · ' + max((tr('%dm left', 99), tr('Oct %d', 23)), key=w18) + ' · ' + tr('%d MB', 99)
        worst[loc] = dict(waiting=w18(tr('%d waiting', 40)), paused=w18(tr('%d paused', 99)), shows=max(w18(tr('%d shows', 40)), w18(tr('%d show', 1))), lib=min(w18(lib_full) if w18(lib_full) <= O['PP_DL_TEXT_W'] else 9999, w18(lib_cnt)),
                          storage=storage, heads=max(fnt.width(T('In Progress'), 20), fnt.width(T('Downloaded'), 20)), labels=max(w18(T('Select')), w18(T('Delete Played Episodes')), w18(T('Pause')), w18(T('Resume')), w18(T('Retry')), w18(T('Cancel Download'))), confirm=w18(T('Delete all played episodes?')),
                          toast=min(w18(tr('%d deleted, %s freed', 300).replace('%s', tr('%d GB', 125))), w18(tr('%d deleted', 300))), tail=w18(tail))
        confirms += [w18(T(k)) for k in ('Unsubscribe from this show?', 'Remove the selected downloads?', 'Delete the selected episodes?', 'Unsubscribe from these shows?')]
        shows.append((loc, w18(lib_full) <= O['PP_DL_TEXT_W'], chain.index(next((s for s in chain if w15(s) <= 288), chain[-1]))))
    print('  widest per language (px):', {k: max(v[k] for v in worst.values()) for k in worst['en_US']}, 'in', {k: max(worst, key=lambda loc: worst[loc][k]) for k in worst['en_US']})
    print('  the Library row keeps its size in', [loc for loc, ok, _ in shows if ok], '(the count alone in the others); the storage line falls back to a shorter form in', {loc: k for loc, _, k in shows if k})
    bad = lambda k, room: [(loc, w[k]) for loc, w in worst.items() if w[k] > room]
    expect(not bad('waiting', O['PP_DL_TEXT_W']) and not bad('paused', O['PP_DL_TEXT_W']) and not bad('shows', O['PP_DL_TEXT_W']), f'"N waiting", "N paused" and "N shows" fit the Library row\'s {O["PP_DL_TEXT_W"]} px ({bad("waiting", 214)} {bad("paused", 214)} {bad("shows", 214)})')
    expect(not bad('lib', O['PP_DL_TEXT_W']), f'the Library row\'s count line (with its size where it fits) fits {O["PP_DL_TEXT_W"]} px ({bad("lib", 214)})')
    expect(not bad('storage', 320 - 2 * O['PP_LINE_X']), f'the storage line, or its shortest form, fits {320 - 2 * O["PP_LINE_X"]} px ({bad("storage", 288)})')
    expect(not bad('heads', 320 - 2 * O['PP_SHOWS_X']), 'the section headers fit a line')
    expect(not bad('labels', row), f'the sheet labels fit their {row} px row ({bad("labels", row)})')
    expect(not bad('confirm', max(confirms) + 1), f'the confirm is no longer than the longest confirm of the pages ({bad("confirm", max(confirms) + 1)}; {max(confirms)})')
    expect(not bad('toast', 300), f'the toast, or its short form, fits 300 px with three digits ({bad("toast", 300)})')
    expect(not bad('tail', O['LIST_TEXT_W'] - O['PS_BADGE_CHECK_W']), f'a Downloaded row\'s "· date · size" (a date of this year or what is left, 99 MB) fits its line whole, played check and all ({bad("tail", O["LIST_TEXT_W"] - O["PS_BADGE_CHECK_W"])})')
    print('  a played Downloaded row leaves the show\'s name less than 40 px (so the name is left out and the line is the date and size) in', [loc for loc, w in worst.items() if w['tail'] > O['LIST_TEXT_W'] - O['PS_BADGE_CHECK_W'] - 40])


SECTIONS = [page_tests, scan_tests, inprogress_tests, ring_tests, open_tests, select_tests, played_tests, heads_tests, off_tests, width_tests]

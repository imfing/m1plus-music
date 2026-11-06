"""The Podcasts page's Subscriptions level and OPML (patch/podcasts.c, docs/modules/podcasts.md "Subscriptions and OPML"): the "..." sheet of the Shows level (Subscriptions, Import from Card over
txt and OPML), the level (a row per subscribed show by title: cover, name, the feed's status words; a tap opens the Show page and Back returns to the same place), its sheet (Select Shows, Export OPML),
the select mode with Unsubscribe (a confirm; the Show page's semantics: feed= dropped, files kept, the folder removed when nothing is left, the user's own files kept, never the playing episode, a
write that fails touches nothing), Export OPML (the file, the toast), the empty state, the screen-off rule and the strings in 13 languages measured in the real font. The compiled payload runs under
Unicorn; the card is a dict of paths."""
import importlib.util, os, struct, sys
import xml.etree.ElementTree as ET
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCS = sibling('pcshows')
import mod_icons, pod_i18n, pod_ui   # noqa: E402
PCP, PCN, DL = PCS.PCP, PCS.PCN, sibling('pcdl')
RP, NOW, F, PN = PCS.RP, PCS.NOW, PCS.F, PCS.PN
ROW, SG_MARK, TOP = O['PC_ROW_H'], O['SG_MARK'], O['PP_TITLE_H']   # (the rows start under the large heading)
EXPORT = f'{RP}/subscriptions-export.opml'
SUBS = ['Alpha Show', 'Sub One', 'Sub Two']   # the shows with a feed, by title (bravo has none)


def card(m):
    """The Shows page's card (Alpha Show with two files and a feed, bravo with files and no feed, Sub One and Sub Two with a feed and nothing on the card), plus a .part file of Sub One's and a note of the
    user's in Sub Two."""
    PCS.card(m)
    m.put(f'{RP}/Sub One/a.mp3.part', b'half')
    m.put(f'{RP}/Sub Two/notes.txt', b'mine')
    m.images.update({'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)})


def page(extra=None):
    m = PCS.opened(extra, card)
    m.confirm_yes = True
    return m


def flags(m, n): return PCS.flags(m, n)
def toasts(m): return [PCS.fixed(c[1]) for c in m.calls if c[0] == 'toast']
def title(m): return PCP.title_text(m)
def unlinks(m): return [c[1].replace(RP + '/', '') for c in m.calls if c[0] == 'unlink']


def sheet_rows(m):
    return [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]


def to_subs(m):
    PCS.tap_row(m, 'Subscriptions')   # (the Shows page's Subscriptions row)


def lines(m, off=0):
    """[(title, grey line)] of the rows drawn in a frame, top to bottom."""
    _, texts, styles, _ = PCP.paint(m, off)
    t = {r[1]: PCS.fixed(v) for (v, r), s in zip(texts, styles) if s == 'label_row_title'}
    g = {r[1]: PCS.fixed(v) for (v, r), s in zip(texts, styles) if s == 'label_row_sub'}
    return [(t[y], next((v for k, v in g.items() if k - y == O['LIST_SUB_Y'] - O['LIST_TITLE_Y']), None)) for y in sorted(t)]


def marks(m, off=0):
    bl, *_ = PCP.paint(m, off)
    return sorted((b[2][0], b[2][1], b[0]) for b in bl if tuple(b[2][2:]) == (SG_MARK, SG_MARK))


def row_tap(m, i, **kw): PCP.tap(m, 150, TOP + i * ROW + 10, **kw)


def entry_tests(ctx):
    """The Shows level: the Subscriptions row (a Library row) opens the page; the "..." holds Import from Card only, so it shows only beside an import source."""
    expect = ctx.expect
    m = page()
    PCP.click(m, 'btn_more')
    expect(flags(m, 'btn_more') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np',
           'with subscriptions and nothing to import there is no "..." (Now Playing is the plain disc) and a stray click opens no sheet')
    expect(m.props.get((m.widgets['pg_sh_card'], 'visible'), 0) == 0 and 'subs' not in PCP.SHEET_ROWS, 'the sheet has no Subscriptions row any more')
    # a card with an OPML file in its root: Import from Card in the "..."
    m = page(lambda mm: mm.put('/mnt/mmc/podcasts.opml', b'<opml><body><outline xmlUrl="https://n.example/rss" text="N"/></body></opml>'))
    PCP.click(m, 'btn_more')
    expect(flags(m, 'btn_more') == (1, 1) and sheet_rows(m) == ['import'] and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1', f'an *.opml in the card\'s root makes the "..." appear, with Import from Card alone ({sheet_rows(m)})')
    PCP.click(m, 'pg_sh_scrim')
    # the level
    m = page()
    m.calls = []
    to_subs(m)
    expect(title(m) == 'Subscriptions' and m.props.get((m.widgets['pg_sh_card'], 'visible'), 0) == 0 and flags(m, 'btn_more') == (1, 1)
           and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play', 'the Subscriptions page: its title, the sheet closed, the capsule "..." | Now Playing')
    expect(m.props.get((m.widgets['label_title'], 'visible')) == 0 and flags(m, 'pg_big') == (1, 1) and PCP.title_text(m) == 'Subscriptions' and sorted(r[1] for (t, r), st in zip(*PCP.paint(m)[1:3]) if st == 'label_row_title') == [TOP + i * ROW + O['LIST_TITLE_Y'] for i in range(3)], 'the large heading is the title (the navbar has none) and the rows start under it')
    got = lines(m)
    expect([t for t, _ in got] == SUBS, f'a row per subscribed show, by title; the show with no feed address is not one ({got})')
    expect(dict(got) == {'Alpha Show': 'Updated today', 'Sub One': 'Never refreshed', 'Sub Two': 'Updated 2d ago'}, f'the grey lines are the Shows page\'s captions ({got})')
    expect(m.props.get((m.sv, 'virtual_h')) == TOP + 3 * ROW, 'three rows')
    bl, texts, styles, _ = PCP.paint(m)
    expect(len([b for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]) == 3 and set(styles) <= {'label_row_title', 'label_row_sub'}, 'each with the show\'s cover (the placeholder here), neutral styles only')
    # the feed status words, from the worker's record, on the page's tick
    h = {k: PCS.hash_of(v) for k, v in F.items()}
    PCS.pn_set(m, gen=7, statuses=[(h['alpha'], PN['OK'], 3), (h['one'], PN['NOWIFI'], 0), (h['two'], PN['NOTFEED'], 0)])
    PCS.tick(m)
    expect(dict(lines(m)) == {'Alpha Show': '3 new', 'Sub One': 'No Wi-Fi', 'Sub Two': 'Not a podcast feed'}, f'the status words: new episodes, no Wi-Fi, not a feed ({lines(m)})')
    PCS.pn_set(m, gen=8, statuses=[(h['alpha'], PN['OK'], 0), (h['one'], PN['GONE'], 0), (h['two'], PN['OK'], 0)])
    PCS.tick(m)
    expect(dict(lines(m)) == {'Alpha Show': 'Updated today', 'Sub One': 'Feed not found', 'Sub Two': 'Updated 2d ago'}, f'Feed not found; a refresh that found nothing falls back to the date ({lines(m)})')
    # Back: the Shows level
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Podcasts' and flags(m, 'btn_more') == (0, 0), 'Back returns to the Shows level')
    # the Downloads page is another page: its own rows and its own sheet (Select, Delete Played Episodes), not this one's
    m = page()
    DL.poke_slot(m, 0, 'Sub One', 'x.mp3', 1, seq=1)
    PCS.tick(m)
    PCP.tap_downloads(m)
    PCP.click(m, 'btn_more')
    expect(title(m) == 'Downloads' and 'export' not in sheet_rows(m) and sheet_rows(m) == ['select'], f'the Downloads page has its own sheet ({sheet_rows(m)})')


def tap_tests(ctx):
    """A tap opens the Show page; Back returns to the list where it was; a drag taps nothing."""
    expect = ctx.expect
    m = page()
    to_subs(m)
    row_tap(m, 1, off=80, move=30)
    expect(title(m) == 'Subscriptions', 'a drag is not a tap')
    row_tap(m, 1, off=80)
    expect(title(m) == 'Sub One', f'a tap on the second row opens its Show page ({title(m)})')
    expect(flags(m, 'btn_more') == (1, 1), 'the Show page has its own "..."')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Subscriptions' and m.word(m.sv + O['SC_YOFF']) == 80 and [t for t, _ in lines(m, 80)] == SUBS[1:], f'Back returns to the Subscriptions page, at the offset it left ({lines(m, 80)})')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Podcasts', 'Back again: the Shows level')
    to_subs(m); row_tap(m, 0)
    PCP.click(m, 'btn_more')
    expect('select' in sheet_rows(m) and PCS.fixed(m.wtext.get(m.widgets['pg_sh_select_tx'], '')) == 'Select Episodes', 'the Show page\'s sheet says Select Episodes again (the row is shared)')
    PCP.click(m, 'pg_sh_scrim')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Subscriptions', 'the Show page opened from the Subscriptions page, and Back')
    # a Show page opened from the Shows level goes back to the Shows level, not here
    PCP.click(m, 'btn_return')
    PCP.tap_show(m, 'Sub Two')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Podcasts', 'a Show page opened from the Shows level still goes back to the Shows level')


def sheet_tests(ctx):
    """The Subscriptions sheet: Select Shows and Export OPML in the two-row glass; with nothing to select the "..." is gone."""
    expect = ctx.expect
    m = page()
    to_subs(m)
    PCP.click(m, 'btn_more')
    expect(sheet_rows(m) == ['select', 'export'] and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet2' and flags(m, 'pg_sh_scrim') == (1, 1),
           f'Select Shows and Export OPML on the two-row glass ({sheet_rows(m)})')
    expect(PCS.fixed(m.wtext.get(m.widgets['pg_sh_select_tx'], '')) == 'Select Shows', 'the Select row says Select Shows here')
    ys = {r: [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'pg_sh_{r}']][-1][3] for r in ('select', 'export')}
    expect(ys == {'select': 0, 'export': O['PM_ROW_H']}, f'Select Shows on top ({ys})')
    PCP.click(m, 'btn_return')
    expect(flags(m, 'pg_sh_card') == (0, 0) and title(m) == 'Subscriptions', 'Back closes the sheet first')
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_scrim')
    expect(flags(m, 'pg_sh_card') == (0, 0), 'a tap on the scrim closes it')
    # icons in the build, with pixels
    for n in ('pod_ic_export',):
        im = asset_image(n)
        path = os.path.join(mod_icons.PNG, n + '.png')
        expect(im.size == (20, 20) and im.getchannel('A').getbbox() is not None and os.path.isfile(path) and open(path, 'rb').read() == open(asset_path(n), 'rb').read(), f'{n}.png: 20 px, has pixels, committed and shipped')
    expect(len({asset_image(n).tobytes() for n in ('pod_ic_export', 'pc_ic_import', 'pc_ic_trash')}) == 3, 'different glyphs')
    # the sheet row of the asset
    rows = {r[0]: r for r in pod_ui.PS_SHEET_ROWS}
    expect(rows['export'][1:3] == ('pod_ic_export', 'Export OPML') and rows['select'][2] == 'Select Episodes' and 'subs' not in rows, 'the asset has the Export row with its glyph and label, and no Subscriptions row')


def select_tests(ctx):
    """Select mode: the x, "N Selected", Select All, marks, a bar with Unsubscribe in place of Delete; taps mark; the Select button never shows."""
    expect = ctx.expect
    m = page()
    to_subs(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select')
    expect(title(m) == '0 Selected' and flags(m, 'btn_selall') == (1, 1) and flags(m, 'pg_bar') == (1, 1) and flags(m, 'btn_more') == (0, 0)
           and m.props.get((m.widgets['btn_return'], 'style:normal:icon')) == 'ah_nav_close', 'select mode: the x, 0 Selected, Select All, the bar; no "..."')
    expect(flags(m, 'pg_unsubp') == (1, 1) and flags(m, 'pg_del') == (0, 0), 'the bar has the Unsubscribe pill, not Delete')
    expect(len(marks(m)) == 3, 'a mark on every row')
    PCP.click(m, 'btn_selall')
    expect(title(m) == '3 Selected', 'Select All marks the three')
    PCP.click(m, 'btn_selall')
    expect(title(m) == '0 Selected', 'Select All again: none')
    row_tap(m, 1)
    expect(title(m) == '1 Selected', 'a tap marks a row')
    row_tap(m, 1)
    expect(title(m) == '0 Selected' and title(m) != 'Sub One', 'and unmarks it; it opens no page in select mode')
    PCP.click(m, 'pg_unsubp')
    expect(not [c for c in m.calls if c[0] == 'confirm'] and not unlinks(m), 'Unsubscribe with nothing marked does nothing')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Subscriptions' and flags(m, 'pg_bar') == (0, 0) and flags(m, 'btn_more') == (1, 1) and flags(m, 'pg_unsubp') == (0, 0), 'the x leaves select mode: the "..." is back, the bar and its pill are hidden')
    # the Downloads level's select mode still has Delete
    m = page()
    DL.poke_slot(m, 0, 'Sub One', 'x.mp3', 1, seq=1)
    PCS.tick(m); PCP.tap_downloads(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select')
    expect(flags(m, 'pg_del') == (1, 1) and flags(m, 'pg_unsubp') == (0, 0), 'the Downloads page\'s select mode (from its sheet) keeps its Delete pill')


def shows_on_card(m): return sorted(s['title'] for s in m.shows()[0])


def unsub_tests(ctx):
    """Unsubscribe in every case: No in the confirm, one show with files left, one with nothing left (its own files and folder go, a .part goes), the user's note kept, the playing episode kept, a write that fails,
    everything, the empty state."""
    expect = ctx.expect
    # No: nothing changes, the mode stays
    m = page(); m.confirm_yes = False
    to_subs(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select'); PCP.click(m, 'btn_selall')
    m.calls = []
    PCP.click(m, 'pg_unsubp')
    expect([c[1] for c in m.calls if c[0] == 'confirm'] == ['Unsubscribe from these shows?'] and not unlinks(m) and title(m) == '3 Selected' and b'feed=http' in m.fs[f'{RP}/Sub One/.show'],
           'the confirm asks about these shows; No: nothing is touched, the marks stay')
    # Yes, everything
    m.confirm_yes = True; m.calls = []
    m.track(f'{RP}/Alpha Show/ep1.mp3')   # (the player is on one of Alpha Show's episodes)
    PCP.click(m, 'pg_unsubp')
    alpha = m.fs[f'{RP}/Alpha Show/.show'].decode()
    expect('\nfeed=\n' in alpha and 'feed=http' not in alpha and 'title=Alpha Show' in alpha, f'a show with files: .show loses feed=, the rest stays ({alpha!r})')
    expect(f'{RP}/Alpha Show/ep1.mp3' in m.fs and f'{RP}/Alpha Show/ep2.mp3' in m.fs and not [u for u in unlinks(m) if u.endswith('.mp3')], 'its episode files stay, the playing one too: no audio file is ever deleted')
    expect(f'{RP}/Alpha Show' in m.dirs, 'and its folder')
    expect(not [p for p in m.fs if p.startswith(f'{RP}/Sub One/')] and f'{RP}/Sub One' not in m.dirs and ('rmdir', f'{RP}/Sub One') in m.calls, 'a show with nothing on the card: its .show, its .episodes and its .part are deleted and the folder is removed')
    expect(f'{RP}/Sub Two/notes.txt' in m.fs and f'{RP}/Sub Two/.show' not in m.fs and f'{RP}/Sub Two' in m.dirs, 'the user\'s own note in a folder stays, and so does the folder (rmdir refuses); the show is no subscription')
    expect(title(m) == 'Subscriptions' and flags(m, 'pg_bar') == (0, 0) and lines(m) == [] and 'No subscriptions' in PCP.hint(m),
           'select mode ends and the page is read again: no subscription left, the empty state says so')
    expect(flags(m, 'btn_more') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np', 'with nothing to select or export the "..." is gone, Now Playing is the disc')
    expect(not toasts(m), 'no toast')
    PCP.click(m, 'btn_return')
    expect(title(m) == 'Podcasts' and shows_on_card(m) == ['Alpha Show', 'bravo'] and flags(m, 'btn_more') == (0, 0), f'the Shows level: the local shows (a folder with only the user\'s note is no show), no "..." (nothing to import, no subscription) ({shows_on_card(m)})')
    # one marked: the others stay subscribed; the queued downloads of the show go
    m = page()
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 1, seq=1)
    to_subs(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select')
    row_tap(m, 1)
    expect(title(m) == '1 Selected', 'Sub One marked')
    m.calls = []
    PCP.click(m, 'pg_unsubp')
    expect([t for t, _ in lines(m)] == ['Alpha Show', 'Sub Two'] and b'feed=http' in m.fs[f'{RP}/Alpha Show/.show'] and f'{RP}/Sub One/.show' not in m.fs, f'only the marked show is unsubscribed ({lines(m)})')
    expect(DL.fn(m, 'pn_dl_count') == 0 or m.word(DL.pn_at(DL.DCANCEL)) or DL.state(m, 'a.mp3', 'Sub One')[0] == 0, 'its queued download is taken out of the queue')
    expect(title(m) == 'Subscriptions' and flags(m, 'btn_more') == (1, 1), 'the page stays, the "..." too (two subscriptions left)')
    # a .show that cannot be written: said, nothing else touched, still subscribed
    m = page()
    m.fail.add(('open', f'{RP}/Sub One/.show.tmp'))
    to_subs(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select'); PCP.click(m, 'btn_selall'); m.calls = []
    PCP.click(m, 'pg_unsubp')
    expect(toasts(m) == ['Storage unavailable'] and b'feed=http' in m.fs[f'{RP}/Sub One/.show'] and f'{RP}/Sub One/a.mp3.part' in m.fs and 'Sub One' in [t for t, _ in lines(m)],
           'a .show that cannot be written: said once, that show is untouched (its .part stays, it stays subscribed); the others went')
    expect([t for t, _ in lines(m)] == ['Sub One'] and b'feed=' not in m.fs[f'{RP}/Alpha Show/.show'].replace(b'feed=\n', b''), f'the others were unsubscribed ({lines(m)})')
    # a refresh running: nothing
    m = page()
    to_subs(m)
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select'); PCP.click(m, 'btn_selall')
    m.setword(DL.pn_at(0), 1)   # (the worker's busy word)
    m.calls = []
    PCP.click(m, 'pg_unsubp')
    expect(not [c for c in m.calls if c[0] == 'confirm'] and b'feed=http' in m.fs[f'{RP}/Sub One/.show'], 'while a refresh runs Unsubscribe does nothing (the refresh dialog is modal anyway)')


def export_tests(ctx):
    """Export OPML from the sheet: the file for the subscriptions, a toast with the count (and the file name where it fits), a failed write says so."""
    expect = ctx.expect
    m = page()
    to_subs(m); m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_export')
    raw = m.fs.get(EXPORT)
    outs = [(o.get('text'), o.get('xmlUrl')) for o in ET.fromstring(raw).iter('outline')] if raw else None
    expect(outs == [('Alpha Show', F['alpha']), ('Sub One', F['one']), ('Sub Two', F['two'])], f'subscriptions-export.opml in the Podcasts folder: the three subscriptions by title ({outs})')
    expect(toasts(m) == ['Exported 3 shows'] and flags(m, 'pg_sh_card') == (0, 0), f'the toast: "Exported 3 shows" ({toasts(m)})')
    expect(not [p for p in m.fs if p.endswith('.tmp')], 'no temp file left')
    # one show: the singular
    m = page(lambda mm: [mm.fs.pop(f'{RP}/{d}/.show') for d in ('Sub One', 'Sub Two')])
    to_subs(m); m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_export')
    expect(toasts(m)[0].startswith('Exported 1 show') and not toasts(m)[0].startswith('Exported 1 shows'), f'one show: "Exported 1 show" ({toasts(m)})')
    # a failed write: said, no file
    m = page()
    m.fail.add(('open', f'{RP}/.subscriptions-export.opml.tmp'))
    to_subs(m); m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_export')
    expect(toasts(m) == ['Storage unavailable'] and EXPORT not in m.fs, 'a card that cannot be written: "Storage unavailable", no file')
    # exported again: replaced
    m = page()
    to_subs(m)
    for _ in range(2): PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_export')
    expect(len(ET.fromstring(m.fs[EXPORT]).findall('.//outline')) == 3, 'exported twice: one file, replaced')
    # what was exported imports again: a card with only the export in its root gives the same subscriptions
    exported = m.fs[EXPORT]
    m2 = PCN.machine()
    m2.put('/mnt/mmc/back.opml', exported)
    shows, arr = m2.shows()
    n = m2.call(PSYMS['pn_import'], a0=m2.cstr(RP), a1=arr, a2=0, count=1 << 40)
    expect(n == 3 and sorted(s['feed'] for s in m2.shows()[0]) == sorted([F['alpha'], F['one'], F['two']]), 'the export imports back on another card: the same three subscriptions')


def import_tests(ctx):
    """Import from Card through the sheet with txt and OPML together: "N added", the dialog, the renamed file, the "..." after."""
    expect = ctx.expect
    WSJ = open(os.path.join(PCS.FEEDS, 'wsj-3items.xml'), 'rb').read()

    def extra(mm):
        mm.put(f'{RP}/subscriptions.txt', f'{F["three"]}\n'.encode())
        mm.put('/mnt/mmc/more.opml', b'<opml><body><outline type="rss" text="Four" xmlUrl="https://f.example/four"/><outline xmlUrl="https://f.example/one"/></body></opml>')
    m = page(extra)
    PCP.click(m, 'btn_more')
    expect(sheet_rows(m) == ['import'], 'subscriptions.txt and an OPML file: Import from Card')
    m.curl_site = lambda url, o: {'body': WSJ}
    m.thread = None; m.calls = []
    PCP.click(m, 'pg_sh_import')
    expect(toasts(m) == ['2 added'] and m.thread is not None and flags(m, 'pod_pd_card') == (1, 1), 'both sources: 2 added (one of the outlines was subscribed already), the dialog opens')
    expect('/mnt/mmc/more.opml' not in m.fs and '/mnt/mmc/more.opml.imported' in m.fs and f'{RP}/subscriptions.txt' in m.fs, 'the OPML file is renamed .imported, subscriptions.txt stays')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    PCP.click(m, 'btn_more')
    expect(sheet_rows(m) == ['import'], 'subscriptions.txt is still there: Import from Card stays (it has nothing new)')
    m.thread = None; m.calls = []
    PCP.click(m, 'pg_sh_import')
    expect(toasts(m) == ['Nothing new to import'] and m.thread is None, 'importing again: nothing new')
    PCP.click(m, 'pg_sh_scrim'); to_subs(m)
    expect(len(lines(m)) == 5 and [t for t, _ in lines(m)].count('WSJ Minute Briefing') == 3, f'the Subscriptions page lists the imported shows too (named by the refresh: {lines(m)})')


def off_tests(ctx):
    """No visual work while the screen is off: the rows are read again only by a lit tick; the loader does nothing."""
    expect = ctx.expect
    m = page()
    to_subs(m)
    before = lines(m)
    h = {k: PCS.hash_of(v) for k, v in F.items()}
    m.screen(False); m.calls = []
    PCS.pn_set(m, gen=11, statuses=[(h['one'], PN['NOWIFI'], 0)])
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(lines(m) == before and not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_tr_text', 'widget_set_text_utf8', 'widget_resize', 'widget_set_visible')], 'screen off: the rows are not read again, no widget work')
    m.calls = []
    m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'widget_invalidate_force')], 'the cover loader does nothing in the dark')
    PCS.tick(m)
    expect(dict(lines(m))['Sub One'] == 'No Wi-Fi', 'the first lit tick reads the status again')


def width_tests(ctx):
    """The new strings in the 13 languages, measured in the real font: the sheet's labels (a 248 px row, no value), the navbar title, the empty state, the Unsubscribe pill (at 18 px or the 16 px a pill drops
    to), the toast (a count of two digits) and the confirm against the longest confirm that exists."""
    expect = ctx.expect
    fnt = PCS.sw().font()
    worst, confirms = {}, []
    row = O['PS_SHEET_VALUE_R'] - O['PS_SHEET_TEXT_X']
    pill_room = O['PL_BAR_PILL_W'] - (O['SG_PILL_H'] - O['SG_PILL_GLYPH']) // 2 - O['SG_PILL_GLYPH'] - O['SG_PILL_GAP']
    full_fits = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, n=None, t=t: (pod_i18n.TEXT[key][t].replace('%d', str(n)) if n is not None else pod_i18n.TEXT[key][t])
        w18 = lambda s: fnt.width(s, 18)
        worst[loc] = dict(labels=max(w18(tr(k)) for k in ('Subscriptions', 'Export OPML', 'Select Shows')), title=fnt.width(tr('Subscriptions'), 22), empty=w18(tr('No subscriptions')),
                          pill=min(w18(tr('Unsubscribe')), fnt.width(tr('Unsubscribe'), O['SG_PILL_PX_SMALL'])), toast=max(w18(tr('Exported %d shows', 40)), w18(tr('Exported %d show', 1))),
                          confirm=w18(tr('Unsubscribe from these shows?')))
        confirms += [w18(tr(k)) for k in ('Unsubscribe from this show?', 'Remove the selected downloads?', 'Delete the selected episodes?')]
        full_fits.append((loc, w18(tr('Exported %d shows', 40) + ': subscriptions-export.opml')))
    print('  widest per language (px):', {k: max(v[k] for v in worst.values()) for k in worst['en_US']}, 'in', {k: max(worst, key=lambda loc: worst[loc][k]) for k in worst['en_US']},
          '; with the file name (one line) at least', min(w for _, w in full_fits), 'px; the longest existing confirm', max(confirms))
    bad = lambda k, room: [(loc, w[k]) for loc, w in worst.items() if w[k] > room]
    expect(not bad('labels', row), f'the sheet labels fit their {row} px row ({bad("labels", row)})')
    room = O['NAV_VIEW_X'] - O['NAV_TITLE_X']
    expect(not bad('title', room), f'the title fits the navbar\'s room of {room} px ({bad("title", room)})')
    expect(not bad('empty', 280), f'the empty state fits one line ({bad("empty", 280)})')
    expect(not bad('pill', pill_room), f'Unsubscribe fits its pill beside the glyph, at most dropping to 16 px ({bad("pill", pill_room)}; room {pill_room})')
    expect(not bad('toast', 300), f'the toast fits 300 px with two digits ({bad("toast", 300)})')
    expect(min(w for _, w in full_fits) > 300, 'the file name does not fit the one-line toast in any language, which is why the toast has the count only')
    expect(not bad('confirm', max(confirms) + 1), f'the confirm is no longer than the longest confirm of the page ({bad("confirm", max(confirms) + 1)})')


SECTIONS = [entry_tests, tap_tests, sheet_tests, select_tests, unsub_tests, export_tests, import_tests, off_tests, width_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

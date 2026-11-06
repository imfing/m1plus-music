"""The refresh dialog of the Podcasts page (patch/podcasts.c pg_dlg_*, patch/pcnet.c's progress and cancel, tools/pod_ui.py podcasts_dialog; docs/modules/podcasts.md "Feeds"): it opens when
Refresh All or Import starts the worker, shows the show, "n of m" and the bar from the status record the worker writes, Cancel and Back stop the worker (between shows and in the middle of
a transfer, through libcurl's transfer-info callback), and it closes itself, with one line of summary, when the worker has stopped. The compiled payload runs under Unicorn."""
import importlib.util, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PF = sibling('pcshows')
PCP, PCN = PF.PCP, PF.PCN
F, RP, PN, flags, toasts, hash_of = PF.F, PF.RP, PF.PN, PF.flags, PF.toasts, PF.hash_of
RET_REPEAT = 8
FEEDS = PF.FEEDS
NOW = PF.NOW


def pn_at(off): return PSYMS['pn'] + off


# the status record's new fields follow its statuses (patch/pcnet.c): part, base, span, cancel, stopped, ok, fail
AFTER = 20 + 12 * O['PC_MAX_SHOWS']
PART, BASE, SPAN, CANCEL, STOPPED, OK, FAIL = (pn_at(AFTER + 4 * i) for i in range(7))


def dlg_tick(m):
    m.screen(True)
    return m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)


def text_of(m, name):
    t = [c for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[name]]
    return t[-1][2] if t else None


def fill_w(m):
    w = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['pod_pd_fill']]
    return w[-1][2:] if w else None


def started(m, sites=None):
    """The Shows level, the refresh line tapped (Refresh All): the worker is waiting in m.thread."""
    WSJ = open(os.path.join(FEEDS, 'wsj-3items.xml'), 'rb').read()
    HEAD = open(os.path.join(FEEDS, 'headlines-3items.xml'), 'rb').read()
    m.curl_site = sites or (lambda url, o: {'body': WSJ if url == F['alpha'] else HEAD if url == F['one'] else b'<html></html>'})
    m.thread = None
    m.calls = []
    PCP.tap_line(m)
    return m


def work(m): m.call(m.thread[0], a0=m.thread[1], count=1 << 40)


def run(ctx):
    expect = ctx.expect
    WSJ = open(os.path.join(FEEDS, 'wsj-3items.xml'), 'rb').read()
    HEAD = open(os.path.join(FEEDS, 'headlines-3items.xml'), 'rb').read()
    h = {k: hash_of(v) for k, v in F.items()}

    # 1. It opens with Refresh All, modal, and shows the record
    m = PF.opened()
    started(m)
    expect(m.thread is not None and flags(m, 'pod_pd_scrim') == (1, 1) and flags(m, 'pod_pd_card') == (1, 1) and flags(m, 'pod_pd_cancel') == (1, 1),
           'Refresh All starts the worker and opens the dialog: the scrim (it takes every touch) and the card shown and sensitive, the Cancel row live')
    expect(text_of(m, 'pod_pd_count') == '1 of 3' and fill_w(m) == (1, 6) and ('timer_add', PSYMS['pg_dlg_tick'], 200) in m.calls, '"1 of 3", the fill at its minimum, a 200 ms page timer')
    m.setword(PART, 500)
    PF.pn_set(m, busy=1, done=1, total=3, cur=h['one'])
    m.calls = []
    r = dlg_tick(m)
    expect(r == RET_REPEAT and text_of(m, 'pod_pd_count') == '2 of 3' and text_of(m, 'pod_pd_name') == 'Sub One' and fill_w(m) == (120, 6),
           f'the record reaches the dialog: show 2 of 3, its name, the bar at (1 show + half of one) of 3 = half of 240 px ({text_of(m, "pod_pd_count")}, {text_of(m, "pod_pd_name")}, {fill_w(m)})')
    m.calls = []
    m.setword(PART, 900); PF.pn_set(m, done=2, cur=h['two'])
    dlg_tick(m)
    expect(text_of(m, 'pod_pd_name') == 'Sub Two' and text_of(m, 'pod_pd_count') == '3 of 3' and fill_w(m) == (240 * ((2 * 1000 + 900) // 3) // 1000, 6), 'the third show, the bar at 2.9 of 3')
    m.calls = []
    dlg_tick(m)
    expect([c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_resize')] == [] or text_of(m, 'pod_pd_name') is None, 'a tick with nothing new changes no name and no width')

    # 1b. A show finishing under the dialog does not rescan the folders (the progress bar would stutter); the close reads them once
    m = PF.opened()
    started(m)
    for g in (1, 2, 3):
        PF.pn_set(m, busy=1, gen=m.word(PSYMS['pn'] + 12) + 1)
        m.calls = []
        PF.tick(m)
        expect(not [c for c in m.calls if c[0] == 'opendir'], f'worker generation moved ({g}) while the dialog is up: the page tick scans no folder')
    PF.pn_set(m, busy=0)
    m.calls = []
    dlg_tick(m)
    scans = [c for c in m.calls if c[0] == 'opendir']
    m.calls = []
    PF.pn_set(m, gen=m.word(PSYMS['pn'] + 12) + 1)
    PF.tick(m)   # the same reload with no dialog: what one scan costs
    expect(scans and scans == [c for c in m.calls if c[0] == 'opendir'] and flags(m, 'pod_pd_card') == (0, 0), 'the dialog closing reads the folders once (as much as one reload of the page)')
    m.calls = []
    PF.tick(m)
    expect(not [c for c in m.calls if c[0] == 'opendir'], 'and the next page tick has nothing to reload (the generation was taken)')

    # 2. The worker ends: the dialog closes by itself with the summary
    for label, site, line in (('two feeds and an HTML page', None, '2 updated, 1 failed'),
                              ('three feeds', lambda url, o: {'body': HEAD if url == F['one'] else WSJ}, '3 updated'),
                              ('nothing reachable', lambda url, o: {'rc': 6}, '3 failed')):
        m = PF.opened()
        started(m, site)
        work(m)
        expect(flags(m, 'pod_pd_card') == (1, 1), f'{label}: the dialog stays until its own timer sees the worker stopped')
        m.calls = []
        r = dlg_tick(m)
        expect(r == 0 and flags(m, 'pod_pd_card') == (0, 0) and flags(m, 'pod_pd_scrim') == (0, 0) and toasts(m) == [line], f'{label}: closes (hidden and insensitive), one line: "{line}" ({toasts(m)})')
    expect("Can't connect" in [t for t, _ in PCP.drawn(m, 120, style='label_ps_gsub')], 'the shows\' captions keep their per-feed errors (the dialog only summarises)')

    # 3. Import opens it too
    sub_txt = f'{RP}/subscriptions.txt'
    m = PF.opened(lambda mm: mm.put(sub_txt, f'{F["three"]}\n'.encode()))
    m.curl_site = lambda url, o: {'body': WSJ}
    m.thread = None
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_import')   # Import from Card
    expect(m.thread is not None and flags(m, 'pod_pd_card') == (1, 1) and text_of(m, 'pod_pd_count') == '1 of 2', 'Import: the new show and Sub One (never refreshed) are refreshed and the dialog is up ("1 of 2")')
    work(m)
    dlg_tick(m)
    expect(flags(m, 'pod_pd_card') == (0, 0) and toasts(m)[-1] == '2 updated', 'and it closes with "2 updated"')

    # 4. No second job while one runs
    m = PF.opened()
    started(m)
    m.calls = []
    PCP.tap_line(m)
    PF.pn_set(m, busy=1)
    PCP.tap_line(m)
    expect('pthread_create' not in m.names() and toasts(m) == [], 'a tap on the refresh line while the worker runs starts nothing (the scrim keeps the real touch away as well)')

    # 5. Cancel
    m = PF.opened()
    started(m)
    m.calls = []
    PCP.click(m, 'pod_pd_cancel')
    expect(m.word(CANCEL) == 1 and flags(m, 'pod_pd_cancel') == (1, 0) and text_of(m, 'pod_pd_count') == m.tr('Cancelling…') and flags(m, 'pod_pd_card') == (1, 1),
           'Cancel sets the flag, the row goes dead, the line says "Cancelling…"; the dialog stays while the worker is alive')
    seen = []
    m.curl_site = lambda url, o: (seen.append(url), {'body': WSJ})[1]
    work(m)
    expect(seen == [] and m.call(PSYMS['pn_busy'], count=2000) == 0 and PF.PCN.status(m, F['alpha']) is None, 'cancelled before the first show: no request, no status')
    m.calls = []
    dlg_tick(m)
    expect(flags(m, 'pod_pd_card') == (0, 0) and toasts(m) == ['Cancelled'], f'the worker has stopped: the dialog closes, "Cancelled" ({toasts(m)})')
    # in the middle of a feed's transfer: aborted at once, nothing written
    m = PF.opened()
    before = dict(m.fs)
    cancel_at = []
    def sites(url, o):
        if url == F['one']: return {'body': WSJ, 'chunk': 4000, 'xfer': lambda u, sent, total: m.setword(CANCEL, 1) if sent >= 8000 else None}   # (Sub One has the newest episode: the grid's, and so the refresh's, first)
        cancel_at.append(url)
        return {'body': HEAD}
    started(m, sites)
    work(m)
    calls = list(m.calls)
    expect(cancel_at == [] and m.fs == before and PCN.status(m, F['one']) is None and 'curl_perform' in [c[0] for c in calls],
           'Cancel in the middle of the first feed: libcurl\'s callback aborted the transfer (42), nothing was written, the show keeps its status, no other show was fetched')
    expect([c for c in calls if c[0] == 'curl_perform'][0][2] == 42, 'the transfer ended with CURLE_ABORTED_BY_CALLBACK')
    m.calls = []
    dlg_tick(m)
    expect(toasts(m) == ['Cancelled'] and m.call(PSYMS['pn_busy'], count=2000) == 0, 'closed with "Cancelled"')
    # in the cover's transfer: the feed is done and counts, no further show starts
    m = PF.opened()
    urls = []
    def sites2(url, o):
        urls.append(url)
        if url == F['one']: return {'body': WSJ}
        if url == F['alpha']: return {'body': HEAD}
        return {'body': b'x' * 30000, 'chunk': 5000, 'xfer': lambda u, sent, total: m.setword(CANCEL, 1) if sent >= 10000 else None}
    started(m, sites2)
    work(m)
    expect(len(urls) == 2 and urls[0] == F['one'] and PCN.status(m, F['one']) == (PN['OK'], 3) and PCN.status(m, F['alpha']) is None and PCN.status(m, F['two']) is None,
           f'Cancel in the picture\'s transfer of the first show (Sub One has no cover picture; Alpha Show has): its feed is complete and OK, the others were not started ({urls})')
    m.calls = []
    dlg_tick(m)
    expect(toasts(m) == ['Cancelled, 1 updated'] and not [p for p in m.fs if '.cover' in p or '/Sub One/cover' in p], 'closed with "Cancelled, 1 updated", no cover file')

    # 6. Back is Cancel, and so is leaving the page
    m = PF.opened()
    started(m)
    m.calls = []
    PCP.click(m, 'btn_return')
    expect(m.word(CANCEL) == 1 and 'navigator_back' not in m.names() and flags(m, 'pod_pd_card') == (1, 1), 'Back with the dialog up is Cancel: the flag, the page and the dialog stay')
    m = PF.opened()
    started(m)
    fn, ctx_ = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(m.word(CANCEL) == 1, 'the page destroyed with the dialog up (the hardware Back key): the worker is told to stop')
    m = PF.opened()
    started(m)
    m.calls = []
    fn, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(m.word(CANCEL) == 0 and flags(m, 'pod_pd_card') == (1, 1), 'another page in front: the refresh goes on, the dialog is still there when the page comes back')

    # 7. The record without a worker of ours: progress, scaled counts, the length unknown
    m = PF.opened()
    parts = []
    def sites3(url, o):
        if url == F['alpha']:
            return {'body': WSJ, 'chunk': 1000, 'length': len(WSJ), 'xfer': lambda u, sent, total: parts.append((sent, m.word(PART)))}
        return {'rc': 6}
    started(m, sites3)
    work(m)
    ps = [p for _, p in parts]
    expect(len(parts) > 3 and ps == sorted(ps) and ps[0] == 0 and 0 < ps[-1] <= 900, f'the feed\'s bytes move the show\'s progress, never back, within its nine tenths ({ps})')
    m = PF.opened()
    seen_opts = []
    started(m, lambda url, o: (seen_opts.append(dict(o)), {'rc': 6})[1])
    work(m)
    o = seen_opts[0]
    expect(o[43] == 0 and o[20219] == PSYMS['pn_xfer'] and o[10057] == 0, 'the request asks for the transfer-info callback (NOPROGRESS off): that is all libcurl needs to abort, no new import')
    m = PF.opened()
    parts = []
    started(m, lambda url, o: {'body': WSJ, 'chunk': 6000, 'length': 0, 'xfer': lambda u, sent, total: parts.append(m.word(PART))} if url == F['alpha'] else {'rc': 6})
    work(m)
    expect(parts and set(parts) == {0}, 'a feed whose length the server did not give: the show moves in one step (900 when the feed is in, 1000 when the show is done)')
    m = PF.opened()
    big_total = []
    started(m, lambda url, o: {'body': WSJ, 'chunk': 60000, 'length': 5 << 30, 'xfer': lambda u, sent, total: big_total.append(m.word(PART))} if url == F['alpha'] else {'rc': 6})
    work(m)
    expect(all(p <= 900 for p in big_total), 'a length over 4 GB is scaled, not wrapped (no 64-bit division in the payload)')

    # 8. The screen off: no visual work, and the dialog is right when the screen comes back
    m = PF.opened()
    started(m)
    work(m)
    m.calls = []
    m.screen(False)
    r = m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    visual = [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_resize', 'widget_set_visible', 'toast', 'widget_invalidate_force')]
    expect(r == 0 and visual == [] and flags(m, 'pod_pd_card') == (1, 1), 'screen off: the dialog timer stops without touching a widget (the worker may well have ended meanwhile)')
    m.calls = []
    m.screen(True)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(('timer_add', PSYMS['pg_dlg_tick'], 200) in m.calls, 'the screen is back: the page\'s 1 s tick starts the dialog timer again')
    m.calls = []
    r = m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(flags(m, 'pod_pd_card') == (0, 0) and len(toasts(m)) == 1, 'and its first tick closes the dialog with the summary')

    # 9. The asset
    import awtk_ui
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_podcasts.bin'), 'rb').read())
    scrim, card = tree.find('pod_pd_scrim'), tree.find('pod_pd_card')
    expect(all(w.get('visible') == 'false' and w.get('sensitive') == 'false' for w in (scrim, card)) and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450)
           and (card.w, card.h, card.x, card.y) == (280, 200, 20, 125), 'the scrim covers the client area, the 280 x 200 card is centred, both start hidden and insensitive')
    expect(card.get('style:normal:bg_image') == 'pl_glass' and card.get('style:normal:bg_image_draw_type') == 'patch3_x', 'the card is the Playlists menu\'s glass')
    kids = {c.name: c for c in card.children}
    expect(list(kids) == ['pod_pd_title', 'pod_pd_name', 'pod_pd_track', 'pod_pd_fill', 'pod_pd_count', 'pod_pd_cancel'], f'the card: title, name, bar, count, Cancel ({list(kids)})')
    expect(all(kids[n].get('sensitive') == 'false' for n in kids if n != 'pod_pd_cancel') and kids['pod_pd_cancel'].get('enable') == 'true', 'the texts and the bar are insensitive; only the Cancel row takes touches')
    expect((kids['pod_pd_cancel'].y, kids['pod_pd_cancel'].h, kids['pod_pd_cancel'].w) == (150, 50, 280) and kids['pod_pd_cancel'].get('tr_text') == 'Cancel'
           and kids['pod_pd_title'].get('tr_text') == 'Refreshing Podcasts', 'the Cancel row fills the card\'s last 50 px; the title is a key')
    expect((kids['pod_pd_track'].x, kids['pod_pd_track'].w, kids['pod_pd_track'].h) == (20, 240, 6) and (kids['pod_pd_fill'].x, kids['pod_pd_fill'].y) == (20, kids['pod_pd_track'].y), 'the track and the fill share a place; the track is 240 x 6')

    # 10. The strings fit in every language (the shipped font)
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    worst = {}
    for key, px in (('Refreshing Podcasts', 20), ('Cancelling…', 15), ('Cancel', 18)):
        ws = [(round(StbText(font, px).layout(built[loc][key])[1]), loc) for loc in pod_i18n.LOCALES]
        worst[key] = max(ws)
    for key in ('%d of %d',):
        ws = [(round(StbText(font, 15).layout(built[loc][key].replace('%d', '40', 1).replace('%d', '40', 1))[1]), loc) for loc in pod_i18n.LOCALES]
        worst[key] = max(ws)
    print('  widest dialog texts (px, room 240):', worst)
    expect(all(w <= 240 for w, _ in worst.values()), f'the title, "Cancelling…", "40 of 40" and Cancel fit the 240 px of the card in all 13 languages ({worst})')
    summaries = []
    for loc in pod_i18n.LOCALES:
        for key, n in (('%d updated, %d failed', 2), ('Cancelled, %d updated', 1), ('%d updated', 1), ('%d failed', 1)):
            t = built[loc][key].replace('%d', '40')
            summaries.append((round(StbText(font, 20).layout(t)[1]), loc, key))
    print('  widest summary line (px at 20 px, the stock message box has no fixed room):', max(summaries))

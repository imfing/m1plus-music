"""The boot guard and the launcher: M1+ Music as Home."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


# ======================= Home guard and launcher (patch/home.c) =======================
RUN, BAD, START = '/mnt/data/m1plus-run', '/mnt/data/m1plus-bad', '/mnt/data/m1plus-start'
KILL_SD, KILL_DATA, LOG_ON, LOG = '/mnt/mmc/m1plus-off', '/mnt/data/m1plus-off', '/mnt/mmc/m1plus-log', '/mnt/mmc/m1plus.log'
CLEAR_MS = 5000
# patch/home.h (V2.1jA, docs/ui.md): the menu opens as soon as Home is up
OPEN_FIRST_MS, OPEN_MS, RETRY_MS, MAX_TRIES = 10, 10, 50, 100
GRID = 'app_gesture'     # patch/home.h GRID_ROOT
HOME_WIN = 0x23000000


def boot(m, win=HOME_WIN, ret=0):
    m.init_ret = ret
    return m.call(PSYMS['m1plus_home_init'], a0=win, a1=0x55, count=3000000)


def writes_atomically(m, path, tmp, data):
    """open(tmp, WRONLY|CREAT|TRUNC), write, fsync(tmp), close, rename(tmp, path); the file holds data."""
    seq = [c[:2] if c[0] != 'rename' else c for c in m.calls if c[0] in ('open', 'write', 'fsync', 'close', 'rename')]
    flat = [c for c in seq if c[1] == tmp]
    want = [('open', tmp), ('write', tmp), ('fsync', tmp), ('close', tmp), ('rename', tmp, path)]
    return flat == want and ('write', tmp, data) in m.calls and m.fs.get(path) == data


SETTINGS, HOMESET = pod_pages.SETTINGS_PAGE, pod_pages.DEVELOPER_PAGE
NAVBAR, LISTVIEW, SCROLLVIEW, SCROLLBAR = 'navigationbar_view', 'pod_listview', 'pod_scrollview', 'scroll_bar_m'
ICON_STYLE = 'home_m1plus_style'
ICON_NAME = str(pod_pages.HOME_ENTRY)


def menu_machine(page, icons=(6, 6, 5)):
    """A machine with the pod menu's widgets (and the Settings page's: the Start-in row lives there) and the
    stock Home grid (home_sview > pages of 6, 6, 5 icons, as English Home)."""
    m = Machine()
    names = ['btn_return', 'btn_backtoplayer', 'label_info'] + [f'pod_row{i}' for i in range(len(page.rows))]
    names += ['label_title', GRID, NAVBAR, LISTVIEW, SCROLLVIEW, SCROLLBAR, 'home_sview', 'home_sindicator']
    names += [f'pod_switch{i}' for i, r in enumerate(HOMESET.rows) if r.action in pod_pages.SWITCH_ACTIONS]   # the Home Screen page's switch image
    m.widgets = {n: 0x30000000 + i for i, n in enumerate(names)}
    m.widgets[SCROLLVIEW] = m.alloc(0x180)   # real memory: menu_arrange reads the scroll_view's vtable word and paint hook
    m.types[m.widgets['home_sview']] = 'slide_view'
    for n in (LISTVIEW, SCROLLVIEW, SCROLLBAR): m.types[m.widgets[n]] = n
    m.props[(m.widgets[SCROLLVIEW], 'w')], m.props[(m.widgets[SCROLLBAR], 'w')] = 310, 10
    m.children[m.widgets['home_sview']] = pages = []
    for n in icons:
        p = m.alloc(0x80); m.types[p] = 'view'; pages.append(p)
        m.children[p] = [m.alloc(0x80) for _ in range(n)]
    # the real rows of the built assets, children in their real order and types (the icon image comes
    # first since V2.1iM: the label is not child 0, which is how "Start in" got a ghost text)
    for pg in (page, SETTINGS):
        ui = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui', pg.key + '.bin'), 'rb').read())
        for i, r in enumerate(pg.rows):
            if pg is page and i < len(SETTINGS.rows): continue   # pod_rowN of the Settings page wins for N < 4
            row = next(w for w in ui.walk() if w.name == f'pod_row{i}')
            kids = [m.alloc(0x80) for _ in row.children]
            for k, c in zip(kids, row.children): m.types[k] = c.type
            m.children[m.widgets[f'pod_row{i}']] = kids
    return m


def switch_image(m, i): return m.widgets[f'pod_switch{i}']


def switch_shows(m, i):
    """The state of the Home Screen page's switch image i, from the last image_base_set_image call on it (None: untouched)."""
    img = [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == switch_image(m, i)]
    return {'sset_on': True, 'sset_off': False}[img[-1]] if img else None


def home_tests(expect, page):
    ALLOWED = {'stock_init_resume', 'access', 'open', 'write', 'fsync', 'close', 'rename', 'unlink', 'read', 'timer_add', 'widget_on'}
    ALLOWED |= {'widget_lookup', 'widget_set_visible', 'widget_set_sensitive'}   # the grid is hidden (after the marker)
    ALLOWED |= {'locale_info_on'}   # patch/fontregion.c fr_boot: the language and theme change handlers (test/pod/fontregion.py)
    clear_cb, open_cb, fg_cb = PSYMS['hm_clear'], PSYMS.get('hm_open'), PSYMS.get('hm_fg')

    # -- the hook itself: two words over home_page_init's PIC prologue, the third and the rest untouched
    d = open(DEMO, 'rb').read()
    off = pod.fileoff(bytearray(d), pod.HOME_INIT)
    w0, w1, w2, w3 = struct.unpack_from('<IIII', d, off)
    expect(w0 == pod.j(PSYMS['m1plus_home_init']) and w1 == 0 and w2 == pod.HOME_INIT_PROLOGUE[2] and w3 == 0x108000f0,
           'home_page_init starts with j m1plus_home_init; nop, and its 3rd and 4th stock words are intact')

    # -- 1. clean boot: stock first, then marker (synced temp + rename), the clear timer, nothing else
    m = Machine(); r = boot(m, ret=0)
    expect(m.calls[0] == ('stock_init_resume', HOME_WIN, 0x55), 'the stock home_page_init runs first, with its arguments')
    expect(r == 0, 'the hook returns the stock result')
    expect(m.fs.get(RUN) == b'1\n' and writes_atomically(m, RUN, RUN + '.tmp', b'1\n'),
           'a clean boot writes the marker through a temp file, fsync and rename')
    expect(('fsync', '/mnt/data') in m.calls, 'and fsyncs the directory')
    expect(m.timers[:1] == [(clear_cb, CLEAR_MS)], f'the marker is cleared by a {CLEAR_MS} ms UI timer ({m.timers})')
    expect(set(m.names()) <= ALLOWED, f'the boot path calls only {sorted(ALLOWED)} (extra: {sorted(set(m.names()) - ALLOWED)})')
    expect(not any(n.startswith('window') or n.startswith('widget_set') or n.startswith('navigator') or n == 'on_backtoplayer_onclick'
                   for n in m.names()), 'no window is opened, shown, hidden or navigated at boot by the guard')   # (this Machine has no widgets)
    expect(m.timers == [(clear_cb, CLEAR_MS), (open_cb, OPEN_FIRST_MS)], f'also the first open timer ({m.timers})')
    wo = [c for c in m.calls if c[0] == 'widget_on' and c[1] != m.wm]   # (fr_boot's theme handler is on the window manager)
    expect(wo == [('widget_on', HOME_WIN, 0x12d, fg_cb, HOME_WIN)], f'one Home-foreground handler on the Home window ({wo})')
    expect([c[1:3] for c in m.calls if c[0] == 'widget_on' and c[1] == m.wm] == [(m.wm, 0x14a)] and len([c for c in m.calls if c[0] == 'locale_info_on']) == 1,
           'the ready path runs fr_boot: one theme handler on the window manager, one locale handler')
    # a stock init that fails leaves everything stock
    m = Machine(); boot(m, ret=0x10)
    expect(not m.fs and not m.timers and m.names() == ['stock_init_resume'], 'a stock init failure: no marker, no timer, no access')
    m = Machine(); boot(m, win=0)
    expect(not m.fs and not m.timers, 'a null window: nothing is armed')
    # the trampoline reaches the stock function past its prologue with $gp restored
    m = Machine(); gp = []
    m.u.hook_add(UC_HOOK_CODE, lambda u, a, s, _: gp.append(u.reg_read(UC_MIPS_REG_GP)), begin=pod.HOME_INIT + 12, end=pod.HOME_INIT + 12)
    boot(m)
    expect(gp == [pod.GP], f'the trampoline restores $gp ({gp})')

    # -- 2. the marker proves itself: the timer removes it (once), a later Home init changes nothing
    m = Machine(); boot(m); m.call(clear_cb)
    expect(RUN not in m.fs and ('unlink', RUN) in m.calls and ('fsync', '/mnt/data') in m.calls,
           'the clear timer removes the marker and syncs the directory')
    m.call(clear_cb); expect('unlink' not in m.names(), 'clearing twice touches nothing')
    m.call(PSYMS['m1plus_home_init'], a0=HOME_WIN + 0x100, a1=0)
    expect(RUN not in m.fs and not [c for c in m.calls if c[0] == 'open'], 'a re-created Home does not arm again')
    expect([c for c in m.calls if c[0] == 'widget_on'] == [('widget_on', HOME_WIN + 0x100, 0x12d, fg_cb, HOME_WIN + 0x100)],
           'but the new Home window gets the foreground handler (and fr_boot registers its change handlers only once)')
    m = Machine(); m.present.add(KILL_SD); boot(m); m.call(clear_cb)
    expect('unlink' not in m.names(), 'the clear timer does nothing when the guard is off')

    # -- 3. a marker at boot: the earlier attempt never proved itself -> stock, note, setting, marker gone
    m = Machine(); m.fs[RUN] = b'1\n'; boot(m)
    expect(m.calls[0][0] == 'stock_init_resume', 'stock runs first on a failed-boot start too')
    expect(m.fs.get(BAD) == b'1\n' and writes_atomically(m, BAD, BAD + '.tmp', b'1\n'), 'the bad note is written atomically')
    expect(m.fs.get(START) == b'0\n', 'the setting is switched to Shanling')
    expect(RUN not in m.fs, 'the marker is removed once the note is down')
    expect(not m.timers and 'widget_on' not in m.names() and not [c for c in m.calls if c[0] == 'window_open'],
           'no timer, no handler, no window: this boot is stock')
    m2 = Machine(); m2.fs = dict(m.fs); boot(m2)
    expect(RUN not in m2.fs and not m2.timers,
           'the next boot, with the note present, stays stock: no marker, no timer (a crash cannot alternate with a good boot)')
    m = Machine(); m.fs[RUN] = b'1\n'; m.fail.add(('write', BAD + '.tmp')); boot(m)
    expect(RUN in m.fs and BAD not in m.fs and not m.timers, 'if the note cannot be written the marker stays, and this boot is stock')
    m3 = Machine(); m3.fs = dict(m.fs); m3.fail = set(m.fail); boot(m3)
    expect(not m3.timers and RUN in m3.fs, 'so every following boot is stock too (while the note cannot be written)')

    # -- 4. kill switches, SD and flash: stock behaviour, no file written
    for kill in (KILL_SD, KILL_DATA):
        m = Machine(); m.present.add(kill); boot(m)
        expect(not m.fs and not m.timers and 'widget_on' not in m.names(), f'{kill}: nothing is written, armed or registered')
        expect(m.names()[0] == 'stock_init_resume', f'{kill}: the stock Home still initialises')

    # -- 5. any failure on the way to the marker leaves the boot stock and no marker behind
    for what, fail in (('the temp file cannot be opened', ('open', RUN + '.tmp')), ('the write fails', ('write', RUN + '.tmp')),
                       ('fsync fails', ('fsync', RUN + '.tmp')), ('the rename fails', ('rename', RUN))):
        m = Machine(); m.fail.add(fail); boot(m)
        expect(RUN not in m.fs and not m.timers and 'widget_on' not in m.names(), f'{what}: no marker, no timer, no handler')
        expect(RUN + '.tmp' not in m.fs, f'{what}: no temp file left behind')
    m = Machine(); m.timer_fail = True; boot(m)
    expect(RUN not in m.fs and 'widget_on' not in m.names(),
           'no timer to clear the marker: the marker is removed again and nothing is registered')

    # -- 5b. the directory entry must be durable too: no confirmation, no arming (audit: the errors were ignored)
    for what, fail in (('the data directory cannot be opened', ('open', '/mnt/data')), ('the directory fsync fails', ('fsync', '/mnt/data'))):
        m = menu_machine(page); m.fail.add(fail); boot(m)
        expect(not m.timers and 'widget_on' not in m.names() and 'view_create' not in m.names() and
               not any(c[0] == 'widget_set_visible' for c in m.calls), f'{what}: not armed (no timer, no handler, no icon, the grid untouched)')
        expect(RUN not in m.fs and RUN + '.tmp' not in m.fs, f'{what}: no marker is left behind (it is removed again)')
        m2 = menu_machine(page); m2.fs = dict(m.fs); m2.fs[RUN] = b'1\n'; boot(m2)   # the removal lost too: the next boot falls back
        expect(m2.fs.get(BAD) == b'1\n' and RUN not in m2.fs and not m2.timers, f'{what}: a marker that survives is a failed boot next time (fail closed)')
        m = Machine(); m.fs[RUN] = b'1\n'; m.fail.add(fail); boot(m)
        expect(RUN in m.fs and not m.timers and 'widget_on' not in m.names(),
               f'{what} while recording a failed boot: the marker stays (the note is not confirmed), this boot is stock')
        expect(START not in m.fs, f'{what} while recording a failed boot: the setting is not rewritten before the note is down')
        m3 = Machine(); m3.fs = dict(m.fs); m3.fail = set(m.fail); boot(m3)
        expect(RUN in m3.fs and not m3.timers, f'{what}: and the next boot is stock again')

    # -- 6. the opt-in log (SD card): off by default, on with /mnt/mmc/m1plus-log
    m = Machine(); boot(m)
    expect(LOG not in m.fs and not any(c[0] == 'open' and c[1] == LOG for c in m.calls), 'no log file unless the card has m1plus-log')
    m = Machine(); m.present.add(LOG_ON); boot(m); m.call(clear_cb)
    expect(LOG in m.fs and b'armed' in m.fs[LOG] and b'marker cleared' in m.fs[LOG], f'with m1plus-log the events are appended ({m.fs.get(LOG)})')

    # ===================== the launcher =====================
    on_row, rowsM = PSYMS['on_row'], PSYMS['pod_rows_0']
    rowsS = PSYMS[f'pod_rows_{pod_pages.SETTINGS_PAGE_INDEX}']
    rowsH = PSYMS[f'pod_rows_{pod_pages.DEVELOPER_PAGE_INDEX}']
    grid_i = next(i for i, r in enumerate(HOMESET.rows) if r.action == pod_pages.ACT_GRID)
    start_i = next(i for i, r in enumerate(HOMESET.rows) if r.action == pod_pages.ACT_STARTUP)
    homeset_i = next(i for i, r in enumerate(SETTINGS.rows) if r.action == pod_pages.ACT_PAGE and r.arg == pod_pages.DEVELOPER_PAGE_INDEX)
    settings_i = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_PAGE and r.arg == pod_pages.SETTINGS_PAGE_INDEX)
    entry = PSYMS['m1plus_home_click']
    expect(homeset_i == len(SETTINGS.rows) - 1 and SETTINGS.rows[homeset_i].label == 'Developer'
           and (SETTINGS.rows[homeset_i].action, SETTINGS.rows[homeset_i].arg) == (pod_pages.ACT_PAGE, pod_pages.DEVELOPER_PAGE_INDEX)
           and [(r.label, r.action) for r in HOMESET.rows] == [('Boot to M1+ Music', pod_pages.ACT_STARTUP), ('Open Shanling Home', pod_pages.ACT_GRID), ('Screenshot', pod_pages.ACT_SHOT),
                                                              ('Cover Cache', pod_pages.ACT_PAGE), ('Clear Track Durations', pod_pages.ACT_CLEARDUR), ('Settings Files', pod_pages.ACT_PAGE), ('System Update', pod_pages.ACT_STOCK)]
           and HOMESET.title == 'Developer' and (start_i, grid_i) == (0, 1)
           and not [r for r in SETTINGS.rows if r.action in (pod_pages.ACT_GRID, pod_pages.ACT_STARTUP)]
           and [(r.label, r.action) for r in pod_pages.HOMESET_PAGE.rows] == [('Recent Albums', pod_pages.ACT_SHELF), ('Daily Mix', pod_pages.ACT_DAILY), ('Main Menu', pod_pages.ACT_PAGE), ('Extras', pod_pages.ACT_PAGE), ('Battery Percentage', pod_pages.ACT_BATTPCT), ('Regenerate Daily Mix', pod_pages.ACT_REGEN)],
           'Settings ends with Developer, whose page holds the launcher rows: Boot to M1+ Music (switch) and Open Shanling Home, then Screenshot, Cover Cache, Clear Track Durations, Settings Files and System Update; the Home Screen page has the shelf and mix switches, Main Menu, Extras, Battery Percentage and last Regenerate Daily Mix')
    expect(page.rows[0].label == 'Now Playing' and page.rows[-1].label == 'Extras' and page.rows[settings_i].label == 'Settings' and len(page.rows) == 25
           and not [r for r in page.rows if r.action in (pod_pages.ACT_GRID, pod_pages.ACT_STARTUP)],
           'the menu keeps the grouped rows, a Settings row and the Extras row last, which opens the Settings page (no launcher rows left on it)')

    def own(m, c): return c[1] not in {h for n, h in m.widgets.items() if n.startswith('pod_row')}   # not one of the menu's rows (patch/menu.c arranges those)
    def hid(m): return [c for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[2] == 0 and own(m, c)]
    def moved(m): return [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and own(m, c)]

    def armed(startfile=None):
        m = menu_machine(page)
        if startfile is not None: m.fs[START] = startfile
        boot(m)
        return m

    def settings_row(m, i):
        """Tap row i of the Home Screen page, opening the Settings page over the menu and that page over it first (once)."""
        if not getattr(m, 'sopen', False):
            m.window = 0x20002000
            m.call(on_row, a0=rowsM + 12 * settings_i)
            m.window = 0x20003000
            m.call(on_row, a0=rowsS + 12 * homeset_i)
            m.window = 0x20001000; m.sopen = True
        if HOMESET.rows[i].action in pod_pages.SWITCH_ACTIONS: m.click(f'pod_row{i}')
        else: m.call(on_row, a0=rowsH + 12 * i)

    def tap_icon(m): m.call(entry, a0=m.icon(ICON_NAME))

    # 7. the setting: missing / garbage = M1+ Music; "0" = Shanling. Both are armed (the icon is new code on the
    #    boot path); only M1+ Music hides the grid and schedules the menu.
    for content, pod_mode in ((None, True), (b'1\n', True), (b'x', True), (b'', True), (b'0\n', False), (b'0', False)):
        m = menu_machine(page)
        if content is not None: m.fs[START] = content
        boot(m)
        expect(RUN in m.fs and ('widget_on', HOME_WIN, 0x12d, fg_cb, HOME_WIN) in m.calls and m.timers[0] == (clear_cb, CLEAR_MS),
               f'start file {content!r}: armed (marker, clear timer, foreground handler)')
        expect(((open_cb, OPEN_FIRST_MS) in m.timers) == pod_mode and (('widget_set_visible', m.widgets[GRID], 0) in m.calls) == pod_mode,
               f'start file {content!r}: {"the menu is scheduled and the grid hidden" if pod_mode else "no menu, the grid stays: Shanling"}')
        expect(m.names().count('view_create') == 1, f'start file {content!r}: the icon is added whatever the setting')

    # I. the "M1+ Music" icon on the stock grid
    def icon_of(m, pi=-1):
        sv = m.widgets['home_sview']; last = m.children[sv][pi]; cell = m.children[last][-1]
        img, lab = m.children[cell]
        return sv, last, cell, img, lab
    def rect(m, w): return tuple(m.props[(w, k)] for k in 'xywh')
    m = menu_machine(page); boot(m)
    sv, last, cell, img, lab = icon_of(m)
    expect(len(m.children[sv]) == 3 and [len(m.children[p]) for p in m.children[sv]] == [6, 6, 6],
           'English Home (17 icons, 3x2 per page): the icon takes the free slot of page 3')
    expect(rect(m, cell) == (6 + 154, 2 * 118, 154, 118) and m.types[cell] == 'view',
           f'in the stock geometry: column 1, row 2 of the page, a 154x118 cell ({rect(m, cell)})')
    expect(rect(m, img) == (44, 20, 66, 66) and rect(m, lab) == (0, 92, 154, 36), 'a 66x66 image at (44, 20), the label 154x36 at y 92')
    expect(m.props.get((img, 'name')) == ICON_NAME and m.read_cstr(m.word(img + O['W_NAME'])) == ICON_NAME,
           f'named "{ICON_NAME}", an id stock never uses (the dispatcher knows 0..17)')
    expect(ICON_NAME.isdigit() and int(ICON_NAME) >= O['HOME_IDS'], 'a decimal id above the stock table')
    expect(m.props.get((img, 'style')) == ICON_STYLE and ('widget_set_prop_bool', img, 'clickable', 1) in m.calls,
           'clickable, with the style whose images are the smartphone disc (m1plus / m1plus_down)')
    expect(('widget_on', img, O['EVT_CLICK'], pod.HOME_CLICK, img) in m.calls,
           'the stock click handler (0x533b80, the dispatcher m1plus_home_click wraps) with the image as ctx, as stock registers it')
    expect(('widget_set_text_utf8', lab, 'M1+ Music') in m.calls and m.props.get((lab, 'style')) == 'label_centerwhitehome_white'
           and ('label_set_line_wrap', lab, 1) in m.calls, 'the label "M1+ Music" in the stock Home label style, wrapped')
    order = [c[0] for c in m.calls if c[0] in ('rename', 'view_create', 'image_create', 'label_create', 'widget_set_visible')]
    expect(order == ['rename', 'view_create', 'image_create', 'label_create', 'widget_set_visible'],
           f'created after the marker is durable and before the grid is hidden ({order})')
    # tap -> the menu, through the stock dispatcher's hook
    m.call(entry, a0=img)
    expect(('window_open', page.key) in m.calls and 'stock_resume' not in m.names(), 'tapping the icon opens the pod menu')
    expect(('widget_set_visible', m.widgets[GRID], 0) not in m.calls, 'a tap does not hide anything on its own')
    # the hit test, by demo's own code: the icon's image is the target of a touch on it (an enabled, sensitive child of its cell)
    def chain(m):
        sv, last, cell, img, lab = icon_of(m)
        def nd(h, name): return Node(name, *rect(m, h))
        c = nd(cell, 'cell'); i = nd(img, m.props[(img, 'name')]); l = nd(lab, 'label'); l.flags &= ~F_SENSITIVE
        c.children = [i, l]; p = Node('page', 0, 0, 320, 364); p.children = [c]; s = Node('home_sview', 0, 0, 320, 364); s.children = [p]
        return s
    m2 = menu_machine(page); boot(m2)
    for x, y, want in ((160 + 44 + 33, 236 + 20 + 33, ICON_NAME), (160 + 77, 236 + 100, 'cell')):
        got = stock_target(m2, chain(m2), x, y)
        expect(got[-1] == want, f'a touch at ({x}, {y}) in the slot reaches {want} ({got})')

    # slots: the first free one of the last page
    for pages_, slot_xy in (((6, 6, 1), (160, 0)), ((6, 6, 2), (6, 118)), ((6, 6, 3), (160, 118)), ((6, 6, 4), (6, 236)),
                            ((3,), (160, 118)), ((4,), (6, 236))):
        m = menu_machine(page, pages_); boot(m)
        sv, last, cell, img, lab = icon_of(m)
        expect(len(m.children[sv]) == len(pages_) and rect(m, cell)[:2] == slot_xy and len(m.children[last]) == pages_[-1] + 1,
               f'pages {pages_}: slot {pages_[-1]} of the last page at {slot_xy} ({rect(m, cell)[:2]})')
    # a full last page: one page more, as the stock page builder makes them, and the indicator's max follows
    m = menu_machine(page, (6, 6, 6)); boot(m)
    sv, last, cell, img, lab = icon_of(m)
    ind = m.widgets['home_sindicator']
    expect(len(m.children[sv]) == 4 and rect(m, last) == (0, 0, 320, 364) and m.children[last] == [cell] and rect(m, cell)[:2] == (6, 0),
           'a full last page: a 4th page (320x364) with the icon in its first slot')
    expect(('slide_indicator_set_max', ind, 4) in m.calls, 'and the page indicator knows four pages')
    m = menu_machine(page, (6, 6, 6)); m.widgets.pop('home_sindicator'); boot(m)
    expect(len(m.children[m.widgets['home_sview']]) == 4 and 'slide_indicator_set_max' not in m.names(), 'no indicator found: the page is still added')
    # no icon, stock behaviour: an unexpected tree, a failed create, the kill switch, a failed boot, a failed stock init
    m = menu_machine(page); m.widgets.pop('home_sview'); boot(m)
    expect(not [c for c in m.calls if c[0] in ('view_create', 'image_create', 'label_create', 'widget_set_name', 'widget_destroy')]
           and RUN in m.fs and (open_cb, OPEN_FIRST_MS) in m.timers, 'no home_sview: no icon, the guard carries on')
    m = menu_machine(page); m.types[m.widgets['home_sview']] = 'view'; boot(m)
    expect('view_create' not in m.names(), 'home_sview is not a slide_view: no icon')
    m = menu_machine(page); m.types[m.children[m.widgets['home_sview']][-1]] = 'widget'; boot(m)
    expect('view_create' not in m.names(), 'a last page that is not a view: no icon')
    m = menu_machine(page, ()); boot(m)
    expect('view_create' not in m.names(), 'no pages: no icon')
    m = menu_machine(page, (6, 6, 7)); boot(m)
    expect('view_create' not in m.names(), 'a page with more than six cells (not the stock layout): no icon')
    for ctor in ('view_create', 'image_create', 'label_create'):
        m = menu_machine(page); m.create_fail.add(ctor); boot(m)
        sv = m.widgets['home_sview']
        expect([len(m.children[p]) for p in m.children[sv]] == [6, 6, 5] and not any(c[0] == 'widget_set_name' for c in m.calls),
               f'{ctor} fails: the grid is as stock (a partial cell is destroyed again)')
        expect(('widget_destroy' in m.names()) == (ctor != 'view_create') and RUN in m.fs and (open_cb, OPEN_FIRST_MS) in m.timers,
               f'{ctor} fails: cleaned up, the boot carries on')
    m = menu_machine(page, (6, 6, 6)); m.create_fail.add('label_create'); boot(m)
    expect(len(m.children[m.widgets['home_sview']]) == 3 and m.names().count('widget_destroy') == 2,
           'a failed cell on a new page removes the cell and that page again')
    expect(not any(c[0] == 'slide_indicator_set_max' for c in m.calls), 'and the indicator is left alone')
    for tag, setup in (('kill switch', lambda m: m.present.add(KILL_SD)), ('flash kill switch', lambda m: m.present.add(KILL_DATA)),
                       ('a marker at boot', lambda m: m.fs.update({RUN: b'1\n'})), ('the bad note', lambda m: m.fs.update({BAD: b'1\n'})),
                       ('marker not writable', lambda m: m.fail.add(('open', RUN + '.tmp')))):
        m = menu_machine(page); setup(m); boot(m)
        expect(not [c for c in m.calls if c[0] in ('view_create', 'image_create', 'label_create', 'widget_set_name', 'widget_on')],
               f'{tag}: no icon (stock behaviour), no handler')
    m = menu_machine(page); boot(m, ret=0x10)
    expect(m.names() == ['stock_init_resume'], 'a failed stock init: nothing at all')
    # the stock code rebuilt the grid (Home customisation): the foreground handler puts the icon back, once
    m = armed(); m.widgets.pop(ICON_NAME)
    m.call(fg_cb, a0=HOME_WIN)
    expect('view_create' in m.names() and m.names().count('widget_set_name') == 1, 'Home in the foreground without the icon: it is re-added')
    m.call(fg_cb, a0=HOME_WIN)
    expect('view_create' not in m.names(), 'and not added twice')
    m = armed(); m.widgets.pop(ICON_NAME); m.present.add(KILL_SD); m.call(fg_cb, a0=HOME_WIN)
    expect('view_create' not in m.names(), 'not with the kill switch')

    # 8. the first open: the stock Home is the topmost normal window and opened -> the pod menu as Home
    m = armed(); m.top_main = HOME_WIN
    m.call(open_cb)
    expect(('window_open', page.key) in m.calls, 'the pod menu opens when Home is the topmost normal window')
    nb, lv, sv_, bar = (m.widgets[n] for n in (NAVBAR, LISTVIEW, SCROLLVIEW, SCROLLBAR))
    expect(('widget_set_visible', nb, 0) in m.calls and ('widget_set_sensitive', nb, 0) in m.calls,
           'the Home instance has no top bar: the navbar view is hidden and insensitive (visible=false alone still takes touches)')
    pad = O['HOME_PAD']; room = 450 - 2 * pad
    expect(6 <= pad <= 12, f'a slight top padding ({pad})')
    expect(('widget_move', lv, 0, pad) in m.calls and ('widget_resize', lv, 320, room) in m.calls and
           ('widget_resize', sv_, 310, room) in m.calls and ('widget_resize', bar, 10, room) in m.calls,
           'the stock list starts HOME_PAD below the status bar and ends HOME_PAD above the screen edge (the scroll view and its bar follow, widths kept)')
    expect(not [c for c in m.calls if c[:2] in (('widget_set_visible', m.widgets['btn_return']), ('widget_set_visible', m.widgets['label_title']))],
           'Back and the title are not touched one by one: they go with their navbar')
    expect(('widget_set_visible', m.widgets[GRID], 0) in m.calls, 'and the stock grid content stays hidden')
    expect(m.names().count('window_open') == 1 and ('get_top_main_window', m.wm) in m.calls,
           'one window, after asking the window manager what is on top')
    expect(not [c for c in m.calls if c[0] == 'widget_set_text_utf8'], 'the menu has no Start-in row to relabel: it lives on the Settings page')
    # the Home instance with a tree that lacks the navbar or the list: nothing is hidden or moved
    for gone in (NAVBAR, LISTVIEW):
        m = armed(); m.top_main = HOME_WIN; m.widgets.pop(gone); m.call(open_cb)
        expect(('window_open', page.key) in m.calls and not moved(m) and
               ('widget_set_visible', m.widgets.get(NAVBAR, -1), 0) not in m.calls, f'no {gone}: the page opens as it is, nothing moved or hidden')
    # the touches: the rows reach the top of the screen, the hidden navbar takes none (demo's own hit test)
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb)
    tree = asset_tree(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui', page.key + '.bin'))
    for nm in (NAVBAR, LISTVIEW, SCROLLVIEW, SCROLLBAR):
        nd, h = node(tree, nm), m.widgets[nm]
        for k in 'xywh':
            if (h, k) in m.props: setattr(nd, k, m.props[(h, k)])
        if (h, 'visible') in m.props: nd.flags = nd.flags & ~F_VISIBLE | (F_VISIBLE if m.props[(h, 'visible')] else 0)
        if (h, 'sensitive') in m.props: nd.flags = nd.flags & ~F_SENSITIVE | (F_SENSITIVE if m.props[(h, 'sensitive')] else 0)
    for x, y, want in ((160, 26 + pad, 'pod_row0'), (278, 25 + pad, 'pod_row0'), (32, pad, 'pod_row0'), (160, 78 + pad, 'pod_row1'), (160, 430, 'pod_row8')):
        got = stock_target(m, tree, x, y)
        expect(want in got and 'pod_scrollview' in got and NAVBAR not in got and 'btn_backtoplayer' not in got,
               f'Home instance: a touch at ({x}, {y}) hits {want}, not the hidden navbar ({got})')
    for y in (0, pad - 1, 450 - pad, 449):   # the padding strips are not rows (and not the hidden navbar)
        got = stock_target(m, tree, 160, y)
        expect(not any(n.startswith('pod_row') for n in got) and NAVBAR not in got and 'btn_backtoplayer' not in got,
               f'Home instance: a touch in the padding (y {y}) hits no row and no hidden navbar ({got})')
    plain = asset_tree(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui', page.key + '.bin'))
    expect('btn_backtoplayer' in stock_target(m, plain, 290, 25),
           'the menu opened from the icon keeps its navbar (and the bars icon takes its touch)')

    # 9. something else on top (resumed Now Playing, the guide, another window): nothing opens
    m = armed(); m.top_main = 0x24000000; m.timers = []
    m.call(open_cb)
    expect('window_open' not in m.names() and not m.timers,
           'another window on top: no open and no retry (its Back brings Home to the foreground)')
    m = armed(); m.top_main = 0
    m.call(open_cb); expect('window_open' not in m.names(), 'no topmost window: nothing')

    # 10. Home not opened yet: retry every 250 ms, MAX_TRIES at most
    m = armed(); m.top_main = HOME_WIN; m.home_opened = 0; m.timers = []
    n = 0
    m.call(open_cb)
    while m.timers and n < 2 * MAX_TRIES:
        expect(m.timers[-1] == (open_cb, RETRY_MS), 'retry timer'); m.timers = []; n += 1
        m.call(open_cb)
    expect('window_open' not in m.names() and n == MAX_TRIES - 1, f'a Home that never opens: {MAX_TRIES - 1} retries, then stop ({n})')
    m = armed(); m.top_main = HOME_WIN; m.home_opened = 0; m.call(open_cb); m.home_opened = 1; m.call(open_cb)
    expect(('window_open', page.key) in m.calls, 'a Home that opens late gets the menu')

    # 11. the go-home paths: each ends with Home coming to the foreground (0x12d) -> reopen
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb)            # the menu is up
    m.timers = []
    m.call(fg_cb, a0=HOME_WIN)                                      # go-home / lock screen / USB / Now Playing back ...
    expect(m.timers == [(open_cb, OPEN_MS)], f'Home in the foreground schedules one open ({m.timers})')
    m.timers = []
    m.call(fg_cb, a0=HOME_WIN); expect(not m.timers, 'a second foreground event while one is pending schedules nothing')
    m.top_main = HOME_WIN; m.call(open_cb)
    expect(('window_open', page.key) in m.calls, 'and the menu comes back')
    m.call(fg_cb, a0=HOME_WIN)
    expect(m.timers == [(open_cb, OPEN_MS)], 'the pending flag is cleared by the open, so the next return schedules again')

    # 12. the navbar is hidden on the Home instance only; the menu the icon opens (the stock grid is behind it) keeps it
    m = armed()
    tap_icon(m)
    expect(('window_open', page.key) in m.calls and not hid(m) and not moved(m),
           'the icon opens the menu with its navbar (Back, title, bars icon) and the list where it is')
    m = armed(); m.top_main = HOME_WIN; m.window = 0; m.call(open_cb)
    expect(('window_open', page.key) in m.calls and not hid(m), 'a failed open hides nothing')
    expect(('widget_set_visible', m.widgets[GRID], 1) in m.calls, 'and a failed open shows the stock grid again (it was hidden at boot)')
    m.window = 0x20001000
    tap_icon(m)
    expect(not hid(m), 'and a later icon open still has its navbar (the failed attempt left no flag)')
    # the Settings page shows the settings when it opens: its switch images, by name
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); m.window = 0x20002000
    m.call(on_row, a0=rowsM + 12 * settings_i)
    expect(('window_open', SETTINGS.key) in m.calls and switch_shows(m, start_i) is None,
           "the menu's Settings row opens the Settings page (no switch on it any more)")
    expect(not hid(m) and not moved(m), 'the Settings page keeps its navbar and list')
    expect([c[0] for c in m.calls].count('widget_on') == 2 + len(SETTINGS.rows) + 2, 'its Back, its bars icon and its rows are bound, and the foreground and destroy events of the values')
    m.window = 0x20003000
    m.call(on_row, a0=rowsS + 12 * homeset_i)
    expect(('window_open', HOMESET.key) in m.calls and switch_shows(m, start_i) is True,
           "the Developer row opens the Developer page; Boot to M1+ Music is on")
    expect(m.types.get(switch_image(m, start_i)) is None and not [c for c in m.calls if c[0] == 'widget_set_text_utf8'],
           'the switches are images (sset_on / sset_off): no text is set anywhere (the V2.1iM ghost text cannot come back)')
    expect(not hid(m) and not moved(m), 'the Developer page keeps its navbar and list')
    expect([c[0] for c in m.calls].count('widget_on') == 2 + len(HOMESET.rows) + 2,'its Back, its bars icon and its rows are bound (and the switch refresh events)')
    m.call(PSYMS['pod_on_back'])
    expect(m.names() == ['navigator_back'], 'Back goes back to the Settings page')

    # 13. kill switches are honoured later too
    for kill in (KILL_SD, KILL_DATA):
        m = armed(); m.top_main = HOME_WIN; m.timers = []; m.present.add(kill)
        m.call(fg_cb, a0=HOME_WIN); expect(not m.timers, f'{kill} appeared: Home in the foreground schedules nothing')
        m.call(open_cb); expect('window_open' not in m.names(), f'{kill} appeared: no open')
        tap_icon(m)
        expect('window_open' not in m.names() and 'stock_resume' in m.names(), f'{kill}: the icon does nothing more than stock would')
    m = Machine(); m.call(entry, a0=m.icon('1'))
    expect(('stock_resume', '1') in m.calls and 'window_open' not in m.names(), 'Tidal (id 1) is Tidal again: stock, no page')

    # 13b. recovery: while the bad note exists there is no grid icon, so Tidal (id 1) opens the menu (with Back)
    m = Machine(); m.fs[BAD] = b'1\n'; m.call(entry, a0=m.icon('1'))
    expect(('window_open', page.key) in m.calls and 'stock_resume' not in m.names(),
           'the bad note: a tap on Tidal opens the M1+ Music menu')
    expect(('widget_set_visible', m.widgets.get(NAVBAR, -1), 0) not in m.calls and 'widget_move' not in m.names(),
           'and it is the normal instance (navbar and Back kept, not the Home layout)')
    m = Machine(); m.fs[BAD] = b'1\n'; m.call(entry, a0=m.icon('2'))
    expect(('stock_resume', '2') in m.calls and 'window_open' not in m.names(), 'the bad note: other icons stay stock')
    m = Machine(); m.fs[BAD] = b'1\n'; m.window = 0; m.call(entry, a0=m.icon('1'))
    expect(('stock_resume', '1') in m.calls, 'the bad note, the page cannot open: Tidal falls back to stock')
    for kill in (KILL_SD, KILL_DATA):
        m = Machine(); m.fs[BAD] = b'1\n'; m.present.add(kill); m.call(entry, a0=m.icon('1'))
        expect(('stock_resume', '1') in m.calls and 'window_open' not in m.names(), f'the bad note and {kill}: Tidal stays stock')

    # 14. Shanling Home: the stock grid for this session
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb)
    settings_row(m, grid_i)
    expect(m.names() == ['widget_lookup', 'widget_set_visible', 'widget_set_sensitive', 'window_close', 'window_close', 'navigator_back'] and
           m.calls[1:3] == [('widget_set_visible', m.widgets[GRID], 1), ('widget_set_sensitive', m.widgets[GRID], 1)] and
           m.calls[3:5] == [('window_close', 0x20001000), ('window_close', 0x20002000)],
           f'the row shows the stock grid again, closes the menu and the Settings page under the Home Screen page, then that page with navigator_back ({m.names()})')
    m.timers = []
    m.call(fg_cb, a0=HOME_WIN); expect(not m.timers, 'the grid stays: Home in the foreground schedules nothing')
    m.call(open_cb); expect('window_open' not in m.names(), 'and a stale timer does not open the menu either')
    tap_icon(m)
    expect(('window_open', page.key) in m.calls and ('widget_set_visible', m.widgets[NAVBAR], 0) in m.calls and
           ('widget_set_visible', m.widgets[GRID], 0) in m.calls and ('widget_move', m.widgets[LISTVIEW], 0, O['HOME_PAD']) in m.calls,
           'the icon on the grid restores M1+ Music as Home: no navbar, list up, grid hidden')
    m.timers = []; m.call(fg_cb, a0=HOME_WIN)
    expect(m.timers == [(open_cb, OPEN_MS)], 'and Home in the foreground reopens the menu again (pod Home for the session)')
    # a Home Screen page without a menu below it (cannot happen from the UI): just the back
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); m.call(on_row, a0=rowsH + 12 * grid_i)
    expect(m.names() == ['widget_lookup', 'widget_set_visible', 'widget_set_sensitive', 'navigator_back'], 'no Settings window known: one navigator_back, no window_close')
    # Settings opened from the Extras page (menu > Extras > Settings > Home Screen): that page is closed too, by handle
    rowsE = PSYMS[f'pod_rows_{pod_pages.EXTRAS_PAGE_INDEX}']
    extras_i = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_PAGE and r.arg == pod_pages.EXTRAS_PAGE_INDEX)
    cust_e = next(i for i, r in enumerate(pod_pages.EXTRAS_PAGE.rows) if r.action == pod_pages.ACT_PAGE and r.arg == pod_pages.SETTINGS_PAGE_INDEX)
    def via_extras():
        m = armed(); m.top_main = HOME_WIN; m.call(open_cb)
        m.window = 0x20002000; m.call(on_row, a0=rowsM + 12 * extras_i)
        m.destroy = [c for c in m.calls if c[0] == 'widget_on' and c[1] == 0x20002000 and c[2] == O['EVT_DESTROY']]
        m.window = 0x20003000; m.call(on_row, a0=rowsE + 12 * cust_e)
        m.window = 0x20004000; m.call(on_row, a0=rowsS + 12 * homeset_i)
        return m
    m = via_extras(); m.call(on_row, a0=rowsH + 12 * grid_i)
    expect(m.names() == ['widget_lookup', 'widget_set_visible', 'widget_set_sensitive', 'window_close', 'window_close', 'window_close', 'navigator_back']
           and m.calls[3:6] == [('window_close', 0x20001000), ('window_close', 0x20002000), ('window_close', 0x20003000)],
           f'menu > Extras > Settings > Home Screen: Shanling Home closes the menu, the Extras page and the Settings page, then the Home Screen page ({m.names()})')
    m = via_extras()
    destroy = m.destroy
    expect(len(destroy) == 1, 'the Extras page registers its destroy')
    m.call(destroy[0][3], a0=destroy[0][4]); m.call(on_row, a0=rowsH + 12 * grid_i)
    expect(m.calls[3:5] == [('window_close', 0x20001000), ('window_close', 0x20003000)] and m.names().count('window_close') == 2,
           'an Extras page that was destroyed is forgotten: it is not closed again')
    # the restoring open fails: back to the grid state it was in, a later tap tries again
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); settings_row(m, grid_i)
    m.window = 0
    tap_icon(m)
    expect(m.names().count('window_open') == 1 and 'stock_resume' in m.names() and not hid(m), 'a failing restore falls to stock and hides nothing')
    m.timers = []; m.call(fg_cb, a0=HOME_WIN); expect(not m.timers, 'and the grid state is kept (nothing reopens)')
    m.window = 0x20001000
    tap_icon(m)
    expect(('widget_set_visible', m.widgets[NAVBAR], 0) in m.calls, 'the next tap restores Home')
    # setting Shanling: the icon's menu is a normal one
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); settings_row(m, start_i)
    settings_row(m, grid_i)
    tap_icon(m)
    expect(('window_open', page.key) in m.calls and not hid(m), 'with Start in: Shanling the icon opens a normal menu, with its navbar')
    m = menu_machine(page); m.fs[START] = b'0\n'; boot(m)
    expect(not any(c[0] == 'widget_set_visible' for c in m.calls), 'a Shanling start never hides the grid')
    tap_icon(m)
    expect(('window_open', page.key) in m.calls and not hid(m), 'and its icon opens the menu with the navbar (there is no pod Home to restore)')
    for kill in (KILL_SD, KILL_DATA):
        m = armed(); m.top_main = HOME_WIN; m.call(open_cb); settings_row(m, grid_i); m.present.add(kill)
        tap_icon(m)
        expect('window_open' not in m.names(), f'{kill}: no restore')
    # 15. Boot to M1+ Music: the persistent switch, written atomically, the switch image following
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb)
    settings_row(m, start_i)
    expect(m.fs.get(START) == b'0\n' and writes_atomically(m, START, START + '.tmp', b'0\n'),
           'switch off -> Shanling: the setting is written atomically')
    expect(switch_shows(m, start_i) is False, 'the switch shows off')
    m.fs[BAD] = b'1\n'; m.timers = []
    m.call(fg_cb, a0=HOME_WIN); expect(not m.timers, 'with Shanling chosen Home in the foreground no longer reopens the menu')
    settings_row(m, start_i)
    expect(m.fs.get(START) == b'1\n' and switch_shows(m, start_i) is True, 'switch on -> M1+ Music: written, the switch shows on')
    expect(BAD not in m.fs, 're-enabling M1+ Music removes the sticky bad note')
    m.fail.add(('write', START + '.tmp'))
    settings_row(m, start_i)
    expect(m.fs.get(START) == b'1\n' and switch_shows(m, start_i) is None and START + '.tmp' not in m.fs,
           'a failed write changes neither the file nor the switch image')
    m = menu_machine(page); m.fs[START] = b'0\n'; boot(m); m.top_main = HOME_WIN; m.window = 0x20002000
    m.call(on_row, a0=rowsM + 12 * settings_i)
    m.window = 0x20003000
    m.call(on_row, a0=rowsS + 12 * homeset_i)
    expect(switch_shows(m, start_i) is False, 'with Shanling saved the Home Screen page opens with the switch off')
    # 15b. never a blank Home (audit): the menu is Home (grid hidden), then Start in is switched to Shanling without
    #      "Shanling Home": the go-home path closes the menus and Home comes to the foreground with no menu to follow
    def grid_shown(m): return ('widget_set_visible', m.widgets[GRID], 1) in m.calls and ('widget_set_sensitive', m.widgets[GRID], 1) in m.calls
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); settings_row(m, start_i)
    expect(m.fs.get(START) == b'0\n', 'Start in -> Shanling while the menu is Home')
    m.timers = []; m.call(fg_cb, a0=HOME_WIN)
    expect(grid_shown(m) and not m.timers, 'Home in the foreground then shows the stock grid again (no menu follows)')
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); m.present.add(KILL_SD); m.timers = []; m.call(fg_cb, a0=HOME_WIN)
    expect(grid_shown(m) and not m.timers, 'a kill switch that appeared while the menu was Home: Home in the foreground shows the grid')
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); m.timer_fail = True; m.timers = []; m.call(fg_cb, a0=HOME_WIN)
    expect(grid_shown(m) and not m.timers, 'the open timer is refused: the grid is shown, not left hidden')
    m = armed(); m.top_main = HOME_WIN; m.call(open_cb); m.timers = []; m.call(fg_cb, a0=HOME_WIN)
    expect(not grid_shown(m) and m.timers == [(open_cb, OPEN_MS)], 'while the menu stays Home the grid stays hidden')
    # a failed boot switches to Shanling and adds no icon; the hook still maps a tap (an icon from before), and the
    # Settings page's toggle is the way back
    m = Machine(); m.fs[RUN] = b'1\n'; boot(m)
    expect(m.fs[START] == b'0\n' and BAD in m.fs, 'failed boot -> setting Shanling + note')
    m2 = menu_machine(page); m2.fs = dict(m.fs); boot(m2)
    expect(not m2.timers and 'view_create' not in m2.names(), 'the next boot is stock: no timer, no icon')
    tap_icon(m2)
    settings_row(m2, start_i)
    expect(m2.fs[START] == b'1\n' and BAD not in m2.fs, 'the Settings page toggle is the way back')
    m3 = menu_machine(page); m3.fs = dict(m2.fs); boot(m3)
    expect(RUN in m3.fs and m3.timers and m3.names().count('view_create') == 1, 'confirmed: the boot after the toggle is armed and has its icon')

    # P1. the grid is hidden at boot, after the marker, and never before it
    m = menu_machine(page); boot(m)
    g = m.widgets[GRID]
    iv = next(i for i, c in enumerate(m.calls) if c[:2] == ('widget_set_visible', g))
    ir = next(i for i, c in enumerate(m.calls) if c[0] == 'rename' and c[2] == RUN)
    expect(('widget_set_visible', g, 0) in m.calls and ('widget_set_sensitive', g, 0) in m.calls and ir < iv,
           'boot hides the grid content (hidden + insensitive), after the marker is durable')
    expect(('widget_lookup', GRID) in m.calls and m.calls[0] == ('stock_init_resume', HOME_WIN, 0x55), 'after the stock init, looked up by name')
    expect(m.timers == [(PSYMS['hm_clear'], CLEAR_MS), (open_cb, OPEN_FIRST_MS)], 'the first open is scheduled right away')
    for tag, fail in (('marker not writable', ('open', RUN + '.tmp')), ('rename fails', ('rename', RUN))):
        m = menu_machine(page); m.fail.add(fail); boot(m)
        expect(not any(c[0] == 'widget_set_visible' for c in m.calls), f'{tag}: the grid is not touched')
    m = menu_machine(page); m.fs[RUN] = b'1\n'; boot(m)
    expect(not any(c[0] == 'widget_set_visible' for c in m.calls), 'marker found: stock, the grid is not touched')
    # P2. every give-up shows the grid again
    m = menu_machine(page); boot(m); m.top_main = HOME_WIN; m.present.add(KILL_SD); m.call(open_cb)
    expect(('widget_set_visible', g, 1) in m.calls and 'window_open' not in m.names(), 'kill switch at open time: the grid is shown, no menu')
    m = menu_machine(page); boot(m); m.top_main = 0; m.call(open_cb)
    expect(('widget_set_visible', g, 1) in m.calls, 'no topmost window: the grid is shown')
    m = menu_machine(page); boot(m); m.top_main = HOME_WIN; m.home_opened = 0; m.timers = []
    m.call(open_cb)
    for _ in range(MAX_TRIES + 2):
        if not m.timers: break
        m.timers = []; m.call(open_cb)
    expect(('widget_set_visible', g, 1) in m.calls, 'Home never opens: after the last retry the grid is shown')
    m = menu_machine(page); boot(m); m.top_main = 0x24000000; m.call(open_cb)
    expect(('widget_set_visible', g, 1) not in m.calls, 'another window on top: the grid stays hidden (its close brings Home back and reopens the menu)')

    # 16. the menu's other rows are unchanged by all this
    m = armed(); m.call(on_row, a0=rowsM + 12 * next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_PLAYER))
    expect('on_backtoplayer_onclick' in m.names(), 'Now Playing still goes to the player')


def run(ctx):
    home_tests(ctx.expect, ctx.page)

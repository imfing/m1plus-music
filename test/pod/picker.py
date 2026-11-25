"""The Add to Playlist picker (patch/picker.c, patch/playlists.c pick mode, docs/modules/picker.md): opened over a page that owns the stock list, it copies the list
and the marks, shows the Playlists page as a list with "New playlist" first and no "..." / view toggle / Now Playing button, keeps the caller's browsing record
through its own stock queries, adds with the stock batch_add_file as the stock row handler does (class, 0xf00b, the list, the selection, the playlist id), says the
stock message and closes; New playlist makes the playlist on the keyboard's Done and adds to it; Back adds nothing; where the page cannot open the caller gets -1 (the
stock picker is its fallback, tested in test/pod/songs.py)."""
import importlib.util, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


def playlists_module():
    """test/pod/playlists.py's helpers (its machine, page opener, loader and tap), loaded as test/patch.py loads it."""
    mod = sys.modules.get('podtest_playlists')
    if mod is None:
        spec = importlib.util.spec_from_file_location('podtest_playlists', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playlists.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['podtest_playlists'] = mod
        spec.loader.exec_module(mod)
    return mod


LIB, CLS = 0xf001, 0xf001
NAV_TITLE, G_CLASS, CLASSINFO = pod.DATA['NAV_TITLE'][0], pod.DATA['G_CLASS_TYPE'][0], pod.DATA['CLASSINFO'][0]
SHOWLIST, SEL_VEC = pod.DATA['PDEQ_SHOWLIST'][0], pod.DATA['SEL_VEC'][0]
LISTS = [(1, 'Road Trip', [0, 1, 2, 3]), (2, 'Late Night', [1, 4]), (3, 'Focus', [5])]


def caller(PL, windows=None):
    """The machine with a Songs-like caller: six songs in *pdeq_showlist, rows 1 and 3 marked, the browsing record the page would have."""
    m = PL.PM(LISTS)
    if windows: m.windows.update(windows)
    m.songs = [m.record(title=f'S{i}', path=f'/mnt/mmc/s/{i}.flac', rid=100 + i) for i in range(6)]
    m.setword(SHOWLIST, m.new_deque(m.songs))
    m.u.mem_write(NAV_TITLE, b'Songs title\0'); m.setword(G_CLASS, CLS); m.setword(CLASSINFO, CLS); m.setword(CLASSINFO + 4, 77)
    m.setword(SEL_VEC, m.alloc(8))   # the stock vector exists
    m.class_lists[0xf00a] = []   # Favourites empty (the picker reads it for its tick)
    m.sel = m.alloc(8); m.u.mem_write(m.sel, bytes([0b00001010]))
    return m


def record_ok(m):
    return m.word(G_CLASS) == CLS and m.read_cstr(NAV_TITLE) == 'Songs title' and m.word(CLASSINFO) == CLS and m.word(CLASSINFO + 4) == 77


def open_picker(m, count=6):
    r = m.call(PSYMS['picker_open'], a0=CLS, a1=count, a2=m.sel, count=60000000)
    return r, list(m.calls)


def destroy(m):
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=20000000)


def run(ctx):
    expect = ctx.expect
    PL = playlists_module()
    ROW = O['LIST_ROW_H']
    vis = PL.vis

    # 1. Opening: the page, the copies, the navbar
    m = caller(PL)
    r, calls = open_picker(m)
    t = m.widgets['label_title']
    expect(r == 1 and ('window_open', 'm1plus_playlists') in calls and not [c for c in calls if c[0] == 'navigator_to_with_context'],
           'picker_open opens our Playlists page (1); the stock playlist_page is not opened')
    expect(('widget_set_text_utf8', m.widgets['pl_title'], 'Add to Playlist') in calls, 'the large title reads Add to Playlist too')
    expect(('widget_set_tr_text', t, 'Add to Playlist') in calls and all(vis(m, n) == (0, 0) for n in ('btn_plactions', 'btn_more', 'btn_backtoplayer'))
           and vis(m, 'btn_return')[0] == 1 and ('widget_resize', t, O['SG_SELALL_X'] - O['NAV_TITLE_X'], 22) in calls,
           'the title is Add to Playlist; the list-plus button, the "..." button and Now Playing are hidden and insensitive; Back stays')
    blits, texts, styles = PL.settle(m)
    titles = [x for x, s in zip(texts, styles) if s == 'label_row_title']
    subs = [x for x, s in zip(texts, styles) if s == 'label_row_sub']
    expect([x[0] for x in titles] == ['playlist_create', 'Favorites', 'Focus', 'Late Night', 'Road Trip'] and [x[0] for x in subs] == ['1 track', '2 tracks', '4 tracks'],
           f'a list: playlist_create (New playlist) and Favorites pinned first (no count), then the playlists in the page\'s name order (A-Z) with their counts ({[x[0] for x in titles]}, {[x[0] for x in subs]})')
    expect(m.word(m.widgets['view_grid'] + 0xc) == PL.TOP + 5 * ROW, 'five rows high, under the title block')
    for saved, want in ((b'1\n', ['Focus', 'Late Night', 'Road Trip']), (b'b\n', ['Focus', 'Late Night', 'Road Trip']), (b'a\n', ['Road Trip', 'Late Night', 'Focus'])):
        m2 = caller(PL); m2.fs['/mnt/data/m1plus/playlists-sort'] = saved
        open_picker(m2); blits, texts, styles = PL.settle(m2)
        got = [x[0] for x, s in zip(texts, styles) if s == 'label_row_title'][2:]
        expect(got == want, f'the saved order {saved!r} ("a" Title Z-A; the date orders "1" and "b" with no times in the file: Title A-Z) orders the picker\'s playlists ({got})')
    m2 = caller(PL); m2.fs['/mnt/data/m1plus/playlists-sort'] = b'1\n'; m2.fs['/mnt/data/m1plus/playlists-meta'] = b'M1PLMETA 1\n1 5 5 0 Road Trip\n'
    open_picker(m2); blits, texts, styles = PL.settle(m2)
    got = [x[0] for x, s in zip(texts, styles) if s == 'label_row_title'][2:]
    expect(got[0] == 'Road Trip', f'Date Added: the picker follows the Playlists page\'s date order too, the stamped playlist first ({got})')
    expect(record_ok(m), 'the browsing class, classinfo[0..1] and the navigation title are the caller\'s after the picker\'s own stock queries')

    # 2. A playlist row: the stock add on the copy and the marks, the message, the page closes
    m.setword(CLASSINFO + 4, 5); m.u.mem_write(NAV_TITLE, b'x\0')   # (what a stock query leaves: put back at the end of the add)
    calls = PL.tap(m, 100, PL.TOP + 3 * ROW + 20)
    add = [c for c in calls if c[0] == 'batch_add_file']
    expect(len(add) == 1 and add[0][1:3] == (CLS, O['CLASS_PLAYLISTS']) and add[0][5] == 2 and add[0][6] == [1, 3] and add[0][4] == m.word(SEL_VEC),
           f'a tap on Late Night: batch_add_file({CLS:#x}, 0xf00b, list, the stock vector, 2) with rows 1 and 3 selected ({add})')
    expect(add and add[0][3] != m.word(SHOWLIST) and [m.deques[add[0][3]][i] for i in range(6)] == m.songs,
           'the list is the picker\'s copy of the songs (the page\'s own queries replaced *pdeq_showlist)')
    expect([c for c in calls if c[0] == 'select_recordinit'] == [('select_recordinit', 6)] and [c[1] for c in calls if c[0] == 'set_selectindex'] == [1, 3],
           'the stock vector is filled from the marks just before')
    expect(('toast', 'msg_addplaylistsuccess', 1, 2000) in calls and ('window_close', m.window) in calls and not [c for c in calls if c[0] == 'navigator_back'],
           'the stock "Added To Playlist" message, then the picker\'s window is closed as the stock handler closes its own')
    expect(m.fs.get('/mnt/data/m1plus/playlists-meta') == b'M1PLMETA 1\n2 0 %d 0 Late Night\n' % m.wall, f'the playlist is stamped as updated ({m.fs.get("/mnt/data/m1plus/playlists-meta")})')
    calls = PL.tap(m, 100, PL.TOP + 4 * ROW + 20)
    expect(not [c for c in calls if c[0] == 'batch_add_file'], 'a second tap adds nothing again')
    destroy(m)
    expect(record_ok(m), 'the page gone: the caller\'s browsing record is back')
    m.setword(SHOWLIST, m.new_deque(m.songs))   # (the caller reads its list again)
    r, calls = open_picker(m)
    expect(r == 1, 'and a new picker opens')
    destroy(m)

    # 2b. The Favourites row: the stock Add button's Favourites path (@0x5281c8): batch_add_file(class, 0xf00a, list, vector, 0), msg_addfavsuccess
    m = caller(PL)
    open_picker(m); PL.settle(m)
    m.setword(CLASSINFO + 4, 5); m.u.mem_write(NAV_TITLE, b'x\0')
    calls = PL.tap(m, 100, PL.TOP + ROW + 20)
    add = [c for c in calls if c[0] == 'batch_add_file']
    expect(len(add) == 1 and add[0][1:3] == (CLS, 0xf00a) and add[0][5] == 0 and add[0][6] == [1, 3] and add[0][4] == m.word(SEL_VEC),
           f'a tap on Favorites: batch_add_file({CLS:#x}, 0xf00a, list, the stock vector, 0) with rows 1 and 3 selected ({add})')
    expect(add and add[0][3] != m.word(SHOWLIST) and [m.deques[add[0][3]][i] for i in range(6)] == m.songs
           and [c for c in calls if c[0] == 'select_recordinit'] == [('select_recordinit', 6)] and [c[1] for c in calls if c[0] == 'set_selectindex'] == [1, 3],
           'on the picker\'s copy of the list, the stock vector filled from the marks')
    expect(('toast', 'msg_addfavsuccess', 1, 2000) in calls and ('window_close', m.window) in calls and not [c for c in calls if c[0] in ('navigator_back', 'createPlayListItem')]
           and not [c for c in calls if c[0] == 'toast' and c[1] != 'msg_addfavsuccess'],
           'the stock "Added To Fav" message, then the picker\'s window is closed')
    calls = PL.tap(m, 100, PL.TOP + 3 * ROW + 20)
    expect(not [c for c in calls if c[0] == 'batch_add_file'], 'a second tap (on a playlist) adds nothing again')
    destroy(m)
    expect(record_ok(m), 'the page gone: the caller\'s browsing record is back')

    # 3. New playlist: our keyboard; its Done creates the playlist and adds to it; a name that cannot be made leaves the picker open
    m = caller(PL)
    open_picker(m); PL.settle(m)
    m.calls = []
    calls = PL.tap(m, 100, PL.TOP + 20)
    expect(('window_open', 'm1plus_keyboard') in calls and not [c for c in calls if c[0] in ('batch_add_file', 'createPlayListItem', 'window_close')],
           'the New playlist row opens the keyboard; nothing is made or added yet')
    for ret, key in ((-1, 'msg_playlistfull'), (-2, 'msg_playlistexist')):
        m.create_ret = ret
        m.call(PSYMS['pl_named'], a0=m.cstr('Mix'), count=40000000)
        expect([c for c in m.calls if c[0] == 'toast'] == [('toast', key, 1, 2000)] and not [c for c in m.calls if c[0] in ('batch_add_file', 'window_close')],
               f'{key}: the stock message, nothing added, the picker stays')
    m.create_ret = 9
    m.call(PSYMS['pl_named'], a0=m.cstr('Mix'), count=40000000)
    expect(('createPlayListItem', 'Mix', 3) in m.calls and ('timer_add', PSYMS['pl_pick_fire']) == m.calls[[c[0] for c in m.calls].index('timer_add')][:2]
           and not [c for c in m.calls if c[0] in ('batch_add_file', 'toast', 'window_close', 'select_recordinit')],
           'Done (run from the keyboard\'s click handler, its page still closing): the playlist is made and the add waits on a timer: no add, message or window_close yet')
    m.call(PSYMS['pl_pick_fire'], count=40000000)
    add = [c for c in m.calls if c[0] == 'batch_add_file']
    expect(len(add) == 1 and add[0][1:3] == (CLS, O['CLASS_PLAYLISTS']) and add[0][5] == 9 and add[0][6] == [1, 3]
           and ('toast', 'msg_addplaylistsuccess', 1, 2000) in m.calls and ('window_close', m.window) in m.calls,
           'the timer: the new playlist (id 9) gets the marked songs, the message, the page closes')
    expect(m.fs.get('/mnt/data/m1plus/playlists-meta') == b'M1PLMETA 1\n9 %d %d 0 Mix\n' % (m.wall, m.wall + 1), f'the new playlist has its Date Added, then the add stamps it as updated ({m.fs.get("/mnt/data/m1plus/playlists-meta")})')
    expect(record_ok(m), 'the browsing record is the caller\'s after the creating queries')
    destroy(m)
    # Back (or anything that ends the page) before the timer fires: the timer is removed and nothing is added
    m = caller(PL)
    open_picker(m); PL.settle(m)
    m.create_ret = 9
    m.call(PSYMS['pl_named'], a0=m.cstr('Mix'), count=40000000)
    destroy(m)
    expect(any(c[0] == 'timer_remove' for c in m.calls), 'a page that ends before the add timer fires removes the timer')
    # the row: plus and centred title
    m = caller(PL)
    open_picker(m); PL.settle(m)
    blits, texts, styles = PL.paint(m)
    white = sorted((f[3], f[4]) for f in m.fills if f[0] == 0xffffffff)
    expect([f for f in m.fills if f[0] == 0xff2e2c2c and f[3] == O['LIST_ART'] and f[4] == O['LIST_ART'] - 4] and white == [(2, 20), (20, 2)],
           f'the New playlist row paints a dark square and a white plus (two bars, {white})')
    title0 = next(x for x, s in zip(texts, styles) if s == 'label_row_title')
    expect(title0[1][1] == PL.TOP + (ROW - O['LIST_TITLE_H']) // 2, f'the New playlist title is centred in the row ({title0})')

    # the Favourites row: the same dark square and a 24 px star (an alpha bitmap), centred in the art box, titled "Favorites" and centred like New playlist
    ay = PL.TOP + ROW + O['LIST_ART_Y']
    star = [b for b in blits if b[2][2] == 24 and b[2][3] == 24 and b[2][1] == ay + (O['LIST_ART'] - 24) // 2]
    expect(len([f for f in m.fills if f[0] == 0xff2e2c2c and f[3] == O['LIST_ART'] and f[4] == O['LIST_ART'] - 4]) == 2 and len(star) == 1
           and star[0][2][0] == O['LIST_ART_X'] + (O['LIST_ART'] - 24) // 2, f'the Favorites row paints the dark square and the star centred in it ({star})')
    if star:
        a = lambda x, y: PL.pixel(m, star[0][0], x, y) >> 24
        rgb = {PL.pixel(m, star[0][0], x, y) & 0xffffff for x in range(24) for y in range(24)}
        expect(a(12, 12) == 255 and a(12, 4) > 200 and a(0, 0) == 0 and a(23, 0) == 0 and a(1, 9) == 0 and a(12, 0) == 0 and a(5, 20) == 0 and a(7, 19) > 0 and a(12, 19) == 0 and rgb == {0xffffff},
               'the star: opaque at its centre and top point, empty at the corners, white')
    title1 = [x for x, s in zip(texts, styles) if s == 'label_row_title'][1]
    expect(title1[0] == 'Favorites' and title1[1][1] == PL.TOP + ROW + (ROW - O['LIST_TITLE_H']) // 2, f'the Favorites title is centred in its row ({title1})')

    # 4. Back: nothing added
    m = caller(PL)
    open_picker(m); PL.settle(m)
    m.calls = []
    m.click('btn_return')
    expect(('navigator_back',) in m.calls and not [c for c in m.calls if c[0] in ('batch_add_file', 'toast')], 'Back closes the picker with nothing added')
    m.u.mem_write(NAV_TITLE, b'x\0')
    destroy(m)
    expect(record_ok(m), 'and the browsing record is put back')

    # 5. Where it cannot open: -1 and nothing left behind (the caller falls back to the stock picker)
    m = caller(PL)
    r, calls = open_picker(m, count=5)
    expect(r == 0xffffffff and not [c for c in calls if c[0] == 'window_open'], 'a list that is not the one the marks are of: -1, no window')
    m.setword(SHOWLIST, 0)
    r, calls = open_picker(m)
    expect(r == 0xffffffff, 'no stock list: -1')
    m = caller(PL, {'m1plus_playlists': 0})
    r, calls = open_picker(m)
    expect(r == 0xffffffff and record_ok(m), 'a window that does not open: -1')
    m.windows.clear()
    r, calls = open_picker(m)
    expect(r == 1, 'and the state it left lets a picker open afterwards')
    destroy(m)
    m.calls = []
    r, calls = open_picker(m, count=6)
    expect(r == 1, 'a picker opens again after the last one went')
    r2, calls = open_picker(m)
    expect(r2 == 0xffffffff, 'but not twice')
    destroy(m)

    # 6. Over our own Songs page of a playlist (the Playlists page is below it): that page's state comes back when the picker goes
    m = caller(PL)
    PL.open_page(m); PL.settle(m)
    first_bound = m.bound[(m.window, O['EVT_DESTROY'])]
    m.setword(SHOWLIST, m.new_deque(m.songs))   # (the first page's scans replaced the caller's list and record: the caller reads and sets them again)
    m.u.mem_write(NAV_TITLE, b'Songs title\0'); m.setword(G_CLASS, CLS); m.setword(CLASSINFO, CLS); m.setword(CLASSINFO + 4, 77)
    r, calls = open_picker(m)
    expect(r == 1, 'the picker opens over a Playlists page that is already open')
    blits, texts, styles = PL.settle(m)
    expect([x[0] for x, s in zip(texts, styles) if s == 'label_row_title'][:2] == ['playlist_create', 'Favorites'], 'the picker is the list with New playlist and Favorites first')
    destroy(m)
    blits, texts, styles = PL.paint(m)
    expect([x[0] for x, s in zip(texts, styles) if s == 'label_grid_title'][:3] == ['Focus', 'Late Night', 'Road Trip'] and first_bound,
           'the Playlists page below is as it was: its grid, its tiles')
    expect(record_ok(m), 'and the caller\'s record is back')

    # 7. One record that is in no shown list (Now Playing's Add to playlist, patch/playmore.c pm_on_addpl): a one-row copy, marked; *pdeq_showlist is not read
    m = caller(PL)
    rec = m.record(title='Playing', path='/mnt/mmc/p/1.flac', rid=900)
    m.setword(SHOWLIST, 0); m.calls = []
    r = m.call(PSYMS['picker_open_rec'], a0=CLS, a1=rec, count=60000000)
    expect(r == 1 and ('window_open', 'm1plus_playlists') in m.calls and not [c for c in m.calls if c[0] == 'navigator_to_with_context'],
           'picker_open_rec opens our Playlists page (1) with no stock list at all')
    r2 = m.call(PSYMS['picker_open_rec'], a0=CLS, a1=rec, count=60000000)
    expect(r2 == 0xffffffff, 'but not twice')
    PL.settle(m)
    calls = PL.tap(m, 100, PL.TOP + 3 * ROW + 20)
    add = [c for c in calls if c[0] == 'batch_add_file']
    expect(len(add) == 1 and add[0][1:3] == (CLS, O['CLASS_PLAYLISTS']) and add[0][5] == 2 and add[0][6] == [0] and m.deques[add[0][3]] == [rec]
           and [c for c in calls if c[0] == 'select_recordinit'] == [('select_recordinit', 1)] and ('toast', 'msg_addplaylistsuccess', 1, 2000) in calls and ('window_close', m.window) in calls,
           f'a tap on Late Night: batch_add_file({CLS:#x}, 0xf00b, the one-row list, the stock vector, 2) with row 0 selected, the message, the page closes ({add})')
    destroy(m)
    expect(record_ok(m), 'the page gone: the browsing record is as it was')
    r = m.call(PSYMS['picker_open_rec'], a0=CLS, a1=0, count=60000000)
    expect(r == 0xffffffff and not [c for c in m.calls[-3:] if c[0] == 'window_open'], 'no record: -1')
    m = caller(PL, {'m1plus_playlists': 0})
    r = m.call(PSYMS['picker_open_rec'], a0=CLS, a1=m.record(rid=901), count=60000000)
    expect(r == 0xffffffff and record_ok(m), 'a window that does not open: -1, nothing left behind')
    m.windows.clear()
    r, calls = open_picker(m)
    expect(r == 1, 'and a picker opens afterwards')
    destroy(m)

    # 8. Already there: a row that holds every song being added (by path and CUE span) shows the Add Songs page's grey tick where the "..." would be, its texts end before it,
    #    and a tap says so and adds nothing (the picker stays); a row that holds some adds as before and says how many of them were added
    import mod_icons
    PX = O['RM_DOTS_PX']
    si = mod_icons.songs_images()

    def there(fav=True, marks=0b00001010, folder=None):
        m = caller(PL)
        m.images['sg_pdone'] = (PX, PX, b''.join(struct.pack('<4B', c, c, c, 255) for c in si['sg_pdone'].getchannel('A').tobytes()))   # (the red channel is the coverage)
        m.songs = [m.record(title=f'S{i}', path=f'/mnt/mmc/m/{i}/1.flac', rid=100 + i) for i in range(6)]   # the playlists' paths: rows 1 and 3 are in Road Trip, row 1 in Late Night
        if folder is not None: m.setword(m.songs[folder] + O['REC_TYPE'], 4)   # a Folders page folder (stock adds its direct audio files)
        m.setword(SHOWLIST, m.new_deque(m.songs)); m.u.mem_write(m.sel, bytes([marks]))
        if fav: m.fav_rows = [(f'{i}.flac', f'/mnt/mmc/m/{i}/1.flac', f'S{i}') for i in (1, 3, 5)]
        open_picker(m); PL.settle(m)
        return m

    def ticks(m):
        blits, texts, styles = PL.paint(m)
        got = []
        for b in blits:
            if b[2][2:] == (PX, PX) and b[0] in m.bitmaps:
                data = m.bitmaps[b[0]][0]
                if struct.unpack('<I', bytes(m.u.mem_read(data + 4 * (PX * (PX // 2) + PX // 2), 4)))[0] & 0xffffff == O['SG_HANDLE_RGB']:
                    got.append(((b[2][1] - PL.TOP) // ROW, b[2][0]))
        widths = {t: w for (t, (x, y, w, h)), s in zip(texts, styles) if s == 'label_row_title'}
        return sorted(got), widths

    m = there()
    got, widths = ticks(m)
    expect([r for r, x in got] == [1, 4] and all(x >= O['LIST_TEXT_X'] + widths['Road Trip'] for r, x in got),
           f'the grey tick on Favorites and Road Trip (both hold rows 1 and 3), not on Late Night (one of them) or Focus, right of the texts ({got})')
    expect(widths['Road Trip'] < widths['Late Night'] == widths['Focus'] == O['LIST_TEXT_W'] and widths['Favorites'] == widths['Road Trip'],
           f'a ticked row\'s texts end before the tick; the others run to LIST_TEXT_W ({widths})')
    expect(record_ok(m), 'the browsing record is put back after the Favourites query')
    for y, key in ((4, 'Already in Playlist'), (1, 'Already in Favorites')):
        m.calls = []
        calls = PL.tap(m, 100, PL.TOP + y * ROW + 20)
        expect([c for c in calls if c[0] == 'toast'] == [('toast', key, 1, 2000)] and not [c for c in calls if c[0] in ('batch_add_file', 'window_close', 'select_recordinit')],
               f'a tap on a ticked row: "{key}", nothing added, the picker stays')
    calls = PL.tap(m, 100, PL.TOP + 3 * ROW + 20)
    add = [c for c in calls if c[0] == 'batch_add_file']
    expect(len(add) == 1 and add[0][5] == 2 and add[0][6] == [1, 3] and ('toast', 'Added 1 of 2 songs', 1, 2000) in calls and ('window_close', m.window) in calls,
           f'a tap on Late Night (holds one of the two): the add as before (stock skips the one there), "Added 1 of 2 songs", the page closes ({add})')
    destroy(m)

    m = there(fav=False, marks=0b00100000)   # row 5 alone: Focus holds it, Favourites is empty
    got, widths = ticks(m)
    expect([r for r, x in got] == [2] and widths['Road Trip'] == widths['Favorites'] == O['LIST_TEXT_W'], f'the tick follows the songs being added: Focus only ({got})')
    calls = PL.tap(m, 100, PL.TOP + ROW + 20)
    expect(('toast', 'msg_addfavsuccess', 1, 2000) in calls and [c for c in calls if c[0] == 'batch_add_file'], 'and the add is the stock one')
    destroy(m)

    m = there(folder=3)   # rows 1 and 3, row 3 a folder: the songs being added are not the rows, so no row is said to hold them
    got, widths = ticks(m)
    calls = PL.tap(m, 100, PL.TOP + 3 * ROW + 20)
    expect(got == [] and ('toast', 'msg_addplaylistsuccess', 1, 2000) in calls and [c for c in calls if c[0] == 'batch_add_file'],
           f'a folder among the marks: no tick, a tap on Late Night adds with the stock message, not "Added 1 of 2 songs" ({got})')
    destroy(m)

    m = caller(PL)   # Now Playing's one song (picker_open_rec): Road Trip and Late Night both hold it
    m.images['sg_pdone'] = (PX, PX, b''.join(struct.pack('<4B', c, c, c, 255) for c in si['sg_pdone'].getchannel('A').tobytes()))
    m.setword(SHOWLIST, 0)
    m.call(PSYMS['picker_open_rec'], a0=CLS, a1=m.record(title='Playing', path='/mnt/mmc/m/1/1.flac', rid=900), count=60000000)
    PL.settle(m)
    got, widths = ticks(m)
    expect([r for r, x in got] == [3, 4], f'one record (Now Playing): the tick on both playlists that hold it ({got})')
    destroy(m)

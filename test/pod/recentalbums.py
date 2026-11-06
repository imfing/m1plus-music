"""Recently Added's album view (patch/songs.c, docs/modules/recent-albums.md): the navbar toggle of the Recently Added list on the Songs page, the newest-first Albums grid
read from the full `time_create desc` query (grouped by library album, a compilation's tracks in one, untagged songs skipped, at most 60), the navbars of the two views, the
remembered choice (recently-added-view), the songs view reading its own 0xf009 list after the album view's query replaced the stock list, and a tap opening our album page."""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

SG = sibling('songs')

RECENT, ALL, ALBUMS = O['CLASS_RECENTADD'], O['CLASS_ALL_SONGS'], O['CLASS_ALBUMS']
VIEW_FILE, VIEW_TMP = '/mnt/data/m1plus/recently-added-view', '/mnt/data/m1plus/recently-added-view.tmp'
TOP, ROW, PITCH, COVER, MARGIN, GAP, VIEW_H = O['SG_PILL_Y'], O['LIST_ROW_H'], O['GRID_COVER'] + O['GRID_TITLE_GAP'] + O['GRID_TITLE_H'] + O['GRID_SUB_H'] + O['GRID_ROW_GAP'], O['GRID_COVER'], O['GRID_MARGIN'], O['GRID_GAP'], O['GRID_VIEW_H']
SORT_FLAG, SHOWLIST = SG.SORT_FLAG, SG.SHOWLIST
SC_YOFF = O['SC_YOFF']
EXTRA = ('btn_albumview', 'label_grid_title', 'label_grid_sub')

# The library, newest first (what `select * from songtable ORDER BY time_create desc` returns): (title, artist, album)
NEWEST = [('n0', 'Anna', 'Alpha'), ('n1', 'Various', 'Mix'), ('n2', 'anna', 'ALPHA'), ('n3', 'Nobody', ''), ('n4', 'Other', 'Mix'), ('n5', 'Bob', 'Beta'),
          ('n6', 'Cy', 'Gamma'), ('n7', 'Various', 'Mix'), ('n8', 'Cy', 'Delta')]
EXPECT = ['Alpha', 'Mix', 'Beta', 'Gamma', 'Delta']   # first appearance, newest first, one per album (NOCASE), the untagged skipped


class FlagMachine(SG.SongsMachine):
    """The query log with the sort_flag each loadLocalClassList ran under."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.flags = []

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'loadLocalClassList': self.flags.append((u.reg_read(UC_MIPS_REG_A0), self.word(SORT_FLAG)))
        return super()._hook(u, address, size, _)


def recent_machine(songs=NEWEST, shown=3, view=None, extra=True):
    """The Songs page's machine with Recently Added: class 0xf001 is the whole library newest first, class 0xf009 (the stock `limit 100` query) its first `shown` songs reversed
    (so the two lists differ), the library's albums one row per album name (as getAllAlbum groups). view: the recently-added-view file."""
    orig = SG.SongsMachine
    SG.SongsMachine = FlagMachine
    try:
        m = SG.list_machine(songs, None)
    finally:
        SG.SongsMachine = orig
    if extra:
        for n in EXTRA: Machine.widget(m, n)
    for r, (title, artist, album) in zip(m.songs, songs):
        if not album: m.setword(r + O['REC_ALBUM'], m.cstr(''))
    m.class_lists[RECENT] = list(reversed(m.songs[:shown]))
    seen, lib = {}, []
    for (title, artist, album) in songs:
        if album and album.lower() not in seen:
            seen[album.lower()] = len(lib)
            lib.append(m.record(album=album, artist=artist, path=f'/mnt/mmc/lib/{len(lib)}.flac', rid=900 + len(lib)))
    m.class_lists[ALBUMS] = lib
    m.lib_row = seen
    if view is not None: m.fs[VIEW_FILE] = view
    return m


def open_recent(m):
    m.call(PSYMS['songs_open_list'], a0=O['HOME_RECENTADD'], count=900000000)
    return list(m.calls)


def shown_titles(texts, titles): return [t for t, r in texts if t in titles]
def vis(m, n): return SG.vis(m, n)
def glyph(m): return m.props.get((m.widgets['btn_albumview'], 'style:normal:icon'))
def moves(m, name): return [c[2] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[name]]


def asset_tests(ctx):
    """1. The asset and the plumbing: the toggle (hidden, the Albums page's slot and glyph), the grid's two text styles, the setting file."""
    expect = ctx.expect
    f = SG.ui().find
    tb = f('btn_albumview')
    expect((tb.x, tb.w, tb.h) == (O['NAV_VIEW_X'], 46, 50) and tb.get('style:normal:icon') == 'pod_nav_grid' and tb.get('style:pressed:icon') == 'pod_nav_grid_down'
           and tb.get('visible') == 'false' and tb.get('sensitive') == 'false' and tb.get('style') == 'img_btn_style' and tb.get('dirty_rect_tolerance') == '7',
           'the Songs asset has the Albums page\'s view toggle: slot 214, the grid glyph, built hidden and insensitive (the payload shows it on Recently Added only)')
    gt, gs = f('label_grid_title'), f('label_grid_sub')
    expect(gt.get('visible') == 'false' and gs.get('visible') == 'false' and gt.get('style:normal:font_size') == '18' and gs.get('style:normal:font_size') == '15'
           and gt.get('style:normal:text_color') == '#FFFFFF' and gs.get('style:normal:text_color') == '#AAAAAA', 'the Albums grid\'s two text styles are hidden labels of the page (18 px white, 15 px grey)')
    expect(O['REC_TIME_CREATE'] == 0x50 and O['REC_TIME_CREATE'] < O['REC_SIZE'] and O['REC_INITIAL'] == 0x54, 'offsets.inc names stSongInfo\'s time_create at +0x50')
    expect('recently-added-view' in pod_pages.SETTING_FILES and pod_pages.SETTING_FILES.index('recently-added-view') == pod_pages.SETTING_FILES.index('playlists-view') + 1,
           'recently-added-view is a Settings Files row (after the Albums and Playlists views)')
    expect(pod_ui.TOGGLE_NAME['grid'] == 'btn_albumview' and f('btn_search').x == 122 and f('btn_select').x == 214, 'the asset\'s own slots stay the library Songs page\'s (the payload moves Select on Recently Added)')


def songs_view_tests(ctx):
    """2. The songs view (the default): the page as before with the capsule Search 122 | Select 168 | toggle 214 | Now Playing, no small title; the other lists are unchanged."""
    expect = ctx.expect
    m = recent_machine()
    calls = open_recent(m)
    m.calls = calls
    expect([c[1] for c in calls if c[0] == 'loadLocalClassList'] == [ALBUMS, RECENT] and 'rv_enter' not in m.names(), 'the page opens on the songs: the library\'s albums, then class 0xf009 (no full query)')
    expect(vis(m, 'btn_albumview') == (1, 1) and vis(m, 'btn_sort') == (0, 0) and vis(m, 'btn_select') == (1, 1) and vis(m, 'btn_search') == (1, 1),
           'the toggle is shown beside Search and Select, Sort is hidden')
    expect(moves(m, 'btn_select') == [O['NAV_CF_X']] and not moves(m, 'btn_search') and ('widget_resize', m.widgets['label_title'], 122 - 58, 22) in calls,
           'Select takes Sort\'s slot 168, Search stays at 122 (the capsule: Search 122 | Select 168 | toggle 214 | Now Playing 260)')
    expect(glyph(m) is None, 'the toggle starts with the asset\'s grid glyph ("show as albums")')
    titles = [t for t, _, _ in NEWEST]
    blits, texts, styles, fills = SG.settle(m)
    expect(shown_titles(texts, titles)[:3] == ['n2', 'n1', 'n0'] and vis(m, 'btn_play') == (1, 1), f'the rows are the 0xf009 list in its order ({shown_titles(texts, titles)[:3]})')
    m.setword(m.sv + SC_YOFF, 300)
    m.call(PSYMS['sg_on_scroll'], count=4000000)
    expect([c for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['label_title'] and c[2]], 'the small title shows once scrolled, as on the other lists (cut to its room before x 122)')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    for label, home, cls in (('Favorites', 'HOME_FAV', 'CLASS_FAV'), ('Hi-Res', 'HOME_HIRES', 'CLASS_HIRES')):
        m = recent_machine(); m.class_lists[O[cls]] = list(m.songs[:3])
        m.call(PSYMS['songs_open_list'], a0=O[home], count=900000000)
        expect(moves(m, 'btn_search') == [O['NAV_CF_X']] and not moves(m, 'btn_select') and not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['btn_albumview'] and c[2]],
               f'{label}: unchanged (Search moves to Sort\'s slot, no toggle)')
        m.call(PSYMS['sg_on_view'], count=4000000)
        expect(('loadLocalClassList', ALL) not in m.calls and VIEW_FILE not in m.fs, f'{label}: the toggle handler does nothing')
        m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = recent_machine(); m.call(PSYMS['songs_open'], count=900000000)
    expect(not moves(m, 'btn_select') and not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['btn_albumview'] and c[2]], 'the library Songs page is unchanged: no toggle, Select stays at 214')
    m = recent_machine(extra=False)
    open_recent(m)
    expect(moves(m, 'btn_search') == [O['NAV_CF_X']] and not moves(m, 'btn_select'), 'an asset without the toggle keeps the plain list\'s capsule')


def album_view_tests(ctx):
    """3. The album view: the full query (sort_flag 3, put back), the grouping, the grid, the navbar, the saved choice; 4. back to the songs; 5. a tap opens the album page."""
    expect = ctx.expect
    m = recent_machine()
    open_recent(m); SG.settle(m)
    m.setword(SORT_FLAG, 2)   # the user's sort order of the library must survive the query
    m.flags.clear(); m.calls.clear()
    calls = SG.click(m, 'btn_albumview')
    expect(m.flags == [(ALL, 3)] and m.word(SORT_FLAG) == 2 and not any(c[0] == 'write_int_config' for c in calls),
           f'the toggle runs the full time_create query: getAllMusic under sort_flag 3 ("Time added (descending)"), the library\'s flag put back, nothing saved ({m.flags})')
    expect([c[1] for c in calls if c[0] == 'loadLocalClassList'] == [ALL] and m.word(O['PDEQ_SHOWLIST'] if 'PDEQ_SHOWLIST' in O else SHOWLIST) is not None,
           'one stock query, the full library list')
    expect(m.fs.get(VIEW_FILE) == b'1\n' and VIEW_TMP not in m.fs and ('fsync', VIEW_TMP) in calls and ('fsync', '/mnt/data/m1plus') in calls and ('rename', VIEW_TMP, VIEW_FILE) in calls,
           'the choice is saved atomically ("1"): temporary file, fsync, rename, directory fsync')
    expect(glyph(m) == 'pod_nav_list' and m.props.get((m.widgets['btn_albumview'], 'style:pressed:icon')) == 'pod_nav_list_down', 'the toggle shows the list glyph ("show as songs")')
    expect(vis(m, 'btn_select') == (0, 0) and vis(m, 'btn_play') == (0, 0) and vis(m, 'btn_shuffle') == (0, 0) and vis(m, 'btn_albumview') == (1, 1) and vis(m, 'btn_search') == (1, 1)
           and vis(m, 'btn_backtoplayer') == (1, 1) and moves(m, 'btn_search')[-1] == O['NAV_CF_X'],
           'the capsule is Search 168 | toggle 214 | Now Playing 260: Select hidden and insensitive, no Play / Shuffle pills')
    expect(m.props.get((m.widgets['sg_foot'], 'visible')) == 0 and vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status') == (0, 0), 'no song count under the albums, no empty-list line')
    rows = (len(EXPECT) + 1) // 2
    expect(m.props[(m.sv, 'virtual_h')] == TOP + rows * PITCH, f'the content is the title block and {rows} grid rows ({m.props[(m.sv, "virtual_h")]})')
    blits, texts, styles, fills = SG.settle(m)
    names = [t for t, r in texts if t in EXPECT]
    expect(names == EXPECT[:4], f'the albums, newest first, one tile per album (a compilation\'s tracks and the same name in another case in one; the song with no album skipped), the second row\'s cut by the window too: {names}')
    expect(set(styles) == {'label_grid_sub', 'label_grid_title'}, f'drawn in the Albums grid\'s text styles ({set(styles)})')
    dst = [b[2] for b in blits if m.bitmaps[b[0]][1:] == (COVER, COVER)]
    want = [[MARGIN + c * (COVER + GAP), TOP + r * PITCH, COVER, COVER] for r in range(rows) for c in range(2)]
    expect([list(d) for d in dst][:4] == want[:4] and len(dst) == 4, f'two columns of {COVER} px covers from y {TOP} (where the pills begin), the Albums page\'s cell geometry ({dst})')
    m.setword(m.sv + SC_YOFF, TOP + rows * PITCH - VIEW_H)
    blits, texts, styles, fills = SG.paint(m)
    expect([t for t, r in texts if t in EXPECT] == EXPECT[2:], f'scrolled to the end: the rest of the albums, in order ({[t for t, r in texts if t in EXPECT]})')
    expect(not any(t in [t2 for t2, _, _ in NEWEST] for t, r in texts), 'no song row is drawn')
    m.setword(m.sv + SC_YOFF, 0)

    # 4. back to the songs: the page reads its own list again (the full query replaced the stock list)
    m.flags.clear(); m.calls.clear()
    calls = SG.click(m, 'btn_albumview')
    expect([c[1] for c in calls if c[0] == 'loadLocalClassList'] == [RECENT] and m.flags == [(RECENT, 2)], 'back on the songs: class 0xf009 is read again, nothing else')
    expect(m.fs.get(VIEW_FILE) == b'0\n' and glyph(m) == 'pod_nav_grid' and vis(m, 'btn_select') == (1, 1) and vis(m, 'btn_play') == (1, 1) and vis(m, 'btn_shuffle') == (1, 1)
           and moves(m, 'btn_search')[-1] == O['NAV_SEARCH_X'] and m.props.get((m.widgets['sg_foot'], 'visible')) == 1, '"0" saved, the grid glyph, Select and the pills back, Search back at 122')
    blits, texts, styles, fills = SG.settle(m)
    expect(shown_titles(texts, [t for t, _, _ in NEWEST])[:3] == ['n2', 'n1', 'n0'] and not [t for t, r in texts if t in EXPECT], f'the songs view shows its own 0xf009 list, not the album view\'s ({shown_titles(texts, ["n0", "n1", "n2"])})')
    # and the albums again, from a fresh query
    m.flags.clear(); m.calls.clear()
    SG.click(m, 'btn_albumview')
    blits, texts, styles, fills = SG.settle(m)
    expect(m.flags == [(ALL, 3)] and [t for t, r in texts if t in EXPECT] == EXPECT[:4], 'toggling again reads the full list again and shows the same albums')

    # nothing of the stock list is read while the album view is up: a replaced list is not stale for it
    m.calls.clear()
    m.setword(SHOWLIST, m.new_deque([m.songs[5]]))
    m.call(PSYMS['sg_on_fg'], count=4000000)
    blits, texts, styles, fills = SG.paint(m)
    bad = [c for c in m.calls if c[0] in ('loadLocalClassList', 'timer_add') and (c[0] != 'timer_add' or c[1] == PSYMS['sg_on_stale'])]
    expect(not bad and [t for t, r in texts if t in EXPECT] == EXPECT[:4], f'{bad}'
           'back in front, or painted, with the stock list replaced: no query, no stale timer, the albums as they were')
    # select mode is not offered
    m.calls.clear(); m.call(PSYMS['sg_on_select'], count=4000000)
    expect(vis(m, 'sg_bar')[0] == 1 and not [c for c in m.calls if c[0] in ('widget_set_visible',) and c[1] == m.widgets['sg_bar'] and c[2]], 'Select does nothing in the album view')

    # 5. a tap on an album opens our album page: the Albums page's call (cc_open_album with the library row)
    m = recent_machine()
    open_recent(m); SG.click(m, 'btn_albumview'); SG.settle(m)
    for cell, name in ((0, 'Alpha'), (1, 'Mix'), (3, 'Gamma')):
        m.calls.clear()
        row = m.lib_row[name.lower()]
        calls = SG.tap(m, MARGIN + cell % 2 * (COVER + GAP) + 20, TOP + cell // 2 * PITCH + 20)
        ao = [c for c in calls if c[0] == 'album_open']
        expect([c[1] for c in calls if c[0] == 'loadAlbumList'] == [ALBUMS] and ao and ao[0][2] == 900 + row,
               f'a tap on {name} loads the library albums and opens its album page (row {row}: {ao})')
        nav = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']
        expect(nav and nav[0][2:4] == (ALBUMS, row), f'(the stock page when ours will not open: class and row {nav})')
    m.calls.clear()
    calls = SG.tap(m, 150, 20)   # the large title
    expect(not [c for c in calls if c[0] in ('loadAlbumList', 'album_open')], 'the title block opens nothing')
    calls = SG.tap(m, MARGIN + 20, TOP + 20, dx=20)
    expect(not [c for c in calls if c[0] in ('loadAlbumList', 'album_open')], 'a drag opens nothing')
    calls = SG.tap(m, MARGIN + 2 * COVER + GAP - 2 + 6, TOP + 20)
    expect(not [c for c in calls if c[0] in ('loadAlbumList', 'album_open')], 'the margin opens nothing')
    # back to the page: still the album view
    m.call(PSYMS['sg_on_destroy'], count=4000000)


def data_tests(ctx):
    """6. The data: the cap of 60 albums, the library row of a compilation's tracks, untagged songs, an empty library, the memory failure."""
    expect = ctx.expect
    many = [(f's{i}', f'Artist {i}', f'Album {i:02d}') for i in range(75)]
    m = recent_machine(many, shown=5)
    open_recent(m); SG.click(m, 'btn_albumview'); SG.settle(m)
    expect(m.props[(m.sv, 'virtual_h')] == TOP + 30 * PITCH, f'75 albums: the newest 60 are kept, 30 grid rows ({m.props[(m.sv, "virtual_h")]})')
    m.setword(m.sv + SC_YOFF, 30 * PITCH + TOP - VIEW_H)
    blits, texts, styles, fills = SG.paint(m)
    last = [t for t, r in texts if t.startswith('Album ')]
    expect(last and last[-1] == 'Album 59' and 'Album 60' not in last, f'the last tile is the 60th newest ({last[-2:]})')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    # a compilation: tracks under different artists are one tile, with the library row's cover (the cache is keyed by that row's artist)
    comp = [('t0', 'Various', 'Hits'), ('t1', 'Zed', 'Hits'), ('t2', 'Ann', 'Solo')]
    m = recent_machine(comp, shown=2)
    open_recent(m); SG.click(m, 'btn_albumview'); blits, texts, styles, fills = SG.settle(m)
    expect([t for t, r in texts if t in ('Hits', 'Solo')] == ['Hits', 'Solo'] and len([b for b in blits if m.bitmaps[b[0]][1:] == (COVER, COVER)]) == 2, 'a compilation is one tile')
    lib_url = 'file://' + art_file(album_key('Various', 'Hits'))
    expect(lib_url in m.loads and 'file://' + art_file(album_key('Zed', 'Hits')) not in m.loads, 'its cover is the library album\'s cache file (the library row\'s artist keys it)')

    # every song without an album: nothing to show
    m = recent_machine([('a', 'X', ''), ('b', 'Y', '')], shown=2)
    open_recent(m); calls = SG.click(m, 'btn_albumview')
    expect(vis(m, 'view_grid') == (0, 0) and vis(m, 'label_status') == (1, 1) and [c for c in calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['label_status'] and 'No albums' in c], 'no albums: the "No albums" line, the grid hidden')
    calls = SG.click(m, 'btn_albumview')
    expect(vis(m, 'view_grid') == (1, 1) and m.fs.get(VIEW_FILE) == b'0\n', 'and the toggle still goes back to the songs')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    # no memory for the list: the page stays on the songs, nothing saved
    m = recent_machine(); open_recent(m)
    m.calloc_fail_size = 4 * 60
    m.calls.clear()
    calls = SG.click(m, 'btn_albumview')
    m.calloc_fail_size = 0
    expect(VIEW_FILE not in m.fs and glyph(m) is None and ('loadLocalClassList', ALL) not in calls and vis(m, 'btn_play') == (1, 1), 'no memory for the album list: the page stays on the songs, nothing is queried or saved')


def state_tests(ctx):
    """7. The remembered choice at open, the select mode round trip, the foreground handlers."""
    expect = ctx.expect
    for data, albums in ((b'1\n', True), (b'1', True), (b'0\n', False), (b'x', False), (None, False)):
        m = recent_machine(view=data)
        calls = open_recent(m)
        queries = [c[1] for c in calls if c[0] == 'loadLocalClassList']
        expect(queries == ([ALBUMS, RECENT, ALL] if albums else [ALBUMS, RECENT]) and (glyph(m) == 'pod_nav_list') == albums,
               f'recently-added-view {data!r}: opens on the {"albums" if albums else "songs"} ({queries})')
        blits, texts, styles, fills = SG.settle(m)
        expect(bool([t for t, r in texts if t in EXPECT]) == albums and (vis(m, 'btn_select') == (0, 0)) == albums, f'recently-added-view {data!r}: and shows them')
        m.call(PSYMS['sg_on_destroy'], count=4000000)

    # select mode hides the toggle and brings it back; the toggle does nothing in select mode
    m = recent_machine(); open_recent(m); SG.settle(m)
    SG.click(m, 'btn_select')
    expect(vis(m, 'btn_albumview') == (0, 0) and vis(m, 'btn_search') == (0, 0) and vis(m, 'sg_bar') == (1, 1), 'select mode hides the capsule, the toggle too')
    m.calls.clear(); m.call(PSYMS['sg_on_view'], count=4000000)
    expect(('loadLocalClassList', ALL) not in m.calls, 'the toggle does nothing in select mode')
    SG.click(m, 'btn_return')
    expect(vis(m, 'btn_albumview') == (1, 1) and vis(m, 'btn_select') == (1, 1), 'leaving select mode shows the capsule again')
    # a stock list replaced under the songs view (another page's query) is still read again; toggling in between does not confuse it
    SG.click(m, 'btn_albumview'); SG.click(m, 'btn_albumview')
    m.setword(SHOWLIST, m.new_deque([m.songs[5]]))
    m.calls.clear(); m.call(PSYMS['sg_on_fg'], count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [RECENT], 'the songs view still reads its list again when another query replaced it')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # destroying the page in the album view frees the grid (no leak, no timer)
    m = recent_machine(); open_recent(m); SG.click(m, 'btn_albumview'); SG.settle(m)
    m.calls.clear(); m.call(PSYMS['sg_on_destroy'], count=4000000)
    expect(not [c for c in m.calls if c[0] == 'timer_add'], 'destroying the page in the album view adds no timer')


SECTIONS = [asset_tests, songs_view_tests, album_view_tests, data_tests, state_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)

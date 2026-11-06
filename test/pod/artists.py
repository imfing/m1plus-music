"""Artists: the list page and Cover Flow scoped to one artist."""
import os, struct
import mod_icons
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

VIEW_H, TOP, HDR, ROW, BOTTOM = O['GRID_VIEW_H'], O['SG_TITLE_H'], O['SG_HDR_H'], 52, 12
TEXT_X, TEXT_Y, TEXT_H, TEXT_END = 24, (52 - O['LIST_TITLE_H']) // 2, O['LIST_TITLE_H'], 252
CHEV_X, CHEV_W, CHEV_H = 262, 10, 16
SCREEN_Y0, SC_YOFF = 80, O['SC_YOFF']   # the list's top on the screen (30 px system bar + 50 px navbar)


def artists_tests(ctx):
    """The menu's Artists row, the Artists page and Cover Flow scoped to one artist."""
    expect, page, cover_asset = ctx.expect, ctx.page, ctx.cover_asset
    import awtk_ui
    row = artists_row(page)
    open_ = PSYMS['artists_open']
    page_tests(expect, cover_asset)

    # 27. The menu's Artists row opens our list, not the stock Artists page; nothing else moved.
    m = artists_machine()
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * row, count=5000000)
    expect(('window_open', 'm1plus_artists') in m.calls, 'the Artists row opens m1plus_artists')
    expect('stock_resume' not in m.names(), 'the Artists row no longer opens the stock page')
    P = pod_pages
    expect([(r.label, r.arg) for r in page.rows[:9] if r.action == P.ACT_HOME] == [],
           'no library row opens a stock Home page any more: Albums (the grid), Artists, Genres (our Artists page), Songs, Playlists (the mosaic grid) and Folders (our page) are ours')

    # 32. Tap an artist: Cover Flow on exactly that artist's albums (the stock loadAlbumList(0xf004)),
    #     titled with the artist, the All albums card last, the covers the library's cached files.
    m = artists_machine()
    m.call(open_, count=5000000)
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    open_calls = list(m.calls)
    expect(('window_open', 'm1plus_cover') in m.calls, 'an artist opens the Cover Flow page')
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][1] == O['CLASS_ARTISTS'] and la[0][3] == 'Miles Davis', f'the stock artist query runs for that artist ({la[:1]})')
    expect(any(c[0] == '_deque_push_back' for c in m.calls), "the artist's row is copied")
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.calls, 'the title is the artist')
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Kind of Blue') in m.calls, 'the first album is centred')
    expect('pthread_create' not in m.names(), "the library's cached covers are used: nothing to build")
    expect(not any(c[0] in ('open', 'read') and c[1].endswith('coverflow-position') for c in m.calls),
           "the main Cover Flow's last album is not read")
    jazz = art_file(fnv(fnv(O["FNV_SEED"], "Various Artists"), "Jazz Hits"))
    loads = [c[1] for c in open_calls if c[0] == 'widget_load_image']   # decoded when the shelf is built (the centre) ...
    for _ in range(10):                                                  # ... and by the loader, one a tick, not in paint
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['on_load'] for c in m.calls): break
        m.call(PSYMS['on_load'], count=20000000)
        loads += [c[1] for c in m.calls if c[0] == 'widget_load_image']
    expect(('file://' + jazz) in loads, f"the compilation shows the library's cover file ({loads})")
    expect(not any('00000000' in u for u in loads), 'the card has no cover file of its own')
    files = [u for u in loads if u.startswith('file://')]
    expect(len(files) == len(set(files)) == 3, f'the shelf asks for nothing past its ends: three albums, each once ({files})')
    paint(m)
    expect(not any(c[0] in ('widget_load_image', 'fopen', 'access') for c in m.calls), 'paint loads nothing')
    put_value(m, 3); m.call(PSYMS['on_changed'], count=2000000)
    card = ('widget_set_text_utf8', m.widgets['label_album'], 'All albums') in m.calls
    put_value(m, 4); m.call(PSYMS['on_changed'], count=2000000)
    expect(card and not any(c[0] == 'widget_set_text_utf8' for c in m.calls), 'three albums and the All albums card, no more')
    put_value(m, 0); m.call(PSYMS['on_changed'], count=2000000)
    b, data, w, h = m.bitmap
    frame = bytes(m.u.mem_read(data, w * h * 4))
    host = host_frame(0, ring=[None] * 3 + [True] * 4)
    # q2-pod's bounded artist shelf: nothing left of the first album, no repeats
    expect(frame == host, 'at the first album nothing is drawn to its left (the host frame of that ring)')

    # 32b. Landscape on an artist's Cover Flow (the choice is shared with the main one): the body-sized frame, the card's
    #      caption All albums over the artist, and the shelf still has its ends.
    lw, lh = O['CFL_W'], O['CFL_H']
    ml = artists_machine(); ml.fs['/mnt/data/m1plus/coverflow-landscape'] = b'1\n'; ml.canvas_mem = ml.alloc(0x80)
    ml.call(open_, count=5000000); ml.call(PSYMS['ar_open'], a0=0, count=8000000)
    expect([(c[1], c[2]) for c in ml.calls if c[0] == 'bitmap_create_ex'] == [(lh, lw)], 'the artist\'s Cover Flow opens in landscape when that is saved')
    def paint_land(m):
        ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas_mem)
        m.glyphs.clear(); m.call(PSYMS['on_paint'], a0=0, a1=ev, count=400000000)
    put_value(ml, 3); ml.call(PSYMS['on_changed'], count=2000000); paint_land(ml)
    text = lambda size: ''.join(chr(c) for c, s in ml.glyphs if s == size)
    expect(text(22).startswith('All albums') and text(18).startswith('Miles Davis'), 'the card reads All albums over the artist in landscape too')
    put_value(ml, 0); ml.call(PSYMS['on_changed'], count=2000000); paint_land(ml)
    b, data, w, h = ml.bitmap
    frame = bytes(ml.u.mem_read(data, w * h * 4))
    host = host_frame(0, ring=[None] * 3 + [True] * 4, land=True)
    at = lambda x, y: (x * lh + lh - 1 - y) * 4
    ok = all(frame[at(x, y):at(x, y) + 4] == host[at(x, y):at(x, y) + 4]
             for y in range(0, O['CFL_ALBUM_Y'] - 6, 3) for x in range(0, lw, 2))
    expect(ok, 'at the first album nothing is drawn to its left in landscape (the host frame of that ring)')

    # 33. The card: All albums over the artist; it opens our Songs page on all the artist's songs (the Songs button's call: the artist is put into the
    #     browsing record by loadAlbumList(0xf004, artist), loadAlbumdetailList turns it into the All songs class 0xff11), not an album page.
    put_value(m, 3)
    m.call(PSYMS['on_changed'], count=2000000)
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'All albums') in m.calls, 'the card reads All albums')
    expect(('widget_set_text_utf8', m.widgets['label_artist'], 'Miles Davis') in m.calls, 'over the artist')
    m3 = artists_machine(); m3.call(open_, count=5000000); m3.call(PSYMS['ar_open'], a0=0, count=8000000)
    put_value(m3, 3); m3.call(PSYMS['on_changed'], count=2000000)
    m3.tap(O['CF_CX'], count=900000000)
    calls = [c for c in m3.calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList', 'window_open', 'navigator_to_with_context') and c[1] != 'm1plus_cover']
    la = [c for c in calls if c[0] == 'loadAlbumList']
    expect([c[:2] for c in calls][:3] == [('loadAlbumList', O['CLASS_ARTISTS']), ('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS']), ('window_open', 'm1plus_songs')]
           and la[0][3] == 'Miles Davis' and not any(c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page' for c in calls),
           f'a tap on the card opens our Songs page on the artist\'s songs, no album page ({calls})')
    expect(not any(c[0] in ('list_item_create', 'loadSongList') for c in m3.calls), 'no track list or play code of our own')
    m3 = artists_machine(); m3.windows['m1plus_songs'] = 0; m3.call(open_, count=5000000); m3.call(PSYMS['ar_open'], a0=0, count=8000000)
    put_value(m3, 3); m3.call(PSYMS['on_changed'], count=2000000)
    m3.tap(O['CF_CX'], count=900000000)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 3) in m3.calls and ('albumcoverinfo_init', m3.opened_album[2]) in m3.calls,
           'a Songs page that will not open: the card falls back to the plain stock albuminfo_page on the All songs row')

    # 34. A centre album: the same, with its own row; Back from the covers returns to the Artists list.
    put_value(m, 1)
    m.call(PSYMS['on_changed'], count=2000000)
    m.tap(O['CF_CX'])
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 1) in m.calls
           and m.read_cstr(m.word(m.deques[m.opened_album[2]][1] + O['REC_ALBUM'])) == 'Jazz Hits',
           'the centre album opens as the stock artist page opens it (class 0xff01, its row)')
    m.call(PSYMS['on_back'], count=2000000)
    expect('navigator_back' in m.names(), 'Back from the covers returns to the Artists list')

    # 35. The shelf has ends: a drag right from the first album does not wrap to the card, a drag
    #     left from the card does not wrap to the first album.
    put_value(m, 0)
    m.touch('down', 60, t=9000); m.touch('move', 120, t=9300); m.touch('move', 200, t=9600)
    off = struct.unpack('<i', struct.pack('<I', shelf_off(m) & 0xffffffff))[0]
    m.touch('up', 200, t=9900); m.settle()
    expect(0 < off <= O['CF_VIEW_H'] * O['OVER_NUM'] // O['OVER_DEN'] and shelf_off(m) == 0 and shelf_value(m) == 0 and not any(c[0] == 'set_value' for c in m.calls),
           f'the first album is an end: stretched by the rubber band (xoffset {off}), then back at 0 with no wrap')
    put_value(m, 3)
    m.touch('down', 250, t=12000); m.touch('move', 150, t=12300); m.touch('move', 20, t=12600)
    m.touch('up', 20, t=12610); m.settle()
    expect(not any(c[0] == 'set_value' for c in m.calls), 'the card is the other end')
    put_value(m, 3)
    m.touch('down', 100, t=15000); m.touch('move', 200, t=15300); m.touch('move', 290, t=15600)
    m.touch('up', 290, t=15900); m.settle()
    expect(('set_value', 1) in m.calls, 'a drag of two spacings from the card goes back two albums')

    # 36. Closing: the scoped page writes no last album, and the main Cover Flow still reads its own.
    m.call(PSYMS['on_destroy'], count=2000000)
    expect(not any(c[0] in ('open', 'write', 'rename') and 'coverflow-position' in str(c) for c in m.calls), "scoped browsing leaves the main Cover Flow's last album alone")
    expect(sum(1 for c in m.calls if c[0] == 'deque_destroy') >= 2, "the artist's albums and row are freed")
    m.fs['/mnt/mmc/.m1plus/coverflow-position'] = b'1234abcd\n'
    m.call(PSYMS['coverflow_open'], count=8000000)
    expect(('open', '/mnt/mmc/.m1plus/coverflow-position', 0) in m.calls,
           'the main Cover Flow still reads its last album')

    # 37. One album: no card. No albums: the message. Cover Flow already open: refused.
    m = artists_machine(); m.call(open_, count=5000000)
    m.call(PSYMS['ar_open'], a0=1, count=8000000)
    shown = ('widget_set_text_utf8', m.widgets['label_album'], 'Pastel Blues') in m.calls
    put_value(m, 1); m.call(PSYMS['on_changed'], count=2000000)
    expect(shown and not any(c[0] == 'widget_set_text_utf8' for c in m.calls), 'an artist with one album gets no card')
    put_value(m, 0)
    r2 = m.call(PSYMS['ar_open'], a0=0, count=200000)
    expect(('window_open', 'm1plus_cover') not in m.calls, f'Cover Flow does not open twice ({r2}, {m.calls[:6]})')
    m = artists_machine(); m.call(open_, count=5000000)
    m.call(PSYMS['ar_open'], a0=2, count=8000000)
    expect('view' not in m.names() and
           any(c[0] == 'widget_set_text_utf8' and c[2] == 'No albums' for c in m.calls),
           'an artist without albums says No albums')
    expect(m.props.get((m.widgets['view_covers'], 'sensitive')) == 0, 'and its empty frame takes no touch')

    # 38. Kill switch: the entry falls through, so neither page can open.
    m = artists_machine(); m.present.add('/mnt/mmc/m1plus-off')
    m.call(PSYMS['m1plus_home_click'], a0=m.icon(str(pod_pages.HOME_ENTRY)), count=200000)
    expect('window_open' not in m.names() and 'stock_resume' in m.names(), 'the kill switch keeps Artists closed')

    # 39. The scoped page's hit test: the covers take touches through the touch layer.
    m = artists_machine(); m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    got = stock_target(m, cover_page_tree(m, cover_asset), 160, CF_FRAME_Y + 80)
    expect(got[-1] == 'touch_layer', f"the artist's covers take touches ({got})")

    # 39b. The Songs button (btn_songs): our Songs page on all the artist's songs. The capsule's left cap on the 214 slot, Now Playing its right cap, the same for
    #      one album or many (every artist whose stock list had the All songs row); never on the main Cover Flow, a composer's page or while preparing.
    tree = awtk_ui.parse(open(cover_asset, 'rb').read())
    flags = lambda w: {k: v for k, v in w.props}
    sb = tree.find('btn_songs')
    expect(sb and (sb.x, sb.y, sb.w, sb.h) == (O['NAV_VIEW_X'], 0, O['NAV_VIEW_W'], pod_ui.NAVBAR_H)
           and flags(sb).get('visible') == 'false' and flags(sb).get('sensitive') == 'false' and 'pod_nav_songs_down' in str(sb.props) and 'pod_nav_songs' in str(sb.props)
           and mod_icons.NAV_VIEW_POS['pod_nav_songs'] == 'left' and 'NAV_SONGS_X' not in O,
           'the asset has the Songs button at x 214, 46 wide, hidden and insensitive, with its left-cap glyph and pressed glyph')
    expect(tree.find('btn_allalbums') is None and flags(tree.find('btn_backtoplayer')).get('style:normal:icon') == 'ah_nav_np',
           'the asset has no All albums button, and Now Playing is the disc (the main Cover Flow and a composer\'s page keep it)')
    def seed(m): m.props[(m.widgets['label_title'], 'x')] = 58; m.props[(m.widgets['label_title'], 'h')] = 22
    def scentre(m):
        b = node(cover_page_tree(m, cover_asset), 'btn_songs')
        return b.x + b.w // 2, b.y + b.h // 2
    def songs_shown(m): return m.props.get((m.widgets['btn_songs'], 'visible')) == 1 and m.props.get((m.widgets['btn_songs'], 'sensitive')) == 1
    def hit(m, name): return stock_target(m, cover_page_tree(m, cover_asset), *scentre(m))[-1] == name
    def np_cap(m):
        np = m.widgets['btn_backtoplayer']
        return (m.props.get((np, 'style:normal:icon')), m.props.get((np, 'style:over:icon')), m.props.get((np, 'style:pressed:icon')))
    for a0, what in ((0, 'with the card (two albums)'), (1, 'with one album (no card)')):
        m = artists_machine(); seed(m); m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=a0, count=8000000)
        opened = list(m.calls)   # (the touch simulation below clears m.calls)
        expect(songs_shown(m) and not any(c[0] == 'widget_move' and c[1] == m.widgets['btn_songs'] for c in opened),
               f'an artist {what}: Songs is shown, at the asset\'s x 214 (not moved)')
        expect(('widget_resize', m.widgets['label_title'], O['NAV_VIEW_X'] - 58, 22) in opened,
               f'an artist {what}: the title ends before the capsule ({[c for c in opened if c[0] == "widget_resize" and c[1] == m.widgets["label_title"]]})')
        expect(hit(m, 'btn_songs'), f'an artist {what}: a touch on Songs reaches it ({stock_target(m, cover_page_tree(m, cover_asset), *scentre(m))[-1]})')
        right = stock_target(m, cover_page_tree(m, cover_asset), O['NAV_VIEW_X'] + O['NAV_VIEW_W'] + 2, 25)[-1]
        expect(right == 'btn_backtoplayer', f'an artist {what}: right of Songs is Now Playing ({right})')
        expect(np_cap(m) == ('ah_nav_play', 'ah_nav_play', 'ah_nav_play_down'), f'an artist {what}: Now Playing is the capsule\'s right cap ({np_cap(m)})')
    m = artists_machine(); seed(m); m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    m.click('btn_songs', count=900000000)
    calls = [c for c in m.calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList', 'window_open', 'navigator_to_with_context') and c[1] != 'm1plus_cover']
    expect([c[:2] for c in calls][:3] == [('loadAlbumList', O['CLASS_ARTISTS']), ('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS']), ('window_open', 'm1plus_songs')]
           and not any(c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page' for c in calls), f'a tap opens our Songs page on the artist ({calls})')
    m.call(PSYMS['on_destroy'], count=2000000)
    m = artists_machine(); seed(m); m.windows['m1plus_songs'] = 0; m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    m.click('btn_songs', count=900000000)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 3) in m.calls, 'a page that will not open falls back to the stock album page on the All songs row')
    m = artists_machine(); seed(m); m.windows['m1plus_songs'] = 0; m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=1, count=8000000)
    m.click('btn_songs', count=900000000)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 1) in m.calls, 'and also for an artist whose card was dropped (one album: the All songs row is the second)')
    m = artists_machine(); seed(m); m.call(open_, count=5000000); m.call(PSYMS['ar_open'], a0=2, count=8000000)
    m.click('btn_songs', count=2000000)
    expect(not songs_shown(m) and np_cap(m)[0] != 'ah_nav_play' and not [c for c in m.calls if c[0] in ('loadAlbumdetailList', 'navigator_to_with_context')],
           'an artist with no albums (No albums): no Songs button, Now Playing keeps its disc, a stray click opens nothing')
    mm = cover_machine(albums=3); seed(mm); mm.call(PSYMS['coverflow_open'], count=5000000)
    mm.click('btn_songs', count=2000000)
    expect(not songs_shown(mm) and np_cap(mm)[0] != 'ah_nav_play' and not any(c[0] == 'widget_resize' and c[1] == mm.widgets['label_title'] for c in mm.calls)
           and not [c for c in mm.calls if c[0] in ('loadAlbumdetailList', 'loadAlbumList', 'navigator_to_with_context')] and not hit(mm, 'btn_songs'),
           'the main Cover Flow keeps Songs hidden, Now Playing the disc and the title full width; a stray click does nothing')
    mp = artists_machine(); seed(mp)
    for f in [f for f in mp.present if f.startswith('/mnt/mmc/.m1plus/covers/')]: mp.present.discard(f)
    mp.call(open_, count=5000000); mp.call(PSYMS['ar_open'], a0=0, count=8000000)
    mp.click('btn_songs', count=2000000)
    expect(not songs_shown(mp) and np_cap(mp)[0] != 'ah_nav_play' and not [c for c in mp.calls if c[0] in ('loadAlbumdetailList', 'navigator_to_with_context')],
           'while preparing the Songs button is hidden, Now Playing the disc, and a stray click does nothing')

    # closing frees the handle: a following main Cover Flow starts clean
    m.call(PSYMS['on_destroy'], count=2000000)


def ar_paint(m, off=0):
    """One EVT_AFTER_PAINT on the content view at scroll offset off: (blits, texts, styles, fills) of that frame."""
    m.setword(m.sv + SC_YOFF, off & 0xffffffff)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - off) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['ar_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(m.texts), list(m.text_styles), list(m.fills)


def rank_of(name):
    k = name_sort_key(name)
    return ord(k[0][1].upper()) - 64 if k and k[0][0] == 2 else 0


def sections_of(ranks):
    """The non-decreasing labelling with the most rows under their own letter (a tie starts a section late): [(first row, letter)] (patch/azlist.c az_sections, written again)."""
    best, came = [[0] * 27], []
    for k in ranks:
        prev, row, low = best[-1], [], []
        for r in range(27):
            d = prev[r] + (r == k)
            lower = r > 0 and row[r - 1] >= d
            row.append(row[r - 1] if lower else d); low.append(lower)
        best.append(row); came.append(low)
    lab, labels = 26, []
    for i in range(len(ranks) - 1, -1, -1):
        while lab and came[i][lab]: lab -= 1
        labels.append(lab)
    labels.reverse()
    return [(i, '#' if l == 0 else chr(64 + l)) for i, l in enumerate(labels) if i == 0 or l != labels[i - 1]]


class Model:
    """The page's geometry from the display-order names (the payload's, written again); the Unknown row (the name 'Unknown ...') takes the rank of the row before it."""
    def __init__(self, names):
        ranks = []
        for i, n in enumerate(names): ranks.append(ranks[-1] if n.startswith('Unknown') and i else rank_of(n))
        self.n, self.secs = len(names), sections_of(ranks) if names else []
    def hdr_y(self, s): return TOP + s * HDR + self.secs[s][0] * ROW
    def sec_of(self, i): return max(k for k, (st, _) in enumerate(self.secs) if st <= i)
    def row_y(self, i): return TOP + (self.sec_of(i) + 1) * HDR + i * ROW
    def content(self): return TOP + len(self.secs) * HDR + self.n * ROW + BOTTOM


def headers(m):
    """{content y: letter} of every section header the page paints (the pinned copy at the window's top excluded), over the whole content."""
    out, vh = {}, m.props.get((m.sv, 'virtual_h'), 0) or VIEW_H
    for off in range(0, max(vh - VIEW_H, 0) + 200, 200):
        _, texts, styles, _ = ar_paint(m, off)
        for (t, (x, y, w, h)), st in zip(texts, styles):
            if x == O['SG_HDR_X'] and st == 'label_hdr' and y > 0: out[y + off] = t
    return out


def scroll_to(m, v):
    """The scroll_view's offset to v, and the page told as the stock setter's EVT_SCROLL tells it."""
    m.setword(m.sv + SC_YOFF, v & 0xffffffff)
    fn, ctx = m.bound[(m.sv, O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=80000000)


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def page_tests(expect, cover_asset):
    """The Artists page in the Songs page's manner: one painted content view in the stock list, section letters with a pinned header, the compact A-Z rail, the
    large title that collapses into the navbar, the rows' touch; the asset; Genres and Composers share all of it (genre_composer_tests)."""
    import awtk_ui, awtk_strings
    open_ = PSYMS['artists_open']
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_artists.bin')

    # 28. Open: the stock Artists query and one copy of it, no widget per row, the handlers bound, the content as tall as the sections and rows make it
    m = artists_machine()
    expect(m.call(open_, count=5000000) == 0, 'artists_open returns 0')
    opened = list(m.calls)
    expect(('loadLocalClassList', O['CLASS_ARTISTS']) in opened and 'deque_assign' in [c[0] for c in opened], 'the list is the stock Artists query, copied')
    expect(not [c for c in opened if c[0] in ('list_item_create', 'hscroll_label_create', 'image_create', 'image_base_set_image')],
           'no widget is made per artist: the content view paints the rows')
    mod = Model(['Miles Davis', 'Nina Simone', 'Unknown Artist'])
    expect(mod.secs == [(0, 'M'), (1, 'N')], f'sections M, N (the Unknown row stays with the section before it): {mod.secs}')
    expect(m.props.get((m.sv, 'virtual_h')) == mod.content() and ('widget_resize', m.view, 320, mod.content()) in opened,
           f'the scroll_view and the content view are {mod.content()} px high (large title, two headers, three rows, the air under them)')
    expect(m.props.get((m.sv, 'yoffset')) == 0 and vis(m, 'artists_listview') == (1, 1) and vis(m, 'label_status')[0] == 0, 'the list shows, at the top; the message is hidden')
    for ev in ('EVT_AFTER_PAINT', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        expect((m.view, O[ev]) in m.bound, f'the content view handles {ev}')
    expect(all((m.rail, O[e]) in m.bound for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_MOVE', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT', 'EVT_AFTER_PAINT')), 'the rail handles its touch and paints')
    expect((m.sv, O['EVT_SCROLL']) in m.bound and (m.sv, O['EVT_SCROLL_END']) in m.bound, 'the scroll_view\'s scroll events are bound (the title collapse, the fade)')
    expect([c for c in opened if c[0] == 'bitmap_create_ex'][:2] == [('bitmap_create_ex', O['SG_RAIL_DISC'], O['SG_RAIL_DISC']), ('bitmap_create_ex', CHEV_W, CHEV_H)],
           'the rail\'s disc and the chevron (a bitmap of our own, 10 x 16: the stock right_arrow is 13 x 22, and the loader only makes squares) are made at open')

    # 29. Paint: the names (the Albums page's tile text, 21 px white), the chevrons, the hairlines, the section letters
    blits, texts, styles, fills = ar_paint(m, 0)
    rows = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    want = [(n, (TEXT_X, mod.row_y(i) + TEXT_Y, TEXT_END - TEXT_X, TEXT_H)) for i, n in enumerate(['Miles Davis', 'Nina Simone', 'Unknown Artist'])]
    expect(rows == want, f'the names are drawn in their 24 px boxes from x {TEXT_X}, up to x {TEXT_END} (the chevron\'s room): {rows}')
    hd = [(t, r[1]) for (t, r), s in zip(texts, styles) if s == 'label_hdr']
    expect(hd == [('M', mod.hdr_y(0)), ('N', mod.hdr_y(1))], f'the section letters at their headers, the Songs page\'s (x {O["SG_HDR_X"]}, 20 px): {hd}')
    chev = [b for b in blits if tuple(b[2][2:]) == (CHEV_W, CHEV_H)]
    expect([tuple(b[2]) for b in chev] == [(CHEV_X, mod.row_y(i) + (ROW - CHEV_H) // 2, CHEV_W, CHEV_H) for i in range(3)], 'a chevron at the right of every row, centred in its row')
    hair = [f for f in fills if f[0] == O['LIST_HAIR'] and f[3] == O['SG_TEXT_END'] - TEXT_X]
    expect([(f[1], f[2], f[4]) for f in hair] == [(TEXT_X, mod.row_y(i) + ROW - 1, 1) for i in range(3)], 'a hairline under every row from the text\'s x')
    expect(not [f for f in fills if f[0] == O['SG_HDR_BG']], 'no pinned header at the top (the first header has not reached the window\'s top)')
    # the chevron's pixels: a stroke of two segments, the grey of the rail's dots, antialiased in the alpha
    data, w, h = m.bitmaps[chev[0][0]]
    px = lambda x, y: struct.unpack('<I', m.u.mem_read(data + (y * w + x) * 4, 4))[0]
    expect((w, h) == (CHEV_W, CHEV_H) and px(0, 0) >> 24 == 0 and px(0, CHEV_H - 1) >> 24 == 0 and px(CHEV_W - 1, 0) >> 24 == 0 and px(CHEV_W - 1, CHEV_H - 1) >> 24 == 0,
           'the chevron\'s corners are clear ' + str([[px(x, y) >> 24 for x in range(CHEV_W)] for y in range(CHEV_H)]))
    tip = max(px(x, CHEV_H // 2) >> 24 for x in range(CHEV_W)); mid_row = [px(x, CHEV_H // 2 - 1) >> 24 for x in range(CHEV_W)]
    expect(tip == 255 and max(px(x, 3) >> 24 for x in range(CHEV_W)) > 200 and all(px(x, 5) & 0xffffff == 0x8a8a8a for x in range(CHEV_W) if px(x, 5) >> 24),
           f'the stroke is solid at its tip and its arms, in #8A8A8A ({tip}, {mid_row})')
    # the window is 400 px: a row is drawn once its 24 px text box and its chevron are wholly inside
    blits, texts, styles, fills = ar_paint(m, mod.row_y(1) - 10)
    got = [t for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    expect(got == ['Nina Simone', 'Unknown Artist'], f'a row whose text box has scrolled out of the window shows nothing of it ({got})')

    # 29a. The press: the row under the finger is filled #333333, a tap opens the artist, nothing else does
    def down(y, x=100): m.touch('down', x, SCREEN_Y0 + y, 1000, fn='ar_on_down')
    down(mod.row_y(1) + 10)
    _, _, _, fills = ar_paint(m, 0)
    expect((O['LIST_PRESS'], 0, mod.row_y(1), 320, ROW - 1) in fills and not [f for f in fills if f[0] == O['LIST_PRESS'] and f[2] != mod.row_y(1)], 'the pressed row is filled')
    m.touch('up', 100, SCREEN_Y0 + mod.row_y(1) + 10, 1080, fn='ar_on_up', count=30000000)
    expect(('window_open', 'm1plus_cover') in m.calls and [c for c in m.calls if c[0] == 'loadAlbumList'][0][3] == 'Nina Simone', 'a tap on a row opens Cover Flow on that artist')
    _, _, _, fills = ar_paint(m, 0)
    expect(not [f for f in fills if f[0] == O['LIST_PRESS']], 'the fill is gone on release')
    for what, y0, dy in (('the large title block', 10, 0), ('a section header', mod.hdr_y(0) + 8, 0), ('the air below the last row', mod.content() - 5, 0), ('a drag past the threshold', mod.row_y(0) + 10, 14)):
        mm = artists_machine(); mm.call(open_, count=5000000)
        mm.touch('down', 100, SCREEN_Y0 + y0, 1000, fn='ar_on_down'); mm.touch('up', 100, SCREEN_Y0 + y0 + dy, 1080, fn='ar_on_up', count=30000000)
        expect(('window_open', 'm1plus_cover') not in mm.calls and 'loadAlbumList' not in mm.names(), f'a touch on {what} opens nothing')
    mm = artists_machine(); mm.call(open_, count=5000000)
    mm.touch('down', 100, SCREEN_Y0 + mod.row_y(0) + 5, 1000, fn='ar_on_down'); mm.touch('up', 100, SCREEN_Y0 + mod.row_y(1) + 5, 1080, fn='ar_on_up', count=30000000)
    expect('loadAlbumList' not in mm.names(), 'a press on one row released on another opens nothing')
    mm.touch('down', 100, SCREEN_Y0 + mod.row_y(0) + 5, 2000, fn='ar_on_down'); mm.touch('abort', 100, SCREEN_Y0 + mod.row_y(0) + 5, 2010, fn='ar_on_abort')
    mm.touch('up', 100, SCREEN_Y0 + mod.row_y(0) + 5, 2020, fn='ar_on_up', count=30000000)
    expect('loadAlbumList' not in mm.names(), 'an aborted press opens nothing')

    # 29b. Sections: the display order's letters, the labelling that keeps a stray in the section around it; the headers are where the model puts them
    stock = ['the Beatles', 'Zed', 'The Who', 'Theo', 'Them', 'Abba', 'Beach Boys', 'THE ROLLING STONES', 'Miles Davis', '1999', 'Unknown Artist']
    order = sort_model(stock)[0]
    mod = Model(order)
    mm = artists_machine(stock); mm.call(open_, count=20000000)
    expect(shown(mm) == order, f'the rows are the sorted order ({shown(mm)})')
    expect(headers(mm) == {mod.hdr_y(s): l for s, (_, l) in enumerate(mod.secs)}, f'the headers are the sections of the labelling ({sorted(headers(mm).values())} for {mod.secs})')
    expect([l for _, l in mod.secs][:3] == ['#', 'A', 'B'] or [l for _, l in mod.secs][0] in '#A', f'Initials: "The Beatles" files under B, "THE ROLLING STONES" under R, the "1999" under # ({mod.secs})')
    expect(mm.props.get((mm.sv, 'virtual_h')) == mod.content(), 'and the content is as tall as they make it')
    # a plain list (no memory for the ranks): no headers, no rail, the rows from the title block's end
    mp = artists_machine(stock); mp.calloc_fail_size = len(stock); mp.call(open_, count=20000000)
    expect(mp.props.get((mp.sv, 'virtual_h')) == TOP + len(stock) * ROW + BOTTOM and not headers(mp) and vis(mp, 'sg_rail')[0] == 0 and vis(mp, 'sg_rail')[1] == 0 and shown(mp) == order,
           'no memory for the section ranks: a plain list, no headers, no rail, the same rows')

    # 29c. The rail: the compact index on the Songs page's metrics (patch/azlist.c, tested at length in test/pod/songs.py): shown with sections, the geometry, a jump
    mm = artists_machine([f'{chr(65 + i)} Band' for i in range(26)] + [f'{chr(65 + i)}2 Band' for i in range(0, 26, 5)]); mm.call(open_, count=40000000)
    names = shown(mm); mod = Model(names)
    expect(len(mod.secs) == 26 and vis(mm, 'sg_rail') == (1, 1), 'the rail shows for 26 sections')
    span = (2 * 9 - 1) * O['SG_RAIL_PITCH']   # 26 sections: every third letter and the last, 9 letters with a dot between each (the plan of patch/azlist.c, tested in test/pod/songs.py)
    geo = tuple(mm.props.get((mm.rail, k)) for k in 'xywh')
    expect(geo[0] == O['SG_RAIL_X'] and geo[2] == O['SG_RAIL_W'] and geo[3] == span + 2 * O['SG_RAIL_PAD'] and abs(geo[1] + geo[3] / 2 - (50 + VIEW_H / 2)) <= 1,
           f'the rail is the Songs page\'s column (x 284, 36 wide, the span {span} px and the margins), centred on the list ({geo})')
    def rail_touch(kind, i, n=len(mod.secs)):
        sp = geo[3] - 2 * O['SG_RAIL_PAD']
        y = 30 + geo[1] + O['SG_RAIL_PAD'] + int((i + 0.5) * sp / n)
        mm.touch(kind, 300, y, 3000, fn='ar_on_rail', count=40000000)
    for i in (5, 20):
        mm.calls = []
        rail_touch('down', i)
        want = min(mod.hdr_y(i), mod.content() - VIEW_H)
        expect(('widget_grab', mm.window, mm.rail) in mm.calls and ('widget_set_prop_int', mm.sv, 'yoffset', want) in mm.calls and vis(mm, 'sg_bubble')[0] == 1,
               f'a touch on the rail grabs it and jumps to section {mod.secs[i][1]}\'s header ({want}), the bubble shows')
        expect(('widget_set_text_utf8', mm.widgets['sg_bubble_letter'], mod.secs[i][1]) in mm.calls, 'the bubble shows the letter')
        mm.touch('up', 300, 200, 3100, fn='ar_on_rail', count=4000000)
        expect(('widget_ungrab', mm.window, mm.rail) in mm.calls and vis(mm, 'sg_bubble')[0] == 0, 'the release lets go and hides the bubble')
    mm.calls = []; rail_touch('down', 0)
    expect(('widget_set_prop_int', mm.sv, 'yoffset', 0) in mm.calls, 'the first section: the top of the list, the large title with it')
    mm.touch('up', 300, 200, 3100, fn='ar_on_rail', count=4000000)
    # the page behind another window lets the rail go
    mm.calls = []; rail_touch('down', 3)
    mm.call(PSYMS['ar_on_bg'], count=4000000)
    expect(('widget_ungrab', mm.window, mm.rail) in mm.calls and vis(mm, 'sg_bubble')[0] == 0, 'a window put in front releases the rail')

    # 29d. The large title collapses: the navbar's small title appears once the large one has scrolled away; the fade shows while the list is scrolled
    mm = artists_machine(); mm.call(open_, count=5000000)
    t, fade = mm.widgets['label_title'], mm.widgets['img_nb_fade']
    expect(('widget_set_visible', t, 1) not in mm.calls and mm.props.get((fade, 'visible'), 0) == 0, 'at rest the large title is the title: the small one and the fade are hidden')
    scroll_to(mm, O['SG_COLLAPSE'] + 1)
    expect(mm.props.get((t, 'visible')) == 1 and mm.props.get((fade, 'visible')) == 1 and mm.props.get((fade, 'sensitive')) == 0, 'past SG_COLLAPSE the small title shows and the fade (insensitive)')
    scroll_to(mm, 0)
    expect(mm.props.get((t, 'visible')) == 0 and mm.props.get((fade, 'visible')) == 0, 'back at the top they go')
    mm = artists_machine(); mm.widget_on_fail = frozenset({O['EVT_SCROLL']}); mm.call(open_, count=5000000)
    expect(('widget_set_visible', mm.widgets['label_title'], 1) in mm.calls, 'without the scroll events the navbar keeps its title')

    # 29e. The titles in every language, cut with an ellipsis to the large label (296 px, 32 px) and the navbar's room (156 px): measured in the real font
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    import awtk_style
    npx = awtk_style.parse(open(os.path.join(raw, 'styles/default.bin'), 'rb').read()).find('label', 'navbar_label_white', 'normal')[0].get('font_size')
    AT = pod.DATA['ARTIST_TYPE'][0]
    cut = []
    for loc in pod_i18n.LOCALES:
        for key, home, kw, album in (('Artists', 0, {}, 0), ('Album Artists', 0, {}, 1), ('Genres', pod_pages.HOME_GENRE, {'genres': ('Rock',)}, 0),
                                     ('Composers', pod_pages.HOME_COMPOSER, {'composers': ('Bach',)}, 0)):
            for name, room, px in (('ar_title', O['SG_TITLE_W'], 32), ('label_title', O['NAV_VIEW_X'] - O['NAV_TITLE_X'], npx)):
                mm = artists_machine(**kw); mm.set_language(loc); mm.setword(AT, album)
                st = StbText(font, px); mm.measure = lambda s, st=st: st.layout(s)[1]
                mm.call(open_, a0=home, count=5000000)
                full = built[loc].get(key, key)
                text = [c[2] for c in mm.calls if c[0] == 'widget_set_text_utf8' and c[1] == mm.widgets[name]][-1:]
                got = text[0].encode('latin-1').decode('utf-8') if text else ''
                expect(got == full or (got.endswith('…') and got[:-1] and full.startswith(got[:-1].rstrip()) and st.layout(got)[1] <= room),
                       f'{loc}: {name} "{full}" fits {room} px or is cut with an ellipsis that fits ({got!r})')
                if got != full: cut.append((loc, key, name))
    print(f'  titles cut with an ellipsis (a title that fits is never cut): {cut}')

    # 30. The asset: the Songs page's structure, hidden and insensitive where the payload shows later, hit tests by demo's own widget_find_target
    tree = awtk_ui.parse(open(asset, 'rb').read())
    lv = tree.find('artists_listview')
    expect(lv.y == pod_ui.NAVBAR_H and lv.y + lv.h == CLIENT_H and [c.type for c in lv.children] == ['scroll_view', 'scroll_bar_m'], 'list_view (50-450) > scroll_view + scroll_bar_m, as stock')
    sv = lv.children[0]
    expect(sv.name == 'artists_scrollview' and [c.name for c in sv.children] == ['view_grid'] and sv.w == 310, 'the scroll_view holds the one content view')
    vg = sv.children[0]
    expect([c.name for c in vg.children] == ['ar_title'] and vg.children[0].get('sensitive') == 'false' and (vg.children[0].x, vg.children[0].w, vg.children[0].h) == (O['SG_TITLE_X'], O['SG_TITLE_W'], O['SG_TITLE_H']),
           'the content view holds the large title only (insensitive, as the Songs page\'s)')
    for name in ('label_status', 'img_nb_fade', 'label_row_title', 'label_hdr', 'label_rail', 'label_rail_on', 'sg_bubble', 'label_title'):
        w = tree.find(name)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == ('true' if name == 'label_title' else 'false') or name == 'label_title' and w.get('visible') == 'false',
               f'{name} starts hidden (and insensitive)')
    rail = tree.find('sg_rail')
    expect((rail.x, rail.y, rail.w, rail.h) == (O['SG_RAIL_X'], 50, O['SG_RAIL_W'], VIEW_H) and rail.get('visible') != 'false', 'the rail is the Songs page\'s column')
    names = [w.name for w in tree.walk() if w.name]
    expect(all(n in names for n in ('btn_return', 'btn_backtoplayer', 'btn_artisttype', 'label_title', 'navigationbar_view', 'sg_bubble_letter')) and
           not [n for n in names if n in ('pod_listview', 'pod_scrollview')], 'the navbar keeps its buttons and title; the old list names are gone')
    tog = tree.find('btn_artisttype')
    expect((tog.x, tog.y, tog.w, tog.h) == (O['NAV_VIEW_X'], 0, O['NAV_VIEW_W'], O['NAV_H']) and tog.x + tog.w == tree.find('btn_backtoplayer').x, 'btn_artisttype is in the toggle slot, flush left of Now Playing')
    lbl = tree.find('label_title')
    expect(lbl.x + lbl.w == O['NAV_VIEW_X'], 'the small title ends where the toggle begins')
    expect(tog.get('style:normal:icon') == 'pod_nav_albumartist' and tog.get('style:pressed:icon') == 'pod_nav_albumartist_down', 'built in Artist mode, the button shows the Album Artist glyph')
    mm = artists_machine(); mm.call(open_, count=5000000)
    root = asset_tree(asset)
    node(root, 'view_grid').h = 3000
    r = node(root, 'sg_rail'); r.x, r.y, r.w, r.h = (mm.props.get((mm.rail, k), v) for k, v in zip('xywh', (r.x, r.y, r.w, r.h)))
    expect(stock_target(mm, root, 150, 300)[-1] == 'view_grid' and 'artists_scrollview' in stock_target(mm, root, 150, 300), 'a touch in the list is the content view\'s, through the scroll view')
    expect(stock_target(mm, root, 40, 25)[-1] == 'btn_return' and stock_target(mm, root, 290, 25)[-1] == 'btn_backtoplayer' and stock_target(mm, root, O['NAV_VIEW_X'] + 20, 25)[-1] == 'btn_artisttype',
           'Back, Now Playing and the switch are hit')
    expect(stock_target(mm, root, 300, r.y + r.h // 2)[-1] == 'sg_rail', 'a touch in the rail\'s column within its span reaches the rail, never the scroll view')
    expect('label_status' not in stock_target(mm, root, 160, 225) and 'sg_bubble' not in stock_target(mm, root, 160, 225), 'the hidden message and the bubble take no touch')

    # 31. The toggle: the stock switch's writes, the other mode's list, the titles (the large one too), the glyph
    AT, RELOAD = pod.DATA['ARTIST_TYPE'][0], pod.DATA['ARTIST_RELOAD'][0]
    m = artists_machine(); m.call(open_, count=5000000)
    big, title, tglyph = m.widgets['ar_title'], m.widgets['label_title'], m.widgets['btn_artisttype']
    expect(('widget_set_text_utf8', title, 'Artists') in m.calls and ('widget_set_text_utf8', big, 'Artists') in m.calls and m.props.get((tglyph, 'style:normal:icon')) == 'pod_nav_albumartist'
           and m.props.get((tglyph, 'style:pressed:icon')) == 'pod_nav_albumartist_down', 'artist_type 0: both titles read "Artists", the Album Artist glyph')
    tclicks = [c for c in opened if c[0] == 'widget_on' and c[1] == tglyph and c[2] == O['EVT_CLICK']]
    expect(len(tclicks) == 1 and tclicks[0][3] == PSYMS['ar_on_toggle'], 'the toggle button is bound')
    scroll_to(m, 300)
    m.call(PSYMS['ar_on_toggle'], count=5000000)
    new = m.calls
    expect(m.word(AT) == 1 and ('write_int_config', 1, 'PLAYSET', 'ARTISTTYPE') in new and m.u.mem_read(RELOAD, 1)[0] == 1, 'a tap sets artist_type, saves [PLAYSET] ARTISTTYPE and raises the stock reload flag')
    expect(('widget_set_text_utf8', title, 'Album Artists') in new and ('widget_set_text_utf8', big, 'Album Artists') in new and m.props.get((tglyph, 'style:normal:icon')) == 'pod_nav_artist'
           and m.props.get((tglyph, 'style:pressed:icon')) == 'pod_nav_artist_down', 'both titles read "Album Artists", the glyph is the Artist one')
    expect(('loadLocalClassList', O['CLASS_ARTISTS']) in new and ('widget_set_prop_int', m.sv, 'yoffset', 0) in new and 'deque_destroy' in [c[0] for c in new],
           'the stock query runs again, the list is at the top, the previous copy is freed')
    expect(shown(m) == ['Miles Davis', 'Various Artists'] and m.props.get((m.sv, 'virtual_h')) == Model(['Miles Davis', 'Various Artists']).content(), 'the list is the album-artist list (sorted: stock has Various Artists first)')
    m.call(PSYMS['ar_on_toggle'], count=5000000)
    expect(m.word(AT) == 0 and ('write_int_config', 0, 'PLAYSET', 'ARTISTTYPE') in m.calls and m.props.get((tglyph, 'style:normal:icon')) == 'pod_nav_albumartist'
           and ('widget_set_text_utf8', title, 'Artists') in m.calls, 'the second tap sets Artist again, titles and glyph with it')
    m3 = artists_machine(); m3.setword(AT, 1); m3.call(open_, count=5000000); calls3 = list(m3.calls)
    expect(shown(m3) == ['Miles Davis', 'Various Artists'] and ('widget_set_text_utf8', m3.widgets['label_title'], 'Album Artists') in calls3 and m3.props.get((m3.widgets['btn_artisttype'], 'style:normal:icon')) == 'pod_nav_artist',
           'opening with album artist set lists them, titled "Album Artists" with the Artist glyph')
    m4 = artists_machine(); del m4.widgets['btn_artisttype']; del m4.widgets['label_title']; del m4.widgets['ar_title']
    m4.call(open_, count=5000000)
    expect(shown(m4) == ['Miles Davis', 'Nina Simone', 'Unknown Artist'] and 'navigator_back' not in m4.names(), 'a page without the toggle or the titles still lists')

    # 32. Back leaves the Artists page; closing it frees its copy and bitmaps. An empty library: the message, no list. A broken asset: leave.
    m.call(PSYMS['pod_on_back'], count=200000)
    expect('navigator_back' in m.names(), 'Back on the Artists page goes back')
    m.call(PSYMS['ar_on_destroy'], count=2000000)
    expect('deque_destroy' in m.names() and sum(1 for c in m.calls if c[0] == 'bitmap_destroy') == 2, 'closing the Artists page frees its list and the two bitmaps')
    m = artists_machine(artists=())
    m.call(open_, count=2000000)
    expect(any(c[0] == 'widget_set_text_utf8' and 'Update Local Music' in c[2] for c in m.calls), 'no artists says so')
    expect(m.props.get((m.lv, 'sensitive')) == 0 and m.props.get((m.widgets['label_status'], 'visible')) == 1 and vis(m, 'sg_rail')[0] == 0, 'the empty list is hidden, the message shown, no rail')
    for gone in ('artists_scrollview', 'view_grid', 'sg_rail', 'label_hdr', 'label_row_title', 'sg_bubble_letter', 'artists_listview'):
        m = artists_machine(); del m.widgets[gone]
        expect(m.call(open_, count=2000000) == 0xffffffff and 'navigator_back' in m.names(), f'an Artists asset without {gone} closes')

    # 32a. 5000 artists (the old page stopped at 2000: one widget each): the rows are painted, the sections and the rail work, the cost is bounded
    big = [f'{chr(65 + i % 26)}{chr(97 + (i * 7) % 26)}{i:05d}' for i in range(5000)]
    m = artists_machine(big).count(); m.call(open_, count=900000000)
    spent = m.icount
    mod = Model(sort_model(big)[0])
    expect(m.props.get((m.sv, 'virtual_h')) == mod.content() and len(mod.secs) == 26, f'5000 artists: {mod.content()} px of content in 26 sections, none dropped')
    print(f'  5000 artists open: {spent:,} payload instructions')
    expect(spent < 200000000, f'open is bounded ({spent:,} payload instructions)')
    _, texts, styles, _ = ar_paint(m, mod.content() - VIEW_H)
    last = [t for (t, r), s in zip(texts, styles) if s == 'label_row_title'][-1]
    expect(last == sort_model(big)[0][-1], 'the last artist is painted at the end of the content')
    expect(sum(1 for c in m.calls if c[0] == 'widget_set_text_utf8') == 0 and len(m.texts) < 60, 'a paint draws only the rows in view')


def shown(m):
    """The artist names of the rows of the page, top to bottom: the page painted at offsets 200 px apart over the whole content, the names (the texts at the
    rows' text x) collected by their content y."""
    names, vh = {}, m.props.get((m.sv, 'virtual_h'), 0) or VIEW_H
    for off in range(0, max(vh - VIEW_H, 0) + 200, 200):
        _, texts, _, _ = ar_paint(m, off)
        for t, (x, y, w, h) in texts:
            if x == TEXT_X: names[y + off] = t
    return [names[y] for y in sorted(names)]




def sort_model(names):
    """Independent model: every row but Unknown Artist sorted by (name_sort_key, stock position); Unknown Artist rows keep their stock positions."""
    fixed = [i for i, n in enumerate(names) if n == 'Unknown Artist']
    rest = iter(sorted((i for i in range(len(names)) if i not in fixed), key=lambda k: (name_sort_key(names[k]), k)))
    out = [i if i in fixed else next(rest) for i in range(len(names))]
    return [names[k] for k in out], out


def sort_tests(ctx):
    expect = ctx.expect
    open_ = PSYMS['artists_open']
    # 40. The sort: the album Artist order's rule (ASCII case aside, a leading "The " dropped, ties stable).
    stock = ['the Beatles', 'Zed', 'The Who', 'Theo', 'Them', 'Abba', 'Beach Boys', 'THE ROLLING STONES', 'The', 'The ',
             'Abba', 'abba', 'Miles Davis', 'Unknown Artist']
    want, order = sort_model(stock)
    m = artists_machine(stock)
    m.call(open_, count=20000000)
    got = shown(m)
    expect(got == want, f'artists sorted: {got}')
    ix = got.index
    expect(ix('Beach Boys') < ix('the Beatles') < ix('Miles Davis') < ix('THE ROLLING STONES') < ix('Them') < ix('Theo') < ix('The Who') < ix('Zed'),
           '"The " (any case) is ignored (Beatles under B, Rolling Stones under R, The Who under W); "Them" and "Theo" are not stripped and file under T')
    expect(got[:3] == ['Abba', 'Abba', 'abba'], 'ties keep the stock order: the two "Abba" rows (stock 5, 10) before "abba" (11)')
    expect(got[-1] == 'Unknown Artist', 'Unknown Artist stays last')
    expect(got.index('The') < got.index('The ') < got.index('Them'),
           '"The" and "The " (nothing after it) are not stripped: they file under T, ahead of "Them"')
    # the tap on a display position opens the artist shown there (the stock row behind it)
    for k in (0, 1, 5, len(stock) - 1):
        m2 = artists_machine(stock); m2.call(open_, count=20000000)
        artists_tap(m2, k, starts=[s for s, _ in Model(got).secs])   # a real tap on the row, the headers in the way counted
        la = [c for c in m2.calls if c[0] == 'loadAlbumList']
        expect(la and la[0][3] == got[k], f'a tap on row {k} opens {got[k]!r} ({la[:1]})')

    # 41. Non-Latin names: a CJK name is placed by its pinyin initials among the Latin names, any other script follows the Latin ones; only Unknown Artist is fixed.
    stock = ['Zed', '周杰伦', 'The Beatles', 'Abba', 'Мумий Тролль', 'Bob', 'Éric', 'Aaa', 'あいみょん', 'Unknown Artist']
    want, _ = sort_model(stock)
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == want, f'mixed scripts: {got}')
    expect(got == ['Aaa', 'Abba', 'The Beatles', 'Bob', 'Zed', '周杰伦', 'Éric', 'Мумий Тролль', 'あいみょん', 'Unknown Artist'],
           'Latin names first (Zed before 周杰伦 = "zjl"), then the other scripts by byte; Unknown Artist last')
    m2 = artists_machine(stock); m2.call(open_, count=20000000)
    m2.call(PSYMS['ar_open'], a0=2, count=8000000)   # display 2 is stock row 2
    la = [c for c in m2.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][3] == 'The Beatles', 'a tap opens the right artist')
    stock = ['Zed', 'Zebra', '周杰伦', 'Abc', '孙燕姿', 'Sam', 'Bob', '陈奕迅', 'Yo', 'The Chef']
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == ['Abc', 'Bob', 'The Chef', '陈奕迅', 'Sam', '孙燕姿', 'Yo', 'Zebra', 'Zed', '周杰伦'] and got == sort_model(stock)[0],
           f'CJK names sort by pinyin initials among the Latin ones (陈奕迅 "cyx" after "Chef", 孙燕姿 "syz" after Sam; Zed before 周杰伦 "zjl"): {got}')
    mod = Model(got)
    expect(headers(m) == {mod.hdr_y(s): l for s, (_, l) in enumerate(mod.secs)} and [l for _, l in mod.secs] == ['A', 'B', 'C', 'S', 'Y', 'Z'],
           f'sections: a CJK name files under its pinyin initial, not "#" ({sorted(headers(m).values())})')
    # The Beatles reaches B across a fixed row
    stock = ['Zed', 'Unknown Artist', 'The Beatles', 'Abba', 'Unknown Artist']
    m = artists_machine(stock); m.call(open_, count=20000000)
    expect(shown(m) == ['Abba', 'Unknown Artist', 'The Beatles', 'Zed', 'Unknown Artist'], f'ASCII names are one set across the fixed rows ({shown(m)})')
    # digit runs by value, digits before letters, symbols before letters, leading white space skipped, ties stable
    stock = ['Vol. 10', 'vol. 2', 'Vol. 1', '  Zed', '2 Pac', '10 Pac', '_Under', 'Abc', '007', '7', '  Abc']
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == sort_model(stock)[0], f'natural order: {got}')
    expect(got.index('Vol. 1') < got.index('vol. 2') < got.index('Vol. 10'), 'digit runs compare by value ("Vol. 2" before "Vol. 10")')
    expect(got.index('2 Pac') < got.index('10 Pac') < got.index('_Under') < got.index('Abc'), 'digits before symbols before letters')
    expect(got.index('Abc') < got.index('  Abc') < got.index('Vol. 1') and got[-1] == '  Zed', 'leading white space is skipped; the equal names keep the stock order (Abc 7, "  Abc" 10)')
    expect(got.index('007') < got.index('7'), 'equal values keep the stock order ("007" is stock row 8, "7" row 9)')

    # 42. Both modes and the toggle: each mode's list is sorted, a tap opens the right one, the toggle re-sorts.
    m = artists_machine(); m.album_artists = [artist_rec(m, a, i + 1) for i, a in enumerate(('The Zed', 'Various Artists', 'the Abba', '周'))]
    m.call(open_, count=20000000)
    m.calls = []
    m.call(PSYMS['ar_on_toggle'], count=20000000)
    expect(shown(m) == ['the Abba', 'Various Artists', '周', 'The Zed'],
           'Album Artist mode is sorted too (The Zed files under Z, after 周 "z")')
    m.calls = []
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    expect([c for c in m.calls if c[0] == 'loadAlbumList'][:1] and [c for c in m.calls if c[0] == 'loadAlbumList'][0][3] == 'the Abba',
           'a tap on the first Album Artist row opens it')
    m.calls = []
    m.call(PSYMS['ar_on_toggle'], count=20000000)
    freed = 'free' in m.names()
    expect(shown(m) == ['Miles Davis', 'Nina Simone', 'Unknown Artist'] and freed, 'toggling back re-sorts the Artist list; the old order is freed')

    # 43. Bounds: a large library is capped as before, the sort is bounded and its memory freed on closing.
    big = [f'Artist {(i * 37) % 3000:04d}' for i in range(3000)]
    big[10] = 'The ' + big[10]
    m = artists_machine(big).count(); m.call(open_, count=300000000)
    spent, callocs = m.icount, [c for c in m.calls if c[0] == 'calloc']
    got = shown(m)
    cap = 3000   # (the page lists up to MAX_ARTISTS 20000 now that no widget is made per row)
    expect(len(got) == cap and got == sort_model(big[:cap])[0], '3000 artists: all are listed, sorted')
    print(f'  sort of {cap} artists on open: {spent:,} payload instructions')
    expect(spent < 150000000, f'the sort and the rows are bounded ({spent:,} payload instructions)')
    expect(sorted(c[1] for c in callocs if c[1] in (cap * 4,)) == [cap * 4] * 4, 'four arrays of 4 bytes per artist: the order, the row pointers, the keys, the sections\' scratch (the ranks are a byte each)')
    m.call(PSYMS['ar_on_destroy'], count=200000)
    expect('free' in m.names(), 'closing frees the order')

    # 44. No memory for the order: the stock order, everything works.
    stock = ['Zed', 'The Beatles', 'Abba']
    m = artists_machine(stock); m.calloc_fail_size = 4 * len(stock)   # the order and the row pointers (and the sections' scratch): refused
    expect(m.call(open_, count=20000000) == 0 and shown(m) == stock, 'allocation failure: the stock order')
    m.call(PSYMS['ar_open'], a0=1, count=8000000)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][3] == 'The Beatles', 'and a tap opens the right artist')
    stock = ['Zed', '周杰伦', 'The Beatles', 'Abba']
    m = artists_machine(stock); m.calloc_fail_size = 4 * len(stock) + len('周杰伦'.encode()) + 1   # only the keys (with the copy of the CJK name): refused
    expect(m.call(open_, count=20000000) == 0 and shown(m) == stock, 'no memory for the keys: the stock order')
    m.call(PSYMS['ar_open'], a0=2, count=8000000)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][3] == 'The Beatles', 'and a tap opens the right artist')
    m = artists_machine(['Solo']); m.call(open_, count=20000000)
    expect(shown(m) == ['Solo'] and not [c for c in m.calls if c[0] == 'calloc' and c[1] == 4], 'one artist needs no order')
    m = artists_machine(); m.calloc_fail = True   # no memory for the text ring: the page is left (the tile's stock page opens for Genres and Composers)
    expect(m.call(open_, count=2000000) == 0xffffffff and 'navigator_back' in m.names(), 'no memory for the ring: the page closes')


def index_tests(ctx):
    """An artist's albums take the cache key of the library's album of the same name (ASCII case folded, the FIRST
    library row of a name), through an index when there are IDX_MIN or more of them and a scan below that. Both give the
    same keys; the index does far less work on a big library."""
    expect = ctx.expect
    ascii_fold = lambda s: ''.join(c.lower() if c.isascii() else c for c in s)
    def keys(m, n):   # cf.keys: the word of cf that holds the n-key calloc (no struct offset assumed)
        made = {c[2] for c in m.calls if c[0] == 'calloc' and c[1] == 4 * n and c[2]}
        at = [m.word(PSYMS['cf'] + o) for o in range(0, 512, 4) if m.word(PSYMS['cf'] + o) in made]
        return [m.word(at[0] + 4 * i) for i in range(n)] if len(at) == 1 else None
    def build(lib_n, k):
        m = artists_machine(['Miles Davis'])
        library, lib = [], []
        names = [f'Album {i}' for i in range(lib_n)]
        names[lib_n // 2] = 'ALBUM 7'                      # a later duplicate in another case: the first row (7) wins
        names[lib_n - 2] = 'album 3'                       # ... and again, at the end
        names[10] = 'Éclat'                                # not ASCII: no folding
        for i, nm in enumerate(names):
            artist = f'Lib {i}'
            library.append(m.record(album=nm, artist=artist, path=f'/mnt/mmc/L/{i}/1.flac', rid=i + 1)); lib.append((artist, nm))
        wants = ['album 7', 'ALBUM 3', 'éclat', 'Éclat', 'No such album', 'aLbUm 12'] + [f'Album {lib_n - 1 - j}' for j in range(k)]
        wants = wants[:k] if k < len(wants) else wants
        arts = [m.record(album=w, artist='Miles Davis', path=f'/mnt/mmc/M/{j}/1.flac', rid=500 + j) for j, w in enumerate(wants)]
        m.artist_albums['Miles Davis'] = arts
        m.class_lists[O['CLASS_ALBUMS']] = library; m.showlist = library
        exp = []
        for w in wants:
            row = next((i for i, (_, nm) in enumerate(lib) if ascii_fold(nm) == ascii_fold(w)), None)
            a, nm = lib[row] if row is not None else ('Miles Davis', w)
            exp.append(fnv(fnv(O['FNV_SEED'], a), nm) or 1)
        return m, exp + [0]                                # the All albums card: key 0
    for lib_n, k in ((1000, 16), (1000, 30), (1000, 200), (40, 30)):
        m, exp = build(lib_n, k)
        if PERF: m.count()
        m.call(PSYMS['artists_open'], count=5000000)
        m.call(PSYMS['ar_open'], a0=0, count=900000000)
        got = keys(m, len(exp))
        expect(got == exp, f'{k} artist albums over {lib_n} library albums: every key is the first case-insensitive match\'s (or its own)')
        if PERF: INDEX_COST[(lib_n, k)] = m.icount
        idx = [c for c in m.calls if c[0] == 'calloc' and c[1] == 4 * 2048]
        frees = [c[1] for c in m.calls if c[0] == 'free']
        expect(bool(idx) == (k >= 24 and lib_n == 1000) and all(c[2] in frees for c in idx), f'{k} albums: the index is built only from 24 albums up, and freed')
    # no memory for the index: the scan gives the same keys
    m, exp = build(1000, 200)
    if PERF: m.count()
    m.calloc_fail_size = 4 * 2048
    m.call(PSYMS['artists_open'], count=5000000)
    m.call(PSYMS['ar_open'], a0=0, count=900000000)
    got = keys(m, len(exp))
    expect(got == exp and not [c for c in m.calls if c[0] == 'calloc' and c[1] == 4 * 2048 and c[2]], 'a refused index: the scan finds the same keys')
    if PERF: expect(INDEX_COST[(1000, 200)] < 1000000 and m.icount > 8000000,
           f'200 albums over 1000: {INDEX_COST[(1000, 200)]:,} payload instructions with the index, {m.icount:,} with the scan (10.2 M before the index existed)')


INDEX_COST = {}


def genre_composer_tests(ctx):
    """Genres and Composers on the Artists page (ACT_ARTISTS with the stock Home tile as its argument): the rows, the stock class queried, the stock order, the title
    of the menu row, the Artist / Album Artist switch gone (hidden and insensitive, a stray click does nothing), a genre's tap on our Songs page, a composer's in Cover
    Flow (loadAlbumList(0xf005): class 0xff02), and the fallbacks to the tile's stock page."""
    expect, page, P = ctx.expect, ctx.page, pod_pages
    on_row, rows0, open_ = PSYMS['on_row'], PSYMS['pod_rows_0'], PSYMS['artists_open']
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_artists.bin')
    CI = pod.DATA['CLASSINFO'][0]
    row = {label: next(i for i, r in enumerate(page.rows) if r.label == label) for label in ('Artists', 'Genres', 'Composers')}
    expect([(page.rows[row[k]].action, page.rows[row[k]].arg) for k in row] ==
           [(P.ACT_ARTISTS, 0), (P.ACT_ARTISTS, P.HOME_GENRE), (P.ACT_ARTISTS, P.HOME_COMPOSER)]
           and O['HOME_GENRE'] == P.HOME_GENRE and O['HOME_COMPOSER'] == P.HOME_COMPOSER
           and (O['CLASS_GENRES'], O['CLASS_COMPOSERS'], O['CLASS_COMPOSER_ALBUMS'], O['CLASS_GENRE_SONGS']) == (0xf006, 0xf005, 0xff02, 0xff09),
           'the Artists, Genres and Composers rows are ACT_ARTISTS with the tile as the argument; offsets.inc has the tiles and classes of docs/modules/addresses.md')
    expect(pod_i18n.key_for('Genres') == 'Genres' and pod_i18n.key_for('Composers') == 'Composers', 'the titles\' keys are the menu rows\'')

    # the page on each class: the stock query, the stock order (no sort), the title, no switch
    for label, home, cls, names in (('Genres', P.HOME_GENRE, 0xf006, ('Rock', 'jazz', '周', 'Unknown Genre')),
                                    ('Composers', P.HOME_COMPOSER, 0xf005, ('Mozart', 'Bach', 'The Beatles', 'Unknown Composer'))):
        m = artists_machine(genres=names if cls == 0xf006 else (), composers=names if cls == 0xf005 else ())
        m.call(on_row, a0=rows0 + 12 * row[label], count=20000000)
        calls = list(m.calls)
        title, tog = m.widgets['label_title'], m.widgets['btn_artisttype']
        expect(('window_open', 'm1plus_artists') in calls and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [cls] and 'stock_resume' not in m.names(),
               f'{label}: our Artists page lists class {cls:#x}')
        expect(shown(m) == list(names),
               f'{label}: the rows are the stock list in its own order, unsorted ({shown(m)})')
        expect(('widget_set_text_utf8', title, label) in calls and not any(c[0] == 'widget_set_text_utf8' and c[1] == title and c[2] in ('Artists', 'Album Artists') for c in calls),
               f'{label}: the title is the menu row\'s text')
        expect(m.props.get((tog, 'visible')) == 0 and m.props.get((tog, 'sensitive')) == 0 and (tog, 'style:normal:icon') not in m.props,
               f'{label}: the Artist / Album Artist switch is hidden and insensitive, its glyph left alone')
        np = m.widgets['btn_backtoplayer']
        expect(m.props.get((np, 'style:normal:icon')) == m.props.get((np, 'style:over:icon')) == 'ah_nav_np' and m.props.get((np, 'style:pressed:icon')) == 'ah_nav_np_down',
               f'{label}: with the switch gone Now Playing is the glass disc (ah_nav_np), not the right cap of a capsule that is not there')
        root = asset_tree(asset)
        node(root, 'btn_artisttype').flags &= ~F_SENSITIVE
        if m.props.get((m.widgets['label_status'], 'sensitive')) == 0: node(root, 'label_status').flags &= ~F_SENSITIVE
        expect(stock_target(m, root, O['NAV_VIEW_X'] + 20, 25)[-1] != 'btn_artisttype', f'{label}: a touch on the switch\'s old slot reaches nothing of it')
        expect(stock_target(m, root, 290, 25)[-1] == 'btn_backtoplayer' and stock_target(m, root, 40, 25)[-1] == 'btn_return', f'{label}: Back and Now Playing are hit')
        at = m.word(pod.DATA['ARTIST_TYPE'][0])
        m.calls = []
        m.call(PSYMS['ar_on_toggle'], count=20000000)
        expect(m.word(pod.DATA['ARTIST_TYPE'][0]) == at and not [c for c in m.calls if c[0] in ('write_int_config', 'loadLocalClassList')],
               f'{label}: a stray click on the switch changes no setting and queries nothing')
        m.call(PSYMS['pod_on_back'], count=200000)
        expect('navigator_back' in m.names(), f'{label}: Back goes back')
        m.call(PSYMS['ar_on_destroy'], count=200000)
        expect('deque_destroy' in m.names(), f'{label}: closing frees the copy')
        # no memory for the page's widgets / window: the tile's stock page
        m = artists_machine(genres=names if cls == 0xf006 else (), composers=names if cls == 0xf005 else ()); m.windows['m1plus_artists'] = 0
        m.call(on_row, a0=rows0 + 12 * row[label], count=2000000)
        expect(('stock_resume', str(home)) in m.calls and 'loadLocalClassList' not in m.names(), f'{label}: a window that will not open leaves the tile\'s stock page')
        m = artists_machine(genres=names if cls == 0xf006 else (), composers=names if cls == 0xf005 else ()); del m.widgets['artists_scrollview']
        m.call(on_row, a0=rows0 + 12 * row[label], count=2000000)
        expect('navigator_back' in m.names() and ('stock_resume', str(home)) in m.calls, f'{label}: an asset that is not ours is left for the tile\'s stock page')
        m = artists_machine(genres=(), composers=()); m.class_lists[cls] = []
        m.call(on_row, a0=rows0 + 12 * row[label], count=2000000)
        expect('list_item_create' not in m.names() and any(c[0] == 'widget_set_text_utf8' and 'Update Local Music' in c[2] for c in m.calls),
               f'{label}: an empty library says so, no rows')

    # Artists itself is as it was: sorted, the switch shown and bound, and the title Artists
    m = artists_machine(); m.call(on_row, a0=rows0 + 12 * row['Artists'], count=20000000)
    tog = m.widgets['btn_artisttype']
    expect(m.props.get((tog, 'visible')) != 0 and m.props.get((tog, 'sensitive')) != 0 and ('widget_set_text_utf8', m.widgets['label_title'], 'Artists') in m.calls
           and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ARTISTS']], 'the Artists row: the switch stays, the title is Artists, class 0xf004')
    expect((m.widgets['btn_backtoplayer'], 'style:normal:icon') not in m.props, 'and Now Playing keeps the capsule\'s right cap')

    # a genre's tap: our Songs page (songs_open_genre), the genre's name and the Unknown byte; the stock row tap's own sequence when that window will not open
    names = ('Rock', 'Jazz', 'Unknown Genre')
    for k, (name, unknown) in enumerate(zip(names, (0, 0, 1))):
        m = artists_machine(genres=names); m.call(open_, a0=P.HOME_GENRE, count=20000000)
        m.calls = []
        m.call(PSYMS['ar_open'], a0=k, count=8000000)
        expect(('window_open', 'm1plus_songs') in m.calls and 'loadAlbumList' not in m.names()
               and not any(c == ('window_open', 'm1plus_cover') for c in m.calls), f'a tap on genre {name!r} opens our Songs page, not Cover Flow')
        m = artists_machine(genres=names); m.call(open_, a0=P.HOME_GENRE, count=20000000); m.windows['m1plus_songs'] = 0
        m.calls = []
        m.call(PSYMS['ar_open'], a0=k, count=8000000)
        nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
        expect(nav and nav[0][:3] == ('navigator_to_with_context', 'allmusic_page', O['CLASS_GENRE_SONGS']) and m.word(CI) == O['CLASS_GENRE_SONGS']
               and m.read_cstr(CI + O['CLASSINFO_GENRE']) == name and m.u.mem_read(CI + O['CLASSINFO_GENRE_UNKNOWN'], 1)[0] == unknown,
               f'songs window will not open: the stock row tap\'s sequence for {name!r} (classinfo[0] 0xff09, the name at +0x30d, byte +0xc = {unknown}, then allmusic_page 0xff09)')

    # a composer's tap: Cover Flow on that composer's albums (loadAlbumList(0xf005, row) = getAlbumByComposer, the All songs row last, class 0xff02)
    comps = ('Mozart', 'Bach', 'Unknown Composer')
    m = artists_machine(composers=comps); m.call(open_, a0=P.HOME_COMPOSER, count=20000000)
    m.calls = []
    m.call(PSYMS['ar_open'], a0=1, count=8000000)   # Bach: two albums and the card
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(('window_open', 'm1plus_cover') in m.calls and la and la[0][1] == O['CLASS_COMPOSERS'] and la[0][3] == 'Bach' and ('window_open', 'm1plus_songs') not in m.calls,
           f'a composer opens Cover Flow with loadAlbumList(0xf005, that composer) ({la[:1]})')
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Bach') in m.calls and ('widget_set_text_utf8', m.widgets['label_album'], 'Goldberg Variations') in m.calls,
           'titled with the composer, centred on his first album')
    put_value(m, 2); m.call(PSYMS['on_changed'], count=2000000)
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'All albums') in m.calls and ('widget_set_text_utf8', m.widgets['label_artist'], 'Bach') in m.calls,
           'two albums: the All albums card over the composer')
    m.calls = []
    m.click('btn_songs', count=900000000)
    npw = m.widgets['btn_backtoplayer']
    expect(m.props.get((m.widgets['btn_songs'], 'visible')) != 1 and m.props.get((npw, 'style:normal:icon')) != 'ah_nav_play'
           and not any(c[0] in ('window_open', 'loadAlbumdetailList') or (c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page') for c in m.calls),
           'a composer\'s page has no Songs button (it runs the artist queries) and Now Playing keeps its disc, and a stray click on it opens nothing')
    m.tap(O['CF_CX'])
    order = [c[0] for c in m.calls if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context')][-3:]
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(order == ['loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context'] and la[-1][1] == O['CLASS_COMPOSERS'] and la[-1][3] == 'Bach'
           and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS'], 2) in m.calls,
           'the card: the composer into the browsing record again, then albuminfo_page with class 0xff02 and the card row')
    cls, rowi, shown_list = m.opened_album
    expect(m.word(m.deques[shown_list][rowi] + O['REC_ID']) == O['ID_ALL_SONGS'] & 0xffffffff, 'that row is the stock All songs row')
    put_value(m, 1); m.call(PSYMS['on_changed'], count=2000000)
    m.tap(O['CF_CX'])
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS'], 1) in m.calls
           and m.read_cstr(m.word(m.deques[m.opened_album[2]][1] + O['REC_ALBUM'])) == 'Cello Suites', 'a centre album opens as the stock composer page opens it (class 0xff02, its row)')
    m.call(PSYMS['on_destroy'], count=2000000)
    # the artist's own scope is untouched by a composer's (the scope is per open)
    m = artists_machine(composers=comps); m.call(open_, count=20000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    put_value(m, 3); m.call(PSYMS['on_changed'], count=2000000); m.tap(O['CF_CX'], count=900000000)
    expect(la[0][1] == O['CLASS_ARTISTS'] and ('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS']) in [c[:2] for c in m.calls] and ('window_open', 'm1plus_songs') in m.calls, 'an artist after a composer: class 0xf004 and 0xff01 again, its card opens our Songs page')
    # a composer with one album: no card; the Unknown Composer row: No albums
    m = artists_machine(composers=comps); m.call(open_, a0=P.HOME_COMPOSER, count=20000000)
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    shown_one = ('widget_set_text_utf8', m.widgets['label_album'], 'Requiem') in m.calls
    put_value(m, 1); m.call(PSYMS['on_changed'], count=2000000)
    expect(shown_one and not any(c[0] == 'widget_set_text_utf8' for c in m.calls), 'a composer with one album gets no card')
    m = artists_machine(composers=comps); m.call(open_, a0=P.HOME_COMPOSER, count=20000000)
    m.call(PSYMS['ar_open'], a0=2, count=8000000)
    expect(any(c[0] == 'widget_set_text_utf8' and c[2] == 'No albums' for c in m.calls), 'a composer without albums says No albums')


def scoped_albums_tests(ctx):
    """A tap on an artist or composer opens our Albums page scoped to them (the shared grid / list mode, the name as the title, the All songs row dropped);
    its Cover Flow button opens the old scoped Cover Flow; a window that will not open falls back to Cover Flow."""
    expect = ctx.expect
    open_ = PSYMS['artists_open']
    ROWH, RGAP = O['LIST_ROW_H'], O['GRID_ROW_GAP']
    CELL_PITCH = O['GRID_COVER'] + O['GRID_TITLE_GAP'] + O['GRID_TITLE_H'] + O['GRID_SUB_H'] + RGAP   # the grid's row pitch (patch/grid.h)
    sv_y = SCREEN_Y0

    def content(m): return [c[3] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1]
    def tap(m, x, y):
        m.touch('down', x, sv_y + y, 1000, fn='al_on_down'); calls = list(m.calls)
        m.touch('up', x, sv_y + y, 1080, fn='al_on_up', count=40000000); m.calls = calls + m.calls
    def opened(artists=('Miles Davis', 'Nina Simone', 'Unknown Artist'), composers=(), view=b'0\n', i=0, home=0):
        m = artists_machine(artists=artists, composers=composers, albums_page=True)
        if view is not None: m.fs['/mnt/data/m1plus/albums-view'] = view
        m.call(open_, a0=home, count=20000000)
        m.calls = []
        m.call(PSYMS['ar_open'], a0=i, count=40000000)
        return m

    # an artist: the Albums page (list mode as saved), the artist's albums without the All songs row, the artist as the title
    m = opened()
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(('window_open', 'm1plus_albums') in m.calls and ('window_open', 'm1plus_cover') not in m.calls,
           'a tap on an artist opens the Albums page, not Cover Flow')
    expect(la and la[0][1] == O['CLASS_ARTISTS'] and la[0][3] == 'Miles Davis', f'the stock artist query runs for that artist ({la[:1]})')
    expect(content(m) == 4 * ROWH, f'three albums and the All Songs row last ({content(m)} px of list rows)')
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.calls, 'the title is the artist')
    expect(m.fs['/mnt/data/m1plus/albums-view'] == b'0\n' and m.props.get((m.widgets['btn_albumview'], 'style:normal:icon')) == 'pod_nav_grid',
           'the list mode saved for Albums is the mode used, the toggle shows the grid glyph')
    # the covers are the library's files (Jazz Hits is filed under Various Artists there)
    loads = []
    for _ in range(12):
        m.call(PSYMS['al_on_load'], count=40000000); loads += [c[1] for c in m.calls if c[0] == 'widget_load_image']
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in m.calls): break
    jazz = 'file://' + art_file(fnv(fnv(O['FNV_SEED'], 'Various Artists'), 'Jazz Hits'))
    expect(jazz in loads and len(set(loads)) == 3, f'the covers take the library album\'s cache keys ({loads})')
    # a tap on the second row opens the artist's album page (class 0xff01)
    m.calls = []
    tap(m, 100, ROWH + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 1) in m.calls
           and [c for c in m.calls if c[0] == 'loadAlbumList'][-1][3] == 'Miles Davis', 'a tap on an album opens its page as the artist\'s album (0xff01, its row)')
    # the toggle persists in the shared file and keeps the artist's albums
    m.calls = []
    m.call(PSYMS['al_on_toggle'], count=40000000)
    expect(m.fs.get('/mnt/data/m1plus/albums-view') == b'1\n' and content(m) == RGAP + 2 * CELL_PITCH, 'the toggle switches to the grid and writes the shared file')
    # Cover Flow, one tap away, on the same artist
    m.calls = []
    m.call(PSYMS['al_on_cover'], count=40000000)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(('window_open', 'm1plus_cover') in m.calls and la and la[0][3] == 'Miles Davis' and ('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.calls,
           'the Cover Flow button opens Cover Flow scoped to the same artist')
    expect(m.fs.get('/mnt/data/m1plus/albums-view') == b'1\n', 'Cover Flow is never stored as the mode: the file still says grid')
    m.call(PSYMS['pod_on_back'], count=2000000)
    m.calls = []
    m.call(PSYMS['al_on_destroy'], count=2000000)
    expect(m.names().count('deque_destroy') >= 2, 'closing frees the album list and the artist row')
    expect(m.fs.get('/mnt/data/m1plus/albums-view') == b'1\n', 'Back from the scoped page leaves the stored mode alone')

    # the mode is the one shared file: the grid chosen on the artist's page is the next artist's and Home > Albums', and the other way round
    grid = lambda m: m.props.get((m.widgets['btn_albumview'], 'style:normal:icon')) == 'pod_nav_list'
    m2 = opened(view=b'1\n', i=1)
    expect(grid(m2) and content(m2) == RGAP + CELL_PITCH, 'an artist tap opens the grid when the grid was chosen last')
    m3 = artists_machine(albums_page=True); m3.fs.update(m.fs); m3.call(PSYMS['albums_open'], count=20000000)
    expect(grid(m3), 'Home > Albums opens in the mode chosen on the artist page')
    m3.call(PSYMS['al_on_toggle'], count=40000000)
    expect(m3.fs.get('/mnt/data/m1plus/albums-view') == b'0\n', 'toggled on Home > Albums: list')
    m4 = artists_machine(albums_page=True); m4.fs.update(m3.fs); m4.call(open_, count=5000000); m4.calls = []
    m4.call(PSYMS['ar_open'], a0=0, count=40000000)
    expect(not grid(m4) and content(m4) == 4 * ROWH and ('window_open', 'm1plus_cover') not in m4.calls, 'and the next artist tap opens the list, never Cover Flow')

    # the All Songs row: the last tile, the artist as its second line, our Songs page on every song of the artist
    m = opened(); m.strings = {'local_allsong': 'All Songs'}
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], SCREEN_Y0 & 0xffffffff)
    m.texts.clear(); m.blits.clear()
    m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
    tx = [t for t, r in m.texts]
    expect(tx == ['Kind of Blue', 'Jazz Hits', 'Bitches Brew', 'All Songs'] + ['Miles Davis'] * 4, f'the fourth row is All Songs over the artist ({tx})')
    m.calls = []
    tap(m, 100, 3 * ROWH + 10)
    expect(('window_open', 'm1plus_songs') in m.calls and not any(c[0] == 'navigator_to_with_context' for c in m.calls), 'a tap on All Songs opens our Songs page on the artist\'s songs')
    m = opened(); m.windows['m1plus_songs'] = 0; m.calls = []
    tap(m, 100, 3 * ROWH + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 3) in m.calls, 'the Songs page will not open: the stock page on the All songs row')
    m = opened(i=1, view=b'1\n')
    expect(content(m) == RGAP + CELL_PITCH, 'one album: no All Songs tile')
    m = opened(i=0, view=b'1\n'); m.calls = []
    tap(m, O['GRID_MARGIN'] + O['GRID_COVER'] + O['GRID_GAP'] + 10, RGAP + CELL_PITCH + 10)   # the grid's fourth tile: row 1, column 1
    expect(('window_open', 'm1plus_songs') in m.calls, 'the grid\'s last tile is All Songs too')

    # one album, none
    m = opened(i=1)
    expect(content(m) == ROWH, 'one album: one row')
    m = opened(i=2)
    expect(any(c[0] == 'widget_set_text_utf8' and c[2] == 'No albums' for c in m.calls), 'an artist without albums says No albums')

    # a composer: loadAlbumList(0xf005), class 0xff02
    m = opened(composers=('Mozart', 'Bach', 'Unknown Composer'), home=pod_pages.HOME_COMPOSER, i=1)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(('window_open', 'm1plus_albums') in m.calls and la and la[0][1] == O['CLASS_COMPOSERS'] and la[0][3] == 'Bach'
           and ('widget_set_text_utf8', m.widgets['label_title'], 'Bach') in m.calls and content(m) == 3 * ROWH, 'a composer: his two albums and the All Songs row on the Albums page')
    m.calls = []
    tap(m, 100, 10)
    expect(any(c[:3] == ('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS']) for c in m.calls), 'and his album page opens as a composer\'s (0xff02)')
    m.calls = []
    tap(m, 100, 2 * ROWH + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS'], 2) in m.calls and ('window_open', 'm1plus_songs') not in m.calls,
           'a composer\'s All Songs row is the stock page on the All songs row, as Cover Flow\'s card (no composer songs page)')

    # a window that will not open: Cover Flow on the artist, as before
    m = artists_machine(); m.call(open_, count=5000000); m.calls = []
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    expect(('window_open', 'm1plus_albums') in m.calls and ('window_open', 'm1plus_cover') in m.calls, 'the Albums window will not open: Cover Flow on the artist')


SECTIONS = [artists_tests, scoped_albums_tests, genre_composer_tests, index_tests, sort_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

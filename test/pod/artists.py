"""Artists: the list page and Cover Flow scoped to one artist."""
import os, struct
import mod_icons
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

VIEW_H, TOP, HDR, ROW, BOTTOM = O['GRID_VIEW_H'], O['SG_TITLE_H'], O['SG_HDR_H'], 52, 12
INSET = O['SG_RAIL_INSET']   # the rows give up this much on the right while the A-Z rail is shown (patch/azlist.c az_inset); rail off: the list-row spec (chevron x 288, text to 278, hairline to 310)
TEXT_X, TEXT_Y, TEXT_H, TEXT_END = 24, (52 - O['LIST_TITLE_H']) // 2, O['LIST_TITLE_H'], O['LIST_TEXT_X'] + O['LIST_TEXT_W_CHEV'] - INSET
CHEV_X, CHEV_W, CHEV_H = O['LIST_CHEV_X'] - INSET, 10, 16
PHOTO, PHOTO_X, NAME_X = 40, 16, 68   # layout A (Artists and Album Artists): a 40 px circle at x 16, the name and the hairline from x 68; Genres and Composers keep TEXT_X
HAIR_END = O['LIST_HAIR_END'] - INSET
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
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Bitches Brew') in m.calls, 'the first album is centred')
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
    #      one album or many (every artist or composer whose stock list had the All songs row); never on the main Cover Flow or while preparing.
    tree = awtk_ui.parse(open(cover_asset, 'rb').read())
    flags = lambda w: {k: v for k, v in w.props}
    sb = tree.find('btn_songs')
    expect(sb and (sb.x, sb.y, sb.w, sb.h) == (O['NAV_VIEW_X'], 0, O['NAV_VIEW_W'], pod_ui.NAVBAR_H)
           and flags(sb).get('visible') == 'false' and flags(sb).get('sensitive') == 'false' and 'pod_nav_songs_down' in str(sb.props) and 'pod_nav_songs' in str(sb.props)
           and mod_icons.NAV_VIEW_POS['pod_nav_songs'] == 'left' and 'NAV_SONGS_X' not in O,
           'the asset has the Songs button at x 214, 46 wide, hidden and insensitive, with its left-cap glyph and pressed glyph')
    expect(tree.find('btn_allalbums') is None and flags(tree.find('btn_backtoplayer')).get('style:normal:icon') == 'ah_nav_np',
           'the asset has no All albums button, and Now Playing is the disc (the main Cover Flow keeps it)')
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
    def __init__(self, names, hh=HDR):   # hh: the header height, 0 with Section Headers off
        self.hh = hh
        ranks = []
        for i, n in enumerate(names): ranks.append(ranks[-1] if n.startswith('Unknown') and i else rank_of(n))
        self.n, self.secs = len(names), sections_of(ranks) if names else []
    def hdr_y(self, s): return TOP + s * self.hh + self.secs[s][0] * ROW
    def sec_of(self, i): return max(k for k, (st, _) in enumerate(self.secs) if st <= i)
    def row_y(self, i): return TOP + (self.sec_of(i) + 1) * self.hh + i * ROW
    def content(self): return TOP + len(self.secs) * self.hh + self.n * ROW + BOTTOM


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


def card_texts(m):
    """The card's texts as the asset's labels give them (the machine measures a text from widget_get_text), and a 60 px measure: the card is fitted to 180 px."""
    for i, t in enumerate(('Name', 'Name', 'Name', 'Name', 'Artists', 'Album Artists', 'Search Artists')): m.wtext[m.widgets[f'vs_label{i}']] = t
    for i in range(4): m.wtext[m.widgets[f'vs_sub{i}']] = 'A–Z'
    m.measure = lambda t: 60


def pick(m, row, count=20000000):
    """Opens the "..." card and taps its row `row` (0 Name, 4 Artists, 5 Album Artists, 6 Search Artists)."""
    m.click('btn_more')
    return m.click(f'vs_item{row}', count=count)


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
    want = [(n, (NAME_X, mod.row_y(i) + TEXT_Y, TEXT_END - NAME_X, TEXT_H)) for i, n in enumerate(['Miles Davis', 'Nina Simone', 'Unknown Artist'])]
    expect(rows == want, f'the names are drawn in their 24 px boxes from x {NAME_X} (right of the circle), up to x {TEXT_END} (the chevron\'s room): {rows}')
    hd = [(t, r[1]) for (t, r), s in zip(texts, styles) if s == 'label_hdr']
    expect(hd == [('M', mod.hdr_y(0)), ('N', mod.hdr_y(1))], f'the section letters at their headers, the Songs page\'s (x {O["SG_HDR_X"]}, 20 px): {hd}')
    chev = [b for b in blits if tuple(b[2][2:]) == (CHEV_W, CHEV_H)]
    expect([tuple(b[2]) for b in chev] == [(CHEV_X, mod.row_y(i) + (ROW - CHEV_H) // 2, CHEV_W, CHEV_H) for i in range(3)], 'a chevron at the right of every row, centred in its row')
    hair = [f for f in fills if f[0] == O['LIST_HAIR'] and f[3] == HAIR_END - NAME_X]
    expect([(f[1], f[2], f[4]) for f in hair] == [(NAME_X, mod.row_y(i) + ROW - 1, 1) for i in range(3)], 'a hairline under every row from the text\'s x (68)')
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

    # 29f. The Index Rail and Section Headers switches (patch/azlist.c az_prefs, read when the page opens): both on by default; with the headers off the rows close up (header height 0), the
    # rail (when on) still jumps to the section's first row, nothing paints a letter or a pinned band; the rows keep the full list-row width with the rail off and give up SG_RAIL_INSET with it on
    bands = [f'{chr(65 + i)} Band' for i in range(26)] + [f'{chr(65 + i)}2 Band' for i in range(0, 26, 5)]
    for rail, heads in ((b'0\n', b'1\n'), (b'0\n', b'0\n'), (b'1\n', b'0\n'), (b'1\n', b'1\n')):
        mm = artists_machine(bands); mm.fs[AZRAIL_FILE], mm.fs[AZHEAD_FILE] = rail, heads
        mm.call(open_, count=40000000)
        hh = 0 if heads == b'0\n' else HDR
        mod = Model(shown(mm), hh)
        what = f'rail {rail.strip().decode()}, headers {heads.strip().decode()}'
        expect(mm.props.get((mm.sv, 'virtual_h')) == mod.content() and vis(mm, 'sg_rail') == ((1, 1) if rail == b'1\n' else (0, 0)),
               f'{what}: the content is {mod.content()} px (header height {hh}) and the rail is {"shown" if rail == b"1\n" else "hidden and insensitive"}')
        letters = []
        for off in range(0, mod.content() - VIEW_H, 150):
            _, texts, styles, _ = ar_paint(mm, off)
            letters += [t for (t, r), s in zip(texts, styles) if s == 'label_hdr']
        _, _, _, fills = ar_paint(mm, 300)
        expect(bool(letters) == bool(hh) and bool([f for f in fills if f[0] == O['SG_HDR_BG']]) == bool(hh), f'{what}: section letters and the pinned band only with the headers')
        _, texts, styles, fills = ar_paint(mm, 0)
        rows = [r[1] for (t, r), s in zip(texts, styles) if s == 'label_row_title']
        expect(rows[:3] == [mod.row_y(i) + TEXT_Y for i in range(3)], f'{what}: the rows start at {mod.row_y(0)}')
        hair = [f for f in fills if f[0] == O['LIST_HAIR']]
        gap = INSET if rail == b'1\n' else 0   # the rail's footprint: hairline end, chevron x and text end move left by it, with the rail off the rows keep the list-row spec
        expect(hair and all(f[1] == NAME_X and f[3] == O['LIST_HAIR_END'] - gap - NAME_X for f in hair), f'{what}: the hairlines end at {O["LIST_HAIR_END"] - gap}')
        blits, texts, styles, _ = ar_paint(mm, 0)
        chev = [tuple(b[2]) for b in blits if tuple(b[2][2:]) == (CHEV_W, CHEV_H)]
        names = [r for (t, r), s in zip(texts, styles) if s == 'label_row_title']
        expect(chev and all(c[0] == O['LIST_CHEV_X'] - gap for c in chev) and names and all(r[0] + r[2] == O['LIST_TEXT_X'] + O['LIST_TEXT_W_CHEV'] - gap for r in names),
               f'{what}: the chevrons at x {O["LIST_CHEV_X"] - gap} and the names cut at x {O["LIST_TEXT_X"] + O["LIST_TEXT_W_CHEV"] - gap}')
        if rail == b'1\n':
            geo = tuple(mm.props.get((mm.rail, k)) for k in 'xywh')
            sp = geo[3] - 2 * O['SG_RAIL_PAD']
            mm.calls = []
            mm.touch('down', 300, 30 + geo[1] + O['SG_RAIL_PAD'] + int((5 + 0.5) * sp / len(mod.secs)), 3000, fn='ar_on_rail', count=40000000)
            want = min(mod.hdr_y(5), mod.content() - VIEW_H)
            got = [c for c in mm.calls if c[0] == 'widget_set_prop_int' and c[2] == 'yoffset']
            expect(got and got[0][3] == want and (hh or want == min(mod.row_y(mod.secs[5][0]), mod.content() - VIEW_H)), f'{what}: the rail jumps to section {mod.secs[5][1]} at {want}' + ('' if hh else ' (its first row)'))
            mm.touch('up', 300, 200, 3100, fn='ar_on_rail', count=4000000)

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
    expect(all(n in names for n in ('btn_return', 'btn_backtoplayer', 'btn_more', 'label_title', 'navigationbar_view', 'sg_bubble_letter')) and 'btn_artisttype' not in names and
           not [n for n in names if n in ('pod_listview', 'pod_scrollview')], 'the navbar keeps its buttons and title, the "..." replaces the switch; the old list names are gone')
    tog = tree.find('btn_more')
    expect((tog.x, tog.y, tog.w, tog.h) == (O['NAV_VIEW_X'], 0, O['NAV_VIEW_W'], O['NAV_H']) and tog.x + tog.w == tree.find('btn_backtoplayer').x and tog.get('visible') != 'false', 'btn_more is the capsule\'s left cap in the 214 slot, flush left of Now Playing')
    lbl = tree.find('label_title')
    expect(lbl.x + lbl.w == O['NAV_VIEW_X'], 'the small title ends where the "..." begins')
    expect(tog.get('style:normal:icon') == 'pod_nav_more' and tog.get('style:pressed:icon') == 'pod_nav_more_down' and tree.find('btn_backtoplayer').get('style:normal:icon') == 'ah_nav_play',
           'the "..." is the left cap and Now Playing the right cap of one capsule')
    mm = artists_machine(); mm.call(open_, count=5000000)
    root = asset_tree(asset)
    node(root, 'view_grid').h = 3000
    r = node(root, 'sg_rail'); r.x, r.y, r.w, r.h = (mm.props.get((mm.rail, k), v) for k, v in zip('xywh', (r.x, r.y, r.w, r.h)))
    expect(stock_target(mm, root, 150, 300)[-1] == 'view_grid' and 'artists_scrollview' in stock_target(mm, root, 150, 300), 'a touch in the list is the content view\'s, through the scroll view')
    expect(stock_target(mm, root, 40, 25)[-1] == 'btn_return' and stock_target(mm, root, 290, 25)[-1] == 'btn_backtoplayer' and stock_target(mm, root, O['NAV_VIEW_X'] + 20, 25)[-1] == 'btn_more',
           'Back, Now Playing and the "..." are hit')
    expect(stock_target(mm, root, 300, r.y + r.h // 2)[-1] == 'sg_rail', 'a touch in the rail\'s column within its span reaches the rail, never the scroll view')
    expect('label_status' not in stock_target(mm, root, 160, 225) and 'sg_bubble' not in stock_target(mm, root, 160, 225), 'the hidden message and the bubble take no touch')

    # 31. The Show group: the stock switch's writes, the other mode's list, the titles (the large one too), the ticks
    AT, RELOAD = pod.DATA['ARTIST_TYPE'][0], pod.DATA['ARTIST_RELOAD'][0]
    m = artists_machine(); m.call(open_, count=5000000)
    big, title = m.widgets['ar_title'], m.widgets['label_title']
    expect(('widget_set_text_utf8', title, 'Artists') in m.calls and ('widget_set_text_utf8', big, 'Artists') in m.calls, 'artist_type 0: both titles read "Artists"')
    mclicks = [c for c in opened if c[0] == 'widget_on' and c[1] == m.widgets['btn_more'] and c[2] == O['EVT_CLICK']]
    expect(len(mclicks) == 1 and mclicks[0][3] == PSYMS['ar_on_more'], 'the "..." button is bound')
    m.click('btn_more')
    expect(vis(m, 'vs_card') == (1, 1) and [vis(m, f'vs_tick{i}')[0] for i in (0, 4, 5)] == [1, 1, 0], 'the card opens with Name and Artists ticked')
    scroll_to(m, 300)
    pick(m, 5)
    new = m.calls
    expect(m.word(AT) == 1 and ('write_int_config', 1, 'PLAYSET', 'ARTISTTYPE') in new and m.u.mem_read(RELOAD, 1)[0] == 1, 'the Album Artists row sets artist_type, saves [PLAYSET] ARTISTTYPE and raises the stock reload flag')
    expect(('widget_set_text_utf8', title, 'Album Artists') in new and ('widget_set_text_utf8', big, 'Album Artists') in new and vis(m, 'vs_card') == (0, 0), 'both titles read "Album Artists", the card closes')
    expect(('loadLocalClassList', O['CLASS_ARTISTS']) in new and ('widget_set_prop_int', m.sv, 'yoffset', 0) in new and 'deque_destroy' in [c[0] for c in new],
           'the stock query runs again, the list is at the top, the previous copy is freed')
    expect(shown(m) == ['Miles Davis', 'Various Artists'] and m.props.get((m.sv, 'virtual_h')) == Model(['Miles Davis', 'Various Artists']).content(), 'the list is the album-artist list (sorted: stock has Various Artists first)')
    m.click('btn_more')
    expect([vis(m, f'vs_tick{i}')[0] for i in (4, 5)] == [0, 1], 'reopened, Album Artists is ticked')
    m.calls = []
    m.click('vs_item5', count=20000000)
    expect(m.word(AT) == 1 and not [c for c in m.calls if c[0] in ('write_int_config', 'loadLocalClassList')] and vis(m, 'vs_card') == (0, 0), 'the ticked row does nothing but close the card')
    pick(m, 4)
    expect(m.word(AT) == 0 and ('write_int_config', 0, 'PLAYSET', 'ARTISTTYPE') in m.calls and ('widget_set_text_utf8', title, 'Artists') in m.calls, 'the Artists row sets Artist again, titles with it')
    m3 = artists_machine(); m3.setword(AT, 1); m3.call(open_, count=5000000); calls3 = list(m3.calls)
    m3.click('btn_more')
    expect(shown(m3) == ['Miles Davis', 'Various Artists'] and ('widget_set_text_utf8', m3.widgets['label_title'], 'Album Artists') in calls3 and [vis(m3, f'vs_tick{i}')[0] for i in (4, 5)] == [0, 1],
           'opening with album artist set lists them, titled "Album Artists", ticked in the card')
    m4 = artists_machine(); del m4.widgets['label_title']; del m4.widgets['ar_title']
    m4.call(open_, count=5000000)
    expect(shown(m4) == ['Miles Davis', 'Nina Simone', 'Unknown Artist'] and 'navigator_back' not in m4.names(), 'a page without the titles still lists')

    # 32. Back leaves the Artists page; closing it frees its copy and bitmaps. An empty library: the message, no list. A broken asset: leave.
    m.call(PSYMS['pod_on_back'], count=200000)
    expect('navigator_back' in m.names(), 'Back on the Artists page goes back')
    m.call(PSYMS['ar_on_destroy'], count=2000000)
    expect('deque_destroy' in m.names() and sum(1 for c in m.calls if c[0] == 'bitmap_destroy') == 3, 'closing the Artists page frees its list and its bitmaps (the rail disc, the chevron, the circle placeholder)')
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
            if x in (TEXT_X, NAME_X): names[y + off] = t
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

    # 41. Non-Latin names: a CJK name is placed by its pinyin initials and a kana name by its romaji initials among the Latin names, an accented Latin letter its base letter, any other script leads with the symbols; only Unknown Artist is fixed.
    stock = ['Zed', '周杰伦', 'The Beatles', 'Abba', 'Мумий Тролль', 'Bob', 'Éric', 'Aaa', 'あいみょん', 'Unknown Artist']
    want, _ = sort_model(stock)
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == want, f'mixed scripts: {got}')
    expect(got == ['Мумий Тролль', 'Aaa', 'Abba', 'あいみょん', 'The Beatles', 'Bob', 'Éric', 'Zed', '周杰伦', 'Unknown Artist'],
           'other scripts first by byte (symbols), then the Latin names (あいみょん = "aimyon" after Abba; Éric = "eric" after Bob; Zed before 周杰伦 = "zjl"); Unknown Artist last')
    # 41b. Kana by romaji initial (the Album Artists page listed ヨルシカ under Z), the rest of the non-ASCII names with the symbols under "#".
    stock = ['Zedd', 'ヨルシカ', '米津玄師', 'Ólafur Arnalds', '아이유', '123', 'Yorushika', 'ガール', 'ひかる', 'ーx', 'ヴァ', 'ヲ', 'Éric', 'Eric', 'Beyoncé', 'Mумий Тролль', 'Ångström', '×÷', 'Þór', 'Łódź', 'Æon', 'Straße']
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == sort_model(stock)[0], f'kana model: {got}')
    pos = got.index
    expect(pos('123') < pos('×÷') < pos('아이유') < pos('Ångström') and pos('ガール') < pos('Zedd') and pos('Yorushika') < pos('ヨルシカ') < pos('Zedd'),
           f'digits, then non-ASCII with no initial (米津玄師 "mjxs" is a letter), then letters; ヨルシカ "yrsk" files under Y, ガール "gr" under G: {got}')
    expect(pos('Ångström') < pos('Æon') < pos('Beyoncé') < pos('Éric') < pos('Eric') < pos('ガール') < pos('Łódź') < pos('Mумий Тролль') < pos('Ólafur Arnalds') < pos('Straße') < pos('Þór') < pos('Yorushika'),
           f'accented Latin letters file under their base letter (Æ a, Ł l, ß s, Þ t); Éric and Eric tie on "eric": stock order; × ÷ are symbols: {got}')
    mod = Model(got)
    hd = headers(m)
    expect(hd == {mod.hdr_y(s): l for s, (_, l) in enumerate(mod.secs)} and [l for _, l in mod.secs][-1] == 'Z' and 'Y' in [l for _, l in mod.secs],
           f'sections: ヨルシカ files under Y, not Z ({sorted(hd.values())})')
    expect('#' in hd.values() and all(l in hd.values() for l in 'AEOSTL'), f'sections: an accented name has its base letter header ({sorted(hd.values())})')
    m2 = artists_machine(stock); m2.call(open_, count=20000000)
    m2.call(PSYMS['ar_open'], a0=got.index('ヨルシカ'), count=8000000)
    la = [c for c in m2.calls if c[0] == 'loadAlbumList']
    expect(la and la[0][3].encode('latin-1').decode() == 'ヨルシカ', 'a tap opens the right artist')
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
    stock = ['Vol. 10', 'vol. 2', 'Vol. 1', '  Zed', '2 Pac', '10 Pac', '_&', 'Abc', '007', '7', '  Abc']
    m = artists_machine(stock); m.call(open_, count=20000000)
    got = shown(m)
    expect(got == sort_model(stock)[0], f'natural order: {got}')
    expect(got.index('Vol. 1') < got.index('vol. 2') < got.index('Vol. 10'), 'digit runs compare by value ("Vol. 2" before "Vol. 10")')
    expect(got.index('2 Pac') < got.index('10 Pac') < got.index('_&') < got.index('Abc'), 'digits before symbols before letters')
    expect(got.index('Abc') < got.index('  Abc') < got.index('Vol. 1') and got[-1] == '  Zed', 'leading white space is skipped; the equal names keep the stock order (Abc 7, "  Abc" 10)')
    expect(got.index('007') < got.index('7'), 'equal values keep the stock order ("007" is stock row 8, "7" row 9)')

    # 42. Both modes and the toggle: each mode's list is sorted, a tap opens the right one, the toggle re-sorts.
    m = artists_machine(); m.album_artists = [artist_rec(m, a, i + 1) for i, a in enumerate(('The Zed', 'Various Artists', 'the Abba', '周'))]
    m.call(open_, count=20000000)
    m.calls = []
    pick(m, 5)
    expect(shown(m) == ['the Abba', 'Various Artists', '周', 'The Zed'],
           'Album Artist mode is sorted too (The Zed files under Z, after 周 "z")')
    m.calls = []
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    expect([c for c in m.calls if c[0] == 'loadAlbumList'][:1] and [c for c in m.calls if c[0] == 'loadAlbumList'][0][3] == 'the Abba',
           'a tap on the first Album Artist row opens it')
    m.calls = []
    pick(m, 4)
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
    # 41c. Leading punctuation is skipped when something follows it (cc_name_keys / cc_name_initial, so_name): "(What's the Story)" files under W, "¡Viva" under V, "「すずめ」" under S,
    # "(The Best Of)" under B (the "The " after the punctuation goes too), "   (x" under X, "+44" is the digits "44" (under "#"); names of punctuation only ("!!!", "...", "=", "÷") stay under "#".
    stock_p = ["(What's the Story)", 'Wall', '\u00a1Viva', 'Vaca', '\u300c\u3059\u305a\u3081\u300d', 'Sam', '(The Best Of)', 'Bob', '   (x', 'Xylo', '+44', '45', '!!!', '...', '=', '\u00f7', 'Zed', 'Wish']
    mp = artists_machine(stock_p); mp.call(open_, count=20000000)
    got_p = shown(mp)
    expect(got_p == sort_model(stock_p)[0], f'leading punctuation model: {got_p}')
    pos = got_p.index
    expect(pos('Wall') < pos("(What's the Story)") < pos('Wish') and pos('Vaca') < pos('\u00a1Viva') < pos('Wall') and pos('Sam') < pos('\u300c\u3059\u305a\u3081\u300d') < pos('Wall')
           and pos('(The Best Of)') < pos('Bob') < pos('Sam') and pos('   (x') < pos('Xylo') < pos('Zed') and pos('+44') < pos('45'), f'W, V, S, B, X placed by the first letter after the punctuation, +44 as 44: {got_p}')
    expect(all(pos(x) < pos('Bob') for x in ('!!!', '...', '=', '\u00f7', '+44', '45')), f'punctuation-only names and digits stay with the symbols: {got_p}')
    hd_p = headers(mp)
    expect(sorted(set(hd_p.values())) == sorted(['#', 'B', 'S', 'V', 'W', 'X', 'Z']), f'sections: #, B, S, V, W, X, Z only ({sorted(hd_p.values())})')


def index_tests(ctx):
    """An artist's albums take the cache key of the library's album of the same name (ASCII case folded, the FIRST
    library row of a name), through an index when there are IDX_MIN or more of them and a scan below that. Both give the
    same keys; the index does far less work on a big library."""
    expect = ctx.expect
    ascii_fold = lambda s: ''.join(c.lower() if c.isascii() else c for c in s)
    def keys(m, n):   # cf.keys: the word of cf that holds an n-key calloc (no struct offset assumed); cf.order (the Title order's rows) is an n-word block too, made after the keys
        made = [c[2] for c in m.calls if c[0] == 'calloc' and c[1] == 4 * n and c[2]]
        at = sorted({m.word(PSYMS['cf'] + o) for o in range(0, 512, 4) if m.word(PSYMS['cf'] + o) in made}, key=made.index)
        return [m.word(at[0] + 4 * i) for i in range(n)] if at else None
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
    if PERF: expect(INDEX_COST[(1000, 200)] < 1500000 and m.icount > 5000000,
           f'200 albums over 1000: {INDEX_COST[(1000, 200)]:,} payload instructions with the index, {m.icount:,} with the scan (10.2 M before the index existed; the index run includes the Title sort of the 200 albums)')


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
        title = m.widgets['label_title']
        expect(('window_open', 'm1plus_artists') in calls and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [cls] and 'stock_resume' not in m.names(),
               f'{label}: our Artists page lists class {cls:#x}')
        expect(shown(m) == list(names),
               f'{label}: the rows are the stock list in its own order, unsorted ({shown(m)})')
        expect(('widget_set_text_utf8', title, label) in calls and not any(c[0] == 'widget_set_text_utf8' and c[1] == title and c[2] in ('Artists', 'Album Artists') for c in calls),
               f'{label}: the title is the menu row\'s text')
        np = m.widgets['btn_backtoplayer']
        expect((np, 'style:normal:icon') not in m.props, f'{label}: Now Playing keeps the capsule\'s right cap beside the "..."')
        card_texts(m)
        m.click('btn_more')
        expect([vis(m, f'vs_item{i}') for i in range(7)] == [(1, 1)] + [(0, 0)] * 6 and vis(m, 'vs_card') == (1, 1) and vis(m, 'vs_hair')[0] == 0,
               f'{label}: the card has the Name row alone (no Search: no search scope; no Show group), the hairline under Search hidden')
        expect([c[2:] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['vs_card']][-1][1] == 48
               and all(m.props.get((m.widgets['vs_card'], f'style:{st}:bg_image')) == 'vs_glass1' for st in ('normal', 'pressed', 'over'))
               and all(m.props.get((m.widgets['vs_item0'], f'style:{st}:border_width')) == 0 for st in ('normal', 'pressed', 'over')),
               f'{label}: a 48 px card in its one-row glass, no stray hairline above the row')
        said = [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['vs_sub0']]
        expect(vis(m, 'vs_tick0')[0] == 1 and vis(m, 'vs_sub0')[0] == 1 and said and said[-1] == 'A–Z', f'{label}: Name is ticked, A–Z under it')
        root = asset_tree(asset)
        expect(stock_target(m, root, O['NAV_VIEW_X'] + 20, 25)[-1] == 'btn_more' and stock_target(m, root, 290, 25)[-1] == 'btn_backtoplayer' and stock_target(m, root, 40, 25)[-1] == 'btn_return', f'{label}: Back, the "..." and Now Playing are hit')
        at = m.word(pod.DATA['ARTIST_TYPE'][0])
        m.calls = []
        m.click('vs_item4', count=20000000)
        expect(m.word(pod.DATA['ARTIST_TYPE'][0]) == at and not [c for c in m.calls if c[0] in ('write_int_config', 'loadLocalClassList')],
               f'{label}: a stray click on a hidden Show row changes no setting and queries nothing')
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

    # Artists itself: sorted, the "..." card with Search Artists, the Show group and Name, and the title Artists
    m = artists_machine(); m.call(on_row, a0=rows0 + 12 * row['Artists'], count=20000000)
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Artists') in m.calls and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ARTISTS']], 'the Artists row: the title is Artists, class 0xf004')
    expect((m.widgets['btn_backtoplayer'], 'style:normal:icon') not in m.props, 'and Now Playing keeps the capsule\'s right cap')
    card_texts(m)
    m.click('btn_more')
    expect([vis(m, f'vs_item{i}') for i in (0, 4, 5, 6)] == [(1, 1)] * 4 and [vis(m, f'vs_item{i}') for i in (1, 2, 3)] == [(0, 0)] * 3 and vis(m, 'vs_hair') == (1, 1),
           'the Artists card has Search Artists, Artists, Album Artists and Name, with the hairline under Search')
    moves = {i: [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'vs_item{i}']][-1] for i in (6, 4, 5, 0)}
    expect(moves == {6: (0, 0), 4: (0, 48), 5: (0, 96), 0: (0, 144)} and [c[2:] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['vs_card']][-1][1] == 192
           and all(m.props.get((m.widgets['vs_card'], f'style:{st}:bg_image')) == 'vs_glass4' for st in ('normal', 'pressed', 'over'))
           and (m.widgets['vs_item0'], 'style:normal:border_width') not in m.props, f'the rows are packed Search, Artists, Album Artists, Name; a 192 px card in the four-row glass; the hairline above Name stays ({moves})')
    m.calls = []
    m.click('vs_item6', count=40000000)
    expect(('window_open', 'm1plus_search') in m.calls and vis(m, 'vs_card') == (0, 0), 'Search Artists closes the card and opens the Search page')

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
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Bach') in m.calls and ('widget_set_text_utf8', m.widgets['label_album'], 'Cello Suites') in m.calls,
           'titled with the composer, centred on his first album')
    put_value(m, 2); m.call(PSYMS['on_changed'], count=2000000)
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'All albums') in m.calls and ('widget_set_text_utf8', m.widgets['label_artist'], 'Bach') in m.calls,
           'two albums: the All albums card over the composer')
    m.calls = []
    m.click('btn_songs', count=900000000)
    npw = m.widgets['btn_backtoplayer']
    lad = [c[:2] for c in m.calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList')]
    expect(m.props.get((m.widgets['btn_songs'], 'visible')) == 1 and m.props.get((npw, 'style:normal:icon')) == 'ah_nav_play'
           and lad[:2] == [('loadAlbumList', O['CLASS_COMPOSERS']), ('loadAlbumdetailList', O['CLASS_COMPOSER_ALBUMS'])]
           and ('window_open', 'm1plus_songs') in m.calls and m.word(CI) == O['CLASS_14'],
           f'a composer\'s page has the Songs button too (Now Playing its right cap): our Songs page on the composer\'s songs (0xf005, then 0xff02 on the All songs row: class 0xff14) ({lad})')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m.calls = []
    m.tap(O['CF_CX'], count=900000000)
    expect(('window_open', 'm1plus_songs') in m.calls and not any(c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page' for c in m.calls),
           'the card: our Songs page on the composer\'s songs, as an artist\'s card')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m.windows['m1plus_songs'] = 0   # our page will not open: the stock page on the All songs row
    m.calls = []
    m.tap(O['CF_CX'])
    order = [c[0] for c in m.calls if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context')][-3:]
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(order == ['loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context'] and la[-1][1] == O['CLASS_COMPOSERS'] and la[-1][3] == 'Bach'
           and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS'], 2) in m.calls,
           'the card when our page will not open: the composer into the browsing record again, then albuminfo_page with class 0xff02 and the card row')
    cls, rowi, shown_list = m.opened_album
    expect(m.word(m.deques[shown_list][rowi] + O['REC_ID']) == O['ID_ALL_SONGS'] & 0xffffffff, 'that row is the stock All songs row')
    put_value(m, 1); m.call(PSYMS['on_changed'], count=2000000)
    m.tap(O['CF_CX'])
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS'], 1) in m.calls
           and m.read_cstr(m.word(m.deques[m.opened_album[2]][1] + O['REC_ALBUM'])) == 'Goldberg Variations', 'a centre album opens as the stock composer page opens it (class 0xff02, its row)')
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
    def block(m): return O['AL_HEAD_END'] - (O['PH_SHIFT'] if getattr(m, 'nocirc', False) else 0) + (0 if m.fs.get('/mnt/data/m1plus/albums-view') == b'1\n' else RGAP)   # the name and pills block above the rows (a list's first row is RGAP under it; the grid's gap is its own); nocirc: the header without the circle

    def content(m): return [c[3] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1] - block(m)   # (the rows' height: the block above them is not counted)
    def tap(m, x, y):
        sv_y = SCREEN_Y0 + block(m)
        m.touch('down', x, sv_y + y, 1000, fn='al_on_down'); calls = list(m.calls)
        m.touch('up', x, sv_y + y, 1080, fn='al_on_up', count=40000000); m.calls = calls + m.calls
    def opened(artists=('Miles Davis', 'Nina Simone', 'Unknown Artist'), composers=(), view=b'0\n', i=0, home=0, files=None):
        m = artists_machine(artists=artists, composers=composers, albums_page=True)
        if files: m.fs.update(files)
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
    expect(m.props.get((m.widgets['sg_rail'], 'visible')) == 0 and m.props.get((m.widgets['sg_rail'], 'sensitive')) == 0 and not [f for f in m.fills if f[0] == O['SG_HDR_BG']],
           'the artist\'s own list has no sections and no rail (the Index Rail switch is on here: the rail of the Artists page behind it is hidden)')
    expect(('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.calls, 'the title is the artist')
    expect(m.fs['/mnt/data/m1plus/albums-view'] == b'0\n' and m.props.get((m.widgets['vs_tick5'], 'visible')) == 1,
           'the list mode saved for Albums is the mode used, the "..." card ticks List')
    # the covers are the library's files (Jazz Hits is filed under Various Artists there)
    loads = []
    for _ in range(12):
        m.call(PSYMS['al_on_load'], count=40000000); loads += [c[1] for c in m.calls if c[0] == 'widget_load_image' and c[1].startswith('file://') and AP_DIR not in c[1]]
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in m.calls): break
    jazz = 'file://' + art_file(fnv(fnv(O['FNV_SEED'], 'Various Artists'), 'Jazz Hits'))
    expect(jazz in loads and len(set(loads)) == 3, f'the covers take the library album\'s cache keys ({loads})')
    # a tap on the second row opens the artist's album page (class 0xff01)
    m.calls = []
    tap(m, 100, ROWH + 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 1) in m.calls
           and [c for c in m.calls if c[0] == 'loadAlbumList'][-1][3] == 'Miles Davis', 'a tap on an album opens its page as the artist\'s album (0xff01, its row)')
    # the page's order (its "..." card, albums-sort; the stock order here, Title, unless the file says another): the Artist order sorts the artist's albums by title and keeps the All Songs row last;
    # a tap still opens the stock row, and the covers are still the library albums' (the keys follow the stock row, not the position)
    ms = opened(files={'/mnt/data/m1plus/albums-sort': b'1\n'})
    ms.calls = []
    tap(ms, 100, 10)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 0) in ms.calls, 'the saved Artist order is Title on one artist\'s page (the stock order): the first row is stock row 0')
    ms.calls = []
    tap(ms, 100, 3 * ROWH + 10)
    expect(not [c for c in ms.calls if c[:2] == ('navigator_to_with_context', 'albuminfo_page') and c[3] < 3], 'the All Songs row stays last: the fourth row opens none of the three albums')
    ms.calls = []
    loads = []
    for _ in range(12):
        ms.call(PSYMS['al_on_load'], count=40000000); loads += [c[1] for c in ms.calls if c[0] == 'widget_load_image' and c[1].startswith('file://') and AP_DIR not in c[1]]
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in ms.calls): break
    jazz = 'file://' + art_file(fnv(fnv(O['FNV_SEED'], 'Various Artists'), 'Jazz Hits'))
    expect(jazz in loads and len(set(loads)) == 3, f'the covers still take the library albums\' keys under the sorted order ({loads})')
    # the toggle persists in the shared file and keeps the artist's albums
    m.calls = []
    view_switch(m, 40000000)
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
    grid = lambda m: m.props.get((m.widgets['vs_tick4'], 'visible')) == 1
    m2 = opened(view=b'1\n', i=1)
    expect(grid(m2) and content(m2) == RGAP + CELL_PITCH, 'an artist tap opens the grid when the grid was chosen last')
    m3 = artists_machine(albums_page=True); m3.fs.update(m.fs); m3.call(PSYMS['albums_open'], count=20000000)
    expect(grid(m3), 'Home > Albums opens in the mode chosen on the artist page')
    view_switch(m3, 40000000)
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
    m.setword(m.sv + SC_YOFF, 200)   # (the rows start under the photo header and the pills)
    m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
    tx = [t for t, r in m.texts]
    expect(tx == ['Bitches Brew', 'Jazz Hits', 'Kind of Blue', 'All Songs'], f'the fourth row is All Songs, with no line under it (an artist\'s albums show their years) ({tx})')
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
    m.nocirc = True   # (a composer's page has the artist header without the circle: a composer has no photo)
    la = [c for c in m.calls if c[0] == 'loadAlbumList']
    expect(('window_open', 'm1plus_albums') in m.calls and la and la[0][1] == O['CLASS_COMPOSERS'] and la[0][3] == 'Bach'
           and ('widget_set_text_utf8', m.widgets['label_title'], 'Bach') in m.calls and content(m) == 3 * ROWH, 'a composer: his two albums and the All Songs row on the Albums page')
    m.calls = []
    tap(m, 100, 10)
    expect(any(c[:3] == ('navigator_to_with_context', 'albuminfo_page', O['CLASS_COMPOSER_ALBUMS']) for c in m.calls), 'and his album page opens as a composer\'s (0xff02)')
    m.calls = []
    tap(m, 100, 2 * ROWH + 10)
    lad = [c[:2] for c in m.calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList')]
    expect(('window_open', 'm1plus_songs') in m.calls and lad[-1:] == [('loadAlbumdetailList', O['CLASS_COMPOSER_ALBUMS'])]
           and not any(c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page' for c in m.calls) and m.word(pod.DATA['CLASSINFO'][0]) == O['CLASS_14'],
           f'a composer\'s All Songs row opens our Songs page on the composer\'s songs (class 0xff14), as Cover Flow\'s card ({lad})')

    # a window that will not open: Cover Flow on the artist, as before
    m = artists_machine(); m.call(open_, count=5000000); m.calls = []
    m.call(PSYMS['ar_open'], a0=0, count=8000000)
    expect(('window_open', 'm1plus_albums') in m.calls and ('window_open', 'm1plus_cover') in m.calls, 'the Albums window will not open: Cover Flow on the artist')




SORT_FILE = '/mnt/data/m1plus/albums-sort'
# Miles Davis's albums in the stock order (by title, which is also our Title order): Bitches Brew (0), Jazz Hits (1), Kind of Blue (2); the library songs, newest first, with their years
SCOPED_SONGS = [('Bitches Brew', 1970), ('Kind of Blue', 1959), ('Jazz Hits', 1990)]
SCOPED_ORDERS = {0: [0, 1, 2], 1: [0, 1, 2],   # Title; the saved Artist is Title here
                 2: [0, 2, 1],                  # Recently Added: Bitches Brew, Kind of Blue, Jazz Hits
                 3: [1, 0, 2]}                  # Year, newest first: Jazz Hits 1990, Bitches Brew 1970, Kind of Blue 1959
SCOPED_REV = {0: [2, 1, 0], 1: [2, 1, 0],       # Z-A (the saved Artist's letter b is Title, Z-A here)
              2: [1, 2, 0],                     # Oldest First, by newest song: Jazz Hits, Kind of Blue, Bitches Brew
              3: [2, 0, 1]}                     # Oldest First: Kind of Blue 1959, Bitches Brew 1970, Jazz Hits 1990


def scoped_machine(sort=None, albums_page=True, view=b'0\n'):
    m = artists_machine(albums_page=albums_page)
    rows = []
    for i, (album, year) in enumerate(SCOPED_SONGS):
        r = m.record(album=album, artist='x', path=f'/mnt/mmc/s/{i}.flac', rid=700 + i)
        m.setword(r + O['REC_YEAR'], year); rows.append(r)
    m.class_lists[O['CLASS_ALL_SONGS']] = rows
    m.fs['/mnt/data/m1plus/albums-view'] = view
    m.fs.pop(SORT_FILE, None)   # (the default, Artist, unless the test gives one)
    if sort is not None: m.fs[SORT_FILE] = sort
    if albums_page:
        for i, t in enumerate(('Title', 'Artist', 'Recently Added', 'Year', 'Grid', 'List', 'Search Albums')): m.wtext[m.widgets[f'vs_label{i}']] = t
        for i in range(4): m.wtext[m.widgets[f'vs_sub{i}']] = 'A–Z'
    m.measure = lambda t: 60   # (the card is fitted: 180 px)
    m.call(PSYMS['artists_open'], a0=0, count=20000000)
    forget_card(m)   # (the machine's widgets are shared by both pages: the Artists page's bind hid rows of the card the Albums page finds whole in its own window)
    m.calls = []
    return m


def scoped_sort_tests(ctx):
    """One album order for every album list (docs/modules/albums.md): the artist's page offers Title, Recently Added and Year (no Artist row, a 200 px card), shows the saved Artist
    order as Title, writes the shared albums-sort; the artist's Cover Flow follows the same order."""
    expect = ctx.expect
    ROWH = O['LIST_ROW_H']
    TOP_ROWS = O['AL_HEAD_END'] + O['GRID_ROW_GAP']   # the list's first row (the photo header and the pills above it)
    vis = lambda m, n: (m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1))
    def tap(m, y):
        m.calls = []
        m.touch('down', 100, 80 + TOP_ROWS + y, 1000, fn='al_on_down')
        m.touch('up', 100, 80 + TOP_ROWS + y, 1080, fn='al_on_up', count=40000000)
        return [c[3] for c in m.calls if c[:2] == ('navigator_to_with_context', 'albuminfo_page')]
    # the card: Grid, List and three sort rows, packed, 240 px, the five-row glass; no Search row (it searched every album, not the artist's); hidden rows are insensitive; the names are all there
    m = scoped_machine(); m.call(PSYMS['ar_open'], a0=0, count=40000000)
    m.click('btn_more')
    expect(vis(m, 'vs_item1') == (0, 0) and vis(m, 'vs_item6') == (0, 0), 'the scoped card has no Artist row and no Search row: hidden and insensitive')
    expect(all(vis(m, f'vs_item{i}') == (1, 1) for i in (0, 2, 3, 4, 5)) and vis(m, 'vs_card') == (1, 1), 'Grid, List, Title, Recently Added and Year are shown')
    moves = {i: [c[2:] for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'vs_item{i}']] for i in (0, 2, 3, 4, 5)}
    expect(moves == {4: [(0, 0)], 5: [(0, 48)], 0: [(0, 96)], 2: [(0, 144)], 3: [(0, 192)]}, f'the rows are packed from the top, Grid and List first ({moves})')
    expect(vis(m, 'vs_hair')[0] == 0, 'no hairline over Grid (nothing above it)')
    expect(all(m.props.get((m.widgets['vs_card'], f'style:{st}:bg_image')) == 'vs_glass5' for st in ('normal', 'pressed', 'over')), 'the card is drawn in the 240 px, five-row glass')
    expect([c[2:] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets['vs_card']][-1][1] == 240, 'the card is 240 px high')
    expect([vis(m, f'vs_tick{i}')[0] for i in range(4)] == [1, 0, 0, 0], 'the saved Artist (the default) shows as Title: Title is ticked')
    # the library page keeps four sorts, the 336 px card and the asset's own seven-row glass
    ml = scoped_machine(); ml.call(PSYMS['albums_open'], count=20000000); ml.calls = []; ml.click('btn_more')
    expect(all(vis(ml, f'vs_item{i}') == (1, 1) for i in range(7)) and [c[2:] for c in ml.calls if c[0] == 'widget_resize' and c[1] == ml.widgets['vs_card']][-1][1] == 336
           and ml.props.get((ml.widgets['vs_card'], 'style:normal:bg_image')) == 'vs_glass7', 'the library page keeps its seven rows on the 336 px card, in the seven-row glass')
    # each saved order on the scoped page: the list, the tick, the stock row a tap opens
    for k, order in SCOPED_ORDERS.items():
        m = scoped_machine(f'{k}\n'.encode()); m.call(PSYMS['ar_open'], a0=0, count=40000000)
        got = [tap(m, r * ROWH + 10) for r in range(3)]
        expect(got == [[o] for o in order], f'albums-sort {k}: the artist\'s rows open stock rows {order} ({got})')
        m.click('btn_more')
        tk = 0 if k == 1 else k
        expect([vis(m, f'vs_tick{i}')[0] for i in range(4)] == [int(i == tk) for i in range(4)], f'albums-sort {k}: the tick is on row {tk}')
    # a row writes the shared file and re-sorts; the library page then reads it
    m = scoped_machine(); m.call(PSYMS['ar_open'], a0=0, count=40000000)
    m.calls = []; m.click('btn_more'); m.click('vs_item3')
    expect(m.fs.get(SORT_FILE) == b'3\n' and ('rename', SORT_FILE + '.tmp', SORT_FILE) in m.calls, 'Year on the artist page writes albums-sort, atomically')
    got = [tap(m, r * ROWH + 10) for r in range(3)]
    expect(got == [[o] for o in SCOPED_ORDERS[3]], f'and the list is in the Year order ({got})')
    m.calls = []; m.click('btn_more'); m.click('vs_item0')
    expect(m.fs.get(SORT_FILE) == b'0\n', 'Title writes 0 once another order is saved')
    # Title is ticked when Artist is saved: a tap on it is the tap on the ticked row, so it reverses the shown Title order (saved as Title, Z-A)
    m = scoped_machine(); m.call(PSYMS['ar_open'], a0=0, count=40000000)
    m.calls = []; m.click('btn_more'); m.click('vs_item0')
    expect(m.fs.get(SORT_FILE) == b'a\n', 'the ticked Title row flips the direction: albums-sort is Title, Z-A')
    got = [tap(m, r * ROWH + 10) for r in range(4)]
    expect(got == [[2], [1], [0], []], f'the artist\'s rows are reversed and the All Songs row stays last ({got})')
    # reversed orders: the second line, the order, the All Songs row last, the library page and the artist's Cover Flow follow
    for k, order in SCOPED_REV.items():
        data = chr(ord('a') + k).encode() + b'\n'
        m = scoped_machine(data); m.call(PSYMS['ar_open'], a0=0, count=40000000)
        got = [tap(m, r * ROWH + 10) for r in range(3)]
        expect(got == [[o] for o in order], f'albums-sort {data!r}: the artist\'s rows open stock rows {order} ({got})')
        m.calls = []; m.click('btn_more')
        tk = 0 if k == 1 else k
        said = {i: [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'vs_sub{i}']] for i in range(4)}
        want = ('Z\u2013A' if tk < 2 else 'Oldest First')
        expect(said[tk] and utf8(said[tk][-1]) == want and vis(m, f'vs_sub{tk}')[0] == 1 and all(vis(m, f'vs_sub{i}')[0] == 0 for i in range(4) if i != tk), f'albums-sort {data!r}: only row {tk} shows "{want}"')
        m.click(f'vs_item{tk}')
        expect(m.fs.get(SORT_FILE) == f'{tk}\n'.encode(), 'a tap on the ticked row flips it back to the default direction')
        expect(tap(m, 3 * ROWH + 10) == [] , 'the All Songs row is still the fourth')   # (it opens the Songs page, which binds the shared "..." name: last)
        ml = scoped_machine(data, albums_page=False); ml.call(PSYMS['ar_open'], a0=0, count=8000000)
        seen = []
        for c in range(3):
            put_value(ml, c); ml.call(PSYMS['on_changed'], count=2000000)
            ml.tap(O['CF_CX'])
            seen += [x[3] for x in ml.calls if x[:2] == ('navigator_to_with_context', 'albuminfo_page')]
        expect(seen == order, f'albums-sort {data!r}: the artist\'s Cover Flow shelf opens stock rows {order} ({seen})')
    m = scoped_machine(b'2\n'); m.call(PSYMS['albums_open'], count=20000000)
    expect(m.fs[SORT_FILE] == b'2\n', 'the library page reads the same file')
    # the artist's Cover Flow: the same order (Artist as Title), the covers keyed by stock row
    for k, order in SCOPED_ORDERS.items():
        m = scoped_machine(f'{k}\n'.encode() if k != 1 else b'1\n', albums_page=False); m.call(PSYMS['ar_open'], a0=0, count=8000000)
        seen = []
        for c in range(3):
            put_value(m, c); m.call(PSYMS['on_changed'], count=2000000)
            m.tap(O['CF_CX'])
            seen += [x[3] for x in m.calls if x[:2] == ('navigator_to_with_context', 'albuminfo_page')]
        expect(seen == order, f'albums-sort {k}: the artist\'s Cover Flow shelf opens stock rows {order} ({seen})')


# Miles Davis's songs as the stock artist query lists them (class 0xff11): the albums' tracks with their year tags. Kind of Blue: 1962, 1959 and no tag (earliest wins);
# Bitches Brew 1970; Jazz Hits has no usable year (999 and 3000 are out of the 1000..2999 range); a song of an album the page does not list is ignored.
PAGE_SONGS = [('Kind of Blue', 1962), ('Kind of Blue', 1959), ('Kind of Blue', 0), ('Bitches Brew', 1970), ('Jazz Hits', 999), ('Jazz Hits', 3000), ('Other Album', 1980)]


def pills_machine(view=b'0\n', sort=None, home=0, i=0, songs=True):
    m = artists_machine(albums_page=True)
    recs = []
    for n, (album, year) in enumerate(PAGE_SONGS):
        path = f'/mnt/mmc/Miles Davis/{album}/{n}.flac'
        r = m.record(album=album, artist='Miles Davis', path=path, rid=800 + n)
        m.setword(r + O['REC_YEAR'], year); m.present.add(path); recs.append(r)
    if songs: m.artist_songs['Miles Davis'] = recs
    m.tracklist = recs
    m.fs['/mnt/data/m1plus/albums-view'] = view
    if sort is not None: m.fs['/mnt/data/m1plus/albums-sort'] = sort
    for n, t in (('btn_play', 'Play'), ('btn_shuffle', 'Shuffle')): m.wtext[m.widgets[n]] = t
    m.call(PSYMS['artists_open'], a0=home, count=20000000)
    m.calls = []
    m.call(PSYMS['ar_open'], a0=i, count=40000000)
    m.open_calls = list(m.calls)
    return m


def scoped_pills_tests(ctx):
    """An artist's albums page (docs/modules/albums.md "Artist page"): Play and Shuffle pills under the large title, the albums' years as their grey line."""
    expect = ctx.expect
    ROWH, RGAP, END = O['LIST_ROW_H'], O['GRID_ROW_GAP'], O['AL_HEAD_END']
    PITCH = O['GRID_COVER'] + O['GRID_TITLE_GAP'] + O['GRID_TITLE_H'] + O['GRID_SUB_H'] + RGAP
    expect(O['AL_PILLS_END'] == O['SG_PILL_Y'] + O['SG_PILL_H'] and END == O['AL_HEAD_PILL_Y'] + O['SG_PILL_H'] and O['AL_PLAY_W'] == 145 and O['AL_SHUFFLE_W'] == 145 and O['AL_PLAY_X'] == 10 and O['AL_SHUFFLE_X'] == 165 and O['AL_SHUFFLE_X'] - (O['AL_PLAY_X'] + O['AL_PLAY_W']) == 10, 'the pill block ends where the Songs page\'s pills do (52 + 40) and, under the photo header, 148 + 40; the page\'s Play and Shuffle pills are 145 wide, Play at x 10 and Shuffle at x 165 (a 10 px gap)')
    # the asset: two hidden pills in the content view after the large title, the Songs page's look; Play 145 wide at x 10, Shuffle 145 wide at x 165
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin'), 'rb').read())
    grid = tree.find('view_grid')
    kids = {c.name: c for c in grid.children}
    expect(list(kids) == ['al_title', 'btn_play', 'btn_shuffle', 'al_name'], f'the content view holds the large title, the two pills and the header\'s name ({list(kids)})')
    for nm, x, w, icon in (('btn_play', 10, 145, 'sg_play'), ('btn_shuffle', 165, 145, 'sg_shuffle')):
        b = kids[nm]
        expect((b.x, b.y, b.w, b.h) == (x, O['SG_PILL_Y'], w, O['SG_PILL_H']) and b.type == 'button' and b.get('visible') == 'false' and b.get('sensitive') == 'false'
               and b.get('style:normal:bg_color') == '#1E1E1E' and b.get('style:pressed:bg_color') == '#333335' and b.get('style:normal:round_radius') == '20'
               and b.get('style:normal:icon') == icon and b.get('style:normal:font_size') == '18', f'{nm}: the Songs page\'s flat pill ({w} x 40 at x {x}), hidden and insensitive until the payload shows it')

    # the library Albums page has none
    m = artists_machine(albums_page=True); m.fs['/mnt/data/m1plus/albums-view'] = b'0\n'; m.call(PSYMS['albums_open'], count=20000000)
    expect(all(m.props.get((m.widgets[n], 'visible'), 0) != 1 for n in ('btn_play', 'btn_shuffle')) and m.props.get((m.widgets['btn_play'], 'sensitive'), 0) != 1,
           'the library Albums page keeps the pills hidden')
    expect(('widget_set_text_utf8', m.widgets['al_title'], 'Albums') in m.calls, 'and its title is Albums')

    for mode, view in (('list', b'0\n'), ('grid', b'1\n')):
        m = pills_machine(view)
        top = END + RGAP   # list rows right under the block's gap; the grid's first gap is the same RGAP
        for nm in ('btn_play', 'btn_shuffle'):
            w = m.widgets[nm]
            expect(m.props.get((w, 'visible')) == 1 and m.props.get((w, 'sensitive')) == 1 and (w, O['EVT_CLICK']) in m.bound, f'{mode}: {nm} is shown, sensitive and bound')
        expect(('widget_set_text_utf8', m.widgets['al_title'], 'Miles Davis') in m.calls, f'{mode}: the large title is the artist')
        h = [c[3] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1]
        want = (top + 4 * ROWH) if mode == 'list' else (END + RGAP + 2 * PITCH)
        expect(h == want, f'{mode}: the content is the title block, the pills and the albums ({h}, want {want})')
    # years: the grey line, as the Year order reads them (earliest tag 1000..2999 of the album's songs), empty without one; the All Songs row has none
    for mode, view in (('list', b'0\n'), ('grid', b'1\n')):
        m = pills_machine(view)
        m.strings = {'local_allsong': 'All Songs'}
        m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
        ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
        m.setword(m.canvas + O['CANVAS_OY'], SCREEN_Y0 & 0xffffffff)
        m.texts.clear(); m.blits.clear()
        m.setword(m.sv + SC_YOFF, 200)   # (the rows start under the photo header and the pills: scrolled so the whole list is in the window)
        m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
        tx = [t for t, r in m.texts]
        expect(tx[:4] == ['Bitches Brew', 'Jazz Hits', 'Kind of Blue', 'All Songs'], f'{mode}: titles ({tx})')
        expect(tx[4:] == ['1970', '1959'], f'{mode}: Bitches Brew 1970, Kind of Blue 1959 (the earliest tag), Jazz Hits and All Songs empty ({tx})')
    # one read of the artist's songs; none for the sorts that need no years beyond it
    qs = [c for c in m.open_calls if c[0] == 'loadAlbumdetailList']
    expect(len(qs) == 1 and qs[0][1] == O['CLASS_ARTIST_ALBUMS'], f'one read of the artist\'s songs on open ({qs})')
    expect(not [c for c in m.open_calls if c[0] == 'loadLocalClassList' and c[1] == O['CLASS_ALL_SONGS']], 'no scan of the library')
    # no songs read: no years, the page still opens
    m = pills_machine(b'0\n', songs=False)
    expect(m.props.get((m.widgets['btn_play'], 'visible')) == 1, 'an artist query that gives no songs still opens the page with its pills')

    # Play: the artist's songs in order from the first; Shuffle: the stock Shuffle mode from a random one
    m = pills_machine(); m.mode = 2
    m.calls = []
    m.click('btn_play', count=900000000)
    calls = list(m.calls)
    ls = [c for c in calls if c[0] == 'loadAlbumdetailList']
    expect(m.played and m.played[1] == 0 and m.played[0] == m.tracklist and m.mode == 0 and [c[3] for c in calls if c[0] == 'loadSongList'] == [O['CLASS_ARTIST_SONGS']]
           and ls, 'Play: every song of the artist in order from the first (class 0xff11), Shuffle mode off')
    m = pills_machine(); m.mode = 0
    m.calls = []
    m.click('btn_shuffle', count=900000000)
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(('mclSetPlayMode', 2) in m.calls and nav and m.played[0] == m.tracklist and 0 <= m.played[1] < len(m.tracklist), 'Shuffle: the same list in the stock Shuffle mode from a random song')
    expect(not [c for c in m.calls if c[0] == 'loadLocalClassList' and c[1] == O['CLASS_ALL_SONGS']], 'Shuffle reads no library list')

    # taps: the first row is at the pill block's end, a tap on the pill block plays/opens no album
    m = pills_machine(b'0\n')
    for y, want in ((END + RGAP - 3, False), (END + RGAP + 5, True)):
        m.calls = []
        m.touch('down', 100, SCREEN_Y0 + y, 1000, fn='al_on_down'); m.touch('up', 100, SCREEN_Y0 + y, 1080, fn='al_on_up', count=40000000)
        expect(bool([c for c in m.calls if c[:2] == ('navigator_to_with_context', 'albuminfo_page')]) == want, f'list: a tap at content y {y} {"opens the first album" if want else "opens nothing"}')
    # the small title appears once the name has scrolled away (AL_HEAD_COLLAPSE: the name's box bottom, as the playlist header's)
    m = pills_machine(b'0\n')
    small = m.widgets['label_title']
    m.setword(m.sv + O['SC_YOFF'], O['AL_HEAD_COLLAPSE'] - 1); m.call(PSYMS['al_on_scroll'], count=4000000)
    expect(m.props.get((small, 'visible'), 0) == 0, 'one px short of AL_HEAD_COLLAPSE the small title is hidden')
    m.setword(m.sv + O['SC_YOFF'], O['AL_HEAD_COLLAPSE']); m.call(PSYMS['al_on_scroll'], count=4000000)
    expect(m.props.get((small, 'visible')) == 1, 'at AL_HEAD_COLLAPSE (132) it shows')

    # a composer's page: the same pills and years, the composer's songs through the stock composer queries (0xf005, then 0xff02 on the All songs row: class 0xff14)
    def composer_machine():
        m = artists_machine(composers=('Mozart', 'Bach', 'Unknown Composer'), albums_page=True)
        recs = []
        for n, (album, year) in enumerate((('Cello Suites', 1720), ('Goldberg Variations', 1741), ('Goldberg Variations', 0))):
            r = m.record(album=album, artist='Glenn Gould', path=f'/mnt/mmc/Bach/{album}/{n}.flac', rid=900 + n)
            m.setword(r + O['REC_YEAR'], year); m.present.add(f'/mnt/mmc/Bach/{album}/{n}.flac'); recs.append(r)
        m.composer_songs['Bach'] = recs; m.tracklist = recs
        m.fs['/mnt/data/m1plus/albums-view'] = b'0\n'
        for n, t in (('btn_play', 'Play'), ('btn_shuffle', 'Shuffle')): m.wtext[m.widgets[n]] = t
        m.call(PSYMS['artists_open'], a0=pod_pages.HOME_COMPOSER, count=20000000); m.calls = []
        m.call(PSYMS['ar_open'], a0=1, count=40000000); m.open_calls = list(m.calls)
        return m
    m = composer_machine()
    qs = [c for c in m.open_calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList')]
    expect(all(m.props.get((m.widgets[n], 'visible')) == 1 and m.props.get((m.widgets[n], 'sensitive')) == 1 for n in ('btn_play', 'btn_shuffle'))
           and [c[:2] for c in qs][-2:] == [('loadAlbumList', O['CLASS_COMPOSERS']), ('loadAlbumdetailList', O['CLASS_COMPOSER_ALBUMS'])],
           f'a composer\'s page has the pills and reads the composer\'s songs once ({[c[:2] for c in qs]})')
    m.strings = {'local_allsong': 'All Songs'}
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], SCREEN_Y0 & 0xffffffff)
    m.texts.clear(); m.blits.clear()
    m.setword(m.sv + SC_YOFF, 0)   # (the header without the circle is short: the three rows are in view)
    m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
    tx = [t for t, r in m.texts]
    expect(tx == ['Cello Suites', 'Goldberg Variations', 'All Songs', '1720', '1741'], f'a composer\'s albums show their years; All Songs has no line (not the composer\'s name) ({tx})')
    m.calls = []
    m.click('btn_play', count=900000000)
    expect(m.played and m.played[1] == 0 and [c[3] for c in m.calls if c[0] == 'loadSongList'] == [O['CLASS_14']],
           'Play on a composer\'s page: every song of the composer from the first, class 0xff14 (what the stock All songs row leaves)')
    m = composer_machine(); m.calls = []
    m.click('btn_shuffle', count=900000000)
    expect(m.played and [c[3] for c in m.calls if c[0] == 'loadSongList'] == [O['CLASS_14']], 'Shuffle on a composer\'s page plays the composer\'s songs (0xff14)')


def name_order_tests(ctx):
    """The Name order of the "..." card (docs/modules/artists.md): A-Z is today's order, Z-A its mirror (sections and rail Z..A, "#" last, the Unknown row still last), tapping the ticked row
    reverses and saves per page (artists-sort, genres-sort, composers-sort: "a" Z-A, anything else A-Z), a save that fails changes nothing."""
    expect = ctx.expect
    open_ = PSYMS['artists_open']
    D = '/mnt/data/m1plus/'
    stock = ['the Beatles', 'Zed', 'Abba', 'Miles Davis', '2 Pac', 'Unknown Artist']
    def letters(m): return [l for _, l in sorted(headers(m).items())]
    def rail_on(m): return m.props.get((m.rail, 'visible')) != 0 and m.props.get((m.rail, 'sensitive')) != 0
    def sub(m): return [utf8(c[2]) for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['vs_sub0']]
    # no file, and files that are not "a": A-Z; "a": Z-A with the Unknown row still last
    for data, rev in ((None, False), (b'0\n', False), (b'x\n', False), (b'1\n', False), (b'a\n', True), (b'a', True)):
        m = artists_machine(stock)
        if data is not None: m.fs[D + 'artists-sort'] = data
        m.call(open_, count=20000000)
        want = ['Zed', 'Miles Davis', 'the Beatles', 'Abba', '2 Pac', 'Unknown Artist'] if rev else ['2 Pac', 'Abba', 'the Beatles', 'Miles Davis', 'Zed', 'Unknown Artist']
        expect(shown(m) == want, f'artists-sort {data!r}: {want}')
        expect(letters(m) == (['Z', 'M', 'B', 'A', '#'] if rev else ['#', 'A', 'B', 'M', 'Z']) and rail_on(m), f'artists-sort {data!r}: the sections run {"Z to A, # last" if rev else "# then A to Z"}, the rail is there')
        card_texts(m); m.click('btn_more')
        expect(vis(m, 'vs_tick0')[0] == 1 and (sub(m) or [''])[-1] == ('Z–A' if rev else 'A–Z'), f'artists-sort {data!r}: Name is ticked with {"Z–A" if rev else "A–Z"} under it')
        if rev:   # a tap opens the artist shown there
            m.click('btn_more')
            m.calls = []
            artists_tap(m, 0, starts=[s for s, _ in Model(['Zed', 'Miles Davis', 'the Beatles', 'Abba', '2 Pac', 'Unknown Artist']).secs])
            la = [c for c in m.calls if c[0] == 'loadAlbumList']
            expect(la and la[0][3] == 'Zed', f'Z-A: a tap on the first row opens Zed ({la[:1]})')
    # a tap on the ticked Name row reverses and saves, atomically; again, back to A-Z; the scroll goes to the top and the stock query runs again
    m = artists_machine(stock); m.call(open_, count=20000000); card_texts(m)
    scroll_to(m, 100)
    m.calls = []
    m.click('btn_more'); m.click('vs_item0', count=20000000)
    calls = list(m.calls)
    expect(m.fs.get(D + 'artists-sort') == b'a\n' and ('rename', D + 'artists-sort.tmp', D + 'artists-sort') in calls, 'the Name row writes artists-sort "a", atomically')
    expect(('widget_set_prop_int', m.sv, 'yoffset', 0) in calls and ('loadLocalClassList', O['CLASS_ARTISTS']) in calls and vis(m, 'vs_card') == (0, 0) and shown(m)[0] == 'Zed', 'the list is Z-A from the top, the card is closed')
    m.calls = []
    m.click('btn_more')
    expect((sub(m) or [''])[-1] == 'Z–A', 'reopened, Z–A is under Name')
    m.click('vs_item0', count=20000000)
    expect(m.fs.get(D + 'artists-sort') == b'0\n' and shown(m)[0] == '2 Pac', 'the second tap writes "0" and the list is A-Z again')
    # the Show group and the order are independent: Album Artists keeps Z-A, the other page's file is not touched
    m = artists_machine(stock); m.fs[D + 'artists-sort'] = b'a\n'; m.call(open_, count=20000000); card_texts(m)
    pick(m, 5)
    expect(shown(m) == ['Various Artists', 'Miles Davis'], 'Album Artists keep the saved Z-A')
    expect(D + 'genres-sort' not in m.fs and D + 'composers-sort' not in m.fs, 'only artists-sort is written')
    # a save that fails: the order, the list and the tick stay
    m = artists_machine(stock); m.call(open_, count=20000000); card_texts(m)
    m.fail.add(('write', D + 'artists-sort.tmp')); m.calls = []
    m.click('btn_more'); m.click('vs_item0', count=20000000)
    reloaded = 'loadLocalClassList' in m.names()
    expect(D + 'artists-sort' not in m.fs and shown(m)[0] == '2 Pac' and not reloaded, 'a save that fails leaves the order and the list as they were')
    # Genres and Composers: stock order is A-Z (the default), Z-A mirrors it with the Unknown row last, each page its own file
    P = pod_pages
    for label, home, cls, fname, names in (('Genres', P.HOME_GENRE, 0xf006, 'genres-sort', ('Rock', 'jazz', '周', 'Unknown Genre')),
                                           ('Composers', P.HOME_COMPOSER, 0xf005, 'composers-sort', ('Mozart', 'Bach', 'The Beatles', 'Unknown Composer'))):
        kw = {'genres': names} if cls == 0xf006 else {'composers': names}
        m = artists_machine(**kw); m.call(open_, a0=home, count=20000000)
        expect(shown(m) == list(names), f'{label}: no file, the stock order')
        m = artists_machine(**kw); m.fs[D + fname] = b'a\n'; m.fs[D + 'artists-sort'] = b'0\n'; m.call(open_, a0=home, count=20000000)
        expect(shown(m) == list(names[:3][::-1]) + [names[3]], f'{label}: {fname} "a" reverses the stock order, the Unknown row stays last ({shown(m)})')
        m = artists_machine(**kw); m.fs[D + 'artists-sort'] = b'a\n'; m.call(open_, a0=home, count=20000000)
        expect(shown(m) == list(names), f'{label}: artists-sort does not touch this page')
        m = artists_machine(**kw); m.call(open_, a0=home, count=20000000); card_texts(m)
        m.click('btn_more'); m.click('vs_item0', count=20000000)
        expect(m.fs.get(D + fname) == b'a\n' and shown(m) == list(names[:3][::-1]) + [names[3]] and (D + 'artists-sort') not in m.fs, f'{label}: the Name row writes {fname} "a" only and reverses the list')
    # Z-A with a large library: the sections never exceed 27 and the other-script names come first, "#" last
    names = ['Zed', 'Abba', '周', 'Привет', '7 Seas', 'Miles', 'Unknown Artist']
    m = artists_machine(names); m.fs[D + 'artists-sort'] = b'a\n'; m.call(open_, count=20000000)
    got = shown(m)
    expect(got[-1] == 'Unknown Artist' and got.index('Zed') < got.index('Miles') < got.index('Abba') < got.index('7 Seas') and len(letters(m)) <= 27, f'Z-A mirrors the order; letters {letters(m)} ({got})')


def scoped_nextalbum_tests(ctx):
    """Continue with Next Album, phase 1 (patch/nextalbum.c): an album tapped on an artist's page notes that artist's albums in the order shown, the scope and a copy of the artist row;
    the All Songs row is not in it."""
    expect = ctx.expect
    NA = sibling('nextalbum')
    ROWH = O['LIST_ROW_H']
    FILE = NA.FILE

    def block(m): return O['AL_HEAD_END'] + 0   # the header and pills block above the list rows (the photo header of the artist's page; the list view: the first row directly under it)

    def tap(m, x, y):
        sv_y = SCREEN_Y0 + block(m)
        m.touch('down', x, sv_y + y, 1000, fn='al_on_down'); calls = list(m.calls)
        m.touch('up', x, sv_y + y, 1080, fn='al_on_up', count=40000000); m.calls = calls + m.calls

    def opened(extra=None, composers=(), home=0, i=0):
        m = NA.snap(artists_machine(composers=composers, albums_page=True))
        m.fs['/mnt/data/m1plus/albums-view'] = b'0\n'
        if extra: m.fs.update(extra)
        m.call(PSYMS['artists_open'], a0=home, count=20000000)
        m.calls = []
        m.call(PSYMS['ar_open'], a0=i, count=40000000)
        return m

    def keys_of(m, artist): return [album_key(m.read_cstr(m.word(r + O['REC_ARTIST'])), m.read_cstr(m.word(r + O['REC_ALBUM']))) for r in m.artist_albums[artist]]

    m = opened({FILE: b'1\n'})
    tap(m, 100, ROWH + 10)
    n = m.noted
    expect(n and n['keys'] == keys_of(m, 'Miles Davis') and n['scope'] == O['CLASS_ARTISTS'] and n['artist'] and len(n['artist_rows']) == 1
           and m.read_cstr(m.word(n['artist_rows'][0] + O['REC_TITLE'])) == 'Miles Davis',
           'an artist\'s page: the three albums in the stock order (the All Songs row is not one), the artist scope and a copy of the artist row')
    expect(NA.state(m)['pending'] is None, 'the note is dropped when cc_open_album returns')
    tap(m, 100, 3 * ROWH + 10)   # the All Songs row: our Songs page, no album
    m2 = opened({FILE: b'1\n'})
    m2.noted = None
    tap(m2, 100, 3 * ROWH + 10)
    expect(m2.noted is None, 'the All Songs row opens the Songs page: nothing is noted')
    # the sorted view: Title on the scoped page is the stock order; reversed it is the reverse of the albums, the card still left out
    ms = opened({FILE: b'1\n', '/mnt/data/m1plus/albums-sort': b'a\n'})
    tap(ms, 100, 10)
    expect(ms.noted and ms.noted['keys'] == keys_of(ms, 'Miles Davis')[::-1], f'Z-A on the artist\'s page: the reversed order ({ms.noted and [hex(k) for k in ms.noted["keys"]]})')
    # setting off: nothing noted
    mo = opened()
    tap(mo, 100, ROWH + 10)
    expect(mo.noted is None, 'setting off: nothing is noted')


AP_DIR = '/mnt/mmc/.m1plus/artists'


def ap_key(name):
    """patch/artistphoto.c ap_key, written again: FNV of the name trimmed, ASCII case folded, without a leading "The "."""
    s = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in name.strip(' \t'))
    if len(s) > 4 and s.startswith('the '): s = s[4:].lstrip(' \t')
    h = fnv(O['FNV_SEED'], s)
    return h or 1


def ap44(name): return f'{AP_DIR}/a{ap_key(name):08x}-44.jpg'


def seed_photos(m, names=('Miles Davis', 'Nina Simone'), color=(40, 40, 40)):
    """The -168 file (a flat picture) of each name: an artist's page with a photo in the cache has the circle header."""
    m.load_image = 0
    for n in names:
        p = f'{AP_DIR}/a{ap_key(n):08x}-168.jpg'
        m.files[p] = 5000; m.present.add(p); m.images['file://' + p] = (168, 168, bytes((*color, 255)) * (168 * 168))


_artists_machine = artists_machine


def artists_machine(*args, photos=True, **kw):
    """The harness's machine; photos: the two artists have a photo in the cache (so their pages open with the circle, as most tests here expect); False: none."""
    m = _artists_machine(*args, **kw)
    if photos: seed_photos(m)
    return m


def photo_machine(artists, photos=(), markers=(), colours=None, **kw):
    """The Artists page's world with photos: photos (names) have a -44 file with a flat picture (colours[name], else by position), markers (names) the empty "no photo" file; the glyph of the placeholder."""
    m = artists_machine(artists, **kw)
    m.load_image = 0
    m.images['pod_ic_ar_art'] = (24, 24, bytes((0x8c, 0x8c, 0x8c, 255)) * (24 * 24))
    for i, n in enumerate(photos):
        c = (colours or {}).get(n, (40 * (i + 1) % 256, 90, 200 - 30 * i))
        m.files[ap44(n)] = 900; m.present.add(ap44(n))
        m.images['file://' + ap44(n)] = (44, 44, bytes((*c, 255)) * (44 * 44))
    for n in markers: m.files[ap44(n)] = 0; m.present.add(ap44(n))
    return m


def photo_tick(m, limit=60):
    """The photo loader's timer fires until it does not re-arm itself; the calls of all the ticks."""
    seen = []
    for _ in range(limit):
        m.calls = []
        m.call(PSYMS['ar_on_photo'], a0=0, count=40000000)
        seen += m.calls
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['ar_on_photo'] for c in m.calls): return seen
    raise AssertionError('the photo loader never finished')


def circles(m, blits):
    """The row circles of a frame: [(dst y, bitmap handle)] of the 40 px blits at x 16."""
    return sorted((b[2][1], b[0]) for b in blits if b[2][0] == PHOTO_X and b[2][2] == PHOTO)


def bmp_px(m, bmp, x, y):
    data, w, h = m.bitmaps[bmp]
    return struct.unpack('<I', m.u.mem_read(data + (y * w + x) * 4, 4))[0]


def photo_rows_tests(ctx):
    """Layout A of the Artists and Album Artists rows (docs/modules/artists.md "Rows"): a 40 px circle at x 16 centred in the 52 px row, the name and the hairline from x 68; the circle
    decoded by the page's own loader (one a tick, none while the list moves, paint opens nothing), the shared placeholder for a row with no photo or not yet looked at, the lead artist's
    photo for "A feat. B"; Genres and Composers rows untouched."""
    expect = ctx.expect
    open_ = PSYMS['artists_open']
    names = ('Abba', 'Abel feat. Zed', 'Adele', 'Aha & Faithless', 'Alt', 'Unknown Artist')
    photos, markers = ('Abba', 'Abel', 'Aha', 'Unknown Artist'), ('Adele', 'Aha & Faithless')
    col = {'Abba': (200, 30, 30), 'Abel': (30, 200, 30), 'Aha': (30, 30, 200), 'Unknown Artist': (250, 250, 250)}
    m = photo_machine(names, photos, markers, colours=col)
    m.call(open_, count=20000000)
    opened = list(m.calls)
    mod = Model(list(names))
    # rows before anything is decoded: the shared placeholder in every circle slot, the names from x 68, the hairlines from x 68
    blits, texts, styles, fills = ar_paint(m, 0)
    ph = circles(m, blits)
    ys = [mod.row_y(i) + (ROW - PHOTO) // 2 for i in range(len(names))]
    expect([y for y, _ in ph] == ys and len({b for _, b in ph}) == 1, f'a 40 px circle at x 16, centred in each row, all the one placeholder bitmap ({ph})')
    touched = lambda calls: [c for c in calls if (c[0] == 'widget_load_image' and c[1].startswith('file://')) or (c[0] in ('fopen', 'access', 'stat') and AP_DIR in str(c[1]))]
    expect(not touched(m.calls) and not touched(opened), 'paint (and open) opens no photo file')
    rows = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_row_title']
    expect(rows == [(n, (NAME_X, mod.row_y(i) + TEXT_Y, TEXT_END - NAME_X, TEXT_H)) for i, n in enumerate(names)], f'the names from x {NAME_X} to the chevron\'s room ({rows})')
    hair = [f for f in fills if f[0] == O['LIST_HAIR']]
    expect([(f[1], f[3]) for f in hair] == [(NAME_X, O['LIST_HAIR_END'] - INSET - NAME_X)] * len(names), 'the hairlines run from x 68 to 284 (the rail shown)')
    chev = [b for b in blits if tuple(b[2][2:]) == (CHEV_W, CHEV_H)]
    expect([b[2][0] for b in chev] == [CHEV_X] * len(names), 'the chevrons stay at x 262')
    # the placeholder: #333333 circle (alpha-cut edge), the glyph's grey in the middle
    p = ph[0][1]
    expect(bmp_px(m, p, 20, 6) == 0xff333333 and bmp_px(m, p, 0, 0) >> 24 == 0 and bmp_px(m, p, 39, 39) >> 24 == 0, 'the placeholder is a #333333 circle: the corners clear, the inside opaque')
    expect(bmp_px(m, p, 20, 20) & 0xffffff == 0x8c8c8c and bmp_px(m, p, 20, 11) & 0xffffff == 0x8c8c8c, 'the glyph in #8C8C8C at the middle (0.52 of the diameter: 20 px)')
    edge = [bmp_px(m, p, x, 20) >> 24 for x in range(0, 6)]
    expect(edge == sorted(edge) and edge[0] < 255 and 0 < max(edge) and any(0 < a < 255 for a in edge) or any(0 < bmp_px(m, p, x, 3) >> 24 < 255 for x in range(40)), f'the edge is antialiased ({edge})')
    # the loader: one row a tick, nearest the middle first; nothing for the rows whose state is known (the marker) or the Unknown row
    seen = photo_tick(m)
    loads = [c[1] for c in seen if c[0] == 'widget_load_image' and c[1].startswith('file://')]
    want = sorted('file://' + ap44(n) for n in ('Abba', 'Abel', 'Aha'))
    expect(sorted(loads) == want, f'the full name\'s file, else the lead artist\'s ("Abel feat. Zed" -> Abel, "Aha & Faithless" -> Aha, whose own file is the empty marker); ({loads})')
    expect('file://' + ap44('Unknown Artist') not in loads and 'file://' + ap44('Adele') not in loads, 'the Unknown Artist row and a marker row are never decoded')
    blits, _, _, _ = ar_paint(m, 0)
    got = dict(circles(m, blits))
    real = [y for y in ys if got[y] != ph[0][1]]
    expect(real == [ys[0], ys[1], ys[3]], f'the circles of Abba, Abel feat. Zed and Aha & Faithless are decoded, the rest keep the placeholder ({real})')
    for y, name in ((ys[0], 'Abba'), (ys[1], 'Abel'), (ys[3], 'Aha')):
        v = bmp_px(m, got[y], 20, 20)
        want_c = col[name]
        expect(v >> 24 == 255 and all(abs(((v >> (8 * k)) & 255) - want_c[k]) <= 3 for k in range(3)) and bmp_px(m, got[y], 0, 0) >> 24 == 0 and bmp_px(m, got[y], 20, 0) >> 24 > 200,
               f'{name}: the photo, cut to a circle (the corners clear)')
    expect(not touched(m.calls), 'the repaint opens nothing')
    # the 2-bit states: the marker is remembered (scrolling away and back never opens its file again); a missing file (Enya) is looked for again
    count44 = lambda mm, n: sum(1 for p in mm.__dict__.get('fopens', []) if p == ap44(n))
    adele, alt = count44(m, 'Adele'), count44(m, 'Alt')
    expect(adele >= 1 and alt >= 1, 'each was looked at once')
    many = [f'A{i:02d}' for i in range(1, 41)]
    ml = photo_machine(many, ('A03',), ('A01',))
    ml.call(open_, count=20000000)
    photo_tick(ml)
    first = (count44(ml, 'A01'), count44(ml, 'A02'), count44(ml, 'A03'))
    scroll_to(ml, 1200); photo_tick(ml)
    scroll_to(ml, 0); photo_tick(ml)
    after = (count44(ml, 'A01'), count44(ml, 'A02'), count44(ml, 'A03'))
    expect(after[0] == first[0] and after[1] == first[1] + 1 and after[2] == first[2] + 1,
           f'the ring let the top rows go: the marker row (A01) is remembered and its file not opened again, the unknown (A02) and the photo (A03) are looked at again ({first} -> {after})')
    # one decode a tick; none while the list moves
    m2 = photo_machine(names, photos, markers, colours=col)
    m2.call(open_, count=20000000)
    m2.calls = []; m2.call(PSYMS['ar_on_photo'], a0=0, count=40000000)
    one = [c for c in m2.calls if c[0] == 'widget_load_image' and c[1].startswith('file://')]
    expect(len(one) <= 1 and any(c[0] == 'timer_add' for c in m2.calls), f'one photo a tick, the timer re-armed ({len(one)})')
    m3 = photo_machine(names, photos, markers, colours=col)
    m3.call(open_, count=20000000)
    m3.u.mem_write(m3.sv + O['SC_PRESSED'], b'\x01'); m3.u.mem_write(m3.sv + O['SC_DRAGGED'], b'\x01')   # a finger dragging the list
    m3.calls = []; m3.call(PSYMS['ar_on_photo'], a0=0, count=40000000)
    expect(not touched(m3.calls) and any(c[0] == 'timer_add' for c in m3.calls), 'nothing is decoded while the scroll_view moves; the timer polls')
    m3.u.mem_write(m3.sv + O['SC_PRESSED'], b'\x00')
    seen = photo_tick(m3)
    expect(len([c for c in seen if c[0] == 'widget_load_image' and c[1].startswith('file://')]) == 3, 'and the photos come once it rests')
    # a file that does not decode is "no photo": the placeholder, remembered
    m4 = photo_machine(('Abba', 'Unknown Artist'), ('Abba',)); m4.load_image = 0
    del m4.images['file://' + ap44('Abba')]
    m4.call(open_, count=20000000)
    photo_tick(m4)
    b4, _, _, _ = ar_paint(m4, 0)
    expect(len({b for _, b in circles(m4, b4)}) == 1, 'a picture that does not decode leaves the placeholder')
    # the destroy frees the timer and every bitmap (the ring's circles, the placeholder, the disc, the chevron)
    m.calls = []
    m.call(PSYMS['ar_on_destroy'], count=2000000)
    freed = sum(1 for c in m.calls if c[0] == 'bitmap_destroy')
    expect(freed >= 6, f'closing the page frees the circles and the placeholder ({freed} bitmaps)')

    # Genres and Composers: no circle, the name at x 24, the hairline from 24, no loader, no file looked at
    P = pod_pages
    for label, home, kw in (('Genres', P.HOME_GENRE, {'genres': ('Rock', 'Jazz', 'Unknown Genre')}), ('Composers', P.HOME_COMPOSER, {'composers': ('Bach', 'Mozart', 'Unknown Composer')})):
        g = photo_machine((), (), (), **kw)
        for n in kw.get('genres', ()) + kw.get('composers', ()):
            g.files[ap44(n)] = 900; g.present.add(ap44(n))
        g.call(open_, a0=home, count=20000000)
        gb, gt, gs, gf = ar_paint(g, 0)
        rows = [(t, r[0], r[2]) for (t, r), s in zip(gt, gs) if s == 'label_row_title']
        expect([x for _, x, _ in rows] == [TEXT_X] * 3 and all(w == TEXT_END - TEXT_X for _, _, w in rows), f'{label}: the names stay at x 24')
        expect(not circles(g, gb) and not [f for f in gf if f[0] == O['LIST_HAIR'] and f[1] != TEXT_X], f'{label}: no circle, the hairlines from x 24')
        expect(not any(c[0] == 'timer_add' and c[1] == PSYMS['ar_on_photo'] for c in g.calls) and not [c for c in g.calls if c[0] == 'widget_load_image' and c[1].startswith('file://')], f'{label}: no photo loader')

    # Album Artists (the Show group) has circles too, and the state restarts with the new list
    m5 = photo_machine(('Abba', 'Adele'), ('Abba', 'Miles Davis'), ('Adele',))
    m5.call(open_, count=20000000)
    photo_tick(m5)
    card_texts(m5)
    pick(m5, 5)
    photo_tick(m5)
    b5, _, _, _ = ar_paint(m5, 0)
    got5 = circles(m5, b5)
    expect(shown(m5) == ['Miles Davis', 'Various Artists'] and len(got5) == 2 and got5[0][1] != got5[1][1], f'Album Artists rows have circles too, Miles Davis\'s decoded ({shown(m5)})')


def al_paint(m, off=0):
    """One EVT_AFTER_PAINT of the Albums page's content view at scroll offset off: the frame's blits."""
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], SCREEN_Y0 & 0xffffffff)
    m.setword(m.sv + SC_YOFF, off)
    m.blits.clear(); m.texts.clear()
    m.call(PSYMS['al_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits)


def al_settle(m, limit=30):
    """The Albums page's loader timer fires until it stops re-arming (the header first, then the covers)."""
    for _ in range(limit):
        m.calls = []
        m.call(PSYMS['al_on_load'], count=40000000)
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['al_on_load'] for c in m.calls): return
    raise AssertionError('the Albums loader never finished')


def head_machine(view=b'0\n', photo=None, key_name='Miles Davis', glyph=True, drop=(), home=0):
    """The artist-scoped Albums page of Miles Davis with the photo header (photo: the colour of his -168 file's flat picture, else no file)."""
    m = artists_machine(albums_page=True, photos=False)
    for w in drop: del m.widgets[w]
    m.load_image = 0
    m.fs['/mnt/data/m1plus/albums-view'] = view
    if glyph: m.images['pod_ic_ar_art'] = (24, 24, bytes((0x8c, 0x8c, 0x8c, 255)) * (24 * 24))
    if photo:
        p = f'{AP_DIR}/a{ap_key(key_name):08x}-168.jpg'
        m.files[p] = 5000; m.present.add(p); m.images['file://' + p] = (168, 168, bytes((*photo, 255)) * (168 * 168))
    for n, t in (('btn_play', 'Play'), ('btn_shuffle', 'Shuffle')): m.wtext[m.widgets[n]] = t
    m.call(PSYMS['artists_open'], a0=home, count=20000000)
    m.calls = []
    m.call(PSYMS['ar_open'], a0=0, count=40000000)
    m.open_calls = list(m.calls)
    return m


def scoped_head_tests(ctx):
    """The artist page's header (docs/modules/albums.md "Scoped to an artist"): the album page's header with a circle: 160 px at (80, 8), the name under it (22 px white, centred, al_name), the pills
    under the name; every offset of the page (rows, hit tests, loader, collapse) starts the header's height further down; the circle is the -168 photo; an artist with no photo has the same header without the circle (PH_SHIFT higher); a composer's page and the
    library's keep the large title."""
    import awtk_ui
    expect = ctx.expect
    END, RGAP, ROWH = O['AL_HEAD_END'], O['GRID_ROW_GAP'], O['LIST_ROW_H']
    PITCH = O['GRID_COVER'] + O['GRID_TITLE_GAP'] + O['GRID_TITLE_H'] + O['GRID_SUB_H'] + RGAP
    CX, CY, CD = O['AL_PHOTO_X'], O['AL_PHOTO_Y'], O['AL_PHOTO_D']
    expect((CD, CX, CY) == (88, 116, 8) and (O['PH_NAME_X'], O['PH_NAME_W'], O['AL_NAME_Y'], O['PH_NAME_H']) == (17, 286, 110, 22),
           'the circle is 88 px, centred (x 116), 8 px under the navbar; the name is 22 px high, 14 px under it, in the album page\'s 286 px')
    expect(O['AL_HEAD_PILL_Y'] == O['AL_NAME_Y'] + O['PH_NAME_H'] + 16 and END == O['AL_HEAD_PILL_Y'] + O['SG_PILL_H'] == 188 and O['AL_HEAD_COLLAPSE'] == O['AL_NAME_Y'] + O['PH_NAME_H'],
           'the pills are 16 px under the name\'s box and the block ends at 188; the navbar title shows once the name\'s box has scrolled away (132)')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_albums.bin'), 'rb').read())
    nm = tree.find('al_name')
    expect(nm is not None and nm in tree.find('view_grid').children and (nm.x, nm.y, nm.w, nm.h) == (17, 110, 286, 22) and nm.get('visible') == 'false' and nm.get('sensitive') == 'false'
           and nm.get('style:normal:font_size') == '22' and nm.get('style:normal:text_color') == '#FFFFFF' and nm.get('style:normal:text_align_h') == 'center',
           'the asset has al_name in the content view: 22 px white, centred, in the album page\'s title box, hidden and insensitive')
    mod_icons_art = mod_icons.ARTIST_ART
    expect(mod_icons_art == ('pod_ic_ar_art', 'mic-vocal') and mod_icons.COVER_FRAC == 0.52 and os.path.exists(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx/pod_ic_ar_art.png')),
           'the placeholder\'s glyph is the Lucide mic-vocal asset pod_ic_ar_art (the no-cover tile rule: 0.52 of the circle)')

    for mode, view in (('list', b'0\n'), ('grid', b'1\n')):
        m = head_machine(view, photo=(60, 90, 200))
        w = lambda n: (m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1))
        expect(('widget_set_text_utf8', m.widgets['al_name'], 'Miles Davis') in m.open_calls and w('al_name') == (1, 1) and w('al_title') == (0, 0),
               f'{mode}: the name is on al_name, shown; the large title is hidden and insensitive')
        expect(('widget_set_text_utf8', m.widgets['label_title'], 'Miles Davis') in m.open_calls and m.props.get((m.widgets['label_title'], 'visible'), 0) != 1, f'{mode}: the navbar\'s small title is the name, hidden at rest')
        expect(('widget_move', m.widgets['btn_play'], O['AL_PLAY_X'], O['AL_HEAD_PILL_Y']) in m.open_calls and ('widget_move', m.widgets['btn_shuffle'], O['AL_SHUFFLE_X'], O['AL_HEAD_PILL_Y']) in m.open_calls,
               f'{mode}: Play and Shuffle move under the name')
        h = [c[3] for c in m.open_calls if c[0] == 'widget_resize' and c[1] == m.view][-1]
        expect(h == END + (RGAP + 4 * ROWH if mode == 'list' else RGAP + 2 * PITCH), f'{mode}: the content is the header block and the albums ({h})')
        # nothing is drawn before the loader has run; then the placeholder circle at 160 px
        expect(not [b for b in al_paint(m) if tuple(b[2]) == (CX, CY, CD, CD)], f'{mode}: no circle before the loader has made it')
        al_settle(m)
        got = [b for b in al_paint(m) if tuple(b[2]) == (CX, CY, CD, CD)]
        expect(len(got) == 1, f'{mode}: the circle is drawn at (116, 8), 88 x 88 ({len(got)})')
        # scrolled: the circle is cut by hand at the top of the window and gone past its end
        c1 = [b for b in al_paint(m, 50) if b[2][0] == CX and b[2][2] == CD]
        c2 = [b for b in al_paint(m, CY + CD) if b[2][0] == CX and b[2][2] == CD]
        expect(c1 and tuple(c1[0][2]) == (CX, 0, CD, CD + CY - 50) and tuple(c1[0][1]) == (0, 50 - CY, CD, CD + CY - 50) and not c2, f'{mode}: scrolled 50 px the top 42 rows are cut away; past the circle nothing is drawn ({c1[:1]})')
        # hit tests: the header and the pills block open nothing; the first album starts END (+ the gap) down
        opened = lambda calls: [c for c in calls if c[:2] == ('navigator_to_with_context', 'albuminfo_page')]
        def tap(y, x=30):
            m.calls = []
            m.touch('down', x, SCREEN_Y0 + y, 1000, fn='al_on_down'); m.touch('up', x, SCREEN_Y0 + y, 1080, fn='al_on_up', count=40000000)
            return opened(m.calls)
        m.setword(m.sv + SC_YOFF, 0)
        first = END + RGAP
        expect(not tap(100) and not tap(CY + 20, CX + CD // 2) and not tap(first - 3) and tap(first + 5), f'{mode}: a tap on the circle, the name or the pills block opens nothing; the first row/cell starts at {first}')
        # the small title appears once the name has gone
        small = m.widgets['label_title']
        m.setword(m.sv + SC_YOFF, O['AL_HEAD_COLLAPSE'] - 1); m.call(PSYMS['al_on_scroll'], count=4000000)
        a = m.props.get((small, 'visible'), 0)
        m.setword(m.sv + SC_YOFF, O['AL_HEAD_COLLAPSE']); m.call(PSYMS['al_on_scroll'], count=4000000)
        expect(a == 0 and m.props.get((small, 'visible')) == 1, f'{mode}: the navbar\'s title shows at 132 (the name\'s box has scrolled away), not at 46')
        m.setword(m.sv + SC_YOFF, 0); m.call(PSYMS['al_on_scroll'], count=4000000)

    # the photo: the -168 file cut to a circle (the corners clear, the edge antialiased); one decode, none while the list moves
    m = head_machine(photo=(10, 120, 240))
    m.u.mem_write(m.sv + O['SC_PRESSED'], b'\x01'); m.u.mem_write(m.sv + O['SC_DRAGGED'], b'\x01')
    m.calls = []; m.call(PSYMS['al_on_load'], count=40000000)
    expect(not [c for c in m.calls if c[0] == 'widget_load_image'] and any(c[0] == 'timer_add' for c in m.calls), 'while the list moves nothing is decoded: the timer polls')
    m.u.mem_write(m.sv + O['SC_PRESSED'], b'\x00')
    al_settle(m)
    got = [b for b in al_paint(m) if tuple(b[2]) == (CX, CY, CD, CD)]
    v = bmp_px(m, got[0][0], CD // 2, CD // 2) if got else 0
    expect(got and v >> 24 == 255 and all(abs(((v >> (8 * k)) & 255) - c) <= 3 for k, c in enumerate((10, 120, 240))) and bmp_px(m, got[0][0], 0, 0) >> 24 == 0 and 0 < bmp_px(m, got[0][0], CD // 2, 0) >> 24 < 256
           and any(0 < bmp_px(m, got[0][0], x, 4) >> 24 < 255 for x in range(CD // 2)), 'the photo: the -168 file cut to a circle, the corners clear, the edge antialiased')
    url = 'file://' + f'{AP_DIR}/a{ap_key("Miles Davis"):08x}-168.jpg'
    expect(len([c for c in m.calls if c[0] == 'widget_load_image' and c[1] == url]) <= 1, 'decoded once')
    m.calls = []
    m.call(PSYMS['al_on_destroy'], count=4000000)
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_destroy') >= 1, 'closing the page frees the circle')

    # an asset without al_name and the library's page keep the large title and the old block; a composer's page has the header without the circle
    m = head_machine(drop=('al_name',))
    expect(m.props.get((m.widgets['al_title'], 'visible'), 1) != 0 and [c[3] for c in m.open_calls if c[0] == 'widget_resize' and c[1] == m.view][-1] == O['AL_PILLS_END'] + RGAP + 4 * ROWH
           and not [c for c in m.open_calls if c[0] == 'widget_move' and c[1] == m.widgets['btn_play']], 'a page without al_name: the large title and the pills at 52, as before')
    m = artists_machine(composers=('Mozart', 'Bach', 'Unknown Composer'), albums_page=True)
    m.fs['/mnt/data/m1plus/albums-view'] = b'0\n'; m.load_image = 0
    m.call(PSYMS['artists_open'], a0=pod_pages.HOME_COMPOSER, count=20000000); m.calls = []
    m.call(PSYMS['ar_open'], a0=1, count=40000000)
    expect(m.props.get((m.widgets['al_name'], 'visible')) == 1 and m.props.get((m.widgets['al_title'], 'visible'), 1) == 0 and ('widget_set_text_utf8', m.widgets['al_name'], 'Bach') in m.calls
           and [c[3] for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1] == O['AL_HEAD_END'] - O['PH_SHIFT'] + RGAP + 3 * ROWH
           and not [c for c in m.calls if c[0] == 'widget_load_image' and AP_DIR in str(c[1])], 'a composer\'s page: the artist header without the circle (centred name, pills), no photo looked up')
    al_settle(m)
    expect(not [b for b in al_paint(m) if b[2][2] == CD], 'and no circle')
    m = artists_machine(albums_page=True); m.fs['/mnt/data/m1plus/albums-view'] = b'0\n'; m.call(PSYMS['albums_open'], count=20000000)
    expect(m.props.get((m.widgets['al_name'], 'visible'), 0) != 1 and ('widget_set_text_utf8', m.widgets['al_title'], 'Albums') in m.calls, 'the library Albums page: unchanged')


def scoped_plain_tests(ctx):
    """An artist with no photo in the cache (docs/modules/albums.md "Scoped to an artist"): the artist header without the circle - the name and the pills PH_SHIFT higher, same gaps and x, the rows
    and the title's collapse with them; no placeholder; the page's re-check of the artist (patch/artistphoto.c ap_recheck, on the cover worker) switches the circle in place."""
    expect = ctx.expect
    END, RGAP, ROWH, SH = O['AL_HEAD_END'], O['GRID_ROW_GAP'], O['LIST_ROW_H'], O['PH_SHIFT']
    PITCH = O['GRID_COVER'] + O['GRID_TITLE_GAP'] + O['GRID_TITLE_H'] + O['GRID_SUB_H'] + RGAP
    CX, CY, CD = O['AL_PHOTO_X'], O['AL_PHOTO_Y'], O['AL_PHOTO_D']
    NX, NY, NH = O['PH_NAME_X'], O['AL_NAME_Y'], O['PH_NAME_H']
    PY, PX1, PX2 = O['AL_HEAD_PILL_Y'], O['AL_PLAY_X'], O['AL_SHUFFLE_X']
    expect(SH == CY + CD == 96 and NY - SH == 14 and PY - SH == O['SG_PILL_Y'] == 52 and END - SH == O['AL_PILLS_END'] == 92 and O['AL_HEAD_COLLAPSE'] - SH == 36,
           'the circle\'s room (8 + 88 px) is the one shift: name y 14, pills y 52, block end 92, collapse 36')
    moves = lambda m, n: [c[2:] for c in m.open_calls if c[0] == 'widget_move' and c[1] == m.widgets[n]]
    for mode, view in (('list', b'0\n'), ('grid', b'1\n')):
        mp, mc = head_machine(view), head_machine(view, photo=(60, 90, 200))
        w = lambda n: (mp.props.get((mp.widgets[n], 'visible'), 1), mp.props.get((mp.widgets[n], 'sensitive'), 1))
        expect(('widget_set_text_utf8', mp.widgets['al_name'], 'Miles Davis') in mp.open_calls and w('al_name') == (1, 1) and w('al_title') == (0, 0),
               f'{mode}: no photo: the same name label, shown; the large title hidden')
        pn, pp, ps, cp, cs = moves(mp, 'al_name'), moves(mp, 'btn_play'), moves(mp, 'btn_shuffle'), moves(mc, 'btn_play'), moves(mc, 'btn_shuffle')
        expect(pn == [(NX, NY - SH)] and pp == [(PX1, PY - SH)] and ps == [(PX2, PY - SH)] and cp == [(PX1, PY)] and cs == [(PX2, PY)] and not moves(mc, 'al_name'),
               f'{mode}: the name and the pills are PH_SHIFT higher without the circle: same x, y {NY - SH} / {PY - SH} against {NY} / {PY}')
        expect(pp[0][1] - (pn[0][1] + NH) == cp[0][1] - (NY + NH) == 16 and pn[0][0] == NX and pp[0][0] == cp[0][0] and ps[0][0] == cs[0][0],
               f'{mode}: the name-to-pills gap (16 px) and every x are the same in both')
        h = [c[3] for c in mp.open_calls if c[0] == 'widget_resize' and c[1] == mp.view][-1]
        expect(h == END - SH + (RGAP + 4 * ROWH if mode == 'list' else RGAP + 2 * PITCH), f'{mode}: the content is the header block (92) and the albums ({h})')
        al_settle(mp)
        expect(not [b for b in al_paint(mp) if b[2][2] == CD] and not [c for c in mp.calls if c[0] == 'widget_load_image' and (AP_DIR in c[1] or c[1] == 'pod_ic_ar_art')]
               , f'{mode}: no circle, no placeholder, no photo file looked at')
        opened = lambda calls: [c for c in calls if c[:2] == ('navigator_to_with_context', 'albuminfo_page')]
        def tap(y, x=30):
            mp.calls = []
            mp.touch('down', x, SCREEN_Y0 + y, 1000, fn='al_on_down'); mp.touch('up', x, SCREEN_Y0 + y, 1080, fn='al_on_up', count=40000000)
            return opened(mp.calls)
        mp.setword(mp.sv + SC_YOFF, 0)
        first = END - SH + RGAP
        expect(not tap(30) and not tap(first - 3) and tap(first + 5), f'{mode}: the pills block opens nothing; the first row/cell starts at {first}')
        small = mp.widgets['label_title']
        mp.setword(mp.sv + SC_YOFF, O['AL_HEAD_COLLAPSE'] - SH - 1); mp.call(PSYMS['al_on_scroll'], count=4000000)
        a = mp.props.get((small, 'visible'), 0)
        mp.setword(mp.sv + SC_YOFF, O['AL_HEAD_COLLAPSE'] - SH); mp.call(PSYMS['al_on_scroll'], count=4000000)
        expect(a == 0 and mp.props.get((small, 'visible')) == 1, f'{mode}: the navbar\'s title shows at 36 (the name\'s box has scrolled away)')

    # the re-check on the page's own set: started once the page's cover build has nothing (or no more) to do; the job holds the artist's albums' first tracks
    def fire(m, name):
        m.calls = []
        m.call(PSYMS[name], count=40000000)
        return list(m.calls)
    def swap(m, photo):
        p = f'{AP_DIR}/a{ap_key("Miles Davis"):08x}-168.jpg'
        if photo:
            m.files[p] = 5000; m.present.add(p); m.images['file://' + p] = (168, 168, bytes((*photo, 255)) * (168 * 168))
        else:
            m.files.pop(p, None); m.present.discard(p)
    def finish(m, changed):
        if changed: m.setword(PSYMS['ap_ep'], m.word(PSYMS['ap_ep']) + 1)
        m.setword(PSYMS['cb'] + 4 * 5, build_state(m)['total'])   # the worker is done
        return fire(m, 'al_on_build')
    for mode, view in (('list', b'0\n'), ('grid', b'1\n')):
        # found: the circle appears, the header moves down
        m = head_machine(view)
        new = fire(m, 'al_on_build_start')
        s = build_state(m)
        jobs = [(m.read_cstr(m.word(s['jobs'] + 16 * i)), m.word(s['jobs'] + 16 * i + 4), m.word(s['jobs'] + 16 * i + 12)) for i in range(s['total'])]
        expect(('pthread_create',) in new and s['total'] == 1 and jobs[0][1] == ap_key('Miles Davis') and jobs[0][2] == 2 and len(jobs[0][0].splitlines()) == 3 and jobs[0][0].endswith('\n')
               and all(t.startswith('/mnt/mmc/Miles Davis/') and t.endswith('/1.flac') for t in jobs[0][0].splitlines()) and [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['al_on_build']],
               f'{mode}: the page asks for a re-check of Miles Davis on the worker: one job (sec 2), the three albums\' first tracks ({jobs}), the poll timer runs')
        expect(not any(c[0] in ('opendir', 'readdir', 'fopen') and AP_DIR in str(c[1:]) for c in new), f'{mode}: the UI thread opens no photo file for it')
        swap(m, (60, 90, 200))
        new = finish(m, True)
        expect(('widget_move', m.widgets['btn_play'], PX1, PY) in new and ('widget_move', m.widgets['al_name'], NX, NY) in new, f'{mode}: a photo found: the name and the pills move down by the circle')
        h = [c[3] for c in new if c[0] == 'widget_resize' and c[1] == m.view][-1]
        expect(h == END + (RGAP + 4 * ROWH if mode == 'list' else RGAP + 2 * PITCH), f'{mode}: and the content grows by the circle\'s room ({h})')
        al_settle(m)
        expect(len([b for b in al_paint(m) if tuple(b[2]) == (CX, CY, CD, CD)]) == 1, f'{mode}: the circle is drawn once the loader has made it')
        expect(build_state(m)['jobs'] == 0, f'{mode}: the set is freed')
        # removed: the photo goes, the circle too
        m = head_machine(view, photo=(60, 90, 200)); al_settle(m)
        fire(m, 'al_on_build_start')
        swap(m, None)
        new = finish(m, True)
        expect(('widget_move', m.widgets['btn_play'], PX1, PY - SH) in new and ('widget_move', m.widgets['al_name'], NX, NY - SH) in new and [c for c in new if c[0] == 'bitmap_destroy'],
               f'{mode}: a photo that is gone: the circle is freed, the name and the pills move up')
        al_settle(m)
        expect(not [b for b in al_paint(m) if b[2][2] == CD], f'{mode}: and no circle is drawn')
        # a replaced photo: the same layout, the circle read again; unchanged: nothing moves and nothing is decoded again
        m = head_machine(view, photo=(60, 90, 200)); al_settle(m)
        fire(m, 'al_on_build_start')
        new = finish(m, False)
        al_settle(m)
        expect(not [c for c in new if c[0] == 'widget_move'] and not [c for c in m.calls if c[0] == 'widget_load_image' and AP_DIR in c[1]], f'{mode}: unchanged: the header stays')
        m = head_machine(view, photo=(60, 90, 200)); al_settle(m)
        fire(m, 'al_on_build_start')
        swap(m, (200, 90, 60))
        new = finish(m, True)
        al_settle(m)
        got = [b for b in al_paint(m) if tuple(b[2]) == (CX, CY, CD, CD)]
        v = bmp_px(m, got[0][0], 80, 80) if got else 0
        expect(not [c for c in new if c[0] == 'widget_move'] and got and abs((v & 255) - 200) <= 3, f'{mode}: a replaced photo: the circle is made again from the new file, nothing moves')
    # the worker busy (Home's pass, Cover Flow): the page asks nothing; a page that closes cancels the re-check
    m = head_machine()
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    new = fire(m, 'al_on_build_start')
    expect(('pthread_create',) not in new and build_state(m)['total'] == 0, 'the worker is held by another set: no re-check, nothing waits for it')
    m = head_machine()
    fire(m, 'al_on_build_start')
    m.calls = []
    m.call(PSYMS['al_on_destroy'], count=4000000)
    expect(not [c for c in m.calls if c[0] == 'pthread_join'] and build_state(m)['orphan'] == 1, 'closing the page cancels the re-check, never waiting for the worker (it is orphaned until it exits)')
    # the Artists list behind the page: the circles are looked for again when it is in front and a re-check changed a photo
    m = photo_machine(('Abba', 'Adele'), ('Abba',), ('Adele',), colours={'Abba': (200, 30, 30)})
    m.call(PSYMS['artists_open'], count=20000000)
    photo_tick(m)
    new = fire(m, 'ar_on_fg')
    expect(not [c for c in new if c[0] == 'timer_add'], 'the Artists page in front again, no photo changed: nothing is looked at again')
    m.files[ap44('Adele')] = 900
    m.images['file://' + ap44('Adele')] = (44, 44, bytes((10, 200, 10, 255)) * (44 * 44))
    m.setword(PSYMS['ap_ep'], m.word(PSYMS['ap_ep']) + 1)
    new = fire(m, 'ar_on_fg')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_photo']], 'a re-check changed a photo: the loader runs again')
    seen = photo_tick(m)
    loads = [c[1] for c in seen if c[0] == 'widget_load_image' and c[1].startswith('file://')]
    expect(sorted(loads) == sorted('file://' + ap44(n) for n in ('Abba', 'Adele')), f'every circle is decoded again, Adele\'s new photo too ({loads})')
    blits, _, _, _ = ar_paint(m, 0)
    expect(len({b for _, b in circles(m, blits)}) == 2, 'both rows show a photo now')
    new = fire(m, 'ar_on_fg')
    expect(not [c for c in new if c[0] == 'timer_add'], 'and once only')
    # rows whose file was missing are looked at again when the Home pass that makes the photos is over
    m = photo_machine(('Abba', 'Alt'), ('Abba',))
    m.call(PSYMS['artists_open'], count=20000000)
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    assert m.call(PSYMS['cc_build_add'], a0=m.cstr('/mnt/mmc/x/1.flac'), a1=5, count=1 << 40) == 1
    m.call(PSYMS['cc_build_start'], count=1 << 40)
    seen = photo_tick(m)
    expect([c for c in seen if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_retry']], 'a row with no file while a set runs: the page waits for its end')
    new = fire(m, 'ar_on_retry')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_retry']] and not [c for c in new if c[1] == PSYMS['ar_on_photo']], 'the set still runs: it asks again later')
    m.files[ap44('Alt')] = 0; m.present.add(ap44('Alt'))
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    new = fire(m, 'ar_on_retry')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_photo']] and not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_retry']], 'the set is over: the rows look again, the page asks no more')
    photo_tick(m)
    new = fire(m, 'ar_on_retry')
    expect(not [c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['ar_on_retry']], 'and the row\'s marker is known now (no more waiting)')


SECTIONS = [artists_tests, scoped_albums_tests, scoped_nextalbum_tests, scoped_pills_tests, scoped_sort_tests, genre_composer_tests, index_tests, sort_tests, name_order_tests, photo_rows_tests, scoped_head_tests, scoped_plain_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)

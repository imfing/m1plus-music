"""Songs (patch/songs.c, docs/modules/songs.md): the menu row and its fallback to the stock page, the asset (the glass navbar with Search / Sort / Select, the large title
and the flat pills in the content view, the rail, the bubble, the sort card, the select bar), the stock list read once and kept as an 8 byte index, the sections of the
Title order (the Initial byte: '*' digits, 'A'..'Z', '#' others, 0 = the title's first letter) and the plain list of every other order, the rows and the pinned header
painted from the stock list, the cover loader and the library lookup, the taps (play like the stock row, mark in select mode), the rail (grab, jump, bubble, disc),
the sort card (sort_flag as the stock dialog writes it), Search, the select mode with Delete (batch_delete_file on the stock selection vector) and Add (the stock
playlist picker), a stock list replaced under the page, the title that collapses into the navbar, the pills' centring and a library of 20,000 songs."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

SCREEN_Y0 = 30 + 50
TOP, HDR, ROW, VIEW_H, TILES, FOOT = O['SG_TOP'], O['SG_HDR_H'], O['LIST_ROW_H'], O['GRID_VIEW_H'], O['GRID_TILES'], O['SG_FOOT_H']
SC_YOFF, SC_VH = O['SC_YOFF'], 0x7c
SORT_FLAG, SEL_VEC, NAV_TITLE, G_CLASS = pod.DATA['SORT_FLAG'][0], pod.DATA['SEL_VEC'][0], pod.DATA['NAV_TITLE'][0], pod.DATA['G_CLASS_TYPE'][0]
SHOWLIST = pod.DATA['PDEQ_SHOWLIST'][0]
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_songs.bin') if WORK else None
ALL = O['CLASS_ALL_SONGS']
TEXT_X, TEXT_END, SEL = O['LIST_TEXT_X'], O['SG_TEXT_END'], O['SG_SEL_COL']
RAIL_X, RAIL_W = O['SG_RAIL_X'], O['SG_RAIL_W']
WIDGETS = ('btn_coverflow', 'view_grid', 'sg_rail', 'sg_foot', 'sg_hname', 'btn_return', 'btn_backtoplayer', 'btn_search', 'btn_sort', 'btn_select', 'btn_selall', 'btn_play', 'btn_shuffle', 'sg_add', 'sg_del', 'sg_scrim', 'sg_card',
           'label_title', 'sg_title', 'label_status', 'label_row_title', 'label_row_sub', 'label_hdr', 'label_rail', 'label_rail_on', 'sg_bubble', 'sg_bubble_letter', 'sg_bar',
           'sg_item0', 'sg_item1', 'sg_item2', 'sg_item3', 'sg_item4', 'sg_tick0', 'sg_tick1', 'sg_tick2', 'sg_tick3', 'sg_tick4')


def colour(i): return 0xff000000 | (i * 37 % 256) | (i * 59 % 256) << 8 | (i * 83 % 256) << 16
def key_path(artist, album): return art_file(album_key(artist, album))
def near(a, b, tol=2): return all(abs(((a >> s) & 255) - ((b >> s) & 255)) <= tol for s in (0, 8, 16, 24))


class SongsMachine(ListMachine):
    """The list machine: the text calls, the animator destroy, the stock selection vector and batch delete, the style setter of the pills.
    cf_page / stack: the artist's covers window patch/coverflow.c would report (coverflow_artist_page) and the window stack navigator_back pops
    (window_manager_get_top_window answers the last of it); None: no covers page, the mocks stay the base machine's."""
    cf_page = None
    stack = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.handlers[PSYMS['coverflow_artist_page']] = 'coverflow_artist_page'   # patch/coverflow.c, trapped

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        ret = None
        if name == 'coverflow_artist_page': ret = self.cf_page or 0
        elif name == 'window_manager_get_top_window' and self.stack is not None: ret = self.stack[-1] if self.stack else 0
        elif name == 'navigator_back' and self.stack is not None:
            self.calls.append(('navigator_back',)); self.stack.pop(); ret = 0
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def initial_of(title, kind=None):
    """The Initial byte the stock scan writes: '*' for a digit, the upper-case letter, '#' for the rest (0: never written)."""
    if kind is not None: return kind
    if title in INITIAL: return INITIAL[title]
    c = title[:1]
    return '*' if c.isdigit() else c.upper() if c.isascii() and c.isalpha() else '#'


def make_song(m, title, artist='Artist 0', album='Album 0', initial='auto', path=None, rid=1, big=False):
    ini = initial_of(title) if initial == 'auto' else initial
    if big:
        r = m.malloc(REC_SIZE); m.u.mem_write(r, bytes(REC_SIZE))
        def s(text):
            a = m.malloc(len(text.encode()) + 1); m.u.mem_write(a, text.encode() + b'\0'); return a
        m.setword(r + O['REC_ID'], rid); m.setword(r + O['REC_TYPE'], 8)
        for off, text in ((O['REC_PATH'], path or f'/mnt/mmc/m/{rid}.flac'), (O['REC_TITLE'], title), (O['REC_ALBUM'], album), (O['REC_ARTIST'], artist), (O['REC_NAME'], f'{rid}.flac')):
            m.setword(r + off, s(text))
    else:
        r = m.record(album=album, artist=artist, path=path or f'/mnt/mmc/m/{rid}.flac', title=title, name=f'{rid}.flac', rid=rid)
    if ini: m.u.mem_write(r + O['REC_INITIAL'], bytes([ord(ini) if isinstance(ini, str) else ini]))
    return r


def songs_machine(songs, sort=0, albums=(), cached=True, window=0x20001000, big=False, cover_missing=()):
    """The page's widgets as widget structs (window > list_view > scroll_view > view_grid, and the rail, for demo's own widget_to_local), the library's songs
    [(title, artist, album, initial)], and a cover file for every album (those in cover_missing excepted)."""
    m = SongsMachine()
    m.window = window
    m.load_image = 0
    for w in WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.images = {'p_default': (24, 24, bytes((0x40, 0x40, 0x40, 255)) * (24 * 24)), 'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676),
                'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)}
    m.setword(SORT_FLAG, sort)
    m.setword(SEL_VEC, m.alloc(8))
    m.lib = {}
    recs = []
    for i, sp in enumerate(songs):
        title, artist, album, ini = (list(sp) + [None] * 4)[:4] if not isinstance(sp, str) else (sp, None, None, None)
        artist, album = artist or f'Artist {i % 5}', album or f'Album {i % 5}'
        recs.append(make_song(m, title, artist, album, 'auto' if ini is None else ini, rid=i + 1, big=big))
        if cached and (artist, album) not in m.lib and (artist, album) not in cover_missing:
            p = key_path(artist, album); m.present.add(p); m.files[p] = 4096
            m.images['file://' + p] = (24, 24, struct.pack('<I', colour(len(m.lib))) * (24 * 24))
        m.lib.setdefault((artist, album), len(m.lib))
    m.songs = recs
    m.class_lists[ALL] = recs
    m.class_lists[O['CLASS_ALBUMS']] = [m.record(album=al, artist=ar, path=f'/mnt/mmc/lib/{n}.flac', rid=900 + n) for (ar, al), n in m.lib.items()] if not big else []
    for a, ar_al in albums: m.class_lists[O['CLASS_ALBUMS']].append(a)
    m.present.update(r for r in [f'/mnt/mmc/m/{i + 1}.flac' for i in range(len(recs))])
    m.stock_songlist = True
    win, lv, sv, view, rail = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_grid'], Machine.widget(m, 'sg_rail')
    m.u.mem_write(sv, bytes(0x180)); m.u.mem_write(rail, bytes(0x80))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['songs_scrollview'] = sv
    for off, v in ((0, RAIL_X), (4, 50), (8, RAIL_W), (0xc, VIEW_H), (0x44, win)): m.setword(rail + off, v)
    for off, v in ((4, 0), (8, 320), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
    m.setword(m.widgets['label_title'] + 8, 64)
    m.mem_geometry, m.live_scroll = True, frozenset({sv, rail})
    for n, t in (('btn_play', 'Play'), ('btn_shuffle', 'Shuffle'), ('sg_add', 'Add to Playlist'), ('sg_del', 'Delete')): m.wtext[m.widgets[n]] = t   # the texts the asset gives them
    m.sv, m.rail, m.view = sv, rail, view
    return m


def open_page(m):
    m.call(PSYMS['songs_open'], count=900000000)
    return list(m.calls)


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts, styles, fills) of that frame, the canvas where the scroll_view leaves it."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['sg_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(m.texts), list(m.text_styles), list(m.fills)


def rail_paint(m):
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['sg_on_rail_paint'], a0=0, a1=ev, count=40000000)
    return list(m.blits), list(m.texts), list(m.text_styles)


def tick(m):
    m.call(PSYMS['sg_on_load'], count=80000000)
    return list(m.calls)


def settle(m, limit=300):
    """The loader's timer fires until it stops re-arming; the decodes of a tick (at most one), then a paint."""
    most = 0
    for _ in range(limit):
        calls = tick(m)
        most = max(most, sum(1 for c in calls if c[0] == 'widget_load_image' and c[1] not in ('p_default', 'unselect', 'selected')))
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['sg_on_load'] for c in calls):
            m.most_per_tick = most
            return paint(m)
    raise AssertionError('the page never finished loading')


def scroll_to(m, v):
    """The scroll_view's offset to v, and the page told as the stock setter's EVT_SCROLL tells it."""
    m.setword(m.sv + SC_YOFF, v & 0xffffffff)
    fn, ctx = m.bound[(m.sv, O['EVT_SCROLL'])]
    m.call(fn, a0=ctx, a1=0, count=80000000)


def off_of(m): return m.s32(m.sv + SC_YOFF)


def pixel(m, bmp, x, y):
    data, w, h = m.bitmaps[bmp]
    return struct.unpack('<I', m.u.mem_read(data + (y * w + x) * 4, 4))[0]


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def touch(m, kind, x, y, fn, t=1000):
    return m.touch(kind, x, y, t, fn=fn)


def tap(m, x, y, dx=0, dy=0):
    """A tap on the content view at content-view point (x, y) (window coordinates of the list: y counted from the list's top, the scroll offset not included)."""
    touch(m, 'down', x, SCREEN_Y0 + y, 'sg_on_down')
    touch(m, 'up', x + dx, SCREEN_Y0 + y + dy, 'sg_on_up', 1080)
    return list(m.calls)


def click(m, name):
    m.click(name, count=900000000)
    return list(m.calls)


class Layout:
    """The model of the page's geometry from the letters of the songs (the payload's, written again)."""
    def __init__(self, letters, sections=True, top=TOP):
        self.top = top
        self.n = len(letters)
        self.secs = []
        if sections and letters:   # the non-decreasing labelling (rank "#" 0, A..Z 1..26) with the most songs under their own letter; a tie starts a section late
            ranks = [0 if c == '#' else ord(c) - 64 for c in letters]
            best, came = [[0] * 27], []          # best[i][r]: the most right labels of songs < i with the last label <= r
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
            self.right = best[-1][26]
            self.secs = [(i, '#' if l == 0 else chr(64 + l)) for i, l in enumerate(labels) if i == 0 or l != labels[i - 1]]

    def hdr_y(self, s): return self.top + s * HDR + self.secs[s][0] * ROW
    def sec_of(self, i): return max(k for k, (st, _) in enumerate(self.secs) if st <= i)
    def row_y(self, i): return self.top + ((self.sec_of(i) + 1) * HDR if self.secs else 0) + i * ROW
    def content(self, pad=0): return self.top + len(self.secs) * HDR + self.n * ROW + FOOT + pad


RAIL_P, RAIL_ITEMS, RAIL_DOT, RAIL_DISC = O['SG_RAIL_PITCH'], O['SG_RAIL_ITEMS'], O['SG_RAIL_DOT'], O['SG_RAIL_DISC']


def rail_geom(n, rh=VIEW_H):
    """The compact rail's model (patch/songs.c sg_rail_plan; the stock page's index shows A F K P U Z with dots between): (the sections whose letters are drawn,
    whether a dot sits between two letters, the drawn height, y of the first item in the rail). At most RAIL_ITEMS items: the letters of all the sections, else
    every k-th (the first and the last kept) with a dot between."""
    if n <= RAIL_ITEMS: secs = list(range(n))
    else:
        for k in range(2, n):
            secs = list(range(0, n - 1, k))
            if len(secs) > 1 and n - 1 - secs[-1] < (k + 1) // 2: secs.pop()
            secs.append(n - 1)
            if 2 * len(secs) - 1 <= RAIL_ITEMS: break
    dots = len(secs) < n
    span = (2 * len(secs) - 1 if dots else len(secs)) * RAIL_P
    return secs, dots, span, (rh - span) // 2


def rail_at(n, i, rh=VIEW_H):
    """The window y of the middle of section i's share of the drawn span (a finger there is section i)."""
    secs, dots, span, y0 = rail_geom(n, rh)
    return SCREEN_Y0 + y0 + int((i + 0.5) * span / n)


RAIL_PAD, RAIL_TEXT_W, RAIL_X_C = O['SG_RAIL_PAD'], O['SG_RAIL_TEXT_W'], O['SG_RAIL_CX'] - O['SG_RAIL_X']   # RAIL_X_C: the dots' x (the drawn column's centre) in the rail's coordinates


def rail_geometry(m): return tuple(m.props.get((m.rail, k), v) for k, v in zip('xywh', (RAIL_X, 50, RAIL_W, VIEW_H)))   # what the payload's widget_move / widget_resize left


def dot_boxes(fills):
    """(x, y, w, h) of each dot: its two fills (the cross that cuts the corners) in paint order."""
    return [(min(a[1], b[1]), min(a[2], b[2]), max(a[1] + a[3], b[1] + b[3]) - min(a[1], b[1]), max(a[2] + a[4], b[2] + b[4]) - min(a[2], b[2])) for a, b in zip(fills[::2], fills[1::2])]


def rail_font():
    from stb_raster import StbFont
    return StbFont(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))


def rail_metrics_of():
    """(ink2, dx) from the tree's font, as pod.py writes them into stock.h (the payload under test was built with the same)."""
    return pod_ui.rail_metrics(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))


def rail_ink(font, ch, rect, px=12, floor=64):
    """((top, bottom), (left, right)) of the ink of ch drawn by canvas_draw_text_in_rect into rect = (x, y, w, h) with the centring style: x = rect.x + (rect.w - lw) / 2
    (integer, lw the measured width: truncated advances + 1 px per glyph), the 12 px text box (rect.h - px) / 2 below the rect's top. Measured on the stb mask of the
    glyph (pixels of 25 % coverage and up), not on the font's metrics: bottom and right exclusive."""
    mask, ox, oy, lw = font.mask(ch, px)
    pix = mask.load()
    pts = [(x - ox, y - oy) for y in range(mask.height) for x in range(mask.width) if pix[x, y] >= floor]
    left, top = rect[0] + (rect[2] - lw) // 2, rect[1] + (rect[3] - px) // 2
    return (top + min(p[1] for p in pts), top + max(p[1] for p in pts) + 1), (left + min(p[0] for p in pts), left + max(p[0] for p in pts) + 1)


def letters_of(titles): return ['#' if initial_of(t) in '*#' else initial_of(t) for t in titles]


# in the stock Title order: symbols, digits ('*'), then the letters, a CJK title under its pinyin initial (春 -> C, INITIAL below)
TITLES = ['(Sittin\' On) The Dock', '1979', '99 Luftballons', 'Abbey Road', 'Aja', 'All Blues', 'Blue in Green', 'Bohemian Rhapsody', 'Come Together', 'Creep', '春よ、来い',
          'Dreams', 'Hotel California', 'Karma Police', 'Let It Be', 'Money', 'Take Five', 'Thriller', 'Zombie']
INITIAL = {'春よ、来い': 'C'}


def ui(): return awtk_ui.parse(open(UI, 'rb').read())


def asset_tests(ctx):
    """The menu row and the sort labels; 1. the asset: navbar, pills, rail, bubble, bar, sort card, glyphs."""
    expect, page = ctx.expect, ctx.page
    row = next(i for i, r in enumerate(page.rows) if r.label == 'Songs')
    expect(page.rows[row].action == pod_pages.ACT_SONGS == O.get('ACT_SONGS', 18) and pod_pages.SONGS in pod_pages.PAGES and pod_pages.SONGS.key == 'm1plus_songs',
           'the menu\'s Songs row opens our page (ACT_SONGS), which is in the page table')
    expect(pod_pages.SORT_MENU == ('sort_alphabet', 'sort_filename', 'sort_format', 'sort_time_desc', 'sort_time_asc') and O['SG_SORT_ROWS'] == 5,
           'the sort card lists the stock sort dialog\'s five labels in sort_flag order')

    # 1. The asset
    tree = ui()
    f = tree.find
    expect([(f(n).x, f(n).w, f(n).h) for n in ('btn_search', 'btn_sort', 'btn_select', 'btn_backtoplayer')] == [(122, 46, 50), (168, 46, 50), (214, 46, 50), (260, 60, 50)]
           and O['NAV_SEARCH_X'] == pod_ui.NAV_SEARCH_X == 122, 'the navbar: Search 122, Sort 168, Select 214 (46 wide, the stock Songs page\'s order), Now Playing 260')
    expect([f(n).get('style:normal:icon') for n in ('btn_search', 'btn_sort', 'btn_select', 'btn_backtoplayer')] == ['pod_nav_search', 'pod_nav_songsort', 'pod_nav_select', 'ah_nav_play']
           and all(f(n).get('style') == 'img_btn_style' for n in ('btn_search', 'btn_sort', 'btn_select')), 'they are the glass capsule\'s pieces; Now Playing is its right cap')
    cfb = f('btn_coverflow')
    expect((cfb.x, cfb.w, cfb.h) == (O['NAV_CF_X'], 46, 50) and cfb.get('style:normal:icon') == 'pod_nav_coverflow' and cfb.get('visible') == 'false' and cfb.get('sensitive') == 'false',
           'the artist\'s songs Cover Flow button: the Albums page\'s left-cap glyph at 168, built hidden and insensitive (patch/songs.c shows it for an artist\'s songs only)')
    lt = f('label_title')
    expect((lt.x, lt.w) == (58, 64) and lt.get('visible') == 'false' and lt.x + lt.w == 122 and O['NAV_TITLE_X'] == 58, 'the small title starts at x 58, ends at the capsule (122) and starts hidden')
    sa = f('btn_selall')
    expect(sa.get('visible') == 'false' and sa.get('sensitive') == 'false' and sa.type == 'button' and sa.x == O['SG_SELALL_X'] and sa.x + sa.w == 312 and sa.x >= lt.x + 142,
           'Select All is a text button at the right, hidden and insensitive until select mode')
    lv, sv, grid, bar = f('songs_listview'), f('songs_scrollview'), f('view_grid'), f('scroll_bar_m')
    expect(lv.type == 'list_view' and sv.type == 'scroll_view' and sv in lv.children and bar in lv.children and (lv.x, lv.y, lv.w, lv.h) == (0, 50, 320, VIEW_H) and (sv.w, bar.x) == (310, 310)
           and sv.children == [grid] and grid.type == 'view', 'the body is the library lists\' structure: list_view > scroll_view > one content view, with the stock mobile scroll bar')
    kids = {c.name: c for c in grid.children}
    hn = kids['sg_hname']
    expect(list(kids) == ['sg_title', 'sg_hname', 'btn_play', 'btn_shuffle', 'sg_foot'] and kids['sg_title'].get('style:normal:font_size') == '32' and kids['sg_title'].get('sensitive') == 'false'
           and kids['sg_title'].get('style:normal:text_color') == '#FFFFFF' and (kids['sg_title'].x, kids['sg_title'].y, kids['sg_title'].h) == (12, 0, 52),
           'the content view holds the large title (32 px white, x 12, insensitive), the playlist header\'s name, the two pills and the song count (no count in the header: the footer is the one)')
    expect(hn.type == 'label' and hn.get('visible') == 'false' and hn.get('sensitive') == 'false' and hn.get('style:normal:text_align_h') == 'center'
           and (hn.x, hn.y, hn.w, hn.h) == (O['PH_NAME_X'], O['PH_NAME_Y'], O['PH_NAME_W'], O['PH_NAME_H']) and hn.get('style:normal:font_size') == '22' and hn.get('style:normal:text_color') == '#FFFFFF',
           'a playlist\'s header: the name (22 px white), centred in 286 px (the album page\'s title label), hidden and insensitive until the payload shows it')
    expect(O['PH_TOP'] == O['PH_PILL_Y'] + O['SG_PILL_H'] + (O['SG_TOP'] - O['SG_PILL_Y'] - O['SG_PILL_H']) and O['PH_COVER_Y'] + O['PH_COVER'] < O['PH_NAME_Y']
           and O['PH_PILL_Y'] == O['PH_NAME_Y'] + O['PH_NAME_H'] + 16 and O['PH_COLLAPSE'] == O['PH_NAME_Y'] + O['PH_NAME_H'] and O['PH_COVER_X'] * 2 + O['PH_COVER'] == 320,
           'the header\'s numbers stack: the cover centred, the name, the pills 16 px under it, the rows start as far under the pills as the library\'s do')
    ft = kids['sg_foot']
    expect(ft.type == 'label' and ft.get('sensitive') == 'false' and (ft.x, ft.w, ft.h) == (O['SG_HDR_X'], 320 - 2 * O['SG_HDR_X'], O['SG_FOOT_TEXT_H'])
           and ft.get('style:normal:font_size') == str(O['SG_FOOT_PX']) and ft.get('style:normal:text_color') == '#9C9C9C' and ft.get('style:normal:text_align_h') == 'left',
           'the song count: an insensitive label, 15 px #9C9C9C (the album page\'s meta line), left at x 10 (the covers\' edge), 20 px high')
    for nm, x, icon in (('btn_play', 10, 'sg_play'), ('btn_shuffle', 149, 'sg_shuffle')):
        b = kids[nm]
        expect((b.x, b.y, b.w, b.h) == (x, 52, 129, 40) and b.type == 'button' and b.get('style:normal:bg_color') == '#1E1E1E' and b.get('style:pressed:bg_color') == '#333335'
               and b.get('style:normal:round_radius') == '20' and b.get('style:normal:icon') == icon and b.get('style:normal:font_size') == '18' and b.get('style:normal:text_color') == '#FFFFFF'
               and all(b.get(f'style:{st}:bg_color') not in (None, '#00000000') for st in pod_ui.STATES), f'{nm}: a flat 129 x 40 pill (#1E1E1E, #333335 pressed, radius 20) with its glyph and an 18 px white label')
    pills = [kids['btn_play'], kids['btn_shuffle']]
    expect(kids['btn_play'].x == 10 and kids['btn_shuffle'].x - (kids['btn_play'].x + kids['btn_play'].w) == 10 and max(p.x + p.w for p in pills) == 278,
           'the content pills are 129 wide at x 10 and 149 with a 10 px gap and end at x 278')
    expect((RAIL_X, RAIL_W) == (284, 36) and all(not (p.x < RAIL_X + RAIL_W and p.x + p.w > RAIL_X) for p in pills) and all(RAIL_X - (p.x + p.w) >= 6 for p in pills),
           'no pill reaches the rail\'s touch column (x 284..320): the pills end at 278, 6 px before it (the pills scroll, the rail is fixed)')
    barpills = [c for c in f('sg_bar').children if c.type == 'button']
    expect(f('sg_bar').y == f('sg_rail').y + O['GRID_VIEW_H'] - O['SG_BAR_H'] and max(p.x + p.w for p in barpills) == 310,
           'the select bar\'s pills (145 wide, Add to Playlist needs the room) end at 310 but sit below the rail, which is 336 px high in select mode and ends at the bar\'s top')
    expect(not any('glass' in (c.get('style:normal:bg_image') or '') or c.get('style:normal:bg_image') for c in grid.children), 'no glass on the pills: no bg_image')
    expect(all(tree.find(n).get('visible') == 'false' and tree.find(n).get('sensitive') == 'false' for n in ('sg_bar', 'sg_scrim', 'sg_card', 'label_status', 'label_row_title', 'label_row_sub', 'label_hdr', 'label_rail', 'label_rail_on'))
           and f('sg_bubble').get('visible') == 'false' and f('sg_bubble').get('sensitive') == 'false' and all(f(f'sg_tick{i}').get('visible') == 'false' for i in range(5)),
           'everything shown later (the bar, the scrim and card, the bubble, the ticks, the status and style labels) starts hidden; the ones that must not take touches are insensitive')
    expect(all(f(n).get('sensitive') == 'false' for n in ('sg_bubble', 'sg_bubble_letter', 'sg_bar_line', 'sg_title', 'img_nb_fade')), 'decorative overlays are insensitive (the bubble, the bar\'s hairline, the title, the fade)')
    rail, bub = f('sg_rail'), f('sg_bubble')
    expect((rail.x, rail.y, rail.w, rail.h) == (284, 50, 36, 400) and rail.get('sensitive') is None and rail not in grid.children and tree.children.index(rail) > tree.children.index(lv),
           'the rail is a widget of the window above the list (x 284, 36 wide; the payload sizes it to the drawn span): a touch on it never reaches the scroll_view')
    expect((bub.x, bub.y, bub.w, bub.h) == (105, 195, 110, 110) and bub.get('style:normal:bg_color') == '#262626' and bub.get('style:normal:round_radius') == '14'
           and bub.get('style:normal:border_color') == '#3A3A3A' and bub.get('style:normal:border_width') == '1' and f('sg_bubble_letter').get('style:normal:text_color') == '#FFFFFF'
           and f('sg_bubble_letter').get('style:normal:font_size') == '56', 'the bubble: 110 x 110 centred on the list, #262626, radius 14, a #3A3A3A edge, a 56 px white letter')
    expect(f('label_rail').get('style:normal:font_size') == '12' and f('label_rail').get('style:normal:text_color') == '#EEEEEC' and f('label_rail_on').get('style:normal:text_color') == '#000000'
           and f('label_hdr').get('style:normal:font_size') == '20', 'the rail letters are 12 px #EEEEEC (black on the disc), the headers 20 px')
    barw = f('sg_bar')
    expect((barw.x, barw.y, barw.w, barw.h) == (0, 386, 320, 64) and barw.get('style:normal:bg_color') == '#000000' and f('sg_bar_line').get('style:normal:bg_color') == '#222222'
           and [(c.name, c.x, c.w, c.h) for c in barw.children if c.type == 'button'] == [('sg_add', 10, 145, 40), ('sg_del', 165, 145, 40)]
           and f('sg_add').get('style:normal:icon') == 'sg_listplus' and f('sg_del').get('style:normal:icon') == 'sg_trash' and f('sg_add').get('style:normal:bg_color') == '#1E1E1E',
           'the select bar: 64 px, black with a #222222 hairline, the two flat pills Add to playlist and Delete')
    card, scrim = f('sg_card'), f('sg_scrim')
    items = [f(f'sg_item{i}') for i in range(5)]
    expect((card.x, card.y, card.w) == (43, 52, 268) and all(card.get(f'style:{st}:bg_image') == 'sg_glass' and card.get(f'style:{st}:bg_image_draw_type') == 'patch3_x'
                                                             and card.get(f'style:{st}:bg_color') == '#00000000' and card.get(f'style:{st}:round_radius') is None for st in pod_ui.STATES)
           and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450) and all(scrim.get(f'style:{st}:bg_color') == '#00000082' for st in pod_ui.STATES)
           and scrim.type == 'button' and [(i.y, i.h) for i in items] == [(k * O['PL_ROW_H'], O['PL_ROW_H']) for k in range(5)] and card.h == 5 * O['PL_ROW_H']
           and card.x + card.w == O['PL_CARD_RIGHT']
           and all(i.get(f'style:{st}:bg_color') == ('#FFFFFF10' if st == 'pressed' else '#00000000') and i.get(f'style:{st}:border_width') == ('1' if k else '0')
                   and i.get(f'style:{st}:border_color') == ('#FFFFFF22' if k else '#00000000') for k, i in enumerate(items) for st in pod_ui.STATES)
           and tree.children.index(scrim) > tree.children.index(barw) and tree.children.index(card) == tree.children.index(scrim) + 1 == len(tree.children) - 3,
           'the sort card: the Playlists menu\'s glass (x 43, y 52, 268 wide, sg_glass drawn patch3_x over no fill, rows transparent, 6 % white pressed, 13 % white hairline above every row but the first, right edge PL_CARD_RIGHT), under the 130/255 dim scrim, then only the rows menu (rm_scrim, rm_card)')
    import io, mod_icons
    from PIL import Image
    gw, gh, gr = mod_icons.GLASS_SORT
    raw_ = open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx/sg_glass.png'), 'rb').read()
    gen = mod_icons.glass_image(gw, gh, gr, fill=mod_icons.GLASS_SHEET_FILL)
    g = Image.open(io.BytesIO(raw_)).convert('RGBA')
    third = gw // 3
    expect(raw_ == open(os.path.join(mod_icons.PNG, 'sg_glass.png'), 'rb').read() and same_pixels(raw_, gen) and (gw, gh, gr) == (72, card.h, O['PL_CARD_R'])
           and all(g.getpixel(p)[3] == 0 for p in ((0, 0), (gw - 1, 0), (0, gh - 1), (gw - 1, gh - 1))) and g.getpixel((gw // 2, gh // 2))[3] >= 0.85 * 255
           and all(len({g.getpixel((x, y)) for x in range(third, gw - third)}) == 1 for y in range(gh)),
           f'sg_glass.png is the generator output pixel for pixel ({gw}x{gh}, the card\'s height, r {gr}, the sheet\'s fill), four transparent corners, the middle third the same in every column (patch3_x stretches it exactly)')
    labs = [next(c for c in i.children if c.type == 'hscroll_label') for i in items]
    expect([l.get('tr_text') for l in labs] == list(pod_pages.SORT_MENU) and all(c.get('sensitive') == 'false' for l in labs for c in [l]), 'the card rows carry the five stock keys')
    expect(all(any(c.type == 'image' and c.get('image') == 'sg_tick' for c in i.children) for i in items), 'each row has a tick image (shown on the current order)')
    for nm in ('btn_play', 'btn_shuffle', 'sg_add', 'sg_del', 'btn_selall'):
        expect(os.path.exists(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', (f(nm).get('style:normal:icon') or 'sg_play') + '.png')), f'{nm}\'s glyph is in the tree')

def open_and_paint_tests(ctx):
    """2. The row opens the page, with the fallbacks; 3. opening; 4. paint; 5. the pinned header and the push."""
    expect, page = ctx.expect, ctx.page
    f = ui().find
    row = next(i for i, r in enumerate(page.rows) if r.label == 'Songs')
    on_row, rows0 = PSYMS['on_row'], PSYMS['pod_rows_0']
    m = songs_machine(TITLES)
    m.call(on_row, a0=rows0 + 12 * row, count=900000000)
    expect(('window_open', 'm1plus_songs') in m.calls and 'stock_resume' not in m.names(), 'the Songs row opens our page')
    m = songs_machine(TITLES, window=0)
    open_page(m)
    expect(('stock_resume', '3') in m.calls, 'if the window will not open the row opens the stock Songs page')
    m = songs_machine(TITLES)
    m.widgets.pop('sg_card')
    open_page(m)
    expect(('navigator_back',) in m.calls and not any(c[0] == 'loadLocalClassList' for c in m.calls), 'an asset that is not ours: the page leaves again, nothing read')

    # 3. Opening: the library's albums first, then the songs (both stock queries replace the stock list), the handlers, the sections
    m = songs_machine(TITLES)
    calls = open_page(m)
    queries = [c[1] for c in calls if c[0] == 'loadLocalClassList']
    expect(queries == [O['CLASS_ALBUMS'], ALL], f'opening reads the albums (the cover lookup), then the songs, once each: {queries}')
    expect(all((m.widgets[n], O['EVT_CLICK']) in m.bound for n in ('btn_return', 'btn_backtoplayer', 'btn_search', 'btn_sort', 'btn_select', 'btn_selall', 'btn_play', 'btn_shuffle', 'sg_add', 'sg_del', 'sg_scrim',
                                                                    'sg_item0', 'sg_item1', 'sg_item2', 'sg_item3', 'sg_item4'))
           and (m.view, O['EVT_AFTER_PAINT']) in m.bound and (m.rail, O['EVT_AFTER_PAINT']) in m.bound and (m.window, O['EVT_WINDOW_TO_FG']) in m.bound
           and all((m.rail, O[e]) in m.bound for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_MOVE', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'))
           and all((m.sv, O[e]) in m.bound for e in ('EVT_SCROLL', 'EVT_SCROLL_END')), 'the buttons, the paints, the rail\'s touch events and the scroll events are bound')
    lay = Layout(letters_of(TITLES))
    expect([c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1][2:] == (320, lay.content()) and m.props[(m.sv, 'virtual_h')] == lay.content(),
           f'the content is {lay.content()} px: {TOP} + {len(lay.secs)} headers x {HDR} + {len(TITLES)} rows x {ROW} + the count\'s {FOOT}; the scroll_view is told')
    foot = m.widgets['sg_foot']
    at = (m.props.get((foot, 'x')), m.props.get((foot, 'y')))
    expect(m.wtext[foot] == f'{len(TITLES)} songs' and at == (O['SG_HDR_X'], lay.content() - FOOT + O['SG_FOOT_GAP']),
           f'the song count under the last row: "{len(TITLES)} songs", {O["SG_FOOT_GAP"]} px below it, at x {O["SG_HDR_X"]} ({m.wtext.get(foot)!r} at {at})')
    expect(vis(m, 'sg_rail') == (1, 1) and vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status') == (0, 0) and not any(c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] in (m.widgets['sg_bar'], m.widgets['btn_selall']) for c in m.calls),
           f'the list and the rail show, the status line is hidden; the bar and Select All stay as the asset has them (hidden): {[vis(m, n) for n in ("sg_rail", "view_grid", "label_status")]}')
    expect(not [c for c in m.calls if c[0] == 'widget_load_image' and c[1] not in ('p_default', 'unselect', 'selected')] and not any(c[0] == 'deque_at_oob' for c in m.calls),
           'no cover is decoded in the open (the placeholder and the two marks only)')
    expect(m.wtext[m.widgets['label_title']] == 'Songs', 'the title says Songs')
    expect(m.word(G_CLASS) == ALL, 'the browsing class is the Songs page\'s, as allmusic_page_init leaves it')
    # the letters: '#' (digits '*' and symbols '#') first, then A.., the CJK title under its pinyin initial C
    expect([l for _, l in lay.secs] == ['#', 'A', 'B', 'C', 'D', 'H', 'K', 'L', 'M', 'T', 'Z'] and [s for s, _ in lay.secs] == [0, 3, 6, 8, 11, 12, 13, 14, 15, 16, 18], 'the model: 11 sections, the CJK title in C')

    # 4. Paint: headers, rows, texts, the pinned header
    blits, texts, styles, fills = settle(m)
    expect(m.most_per_tick <= 1, f'at most one cover decoded per tick ({m.most_per_tick})')
    covers = [b for b in blits if b[2][2] == O['LIST_ART']]
    rows_in = [i for i in range(len(TITLES)) if lay.row_y(i) < VIEW_H and lay.row_y(i) + ROW > 0]
    expect(sorted(b[2][1] for b in covers) == [lay.row_y(i) + O['LIST_ART_Y'] for i in rows_in] and all(b[2][0] == 10 and b[2][3] == min(52, VIEW_H - b[2][1]) for b in covers),
           f'a 52 px cover at (10, row + LIST_ART_Y) for each row in view ({len(rows_in)}): {sorted(b[2][1] for b in covers)} vs {[lay.row_y(i) + O['LIST_ART_Y'] for i in rows_in]}')
    tx = {t: r for t, r in texts}
    titles = [(t, r) for t, r in texts if t in TITLES or t.endswith('…')]
    expect(all(r[0] == TEXT_X and r[2] == TEXT_END - TEXT_X == 222 and r[3] == 24 for t, r in titles) and
           all(tx[TITLES[i]][1] == lay.row_y(i) + O['LIST_TITLE_Y'] for i in rows_in if TITLES[i] in tx),
           'a title at (74, row + LIST_TITLE_Y) in a 222 x 24 rect: from x 74 to 296 (the rail\'s touch column starts there)')
    sub = [(t, r) for t, r in texts if t.startswith('Artist')]
    expect(sub and all(r[0] == TEXT_X and r[2] == 222 and r[3] == 20 for t, r in sub) and all(s == 'label_row_sub' for (t, _), s in zip(texts, styles) if t.startswith('Artist')),
           'the artist at (74, row + LIST_SUB_Y), 222 x 20, in the 18 px #AAAAAA style')
    expect(all(s == 'label_row_title' for (t, _), s in zip(texts, styles) if t in TITLES) and all(s == 'label_hdr' for (t, _), s in zip(texts, styles) if len(t) == 1),
           'titles in the 21 px style, header letters in the 20 px one')
    hdr_texts = [(t, r) for t, r in texts if len(t) == 1]
    seen_secs = [s for s in range(len(lay.secs)) if lay.hdr_y(s) >= 0 and lay.hdr_y(s) + HDR <= VIEW_H]
    expect([(t, r[0], r[1]) for t, r in hdr_texts[:len(seen_secs)]] == [(lay.secs[s][1], 10, lay.hdr_y(s)) for s in seen_secs],
           'a header letter at x 10 on each header in view (20 px, the band\'s top)')
    # the header is the Recently Played shelf's (pod_ui.SH_HEAD_*: 20 px white, x 10, on the page's black): the letter alone, no band, no hairline
    expect(f('label_hdr').get('style:normal:text_color') == pod_ui.SH_TITLE_RGB == '#FFFFFF' and f('label_hdr').get('style:normal:font_size') == str(pod_ui.SH_HEAD_PX) == '20'
           and O['SG_HDR_X'] == pod_ui.SH_HEAD_X == 10 and O['SG_HDR_BG'] == 0xff000000 and f('label_hdr').get('style:normal:text_align_h') == 'left',
           'the header letter is the shelf header\'s: 20 px #FFFFFF at x 10; the pinned header\'s backing is the page\'s black')
    expect(not [fl for fl in fills if fl[0] in (0xff141414, 0xff222222) and fl[3] == 320] and not [fl for fl in fills if fl[0] == O['SG_HDR_BG']],
           'no band and no hairline under a header in the flow (the only backing is the pinned copy\'s black)')
    rh = [fl for fl in fills if fl[0] == O['LIST_HAIR'] and fl[3] != 320]
    expect(all(h[1] == TEXT_X and h[3] == 222 and h[4] == 1 for h in rh) and sorted(h[2] for h in rh) == sorted(lay.row_y(i) + ROW - 1 for i in rows_in if lay.row_y(i) + ROW - 1 < VIEW_H),
           f'a #222222 hairline under each row from x 74 to the rail: {sorted((h[1], h[2], h[3]) for h in rh)} vs {sorted(lay.row_y(i) + ROW - 1 for i in rows_in)}')
    expect(not any(fl[0] == O['LIST_PRESS'] for fl in fills), 'nothing is pressed at rest')

    # 5. The pinned header and the push; scrolled paint
    for off, want in ((0, None), (lay.hdr_y(2) + 10, (2, 0)), (lay.hdr_y(3) - 14, (2, -(HDR - 14))), (lay.hdr_y(3) + 1, (3, 0))):
        scroll_to(m, off)
        blits, texts, styles, fills = settle(m)
        pin = [fl for fl in fills if fl[0] == O['SG_HDR_BG']]
        if want is None:
            expect(not pin, 'at the top nothing is pinned: no backing')
            continue
        s, y = want
        expect(len(pin) == 1 and pin[0][1] == 0 and pin[0][2] == 0 and pin[0][3] == 320 and pin[0][4] == HDR + y,
               f'offset {off}: the pinned header of section {s}: an opaque black backing across the window, {HDR} px high, cut by the window by {-y} px as the next header pushes it ({pin})')
        letter = [(t, r[1]) for t, r in texts if len(t) == 1]
        if y == 0: expect((lay.secs[s][1], 0) in letter, f'offset {off}: the pinned header\'s letter {lay.secs[s][1]} is drawn at the top')
        else: expect((lay.secs[s][1], y) not in letter, f'offset {off}: a header being pushed up has no letter (it is not wholly inside the window)')
    scroll_to(m, 0)

def touch_tests(ctx):
    """6. Touch: a tap plays the row like the stock handler; a drag, an abort and the gap open nothing; the press fill; Play, Shuffle, the navbar fade; 7. the pills' centring."""
    expect = ctx.expect
    f = ui().find
    lay = Layout(letters_of(TITLES))
    m = songs_machine(TITLES); open_page(m)
    settle(m)
    i = 4
    calls = tap(m, 150, lay.row_y(i) + 30)
    pl = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(pl and m.played[1] == i and m.word(G_CLASS) == ALL and [c for c in calls if c[0] == 'loadSongList'][0][1:] == (f'{i + 1}.flac', 0, ALL)
           and len(m.played[0]) == len(TITLES) and m.played[0] == m.songs,
           'a tap on a row: loadSongList of the shown list, then playing_page at that row')
    for label, dx, dy in (('a drag', 0, 14), ('a slide sideways', 12, 0)):
        expect(not [c for c in tap(m, 150, lay.row_y(2) + 30, dx, dy) if c[0] == 'navigator_to_with_context'], f'{label} plays nothing')
    expect(not [c for c in tap(m, 150, 20) if c[0] == 'navigator_to_with_context'] and not [c for c in tap(m, 150, lay.hdr_y(1) + 10) if c[0] == 'navigator_to_with_context'],
           'a tap on the title block or on a header plays nothing')
    touch(m, 'down', 150, SCREEN_Y0 + lay.row_y(3) + 20, 'sg_on_down')
    _, _, _, fl = paint(m)
    expect(any(f_[0] == O['LIST_PRESS'] and f_[2] == lay.row_y(3) and f_[4] == min(ROW - 1, VIEW_H - lay.row_y(3)) for f_ in fl), f'the row under the finger is filled #333333: {[f_ for f_ in fl if f_[0] == O["LIST_PRESS"]]} (row at {lay.row_y(3)})')
    touch(m, 'abort', 150, SCREEN_Y0 + lay.row_y(3) + 20, 'sg_on_abort')
    _, _, _, fl = paint(m)
    expect(not any(f_[0] == O['LIST_PRESS'] for f_ in fl) and not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'an abort (the scroll_view took a drag) clears it and plays nothing')

    # Play and Shuffle
    click(m, 'btn_play')
    expect(m.played[1] == 0 and len(m.played[0]) == len(TITLES), 'Play: the whole list from its first song')
    m.mode = 0
    calls = click(m, 'btn_shuffle')
    expect(('mclSetPlayMode', 2) in calls and any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [ALL],
           'Shuffle: Shuffle Songs of patch/shuffle.c (stock Shuffle mode, a random song)')
    for before, after in ((0, 0), (1, 0), (2, 0), (3, 3)):
        m = songs_machine(TITLES); open_page(m); m.mode = before
        calls = click(m, 'btn_play')
        expect(m.played[1] == 0 and m.mode == after and (('mclSetPlayMode', after) in calls) == (before != after),
               f'Play from mode {before}: mode {after} (after a Shuffle, Play plays the list in order)')
        m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = songs_machine(TITLES); open_page(m); m.mode = 2
    calls = tap(m, 150, lay.row_y(2) + 30)
    expect(m.played and m.played[1] == 2 and m.mode == 2 and not any(c[0] == 'mclSetPlayMode' for c in calls), 'a row tap keeps the play mode (Shuffle stays Shuffle), as the stock row')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # The navbar's fade (img_nb_fade, built hidden): shown only while the list is scrolled, as the Albums and Playlists pages (at rest it would darken the
    # large title); it stays insensitive; without the widget the page opens and scrolls as before.
    m = songs_machine(TITLES); fade = Machine.widget(m, 'img_nb_fade'); m.props[(fade, 'visible')] = 0
    state = lambda: (m.props.get((fade, 'visible')), m.props.get((fade, 'sensitive'), 0))
    open_page(m); s = [state()]
    scroll_to(m, 1); s.append(state())
    scroll_to(m, 300); s.append(state())
    scroll_to(m, 0); s.append(state())
    expect(s == [(0, 0), (1, 0), (1, 0), (0, 0)], f'the fade is hidden at rest, shown (insensitive) when scrolled, hidden again back at 0 ({s})')
    expect(pod_ui.NB_FADE_NAME == 'img_nb_fade' and f('img_nb_fade').get('visible') == 'false' and f('img_nb_fade').get('sensitive') == 'false', 'the asset builds the fade hidden and insensitive')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = songs_machine(TITLES); open_page(m); scroll_to(m, 300)
    expect(off_of(m) == 300, 'no fade widget: the page opens and scrolls as before')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    m = songs_machine(TITLES); open_page(m)
    m.present.discard('/mnt/mmc/m/1.flac')
    calls = click(m, 'btn_play')
    expect(any(c[0] == 'toast' for c in calls) and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), 'a missing file: the message box, nothing plays')
    m = songs_machine(['Same', 'Same', 'Same']); open_page(m)
    for r in m.songs: m.setword(r + O['REC_NAME'], m.cstr('01.flac'))
    tap(m, 150, Layout(['S', 'S', 'S']).row_y(2) + 20)
    expect(m.played and m.played[1] == 2, 'a duplicate file name (01.flac in every album): the row\'s own index plays, not the first')

    # 7. The pills: the glyph and the label centred as a pair, 8 px apart (the album page's Play all rule)
    m = songs_machine(TITLES); open_page(m)
    sty = [(n, v) for w, n, v in m.styled if w == m.widgets['btn_play']]
    centred = (129 - (16 + 8 + 8 * len('Play'))) // 2 - (40 - 16) // 2
    expect(('normal:margin_left', centred) in sty and ('pressed:margin_left', centred) in sty and ('disable:margin_left', centred) in sty and ('normal:icon_at', 1) in sty
           and ('normal:spacer', (8 - 12) & 0xffffffff) in sty and ('normal:text_align_h', 2) in sty, f'Play: the margin that centres glyph + 8 + label is {centred} px (spacer -4, icon left, text left)')
    sty2 = [(n, v) for w, n, v in m.styled if w == m.widgets['btn_shuffle']]
    expect(('normal:margin_left', (129 - (16 + 8 + 8 * len('Shuffle'))) // 2 - 12) in sty2, 'Shuffle: its own margin, from its own text')
    expect(not any(n.endswith('font_size') for n, _ in sty + sty2), 'labels that fit keep the asset\'s 18 px (no font_size set)')
    # a label too wide beside its glyph (ru "Перемешать": 97 px at 18 px, 93 px of room) steps down to SG_PILL_PX_SMALL and is centred from its new width (86 px)
    m = songs_machine(TITLES)
    shuffle = m.widgets['btn_shuffle']
    m.measure = lambda t: 86 if any(w == shuffle and n == 'normal:font_size' and v == O['SG_PILL_PX_SMALL'] for w, n, v in m.styled) else 97
    open_page(m)
    sty3 = [(n, v) for w, n, v in m.styled if w == shuffle]
    expect(all((f'{s}:font_size', O['SG_PILL_PX_SMALL']) in sty3 for s in ('normal', 'pressed', 'over', 'focused', 'disable'))
           and ('normal:margin_left', max(0, (129 - (16 + 8 + 86)) // 2 - 12)) in sty3,   # (clamped at 0: the glyph's square starts at the pill's edge)
           f'a 97 px label steps down to {O["SG_PILL_PX_SMALL"]} px in every state and is centred from its 86 px ({[x for x in sty3 if x[0] == "normal:margin_left"]})')

def rail_tests(ctx):
    """8. The rail: letters, grab, jump, bubble, disc, the compact index, the dragged finger."""
    expect = ctx.expect
    lay = Layout(letters_of(TITLES))
    m = songs_machine(TITLES); open_page(m); settle(m)
    n = len(lay.secs)
    pitch = RAIL_P
    y0 = (VIEW_H - n * pitch) // 2
    blits, texts, styles = rail_paint(m)
    expect([t for t, _ in texts] == [l for _, l in lay.secs] and all(s == 'label_rail' for s in styles) and not blits
           and [r[1] for _, r in texts] == [RAIL_PAD + k * pitch for k in range(n)] and all(r[2] == RAIL_TEXT_W and r[3] == pitch for _, r in texts),
           f'the rail: one letter per section ({"".join(l for _, l in lay.secs)}), {pitch} px apart from {RAIL_PAD} px down its widget; no disc at rest')
    expect((RAIL_X, RAIL_W) == (284, 36) and O['SG_RAIL_CX'] == 310 and RAIL_PAD == 12 and rail_geometry(m) == (284, 50 + y0 - RAIL_PAD, 36, n * pitch + 2 * RAIL_PAD),
           f'the touch column is x 284..320; the drawn column (letters and dots) is centred on x 310; the widget is the drawn span plus 12 px above and below, centred on the list: {rail_geometry(m)}')
    def rail_touch(kind, k, frac=0.5):
        y = SCREEN_Y0 + y0 + int((k + frac) * pitch)
        return touch(m, kind, 306, y, 'sg_on_rail')
    k = 4
    rail_touch('down', k)
    expect(('widget_grab', m.window, m.rail) in m.calls, 'a touch on the rail grabs it: the moves and the release come wherever they go')
    expect(off_of(m) == min(lay.hdr_y(k), lay.content() - VIEW_H) and ('widget_set_prop_int', m.sv, 'yoffset', min(lay.hdr_y(k), lay.content() - VIEW_H)) in m.calls,
           f'it jumps the list to section {lay.secs[k][1]}\'s header (offset {off_of(m)})')
    expect(vis(m, 'sg_bubble')[0] == 1 and ('widget_set_sensitive', m.widgets['sg_bubble'], 1) not in m.calls and m.wtext[m.widgets['sg_bubble_letter']] == lay.secs[k][1], 'the bubble shows the letter (it is never made sensitive: it takes no touch)')
    blits, texts, styles = rail_paint(m)
    disc = [b for b in blits if b[2][2] == O['SG_RAIL_DISC']]
    ink2 = rail_metrics_of()[0]
    expect(len(disc) == 1 and disc[0][2][1] == RAIL_PAD + k * pitch + (ink2 - RAIL_DISC) // 2 and disc[0][2][0] == 310 - RAIL_X - RAIL_DISC // 2, f'the touched letter sits on the {RAIL_DISC} px disc')
    expect([(t, s) for (t, _), s in zip(texts, styles) if s == 'label_rail_on'] == [(lay.secs[k][1], 'label_rail_on')] and len(texts) == n, 'the touched letter is black, the others stay')
    px = pixel(m, disc[0][0], RAIL_DISC // 2, RAIL_DISC // 2), pixel(m, disc[0][0], 0, 0), pixel(m, disc[0][0], RAIL_DISC // 2, 0)
    expect(px[0] == O['SG_ACCENT'] and px[1] >> 24 == 0 and px[2] >> 24 > 100, f'the disc is #EEEEEC with its corners cut ({[hex(p) for p in px]})')
    rail_touch('move', 9)
    expect(off_of(m) == min(lay.hdr_y(9), lay.content() - VIEW_H) and m.wtext[m.widgets['sg_bubble_letter']] == lay.secs[9][1], 'dragging down to another letter jumps again')
    rail_touch('move', 9, 0.8)
    expect(not any(c[0] == 'widget_set_prop_int' and c[2] == 'yoffset' for c in m.calls), 'moving inside the same letter does nothing')
    touch(m, 'move', 306, SCREEN_Y0 + VIEW_H + 40, 'sg_on_rail')
    expect(off_of(m) == lay.content() - VIEW_H, 'a finger below the rail is the last letter (the end of the list)')
    touch(m, 'move', 306, SCREEN_Y0 - 30, 'sg_on_rail')
    expect(off_of(m) == 0, 'a finger above the rail is the first letter (the top)')
    rail_touch('up', 2)
    expect(('widget_ungrab', m.window, m.rail) in m.calls and vis(m, 'sg_bubble')[0] == 0, 'the release lets go and hides the bubble')
    blits, texts, styles = rail_paint(m)
    expect(not blits and all(s == 'label_rail' for s in styles), 'and the disc and the black letter are gone')
    rail_touch('move', 3)
    expect(not any(c[0] == 'widget_set_prop_int' for c in m.calls), 'a stray move with no touch down does nothing')
    # the stock hit test (window coordinates, the geometry the payload left): a touch on the rail's column within its span plus the 12 px margins reaches the rail, never
    # the scroll_view (so it cannot start a drag); a touch above or below, or left of the column, reaches the list
    mm = songs_machine(TITLES); open_page(mm); settle(mm)
    root = asset_tree(UI)
    node(root, 'view_grid').h = 3000
    node(root, 'sg_rail').x, node(root, 'sg_rail').y, node(root, 'sg_rail').w, node(root, 'sg_rail').h = rail_geometry(mm)
    top, bot = rail_geometry(mm)[1], rail_geometry(mm)[1] + rail_geometry(mm)[3]
    got = [stock_target(mm, root, x, y)[-1] for x in (284, 305, 319) for y in (top, top + RAIL_PAD, (top + bot) // 2, bot - 1)]
    expect(all(g == 'sg_rail' for g in got), f'a touch in the rail\'s column from 12 px above its span to 12 px below hits sg_rail ({set(got)})')
    above = [stock_target(mm, root, x, y)[-1] for x in (284, 305, 319) for y in (top - 1, top - 30, 60)]
    below = [stock_target(mm, root, x, y)[-1] for x in (284, 305, 319) for y in (bot, bot + 30, 440)]
    side = [stock_target(mm, root, x, y)[-1] for x in (270, 283) for y in (top, (top + bot) // 2, bot - 1)]
    expect(set(above + below + side) <= {'view_grid', 'scroll_bar_m'} and 'view_grid' in set(above + below + side),
           f'a tap above or below the rail\'s span (and its margin), or in the 13 px left of the column, reaches the list (the rows, at the far edge the stock scroll bar), never the rail: {set(above + below + side)}')
    mm = songs_machine(TITLES)
    expect(stock_target(mm, root, 150, 300)[-1] == 'view_grid' and stock_target(mm, root, 100, 110)[-1] == 'btn_play' and stock_target(mm, root, 250, 110)[-1] == 'btn_shuffle',
           'and a touch in the list reaches the content, and the pills where they are')

    # 8b. The compact rail (the stock page's index is the image search_icon.png: * A . . F . . K . . P . . U . . Z #, 400 px, 16 wide): at most RAIL_ITEMS items
    #     of RAIL_P px; the letters of all the sections when they fit, else every k-th with a dot between, the first and the last always; a finger maps to ALL sections
    expect(RAIL_ITEMS * RAIL_P <= 260 and RAIL_P == 13 and RAIL_ITEMS == 20 and RAIL_DOT == 4, f'the rail is at most {RAIL_ITEMS} items of {RAIL_P} px ({RAIL_ITEMS * RAIL_P} px: the list is 400)')
    def rail_titles(n): return (['1 Intro'] + [f'{chr(65 + i)} Song' for i in range(26)])[:n]
    for n_sec, want in ((27, '#CFILORUXZ'), (10, '#ABCDEFGHI'), (3, '#AB'), (20, '#ABCDEFGHIJKLMNOPQRS'), (21, '#CFILORT'), (26, '#CFILORUY')):
        ts = rail_titles(n_sec)
        m = songs_machine(ts); open_page(m); settle(m)
        rl = Layout(letters_of(ts))
        secs, dots, span, ry0 = rail_geom(n_sec)
        blits, texts, styles = rail_paint(m)
        got = ''.join(t for t, _ in texts)
        letters = [rl.secs[s][1] for s in secs]
        step = 2 if dots else 1
        expect(len(rl.secs) == n_sec and got == ''.join(letters) and not blits and all(s == 'label_rail' for s in styles), f'{n_sec} sections: the rail draws {"".join(letters)} ({got})')
        expect(got == want, f'{n_sec} sections draw {want}')
        expect(texts[0][0] == rl.secs[0][1] and texts[-1][0] == rl.secs[-1][1], f'{n_sec} sections: the first and the last letter are always drawn')
        dx_of = lambda r: r[0] - (RAIL_X_C - RAIL_TEXT_W // 2)
        expect([r[1] for _, r in texts] == [RAIL_PAD + j * step * RAIL_P for j in range(len(secs))] and all(r[2] == RAIL_TEXT_W and r[3] == RAIL_P and abs(dx_of(r)) <= 1 for _, r in texts),
               f'{n_sec} sections: the letters {step * RAIL_P} px apart from {RAIL_PAD} px down the widget, in 24 px rects centred on the dots\' x (shifted by at most 1 px each)')
        dotr = [fl for fl in m.fills if fl[0] == O['SG_RAIL_DOT_RGB']]
        dboxes = dot_boxes(dotr)
        want_dots = [RAIL_PAD + (2 * j + 1) * RAIL_P + (rail_metrics_of()[0] - RAIL_DOT) // 2 for j in range(len(secs) - 1)] if dots else []
        expect([b[1] for b in dboxes] == want_dots and len(dotr) == 2 * len(want_dots) and all(b[0] == RAIL_X_C - RAIL_DOT // 2 and b[2] == RAIL_DOT and b[3] == RAIL_DOT for b in dboxes),
               f'{n_sec} sections: {len(want_dots)} dots of {RAIL_DOT} px, one between two letters (none when every letter is drawn)')
        expect(span == (2 * len(secs) - 1 if dots else len(secs)) * RAIL_P and span <= RAIL_ITEMS * RAIL_P and ry0 == (VIEW_H - span) // 2 and VIEW_H - span - ry0 - ry0 in (0, 1) and (n_sec < 21 or ry0 >= 70)
               and rail_geometry(m) == (284, 50 + ry0 - RAIL_PAD, 36, span + 2 * RAIL_PAD),
               f'{n_sec} sections: {span} px tall, {ry0} px above and {VIEW_H - span - ry0} below (centred on the list); the widget x 284, 36 wide, {span + 2 * RAIL_PAD} high from y {50 + ry0 - RAIL_PAD}')
        # alignment, measured on the font's own ink (the stb mask of the tree's default.ttf at 12 px), the text placed as AWTK's canvas_draw_text_in_rect does
        font = rail_font()
        inks = [rail_ink(font, t, r) for t, r in texts]
        worst_x = max(abs((lo + hi) / 2 - RAIL_X_C) for _, (lo, hi) in inks)
        expect(worst_x <= 0.5, f'{n_sec} sections: every letter\'s ink is centred on the dots\' x {RAIL_X_C} within 0.5 px (worst {worst_x})')
        if dots:
            expect(all((b[0] + b[0] + b[2]) / 2 == RAIL_X_C for b in dboxes), f'{n_sec} sections: the dots are centred on x {RAIL_X_C}')
            gaps = [(b[1] - inks[j][0][1], inks[j + 1][0][0] - (b[1] + b[3])) for j, b in enumerate(dboxes)]
            expect(len(gaps) == len(secs) - 1 and all(abs(a - c) <= 1 and a >= 5 for a, c in gaps), f'{n_sec} sections: the ink gap above each dot equals the gap below within 1 px ({sorted(set(gaps))})')
    # the dragged finger reaches every section, in order, whatever the letters drawn
    n_sec = 27
    ts = rail_titles(n_sec); m = songs_machine(ts); open_page(m); settle(m)
    rl = Layout(letters_of(ts))
    secs, dots, span, ry0 = rail_geom(n_sec)
    seq, offs = [], []
    for y in range(SCREEN_Y0 + ry0 - 6, SCREEN_Y0 + ry0 + span + 7):
        touch(m, 'down' if y == SCREEN_Y0 + ry0 - 6 else 'move', 306, y, 'sg_on_rail')
        seq.append(m.wtext[m.widgets['sg_bubble_letter']]); offs.append(off_of(m))
        if y == rail_at(n_sec, 2):   # section 2's share of the span (B, not drawn): the disc is only on a drawn letter
            blits, texts, styles = rail_paint(m)
            expect(not [b for b in blits if b[2][2] == RAIL_DISC] and not [1 for s in styles if s == 'label_rail_on'] and m.wtext[m.widgets['sg_bubble_letter']] == rl.secs[2][1],
                   'a section whose letter is not drawn (B) has the bubble but no disc and no black letter')
    order = [[l for _, l in rl.secs].index(c) for c in seq]
    expect(order[0] == 0 and order[-1] == n_sec - 1 and order == sorted(order) and sorted(set(order)) == list(range(n_sec)),
           f'a finger moving down the rail visits all {n_sec} sections in order (above the span is the first, below the last)')
    expect(offs == sorted(offs) and len(set(offs)) >= 20, 'and the list offset only grows')
    for i in range(n_sec):
        touch(m, 'move', 306, rail_at(n_sec, i), 'sg_on_rail')
        expect(m.wtext[m.widgets['sg_bubble_letter']] == rl.secs[i][1] and off_of(m) == (min(rl.hdr_y(i), rl.content() - VIEW_H) if i else 0),
               f'the middle of section {i}\'s share of the span shows {rl.secs[i][1]} and jumps to its header')
    for i in (secs[1], secs[-2]):
        touch(m, 'move', 306, rail_at(n_sec, i), 'sg_on_rail')
        blits, texts, styles = rail_paint(m)
        expect(len([b for b in blits if b[2][2] == RAIL_DISC]) == 1 and [t for (t, _), s in zip(texts, styles) if s == 'label_rail_on'] == [rl.secs[i][1]],
               f'a drawn letter ({rl.secs[i][1]}) takes the disc and the black ink when the finger is on its section')
        dsc = [b for b in blits if b[2][2] == RAIL_DISC][0][2]
        (it, ib), (il, ir) = rail_ink(rail_font(), *[(t, r) for (t, r), s in zip(texts, styles) if s == 'label_rail_on'][0])
        expect(abs(dsc[0] + RAIL_DISC / 2 - (il + ir) / 2) <= 0.5 and abs(dsc[1] + RAIL_DISC / 2 - (it + ib) / 2) <= 0.5,
               f'the disc behind {rl.secs[i][1]} is centred on the letter\'s ink (disc centre {dsc[0] + RAIL_DISC / 2}, {dsc[1] + RAIL_DISC / 2}; ink centre {(il + ir) / 2}, {(it + ib) / 2})')
    touch(m, 'up', 306, rail_at(n_sec, 26), 'sg_on_rail')

def order_search_and_stale_tests(ctx):
    """9. The plain list of any other order, strays in the Title order; 10. the Initial byte; 11. the sort card; 12. Search; 13. the stock list replaced under the page."""
    expect = ctx.expect
    lay = Layout(letters_of(TITLES))
    m = songs_machine(TITLES, sort=1)
    open_page(m)
    plain = Layout(letters_of(TITLES), sections=False)
    expect(m.props[(m.sv, 'virtual_h')] == plain.content() == TOP + len(TITLES) * ROW + FOOT and vis(m, 'sg_rail') == (0, 0), 'sort_flag 1 (file name): a plain list, TOP + rows x 64, and no rail')
    blits, texts, styles, fills = settle(m)
    expect(not [t for t, _ in texts if len(t) == 1] and not [fl for fl in fills if fl[0] == O['SG_HDR_BG']] and any(t == TITLES[0] for t, _ in texts), 'no header, no pinned backing')
    expect(dict(texts)[TITLES[0]][1] == TOP + O['LIST_TITLE_Y'] and dict(texts)[TITLES[1]][1] == TOP + ROW + O['LIST_TITLE_Y'], 'rows start at the top block\'s end, one every 64 px')
    # The device case (V2.1oGS showed no headers and no rail): the stock Title order sorts by the whole title, the Initial is the scan's first surviving character,
    # so the letters only roughly follow the order. Strays (a title placed elsewhere, a symbol after 'z', an accented letter, a dropped kana) must not make the list
    # plain, and one stray must not open a section early (夜 'Y' between C and D would otherwise swallow D and M): the sections are the non-decreasing labelling
    # with the most songs under their own letter, the strays stay in the section around them, the list keeps the stock order.
    rough = [('(Live) Intro', None, None, '#'), ('1979', None, None, '*'), ('Abbey Road', None, None, 'A'), ('The Beatles Song', None, None, 'B'), ('Bohemian', None, None, 'B'),
             ('Aja', None, None, 'A'), ('Creep', None, None, 'C'), ('夜に駆ける', None, None, 'Y'), ('Dreams', None, None, 'D'), ('#1 Crush', None, None, '#'),
             ('Money', None, None, 'M'), ('Zombie', None, None, 'Z'), ('Édith', None, None, '#'), ('ゆめ', None, None, '#')]
    letters = ['#' if t[3] in ('*', '#') else t[3] for t in rough]
    want = Layout(letters)
    m = songs_machine(rough)
    open_page(m)
    expect([(i, c) for i, c in want.secs] == [(0, '#'), (2, 'A'), (3, 'B'), (6, 'C'), (8, 'D'), (10, 'M'), (11, 'Z')] and want.right == 9,
           f'the model: # A B C D M Z, Aja stays in B, 夜 in C, #1 Crush in D, Édith and ゆめ in Z ({want.secs}, {want.right} of 14 under their letter)')
    expect(vis(m, 'sg_rail') == (1, 1) and m.props[(m.sv, 'virtual_h')] == want.content(), f'the page has those 7 sections and the rail (virtual_h {m.props[(m.sv, "virtual_h")]})')
    blits, texts, styles = rail_paint(m)
    expect([t for t, _ in texts] == ['#', 'A', 'B', 'C', 'D', 'M', 'Z'], f'the rail\'s letters: {[t for t, _ in texts]}')
    scroll_to(m, want.hdr_y(4))
    blits, texts, styles, fills = settle(m)
    expect([t for (t, _), s in zip(texts, styles) if s == 'label_hdr'][:1] == ['D'], 'a header is drawn where the model puts it (D)')
    # a list far out of order (40 songs, 37 runs of letters): still sections, the payload's equal to the model's, at most 27
    jumbled = [(f'{chr(65 + (i * 7) % 26)}{i}', None, None, None) for i in range(40)]
    m = songs_machine(jumbled)
    open_page(m)
    jl = Layout([t[0][0] for t in jumbled])
    blits, texts, styles = rail_paint(m)
    expect(vis(m, 'sg_rail') == (1, 1) and m.props[(m.sv, 'virtual_h')] == jl.content() and [t for t, _ in texts] == [c for _, c in jl.secs] and len(jl.secs) <= 27,
           f'a list in no letter order still gets the model\'s sections, never a plain list ({[c for _, c in jl.secs]})')

    # 10. The Initial byte: '*' and '#' are one section "#"; 0 (never written) takes the title's first letter; lower case folds
    odd = [('9 to 5', None, None, '*'), ('!Bang', None, None, '#'), ('Apple', None, None, 'A'), ('apple pie', None, None, 0), ('Berry', None, None, 0), ('春', None, None, 'C'), ('Zoo', None, None, 'Z')]
    m = songs_machine(odd)
    open_page(m)
    lo = Layout(['#', '#', 'A', 'A', 'B', 'C', 'Z'])
    expect(m.props[(m.sv, 'virtual_h')] == lo.content() and len(lo.secs) == 5, f'"*" and "#" are one section, Initial 0 uses the title, "apple pie" joins A: {len(lo.secs)} sections')
    blits, texts, styles, fills = settle(m)
    expect([t for (t, _), s in zip(texts, styles) if s == 'label_hdr'] == ['#', 'A'], f'the headers in view read # A (then B, C, Z below): {[(t, s) for (t, _), s in zip(texts, styles)]}')
    blits, texts, styles = rail_paint(m)
    expect([t for t, _ in texts] == ['#', 'A', 'B', 'C', 'Z'], 'and so does the rail')

    # 11. The sort card
    m = songs_machine(TITLES); open_page(m)
    expect([c for c in m.calls if c[0] == 'widget_set_visible' and c[1] in [m.widgets[f'sg_tick{i}'] for i in range(5)]][-5:] == [('widget_set_visible', m.widgets[f'sg_tick{i}'], int(i == 0)) for i in range(5)],
           'Title (sort_flag 0) is ticked')
    click(m, 'btn_sort')
    expect(vis(m, 'sg_scrim') == (1, 1) and vis(m, 'sg_card') == (1, 1), 'the Sort button opens the card and its scrim')
    click(m, 'sg_scrim')
    expect(vis(m, 'sg_scrim') == (0, 0) and vis(m, 'sg_card') == (0, 0), 'the scrim closes it')
    click(m, 'btn_sort'); click(m, 'btn_sort')
    expect(vis(m, 'sg_card') == (0, 0), 'the button again closes it')
    click(m, 'btn_sort')
    calls = click(m, 'sg_item0')
    expect(vis(m, 'sg_card') == (0, 0) and not any(c[0] in ('loadLocalClassList', 'write_int_config') for c in calls), 'the current order again closes the card and changes nothing')
    click(m, 'btn_sort')
    m.class_lists[ALL] = list(reversed(m.songs))
    calls = click(m, 'sg_item3')
    expect(m.word(SORT_FLAG) == 3 and ('write_int_config', 3, 'SYSSET', 'SORTSELECT') in calls and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [ALL] and vis(m, 'sg_card') == (0, 0),
           'a row: sort_flag, [SYSSET] SORTSELECT written as the stock dialog\'s row handler does, the list read again, the card closed')
    expect(m.props[(m.sv, 'virtual_h')] == TOP + len(TITLES) * ROW + FOOT and vis(m, 'sg_rail') == (0, 0), 'in Recently Added order the list is plain: no sections, no rail')
    expect(off_of(m) == 0, 'a new order starts at the top')
    click(m, 'btn_sort')
    expect([c for c in m.calls if c[0] == 'widget_set_visible' and c[1] in [m.widgets[f'sg_tick{i}'] for i in range(5)]][-5:] == [('widget_set_visible', m.widgets[f'sg_tick{i}'], int(i == 3)) for i in range(5)],
           'the tick follows the order')
    m.class_lists[ALL] = m.songs
    click(m, 'sg_item0')
    expect(m.word(SORT_FLAG) == 0 and m.props[(m.sv, 'virtual_h')] == lay.content() and vis(m, 'sg_rail') == (1, 1), 'back to Title: the sections and the rail are back')

    # 12. Search: the stock page, no context; the list it leaves is read again when this page is back
    m = songs_machine(TITLES); open_page(m)
    calls = click(m, 'btn_search')
    expect(('navigator_to_with_context', 'search_page', 0) in calls, 'Search opens the stock search page with no context')
    m.setword(SHOWLIST, m.new_deque(m.songs[:3]))   # what the search page leaves in the stock list
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [ALL] and m.props[(m.sv, 'virtual_h')] == lay.content(), 'back from Search the songs are read again')
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(not any(c[0] == 'loadLocalClassList' for c in m.calls), 'a to-foreground with the list still the stock one reads nothing')

    # 13. The stock list replaced under the page: nothing of it is read; a page on top reads it again from a timer, one behind another when it comes back
    m = songs_machine(TITLES); open_page(m); settle(m)
    other = m.new_deque(m.songs[:2])
    m.setword(SHOWLIST, other)
    blits, texts, styles, fills = paint(m)
    expect(not blits and not texts and not any(c[0] == 'deque_at_oob' for c in m.calls) and any(c[0] == 'timer_add' and c[1] == PSYMS['sg_on_stale'] for c in m.calls),
           'a paint with the stock list replaced draws no row, reads no record and arms the stale timer')
    m.top_main = 0
    m.call(PSYMS['sg_on_stale'], count=900000000)
    expect(not any(c[0] == 'loadLocalClassList' for c in m.calls), 'a page that is not on top does not read it from the timer (it reads it when it is back)')
    m.top_main = m.window
    m.call(PSYMS['sg_on_stale'], count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [ALL], 'on top, the timer reads the list again')
    scroll_to(m, 0)
    m.setword(SHOWLIST, m.new_deque(list(m.songs)))   # the same songs in another deque: replaced all the same
    expect(not any(c[0] == 'navigator_to_with_context' for c in tap(m, 150, lay.row_y(2) + 20)), 'a tap on a list the stock query replaced plays nothing (the rows are not the page\'s any more)')

def collapse_and_select_tests(ctx):
    """14. The title collapses into the navbar (and fits in every language); 15. select mode with Delete and Add."""
    expect = ctx.expect
    lay = Layout(letters_of(TITLES))
    m = songs_machine(TITLES); open_page(m)
    lt_h = m.widgets['label_title']
    shown = lambda: [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == lt_h]
    scroll_to(m, 30)
    expect(shown() == [], 'at 30 px the large title is still in view: the navbar has no small title')
    scroll_to(m, O['SG_COLLAPSE'] + 1)
    expect(shown() == [1], 'past SG_COLLAPSE the small title appears')
    scroll_to(m, O['SG_COLLAPSE'] + 20)
    expect(shown() == [], 'and is not set again while it stays')
    scroll_to(m, 0)
    expect(shown() == [0], 'back at the top it goes')
    m = songs_machine(TITLES); m.measure = lambda t: 85 if t else 0; open_page(m)   # a language whose word is wider than the 64 px room (Spanish "Canciones", 85 px)
    scroll_to(m, 100)
    expect([c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['label_title']] == [1] and m.wtext[m.widgets['label_title']].endswith(fitted('…', 0)), 'a title that does not fit its room is cut with an ellipsis and shown all the same')
    m = songs_machine(TITLES); m.widget_on_fail = frozenset({O['EVT_SCROLL']}); open_page(m)
    expect(('widget_set_visible', m.widgets['label_title'], 1) in m.calls, 'without the scroll events the navbar keeps its title (no collapse)')
    lt = ui().find('label_title')
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    wide = [loc for loc in pod_i18n.LOCALES if StbText(font, 20).layout(built[loc]['Songs'])[1] > lt.w]
    expect(wide == ['sp_ES'], f'only Spanish "Songs" is wider than the title\'s 64 px at 20 px: {wide}')
    for key, room, px in [(k, 236 - 18 - 8, 18) for k in pod_pages.SORT_MENU]:
        over = [(loc, StbText(font, px).layout(built[loc].get(key, key))[1]) for loc in pod_i18n.LOCALES if StbText(font, px).layout(built[loc].get(key, key))[1] > room]
        expect(not over, f'the sort card label {key} fits its {room} px row in all 13 languages ({over[:3]})')
    small = O['SG_PILL_PX_SMALL']
    for key, room, px in [(k, O['SG_PILL_W'] - 16 - 8 - 12, 18) for k in ('Play', 'Shuffle')] + [(k, O['SG_BAR_PILL_W'] - 16 - 8 - 12, 18) for k in ('Add to Playlist', 'Delete')]:
        stepped = [loc for loc in pod_i18n.LOCALES if StbText(font, px).layout(built[loc].get(key, key))[1] > room]   # sg_centre_pill steps these down to SG_PILL_PX_SMALL
        over = [(loc, StbText(font, small).layout(built[loc].get(key, key))[1]) for loc in stepped if StbText(font, small).layout(built[loc].get(key, key))[1] > room]
        expect(not over and (key != 'Shuffle' or stepped == ['ru_RU']) and (key == 'Shuffle' or not stepped),
               f'the pill label {key} fits beside its glyph in all 13 languages, at {px} px or stepped down to {small} ({stepped}; over {over[:3]})')
    over = [(loc, StbText(font, 20).layout(built[loc]['%d Selected'].replace('%d', '9999'))[1]) for loc in pod_i18n.LOCALES
            if StbText(font, 20).layout(built[loc]['%d Selected'].replace('%d', '9999'))[1] > O['SG_SELALL_X'] - 58]
    expect(not over, f'"9999 Selected" fits between the title\'s x 58 and Select All in all languages ({over[:3]})')
    over = [(loc, StbText(font, 18).layout(built[loc]['Select All'])[1]) for loc in pod_i18n.LOCALES if StbText(font, 18).layout(built[loc]['Select All'])[1] > 104 - 8]
    expect(not over, f'"Select All" fits its button in all languages ({over[:3]})')
    over = [(loc, w) for loc in pod_i18n.LOCALES for w in [StbText(font, 32).layout(built[loc]['Songs'])[1]] if w > O['SG_TITLE_W']]
    expect(not over, f'the large title fits its label in all languages ({over})')

    # 15. Select mode
    m = songs_machine(TITLES); open_page(m); settle(m)
    n = len(lay.secs)
    n_songs = len(TITLES)
    click(m, 'btn_select')
    expect(all(vis(m, n) == (0, 0) for n in ('btn_search', 'btn_sort', 'btn_select', 'btn_backtoplayer')) and vis(m, 'btn_selall') == (1, 1) and vis(m, 'sg_bar') == (1, 1),
           'Select hides the four buttons, shows Select All and the bar')
    back = m.widgets['btn_return']
    expect(m.props[(back, 'style:normal:icon')] == 'ah_nav_close' and m.props[(back, 'style:pressed:icon')] == 'ah_nav_close_down', 'Back becomes the x (cancel), a glass disc like it')
    expect(m.wtext[m.widgets['label_title']] == '0 Selected' and ('widget_set_visible', m.widgets['label_title'], 1) in m.calls
           and ('widget_resize', m.widgets['label_title'], 150, 22) in m.calls, 'the title reads "0 Selected", from x 58 to Select All')
    expect(('widget_set_sensitive', m.widgets['btn_play'], 0) in m.calls and ('widget_set_sensitive', m.widgets['btn_shuffle'], 0) in m.calls, 'the pills are disabled (their dim style)')
    expect(m.props[(m.sv, 'virtual_h')] == lay.content(O['SG_BAR_H']), 'the content is 64 px longer: the last row scrolls clear of the bar')
    blits, texts, styles, fills = settle(m)
    marks = [b for b in blits if b[2][2] == O['SG_MARK']]
    covers = [b for b in blits if b[2][2] == O['LIST_ART']]
    expect(len(marks) == len(covers) and all(b[2][0] == 9 and b[2][1] == c[2][1] - O['LIST_ART_Y'] + 19 for b, c in zip(marks, covers)) and all(c[2][0] == 40 for c in covers),
           'a 26 px mark at x 9 on each row, the cover at x 40 (30 px right)')
    ttl = [(t, r) for t, r in texts if t in TITLES]
    expect(ttl and all(r[0] == 104 and r[2] == 192 for t, r in ttl), 'and the text from x 104 to 296 (192 px)')
    bits = [b[0] for b in marks]
    expect(len(set(bits)) == 1, 'all unselected: one mark image')
    expect(pixel(m, bits[0], 0, 0) >> 24 == 0 and pixel(m, bits[0], 25, 25) >> 24 == 0 and pixel(m, bits[0], 13, 13) >> 24 == 255 and pixel(m, bits[0], 13, 2) >> 24 >= 128,
           'the mark is cut to its circle (radius 11 in the 26 px square): the corners are transparent, the disc opaque, so no black square shows on a cover')
    off_mark = bits[0]
    tap(m, 150, lay.row_y(1) + 30); tap(m, 150, lay.row_y(3) + 30)
    expect(m.wtext[m.widgets['label_title']] == '2 Selected' and not any(c[0] == 'navigator_to_with_context' for c in m.calls), 'a tap marks a row (the count follows) and plays nothing')
    blits, texts, styles, fills = paint(m)
    marks = {b[2][1]: b[0] for b in blits if b[2][2] == O['SG_MARK']}
    expect(marks[lay.row_y(1) + 19] != off_mark and marks[lay.row_y(3) + 19] != off_mark and marks[lay.row_y(2) + 19] == off_mark, 'the two marked rows show the selected mark')
    expect(not any(f_[0] == O['LIST_PRESS'] for f_ in fills), 'no press fill in select mode')
    tap(m, 150, lay.row_y(1) + 30)
    expect(m.wtext[m.widgets['label_title']] == '1 Selected', 'a second tap unmarks')
    click(m, 'btn_selall')
    expect(m.wtext[m.widgets['label_title']] == f'{n_songs} Selected', 'Select All marks everything')
    click(m, 'btn_selall')
    expect(m.wtext[m.widgets['label_title']] == '0 Selected', 'and again none')
    # Delete: nothing selected -> the stock message; a selection -> confirm, the stock selection vector, batch_delete_file, the message, the list read again
    m.calls = []
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'toast' and c[1] == 'msg_delsongfailed' for c in calls) and not any(c[0] == 'confirm' for c in calls), 'Delete with nothing selected: the stock "failed" message, no dialog')
    tap(m, 150, lay.row_y(1) + 30); tap(m, 150, lay.row_y(5) + 30); tap(m, 150, lay.row_y(6) + 30)
    m.confirm_answer = 0   # No
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'confirm' and c[1] == 'msg_delsong' and c[2] == O['CONFIRM_KIND_DELETE'] for c in calls) and not any(c[0] in ('batch_delete_file', 'select_recordinit') for c in calls),
           'Delete asks with the stock confirm dialog (kind 3, "Delete Song?"); No deletes nothing')
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    list_h = m.word(SHOWLIST)
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(('select_recordinit', n_songs) in calls and [c[1] for c in calls if c[0] == 'set_selectindex'] == [1, 5, 6]
           and bd and bd[0][1:6] == (ALL, list_h, m.word(SEL_VEC), 0, 0) and bd[0][6] == [1, 5, 6], 'Yes (the library only): the stock vector is made as long as the list with the selected rows, then batch_delete_file(0xf001, the shown list, the vector, 0, 0)')
    expect(calls.index(bd[0]) < next(i for i, c in enumerate(calls) if c[0] == 'toast' and c[1] == 'msg_delsongsuccess') and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [ALL],
           'then the stock "Song Deleted" message and the list is read again')
    expect(vis(m, 'sg_bar') == (0, 0) and vis(m, 'btn_search') == (1, 1) and m.props[(back, 'style:normal:icon')] == 'ah_nav_back', 'and select mode is over')
    click(m, 'btn_select'); tap(m, 150, lay.row_y(0) + 30)
    m.confirm_answer = O['CONFIRM_DELETE_FILE']
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][5] == 1 and bd[0][6] == [0], 'the second answer (0x14, also the file) sets the delete-file flag')
    m.confirm_answer = None
    # Add to playlist: the stock picker, the selection in the stock vector, the title and class put back when the window is back
    click(m, 'btn_select')
    calls = click(m, 'sg_add')
    expect(any(c[0] == 'toast' and c[1] == 'msg_addfailed' for c in calls) and not any(c[0] == 'navigator_to_with_context' and c[1] != 'dialog/msginfo_dialog' for c in calls), 'Add with nothing selected: the stock "Adding Failed" message')
    tap(m, 150, lay.row_y(3) + 30); tap(m, 150, lay.row_y(7) + 30)
    m.windows['m1plus_playlists'] = 0   # our picker's page does not open: the stock picker (test/pod/picker.py is ours)
    m.u.mem_write(NAV_TITLE, b'Songs title\0'); m.setword(G_CLASS, 0xf00b); m.setword(pod.DATA['NAVIGATION_STATUS'][0], 1)
    calls = click(m, 'sg_add')
    expect(m.word(pod.DATA['NAVIGATION_STATUS'][0]) == 0, 'the picker is opened with navigation_status 0 (the stock row handler adds only when it is not 1)')
    expect([c[1] for c in calls if c[0] == 'set_selectindex'] == [3, 7] and ('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | ALL) in calls and O['PICKER_ADD'] | ALL == 0x1f001,
           'Add fills the stock selection and opens the stock playlist picker with the add context (1 << 16 | 0xf001)')
    m.u.mem_write(NAV_TITLE, b'Mix\0'); m.setword(G_CLASS, 0xf00b)   # what the picker leaves
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(m.word(G_CLASS) == ALL and m.read_cstr(NAV_TITLE) == 'Songs title' and vis(m, 'sg_bar') == (0, 0) and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [ALL],
           'back from the picker: the browsing class and the title are put back, select mode is over, the list is read again (the add changed its records)')
    # leaving select mode
    click(m, 'btn_select'); tap(m, 150, lay.row_y(1) + 30)
    calls = click(m, 'btn_return')
    expect(vis(m, 'sg_bar') == (0, 0) and not any(c[0] == 'navigator_back' for c in calls) and m.wtext[m.widgets['label_title']] == 'Songs', 'the x leaves select mode (Back does not go back)')
    calls = click(m, 'btn_return')
    expect(('navigator_back',) in calls, 'Back outside select mode goes back')
    click(m, 'btn_select')
    expect(m.wtext[m.widgets['label_title']] == '0 Selected', 'select mode starts with nothing marked')
    # the rail stays in select mode, centred on the shorter list
    p2, sel_h = RAIL_P, VIEW_H - O['SG_BAR_H']
    expect(rail_geometry(m) == (RAIL_X, 50 + (sel_h - n * p2) // 2 - RAIL_PAD, RAIL_W, n * p2 + 2 * RAIL_PAD) and 50 + (sel_h - n * p2) // 2 + n * p2 + RAIL_PAD <= 50 + sel_h,
           f'the rail stays in select mode: the span plus 12 px either side, centred on the list the bar leaves (336 px), ending above the bar: {rail_geometry(m)}')
    blits, texts, styles = rail_paint(m)
    expect([r[1] for _, r in texts] == [RAIL_PAD + k * p2 for k in range(n)], f'its letters {p2} px apart from {RAIL_PAD} px down the widget')

def loader_tests(ctx):
    """16. The loader: one decode a tick, none while the scroll_view moves, the library lookup for a compilation, the placeholder; a coasting list; the background cover build."""
    expect = ctx.expect
    lay = Layout(letters_of(TITLES))
    comp = [('Track A', 'Artist 0', 'Album 0', None), ('Track B', 'Other', 'Album 0', None), ('Track C', 'Lonely', 'Album 9', None)]
    m = songs_machine(comp, cover_missing=[('Other', 'Album 0'), ('Lonely', 'Album 9')])
    open_page(m)
    m.setword(m.sv + 0xa0, 0x101)   # pressed and dragged (SC_PRESSED, SC_DRAGGED bytes)
    calls = tick(m)
    expect(not any(c[0] == 'widget_load_image' for c in calls) and any(c[0] == 'timer_add' and c[1] == PSYMS['sg_on_load'] for c in calls), 'the loader decodes nothing while a finger drags the list, and looks again next tick')
    m.setword(m.sv + 0xa0, 0)
    blits, texts, styles, fills = settle(m)
    cov = sorted([b for b in blits if b[2][2] == 52], key=lambda b: b[2][1])
    want = [colour(0), colour(0), None]
    got = [pixel(m, b[0], 26, 26) if b[0] in m.bitmaps else None for b in cov]
    expect(len(cov) == 3 and near(got[0], want[0]) and near(got[1], want[1]) and got[2] == pixel(m, cov[2][0], 26, 26),
           f'Track B (another artist, the library lists the album under Artist 0) finds the library album\'s cover; Track C with no file shows the placeholder: {[hex(g or 0) for g in got]} vs {[hex(w or 0) for w in want]}, {len(cov)} covers')
    expect(sum(1 for c in m.calls if c[0] == 'widget_load_image' and c[1].startswith('file://')) <= 3, 'at most one decode per song')

    # 16a. A coasting list (the scroll animator running): nothing decodes, and a touch on the rail stops it before it jumps
    m = songs_machine(TITLES); open_page(m)
    an = m.alloc(0x80); m.u.mem_write(an, bytes(0x80)); m.setword(an + 4, m.sv); m.setword(an + 0x28, O['SC_AN_RUNNING']); m.setword(m.sv + O['SC_WA'], an)
    calls = tick(m)
    expect(not any(c[0] == 'widget_load_image' for c in calls) and any(c[0] == 'timer_add' and c[1] == PSYMS['sg_on_load'] for c in calls), 'no decoding while the scroll animator (a fling) runs')
    n_sec = len(lay.secs); pit = RAIL_P; yy = (VIEW_H - n_sec * pit) // 2
    touch(m, 'down', 306, SCREEN_Y0 + yy + 5 * pit + 4, 'sg_on_rail')
    expect(('widget_animator_destroy', an) in m.calls and ('stock_scroll_done', m.sv) in m.calls and m.word(m.sv + O['SC_WA']) == 0
           and m.calls.index(('widget_animator_destroy', an)) < m.calls.index(('widget_set_prop_int', m.sv, 'yoffset', off_of(m))), 'a jump stops the coasting list first (the animator destroyed, the scroll end handler run)')
    touch(m, 'up', 306, SCREEN_Y0 + yy + 5 * pit + 4, 'sg_on_rail')

    # 16b. The background cover build: the songs around the first in view that have no cache file, once each album, nearest first
    m = songs_machine([(f'S{i}', f'Artist {i % 4}', f'Album {i % 4}', None) for i in range(40)], cached=False)
    calls = open_page(m)
    START, POLL = PSYMS['sg_on_build_start'], PSYMS['sg_on_build']
    expect(any(c[0] == 'timer_add' and c[1] == START for c in calls) and 'pthread_create' not in [c[0] for c in calls] and build_state(m)['jobs'] == 0,
           'the open arms a one-shot start timer and starts no worker')
    fired(m, 'sg_on_build_start')
    s, jobs = build_state(m), build_jobs(m)
    expect(count_of(m, 'pthread_create') == 1 and s['running'] == 1 and s['mode'] == 0 and s['total'] == 4 and jobs == [(f'/mnt/mmc/m/{i + 1}.flac', fnv(fnv(O['FNV_SEED'], f'Artist {i}'), f'Album {i}') or 1) for i in range(4)],
           f'one worker, four jobs (an album once, nearest the first in view first): {jobs}')
    expect(any(c[0] == 'timer_add' and c[1] == POLL for c in m.calls), 'the poll timer runs')
    for _ in range(4): tick(m)
    pth = key_path('Artist 1', 'Album 1')
    m.setword(PSYMS['cb'] + 4 * 5, 2); m.present.add(pth); m.files[pth] = 4096
    m.images['file://' + pth] = (24, 24, struct.pack('<I', 0xff123456) * 576)
    new = fired(m, 'sg_on_build')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == POLL] and not [c for c in new if c[0] == 'pthread_join'], 'a poll with the worker running re-arms itself (and lets the tiles that had no file try again)')
    for _ in range(8): tick(m)
    expect(f'file://{pth}' in m.loads, 'and the new cover is decoded')
    m.setword(PSYMS['cb'] + 4 * 5, 4)
    new = fired(m, 'sg_on_build')
    expect([c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] == 0 and not [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'the worker done: joined, the set freed, no more polls')
    calls = tick(m)
    scroll_to(m, 2500)
    expect(any(c[0] == 'timer_add' and c[1] == START for c in m.calls), 'a page that scrolled far from where the build looked starts another')
    m.top_main = m.window
    fired(m, 'sg_on_build_start')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    expect(build_state(m)['orphan'] == 1 and ('pthread_join',) not in m.calls and len(m.bitmaps) == 0, 'closing the page cancels the worker it holds without joining it and frees every bitmap')

def big_library_tests(ctx):
    """17. A library of 20,000 songs: the index, the content height, the clamp, the rail jump, the ring, the cost of opening."""
    expect = ctx.expect
    big_titles = [f'{chr(65 + i * 26 // 20000)}{i:05d}' for i in range(20000)]
    m = songs_machine(big_titles, big=True, cached=False).count()
    m.class_lists[O['CLASS_ALBUMS']] = []
    open_page(m)
    biglay = Layout([t[0] for t in big_titles])
    h = biglay.content()
    expect(h == TOP + 26 * HDR + 20000 * ROW + FOOT and h > 1_280_000 and m.props[(m.sv, 'virtual_h')] == h and [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.view][-1][3] == h,
           f'20,000 songs: the content is {h:,} px (26 sections), the scroll_view is told')
    expect(sum(c[1] for c in m.calls if c[0] == 'calloc' and c[1] == 20000 * 8) == 160000, 'the index is 8 bytes a song (160,000 bytes), not a copy of the list')
    print(f'  opening 20,000 songs: {m.icount:,} payload instructions')
    expect(m.icount < 150_000_000, f'opening a 20,000 song library costs {m.icount:,} instructions')
    # the rail: Z is the last letter; the jump clamps to the end
    n = 26   # (the compact rail: 26 sections are more than it has room for, every section is still reached)
    touch(m, 'down', 306, rail_at(n, 12), 'sg_on_rail')
    expect(off_of(m) == biglay.hdr_y(12) and m.wtext[m.widgets['sg_bubble_letter']] == 'M', f'the rail jumps to M ({off_of(m):,})')
    touch(m, 'move', 306, rail_at(n, 25), 'sg_on_rail')
    expect(off_of(m) == min(biglay.hdr_y(25), h - VIEW_H) and m.wtext[m.widgets['sg_bubble_letter']] == 'Z', f'to Z: the Z header ({off_of(m):,})')
    touch(m, 'up', 306, rail_at(n, 25), 'sg_on_rail')
    scroll_to(m, h + 5000)   # past the end (overscroll)
    blits, texts, styles, fills = paint(m)
    expect(not any(c[0] == 'deque_at_oob' for c in m.calls), 'a list pulled past its end reads no record beyond it')
    scroll_to(m, h - VIEW_H)
    blits, texts, styles, fills = settle(m)
    expect(len(m.bitmaps) <= TILES + 1 + 3 and m.most_per_tick <= 1, f'the bitmaps alive stay within the ring and the placeholder, the disc and the marks ({len(m.bitmaps)})')
    last = [t for t, r in texts if t in big_titles]
    expect(last and last[-1] == big_titles[-1], f'the end of the list paints its last row ({last[-1] if last else None})')
    scroll_to(m, 640_000)
    blits, texts, styles, fills = settle(m)
    expect(blits and all(0 <= b[2][1] < VIEW_H for b in blits if b[2][2] == 52), 'a paint half way down (offset 640,000) draws rows at window coordinates')
    scroll_to(m, 0)
    blits, texts, styles, fills = settle(m)
    expect(any(t == big_titles[0] for t, _ in texts), 'back at the top')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    expect(len(m.bitmaps) == 0, f'closing frees every bitmap ({len(m.bitmaps)} left)')


LISTS = [('Favorites', 'HOME_FAV', 'CLASS_FAV'), ('Recently Added', 'HOME_RECENTADD', 'CLASS_RECENTADD'), ('Recently Played', 'HOME_RECENT', 'CLASS_RECENT'),
         ('Most Played', 'HOME_MOST', 'CLASS_OFTEN'), ('Hi-Res', 'HOME_HIRES', 'CLASS_HIRES')]


def list_machine(titles, cls=None, **kw):
    """songs_machine whose songs are also the list of class cls; the large title full width as in the asset."""
    m = songs_machine(titles, **kw)
    if cls is not None: m.class_lists[cls] = list(m.songs)
    m.setword(m.widgets['sg_title'] + 8, O['SG_TITLE_W'])
    m.setword(m.widgets['sg_hname'] + 8, O['PH_NAME_W'])   # the playlist header's name label, as the asset sizes it
    return m


def fitted(text, room, px=8):
    """sg_fit's result under the machine's measure (px per character): the text, or its longest prefix that fits with the ellipsis (no space before it), as the
    payload's UTF-8 reads back (latin-1 chars)."""
    if px * len(text) > room: text = text[:room // px - 1].rstrip(' ') + '…'
    return text.encode('utf-8').decode('latin-1')


def lists_tests(ctx):
    """17. The other lists on the same page (docs/modules/songs.md "The other lists"): the menu rows (ACT_LIST) and their fallback, the capsule without Sort, a plain
    list in the query's order, the titles cut with an ellipsis, play / Play / Shuffle / Delete with the list's class, a list read again on every return, the empty
    line, and a playlist (the Playlists page's tap): its id in classinfo[1] for every read and play, its name cut on a character."""
    expect, page = ctx.expect, ctx.page
    P = pod_pages
    expect(all(O[h] == getattr(P, h) for _, h, _ in LISTS) and [O[c] for _, _, c in LISTS] == [0xf00a, 0xf009, 0xf007, 0xf008, 0xf002] and P.ACT_LIST == 21,
           'offsets.inc HOME_* are tools/pod_pages.py\'s and the classes the stock Home dispatcher opens for those tiles (docs/modules/addresses.md)')
    expect(all(pod_i18n.key_for(label) in ('hr', label) for label, _, _ in LISTS) and pod_i18n.key_for('Hi-Res') == 'hr',
           'the titles\' keys (patch/songs.c SG_LISTS) are the menu rows\' keys: the label, Hi-Res the stock key hr')
    on_row, rows0 = PSYMS['on_row'], PSYMS['pod_rows_0']
    titles = ['Zed', 'Alpha', 'Mike', 'Bravo', 'Echo', 'Yankee', 'Delta', 'Kilo']   # not in title order: a list keeps its query's order
    lay = Layout(['A'] * len(titles), sections=False)
    for label, home, cls_name in LISTS:
        cls = O[cls_name]
        row = next(i for i, r in enumerate(page.rows) if r.label == label)
        expect(page.rows[row].action == P.ACT_LIST and page.rows[row].arg == O[home], f'the menu\'s {label} row opens the list (ACT_LIST) with its Home tile')
        m = list_machine(titles, cls); m.strings = {'hr': 'Hi-Res'}
        m.setword(m.songs[0] + O['REC_TRACK'], 11)   # REC_TRACK = plays - 1 on the Most Played records (the others' track numbers are never shown)
        m.call(on_row, a0=rows0 + 12 * row, count=900000000)
        calls = m.calls
        queries = [c[1] for c in calls if c[0] == 'loadLocalClassList']
        big, lt = m.widgets['sg_title'], m.widgets['label_title']
        expect(('window_open', 'm1plus_songs') in calls and queries == [O['CLASS_ALBUMS'], cls] and m.word(G_CLASS) == cls,
               f'{label}: our Songs page reads the albums, then class {cls:#x}, and sets the browsing class as allmusic_page_init does ({queries})')
        expect(m.wtext.get(big) == fitted(label, O['SG_TITLE_W']) and m.wtext.get(lt) == fitted(label, 110),
               f'{label}: the large title and the small one (110 px) are the row\'s text, cut with an ellipsis where too wide ({m.wtext.get(big)!r}, {m.wtext.get(lt)!r})')
        expect(vis(m, 'btn_sort') == (0, 0) and ('widget_move', m.widgets['btn_search'], O['NAV_CF_X'], 0) in calls and ('widget_resize', lt, O['NAV_CF_X'] - 58, 22) in calls,
               f'{label}: no Sort; Search (the left cap) moves to Sort\'s slot beside Select, the small title runs from 58 to it')
        blits, texts, styles, fills = settle(m)
        shown = [t for t, r in texts if t in titles]
        expect(vis(m, 'sg_rail')[0] == 0 and len(shown) >= 4 and shown == titles[:len(shown)] and not any(len(t) == 1 for t, r in texts)
               and m.props[(m.sv, 'virtual_h')] == lay.content(), f'{label}: a plain list in the query\'s order, no sections, no rail')
        subs = [t for t, r in texts if 'Artist' in t]
        plays = ['12 plays', '1 play', '1 play', '1 play']
        want = [f'{p} \xb7 Artist {i}' for i, p in enumerate(plays)] if cls == O['CLASS_OFTEN'] else [f'Artist {i}' for i in range(4)]
        expect(subs[:4] == want, f'{label}: the grey line is the artist, on Most Played "N plays \xb7 artist" (REC_TRACK + 1; "1 play" singular) ({subs[:4]!r})')
        calls = tap(m, 150, lay.row_y(2) + 30)
        nav = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
        expect(nav and nav[0][3] == cls and m.played[1] == 2 and m.played[0] == m.songs and [c[3] for c in calls if c[0] == 'loadSongList'] == [cls] and m.word(G_CLASS) == cls,
               f'{label}: a row plays the list from that song with the list\'s class')
        m.call(PSYMS['sg_on_destroy'], count=4000000)

    fav = O['CLASS_FAV']
    m = list_machine(titles, fav); m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000); settle(m)
    lt = m.widgets['label_title']
    m.mode = 2
    calls = click(m, 'btn_play')
    expect(m.played[1] == 0 and m.mode == 0 and ('mclSetPlayMode', 0) in calls, 'Play: the list in order from its first song (Shuffle becomes List play)')
    m.mode = 0
    calls = click(m, 'btn_shuffle')
    nav = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(('mclSetPlayMode', 2) in calls and nav and nav[0][3] == fav and m.played[0] == m.songs and 0 <= m.played[1] < len(titles)
           and not any(c[0] == 'loadLocalClassList' for c in calls), 'Shuffle: this list in the stock Shuffle mode from a random song of it (not Shuffle Songs of the library)')
    calls = click(m, 'btn_sort')
    expect(vis(m, 'sg_card') == (0, 0), 'the Sort handler does nothing on a list (its button is hidden)')
    click(m, 'btn_select')
    expect(all(vis(m, n) == (0, 0) for n in ('btn_search', 'btn_sort', 'btn_select', 'btn_backtoplayer')) and vis(m, 'sg_bar') == (1, 1), 'select mode as on Songs')
    tap(m, 150, lay.row_y(1) + 30); tap(m, 150, lay.row_y(4) + 30)
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1] == fav and bd[0][5] == 0 and bd[0][6] == [1, 4] and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [fav],
           'Delete: batch_delete_file with the list\'s class (the stock removes the songs from that list), then the list is read again')
    m.confirm_answer = None
    expect(vis(m, 'btn_sort') == (0, 0) and vis(m, 'btn_search') == (1, 1) and vis(m, 'btn_select') == (1, 1) and m.props[(lt, 'w')] == O['NAV_CF_X'] - 58
           and m.wtext[lt] == fitted('Favorites', 110), 'leaving select mode brings back Search and Select, not Sort, and the list\'s title in its 110 px')
    click(m, 'btn_select'); tap(m, 150, lay.row_y(2) + 30)
    m.windows['m1plus_playlists'] = 0   # the stock picker (our page does not open)
    calls = click(m, 'sg_add')
    expect(('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | fav) in calls, 'Add opens the stock playlist picker with the list\'s class (1 << 16 | class, as the stock button)')
    m.setword(G_CLASS, 0xf00b)   # what the picker leaves
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(m.word(G_CLASS) == fav and vis(m, 'sg_bar') == (0, 0), 'back from the picker: the list\'s class is put back, select mode is over')
    m.calls = []
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [fav], 'Favourites (and Recently Played, Most Played) are read again when the page is back in front (a play, the star)')
    # The tiles: an unchanged list read again keeps its covers; a changed one drops them; the lists that cannot change while away are not read at all
    def covers(blits): return sorted(b[0] for b in blits if b[2][2] == 52)
    blits, *_ = settle(m)
    before, nloads = covers(blits), len(m.loads)
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    queried = [c[1] for c in m.calls if c[0] == 'loadLocalClassList']
    blits, *_ = settle(m)
    expect(queried == [fav] and len(m.loads) == nloads and covers(blits) == before and before,
           'an unchanged list read again keeps its tiles: no cover decoded again, the same bitmaps drawn')
    m.class_lists[fav] = list(reversed(m.songs))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    blits, *_ = settle(m)
    expect(len(m.loads) > nloads and covers(blits) != before, 'a changed list (another order) drops its tiles and decodes the covers again')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    for cls, nm in ((O['CLASS_RECENTADD'], 'Recently Added'), (O['CLASS_HIRES'], 'Hi-Res')):
        m = list_machine(titles, cls); m.call(PSYMS['songs_open_list'], a0={O['CLASS_RECENTADD']: O['HOME_RECENTADD'], O['CLASS_HIRES']: O['HOME_HIRES']}[cls], count=900000000)
        settle(m); m.calls = []
        m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
        expect(not any(c[0] == 'loadLocalClassList' for c in m.calls), f'{nm}: a list that cannot change while the page is behind is not read again on the way back')
        m.calls = []
        scroll_to(m, O['SG_COLLAPSE'] + 1)
        expect([c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets['label_title']] == [1], f'{nm}: the small title collapses in like the others (cut with an ellipsis to its room)')
        m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = list_machine(titles, fav); m.class_lists[fav] = []; m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000)
    expect(vis(m, 'label_status') == (1, 1) and m.wtext[m.widgets['label_status']] == 'No songs' and vis(m, 'view_grid') == (0, 0), 'an empty list says "No songs"')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = list_machine(titles, fav); m.windows['m1plus_songs'] = 0; m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000)
    expect(('stock_resume', str(O['HOME_FAV'])) in m.calls, 'a window that will not open leaves the stock page of the tile')
    m = list_machine(titles); m.call(PSYMS['songs_open_list'], a0=P.HOME_GENRE, count=900000000)
    expect(('stock_resume', str(P.HOME_GENRE)) in m.calls and 'window_open' not in m.names(), 'a tile that is not one of the lists opens its stock page')

    # A playlist: its id in classinfo[1] for every read and play (another page's query may leave another), its name the title
    pls, ci = O['CLASS_PLAYLIST_SONGS'], pod.DATA['CLASSINFO'][0] + O['CLASSINFO_ARG']
    m = list_machine(titles); m.playlist_songs = {7: list(m.songs[:5]), 3: list(m.songs[5:])}
    name = 'A very long playlist name for the road'
    r = m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr(name), count=900000000)
    big = m.widgets['sg_title']
    pl_lay = lambda n: Layout(['A'] * n, sections=False, top=O['PH_TOP'])   # a playlist's rows start under its header
    expect(r == 0 and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ALBUMS'], pls] and m.word(ci) == 7 and m.word(G_CLASS) == pls
           and m.props[(m.sv, 'virtual_h')] == pl_lay(5).content(), 'songs_open_playlist: class 0xff13 with the playlist in classinfo[1]: its five songs')
    expect(m.wtext[big] == fitted(name, O['SG_TITLE_W']) == fitted('A very long playlist name for the ro…', O['SG_TITLE_W']) and m.wtext[m.widgets['label_title']] == fitted(name, 110),
           f'the name is the title, cut with an ellipsis (no space before it) to the large title\'s full width and the small one\'s 110 ({m.wtext[big]!r})')
    foot = m.widgets['sg_foot']
    expect(m.wtext[foot] == '5 songs' and m.props.get((foot, 'y')) == O['PH_TOP'] + 5 * ROW + O['SG_FOOT_GAP'], f'the playlist\'s count under its last row: "5 songs" ({m.wtext.get(foot)!r})')
    m.setword(ci, 3)
    m.calls = []
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(not any(c[0] == 'loadLocalClassList' for c in m.calls), 'a playlist is not read again on the way back while the stock list is still its own')
    m.setword(SHOWLIST, m.new_deque([]))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(m.word(ci) == 7 and m.props[(m.sv, 'virtual_h')] == pl_lay(5).content(), 'read again with its own id put back in classinfo[1]')
    m.playlist_songs[7] = list(m.songs[:1]); m.setword(SHOWLIST, m.new_deque([]))   # one song left (deleted elsewhere); another query replaced the list
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(m.wtext[foot] == '1 song' and m.props.get((foot, 'y')) == O['PH_TOP'] + ROW + O['SG_FOOT_GAP'], f'read again, the count follows: "1 song" ({m.wtext.get(foot)!r})')
    m.playlist_songs[7] = list(m.songs[:5]); m.setword(SHOWLIST, m.new_deque([]))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    settle(m); m.setword(ci, 3)
    calls = tap(m, 150, pl_lay(5).row_y(1) + 30)
    expect(m.word(ci) == 7 and [c[3] for c in calls if c[0] == 'loadSongList'] == [pls] and m.played[1] == 1 and m.played[0] == m.songs[:5],
           'a row plays the playlist with class 0xff13 and its id in classinfo[1] (loadSongList keeps classinfo for the memory playback)')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    for nm in ('我的歌单' * 12, 'é' * 200):   # wide characters cut on a character; a name longer than the 255 bytes kept is cut before a character too
        m = list_machine(titles); m.playlist_songs = {7: list(m.songs[:2])}
        m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr(nm), count=900000000)
        kept = nm.encode('utf-8')[:255].decode('utf-8', 'ignore')
        expect(m.wtext[m.widgets['sg_title']] == fitted(kept, O['SG_TITLE_W']), f'a {len(nm.encode())} byte name is cut on characters ({len(kept)} kept)')
        m.call(PSYMS['sg_on_destroy'], count=4000000)

    # A playlist over a Songs page (Search was opened from it and a playlist result tapped): ours opens over it, and the page below is itself again when ours is destroyed
    fav = O['CLASS_FAV']
    m = list_machine(titles, fav); m.playlist_songs = {7: list(m.songs[:5])}
    m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000); settle(m)
    m.calls = []
    r = m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Road Trip'), count=900000000)
    expect(r == 0 and ('window_open', 'm1plus_songs') in m.calls and m.word(G_CLASS) == pls and m.word(ci) == 7, 'a playlist opens our Songs page over a Songs page below')
    r = m.call(PSYMS['songs_open_playlist'], a0=3, a1=m.cstr('Third'), count=900000000)
    expect(r == 0xffffffff, 'a second level is refused (the caller opens the stock page)')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m.calls = []; m.setword(SHOWLIST, m.new_deque([]))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'][-1:] == [fav], 'the page below is its own again (Favourites) when the playlist page is destroyed')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m.calls = []
    expect(m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Road Trip'), count=900000000) == 0 and ('window_open', 'm1plus_songs') in m.calls, 'nothing is left set aside once both are gone')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    # A playlist's header (docs/modules/songs.md "A playlist's header"): the Playlists page's 2 x 2 mosaic (patch/grid.c, one source a tick), the name and the count under
    # it, the pills and the rows lower, the large title gone, the small title once the name has scrolled away; other lists keep the large title
    PHC = O['PH_COVER']
    def head_blits(blits): return [b for b in blits if b[2][2] == PHC]
    def quad(m, bmp): return [pixel(m, bmp, x, y) for x, y in ((PHC // 4, PHC // 4), (3 * PHC // 4, PHC // 4), (PHC // 4, 3 * PHC // 4), (3 * PHC // 4, 3 * PHC // 4))]
    m = list_machine(titles); m.playlist_songs = {7: list(m.songs[:5])}
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Road Trip'), count=900000000)
    calls = list(m.calls)
    hn, big, lt = (m.widgets[n] for n in ('sg_hname', 'sg_title', 'label_title'))
    expect(('widget_set_visible', hn, 1) in calls and not [c for c in calls if c[0] == 'widget_set_sensitive' and c[1] == hn]
           and vis(m, 'sg_title') == (0, 0), 'a playlist shows its name label (insensitive: never a touch target) and hides the large title')
    expect(('widget_move', m.widgets['btn_play'], O['SG_PILL_X0'], O['PH_PILL_Y']) in calls and ('widget_move', m.widgets['btn_shuffle'], O['SG_PILL_X1'], O['PH_PILL_Y']) in calls,
           'the pills move under the header (the same x, y PH_PILL_Y)')
    expect(m.wtext[hn] == 'Road Trip', f'the name ({m.wtext.get(hn)!r})')
    blits, texts, styles, fills = settle(m)
    hb = head_blits(blits)
    expect(len(hb) == 1 and tuple(hb[0][2][:2]) == (O['PH_COVER_X'], O['PH_COVER_Y']) and m.most_per_tick == 1, f'the mosaic is drawn centred at (80, 8), 160 px, one cover decoded a tick ({[b[2] for b in hb]})')
    expect(all(near(a, colour(k)) for k, a in enumerate(quad(m, hb[0][0]))) and pixel(m, hb[0][0], 0, 0) & 0xffffff == 0, 'the four distinct albums fill the quadrants A B / C D, the corner rounded into black')
    rows0 = [r for t, r in texts if t == titles[0]]
    expect(rows0 and rows0[0][1] >= O['PH_TOP'], 'the first row is under the header (its text from PH_TOP down)')
    keep = hb[0][0]
    m.setword(SHOWLIST, m.new_deque([]))   # another query replaced the list: it is read again
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    blits2, *_ = settle(m)
    expect(head_blits(blits2)[0][0] == keep, 'a list read again keeps the mosaic (the same albums: no new tile, no flicker)')
    m.playlist_songs[7] = list(m.songs[2:4]); m.setword(SHOWLIST, m.new_deque([]))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    blits3, *_ = settle(m)
    expect(all(near(a, b2) for a, b2 in zip(quad(m, head_blits(blits3)[0][0]), [colour(2), colour(3), colour(3), colour(2)])),
           'other songs: the mosaic is made again from them (two albums: A B / B A)')
    scroll_to(m, O['PH_COLLAPSE'] - 10)
    expect(m.props.get((lt, 'visible')) != 1, 'the navbar\'s small title stays away while the name is in view')
    scroll_to(m, O['PH_COLLAPSE'] + 1)
    expect(m.props.get((lt, 'visible')) == 1, 'and shows once the name has scrolled away (PH_COLLAPSE, not the large title\'s 46)')
    scroll_to(m, 0)
    expect(m.props.get((lt, 'visible')) == 0, 'back at the top it goes')
    scroll_to(m, 100)
    blits4, *_ = paint(m)
    expect(head_blits(blits4)[0][1][1] == 100 - O['PH_COVER_Y'] and head_blits(blits4)[0][2][1] == 0, 'the mosaic scrolls with the content (cut at the window\'s top: its first 92 rows are gone)')
    calls = tap(m, 150, 20)
    expect(not [c for c in calls if c[0] in ('navigator_to_with_context', 'loadSongList')], 'a tap on the header opens and plays nothing')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    expect(sum(1 for c in m.calls if c[0] == 'bitmap_destroy') >= 3, 'closing frees the header\'s bitmaps with the others')
    # one album: its cover full size; none with a cache file: the placeholder disc; no memory for a quadrant: the first cover
    m = list_machine(titles); m.playlist_songs = {7: [m.songs[0], m.songs[5]]}
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('One'), count=900000000)
    hb = head_blits(settle(m)[0])
    expect(all(near(a, colour(0)) for a in quad(m, hb[0][0])), 'two songs of one album: that cover full size')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = list_machine(titles, cached=False); m.playlist_songs = {7: list(m.songs[:5])}
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Bare'), count=900000000)
    hb = head_blits(settle(m)[0])
    expect(len(hb) == 1 and all(near(a, 0xff404040) for a in quad(m, hb[0][0])), 'no album with a cache file: the stock placeholder disc')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = list_machine(titles); m.playlist_songs = {7: list(m.songs[:5])}; m.calloc_fail_size = (PHC // 2) * (PHC // 2) * 4
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Tight'), count=900000000)
    hb = head_blits(settle(m)[0])
    expect(all(near(a, colour(0)) for a in quad(m, hb[0][0])), 'no memory for the quadrant buffer: the first cover full size (as the Playlists page)')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # an empty playlist: the page says so (no header to show over nothing)
    m = list_machine(titles); m.playlist_songs = {7: []}
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Empty'), count=900000000)
    expect(vis(m, 'label_status') == (1, 1) and vis(m, 'view_grid') == (0, 0), 'an empty playlist: "No songs", the view hidden')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # an asset without the two labels, or no tile ring: the plain look (the large title, the pills where they were)
    m = list_machine(titles); m.playlist_songs = {7: list(m.songs[:5])}; del m.widgets['sg_hname']
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Plain'), count=900000000)
    expect(('widget_set_visible', m.widgets['sg_title'], 0) not in m.calls and not [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets['btn_play']]
           and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 5, sections=False).content(), 'without the header labels the page keeps the large title and the rows from SG_TOP')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # the other lists have no header
    m = list_machine(titles, O['CLASS_FAV']); m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000)
    expect(('widget_set_visible', m.widgets['sg_hname'], 1) not in m.calls and vis(m, 'sg_title') == (1, 1) and not [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets['btn_play']],
           'Favorites (and every list but a playlist) keep the large title and the pills where they were')
    m.call(PSYMS['sg_on_destroy'], count=4000000)

    # A genre's songs (class 0xff09, from the Genres page's tap): the genre's name and the Unknown byte in the browsing record for every read and play, its name the
    # title, and no Search (the stock navbar builder leaves it out for 0xff09): the capsule is Select (the left cap) | Now Playing
    gen, CI = O['CLASS_GENRE_SONGS'], pod.DATA['CLASSINFO'][0]
    ci_name = lambda m: m.read_cstr(CI + O['CLASSINFO_GENRE'])
    ci_unknown = lambda m: m.u.mem_read(CI + O['CLASSINFO_GENRE_UNKNOWN'], 1)[0]
    def genre_machine():
        m = list_machine(titles)
        m.genre_songs = {('Rock', 0): list(m.songs[:5]), ('Unknown Genre', 1): list(m.songs[5:]), ('我的' * 70, 0): list(m.songs[:2])}
        return m
    def corrupt(m):   # what another page's query leaves
        m.setword(CI, 0xff10); m.u.mem_write(CI + O['CLASSINFO_GENRE'], b'Other\0'); m.u.mem_write(CI + O['CLASSINFO_GENRE_UNKNOWN'], b'\x07')
    m = genre_machine()
    r = m.call(PSYMS['songs_open_genre'], a0=m.cstr('Rock'), a1=0, count=900000000)
    big, lt = m.widgets['sg_title'], m.widgets['label_title']
    expect(r == 0 and ('window_open', 'm1plus_songs') in m.calls and [c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [O['CLASS_ALBUMS'], gen]
           and m.word(G_CLASS) == gen and m.word(CI) == gen and ci_name(m) == 'Rock' and ci_unknown(m) == 0
           and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 5, sections=False).content(),
           'songs_open_genre: class 0xff09 with classinfo[0], the name at +0x30d and the Unknown byte 0 put in before the query: the genre\'s five songs')
    expect(m.wtext[big] == fitted('Rock', O['SG_TITLE_W']) and m.wtext[lt] == fitted('Rock', 156), 'the genre\'s name is the title (large full width, small 156 px)')
    sel = m.widgets['btn_select']
    expect(vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_sort') == (0, 0) and vis(m, 'btn_select') == (1, 1) and vis(m, 'btn_backtoplayer') == (1, 1)
           and ('widget_move', m.widgets['btn_search'], O['NAV_CF_X'], 0) not in m.calls and ('widget_resize', lt, O['NAV_VIEW_X'] - 58, 22) in m.calls,
           'no Search (hidden and insensitive) and no Sort: Select and Now Playing; the small title runs from 58 to 214 (Select\'s slot)')
    expect(m.props[(sel, 'style:normal:icon')] == m.props[(sel, 'style:over:icon')] == 'pod_nav_selectl' and m.props[(sel, 'style:pressed:icon')] == 'pod_nav_selectl_down',
           'Select shows its left-cap glass piece (pod_nav_selectl), so Select | Now Playing is one capsule (test/pod/glassbtn.py glues the two)')
    blits, texts, styles, fills = settle(m)
    shown = [t for t, r in texts if t in titles]
    expect(vis(m, 'sg_rail')[0] == 0 and shown == titles[:len(shown)] and len(shown) >= 4, 'a plain list in the query\'s order, no rail')
    corrupt(m); m.setword(SHOWLIST, m.new_deque([]))   # (the query that changed the record replaced the list too: a page behind another reads a replaced list again)
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(m.word(CI) == gen and ci_name(m) == 'Rock' and ci_unknown(m) == 0 and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 5, sections=False).content(),
           'read again with the browsing record put back (another page\'s query had changed it)')
    settle(m); corrupt(m)
    calls = tap(m, 150, lay.row_y(1) + 30)
    nav = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(nav and nav[0][3] == gen and m.played[1] == 1 and m.played[0] == m.songs[:5] and m.word(CI) == gen and ci_name(m) == 'Rock' and ci_unknown(m) == 0
           and [c[3] for c in calls if c[0] == 'loadSongList'] == [gen], 'a row plays the genre with class 0xff09 and the record put back before loadSongList')
    corrupt(m)
    calls = click(m, 'btn_play')
    expect(m.played[1] == 0 and m.word(CI) == gen and ci_name(m) == 'Rock', 'Play: the genre from its first song, the record put back')
    corrupt(m)
    calls = click(m, 'btn_shuffle')
    nav = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    expect(nav and nav[0][3] == gen and m.word(CI) == gen and ci_name(m) == 'Rock' and ('mclSetPlayMode', 2) in calls, 'Shuffle: this genre in the stock Shuffle mode, the record put back')
    click(m, 'btn_select')
    expect(all(vis(m, n) == (0, 0) for n in ('btn_search', 'btn_sort', 'btn_select', 'btn_backtoplayer')) and vis(m, 'sg_bar') == (1, 1), 'select mode as on Songs')
    tap(m, 150, lay.row_y(0) + 30); tap(m, 150, lay.row_y(3) + 30)
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    corrupt(m)
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1] == gen and bd[0][6] == [0, 3] and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [gen] and ci_name(m) == 'Rock',
           'Delete: batch_delete_file with class 0xff09 (the generic library delete), then the genre is read again with the record put back')
    m.confirm_answer = None
    expect(vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_sort') == (0, 0) and vis(m, 'btn_select') == (1, 1) and vis(m, 'btn_backtoplayer') == (1, 1)
           and m.props[(lt, 'w')] == O['NAV_VIEW_X'] - 58, 'leaving select mode brings back Select and Now Playing only, the title in its 156 px')
    click(m, 'btn_select'); tap(m, 150, lay.row_y(2) + 30)
    m.windows['m1plus_playlists'] = 0   # the stock picker (our page does not open)
    calls = click(m, 'sg_add')
    expect(('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | gen) in calls, 'Add opens the stock playlist picker with 1 << 16 | 0xff09')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # the Unknown Genre row, a long CJK name (cut as the stock snprintf of 0x80 bytes), and the fallback
    m = genre_machine()
    m.call(PSYMS['songs_open_genre'], a0=m.cstr('Unknown Genre'), a1=1, count=900000000)
    expect(ci_name(m) == 'Unknown Genre' and ci_unknown(m) == 1 and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 3, sections=False).content(),
           'the Unknown Genre row sets the byte classinfo + 0xc: its three songs')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = genre_machine()
    long_name = '我的' * 70   # 420 bytes: the page keeps 255, classinfo holds 0x7f of them, as the stock snprintf(.., 0x80, "%s") cuts it
    m.call(PSYMS['songs_open_genre'], a0=m.cstr(long_name), a1=0, count=900000000)
    raw = bytes(m.u.mem_read(CI + O['CLASSINFO_GENRE'], O['CLASSINFO_GENRE_SIZE']))
    expect(raw == long_name.encode()[:127] + b'\0', f'a long name is cut at 0x7f bytes with a terminating zero in classinfo + 0x30d ({len(raw)} bytes)')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m = genre_machine(); m.windows['m1plus_songs'] = 0
    r = m.call(PSYMS['songs_open_genre'], a0=m.cstr('Rock'), a1=0, count=900000000)
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    expect(r == 0xffffffff and nav and nav[0][:3] == ('navigator_to_with_context', 'allmusic_page', gen) and m.word(CI) == gen and ci_name(m) == 'Rock' and ci_unknown(m) == 0
           and 'loadLocalClassList' not in m.names(), 'a window that will not open: the stock row tap\'s sequence (the record, then allmusic_page 0xff09)')
    # the other lists keep Search and the plain Select icon
    m = list_machine(titles, O['CLASS_FAV']); m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000)
    expect(vis(m, 'btn_search') == (1, 1) and (m.widgets['btn_select'], 'style:normal:icon') not in m.props, 'Favorites keeps Search and the middle-piece Select')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    # An artist's songs (Cover Flow's artist page): the 0x390 byte browsing record is the list's state
    art_cls, ci0, nci = O['CLASS_ARTIST_SONGS'], pod.DATA['CLASSINFO'][0], O['CLASSINFO_SIZE']
    NONE = 0xffffffff
    def artist_machine(name='Miles Davis', n=5):
        m = list_machine(titles)
        m.artist_albums = {name: [m.record(album=f'Album {i}', artist=name, rid=100 + i) for i in range(2)]}
        m.artist_songs = {name: list(m.songs[:n]), 'Nina Simone': list(m.songs[n:])}
        return m, m.record(album='', artist=name, path='', title=name, name='', rid=7)
    m, row = artist_machine()
    r = m.call(PSYMS['songs_open_artist'], a0=row, count=900000000)
    calls = [c for c in m.calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList', 'loadLocalClassList', 'window_open')]
    expect(r == 0 and [c[:2] for c in calls] == [('loadAlbumList', O['CLASS_ARTISTS']), ('loadAlbumdetailList', O['CLASS_ARTIST_ALBUMS']), ('window_open', 'm1plus_songs'),
                                                 ('loadLocalClassList', O['CLASS_ALBUMS']), ('loadLocalClassList', art_cls)]
           and calls[0][2] == row and m.word(calls[1][2] + O['REC_ID']) == O['ID_ALL_SONGS'] & NONE and m.word(G_CLASS) == art_cls
           and m.deques[m.word(pod.DATA['PDEQ_SHOWLIST'][0])] == m.songs[:5],
           f'songs_open_artist: loadAlbumList(0xf004, the artist), loadAlbumdetailList(0xff01, the All songs row), the page, then class 0xff11: the artist\'s five songs ({calls})')
    expect(m.u.mem_read(ci0 + O['CLASSINFO_ALL_SONGS'], 1)[0] == 1 and m.word(ci0) == art_cls and m.read_cstr(ci0 + O['CLASSINFO_ARTIST']) == 'Miles Davis',
           'the record holds the all-songs flag, class 0xff11 and the artist, as the stock queries leave it')
    big, lt = m.widgets['sg_title'], m.widgets['label_title']
    expect(m.wtext[big] == 'Miles Davis' and m.wtext[lt] == 'Miles Davis' and vis(m, 'btn_sort') == (0, 0) and ('widget_move', m.widgets['btn_search'], O['NAV_CF_X'], 0) not in m.calls,
           'the artist is the title; no Sort')
    cfb = m.widgets['btn_coverflow']
    expect(vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_coverflow') == (1, 1) and m.props[(lt, 'w')] == O['NAV_CF_X'] - 58,
           'an artist\'s songs: no Search (hidden and insensitive), the Cover Flow button is the capsule\'s left cap at 168 and the title ends there')
    expect((cfb, O['EVT_CLICK']) in m.bound, 'the Cover Flow button is bound')
    blits, texts, styles, fills = settle(m)
    shown = [t for t, rc in texts]
    expect(vis(m, 'sg_rail')[0] == 0 and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 5, sections=False).content() and shown[:5] == titles[:5] and 'Album 0' in shown
           and not any(t.startswith('Artist ') for t in shown), f'a plain list in the query\'s order whose second line is the album, not the artist ({shown[:6]})')
    snap = bytes(m.u.mem_read(ci0, nci))
    m.u.mem_write(ci0, b'\xaa' * nci); m.setword(SHOWLIST, m.new_deque([]))   # another page's query
    m.calls = []
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect([c[1] for c in m.calls if c[0] == 'loadLocalClassList'] == [art_cls] and m.props[(m.sv, 'virtual_h')] == Layout(['A'] * 5, sections=False).content()
           and bytes(m.u.mem_read(ci0, nci)) == snap, 'read again on return: the record is put back first, so the same five songs')
    settle(m)
    m.u.mem_write(ci0, b'\xaa' * nci)
    calls = tap(m, 150, lay.row_y(1) + 30)
    expect([c[3] for c in calls if c[0] == 'loadSongList'] == [art_cls] and bytes(m.u.mem_read(ci0, nci)) == snap and m.played[1] == 1 and m.played[0] == m.songs[:5]
           and m.word(G_CLASS) == art_cls, 'a row plays the artist\'s songs with class 0xff11, the record put back before loadSongList')
    # the toggle with Cover Flow's artist page: the Cover Flow button closes this page only (the covers page is under it); Back leaves the artist (both pages)
    COVERS_WIN, SONGS_WIN = 0x111, 0x222
    def backs(m): return sum(1 for c in m.calls if c[0] == 'navigator_back')
    m.cf_page = COVERS_WIN; m.stack = [COVERS_WIN, SONGS_WIN]; m.calls = []
    click(m, 'btn_coverflow')
    expect(backs(m) == 1 and m.stack == [COVERS_WIN], f'Cover Flow button: one navigator_back, the covers page is what is left ({backs(m)}, {m.stack})')
    m.stack = [COVERS_WIN, SONGS_WIN]; m.calls = []
    click(m, 'btn_return')
    expect(backs(m) == 2 and m.stack == [], f'Back from the artist\'s songs leaves the artist: this page and the covers page close ({backs(m)}, {m.stack})')
    m.stack = [0x999, COVERS_WIN, SONGS_WIN]; m.calls = []
    click(m, 'btn_return')
    expect(backs(m) == 2 and m.stack == [0x999], 'Back with Now Playing or the Artists list under the covers page ends there (two pages closed)')
    m.stack = [0x999, SONGS_WIN]; m.calls = []
    click(m, 'btn_return')
    expect(backs(m) == 1 and m.stack == [0x999], 'Back with another window under this page (no covers page) closes only this page')
    m.cf_page = None; m.stack = None; m.calls = []
    click(m, 'btn_select')
    expect(vis(m, 'btn_coverflow') == (0, 0) and vis(m, 'btn_search') == (0, 0), 'select mode hides the Cover Flow button')
    click(m, 'btn_coverflow')
    expect(backs(m) == 0, 'a stray click on the hidden Cover Flow button in select mode does nothing')
    click(m, 'btn_return')
    expect(vis(m, 'btn_coverflow') == (1, 1) and vis(m, 'btn_search') == (0, 0) and backs(m) == 0, 'leaving select mode shows the Cover Flow button again, still no Search')
    click(m, 'btn_select'); tap(m, 150, lay.row_y(0) + 30); tap(m, 150, lay.row_y(3) + 30)
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    m.u.mem_write(ci0, b'\xaa' * nci)
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1] == art_cls and bd[0][6] == [0, 3] and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [art_cls],
           'Delete: batch_delete_file with class 0xff11, then the list is read again')
    m.confirm_answer = None
    click(m, 'btn_select'); tap(m, 150, lay.row_y(2) + 30)
    m.windows['m1plus_playlists'] = 0   # the stock picker (our page does not open)
    calls = click(m, 'sg_add')
    expect(('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | art_cls) in calls, 'Add opens the playlist picker with class 0xff11')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    long_name = 'Miles Davis and the Quintet of Many Names'
    m, row = artist_machine(long_name)
    m.call(PSYMS['songs_open_artist'], a0=row, count=900000000)
    expect(m.wtext[m.widgets['sg_title']] == fitted(long_name, O['SG_TITLE_W']) and m.wtext[m.widgets['label_title']] == fitted(long_name, 110),
           'a long artist name is cut with an ellipsis, like a playlist\'s')
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    m, row = artist_machine(); m.artist_albums = {}   # no All songs row (the stock list is empty)
    r = m.call(PSYMS['songs_open_artist'], a0=row, count=900000000)
    expect(r & NONE == NONE and 'window_open' not in m.names() and 'loadAlbumdetailList' not in m.names(), 'an artist with no All songs row: -1, no page, the caller falls back')
    m, row = artist_machine(); m.windows['m1plus_songs'] = 0
    expect(m.call(PSYMS['songs_open_artist'], a0=row, count=900000000) & NONE == NONE and not any(c[0] == 'stock_resume' for c in m.calls),
           'a window that will not open: -1, no Home fallback')
    expect(m.call(PSYMS['songs_open_artist'], a0=0, count=900000000) & NONE == NONE, 'no artist: -1')


SECTIONS = [asset_tests, open_and_paint_tests, touch_tests, rail_tests, order_search_and_stale_tests, collapse_and_select_tests, loader_tests, big_library_tests, lists_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

"""The album page (patch/albumpage.c, patch/songops.c, docs/modules/album-page.md): our own page in place of the stock albuminfo_page. The built asset (the list that is the
whole window, the header's widgets, the glass controls last, every number against patch/offsets.inc and the stock page's design), how cc_open_album reaches it and falls back
to the stock page, the header (the texts, the pill's pair in every language, the cover from the cache or from the cache worker, the tint, the status bar and its hand-over,
the tone cache), the rows painted from the stock list (number, title, the playing row's gold, a CUE track, three digits, the press fill, the hairline), the taps (a track, Play,
Shuffle: the stock sequence and Now Playing the stock album page's way), the select mode with Add and Delete on the stock selection vector, and a list another query replaced.
The compiled payload runs under Unicorn; the stock library is the machine's lists."""
import importlib.util, os, struct, sys
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


SG = sibling('songs')
NA = sibling('nextalbum')

WIN_H, HDR, ROW, SY0 = O['AH_WIN_H'], O['AH_HDR_H'], O['LIST_ROW_H'], 30   # SY0: the window's screen y (the status bar's 30 px; the list is the whole window)
SC_YOFF = O['SC_YOFF']
LIB, ALBUMS, ART, COMP = O['CLASS_ALBUM_TRACKS'], O['CLASS_ALBUMS'], O['CLASS_ARTIST_SONGS'], O['CLASS_14']
CI = pod.DATA['CLASSINFO'][0]
SHOWLIST, G_CLASS, NAV_TITLE, SEL_VEC, SONGER = (pod.DATA[k][0] for k in ('PDEQ_SHOWLIST', 'G_CLASS_TYPE', 'NAV_TITLE', 'SEL_VEC', 'SONGER_FLAG'))
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_album.bin') if WORK else None
ALBUM, ARTIST = 'Kind of Blue', 'Miles Davis'
RED = (190, 50, 55)
NAMES = ['So What', 'Freddie Freeloader', 'Blue in Green', 'All Blues', 'Flamenco Sketches', 'Flamenco Sketches (Alt)', 'So What (Alt)', 'Blue in Green (Alt)']
WIDGETS = ('view_grid', 'btn_return', 'btn_backtoplayer', 'btn_select', 'btn_selall', 'sg_add', 'sg_del', 'btn_cancel', 'btn_play', 'btn_shuffle', 'label_status', 'label_row_num', 'label_row_title', 'label_row_dim', 'label_row_val',
           'ab_title', 'ab_artist', 'ab_meta', 'ab_foot', 'ab_spin', 'ab_glyph', 'ab_play_text', 'label_title', 'img_ah_tint',
           'btn_more', 'vs_scrim', 'vs_card', 'vs_hair') + tuple(f'vs_item{i}' for i in range(8)) + tuple(f'vs_label{i}' for i in range(8)) + tuple(f'vs_tick{i}' for i in range(6)) + tuple(f'vs_sub{i}' for i in range(4)) + tuple(f'vs_glyph{i}' for i in range(4, 8))
NAV_BTNS = ('btn_return', 'btn_backtoplayer', 'btn_select', 'btn_selall', 'sg_add', 'sg_del', 'btn_cancel')
BAR_BLACK = O['NP_BAR_STOCK']


def utf(s): return s.encode('latin-1').decode('utf-8')


class AM(SG.SongsMachine):
    """The Songs machine plus what the album page calls: loadAlbumdetailList on an album row (class 0xff10 / 0xff11 / 0xff14, the record's names, the album's tracks), the
    class query that reads the browsing record (empty when another page changed it), is_playing, and a status bar among the window manager's children."""
    album_tracks = None   # album name -> its track records
    playing = None        # (file name, url, cue start) is_playing answers 1 for
    na_at_open = None     # Continue with Next Album's state as Now Playing opened (the load happens there)
    load_on_open = False  # run the payload's na_on_load for the queue load the open makes (mclLoadPlayList's hook)
    scoped = ARTIST       # the artist an artist's / composer's album page was reached through (loadAlbumList left it in the record)

    def tracks_of(self, album): return list((self.album_tracks or {}).get(album, []))

    def with_bar(self):
        nav = self.alloc(0x80); self.bar = self.alloc(0x80)
        self.children[self.wm] = [nav, self.bar]; self.types[nav] = 'system_bar_bottom'; self.types[self.bar] = 'system_bar'
        return self

    def bar_styles(self): return [s[2] for s in self.styled if s[0] == getattr(self, 'bar', -1)]
    def win_colors(self): return [s[2] for s in self.styled if s[0] == self.window and s[1] == 'normal:bg_color']

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = 0
        if name == 'is_playing':
            self.calls.append(('is_playing', a0, a1))
            ret = int(self.playing is not None and self.playing == (self.read_cstr(a2), self.read_cstr(a3), a1))
        elif name == 'loadAlbumdetailList':
            self.calls.append(('loadAlbumdetailList', a0, a1))
            cls = {O['CLASS_ALBUMS']: LIB, O['CLASS_ARTIST_ALBUMS']: ART, O['CLASS_COMPOSER_ALBUMS']: COMP}[a0]
            album = self.read_cstr(self.word(a1 + O['REC_ALBUM']))
            self.u.mem_write(CI + O['CLASSINFO_ALBUM'], bytes(0x100)); self.u.mem_write(CI + O['CLASSINFO_ALBUM'], album.encode())
            if a0 == O['CLASS_ALBUMS']:   # the Albums row: the record's artist is the row's, +9 the Unknown Album flag
                self.u.mem_write(CI + O['CLASSINFO_ARTIST'], bytes(0x100)); self.u.mem_write(CI + O['CLASSINFO_ARTIST'], self.read_cstr(self.word(a1 + O['REC_ARTIST'])).encode())
                self.u.mem_write(CI + 9, bytes([int(self.word(a1 + O['REC_ID']) == 0xffffffff)]))
            else:   # the artist's or composer's page: the name loadAlbumList left (+0x10d, +0x20d for 0xff14)
                self.u.mem_write(CI + (O['CLASSINFO_ARTIST_14'] if cls == COMP else O['CLASSINFO_ARTIST']), self.scoped.encode() + b'\0')
            self.setword(CI, cls)
            items = self.tracks_of(album)
            self.setword(SHOWLIST, self.new_deque(items)); ret = len(items)
        elif name == 'loadLocalClassList' and a0 in (LIB, ART, COMP):
            self.calls.append(('loadLocalClassList', a0))
            items = self.tracks_of(self.read_cstr(CI + O['CLASSINFO_ALBUM'])) if self.word(CI) == a0 else []
            self.setword(SHOWLIST, self.new_deque(items)); ret = len(items)
        elif name == 'navigator_to_with_context' and self.read_cstr(a0) == 'playing_page':
            # start_player runs inside playing_page's init, so inside this call, and loads the queue through mclLoadPlayList (hook 14: sh_load_playlist -> na_on_load first):
            # the state na_on_load sees is the one at this moment, and the mock lets the payload's own na_on_load run for it (it returns to the caller as the navigator does)
            super()._hook(u, address, size, _)
            self.na_at_open = NA.state(self)
            if self.load_on_open: u.reg_write(UC_MIPS_REG_PC, PSYMS['na_on_load'])
            return
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def album_machine(n=8, album=ALBUM, artist=ARTIST, rgb=RED, cover='file', titles=None, year=1959, cues=(), others=2):
    """The page's widgets as widget structs (window > list_view > scroll_view > view_grid, for demo's own widget_to_local), the album's n tracks, the library's album list (the
    album first) and the cover cache file of the album: cover 'file' (a flat rgb picture), 'marker' (the empty "no art" file) or None (no file)."""
    m = AM(); m.real_album = True
    m.load_image = 0
    for w in WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.images = {'p_default': (24, 24, bytes((0x40, 0x40, 0x40, 255)) * (24 * 24)), 'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676),
                'ah_wave': (12, 12, b''.join(struct.pack('<I', 0xff0000ee if 4 <= x < 7 else 0xff000000) for y in range(12) for x in range(12)))}   # (a bar at columns 4..6, flattened over black as cc_decode gives it)
    m.setword(SEL_VEC, m.alloc(8))
    m.stock_songlist = True
    recs = []
    for i in range(n):
        title = titles[i] if titles else NAMES[i % len(NAMES)] if n <= len(NAMES) else f'Track {i + 1}'
        r = m.record(album=album, artist=artist, path=f'/mnt/mmc/m/{i}.flac', title=title, name=f'{i}.flac', rid=100 + i)
        m.setword(r + O['REC_YEAR'], year)
        if i in cues: m.setword(r + O['REC_CUE_START'], 1000 * i)
        m.present.add(f'/mnt/mmc/m/{i}.flac')
        recs.append(r)
    m.songs, m.album_tracks = recs, {album: recs}
    row = m.record(album=album, artist=artist, path='/mnt/mmc/m/0.flac', title=album, name='', rid=900)
    m.row = row
    m.class_lists[ALBUMS] = [row] + [m.record(album=f'Other {i}', artist=f'Artist {i}', path=f'/mnt/mmc/o/{i}.flac', title=f'Other {i}', rid=901 + i) for i in range(others)]
    m.key = album_key(artist, album)
    m.cover_path = art_file(m.key)
    if cover == 'file':
        m.present.add(m.cover_path); m.files[m.cover_path] = 4096
        m.images['file://' + m.cover_path] = (168, 168, bytes(rgb + (255,)) * (168 * 168))
    elif cover == 'marker':
        m.present.add(m.cover_path); m.files[m.cover_path] = 0
    win, lv, sv, view = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_grid']
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, SY0, WIN_H, 0), (lv, 0, WIN_H, win), (sv, 0, WIN_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310); m.setword(sv + 0x70, SV_VT)   # a real scroll_view's vtable: demo's widget_to_local adds its offset
    m.widgets['songs_scrollview'] = sv
    for off, v in ((4, 0), (8, 320), (0xc, WIN_H), (0x44, sv)): m.setword(view + off, v)
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    m.wtext[m.widgets['ab_play_text']] = 'Play'
    m.sv, m.view = sv, view
    m.with_bar()
    return m


def open_album(m, index=0):
    r = m.call(PSYMS['cc_open_album'], a0=0, a1=0, a2=index, count=900000000)
    return r, list(m.calls)


def opened(**kw):
    m = album_machine(**kw)
    r, calls = open_album(m)
    assert r == 0 and ('window_open', 'm1plus_album') in calls, f'the page did not open ({r}, {calls[:12]})'
    return m


def scroll_to(m, v): m.setword(m.sv + SC_YOFF, v & 0xffffffff)
def off_of(m): return m.s32(m.sv + SC_YOFF)


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts, styles, fills) of that frame, the canvas where the scroll_view leaves it."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SY0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['ab_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(zip(m.texts, m.text_styles)), list(m.fills)


def touch(m, kind, x, y, fn, t=1000): return m.touch(kind, x, SY0 + y, t, fn=fn)


def tap(m, x, y, dx=0, dy=0):
    """A tap on the content view at list point (x, y) (the list starts at the window's top; the scroll offset is not included)."""
    touch(m, 'down', x, y, 'ab_on_down')
    touch(m, 'up', x + dx, y + dy, 'ab_on_up', 1080)
    return list(m.calls)


def click(m, name):
    m.click(name, count=900000000)
    return list(m.calls)


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def row_y(i): return HDR + i * ROW


def ui(): return awtk_ui.parse(open(UI, 'rb').read())


def tone_word(rgb):
    import mod_nowplaying as mn
    t = mn.tone(*rgb)
    return 0xff000000 | t[0] | t[1] << 8 | t[2] << 16


def pill(tw): return O['AH_PLAY_X'] + (O['AH_PLAY_W'] - (O['AH_PILL_GLYPH'] + O['AH_PILL_GAP'] + tw)) // 2   # x of the pill's glyph for a text tw px wide


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def asset_tests(ctx):
    """1. The built asset: a list that is the whole window under a gradient image, the header's widgets at the stock page's numbers, the glass controls last."""
    expect = ctx.expect
    root = ui()
    f = root.find
    kids = [c.name for c in root.children]
    expect(root.name == 'm1plus_album_page' == pod_pages.ALBUM_PAGE.name and pod_pages.ALBUM_PAGE in pod_pages.PAGES and pod_pages.ALBUM_PAGE.key == 'm1plus_album' == O.get('AB_ASSET', 'm1plus_album'),
           'the page is m1plus_album (window m1plus_album_page)')
    expect(kids[0] == 'img_ah_tint' and kids[-5] == 'btn_cancel' and kids[-13] == 'label_title' and kids[-4:] == ['vs_scrim', 'vs_card', 'rm_scrim', 'rm_card'] and 'songs_listview' in kids, f'the gradient is the window\'s first child, the glass controls and the rows menu its last: {kids}')
    tint = f('img_ah_tint')
    expect((tint.x, tint.y, tint.w, tint.h) == (0, 0, 320, 450) and tint.get('image') == 'ah_tint' and tint.get('clickable') == 'false' and tint.get('sensitive') == 'false'
           and tint.get('visible') != 'false', 'img_ah_tint: ah_tint over the whole 320 x 450 window, insensitive (over a black page it changes nothing)')
    lv, sv, grid = f('songs_listview'), f('songs_scrollview'), f('view_grid')
    expect((lv.x, lv.y, lv.w, lv.h) == (0, 0, 320, WIN_H) and (sv.y, sv.w, sv.h) == (0, 310, WIN_H) and f('scroll_bar_m') is not None
           and all(w.get(f'style:{st}:bg_color') == '#00000000' for w in (lv, sv, grid) for st in ('normal',)),
           'the list is the whole window (y 0, 450 high), its scroll_view 310 wide with the stock scroll bar, all transparent: the window\'s colour and the gradient show through')
    # the header: the stock page's numbers (docs/modules/album-page.md)
    expect((O['AH_ART'], O['AH_ART_X'], O['AH_ART_Y'], O['AH_CORNER'], O['AH_HDR_H'], O['AH_TITLE_Y'], O['AH_ARTIST_Y'], O['AH_META_Y'], O['AH_BTN_Y']) == (160, 80, 50, 10, 346, 224, 247, 267, 292)
           and (O['AH_SHUF_X'], O['AH_SHUF_W'], O['AH_PLAY_X'], O['AH_PLAY_W'], O['AH_BTN_H']) == (42, 44, 96, 180, 44), 'the geometry constants are the stock album page\'s')
    expect(O['AH_HDR_H'] - (O['AH_BTN_Y'] + (O['AH_BTN_H'] + O['AH_PILL_H']) // 2) == 12, 'the first track row is 12 px under the Play pill (drawn 294 .. 334), as on the Songs, playlist, Folders and Daily Mix pages')
    for name, y, h, px, colour in (('ab_title', 224, 22, 22, '#FFFFFF'), ('ab_artist', 247, 18, 18, '#AAAAAA'), ('ab_meta', 267, 15, 15, '#9C9C9C')):
        w = f(name)
        expect(w.type == 'hscroll_label' and (w.x, w.y, w.w, w.h) == (17, y, 286, h) and w.get('sensitive') == 'false' and w.get('ellipses') == 'true' and w.get('yoyo') == 'true'
               and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == colour and w.get('style:normal:text_align_h') == 'center',
               f'{name}: a centred {px} px {colour} hscroll_label at (17, {y}), 286 x {h}, insensitive (a drag over it scrolls the list), scrolling a long text')
    shuf, play, glyph, ptext = f('btn_shuffle'), f('btn_play'), f('ab_glyph'), f('ab_play_text')
    expect((shuf.x, shuf.y, shuf.w, shuf.h) == (42, 292, 44, 44) and shuf.get('style:normal:icon') == 'ah_shuffle' and shuf.get('style:pressed:icon') == 'ah_shuffle_down'
           and (play.x, play.y, play.w, play.h) == (96, 292, 180, 44) and play.get('style:normal:icon') == 'ah_pill' and play.get('style:pressed:icon') == 'ah_pill_down',
           'Shuffle is a 44 x 44 touch rectangle with the 40 px disc, Play a 180 x 44 one with the 180 x 40 pill (the disc as high as the pill), 12 px apart')
    import mod_icons as _mi
    expect(O['AH_DISC'] == 40 == _mi.AH_DISC_PX == O['AH_PILL_H'] and O['AH_PLAY_X'] == O['AH_SHUF_X'] + (O['AH_SHUF_W'] + O['AH_DISC']) // 2 + 12, 'the Shuffle disc is the pill\'s 40 px high; the pill starts 12 px after it')
    expect(glyph.type == 'image' and (glyph.w, glyph.h) == (16, 16) and glyph.get('image') == 'ah_play' and glyph.get('sensitive') == 'false' and glyph.y == 292 + 14
           and glyph.x == pill(O['AB_PLAY_TEXT_W']), 'the pill\'s play glyph is a 16 px insensitive image over the pill (the English pair centred where the payload cannot measure)')
    expect(ptext.get('visible') == 'false' and ptext.get('sensitive') == 'false' and ptext.get('style:normal:font_size') == '18' and ptext.get('style:normal:text_color') == '#141414'
           and ptext.get('style:normal:bg_color') == '#FFFFFF' and ptext.get('text') in (None, 'Play') and ptext.get('tr_text', 'Play') == 'Play',
           'the pill\'s text is a hidden label (the 18 px #141414 style and the translated "Play"; its white background is the pill\'s for the contrast scan)')
    for name, align, colour in (('label_row_num', 'right', '#AAAAAA'), ('label_row_title', 'left', '#FFFFFF')):
        w = f(name)
        expect(w.get('visible') == 'false' and w.get('sensitive') == 'false' and w.get('style:normal:font_size') == '19' and w.get('style:normal:text_color') == colour and w.get('style:normal:text_align_h') == align,
               f'{name}: the hidden 19 px {colour} {align} text style of the rows')
    # the glass controls
    k = {c.name: c for c in root.children}
    expect('navigationbar_view' not in k, 'the controls are children of the window itself (no bar view over the list)')
    want = {'btn_return': (7, 44, 'ah_nav_back', 1), 'btn_select': (214, 46, 'pod_nav_selectl', 1), 'btn_backtoplayer': (260, 60, 'ah_nav_play', 1),
            'btn_selall': (0, 50, 'ah_nav_unsel', 0), 'sg_add': (116, 60, 'ah_nav_add', 0), 'sg_del': (191, 60, 'ah_nav_del', 0), 'btn_cancel': (268, 60, 'ah_nav_cancel', 0)}
    xx = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    for name, (x, w, icon, shown) in want.items():
        b = k[name]
        expect((b.x, b.y, b.w, b.h) == (x, 0, w, 50) and b.get('style:normal:icon') == icon and b.get('style:pressed:icon') == icon + '_down' and (b.get('visible') != 'false') == bool(shown)
               and (b.get('sensitive') != 'false') == bool(shown) and os.path.exists(os.path.join(xx, icon + '.png')) and os.path.exists(os.path.join(xx, icon + '_down.png')),
               f'{name}: {icon} at x {x} ({w} wide, 50 high), pressed {icon}_down, {"shown" if shown else "hidden and insensitive"}')
    expect(k['btn_select'].x + k['btn_select'].w == k['btn_backtoplayer'].x, 'Select is flush left of Now Playing: one glass capsule (the genre songs list\'s: the left cap, then the right cap)')
    expect(k['label_title'].get('visible') == 'false' and not [c for c in root.walk() if c.name in ('sg_rail', 'sg_bubble', 'sg_card', 'sg_bar', 'img_nb_fade', 'sg_foot')],
           'the page has no title, no fade, no rail, no sort card, no bottom bar and no count: the controls float over the rows')
    for n in ('btn_return', 'btn_select', 'btn_backtoplayer', 'btn_play', 'btn_shuffle'):
        expect(f(n).get('style') == 'img_btn_style', f'{n} draws its picture only (img_btn_style)')
    # demo's own hit test on the built page with the list's rows under the controls
    m = AM(); m.real_album = True
    tree = asset_tree(UI)
    node(tree, 'view_grid').h = 3000
    for sel in ('btn_selall', 'sg_add', 'sg_del', 'btn_cancel'): node(tree, sel).flags = 0   # hidden and insensitive, as the payload leaves them outside select mode
    top = lambda x, y: stock_target(m, tree, x, y)[-1]
    expect(top(29, 25) == 'btn_return' and top(8, 6) == 'btn_return' and top(237, 25) == 'btn_select' and top(290, 25) == 'btn_backtoplayer' and top(311, 45) == 'btn_backtoplayer',
           f'Back, Select and Now Playing are hit at the glass\'s centres and corners ({[top(29, 25), top(237, 25), top(290, 25)]})')
    expect(top(160, 25) == 'view_grid' and top(100, 8) == 'view_grid' and top(160, 150) == 'view_grid', f'the band between the controls takes no touch itself: a drag that starts there scrolls the list ({[top(160, 25), top(100, 8)]})')
    expect('img_ah_tint' not in stock_target(m, tree, 160, 300) and top(300, 25) != 'img_ah_tint', 'the gradient image takes no touch')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def open_tests(ctx):
    """2. cc_open_album reaches the page, with the fallbacks to the stock page; 3. the open: what it queries, binds and shows."""
    expect = ctx.expect
    m = album_machine()
    r, calls = open_album(m)
    seq = [c[:2] for c in calls if c[0] in ('loadAlbumList', 'loadAlbumdetailList', 'window_open', 'loadLocalClassList', 'albumcoverinfo_init', 'batchadd_albumcover_task')]
    expect(r == 0 and seq == [('loadAlbumList', ALBUMS), ('loadAlbumdetailList', ALBUMS), ('window_open', 'm1plus_album'), ('loadLocalClassList', LIB)]
           and [c for c in calls if c[0] == 'loadAlbumdetailList'][0][2] == m.row and not [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page'],
           f'the Albums row: loadAlbumList(0xf003), loadAlbumdetailList(0xf003, the row\'s record), our window, the tracks\' query; the stock page and its cover thread are not started ({seq})')
    expect(m.word(G_CLASS) == LIB and m.word(CI) == LIB and m.read_cstr(CI + O['CLASSINFO_ALBUM']) == ALBUM and m.read_cstr(CI + O['CLASSINFO_ARTIST']) == ARTIST,
           'the browsing class is the album tracks\' (0xff10), as albuminfo_page_init leaves it')
    expect(all((m.widgets[n], O['EVT_CLICK']) in m.bound for n in NAV_BTNS[:1] + ('btn_backtoplayer', 'btn_select', 'btn_selall', 'sg_add', 'sg_del', 'btn_cancel', 'btn_play', 'btn_shuffle'))
           and all((m.view, O[e]) in m.bound for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT', 'EVT_AFTER_PAINT'))
           and all((m.window, O[e]) in m.bound for e in ('EVT_WINDOW_TO_FG', 'EVT_WINDOW_TO_BG', 'EVT_DESTROY')), 'the buttons, the content view\'s touch and paint events and the window\'s events are bound')
    sizes = [c for c in calls if c[0] == 'widget_resize' and c[1] == m.view]
    expect(sizes and sizes[-1][2:] == (320, HDR + 8 * ROW) and m.props[(m.sv, 'virtual_h')] == HDR + 8 * ROW, f'the content is the {HDR} px header and 8 rows of {ROW}: {HDR + 8 * ROW} px, the scroll_view is told (no footer without a known duration)')
    expect(vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status') == (0, 0) and not any(c[0] == 'widget_set_visible' and c[1] in [m.widgets[n] for n in ('btn_selall', 'sg_add', 'sg_del', 'btn_cancel')] for c in calls),
           'the list shows, the status line is hidden, the select mode\'s buttons stay as the asset has them (hidden)')
    expect(not [c for c in calls if c[0] == 'widget_load_image' and c[1] not in ('p_default', 'unselect', 'selected', 'ah_wave') and not c[1].endswith('.jpg')], 'only the cover file is decoded (no cover per row)')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(len(m.bitmaps) == 0 and not m.timers_open() if hasattr(m, 'timers_open') else len(m.bitmaps) == 0, f'closing frees every bitmap ({len(m.bitmaps)} left)')
    # the artist's and the composer's album: the same page, the classes 0xff11 / 0xff14, the artist from the record loadAlbumList filled
    for scope, cls, cd in ((O['CLASS_ARTISTS'], ART, O['CLASS_ARTIST_ALBUMS']), (O['CLASS_COMPOSERS'], COMP, O['CLASS_COMPOSER_ALBUMS'])):
        m = album_machine(); m.scoped = 'Bach'
        arow = m.record(album='', artist='Bach', path='', title='Bach', name='', rid=7)
        m.artist_albums = {'Bach': [m.row]}
        r = m.call(PSYMS['cc_open_album'], a0=m.new_deque([arow]), a1=scope, a2=0, count=900000000)
        la = [c for c in m.calls if c[0] == 'loadAlbumList']
        expect(r == 0 and ('window_open', 'm1plus_album') in m.calls and la[0][1] == (scope if scope == O['CLASS_COMPOSERS'] else O['CLASS_ARTISTS']) and ('loadAlbumdetailList', cd, m.row) in m.calls
               and m.word(G_CLASS) == cls and m.word(CI) == cls, f'an {"artist" if cls == ART else "composer"}\'s album: loadAlbumdetailList({cd:#x}), the class {cls:#x}')
        expect(m.wtext[m.widgets['ab_artist']] == 'Bach', 'its artist line is the name loadAlbumList left in the record')
        m.call(PSYMS['ab_on_destroy'], count=4000000)
    # fallbacks: the stock page, in the stock sequence
    def stock_ok(m, why, queried=True):
        names = [c[0] for c in m.calls]
        nav = [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']
        expect(nav and nav[0][2:] == (ALBUMS, 0) and 'albumcoverinfo_init' in names and 'batchadd_albumcover_task' in names and names.count('loadAlbumList') == (2 if queried else 1),
               f'{why}: the stock albuminfo_page opens, the cover thread released, the album list loaded {"again" if queried else "once"} ({names.count("loadAlbumList")} loads)')
    m = album_machine(); m.windows['m1plus_album'] = 0
    open_album(m)
    stock_ok(m, 'a window that will not open')
    m = album_machine(); m.widgets.pop('ab_glyph')
    open_album(m)
    stock_ok(m, 'an asset that is not ours')
    expect(('navigator_back',) in m.calls, 'whose window is left again')
    m = album_machine()
    card = m.record(album='', artist=ARTIST, path='', title='All songs', name='', rid=O['ID_ALL_SONGS'] & 0xffffffff)
    m.class_lists[ALBUMS] = [card]
    open_album(m)
    stock_ok(m, 'the All albums card', queried=False)
    m = album_machine()
    open_album(m); m.calls = []
    r, calls = open_album(m)
    stock_ok(m, 'a page that is already open', queried=False)
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    r, calls = open_album(m)
    expect(r == 0 and ('window_open', 'm1plus_album') in calls, 'after its destroy the page opens again (the state is cleared)')
    m = album_machine()
    expect(m.call(PSYMS['cc_open_album'], a0=0, a1=0, a2=99, count=900000000) & 0xffffffff == 0xffffffff and 'window_open' not in m.names(), 'a row that is not in the list: -1, nothing opened')
    # Now Playing's Look up album and the pages in the stack: both album pages are closed first
    src = open(os.path.join(ROOT, 'patch', 'playmore.c')).read()
    expect('pm_close_albums' in src and 'AB_WINDOW' in src and O.get('AB_WINDOW') is None and pod_pages.ALBUM_PAGE.name == 'm1plus_album_page',
           'Look up album and Look up artist close an album page of ours and the stock one (AB_WINDOW is the root widget\'s name)')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def header_tests(ctx):
    """4. The header: texts, the pill's pair in the player's language, the cover and its corners."""
    expect = ctx.expect
    m = opened()
    t = lambda n: utf(m.wtext[m.widgets[n]])
    expect(t('ab_title') == ALBUM and t('ab_artist') == ARTIST and t('ab_meta') == '1959 · 8 tracks', f'the title, the artist and "year · N tracks": {[t(n) for n in ("ab_title", "ab_artist", "ab_meta")]}')
    for n, year, want in ((1, 1959, '1959 · 1 track'), (3, 0, '3 tracks'), (3, 99, '3 tracks'), (3, 3000, '3 tracks'), (1, 0, '1 track'), (12, 1001, '1001 · 12 tracks')):
        m2 = opened(n=n, year=year)
        expect(utf(m2.wtext[m2.widgets['ab_meta']]) == want, f'{n} tracks, year {year}: "{want}"')
        m2.call(PSYMS['ab_on_destroy'], count=4000000)
    m2 = opened(titles=NAMES)
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # the first track with a year (1000..2999) names it
    m2 = album_machine(n=4); m2.setword(m2.songs[0] + O['REC_YEAR'], 0); m2.setword(m2.songs[1] + O['REC_YEAR'], 77); m2.setword(m2.songs[2] + O['REC_YEAR'], 1971)
    open_album(m2)
    expect(utf(m2.wtext[m2.widgets['ab_meta']]) == '1971 · 4 tracks', 'the first track that carries a year (1000 .. 2999) names it')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # the pill: glyph, 8 px, text centred as a pair
    for tw in (64, 40, 100, 140, 300):
        m2 = album_machine(); m2.measure = lambda text, tw=tw: tw if text else 0
        open_album(m2)
        fits = 16 + 8 + tw <= 180
        x = pill(tw if fits else O['AB_PLAY_TEXT_W'])
        expect(('widget_move', m2.widgets['ab_glyph'], x, 292 + 14) in m2.calls, f'a {tw} px text: the glyph at x {x}' + ('' if fits else ' (too wide: centred as the English one)'))
        blits, texts, fills = paint(m2)
        pt = [(t_, r) for (t_, r), s in texts if s == 'ab_play_text']
        expect(pt == [('Play', (x + 24, 292 + 11, (tw if fits else O['AB_PLAY_TEXT_W']) + O['AB_TEXT_SLACK'], 22))], f'a {tw} px text: painted 8 px after the glyph in a 22 px line in the middle of the pill ({pt})')
        m2.call(PSYMS['ab_on_destroy'], count=4000000)
    m2 = album_machine(); m2.measure = lambda text: 0
    open_album(m2)
    expect(('widget_move', m2.widgets['ab_glyph'], pill(O['AB_PLAY_TEXT_W']), 306) in m2.calls, 'a text that cannot be measured: the English place')
    # the translated text in every language fits the pill beside its glyph (the stock pill's own rule)
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    built = {loc: dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    over = [(loc, StbText(font, 18).layout(built[loc]['Play'])[1]) for loc in pod_i18n.LOCALES if 16 + 8 + StbText(font, 18).layout(built[loc]['Play'])[1] > 180 - 20]
    expect(not over, f'"Play" and its glyph fit the 180 px pill with a margin in all 13 languages ({over})')
    over = [(loc, w) for loc in pod_i18n.LOCALES for w in [StbText(font, 15).layout(built[loc]['%d tracks'].replace('%d', '9999'))[1] + StbText(font, 15).layout('1959 · ')[1]] if w > 286]
    expect(not over, f'"1959 · 9999 tracks" fits the meta line in all languages ({over})')
    # the cover: the cache file reduced to 160 px with the corners cut in the alpha, drawn at (80, 50)
    blits, texts, fills = paint(m)
    cov = [b for b in blits if b[2][2] == O['AH_ART']]
    expect(len(cov) == 1 and cov[0][2] == (80, 50, 160, 160) and cov[0][1] == (0, 0, 160, 160), f'the cover is a 160 px tile at (80, 50) ({cov})')
    bmp = cov[0][0]
    px = lambda x, y: SG.pixel(m, bmp, x, y)
    expect(bmp in m.bitmaps and m.bitmaps[bmp][1:] == (160, 160) and px(0, 0) >> 24 == 0 and px(159, 0) >> 24 == 0 and px(0, 159) >> 24 == 0 and px(159, 159) >> 24 == 0 and px(80, 80) >> 24 == 255
           and px(10, 0) >> 24 == 255 and px(0, 10) >> 24 == 255 and px(80, 80) & 0xffffff == RED[0] | RED[1] << 8 | RED[2] << 16,
           'the four 10 px corners are cut in the alpha (whatever lies behind shows: the tint), the picture is the file\'s colour')
    blits, texts, fills = paint(m) if scroll_to(m, 100) is None else (0, 0, 0)
    cov = [b for b in blits if b[2][2] == O['AH_ART']]
    expect(len(cov) == 1 and cov[0][1] == (0, 50, 160, 110) and cov[0][2] == (80, 0, 160, 110), f'scrolled 100 px the cover is cut at the window\'s top ({cov})')
    scroll_to(m, 300)
    blits, texts, fills = paint(m)
    expect(not [b for b in blits if b[2][2] == O['AH_ART']], 'scrolled past it the cover is not drawn')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a cover that is not there: the placeholder disc (rounded like a cover) while the worker makes the file
    m = album_machine(cover=None); open_album(m)
    blits, texts, fills = paint(m)
    cov = [b for b in blits if b[2][2] == O['AH_ART']]
    expect(len(cov) == 1 and cov[0][2] == (80, 50, 160, 160) and SG.pixel(m, cov[0][0], 0, 0) >> 24 == 0 and SG.pixel(m, cov[0][0], 80, 80) >> 24 == 255, 'no cache file: the placeholder disc, 160 px with the same corners')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def cover_tests(ctx):
    """5. The cover from the cache worker; the empty marker; the tint, the status bar and its hand-over; the tone cache."""
    expect = ctx.expect
    POLL = PSYMS['ab_on_cover']
    # the worker: one job, polled; the file appears and the cover and the tint follow
    m = album_machine(cover=None)
    open_album(m)
    s, jobs = build_state(m), build_jobs(m)
    expect(count_of(m, 'pthread_create') == 1 and s['running'] == 1 and s['mode'] == 0 and s['total'] == 1 and jobs == [('/mnt/mmc/m/0.flac', m.key)],
           f'no cache file: one worker with one job, the album\'s first track and key ({jobs})')
    expect(any(c[0] == 'timer_add' and c[1] == POLL and c[2] == O['AB_COVER_MS'] for c in m.calls), f'polled every {O["AB_COVER_MS"]} ms')
    expect(not m.win_colors() and not m.bar_styles(), 'the page is black until there is a cover')
    new = fired(m, 'ab_on_cover')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == POLL] and not [c for c in new if c[0] == 'pthread_join'], 'a poll with the worker running re-arms itself')
    m.present.add(m.cover_path); m.files[m.cover_path] = 4096
    m.images['file://' + m.cover_path] = (168, 168, bytes(RED + (255,)) * (168 * 168))
    m.setword(PSYMS['cb'] + 4 * 5, 1)
    new = fired(m, 'ab_on_cover')
    expect([c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] == 0 and not [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'the worker done: joined, the set freed, no more polls')
    blits, texts, fills = paint(m)
    cov = [b for b in blits if b[2][2] == O['AH_ART']]
    expect(cov and SG.pixel(m, cov[0][0], 80, 80) & 0xffffff == RED[0] | RED[1] << 8 | RED[2] << 16 and m.win_colors() == [tone_word(RED)] and m.bar_styles() and m.bar_styles()[-1] != BAR_BLACK,
           'the cover is drawn, the window takes its tone and the status bar the page\'s first row')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(m.bar_styles()[-1] == BAR_BLACK, 'closing the page: the bar is black again')
    # the worker made nothing (no art: the empty marker) or nothing yet: the placeholder, a black page
    m = album_machine(cover=None); open_album(m)
    m.present.add(m.cover_path); m.files[m.cover_path] = 0
    m.setword(PSYMS['cb'] + 4 * 5, 1); fired(m, 'ab_on_cover')
    blits, texts, fills = paint(m)
    cov = [b for b in blits if b[2][2] == O['AH_ART']]
    expect(cov and SG.pixel(m, cov[0][0], 80, 80) >> 24 == 255 and not m.win_colors() and not m.bar_styles(), 'an album with no art (the worker\'s empty marker): the placeholder disc, the page stays black, the bar untouched')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = album_machine(cover='marker'); calls = open_album(m)[1]
    expect('pthread_create' not in [c[0] for c in calls] and not m.win_colors() and not [c for c in calls if c[0] == 'widget_load_image' and c[1].endswith('.jpg')], 'the marker from Cover Flow\'s cache: no worker, no decode, black')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # another page holds the worker (Cover Flow's build): no job, the placeholder; nothing breaks
    m = album_machine(cover=None); m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=200000)
    open_album(m)
    expect(count_of(m, 'pthread_create') == 0 and not any(c[0] == 'timer_add' and c[1] == POLL for c in m.calls), 'the worker is held by another page: no job, no poll')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # closing the page cancels the worker it holds (orphaned until it exits)
    m = album_machine(cover=None); open_album(m)
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(build_state(m)['orphan'] == 1 and ('pthread_join',) not in m.calls and len(m.bitmaps) == 0, 'closing the page cancels the worker it holds without joining it and frees every bitmap')

    # ---- the tint of a page with a cover file
    BG, FG = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']
    covers = {'red': (190, 50, 55), 'blue': (40, 80, 190), 'grey': (120, 120, 124), 'bright': (240, 225, 150), 'black': (0, 0, 0), 'white': (255, 255, 255)}
    bad = []
    for name, rgb in covers.items():
        m = opened(rgb=rgb)
        if m.win_colors() != [tone_word(rgb)]: bad.append((name, m.win_colors()))
        m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(not bad, f'the window\'s colour is mod_nowplaying.tone of the cover\'s average (red, blue, grey, bright, black, white): {bad}')
    m = opened()
    expect(m.win_colors() == [tone_word(RED)] and ('widget_invalidate_force', m.window) in m.calls + [('widget_invalidate_force', m.window)], 'the window takes the tone of the cover file (the tone cache is empty)')
    loads = [c[1] for c in m.calls if c[0] == 'widget_load_image' and c[1].endswith('.jpg')]
    expect(len(loads) == 2, f'the cover file is decoded twice at the open: its average colour, and the 160 px picture ({len(loads)})')
    expect(len(m.bar_styles()) == 1 and m.bar_styles()[0] == bar_model(RED), f'the status bar takes the page\'s first row, darkened for the white glyphs ({[hex(x) for x in m.bar_styles()]})')
    c = m.bar_styles()[0]
    expect(contrast((c & 255, c >> 8 & 255, c >> 16 & 255), (255, 255, 255)) >= 4.5, 'the clock and glyphs keep 4.5:1 on it')
    # the hand-over: background -> black, foreground -> the colour, one owner
    m.fire(BG)
    expect(m.bar_styles()[-1] == BAR_BLACK, 'the page goes to the background: the bar is black again')
    m.fire(FG)
    expect(m.bar_styles()[-1] == bar_model(RED) and len(m.bar_styles()) == 3, 'back in front: the bar is the page\'s colour again')
    m.call(PSYMS['pod_bar_tint'], a0=0x1234, a1=0xff112233, count=200000)   # another page (Now Playing) takes the bar
    n = len(m.bar_styles())
    m.fire(BG)
    expect(len(m.bar_styles()) == n, 'the bar is another page\'s now: a late background event leaves it alone (one owner)')
    m.fire(FG); m.call(m.bound[(m.window, O['EVT_DESTROY'])][0], a0=m.bound[(m.window, O['EVT_DESTROY'])][1], count=4000000)
    # the tone cache: the album again tints at once, from RAM
    m2 = album_machine(cover='file'); r, calls = open_album(m2)
    expect(len([c for c in calls if c[0] == 'widget_load_image' and c[1].endswith('.jpg')]) == 2, 'a fresh machine has an empty cache')
    pk = PSYMS['pod_tone_get']
    tone_cache = m2.call(pk, a0=m2.key, a1=m2.alloc(8), count=200000)
    expect(tone_cache == 1, 'the tone was remembered for the album (pod_tone_put)')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    m2.images.pop('file://' + m2.cover_path); m2.present.discard(m2.cover_path); m2.files.pop(m2.cover_path)
    m2.windows.clear(); m2.styled.clear(); m2.calls = []
    r, calls = open_album(m2)
    expect(m2.win_colors() == [tone_word(RED)] and not [c for c in calls if c[0] == 'widget_load_image' and c[1].endswith('.jpg')], 'opened again with no file at all: the tone comes from the cache (no decode)')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # a bar that refuses the style call is not owed anything; a page without the window events never touches the bar
    m = album_machine(); m.bar_fail = True
    m.handlers[pod.FUNCTIONS['widget_set_style'][2]] = 'widget_set_style'
    m = album_machine(); m.widget_on_fail = frozenset({BG})
    open_album(m)
    expect(m.win_colors() == [tone_word(RED)] and not m.bar_styles(), 'without the window events registered the page tints its window but never the bar (it could not give it back)')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a page showing a cover in the dark / with no bar widget
    m = album_machine(); m.children[m.wm] = []
    open_album(m)
    expect(m.win_colors() == [tone_word(RED)], 'no status bar among the windows: the page is tinted all the same')
    expect(m.call(PSYMS['ab_has_tone'], count=20000) == 1, 'ab_has_tone: a tinted page shows a cover\'s tone (the Tinted wash leaves it alone)')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


def bar_model(rgb):
    """The status bar's colour for a page tinted from rgb: the tone under the overlay's first alpha, darkened until the white glyphs keep 4.5:1 (docs/modules/nowplaying.md)."""
    import mod_nowplaying as mn, mod_icons
    keep = 255 - mod_icons.ah_tint_alpha(0)
    r, g, b = (v * keep // 255 for v in mn.tone(*rgb))
    while 2126 * r * r + 7152 * g * g + 722 * b * b > O['NP_BAR_LUM_MAX']: r, g, b = r * 15 >> 4, g * 15 >> 4, b * 15 >> 4
    return 0xff000000 | r | g << 8 | b << 16


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def rows_tests(ctx):
    """6. The rows painted from the stock list."""
    expect = ctx.expect
    m = opened()
    blits, texts, fills = paint(m)
    num = [(t, r) for (t, r), s in texts if s == 'label_row_num']
    ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
    expect(num == [(str(i + 1), (12, row_y(i) + O['AB_TEXT_Y'], 22, 22)) for i in range(2)], f'the number (position + 1) right aligned in a 22 px column at x 12, a 22 px line AB_TEXT_Y down the row: {num}')
    expect(ttl == [(NAMES[i], (42, row_y(i) + O['AB_TEXT_Y'], 256, 22)) for i in range(2)], f'the title from x 42 (8 px after the number) to 298: {ttl}')
    order = [s for _, s in texts if s in ('label_row_num', 'label_row_title')]
    expect(order == ['label_row_num'] * 2 + ['label_row_title'] * 2, 'the numbers, then the titles: one text style at a time')
    hair = [f_ for f_ in fills if f_[0] == 0x22ffffff]   # AB_HAIR: 13 % white
    expect(hair == [(0x22ffffff, 0, row_y(0) + 63, 310, 1)], f'a 1 px hairline of 13 % white across the row\'s foot (row 1\'s lies below the window): {hair}')
    expect(len([1 for _, s in texts if s.startswith('label_row')]) == 4 and not [f_ for f_ in fills if f_[0] == 0x33ffffff], 'rows 0 and 1 are in view; nothing is pressed at rest')
    scroll_to(m, 300)
    blits, texts, fills = paint(m)
    seen = [t for (t, r), s in texts if s == 'label_row_title']
    last = (300 + WIN_H - 1 - HDR) // ROW   # the last row in the window: a line it cuts is drawn, the clip cuts it
    expect(seen == NAMES[:last + 1] and all(r[1] == row_y(i) + O['AB_TEXT_Y'] - 300 for i, ((t, r), s) in enumerate(x for x in texts if x[1] == 'label_row_title')),
           f'scrolled 300 px: rows 0 to {last} (the header is above the window), at their y less the offset ({seen})')
    # long titles are cut with an ellipsis at the room's end
    long_title = 'The Complete Concert in Paris, Olympia, 1961 (Remastered Live Edition)'
    m2 = opened(n=3, titles=[long_title, 'x', 'y'])
    blits, texts, fills = paint(m2)
    got = [t for (t, r), s in texts if s == 'label_row_title'][0]
    expect(got == SG.fitted(long_title, 256).encode('latin-1').decode('utf-8') or utf(got) == utf(SG.fitted(long_title, 256)), f'a title wider than its 256 px is cut with an ellipsis ({got!r})')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # a CUE track shows its file name, a track without a title its file name
    m2 = opened(n=4, titles=['A', '', 'C', 'D'], cues=(2,))
    scroll_to(m2, 200)
    blits, texts, fills = paint(m2)
    got = [t for (t, r), s in texts if s == 'label_row_title']
    expect(got == ['A', '1.flac', '2.flac', 'D'], f'a track with no title shows its file name, a CUE track (start > 0) always its file name ({got})')
    m2.call(PSYMS['ab_on_destroy'], count=4000000)
    # the playing row: a white title like the others, the wave marker in place of the number
    m.playing = ('1.flac', '/mnt/mmc/m/1.flac', 0)
    blits, texts, fills = paint(m)
    scroll_to(m, 0)
    blits, texts, fills = paint(m)
    styles = {s for _, s in texts}
    expect(styles - {'ab_play_text'} == {'label_row_num', 'label_row_title'} and [t for (t, r), s in texts if s == 'label_row_title'] == NAMES[:2],
           f'the playing track (is_playing: the file name and the url, the CUE start) keeps the white title style: no gold style ({styles})')
    num = [t for (t, r), s in texts if s == 'label_row_num']
    wv = [b for b in blits if b[2][2] == O['AB_WAVE'] and b[2][3] == O['AB_WAVE']]
    expect(num == ['1'] and len(wv) == 1 and wv[0][2][:2] == (12 + 22 - O['AB_WAVE'], row_y(1) + O['AB_TEXT_Y'] + (O['AB_TEXT_H'] - O['AB_WAVE']) // 2) and wv[0][1] == (0, 0, O['AB_WAVE'], O['AB_WAVE']),
           f'the playing row (row 1, the second) has no number but an AB_WAVE px wave right aligned in the number column, centred on the title line: {num} {[b[2] for b in wv]}')
    bm = wv[0][0]
    expect(SG.pixel(m, bm, 0, 0) >> 24 == 0 and SG.pixel(m, bm, 5, 8) == 0xff000000 | 0xECEEEE and (SG.pixel(m, bm, 5, 8) & 0xffffff) == 0xECEEEE,
           'the wave is #EEEEEC where the image has ink, transparent elsewhere')
    ip = [c for c in m.calls if c[0] == 'is_playing']
    expect(ip and all(c[1] == LIB and c[2] == 0 for c in ip), 'is_playing is asked with the browsing class and the CUE start, as the stock row builder does')
    # three-digit numbers: a 32 px column, the title 10 px further
    big = opened(n=130, titles=[f'T{i}' for i in range(130)])
    scroll_to(big, HDR + 97 * ROW)
    blits, texts, fills = paint(big)
    num = {t: r for (t, r), s in texts if s == 'label_row_num'}
    ttl = {t: r for (t, r), s in texts if s == 'label_row_title'}
    expect(num['99'][2] == 22 and num['100'][2] == 32 and num['100'][0] == 12 and ttl['T98'][0] == 42 and ttl['T99'][0] == 52 and ttl['T99'][2] == 246 and ttl['T98'][2] == 256,
           f'row 99 has a 22 px column, row 100 a 32 px one: the title starts at x 52 and is 246 px wide ({num["100"]}, {ttl["T99"]})')
    expect(big.props[(big.sv, 'virtual_h')] == HDR + 130 * ROW, 'the content grows with the tracks')
    scroll_to(big, HDR + 130 * ROW + 5000)
    blits, texts, fills = paint(big)
    expect(not any(c[0] == 'deque_at_oob' for c in big.calls), 'a list pulled past its end reads no record beyond it')
    big.call(PSYMS['ab_on_destroy'], count=4000000)
    # a short album cannot scroll: the content is shorter than the window
    m3 = opened(n=2)
    expect(m3.props[(m3.sv, 'virtual_h')] == HDR + 2 * ROW, 'two tracks: the content is 472 px')
    m3.call(PSYMS['ab_on_destroy'], count=4000000)
    m.call(PSYMS['ab_on_destroy'], count=4000000)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def play_tests(ctx):
    """7. Taps: a track, Play, Shuffle; the press fill; the stock list replaced under the page; back from Now Playing."""
    expect = ctx.expect
    m = opened()
    m.watch[PSYMS['pod_open_player']] = 'pod_open_player'; m.hooked and None
    calls = tap(m, 150, row_y(1) + 20)
    pl = [c for c in calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
    ls = [c for c in calls if c[0] == 'loadSongList']
    expect(pl and m.played[1] == 1 and m.played[0] == m.songs and m.word(G_CLASS) == LIB and ls[0][1:] == ('1.flac', 0, LIB) and [c for c in calls if c[0] == 'pod_open_player'],
           'a tap on a track: loadSongList of the album (class 0xff10), Now Playing at that row through the stock row handler\'s tail (pod_open_player)')
    expect(not any(c[0] == 'mclSetPlayMode' for c in calls), 'a track tap keeps the play mode (the stock row)')
    for label, dx, dy in (('a drag', 0, 14), ('a slide sideways', 12, 0)):
        expect(not [c for c in tap(m, 150, row_y(2) + 20, dx, dy) if c[0] == 'navigator_to_with_context'], f'{label} plays nothing')
    expect(not [c for c in tap(m, 150, 100) if c[0] == 'navigator_to_with_context'] and not [c for c in tap(m, 150, 330) if c[0] == 'navigator_to_with_context'], 'a tap on the header (the cover, the lines, the gap above the first row) plays nothing')
    touch(m, 'down', 150, row_y(0) + 20, 'ab_on_down')
    _, _, fills = paint(m)
    expect((0x33ffffff, 0, row_y(0), 310, ROW) in fills, f'the row under the finger is filled 20 % white over its whole 64 px: {[f_ for f_ in fills if f_[0] == 0x33ffffff]}')
    touch(m, 'abort', 150, row_y(0) + 20, 'ab_on_abort')
    _, _, fills = paint(m)
    expect(not any(f_[0] == O['AB_PRESS'] for f_ in fills), 'an abort (the scroll_view took a drag) clears it')
    touch(m, 'down', 150, row_y(1) + 20, 'ab_on_down'); touch(m, 'up', 150, row_y(1) + 20, 'ab_on_up', 1080)
    _, _, fills = paint(m)
    expect(not any(f_[0] == O['AB_PRESS'] for f_ in fills), 'and a release')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # Play: the first track in order (Shuffle and Repeat one become List play); Shuffle: a random track in the stock Shuffle mode
    for before, after in ((0, 0), (1, 0), (2, 0), (3, 3)):
        m = opened(); m.mode = before
        calls = click(m, 'btn_play')
        expect(m.played[1] == 0 and m.played[0] == m.songs and m.mode == after and (('mclSetPlayMode', after) in calls) == (before != after) and [c for c in calls if c[0] == 'loadSongList'][0][1:] == ('0.flac', 0, LIB),
               f'Play from mode {before}: the first track of the album, mode {after}')
        m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = opened(); m.mode = 0
    calls = click(m, 'btn_shuffle')
    expect(('mclSetPlayMode', 2) in calls and m.mode == 2 and 0 <= m.played[1] < 8 and m.played[0] == m.songs and [c for c in calls if c[0] == 'loadSongList'][0][3] == LIB,
           'Shuffle: the stock Shuffle mode, a random track of the album as the queue')
    picks = set()
    for k in range(12):
        m.seed = 100 + 7 * k; click(m, 'btn_shuffle'); picks.add(m.played[1])
    expect(len(picks) >= 3, f'Shuffle starts at different tracks ({sorted(picks)})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a missing file: the usual message, the page stays
    m = opened()
    m.present.discard('/mnt/mmc/m/0.flac'); m.played = None
    calls = click(m, 'btn_play')
    expect(m.played is None and any(c[0] == 'toast' and c[1] == 'Storage unavailable' for c in calls), 'a track that is not on the card: "Storage unavailable", nothing starts')
    # the album's class and record: another page changed the browsing record: it is put back before the query and before loadSongList
    m = opened()
    ci_before = bytes(m.u.mem_read(CI, O['CLASSINFO_SIZE']))
    m.u.mem_write(CI, b'\xaa' * O['CLASSINFO_SIZE'])
    calls = tap(m, 150, row_y(2) + 20)
    expect(bytes(m.u.mem_read(CI, O['CLASSINFO_SIZE'])) == ci_before and m.played[1] == 2 and m.played[0] == m.songs, 'another page overwrote the browsing record: the page puts its snapshot back before it plays')
    # a stock list replaced under the page: nothing of it is read; the page reads the tracks again when it is on top
    m.setword(SHOWLIST, m.new_deque(m.songs[:3]))
    blits, texts, fills = paint(m)
    expect(not [t for (t, r), s in texts if s == 'label_row_title'] and any(c[0] == 'timer_add' and c[1] == PSYMS['ab_on_stale'] for c in m.calls), 'the stock list replaced: a paint reads nothing of it and arms the one-shot timer')
    expect(not [c for c in tap(m, 150, row_y(1) + 20) if c[0] == 'navigator_to_with_context'], 'a tap on rows that are not the page\'s plays nothing')
    m.top_main = m.window
    fired(m, 'ab_on_stale')
    expect(('loadLocalClassList', LIB) in m.calls or 'loadLocalClassList' in m.names(), 'on top, the page reads its tracks again')
    blits, texts, fills = paint(m)
    expect(len([t for (t, r), s in texts if s == 'label_row_title']) == 2, 'and paints them')
    # back in front (from Now Playing): a list that is still the page's is not read again
    m.calls = []
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect('loadLocalClassList' not in m.names(), 'back in front with its list intact: nothing is read again')
    m.setword(SHOWLIST, m.new_deque([])); m.calls = []
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect('loadLocalClassList' in m.names() and off_of(m) == 0, 'back in front with the list replaced: read again')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # the list is empty (the tracks were deleted elsewhere): "No songs", the header is gone with the content view
    m = album_machine(); m.album_tracks = {}
    r, calls = open_album(m)
    expect(r == 0 and vis(m, 'view_grid') == (0, 0) and vis(m, 'label_status') == (1, 1) and m.wtext[m.widgets['label_status']] == 'No songs', 'an album with no tracks: the page opens with the message')
    click(m, 'btn_play'); click(m, 'btn_shuffle'); click(m, 'btn_select')
    expect(m.played is None and ('widget_set_visible', m.widgets['btn_selall'], 1) not in m.calls and not any(c[0] == 'loadSongList' for c in m.calls), 'Play, Shuffle and Select do nothing on it')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # Back and Now Playing
    m = opened()
    calls = click(m, 'btn_return')
    expect(('navigator_back',) in calls, 'Back goes back')
    calls = click(m, 'btn_backtoplayer')
    expect(('on_backtoplayer_onclick',) in calls or any(c[0] == 'on_backtoplayer_onclick' for c in calls), 'Now Playing is the stock "back to the player" button')
    m.call(PSYMS['ab_on_destroy'], count=4000000)




def select_tests(ctx):
    """8. Select mode: the glass toggle, Add, Delete and Cancel in place of Back and the capsule; the marks; Delete and Add on the stock selection vector."""
    expect = ctx.expect
    OFF = 200   # the list scrolled: the first five rows are in view
    ty = lambda i: row_y(i) - OFF + 20   # the tap point on row i
    m = opened()
    click(m, 'btn_select')
    expect(all(vis(m, n) == (0, 0) for n in ('btn_return', 'btn_select', 'btn_backtoplayer')) and all(vis(m, n) == (1, 1) for n in ('btn_selall', 'sg_add', 'sg_del', 'btn_cancel')),
           'Select hides Back and the capsule and shows the toggle, Add, Delete and Cancel (glass, in the places the stock builder gave them)')
    expect(('widget_set_sensitive', m.widgets['btn_play'], 0) in m.calls and ('widget_set_sensitive', m.widgets['btn_shuffle'], 0) in m.calls, 'the header\'s buttons are dead')
    tg = m.widgets['btn_selall']
    expect(m.props[(tg, 'style:normal:icon')] == 'ah_nav_unsel' and m.props[(tg, 'style:pressed:icon')] == 'ah_nav_unsel_down', 'the toggle is the open circle')
    scroll_to(m, OFF)
    blits, texts, fills = paint(m)
    marks = [b for b in blits if b[2][2] == O['SG_MARK']]
    num = [(t, r) for (t, r), s in texts if s == 'label_row_num']
    ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
    expect(len(marks) == 5 and all(b[2][0] == 9 for b in marks) and [b[2][1] for b in marks] == [row_y(i) + 19 - OFF for i in range(5)]
           and num[0][1][0] == 12 + O['SG_SEL_COL'] and ttl[0][1][0] == 42 + O['SG_SEL_COL'] and ttl[0][1][2] == 256 - O['SG_SEL_COL'],
           f'a 26 px mark on each row, the number and the title 30 px right (the title 30 px narrower): {len(marks)} marks')
    off_mark = marks[0][0]
    pix = lambda x, y: SG.pixel(m, off_mark, x, y)
    expect(pix(0, 0) >> 24 == 0 and pix(13, 13) >> 24 == 255, 'the mark is cut to its circle')
    tap(m, 150, ty(1)); tap(m, 150, ty(3))
    expect(not any(c[0] == 'navigator_to_with_context' for c in m.calls), 'a tap marks a row and plays nothing')
    blits, texts, fills = paint(m)
    marks = {b[2][1]: b[0] for b in blits if b[2][2] == O['SG_MARK']}
    expect(marks[row_y(1) + 19 - OFF] != off_mark and marks[row_y(3) + 19 - OFF] != off_mark and marks[row_y(0) + 19 - OFF] == off_mark and marks[row_y(2) + 19 - OFF] == off_mark,
           'the two marked rows show the selected mark')
    expect(not any(f_[0] == O['AB_PRESS'] for f_ in fills), 'no press fill in select mode')
    tap(m, 150, ty(1))
    click(m, 'btn_selall')
    expect(m.props[(tg, 'style:normal:icon')] == 'ah_nav_sel' and m.props[(tg, 'style:pressed:icon')] == 'ah_nav_sel', 'Select all marks everything: the toggle is the checked circle')
    tap(m, 150, ty(2))
    expect(m.props[(tg, 'style:normal:icon')] == 'ah_nav_unsel', 'a track unmarked: the open circle again')
    click(m, 'btn_selall'); click(m, 'btn_selall')
    expect(m.props[(tg, 'style:normal:icon')] == 'ah_nav_unsel', 'all, then none: the open circle')
    # Delete
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'toast' and c[1] == 'msg_delsongfailed' for c in calls) and not any(c[0] == 'confirm' for c in calls), 'Delete with nothing marked: the stock "failed" message, no dialog')
    tap(m, 150, ty(1)); tap(m, 150, ty(4))
    m.confirm_answer = 0
    calls = click(m, 'sg_del')
    expect(any(c[0] == 'confirm' and c[1] == 'msg_delsong' and c[2] == O['CONFIRM_KIND_DELETE'] for c in calls) and not any(c[0] in ('batch_delete_file', 'select_recordinit') for c in calls),
           'Delete asks with the stock confirm dialog; No deletes nothing')
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    list_h = m.word(SHOWLIST)
    calls = click(m, 'sg_del')
    bd = [c for c in calls if c[0] == 'batch_delete_file']
    expect(bd and bd[0][1:6] == (LIB, list_h, m.word(SEL_VEC), 0, 0) and bd[0][6] == [1, 4] and ('select_recordinit', 8) in calls and [c[1] for c in calls if c[0] == 'set_selectindex'] == [1, 4]
           and any(c[0] == 'toast' and c[1] == 'msg_delsongsuccess' for c in calls) and [c[1] for c in calls if c[0] == 'loadLocalClassList'] == [LIB],
           'Yes: batch_delete_file(0xff10, the album\'s list, the stock vector, 0, 0) on the marked rows, the message, the tracks read again')
    expect(all(vis(m, n) == (1, 1) for n in ('btn_return', 'btn_select', 'btn_backtoplayer')) and all(vis(m, n) == (0, 0) for n in ('btn_selall', 'sg_add', 'sg_del', 'btn_cancel')), 'and select mode is over')
    scroll_to(m, 0)
    click(m, 'btn_select'); tap(m, 150, row_y(0) + 20)
    m.confirm_answer = O['CONFIRM_DELETE_FILE']
    bd = [c for c in click(m, 'sg_del') if c[0] == 'batch_delete_file']
    expect(bd and bd[0][5] == 1 and bd[0][6] == [0], 'the second answer (also the file) sets the delete-file flag')
    m.confirm_answer = None
    # Add
    click(m, 'btn_select')
    calls = click(m, 'sg_add')
    expect(any(c[0] == 'toast' and c[1] == 'msg_addfailed' for c in calls) and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playlist_page' for c in calls), 'Add with nothing marked: the stock message')
    tap(m, 150, row_y(0) + 20)
    m.windows['m1plus_playlists'] = 0   # our picker's page does not open: the stock picker (test/pod/picker.py is ours)
    m.u.mem_write(NAV_TITLE, b'Album title\0'); m.setword(G_CLASS, 0xf00b); m.setword(pod.DATA['NAVIGATION_STATUS'][0], 1)
    calls = click(m, 'sg_add')
    expect([c[1] for c in calls if c[0] == 'set_selectindex'] == [0] and ('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | LIB) in calls and m.word(pod.DATA['NAVIGATION_STATUS'][0]) == 0,
           'Add fills the stock vector and opens the stock playlist picker with 1 << 16 | 0xff10')
    m.u.mem_write(NAV_TITLE, b'Mix\0'); m.setword(G_CLASS, 0xf00b)
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.word(G_CLASS) == LIB and m.read_cstr(NAV_TITLE) == 'Album title' and vis(m, 'sg_add') == (0, 0) and 'loadLocalClassList' in m.names(),
           'back from the picker: the class and the title are put back, select mode is over, the tracks are read again')
    # Cancel leaves select mode
    click(m, 'btn_select')
    calls = click(m, 'btn_cancel')
    expect(vis(m, 'sg_del') == (0, 0) and vis(m, 'btn_return') == (1, 1) and not any(c[0] == 'navigator_back' for c in calls), 'Cancel leaves select mode (and does not go back)')
    # the stock list replaced under select mode: nothing is acted on, the page reads its tracks again
    click(m, 'btn_select'); tap(m, 150, row_y(1) + 20)
    m.setword(SHOWLIST, m.new_deque(m.songs[:3]))
    m.confirm_answer = O['CONFIRM_DELETE_LIBRARY']
    calls = click(m, 'sg_del')
    expect(not any(c[0] == 'batch_delete_file' for c in calls) and vis(m, 'sg_del') == (0, 0) and 'loadLocalClassList' in [c[0] for c in calls],
           'the stock list is not the page\'s any more: Delete deletes nothing and the page reads its tracks again')
    m.confirm_answer = None
    m.call(PSYMS['ab_on_destroy'], count=4000000)


class FakeAP(AM):
    """AM plus a fake non-stock library source (names fake_ap_*): its lib_src_t lives in emulator memory, its members are trapped addresses answered here. Tracks are records
    with synthetic ids and "nd://" paths; every call is recorded in m.calls."""
    gen = 1
    gen_rows = None     # what src->gen_rows answers (None: the same as gen)
    cover_ret = 1
    seconds_of = None   # record address -> seconds
    row_of = None       # record address -> (dl, pct, dsd, fav, offline): the ls_row_t src->row fills (absent: all 0)
    playing_rec = None  # the record address src->playing says is playing (None: nothing)
    play_ret = 0        # what src->play answers (-2: a DSD track that is not downloaded)
    act_ret = -1        # what src->act answers
    queue_none = False  # src->queue_row answers NULL
    acts = None         # [(record address, what)] src->act was called with
    queued = None       # [record address] src->queue_row was asked for

    def fake_src(self, n=5, album='Fake Album', artist='Fake Artist', cover_ret=1, secs=(60, 120, 180, 240, 300), with_playing=False):
        self.cover_ret = cover_ret
        self.fake_tracks = []
        self.seconds_of = {}
        for i in range(n):
            r = self.record(album=album, artist=artist, path=f'nd://t{i}', title=f'Remote {i}', name='', rid=-3 - i)
            self.setword(r + O['REC_YEAR'], 2001)
            self.fake_tracks.append(r); self.seconds_of[r] = secs[i % len(secs)]
        self.fake_row = self.record(album=album, artist=artist, path='nd://al1', title=album, name='', rid=-50)
        self.fake_key = album_key(artist, album)
        self.fake_cover = '/mnt/mmc/.m1plus/subsonic/covers/%08x-168.jpg' % self.fake_key   # the source's own file, named by the source (never the Cover Flow cache file of the key, which stays absent)
        old = art_file(self.fake_key)
        if old in self.present:   # (album_machine made the picture at the Cover Flow path: move it to the source's)
            self.present.discard(old); self.present.add(self.fake_cover); self.files[self.fake_cover] = self.files.pop(old, 4096)
            if 'file://' + old in self.images: self.images['file://' + self.fake_cover] = self.images.pop('file://' + old)
        addrs = {}
        for nm in ('list', 'rec_id', 'play', 'cover', 'seconds', 'row', 'act', 'gen', 'playing', 'queue_row', 'state', 'gen_rows'):
            addrs[nm] = self.alloc(16); self.handlers[addrs[nm]] = 'fake_ap_' + nm
        self.src = self.alloc(64)
        self.setword(self.src, self.cstr('fake'))
        for i, nm in enumerate(('list', 'rec_id', 'play', 'cover', 'seconds', 'row', 'act', 'gen')): self.setword(self.src + 4 * (i + 1), addrs[nm])
        self.row_of = {}
        if with_playing: self.setword(self.src + 40, addrs['playing'])   # lib_src_t.playing, after complete (offset 36)
        self.setword(self.src + 44, addrs['queue_row'])   # lib_src_t.queue_row
        self.setword(self.src + 60, addrs['gen_rows'])   # lib_src_t.gen_rows (offset 60, after state; src is 64 bytes)
        self.setword(self.src + 56, addrs['state'])   # lib_src_t.state (offset 56, after count), the last member
        self.state_ret = 0   # LS_ST_READY
        self.acts, self.queued, self.acts_dd = [], [], []   # acts_dd: the deques destroyed before each act (a record the act reads must still be alive)
        return self

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if not name.startswith('fake_ap_'): return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        sp = u.reg_read(UC_MIPS_REG_SP)
        ret = 0
        if name == 'fake_ap_list':
            self.calls.append((name, a1, a2))
            ret = self.new_deque(self.fake_tracks) if a1 == 2 and self.fake_tracks else 0
        elif name == 'fake_ap_rec_id':
            ret = self.cstr(self.read_cstr(self.word(a1 + O['REC_PATH']))[5:])
        elif name == 'fake_ap_play':
            self.calls.append((name, a1, a2 & 0xffffffff, a3, self.word(sp + 16), self.word(sp + 20)))
            self.played_src = ([self.read_cstr(self.word(r + O['REC_PATH'])) for r in self.deques[a1]], a2 & 0xffffffff, a3)
            ret = self.play_ret
        elif name == 'fake_ap_cover':
            self.calls.append((name, a1, a2, self.cover_ret)); ret = self.cover_ret & 0xffffffff
            if self.cover_ret == 1: self.u.mem_write(a3, self.fake_cover.encode() + b'\0')   # (the file the source names, not the page's key's)
        elif name == 'fake_ap_seconds':
            ret = self.seconds_of.get(a1, 0)
        elif name == 'fake_ap_gen':
            ret = self.gen
        elif name == 'fake_ap_gen_rows':
            ret = self.gen if self.gen_rows is None else self.gen_rows
        elif name == 'fake_ap_act':
            self.acts_dd.append(sum(c[0] == 'deque_destroy' for c in self.calls)); self.calls.append((name, a2)); self.acts.append((a1, a2)); ret = self.act_ret
        elif name == 'fake_ap_queue_row':
            self.queued.append(a1); self.calls.append((name,))
            ret = 0
            if not self.queue_none:   # the queue record: the stream address in REC_PATH, the id the map would give
                title = self.read_cstr(self.word(a1 + O['REC_TITLE']))
                ret = self.new_deque([self.record(album='Fake Album', artist='Fake Artist', path=f'http://nd.example/stream?id={title}', title=title, name=f'{title}.flac', rid=-1000 - len(self.queued))])
        elif name == 'fake_ap_row':
            self.u.mem_write(a2, struct.pack('<5i', *self.row_of.get(a1, (0, 0, 0, 0, 0))))
        elif name == 'fake_ap_state':
            self.calls.append((name, a1, a2)); ret = self.state_ret
        elif name == 'fake_ap_playing':
            ret = int(a1 == self.playing_rec)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def fake_machine(**kw):
    ret, wp = kw.pop('cover_ret', 1), kw.pop('with_playing', False)
    m = album_machine(album='Fake Album', artist='Fake Artist', **kw)   # (the cover cache file is the fake album's)
    m.__class__ = FakeAP
    m.top_main = m.window   # pod_is_top: the page is in front (the shared cover poll only runs then)
    return m.fake_src(cover_ret=ret, with_playing=wp)


def source_tests(ctx):
    """7. album_open_src: NULL and &lib_stock are album_open; a fake source's tracks, cover, footer, play and gen."""
    expect = ctx.expect
    LS_SONGS = 2
    # stock unchanged
    for which in (0, PSYMS['lib_stock']):
        m = album_machine()
        r = m.call(PSYMS['album_open_src'], a0=which, a1=ALBUMS, a2=m.row, count=900000000)
        calls = list(m.calls)
        expect(not any(v[1:] == (28, 28) for v in m.bitmaps.values()) and ('timer_add', PSYMS['ls_cover_tick'], 250) not in calls, f'src {which:#x}: no cover spinner on the stock page')
        expect(r == 0 and ('window_open', 'm1plus_album') in calls and ('loadAlbumdetailList', ALBUMS, m.row) in calls and m.word(G_CLASS) == LIB
               and utf(m.wtext[m.widgets['ab_title']]) == ALBUM and vis(m, 'btn_select') == (1, 1),
               f'album_open_src({"NULL" if not which else "&lib_stock"}) is album_open: the stock query, the stock class, the select button ({r}, {calls[:10]})')
        m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a fake source
    m = fake_machine(n=5)
    m.setword(G_CLASS, 0x1234)
    r = m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    calls = list(m.calls)
    expect(r == 0 and ('window_open', 'm1plus_album') in calls and [c[1] for c in calls if c[0] == 'fake_ap_list'] == [LS_SONGS],
           f'the fake source opens the page and is asked for LS_SONGS: {r} {calls[:12]}')
    expect(not any(c[0] in ('loadAlbumdetailList', 'loadLocalClassList') for c in calls) and m.word(G_CLASS) == 0x1234, 'no stock query runs and the stock class is left alone')
    scope = [c for c in calls if c[0] == 'fake_ap_list'][0][2]
    expect(('_deque_push_back', m.deques and [c for c in calls if c[0] == '_deque_push_back'][0][1], m.fake_row) in calls and m.read_cstr(m.word(scope + O['REC_PATH'])) == 'nd://al1',
           'the scope is the album row, pushed into the page\'s own one-record deque')
    expect(utf(m.wtext[m.widgets['ab_title']]) == 'Fake Album' and utf(m.wtext[m.widgets['ab_artist']]) == 'Fake Artist' and utf(m.wtext[m.widgets['ab_meta']]) == '2001 \xb7 5 tracks',
           f'the header texts come from the row and the tracks: {m.wtext[m.widgets["ab_title"]]!r} {m.wtext[m.widgets["ab_meta"]]!r}')
    expect(vis(m, 'btn_select') == (0, 0) and vis(m, 'btn_return') == (1, 1) and vis(m, 'btn_backtoplayer') == (1, 1), 'the Select button is hidden (no select mode on a source page yet)')
    expect(vis(m, 'btn_more') == (1, 1) and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) is None, 'a source page: the "..." shows in Select\'s place and Now Playing stays the capsule\'s right cap')
    expect(utf(m.wtext[m.widgets['ab_foot']]) == '5 tracks, 15 minutes' and vis(m, 'ab_foot')[0] == 1, f'the footer is the sum of src->seconds: {m.wtext[m.widgets["ab_foot"]]!r}')
    expect(not any(c[0] in ('cc_build_open',) for c in calls) and not any(c[0].startswith('dur_') for c in calls), 'no cover or length worker, no durations table')
    blits, texts, fills = paint(m)
    flat = ' '.join(str(t) for t in texts)
    expect('Remote 0' in flat and 'Remote 1' in flat, f'the rows paint the fake tracks: {flat[:200]}')
    expect(len(blits) >= 1, 'the header cover (the cache file the source says is there) is blitted')
    expect(m.win_colors(), 'the window is tinted from the cover')
    # the playing marker: by the "nd://" url, a stock file name never matches
    m.playing = ('', 'nd://t0', 0)
    scroll_to(m, 0)
    blits, texts, fills = paint(m)
    wv = [b for b in blits if b[2][2] == O['AB_WAVE'] and b[2][3] == O['AB_WAVE']]
    num = [t for (t, r), s_ in texts if s_ == 'label_row_num']
    expect(len(wv) == 1 and wv[0][2][1] == row_y(0) + O['AB_TEXT_Y'] + (O['AB_TEXT_H'] - O['AB_WAVE']) // 2 and '1' not in num and '2' in num,
           f'the track whose url plays (row 0) has the wave in place of its number: {num} {[b[2] for b in wv]}')
    m.playing = ('0.flac', '/mnt/mmc/m/0.flac', 0)
    wv = [b for b in paint(m)[0] if b[2][2] == O['AB_WAVE'] and b[2][3] == O['AB_WAVE']]
    expect(not wv, 'a stock path that plays marks nothing on a source page')
    # play
    m.played_src = None
    calls = tap(m, 150, row_y(3) + 20)
    pl = [c for c in calls if c[0] == 'fake_ap_play']
    expect(pl and pl[0][2] == 3 and pl[0][3] == 0 and m.played_src[0] == [f'nd://t{i}' for i in range(5)] and not any(c[0] in ('loadSongList', 'start_player') for c in calls),
           f'a row tap plays through src->play at its index, how LS_PLAY_KEEP: {pl}')
    calls = click(m, 'btn_play')
    pl = [c for c in calls if c[0] == 'fake_ap_play']
    expect(pl and pl[0][2] == 0 and pl[0][3] == 1, f'Play: index 0, in order: {pl}')
    calls = click(m, 'btn_shuffle')
    pl = [c for c in calls if c[0] == 'fake_ap_play']
    expect(pl and pl[0][2] == 0xffffffff and pl[0][3] == 2, f'Shuffle: index -1, shuffle: {pl}')
    # gen moves: the tracks are read again
    m.fake_tracks = m.fake_tracks[:3]
    m.gen = 2
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    calls = list(m.calls)
    expect(any(c[0] == 'fake_ap_list' for c in calls) and utf(m.wtext[m.widgets['ab_meta']]) == '2001 \xb7 3 tracks' and utf(m.wtext[m.widgets['ab_foot']]) == '3 tracks, 6 minutes',
           f'a gen change reads the tracks again: {calls[:8]} {m.wtext[m.widgets["ab_meta"]]!r}')
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(not any(c[0] == 'fake_ap_list' for c in m.calls), 'the same gen reads nothing')
    # gen alone moves (a download's progress): the rows are painted again, the list is not read
    m.gen_rows = 2; m.gen = 4
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(not any(c[0] == 'fake_ap_list' for c in m.calls), 'a move of gen alone reads no list')
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(not any(c[0] == 'fake_ap_list' for c in m.calls), 'the new gen was recorded: the next tick does nothing')
    # gen_rows moves: the list is read; held back by a finger until it is up
    m.gen_rows = 3; m.gen = 5
    touch(m, 'down', 150, row_y(0) + 20, 'ab_on_down')
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(not any(c[0] == 'fake_ap_list' for c in m.calls), 'a finger is down: the list is not read')
    touch(m, 'up', 150, row_y(0) + 20, 'ab_on_up', 1080)
    m.calls = []
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(any(c[0] == 'fake_ap_list' for c in m.calls), 'a move of gen_rows reads the list at the first tick after the release')
    m.gen_rows = None
    # an unknown length: no footer
    m.seconds_of[m.fake_tracks[1]] = 0
    m.gen = 6
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(vis(m, 'ab_foot')[0] == 0, 'a track whose length the source does not know: no footer')
    nd = len([c for c in m.calls if c[0] == 'deque_destroy'])
    m.calls = []
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    expect(len([c for c in m.calls if c[0] == 'deque_destroy']) == 2, f'destroy frees the page\'s track list and its copy of the row ({nd} before)')
    # a cover that is asked for: polled, then shown
    def spin_images(m):
        for i in range(8): m.images[f'wf_spinL{i}'] = (28, 28, bytes((0x55, 0x55, 0x55, 255)) * (28 * 28))   # (the 28 px frames as cc_decode flattens them over black)

    def spinners(m): return [b for b in paint(m)[0] if m.bitmaps[b[0]][1:] == (28, 28)]
    m = fake_machine(n=3, cover=None, cover_ret=0)
    spin_images(m)
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    calls = list(m.calls)
    sp = spinners(m)
    expect(len(sp) == 1 and sp[0][2] == (O['AH_ART_X'] + (O['AH_ART'] - 28) // 2, O['AH_ART_Y'] + (O['AH_ART'] - 28) // 2, 28, 28) and ('timer_add', PSYMS['ls_cover_tick'], 250) in calls,
           f'a cover asked for: the 28 px spinner centred on the header cover, turned by the shared 250 ms cover poll: {[b[2] for b in sp]}')
    expect(m.call(PSYMS['ls_cover_tick'], a0=0x5a5a5a50, count=80000000) == 8 and spinners(m)[0][0] != sp[0][0], 'a tick repeats and turns the frame (its argument is stock\'s timer_info_t: not read)')
    expect(any(c[0] == 'fake_ap_cover' for c in calls) and ('timer_add', PSYMS['ls_cover_tick'], 250) in calls and not any(c[0] == 'cc_build_open' for c in calls),
           f'no file: src->cover is asked and polled, the cache worker is not used: {calls[-6:]}')
    m.present.add(m.fake_cover); m.files[m.fake_cover] = 4096; m.cover_ret = 1   # (the source answers 1 and names the file now)
    m.images['file://' + m.fake_cover] = (168, 168, bytes(RED + (255,)) * (168 * 168))
    m.call(PSYMS['ls_cover_tick'], count=80000000)
    blits, _, _ = paint(m)
    expect(len(blits) >= 1 and m.win_colors(), 'the file arrived: the cover is shown and the window tinted')
    expect(not spinners(m) and [m.call(PSYMS['ls_cover_tick'], count=80000000) for _ in range(3)][-1] != 8, 'and the spinner is gone, the shared poll ends')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # no cover at all (-1): the placeholder, no timer
    m = fake_machine(n=3, cover=None, cover_ret=-1)
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    expect(not any(c[0] == 'timer_add' and c[1] == PSYMS['ls_cover_tick'] for c in m.calls), 'src->cover -1: the placeholder, nothing polled')
    expect(not spinners(m), 'and no spinner')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # the poll gives up (libsrc LS_COVER_POLLS, the one rule): the placeholder stays, the spinner goes
    m = fake_machine(n=3, cover=None, cover_ret=0)
    spin_images(m)
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    for _ in range(1199): m.call(PSYMS['ls_cover_tick'], count=80000000)
    expect(len(spinners(m)) == 1, 'still polled: still the spinner')
    m.call(PSYMS['ls_cover_tick'], count=80000000); m.call(PSYMS['ls_cover_tick'], count=80000000)
    expect(not spinners(m) and m.call(PSYMS['ls_cover_tick'], count=80000000) != 8, 'the last poll found nothing: no spinner, the poll ends')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a page that is not on top asks nothing and turns nothing
    m = fake_machine(n=3, cover=None, cover_ret=0)
    spin_images(m)
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    m.top_main = 0; m.calls = []
    expect(m.call(PSYMS['ls_cover_tick'], count=80000000) == 8 and not [c for c in m.calls if c[0] == 'fake_ap_cover'], 'not the top window: the poll waits, the source is not asked')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # an empty source list
    m = fake_machine(n=3)
    m.fake_tracks = []
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    expect(vis(m, 'label_status')[0] == 1 and vis(m, 'view_grid')[0] == 0, 'a source without tracks: the "No songs" status')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


def loading_tests(ctx):
    """A source's album opened before its tracks are cached: the normal layout (header texts, cover) with the spinner in the track area, never the empty text; the rows fill in when
    they arrive; an answer of zero tracks (or a failed request) is the empty state."""
    expect = ctx.expect
    LS_SONGS = 2

    def status(m): return m.wtext.get(m.widgets['label_status'], '')

    m = fake_machine(n=5)
    m.fake_tracks, m.state_ret = [], 1   # LS_ST_LOADING
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    calls = list(m.calls)
    expect(any(c[:2] == ('fake_ap_state', LS_SONGS) for c in calls), f'the page asks src->state(LS_SONGS, the album row): {calls[:10]}')
    expect(vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status')[0] == 0 and vis(m, 'ab_spin')[0] == 1, 'loading: the content view (header) shows, the spinner is up, no status line')
    expect(all(vis(m, n)[0] == 0 for n in ('btn_play', 'btn_shuffle', 'ab_glyph')) and vis(m, 'btn_play')[1] == 0 and vis(m, 'btn_shuffle')[1] == 0,
           'loading: the Shuffle disc and the Play pill (buttons and glyph) are hidden and insensitive')

    expect(utf(m.wtext[m.widgets['ab_title']]) == 'Fake Album' and utf(m.wtext[m.widgets['ab_artist']]) == 'Fake Artist' and utf(m.wtext[m.widgets['ab_meta']]) == '',
           f'the header has the tapped row\'s title and artist and no "0 tracks": {m.wtext[m.widgets["ab_title"]]!r} {m.wtext[m.widgets["ab_meta"]]!r}')
    expect('No songs' not in status(m) and any(c[0] == 'fake_ap_cover' for c in calls), f'the empty text is not set, the cover is asked for ({status(m)!r})')
    expect(('timer_add', PSYMS['ls_spin_tick'], 250) in calls, 'the spinner turns on a timer')
    blits, texts, _ = paint(m)
    expect(len(blits) >= 1, 'the header paints (the cover or its disc) with no rows')
    expect(not texts, f'no pill text is painted while loading ({texts})')
    frames = []
    for _ in range(2):
        m.call(PSYMS['ls_spin_tick'], a0=0x5a5a5a50, count=4000000)
        frames += [c[2] for c in m.calls if c[0] == 'image_base_set_image']
    expect(frames == ['wf_spin1', 'wf_spin2'], f'each tick sets the next frame, whatever stock passes as the argument (its timer_info_t): {frames}')
    # the tracks arrive: the rows fill in, the spinner is gone, the header keeps its cover
    m.fake_tracks = [m.record(album='Fake Album', artist='Fake Artist', path=f'nd://t{i}', title=f'Remote {i}', name='', rid=-3 - i) for i in range(3)]
    m.state_ret, m.gen = 0, 2
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status')[0] == 0, 'the tracks arrive: the content view stays, no status line')
    expect(vis(m, 'ab_spin')[0] == 0 and 'tracks' in utf(m.wtext[m.widgets['ab_meta']]), f'the meta line has the count now ({m.wtext[m.widgets["ab_meta"]]!r})')
    expect(all(vis(m, n) == (1, 1) for n in ('btn_play', 'btn_shuffle')) and vis(m, 'ab_glyph')[0] == 1, 'the tracks arrive: the Shuffle disc and the Play pill show, live')
    expect(any(t for t, _ in paint(m)[1]), 'the pill text is painted again')
    m.call(PSYMS['ls_spin_tick'], a0=0x5a5a5a50, count=4000000)
    expect(not any(c[0] in ('image_base_set_image', 'timer_add') for c in m.calls), 'the spinner timer ends with the wait')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # the server answered with no tracks: the empty state, no spinner
    m = fake_machine(n=5)
    m.fake_tracks, m.state_ret = [], 0
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    expect(vis(m, 'view_grid')[0] == 0 and vis(m, 'label_status')[0] == 1 and status(m) == 'No songs' and vis(m, 'ab_spin')[0] == 0, 'an empty answer: "No songs", no spinner')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    # a failed request: the reason, no header, no pills, no spinner
    for st, want in ((2, "Can't connect to the server"), (3, 'Connect to Wi-Fi first')):
        m = fake_machine(n=5)
        m.fake_tracks, m.state_ret = [], st   # LS_ST_FAILED / LS_ST_OFFLINE
        m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
        expect(vis(m, 'label_status')[0] == 1 and status(m) == want and vis(m, 'ab_spin')[0] == 0 and vis(m, 'view_grid')[0] == 0 and vis(m, 'btn_play')[0] == 0, f'state {st}: {want!r}, no spinner, no header, no pills ({status(m)!r})')
        m.call(PSYMS['ab_on_destroy'], count=4000000)


def marks_tests(ctx):
    """8. A source's row marks (docs/modules/subsonic.md ND-13): the downloaded disc, the download ring (no "Downloading" text), the DSD tag, the dim offline title, and the playing marker asked of src->playing."""
    from PIL import Image
    expect = ctx.expect
    LS_DONE, LS_WAIT, LS_ACTIVE = 3, 1, 2
    im = Image.open(os.path.join(ROOT, 'assets', 'icons', 'png', 'pc_atlas.png')).convert('RGBA')
    m = fake_machine().fake_src(n=6, with_playing=True)   # six tracks, the source answers src->playing
    m.images['pc_atlas'] = (im.width, im.height, im.tobytes())
    t = m.fake_tracks
    m.row_of = {t[0]: (LS_DONE, 0, 0, 0, 0), t[1]: (LS_ACTIVE, 42, 0, 0, 0), t[2]: (LS_ACTIVE, -1, 0, 0, 0), t[3]: (0, 0, 1, 0, 1), t[4]: (LS_DONE, 0, 1, 0, 0), t[5]: (LS_WAIT, 0, 0, 0, 0)}
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    scroll_to(m, HDR)
    blits, texts, fills = paint(m)
    disc, dsd, ring = (O['PA_BADGE_PX'], O['PA_DSD_H']), (O['PA_DSD_W'], O['PA_DSD_H']), (O['PA_DL_PX'],) * 2

    discs = {b[2][1] // ROW: b[2] for b in blits if tuple(b[2][2:]) == disc}
    dsds = {b[2][1] // ROW: b[2] for b in blits if tuple(b[2][2:]) == dsd}
    ARROW, STOP, NSTEP = O['PA_DL_ARROW'], O['PA_DL_STOP'], O['PA_DL_N']
    cell = lambda b: b[1][0] // O['PA_DL_PX'] + (b[1][1] - O['PA_DSD_H']) // O['PA_DL_PX'] * O['PA_DL_COLS']   # the atlas cell a ring blit copies
    ringblits = [b for b in blits if tuple(b[2][2:]) == ring]
    rings = {b[2][1] // ROW: b for b in ringblits if cell(b) < NSTEP}
    marks = {b[2][1] // ROW: cell(b) for b in ringblits if cell(b) >= NSTEP}
    titles = {r[1] // ROW: (s, st) for (s, r), st in texts if st in ('label_row_title', 'label_row_dim') and r[0] > 30}
    expect(sorted(discs) == [0, 4], f'the downloaded disc (PA_BADGE_PX square) is on the two downloaded rows only: {sorted(discs)}')
    expect(sorted(dsds) == [3, 4], f'the DSD tag (PA_DSD_W x PA_DSD_H) is on the two DSD rows only: {sorted(dsds)}')
    expect(sorted(rings) == [1, 2, 5], f'the download ring is on the downloading and the queued rows only: {sorted(rings)}')
    ks = {r: cell(rings[r]) for r in rings}
    expect(ks == {1: 5, 2: 0, 5: 0} and all(rings[r][1][2:] == ring for r in rings), f'42 % draws the 5 / 12 step (nearest), an unknown progress and a queued track the empty ring: {ks}')
    expect(marks == {1: STOP, 2: STOP, 5: ARROW}, f'a running download draws the stop square over its step (42 % and unknown), a queued track the arrow on the empty ring: {marks}')
    expect(not [1 for _, st in texts if st == 'label_row_val'] and not any('Downloading' in s or 'Waiting' in s for (s, r), st in texts), 'no state text on the page')
    expect(rings[1][2][0] + rings[1][2][2] == rings[2][2][0] + rings[2][2][2] and rings[1][2][1] % ROW + 7 == O['AB_TEXT_Y'] + O['AB_TEXT_H'] // 2, f'the ring ends where the group ends, centred on the title line: {rings[1][2]}')
    for pct, want in ((0, 0), (80, 10), (100, 11)):   # the ring follows the progress on the next paint
        m.row_of[t[1]] = (LS_ACTIVE, pct, 0, 0, 0)
        b1 = [b for b in paint(m)[0] if tuple(b[2][2:]) == ring and b[2][1] // ROW == 1]
        k1 = [cell(b) for b in b1 if cell(b) < NSTEP]
        expect(k1 == [want] and [cell(b) for b in b1 if cell(b) >= NSTEP] == [STOP], f'{pct} % draws step {want} with the stop square: {k1}')
    m.row_of[t[1]] = (LS_ACTIVE, 42, 0, 0, 0)
    # the title stops before the marks; the marks sit left of the "..." zone
    end = rings[1][2][0] + rings[1][2][2]
    d0, d4, s4, s3 = discs[0], discs[4], dsds[4], dsds[3]
    expect(s3[0] + s3[2] == end and s4[0] + s4[2] == end and d4[0] + d4[2] + 6 == s4[0] and d0[0] + d0[2] == end,
           f'the group ends at the text end ({end}): DSD last, the disc LS_MK_GAP before it: {d0} {d4} {s4} {s3}')
    mid = lambda b: b[1] % ROW + b[3] // 2
    expect(mid(d0) == O['AB_TEXT_Y'] + O['AB_TEXT_H'] // 2 == mid(s4), f'both marks are centred on the title line: {mid(d0)} {mid(s4)}')
    expect(all(titles[r][0] for r in range(5)), f'titles painted: {titles}')
    expect([titles[r][1] for r in range(5)] == ['label_row_title'] * 3 + ['label_row_dim', 'label_row_title'], f'only the offline row (3) is in the dim style: {[titles[r][1] for r in range(5)]}')
    # stock page: no marks, no extra styles
    m2 = album_machine(n=4)
    m2.images['pc_atlas'] = (im.width, im.height, im.tobytes())
    open_album(m2)
    scroll_to(m2, HDR)
    b2, t2, _ = paint(m2)
    expect(not [b for b in b2 if tuple(b[2][2:]) in (disc, dsd)] and not [1 for _, st in t2 if st in ('label_row_val', 'label_row_dim')] and not any(c[0] == 'widget_load_image' and c[1] == 'pc_atlas' for c in m2.calls),
           'a stock page draws no marks and never loads the atlas')
    # the playing marker comes from src->playing
    m.playing_rec = t[2]
    m.playing = ('', 'nd://t0', 0)   # (the url test would pick row 0: it must not be asked)
    blits, texts, fills = paint(m)
    wv = [b for b in blits if b[2][2] == O['AB_WAVE'] and b[2][3] == O['AB_WAVE']]
    expect(len(wv) == 1 and wv[0][2][1] // ROW == 2, f'src->playing picks the row with the wave: {[b[2] for b in wv]}')
    m.playing_rec = None
    expect(not [b for b in paint(m)[0] if b[2][2] == O['AB_WAVE'] and b[2][3] == O['AB_WAVE']], 'src->playing 0 for every row: no wave')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


def dsd_tests(ctx):
    """9. The DSD confirm (ND-14): a source's play answering -2 (a DSD track that is not downloaded) shows "Download to Play?" from a row tap, Play and Shuffle; Download asks src->act(LS_ACT_DOWNLOAD)
    on the row, Cancel asks nothing; another answer shows no dialog."""
    expect = ctx.expect
    TEXT = 'Download to Play?\nDSD tracks play from the card. Remote {n}, ? MB.'
    def asked(m): return [c for c in m.calls if c[0] == 'confirm']
    def open_src(**kw):
        m = fake_machine(n=5, **kw)
        m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
        m.top_main = 0   # (no top window: the confirm dialog's scrim needs a mapped one)
        return m
    for what, act in (('a row tap', lambda m: tap(m, 150, row_y(3) + 20)), ('Play', lambda m: click(m, 'btn_play')), ('Shuffle', lambda m: click(m, 'btn_shuffle'))):
        n = 3 if what == 'a row tap' else 0   # (a Shuffle start is the row the source answered -2 for: the source here never says, so the first)
        m = open_src(); m.play_ret = -2; m.confirm_yes = False
        calls = act(m)
        ask = asked(m)
        expect(len(ask) == 1 and ask[0][1] == TEXT.format(n=n) and ask[0][2] == O['CONFIRM_KIND_WRAP'] and not m.acts, f'{what}: -2 asks "Download to Play?" with the track and size, Cancel asks nothing ({[a[1:] for a in ask]})')
        expect(any(c[0] == 'timer_add' for c in calls), f'{what}: the dialog\'s buttons are relabelled Cancel / Download by a timer')
        m = open_src(); m.play_ret = -2; m.confirm_yes = True; m.act_ret = 0
        act(m)
        expect(m.acts == [(m.fake_tracks[n], 1)], f'{what}: Download asks src->act(LS_ACT_DOWNLOAD) for that row ({m.acts})')
        m = open_src(); m.play_ret = 0; m.confirm_yes = True
        act(m)
        expect(not asked(m) and not m.acts, f'{what}: a source that played shows no dialog')
        m = open_src(); m.play_ret = -1; m.confirm_yes = True
        act(m)
        expect(not asked(m) and not m.acts, f'{what}: -1 (nothing started, the source said why) shows no dialog')
    m = open_src(); m.play_ret = -2; m.confirm_yes = True; m.act_ret = 0
    m.setword(m.fake_tracks[3] + O['REC_TITLE'], m.cstr('A very long track title that goes on and on, \u00e9 \u00e9 \u00e9 \u00e9'))
    tap(m, 150, row_y(3) + 20)
    ask = asked(m)
    expect(len(ask) == 1 and len(ask[0][1].encode('latin-1')) < 0x1ff and '...' in ask[0][1], f'a long title is cut with an ellipsis so the text fits the dialog: {ask[0][1] if ask else None!r}')


def nextalbum_tests(ctx):
    """Continue with Next Album, phase 1 (patch/nextalbum.c): the order an opener noted is taken by album_open; Play, Shuffle and a track arm it around the queue load, which keeps it;
    an album opened without a note, or with the setting off, has no order; a play that loads nothing leaves the old source."""
    expect = ctx.expect
    OTHERS = [(f'Artist {i}', f'Other {i}') for i in range(2)]

    def noted(setting=True, order=None, note=True):
        m = album_machine(); m.load_on_open = True
        if setting: NA.on(m)
        keys = [m.key] + [album_key(a, b) for a, b in OTHERS]
        if note: NA.note(m, m.new_deque(m.class_lists[ALBUMS]), order=order)
        return m, keys

    m, keys = noted()
    r, calls = open_album(m)
    s = NA.state(m)
    expect(r == 0 and s['pending'] is None and s['page'] and s['page']['keys'] == keys and s['page']['own'] == m.key and s['active'] is None and s['armed'] == 0,
           'album_open takes the note: it is the page\'s order with the album\'s own key; nothing plays from it yet')
    # the three ways to play arm the order for the load Now Playing makes, and the load keeps it
    for what, act in (('Play', lambda m: click(m, 'btn_play')), ('Shuffle', lambda m: click(m, 'btn_shuffle')), ('a track row', lambda m: tap(m, 150, row_y(2) + 20))):
        m, keys = noted(); open_album(m)
        act(m)
        s = NA.state(m)
        expect(m.played is not None and m.na_at_open['armed'] == 1 and m.na_at_open['active'] and m.na_at_open['active']['keys'] == keys,
               f'{what}: the order is armed and active while Now Playing opens (start_player\'s load runs inside the navigator call)')
        expect(s['armed'] == 0 and s['active'] and s['active']['keys'] == keys and s['active']['cur'] == m.key and s['prev'] is None, f'{what}: the load kept it; nothing is left armed afterwards')
        m.call(PSYMS['ab_on_destroy'], count=4000000)
        expect(NA.state(m)['page'] is None and NA.state(m)['active'] and NA.state(m)['active']['ref'] == 1, f'{what}: the page closing keeps the playing source')
    # the order is the one shown: a sorted and reversed view
    m, keys = noted(order=[2, 0, 1]); open_album(m); click(m, 'btn_play')
    expect(NA.state(m)['active']['keys'] == [keys[2], keys[0], keys[1]], 'a sorted view: the order as shown')
    # an album opened without a note has no order, and arming it keeps nothing
    m, keys = noted(note=False)
    open_album(m)
    expect(NA.state(m)['page'] is None, 'no note: the page has no order')
    click(m, 'btn_play')
    expect(m.played is not None and m.na_at_open['active'] is None and NA.state(m)['active'] is None, 'and Play leaves no source')
    # a source from an earlier album is gone once an album with no order plays
    m, keys = noted(); open_album(m); click(m, 'btn_play')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    open_album(m)
    click(m, 'btn_play')
    expect(NA.state(m)['active'] is None, 'playing an album that has no order drops the earlier source')
    # a note for another album (cc_open_album took a different row) is not taken
    m, keys = noted(order=[1, 2])
    open_album(m)
    expect(NA.state(m)['page'] is None, 'the opened album is not in the note: no order')
    # the setting off records nothing
    m, keys = noted(setting=False)
    open_album(m); click(m, 'btn_play')
    expect(NA.state(m)['page'] is None and NA.state(m)['active'] is None and NA.state(m)['pending'] is None, 'setting off: no order, no source')
    # a play that loads nothing (a missing file) leaves the old source and arms nothing
    m, keys = noted(); open_album(m); click(m, 'btn_play')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    old = NA.state(m)['active']['ptr']
    m2 = m
    m2.present.discard('/mnt/mmc/m/0.flac'); m2.played = None
    NA.note(m2, m2.new_deque(m2.class_lists[ALBUMS]), order=[2, 1, 0])
    open_album(m2)
    click(m2, 'btn_play')
    s = NA.state(m2)
    expect(m2.played is None and s['active'] and s['active']['ptr'] == old and s['armed'] == 0 and s['prev'] is None,
           'a track that is not on the card: nothing loads, the playing queue keeps its source')
    # a stock list replaced under the page: Play only reads again
    m, keys = noted(); open_album(m)
    m.setword(SHOWLIST, m.new_deque(m.songs[:3]))
    click(m, 'btn_play')
    expect(NA.state(m)['armed'] == 0 and NA.state(m)['active'] is None, 'a list that was replaced: the page reads it again and plays nothing, nothing armed')
    # another page loads a queue (Songs, a playlist, a folder, DLNA ...): mclLoadPlayList without an armed order drops the source
    m, keys = noted(); open_album(m); click(m, 'btn_play')
    m.call(PSYMS['na_on_load'], count=100000)
    expect(NA.state(m)['active'] is None, 'any later load drops it')


def more_tests(ctx):
    """12. The source page's "..." (Download Album): hidden on the library's page, its card opens, closes on the scrim and its one row asks src->act(LS_ACT_DOWNLOAD_ALL) once with the page's list."""
    expect = ctx.expect
    LS_ACT_DOWNLOAD_ALL = 6
    f = ui().find
    expect(f('btn_more') is not None and f('btn_more').get('visible') == 'false' and (f('btn_more').x, f('btn_more').w) == (f('btn_select').x, f('btn_select').w)
           and f('btn_more').get('style:normal:icon') == 'pod_nav_more' and f('btn_more').get('style:pressed:icon') == 'pod_nav_more_down', 'the asset has a hidden "..." on Select\'s slot')
    expect(f('vs_card').get('visible') == 'false' and f('vs_label6').get('tr_text') == 'Download Album' and f('vs_glyph6').get('image') == 'pod_ic_vsdownload' and f('vs_item8') is None,
           'the card is hidden and its first action row is Download Album with the download glyph')
    m = album_machine()   # the stock page: Select as before, no "..."
    m.call(PSYMS['album_open_src'], a0=0, a1=ALBUMS, a2=m.row, count=900000000)
    expect(vis(m, 'btn_select') == (1, 1) and not any(c in m.calls for c in (('widget_lookup', 'btn_more'), ('widget_lookup', 'vs_scrim'))),
           'the stock page: Select shows, the "..." stays hidden and unbound, the card is not bound')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = fake_machine(n=4)
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    expect(vis(m, 'btn_more') == (1, 1) and vis(m, 'btn_select')[0] == 0 and vis(m, 'vs_card')[0] == 0, 'a source page: the "..." shows, Select does not, the card is closed')
    click(m, 'btn_more')
    expect(vis(m, 'vs_card')[0] == 1 and vis(m, 'vs_scrim')[0] == 1 and vis(m, 'vs_item6')[0] == 1 and vis(m, 'vs_item7')[0] == 0 and vis(m, 'vs_item0')[0] == 0, 'the "..." opens the card with the one row')
    click(m, 'vs_scrim')
    expect(vis(m, 'vs_card')[0] == 0 and not m.acts, 'the scrim closes it and asks nothing')
    click(m, 'btn_more'); click(m, 'btn_more')
    expect(vis(m, 'vs_card')[0] == 0, 'the "..." closes the open card')
    click(m, 'btn_more')
    m.act_ret = 0
    click(m, 'vs_item6')
    expect(len(m.acts) == 1 and m.acts[0][1] == LS_ACT_DOWNLOAD_ALL and m.acts[0][0] in m.deques and m.deques[m.acts[0][0]] == m.fake_tracks and vis(m, 'vs_card')[0] == 0,
           f'Download Album calls src->act(LS_ACT_DOWNLOAD_ALL) once with the page\'s list and closes the card ({m.acts})')
    m.call(PSYMS['ab_on_destroy'], count=4000000)
    m = fake_machine(n=4)   # the tracks have not arrived yet
    m.fake_tracks, m.state_ret = [], 1   # LS_ST_LOADING
    m.call(PSYMS['album_open_src'], a0=m.src, a1=ALBUMS, a2=m.fake_row, count=900000000)
    expect(vis(m, 'btn_more') == (1, 0) and vis(m, 'vs_card')[0] == 0, f'the album is loading: the "..." keeps its place but is dead ({vis(m, "btn_more")})')
    m.fake_tracks = [m.record(album='Fake Album', artist='Fake Artist', path=f'nd://t{i}', title=f'Remote {i}', name='', rid=-3 - i) for i in range(3)]
    m.state_ret, m.gen = 0, 2
    m.call(PSYMS['ab_on_gen'], count=80000000)
    expect(vis(m, 'btn_more') == (1, 1), 'the tracks arrive: the "..." is live')
    m.call(PSYMS['ab_on_destroy'], count=4000000)


SECTIONS = [asset_tests, open_tests, header_tests, cover_tests, rows_tests, play_tests, select_tests, source_tests, loading_tests, marks_tests, dsd_tests, nextalbum_tests, more_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

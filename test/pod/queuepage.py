"""The Queue page (patch/queuepage.c, docs/modules/queue.md): our own page in place of the stock queue drawer. The built asset (the list that is the whole window, the header's
widgets and the icon-only mode buttons at the numbers of patch/offsets.inc, the glass Back last, touches by demo's own hit test), Now Playing's queue button (the click handler bound
after the stock init and what each of its answers does), the open and its fallbacks to the stock drawer (empty queue, streams, a window that will not open, a foreign
asset), the header (the playing track, the cover from the cache), Up Next (the tracks after the playing one, texts, covers, the press fill, the hairline, the grey line when nothing
follows), the loader, the taps (start_playqueue with the queue index as the stock drawer's row handler calls it; drags and the header play nothing), the mode buttons (Shuffle
toggles, Repeat cycles off / all / one, the buttons' look), the refresh timer (the player moves on, the mode changes elsewhere, the queue is replaced, a dark screen) and the destroy.
The compiled payload runs under Unicorn; the player is the machine's queue (the deque at PLAY_QUEUE) and position."""
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


SG = sibling('songs')

WIN_H, TOP, ROW, SY0 = O['QP_WIN_H'], O['QP_TOP'], O['LIST_ROW_H'], 30   # SY0: the window's screen y (the status bar's 30 px; the list is the whole window)
SC_YOFF = O['SC_YOFF']
PLAY_QUEUE, FORCE = pod.DATA['PLAY_QUEUE'][0], pod.DATA['FORCE_REFRESH'][0]
UI = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_queue.bin') if WORK else None
FLAG_FILE = '/mnt/data/m1plus/playback-shuffle'
flag_on = lambda m: m.fs.get(FLAG_FILE) == b'1\n'   # the Shuffle flag as saved
WIDGETS = ('view_queue', 'btn_return', 'btn_shuffle', 'btn_repeat', 'label_status', 'label_row_title', 'label_row_sub', 'qp_title', 'qp_artist', 'qp_empty', 'qp_head', 'btn_qclear', 'label_title')
NAMES = ['So What', 'Freddie Freeloader', 'Blue in Green', 'All Blues', 'Flamenco Sketches', 'Chorus Complains', 'Come Together', 'Something', 'Hey Jude', 'Let It Be']
RGB = (190, 50, 55)
COVER_PIX = [bytes((RGB[0] + 20 * k, RGB[1], RGB[2], 255)) * (168 * 168) for k in range(2)] + [bytes((RGB[0], RGB[1], RGB[2], 255)) * 64]


class QM(SG.SongsMachine):
    """The Songs machine plus what the Queue page calls: the player's play type, start_playqueue (the position moves)."""
    ptype = 0     # mclGetPlayType

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for n in ('mclGetPlayType', 'start_playqueue', 'mclSetGaplessMode'): self.handlers[pod.FUNCTIONS[n][2]] = n
        self.install_libcstl()
        self.sbtrack, self.sbcover = {}, {}   # server track REC_ID -> track id (sba_rec_track); REC_ID -> [sba_rec_cover's answer, the file's path] (patch/sbapi.c, tested in sbapi.py)
        for n in ('sba_rec_track', 'sba_rec_cover'): self.handlers[PSYMS[n]] = n
        self.pics, self.pic_fp, self.dir_log = {}, {}, []   # path -> the picture file's bytes (an episode's show cover: pc_cover_ok seeks through its header), open handle -> [path, position]

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0 = u.reg_read(UC_MIPS_REG_A0)
        a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        if name == 'opendir': self.dir_log.append(self.read_cstr(a0))   # (every folder read of the machine's life; the base mock answers)
        if name == 'mclGetPlayType': ret = self.ptype
        elif name == 'sba_rec_track':
            rid = a0 - (1 << 32) if a0 >= 1 << 31 else a0; ret = self.cstr(self.sbtrack.get(rid, ''))
        elif name == 'sba_rec_cover':
            rid = self.word(a0 + O['REC_ID']); rid = rid - (1 << 32) if rid >= 1 << 31 else rid
            r, path = self.sbcover.get(rid, [-1, None]); self.calls.append(('sba_rec_cover', rid)); ret = r
            if r == 1: self.u.mem_write(a1, path.encode() + b'\0')
        elif name == 'fopen' and self.read_cstr(a0) in self.pics:
            path = self.read_cstr(a0); self.calls.append(('fopen', path, self.read_cstr(a1))); ret = self.alloc(4); self.pic_fp[ret] = [path, 0]
        elif name == 'fseek' and a0 in self.pic_fp: self.pic_fp[a0][1] = a1; ret = 0
        elif name == 'fread' and a3 in self.pic_fp:
            path, pos = self.pic_fp[a3]; data = self.pics[path][pos:pos + a1 * a2]
            if data: self.u.mem_write(a0, data)
            self.pic_fp[a3][1] += len(data); ret = len(data) // a1
        elif name == 'fclose' and a0 in self.pic_fp: self.pic_fp.pop(a0); ret = 0
        elif name == 'mclSetGaplessMode':   # stock's setter: the byte, and for 0 with a preload open (state 1) {mcl-closegapless} and state -1
            self.calls.append(('mclSetGaplessMode', a0)); self.u.mem_write(pod.DATA['MCL_GAPLESS'][0], bytes((a0 & 255,)))
            if a0 == 0 and self.word(pod.DATA['MCL_PRELOAD'][0]) == 1: self.setword(pod.DATA['MCL_PRELOAD'][0], -1); self.calls.append(('closegapless',))
            ret = 0
        elif name == 'start_playqueue': self.calls.append(('start_playqueue', a0)); self.play_pos = a0; ret = 0
        else: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def queue_machine(n=6, pos=1, titles=None, cover=True, cues=(), tracks=None, library=None, paths=None):
    """The page's widgets as widget structs (window > list_view > scroll_view > view_queue, for demo's own widget_to_local) and the player on an n track queue at pos. Track i is
    Artist {i // 3} / Album {i // 3}; a cover file for the first two albums (cover: True, 'marker' for the empty "no art" file, False for none). tracks: [(artist, album)] instead.
    library: [(artist, album, has_cover)], the library's album records (what getAllAlbum's query returns) and their cache files, instead of the first two albums' files.
    paths: the tracks' file paths instead of /mnt/mmc/m/{i}.flac (a podcast episode is a file in a show folder under the Podcasts folder)."""
    m = QM()
    m.load_image = 0
    for w in WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.images = {'p_default': (24, 24, bytes((0x40, 0x40, 0x40, 255)) * (24 * 24))}
    recs = []
    for i in range(n):
        title = titles[i] if titles else NAMES[i % len(NAMES)] if n <= len(NAMES) else f'Track {i + 1}'
        artist, album = tracks[i] if tracks else (f'Artist {i // 3}', f'Album {i // 3}')
        path = paths[i] if paths else f'/mnt/mmc/m/{i}.flac'
        r = m.record(album=album, artist=artist, path=path, title=title, name=path.rsplit('/', 1)[1], rid=100 + i)
        if i in cues: m.setword(r + O['REC_CUE_START'], 1000 * i)
        m.present.add(path)
        recs.append(r)
    m.songs = recs
    m.play(recs, pos)
    m.cover_paths = {}
    covers = [(a, b) for a, b, c in library if c] if library is not None else [(f'Artist {k}', f'Album {k}') for k in range(min(2, (n + 2) // 3))]
    if library is not None: m.class_lists[O['CLASS_ALBUMS']] = [m.record(album=b, artist=a, path=f'/mnt/mmc/lib/{i}.flac', rid=900 + i) for i, (a, b, c) in enumerate(library)]
    for k, (ar, al) in enumerate(covers):
        path = art_file(album_key(ar, al))
        m.cover_paths[k] = path
        if cover == 'marker': m.present.add(path); m.files[path] = 0
        elif cover:
            m.present.add(path); m.files[path] = 4096
            m.images['file://' + path] = ((8, 8, COVER_PIX[2]) if library is not None else (168, 168, COVER_PIX[k % 2]))   # (shared pictures; a library's are tiny: the emulated heap keeps every decode)
    win, lv, sv, view = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_queue']
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, SY0, WIN_H, 0), (lv, 0, WIN_H, win), (sv, 0, WIN_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310); m.setword(sv + 0x70, SV_VT)   # a real scroll_view's vtable: demo's widget_to_local adds its offset
    m.widgets['queue_scrollview'] = sv
    for off, v in ((4, 0), (8, 320), (0xc, WIN_H), (0x44, sv)): m.setword(view + off, v)
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    m.sv, m.view = sv, view
    return m


def open_queue(m):
    r = m.call(PSYMS['queue_open'], count=900000000)
    return r if r < 0x80000000 else r - 2 ** 32, list(m.calls)


def opened(**kw):
    m = queue_machine(**kw)
    m.top_main = m.window
    r, calls = open_queue(m)
    assert r == 0 and ('window_open', 'm1plus_queue') in calls, f'the page did not open ({r}, {calls[:12]})'
    return m


def scroll_to(m, v): m.setword(m.sv + SC_YOFF, v & 0xffffffff)


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts, fills) of that frame, the canvas where the scroll_view leaves it."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SY0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['qp_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(zip(m.texts, m.text_styles)), list(m.fills)


def touch(m, kind, x, y, fn, t=1000): return m.touch(kind, x, SY0 + y, t, fn=fn)


def tap(m, x, y, dx=0, dy=0):
    """A tap on the content view at list point (x, y) (the list starts at the window's top; the scroll offset is not included)."""
    touch(m, 'down', x, y, 'qp_on_down')
    touch(m, 'up', x + dx, y + dy, 'qp_on_up', 1080)
    return list(m.calls)


def click(m, name):
    m.click(name, count=900000000)
    return list(m.calls)


def tick(m):
    r = m.call(PSYMS['qp_on_tick'], count=900000000)
    return r, list(m.calls)


def destroy(*ms):
    for m in ms: m.call(PSYMS['qp_on_destroy'], count=4000000)


def row_y(i): return TOP + i * ROW
def ui(): return awtk_ui.parse(open(UI, 'rb').read())
def text_of(m, name): return m.wtext.get(m.widgets[name])
def utf(s): return s.encode('latin-1').decode('utf-8')
def fills_of(fills, colour): return [f_ for f_ in fills if f_[0] == colour]
def vh(m): return m.props.get((m.sv, 'virtual_h'))
def shown(m, name): return m.props.get((m.widgets[name], 'visible'), 1) and m.props.get((m.widgets[name], 'sensitive'), 1)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def asset_tests(ctx):
    """1. The built asset: a list that is the whole window, the header's widgets and the mode buttons at the numbers of offsets.inc, the glass Back last."""
    expect = ctx.expect
    root = ui()
    f = root.find
    kids = [c.name for c in root.children]
    expect(root.name == 'm1plus_queue_page' == pod_pages.QUEUE_PAGE.name == O.get('QP_WINDOW', 'm1plus_queue_page') and pod_pages.QUEUE_PAGE in pod_pages.PAGES and pod_pages.QUEUE_PAGE.key == 'm1plus_queue',
           'the page is m1plus_queue (window m1plus_queue_page)')
    expect(kids[0] == 'queue_listview' and kids[-2:] == ['label_title', 'btn_return'] and 'btn_backtoplayer' not in kids, f'the list is the window\'s first child, the glass Back its last, no Now Playing: {kids}')
    lv, sv, view = f('queue_listview'), f('queue_scrollview'), f('view_queue')
    expect((lv.x, lv.y, lv.w, lv.h) == (0, 0, 320, WIN_H) and (sv.y, sv.w, sv.h) == (0, 310, WIN_H) and f('scroll_bar_m') is not None and (view.x, view.y, view.w, view.h) == (0, 0, 320, WIN_H),
           'the list is the whole window (y 0, 450 high), its scroll_view 310 wide with the stock scroll bar, the content view in it')
    for name, y, h, px, colour in (('qp_title', O['QP_TITLE_Y'], O['QP_TITLE_H'], 20, '#FFFFFF'), ('qp_artist', O['QP_ARTIST_Y'], O['QP_ARTIST_H'], 16, '#AAAAAA')):
        w = f(name)
        expect(w.type == 'hscroll_label' and (w.x, w.y, w.w, w.h) == (O['QP_TEXT_X'], y, O['QP_TEXT_W'], h) and w.get('sensitive') == 'false' and w.get('ellipses') == 'true'
               and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == colour and w.get('style:normal:text_align_h') == 'left',
               f'{name}: a left aligned {px} px {colour} hscroll_label at x {O["QP_TEXT_X"]}, insensitive (a drag over it scrolls the list)')
    expect(O['QP_TEXT_X'] == O['QP_COVER_X'] + O['QP_COVER'] + 12 and O['QP_TEXT_X'] + O['QP_TEXT_W'] == 310 and O['QP_TITLE_Y'] + O['QP_TITLE_H'] + 2 + O['QP_ARTIST_H'] + (O['QP_TITLE_Y'] - O['QP_COVER_Y']) == O['QP_COVER_Y'] + O['QP_COVER'],
           'the two lines are centred on the cover (the title 24 px, 2 px, the artist 20 px) and start 12 px after it')
    for name, x, icon in (('btn_shuffle', O['QP_PILL_X0'], 'sg_shuffle'), ('btn_repeat', O['QP_PILL_X1'], 'sg_repeat')):
        b = f(name)
        expect(b.type == 'button' and (b.x, b.y, b.w, b.h) == (x, O['QP_PILL_Y'], O['QP_PILL_W'], O['SG_PILL_H']) and b.get('style:normal:round_radius') == str(O['SG_PILL_R'])
               and b.get('style:normal:bg_color') == '#2C2C2E' and b.get('style:pressed:bg_color') == '#3A3A3D' and b.get('style:normal:icon') == icon and b.get('tr_text') is None and not b.get('text'),
               f'{name}: an icon-only flat button ({O["QP_PILL_W"]} x {O["SG_PILL_H"]}, the 20 px radius, off: #2C2C2E, pressed #3A3A3D, no label) with the {icon} glyph at x {x}')
    expect(O['QP_PILL_X0'] + O['QP_PILL_W'] + 10 == O['QP_PILL_X1'] and O['QP_PILL_X1'] + O['QP_PILL_W'] == 310 and O['QP_PILL_X0'] == 10 and O['QP_PILL_Y'] == O['QP_COVER_Y'] + O['QP_COVER'] + 16,
           'the two buttons are equal, 10 px apart, spanning the 10 px margins, 16 px under the cover')
    head, empty = f('qp_head'), f('qp_empty')
    expect((head.x, head.y, head.h) == (O['SG_HDR_X'], O['QP_HEAD_Y'], O['QP_HEAD_H']) and head.get('style:normal:font_size') == '20' and head.get('style:normal:text_color') == '#FFFFFF'
           and head.get('tr_text', 'Queue') == 'Queue' and head.get('sensitive') == 'false' and f('qp_count') is None, '"Queue" 20 px white at x 10 (the shelf header\'s style), no count')
    expect((empty.x, empty.y, empty.h) == (O['SG_HDR_X'], TOP + O['QP_EMPTY_Y'], O['QP_EMPTY_H']) and empty.get('visible') == 'false' and empty.get('sensitive') == 'false'
           and empty.get('style:normal:text_color') == '#9C9C9C' and empty.get('style:normal:font_size') == '16' and empty.get('tr_text', 'No upcoming songs') == 'No upcoming songs',
           '"No upcoming songs": a quiet grey 16 px line where the first row would be, hidden until nothing follows')
    expect(O['QP_HEAD_Y'] == O['QP_PILL_Y'] + O['SG_PILL_H'] + 16 and O['QP_TOP'] == O['QP_HEAD_Y'] + O['QP_HEAD_H'] + 6, 'the section line is 16 px under the buttons, the rows 6 px under it')
    for name, px, colour in (('label_row_title', 21, '#FFFFFF'), ('label_row_sub', 18, '#AAAAAA')):
        w = f(name)
        expect(w.get('visible') == 'false' and w.get('sensitive') == 'false' and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == colour,
               f'{name}: the hidden {px} px {colour} text style of the rows (the Songs page\'s)')
    k = {c.name: c for c in root.children}
    xx = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    b = k['btn_return']
    expect((b.x, b.y, b.w, b.h) == (7, 0, 44, 50) and b.get('style') == 'img_btn_style' and b.get('style:normal:icon') == 'ah_nav_back' and b.get('style:pressed:icon') == 'ah_nav_back_down'
           and os.path.exists(os.path.join(xx, 'ah_nav_back.png')), 'btn_return: the glass ah_nav_back disc at x 7 (44 wide), pressed ah_nav_back_down: the only control, to leave')
    expect('navigationbar_view' not in k and k['label_title'].get('visible') == 'false', 'the control is a child of the window itself (no bar view); the section line is the page\'s title')
    for img in ('sg_shuffle', 'sg_repeat', 'sg_repeat1', 'sg_shuffle_on', 'sg_repeat_on', 'sg_repeat1_on'): expect(os.path.exists(os.path.join(xx, img + '.png')), f'{img}.png is in the build')
    expect(not [n.name for n in root.walk() if (n.name or '').startswith('qp_shuf')] and not os.path.exists(os.path.join(xx, 'sg_shuffle_big.png')), 'the Shuffle placeholder (widgets and glyph) is gone: Up Next always shows the queue')
    # contrast of the glyph on its pill (WCAG): white on the off fill, the dark glyph on the lit fill, pressed too
    from PIL import Image

    def lum(c):
        v = [x / 255 for x in c[:3]]
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    ratio = lambda a, b: (max(lum(a), lum(b)) + 0.05) / (min(lum(a), lum(b)) + 0.05)
    rgb = lambda w: (w & 255, (w >> 8) & 255, (w >> 16) & 255)
    for img, fills in (('sg_shuffle', (O['QP_PILL_OFF'], O['QP_PILL_OFF_DOWN'])), ('sg_repeat1_on', (O['QP_PILL_ON'], O['QP_PILL_ON_DOWN']))):
        im = Image.open(os.path.join(xx, img + '.png')).convert('RGBA')
        ink = max((p for p in im.getdata() if p[3] > 200), key=lambda p: lum(p) if img.endswith('_on') is False else -lum(p))
        for w in fills: expect(ratio(ink, rgb(w)) >= 4.5, f'{img} on #{w & 0xffffff:06x}: {ratio(ink, rgb(w)):.1f}:1 (>= 4.5)')
    expect(O['QP_PILL_ON'] == 0xffc8c8c8 and O['QP_PILL_OFF'] == 0xff2e2c2c, 'on is #C8C8C8, off #2C2C2E (Apple\'s lit and unlit buttons)')
    # demo's own hit test: rows under the disc, drags that start beside it reach the list
    m = QM()
    tree = asset_tree(UI)
    node(tree, 'view_queue').h = 3000
    top = lambda x, y: stock_target(m, tree, x, y)[-1]
    expect(top(29, 25) == 'btn_return' and top(8, 6) == 'btn_return' and top(290, 25) == 'view_queue' and top(160, 25) == 'view_queue' and top(160, 300) == 'view_queue',
           f'Back is hit at the glass\'s centre and corner, everything else on the band is the list ({[top(29, 25), top(290, 25), top(160, 25)]})')
    expect(top(80, O['QP_PILL_Y'] + 20) == 'btn_shuffle' and top(230, O['QP_PILL_Y'] + 20) == 'btn_repeat' and top(160, O['QP_PILL_Y'] + 20) == 'view_queue', 'the buttons are hit, the 10 px between them is the list')
    import pod_i18n
    for key in ("Queue", "No upcoming songs"):
        expect(set(pod_i18n.TEXT[key]) == set(pod_i18n.LOCALES) and all(pod_i18n.TEXT[key][lc] for lc in pod_i18n.LOCALES) and pod_i18n.TEXT[key]['en_US'] == key, f'"{key}" is translated in all 13 languages')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def open_tests(ctx):
    """2. Now Playing's queue button and the open: what it reads, binds and shows; the fallbacks to the stock drawer."""
    expect = ctx.expect
    m = queue_machine()
    r = m.call(PSYMS['np_on_queue'], count=900000000)
    expect(r == O['RET_STOP'] and ('window_open', 'm1plus_queue') in m.calls, f'the queue button opens our page and stops the stock handler (RET_STOP, {r})')
    destroy(m)
    for why, setup in (('an empty queue', lambda m: m.setword(PLAY_QUEUE, m.new_deque([]))), ('no queue at all', lambda m: m.setword(PLAY_QUEUE, 0)),
                       ('no track at the position', lambda m: setattr(m, 'play_pos', -1)), ('a position past the queue', lambda m: setattr(m, 'play_pos', 99)),
                       ('a stream (play type 2)', lambda m: setattr(m, 'ptype', 2)), ('play type 3', lambda m: setattr(m, 'ptype', 3)),
                       ('play type 0xf0', lambda m: setattr(m, 'ptype', 0xf0)), ('play type 0xf1', lambda m: setattr(m, 'ptype', 0xf1)),
                       ('a window that will not open', lambda m: m.windows.__setitem__('m1plus_queue', 0))):
        m = queue_machine(); setup(m)
        r = m.call(PSYMS['np_on_queue'], count=900000000)
        expect(r == O['RET_OK'] and not [c for c in m.calls if c[0] in ('navigator_back', 'start_playqueue')], f'{why}: RET_OK, the stock drawer opens ({r})')
    for t in (0, 1):
        m = queue_machine(); m.ptype = t
        expect(m.call(PSYMS['queue_open'], count=900000000) == 0, f'play type {t} (a local file) opens the page')
        destroy(m)
    m = queue_machine(); del m.widgets['btn_repeat']
    r = m.call(PSYMS['queue_open'], count=900000000)
    expect((r & 0xffffffff) == 0xfffffffe and ('navigator_back',) in m.calls, 'a window without the page\'s widgets goes back and says -2')
    m = opened()
    expect(all((m.widgets[n], O['EVT_CLICK']) in m.bound for n in ('btn_return', 'btn_shuffle', 'btn_repeat')), 'Back, Shuffle and Repeat have click handlers')
    expect(all((m.view, O[e]) in m.bound for e in ('EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT', 'EVT_AFTER_PAINT')) and (m.sv, O['EVT_SCROLL']) in m.bound and (m.sv, O['EVT_SCROLL_END']) in m.bound
           and (m.window, O['EVT_DESTROY']) in m.bound and (m.window, O['EVT_WINDOW_TO_FG']) in m.bound and (m.window, O['EVT_WINDOW_TO_BG']) in m.bound,
           'the content view takes the touches and the paint, the scroll_view its scroll events, the window its destroy and foreground events')
    expect(len([1 for t in m.timers if t[1] == O['QP_TICK_MS']]) == 1, f'one refresh timer of {O["QP_TICK_MS"]} ms ({m.timers})')
    expect(vh(m) == TOP + 4 * ROW + O['QP_BOTTOM'] and m.props.get((m.sv, 'yoffset')) == 0 and not shown(m, 'qp_empty'),
           'six tracks, the second playing: Up Next is the four after it; the content is the header, four rows and the air; the page opens at the top; no empty line')
    deep = opened(n=60, pos=40)
    expect(vh(deep) == TOP + 19 * ROW + O['QP_BOTTOM'] and deep.props.get((deep.sv, 'yoffset')) == 0, 'the 41st of 60 playing: 19 rows, opened at the top (Up Next starts at once)')
    last = opened(n=6, pos=5)
    expect(vh(last) == WIN_H and shown(last, 'qp_empty') and text_of(last, 'qp_title') == NAMES[5], 'the last track playing: no rows, the grey "No upcoming songs" line shows, the header keeps the track')
    blits, texts, fills = paint(last)
    expect(not [t for (t, r), s in texts if s.startswith('label_row')] and [b for b in blits if tuple(b[2][2:]) == (64, 64)], 'and nothing is painted below the header but the cover')
    stopped = opened(n=6, pos=0)
    expect(vh(stopped) == TOP + 5 * ROW + O['QP_BOTTOM'], 'the first track playing: the other five follow')
    r, calls = open_queue(stopped)
    expect(r == -1, 'a page that is open is not opened again')
    destroy(stopped)
    stopped.play(stopped.songs[:2], 0)
    expect(open_queue(stopped)[0] == 0 and vh(stopped) == TOP + ROW + O['QP_BOTTOM'], 'after the destroy the page opens again, on the queue the player has now')
    destroy(m, deep, last, stopped)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def header_tests(ctx):
    """3. The header: the playing track and its cover."""
    expect = ctx.expect
    m = opened(n=6, pos=1)
    expect(text_of(m, 'qp_title') == 'Freddie Freeloader' and text_of(m, 'qp_artist') == 'Artist 0', f'the playing track\'s title and artist ({[text_of(m, n) for n in ("qp_title", "qp_artist")]})')
    destroy(m)
    m = opened(n=4, pos=1, titles=['A', '', 'C', 'D'])
    expect(text_of(m, 'qp_title') == '1.flac', 'a playing track with no title shows its file name')
    destroy(m)
    m = opened(n=4, pos=2, titles=['A', 'B', 'C', 'D'], cues=(2,))
    expect(text_of(m, 'qp_title') == '2.flac', 'a CUE track shows its file name (the stock drawer\'s rule)')
    destroy(m)
    m = opened(n=6, pos=1)
    blits, texts, fills = paint(m)
    cov = [b for b in blits if tuple(b[2][2:]) == (64, 64)]
    expect(len(cov) == 1 and tuple(cov[0][2][:2]) == (O['QP_COVER_X'], O['QP_COVER_Y']), f'the cover is a 64 px blit at (10, 56) ({[b[2] for b in blits][:3]})')
    expect(('file://' + m.cover_paths[0]) in m.loads, 'it is decoded from the Cover Flow cache file of Artist 0 / Album 0')
    expect(not any('/tmp/' in u for u in m.loads), 'nothing is read from /tmp (the playing track\'s cover is the cache\'s)')
    destroy(m)
    for cover in ('marker', False):
        m = opened(cover=cover)
        blits, texts, fills = paint(m)
        expect(len([b for b in blits if tuple(b[2][2:]) == (64, 64)]) == 1 and not any(u.startswith('file://') for u in m.loads), f'cover {cover}: the placeholder disc (a blit, no file read)')
        destroy(m)
    long_title = 'The Complete Concert in Paris, Olympia, 1961 (Remastered Live Edition)'
    m = opened(n=3, pos=0, titles=[long_title, 'x', 'y'])
    expect(text_of(m, 'qp_title') == long_title, 'a long title is set whole (the label scrolls it)')
    destroy(m)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def rows_tests(ctx):
    """4. Up Next: the tracks after the playing one, painted from the stock queue."""
    expect = ctx.expect
    m = opened(n=6, pos=1)
    blits, texts, fills = paint(m)
    ttl = [(t, r) for (t, r), s in texts if s == 'label_row_title']
    sub = [(t, r) for (t, r), s in texts if s == 'label_row_sub']
    room = O['QP_TEXT_END'] - O['LIST_TEXT_X']
    expect(ttl == [(NAMES[2 + i], (74, row_y(i) + O['LIST_TITLE_Y'], room, 24)) for i in range(4)], f'the rows are the tracks after the playing one, never the playing track: titles from x 74 to 298 (row 3, cut by the window\'s edge, too: the scroll_view clips), 24 px high LIST_TITLE_Y down ({ttl})')
    expect(sub == [(f'Artist {(2 + i) // 3}', (74, row_y(i) + O['LIST_SUB_Y'], room, 20)) for i in range(4)], f'the artists LIST_SUB_Y down, 20 px high (row 3 too): {sub}')
    expect([s for _, s in texts] == ['label_row_title'] * 4 + ['label_row_sub'] * 4, 'the titles, then the artists: one text style at a time')
    expect(fills_of(fills, O['LIST_HAIR']) == [(O['LIST_HAIR'], 74, row_y(i) + 63, room, 1) for i in range(3)], 'a 1 px hairline under the text of the rows wholly in view')
    rowcov = [b for b in blits if tuple(b[2][2:]) == (52, 52)]
    expect([tuple(b[2][:2]) for b in rowcov] == [(10, row_y(i) + O['LIST_ART_Y']) for i in range(3)], f'a 52 px cover at x 10, LIST_ART_Y down each row that is wholly in view: {[tuple(b[2]) for b in rowcov]}')
    expect(len(fills) == 3 and not [f_ for f_ in fills if f_[0] == O['LIST_PRESS']], 'no wave, no dim, no mark: only the hairlines; nothing is pressed at rest')
    scroll_to(m, 200)
    blits, texts, fills = paint(m)
    got = [(t, r[1]) for (t, r), s in texts if s == 'label_row_title']
    expect(got == [(NAMES[2 + i], row_y(i) + O['LIST_TITLE_Y'] - 200) for i in range(4)], f'scrolled 200 px: the rows at their y less the offset ({got})')
    cover_blits = [b for b in blits if tuple(b[2][2:]) == (64, 64)]
    expect(not cover_blits or cover_blits[0][2][1] == O['QP_COVER_Y'] - 200, 'the header\'s cover goes up with the list')
    destroy(m)
    long_title = 'The Complete Concert in Paris, Olympia, 1961 (Remastered Live Edition)'
    m2 = opened(n=5, pos=0, titles=['P', long_title, '', 'C', 'D'], cues=(3,))
    scroll_to(m2, 100)
    blits, texts, fills = paint(m2)
    got = [t for (t, r), s in texts if s == 'label_row_title']
    expect(got[0].endswith('…') and long_title.startswith(got[0][:-1]) and 8 * len(got[0]) <= room < 8 * (len(got[0]) + 2) and got[1:] == ['2.flac', '3.flac', 'D'],
           f'a title wider than its room is cut with an ellipsis, an untitled track shows its file name, a CUE track always ({got})')
    destroy(m2)
    big = opened(n=300, pos=0)
    expect(vh(big) == TOP + 299 * ROW + O['QP_BOTTOM'], 'the content grows with the queue')
    scroll_to(big, TOP + 120 * ROW)
    blits, texts, fills = paint(big)
    seen = [t for (t, r), s in texts if s == 'label_row_title']
    expect(seen and seen[0] == 'Track 122' and len(seen) <= 8, f'row 120 (queue index 121) at the top of a 300 track queue: {seen[:3]} ({len(seen)} rows)')
    scroll_to(big, TOP + 300 * ROW + 5000)
    paint(big)
    expect(not any(c[0] == 'deque_at_oob' for c in big.calls), 'a list pulled past its end reads no record beyond it')
    destroy(big)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def loader_tests(ctx):
    """5. The cover loader: one per tick, none while the list moves, the cache's file or the placeholder."""
    expect = ctx.expect
    m = opened(n=9, pos=0)
    paint(m)
    m.loads.clear()
    ticks = 0
    while ticks < 40:
        m.calls = []
        m.call(PSYMS['qp_on_load'], count=900000000)
        ticks += 1
        if not any(c[0] == 'timer_add' for c in m.calls): break
    expect(3 <= ticks <= 10, f'the visible rows are loaded one a tick and the timer stops when none is left ({ticks} ticks)')
    expect(sorted(set(m.loads)) == sorted('file://' + p for p in m.cover_paths.values()) and len(m.loads) >= 2, f'the covers come from the Cover Flow cache files ({m.loads})')
    blits, texts, fills = paint(m)
    expect(len([b for b in blits if tuple(b[2][2:]) == (52, 52)]) >= 3, 'every visible row has a cover blit (the file\'s or the placeholder)')
    destroy(m)
    m = opened(n=9, pos=0)
    paint(m)
    m.loads.clear()
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([1, 1]))
    m.calls = []
    m.call(PSYMS['qp_on_load'], count=900000000)
    expect(not m.loads and any(c[0] == 'timer_add' for c in m.calls), 'a list that is being dragged decodes nothing and looks again next tick')
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([0, 0]))
    destroy(m)


def episode_open(paths, tracks, pos=0):
    """A queue of podcast episodes (and tracks) over show folders: Story Show has cover.jpg and folder.jpg (cover.jpg wins, the Shows page's rank) beside other pictures,
    Big Show's cover.jpg is too big to decode, Bare Show has no picture. The page open and every row loaded once."""
    m = queue_machine(n=len(paths), pos=pos, paths=paths, tracks=tracks)
    m.listing[EP_S] = [('.', 4), ('..', 4), ('Ep 1.mp3', 8), ('art.jpg', 8), ('folder.jpg', 8), ('cover.jpg', 8)]
    for nm in ('art.jpg', 'folder.jpg', 'cover.jpg'):
        m.pics[f'{EP_S}/{nm}'] = jpeg_header(600); m.images[f'file://{EP_S}/{nm}'] = (8, 8, COVER_PIX[2])
    m.listing[EP_B] = [('.', 4), ('b.mp3', 8), ('cover.jpg', 8)]
    m.pics[f'{EP_B}/cover.jpg'] = jpeg_header(3000); m.images[f'file://{EP_B}/cover.jpg'] = (8, 8, COVER_PIX[2])
    m.listing[EP_N] = [('.', 4), ('n.mp3', 8)]
    m.top_main = m.window
    r, calls = open_queue(m)
    assert r == 0, f'the page did not open ({r})'
    load_all(m)
    return m


EP_S, EP_B, EP_N = '/mnt/mmc/Podcasts/Story Show', '/mnt/mmc/podcasts/Big Show', '/mnt/mmc/podcasts/Bare Show'


def episode_tests(ctx):
    """5c. A podcast episode shows its show folder's picture (the Podcasts page's choice), in the header and the rows; it is never looked up as an album."""
    expect = ctx.expect
    story = [f'{EP_S}/Ep {i}.mp3' for i in range(1, 7)]
    m = episode_open(story, [('Host', 'Story Show')] * 6)
    blits, texts, fills = paint(m)
    expect(covers_of(m) and set(covers_of(m)) == {f'file://{EP_S}/cover.jpg'}, f'the header and every row: the show\'s cover.jpg (before folder.jpg; another picture is not a cover) ({sorted(set(covers_of(m)))})')
    expect(len([b for b in blits if tuple(b[2][2:]) == (64, 64)]) == 1 and len([b for b in blits if b[2][2] == 52]) == 4, f'the header\'s cover and the four rows in view (the last cut at the window\'s edge) are painted ({[tuple(b[2]) for b in blits]})')
    expect(m.dir_log.count(EP_S) == 1, f'one show: its folder is read once while the page is open ({m.dir_log})')
    expect(not m.__dict__.get('queries'), 'no album lookup (no cover map query) for episodes')
    destroy(m)
    r, calls = open_queue(m); load_all(m)
    expect(r == 0 and m.dir_log.count(EP_S) == 2, f'the next open reads the folder again (a picture added meanwhile shows) ({m.dir_log})')
    destroy(m)

    paths = [f'{EP_B}/b.mp3', f'{EP_N}/n.mp3', story[0], '/mnt/mmc/m/3.flac']
    m = episode_open(paths, [('B', 'Big Show'), ('N', 'Bare Show'), ('Host', 'Story Show'), ('Artist 0', 'Album 0')])
    blits, texts, fills = paint(m)
    expect(set(covers_of(m)) == {f'file://{EP_S}/cover.jpg', 'file://' + m.cover_paths[0]}, f'a show whose picture is too big and a show with none: the placeholder (no file decoded); a song keeps its album\'s cache file ({sorted(set(covers_of(m)))})')
    expect(len([b for b in blits if tuple(b[2][2:]) == (64, 64)]) == 1 and len([b for b in blits if tuple(b[2][2:]) == (52, 52)]) == 3, 'every row and the header still have a cover blit')
    destroy(m)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def fnv_nocase(s):
    """The payload's album name hash (cmap_hash): FNV-1a over the bytes of the UTF-8 name with ASCII A-Z folded to lower case."""
    h = 2166136261
    for c in s.encode():
        h = ((h ^ (c + 32 if 65 <= c <= 90 else c)) * 16777619) & 0xffffffff
    return h


def finish_loading(m):
    """The loader until its timer stops."""
    for _ in range(400):
        m.calls = []
        m.call(PSYMS['qp_on_load'], count=900000000)
        if not any(c[0] == 'timer_add' for c in m.calls): return


def covers_of(m): return sorted(u for u in m.loads if u.startswith('file://'))


def load_all(m, step=200):
    """Every row of the list brought into view (down the list, the loader run at each stop), then back to the top."""
    top = vh(m)
    for off in list(range(0, top, step)) + [0]:
        scroll_to(m, off); paint(m); finish_loading(m); tick(m)


def collab_open(tracks, library, pos=0, **kw):
    """A queue of `tracks` over `library`, the page open and every row loaded once."""
    m = queue_machine(n=len(tracks), pos=pos, tracks=tracks, library=library, **kw)
    m.top_main = m.window
    r, calls = open_queue(m)
    assert r == 0, f'the page did not open ({r})'
    load_all(m)
    return m


def collab_tests(ctx):
    """5b. A track whose artist differs from its album's (a collab, "A; B") shows the album's cover, from the cover map: ONE getAllAlbum query on the first miss, never the album list."""
    expect = ctx.expect
    ALB = 'WHAT HAPPENED TO THE STREETS?'
    url = lambda a, b: 'file://' + art_file(album_key(a, b))
    queries = lambda m: list(m.__dict__.get('queries', []))
    ASQL = pod.ALBUM_SQL
    lib = [('21 Savage', ALB, True), ('Zed', 'Other', False), ("O'Brien", "It's a Wonder", True), ('Café Band', 'Café', True), ('Éa', 'Éclair', True), ('B', 'Born', True),
           ('Low', 'Lower Case Album', True), ('Feat', 'Featured Album', True)]
    tracks = [('21 Savage; Young Nudy', ALB), ('21 Savage', ALB), ('Low; X', 'LOWER CASE ALBUM'), ('G Herbo; Feat', 'Featured Album'), ('Nobody', ''), ('Zed; Q', 'Other'),
              ("O'Brien; X", "It's a Wonder"), ('Cafe Q', 'CAFé'), ('Ea Q', 'éclair'), ('B; Q', 'Born'), ('Ghost', 'Not In The Library')]
    m = queue_machine(n=len(tracks), pos=0, tracks=tracks, library=lib)
    m.top_main = m.window
    shown0, tmp = m.word(pod.DATA['PDEQ_SHOWLIST'][0]), pod.DATA['PDEQ_TOOLS_TMP'][0]
    m.present.add('/mnt/mmc/m1plus-log')
    r, calls = open_queue(m)
    expect(r == 0 and queries(m) == [ASQL] and m.loads.count(url('21 Savage', ALB)) == 1, f'the playing collab track\'s header: the first miss builds the map, ONE query (getAllAlbum\'s statement), the album\'s cover ({queries(m)})')
    load_all(m)
    got = set(covers_of(m))
    expect(got == {url('21 Savage', ALB), url('Low', 'Lower Case Album'), url('Feat', 'Featured Album'), url("O'Brien", "It's a Wonder"), url('Café Band', 'Café'), url('B', 'Born')},
           f'a collab, an ASCII case difference, a feature, a quote, a name with \u00e9 and a collab of an album with a cover take the album\'s cover; the album-less, the no-art album, '
           f'\u00e9clair against \u00c9clair (non-ASCII case) and an album the library lacks do not ({sorted(u[-17:] for u in got)})')
    log = m.fs.get('/mnt/mmc/m1plus.log', b'').decode()
    expect(log.startswith('queue: cover map ') and ', 8 albums, 8 kept, 0 ambiguous, 11 queued' in log and log.count('\n') == 1, f'the opt-in log gets one line for the build ({log!r})')
    expect(len(queries(m)) == 1, 'no other query for the page: not per row, not at paint, not in the refresh ticks, not scrolling down and back')
    expect(not any(c[0] in ('loadLocalClassList', 'deque_assign', 'loadAlbumList') for c in calls + m.calls) and m.word(pod.DATA['PDEQ_SHOWLIST'][0]) == shown0, '*pdeq_showlist is untouched and no album list is loaded')
    expect(m.deques[m.word(tmp)] == [], 'the stock records are cleared from the scratch deque')
    destroy(m)
    expect(any(c[0] == 'free' for c in m.calls), 'closing the page frees the map')
    m.calls = []
    r, calls = open_queue(m); load_all(m)
    expect(r == 0 and len(queries(m)) == 2, f'the next open builds it again, one query ({len(queries(m))})')
    destroy(m)

    # a queue with no miss builds nothing
    m = collab_open([('21 Savage', ALB), ('B', 'Born'), ("O'Brien", "It's a Wonder")], lib)
    expect(not queries(m) and len(set(covers_of(m))) == 3, 'every track has its own file: no query')
    destroy(m)

    # a failed query and an empty library: one query, then none, the placeholder for every miss
    for label, kw, lb in (('a failed query', {'fails': True}, lib), ('an empty library', {}, [])):
        m = queue_machine(n=len(tracks), pos=0, tracks=tracks, library=lb)
        m.top_main = m.window
        if kw.get('fails'): m.album_query_fails = True
        r, calls = open_queue(m); load_all(m)
        own = {url('21 Savage', ALB)} if lb else set()   # (the tracks whose own key has a file)
        expect(r == 0 and len(queries(m)) == 1 and set(covers_of(m)) == own, f'{label}: one query, no other, the placeholder for every miss ({len(queries(m))}, {len(covers_of(m))} covers)')
        destroy(m)
    # no memory for the map
    m = queue_machine(n=len(tracks), pos=0, tracks=tracks, library=lib)
    m.top_main = m.window
    m.calloc_fail_size = 16 + 8 * (len(lib) - 1) + (len(lib) + 3) // 4   # (the map: count, state pointer, the entries, 2 bits an entry)
    r, calls = open_queue(m); load_all(m)
    expect(r == 0 and len(queries(m)) == 1 and set(covers_of(m)) == {url('21 Savage', ALB)} and m.deques[m.word(tmp)] == [], 'no memory for the map: one query, none after it, the scratch deque cleared, the placeholder for every miss')
    destroy(m)

    # two names with one hash, and one folded name under two records
    import random
    seen, a, b, rr = {}, None, None, random.Random(3)
    for i in range(2000000):
        nm = 'c%x' % rr.getrandbits(40)
        h = fnv_nocase(nm)
        if h in seen and seen[h] != nm: a, b = seen[h], nm; break
        seen[h] = nm
    expect(a is not None and fnv_nocase(a) == fnv_nocase(b) and a != b, f'a colliding pair of names was found ({a}, {b})')
    lib2 = [('P', a, True), ('Q', b, True), ('R', 'Fine', True), ('S', 'Dup', True), ('T', 'DUP', True)]
    tr2 = [('P; X', a), ('Q; X', b), ('R; X', 'Fine'), ('S; X', 'Dup'), ('T; X', 'dup')]
    m = collab_open(tr2, lib2, pos=0)
    got = covers_of(m)
    expect(set(got) == {url('R', 'Fine')} and len(queries(m)) == 1,
           f'two different names with one hash are both ambiguous (the placeholder), a name of its own resolves; one folded name under two records with different keys is the same case: dropped ({[g[-30:] for g in got]})')
    destroy(m)

    # the cap: the first CC_CMAP_MAX albums of the query resolve, the rest show the placeholder; one query
    cap = O['CC_CMAP_MAX'] if 'CC_CMAP_MAX' in O else 4096
    lib3 = [(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap + 40)]
    tr3 = [(f'Artist {i}; G', f'Album {i:05d}') for i in (5, cap - 1, cap, cap + 39)]
    m = collab_open(tr3, lib3, pos=0)
    expect(set(covers_of(m)) == {url('Artist 5', 'Album 00005'), url(f'Artist {cap - 1}', f'Album {cap - 1:05d}')} and len(queries(m)) == 1,
           f'past the cap ({cap}): the albums inside resolve, those beyond show the placeholder, one query ({len(set(covers_of(m)))} covers)')
    destroy(m)


def find_collision():
    """Two different names with one cover map hash (FNV-1a, ASCII folded)."""
    import random
    seen, rr = {}, random.Random(3)
    for i in range(2000000):
        nm = 'c%x' % rr.getrandbits(40)
        h = fnv_nocase(nm)
        if h in seen and seen[h] != nm: return seen[h], nm
        seen[h] = nm
    return None, None


def cmap_tests(ctx):
    """5d. The cover map's lazy file checks: the build opens no file, an album's file is looked at once (and the answer kept, 2 bits an album), a queue opens only what its rows need, a
    tile shown again after its eviction decodes again without the check; an album past the cap whose hash is a kept album's makes it ambiguous."""
    expect = ctx.expect
    ALB = 'WHAT HAPPENED TO THE STREETS?'
    path = lambda a, b: art_file(album_key(a, b))
    url = lambda a, b: 'file://' + path(a, b)
    fopens = lambda m: list(m.__dict__.get('fopens', []))
    probes = lambda m, p: fopens(m).count(p)

    # the build itself and cc_cmap_key, called as the page does
    lib = [(f'Artist {i}', f'Album {i:02d}', i % 3 != 1) for i in range(23)] + [('21 Savage', ALB, True), ('Dup', 'Same', True)]
    m = queue_machine(n=1, tracks=[('X', 'Y')], library=lib)
    st, before = m.alloc(16), len(fopens(m))
    mp = m.call(PSYMS['cc_cmap_build'], a0=st, count=900000000)
    stat = [m.word(st + 4 * k) for k in range(3)]
    expect(mp and stat == [len(lib), len(lib), 0] and len(fopens(m)) == before and not any(c[0] in ('fopen', 'fseek', 'ftell') for c in m.calls),
           f'cc_cmap_build: {len(lib)} albums kept, none ambiguous, NO cover file opened ({stat}, {len(fopens(m)) - before} opens)')
    ask = lambda album: m.call(PSYMS['cc_cmap_key'], a0=mp, a1=m.cstr(album), count=900000000)
    want = {b: (album_key(a, b) if c else 0) for a, b, c in lib}
    got, mark = {}, len(fopens(m))
    for b in want: got[b] = ask(b)
    expect(got == want and len(fopens(m)) - mark == len(lib), f'every album asked for once: its key (0 with no picture) and one look at its file each ({len(fopens(m)) - mark} opens for {len(lib)} albums)')
    mark = len(fopens(m))
    again = {b: ask(b.upper() if k % 2 else b) for k, b in enumerate(reversed(list(want)))}
    expect(again == want and len(fopens(m)) == mark, 'asked again (in the other order, in either case): the same answers from the 2 bit states, no file looked at, the neighbours in a byte untouched')
    expect(ask('No Such Album') == 0 and ask('') == 0 and len(fopens(m)) == mark, 'an album the library lacks, and an empty name: 0, no file looked at')
    m.call(PSYMS['cc_cmap_free'], a0=mp)
    expect(m.call(PSYMS['cc_cmap_key'], a0=0, a1=m.cstr(ALB)) == 0, 'no map: 0')

    # a queue of five tracks opens the files its rows need and no others
    big = [(f'Artist {i}', f'Album {i:04d}', i % 2 == 0) for i in range(600)]
    tr = [('Artist 4; G', 'Album 0004'), ('Artist 10', 'Album 0010'), ('Artist 6; G', 'Album 0006'), ('Artist 7; G', 'Album 0007'), ('Artist 4; H', 'ALBUM 0004')]
    m = collab_open(tr, big, pos=0)
    allowed = {path(a, b) for a, b in tr} | {path('Artist 4', 'Album 0004'), path('Artist 6', 'Album 0006'), path('Artist 7', 'Album 0007'), path('Artist 10', 'Album 0010')}
    art = [f for f in fopens(m) if f.startswith('/mnt/mmc/.m1plus/covers/')]
    expect(set(art) <= allowed and len(set(art)) <= 8, f'a 5 track queue over 600 albums opens only the files of its own keys and the albums of its collabs ({len(set(art))} files, {len(art)} opens)')
    expect(set(covers_of(m)) == {url('Artist 4', 'Album 0004'), url('Artist 6', 'Album 0006'), url('Artist 10', 'Album 0010')}, 'the covers shown: the two collabs of an album with a cover, the solo; the odd album has none')
    destroy(m)

    # several collab rows of one album look at its file once; an album with no picture is looked at once and not again
    for have in (True, False):
        lb = [('Artist 0', 'Album A', have), ('Artist 1', 'Album B', True)]
        tr = [(f'Artist 0; G{i}', 'Album A') for i in range(6)]
        m = collab_open(tr, lb, pos=0)
        canon = path('Artist 0', 'Album A')
        decodes = m.loads.count('file://' + canon)
        expect(probes(m, canon) == (decodes + 1 if have else 1) and decodes == (6 if have else 0),
               f'six collab rows (header included) of an album {"with" if have else "with no"} picture: the file is looked at once ({probes(m, canon)} opens, {decodes} decodes)')
        destroy(m)

    # eviction: more rows than the ring holds, scrolled down and back twice: the tiles decode again, the files are not looked at again
    lb = [('Artist 0', 'Album A', True), ('Artist 1', 'Album B', True), ('Artist 2', 'Album C', False)]
    tr = [(f'Artist {i % 3}; G{i}', f'Album {"ABC"[i % 3]}') for i in range(120)]
    m = collab_open(tr, lb, pos=0)
    d1 = {k: m.loads.count(url(f'Artist {k}', f'Album {"ABC"[k]}')) for k in range(3)}
    load_all(m)
    d2 = {k: m.loads.count(url(f'Artist {k}', f'Album {"ABC"[k]}')) for k in range(3)}
    expect(d2[0] > d1[0] and d2[1] > d1[1] and d2[2] == 0, f'tiles shown again after their eviction are decoded again ({d1} -> {d2})')
    left = {k: probes(m, path(f'Artist {k}', f'Album {"ABC"[k]}')) - m.loads.count(url(f'Artist {k}', f'Album {"ABC"[k]}')) for k in range(3)}
    expect(left == {0: 1, 1: 1, 2: 1}, f'each album\'s file was looked at once however often its tiles came back (extra opens beyond the decodes: {left})')
    expect(len(m.__dict__.get('queries', [])) == 1, 'and still one query')
    destroy(m)

    # a collision across the cap: a kept album and one past the cap share a hash under two keys: both show the placeholder (either one inside)
    a, b = find_collision()
    cap = O['CC_CMAP_MAX'] if 'CC_CMAP_MAX' in O else 4096
    expect(a is not None and fnv_nocase(a) == fnv_nocase(b), f'a colliding pair was found ({a}, {b})')
    for inside, beyond in ((a, b), (b, a)):
        lb = [(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap - 1)] + [('P', inside, True)] + [(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap, cap + 30)] + [('Q', beyond, True)]
        tr = [('P; X', inside), ('Q; X', beyond), ('Artist 5; G', 'Album 00005')]
        m = collab_open(tr, lb, pos=0)
        m.present.add('/mnt/mmc/m1plus-log')
        got = covers_of(m)
        expect(got == [url('Artist 5', 'Album 00005')] and len(m.__dict__.get('queries', [])) == 1,
               f'a name inside the cap and a name past it with one hash: both the placeholder, an album of its own resolves ({[g[-30:] for g in got]})')
        destroy(m)
    # control: a name past the cap with no kept hash of its own changes nothing, and the same album twice (same key) past the cap is no collision
    lb = [(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap - 1)] + [('P', a, True)] + [('P', a, True), ('Q', 'Elsewhere', True)]
    m = collab_open([('P; X', a), ('Artist 9; G', 'Album 00009')], lb, pos=0)
    expect(set(covers_of(m)) == {url('P', a), url('Artist 9', 'Album 00009')}, 'past the cap, the same album again (the same key) is no collision: the kept album resolves')
    destroy(m)
    m = queue_machine(n=3, tracks=[('P; X', a), ('Q; X', b), ('Artist 5; G', 'Album 00005')], library=[(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap - 1)] + [('P', a, True)] + [(f'Artist {i}', f'Album {i:05d}', True) for i in range(cap, cap + 5)] + [('Q', b, True)])
    m.top_main = m.window
    m.present.add('/mnt/mmc/m1plus-log')
    open_queue(m)
    log = m.fs.get('/mnt/mmc/m1plus.log', b'').decode()
    expect(f', {cap + 6} albums, {cap - 1} kept, 1 ambiguous, 3 queued' in log, f'the log counts the entries dropped for a collision across the cap ({log!r})')
    destroy(m)


def scroll_tests(ctx):
    """5c. A shuffled queue of thousands: the whole list scrolled down and back asks the database once."""
    expect = ctx.expect
    import random
    rnd = random.Random(7)
    lib = []
    for i in range(300):
        name = f"Album's {i}" if i % 13 == 0 else f'Album {i}'
        lib.append((f'Artist {i}', name, i % 4 != 3))
    tracks = []
    for _ in range(3000):
        a, b, c = lib[rnd.randrange(len(lib))]
        k = rnd.randrange(6)
        tracks.append((a, b) if k < 2 else (f'{a}; Guest', b if k < 4 else b.upper()) if k < 5 else ('Loose', ''))
    m = queue_machine(n=len(tracks), pos=0, tracks=tracks, library=lib)
    m.top_main = m.window
    shown0, tmp = m.word(pod.DATA['PDEQ_SHOWLIST'][0]), pod.DATA['PDEQ_TOOLS_TMP'][0]
    r, calls = open_queue(m)
    after_open = len(m.__dict__.get('queries', []))
    expect(r == 0 and vh(m) == TOP + (len(tracks) - 1) * ROW + O['QP_BOTTOM'] and after_open <= 1, f'a 3,000 track queue opens ({after_open} queries so far)')
    top = vh(m)
    path = list(range(0, top, 1400)) + list(range(top, 0, -1400)) + [0]
    for off in path:
        scroll_to(m, off); paint(m); finish_loading(m); tick(m)
    q = m.__dict__.get('queries', [])
    expect(q == [pod.ALBUM_SQL], f'scrolled to the end and back: exactly one library query in all, none per row, per paint or per tick ({len(q)}: {q[:3]})')
    expect(not any(c[0] in ('loadLocalClassList', 'deque_assign', 'loadAlbumList') for c in m.calls) and m.word(pod.DATA['PDEQ_SHOWLIST'][0]) == shown0 and m.deques[m.word(tmp)] == [],
           '*pdeq_showlist unchanged, no album list loaded, the scratch deque cleared')
    have = {'file://' + art_file(album_key(a, b)) for a, b, c in lib if c}
    expect(set(covers_of(m)) <= have and covers_of(m), 'every cover read is the cache file of a library album that has one')
    destroy(m)
    # cost of the map itself (the payload's instructions only: the SQL is mocked, so this says nothing of the database): the same open with a collab header (builds it) less one with a solo header
    for n in (1000, 4000):
        libn = [(f'Artist {i}', f'Album {i}', i % 2 == 0) for i in range(n)]
        cost = []
        for header in (('Artist 0; G', 'Album 0'), ('Artist 0', 'Album 0')):
            m = queue_machine(n=2, pos=0, tracks=[header, ('X', 'Y')], library=libn)
            m.top_main = m.window
            m.count()
            r, calls = open_queue(m)
            cost.append(m.icount)
            destroy(m)
        print(f'  Queue cover map, {n} albums: {cost[0] - cost[1]:,} payload instructions to build it (the query is mocked; no file is opened)')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def play_tests(ctx):
    """6. The taps: a row plays through start_playqueue (the queue index); the press fill; Back."""
    expect = ctx.expect
    m = opened(n=6, pos=1)
    calls = tap(m, 150, row_y(1) + 20)
    expect(('start_playqueue', 3) in calls and m.play_pos == 3 and m.word(FORCE) & 0xff == 1, 'a tap on the second row (queue index 3): start_playqueue(3) (the stock drawer\'s row handler) and force_refreshflag set')
    expect(not [c for c in calls if c[0] in ('navigator_to_with_context', 'loadSongList', 'start_player', 'navigator_back')], 'the page stays and the queue is not rebuilt: only the position moves')
    expect(text_of(m, 'qp_title') == NAMES[3] and vh(m) == TOP + 2 * ROW + O['QP_BOTTOM'], 'the header follows at once and Up Next is now the tracks after the new one')
    _, texts, _ = paint(m)
    expect([t for (t, r), s in texts if s == 'label_row_title'] == NAMES[4:6], 'its rows are the two after it')
    for label, dx, dy in (('a drag', 0, 14), ('a slide sideways', 12, 0)):
        expect(not [c for c in tap(m, 150, row_y(1) + 20, dx, dy) if c[0] == 'start_playqueue'], f'{label} plays nothing')
    expect(not [c for c in tap(m, 150, 100) if c[0] == 'start_playqueue'] and not [c for c in tap(m, 150, TOP - 4) if c[0] == 'start_playqueue'] and not [c for c in tap(m, 150, row_y(2) + 10) if c[0] == 'start_playqueue'],
           'a tap on the header, the gap above the first row and the air below the last plays nothing')
    touch(m, 'down', 150, row_y(0) + 20, 'qp_on_down')
    _, _, fills = paint(m)
    expect((O['LIST_PRESS'], 0, row_y(0), O['QP_ROW_W'], ROW - 1) in fills, f'the row under the finger is filled: {[f_ for f_ in fills if f_[0] == O["LIST_PRESS"]]}')
    touch(m, 'abort', 150, row_y(0) + 20, 'qp_on_abort')
    _, _, fills = paint(m)
    expect(not any(f_[0] == O['LIST_PRESS'] for f_ in fills), 'an abort (the scroll_view took a drag) clears it')
    touch(m, 'down', 150, row_y(0) + 20, 'qp_on_down'); touch(m, 'up', 150, row_y(0) + 20, 'qp_on_up', 1080)
    expect(m.play_pos == 4, 'a tap on the first row plays the next track')
    _, _, fills = paint(m)
    expect(not any(f_[0] == O['LIST_PRESS'] for f_ in fills), 'and a release clears the fill')
    destroy(m)
    new = lambda m: [m.record(album='New', artist='New Artist', path=f'/mnt/mmc/n/{i}.flac', title=f'New {i}', name=f'n{i}.flac', rid=500 + i) for i in range(3)]
    m = opened(n=6, pos=1)
    m.play(new(m), 0)
    blits, texts, fills = paint(m)
    expect(not texts and not blits and any(c[0] == 'timer_add' for c in m.calls), 'a paint of a queue that is not the page\'s paints nothing and asks to read it again')
    m.call(PSYMS['qp_on_stale'], count=900000000)
    expect(text_of(m, 'qp_title') == 'New 0' and vh(m) == TOP + 2 * ROW + O['QP_BOTTOM'], 'the page reads the new queue when it is on top')
    destroy(m)
    m = opened(n=6, pos=1)
    m.play(new(m), 0)
    expect(not [c for c in tap(m, 150, row_y(1) + 20) if c[0] == 'start_playqueue'], 'a tap on rows that are not the player\'s queue plays nothing')
    destroy(m)
    m = opened(n=6, pos=1)
    touch(m, 'down', 150, row_y(1) + 20, 'qp_on_down')
    m.play(new(m), 0)
    touch(m, 'up', 150, row_y(1) + 20, 'qp_on_up', 1080)
    expect(not [c for c in m.calls if c[0] == 'start_playqueue'] and text_of(m, 'qp_title') == 'New 0', 'a queue replaced between the press and the release: the page reads the new one instead of playing a row of the old')
    destroy(m)
    m = opened()
    expect(('navigator_back',) in click(m, 'btn_return'), 'Back goes back to Now Playing')
    destroy(m)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def mode_tests(ctx):
    """7. The buttons: Shuffle toggles the stock Shuffle, Repeat cycles off / all / one; the buttons show the mode."""
    expect = ctx.expect
    RA, RO, OR = O['MODE_REPEAT_ALL'], O['MODE_REPEAT_ONE'], O['MODE_ORDER']
    on_n, on_d, off_n, off_d = O['QP_PILL_ON'], O['QP_PILL_ON_DOWN'], O['QP_PILL_OFF'], O['QP_PILL_OFF_DOWN']

    def look(m):
        out = {}
        for name in ('btn_shuffle', 'btn_repeat'):
            w = m.widgets[name]
            bg = {s[1]: s[2] for s in m.styled if s[0] == w and s[1].endswith(':bg_color')}
            out[name] = (bg.get('normal:bg_color'), bg.get('pressed:bg_color'), m.props.get((w, 'style:normal:icon')), m.props.get((w, 'style:pressed:icon')))
        return out
    m = queue_machine(); m.top_main = m.window; m.mode = OR; open_queue(m)
    lk = look(m)
    expect(lk['btn_shuffle'] == (off_n, off_d, 'sg_shuffle', 'sg_shuffle') and lk['btn_repeat'] == (off_n, off_d, 'sg_repeat', 'sg_repeat'), f'List play: both buttons dark with the white glyph ({lk})')
    expect(O['QP_PILL_OFF'] == 0xff2e2c2c and O['QP_PILL_OFF_DOWN'] == 0xff3d3a3a and O['QP_PILL_ON_DOWN'] < O['QP_PILL_ON'], 'the off look is the asset\'s own colours (#2C2C2E, pressed #3A3A3D); the lit one is lighter, pressed a little darker')
    destroy(m)
    for start in (OR, RA, RO):   # Shuffle is the payload's flag: stock's repeat mode is not touched, whatever it is
        m = queue_machine(); m.top_main = m.window; m.mode = start; open_queue(m)
        expect(not flag_on(m) and look(m)['btn_shuffle'][0] == off_n, f'repeat mode {start}: Shuffle starts off')
        calls = click(m, 'btn_shuffle')
        expect(flag_on(m) and m.mode == start and not [c for c in calls if c[0] == 'mclSetPlayMode'] and ('write_int_config', start, 'PLAYSET', 'PLAYMODE') in calls,
               f'Shuffle on from repeat mode {start}: the flag is saved, stock\'s mode stays {start} (and is saved as it is)')
        expect(look(m)['btn_shuffle'] == (on_n, on_d, 'sg_shuffle_on', 'sg_shuffle_on') and look(m)['btn_repeat'][0] == (off_n if start == OR else on_n), 'the Shuffle button is lit, Repeat shows its own state')
        click(m, 'btn_shuffle')
        expect(not flag_on(m) and m.mode == start and look(m)['btn_shuffle'][0] == off_n, f'Shuffle off again: the flag goes, the repeat mode {start} stays')
        destroy(m)
    m = queue_machine(); m.top_main = m.window; m.mode = OR; open_queue(m)
    seq = []
    for _ in range(4):
        click(m, 'btn_repeat'); seq.append((m.mode, look(m)['btn_repeat']))
    expect([s[0] for s in seq] == [RA, RO, OR, RA], f'Repeat cycles all, one, off, all ({[s[0] for s in seq]})')
    expect(seq[0][1] == (on_n, on_d, 'sg_repeat_on', 'sg_repeat_on') and seq[1][1] == (on_n, on_d, 'sg_repeat1_on', 'sg_repeat1_on') and seq[2][1] == (off_n, off_d, 'sg_repeat', 'sg_repeat'),
           f'Repeat all is the lit button with the dark repeat glyph, Repeat one with the dark repeat-1 glyph, off the dark button ({seq})')
    expect(('write_int_config', RA, 'PLAYSET', 'PLAYMODE') in m.calls and not flag_on(m), 'the mode is saved as the Play settings page saves it')
    destroy(m)
    # independent, as on Apple: Repeat cycles the same with Shuffle on, and Shuffle plus Repeat all is allowed
    m = queue_machine(); m.top_main = m.window; m.mode = OR; open_queue(m)
    click(m, 'btn_shuffle'); seq = []
    for _ in range(3):
        click(m, 'btn_repeat'); seq.append((m.mode, flag_on(m), look(m)['btn_shuffle'][0], look(m)['btn_repeat'][0]))
    expect(seq == [(RA, True, on_n, on_n), (RO, True, on_n, on_n), (OR, True, on_n, off_n)], f'Shuffle on: Repeat cycles all, one, off and Shuffle stays lit ({seq})')
    destroy(m)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def tick_tests(ctx):
    """8. The refresh timer: the player moves on, the mode changes elsewhere, the queue is replaced, a dark screen, the destroy."""
    expect = ctx.expect
    m = opened(n=6, pos=1)
    paint(m)
    r, calls = tick(m)
    expect(r == O['RET_REPEAT'] and not [c for c in calls if c[0] in ('widget_set_text_utf8', 'widget_invalidate_force')], 'a tick with nothing new changes nothing and repeats')
    m.play_pos = 2   # the next track started (auto advance, a hardware key)
    r, calls = tick(m)
    expect(r == O['RET_REPEAT'] and text_of(m, 'qp_title') == NAMES[2] and vh(m) == TOP + 3 * ROW + O['QP_BOTTOM'] and any(c[0] == 'widget_invalidate_force' and c[1] == m.sv for c in calls),
           'the next track: the header follows, the rows are the three after it, the list is redrawn')
    _, texts, _ = paint(m)
    expect([t for (t, r), s in texts if s == 'label_row_title'] == NAMES[3:6], 'the playing track left Up Next')
    m.play_pos = 5; tick(m)
    expect(shown(m, 'qp_empty') and vh(m) == WIN_H, 'the last track: "No upcoming songs" shows')
    m.play_pos = 0; tick(m)
    expect(not shown(m, 'qp_empty'), 'and goes when rows follow again')
    m.mode = O['MODE_REPEAT_ALL']; tick(m)
    expect(m.props.get((m.widgets['btn_repeat'], 'style:normal:icon')) == 'sg_repeat_on' and [s[2] for s in m.styled if s[0] == m.widgets['btn_repeat'] and s[1] == 'normal:bg_color'][-1] == O['QP_PILL_ON'],
           'a mode set elsewhere (Now Playing\'s own button, the Play settings) lights the button')
    m.mode = O['MODE_ORDER']; tick(m)
    new = [m.record(album='New', artist='New Artist', path=f'/mnt/mmc/n/{i}.flac', title=f'New {i}', name=f'n{i}.flac', rid=500 + i) for i in range(4)]
    m.play(new, 1)
    m.call(PSYMS['qp_on_bg'], count=900000000); tick(m)
    expect(text_of(m, 'qp_title') == NAMES[0], 'behind another page the queue is not read')
    m.call(PSYMS['qp_on_fg'], count=900000000)
    expect(text_of(m, 'qp_title') == 'New 1' and vh(m) == TOP + 2 * ROW + O['QP_BOTTOM'], 'back in front it reads the new queue (EVT_WINDOW_TO_FG)')
    m.screen(False); tick(m)
    expect(any(c[0] == 'timer_modify' and c[2] == 1000 for c in m.calls), 'a dark screen slows the timer to 1 s')
    m.screen(True); tick(m)
    expect(any(c[0] == 'timer_modify' and c[2] == O['QP_TICK_MS'] for c in m.calls), 'and a lit one restores it')
    destroy(m)
    removed = [c for c in m.calls if c[0] == 'timer_remove']
    expect(len(removed) >= 1, f'the destroy removes the page\'s timers ({removed})')
    expect(open_queue(m)[0] == 0, 'a fresh open after the destroy works (no state is left)')
    destroy(m)


def shuffle_tests(ctx):
    """9. Shuffle (patch/shuffle.c): the page has no placeholder, Up Next is always the queue's own order; the button reorders the queue after the playing track and a flag turned on elsewhere (the hook on mclSetPlayMode) shows at the next tick."""
    expect = ctx.expect
    SH, OR = O['MODE_SHUFFLE'], O['MODE_ORDER']
    titles = lambda m: [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in m.deques[m.word(PLAY_QUEUE)]]
    rows = lambda m: [t for (t, r), s in paint(m)[1] if s == 'label_row_title']

    # opened with Shuffle on (the flag file): the real rows, in the queue's order, and the lit button
    m = queue_machine(n=6, pos=1); m.top_main = m.window; m.fs[FLAG_FILE] = b'1\n'; open_queue(m)
    expect(vh(m) == TOP + 4 * ROW + O['QP_BOTTOM'] and not shown(m, 'qp_empty') and 'qp_shuf_img' not in m.widgets, 'opened with Shuffle on: Up Next shows the four songs after the playing one, no placeholder, "No upcoming songs" stays hidden')
    expect(rows(m) == NAMES[2:6] and text_of(m, 'qp_title') == NAMES[1], 'the rows are the queue as it is (the header keeps the playing track)')
    expect([s[2] for s in m.styled if s[0] == m.widgets['btn_shuffle'] and s[1] == 'normal:bg_color'][-1] == O['QP_PILL_ON'], 'and the Shuffle button is lit')
    expect(m.call(PSYMS['pod_play_mode'], count=100000) == SH and m.mode == OR, 'pod_play_mode (the display sites) answers Shuffle while stock\'s own mode stays List play')
    click(m, 'btn_shuffle')
    expect(not flag_on(m) and titles(m) == NAMES[:6] and rows(m) == NAMES[2:6], 'Shuffle off from the button with no order to restore: the queue and the rows stay')
    destroy(m)

    # the button turns Shuffle on: the songs after the playing one are shuffled in place, the page shows the new order
    for clock in (3, 77, 4099):
        m = queue_machine(n=6, pos=1); m.top_main = m.window; m.clock = clock; open_queue(m)
        before = titles(m)
        click(m, 'btn_shuffle')
        after = titles(m)
        expect(flag_on(m) and after[:2] == before[:2] and sorted(after[2:]) == sorted(before[2:]) and not [c for c in m.calls if c[0] == 'mclSetPlayMode'] and m.play_pos == 1,
               f'Shuffle on (clock {clock}): the playing song and the ones before it stay, the rest is a permutation, the position is unchanged ({after})')
        expect(rows(m) == after[2:6] and vh(m) == TOP + 4 * ROW + O['QP_BOTTOM'] and text_of(m, 'qp_title') == NAMES[1], f'Up Next shows the new order at once ({rows(m)})')
        if clock == 77: moved = after != before
        click(m, 'btn_shuffle')
        expect(not flag_on(m) and titles(m) == before and m.play_pos == 1 and rows(m) == before[2:6], 'Shuffle off: the original order is back and the same song is playing')
        destroy(m)
    expect(moved, 'the shuffle moved songs')

    # turned on elsewhere (Now Playing's button, Play settings: the hook on mclSetPlayMode): the next tick shows the new order, and the repeat button follows stock's mode
    m = queue_machine(n=6, pos=1); m.top_main = m.window; m.clock = 5; open_queue(m)
    scroll_to(m, 100)
    m.call(PSYMS['sh_set_mode'], a0=SH, count=900000000)
    expect(flag_on(m) and m.mode == OR, 'the hook turned the flag on and left stock in List play')
    tick(m)
    expect(rows(m) == titles(m)[2:6] and m.props.get((m.sv, 'yoffset')) == 0, 'the tick shows the shuffled order, from the top')
    m.call(PSYMS['sh_set_mode'], a0=OR, count=900000000)
    tick(m)
    expect(not flag_on(m) and rows(m) == NAMES[2:6], 'and the original one when it is turned off elsewhere')
    destroy(m)
    m = queue_machine(n=1, pos=0); m.top_main = m.window; m.fs[FLAG_FILE] = b'1\n'; open_queue(m)
    expect(shown(m, 'qp_empty') and vh(m) == WIN_H, 'one song with Shuffle on: "No upcoming songs"')
    destroy(m)


def clear_tests(ctx):
    """10. Clear (patch/queuepage.c qp_on_clear, patch/shuffle.c pod_clear_upnext): the button, the engine (the tracks after the play position go, the rest stays and plays on), the
    gapless preload, the Shuffle order, the refusals and the pins."""
    expect = ctx.expect
    PRE, PRE_NEXT, GAP = (pod.DATA[k][0] for k in ('MCL_PRELOAD', 'MCL_PRELOAD_NEXT', 'MCL_GAPLESS'))
    recs = lambda m: list(m.deques[m.word(PLAY_QUEUE)])
    strs = lambda m, rs: [m.word(r + O[f]) for r in rs for f in ('REC_TITLE', 'REC_ARTIST', 'REC_ALBUM', 'REC_PATH', 'REC_NAME')]
    titles = lambda m: [m.read_cstr(m.word(r + O['REC_TITLE'])) for r in recs(m)]
    rows = lambda m: [t for (t, r), s in paint(m)[1] if s == 'label_row_title']

    # the asset: a flat grey text button right of "Queue", hidden and insensitive until songs follow
    root = ui(); b = root.find('btn_qclear'); view = root.find('view_queue')
    expect(b is not None and b.type == 'button' and (b.x, b.y, b.w, b.h) == (O['QP_CLEAR_X'], O['QP_CLEAR_Y'], O['QP_CLEAR_W'], O['QP_CLEAR_H']) and b.get('visible') == 'false' and b.get('sensitive') == 'false',
           'btn_qclear: a 100 x 40 button at x 210, hidden and insensitive from the start')
    expect(b.get('style:normal:text_color') == '#9C9C9C' and b.get('style:pressed:text_color') == '#7A7A7A' and b.get('style:normal:font_size') == '17' and b.get('style:normal:text_align_h') == 'right'
           and b.get('style:normal:bg_color') == '#00000000' and b.get('style:pressed:bg_color') == '#00000000' and b.get('tr_text', 'Clear') == 'Clear', 'Clear: 17 px neutral grey #9C9C9C, #7A7A7A pressed, right aligned, no fill')
    expect(O['QP_CLEAR_X'] + O['QP_CLEAR_W'] == 310 and O['QP_CLEAR_Y'] + O['QP_CLEAR_H'] // 2 == O['QP_HEAD_Y'] + O['QP_HEAD_H'] // 2 and O['QP_CLEAR_Y'] >= O['QP_PILL_Y'] + O['SG_PILL_H']
           and O['QP_CLEAR_Y'] + O['QP_CLEAR_H'] <= TOP, 'it ends at x 310, is centred on the "Queue" line and touches neither the buttons above nor the rows below')
    names = [c.name for c in view.children]
    expect(names.index('btn_qclear') > names.index('qp_head'), f'it is above the line in z order ({names})')
    import pod_i18n
    expect(set(pod_i18n.TEXT['Clear']) == set(pod_i18n.LOCALES) and all(pod_i18n.TEXT['Clear'][lc] for lc in pod_i18n.LOCALES) and pod_i18n.TEXT['Clear']['en_US'] == 'Clear', '"Clear" is translated in all 13 languages')

    # mid-queue: 0..pos stay as they are (the same records and string pointers, bytes untouched, nothing freed or copied), only the tail records are destroyed (last first, by libcstl's deque_pop_back)
    m = opened(n=6, pos=2)
    q = m.word(PLAY_QUEUE); before = recs(m); kept, tail = before[:3], before[3:]
    owned, tail_owned = strs(m, kept), strs(m, tail)
    raw = lambda m, rs: [bytes(m.u.mem_read(r, O['REC_SIZE'])) for r in rs]
    kept_raw = raw(m, kept); m.calls.clear()
    expect(shown(m, 'btn_qclear') and rows(m) == NAMES[3:6], 'songs follow: Clear shows (visible and sensitive)')
    click(m, 'btn_qclear')
    expect(recs(m) == kept and m.word(PLAY_QUEUE) == q and strs(m, kept) == owned and raw(m, kept) == kept_raw and titles(m) == NAMES[:3] and m.play_pos == 2 and len(m.deques[q]) == 3 == m.play_pos + 1,
           f'Clear: the queue is the playing track and the ones before it ({titles(m)}): the same deque, the same records at the same addresses with the same bytes and string pointers, size = position + 1')
    pops = [c for c in m.calls if c[0] == 'pop_back']
    freed = [c[1] for c in m.calls if c[0] == 'free' and c[1]]   # (free(NULL) from the page's own reload is no free)
    expect([c[2] for c in pops] == tail[::-1] and all(c[1] == q for c in pops), f'only the tail records are popped, the last first ({len(pops)} pops)')
    expect(sorted(freed) == sorted(tail_owned) and not set(freed) & set(owned) and raw(m, tail) == [bytes(O['REC_SIZE'])] * 3,
           'the tail records\' strings are freed once each (the stSongInfo destructor) and the records cleared; no retained string is freed')
    expect(not [c for c in m.calls if c[0] in ('calloc', 'strdup', 'memcpy', 'memset', '_create_deque', 'deque_init', '_deque_push_back', 'deque_assign', 'deque_destroy', 'deque_clear', 'mclSetPlayPos', 'start_playqueue', 'mclStartPlayer')
                                               or c[0] == 'free' and c[1] in owned],
           'no allocation, no copy, no temporary deque, no assign; the player is not restarted or moved')
    names = m.names(); lk, ul = names.index('lock'), names.index('unlock')
    expect(names.count('lock') == names.count('unlock') == 1 and names[lk:ul].count('pop_back') == 3 == names.count('pop_back'),
           'the payload lock is taken once and covers the three pops')
    expect(shown(m, 'qp_empty') and not shown(m, 'btn_qclear') and vh(m) == WIN_H and rows(m) == [] and text_of(m, 'qp_title') == NAMES[2], 'the page: "No upcoming songs", Clear hidden and insensitive, the header keeps the track')
    expect(m.props.get((m.widgets['btn_qclear'], 'sensitive')) == 0 and m.props.get((m.widgets['btn_qclear'], 'visible')) == 0, 'hidden also means insensitive')
    m.calls.clear(); r = m.call(PSYMS['qp_on_clear'], count=900000000)
    expect(not [c for c in m.calls if c[0] in ('pop_back', 'lock')] and recs(m) == kept, 'a second tap (nothing follows) changes nothing')
    destroy(m)

    # the engine: 1 done, 0 nothing after the position, an unknown position; the queue is shortened to pos + 1 with the retained records unchanged
    for pos, want in ((0, 1), (4, 1), (5, 0), (-1, 0), (9, 0)):
        m = queue_machine(n=6, pos=pos); m.top_main = m.window; m.play_pos = pos
        before = recs(m); owned = strs(m, before[:pos + 1]) if pos >= 0 else []
        r = m.call(PSYMS['pod_clear_upnext'], count=900000000)
        r = r if r < 0x80000000 else r - 2 ** 32
        expect(r == want and len(recs(m)) == (pos + 1 if want else 6) and recs(m) == before[:pos + 1 if want else 6] and m.play_pos == pos, f'pod_clear_upnext at {pos}: {want}, {len(recs(m))} left, retained records in place')
        expect(not [c for c in m.calls if c[0] == 'free' and c[1] in owned] and len([c for c in m.calls if c[0] == 'pop_back']) == (5 - pos if want else 0), f'pod_clear_upnext at {pos}: {5 - pos if want else 0} pops, nothing retained freed')
    m = queue_machine(n=6, pos=5); m.top_main = m.window; open_queue(m)
    expect(not shown(m, 'btn_qclear') and shown(m, 'qp_empty'), 'the last track playing: Clear is hidden and insensitive')
    destroy(m)

    # the position and the size are read again under the lock: a player that moved on, or a queue that shrank, while the lock was waited for
    m = opened(n=6, pos=2); q = m.word(PLAY_QUEUE); before = recs(m)
    def moved(): m.play_pos = 3; m.on_lock = None
    m.on_lock = moved
    r = m.call(PSYMS['pod_clear_upnext'], count=900000000)
    expect(r == 1 and recs(m) == before[:4] and m.play_pos == 3, 'the position moved to 3 while the lock was waited for: the playing track (now 3) is kept, not the old one\'s successor')
    destroy(m)
    m = opened(n=6, pos=2); q = m.word(PLAY_QUEUE); before = recs(m)
    def shrank(): m.deques[q] = m.deques[q][:4]; m.on_lock = None
    m.on_lock = shrank; m.calls.clear()
    r = m.call(PSYMS['pod_clear_upnext'], count=900000000)
    expect(r == 1 and recs(m) == before[:3] and len([c for c in m.calls if c[0] == 'pop_back']) == 1, 'the queue shrank to 4 while the lock was waited for: one pop (the size is read under the lock, never popped below pos + 1)')
    destroy(m)
    m = opened(n=6, pos=2); q = m.word(PLAY_QUEUE); before = recs(m)
    def played_out(): m.play_pos = 5; m.on_lock = None
    m.on_lock = played_out; m.calls.clear()
    r = m.call(PSYMS['pod_clear_upnext'], count=900000000)
    expect(r == 0 and recs(m) == before and not [c for c in m.calls if c[0] == 'pop_back'], 'the last track became the playing one while the lock was waited for: nothing to remove, no pop')
    destroy(m)

    # a preload that is open names the old next song: closed with stock's setter before the first pop, the Gapless setting put back; the remembered target is dropped
    for gap in (0, 1):
        m = opened(n=6, pos=2); m.setword(PRE, 1); m.setword(PRE_NEXT, 3); m.u.mem_write(GAP, bytes((gap,)))
        click(m, 'btn_qclear')
        sets = [c for c in m.calls if c[0] == 'mclSetGaplessMode']
        first_pop = next(i for i, c in enumerate(m.calls) if c[0] == 'pop_back')
        expect(sets == [('mclSetGaplessMode', 0), ('mclSetGaplessMode', gap)] and ('closegapless',) in m.calls and m.word(PRE) == 0xffffffff and m.u.mem_read(GAP, 1)[0] == gap and m.word(PRE_NEXT) == 0xffffffff
               and max(i for i, c in enumerate(m.calls) if c[0] == 'mclSetGaplessMode') < first_pop,
               f'gapless setting {gap}: the open preload is closed (state -1) before the first pop, the setting is back, the target is forgotten ({sets})')
        destroy(m)
    m = opened(n=6, pos=2); m.setword(PRE, 0); m.setword(PRE_NEXT, 1)
    click(m, 'btn_qclear')
    expect(not [c for c in m.calls if c[0] == 'mclSetGaplessMode'] and m.word(PRE) == 0 and m.word(PRE_NEXT) == 1, 'no preload open: the setter is not touched, a target at or before the position stays')
    destroy(m)

    # Shuffle: the flag stays on, the saved order is dropped (the queue shrank, Shuffle off keeps what is left)
    m = queue_machine(n=6, pos=1); m.top_main = m.window; m.clock = 77; open_queue(m)
    click(m, 'btn_shuffle')
    expect(flag_on(m) and shown(m, 'btn_qclear'), 'Shuffle on, songs follow')
    kept = recs(m)[:2]
    click(m, 'btn_qclear')
    expect(flag_on(m) and recs(m) == kept and rows(m) == [], 'Clear with Shuffle on: the flag stays, the queue is the first two')
    click(m, 'btn_shuffle')
    expect(not flag_on(m) and recs(m) == kept and titles(m) == NAMES[:2] and not [c for c in m.calls if c[0] == 'mclSetPlayPos'], 'Shuffle off afterwards restores nothing (the order is dropped) and does not touch the queue')
    destroy(m)

    m = opened(n=6, pos=2); m.ptype = 2; before = recs(m)  # refusals: a stream
    click(m, 'btn_qclear')
    expect(recs(m) == before, 'a stream play type: the tap does nothing')
    m.setword(PLAY_QUEUE, m.new_deque(before)); tick(m)
    expect(not shown(m, 'btn_qclear'), 'and a page read while a stream plays hides Clear')
    destroy(m)

    # libcstl's deque_pop_back is found from deque_size's resolved GOT slot and checked word for word; anything else refuses Clear (the button hidden, the engine -1, nothing called)
    m = opened(n=6, pos=2); slot, base = m.got_deque_size, m.CSTL_BASE; destroy(m)
    def refused(m, why):
        before = recs(m); m.calls.clear()
        r = m.call(PSYMS['pod_clear_upnext'], count=900000000); ready = m.call(PSYMS['pod_clear_ready'], count=900000000)
        expect(r == 0xffffffff and ready == 0 and recs(m) == before and not [c for c in m.calls if c[0] in ('pop_back', 'free', 'mclSetGaplessMode')], f'{why}: Clear is refused (engine -1, not ready), the queue is untouched')
    m = opened(n=6, pos=2)
    expect(m.call(PSYMS['pod_clear_ready'], count=900000000) == 1 and shown(m, 'btn_qclear'), 'libcstl bound and as pinned: ready, Clear shows')
    destroy(m)
    m = queue_machine(n=6, pos=2); m.top_main = m.window; m.install_libcstl(bound=False); open_queue(m)
    expect(m.word(slot) == 0x743590 and not shown(m, 'btn_qclear'), 'the GOT slot still holds the stub inside demo: Clear is hidden')
    click(m, 'btn_qclear'); refused(m, 'an unbound slot')
    destroy(m)
    for why, patch in (('the slot points at another function of the library', lambda m: m.setword(slot, base + pod.CSTL_POP)),
                       ('the slot is null', lambda m: m.setword(slot, 0)), ('the slot is unaligned', lambda m: m.setword(slot, base + pod.CSTL_SIZE + 1)),
                       ('a word of deque_size differs', lambda m: m.setword(base + pod.CSTL_SIZE + 4 * 7, 0)), ('the first word of deque_pop_back differs', lambda m: m.setword(base + pod.CSTL_POP, 0)),
                       ('the last word of deque_pop_back differs (n = 2)', lambda m: m.setword(base + pod.CSTL_POP + 20, 0x24050002)),
                       ('another build of the library (pop_back moved)', lambda m: (m.setword(slot, base + pod.CSTL_SIZE + 0x100), m.u.mem_write(base + pod.CSTL_SIZE + 0x100, bytes(m.u.mem_read(base + pod.CSTL_SIZE, 32)))))):
        m = opened(n=6, pos=2); patch(m); refused(m, why); destroy(m)
    # the build pins: the library file and its symbols and words (tools/pod.py check_libcstl_bytes / check_libcstl)
    lib = open(os.path.join(WORK, 'rootfs', pod.LIBCSTL), 'rb').read()
    pod.check_libcstl_bytes(lib)
    h = open(os.path.join(BUILD, 'stock.h')).read()
    expect(pod.sha(lib) == pod.LIBCSTL_SHA and os.path.realpath(os.path.join(WORK, 'rootfs', pod.LIBCSTL_LINK)) == os.path.realpath(os.path.join(WORK, 'rootfs', pod.LIBCSTL)) and '#define STOCK_IMAGE_END 0xa11000u' in h,
           'the tree\'s libcstl is the pinned file, libcstl.so.2 links to it, and the payload was built with demo\'s image end 0xa11000 (check_libcstl)')
    for why, off in (('a deque_size word', pod.CSTL_SIZE + 8), ('a deque_pop_back word', pod.CSTL_POP + 12)):
        bad = bytearray(lib); bad[off] ^= 1
        try: pod.check_libcstl_bytes(bytes(bad)); ok = False
        except ValueError: ok = True
        expect(ok, f'build pin: {why} changed -> the build fails')
    bad = bytearray(lib); bad[0x40000] ^= 1
    expect(pod.sha(bytes(bad)) != pod.LIBCSTL_SHA, 'build pin: any other change to the file fails the SHA-256 check')

    # another path clears it (the engine called under an open page): the tick finds the shrunk queue (same pointer, other size) and reads it again
    m = opened(n=6, pos=2)
    m.call(PSYMS['pod_clear_upnext'], count=900000000)
    tick(m)
    expect(rows(m) == [] and shown(m, 'qp_empty') and not shown(m, 'btn_qclear') and vh(m) == WIN_H, 'the refresh tick reads the shrunk queue')
    destroy(m)

    # the DLNA renderer service (dmr_serverflag == 1) can read the queue on the UPnP threads: Clear is hidden and insensitive, and refused by the engine, while it runs
    DMR = pod.DATA['DMR_SERVERFLAG'][0]
    m = opened(n=6, pos=2); before = recs(m)
    expect(DMR == 0xa06020 and shown(m, 'btn_qclear') and m.word(DMR) == 0, 'the service flag is 0xa06020 (dmr_serverflag): off, Clear shows')
    m.setword(DMR, 1); tick(m)
    expect(not shown(m, 'btn_qclear') and m.props.get((m.widgets['btn_qclear'], 'sensitive')) == 0 and m.props.get((m.widgets['btn_qclear'], 'visible')) == 0 and rows(m) == NAMES[3:6],
           'the service starts under the open page: the tick hides Clear (visible and sensitive), the rows stay')
    m.calls.clear(); click(m, 'btn_qclear'); r = m.call(PSYMS['pod_clear_upnext'], count=900000000); ready = m.call(PSYMS['pod_clear_ready'], count=900000000)
    names = m.names()
    expect(r == 0xffffffff and ready == 0 and recs(m) == before and not [c for c in m.calls if c[0] in ('pop_back', 'free', 'mclSetGaplessMode')] and names.count('lock') == names.count('unlock'),
           'service running: the tap does nothing, the engine answers -1 and releases the lock, not ready, the queue is untouched')
    m.setword(DMR, 0); tick(m)
    expect(shown(m, 'btn_qclear'), 'the service stops: the tick shows Clear again')
    m.setword(DMR, 2); tick(m)
    expect(shown(m, 'btn_qclear'), 'any other value than 1 (stock tests == 1) is not running')
    destroy(m)
    m = queue_machine(n=6, pos=2); m.top_main = m.window; m.setword(DMR, 1); open_queue(m)
    expect(not shown(m, 'btn_qclear') and rows(m) == NAMES[3:6], 'a page opened while the service runs: no Clear')
    destroy(m)
    m = opened(n=6, pos=2); m.setword(DMR, 1); n0 = len(recs(m))
    r = m.call(PSYMS['pod_clear_upnext'], count=900000000); m.setword(DMR, 0)
    r2 = m.call(PSYMS['pod_clear_upnext'], count=900000000)
    expect(r == 0xffffffff and n0 == 6 and r2 == 1 and len(recs(m)) == 3, 'the engine alone: -1 with the service running, then 1 once it stopped (the lock was released)')
    destroy(m)
    import struct
    stock_demo = open(os.path.join(WORK, 'rootfs', pod.DEMO), 'rb').read()
    pw = lambda a: struct.unpack_from('<I', stock_demo, pod.fileoff(stock_demo, a))[0]
    dpins = {a: old for a, old, what in pod.SHUFFLE_PINS if 'dmr_serverflag' in what or 'dmrStartService' in what or 'dmrStopService' in what}
    expect(sorted(dpins) == [0x507a78, 0x507bf8, 0x507bfc, 0x507c00, 0x5084a0] and all(pw(a) == old for a, old in dpins.items()), 'the flag\'s reader, setter and clearer are pinned and are stock\'s words (a mismatch fails the build)')
    expect(pod.DATA['DMR_SERVERFLAG'][1] == 'dmr_serverflag', 'the flag is looked up by its stock symbol')

    # the pinned stock words the engine relies on
    pinned = {a for a, _, _ in pod.SHUFFLE_PINS}
    expect({0x5d28ac, 0x5d28cc, 0x5d28d0, 0x5d28dc, 0x5d28e0, 0x5d290c, 0x5d2914} <= pinned and pod.FUNCTIONS['mclSetGaplessMode'][2] == 0x5d28ac and (PRE, PRE_NEXT, GAP) == (0xa0abd0, 0xa0abcc, 0xa0ab89),
           'mclSetGaplessMode (prologue, the byte store, the preload test and close) and the three player words are pinned')


def server_tests(ctx):
    """5d. A server track (streamed or downloaded; its REC_ID is in the queue map) shows the source's cover file by that id, in the header and the rows: never the library's album of the same artist
    and album, never its address. A cover on its way keeps the placeholder and is looked for again on the tick; none stays the placeholder. A server queue is this page's (its play type is a list
    class, not a stream)."""
    expect = ctx.expect
    SC = '/mnt/mmc/.m1plus/subsonic/covers/%08x-168.jpg'
    STREAM = 'http://nd.example:4533/rest/stream.view?id=t%d&t=tok&s=salt'

    def server_queue(pos, plan):
        """A queue of 9 (Artist/Album k = row // 3, the library has covers for Album 0 and 1) whose rows in plan are server tracks: row -> (stream or downloaded, sba_rec_cover's answer, the file)."""
        m = queue_machine(n=9, pos=pos)
        for i, (kind, ans, path) in plan.items():
            rid = -(10 + i); r = m.songs[i]
            m.sbtrack[rid] = f't{i}'; m.setword(r + O['REC_ID'], rid & 0xffffffff)
            if kind == 'stream': m.setword(r + O['REC_PATH'], m.cstr(STREAM % i))
            m.sbcover[rid] = [ans, path]
            if ans == 1: m.present.add(path); m.images['file://' + path] = (168, 168, COVER_PIX[i % 2])
        m.ptype = O['CLASS_ARTISTS']
        m.top_main = m.window
        r, calls = open_queue(m)
        assert r == 0 and ('window_open', 'm1plus_queue') in calls, f'the server queue did not open ({r})'
        return m
    A, B, P = SC % 0x1000, SC % 0x1001, SC % 0x2005
    m = server_queue(0, {1: ('stream', 1, B), 2: ('stream', 1, A), 3: ('down', 1, B), 4: ('stream', -1, SC % 0x2004), 5: ('stream', 0, P)})
    load_all(m)
    paint(m)
    got = set(covers_of(m))
    expect(got == {'file://' + A, 'file://' + B, 'file://' + m.cover_paths[0]},
           f'the server rows decode the source\'s files (streamed or downloaded); the library album cache files of their albums (Album 1 is all server rows) are not read; the local playing track\'s header keeps its album ({sorted(got)})')
    expect(not any('stream.view' in u or 'http' in u for u in m.loads) and m.sbcover[-15][0] == 0 and 'file://' + P not in got, 'no address is ever opened; the cover on its way is not decoded yet')
    blits, texts, fills = paint(m)
    expect(len([b for b in blits if b[2][2] == 52]) >= 3, 'every row in view has a cover blit (the file\'s or the placeholder)')
    # it lands: the tick looks again and the next loader pass decodes it
    m.sbcover[-15] = [1, P]; m.present.add(P); m.images['file://' + P] = (168, 168, COVER_PIX[1])
    scroll_to(m, 0); tick(m); finish_loading(m)
    scroll_to(m, 4 * ROW); paint(m); tick(m); finish_loading(m)
    expect('file://' + P in m.loads, f'the cover that was on its way is decoded once the file is there ({sorted(set(covers_of(m)))})')
    destroy(m)
    # the header: the playing server track's file, never the album that shares its artist and album
    m = server_queue(1, {1: ('stream', 1, B), 2: ('stream', 1, A)})
    paint(m); finish_loading(m)
    expect(('file://' + B) in m.loads and ('file://' + m.cover_paths[0]) not in m.loads, f'the header shows the playing server track\'s file, not Album 0\'s cache file ({sorted(set(covers_of(m)))})')
    destroy(m)
    none = {i: ('stream', -1, SC % (0x3000 + i)) for i in range(6, 9)}
    m = server_queue(5, {5: ('stream', 0, P), **none})
    paint(m); finish_loading(m)
    expect(('file://' + P) not in m.loads and m.__dict__.get('queries') in (None, []) and len([b for b in paint(m)[0] if tuple(b[2][2:]) == (64, 64)]) == 1, 'a header cover on its way: the placeholder, no album lookup')
    m.sbcover[-15] = [1, P]; m.present.add(P); m.images['file://' + P] = (168, 168, COVER_PIX[1])
    tick(m); finish_loading(m); paint(m)
    expect(('file://' + P) in m.loads, 'and the tick looks again: the file is decoded into the header when it lands')
    destroy(m)
    # a server track the source has no picture for: the placeholder, not the library album of that name
    m = server_queue(4, {i: ('stream', -1, SC % (0x3000 + i)) for i in range(4, 9)})
    paint(m); finish_loading(m)
    expect(not [u for u in m.loads if u.startswith('file://')] and not m.__dict__.get('queries'), f'no source picture: the placeholder, and no cover map query (the library\'s Album 1 cache file is not taken: {m.loads})')
    destroy(m)


SECTIONS = [asset_tests, open_tests, header_tests, rows_tests, loader_tests, episode_tests, collab_tests, server_tests, cmap_tests, scroll_tests, play_tests, mode_tests, tick_tests, shuffle_tests, clear_tests]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)

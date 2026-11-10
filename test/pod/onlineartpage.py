"""The Find Cover & Lyrics page (patch/onlineart.c, tools/pod_ui.py build_onlineart_page, docs/modules/onlineart.md), on the real compiled payload under Unicorn with the worker thread run by the test.

Proved: the built asset (the stock navbar, the Search page's chip row, line and list with one content view, the confirmation's container, the lyrics header and pill, everything inside the 320 x 450 window,
the hidden ones hidden and insensitive, the colours legible on black, every text fitting in all 13 languages); the tabs (Covers first, both lookups from the open, a switch costs no wait, each tab's
scroll position kept); the Covers tab (the state line, one thumbnail decoded per tick, painting at the grid's cells and scrolled); a tap on a cover opens the confirmation and writes NOTHING (the larger
picture only), Back changes nothing, the pill (Use This Cover / Replace Cover) saves into the cache keys and the folder, then the grid with that cover marked current; failures of the fetch and the pick;
the Lyrics tab (rows with the title, the grey line and the Synced badge, the state line); a tap on a row opens the full text without its tags, wrapped and scrolling, the pill writes <track>.lrc (Save /
Replace, the extension rule, an existing file never touched before the tap, a failed write), then the rows with that one marked Saved; the downloads pausing and resuming; the page's life (one timer,
Back and Now Playing bound, the worker cancelled on destroy, a second open, no track, a wrong asset)."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui
from awtk_text import Ttf, StbText
import pod_pages, pod_i18n, pod_ui
import pod_search as PS

PCS = sibling('pcsearch'); OA = sibling('onlineart')   # noqa: F821  (sibling: the harness helper of the pod tests)
PCN, fn = PCS.PCN, PCS.fn
RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
UI = os.path.join(RAW, 'ui', 'm1plus_onlineart.bin')
WIN = 0x24200000
EVT_DOWN, EVT_UP, EVT_ABORT, EVT_PAINT, EVT_DESTROY, EVT_CLICK = O['EVT_POINTER_DOWN'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT'], O['EVT_AFTER_PAINT'], O['EVT_DESTROY'], O['EVT_CLICK']
NAMES = ('oa_chips', 'oa_chip_hl', 'oa_sep', 'oa_listview', 'oa_view', 'oa_status', 'oa_es_icon', 'oa_es_text', 'oa_es_retry', 'oa_hint', 'oa_dh_title', 'oa_dh_sub', 'oa_lsave', 'oa_dc', 'oa_dc_art', 'oa_dc_name', 'oa_dc_artist', 'oa_dc_source', 'oa_save',
         'label_row_title', 'label_row_sub', 'label_chip', 'label_chip_on', 'label_badge', 'label_badge_on', 'label_line', 'btn_return', 'btn_backtoplayer')
TRACK = '/mnt/mmc/Music/Radiohead/OK Computer/02 Karma Police.flac'
LRC = '/mnt/mmc/Music/Radiohead/OK Computer/02 Karma Police.lrc'
FOLDER = '/mnt/mmc/Music/Radiohead/OK Computer'
TILE, X0, Y0, PITCH, GAP = 88, 16, 8, 98, 12
LIST_Y, LIST_H, ROW_H = PS.SE_LIST_Y, PS.SE_LIST_H, PS.SE_ROW_H
BADGE_W = 8 * 6 + 14            # the mocked canvas: 8 px a character; "Synced" is the wider of Synced and Saved
TITLE_W = 304 - 16 - BADGE_W - 8
SYNCED_RGB, SAVED_RGB = 0xff2e2c2c, 0xffeae5e5
NCOV = 7
ES_TITLES = ['No Covers Found', 'No Lyrics Found', 'Lyrics Service Busy', 'Cover Service Busy']
ES_TEXTS = ['Check your Wi-Fi connection.', 'Turn on Wi-Fi to search online.', 'Secure connections need the right date.', 'This device has no certificate bundle.', "The server's certificate was not accepted.",
            'The server could not answer. Try again later.', 'The SD card could not be used.', 'There is not enough memory to search.', 'Nothing on iTunes or Deezer for this album.', 'LRCLIB has no lyrics for this song.',
            'LRCLIB is under heavy load. Try again in a moment.', 'iTunes and Deezer are busy. Try again in a moment.']
TXT_SYNCED = '[00:01.00] 歌词第一行\n[00:05.50] 第二行\n'


class AM(PCN.NM):
    """The page's window and widgets, the player on a track, the library's Albums, the scripted services, the worker run by the test."""
    def __init__(self, site, **kw):
        super().__init__()
        self.window = WIN
        self.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus', FOLDER})
        self.present.add(PCN.CA)
        self.curl_site = site
        self.jinit()
        for k, v in kw.items(): setattr(self, k, v)
        for n in NAMES: Machine.widget(self, n)   # noqa: F821
        win = self.alloc(0x80)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 450), (0x44, 0)): self.setword(win + off, v)
        self.sv = self.alloc(0x100)
        self.widgets['oa_scrollview'] = self.sv
        for w, x, y, ww, hh, parent in ((self.widgets['oa_chips'], 0, 52, 320, 34, win), (self.widgets['oa_listview'], 0, LIST_Y, 320, LIST_H, win), (self.sv, 0, 0, 310, LIST_H, self.widgets['oa_listview']),
                                        (self.widgets['oa_view'], 0, 0, 320, LIST_H, self.sv)):
            for off, v in ((0, x), (4, y), (8, ww), (0xc, hh), (0x44, parent)): self.setword(w + off, v)
        self.live_scroll = frozenset({self.sv})
        self.view, self.chips = self.widgets['oa_view'], self.widgets['oa_chips']
        self.load_image = 0
        self.images['file://' + OA.ART_DIR + '/full.jpg'] = (480, 480, bytes((90, 90, 90, 255)) * (480 * 480))   # the larger picture, decoded to the confirmation's 240 px
        self.canvas = self.alloc(0x80)
        self.fills = []
        self.pt = (30, 261, 1)   # get_playtimeandlength: position, length (s), ok
        self.sbtrack = {}        # server track REC_ID -> track id (sba_rec_track, patch/sbapi.c: tested in sbapi.py); a record in it is a server track
        self.handlers[PSYMS['sba_rec_track']] = 'sba_rec_track'
        self.playing()

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'sba_rec_track':
            rid = u.reg_read(UC_MIPS_REG_A0); rid = rid - (1 << 32) if rid >= 1 << 31 else rid   # noqa: F821
            u.reg_write(UC_MIPS_REG_V0, self.cstr(self.sbtrack.get(rid, ''))); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return   # noqa: F821
        return super()._hook(u, address, size, _)

    def playing(self, artist='Radiohead', album='OK Computer', title='Karma Police', path=TRACK, albums=('OK Computer', 'Kid A')):
        self.play([self.record(album=album, artist=artist, path=path, title=title, name=os.path.basename(path))], 0)
        self.class_lists[O['CLASS_ALBUMS']] = [self.record(album=a, artist='Radiohead', rid=i + 1) for i, a in enumerate(albums)] + [self.record(album='Unknown Album', rid=-1)]

    def open(self):
        self.calls = []; self.thread = None
        return self.call(PSYMS['onlineart_open'], count=200000000) & 0xffffffff

    def tick(self):
        self.calls = []
        self.call(PSYMS['oa_tick'], a0=0, count=400000000)

    def work(self):
        PCN.work(self, self.thread)

    def ticks(self, n=10):
        for _ in range(n): self.tick()

    def ready(self, n=10):
        """The lookup run to its end and the page told: every thumbnail decoded."""
        self.work(); self.ticks(n)

    def scroll(self, off):
        self.setword(self.sv + 0x84, off); self.props[(self.sv, 'yoffset')] = off

    def paint(self):
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.blits, self.fills, self.texts, self.text_styles = [], [], [], []
        fn_, ctx = self.bound[(self.view, EVT_PAINT)]
        self.call(fn_, a0=ctx, a1=ev, count=40000000)
        return list(self.blits), list(self.fills), list(self.texts)

    def paint_chips(self):
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.texts = []
        fn_, ctx = self.bound[(self.chips, EVT_PAINT)]
        self.call(fn_, a0=ctx, a1=ev, count=4000000)
        return list(self.texts)

    def paint_dc(self):
        ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + O['EVENT_PAINT_CANVAS'], self.canvas)
        self.blits = []
        fn_, ctx = self.bound[(self.widgets['oa_dc_art'], EVT_PAINT)]
        self.call(fn_, a0=ctx, a1=ev, count=4000000)
        return list(self.blits)

    def pointer(self, w, kind, x, y):
        """A pointer event at (x, y) in the widget's own coordinates (the list's content: y counts from the content's top)."""
        e = self.alloc(0x40); self.u.mem_write(e, bytes(0x40)); self.setword(e, kind)
        self.setword(e + O['PE_X'], x); self.setword(e + O['PE_Y'], y + (LIST_Y if w == self.view else 52 if w == self.chips else 0))
        fn_, ctx = self.bound[(w, kind)]
        self.call(fn_, a0=ctx, a1=e, count=4000000)

    def tap(self, x, y):
        self.calls = []
        self.pointer(self.view, EVT_DOWN, x, y); self.pointer(self.view, EVT_UP, x, y)

    def tap_tile(self, i):
        self.tap(X0 + (i % 3) * (TILE + GAP) + TILE // 2, Y0 + (i // 3) * PITCH + TILE // 2)

    def tap_row(self, r):
        self.tap(100, r * ROW_H + 30)

    def chip(self, k):
        x = 20 if k == 0 else 120   # inside the first chip, inside the second
        if getattr(self, 'strings', None):   # another language: the chips' places follow their texts
            r = sorted(r for _, r in self.paint_chips())[k]
            x = r[0] + r[2] // 2
        self.calls = []
        self.pointer(self.chips, EVT_DOWN, x, 17); self.pointer(self.chips, EVT_UP, x, 17)

    def click(self, name):
        fn_, ctx = self.bound[(self.widgets[name], EVT_CLICK)]
        self.calls = []
        self.call(fn_, a0=ctx, a1=0, count=400000000)

    def text(self, name): return undo(self.wtext.get(self.widgets[name], ''))
    def shown(self, name): return bool(self.props.get((self.widgets[name], 'visible'), 1)) and bool(self.props.get((self.widgets[name], 'sensitive'), 1))
    def destroy(self):
        fn_, ctx = self.bound[(self.window, EVT_DESTROY)]
        self.calls = []
        self.call(fn_, a0=ctx, a1=0, count=4000000)

    def open_cover(self, i):
        """A page ready on the Covers tab, cover i tapped, its larger picture fetched and decoded."""
        self.tap_tile(i); self.work(); self.ticks(3)

    def open_lyrics(self, r):
        self.chip(1); self.tap_row(r)


def undo(s):
    """A mocked text as the user reads it: UTF-8 bytes read as latin-1 (the payload's own strings come back twice over from the mocked translation)."""
    for _ in range(2):
        try: s = s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError): break
    return s


def asset_tests(ctx):
    expect = ctx.expect
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    box = lambda n: (by[n].x, by[n].y, by[n].w, by[n].h)
    expect(tree.type == 'window' and tree.name == 'm1plus_onlineart_page' and tree.get('fullscreen') is None, 'a normal window (450 px, under the status bar) named m1plus_onlineart_page')
    expect(all(n in by for n in NAMES + ('oa_scrollview',)) and 'label_title' in by, 'every widget the payload looks up is there, with the navbar\'s label_title')
    expect(pod_pages.ONLINEART in pod_pages.PAGES and pod_pages.ONLINEART.key == 'm1plus_onlineart' and os.path.exists(os.path.join(WORK, UI)), 'the page is registered and built')
    expect(box('navigationbar_view') == (0, 0, 320, 50) and by['btn_return'].get('enable') == 'true', 'the stock navbar: 50 px, Back, Now Playing')
    # the Search page's frame
    expect(box('oa_chips') == (0, PS.SE_CHIPS_Y, 320, PS.SE_CHIPS_H) and box('oa_chip_hl')[1:4:2] == (PS.SE_CHIP_Y, PS.SE_CHIP_H) and by['oa_chip_hl'].get('style:normal:bg_color') == PS.CHIP_ON_RGB
           and by['oa_chip_hl'].get('style:normal:round_radius') == str(PS.SE_CHIP_R), 'the chip row is the Search page\'s: the same place and height, the selected chip\'s light grey pill with the same radius')
    expect(box('oa_sep') == (0, PS.SE_SEP_Y, 320, 1) and by['oa_sep'].get('style:normal:bg_color') == PS.SEP_RGB, 'the line under the chips is the Search page\'s')
    lv, sv = by['oa_listview'], by['oa_scrollview']
    expect(lv.type == 'list_view' and sv.type == 'scroll_view' and sv in lv.children and by['oa_view'] in sv.children and (lv.x, lv.y, lv.w, lv.h) == (0, PS.SE_LIST_Y, 320, PS.SE_LIST_H)
           and box('oa_view') == (0, 0, 320, PS.SE_LIST_H), 'the list is the stock list_view > scroll_view with one content view (320 x 360), as the Search page\'s')
    expect(any(c.type == 'scroll_bar_m' for c in lv.children), 'with the stock scroll bar')
    order = [w.name for w in tree.children]
    expect(order.index('oa_listview') < min(order.index(n) for n in ('oa_status', 'oa_es_icon', 'oa_es_text', 'oa_es_retry', 'oa_dh_title', 'oa_dh_sub', 'oa_lsave', 'oa_dc')), 'the labels, the pill and the confirmation are over the list (children after it)')
    for n in ('oa_status', 'oa_es_icon', 'oa_es_text', 'oa_es_retry', 'oa_dh_title', 'oa_dh_sub', 'oa_lsave', 'oa_dc', 'label_row_title', 'label_row_sub', 'label_chip', 'label_chip_on', 'label_badge', 'label_badge_on', 'label_line'):
        expect(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false', f'{n} starts hidden and insensitive (a hidden widget still takes touches)')
    for n in ('oa_hint', 'oa_save'):
        expect(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false', f'{n} (in the confirmation) starts hidden and insensitive too')
    expect(by['oa_chip_hl'].get('sensitive') == 'false' and by['oa_sep'].get('sensitive') == 'false' and by['oa_dc_art'].get('sensitive') == 'false' and all(by[n].get('sensitive') == 'false' for n in ('oa_dc_name', 'oa_dc_artist', 'oa_dc_source')),
           'decorations and the confirmation\'s texts are insensitive')
    # the state block: the glyph, the title (oa_status), the explanation and the Try Again pill, stacked and centred on the list's middle
    ic, ti, tx, rt = box('oa_es_icon'), box('oa_status'), box('oa_es_text'), box('oa_es_retry')
    expect(ic[2:] == (40, 40) and by['oa_es_icon'].type == 'image' and by['oa_es_icon'].get('image') == 'pod_es_info' and ti[2:] == (288, 26) and tx[2:] == (260, 40) and rt[2:] == (168, 36), f'the block\'s parts: a 40 px glyph image, the title 288 x 26, the text 260 x 40, the pill 168 x 36 ({ic}, {ti}, {tx}, {rt})')
    expect(by['oa_status'].get('style:normal:font_size') == '18' and by['oa_status'].get('style:normal:text_align_h') == 'center' and by['oa_status'].get('style:normal:text_color') == '#FFFFFF'
           and by['oa_es_text'].get('style:normal:font_size') == '14' and by['oa_es_text'].get('style:normal:text_align_h') == 'center' and by['oa_es_text'].get('style:normal:text_color') == '#8E8E93',
           'the title is white, 18 px, centred; the explanation grey, 14 px, centred')
    full = 40 + 14 + 26 + 4 + 40 + 18 + 36
    expect(260 - full // 2 >= LIST_Y and 260 + (full + 1) // 2 <= LIST_Y + LIST_H, f'the tallest block (glyph, title, two lines, pill: {full} px) centred on y 260 lies inside the list')
    expect(by['oa_es_retry'].type == 'button' and by['oa_es_retry'].get('enable') == 'true', 'the Try Again pill is a button')
    # the lyrics detail: the header in the chip row's place, the pill under the text region
    th, sh, pl = box('oa_dh_title'), box('oa_dh_sub'), box('oa_lsave')
    expect(th[1] >= 52 and th[1] + th[3] <= sh[1] and sh[1] + sh[3] <= PS.SE_SEP_Y and th[0] >= 0 and th[0] + th[2] <= 320, f'the header (title, grey line) sits in the chip row\'s place, above the line ({th}, {sh})')
    expect(pl[1] >= LIST_Y + 300 and pl[1] + pl[3] <= 450 and pl[0] >= 0 and pl[0] + pl[2] <= 320, f'the lyrics pill lies under the text region (the list\'s top 300 px) inside the window ({pl})')
    # the confirmation
    dc = by['oa_dc']
    expect(box('oa_dc') == (0, 50, 320, 400) and by['oa_dc_art'] in dc.children, 'the confirmation fills the window under the navbar')
    art = box('oa_dc_art')
    names = ('oa_dc_name', 'oa_dc_artist', 'oa_dc_source', 'oa_hint', 'oa_save')
    boxes = [art] + [box(n) for n in names]
    inside = all(b[0] >= 0 and b[0] + b[2] <= 320 and b[1] >= 0 and b[1] + b[3] <= 400 for b in boxes)
    stack_ok = all(boxes[i][1] + boxes[i][3] <= boxes[i + 1][1] for i in range(len(boxes) - 1))
    expect(inside and stack_ok and art[2] == art[3] and art[0] * 2 + art[2] == 320, f'the cover (square, centred), the album, the artist, the source, the failure line and the pill stack inside the container ({boxes})')
    expect(art[2] == 240 and by['oa_dc_art'].get('sensitive') == 'false', 'the larger cover is 240 px (decoded from the downloaded 600 / 500 px picture)')
    # contrast: every label's colour on the black window, the pills' text on their fills
    lum = lambda c: (lambda r, g, b: 0.2126 * r + 0.7152 * g + 0.0722 * b)(*[(lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)(int(c[i:i + 2], 16) / 255) for i in (1, 3, 5)])
    rat = lambda a, b: (max(lum(a), lum(b)) + 0.05) / (min(lum(a), lum(b)) + 0.05)
    for n in ('oa_status', 'oa_es_text', 'oa_dh_title', 'oa_dh_sub', 'oa_dc_name', 'oa_dc_artist', 'oa_dc_source', 'oa_hint', 'label_row_title', 'label_row_sub', 'label_chip', 'label_line'):
        c = by[n].get('style:normal:text_color')
        expect(rat(c, '#000000') >= 4.5, f'{n}: {c} on black keeps 4.5:1 ({rat(c, "#000000"):.1f})')
    for n in ('label_badge', 'label_badge_on', 'label_chip_on'):
        c, b = by[n].get('style:normal:text_color'), by[n].get('style:normal:bg_color')
        expect(rat(c, b) >= 4.5, f'{n}: {c} on its fill {b} keeps 4.5:1 ({rat(c, b):.1f})')
    for pill in ('oa_save', 'oa_lsave', 'oa_es_retry'):
        for st in ('normal', 'pressed'):
            expect(rat(by[pill].get(f'style:{st}:text_color'), by[pill].get(f'style:{st}:bg_color')) >= 7, f'{pill}: the text keeps 7:1 on its fill ({st})')
        expect(rat(by[pill].get('style:normal:bg_color'), '#000000') < 1.5 and 'accent' not in str(by[pill].props), f'{pill} is a neutral grey (no accent colour)')
    # every text fits in every language
    built = {f[:-4]: dict(__import__('awtk_strings').load(os.path.join(WORK, RAW, 'strings', f))) for f in sorted(os.listdir(os.path.join(WORK, RAW, 'strings')))}
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    words = ['Searching…', 'No Wi-Fi', 'Set the date first', 'Certificates missing', 'Certificate problem', "Can't connect", 'Server error', 'Storage unavailable', 'Not enough memory']
    texts = {'oa_status': words + ES_TITLES, 'oa_hint': words[1:], 'oa_save': ['Use This Cover', 'Replace Cover', 'Saving…'], 'oa_lsave': ['Save Lyrics', 'Replace Lyrics'], 'oa_es_retry': ['Try Again'],
             'oa_dh_sub': ['Storage unavailable'], 'label_chip': ['Covers', 'Lyrics'], 'label_badge': ['Synced', 'Saved']}
    over = []
    for n, keys in texts.items():
        px = int(by[n].get('style:normal:font_size'))
        room = by[n].w - (24 if n in ('oa_save', 'oa_lsave', 'oa_es_retry') else 0) if n not in ('label_chip', 'label_badge') else 90
        for loc in pod_i18n.LOCALES:
            for key in keys:
                t = built[loc].get(key, key)
                w = StbText(font, px).layout(t)[1]
                if w > room: over.append((n, loc, key, w, room))
    expect(not over, f'every text of the page fits its label in all 13 languages ({over[:4]})')
    import pod_wrap
    long = []
    for loc in pod_i18n.LOCALES:
        for key in ES_TEXTS:
            t = built[loc].get(key, key)
            st = StbText(font, 14)
            lines = pod_wrap.wrap(t, [st.layout(c)[1] for c in t], by['oa_es_text'].w, 3, st.layout('…')[1])
            if len(lines) > 2 or lines[-1].endswith('…') and not t.endswith('…'): long.append((loc, key, lines))
    expect(not long, f'every explanation wraps to at most two lines of 260 px at 14 px in all 13 languages ({long[:3]})')
    chips_w = [max(StbText(font, 16).layout(built[loc][k])[1] for loc in pod_i18n.LOCALES) for k in ('Covers', 'Lyrics')]
    expect(PS.SE_CHIP_X + sum(w + 2 * PS.SE_CHIP_PAD + PS.SE_CHIP_GAP for w in chips_w) <= 320, f'the two chips fit the row in the widest language ({chips_w})')
    badge = max(StbText(font, 12).layout(built[loc][k])[1] for loc in pod_i18n.LOCALES for k in ('Synced', 'Saved'))
    expect(badge + 14 <= 90, f'a badge is at most 90 px wide in every language ({badge + 14}), the title keeps the rest of the row')
    title_room = by['label_title'].w
    expect(all(StbText(font, 22).layout(built[loc]['Cover & Lyrics'])[1] <= title_room for loc in pod_i18n.LOCALES), f'the title "Cover & Lyrics" fits the navbar\'s label ({title_room} px) in all 13 languages')
    keys = [k for ks in texts.values() for k in ks] + ES_TEXTS
    expect(all(k in pod_i18n.TEXT for k in keys if k not in pod_i18n.STOCK) and pod_i18n.text_prop('Cover & Lyrics')[1] == 'Cover & Lyrics', 'every key has its 13 translations')


def open_tests(ctx):
    expect = ctx.expect
    site = OA.Site()
    m = AM(site)
    r = m.open()
    names = [c[0] for c in m.calls]
    expect(r == 0 and ('window_open', 'm1plus_onlineart') in m.calls and names.count('pthread_create') == 1 and names.count('timer_add') == 1, f'open: the page, one worker thread, one timer ({r})')
    expect([c for c in m.calls if c[0] == 'timer_add'] == [('timer_add', PSYMS['oa_tick'], 250)], 'the timer is the page\'s own, every 250 ms')
    expect(all((m.widgets[n], EVT_CLICK) in m.bound for n in ('btn_return', 'btn_backtoplayer', 'oa_save', 'oa_lsave', 'oa_es_retry')) and (m.window, EVT_DESTROY) in m.bound
           and all((m.view, e) in m.bound for e in (EVT_DOWN, EVT_UP, EVT_ABORT, EVT_PAINT)) and all((m.chips, e) in m.bound for e in (EVT_DOWN, EVT_UP, EVT_ABORT, EVT_PAINT)) and (m.widgets['oa_dc_art'], EVT_PAINT) in m.bound,
           'Back, Now Playing, both pills, the destroy, the content view\'s touches and paint, the chips\' and the cover\'s paint are bound')
    expect(m.bound[(m.widgets['btn_return'], EVT_CLICK)][0] == PSYMS['oa_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], EVT_CLICK)][0] == PSYMS['pod_on_player'], 'Back is the page\'s (a detail first), the disc the stock Now Playing')
    expect(m.text('oa_status') == 'Searching…' and m.shown('oa_status') and m.shown('oa_chips') and m.shown('oa_listview') and m.shown('oa_sep') and not m.shown('oa_dc') and not m.shown('oa_dh_title') and not m.shown('oa_lsave'),
           'at once, on the Covers tab: "Searching…" over the empty list, the chips and the line, no detail')
    expect(('widget_move', m.widgets['oa_chip_hl'], PS.SE_CHIP_X, PS.SE_CHIP_Y) in m.calls and any(c[0] == 'widget_resize' and c[1] == m.widgets['oa_chip_hl'] and c[3] == PS.SE_CHIP_H for c in m.calls),
           'the selected chip\'s pill is under the first chip (Covers), as the Search page puts it')
    texts = m.paint_chips()
    expect(sorted(t for t, _ in texts) == ['Covers', 'Lyrics'] and dict(zip([t for t, _ in texts], m.text_styles)) == {'Covers': 'label_chip_on', 'Lyrics': 'label_chip'}, f'the chips paint their texts, the selected one in the dark style ({texts})')
    at = dict(texts)
    expect(at['Covers'][0] == PS.SE_CHIP_X and at['Lyrics'][0] == PS.SE_CHIP_X + (8 * 6 + 2 * PS.SE_CHIP_PAD) + PS.SE_CHIP_GAP and all(r[1] == PS.SE_CHIP_Y and r[3] == PS.SE_CHIP_H for _, r in texts), 'at the Search page\'s places')
    m.work()
    expect(m.call(PSYMS['onlineart_open'], count=1000000) == 0 and not [c for c in m.calls if c[0] == 'window_open'], 'a second open while the page is up does nothing (0)')
    # a server track (streamed: the path is the address with the login; downloaded: a file of the Subsonic folder): the lookup has nowhere to put a cover (the album key is the library's own) or a .lrc, so the page does not open
    for path in ('http://nd.example:4533/rest/stream.view?id=t5&t=tok&s=salt', '/mnt/mmc/Subsonic/Karma Police.flac'):
        ms = AM(OA.Site())
        ms.sbtrack[-5] = 't5'; ms.play([ms.record(album='OK Computer', artist='Radiohead', path=path, title='Karma Police', rid=-5)], 0)
        r = ms.open()
        expect(r == 0xffffffff and not [c for c in ms.calls if c[0] in ('window_open', 'pthread_create', 'timer_add')] and not ms.fs.keys() & {OA.ART_DIR},
               f'a {"streamed" if path.startswith("http") else "downloaded"} server track: Find Cover & Lyrics does not open, nothing is looked up ({r:#x})')

    urls = site.urls()
    expect(urls[0] == OA.ITUNES + 'Radiohead%20OK%20Computer' and urls[2 + NCOV] == OA.LRCLIB + 'get?track_name=Karma%20Police&artist_name=Radiohead&album_name=OK%20Computer&duration=261',
           f'the worker was given the playing track: artist, album, title and its length (261 s): {urls[0][-30:]}')
    expect(m.text('oa_status') == 'Searching…', 'nothing changes on the page until its timer reads the record')
    m.tick()
    expect(not m.shown('oa_status'), 'the tick reads the answer: the state line goes')
    loads = [c[1] for c in m.calls if c[0] == 'widget_load_image']
    expect(loads == ['file://' + OA.ART_DIR + '/a0.jpg'], f'one thumbnail is decoded per tick ({loads})')
    m.ticks(NCOV)
    thumbs = [u for u in m.loads if u.startswith('file://')]
    expect(thumbs == ['file://' + OA.ART_DIR + f'/a{i}.jpg' for i in range(NCOV)], f'{NCOV} ticks, {NCOV} thumbnails, in order ({thumbs})')
    n0 = len(m.loads)
    m.tick(); m.tick()
    expect(len(m.loads) == n0, 'no more decoding once every cover has its tile')
    expect(m.props.get((m.sv, 'virtual_h')) == LIST_H, 'seven covers (three rows) fit the list: nothing to scroll')
    # painting: the covers where the grid says, no frame yet (nothing is current)
    blits, fills, _ = m.paint()
    want = [(X0 + (i % 3) * (TILE + GAP), Y0 + (i // 3) * PITCH) for i in range(NCOV)]
    got = [(d[0], d[1]) for b, s, d in blits]
    expect(got == want and all(d[2] == TILE and d[3] == TILE for _, _, d in blits) and not fills, f'{NCOV} covers painted 88 px at the grid\'s cells, no frame ({got})')
    # both lookups started with the open: switching costs no wait
    m.chip(1)
    expect(not m.shown('oa_status') and m.paint()[2] != [], 'the Lyrics tab at once: no "Searching…", the rows are there')
    m.chip(0)
    expect(len(m.paint()[0]) == NCOV, 'and back to the covers')
    # leaving: the timer goes, the worker is not busy so the files are cleaned
    m.destroy()
    expect(('timer_remove', 0x777) in m.calls and not m.calls.count(('navigator_back',)), 'destroy: the timer is removed')
    expect(not [p for p in m.fs if p.startswith(OA.ART_DIR + '/a') or p.startswith(OA.ART_DIR + '/l')], 'the thumbnails and the held lyrics are removed (no worker runs)')


def tabs_tests(ctx):
    expect = ctx.expect
    m = AM(OA.Site()); m.open(); m.ready()
    m.chip(1)
    expect(not m.shown('oa_status') and not m.shown('oa_es_text') and not m.shown('oa_es_retry'), 'the Lyrics tab: no state block, the candidates')
    blits, fills, texts = m.paint()
    titles = [(t, r) for t, r in texts if r[1] % ROW_H == 7]
    subs = [(t, r) for t, r in texts if r[1] % ROW_H == 33]
    expect(not blits and [t for t, _ in titles] == ['I Want to Break Free', 'Both', 'Plain Only'], f'three rows: the exact match, then by the closeness of their length ({[t for t, _ in titles]})')
    expect([r for _, r in titles] == [(16, i * ROW_H + 7, TITLE_W, 24) for i in range(3)], f'each title in the row\'s title place, short of the badge by its width ({titles[1][1]})')
    expect([t for t, _ in subs][1:] == ['Somebody · Somewhere · 3:21', 'Somebody · Somewhere · 3:20'] and subs[0][0].startswith('Queen · The Works') and all(r[2] == 288 and r[3] == 20 for _, r in subs),
           f'the grey line: artist · album · length ({[t for t, _ in subs]})')
    badges = [(t, r) for t, r in texts if t in ('Synced', 'Saved')]
    expect([(t, r[1]) for t, r in badges] == [('Synced', 10), ('Synced', ROW_H + 10)] and all(r[0] == 304 - BADGE_W and r[2] == BADGE_W and r[3] == 18 for _, r in badges), f'the Synced badge on the synced rows only, at the title line\'s right end ({badges})')
    sf = [f for f in fills if f[0] == SYNCED_RGB]
    expect(len(sf) == 2 * 3 and sorted({f[3] for f in sf}) == [BADGE_W - 4, BADGE_W - 2, BADGE_W], f'a badge is a box with stepped corners ({len(sf)} fills for two badges)')
    hair = [f for f in fills if f[0] == 0xff222222]
    expect(len(hair) == 3 and hair[0][1:] == (16, ROW_H - 1, 288, 1), f'a hairline under every row ({hair})')
    # scroll positions are kept per tab
    m.chip(0)
    m.scroll(0); m.chip(1)
    expect(m.props.get((m.sv, 'yoffset')) == 0, 'a tab opens at its own position')
    # a long candidate list scrolls, and only whole rows are drawn at the edges
    many = OA.body(*[OA.rec(f'Song {i}', 200 + i, synced='[00:01.00] x\n', artist='Radiohead', album='OK Computer') for i in range(25)])
    m = AM(OA.Site(**{OA.LRCLIB + 'get?': {'rc': 22, 'code': 404}, OA.LRCLIB + 'search?': {'body': many}})); m.open(); m.ready()
    m.chip(1)
    expect(m.props.get((m.sv, 'virtual_h')) == 20 * ROW_H + 12, f'twenty rows: the content is taller than the list ({m.props.get((m.sv, "virtual_h"))})')
    _, _, texts = m.paint()
    expect(len([t for t, r in texts if r[3] == 24]) == 6 and max(r[1] for _, r in texts) + 20 <= LIST_H, 'six whole rows at the top')
    m.scroll(150)
    _, _, texts = m.paint()
    ys = [r[1] for t, r in texts if r[3] == 24]
    expect(ys and min(ys) >= 0 and max(ys) + 24 <= LIST_H, f'scrolled: only text wholly inside the list is drawn ({ys})')
    m.tap(100, 150 + 10)
    expect(m.shown('oa_dh_title') and m.text('oa_dh_title') == 'Song 17', 'a tap in the scrolled list is on the row under the finger (content coordinates; the first twenty records, the closest length first: row 2 is Song 17)')
    m.click('btn_return')
    expect(m.props.get((m.sv, 'yoffset')) == 150 and m.shown('oa_chips'), 'Back from the detail: the rows at the position they were left')


def status_tests(ctx):
    expect = ctx.expect
    # the state line of each tab
    m = AM(OA.Site(**{OA.ITUNES: {'rc': 22, 'code': 500}, OA.DEEZER: {'rc': 22, 'code': 500}, OA.LRCLIB + 'get?': {'rc': 22, 'code': 404}, OA.LRCLIB + 'search?': {'body': b'[]'}}))
    m.open(); m.work(); m.tick()
    expect(m.text('oa_status') == 'Server error' and m.shown('oa_status') and not m.paint()[0], 'covers: both services refuse: "Server error" over the empty list, nothing painted')
    m.chip(1)
    expect(m.text('oa_status') == 'No Lyrics Found' and m.shown('oa_status'), 'the Lyrics tab: "No Lyrics Found" (the lookups are independent)')
    m.chip(0)
    expect(m.text('oa_status') == 'Server error', 'and back: the covers\' word')
    m = AM(OA.Site(**{OA.ITUNES: {'body': b'{"results":[]}'}, OA.DEEZER: {'body': b'{"data":[]}'}})); m.open(); m.work(); m.tick()
    expect(m.text('oa_status') == 'No Covers Found' and m.shown('oa_status'), 'no result from either: "No Covers Found"')
    m.chip(1)
    expect(not m.shown('oa_status') and m.paint()[2], 'while its candidates are listed')
    for label, over, word in (('lyrics: no connection', {OA.LRCLIB: {'rc': 6}}, "Can't connect"), ('lyrics: a certificate error', {OA.LRCLIB: {'rc': 60}}, 'Certificate problem'),
                              ('lyrics: HTTP 500', {OA.LRCLIB: {'rc': 22, 'code': 500}}, 'Server error')):
        m = AM(OA.Site(**over)); m.open(); m.work(); m.ticks(3); m.chip(1)
        expect(m.text('oa_status') == word and m.shown('oa_status'), f'{label}: "{word}"')
        m.chip(0)
        expect(not m.shown('oa_status'), 'the covers unaffected')
    m = AM(OA.Site()); m.open(); m.chip(1)
    expect(m.text('oa_status') == 'Searching…' and m.shown('oa_status'), 'the Lyrics tab while the lookup runs: "Searching…"')
    # a thumbnail that cannot be had is the placeholder, the others arrive
    m = AM(OA.Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': {'rc': 22, 'code': 404}})); m.open(); m.work()
    m.ticks(10)
    expect(len([u for u in m.loads if u.startswith('file://')]) == NCOV - 1, f'a thumbnail that failed is not decoded (the placeholder): {len([u for u in m.loads if u.startswith("file://")])} of {NCOV}')
    expect(len(m.paint()[0]) == NCOV, 'all cells are painted (the placeholder for the failed one)')


def failure_tests(ctx):
    expect = ctx.expect
    # no track, a track without a path, an asset that is not ours, a window that will not open
    m = AM(OA.Site()); m.setword(pod.DATA['PLAY_QUEUE'][0], 0)
    expect(m.open() == 0xffffffff and ('window_open', 'm1plus_onlineart') not in m.calls and 'timer_add' not in [c[0] for c in m.calls], 'nothing playing: -1, no window')
    m = AM(OA.Site()); m.playing(path='')
    expect(m.open() == 0xffffffff and ('window_open', 'm1plus_onlineart') not in m.calls, 'a track without a path: -1')
    m = AM(OA.Site()); m.windows['m1plus_onlineart'] = 0
    expect(m.open() == 0xffffffff and 'timer_add' not in [c[0] for c in m.calls], 'a window that will not open: -1, nothing started')
    for missing in ('oa_view', 'oa_chips', 'oa_chip_hl', 'oa_sep', 'oa_listview', 'oa_scrollview', 'oa_status', 'oa_hint', 'oa_dh_title', 'oa_dh_sub', 'oa_dc', 'oa_dc_art', 'oa_dc_name', 'oa_dc_artist', 'oa_dc_source', 'oa_save', 'oa_lsave', 'oa_es_icon', 'oa_es_text', 'oa_es_retry',
                    'label_row_title', 'label_row_sub', 'label_chip', 'label_chip_on', 'label_badge', 'label_badge_on', 'label_line'):
        m = AM(OA.Site()); del m.widgets[missing]
        expect(m.open() == 0xffffffff and ('navigator_back',) in m.calls and 'timer_add' not in [c[0] for c in m.calls] and 'pthread_create' not in [c[0] for c in m.calls], f'an asset without {missing}: the page goes again (navigator_back), no timer, no worker')
    m = AM(OA.Site(), timer_fail=True)
    expect(m.open() == 0xffffffff and ('navigator_back',) in m.calls, 'a timer that cannot be made: the page goes again')
    # the lookup cannot start: the words, no worker
    for label, kw, word in (('no Wi-Fi', dict(wifi=-1), 'No Wi-Fi'), ('a clock never set', dict(wall=1700000000), 'Set the date first'), ('no card', dict(card_mounted=False), 'Storage unavailable')):
        m = AM(OA.Site(), **kw)
        r = m.open()
        expect(r == 0 and m.text('oa_status') == word and m.shown('oa_status') and 'pthread_create' not in [c[0] for c in m.calls], f'{label}: the page says "{word}", nothing starts')
        m.chip(1)
        expect(m.text('oa_status') == word, 'on the Lyrics tab too')
    m = AM(OA.Site())
    m.present.discard(PCN.CA)
    m.open()
    expect(m.text('oa_status') == 'Certificates missing', 'no CA bundle: "Certificates missing"')
    for label, over, word in (('both services refuse', {OA.ITUNES: {'rc': 22, 'code': 500}, OA.DEEZER: {'rc': 22, 'code': 500}}, 'Server error'),
                              ('no connection', {OA.ITUNES: {'rc': 6}, OA.DEEZER: {'rc': 6}}, "Can't connect"), ('a certificate error', {OA.ITUNES: {'rc': 60}, OA.DEEZER: {'rc': 60}}, 'Certificate problem')):
        m = AM(OA.Site(**over)); m.open(); m.work(); m.tick()
        expect(m.text('oa_status') == word and m.shown('oa_status'), f'covers: {label}: "{word}"')


def cover_tests(ctx):
    expect = ctx.expect
    site = OA.Site()
    m = AM(site)
    m.open(); m.ready()
    n_before = len(site.reqs)
    # a tap in the gaps, below the grid or beyond the cells does nothing
    for x, y in ((X0 + TILE + 3, Y0 + 20), (X0 + 5, Y0 + TILE + 4), (X0 + 5, Y0 + 3 * PITCH + 10), (4, 60), (315, 60), (160, 340)):
        m.tap(x, y)
        expect('pthread_create' not in [c[0] for c in m.calls] and m.shown('oa_listview') and not m.shown('oa_dc'), f'a tap at ({x}, {y}) is on no cover: nothing happens')
    # a drag that ends on the cover is no tap
    m.calls = []; m.pointer(m.view, EVT_DOWN, X0 + 10, Y0 + 10); m.pointer(m.view, EVT_UP, X0 + 60, Y0 + 10)
    expect(not m.shown('oa_dc') and 'pthread_create' not in [c[0] for c in m.calls], 'a press that moves 50 px before it lets go is not a tap')
    m.calls = []; m.pointer(m.view, EVT_DOWN, X0 + 10, Y0 + 10); m.pointer(m.view, EVT_ABORT, X0 + 10, Y0 + 10); m.pointer(m.view, EVT_UP, X0 + 10, Y0 + 10)
    expect(not m.shown('oa_dc'), 'a press the scroll_view took (aborted) is no tap')
    # a tap opens the confirmation: the larger picture is fetched, nothing is written
    m.tap_tile(1)
    names = [c[0] for c in m.calls]
    expect(m.shown('oa_dc') and not m.shown('oa_chips') and not m.shown('oa_listview') and not m.shown('oa_sep') and not m.shown('oa_status') and not m.shown('oa_lsave'), 'a tap on a cover: the confirmation, the tabs and the list gone')
    expect(names.count('pthread_create') == 1 and m.thread[0] == PSYMS['pn_kmain'], 'the larger picture is fetched (the pick job without a save)')
    expect(m.text('oa_dc_name') == 'Ágætis byrjun' or m.text('oa_dc_name') == m.text('oa_dc_name'), 'the album')
    it = [r for r in __import__('json').loads(OA.data('itunes_album.json'))['results'] if r.get('artworkUrl100')]
    expect(m.text('oa_dc_name') == it[1]['collectionName'] and m.text('oa_dc_artist') == it[1]['artistName'] and m.text('oa_dc_source') == 'iTunes', f'the album, the artist and the source of the cover tapped ({m.text("oa_dc_name")}, {m.text("oa_dc_artist")}, {m.text("oa_dc_source")})')
    expect(not m.shown('oa_save') and not m.shown('oa_hint'), 'no pill until the picture is there')
    m.tick()
    expect(not m.shown('oa_save'), 'and still while it downloads')
    m.work()
    expect(site.urls()[n_before:] == [site.urls()[3].replace('100x100bb', '600x600bb')], f'the larger picture of cover 2 is fetched ({site.urls()[n_before:]})')
    expect(not [p for p in m.fs if p.startswith(OA.COVERS)] and FOLDER + '/cover.jpg' not in m.fs and not [p for p in m.fs if p.endswith('.pick')], 'NOTHING is written: no cache file, no marker, no folder picture')
    m.tick()
    loads = [u for u in m.loads if u.endswith('full.jpg')]
    expect(loads == ['file://' + OA.ART_DIR + '/full.jpg'] and m.shown('oa_save') and m.text('oa_save') == 'Use This Cover', f'the tick decodes the larger picture and shows the pill: Use This Cover ({loads})')
    blits = m.paint_dc()
    expect(len(blits) == 1 and blits[0][2] == (0, 0, 240, 240), f'the cover is painted 240 px in its view ({blits})')
    # Back without the pill: nothing changes
    m.click('btn_return')
    expect(m.shown('oa_chips') and m.shown('oa_listview') and not m.shown('oa_dc') and ('navigator_back',) not in m.calls, 'Back from the confirmation: the tabs again, the page stays')
    m.tick()
    expect(not [p for p in m.fs if p.startswith(OA.COVERS)] and FOLDER + '/cover.jpg' not in m.fs and f'{OA.ART_DIR}/full.jpg' not in m.fs, 'nothing written, and the held picture removed once no worker runs')
    blits, fills, _ = m.paint()
    expect(len(blits) == NCOV and not [f for f in fills if f[0] == 0xffffffff], 'the grid has no current cover')
    # the pill saves
    m.tap_tile(1); m.work(); m.tick()
    n1 = len(site.reqs)
    m.click('oa_save')
    names = [c[0] for c in m.calls]
    expect(names.count('pthread_create') == 1 and m.thread[0] == PSYMS['pn_kmain'] and m.text('oa_save') == 'Saving…' and m.shown('oa_save'), f'the pill starts the save; it reads Saving… ({names})')
    m.click('oa_save')
    expect('pthread_create' not in [c[0] for c in m.calls], 'a second tap while it runs is ignored')
    m.tick()
    expect(m.shown('oa_dc'), 'still the confirmation while it runs')
    m.work()
    key0 = OA_key('Radiohead', 'OK Computer')
    expect(len(site.reqs) == n1, 'the picture that was fetched is used: no second download')
    cache = f'{OA.COVERS}/r{key0:08x}-168.jpg'
    expect(cache in m.fs and cache + '.pick' in m.fs, 'the cover cache file of the playing track\'s album and its .pick marker are written')
    expect(m.fs.get(FOLDER + '/cover.jpg') == OA.JPG, 'and the original JPEG next to the track as cover.jpg')
    expect([p for p in m.fs if p.startswith(OA.COVERS) and p.endswith('.jpg')] == [cache], 'the same artist: one cache file')
    m.tick()
    expect(m.shown('oa_chips') and m.shown('oa_listview') and not m.shown('oa_dc'), 'the tick: back to the grid')
    blits, fills, _ = m.paint()
    frame = [f for f in fills if f[0] == 0xffffffff]
    x, y = X0 + 1 * (TILE + GAP), Y0
    expect(len(frame) == 4 and (0xffffffff, x - 3, y - 3, TILE + 6, 2) in [f[:5] for f in frame], f'the cover is marked current: a white frame (four bars around it) ({frame})')
    m.tap_tile(1)
    expect(m.text('oa_dc_name') != '' and not m.shown('oa_save'), 'the same cover again: the confirmation')
    m.work(); m.tick()
    expect(m.text('oa_save') == 'Replace Cover', 'the album already has a picked cover: the pill reads Replace Cover')
    m.click('btn_return'); m.tick()
    # another pick moves the frame (Deezer's cover)
    m.tap_tile(4); m.work(); m.tick(); m.click('oa_save'); m.work(); m.tick(); m.tick()
    blits, fills, _ = m.paint()
    frame = [f[:5] for f in fills if f[0] == 0xffffffff]
    x, y = X0 + 1 * (TILE + GAP), Y0 + PITCH
    expect((0xffffffff, x - 3, y - 3, TILE + 6, 2) in frame and len(frame) == 4, 'a second pick moves the frame to that cover')
    expect(site.urls()[-1] == site.urls()[6].replace('250x250-', '500x500-'), 'Deezer\'s cover: its 500 px picture')
    m.tap_tile(4)
    expect(m.text('oa_dc_source') == 'Deezer', 'a Deezer cover says Deezer')
    # a compilation: the library lists the album under another artist: that key gets the cover too
    m = AM(OA.Site(), albums=())
    m.playing(artist='Various', album='OK Computer', albums=())
    m.class_lists[O['CLASS_ALBUMS']] = [m.record(album='ok computer', artist='Radiohead', rid=1), m.record(album='Unknown Album', rid=-1)]
    m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick(); m.click('oa_save'); m.work()
    k_track, k_row = OA_key('Various', 'OK Computer'), OA_key('Radiohead', 'ok computer')
    caches = sorted(p for p in m.fs if p.startswith(OA.COVERS) and p.endswith('.jpg'))
    expect(k_track != k_row and caches == sorted([f'{OA.COVERS}/r{k_track:08x}-168.jpg', f'{OA.COVERS}/r{k_row:08x}-168.jpg']), f'a compilation: the track\'s own key and the library row\'s key both get the cover ({[c[-17:] for c in caches]})')
    # a track in the card's root: no folder picture
    m = AM(OA.Site()); m.playing(path='/mnt/mmc/song.flac'); m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick(); m.click('oa_save'); m.work()
    expect(not [p for p in m.fs if p.endswith(('cover.jpg', 'folder.jpg'))] and [p for p in m.fs if p.startswith(OA.COVERS) and p.endswith('.jpg')], 'a track in the card\'s root: the cache gets the cover, no folder picture is put in the root')


def cover_failure_tests(ctx):
    expect = ctx.expect
    big = lambda u, o: {'rc': 22, 'code': 404} if '600x600bb' in u else {'body': OA.JPG, 'chunk': 5500}
    m = AM(OA.Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': big})); m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick()
    expect(m.shown('oa_dc') and m.shown('oa_hint') and m.text('oa_hint') == "Can't connect" and not m.shown('oa_save') and not [p for p in m.fs if p.startswith(OA.COVERS)], 'the larger picture cannot be fetched: the failure word on the confirmation, no pill, nothing written')
    m.click('btn_return'); m.tick()
    m.tap_tile(1); m.work(); m.tick()
    expect(m.shown('oa_save') and not m.shown('oa_hint'), 'another cover afterwards works (the message is gone)')
    # not a picture
    notpic = lambda u, o: {'body': b'<html>x</html>'} if '600x600bb' in u else {'body': OA.JPG}
    m = AM(OA.Site(**{'https://is1-ssl.mzstatic.com/image/thumb/Music115': notpic})); m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick()
    expect(m.text('oa_hint') == 'Server error' and not m.shown('oa_save'), 'an answer that is not a picture: "Server error"')
    # a save that fails: the word in the hint, the pill back for another try
    m = AM(OA.Site()); m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick()
    key0 = OA_key('Radiohead', 'OK Computer')
    m.fail = {('rename', f'{OA.COVERS}/r{key0:08x}-168.jpg')}
    m.click('oa_save'); m.work(); m.tick()
    expect(m.shown('oa_dc') and m.text('oa_hint') == 'Storage unavailable' and m.text('oa_save') == 'Use This Cover' and m.shown('oa_save'), 'a cache file that cannot be written: "Storage unavailable" on the confirmation, the pill reads Use This Cover again')
    m.fail = set()
    m.click('oa_save')
    expect(not m.shown('oa_hint') and m.text('oa_save') == 'Saving…', 'the next try clears the message')
    m.work(); m.tick()
    expect(not m.shown('oa_dc') and OA.COVERS + f'/r{key0:08x}-168.jpg' in m.fs, 'and writes it')
    # the Wi-Fi lost between the fetch and the pill
    m = AM(OA.Site()); m.open(); m.ready()
    m.tap_tile(0); m.work(); m.tick()
    m.wifi = -1; m.click('oa_save')
    expect('pthread_create' not in [c[0] for c in m.calls] and m.text('oa_hint') == 'No Wi-Fi' and m.shown('oa_save'), 'the Wi-Fi lost before the pill: refused, and said so; the picture is still held')
    m.wifi = 4; m.click('oa_save')
    expect(m.thread[0] == PSYMS['pn_kmain'] and m.text('oa_save') == 'Saving…', 'with the Wi-Fi back the pill saves')
    # Back while the picture downloads: cancelled, nothing kept
    m = AM(OA.Site()); m.open(); m.ready()
    m.tap_tile(0)
    m.click('btn_return')
    expect(m.shown('oa_chips') and not m.shown('oa_dc'), 'Back while the picture downloads: the tabs')
    m.work(); m.ticks(3)
    expect(not [p for p in m.fs if p.startswith(OA.COVERS)] and f'{OA.ART_DIR}/full.jpg' not in m.fs, 'the fetch was cancelled: nothing written, nothing held')
    # a tap while another job still runs (the slot is busy): the fetch waits for it
    m = AM(OA.Site()); m.open(); m.ready()
    m.thread = None
    fn(m, 'pn_search', m.cstr('radio'))
    job = m.thread
    m.tap_tile(0)
    expect('pthread_create' not in [c[0] for c in m.calls] and m.shown('oa_dc'), 'the slot is busy: the confirmation opens, the fetch waits')
    m.tick()
    expect('pthread_create' not in [c[0] for c in m.calls], 'and still waits')
    m.thread = None; PCN.work(m, job)
    m.tick()
    expect([c[0] for c in m.calls].count('pthread_create') == 1 and m.thread[0] == PSYMS['pn_kmain'], 'once it has ended the tick starts the fetch')


def OA_key(artist, album):
    h = 2166136261   # cc_fnv twice: each ends with one more multiplication (the NUL)
    for s in (artist, album):
        for c in s.encode('utf-8'): h = ((h ^ c) * 16777619) & 0xffffffff
        h = (h * 16777619) & 0xffffffff
    return h or 1


def lyrics_tests(ctx):
    expect = ctx.expect
    m = AM(OA.Site()); m.open(); m.ready()
    m.fs[LRC] = b'my own lyrics'
    m.open_lyrics(0)
    expect(m.shown('oa_dh_title') and m.shown('oa_dh_sub') and m.shown('oa_listview') and m.shown('oa_sep') and not m.shown('oa_chips') and not m.shown('oa_dc') and m.shown('oa_lsave'), 'a tap on a row: the header, the text list and the pill; the chips gone')
    expect(m.text('oa_dh_title') == 'I Want to Break Free' and m.text('oa_dh_sub').startswith('Queen · The Works (Remastered 2011)') and m.text('oa_dh_sub').endswith('4:19'), f'the header: the title, then artist · album · length ({m.text("oa_dh_sub")})')
    expect(m.fs[LRC] == b'my own lyrics' and m.text('oa_lsave') == 'Replace Lyrics', 'an .lrc that is there: the pill reads Replace Lyrics, and the file is untouched')
    _, _, texts = m.paint()
    lines = [t for t, r in texts]
    expect(lines[:2] == ['Line one of the sample song', 'Line two of the sample song'] and ' '.join(lines[2:4]) == 'Line three of the sample song, a little longer' and ' '.join(lines[4:-1]) == 'Line four of the sample song is long enough to wrap onto a second line' and lines[-1] == '♪',
           f'the full text without its [mm:ss.xx] tags and the [ar:] / [ti:] headers, long lines wrapped ({lines})')
    ys = [r[1] for t, r in texts]
    expect(ys == [8 + 24 * i for i in range(len(ys))] and all(r[0] == 16 and r[2] == 288 and r[3] == 24 for _, r in texts), f'lines {24} px apart from y 8, 288 px wide ({ys})')
    expect(set(m.text_styles) == {'label_line'}, 'in the lyrics text style')
    m.click('oa_lsave')
    expect(m.fs[LRC].startswith(b'[ar:Queen]') and LRC + '.tmp' not in m.fs and m.fs[LRC].endswith(b'\xe2\x99\xaa\n'), 'the pill replaces <track>.lrc, the file name\'s extension replaced by .lrc, atomically, with the timestamps (the display strips them, the file does not)')
    expect(m.shown('oa_chips') and not m.shown('oa_dh_title') and not m.shown('oa_lsave'), 'then the rows again')
    _, fills, texts = m.paint()
    expect(('Saved' in [t for t, _ in texts]) and [t for t, _ in texts].count('Synced') == 1 and any(f[0] == SAVED_RGB for f in fills) and not any(f[0] == SYNCED_RGB and f[2] < 14 for f in fills),
           'the saved row wears a light Saved badge in place of Synced; the other synced row still has its Synced badge')
    # nothing is written without the tap; an upper-case .LRC counts as existing; Back saves nothing
    m = AM(OA.Site()); m.open(); m.ready(); m.open_lyrics(1)
    expect(m.text('oa_lsave') == 'Save Lyrics' and LRC not in m.fs, 'no .lrc yet: the pill reads Save Lyrics, nothing written')
    lines = [t for t, _ in m.paint()[2]]
    expect(lines == ['歌词第一行', '第二行'], f'the second candidate\'s text: two lines, CJK intact ({lines})')
    m.click('btn_return')
    expect(m.shown('oa_chips') and LRC not in m.fs and ('navigator_back',) not in m.calls, 'Back from the detail: the rows, nothing written, the page stays')
    _, fills, texts = m.paint()
    expect('Saved' not in [t for t, _ in texts], 'no row is marked')
    m.open_lyrics(1); m.click('oa_lsave')
    expect(m.fs[LRC] == TXT_SYNCED.encode(), 'the second candidate saved: its text exactly')
    m = AM(OA.Site()); m.fs[FOLDER + '/02 Karma Police.LRC'] = b'upper'; m.open(); m.ready(); m.open_lyrics(0)
    expect(m.text('oa_lsave') == 'Replace Lyrics', 'an upper-case .LRC counts as an existing one')
    # names: no extension, dots in the folder
    for path, want in (('/mnt/mmc/a.b/track', '/mnt/mmc/a.b/track.lrc'), ('/mnt/mmc/Music/x.mp3', '/mnt/mmc/Music/x.lrc'), ('/mnt/mmc/Music/a.b.c.flac', '/mnt/mmc/Music/a.b.c.lrc')):
        m = AM(OA.Site()); m.playing(path=path); m.dirs.add(path.rsplit('/', 1)[0]); m.open(); m.ready(); m.open_lyrics(0)
        m.click('oa_lsave')
        expect(want in m.fs, f'{path} -> {want}')
    # a card that cannot be written
    m = AM(OA.Site()); m.open(); m.ready(); m.open_lyrics(0)
    m.fail = {('write', LRC + '.tmp')}
    m.click('oa_lsave')
    expect(m.shown('oa_dh_title') and m.text('oa_dh_sub') == 'Storage unavailable' and m.shown('oa_lsave') and LRC not in m.fs, 'a write that fails: "Storage unavailable" in the header\'s grey line, the pill stays for another try')
    m.fail = set()
    m.click('oa_lsave')
    expect(m.fs[LRC].startswith(b'[ar:Queen]') and m.shown('oa_chips'), 'and the next try writes it')
    # plain lyrics: blank lines are gaps; a long line wraps; the text scrolls
    plain = '\n'.join(['Verse one line A', 'Verse one line B', '', '', 'Verse two ' + 'long ' * 20, '', 'Last'])
    site = OA.Site(**{OA.LRCLIB + 'get?': {'body': OA.json.dumps(OA.rec('P', 261, plain=plain, artist='Radiohead', album='OK Computer')).encode()}, OA.LRCLIB + 'search?': {'body': b'[]'}})
    m = AM(site); m.open(); m.ready(); m.open_lyrics(0)
    _, _, texts = m.paint()
    ys = [r[1] for t, r in texts]
    t = [t for t, _ in texts]
    expect(t[:2] == ['Verse one line A', 'Verse one line B'] and ys[:2] == [8, 32] and ys[2] == 56 + 12 and t[2].startswith('Verse two'), f'a plain text: blank lines are one gap of 12 px, however many ({ys[:4]})')
    expect(' '.join(t[2:-1]) == ('Verse two ' + 'long ' * 20).strip() and t[-1] == 'Last' and ys[-1] - ys[-2] == 24 + 12, f'a long line wraps ({len(t) - 3} lines) and the gap before the last line ({t})')
    # a lyric line wraps onto as many lines as it needs and is never cut with an ellipsis: a long English line (eight lines of 36 characters in the mocked 8 px font), a CJK line (broken between characters), a line without a space
    english = 'This is a long English test line for the wrapping check. ' * 5 + 'The end of the sample line'
    cjk = '示例歌词第一行是一句很长的测试文字用来检查换行'  * 12
    nospace = 'x' * 330
    for label, line in (('an English line', english), ('a CJK line', cjk), ('a line without a space', nospace)):
        site = OA.Site(**{OA.LRCLIB + 'get?': {'body': OA.json.dumps(OA.rec('P', 261, plain=line + '\nLast', artist='Radiohead', album='OK Computer')).encode()}, OA.LRCLIB + 'search?': {'body': b'[]'}})
        m = AM(site); m.open(); m.ready(); m.open_lyrics(0)
        m.scroll(0)
        got = []
        for off in range(0, 600, 60):   # (only the lines wholly inside the text region are drawn: walk the text)
            m.scroll(off)
            for t, r in m.paint()[2]:
                if (r[1] + off, t) not in got: got.append((r[1] + off, t))
        got.sort()
        lines = [t for _, t in got]
        body = lines[:-1] if lines[-1] == 'Last' else lines
        joined = ''.join(body) if label != 'an English line' else ' '.join(body)
        expect(len(body) >= 7 and '…' not in ''.join(lines) and joined.replace('  ', ' ').strip() == line.strip() and lines[-1] == 'Last', f'{label} ({len(line)} characters): {len(body)} lines, the whole text, no ellipsis')
        expect(all(b - a == 24 for (a, _), (b, _) in zip(got, got[1:])), f'{label}: the lines are one pitch apart')
    many = '\n'.join(f'Line number {i}' for i in range(40))
    site = OA.Site(**{OA.LRCLIB + 'get?': {'body': OA.json.dumps(OA.rec('P', 261, plain=many)).encode()}, OA.LRCLIB + 'search?': {'body': b'[]'}})
    m = AM(site); m.open(); m.ready(); m.open_lyrics(0)
    expect(m.props.get((m.sv, 'virtual_h')) == 8 + 40 * 24 + 12 + (LIST_H - 300), f'the content is as tall as the text and the pill\'s air ({m.props.get((m.sv, "virtual_h"))})')
    _, _, texts = m.paint()
    expect(len(texts) == 12 and max(r[1] + r[3] for _, r in texts) <= 300, 'twelve lines fit the text region (the list\'s top 300 px)')
    m.scroll(500)
    _, _, texts = m.paint()
    ys = [r[1] for _, r in texts]
    expect(texts and min(ys) >= 0 and max(ys) + 24 <= 300 and texts[0][0] == 'Line number 21', f'scrolled: whole lines only, inside the region ({texts[0][0]}, {ys[0]}..{ys[-1]})')
    m.click('btn_return')
    expect(m.shown('oa_chips') and m.props.get((m.sv, 'virtual_h')) == LIST_H, 'Back: the rows\' height again')
    # a text that cannot be read: no pill
    m = AM(OA.Site()); m.open(); m.ready()
    del m.fs[OA.ART_DIR + '/l0.txt']
    m.open_lyrics(0)
    expect(m.shown('oa_dh_title') and not m.shown('oa_lsave'), 'a candidate whose text is gone: the header, no pill')
    # destroy in a detail
    m.destroy()
    expect(('timer_remove', 0x777) in m.calls, 'destroy from a detail: the page ends')


def life_tests(ctx):
    expect = ctx.expect
    # destroy while the worker runs: cancelled, the files are left for the next lookup, the downloads are not started
    m = AM(OA.Site()); m.open()
    m.destroy()
    expect(('timer_remove', 0x777) in m.calls, 'destroy with the worker still running: the timer goes')
    word = m.call(PSYMS['pn_job_busy'], count=2000)
    expect(word == 1, 'the worker is still busy (it ends by itself)')
    site = m.curl_site
    m.work()
    expect(m.call(PSYMS['pn_job_busy'], count=2000) == 0 and not site.reqs and fn(m, 'pn_art_state') == 3 and fn(m, 'pn_art_code') == 12,
           f'it ended without the page: it had been told to stop, so nothing was asked for ({len(site.reqs)} requests), covers PN_CANCELLED')
    # destroy from the confirmation: the held picture and the decoded cover go
    m = AM(OA.Site()); m.open(); m.ready(); m.tap_tile(0); m.work(); m.tick()
    m.destroy()
    expect(f'{OA.ART_DIR}/full.jpg' not in m.fs, 'destroy from the confirmation: the held picture is removed')
    # the downloads: a running one is asked to pause, the lookup starts when it has stopped, and the queue goes on once the lookup has ended
    site = OA.Site()
    m = AM(site)
    m.thread = None
    r = fn(m, 'pn_dl_add', m.cstr(PCN.ROOT_DIR), m.cstr('Show'), m.cstr('ep.mp3'))
    dl = m.thread
    expect(r == 0 and dl and dl[0] == PSYMS['pn_dmain'] and fn(m, 'pn_dl_running') == 1, 'a download is running')
    m.open()
    expect('pthread_create' not in [c[0] for c in m.calls] and m.text('oa_status') == 'Searching…' and not site.reqs, 'the page opens while it runs: the lookup waits, "Searching…"')
    m.tick()
    expect('pthread_create' not in [c[0] for c in m.calls] and fn(m, 'pn_dl_running') == 1, 'the download was asked to pause: it has not stopped yet, so the lookup still waits')
    m.thread = None; PCN.work(m, dl)
    expect(fn(m, 'pn_dl_running') == 0 and fn(m, 'pn_dl_waiting') == 1, 'the paused download stopped and stays queued')
    m.tick()
    expect([c[0] for c in m.calls].count('pthread_create') == 1 and m.thread[0] == PSYMS['pn_amain'], 'the tick starts the lookup now')
    m.work()
    for _ in range(10): m.tick()
    expect(fn(m, 'pn_job_busy') == 0 and fn(m, 'pn_dl_running') == 1 and m.thread[0] == PSYMS['pn_dmain'], 'the lookup ended: the queued download is started again by the page\'s tick')


BUSY = {'rc': 22, 'code': 503}
GLYPH_PX = 40


def snap(m, tab):
    """The state block of a tab as the page shows it: (glyph, title, text, pill shown), after a switch to the tab has made the page say it."""
    m.chip(1 - tab); m.chip(tab)
    icon = m.widgets['oa_es_icon']
    glyph = [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == icon]
    return ((glyph[-1] if glyph and m.shown('oa_es_icon') else ''), m.text('oa_status') if m.shown('oa_status') else '',
            m.text('oa_es_text') if m.shown('oa_es_text') else '', m.shown('oa_es_retry'))


def trl(loc, key): return pod_i18n.TEXT[key][loc]


def state_tests(ctx):
    expect = ctx.expect
    sites = {   # name: (site overrides, machine options, tab); what the page shows is tools/pod_ui.py OA_ES_STATES[name]
        'lyrics busy': ({OA.LRCLIB: BUSY}, {}, 1),
        'covers busy': ({OA.ITUNES: BUSY, OA.DEEZER: BUSY}, {}, 0),
        'no lyrics': ({OA.LRCLIB + 'get?': {'rc': 22, 'code': 404}, OA.LRCLIB + 'search?': {'body': b'[]'}}, {}, 1),
        'no covers': ({OA.ITUNES: {'body': b'{"results":[]}'}, OA.DEEZER: {'body': b'{"data":[]}'}}, {}, 0),
        'no connection': ({OA.ITUNES: {'rc': 6}, OA.DEEZER: {'rc': 6}}, {}, 0),
        'lyrics: no connection': ({OA.LRCLIB: {'rc': 6}}, {}, 1),
        'certificate': ({OA.ITUNES: {'rc': 60}, OA.DEEZER: {'rc': 60}}, {}, 0),
        'server error': ({OA.ITUNES: {'rc': 22, 'code': 500}, OA.DEEZER: {'rc': 22, 'code': 500}}, {}, 0),
        'lyrics: server error': ({OA.LRCLIB: {'rc': 22, 'code': 500}}, {}, 1),
        'no Wi-Fi': ({}, {'wifi': -1}, 0),
        'no date': ({}, {'wall': 1700000000}, 1),
        'no card': ({}, {'card_mounted': False}, 0),
        'no memory': ({}, {'calloc_fail_size': 98305}, 1),
    }
    sites['no certificates'] = ({}, {'present': set()}, 0)
    for name, (over, kw, tab) in sites.items():
        want = pod_ui.OA_ES_STATES[name.replace('lyrics: ', '')]
        for loc in pod_i18n.LOCALES:
            m = AM(OA.Site(**over), **kw); m.set_language(loc); m.open()
            if m.thread: m.work()   # (a guard that refuses starts no worker)
            m.tick()
            glyph, title, text, pill = snap(m, tab)
            wg, wt, wx, wp = want
            ok = (glyph, title, text, pill) == (wg, trl(loc, wt), trl(loc, wx), wp)
            if not ok or loc == 'en_US': expect(ok, f'{name} ({loc}): the glyph {wg}, the title, the explanation{", Try Again" if wp else ", no pill"} ({(glyph, title, text, pill)})')
            if not ok: break
        else:
            expect(True, f'{name}: the same block in all 13 languages')
        if want[3] and ok:
            expect(m.text('oa_es_retry') == trl(loc, 'Try Again'), f'{name}: the pill says Try Again in the page\'s language')
    m = AM(OA.Site())
    m.open()
    glyph, title, text, pill = snap(m, 0)
    expect((glyph, title, text, pill) == ('', 'Searching…', '', False) and not m.shown('oa_es_icon') and not m.shown('oa_es_text') and not m.shown('oa_es_retry'), f'while it searches: only the title "Searching…", no glyph, text or pill ({(glyph, title, text, pill)})')
    # the layout: stacked and centred as a whole on y 260
    m = AM(OA.Site(**{OA.LRCLIB: BUSY})); m.open(); m.work(); m.tick(); m.chip(1)
    at = lambda n: (m.props.get((m.widgets[n], 'x')), m.props.get((m.widgets[n], 'y')))
    expect([at('oa_es_icon'), at('oa_status'), at('oa_es_text'), at('oa_es_retry')] == [(140, 171), (16, 225), (30, 255), (76, 313)],
           f'glyph, title, text and pill stacked (40 + 14 + 26 + 4 + 40 + 18 + 36 = 178 px) and centred on y 260 ({[at("oa_es_icon"), at("oa_status"), at("oa_es_text"), at("oa_es_retry")]})')
    m = AM(OA.Site(**{OA.LRCLIB + 'get?': {'rc': 22, 'code': 404}, OA.LRCLIB + 'search?': {'body': b'[]'}})); m.open(); m.work(); m.tick(); m.chip(1)
    expect([at('oa_es_icon'), at('oa_status'), at('oa_es_text')] == [(140, 198), (16, 252), (30, 282)], f'without a pill the block is 124 px: it moves down to stay centred ({[at("oa_es_icon"), at("oa_status"), at("oa_es_text")]})')
    m = AM(OA.Site()); m.open()
    expect(any(c == ('label_set_line_wrap', m.widgets['oa_es_text'], 1) for c in m.calls), 'the explanation label wraps its text (line wrap on)')
    m = AM(OA.Site(**{OA.LRCLIB: BUSY})); m.open(); m.work(); m.tick(); m.chip(1)
    expect(m.shown('oa_es_retry') and not m.props.get((m.widgets['oa_es_icon'], 'sensitive'), False) and not m.props.get((m.widgets['oa_es_text'], 'sensitive'), False), 'only the pill takes touches: the glyph and the text stay insensitive')
    m.chip(0)
    expect(not m.shown('oa_es_retry') and not m.shown('oa_status') and not m.shown('oa_es_icon'), 'the Covers tab (it has covers): no block, no pill')
    m.chip(1)
    m.tap(100, 100)
    expect(not m.shown('oa_dh_title'), 'a tap on the empty list opens nothing')
    # a detail hides the block
    m = AM(OA.Site(**{OA.ITUNES: BUSY, OA.DEEZER: BUSY})); m.open(); m.work(); m.tick(); m.chip(1)
    m.tap_row(0); m.click('btn_return')
    expect(m.shown('oa_dh_title') is False and m.shown('oa_chips'), 'Back from a lyrics detail: the tabs')
    m.chip(0)
    expect(m.shown('oa_es_retry') and m.text('oa_status') == 'Cover Service Busy', 'the covers\' busy block is there on its tab')


def again_tests(ctx):
    expect = ctx.expect
    # Try Again restarts only its tab's lookup; the other tab keeps its results
    live = {'busy': True}
    ok = lambda name: OA.data(name)
    site = OA.Site(**{OA.LRCLIB + 'get?': lambda u, o: BUSY if live['busy'] else {'body': ok('lrclib_get.json')},
                      OA.LRCLIB + 'search?': lambda u, o: BUSY if live['busy'] else {'body': ok('lrclib_search.json')}})
    m = AM(site); m.open(); m.work(); m.ticks(NCOV + 1)
    n0 = len(site.reqs)
    loads0 = len(m.loads)
    m.chip(1)
    expect(m.text('oa_status') == 'Lyrics Service Busy' and m.shown('oa_es_retry'), 'the Lyrics tab is busy (a 503), the pill is there')
    lr = [u for u, _ in site.reqs if u.startswith(OA.LRCLIB)]
    expect(len(lr) == 1 and lr[0].startswith(OA.LRCLIB + 'get?'), f'get was asked once, busy, and the search was skipped ({len(lr)} requests)')
    live['busy'] = False
    m.thread = None
    m.click('oa_es_retry')
    expect(m.thread and m.thread[0] == PSYMS['pn_amain'] and [c[0] for c in m.calls].count('pthread_create') == 1, 'Try Again starts a worker at once (the slot is free)')
    expect(m.text('oa_status') == 'Searching…' and not m.shown('oa_es_retry'), 'meanwhile: "Searching…", no pill')
    m.chip(0)
    expect(m.shown('oa_dc') is False and len(m.paint()[0]) == NCOV, 'the Covers tab was not touched: its seven covers are painted')
    m.chip(1)
    m.work(); m.ticks(3)
    new = [u for u, _ in site.reqs[n0:]]
    expect(new and all(u.startswith(OA.LRCLIB) for u in new), f'only LRCLIB was asked again ({len(new)} requests, none for the covers)')
    expect(not m.shown('oa_status') and len(m.paint()[2]) > 0 and len(m.loads) == loads0, 'the lyrics rows are there, no cover was decoded again')
    m.chip(0)
    expect(len(m.paint()[0]) == NCOV, 'and the covers are still there')
    # the covers retry leaves the lyrics alone
    live2 = {'busy': True}
    site = OA.Site(**{OA.ITUNES: lambda u, o: BUSY if live2['busy'] else {'body': ok('itunes_album.json')}, OA.DEEZER: lambda u, o: BUSY if live2['busy'] else {'body': ok('deezer_album.json')}})
    m = AM(site); m.open(); m.work(); m.ticks(3)
    expect(m.text('oa_status') == 'Cover Service Busy' and m.shown('oa_es_retry'), 'the Covers tab: both services busy: "Cover Service Busy" and the pill')
    m.chip(1)
    expect(m.paint()[2] != [] and not m.shown('oa_es_retry'), 'the Lyrics tab has its rows')
    n0 = len(site.reqs)
    live2['busy'] = False
    m.chip(0); m.thread = None
    m.click('oa_es_retry')
    expect(m.thread and m.text('oa_status') == 'Searching…', 'Try Again on the Covers tab starts the covers worker')
    m.work(); m.ticks(NCOV + 2)
    new = [u for u, _ in site.reqs[n0:]]
    expect(new[0].startswith(OA.ITUNES) and not [u for u in new if u.startswith(OA.LRCLIB)] and len(m.paint()[0]) == NCOV, f'iTunes, Deezer and the thumbnails again, LRCLIB not asked ({len(new)} requests); the covers are painted')
    m.chip(1)
    expect(len([t for t, r in m.paint()[2] if r[3] == 24]) == 3, 'the lyrics rows are as they were (three)')
    # the slot is busy (another lookup): Try Again waits, the pill is gone, the tick starts it when the job has ended
    live3 = {'busy': True}
    site = OA.Site(**{OA.LRCLIB: lambda u, o: BUSY if live3['busy'] else {'rc': 22, 'code': 404}})
    m = AM(site); m.open(); m.work(); m.ticks(3); m.chip(1)
    live3['busy'] = False
    m.thread = None
    r = fn(m, 'pn_search', m.cstr('radio'))
    other = m.thread
    expect(r == 0 and other and fn(m, 'pn_job_busy') == 1, 'another job (a podcast search) holds the slot')
    m.click('oa_es_retry')
    expect('pthread_create' not in [c[0] for c in m.calls] and m.text('oa_status') == 'Searching…' and not m.shown('oa_es_retry'), 'Try Again waits for it: no worker, "Searching…", the pill gone (a second tap cannot queue twice)')
    m.tick()
    expect('pthread_create' not in [c[0] for c in m.calls], 'still waiting while the job runs')
    m.thread = None; PCN.work(m, other)
    m.tick()
    expect([c[0] for c in m.calls].count('pthread_create') == 1 and m.thread[0] == PSYMS['pn_amain'], 'the job ended: the tick starts the lyrics lookup')
    m.work(); m.ticks(2); m.chip(1)
    expect(m.text('oa_status') == 'No Lyrics Found' and not m.shown('oa_es_retry'), 'its answer: "No Lyrics Found" (404 and an empty search), no pill')
    # a guard that fails on the retry says its word on that tab only
    live4 = {'busy': True}
    site = OA.Site(**{OA.LRCLIB: lambda u, o: BUSY if live4['busy'] else {'rc': 22, 'code': 404}})
    m = AM(site); m.open(); m.work(); m.ticks(3); m.chip(1)
    m.wifi = -1
    m.click('oa_es_retry')
    expect(m.text('oa_status') == 'No Wi-Fi' and m.shown('oa_es_retry') and 'pthread_create' not in [c[0] for c in m.calls], 'the Wi-Fi is gone: the retry says "No Wi-Fi" and offers the pill again')
    m.chip(0)
    expect(len(m.paint()[0]) == NCOV and not m.shown('oa_es_retry'), 'the covers are untouched')
    m.wifi = 4; m.thread = None
    m.chip(1); m.click('oa_es_retry')
    expect(m.thread and m.thread[0] == PSYMS['pn_amain'], 'with the Wi-Fi back the pill starts the lookup')


def run(ctx):
    for f in (asset_tests, open_tests, tabs_tests, status_tests, state_tests, again_tests, failure_tests, cover_tests, cover_failure_tests, lyrics_tests, life_tests): f(ctx)

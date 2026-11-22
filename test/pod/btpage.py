"""The own Bluetooth page (patch/btpage.c, tools/pod_ui.py build_bluetooth_page, docs/modules/bluetooth.md "The page") on the real compiled payload under Unicorn, over the control layer (patch/btset.c)
with the Bluetooth backend mocked as test/pod/btset.py mocks it (every stock call recorded with its arguments).

The asset against the Wi-Fi page's numbers; the layout for off, on and starting / scanning with no device, found and paired devices, a scan that ended, a device connecting and connected; names (UTF-8, long, bad
bytes) and the row pools; every tap and the stock call and device it reaches; the 200 ms timer (the count-down, only in front, none under a dialog) and every way the search is stopped; the Audio Codec picker; the
Settings row and the All System Settings hub's row."""
import importlib.util, os, re, struct, sys
import awtk_ui, pod_i18n, pod_pages, pod_settings as ST, pod_ui
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
UI = os.path.join(RAW, 'ui', 'm1plus_bluetooth.bin')
UI_CODEC = os.path.join(RAW, 'ui', 'm1plus_btcodec.bin')
UI_DEV = os.path.join(RAW, 'ui', 'm1plus_btdevice.bin')
BP_MY, BP_OTH = 8, 16   # patch/btpage.c BP_MY, BP_OTH
BP_ROWS = BP_MY + BP_OTH
BP_DEVS = 32
WIN = 0x24500000
TICK = 200


def _btset():
    """The control layer's test machine (test/pod/btset.py), loaded once under its own name."""
    if 'btpage_btset' not in sys.modules:
        spec = importlib.util.spec_from_file_location('btpage_btset', os.path.join(ROOT, 'test', 'pod', 'btset.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['btpage_btset'] = mod
        spec.loader.exec_module(mod)
    return sys.modules['btpage_btset']


BT = _btset()
D = BT.D
MAC = BT.mac


class PM(BT.BM):
    """The page's machine: every call's record kept, the window's widgets by the asset's names, the stock backend mocked."""
    def __init__(self):
        super().__init__()
        self.hist = []
        self.window = self.page_window = WIN
        self.windows = {'m1plus_bluetooth': WIN}
        self.widgets['bluetooth_scrollview'] = self.alloc(0x200)
        for ui in (UI, UI_DEV):
            for w in awtk_ui.parse(open(os.path.join(WORK, ui), 'rb').read()).walk():
                if w.name: Machine.widget(self, w.name)
        self.listing = []

    def call(self, *a, **k):
        r = super().call(*a, **k)
        self.hist += self.calls
        return r

    def _hook(self, u, address, size, _):
        if self.handlers.get(address) == 'handleBluetoothPair':   # a successful unpair takes the device out of the pair list (the show list keeps it, as getSearchResult leaves it until it runs again)
            a0 = u.reg_read(UC_MIPS_REG_A0)
            super()._hook(u, address, size, _)
            if self.pair_ret in (1, 2) and a0 < len(self.shown): self.paired.discard(self.shown[a0])
            return
        if self.handlers.get(address) != 'switchBluetooth': return super()._hook(u, address, size, _)
        was = u.reg_read(UC_MIPS_REG_A0) & 0xff
        super()._hook(u, address, size, _)   # (recorded; stock's own effects follow)
        u.mem_write(D['BT_FLAG'], bytes([int(was == 0)]))
        if was: u.mem_write(D['BT_SEARCHTIME'], b'\0')   # the off path stops the search itself (btStopSearch)
        else: self.setword(D['BT_INITSTATUS'], 1)   # the on path starts the init thread

    def last(self, kind, w, pos=2):
        for c in reversed(self.hist):
            if c[0] == kind and c[1] == w: return c[pos]
        return None

    def text(self, name): return self.last('widget_set_text_utf8', self.widgets[name], 2)
    def image(self, name): return self.last('image_base_set_image', self.widgets[name], 2)
    def visible(self, name): return self.props.get((self.widgets[name], 'visible'), 1)
    def sensitive(self, name): return self.props.get((self.widgets[name], 'sensitive'), 1)
    def y(self, name): return self.props.get((self.widgets[name], 'y'))
    def piece(self, name): return self.props.get((self.widgets[name], 'style:normal:bg_image'))
    def toasts(self): return [e[1] for e in self.log if e[0] == 'toast']
    def stock(self, *names): return [e for e in self.log if e[0] in names]
    def opened_windows(self): return [c[1] for c in self.hist if c[0] == 'window_open']

    def tick(self, n=1):   # the Bluetooth page's own timer (the first one made)
        for _ in range(n): self.call(self.timers[0][0], a0=0, count=20000000)

    def dtick(self, n=1):   # the device page's (the last one made)
        for _ in range(n): self.call(self.timers[-1][0], a0=0, count=20000000)

    def tap(self, name, x=100):
        return self.click(name, count=20000000, x=x)

    def rows(self):
        """(name, check or spinner image or None, info glyph shown, piece, y, slot) of the device rows that are shown, top to bottom."""
        out = []
        for i in range(BP_ROWS):
            if self.visible(f'bt_row{i}'):
                out.append((self.text(f'bt_name{i}'), self.image(f'bt_chk{i}') if self.visible(f'bt_chk{i}') else None, i < BP_MY and bool(self.visible(f'bt_info{i}')),
                            self.piece(f'bt_row{i}'), self.y(f'bt_row{i}'), i))
        return sorted(out, key=lambda r: r[4])

    def slot(self, name): return next(r[5] for r in self.rows() if r[0] == name)


class Fit(PM):
    """The widgets' text and its measure (13 px a character) for az_fit_room and the codec value's fit; `char_w` is the width of a character."""
    char_w = 13.0

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('widget_get_text', 'widget_measure_text'): return super()._hook(u, address, size, _)
        a0, a1 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1))
        if name == 'widget_measure_text':
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', self.char_w * len(self.words_until_zero(a1))))[0])
        else:
            t = next((c[2] for c in reversed(self.hist + self.calls) if c[0] == 'widget_set_text_utf8' and c[1] == a0), '').encode('latin-1').decode('utf-8')
            ret = self.alloc(4 * len(t) + 4); self.u.mem_write(ret, struct.pack(f'<{len(t) + 1}I', *map(ord, t), 0))
            u.reg_write(UC_MIPS_REG_V0, ret)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


PAIRED = [(MAC(1), 'AirPods Pro'), (MAC(2), 'Sony WH-1000XM5')]
OTHERS = [(MAC(3), 'JBL Flip 6'), (MAC(4), 'Living Room TV'), (MAC(5), 'Car Stereo')]


def page(flag=1, paired=(), others=(), linked=(), init=0, conn=0, coding=3, show=0, wifi=0, cls=PM, confirm=True, link=0, search=0, **kw):
    m = cls()
    m.reset(flag=flag, init=init, conn=conn, coding=coding, show=show, wifi=wifi, confirm=confirm, link=link, search=search, **kw)
    m.set_lists(list(paired), list(others))
    m.linked = list(linked)
    return m


def opened(m):
    r = m.call(PSYMS['btpage_open'], count=30000000)
    return struct.unpack('<i', struct.pack('<I', r))[0]


def scan_out(m):
    """Run the timer until the search has ended (49 ticks)."""
    n = 0
    while m.s8(D['BT_SEARCHTIME']) > 0 and n < 80:
        m.tick(1); n += 1
    return n


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the asset

def asset_tests(ctx):
    expect = ctx.expect
    import paths, mod_icons
    from awtk_text import Ttf, StbText
    stock = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), RAW, 'ui', 'systemset', 'bluetooth_page.bin'), 'rb').read())
    wifi = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', 'm1plus_wifi.bin'), 'rb').read())
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    wby = {w.name: w for w in wifi.walk() if w.name}
    page_ = pod_pages.BLUETOOTH_PAGE
    expect(page_ in pod_pages.PAGES and page_.kind == 'bluetooth' and page_.key == 'm1plus_bluetooth' and page_.title == 'Bluetooth' and tree.name == page_.name, 'the page is registered, titled Bluetooth')
    expect(by['label_title'].get('tr_text') == 'Bluetooth' and 'btn_return' in by and 'btn_backtoplayer' in by and 'navigationbar_view' in by, 'the navbar is ours: title, Back, Now Playing')
    sl, ss = (next(w for w in stock.walk() if w.name == n) for n in ('bluetooth_listview', 'bluetooth_scrollview'))
    geo = lambda w: (w.x, w.y, w.w, w.h)
    expect(geo(by['bluetooth_listview']) == geo(sl) == (0, 50, 320, 400) and geo(by['bluetooth_scrollview']) == geo(ss) == (0, 0, 310, 400) and by['bluetooth_listview'].type == sl.type and by['bluetooth_scrollview'].type == ss.type,
           'the list and its scroll view carry stock\'s names and sit where stock\'s do')
    expect(geo(by['scroll_bar_m']) == (310, 0, 10, 400) and by['bluetooth_listview'].get('default_item_height') == str(ST.ROW_H), 'the scroll bar and the list\'s item height')
    names = [c.name for c in by['bluetooth_scrollview'].children]
    want = ['pod_top', 'bt_row_sw', 'bt_row_codec', 'bt_note', 'bt_hdr_my'] + [f'bt_row{i}' for i in range(BP_MY)] + ['bt_hdr_oth'] + [f'bt_row{i}' for i in range(BP_MY, BP_ROWS)] + ['bt_row_search', 'pod_end']
    expect(names == want, f'display order: spacer, switch, codec, note, My Devices, its rows, Other Devices, its rows, Search Again, spacer: {names}')
    expect(pod_ui.BT_MY == BP_MY and pod_ui.BT_OTH == BP_OTH, 'the pools of the asset and of the payload')
    src = open(os.path.join(ROOT, 'patch', 'btpage.c')).read()
    expect(re.search(r'#define BP_MY (\d+)', src).group(1) == str(BP_MY) and re.search(r'#define BP_OTH (\d+)', src).group(1) == str(BP_OTH) and re.search(r'#define BP_DEVS (\d+)', src).group(1) == str(BP_DEVS),
           'the pool sizes are the payload\'s')
    box = lambda n: geo(by[n])
    ax, ay, aw, ah = ST.accessory('switch'); lx, lw = ST.label_box('switch', False)
    expect(box('bt_row_sw') == (0, 0, ST.LIST_W, ST.ROW_H) and box('bt_sw_label') == (lx, 0, lw, ST.ROW_H) and box('bt_sw_img') == (ax, ay, aw, ah) and by['bt_sw_img'].get('image') == 'sset_off'
           and box('bt_row_sw') == (0,) + geo(wby['wf_row_sw'])[1:] and box('bt_sw_img') == geo(wby['wf_sw_img']), 'the switch row is the Wi-Fi page\'s')
    cx, cw = ST.label_box('value', False); vx, vw = ST.value_box(); chx, chy, chw, chh = ST.accessory('chevron')
    expect(box('bt_row_codec') == (0, 0, ST.LIST_W, ST.ROW_H) and box('bt_codec_label') == (cx, 0, cw, ST.ROW_H) and box('bt_codec_val') == (vx, 0, vw, ST.ROW_H) and box('bt_codec_chev') == (chx, chy, chw, chh)
           and by['bt_codec_val'].get('style:normal:text_align_h') == 'right' and by['bt_codec_val'].get('style:normal:font_size') == str(ST.VALUE_PX) and by['bt_codec_val'].get('style:normal:text_color') == ST.GREY
           and by['bt_codec_chev'].get('image') == mod_icons.CARD_CHEVRON[0], 'the codec row: a value row of the Settings pages')
    expect((cx, ST.value_box()[0] + ST.value_box()[1], ST.VALUE_MAX, ST.VALUE_LABEL_GAP) == tuple(int(re.search(rf'#define {n}[\s\\]+(\d+)', src).group(1)) for n in ('BP_LABEL_X', 'BP_VALUE_RIGHT', 'BP_VALUE_MAX', 'BP_VALUE_GAP')),
           'the codec value\'s room is the Settings pages\' (the payload repeats it)')
    for k in range(BP_ROWS):
        want = [(0, 0, ST.LIST_W, ST.ROW_H), (24, 16, 20, 20), (54, 0, 210 if k < BP_MY else 242, ST.ROW_H)]
        if k < BP_MY: want.append((274, 15, 22, 22))
        want.append((24, 51, 286, 1))
        got = [box(f'bt_row{k}'), box(f'bt_chk{k}'), box(f'bt_name{k}')] + ([box(f'bt_info{k}')] if k < BP_MY else []) + [box(f'bt_hair{k}')]
        expect(got == want, f'device row {k}: check (24, 16, 20, 20), name from x 54 ({want[2][2]} px: up to the info glyph, or to the card\'s edge), info glyph (paired only), hairline from x 24: {got}')
        expect(('bt_info%d' % k in by) == (k < BP_MY) and not any(f'bt_lock{k}' in by or f'bt_sig{k}' in by for _ in (0,)), f'row {k}: the info glyph on paired rows only, no lock, no signal')
    expect(all(box(f'bt_chk{k}')[:2] == geo(wby['wf_chk0'])[:2] and box(f'bt_info{k}') == geo(wby['wf_info0']) and box(f'bt_name{k}')[:2] == geo(wby['wf_name0'])[:2] for k in range(BP_MY)), 'the check, name and info glyph are at the Wi-Fi rows\' places')
    expect(box('bt_hdr_my') == (0, 0, ST.LIST_W, 40) == box('bt_hdr_oth') and box('bt_hdr_my_t')[:2] == (24, ST.HDR_LABEL_Y) == box('bt_hdr_oth_t')[:2] and box('bt_hdr_oth_spin')[2:] == (14, 14)
           and by['bt_hdr_oth_spin'].get('image') == 'wf_spin0' and by['bt_hdr_my_t'].get('style:normal:font_size') == '18' and by['bt_hdr_my_t'].get('style:normal:text_color') == '#AAAAAA'
           and 'bt_hdr_my_spin' not in by, 'the headers are the Wi-Fi page\'s: 40 px strips, 18 px grey; the spinner is on Other Devices only')
    expect(box('bt_row_search') == (0, 0, ST.LIST_W, ST.ROW_H) and box('bt_search_label')[0] == 54 and box('bt_search_label') == geo(wby['wf_other_label']) and by['bt_search_label'].get('style') == 'srlabel_leftwhite21_style',
           'Search Again is placed as Other... is on the Wi-Fi page')
    expect(box('bt_note') == (0, 0, ST.LIST_W, ST.NOTE_H) and box('bt_note_t')[:2] == (ST.HDR_X, ST.NOTE_LABEL_Y) and by['bt_note_t'].get('style:normal:font_size') == str(ST.NOTE_PX)
           and by['bt_note_t'].get('style:normal:text_color') == ST.GREY and by['bt_note_t'].get('tr_text') == 'This player is shown as “%s”', 'the note is the cards pages\' note (15 px grey, 34 px)')
    expect(box('pod_top')[3] == ST.CM and box('pod_end')[3] == ST.END_H, 'the spacers are the Settings pages\'')
    st = lambda n, k='style': by[n].get(k)
    expect(all(st(f'bt_row{k}') == 'list_item_style' for k in range(BP_ROWS)) and all(st(f'bt_name{k}') == 'srlabel_leftwhite21_style' for k in range(BP_ROWS)) and st('bt_row_search') == st('bt_row_codec') == 'list_item_style',
           'rows are stock list items with the stock 21 px white labels')
    expect(by['bt_row_sw'].get('style:normal:bg_image') == 'pod_cd_single' and by['bt_row_codec'].get('style:normal:bg_image') == 'pod_cd_bot' and by['bt_row_codec'].get('style:pressed:bg_image') == 'pod_cd_bot_down'
           and by['bt_row3'].get('style:normal:bg_image') == 'pod_cd_mid' and by['bt_row_search'].get('style:pressed:bg_image') == 'pod_cd_bot_down', 'card pieces and their pressed twins')
    expect(by['bt_chk0'].get('image') == 'pod_check' and by['bt_info0'].get('image') == 'wf_info' and all(n in mod_icons.DAILY for n in mod_icons.WIFI_IMAGES), 'the Wi-Fi page\'s images, none added')
    expect([by[n].get('tr_text') for n in ('bt_sw_label', 'bt_codec_label', 'bt_hdr_my_t', 'bt_hdr_oth_t', 'bt_search_label')] == [pod_i18n.key_for(t) for t in ('Bluetooth', 'Audio Codec', 'My Devices', 'Other Devices', 'Search Again')],
           'the texts, in every language (tools/pod_i18n.py)')
    # touch: the rows take every tap, the rest never does; the hidden start state
    rows = ['bt_row_sw', 'bt_row_codec', 'bt_row_search'] + [f'bt_row{k}' for k in range(BP_ROWS)]
    kids = [w for r in rows for w in by[r].children]
    expect(kids and all(w.get('sensitive') == 'false' for w in kids), 'every child of a row is insensitive: the row takes the tap')
    hid = ['bt_row_codec', 'bt_row_search', 'bt_note', 'bt_hdr_my', 'bt_hdr_oth'] + [f'bt_row{k}' for k in range(BP_ROWS)] + ['bt_hdr_oth_spin'] + [f'bt_chk{k}' for k in range(BP_ROWS)]
    expect(all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' for n in hid) and by['bt_row_sw'].get('visible') != 'false' and by['img_nb_fade'].get('visible') == 'false',
           'everything but the switch row starts hidden and insensitive')
    expect(by['pod_top'].get('sensitive') == 'false' and by['pod_end'].get('sensitive') == 'false' and by['bt_note'].get('sensitive') == 'false', 'the spacers and the note are never touch targets')
    # the codec picker's asset and texts
    ct = awtk_ui.parse(open(os.path.join(WORK, UI_CODEC), 'rb').read())
    cp = pod_pages.BTCODEC_PAGE
    expect(pod_pages.PAGES[pod_pages.BTCODEC_PAGE_INDEX] is cp and (cp.key, cp.title) == ('m1plus_btcodec', 'Audio Codec') and ct.find('label_title').get('tr_text') == 'Audio Codec'
           and [(r.label, r.action, r.arg) for r in cp.rows] == [(t, pod_pages.ACT_BTCODECSET, i) for i, t in enumerate(pod_pages.BT_CODECS)] and all(pod_pages.row_kind(r) == 'check' for r in cp.rows)
           and pod_pages.ACT_BTCODECSET == 184 and pod_pages.ACT_BTCODECSET in pod_pages.CHECK_ACTIONS, 'the picker: eight check rows in stock\'s order, action 184')
    expect(all(ct.find(f'pod_check{i}').get('visible') == 'false' and ct.find(f'pod_check{i}').get('sensitive') == 'false' for i in range(8))
           and [ct.find(f'pod_label{i}').get('tr_text') for i in range(8)] == ['LDAC HQ', 'LDAC Standard', 'LDAC Connection', 'btcode_aptxhd', 'btcode_aptx', 'btcode_aac', 'btcode_sbchq', 'btcode_sbc']
           and pod_pages.BT_CODECS == ('LDAC HQ', 'LDAC Standard', 'LDAC Connection', 'aptX HD', 'aptX', 'AAC', 'SBC HQ', 'SBC'), 'a hidden insensitive check each; stock\'s keys for aptX .. SBC, ours for the LDAC choices')
    csrc = re.search(r'bp_codec_text\[8\] = \{([^}]*)\}', src).group(1)
    expect(re.findall(r'"([^"]*)"', csrc) == [ct.find(f'pod_label{i}').get('tr_text') for i in range(8)], 'the page\'s codec value uses the same eight keys as the picker')
    # the texts against their rooms, in every language
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    for loc in pod_i18n.LOCALES:
        w = lambda t, px: StbText(font, px).layout(t)[1]
        tab = pod_i18n.table_for(loc)
        tx = lambda k: pod_i18n.TEXT[k][tab]
        import awtk_strings
        stock_t = dict(awtk_strings.load(os.path.join(WORK, RAW, 'strings', loc + '.bin')))
        codec_texts = [tx(t) if t in pod_i18n.TEXT else stock_t[k] for t, k in zip(pod_pages.BT_CODECS, pod_pages.BT_CODEC_KEYS)]
        lx, lw = ST.label_box('check', False)
        room = ST.value_box()[0] + ST.value_box()[1] + 0 - 24 - ST.VALUE_LABEL_GAP   # 254 px between the label's x and the chevron's gap
        worst = max(w(t, ST.VALUE_PX) for t in codec_texts)
        spin_room = ST.HDR_W - 4 - 8 - 14
        too = ([t for t in codec_texts if w(t, 21) > lw] + (['Audio Codec + the longest codec'] if w(tx('Audio Codec'), 21) + ST.VALUE_LABEL_GAP + min(worst, ST.VALUE_MAX) > room else [])
               + [k for k in ('My Devices',) if w(tx(k), 18) > ST.HDR_W - 4] + [k for k in ('Other Devices',) if w(tx(k), 18) > spin_room] + [k for k in ('Search Again',) if w(tx(k), 21) > pod_ui.WF_NAME_W + 40 - 4]
               + [k for k in ('This player is shown as “%s”',) if w(tx(k).replace('%s', 'Shanling M1 Plus'), ST.NOTE_PX) > ST.HDR_W - 4])
        expect(not too, f'{loc}: the page\'s texts fit their rooms in the built font: {too}')
        expect(all(codec_texts) and stock_t['btcode_aptxhd'] == 'aptX HD' and stock_t['btcode_sbc'] == 'SBC', f'{loc}: the stock codec keys are there')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the layout

def layout_tests(ctx):
    expect = ctx.expect
    # off: the switch row alone, nothing asked of the backend
    m = page(flag=0)
    expect(opened(m) == 0 and ('window_open', 'm1plus_bluetooth') in m.hist and m.timers == [(m.timers[0][0], TICK)] and len(m.timers) == 1, 'the page opens m1plus_bluetooth with one timer of 200 ms')
    expect(m.image('bt_sw_img') == 'sset_off' and m.piece('bt_row_sw') == 'pod_cd_single' and not m.visible('bt_hair_sw') and not m.visible('bt_row_codec') and not m.visible('bt_note') and not m.visible('bt_hdr_my')
           and not m.visible('bt_hdr_oth') and not m.visible('bt_row_search') and m.rows() == [] and m.props[(m.widgets['bluetooth_scrollview'], 'virtual_h')] == 72, 'off: the switch row alone, as a single card')
    expect(not m.stock('btStartSearch', 'getLocalBtName', 'switchBluetooth'), 'off: no search, no name read')
    expect(m.props.get((m.widgets['bt_row_codec'], 'sensitive')) == 0 and m.props.get((m.widgets['bt_row_search'], 'sensitive')) == 0 and m.props[(m.widgets['bt_row_sw'], 'sensitive')] == 1,
           'the hidden rows are insensitive')
    m.tick(30)
    expect(not m.stock('btStartSearch', 'getSearchResult') and m.s8(D['BT_SEARCHTIME']) == 0, 'and the timer starts nothing')
    # on, nothing found yet: a search starts as the page opens
    m = page(flag=1)
    opened(m)
    expect([e[0] for e in m.stock('getLocalBtName', 'btStartSearch')] == ['getLocalBtName', 'btStartSearch'] and m.s8(D['BT_SEARCHTIME']) == 50, 'on: the name is read and a search starts as the page opens (stock\'s page init)')
    expect(m.image('bt_sw_img') == 'sset_on' and m.piece('bt_row_sw') == 'pod_cd_top' and m.visible('bt_hair_sw') and m.visible('bt_row_codec') and m.piece('bt_row_codec') == 'pod_cd_bot'
           and m.y('bt_row_sw') == 10 and m.y('bt_row_codec') == 62, 'on: the switch row tops card 1, the Audio Codec row ends it')
    expect(m.last('widget_set_tr_text', m.widgets['bt_codec_val']) == 'btcode_aptxhd', 'the codec row shows the preferred codec (btcoding 3, aptX HD) by its key')
    expect(m.visible('bt_note') and m.y('bt_note') == 114 and m.text('bt_note_t').encode('latin-1').decode('utf-8') == 'This player is shown as “Player”', f'the note under the card names this player: {m.text("bt_note_t")}')
    expect(not m.visible('bt_hdr_my') and m.visible('bt_hdr_oth') and m.y('bt_hdr_oth') == 148 and m.visible('bt_hdr_oth_spin') and m.image('bt_hdr_oth_spin').startswith('wf_spin')
           and m.props.get((m.widgets['bt_hdr_oth_spin'], 'x')) == 24 + 2 + 76 + 8, 'Other Devices with its spinner after the text (scanning)')
    expect(m.rows() == [] and not m.visible('bt_row_search') and m.props[(m.widgets['bluetooth_scrollview'], 'virtual_h')] == 148 + 40 + 10, 'scanning with nothing found: no card, no Search Again')
    # a search that found devices, still going: one card, no Search Again
    m = page(paired=PAIRED, others=OTHERS)
    opened(m)
    got = m.rows()
    expect([g[0] for g in got] == ['AirPods Pro', 'Sony WH-1000XM5', 'JBL Flip 6', 'Living Room TV', 'Car Stereo'], f'paired first, then the others, in the list\'s order: {[g[0] for g in got]}')
    expect([g[3] for g in got] == ['pod_cd_top', 'pod_cd_bot', 'pod_cd_top', 'pod_cd_mid', 'pod_cd_bot'], f'two cards: My Devices top / bottom, Other Devices top .. bottom: {[g[3] for g in got]}')
    expect([g[4] for g in got] == [188, 240, 332, 384, 436] and m.y('bt_hdr_my') == 148 and m.y('bt_hdr_oth') == 292 and not m.visible('bt_row_search') and m.props[(m.widgets['bluetooth_scrollview'], 'virtual_h')] == 488 + 10,
           f'52 px rows: My Devices header at 148, its rows 188 and 240, Other Devices at 292, its rows from 332 ({[g[4] for g in got]})')
    expect([g[2] for g in got] == [True, True, False, False, False], 'the info glyph on the paired devices only')
    expect(m.visible('bt_hair0') and not m.visible('bt_hair1') and m.visible(f'bt_hair{BP_MY}') and not m.visible(f'bt_hair{BP_MY + 2}'), 'hairlines under every row of a card but its last')
    expect(m.visible('bt_hdr_oth_spin') and all(m.props.get((m.widgets[f'bt_row{g[5]}'], 'sensitive')) == 1 for g in got) and (m.widgets['bt_hdr_my'], 'sensitive') not in m.props, 'the spinner while it searches; shown rows touchable, headers never')
    expect(sorted(g[5] for g in got) == [0, 1, BP_MY, BP_MY + 1, BP_MY + 2], 'paired devices take the first pool, the others the second')
    # the search has ended: Search Again closes the second card
    scan_out(m)
    got = m.rows()
    expect(not m.visible('bt_hdr_oth_spin') and m.visible('bt_row_search') and m.piece('bt_row_search') == 'pod_cd_bot' and m.y('bt_row_search') == 488 and [g[3] for g in got][2:] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_mid']
           and m.visible(f'bt_hair{BP_MY + 2}') and m.props[(m.widgets['bluetooth_scrollview'], 'virtual_h')] == 540 + 10, f'search over: no spinner, Search Again ends the card ({[g[3] for g in got]})')
    # the search ended with no unpaired device: Search Again is the card
    m = page(paired=PAIRED)
    opened(m); scan_out(m)
    expect(m.rows()[-1][4] == 240 and m.visible('bt_row_search') and m.piece('bt_row_search') == 'pod_cd_single' and m.y('bt_row_search') == 332, 'nothing found: Search Again alone in the card')
    # no paired device: no My Devices
    m = page(others=OTHERS)
    opened(m); scan_out(m)
    expect(not m.visible('bt_hdr_my') and m.y('bt_hdr_oth') == 148 and [g[4] for g in m.rows()] == [188, 240, 292] and m.y('bt_row_search') == 344, 'no paired device: no My Devices header, the others from the first header')
    # starting (the init runs): the header and its spinner, no Search Again, no search is begun
    m = page(init=1)
    opened(m)
    expect(not m.stock('btStartSearch') and m.visible('bt_hdr_oth') and m.visible('bt_hdr_oth_spin') and not m.visible('bt_row_search') and m.rows() == [], 'starting: Other Devices with its spinner, nothing to search yet')
    m.u.mem_write(D['BT_INITSTATUS'], bytes(4)); m.setword(D['BT_START_SCAN'], 1)
    m.u.mem_write(D['BT_START_SCAN'], b'\1'); m.u.mem_write(D['BT_REFRESH'], b'\1')
    m.tick(1)
    expect(m.stock('btStartSearch') and m.visible('bt_hdr_oth_spin') and not m.visible('bt_row_search'), 'the init is over (stock\'s idle handler sets the redraw flag and the scan request): the search starts, still no Search Again')
    # connected and connecting devices
    m = page(paired=PAIRED, others=OTHERS, linked=[(3, MAC(1))], show=3)
    opened(m)
    got = {g[0]: g for g in m.rows()}
    expect(got['AirPods Pro'][1] == 'pod_check' and got['Sony WH-1000XM5'][1] is None and got['JBL Flip 6'][1] is None, f'a connected device: the check at the left ({[(k, v[1]) for k, v in got.items()]})')
    m = page(paired=PAIRED, others=OTHERS, linked=[(1, MAC(3))], conn=1)
    opened(m)
    f0 = {g[0]: g for g in m.rows()}['JBL Flip 6'][1]
    m.tick(1)
    f1 = {g[0]: g for g in m.rows()}['JBL Flip 6'][1]
    m.tick(1)
    f2 = {g[0]: g for g in m.rows()}['JBL Flip 6'][1]
    expect(f0 and f0.startswith('wf_spin') and f1.startswith('wf_spin') and f2.startswith('wf_spin') and len({f0, f1, f2}) == 3 and not any(g[1] for g in m.rows() if g[0] != 'JBL Flip 6'), f'a device connecting (unpaired, being paired): a spinner turns where the check goes: {f0} {f1} {f2}')
    # no name: no note
    m = page()
    m.call(PSYMS['btpage_open'], count=30000000)
    m.u.mem_write(D['BT_LOCALNAME'], b'\0'); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.tick(1)
    expect(not m.visible('bt_note') and m.y('bt_hdr_oth') == 114, 'an empty name: the note is hidden and the rows close up')
    m.u.mem_write(D['BT_LOCALNAME'], 'Café 咖啡'.encode() + b'\0'); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.tick(1)
    expect(m.visible('bt_note') and m.text('bt_note_t') == 'This player is shown as “Café 咖啡”'.encode().decode('latin-1'), f'a UTF-8 name: {m.text("bt_note_t")!r}')
    for loc, text in (('zh_CN', '此播放器显示为“Player”'), ('fr_FR', 'Visible sous le nom « Player »')):
        m = page(); m.set_language(loc); opened(m)
        expect(m.text('bt_note_t') == text.encode().decode('latin-1'), f'{loc}: the note in the table\'s words: {m.text("bt_note_t")!r}')
    # every codec on the codec row
    keys = ['LDAC HQ', 'LDAC Standard', 'LDAC Connection', 'btcode_aptxhd', 'btcode_aptx', 'btcode_aac', 'btcode_sbchq', 'btcode_sbc']
    for c in range(8):
        m = page(coding=c); opened(m)
        expect(m.last('widget_set_tr_text', m.widgets['bt_codec_val']) == keys[c], f'btcoding {c}: the value is {keys[c]}')
    m = page(coding=9); opened(m)
    expect(m.last('widget_set_tr_text', m.widgets['bt_codec_val']) == 'LDAC HQ', 'a btcoding out of range reads as 0 (as config_init clamps it)')
    # names: UTF-8, long (cut with an ellipsis to the label's room), bad bytes
    names = ['ElevenChars!', 'Twelve Chars!!', 'A very long headset name that goes on', '咖啡店的蓝牙耳机名字很长很长很长很长很长']
    others = [(MAC(10 + i), n) for i, n in enumerate(names)]
    m = page(paired=[(MAC(1), 'Café ♪'), (MAC(2), 'Sony WH-1000XM5 Black Edition')], others=others, cls=Fit)
    for i in range(BP_ROWS): m.setword(m.widgets[f'bt_name{i}'] + O['W_W'], pod_ui.BT_NAME_W_PAIRED if i < BP_MY else pod_ui.BT_NAME_W_OTHER)
    opened(m); scan_out(m)
    shown = [g[0].encode('latin-1').decode('utf-8') for g in m.rows()]
    expect(shown[0] == 'Café ♪' and shown[1].endswith('…') and shown[1].startswith('Sony WH-1000X') and len(shown[1]) == 15, f'a paired name is cut to its 206 px (13 px a character here): {shown[:2]}')
    expect(shown[2] == 'ElevenChars!' and shown[3] == 'Twelve Chars!!' and shown[4].endswith('…') and len(shown[4]) == 18 and shown[5].endswith('…'), f'another name fits 238 px: whole up to 18 characters, an ellipsis after: {shown[2:]}')
    m = page(others=[(MAC(1), 'a\x01b'), (MAC(2), 'x'.ljust(255, 'y'))])
    opened(m); scan_out(m)
    bad = m.rows()
    expect(bad[0][0] == 'a?b' and len(bad[1][0]) == 255, f'a control character shows as ?, a 255 byte name is read whole: {bad[0][0]!r} {len(bad[1][0])}')
    # the pools: more devices than rows drop the rest; the show list is read up to 32
    paired = [(MAC(i), f'P{i}') for i in range(1, 11)]
    others = [(MAC(100 + i), f'O{i}') for i in range(30)]
    m = page(paired=paired, others=others)
    opened(m); scan_out(m)
    got = m.rows()
    expect([g[0] for g in got[:BP_MY]] == [f'P{i}' for i in range(1, BP_MY + 1)] and [g[0] for g in got[BP_MY:]] == [f'O{i}' for i in range(BP_DEVS - 10)][:BP_OTH] and len(got) == BP_ROWS,
           f'{BP_MY} of 10 paired and {BP_OTH} of the {BP_DEVS - 10} others the list holds are shown ({len(got)} rows)')
    expect(m.visible('bt_row_search') and m.y('bt_row_search') == got[-1][4] + 52 and m.piece('bt_row_search') == 'pod_cd_bot', 'Search Again still ends the second card')
    m = page(paired=[(MAC(i), f'P{i}') for i in range(1, 6)], others=[(MAC(100 + i), f'O{i}') for i in range(4)])
    opened(m); scan_out(m)
    expect(len(m.rows()) == 9 and m.s8(D['BT_SEARCHTIME']) == 0, 'fewer than the pools: each shown, the unused rows hidden')
    expect(not any(m.visible(f'bt_row{i}') for i in range(5, BP_MY)) and not any(m.visible(f'bt_row{i}') for i in range(BP_MY + 4, BP_ROWS)), 'the unused pool rows are hidden')
    expect(all(m.props.get((m.widgets[f'bt_row{i}'], 'sensitive')) == 0 for i in list(range(5, BP_MY)) + list(range(BP_MY + 4, BP_ROWS))), 'and insensitive')
    # a device the page shows and then no longer finds: the next layout drops it
    m = page(paired=PAIRED, others=OTHERS); opened(m); scan_out(m)
    m.set_lists(PAIRED, OTHERS[:2]); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.tick(1)
    expect([g[0] for g in m.rows()][-2:] == ['JBL Flip 6', 'Living Room TV'] and len(m.rows()) == 4, 'a device that left the list is gone at the next layout')
    # to-foreground re-reads everything
    m = page(paired=PAIRED, others=OTHERS); opened(m); scan_out(m)
    m.setword(D['BT_CODING'], 6); m.set_lists(PAIRED[:1], []); m.u.mem_write(D['BT_FLAG'], b'\1')
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.last('widget_set_tr_text', m.widgets['bt_codec_val']) == 'btcode_sbchq' and [g[0] for g in m.rows()] == ['AirPods Pro'], 'back in front: the codec and the devices are read again')
    m.u.mem_write(D['BT_FLAG'], b'\0')
    m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.image('bt_sw_img') == 'sset_off' and m.rows() == [] and not m.visible('bt_row_codec'), 'and Bluetooth turned off elsewhere (the pull-down) shows as off')
    # the window is about to open: the rows are laid out again (the names are cut in the row's style)
    m = page(paired=PAIRED); opened(m); m.hist = []
    m.fire(O['EVT_WINDOW_WILL_OPEN'])
    expect(any(c[0] == 'widget_move' for c in m.hist) and len(m.rows()) == 2, 'EVT_WINDOW_WILL_OPEN lays the rows out again')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the taps

def action_tests(ctx):
    expect = ctx.expect
    # the switch: off to on (stock's call, then the rows), on to off (the search stopped)
    m = page(flag=0); opened(m)
    m.log = []; m.tap('bt_row_sw')
    expect([e[:3] for e in m.stock('switchBluetooth')] == [('switchBluetooth', 0, 1)], f'off -> on: switchBluetooth(0, 1) ({m.log})')
    expect(m.image('bt_sw_img') == 'sset_on' and m.visible('bt_row_codec') and m.visible('bt_hdr_oth_spin') and not m.visible('bt_row_search') and m.rows() == [], 'on: the rows appear, the header spinner turns while the init runs (stock\'s start)')
    m = page(flag=1, paired=PAIRED); opened(m)
    m.log = []; m.tap('bt_row_sw')
    expect([e[:3] for e in m.stock('switchBluetooth')] == [('switchBluetooth', 1, 1)] and m.s8(D['BT_SEARCHTIME']) == 0 and m.image('bt_sw_img') == 'sset_off' and m.rows() == [] and not m.visible('bt_row_codec') and m.piece('bt_row_sw') == 'pod_cd_single',
           'on -> off: switchBluetooth(1, 1), the search is stopped (by stock\'s off path), the page is the switch row alone')
    m = page(flag=0, wifi=1, confirm=False); opened(m); m.log = []
    m.tap('bt_row_sw')
    expect([e[1] for e in m.log if e[0] == 'confirm'] == ['Wi-Fi is turned on. Turn it off first?'] and not m.stock('switchBluetooth') and m.image('bt_sw_img') == 'sset_off', 'Wi-Fi is on: the coexistence question, Cancel changes nothing')
    m.confirm_yes = True; m.log = []; m.tap('bt_row_sw')
    expect([e[:3] for e in m.stock('switchBluetooth')] == [('switchBluetooth', 0, 1)] and not m.stock('wifi_switch'), 'OK: Bluetooth starts, Wi-Fi is left alone')
    m = page(flag=0, init=1); opened(m); m.log = []
    m.tap('bt_row_sw')
    expect(not m.stock('switchBluetooth') and m.toasts() == ['Bluetooth Starting'], 'a tap while the init runs: the toast, nothing else (stock\'s guard)')
    # a device row: bs_link with the device's MAC, stock's index in the list
    paired, others = PAIRED, OTHERS
    for k, (mac, name) in enumerate(paired + others):
        m = page(paired=paired, others=others); opened(m); scan_out(m)
        m.log = []; m.link_ret = 0
        m.tap(f'bt_row{m.slot(name)}', x=100)
        calls = m.stock('btStopSearch', 'handleBluetoothLink')
        expect([e[0] for e in calls] == ['btStopSearch', 'handleBluetoothLink'] and calls[1][1] == k, f'a tap on {name}: the scan stopped, handleBluetoothLink({k}) (its place in the list): {[e[:2] for e in calls]}')
    # the info glyph: a paired device's page opens (no call to stock); a tap left of it is the row's
    m = page(paired=paired, others=others); opened(m); scan_out(m)
    slot = m.slot("Sony WH-1000XM5")
    m.hist = []; m.log = []; m.link_ret = 0
    m.tap(f'bt_row{slot}', x=263)
    expect([e[1] for e in m.stock('handleBluetoothLink')] == [1] and 'm1plus_btdevice' not in m.opened_windows(), 'x 263 on a paired row: handleBluetoothLink(1), no device page')
    for x in (264, 290):
        m = page(paired=paired, others=others); opened(m); scan_out(m)
        slot = m.slot("Sony WH-1000XM5")
        m.hist = []; m.log = []
        m.tap(f'bt_row{slot}', x=x)
        expect(m.opened_windows() == ['m1plus_btdevice'] and not m.stock('handleBluetoothLink', 'btStopSearch'), f'x {x} on a paired row: the device page opens and nothing is sent to stock')
    m = page(paired=paired, others=others); opened(m); scan_out(m)
    slot = m.slot("JBL Flip 6")
    m.hist = []; m.log = []
    m.tap(f'bt_row{slot}', x=290)
    expect([e[1] for e in m.stock('handleBluetoothLink')] == [2], 'an unpaired row has no glyph: the whole row connects')
    # a connected device taps to a disconnect: the toast, the output restore, the rows read again
    m = page(paired=paired, others=others, linked=[(3, MAC(1))], show=3, link=1); opened(m)
    m.log = []; m.link_ret = 1; m.judge = 0
    m.tap(f'bt_row{m.slot("AirPods Pro")}')
    expect(m.toasts() == ['Disconnected'] and [e[0] for e in m.log if e[0] in ('handleBluetoothLink', 'save_start_player')] == ['handleBluetoothLink', 'save_start_player'], f'a connected device: Disconnected ({[e[0] for e in m.log]})')
    # SyncLink answers -1: its toast, and the page keeps its rows
    m = page(paired=paired); opened(m); m.log = []; m.link_ret = -1
    m.tap(f'bt_row{m.slot("AirPods Pro")}')
    expect(m.toasts() == ['Please close SyncLink'] and len(m.rows()) == 2, 'SyncLink over Bluetooth: its toast')
    # ignored while a connect runs, guarded while the init runs
    m = page(paired=paired, others=others, conn=1); opened(m); m.log = []
    m.tap(f'bt_row{m.slot("AirPods Pro")}')
    expect(not m.stock('handleBluetoothLink', 'btStopSearch'), 'a tap while a connect runs: ignored')
    m = page(paired=paired, others=others, init=1); opened(m); m.log = []
    m.tap(f'bt_row{m.slot("AirPods Pro")}')
    expect(not m.stock('handleBluetoothLink') and m.toasts() == ['Bluetooth Starting'], 'a tap while the init runs: the toast')
    # the list changed since it was drawn: the MAC still finds its device
    m = page(paired=paired, others=others); opened(m); scan_out(m)
    slot = m.slot('Sony WH-1000XM5')
    m.set_lists([(MAC(9), 'New')] + paired, others); m.log = []; m.link_ret = 0
    m.tap(f'bt_row{slot}')
    expect([e[1] for e in m.stock('handleBluetoothLink')] == [2], 'the index handed to stock is the one in the list now, not the one drawn')
    # a device that is gone: only the scan stop, the rows are read again
    m = page(paired=paired, others=others); opened(m); scan_out(m)
    slot = m.slot('Car Stereo')
    m.set_lists(paired, others[:2]); m.log = []
    m.tap(f'bt_row{slot}')
    expect(not m.stock('handleBluetoothLink') and [e[0] for e in m.stock('btStopSearch')] and 'Car Stereo' not in [g[0] for g in m.rows()], 'a device that left the list: nothing is called but the scan stop, and its row goes')
    # Search Again: stock's call, the spinner and the row follow
    m = page(paired=paired, others=others); opened(m); scan_out(m)
    expect(m.visible('bt_row_search') and not m.visible('bt_hdr_oth_spin'), 'search over')
    m.log = []; m.tap('bt_row_search')
    expect([e[0] for e in m.stock('btStartSearch')] == ['btStartSearch'] and m.s8(D['BT_SEARCHTIME']) == 50 and not m.visible('bt_row_search') and m.visible('bt_hdr_oth_spin'), 'Search Again: btStartSearch, the spinner is back and the row goes')
    scan_out(m)
    expect(m.visible('bt_row_search') and not m.visible('bt_hdr_oth_spin'), 'and it returns when the search ends')
    m = page(paired=paired, others=others, init=0); opened(m); scan_out(m)
    m.u.mem_write(D['BT_INITSTATUS'], b'\1\0\0\0'); m.log = []
    m.tap('bt_row_search')
    expect(not m.stock('btStartSearch') and m.toasts() == ['Bluetooth Starting'], 'Search Again while the init runs: the toast')
    # the Audio Codec row opens the picker; while the init runs the toast instead
    m = page(); opened(m); m.hist = []
    m.tap('bt_row_codec')
    expect(m.opened_windows() == ['m1plus_btcodec'], f'the Audio Codec row opens its picker: {m.opened_windows()}')
    m = page(init=1); opened(m); m.hist = []; m.log = []
    m.tap('bt_row_codec')
    expect(m.opened_windows() == [] and m.toasts() == ['Bluetooth Starting'], 'while the init runs: the toast, no picker')
    # Back and Now Playing stop the search first
    m = page(paired=paired); opened(m); m.log = []; m.hist = []
    m.tap('btn_return')
    expect([e[0] for e in m.stock('btStopSearch')] and ('navigator_back',) in m.hist and m.s8(D['BT_SEARCHTIME']) == 0, 'Back: the search stops, then the page goes back')
    m = page(paired=paired); opened(m); m.log = []; m.hist = []
    m.tap('btn_backtoplayer')
    expect([e[0] for e in m.stock('btStopSearch')] and ('on_backtoplayer_onclick',) in m.hist and m.s8(D['BT_SEARCHTIME']) == 0, 'Now Playing: the search stops, then stock\'s button')
    # the actions of the control layer that the device page will call stay out of this page's taps
    expect(not any(e[0] in ('handleBluetoothPair', 'adjustA2dpVolume') for e in m.log), 'no forget, no volume from this page (they are the device page\'s)')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the timer and the life

def timer_tests(ctx):
    expect = ctx.expect
    m = page(paired=PAIRED, others=OTHERS); opened(m)
    expect(m.s8(D['BT_SEARCHTIME']) == 50, 'the search runs')
    frames, shown, refreshes, stops = [], [], [], 0
    for t in range(1, 52):
        m.log = []
        m.tick(1)
        frames.append(m.image('bt_hdr_oth_spin')); shown.append(bool(m.visible('bt_hdr_oth_spin')))
        if m.stock('getSearchResult'): refreshes.append(t)
        stops += len(m.stock('btStopSearch'))
    expect(m.s8(D['BT_SEARCHTIME']) == 0 and stops == 1 and refreshes == [25, 49], f'bs_tick counts the search down: 49 ticks, results at 5 s and at the end, one stop (results at {refreshes}, {stops} stops)')
    expect(all(shown[:48]) and not any(shown[48:]) and len(set(frames[:8])) == 8 and frames[0] != frames[1], 'the header\'s spinner turns one frame a tick while it searches and goes when it ends')
    expect(m.visible('bt_row_search'), 'and Search Again is there at the end')
    # only while in front: to-background stops the search and the timer leaves the state alone
    m = page(paired=PAIRED, others=OTHERS); opened(m)
    m.tick(3); n = m.s8(D['BT_SEARCHTIME'])
    m.log = []; m.fire(O['EVT_WINDOW_TO_BG'])
    expect([e[0] for e in m.stock('btStopSearch')] and m.s8(D['BT_SEARCHTIME']) == 0, 'to-background: btStopSearch')
    m.u.mem_write(D['BT_SEARCHTIME'], bytes([30])); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.log = []
    m.tick(5)
    expect(m.s8(D['BT_SEARCHTIME']) == 30 and not m.stock('getSearchResult', 'btStartSearch') and m.u.mem_read(D['BT_REFRESH'], 1)[0] == 1, 'not in front: the timer does nothing (the count-down and the redraw flag are left alone)')
    m.fire(O['EVT_WINDOW_TO_FG'])
    m.log = []; m.tick(2)
    expect(m.s8(D['BT_SEARCHTIME']) == 28, 'back in front: the timer counts again')
    # a change nobody flagged is seen by the tick (Bluetooth switched from the pull-down)
    m = page(paired=PAIRED); opened(m)
    m.u.mem_write(D['BT_FLAG'], b'\0'); m.tick(1)
    expect(m.image('bt_sw_img') == 'sset_off' and m.rows() == [] and not m.visible('bt_row_codec'), 'Bluetooth turned off elsewhere: the next tick shows it off')
    m.u.mem_write(D['BT_FLAG'], b'\1'); m.tick(1)
    expect(m.image('bt_sw_img') == 'sset_on' and m.visible('bt_row_codec') and len(m.rows()) == 2, 'and on again')
    # a connect that ends: the redraw flag stock's idle handler sets makes the page read the state
    m = page(paired=PAIRED, others=OTHERS); opened(m); scan_out(m)
    m.linked = [(3, MAC(2))]; m.setword(D['BT_SHOWCODING'], 3); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.tick(1)
    expect({g[0]: g[1] for g in m.rows()}['Sony WH-1000XM5'] == 'pod_check', 'the redraw flag (a link came up): the check appears')
    m.linked = [(1, MAC(4))]; m.setword(D['BT_CONNECTSTATUS'], 1); m.setword(D['BT_SHOWCODING'], 0); m.u.mem_write(D['BT_REFRESH'], b'\1'); m.tick(1)
    rows = {g[0]: g[1] for g in m.rows()}
    expect(rows['Sony WH-1000XM5'] is None and rows['Living Room TV'].startswith('wf_spin'), 'and a device that starts connecting shows the spinner')
    # the init spinner count-down is bs_tick's; the init end starts the search
    m = page(init=1); opened(m)
    m.setword(D['BT_INITSTATUS'], 1); m.u.mem_write(D['BT_INITTIME'], bytes([5]))
    m.tick(3)
    expect(m.s8(D['BT_INITTIME']) == 2 and m.visible('bt_hdr_oth_spin'), 'starting: bs_tick counts the init\'s spinner down, the header spinner turns')
    # no tick under a dialog of ours: the page's tick returns at once
    sym = PSYMS.get('bs_modal_on')
    if sym:
        m = page(paired=PAIRED); opened(m)
        m.u.mem_write(sym, b'\1'); n = m.s8(D['BT_SEARCHTIME']); m.tick(3)
        expect(m.s8(D['BT_SEARCHTIME']) == n, 'a dialog is up (bs_modal): the tick returns at once')
        m.u.mem_write(sym, b'\0'); m.tick(1)
        expect(m.s8(D['BT_SEARCHTIME']) == n - 1, 'and counts again after it')
    src = open(os.path.join(ROOT, 'patch', 'btpage.c')).read()
    expect(re.search(r'static int bp_tick\(const void \*timer\) \{[^}]*if \(!bp\.fg \|\| bs_modal\(\)\) return RET_REPEAT;', src), 'the tick returns early while the page is not in front or a dialog is up (source)')


def life_tests(ctx):
    expect = ctx.expect
    # every way out of the page stops the search
    def fresh():
        m = page(paired=PAIRED, others=OTHERS); opened(m); m.log = []
        return m
    m = fresh(); m.fire(O['EVT_WINDOW_TO_BG'])
    expect([e[0] for e in m.stock('btStopSearch')] == ['btStopSearch'] and m.s8(D['BT_SEARCHTIME']) == 0, 'to-background stops the search')
    m = fresh(); m.fire(O['EVT_WINDOW_CLOSE'])
    expect([e[0] for e in m.stock('btStopSearch')] == ['btStopSearch'] and m.s8(D['BT_SEARCHTIME']) == 0, 'the window\'s close event stops the search')
    m = fresh()
    fn, ctx_ = m.bound[(WIN, O['EVT_DESTROY'])]
    m.call(fn, a0=ctx_, a1=0, count=200000)
    expect([e[0] for e in m.stock('btStopSearch')] == ['btStopSearch'] and m.s8(D['BT_SEARCHTIME']) == 0 and ('timer_remove', 0x777) in m.hist, 'destroy stops the search and the timer')
    # the page forgets itself and opens again
    m.hist = []; m.timers = []
    expect(opened(m) == 0 and len(m.timers) == 1 and ('window_open', 'm1plus_bluetooth') in m.hist, 'and can open again')
    # a second open leaves the page as it is
    m = fresh()
    expect(opened(m) == 0 and 'window_open' not in [c[0] for c in m.calls], 'a second open leaves the page as it is')
    # a stale destroy of an earlier window leaves a newer page alone
    m = fresh(); fn, ctx_ = m.bound[(WIN, O['EVT_DESTROY'])]
    m.call(fn, a0=0x1234, a1=0, count=20000)
    expect(not m.stock('btStopSearch') and not any(c[0] == 'timer_remove' for c in m.hist[-3:]), 'the end of another window is not this page\'s')
    # a window that will not open: -1, nothing bound, no search begun
    m = page(); m.windows = {'m1plus_bluetooth': 0}
    expect(opened(m) == -1 and not m.timers and not m.stock('btStartSearch') and ('navigator_back',) not in m.hist and not any(c[0] == 'widget_on' for c in m.hist), 'no window: -1, so Settings opens the stock page')
    # an asset that is not ours; a timer that will not start: backed out, -1, no search left running
    m = page(); del m.widgets['bt_row_search']
    expect(opened(m) == -1 and ('navigator_back',) in m.hist and not m.timers and not m.stock('btStartSearch'), 'a wrong asset: back out, -1, no search')
    m = page(); del m.widgets['bt_info3']
    expect(opened(m) == -1 and ('navigator_back',) in m.hist, 'a missing row child: back out, -1')
    m = page(); m.timer_fail = True
    expect(opened(m) == -1 and ('navigator_back',) in m.hist and not m.stock('btStartSearch'), 'no timer: back out, -1, no search begun')
    # events and handlers: bound once each
    m = page(); opened(m)
    for ev in ('EVT_WINDOW_WILL_OPEN', 'EVT_WINDOW_TO_FG', 'EVT_WINDOW_TO_BG', 'EVT_WINDOW_CLOSE', 'EVT_DESTROY'):
        expect((WIN, O[ev]) in m.bound, f'{ev} is bound')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] != PSYMS['m1_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])][0] != PSYMS['m1_on_player'], 'Back and Now Playing stop the search first (their own handlers)')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the Audio Codec picker

def codec_tests(ctx):
    expect = ctx.expect
    P = pod_pages
    ci = P.BTCODEC_PAGE_INDEX

    def picker(**kw):
        m = page(**kw)
        for i in range(8):
            for k in ('pod_row', 'pod_check', 'pod_label'): m.widget(f'{k}{i}')
        m.windows['m1plus_btcodec'] = WIN
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, ci)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        m.hist = list(m.calls)
        return m

    def checks(m):
        out = []
        for i in range(8):
            v = [c[2] for c in m.hist if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out

    for c in range(8):
        m = picker(coding=c)
        expect(('window_open', 'm1plus_btcodec') in m.hist and checks(m) == [int(i == c) for i in range(8)], f'btcoding {c}: the check is on row {c} ({checks(m)})')
    # a tap: stock's Quality choice, then the check moves
    m = picker(coding=3)
    m.log = []; m.click('pod_row6', count=20000000); m.hist += m.calls
    expect([e[:3] for e in m.stock('write_int_config')] == [('write_int_config', 6, 'SYSSET')] and m.stock('write_int_config')[0][3] == 'BTCODING' and [e[1] for e in m.stock('switchBtPriority')] == [6]
           and m.word(D['BT_CODING']) == 6 and checks(m) == [0, 0, 0, 0, 0, 0, 1, 0] and not m.stock('bluetoothLink') and m.u.mem_read(D['BT_REFRESH'], 1)[0] == 1,
           f'a tap on SBC HQ: stock\'s Quality choice (switchBtPriority, BTCODING saved, the redraw flag), the check moves ({m.log})')
    m.log = []; m.click('pod_row6', count=20000000)
    expect(not m.stock('write_int_config', 'switchBtPriority'), 'a tap on the chosen row writes nothing')
    for c in range(8):
        m = picker(coding=(c + 3) % 8)
        m.click(f'pod_row{c}', count=20000000)
        expect(m.word(D['BT_CODING']) == c and [e[1] for e in m.stock('write_int_config')] == [c], f'row {c} sets btcoding {c}')
    # connected: the reconnect question; Cancel leaves the codec and the check, OK reconnects
    m = picker(coding=3, link=1, show=3, linked=[(3, MAC(1))], paired=PAIRED, confirm=False)
    m.log = []; m.click('pod_row0', count=20000000); m.hist += m.calls
    expect([e[1] for e in m.log if e[0] == 'confirm'] == ['Reconnect Bluetooth?'] and m.word(D['BT_CODING']) == 3 and checks(m)[3] == 1 and checks(m)[0] == 0 and not m.stock('write_int_config', 'switchBtPriority', 'bluetoothLink', 'save_stop_player'),
           'connected, the question cancelled: nothing changes and the check stays where it was')
    m.confirm_yes = True; m.log = []; m.click('pod_row0', count=20000000); m.hist += m.calls
    expect(m.word(D['BT_CODING']) == 0 and [e[1] for e in m.stock('bluetoothLink')] == [2] and checks(m)[0] == 1 and checks(m)[3] == 0 and [e[0] for e in m.stock('save_stop_player')], f'OK: the choice is taken and the device connects again ({[e[0] for e in m.log]})')
    # the init guard comes first
    m = picker(coding=3, init=1)
    m.log = []; m.click('pod_row0', count=20000000)
    expect(m.toasts() == ['Bluetooth Starting'] and m.word(D['BT_CODING']) == 3 and not m.stock('write_int_config', 'switchBtPriority'), 'while the init runs: the toast and nothing else')
    # a connect that runs: ignored, the check stays
    m = picker(coding=3, conn=1)
    m.log = []; m.click('pod_row0', count=20000000); m.hist += m.calls
    expect(not m.stock('write_int_config') and checks(m)[3] == 1 and m.word(D['BT_CODING']) == 3, 'a connect running: the choice is ignored')
    # the page's codec row follows after the picker
    m = page(coding=3); opened(m)
    m.setword(D['BT_CODING'], 7); m.fire(O['EVT_WINDOW_TO_FG'])
    expect(m.last('widget_set_tr_text', m.widgets['bt_codec_val']) == 'btcode_sbc', 'back from the picker: the codec row reads the new codec')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the device page

DEV_ROWS = ('bd_nm0', 'bd_nm1', 'bd_row_link', 'bd_gap0', 'bd_row_vol', 'bd_gap1', 'bd_row_forget')
TITLE_W = {w.name: w.w for w in awtk_ui.parse(open(os.path.join(WORK, UI_DEV), 'rb').read()).walk() if w.name in ('label_title', 'bd_name0', 'bd_name1')}


class DM(PM):
    """The page's machine with a link that behaves: a disconnect (answer 1) ends the link, a connect (0 or 2) starts one that has not finished (the idle handler finishes it: the test says when)."""
    def _hook(self, u, address, size, _):
        if self.handlers.get(address) != 'handleBluetoothLink': return super()._hook(u, address, size, _)
        a0 = u.reg_read(UC_MIPS_REG_A0)
        super()._hook(u, address, size, _)
        if self.link_ret == 1:
            self.linked = []; self.setword(D['BT_SHOWCODING'], 0); u.mem_write(D['BT_LINKSTATUS'], b'\0')
        elif self.link_ret in (0, 2) and a0 < len(self.shown):
            self.linked = [(1, self.shown[a0])]; self.setword(D['BT_CONNECTSTATUS'], 1)


class DFit(Fit, DM):
    pass


def devpage(connected=False, joining=False, cls=DM, paired=PAIRED, others=OTHERS, **kw):
    if connected: kw.update(linked=[(3, MAC(1))], show=3, link=1)
    if joining: kw.update(linked=[(1, MAC(1))], conn=1)
    m = page(paired=paired, others=others, cls=cls, **kw)
    opened(m); scan_out(m)
    if cls is DFit:
        for n, w in TITLE_W.items(): m.setword(m.widgets[n] + O['W_W'], w)
        for i in range(BP_ROWS): m.setword(m.widgets[f'bt_name{i}'] + O['W_W'], pod_ui.BT_NAME_W_PAIRED if i < BP_MY else pod_ui.BT_NAME_W_OTHER)
    return m


def dev_open(m, slot_name='AirPods Pro', x=270):
    """Tap the info glyph of that paired device's row."""
    slot = m.slot(slot_name)
    m.hist = []; m.log = []
    m.tap(f'bt_row{slot}', x=x)


def dev_rows(m):
    return sorted(((n, m.y(n)) for n in DEV_ROWS if m.visible(n)), key=lambda r: r[1])


def finish_link(m, mac=None, coding=3):
    """The idle handler's side of a link that finished: the link list, the codec, the link status."""
    m.linked = [(3, mac or MAC(1))]; m.setword(D['BT_CONNECTSTATUS'], 0); m.setword(D['BT_SHOWCODING'], coding); m.u.mem_write(D['BT_LINKSTATUS'], b'\1')


def dev_asset_tests(ctx):
    expect = ctx.expect
    import mod_icons
    from PIL import Image
    from awtk_text import Ttf, StbText
    P = pod_pages
    tree = awtk_ui.parse(open(os.path.join(WORK, UI_DEV), 'rb').read())
    wtree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', 'm1plus_wifiinfo.bin'), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    wby = {w.name: w for w in wtree.walk() if w.name}
    pg = P.BTDEVICE_PAGE
    expect(P.PAGES[-11] is pg and P.PAGES[-12] is P.BTCODEC_PAGE and pg.kind == 'btdevice' and pg.key == 'm1plus_btdevice' and tree.name == pg.name and P.page_index('m1plus_btdevice') == 118 and len(P.PAGES) == 129,
           'the page is registered after the Audio Codec picker: index 118 of 129 (the two Playback Settings sub-pages, the Volume page, the two Update Library pages, Split Genres, the three Card Script pages and Crossfade follow)')
    expect(by['label_title'].get('tr_text') == 'Bluetooth' and 'btn_return' in by and 'btn_backtoplayer' in by and 'navigationbar_view' in by, 'the navbar is ours: Back, Now Playing and a title the payload replaces by the name')
    geo = lambda w: (w.x, w.y, w.w, w.h)
    sv = by['btdevice_scrollview']
    expect(geo(by['btdevice_listview']) == geo(wby['wifiinfo_listview']) and geo(sv) == geo(wby['wifiinfo_scrollview']), 'the list and its scroll view sit where the Wi-Fi info page\'s do')
    names = [c.name for c in sv.children]
    expect(names == ['pod_top', 'bd_nm0', 'bd_nm1', 'bd_row_link', 'bd_gap0', 'bd_row_vol', 'bd_gap1', 'bd_row_forget', 'pod_end'], f'display order: spacer, name lines, Connect, gap, Headset Volume, gap, Forget, spacer: {names}')
    expect(all(geo(by[n]) == geo(wby[m_]) for n, m_ in (('bd_row_link', 'wi_row_forget'), ('bd_row_forget', 'wi_row_forget'), ('bd_gap0', 'wi_gap0'), ('bd_nm0', 'wi_nm0'), ('bd_name0', 'wi_name0'))), 'the rows, the gaps and the name lines have the Wi-Fi info page\'s boxes')
    expect(all(c.get('sensitive') == 'false' for n in ('bd_row_link', 'bd_row_forget') for c in by[n].children) and by['bd_vol_t'].get('sensitive') == 'false', 'the labels are insensitive: the row takes the tap')
    # the Forget row is the Wi-Fi page's Forget row: the same centred 21 px label in the same ink
    prop = lambda n, w=by: tuple(w[n].get(k) for k in ('style:normal:font_size', 'style:normal:text_color', 'style:normal:text_align_h', 'style:normal:text_align_v')) + geo(w[n])[::2]
    expect(prop('bd_forget_t') == prop('wi_forget_t', wby) and prop('bd_link_t')[:1] + prop('bd_link_t')[2:] == prop('wi_forget_t', wby)[:1] + prop('wi_forget_t', wby)[2:] and prop('bd_forget_t')[1] == '#FF6B6B' and prop('bd_link_t')[1] == '#FFFFFF' and prop('bd_forget_t')[2] == 'center', f'Connect and Forget This Device are centred in the ink Forget This Network has: {prop("bd_forget_t")} / {prop("wi_forget_t", wby)}')
    expect([by[n].get('tr_text') for n in ('bd_link_t', 'bd_forget_t', 'bd_vol_t')] == [pod_i18n.key_for(t) for t in ('Connect', 'Forget This Device', 'Headset Volume')], 'the texts, in every language (tools/pod_i18n.py)')
    # the rows' pieces: one card each; the volume row is not a tap target, so its pressed picture is its normal one
    st = lambda n, k: by[n].get(f'style:{k}:bg_image')
    expect(st('bd_row_link', 'normal') == 'pod_cd_single' and st('bd_row_link', 'pressed') == 'pod_cd_single_down' and st('bd_row_forget', 'pressed') == 'pod_cd_single_down'
           and all(st('bd_row_vol', k) == 'pod_cd_single' for k in ('normal', 'over', 'pressed', 'focused', 'disable')), 'single cards; the volume row does not light under a finger')
    # the keys: real buttons with their own images, the pill 38 x 34 centred in a touch area the row's height
    dn, up = by['bd_vol_dn'], by['bd_vol_up']
    expect(dn.type == up.type == 'button' and dn.get('style') == up.get('style') == 'img_btn_style' and (dn.y, dn.h, up.y, up.h) == (0, 52, 0, 52) and dn.w == up.w == 46 and up.x + 4 + 38 == ST.RIGHT and up.x - (dn.x + 46) == 2
           and [dn.get(f'style:{k}:icon') for k in ('normal', 'over', 'pressed')] == ['pod_ic_btvol_dn', 'pod_ic_btvol_dn', 'pod_ic_btvol_dn_down'] and [up.get(f'style:{k}:icon') for k in ('normal', 'over', 'pressed')] == ['pod_ic_btvol_up', 'pod_ic_btvol_up', 'pod_ic_btvol_up_down'],
           f'two buttons at the row\'s right, each with its own normal and pressed image: {geo(dn)} {geo(up)}')
    expect(by['bd_vol_t'].x == 24 and by['bd_vol_t'].x + by['bd_vol_t'].w <= dn.x - 4 and by['bd_vol_t'].get('style') == 'srlabel_leftwhite21_style', 'the label ends before the first key')
    png = lambda n: Image.open(os.path.join(ROOT, 'assets', 'icons', 'png', n + '.png')).convert('RGBA')
    ims = {n: png(n) for n in mod_icons.BT_VOL_IMAGES}
    expect(all(i.size == (38, 34) for i in ims.values()) and all(n in mod_icons.DAILY for n in mod_icons.BT_VOL_IMAGES) and len(mod_icons.BT_VOL_IMAGES) == 4, 'four 38 x 34 images, installed')
    grey = lambda i: all(abs(p[0] - p[1]) < 4 and abs(p[1] - p[2]) < 4 for p in i.getdata() if p[3] > 0)
    expect(all(grey(i) for i in ims.values()), 'neutral greys only: no accent colour')
    body = lambda i: i.getpixel((4, 17))
    expect(body(ims['pod_ic_btvol_dn'])[:3] == (0x3A, 0x3A, 0x3C) and body(ims['pod_ic_btvol_dn_down'])[0] > body(ims['pod_ic_btvol_dn'])[0] and ims['pod_ic_btvol_dn'].getpixel((19, 16))[:3] == (255, 255, 255) and ims['pod_ic_btvol_up'].getpixel((19, 16))[:3] == (255, 255, 255)
           and ims['pod_ic_btvol_up'].getpixel((19, 10))[:3] == (255, 255, 255) and ims['pod_ic_btvol_dn'].getpixel((19, 10))[:3] != (255, 255, 255), 'a dark pill (lighter pressed) with a white minus or plus at its centre (the plus has a vertical stroke, the minus none)')
    # hidden start state: everything but the connect and forget rows hidden and insensitive
    hid = ['bd_nm0', 'bd_nm1', 'bd_row_link', 'bd_gap0', 'bd_row_vol', 'bd_gap1', 'bd_row_forget', 'bd_vol_dn', 'bd_vol_up']
    expect(all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' for n in hid) and by['img_nb_fade'].get('visible') == 'false' and by['pod_top'].get('sensitive') == 'false', 'everything starts hidden and insensitive')
    # the texts against their rooms in every language, in the built font
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    lab_w = by['bd_vol_t'].w
    for loc in pod_i18n.LOCALES:
        w = lambda t, px: StbText(font, px).layout(t)[1]
        tx = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        too = [k for k in ('Connect', 'Disconnect', 'Forget This Device') if w(tx(k), 21) > ST.CARD_W - 2 * ST.PAD] + [k for k in ('Headset Volume',) if w(tx(k), 21) > lab_w - 4]
        expect(not too, f'{loc}: the device page\'s texts fit their rooms (272 px centred, {lab_w - 4} px beside the keys) in the built font: {too}')
        expect(loc == 'en_US' or all(tx(k) != k for k in ('Connect', 'Disconnect', 'Headset Volume', 'Forget This Device')), f'{loc}: translated')


def device_tests(ctx):
    expect = ctx.expect
    # a paired device that is not connected: Connect, then Forget
    m = devpage()
    dev_open(m, 'Sony WH-1000XM5')
    expect(m.opened_windows() == ['m1plus_btdevice'] and m.text('label_title') == 'Sony WH-1000XM5' and len(m.timers) == 2 and m.timers[1][1] == 500, f'the info glyph opens the device page, the navbar says the name, a 500 ms timer: {m.text("label_title")}')
    expect(dev_rows(m) == [('bd_row_link', 10), ('bd_gap0', 62), ('bd_row_forget', 82)] and m.props[(m.widgets['btdevice_scrollview'], 'virtual_h')] == 82 + 52 + 10 and not m.visible('bd_row_vol') and not m.visible('bd_gap1'), f'Connect and Forget in their own cards 20 px apart, no volume: {dev_rows(m)}')
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect' and m.piece('bd_row_link') == 'pod_cd_single' and m.piece('bd_row_forget') == 'pod_cd_single'
           and m.props.get((m.widgets['bd_row_link'], 'sensitive')) == 1 and m.props.get((m.widgets['bd_row_forget'], 'sensitive')) == 1 and m.props.get((m.widgets['bd_link_t'], 'opacity'), 255) == 255, 'the Connect row: its text, a card, touchable, not dimmed')
    expect(m.props.get((m.widgets['bd_row_vol'], 'sensitive')) == 0 and m.props.get((m.widgets['bd_vol_dn'], 'sensitive')) == 0 and m.props.get((m.widgets['bd_vol_up'], 'sensitive')) == 0 and m.props.get((m.widgets['bd_gap1'], 'visible')) == 0
           and m.props.get((m.widgets['bd_vol_dn'], 'visible')) == 0, 'the hidden volume card and its keys are insensitive too')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])] and (m.widgets['bd_row_vol'], O['EVT_CLICK']) not in m.bound and (m.widgets['bd_gap0'], O['EVT_CLICK']) not in m.bound,
           'Back and Now Playing are bound; the volume row and the gaps are not')
    expect(not m.stock('btStartSearch', 'getSearchResult', 'handleBluetoothLink') and m.s8(D['BT_SEARCHTIME']) == 0, 'opening starts nothing and leaves the search stopped (the Bluetooth page stopped it going to the background)')
    # Connect: the device's index in stock's list, then "Connect" dimmed and untouchable while the link is made
    m.log = []; m.link_ret = 0
    m.tap('bd_row_link')
    calls = m.stock('btStopSearch', 'handleBluetoothLink')
    expect([e[0] for e in calls] == ['btStopSearch', 'handleBluetoothLink'] and calls[1][1] == 1, f'Connect: bs_link(mac): handleBluetoothLink(1), the Sony\'s place in the list: {[e[:2] for e in calls]}')
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect' and m.props[(m.widgets['bd_link_t'], 'opacity')] == 153 and m.props[(m.widgets['bd_row_link'], 'sensitive')] == 0 and not m.visible('bd_row_vol'), 'it is connecting: "Connect" dimmed, the row insensitive, read again at once without a tap')
    m.log = []
    m.tap('bd_row_link')
    expect(not m.stock('handleBluetoothLink'), 'a tap on it while connecting does nothing')
    # the link finishes by itself: the timer shows it
    finish_link(m, MAC(2)); m.dtick(1)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect' and m.props[(m.widgets['bd_link_t'], 'opacity')] == 255 and m.props[(m.widgets['bd_row_link'], 'sensitive')] == 1
           and dev_rows(m) == [('bd_row_link', 10), ('bd_gap0', 62), ('bd_row_vol', 82), ('bd_gap1', 134), ('bd_row_forget', 154)] and m.props[(m.widgets['btdevice_scrollview'], 'virtual_h')] == 154 + 52 + 10,
           f'Connecting -> Connected without a tap: Disconnect, the volume card between the gaps: {dev_rows(m)}')
    # the connected device
    m = devpage(connected=True)
    dev_open(m)
    expect(m.text('label_title') == 'AirPods Pro' and m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect' and dev_rows(m) == [('bd_row_link', 10), ('bd_gap0', 62), ('bd_row_vol', 82), ('bd_gap1', 134), ('bd_row_forget', 154)], f'the connected device: Disconnect, Headset Volume, Forget: {dev_rows(m)}')
    # Disconnect: stock's call, its toast, the page stays and says Connect
    m.log = []; m.link_ret = 1; m.judge = 0
    m.tap('bd_row_link')
    expect([e[1] for e in m.stock('handleBluetoothLink')] == [0] and m.toasts() == ['Disconnected'] and ('navigator_back',) not in m.hist, f'Disconnect: handleBluetoothLink(0), the toast, the page stays: {m.toasts()}')
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect' and dev_rows(m) == [('bd_row_link', 10), ('bd_gap0', 62), ('bd_row_forget', 82)] and not m.visible('bd_row_vol') and m.props[(m.widgets['bd_vol_up'], 'sensitive')] == 0,
           'afterwards the row reads Connect and the volume card is gone')
    # SyncLink in the way: the toast, the page keeps its rows
    m = devpage(); dev_open(m, 'Sony WH-1000XM5'); m.log = []; m.link_ret = -1
    m.tap('bd_row_link')
    expect(m.toasts() == ['Please close SyncLink'] and dev_rows(m)[0] == ('bd_row_link', 10) and ('navigator_back',) not in m.hist, 'SyncLink over Bluetooth: its toast, the page stays')
    # a connect that is made by another device is the stock\'s ignored tap
    m = devpage(conn=1, linked=[(1, MAC(4))]); dev_open(m, 'Sony WH-1000XM5'); m.log = []
    m.tap('bd_row_link')
    expect(not m.stock('handleBluetoothLink', 'btStopSearch'), 'while another connect runs the tap is stock\'s ignored one')
    # a device that is connecting when the page opens
    m = devpage(joining=True); dev_open(m)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect' and m.props[(m.widgets['bd_link_t'], 'opacity')] == 153 and m.props[(m.widgets['bd_row_link'], 'sensitive')] == 0 and not m.visible('bd_row_vol'), 'connecting at open: dimmed "Connect", no volume')
    m.log = []; m.tap('bd_row_forget')
    expect(m.stock('handleBluetoothPair') == [] and ('navigator_back',) not in m.hist, 'Forget while a connect runs: stock\'s ignored tap, the page stays')
    # Forget: stock's confirm; Cancel stays, OK unpairs and closes the page
    m = devpage(confirm=False); dev_open(m, 'Sony WH-1000XM5'); m.log = []
    m.tap('bd_row_forget')
    expect([e[1] for e in m.log if e[0] == 'confirm'] == ['unpair?'] and not m.stock('handleBluetoothPair') and ('navigator_back',) not in m.hist and dev_rows(m)[0] == ('bd_row_link', 10), 'Forget: stock\'s question; Cancel changes nothing and the page stays')
    m.confirm_yes = True; m.log = []; m.tap('bd_row_forget')
    expect([e[1] for e in m.stock('handleBluetoothPair')] == [1] and m.toasts() == ['Unpaired'] and [e[0] for e in m.stock('getSearchResult')] and m.hist.count(('navigator_back',)) == 1,
           f'OK: handleBluetoothPair(1), the "Unpaired" toast, the list read again, back to the Bluetooth page ({m.hist.count(("navigator_back",))} back)')
    # a failed unpair (result 0): stays
    m = devpage(); dev_open(m); m.pair_ret = 0; m.log = []; m.confirm_yes = True
    m.tap('bd_row_forget')
    expect(('navigator_back',) not in m.hist and m.toasts() == [], 'an unpair that failed: no toast, the page stays')
    # forgetting the connected device restores the output (stock\'s) and closes
    m = devpage(connected=True); dev_open(m); m.pair_ret = 2; m.confirm_yes = True; m.log = []; m.judge = 0
    m.tap('bd_row_forget')
    expect([e[1] for e in m.stock('handleBluetoothPair')] == [0] and [e[0] for e in m.stock('judge_outputdevice')] and m.hist.count(('navigator_back',)) == 1, 'the connected device: unpaired, the output restored, the page closes')
    # the init guard comes first
    m = devpage(); dev_open(m); m.u.mem_write(D['BT_INITSTATUS'], b'\1\0\0\0'); m.log = []; m.confirm_yes = True
    m.tap('bd_row_forget')
    expect(m.toasts() == ['Bluetooth Starting'] and not m.stock('handleBluetoothPair'), 'while the init runs: stock\'s toast and nothing else')

    # the page opens once; Back goes back, leaving the Bluetooth page to read again
    m = devpage(); dev_open(m); n = len(m.timers)
    m.tap('bt_row0', x=270)   # (AirPods Pro: the first paired row)
    expect(m.opened_windows() == ['m1plus_btdevice'] and len(m.timers) == n, 'a second tap while it is open opens nothing')
    m.hist = []; m.tap('btn_return')
    expect(('navigator_back',) in m.hist and not m.stock('btStopSearch'), 'Back: the page goes back (the search is already stopped)')
    m.hist = []; m.tap('btn_backtoplayer')
    expect(('on_backtoplayer_onclick',) in m.hist, 'Now Playing: stock\'s button')


def devlife_tests(ctx):
    expect = ctx.expect
    # the refresh on to-foreground and the slow timer; the page never runs the search's tick and leaves the redraw flag alone
    m = devpage(); bt_fg = m.bound[(WIN, O['EVT_WINDOW_TO_FG'])]
    dev_open(m, 'Sony WH-1000XM5')
    m.u.mem_write(D['BT_REFRESH'], b'\1'); m.u.mem_write(D['BT_SEARCHTIME'], bytes([30])); m.log = []
    m.dtick(4)
    expect(m.u.mem_read(D['BT_REFRESH'], 1)[0] == 1 and m.s8(D['BT_SEARCHTIME']) == 30 and not m.stock('getSearchResult', 'btStartSearch', 'btStopSearch'), 'the timer reads the list only: no count-down, no search, the redraw flag the Bluetooth page waits for is left set')
    finish_link(m, MAC(2)); m.u.mem_write(D['BT_REFRESH'], b'\0')
    m.dtick(1)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect' and m.visible('bd_row_vol'), 'a link made from the other side shows without a tap')
    sig = len(m.hist); m.dtick(3)
    expect(not any(c[0] in ('widget_move', 'widget_set_visible', 'widget_set_prop_str') for c in m.hist[sig:]), 'an unchanged state is not laid out again')
    # to-background: the timer rests; to-foreground reads again at once
    fg, bg = m.bound[(WIN, O['EVT_WINDOW_TO_FG'])], m.bound[(WIN, O['EVT_WINDOW_TO_BG'])]
    m.call(bg[0], a0=bg[1], a1=0)
    m.linked = []; m.setword(D['BT_SHOWCODING'], 0); m.u.mem_write(D['BT_LINKSTATUS'], b'\0'); m.log = []
    m.dtick(3)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect' and m.visible('bd_row_vol'), 'not in front: the timer does nothing')
    m.call(fg[0], a0=fg[1], a1=0)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect' and not m.visible('bd_row_vol'), 'back in front: everything is read again')
    # no read under a dialog of ours
    sym = PSYMS.get('bs_modal_on')
    expect(sym is not None, 'the dialog flag is a symbol of the payload')
    if sym:
        m.u.mem_write(sym, b'\1'); finish_link(m, MAC(2)); m.dtick(3)
        expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect', 'a dialog is up (bs_modal): the timer returns at once')
        m.log = []; m.tap('bd_row_link'); m.tap('bd_row_forget'); m.tap('bd_vol_dn')
        expect(not m.stock('handleBluetoothLink', 'handleBluetoothPair', 'adjustA2dpVolume'), 'and the taps do nothing')
        m.u.mem_write(sym, b'\0'); m.dtick(1)
        expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect', 'after it the timer reads again')
    # the Bluetooth page reads again when this one returns: the connected check shows
    m.hist = []; bt_fg_fn, bt_fg_ctx = bt_fg
    m.call(bt_fg_fn, a0=bt_fg_ctx, a1=0)
    expect({g[0]: g[1] for g in m.rows()}['Sony WH-1000XM5'] == 'pod_check', 'the Bluetooth page, in front again, shows the new link')
    # the device vanished: Bluetooth turned off from the Control Center, or the device left the list
    m = devpage(); dev_open(m)
    m.u.mem_write(D['BT_FLAG'], b'\0'); m.hist = []; m.dtick(1)
    expect(m.hist.count(('navigator_back',)) == 1, 'Bluetooth off under the page: it closes')
    m.dtick(2)
    expect(m.hist.count(('navigator_back',)) == 1, 'and only once')
    m = devpage(); dev_open(m)
    m.set_lists([PAIRED[1]], OTHERS); m.hist = []; m.dtick(1)
    expect(m.hist.count(('navigator_back',)) == 1, 'the device left the list: it closes')
    m = devpage(); dev_open(m)
    m.set_lists([], [PAIRED[0]] + OTHERS); m.hist = []; m.dtick(1)
    expect(m.hist.count(('navigator_back',)) == 1, 'no longer paired (forgotten elsewhere): it closes')
    m = devpage(); dev_open(m); m.hist = []
    m.u.mem_write(D['BT_FLAG'], b'\0'); m.call(m.bound[(WIN, O['EVT_WINDOW_TO_FG'])][0], a0=0, a1=0)
    expect(m.hist.count(('navigator_back',)) == 1, 'and on to-foreground too')
    # a device that left the list between the row's draw and the glyph tap: no page, the rows read again
    m = devpage(); slot = m.slot('Sony WH-1000XM5'); m.set_lists([PAIRED[0]], OTHERS); m.hist = []; m.log = []
    m.tap(f'bt_row{slot}', x=270)
    expect(m.opened_windows() == [] and 'Sony WH-1000XM5' not in [g[0] for g in m.rows()], 'a device that is gone has no page: the Bluetooth page lays itself out again')
    # destroy: the timer is removed, the state cleared, the page can open again; a stale destroy leaves a newer page alone
    m = devpage(); dev_open(m)
    fn, ctx_ = m.bound[(WIN, O['EVT_DESTROY'])]
    m.hist = []; m.call(fn, a0=0x1234, a1=0, count=20000)
    expect(not any(c[0] == 'timer_remove' for c in m.hist), 'the end of another window is not this page\'s')
    m.call(fn, a0=ctx_, a1=0, count=200000)
    expect(('timer_remove', 0x777) in m.hist, 'destroy removes the timer')
    m.timers = m.timers[:1]; m.hist = []; m.tap('bt_row0', x=270)
    expect(m.opened_windows() == ['m1plus_btdevice'] and len(m.timers) == 2, 'and the page opens again')
    # an asset that is not ours, a timer that will not start, a window that will not open
    m = devpage(); del m.widgets['bd_vol_up']; dev_open(m)
    expect(('navigator_back',) in m.hist and len(m.timers) == 1, 'a wrong asset: back out, no timer')
    m = devpage(); m.timer_fail = True; dev_open(m)
    expect(('navigator_back',) in m.hist, 'no timer: back out')
    m = devpage(); m.windows['m1plus_btdevice'] = 0; dev_open(m)
    expect(('navigator_back',) not in m.hist and len(m.timers) == 1 and len(m.rows()) == 5, 'no window: nothing happens, the Bluetooth page stays')
    # events bound once each
    m = devpage(); dev_open(m)
    expect(all((WIN, O[ev]) in m.bound for ev in ('EVT_WINDOW_TO_FG', 'EVT_WINDOW_TO_BG', 'EVT_DESTROY')), 'the window\'s events are bound')
    src = open(os.path.join(ROOT, 'patch', 'btpage.c')).read()
    expect(re.search(r'static int bd_tick\(const void \*timer\) \{[^}]*if \(!bd\.fg \|\| bs_modal\(\)\) return RET_REPEAT;', src) and 'bs_tick(' not in src[src.index('the device page\n'):src.index('static int bp_on_dev(')], 'the device page\'s timer returns early while behind or under a dialog, and never calls bs_tick (source)')


def devvol_tests(ctx):
    expect = ctx.expect
    # the volume card: shown only for the connected device and while the volume can be set
    m = devpage(connected=True); dev_open(m)
    expect(m.visible('bd_row_vol') and m.props[(m.widgets['bd_vol_dn'], 'sensitive')] == 1 and m.props[(m.widgets['bd_vol_up'], 'sensitive')] == 1 and m.props[(m.widgets['bd_vol_dn'], 'visible')] == 1 and m.props[(m.widgets['bd_row_vol'], 'sensitive')] == 1
           and m.piece('bd_row_vol') is None, 'the connected device: the Headset Volume card, its keys visible and touchable')
    expect(m.bound[(m.widgets['bd_vol_dn'], O['EVT_CLICK'])][0] != m.bound[(m.widgets['bd_vol_up'], O['EVT_CLICK'])][0], 'each key has its own handler')
    m.log = []; m.tap('bd_vol_dn')
    expect([e[:2] for e in m.stock('adjustA2dpVolume')] == [('adjustA2dpVolume', 0)] and not m.toasts(), 'the minus key: adjustA2dpVolume(0), one step')
    m.log = []; m.tap('bd_vol_up')
    expect([e[:2] for e in m.stock('adjustA2dpVolume')] == [('adjustA2dpVolume', 1)], 'the plus key: adjustA2dpVolume(1)')
    m.log = []; m.tap('bd_vol_up'); m.tap('bd_vol_up')
    expect(len(m.stock('adjustA2dpVolume')) == 2, 'one step per tap')
    expect(dev_rows(m)[2] == ('bd_row_vol', 82), 'the card stays')
    # the conditions of adjustA2dpVolume, one by one
    for what, edit in (('no link', lambda m: m.u.mem_write(D['BT_LINKSTATUS'], b'\0')), ('the codec not known yet', lambda m: m.setword(D['BT_SHOWCODING'], 0)),
                       ('a receiver page', lambda m: m.setword(D['BT_RECV_PAGE'], 1))):
        m = devpage(connected=True); dev_open(m)
        edit(m); m.dtick(1)
        expect(not m.visible('bd_row_vol') and m.props[(m.widgets['bd_vol_dn'], 'sensitive')] == 0 and m.props[(m.widgets['bd_vol_up'], 'sensitive')] == 0, f'{what}: the volume card is hidden and its keys insensitive')
        m.log = []
        m.tap('bd_vol_up')
        expect(not m.stock('adjustA2dpVolume'), f'{what}: a key tap (a stale one) calls nothing')
        undo = {'no link': lambda: m.u.mem_write(D['BT_LINKSTATUS'], b'\1'), 'the codec not known yet': lambda: m.setword(D['BT_SHOWCODING'], 3), 'a receiver page': lambda: m.setword(D['BT_RECV_PAGE'], 0)}[what]
        undo(); m.dtick(1)
        expect(m.visible('bd_row_vol'), f'{what}: and it returns when the condition does')
    # another device is the connected one: no volume for this device
    m = devpage(connected=True); dev_open(m, 'Sony WH-1000XM5')
    expect(not m.visible('bd_row_vol') and m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Connect', 'not the connected device: no volume card, Connect')
    # an unpaired device that is connected is not a page of ours (its row has no glyph)
    # the init guard
    m = devpage(connected=True); dev_open(m); m.u.mem_write(D['BT_INITSTATUS'], b'\1\0\0\0'); m.log = []
    m.tap('bd_vol_up')
    expect(m.toasts() == ['Bluetooth Starting'] and not m.stock('adjustA2dpVolume'), 'while the init runs: stock\'s toast, no step')
    # the keys at the pressed state need no payload: the buttons draw their own pressed image
    m = devpage(connected=True); dev_open(m)
    expect(not any(c[0] == 'widget_set_prop_str' and c[1] in (m.widgets['bd_vol_dn'], m.widgets['bd_vol_up']) for c in m.hist), 'the payload does not restyle the keys')


def devname_tests(ctx):
    expect = ctx.expect
    from_ = lambda raw: raw.encode('utf-8').decode('latin-1')
    def named(name):
        m = devpage(cls=DFit, paired=[(MAC(1), name), PAIRED[1]])
        m.hist = []; m.log = []; m.tap('bt_row0', x=270)
        kids = [n for n in DEV_ROWS if m.visible(n)]
        hs = [m.props.get((m.widgets[n], 'h'), 20 if 'gap' in n or 'nm' in n else 52) for n in kids]
        expect([m.y(n) for n in kids] == [10 + sum(hs[:k]) for k in range(len(kids))], f'{name[:20]}: the rows are stacked by their heights (a stock relayout moves nothing): {[(n, m.y(n)) for n in kids]} {hs}')
        return m, [m.text(f'bd_name{i}') for i in range(2) if m.visible(f'bd_nm{i}')], [m.y(f'bd_nm{i}') for i in range(2) if m.visible(f'bd_nm{i}')], [m.y(n) for n in ('bd_row_link', 'bd_row_forget')]
    m, lines, ys, rows = named('FifteenChars!!!')
    expect(m.text('label_title') == 'FifteenChars!!!' and lines == [] and rows == [10, 82], f'a name the title holds (202 px: 15 characters of 13 px): no name line: {m.text("label_title")} {lines} {rows}')
    m, lines, ys, rows = named('TwentyCharactersLong')
    expect(m.text('label_title') == from_('TwentyCharacte…') and lines == ['TwentyCharactersLong'] and ys == [10] and rows == [38, 110], f'a cut title: the whole name in one line, the cards 28 px lower: {m.text("label_title")} {lines} {ys} {rows}')
    m, lines, ys, rows = named('Sony WH-1000XM5 Black Edition')
    expect(lines == ['Sony WH-1000XM5 Black', 'Edition'] and ys == [10, 30] and rows == [58, 130], f'a name longer than a line: two lines, broken at a space: {lines} {ys} {rows}')
    expect(m.props[(m.widgets['btdevice_scrollview'], 'virtual_h')] == 130 + 52 + 10, 'and the list is as long as its rows')
    m, lines, ys, rows = named('咖啡店的蓝牙耳机名字很长很长很长很长很长')
    expect(m.text('label_title') == from_('咖啡店的蓝牙耳机名字很长很长…') and lines == [from_('咖啡店的蓝牙耳机名字很长很长很长很长很长')] and rows == [38, 110], f'a non-ASCII name (one 13 px cell a character): UTF-8 in the title and the line: {m.text("label_title")!r} {lines} {rows}')
    m, lines, ys, rows = named('Café ♪')
    expect(m.text('label_title') == from_('Café ♪') and lines == [], 'a short non-ASCII name is whole')
    long = ('Bluetooth Headset ' * 14)[:250]
    m, lines, ys, rows = named(long)
    expect(len(lines) == 2 and lines[1].endswith(from_('…')) and ys == [10, 30] and rows == [58, 130] and m.hist.count(('navigator_back',)) == 0, f'a 250 character name: two lines, the second cut with an ellipsis: {lines}')
    m, lines, ys, rows = named('a\x01b')
    expect(m.text('label_title') == 'a?b', f'a control character shows as ?: {m.text("label_title")!r}')
    m = devpage(cls=DFit, paired=[(MAC(1), 'x'.ljust(255, 'y')), PAIRED[1]]); m.hist = []; m.tap('bt_row0', x=270)
    expect(m.opened_windows() == ['m1plus_btdevice'] and m.text('label_title').endswith(from_('…')), 'a 255 byte name opens the page, its title cut')
    # the page opens before stock resolves the styles (EVT_WINDOW_WILL_OPEN): a name measured in the default style's smaller font (12 px a character here) fits the title at open,
    # and is fitted again from the whole name in the title's style when the window is about to open: the title cut, the whole name in the line, the cards lower
    m = devpage(cls=DFit, paired=[(MAC(1), 'Sixteen Chars!!!'), PAIRED[1]]); m.char_w = 12.0
    m.hist = []; m.log = []; m.tap('bt_row0', x=270)
    early = (m.text('label_title'), m.visible('bd_nm0'), m.y('bd_row_link'))
    m.char_w = 13.0
    m.fire(O['EVT_WINDOW_WILL_OPEN'])
    late = (m.text('label_title'), m.visible('bd_nm0') and m.text('bd_name0'), m.y('bd_row_link'), m.y('bd_row_forget'))
    expect(early == ('Sixteen Chars!!!', 0, 10) and late == (from_('Sixteen Chars!…'), 'Sixteen Chars!!!', 38, 110),
           f'a name that fits at open in the default style is fitted again in the title\'s style when the window is about to open: {early} -> {late}')
    m.fire(O['EVT_WINDOW_WILL_OPEN'])
    expect(m.text('label_title') == from_('Sixteen Chars!…') and m.text('bd_name0') == 'Sixteen Chars!!!', 'a second fit starts from the whole name, not the cut title')
    # the page is keyed by the MAC: the list changes under it and the page still follows the same device
    m = devpage(); dev_open(m, 'Sony WH-1000XM5')
    m.set_lists([(MAC(9), 'New Device')] + PAIRED, OTHERS); finish_link(m, MAC(2)); m.log = []
    m.dtick(1)
    expect(m.last('widget_set_tr_text', m.widgets['bd_link_t']) == 'Disconnect', 'the list gained a device in front: the page still follows the Sony by its MAC')
    m.log = []; m.link_ret = 1
    m.tap('bd_row_link')
    expect([e[1] for e in m.stock('handleBluetoothLink')] == [2], 'and the index handed to stock is the one it has now (2), not the one the row had (1)')
    m.log = []; m.confirm_yes = True; m.tap('bd_row_forget')
    expect([e[1] for e in m.stock('handleBluetoothPair')] == [2], 'Forget too')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the entries

def settings_tests(ctx):
    expect, P = ctx.expect, pod_pages
    rows = P.SETTINGS_PAGE.rows
    bt = [r for r in rows if r.label == 'Bluetooth']
    expect(len(bt) == 1 and bt[0].action == P.ACT_STOCK and bt[0].arg == P.STOCK_BLUETOOTH == 1 and P.STOCK_PAGES[1][0] == 'systemset/bluetooth_page' and P.row_kind(bt[0]) == 'value',
           'Settings > Bluetooth is still the stock row (its value shows On / Off), arg 1')
    src = open(os.path.join(ROOT, 'patch', 'm1plus.c')).read()
    expect(re.search(r'row->arg == 1 /\* STOCK_BLUETOOTH \*/ && pd_open_page\("m1plus_bluetooth_page", btpage_open, 0\)\)\s*return RET_OK;[^\n]*\n[\s\S]{0,400}?m1_open_stock\(\s*POD_STOCK\[row->arg\]\.name,\s*POD_STOCK\[row->arg\]\.window\)', src),
           'the row opens our page first, and the stock page where it will not open')
    expect(not any(k.startswith('ACT_') and ('BTPAGE' in k or k == 'ACT_BT') for k in vars(P)) and P.ACT_BTCODECSET == 184,
           'one action id was added: 184, the picker\'s row')

    def row_machine(window=True):
        m = page()
        if not window: m.windows = {'m1plus_bluetooth': 0}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row1')); m.setword(row + 4, P.ACT_STOCK); m.setword(row + 8, 1)
        m.call(PSYMS['on_row'], a0=row, count=30000000)
        return m
    m = row_machine()
    expect(('window_open', 'm1plus_bluetooth') in m.hist and not [c for c in m.hist if c[0] == 'navigator_to'] and m.timers, 'the row opens our page, not stock\'s')
    m = row_machine(window=False)
    expect([c for c in m.hist if c[0] == 'navigator_to'] == [('navigator_to', 'systemset/bluetooth_page')] and not m.timers, 'a page that will not open: stock\'s page, by stock\'s navigator_to')
    # the All System Settings hub's row (payload hook 32, tools/pod.py BTHUB_SITE)
    NAME = 'systemset/bluetooth_page'
    stock_demo, built = stock_demo_bytes(), built_demo_bytes()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site = pod.BTHUB_SITE
    expect(site == 0x4b1428 and w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['bt_hub_open'],
           'the build replaced stock\'s `jalr t9` (navigator_to) at 0x4b1428 by `jal bt_hub_open`')
    pins = [(a, old) for a, old, what in pod.SETTINGS_PINS if 0x4b1408 <= a <= 0x4b1430]
    expect(len(pins) == 8 and all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old in pins) and w(built, site + 4) == 0x24848f00,
           'the thunk\'s prologue, GOT loads, the delay slot (a0 = "systemset/bluetooth_page") and the result are stock\'s')
    expect(MANIFEST['hook_bthub'] == {'addr': site, 'target': PSYMS['bt_hub_open']} and site != pod.WIFIHUB_SITE, 'the manifest records the hook')

    def hub(kill=False, bad=False):
        m = page()
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        if bad: m.windows = {'m1plus_bluetooth': 0}
        r = m.call(PSYMS['bt_hub_open'], a0=m.cstr(NAME), count=30000000)
        return m, struct.unpack('<i', struct.pack('<I', r))[0]
    m, r = hub()
    expect(r == 0 and ('window_open', 'm1plus_bluetooth') in m.hist and not [c for c in m.hist if c[0] == 'navigator_to'], 'the hub row opens our page, without the stock one')
    m, r = hub(kill=True)
    expect(('window_open', 'm1plus_bluetooth') not in m.hist and [c for c in m.hist if c[0] == 'navigator_to'] == [('navigator_to', NAME)] and not m.timers, 'with the kill switch the stock page opens, nothing of ours')
    m, r = hub(bad=True)
    expect([c for c in m.hist if c[0] == 'navigator_to'] == [('navigator_to', NAME)] and not m.timers, 'a page that will not open leaves stock\'s call, with its argument')


SECTIONS = [asset_tests, layout_tests, action_tests, timer_tests, life_tests, codec_tests, dev_asset_tests, device_tests, devlife_tests, devvol_tests, devname_tests, settings_tests]

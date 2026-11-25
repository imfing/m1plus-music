"""Settings > Network Services and Wi-Fi Transfer (patch/netservice.c, docs/modules/wifi-transfer.md): our pages for stock's Network Service page and its Wi-Fi file transfer page. The state is stock's own (the bytes airplayflag,
dlnaflag, wifitransport_flag); the tests run stock's own click handlers (0x4a8a84 AirPlay, 0x4a8b14 DLNA), key filter (0x4b14d0) and close handler (0x4b14ec) under the emulator beside ours and compare the bytes and the calls.
The page opens (a tap on the Wi-Fi Transfer row with and without a network, then the calls of the open) and every way it goes are driven through the handlers the payload bound."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

AIR, DLNA, WTF = (pod.DATA[n][0] for n in ('AIRPLAY_FLAG', 'DLNA_FLAG', 'WIFITRANSPORT_FLAG'))
CLICK_DLNA, CLICK_AIR, KEYFILTER, CLOSE_H = 0x4a8b14, 0x4a8a84, 0x4b14d0, 0x4b14ec
SW_CALLS = ('airplay_switch', 'dlna_switch', 'switch_wifitransport', 'stop_player')


class NS(Machine):
    """Stock's switch functions and the file server's are modelled: the two switches flip their byte, switch_wifitransport(n) sets / clears its byte; every call is recorded."""
    def __init__(self, net=1, air=0, dlna=0, ip=b'192.168.100.100'):
        super().__init__()
        self.net, self.ip = net, ip
        self.u.mem_write(AIR, bytes([air])); self.u.mem_write(DLNA, bytes([dlna])); self.u.mem_write(WTF, b'\0')

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in SW_CALLS: return super()._hook(u, address, size, _)
        a0 = u.reg_read(UC_MIPS_REG_A0)
        if name in ('airplay_switch', 'dlna_switch'):
            at = AIR if name == 'airplay_switch' else DLNA
            self.calls.append((name,)); self.u.mem_write(at, bytes([self.u.mem_read(at, 1)[0] ^ 1]))
        elif name == 'switch_wifitransport':
            self.calls.append((name, a0)); self.u.mem_write(WTF, bytes([1 if a0 else 0]))
        else: self.calls.append((name,))
        u.reg_write(UC_MIPS_REG_V0, 1); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]
    def seen(self): return [c for c in self.calls if c[0] in SW_CALLS]


def state_tests(ctx):
    """The two switches against stock's click handlers, the toasts, the address text, the pins."""
    expect = ctx.expect
    expect(pod.DATA['WIFITRANSPORT_FLAG'][0] == 0xa05abc and pod.FUNCTIONS['switch_wifitransport'][2] == 0x5075e4 and pod.FUNCTIONS['stop_player'][2] == 0x4e08c4, 'the server byte and its two functions are stock\'s (pinned addresses)')
    m0 = Machine()
    expect(all(m0.word(a) == w for a, w, _ in pod.NETSERVICE_PINS) and len(pod.NETSERVICE_PINS) > 40, f'every pinned stock word is demo\'s ({len(pod.NETSERVICE_PINS)} pins)')
    pins = {a for a, _, _ in pod.NETSERVICE_PINS}
    expect({0x4b1710, 0x4b1720, 0x4b1730, 0x4b16ac, 0x4b16cc, 0x4b14d8, 0x4b1508, 0x507600, 0x507670, 0x4cd7f8, 0x4ce670, 0x4a8ac8, 0x4a8b58, 0x4a8c50} <= pins, 'the init\'s calls and binds, both handlers, the server\'s two paths, the readers of the byte and the click handlers are pinned')
    # AirPlay and DLNA: from every state, stock's click handler and ours leave the same bytes and make the same switch call
    for air, dlna in ((0, 0), (1, 0), (0, 1), (1, 1)):
        for name, click, tog, at in (('AirPlay', CLICK_AIR, 'ns_airplay_toggle', AIR), ('DLNA', CLICK_DLNA, 'ns_dlna_toggle', DLNA)):
            ms = NS(air=air, dlna=dlna); ms.widget('img0'); ms.widget('img1'); ms.call(click, a0=ms.window, count=3000000)
            mo = NS(air=air, dlna=dlna); r = mo.call(PSYMS[tog], count=3000000)
            expect((ms.byte(AIR), ms.byte(DLNA)) == (mo.byte(AIR), mo.byte(DLNA)) and ms.seen() == mo.seen() and r == mo.byte(at) and len(ms.seen()) == 1,
                   f'{name} from ({air}, {dlna}): stock\'s click and ours leave ({mo.byte(AIR)}, {mo.byte(DLNA)}), one {mo.seen()}, answer {r}')
            expect(mo.call(PSYMS['ns_airplay' if name == 'AirPlay' else 'ns_dlna']) == mo.byte(at), f'{name}: the shown state is the byte')
    expect(not any(c[0] in ('airplayGetFlag',) for c in mo.calls), 'no AirPlay-playing guard: stock\'s page has none')
    # the toast: on without Wi-Fi says why; off, or on with Wi-Fi, says nothing
    for net, air, want in ((0, 0, ['Connect to Wi-Fi first']), (0, 1, []), (1, 0, []), (1, 1, [])):
        m = NS(net=net, air=air); m.call(PSYMS['ns_airplay_toggle'], count=3000000)
        expect(toasts(m) == want, f'AirPlay, Wi-Fi {net}, from {air}: toast {toasts(m)}')
    m = NS(net=0, dlna=0); m.call(PSYMS['ns_dlna_toggle'], count=3000000)
    expect(toasts(m) == ['Connect to Wi-Fi first'] and m.byte(DLNA) == 1, 'DLNA on without Wi-Fi: the byte is stored (a preference) and the toast says why')
    # the Wi-Fi Transfer row: stock's click asks networkGetConnectStatus (nonzero opens); ours opens above 0
    for net, want, toast in ((0, 0, ['Connect to Wi-Fi first']), (1, 1, []), (2, 1, [])):
        m = NS(net=net); r = m.call(PSYMS['ns_transfer_ok'], count=3000000)
        expect(r == want and toasts(m) == toast, f'Wi-Fi status {net}: the row opens {want}, toast {toasts(m)}')
    # the address text (stock's init formats it with http://; the page's big card leaves the scheme out)
    for net, ip, want in ((1, b'192.168.100.100', '192.168.100.100:8888'), (1, b'255.255.255.255', '255.255.255.255:8888'), (1, b'10.0.0.2', '10.0.0.2:8888'), (0, b'10.0.0.2', '-'), (1, b'', '-')):
        m = NS(net=net, ip=ip); buf = m.alloc(64); m.call(PSYMS['wt_url_text'], a0=buf, a1=64, count=3000000)
        expect(m.read_cstr(buf) == want, f'Wi-Fi {net}, ip {ip!r}: the address reads {m.read_cstr(buf)!r}')
    # (stock's init is not run: its widget_foreach visitor needs a real widget tree; its calls, their order and the two binds are pinned above, init 0x4b1664: binds 0x4b16ac / 0x4b16cc, then
    # networkGetIPAddr 0x4b1710, stop_player 0x4b1720, switch_wifitransport(1) 0x4b1730, then the text 0x4b1794)
    expect(0x4b16ac < 0x4b16cc < 0x4b1710 < 0x4b1720 < 0x4b1730 < 0x4b1794 and {0x4b16ac, 0x4b16c8, 0x4b16cc, 0x4b16e8} <= pins, 'stock\'s init order is pinned: the two binds, the address, stop_player, the server, the text')
    # stock's key filter and close handler
    for key in (0, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xdc, 0xdd, 0x100):
        m = NS(); e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x18, key)
        expect(m.call(KEYFILTER, a0=m.window, a1=e) == (0xb if 0xd5 <= key <= 0xd7 else 0), f'stock\'s key filter: key {key:#x} is stopped only for 0xd5 .. 0xd7')
    m = NS(); m.u.mem_write(WTF, b'\1'); m.call(CLOSE_H, a0=m.window, count=3000000)
    expect(m.seen() == [('switch_wifitransport', 0)] and m.byte(WTF) == 0, 'stock\'s close handler: switch_wifitransport(0), the byte cleared')


def page_tests(ctx):
    """The two pages as cards, the way a tap opens the transfer page, and every way it goes."""
    expect, P = ctx.expect, pod_pages
    NP, WP, SP = P.NETSERVICE_PAGE, P.WIFITRANSFER_PAGE, P.SETTINGS_PAGE
    expect((NP.key, NP.title, NP.kind) == ('m1plus_netservice', 'Network Services', 'cards') and (WP.key, WP.title, WP.kind) == ('m1plus_wifitransfer', 'Wi-Fi Transfer', 'cards'), 'the two pages and their titles')
    expect([(r.label, r.action) for r in NP.rows] == [('AirPlay', P.ACT_NETAIR), ('DLNA', P.ACT_NETDLNA), ('SyncLink', P.ACT_STOCK), ('Wi-Fi Transfer', P.ACT_NETTRANS)] and NP.layout[2] is P.GAP and NP.rows[2].arg == P.STOCK_SYNCLINK, 'Network Services: AirPlay, DLNA, a gap, then the SyncLink and Wi-Fi Transfer links')
    expect([P.row_kind(r) for r in NP.rows] == ['switch', 'switch', 'link', 'link'] and NP.rows[3].arg == P.WIFITRANSFER_PAGE_INDEX, 'two switches, SyncLink and a link to our page')
    lay = WP.layout
    expect(not WP.rows and [type(x).__name__ for x in lay] == ['Hero', 'QrCard', 'BigCard', 'Note', 'QrPill'] and (lay[0].glyph, lay[0].title, lay[0].text, lay[0].lines) == ('wifi', 'Wi-Fi Transfer', P.WT_INFO, 2) and (lay[3].text, lay[3].center) == (P.WT_NOTE, True)
           and lay[1].hero is lay[0] and lay[1].start_hidden and lay[4].text == P.WT_SHOW_QR, 'Wi-Fi Transfer: a hero (glyph, title, description), the hidden QR code in its place, the address card, the footer note, the Show QR Code pill; no rows')
    expect(P.WT_INFO == 'On the same Wi-Fi, open this address in a browser to manage your music.' and P.WT_NOTE == 'Playback is paused while this page is open. Leave the page to turn it off.', 'the two texts')
    expect(P.WIFITRANSFER_PAGE.wrap_notes() == 0b11, 'the description (note 0) and the centred footer (note 1) wrap')
    expect(P.PAGE_ORDER[-15:-13] == ['m1plus_netservice', 'm1plus_wifitransfer'] and (P.ACT_NETAIR, P.ACT_NETDLNA, P.ACT_NETTRANS) == (166, 167, 168) and not hasattr(P, 'ACT_WTADDR'), 'the pages come before the three Bluetooth pages (then the two Playback Settings sub-pages, the Volume page, the Update Library page and its folder picker, Split Genres, the three Card Script pages, then Crossfade, the last of PAGE_ORDER); the action ids are 166 .. 168')
    row = SP.rows[2]
    expect([r.label for r in SP.rows[:3]] == ['Wi-Fi', 'Bluetooth', 'Network Services'] and (row.action, row.arg) == (P.ACT_PAGE, P.NETSERVICE_PAGE_INDEX) and SP.layout[3] is P.GAP, 'Settings: Wi-Fi, Bluetooth and Network Services share the first card')
    expect([r.label for r in NP.rows + WP.rows if r.action == P.ACT_STOCK] == ['SyncLink'] and not any('netservice' in n or 'wifitransport' in n for n, *_ in P.STOCK_PAGES), 'only SyncLink opens a stock page; the Wi-Fi Transfer and Network Services pages are ours')
    import pod_i18n
    keys = ('Network Services', 'Wi-Fi Transfer', P.WT_INFO, P.WT_NOTE, P.WT_SHOW_QR, P.WT_HIDE_QR)
    expect(all(k in pod_i18n.TEXT for k in keys) and 'AirPlay' in pod_i18n.BRANDS and 'DLNA' in pod_i18n.BRANDS and 'Address' not in pod_i18n.TEXT, 'our keys, the brands')
    expect(all(all(pod_i18n.TEXT[k][loc] for loc in pod_i18n.LOCALES) for k in keys), 'every text has a translation in all 13 languages')
    expect(pod_i18n.TEXT['Wi-Fi Transfer']['zh_CN'] == 'Wi-Fi 传输' and pod_i18n.TEXT['Wi-Fi Transfer']['zh_HK'] == 'Wi-Fi 傳輸' and not any('传歌' in v or '傳歌' in v for d in pod_i18n.TEXT.values() for v in d.values()), 'the Chinese title is Wi-Fi 传输 / 傳輸')
    import mod_icons
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Network Services', 'AirPlay', 'DLNA', 'Wi-Fi Transfer')] == ['network', 'airplay', '+dlna:filled', 'folder-sync'], 'the glyphs: Network Services is Lucide network (not the Chromecast-like cast)')
    expect(mod_icons.HERO_ICONS == {'pod_hero_wifi': 'wifi'} and mod_icons.HERO_PX == 36 and os.path.exists(os.path.join(mod_icons.PNG, 'pod_hero_wifi.png')) and os.path.exists(os.path.join(mod_icons.PNG, 'pod_ci_network.png'))
           and not os.path.exists(os.path.join(mod_icons.PNG, 'pod_ci_cast.png')), 'the hero glyph image and the network card glyph exist, the cast one is gone')
    expect(mod_icons.SONGS_IMAGES['wt_qr'][:3] == ('qr-code', (0xAA, 0xAA, 0xAA), 14) and os.path.exists(asset_path('wt_qr')), 'the pill\'s glyph: Lucide qr-code, 14 px, the label\'s grey')

    def page(net=1, **kw):
        m = NS(net=net, **kw)
        m.widgets.update({n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row', 'pod_label', 'pod_value', 'pod_check', 'pod_switch') for i in range(4)] + ['pod_big0_t'] + list(QR_WIDGETS))})
        r = m.alloc(12)
        m.setword(r, m.cstr('pod_row0')); m.setword(r + 4, P.ACT_NETTRANS); m.setword(r + 8, P.WIFITRANSFER_PAGE_INDEX)
        m.on_row_arg = r
        return m
    # without a network: the toast and nothing else
    m = page(net=0); m.call(PSYMS['on_row'], a0=m.on_row_arg, count=6000000)
    expect(toasts(m) == ['Connect to Wi-Fi first'] and ('window_open', 'm1plus_wifitransfer') not in m.calls and not m.seen(), 'no network: the toast; no window, no stop_player, no server')
    # with one: the window, then stock's init order
    m = page(net=1); m.call(PSYMS['on_row'], a0=m.on_row_arg, count=6000000)
    names = m.names()
    expect(('window_open', 'm1plus_wifitransfer') in m.calls and m.seen() == [('stop_player',), ('switch_wifitransport', 1)] and m.byte(WTF) == 1, f'a network: the window opens, then stop_player, then switch_wifitransport(1) ({m.seen()})')
    binds = {c[2] for c in m.calls if c[0] == 'widget_on' and c[1] == m.window}
    first_bind = min(i for i, c in enumerate(m.calls) if c[0] == 'widget_on' and c[1] == m.window and c[2] in (0x113, 0x12e))
    expect({0x113, 0x12e, 0xc} <= binds and first_bind < names.index('stop_player'), 'EVT_KEY_UP, EVT_WINDOW_CLOSE and EVT_DESTROY are bound before the server starts')
    lab = m.widgets['pod_big0_t']
    expect([c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == lab][-1:] == ['192.168.100.100:8888'], 'the big card\'s label shows <ip>:8888')
    # the key filter: stock's own decisions
    kf = m.bound[(m.window, 0x113)]
    for key in range(0xd0, 0xe0):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x18, key)
        st = NS(); se = st.alloc(0x30); st.u.mem_write(se, bytes(0x30)); st.setword(se + 0x18, key)
        ours, theirs = m.call(kf[0], a0=kf[1], a1=e, count=200000), st.call(KEYFILTER, a0=st.window, a1=se, count=200000)
        expect(ours == theirs, f'key {key:#x}: our filter answers {ours}, stock\'s {theirs}')

    def opened():
        mm = page(net=1); mm.call(PSYMS['on_row'], a0=mm.on_row_arg, count=6000000); mm.calls = []; return mm
    # every way out calls switch_wifitransport(0): the close event (as stock), the destroy event alone, both (once)
    mm = opened(); mm.fire(0x12e)
    expect(mm.seen() == [('switch_wifitransport', 0)] and mm.byte(WTF) == 0, 'the close event (Back, Home): the server stops, as stock\'s close handler does')
    mm.calls = []; mm.fire(0xc)
    expect(mm.seen() == [], 'the destroy event after it stops nothing a second time')
    mm = opened(); mm.fire(0xc)
    expect(mm.seen() == [('switch_wifitransport', 0)] and mm.byte(WTF) == 0, 'a window destroyed without a close event: the server stops')
    # Now Playing: the server stops, the player is not stopped again, and the page starts it again when it is back in front
    mm = page(net=1); mm.call(PSYMS['on_row'], a0=mm.on_row_arg, count=6000000)
    clicks = [c for c in mm.calls if c[0] == 'widget_on' and c[1] == mm.widgets['btn_backtoplayer'] and c[2] == O['EVT_CLICK']]
    expect(len(clicks) == 2, f'the Now Playing button has two handlers: the page\'s own and the one every page has ({len(clicks)})')
    mm.calls = []; mm.click('btn_backtoplayer')
    expect(mm.seen() == [('switch_wifitransport', 0)] and mm.byte(WTF) == 0, 'the Now Playing button: the server stops (stock leaves it running under the player)')
    mm.calls = []; mm.click('btn_backtoplayer')
    expect(mm.seen() == [], 'a second press stops nothing again')
    mm.calls = []; mm.fire(O['EVT_WINDOW_TO_FG'])
    expect(mm.seen() == [('switch_wifitransport', 1)] and mm.byte(WTF) == 1, 'back in front: the server starts again, the player is not stopped a second time')
    mm.calls = []; mm.fire(O['EVT_WINDOW_TO_FG'])
    expect(mm.seen() == [], 'back in front while it runs: nothing')
    mm.calls = []; mm.fire(0x12e)
    expect(mm.seen() == [('switch_wifitransport', 0)] and mm.byte(WTF) == 0, 'the close after that stops it')
    mm.calls = []; mm.fire(O['EVT_WINDOW_TO_FG'])
    expect(mm.seen() == [], 'a window that is gone is never started again')
    # a bind that fails: nothing starts (nothing could stop it)
    for ev in (0x113, 0x12e, 0xc):
        m = page(net=1); m.widget_on_fail = {ev}; m.call(PSYMS['on_row'], a0=m.on_row_arg, count=6000000)
        expect(not m.seen() and m.byte(WTF) == 0, f'the bind of event {ev:#x} refused: no stop_player, no server')
    # the Network Services page's switches are bound
    m = page(net=1)
    expect(switch_ok(m), 'the switch rows are generic switch rows')
    # the asset
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    t = awtk_ui.parse(open(os.path.join(raw, 'm1plus_netservice.bin'), 'rb').read())
    expect(t.find('label_title').get('tr_text') == 'Network Services' and [t.find(f'pod_label{i}').get('tr_text') or t.find(f'pod_label{i}').get('text') for i in range(4)] == ['AirPlay', 'DLNA', 'wifiset_synclink', 'Wi-Fi Transfer'], 'the asset: our title and row keys (the brands as plain text; SyncLink is stock\'s key)')
    t = awtk_ui.parse(open(os.path.join(raw, 'm1plus_wifitransfer.bin'), 'rb').read())
    expect(t.find('label_title').get('tr_text') == 'Wi-Fi Transfer', 'the transfer asset: our title in the navbar')
    from awtk_text import Ttf, awtk_width
    import pod_settings as ST
    sv = t.find('pod_scrollview'); kids = sv.children
    expect([c.name for c in kids] == ['pod_top', 'pod_hero', 'pod_qr', 'pod_big0', 'pod_note1', 'pod_qrpill', 'pod_end'] and not any(c.type == 'list_item' for c in kids), 'the transfer asset: top, hero, the QR code, the address card, the footer note, the pill, end; no row')
    qr, code, pill, btn = (t.find(n) for n in ('pod_qr', 'pod_qr_code', 'pod_qrpill', 'pod_qrbtn'))
    expect(qr.get('visible') == 'false' and qr.get('sensitive') == 'false' and qr.h == t.find('pod_hero').h and code.get('sensitive') == 'false' and code.w == code.h == ST.QR_SIDE == 132
           and qr.x + code.x + code.w // 2 == 160 and code.y == (qr.h - code.h) // 2, 'the QR item: hidden and insensitive, as high as the hero (so the swap moves nothing), the 132 px code centred on the page and on the item')
    expect(pill.get('sensitive') != 'false' and btn.type == 'button' and btn.get('tr_text') == P.WT_SHOW_QR and btn.get('style:normal:icon') == 'wt_qr' and btn.get('style:normal:font_size') == '14'
           and btn.get('style:normal:text_color') == '#AAAAAA' and btn.get('style:normal:bg_color') == '#1C1C1E' and btn.get('style:pressed:bg_color') == '#333333' and btn.get('style:normal:round_radius') == '16'
           and (btn.y, btn.h, pill.h) == (6, 32, 38), 'the pill: a sensitive item (its button gets the touch), a flat 32 px pill on the rest surface, the grey 14 px label and the qr-code glyph, 6 px under the note')
    import mod_icons; g = asset_image('wt_qr')
    expect(ST.PILL_DROP == mod_icons.WT_QR_DROP == 1 and all(btn.get(f'style:{st}:margin_top') == '3' and btn.get(f'style:{st}:margin_bottom') == '1' for st in ('normal', 'pressed'))
           and g.size == (14, 16) and g.getchannel('A').crop((0, 14, 14, 16)).getbbox() is None and g.getchannel('A').crop((0, 0, 14, 14)).getbbox() == (0, 0, 14, 14),
           'the label sits 1 px low (margins 3 / 1: its caps centre on the pill and the glyph); the glyph PNG carries 2 clear rows under it, so the glyph stays centred on the pill')
    expect(touch_misses(page(net=1), os.path.join(raw, 'm1plus_wifitransfer.bin'), ['pod_qrbtn']) == [], 'the pill is reached by the hit test')
    expect(all(O[k] == v for k, v in (('WT_QR_MOD', ST.QR_MOD), ('WT_QR_QUIET', ST.QR_QUIET), ('WT_QR_R', ST.QR_R), ('WT_PILL_Y', ST.PILL_Y), ('WT_PILL_H', ST.PILL_H), ('WT_PILL_GLYPH', ST.PILL_GLYPH),
                                          ('WT_PILL_GAP', ST.PILL_GAP), ('WT_PILL_PAD', ST.PILL_PAD), ('WT_PILL_MID', ST.CM + ST.CARD_W // 2)))
           and O['WT_QR_PAPER'] == 0xff000000 | int(ST.QR_RGB[5:7], 16) << 16 | int(ST.QR_RGB[3:5], 16) << 8 | int(ST.QR_RGB[1:3], 16), 'patch/offsets.inc WT_* hold tools/pod_settings.py\'s numbers and the paper colour')
    hero, big, foot = (t.find(n) for n in ('pod_hero', 'pod_big0', 'pod_note1'))
    tile, icon, title, desc = (t.find(n) for n in ('pod_hero_tile', 'pod_hero_icon', 'pod_hero_title', 'pod_note0_t'))
    expect((tile.w, tile.h) == (64, 64) and hero.x + tile.x + tile.w // 2 == 160 and tile.get('style:normal:round_radius') == '16' and tile.get('style:normal:bg_color') == '#2C2C2E'
           and (icon.w, icon.h, icon.get('image')) == (36, 36, 'pod_hero_wifi') and icon.x + icon.w // 2 == tile.w // 2 and icon.y + icon.h // 2 == tile.h // 2, 'the hero tile: 64 px, radius 16, the raised surface colour, centred on the page, the 36 px wifi glyph centred in it')
    expect(title.get('tr_text') == 'Wi-Fi Transfer' and title.get('style:normal:font_size') == '22' and title.get('style:normal:text_color') == '#FFFFFF' and title.get('style:normal:text_align_h') == 'center'
           and hero.x + title.x + title.w // 2 == 160, 'the title: 22 px white, centred')
    expect(desc.type == 'label' and desc.get('tr_text') == P.WT_INFO and desc.get('style:normal:font_size') == '14' and desc.get('style:normal:text_color') == '#AAAAAA' and desc.get('style:normal:text_align_h') == 'center'
           and hero.x + desc.x + desc.w // 2 == 160, 'the description: a wrapping label, 14 px grey, centred')
    card = big.children[0]; lab = t.find('pod_big0_t')
    expect(card.get('style:normal:bg_image') == 'pod_cdl_single' and (card.w, card.h) == (310, 60) and lab.get('text') == '' and lab.get('style:normal:font_size') == '22' and lab.get('style:normal:font_name') == 'lyrics'
           and lab.get('style:normal:text_color') == '#FFFFFF' and lab.get('style:normal:text_align_h') == 'center' and lab.x + lab.w // 2 == 160, 'the address card: the tall single card piece, the text empty (the payload writes it), 22 px white bold, centred')
    fon = Ttf(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts/lyrics.ttf'))
    worst = max(awtk_width(fon, f'{a}.{a}.{a}.{a}:8888', 22) for a in ('255', '888', '192', '100'))
    expect(worst + 2 * 12 <= lab.w - 4, f'the worst case address (255.255.255.255:8888) is {worst} px in the bold 22 px face: one line with 12 px side padding in the 300 px card')
    expect(foot.children[0].get('style:normal:font_size') == '15' and foot.children[0].get('style:normal:text_align_h') == 'center' and foot.children[0].get('tr_text') == P.WT_NOTE and foot.children[0].type == 'label', 'the footer: a wrapping label, 15 px grey (the note size), centred')
    end = ST.layout(P.WIFITRANSFER_PAGE.layout)[1]
    expect(end <= 400 and qr.y == t.find('pod_hero').y and t.find('pod_big0').y == qr.y + qr.h, f'the page does not scroll ({end} px of 400); the code sits in the hero\'s place (the layouter stacks the one shown)')


QR_WIDGETS = ('pod_hero', 'pod_qr', 'pod_qr_code', 'pod_qrpill', 'pod_qrbtn')
# Project Nayuki's QR Code generator (qrcodegen 1.8, encode_segments with one alphanumeric segment, level MEDIUM, version 2, automatic mask): the symbols as 25 rows of 7 hex digits
NAYUKI = {'HTTP://192.168.100.100:8888': (4, '1fddb7f104bd41174835d175cb5d1753e5d1053c411fd557f001a0001175ff91a336d8035bfc403a4b6311f382c10a4c9403ec387073d4301b56dfd001911e1fd7f5f10429181755bf21748d21174c0b610457bb1fd6c59'),
          'HTTP://255.255.255.255:8888': (4, '1fd9b7f1044d41174635d1758b5d175ee5d1052c411fd557f00190001174ff90aae6e81f48cf410b6b430d7bb3c1e18ea4065838701957f01b66ffd001111e1fdff5f104a9181755bf21744d6517400be10456531fd6e15'),
          'HTTP://10.0.0.2:8888': (1, '1fd6e7f1044241175d85d174a35d174e35d105dd411fd557f000d800146cb250f12159087edb51b0470d01f0d7208b4c251cfa3d604a88ee1b43bf3001911f1fd9d5f10437151748dfe174cd00175a37f10488911fd7b2b')}


def qr_rows(hexrows): return [[int(b) for b in format(int(hexrows[i:i + 7], 16), '025b')] for i in range(0, 175, 7)]


def qr_tests(ctx):
    """patch/qr.c against its model tools/qr.py, the model against Nayuki's generator, and the page's swap and paint."""
    expect = ctx.expect
    import qr
    for text, (mask, rows) in NAYUKI.items():
        expect(qr.encode(text) == qr_rows(rows) and qr.encode(text, mask) == qr_rows(rows), f'{text}: tools/qr.py makes Nayuki\'s symbol and mask {mask}')
    m = Machine()

    def c_make(text, mask=-1):
        buf = m.alloc(qr.SIZE * qr.SIZE // 8 + 1); m.u.mem_write(buf, bytes(80))
        r = m.call(PSYMS['qr_make'], a0=m.cstr(text), a1=mask & 0xffffffff, a2=buf, count=60000000)
        bits = m.u.mem_read(buf, 79)
        return r, [[(bits[(y * 25 + x) >> 3] >> (7 - ((y * 25 + x) & 7))) & 1 for x in range(25)] for y in range(25)]
    for ip in ('192.168.100.100', '255.255.255.255', '10.0.0.2', '172.16.254.1'):
        text = qr.address_text(ip)
        r, rows = c_make(text)
        expect(r == 25 and rows == qr.encode(text), f'{text}: the payload\'s symbol (least penalty) is the model\'s')
    text = qr.address_text('192.168.1.23')
    bad = [k for k in range(8) if c_make(text, k)[1] != qr.encode(text, k)]
    expect(not bad, f'{text}: every mask the same as the model ({bad} differ)')
    for text in ('http://10.0.0.2:8888', 'A' * 39, 'HTTP://10.0.0.2:8888?'):
        expect(c_make(text)[0] == 0, f'{text!r}: refused (not alphanumeric, or longer than 38)')
    expect(c_make('A' * 38)[0] == 25 and c_make('')[0] == 25, 'up to 38 characters fit, and the empty text')

    # the page: opened with the hero, the pill swaps the code in and out; the paint is the model's symbol
    P = pod_pages
    m = NS(net=1)
    m.widgets.update({n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer', 'pod_big0_t'] + list(QR_WIDGETS))})
    r = m.alloc(12); m.setword(r, m.cstr('pod_row0')); m.setword(r + 4, P.ACT_NETTRANS); m.setword(r + 8, P.WIFITRANSFER_PAGE_INDEX)
    m.call(PSYMS['on_row'], a0=r, count=8000000)
    W = m.widgets

    def shown(n): return [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == W[n]][-1:] == [1]

    def label(): return [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == W['pod_qrbtn']][-1:]
    expect(shown('pod_hero') and not shown('pod_qr') and shown('pod_qrpill') and label() == [P.WT_SHOW_QR], 'opened: the hero, the pill reads Show QR Code, the code hidden')
    m.click('pod_qrbtn')
    expect(shown('pod_qr') and not shown('pod_hero') and label() == [P.WT_HIDE_QR], 'the pill: the code in the hero\'s place, the pill reads Hide QR Code')
    expect(m.seen()[-1:] != [('switch_wifitransport', 0)], 'the swap leaves the server alone')
    fn, ctx2 = m.bound[(W['pod_qr_code'], O['EVT_AFTER_PAINT'])]
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + O['EVENT_PAINT_CANVAS'], m.alloc(64))
    m.fills = []; m.call(fn, a0=ctx2, a1=e, count=8000000)
    side, mod, quiet = 132, O['WT_QR_MOD'], O['WT_QR_QUIET']
    grid = [[0] * 25 for _ in range(25)]
    for col, x, y, w, h in m.fills:
        if col == O['WT_QR_DARK'] and h == mod and x >= quiet * mod and y >= quiet * mod:
            for k in range(w // mod): grid[y // mod - quiet][x // mod - quiet + k] = 1
    expect(m.fills[0][:5] == (O['WT_QR_PAPER'], 0, 0, side, side), f'the paint: the near-white paper first, the whole {side} px square (raw colour: Light Mode keeps it)')
    expect(grid == qr.encode(qr.address_text('192.168.100.100')), 'the dark modules painted are the model\'s symbol of HTTP://192.168.100.100:8888, 4 px each inside the 4-module border')
    expect(any(w == 1 and h == 1 and x < O['WT_QR_R'] and y < O['WT_QR_R'] for _, x, y, w, h in m.fills), 'the corners are rounded (the page\'s colour over the paper)')
    m.click('pod_qrbtn')
    expect(shown('pod_hero') and not shown('pod_qr') and label() == [P.WT_SHOW_QR], 'again: the hero back, Show QR Code')
    m.click('pod_qrbtn'); m.click('btn_backtoplayer'); m.fire(O['EVT_WINDOW_TO_FG'])
    expect(shown('pod_qr') and label() == [P.WT_HIDE_QR], 'back in front after Now Playing: the code is still shown')
    # Wi-Fi gone while the page is open: no address, no code, no pill
    m.net = 0; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(shown('pod_hero') and not shown('pod_qr') and not shown('pod_qrpill'), 'no address: the hero, and the pill hidden')


def switch_ok(m):
    """The Network Services rows are switches the generic page binds (pod_pages SWITCH_ACTIONS and the payload's table agree)."""
    return pod_pages.ACT_NETAIR in pod_pages.SWITCH_ACTIONS and pod_pages.ACT_NETDLNA in pod_pages.SWITCH_ACTIONS


SECTIONS = [state_tests, page_tests, qr_tests]

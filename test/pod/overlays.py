"""The overlay screens (tools/mod_overlays.py, docs/modules/overlays.md): the message / confirm dialogs and the power-off splash."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_overlays as mo
from PIL import Image
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA


def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    def img(n): return Image.open(os.path.join(raw, 'images/xx', n + '.png'))
    def shipped(n): return open(os.path.join(raw, 'images/xx', n + '.png'), 'rb').read()
    pins = mo.load_pins()
    expect(sorted(pins) == sorted(mo.NAMES) and len(mo.NAMES) == 3, 'every replaced image is pinned')
    for n in mo.NAMES:
        expect(shipped(n) == open(os.path.join(mo.ASSET, n + '.png'), 'rb').read(), f'{n}: the built file is the committed asset')
    expect(sorted(os.listdir(mo.ASSET)) == sorted(n + '.png' for n in mo.NAMES), 'the committed art is exactly the three files')

    # the charging and battery art stays the stock bytes (the scan spinner, chargebg and the USB pages are tools/mod_icons.py's, docs/modules/icons.md)
    stock = mo.stock_dir()
    for n in ['charging0', 'charging18', 'charge_big', 'dac_charge']:
        expect(shipped(n) == open(os.path.join(stock, n + '.png'), 'rb').read(), f'{n} is stock')

    sizes = {'msginfo_bg': (260, 180), 'confirminfo_bg': (260, 180), 'shutdown': (320, 480)}
    expect(all(img(n).size == s for n, s in sizes.items()), 'every image keeps its stock pixel size')

    # dialogs: glass (translucent, rounded corners), divider only on the confirm card
    msg, con = img('msginfo_bg').convert('RGBA'), img('confirminfo_bg').convert('RGBA')
    expect(msg.getpixel((0, 0))[3] == 0 and 200 < msg.getpixel((130, 90))[3] < 255, 'message card: transparent corner, glass body')
    expect(con.getpixel((60, mo.DIVIDER_Y))[3] > msg.getpixel((60, mo.DIVIDER_Y))[3] and con.getpixel((60, 160)) == msg.getpixel((60, 160)), 'confirm card: the horizontal divider, no vertical line in the image')
    expect(mo.dialog(False).tobytes() == msg.tobytes() and mo.dialog(True).tobytes() == con.tobytes(), 'dialog art is the generator output')
    expect(img('shutdown').size == (320, 480) and img('shutdown').convert('RGB').getpixel((5, 5)) == (0, 0, 0), 'the splash is the black boot logo')

    # the resolved styles of every message-like 260 x 180 dialog agree with the confirm box's: the same card (bg_image / bg_color / border / radius in the states the dialogs use),
    # no grey border; the message box (msginfo) and the confirm box differ only in the card picture's divider
    dlg = os.path.join(raw, 'ui', 'dialog')
    def card(rel):
        t = awtk_ui.parse(open(os.path.join(dlg, rel), 'rb').read())
        return {(st, k): t.get(f'style:{st}:{k}') for st in mo.CARD_STATES for k in ('bg_color', 'border_color', 'round_radius')}, {t.get(f'style:{st}:bg_image') for st in mo.CARD_STATES} - {None}, (t.w, t.h)
    ref, _, ref_size = card('confirminfo_dialog.bin')
    for rel in ('msginfo_dialog.bin', 'rippercompleted_dialog.bin', *[k.split('/')[1] for k in mo.CARD_DIALOGS]):
        st, images, size = card(rel)
        expect(size == ref_size and all(st[k] == ref[k] for k in ref if k[1] != 'round_radius' or st[k] is not None) and st[('normal', 'round_radius')] in ('12', None) and len(images) == 1,
               f'{rel}: the confirm box\'s card styles (transparent fill and border, one picture) ({st})')
    for rel, image in {'msginfo_dialog.bin': 'msginfo_bg', 'confirminfo_dialog.bin': 'confirminfo_bg', **{k.split('/')[1]: v for k, v in mo.CARD_DIALOGS.items()}}.items():
        expect(card(rel)[1] == {image}, f'{rel}: bg_image {image}')
    t = awtk_ui.parse(open(os.path.join(dlg, 'dialog_autoshutdown.bin'), 'rb').read()); b = t.find('btn_cancel')
    expect(b.get('style:normal:bg_color') == '#00000000' and b.get('style:normal:border_color') == '#00000000', 'the sleep countdown\'s button has no black fill or grey border')
    # ui edits
    ui = os.path.join(raw, 'ui')
    for rel in ('dialog/confirminfo_dialog.bin', 'dialog/rippercompleted_dialog.bin'):
        t = awtk_ui.parse(open(os.path.join(ui, rel), 'rb').read())
        btns = [b for b in (t.find('btn_cancel'), t.find('btn_enter')) if b is not None]
        expect(btns and all(b.get('style:normal:bg_color') == '#00000000' for b in btns), f'{rel}: buttons transparent so the card shows')
    t = awtk_ui.parse(open(os.path.join(ui, 'dialog/confirminfo_dialog.bin'), 'rb').read())
    c, e = t.find('btn_cancel'), t.find('btn_enter')
    expect((c.x, c.y, c.w, c.h) == (1, 131, 128, 48) and (e.x, e.y, e.w, e.h) == (131, 131, 128, 48), 'confirm buttons keep their geometry')
    expect(t.get('highlight') == mo.CONFIRM_DIM == 'default(alpha=130)', 'the confirm dialog dims the window below like our popups\' scrim (the highlighter\'s alpha 130)')
    expect(c.get('style:normal:border') == 'right' and c.get('style:normal:border_color') == mo.BTN_BORDER, 'Cancel draws the vertical divider as its right border')
    p = open(os.path.join(ui, 'poweroff_page.bin'), 'rb').read()
    q = open(os.path.join(stock, '..', '..', 'ui', 'poweroff_page.bin'), 'rb').read()
    expect(p == q, 'poweroff_page.bin is stock (only shutdown.png changed)')
    scrim_tests(ctx)
    coex_tests(ctx)


BT_EXIT_INIT, BT_INITSTATUS, WIFI_FLAG, BT_FLAG = 0xa038a8, 0xa038a4, 0x97caf8, 0xa05ac0   # stock's bytes / words (docs/modules/addresses.md "Wi-Fi and Bluetooth together")


class CoexMachine(Machine):
    """The stock Wi-Fi switch-on handlers run for real over the built demo (the Control Center tile 0x474ec8, the settings page row handler 0x4b0a88; its closing list refresh 0x4b0814 is trapped), with the calls around them trapped:
    wifi_switch (toggles wififlag as stock does), switchBluetooth, usleep, the confirm (Machine's navigator_to_with_context: confirm_yes) and every write to bt_exit_init is recorded."""
    CC_TILE, SETTINGS_ROW = 0x474ec8, 0x4b0a88

    def __init__(self):
        super().__init__()
        self.sw = []   # ('wifi_switch', a0), ('switchBluetooth', a0, a1), ('usleep', a0), ('getFormatString', key), in order
        self.exit_writes = []
        for a, n in {0x507a8c: 'wifi_switch', 0x4d516c: 'switchBluetooth', 0x7423e0: 'usleep', 0x4ccc18: 'getFormatString', 0x742da0: 'memset', 0x66a9a8: 'widget_get_window', 0x506d60: 'settings_pre', 0x4b0814: 'settings_pre', 0x742fd0: 'settings_pre', 0x7435b0: 'atoi'}.items():
            self.handlers[a] = n
        self.u.hook_add(UC_HOOK_MEM_WRITE, lambda u, access, address, size, value, _: self.exit_writes.append(value), begin=BT_EXIT_INIT, end=BT_EXIT_INIT)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        if name == 'wifi_switch':
            self.sw.append(('wifi_switch', a0)); on = self.u.mem_read(WIFI_FLAG, 1)[0]; self.u.mem_write(WIFI_FLAG, bytes([0 if on else 1]))
        elif name == 'switchBluetooth':
            self.sw.append(('switchBluetooth', a0, a1)); self.u.mem_write(BT_FLAG, bytes([0 if self.u.mem_read(BT_FLAG, 1)[0] else 1]))
        elif name == 'usleep':
            self.sw.append(('usleep', a0))
        elif name == 'getFormatString':
            self.sw.append(('getFormatString', self.read_cstr(a0)))
        elif name == 'settings_pre':
            pass
        else: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def switch_on(self, which, bt_start, yes, bt=True):
        """Wi-Fi off, Bluetooth on (bt) and starting (bt_start: bt_initstatus != 0); the tile / the settings row is tapped and the warning answered OK (yes) or Cancel."""
        self.sw, self.exit_writes = [], []
        self.u.mem_write(WIFI_FLAG, b'\0'); self.u.mem_write(BT_FLAG, bytes([int(bt)]))
        self.setword(BT_INITSTATUS, int(bt_start)); self.u.mem_write(BT_EXIT_INIT, b'\0')
        self.confirm_yes = yes
        if which == 'tile': self.call(self.CC_TILE, a0=self.alloc(0x40), count=3000000)
        else:
            ev = self.alloc(0x40); self.u.mem_write(ev, bytes(0x40)); self.setword(ev + 0x10, self.cstr('0'))
            self.call(self.SETTINGS_ROW, a0=ev, a1=self.alloc(0x40), count=3000000)
        return self


def coex_tests(ctx):
    """Wi-Fi and Bluetooth together (tools/coex.py): the stock handlers run over the build. Wi-Fi on while Bluetooth is on shows the warning and, on OK, only calls wifi_switch(1): nothing of stock's
    cancellation of a Bluetooth start in progress runs (bt_exit_init is never written, no wait, no switch-off), so Bluetooth keeps starting and stays on. Cancel changes nothing. The Bluetooth-side
    handlers have no preamble: their `beqz v0` after OK is `b`. Every neighbouring word is stock's, and the two question keys are called at the pinned addresses."""
    import struct
    import coex, paths
    expect = ctx.expect
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    expect([a for a, *_ in coex.EDITS] == [0x474d98, 0x474fd8, 0x4a3b64, 0x4b0b9c], 'the four callers of the switch-on question are patched')
    for a, old, new, what in coex.EDITS:
        target = a + 4 + 4 * (new & 0xffff)
        expect(w(stock_demo, a) == old and w(built, a) == new and new >> 16 == 0x1000 and target in (0x474db0, 0x475028, 0x4a3b78, 0x4b0c00),
               f'{a:#x}: stock {old:#010x} -> b, to {target:#x} ({what})')
    expect(all(w(stock_demo, a) == old and w(built, a) == old for a, old, _ in coex.PINS), 'the neighbouring words (the Wi-Fi flag test, the confirm call and test, the wifi_switch call setup) are stock\'s, in the stock demo and in the build')
    # static: the Wi-Fi-side branches land on the lw t9 of wifi_switch(1) (jalr + a0 = 1), past the whole preamble; the Bluetooth-side ones on switchBluetooth's call setup (no preamble before)
    expect(w(built, 0x475028) == 0x8f99a994 and w(built, 0x47502c) == 0x0320f809 and w(built, 0x475030) == 0x24040001 and w(built, 0x4b0c00) == 0x8f99a994 and w(built, 0x4b0c04) == 0x0320f809 and w(built, 0x4b0c08) == 0x24040001,
           'the Wi-Fi-side branches land on lw t9 wifi_switch, jalr, a0 = 1')
    # the question itself: msg_wifi_open / msg_bt_open are the keys the four callers pass to getFormatString (0x7445dc, 0x7445a8)
    for key, addr, sites in (('msg_wifi_open', 0x7445dc, (0x474fb0, 0x4b0b74)), ('msg_bt_open', 0x7445a8, (0x474d6c, 0x4a3b38))):
        o = pod.fileoff(built, addr)
        expect(built[o:o + len(key) + 1] == key.encode() + b'\0' and all(w(built, s) & 0xffff == addr & 0xffff and w(built, s) >> 16 == 0x2484 for s in sites), f'{key} at {addr:#x} is passed at {[hex(s) for s in sites]}')
    # run: Wi-Fi switched on with Bluetooth on, from the Control Center tile and from the settings page's row handler
    for which in ('tile', 'row'):
        m = CoexMachine()
        m.widget('img_btswitch'); m.widget('img_wifiswitch')
        for starting in (True, False):
            m.switch_on(which, starting, yes=True)
            seq = [c[0] if c[0] != 'getFormatString' else c[1] for c in m.sw]
            expect(seq == ['msg_wifi_open', 'wifi_switch'] and m.sw[1] == ('wifi_switch', 1), f'{which}, Bluetooth {"starting" if starting else "up"}, OK: the warning, then wifi_switch(1) alone (no wait, no switch-off): {m.sw}')
            expect(m.exit_writes == [] and m.u.mem_read(BT_EXIT_INIT, 1)[0] == 0 and m.word(BT_INITSTATUS) == int(starting), f'{which}, starting={starting}: bt_exit_init is never written, bt_initstatus left alone ({m.exit_writes})')
            expect(m.u.mem_read(BT_FLAG, 1)[0] == 1 and m.u.mem_read(WIFI_FLAG, 1)[0] == 1, f'{which}, starting={starting}: Bluetooth stays on, Wi-Fi is on')
            m.switch_on(which, starting, yes=False)
            expect([c for c in m.sw if c[0] != 'getFormatString'] == [] and m.exit_writes == [] and m.u.mem_read(BT_FLAG, 1)[0] == 1 and m.u.mem_read(WIFI_FLAG, 1)[0] == 0,
                   f'{which}, starting={starting}, Cancel: nothing is called or written, Wi-Fi stays off: {m.sw}')
        m.switch_on(which, False, yes=True, bt=False)
        expect([c[0] for c in m.sw] == ['wifi_switch'], f'{which}: Bluetooth off: no warning, wifi_switch(1) ({m.sw})')


def scrim_tests(ctx):
    """The confirm dialog over the page (docs/modules/overlays.md): while the modal dialog is up, a full-window view of #00000082 is the top main window's last child,
    insensitive; it is hidden, made insensitive and destroyed when the call returns, Yes or No. Nothing is touched when the page closed meanwhile or the view failed."""
    expect = ctx.expect
    DIM = 0x82000000   # #00000082 as the uint32 value_t holds
    CONFIRM = 'Delete all measured track durations? They will be measured again on Home.'

    def page(m, w=320, h=450):
        win = m.alloc(0x80); m.u.mem_write(win, bytes(0x80))
        m.setword(win + O['W_W'], w); m.setword(win + O['W_H'], h)
        m.top_main = win; m.children[m.wm] = [win]
        return win

    def at(m, pred): return [i for i, c in enumerate(m.calls) if pred(c)]

    m = Machine(); win = page(m); snap = []
    m.on_confirm = lambda mm: snap.append(list(mm.children.get(win, [])))
    for yes in (False, True):
        m.confirm_yes = yes; snap.clear(); n0 = len(getattr(m, 'styled', []))
        m.call(PSYMS['durations_clear_ask'], count=3000000)
        made = [c[1] for c in m.calls if c[0] == 'view_create']
        scrim = made[0] if len(made) == 1 else 0
        dim = [s for s in getattr(m, 'styled', [])[n0:] if s[0] == scrim and s[1] == 'normal:bg_color']
        ask, shown = at(m, lambda c: c[0] == 'confirm'), at(m, lambda c: c[0] == 'widget_destroy' and c[1] == scrim)
        expect(scrim and [c[1] for c in m.calls if c[0] == 'confirm'] == [CONFIRM], f'Yes={yes}: one scrim view is made for the confirm ({made})')
        expect(snap and snap[0][-1] == scrim and m.props.get((scrim, 'w')) == 320 and m.props.get((scrim, 'h')) == 450 and m.props.get((scrim, 'x')) == 0,
               f'Yes={yes}: while the dialog is up the scrim is the window\'s last child, the window\'s size ({snap})')
        expect(dim and dim[-1][2] == DIM, f'Yes={yes}: the scrim is #00000082 ({dim})')
        expect(at(m, lambda c: c == ('widget_set_sensitive', scrim, 0)) and at(m, lambda c: c == ('widget_set_sensitive', scrim, 0))[0] < ask[0],
               f'Yes={yes}: the scrim takes no input, from before the dialog')
        hid = at(m, lambda c: c == ('widget_set_visible', scrim, 0))
        expect(hid and shown and hid[0] < shown[0] and shown[0] > ask[0],
               f'Yes={yes}: hidden, insensitive and destroyed after the dialog returned')
        expect(scrim not in m.children.get(win, []), f'Yes={yes}: no scrim is left on the page')
    expect(sum(1 for c in m.calls if c[0] == 'widget_destroy') == 1, 'the last call destroys the scrim and nothing else')

    # the page closed while the dialog is up: the window manager no longer holds it, so the scrim (freed with it) is never touched
    m = Machine(); win = page(m)
    m.on_confirm = lambda mm: mm.children.__setitem__(mm.wm, [])
    m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    scrim = [c[1] for c in m.calls if c[0] == 'view_create']
    expect(scrim and not [c for c in m.calls if c[0] in ('widget_destroy', 'widget_set_visible') and c[1] == scrim[0]] and [c for c in m.calls if c[0] == 'confirm'],
           'the page closed under the dialog: nothing is done to the scrim after the call')

    # no top main window: no scrim, the dialog still opens; a view that cannot be made: the dialog opens without one
    m = Machine(); m.top_main = 0; m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect(not [c for c in m.calls if c[0] == 'view_create'] and [c for c in m.calls if c[0] == 'confirm'], 'no page to dim: the confirm still opens, no view is made')
    m = Machine(); page(m); m.create_fail.add('view_create'); m.confirm_yes = True
    m.call(PSYMS['durations_clear_ask'], count=3000000)
    expect([c for c in m.calls if c[0] == 'confirm'] and not [c for c in m.calls if c[0] == 'widget_destroy'], 'a view that cannot be made: the confirm still opens, nothing is destroyed')

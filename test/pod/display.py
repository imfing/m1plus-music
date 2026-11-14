"""Settings > System > Display (patch/display.c, docs/modules/settings.md "Display"): our page in place of stock's Display list and its four pages. The brightness card (stock's own slider
handlers bound to our slider), Screen Timeout (stock's backlight time), LED Light and Follow Screen (stock's lamp mode and switch): each state is stock's and is written the way stock's
own page writes it, which the tests check by running stock's handlers under the emulator on the same state."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

MODE, LED, FOLLOW, LIGHTNESS, CHANGEFLAG = pod.DATA['LIGHT_MODE'][0], pod.DATA['LED_MODE'][0], pod.DATA['LED_FOLLOW'][0], pod.DATA['LIGHTNESS'][0], 0xa05a38
STOCK_ROWS = (0x4a8708, 0x4a86a4, 0x4a8640, 0x4a85dc, 0x4a8578)   # stock's systemset/lighttime_page click handlers, row 1 (index 0) .. row 5 (index 4)
LED_SWITCH, LED_ORANGE, LED_BLUE, LED_FOLLOW = 0x4a1c30, 0x4a1e14, 0x4a1d8c, 0x4a1940   # stock's systemset/atmosphereled_page click handlers (the window in a0); stock's "orange" (img_orange) is the green lamp
B_REFRESH, B_CHANGED, B_CHANGING = (pod.DATA[n][0] for n in ('BRIGHT_REFRESH', 'BRIGHT_CHANGED', 'BRIGHT_CHANGING'))
TEXTS = ('Never', '15s', '30s', '1min', '5min')
WIN = 0x30000000
# leaves stock's handlers reach that the base machine does not mock: (address, name)
LEAVES = {0x742da0: 'memset', 0x70f8d8: 'tk_snprintf', 0x669320: 'widget_set_enable', 0x5e4f10: 'toolSetBackLight', 0x6316dc: 'slider_set_value'}


class DM(Machine):
    """Stock's handlers and refresh run for real, with the leaves above recorded."""
    def __init__(self):
        super().__init__()
        for a, n in LEAVES.items(): self.handlers[a] = n   # (stock's refresh converts the value to a double: the base machine has the FPU on)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in ('tk_snprintf', 'widget_set_enable', 'toolSetBackLight', 'slider_set_value', 'reset_atmosphereled_rgb'): return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = 0
        if name == 'tk_snprintf':   # (buffer, size, format, one integer)
            text = self.read_cstr(a2) % a3
            u.mem_write(a0, text.encode() + b'\0'); ret = len(text)
        elif name == 'slider_set_value': self.calls.append((name, a0, struct.unpack('<d', struct.pack('<II', a2, a3))[0]))   # (widget, a double in a2 / a3)
        elif name == 'reset_atmosphereled_rgb': self.calls.append((name, self.u.mem_read(LED, 1)[0]))   # the lamp follows the byte as it is at the call
        elif name == 'toolSetBackLight': self.calls.append((name, a0))   # (one argument)
        else: self.calls.append((name, a0, a1))
        u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]


def machine(mode=0, led=0, follow=0):
    m = DM()
    m.setword(MODE, mode & 0xffffffff)
    m.u.mem_write(LED, bytes([led & 0xff])); m.u.mem_write(FOLLOW, bytes([follow & 0xff]))
    return m


def saves(m):
    """What reaches stock's state: the saves and the calls that apply them, in order."""
    return [c[:4] for c in m.calls if c[0] in ('write_int_config', 'reset_poweroptions_timer', 'reset_atmosphereled_rgb', 'toolSetBackLight')]


def timeout_tests(ctx):
    """disp_light / disp_light_set against stock's own row handlers, run for real on the same state."""
    expect = ctx.expect
    expect(pod.DATA['LIGHT_MODE'] == (0xa05a7c, 'backlighttime_mode'), 'LIGHT_MODE is stock\'s backlighttime_mode (checked against demo\'s dynsym by the build)')
    pins = {a: w for a, w, _ in pod.LOCKSCREEN_PINS}
    expect(all(a in pins for a in (0x4a84b8, 0x4a84bc, 0x4a84c0, 0x4a8540, 0x4a8544, 0x4a8548, 0x4a854c, 0x4a85b4, 0x4a85bc, 0x4a85c4, 0x4a85c8, 0x4e60d4, 0x4e60f0)),
           'the handler\'s read, compare, store, save and countdown call, and config_init\'s 0 .. 4 clamp are pinned')
    for mode, want in ((0, 0), (1, 1), (4, 4), (5, 0), (-1, 0), (0x7fffffff, 0)):
        expect(machine(mode).call(PSYMS['disp_light'], count=200000) == want, f'the word {mode}: index {want}')
    for old in range(5):
        for new in range(5):
            ms = machine(old); ms.call(STOCK_ROWS[new], a0=WIN, count=2000000)   # stock's handler (the window in a0; its row images are mocked lookups)
            mo = machine(old); r = mo.call(PSYMS['disp_light_set'], a0=new, count=2000000)
            want = [] if old == new else [('write_int_config', new, 'SYSSET', 'LIGHTTIME'), ('reset_poweroptions_timer', 0, 0, 1)]
            expect(r == 0 and mo.word(MODE) == ms.word(MODE) == new and saves(mo) == saves(ms) == want, f'{old} -> {new}: the word and the calls are stock\'s ({saves(mo)} / {saves(ms)})')

    class SM(DM):
        """The word as write_int_config sees it (stock stores it before the call)."""
        def _hook(self, u, address, size, _):
            if self.handlers.get(address) == 'write_int_config': self.seen = self.word(MODE)
            return super()._hook(u, address, size, _)

    ms = SM(); ms.setword(MODE, 1); ms.call(STOCK_ROWS[3], a0=WIN, count=2000000)
    mo = SM(); mo.setword(MODE, 1); mo.call(PSYMS['disp_light_set'], a0=3, count=2000000)
    expect(mo.seen == ms.seen == 3, 'the word is stored before the save, as in stock')
    for bad in (-1, 5, 100):
        m = machine(2)
        expect(m.call(PSYMS['disp_light_set'], a0=bad & 0xffffffff, count=200000) == 0xffffffff and m.word(MODE) == 2 and not saves(m), f'index {bad}: refused, nothing written')


def led_tests(ctx):
    """disp_led / disp_led_set / disp_follow_toggle against stock's switch, colour and Follow Screen handlers."""
    expect = ctx.expect
    expect(pod.DATA['LED_MODE'] == (0xa05a75, 'atmosphereled_mode') and pod.DATA['LED_FOLLOW'] == (0xa05a74, 'ledfollowscreen_flag'), 'the two bytes are stock\'s (checked against demo\'s dynsym by the build)')
    pins = {a: w for a, w, _ in pod.LOCKSCREEN_PINS}
    expect(all(a in pins for a in (0x4a1ca8, 0x4a1cbc, 0x4a1d60, 0x4a1d04, 0x4a1d18, 0x4a1db8, 0x4a1dd0, 0x4a1e40, 0x4a1e58, 0x4a1964, 0x4a197c, 0x4a1980, 0x4a1984, 0x4a1988, 0x4e6718, 0x4e6b9c)),
           'the switch\'s and the colours\' stores, the save\'s key, the lamp call, Follow Screen\'s xor, order and key, and config_init\'s clamp are pinned')

    def stock(led, handler):
        m = machine(led=led)
        for n in ('image_switch', 'view', 'img_orange', 'img_blue', 'img_followscreen'): m.widget(n)   # the page's widgets: the handlers return early without them
        m.call(handler, a0=WIN, count=3000000)
        return m

    for v, want in ((0, 0), (1, 1), (2, 2), (3, 0), (0xff, 0)):
        expect(machine(led=v).call(PSYMS['disp_led'], count=200000) == want, f'the byte {v}: mode {want}')
    # every change stock's page can make, made by ours: the same byte, the same save, the same lamp call (which sees the new byte)
    for old, new, handler, what in ((1, 0, LED_SWITCH, 'the switch off from green'), (2, 0, LED_SWITCH, 'the switch off from blue'), (0, 1, LED_SWITCH, 'the switch on (green)'),
                                    (2, 1, LED_ORANGE, 'green from blue'), (1, 2, LED_BLUE, 'blue from green'), (1, 1, LED_ORANGE, 'green again'), (2, 2, LED_BLUE, 'blue again')):
        ms = stock(old, handler)
        mo = machine(led=old); r = mo.call(PSYMS['disp_led_set'], a0=new, count=2000000)
        want = [] if old == new else [('write_int_config', new, 'SYSSET', 'ATMOSPHERELEDMODE'), ('reset_atmosphereled_rgb', new)]
        expect(r == 0 and mo.byte(LED) == ms.byte(LED) == new and saves(mo) == saves(ms) == want, f'{what}: the byte and the calls are stock\'s ({saves(mo)} / {saves(ms)})')
    m = machine(led=0); r = m.call(PSYMS['disp_led_set'], a0=2, count=2000000)
    expect(r == 0 and m.byte(LED) == 2 and saves(m) == [('write_int_config', 2, 'SYSSET', 'ATMOSPHERELEDMODE'), ('reset_atmosphereled_rgb', 2)], 'blue from off: one step (stock\'s page needs its switch, then the colour)')
    m = machine(led=0); r = m.call(PSYMS['disp_led_set'], a0=0, count=2000000)
    expect(r == 0 and not saves(m), 'off while off writes nothing')
    for bad in (-1, 3, 9):
        m = machine(led=1)
        expect(m.call(PSYMS['disp_led_set'], a0=bad & 0xffffffff, count=200000) == 0xffffffff and m.byte(LED) == 1 and not saves(m), f'mode {bad}: refused, nothing written')

    class FM(DM):
        """The byte as write_int_config sees it (stock stores it in the call's delay slot)."""
        def _hook(self, u, address, size, _):
            if self.handlers.get(address) == 'write_int_config': self.seen = self.byte(FOLLOW)
            return super()._hook(u, address, size, _)

    for st in (0, 1):
        ms = FM(); ms.u.mem_write(FOLLOW, bytes([st])); ms.call(LED_FOLLOW, a0=WIN, count=2000000)
        mo = FM(); mo.u.mem_write(FOLLOW, bytes([st])); r = mo.call(PSYMS['disp_follow_toggle'], count=2000000)
        expect(r == 1 - st and mo.byte(FOLLOW) == ms.byte(FOLLOW) == 1 - st and mo.seen == ms.seen == 1 - st and saves(mo) == saves(ms) == [('write_int_config', 1 - st, 'SYSSET', 'LEDFOLLOWSCREEN')],
               f'Follow Screen from {st}: the byte before the save and the one call are stock\'s ({saves(mo)} / {saves(ms)})')
        expect(machine(follow=st).call(PSYMS['disp_follow'], count=200000) == st, f'the byte {st}: the switch shows {st}')


def brightness_tests(ctx):
    """The brightness card: stock's two handlers bound to our slider, and what they do through our asset's widget names."""
    expect = ctx.expect
    expect((B_REFRESH, B_CHANGED, B_CHANGING) == (0x4a4450, 0x4a4678, 0x4a4744) and (O['EVT_VALUE_CHANGED'], O['EVT_VALUE_CHANGING']) == (0x11c, 0x11d) and pod.DATA['LIGHTNESS'] == (0x97caf0, 'lightness'),
           'stock\'s refresh and its two handlers, the events stock binds them to, and the word they write')
    pins = {a: w for a, w, _ in pod.LOCKSCREEN_PINS}
    expect(pins.get(0x4a43ac) == 0x2405011d and pins.get(0x4a43bc) == 0x24c64744 and pins.get(0x4a43c0) == 0x2405011c and pins.get(0x4a43d0) == 0x24c64678 and all(a in pins for a in (B_REFRESH, B_CHANGED, B_CHANGING, 0x4a46b8, 0x4a4780)),
           'stock\'s own bindings (0x11d -> 0x4a4744, 0x11c -> 0x4a4678), the three entries and the 0 .. 100 tests are pinned')
    # the payload: refresh first, then the two handlers on the slider with the window as their context, as stock's page binds them
    m = DM(); s = m.widget('slider_brightness'); m.widget('label_brightness'); m.setword(LIGHTNESS, 42)
    m.call(PSYMS['disp_opened'], a0=WIN, count=2000000)
    seq = [c for c in m.calls if c[0] in ('slider_set_value', 'widget_on')]
    expect(seq == [('slider_set_value', s, 42.0), ('widget_on', s, 0x11d, B_CHANGING, WIN), ('widget_on', s, 0x11c, B_CHANGED, WIN)] and not saves(m), f'the page opens: stock\'s refresh (the slider at 42), then stock\'s handlers bound; nothing saved ({seq})')
    m.setword(LIGHTNESS, 80); m.call(PSYMS['disp_refresh'], a0=WIN, count=2000000)
    expect([c for c in m.calls if c[0] == 'slider_set_value'] == [('slider_set_value', s, 80.0)], 'back in front: stock\'s refresh again, the slider follows the word (the pull-down changes it)')
    for missing in ('slider_brightness', 'label_brightness'):
        m = DM(); m.widget('label_brightness' if missing == 'slider_brightness' else 'slider_brightness')
        m.call(PSYMS['disp_opened'], a0=WIN, count=2000000); m.call(PSYMS['disp_refresh'], a0=WIN, count=2000000)
        expect(not [c for c in m.calls if c[0] in ('slider_set_value', 'widget_on')], f'a page without {missing}: nothing bound, nothing called')
    m = DM(); m.call(PSYMS['disp_opened'], a0=0, count=200000)
    expect(not m.calls, 'no window: nothing')

    # stock's code on our widget names: the refresh sets our slider from the word; a drag stores the word and the pending flag only; the release sets the backlight and saves
    def real(lightness):
        m = DM(); m.setword(LIGHTNESS, lightness)
        return m, m.widget('slider_brightness'), m.widget('label_brightness')

    m, s, lab = real(37); m.call(B_REFRESH, a0=WIN, count=3000000)
    expect(('slider_set_value', s, 37.0) in m.calls and ('widget_set_text_utf8', lab, '37%') in m.calls and not saves(m), 'the refresh: our slider at the word lightness (37), the hidden label written, nothing saved')

    def event(m, s, value):
        e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x10, s)   # the event's target
        m.props[(s, 'value')] = value
        return e

    m, s, lab = real(37); m.u.mem_write(CHANGEFLAG, b'\0')
    m.call(B_CHANGING, a0=WIN, a1=event(m, s, 60), count=3000000)
    expect(m.word(LIGHTNESS) == 60 and m.byte(CHANGEFLAG) == 1 and saves(m) == [('reset_poweroptions_timer', 1, 1, 1)] and ('slider_set_value', s, 60.0) in m.calls,
           f'a drag to 60: the word, the pending flag, the timers; no save and no backlight call yet ({saves(m)})')
    m.call(B_CHANGED, a0=WIN, a1=event(m, s, 60), count=3000000)
    expect(m.word(LIGHTNESS) == 60 and m.byte(CHANGEFLAG) == 0 and saves(m) == [('toolSetBackLight', 61), ('write_int_config', 60, 'SYSSET', 'LIGHTNESS'), ('reset_poweroptions_timer', 1, 1, 1)],
           f'the release: the backlight (value + 1), [SYSSET] LIGHTNESS, the timers ({saves(m)})')
    m, s, lab = real(37); m.call(B_CHANGED, a0=WIN, a1=event(m, s, 101), count=3000000)
    expect(m.word(LIGHTNESS) == 37 and not saves(m), 'a value above 100 is ignored by stock\'s handler')


def settings_tests(ctx):
    """The Settings row, the Display page, the pickers, the switch, the texts and the assets."""
    expect, P = ctx.expect, pod_pages
    V, D, L, E = P.SETTINGS_PAGE, P.DISPLAY_PAGE, P.LIGHTTIME_PAGE, P.LED_PAGE
    labels = [r.label for r in V.rows]
    di = labels.index('Display')
    expect(V.rows[di].action == P.ACT_PAGE and V.rows[di].arg == P.DISPLAY_PAGE_INDEX == 70 and P.row_kind(V.rows[di]) == 'link' and labels[di + 1] == 'Buttons & Power',
           'Settings > System > Display opens our page')
    lay = [x.label if isinstance(x, P.Row) else x for x in V.layout]
    expect(lay[-4:] == ['About', P.GAP, 'All System Settings', 'Developer'], f'the last card: All System Settings, then Developer ({lay[-4:]})')
    expect(P.PAGES[P.DISPLAY_PAGE_INDEX] is D and P.PAGES[P.LIGHTTIME_PAGE_INDEX] is L and P.PAGES[P.LED_PAGE_INDEX] is E and (P.LIGHTTIME_PAGE_INDEX, P.LED_PAGE_INDEX) == (71, 72)
           and (D.key, D.title, L.key, L.title, E.key, E.title) == ('m1plus_display', 'Display', 'm1plus_lighttime', 'Screen Timeout', 'm1plus_ledlight', 'LED Light'), 'the three pages')
    expect([(r.label, r.action, r.arg) for r in D.rows] == [('Screen Timeout', P.ACT_LIGHT, P.LIGHTTIME_PAGE_INDEX), ('Lock Screen', P.ACT_PAGE, P.LOCK_PAGE_INDEX), ('LED Light', P.ACT_LED, P.LED_PAGE_INDEX), ('Follow Screen', P.ACT_LEDFOLLOW, 0)]
           and [P.row_kind(r) for r in D.rows] == ['value', 'link', 'value', 'switch'], 'the Display page\'s rows: Screen Timeout, Lock Screen, LED Light, Follow Screen')
    dl = [x.label if isinstance(x, P.Row) else 'brightness' if isinstance(x, P.Brightness) else x for x in D.layout]
    expect(dl == ['brightness', P.GAP, 'Screen Timeout', 'Lock Screen', P.GAP, 'LED Light', 'Follow Screen'], f'three cards: the brightness slider; Screen Timeout + Lock Screen; LED Light + Follow Screen ({dl})')
    expect([(r.label, r.action, r.arg) for r in L.rows] == [(t, P.ACT_LIGHTSET, i) for i, t in enumerate(TEXTS)] and all(P.row_kind(r) == 'check' for r in L.rows) and P.LIGHTTIME_VALUES == TEXTS,
           'the Screen Timeout picker: stock\'s five choices in stock\'s order, the argument is stock\'s index')
    expect([(r.label, r.action, r.arg) for r in E.rows] == [('Off', P.ACT_LEDSET, 0), ('Green', P.ACT_LEDSET, 1), ('Blue', P.ACT_LEDSET, 2), ('Sample Rate', P.ACT_LEDSET, 3)] and all(P.row_kind(r) == 'check' for r in E.rows),
           'the LED Light picker: stock Off, Green and Blue plus Sample Rate')
    expect((P.ACT_LIGHT, P.ACT_LIGHTSET, P.ACT_LED, P.ACT_LEDSET, P.ACT_LEDFOLLOW) == (97, 98, 99, 100, 101) and {P.ACT_LIGHT, P.ACT_LED} <= set(P.VALUE_ACTIONS) and {P.ACT_LIGHTSET, P.ACT_LEDSET} <= set(P.CHECK_ACTIONS)
           and P.ACT_LEDFOLLOW in P.SWITCH_ACTIONS, 'the actions')
    expect(len(P.STOCK_PAGES) == 2 and not any(n.split('/')[-1] in ('display_page', 'brightness_page', 'lighttime_page', 'atmosphereled_page', 'screensaver_page') for n, *_ in P.STOCK_PAGES)
           and not [r for r in D.rows if r.action == P.ACT_STOCK] and not any(r.label == 'Lock Screen' for r in P.APPEARANCE_PAGE.rows),
           'no row opens stock\'s Display list or any of its four pages; Lock Screen is on Display only')
    stock_ui = os.path.join(paths.find_stock(), 'rootfs/release/assets/default/raw/ui')
    lt = awtk_ui.parse(open(os.path.join(stock_ui, 'systemset/lighttime_page.bin'), 'rb').read())
    expect([lt.find(f'ltime_scrlabel{i}').get('text') for i in range(2, 6)] == list(TEXTS[1:]), 'the four timed choices are the texts of stock\'s page')
    import pod_i18n
    import mod_icons
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in ('Display', 'Screen Timeout', 'Lock Screen', 'LED Light', 'Follow Screen', 'Never', 'Off', 'Green', 'Blue')), f'the page texts have a translation in {loc}')
    expect(all(pod_i18n.key_for(t) is None for t in TEXTS[1:]) and pod_i18n.key_for('Never') == 'Never', '15s .. 5min are plain texts, Never is a key')
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Screen Timeout', 'Lock Screen', 'LED Light', 'Follow Screen')] == ['timer', 'lock', 'lightbulb', 'smartphone'], 'the glyphs')

    def page(index, nrows, kinds=('pod_check', 'pod_label'), **state):
        m = machine(**state)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row',) + tuple(kinds) for i in range(nrows)])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, index)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    def checks(m, n):
        out = []
        for i in range(n):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out
    # the Screen Timeout picker
    for mode in range(5):
        m = page(P.LIGHTTIME_PAGE_INDEX, 5, mode=mode)
        expect(('window_open', L.key) in m.calls and checks(m, 5) == [int(i == mode) for i in range(5)] and not saves(m), f'the word {mode}: the picker\'s check {checks(m, 5)}, nothing written')
    m = page(P.LIGHTTIME_PAGE_INDEX, 5, mode=2)
    m.click('pod_row4')
    expect(m.word(MODE) == 4 and saves(m) == [('write_int_config', 4, 'SYSSET', 'LIGHTTIME'), ('reset_poweroptions_timer', 0, 0, 1)] and checks(m, 5) == [0, 0, 0, 0, 1], 'a tap on 5min: stock\'s word, save and countdown, the check follows')
    m.calls = []; m.click('pod_row4')
    expect(m.word(MODE) == 4 and not saves(m), 'a tap on the chosen row writes nothing')
    m.click('pod_row0')
    expect(m.word(MODE) == 0 and saves(m)[-2:] == [('write_int_config', 0, 'SYSSET', 'LIGHTTIME'), ('reset_poweroptions_timer', 0, 0, 1)] and checks(m, 5) == [1, 0, 0, 0, 0], 'Never: index 0')
    # the LED Light picker
    for led in range(3):
        m = page(P.LED_PAGE_INDEX, 4, led=led)
        expect(('window_open', E.key) in m.calls and checks(m, 4) == [int(i == led) for i in range(4)] and not saves(m), f'the byte {led}: the LED picker\'s check {checks(m, 4)}, nothing written')
    m = page(P.LED_PAGE_INDEX, 4, led=0)
    m.click('pod_row2')
    expect(m.byte(LED) == 2 and saves(m) == [('write_int_config', 2, 'SYSSET', 'ATMOSPHERELEDMODE'), ('reset_atmosphereled_rgb', 2)] and checks(m, 4) == [0, 0, 1, 0], 'a tap on Blue: stock\'s byte, save and lamp call, the check follows')
    m.click('pod_row0')
    expect(m.byte(LED) == 0 and saves(m) == [('write_int_config', 0, 'SYSSET', 'ATMOSPHERELEDMODE'), ('reset_atmosphereled_rgb', 0)] and checks(m, 4) == [1, 0, 0, 0], 'Off: the lamp call with the byte 0')
    # the Display page: the two values, the switch, the Lock Screen row, the brightness card
    DK = ('pod_value', 'pod_label', 'pod_switch')

    def value(m, i):
        got = [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_tr_text') and c[1] == m.widgets[f'pod_value{i}']]
        return got, [t for n, t in got if n == 'widget_set_tr_text']   # (the machine records a translated text as a plain one too)
    for mode in range(5):
        got, tr = value(page(P.DISPLAY_PAGE_INDEX, 4, DK, mode=mode), 0)
        expect(tr == (['Never'] if mode == 0 else []) and got[-1][1] == TEXTS[mode] and len(got) == 1 + len(tr), f'the word {mode}: the Screen Timeout row shows {got}')
    for led, want in ((0, 'Off'), (1, 'Green'), (2, 'Blue'), (7, 'Off')):
        got, tr = value(page(P.DISPLAY_PAGE_INDEX, 4, DK, led=led), 2)
        expect(tr == [want], f'the byte {led}: the LED Light row shows {tr}')

    def sw_images(m): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets['pod_switch3']]
    for st, img in ((0, 'sset_off'), (1, 'sset_on')):
        m = page(P.DISPLAY_PAGE_INDEX, 4, DK, follow=st)
        expect(sw_images(m) == [img] and not saves(m), f'Follow Screen opens {img} with the byte {st}, nothing written')
    m = page(P.DISPLAY_PAGE_INDEX, 4, DK, follow=0)
    m.click('pod_row3')
    expect(m.byte(FOLLOW) == 1 and saves(m) == [('write_int_config', 1, 'SYSSET', 'LEDFOLLOWSCREEN')] and sw_images(m) == ['sset_on'], 'a tap turns Follow Screen on: the byte, the save, the switch')
    m.click('pod_row3')
    expect(m.byte(FOLLOW) == 0 and saves(m) == [('write_int_config', 0, 'SYSSET', 'LEDFOLLOWSCREEN')] and sw_images(m) == ['sset_off'], 'and off again')
    m = page(P.DISPLAY_PAGE_INDEX, 4, DK); m.calls = []
    m.click('pod_row1')
    expect([c[1] for c in m.calls if c[0] == 'window_open'] == [P.LOCK_PAGE.key] and 'navigator_to' not in m.names(), 'the Lock Screen row opens our Lock Screen page')
    m = machine(); m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer', 'slider_brightness', 'label_brightness'])}
    row = m.alloc(12); m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.DISPLAY_PAGE_INDEX)
    m.call(PSYMS['on_row'], a0=row, count=6000000)
    s = m.widgets['slider_brightness']
    expect([c[1:4] for c in m.calls if c[0] == 'widget_on' and c[1] == s] == [(s, 0x11d, B_CHANGING), (s, 0x11c, B_CHANGED)] and 'slider_set_value' in m.names(), 'opening the Display page binds stock\'s handlers to the slider and refreshes it')
    # the assets
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    dt = awtk_ui.parse(open(os.path.join(raw, 'm1plus_display.bin'), 'rb').read())
    pt = awtk_ui.parse(open(os.path.join(raw, 'm1plus_lighttime.bin'), 'rb').read())
    et = awtk_ui.parse(open(os.path.join(raw, 'm1plus_ledlight.bin'), 'rb').read())
    st = awtk_ui.parse(open(os.path.join(raw, 'm1plus_settings.bin'), 'rb').read())
    pd = awtk_ui.parse(open(os.path.join(raw, 'dialog/dropdown_dialog.bin'), 'rb').read())
    expect([dt.find(f'pod_row{i}').find('pod_icon').get('image') for i in range(4)] == ['pod_ci_timer', 'pod_ci_lock', 'pod_ci_lightbulb', 'pod_ci_smartphone'] and dt.find('label_title').get('tr_text') == 'Display'
           and st.find(f'pod_row{di}').find('pod_icon').get('image') == 'pod_ci_sun', 'the page asset: the four glyphs and the title')
    sl, lab, ps = dt.find('slider_brightness'), dt.find('label_brightness'), pd.find('slider_backlight')
    look = lambda w: {k: v for k, v in w.props if (k.startswith('style:') and not k.endswith(':icon')) or k in ('slide_with_bar', 'dragger_size', 'dragger_adapt_to_icon')}
    expect(sl is not None and sl.type == 'slider' and sl.get('max') == '100' and sl.get('step') == '1' and (sl.w, sl.h) == (ps.w, ps.h) and look(sl) == look(ps),
           'the slider: stock\'s name and its 0 .. 100 range, the size, the track and the fill of the pull-down\'s brightness slider')
    from PIL import Image
    img = lambda n: Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', n + '.png')).convert('RGBA')
    th, track = img('pod_sl_thumb'), img('drop_bg')
    box = th.getchannel('A').point(lambda a: 255 if a >= 250 else 0).getbbox()
    expect({v for k, v in sl.props if k.endswith(':icon')} == {'pod_sl_thumb'} and sl.get('bar_size') == str(track.height) == '6' and mod_icons.SLIDER_THUMB == ('pod_sl_thumb', 38, 24, 46, 34) and th.size == (46, 34)
           and (box[2] - box[0], box[3] - box[1]) in ((38, 24), (38, 22), (36, 24), (36, 22)) and th.getpixel((23, 17)) == (255, 255, 255, 255) and th.getpixel((0, 0))[3] == 0 and 0 < th.getpixel((23, 31))[3] < 255,
           f'the thumb: our white capsule (38 x 24 in a 46 x 34 canvas, a soft shadow under it) on a bar as high as the track image ({box})')
    expect(lab is not None and lab.get('visible') == 'false' and lab.get('sensitive') == 'false', 'label_brightness (stock\'s refresh needs it) is hidden and insensitive')
    card = dt.find('pod_bright')
    expect(card.h == dt.find('pod_row0').h and [card.find(n).get('image') for n in ('pod_bright_lo', 'pod_bright_hi')] == ['drop_lighticon0', 'drop_lighticon1']
           and card.find('pod_bright_lo').x == dt.find('pod_row0').find('pod_icon').x + 2 and sl.x == dt.find('pod_label0').x and card.find('pod_bright_hi').x + card.find('pod_bright_hi').w == 296,
           'the card: a row high, the small sun in the glyph column, the slider from the label column, the large sun at the card\'s right padding')
    for tree, n, title, first in ((pt, 5, 'Screen Timeout', 'Never'), (et, 4, 'LED Light', 'Off')):
        expect(all(tree.find(f'pod_check{i}').get('visible') == 'false' and tree.find(f'pod_check{i}').get('sensitive') == 'false' for i in range(n)) and tree.find('label_title').get('tr_text') == title
               and tree.find('pod_label0').get('tr_text') == first, f'the {title} picker asset: {n} rows, a hidden insensitive check each')
    expect([pt.find(f'pod_label{i}').get('text') for i in range(1, 5)] == list(TEXTS[1:]) and [et.find(f'pod_label{i}').get('tr_text') for i in range(4)] == ['Off', 'Green', 'Blue', 'Sample Rate'],
           'the times as stock writes them; the lamp modes translated')


SECTIONS = [timeout_tests, led_tests, brightness_tests, settings_tests]

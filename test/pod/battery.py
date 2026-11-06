"""Battery Percentage (patch/battery.c, docs/modules/battery.md "The percentage"): the one hook at show_sysbar_face's call of get_battery_capacity (0x5450f8), run against the
mocked stock function; the Settings switch; the hidden label in the status bar and both pull-down bars and the layout it makes."""
import os, re, struct
import paths
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DEFS = {}
for _line in open(os.path.join(ROOT, 'patch', 'battery.h')).read().replace('\\\n', ' ').splitlines():
    _m = re.match(r'#define\s+(\w+)\s+("[^"]*"|\w+)\s*(?:/\*.*)?$', _line.strip())
    if _m: DEFS[_m.group(1)] = _m.group(2).strip('"') if _m.group(2).startswith('"') else int(_m.group(2), 0)
FILE, GAUGE, KILL = DEFS['BP_FILE'], DEFS['BP_GAUGE'], '/mnt/mmc/m1plus-off'
LABEL, LABEL_DD = DEFS['BP_LABEL'], DEFS['BP_LABEL_DD']
STOCK_CAP = 40


class BM(Machine):
    COUNT = True   # the instruction count (icount) the cost tests read


def machine(setting=b'1\n', gauge=b'87\n', labels=True, cap=STOCK_CAP, w=32):
    """A machine with the status bar's label and the pull-down's twin (width w at +8, a parent at +0x44), the setting file, the gauge file and stock's capacity."""
    m = BM()
    m.mem_geometry = True
    m.stock_cap = cap
    if setting is not None: m.fs[FILE] = setting
    if gauge is not None: m.fs[GAUGE] = gauge
    if labels:
        for name in (LABEL, LABEL_DD):
            h = m.widget(name); m.setword(h + DEFS['BP_W_W'], w); m.setword(h + DEFS['BP_W_H'], 30); m.setword(h + DEFS['BP_W_PARENT'], 0x31000000)
    for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG'): m.setword(pod.DATA[k][0], 0)   # on battery (the demo's data starts with its own values)
    bar = m.alloc(0x80); m.setword(pod.DATA['SYSTEM_BAR'][0], bar)
    return m


def tick(m):
    return m.call(PSYMS['bp_capacity'], count=200000)


def power(m): return m.s32(pod.DATA['POWER_CAPACITY'][0])


def texts(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8']


def vis(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'widget_set_visible']


def run(ctx):
    expect = ctx.expect
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    P = pod_pages

    # 1. The hook: one call-site word, everything around it stock's.
    site = pod.BATTERY_SITE
    expect(site == 0x5450f8 and w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['bp_capacity'],
           'the build replaced stock\'s `jalr t9` (get_battery_capacity) at 0x5450f8 by `jal bp_capacity`')
    expect(all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old, _ in pod.BATTERY_PINS),
           'every pinned word (show_sysbar_face, get_battery_capacity, the widget_t fields) is stock\'s in the stock demo and unchanged in the build, but the site')
    expect(w(built, 0x5450fc) == 0 and w(built, 0x5450f0) == 0x8fbc0010 and w(built, 0x545104) == 0x8fbc0010, 'the delay slot is still a nop and $gp is still reloaded from the stack after the call')
    expect(MANIFEST['hook_battery'] == {'addr': site, 'target': PSYMS['bp_capacity']}, 'the manifest records the hook')
    expect(pod.DATA['POWER_CAPACITY'][0] == 0xa059ec and pod.FUNCTIONS['get_battery_capacity'][2] == 0x4e6dd8, 'power_capacity and get_battery_capacity are the pinned addresses')
    expect(DEFS['BP_W_W'] == 8 and DEFS['BP_W_H'] == 0xc and DEFS['BP_W_PARENT'] == 0x44 and DEFS['BP_FILE'] == '/mnt/data/m1plus/battery-percentage'
           and DEFS['BP_GAUGE'] == '/sys/class/power_supply/battery/capacity', 'the widget_t offsets and the two files')

    # 2. Off (the default): stock's value, no label touched, no gauge read.
    for setting in (None, b'0\n', b'x', b''):
        m = machine(setting=setting)
        v = tick(m)
        expect(v == STOCK_CAP and power(m) == STOCK_CAP and texts(m) == [] and vis(m) == []
               and ('open', GAUGE, 0) not in m.calls and not any(c[0] == 'widget_lookup' for c in m.calls),
               f'setting {setting!r}: stock\'s capacity ({STOCK_CAP}) returned and left in power_capacity, no label touched, no lookup, the gauge not read')
    m = machine(setting=None); tick(m); m.calls = []; tick(m)
    expect(m.names() == ['get_battery_capacity', 'access'] and m.icount < 400, f'off, steady state: stock\'s function and the kill switch test only ({m.names()}, {m.icount} instructions)')

    # 3. On with a valid gauge: the real percentage, in power_capacity and the return value; the label shows "N%".
    for text, pct in ((b'87\n', 87), (b'87', 87), (b'0\n', 0), (b'5\n', 5), (b'6\n', 6), (b'10\n', 10), (b'99\n', 99), (b'100\n', 100), (b'007\n', 7)):
        m = machine(gauge=text)
        v = tick(m)
        want = f'{pct}%'
        stored = 0 if pct <= DEFS['BP_LOW'] else pct   # on battery, at most BP_LOW: 0, stock's red bar_lowpower
        expect(v == stored and power(m) == stored and [t for _, t in texts(m)] == [want, want] and all(a for _, a in vis(m)) and len(vis(m)) == 2,
               f'on, gauge {text!r}: {stored} returned and stored, "{want}" shown in the bar\'s label and the pull-down\'s ({texts(m)})')
    m = machine(gauge=b'87\n'); tick(m)
    expect(('open', GAUGE, 0) in m.calls and ('access', KILL) in m.calls and m.calls.index(('access', KILL)) > m.calls.index(('get_battery_capacity',)),
           'stock\'s function runs first, then the kill switch is tested, then the gauge read')
    # the label fits its text: the widths the build measured, the group asked to lay out again when the width changed
    import pod_ui
    w2, w3, w4 = pod_ui.pct_widths(os.path.join(WORK, 'rootfs', pod_ui.PCT_FONT))
    stockh = open(os.path.join(BUILD, 'stock.h')).read()
    expect([int(re.search(rf'#define BP_W{n} (\d+)', stockh).group(1)) for n in (2, 3, 4)] == [w2, w3, w4], f'the payload\'s widths are the build\'s measure ({w2}, {w3}, {w4})')
    for text, want in ((b'5\n', w2), (b'87\n', w3), (b'100\n', w4)):
        m = machine(gauge=text, w=0)
        tick(m)
        lab = m.widgets[LABEL]
        rs = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == lab]
        expect(rs == [('widget_resize', lab, want, 30)] and ('widget_set_need_relayout_children', 0x31000000) in m.calls and m.word(lab + 8) == want,
               f'gauge {text!r}: the label is resized to {want} px (its height kept) and its parent relaid out')
        m.calls = []; tick(m)
        expect(not any(c[0] in ('widget_resize', 'widget_set_need_relayout_children') for c in m.calls), 'an unchanged width asks for no resize and no layout')
    # charging: stock's animation (a +10 counter in power_capacity) is replaced by the gauge's value on every tick, the picture logic is not touched
    m = machine(gauge=b'63\n', cap=70); tick(m)
    expect(power(m) == 63, 'charging (stock leaves its animation value): the real percentage is stored')
    # low battery: 5% or less on battery, or stock's own bucket 0, is stored as 0 (red); a charging picture keeps the real value
    ext, usb, flag, dac = (pod.DATA[k][0] for k in ('POWER_EXT', 'POWER_USBSTATE', 'POWER_FLAG', 'USBDAC_CHARGEFLAG'))
    for text, cap, want in ((b'6\n', 40, 6), (b'5\n', 40, 0), (b'1\n', 40, 0), (b'30\n', 0, 0), (b'30\n', 40, 30)):
        m = machine(gauge=text, cap=cap); v = tick(m)
        expect(v == want and power(m) == want, f'on battery, gauge {text!r}, stock bucket {cap}: {want} stored ({power(m)})')
    for text, cap, want in ((b'3\n', 40, 3), (b'1\n', 0, 1), (b'30\n', 0, 30)):
        m = machine(gauge=text, cap=cap); m.setword(ext, 1)   # external power, USB state not 2: stock draws the charging picture
        v = tick(m)
        expect(v == want and power(m) == want, f'charging (stock draws bar_charge), gauge {text!r}, stock bucket {cap}: the real value {want} stored ({power(m)})')
    m = machine(gauge=b'3\n'); m.setword(ext, 1); m.setword(usb, 2); m.u.mem_write(flag, b'\x01')
    expect(tick(m) == 0 and power(m) == 0, 'external power but stock\'s test falls through to the low / normal picture: 3% is stored as 0')
    m = machine(gauge=b'3\n'); m.setword(ext, 1); m.setword(usb, 2); m.u.mem_write(flag, b'\x01'); m.setword(dac, 1)
    expect(tick(m) == 3 and power(m) == 3, 'external power with the DAC charge flag set: the charging picture, the real value')

    # 4. On, but no valid gauge: stock's value; the label hidden (and not shown before: nothing to hide)
    for text in (None, b'', b'\n', b'abc', b'101\n', b'-5\n', b'+5\n', b'12x\n', b'1234\n', b' 50\n', b'5 0\n', b'50\n50\n', b'1.5\n', b'0x10\n'):
        m = machine(gauge=text)
        v = tick(m)
        expect(v == STOCK_CAP and power(m) == STOCK_CAP and texts(m) == [] and vis(m) == [], f'on, gauge {text!r}: stock\'s capacity, no label shown')
    m = machine(gauge=b'87\n'); tick(m)
    m.fs[GAUGE] = b'garbage'; m.calls = []
    v = tick(m)
    expect(v == STOCK_CAP and power(m) == STOCK_CAP and sorted(vis(m)) == sorted([(m.widgets[LABEL], 0), (m.widgets[LABEL_DD], 0)])
           and sorted((c[1], c[2]) for c in m.calls if c[0] == 'widget_set_sensitive') == sorted([(m.widgets[LABEL], 0), (m.widgets[LABEL_DD], 0)]),
           'the gauge goes bad after a good reading: stock\'s value again and both labels hidden (visible and sensitive off)')
    m.calls = []; tick(m)
    expect(not any(c[0] == 'widget_lookup' for c in m.calls), 'and once hidden nothing is looked up again')
    # kill switch
    m = machine(gauge=b'87\n'); tick(m)
    m.present.add(KILL); m.calls = []
    v = tick(m)
    expect(v == STOCK_CAP and power(m) == STOCK_CAP and len(vis(m)) == 2 and not any(a for _, a in vis(m)) and ('open', GAUGE, 0) not in m.calls,
           '/mnt/mmc/m1plus-off: stock\'s value, the labels hidden, the gauge not read')
    m = machine(gauge=b'87\n'); m.present.add(KILL)
    expect(tick(m) == STOCK_CAP and vis(m) == [] and ('open', FILE, 0) not in m.calls, 'the kill switch from the start: stock, nothing touched, the setting not even read')
    # no label widgets (an asset from another build): the value is still the real one, nothing else happens
    m = machine(gauge=b'87\n', labels=False)
    expect(tick(m) == 87 and power(m) == 87 and texts(m) == [], 'no label in the window tree: the percentage still fills the battery, nothing is shown')
    m = machine(gauge=b'87\n'); m.setword(pod.DATA['SYSTEM_BAR'][0], 0)
    expect(tick(m) == 87 and [t for _, t in texts(m)] == ['87%'], 'no status bar window: the pull-down\'s label is still set')
    # the setting is cached: a file edited behind the payload's back is read after a restart, a switch tap applies at once
    m = machine(setting=b'1\n', gauge=b'87\n'); tick(m)
    m.fs[FILE] = b'0\n'; m.calls = []
    expect(tick(m) == 87 and ('open', FILE, 0) not in m.calls, 'the setting is read once, at the first tick')

    # 5. The Settings switch
    expect(m.call(PSYMS['battpct_setting'], count=2000000) == 0, 'battpct_setting reads the file: 0 now')
    for saved, on in ((None, 0), (b'1\n', 1), (b'1', 1), (b'0\n', 0), (b'', 0), (b'x', 0), (b'1x', 0), (b'11', 0), (b'\n1', 0)):
        m = machine(setting=saved)
        expect(m.call(PSYMS['battpct_setting'], count=2000000) == on, f'saved {saved!r}: the setting reads {on}')
    m = machine(setting=None, gauge=b'87\n')
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 1 and m.fs[FILE] == b'1\n' and FILE + '.tmp' not in m.fs and ('rename', FILE + '.tmp', FILE) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls,
           'the first toggle writes "1" atomically (a temp file, fsync, rename) and turns it on')
    expect(tick(m) == 87 and [t for _, t in texts(m)] == ['87%', '87%'], 'the next tick shows the percentage at once (the cache follows the switch)')
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 0 and m.fs[FILE] == b'0\n', 'and off again')
    m.calls = []
    expect(tick(m) == STOCK_CAP and len(vis(m)) == 2 and not any(a for _, a in vis(m)), 'the next tick is stock\'s again and hides the labels')
    m = machine(setting=b'1\n', gauge=b'87\n'); m.fail.add(('write', FILE + '.tmp'))
    expect(m.call(PSYMS['battpct_toggle'], count=4000000) == 0xffffffff and m.fs[FILE] == b'1\n' and FILE + '.tmp' not in m.fs and tick(m) == 87,
           'a failed save: -1, the file and the behaviour are unchanged')

    # 6. The row: Settings > Home Screen > Status Bar > Battery Percentage (a switch, off by default)
    H = P.HOMESET_PAGE
    layout = [type(x).__name__ + (':' + x.label if isinstance(x, P.Row) else ':' + x.text if hasattr(x, 'text') else '') for x in H.layout]
    bp_i = next(i for i, r in enumerate(H.rows) if r.action == P.ACT_BATTPCT)
    expect(H.rows[bp_i].label == 'Battery Percentage' and P.ACT_BATTPCT == 36 and P.ACT_BATTPCT in P.SWITCH_ACTIONS and P.row_kind(H.rows[bp_i]) == 'switch'
           and layout[-5:-2] == ['Hdr:Status Bar', 'Row:Battery Percentage', 'Note:The exact charge beside the battery icon'] and layout[-2:] == ['Row:Regenerate Daily Mix', 'Note:A new mix the next time Home opens'],
           f'the Home Screen page has a Status Bar header, the Battery Percentage switch row and its note before Regenerate Daily Mix ({layout[-5:]})')
    S = P.SETTINGS_PAGE
    hs_i = next(i for i, r in enumerate(S.rows) if r.action == P.ACT_PAGE and r.arg == P.HOMESET_PAGE_INDEX)
    rows_s = PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}']; on_row = PSYMS['on_row']

    def open_home(saved=None):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))] + [f'pod_switch{bp_i}'])}
        if saved is not None: m.fs[FILE] = saved
        m.call(on_row, a0=rows_s + 12 * hs_i, count=3000000)
        return m

    def images(m): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{bp_i}']]

    m = open_home()
    expect(('window_open', H.key) in m.calls and images(m) == ['sset_off'] and FILE not in m.fs, 'the page opens with nothing saved: the switch is off and nothing is written (the default)')
    for data, on in ((b'1\n', 1), (b'0\n', 0), (b'', 0)):
        expect(images(open_home(data)) == [('sset_on' if on else 'sset_off')], f'saved {data!r}: the switch opens {"on" if on else "off"}')
    m = open_home()
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'1\n' and images(m)[-1] == 'sset_on', 'a tap on the row turns it on (saved, the switch on)')
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'0\n' and images(m)[-1] == 'sset_off', 'and off again')
    m = open_home(b'1\n'); m.fail.add(('write', FILE + '.tmp'))
    m.click(f'pod_row{bp_i}')
    expect(m.fs.get(FILE) == b'1\n' and images(m) == [], 'a failed save changes neither the file nor the switch')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Status Bar', 'Battery Percentage', 'The exact charge beside the battery icon')), f'the header, row and note have a text in {loc}')

    # 7. The assets: the hidden label in the system bar and in the pull-down
    import awtk_ui, statusbar
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', pod_ui.PCT_FONT))
    stock_bar = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    bar = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    bars = [('system_bar', bar, LABEL)]
    dd = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), 'rb').read())
    bars.append(('pull-down', dd.find('view_sysbar'), LABEL_DD))
    for what, root, name in bars:
        group, lab = root.find('view_bar_right'), root.find(name)
        kids = [c.name for c in group.children]
        expect(lab is not None and lab.type == 'label' and lab.get('visible') == 'false' and lab.get('sensitive') == 'false' and group.children.index(lab) == (len(kids) - (2 if kids[-1] == 'pod_shot' else 1))
               and [k for k in kids[:4] if k != 'pod_sync'] == ['img_btclass', 'img_synclink', 'img_wifi'] and kids[1] == 'pod_sync' and sum(c.name == name for c in root.walk()) == 1,
               f'{what}: {name} is one hidden, insensitive label in the right group, after the stock icons and before the camera ({kids})')
        sty = {st: (lab.get(f'style:{st}:text_color'), lab.get(f'style:{st}:font_size'), lab.get(f'style:{st}:text_align_h'), lab.get(f'style:{st}:text_align_v')) for st in statusbar.STATES}
        expect(all(v == ('#FFFFFF', str(statusbar.PCT_PX), 'right', 'middle') for v in sty.values()) and lab.w == w3 and lab.h == 0, f'{what}: white {statusbar.PCT_PX} px text, right-aligned, vertically centred, {w3} px wide in every state')
    expect({n.name for n in stock_bar.walk()} == {n.name for n in bar.walk()} - {LABEL, 'pod_shot', 'pod_lo', 'pod_sync'}, 'no stock widget is renamed or removed (the label and the camera are the only additions)')
    expect(font.width('100%', statusbar.PCT_PX) > 0 and w4 == StbText(font, statusbar.PCT_PX).layout('100%')[1] and w2 < w3 < w4, 'the widths are StbText\'s measure of "100%" and the shorter forms')
    # layout: the group is right-aligned from its right edge (4 px before the outline); with the label the icons move left by its width + 4. Every icon's ink must stay clear of the clock.
    from PIL import Image
    group, clock = bar.find('view_bar_right'), bar.find('bar_dclock')
    clock_px = int(clock.get('style:normal:font_size'))
    clock_end = max(clock.x + (clock.w + StbText(font, clock_px).layout(t)[1]) // 2 for t in ('12:59', '12:59 PM', '10:59 AM', '12:59 AM'))
    imgs = {'img_btclass': 'bar_bt', 'img_synclink': 'bar_synclink', 'img_wifi': 'bar_wifi0', 'pod_shot': 'pod_bar_shot'}
    ink_left = {n: Image.open(os.path.join(WORK, 'rootfs/release/assets/default/raw/images/xx', f'{f}.png')).convert('RGBA').getchannel('A').getbbox()[0] for n, f in imgs.items()}
    sizes = {c.name: c.w for c in group.children}
    edge = group.x + group.w
    expect(edge + 4 == bar.find('img_battery').x, 'the group ends 4 px before the battery outline')

    def spans(visible):
        out, e = {}, edge
        for n in reversed([c.name for c in group.children]):
            if n in visible: out[n] = (e - sizes[n], e); e -= sizes[n] + 4
        return out

    for label_w in (w2, w3, w4):
        sizes[LABEL] = label_w
        s = spans(['img_btclass', 'img_synclink', 'img_wifi', LABEL])
        expect(s[LABEL] == (edge - label_w, edge), f'the {label_w} px label sits against the right end of the group, 4 px before the outline')
        gaps = {n: s[n][0] + ink_left[n] for n in s if n != LABEL}
        expect(all(g >= clock_end + 3 for g in gaps.values()), f'{label_w} px label, Bluetooth, SyncLink and Wi-Fi all lit: every icon\'s ink starts at least 3 px clear of the 12 h and 24 h clock ({gaps}, clock ends {clock_end})')
    sizes[LABEL] = w4
    s = spans(['img_btclass', 'img_wifi', LABEL, 'pod_shot'])
    expect(s['pod_shot'] == (edge - 16, edge) and all(s[n][0] + ink_left[n] >= clock_end + 3 for n in ('img_btclass', 'img_wifi')),
           'with the Screenshot camera too (against the outline), Bluetooth and Wi-Fi lit, the ink is still at least 3 px clear of the clock')

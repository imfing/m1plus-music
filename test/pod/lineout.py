"""Line Out pill (patch/lineout.c, docs/modules/lineout.md): the two hooks at show_sysbar_face's and dropdown_showface's `jalr widget_set_text_utf8` of label_volume, run against the
mocked stock function; the hidden pill in the system bar and the pull-down's bar, its image, and that neither the accent nor Light Mode touches it."""
import os, re, struct
import paths
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DEFS = {}
for _line in open(os.path.join(ROOT, 'patch', 'lineout.h')).read().replace('\\\n', ' ').splitlines():
    _m = re.match(r'#define\s+(\w+)\s+("[^"]*"|\w+)\s*(?:/\*.*)?$', _line.strip())
    if _m: DEFS[_m.group(1)] = _m.group(2).strip('"') if _m.group(2).startswith('"') else int(_m.group(2), 0)
PILL, KILL = DEFS['LO_PILL'], '/mnt/mmc/m1plus-off'


class LM(Machine):
    COUNT = True   # the instruction count (icount) the cost check reads


def machine(pill=True, sync=False):
    """label_volume (a parent at +0x44, the left group, whose parent is the bar) and, unless pill is False, the pill beside it; with sync, the sync icon in the bar (the right group's child)."""
    m = LM()
    group = m.alloc(0x80); bar = m.alloc(0x80); m.setword(group + DEFS['LO_W_PARENT'], bar)
    m.label = m.widget('label_volume'); m.setword(m.label + DEFS['LO_W_PARENT'], group)
    if pill: m.pill = m.widget(PILL); m.setword(m.pill + DEFS['LO_W_PARENT'], group)
    if sync: m.sync = m.widget(DEFS['SYNC_IND']); m.props[(m.sync, 'visible')] = 0   # (hidden in the asset)
    return m


def tick(m, text):
    return m.call(PSYMS['lo_set_text'], a0=m.label, a1=m.cstr(text), count=20000)


def log(m, what): return [(c[1], c[2]) for c in m.calls if c[0] == what]


def run(ctx):
    expect = ctx.expect
    import awtk_ui, statusbar, mod_icons
    from PIL import Image
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]

    # 1. The hooks: two call-site words, everything around them stock's.
    sites = [a for a, _ in pod.LINEOUT_SITES]
    expect(sites == [0x544f90, 0x475ad8] and [l for _, l in pod.LINEOUT_SITES] == [0x544f88, 0x475ad0], 'the sites are show_sysbar_face 0x544f90 and dropdown_showface 0x475ad8')
    expect(all(w(stock_demo, a) == 0x0320f809 and w(built, a) >> 26 == 3 and (w(built, a) & 0x3ffffff) << 2 == PSYMS['lo_set_text'] for a in sites),
           'the build replaced stock\'s `jalr t9` (widget_set_text_utf8) at both sites by `jal lo_set_text`')
    expect(all(w(stock_demo, a) == old and (a in sites or w(built, a) == old) for a, old, _ in pod.LINEOUT_PINS), 'every pinned word is stock\'s in the stock demo and unchanged in the build, but the sites')
    expect(all(w(built, a + 4) == 0x02e02025 and w(built, a - 4) == 0x02c02825 and w(built, a - 8) == 0x8f99a86c for a in sites),
           'the delay slot (move a0, s7 = label_volume) and a1 = the text (move a1, s6) and the lw t9 widget_set_text_utf8 are stock\'s')
    expect(pod.FUNCTIONS['widget_set_text_utf8'][2] == 0x66f720 and DEFS['LO_W_PARENT'] == 0x44 and any(a == 0x66c428 for a, *_ in pod.BATTERY_PINS), 'widget_set_text_utf8 and the parent offset are the pinned ones')
    expect(MANIFEST['hook_lineout'] == {'sites': [hex(a) for a in sites], 'target': PSYMS['lo_set_text']}, 'the manifest records the hooks')

    # 2. "LO": stock's text call first, then the label hidden (visible and sensitive off) and the pill shown (both on).
    m = machine(); tick(m, 'LO')
    lab, pill = m.label, m.pill
    expect(m.names()[0] == 'widget_set_text_utf8' and log(m, 'widget_set_text_utf8') == [(lab, 'LO')], 'stock\'s widget_set_text_utf8 runs first, with the text unchanged')
    expect(log(m, 'widget_set_visible') == [(lab, 0), (pill, 1)] and log(m, 'widget_set_sensitive') == [(lab, 0), (pill, 1)], 'LO: label_volume hidden and insensitive, the pill visible and sensitive')
    expect(sorted(c[1] for c in m.calls if c[0] == 'widget_lookup') == sorted([PILL, DEFS['SYNC_IND']]), 'the pill and the sync icon are looked up by name (once each)')
    expect(m.icount < 900, f'cost: {m.icount} instructions')

    # 3. A number, or anything else: stock's label, the pill hidden.
    for text in ('87', '100', '0', 'L', 'LOL', 'lo', 'Lo', ' LO', 'LO ', ''):
        m = machine(); tick(m, text)
        expect(log(m, 'widget_set_text_utf8') == [(m.label, text)] and log(m, 'widget_set_visible') == [(m.label, 1), (m.pill, 0)] and log(m, 'widget_set_sensitive') == [(m.label, 1), (m.pill, 0)],
               f'text {text!r}: the label shown and sensitive, the pill hidden and insensitive')
    m = machine(); tick(m, 'LO'); m.calls = []; tick(m, '55')
    expect(log(m, 'widget_set_visible') == [(m.label, 1), (m.pill, 0)], 'LO off again: the next tick restores the label and hides the pill')

    # 4. The kill switch: stock's "LO" text stays, the pill never shows.
    m = machine(); m.present.add(KILL); tick(m, 'LO')
    expect(log(m, 'widget_set_text_utf8') == [(m.label, 'LO')] and log(m, 'widget_set_visible') == [(m.label, 1), (m.pill, 0)], '/mnt/mmc/m1plus-off: the label shows stock\'s "LO", the pill is hidden')

    # 5. Missing pieces: stock's behaviour, nothing else touched.
    m = machine(pill=False); tick(m, 'LO')
    expect(log(m, 'widget_set_text_utf8') == [(m.label, 'LO')] and log(m, 'widget_set_visible') == [] and log(m, 'widget_set_sensitive') == [], 'no pill in the bar (an asset from another build): stock\'s "LO" label stays')
    m = machine(); m.setword(m.label + 0x44, 0); tick(m, 'LO')
    expect(log(m, 'widget_set_text_utf8') == [(m.label, 'LO')] and log(m, 'widget_set_visible') == [], 'no parent: stock\'s text only')
    m = machine(); m.call(PSYMS['lo_set_text'], a0=0, a1=m.cstr('LO'), count=20000)
    expect(log(m, 'widget_set_visible') == [], 'a null label is passed to stock\'s function and nothing else')

    # 6. The assets: one hidden, insensitive pill image right after label_volume, in the system bar and the pull-down, laid out from statusbar.py.
    rootfs = os.path.join(WORK, 'rootfs')
    bars = [('system_bar', awtk_ui.parse(open(os.path.join(rootfs, 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read()))]
    dd = awtk_ui.parse(open(os.path.join(rootfs, 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), 'rb').read())
    bars.append(('pull-down', dd.find('view_sysbar')))
    for what, bar in bars:
        left = bar.find('view_bar_left'); kids = [c.name for c in left.children]; p = bar.find(PILL)
        expect(p is not None and p.type == 'image' and p.get('visible') == 'false' and p.get('sensitive') == 'false' and p.get('image') == statusbar.LO_IMAGE and p.w == statusbar.VOLUME_W
               and kids.index(PILL) == kids.index('label_volume') + 1 and sum(c.name == PILL for c in bar.walk()) == 1 and statusbar.LO_WIDGET == PILL,
               f'{what}: {PILL} is one hidden, insensitive image right after label_volume ({kids})')
    stock_bar = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release/assets/default/raw/ui/system_bar.bin'), 'rb').read())
    expect({n.name for n in stock_bar.walk()} == {n.name for n in bars[0][1].walk()} - {PILL, 'pod_shot', 'pod_pct', 'pod_sync'}, 'no stock widget is renamed or removed')

    # 7. The image: amber, not the Accent Orange, a full pill, and no tint or flip touches it.
    png = os.path.join(rootfs, 'release/assets/default/raw/images/xx', statusbar.LO_IMAGE + '.png')
    expect(open(png, 'rb').read() == open(os.path.join(mod_icons.PNG, statusbar.LO_IMAGE + '.png'), 'rb').read() and statusbar.LO_IMAGE in mod_icons.pod_names(), 'the image is added from the committed PNG')
    im = Image.open(png).convert('RGBA')
    expect(im.size == (statusbar.LO_W, 16) and (mod_icons.LO_BAR_W, mod_icons.LO_BAR_H) == im.size and mod_icons.LO_BAR_RGB == (0xFF, 0xD6, 0x0A) and mod_icons.LO_BAR_RGB != (0xFF, 0x9F, 0x0A), 'a 26 x 16 pill, amber #FFD60A (not Accent Orange #FF9F0A)')
    px = im.load(); h = im.height
    expect(px[0, 0][3] == 0 and px[im.width - 1, h - 1][3] == 0 and px[im.width // 2, 0][3] == 255 and px[im.width // 2, h - 1][3] == 255 and px[2, h // 2][3] > 0, 'rounded ends: the corners are transparent, the middle of the top and bottom edge opaque')
    solid = [px[x, y] for x in range(im.width) for y in range(h) if px[x, y][3] == 255]
    expect(set(c[:3] for c in solid) >= {(0xFF, 0xD6, 0x0A), (0, 0, 0)} and sum(c[:3] == (0, 0, 0) for c in solid) > 15, 'amber with black "LO" text')
    import palette
    expect(statusbar.LO_IMAGE not in palette.ACCENT_ALL and not statusbar.LO_IMAGE.startswith(palette.ACCENT_GLYPH) and not statusbar.LO_IMAGE.startswith(palette.WHOLE),
           'the accent lists name no pod_bar_lo (the accent never tints it)')
    sat = max(max(c[:3]) - min(c[:3]) for c in solid)
    expect(sat > 200, f'Light Mode\'s flip only takes images without colour: this one is saturated ({sat} > 40)')

    # 8. The sync icon (hook 20's second job): visible and sensitive iff the cover worker runs a cover or duration set with work left; set only on a change; kill switch or no widget: hidden.
    SYNC = DEFS['SYNC_IND']
    path = '/mnt/mmc/m/1.flac'

    def build(m, mode=0, n=2, start=True):
        """A set of n jobs held by the shared worker (the thread is the harness's: it never runs)."""
        m.present.add(path)
        assert m.call(PSYMS['cc_build_open'], a0=8, a1=mode, count=2000000) == 1
        for i in range(n):
            if mode == 2: m.call(PSYMS['cc_build_add_dur'], a0=m.cstr(path), a1=100 + i, a2=1000, count=2000000)
            else: m.call(PSYMS['cc_build_add'], a0=m.cstr(path), a1=100 + i, count=2000000)
        if start: assert m.call(PSYMS['cc_build_start'], count=2000000) == 1

    def sync_log(m): return [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == m.sync]

    m = machine(sync=True); tick(m, '50')
    expect(not sync_log(m), 'no build: the icon stays hidden, nothing is set (no relayout each second)')
    build(m); m.calls = []; tick(m, '50')
    expect(sync_log(m) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)], 'a cover build runs: the icon is visible and sensitive')
    m.calls = []; tick(m, 'LO')
    expect(not sync_log(m) and log(m, 'widget_set_visible')[-1] == (m.pill, 1), 'a steady build changes nothing again, and the Line Out pill still works beside it')
    m.setword(PSYMS['cb'] + 4 * 5, 2)   # done == total (the worker has finished, the owner has not stopped the set yet)
    m.calls = []; tick(m, '50')
    expect(sync_log(m) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'every job done: hidden')
    m.setword(PSYMS['cb'] + 4 * 5, 0); m.calls = []; tick(m, '50'); m.calls = []
    m.call(PSYMS['cc_build_stop']); tick(m, '50')
    expect(sync_log(m)[0][1] == 0, 'the set stopped: hidden')
    m = machine(sync=True); build(m, mode=1); tick(m, '50')
    expect(sync_log(m)[0][1] == 1, 'a Rebuild Covers set shows it too')
    m = machine(sync=True); build(m, mode=2); tick(m, '50')
    expect(sync_log(m)[0][1] == 1, 'a duration pass shows it too (any owner)')
    m = machine(sync=True); build(m, start=False); tick(m, '50')
    expect(not sync_log(m), 'a set held but not started (a scan in progress): hidden')
    m = machine(sync=True); m.present.add(path)
    m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=2000000); m.call(PSYMS['cc_build_add_file'], a0=m.cstr(path), a1=m.cstr('/tmp/x.jpg'), a2=100, count=2000000); m.call(PSYMS['cc_build_start'], count=2000000)
    tick(m, '50')
    expect(build_state(m)['running'] == 1 and not sync_log(m), 'a transient cover-pane job is not a build: hidden')
    m = machine(sync=True); build(m); m.present.add(KILL); tick(m, '50')
    expect(not sync_log(m), 'kill switch: hidden')
    m = machine(); build(m); tick(m, '50')
    expect(not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] not in (m.label, m.pill)], 'no sync widget in the bar (an older asset): nothing else is touched')
    m = LM(); lab = m.widget('label_volume'); grp = m.alloc(0x80); m.setword(lab + DEFS['LO_W_PARENT'], grp)   # a group with no parent bar
    m.call(PSYMS['lo_set_text'], a0=lab, a1=m.cstr('50'), count=20000)
    expect(log(m, 'widget_set_text_utf8') == [(lab, '50')], 'no bar above the group: stock\'s text only')

    # the assets: one hidden, insensitive 18 px image in view_bar_right right after the Bluetooth box, both bars identical (test/pod/assets.py compares them whole)
    for what, bar in bars:
        right = bar.find('view_bar_right'); kids = [c.name for c in right.children]; s = bar.find(SYNC)
        expect(s is not None and s.type == 'image' and s.get('visible') == 'false' and s.get('sensitive') == 'false' and s.get('image') == statusbar.SYNC_IMAGE == 'pod_bar_sync' and s.w == 18
               and kids.index(SYNC) == kids.index('img_btclass') + 1 and sum(c.name == SYNC for c in bar.walk()) == 1 and statusbar.SYNC_WIDGET == SYNC,
               f'{what}: {SYNC} is one hidden, insensitive 18 px image after img_btclass in view_bar_right ({kids})')
    png = os.path.join(rootfs, 'release/assets/default/raw/images/xx', statusbar.SYNC_IMAGE + '.png')
    expect(open(png, 'rb').read() == open(os.path.join(mod_icons.PNG, statusbar.SYNC_IMAGE + '.png'), 'rb').read() and statusbar.SYNC_IMAGE in mod_icons.pod_names(), 'the image is added from the committed PNG')
    im = Image.open(png).convert('RGBA'); px = im.load()
    ink = [px[x, y] for x in range(im.width) for y in range(im.height) if px[x, y][3] > 0]
    expect(im.size == (18, 18) and ink and all(c[:3] == (255, 255, 255) for c in ink) and im.getchannel('A').getbbox()[2] - im.getchannel('A').getbbox()[0] >= 14,
           'an 18 x 18 white glyph (Lucide refresh-cw, 1.5 px stroke) filling the canvas')
    expect(statusbar.SYNC_IMAGE not in palette.ACCENT_ALL and not statusbar.SYNC_IMAGE.startswith(palette.ACCENT_GLYPH) and not statusbar.SYNC_IMAGE.startswith(palette.WHOLE),
           'the accent lists name no pod_bar_sync: neutral white like the other status glyphs (Light Mode flips it with them)')
    # layout: shown with Bluetooth and Wi-Fi (and the volume pill), its ink and Bluetooth's stay clear of the clock
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(rootfs, 'release/assets/default/raw/fonts/default.ttf'))
    sysbar = bars[0][1]; group, clock = sysbar.find('view_bar_right'), sysbar.find('bar_dclock')
    clock_end = max(clock.x + (clock.w + StbText(font, int(clock.get('style:normal:font_size'))).layout(t)[1]) // 2 for t in ('12:59', '12:59 PM', '10:59 AM', '12:59 AM'))
    ink_left = {n: Image.open(os.path.join(rootfs, 'release/assets/default/raw/images/xx', f'{f}.png')).convert('RGBA').getchannel('A').getbbox()[0] for n, f in {'img_btclass': 'bar_bt', 'pod_sync': 'pod_bar_sync', 'img_wifi': 'bar_wifi0'}.items()}
    sizes = {c.name: c.w for c in group.children}; e, spans = group.x + group.w, {}
    for n in reversed([c.name for c in group.children]):
        if n in ('img_btclass', 'pod_sync', 'img_wifi'): spans[n] = (e - sizes[n], e); e -= sizes[n] + 4
    gaps = {n: spans[n][0] + ink_left[n] for n in spans}
    expect(all(g >= clock_end + 3 for g in gaps.values()), f'sync icon, Bluetooth and Wi-Fi lit: every ink starts 3 px clear of the clock ({gaps}, clock ends {clock_end})')

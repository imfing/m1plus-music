"""Line Out pill (patch/lineout.c, docs/modules/lineout.md): the two hooks at show_sysbar_face's and dropdown_showface's `jalr widget_set_text_utf8` of label_volume, run against the
mocked stock function; the hidden pill in the system bar and the pull-down's bar, its image, and that neither the accent nor Light Mode touches it."""
import os, struct
import paths
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'lineout.h'), strings=True)
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
    stock_demo = stock_demo_bytes()
    built = built_demo_bytes()
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
    expect(sorted(c[1] for c in m.calls if c[0] == 'widget_lookup') == sorted([PILL, DEFS['SLEEP_SHOT'], DEFS['SYNC_IND'], DEFS['SLEEP_IND'], DEFS['EQ_IND']]), 'the pill, the camera, the sync icon, the sleep icon and the EQ mark are looked up by name (once each)')
    expect(m.icount < 1000, f'cost: {m.icount} instructions')

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

    # 4b. The per-output EQ follows the same one second tick (patch/peqout.c, docs/modules/peq.md "Per-output EQ"): the first tick notes the output, a change files the record; the kill switch leaves it alone.
    out_file, rec, slot = '/mnt/data/m1plus/playback-eq-output', '/mnt/data/m1plus/playback-eq', '/mnt/data/m1plus/playback-eq-headphones'
    m = machine(); m.fs[rec] = b'M1PEQ03\0' + bytes(2240); tick(m, '55')
    expect(out_file in m.fs and m.fs[out_file][8:12] == struct.pack('<i', 0), 'the bar tick notes the output (Headphones) in the per-output EQ file')
    m = machine(); m.fs[rec] = b'M1PEQ03\0' + bytes(2240); m.present.add(KILL); tick(m, '55')
    expect(out_file not in m.fs and slot not in m.fs, 'with the kill switch the tick does nothing for the EQ')

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
    expect({n.name for n in stock_bar.walk()} == {n.name for n in bars[0][1].walk()} - {PILL, 'pod_shot', 'pod_bat_bg', 'pod_pct_bg', 'pod_pct', 'pod_chg_lvl', 'pod_chg_bolt', 'pod_chg_bolts', 'pod_sync', 'pod_sleep', 'pod_eq'}, 'no stock widget is renamed or removed')

    # 7. The image: amber, not the Accent Orange, a full pill, and no tint or flip touches it.
    png = os.path.join(rootfs, 'release/assets/default/raw/images/xx', statusbar.LO_IMAGE + '.png')
    expect(open(png, 'rb').read() == open(os.path.join(mod_icons.PNG, statusbar.LO_IMAGE + '.png'), 'rb').read() and statusbar.LO_IMAGE in mod_icons.pod_names(), 'the image is added from the committed PNG')
    im = Image.open(png).convert('RGBA')
    import status_art
    expect(im.size == (statusbar.LO_W, 16) and status_art.AMBER[:3] == (0xFF, 0xD6, 0x0A) != (0xFF, 0x9F, 0x0A), 'a 26 x 16 canvas, amber #FFD60A (not Accent Orange #FF9F0A)')
    px = im.load(); x0, y0, x1, y1 = im.getchannel('A').getbbox(); mx = (x0 + x1) // 2
    expect(y1 - y0 == status_art.GLYPH_H and y0 == (im.height - status_art.GLYPH_H) // 2 and abs(x0 + x1 - im.width) <= 1,
           f'a {status_art.GLYPH_H} px pill (the other status marks\' height), centred in the canvas')
    expect(px[x0, y0][3] == 0 and px[x1 - 1, y1 - 1][3] == 0 and px[mx, y0][3] == 255 and px[mx, y1 - 1][3] == 255, 'rounded ends: the corners are transparent, the middle of the top and bottom edge opaque')
    h = im.height
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

    # the assets: one hidden, insensitive image as wide as its glyph's canvas in view_bar_right right after the Bluetooth box, both bars identical (test/pod/assets.py compares them whole)
    for what, bar in bars:
        right = bar.find('view_bar_right'); kids = [c.name for c in right.children]; s = bar.find(SYNC)
        expect(s is not None and s.type == 'image' and s.get('visible') == 'false' and s.get('sensitive') == 'false' and s.get('image') == statusbar.SYNC_IMAGE == 'pod_bar_sync' and s.w == statusbar.SYNC_W == 16
               and kids.index(SYNC) == kids.index('img_btclass') + 1 and sum(c.name == SYNC for c in bar.walk()) == 1 and statusbar.SYNC_WIDGET == SYNC,
               f'{what}: {SYNC} is one hidden, insensitive 16 px image after img_btclass in view_bar_right ({kids})')
    png = os.path.join(rootfs, 'release/assets/default/raw/images/xx', statusbar.SYNC_IMAGE + '.png')
    expect(open(png, 'rb').read() == open(os.path.join(mod_icons.PNG, statusbar.SYNC_IMAGE + '.png'), 'rb').read() and statusbar.SYNC_IMAGE in mod_icons.pod_names(), 'the image is added from the committed PNG')
    im = Image.open(png).convert('RGBA'); px = im.load()
    ink = [px[x, y] for x in range(im.width) for y in range(im.height) if px[x, y][3] > 0]
    import status_art
    bb = im.getchannel('A').getbbox()
    expect(im.size == (statusbar.SYNC_W, 18) and (bb[0], bb[2]) == (1, im.width) and ink and all(c[:3] == (255, 255, 255) for c in ink) and bb[3] - bb[1] == status_art.GLYPH_H,
           f'a white glyph {status_art.GLYPH_H} px tall (tools/status_art.py, the other status marks\' height) at the right of a 16 x 18 canvas, 1 px empty on the left')
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
        if n in ('img_btclass', 'pod_sync', 'img_wifi'): spans[n] = (e - sizes[n], e); e -= sizes[n] + statusbar.RGAP
    gaps = {n: spans[n][0] + ink_left[n] for n in spans}
    expect(all(g >= clock_end + 3 for g in gaps.values()), f'sync icon, Bluetooth and Wi-Fi lit: every ink starts 3 px clear of the clock ({gaps}, clock ends {clock_end})')

    # 9. The EQ mark (hook 20's third job): the label pod_eq is visible and sensitive iff the Equalizer switch (stock's equalizer_flag) is on, the digital-out glyph is hidden and the kill switch is absent; set only on a change.
    EQ = DEFS['EQ_IND']

    def eq_machine(flag, digital=None):
        m = machine(); m.eq = m.widget(EQ); m.props[(m.eq, 'visible')] = 0   # (hidden in the asset)
        if digital is not None: m.dig = m.widget(DEFS['EQ_DIGITAL']); m.props[(m.dig, 'visible')] = digital
        m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag]))
        return m

    def eq_log(m): return [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == m.eq]

    m = eq_machine(0); tick(m, '50')
    expect(not eq_log(m), 'Equalizer off: the mark stays hidden, nothing is set')
    m = eq_machine(1); tick(m, '50')
    expect(eq_log(m) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)], 'Equalizer on: the mark is visible and sensitive')
    expect(m.icount < 1200, f'cost with the mark: {m.icount} instructions')
    m.calls = []; tick(m, 'LO')
    expect(not eq_log(m) and log(m, 'widget_set_visible')[-1] == (m.pill, 1), 'a steady switch sets nothing again, and the Line Out pill works beside it')
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], b'\0'); m.calls = []; tick(m, '50')
    expect(eq_log(m) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'Equalizer off again: hidden and insensitive')
    m = eq_machine(1, digital=1); tick(m, '50')
    expect(not eq_log(m), 'the digital-out glyph shows: no room before the clock, the mark stays hidden')
    m = eq_machine(1, digital=0); tick(m, '50')
    expect(eq_log(m)[0] == ('widget_set_visible', 1), 'the digital-out glyph hidden: the mark shows')
    m.props[(m.dig, 'visible')] = 1; m.calls = []; tick(m, '50')
    expect(eq_log(m)[0] == ('widget_set_visible', 0), 'the glyph comes on: the mark goes')
    m = eq_machine(1); m.present.add(KILL); tick(m, '50')
    expect(not eq_log(m), 'kill switch: hidden')
    m = machine(); m.u.mem_write(pod.DATA['EQ_FLAG'][0], b'\1'); tick(m, '50')
    expect(not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] not in (m.label, m.pill)], 'no EQ mark in the bar (an older asset): nothing else is touched')
    # the assets: one hidden, insensitive label right after the pill in view_bar_left, in label_volume's style; shown, the group ends before the clock's ink
    clock_start = min(clock.x + (clock.w - StbText(font, int(clock.get('style:normal:font_size'))).layout(t)[1]) // 2 for t in ('12:59', '12:59 PM', '10:59 AM', '12:59 AM'))
    for what, bar in bars:
        left = bar.find('view_bar_left'); kids = [c.name for c in left.children]; e = bar.find(EQ); vol = bar.find('label_volume')
        expect(e is not None and e.type == 'label' and e.get('visible') == 'false' and e.get('sensitive') == 'false' and e.get('text') == 'EQ' and statusbar.EQ_WIDGET == EQ
               and kids.index(EQ) == kids.index(PILL) + 1 and kids[-1] == DEFS['EQ_DIGITAL'] and sum(c.name == EQ for c in bar.walk()) == 1
               and all(e.get(f'style:{st}:{k}') == vol.get(f'style:{st}:{k}') for st in statusbar.STATES for k in ('text_color', 'text_align_v')) and e.get('style:normal:font_size') == str(statusbar.EQ_PX) == '16',
               f'{what}: {EQ} is one hidden, insensitive label after the pill, before the digital-out glyph, white like the volume number, at 16 px like the volume number ({kids})')
        expect(e.w >= StbText(font, statusbar.EQ_PX).layout('EQ')[1], f'{what}: the box holds "EQ" at 16 px ({e.w})')
        end = statusbar.EDGE + sum(c.w + statusbar.GAP for c in left.children if c.name not in (PILL, DEFS['EQ_DIGITAL'])) - statusbar.GAP
        expect(end + 3 <= clock_start, f'{what}: play state, volume and the mark end at x {end}, 3 px clear of the clock\'s ink ({clock_start})')

    # 10. The Sleep Timer icon (hook 20's fourth job): pod_sleep in view_bar_right right after pod_sync, visible and sensitive iff sleepflag != 0 and sleep_time > 0 and the kill switch is absent; set only on a change.
    SLEEP = DEFS['SLEEP_IND']

    def sleep_machine(flag, secs):
        m = machine(); m.sleep = m.widget(SLEEP); m.props[(m.sleep, 'visible')] = 0   # (hidden in the asset)
        m.u.mem_write(pod.DATA['SLEEP_FLAG'][0], bytes([flag]))
        m.setword(pod.DATA['SLEEP_TIME'][0], secs)
        return m

    def sleep_log(m): return [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == m.sleep]

    for flag, secs in ((0, 0), (1, 0), (0, 900)):
        m = sleep_machine(flag, secs); tick(m, '50')
        expect(not sleep_log(m), f'Sleep Timer ({flag}, {secs}): stays hidden, nothing is set (no relayout each second)')
    m = sleep_machine(1, 900); tick(m, '50')
    expect(sleep_log(m) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)], 'Sleep Timer running: pod_sleep is visible and sensitive')
    m.calls = []; tick(m, 'LO')
    expect(not sleep_log(m) and log(m, 'widget_set_visible')[-1] == (m.pill, 1), 'a steady timer sets nothing again, and the Line Out pill still works beside it')
    m.setword(pod.DATA['SLEEP_TIME'][0], 0); m.calls = []; tick(m, '50')
    expect(sleep_log(m) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'time hits 0: hidden and insensitive')
    m = sleep_machine(1, 900); tick(m, '50'); m.u.mem_write(pod.DATA['SLEEP_FLAG'][0], b'\0'); m.calls = []; tick(m, '50')
    expect(sleep_log(m) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)], 'switch cleared: hidden and insensitive')
    m = sleep_machine(1, 900); m.present.add(KILL); tick(m, '50')
    expect(not sleep_log(m), 'kill switch: hidden')
    m = machine(); m.u.mem_write(pod.DATA['SLEEP_FLAG'][0], b'\1'); m.setword(pod.DATA['SLEEP_TIME'][0], 900); tick(m, '50')
    expect(not [c for c in m.calls if c[0] == 'widget_set_visible' and c[1] not in (m.label, m.pill)], 'no sleep icon in the bar (an older asset): nothing else is touched')
    # pull-down init refresh: lo_bar_refresh shows pod_sleep on the first frame
    m = sleep_machine(1, 900); m.call(PSYMS['lo_bar_refresh'], a0=m.alloc(0x80), count=20000)
    expect(sleep_log(m) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)], 'lo_bar_refresh sets pod_sleep on the pull-down\'s first frame')
    # the assets: one hidden, insensitive image as wide as its glyph's canvas in view_bar_right right after pod_sync, in both bar copies
    for what, bar in bars:
        right = bar.find('view_bar_right'); kids = [c.name for c in right.children]; sl = bar.find(SLEEP)
        expect(sl is not None and sl.type == 'image' and sl.get('visible') == 'false' and sl.get('sensitive') == 'false' and sl.get('image') == statusbar.SLEEP_IMAGE == 'pod_bar_sleep' and sl.w == statusbar.SLEEP_W == 17
               and kids.index(SLEEP) == kids.index(SYNC) + 1 and sum(c.name == SLEEP for c in bar.walk()) == 1 and statusbar.SLEEP_WIDGET == SLEEP,
               f'{what}: {SLEEP} is one hidden, insensitive 17 px image right after {SYNC} in view_bar_right ({kids})')
    png = os.path.join(rootfs, 'release/assets/default/raw/images/xx', statusbar.SLEEP_IMAGE + '.png')
    expect(open(png, 'rb').read() == open(os.path.join(mod_icons.PNG, statusbar.SLEEP_IMAGE + '.png'), 'rb').read() and statusbar.SLEEP_IMAGE in mod_icons.pod_names(), 'pod_bar_sleep is added from the committed PNG')
    im = Image.open(png).convert('RGBA'); px = im.load()
    ink = [px[x, y] for x in range(im.width) for y in range(im.height) if px[x, y][3] > 0]
    import status_art
    bb = im.getchannel('A').getbbox()
    expect(im.size == (statusbar.SLEEP_W, 16) and (bb[0], bb[2]) == (3, im.width) and ink and all(c[:3] == (255, 255, 255) for c in ink) and bb[3] - bb[1] == status_art.GLYPH_H,
           f'a white solid crescent {status_art.GLYPH_H} px tall (tools/status_art.py, the other status marks\' height) at the right of a 17 x 16 canvas, 3 px empty on the left')
    expect(statusbar.SLEEP_IMAGE not in palette.ACCENT_ALL and not statusbar.SLEEP_IMAGE.startswith(palette.ACCENT_GLYPH) and not statusbar.SLEEP_IMAGE.startswith(palette.WHOLE),
           'the accent lists name no pod_bar_sleep: neutral white like the other status glyphs (Light Mode flips it with them)')
    # room: the moon shows only if the right group's visible ink, the moon included, stays 3 px clear of the 12 h clock; it yields to every other mark (the review case: the AAC badge, Wi-Fi and the screenshot camera)
    xx = os.path.join(rootfs, 'release/assets/default/raw/images/xx')
    bbox = lambda f: Image.open(os.path.join(xx, f + '.png')).convert('RGBA').getchannel('A').getbbox()
    bt_ink = {DEFS[f'SLEEP_BT_{k}']: DEFS[f'SLEEP_INK_{v}'] for k, v in (('GLYPH', 'GLYPH'), ('CON', 'GLYPH'), ('AAC', 'AAC'), ('SBC', 'SBC'), ('LDAC', 'LDAC'), ('APTX', 'APTX'), ('APTXHD', 'APTXHD'))}
    expect(all(47 - bbox(f)[0] == ink and bbox(f)[2] == 47 for f, ink in bt_ink.items()), f'the Bluetooth ink widths match the images, each ending at the 47 px box\'s right edge ({bt_ink})')
    peers = {DEFS[k] for k in ('SYNC_IND', 'SLEEP_SYNCLINK', 'SLEEP_WIFI', 'SLEEP_SHOT')}
    ends = lambda c, texts: max(c.x + (c.w + StbText(font, int(c.get('style:normal:font_size'))).layout(t)[1]) // 2 for t in texts)
    H12, H24 = ('12:59 PM', '10:59 AM', '12:59 AM'), ('12:59', '23:59', '00:00')
    for what, bar in bars:
        g, c = bar.find('view_bar_right'), bar.find('bar_dclock')
        kids = [k.name for k in g.children]
        expect(c.x + c.w // 2 == 160 and c.get('style:normal:text_align_h') == 'center', f'{what}: the clock box is centred on the 320 px bar and its text centred in it, so the 12 h and the 24 h clock are both centred ({c.x}, {c.w})')
        expect(g.x + g.w - ends(c, H12) - 3 == DEFS['BAR_ROOM_12H'] and g.x + g.w - ends(c, H24) - 3 == DEFS['BAR_ROOM_24H'] and DEFS['SLEEP_GAP'] == statusbar.RGAP and f's={statusbar.RGAP}' in g.get('children_layout')
               and kids[0] == DEFS['SLEEP_BT'] and set(kids) - {DEFS['SLEEP_BT'], SLEEP} <= peers,
               f'{what}: BAR_ROOM_12H / _24H are the group\'s end less the 12 h / 24 h clock\'s ink end and 3 px, and every other child of the group is a counted peer ({kids})')
    expect('SLEEP_PCT' not in DEFS and 'SLEEP_PCT_DD' not in DEFS and DEFS['SLEEP_SHOT'] == 'pod_shot', 'the battery percentage is no peer (it sits inside the battery); the screenshot mark is')
    expect(bt_ink[DEFS['SLEEP_BT_APTXHD']] == 44 and max(v for k, v in bt_ink.items() if k != DEFS['SLEEP_BT_APTXHD']) == 38, 'the widest tags: aptX HD 44 px, then LDAC 38 px')
    w_box = {k.name: k.w for k in group.children}
    import itertools

    def ink_start(names, bt):
        """The leftmost ink of `names` laid out right-aligned from the group's end, RGAP px apart, in the group's order (Bluetooth: its image's ink); the group's end when none."""
        order = [n for n in [c.name for c in group.children] if n in names]
        if not order: return group.x + group.w
        start = group.x + group.w - sum(w_box[n] for n in order) - statusbar.RGAP * (len(order) - 1)
        return start + (47 - bt_ink[bt] if order[0] == DEFS['SLEEP_BT'] else 0)

    wrong, shown_cases, sync_hidden, shot_hidden, over = [], 0, 0, 0, set()
    BTS = (None, 'bar_bt', 'bar_aac', 'bar_sbc', 'bar_ldac', 'bar_aptx', 'bar_aptxhd')
    for h24, bt, link, sync, wifi, shot in itertools.product((0, 1), BTS, (0, 1), (0, 1), (0, 1), (0, 1)):
        m = sleep_machine(1, 900); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([h24]))
        m.setword(m.sleep + 8, statusbar.SLEEP_W)
        for name, on, width in ((DEFS['SLEEP_BT'], bt is not None, 47), (DEFS['SLEEP_SYNCLINK'], link, 16), (SYNC, sync, statusbar.SYNC_W), (DEFS['SLEEP_WIFI'], wifi, statusbar.WIFI_W), (DEFS['SLEEP_SHOT'], shot, 16)):
            wd = m.widget(name); m.setword(wd + 8, width); m.props[(wd, 'visible')] = int(bool(on))
        sw, pw = m.widget(SYNC), m.widget(DEFS['SLEEP_SHOT'])
        if bt: m.props[(m.widget(DEFS['SLEEP_BT']), 'image')] = m.cstr(bt)
        if sync: build(m)
        tick(m, '50'); shown = sleep_log(m) == [('widget_set_visible', 1), ('widget_set_sensitive', 1)]
        sync_shown, shot_shown = bool(m.props[(sw, 'visible')]), bool(m.props[(pw, 'visible')])
        # by rank: the camera fits beside stock's marks, the sync icon beside those and the camera as shown, the moon beside all of them: each 3 px clear of the clock of this mode
        lim = ends(clock, H24 if h24 else H12) + 3
        stock = {n for n, on in ((DEFS['SLEEP_BT'], bt), (DEFS['SLEEP_SYNCLINK'], link), (DEFS['SLEEP_WIFI'], wifi)) if on}
        want_shot = bool(shot) and ink_start(stock | {DEFS['SLEEP_SHOT']}, bt) >= lim
        base = stock | ({DEFS['SLEEP_SHOT']} if want_shot else set())
        want_sync = bool(sync) and ink_start(base | {SYNC}, bt) >= lim
        want_moon = ink_start(base | ({SYNC} if want_sync else set()) | {SLEEP}, bt) >= lim
        if (shot_shown, sync_shown, shown) != (want_shot, want_sync, want_moon): wrong.append((h24, bt, link, sync, wifi, shot, shot_shown, sync_shown, shown))
        if ink_start(stock, bt) < lim: over.add((h24, bt, link, wifi))
        shown_cases += shown; sync_hidden += bool(sync) and not sync_shown; shot_hidden += bool(shot) and not shot_shown
    expect(not wrong, f'every combination of clock mode, Bluetooth image, SyncLink, sync, Wi-Fi and screenshot mark: the camera, then the sync icon, then the moon, show exactly when the row\'s ink stays 3 px clear of the clock (wrong: {wrong[:4]})')
    expect(0 < shown_cases < 224 and 0 < sync_hidden < 112 and 0 < shot_hidden < 112, f'each of our marks shows in some combinations and yields in others (moon {shown_cases} of 224 shown, sync {sync_hidden} of 112 hidden, camera {shot_hidden} of 112 hidden)')
    expect(over == {(0, 'bar_aptxhd', 1, 1)}, f'stock\'s own marks fit left of the clock except aptX HD + SyncLink + Wi-Fi under the 12 h clock (82 px of 77; hook 40 hides SyncLink there): {sorted(over, key=str)}')
    # the camera's start check (patch/shot.c indicator): lo_shot_fits on the camera, its group holding the peers
    def shot_room(bt, h24=0, parent=True):
        m = machine(); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([h24])); grp = m.alloc(0x80); cam = m.widget(DEFS['SLEEP_SHOT']); m.setword(cam + 8, 16)
        if parent: m.setword(cam + DEFS['LO_W_PARENT'], grp)
        for name, width in ((DEFS['SLEEP_BT'], 47), (DEFS['SLEEP_WIFI'], statusbar.WIFI_W)): m.setword(m.widget(name) + 8, width); m.props[(m.widget(name), 'visible')] = 1
        m.props[(m.widget(DEFS['SLEEP_BT']), 'image')] = m.cstr(bt)
        return m.call(PSYMS['lo_shot_fits'], a0=cam, count=20000)
    expect((shot_room('bar_ldac'), shot_room('bar_aptxhd'), shot_room('bar_aptxhd', h24=1), shot_room('bar_btcondown'), shot_room('bar_btcondown', h24=1), shot_room('bar_aptxhd', parent=False)) == (1, 0, 1, 0, 1, 1),
           'the camera has room beside LDAC and Wi-Fi (76 px of 77); beside aptX HD (82) or an unlisted image (its whole 47 px box: 85) not under a 12 h clock, but under a 24 h one (92); no group: room')
    # hook 40 (lo_link_show): stock's widget_set_visible(img_synclink, 1); SyncLink shows exactly when Bluetooth, Wi-Fi and SyncLink stay 3 px clear of the clock, so stock's marks never reach it
    def link_show(bt, wifi, h24, on=1, kill=False, parent=True):
        m = machine(); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([h24])); grp = m.alloc(0x80); lw = m.widget(DEFS['SLEEP_SYNCLINK']); m.setword(lw + 8, 16); m.props[(lw, 'visible')] = 0
        if parent: m.setword(lw + DEFS['LO_W_PARENT'], grp)
        if kill: m.present.add(KILL)
        for name, vis, width in ((DEFS['SLEEP_BT'], bt is not None, 47), (DEFS['SLEEP_WIFI'], wifi, statusbar.WIFI_W)): m.setword(m.widget(name) + 8, width); m.props[(m.widget(name), 'visible')] = int(bool(vis))
        if bt: m.props[(m.widget(DEFS['SLEEP_BT']), 'image')] = m.cstr(bt)
        m.call(PSYMS['lo_link_show'], a0=lw, a1=on, a2=0, count=20000)
        return [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] == lw]
    wrong = []
    for h24, bt, wifi in itertools.product((0, 1), BTS, (0, 1)):
        lim = ends(clock, H24 if h24 else H12) + 3
        fits = ink_start({n for n, on in ((DEFS['SLEEP_BT'], bt), (DEFS['SLEEP_SYNCLINK'], 1), (DEFS['SLEEP_WIFI'], wifi)) if on}, bt) >= lim
        got = link_show(bt, wifi, h24)
        if got != [('widget_set_visible', int(fits)), ('widget_set_sensitive', int(fits))]: wrong.append((h24, bt, wifi, got))
    expect(not wrong, f'SyncLink shown (visible and sensitive) exactly when it fits beside the Bluetooth image and Wi-Fi, hidden and insensitive otherwise (wrong: {wrong[:3]})')
    expect(link_show('bar_aptxhd', 1, 0) == [('widget_set_visible', 0), ('widget_set_sensitive', 0)] and link_show('bar_aptxhd', 1, 1)[0] == ('widget_set_visible', 1),
           'the review case: aptX HD + Wi-Fi + SyncLink hides SyncLink under the 12 h clock, not under the 24 h one')
    expect(all(link_show('bar_aptxhd', 1, 0, **kw) == [('widget_set_visible', v)] for kw, v in (({'on': 0}, 0), ({'kill': True}, 1), ({'parent': False}, 1))),
           'stock\'s call unchanged when it hides SyncLink, with the kill switch, and without a group')
    # yielding: the screenshot mark appearing beside AAC and Wi-Fi (31 + 3 + 16 + 3 + 17 = 70 with the moon fits 77; the camera too is 89) hides the moon on the next tick; its going away brings it back
    m = sleep_machine(1, 900); m.setword(m.sleep + 8, statusbar.SLEEP_W)
    for name, width in ((DEFS['SLEEP_BT'], 47), (DEFS['SLEEP_WIFI'], statusbar.WIFI_W)): m.setword(m.widget(name) + 8, width)
    m.props[(m.widget(DEFS['SLEEP_BT']), 'image')] = m.cstr('bar_aac'); pw = m.widget(DEFS['SLEEP_SHOT']); m.setword(pw + 8, 16); m.props[(pw, 'visible')] = 0
    tick(m, '50'); first = sleep_log(m); m.props[(pw, 'visible')] = 1; m.calls = []; tick(m, '50'); second = sleep_log(m); m.props[(pw, 'visible')] = 0; m.calls = []; tick(m, '50')
    expect(first == [('widget_set_visible', 1), ('widget_set_sensitive', 1)] and second == [('widget_set_visible', 0), ('widget_set_sensitive', 0)] and sleep_log(m) == first,
           'AAC + Wi-Fi: the moon shows; the screenshot camera appears: it hides; the camera goes: it shows again')
    # the sync icon yields too: AAC, Wi-Fi and the camera with it are 31 + 3 * 19 = 88, over the 12 h room (77) and within the 24 h one (92)
    for h24 in (0, 1):
        m = machine(sync=True); m.u.mem_write(pod.DATA['TIME_24H'][0], bytes([h24])); m.setword(m.sync + 8, statusbar.SYNC_W)
        for name, width in ((DEFS['SLEEP_BT'], 47), (DEFS['SLEEP_WIFI'], statusbar.WIFI_W), (DEFS['SLEEP_SHOT'], 16)): m.setword(m.widget(name) + 8, width)
        m.props[(m.widget(DEFS['SLEEP_BT']), 'image')] = m.cstr('bar_aac'); build(m); tick(m, '50')
        expect(sync_log(m) == ([('widget_set_visible', 1), ('widget_set_sensitive', 1)] if h24 else []), f'AAC + Wi-Fi + camera, {"24" if h24 else "12"} h clock: a cover build {"shows" if h24 else "does not show"} the sync icon ({sync_log(m)})')
    m = sleep_machine(1, 900); m.setword(m.sleep + 8, statusbar.SLEEP_W); m.calls = []; tick(m, '50')
    expect(m.icount < 3000, f'cost with the timer running: {m.icount} instructions')

    # the palette follows the window in front on the real bar's tick (pal_bar_follow, test/pod/palette.py bar_follow_tests): under Tinted, a bar painted under Now Playing is repainted once
    # the Sleep Timer page is in front
    def follow_machine(kind):
        m = machine(); bar = m.word(m.word(m.label + DEFS['LO_W_PARENT']) + DEFS['LO_W_PARENT']); m.types[bar] = kind
        m.fs['/mnt/data/m1plus/appearance-background'] = b'1\n'; m.fs['/mnt/data/m1plus/appearance-accent'] = b'4\n'
        np_win = m.alloc(0x80); m.setword(np_win + 0x10, m.cstr('playing_page')); m.top_main = np_win
        tick(m, '50')
        paint = m.bound.get((bar, O['EVT_BEFORE_PAINT']))
        if paint: m.call(paint[0], a0=paint[1], a1=0, count=20000)   # the bar painted under Now Playing
        tick(m, '50'); quiet = not [c for c in m.calls if c[0] == 'widget_invalidate_force']
        page = m.alloc(0x80); m.setword(page + 0x10, m.cstr('m1plus_sleeptimer')); m.top_main = page; tick(m, '50')
        return paint, quiet, [c[1] for c in m.calls if c[0] == 'widget_invalidate_force'], bar
    paint, quiet, inv, bar = follow_machine('system_bar')
    expect(paint and quiet and inv == [bar], 'the status bar\'s tick: its paints are listened to, steady under Now Playing, then the Sleep Timer page in front repaints the bar once')
    paint, quiet, inv, bar = follow_machine('view')
    expect(not paint and not inv, 'the pull-down\'s bar copy (a view in the dialog, which paints itself whole) is not followed')

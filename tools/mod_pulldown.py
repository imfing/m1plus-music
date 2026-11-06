#!/usr/bin/env python3
"""The pull-down control centre: its status bar the real one, its text one step smaller (V2.1gB, docs/ui.md).

ui/dialog/dropdown_dialog.bin (the dialog has no page theme, styles/ has no
dropdown_dialog.bin) carries its own copy of the status bar (view_sysbar) and the tile captions:

  view_sysbar    laid out from the table the real bar (ui/system_bar.bin) uses, tools/statusbar.py: left group
                 at x 10, 4 px spacing, the volume number 16 px middle in 30 px, the clock 104..194 at 18 px, the
                 right group 4 px spacing and clear of the battery; the bar black as the real one
  label_*        the eight tile captions (Wi-Fi, Bluetooth, Buttons lock, gain, USB mode, output,
                 Playback / System Setting), word-wrapped in 57 x 40 boxes  18 -> 16 (normal),
                                                                            16 -> 14 (disable, focused)

pgbar_battery shows no number there (show_text false, stock), the slider and the icons have no text.
The caption boxes are widened from 57 to 71 px around the same centre (the tiles are 74 px apart, so
3 px stay between neighbours): "Bluetooth" is 60 px at 16, so in 57 AWTK broke it as "Bluetoot/h" and
"Playbac/k Setting". Nothing else moves; the boxes keep height and vertical alignment (stock:
middle, or AWTK's default, which centres too), so the text stays centred. The tool measures what it
sets with the shared text model (awtk_text.StbText: truncated advances + 1 px per glyph) in the
tree's own font, so it must run after the font step:

  - "100" (the widest volume) must fit label_volume (30 px);
  - "12:59 PM" (the widest clock) must fit bar_dclock;
  - every tile caption in English and Simplified Chinese (strings/en_US.bin, zh_CN.bin, the keys
    demo sets @0x4743c8..) must wrap into the 40 px box (lines x font size), greedy word wrap as
    AWTK breaks lines, and no Latin word may be broken inside; the other languages are reported
    (several overflow or break words already in stock).

Usage: mod_pulldown.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statusbar
from modlib import clone_workdir, edit_ui
from awtk_text import Ttf, awtk_width

RAW = 'rootfs/release/assets/default/raw'
DIALOG = 'ui/dialog/dropdown_dialog.bin'
FONT = 'rootfs/release/assets/default/raw/fonts/default.ttf'
STATES = ('normal', 'disable', 'focused')
# old -> new inline font sizes
TILE = {18: 16, 16: 14}
TILES = ('label_wifi', 'label_bt', 'label_lock', 'label_gain', 'label_usbmode', 'label_outputway',
         'label_playset', 'label_sysset')
# the tile captions' string keys (demo @0x4743c8..0x474b70: widget_set_tr_text on the labels above)
TILE_KEYS = ('wifiset_wifi', 'wifiset_bt', 'system_keylock', 'gain_high', 'gain_low', 'sset_outputway',
             'playset', 'sysset', 'usbmode_audio', 'usbmode_dac', 'usbmode_storge')
MUST_FIT = ('en_US', 'zh_CN')
VOLUME_MAX, CLOCK_MAX = '100', '12:59 PM'
TILE_W, TILE_DX = 71, -7                 # caption box width and x shift (stock 57; the box centre stays)


def check(ok, msg):
    if not ok: raise SystemExit(f'mod_pulldown: {msg}')


def strings(path, keys):
    """key -> text from an AWTK strings/*.bin (a table of NUL-terminated key, value pairs)."""
    d = open(path, 'rb').read(); out = {}
    for k in keys:
        i = d.find(b'\0' + k.encode() + b'\0')
        if i < 0: continue
        j = i + len(k) + 2
        out[k] = d[j:d.index(b'\0', j)].decode('utf-8')
    return out


def wrap(ttf, text, px, width):
    """Lines of a word-wrapped label: break after spaces, before and after CJK characters, and
    inside a word that is wider than the box on its own (AWTK's line breaker does the same)."""
    toks, cur = [], ''
    for ch in text:
        if ch == ' ': toks.append(cur + ' '); cur = ''
        elif ord(ch) >= 0x2e80:
            if cur: toks.append(cur); cur = ''
            toks.append(ch)
        else: cur += ch
    if cur: toks.append(cur)
    lines, line = [], ''
    for t in toks:
        if awtk_width(ttf, (line + t).rstrip(), px) <= width: line += t; continue
        if line.strip(): lines.append(line.rstrip())
        line = ''
        while awtk_width(ttf, t.rstrip(), px) > width:
            k = len(t)
            while k > 1 and awtk_width(ttf, t[:k], px) > width: k -= 1
            lines.append(t[:k]); t = t[k:]
        line = t
    if line.strip(): lines.append(line.rstrip())
    return lines


def split_words(ttf, text, px, width):
    """Latin words wider than the box (AWTK would break them inside)."""
    return [t for t in text.split(' ') if t.isascii() and awtk_width(ttf, t, px) > width]


def resize(w, table, states=STATES):
    """Every state that sets a font size gets the table's smaller one; returns {old: new}."""
    done = {}
    for st in states:
        v = w.get(f'style:{st}:font_size')
        if v is None: continue
        check(int(v) in table, f'{w.name}: unexpected {st} font size {v}')
        w.set(f'style:{st}:font_size', str(table[int(v)])); done[int(v)] = table[int(v)]
    check(done, f'{w.name}: no inline font size')
    return done


def edit(root, ttf, texts, report):
    shape = [(w.type, w.name, w.x, w.y, w.w, w.h) for w in root.walk()]
    sysbar = root.find('view_sysbar')
    check(sysbar is not None and all(sysbar.find(n) is not None for n in statusbar.NAMES), 'unexpected pull-down layout')
    # the pull-down's copy of the status bar is laid out from the real bar's table (tools/statusbar.py): identical
    # positions, sizes and styles, on the real bar's black
    statusbar.apply(sysbar)
    for st in statusbar.STATES: sysbar.set(f'style:{st}:bg_color', statusbar.BAR_BG)
    vol, clock = sysbar.find('label_volume'), sysbar.find('bar_dclock')
    px = int(vol.get('style:normal:font_size')); need = awtk_width(ttf, VOLUME_MAX, px)
    check(need <= vol.w, f'"{VOLUME_MAX}" needs {need} px at {px}, label_volume is {vol.w}')
    cpx = int(clock.get('style:normal:font_size')); cw = awtk_width(ttf, CLOCK_MAX, cpx)
    check(cw <= clock.w, f'"{CLOCK_MAX}" needs {cw} px at {cpx}, the clock box is {clock.w}')
    report.append(f'status bar as the real one (statusbar.py): "{VOLUME_MAX}" {need}/{vol.w} px at {px}, "{CLOCK_MAX}" {cw}/{clock.w} px at {cpx}')
    for name in TILES:
        w = root.find(name); check(w is not None and w.type == 'label', f'{name} missing')
        spx = int(w.get('style:normal:font_size'))
        check(w.w == 57, f'{name}: unexpected caption width {w.w}')
        w.x += TILE_DX; w.w = TILE_W      # before measuring: fits() reads w.w
        changed = resize(w, TILE)
        tpx = int(w.get('style:normal:font_size'))
        fits = lambda t, px, bw=w.w: len(wrap(ttf, t, px, bw)) * px <= w.h
        for lang in MUST_FIT:
            for k, t in texts[lang].items():
                check(not split_words(ttf, t, tpx, w.w), f'{lang} {k} {t!r}: a word is wider than {w.w} px at {tpx}')
                check(fits(t, tpx), f'{lang} {k} {t!r} does not fit {w.w}x{w.h} at {tpx}: {wrap(ttf, t, tpx, w.w)}')
        if name == TILES[0]:   # the boxes are all the same size: count once
            over = lambda px, bw: sorted(f'{l}:{k}' for l, kv in texts.items() for k, t in kv.items() if not fits(t, px, bw))
            report.append(f'tile captions over 40 px: {len(over(spx, 57))} at {spx} px x 57 (stock), {len(over(tpx, w.w))} at {tpx} px x {w.w} '
                          f'(none in {"/".join(MUST_FIT)}); still over: {", ".join(over(tpx, w.w))}')
    report.append(f'tiles {changed}')
    after = [(w.type, w.name, w.x, w.y, w.w, w.h) for w in root.walk() if w.name not in (statusbar.LO_WIDGET, statusbar.SYNC_WIDGET)]   # (the Line Out pill and the sync icon statusbar.apply adds are the new widgets)
    bar_names = {w.name for w in sysbar.walk()}
    moved = [a for a, b in zip(shape, after) if a != b and a[1] not in bar_names and a[1] not in TILES]   # the bar's own widgets and the caption boxes
    check(len(shape) == len(after) and not moved, f'widgets moved: {moved}')


def apply(work):
    ttf = Ttf(os.path.join(work, FONT))
    langs = os.path.join(work, RAW, 'strings')
    texts = {f[:-4]: strings(os.path.join(langs, f), TILE_KEYS) for f in sorted(os.listdir(langs)) if f.endswith('.bin')}
    check(all(len(texts[l]) == len(TILE_KEYS) for l in MUST_FIT), 'tile caption strings missing')
    out = []
    path = os.path.join(work, RAW, DIALOG)
    report = []
    old, new, _ = edit_ui(path, lambda root: edit(root, ttf, texts, report))
    out.append(f'{os.path.relpath(path, work)}: {len(old)} -> {len(new)} bytes')
    out += [f'  {r}' for r in report]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('out')
    a = ap.parse_args()
    clone_workdir(a.src, a.out)
    for line in apply(a.out): print('pulldown:', line)


if __name__ == '__main__': main()

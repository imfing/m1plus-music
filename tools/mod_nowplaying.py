#!/usr/bin/env python3
"""Apple-Music-style Now Playing for the Shanling M1 Plus: ui + page theme + new images, and five pinned words of demo
(the A-B markers), re-fitted to the 320x450 portrait window (docs/ui.md "Now Playing"):

   0   ====== (grabber pill, the Back button 120x44)
  28   +----------------------------+
       |   cover 264 x 264, r 12    |       slide page 1: the file is 264 px (1:1); the payload rounds the corners
 292   +----------------------------+
 296           . o .                         micro page dots (4 px)
 305   Title                  (star)(...)   20 px white; star and More 44 px targets on 32 px translucent discs
 329   Artist                              18 px #AAAAAA
 348   ================---------------        6 px rounded progress bar (ink 360..366) in the stock 30 px seek target
 379   1:23                        -3:42    14 px #AAAAAA (digits 382..391); the right one is the remaining time (patch/nowplaying.c)
 392   [mode] [<<]   [ || ]   [>>]  [queue]   58 px transport row in the five stock slots (glyphs 407..435)
 450

The window is the cover's colour, darkened (patch/nowplaying.c writes bg_color per track; the asset's is the neutral
tone), under a static black gradient (np_tint.png, alpha 0.15 at the top to 0.92 at the bottom) that is the
first child of view_local. The album line, the "3/12" index and the quality line are not on the art page: label_album
stays on the info page, label_index is hidden at 0x0 like img_hr, label_info stays on the info page.

What demo drives here, by name (disasm.py xref, docs/ui.md): scrlabel_title, scrlabel_artist, img_playcover,
label_index ("%d/%d"), label_info, label_album/genre/year/size/location ("%s:%s"), label_playtime, label_playlen,
slider_play, img_repeata/b (moved by code to x = 12 + pos*296/len, y = 364; five pinned immediates make it x =
28 + pos*264/len, y = 370: the bar's centre + 7), img_hr, img_mqa, btn_fav/more/playmode/prev/play/next/queue/
return, image_wait, slide_view, slide_indicator, view_lrc, scroll_lrc, label_lyricmsg, view_local/view_dlna,
app_gesture. Every one keeps its name; the new widgets are img_np_tint, np_remaining and np_elapsed.

Files (every image is new and referenced only from these two files):
  ui/playing_page.bin      geometry and inline styles
  styles/playing_page.bin  the page's own theme (searched before default.bin, see docs/ui.md): mode/fav icons -> np_*,
                           page-local btn_imgplay_style / btn_imgpause_style and lyric line styles
  images/xx/np_*.png       the glyphs (tools/mod_icons.py draws them; this step copies the committed PNGs) and the
                           gradient (drawn here)
  rootfs/release/bin/demo  five pinned immediates of the A-B marker position (getx_by_playtime)

Usage: mod_nowplaying.py SRC_WORKDIR OUT_WORKDIR
  OUT_WORKDIR == SRC_WORKDIR edits in place.
"""
import os, shutil, struct, sys
from math import erf, sqrt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui, awtk_style, mod_icons
from modlib import clone_workdir, edit_ui, write_keep_mode

from awtk_ui import RAW
UI = f'{RAW}/ui/playing_page.bin'
STYLE = f'{RAW}/styles/playing_page.bin'
IMAGES = f'{RAW}/images/xx'
DEMO = 'rootfs/release/bin/demo'
IMG_MODE, IMG_MTIME = 0o755, 1750924035     # most stock images are 755; a stock asset mtime, fixed for determinism

W, H = 320, 450                  # normal window under the 30 px status bar
STATES = ('normal', 'disable', 'focused')
BTN_STATES = ('normal', 'disable', 'focused', 'over', 'pressed')
BG = '#202020'                   # the neutral tone: the window until a cover tints it (patch/offsets.inc NP_NEUTRAL)
FG = '#EEEEEC'                   # q2-pod MINIMAL_FILL: glyphs, selected lyric
DOWN = '#8C8C8C'                 # q2-pod SUDO_MUTED: pressed glyphs
LYR_DIM = '#C4C4C4'              # the other lines of the stock lyric list (shown only without the payload): lighter than DOWN, 2.5:1 or better under the lyrics scrim on every tone (test/pod/nowplaying.py)
TITLE_RGB, GREY = '#FFFFFF', '#AAAAAA'      # secondary text is one grey (V2.1lA)
TITLE_PX, META_PX, TIMES_PX = 20, 18, 14
TRACK, FILL = '#FFFFFF4D', '#FFFFFEEB'      # progress bar: white 30 % track (was 20 %: lost on dark tints), 92 % fill (over the tint; #FFFFFE not #FFFFFF: palette.ROLE_PROGRESS, the accent maps it, the page dots keep #FFFFFFEB)
DOT_OFF, DOT_ON = '#FFFFFF46', '#FFFFFFEB'
TINT_ALPHA = (38, 235)           # np_tint.png: black, alpha at the top .. at the bottom (0.15 .. 0.92)
# The lyrics and info pages put text over whatever the cover's tone is; a translucent black scrim (np_scrim.png, an asset-only
# image, the first child of view_lyrics and view_info, insensitive) darkens the band behind it, soft at its top and bottom
# edges. The art page keeps the full tint.
SCRIM = (0, 8, W, 324)            # x, y, w, h in the page: y 8 .. 332; the text lies in 44 .. 288, inside the full-strength middle
SCRIM_ALPHA, SCRIM_EDGE = 128, 36 # 50 % black; the edges ramp from 0 over SCRIM_EDGE rows (test/pod/nowplaying.py)
# The lyrics page has its own, lighter scrim (np_scrim_lyrics.png): Apple Music shows the cover's colour with no heavy black band. The bold white
# lines need less behind them than the info page's small grey text; 68 (27 %) is the lowest alpha that keeps the current line at 4.5:1 and the next at
# 2.3:1 on the worst tone (test/pod/lyrics.py). The edges ease in over LSCRIM_EDGE rows (smoothstep), so there is no visible band edge; the text area (44..288) is the full-strength middle.
LSCRIM = (0, 0, W, 332)
LSCRIM_ALPHA, LSCRIM_EDGE = 68, 44
DOT = 10                         # the interlude dots' diameter (patch/offsets.inc LY_DOT): np_dot.png, white, anti-aliased; the payload makes three image widgets

M = 28                           # side margin: the cover, the text column and the bar share it
ART, ART_R = 264, 12             # cover = what demo writes (mod_lockscreen.COVER_SIZE, 1:1), corner radius
ART_X, ART_Y = M, 28
# The soft shadow under the cover (np_shadow.png, an asset-only image, insensitive, a child of page 1 so it slides with the art): the
# art's rectangle shifted down SHADOW_DY, blurred by a Gaussian of SHADOW_SIGMA px, black, SHADOW_ALPHA (55 %) under the art, which makes the visible maximum (just under the bottom edge) 38 %, laid over the cover
# with a hole of the art's rounded rectangle (so the payload's corner fills are shadowed too). SHADOW_PAD px on every side hold the
# blur: 24 > 3 sigma, and the 312 px image (4 .. 316) stays inside the 320 px page.
SHADOW_PAD, SHADOW_SIGMA, SHADOW_DY, SHADOW_ALPHA = 24, 7.0, 4, 140
SHADOW_SIZE = ART + 2 * SHADOW_PAD
SLIDE_H = 352                    # slide pages 0..352 hold art, dots, title and artist; lyrics and info end at 288
DOTS = (145, 296, 30, 4)         # 3 dots of size 4, 10 apart, centred in the window
TITLE_Y, TITLE_H, ARTIST_Y, ARTIST_H, TEXT_W = 305, 24, 329, 22, 182   # the 46 px block is centred on the star / More discs (y 310..346, centre 328)
BTN, FAV_X, MORE_X, BTN_Y = 44, 210, 254, 306       # star and More: 44 px targets right of the text, 32 px discs in the PNGs; the More disc ends at W - M (292), as the text starts at M
RETURN = (100, 0, 120, 44)       # the grabber pill is drawn in the button (np_grabber), over the art's top 16 px
# The lower half's rhythm, measured on ink: artist ink bottom 344, then 16 px of air to the bar (ink 360..366), 16 to the
# times (digits 382..391), 16 to the transport glyphs (pause bars 407..435), and 15 from their bottom to the window's
# (stock-ish V2.1nL had 22 / 13 / 17 / 11). Each box is placed from its font's ink offset: the 14 px digits start 3 px under
# their label's top; the glyphs are centred in the row (ROW_Y + ROW_H / 2 = 421, the glyphs' centre).
SLIDER = (M, 348, W - 2 * M, 30)  # stock 30 px target; bar_size 6 centred at y 363
BAR = 6
TIMES_Y, TIMES_H, TIMES_W = 379, 18, 72   # 14 px: "-0:00:00" is 8 characters (test/pod/nowplaying.py measures it)
ROW_Y = 392                      # transport row 392..450, glyphs centred on 421
ROW_H = H - ROW_Y
SVV_H = TIMES_Y + TIMES_H        # slide_view_view ends under the times, which it parents (the row overlaps its last 5 px, on top)
# transport slots: x, w (sum 320 incl. 4 px edges); the image_wait spinner centres on play
SLOTS = {'btn_playmode': (4, 56), 'btn_prev': (64, 60), 'btn_play': (124, 72), 'btn_next': (196, 60), 'btn_queue': (260, 56)}
LYR_FONT, LYR_LEFT = 30, 2   # patch/offsets.inc LY_FONT; text_align_h in this build: 0 none, 1 centre, 2 left, 3 right (the stock 'msg*_style' names)
LYR_SPACER = 4               # AWTK's row pitch inside a wrapped label is font_size + the style's `spacer` (label paint, 0x62e9f8; default 2): LY_LINE_H = 30 + 4 = 34
LYR_WHITE = '#FFFFFF'        # every lyric line is white; the current one is only the most opaque (patch/lyrics.c ly_opacity)
LYR_FACE = 'lyrics'          # font_name of the bold face: assets/default/raw/fonts/lyrics.ttf (tools/mod_font.py lyric_face)
# patch/lyrics.c: a line of Latin, Greek and Cyrillic only is drawn in the bold file, any other line in the default font (AWTK has no per-glyph fallback)
LYRIC_LABEL_STYLES = {'np_lyric_style': LYR_FACE, 'np_lyric_cjk_style': None}
LYR_Y, LYR_H = 44, 244           # the lyrics list; the info lines end at 288 too (the dots sit at 296)

# The A-B repeat markers: demo moves img_repeata/b to x = 12 + (pos - cue) * 296 / len, y = 364 (getx_by_playtime
# 0x53b824 and its caller 0x53b8f0, only from this page's timer): `addiu v0, zero, 0x128`, `addiu v0, v0, 0xc` and three
# `addiu a2, zero, 0x16c`. They are moved to the new bar: x from SLIDER's left over its width, y = bar centre + 7 (stock:
# 357 + 7 = 364, a dot under the 4 px bar). Every patched word and the two functions' PIC prologues are pinned.
MARKER_X_SCALE, MARKER_X_OFFSET, MARKER_Y = 0x53b8d4, 0x53b8ec, (0x53b9c4, 0x53ba48, 0x53ba64)
MARKER_WORDS = {MARKER_X_SCALE: 0x24020128, MARKER_X_OFFSET: 0x2442000c, **{a: 0x2406016c for a in MARKER_Y}}
MARKER_PINS = {0x53b824: 0x3c1c004d, 0x53b828: 0x279c86ac, 0x53b82c: 0x0399e021, 0x53b8f0: 0x3c1c004d,
               0x53b8f4: 0x279c85e0, 0x53b8f8: 0x0399e021, 0x53b9bc: 0x0411ff99, 0x53ba2c: 0x0411ff7d, 0x53ba40: 0x0411ff78}

# ---------------------------------------------------------------------------------------------- the tone (patch/nowplaying.c)

# patch/offsets.inc NP_*: the cover's average colour becomes value NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) / 255 (v = the
# brightest channel), every channel keeping 23/25 (0.92) of its distance from v (HSV saturation x 0.92; it was 4/5); black is the neutral tone. test/pod/nowplaying.py
# runs the compiled C against this reference.
NP_V_MIN, NP_V_MAX, NP_SAT_NUM, NP_SAT_DEN, NP_NEUTRAL = 32, 192, 23, 25, (0x20, 0x20, 0x20)

def tone(r, g, b):
    v = max(r, g, b)
    if not v: return NP_NEUTRAL
    vt = NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) // 255
    return tuple(vt - vt * NP_SAT_NUM * (v - c) // (NP_SAT_DEN * v) for c in (r, g, b))

def corner_alpha():
    """patch/nowplaying.c np_corner_init: the top left corner of the art, ART_R x ART_R pixels, the coverage (0..255) of
    the area outside a quarter circle of radius ART_R centred on the square's inner corner, 8 x 8 samples a pixel."""
    c, out = 16 * ART_R, []
    for y in range(ART_R):
        for x in range(ART_R):
            n = sum((2 * (x * 8 + i) + 1 - c) ** 2 + (2 * (y * 8 + j) + 1 - c) ** 2 > c * c for i in range(8) for j in range(8))
            out.append((n * 255 + 32) // 64)
    return out

_CORNER = []
def corner_table():
    """corner_alpha(), computed once."""
    if not _CORNER: _CORNER.append(corner_alpha())
    return _CORNER[0]

def tint_alpha(y):
    """The gradient's alpha (0..255) on window row y."""
    return TINT_ALPHA[0] + ((TINT_ALPHA[1] - TINT_ALPHA[0]) * y + (H - 1) // 2) // (H - 1)

# ---------------------------------------------------------------------------------------------- images

# PIL is imported where it is used, so build.py (plain python3) can import added_rels() without pillow
def tint_gradient():
    """Black, alpha rising down the window: the cover's colour fades to black."""
    from PIL import Image
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for y in range(H): im.paste((0, 0, 0, tint_alpha(y)), (0, y, W, y + 1))
    return im

def scrim_alpha(y):
    """np_scrim.png's alpha on row y of its SCRIM[3] rows: SCRIM_ALPHA in the middle, ramping linearly to 0 at the first and last row."""
    d = min(y, SCRIM[3] - 1 - y)
    return SCRIM_ALPHA if d >= SCRIM_EDGE else SCRIM_ALPHA * d // SCRIM_EDGE

def lscrim_alpha(y):
    """np_scrim_lyrics.png's alpha on row y of its LSCRIM[3] rows: LSCRIM_ALPHA in the middle, easing (smoothstep 3t^2 - 2t^3) to 0 over LSCRIM_EDGE rows at both ends."""
    d = min(y, LSCRIM[3] - 1 - y)
    return LSCRIM_ALPHA if d >= LSCRIM_EDGE else LSCRIM_ALPHA * (3 * d * d * LSCRIM_EDGE - 2 * d ** 3) // LSCRIM_EDGE ** 3

def scrim_image(lyrics=False):
    from PIL import Image
    box, alpha = (LSCRIM, lscrim_alpha) if lyrics else (SCRIM, scrim_alpha)
    im = Image.new('RGBA', box[2:], (0, 0, 0, 0))
    for y in range(box[3]): im.paste((0, 0, 0, alpha(y)), (0, y, box[2], y + 1))
    return im

def dot_alpha(x, y):
    """np_dot.png's alpha on pixel (x, y) of its DOT square: a white disc of diameter DOT, 8 x 8 samples a pixel (coverage 0..255)."""
    n, c = 8, DOT / 2
    hit = sum((x + (i + .5) / n - c) ** 2 + (y + (j + .5) / n - c) ** 2 <= c * c for i in range(n) for j in range(n))
    return round(255 * hit / (n * n))

def dot_image():
    from PIL import Image
    im = Image.new('RGBA', (DOT, DOT)); px = im.load()
    for y in range(DOT):
        for x in range(DOT): px[x, y] = (255, 255, 255, dot_alpha(x, y))
    return im

def shadow_alpha(x, y):
    """np_shadow.png's alpha on pixel (x, y) of its SHADOW_SIZE square (0..255): the Gaussian-blurred rectangle of the art (shifted
    down SHADOW_DY, maximum SHADOW_ALPHA), seen only where the art is not: the area outside the art's rounded rectangle. The
    image lies over the cover, so it also darkens the four corner squares the payload paints in the window colour, anti-aliased
    with the same coverage (corner_alpha); the art itself is untouched."""
    ax, ay = x - SHADOW_PAD, y - SHADOW_PAD
    def prof(p, a):      # the interval [a, a + ART) blurred by the Gaussian, at the pixel centre p
        k = SHADOW_SIGMA * sqrt(2)
        return 0.5 * (erf((p + 0.5 - a) / k) - erf((p + 0.5 - a - ART) / k))
    out = 255
    if 0 <= ax < ART and 0 <= ay < ART:
        cx, cy = ax if ax < ART_R else ART - 1 - ax, ay if ay < ART_R else ART - 1 - ay
        out = corner_table()[cy * ART_R + cx] if cx < ART_R and cy < ART_R else 0
    return round(SHADOW_ALPHA * prof(ax, 0) * prof(ay, SHADOW_DY) * out / 255)

def shadow_image():
    from PIL import Image
    im = Image.new('RGBA', (SHADOW_SIZE, SHADOW_SIZE), (0, 0, 0, 0)); px = im.load()
    for y in range(SHADOW_SIZE):
        for x in range(SHADOW_SIZE): px[x, y] = (0, 0, 0, shadow_alpha(x, y))
    return im

LIVE_W, LIVE_GAP = 44, 8                                      # the LIVE label's width and the gap either side of it
LIVE_BAR_W = (W - 2 * M - LIVE_W - 2 * LIVE_GAP) // 2          # each capsule's width
LIVE_BAR_H, LIVE_BAR_OUT, LIVE_BAR_IN = 4, 0.45, 0.05      # Radio Now Playing's LIVE capsules (rn_live_l / rn_live_r): height, white alpha at the outer end and next to LIVE

def live_bar_image(w, right):
    """rn_live_l.png / rn_live_r.png: a w x LIVE_BAR_H white capsule (fully rounded ends, 8 x 8 samples a pixel) whose alpha runs from LIVE_BAR_OUT at the
    outer end to LIVE_BAR_IN at the inner end along a smoothstep; the right bar is the left one mirrored."""
    from PIL import Image
    h, r, n = LIVE_BAR_H, LIVE_BAR_H / 2, 8
    im = Image.new('RGBA', (w, h)); px = im.load()
    for y in range(h):
        for x in range(w):
            cov = 0
            for sy in range(n):
                for sx in range(n):
                    fx, fy = x + (sx + .5) / n, y + (sy + .5) / n
                    dx = max(r - fx, fx - (w - r), 0); dy = fy - r
                    cov += dx * dx + dy * dy <= r * r
            t = (x + .5) / w; t = t * t * (3 - 2 * t)
            px[x, y] = (255, 255, 255, round(255 * cov / (n * n) * (LIVE_BAR_OUT + (LIVE_BAR_IN - LIVE_BAR_OUT) * t)))
    return im.transpose(Image.FLIP_LEFT_RIGHT) if right else im

def write_images(rootfs_xx):
    """The glyphs (committed PNGs of mod_icons.py), the corner mask and the gradient, as new files; returns the names."""
    for name in NP_IMAGES:
        p = os.path.join(rootfs_xx, name + '.png')
        assert not os.path.exists(p), p
        if name == 'np_tint': tint_gradient().save(p, optimize=True)     # PIL PNG output has no timestamp
        elif name == 'np_scrim': scrim_image().save(p, optimize=True)
        elif name == 'np_scrim_lyrics': scrim_image(True).save(p, optimize=True)
        elif name == 'np_dot': dot_image().save(p, optimize=True)
        elif name == 'np_shadow': shadow_image().save(p, optimize=True)
        elif name in ('rn_live_l', 'rn_live_r'): live_bar_image(LIVE_BAR_W, name.endswith('r')).save(p, optimize=True)
        else: shutil.copyfile(os.path.join(mod_icons.PNG, name + '.png'), p)
        os.chmod(p, IMG_MODE); os.utime(p, (IMG_MTIME, IMG_MTIME))
    return list(NP_IMAGES)

NP_IMAGES = sorted(mod_icons.np_names() + ['np_tint', 'np_scrim', 'np_scrim_lyrics', 'np_dot', 'np_shadow', 'rn_live_l', 'rn_live_r'])

def added_rels(stock_rootfs=None):
    """Rootfs-relative paths of the added images (for fwtool --allow-added; all new in any tree)."""
    return [f'{IMAGES.removeprefix("rootfs/")}/{n}.png' for n in NP_IMAGES]

# ---------------------------------------------------------------------------------------------- ui

def each(w, states, prop, value):
    for st in states: w.set(f'style:{st}:{prop}', value)

def text_style(w, px, rgb, align):
    """Font, colour and alignment in every state: some labels on this page paint in the disable state
    (q2-pod found the same on the Q2), so a lone normal value would not apply."""
    each(w, STATES, 'font_size', str(px)); each(w, STATES, 'text_color', rgb); each(w, STATES, 'text_align_h', align)

def img_button(w, normal, pressed):
    w.set('style', 'img_btn_style')
    for st in BTN_STATES: w.set(f'style:{st}:bg_image', pressed if st == 'pressed' else normal)

def move(w, x, y, ww, hh): w.x, w.y, w.w, w.h = x, y, ww, hh

def hide(w):
    """Kept in the tree (the app looks it up), shown by nobody: visible=false does not stop hit testing, so it is also insensitive."""
    move(w, 0, 0, 0, 0); w.set('visible', 'false'); w.set('sensitive', 'false')

def find(root, name):
    w = root.find(name); assert w is not None, f'playing_page: no widget {name!r}'; return w

def parent_of(root, child):
    for w in root.walk():
        if child in w.children: return w

def apply_ui(root):
    names = [w.name for w in root.walk() if w.name]
    gesture, local = find(root, 'app_gesture'), find(root, 'view_local')
    svv, sv = find(root, 'slide_view_view'), find(root, 'slide_view')
    page1, lyr, info = (find(root, n) for n in ('view', 'view_lyrics', 'view_info'))
    assert sv.children == [page1, lyr, info] and parent_of(root, sv) is svv and parent_of(root, svv) is local, 'unexpected playing_page layout'

    root.set('style:normal:bg_color', BG)
    # the gesture/content area fills the 450 px window (stock: 438, centred)
    gesture.set('self_layout', f'default(x=c,y=m,w={W},h={H})'); move(gesture, 0, 0, W, H)
    move(local, 0, 0, W, H)
    # the gradient first: it is painted before everything else of the page and never takes a touch
    tint = awtk_ui.Widget('image', 0, 0, W, H, [('name', 'img_np_tint'), ('image', 'np_tint'), ('draw_type', 'default'),
                          ('clickable', 'false'), ('sensitive', 'false')])
    local.children.insert(0, tint)

    # the scrim behind the text of the lyrics and info pages (the first child: painted under the lines, never takes a touch)
    for page, box, img in ((lyr, LSCRIM, 'np_scrim_lyrics'), (info, SCRIM, 'np_scrim')):
        page.children.insert(0, awtk_ui.Widget('image', *box, [('name', 'img_np_scrim_' + page.name.removeprefix('view_')), ('image', img), ('draw_type', 'default'),
                                                       ('clickable', 'false'), ('sensitive', 'false')]))

    # slide_view_view spans the window down to the times row so the controls it parents (more, fav, times, dots) stay
    # inside it; later siblings (btn_return, slider, buttons) sit on top for touch
    move(svv, 0, 0, W, SVV_H)
    sv.set('self_layout', f'default(x=0,y=0,w=100%,h={SLIDE_H})'); move(sv, 0, 0, W, SLIDE_H)

    # ---- the grabber is Back; the index, the Hi-Res tag and the album line are not on the art page
    ret = find(root, 'btn_return'); move(ret, *RETURN); img_button(ret, 'np_grabber', 'np_grabber_down')
    hide(find(root, 'label_index')); hide(find(root, 'img_hr'))
    fav = find(root, 'btn_fav'); move(fav, FAV_X, BTN_Y, BTN, BTN); fav.set('style:pressed:icon', 'np_unfav_down')
    more = find(root, 'btn_more'); move(more, MORE_X, BTN_Y, BTN, BTN); img_button(more, 'np_more', 'np_more_down')

    # ---- page 1: cover, mask, title and artist under it
    cover = find(root, 'img_playcover'); move(cover, ART_X, ART_Y, ART, ART)
    title, artist = find(root, 'scrlabel_title'), find(root, 'scrlabel_artist')
    for w in (title, artist): parent_of(root, w).children.remove(w)
    move(title, M, TITLE_Y, TEXT_W, TITLE_H); text_style(title, TITLE_PX, TITLE_RGB, 'left')
    move(artist, M, ARTIST_Y, TEXT_W, ARTIST_H); text_style(artist, META_PX, GREY, 'left')
    page1.children += [title, artist]
    # the cover's shadow: right over the cover (its hole is the art), under the title and artist; a child of page 1, so it slides away with the art
    shadow = awtk_ui.Widget('image', ART_X - SHADOW_PAD, ART_Y - SHADOW_PAD, SHADOW_SIZE, SHADOW_SIZE, [('name', 'img_np_shadow'), ('image', 'np_shadow'),
                            ('draw_type', 'default'), ('clickable', 'false'), ('sensitive', 'false')])
    assert cover in page1.children, 'the cover is not on page 1'
    page1.children.insert(page1.children.index(cover) + 1, shadow)

    # ---- page 2: lyrics (below the grabber, above the dots); page 3: info (album, genre, year, size, location)
    lrc = find(root, 'view_lrc'); move(lrc, M, LYR_Y, W - 2 * M, LYR_H)
    # our own lyrics (patch/lyrics.c, docs/modules/lyrics.md): a scroll_view (it clips its children) on the stock list's rectangle, empty in the asset, sensitive (it takes the touches: patch/lyrics.c listeners; neither axis slidable, so it never scrolls itself); the
    # payload fills it with a pool of labels and hides view_lrc. Without the payload the stock list shows and this box is empty.
    assert lrc in lyr.children and root.find('np_lyrics') is None
    lyr.children.insert(lyr.children.index(lrc) + 1, awtk_ui.Widget('scroll_view', M, LYR_Y, W - 2 * M, LYR_H, [('name', 'np_lyrics'), ('floating', 'false')]))
    msg = find(root, 'label_lyricmsg'); move(msg, 0, LYR_Y + (LYR_H - 28) // 2, W, 28); text_style(msg, META_PX, GREY, 'center')
    mqa = find(root, 'img_mqa'); move(mqa, mqa.x, 22, mqa.w, mqa.h)
    y = 52
    li = find(root, 'label_info'); move(li, 8, y, W - 16, 24); text_style(li, META_PX, FG, 'center'); y += 32
    # the formatted quality line (patch/nowplaying.c np_quality): stock rewrites label_info on every tick, so the payload shows this label instead and hides label_info
    nq = awtk_ui.Widget('label', 8, li.y, W - 16, 24, [('name', 'np_quality'), ('visible', 'false'), ('sensitive', 'false')])
    text_style(nq, META_PX, FG, 'center'); li.set('sensitive', 'false')
    lp = parent_of(root, li); lp.children.insert(lp.children.index(li) + 1, nq)
    for n in ('label_album', 'label_genre', 'label_year', 'label_size'):
        w = find(root, n); move(w, 24, y, W - 48, 24); text_style(w, META_PX, GREY, 'center'); y += 30
    loc = find(root, 'label_location'); move(loc, 24, y + 4, W - 48, LYR_Y + LYR_H - y - 4); text_style(loc, 16, GREY, 'center')
    album = find(root, 'label_album')

    # ---- progress bar, times, page dots
    sl = find(root, 'slider_play'); move(sl, *SLIDER); sl.set('bar_size', str(BAR))
    each(sl, BTN_STATES, 'bg_color', TRACK); each(sl, BTN_STATES, 'fg_color', FILL)
    each(sl, BTN_STATES, 'round_radius', str(BAR // 2 + 1))   # the slider paint reads it for both bars; if this build ignores it the bar is square (device)
    each(sl, BTN_STATES, 'icon', '')                          # no thumb (drag works anywhere on the bar)
    pt, pl = find(root, 'label_playtime'), find(root, 'label_playlen')
    move(pt, M, TIMES_Y, TIMES_W, TIMES_H); text_style(pt, TIMES_PX, GREY, 'left')
    move(pl, W - M - TIMES_W, TIMES_Y, TIMES_W, TIMES_H); text_style(pl, TIMES_PX, GREY, 'right')
    rem = awtk_ui.Widget('label', pl.x, pl.y, pl.w, pl.h, [('name', 'np_remaining'), ('visible', 'false')])
    text_style(rem, TIMES_PX, GREY, 'right')
    el = awtk_ui.Widget('label', pt.x, pt.y, pt.w, pt.h, [('name', 'np_elapsed'), ('visible', 'false')])
    text_style(el, TIMES_PX, GREY, 'left')
    svv.children += [rem, el]
    for w in (pt, pl, rem, el): w.set('sensitive', 'false')   # decoration; patch/nowplaying.c swaps the stock times and ours
    dots = find(root, 'slide_indicator'); move(dots, *DOTS)
    dots.set('size', str(DOTS[3])); dots.set('spacing', '10')
    dots.set('style:normal:selected_fg_color', DOT_ON); dots.set('style:normal:fg_color', DOT_OFF)

    # ---- transport row
    vb = find(root, 'view_buttons'); move(vb, 0, ROW_Y, W, ROW_H)
    for n, (x, w) in SLOTS.items():
        b = find(root, n); b.set('self_layout', f'default(x={x},y=0,w={w},h=100%)'); move(b, x, 0, w, ROW_H)
    img_button(find(root, 'btn_prev'), 'np_prev', 'np_prev_down')
    img_button(find(root, 'btn_next'), 'np_next', 'np_next_down')
    img_button(find(root, 'btn_queue'), 'np_playqueue', 'np_playqueue_down')
    wait = find(root, 'image_wait'); x, w = SLOTS['btn_play']; move(wait, x + (w - 50) // 2, (ROW_H - 50) // 2, 50, 50)
    # decorative widgets on top of controls: this AWTK hit-tests hidden widgets too, so they must not take
    # touches (stock: the spinner covers the play button's centre, the A-B markers lie over the slider)
    for n in ('image_wait', 'img_repeata', 'img_repeatb'): find(root, n).set('sensitive', 'false')
    for n in ('img_repeata', 'img_repeatb'): w = find(root, n); move(w, SLIDER[0], SLIDER[1] + SLIDER[3] // 2 + 7, w.w, w.h)

    after = [w.name for w in root.walk() if w.name]
    assert sorted(set(names)) == sorted(set(after) - {'img_np_tint', 'np_remaining', 'np_elapsed', 'np_quality', 'img_np_scrim_lyrics', 'img_np_scrim_info', 'img_np_shadow', 'np_lyrics'}), 'a widget name was lost'
    assert album in info.children
    return root

# ---------------------------------------------------------------------------------------------- the A-B markers (demo)

def marker_edits():
    """address -> (stock word, new word)."""
    bar_centre = SLIDER[1] + SLIDER[3] // 2
    new = {MARKER_X_SCALE: (MARKER_WORDS[MARKER_X_SCALE] & 0xffff0000) | SLIDER[2],
           MARKER_X_OFFSET: (MARKER_WORDS[MARKER_X_OFFSET] & 0xffff0000) | SLIDER[0],
           **{a: (MARKER_WORDS[a] & 0xffff0000) | (bar_centre + 7) for a in MARKER_Y}}
    return {a: (MARKER_WORDS[a], w) for a, w in new.items()}

def patch_markers(out):
    from mod_lockscreen import va_to_off
    path = os.path.join(out, DEMO); b = bytearray(open(path, 'rb').read())
    for va, want in {**MARKER_PINS, **MARKER_WORDS}.items():
        got = struct.unpack_from('<I', b, va_to_off(b, va))[0]
        if got != want: raise SystemExit(f'{DEMO}: {va:#x} = {got:#010x}, expected the stock {want:#010x} (A-B marker code)')
    for va, (_, new) in marker_edits().items():
        assert new & 0xffff0000 == MARKER_WORDS[va] & 0xffff0000 and 0 < new & 0xffff < 0x8000
        struct.pack_into('<I', b, va_to_off(b, va), new)
    write_keep_mode(path, bytes(b))

# ---------------------------------------------------------------------------------------------- touch check

# view_dlna (full-size, last child) is shown/hidden *and* enabled/disabled by playing_choiceshowpage; in local
# playback it is disabled, so the model leaves it out as the device does.
RUNTIME_DISABLED = {'view_dlna'}
PROBES = ['btn_return', 'btn_more', 'btn_fav', 'slider_play', *SLOTS]

def _rect(w, parent_rect, dx=0):
    px, py, pw, ph = parent_rect
    sl = w.get('self_layout', '')
    ww = pw if 'w=100%' in sl else w.w
    hh = ph if 'h=100%' in sl else w.h
    return (px + w.x + dx, py + w.y, ww, hh)

def hit(w, rect, x, y):
    """demo's widget_find_target_default (docs/architecture.md): children from the top, the first with enable and
    sensitive set that contains the point; `visible` is not looked at."""
    for i, c in reversed(list(enumerate(w.children))):
        if c.get('sensitive') == 'false' or c.get('enable') == 'false' or c.name in RUNTIME_DISABLED: continue
        r = _rect(c, rect, i * rect[2] if w.type == 'slide_view' else 0)      # slide_view: page i at x = i * width
        if r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]:
            return hit(c, r, x, y)
    return w

def check_touch(root):
    """Every control's centre must reach that control; the cover and the title rows must reach the slide_view (swipe)."""
    rects = {}
    def collect(w, rect):
        for i, c in enumerate(w.children):
            r = _rect(c, rect, i * rect[2] if w.type == 'slide_view' else 0); rects[c.name] = r; collect(c, r)
    collect(root, (0, 0, W, H))
    sv = find(root, 'slide_view')
    def inside(t, anc): return t is anc or any(inside(t, c) for c in anc.children)
    for n in PROBES:
        x, y, w, h = rects[n]; t = hit(root, (0, 0, W, H), x + w // 2, y + h // 2)
        assert inside(t, find(root, n)), f'touch at the centre of {n} lands on {t.name or t.type}'
        assert w >= 44 and h >= 30 and (n == 'slider_play' or h >= 44), f'{n}: touch target {w}x{h} too small'
    for n in ('img_hr', 'label_index'):
        hr = find(root, n); assert hr.w == 0 and hr.h == 0 and hr.get('sensitive') == 'false' and hr.get('visible') == 'false', f'{n} must stay out of the way'
    for x, y in ((W // 2, ART_Y + ART // 2), (ART_X + 8, ART_Y + ART - 8), (M + 20, TITLE_Y + TITLE_H // 2), (M + 20, ARTIST_Y + ARTIST_H // 2)):
        t = hit(root, (0, 0, W, H), x, y)
        assert inside(t, sv), f'touch at ({x},{y}) on the cover page lands on {t.name or t.type}, not the slide_view'
    # the decoration never takes a touch
    for n in ('img_np_tint', 'img_np_scrim_lyrics', 'img_np_scrim_info', 'img_np_shadow', 'np_remaining', 'np_elapsed', 'np_quality', 'label_info', 'label_playtime', 'label_playlen', 'img_repeata', 'img_repeatb', 'image_wait'):
        assert find(root, n).get('sensitive') == 'false', f'{n} must be insensitive'
    return [(n, rects[n]) for n in PROBES]

# ---------------------------------------------------------------------------------------------- page theme

ICONS = {'btn_imgrandom_style': 'np_random', 'btn_imgcycle_style': 'np_cycle', 'btn_imgcycle1_style': 'np_cycle1',
         'btn_imgorder_style': 'np_order', 'btn_imgfav_style': 'np_fav', 'btn_imgunfav_style': 'np_unfav'}
# The page theme's styles btn_imgsave_style / btn_imgunsave_style are the fav / unfav ones with the bookmark icons (patch/nowplaying.c np_fav_sync swaps them in while an episode plays, and the widget's
# own pressed icon, stock's inline style:pressed:icon which the page sets above, to np_unsave_down).
SAVE = {'btn_imgfav_style': ('btn_imgsave_style', 'np_save'), 'btn_imgunfav_style': ('btn_imgunsave_style', 'np_unsave')}
# play/pause: the app swaps btn_play between these default.bin styles; page-local copies win (the window
# theme is searched first) and leave default.bin, and every other page's play button, untouched.
PLAY = {'btn_imgplay_style': ('np_play', 'np_play_down'), 'btn_imgpause_style': ('np_pause', 'np_pause_down')}

def apply_style(th):
    for name, icon in ICONS.items():
        ss = th.find('button', name); assert len(ss) == 5, name
        for s in ss: s.set('icon', icon)
    for name, (new, icon) in SAVE.items():
        assert not th.find(style=new), f'{new} already in the page theme'
        for t in th.find('button', name):
            s = awtk_style.Item('button', new, t.state, list(t.props))
            s.set('icon', icon); th.items.append(s)
    template = th.find('button', 'btn_imgrandom_style')
    for name, (icon, down) in PLAY.items():
        assert not th.find(style=name), f'{name} already in the page theme'
        for t in template:
            s = awtk_style.Item('button', name, t.state, list(t.props))
            s.set('icon', down if t.state == 'pressed' else icon); th.items.append(s)
    # lyrics: other lines quiet grey, the current one off-white (stock: white / orange #FE7E40)
    for name, rgb in (('listitem_lyric_style', LYR_DIM), ('listitem_sellyric_style', FG)):
        assert not th.find(style=name)
        for st in BTN_STATES:
            s = awtk_style.Item('list_item', name, st)
            s.set('text_align_h', 1, awtk_style.T_INT32)       # as default.bin (centre)
            s.set_color('bg_color', '#00000000'); s.set_color('border_color', '#00000000')
            s.set('font_size', 18); s.set_color('text_color', rgb); th.items.append(s)
    # our lyrics page's labels (patch/lyrics.c np_lyric_style, bold face / np_lyric_cjk_style, default font): white, as label styles (a style is found by widget type and name)
    for name, face in LYRIC_LABEL_STYLES.items():
        assert not th.find(style=name)
        for st in BTN_STATES:
            s = awtk_style.Item('label', name, st)
            s.set('text_align_h', LYR_LEFT, awtk_style.T_INT32)       # left, the Apple Music lyrics look (the hidden stock list_item styles stay centred)
            s.set_color('bg_color', '#00000000'); s.set_color('border_color', '#00000000')
            s.set('font_size', LYR_FONT); s.set('spacer', LYR_SPACER, awtk_style.T_INT32); s.set_color('text_color', LYR_WHITE)
            if face: s.set('font_name', face)
            th.items.append(s)
    return th

def edit_style(path):
    old = open(path, 'rb').read()
    th = awtk_style.parse(old)
    assert awtk_style.serialize(th) == old, f'{path}: style round trip is not byte-exact'
    new = awtk_style.serialize(apply_style(th))
    write_keep_mode(path, new)
    return old, new

# ---------------------------------------------------------------------------------------------- main

def main():
    if len(sys.argv) != 3: sys.exit(__doc__)
    src, out = sys.argv[1:]
    import mod_lockscreen
    assert ART == mod_lockscreen.COVER_SIZE, 'the art is drawn 1:1 only if it is the size demo writes the cover at'
    clone_workdir(src, out)
    xx = os.path.join(out, IMAGES)
    clash = [n for n in added_rels() if os.path.exists(os.path.join(out, 'rootfs', n))]
    assert not clash, f'np_* images already present (tree already modded?): {clash}'
    old, new, root = edit_ui(os.path.join(out, UI), lambda r: check_touch(apply_ui(r)))
    sold, snew = edit_style(os.path.join(out, STYLE))
    imgs = write_images(xx)
    patch_markers(out)
    size = sum(os.path.getsize(os.path.join(xx, n + '.png')) for n in imgs)
    print(f'nowplaying: {UI} {len(old)} -> {len(new)} bytes; {STYLE} {len(sold)} -> {len(snew)} bytes; '
          f'{len(imgs)} images added ({size} bytes); {DEMO}: A-B markers x {SLIDER[0]} + pos * {SLIDER[2]} / len, y '
          f'{SLIDER[1] + SLIDER[3] // 2 + 7} ({len(marker_edits())} immediates)')

if __name__ == '__main__': main()

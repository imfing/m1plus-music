#!/usr/bin/env python3
"""One battery design for the status bar and the lock screen (docs/modules/battery.md).

The app swaps one image between three states and feeds a progress bar the level, drawn UNDER the
image (stock child order). The battery reads as one solid grey body with the level in white (iOS-like):
the progress bar draws the level in white over the body's interior (`fill`, inset 1 px; the grey under it
is a view of its own, tools/statusbar.py battery_parts), and the image is only the 1 px rim that rounds the
body's corners, and the nub:

  normal    EMPTY grey rim and nub
  charging  the normal picture; patch/battery.c shows the level in green #34C759 (CHARGE) and a bolt over the body (below)
  low       red #FF3B30 rim and nub + a red sliver at the level's left end (the app's low icon, capacity 0)

The image has no pixel outside the body and the nub, so it sits on any background (the lock screen's wallpaper).

  STATUS  28 x 14 canvas, body 26 x 14 (radius 4), nub 1.6 x 5,
          fill (pgbar_battery) 24 x 12 at (1, 1)   bar_power/charge/lowpower
          the lock screen's screens_battery/charge/lowbattery are the same three pictures (tools/mod_lockscreen.py)

The charging bolts are images of their own over the picture (tools/statusbar.py battery_parts, hidden until patch/battery.c shows one):
  BOLT_MID    white with a dark edge, 8 x 12 in the body's middle: charging without the Battery Percentage
  BOLT_SMALL  white like the digits beside it (patch/battery.c turns them white while charging), 5 x 9 at the interior's right end: charging with the number left of it (PCT_W_CHG)

Output is a plain zlib RGBA PNG (the bytes do not depend on an image library's version; supersampling is integer box
reduction). Used by mod_battery.py and mod_lockscreen.py.
"""
import struct, zlib

EMPTY = '#5A5A5A'                  # the body under the level (tools/status_art.py DIM)
EMPTY_PCT = '#8E8E93'              # the same while the percentage shows in it: light enough for the black digits
WHITE, GREY, CHARGE, LOW = (255, 255, 255), (0x5A, 0x5A, 0x5A), (0x34, 0xC7, 0x59), (0xFF, 0x3B, 0x30)
BOLT_EDGE, BOLT_EDGE_PX = (0x0B, 0x3A, 0x18), 0.75   # the dark edge round the middle bolt
SS = 8
SLIVER = 3                         # the low picture's red level, px

class Spec:
    def __init__(self, canvas, body, nub, radius, fill):
        self.canvas, self.body, self.nub, self.radius, self.fill = canvas, body, nub, radius, fill

STATUS = Spec((28, 14), (0, 0, 26, 14), (26.4, 4.5, 1.6, 5), 4, (1, 1, 24, 12))
STATES = {'normal': GREY, 'charge': GREY, 'low': LOW}

BOLT = ((0.62, 0.0), (0.0, 0.58), (0.42, 0.58), (0.30, 1.0), (1.0, 0.38), (0.55, 0.38))   # unit box, y down
# the bolts' widgets in the battery image's box (x, y, w, h), and the bolt inside each (x, y, w, h)
BOLT_MID, BOLT_MID_INK = (8, 0, 10, 14), (1, 1, 8, 12)
BOLT_SMALL, BOLT_SMALL_INK = (19, 2, 6, 10), (0, 0.5, 5, 9)
PCT_W_CHG = 21                     # the number's box while the small bolt shows: the body's left 21 px, into the bolt's box, as the digits' ink sits ~1.5 px left of the box's centre: two digits clear the rim by 1 px and the bolt by 2 (patch/battery.h BP_W_CHG)

def mask(spec):
    """-> the rim + nub as an L mask at 1x."""
    from PIL import Image, ImageDraw
    w, h = spec.canvas; s = SS
    S = lambda *v: [round(x * s) for x in v]
    m = Image.new('L', (w * s, h * s), 0); d = ImageDraw.Draw(m)
    bx, by, bw, bh = spec.body
    d.rounded_rectangle(S(bx, by, bx + bw - 1 / s, by + bh - 1 / s), radius=spec.radius * s, fill=255)
    fx, fy, fw, fh = spec.fill
    d.rounded_rectangle(S(fx, fy, fx + fw - 1 / s, fy + fh - 1 / s), radius=(spec.radius - 1) * s, fill=0)   # the progress bar shows
    # through; the rim covers the bar's square corners, so the level's ends are rounded too
    nx, ny, nw, nh = spec.nub
    d.rounded_rectangle(S(nx, ny, nx + nw - 1 / s, ny + nh - 1 / s), radius=nw / 2 * s, fill=255)
    d.rectangle(S(nx, ny, nx + nw / 2, ny + nh - 1 / s), fill=255)         # square on the body's side
    return m.reduce(s)

def render(spec, state):
    from PIL import Image
    rgb = STATES[state]
    w, h = spec.canvas
    im = Image.new('RGBA', (w, h), rgb + (0,)); im.putalpha(mask(spec))
    if state == 'low':
        fx, fy, fw, fh = spec.fill
        from PIL import ImageDraw
        m = Image.new('L', (w * SS, h * SS), 0)          # the fill's rounded shape, its left SLIVER px
        ImageDraw.Draw(m).rounded_rectangle((fx * SS, fy * SS, (fx + fw) * SS - 1, (fy + fh) * SS - 1), radius=(spec.radius - 1) * SS, fill=255)
        ImageDraw.Draw(m).rectangle(((fx + SLIVER) * SS, 0, w * SS, h * SS), fill=0)
        s = Image.new('RGBA', (w, h), rgb + (255,)); s.putalpha(m.reduce(SS)); im.alpha_composite(s)
    return im

def bolt(small):
    """The charging bolt's image: BOLT_SMALL (white) or BOLT_MID (white, dark edge), on a transparent canvas of its widget's size."""
    from PIL import Image, ImageDraw, ImageFilter
    (_, _, w, h), (ox, oy, ow, oh) = (BOLT_SMALL, BOLT_SMALL_INK) if small else (BOLT_MID, BOLT_MID_INK)
    core = Image.new('L', (w * SS, h * SS), 0)
    ImageDraw.Draw(core).polygon([(round((ox + u * ow) * SS), round((oy + v * oh) * SS)) for u, v in BOLT], fill=255)
    layers = [(WHITE, core)] if small else [(BOLT_EDGE, core.filter(ImageFilter.MaxFilter(2 * round(BOLT_EDGE_PX * SS) + 1))), (WHITE, core)]
    im = Image.new('RGBA', (w, h), layers[0][0] + (0,))
    for c, a in layers:
        g = Image.new('RGBA', (w, h), c + (255,)); g.putalpha(a.reduce(SS)); im.alpha_composite(g)
    return im

def png(spec, state):
    im = render(spec, state); w, h = im.size
    raw = b''.join(b'\0' + im.crop((0, y, w, y + 1)).tobytes() for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))

"""The mini player pill as the payload draws it, shared by the Home bar preview (tools/preview.py minibar_page) and the lock screen's mini layout
(tools/preview_lockscreen.py): the backdrop blur (the bit-exact model tools/pod_blur.py) of what is under the pill, the translucent glass image, the 36 px cover with
rounded corners, title and artist cut to their boxes, the white play / pause and next glyphs. tools/pod_ui.py's numbers (patch/offsets.inc MB_*). Approximate, not AWTK.
"""
import os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_ui as U, pod_blur


def rounded_cover(art):
    """art (MB_ART px RGBA) with its MB_ART_R px corners rounded (drawn 4x and reduced)."""
    k = 4
    mask = Image.new('L', (U.MB_ART * k, U.MB_ART * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, U.MB_ART * k - 1, U.MB_ART * k - 1), radius=U.MB_ART_R * k, fill=255)
    art = art.copy()
    art.putalpha(mask.resize((U.MB_ART, U.MB_ART), Image.LANCZOS))
    return art


def blur_under(im, ox, oy):
    """The backdrop blur on the RGB565 pixels under the pill at (ox, oy) in im (RGBA, opaque there)."""
    px = im.convert('RGB').load()
    def get(x, y):
        r, g, b = px[ox + x, oy + y]
        return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
    for (x, y), v in pod_blur.blur(get).items():
        r, g, b = v >> 11, v >> 5 & 63, v & 31
        im.putpixel((ox + x, oy + y), (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2, 255))


def draw(im, ox, oy, img, text, clip, title, artist, art, playing=True, blur=True):
    """The pill at (ox, oy) of im. img(name) -> RGBA of an asset image; text(im, x, centre_y, string, px, rgb or None) draws a left-aligned line; clip(string, px, width) -> the
    string cut to the box; art: the cover (MB_ART px RGBA, not yet rounded)."""
    if blur: blur_under(im, ox, oy)
    im.alpha_composite(img('mb_glass'), (ox, oy))
    im.alpha_composite(rounded_cover(art), (ox + U.MB_ART_X, oy + U.MB_ART_Y))
    x = ox + U.MB_TEXT_X
    text(im, x, oy + U.MB_TITLE_Y + U.MB_TITLE_H / 2, clip(title, U.MB_TITLE_PX, U.MB_TEXT_W), U.MB_TITLE_PX, None)
    text(im, x, oy + U.MB_ARTIST_Y + U.MB_ARTIST_H / 2, clip(artist, U.MB_ARTIST_PX, U.MB_TEXT_W), U.MB_ARTIST_PX, tuple(int(U.MB_ARTIST_RGB[i:i + 2], 16) for i in (1, 3, 5)))
    for name, bx in (('mb_pause' if playing else 'mb_play', U.MB_PLAY_X), ('mb_next', U.MB_NEXT_X)):
        g = img(name)
        im.alpha_composite(g, (ox + bx + (U.MB_BTN_W - g.width) // 2, oy + (U.MB_H - g.height) // 2))

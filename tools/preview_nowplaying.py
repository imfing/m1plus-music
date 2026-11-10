#!/usr/bin/env python3
"""Approximate PIL mock-up of the Now Playing page (ui/playing_page.bin + its page theme); not pixel-exact AWTK.

  preview_nowplaying.py OUT.png LABEL=RAW_DIR[,page=N][,cover=FILE][,tint=RRGGBB][,playing] ...

RAW_DIR is a tree's rootfs/release/assets/default/raw. Each panel draws a 30 px status bar and the 450 px
window under it. Styles resolve as on the device: inline style:<state>:<prop>, then the window theme
(styles/playing_page.bin), then styles/default.bin. Text is laid out as demo's AWTK does it
(awtk_text.StbText: font_size = ascender - descender, advances truncated, +1 px after every glyph,
hscroll_label text from margin_left 2 and clipped to its margins); the glyphs themselves are PIL's. App-filled
values (title, times, cover...) are sample data. The cover is a synthetic gradient, or cover=FILE (drawn at the
widget's size, and its box average gives the window colour through mod_nowplaying.tone, as patch/nowplaying.c
does); tint=RRGGBB is a cover's average colour given directly. page=N shows slide page N (0 cover, 1 lyrics,
2 info). The remaining time label is shown in place of the total, as with the hook running.
"""
import argparse, os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui, awtk_style
from awtk_text import Ttf, StbText
from mod_nowplaying import tone, tint_alpha, corner_alpha, ART_R, BG

HSCROLL_MARGIN = 2
W, BAR, H = 320, 30, 450
SAMPLE = {'scrlabel_title': 'Money', 'scrlabel_artist': 'Pink Floyd', 'label_album': 'Album: The Dark Side of the Moon',
          'label_index': '5/10', 'np_elapsed': '1:23', 'np_remaining': '-4:59',
          # the info page's lines as patch/nowplaying.c np_info leaves them (stock writes "Album:...", "Genres:...", "Era:...",
          # "File Size:48.92MB", "FLAC|44.1kHz|16bit|1021kbps")
          'np_quality': 'FLAC | 44.1 kHz | 16-bit | 1021 kbps', 'label_genre': 'Genre: Progressive Rock', 'label_year': 'Year: 1973',
          'label_size': 'File Size: 48.92 MB', 'label_location': 'Location: SD:/Music/Pink Floyd/The Dark Side of the Moon',
          'label_lyricmsg': 'No lyrics'}
PROGRESS = 22    # % played in the mock-up

def color_str(u):
    """uint32 colour -> '#RRGGBB' (opaque) or '#RRGGBBAA'."""
    c = awtk_style.color_to_str(u); return c[:7] if c.endswith('FF') else c

class Theme:
    def __init__(self, raw):
        self.sets = []
        for f in ('playing_page.bin', 'default.bin'):
            p = os.path.join(raw, 'styles', f)
            if os.path.exists(p): self.sets.append(awtk_style.parse(open(p, 'rb').read()).items)
    def get(self, wtype, style, state, prop):
        for st in self.sets:
            for s in st:
                if s.widget == wtype and s.style == style and s.state == state:
                    v = s.get(prop)
                    if v is not None: return color_str(v) if 'color' in prop and isinstance(v, int) else v
                    break      # the first theme that defines the style wins for the whole style (as AWTK)
            else: continue
            break
        return None

class Painter:
    def __init__(self, raw):
        self.raw, self.theme, self.sample = raw, Theme(raw), SAMPLE
        self.font_path = os.path.join(raw, 'fonts', 'default.ttf')
        a, d = ImageFont.truetype(self.font_path, 1000).getmetrics()
        self.k = 1000 / (a + d); self.fonts = {}
        self.ttf, self.stbs = Ttf(self.font_path), {}
    def font(self, px):
        if px not in self.fonts: self.fonts[px] = ImageFont.truetype(self.font_path, px * self.k)
        return self.fonts[px]
    def stb(self, px):
        if px not in self.stbs: self.stbs[px] = StbText(self.ttf, px)
        return self.stbs[px]
    playing = False      # the play button shows the pause glyph (the app swaps btn_imgplay_style / btn_imgpause_style)
    def image(self, name):
        if not name: return None
        if self.playing: name = {'np_play': 'np_pause', 'np_play_down': 'np_pause_down'}.get(name, name)
        p = os.path.join(self.raw, 'images', 'xx', name + '.png')
        return Image.open(p).convert('RGBA') if os.path.exists(p) else None
    def prop(self, wd, prop, state='normal'):
        v = wd.get(f'style:{state}:{prop}')
        if v is None: v = self.theme.get(wd.type, wd.get('style', 'default'), state, prop)
        return v
    def text(self, layer, r, s, wd):
        px = int(self.prop(wd, 'font_size') or 18)
        rgb = self.prop(wd, 'text_color') or '#444444'
        ah = self.prop(wd, 'text_align_h'); av = self.prop(wd, 'text_align_v') or 'middle'
        # AWTK align_h_t: 1 centre, 2 left, 3 right (canvas_draw_text_in_rect); other values centre
        ah = {0: 'center', 1: 'center', 2: 'left', 3: 'right', None: 'center' if wd.type == 'label' else 'left'}.get(ah, ah)
        f, st = self.font(px), self.stb(px)
        adv = lambda t: st.layout(t)[1]          # AWTK: advances truncated, +1 px after every glyph
        full = r
        if wd.type == 'hscroll_label':           # text from margin_left, clipped to the margins (default 2)
            ml, mr = (HSCROLL_MARGIN if v is None else int(v) for v in (self.prop(wd, k) for k in ('margin_left', 'margin_right')))
            r = (r[0] + ml, r[1], r[2] - ml - mr, r[3])
            out, layer = layer, Image.new('RGBA', layer.size)
        tw = adv(s)
        if tw > r[2] and wd.get('ellipses') == 'true' and wd.get('name') != 'label_album':
            while s and adv(s + '...') > r[2]: s = s[:-1]
            s += '...'; tw = adv(s)
        if wd.get('line_wrap') == 'true' and tw > r[2]:      # crude wrap for the location line
            lines, cur = [], ''
            for ch in s:
                if adv(cur + ch) > r[2]: lines.append(cur); cur = ''
                cur += ch
            lines.append(cur)
        else: lines = [s]
        top = r[1] if av == 'top' else r[1] + (r[3] - px) // 2
        d = ImageDraw.Draw(layer)
        for i, ln in enumerate(lines):
            lw = adv(ln)
            x = r[0] if ah == 'left' or tw > r[2] and len(lines) == 1 else r[0] + r[2] - lw if ah == 'right' else r[0] + (r[2] - lw) // 2
            for ch, pen in st.layout(ln)[0]:
                d.text((x + pen, top + i * (px + 4) + f.getmetrics()[0]), ch, font=f, fill=rgb, anchor='ls')
        if full is not r:
            box = (max(0, r[0]), max(0, r[1]), min(layer.width, r[0] + r[2]), min(layer.height, r[1] + r[3]))
            if box[0] < box[2] and box[1] < box[3]: out.alpha_composite(layer.crop(box), box[:2])
    cover_img = None      # a PIL image drawn as the cover (cover=FILE), else the synthetic one
    tint = None           # the window colour of the cover; None: the asset's neutral tone

    def cover(self, w, h):
        if self.cover_img: return self.cover_img.convert('RGBA').resize((w, h), Image.LANCZOS)
        im = Image.new('RGBA', (w, h)); d = ImageDraw.Draw(im)
        for y in range(h): d.line([(0, y), (w, y)], fill=(20 + y * 60 // h, 30 + y * 20 // h, 70 + y * 90 // h))
        d.ellipse([w * .18, h * .2, w * .82, h * .84], outline=(240, 200, 120), width=max(2, w // 60))
        d.polygon([(w * .5, h * .3), (w * .72, h * .7), (w * .28, h * .7)], fill=(250, 250, 245))
        return im
    def corners(self, layer, r):
        """patch/nowplaying.c np_on_art_paint: the four corners in the colour the window has there (tone under the gradient)."""
        rgb = self.tint or tuple(int(BG[k:k + 2], 16) for k in (1, 3, 5)); cov = corner_alpha()
        if self.tint is None and self.cover_img: rgb = tone(*self.cover_img.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0)))
        px = layer.load()
        for k in range(4):
            for y in range(ART_R):
                ly = r[3] - 1 - y if k & 2 else y; keep = 255 - tint_alpha(r[1] + ly)
                for x in range(ART_R):
                    a = cov[y * ART_R + x]
                    if not a: continue
                    X, Y = r[0] + (r[2] - 1 - x if k & 1 else x), r[1] + ly
                    base = px[X, Y]
                    px[X, Y] = tuple((base[i] * (255 - a) + c * keep // 255 * a) // 255 for i, c in enumerate(rgb)) + (255,)

    def render(self, root, page):
        im = Image.new('RGBA', (W, BAR + H), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
        f = self.font(16); d.text((W // 2, 21), '9:41', font=f, fill='#FFFFFF', anchor='ms')
        d.text((W - 30, 21), '86%', font=self.font(15), fill='#FFFFFF', anchor='rs')
        d.rectangle([W - 24, 10, W - 11, 22], outline='#FFFFFF')
        rgb = self.tint
        if rgb is None and self.cover_img:       # patch/nowplaying.c: the box average of the file, toned
            rgb = tone(*self.cover_img.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0)))
        win = Image.new('RGBA', (W, H), ('#%02X%02X%02X' % tuple(rgb)) if rgb else root.get('style:normal:bg_color', BG))
        self.walk(win, root, 0, 0, (0, 0, W, H), page, root)
        im.alpha_composite(win, (0, BAR))
        return im
    def walk(self, im, wd, ox, oy, clip, page, root):
        if wd.name in ('np_remaining', 'np_elapsed', 'np_quality'): pass       # the hook shows them and hides the stock times / quality line
        elif wd.name in ('label_info',) or wd.name in ('label_playlen', 'label_playtime') or wd.get('visible') == 'false' or wd.get('disg:hide') == 'true': return
        if wd.name in ('image_wait', 'img_repeata', 'img_repeatb'): return       # app-driven, normally hidden
        w, h = wd.w, wd.h
        x, y = wd.x, wd.y
        sl = wd.get('self_layout', '')
        if 'w=100%' in sl: w = None
        if w is None or (wd.type == 'view' and (w, h) == (100, 100)): w, h = clip[2] - clip[0], clip[3] - clip[1]
        r = (ox + x, oy + y, w, h)
        if wd.type == 'gesture' or wd.type == 'window': r = (0, 0, W, H)
        c = (max(clip[0], r[0]), max(clip[1], r[1]), min(clip[2], r[0] + r[2]), min(clip[3], r[1] + r[3]))
        layer = Image.new('RGBA', im.size)
        t, name = wd.type, wd.name
        if t == 'image':
            img = self.cover(r[2], r[3]) if name == 'img_playcover' else self.image(wd.get('image'))
            if img:
                if wd.get('draw_type') == 'scale_auto' or name == 'img_playcover': img = img.resize((r[2], r[3]))
                layer.alpha_composite(img, (r[0] + (r[2] - img.width) // 2, r[1] + (r[3] - img.height) // 2)) if img.size != (r[2], r[3]) else layer.alpha_composite(img, r[:2])
            if name == 'img_playcover': self.corners(layer, r)
        elif t == 'button':
            img = self.image(self.prop(wd, 'icon') or self.prop(wd, 'bg_image'))
            if img: layer.alpha_composite(img, (r[0] + (r[2] - img.width) // 2, r[1] + (r[3] - img.height) // 2))
        elif t in ('label', 'hscroll_label'):
            ec = self.prop(wd, 'border_color')
            if ec: ImageDraw.Draw(layer).rectangle([r[0], r[1], r[0] + r[2] - 1, r[1] + r[3] - 1], outline=ec)
            self.text(layer, r, self.sample.get(name, wd.get('text', '')), wd)
        elif t == 'slider':
            bs = int(wd.get('bar_size', '4')); cy = r[1] + r[3] // 2; d = ImageDraw.Draw(layer)
            fill = r[0] + r[2] * PROGRESS // 100
            d.rounded_rectangle([r[0], cy - bs // 2, r[0] + r[2] - 1, cy - bs // 2 + bs - 1], radius=bs / 2, fill=self.prop(wd, 'bg_color'))
            d.rounded_rectangle([r[0], cy - bs // 2, fill, cy - bs // 2 + bs - 1], radius=bs / 2, fill=self.prop(wd, 'fg_color'))
            dot = self.image(self.prop(wd, 'icon'))
            if dot: layer.alpha_composite(dot, (fill - dot.width // 2, cy - dot.height // 2))
        elif t == 'slide_indicator':
            n = int(wd.get('max', '2')) + 1; sp = int(wd.get('spacing', '15')); d = ImageDraw.Draw(layer)
            dia = int(wd.get('size', '6')); x0 = r[0] + (r[2] - (n - 1) * sp) // 2; cy = r[1] + r[3] // 2
            for i in range(n):
                col = self.prop(wd, 'selected_fg_color') if i == page else self.prop(wd, 'fg_color')
                d.ellipse([x0 + i * sp - dia // 2, cy - dia // 2, x0 + i * sp + (dia + 1) // 2 - 1, cy + (dia + 1) // 2 - 1], fill=col)
        if c[0] < c[2] and c[1] < c[3]: im.alpha_composite(layer.crop(c), c[:2])
        kids = wd.children
        if t == 'slide_view': kids = kids[page:page + 1]
        sub = c if t in ('scroll_view', 'slide_view', 'list_view') else clip    # only these clip children in AWTK
        for ch in kids: self.walk(im, ch, r[0], r[1], sub, page, root)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out'); ap.add_argument('panels', nargs='+')
    a = ap.parse_args()
    shots = []
    for spec in a.panels:
        label, rest = spec.split('=', 1); raw, *opts = rest.split(',')
        page = next((int(o[5:]) for o in opts if o.startswith('page=')), 0)
        root = awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
        p = Painter(raw)
        for o in opts:
            if o.startswith('cover='): p.cover_img = Image.open(o[6:])
            if o == 'playing': p.playing = True
            if o.startswith('tint='): p.tint = tone(*(int(o[5:][k:k + 2], 16) for k in (0, 2, 4)))
        shots.append((label, p.render(root, page)))
    top, pad = 18, 10
    out = Image.new('RGB', (len(shots) * (W + pad) + pad, BAR + H + top + 18), (40, 40, 40)); d = ImageDraw.Draw(out)
    for i, (label, im) in enumerate(shots):
        x = pad + i * (W + pad); out.paste(im.convert('RGB'), (x, top)); d.text((x, 3), label, fill=(220, 220, 220))
    d.text((pad, BAR + H + top + 3), 'approximate PIL mock-up, not AWTK; sample track data, the cover as given', fill=(160, 160, 160))
    out.save(a.out, optimize=True); print('wrote', a.out)

if __name__ == '__main__': main()

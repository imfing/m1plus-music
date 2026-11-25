#!/usr/bin/env python3
"""Approximate PIL mock-up of the Now Playing page (ui/playing_page.bin + its page theme); not pixel-exact AWTK.

  preview_nowplaying.py OUT.png LABEL=RAW_DIR[,page=N][,info=cd|hires|dsd|mp3|long][,out=HZ][,key1=LABEL][,scroll=PX][,full][,cover=FILE][,tint=RRGGBB][,playing][,paused|,art=PX][,skip][,scrub] ...

RAW_DIR is a tree's rootfs/release/assets/default/raw. Each panel draws a 30 px status bar and the 450 px
window under it. Styles resolve as on the device: inline style:<state>:<prop>, then the window theme
(styles/playing_page.bin), then styles/default.bin. Text is laid out as demo's AWTK does it
(awtk_text.StbText: font_size = ascender - descender, advances truncated, +1 px after every glyph,
hscroll_label text from margin_left 2 and clipped to its margins); the glyphs themselves are PIL's. App-filled
values (title, times, cover...) are sample data. The cover is a synthetic gradient, or cover=FILE (drawn at the
widget's size, and its box average gives the window colour through mod_nowplaying.tone, as patch/nowplaying.c
does); tint=RRGGBB is a cover's average colour given directly. page=N shows slide page N (0 cover, 1 lyrics,
2 info; paused draws the cover and its shadow at the paused size, art=PX at any side of the spring; scroll=PX shows the info page's content scrolled by that many px, full draws the whole content as a taller panel; skip draws an episode's page: speed, back 15 s, forward 30 s, the plain queue glyph, no page dots; scrub draws the progress bar as thick as under a finger). The remaining time label is shown in place of the total, as with the hook running.
"""
import argparse, os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import awtk_ui, awtk_style, cdefs
from awtk_text import Ttf, StbText
import mod_nowplaying as MN
from mod_nowplaying import tone, tint_alpha, corner_alpha, ART_R, BG

HSCROLL_MARGIN = 2
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W, BAR, H = 320, 30, 450
SAMPLE = {'scrlabel_title': 'Money', 'scrlabel_artist': 'Pink Floyd', 'label_album': 'Album: The Dark Side of the Moon',
          'label_index': '5/10', 'np_elapsed': '1:23', 'np_remaining': '-4:59',
          # (the information page is drawn by Painter.info_page from INFO)
          'label_lyricmsg': 'No lyrics'}
# The information page's sample tracks (page=2, info=NAME): what stock writes (the quality line, the lines "Label:value") and the record's title, artist, album
INFO = {'cd': dict(title='Money', artist='Pink Floyd', album='The Dark Side of the Moon', quality='FLAC|44.1kHz|16bit|1021kbps', genre='Progressive Rock', year='1973', size='48.92MB',
                   location='SD:/Music/Pink Floyd/The Dark Side of the Moon/05 Money.flac', badge=''),
        'hires': dict(title='Aja', artist='Steely Dan', album='Aja', quality='FLAC|96kHz|24bit|2913kbps', genre='Jazz Rock', year='1977', size='173.40MB', location='SD:/Music/Steely Dan/Aja/02 Aja.flac', badge='HI-RES'),
        'dsd': dict(title='So What', artist='Miles Davis', album='Kind of Blue', quality='DSF|2822.4kHz|1bit|5645kbps', genre='Jazz', year='1959', size='379.12MB', location='SD:/Music/Miles Davis/Kind of Blue/01 So What.dsf', badge='DSD'),
        'mp3': dict(title='Wish You Were Here (2011 Remastered Version)', artist='Pink Floyd', album='Wish You Were Here', quality='MP3|44.1kHz|16bit|320kbps', genre='Rock', year='1975', size='12.80MB',
                    location='SD:/Music/Pink Floyd/Wish You Were Here/04 Wish You Were Here.mp3', badge='')}
INFO['long'] = dict(title='Wish You Were Here (2011 Remastered Version)', artist='Pink Floyd', album='Wish You Were Here', quality='FLAC|96kHz|24bit|2707kbps', genre='Progressive Rock', year='1975',
                    size='173.40MB', location='SD:/Music/Hi-Res/Pink Floyd/Wish You Were Here (2011 Remastered Version)/04 Wish You Were Here.flac', badge='HI-RES')
INFO['episode'] = dict(title='112: Why Old Players Still Sound Great', artist='Night Shift Radio', album='Night Shift Radio', quality='MP3|44.1kHz|16bit|128kbps', genre='Podcast', year='2026', size='49.80MB',
                       location='SD:/Podcasts/Night Shift Radio/nsr-112-old-players.mp3', badge='')
# The episode notes page's samples (page=1 with notes=NAME): the header's three lines and the notes (paragraphs split by newlines; '' shows the hint)
NOTES = {'feed': dict(title='112: Why Old Players Still Sound Great', show='Night Shift Radio', date='Nov 18 · 52m',
                      text='This week we dig out a drawer of portable players from the last twenty years and ask a simple question: why do some of them still sound so good?\n'
                           'We talk about output stages, why a clean volume curve matters more than the spec sheet, and how a small screen can still make a library feel easy to browse.\n'
                           'Plus listener mail: replacing a worn headphone jack, the best way to tag a large collection, and whether gapless playback is worth fighting for.\n'
                           'Chapters: 00:00 Intro · 04:12 The drawer · 21:40 Output stages · 38:05 Listener mail\n'
                           'Thanks for listening. Leave us a review and tell a friend about the show.'),
         'short': dict(title='111: Live from the Workshop', show='Night Shift Radio', date='Nov 11 · 47m',
                       text='A recorded live session from the workshop, with questions from the audience about repairs and batteries.'),
         'local': dict(title='nsr-098-interview', show='Night Shift Radio', date='Jun 2', text='')}
NOTES_HINT = 'No description'
INFO_LABELS = ('label_info', 'label_album', 'label_genre', 'label_year', 'label_size', 'label_location')    # stock's data labels: hidden while the payload's own show
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
    info = INFO['cd']    # the information page's sample track
    scroll, full = 0, False   # the info page's content offset; the whole content (a taller image)
    playing = False      # the play button shows the pause glyph (the app swaps btn_imgplay_style / btn_imgpause_style)
    art = MN.ART         # the cover's side: ART_SMALL while paused (patch/nowplaying.c np_art_place), art=PX any frame of the spring
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
        R = min(ART_R, (ART_R * r[2] + MN.ART // 2) // MN.ART)   # the radius scales with the cover, never more than ART_R
        rgb = self.tint or tuple(int(BG[k:k + 2], 16) for k in (1, 3, 5)); cov = corner_alpha(R)
        if self.tint is None and self.cover_img: rgb = tone(*self.cover_img.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0)))
        px = layer.load()
        for k in range(4):
            for y in range(R):
                ly = r[3] - 1 - y if k & 2 else y; keep = 255 - tint_alpha(r[1] + ly)
                for x in range(R):
                    a = cov[y * R + x]
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
        if page == 2 or page == 1 and self.notes:
            tall = self.notes_page(win) if page == 1 else self.info_page(win)
            if tall: return tall
        im.alpha_composite(win, (0, BAR))
        return im
    def info_page(self, win):
        """The information page as patch/nowplaying.c lays it out (np_header, np_quality, np_row, np_flow), from the shared model (mod_nowplaying qparse / flow / loc_wrap) and the built font. The content is drawn in
        page coordinates on a canvas as tall as it is; the scroll_view shows the 300 px from y 36 + self.scroll, or with self.full the whole content is returned as a taller window image."""
        I = self.info
        adv = lambda t, px: self.stb(px).layout(t)[1] if t else 0
        rows = {r: (getattr(self, 'key1', None) if r == 1 and getattr(self, 'key1', None) else MN.I_KEYS[r], v) for r, v in MN.qparse(I['quality']).items()}
        for r, k, v in ((4, 'Genre', I['genre']), (5, 'Year', I['year']), (6, 'File Size', I['size'].replace('MB', ' MB')), (7, 'Location', I['location'])): rows[r] = (k, v)
        if self.notes: rows.pop(4, None), rows.pop(5, None)      # spoken audio leaves Genre and Year out
        present = [r in rows for r in range(MN.I_ROWS)]
        loc = MN.loc_wrap(I['location'], MN.I_W, lambda t: adv(t, MN.I_ROW_PX)) if present[7] else []
        tl, cut = MN.title_wrap(I['title'], MN.I_TEXT_W, lambda t: adv(t, MN.I_TITLE_PX))
        sh = MN.I_TITLE_LH if len(tl) > 1 else 0
        bare = bool(self.notes)                          # spoken audio: the notes page has the header, so this page has none
        hair, text, locy, bottom = MN.flow(present, len(loc) or 1, sh, bare)
        cv = Image.new('RGBA', (W, max(H, bottom + 12)))
        def put(x, y, t, px, rgb):                       # the text's top at y, left at x
            f = self.font(px); layer = Image.new('RGBA', cv.size); ld = ImageDraw.Draw(layer)
            for ch, pen in self.stb(px).layout(t)[0]: ld.text((x + pen, y + f.getmetrics()[0]), ch, font=f, fill=rgb, anchor='ls')
            cv.alpha_composite(layer)
        def end_fit(t, px, room):
            if adv(t, px) <= room: return t
            while t and adv(t + '...', px) > room: t = t[:-1]
            return t + '...'
        if not bare:
            c = self.cover(MN.I_ART, MN.I_ART); m = Image.new('L', c.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, c.width - 1, c.height - 1], radius=MN.I_ART_R, fill=255)
            cv.paste(c, (MN.I_X, MN.I_ART_Y), m)
            for i, t in enumerate(tl): put(MN.I_TEXT_X, MN.I_TITLE_Y + i * MN.I_TITLE_LH, end_fit(t, MN.I_TITLE_PX, MN.I_TEXT_W) if cut else t, MN.I_TITLE_PX, '#FFFFFF')
            put(MN.I_TEXT_X, MN.I_ARTIST_Y + sh, end_fit(I['artist'], MN.I_META_PX, MN.I_TEXT_W), MN.I_META_PX, MN.GREY)
            put(MN.I_TEXT_X, MN.I_ALBUM_Y + sh, end_fit(I['album'], MN.I_META_PX, MN.I_TEXT_W), MN.I_META_PX, MN.GREY)
        for r, (k, v) in rows.items():
            if r in hair: cv.alpha_composite(Image.new('RGBA', (MN.I_W, 1), MN.HAIR_RGBA), (MN.I_X, hair[r]))
            put(MN.I_X, text[r], k, MN.I_ROW_PX, MN.GREY)
            if r == MN.I_LOC_ROW:
                for line, y in zip(loc, locy): put(MN.I_X, y, line, MN.I_ROW_PX, '#FFFFFF')
                continue
            room = MN.I_W - adv(k, MN.I_ROW_PX) - MN.I_KEY_GAP
            conv = MN.resampled(v, I.get('out', 0)) if r == 1 else None   # a track converted to the kept output's rate
            if conv: v = conv[0] if adv(conv[0], MN.I_ROW_PX) <= room else conv[1]
            v = end_fit(v, MN.I_ROW_PX, room)
            put(MN.I_R - adv(v, MN.I_ROW_PX), text[r], v, MN.I_ROW_PX, '#FFFFFF')
            if r == 0 and I['badge']:
                bw = MN.I_BADGE_W[I['badge']]
                cv.alpha_composite(self.image('np_i_badge_' + ('hires' if I['badge'] == 'HI-RES' else 'dsd')), (MN.badge_x(adv(v, MN.I_ROW_PX), bw), text[0] + (MN.I_ROW_PX - MN.I_BADGE_H) // 2))
        return self.scroll_out(win, cv, bottom)

    notes = None     # an episode's notes page sample (NOTES), drawn in the lyrics page's place
    def notes_page(self, win):
        """The proposed episode notes page (the lyrics page's place while an episode plays): the info page's scrim and header (cover, title up to two lines, show, date · length), one hairline, then the notes
        wrapped by tools/pod_wrap.py (kinsoku, CJK anywhere) in the scroll area; no notes: the hint in grey."""
        import pod_show, pod_wrap
        N = self.notes
        win.alpha_composite(MN.scrim_image().convert('RGBA'), MN.SCRIM[:2])   # (np_scrim.png as the build makes it)
        adv = lambda t, px: self.stb(px).layout(t)[1] if t else 0
        font = pod_show.Font(self.font_path)
        tl, cut = MN.title_wrap(N['title'], MN.I_TEXT_W, lambda t: adv(t, MN.I_TITLE_PX))
        sh = MN.I_TITLE_LH if len(tl) > 1 else 0
        hair, body, bottom = MN.notes_layout(N['text'], lambda par: pod_wrap.wrap_font(font, par, MN.N_PX, MN.I_W, 320), sh)
        if not body: body = [(NOTES_HINT, hair + MN.N_GAP)]      # no text: the hint, one grey line
        cv = Image.new('RGBA', (W, max(H, bottom + 12)))
        def put(x, y, t, px, rgb):
            f = self.font(px); layer = Image.new('RGBA', cv.size); ld = ImageDraw.Draw(layer)
            for ch, pen in self.stb(px).layout(t)[0]: ld.text((x + pen, y + f.getmetrics()[0]), ch, font=f, fill=rgb, anchor='ls')
            cv.alpha_composite(layer)
        fit = lambda t, px, room: MN.end_fit(t, room, lambda s: adv(s, px))
        c = self.cover(MN.I_ART, MN.I_ART); m = Image.new('L', c.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, c.width - 1, c.height - 1], radius=MN.I_ART_R, fill=255)
        cv.paste(c, (MN.I_X, MN.I_ART_Y), m)
        for i, t in enumerate(tl): put(MN.I_TEXT_X, MN.I_TITLE_Y + i * MN.I_TITLE_LH, fit(t, MN.I_TITLE_PX, MN.I_TEXT_W) if cut else t, MN.I_TITLE_PX, '#FFFFFF')
        put(MN.I_TEXT_X, MN.I_ARTIST_Y + sh, fit(N['show'], MN.I_META_PX, MN.I_TEXT_W), MN.I_META_PX, MN.GREY)
        put(MN.I_TEXT_X, MN.I_ALBUM_Y + sh, fit(N['date'], MN.I_META_PX, MN.I_TEXT_W), MN.I_META_PX, MN.GREY)
        cv.alpha_composite(Image.new('RGBA', (MN.I_W, 1), MN.HAIR_RGBA), (MN.I_X, hair))
        for t, ty in body: put(MN.I_X, ty, t, MN.N_PX, MN.N_RGB if N['text'] else MN.GREY)
        return self.scroll_out(win, cv, bottom)

    def scroll_out(self, win, cv, bottom):
        """The content canvas cv (page coordinates, bottom its end) shown through the 300 px scroll area at self.scroll with the edge fades, or with self.full the whole content as a taller window image."""
        if self.full:
            tall = Image.new('RGBA', (W, bottom + 12), win.getpixel((2, 2))); tall.alpha_composite(cv); return tall
        view = cv.crop((0, MN.I_TOP + self.scroll, W, MN.I_BOTTOM + self.scroll))
        tn = self.tint or (tone(*self.cover_img.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0))) if self.cover_img else tuple(int(BG[k:k + 2], 16) for k in (1, 3, 5)))
        ih = max(bottom - MN.I_TOP, MN.I_BOTTOM - MN.I_TOP); off = max(0, min(self.scroll, ih - (MN.I_BOTTOM - MN.I_TOP)))
        for y in MN.fade_rows(off, ih):          # the edge fades: the tone under the scrim and gradient, alpha by the row's distance from the edge
            k = min(y, MN.I_BOTTOM - MN.I_TOP - 1 - y); col = MN.fade_color(tn, y)
            row = Image.new('RGBA', (W, 1), (col & 255, col >> 8 & 255, col >> 16 & 255, MN.fade_alpha(k))); view.alpha_composite(row, (0, y))
        win.alpha_composite(view, (0, MN.I_TOP))

    def walk(self, im, wd, ox, oy, clip, page, root):
        if wd.name in ('np_remaining', 'np_elapsed'): pass       # the hook shows them and hides the stock times / quality line
        elif wd.name in INFO_LABELS or wd.name in ('label_playlen', 'label_playtime') or wd.get('visible') == 'false' or wd.get('disg:hide') == 'true': return
        if wd.name in ('image_wait', 'img_repeata', 'img_repeatb') or self.notes and wd.name == 'view_lyrics': return       # app-driven, normally hidden
        w, h = wd.w, wd.h
        x, y = wd.x, wd.y
        sl = wd.get('self_layout', '')
        if 'w=100%' in sl: w = None
        if w is None or (wd.type == 'view' and (w, h) == (100, 100)): w, h = clip[2] - clip[0], clip[3] - clip[1]
        if wd.name in ('img_playcover', 'img_np_shadow') and self.art != MN.ART:   # the paused cover and its shadow, scaled about the full cover's centre
            pad = MN.SHADOW_PAD * self.art // MN.ART if wd.name == 'img_np_shadow' else 0
            x = y = MN.ART_X + (MN.ART - self.art) // 2 - pad; w = h = self.art + 2 * pad
        r = (ox + x, oy + y, w, h)
        if wd.type == 'gesture' or wd.type == 'window': r = (0, 0, W, H)
        c = (max(clip[0], r[0]), max(clip[1], r[1]), min(clip[2], r[0] + r[2]), min(clip[3], r[1] + r[3]))
        layer = Image.new('RGBA', im.size)
        t, name = wd.type, wd.name
        if t == 'image':
            img = self.cover(r[2], r[3]) if name == 'img_playcover' else self.image(wd.get('image'))
            if img:
                if wd.get('draw_type') in ('scale_auto', 'scale') or name == 'img_playcover': img = img.resize((r[2], r[3]))
                if name == 'img_np_shadow' and MN.shadow_opacity(self.art) < 255:   # the payload's widget opacity (np_art_place)
                    img = img.copy(); img.putalpha(img.getchannel('A').point(lambda a: a * MN.shadow_opacity(self.art) // 255))
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
            if o == 'paused': p.art = MN.ART_SMALL
            if o.startswith('art='): p.art = int(o[4:])
            if o.startswith('info='): p.info = INFO[o[5:]]
            if o.startswith('out='): p.info = dict(p.info, out=int(o[4:]))   # after info=: the rate the output is kept at
            if o.startswith('key1='): p.key1 = o[5:]   # another language's Sample Rate label
            if o.startswith('scroll='): p.scroll = int(o[7:])
            if o.startswith('notes='): p.notes = NOTES[o[6:]]
            if o == 'full': p.full = True
            if o == 'scrub':   # a finger on the progress bar: np_scrub_look's thickness (patch/offsets.inc NP_BAR_SCRUB)
                b = cdefs.defines(os.path.join(ROOT, 'patch', 'offsets.inc'), ['NP_BAR_SCRUB'])['NP_BAR_SCRUB']; root.find('slider_play').set('bar_size', str(b))
            if o == 'skip' or o.startswith('notes='):   # an episode or a book part: the skip glyphs, as np_skip_sync sets them
                for n, g in (('btn_prev', 'np_back15'), ('btn_next', 'np_fwd30'), ('btn_queue', 'np_playlist')): root.find(n).set('style:normal:bg_image', g)
                root.find('btn_playmode').set('style', 'btn_imgspeed0_style')   # the speed button at 1x (np_mode_sync)
                if o == 'skip': root.find('slide_indicator').set('visible', 'false')   # the cover page alone: no page dots (np_pages_sync)
            if o.startswith('tint='): p.tint = tone(*(int(o[5:][k:k + 2], 16) for k in (0, 2, 4)))
        shots.append((label, p.render(root, page)))
    top, pad = 18, 10
    hmax = max(im.height for _, im in shots)
    out = Image.new('RGB', (len(shots) * (W + pad) + pad, hmax + top + 18), (40, 40, 40)); d = ImageDraw.Draw(out)
    for i, (label, im) in enumerate(shots):
        x = pad + i * (W + pad); out.paste(im.convert('RGB'), (x, top)); d.text((x, 3), label, fill=(220, 220, 220))
    d.text((pad, hmax + top + 3), 'approximate PIL mock-up, not AWTK; sample track data, the cover as given', fill=(160, 160, 160))
    out.save(a.out, optimize=True); print('wrote', a.out)

if __name__ == '__main__': main()

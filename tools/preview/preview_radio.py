#!/usr/bin/env python3
"""Approximate PIL mock-up of Radio's stations page (patch/radiopage.c, docs/modules/radio.md) on the Songs / Folders preview model (tools/preview/preview_songs.py, preview_folders.py: the project's
own text model, the built font and glyphs): the root with its Now Playing group, the countries as the Genres page's A-Z list (section letters, the rail), the stations as the Albums
list (the default: 64 px rows, a 52 px logo or grey radio-glyph tile, name, "Country · CODEC 128k") and as the Albums grid, the search results and the genres' rows; the navbar toggle
sits on the 214 slot of the station lists, Search on 168; the directory's credit shows under the root and the search results only.
Not pixel-exact AWTK.

  preview_radio.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release).
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview_icons as PI
import preview_songs as PS
import preview_folders as PF
import pod_ui
import awtk_ui
import pod_search as PSE
import preview_keyboard as PKV
import preview_search as PSV

O, W, WIN, NAV = PS.O, PS.W, PS.WIN, PS.NAV
HAIR, GREY = PS.HAIR, PS.GREY
ROW = pod_ui.ROW_H                                   # 52
TOP, TOP_SEARCH = 60, 48                             # patch/radiopage.c RP_TOP
GAP, CREDIT_GAP = 24, 12
CARD = (0x2C, 0x2C, 0x2E)
COVER, GCOL, GROW, GR, TITLE_GAP, TITLE_H, SUB_H = (O[k] for k in ('GRID_COVER', 'GRID_GAP', 'GRID_ROW_GAP', 'GRID_R', 'GRID_TITLE_GAP', 'GRID_TITLE_H', 'GRID_SUB_H'))
MARGIN = O['GRID_MARGIN']
PITCH = COVER + TITLE_GAP + TITLE_H + SUB_H + GROW
CREDIT = 'Stations from radio-browser.info'

ROOT_ROWS = [('Now Playing', 'pod_ic_nowplaying'), ('My Stations', 'pod_ic_rd_stations'), ('Recently Played', 'pod_ic_recent'), ('Radio Browser', 'pod_ic_rd_browser')]
COUNTRIES = ['Austria', 'Belgium', 'Brazil', 'Canada', 'France', 'The Gambia', 'Germany', 'Greece', 'Italy', 'Japan', 'Spain', 'Sweden', 'The United States Of America']
GENRES = [('pop', 6202), ('rock', 3158), ('news', 2897), ('jazz', 1311)]
STATIONS = [('BBC Radio 3', 'United Kingdom · AAC 128k', True), ('Radio Paradise', 'United States · MP3 128k', False), ('FIP', 'France · MP3 192k', True),
            ('SWR3', 'Germany · MP3 128k', False), ('Triple J', 'Australia · AAC 64k', False), ('Jazz FM', 'United Kingdom · MP3 128k', True)]


def synthetic_logo(i, n=COVER):
    """A stand-in logo: a coloured disc on the white card pv_shrink gives."""
    im = Image.new('RGBA', (n, n), (255, 255, 255, 255)); d = ImageDraw.Draw(im)
    rgb = [(214, 64, 52), (30, 110, 190), (40, 150, 90)][i % 3]
    d.ellipse((n * .16, n * .16, n * .84, n * .84), fill=rgb); d.rectangle((n * .34, n * .44, n * .66, n * .56), fill='white')
    return im


def cover(s, im, x, y, logo):
    """A tile's cover: the logo, or the #2C2C2E card with the radio glyph; the corners cut into black as grid_round does."""
    tile = logo if logo else Image.new('RGBA', (COVER, COVER), CARD + (255,))
    if not logo:
        g = s.img('pod_ic_rd_art'); tile.alpha_composite(g, ((COVER - g.width) // 2, (COVER - g.height) // 2))
    k = 4; mask = Image.new('L', (COVER * k, COVER * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, COVER * k - 1, COVER * k - 1), radius=GR * k, fill=255)
    im.paste(tile, (x, y), mask.resize((COVER, COVER), Image.LANCZOS))


def navbar(s, im, title, search=False, view=None):
    """view: None (no toggle), 'list' or 'grid' (the mode shown; the glyph is the other one). search: the search page (no Search button)."""
    d = ImageDraw.Draw(im); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    PS.glass(s, im, 'ah_nav_back', 7, 44)
    glyph = {'list': 'pod_nav_grid', 'grid': 'pod_nav_list'}.get(view)
    if view == 'more':   # My Stations, Recently Played: [... | Now Playing], the "..." the left cap on the 214 slot (the view is in its card)
        PS.glass(s, im, 'pod_nav_more', 214); PS.glass(s, im, 'ah_nav_play', 260, 60)
    elif search and not view: PS.glass(s, im, 'ah_nav_np', 260, 60)
    elif search:   # [toggle (left cap) | Now Playing]
        PS.glass(s, im, glyph + 'l', 214); PS.glass(s, im, 'ah_nav_play', 260, 60)
    elif view:   # [Search | toggle | Now Playing]
        PS.glass(s, im, 'pod_nav_search', O['NAV_CF_X']); PS.glass(s, im, glyph, 214); PS.glass(s, im, 'ah_nav_play', 260, 60)
    else:   # the capsule: Search | Now Playing
        PS.glass(s, im, 'pod_nav_search', 214); PS.glass(s, im, 'ah_nav_play', 260, 60)


def stations_card(s, recent=False, grid=False):
    """My Stations (or Recently Played) with the "..." card open (patch/radiopage.c rp_card): the list under the scrim's dim, the card as vs_fit lays it out. My Stations: Select, Sort by Name, Add by URL, Import from Card,
    a hairline, Grid, List (the tick on the current view); Recently Played: Grid, List, a hairline, Clear Recently Played (red, last)."""
    im = (grid_page if grid else list_page)(s, 'Recently Played' if recent else 'My Stations')
    navbar(s, im, 'Recently Played' if recent else 'My Stations', False, 'more')
    im.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 0x82)))
    views = [('Grid', 'pod_ic_vsgrid', grid, None), ('List', 'pod_ic_vslist', not grid, None)]
    if recent:
        return PI.view_card(s, im, views + [('Clear History', 'pod_ic_vstrash', False, None, True)], 'vs_glass3', (2,))
    acts = [('Select', 'pod_ic_vsselect', False, None), ('Sort by Name', 'pod_ic_vsorder', False, None), ('Add by URL', 'pod_ic_vslink', False, None), ('Import from Card', 'pod_ic_vsimport', False, None)]
    return PI.view_card(s, im, acts + views, 'vs_glass6', (4,))


def credit(s, im, x, y):
    s.text(im, x, y + 10, PS.tr(s, CREDIT), pod_ui.RD_CREDIT_PX, (0x8E, 0x8E, 0x93))


def new_page(s, title, big=True):
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    if big: s.text(im, O['SG_TITLE_X'], NAV + O['SG_TITLE_H'] / 2, PS.fit(s, PS.tr(s, title), 32, O['SG_TITLE_W']), 32)
    return im


def root_page(s):
    im = new_page(s, 'Radio'); d = ImageDraw.Draw(im)
    for i, (label, icon) in enumerate(ROOT_ROWS):
        y = NAV + TOP + i * ROW + (GAP if i else 0)
        im.alpha_composite(s.img(icon), (16, y + (ROW - 24) // 2))
        PF.chevron(im, 289, y + (ROW - 16) // 2)
        s.text(im, 56, y + ROW / 2, PS.tr(s, label), pod_ui.LIST_TITLE_PX)
        if i != 0: d.rectangle((56, y + ROW - 1, W - 11, y + ROW - 1), fill=HAIR)   # a group of one row ends without a separator
    navbar(s, im, 'Radio')
    return im


def countries_page(s):
    """The Genres page's A-Z list (patch/artists.c numbers): section letters on their own 28 px rows, 52 px rows, name at x 24, chevron at x 262, the rail."""
    im = new_page(s, 'Countries'); d = ImageDraw.Draw(im)
    key = lambda n: n[4:] if n.startswith('The ') else n
    letters, y = [], NAV + O['SG_TITLE_H']
    last = None
    for n in COUNTRIES:
        c = key(n)[0].upper()
        if c != last:
            PS.header(s, im, c, y); letters.append(c); y += O['SG_HDR_H']; last = c
        d.rectangle((24, y + ROW - 1, O['LIST_HAIR_END'] - O['SG_RAIL_INSET'] - 1, y + ROW - 1), fill=HAIR)   # the rail is shown: patch/azlist.c az_inset
        PF.chevron(im, O['LIST_CHEV_X'] - O['SG_RAIL_INSET'], y + (ROW - 16) // 2)
        s.text(im, 24, y + ROW / 2, s.clip(PS.tr(s, n) if False else n, 20, O['LIST_TEXT_X'] + O['LIST_TEXT_W_CHEV'] - O['SG_RAIL_INSET'] - 24), 20)
        y += ROW
    PS.rail(s, im, letters)
    navbar(s, im, 'Countries')
    return im


def list_page(s, title, top=TOP, search=False):
    """The stations as the Albums list: 64 px rows, the 52 px logo at (10, 4) with 4 px corners cut in the alpha, text from x 74, a full-width hairline."""
    im = new_page(s, title, big=not search); d = ImageDraw.Draw(im)
    R, ART, LR = O['LIST_ROW_H'], O['LIST_ART'], O['LIST_R']
    stations = STATIONS[:4] if search else STATIONS   # a short result list, so the credit under it shows
    for i, (name, sub, logo) in enumerate(stations):
        y = NAV + top + i * R
        if y >= WIN: break
        tile = synthetic_logo(i, ART) if logo else Image.new('RGBA', (ART, ART), CARD + (255,))
        if not logo:
            g = s.img('pod_ic_rd_art').resize((ART * 2 // 3, ART * 2 // 3), Image.LANCZOS); tile.alpha_composite(g, ((ART - g.width) // 2, (ART - g.height) // 2))
        k = 4; mask = Image.new('L', (ART * k, ART * k), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, ART * k - 1, ART * k - 1), radius=LR * k, fill=255)
        im.paste(tile, (O['LIST_ART_X'], y + O['LIST_ART_Y']), mask.resize((ART, ART), Image.LANCZOS))
        s.text(im, O['LIST_TEXT_X'], y + O['LIST_TITLE_Y'] + O['LIST_TITLE_H'] / 2, s.clip(name, 20, O['LIST_TEXT_W']), 20)
        s.text(im, O['LIST_TEXT_X'], y + O['LIST_SUB_Y'] + O['LIST_SUB_H'] / 2, s.clip(sub, 18, O['LIST_TEXT_W']), 18, (0xAA,) * 3)
        d.rectangle((0, y + R - 1, W - 1, y + R - 1), fill=HAIR)
    if search:
        cy = NAV + top + len(stations) * R + CREDIT_GAP
        if cy < WIN: credit(s, im, O['LIST_TEXT_X'], cy)
    navbar(s, im, title, search, 'list')
    return im


def grid_page(s, title, top=TOP, search=False):
    im = new_page(s, title, big=not search)
    for i, (name, sub, logo) in enumerate(STATIONS):
        x = MARGIN + (i % 2) * (COVER + GCOL); y = NAV + top + (i // 2) * PITCH
        if y >= WIN: break
        cover(s, im, x, y, synthetic_logo(i) if logo else None)
        s.text(im, x, y + COVER + TITLE_GAP + TITLE_H / 2, s.clip(name, 18, COVER), 18)
        s.text(im, x, y + COVER + TITLE_GAP + TITLE_H + SUB_H / 2, s.clip(sub, 15, COVER), 15, (0xAA,) * 3)
    if search:   # the credit is on the root and the search results only
        cy = NAV + top + (len(STATIONS) + 1) // 2 * PITCH - GROW + CREDIT_GAP
        if cy < WIN: credit(s, im, MARGIN, cy)
    navbar(s, im, title, search, 'grid')
    return im


def field_tree(s, name):
    return awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', name + '.bin'), 'rb').read())


def draw_field(s, im, root, y_off, text, caret=True, hint='Search'):
    """A search field from a built page (kb_field, its magnifier, hint or text, caret and clear button; the Search page's drawing, preview_search.draw_top) at window y f.y + y_off. Radio's
    capsule (fill and magnifier) is rd_capsule, under a kb_field with no fill whose text starts at its x 0."""
    f = root.find('kb_field'); y = f.y + y_off
    cap = root.find('rd_capsule') or f
    mag, clear, caret_n = root.find('kb_mag'), root.find('kb_clear'), root.find('kb_caret')
    rgb = PKV.rgb
    def paint(d, k): d.rounded_rectangle(k(cap.x, y, cap.x + cap.w, y + cap.h), radius=PSE.D['SE_FIELD_R'] * PKV.SS, fill=rgb(cap.get('style:normal:bg_color')) + (255,))
    im.alpha_composite(PKV.layer(paint))
    im.alpha_composite(s.img(mag.get('image')), (cap.x + mag.x + (mag.w - 16) // 2, y + mag.y))
    tx, ty = f.x + root.find('kb_text').x, y + f.h / 2
    room = root.find('kb_text').w
    if text:
        shown = text
        while s.font.width(shown, PSE.FIELD_PX) > room and len(shown) > 1: shown = shown[1:]
        s.text(im, tx, ty, shown, PSE.FIELD_PX, rgb(root.find('kb_text').get('style:normal:text_color')))
        c = s.img(clear.get('style:normal:icon')); im.alpha_composite(c, (f.x + clear.x + (clear.w - c.width) // 2, int(ty - c.height / 2)))
        cx = tx + s.font.width(shown, PSE.FIELD_PX) + 1
    else:
        s.text(im, tx, ty, hint, PSE.FIELD_PX, rgb(root.find('kb_hint').get('style:normal:text_color'))); cx = tx
    if caret: ImageDraw.Draw(im).rectangle((cx, y + caret_n.y, cx + caret_n.w - 1, y + caret_n.y + caret_n.h - 1), fill=rgb(caret_n.get('style:normal:bg_color')))


def search_screen(s, kb, root, results, keyboard):
    """Radio's search level on a 320 x 480 screen (the status bar over the 450 px window): the field under the navbar, then the pad or the results."""
    scr = Image.new('RGBA', (W, PKV.H), (0, 0, 0, 255)); PI.status_bar(s, scr)
    page = list_page(s, 'Search', TOP_SEARCH, True) if results else new_page(s, 'Search', big=False)
    if not results: navbar(s, page, 'Search', True, None)
    draw_field(s, page, root, 0, 'jazz fm' if results else 'jazz', caret=keyboard)
    s.text(page, 58, 25, PS.fit(s, PS.tr(s, 'Search Stations'), 22, 214 - 58), 22)   # the small title, shown on the search page, ends at the glass (patch/radiopage.c rp_nav: x 214)
    scr.alpha_composite(page, (0, PKV.BAR))
    if keyboard: PKV.keyboard(kb, scr, 'abc', None)
    return scr


def addurl_screen(s, kb, root, step, url, name):
    """Add by URL (patch/radiopage.c rp_entry): the navbar with Now Playing as the lone disc, the Sign In card (Stream URL, Station Name), the field on row step - 1, the other row's value
    or grey name, the keyboard (Next on the address, Done on the name)."""
    by = {w.name: w for w in root.walk() if w.name}
    scr = Image.new('RGBA', (W, PKV.H), (0, 0, 0, 255)); PI.status_bar(s, scr)
    page = new_page(s, 'Add by URL', big=False)
    d = ImageDraw.Draw(page); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    PS.glass(s, page, 'ah_nav_back', 7, 44); PS.glass(s, page, 'ah_nav_np', 260, 60)
    s.text(page, 58, 25, PS.tr(s, 'Add by URL'), 22)
    c, h = by['rd_add_card'], by['rd_add_hair']
    def paint(d, k):
        d.rounded_rectangle(k(c.x, c.y, c.x + c.w, c.y + c.h), radius=int(c.get('style:normal:round_radius')) * PKV.SS, fill=PKV.rgb(c.get('style:normal:bg_color')) + (255,))
        d.rectangle(k(h.x, h.y, h.x + h.w, h.y + h.h), fill=PKV.rgb(h.get('style:normal:bg_color')) + (255,))
    page.alpha_composite(PKV.layer(paint))
    def fitted(t, room, tail):
        while s.font.width(t, PSE.FIELD_PX) > room and len(t) > 1: t = t[1:] if tail else t[:-2] + '…'
        return t
    car, cl = by['kb_caret'], by['kb_clear']
    for i, (text, room) in enumerate(((url, pod_ui.RD_ADD_VAL_W), (name, pod_ui.RD_ADD_VAL_W))):
        v = by[f'rd_add_v{i}']; y = v.y + v.h / 2
        if i == step - 1:
            t = fitted(text, pod_ui.RD_ADD_TW, True)
            if text: s.text(page, v.x, y, t, PSE.FIELD_PX, (255,) * 3)
            else: s.text(page, v.x, y, PS.tr(s, pod_ui.RD_ADD_ROWS[i]), PSE.FIELD_PX, PKV.rgb(by[f'rd_add_h{i}'].get('style:normal:text_color')))
            cx = v.x + (s.font.width(t, PSE.FIELD_PX) + 1 if text else 0)
            cy = v.y + (v.h - pod_ui.PS.SE_FIELD_H) // 2 + car.y   # the 36 px field centred in the row (patch/radiopage.c RP_ADD_DY)
            ImageDraw.Draw(page).rectangle((cx, cy, cx + car.w - 1, cy + car.h - 1), fill=(255,) * 3)
            if text and text != 'http://':
                g = s.img(cl.get('style:normal:icon')); fw = pod_ui.trail_field_w(v.x)
                page.alpha_composite(g, (v.x + fw - cl.w + (cl.w - g.width) // 2, int(y - g.height / 2)))
        elif text: s.text(page, v.x, y, fitted(text, room, False), PSE.FIELD_PX, (255,) * 3)
        else: s.text(page, v.x, y, PS.tr(s, pod_ui.RD_ADD_ROWS[i]), PSE.FIELD_PX, PKV.rgb(by[f'rd_add_h{i}'].get('style:normal:text_color')))
    scr.alpha_composite(page, (0, PKV.BAR))
    PKV.keyboard(kb, scr, 'abc', None, go=('Next' if step == 1 else 'Done', step == 1 and url == 'http://'))
    return scr


def library_search_screen(s, kb):
    t = PSV.Tree(s)
    return PSV.screen(s, t, kb, 'jazz', PSV.ALBUMS, 0, True)


def genres_page(s):
    im = new_page(s, 'Genres'); d = ImageDraw.Draw(im)
    for i, (name, n) in enumerate(GENRES):
        y = NAV + TOP + i * 64
        PF.chevron(im, 289, y + 24)
        s.text(im, 16, y + O['LIST_TITLE_Y'] + O['LIST_TITLE_H'] / 2, name, 20)
        s.text(im, 16, y + O['LIST_SUB_Y'] + O['LIST_SUB_H'] / 2, PS.tr(s, '%d stations').replace('%d', str(n)), 15, (0xAA,) * 3)
        d.rectangle((16, y + 63, W - 11, y + 63), fill=HAIR)
    navbar(s, im, 'Genres')
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    panels = [('Radio: Now Playing group, no separator', root_page(s)), ('By Country: A-Z list, rail', countries_page(s)), ('Top Stations: list (default)', list_page(s, 'Top Stations')),
              ('Top Stations: grid', grid_page(s, 'Top Stations')), ('My Stations: the "..." card', stations_card(s)), ('Recently Played: the "..." card', stations_card(s, True, True)), ('Search results: list', list_page(s, 'Search', TOP_SEARCH, True)), ('By Genre: the rows', genres_page(s))]
    kb, root = PKV.Page(s), field_tree(s, 'm1plus_radio')
    panels += [('Radio search: keyboard up (field 296 wide)', search_screen(s, kb, root, False, True).crop((0, PKV.BAR, W, PKV.BAR + 450))),
               ('Radio search: results (toggle + Now Playing)', search_screen(s, kb, root, True, False).crop((0, PKV.BAR, W, PKV.BAR + 450))),
               ('Library Search (for comparison)', library_search_screen(s, kb).crop((0, PKV.BAR, W, PKV.BAR + 450))),
               ('Add by URL: the address', addurl_screen(s, kb, root, 1, 'https://stream.example.com/live', '').crop((0, PKV.BAR, W, PKV.BAR + 450))),
               ('Add by URL: the name', addurl_screen(s, kb, root, 2, 'https://stream.example.com:8000/live.mp3', 'stream.example.com').crop((0, PKV.BAR, W, PKV.BAR + 450)))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()

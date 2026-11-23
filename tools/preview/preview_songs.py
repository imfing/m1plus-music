#!/usr/bin/env python3
"""Approximate PIL mock-up of the Songs page (patch/songs.c, docs/modules/songs.md) drawn from the built asset (ui/m1plus_songs.bin) and the payload's constants
(patch/offsets.inc SG_*, LIST_*): the large "Songs" title and the flat Play / Shuffle pills, the songs in sections (pinned header while scrolling), the A-Z
rail with its disc and the 110 px bubble, the glass navbar (Search | ... | Now Playing; Search | Select | Now Playing on a list with no card), the sort card, select mode (marks, "N Selected", Select All, the bar), and the
other lists on the page (Favourites, a playlist: Search / Select, no sections, no rail, the title cut with an ellipsis).
Not pixel-exact AWTK (the text is the project's own text model, the covers are stand-in gradients).

  preview_songs.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release). Titles are in the stock Title order: symbols and digits first (the stock scan's '#' and '*', one section "#"), then A..Z,
a CJK title under its pinyin initial.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import awtk_ui
import preview_icons as PI
import mod_icons as M
import pod_i18n, pod_pages, pod_ui

W, WIN, NAV = 320, 450, 50
RAW = PI.RAW
O = PI.offsets()
GREY, ACCENT = (0xAA, 0xAA, 0xAA), (0xEE, 0xEE, 0xEC)
ACC = None   # an accent's (r, g, b): the rail's disc and the selected mark take it, the pressed sheet row is its tint (tools/preview/preview_accent.py sets it)
PRESSED_ROW = None   # the sheet row drawn pressed (row_menu)
TOP, HDR_H, ROW_H = O['SG_TOP'], O['SG_HDR_H'], O['LIST_ROW_H']
ART, ART_X, ART_Y = O['LIST_ART'], O['LIST_ART_X'], O['LIST_ART_Y']
TEXT_X, TEXT_END, SEL_COL, MARK, BAR_H = O['LIST_TEXT_X'], O['LIST_HAIR_END'] - O['SG_RAIL_INSET'], O['SG_SEL_COL'], O['SG_MARK'], O['SG_BAR_H']
PILL_Y, PILL_H, PILL_W, PILL_R = O['SG_PILL_Y'], O['SG_PILL_H'], O['SG_PILL_W'], O['SG_PILL_R']
PILL_RGB, PILL_DOWN, GLYPH, GAP = (0x1C, 0x1C, 0x1E), (0x33, 0x33, 0x33), O['SG_PILL_GLYPH'], O['SG_PILL_GAP']
BAND, HAIR = (0x14, 0x14, 0x14), (0x22, 0x22, 0x22)
RAIL_X, RAIL_W, RAIL_CX, RAIL_PITCH, RAIL_ITEMS, RAIL_DOT, DISC, BUBBLE = (O[k] for k in ('SG_RAIL_X', 'SG_RAIL_W', 'SG_RAIL_CX', 'SG_RAIL_PITCH', 'SG_RAIL_ITEMS', 'SG_RAIL_DOT', 'SG_RAIL_DISC', 'SG_BUBBLE'))
DOT_RGB = tuple((O['SG_RAIL_DOT_RGB'] >> s) & 255 for s in (16, 8, 0))
ALL_LETTERS = ['#'] + [chr(65 + i) for i in range(26)]     # a library with a song under every letter: 27 sections, the collapsed index
MORE_W, INK_X, INK_GAP, DOTS_PX = O['RM_MORE_W'], O['RM_INK_X'], O['RM_INK_GAP'], O['RM_DOTS_PX']   # the rows' "..." (patch/rowmenu.c): its tap zone, the glyph's first ink column, the gap from the text to the ink, the glyph
DOTS_RGB = tuple((O['RM_DOTS_RGB'] >> sh) & 255 for sh in (16, 8, 0))

# title, artist, cover colour (index into PI.ALBUMS), the Initial a CJK title files under (the stock scan: its pinyin initial)
SONGS = [("(Sittin' On) The Dock of the Bay", 'Otis Redding', 9), ('1979', 'The Smashing Pumpkins', 11), ('99 Luftballons', 'Nena', 5),
         ('Abbey Road Medley', 'The Beatles', 2), ('Aja', 'Steely Dan', 6), ('All Blues', 'Miles Davis', 0),
         ('Blue in Green', 'Miles Davis', 0), ('Bohemian Rhapsody', 'Queen', 4),
         ('Come Together', 'The Beatles', 2), ('Creep', 'Radiohead', 6), ('春よ、来い', '松任谷由実', 10, 'C'),
         ('Do I Wanna Know?', 'Arctic Monkeys', 3), ('Dreams', 'Fleetwood Mac', 4),
         ('Fade Into You', 'Mazzy Star', 7), ('Fly Me to the Moon', 'Frank Sinatra', 9),
         ('Hey Jude', 'The Beatles', 2), ('Hotel California', 'Eagles', 1),
         ('Jolene', 'Dolly Parton', 1), ('Karma Police', 'Radiohead', 6),
         ('Let It Be', 'The Beatles', 2), ('Lovely Day', 'Bill Withers', 7),
         ('Money', 'Pink Floyd', 3), ('Moon River', 'Audrey Hepburn', 9),
         ('Rolling in the Deep', 'Adele', 8), ('Smells Like Teen Spirit', 'Nirvana', 8),
         ('Take Five', 'The Dave Brubeck Quartet', 0), ('Thriller', 'Michael Jackson', None), ('夜に駆ける', 'YOASOBI', 10, 'Y')]


def section(t):
    """The payload's section letter (patch/songs.c sg_letter): the Initial, '*' (digits) and '#' (the rest) one section "#"."""
    if len(t) > 3: return t[3]
    c = t[0][0].upper()
    return c if c.isalpha() and c.isascii() else '#'


def dots(s):
    """The row's "..." as the payload makes it (patch/rowmenu.c rm_make_dots): #8C8C8C with the image's coverage (cc_decode flattens it over black: the red channel) as the alpha."""
    g = s.img('rm_dots').convert('RGBA')
    flat = Image.new('RGBA', g.size, (0, 0, 0, 255)); flat.alpha_composite(g)
    out = Image.new('RGBA', g.size, DOTS_RGB + (255,)); out.putalpha(flat.getchannel('R'))
    return out


def more_right(rail):
    """The right edge of the "..." zone: the list's edge, or left of the rail's touch column while the A-Z rail is shown (patch/songs.c sg_more_right)."""
    return O['RM_MORE_RIGHT_RAIL'] if rail else O['RM_MORE_RIGHT']


def dots_x(right, rail):
    """The "..." bitmap's x: centred in the zone ending at `right`, or with its right edge on `right` beside the rail (patch/rowmenu.c rowmenu_paint `flush`)."""
    return right - DOTS_PX if rail else right - MORE_W + (MORE_W - DOTS_PX) // 2


def build_items(sections=True, top=TOP):
    """Flat list of ('h', letter, y) and ('r', song, y) with the content y of each, plus {letter: header y}. sections=False: a list (Favourites, a playlist ...), rows only."""
    items, y, heads, last = [], top, {}, None
    for t in SONGS:
        c = section(t)
        if sections and c != last:
            items.append(('h', c, y)); heads[c] = y; y += HDR_H; last = c
        items.append(('r', t, y)); y += ROW_H
    return items, heads, y


def round_rect(im, x, y, w, h, r, rgb):
    k = 4; mask = Image.new('L', (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=r * k, fill=255)
    im.paste(Image.new('RGBA', (w, h), rgb + (255,)), (x, y), mask.resize((w, h), Image.LANCZOS))


def play_header(s, im, y):
    """A playlist's header: the album page's Shuffle disc and Play pill (patch/common.c m1_pill_place): y is the pill's drawn top (PH_PILL_Y), the 44 px buttons start 2 px above it."""
    by = y - (O['AH_BTN_H'] - O['AH_PILL_H']) // 2
    disc = s.img('ah_shuffle'); im.alpha_composite(disc, (O['AH_SHUF_X'] + (O['AH_SHUF_W'] - disc.width) // 2, by + (O['AH_BTN_H'] - disc.height) // 2))
    im.alpha_composite(s.img('ah_pill'), (O['AH_PLAY_X'], by + (O['AH_BTN_H'] - O['AH_PILL_H']) // 2))
    word = tr(s, 'Play')
    tw = s.font.width(word, 18)
    if O['AH_PILL_GLYPH'] + O['AH_PILL_GAP'] + tw > O['AH_PLAY_W']: tw = O['AB_PLAY_TEXT_W']
    gx = O['AH_PLAY_X'] + (O['AH_PLAY_W'] - (O['AH_PILL_GLYPH'] + O['AH_PILL_GAP'] + tw)) // 2
    im.alpha_composite(s.img('ah_play'), (gx, by + (O['AH_BTN_H'] - O['AH_PILL_GLYPH']) // 2))
    s.text(im, gx + O['AH_PILL_GLYPH'] + O['AH_PILL_GAP'], by + O['AH_BTN_H'] / 2, word, 18, (0x14, 0x14, 0x14))


def pill(s, im, x, y, label, glyph, rgb=PILL_RGB, w=PILL_W):
    """A flat pill as the payload lays it out: the glyph (centred in a square as high as the button at margin_left) and the label 8 px after the glyph's ink, the pair centred."""
    round_rect(im, x, y, w, PILL_H, PILL_R, rgb)
    tw = s.font.width(label, 18); gx = x + (w - (GLYPH + GAP + tw)) // 2
    im.alpha_composite(glyph, (gx, y + (PILL_H - glyph.height) // 2)); s.text(im, gx + GLYPH + GAP, y + PILL_H / 2, label, 18)


def tr(s, english):
    k = pod_i18n.key_for(english)
    return s.strings.get(k, k) if k else english


def fit(s, text, px, room):
    """patch/songs.c sg_fit: the text, or its longest prefix that fits with an ellipsis after it (no space before it)."""
    if s.font.width(text, px) <= room: return text
    k = len(text) - 1
    while k and s.font.width(text[:k].rstrip(' ') + '…', px) > room: k -= 1
    return text[:k].rstrip(' ') + '…'


def wrap2(s, text, px, room):
    """patch/common.c m1_wrap2: one line when it fits, else broken at the last space that leaves line 1 inside room (else at the last character that fits), line 2 cut with an ellipsis."""
    if s.font.width(text, px) <= room: return [text]
    cut = len(text)
    while cut > 1 and s.font.width(text[:cut], px) > room: cut -= 1
    sp = text.rfind(' ', 0, cut + 1)
    head, rest = (text[:sp].rstrip(), text[sp:].lstrip()) if sp > 0 and text[:sp].strip() else (text[:cut], text[cut:])
    return [head, s.clip(rest, px, room)]


def head_shift(s, title):
    """A playlist's header: AH_TITLE_LH px more when its name takes two lines (patch/songs.c sg.tsh)."""
    return O['AH_TITLE_LH'] if len(wrap2(s, title, 22, O['PH_NAME_W'])) > 1 else 0


def content(s, covers_on=True, select=None, title=None, head=False, edit=False, pick=None):
    """The whole list as one tall image (window x, content y): title, pills, headers, rows. select: the set of marked titles in select mode (a mark column; the pills dim).
    title: a list's title (no sections), else the library's "Songs"."""
    tsh = head_shift(s, title) if head else 0
    items, heads, end = build_items(title is None, O['PH_TOP'] + tsh - (O['PH_EDIT_UP'] if edit else 0) if head else 0 if pick is not None else TOP)   # (Add Songs: the rows start under the navbar)
    im = Image.new('RGBA', (W, end + O['SG_FOOT_H'] + 20), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    if head:   # a playlist's header: the mosaic (the Playlists page's tile, PH_COVER px, 10 px corners), the name 22 px centred under it (patch/songs.c; the count is the footer only)
        im.alpha_composite(PI.mosaic([PI.ALBUMS[i][2] for i in (0, 1, 2, 3)], O['PH_COVER'], O['PH_COVER_R']), (O['PH_COVER_X'], O['PH_COVER_Y']))
        lines = wrap2(s, title, 22, O['PH_NAME_W'])
        for i, line in enumerate(lines): s.text(im, W / 2, O['PH_NAME_Y'] + i * O['AH_TITLE_LH'] + O['PH_NAME_H'] / 2, line, 22, anchor='m')
        if edit: im.alpha_composite(s.img('sg_pencil'), (int(W / 2 + s.font.width(lines[-1], 22) / 2 + 8), O['PH_NAME_Y'] + tsh + (O['PH_NAME_H'] - 16) // 2))   # Edit: the grey pencil after the name (patch/songs.c sg_pencil)
    elif pick is None: s.text(im, O['SG_TITLE_X'], O['SG_TITLE_H'] / 2, fit(s, title, 32, O['SG_TITLE_W']) if title else tr(s, 'Songs'), 32)
    n = sum(1 for it in items if it[0] == 'r')   # the song count under the last row (patch/songs.c sg_foot_text: the key by n == 1, the number where %d is)
    foot = tuple(int(pod_ui.SG_FOOT_RGB[i:i + 2], 16) for i in (1, 3, 5))
    count = tr(s, '%d song' if n == 1 else '%d songs').replace('%d', str(n))
    s.text(im, O['SG_HDR_X'], end + O['SG_FOOT_GAP'] + O['SG_FOOT_TEXT_H'] / 2, count, O['SG_FOOT_PX'], foot)
    if head:
        if not edit: play_header(s, im, O['PH_PILL_Y'] + tsh)
    elif pick is None:
        for i, (label, g) in enumerate((('Play', 'sg_play'), ('Shuffle', 'sg_shuffle'))):
            pill(s, im, (O['SG_PILL_X0'], O['SG_PILL_X1'])[i], PILL_Y, tr(s, label), s.img(g), PILL_RGB if select is None else BAND)
    shift = SEL_COL if select is not None else 0
    tx = TEXT_X + shift
    more, title_none = dots(s), title is None   # (the library has the rail: the "..." sits left of it)
    handle = Image.new('RGBA', (O['SG_HANDLE_PX'],) * 2, (0x8E, 0x8E, 0x93, 0)); handle.putalpha(M.handle_image().getchannel('A'))
    on, off = s.img('selected'), s.img('unselect')
    if ACC:   # patch/common.c m1_make_mark: the selected mark's lightness scales the accent (white goes to it, the black tick stays)
        on = on.copy(); on.putdata([(((ACC[0] * p[0] + 127) // 255, (ACC[1] * p[0] + 127) // 255, (ACC[2] * p[0] + 127) // 255, p[3])) for p in on.getdata()])
    for kind, v, y in items:
        if kind == 'h':
            header(s, im, v, y); continue
        title, artist, ci = v[:3]
        right = more_right(title_none)
        end = TEXT_END if title_none else O['LIST_HAIR_END']   # (without the rail the rows run to the list-row spec's end)
        room = (O['SG_HANDLE_X'] if edit else end) - tx if select is not None else dots_x(right, title_none) + INK_X - INK_GAP - tx   # (select mode has no "...": the text ends at the hairline's end again)
        d.rectangle((tx, y + ROW_H - 1, end - 1, y + ROW_H - 1), fill=HAIR)
        if pick is not None:   # Add Songs: a white plus, or the grey tick for a song the playlist has (the baked sg_padd / sg_pdone, patch/songs.c sg_make_bmp)
            mk = s.img('sg_padd').copy() if title not in pick else Image.new('RGBA', (DOTS_PX,) * 2, (0x8E, 0x8E, 0x93, 0))
            if title in pick: mk.putalpha(s.img('sg_pdone').getchannel('A'))
            im.alpha_composite(mk, (dots_x(right, title_none), y + (ROW_H - 1 - DOTS_PX) // 2))
        elif select is None: im.alpha_composite(more, (dots_x(right, title_none), y + (ROW_H - 1 - DOTS_PX) // 2))
        if edit: im.alpha_composite(handle, (O['SG_HANDLE_CX'] - O['SG_HANDLE_PX'] // 2, y + (ROW_H - 1 - O['SG_HANDLE_PX']) // 2))   # Edit: the reorder handle (the baked sg_handle, #8E8E93)
        if select is not None:
            mk = on if title in select else off
            im.alpha_composite(mk, (ART_X + (SEL_COL - 6 - mk.width) // 2, y + (ROW_H - mk.height) // 2))
        rgb = PI.ALBUMS[ci][2] if ci is not None else None
        im.alpha_composite(PI.rounded(PI.sample_cover(rgb, ART), O['LIST_R']), (ART_X + shift, y + ART_Y))
        s.text(im, tx, y + O['LIST_TITLE_Y'] + O['LIST_TITLE_H'] / 2, s.clip(title, 20, room), 20)
        s.text(im, tx, y + O['LIST_SUB_Y'] + O['LIST_SUB_H'] / 2, s.clip(artist, 18, room), 18, GREY)
    return im, heads


def header(s, im, letter, y):
    """A section header: the letter alone, 20 px white at x 10 on the page's black (the Recently Played shelf header's look: no band, no hairline)."""
    s.text(im, O['SG_HDR_X'], y + (HDR_H - 1) / 2, letter, 20)


def rail_plan(n):
    """The sections whose letters the rail draws (patch/songs.c sg_rail_plan): all of them when they fit RAIL_ITEMS, else every k-th with the first and last kept."""
    if n <= RAIL_ITEMS: return list(range(n))
    for k in range(2, n):
        secs = list(range(0, n - 1, k))
        if len(secs) > 1 and n - 1 - secs[-1] < (k + 1) // 2: secs.pop()
        secs.append(n - 1)
        if 2 * len(secs) - 1 <= RAIL_ITEMS: return secs


def rail(s, im, letters, touched=None, view=WIN - NAV):
    """The compact index (the stock page's A . . F . . K look): the plan's letters with a dot between two of them, centred on the list's height; the touched letter,
    when it is a drawn one, on an accent disc with a black letter."""
    d = ImageDraw.Draw(im); secs = rail_plan(len(letters)); dots = len(secs) < len(letters)
    step = 2 if dots else 1; span = (2 * len(secs) - 1 if dots else len(secs)) * RAIL_PITCH; y0 = (view - span) // 2
    ink2, dxs = pod_ui.rail_metrics(os.path.join(s.tree, RAW, 'fonts/default.ttf'))   # as the payload gets them (stock.h)
    dot_y, disc_y = (ink2 - RAIL_DOT) // 2, -((DISC - ink2 + 1) // 2)
    for j, sec in enumerate(secs):
        c, top = letters[sec], NAV + y0 + step * j * RAIL_PITCH
        if j and dots:
            dy = top - RAIL_PITCH + dot_y; dx = RAIL_CX - RAIL_DOT // 2
            d.rectangle((dx, dy + 1, dx + RAIL_DOT - 1, dy + RAIL_DOT - 2), fill=DOT_RGB); d.rectangle((dx + 1, dy, dx + RAIL_DOT - 2, dy + RAIL_DOT - 1), fill=DOT_RGB)
        on = c == touched
        if on:
            k = 4; r = DISC // 2
            disc = Image.new('L', (2 * r * k, 2 * r * k), 0); ImageDraw.Draw(disc).ellipse((0, 0, 2 * r * k - 1, 2 * r * k - 1), fill=255)
            im.paste(Image.new('RGBA', (2 * r, 2 * r), (ACC or ACCENT) + (255,)), (RAIL_CX - r, top + disc_y), disc.resize((2 * r, 2 * r), Image.LANCZOS))
        # canvas_draw_text_in_rect: the rect (SG_RAIL_TEXT_W wide, centred on the dots' x, moved by the letter's SG_RAIL_DX), the text at rect.x + (rect.w - lw) / 2, its box (13 - 12) / 2 down
        tw = O['SG_RAIL_TEXT_W']; rx = RAIL_CX - tw // 2 + dxs[0 if c == '#' else ord(c) - 64]
        s.font.draw(im, rx + (tw - s.font.width(c, 12)) // 2, top + (RAIL_PITCH - 12) // 2, c, 12, ((0, 0, 0) if on else ACCENT) + (255,))


def tick(im, x, y, size, rgb):
    t = Image.open(os.path.join(M.PNG, 'sg_tick.png')).convert('RGBA'); im.alpha_composite(t, (x, y))


def glass(s, im, name, x, button_w=46):
    """A glass piece of the navbar: the button's image centred in it (img_btn_style), 42 px high in the 50 px bar."""
    g = s.img(name); im.alpha_composite(g, (x + (button_w - g.width) // 2, (NAV - g.height) // 2))


def selall(s, im, text, on=True):
    """The select mode's Select All: a glass pill (sg_selall_glass) at the navbar's right, 14 px each side of the 17 px label, right edge at SG_SELALL_R."""
    tw = s.font.width(text, 17); pw = tw + 2 * O['SG_SELALL_PAD']; x = O['SG_SELALL_R'] - pw
    im.alpha_composite(M.glass_image(pw, O['SG_SELALL_H'], O['SG_SELALL_H'] // 2), (x, O['SG_SELALL_Y']))
    s.text(im, x + O['SG_SELALL_PAD'], NAV // 2, text, 17, (255, 255, 255) if on else (0x59,) * 3)


def selbar(s, im, win_h, pieces, on=True):
    """The select bar's one centred glass capsule of icon-only 60 px slots (M.selbar_images: 'add' + 'del', or 'one'), vertically centred in the SG_BAR_H bar; dimmed glyphs while nothing is marked."""
    f = M.selbar_images(); slot = M.SELBAR_SLOT
    x = (W - slot * len(pieces)) // 2; y = win_h - BAR_H + (BAR_H - M.GLASS_H) // 2
    for k, n in enumerate(pieces): im.alpha_composite(f['sg_bar_' + n + ('' if on else '_off')], (x + k * slot, y))


def navbar(s, im, scroll, select, title=None, artist=False, search=True, direct=False, edit=False, pick=None):
    d = ImageDraw.Draw(im); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    if pick is not None:   # Add Songs: the check where Back is, "Add to <name>" (cut to the room before Now Playing's place), nothing else
        glass(s, im, 'ah_nav_done', 7, 44)
        s.text(im, O['NAV_TITLE_X'], 25, fit(s, tr(s, 'Add to %s').replace('%s', pick[1]), PI.title_px(s.tree), O['NAV_VIEW_X'] + O['NAV_VIEW_W'] - O['NAV_TITLE_X']), PI.title_px(s.tree))
        return
    if select is not None:    # select mode: the x (glass disc) where Back was, "N Selected" from x 58, Select All at the right
        glass(s, im, 'ah_nav_done' if edit else 'ah_nav_close', 7, 44)   # (Edit: the check)
        s.text(im, O['NAV_TITLE_X'], 25, s.strings.get('%d Selected', '%d Selected').replace('%d', str(len(select))), PI.title_px(s.tree))
        selall(s, im, tr(s, 'Select All'))
        return
    glass(s, im, 'ah_nav_back', 7, 44); glass(s, im, 'ah_nav_play', 260, 60)
    if artist:    # an artist's songs: Cover Flow (the left cap) | Select (middle) | Now Playing
        glass(s, im, 'pod_nav_coverflow', O['NAV_CF_X']); glass(s, im, 'pod_nav_select' if direct else 'pod_nav_moremid', O['NAV_VIEW_X'])
    elif search: glass(s, im, 'pod_nav_search', O['NAV_CF_X']); glass(s, im, 'pod_nav_select' if direct else 'pod_nav_moremid', O['NAV_VIEW_X'])    # the lists that search: Search (the left cap) | "..." or Select (middle) | Now Playing
    else: glass(s, im, 'pod_nav_selectl' if direct else 'pod_nav_more', O['NAV_VIEW_X'])    # a genre's or a playlist's songs: Select (the left cap, where the "..." was) | Now Playing
    room = (O['NAV_CF_X'] if artist or search else O['NAV_VIEW_X']) - O['NAV_TITLE_X']
    if scroll > O['SG_COLLAPSE']:    # the large title has scrolled away: the navbar carries the small one (cut with an ellipsis to its room)
        s.text(im, O['NAV_TITLE_X'], 25, fit(s, title or tr(s, 'Songs'), PI.title_px(s.tree), room), PI.title_px(s.tree))


def sort_card(s, im, current=0, rev=False, kind='library'):
    """The \"...\" card (patch/viewsort.c, the shared card): the scrim's dim, then what the list offers (docs/modules/songs.md): the library's Select and Title, File Name, Format and Recently Added
    in vs_glass5, a tick on `current` (0..3) with its direction line under the label (A-Z / Z-A, and for Recently Added Newest First / Oldest First); 'list' Select (vs_glass1);
    'recent' Select and Albums / Songs with Songs ticked (vs_glass3); 'albums' Albums ticked, Songs (vs_glass2); 'select' Select alone (vs_glass1)."""
    im.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 0x82)))
    sub = tr(s, ('Z–A' if rev else 'A–Z') if current < 3 else ('Oldest First' if rev else 'Newest First'))
    select = ('Select', 'pod_ic_vsselect', False, None)
    grid, lst = ('Albums', 'pod_ic_vsgrid', kind == 'albums', None), ('Songs', 'pod_ic_vslist', kind == 'recent', None)
    sorts = [(k, None, i == current, sub if i == current else None) for i, k in enumerate(pod_pages.SONGS_SORT_KEYS)]
    rows, glass_name, hairs = {'library': ([select] + sorts, 'vs_glass5', (1,)), 'list': ([select], 'vs_glass1', ()), 'recent': ([select, grid, lst], 'vs_glass3', (1,)),
                               'albums': ([grid, lst], 'vs_glass2', ()), 'select': ([select], 'vs_glass1', ())}[kind]
    PI.view_card(s, im, rows, glass_name, hairs)


SHEET_GROUPS = ({'Play', 'Shuffle'},
                {'Pin Album', 'Unpin Album', 'Pin Song', 'Unpin Song', 'Pin Artist', 'Unpin Artist', 'Pin Playlist', 'Unpin Playlist', 'Add to Playlist', 'Download', 'Remove Download',
                 'Cancel Download', 'Favorite', 'Undo Favorite', 'Get Info'},
                {'Play Next', 'Play After'}, {'Select'}, {'Remove from Playlist', 'Remove from Queue'})   # the sheets' groups (patch/rowmenu.c: a hairline between two, none inside one)


def sheet_group(key): return next((i for i, g in enumerate(SHEET_GROUPS) if key in g), -1)


def row_menu(s, im, keys=('Pin Song', 'Add to Playlist', 'Favorite', 'Get Info', 'Play Next', 'Play After'), fav_on=False,
             glyphs=('rm_ic_pin', 'rm_ic_add', 'rm_ic_fav', 'rm_ic_info', 'rm_ic_next', 'rm_ic_after')):
    """The rows' menu (patch/rowmenu.c rm_layout, tools/pod_ui.py row_menu): the scrim's dim, then the sheet at the window's foot: the pc_sheet<n> pane (320 x 50 n, top corners only),
    50 px rows, a 24 px glyph at x 14, the 18 px label from x 48; the rows in groups (SHEET_GROUPS) with the 13 % white hairline on the top edge of every group's first row but the sheet's
    first, none inside a group; the destructive rows' labels red (pod_ui.RM_RED_KEYS)."""
    import pod_ui
    im.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 0x82)))
    rh = O['PM_ROW_H']; h = len(keys) * rh; y = im.height - h
    im.alpha_composite(s.img('pc_sheet%d' % len(keys)), (0, y))
    for i, (key, name) in enumerate(zip(keys, glyphs)):
        ry = y + i * rh
        if i and sheet_group(key) != sheet_group(keys[i - 1]): im.alpha_composite(Image.new('RGBA', (W, 1), (255, 255, 255, 0x22)), (0, ry))
        if i == PRESSED_ROW: im.alpha_composite(Image.new('RGBA', (W, rh), (ACC + (56,)) if ACC else (255, 255, 253, 0x10)), (0, ry))
        if fav_on and key == 'Favorite': name, key = 'rm_ic_unfav', 'Undo Favorite'
        g = s.img(name); im.alpha_composite(g, (pod_ui.RM_ICON_X, ry + (rh - g.height) // 2))
        s.text(im, pod_ui.RM_TEXT_X, ry + rh / 2, s.clip(tr(s, key), pod_ui.RM_LABEL_PX, W - pod_ui.RM_TEXT_X - pod_ui.RM_TEXT_R), pod_ui.RM_LABEL_PX,
               tuple(int(pod_ui.RED_RGB[k:k + 2], 16) for k in (1, 3, 5)) if key in pod_ui.RM_RED_KEYS else (255, 255, 255))
    return 0, y, W, h


def page(s, covers=True, scroll=0, touched=None, select=None, menu=False, order=None, letters=None, title=None, head=False, row_menu_at=False, artist=False, search=True, direct=False, edit=False, pick=None):
    tsh = head_shift(s, title) if head else 0
    items, heads, end = build_items(title is None, O['PH_TOP'] + tsh - (O['PH_EDIT_UP'] if edit else 0) if head else 0 if pick is not None else TOP)
    tall, _ = content(s, covers, select, title, head, edit, pick[0] if pick else None)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    pad = BAR_H if select is not None else 0
    scroll = max(0, min(scroll, end + O['SG_FOOT_H'] + pad - (WIN - NAV)))       # the list ends with the song count at the window's foot (the bar's room added in select mode)
    im.alpha_composite(tall.crop((0, scroll, W, min(tall.height, scroll + WIN - NAV))), (0, NAV))
    hs = sorted((y, c) for c, y in heads.items())
    cur = max((h for h in hs if h[0] <= scroll), default=None)   # the pinned header: the section the top is in, pushed up by the next as it arrives
    if cur:
        nxt = next((h for h in hs if h[0] > cur[0]), None)
        push = min(0, nxt[0] - scroll - HDR_H) if nxt else 0
        band = Image.new('RGBA', (W, HDR_H), (0, 0, 0, 255)); header(s, band, cur[1], 0)
        if push < 0:    # a header that is not wholly inside the window has no letter (patch/songs.c sg_letter_text)
            ImageDraw.Draw(band).rectangle((0, 0, 60, HDR_H - 1), fill=(0, 0, 0))
        im.alpha_composite(band.crop((0, -push, W, HDR_H)), (0, NAV))
    navbar(s, im, scroll - (O['PH_COLLAPSE'] + tsh - O['SG_COLLAPSE'] if head else 0), select, title, artist, search, direct, edit, pick)   # (a playlist's header collapses the title at PH_COLLAPSE)
    if title is None: rail(s, im, letters or [h[1] for h in items if h[0] == 'h'], touched, WIN - NAV - pad)   # (a list has no rail)
    if select is not None:    # the bar: Add to Playlist, Delete (the stock multi-select's add and delete), flat pills
        if edit:   # a playlist's Edit: Delete (dim until a row is marked) | + (patch/songs.c sg_bar_edit)
            f = M.selbar_images(); x = (W - 2 * M.SELBAR_SLOT) // 2; y = WIN - BAR_H + (BAR_H - M.GLASS_H) // 2
            im.alpha_composite(f['sg_bar_edel' + ('' if select else '_off')], (x, y)); im.alpha_composite(f['sg_bar_eplus'], (x + M.SELBAR_SLOT, y))
        else: selbar(s, im, WIN, ('add', 'del'), bool(select))
    if menu: sort_card(s, im, *(order or (0, False)), kind='library' if menu is True else menu)
    if row_menu_at: row_menu(s, im, fav_on=row_menu_at == 'fav')
    if touched:
        x, y = (W - BUBBLE) // 2, NAV + (WIN - NAV - BUBBLE) // 2
        r = 4
        mask = Image.new('L', (BUBBLE * r, BUBBLE * r), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, BUBBLE * r - 1, BUBBLE * r - 1), radius=14 * r, fill=255)
        inner = Image.new('L', (BUBBLE * r, BUBBLE * r), 0)
        ImageDraw.Draw(inner).rounded_rectangle((r, r, BUBBLE * r - 1 - r, BUBBLE * r - 1 - r), radius=13 * r, fill=255)
        im.paste(Image.new('RGBA', (BUBBLE, BUBBLE), (0x3A, 0x3A, 0x3A, 255)), (x, y), mask.resize((BUBBLE, BUBBLE), Image.LANCZOS))
        im.paste(Image.new('RGBA', (BUBBLE, BUBBLE), (0x26, 0x26, 0x26, 255)), (x, y), inner.resize((BUBBLE, BUBBLE), Image.LANCZOS))
        s.text(im, x + BUBBLE / 2, y + BUBBLE / 2, touched, 56, anchor='m')
    return im


def empty_page(s, title):
    """An empty stock playlist (patch/songs.c sg_paint_add): the header (the placeholder disc as its mosaic, the name), then where the pills were (PH_EDIT_UP higher) one Add Songs row: the
    SG_ADD_TILE_RGB tile with the grey notes and the white badge, "Add Songs" in the title style centred on the row; no pills, no footer, no "No songs"."""
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    tall = Image.new('RGBA', (W, WIN - NAV), (0, 0, 0, 255))
    tall.alpha_composite(PI.mosaic([], O['PH_COVER'], O['PH_COVER_R']), (O['PH_COVER_X'], O['PH_COVER_Y']))
    for i, line in enumerate(wrap2(s, title, 22, O['PH_NAME_W'])): s.text(tall, W / 2, O['PH_NAME_Y'] + i * O['AH_TITLE_LH'] + O['PH_NAME_H'] / 2, line, 22, anchor='m')
    y = O['PH_TOP'] + head_shift(s, title) - O['PH_EDIT_UP']
    c = O['SG_ADD_TILE_RGB']; round_rect(tall, ART_X, y + ART_Y, ART, ART, O['LIST_R'], (c & 255, c >> 8 & 255, c >> 16 & 255))
    h = O['SG_HANDLE_RGB']; note, badge = M.add_tile_images()
    g = Image.new('RGBA', note.size, (h & 255, h >> 8 & 255, h >> 16 & 255, 0)); g.putalpha(note.getchannel('A'))
    tall.alpha_composite(g, (ART_X, y + ART_Y)); tall.alpha_composite(badge, (ART_X, y + ART_Y))
    s.text(tall, TEXT_X, y + (ROW_H - 1) / 2, tr(s, 'Add Songs'), 20)
    im.alpha_composite(tall, (0, NAV))
    navbar(s, im, -10 ** 6, None, title, False, False, True)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    asset = awtk_ui.parse(open(os.path.join(a.workdir, RAW, 'ui', 'm1plus_songs.bin'), 'rb').read())
    assert asset.find('sg_rail') is not None and (asset.find('sg_rail').x, asset.find('sg_rail').w) == (RAIL_X, RAIL_W), 'not the Songs asset'
    _, heads, _ = build_items()
    panels = [('Top (a library with all 27 letters: the collapsed index)', page(s, letters=ALL_LETTERS)),
              ('Finger on M (no drawn letter): bubble', page(s, scroll=heads['M'], touched='M', letters=ALL_LETTERS)),
              ('"...": the card (Select, the order: Title, A–Z); Search | ... | Now Playing', page(s, menu=True)),
              ('Sort card: Recently Added, Oldest First', page(s, menu=True, order=(3, True))),
              ('Select button: marks, Add to Playlist / Delete', page(s, scroll=heads['C'] - 8, select={'Creep', '春よ、来い'})),
              ('End of the list: Y (a CJK title by pinyin), the song count', page(s, scroll=10 ** 6)),
              ('Favorites: Search | Select | Now Playing', page(s, title=tr(s, 'Favorites'), direct=True)),
              ('A playlist: the header', page(s, title='Late Night Drive: Songs for the Long Way Home', head=True, search=False, direct=True)),
              ('A playlist in Edit: the check, the pencil, the handles, Delete | +', page(s, title='Late Night Drive', head=True, search=False, direct=True, select={'Creep'}, edit=True)),
              ('Add Songs (Edit\'s +): the check, "Add to ...", a plus or a tick on every row, the rail', page(s, letters=ALL_LETTERS, pick=({'Creep', '春よ、来い'}, 'Late Night Drive'))),
              ('An empty playlist (just made): the header and the Add Songs row', empty_page(s, 'Late Night Drive')),
              ('A playlist, past the name', page(s, scroll=260, title='Late Night Drive: Songs for the Long Way Home', head=True, search=False, direct=True)),
              ('A playlist\'s end: the song count', page(s, scroll=10 ** 6, title='Late Night Drive: Songs for the Long Way Home', head=True, search=False, direct=True)),
              ('A genre\'s songs, scrolled: Select | Now Playing (no card)', page(s, scroll=200, title='Alternative & Punk', search=False, direct=True)),
              ('Recently Added: the card (Select, Albums / Songs)', page(s, title=tr(s, 'Recently Added'), menu='recent')),
              ('An artist\'s songs, scrolled: Cover Flow | Select | Now Playing', page(s, scroll=200, title='Miles Davis', artist=True, direct=True))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()

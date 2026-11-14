#!/usr/bin/env python3
"""The Settings pages' layout model (tools/pod_pages.py cards pages, docs/modules/settings.md "Cards"): iOS-style grouped cards in the stock list.

tools/pod_ui.py builds the widget trees from these numbers, tools/preview/preview_settings.py draws the design from them and test/pod/settings.py checks the built
trees against them (with demo's own layouter), so the mock, the tests and the device share one set of numbers.

The stock list_view layouter ignores a child's y: it stacks every visible child of the scroll_view in child order, from y 0, setting x (0) and the width and summing the heights
into virtual_h. So the page is a column of full-width items, each as high as the model says: a CM spacer, then rows (ROW_H), headers (HDR_H), notes (NOTE_H) and gaps (GAP_H) in
the order of the page's layout, then an END_H spacer. There are no card views: a card is drawn by its rows, each of which has a picture as its background (single / top / middle /
bottom piece, ROW_W x ROW_H, tools/mod_icons.py card_piece) with the card's x CM .. CM + CARD_W, its corners (CARD_R, only where the piece needs them) and its fill baked in and
transparent outside (the pressed pieces are lit). A hairline (CARD_HAIR_RGB) is a child of the row from the label to the card's right edge, on every row but a card's last. Coordinates
below are row relative (x 0 is the list's left edge, so a card starts at CM). The 20 px glyph (GLYPH_PX in a 24 px image) is centred in a 20 px column PAD from the card's edge, the label
starts LABEL_GAP after the column (a picker row has no glyph: PAD). On the right, the ink of the chevron, the switch and the check ends PAD from the card's edge; a value is grey, 8 px
left of the chevron. A header is secondary grey and a note smaller grey text; their labels start at HDR_X, the left of the glyph column's ink.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_pages
from pod_roles import SUB_RGB, SURFACE_RGB, LINE_RGB, RAISED_RGB, CAPTION_PX, CAPTION_H, CAPTION_LABEL_Y, CAPTION_LABEL_H

ROW_H = 52                   # tools/pod_ui.py ROW_H
CM, CARD_W, CARD_R = 10, 300, 12
CARD_RGB, CARD_HAIR_RGB, PRESSED_RGB = SURFACE_RGB, LINE_RGB, RAISED_RGB   # PRESSED_RGB: a tapped row (the Songs sort card's pressed grey)
PAD, GLYPH_PX, ICON_PX, LABEL_GAP = 14, 20, 24, 14
HDR_H, HDR_PX, HDR_LABEL_Y, HDR_LABEL_H = CAPTION_H, CAPTION_PX, CAPTION_LABEL_Y, CAPTION_LABEL_H   # the group caption (pod_roles)
NOTE_H, NOTE_PX, NOTE_LABEL_Y, NOTE_LABEL_H = 34, 15, 6, 22
WRAP_LINE = 21               # a wrapping note (Note.lines > 1, a plain label): each further line adds this
GAP_H, END_H = 20, 10       # the space between two cards without a header or note; the list's bottom padding
REGION_H = 30               # the 10-Band editor's region line box (pod_regionbox): the 18 px line centred, 6 px clear above and below it, between the graph and the slider card
GRAPH_H = 170                # the preset page's graph card (patch/offsets.inc PG_H): a view the width of the list, the card (x CM, CARD_W wide, rounded) baked into the bitmap the payload paints
SEG_H, HSL_H = 58, 150       # the band page's Peak / Low shelf / High shelf control (a 40 px control with 10 px above it and 8 below: patch/offsets.inc BD_SEG_*) and its card of three 50 px slider rows (BD_HSL_*)
SLIDERS_H = 170              # the 10-Band editor's slider card (patch/offsets.inc TB_H): a view the width of the list, its card (x CM, CARD_W wide, rounded) baked into the bitmap the payload paints
LIB_ROW_H = 60               # a Presets page row (a preset file: two lines and a chevron, the mockup's 60 px); its card pieces are the tall pod_cdl_* images
PREAMP_W = 150               # the preset page's preamp row: the value's box (the longest text, "Auto - 6.0 dB", in 18 px), right aligned at RIGHT
BAND_TITLE_PX, BAND_SUB_PX = 20, 16   # a two-line row's text sizes: the Podcasts cells' title and grey line (label_ps_ctitle 20, label_ps_cdesc 16); the library rows' 21 / 18 are for 64 px rows
BAND_TITLE_Y, BAND_TITLE_H, BAND_SUB_Y, BAND_SUB_H = 5, 22, 28, 19   # a band row's two lines in the 52 px row: 5 px above the title box, 5 px below the grey line's
LIB_TITLE_Y, LIB_TITLE_H, LIB_SUB_Y, LIB_SUB_H = 8, 22, 32, 19   # a Presets page row's (LIB_ROW_H 60): the same boxes, 8 above and 9 below
BAND_GAIN_W, BAND_GAIN_GAP = 76, 4   # the gain's box (a value: VALUE_PX grey, right aligned at band_right(), centred on the row like every value row's and the chevron) and the gap before it
GREY = SUB_RGB             # headers, notes and values
VALUE_PX, VALUE_GAP, VALUE_W, VALUE_MAX, VALUE_LABEL_GAP = 18, 8, 100, 140, 6   # a value: its size, the gap to the chevron, its box at rest (right aligned), the most the payload gives it (it takes the room its text needs: patch/m1plus.c value_fit), the gap to the label
INFO_PX, INFO_W, INFO_MAX = 16, 100, 190   # an About row's value: 16 px grey, its box at rest (right aligned, ink at RIGHT), the most the payload gives it (it takes the room its text needs; the label gets the rest)
SWITCH_W, SWITCH_H = 57, 28  # the stock switch images sset_on / sset_off (their ink fills the image)
CHEV_W, CHEV_H, CHEV_RGB = 10, 16, (0x8A,) * 3   # the chevron image pod_chev: the shared list chevron (patch/common.c m1_make_chevron, mod_icons.pod_chevron)
CHEV_INSET = 12   # the chevron's left edge is this far from the card's right edge (x 288 in the 320 px row); a link's label box and a value end VALUE_GAP before it (x 280: the hscroll_label insets its text 2 px, so the text ends at 278)
CHECK_PX = 20                # the picker's check image pod_check
CURVE_W, CURVE_GAP = 112, 8   # the 10-Band EQ picker row's curve name: its box (18 px grey, right aligned: Классическая fits) and the gap to the check's ink
LIST_W = 310                 # the items' width in the asset (the scroll_view's; the layouter sets it)
ROW_W = 320                  # the pieces' width: the list_view's (the layouter gives a child that width, or the scroll_view's 310: the piece is drawn from the left edge either way)
ICON_X = CM + PAD + GLYPH_PX // 2 - ICON_PX // 2      # the 24 px image of a row's glyph: row relative
ICON_Y = (ROW_H - ICON_PX) // 2
TEXT_X = CM + PAD + GLYPH_PX + LABEL_GAP              # a row's label with a glyph; CM + PAD without
RIGHT = CM + CARD_W - PAD                             # the right ink edge of the chevron, the switch and the check, row relative
HDR_X = CM + PAD                                      # a header's and a note's label: the left of the row glyphs' ink
HDR_W = CARD_W - PAD - 4   # the text starts at the card's text; the label runs to 4 px short of the scroll bar strip (the hscroll_label insets its text 2 px each side)


TOP, END = 'top', 'end'      # the spacers the page starts and ends with (CM and END_H high)


def row_h(row):
    """A row's height: ROW_H, or LIB_ROW_H for a Presets page row."""
    return LIB_ROW_H if row.action == pod_pages.ACT_PEQ_LIB else ROW_H


def item_h(item):
    """The height of a layout item: Hdr, Note, GAP, Row or TOP / END."""
    return (HDR_H if isinstance(item, pod_pages.Hdr) else NOTE_H + (item.lines - 1) * WRAP_LINE if isinstance(item, pod_pages.Note) else GAP_H if item is pod_pages.GAP
            else REGION_H if item is pod_pages.REGION else GRAPH_H if isinstance(item, pod_pages.Graph) else SLIDERS_H if isinstance(item, pod_pages.Sliders) else SEG_H if isinstance(item, pod_pages.Segment) else ROW_H if isinstance(item, (pod_pages.Brightness, pod_pages.VolCard)) else HSL_H if isinstance(item, pod_pages.HSliders) else CM if item == TOP else END_H if item == END else row_h(item))


def layout(items):
    """(placed, end): placed = [(item, y)] for [TOP] + items + [END], the stacked column the list_view layouter makes; end = virtual_h."""
    y, placed = 0, []
    for it in [TOP] + list(items) + [END]:
        placed.append((it, y))
        y += item_h(it)
    return placed, y


def pieces(items):
    """The background piece of each row, in row order: 'single', 'top', 'mid' or 'bot' (a card is a run of rows between the other items)."""
    kinds = [isinstance(it, pod_pages.Row) for it in items]
    rows = [i for i, k in enumerate(kinds) if k]
    out = []
    for i in rows:
        up = i > 0 and kinds[i - 1]
        down = i + 1 < len(kinds) and kinds[i + 1]
        out.append('mid' if up and down else 'bot' if up else 'top' if down else 'single')
    return out


def peq_pieces(n):
    """The card pieces of the Equalizer page's picker card (10-Band EQ, then n presets), in row order: what patch/peq_ui.c sets."""
    return pieces(pod_pages.peq_items(n))[1:-2]   # (the first row is the switch's card, the last two the bottom card's: 10-Band EQ and Presets links)


def peqp_pieces(n):
    """The card pieces of the preset page's band card (n bands), in row order: what patch/peqpage.c sets (the preamp row is a single card of its own, the Rename / Delete card two rows under the bands)."""
    return pieces(pod_pages.peqp_items(n))[1:-2]


def piece_images(piece, tall=False):
    """(normal, pressed) image names of a piece: pod_cd_<piece>, pod_cd_<piece>_down; tall (a LIB_ROW_H row): pod_cdl_<piece>[_down]."""
    base = 'pod_cdl_' if tall else 'pod_cd_'
    return f'{base}{piece}', f'{base}{piece}_down'


_ink = {}


def ink(name):
    """(left, top, right, bottom) of the ink of an image of ours inside its canvas: the chevron and the check, drawn by tools/mod_icons.py."""
    if name not in _ink:
        import mod_icons as M
        im = {'chev': lambda: M.pod_chevron(CHEV_RGB), 'check': lambda: M.glyph_fit('check', CHECK_PX, CHECK_PX)}[name]()
        _ink[name] = im.getchannel('A').getbbox()
    return _ink[name]


def accessory(kind, row_h=ROW_H):
    """(x, y, w, h) of a row's right accessory, card relative, so that its ink ends at RIGHT and is centred in a row of row_h: 'chevron', 'check' (a preset's too) or 'switch'."""
    if kind == 'switch': return RIGHT - SWITCH_W, (row_h - SWITCH_H) // 2, SWITCH_W, SWITCH_H
    if kind == 'chevron': return chevron_left(), (row_h - 1 - CHEV_H) // 2, CHEV_W, CHEV_H
    name, w, h = 'check', CHECK_PX, CHECK_PX
    b = ink(name)
    return RIGHT - b[2], (row_h - (b[3] - b[1])) // 2 - b[1], w, h


def chevron_left():
    """The left edge of the chevron's image (row relative; x 288 in the 320 px row)."""
    return CM + CARD_W - CHEV_INSET - CHEV_W


def curve_box():
    """(x, w) of the Equalizer page's 10-Band EQ picker row's grey curve name (right aligned, before the check): it ends CURVE_GAP before the check's ink."""
    right = accessory('check')[0] + ink('check')[0] - CURVE_GAP
    return right - CURVE_W, CURVE_W


def label_box(kind, has_icon):
    """(x, w) of a row's label, card relative: from TEXT_X (PAD without a glyph) to the accessory, the value's box or the right ink edge."""
    x = TEXT_X if has_icon else CM + PAD
    if kind == 'info': return x, info_box()[0] - VALUE_LABEL_GAP - x
    if kind == 'preamp': return x, band_right() - PREAMP_W - VALUE_LABEL_GAP - x
    if kind == 'band': return x, band_right() - BAND_GAIN_W - BAND_GAIN_GAP - x
    if kind == 'preset': return x, accessory('check')[0] - 8 - x
    if kind == 'lib': return x, chevron_left() - 8 - x
    if kind == 'wvalue': return x, wvalue_box()[0] - VALUE_LABEL_GAP - x
    if kind in ('link', 'value'): right = chevron_left() - VALUE_GAP
    elif kind == 'switch': right = accessory('switch')[0] - 8
    elif kind == 'check': right = accessory('check')[0] - 8
    else: right = RIGHT
    if kind == 'value': right = value_box()[0] - VALUE_LABEL_GAP
    return x, right - x


def wvalue_box():
    """(x, w) of the editor's Curve and Preamp rows' grey value (right aligned, before the chevron): PREAMP_W wide, so that "Auto · −12.0 dB" and the longest curve name fit."""
    right = chevron_left() - VALUE_GAP
    return right - PREAMP_W, PREAMP_W


def band_right():
    """The right edge of the preset page's value column (a band's gain, the Preamp's value): VALUE_GAP before the chevron, as every value row's."""
    return chevron_left() - VALUE_GAP


def band_sub_box():
    """(x, w) of a band row's grey line: as its title, from the text edge to the gain's box (the gain is centred on the row, beside both lines)."""
    return CM + PAD, band_right() - BAND_GAIN_W - BAND_GAIN_GAP - (CM + PAD)


def info_box():
    """(x, w) of an About row's value box (right aligned text, no chevron): it ends at the right ink edge."""
    return RIGHT - INFO_W, INFO_W


def value_box():
    """(x, w) of a value's box (right aligned text), card relative: it ends VALUE_GAP before the chevron's ink."""
    right = chevron_left() - VALUE_GAP
    return right - VALUE_W, VALUE_W

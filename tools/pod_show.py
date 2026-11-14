#!/usr/bin/env python3
"""The Podcasts Show page's and Shows page's layout model (patch/podcasts.c, docs/modules/podcasts.md "The Show page", "The Shows page"): the PS_* and PP_* numbers of patch/offsets.inc, the line breaking of tools/pod_wrap.py
and the glyph advances of the font (tools/awtk_text.py: the glyph's width and 1 px each). test/pod/pcshow.py and test/pod/pcshows.py check the payload against it and tools/preview/preview_podcasts_revamp.py draws
from it, so the preview, the tests and the device share one set of numbers.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdefs
import pod_ui, pod_wrap
from awtk_text import Ttf, StbText

O = pod_ui.OFFSETS
PX = {name: px for name, px, _, _ in pod_ui.PS_STYLES}          # the text styles' sizes: label_ps_name 22 ...
SEP = ' · '                                                 # the " · " between the two halves of a line


class Font:
    """Widths in the font of a tree (default.ttf), per size."""
    def __init__(self, path):
        self.ttf, self._st = Ttf(path), {}

    def width(self, text, px):
        st = self._st.get(px)
        if st is None: st = self._st[px] = StbText(self.ttf, px)
        return round(st.layout(text)[1]) if text else 0


def lines(font, text, style, room, maxl):
    """The lines of text in a style label (label_ps_*), room px wide, at most maxl."""
    return pod_wrap.wrap_font(font, text, PX[style], room, maxl) if text else []


def meta(category, author):
    return SEP.join(p for p in (category, author) if p)


def header(font, title, desc='', category='', author='', has_latest=True):
    """The Show header's layout (patch/podcasts.c pg_hdr_make): the wrapped texts and the blocks' tops, content y from the list's top."""
    o, h = O, {}
    y = o['PS_ART'] + o['PS_NAME_GAP']
    h['name'] = lines(font, title, 'label_ps_name', o['PS_NAME_W'], o['PS_NAME_LINES'])
    h['y_name'] = y
    y += len(h['name']) * o['PS_NAME_PITCH']
    h['collapse'] = y - o['PS_COLLAPSE_BACK']
    gap = o['PS_LATEST_GAP']
    h['has_latest'] = has_latest
    if has_latest:
        y += o['PS_LATEST_GAP']; h['y_latest'] = y; y += o['PS_LATEST_H']; gap = o['PS_DESC_GAP']
    h['desc'] = lines(font, desc, 'label_ps_sec', o['PS_DESC_W'], o['PS_DESC_LINES'])
    if h['desc']:
        y += gap; h['y_desc'] = y; y += len(h['desc']) * o['PS_DESC_PITCH']; gap = o['PS_META_GAP']
    h['meta'] = lines(font, meta(category, author), 'label_ps_meta', o['PS_DESC_W'], 1)
    if h['meta']:
        y += gap; h['y_meta'] = y; y += o['PS_META_PITCH']
    y += o['PS_HEAD_GAP']
    h['y_head'] = y
    h['h'] = y + o['PS_HEAD_H']
    return h


def pill_width(font, label):
    """A cell's state pill: pad, the 16 px glyph, gap, the label, pad."""
    o = O
    return o['PS_PILL_PADL'] + o['PA_G_PX'] + o['PS_PILL_GAP'] + font.width(label, PX['label_ps_pill']) + o['PS_PILL_PADR']


def latest_label(font, label, white):
    """The Latest Episode pill's label as the payload keeps it: cut with an ellipsis to fit PS_LATEST_MAX."""
    o = O
    style = 'label_ps_latest' if white else 'label_ps_latestw'
    room = o['PS_LATEST_MAX'] - o['PS_LATEST_PADL'] - o['PS_LATEST_GLYPH'] - o['PS_LATEST_GAPG'] - o['PS_LATEST_PADR']
    got = lines(font, label, style, room, 1)
    return got[0] if got else ''


def latest_width(font, label, white):
    o = O
    return o['PS_LATEST_PADL'] + o['PS_LATEST_GLYPH'] + o['PS_LATEST_GAPG'] + font.width(latest_label(font, label, white), PX['label_ps_latest' if white else 'label_ps_latestw']) + o['PS_LATEST_PADR']


def cell(font, title, desc, sx=0):
    """A cell's wrapped title and description (two lines each at most, PS_CELL_W less the select column sx)."""
    room = O['PS_CELL_W'] - sx
    return lines(font, title, 'label_ps_ctitle', room, 2), lines(font, desc, 'label_ps_cdesc', room, 2)


def content_height(h_hdr, n, select=False, more=False):
    """The content's height: the header, n cells, the See All row (more: a subscribed show with no archive) and the air under the last (PG_BOTTOM 20), and the select bar's room."""
    return h_hdr + n * O['PS_CELL_H'] + 20 + (O['PS_MORE_H'] if more and n and not select else 0) + (O['SG_BAR_H'] if select and n else 0)


def font_path(work):
    return os.path.join(work, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf')


# ---------------------------------------------------------------------------
# The Shows page (round 2; patch/podcasts.c pg_home_layout, pg_paint_home): the blocks' tops and the cells' boxes, content y from the list's top.

def shows_layout(n_shows, has_line, n_cont, discover=True):
    """The Shows level's layout: where each block starts (0 when it is not there), the grid's top and the content's height. The Library rows close the page, PP_LIB_GAP under the grid: Discover (while Podcast Discover is on, `discover`), Downloads, Subscriptions while a show has a feed
    (has_line: the refresh line shows under the same condition), then Saved."""
    o = O
    L = dict(y_line=o['PP_LINE_Y'] if has_line else 0, y_shelf=0, y_srch=0, y_sub=0)
    y = o['PP_LINE_Y'] + (o['PP_LINE_PITCH'] if has_line else o['PP_NOLINE_PITCH'])
    if n_cont:
        L['y_shelf'] = y
        y += o['PP_HEAD_PITCH'] + o['PP_SHELF_PITCH_Y'] + o['PP_SEC_GAP']
    L['y_shows'] = y
    y += o['PP_HEAD_PITCH']
    L['y_grid'] = y
    y += (min(n_shows, o['PP_SHOWS_MAX']) + o['GRID_COLS'] - 1) // o['GRID_COLS'] * grid_pitch()
    L['y_all'] = 0
    if n_shows > o['PP_SHOWS_MAX']:   # the See All row (the All Shows page) in place of the gap
        L['y_all'] = y
        y += o['PS_MORE_H']
    else:
        y += o['PP_LIB_GAP'] if n_shows else 0
    if discover:
        L['y_srch'] = y
        y += o['PC_ROW_H']
    L['y_dl'] = y
    y += o['PC_ROW_H']
    if has_line:
        L['y_sub'] = y
        y += o['PC_ROW_H']
    L['y_sav'] = y
    y += o['PC_ROW_H']
    L['h'] = y + o['PP_BOTTOM']
    return L


def downloads_layout(n_ip, n_dl, select=False):
    """The Downloaded page's layout (patch/podcasts.c pg_dy, pg_dh): the storage line, the In Progress header and rows, PP_SEC_GAP, the downloaded rows, content y from the list's top; the In Progress header's top
    (None unless both sections have rows: the downloaded rows have no header, the page's title "Downloaded" is theirs, and In Progress alone needs none; the rows then start where the header would have), each row's top (In Progress
    then downloaded) and the content's height (the select bar's room too)."""
    o = O
    y, rows, y_ip = o['PDL_LINE_PITCH'], [], None
    heads = bool(n_ip and n_dl)
    if n_ip:
        if heads: y_ip = y; y += o['PP_HEAD_PITCH']
        rows += [y + i * o['PC_ROW_H'] for i in range(n_ip)]
        y += n_ip * o['PC_ROW_H'] + o['PP_SEC_GAP']
    if n_dl:
        rows += [y + i * o['PC_ROW_H'] for i in range(n_dl)]
    return dict(y_line=o['PDL_LINE_Y'], y_ip=y_ip, rows=rows, h=(rows[-1] + o['PC_ROW_H'] + o['PP_BOTTOM'] if rows else o['PDL_LINE_PITCH']) + (o['SG_BAR_H'] if select and rows else 0))


def grid_pitch():
    """Row to row of the Albums grid: the cover, the gap, the title, the grey line and the row gap."""
    o = O
    return o['GRID_COVER'] + o['GRID_TITLE_GAP'] + o['GRID_TITLE_H'] + o['GRID_SUB_H'] + o['GRID_ROW_GAP']


def grid_cell(i, y_grid):
    """Show i's cell: (x of the cover, y of the cover, y of the title box, y of the grey line's box)."""
    o = O
    x = o['GRID_MARGIN'] + i % o['GRID_COLS'] * (o['GRID_COVER'] + o['GRID_GAP'])
    y = y_grid + i // o['GRID_COLS'] * grid_pitch()
    ty = y + o['GRID_COVER'] + o['GRID_TITLE_GAP']
    return x, y, ty, ty + o['GRID_TITLE_H']


def shelf_play(i, y_shelf):
    """Continue Listening item i's play disc (x, y of its top left): PA_PLAYB_PX px, PP_SHELF_PLAY_INSET from the cover's right and bottom edges."""
    o = O
    x, y = shelf_item(i, y_shelf)[:2]
    d = o['PP_SHELF_ART'] - o['PP_SHELF_PLAY_INSET'] - o['PA_PLAYB_PX']
    return x + d, y + d


def shelf_item(i, y_shelf):
    """Continue Listening item i: (x, y of the cover, y of the title box, y of the "left" box); the cover is PP_SHELF_ART px."""
    o = O
    x, y = o['PP_SHELF_X'] + i * o['PP_SHELF_PITCH'], y_shelf + o['PP_HEAD_PITCH']
    return x, y, y + o['PP_SHELF_TITLE_Y'], y + o['PP_SHELF_LEFT_Y']


def hint_layout(top, widths, busy=False, more=False):
    """An empty page's hint and the Discover / search status line (patch/podcasts.c pg_hint_at, pg_paint_hint; docs/modules/podcasts.md "The hint"): the wrapped lines (widths: each line's px, at most four)
    are centred as a block in the room under the header (content y top): down to the view's bottom (GRID_VIEW_H) when the header leaves more than the four lines' room (PG_HINT_H = 8 + 4 lines), else that
    room; with the See All row under the hint (more) always that room. Each line is centred across the page; a busy line (Loading…, Searching…) has the 14 px spinner and its gap before the first line,
    the two centred as one group. h: the content's height without the See All row, lines: [(x, y)], spin: (x, y) or None."""
    o = O
    pitch, room = o['PS_TITLE_PITCH'], 8 + 4 * o['PS_TITLE_PITCH']
    bottom = top + room if more else max(top + room, o['GRID_VIEW_H'])
    y0 = top + (bottom - top - len(widths) * pitch) // 2
    sx = o['PS_SPIN_PX'] + o['PS_SPIN_GAP'] if busy else 0
    lines = [((pod_ui.SCREEN_W - sx - w) // 2 + sx, y0 + k * pitch) for k, w in enumerate(widths)]
    return dict(h=bottom, lines=lines, spin=(lines[0][0] - sx, y0 + (pitch - o['PS_SPIN_PX']) // 2) if busy and lines else None)


def search_layout(n):
    """The search level of the Podcasts page (docs/modules/podcasts.md "Search") with n result rows: the field's rectangle, where the rows start, each row's top, the content's height."""
    o = O
    top = o['PQ_TOP']
    return dict(field=(o['PQ_FIELD_X'], o['PQ_FIELD_Y'], o['PQ_FIELD_W'], o['PQ_FIELD_H']), top=top,
                rows=[top + i * o['PC_ROW_H'] for i in range(n)], h=top + n * o['PC_ROW_H'] + o['PQ_BOTTOM'] if n else hint_layout(top, [0])['h'], hint_y=hint_layout(top, [0])['lines'][0][1])


def capsule(x, y, w, h, r, c):
    """The rectangles patch/common.c m1_capsule fills for a capsule w x h at (x, y), corner radius r (at most half the height), colour c (a color_t word): [(colour, x, y, w, h)]. Each corner row is inset by the circle's chord on the
    row's middle, in 1/256 px; the pixel at the end is lit by what the circle leaves of it (the colour's alpha scaled by 255 - the fraction), the rows between the corners are one fill."""
    import math
    r = max(0, min(r, h // 2, w // 2))
    out = []
    for i in range(r):
        dy = 2 * (r - i) - 1
        u = math.isqrt((4 * r * r - dy * dy) << 16)
        inset = r * 256 - u // 2
        x0, f = inset >> 8, inset & 255
        rows = (y + i, y + h - 1 - i)
        if f:
            edge = (c & 0x00ffffff) | (((c >> 24) * (255 - f) // 255) << 24)
            for yy in rows: out += [(edge, x + x0, yy, 1, 1), (edge, x + w - 1 - x0, yy, 1, 1)]
            x0 += 1
        for yy in rows: out.append((c, x + x0, yy, w - 2 * x0, 1))
    if h - 2 * r > 0: out.append((c, x, y + r, w, h - 2 * r))
    return out


def segmented(x, y, w, h, n, sel):
    """The segmented control patch/common.c m1_segmented paints (docs/modules/ui-rules.md "Segmented control"): the track and the thumb as (x, y, w, h, radius), the hairlines between unselected segments (x, y, w, h), and each
    segment's box (x, w). Colours are SEG_TRACK, SEG_THUMB and SEG_SEP of patch/offsets.inc."""
    o, pad = O, O['SEG_PAD']
    seg = (w - 2 * pad) // n
    thumb = (x + pad + sel * seg, y + pad, (w - 2 * pad - sel * seg) if sel == n - 1 else seg, h - 2 * pad, (h - 2 * pad) // 2)
    seps = [(x + pad + k * seg, y + h // 4, 1, h // 2) for k in range(1, n) if k - 1 != sel and k != sel]
    return dict(track=(x, y, w, h, h // 2), thumb=thumb, seps=seps, segs=[(x + pad + k * seg, seg) for k in range(n)], label_h=o['SEG_LABEL_H'])


def discover_layout(n):
    """The Discover level of the Podcasts page (docs/modules/podcasts.md "Discover") with n chart rows: the grey line's top, the Shows | Episodes control's rectangle (segmented(): the track and the thumb of each selection), where the rows
    start, each row's top, the content's height (with no rows: the status text's room, hint_layout), and the rank / cover / text columns (the list painter shifted DC_SHIFT right)."""
    o = O
    seg = (o['DC_SEG_X'], o['DC_SEG_Y'], o['DC_SEG_W'], o['DC_SEG_H'])
    top = o['DC_TOP']
    return dict(line_y=o['PDL_LINE_Y'], seg=seg, sel=[segmented(*seg, 2, k) for k in range(2)], top=top, rows=[top + i * o['PC_ROW_H'] for i in range(n)],
                h=top + n * o['PC_ROW_H'] + o['DC_BOTTOM'] if n else hint_layout(top, [0])['h'], hint_y=hint_layout(top, [0])['lines'][0][1], rank_end=o['DC_RANK_END'],
                art_x=o['LIST_ART_X'] + o['DC_SHIFT'], text_x=o['LIST_TEXT_X'] + o['DC_SHIFT'], text_end=o['LIST_TEXT_X'] + o['LIST_TEXT_W_CHEV'], chev_x=o['LIST_CHEV_X'])


def subscribe_pill(font, text):
    """The preview's Subscribe / Subscribed pill: (width, x of the text inside it): the label's width plus the Latest Episode pill's paddings, at least PQ_SUB_MIN, the text centred."""
    o = O
    tw = font.width(text, PX['label_ps_latest'])
    w = max(o['PS_LATEST_PADL'] + tw + o['PS_LATEST_PADR'], o['PQ_SUB_MIN'])
    return w, (w - tw) // 2


# ---------------------------------------------------------------------------
# The episode page (patch/pcdetail.c, docs/modules/podcasts.md "The episode page"): the PD_* numbers of patch/pcdetail.h and the layout of pd_make in Python.

PD = cdefs.defines(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patch', 'pcdetail.h'))


def detail_date(when, length, mb='%d MB'):
    """The date line (pd_date): "Oct 28 · 48 MB", English words; the size is left out when it is unknown, the date when there is none."""
    size = mb % ((length + 1048575) >> 20) if length else ''
    return ' · '.join(x for x in (when, size) if x)


def detail_layout(font, title, show, desc, hint='No description', has_pill=True):
    """The episode page's layout (pd_make): the date line's top, the title's lines, the show row's top and the show's name cut to its room, the pill row's top and each description line as (text, y); h is the
    content's height. desc: paragraphs separated by newlines ('' shows the hint, in the grey line's style)."""
    p = PD
    L = {}
    y = p['PD_TOP']
    L['y_date'] = y
    y += p['PD_DATE_H'] + p['PD_GAP_DATE']
    L['y_title'] = y
    L['title'] = lines(font, title, 'label_ps_head', p['PD_W'], p['PD_TITLE_LINES'])
    y += len(L['title']) * p['PD_TITLE_PITCH'] + p['PD_GAP_TITLE']
    L['y_show'] = y
    got = lines(font, show, 'label_ps_meta', p['PD_SHOW_TEXT_W'], 1)
    L['show'] = got[0] if got else ''
    y += p['PD_SHOW_H'] + p['PD_GAP_SHOW']
    L['y_pill'] = 0
    if has_pill:
        L['y_pill'] = y
        y += p['PD_PILL_ROW'] + p['PD_GAP_PILL']
    L['y_desc'] = y
    style = 'label_ps_sec' if desc else 'label_ps_meta'
    L['hint'] = not desc
    out, para, n = [], False, 0
    for par in (desc or hint).split('\n'):
        if not par or n >= p['PD_LINES']: continue
        ls = lines(font, par, style, p['PD_W'], p['PD_LINES'] - n)
        if para: y += p['PD_PGAP']
        for t in ls:
            out.append((t, y)); y += p['PD_PITCH']
        n += len(ls); para = True
    L['desc'] = out
    L['h'] = y + p['PD_BOTTOM']
    return L

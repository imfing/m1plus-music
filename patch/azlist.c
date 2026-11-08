/* The A-Z list furniture shared by the Songs page and the Artists page (patch/azlist.h has the design).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Moved from patch/songs.c; the comments that say why are docs/modules/songs.md's (the rail's alignment and evidence).
 */
#include "offsets.inc"
#include "stock.h"
#include "scroll.h"
#include "common.h"
#include "azlist.h"

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

#define SG_RANKS 27
#if SG_MAX_SEC < SG_RANKS
#error a section per rank does not fit
#endif

int az_rank_of(int c) {
    if (c >= 'a' && c <= 'z') c -= 32;
    return c >= 'A' && c <= 'Z' ? c - 'A' + 1 : 0;
}

unsigned char az_rank_letter(int r) { return r > 0 ? (unsigned char)('A' + r - 1) : '#'; }

/* The sections of the stock Title order. It sorts by the whole title (toolsQueryDbTable's comparator) and the Initial is the scan's first surviving character, so the
 * two only roughly agree (a symbol that sorts after 'z', an accented letter, a dropped kana, a CJK title placed by its whole pinyin): the songs are not in runs of
 * equal letters (V2.1oGS made a section per run and fell back to a plain list over SG_MAX_SEC runs: on the device no headers, no rail). The list keeps the stock
 * order (the play queue), so the sections are the non-decreasing labelling of the songs that puts the most of them under their own letter: a stray stays in the
 * section around it and cannot open one early. One pass forward keeps m[r] = the most songs labelled correctly so far with a last label <= r and, per song, a
 * bit per rank that says the best for r came from a lower label; one pass back reads the labels off; a section starts where the label changes. 4 bytes per
 * song, for the duration of the call; no memory = a plain list. At most SG_RANKS sections. */
void az_sections(az_t *az, const unsigned char *rank, unsigned stride) {
    unsigned *bits = calloc((unsigned)az->count, sizeof(unsigned)), i, b, n = (unsigned)az->count;
    int m[SG_RANKS], r, d, k, lab = SG_RANKS - 1, prev = -1;
    az->nsec = 0;
    if (!bits) return;
    for (r = 0; r < SG_RANKS; ++r) m[r] = 0;
    for (i = 0; i < n; ++i) {
        for (b = 0, k = rank[i * stride], r = 0; r < SG_RANKS;
             ++r) { /* m[r] still holds the previous song's value, m[r - 1] already this song's */
            d = m[r] + (r == k);
            if (r && m[r - 1] >= d)
                m[r] = m[r - 1], b |= 1u << r; /* a tie takes the lower label: a section starts as late as it can */
            else
                m[r] = d;
        }
        bits[i] = b;
    }
    for (i = n; i-- > 0;) {
        while (lab && (bits[i] >> lab & 1)) --lab;
        bits[i] = (unsigned)lab;
    }
    for (i = 0; i < n; ++i)
        if ((int)bits[i] != prev)
            prev = (int)bits[i], az->sec_start[az->nsec] = i, az->sec_letter[az->nsec++] = az_rank_letter(prev);
    free(bits);
}

/* ---------------------------------------------------------------------------
 * Geometry. The rows (and the headers, with sections) start at az->top; section s's header is at az_hdr_y(s), its rows follow.
 */
int az_off(const az_t *az) { return az->sv ? I(az->sv, SC_YOFF) : 0; }

int az_hdr_y(const az_t *az, int s) { return az->top + s * SG_HDR_H + (int)az->sec_start[s] * az->row; }

int az_sec_of(const az_t *az, int i) {
    int s = az->nsec - 1;
    while (s > 0 && (int)az->sec_start[s] > i) --s;
    return s;
}

int az_row_y(const az_t *az, int i) {
    return az->top + (az->nsec ? (az_sec_of(az, i) + 1) * SG_HDR_H : 0) + i * az->row;
}
int az_rows_end(const az_t *az) { return az->top + az->nsec * SG_HDR_H + az->count * az->row; }

int az_max_scroll(const az_t *az) {
    int m = az->content - (az->view_h > 0 ? az->view_h : GRID_VIEW_H);
    return m > 0 ? m : 0;
}

int az_row_from(const az_t *az, int y) {
    int s, i;
    if (!az->count) return 0;
    if (y < az->top) return 0;
    if (!az->nsec)
        i = (y - az->top) / az->row;
    else {
        s = az->nsec - 1;
        while (s > 0 && az_hdr_y(az, s) > y) --s;
        i = y < az_hdr_y(az, s) + SG_HDR_H ? (int)az->sec_start[s]
                                           : (int)az->sec_start[s] + (y - az_hdr_y(az, s) - SG_HDR_H) / az->row;
    }
    return i > az->count - 1 ? az->count - 1 : i;
}

int az_at(const az_t *az, int y) {
    int i;
    if (y < az->top || !az->count) return -1;
    i = az_row_from(az, y);
    return y >= az_row_y(az, i) && y < az_row_y(az, i) + az->row ? i : -1;
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none), inside [0, count - 1] also while a drag pulls the list past an end. */
void az_span(const az_t *az, int *r0, int *r1) {
    int s = az_off(az), n = az->count;
    *r0 = az_row_from(az, s < 0 ? 0 : s);
    *r1 = az_row_from(az, s + GRID_VIEW_H - 1);
    if (n && az_row_y(az, *r1) > s + GRID_VIEW_H - 1)
        --*r1; /* the last pixel is in a header: the row after it is not in view */
    if (n && az_row_y(az, *r0) + az->row <= s) ++*r0;
    if (*r1 > n - 1) *r1 = n - 1;
    if (*r0 < 0) *r0 = 0;
}

/* ---------------------------------------------------------------------------
 * Paint: coordinates are the window's (its top is 0): the scroll_view has moved the canvas up by yoffset, which the page's paint adds back (CANVAS_OY).
 */
void az_fill_h(void *canvas, int x, int y0, int y1, int w, unsigned c, int view_h) {
    if (y0 < 0) y0 = 0;
    if (y1 > view_h) y1 = view_h;
    if (y1 <= y0) return;
    ui_fill_color(canvas, c);
    canvas_fill_rect(canvas, x, y0, w, y1 - y0);
}

void az_fill(void *canvas, int x, int y0, int y1, int w, unsigned c) {
    az_fill_h(canvas, x, y0, y1, w, c, GRID_VIEW_H);
}

/* The header letter of section s with its top at window y (only when it lies wholly inside the window, as every text). */
static void az_letter_text(const az_t *az, void *canvas, int s, int y) {
    unsigned w[2];
    int rect[4];
    if (y < 0 || y + SG_HDR_H > GRID_VIEW_H) return;
    w[0] = az->sec_letter[s], w[1] = 0;
    rect[0] = SG_HDR_X, rect[1] = y, rect[2] = 100, rect[3] = SG_HDR_H - 1;
    canvas_draw_text_in_rect(canvas, w, 1, rect);
}

/* The pinned header: the section the window's top is in, at the top; the next header, as it arrives, pushes it up. Returns its section (-1 for none)
 * and the y of its band (<= 0). */
static int az_pinned(const az_t *az, int *y) {
    int s = az_off(az), k = az->nsec - 1;
    if (!az->nsec) return -1;
    while (k >= 0 && az_hdr_y(az, k) > s) --k;
    if (k < 0) return -1;
    *y = k + 1 < az->nsec && az_hdr_y(az, k + 1) - s < SG_HDR_H ? az_hdr_y(az, k + 1) - s - SG_HDR_H : 0;
    return k;
}

/* The letters of the headers, then the pinned band (the page's black over the rows scrolling under it: the headers in the flow have no band) and its letter. */
void az_paint_heads(az_t *az, void *canvas) {
    int s, pin, py, off = az_off(az);
    if (!az->nsec) return;
    widget_prepare_text_style(az->st_hdr, canvas);
    for (s = 0; s < az->nsec; ++s) az_letter_text(az, canvas, s, az_hdr_y(az, s) - off);
    pin = az_pinned(az, &py); /* over everything: the pinned band and its letter */
    if (pin >= 0) {
        az_fill(canvas, 0, py, py + SG_HDR_H, 320, SG_HDR_BG);
        az_letter_text(az, canvas, pin, py);
    }
}

/* ---------------------------------------------------------------------------
 * The rail
 */
void az_redraw_rail(const az_t *az) { widget_invalidate_force(az->rail, (void *)0); }

/* The rail's plan (the stock page's index shows A F K P U Z with two dots between: an image, search_icon.png): the letters it draws, as section numbers in sec[],
 * and how many (the return). At most SG_RAIL_ITEMS items fit: the sections' own letters when there are that few, else every k-th section (k from 2 up, until the
 * letters with a dot between each pair fit) with the first and the last always there (a multiple of k within half a step of the last gives way to it). A rail with
 * fewer letters than sections (the return < az->nsec) has a dot between two letters: item 2j is letter j, item 2j + 1 a dot. */
int az_rail_plan(const az_t *az, int *sec) {
    int n = az->nsec, k, m, i;
    if (n <= SG_RAIL_ITEMS) {
        for (i = 0; i < n; ++i) sec[i] = i;
        return n;
    }
    for (k = 2;; ++k) {
        for (m = 0, i = 0; i < n - 1; i += k) sec[m++] = i;
        if (m > 1 && n - 1 - sec[m - 1] < (k + 1) / 2) --m;
        sec[m++] = n - 1;
        if (2 * m - 1 <= SG_RAIL_ITEMS) return m;
    }
}

int az_rail_span(const az_t *az, int letters) {
    return (letters < az->nsec ? 2 * letters - 1 : letters) * SG_RAIL_PITCH;
} /* the drawn height */

static void az_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The rail widget is the drawn span plus SG_RAIL_PAD above and below, centred on the list of rail_h px (the bar of select mode leaves less than the window; a touch
 * further from the span reaches the rows, and the wide column takes none of the rows' right edge or the pills outside it); inside it the span starts at
 * SG_RAIL_PAD. There only when there are sections. */
void az_rail_fit(az_t *az, int rail_h) {
    int sec[SG_MAX_SEC], span;
    if (az->nsec > 0) {
        span = az_rail_span(az, az_rail_plan(az, sec));
        widget_move(az->rail, SG_RAIL_X,
                    (az->rail_origin ? az->rail_origin : SG_LIST_Y) + (rail_h - span) / 2 - SG_RAIL_PAD);
        widget_resize(az->rail, SG_RAIL_W, span + 2 * SG_RAIL_PAD);
    }
    az_show(az->rail, az->nsec > 0 && az->count);
    az_redraw_rail(az);
}

static void az_bubble(az_t *az, int i) { /* the bubble shows section i's letter, or hides */
    char s[2];
    if (i < 0) {
        widget_set_visible(az->bubble, 0, 0);
        return;
    }
    s[0] = (char)az->sec_letter[i], s[1] = 0;
    widget_set_text_utf8(az->bubble_letter, s);
    widget_set_visible(az->bubble, 1, 0);
}

/* Section i's header at the window's top (clamped); a coasting list stops first. */
static void az_jump(az_t *az, int i) {
    int v = az->rail_only ? az->top + (int)az->sec_start[i] * az->row
            : i           ? az_hdr_y(az, i)
                          : 0,
        max = az_max_scroll(az); /* (the first section: the top, the large title and the pills with it) */
    void *wa = P(az->sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING && P(wa, SC_AN_WIDGET) == az->sv) { /* patch/scroll.c sc_down */
        widget_animator_destroy(wa);
        stock_scroll_done(az->sv, (void *)0);
    }
    widget_set_prop_int(az->sv, "yoffset", v > max ? max : v);
}

static void az_rail_set(az_t *az, int i) {
    if (i == az->rail_i && az->rail_on) return;
    az->rail_i = i;
    az->rail_on = 1;
    az_jump(az, i);
    az_bubble(az, i);
    az_redraw_rail(az);
}

void az_rail_end(az_t *az) {
    if (!az->grab) return;
    az->grab = az->rail_on = 0;
    widget_ungrab(az->win, az->rail);
    az_bubble(az, -1);
    az_redraw_rail(az);
}

/* DOWN grabs the touch (the moves and the release come here wherever they go), every position sets the letter under it (above the first and below the last: those). */
void az_rail_event(az_t *az, void *e) {
    int type, pt[2], i, l, sec[SG_MAX_SEC];
    if (!e || !az->nsec) return;
    type = I(e, 0);
    if (type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) {
        az_rail_end(az);
        return;
    }
    if (type == EVT_POINTER_DOWN) {
        if (!az->grab) widget_grab(az->win, az->rail);
        az->grab = 1, az->rail_on = 0; /* a new touch: its first letter always sets */
    } else if (!az->grab)
        return;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(az->rail, pt);
    l = az_rail_plan(
        az,
        sec); /* the drawn span, however many letters it shows, is split into the sections: every one is reachable */
    i = pt[1] < SG_RAIL_PAD ? 0
                            : (pt[1] - SG_RAIL_PAD) * az->nsec /
                                  az_rail_span(az, l); /* (the span starts SG_RAIL_PAD down the widget) */
    if (i > az->nsec - 1) i = az->nsec - 1;
    az_rail_set(az, i);
}

/* Alignment (tools/pod_ui.py rail_metrics derives the two numbers from the tree's own font and pod.py writes them to stock.h):
 * vertically the 12 px text box of a 13 px item sits at its top and the baseline int(ascender * scale) lower, so the cap ink centre is SG_RAIL_INK2 / 2 below the
 * item's top; a dot goes where the midpoint of two letters' ink centres is (one item below the upper letter's centre: the letters are two items apart), so its top is
 * (INK2 - DOT) / 2 into its item, and the disc is centred on the same line. Horizontally canvas_draw_text_in_rect puts a text of measured width lw (the truncated
 * advances + 1 px per glyph) at rect.x + (rect.w - lw) / 2, integer: so the rect is SG_RAIL_TEXT_W wide, centred on the dots' x and moved by the letter's own
 * SG_RAIL_DX so the ink (not the advance) is centred on that x within half a pixel. */
static const signed char az_rail_dx[27] = SG_RAIL_DX; /* "#", A..Z */
#define SG_RAIL_DOT_Y ((SG_RAIL_INK2 - SG_RAIL_DOT) / 2)
#define SG_RAIL_DISC_Y \
    (-((SG_RAIL_DISC - SG_RAIL_INK2 + 1) / 2)) /* floor((INK2 - DISC) / 2), negative: the disc starts above the item */

/* The rail (its own EVT_AFTER_PAINT, the rail's coordinates, the span from SG_RAIL_PAD): the plan's letters, a dot between two of them when the plan skips sections,
 * the touched letter (when it is a drawn one) on its disc with a black letter. */
void az_rail_paint(az_t *az, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int j, k, l, y0 = SG_RAIL_PAD, step, dots, pass, rect[4], sec[SG_MAX_SEC];
    unsigned w[2];
    if (!canvas || !az->nsec) return;
    l = az_rail_plan(az, sec);
    dots = l < az->nsec;
    step = dots ? 2 : 1; /* the items a letter takes with the dot after it */
    if (dots) {
        int x = SG_RAIL_CX - SG_RAIL_X - SG_RAIL_DOT / 2;
        ui_fill_color(canvas, SG_RAIL_DOT_RGB);
        for (j = 0; j + 1 < l; ++j) { /* a dot of four pixels: the cross of two bars cuts its corners */
            int y = y0 + (step * j + 1) * SG_RAIL_PITCH + SG_RAIL_DOT_Y;
            canvas_fill_rect(canvas, x, y + 1, SG_RAIL_DOT, SG_RAIL_DOT - 2);
            canvas_fill_rect(canvas, x + 1, y, SG_RAIL_DOT - 2, SG_RAIL_DOT);
        }
    }
    if (az->rail_on && az->disc) {
        for (j = 0; j < l; ++j) {
            if (sec[j] == az->rail_i) {
                int src[4], dst[4];
                src[0] = src[1] = 0, src[2] = src[3] = SG_RAIL_DISC;
                dst[0] = SG_RAIL_CX - SG_RAIL_X - SG_RAIL_DISC / 2,
                dst[1] = y0 + step * j * SG_RAIL_PITCH + SG_RAIL_DISC_Y, dst[2] = dst[3] = SG_RAIL_DISC;
                canvas_draw_image(canvas, az->disc, src, dst);
            }
        }
    }
    for (pass = 0; pass < 2; ++pass) { /* the others, then the touched one (black) */
        if (pass && !az->rail_on) break;
        widget_prepare_text_style(pass ? az->st_rail_on : az->st_rail, canvas);
        for (j = 0; j < l; ++j) {
            if ((sec[j] == az->rail_i && az->rail_on) != pass) continue;
            w[0] = az->sec_letter[sec[j]], w[1] = 0;
            k = w[0] >= 'A' && w[0] <= 'Z' ? (int)w[0] - 'A' + 1 : 0;
            rect[0] = SG_RAIL_CX - SG_RAIL_X - SG_RAIL_TEXT_W / 2 + az_rail_dx[k],
            rect[1] = y0 + step * j * SG_RAIL_PITCH, rect[2] = SG_RAIL_TEXT_W, rect[3] = SG_RAIL_PITCH;
            canvas_draw_text_in_rect(canvas, w, 1, rect);
        }
    }
}

/* The disc: SG_RAIL_DISC px, the accent colour, four corners of radius SG_RAIL_DISC / 2 cut in the alpha (a disc). */
void az_make_disc(az_t *az) {
    unsigned char tab[(SG_RAIL_DISC / 2) * (SG_RAIL_DISC / 2)];
    unsigned *px;
    unsigned x, y, k, r = SG_RAIL_DISC / 2;
    void *b = bitmap_create_ex(SG_RAIL_DISC, SG_RAIL_DISC, SG_RAIL_DISC * 4, BITMAP_RGBA8888);
    if (!b) return;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != SG_RAIL_DISC * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return;
    }
    pod_corner_fill(tab, r);
    for (y = 0; y < SG_RAIL_DISC * SG_RAIL_DISC; ++y) px[y] = SG_ACCENT;
    for (k = 0; k < 4; ++k)
        for (y = 0; y < r; ++y)
            for (x = 0; x < r; ++x) {
                unsigned *p = px + (k & 2 ? 2 * r - 1 - y : y) * 2 * r + (k & 1 ? 2 * r - 1 - x : x);
                *p = (*p & 0xffffff) | (255u - tab[y * r + x]) << 24;
            }
    bitmap_unlock_buffer(b);
    az->disc = b;
}

void az_free(az_t *az) {
    if (az->disc) bitmap_destroy(az->disc);
    az->disc = (void *)0;
}

/* ---------------------------------------------------------------------------
 * Titles cut to their label
 */
int az_text_w(void *w, const unsigned *t) { return (int)(widget_measure_text(w, t) + 0.999f); }

/* The UTF-8 text on label w, cut with an ellipsis to the label's width, measured in its own style (grid_fit's rule: the longest prefix that fits with the
 * ellipsis after it, a binary search). At most SG_NAME_MAX wide chars are looked at. */
void az_fit(void *w, const char *text) {
    unsigned s[SG_NAME_MAX + 1], len = 0, lo, hi, i, o = 0, c;
    char out[4 * SG_NAME_MAX + 1];
    const unsigned *t;
    int room;
    if (!w) return;
    room = I(w, W_W);
    widget_set_text_utf8(w, text);
    t = widget_get_text(w);
    if (!t || az_text_w(w, t) <= room) return;
    while (t[len] && len < SG_NAME_MAX) s[len] = t[len], ++len;
    s[len] = 0;
    lo = 0, hi = len - 1;
    while (lo < hi) {
        unsigned mid = (lo + hi + 1) / 2, k0 = s[mid], k1 = s[mid + 1];
        s[mid] = ELLIPSIS, s[mid + 1] = 0;
        if (az_text_w(w, s) <= room)
            lo = mid;
        else
            hi = mid - 1;
        s[mid] = k0, s[mid + 1] = k1;
    }
    while (lo && s[lo - 1] == ' ') --lo; /* no space before the ellipsis */
    s[lo] = ELLIPSIS, s[lo + 1] = 0;
    for (i = 0; s[i]; ++i) { /* back to UTF-8 */
        c = s[i];
        if (c < 0x80)
            out[o++] = (char)c;
        else if (c < 0x800)
            out[o++] = (char)(0xc0 | c >> 6), out[o++] = (char)(0x80 | (c & 63));
        else if (c < 0x10000)
            out[o++] = (char)(0xe0 | c >> 12), out[o++] = (char)(0x80 | (c >> 6 & 63)),
            out[o++] = (char)(0x80 | (c & 63));
        else
            out[o++] = (char)(0xf0 | c >> 18), out[o++] = (char)(0x80 | (c >> 12 & 63)),
            out[o++] = (char)(0x80 | (c >> 6 & 63)), out[o++] = (char)(0x80 | (c & 63));
    }
    out[o] = 0;
    widget_set_text_utf8(w, out);
}

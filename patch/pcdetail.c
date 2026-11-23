/* M1+ Music Podcasts, the episode page's texts: the layout of the title, the grey line, the date and the full description, and their painting (patch/pcdetail.h).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "i18n.h"
#include "podcasts.h"
#include "pcdetail.h"

static int pd_wlen(const unsigned *s) {
    int n = 0;
    while (s[n]) ++n;
    return n;
}

static int pd_wide(unsigned *dst, int cap, const char *utf8) {
    unsigned n = 0;
    while (utf8[n] && n < 4u * (unsigned)cap) ++n;
    tk_utf8_to_utf16_ex(utf8, n, dst, (unsigned)cap);
    return pd_wlen(dst);
}

/* The advance AWTK charges for each of the n chars of s in the style label st (docs/modules/ui-rules.md "Text width"): one measure a distinct char (a 4 KB text has a few hundred), a newline is nothing. */
static void pd_adv(pd_t *d, void *st, const unsigned *s, int n, unsigned short *adv) {
    unsigned t[2];
    int i;
    t[1] = 0;
    if (d->cache_st != st) /* (the advances are the style's: another style starts the cache again) */
        memset(d->cache, 0, sizeof d->cache), d->cache_st = st;
    for (i = 0; i < n; ++i) {
        unsigned cp = s[i], slot = (cp * 2654435761u) >> 24;
        if (cp == '\n') {
            adv[i] = 0;
            continue;
        }
        if (d->cache[slot].w && d->cache[slot].cp == cp) {
            adv[i] = (unsigned short)(d->cache[slot].w - 1);
            continue;
        }
        t[0] = cp;
        adv[i] = (unsigned short)m1_text_w(st, t);
        d->cache[slot].cp = cp,
        d->cache[slot].w = (unsigned short)(adv[i] + 1); /* (w is the advance + 1: 0 is an empty slot) */
    }
}

/* s (n chars) in at most maxl lines of room px, the lines' starts relative to s (an ellipsis closes the last line when text is left). */
int pd_lines(pd_t *d, void *st, unsigned *s, int n, int room, int maxl, pw_line_t *out) {
    unsigned e[2];
    unsigned short *adv = d->adv;
    e[0] = ELLIPSIS, e[1] = 0;
    if (n > PD_WIDE - 1) n = PD_WIDE - 1, s[n] = 0;
    pd_adv(d, st, s, n, adv);
    return pw_wrap(s, n, adv, room, maxl, m1_text_w(st, e), out);
}

void pd_date(char *out, unsigned size, const char *when, unsigned dur, unsigned length) {
    char t[24];
    unsigned o = 0;
    out[0] = 0;
    if (when[0]) o = (unsigned)snprintf(out, size, "%s", when);
    if (o >= size) return;
    if (dur) {
        pc_len_text(t, sizeof t, dur);
        o += (unsigned)snprintf(out + o, size - o, "%s%s", o ? " \xc2\xb7 " : "", t);
        if (o >= size) return;
    }
    if (length) {
        pc_fmt(t, sizeof t, TR("%d MB"), (length + 1048575) >> 20);
        snprintf(out + o, size - o, "%s%s", o ? " \xc2\xb7 " : "", t);
    }
}

/* text wrapped paragraph by paragraph (the text between newlines, each by itself, PD_W wide in the style label st) into d->text, d->dl and d->dy: the first line's top is y, the lines PD_PITCH apart, PD_PGAP more between
 * paragraphs. Returns the y under the last line (y itself for no text). At most PD_LINES lines; the text is cut at PD_WIDE chars. */
int pd_paras(pd_t *d, void *st, const char *text, int y) {
    int n, k, a, b, para = 0;
    d->nl = 0;
    n = pd_wide(d->text, PD_WIDE, text);
    for (a = 0; a < n && d->nl < PD_LINES; a = b + 1) {
        int cnt;
        b = a;
        while (b < n && d->text[b] != '\n') ++b;
        d->text[b] = 0; /* (the newline becomes the paragraph's end; the NUL after the text is there already) */
        if (b > a) {
            cnt = pd_lines(d, st, d->text + a, b - a, PD_W, PD_LINES - d->nl, d->dl + d->nl);
            if (para) y += PD_PGAP;
            for (k = 0; k < cnt; ++k) {
                d->dl[d->nl + k].start = (short)(d->dl[d->nl + k].start + a);
                d->dy[d->nl + k] = (short)y;
                y += PD_PITCH;
            }
            d->nl += cnt;
            para = 1;
        }
    }
    return y;
}

void pd_make(pd_t *d, void *st_title, void *st_meta, void *st_desc, const char *title, const char *show,
             const char *date, const char *desc, const char *hint, int has_pill) {
    int y, n;
    unsigned buf[PD_META_MAX];
    memset(d, 0, sizeof *d);
    n = pd_wide(d->title, PD_TITLE_MAX, title);
    d->tn = pd_lines(d, st_title, d->title, n, PD_W, PD_TITLE_LINES, d->tl);
    d->datelen = pd_wide(d->date, 48, date);
    /* the show's name, one line cut with an ellipsis to the room between the cover and the chevron */
    n = pd_wide(buf, PD_META_MAX, show);
    {
        pw_line_t ln;
        int got = pd_lines(d, st_meta, buf, n, PD_SHOW_TEXT_W, 1, &ln);
        d->nm = 0;
        if (got == 1) {
            memcpy(d->meta, buf + ln.start, (unsigned)ln.len * sizeof *buf);
            d->nm = ln.len;
        }
        d->meta[d->nm] = 0;
    }
    y = PD_TOP;
    d->y_date = y;
    y += PD_DATE_H + PD_GAP_DATE;
    d->y_title = y;
    y += d->tn * PD_TITLE_PITCH + PD_GAP_TITLE;
    d->y_show = y;
    y += PD_SHOW_H + PD_GAP_SHOW;
    if (has_pill) {
        d->y_pill = y;
        y += PD_PILL_ROW + PD_GAP_PILL;
    }
    d->y_desc = y;
    d->hint = !desc[0];
    y = pd_paras(d, desc[0] ? st_desc : st_meta, desc[0] ? desc : hint, y);
    d->h = y + PD_BOTTOM;
}

/* A text drawn wholly inside the view only (every text of the payload's pages: AWTK does not clip it). The canvas has the style. */
static void pd_text(void *canvas, const unsigned *s, int n, int x, int y, int w, int h) {
    int rect[4];
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    if (n > 0 && y >= 0 && y + h <= GRID_VIEW_H) canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

void pd_paint(void *canvas, const pd_t *d, int off, void *st_date, void *st_title, void *st_meta, void *st_desc,
              int datex) {
    int k;
    widget_prepare_text_style(st_date, canvas);
    pd_text(canvas, d->date, d->datelen, datex, d->y_date - off, PD_X + PD_W - datex, PD_DATE_H);
    widget_prepare_text_style(st_title, canvas);
    for (k = 0; k < d->tn; ++k)
        pd_text(canvas, d->title + d->tl[k].start, d->tl[k].len, PD_X, d->y_title + k * PD_TITLE_PITCH - off, PD_W,
                PD_TITLE_PITCH);
    widget_prepare_text_style(st_meta, canvas);
    pd_text(canvas, d->meta, d->nm, PD_SHOW_TEXT_X, d->y_show + (PD_SHOW_H - PD_SHOW_TEXT_H) / 2 - off, PD_SHOW_TEXT_W,
            PD_SHOW_TEXT_H);
    widget_prepare_text_style(d->hint ? st_meta : st_desc, canvas);
    for (k = 0; k < d->nl; ++k) {
        int y = d->dy[k] - off;
        if (y + PD_PITCH <= 0) continue;
        if (y >= GRID_VIEW_H) break;
        pd_text(canvas, d->text + d->dl[k].start, d->dl[k].len, PD_X, y, PD_W, PD_PITCH);
    }
}

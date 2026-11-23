/* The Podcasts episode page's layout and texts (patch/pcdetail.c; docs/modules/podcasts.md "Pages and controls").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The page is the Show level's content view painted another way (patch/podcasts.c holds the state, the pill, the badges and the touch); this file makes the texts: the date line, the title, the show's name and the
 * description wrapped once (patch/pcwrap.c: kinsoku, CJK anywhere) from the font's own advances, the blocks' tops, and paints them. tools/pod_show.py `detail_layout` is the same layout in Python
 * (it reads the PD_* numbers below): the tests and the preview use it. Content y from the list's top (window row 50).
 */
#pragma once
#include "pcwrap.h"

#define PD_X 16 /* the texts' left edge and width */
#define PD_W 288
#define PD_TOP 12 /* the content's top to the date line (no cover above it) */
#define PD_DATE_H 22
#define PD_GAP_DATE 4
#define PD_TITLE_PITCH 26
#define PD_TITLE_LINES 5
#define PD_GAP_TITLE 10 /* the title's last line to the show row */
#define PD_SHOW_H 40 /* the show row: a rounded cover, the show's name, a chevron */
#define PD_COVER 32 /* the show row's cover, at x PD_X, centred in the row */
#define PD_COVER_R 6
#define PD_SHOW_TEXT_X 58 /* the show's name: x and width (it ends at x 278, 10 px before the shared chevron) */
#define PD_SHOW_TEXT_W 220
#define PD_SHOW_TEXT_H 22 /* the name's line, centred in the row */
#define PD_CHEV_X 288 /* the shared chevron's left edge (LIST_CHEV_X) */
#define PD_GAP_SHOW 14 /* the show row to the pill row (or to the description when there is no pill) */
#define PD_PILL_ROW 30
#define PD_GAP_PILL 18
#define PD_PITCH 22 /* the description's lines */
#define PD_PGAP 10 /* extra air between paragraphs */
#define PD_BOTTOM 28
#define PD_LINES 320 /* lines kept of the description (a 4 KB text needs about 100 of them) */
#define PD_TITLE_MAX 100 /* wide chars of the title and the show name */
#define PD_META_MAX 232
#define PD_WIDE 4104 /* wide chars of the description: PF_NOTE bytes are at most that many characters, and the NUL */

typedef struct {
    unsigned title[PD_TITLE_MAX], meta[PD_META_MAX], date[48];
    pw_line_t tl[PD_TITLE_LINES], dl[PD_LINES];
    int tn, nm, datelen,
        nl; /* lines of the title, chars of the show's name and of the date line, lines of the description */
    int y_date, y_title, y_show, y_pill, y_desc,
        h; /* the blocks' tops; y_pill is 0 without a pill; h is the content's height */
    int hint; /* the description is the "no description" hint (painted in the grey line's style) */
    short dy[PD_LINES]; /* each description line's y */
    unsigned text[PD_WIDE];
    unsigned short adv[PD_WIDE];
    struct {
        unsigned cp;
        unsigned short w;
    } cache[256]; /* the glyphs' advances measured so far in the style cache_st (direct mapped) */
    void *cache_st;
} pd_t;

/* The date line: the cell's date and, when the size is known, " · 48 MB" ("Oct 28 · 48 MB"; just the size when there is no date). */
void pd_date(char *out, unsigned size, const char *when, unsigned dur, unsigned length);
/* text (paragraphs split by newlines) wrapped to PD_W in the style label st into d->text / d->dl / d->dy / d->nl, the first line's top at y; returns the y under the last line. */
int pd_paras(pd_t *d, void *st, const char *text, int y);
/* The page's texts: title in st_title, the show's name in st_meta (cut with an ellipsis to PD_SHOW_TEXT_W), the date line, and the description in st_desc (empty desc: the hint text instead, in the meta
 * style). has_pill: the pill row is there (the page puts the pill and the "..." at y_pill). */
void pd_make(pd_t *d, void *st_title, void *st_meta, void *st_desc, const char *title, const char *show,
             const char *date, const char *desc, const char *hint, int has_pill);
/* s (n chars) in at most maxl lines of room px in the style label st, the lines as (start, length) into s (an ellipsis closes the last line when text is left); d only holds the advances' cache
 * (Find Cover & Lyrics wraps a lyrics text line by line with it). */
int pd_lines(pd_t *d, void *st, unsigned *s, int n, int room, int maxl, pw_line_t *out);
/* The texts of the page at scroll offset off, each wholly inside the 400 px view or not at all (AWTK does not clip): datex is where the date starts (after the badges). */
void pd_paint(void *canvas, const pd_t *d, int off, void *st_date, void *st_title, void *st_meta, void *st_desc,
              int datex);

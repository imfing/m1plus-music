/* The A-Z list furniture shared by the Songs page (patch/songs.c) and the Artists / Genres / Composers page (patch/artists.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Moved from patch/songs.c (docs/modules/songs.md has the design and the evidence); the Songs page's behaviour is unchanged.
 *
 * A page that uses it is a stock list_view > scroll_view holding ONE content view that paints the rows itself; this module is what both pages
 * do with sections and the index and neither owns:
 *   sections  az_sections: the non-decreasing labelling of the rows' ranks ("#" 0, A..Z 1..26) that puts the most rows under their own letter; the
 *             list keeps its order, a stray stays in the section around it. sec_start / sec_letter, at most SG_MAX_SEC (28) sections.
 *   geometry  the header of section s is at az_hdr_y(s) = top + s * hdr_h + sec_start[s] * row (hdr_h is SG_HDR_H, or 0 with Section Headers off); a row's y, the row under a y, the rows in view.
 *   switches  az_prefs: Index Rail (on by default; off: norail) and Section Headers (on by default: hdr_h), read when a page opens (docs/modules/artists.md).
 *   headers   az_paint_heads: the bare 20 px letters and the pinned header (an opaque black backing, the next header pushes it up).
 *   rail      the compact A-Z index (az_rail_*): plan, widget fit, paint (letters, dots, the touched letter's disc), touch (grab, jump), the bubble.
 * The page owns the scroll_view, the rows and the timers; it fills in the az_t fields marked (page) and calls these.
 */
#pragma once

typedef struct {
    void *win, *sv; /* (page) the window and the scroll_view the rail scrolls */
    void *rail, *bubble,
        *bubble_letter; /* (page) the rail widget (outside the scroll_view), the bubble and its letter label */
    void *st_hdr, *st_rail,
        *st_rail_on; /* (page) hidden labels whose styles are the header letter, the rail letter and the touched rail letter */
    void *disc; /* the touched letter's disc (SG_RAIL_DISC px, alpha) */
    int top; /* (page) content y of the first header */
    int row; /* (page) the rows' height */
    int count; /* (page) rows */
    int content; /* (page) the content's height: the scroll offset is clamped to content - GRID_VIEW_H */
    int nsec; /* 0: a plain list; else the sections */
    unsigned sec_start[SG_MAX_SEC]; /* the first row of each section */
    unsigned char sec_letter[SG_MAX_SEC];
    int grab, rail_on,
        rail_i; /* a finger holds the rail; it has set a letter (the disc and the bubble show); the letter's section */
    int hdr_h; /* the section header's height: SG_HDR_H, 0 with Section Headers off (az_prefs sets it: the page calls it when it opens) */
    int norail; /* Index Rail off (az_prefs): no rail, no bubble; the rows keep the full list-row width (az_inset 0) */
    /* A page whose sections are named, not lettered (the Downloaded page: Downloading / Downloaded): sec_text[s] is section s's header as a TR key, drawn in place of the letter (NULL: letters; such a
     * page sets norail). sec_act, with it, is a TR key drawn at the right end of section 0's header in st_act's style (a text button: az_act_hit is its touch test). */
    const char *const *sec_text;
    const char *sec_act;
    void *st_act;
} az_t;

/* The rail's footprint on the rows: SG_RAIL_INSET while the rail is shown (sections and the Index Rail switch on), else 0. Every row of an A-Z page subtracts it from the list-row spec's
 * right side (hairline end LIST_HAIR_END, chevron x LIST_CHEV_X, text end LIST_TEXT_X + LIST_TEXT_W[_CHEV], the "..." zone's right edge RM_MORE_RIGHT); az_end is the hairline's end. */
int az_inset(const az_t *az);
int az_end(const az_t *az);

/* The two switches of Settings > Library (appearance-index-rail, appearance-headers), read when a page opens: az_prefs sets hdr_h and norail. */
void az_prefs(az_t *az);
int azrail_setting(void);
int azrail_toggle(void);
int azhead_setting(void);
int azhead_toggle(void);

/* The rank of a character in the sections: 0 "#" (a digit, '*', anything else), 1..26 'A'..'Z' (either case). */
int az_rank_of(int c);
unsigned char az_rank_letter(int rank); /* the letter a rank shows */
/* The Z-A mirror: Z is rank 0 .. A rank 25 and "#" last (26), so the ranks still rise down the list. */
static inline int az_flip_rank(int k) { return k ? 26 - k : 26; }
void az_flip_letters(
    az_t *
        az); /* the headers and the rail of mirrored ranks: each section's letter (the rank az_sections labelled it with) shows as its mirror */
/* The six widgets of the A-Z furniture of win (label_hdr, label_rail, label_rail_on, sg_rail, sg_bubble, sg_bubble_letter, looked up in that order); 1 when all six exist. */
int az_bind(az_t *az, void *win);
/* The rail's touch (DOWN, MOVE, UP, ABORT -> on) and its paint (AFTER_PAINT -> paint). */
void az_bind_rail(az_t *az, int (*on)(void *, void *), int (*paint)(void *, void *));
/* The sections of az->count rows whose ranks are the bytes rank[0], rank[stride], ...; no memory = a plain list (nsec 0). */
void az_sections(az_t *az, const unsigned char *rank, unsigned stride);

/* Geometry. */
int az_off(const az_t *az); /* the scroll_view's offset */
int az_hdr_y(const az_t *az, int s);
int az_sec_of(const az_t *az, int i); /* the section holding row i, -1 in a plain list */
int az_row_y(const az_t *az, int i);
int az_rows_end(const az_t *az); /* the content y under the last row */
int az_max_scroll(const az_t *az);
int az_row_from(const az_t *az, int y); /* the first row whose end is below content y */
int az_at(const az_t *az, int y); /* the row under content point y, -1 for the title block, a header or the air below */
void az_span(const az_t *az, int *r0, int *r1); /* the rows [*r0, *r1] that touch the view (r1 < r0 for none) */

/* Paint, in the content view's EVT_AFTER_PAINT with the canvas origin moved by the offset: a fill clipped to the window; the section letters and the pinned header. */
void az_fill(void *canvas, int x, int y0, int y1, int w, unsigned c);
void az_fill_h(void *canvas, int x, int y0, int y1, int w, unsigned c,
               int view_h); /* the same in a window view_h rows high (the album page's list is the whole 450 px) */
void az_paint_heads(az_t *az, void *canvas);
/* Whether content point (x, y) is on section 0's text button (sec_act), where its header is drawn now: in the flow, or pinned at the window's top. */
int az_act_hit(const az_t *az, int x, int y);

/* The rail. */
int az_rail_plan(const az_t *az, int *sec); /* the letters drawn, as section numbers in sec[]; the return is how many */
int az_rail_span(const az_t *az, int letters); /* the drawn height */
void az_rail_fit(
    az_t *az,
    int rail_h); /* move and size the widget to the span centred on rail_h of the list; shown when there are sections and rows */
void az_rail_paint(az_t *az, void *e);
void az_rail_event(az_t *az, void *e); /* DOWN grabs, MOVE sets the letter, UP / ABORT end */
void az_rail_end(az_t *az);
void az_make_disc(az_t *az);
void az_free(az_t *az); /* the disc */
void az_redraw_rail(const az_t *az);

/* The UTF-8 text on label w cut with an ellipsis to the label's width (wide chars, at most SG_NAME_MAX looked at); 1 when it was cut. */
int az_fit(void *w, const char *text);
/* The same, cut to room px (an hscroll_label draws its text in its width less a 2 px margin each side, and scrolls a text wider than that). */
int az_fit_room(void *w, const char *text, int room);

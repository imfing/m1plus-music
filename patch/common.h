/* Small helpers every page of the payload shares (patch/common.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once
#include "palette.h" /* Light Mode: ui_ink, ui_fill_color, pal_tone (every page that paints its own colours includes this file) */

#define ELLIPSIS 0x2026 /* U+2026 HORIZONTAL ELLIPSIS, the wide char texts are cut with */
#define POD_DARK_MS 1000

/* A stock object's field at a byte offset (the offsets are patch/offsets.inc's): an int, a byte. */
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))

/* The widget's text as UTF-8 in buf (size bytes, cut at a character boundary, always NUL terminated). Returns the length the whole text needs: it fitted when the result is below
 * size; -1 when the widget has no text. Use this, never stock widget_get_text_utf8, which ignores size for a wide text (docs/modules/payload.md). */
int m1_text_utf8(void *widget, char *buf, unsigned size);
/* The n bytes at in with each %XX decoded to its byte, into out (size bytes, always NUL terminated, never written past; a malformed '%' stays). Returns the length written. */
unsigned m1_url_decode(char *out, unsigned size, const char *in, unsigned n);
/* Up to cap bytes of a file in a heap buffer (a NUL after them, the caller frees it), *n the length; NULL when it is missing, empty or there is no memory. */
char *m1_read_file(const char *path, unsigned cap, unsigned *n);
/* The end of an atomic write: fd (the open tmp; ok: all of it was written) fsynced and closed, tmp renamed onto path. 1 on success; any failure removes tmp. */
int m1_commit(int fd, int ok, const char *tmp, const char *path);
/* data (n bytes) into path atomically: written to tmp (created with mode), then m1_commit. 1 on success; a failure leaves no temp file (the directory is not fsynced:
 * m1_card_write does that for the card's own files). */
int m1_save(const char *path, const char *tmp, unsigned mode, const void *data, unsigned n);
int m1_screen_lit(void); /* stock backlight state */

int m1_on_back(void *ctx, void *e); /* click handler: navigator_back() */
void m1_open_now_playing(void); /* Radio Now Playing while a station plays, else the stock player */
int m1_on_player(void *ctx, void *e); /* click handler: the stock "back to the player" button */
int m1_scan_dir(
    const char *name,
    const char *
        dot); /* the library scan's strcmp(name, ".") replacement: 0 for any name starting with '.' (docs/modules/payload.md hook 5) */
/* One artist of an artist field: a slice of the caller's string, never a copy. */
typedef struct {
    const char *p;
    unsigned n;
} m1_artist_span;
/* The names in an artist field, in the order they appear: split on " feat. ", " ft. ", " featuring ", " & ", " x ", ", " and "; " (ASCII case folded; each separator
 * carries the spaces it is written with, so a bare "Tom;Jerry" stays one name), parts trimmed and empty ones dropped, at most max into out. Returns the count (1 for a
 * field with no separator, 0 when there is nothing to share). Reads `field` only: the span must not outlive it. docs/modules/artists.md "Separators". */
int m1_artist_split(const char *field, m1_artist_span *out, int max);
int m1_card_mounted(
    void); /* the SD card is mounted (statfs: /mnt/mmc is another file system than /mnt); never write under /mnt/mmc otherwise */
/* a (na bytes) then b (nb) into path in dir (CARD_DIR or a folder in it) on the card, atomically (tmp, fsync, rename, fsync of dir);
 * the folders made first. 0 on success, -1 (nothing written) with the card not mounted. */
int m1_card_write(const char *dir, const char *path, const char *tmp, const void *a, unsigned na, const void *b,
                  unsigned nb);
/* write() all n bytes of data to fd; 1 on success, 0 on a failed or empty write. */
int m1_write_all(int fd, const void *data, unsigned n);
#define M1_CA \
    "/etc/m1plus-cacert.pem" /* the CA bundle libcurl verifies with: Mozilla's roots, in the firmware (tools/mod_cacerts.py; stock's /etc/ssl/certs is empty) */
#define M1_MIN_EPOCH \
    1750000000u /* a clock before this (mid 2025, before the firmware existed) was never set: certificates would not verify */
/* Percent-escape s into out at offset used (RFC 3986 unreserved characters pass, every other byte is %XX); returns the new length, or 0 when s is NULL or the result does not fit
 * (a terminator's room is kept, none is written). */
unsigned m1_urlenc(char *out, unsigned cap, unsigned used, const char *s);
/* KB free for a non-root user on the file system of path (statfs); 0 when it fails (*kb is then not set). */
int m1_free_kb(const char *path, unsigned *kb);
/* The topmost opened window called name (the asset's root name, not the navigator_to path) brought to the front by stock's own restack, nothing closed. The window, or NULL (no such window, it is closing, or stock refused) with the stack as it was. */
void *m1_restack_window(const char *name);
/* A stock page: its opened window called window (the asset's root name; NULL: none) restacked as m1_restack_window does, else stock's navigator_to(path) (always, for NULL: a page whose init a restack would not redo). RET_OK, or navigator_to's result. */
int m1_open_stock(const char *path, const char *window);
int m1_is_type(void *w, const char *type); /* w is a widget of exactly this type name */
/* The navbar's small title (docs/modules/navbar.md "Small titles"): m1_title_gone(off, head) is 1 once the page's heading has scrolled away (head 0: the large title, SG_COLLAPSE;
 * else the offset a header's name is gone at); m1_title_set shows or hides w when on differs from *cur. */
int m1_title_gone(int off, int head);
/* w shown or hidden, and in or out of the hit test with it (this AWTK's widget_find_target ignores visible); a NULL w is left alone. */
void m1_show(void *w, int on);
/* The timer *t removed (0: there is none) and *t cleared. */
void m1_timer_stop(unsigned *t);
/* The width of the text t in widget w's own font, rounded up to whole px (0 or less: it cannot be measured). */
int m1_text_w(void *w, const unsigned *t);
/* Where a pointer press began (screen coordinates). A page keeps its pressed row + 1 itself; the tap is a release closer than SC_DRAG_PX on both axes (the scroll_view's own drag threshold). */
typedef struct {
    int x, y;
} m1_tap_t;
void m1_tap_at(m1_tap_t *t, void *e);
int m1_tap_near(const m1_tap_t *t, void *e);
/* Select All on a page's mark bits (count rows, nsel marked): all of them, unless all are: then none. Returns the new number marked. */
unsigned m1_sel_all(unsigned char *sel, unsigned count, unsigned nsel);
static inline int m1_abs(int v) { return v < 0 ? -v : v; }
void m1_title_set(void *w, int *cur, int on);
/* The translated text f ("%d tracks") with n where it has its %d, into out (size bytes). */
void m1_fmt(char *out, unsigned size, const char *f, int n);
/* Bind fn to EVT_CLICK of the widget called name in win (ctx passed through); returns the widget, NULL if
 * the page has none (or fn is NULL). */

/* Cover tint, shared by Now Playing and the album page (patch/common.c). */
/* A dark, slightly desaturated tone of a cover's average colour (r, g, b bytes), a color_t word (0xAABBGGRR, alpha ff). */
unsigned m1_tone(unsigned r, unsigned g, unsigned b);
/* The tone cache (RAM, TONE_CACHE_N entries, least recently used out): the tone word of an album key (cc_album_key).
 * get: 1 and *tone when cached. put: insert or replace. A key of 0 is never stored or found. */
int m1_tone_get(unsigned key, unsigned *tone);
void m1_tone_put(unsigned key, unsigned tone);
/* The black gradient's alpha on row y of `rows`: a_top on the first row to a_bot on the last (rows past it: a_bot). */
unsigned m1_alpha(unsigned y, unsigned a_top, unsigned a_bot, unsigned rows);
/* color (0x..BBGGRR) as it shows on row y under that gradient. */
unsigned m1_shade(unsigned color, unsigned y, unsigned a_top, unsigned a_bot, unsigned rows);
/* The top left corner's coverage (0..255) outside a quarter circle of radius r, r * r bytes. */
void m1_corner_fill(unsigned char *tab, unsigned r);
/* A square cover's four corners painted in the colour the window has behind them (a canvas in the cover's own
 * coordinates): cover row 0 is window row row0, under the gradient (a_top, a_bot, rows). Returns nothing. */
void m1_corners(void *canvas, const unsigned char *tab, unsigned r, unsigned side, unsigned color, int row0,
                unsigned a_top, unsigned a_bot, unsigned rows);
/* The status bar in a page's top-edge colour (Now Playing, the album page). color is 0x..BBGGRR as the page shows it on row 0;
 * m1_bar_color darkens it until the bar's white glyphs keep 4.5:1 (luminance cap NP_BAR_LUM_MAX) and returns a color_t word.
 * m1_bar_tint: the bar takes it and win owns the bar; 1 on success, 0 (nothing owed) when there is no bar or the style call fails.
 * m1_bar_black: the stock black, only if win is the owner (so a page that lost the bar to the next page leaves it alone).
 * m1_is_top: win is the window manager's top normal window. */
unsigned m1_bar_color(unsigned color);
int m1_bar_tint(void *win, unsigned color);
void m1_bar_black(void *win);
int m1_is_top(void *win);
void *m1_bind(void *win, const char *name, int (*fn)(void *, void *), const void *ctx);
/* The flat pill's glyph and label (a button whose style has the glyph as its icon) centred as a pair SG_PILL_GAP apart in a pill pw px wide (the Songs, Folders and artist pages' Play / Shuffle pills, the select bars' pills; AWTK puts the glyph in a square as high as the button at margin_left and the text at the square's end plus the spacer); a label too wide beside
 * the glyph steps down to SG_PILL_PX_SMALL. Needs the button's text (widget_get_text) to be set. */
void m1_centre_pill(void *btn, int pw);
/* The header's Play pill, the album page's design (patch/albumpage.c, a playlist's page): the pill is a picture (the button), the glyph an image over it and
 * the text painted by the page's content view; glyph and text are centred as a pair for the language (AH_PILL_*). ptext is the hidden label with the text style and the translated
 * text. m1_pill_place puts the glyph and measures the text for a button whose top is y (AH_PLAY_X, AH_BTN_H high; one that cannot be measured, or does not fit, is centred as
 * the English one); m1_pill_paint draws the text for that y less the scroll offset, over the picture. */
typedef struct {
    void *glyph, *ptext;
    int tx, tw;
} m1_pill_t;
void m1_pill_place(m1_pill_t *p, int y);
/* The centring m1_pill_place does, for a pill whose touch rectangle is x0, w0: glyph and gap px wide, a text tw px wide. Returns the glyph's x; *tx is the text's x and *twide its paint width (tw + AB_TEXT_SLACK). */
int m1_pill_pair(int x0, int w0, int glyph, int gap, int tw, int *tx, int *twide);
void m1_pill_paint(const m1_pill_t *p, void *canvas, int y);
/* A bottom sheet's n rows (1 .. 6; their row widgets rows[] and hairlines hrs[], in order) PM_ROW_H each from the card's top, the first without its hairline, the card w px wide over the window's bottom edge, with the glass picture of its
 * height (pc_sheet<n>); the rows, the card and the scrim shown. */
void m1_sheet_rows(void *scrim, void *card, int w, void *const *rows, void *const *hrs, int n);
/* A select mark: the stock image called name (the multi-select's unselect / selected, SG_MARK px) as an opaque bitmap, NULL when it cannot be made. win: any widget of the page. */
void *m1_make_mark(void *win, const char *name);
/* The pair of select marks (mark[0] unselect, mark[1] selected), all or none: 1 with both made, 0 with both NULL (no marks: no select mode). */
int m1_make_marks(void *win, void *mark[2]);

/* The grey chevron the list rows of the Artists and Search pages end with: a POD_CHEV_W x POD_CHEV_H RGBA bitmap (a two segment stroke, antialiased by 4 x 4 samples, POD_CHEV_RGB), NULL when it cannot be made. */
#define POD_CHEV_W 10
#define POD_CHEV_H 16
#define POD_CHEV_RGB 0x8a8a8a
void *m1_make_chevron(void);
/* A capsule: the rectangle w x h at (x, y) with corners of radius r (at most half the height: a full capsule), in colour c (a color_t word), edges smoothed with a pixel of partial cover. view_h: the canvas' visible rows
 * (a row outside 0 .. view_h - 1 is not painted: the page paints into the scrolled content view). */
void m1_capsule(void *canvas, int view_h, int x, int y, int w, int h, int r, unsigned c);
/* The segmented control (docs/modules/ui-rules.md "Segmented control"): a SEG_TRACK capsule w x h at (x, y) holding n equal segments, the selected one a SEG_THUMB capsule floating SEG_PAD inside the track; a SEG_SEP
 * hairline half the track high between two segments that are both unselected (none beside the thumb); each label (label[k], len[k] wide chars) centred in its segment, in the style label st_on on the thumb and st_off elsewhere.
 * Nothing is painted outside view_h's rows; the caller makes the label styles (their ink is dark on the thumb, light on the track). */
void m1_segmented(void *canvas, int view_h, int x, int y, int w, int h, int n, int sel, void *st_on, void *st_off,
                  const unsigned *const *label, const int *len);
/* A POD_CROSS px square bitmap of a grey x (the Search page's recent searches remove it), made as the chevron; NULL when it cannot be made. */
#define POD_CROSS 12
void *m1_make_cross(void);
/* c over v by a (of 255), opaque result: w = a + (a >> 7), both colour lanes at once. */
static inline __attribute__((always_inline)) unsigned m1_mix(unsigned v, unsigned c, unsigned a) {
    unsigned w = a + (a >> 7);
    return 0xff000000u | (((v & 0xff00ffu) * (256 - w) + (c & 0xff00ffu) * w) >> 8 & 0xff00ffu) |
           (((v & 0xff00u) * (256 - w) + (c & 0xff00u) * w) >> 8 & 0xff00u);
}
/* The integer square root of v (the largest s with s * s <= v). */
unsigned m1_isqrt(unsigned v);
/* A bitmap of ours from the asset `name` of win, w x h as the image is stored, as RGBA8888 whatever order the decoder gave (premultiplied when pm). NULL when it cannot be loaded or has another size. */
void *m1_asset_rgba(void *win, const char *name, unsigned w, unsigned h, int pm);

/* Small helpers every page of the payload shares (patch/common.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once
#include "palette.h" /* Light Mode: ui_ink, ui_fill_color, pal_tone (every page that paints its own colours includes this file) */

#define ELLIPSIS 0x2026 /* U+2026 HORIZONTAL ELLIPSIS, the wide char texts are cut with */
#define POD_DARK_MS 1000

/* The widget's text as UTF-8 in buf (size bytes, cut at a character boundary, always NUL terminated). Returns the length the whole text needs: it fitted when the result is below
 * size; -1 when the widget has no text. Use this, never stock widget_get_text_utf8, which ignores size for a wide text (docs/modules/payload.md). */
int pod_text_utf8(void *widget, char *buf, unsigned size);
/* The n bytes at in with each %XX decoded to its byte, into out (size bytes, always NUL terminated, never written past; a malformed '%' stays). Returns the length written. */
unsigned pod_url_decode(char *out, unsigned size, const char *in, unsigned n);
int pod_screen_lit(void); /* stock backlight state */

int pod_on_back(void *ctx, void *e); /* click handler: navigator_back() */
void pod_open_now_playing(void); /* Radio Now Playing while a station plays, else the stock player */
int pod_on_player(void *ctx, void *e); /* click handler: the stock "back to the player" button */
int pod_scan_dir(
    const char *name,
    const char *
        dot); /* the library scan's strcmp(name, ".") replacement: 0 for any name starting with '.' (docs/modules/payload.md hook 5) */
int pod_card_mounted(
    void); /* the SD card is mounted (statfs: /mnt/mmc is another file system than /mnt); never write under /mnt/mmc otherwise */
/* a (na bytes) then b (nb) into path in dir (CARD_DIR or a folder in it) on the card, atomically (tmp, fsync, rename, fsync of dir);
 * the folders made first. 0 on success, -1 (nothing written) with the card not mounted. */
int pod_card_write(const char *dir, const char *path, const char *tmp, const void *a, unsigned na, const void *b,
                   unsigned nb);
/* The topmost opened window called name (the asset's root name, not the navigator_to path) brought to the front by stock's own restack, nothing closed. The window, or NULL (no such window, it is closing, or stock refused) with the stack as it was. */
void *pod_restack_window(const char *name);
/* A stock page: its opened window called window (the asset's root name; NULL: none) restacked as pod_restack_window does, else stock's navigator_to(path) (always, for NULL: a page whose init a restack would not redo). RET_OK, or navigator_to's result. */
int pod_open_stock(const char *path, const char *window);
int pod_is_type(void *w, const char *type); /* w is a widget of exactly this type name */
/* The navbar's small title (docs/modules/navbar.md "Small titles"): pod_title_gone(off, head) is 1 once the page's heading has scrolled away (head 0: the large title, SG_COLLAPSE;
 * else the offset a header's name is gone at); pod_title_set shows or hides w when on differs from *cur. */
int pod_title_gone(int off, int head);
void pod_title_set(void *w, int *cur, int on);
/* The translated text f ("%d tracks") with n where it has its %d, into out (size bytes). */
void pod_fmt(char *out, unsigned size, const char *f, int n);
/* Bind fn to EVT_CLICK of the widget called name in win (ctx passed through); returns the widget, NULL if
 * the page has none (or fn is NULL). */

/* Cover tint, shared by Now Playing and the album page (patch/common.c). */
/* A dark, slightly desaturated tone of a cover's average colour (r, g, b bytes), a color_t word (0xAABBGGRR, alpha ff). */
unsigned pod_tone(unsigned r, unsigned g, unsigned b);
/* The tone cache (RAM, TONE_CACHE_N entries, least recently used out): the tone word of an album key (cc_album_key).
 * get: 1 and *tone when cached. put: insert or replace. A key of 0 is never stored or found. */
int pod_tone_get(unsigned key, unsigned *tone);
void pod_tone_put(unsigned key, unsigned tone);
/* The black gradient's alpha on row y of `rows`: a_top on the first row to a_bot on the last (rows past it: a_bot). */
unsigned pod_alpha(unsigned y, unsigned a_top, unsigned a_bot, unsigned rows);
/* color (0x..BBGGRR) as it shows on row y under that gradient. */
unsigned pod_shade(unsigned color, unsigned y, unsigned a_top, unsigned a_bot, unsigned rows);
/* The top left corner's coverage (0..255) outside a quarter circle of radius r, r * r bytes. */
void pod_corner_fill(unsigned char *tab, unsigned r);
/* A square cover's four corners painted in the colour the window has behind them (a canvas in the cover's own
 * coordinates): cover row 0 is window row row0, under the gradient (a_top, a_bot, rows). Returns nothing. */
void pod_corners(void *canvas, const unsigned char *tab, unsigned r, unsigned side, unsigned color, int row0,
                 unsigned a_top, unsigned a_bot, unsigned rows);
/* The status bar in a page's top-edge colour (Now Playing, the album page). color is 0x..BBGGRR as the page shows it on row 0;
 * pod_bar_color darkens it until the bar's white glyphs keep 4.5:1 (luminance cap NP_BAR_LUM_MAX) and returns a color_t word.
 * pod_bar_tint: the bar takes it and win owns the bar; 1 on success, 0 (nothing owed) when there is no bar or the style call fails.
 * pod_bar_black: the stock black, only if win is the owner (so a page that lost the bar to the next page leaves it alone).
 * pod_is_top: win is the window manager's top normal window. */
unsigned pod_bar_color(unsigned color);
int pod_bar_tint(void *win, unsigned color);
void pod_bar_black(void *win);
int pod_is_top(void *win);
void *pod_bind(void *win, const char *name, int (*fn)(void *, void *), const void *ctx);
/* The flat pill's glyph and label (a button whose style has the glyph as its icon) centred as a pair SG_PILL_GAP apart in a pill pw px wide (the Songs, Folders and artist pages' Play / Shuffle pills, the select bars' pills; AWTK puts the glyph in a square as high as the button at margin_left and the text at the square's end plus the spacer); a label too wide beside
 * the glyph steps down to SG_PILL_PX_SMALL. Needs the button's text (widget_get_text) to be set. */
void pod_centre_pill(void *btn, int pw);
/* The header's Play pill, the album page's design (patch/albumpage.c, a playlist's page): the pill is a picture (the button), the glyph an image over it and
 * the text painted by the page's content view; glyph and text are centred as a pair for the language (AH_PILL_*). ptext is the hidden label with the text style and the translated
 * text. pod_pill_place puts the glyph and measures the text for a button whose top is y (AH_PLAY_X, AH_BTN_H high; one that cannot be measured, or does not fit, is centred as
 * the English one); pod_pill_paint draws the text for that y less the scroll offset, over the picture. */
typedef struct {
    void *glyph, *ptext;
    int tx, tw;
} pod_pill_t;
void pod_pill_place(pod_pill_t *p, int y);
void pod_pill_paint(const pod_pill_t *p, void *canvas, int y);
/* A select mark: the stock image called name (the multi-select's unselect / selected, SG_MARK px) as an opaque bitmap, NULL when it cannot be made. win: any widget of the page. */
void *pod_make_mark(void *win, const char *name);

/* The grey chevron the list rows of the Artists and Search pages end with: a POD_CHEV_W x POD_CHEV_H RGBA bitmap (a two segment stroke, antialiased by 4 x 4 samples, POD_CHEV_RGB), NULL when it cannot be made. */
#define POD_CHEV_W 10
#define POD_CHEV_H 16
#define POD_CHEV_RGB 0x8a8a8a
void *pod_make_chevron(void);
/* A capsule: the rectangle w x h at (x, y) with corners of radius r (at most half the height: a full capsule), in colour c (a color_t word), edges smoothed with a pixel of partial cover. view_h: the canvas' visible rows
 * (a row outside 0 .. view_h - 1 is not painted: the page paints into the scrolled content view). */
void pod_capsule(void *canvas, int view_h, int x, int y, int w, int h, int r, unsigned c);
/* The segmented control (docs/modules/ui-rules.md "Segmented control"): a SEG_TRACK capsule w x h at (x, y) holding n equal segments, the selected one a SEG_THUMB capsule floating SEG_PAD inside the track; a SEG_SEP
 * hairline half the track high between two segments that are both unselected (none beside the thumb); each label (label[k], len[k] wide chars) centred in its segment, in the style label st_on on the thumb and st_off elsewhere.
 * Nothing is painted outside view_h's rows; the caller makes the label styles (their ink is dark on the thumb, light on the track). */
void pod_segmented(void *canvas, int view_h, int x, int y, int w, int h, int n, int sel, void *st_on, void *st_off,
                   const unsigned *const *label, const int *len);
/* A POD_CROSS px square bitmap of a grey x (the Search page's recent searches remove it), made as the chevron; NULL when it cannot be made. */
#define POD_CROSS 12
void *pod_make_cross(void);

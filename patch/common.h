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
/* data (n bytes) into path atomically: written to path + ".tmp" (created with mode), then m1_commit. 1 on success; a failure (a path too long for its temp name too) leaves no
 * temp file (the directory is not fsynced: m1_card_write does that for the card's own files). */
int m1_save(const char *path, unsigned mode, const void *data, unsigned n);
/* m1_save through a temp file of the caller's choosing, for a name that is not path + ".tmp". */
int m1_save_as(const char *path, const char *tmp, unsigned mode, const void *data, unsigned n);
/* fsync of a directory, so the renames in it survive a power cut. 1 on success. */
int m1_sync_dir(const char *dir);
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
/* The separators m1_artist_split may split on (a bitmask the caller picks). Symbols split with or without spaces, in their ASCII and full-width / CJK forms; the word ones need a space (or an opening bracket) before and a space after. */
#define M1_SPLIT_SEMICOLON 0x001u /* ; and the full-width semicolon */
#define M1_SPLIT_SLASH 0x002u /* / and the full-width solidus */
#define M1_SPLIT_AMPERSAND 0x004u /* & and the full-width ampersand */
#define M1_SPLIT_COMMA 0x008u /* , the full-width comma and the ideographic comma */
#define M1_SPLIT_FEAT 0x010u /* feat, ft, featuring (a full stop may follow; any case) */
#define M1_SPLIT_VS 0x020u /* vs, versus (a full stop may follow; any case) */
#define M1_SPLIT_X 0x040u /* the word x (lower case only, so "Malcolm X" stays whole) and the multiplication sign */
#define M1_SPLIT_PLUS 0x080u /* + and the full-width plus */
#define M1_SPLIT_WITH 0x100u /* with (any case) */
#define M1_SPLIT_AND 0x200u /* and (any case) */
#define M1_SPLIT_DEFAULT (M1_SPLIT_SEMICOLON | M1_SPLIT_SLASH | M1_SPLIT_AMPERSAND | M1_SPLIT_FEAT)
/* What the caller chooses: the separators (M1_SPLIT_*) and names that never split (a NULL-terminated array, matched ASCII case-insensitively wherever they occur in the field; NULL: none). */
typedef struct {
    unsigned mask;
    const char *const *except;
} m1_split_opts;
/* The built-in names that never split ("AC/DC", "Simon & Garfunkel", ...), NULL-terminated, for m1_split_opts.except. */
const char *const *m1_artist_split_exceptions(void);
/* The names in an artist field, in the order they appear, at most max into out: split on the separators opts allows (NULL opts: M1_SPLIT_DEFAULT, no exceptions), each part trimmed (spaces, and
 * the bracket a cut leaves behind: "A (feat. B)" gives "A" and "B"), empty and repeated parts dropped. Inside () and [] only feat/ft/featuring/vs/versus split, and a symbol splits there only after
 * one of them in the same brackets. Returns the count (1 for a field with no separator, 0 when there is nothing to share). Reads `field` only: the spans must not outlive it. docs/modules/artists.md "Separators". */
int m1_artist_split(const char *field, m1_artist_span *out, int max, const m1_split_opts *opts);
int m1_card_mounted(
    void); /* the SD card is mounted (statfs: /mnt/mmc is another file system than /mnt); never write under /mnt/mmc otherwise */
/* a (na bytes) then b (nb) into path in dir (CARD_DIR or a folder in it) on the card, atomically (path + ".tmp", fsync, rename, fsync of dir);
 * the folders made first. 0 on success; 1 replaced but the directory's fsync failed; -1 path untouched (as with the card not mounted). */
int m1_card_write(const char *dir, const char *path, const void *a, unsigned na, const void *b, unsigned nb);
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
/* The opened windows above win closed (top first, dialogs stay), so win is in front once they go. */
void m1_uncover(void *win);
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
/* The width of the n bytes of the UTF-8 s (with "..." before them when dots) in w's font; at most M1_FIT_TAIL bytes of s are measured. */
int m1_text_wn(void *w, int dots, const char *s, unsigned n);
/* 1 when byte i of v continues a UTF-8 character. */
static inline int m1_utf8_cont(const char *v, unsigned i) { return ((unsigned char)v[i] & 0xc0) == 0x80; }
/* A character boundary of v strictly between lo and hi (both boundaries), near the middle; hi when there is none. */
unsigned m1_utf8_mid(const char *v, unsigned lo, unsigned hi);
/* v in the label w, room px wide: whole when it fits, else the longest start (of its first M1_FIT_TAIL bytes: no more is measured) that fits with "..." after it (the spaces
 * before the dots dropped). tools/mod_nowplaying.py end_fit is the model. */
void m1_fit(void *w, const char *v, int room);
/* v in up to two labels room px wide (w1 line 1, w2 line 2, which is emptied first); returns 1 with two lines. The break is at the last space that leaves line 1 inside the
 * width (the spaces round it dropped), always, even when line 2 then needs its own end ellipsis; only with no such space (CJK, a first word wider than the line) at the last
 * character that fits. Line 2 is the rest, cut by m1_fit. tools/mod_nowplaying.py title_wrap is the model. */
int m1_wrap2(void *w1, void *w2, const char *v, int room);
/* Where a pointer press began (screen coordinates). A page keeps its pressed row + 1 itself; the tap is a release closer than SC_DRAG_PX on both axes (the scroll_view's own drag threshold). */
typedef struct {
    int x, y;
} m1_tap_t;
void m1_tap_at(m1_tap_t *t, void *e);
int m1_tap_near(const m1_tap_t *t, void *e);
/* Select All on a page's mark bits (count rows, nsel marked) over the rows can(ctx, i) accepts (NULL: all): nmark of them; all marked when nsel >= nmark, then none. Returns the new number marked. */
unsigned m1_sel_all_can(unsigned char *sel, unsigned count, unsigned nsel, unsigned nmark, int (*can)(void *ctx, int i),
                        void *ctx);
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
/* The dim behind sheets and dialogs (tools/pod_ui.py PL_DIM) as a color_t word: AWTK's colour, alpha in the top byte. */
#define M1_SCRIM_COLOR 0x82000000u
/* A sheet's or dialog's scrim shown or hidden; the status bar (a window of its own, above the page's) is dimmed with it while the scrim's window is in front. Use it for
 * every page scrim instead of m1_show. m1_bar_scrim: the bar's part alone, for a scrim that is shown otherwise (patch/m1plus.c pod_confirm_dialog's view). */
void m1_scrim(void *scrim, int on);
void m1_bar_scrim(void *win, void *scrim, int on);
/* The status bar's 1 s tick (patch/lineout.c, the real bar): repaints the bar once when its paints drew another number of scrim layers than the window in front has now.
 * Nothing until a scrim has been shown. */
void m1_bar_scrim_tick(void *bar);
void *m1_bind(void *win, const char *name, int (*fn)(void *, void *), const void *ctx);
/* The flat pill's glyph and label (a button whose style has the glyph as its icon) centred as a pair SG_PILL_GAP apart in a pill pw px wide (the Songs, Folders and artist pages' Play / Shuffle pills, the select bars' pills; AWTK puts the glyph in a square as high as the button at margin_left and the text at the square's end plus the spacer); a label too wide beside
 * the glyph steps down to SG_PILL_PX_SMALL. Needs the button's text (widget_get_text) to be set. */
void m1_centre_pill(void *btn, int pw);
/* A pill pw x ph: its glyph (glyph px) and label (tw px) centred as a pair gap apart (the styles m1_centre_pill sets, for any pill size). */
void m1_pill_styles(void *btn, int pw, int ph, int glyph, int gap, int tw);
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
/* The grey value of a sheet row (the Podcasts sheets' Playback Speed, Refresh Feed, Episode Order, Filter): `value` is the row's value label, set to text and right aligned to x PS_SHEET_VALUE_R in the room the row's `label` leaves (the
 * label keeps its whole text; cut with an ellipsis by the value label when wider; the label ends PS_SHEET_GAP before it). */
void m1_sheet_value(void *label, void *value, const char *text);
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
int m1_cat(char *out, unsigned size, const char *s);
/* A bitmap of ours from the asset `name` of win, w x h as the image is stored, as RGBA8888 whatever order the decoder gave (premultiplied when pm). NULL when it cannot be loaded or has another size. */
void *m1_asset_rgba(void *win, const char *name, unsigned w, unsigned h, int pm);

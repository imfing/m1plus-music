/* Small helpers every page of the payload shares (patch/common.h).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "radio.h"
#include "shot.h"
#include "covercache.h"

/* The library scan's folder walk (tools/pod.py SCAN_SITE, docs/modules/payload.md hook 5): stock skips a directory entry when strcmp(name, ".") is 0 (and then ".." and a list of
 * system folders); the call is replaced by `jal pod_scan_dir`, whose delay slot still loads a1 = ".". A hidden folder (a name starting with '.') counts as a match, so
 * /mnt/mmc/.m1plus/ (our cache, covers and downloads) never joins Songs and Albums; anything else is stock's strcmp. (q2-pod's ringnav_scan_dir.) */
__attribute__((noinline)) int pod_scan_dir(const char *name, const char *dot) {
    return name[0] == '.' ? 0 : strcmp(name, dot);
}

/* A widget's text as UTF-8 in buf (size bytes, never written past): stock widget_get_text_utf8 ignores its size for a wide text (tk_utf8_from_utf16 at 0x70e790 overwrites
 * its out_size argument before reading it, counts the whole encoding and writes all of it), so a long lyric line or tag overran the caller's stack buffer. This reads the wide
 * text (widget_get_text) and encodes it here: a text that does not fit is cut at a character boundary, buf is always NUL terminated (size >= 1). Returns the length the whole
 * text needs (snprintf's), so the text fitted when the result is below size; -1 when the widget has no text (buf is then empty). A code point beyond U+10FFFF or a surrogate is U+FFFD. */
int pod_text_utf8(void *widget, char *buf, unsigned size) {
    const unsigned *t = widget ? widget_get_text(widget) : (const unsigned *)0;
    unsigned n = 0, w = 0, c, len, cut = 0;
    char e[4];
    if (!size) return -1;
    buf[0] = 0;
    if (!t) return -1;
    for (; (c = *t) != 0; ++t) {
        if (c > 0x10ffff || (c >= 0xd800 && c < 0xe000)) c = 0xfffd;
        if (c < 0x80) {
            e[0] = (char)c, len = 1;
        } else if (c < 0x800) {
            e[0] = (char)(0xc0 | c >> 6), e[1] = (char)(0x80 | (c & 0x3f)), len = 2;
        } else if (c < 0x10000) {
            e[0] = (char)(0xe0 | c >> 12), e[1] = (char)(0x80 | (c >> 6 & 0x3f)), e[2] = (char)(0x80 | (c & 0x3f)),
            len = 3;
        } else {
            e[0] = (char)(0xf0 | c >> 18), e[1] = (char)(0x80 | (c >> 12 & 0x3f)),
            e[2] = (char)(0x80 | (c >> 6 & 0x3f)), e[3] = (char)(0x80 | (c & 0x3f)), len = 4;
        }
        /* (room for the character and the NUL; once one does not fit, the rest only counts) */
        if (!cut && w + len < size) {
            unsigned k;
            for (k = 0; k < len; ++k) buf[w + k] = e[k];
            buf[w += len] = 0;
        } else {
            cut = 1;
        }
        n += len;
    }
    return (int)n;
}

/* The n bytes at in with each %XX (hex digits of either case) decoded to its byte, into out (size bytes, never written past, always NUL terminated; size >= 1). A '%' not followed
 * by two hex digits stays as it is. Stops when the next byte does not fit (a cut can split a UTF-8 character: the caller trims). Returns the length written. */
unsigned pod_url_decode(char *out, unsigned size, const char *in, unsigned n) {
    unsigned o = 0, i;
    if (!size) return 0;
    for (i = 0; i < n && o + 1 < size; ++i) {
        unsigned char c = (unsigned char)in[i];
        if (c == '%' && i + 2 < n) {
            int h = 0, l = 0, k;
            for (k = 1; k <= 2; ++k) {
                unsigned char d = (unsigned char)in[i + k];
                int v = d - '0' < 10u ? d - '0' : (d | 32) - 'a' < 6u ? (d | 32) - 'a' + 10 : -1;
                if (k == 1)
                    h = v;
                else
                    l = v;
            }
            if (h >= 0 && l >= 0) c = (unsigned char)(h << 4 | l), i += 2;
        }
        out[o++] = (char)c;
    }
    out[o] = 0;
    return o;
}

int pod_screen_lit(void) { return *(volatile unsigned char *)BACKLIGHT_STATUS != 0; }

/* Whether the card is mounted: its mount point is another file system than the one it is in (an unmounted /mnt/mmc is a plain directory on the internal flash). */
int pod_card_mounted(void) {
    unsigned a[32], b[32];
    memset(a, 0, sizeof a);
    memset(b, 0, sizeof b);
    if (statfs(SHOT_CARD, a) || statfs(SHOT_PARENT, b)) return 0;
    return !(a[0] == b[0] && a[8] == b[8] &&
             a[9] == b[9]); /* f_type, f_fsid (MIPS o32 statfs words 0, 8, 9): the same, nothing mounted */
}

/* The one writer of the payload's card files: CARD_DIR then dir made (EEXIST is fine; a failure shows in the open), a then b (either may
 * be empty) into tmp, fsync, rename onto path, fsync of dir. 0 on success; -1, and nothing written, while the card is not mounted. */
int pod_card_write(const char *dir, const char *path, const char *tmp, const void *a, unsigned na, const void *b,
                   unsigned nb) {
    int fd, ok, d;
    if (!pod_card_mounted()) return -1; /* never write to the internal flash under the mount point */
    mkdir(CARD_DIR, 0755);
    if (strcmp(dir, CARD_DIR)) mkdir(dir, 0755);
    fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return -1;
    ok = (!na || write(fd, a, na) == (int)na) && (!nb || write(fd, b, nb) == (int)nb) && fsync(fd) == 0;
    ok = (close(fd) == 0) && ok;
    if (!ok || rename(tmp, path) != 0) {
        unlink(tmp);
        return -1;
    }
    d = open(dir, O_RDONLY, 0);
    if (d < 0) return -1;
    ok = fsync(d) == 0;
    return (close(d) == 0 && ok) ? 0 : -1;
}

int pod_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    navigator_back();
    return RET_OK;
}

/* Every Now Playing entry of our pages: Radio's page while a station plays, else stock's player (the trampoline: the hook on stock's handler would decide again). */
void pod_open_now_playing(void) {
    if (!rn_open_if_active()) stock_backtoplayer_trampoline((void *)0, (void *)0);
}

int pod_on_player(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pod_open_now_playing();
    return RET_OK;
}

int pod_is_type(void *w, const char *type) {
    const char *t = w ? widget_get_type(w) : (const char *)0;
    return t && strcmp(t, type) == 0;
}

/* The topmost opened window called name in the window manager is brought to the front the way stock brings the player back (window_manager_switch_to, nothing closed, Back returns to where the user came from).
 * Stock's navigator_to opens a page that has no single_instance property afresh each time, so a page left in the stack (the top-right Now Playing button restacks the player over it) would be stacked twice. */
void *pod_restack_window(const char *name) {
    void *wm = window_manager();
    unsigned n;
    if (!wm) return (void *)0;
    for (n = widget_count_children(wm); n--;) {
        void *w = widget_get_child(wm, n);
        const char *nm = w ? *(const char **)((char *)w + WIDGET_NAME) : (const char *)0;
        if (nm && !strcmp(nm, name)) {
            if (!widget_is_window_opened(w)) return (void *)0; /* (a page that is closing is gone) */
            return window_manager_switch_to(wm, window_manager_get_top_window(wm), w, 0) == RET_OK ? w : (void *)0;
        }
    }
    return (void *)0;
}

/* A stock page opened the way the stock lists would, without stacking a second window of a page that has no single_instance property: the opened window is restacked, else navigator_to(path).
 * window is NULL for a page that must be opened afresh because its init starts or reads something that a restack does not redo: stock's restack sends EVT_WINDOW_TO_FG (0x12d) to the page and EVT_WINDOW_TO_BG (0x12c) to the window it leaves, and
 * only a new open runs init. Wi-Fi (init 0x4b1048 calls wifi_scan on every open, its 0x12d handler 0x4b0a34 only rebuilds the list), Bluetooth (its 0x12c handler 0x4a2a20 calls btStopSearch, its 0x12d handler 0x4a3a28 does not restart discovery, init 0x4a411c does) are opened afresh. */
int pod_open_stock(const char *path, const char *window) {
    if (window && pod_restack_window(window)) return RET_OK;
    return navigator_to(path);
}

/* The navbar's small title of a page with a large heading: shown once the heading has scrolled away, i.e. the scroll offset has reached SG_COLLAPSE, or, on a page whose
 * heading is a header's name (a playlist, a podcast show), `head` (the offset the name has gone at). The page ORs in its own conditions (select mode, no scroll events ...). */
int pod_title_gone(int off, int head) { return off >= (head ? head : SG_COLLAPSE); }

/* Show or hide the small title w when `on` differs from *cur. */
void pod_title_set(void *w, int *cur, int on) {
    if (on == *cur) return;
    *cur = on;
    if (w) widget_set_visible(w, on, 0);
}

/* A translated "%d songs" with the number put where the translation has its %d. The table's text is never a printf format. */
void pod_fmt(char *out, unsigned size, const char *f, int n) {
    char digits[12];
    unsigned o = 0, d = 0, i;
    for (i = (unsigned)(n < 0 ? 0 : n); d == 0 || i; i /= 10) digits[d++] = (char)('0' + i % 10);
    while (*f && o + 1 < size) {
        if (f[0] == '%' && f[1] == 'd') {
            while (d && o + 1 < size) out[o++] = digits[--d];
            f += 2;
        } else
            out[o++] = *f++;
    }
    out[o] = 0;
}

void *pod_bind(void *win, const char *name, int (*fn)(void *, void *), const void *ctx) {
    void *w = widget_lookup(win, name, 1);
    if (w && fn) widget_on(w, EVT_CLICK, fn, (void *)ctx);
    return w;
}

/* The cover tint (Now Playing's, patch/nowplaying.c, and the album page's, patch/albumpage.c). Value: NP_V_MIN + v *
 * (NP_V_MAX - NP_V_MIN) / 255 for the brightest channel v; every channel keeps NP_SAT_NUM / NP_SAT_DEN of its distance
 * from v (a grey stays grey). A black cover is the neutral tone. With NP_V_MAX 192 white text keeps 4.5:1 under the
 * gradients of both pages (test/pod/nowplaying.py, test/pod/albumpage.py). */
__attribute__((noinline)) unsigned pod_tone(unsigned r, unsigned g, unsigned b) {
    unsigned v = r > g ? r : g, c[3], i, vt;
    if (b > v) v = b;
    if (!v) return NP_NEUTRAL;
    c[0] = r, c[1] = g, c[2] = b;
    vt = NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) / 255;
    for (i = 0; i < 3; ++i) c[i] = vt - vt * NP_SAT_NUM * (v - c[i]) / (NP_SAT_DEN * v);
    return 0xff000000u | c[0] | c[1] << 8 | c[2] << 16;
}

/* The status bar (a window of the window manager, vtable type "system_bar") in a page's top-edge colour. One owner at a time:
 * the window that last tinted it. Only the owner can put the stock black back, so a page that is replaced or covered after the
 * next page has taken the bar over (Play, Back) never undoes the new owner's colour. */
#define POD_LUM(r, g, b) (2126u * (r) * (r) + 7152u * (g) * (g) + 722u * (b) * (b))
static void *bar_owner __attribute__((section(".scratch")));

__attribute__((noinline)) unsigned pod_bar_color(unsigned color) {
    unsigned r = color & 255, g = color >> 8 & 255, b = color >> 16 & 255;
    while (POD_LUM(r, g, b) > NP_BAR_LUM_MAX) r = r * 15 >> 4, g = g * 15 >> 4, b = b * 15 >> 4;
    return pal_not_role(0xff000000u | r | g << 8 | b << 16);
}

static void *bar_find(void) {
    void *wm = window_manager(), *w;
    unsigned i, n;
    if (!wm) return (void *)0;
    for (n = widget_count_children(wm), i = 0; i < n; ++i) {
        w = widget_get_child(wm, i);
        if (pod_is_type(w, "system_bar")) return w; /* the navbar is "system_bar_bottom" */
    }
    return (void *)0;
}

static int bar_set(unsigned color) {
    void *bar = bar_find();
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    if (!bar) return 0;
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    if (widget_set_style(bar, "normal:bg_color", v) != RET_OK) return 0;
    widget_invalidate_force(bar, (void *)0);
    return 1;
}

__attribute__((noinline)) int pod_bar_tint(void *win, unsigned color) {
    if (!win || !bar_set(pod_bar_color(color))) return 0; /* a failed call keeps what the bar has (and owes) */
    bar_owner = win;
    return 1;
}

__attribute__((noinline)) void pod_bar_black(void *win) {
    if (!win || bar_owner != win) return;
    bar_owner = (void *)0;
    bar_set(NP_BAR_STOCK);
}

__attribute__((noinline)) int pod_is_top(void *win) {
    void *wm = window_manager();
    return win && wm && window_manager_get_top_main_window(wm) == win;
}

/* The tone cache: album key (cc_album_key) -> pod_tone word, RAM only, fixed size, least recently used out. Both pages look
 * an album up before they decode a cover; a miss is decoded once and inserted. A key is never 0 (0 marks a free entry). */
static struct {
    unsigned key, tone, used;
} tone_tab[TONE_CACHE_N] __attribute__((section(".scratch")));
static unsigned tone_clock __attribute__((section(".scratch")));

__attribute__((noinline)) int pod_tone_get(unsigned key, unsigned *tone) {
    unsigned i;
    if (!key) return 0;
    for (i = 0; i < TONE_CACHE_N; ++i)
        if (tone_tab[i].key == key) {
            tone_tab[i].used = ++tone_clock;
            *tone = tone_tab[i].tone;
            return 1;
        }
    return 0;
}

__attribute__((noinline)) void pod_tone_put(unsigned key, unsigned tone) {
    unsigned i, at = 0;
    if (!key) return;
    for (i = 0; i < TONE_CACHE_N; ++i) {
        if (tone_tab[i].key == key) {
            at = i;
            break;
        } /* the same album again: replaced in place */
        if (!tone_tab[i].key) {
            at = i;
            break;
        } /* the first free entry */
        if (tone_tab[i].used < tone_tab[at].used) at = i; /* else the least recently used */
    }
    tone_tab[at].key = key, tone_tab[at].tone = tone, tone_tab[at].used = ++tone_clock;
}

__attribute__((noinline)) unsigned pod_alpha(unsigned y, unsigned a_top, unsigned a_bot, unsigned rows) {
    if (y >= rows - 1) return a_bot;
    return a_top + ((a_bot - a_top) * y + (rows - 1) / 2) / (rows - 1);
}

__attribute__((noinline)) unsigned pod_shade(unsigned color, unsigned y, unsigned a_top, unsigned a_bot,
                                             unsigned rows) {
    unsigned keep = 255 - pod_alpha(y, a_top, a_bot, rows);
    return pal_not_role((color & 255) * keep / 255 | (color >> 8 & 255) * keep / 255 << 8 |
                        (color >> 16 & 255) * keep / 255 << 16);
}

/* The coverage of the area outside a quarter circle of radius r in the corner square of r pixels (the circle's centre at
 * the square's inner corner), 0..255: each pixel is sampled 8 x 8 times. */
__attribute__((noinline)) void pod_corner_fill(unsigned char *tab, unsigned r) {
    unsigned x, y, i, j, n, c = 2 * 8 * r;
    for (y = 0; y < r; ++y)
        for (x = 0; x < r; ++x) {
            for (n = 0, i = 0; i < 8; ++i)
                for (j = 0; j < 8; ++j) {
                    int dx = (int)(2 * (x * 8 + i) + 1) - (int)c, dy = (int)(2 * (y * 8 + j) + 1) - (int)c;
                    n += (unsigned)(dx * dx + dy * dy) > c * c;
                }
            tab[y * r + x] = (unsigned char)((n * 255 + 32) / 64);
        }
}

__attribute__((noinline)) void pod_corners(void *canvas, const unsigned char *tab, unsigned r, unsigned side,
                                           unsigned color, int row0, unsigned a_top, unsigned a_bot, unsigned rows) {
    unsigned k, x, y;
    for (k = 0; k < 4; ++k)
        for (y = 0; y < r; ++y) {
            unsigned ly = k & 2 ? side - 1 - y : y;
            int row = row0 + (int)ly;
            unsigned shade = pod_shade(color, row < 0 ? 0 : (unsigned)row, a_top, a_bot, rows);
            for (x = 0; x < r; ++x) {
                unsigned a = tab[y * r + x];
                if (!a) continue;
                ui_fill_color(canvas, shade | a << 24);
                canvas_fill_rect(canvas, k & 1 ? side - 1 - x : x, ly, 1, 1);
            }
        }
}

void pod_pill_place(pod_pill_t *p, int y) {
    const unsigned *text = widget_get_text(p->ptext);
    float w = text && *text ? widget_measure_text(p->ptext, text) : 0.0f;
    int tw = (int)(w + 0.999f), x;
    if (tw <= 0 || AH_PILL_GLYPH + AH_PILL_GAP + tw > AH_PLAY_W) tw = AB_PLAY_TEXT_W;
    x = AH_PLAY_X + (AH_PLAY_W - (AH_PILL_GLYPH + AH_PILL_GAP + tw)) / 2;
    widget_move(p->glyph, x, y + (AH_BTN_H - AH_PILL_GLYPH) / 2);
    p->tx = x + AH_PILL_GLYPH + AH_PILL_GAP, p->tw = tw + AB_TEXT_SLACK;
}

void pod_pill_paint(const pod_pill_t *p, void *canvas, int y) {
    const unsigned *text = widget_get_text(p->ptext);
    unsigned n = 0;
    int rect[4];
    while (text && text[n]) ++n;
    rect[0] = p->tx, rect[1] = y + (AH_BTN_H - AB_TEXT_H) / 2, rect[2] = p->tw, rect[3] = AB_TEXT_H;
    widget_prepare_text_style(p->ptext, canvas);
    if (n) canvas_draw_text_in_rect(canvas, text, n, rect);
}

/* The pills: the glyph and the label centred as a pair SG_PILL_GAP apart (the flat pills of the Songs, Folders and artist pages, the select bars'): AWTK puts the glyph in a
 * square as high as the button at margin_left and the text at the square's end plus the spacer. Moved from patch/songs.c. */
void pod_centre_pill(void *btn, int pw) {
    static const char *const key[5] = {"normal:", "pressed:", "over:", "focused:", "disable:"};
    static const char *const prop[5] = {"margin_left", "icon_at", "margin_right", "spacer", "text_align_h"};
    const unsigned *text = widget_get_text(btn);
    float w = text && *text ? widget_measure_text(btn, text) : 0.0f;
    int tw = (int)(w + 0.999f), margin, i, j;
    unsigned v[4], val[5]; /* value_t: type at 0, the uint32 at 8 */
    char name[32];
    if (!text || !*text)
        return; /* (a text that cannot be measured is taken as 0 px wide: the glyph is still put at the left, not above the text as the automatic icon position would) */
    if (tw > pw - (SG_PILL_H - SG_PILL_GLYPH) / 2 - SG_PILL_GLYPH -
                 SG_PILL_GAP) { /* too wide beside the glyph (ru "Перемешать"): the label steps down to
                                                                                      * SG_PILL_PX_SMALL, as an iOS button shrinks its title, and is measured again */
        for (i = 0; i < 5; ++i) {
            unsigned k = 0, m = 0;
            static const char fs[] = "font_size";
            while (key[i][k]) name[k] = key[i][k], ++k;
            while (fs[m]) name[k++] = fs[m++];
            name[k] = 0;
            memset(v, 0, sizeof v);
            value_set_uint32(v, SG_PILL_PX_SMALL);
            widget_set_style(btn, name, v);
        }
        w = widget_measure_text(btn, text);
        tw = (int)(w + 0.999f);
    }
    margin = (pw - (SG_PILL_GLYPH + SG_PILL_GAP + tw)) / 2 - (SG_PILL_H - SG_PILL_GLYPH) / 2;
    if (margin < 0) margin = 0;
    val[0] = (unsigned)margin, val[1] = 1, val[2] = 0,
    val[3] = (unsigned)(SG_PILL_GAP - (SG_PILL_H - SG_PILL_GLYPH) / 2),
    val[4] = 2; /* icon_at left, text_align_h left */
    for (j = 0; j < 5; ++j) {
        memset(v, 0, sizeof v);
        value_set_uint32(v, val[j]);
        for (i = 0; i < 5; ++i) {
            unsigned k = 0, m = 0;
            while (key[i][k]) name[k] = key[i][k], ++k;
            while (prop[j][m]) name[k++] = prop[j][m++];
            name[k] = 0;
            widget_set_style(btn, name, v);
        }
    }
}

/* A select mark: the stock image (26 px) as a bitmap, cut to its circle. cc_decode flattens the image over black, so the square
 * around the ring would be black on a cover (the Playlists grid): every pixel's alpha becomes its coverage by the ink's circle
 * (the stock unselect / selected images: ink 2 .. 23, a circle of radius SG_MARK_INK centred in the square; 8 x 8 samples a pixel),
 * so only the ring and what it holds are drawn. Over the Songs page's black it looks as before. */
#define SG_MARK_INK 11
void *pod_make_mark(void *win, const char *name) {
    unsigned *px, x, y, i, j, n, c = 8 * SG_MARK, rr = 2 * 8 * SG_MARK_INK;
    void *b = bitmap_create_ex(SG_MARK, SG_MARK, SG_MARK * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != SG_MARK * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, name, 1, SG_MARK, 1, px);
    for (y = 0; ok && y < SG_MARK; ++y)
        for (x = 0; x < SG_MARK; ++x) {
            for (n = 0, i = 0; i < 8; ++i)
                for (j = 0; j < 8;
                     ++j) { /* (coordinates doubled: the sample centres are odd, the circle's centre is c) */
                    int dx = (int)(2 * (x * 8 + i) + 1) - (int)c, dy = (int)(2 * (y * 8 + j) + 1) - (int)c;
                    n += (unsigned)(dx * dx + dy * dy) <= rr * rr;
                }
            px[y * SG_MARK + x] = (px[y * SG_MARK + x] & 0xffffff) | ((n * 255 + 32) / 64) << 24;
        }
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

/* The chevron: a stroke of two segments (the stock right_arrow is 13 x 22 and our image loader only makes squares), antialiased by 4 x 4 samples per pixel, in the
 * alpha of a grey bitmap (the rail's disc is made the same way). Coordinates are eighths of a pixel. */
static int pod_seg2(int px, int py, int ax, int ay, int bx,
                    int by) { /* the squared distance of (px, py) to the segment a-b */
    int dx = bx - ax, dy = by - ay, n = (px - ax) * dx + (py - ay) * dy, d = dx * dx + dy * dy, cx, cy, cr;
    if (n <= 0)
        cx = px - ax, cy = py - ay;
    else if (n >= d)
        cx = px - bx, cy = py - by;
    else {
        cr = (px - ax) * dy - (py - ay) * dx; /* the cross product: distance = |cr| / sqrt(d) */
        return cr * cr / d;
    }
    return cx * cx + cy * cy;
}

void *pod_make_cross(void) {
    unsigned *px;
    int x, y, i, j, n, d, e;
    void *b = bitmap_create_ex(POD_CROSS, POD_CROSS, POD_CROSS * 4, BITMAP_RGBA8888);
    if (!b) return (void *)0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != POD_CROSS * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    e = POD_CROSS * 8 - 16; /* the strokes run from 2 px in from each corner */
    for (y = 0; y < POD_CROSS; ++y)
        for (x = 0; x < POD_CROSS; ++x) {
            for (n = 0, i = 0; i < 4; ++i)
                for (j = 0; j < 4; ++j) {
                    int sx = x * 8 + 2 * j + 1, sy = y * 8 + 2 * i + 1;
                    d = pod_seg2(sx, sy, 16, 16, e, e);
                    if (pod_seg2(sx, sy, e, 16, 16, e) < d) d = pod_seg2(sx, sy, e, 16, 16, e);
                    if (d <= 49) ++n; /* a stroke 1.75 px wide */
                }
            px[y * POD_CROSS + x] = (unsigned)(n * 255 / 16) << 24 | POD_CHEV_RGB;
        }
    bitmap_unlock_buffer(b);
    return b;
}

void *pod_make_chevron(void) {
    unsigned *px;
    int x, y, i, j, n, d;
    void *b = bitmap_create_ex(POD_CHEV_W, POD_CHEV_H, POD_CHEV_W * 4, BITMAP_RGBA8888);
    if (!b) return (void *)0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != POD_CHEV_W * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    for (y = 0; y < POD_CHEV_H; ++y)
        for (x = 0; x < POD_CHEV_W; ++x) {
            for (n = 0, i = 0; i < 4; ++i)
                for (j = 0; j < 4; ++j) {
                    int sx = x * 8 + 2 * j + 1, sy = y * 8 + 2 * i + 1;
                    d = pod_seg2(sx, sy, 14, 14, 68, 64);
                    if (pod_seg2(sx, sy, 68, 64, 14, 114) < d) d = pod_seg2(sx, sy, 68, 64, 14, 114);
                    if (d <= 64) ++n; /* half the stroke's width: 1 px */
                }
            px[y * POD_CHEV_W + x] = (unsigned)(n * 255 / 16) << 24 | POD_CHEV_RGB;
        }
    bitmap_unlock_buffer(b);
    return b;
}

/* One row of a shape: x .. x + w - 1 of row y of the canvas, in colour c, only when the row is inside the view (rows 0 .. view_h - 1). */
static void pod_fill_row(void *canvas, int view_h, int x, int y, int w, unsigned c) {
    if (w <= 0 || y < 0 || y >= view_h) return;
    ui_fill_color(canvas, c);
    canvas_fill_rect(canvas, x, y, w, 1);
}

/* The integer square root of v (the largest s with s * s <= v). */
static unsigned pod_isqrt(unsigned v) {
    unsigned s = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    for (; bit; bit >>= 2)
        if (v >= s + bit)
            v -= s + bit, s = (s >> 1) + bit;
        else
            s >>= 1;
    return s;
}

void pod_capsule(void *canvas, int view_h, int x, int y, int w, int h, int r, unsigned c) {
    int i, top, bottom;
    unsigned a;
    if (r > h / 2) r = h / 2;
    if (r > w / 2) r = w / 2;
    if (r < 0) r = 0;
    /* the corner rows, from the outside in: the circle's chord on the row's middle, its ends smoothed by a pixel of partial cover */
    for (i = 0; i < r; ++i) {
        int dy = 2 * (r - i) - 1, inset, x0, f;
        inset = r * 256 - (int)(pod_isqrt((unsigned)(4 * r * r - dy * dy) << 16) / 2); /* in 1/256 px */
        x0 = inset >> 8, f = inset & 255;
        a = (unsigned)(255 - f);
        top = y + i, bottom = y + h - 1 - i;
        if (f) {
            unsigned edge = (c & 0x00ffffffu) | (((c >> 24) * a / 255) << 24);
            pod_fill_row(canvas, view_h, x + x0, top, 1, edge);
            pod_fill_row(canvas, view_h, x + w - 1 - x0, top, 1, edge);
            pod_fill_row(canvas, view_h, x + x0, bottom, 1, edge);
            pod_fill_row(canvas, view_h, x + w - 1 - x0, bottom, 1, edge);
            ++x0;
        }
        pod_fill_row(canvas, view_h, x + x0, top, w - 2 * x0, c);
        pod_fill_row(canvas, view_h, x + x0, bottom, w - 2 * x0, c);
    }
    top = y + r, bottom = y + h - r;
    if (top < 0) top = 0;
    if (bottom > view_h) bottom = view_h;
    if (bottom > top) {
        ui_fill_color(canvas, c);
        canvas_fill_rect(canvas, x, top, w, bottom - top);
    }
}

void pod_segmented(void *canvas, int view_h, int x, int y, int w, int h, int n, int sel, void *st_on, void *st_off,
                   const unsigned *const *label, const int *len) {
    int seg = (w - 2 * SEG_PAD) / n, k, rect[4];
    if (n < 1) return;
    pod_capsule(canvas, view_h, x, y, w, h, h / 2, SEG_TRACK);
    pod_capsule(canvas, view_h, x + SEG_PAD + sel * seg, y + SEG_PAD, sel == n - 1 ? w - 2 * SEG_PAD - sel * seg : seg,
                h - 2 * SEG_PAD, (h - 2 * SEG_PAD) / 2, SEG_THUMB);
    /* a short hairline between two segments that are both unselected (none next to the thumb) */
    for (k = 1; k < n; ++k)
        if (k - 1 != sel && k != sel && y + h / 4 >= 0 && y + h - h / 4 <= view_h) {
            ui_fill_color(canvas, SEG_SEP);
            canvas_fill_rect(canvas, x + SEG_PAD + k * seg, y + h / 4, 1, h / 2);
        }
    /* the labels, each centred in its segment: the selected one on the thumb in the dark ink */
    for (k = 0; k < n; ++k) {
        void *st = k == sel ? st_on : st_off;
        int tw;
        widget_prepare_text_style(st, canvas);
        tw = (int)(widget_measure_text(st, label[k]) + 0.999f);
        rect[0] = x + SEG_PAD + k * seg + (seg - tw) / 2, rect[1] = y + (h - SEG_LABEL_H) / 2, rect[2] = tw + 2,
        rect[3] = SEG_LABEL_H;
        if (len[k] > 0 && rect[1] >= 0 && rect[1] + SEG_LABEL_H <= view_h)
            canvas_draw_text_in_rect(canvas, label[k], (unsigned)len[k], rect);
    }
}

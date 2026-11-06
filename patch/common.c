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
 * next page has taken the bar over (Play all, Back) never undoes the new owner's colour. */
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

/* The pills: the glyph and the label centred as a pair SG_PILL_GAP apart (the album page's Play all, patch/albumpage.c): AWTK puts the glyph in a
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

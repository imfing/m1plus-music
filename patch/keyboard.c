/* M1+ Music's own on-screen QWERTY keyboard: one page, ui/m1plus_keyboard.bin (docs/modules/keyboard.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Stock's T9 popup (ui/user_keyboard.bin) is laid out 640 px wide in a 320 px popup; this is a page of ordinary AWTK buttons instead: 26 char keys the payload
 * moves, relabels and hides per page (lowercase, uppercase, 123 and #+=), the function keys, a search field (a grey hint, the text, a caret and a clear button) and
 * the key pop-up. The geometry is tools/pod_keyboard.py's (the asset is the lowercase page) and patch/keyboard.h's. Everything is an event handler of the page's
 * own widgets: no hook, no timer except the delete key's repeat (armed only while that key is held), nothing at boot, in the main loop or at paint.
 *
 * Typing: a char key inserts its label when the finger lifts on it (a click); while it is down a balloon with the letter stands above it (the pop-up: two insensitive
 * views, a stem over the key and a balloon over it). Shift is one-shot: the field starts on the uppercase page when it is empty, the first letter goes back to
 * lowercase, an emptied field turns shift on again; shift's key shows the state (the widget kb_shift, or kb_shifton while on). 123 and ABC switch the page, #+= and
 * 123 on the third row go between the two symbol pages. Delete works on touch down and repeats while held. Search (empty text: nothing) closes the page and calls
 * on_done with the text; Back closes it and calls on_cancel. A text too wide for the field shows its end after an ellipsis; the caret follows the measured width.
 * A touch on the pad that lands on no key (a gap, a margin) goes to the nearest key, as on an iPhone: the pad's own touch events resolve it and press that key.
 *
 * Keyboards (Settings > Keyboards): English is always there. With Chinese (Pinyin) on, a language key sits in row four and the Chinese layer composes pinyin with stock's Google
 * Pinyin engine (the shipped gpinyin.dat, opened when the layer is first used and closed with the page): the letters build the pinyin in a candidate strip above the pad, the
 * candidates scroll sideways, a tap takes one (a long input in steps), space takes the first, and after a commit the strip offers the words that usually follow. A layer is a struct
 * of functions (struct kb_layer): key labels per page come from the page tables, compose / backspace / flush / pending are the layer's, so a Korean or kana composer can plug in.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "keyboard.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */

#define PY_ENGINE_PTR \
    (*(void *volatile *) \
         PY_ENGINE) /* the engine's global MatrixSearch*; its first byte is inited_ (docs/modules/addresses.md) */
#define py_predicts \
    _ZN10ime_pinyin12MatrixSearch12get_predictsEPKtPA8_tj /* get_predicts(this, history, out[][8], n): what follows */

enum { P_LOWER = 0, P_UPPER = 1, P_NUM = 2, P_SYM = 3 };
enum { L_EN = 0, L_ZH = 1 };
enum { S_NONE = 0, S_PINYIN = 1, S_PRED = 2 }; /* what the candidate strip shows */
enum {
    K_DEL = 100,
    K_SHIFT,
    K_SHIFTON,
    K_SYM,
    K_MODE,
    K_LANG,
    K_SPACE,
    K_GO
}; /* ids of the function keys (the char keys are 0 .. KB_KEYS - 1) */

#define KB_TOP (KB_WIN_H - KB_H) /* the pad's top in the window */
#define KB_RIGHT (KB_W - 1 - KB_FN_W) /* delete's left edge */
#define KB_ROW2_Y (KB_PAD + 2 * KB_PITCH)
#define KB_ROW3_Y (KB_PAD + 3 * KB_PITCH)
#define KB_LANG_X (KB_EDGE + KB_MODE_W + KB_GAP) /* the language key; without it space starts here */
#define KB_GO_X (KB_W - 1 - KB_MODE_W)
#define KB_NRECT \
    (KB_KEYS + 7) /* the rectangles a touch is measured against: char keys, shift / sym, del, mode, lang, space, go */

static const char *const KB_ROWS[4][3] = {
    {"qwertyuiop", "asdfghjkl", "zxcvbnm"},
    {"QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"},
    {"1234567890", "-/:;()$&@\"", ".,?!'"},
    {"[]{}#%^*+=", "_\\|~<>€£¥`", ".,?!'"},
};

/* A keyboard layer: the part of typing that differs per language. English has none of the hooks (letters type as they are); the Chinese layer composes pinyin. */
struct kb_layer {
    const char *tag; /* what the language key shows while this layer is the one a tap goes to */
    int (*enter)(void); /* 0 when ready (the engine is open) */
    void (*leave)(void);
    int (*compose)(int c); /* a letter key on the layer's letter page: 1 when it was taken into the composition */
    int (*backspace)(void); /* delete: 1 when it removed something of the composition */
    void (*flush)(void); /* commit what is pending (space, Search, a page or layer switch) */
    int (*pending)(void); /* something is being composed */
    void (*reset)(void); /* forget it (clear) */
};

static const struct kb_layer *kb_layer_of(int layer);

static struct {
    void *win, *pad, *title, *text, *hint, *caret, *clear, *stem, *pop, *pop_l;
    void *key[KB_KEYS];
    void *shift, *shifton, *sym, *del, *mode, *space, *go, *lang;
    void *strip, *py, *sep, *cands, *chl, *item[KB_POOL];
    int page, geo, popped, held, hold, finished, seen_n, seen_x, seen_y, gap, layers, layer, nkeys;
    unsigned timer, len, flags, seen_t;
    kb_done_fn done;
    kb_cancel_fn cancel;
    kb_change_fn on_change; /* embedded: called with the field's text whenever it may have changed */
    kb_go_fn on_go; /* embedded: the action key */
    int mask, go_off; /* the field shows dots; the action key is dimmed and inert */
    int embedded, hidden, tx, tw,
        cy; /* embedded in another page (keyboard_attach); the pad is hidden; the field's text x, text room and caret y */
    short kx[KB_KEYS], ky[KB_KEYS], kw[KB_KEYS];
    char lab[KB_KEYS][4];
    char buf[KB_MAX_LONG + 1];
    unsigned max; /* the limit of this keyboard's text: KB_MAX, or KB_MAX_LONG with KB_LONG */
} kb __attribute__((section(".scratch")));

/* The Chinese layer's state: the pinyin typed, the engine's answer, the candidates read (UTF-8 in a pool, their x offsets in the strip), the strip's scroll and press. */
static struct {
    char raw[KB_RAW_MAX + 2];
    unsigned raw_n;
    int src, total, ncand, pool_n, nsp, sx, pyw, down, dx, sx0, drag, hot, own, ready;
    short off[KB_MAX_CAND + 1], soff[KB_MAX_CAND];
    unsigned short sp[KB_RAW_MAX + 2];
    unsigned short slot[KB_POOL]; /* the candidate (+ 1) each item widget shows, 0 for none */
    char pool[KB_POOL_BYTES];
} zh __attribute__((section(".scratch")));

static int kb_memo __attribute__((section(
    ".scratch"))); /* the layer the last keyboard ended on: the session's choice (the page's state is cleared with the page) */

static unsigned kb_slen(const char *s) {
    unsigned n = 0;
    while (s[n]) n++;
    return n;
}

static unsigned kb_clen(const char *s) { /* the bytes of the UTF-8 character at s */
    unsigned char c = (unsigned char)*s;
    return c < 0x80 ? 1 : c < 0xe0 ? 2 : c < 0xf0 ? 3 : 4;
}

static void kb_show(void *w, int on) { /* hide = invisible and insensitive: an invisible widget still takes touches */
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* UTF-16 (a surrogate pair is one character, a lone surrogate U+FFFD) to UTF-8 in out[cap], NUL-terminated and never cut inside a character; returns the length. */
static unsigned u16_to_u8(const unsigned short *s, char *out, unsigned cap) {
    unsigned n = 0;
    while (*s) {
        unsigned cp = *s++, k;
        if (cp >= 0xd800 && cp < 0xdc00 && *s >= 0xdc00 && *s < 0xe000)
            cp = 0x10000 + ((cp - 0xd800) << 10) + (unsigned)(*s++ - 0xdc00);
        else if (cp >= 0xd800 && cp < 0xe000)
            cp = 0xfffd;
        k = cp < 0x80 ? 1u : cp < 0x800 ? 2u : cp < 0x10000 ? 3u : 4u;
        if (n + k + 1 > cap) break;
        if (k == 1)
            out[n] = (char)cp;
        else if (k == 2) {
            out[n] = (char)(0xc0 | (cp >> 6));
            out[n + 1] = (char)(0x80 | (cp & 63));
        } else if (k == 3) {
            out[n] = (char)(0xe0 | (cp >> 12));
            out[n + 1] = (char)(0x80 | ((cp >> 6) & 63));
            out[n + 2] = (char)(0x80 | (cp & 63));
        } else {
            out[n] = (char)(0xf0 | (cp >> 18));
            out[n + 1] = (char)(0x80 | ((cp >> 12) & 63));
            out[n + 2] = (char)(0x80 | ((cp >> 6) & 63));
            out[n + 3] = (char)(0x80 | (cp & 63));
        }
        n += k;
    }
    out[n] = 0;
    return n;
}

/* The three byte UTF-8 characters of s[0..n) as UTF-16 into out[cap] (zero-terminated; a character outside the BMP ends it); returns the units. */
static unsigned u8_to_u16(const char *s, unsigned n, unsigned short *out, unsigned cap) {
    unsigned i = 0, k = 0;
    while (i < n && k + 1 < cap) {
        unsigned char c = (unsigned char)s[i];
        if (c < 0x80) {
            out[k++] = c;
            i++;
        } else if (c < 0xe0 && i + 1 < n) {
            out[k++] = (unsigned short)(((c & 31) << 6) | (s[i + 1] & 63));
            i += 2;
        } else if (c < 0xf0 && i + 2 < n) {
            out[k++] = (unsigned short)(((c & 15) << 12) | ((s[i + 1] & 63) << 6) | (s[i + 2] & 63));
            i += 3;
        } else
            break;
    }
    out[k] = 0;
    return k;
}

/* ---- the field ---- */
static int kb_measure(
    void *w,
    const char
        *s) { /* the text's width in widget w's own font; a text that cannot be measured is taken as 9 px a character */
    unsigned wide[160], n = kb_slen(s);
    float f;
    memset(wide, 0, sizeof wide);
    tk_utf8_to_utf16_ex(s, n, wide, 159);
    wide[159] = 0;
    f = widget_measure_text(w, wide);
    if (f <= 0.0f) return (int)n * 9;
    return (int)(f + 0.999f);
}

/* src[0..n) in out (n + 4 bytes): the whole text when it fits maxw in widget w's font, else its end after an ellipsis (leading characters dropped until it does); returns the width. */
static int kb_fit(void *w, const char *src, unsigned n, int maxw, char *out) {
    unsigned off = 0, i, k;
    int wd, prefix = 0;
    for (;;) {
        k = 0;
        if (prefix) {
            out[0] = (char)0xe2, out[1] = (char)0x80, out[2] = (char)0xa6; /* U+2026, the ellipsis */
            k = 3;
        }
        for (i = off; i < n; ++i) out[k++] = src[i];
        out[k] = 0;
        wd = kb_measure(w, out);
        if (wd <= maxw || off >= n) break;
        off += kb_clen(src + off);
        prefix = 1;
    }
    return wd;
}

static void kb_refresh(void) { /* the text and the caret */
    char shown[KB_PASS_MAX * 3 + 8],
        dots[KB_PASS_MAX * 3 + 1]; /* (a masked field is dots, 3 bytes each: KB_PASS_MAX at most) */
    int w = 0;
    if (kb.len &&
        kb.mask) { /* one dot (U+2022) per character; a masked field never takes more than KB_PASS_MAX bytes of characters */
        unsigned i, n = 0;
        for (i = 0; i < kb.len && n + 3 <= KB_PASS_MAX * 3; i += kb_clen(kb.buf + i), n += 3)
            dots[n] = (char)0xe2, dots[n + 1] = (char)0x80, dots[n + 2] = (char)0xa2;
        dots[n] = 0;
        w = kb_fit(kb.text, dots, n, kb.tw, shown);
    } else if (kb.len)
        w = kb_fit(kb.text, kb.buf, kb.len, kb.tw, shown);
    else
        shown[0] = 0;
    widget_set_text_utf8(kb.text, shown);
    widget_set_visible(kb.hint, kb.len == 0, 0);
    kb_show(kb.clear, kb.len != 0 && !(kb.flags & KB_PASSWORD));
    widget_move(kb.caret, kb.tx + (kb.len ? w + 1 : 0), kb.cy);
    if (kb.embedded && kb.on_change) kb.on_change(kb.buf);
}

static void kb_page(int page);

static int kb_letters(
    void) { /* the letter page of the layer: English starts on capitals for an empty field (not a password field), Chinese is always lowercase */
    return kb.layer == L_ZH || kb.len || (kb.flags & KB_PASSWORD) ? P_LOWER : P_UPPER;
}

/* A new text: the shift rule (an empty field starts a capital, English only) then the field. */
static void kb_changed(void) {
    if (kb.len == 0 && kb.page == P_LOWER && kb.layer == L_EN && !(kb.flags & KB_PASSWORD)) kb_page(P_UPPER);
    kb_refresh();
}

static void kb_insert(const char *s) {
    unsigned n = kb_slen(s), i;
    if (kb.len + n > kb.max) return;
    for (i = 0; i < n; ++i) kb.buf[kb.len + i] = s[i];
    kb.len += n;
    kb.buf[kb.len] = 0;
}

static void kb_insert_fit(const char *s) { /* as many whole characters of s as there is room for */
    unsigned n = kb_slen(s), c = 0, l, i;
    while (c < n && c + (l = kb_clen(s + c)) <= n && kb.len + c + l <= kb.max) c += l;
    for (i = 0; i < c; ++i) kb.buf[kb.len + i] = s[i];
    kb.len += c;
    kb.buf[kb.len] = 0;
}

static void kb_delete_char(void) {
    if (!kb.len) return;
    while (kb.len > 1 && ((unsigned char)kb.buf[kb.len - 1] & 0xc0) == 0x80)
        kb.len--; /* the continuation bytes, then the lead byte */
    kb.len--;
    kb.buf[kb.len] = 0;
    kb_changed();
}

/* ---- the pages ---- */
static void kb_page(int page) {
    int letters = page <= P_UPPER, geo = letters ? 0 : 1, r, k = 0, zh_page = kb.layer == L_ZH && page == P_LOWER;
    kb.page = page;
    for (r = 0; r < 3; ++r) {
        const char *row = KB_ROWS[page][r];
        unsigned i, n = 0, l;
        int w = (r == 2 && !letters) ? KB_NUM_KW : KB_KW, x;
        for (i = 0; row[i]; i += kb_clen(row + i)) n++;
        x = (KB_W - (int)n * w - ((int)n - 1) * KB_GAP + 1) / 2;
        for (i = 0; row[i]; i += l, ++k) {
            unsigned j;
            l = kb_clen(row + i);
            for (j = 0; j < l; ++j) kb.lab[k][j] = row[i + j];
            kb.lab[k][l] = 0;
            kb.kx[k] = (short)x, kb.ky[k] = (short)(KB_PAD + r * KB_PITCH), kb.kw[k] = (short)w;
            if (kb.key[k]) {
                if (geo != kb.geo) {
                    widget_move(kb.key[k], x, KB_PAD + r * KB_PITCH);
                    widget_resize(kb.key[k], w, KB_KH);
                    kb_show(kb.key[k], 1);
                }
                widget_set_text_utf8(kb.key[k], kb.lab[k]);
            }
            x += w + KB_GAP;
        }
    }
    kb.nkeys = k;
    if (geo != kb.geo)
        for (r = k; r < KB_KEYS; ++r) kb_show(kb.key[r], 0);
    kb.geo = geo;
    kb_show(kb.shift, page == P_LOWER &&
                          !zh_page); /* the Chinese letter page has no shift: the pinyin separator takes its place */
    kb_show(kb.shifton, page == P_UPPER);
    kb_show(kb.sym, !letters || zh_page);
    if (!letters)
        widget_set_text_utf8(kb.sym, page == P_NUM ? "#+=" : "123");
    else if (zh_page)
        widget_set_text_utf8(kb.sym, "'");
    widget_set_text_utf8(kb.mode, letters ? "123" : "ABC");
}

/* Row four: with a second keyboard the language key sits right of 123 and space is that much narrower. */
static void kb_bottom(void) {
    int lang = kb.layers > 1, x = lang ? KB_LANG_X + KB_LANG_W + KB_GAP : KB_LANG_X;
    widget_move(kb.space, x, KB_ROW3_Y);
    widget_resize(kb.space, KB_GO_X - KB_GAP - x, KB_KH);
    kb_show(kb.lang, lang);
}

static void kb_lang_label(void) { /* the layer a tap goes to */
    if (kb.lang) widget_set_text_utf8(kb.lang, kb_layer_of(kb.layer == L_EN ? L_ZH : L_EN)->tag);
}

/* ---- the pop-up ---- */
static void kb_unpop(void) {
    if (!kb.popped) return;
    widget_set_visible(kb.stem, 0, 0);
    widget_set_visible(kb.pop, 0, 0);
    kb.popped = 0;
}

static void kb_pop(
    int i) { /* the stem over the key, the balloon above it (tools/pod_keyboard.py pop_rect); both stay insensitive */
    int top = KB_TOP + kb.ky[i], bx = kb.kx[i] + kb.kw[i] / 2 - KB_POP_W / 2, by = top - KB_POP_GAP - KB_POP_H, sy;
    if (bx < 1) bx = 1;
    if (bx > KB_W - 1 - KB_POP_W) bx = KB_W - 1 - KB_POP_W;
    sy = by + KB_POP_H - KB_STEM_UP;
    widget_move(kb.stem, kb.kx[i], sy);
    widget_resize(kb.stem, kb.kw[i], top + KB_KH - sy);
    widget_move(kb.pop, bx, by);
    widget_set_text_utf8(kb.pop_l, kb.lab[i]);
    widget_set_visible(kb.stem, 1, 0);
    widget_set_visible(kb.pop, 1, 0);
    kb.popped = i + 1;
}

/* ====================================================================================================================================
 * The Chinese (Pinyin) layer
 * ==================================================================================================================================== */

/* ---- the candidate strip ---- */
static int zh_itemw(int k) { return zh.off[k + 1] - zh.off[k]; }

static void zh_item_rect(int k, int *x,
                         int *w) { /* a candidate's rectangle in the candidates view: its text starts KB_CAND_PAD in */
    *x = zh.off[k] - zh.sx;
    *w = zh_itemw(k);
}

static void zh_highlight(int k) {
    int x, w;
    if (k < 0 || k >= zh.ncand) {
        widget_set_visible(kb.chl, 0, 0);
        return;
    }
    zh_item_rect(k, &x, &w);
    widget_move(kb.chl, x + 2, KB_CHL_Y);
    widget_resize(kb.chl, w - 4, KB_CHL_H);
    widget_set_visible(kb.chl, 1, 0);
}

static int zh_item_at(int x) { /* the candidate under x (candidates view coordinates), -1 for none */
    int k;
    x += zh.sx;
    for (k = 0; k < zh.ncand; ++k)
        if (x >= zh.off[k] && x < zh.off[k + 1]) return k;
    return -1;
}

/* Append a candidate (or prediction) given as UTF-8; 0 when the list or the pool is full. */
static int zh_add(const char *u8, unsigned len) {
    int w;
    if (zh.ncand >= KB_MAX_CAND || zh.pool_n + (int)len + 1 > KB_POOL_BYTES) return 0;
    zh.soff[zh.ncand] = (short)zh.pool_n;
    memcpy(zh.pool + zh.pool_n, u8, len + 1);
    zh.pool_n += (int)len + 1;
    w = kb_measure(kb.item[0], u8) + 2 * KB_CAND_PAD;
    w = w < KB_CAND_MIN ? KB_CAND_MIN : w > KB_CAND_MAXW ? KB_CAND_MAXW : w;
    zh.off[zh.ncand + 1] = (short)(zh.off[zh.ncand] + w);
    zh.ncand++;
    return 1;
}

static void zh_clear_list(void) {
    zh.ncand = zh.pool_n = zh.sx = 0;
    zh.off[0] = 0;
    zh.hot = -1;
    memset(zh.slot, 0, sizeof zh.slot);
}

static void zh_read_more(void) { /* the next candidates of the current search, KB_CHUNK at a time */
    unsigned short cb[KB_CAND_U16];
    char u8[KB_CAND_U16 * 3 + 1];
    int i = zh.ncand, to = zh.total < KB_MAX_CAND ? zh.total : KB_MAX_CAND, stop = zh.ncand + KB_CHUNK;
    while (i < to && i < stop) {
        unsigned len;
        cb[0] = cb[KB_CAND_U16 - 1] = 0;
        if (!im_get_candidate((unsigned)i, cb, KB_CAND_U16)) {
            zh.total = i;
            break;
        }
        cb[KB_CAND_U16 - 1] = 0;
        len = u16_to_u8(cb, u8, sizeof u8);
        if (!zh_add(u8, len)) {
            zh.total = i;
            break;
        }
        i = zh.ncand;
    }
}

/* The pinyin as the engine segments it ("ni hao"), raw letters past what it decoded; an apostrophe already separates. */
static void zh_label(char *out) {
    unsigned i, k = 0, s = 1;
    for (i = 0; i < zh.raw_n; ++i) {
        while (s < (unsigned)zh.nsp && zh.sp[s] < i) s++;
        if (i && s < (unsigned)zh.nsp && zh.sp[s] == i && zh.raw[i - 1] != '\'') out[k++] = ' ';
        out[k++] = zh.raw[i];
    }
    out[k] = 0;
}

/* Put the strip right: the pinyin label, the divider, the candidates view, the items in view (a ring of KB_POOL widgets: candidate k is always in widget k % KB_POOL). */
static void zh_render(void) {
    char lab[2 * KB_RAW_MAX + 8], shown[2 * KB_RAW_MAX + 12];
    int cx, cw, k, j, total, max;
    unsigned used = 0;
    if (!kb.strip) return;
    if (zh.src == S_NONE) {
        kb_show(kb.strip, 0);
        return;
    }
    if (zh.src == S_PINYIN) {
        zh_label(lab);
        zh.pyw = kb_fit(kb.py, lab, kb_slen(lab), KB_PY_MAX, shown);
        widget_set_text_utf8(kb.py, shown);
        cx = KB_PY_X + zh.pyw + KB_PY_X;
        widget_move(kb.sep, cx - KB_PY_X / 2, KB_SEP_Y);
        widget_set_visible(kb.sep, 1, 0);
    } else {
        zh.pyw = 0;
        widget_set_text_utf8(kb.py, "");
        cx = 0;
        widget_set_visible(kb.sep, 0, 0);
    }
    cw = KB_W - cx;
    widget_move(kb.cands, cx, 0);
    widget_resize(kb.cands, cw, KB_STRIP_H);
    for (;;) { /* more candidates while the strip is within 160 px of the end of what was read */
        int before = zh.ncand;
        if (zh.src == S_PINYIN && zh.ncand < zh.total && zh.ncand < KB_MAX_CAND && zh.sx + cw + 160 > zh.off[zh.ncand])
            zh_read_more();
        if (zh.ncand == before) break;
    }
    total = zh.off[zh.ncand];
    max = total > cw ? total - cw : 0;
    if (zh.sx > max) zh.sx = max;
    if (zh.sx < 0) zh.sx = 0;
    for (k = 0; k < zh.ncand; ++k) {
        int x, w;
        if (zh.off[k + 1] <= zh.sx) continue;
        if (zh.off[k] >= zh.sx + cw) break;
        j = k % KB_POOL;
        zh_item_rect(k, &x, &w);
        if (zh.slot[j] != k + 1) {
            widget_set_text_utf8(kb.item[j], zh.pool + zh.soff[k]);
            zh.slot[j] = (unsigned short)(k + 1);
        }
        widget_move(kb.item[j], x + KB_CAND_PAD, 0);
        widget_resize(kb.item[j], w - KB_CAND_PAD, KB_STRIP_H);
        widget_set_visible(kb.item[j], 1, 0);
        used |= 1u << j;
    }
    for (j = 0; j < KB_POOL; ++j)
        if (!(used & (1u << j))) {
            widget_set_visible(kb.item[j], 0, 0);
            zh.slot[j] = 0;
        }
    zh_highlight(zh.hot);
    kb_show(kb.strip, 1);
}

static void zh_hide(void) { /* nothing to show: predictions or candidates off */
    if (zh.src == S_NONE) return;
    zh.src = S_NONE;
    zh_clear_list();
    zh_render();
}

/* ---- the engine ---- */
/* Open the engine, or find it open: 0 when it is ready; *own says whether this call opened it (and so whoever asked must close it). */
static int kb_engine_open(int *own) {
    void *eng = PY_ENGINE_PTR;
    *own = 0;
    if (eng && *(volatile unsigned char *)
                   eng) /* an engine somebody else opened and initialised: use it as it is, leave it open */
        return 0;
    if (access(PINYIN_DICT, 0) != 0) {
        return -1;
    }
    if (eng)
        im_close_decoder(); /* stock's keyboard left an object that was never initialised (its dictionary is not there): ours replaces it */
    im_open_decoder(PINYIN_DICT, PINYIN_USER);
    eng = PY_ENGINE_PTR;
    if (!eng || !*(volatile unsigned char *)eng) {
        im_close_decoder();
        return -1;
    }
    *own = 1;
    return 0;
}

static int zh_enter(void) {
    if (zh.ready) return 0;
    if (kb_engine_open(&zh.own) != 0) return -1;
    zh.ready = 1;
    return 0;
}

static void zh_leave(void) {
    if (zh.ready && zh.own) im_close_decoder();
    zh.ready = zh.own = 0;
}

static int py_own __attribute__((
    section(".scratch"))); /* the search page opened the engine (pinyin_hold) and closes it (pinyin_release) */

/* The engine held open for the page's life, whatever the keyboard's Chinese layer does (the layer closes only an engine it opened itself: one it finds open it leaves). 0 when it is ready.
 * An engine the layer opened is taken over: the layer no longer closes it. */
int pinyin_hold(void) {
    int own;
    if (py_own) return 0;
    if (zh.ready && zh.own) {
        zh.own = 0, py_own = 1;
        return 0;
    }
    if (kb_engine_open(&own) != 0) return -1;
    py_own = own;
    return 0;
}

/* Let go of what pinyin_hold opened (after keyboard_detach: the layer is gone). */
void pinyin_release(void) {
    if (py_own) im_close_decoder();
    py_own = 0;
}

/* A new search of the pinyin typed: the candidates, the engine's segmentation. */
static void zh_research(void) {
    const unsigned short *p = (const unsigned short *)0;
    unsigned n, i;
    zh_clear_list();
    zh.src = S_PINYIN;
    zh.nsp = 0;
    zh.sp[0] = 0;
    im_reset_search();
    zh.total = (int)im_search(zh.raw, zh.raw_n);
    if (zh.total > 0) {
        n = im_get_spl_start_pos(&p);
        if (p && n <= KB_RAW_MAX) {
            for (i = 0; i <= n; ++i) zh.sp[i] = p[i];
            zh.nsp = (int)n;
        }
    }
    zh_render();
}

/* The words that usually follow the last characters of the field (at most seven Chinese ones), shown in the strip; none, no strip. */
static void zh_predict(void) {
    unsigned short hist[8], pred[KB_PRED][8];
    char u8[8 * 3 + 1];
    unsigned at = kb.len, chars = 0, n, i;
    zh_clear_list();
    zh.src = S_NONE;
    while (at >= 3 && chars < 7 && ((unsigned char)kb.buf[at - 3] & 0xf0) == 0xe0)
        at -= 3, chars++; /* the trailing run of three byte characters */
    if (chars) {
        u8_to_u16(kb.buf + at, kb.len - at, hist, 8);
        memset(pred, 0, sizeof pred);
        n = py_predicts(PY_ENGINE_PTR, hist, pred, KB_PRED);
        for (i = 0; i < n && i < KB_PRED; ++i) {
            pred[i][7] = 0;
            zh_add(u8, u16_to_u8(pred[i], u8, sizeof u8));
        }
        if (zh.ncand) zh.src = S_PRED;
    }
    zh_render();
}

/* Take candidate k of the current search into the field: the engine fixes it (im_choose), the characters it covers say how many syllables, so the rest of the pinyin stays. Returns the letters left. */
static unsigned zh_take(int k) {
    char text[KB_CAND_U16 * 3 + 1];
    unsigned fixed, used, i, n = 0;
    const char *p = zh.pool + zh.soff[k];
    while (p[n] && n < sizeof text - 1) text[n] = p[n], n++;
    text[n] = 0;
    im_choose((unsigned)k);
    fixed = im_get_fixed_len();
    if (!fixed)
        for (i = 0; i < n; i += kb_clen(text + i)) fixed++; /* the engine did not say: the characters of the text */
    if (fixed > (unsigned)zh.nsp) fixed = (unsigned)zh.nsp;
    used = fixed ? zh.sp[fixed] : zh.raw_n;
    if (!used || used > zh.raw_n) used = zh.raw_n;
    kb_insert_fit(text);
    while (used < zh.raw_n && zh.raw[used] == '\'') used++; /* a separator the candidate ended on */
    for (i = used; i < zh.raw_n; ++i) zh.raw[i - used] = zh.raw[i];
    zh.raw_n -= used;
    zh.raw[zh.raw_n] = 0;
    return zh.raw_n;
}

static int zh_pending(void) { return (int)zh.raw_n; }

static void zh_flush(
    void) { /* commit all that is pending: candidate 0 until the pinyin is used up (letters the engine cannot read go in as typed) */
    unsigned guard = KB_RAW_MAX + 2;
    while (zh.raw_n && guard--) {
        if (zh.src == S_PINYIN && zh.ncand > 0 && zh.total > 0) {
            if (zh_take(0)) zh_research();
        } else {
            kb_insert_fit(zh.raw);
            zh.raw_n = 0;
        }
    }
    zh.raw[0] = 0;
    kb_refresh();
    zh_hide();
}

static void zh_reset(void) {
    zh.raw_n = 0;
    zh.raw[0] = 0;
    zh_hide();
}

static int zh_compose(int c) {
    if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    if (!((c >= 'a' && c <= 'z') || (c == '\'' && zh.raw_n && zh.raw[zh.raw_n - 1] != '\''))) return 0;
    if (zh.raw_n >= KB_RAW_MAX) return 1; /* the engine takes no more: the key is used up, nothing changes */
    zh.raw[zh.raw_n++] = (char)c;
    zh.raw[zh.raw_n] = 0;
    zh_research();
    return 1;
}

static int zh_backspace(void) {
    if (zh.raw_n) {
        zh.raw[--zh.raw_n] = 0;
        if (zh.raw_n)
            zh_research();
        else
            zh_hide();
        return 1;
    }
    zh_hide(); /* predictions go; the field's own character does too */
    return 0;
}

static void zh_commit(
    int k) { /* a candidate was tapped: it goes into the field, a long input is taken in steps, a finished one asks what follows */
    unsigned left = zh_take(k);
    kb_refresh();
    if (left)
        zh_research();
    else
        zh_predict();
}

static void zh_pick(int k) { /* a prediction was tapped: it is appended and the next ones are offered */
    char text[8 * 3 + 1];
    unsigned n = 0;
    const char *p = zh.pool + zh.soff[k];
    while (p[n] && n < sizeof text - 1) text[n] = p[n], n++;
    text[n] = 0;
    kb_insert_fit(text);
    kb_refresh();
    zh_predict();
}

static void zh_tap(int k) {
    if (k < 0 || k >= zh.ncand) return;
    if (zh.src == S_PINYIN)
        zh_commit(k);
    else if (zh.src == S_PRED)
        zh_pick(k);
}

/* The strip's touches: a press highlights the item, a move of KB_DRAG px makes it a scroll of the row, a lift without that takes the item. */
static int zh_on_strip(void *ctx, void *e) {
    int pt[2], type = e ? *(int *)e : 0;
    (void)ctx;
    if (!kb.win || kb.finished || !e || zh.src == S_NONE) return RET_OK;
    pt[0] = *(int *)((char *)e + PE_X);
    pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(kb.cands, pt);
    if (type == EVT_POINTER_DOWN) {
        zh.down = 1, zh.drag = 0, zh.dx = pt[0], zh.sx0 = zh.sx;
        zh.hot = zh_item_at(pt[0]);
        zh_highlight(zh.hot);
    } else if (type == EVT_POINTER_MOVE && zh.down) {
        int dx = pt[0] - zh.dx;
        if (!zh.drag && (dx >= KB_DRAG || -dx >= KB_DRAG)) {
            zh.drag = 1;
            zh.hot = -1;
        }
        if (zh.drag) {
            zh.sx = zh.sx0 - dx;
            zh_render();
        }
    } else if (type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) {
        int k = zh.hot;
        int was = zh.down && !zh.drag && type == EVT_POINTER_UP;
        zh.down = zh.drag = 0;
        zh.hot = -1;
        zh_highlight(-1);
        if (was) zh_tap(k);
    }
    return RET_OK;
}

static const struct kb_layer KB_LAYERS[2] = {
    {"EN", (int (*)(void))0, (void (*)(void))0, (int (*)(int))0, (int (*)(void))0, (void (*)(void))0, (int (*)(void))0,
     (void (*)(void))0},
    {"中", zh_enter, zh_leave, zh_compose, zh_backspace, zh_flush, zh_pending, zh_reset},
};

static const struct kb_layer *kb_layer_of(int layer) { return &KB_LAYERS[layer]; }

/* Settings > Keyboards > Chinese (Pinyin): "1" = on, anything else or no file = off. */
int kb_zh_setting(void) { return set_read(KBZH_FILE, 0) == '1'; }

int kb_zh_toggle(void) {
    int next = !kb_zh_setting();
    if (home_write_atomic(KBZH_FILE, KBZH_TMP, next ? "1\n" : "0\n") != 0) return -1;
    if (!next) kb_memo = L_EN; /* off: the next time it is turned on the keyboard starts on English again */
    return next;
}

/* ---- the layers ---- */
static void kb_layer_set(int layer) {
    const struct kb_layer *old = kb_layer_of(kb.layer);
    if (old->flush) old->flush();
    zh_hide();
    kb.layer = layer;
    kb_memo = layer;
    kb_page(kb_letters());
    kb_lang_label();
    kb_refresh();
}

static void kb_lang_tap(void) { /* the language key: the other layer; the Chinese one is opened the first time */
    int to = kb.layer == L_EN ? L_ZH : L_EN;
    const struct kb_layer *l = kb_layer_of(to);
    if (l->enter && l->enter() != 0) { /* no engine: the key goes away, English stays */
        kb.layers = 1;
        kb_bottom();
        return;
    }
    kb_layer_set(to);
}

/* ---- delete's repeat ---- */
static void kb_delete(void) {
    const struct kb_layer *l = kb_layer_of(kb.layer);
    if (l->backspace && l->backspace()) return; /* a letter of the pinyin first, then the text */
    kb_delete_char();
}

static int kb_repeat(const void *timer) {
    (void)timer;
    const struct kb_layer *l = kb_layer_of(kb.layer);
    if (!kb.win || !kb.held || (!kb.len && !(l->pending && l->pending()))) {
        kb.timer = 0;
        return RET_OK;
    }
    if (++kb.hold >= KB_HOLD_TICKS) kb_delete();
    return RET_REPEAT;
}

static void kb_stop(void) {
    kb.held = 0;
    if (kb.timer) timer_remove(kb.timer);
    kb.timer = 0;
}

/* ---- events ---- */
static void kb_finish(int ok) {
    kb_done_fn done = kb.done;
    kb_cancel_fn cancel = kb.cancel;
    char text[KB_MAX_LONG + 1];
    unsigned a = 0, b, i;
    if (kb.finished) return;
    if (kb.embedded) { /* the action key of an embedded pad: what is pending is committed, the page decides what follows (hides the pad) */
        if (kb.go_off) return; /* dimmed: nothing happens */
        if (kb_layer_of(kb.layer)->flush) kb_layer_of(kb.layer)->flush();
        kb_unpop();
        kb_stop();
        if (kb.on_go) kb.on_go();
        return;
    }
    if (ok && kb_layer_of(kb.layer)->flush)
        kb_layer_of(kb.layer)->flush(); /* the pinyin still pending is committed as its first candidate */
    b = kb.len;
    while (a < b && kb.buf[a] == ' ') a++;
    while (b > a && kb.buf[b - 1] == ' ') b--;
    if (ok && a == b) return; /* nothing to search for */
    for (i = a; i < b; ++i) text[i - a] = kb.buf[i];
    text[b - a] = 0;
    kb.finished = 1;
    kb_unpop();
    kb_stop();
    if (ok) {
        navigator_back();
        if (done) done(text); /* the page is closing: kb may already be reset, only locals from here */
    } else {
        navigator_back();
        if (cancel) cancel();
    }
}

static int kb_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (kb.win) kb_finish(0);
    return RET_OK;
}

static void kb_click(int id) {
    const struct kb_layer *l = kb_layer_of(kb.layer);
    if (!kb.win || kb.finished) return;
    if (id < KB_KEYS) {
        if (l->compose && kb.page == P_LOWER && l->compose(kb.lab[id][0])) return;
        zh_hide();
        kb_insert(kb.lab[id]);
        if (kb.page == P_UPPER) kb_page(P_LOWER);
        kb_refresh();
    } else if (id == K_SHIFT || id == K_SHIFTON) {
        kb_page(kb.page == P_LOWER ? P_UPPER : P_LOWER);
    } else if (id == K_SYM) {
        if (kb.page == P_LOWER) { /* the Chinese layer's pinyin separator */
            if (l->compose) l->compose('\'');
        } else
            kb_page(kb.page == P_NUM ? P_SYM : P_NUM);
    } else if (id == K_MODE) {
        if (l->flush) l->flush();
        zh_hide();
        if (kb.page <= P_UPPER)
            kb_page(P_NUM);
        else
            kb_page(kb_letters());
    } else if (id == K_LANG) {
        kb_lang_tap();
    } else if (id == K_SPACE) {
        if (l->pending && l->pending()) {
            l->flush();
            zh_predict(); /* after a commit the words that usually follow */
            return;
        }
        zh_hide();
        if ((kb.flags & (KB_PASSWORD | KB_LITERAL)) || (kb.len && kb.buf[kb.len - 1] != ' ')) {
            kb_insert(" ");
            kb_refresh();
        }
    } else if (id == K_GO) {
        kb_finish(1);
    }
}

static int kb_on_click(void *ctx, void *e) {
    (void)e;
    kb_click((int)(long)ctx);
    return RET_OK;
}

static int kb_on_clear(void *ctx, void *e) {
    const struct kb_layer *l = kb_layer_of(kb.layer);
    (void)ctx;
    (void)e;
    if (!kb.win || kb.finished) return RET_OK;
    if (l->reset) l->reset();
    kb.len = 0;
    kb.buf[0] = 0;
    if (kb.page >= P_NUM) kb_page(kb_letters());
    kb_changed();
    return RET_OK;
}

static void kb_down(void *e, int from_pad);

/* A key goes down (its own touch, or the pad's for a touch that fell between the keys): the pop-up, delete's first deletion and its repeat. */
static void kb_press(int id) {
    kb_unpop();
    if (id < KB_KEYS) kb_pop(id);
    if (id == K_DEL) {
        kb_stop();
        kb.held = 1, kb.hold = 0;
        kb_delete();
        kb.timer = timer_add(kb_repeat, (void *)0, KB_HOLD_MS);
    }
}

static void kb_release(int id) {
    kb_unpop();
    if (id == K_DEL) kb_stop();
}

/* The key's touch: the pop-up while a char key is down; delete acts on touch down and repeats while held. */
static int kb_on_touch(void *ctx, void *e) {
    int id = (int)(long)ctx, type = e ? *(int *)e : 0;
    if (!kb.win || kb.finished) return RET_OK;
    if (type == EVT_POINTER_DOWN) {
        kb_down(e, 0);
        if (kb.gap) { /* the pad took this touch as a gap, but a key has it: the key wins */
            kb_release(kb.gap - 1);
            kb.gap = 0;
        }
        kb_press(id);
    } else
        kb_release(id);
    return RET_OK;
}

/* The rectangles of the keys that are there now (pad coordinates), in the order a tie is settled: char keys, the left key, delete, 123 / ABC, the language key, space, Search. */
static int kb_rects(int *id, int *x, int *y, int *w) {
    int n = 0, i, sx = kb.layers > 1 ? KB_LANG_X + KB_LANG_W + KB_GAP : KB_LANG_X;
    for (i = 0; i < kb.nkeys; ++i) id[n] = i, x[n] = kb.kx[i], y[n] = kb.ky[i], w[n++] = kb.kw[i];
    id[n] = kb.page == P_UPPER ? K_SHIFTON : kb.page == P_LOWER && kb.layer == L_EN ? K_SHIFT : K_SYM;
    x[n] = KB_EDGE, y[n] = KB_ROW2_Y, w[n++] = KB_FN_W;
    id[n] = K_DEL, x[n] = KB_RIGHT, y[n] = KB_ROW2_Y, w[n++] = KB_FN_W;
    id[n] = K_MODE, x[n] = KB_EDGE, y[n] = KB_ROW3_Y, w[n++] = KB_MODE_W;
    if (kb.layers > 1) id[n] = K_LANG, x[n] = KB_LANG_X, y[n] = KB_ROW3_Y, w[n++] = KB_LANG_W;
    id[n] = K_SPACE, x[n] = sx, y[n] = KB_ROW3_Y, w[n++] = KB_GO_X - KB_GAP - sx;
    id[n] = K_GO, x[n] = KB_GO_X, y[n] = KB_ROW3_Y, w[n++] = KB_MODE_W;
    return n;
}

static void *kb_widget(int id) {
    return id < KB_KEYS      ? kb.key[id]
           : id == K_SHIFT   ? kb.shift
           : id == K_SHIFTON ? kb.shifton
           : id == K_SYM     ? kb.sym
           : id == K_DEL     ? kb.del
           : id == K_MODE    ? kb.mode
           : id == K_LANG    ? kb.lang
           : id == K_SPACE   ? kb.space
                             : kb.go;
}

/* A touch went down on the pad (or on one of its keys): log it, and when it fell on no key (from_pad, the pad's own event) resolve it to the nearest key: that key is pressed now and
 * clicked when the finger lifts. The same touch arrives once from the key and once from the pad whichever way AWTK passes it on: only the first is looked at. */
static void kb_down(void *e, int from_pad) {
    int id[KB_NRECT], x[KB_NRECT], y[KB_NRECT], w[KB_NRECT], pt[2], i, n, best = -1, bd = 0x7fffffff, sx, sy;
    unsigned t;
    if (!e) return;
    sx = *(int *)((char *)e + PE_X);
    sy = *(int *)((char *)e + PE_Y);
    t = *(unsigned *)((char *)e + 8);
    if (kb.seen_n && kb.seen_t == t && kb.seen_x == sx && kb.seen_y == sy) return;
    kb.seen_n = 1, kb.seen_t = t, kb.seen_x = sx, kb.seen_y = sy;
    if (!from_pad) return; /* a key's own touch needs nothing worked out */
    pt[0] = sx;
    pt[1] = sy;
    widget_to_local(kb.pad, pt);
    n = kb_rects(id, x, y, w);
    for (i = 0; i < n; ++i) {
        int dx = pt[0] < x[i] ? x[i] - pt[0] : pt[0] >= x[i] + w[i] ? pt[0] - (x[i] + w[i] - 1) : 0;
        int dy = pt[1] < y[i] ? y[i] - pt[1] : pt[1] >= y[i] + KB_KH ? pt[1] - (y[i] + KB_KH - 1) : 0;
        int d = dx * dx + dy * dy;
        if (d < bd) bd = d, best = i;
    }
    if (best < 0) return;
    if (bd > 0 && !kb.gap) {
        kb.gap = id[best] + 1;
        if (kb_widget(id[best]) && !(id[best] == K_GO && kb.go_off)) widget_set_state(kb_widget(id[best]), "pressed");
        kb_press(id[best]);
    }
}

static void kb_gap_end(int click) { /* the finger left a touch that was resolved to a key */
    int id = kb.gap - 1;
    if (!kb.gap) return;
    kb.gap = 0;
    if (kb_widget(id) && !(id == K_GO && kb.go_off)) widget_set_state(kb_widget(id), "normal");
    kb_release(id);
    if (click && id != K_DEL) kb_click(id);
}

static int kb_on_pad(
    void *ctx,
    void *
        e) { /* the pad's own touches: the ones between the keys (any touch, when the pad is told about its children's) */
    int type = e ? *(int *)e : 0;
    (void)ctx;
    if (!kb.win || kb.finished) return RET_OK;
    if (type == EVT_POINTER_DOWN)
        kb_down(e, 1);
    else if (type == EVT_POINTER_UP)
        kb_gap_end(1);
    else if (type == EVT_POINTER_ABORT)
        kb_gap_end(0);
    return RET_OK;
}

static int kb_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    kb_gap_end(0);
    kb_unpop();
    kb_stop();
    return RET_OK;
}

static int kb_on_destroy(void *ctx, void *e) {
    kb_cancel_fn cancel;
    (void)e;
    if (ctx != kb.win) return RET_OK;
    cancel = kb.finished ? (kb_cancel_fn)0 : kb.cancel; /* the hardware Back key, or a page replaced: that is Cancel */
    kb_stop();
    zh_leave(); /* the engine's megabyte goes back with the page */
    memset(&zh, 0, sizeof zh);
    memset(&kb, 0, sizeof kb);
    if (cancel) cancel();
    return RET_OK;
}

static void *kb_find(const char *name) { return widget_lookup(kb.win, name, 1); }

/* Bind the touch events (down, up, abort) and the click of a key widget. */
static int kb_bind(void *w, int id) {
    if (!w) return 0;
    return widget_on(w, EVT_CLICK, kb_on_click, (void *)(long)id) &&
           widget_on(w, EVT_POINTER_DOWN, kb_on_touch, (void *)(long)id) &&
           widget_on(w, EVT_POINTER_UP, kb_on_touch, (void *)(long)id) &&
           widget_on(w, EVT_POINTER_ABORT, kb_on_touch, (void *)(long)id);
}

/* The field's text to start with (cut on a character boundary at the limit); NULL or "" for none. */
static void kb_load(const char *initial) {
    unsigned n, c = 0, l, i;
    kb.len = 0;
    kb.buf[0] = 0;
    if (!initial) return;
    n = kb_slen(initial);
    while (c < n && c + (l = kb_clen(initial + c)) <= kb.max && c + l <= n) c += l;
    for (i = 0; i < c; ++i) kb.buf[i] = initial[i];
    kb.len = c;
    kb.buf[c] = 0;
}

/* The layers, the bottom row and the first page for the field's flags and text, then the field drawn (the tail of kb_init, also of keyboard_refocus). */
static void kb_start(void) {
    kb.layers = 1;
    if (!(kb.flags & KB_PASSWORD) &&
        kb_zh_setting()) { /* (a password field: English only) a second keyboard: the language key; the layer the last keyboard ended on comes back (a layer that will not open is dropped) */
        kb.layers = 2;
        if (kb_memo == L_ZH) {
            if (KB_LAYERS[L_ZH].enter() == 0)
                kb.layer = L_ZH;
            else
                kb.layers = 1, kb_memo = L_EN;
        } else if (access(PINYIN_DICT, 0) != 0) {
            kb.layers = 1;
        }
    }
    kb_bottom();
    kb_lang_label();
    kb_page(kb_letters());
    kb_refresh();
}

/* The lookups and bindings both ways of having the pad share (a page of its own, or embedded in another): the widgets by name, the pad's, the field's and the strip's events, the
 * keyboards and the first page. 0 when every widget is there; -1 (the state cleared) for an asset that is not ours. */
static int kb_init(const char *placeholder, const char *initial, int embedded) {
    char name[12];
    int i, ok;
    kb.title = embedded ? (void *)0 : kb_find("label_title");
    kb.pad = kb_find("kb_pad");
    kb.text = kb_find("kb_text");
    kb.hint = kb_find("kb_hint");
    kb.caret = kb_find("kb_caret");
    kb.clear = kb_find("kb_clear");
    kb.stem = kb_find("kb_stem");
    kb.pop = kb_find("kb_pop");
    kb.pop_l = kb_find("kb_pop_l");
    kb.shift = kb_find("kb_shift");
    kb.shifton = kb_find("kb_shifton");
    kb.sym = kb_find("kb_sym");
    kb.del = kb_find("kb_del");
    kb.mode = kb_find("kb_mode");
    kb.space = kb_find("kb_space");
    kb.go = kb_find("kb_go");
    kb.lang = kb_find("kb_lang");
    kb.strip = kb_find("kb_strip");
    kb.py = kb_find("kb_py");
    kb.sep = kb_find("kb_sep");
    kb.cands = kb_find("kb_cands");
    kb.chl = kb_find("kb_chl");
    ok = (embedded || kb.title) && kb.pad && kb.text && kb.hint && kb.caret && kb.clear && kb.stem && kb.pop &&
         kb.pop_l && kb.shift && kb.shifton && kb.sym && kb.del && kb.mode && kb.space && kb.go && kb.lang &&
         kb.strip && kb.py && kb.sep && kb.cands && kb.chl;
    for (i = 0; i < KB_KEYS; ++i) {
        snprintf(name, sizeof name, "kb_k%d", i);
        kb.key[i] = kb_find(name);
        ok = ok && kb.key[i];
    }
    for (i = 0; i < KB_POOL; ++i) {
        snprintf(name, sizeof name, "kb_c%d", i);
        kb.item[i] = kb_find(name);
        ok = ok && kb.item[i];
    }
    if (!ok) { /* an asset that is not ours */
        memset(&kb, 0, sizeof kb);
        return -1;
    }
    widget_on(kb.win, EVT_WINDOW_TO_BG, kb_on_bg, (void *)0);
    for (i = 0; i < KB_KEYS; ++i) kb_bind(kb.key[i], i);
    kb_bind(kb.shift, K_SHIFT);
    kb_bind(kb.shifton, K_SHIFTON);
    kb_bind(kb.sym, K_SYM);
    kb_bind(kb.del, K_DEL);
    kb_bind(kb.mode, K_MODE);
    kb_bind(kb.lang, K_LANG);
    kb_bind(kb.space, K_SPACE);
    kb_bind(kb.go, K_GO);
    widget_on(kb.clear, EVT_CLICK, kb_on_clear, (void *)0);
    widget_on(kb.pad, EVT_POINTER_DOWN, kb_on_pad, (void *)0);
    widget_on(kb.pad, EVT_POINTER_UP, kb_on_pad, (void *)0);
    widget_on(kb.pad, EVT_POINTER_ABORT, kb_on_pad, (void *)0);
    widget_on(kb.cands, EVT_POINTER_DOWN, zh_on_strip, (void *)0);
    widget_on(kb.cands, EVT_POINTER_MOVE, zh_on_strip, (void *)0);
    widget_on(kb.cands, EVT_POINTER_UP, zh_on_strip, (void *)0);
    widget_on(kb.cands, EVT_POINTER_ABORT, zh_on_strip, (void *)0);
    zh.hot = -1;
    widget_set_text_utf8(kb.hint, placeholder ? placeholder : "");
    kb_load(initial);
    kb.geo = 0; /* the asset is the lowercase page's geometry */
    kb_start();
    return 0;
}

int keyboard_busy(void) { return kb.win != 0; }

int keyboard_open(const char *title, const char *placeholder, const char *initial, kb_done_fn on_done,
                  kb_cancel_fn on_cancel, unsigned flags) {
    if (kb.win) return -1;
    memset(&kb, 0, sizeof kb);
    memset(&zh, 0, sizeof zh);
    kb.win = window_open("m1plus_keyboard");
    if (!kb.win) return -1;
    kb.done = on_done, kb.cancel = on_cancel, kb.flags = flags;
    kb.max = flags & KB_LONG ? KB_MAX_LONG : KB_MAX; /* before kb_init, which cuts the initial text to it */
    kb.tx = KB_TEXT_X, kb.tw = KB_TEXT_W, kb.cy = KB_CARET_Y;
    if (kb_init(placeholder, initial, 0) != 0) {
        navigator_back();
        return -1;
    }
    widget_on(kb.win, EVT_DESTROY, kb_on_destroy, kb.win);
    pod_bind(kb.win, "btn_return", kb_on_back, (void *)0);
    pod_bind(kb.win, "btn_backtoplayer", pod_on_player, (void *)0);
    if (title && title[0]) widget_set_text_utf8(kb.title, title);
    if (flags & KB_DONE) widget_set_tr_text(kb.go, "Done");
    return 0;
}

/* The pad, the candidate strip and the field of ANOTHER page's window (the same widget names; ui/m1plus_search.bin has them, built from the same pieces as the keyboard page: tools/pod_ui.py
 * keyboard_pad_widgets). The text goes to on_change whenever it may have changed (the page ignores a repeat), the action key to on_go (the page hides the pad); the page's own Back closes the
 * window and ends this with keyboard_detach from its destroy handler. The pad starts shown. text_x, text_w, caret_y: the field's inner geometry in that page. */
int keyboard_attach(void *win, const char *placeholder, int text_x, int text_w, int caret_y, unsigned flags,
                    kb_change_fn on_change, kb_go_fn on_go) {
    if (kb.win || !win) return -1;
    memset(&kb, 0, sizeof kb);
    memset(&zh, 0, sizeof zh);
    kb.win = win, kb.embedded = 1, kb.max = flags & KB_PASSWORD ? KB_PASS_MAX : KB_MAX, kb.flags = flags;
    kb.mask = (flags & KB_PASSWORD) != 0;
    kb.tx = text_x, kb.tw = text_w, kb.cy = caret_y;
    if (kb_init(placeholder, (const char *)0, 1) != 0) return -1;
    kb.on_change = on_change, kb.on_go = on_go;
    return 0;
}

/* Another field of the same page takes the pad (a page with several fields moves the field widgets itself): the flags, the text room, the placeholder, the text and the callbacks of the new field, the
 * widgets and their bindings kept. What was pending (a pinyin composition, a held key, a pop-up) is dropped, the layers and the first page are chosen again for the flags (a password field is English only;
 * the Chinese engine stays open for the plain field that comes back), the action key's label and dimming are the page's to set again (keyboard_set_go), and on_change gets the new text. -1 when there is no
 * embedded keyboard. */
int keyboard_refocus(const char *placeholder, int text_w, unsigned flags, const char *text, kb_change_fn on_change,
                     kb_go_fn on_go) {
    if (!kb.win || !kb.embedded) return -1;
    kb_gap_end(0);
    kb_unpop();
    kb_stop();
    zh_reset();
    kb.layer = L_EN;
    kb.flags = flags;
    kb.max = flags & KB_PASSWORD ? KB_PASS_MAX : KB_MAX; /* before kb_load, which cuts the text to it */
    kb.mask = (flags & KB_PASSWORD) != 0;
    kb.tw = text_w;
    kb.on_change = on_change, kb.on_go = on_go;
    widget_set_text_utf8(kb.hint, placeholder ? placeholder : "");
    kb_load(text);
    kb_start();
    return 0;
}

/* A password field's eye: dots or the text. The caret is measured on what is shown. */
void keyboard_set_mask(int on) {
    if (!kb.win || !kb.embedded || kb.mask == !!on) return;
    kb.mask = !!on;
    kb_refresh();
}

/* The action key's label (a string key of tools/pod_i18n.py; NULL keeps it) and whether it works: dimmed (the "disable" style) and insensitive while not, so neither a touch on it nor one that
 * the gap rule resolves to it does anything. */
void keyboard_set_go(const char *key, int enabled) {
    if (!kb.win || !kb.embedded) return;
    if (key) widget_set_tr_text(kb.go, key);
    kb.go_off = !enabled;
    widget_set_sensitive(kb.go, enabled);
    widget_set_state(kb.go, enabled ? "normal" : "disable");
}

/* An embedded field that takes more than KB_MAX bytes (the stock Tidal edit takes 127, patch/tidalkb.c): right after keyboard_attach, at most KB_MAX_LONG (the buffer); keyboard_refocus sets the default again. */
void keyboard_set_max(unsigned bytes) {
    if (kb.win && kb.embedded && bytes && bytes <= KB_MAX_LONG) kb.max = bytes;
}

/* The action key as if pressed (a page's own Search button, patch/tidalkb.c): what is pending (a pinyin composition) is committed, then on_go; nothing while the key is dimmed. */
void keyboard_go(void) {
    if (kb.win && kb.embedded) kb_finish(1);
}

/* The page's window is going: the timer, the engine's megabyte and the state go with it. */
void keyboard_detach(void) {
    if (!kb.win || !kb.embedded) return;
    kb_stop();
    zh_leave();
    memset(&zh, 0, sizeof zh);
    memset(&kb, 0, sizeof kb);
}

/* Show or hide an embedded pad: hidden it takes no touch (hidden and insensitive), the caret goes, a key held or a pop-up in the air is let go; shown again the candidate strip comes back
 * only if candidates are there. */
void keyboard_show(int on) {
    if (!kb.win || !kb.embedded || kb.hidden == !on) return;
    kb.hidden = !on;
    if (!on) {
        kb_gap_end(0);
        kb_unpop();
        kb_stop();
    }
    kb_show(kb.pad, on);
    kb_show(kb.strip, on && zh.src != S_NONE);
    widget_set_visible(kb.caret, on, 0);
}

int keyboard_shown(void) { return kb.win && kb.embedded && !kb.hidden; }

const char *keyboard_text(void) { return kb.win ? kb.buf : ""; }

/* The field's text replaced by s (whole characters up to the limit), as if typed: a pending composition is dropped, the change is reported. */
void keyboard_set_text(const char *s) {
    const struct kb_layer *l;
    if (!kb.win || kb.finished) return;
    l = kb_layer_of(kb.layer);
    if (l->reset) l->reset();
    kb.len = 0;
    kb.buf[0] = 0;
    kb_insert_fit(s);
    if (kb.page >= P_NUM) kb_page(kb_letters());
    kb_changed();
}

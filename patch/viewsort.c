/* The "..." card of the pages with a sort order and a grid / list view (patch/viewsort.h).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Built by tools/pod_ui.py view_sort_card as an Apple-style grouped menu (the optional Search and Select rows first, then View, then Sort) and fitted to the language as the Playlists menu is (patch/playlists.c pl_fit):
 * the card is as wide as its widest label (or direction line) plus its x and the margin, VS_CARD_MIN..PL_CARD_MAX, its right edge fixed under the navbar's glass. The glass is drawn patch3_x, so any width is exact.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "i18n.h"
#include "viewsort.h"

static int vs_has(const vs_t *v, int row) { return v->sorts >> row & 1; }

/* The rows top to bottom: the action rows (Search and Select, or the Playlists page's four), when offered, Grid, List, then the sorts. */
static const unsigned char VS_ORDER[VS_ROWS] = {VS_SEARCH,    VS_SELECT, VS_ACT2, VS_ACT3, VS_SORTS,
                                                VS_SORTS + 1, 0,         1,       2,       3};

static void vs_fit(vs_t *v);

/* How many rows of the first group (Search, Select, slots 8 and 9) the page offers. */
static int vs_actions(const vs_t *v) {
    return vs_has(v, VS_SEARCH) + vs_has(v, VS_SELECT) + vs_has(v, VS_ACT2) + vs_has(v, VS_ACT3);
}

void vs_offer(vs_t *v, unsigned mask) {
    static const char *const ST[] = {"normal", "pressed", "over"};
    char key[32], glass[16];
    int i;
    v->sorts = mask & (VS_ALL_SORTS | VS_WITH_VIEWS | VS_WITH_SEARCH | VS_WITH_SELECT | VS_WITH_ACT2 | VS_WITH_ACT3);
    for (i = 0, v->rows = 0; i < VS_ROWS; ++i) v->rows += vs_has(v, i);
    for (i = 0; i < VS_ROWS; ++i)
        m1_show(v->item[i], vs_has(v, i)); /* a row the page does not offer: hidden and insensitive, the widgets stay */
    widget_set_visible(
        v->hair, vs_actions(v) && v->rows > vs_actions(v),
        0); /* (the hairline under the first group goes with it, or when nothing follows; it stays insensitive) */
    snprintf(glass, sizeof glass, VS_GLASS_FMT, v->rows); /* the glass of that height, the one picture of its height */
    for (i = 0; i < 3; ++i) {
        snprintf(key, sizeof key, "style:%s:bg_image", ST[i]);
        widget_set_prop_str(v->card, key, glass);
    }
    { /* the first sort row's top border is the hairline between the groups: with no view rows above the sorts it would be a stray at the card's top or double the hairline under the first group (a card offered again with view rows gets it back) */
        int bw = vs_has(v, VS_SORTS) || vs_has(v, VS_SORTS + 1);
        for (i = 0; i < 3 && bw == v->bare; ++i) { /* (only when it changes: the asset starts with the border) */
            snprintf(key, sizeof key, "style:%s:border_width", ST[i]);
            widget_set_prop_int(v->item[0], key, bw);
        }
        v->bare = !bw;
    }
    if (v->on) vs_fit(v); /* (a card that is open is packed again) */
}

int vs_bind(vs_t *v, void *win, int (*item)(void *, void *), int (*scrim)(void *, void *), unsigned sorts) {
    static const char *const ITEMS[VS_ROWS] = {"vs_item0", "vs_item1", "vs_item2", "vs_item3", "vs_item4",
                                               "vs_item5", "vs_item6", "vs_item7", "vs_item8", "vs_item9"};
    static const char *const LABELS[VS_ROWS] = {"vs_label0", "vs_label1", "vs_label2", "vs_label3", "vs_label4",
                                                "vs_label5", "vs_label6", "vs_label7", "vs_label8", "vs_label9"};
    static const char *const TICKS[VS_SEARCH] = {"vs_tick0", "vs_tick1", "vs_tick2",
                                                 "vs_tick3", "vs_tick4", "vs_tick5"}; /* (the action rows have none) */
    static const char *const SUBS[VS_SORTS] = {"vs_sub0", "vs_sub1", "vs_sub2", "vs_sub3"};
    static const char *const GLYPHS[VS_VIEWS + 4] = {"vs_glyph4", "vs_glyph5", "vs_glyph6",
                                                     "vs_glyph7", "vs_glyph8", "vs_glyph9"};
    int i;
    memset(v, 0, sizeof *v);
    v->dated = 1u << 2 | 1u << 3;
    v->scrim = widget_lookup(win, "vs_scrim", 1);
    v->card = widget_lookup(win, "vs_card", 1);
    v->hair = widget_lookup(win, "vs_hair", 1);
    if (!v->scrim || !v->card || !v->hair) return -1;
    for (i = 0; i < VS_ROWS; ++i) {
        v->item[i] = widget_lookup(win, ITEMS[i], 1);
        v->label[i] = widget_lookup(win, LABELS[i], 1);
        if (i >= VS_ACT2 && !v->item[i] && !v->label[i])
            continue; /* (slot 8 exists only in the Playlists and Songs assets, slot 9 in the Playlists asset: a page that offers them without the widgets is not ours, below) */
        if (!v->item[i] || !v->label[i]) return -1;
        if (i < VS_SEARCH && !(v->tick[i] = widget_lookup(win, TICKS[i], 1))) return -1;
    }
    for (i = 0; i < VS_SORTS; ++i)
        if (!(v->sub[i] = widget_lookup(win, SUBS[i], 1))) return -1;
    for (i = 0; i < VS_VIEWS + 4; ++i) {
        v->glyph[i] = widget_lookup(win, GLYPHS[i], 1);
        if (!v->glyph[i] && i < VS_VIEWS + 2) return -1;
    }
    if (sorts & (VS_WITH_ACT2 | VS_WITH_ACT3))
        for (i = VS_ACT2; i < VS_ROWS; ++i)
            if ((sorts >> i & 1) && (!v->item[i] || !v->glyph[i - VS_SORTS])) return -1;
    for (i = 0; i < VS_ROWS; ++i) m1_bind(win, ITEMS[i], item, (void *)(long)i);
    m1_bind(win, "vs_scrim", scrim, (void *)0);
    vs_offer(v, sorts);
    m1_show(v->scrim, 0);
    m1_show(v->card, 0);
    return 0;
}

/* The direction line of the ticked sort row: Title and Artist read A-Z, Recently Added and Year newest first (v->dated); `rev` is the other way. */
static const char *vs_dir(const vs_t *v, int sort, int rev) {
    if (!(v->dated >> sort & 1)) return rev ? "Z–A" : "A–Z";
    return rev ? "Oldest First" : "Newest First";
}

void vs_dated(vs_t *v, unsigned rows) { v->dated = rows & VS_ALL_SORTS; }

/* The width of a text in a widget's own font; 0 when it cannot be measured. */
static int vs_text_w(void *w) {
    const unsigned *t = widget_get_text(w);
    return t && *t ? m1_text_w(w, t) : 0;
}

/* The card as wide as the language needs: the widest label (widget_measure_text: the label's own font and translated text) or direction line, each from its own x, plus the margin, clamped; the right
 * edge stays. A text that cannot be measured leaves the asset's width (PL_CARD_MAX, the widest language's). Rows are packed from the top in display order. */
static void vs_fit(vs_t *v) {
    int i, y, w = 0, ok = 1;
    int gx =
        v->rows > vs_actions(v)
            ? VS_GLYPH_X
            : VS_TICK_X; /* a card of action rows only has nothing to tick: its glyphs start at the tick column's edge and the labels follow with the same gap */
    int lx = gx + VS_LABEL_X_GLYPH - VS_GLYPH_X;
    for (i = 0; i < VS_ROWS && ok; ++i) {
        int tw, x0 = i >= VS_SORTS ? lx : VS_LABEL_X;
        if (!vs_has(v, i)) continue;
        tw = vs_text_w(v->label[i]);
        if (i == v->sort) { /* (the ticked sort row's direction line too) */
            int sw = vs_text_w(v->sub[i]);
            if (sw <= 0)
                tw = 0;
            else if (x0 + sw > w)
                w = x0 + sw;
        }
        if (tw <= 0)
            ok = 0;
        else if (x0 + tw > w)
            w = x0 + tw;
    }
    if (ok) {
        w += VS_LABEL_R;
        if (w < VS_CARD_MIN) w = VS_CARD_MIN;
        if (w > PL_CARD_MAX) w = PL_CARD_MAX;
        widget_move(v->card, PL_CARD_RIGHT - w, PL_CARD_Y);
        widget_resize(v->card, w, v->rows * VS_ROW_H);
    } else
        w = PL_CARD_MAX;
    if (vs_actions(v)) { /* the hairline under the first group (Search, Select), as wide as the card */
        widget_move(v->hair, 0, vs_actions(v) * VS_ROW_H);
        widget_resize(v->hair, w, 1);
    }
    for (i = 0, y = 0; i < VS_ROWS; ++i) {
        int k = VS_ORDER[i], x0 = k >= VS_SORTS ? lx : VS_LABEL_X, two = k == v->sort;
        if (!vs_has(v, k)) continue;
        if (k >= VS_SORTS && v->glyph[k - VS_SORTS]) widget_move(v->glyph[k - VS_SORTS], gx, (VS_ROW_H - VS_GLYPH) / 2);
        widget_move(v->item[k], 0, y), y += VS_ROW_H; /* the rows shown are packed from the top */
        widget_resize(v->item[k], w, VS_ROW_H);
        widget_move(v->label[k], x0, two ? VS_LABEL2_Y : 0);
        widget_resize(v->label[k], w - x0 - VS_LABEL_R, two ? VS_LABEL2_H : VS_ROW_H);
        if (two) {
            widget_move(v->sub[k], x0, VS_SUB_Y);
            widget_resize(v->sub[k], w - x0 - VS_LABEL_R, VS_SUB_H);
        }
    }
}

void vs_view(vs_t *v, int list) {
    widget_set_visible(v->tick[VS_SORTS], !list, 0);
    widget_set_visible(v->tick[VS_SORTS + 1], list, 0);
}

void vs_menu(vs_t *v, int on, int sort, int rev, int list) {
    int i;
    if (on) {
        v->sort = sort, v->rev = rev;
        for (i = 0; i < VS_SORTS; ++i) {
            widget_set_visible(v->tick[i], i == sort, 0);
            widget_set_visible(v->sub[i], i == sort, 0);
        }
        widget_set_tr_text(v->sub[sort], vs_dir(v, sort, rev));
        vs_view(v, list);
        vs_fit(v);
    }
    v->on = on;
    m1_show(v->scrim, on);
    m1_show(v->card, on);
}

/* The "..." card of the pages with a sort order and a grid / list view (docs/modules/albums.md "The ... card"): an Apple-style grouped menu. The optional Search and Select rows (a glyph, no tick; the page decides
 * what they do) come first, then the View group (Grid, List, each with a glyph, a tick on the
 * current view) above the Sort group (Title, Artist, Recently Added, Year: a tick on the current one and, under its label, a grey line with the direction), 48 px rows on the card's own glass, one
 * hairline between the groups (vs_hair under the Search / Select rows, the first sort row's top border). The page owns what a row does: it passes the click handlers and the state; this file owns the widgets (found by name in the page: vs_scrim, vs_card, vs_hair, vs_item0..7,
 * vs_label0..7, vs_tick0..5, vs_glyph4..7, vs_sub0..3; slots 0..3 are the sorts, 4 Grid, 5 List, 6 Search, 7 Select; the Playlists asset adds vs_item8 / 9 with vs_label8 / 9 and vs_glyph8 / 9: its four page actions are slots 6..9 in card order), the width that fits the language and the row texts.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

typedef struct {
    void *scrim, *card, *hair, *item[10], *label[10], *tick[6], *glyph[6],
        *sub[4]; /* (glyph[0..5] = slots 4..9; the action rows (6..9) have no tick; slot 8 only exists in the Playlists and Songs assets, slot 9 in the Playlists asset: NULL elsewhere) */
    int on;
    int sort, rev; /* what vs_menu last showed: the ticked sort row and its direction */
    unsigned
        sorts; /* the rows offered, bit i = row i (the view rows' bits VS_SORTS.. only with VS_WITH_VIEWS, the Search row's only with VS_WITH_SEARCH, Select's with VS_WITH_SELECT, slots 8 and 9 with VS_WITH_ACT2 / VS_WITH_ACT3) */
    int rows; /* how many rows the card has */
    int bare; /* sort row 0's top border (the hairline between the groups) is off: no view rows above it */
    unsigned
        dated; /* the sort rows whose direction line reads Newest First / Oldest First (bit i = row i); the others read A-Z / Z-A. vs_bind sets rows 2 and 3 (Recently Added, Year); a page changes it with vs_dated */
} vs_t;

/* Finds and binds the widgets of the page `win`: a click on sort row i calls item(ctx = (void *)i), the Grid row item(ctx = (void *)VS_SORTS), the List row item(ctx = (void *)(VS_SORTS + 1)), the Search row item(ctx = (void *)VS_SEARCH), the Select row item(ctx = (void *)VS_SELECT), the
 * scrim scrim(NULL). `sorts` is the set of rows the page offers (bit i = sort row i, VS_ALL_SORTS for all sorts; | VS_WITH_SEARCH for the Search row, | VS_WITH_SELECT for the Select row): the others are hidden and insensitive, the rest packed
 * (sort row 0 must be offered: it is the row with the hairline above it, which goes when no view row is offered; | VS_WITH_VIEWS for the two view rows), and the card gets the glass of its row count (VS_GLASS_FMT: 1, 2, 3, 4, 6 and 7 rows exist).
 * With no first-group row offered the hairline under it is hidden; with one it sits under the last of them.
 * 0 when everything is there; -1 for an asset that is not ours (nothing is bound then). */
int vs_bind(vs_t *v, void *win, int (*item)(void *, void *), int (*scrim)(void *, void *), unsigned sorts);
/* Changes the rows offered (the same mask as vs_bind's) at run time: Recently Added's albums view has no Select. The rows are packed again, an open card too. */
void vs_offer(vs_t *v, unsigned mask);
/* The sort rows whose direction line is Newest First / Oldest First (bit i = sort row i; the default, rows 2 and 3, is the Albums page's). The Songs page: row 3 alone. Call after vs_bind, before the card opens. */
void vs_dated(vs_t *v, unsigned rows);
/* Opens (on) or closes the card: the tick on sort row `sort` with its direction line (`rev` = reversed from the order's default: Z-A, Oldest First), the tick on the current view (`list`), the width
 * fitted to the language again. */
void vs_menu(vs_t *v, int on, int sort, int rev, int list);
/* The tick on the current view (`list` = the page is a list now); done by the page when it opens and when the mode changes. */
void vs_view(vs_t *v, int list);

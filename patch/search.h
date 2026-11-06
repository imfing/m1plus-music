/* M1+ Music Search (patch/search.c, docs/modules/search.md): the entry point and the page's geometry, which tools/pod_search.py repeats (the builder, the preview and the tests read
 * both: test/pod/search.py parses the #defines of this file).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* Open the Search page (the Apple Music search screen: a field with our keyboard embedded at the bottom of the same page, chips, live results). 0 once the page is up; -1 when it could not open
 * (a Search page exists already, no memory, or the asset is not ours): the caller opens the stock search page. */
int search_open(void);

/* The same page scoped to one type: SEARCH_ARTISTS .. SEARCH_PLAYLISTS (the chip order; SEARCH_ALL is search_open). Its chip row shows that one chip, selected, and only that type is searched.
 * 0 once the page is up; -1 as search_open, or for a scope that is not one of these. */
#define SEARCH_ALL 0
#define SEARCH_ARTISTS 1
#define SEARCH_ALBUMS 2
#define SEARCH_SONGS 3
#define SEARCH_PLAYLISTS 4
int search_open_in(int scope);

/* Window coordinates (the window is 320 x 450 under the status bar). */
#define SE_FIELD_X 12 /* the rounded search field: a capsule */
#define SE_FIELD_Y 8
#define SE_FIELD_W 250
#define SE_FIELD_H 36
#define SE_FIELD_R 18
#define SE_MAG_X 12 /* the magnifier (16 px) in the field */
#define SE_TEXT_X 36 /* the text starts here in the field, and may take SE_TEXT_W up to the clear button */
#define SE_TEXT_W 178
#define SE_CLEAR_W 36 /* the clear button's touch area at the field's right end */
#define SE_CARET_Y 7
#define SE_CLOSE_X 270 /* the round X button: closes the page (se_close, a flat disc centred on the field) */
#define SE_CLOSE_Y 4
#define SE_CLOSE_W 46
#define SE_CLOSE_H 44
#define SE_CHIPS_Y 52 /* the chip row: a view SE_CHIPS_H high holding the highlight and painting the texts */
#define SE_CHIPS_H 34
#define SE_CHIP_Y 2 /* a chip's pill inside the row */
#define SE_CHIP_H 30
#define SE_CHIP_X 12 /* the first chip's left edge */
#define SE_CHIP_PAD 14 /* the padding either side of a chip's text */
#define SE_CHIP_GAP 6
#define SE_CHIP_PX 16
#define SE_CHIP_R 15
#define SE_SEP_Y 88 /* the line under the chips */
#define SE_LIST_Y 90 /* the results list: to the window's bottom (the keyboard covers its lower part) */
#define SE_LIST_H 360
#define SE_ROW_H 60 /* every result row */
#define SE_ART 44 /* the thumbnail: round for an artist, SE_ART_R px corners otherwise */
#define SE_ART_R 4
#define SE_ART_X 12
#define SE_ART_Y 8
#define SE_TITLE_Y \
    7 /* the title and the grey line, centred in the SE_ROW_H row (the library rows' LIST_TITLE_H / LIST_SUB_H boxes, 2 px higher) */
#define SE_SUB_Y 33
#define SE_TEXT_LEFT 68 /* the title and the grey line start here; the separator too */
#define SE_END_CHEV 278 /* the text of a row with a chevron ends here, one without at SE_END_PLAIN */
#define SE_END_PLAIN 302
#define SE_CHEV_X 288
#define SE_SEP_END 310 /* the row separators end at the scroll_view's edge */
#define SE_REC_MAX 5 /* recent searches kept (the empty state lists them under a header) */
#define SE_REC_HEAD_H 40 /* the header "Recently Searched" */
#define SE_REC_ROW_H 50 /* a recent row: the query, an x on the right */
#define SE_REC_TEXT_X 16 /* the header and the query start here; the hairline too */
#define SE_REC_TEXT_END 262 /* the query is cut here (the x's touch area starts at SE_REC_X) */
#define SE_REC_X 266 /* the x's touch area: SE_REC_X_W wide (44 px) and the row high */
#define SE_REC_X_W 44
#define SE_REC_X_C 292 /* the centre of the x, which is POD_CROSS (12) px square */
#define SE_BOTTOM 12 /* air under the last row (the pad's height instead while the keyboard is up) */
#define SE_CHIPS 5 /* Top Results, Artists, Albums, Songs, Playlists */
#define SE_MAX_ROWS 200
#define SE_CAP_TOP 30 /* the rows of Top Results */
#define SE_CAP_ARTISTS 100 /* ... and of each type's chip */
#define SE_CAP_ALBUMS 100
#define SE_CAP_SONGS 200
#define SE_CAP_PLAYLISTS 100
#define SE_TICK_MS 40 /* the page's one timer: the debounce counts these, the covers load one a tick */
#define SE_DEBOUNCE 5 /* ticks without a key before the results refresh: 200 ms */

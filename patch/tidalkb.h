/* The keyboard field inside the stock Tidal > Search bar (patch/tidalkb.c, docs/modules/tidalkb.md): the geometry tools/pod_ui.py add_tidal_keyboard builds into
 * ui/tidal/tidal_serach_page.bin and the payload tells keyboard_attach. All of it is in the bar's own list_item `listitem_ssid` (240 x 38), over the stock edit `search_edit`
 * (15, 0, 210 x 38).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define TK_FIELD_X 19 /* the field in the bar: where the stock edit's text starts (the edit is at x 15) */
#define TK_FIELD_W 206 /* ... up to the edit's right end less its margin */
#define TK_FIELD_H 38 /* the bar's height */
#define TK_TEXT_X 0 /* the text and the caret start at the field's left edge */
#define TK_TEXT_W 166 /* the room for the text: the clear button takes the rest */
#define TK_CLEAR_W 36 /* the clear button's touch area at the field's right end */
#define TK_CARET_Y 8 /* the 22 px caret centred in the bar */
#define TK_PX 18 /* the stock edit's font size */

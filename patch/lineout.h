/* Line Out pill (patch/lineout.c, docs/modules/lineout.md): constants the payload and test/pod/lineout.py share.
 * The test parses the #defines in this file, so a change cannot leave the mocks behind.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define LO_PILL \
    "pod_lo" /* the hidden amber pill image tools/statusbar.py puts after label_volume in view_bar_left (both bar copies) */
#define LO_W_PARENT 0x44 /* widget->parent (pinned by BATTERY_PINS against widget_set_visible) */
#define EQ_IND \
    "pod_eq" /* the hidden "EQ" label tools/statusbar.py puts after the pill in view_bar_left (both bar copies); shown while the Equalizer is on */
#define EQ_DIGITAL \
    "img_digital" /* stock's digital-out glyph, the left group's last child: while it shows there is no room for the EQ mark before the clock */
#define SYNC_IND \
    "pod_sync" /* the hidden sync icon tools/statusbar.py puts in view_bar_right (both bar copies); shown while a cover or duration build runs */

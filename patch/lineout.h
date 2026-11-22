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
#define LO_GROUP "view_bar_left" /* the bar's left group, where the pill and the EQ mark sit */
#define EQ_DIGITAL \
    "img_digital" /* stock's digital-out glyph, the left group's last child: while it shows there is no room for the EQ mark before the clock */
#define SYNC_IND \
    "pod_sync" /* the hidden sync icon tools/statusbar.py puts in view_bar_right (both bar copies); shown while a cover or duration build runs */
#define SLEEP_IND \
    "pod_sleep" /* the hidden moon icon tools/statusbar.py puts in view_bar_right (both bar copies); shown while a Sleep Timer is running */
/* The room test for the right group's marks that yield (patch/lineout.c lo_fits): stock's SyncLink (hook 40), the screenshot camera, the sync icon, then the moon show only if the group's visible ink, the mark included, spans at most
 * the room left of the centred clock, so they never push the Bluetooth box into it. The group lays out right-aligned with SLEEP_GAP spacing; each visible peer counts its box, the Bluetooth box only its ink
 * (the glyph or codec badge at the box's right edge; an image not listed counts the whole box). */
#define BAR_ROOM_12H \
    77 /* the group's right end (x 277) less the 12 h clock's widest ink end (x 197, "10:59 AM") and 3 px clearance */
#define BAR_ROOM_24H 92 /* the same with the 24 h clock (ink end x 182, "23:59"); stock's time24hflag picks */
#define SLEEP_GAP 3 /* tools/statusbar.py RGAP */
#define SLEEP_BT "img_btclass" /* stock's Bluetooth box, the group's first child */
#define SLEEP_SYNCLINK "img_synclink" /* stock's SyncLink glyph */
#define SLEEP_WIFI "img_wifi" /* stock's Wi-Fi glyph */
#define SLEEP_SHOT "pod_shot" /* the screenshot mark (system bar only) */
#define SLEEP_BT_GLYPH "bar_bt" /* Bluetooth on: ink 10 px (tools/status_art.py) */
#define SLEEP_BT_CON "bar_btcon" /* connected: ink 10 px */
#define SLEEP_INK_GLYPH 10
#define SLEEP_BT_AAC "bar_aac" /* the AAC tag: ink 31 px */
#define SLEEP_INK_AAC 31
#define SLEEP_BT_SBC "bar_sbc" /* the SBC tag: ink 28 px */
#define SLEEP_INK_SBC 28
#define SLEEP_BT_LDAC "bar_ldac" /* the LDAC tag: ink 38 px */
#define SLEEP_INK_LDAC 38
#define SLEEP_BT_APTX "bar_aptx" /* the aptX tag: ink 32 px */
#define SLEEP_INK_APTX 32
#define SLEEP_BT_APTXHD "bar_aptxhd" /* the aptX HD tag: ink 44 px */
#define SLEEP_INK_APTXHD 44

int lo_shot_fits(
    void *
        ind); /* the screenshot camera `ind` has room in its group beside stock's marks (patch/shot.c, as the countdown starts) */

void lo_bar_refresh(
    void *
        win); /* a window's bar copy at its init: the EQ mark follows stock's digital-out glyph at once (patch/lineout.c) */

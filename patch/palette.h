/* The palette (patch/palette.c, docs/modules/accent.md): the colours the painter gets, mapped at run time over the same assets, by the background (Black or Light) and the accent.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The approach, the flip and the image rules are q2-pod's Light Mode (its navigation.c ringnav_style_color / ringnav_image_add,
 * `ui_ink`).
 */
#pragma once

enum {
    PAL_BLACK = 0,
    PAL_LIGHT = 1,
    PAL_TINTED = 2
}; /* the effective background (Tinted needs an accent: Tinted + Neutral is Black) */
/* The accent: the saved index (appearance-accent), in the order of tools/palette.py ACCENTS and the picker. Neutral is stock's colours. */
enum { PAL_NEUTRAL = 0, PAL_RED, PAL_ORANGE, PAL_GREEN, PAL_TEAL, PAL_PURPLE, PAL_CHAMPAGNE, PAL_ACCENTS };

/* The effective background and accent, and whether the palette changes anything at all (not Black + Neutral, and no kill switch or bad-boot note): the hooks are pass-throughs
 * while it is not. */
int pal_background(void);
int pal_accent(void);
int pal_active(void);

/* The one colour mapping entry point: a colour (color_t: bytes r, g, b, a) as the painter should get it, background then accent. */
unsigned pal_map(unsigned c);

/* 1 while the background is light: the setting is On, or Auto and it is day by the device clock, and the kill switch (/mnt/mmc/m1plus-off) and the bad-boot note are absent.
 * The first call reads the setting. */
int pal_light(void);

/* The accent setting (the picker's, phase 3). pal_accent_set(i) saves the index atomically (/mnt/data/m1plus/appearance-accent), applies it at once (cached images dropped, the tinted
 * pages and the screen repainted) and returns i, or -1 (an index outside 0 .. PAL_ACCENTS - 1, or a failed save: the saved one is unchanged). pal_accent_saved() is the saved index
 * (what the picker checks; pal_accent() is the effective one, Neutral under the kill switch or the bad-boot note). pal_accent_color(i) is accent i as an opaque color_t word for
 * swatches (Neutral: today's #EEEEEC fill); pal_fill() the colour of the fills now (the effective accent's, or Neutral's). Pages that bake the fill into a bitmap when they open ask it. */
int pal_accent_saved(void);
int pal_accent_set(int index);
unsigned pal_accent_color(int index);
unsigned pal_fill(void);

/* A colour (color_t: bytes r, g, b, a) as the payload draws it: flipped in Light Mode when neutral, else as it is. A clear colour (alpha 0) stays clear. */
unsigned ui_ink(unsigned c);

/* The saved background: 0 Black (the default), 1 Tinted, 2 Light, 3 Light Auto (light from LIGHT_FROM to LIGHT_UNTIL by the clock; Light is not in the picker). pal_bg_set saves it
 * atomically (/mnt/data/m1plus/appearance-background), applies it (cached images dropped, the screen repainted) and returns the mode, or -1 (an unknown mode, or a failed save: the saved
 * one is unchanged). */
int pal_bg_mode(void);
int pal_bg_set(int mode);

/* The flip of one neutral channel / colour and the tint a cover-tinted page shows (pure; test/pod/palette.py runs them against tools/palette.py). */
unsigned light_flip(unsigned c);
int light_is_neutral(unsigned c);
/* The colour a cover-tinted page puts under its text: the tone itself (never a role colour: pal_not_role), or in Light Mode the page's neutral colour (the chromatic dark tone cannot flip, and the page's text does). */
unsigned pal_tone(unsigned tone);
/* A colour derived from a cover (a tone, a shade of it, the status bar's colour) that is a role colour (a pressed row, the progress fill) moved one LSB off it; any other as it is. */
unsigned pal_not_role(unsigned c);

/* Set a canvas fill from the payload's own palette. */
#define ui_fill_color(canvas, c) canvas_set_fill_color(canvas, ui_ink(c))

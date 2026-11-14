/* Sample Rate, the lamp's fourth mode (patch/tracklamp.c, docs/modules/display.md "Sample Rate"): constants the payload and test/pod/tracklamp.py share.
 * The test parses the #defines in this file, so a change cannot leave the mocks behind. */
#pragma once

#define TL_FILE "/mnt/data/m1plus/led-dynamic" /* "0" or missing: off; "1" .. "6": on, the theme below + 1 */
#define TL_TMP "/mnt/data/m1plus/led-dynamic.tmp"
#define TL_LAMP "/sys/class/led_ktd2026/led_config_rgb" /* the lamp: the decimal number red << 16 | green << 8 | blue */
#define TL_UAC "/sys/class/uac2/uac2_samprate" /* USB DAC mode: the rate the host chose */

/* The themes, in the order of the Sample Rate page's rows (tools/pod_pages.py RGB_THEMES). The first four show the rate's colour. */
#define TL_REFERENCE 0
#define TL_BREATHE 1
#define TL_HEARTBEAT 2
#define TL_LIGHTHOUSE 3
#define TL_CANDLE 4
#define TL_OCEAN 5
#define TL_THEMES 6

#define TL_LEVEL 17 /* a channel's brightest level (0x11, the level stock uses for its red) */
#define TL_POLL_MS 250 /* the player is asked this far apart; the timer's pace while nothing moves */
#define TL_FAST_MS 50 /* the timer's pace while a theme or the pause fade moves */
#define TL_FADE_MS 500 /* a pause: down to a fifth in this time ... */
#define TL_PAUSE_MS 2500 /* ... and the lamp is let go this long after the pause */
#define TL_GONE 4 /* polls without a track before a playing lamp is let go (the gap between two tracks) */

int tl_play_status(void); /* the hook */
int tl_led(void); /* LED Light: 0 Off, 1 Green, 2 Blue (stock's), 3 Sample Rate */
int tl_led_set(int mode); /* 0, or -1 when it could not be saved */
int tl_theme(void);
int tl_theme_set(int theme); /* 0, or -1 */

/* Settings for the stock Atmosphere Lamp's sample-rate indicator (patch/tracklamp.c). */
#pragma once

#define TL_FILE "/mnt/data/m1plus/sample-rate-rgb" /* "0" off; "1" enables Sample Rate RGB */
#define TL_TMP "/mnt/data/m1plus/sample-rate-rgb.tmp"

int formatlamp_enabled(void);
int formatlamp_set_enabled(int enabled); /* 1/0, or -1 if it could not be saved */
int formatlamp_theme(void);
int formatlamp_warning(void);
int formatlamp_volume_brightness(void);
int formatlamp_select_theme(int theme);
int formatlamp_set_warning(int enabled);
int formatlamp_set_volume_brightness(int enabled);
int formatlamp_led_mode(void);
int formatlamp_led_set(int mode);
unsigned formatlamp_rgb_levels(void *record, const unsigned info[13], int volume); /* packed 0xRRGGBB, levels 0..17 */

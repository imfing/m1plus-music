/* Settings for the stock Atmosphere Lamp's sample-rate indicator (patch/tracklamp.c). */
#pragma once

#define TL_FILE "/mnt/data/m1plus/rgb-indicator" /* "0" off; any other value enables Sample Rate RGB */
#define TL_TMP "/mnt/data/m1plus/rgb-indicator.tmp"

int formatlamp_enabled(void);
int formatlamp_set_enabled(int enabled); /* 1/0, or -1 if it could not be saved */
unsigned formatlamp_rgb_levels(void *record, const unsigned info[13], int volume); /* packed 0xRRGGBB, levels 0..17 */

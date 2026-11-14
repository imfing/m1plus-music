/* Sample-rate RGB indicator for the stock Atmosphere Lamp.
 *
 * Reads the currently playing track's format metadata and current volume, then
 * stages the matching colour/intensity in Shanling's transient lamp state.
 * No audio samples or playback controls are read or changed.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "covercache.h"
#include "radio.h"
#include "tracklamp.h"

/* Stock Display-page helpers, retained as the implementation for Off/Green/Blue. */
int disp_led(void);
int disp_led_set(int mode);
int disp_follow(void);

enum { TL_INTENSITY = 0x11, TL_RATIO_SCALE = 100, TL_VOLUME_FULL_INTENSITY = 85 };

static struct {
    int active;
    int setting; /* 0 unread, otherwise enabled + 1 */
    int volume_seen, volume_high;
    unsigned timer, last_poll, pause_at, alert_at, battery_at, battery_next;
    unsigned mix, random, flame_brightness, flame_green;
    unsigned effect_elapsed, effect_last;
    int options_loaded, effect, theme, warning, volume_brightness;
    int paused, battery_seen, battery_level;
} tl __attribute__((section(".scratch")));

static const unsigned char tl_palettes[10][10][3] = {{{65, 10, 25},
                                                      {50, 10, 40},
                                                      {30, 10, 60},
                                                      {10, 20, 70},
                                                      {10, 35, 55},
                                                      {10, 50, 40},
                                                      {10, 65, 25},
                                                      {15, 75, 10},
                                                      {10, 80, 10},
                                                      {0, 100, 0}},
                                                     {{90, 5, 5},
                                                      {85, 10, 5},
                                                      {80, 15, 5},
                                                      {75, 20, 5},
                                                      {70, 25, 5},
                                                      {65, 30, 5},
                                                      {60, 35, 5},
                                                      {55, 40, 5},
                                                      {50, 45, 5},
                                                      {45, 45, 10}},
                                                     {{5, 5, 90},
                                                      {5, 10, 85},
                                                      {5, 20, 75},
                                                      {5, 30, 65},
                                                      {5, 40, 55},
                                                      {10, 40, 50},
                                                      {15, 40, 45},
                                                      {20, 40, 40},
                                                      {25, 35, 40},
                                                      {30, 35, 35}},
                                                     {{70, 5, 25},
                                                      {55, 5, 40},
                                                      {40, 5, 55},
                                                      {25, 5, 70},
                                                      {10, 15, 75},
                                                      {5, 30, 65},
                                                      {5, 50, 45},
                                                      {5, 65, 30},
                                                      {5, 75, 20},
                                                      {5, 85, 10}},
                                                     {{55, 20, 25},
                                                      {45, 20, 35},
                                                      {35, 20, 45},
                                                      {25, 25, 50},
                                                      {20, 35, 45},
                                                      {20, 45, 35},
                                                      {25, 50, 25},
                                                      {30, 50, 20},
                                                      {35, 45, 20},
                                                      {40, 40, 20}},
                                                     {{60, 10, 30},
                                                      {70, 10, 20},
                                                      {80, 15, 5},
                                                      {85, 20, 5},
                                                      {90, 30, 10},
                                                      {75, 40, 15},
                                                      {60, 50, 20},
                                                      {45, 60, 35},
                                                      {25, 75, 60},
                                                      {0, 90, 100}},
                                                     {{15, 60, 25},
                                                      {20, 65, 15},
                                                      {25, 70, 5},
                                                      {30, 60, 10},
                                                      {35, 50, 15},
                                                      {40, 40, 30},
                                                      {45, 35, 40},
                                                      {50, 30, 55},
                                                      {40, 35, 75},
                                                      {30, 40, 90}},
                                                     {{90, 10, 0},
                                                      {85, 15, 0},
                                                      {80, 20, 0},
                                                      {75, 25, 0},
                                                      {70, 30, 0},
                                                      {65, 35, 0},
                                                      {60, 40, 0},
                                                      {55, 45, 0},
                                                      {50, 50, 0},
                                                      {45, 55, 0}},
                                                     {{50, 10, 70},
                                                      {60, 10, 60},
                                                      {70, 10, 50},
                                                      {80, 15, 40},
                                                      {90, 20, 30},
                                                      {75, 30, 35},
                                                      {60, 40, 40},
                                                      {45, 50, 50},
                                                      {30, 60, 65},
                                                      {15, 75, 80}},
                                                     {{90, 90, 90},
                                                      {85, 88, 92},
                                                      {80, 85, 95},
                                                      {70, 80, 98},
                                                      {60, 75, 100},
                                                      {50, 70, 95},
                                                      {40, 65, 90},
                                                      {30, 60, 85},
                                                      {20, 55, 80},
                                                      {10, 50, 75}}};

/* The user selects a complete visual personality, rather than independently
 * combining an effect and palette. The stored values remain the compact
 * effect/palette pair used by the renderer. */
static const unsigned char tl_theme_effect[10] = {0, 1, 2, 3, 9, 10, 12, 14, 13, 11};
static const unsigned char tl_theme_palette[10] = {0, 3, 1, 2, 6, 8, 4, 7, 0, 1};

static void tl_options(void) {
    char text[5] = {0};
    int fd, n;
    if (tl.options_loaded) return;
    tl.options_loaded = 1;
    tl.effect = tl_theme_effect[0];
    tl.theme = tl_theme_palette[0];
    tl.warning = 0;
    tl.volume_brightness = 1;
    fd = open("/mnt/data/m1plus/sample-rate-rgb-options", 0, 0);
    if (fd < 0) return;
    n = read(fd, text, sizeof text);
    close(fd);
    int effect = text[0] >= '0' && text[0] <= '9'   ? text[0] - '0'
                 : text[0] >= 'A' && text[0] <= 'E' ? text[0] - 'A' + 10
                                                    : -1;
    if ((n == 4 || n == 5) && effect >= 0 && text[1] >= '0' && text[1] <= '9' && (text[2] == '0' || text[2] == '1') &&
        (n == 4 || text[3] == '0' || text[3] == '1') && text[n - 1] == '\n') {
        unsigned i;
        for (i = 0; i < 10; ++i)
            if (effect == tl_theme_effect[i] && text[1] - '0' == tl_theme_palette[i]) {
                tl.effect = effect;
                tl.theme = text[1] - '0';
                tl.warning = text[2] - '0';
                if (n == 5) tl.volume_brightness = text[3] - '0';
                break;
            }
    }
}

int formatlamp_theme(void) {
    unsigned i;
    tl_options();
    for (i = 0; i < 10; ++i)
        if (tl.effect == tl_theme_effect[i] && tl.theme == tl_theme_palette[i]) return (int)i;
    return 0;
}
int formatlamp_warning(void) {
    tl_options();
    return tl.warning;
}
int formatlamp_volume_brightness(void) {
    tl_options();
    return tl.volume_brightness;
}

static int tl_option_save(int effect, int theme, int warning, int volume_brightness) {
    char text[6] = {(char)(effect < 10 ? '0' + effect : 'A' + effect - 10),
                    (char)('0' + theme),
                    (char)('0' + warning),
                    (char)('0' + !!volume_brightness),
                    '\n',
                    0};
    if (home_write_atomic("/mnt/data/m1plus/sample-rate-rgb-options", "/mnt/data/m1plus/sample-rate-rgb-options.tmp",
                          text))
        return -1;
    tl.effect = effect;
    tl.theme = theme;
    tl.warning = warning;
    tl.volume_brightness = !!volume_brightness;
    return 0;
}

int formatlamp_select_theme(int theme) {
    tl_options();
    if (theme < 0 || theme >= 10 ||
        tl_option_save(tl_theme_effect[theme], tl_theme_palette[theme], tl.warning, tl.volume_brightness))
        return -1;
    tl.effect_elapsed = 0;
    tl.effect_last = time_now_ms();
    return theme;
}
int formatlamp_set_warning(int enabled) {
    tl_options();
    if (tl_option_save(tl.effect, tl.theme, !!enabled, tl.volume_brightness)) return -1;
    if (!enabled) tl.alert_at = 0;
    return !!enabled;
}
int formatlamp_set_volume_brightness(int enabled) {
    tl_options();
    if (tl_option_save(tl.effect, tl.theme, tl.warning, !!enabled)) return -1;
    return !!enabled;
}

static int tl_setting_read(void) { return set_read(TL_FILE, '0') == '1'; }

int formatlamp_enabled(void) {
    if (!tl.setting) tl.setting = tl_setting_read() + 1;
    return tl.setting - 1;
}

static int tl_eq(const char *a, const char *b) {
    unsigned i;
    if (!a || !b) return 0;
    for (i = 0; i < 12; ++i) {
        unsigned x = (unsigned char)a[i], y = (unsigned char)b[i];
        if (x >= 'A' && x <= 'Z') x += 'a' - 'A';
        if (y >= 'A' && y <= 'Z') y += 'a' - 'A';
        if (x != y) return 0;
        if (!x) return 1;
    }
    return 0;
}

/* The queue name carries the original server suffix for Navidrome rows and
 * the scanned filename for local rows. Stop at URL query delimiters just in
 * case a stock-created record carries a URL there. */
static const char *tl_ext(const char *name) {
    const char *dot = (const char *)0;
    unsigned i;
    if (!name) return (const char *)0;
    for (i = 0; i < 256 && name[i]; ++i) {
        if (name[i] == '?' || name[i] == '#') break;
        if (name[i] == '.') dot = name + i + 1;
    }
    return dot;
}

static int tl_is_dsd(const char *ext) { return tl_eq(ext, "dsf") || tl_eq(ext, "dff") || tl_eq(ext, "iso"); }

static int tl_is_dsd_format(const char *format) {
    unsigned char a, b, c;
    if (tl_eq(format, "dsd") || tl_eq(format, "dsf") || tl_eq(format, "dff") || tl_eq(format, "iso")) return 1;
    if (!format) return 0;
    a = (unsigned char)format[0];
    b = (unsigned char)format[1];
    c = (unsigned char)format[2];
    if (a >= 'A' && a <= 'Z') a += 'a' - 'A';
    if (b >= 'A' && b <= 'Z') b += 'a' - 'A';
    if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    return a == 'd' && b == 's' && c == 'd'; /* recognize labels such as DSD128 */
}

static unsigned tl_rgb(unsigned red, unsigned green, unsigned blue) { return (red << 16) | (green << 8) | blue; }

static unsigned tl_rate_mix(unsigned rate) {
    static const unsigned limits[9] = {44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000, 1411199};
    unsigned slot = 0;
    const unsigned char *colour;
    while (slot < 9 && rate > limits[slot]) ++slot;
    tl_options();
    colour = tl_palettes[tl.theme][slot];
    return tl_rgb(colour[0], colour[1], colour[2]);
}

static unsigned tl_classify(void *record, const unsigned info[13]) {
    const char *name = cc_str(record, REC_NAME);
    const char *ext = tl_ext(name);
    const char *format = (const char *)(info + 4); /* MCL codec label at +0x10. */
    unsigned rate = info[1];
    if (!ext) ext = tl_ext(cc_str(record, REC_PATH));
    if (tl_is_dsd(ext) || tl_is_dsd_format(format)) {
        rate /= 16u; /* Normalize native DSD to the corresponding DoP carrier. */
    }
    return tl_rate_mix(rate);
}

static unsigned tl_volume_intensity(int volume) {
    tl_options();
    if (!tl.volume_brightness) return TL_INTENSITY;
    if (volume <= 0) return 0;
    if (volume >= TL_VOLUME_FULL_INTENSITY) return TL_INTENSITY;
    return ((unsigned)volume + 4u) / 5u; /* 1-5 -> 1, 6-10 -> 2, ... 81-85 -> 17. */
}

static unsigned tl_scale_channel(unsigned intensity, unsigned ratio) {
    return (intensity * ratio + TL_RATIO_SCALE / 2u) / TL_RATIO_SCALE;
}

unsigned formatlamp_rgb_levels(void *record, const unsigned info[13], int volume) {
    unsigned mix, intensity;
    if (!record || !info) return 0;
    mix = tl_classify(record, info);
    intensity = tl_volume_intensity(volume);
    return tl_rgb(tl_scale_channel(intensity, (mix >> 16) & 0xffu), tl_scale_channel(intensity, (mix >> 8) & 0xffu),
                  tl_scale_channel(intensity, mix & 0xffu));
}

static void tl_restore(void) {
    if (tl.timer) timer_remove(tl.timer);
    tl.timer = 0;
    tl.paused = 0;
    tl.effect_elapsed = 0;
    if (!tl.active) return;
    reset_atmosphereled_rgb(); /* reload the user's persistent stock lamp colors */
    tl.active = 0;
}

int formatlamp_set_enabled(int enabled) {
    const char *value;
    enabled = enabled ? 1 : 0;
    if (enabled == formatlamp_enabled()) return enabled;
    value = enabled ? "1\n" : "0\n";
    if (home_write_atomic(TL_FILE, TL_TMP, value) != 0) return -1;
    tl.setting = enabled + 1;
    tl.alert_at = tl.battery_at = 0;
    tl.volume_seen = 0;
    tl.battery_seen = tl.battery_level = 0;
    tl_restore(); /* let the stock timer regain its lamp before the next update */
    return enabled;
}

/* LED Light keeps its stock choices; Sample Rate is a fourth choice that
 * hands lamp ownership to this module. */
int formatlamp_led_mode(void) { return formatlamp_enabled() ? 3 : disp_led(); }
int formatlamp_led_set(int mode) {
    if (mode == 3) {
        if (formatlamp_set_enabled(1) < 0 || disp_led_set(0) < 0) return -1;
        return 3;
    }
    if (mode < 0 || mode > 2 || formatlamp_set_enabled(0) < 0) return -1;
    return disp_led_set(mode);
}

static void tl_output(unsigned red, unsigned green, unsigned blue) {
    volatile unsigned char *rgb = (volatile unsigned char *)ATMOSPHERE_RGB_STATE;
    unsigned char r = red > TL_INTENSITY ? TL_INTENSITY : (unsigned char)red;
    unsigned char g = green > TL_INTENSITY ? TL_INTENSITY : (unsigned char)green;
    unsigned char b = blue > TL_INTENSITY ? TL_INTENSITY : (unsigned char)blue;
    /* Stock light_state is stored as [red, blue, green]; its timer reorders
     * the last two bytes when calling config_atmosphere_light. */
    if (rgb[0] != r || rgb[1] != b || rgb[2] != g) {
        char text[16];
        int length = snprintf(text, sizeof text, "%u\n", ((unsigned)r << 16) | ((unsigned)g << 8) | b);
        int fd = open("/sys/class/led_ktd2026/led_config_rgb", O_WRONLY, 0);
        if (fd < 0) return;
        int written = write(fd, text, (unsigned)length);
        close(fd);
        if (written != length) return;
        rgb[0] = r;
        rgb[1] = b;
        rgb[2] = g;
        rgb[3] = 0;
    }
    tl.active = 1;
}

/* Ratios remain 0..100 until the common volume scaling step. */
static unsigned tl_blend(unsigned a, unsigned b, unsigned position, unsigned duration) {
    unsigned red = (((a >> 16) & 255u) * (duration - position) + ((b >> 16) & 255u) * position) / duration;
    unsigned green = (((a >> 8) & 255u) * (duration - position) + ((b >> 8) & 255u) * position) / duration;
    unsigned blue = ((a & 255u) * (duration - position) + (b & 255u) * position) / duration;
    return tl_rgb(red, green, blue);
}

static unsigned tl_sine(unsigned elapsed, unsigned period) {
    static const unsigned char wave[33] = {50, 60, 69, 78, 85, 92, 96, 99, 100, 99, 96, 92, 85, 78, 69, 60, 50,
                                           40, 31, 22, 15, 8,  4,  1,  0,  1,   4,  8,  15, 22, 31, 40, 50};
    unsigned position = (elapsed % period) * 32u, index = position / period, fraction = position % period;
    return (wave[index] * (period - fraction) + wave[index + 1u] * fraction) / period;
}

static unsigned tl_smooth(unsigned position, unsigned duration) {
    unsigned t = position * 1000u / duration;
    return t * t * (3000u - 2u * t) / 1000000u;
}

static unsigned tl_ambient(unsigned elapsed) {
    unsigned position, segment, colour;
    if (tl.effect == 9) {
        colour = tl_blend(tl_rgb(8, 75, 17), tl_rgb(35, 55, 10), tl_sine(elapsed, 17000), 100);
        return tl_blend(colour, tl_rgb(65, 30, 5), tl_sine(elapsed, 61000) / 3u, 100);
    }
    if (tl.effect == 10) {
        static const unsigned nebula[5] = {0x320a32, 0x140550, 0x230a41, 0x460f1e, 0x28143c};
        segment = (elapsed / 60000u) % 5u;
        return tl_blend(nebula[segment], nebula[(segment + 1u) % 5u], tl_smooth(elapsed % 60000u, 60000), 1000);
    }
    if (tl.effect == 11) {
        static const unsigned ember[5] = {0x643c10, 0x641e05, 0x500c00, 0x400005, 0x1e0528};
        position = elapsed % 90000u;
        segment = position / 22500u;
        if (segment >= 4) segment = 3;
        return tl_blend(ember[segment], ember[segment + 1u], tl_smooth(position - segment * 22500u, 22500), 1000);
    }
    /* Focus Fade reaches warm amber after 25 minutes and holds it until stopped
     * or explicitly selected again. Playback pause and transient alerts suspend its clock. */
    position = elapsed > 1500000u ? 1500000u : elapsed;
    return tl_blend(tl_rgb(30, 35, 35), tl_rgb(65, 30, 5), tl_smooth(position, 1500000), 1000);
}

static int tl_animate(const void *unused) {
    unsigned now = time_now_ms(), mix = tl.mix, scale = 100, phase;
    unsigned red, green, blue;
    unsigned delta = now - tl.effect_last;
    tl.effect_last = now;
    (void)unused;
    if (!formatlamp_enabled() || now - tl.last_poll > 3000u) {
        tl.timer = 0;
        tl_restore();
        return RET_OK;
    }
    if (tl.alert_at && now - tl.alert_at < 900u) {
        phase = (now - tl.alert_at) / 150u;
        unsigned level = phase & 1u ? 0 : TL_INTENSITY;
        tl_output(level, level, 0);
        return RET_REPEAT;
    }
    tl.alert_at = 0;
    if (tl.battery_at && now - tl.battery_at < 800u) {
        unsigned level = ((now - tl.battery_at) / 200u) & 1u ? 0 : TL_INTENSITY;
        tl_output(level, level * 6u / 17u, 0);
        return RET_REPEAT;
    }
    tl.battery_at = 0;
    if (!tl.paused) {
        if (tl.effect == 14 && delta > 1500000u - tl.effect_elapsed)
            tl.effect_elapsed = 1500000;
        else
            tl.effect_elapsed += delta;
    }
    if (tl.paused) {
        unsigned elapsed = now - tl.pause_at;
        if (elapsed >= 2500u) {
            tl_output(0, 0, 0);
            tl.timer = 0;
            return RET_OK;
        }
        scale = elapsed < 500u ? 100u - elapsed * 80u / 500u : elapsed < 2500u ? 20u : 0;
    } else if (tl.effect == 1) {
        phase = now % 4000u;
        if (phase > 2000u) phase = 4000u - phase;
        scale = 15u + phase * 85u / 2000u;
    } else if (tl.effect == 2) {
        tl.random = tl.random * 1664525u + 1013904223u;
        unsigned brightness = 55u + ((tl.random >> 16) % 46u);
        unsigned warm = 3u + ((tl.random >> 24) % 7u);
        if (!tl.flame_brightness) tl.flame_brightness = 75;
        if (!tl.flame_green) tl.flame_green = 6;
        if (brightness > tl.flame_brightness)
            ++tl.flame_brightness;
        else if (brightness < tl.flame_brightness)
            --tl.flame_brightness;
        if (warm > tl.flame_green)
            ++tl.flame_green;
        else if (warm < tl.flame_green)
            --tl.flame_green;
        mix = tl_rgb(17, tl.flame_green, 0);
        scale = tl.flame_brightness;
        scale = scale * tl_volume_intensity(*(volatile int *)G_VOLUME) / TL_INTENSITY;
    } else if (tl.effect == 3) {
        static const unsigned char wheel[6][3] = {{100, 0, 0}, {70, 30, 0}, {50, 50, 0},
                                                  {0, 100, 0}, {0, 0, 100}, {50, 0, 50}};
        unsigned position = now % 12000u, segment = position / 2000u, fraction = position % 2000u;
        const unsigned char *a = wheel[segment], *b = wheel[(segment + 1u) % 6u];
        unsigned intensity = tl_volume_intensity(*(volatile int *)G_VOLUME);
        red = (a[0] * (2000u - fraction) + b[0] * fraction) / 2000u;
        green = (a[1] * (2000u - fraction) + b[1] * fraction) / 2000u;
        blue = (a[2] * (2000u - fraction) + b[2] * fraction) / 2000u;
        mix = tl_rgb(tl_scale_channel(intensity, red), tl_scale_channel(intensity, green),
                     tl_scale_channel(intensity, blue));
    } else if (tl.effect == 12) {
        phase = tl.effect_elapsed % 1600u;
        if (phase < 140u)
            scale = tl_smooth(phase, 140);
        else if (phase < 320u)
            scale = 1000u - tl_smooth(phase - 140u, 180);
        else if (phase < 460u)
            scale = tl_smooth(phase - 320u, 140) * 65u / 100u;
        else if (phase < 700u)
            scale = (1000u - tl_smooth(phase - 460u, 240)) * 65u / 100u;
        else
            scale = 0;
        scale /= 10u;
    } else if (tl.effect == 13) {
        phase = tl.effect_elapsed % 6000u;
        if (phase < 2000u)
            scale = tl_smooth(phase, 2000) * 65u / 1000u;
        else if (phase < 2200u)
            scale = 65u + tl_smooth(phase - 2000u, 200) * 35u / 1000u;
        else if (phase < 5000u)
            scale = (1000u - tl_smooth(phase - 2200u, 2800)) / 10u;
        else
            scale = 0;
    } else if (tl.effect >= 6) {
        mix = tl_ambient(tl.effect_elapsed);
        unsigned intensity = tl_volume_intensity(*(volatile int *)G_VOLUME);
        red = tl_scale_channel(intensity, (mix >> 16) & 255u);
        green = tl_scale_channel(intensity, (mix >> 8) & 255u);
        blue = tl_scale_channel(intensity, mix & 255u);
        mix = tl_rgb(red, green, blue);
        if (tl.effect == 9) scale = 70u + tl_sine(tl.effect_elapsed, 11000) * 30u / 100u;
        if (tl.effect == 11) {
            phase = tl.effect_elapsed % 90000u;
            scale = phase < 2000u ? tl_smooth(phase, 2000) / 10u : 100u - phase * 85u / 90000u;
        }
    }
    tl_output(((mix >> 16) & 255u) * scale / 100u, ((mix >> 8) & 255u) * scale / 100u, (mix & 255u) * scale / 100u);
    return RET_REPEAT;
}

static void tl_apply_rgb(unsigned red, unsigned green, unsigned blue) {
    tl.mix = tl_rgb(red, green, blue);
    tl.last_poll = time_now_ms();
    if (!tl.effect && !tl.alert_at && !tl.battery_at && !tl.paused) {
        if (tl.timer) timer_remove(tl.timer);
        tl.timer = 0;
        tl_output(red, green, blue);
        return;
    }
    if (!tl.timer) {
        tl.effect_last = tl.last_poll;
        tl.timer = timer_add(tl_animate, (void *)0, tl.effect == 2 || tl.effect == 3 || tl.effect == 12 ? 50 : 250);
    }
    if (!tl.timer)
        tl_output(red, green, blue);
    else
        tl_animate((void *)0);
}

/* A sustained high volume cannot retrigger the timed reminder.
 * Establish a baseline on the first refresh. */
static void tl_volume_alert(int volume) {
    int high = volume > 75;
    if (tl.volume_seen && high && !tl.volume_high && formatlamp_warning()) tl.alert_at = time_now_ms();
    tl.volume_seen = 1;
    tl.volume_high = high;
    if (!high || !formatlamp_warning()) tl.alert_at = 0;
}

static void tl_battery_check(void) {
    static const unsigned thresholds[3] = {20, 10, 5};
    char text[8];
    unsigned now = time_now_ms();
    if ((int)(now - tl.battery_next) < 0) return;
    tl.battery_next = now + 60000u;
    int fd = open("/sys/class/power_supply/battery/capacity", 0, 0);
    int n = fd < 0 ? -1 : read(fd, text, sizeof text - 1);
    unsigned capacity = 0, i = 0;
    if (fd >= 0) close(fd);
    if (n <= 0) return;
    text[n] = 0;
    while (i < (unsigned)n && text[i] >= '0' && text[i] <= '9') {
        capacity = capacity * 10u + (unsigned)(text[i++] - '0');
        if (capacity > 100u) return;
    }
    if (!i || (i < (unsigned)n && (text[i] != '\n' || i + 1u != (unsigned)n))) return;
    fd = open("/sys/class/power_supply/battery/status", 0, 0);
    n = fd < 0 ? -1 : read(fd, text, sizeof text);
    if (fd >= 0) close(fd);
    int charging = n > 0 && (text[0] == 'C' || text[0] == 'F');
    for (i = 0; i < 3; ++i) {
        if (capacity >= thresholds[i] + 3u) tl.battery_level &= ~(1 << i);
        if (capacity <= thresholds[i] && !(tl.battery_level & (1 << i))) {
            tl.battery_level |= 1 << i;
            if (tl.battery_seen && !charging) tl.battery_at = time_now_ms();
        }
    }
    tl.battery_seen = 1;
}

/* Patched at the stock on_wm_idle_status call to mclGetPlayStatus. Keep the
 * original result and update the lamp only while a track is actively playing. */
int tl_play_status(void) {
    int status = mclGetPlayStatus();
    void *record;
    unsigned info[13] = {0}; /* A failed/partial stock snapshot must not read stack garbage. */
    unsigned rgb;
    if (!formatlamp_enabled()) {
        tl.alert_at = 0;
        tl.battery_at = 0;
        tl.volume_seen = 0;
        tl_restore();
        return status;
    }
    if (access(KILL_SD, F_OK) == 0) {
        tl.alert_at = 0;
        tl.battery_at = 0;
        tl.volume_seen = 0;
        tl_restore();
        return status;
    }
    /* Follow Screen is stock's saved preference.  Use its own verified
     * backlight state rather than waking or touching display power: while
     * dark, release the transient RGB state (stock LED mode is Off in Sample
     * Rate mode), cancel animation work and resume on the next lit status. */
    if (disp_follow() && !m1_screen_lit()) {
        tl_restore();
        return status;
    }
    tl_volume_alert(*(volatile int *)G_VOLUME);
    if (formatlamp_warning())
        tl_battery_check();
    else
        tl.battery_at = 0;
    if (rd_running()) {
        tl_restore();
        return status;
    }
    if (*(volatile int *)TL_USB_LINK == 2 && *(volatile unsigned char *)TL_USB_MODE == 1) {
        tl.paused = 0;
        char text[32];
        unsigned rate = 0;
        int fd = open("/sys/class/uac2/uac2_samprate", 0, 0);
        int n = fd < 0 ? -1 : read(fd, text, sizeof text - 1);
        if (fd >= 0) close(fd);
        if (n > 0) {
            text[n] = 0;
            rate = (unsigned)atoi(text);
        }
        if (!rate) {
            tl_restore();
            return status;
        }
        if (rate == 2822400u || rate == 5644800u || rate == 11289600u || rate == 22579200u || rate == 45158400u)
            rate /= 16u;
        /* No queue record belongs to USB input. Scale the shared rate colour directly. */
        rgb = tl_rate_mix(rate);
        unsigned intensity = tl_volume_intensity(*(volatile int *)G_VOLUME);
        tl_apply_rgb(tl_scale_channel(intensity, (rgb >> 16) & 255u), tl_scale_channel(intensity, (rgb >> 8) & 255u),
                     tl_scale_channel(intensity, rgb & 255u));
        return status;
    }
    if (status == 3 && tl.active) {
        if (!tl.paused) {
            volatile unsigned char *current = (volatile unsigned char *)ATMOSPHERE_RGB_STATE;
            tl.pause_at = time_now_ms();
            tl.mix = tl_rgb(current[0], current[2], current[1]);
        }
        tl.paused = 1;
        tl.last_poll = time_now_ms();
        if (!tl.timer && (tl.last_poll - tl.pause_at < 2500u || tl.alert_at || tl.battery_at))
            tl.timer = timer_add(tl_animate, (void *)0, 50);
        return status;
    }
    tl.paused = 0;
    if (status != 2) {
        unsigned now = time_now_ms();
        if ((tl.alert_at && now - tl.alert_at < 900u) || (tl.battery_at && now - tl.battery_at < 800u)) {
            tl_apply_rgb(0, 0, 0);
            return status;
        }
        tl_restore();
        return status;
    }
    record = cc_playing();
    if (!record) {
        tl_restore();
        return status;
    }
    mclGetInfo(info); /* stock 0x34-byte snapshot: sample rate @+4, bit depth @+0x30. */
    rgb = formatlamp_rgb_levels(record, info, *(volatile int *)G_VOLUME);
    tl_apply_rgb((rgb >> 16) & 0xffu, (rgb >> 8) & 0xffu, rgb & 0xffu);
    return status;
}

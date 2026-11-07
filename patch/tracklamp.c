/* Sample-rate RGB indicator for the stock Atmosphere Lamp.
 *
 * Reads the currently playing track's format metadata and current volume, then
 * stages the matching colour/intensity in Shanling's transient lamp state.
 * No audio samples or playback controls are read or changed.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "radio.h"
#include "tracklamp.h"

enum { TL_INTENSITY = 0x11, TL_RATIO_SCALE = 100, TL_VOLUME_FULL_INTENSITY = 85 };

static struct {
    int active;
    int setting; /* 0 unread, otherwise enabled + 1 */
} tl __attribute__((section(".scratch")));

static int tl_setting_read(void) {
    /* Old Visualizer builds stored "2". Keep the feature enabled as the new
     * Sample Rate RGB mode when upgrading; only an explicit "0" disables it. */
    return set_read(TL_FILE, '1') != '0';
}

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

static int tl_is_lossless_format(const char *format) {
    return tl_eq(format, "flac") || tl_eq(format, "alac") || tl_eq(format, "wav") || tl_eq(format, "wave") ||
           tl_eq(format, "ape") || tl_eq(format, "aiff") || tl_eq(format, "aif");
}

static int tl_is_lossy(const char *ext, const char *format) {
    if (tl_is_lossless_format(format)) return 0; /* e.g. ALAC commonly uses the .m4a suffix. */
    return tl_eq(ext, "mp3") || tl_eq(ext, "mp2") || tl_eq(ext, "aac") || tl_eq(ext, "ogg") || tl_eq(ext, "oga") ||
           tl_eq(ext, "opus") || tl_eq(ext, "wma") || tl_eq(ext, "m4a") || tl_eq(ext, "mp4") || tl_eq(ext, "ac3") ||
           tl_eq(ext, "eac3") || tl_eq(ext, "ra") || tl_eq(ext, "rm") || tl_eq(ext, "3gp") || tl_eq(ext, "amr") ||
           tl_eq(ext, "mpc") || tl_eq(format, "mp3") || tl_eq(format, "mp2") || tl_eq(format, "aac") ||
           tl_eq(format, "ogg") || tl_eq(format, "vorbis") || tl_eq(format, "opus") || tl_eq(format, "wma") ||
           tl_eq(format, "ac3") || tl_eq(format, "eac3") || tl_eq(format, "amr");
}

static unsigned tl_rgb(unsigned red, unsigned green, unsigned blue) { return (red << 16) | (green << 8) | blue; }

static unsigned tl_classify(void *record, const unsigned info[13]) {
    const char *name = cc_str(record, REC_NAME);
    const char *ext = tl_ext(name);
    const char *format = (const char *)(info + 4); /* MCL codec label at +0x10. */
    unsigned rate = info[1], depth = info[12];
    if (!ext) ext = tl_ext(cc_str(record, REC_PATH));
    if (tl_is_dsd(ext) || tl_is_dsd_format(format)) {
        if (!rate) return tl_rgb(TL_RATIO_SCALE, 0, 0); /* Unknown DSD rate keeps the conservative red fallback. */
        if (rate < 5644800u) return tl_rgb(60, 0, 40); /* DSD64. */
        if (rate < 11289600u) return tl_rgb(0, 20, 80); /* DSD128. */
        if (rate < 22579200u) return tl_rgb(0, 40, 60); /* DSD256. */
        return tl_rgb(0, TL_RATIO_SCALE, 0); /* DSD512 and above. */
    }
    if (tl_is_lossy(ext, format)) return tl_rgb(TL_RATIO_SCALE, 0, 0);
    if (rate <= 44100u) {
        if (depth <= 16u) return tl_rgb(TL_RATIO_SCALE, 0, 0);
        return tl_rgb(60, 0, 40);
    }
    if (rate <= 48000u) return tl_rgb(20, 0, 80);
    if (rate <= 88200u) return tl_rgb(0, 0, TL_RATIO_SCALE);
    if (rate < 176400u) return tl_rgb(0, 20, 80);
    if (rate < 192000u) return tl_rgb(0, 40, 60);
    return depth >= 24u ? tl_rgb(0, TL_RATIO_SCALE, 0) : tl_rgb(0, 0, TL_RATIO_SCALE);
}

static unsigned tl_volume_intensity(int volume) {
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
    tl_restore(); /* let the stock timer regain its lamp before the next update */
    return enabled;
}

static void tl_apply_rgb(unsigned red, unsigned green, unsigned blue) {
    volatile unsigned char *rgb = (volatile unsigned char *)ATMOSPHERE_RGB_STATE;
    unsigned char r = red > TL_INTENSITY ? TL_INTENSITY : (unsigned char)red;
    unsigned char g = green > TL_INTENSITY ? TL_INTENSITY : (unsigned char)green;
    unsigned char b = blue > TL_INTENSITY ? TL_INTENSITY : (unsigned char)blue;
    /* Stock light_state is stored as [red, blue, green]; its timer reorders
     * the last two bytes when calling config_atmosphere_light. */
    if (rgb[0] != r || rgb[1] != b || rgb[2] != g) {
        rgb[0] = r;
        rgb[1] = b;
        rgb[2] = g;
        rgb[3] = 1; /* Shanling's existing timer applies the staged RGB. */
    }
    tl.active = 1;
}

/* Patched at the stock on_wm_idle_status call to mclGetPlayStatus. Keep the
 * original result and update the lamp only while a track is actively playing. */
int tl_play_status(void) {
    int status = mclGetPlayStatus();
    void *record;
    unsigned info[13];
    unsigned rgb;
    if (!formatlamp_enabled() || status != 2 || rd_running()) {
        tl_restore();
        return status;
    }
    if (access(KILL_SD, F_OK) == 0) {
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

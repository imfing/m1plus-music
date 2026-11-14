/* Sample Rate: the stock lamp shows the playing track's sample rate (Settings > System > Display > LED Light > Sample Rate; docs/modules/display.md
 * "Sample Rate"; contributed in PR #5).
 *
 * Opt in: with the setting off the hook is one cached compare. With it on the hook only keeps one timer of ours alive; the timer asks the player
 * TL_POLL_MS apart (the status, the track's format, the kill switch, Follow Screen, the radio, USB DAC mode) and draws the theme's frame on every
 * tick: TL_FAST_MS apart while a theme moves, TL_POLL_MS apart otherwise. The lamp file is written only when a level changes (18 levels a channel).
 * No audio samples or playback controls are read or changed.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "covercache.h"
#include "radio.h"
#include "tracklamp.h"

/* Stock's lamp mode and Follow Screen (patch/display.c): Off, Green and Blue stay stock's. */
int disp_led(void);
int disp_led_set(int mode);
int disp_follow(void);

enum { TL_NONE, TL_PLAY, TL_PAUSE }; /* tl.mode: the lamp is stock's; the theme plays; the fade after a pause */

static struct {
    int setting; /* 0 unread, else the saved character - '0' + 1 (1 off, 2 .. TL_THEMES + 1 a theme) */
    int active; /* the lamp shows a colour of ours */
    int mode, gone;
    unsigned timer, period, poll_at, pause_at, last, elapsed;
    unsigned mix; /* the rate's colour in the theme's palette, 0xRRGGBB, each channel 0 .. 100 */
    unsigned random, flame, warm; /* Candle's walk */
} tl __attribute__((section(".scratch")));

/* A palette is ten colours (red, green, blue; the three add up to about 100), one per rate band. */
static const unsigned tl_limits[9] = {44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000, 1411199};
static const unsigned char tl_palettes[3][10][3] = {/* Reference, Lighthouse */
                                                    {{65, 10, 25},
                                                     {50, 10, 40},
                                                     {30, 10, 60},
                                                     {10, 20, 70},
                                                     {10, 35, 55},
                                                     {10, 50, 40},
                                                     {10, 65, 25},
                                                     {15, 75, 10},
                                                     {10, 80, 10},
                                                     {0, 100, 0}},
                                                    /* Gentle Breathe */
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
                                                    /* Heartbeat */
                                                    {{55, 20, 25},
                                                     {45, 20, 35},
                                                     {35, 20, 45},
                                                     {25, 25, 50},
                                                     {20, 35, 45},
                                                     {20, 45, 35},
                                                     {25, 50, 25},
                                                     {30, 50, 20},
                                                     {35, 45, 20},
                                                     {40, 40, 20}}};
static const unsigned char tl_palette_of[TL_THEMES] = {0, 1, 2, 0, 0, 0}; /* (Candle and Wave have their own colours) */

/* ---- the setting ---- */

static int tl_setting(void) {
    if (!tl.setting) {
        int c = set_read(TL_FILE, '0') - '0';
        tl.setting = (c >= 1 && c <= TL_THEMES ? c : 0) + 1;
    }
    return tl.setting - 1;
}

static int tl_save(int value) {
    char text[3] = {(char)('0' + value), '\n', 0};
    if (value == tl_setting()) return 0;
    if (home_write_atomic(TL_FILE, TL_TMP, text) != 0) return -1;
    tl.setting = value + 1;
    return 0;
}

/* ---- the lamp ---- */

static unsigned tl_rgb(unsigned red, unsigned green, unsigned blue) { return (red << 16) | (green << 8) | blue; }

/* Levels 0 .. TL_LEVEL, written the way stock's config_atmosphere_light (0x4e6fec) writes them, and stock's own state follows: light_state is
 * [red, blue, green, pending], and its 100 ms timer (0x4cff40) writes the state again only while pending is 1. */
static void tl_output(unsigned red, unsigned green, unsigned blue) {
    volatile unsigned char *rgb = (volatile unsigned char *)ATMOSPHERE_RGB_STATE;
    char text[16];
    int length, fd, written;
    if (rgb[0] == red && rgb[1] == blue && rgb[2] == green) return;
    length = snprintf(text, sizeof text, "%u\n", tl_rgb(red, green, blue));
    fd = open(TL_LAMP, O_WRONLY, 0);
    if (fd < 0) return;
    written = write(fd, text, (unsigned)length);
    close(fd);
    if (written != length) return;
    rgb[0] = (unsigned char)red;
    rgb[1] = (unsigned char)blue;
    rgb[2] = (unsigned char)green;
    rgb[3] = 0;
}

/* The lamp goes back to what stock shows with its mode Off (reset_atmosphereled_rgb 0x4e6b9c): red while external power charges the battery,
 * dark otherwise. (Stock's function is not called: it also saves three config values every time.) */
static void tl_release(void) {
    tl.mode = TL_NONE;
    if (!tl.active) return;
    tl.active = 0;
    tl_output(*(volatile int *)POWER_EXT == 1 && *(volatile int *)PMUCHARGE_STATUS != 2 ? TL_LEVEL : 0, 0, 0);
}

/* A colour (each channel 0 .. 100) at a brightness (0 .. 100), rounded to the lamp's levels. */
static void tl_show(unsigned colour, unsigned scale) {
    unsigned red = (TL_LEVEL * ((colour >> 16) & 255u) * scale + 5000u) / 10000u;
    unsigned green = (TL_LEVEL * ((colour >> 8) & 255u) * scale + 5000u) / 10000u;
    unsigned blue = (TL_LEVEL * (colour & 255u) * scale + 5000u) / 10000u;
    tl.active = 1;
    tl_output(red > TL_LEVEL ? TL_LEVEL : red, green > TL_LEVEL ? TL_LEVEL : green, blue > TL_LEVEL ? TL_LEVEL : blue);
}

/* ---- the playing format ---- */

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

/* The queue name carries the original server suffix for Navidrome rows and the scanned filename for local rows. Stop at URL query delimiters
 * just in case a stock-created record carries a URL there. */
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

static int tl_is_dsd(const char *ext, const char *codec) {
    if (tl_eq(ext, "dsf") || tl_eq(ext, "dff") || tl_eq(ext, "iso") || tl_eq(codec, "dsf") || tl_eq(codec, "dff") ||
        tl_eq(codec, "iso"))
        return 1;
    return (codec[0] | 0x20) == 'd' && (codec[1] | 0x20) == 's' &&
           (codec[2] | 0x20) == 'd'; /* "DSD", and labels such as "DSD128" */
}

/* The playing track's rate from the player's information (mclGetInfo: a mutex and a copy), 0 when there is none. A DSD rate becomes its DoP
 * carrier's (DSD64 shows as 176.4 kHz). */
static unsigned tl_track_rate(void) {
    int in[PLAYINFO_SIZE / 4];
    void *record = cc_playing();
    const char *ext, *codec = (const char *)in + PLAYINFO_FMT;
    unsigned rate;
    if (!record) return 0;
    memset(in, 0, sizeof in); /* (a failed or partial copy must not leave stack bytes) */
    mclGetInfo(in);
    ((char *)in)[PLAYINFO_BITS - 1] = 0;
    rate = in[PLAYINFO_RATE / 4] > 0 ? (unsigned)in[PLAYINFO_RATE / 4] : 0;
    ext = tl_ext(cc_str(record, REC_NAME));
    if (!ext) ext = tl_ext(cc_str(record, REC_PATH));
    return in[PLAYINFO_BITS / 4] == 1 || tl_is_dsd(ext, codec) ? rate / 16u : rate;
}

/* USB DAC mode has no queue record: the rate the host chose, from the gadget driver. */
static unsigned tl_dac_rate(void) {
    char text[32];
    unsigned rate = 0;
    int fd = open(TL_UAC, 0, 0), n;
    if (fd < 0) return 0;
    n = read(fd, text, sizeof text - 1);
    close(fd);
    if (n <= 0) return 0;
    text[n] = 0;
    rate = (unsigned)atoi(text);
    return rate >= 2822400u ? rate / 16u : rate; /* (a native DSD rate; no PCM rate is that high) */
}

static unsigned tl_colour(unsigned rate) {
    const unsigned char *c;
    unsigned band = 0;
    while (band < 9 && rate > tl_limits[band]) ++band;
    c = tl_palettes[tl_palette_of[tl_setting() - 1]][band];
    return tl_rgb(c[0], c[1], c[2]);
}

/* ---- the themes ---- */

static unsigned tl_smooth(unsigned position, unsigned duration) { /* 0 .. 1000, eased */
    unsigned t = position * 1000u / duration;
    return t * t * (3000u - 2u * t) / 1000000u;
}

/* The frame at tl.elapsed (the theme's own clock: it stands still while paused). Sets the brightness, returns the colour. */
static unsigned tl_frame(unsigned *scale) {
    unsigned t = tl.elapsed, phase;
    *scale = 100;
    switch (tl_setting() - 1) {
    case TL_BREATHE: /* 4 s: up and down between 15 % and full */
        phase = t % 4000u;
        if (phase > 2000u) phase = 4000u - phase;
        *scale = 15u + phase * 85u / 2000u;
        break;
    case TL_HEARTBEAT: /* 1.6 s: a beat, a softer one, a rest */
        phase = t % 1600u;
        if (phase < 140u)
            *scale = tl_smooth(phase, 140) / 10u;
        else if (phase < 320u)
            *scale = (1000u - tl_smooth(phase - 140u, 180)) / 10u;
        else if (phase < 460u)
            *scale = tl_smooth(phase - 320u, 140) * 65u / 1000u;
        else if (phase < 700u)
            *scale = (1000u - tl_smooth(phase - 460u, 240)) * 65u / 1000u;
        else
            *scale = 0;
        break;
    case TL_LIGHTHOUSE: /* 6 s: a slow rise, a flash, a long fall, a second of dark */
        phase = t % 6000u;
        if (phase < 2000u)
            *scale = tl_smooth(phase, 2000) * 65u / 1000u;
        else if (phase < 2200u)
            *scale = 65u + tl_smooth(phase - 2000u, 200) * 35u / 1000u;
        else if (phase < 5000u)
            *scale = (1000u - tl_smooth(phase - 2200u, 2800)) / 10u;
        else
            *scale = 0;
        break;
    case TL_CANDLE: { /* a flame: brightness and warmth each walk one step a tick towards a random target */
        unsigned bright, warm;
        tl.random = tl.random * 1664525u + 1013904223u;
        bright = 55u + ((tl.random >> 16) % 46u);
        warm = 18u + ((tl.random >> 24) % 36u);
        if (!tl.flame) tl.flame = 75, tl.warm = 35;
        tl.flame += bright > tl.flame ? 1 : bright < tl.flame ? -1 : 0;
        tl.warm += warm > tl.warm ? 2 : warm < tl.warm ? -2 : 0;
        *scale = tl.flame;
        return tl_rgb(100, tl.warm, 0);
    }
    case TL_OCEAN: { /* 12 s around six colours */
        static const unsigned char wheel[6][3] = {{100, 0, 0}, {70, 30, 0}, {50, 50, 0},
                                                  {0, 100, 0}, {0, 0, 100}, {50, 0, 50}};
        unsigned at = t % 12000u, f = at % 2000u;
        const unsigned char *a = wheel[at / 2000u], *b = wheel[(at / 2000u + 1u) % 6u];
        return tl_rgb((a[0] * (2000u - f) + b[0] * f) / 2000u, (a[1] * (2000u - f) + b[1] * f) / 2000u,
                      (a[2] * (2000u - f) + b[2] * f) / 2000u);
    }
    default: /* Reference: the rate's colour, steady */
        break;
    }
    return tl.mix;
}

/* ---- the timer ---- */

/* What the lamp should do now. A track that plays (or a USB host that sends) gives its colour; a pause after that fades; anything else lets the
 * lamp go, after TL_GONE polls so the gap between two tracks does not blink. */
static void tl_poll(unsigned now) {
    unsigned rate = 0;
    int status = 0;
    if (access(KILL_SD, F_OK) == 0 || (disp_follow() && !m1_screen_lit()) || rd_running()) {
        tl_release();
        return;
    }
    if (*(volatile int *)POWER_USBSTATE == 2 && *(volatile unsigned char *)POWER_FLAG == 1)
        rate = tl_dac_rate();
    else if ((status = mclGetPlayStatus()) == 2)
        rate = tl_track_rate();
    if (rate) {
        tl.mix = tl_colour(rate);
        tl.mode = TL_PLAY;
        tl.gone = 0;
    } else if (status == 3 && tl.mode != TL_NONE) {
        if (tl.mode == TL_PLAY) tl.pause_at = now;
        tl.mode = TL_PAUSE;
    } else if (tl.mode != TL_PLAY || ++tl.gone >= TL_GONE)
        tl_release();
}

static void tl_draw(unsigned now) {
    unsigned colour, scale, paused;
    if (tl.mode == TL_NONE) return;
    if (tl.mode == TL_PLAY) tl.elapsed += now - tl.last;
    colour = tl_frame(&scale);
    if (tl.mode == TL_PAUSE) { /* down to a fifth in TL_FADE_MS, then the lamp is let go TL_PAUSE_MS after the pause */
        paused = now - tl.pause_at;
        if (paused >= TL_PAUSE_MS) {
            tl_release();
            return;
        }
        scale = paused < TL_FADE_MS ? scale * (100u - paused * 80u / TL_FADE_MS) / 100u : scale / 5u;
    }
    tl_show(colour, scale);
}

static unsigned tl_period(unsigned now) {
    if (tl.mode == TL_PLAY) return tl_setting() - 1 == TL_REFERENCE ? TL_POLL_MS : TL_FAST_MS;
    return tl.mode == TL_PAUSE && now - tl.pause_at < TL_FADE_MS ? TL_FAST_MS : TL_POLL_MS;
}

static int tl_tick(const void *timer) {
    unsigned now = (unsigned)time_now_ms(), want;
    (void)timer;
    if (!tl_setting()) { /* turned off: tl_led_set gave the lamp back */
        tl.timer = 0;
        return RET_OK;
    }
    if (now - tl.poll_at >= TL_POLL_MS) {
        tl.poll_at = now;
        tl_poll(now);
    }
    tl_draw(now);
    tl.last = now;
    want = tl_period(now);
    if (want == tl.period) return RET_REPEAT;
    tl.period = want; /* another pace: this timer ends and one at the new pace starts (none: the hook starts one) */
    tl.timer = timer_add(tl_tick, (void *)0, want);
    return RET_OK;
}

/* The hook (tools/pod.py FORMAT_LAMP_SITE): stock's mclGetPlayStatus in on_wm_idle_status, an idle handler the main loop runs on every pass.
 * Stock's answer is returned unchanged. */
int tl_play_status(void) {
    int status = mclGetPlayStatus();
    if (tl_setting() && !tl.timer) {
        tl.last = (unsigned)time_now_ms();
        tl.poll_at = tl.last - TL_POLL_MS; /* the first tick asks the player */
        tl.period = TL_POLL_MS;
        tl.timer = timer_add(tl_tick, (void *)0, TL_POLL_MS);
    }
    return status;
}

/* ---- Settings ---- */

/* LED Light: stock's three modes and, as a fourth, Sample Rate (stock's mode is then Off, so stock lights nothing of its own). */
int tl_led(void) { return tl_setting() ? 3 : disp_led(); }

int tl_led_set(int mode) {
    if (mode == 3) {
        if (!tl_setting() && tl_save(1 + TL_REFERENCE) != 0) return -1;
        return disp_led_set(0);
    }
    if (mode < 0 || mode > 2 || tl_save(0) != 0) return -1;
    tl_release(); /* (the timer ends on its next tick) */
    return disp_led_set(mode);
}

/* The Sample Rate page's rows: the theme, 0 .. TL_THEMES - 1. */
int tl_theme(void) { return tl_setting() ? tl_setting() - 1 : 0; }

int tl_theme_set(int theme) {
    if (theme < 0 || theme >= TL_THEMES || tl_save(theme + 1) != 0) return -1;
    tl.elapsed = 0;
    return 0;
}

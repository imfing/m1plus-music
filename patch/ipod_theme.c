/* Pod-only light/dark appearance. Copyright (c) 2026 Xin. MIT licence, see LICENSE. */
#include "stock.h"
#include "home.h"
#include "ipod_theme.h"

static int dark __attribute__((section(".scratch")));

/* Colours are AWTK's low 24 bits: r | g << 8 | b << 16. */
/* Dark is the case and wheel only, as the black iPod Classic: its screen is the same white screen (the reference app and the real one). */
#define SCREEN_COLORS \
    0xffffffu, 0x000000u, 0x666666u, \
        0x3c3c3cu /* np_text: the artist, album and queue place, a dark grey under the black title (the user's nano photo) */
#define SCREEN_REST \
    0xf5f3f2u, 0xddddddu, {0xfdfdfdu, 0xe7e7e7u, 0xd8d8d8u, 0xabababu}, 0x6a6a6au, 0x646363u, \
        {0x5b5853u, 0x797471u, 0xa6a4a0u}, 0x000000u
static const struct ip_theme_palette palettes[2] = {{SCREEN_COLORS, 0xcec9c6u, SCREEN_REST},
                                                    {SCREEN_COLORS, 0x111111u, SCREEN_REST}};

void ip_theme_load(void) { dark = set_read(IP_THEME_FILE, 0) == '1'; /* missing and invalid settings are Light */ }

int ip_theme_dark(void) { return dark; }

int ip_theme_toggle(void) {
    int next = !dark;
    if (home_set_digit(IP_THEME_FILE, next, 1) < 0) return -1;
    dark = next;
    return dark;
}

const struct ip_theme_palette *ip_theme_colors(void) { return &palettes[dark != 0]; }

static void color(void *widget, const char *property, unsigned rgb) {
    unsigned value[4];
    if (!widget) return;
    memset(value, 0, sizeof value);
    value_set_uint32(value, 0xff000000u | rgb);
    widget_set_style(widget, property, value);
}

void ip_theme_apply(void *win, void *wheel_img) {
    static const char *const labels[] = {"label_ip_row",    "label_ip_sel", "label_ip_title", "label_ip_small",
                                         "label_ip_subsel", "label_ip_np1", "label_ip_np2",   "label_ip_time",
                                         "label_ip_val",    "label_ip_np3", "label_ip_shuf",  "label_ip_selb"};
    const struct ip_theme_palette *p = ip_theme_colors();
    unsigned colors[12];
    unsigned i;
    if (!win) return;
    color(win, "normal:bg_color", p->body);
    color(widget_lookup(win, "ipod_screen", 1), "normal:bg_color", p->bg);
    colors[0] = colors[2] = colors[5] = p->fg;
    colors[1] = colors[4] = colors[11] = 0xffffffu;
    colors[3] = p->sub;
    colors[6] = colors[9] = p->np_text, colors[7] = p->fg, colors[8] = colors[10] = 0xd2620cu;
    for (i = 0; i < 12; ++i) color(widget_lookup(win, labels[i], 1), "normal:text_color", colors[i]);
    if (wheel_img) widget_set_prop_str(wheel_img, "image", dark ? "ipod_wheel_dark" : "ipod_wheel");
    widget_invalidate_force(win, (void *)0);
}

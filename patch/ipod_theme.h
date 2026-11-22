/* Pod-only appearance. Copyright (c) 2026 Xin. MIT licence, see LICENSE. */
#pragma once

#define IP_THEME_FILE "/mnt/data/m1plus/pod-appearance"

struct ip_theme_palette {
    unsigned bg, fg, sub, np_text, body, pane, rule;
    unsigned header[4], header_rule;
    unsigned battery_edge, battery_empty[3], mode;
};

void ip_theme_load(void);
int ip_theme_dark(void);
/* Persist atomically before changing the live theme. -1 leaves the live theme unchanged. */
int ip_theme_toggle(void);
const struct ip_theme_palette *ip_theme_colors(void);
/* Update the existing window, style labels and insensitive wheel image; no new widget or timer. */
void ip_theme_apply(void *win, void *wheel_img);

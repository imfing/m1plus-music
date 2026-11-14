/* M1+ Music Settings > System > Display (docs/modules/display.md): the state behind our Display page's Screen Timeout row and its picker.
 *
 * The state is stock's own: the word backlighttime_mode (LIGHT_MODE), an index 0 .. 4 (never, 15 s, 30 s, 1 min, 5 min), loaded from [SYSSET] LIGHTTIME by config_init (anything else becomes 0)
 * and shown by stock's systemset/lighttime_page, which stays reachable through All System Settings and reads the same word. Nothing of ours is saved.
 *
 * The page's other controls are stock's state too: the brightness card (stock's own slider handlers), LED Light and Follow Screen (below). */
#include "offsets.inc"
#include "stock.h"
#include "entries.h"

#define DISP_LIGHT_MAX 4 /* stock's last index (five minutes) */
#define brightness_refresh \
    ((int (*)(void *))BRIGHT_REFRESH) /* stock's brightness page code (no symbols: tools/pod.py DATA) */

int disp_light(void) {
    int v = *(volatile int *)LIGHT_MODE;
    return v >= 0 && v <= DISP_LIGHT_MAX ? v : 0;
}

/* Choose an index the way a row of stock's page does (its handlers 0x4a8708 .. 0x4a8578 and the shared 0x4a8410, tools/pod.py LOCKSCREEN_PINS): nothing when it is the index already; else the
 * word first, then the save (stock ignores write_int_config's result too), then reset_poweroptions_timer(0, 0, 1), which sets the screen's countdown from the new word. 0, or -1 for an index
 * stock does not have. */
int disp_light_set(int index) {
    if (index < 0 || index > DISP_LIGHT_MAX) return -1;
    if (*(volatile int *)LIGHT_MODE == index) return 0;
    *(volatile int *)LIGHT_MODE = index;
    write_int_config(index, "SYSSET", "LIGHTTIME");
    reset_poweroptions_timer(0, 0, 1);
    return 0;
}

/* LED Light: stock's lamp mode, the byte atmosphereled_mode (LED_MODE): 0 off, 1 green (stock names it orange, img_orange, but reset_atmosphereled_rgb lights only the green channel), 2 blue, loaded from [SYSSET] ATMOSPHERELEDMODE by config_init (anything else becomes its default). */
int disp_led(void) {
    int v = *(volatile signed char *)LED_MODE;
    return v == 1 || v == 2 ? v : 0;
}

/* Choose a mode the way stock's page does: its switch (0x4a1c30: off, or on as green) and its two colour images (0x4a1e14, 0x4a1d8c) each store the byte, save it and call reset_atmosphereled_rgb, which makes the
 * lamp follow; a colour that is the mode already does nothing. Blue from off is one step here (stock's page shows the colours only while the lamp is on: its switch, then the colour). 0, or -1 for a mode stock
 * does not have. */
int disp_led_set(int mode) {
    if (mode < 0 || mode > 2) return -1;
    if (*(volatile signed char *)LED_MODE == mode) return 0;
    *(volatile signed char *)LED_MODE = (signed char)mode;
    write_int_config(mode, "SYSSET", "ATMOSPHERELEDMODE");
    reset_atmosphereled_rgb();
    return 0;
}

/* Follow Screen: stock's byte ledfollowscreen_flag (LED_FOLLOW) and [SYSSET] LEDFOLLOWSCREEN. Stock's handler 0x4a1940 stores the byte xor 1 (as 0 or 1) in the delay slot of the save, the byte first, and calls
 * nothing else. The new state. */
int disp_follow(void) { return *(volatile signed char *)LED_FOLLOW == 1; }

int disp_follow_toggle(void) {
    int next = (*(volatile signed char *)LED_FOLLOW ^ 1) != 0;
    *(volatile signed char *)LED_FOLLOW = (signed char)next;
    write_int_config(next, "SYSSET", "LEDFOLLOWSCREEN");
    return next;
}

/* The brightness card. Its slider has the name of stock's (slider_brightness), so stock's own two handlers are bound to it with the window as their context, as stock's page binds them (tools/pod.py
 * LOCKSCREEN_PINS): the drag (the word lightness, the pending flag) and the release (the backlight, [SYSSET] LIGHTNESS) are stock's code. disp_refresh is stock's refresh: the slider at the word lightness
 * (called when the page opens and each time it is back in front: the pull-down's slider changes the same word). A page without the slider or the hidden label_brightness leaves both alone. */
void disp_refresh(void *win) {
    if (win && widget_lookup(win, "slider_brightness", 1) && widget_lookup(win, "label_brightness", 1))
        brightness_refresh(win);
}

void disp_opened(void *win) {
    void *s = win ? widget_lookup(win, "slider_brightness", 1) : (void *)0;
    if (!s || !widget_lookup(win, "label_brightness", 1)) return;
    brightness_refresh(win); /* before the handlers are bound: setting the slider is not a change to save */
    widget_on(s, EVT_VALUE_CHANGING, (void *)BRIGHT_CHANGING, win);
    widget_on(s, EVT_VALUE_CHANGED, (void *)BRIGHT_CHANGED, win);
}

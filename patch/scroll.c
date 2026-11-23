/* M1+ Music list gestures: a swipe never plays a song, and a touch on a coasting list stops it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Every stock list is list_view > scroll_view > list_item rows. The stock code (docs/modules/gestures.md)
 * has two holes. (1) A row cancels its press (and the scroll_view cancels it for every child) only when a MOVE crosses
 * the 10 px threshold. The scroll_view sees the pointer-up after its rows: a release far from the press with no MOVE
 * past the threshold in between (sparse touch samples in a quick flick) reaches the row as a click while the list
 * flings. (2) A touch on a list that is still animating its fling presses and clicks the row under the finger, and the
 * drag that follows cannot move the list until the animation ends.
 *
 * One hook, and no code of the stock app is overwritten: the on_event_before_children slot of g_scroll_view_vtable
 * (0x97a330, zero in stock), which widget_on_event_before_children (0x666c34) calls for every pointer event of a
 * scroll_view before the event goes down to its children. It runs only for touches inside a scroll_view; never at boot,
 * in paint or in the main loop. A MOVE costs three compares. No allocation, no syscall, no log: the kill switch
 * (/mnt/mmc/m1plus-off, or the flash one) is read once, at the first DOWN or UP, and the hook is a no-op for a session
 * that starts with it.
 *
 *  DOWN on a scroll_view whose scroll animator is running: the animator is destroyed and the stock end-of-animation
 *  handler runs (wa cleared, the end events), then the scroll_view takes the press itself (widget_dispatch: grab,
 *  velocity, press position) and the event is stopped, so the rows below never see this DOWN. The rest of the gesture
 *  is stock: a drag scrolls from here, a plain tap does nothing (the row was never pressed, so its UP is no click).
 *  UP after the finger moved the threshold from where it came down, without the stock MOVE path having noticed
 *  (dragged is still 0): the same EVT_POINTER_DOWN_ABORT the stock MOVE path sends, before the rows see the UP, so the
 *  row that was pressed drops its press and the release is no click.
 * The threshold is the stock one and the stock axes: slidable ones only, so a horizontal drag inside a vertical list (a
 * slider in a settings row) is left alone; a scroll_view that snaps to pages is left to stock.
 */
#include "offsets.inc"
#include "stock.h"
#include "scroll.h"
#include "home.h"

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static int sc_state __attribute__((section(".scratch"))); /* 0 not read yet, 1 on, 2 kill switch */

/* The list a tile or row is lifted in (a Home pin, patch/pins.c; a playlist row in Edit mode, patch/songs.c), for the hook below: yslidable off at the lift does not last, a layout turns it back on each
 * time (scroll_view_set_yslidable(sv, 1), 0x60b1e4), so the hook turns it off again before every pointer event of the lift reaches the list. */
void *m1_lift_sv __attribute__((section(".scratch")));

static int sc_off(void) {
    if (!sc_state) sc_state = home_off() ? 2 : 1;
    return sc_state != 1;
}

__attribute__((noinline)) static int sc_down(void *w,
                                             void *e) { /* noinline: a MOVE (the common event) stays frameless */
    void *wa = P(w, SC_WA);
    if (!wa || B(w, SC_SNAP) || sc_off()) return RET_OK;
    if (I(wa, SC_AN_STATE) != SC_AN_RUNNING || P(wa, SC_AN_WIDGET) != w)
        return RET_OK; /* not a live animator of this list: stock */
    widget_animator_destroy(wa);
    stock_scroll_done(w, (void *)0);
    widget_dispatch(w, e);
    return SC_RET_STOP;
}

__attribute__((noinline)) static int sc_up(void *w, void *e) {
    unsigned ev[12];
    int dx, dy, d, i;
    if (!B(w, SC_PRESSED) || B(w, SC_DRAGGED) || B(w, SC_SNAP)) return RET_OK;
    dx = I(e, PE_X) - I(w, SC_DOWN_X);
    dy = I(e, PE_Y) - I(w, SC_DOWN_Y);
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    d = B(w, SC_YSLIDE) ? dy : 0;
    if (B(w, SC_XSLIDE) && dx > d) d = dx;
    if (d < SC_DRAG_PX || sc_off()) return RET_OK;
    for (i = 0; i < 12; i++)
        ev[i] = ((unsigned *)e)[i]; /* the stock MOVE path's copy of the pointer event (0x30 bytes) */
    ev[0] = EVT_POINTER_ABORT;
    widget_dispatch_event_to_target_recursive(w, ev);
    return RET_OK;
}

/* g_scroll_view_vtable.on_event_before_children (tools/pod.py patch_scroll): widget_on_event_before_children passes the
 * widget and the event, both non-null. Anything but a pointer DOWN or UP is stock. */
int m1plus_scroll_event(void *w, void *e) {
    unsigned type = *(unsigned *)e & 0xffff;
    if (w == m1_lift_sv)
        B(w, SC_YSLIDE) =
            0; /* a Home pin or a playlist row is lifted (patch/pins.c, patch/songs.c): the list does not slide with its drag or fling at its drop, whatever a layout set since the hold; no late-drag abort either */
    if (type == EVT_POINTER_DOWN) return sc_down(w, e);
    if (type == EVT_POINTER_UP) return sc_up(w, e);
    return RET_OK;
}

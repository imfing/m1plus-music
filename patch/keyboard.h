/* M1+ Music's own on-screen QWERTY keyboard (patch/keyboard.c, docs/modules/keyboard.md): the API, and the geometry that tools/pod_keyboard.py repeats.
 * test/pod/keyboard.py parses the #defines in this file, so the asset, the payload and the preview cannot drift apart.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* Open the keyboard page over whatever is in front: a navbar (Back = cancel), a search field with the placeholder, and the pad.
 *   title        the navbar's title, UTF-8 and already translated; NULL keeps the page's own ("Keyboard")
 *   placeholder  the grey text of the empty field (UTF-8, already translated); NULL or "" for none
 *   initial      the field's text to start with (UTF-8, at most KB_MAX bytes, cut on a character boundary); NULL for none
 *   on_done      Search with a non-empty text: called with the text (spaces at both ends removed) right after the page was told to close
 *   on_cancel    Back (the navbar's or the hardware key) without Search; NULL for none
 *   flags        KB_DONE: the action key (on_done) reads "Done" instead of "Search"
 *                KB_LONG: the text may be KB_MAX_LONG bytes, not KB_MAX
 *                KB_PASSWORD: a password field (KB_PASS_MAX bytes, shown as dots, as keyboard_attach's)
 * Returns 0 once the page is up, -1 when it could not open (another keyboard is still there: one at a time, also from inside a callback, since the page is
 * destroyed only after the callback ran; or the asset is not ours). The callbacks run on the UI thread, from the event that closed the page (on_cancel for the hardware
 * Back key from the page's destroy event); the page is gone or closing, so a callback must not use it. */
typedef void (*kb_done_fn)(const char *text);
typedef void (*kb_cancel_fn)(void);
#define KB_DONE 2 /* the action key reads "Done" (a name, not a search) */
#define KB_LONG 4 /* the text may be KB_MAX_LONG bytes, not KB_MAX (the podcast search field takes a feed address) */
#define KB_LITERAL \
    16 /* keyboard_attach: spaces are typed as pressed (leading, doubled, trailing; an SSID has them); everything else as a plain field */
#define KB_PASSWORD \
    8 /* keyboard_attach: a password field: English layer only (no language key, no pinyin whatever the setting), a lowercase page that no empty field turns to capitals, spaces anywhere
                       * (leading, doubled), the text as typed (untrimmed), shown as one dot a character until keyboard_set_mask(0), no clear button,
                       * up to KB_PASS_MAX bytes */
typedef void (*kb_change_fn)(const char *text);
typedef void (*kb_go_fn)(void);
/* The same pad embedded in another page (patch/search.c): the page's window holds the widgets kb_pad, kb_strip, kb_stem, kb_pop and a field (kb_text, kb_hint, kb_caret, kb_clear) of the
 * names of the keyboard page's; on_change gets the field's text whenever it may have changed, on_go the action key. flags: KB_PASSWORD (0 for none). -1 when a keyboard exists already or the
 * widgets are not there. */
int keyboard_attach(void *win, const char *placeholder, int text_x, int text_w, int caret_y, unsigned flags,
                    kb_change_fn on_change, kb_go_fn on_go);
int keyboard_refocus(
    const char *placeholder, int text_w, unsigned flags, const char *text, kb_change_fn on_change,
    kb_go_fn
        on_go); /* another field of the page takes the pad: new flags, text room, placeholder, text and callbacks (the widgets are the page's to move); on_change gets the text; -1 without a keyboard */
void keyboard_set_mask(
    int on); /* the field shows one dot per character (on) or the text; the caret follows what is shown */
void keyboard_set_go(
    const char *key,
    int enabled); /* the action key reads the translated string `key` (NULL keeps its label) and is dimmed and inert while not enabled (on_go does not fire) */
void keyboard_set_max(
    unsigned
        bytes); /* after keyboard_attach: the embedded field takes this many bytes instead of KB_MAX (at most KB_MAX_LONG) */
void keyboard_go(
    void); /* the action key as if pressed (a page's own Search button): what is pending is committed, then on_go; nothing while the key is dimmed */
void keyboard_detach(void); /* the page's destroy event */
void keyboard_show(int on); /* show or hide the embedded pad (hidden: no touch, no caret) */
int keyboard_shown(void);
int pinyin_hold(void); /* the Pinyin engine open for a page's life (0 ready); the search page's initials index */
void pinyin_release(void); /* after keyboard_detach: closes what pinyin_hold opened */
const char *keyboard_text(void); /* the field's committed text (UTF-8) */
void keyboard_set_text(const char *s); /* the field's text replaced (a recent search tapped); on_change gets it */
int keyboard_busy(
    void); /* a keyboard page is up or not destroyed yet (keyboard_open would return -1 for that reason, not for a failure to open) */
int keyboard_open(const char *title, const char *placeholder, const char *initial, kb_done_fn on_done,
                  kb_cancel_fn on_cancel, unsigned flags);

#define KB_W 320
#define KB_H 180 /* the pad's height; its top is at 450 - KB_H in the window */
#define KB_WIN_H 450
#define KB_PAD 6 /* the padding above and under the four rows */
#define KB_PITCH 44 /* the rows' pitch */
#define KB_KH 36 /* every key's height */
#define KB_KW 29 /* a char key's width: ten across with KB_GAP between */
#define KB_GAP 3
#define KB_NUM_KW 41 /* the third row's keys on the 123 and #+= pages */
#define KB_FN_W 40 /* shift, #+= and delete */
#define KB_MODE_W 74 /* 123 / ABC and Search */
#define KB_EDGE 2 /* the left margin of a full row (the right one is 1) */
#define KB_LANG_W 40 /* the language key of row four (more than one keyboard on); space gives it room */
#define KB_KEYS 26 /* char key widgets */
#define KB_MAX 63 /* bytes of text */
#define KB_MAX_LONG 255 /* ... with KB_LONG (a feed address) */
#define KB_PASS_MAX 127 /* ... in a KB_PASSWORD field (a WPA3 password; a WPA2 one is 63 bytes or 64 hex digits) */
#define KB_POP_W 46 /* the key pop-up: the balloon */
#define KB_POP_H 50
#define KB_POP_GAP 10 /* above the key */
#define KB_STEM_UP 12 /* the stem rises to this far under the balloon's bottom edge */
#define KB_TEXT_X 30 /* the field's text and caret start (field coordinates) */
#define KB_TEXT_W 228 /* the room for the text */
#define KB_CARET_Y 7
#define KB_HOLD_MS 80 /* delete repeats on this tick ... */
#define KB_HOLD_TICKS 6 /* ... after this many ticks of holding */

/* The Chinese (Pinyin) layer: the candidate strip above the pad and the engine it asks (docs/modules/keyboard.md) */
#define KB_STRIP_Y 234 /* the strip's top in the window (the pad's top minus its height) */
#define KB_STRIP_H 36
#define KB_POOL 12 /* candidate item widgets; at most this many items are on screen */
#define KB_PY_X 8 /* the pinyin label: its left margin, the room it may take */
#define KB_PY_MAX 120
#define KB_CAND_PAD 12 /* the padding either side of a candidate's text, the narrowest and the widest item */
#define KB_CAND_MIN 36
#define KB_CAND_MAXW 230
#define KB_CHL_Y 4 /* the pressed item's highlight */
#define KB_CHL_H 28
#define KB_SEP_Y 8 /* the divider between the pinyin and the candidates */
#define KB_SEP_H 20
#define KB_DRAG 6 /* px a finger moves before a press on the strip is a scroll */
#define KB_MAX_CAND 100 /* candidates taken from the engine for one input */
#define KB_CHUNK 12 /* ... this many at a time, more as the strip scrolls towards its end */
#define KB_POOL_BYTES 4096 /* the UTF-8 of the candidates read */
#define KB_PRED 10 /* predictions asked for after a commit */
#define KB_RAW_MAX 39 /* letters of pinyin the engine takes */
#define KB_CAND_U16 48 /* char16 units given to im_get_candidate, the terminator included */
#define PINYIN_DICT "/release/assets/default/raw/data/gpinyin.dat" /* stock ships it; nothing else loads it */
#define PINYIN_USER "/proc/m1plus/pinyin-user.dat" /* neither readable nor creatable: no learning */

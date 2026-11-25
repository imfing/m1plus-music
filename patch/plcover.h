/* Generated playlist covers (patch/plcover.c, docs/modules/plcover.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* The styles; the numbers are stored, so they never change. Albums is the grid's 2x2 mosaic: plc_art never draws it. */
enum { PLC_STYLE_ALBUMS, PLC_STYLE_SOLID, PLC_STYLE_MESH, PLC_STYLE_SUNBURST, PLC_STYLE_STRIPES, PLC_STYLE_BAND };
#define PLC_GREY 0xff787878u /* the tone of a playlist without a cover tone */

/* Draws style 1..5 into px, side x side opaque RGBA words (RGB565 values expanded; red lowest), side 1..PLC_MAX, from the first tone (m1_tone words, 0xAABBGGRR)
 * or, for Mesh, all of nt (at most 4); nt 0 is a grey. seed shapes Mesh only. Another style or side draws nothing. The corners are the caller's. */
void plc_art(unsigned *px, int side, int style, const unsigned *tones, int nt, unsigned seed);

/* ---------------------------------------------------------------------------
 * The stored choice: a local playlist's cover on the card (patch/plcover.c, docs/modules/plcover.md). A playlist is its stock id and its name (the ids are reused: another name is another playlist).
 */
#define PLC_FILE "/mnt/mmc/.m1plus/playlist-covers"
#define PLC_FLAG_NAME 1u /* flags bit 0: the name is drawn on the cover (grid_plc_name draws it) */
#define PLC_NAME_MAX 64 /* bytes of a name kept, the NUL included */
#define PLC_FILE_MAX 12288

typedef struct {
    int style; /* PLC_STYLE_SOLID..BAND */
    unsigned flags; /* PLC_FLAG_* (other bits are kept as read) */
    unsigned seed; /* Mesh's seed, made once when the cover is first set */
    int nt; /* 0..3 */
    unsigned tones[3]; /* m1_tone words (0xffBBGGRR) frozen when the style was chosen */
    unsigned sig; /* a hash of the above (never 0): changes when the picture would; a rename keeps it */
} plc_t;

/* 1 and *out (may be NULL) when the playlist has a cover of a style other than Albums, 0 when not (no card, no file, a playlist with the same id and another name). */
int plc_get(int id, const char *name, plc_t *out);
/* Stores the cover: style 1..5 with its flags and the first nt (0..3) tones; the seed is made from the id and the name at the first set of an entry and kept after. Style 0 (Albums) removes it. A stale entry of the same id
 * and another name is replaced. 0 when done; -1 and nothing changed for a bad argument, no card, a full file or a write that failed. */
int plc_set(int id, const char *name, int style, unsigned flags, const unsigned *tones, int nt);
/* The seed a Mesh cover of this playlist has: the stored one, else the one plc_set would make (the Cover page draws what a tap would store). */
unsigned plc_seed(int id, const char *name);
/* The playlist was renamed: its entry follows. 1 when there was one and the file was written. */
int plc_rename(int id, const char *old, const char *name);
/* The playlist was deleted: its entry goes. 1 when there was one and the file was written. */
int plc_forget(int id, const char *name);

/* ---------------------------------------------------------------------------
 * The Cover page (patch/plcpage.c): a stock playlist's cover chosen from the Songs page's Edit mode.
 */
/* Opens the page for the playlist id / name whose albums' cover keys are key[0..nk) (nk 0..4, grid_mosaic_keys). 0 when it opened, -1 when not. */
int plcpage_open(int id, const char *name, const unsigned *key, int nk);
void plcpage_opened(
    void *win,
    int page); /* the page's window opened (patch/m1plus.c open_page; page: its number, for pod_page_refresh) */
int plcpage_style(void); /* the chosen style (0 Albums) */
int plcpage_name_on(void); /* Name on Cover: the switch's state (off for Albums) */
int plcpage_name_toggle(void); /* the switch: the new state, -1 when the card did not take it (a toast shows) */

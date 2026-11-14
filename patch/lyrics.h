/* The Now Playing lyrics page (patch/lyrics.c, docs/modules/lyrics.md). Called from patch/nowplaying.c's page timer; no hook of its own.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* The page is built (win: the playing window). Finds the asset's np_lyrics box and the stock lyric list, makes the label pool and hides the stock list.
 * Anything missing leaves the stock list as it is. */
void ly_start(void *win);
/* The page's 500 ms tick: new lyrics, the current line, the layout. */
void ly_tick(void);
/* The page is over (or replaced): the animation timer goes, the state is cleared. */
void ly_stop(void);
/* Another view drives the engine (the idle page, patch/idlelyrics.c; docs/modules/idlelyrics.md): box, a scroll_view of its own h px high in window win, gets the pool and the touch
 * listeners; the lines are still Now Playing's stock rows. 0, or -1 with nothing changed (Now Playing has no engine, it is already taken, a label is refused). ly_release gives the engine back
 * to Now Playing (idempotent; ly_refresh does it as well when Now Playing is in front); ly_target is the box the engine drives now (0 stopped); ly_lines the rows it reads. */
int ly_retarget(void *win, void *box, int h);
void ly_release(void);
void *ly_target(void);
int ly_lines(void);
int ly_has_rows(
    void); /* 1 when Now Playing's scroll_lrc holds at least one row right now (read live from the widget; 0 with the engine stopped) */
/* The page is in front again: a text size changed in Settings is taken (the lines are laid out again). */
void ly_refresh(void);
/* Settings > Now Playing > Lyrics Text Size (file LYRSIZE_FILE): the saved size, 0 Small (22 px), 1 Medium (26), 2 Large (30, the default); ly_size_set saves one atomically (the size or -1). */
int ly_size(void);
int ly_size_set(int size);

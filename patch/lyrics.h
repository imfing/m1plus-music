/* The Now Playing lyrics page (patch/lyrics.c, docs/modules/lyrics.md). Called from patch/nowplaying.c's page timer; no hook of its own.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* The page is built (win: the playing window). Finds the asset's np_lyrics box and the stock lyric list, makes the label pool and hides the stock list.
 * Anything missing leaves the stock list as it is. */
void ly_start(void *win);
/* Whether every code point of the UTF-8 text is in the bold face lyrics.ttf (Latin, Greek, Cyrillic); any other text is drawn in the default font. */
int ly_latin(const char *s);
/* Loads the lyrics face if needed and installs the coverage gamma on it (idempotent). */
void ly_font(void);
/* A title label of the Vinyl and VU pages: sets its font to the bold face (lyrics) when s is all in it, else the default font, and makes sure the bold face is loaded with the gamma. Call before setting the text. */
void ly_title_face(void *w, const char *s);
/* The page's 500 ms tick: new lyrics, the current line, the layout. */
void ly_tick(void);
/* The page is over (or replaced): the animation timer goes, the state is cleared. */
void ly_stop(void);
/* Spoken audio plays: Now Playing shows its notes page in the lyrics page's place. With on = 1 the next ly_tick hides the lyrics box, the stock list and message and the lyrics scrim and does nothing else; with 0 it shows them
 * again (the message as it was). Touch only Now Playing's own widgets: nothing while the idle page has the engine (ly_retarget). */
void ly_standdown(int on);
/* The playing track's lyrics were reloaded and stock's rows will be rebuilt (it clears force_refreshflag when it has): the next tick after that reads them as new lyrics even when
 * their handles, count and times are the same (the row signature has no text). No-op with the engine stopped; a pending mark survives ly_release and ly_retarget. */
void ly_reload(void);
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

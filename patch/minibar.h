/* The mini player bar's pieces that the lock screen's mini layout shares (patch/lockscreen.c): the rounded cover and the backdrop blur. patch/minibar.c owns them;
 * the Home bar and the lock bar each keep their own state (a mb_art_t, a mb_blur_t) and call the same code. docs/modules/minibar.md, docs/modules/lockscreen.md. */
#ifndef MINIBAR_H
#define MINIBAR_H
#include "offsets.inc"

/* The cover: an MB_ART px RGBA bitmap whose four MB_ART_R px corners are rounded in its own alpha. */
typedef struct {
    void *bmp; /* NULL until the first picture (or when it could not be made) */
    unsigned char corner[MB_ART_R * MB_ART_R]; /* the top left corner's coverage outside the arc, 0..255 */
    unsigned fkey; /* the hash of the /tmp cover file the picture was made from, 0 when it was not */
    int settle; /* ticks left that read the /tmp file again */
} mb_art_t;

unsigned mb_track_key(void *t); /* a hash of the track's path, title, file name and cue start, never 0 */
unsigned *mb_art_begin(mb_art_t *a); /* the bitmap's locked pixels (the bitmap made on first use), NULL: no cover */
void mb_art_end(mb_art_t *a, unsigned *px); /* round the corners and unlock */
int mb_art_cover(mb_art_t *a, void *win, void *t,
                 int first); /* the playing track's cover (album cache, /tmp file, disc); 1 when the bitmap changed */
int mb_art_settle(mb_art_t *a, void *win,
                  void *t); /* one tick of the /tmp file watch after a new track; 1 when the cover was redone */
void mb_art_paint(mb_art_t *a,
                  void *canvas); /* the resident cover at the card's MB_ART_X / MB_ART_Y (the card's EVT_AFTER_PAINT) */
void mb_art_free(mb_art_t *a);

/* The backdrop blur of the pill under a canvas translated to the card (tools/pod_blur.py is the model). */
typedef struct {
    unsigned *pl; /* the half-resolution plane, MB_HW x MB_HH words (heap) */
    int on; /* registered and still allowed (a structural mismatch clears it) */
    int fix; /* a frame was partial: invalidate the whole pill at the next chance */
    unsigned char x0[MB_HH]; /* per half row: the first block inside the pill */
} mb_blur_t;

int mb_blur_alloc(mb_blur_t *b); /* 0: off (the SD file m1plus-noblur, or no memory) */
void mb_blur_enable(mb_blur_t *b); /* after every handler is registered */
void mb_blur_paint(mb_blur_t *b, void *canvas); /* the card's EVT_BEFORE_PAINT */
void mb_blur_free(mb_blur_t *b);
#endif

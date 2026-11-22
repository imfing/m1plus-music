/* M1+ Music Mono Audio and Crossfeed: the player's stereo stage and the record that sets it (docs/modules/stereo.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The crossfeed is Boris Mikhaylov's bs2b (libbs2b 3.1.0, Copyright (c) 2005 Boris Mikhaylov, MIT licence): its level
 * arithmetic (the low-pass and the high-boost one-pole filters and their gains) and its three settings are his, rewritten
 * for float blocks with a ramp. Mono is (L + R) / 2.
 *
 * Built into hciplayer's payload (PEQ_PLAYER: player.h, which tools/mod_player.py writes); demo (stock.h) only includes
 * the record's path, magic and layout, to write it.
 */
#pragma once

#ifdef PEQ_PLAYER
#include "player.h"
#else
#include "stock.h"
#endif

/* The record in the settings folder (the playback-<thing> files): demo writes it whole (tmp, fsync, rename) with the
 * state that is in effect for the current output, the player reads it at each REINIT and each channel-0 gain command.
 * A missing, short, long or invalid record is both off. */
#define STEREO_FILE "/mnt/data/m1plus/playback-stereo"
#define STEREO_MAGIC "M1STR01" /* 8 bytes with its NUL */
enum { STEREO_OFF, STEREO_LOW, STEREO_MEDIUM, STEREO_HIGH, STEREO_LEVELS };
typedef struct {
    char magic[8];
    int mono; /* 0 or 1: Mono Audio */
    int crossfeed; /* STEREO_OFF .. STEREO_HIGH: the crossfeed in effect (demo: the setting on headphones and Bluetooth, off on Line Out and USB DAC) */
} stereo_record;
_Static_assert(sizeof(stereo_record) == 16, "record layout");

typedef struct {
    double a0lo, b1lo, a0hi, a1hi, b1hi, gain;
} sx_coef;
typedef struct {
    double lo[2], hi[2], asis[2];
} sx_mem;
typedef struct {
    int level; /* STEREO_LOW .., 0: free */
    double w; /* its share of the output, 0..1 */
    sx_coef c;
    sx_mem m;
} sx_slot;
typedef struct {
    int rate, active; /* active: stereo */
    double step; /* the weights' change a frame: 20 ms */
    int mono_to, level_to; /* what the record asks */
    double mono_w;
    sx_slot slot[2]; /* the crossfeed in effect and the one arriving (a level change crosses over) */
} stereo_dsp;
/* What an instance leaves for the next one across a gapless join: the weights where they are (a ramp goes on) and the
 * crossfeed's filters. */
typedef struct {
    int rate; /* 0: nothing (the track was not stereo) */
    double mono_w;
    sx_slot slot[2];
} stereo_carry;

int stereo_load(stereo_record *r); /* 1: a valid record; 0: none, r is both off */
int stereo_on(const stereo_record *r); /* Mono Audio or Crossfeed on */
/* A new instance. ramp 0: what the record asks plays from the first frame (a track's start); 1: it ramps in from the
 * untouched signal in 20 ms (the instance replaces a pass-through one while the music plays). */
void stereo_reset(stereo_dsp *s, int rate, int channels, const stereo_record *r, int ramp);
void stereo_update(stereo_dsp *s, const stereo_record *r); /* a change while playing: 20 ms ramps */
void stereo_pre(stereo_dsp *s, float *audio, unsigned frames); /* Mono Audio: before the EQ */
void stereo_post(stereo_dsp *s, float *audio, unsigned frames); /* Crossfeed: after the EQ */
int stereo_carry_out(const stereo_dsp *s, stereo_carry *c); /* 0: not finite, carry nothing */
void stereo_carry_in(stereo_dsp *s, const stereo_carry *c);
int stereo_carry_live(const stereo_carry *c, int rate); /* it would still be heard at this rate: a weight above 0 */

#ifndef PEQ_PLAYER
/* demo's side (patch/stereoset.c): the user's two settings and the effective record. The settings are ours to store (the player never reads them): the level the user chose is kept apart from the
 * record, because the record's level is 0 on Line Out and a USB DAC. */
#define STEREO_MONO_FILE "/mnt/data/m1plus/playback-mono" /* "1" Mono Audio on; missing or anything else off */
#define STEREO_XFEED_FILE \
    "/mnt/data/m1plus/playback-crossfeed" /* "0" .. "3" (STEREO_OFF .. STEREO_HIGH); missing or anything else off */

int stereo_mono(void); /* Mono Audio as chosen: 1 or 0 */
int stereo_mono_toggle(void); /* the new state, or -1 when it could not be saved (nothing changes) */
int stereo_crossfeed(void); /* the level as chosen: STEREO_OFF .. STEREO_HIGH (not the effective one) */
int stereo_crossfeed_set(int level); /* the level, or -1 when it is not one or could not be saved (nothing changes) */
int stereo_sync(
    int output,
    int notify); /* peqout_sync's call: the effective record for `output` (PO_*) is on disk and the player has reread it; 1 when the record was written */
#endif

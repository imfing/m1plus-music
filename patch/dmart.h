/* The Daily Mix art's shared pieces (patch/dailymix.c, tools/pod_dailymix.py is the model): the tone preparation, the blob field and the 4 x 4 dither
 * the generated playlist covers' Mesh style (patch/plcover.c) draws with too.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

typedef struct {
    int cx, cy;
    unsigned r2;
    int t[3];
} blob_t;

void dm_prep(unsigned tone, int *out); /* a 0xAABBGGRR tone made card-ready: out[0..2] = r, g, b */
void dm_blobs_wh(const unsigned *tone, unsigned n, unsigned aseed, unsigned w, unsigned h, int *base,
                 blob_t *bl); /* the base colour and the blobs of n (at most 4) tones on a w x h field */
void dm_field_wh(unsigned char *o, unsigned y, unsigned w, const int *base, const blob_t *bls,
                 unsigned nbl); /* row y of the field, w pixels of 3 bytes */
unsigned dm_quant(int c, unsigned t, int step, unsigned bits,
                  unsigned *e); /* a channel through the dither value t: the quantised, e the expanded */
extern const unsigned char dm_bayer[4][4];

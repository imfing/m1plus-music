/* Podcast cover art: shrink a downloaded JPEG once to the size the Podcasts pages draw (patch/pccover.c; docs/modules/podcasts.md "Cover art").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define PV_SIZE \
    192 /* the longer side of the saved cover: twice the largest the pages draw (the Show header's 96 px cover), so the grid's area average has pixels to average */
#define PV_QUALITY 85 /* JPEG quality of the saved cover (about 10 to 20 kB) */
#define PV_BASELINE_MAX_PX \
    16000000u /* a baseline JPEG above this many pixels is refused (libjpeg's time and the 6 MiB download cap make it rare); a progressive one is held to PC_COVER_MAX_PX: libjpeg keeps all its coefficients */

#define CV_QUALITY 90 /* JPEG quality of an album cover (stock's encoder 0x5de554: jpeg_set_quality(90), pinned) */
#define PV_COVER_PROGRESSIVE_PX \
    4194304u /* a progressive album cover above this many pixels (or 8192 on a side) is refused (PV_REFUSED: libjpeg keeps all its coefficients, about 3 bytes a pixel, even at 1/8 scale) */
#define PV_REFUSED \
    (-2) /* pv_cover's answer for such a picture: no art, and stock is not asked either (it would decode it the same way) */

/* An album cover, the cache's extraction (patch/covercache.c): the JPEG or PNG at src into dst fitted inside size x size as stock's resize does (the same output size, cc_stock_fit), JPEG quality
 * CV_QUALITY, by the exact area average. Returns 1; -1 when stock keeps the picture as it is (smaller than size) or it is an interlaced PNG; PV_REFUSED for a progressive JPEG over PV_COVER_PROGRESSIVE_PX or 8192 on a side; 0 on any other failure (not a picture this
 * takes, too large, an error): nothing is left at dst, and the caller falls back to stock's own extraction. Worker thread only. */
int pv_cover(const char *src, const char *dst, unsigned size);

/* The JPEG at src into dst: fitted inside PV_SIZE x PV_SIZE, aspect kept, never upscaled, written as a baseline JPEG. libjpeg's own 1/2, 1/4 or 1/8 scaling does the first reduction while it
 * decodes, one row at a time, and an area average the rest, so a 3000 x 3000 picture needs a few hundred kB, not the 27 MB its bitmap would. Returns 1; on any failure (not a baseline or
 * progressive JPEG, too large, a decode error, a write error) 0, and dst is not left behind. For the refresh worker thread: demo's libjpeg and libc only, no stock function, no widget. */
int pv_shrink(const char *src, const char *dst);
/* The same for the PNG at src, through the streaming decoder of patch/pcpng.c: any 8 / 16 bit or palette PNG up to PP_MAX_SIDE and PP_MAX_PX, transparency over white. Returns 1; -1 for an interlaced
 * PNG (not decodable in one pass over its rows: the caller may keep a small one as it is); 0 for any other failure (nothing left at dst). */
int pv_shrink_png(const char *src, const char *dst);

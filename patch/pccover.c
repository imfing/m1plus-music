/* Cover art shrunk once, in a worker thread: the podcast covers (docs/modules/podcasts.md "Cover art") and the album covers of the cache (docs/modules/coverflow.md "Cover resampling").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Podcast art is often 3000 x 3000 (1 MB or more); stock's loader holds the whole bitmap (27 MB and more), so the worker shrinks it itself, with demo's own libjpeg 7 for the output (and
 * for a JPEG input: the library stock's picture decoder 0x5dd5ec and encoder 0x5de554 call; the structures are written by offset, every offset and the two sizes pinned by tools/pod.py
 * JPEG_PINS against those stock functions). A JPEG input is decoded at scale 1/d (d = 1, 2, 4 or 8: libjpeg's DCT scaling, the cheap way down) one row at a time; a PNG goes through the
 * streaming decoder of patch/pcpng.c (demo has no png_read_row and no zlib). Either way every row goes into the exact area average of patch/covercache.c (ar_push) to the target width
 * and height, which feeds the encoder row by row. Memory: libjpeg's row buffers (or the PNG state, patch/pcpng.c) and the 14 kB of the average, whatever the picture's size.
 * The album covers use the same path (pv_cover) in place of stock's toolsGetAlbumCover / toolsGetExternCover resize, which decodes the whole picture (up to 1024 x 1024, else at
 * DCT scale 1/2 to 1/8) and maps its pixels by a four-tap bilinear that aliases at 6 : 1: the output size is stock's exactly (cc_stock_fit), only the sampling differs.
 * Errors: libjpeg's error_exit never returns, and its default exits the process; the exit installed is stock's own (0x5dbfe0: print the message, longjmp to the jump buffer that follows
 * the 0x88 byte error manager), with our _setjmp before the first libjpeg call. Everything that must be freed afterwards is volatile.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "podcasts.h"
#include "covercache.h"
#include "pccover.h"
#include "pcpng.h"

extern int pod_lib__setjmp(void *) __attribute__((returns_twice));

#define PV_ERR_EXIT 0x5dbfe0u /* stock's error_exit (JPEG_PINS) */
#define PV_VERSION 70 /* JPEG_LIB_VERSION of demo's libjpeg */
#define PV_DEC_SIZE 0x1d8 /* sizeof (struct jpeg_decompress_struct) */
#define PV_ENC_SIZE 0x1a8 /* sizeof (struct jpeg_compress_struct) */

/* Field offsets of the two structures (libjpeg 7, o32) */
#define JF_WIDTH 0x1c /* image_width (both) */
#define JF_HEIGHT 0x20 /* image_height (both) */
#define JF_COMPONENTS 0x24 /* num_components (decompress), input_components (compress) */
#define JF_COLORSPACE 0x28 /* in_color_space (compress); JCS_RGB = 2 */
#define JF_SCALE_NUM 0x30 /* decompress */
#define JF_SCALE_DEN 0x34
#define JF_OUT_WIDTH 0x70 /* output_width, valid after jpeg_start_decompress */
#define JF_OUT_HEIGHT 0x74

typedef struct {
    unsigned char pub[0x88]; /* struct jpeg_error_mgr: error_exit is its first word */
    unsigned long long jb[32]; /* the jmp_buf stock's error_exit longjmps to */
} pv_err_t;

/* The output side: the area average and the encoder, shared by both inputs. */
typedef struct {
    pv_err_t err;
    unsigned char enc[PV_ENC_SIZE] __attribute__((aligned(8)));
    void *volatile fout;
    volatile int enc_up, made, werr;
    ar_t ar;
} pv_out_t;

static unsigned *pv_w(void *c, unsigned off) { return (unsigned *)((unsigned char *)c + off); }

static void pv_out_init(pv_out_t *o) {
    jpeg_std_error(&o->err);
    *(void **)o->err.pub = (void *)PV_ERR_EXIT;
    *(void **)o->enc = &o->err;
    o->fout = (void *)0, o->enc_up = o->made = o->werr = 0;
}

/* The podcast size of an ow x oh source: fitted inside PV_SIZE, aspect kept, never upscaled. */
static void pv_pod_fit(unsigned ow, unsigned oh, unsigned *tw, unsigned *th) {
    unsigned m = ow > oh ? ow : oh;
    *tw = ow, *th = oh;
    if (m > PV_SIZE) *tw = ow * PV_SIZE / m, *th = oh * PV_SIZE / m;
    if (!*tw) *tw = 1;
    if (!*th) *th = 1;
}

/* The encoder for an ow x oh source into dst at tw x th. 1, or 0 when dst cannot be opened or the sizes are out of the average's range. */
static int pv_out_begin(pv_out_t *o, unsigned ow, unsigned oh, unsigned tw, unsigned th, int quality, const char *dst) {
    if (!ar_init(&o->ar, ow, oh, tw, th)) return 0;
    jpeg_CreateCompress(o->enc, PV_VERSION, PV_ENC_SIZE);
    o->enc_up = 1;
    o->fout = fopen(dst, "wb");
    if (!o->fout) return 0;
    o->made = 1;
    jpeg_stdio_dest(o->enc, o->fout);
    *pv_w(o->enc, JF_WIDTH) = tw, *pv_w(o->enc, JF_HEIGHT) = th, *pv_w(o->enc, JF_COMPONENTS) = 3,
                  *pv_w(o->enc, JF_COLORSPACE) = 2;
    jpeg_set_defaults(o->enc);
    jpeg_set_quality(o->enc, quality, 1);
    jpeg_start_compress(o->enc, 1);
    return 1;
}

/* A finished target row to the encoder. */
static void pv_emit(void *user, const unsigned char *rgb) {
    pv_out_t *o = user;
    unsigned char *line[1];
    line[0] = (unsigned char *)rgb;
    if (!o->werr && jpeg_write_scanlines(o->enc, line, 1) != 1) o->werr = 1;
}

/* The next source row (ow pixels of n = 1 or 3 bytes) into the average. 0 on failure. */
static int pv_out_row(pv_out_t *o, const unsigned char *row, unsigned n) {
    if (o->ar.j >= o->ar.oh) return 0;
    ar_push(&o->ar, row, n, 0, n == 3 ? 1 : 0, n == 3 ? 2 : 0, n, pv_emit, o);
    return !o->werr;
}

static int pv_out_end(pv_out_t *o) {
    if (o->ar.j != o->ar.oh || o->ar.ty != o->ar.th || o->werr) return 0;
    jpeg_finish_compress(o->enc);
    return 1;
}

/* The output side after success or an error exit: the encoder and the file closed, the file removed unless it is a good one. Returns ok, 0 when closing the file failed. */
static int pv_out_close(pv_out_t *o, const char *dst, int ok) {
    if (o->enc_up) jpeg_destroy_compress(o->enc);
    o->enc_up = 0;
    if (o->fout && fclose((void *)o->fout)) ok = 0;
    o->fout = (void *)0;
    if (!ok && o->made) unlink(dst);
    return ok;
}

/* The JPEG at src into dst. cover = 0: a podcast cover (PV_SIZE, quality PV_QUALITY, a progressive picture held to PC_COVER_MAX_PX). cover = the size t of an album cover: stock's size and
 * quality 90, the decode scale the smallest picture that still has both target sides; a picture stock keeps as it is (smaller than t) is not touched: -1. Else 1 or 0. */
static int pv_jpeg(const char *src, const char *dst, unsigned cover) {
    unsigned char dec[PV_DEC_SIZE] __attribute__((aligned(8)));
    pv_out_t o;
    void *volatile fin = (void *)0;
    unsigned char *volatile row = (unsigned char *)0;
    volatile int dec_up = 0, ok = 0, keep = 0;
    unsigned w, h, sof, side, d, ow, oh, n, y, tw = 0, th = 0;
    unsigned char *line[1];
    if (pc_pic_info(src, &w, &h, &sof) != 1 || (sof != 0xc0 && sof != 0xc1 && sof != 0xc2) || !w || !h) return 0;
    if (cover && sof == 0xc2 && (w > 8192 || h > 8192 || w * h > PV_COVER_PROGRESSIVE_PX)) return PV_REFUSED;
    if (w > 8192 || h > 8192 ||
        w * h > (sof != 0xc2 ? PV_BASELINE_MAX_PX
                 : cover     ? PV_COVER_PROGRESSIVE_PX
                             : PC_COVER_MAX_PX))
        return 0;
    side = w > h ? w : h;
    fin = fopen(src, "rb");
    if (!fin) return 0;
    pv_out_init(&o);
    *(void **)dec = &o.err;
    if (_setjmp(o.err.jb)) goto done; /* a libjpeg error lands here */
    jpeg_CreateDecompress(dec, PV_VERSION, PV_DEC_SIZE);
    dec_up = 1;
    jpeg_stdio_src(dec, fin);
    if (jpeg_read_header(dec, 1) != 1) goto done;
    n = *pv_w(dec, JF_COMPONENTS);
    if (n != 1 && n != 3) goto done; /* gray or colour; CMYK is refused */
    if (cover) {
        unsigned sw, sh;
        cc_stock_dims(w, h, n, &sw, &sh);
        if (!cc_stock_fit(sw, sh, cover, &tw, &th)) {
            keep = 1;
            goto done;
        }
        for (d = 8; d > 1 && ((w + d - 1) / d < tw || (h + d - 1) / d < th); d >>= 1) {
        } /* the largest reduction that keeps both target sides */
    } else
        for (d = 8; d > 1 && (side + d - 1) / d < PV_SIZE; d >>= 1) {
        } /* the largest reduction that keeps the longer side at PV_SIZE or more */
    *pv_w(dec, JF_SCALE_NUM) = 1;
    *pv_w(dec, JF_SCALE_DEN) = d;
    if (!jpeg_start_decompress(dec)) goto done;
    ow = *pv_w(dec, JF_OUT_WIDTH), oh = *pv_w(dec, JF_OUT_HEIGHT);
    if (!ow || !oh || ow > 8192) goto done;
    if (!cover) pv_pod_fit(ow, oh, &tw, &th);
    row = calloc(ow * n, 1);
    if (!row || !pv_out_begin(&o, ow, oh, tw, th, cover ? CV_QUALITY : PV_QUALITY, dst)) goto done;
    for (y = 0; y < oh; ++y) {
        line[0] = (unsigned char *)row;
        if (jpeg_read_scanlines(dec, line, 1) != 1 || !pv_out_row(&o, (unsigned char *)row, n)) goto done;
    }
    ok = pv_out_end(&o);
done:
    if (dec_up) jpeg_destroy_decompress(dec);
    free((void *)row);
    if (fin) fclose((void *)fin);
    ok = pv_out_close(&o, dst, ok);
    return keep ? -1 : ok;
}

int pv_shrink(const char *src, const char *dst) { return pv_jpeg(src, dst, 0); }

static int pv_png_row(void *user, const unsigned char *rgb, unsigned w) {
    (void)w;
    return pv_out_row(user, rgb, 3);
}

static int pv_png(const char *src, const char *dst, unsigned cover) {
    pv_out_t o;
    void *volatile fin = (void *)0;
    pp_t *volatile pp = (pp_t *)0;
    volatile int ok = 0,
                 keep =
                     0; /* keep: not a picture this can shrink in one pass (interlaced), or one stock keeps as it is */
    pp_t *opened = (pp_t *)0;
    unsigned w, h, tw = 0, th = 0;
    int r;
    fin = fopen(src, "rb");
    if (!fin) return 0;
    pv_out_init(&o);
    if (_setjmp(o.err.jb)) goto done; /* a libjpeg error (the encoder's) lands here */
    r = pp_open(fin, &opened, &w, &h);
    pp = opened;
    if (r <= 0) {
        keep = r < 0;
        goto done;
    }
    if (cover) {
        if (!cc_stock_fit(w, h, cover, &tw, &th)) { /* stock keeps a picture smaller than the request */
            keep = 1;
            goto done;
        }
    } else
        pv_pod_fit(w, h, &tw, &th);
    if (!pv_out_begin(&o, w, h, tw, th, cover ? CV_QUALITY : PV_QUALITY, dst) || !pp_run(pp, pv_png_row, &o)) goto done;
    ok = pv_out_end(&o);
done:
    pp_free((pp_t *)pp);
    if (fin) fclose((void *)fin);
    ok = pv_out_close(&o, dst, ok);
    return ok ? 1 : -keep;
}

int pv_shrink_png(const char *src, const char *dst) { return pv_png(src, dst, 0); }

int pv_cover(const char *src, const char *dst, unsigned size) {
    unsigned w, h, sof;
    int kind = pc_pic_info(src, &w, &h, &sof);
    return kind == 1 ? pv_jpeg(src, dst, size) : kind == 2 ? pv_png(src, dst, size) : 0;
}

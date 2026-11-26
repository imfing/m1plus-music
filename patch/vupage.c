/* M1+ Music VU Meter Mode: a fullscreen Now Playing page of two needle VU meters (portrait).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/vu.md has the design. The page is ui/m1plus_vu.bin (tools/pod_ui.py build_vu_page), the Vinyl page's structure (patch/vinyl.c): a fullscreen window holding one view vu_view (the whole
 * window: the touch target, painted by this file in its own EVT_AFTER_PAINT) and the text as ordinary labels over it. Like the Vinyl page it has no hook, no widget per thing drawn, one page-scoped
 * timer set in place with timer_modify, and nothing at boot but vupage_boot (the stale mark).
 *
 *   picture   a 320 x 480 RGBA frame this file owns, composed from tools/vu_art.py's pictures: vu_base (faceplate, both dials without needles, hoods, unlit PEAK lamps, print, keys at rest),
 *             the needles and their shadows (drawn here at run time: vp_needle is tools/vu_art.py draw_needle), vu_hood over each needle's root, vu_lamp for a lit PEAK lamp, vu_keys. A
 *             change restores its rectangle from vu_base, draws it again and invalidates only that rectangle.
 *   levels    the page creates the mark (VU_FILE with VU_MAGIC) while it is in front and the screen is lit and removes it when the screen goes dark, another window covers it or it closes: the player's level tap (patch/vu.c) measures only while it is there and keeps
 *             the record in the same file. Each tick reads it whole (a read is kept when seq == seq_end), takes the entries audible since the last tick (their due_us and dur_us against
 *             CLOCK_MONOTONIC) and turns their rms into the needle's target (the law of tools/vu_art.py, linear in the voltage; 0 VU is the page's automatic reference level vp_lv.lt, see vp_level). Nothing audible (rate 0, a record
 *             that stopped being written, a player that is not playing): the target is the rest position.
 *   needle    a second-order model (VP_OMEGA, VP_ZETA: 99 % of a step in about 300 ms, about 1 % overshoot) stepped by the real elapsed time, in 1 ms steps, capped at VN_DT_MAX.
 *   lamp      PEAK lights when a block's peak is at or above ref + 8 dB (VP_G11) or at digital full scale (VP_PEAK_FS), and stays VU_HOLD_MS after the last such block.
 *   touch     as the Vinyl page: the chevron closes, the keys play / pause and skip, a tap on the page above the keys plays / pauses (closes, when Now Playing's idle timer opened it).
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "libsrc.h"
#include "entries.h"
#include "scrobble.h"
#include "lyrics.h"
#include "vu.h"

enum { K_NONE, K_CLOSE, K_PREV, K_PLAY, K_NEXT, K_BODY };

#define VP_DEG 0.017453292519943295
#define VP_SWEEP (46 * VP_DEG) /* the scale's half sweep (tools/vu_art.py SWEEP) */
#define VP_REST (-(46 + 2.5) * VP_DEG) /* the parked needle (tools/vu_art.py REST) */
/* The automatic reference ("someone set the record level", docs/modules/vu.md). 0 VU is the reference ref (dBFS rms), one value for both channels; the page follows the long-term level lt (power of the
 * louder channel's rms) so that ref = lt + 3 dB: the long-term average sits 3 dB below 0 VU. Everything is kept in the power domain (no log, no pow): ref power = lt * VP_G3, the rms at +3 VU = sqrt(lt) * VP_G3. */
#define VP_G3 1.9952623149688795 /* 10^(3/10): 3 dB in power (also 3 dB in amplitude: 10^(3/20) squared) */
#define VP_G11 \
    12.589254117941675 /* 10^(11/10): the PEAK lamp's level in lt: ref + 8 dB in power = lt * 10^(0.3 + 0.8) (real tracks: lit some 10 to 30 % of the time, docs/modules/vu.md) */
#define VP_LT0 0.03162277660168379 /* the start value on page open: ref -12 dBFS, lt -15 dBFS */
#define VP_LT_MIN 0.0019952623149688797 /* ref -24 dBFS: lt -27 dBFS */
#define VP_LT_MAX \
    0.12589254117941673 /* ref -6 dBFS: lt -9 dBFS (lt is clamped, so a loud track does not wind it up beyond what ref can show) */
#define VP_FLOOR 1e-5 /* the power below which a block is not programme (-50 dBFS rms): lt stands still */
#define VP_TAU_SLOW 12000 /* ms: lt follows the louder channel's power with this time constant, up and down */
#define VP_TAU_FAST 2000 /* ms: while a loud track pegs the needle, lt rises with this one */
#define VP_PEG_MS \
    1000 /* the needle must read above +3 VU (power > lt * VP_G3 * VP_G3) this long before lt rises fast; the fast rise ends when the level is under 0 VU again */
#define VP_PEAK_FS \
    0.9885530946569389 /* 10^(-0.1/20): the PEAK lamp always lights from this peak, -0.1 dBFS (digital full scale) */
#define VP_OMEGA 14.05 /* the needle's natural frequency (rad/s) and damping: 99 % in 300 ms, 0.9 % overshoot */
#define VP_ZETA 0.826
/* The kick when the page opens: each needle starts at the rest with this speed (rad/s) and runs through the ballistics, like a meter that is powered up. With the target at the rest,
 * x = REST + v0 / wd * exp(-z w t) sin(wd t), wd = w sqrt(1 - z^2) = 7.92: the peak lies at t = atan(wd / (z w)) / wd = 76 ms and is v0 * 0.02960 rad. 13.62 gives 0.4031 rad, 23.1 degrees: the -10 VU mark
 * (angle -25.4 degrees). The needle crosses the rest again at pi / wd = 397 ms (vp_step holds it there). */
#define VP_KICK 13.62
#define VP_SEE 0.0008 /* a needle is drawn again when it moved this much (rad: 0.12 px at the tip) */
#define VP_SHADOW_ALPHA (120.0 / 255.0)

/* tools/vu_art.py: the shadow's blur is a gaussian of sigma 1.6 px, so its edge is the normal distribution's: P(u) = 65535 * 0.5 * (1 + erf(u / (1.6 sqrt 2))) at u = i / 16 px, i = 0 .. 128
 * (u < 0: 65535 - P(-u); u >= 8: 65535). test/pod/vu.py compares the table. */
static const unsigned short vp_phi_t[129] = {
    32768, 33789, 34808, 35824, 36836, 37842, 38840, 39828, 40807, 41773, 42726, 43665, 44588, 45495, 46384,
    47253, 48104, 48933, 49742, 50528, 51292, 52034, 52751, 53445, 54115, 54762, 55383, 55981, 56555, 57104,
    57630, 58132, 58611, 59067, 59501, 59913, 60304, 60673, 61023, 61352, 61663, 61955, 62230, 62487, 62728,
    62954, 63164, 63360, 63543, 63713, 63870, 64016, 64151, 64276, 64391, 64497, 64594, 64684, 64766, 64841,
    64909, 64972, 65029, 65081, 65128, 65171, 65209, 65244, 65276, 65305, 65330, 65353, 65374, 65392, 65409,
    65424, 65437, 65449, 65459, 65469, 65477, 65484, 65490, 65496, 65501, 65506, 65509, 65513, 65516, 65518,
    65521, 65523, 65524, 65526, 65527, 65528, 65529, 65530, 65531, 65531, 65532, 65532, 65533, 65533, 65533,
    65534, 65534, 65534, 65534, 65534, 65534, 65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535,
    65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535};

typedef struct {
    double x, v, tgt; /* the needle's angle (rad, clockwise from straight up), its speed and its target */
    double ad; /* the angle drawn */
    int drawn, r[4]; /* a needle is on the frame, and the rectangle it was drawn in */
    int lit, lvl,
        lvl_drawn; /* the PEAK lamp: held lit now; its brightness now and as drawn (0 .. 255; 255 while lit, falling to 0 over VU_GLOW_MS after) */
    unsigned until; /* time_now_ms at which a lit lamp goes out and starts to fade */
} vp_meter;

static struct {
    void *win, *view, *title, *artist, *times, *status;
    void *frame, *base, *keys, *hood, *lamp; /* RGBA8888 bitmaps: the frame and the pictures */
    unsigned timer, ival;
    int fg;
    unsigned key; /* the playing track (a hash), 0 none, ~0 not looked at yet */
    int playing, pos, len;
    char fmt[8];
    int vol, hh, mm;
    int playkey; /* the play key shows 0 play, 1 pause; -1 not drawn */
    int pressed; /* the key drawn pressed, K_NONE */
    unsigned t_last;
    int dx0, dy0, dx1, dy1; /* the rectangle changed since the last invalidate (empty: dx1 <= dx0) */
    int touch, down, sx, sy; /* a touch is down; what it began on; where */
    int idle; /* opened by Now Playing's timer (vupage_open_idle): a tap on the page closes it; cleared with the rest at destroy */
    vp_meter m[2];
    long long t_prev; /* CLOCK_MONOTONIC us up to which the record's entries were taken */
    int sig; /* the last fresh record had a signal */
    double rms[2], pk[2]; /* its levels */
    vu_record rec; /* the last read */
    int watch; /* the mark file exists (vp_watch) */
} vu __attribute__((section(".scratch")));

static void vp_watch(int on);

/* ---------------------------------------------------------------------------
 * The record
 */
static long long vp_now_us(void) {
    struct {
        int sec, nsec;
    } ts;
    return clock_gettime(1, &ts) ? 0 : (long long)ts.sec * 1000000 + ts.nsec / 1000;
}

/* A float of the record as a double; 0 for a negative, NaN, infinite or tiny one (below 2^-63, which also keeps the denormals, which trap on the MIPS FPU, out of the FPU). */
static double vp_fl(const float *p) {
    unsigned b;
    __builtin_memcpy(&b, p, 4);
    return (b >> 31) || (b >> 23 & 255) < 64 || (b >> 23 & 255) == 255 ? 0.0 : (double)*p;
}

/* The record whole into vu.rec: 1 when it is consistent, 0 when there is none (no file, only the mark, another magic: the kill switch leaves the mark alone), -1 when a write kept
 * overlapping the reads (the caller keeps what it knew). */
static int vp_read(void) {
    int tries, i;
    for (tries = 0; tries < 3; ++tries) {
        void *f = fopen(VU_FILE, "rb");
        unsigned n;
        if (!f) return 0;
        n = fread(&vu.rec, 1, sizeof vu.rec, f);
        fclose(f);
        if (n != sizeof vu.rec) return 0;
        for (i = 0; i < 8; ++i)
            if (vu.rec.magic[i] != VU_MAGIC[i]) return 0;
        if (vu.rec.seq == vu.rec.seq_end) return 1;
    }
    return -1;
}

/* The levels of what became audible since the last tick (at most the last 100 ms): the entries with due_us <= t whose end (due_us + dur_us) is after the window's start, their sums of
 * squares and frames added and the largest peak. 0 when there is nothing: rate 0 (no levels), no entry, a record that has not been written for VU_STALL_MS (paused, stopped, no new block) or no
 * entry audible in the window. */
static int vp_signal(long long t) {
    const vu_record *r = &vu.rec;
    long long lo = vu.t_prev < t - 100000 ? t - 100000 : vu.t_prev;
    double sq[2] = {0, 0}, fr = 0;
    int i, c;
    vu.pk[0] = vu.pk[1] = 0;
    if (r->rate <= 0 || r->count <= 0 || r->count > VU_RING || r->head < 0 || r->head >= VU_RING) return 0;
    if (t - r->now_us > VU_STALL_MS * 1000LL) return 0;
    for (i = 0; i < r->count; ++i) {
        const vu_entry *e = &r->ring[(r->head - i + VU_RING) % VU_RING];
        if (e->due_us > t) continue; /* not audible yet */
        if (e->due_us + e->dur_us <= lo) break; /* it, and every older one, ended before the window */
        if (e->frames <= 0) continue;
        fr += e->frames;
        for (c = 0; c < 2; ++c) {
            double p = vp_fl(&e->peak[c]);
            sq[c] += vp_fl(&e->sumsq[c]);
            if (p > vu.pk[c]) vu.pk[c] = p;
        }
    }
    if (fr <= 0) return 0;
    for (c = 0; c < 2; ++c) vu.rms[c] = sqrt(sq[c] / fr);
    return 1;
}

/* The automatic reference's state (reset by vupage_open, kept across tracks): lt, the long-term power of the louder channel (ref = lt + 3 dB); peg, ms the needle has read above +3 VU; fast, the quick rise is on. */
static struct {
    double lt;
    int peg, fast;
} vp_lv __attribute__((section(".scratch")));

/* One look's worth of programme level: p, the louder channel's rms power of this look, over dt ms. Below the floor (silence, a pause) nothing moves. lt follows p slowly (VP_TAU_SLOW), up and
 * down; after the needle has read above +3 VU for VP_PEG_MS it rises with VP_TAU_FAST until the level is under 0 VU again. lt stays inside [VP_LT_MIN, VP_LT_MAX] (ref -24 .. -6 dBFS). */
static void vp_level(double p, unsigned dt) {
    double *lt = &vp_lv.lt;
    if (p <= VP_FLOOR) {
        vp_lv.peg = 0;
        return;
    }
    if (p > *lt * VP_G3 * VP_G3) {
        if (vp_lv.peg < VP_PEG_MS) vp_lv.peg += (int)dt;
        if (vp_lv.peg >= VP_PEG_MS) vp_lv.fast = 1;
    } else {
        vp_lv.peg = 0;
        if (p < *lt * VP_G3) vp_lv.fast = 0;
    }
    *lt += (p - *lt) * ((double)dt / (vp_lv.fast && p > *lt ? VP_TAU_FAST : VP_TAU_SLOW));
    if (*lt < VP_LT_MIN) *lt = VP_LT_MIN;
    if (*lt > VP_LT_MAX) *lt = VP_LT_MAX;
}

/* The needle's angle for an rms (tools/vu_art.py angle, frac): the sweep is linear in the voltage, +3 VU at the end (full, the rms there), 3 % past it at most. */
static double vp_angle(double rms, double full) {
    double f = rms / full;
    return -VP_SWEEP + (f > 1.03 ? 1.03 : f) * 2 * VP_SWEEP;
}

/* The needle model, x'' = w^2 (target - x) - 2 z w x', in 1 ms steps (semi-implicit Euler: its step response is the 300 ms / 1 % of VP_OMEGA and VP_ZETA). A needle that has all but arrived
 * lands on the target, so the tail never decays into denormals. */
static void vp_step(vp_meter *m, int ms) {
    int i;
    double e;
    for (i = 0; i < ms; ++i) {
        m->v += 0.001 * (VP_OMEGA * VP_OMEGA * (m->tgt - m->x) - 2 * VP_ZETA * VP_OMEGA * m->v);
        m->x += 0.001 * m->v;
        if (m->x < VP_REST)
            m->x = VP_REST,
            m->v = 0; /* the rest is the stop: the kick's rebound (and any overshoot of a fall) ends on it */
    }
    e = m->tgt - m->x;
    if (__builtin_fabs(e) < 2e-5 && __builtin_fabs(m->v) < 1e-4) m->x = m->tgt, m->v = 0;
}

/* ---------------------------------------------------------------------------
 * Composing: what changed is drawn again into the frame and its rectangle marked to invalidate
 */
static void vp_dirty(int x0, int y0, int x1, int y1) {
    if (vu.dx1 <= vu.dx0)
        vu.dx0 = x0, vu.dy0 = y0, vu.dx1 = x1, vu.dy1 = y1;
    else {
        if (x0 < vu.dx0) vu.dx0 = x0;
        if (y0 < vu.dy0) vu.dy0 = y0;
        if (x1 > vu.dx1) vu.dx1 = x1;
        if (y1 > vu.dy1) vu.dy1 = y1;
    }
}

static void vp_flush(void) {
    int r[4];
    if (vu.dx1 <= vu.dx0 || !vu.view) return;
    r[0] = vu.dx0, r[1] = vu.dy0, r[2] = vu.dx1 - vu.dx0, r[3] = vu.dy1 - vu.dy0;
    vu.dx0 = vu.dy0 = vu.dx1 = vu.dy1 = 0;
    widget_invalidate_force(vu.view, r);
}

/* The pictures a draw reads and the frame it writes, locked once for a whole look. */
static struct {
    unsigned *f, *base, *hood, *lamp;
} vl __attribute__((section(".scratch")));

static int vp_lock(void) {
    vl.f = (unsigned *)bitmap_lock_buffer_for_write(vu.frame);
    vl.base = (unsigned *)bitmap_lock_buffer_for_read(vu.base);
    vl.hood = (unsigned *)bitmap_lock_buffer_for_read(vu.hood);
    vl.lamp = (unsigned *)bitmap_lock_buffer_for_read(vu.lamp);
    return vl.f && vl.base && vl.hood && vl.lamp;
}

static void vp_unlock(void) {
    if (vl.f) bitmap_unlock_buffer(vu.frame);
    if (vl.base) bitmap_unlock_buffer(vu.base);
    if (vl.hood) bitmap_unlock_buffer(vu.hood);
    if (vl.lamp) bitmap_unlock_buffer(vu.lamp);
    memset(&vl, 0, sizeof vl);
}

/* The dirty rectangle of meter m's needle at angle a (tools/vu_art.py needle_rect): the box of its four corners, grown by VU_RECT_PAD, the shadow's offset on the right and bottom, clipped to the window. */
__attribute__((noinline)) void vp_rect(int m, double a, int *r) {
    static const double rr[2] = {VU_R0, VU_R1}, hw[2] = {1.1, 0.5};
    double ux = sin(a), uy = -cos(a), nx = cos(a), ny = sin(a), x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    int i, s, wy0 = VU_WIN_Y0 + m * VU_METER_DY, ix1, iy1;
    for (i = 0; i < 2; ++i)
        for (s = -1; s <= 1; s += 2) {
            double x = VU_PIV_X + rr[i] * ux + s * hw[i] * nx,
                   y = VU_PIV_Y + m * VU_METER_DY + rr[i] * uy + s * hw[i] * ny;
            if (x < x0) x0 = x;
            if (y < y0) y0 = y;
            if (x > x1) x1 = x;
            if (y > y1) y1 = y;
        }
    ix1 = (int)x1 + (x1 > (int)x1),
    iy1 = (int)y1 + (y1 > (int)y1); /* (the page's coordinates are positive: a cast is the floor) */
    r[0] = (int)x0 - VU_RECT_PAD, r[1] = (int)y0 - VU_RECT_PAD;
    r[2] = ix1 + VU_RECT_PAD + VU_SH_DX, r[3] = iy1 + VU_RECT_PAD + VU_SH_DY;
    if (r[0] < VU_WIN_X0) r[0] = VU_WIN_X0;
    if (r[1] < wy0) r[1] = wy0;
    if (r[2] > VU_WIN_X1) r[2] = VU_WIN_X1;
    if (r[3] > wy0 + VU_WIN_H) r[3] = wy0 + VU_WIN_H;
}

static int vp_phi(double u) { /* the shadow's edge, 0 .. 65535 */
    double v = u < 0 ? -u : u;
    unsigned k, i, fr;
    int p;
    if (v >= 8.0) return u < 0 ? 0 : 65535;
    k = (unsigned)(v * 4096.0), i = k >> 8, fr = k & 255;
    p = (int)((vp_phi_t[i] * (256 - fr) + vp_phi_t[i + 1] * fr) >> 8);
    return u < 0 ? 65535 - p : p;
}

static double vp_hw(double t) {
    return 1.1 + (0.5 - 1.1) * (t - VU_R0) / (VU_R1 - VU_R0);
} /* the needle's half width at radius t */

/* Meter m's needle and its shadow at angle a over the frame, inside c (x0, y0, x1, y1): tools/vu_art.py draw_needle, pixel for pixel in its arithmetic (coverage of the needle, the shadow
 * from the gaussian's edge table). Only the columns of a row that the needle or its shadow can reach are looked at. */
__attribute__((noinline)) void vp_needle(int m, double a, const int *c) {
    double ux = sin(a), uy = -cos(a), cs = -uy, sn = ux, py = VU_PIV_Y + m * VU_METER_DY;
    double ts = VU_SH_DX * ux + VU_SH_DY * uy, ds = VU_SH_DX * cs + VU_SH_DY * sn;
    int x, y;
    for (y = c[1]; y < c[3]; ++y) {
        double dy = y + 0.5 - py, lo = (-2.7 - dy * sn) / cs, hi = (2.7 - dy * sn) / cs, lo2, hi2;
        unsigned *row = vl.f + y * VN_W;
        int xa, xb;
        lo2 = VU_SH_DX + (-6.5 - (dy - VU_SH_DY) * sn) / cs, hi2 = VU_SH_DX + (6.5 - (dy - VU_SH_DY) * sn) / cs;
        if (lo2 < lo) lo = lo2;
        if (hi2 > hi) hi = hi2;
        lo += VU_PIV_X - 1.5, hi += VU_PIV_X - 0.5 + 2; /* x + 0.5 = VU_PIV_X + dx */
        xa = lo <= c[0] ? c[0] : lo >= c[2] ? c[2] : (int)lo;
        xb = hi >= c[2] ? c[2] : hi < c[0] ? c[0] : (int)hi + 1;
        for (x = xa; x < xb; ++x) {
            double dx = x + 0.5 - VU_PIV_X, t = dx * ux + dy * uy, d = dx * cs + dy * sn, t2 = t - ts, d2 = d - ds,
                   al = 0, cov = 0;
            if (t2 > VU_R0 - 9.1 && t2 < VU_R1 + 9.1) { /* the shadow: the needle's shape moved, blurred */
                double tc = t2 < VU_R0 ? VU_R0 : t2 > VU_R1 ? VU_R1 : t2, hw = vp_hw(tc);
                if ((d2 < 0 ? -d2 : d2) < hw + 8.0) {
                    int lat = vp_phi(hw - d2) + vp_phi(hw + d2) - 65535,
                        en = vp_phi(t2 - VU_R0) + vp_phi(VU_R1 - t2) - 65535;
                    if (lat > 0 && en > 0) al = (double)lat * en * (VP_SHADOW_ALPHA / 65535.0 / 65535.0);
                }
            }
            if (t > VU_R0 - 1 && t < VU_R1 + 1) { /* the needle: coverage of its edge and both ends */
                double w = vp_hw(t) + 0.5 - (d < 0 ? -d : d), e0 = t - VU_R0 + 0.5, e1 = VU_R1 - t + 0.5;
                if (w > 0 && e0 > 0 && e1 > 0) cov = (w > 1 ? 1 : w) * (e0 > 1 ? 1 : e0) * (e1 > 1 ? 1 : e1);
            }
            if (al > 0.002 || cov > 0) {
                unsigned p = row[x];
                double r = p & 255, g = p >> 8 & 255, b = p >> 16 & 255;
                if (al > 0.002) r *= 1 - al, g *= 1 - al, b *= 1 - al;
                if (cov > 0) r += (0x16 - r) * cov, g += (0x13 - g) * cov, b += (0x10 - b) * cov;
                row[x] = 0xff000000u | (unsigned)(r + 0.5) | (unsigned)(g + 0.5) << 8 | (unsigned)(b + 0.5) << 16;
            }
        }
    }
}

/* A picture (w x h, at (ox, oy)) over the frame inside the rectangle d, by its alpha times scale / 255. */
static void vp_over(const unsigned *img, int ox, int oy, int w, int h, const int *d, int scale) {
    int x0 = d[0] > ox ? d[0] : ox, y0 = d[1] > oy ? d[1] : oy, x1 = d[2] < ox + w ? d[2] : ox + w,
        y1 = d[3] < oy + h ? d[3] : oy + h, x, y;
    for (y = y0; y < y1; ++y)
        for (x = x0; x < x1; ++x) {
            unsigned l = img[(y - oy) * w + x - ox];
            unsigned a = ((l >> 24) * (unsigned)scale + 127) / 255;
            if (a) vl.f[y * VN_W + x] = m1_mix(vl.f[y * VN_W + x], l, a);
        }
}

static void vp_union(int *d, const int *r) {
    if (d[2] <= d[0])
        memcpy(d, r, 16);
    else {
        if (r[0] < d[0]) d[0] = r[0];
        if (r[1] < d[1]) d[1] = r[1];
        if (r[2] > d[2]) d[2] = r[2];
        if (r[3] > d[3]) d[3] = r[3];
    }
}

/* Meter m, if its needle moved visibly (VP_SEE; one that has come to rest is drawn where it stopped), its lamp changed or force (the first look): the rectangle (the needle's old and new, the lamp's, with force the hood's) restored from vu_base,
 * then, as tools/vu_art.py compose, the lit lamp, the needle and the hood over what they touch; invalidated. The layers are locked. */
static void vp_meter_draw(int m, int force) {
    vp_meter *vm = &vu.m[m];
    int moved = force || !vm->drawn || __builtin_fabs(vm->x - vm->ad) >= VP_SEE || (!vm->v && vm->x != vm->ad),
        lamp = force || vm->lvl != vm->lvl_drawn;
    int d[4] = {0, 0, 0, 0}, nr[4], lr[4], hr[4], c[4], y;
    double a = moved ? vm->x : vm->ad;
    if (!moved && !lamp) return;
    lr[0] = VU_LAMP_X, lr[1] = VU_LAMP_Y + m * VU_METER_DY, lr[2] = lr[0] + VU_LAMP_W, lr[3] = lr[1] + VU_LAMP_H;
    hr[0] = VU_HOOD_X, hr[1] = VU_HOOD_Y + m * VU_METER_DY, hr[2] = hr[0] + VU_HOOD_W, hr[3] = hr[1] + VU_HOOD_H;
    vp_rect(m, a, nr);
    if (moved) {
        vp_union(d, nr);
        if (vm->drawn) vp_union(d, vm->r);
    }
    if (lamp) vp_union(d, lr);
    if (force) vp_union(d, hr);
    for (y = d[1]; y < d[3]; ++y)
        memcpy(vl.f + y * VN_W + d[0], vl.base + y * VN_W + d[0], (unsigned)(d[2] - d[0]) * 4);
    if (vm->lvl) vp_over(vl.lamp, lr[0], lr[1], VU_LAMP_W, VU_LAMP_H, d, vm->lvl);
    c[0] = nr[0] > d[0] ? nr[0] : d[0], c[1] = nr[1] > d[1] ? nr[1] : d[1];
    c[2] = nr[2] < d[2] ? nr[2] : d[2], c[3] = nr[3] < d[3] ? nr[3] : d[3];
    if (c[2] > c[0] && c[3] > c[1]) vp_needle(m, a, c);
    vp_over(vl.hood, hr[0], hr[1], VU_HOOD_W, VU_HOOD_H, d, 255);
    vm->ad = a, vm->drawn = 1, vm->lvl_drawn = vm->lvl;
    memcpy(vm->r, nr, 16);
    vp_dirty(d[0], d[1], d[2], d[3]);
    vp_flush();
}

/* A key's cell of the band: the play key in its look (the glyph, pressed), previous and next pressed from vu_keys, at rest from the base (the Vinyl page's vn_key). */
static void vp_key(int k) {
    unsigned *f = (unsigned *)bitmap_lock_buffer_for_write(vu.frame),
             *base = (unsigned *)bitmap_lock_buffer_for_read(vu.base),
             *keys = (unsigned *)bitmap_lock_buffer_for_read(vu.keys);
    int x0 = k == K_PREV   ? VN_PREV_X0
             : k == K_PLAY ? VN_PLAY_X0
                           : VN_NEXT_X0,
        x1 = k == K_PREV   ? VN_PLAY_X0
             : k == K_PLAY ? VN_NEXT_X0
                           : VN_NEXT_X1,
        down = vu.pressed == k,
        cell = k == K_PLAY ? (vu.playkey + 2 * down) * (VN_NEXT_X0 - VN_PLAY_X0)
               : down      ? (k == K_PREV ? VN_CELL_PREV : VN_CELL_NEXT)
                           : -1,
        x, y;
    if (f && base && keys) {
        for (y = VN_BAND_Y0; y < VN_BAND_Y1; ++y)
            for (x = x0; x < x1; ++x)
                f[y * VN_W + x] = cell < 0 ? base[y * VN_W + x] : keys[(y - VN_BAND_Y0) * VN_KEYS_W + cell + x - x0];
        vp_dirty(x0, VN_BAND_Y0, x1, VN_BAND_Y1);
    }
    if (f) bitmap_unlock_buffer(vu.frame);
    if (base) bitmap_unlock_buffer(vu.base);
    if (keys) bitmap_unlock_buffer(vu.keys);
}

static int vp_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int src[4];
    (void)ctx;
    if (!canvas || !vu.win || !vu.frame) return RET_OK;
    src[0] = 0, src[1] = 0, src[2] = VN_W, src[3] = VN_H;
    canvas_draw_image(canvas, vu.frame, src, src);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * What the page shows: the player, the record, the status bar and the clock, looked at on the timer (the text parts are the Vinyl page's)
 */
static int vp_volume(void) { /* the status bar's label_volume text, read only (never set) */
    void *bar = *(void **)SYSTEM_BAR, *lab = bar ? widget_lookup(bar, "label_volume", 1) : (void *)0;
    char buf[16];
    int v = 0, i;
    if (!lab) return 0;
    buf[0] = 0;
    m1_text_utf8(lab, buf, sizeof buf);
    for (i = 0; buf[i] >= '0' && buf[i] <= '9' && i < 4; ++i) v = v * 10 + buf[i] - '0';
    return v;
}

static void vp_format(char *out, const char *path) { /* the file extension, upper case, at most 4 characters */
    unsigned n = 0, dot = 0, i, k = 0;
    while (path[n]) {
        if (path[n] == '.') dot = n + 1;
        if (path[n] == '/') dot = 0;
        ++n;
    }
    for (i = dot; dot && path[i] && k < 4; ++i)
        out[k++] = path[i] >= 'a' && path[i] <= 'z' ? (char)(path[i] - 32) : path[i];
    out[k] = 0;
}

static unsigned vp_track_key(void *t) {
    unsigned h = cc_fnv(cc_fnv(cc_fnv(FNV_SEED, cc_str(t, REC_PATH)), cc_str(t, REC_TITLE)), cc_str(t, REC_NAME));
    return h | !h;
}

static void vp_copy(char *dst, unsigned size, const char *s) {
    unsigned n = 0;
    while (s[n] && n + 1 < size) dst[n] = s[n], ++n;
    while (n && ((unsigned char)s[n] & 0xc0) == 0x80 && s[n]) --n; /* a cut never leaves half a UTF-8 character */
    dst[n] = 0;
}

/* "VOL 42 | FLAC | 21:07" (tools/vinyl_art.py status_text). */
static void vp_status(char *out, unsigned size) {
    snprintf(out, size, "VOL %d | %s%s%02d:%02d", vu.vol, vu.fmt, vu.fmt[0] ? " | " : "", vu.hh, vu.mm);
}

static int vp_moving(void) {
    int i;
    if (vu.playing) return 1;
    for (i = 0; i < 2; ++i) {
        const vp_meter *m = &vu.m[i];
        if (m->lit || m->lvl || __builtin_fabs(m->tgt - m->x) > 1e-4 || __builtin_fabs(m->v) > 1e-3 || m->x != m->ad)
            return 1;
    }
    return 0;
}

/* One look at everything: the text, the record, the needles, the lamps, the keys; draws what changed and invalidates it. */
static void vp_update(int force) {
    void *t = cc_playing();
    int pos = 0, len = 0, vol, playing = mclGetPlayStatus() == 2, status = force, fresh = 0, i;
    double full;
    unsigned key = t ? vp_track_key(t) : 0, now = time_now_ms(), dt = now - vu.t_last;
    long secs = time((long *)0);
    const int *tm = secs > 1577836800L ? localtime(&secs) : (const int *)0;
    int hh = tm ? tm[2] : 0, mm = tm ? tm[1] : 0;
    char line[96];
    if (force) vu.key = ~0u;
    if (!vu.t_last || dt > VN_DT_MAX)
        dt = vu.t_last ? VN_DT_MAX : 0; /* the first look moves nothing; a stalled loop never jumps */
    vu.t_last = now | !now;
    if (!t || get_playtimeandlength(&pos, &len) != 1 || len <= 0) pos = len = 0;
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if (len > 65535) len = 65535, pos = pos > len ? len : pos;
    if (key != vu.key) {
        const char *s = t ? cc_str(t, REC_TITLE) : "";
        if (t && !*s) s = cc_str(t, REC_NAME);
        vu.key = key;
        vp_copy(line, sizeof line, t ? s : TR("Not Playing"));
        ly_title_face(vu.title, line);
        widget_set_text_utf8(vu.title, line);
        vp_copy(line, sizeof line, t ? cc_str(t, REC_ARTIST) : "");
        widget_set_text_utf8(vu.artist, line);
        vp_format(vu.fmt, t ? cc_str(t, REC_PATH) : "");
        vu.pos = -1, status = 1;
    }
    if (pos != vu.pos || len != vu.len) {
        vu.pos = pos, vu.len = len;
        snprintf(line, sizeof line, "%d:%02d  -%d:%02d", pos / 60, pos % 60, (len - pos) / 60, (len - pos) % 60);
        widget_set_text_utf8(vu.times, line);
    }
    vol = vp_volume();
    if (status || vol != vu.vol || hh != vu.hh || mm != vu.mm) {
        vu.vol = vol, vu.hh = hh, vu.mm = mm;
        vp_status(line, sizeof line);
        widget_set_text_utf8(vu.status, line);
    }
    vu.playing = playing;
    /* the levels: only a player that plays has any; a torn read (the player writing as it was read) keeps the last */
    if (playing) {
        long long us = vp_now_us();
        int r = vp_read();
        if (r >= 0) vu.sig = r == 1 && vp_signal(us), fresh = vu.sig;
        vu.t_prev = us;
    } else
        vu.sig = 0, vu.t_prev = 0;
    /* the rms at +3 VU: the reference this look is read against (the level learns from the look after it, below) */
    full = sqrt(vp_lv.lt) * VP_G3;
    for (i = 0; i < 2; ++i) {
        vp_meter *m = &vu.m[i];
        m->tgt = vu.sig ? vp_angle(vu.rms[i], full) : VP_REST;
        if (fresh && (vu.pk[i] >= VP_PEAK_FS || vu.pk[i] * vu.pk[i] >= vp_lv.lt * VP_G11))
            m->lit = 1, m->until = now + VU_HOLD_MS;
        else if (m->lit && (int)(now - m->until) >= 0)
            m->lit = 0;
        if (m->lit)
            m->lvl = 255;
        else if (m->lvl) { /* the afterglow: linear in alpha over VU_GLOW_MS from the end of the hold */
            int el = (int)(now - m->until);
            m->lvl = el >= VU_GLOW_MS ? 0 : 255 * (VU_GLOW_MS - el) / VU_GLOW_MS;
        }
        vp_step(m, (int)dt);
    }
    if (fresh) {
        double p0 = vu.rms[0] * vu.rms[0], p1 = vu.rms[1] * vu.rms[1];
        vp_level(p0 > p1 ? p0 : p1, dt);
    }
    if (vp_lock()) {
        vp_meter_draw(0, force);
        vp_meter_draw(1, force);
    }
    vp_unlock();
    if (force || playing != vu.playkey) {
        vu.playkey = playing;
        for (i = force ? K_PREV : K_PLAY; i <= (force ? K_NEXT : K_PLAY); ++i) vp_key(i);
    }
    vp_flush();
}

/* ---------------------------------------------------------------------------
 * The timer, the window's events
 */
static unsigned vp_want_ms(void) {
    return !m1_screen_lit() ? POD_DARK_MS : vp_moving() ? VU_TICK_MS : VN_IDLE_MS;
} /* screen off: a slow check, no visual work (docs/modules/vinyl.md "Timer and idle power") */

static void vp_retime(void) {
    unsigned want = vp_want_ms();
    if (vu.timer && want != vu.ival) {
        timer_modify(vu.timer, want);
        vu.ival = want;
    }
}

static int vp_tick(const void *timer) {
    (void)timer;
    if (!vu.win || !vu.fg) {
        vu.timer = 0;
        return RET_OK;
    }
    scrobble_note(cc_playing()); /* lit or dark (patch/scrobble.c) */
    vp_watch(m1_screen_lit());
    if (m1_screen_lit())
        vp_update(0); /* dark: nothing drawn, nothing read, no mark; the first lit tick catches up (dt is capped) */
    vp_retime();
    return RET_REPEAT;
}

static int vp_first(const void *timer) {
    (void)timer;
    vu.timer = 0;
    if (!vu.win || !vu.fg) return RET_OK;
    vp_watch(m1_screen_lit());
    if (!m1_screen_lit()) { /* opened with the screen off: the first full draw waits for the light */
        vu.timer = timer_add(vp_first, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    vp_update(1);
    vu.ival = vp_want_ms();
    vu.timer = timer_add(vp_tick, (void *)0, vu.ival);
    return RET_OK;
}

static void vp_free(void) {
    void **b[5] = {&vu.frame, &vu.base, &vu.keys, &vu.hood, &vu.lamp};
    int i;
    for (i = 0; i < 5; ++i)
        if (*b[i]) bitmap_destroy(*b[i]), *b[i] = (void *)0;
}

static void vp_unarm(void) { m1_timer_stop(&vu.timer); }

static void vp_release(void) { /* the touch is over (or never was): a key held is let go */
    int was = vu.pressed;
    vu.touch = 0, vu.down = K_NONE, vu.pressed = K_NONE;
    if (was && vu.frame) vp_key(was), vp_flush();
}

static int vp_on_background(void *ctx, void *e) {
    (void)e;
    if (!vu.win || ctx != vu.win) return RET_OK;
    vu.fg = 0;
    vp_unarm();
    vp_watch(0); /* covered (another page, or the lock screen as the screen goes dark: no tick runs then) */
    vp_release();
    return RET_OK;
}

static int vp_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!vu.win || ctx != vu.win) return RET_OK;
    vu.fg = 1;
    vp_watch(m1_screen_lit()); /* (before the first look, so the player has a block measured by then) */
    if (!vu.timer) vu.timer = timer_add(vp_first, (void *)0, VN_FIRST_MS);
    return RET_OK;
}

static int vp_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != vu.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    vp_unarm();
    vp_free();
    unlink(VU_FILE); /* nobody watches: the player stops measuring at its next block */
    memset(&vu, 0, sizeof vu);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch
 */
static void vp_local(void *e, int *x, int *y) {
    int pt[2];
    pt[0] = *(int *)((char *)e + PE_X), pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(vu.view, pt);
    *x = pt[0], *y = pt[1];
}

__attribute__((noinline)) int vp_hit(int x, int y) {
    if (x >= 0 && x < VN_CLOSE_X1 && y >= 0 && y < VN_CLOSE_Y1) return K_CLOSE;
    if (y >= VN_BAND_Y0 && y < VN_H && x >= VN_PREV_X0 && x < VN_NEXT_X1)
        return x < VN_PLAY_X0 ? K_PREV : x < VN_NEXT_X0 ? K_PLAY : K_NEXT;
    if (y < VN_BAND_Y0) return K_BODY;
    return K_NONE;
}

/* DOWN, UP and ABORT of the view; nothing else is bound and nothing is grabbed (a MOVE is never consumed here: the stock pull-down from the top edge reads the drag itself). */
static int vp_on_touch(void *ctx, void *e) {
    int type, x, y;
    (void)ctx;
    if (!e || !vu.win) return RET_OK;
    type = *(int *)e;
    if (type == EVT_POINTER_DOWN) {
        vp_release();
        vp_local(e, &x, &y);
        vu.touch = 1, vu.sx = x, vu.sy = y, vu.down = vp_hit(x, y);
        if (vu.down >= K_PREV && vu.down <= K_NEXT) vu.pressed = vu.down, vp_key(vu.down), vp_flush();
    } else if (type == EVT_POINTER_UP && vu.touch) {
        int dx, dy, down = vu.down, hit;
        vp_local(e, &x, &y);
        dx = x - vu.sx, dy = y - vu.sy, hit = vp_hit(x, y);
        vp_release();
        if (hit != down) return RET_OK; /* the finger left what it began on: nothing */
        if (down == K_CLOSE) {
            navigator_back();
            return RET_OK;
        }
        if (down == K_BODY && ((dx < 0 ? -dx : dx) >= VN_TAP_PX || (dy < 0 ? -dy : dy) >= VN_TAP_PX)) return RET_OK;
        if (down == K_BODY && vu.idle) {
            navigator_back();
            return RET_OK;
        }
        if (down == K_PLAY || down == K_BODY)
            playpause_quick_click();
        else if (down == K_NEXT)
            next_quick_click(
                e, 0); /* the click's own event: stock reads its time and ignores a click within 1 s of the last */
        else if (down == K_PREV)
            prev_quick_click(e, 0);
        else
            return RET_OK;
        vp_update(0); /* the page looks again at once: the key's glyph follows without waiting a tick */
        vp_retime();
    } else if (type == EVT_POINTER_ABORT) {
        vp_release();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The mark, open
 */
/* The file the player's tap looks for: just the magic (the player writes the record over it); 1 when it was made. */
static int vp_mark(void) {
    void *f = fopen(VU_FILE, "wb");
    if (!f) return 0;
    fwrite(VU_MAGIC, 1, 8, f);
    fclose(f);
    return 1;
}

/* The mark exists while the page is in front and the screen is lit: nobody sees the needles otherwise, so the player does not measure. Acts only on a change;
 * a mark that could not be made is not remembered, so the next call tries again. */
static void vp_watch(int on) {
    on = on != 0;
    if (on == vu.watch) return;
    if (on) {
        if (!vp_mark()) return;
    } else
        unlink(VU_FILE);
    vu.watch = on;
}

/* Demo starts: a mark left by an earlier run (the page closed by a crash, the player kept measuring) goes; /tmp is empty after a reboot anyway. Called from home_boot. */
void vupage_boot(void) { unlink(VU_FILE); }

/* Open: the page. 0 once it is up (or already open); -1 when it could not open (nothing is left of it). */
int vupage_open(void) {
    if (vu.win) return 0;
    memset(&vu, 0, sizeof vu);
    /* the reference starts again at every open, and stays over track changes */
    vp_lv.lt = VP_LT0;
    vp_lv.peg = vp_lv.fast = 0;
    vu.win = window_open("m1plus_vu");
    if (!vu.win) {
        memset(&vu, 0, sizeof vu);
        return -1;
    }
    widget_on(vu.win, EVT_DESTROY, vp_on_destroy, vu.win);
    vu.view = widget_lookup(vu.win, "vu_view", 1);
    vu.title = widget_lookup(vu.win, "vu_title", 1);
    vu.artist = widget_lookup(vu.win, "vu_artist", 1);
    vu.times = widget_lookup(vu.win, "vu_times", 1);
    vu.status = widget_lookup(vu.win, "vu_status", 1);
    if (vu.view && vu.title && vu.artist && vu.times && vu.status) {
        unsigned *f;
        vu.base = m1_asset_rgba(vu.win, "vu_base", VN_W, VN_H, 0);
        vu.keys = m1_asset_rgba(vu.win, "vu_keys", VN_KEYS_W, VN_BAND_Y1 - VN_BAND_Y0, 0);
        vu.hood = m1_asset_rgba(vu.win, "vu_hood", VU_HOOD_W, VU_HOOD_H, 0);
        vu.lamp = m1_asset_rgba(vu.win, "vu_lamp", VU_LAMP_W, VU_LAMP_H, 0);
        vu.frame = bitmap_create_ex(VN_W, VN_H, VN_W * 4, BITMAP_RGBA8888);
        f = vu.frame && vu.base && vu.keys && vu.hood && vu.lamp ? (unsigned *)bitmap_lock_buffer_for_write(vu.frame)
                                                                 : (unsigned *)0;
        if (f) {
            const unsigned *b = (const unsigned *)bitmap_lock_buffer_for_read(vu.base);
            if (b) {
                memcpy(f, b, (unsigned)VN_W * VN_H * 4);
                bitmap_unlock_buffer(vu.base);
            }
            bitmap_unlock_buffer(vu.frame);
            if (!b) f = (unsigned *)0;
        }
        if (f) {
            int i;
            vu.fg = 1;
            vu.key = ~0u;
            vu.playkey = -1;
            for (i = 0; i < 2; ++i) vu.m[i].x = vu.m[i].tgt = VP_REST, vu.m[i].v = VP_KICK;
            widget_on(vu.win, EVT_WINDOW_TO_BG, vp_on_background, vu.win);
            widget_on(vu.win, EVT_WINDOW_TO_FG, vp_on_foreground, vu.win);
            widget_on(vu.view, EVT_POINTER_DOWN, vp_on_touch, (void *)0);
            widget_on(vu.view, EVT_POINTER_UP, vp_on_touch, (void *)0);
            widget_on(vu.view, EVT_POINTER_ABORT, vp_on_touch, (void *)0);
            widget_on(vu.view, EVT_AFTER_PAINT, vp_on_paint, (void *)0);
            vp_watch(
                m1_screen_lit()); /* the player's tap measures from here while the screen is lit, until the page is destroyed */
            vu.timer = timer_add(vp_first, (void *)0, VN_FIRST_MS);
            return 0;
        }
    }
    vp_free(); /* an asset that is not ours, or no memory: the window goes again */
    vu.win = (void *)0; /* (its destroy handler leaves a newer page alone) */
    navigator_back();
    memset(&vu, 0, sizeof vu);
    return -1;
}

/* Open for Now Playing's idle timer: as vupage_open, and a tap on the page then closes it like the chevron. A page that is already open is left as it is, flag included. */
int vupage_open_idle(void) {
    int was = vu.win != (void *)0, r = vupage_open();
    if (!was && r == 0) vu.idle = 1;
    return r;
}

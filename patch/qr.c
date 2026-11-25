/* The QR code of the Wi-Fi Transfer page's address (docs/modules/wifi-transfer.md "QR code"): a line-for-line port of tools/qr.py, which the tests run beside it.
 *
 * One symbol size only: version 2 (25 x 25 modules), level M, one alphanumeric segment of at most QR_MAX characters, so "HTTP://255.255.255.255:8888" (27) always fits.
 * The steps and the mask penalty follow ISO/IEC 18004 as Project Nayuki's QR Code generator (MIT) implements them; this is a fresh, reduced implementation, not a copy.
 * Pure: no stock call, no allocation, about 1.3 KB of stack. */
#include "entries.h"

#define QR_N QR_SIZE
#define QR_DATA_CW 28
#define QR_EC_CW 16
#define QR_CW (QR_DATA_CW + QR_EC_CW)
#define QR_ALIGN 18
#define QR_MAX 38

struct qr {
    unsigned char mod[QR_N][QR_N]; /* 1 dark */
    unsigned char fn[QR_N][QR_N]; /* 1: a function module (finder, timing, alignment, format) */
};

static int qr_alnum(int c) {
    static const char set[] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:";
    int i;
    for (i = 0; i < 45; ++i)
        if (set[i] == c) return i;
    return -1;
}

static unsigned qr_gf_mul(unsigned a, unsigned b) {
    unsigned z = 0;
    int i;
    for (i = 7; i >= 0; --i) {
        z = (z << 1) ^ ((z >> 7) * 0x11d);
        z ^= ((b >> i) & 1) * a;
    }
    return z & 0xff;
}

/* The 44 codewords of text, or 0 when it is not alphanumeric or too long. */
static int qr_codewords(const char *text, unsigned char *cw) {
    unsigned char div[QR_EC_CW], rem[QR_EC_CW];
    unsigned bit = 0, root = 1, n = 0, i, j;
    unsigned char pad = 0xec;
    while (text[n]) {
        if (n >= QR_MAX || qr_alnum((unsigned char)text[n]) < 0) return 0;
        ++n;
    }
    for (i = 0; i < QR_CW; ++i) cw[i] = 0;
#define PUT(v, nb) \
    do { \
        int k_; \
        for (k_ = (nb) - 1; k_ >= 0; --k_, ++bit) \
            if (((v) >> k_) & 1) cw[bit >> 3] |= (unsigned char)(0x80 >> (bit & 7)); \
    } while (0)
    PUT(2u, 4);
    PUT(n, 9);
    for (i = 0; i + 1 < n; i += 2)
        PUT((unsigned)(qr_alnum((unsigned char)text[i]) * 45 + qr_alnum((unsigned char)text[i + 1])), 11);
    if (n & 1) PUT((unsigned)qr_alnum((unsigned char)text[n - 1]), 6);
#undef PUT
    bit += QR_DATA_CW * 8 - bit < 4 ? QR_DATA_CW * 8 - bit : 4; /* the terminator (zeros) */
    for (i = (bit + 7) >> 3; i < QR_DATA_CW; ++i) cw[i] = pad, pad ^= 0xec ^ 0x11;
    /* the Reed-Solomon divisor of degree 16 and the remainder of the data */
    for (i = 0; i < QR_EC_CW; ++i) div[i] = 0, rem[i] = 0;
    div[QR_EC_CW - 1] = 1;
    for (i = 0; i < QR_EC_CW; ++i) {
        for (j = 0; j < QR_EC_CW; ++j) {
            div[j] = (unsigned char)qr_gf_mul(div[j], root);
            if (j + 1 < QR_EC_CW) div[j] ^= div[j + 1];
        }
        root = qr_gf_mul(root, 2);
    }
    for (i = 0; i < QR_DATA_CW; ++i) {
        unsigned f = cw[i] ^ rem[0];
        for (j = 0; j + 1 < QR_EC_CW; ++j) rem[j] = rem[j + 1];
        rem[QR_EC_CW - 1] = 0;
        for (j = 0; j < QR_EC_CW; ++j) rem[j] ^= (unsigned char)qr_gf_mul(div[j], f);
    }
    for (i = 0; i < QR_EC_CW; ++i) cw[QR_DATA_CW + i] = rem[i];
    return 1;
}

static void qr_fn(struct qr *q, int x, int y, int dark) {
    q->mod[y][x] = (unsigned char)(dark != 0);
    q->fn[y][x] = 1;
}

static void qr_format(struct qr *q, int mask) {
    unsigned data = (unsigned)mask, rem = data, b; /* level M's two bits are 00 */
    int i;
    for (i = 0; i < 10; ++i) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
    b = (data << 10 | rem) ^ 0x5412;
    for (i = 0; i < 6; ++i) qr_fn(q, 8, i, (b >> i) & 1);
    qr_fn(q, 8, 7, (b >> 6) & 1);
    qr_fn(q, 8, 8, (b >> 7) & 1);
    qr_fn(q, 7, 8, (b >> 8) & 1);
    for (i = 9; i < 15; ++i) qr_fn(q, 14 - i, 8, (b >> i) & 1);
    for (i = 0; i < 8; ++i) qr_fn(q, QR_N - 1 - i, 8, (b >> i) & 1);
    for (i = 8; i < 15; ++i) qr_fn(q, 8, QR_N - 15 + i, (b >> i) & 1);
    qr_fn(q, 8, QR_N - 8, 1);
}

static int qr_abs(int v) { return v < 0 ? -v : v; }

static void qr_patterns(struct qr *q) {
    static const unsigned char fc[3][2] = {{3, 3}, {QR_N - 4, 3}, {3, QR_N - 4}};
    int i, k, dx, dy;
    for (i = 0; i < QR_N; ++i) qr_fn(q, 6, i, !(i & 1)), qr_fn(q, i, 6, !(i & 1));
    for (k = 0; k < 3; ++k)
        for (dy = -4; dy <= 4; ++dy)
            for (dx = -4; dx <= 4; ++dx) {
                int x = fc[k][0] + dx, y = fc[k][1] + dy, d = qr_abs(dx) > qr_abs(dy) ? qr_abs(dx) : qr_abs(dy);
                if (x >= 0 && x < QR_N && y >= 0 && y < QR_N) qr_fn(q, x, y, d != 2 && d != 4);
            }
    for (dy = -2; dy <= 2; ++dy)
        for (dx = -2; dx <= 2; ++dx)
            qr_fn(q, QR_ALIGN + dx, QR_ALIGN + dy, (qr_abs(dx) > qr_abs(dy) ? qr_abs(dx) : qr_abs(dy)) != 1);
    qr_format(q, 0);
}

static void qr_place(struct qr *q, const unsigned char *cw) {
    int right, vert, j, i = 0;
    for (right = QR_N - 1; right >= 1; right -= 2) {
        if (right == 6) right = 5;
        for (vert = 0; vert < QR_N; ++vert)
            for (j = 0; j < 2; ++j) {
                int x = right - j, y = ((right + 1) & 2) == 0 ? QR_N - 1 - vert : vert;
                if (!q->fn[y][x] && i < QR_CW * 8) {
                    q->mod[y][x] = (unsigned char)((cw[i >> 3] >> (7 - (i & 7))) & 1);
                    ++i;
                }
            }
    }
}

static int qr_masked(int m, int x, int y) {
    switch (m) {
    case 0:
        return (x + y) % 2 == 0;
    case 1:
        return y % 2 == 0;
    case 2:
        return x % 3 == 0;
    case 3:
        return (x + y) % 3 == 0;
    case 4:
        return (x / 3 + y / 2) % 2 == 0;
    case 5:
        return x * y % 2 + x * y % 3 == 0;
    case 6:
        return (x * y % 2 + x * y % 3) % 2 == 0;
    default:
        return ((x + y) % 2 + x * y % 3) % 2 == 0;
    }
}

static void qr_apply(struct qr *q, int m) {
    int x, y;
    for (y = 0; y < QR_N; ++y)
        for (x = 0; x < QR_N; ++x)
            if (!q->fn[y][x] && qr_masked(m, x, y)) q->mod[y][x] ^= 1;
}

static void qr_hist(int run, int *h) {
    int i;
    if (h[0] == 0) run += QR_N; /* the light border before the first run */
    for (i = 6; i > 0; --i) h[i] = h[i - 1];
    h[0] = run;
}

static int qr_finders(const int *h) {
    int n = h[1], core = n > 0 && h[2] == n && h[4] == n && h[5] == n && h[3] == n * 3;
    return (core && h[0] >= n * 4 && h[6] >= n) + (core && h[6] >= n * 4 && h[0] >= n);
}

/* Line k of the 50 (rows, then columns), module i. */
#define QR_AT(q, k, i) ((k) < QR_N ? (q)->mod[k][i] : (q)->mod[i][(k) - QR_N])

static int qr_penalty(const struct qr *q) {
    int score = 0, k, i, x, y, dark = 0, total = QR_N * QR_N, d;
    for (k = 0; k < 2 * QR_N; ++k) {
        int color = 0, run = 0, h[7] = {0, 0, 0, 0, 0, 0, 0};
        for (i = 0; i < QR_N; ++i) {
            int v = QR_AT(q, k, i);
            if (v == color) {
                ++run;
                if (run == 5)
                    score += 3;
                else if (run > 5)
                    ++score;
            } else {
                qr_hist(run, h);
                if (!color) score += qr_finders(h) * 40;
                color = v, run = 1;
            }
        }
        if (color) qr_hist(run, h), run = 0;
        qr_hist(run + QR_N, h);
        score += qr_finders(h) * 40;
    }
    for (y = 0; y + 1 < QR_N; ++y)
        for (x = 0; x + 1 < QR_N; ++x) {
            int c = q->mod[y][x];
            if (c == q->mod[y][x + 1] && c == q->mod[y + 1][x] && c == q->mod[y + 1][x + 1]) score += 3;
        }
    for (y = 0; y < QR_N; ++y)
        for (x = 0; x < QR_N; ++x) dark += q->mod[y][x];
    d = dark * 20 - total * 10;
    return score + ((qr_abs(d) + total - 1) / total - 1) * 10;
}

int qr_make(const char *text, int mask, unsigned char *bits) {
    struct qr q;
    unsigned char cw[QR_CW];
    int x, y, m, best = -1, best_p = 0;
    if (!text || !bits || mask > 7 || !qr_codewords(text, cw)) return 0;
    for (y = 0; y < QR_N; ++y)
        for (x = 0; x < QR_N; ++x) q.mod[y][x] = 0, q.fn[y][x] = 0;
    qr_patterns(&q);
    qr_place(&q, cw);
    if (mask < 0) {
        for (m = 0; m < 8; ++m) {
            int p;
            qr_apply(&q, m);
            qr_format(&q, m);
            p = qr_penalty(&q);
            if (best < 0 || p < best_p) best = m, best_p = p;
            qr_apply(&q, m);
        }
        mask = best;
    }
    qr_apply(&q, mask);
    qr_format(&q, mask);
    for (x = 0; x < QR_BYTES; ++x) bits[x] = 0;
    for (y = 0; y < QR_N; ++y)
        for (x = 0; x < QR_N; ++x)
            if (q.mod[y][x]) bits[(y * QR_N + x) >> 3] |= (unsigned char)(0x80 >> ((y * QR_N + x) & 7));
    return QR_N;
}

/* M1+ Music parametric EQ: the APO / AutoEQ parser, the state record and the biquad DSP (patch/peq.h, docs/modules/peq.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The parser, the RBJ designs, Auto preamp and the ramped engine are q2-pod's patch/peq.c (Copyright (c) 2026 Diamond Bond,
 * MIT licence), kept as it has them; the state record and the graphic EQ preset are this project's.
 */
#include "peq.h"
#ifndef PEQ_PLAYER
#include "offsets.inc"
#include "common.h"
#endif

static int between(double x, double lo, double hi) { return __builtin_isfinite(x) && x >= lo && x <= hi; }

void peq_default(peq_preset *p) {
    static const double frequencies[10] = {31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
    memset(p, 0, sizeof(*p));
    p->count = 10;
    p->bypass = 1;
    for (int i = 0; i < PEQ_BANDS; ++i) {
        p->bands[i].frequency = i < 10 ? frequencies[i] : 1000;
        p->bands[i].q = 1.41; /* one octave wide, as graphic EQs use */
    }
}

static int valid_band(const peq_band *b) {
    return b->enabled >= 0 && b->enabled <= 3 && b->type >= 0 && b->type <= 2 && between(b->frequency, 20, 20000) &&
           between(b->gain, -24, 24) && between(b->q, 0.1, 10);
}

int peq_valid(const peq_preset *p) {
    if (!p || p->count < 0 || p->count > PEQ_BANDS || (p->bypass != 0 && p->bypass != 1) ||
        !between(p->preamp, -60, 24) || !between(p->balance, -12, 12) || (unsigned)p->automatic > 2)
        return 0;
    for (int i = 0; i < p->count; ++i)
        if (!valid_band(&p->bands[i])) return 0;
    return 1;
}

#ifndef PEQ_PLAYER /* the parser is demo's: the player reads the parsed record */
static int error_at(peq_error *e, unsigned line, const char *reason) {
    if (e) {
        e->line = line;
        e->reason = reason;
        e->skipped = 0;
    }
    return 0;
}

/* Decimal only (comma accepted as the mark, like APO); no hex floats, expressions, NaN or infinity.
 * libc reads the value, and the token must be consumed whole (demo imports __isoc99_sscanf, not strtod). */
int peq_number(const char *s, double *out) {
    char buf[PEQ_LINE_LIMIT + 1];
    unsigned n = 0;
    while (s[n]) {
        if (n == PEQ_LINE_LIMIT) return 0;
        char c = s[n];
        if (!(c >= '0' && c <= '9') && c != '+' && c != '-' && c != '.' && c != ',' && c != 'e' && c != 'E') return 0;
        buf[n] = c == ',' ? '.' : c;
        ++n;
    }
    buf[n] = 0;
    const char *p = buf + (buf[0] == '+' || buf[0] == '-');
    if (!n || (p[0] == '0' && (p[1] | 32) == 'x')) return 0; /* no hex floats */
    int len = 0;
    double v;
    if (__isoc99_sscanf(buf, "%lf%n", &v, &len) != 1 || len != (int)n || !__builtin_isfinite(v)) return 0;
    *out = v;
    return 1;
}

int peq_parse(const char *text, unsigned size, peq_preset *out, peq_error *error) {
    peq_preset p;
    peq_default(&p);
    p.count = 0;
    p.bypass = 0;
    unsigned pos = 0, line = 0, preamp_line = 0;
    int scope =
        1; /* APO Channel: 1 both, 2 left, 3 right, as peq_band.enabled; 4 a channel set this engine has no band for (what follows is skipped) */
    unsigned skipped =
        0; /* the lines left out: a command, a filter type or a channel the engine does not have (docs/modules/peq.md "The parser") */
    double side[4] = {0}; /* Preamp under Channel: L or R */
    if (size > PEQ_FILE_LIMIT) return error_at(error, 1, "file exceeds 16384 bytes");
    if (size >= 3 && (unsigned char)text[0] == 239 && (unsigned char)text[1] == 187 && (unsigned char)text[2] == 191)
        pos = 3;
    while (pos < size) {
        char buf[PEQ_LINE_LIMIT + 1], *t[16];
        unsigned length = 0;
        ++line;
        while (pos < size && text[pos] != '\n') {
            if (length == PEQ_LINE_LIMIT) return error_at(error, line, "line exceeds 512 bytes");
            if (!text[pos]) return error_at(error, line, "embedded NUL");
            buf[length++] = text[pos++];
        }
        if (pos < size) ++pos;
        buf[length] = 0;
        int n = 0, over = 0;
        char *s = buf;
        while (*s && *s != '#') {
            if (*s == ' ' || *s == '\t' || *s == '\r') {
                ++s;
                continue;
            }
            if (n == 16) { /* more tokens than any form has: refused below when the line is one of ours, else skipped */
                over = 1;
                break;
            }
            /* A colon is a separate token, even in "Filter 1:" and "Preamp:". */
            if (*s == ':') {
                t[n++] = ":";
                ++s;
                continue;
            }
            t[n++] = s;
            while (*s && *s != ' ' && *s != '\t' && *s != '\r' && *s != ':' && *s != '#') ++s;
            char delimiter = *s;
            if (*s) *s++ = 0;
            if (delimiter == ':') {
                if (n == 16) {
                    over = 1;
                    break;
                }
                t[n++] = ":";
            }
            if (delimiter == '#') break;
        }
        if (!n) continue;
        if (over &&
            (!strcmp(t[0], "Preamp") || !strcmp(t[0], "Channel"))) /* (a Filter line is judged by its type below) */
            return error_at(error, line, "unsupported filter form");
        if (!strcmp(t[0], "Preamp")) {
            double gain;
            if (n != 4 || strcmp(t[1], ":") || strcmp(t[3], "dB"))
                return error_at(error, line, "expected Preamp: <gain> dB");
            if (!peq_number(t[2], &gain) || !between(gain, -60, 24))
                return error_at(error, line, "preamp outside -60..24 dB or invalid number");
            if (scope == 4) { /* a preamp of a channel the engine does not have */
                ++skipped;
                continue;
            }
            if (scope == 1)
                p.preamp += gain;
            else
                side[scope] += gain;
            preamp_line = line;
            continue;
        }
        if (!strcmp(t[0], "Channel")) {
            int l = 0, r = 0, other = 0;
            if (n < 3 || strcmp(t[1], ":")) return error_at(error, line, "expected Channel: L, R or all");
            for (int i = 2; i < n; ++i) {
                if (!strcmp(t[i], "L"))
                    l = 1;
                else if (!strcmp(t[i], "R"))
                    r = 1;
                else if (!strcmp(t[i], "all"))
                    l = r = 1;
                else
                    other = 1; /* C, LFE, SL, SR ...: no band for them, the filters that follow are skipped */
            }
            scope = other ? 4 : l && r ? 1 : l ? 2 : 3;
            continue;
        }
        if (strcmp(t[0], "Filter")) { /* Device:, Include:, Copy:, GraphicEQ: ... */
            ++skipped;
            continue;
        }
        int k = 1;
        if (n > 1 && strcmp(t[1], ":")) {
            for (s = t[1]; *s; ++s)
                if (*s < '0' || *s > '9') return error_at(error, line, "invalid filter label");
            ++k;
        }
        if (n <= k || strcmp(t[k++], ":")) return error_at(error, line, "expected Filter [number]:");
        if (n - k == 2 && !strcmp(t[k + 1], "None")) continue; /* REW/APO empty slot */
        if (n - k < 2) return error_at(error, line, "unsupported filter form");
        peq_band b = {0, 0, 0, 0, 0.7071067811865476};
        if (!strcmp(t[k], "ON"))
            b.enabled = scope;
        else if (strcmp(t[k], "OFF"))
            return error_at(error, line, "expected ON or OFF");
        int type = !strcmp(t[k + 1], "PK") || !strcmp(t[k + 1], "PEQ")   ? 0
                   : !strcmp(t[k + 1], "LS") || !strcmp(t[k + 1], "LSC") ? 1
                   : !strcmp(t[k + 1], "HS") || !strcmp(t[k + 1], "HSC") ? 2
                                                                         : -1;
        if (type < 0 ||
            scope ==
                4) { /* LP, HP, BP, NO, AP, LSQ ... or a channel with no band: left out (an OFF one was never there) */
            if (b.enabled) ++skipped;
            continue;
        }
        if (n - k != 8 && n - k != 10) return error_at(error, line, "unsupported filter form");
        b.type = type;
        ++k;
        int corner = !t[k][2]; /* APO: LS/HS take a corner frequency, LSC/HSC the centre */
        ++k;
        if (strcmp(t[k], "Fc") || strcmp(t[k + 2], "Hz") || strcmp(t[k + 3], "Gain") || strcmp(t[k + 5], "dB"))
            return error_at(error, line, "expected Fc <Hz> Hz Gain <dB> dB");
        if (!peq_number(t[k + 1], &b.frequency) || !peq_number(t[k + 4], &b.gain))
            return error_at(error, line, "invalid frequency or gain number");
        k += 6;
        if (k < n) {
            if (strcmp(t[k], "Q") || !peq_number(t[k + 1], &b.q)) return error_at(error, line, "expected Q <number>");
        } else if (!b.type)
            return error_at(error, line, "peaking filter requires Q");
        if (b.type && valid_band(&b)) {
            /* Match Equalizer APO: no Q means slope 0.9 at Fc; LS/HS with Q shift the corner to the centre. */
            double a = pow(10, b.gain / 40), ab = a + 1 / a;
            if (k >= n)
                b.q = 1 / __builtin_sqrt(ab * (1 / 0.9 - 1) + 2);
            else if (corner) {
                double f = pow(10, __builtin_fabs(b.gain) / 80 * ((1 / (b.q * b.q) - 2) / ab + 1));
                b.frequency = b.type == 1 ? b.frequency * f : b.frequency / f;
                /* The shift can leave 20..20000 Hz; clamp instead of rejecting the whole file. */
                if (b.frequency > 20000) b.frequency = 20000;
                if (b.frequency < 20) b.frequency = 20;
            }
        }
        if (!valid_band(&b)) {
            if (!b.enabled) continue; /* APO ignores OFF filters; exporters fill blank slots with Fc 0 Q 0 */
            return error_at(error, line, "range: 20..20000 Hz, -24..24 dB, Q 0.1..10");
        }
        if (p.count == PEQ_BANDS) return error_at(error, line, "more than 64 bands");
        p.bands[p.count++] = b;
    }
    int usable = 0;
    for (int i = 0; i < p.count; ++i) usable += p.bands[i].enabled != 0;
    if (!usable)
        return error_at(error, 0, "no usable filter"); /* nothing ON that the engine has: a flat curve is no preset */
    /* Per-channel preamps become the louder one's common preamp plus a balance that turns the other down. */
    p.preamp += side[2] > side[3] ? side[2] : side[3];
    p.balance = side[3] - side[2];
    if (!between(p.preamp, -60, 24)) return error_at(error, preamp_line, "summed preamp outside -60..24 dB");
    if (!between(p.balance, -12, 12)) return error_at(error, preamp_line, "L/R preamp differ by more than 12 dB");
    p.automatic = preamp_line ? 2 : 1; /* the file's preamp; without one, Auto */
    *out = p; /* Commit only after the complete file validates. */
    if (error) {
        error->line = 0;
        error->reason = 0;
        error->skipped = skipped;
    }
    return 1;
}

int peq_import_file(const char *path, peq_preset *out, peq_error *error) {
    char *text = calloc(1, PEQ_FILE_LIMIT + 1);
    if (!text) return error_at(error, 1, "out of memory");
    void *f = fopen(path, "rb");
    if (!f) {
        free(text);
        return error_at(error, 1, "cannot open file");
    }
    unsigned n = fread(text, 1, PEQ_FILE_LIMIT + 1, f);
    int bad = ferror(f);
    if (fclose(f)) bad = 1;
    int ok = bad ? error_at(error, 1, "file read failed") : peq_parse(text, n, out, error);
    free(text);
    return ok;
}
#endif

static int state_valid(const peq_state *s) {
    unsigned n = 0;
    while (n < PEQ_NAME && s->name[n]) ++n;
    if (!((s->mode == PEQ_TENBAND_MODE || s->mode == PEQ_FILE) && n < PEQ_NAME && peq_valid(&s->preset))) return 0;
    if (s->curve < 0 || s->curve >= PEQ_CURVES || s->preamp < PEQ_PREAMP_AUTO || s->preamp > PEQ_GAIN_MAX) return 0;
    for (int i = 0; i < PEQ_TENBAND; ++i)
        if (!between(s->gain[i], -PEQ_GAIN_MAX, PEQ_GAIN_MAX) || !between(s->custom[i], -PEQ_GAIN_MAX, PEQ_GAIN_MAX))
            return 0;
    return 1;
}

/* The record 1.8.1 shipped (M1PEQ02, 1160 bytes): the same fields with 30 bands. Read once and saved as PEQ_MAGIC on the next
 * save, so an update keeps each output's choice. Temporary: drop it a few releases after 1.8.1. */
#define PEQ_MAGIC_02 "M1PEQ02"
#define PEQ_BANDS_02 30
typedef struct {
    int mode;
    struct {
        int count, bypass;
        double preamp;
        peq_band bands[PEQ_BANDS_02];
        double balance;
        int automatic, spare;
    } preset;
    char name[PEQ_NAME];
    int curve, preamp;
    float gain[PEQ_TENBAND], custom[PEQ_TENBAND];
} peq_state_02;

static int magic_is(const char *have, const char *want) {
    for (unsigned i = 0; i < 8; ++i)
        if (have[i] != want[i]) return 0; /* the 7 letters and the NUL */
    return 1;
}

static void state_from_02(const peq_state_02 *o, peq_state *s) {
    s->mode = o->mode;
    s->preset.count = o->preset.count;
    s->preset.bypass = o->preset.bypass;
    s->preset.preamp = o->preset.preamp;
    memcpy(s->preset.bands, o->preset.bands, sizeof(o->preset.bands));
    s->preset.balance = o->preset.balance;
    s->preset.automatic = o->preset.automatic;
    s->preset.spare = o->preset.spare;
    memcpy(s->name, o->name, sizeof(s->name));
    s->curve = o->curve;
    s->preamp = o->preamp;
    memcpy(s->gain, o->gain, sizeof(s->gain));
    memcpy(s->custom, o->custom, sizeof(s->custom));
}

static void state_none(peq_state *s) {
    memset(s, 0, sizeof(*s));
    peq_default(&s->preset);
    s->preamp = PEQ_PREAMP_AUTO; /* none readable: Flat (the zeros), Auto */
}

int peq_state_load_from(const char *path, peq_state *s) {
    union {
        struct {
            char magic[8];
            peq_state s;
        } cur;
        struct {
            char magic[8];
            peq_state_02 s;
        } old;
    } file;
    char extra;
    state_none(s);
    void *f = fopen(path, "rb");
    if (!f) return 0;
    memset(&file, 0, sizeof(file));
    unsigned n = fread(&file, 1, sizeof(file.cur), f);
    int ok = fread(&extra, 1, 1, f) == 0;
    if (fclose(f)) ok = 0;
    if (!ok) return 0;
    if (n == sizeof(file.cur) && magic_is(file.cur.magic, PEQ_MAGIC))
        *s = file.cur.s;
    else if (n == sizeof(file.old) && magic_is(file.old.magic, PEQ_MAGIC_02) && file.old.s.preset.count >= 0 &&
             file.old.s.preset.count <= PEQ_BANDS_02)
        state_from_02(&file.old.s, s);
    else
        return 0;
    if (state_valid(s)) return 1;
    state_none(s);
    return 0;
}
int peq_state_load(peq_state *s) { return peq_state_load_from(PEQ_STATE, s); }

#ifndef PEQ_PLAYER
/* PEQ_MAGIC then the record, fsynced under path.tmp and renamed over path (demo only; peq_state_save is PEQ_STATE: the file the player reads). */
int peq_state_save_to(const char *path, const peq_state *s) {
    struct {
        char magic[8];
        peq_state s;
    } file;
    if (!state_valid(s)) return -1;
    memcpy(file.magic, PEQ_MAGIC, 8);
    file.s = *s;
    if (m1_save(path, 0644, &file, sizeof file)) return 0;
    return mkdir(PEQ_STATE_DIR, 0755) == 0 && m1_save(path, 0644, &file, sizeof file) ? 0 : -1;
}
int peq_state_save(const peq_state *s) { return peq_state_save_to(PEQ_STATE, s); }
#endif

void peq_tenband(peq_preset *p, const float *gain, int preamp) {
    peq_default(p);
    p->bypass = 0;
    p->automatic = preamp == PEQ_PREAMP_AUTO ? 1 : 2;
    p->preamp = preamp > 0 && preamp <= PEQ_GAIN_MAX ? -preamp : 0;
    for (int i = 0; i < PEQ_TENBAND; ++i) {
        double g = gain[i];
        p->bands[i].gain = between(g, -PEQ_GAIN_MAX, PEQ_GAIN_MAX) ? g : 0;
        p->bands[i].enabled = 1;
    }
}

/* The preamp, linear, on every channel, then balance turning one side down. */
static void level(peq_engine *e, double gain, double balance) {
    for (int ch = 0; ch < PEQ_CHANNELS; ++ch) e->gain[ch] = gain;
    if (balance > 0) e->gain[0] *= pow(10, -balance / 20);
    if (balance < 0) e->gain[1] *= pow(10, balance / 20);
}

/* RBJ peaking and Q-form shelves. All design work is outside the PCM callback. */
int peq_compile(const peq_preset *p, int rate, peq_engine *out) {
    peq_engine e;
    memset(&e, 0, sizeof(e));
    if (!peq_valid(p) || rate < 8000 || rate > 384000) return 0;
    level(&e, pow(10, p->preamp / 20), p->balance);
    e.bypass = p->bypass;
    for (int i = 0; i < PEQ_BANDS; ++i) {
        e.c[i].b0 = 1;
        if (i >= p->count || !p->bands[i].enabled || !p->bands[i].gain) continue;
        e.used = i + 1;
        if (p->bands[i].enabled > 1) e.only[i] = p->bands[i].enabled - 1;
        const peq_band *b = &p->bands[i];
        if (b->frequency >= rate * 0.5) continue; /* not representable at this rate; skip only this band */
        double a = pow(10, b->gain / 40), w = 6.283185307179586 * b->frequency / rate;
        double c = cos(w), alpha = sin(w) / (2 * b->q), r = 2 * __builtin_sqrt(a) * alpha;
        double b0, b1, b2, a0, a1, a2;
        if (!b->type) {
            b0 = 1 + alpha * a;
            b1 = -2 * c;
            b2 = 1 - alpha * a;
            a0 = 1 + alpha / a;
            a1 = -2 * c;
            a2 = 1 - alpha / a;
        } else if (b->type == 1) {
            b0 = a * ((a + 1) - (a - 1) * c + r);
            b1 = 2 * a * ((a - 1) - (a + 1) * c);
            b2 = a * ((a + 1) - (a - 1) * c - r);
            a0 = (a + 1) + (a - 1) * c + r;
            a1 = -2 * ((a - 1) + (a + 1) * c);
            a2 = (a + 1) + (a - 1) * c - r;
        } else {
            b0 = a * ((a + 1) + (a - 1) * c + r);
            b1 = -2 * a * ((a - 1) + (a + 1) * c);
            b2 = a * ((a + 1) + (a - 1) * c - r);
            a0 = (a + 1) - (a - 1) * c + r;
            a1 = 2 * ((a - 1) - (a + 1) * c);
            a2 = (a + 1) - (a - 1) * c - r;
        }
        e.c[i] = (peq_coeff){b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0};
    }
    *out = e;
    return 1;
}

/* |H|^2 of the engine's left and right chains, without preamp or balance. */
void peq_response(const peq_engine *e, int rate, double f, double *l, double *r) {
    double w = 6.283185307179586 * f / rate, c1 = cos(w), s1 = sin(w), c2 = 2 * c1 * c1 - 1, s2 = 2 * s1 * c1;
    *l = *r = 1;
    for (int i = 0; i < e->used; ++i) { /* bands past used are identity */
        const peq_coeff *q = &e->c[i];
        double nr = q->b0 + q->b1 * c1 + q->b2 * c2, ni = q->b1 * s1 + q->b2 * s2;
        double dr = 1 + q->a1 * c1 + q->a2 * c2, di = q->a1 * s1 + q->a2 * s2;
        double m = (nr * nr + ni * ni) / (dr * dr + di * di);
        if (e->only[i] != 2) *l *= m; /* only: 1 left, 2 right */
        if (e->only[i] != 1) *r *= m;
    }
}

/* The loudest |H|^2 of e (p compiled at rate), either channel, at least 1 (Auto never boosts) and
 * at most 60 dB. Includes DC, Nyquist and each band's centre: near Nyquist a peak can be narrower
 * than the grid. Sampled steady-state peaks, not a transient or intersample bound. */
static double peak(const peq_engine *e, const peq_preset *p, int rate) {
    double nyquist = rate * 0.5, best = 1;
    for (int k = -2; k < 1024 + p->count; ++k) {
        double f = k == -2 ? 0 : k == -1 ? nyquist : k < 1024 ? pow(nyquist, k / 1023.0) : p->bands[k - 1024].frequency;
        if (f >= nyquist && k != -1) continue;
        double l, r;
        peq_response(e, rate, f, &l, &r);
        if (l > best) best = l;
        if (r > best) best = r;
    }
    return best < 1.0000230261 ? 1 : best > 1e6 ? 1e6 : best; /* under 0.0001 dB is none */
}

/* The player's engine: Auto (1) takes the cut for this rate's own response, from the coefficients
 * just designed, in place of the saved number. */
static int prepare(const peq_preset *p, int rate, peq_engine *e) {
    if (!peq_compile(p, rate, e)) return 0;
    if (p->automatic == 1) level(e, pow(peak(e, p, rate), -0.5), p->balance);
    return 1;
}

void peq_reset(peq_dsp *d, int rate, int channels, const peq_preset *p) {
    memset(d, 0, sizeof(*d));
    d->rate = rate;
    d->channels = channels;
    d->ramp_length = rate / 50; /* 20 ms */
    if (!prepare(p, rate, &d->current)) d->current.bypass = 1;
}

int peq_update(peq_dsp *d, const peq_preset *p) {
    if (!prepare(p, d->rate, &d->pending)) return 0;
    d->waiting = 1; /* Latest complete update wins; never interrupt an in-flight crossfade. */
    return 1;
}

/* Identity coefficients: with zero memory the band passes x through unchanged. */
static inline __attribute__((always_inline)) int identity(const peq_coeff *c) {
    return c->b0 == 1 && !c->b1 && !c->b2 && !c->a1 && !c->a2;
}

/* The bands sample can act on, in order: identity bands with zero memory stay so until an update. */
static int live(const peq_engine *e, int *list) {
    int n = 0;
    for (int i = 0; i < e->used; ++i) {
        int on = e->only[i] || !identity(&e->c[i]);
        for (int ch = 0; ch < PEQ_CHANNELS && !on; ++ch) on = e->z[ch][i][0] || e->z[ch][i][1];
        if (on) list[n++] = i;
    }
    return n;
}

static double sample(peq_engine *e, const int *list, int n, double x, int ch) {
    if (e->bypass) return x;
    for (int k = 0; k < n; ++k) {
        int i = list[k];
        const peq_coeff *c = &e->c[i];
        double *z = e->z[ch][i];
        /* The other channel's band: drop memory carried from a both-channel version. */
        if (e->only[i] && e->only[i] != ch + 1) {
            z[0] = z[1] = 0;
            continue;
        }
        /* Still checked per sample: a band can drain to idle mid-block. */
        if (identity(c) && !z[0] && !z[1]) continue;
        /* Flush |y| < ~2e-34 to zero: decaying tails would otherwise reach denormals, which MIPS FPUs trap on. */
        double y = c->b0 * x + z[0] + 1e-18 - 1e-18;
        z[0] = c->b1 * x - c->a1 * y + z[1];
        z[1] = c->b2 * x - c->a2 * y;
        x = y;
    }
    return x * e->gain[ch]; /* after the cascade, so filter memory is independent of preamp */
}

void peq_process(peq_dsp *d, float *audio, unsigned frames) {
    if (!audio || d->channels < 1 || d->channels > PEQ_CHANNELS) return;
    if (d->current.bypass && !d->ramp && !d->waiting) return; /* steady bypass leaves the whole block untouched */
    int cur[PEQ_BANDS], nxt[PEQ_BANDS], nc = live(&d->current, cur), nn = d->ramp ? live(&d->next, nxt) : 0;
    for (unsigned i = 0; i < frames; ++i) {
        if (!d->ramp && d->waiting) {
            d->next = d->pending;
            d->waiting = 0;
            d->ramp = d->ramp_length;
            /* Carry filter memory over so unchanged bands and preamp-only edits crossfade without a transient. */
            if (!d->current.bypass) memcpy(d->next.z, d->current.z, sizeof(d->next.z));
            /* Bands dropped from the end still run until their carried memory drains. */
            for (int b = d->next.used; b < d->current.used; ++b)
                for (int ch = 0; ch < PEQ_CHANNELS; ++ch)
                    if (d->next.z[ch][b][0] || d->next.z[ch][b][1]) d->next.used = b + 1;
            nn = live(&d->next, nxt);
        }
        for (int ch = 0; ch < d->channels; ++ch, ++audio) {
            if (!d->ramp && d->current.bypass) continue; /* bit-exact steady bypass */
            double x = *audio;
            if (!__builtin_isfinite(x)) x = 0;
            double y = sample(&d->current, cur, nc, x, ch);
            if (d->ramp) {
                double wet = sample(&d->next, nxt, nn, x, ch);
                double mix = (double)(d->ramp_length - d->ramp + 1) / d->ramp_length;
                y += (wet - y) * mix;
            }
            /* Keep float headroom for downstream volume; the output converter owns full-scale clipping. A stack of big boosts
             * (64 shelves at +24 dB) outgrows float: bound it at PEQ_OUT_MAX, far above any curve a listener plays. */
            if (!__builtin_isfinite(y))
                y = 0;
            else if (y > PEQ_OUT_MAX)
                y = PEQ_OUT_MAX;
            else if (y < -PEQ_OUT_MAX)
                y = -PEQ_OUT_MAX;
            *audio = (float)y;
        }
        if (d->ramp && !--d->ramp) d->current = d->next, nc = nn, memcpy(cur, nxt, sizeof(cur));
    }
}

#ifndef PEQ_PLAYER
/* Stock's genre curves, dB per band: the rows 4..11 of the 12 x 10 float table demo's reset_user_eq copies (0x4d8490: memcpy of
 * 0x1e0 bytes from 0x74b5bc, each entry then stored +6 into the user table 0xa0c588 for set_equalizer_value), in the order of the
 * name table at 0x97c7a0 (eq_pop, eq_rock, eq_dance, eq_blues, eq_metal, eq_vocal, eq_classical, eq_jazz). Rows 0..3 (None and
 * Custom 1..3) are all zero. Read from the V2.1 demo; docs/modules/peq.md "10-Band EQ". Flat is zero, Custom is the record's. */
static const float curves[PEQ_CURVES][PEQ_TENBAND] = {
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 0}, /* Flat */
    {3, 1, 0, -2, -4, -4, -2, 0, 1, 2}, /* Pop */
    {-2, 0, 2, 4, -2, -2, 0, 0, 4, 4}, /* Rock */
    {-2, 3, 4, 1, -2, -2, 0, 0, 4, 4}, /* Dance */
    {-2, 0, 2, 1, 0, 0, 0, 0, -2, -4}, /* Blues */
    {-6, 0, 0, 0, 0, 0, 2, 0, 2, 0}, /* Metal */
    {-4, 0, 2, 1, 0, 0, 0, 0, -4, -6}, /* Vocal */
    {0, 3, 3, 2, 0, 0, 0, 0, 1, 1}, /* Classical */
    {0, 0, 0, 2, 2, 2, 0, 1, 2, 2}, /* Jazz */
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 0}, /* Custom: the record's */
};
void peq_curve_gains(const peq_state *s, int curve, float *out) {
    const float *g = curve == PEQ_CUSTOM                ? s->custom
                     : curve >= 0 && curve < PEQ_CURVES ? curves[curve]
                                                        : curves[PEQ_FLAT];
    for (int i = 0; i < PEQ_TENBAND; ++i) out[i] = g[i];
}
void peq_set_curve(peq_state *s, int curve) {
    if (curve < 0 || curve >= PEQ_CURVES) curve = PEQ_FLAT;
    s->curve = curve;
    peq_curve_gains(s, curve, s->gain);
}

/* the preset page's Auto preamp: what the player plays this preset at with at rate */
/* The preamp, linear, of channel 0 as the player applies it at rate (Auto: this rate's own cut; the file's Preamp otherwise); 1 when the preset does not compile. */
double peq_preamp_gain(const peq_preset *p, int rate) {
    peq_engine *e = calloc(1, sizeof *e);
    double g = 1;
    if (e && prepare(p, rate, e)) g = e->gain[0];
    free(e);
    return g;
}
#endif

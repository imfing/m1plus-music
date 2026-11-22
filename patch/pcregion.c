/* M1+ Music Podcast Region: which Apple Podcasts storefront the search and the Discover charts ask (docs/modules/podcasts.md "Region"; tools/pcregion.py is the model).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The choice is /mnt/data/m1plus/podcast-region: the two capital letters of one of the PCREGION_N storefronts and a line feed. Missing, empty or anything else is Automatic, which takes the UI language's country
 * where one language is one country (ja JP, ko KR, zh_CN CN, zh_HK HK, zh_TW TW, de DE, fr FR, it IT, pl PL, th TH, ru RU, uk UA), for English and Spanish the Settings time zone's place (the stock default,
 * Shanghai, names nothing), else the United States. Nothing here runs at paint: the search and a chart ask when they start, the Settings page when it shows its row.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "i18n.h"
#include "pcregion.h"

static const char *const rg_codes[] = PCREGION_CODES;
static const char *const rg_names[] = PCREGION_NAMES;
static const char *const rg_zones[] = PCREGION_ZONES;
#define RG_ZONES (sizeof rg_zones / sizeof *rg_zones)

static int rg_is(const char *s, char a, char b) { return s[0] == a && s[1] == b && !s[2]; }

static int rg_find(const char *code) {
    int i;
    for (i = 0; i < PCREGION_N; ++i)
        if (code[0] == rg_codes[i][0] && code[1] == rg_codes[i][1] && !code[2]) return i;
    return -1;
}

/* The saved storefront's index into the table, -1 for Automatic: exactly two letters of the table, then nothing or a line feed. */
static int rg_read(void) {
    char b[8];
    int fd = open(PCREGION_FILE, O_RDONLY, 0), n;
    if (fd < 0) return -1;
    n = read(fd, b, sizeof b - 1);
    close(fd);
    if (n == 3 && b[2] == '\n') n = 2;
    if (n != 2) return -1;
    b[2] = 0;
    return rg_find(b);
}

/* The storefront Automatic gives. */
static const char *rg_infer(void) {
    const char *l = locale_info();
    unsigned zone = *(volatile unsigned *)TIME_ZONE;
    if (l) {
        const char *lang = l + LOCALE_LANGUAGE, *cc = l + LOCALE_COUNTRY;
        if (rg_is(lang, 'j', 'a')) return "JP";
        if (rg_is(lang, 'k', 'o')) return "KR";
        if (rg_is(lang, 'z', 'h')) return rg_is(cc, 'H', 'K') ? "HK" : rg_is(cc, 'T', 'W') ? "TW" : "CN";
        if (rg_is(lang, 'g', 'e')) return "DE";
        if (rg_is(lang, 'f', 'r')) return "FR";
        if (rg_is(lang, 'i', 't')) return "IT";
        if (rg_is(lang, 'p', 'o')) return "PL";
        if (rg_is(lang, 't', 'h')) return "TH";
        if (rg_is(lang, 'r', 'u')) return "RU";
        if (rg_is(lang, 'u', 'k')) return "UA";
        if ((rg_is(lang, 'e', 'n') || rg_is(lang, 's', 'p')) && zone < RG_ZONES && rg_zones[zone][0])
            return rg_zones[zone];
    }
    return PCREGION_FALLBACK;
}

const char *pcregion_code(void) {
    int i = rg_read();
    return i >= 0 ? rg_codes[i] : rg_infer();
}

int pcregion_saved(void) { return rg_read() + 1; }

int pcregion_set(int row) {
    char text[4];
    if (row < 0 || row > PCREGION_N) return -1;
    if (row == 0) {
        if (access(PCREGION_FILE, F_OK) == 0 && unlink(PCREGION_FILE) != 0) return -1;
        return 0;
    }
    text[0] = rg_codes[row - 1][0], text[1] = rg_codes[row - 1][1], text[2] = '\n', text[3] = 0;
    return home_write_atomic(PCREGION_FILE, text) == 0 ? row : -1;
}

const char *pcregion_name(const char *code) {
    int i = rg_find(code);
    return i >= 0 ? rg_names[i] : code;
}

void pcregion_value(char *out, unsigned size) {
    int i = rg_read();
    snprintf(out, size, "%s", i >= 0 ? rg_names[i] : TR("Automatic"));
}

void pcregion_auto_label(char *out, unsigned size) {
    snprintf(out, size, "%s (%s)", TR("Automatic"), pcregion_name(rg_infer()));
}

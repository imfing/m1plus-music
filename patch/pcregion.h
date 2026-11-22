/* Podcast Region (patch/pcregion.c, docs/modules/podcasts.md "Region"): the Apple Podcasts storefront the directory search and the Discover charts use.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define PCREGION_FILE \
    "/mnt/data/m1plus/podcast-region" /* Settings > Library > Podcast Region: the storefront's two capital letters and a line feed; missing or anything else = Automatic */
#define PCREGION_FALLBACK "US" /* where Automatic ends up when nothing names a place, and what a chart falls back to */

/* The storefront in use: the saved one, else the one Automatic infers (the UI language's country, for English and Spanish the Settings time zone's, else US). Two capital letters (a static string). */
const char *pcregion_code(void);
/* The picker row of the saved choice: 0 Automatic, 1.. a storefront (tools/pcregion.py CODES order, plus one). */
int pcregion_saved(void);
/* Choose row 0 (Automatic) or 1..PCREGION_N, saved atomically; the row, or -1 when it was not saved (nothing changes) or is not a row. */
int pcregion_set(int row);
/* The English name of a storefront code; the code itself for one that is not in the table. */
const char *pcregion_name(const char *code);
/* The Settings row's value: the chosen storefront's name, or Automatic. */
void pcregion_value(char *out, unsigned size);
/* The picker's first row: "Automatic (United States)", the inferred storefront in brackets. */
void pcregion_auto_label(char *out, unsigned size);

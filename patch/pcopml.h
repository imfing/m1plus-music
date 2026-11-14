/* OPML import and export for the Podcasts subscriptions (patch/pcopml.c; docs/modules/podcasts.md "Subscriptions and OPML").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The input of po_next is a file from another app, so it is untrusted: the scanner walks the text once, without recursion, without a tree and without allocating, reads nothing outside
 * [s, e) and writes nothing outside the item it fills. It sees tags only: an <outline> (any case, nested to any depth: the nesting is not looked at) that has an xmlUrl attribute with an http(s)
 * address gives one item; its name is the text attribute, else title. Comments, CDATA, processing instructions and the DOCTYPE (with an internal subset) are skipped whole. Attributes come in any
 * order, with single or double quotes (an unquoted value is accepted), in any case; entities (&amp; &lt; &gt; &quot; &apos; &#n; &#xh;) are decoded, an unknown one stays as written.
 */
#pragma once

/* (the PC_* sizes are patch/offsets.inc's, pc_show_t is patch/podcasts.h's: include them first) */

#define PO_FILE_MAX \
    524288 /* bytes of an OPML file read; the rest is not looked at. Not under PO_EXPORT_MAX: our own export is read back whole */
#define PO_EXPORT_MAX \
    327680 /* bytes of the export: PC_MAX_SHOWS (100) shows of the worst escaping (about 2.8 kB each) */
_Static_assert(PO_FILE_MAX >= PO_EXPORT_MAX, "an export must be importable whole");

typedef struct {
    const unsigned char *s, *e; /* the text still to scan: from s to e */
} po_t;

typedef struct {
    char url[PC_URL]; /* the feed address: http:// or https://, no byte under 33, shorter than PC_URL */
    char title
        [PC_TITLE]; /* the outline's text (else title): UTF-8, white space collapsed, cut on a character boundary; "" = none */
} po_item_t;

/* Start scanning the n bytes at buf. */
void po_open(po_t *p, const char *buf, unsigned n);
/* The next outline with a usable feed address into it: 1, or 0 when the text is used up. An outline whose xmlUrl is missing, empty, too long, not http(s) or holds a space is not an item. */
int po_next(po_t *p, po_item_t *it);

/* The subscriptions of shows[0..n) (those with a feed address) as indexes into shows, by title (a leading "The " and the case aside, then the folder name): into order (room for n). Returns how many. */
int po_order(const pc_show_t *shows, int n, int *order);
/* OPML 2.0 for the shows shows[order[0..n)] into out (cap bytes, with a NUL after the text): one <outline type="rss" text title xmlUrl> per show, the attributes XML-escaped (control bytes are
 * left out). Returns the length, 0 when it does not fit. */
unsigned po_render(const pc_show_t *shows, const int *order, int n, char *out, unsigned cap);

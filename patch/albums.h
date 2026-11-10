/* The Albums page (patch/albums.c) for callers that open it on a library source (patch/libsrc.h).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once
#include "libsrc.h"

/* The page on src's albums: artist NULL every album, else src's artist record (the caller keeps it) and that artist's. NULL or &lib_stock is the stock page. 0 once up, -1 window did not open, -2 asset not ours. */
int albums_open_src(const lib_src_t *src, void *artist);

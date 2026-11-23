#!/usr/bin/env python3
"""Lightweight /usr/bin/checkappprocess.sh watchdog (no 2 s pgrep fork loop).

Stock's /usr/bin/checkappprocess.sh runs `pgrep "/release/bin/demo"` every 2 s forever,
forking pgrep + sleep every 2 s and triggering repeated SquashFS reads.
Caching demo's PID and checking `/proc/$DEMO_PID/comm` in-shell keeps the exact 2 s
watchdog reboot behaviour while eliminating the `pgrep` fork while demo is alive
(leaving only `sleep 2`); any miss rescans `/proc` and falls back to stock's
`pgrep "/release/bin/demo"` before calling `reboot`.

Usage: mod_watchdog.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modlib import clone_workdir, sha256, write_keep_mode

REL = 'usr/bin/checkappprocess.sh'
STOCK_SHA = '68843ed739919420974ca55e6c5a6a2e52e63711b2faca116656440e5bd6a096'

WATCHDOG_SH = b"""#!/bin/sh
# Lightweight demo watchdog: caches demo's PID in-shell (no pgrep fork while alive),
# rescans /proc and falls back to pgrep on miss before rebooting.
find_demo() {
\tfor p in /proc/[0-9]*/comm; do
\t\tread c < "$p" 2>/dev/null || continue
\t\tif [ "$c" = "demo" ]; then
\t\t\tp=${p#/proc/}
\t\t\tDEMO_PID=${p%/comm}
\t\t\treturn 0
\t\tfi
\tdone
\tDEMO_PID=""
\treturn 1
}

DEMO_PID=""
while true
do
\tif [ -n "$DEMO_PID" ] && read c < "/proc/$DEMO_PID/comm" 2>/dev/null && [ "$c" = "demo" ]; then
\t\t:
\telif ! find_demo && ! pgrep "/release/bin/demo" > /dev/null; then
\t\treboot
\tfi
\tsleep 2
done
"""


def patch(data):
    """The stock script's bytes -> ours; ValueError on anything but the pinned stock file."""
    if sha256(data) != STOCK_SHA:
        raise ValueError(f'{REL}: not the pinned stock script')
    return WATCHDOG_SH


def apply(out):
    path = os.path.join(out, 'rootfs', REL)
    write_keep_mode(path, patch(open(path, 'rb').read()))
    print(f'watchdog: lightweight /{REL} ({len(WATCHDOG_SH)} bytes)')


if __name__ == '__main__':
    clone_workdir(sys.argv[1], sys.argv[2]); apply(sys.argv[2])

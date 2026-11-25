# Boot logo, quotes, settings slides

**Sources:** `tools/mod_boot.py`, `tools/boot_logo.py`, `assets/boot-logo.svg`,
`assets/S11logo_display_shell`.

## Logo

`/etc/init.d/S11logo_display_shell` runs `display_logo` on `images/xx/logo180.jpg` when
`/mnt/data/config.ini` has `ROTATEMODE=1`, else on `logo.jpg`. These are the only splash images.
`display_logo` draws 1:1, so a replacement must be a 320x480 baseline JPEG (`logo180` is `logo`
turned 180 degrees).

`assets/boot-logo.svg` is just the outlined **M1+** wordmark on black, with no product name, so
renaming the launcher does not touch it (q2-pod style). `tools/boot_logo.py` (`brew install
librsvg`) renders it into the committed `assets/boot-logo.jpg` and `boot-logo180.jpg`.
`mod_boot.py` checks both stock files by SHA-256 and each new file's frame header, and keeps
mode 755.

## Card logo

The stock splash script, pinned by SHA-256, is replaced by `assets/S11logo_display_shell` (stock
mode and mtime). It works like q2-pod's card logo, but in shell only, with no payload code.

- **Display:** `/mnt/data/m1plus/boot-logo.jpg`, or `boot-logo180.jpg` under `ROTATEMODE=1`, when
  present, else the built-in file. There is one `display_logo` call.
- **Import** (in the background, beside the display): waits up to 60 s for `/mnt/mmc` in
  `/proc/mounts`, since the card mounts after the splash. `/tmp/mmc_add` is no sign:
  `add_removesd.sh` touches it even when the mount fails, as for the whole-disk `mmcblk4` event
  early in boot (exFAT "failed to read boot sector"). Then it follows `/boot-logo.jpg` on the card:
  - **Changed** (its md5 differs from `boot-logo.md5`): `jpeg_size` reads the width and height
    from the JPEG's frame header (SOF0-15, after any APP segments) with `od`, before anything is
    decoded. The stock `ffmpeg`, at `nice 19`, scales the card file to 320x480 with no aspect kept,
    with the decoder bound `-max_pixels 8388608`: ffmpeg follows a later frame header, which
    `jpeg_size` never reads. It then turns that small copy with `hflip,vflip`, so the source is
    decoded once. Both go through
    `.tmp` files and `mv`; the md5 is written only once both are installed, then `sync` runs.
  - **Unchanged:** nothing runs.
  - **Missing** from a mounted card: the three files are deleted.
  - **No card:** nothing changes.
- **Limits:**
  - Files over 2 MB are ignored, with no md5.
  - **Refused**, with the md5 kept so the file is not looked at again: no JPEG frame header (a PNG,
    say), over 4096 px a side, or over 8 megapixels. ffmpeg decodes the whole frame before scaling,
    about 2 bytes a pixel (a 10000x10000 JPEG of 1.6 MB needs about 190 MB), and the player has
    128 MiB.
  - **A failed conversion** (ffmpeg, a frame over `-max_pixels`, a full `/mnt/data`, `mv`) keeps
    the old logo and writes no md5, so the next boot tries again; the decoder refuses an oversized
    frame before taking its memory.
  - ffmpeg's mjpeg output is an 8-bit, three-component baseline JPEG, as `display_logo` needs. A
    JPEG's EXIF orientation is not applied.
- A new file shows from the second power-on: the first imports it.
- The power-off splash stays the M1+ logo ([overlays](overlays.md)).

## Quotes

The stock font gives the curly quotes the CJK em advance, so "Paul's" shows a wide gap. The step
can map them to the straight glyphs, but it accepts a non-stock font only if every curly quote is
already mapped and narrower than half an em. With Inter the quotes are proper, so the release
keeps them curly.

## Slides

Every settings window in `ui/systemset/` gets `open_anim_hint` and `close_anim_hint` =
`slide_left(duration=200,easing=cubic_out)` (what the stock lock screen's close hint uses): a page
slides in from the right and back out. `fwupdate_page` and `fwdownload_page` stay stock, the way
back to a known build. There is no switch; a stuck page needs a code change in
`mod_boot.apply_anim`.

## Slide safety rule

A close animation keeps the window in the stack, visible, until it ends in the main loop (200 ms).
Code that pops windows in a loop and expects the stack to change synchronously
(`while (top != X) navigator_back();`) would spin and the watchdog would reboot. The only such
loops are Album detail "play from here" and the jump list. Both stop at the first `playing_page` or
`home_page`, and they open only from library pages, the Now Playing "more" dialog, the Home
dispatcher and search, never from settings code (a static reachability search over stock `demo`).
So the slides stay on all settings windows; new code must not add such a loop reachable from them.

Behaviour differences without hanging: the folder-scan dialog on the specified-folder page opens
about 200 ms late after Back, two closes or opens within one slide share a pending slot, and the
pull-down to settings slides in while the finger is down.

## Theme at boot

A pinned clamp makes `config_init` read any non-zero `[SYSSET] THEME` as 0, so the `default` theme
always loads and the System page has no Theme row ([theme](theme.md) "theme1 is off"). No payload
code or kill switch is involved.

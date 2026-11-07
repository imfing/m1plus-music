# Payload safety

- **Keep the approved entry points.** Home icon tap, guarded Home initialization,
  Now Playing initialization, More-dialog initialization, pull-down initialization (opened by the user's swipe only), the podcast tag-copy call site, the
  dot-folder scan, library query functions, status bar's battery-capacity call site
  (Battery Percentage, off by default), the RGB-lamp status call at `0x4ce968` (MCL track metadata and read-only volume),
  `toolsGetFileCreateTime`'s prologue (song dates: one `statx`, stock's date on any failure), `mclStartPlayer`'s prologue (Radio's hand-over: it stops a running radio, one
  comparison otherwise), `on_backtoplayer_onclick`'s prologue (every stock Now Playing button: Radio Now Playing while a station plays, else stock), the previously empty `scroll_view` event slot, the All System Settings hub's Wi-Fi row (`navigator_to` call site `0x4b1460`: our Wi-Fi page, stock's on the kill switch or a page that will not open), and the
  palette's three paint-time hooks: `style_get_color` `0x659fcc`, `style_get_gradient` `0x659f9c` and
  `image_manager_add` `0x655638` ([accent](accent.md), payload hooks 10 - 12); in `hciplayer`, the
  equalizer's `af_info` open slot `0x89381c` and its two 48 kHz gates ([parametric EQ](peq.md)).
  Each is pinned, falls back to
  stock and is a pass-through while the palette is inactive (Black + Neutral) or `/mnt/mmc/m1plus-off` exists.
  [Payload](payload.md) defines the hook sites and fallbacks. Do not add global paint or
  main-loop work outside that scope. The RGB lamp uses the existing stock player-status callback
  and returns the stock play-status value unchanged. While playing, it reads track metadata and
  the volume global; it adds no timer, worker or network request.
- **Boot-reachable hooks are a paved path.** A new pinned prologue or call-site hook on a stock
  function that also runs at boot (such as `select_timezone` from `config_init`) needs no
  separate approval when it falls back to stock on the kill switch, invalid input or any error,
  and does only bounded work: no thread, timer, loop over files or network. Document it in
  [payload](payload.md) with its `tools/reach.py` boot reachability and add it to the list above.
- **Treat startup as critical.** Home initialization needs the crash marker. The tag-reader
  hook is also reachable through Memory Playback at boot: run stock's copy first and restrict
  podcast processing to its card path. The `mclStartPlayer` hook is reached there too: with no radio running it
  is one comparison before stock's function. The player's EQ filter is reachable at boot too (Memory
  Playback with stock's Equalizer on): it reads one flash file per track and passes DSD and the
  kill switch through. The recovery button combination remains unverified.
- **Preserve hook restrictions.** Tidal-icon recovery applies only while the bad note exists.
  Home's ready path changes the language's CJK cmap field and glyph-cache size, repeated
  by a timer after language/theme changes. Podcast tags apply only under
  `/mnt/mmc/Podcasts/` after stock's path copy. Library query hooks are reachable through
  Memory Playback at boot: rewrite only the documented songtable/myfav cases and pass
  other SQL untouched. Album queries use track order so the first track supplies the row/cover.
  The scan hook skips dot-folders outside the boot path. The battery hook runs stock first
  from the first status refresh; only an enabled percentage setting changes capacity/label.
  Disabled it adds only an access and cached flag. The RGB-lamp hook reads MCL's 52-byte metadata
  snapshot and volume value, only while playing. It stages RGB and intensity in stock's transient
  lamp state and calls the stock reset when disabled, playback ends or the kill switch is present;
  it does not read or write PCM samples or change the volume. Its on/off setting uses the settings
  folder's atomic-write helper.
  Now Playing's paint work stays on the
  cover widget; More work stays on init, More/back taps and covering-dialog handling. The pull-down hook runs stock's init first,
  then moves and hides the eight tiles and their captions once.
- **Pin every edit.** Check stock SHA-256, words, symbols, `$gp` and offsets before writing.
  A mismatch fails the build; hook errors fall back to stock.
- **Honor the kill switch.** `/mnt/mmc/m1plus-off` disables the payload on the path rollback needs: the
  menu entry and boot guard (`m1plus.c`, `home.c`), boot-reachable hooks and hooks that run on every
  screen (paint, status bar, list gesture) check it. The list-gesture hook reads it once per session.
  Hooks on tap-only stock screens (Now Playing, More dialog, pull-down, library rows, Radio Now Playing)
  and everything reached from the menu do not, and rely on their stock fallback.
- **Preserve widget names.** Restyle, move or hide widgets the application looks up; never
  rename or delete them. Hide with both `visible=false` and `sensitive=false`; decorative
  overlays must be insensitive. See [UI rules](ui-rules.md) for hit-test evidence.
- **Preserve update boundaries.** Only kernel and rootfs are packaged. Never write bootloader
  or recovery kernel. The rebuilt rootfs must not exceed stock size.

The radio engine's 500 ms timer is the one timer that is not a page's: it lives from a station's start (a tap) to its stop, error
or hand-over, holds standby and the DAC timer, and ends itself ([radio](radio.md)).

Normal windows are 450 px below the status bar; fullscreen windows are 480 px. Feature timers,
workers and paint events must remain owned by their page and follow its lifetime.

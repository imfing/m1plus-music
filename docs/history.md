# History

Selected milestones and device findings. Release-by-release changes live in git.
Current behavior belongs in the [module references](README.md), [architecture](architecture.md)
and [UI reference](ui.md). Hardware observations below do not validate later builds.

## Milestones

- **2026-10-19 to 2026-11-01:** established deterministic firmware repacking and stock restore,
  the appended MIPS payload, guarded Home entry and the M1+ Music interface. Library,
  playback, podcast and virtual-iPod features are documented by module.
- **1.0.0, 2026-11-01:** flashed and accepted. Introduced semantic release tags, cold-build
  verification, manual macOS CI and draft-release publishing. Included Find Cover & Lyrics,
  the Home cover build and Rebuild Covers.
- **1.1.0, 2026-11-03:** Software Update over Wi-Fi with release notes, album length footers,
  artist albums on the Albums page and the RTC kept as UTC for stock auto time.
- **1.2.0, 2026-11-05:** Internet Radio, accent colours, an Apple-style shuffled queue with
  Play Next / Play After and Queue Clear, Control Center tiles and 43 time zones.
- **1.2.1, 2026-11-05:** a sturdier, visible Home cover build (progress pill, stop, skip of hung
  albums, unchanged-library stamp) and list, title and Radio fixes.
- **1.3.0, 2026-11-06:** a 10-band EQ editor, AutoEq downloads and per-output EQ, a new Wi-Fi
  page (WPA3, Enhanced Open), a redesigned Wi-Fi Transfer page, Podcast Discover, library "…"
  menus, Favorite and Get Info, and the long-lyric-line reboot fix.
- **1.3.1, 2026-11-07:** fixes for the pull-down's Settings tiles, long lyric lines opened
  mid-song and the stock Equalizer row, which now opens the Equalizer page.
- **1.3.2, 2026-11-08:** a steady Now Playing quality line, a sharp enlarged cover and lyric
  lines that no longer clip their last letter.

## Device findings

- **Vinyl tint:** recoloring an already-tinted anti-aliased rim retained the previous color.
  The model reproduced the same mistake, so tests agreed with the bug. Recolor from pristine
  rim pixels and compare successive changes against a fresh composition.
- **Vinyl pause:** stock `play_pause_music` sleeps 150 ms on the UI thread. Full diagonal-box
  composition then caused arm stutter. Per-row spans, layer passes, stepped sampling,
  a late-tick cap and waiting for the record to stop reduced the work.
  See [Vinyl](modules/vinyl.md) for current budgets.
- **Songs sections:** independent letter runs failed on a real library. Section labels must
  be non-decreasing while assigning as many songs as possible to their own initial.
- **Cover-pane motion:** resizing and moving the sampled window every frame produced visible
  jiggle. Scale once and copy at whole-pixel offsets; see [iPod](modules/ipod.md).
- **Recently Played artwork:** an old album-row key selected a cache filename the current
  builder never produced. A placeholder tile could coexist with correct album-page art.
  Cache lookup and construction must use the same album identity.
- **LRCLIB:** uncached requests returned HTTP 503 under load; service errors need a retry path.
- **Standby:** `reset_poweroptions_timer(1, 1, 0)` can keep the device awake while the
  screen turns off. Ordinary standby stops Wi-Fi and CPU execution.
- **Keyboard:** a 155-tap log showed misses between keys without a systematic offset,
  supporting nearest-key selection. The stock T9 popup was 640 px wide on a 320 px screen;
  the shipped Pinyin dictionary opened through `im_open_decoder` in 76 ms.

## Durable lessons

| Area | Finding / constraint | Reference |
|---|---|---|
| Hit testing | Invisible widgets still take touches; hide with sensitivity off. Decorative overlays must be insensitive. | [UI rules](modules/ui-rules.md) |
| Coordinates | Pointer coordinates are screen-relative; convert with `widget_to_local`. Never index outside a list during overscroll: row -1 rebooted the player. | [Gestures](modules/gestures.md) |
| List layout | The stock layouter restacks children by index and ignores custom child y positions. A mobile scrollbar enables vertical scrolling. | [Albums](modules/albums.md), [Home guard](modules/home-guard.md) |
| Widget identity | Names are an application API; asset steps can also change child order. Find widgets by name/type rather than an assumed child index. | [UI rules](modules/ui-rules.md) |
| Slide menus | Stock starts on item 1; set the intended value explicitly, including one-album shelves. | [Cover Flow](modules/coverflow.md) |
| Dirty rectangles | Drawing beyond widget bounds requires invalidating the complete drawn area. Pressed artwork must fit its repaint rectangle. | [Navbars](modules/navbar.md), [Cover Flow](modules/coverflow.md) |
| Text | Measure truncated glyph advances plus 1 px per glyph in the built font. Button alignment, spacer and icon size affect the painted result. | [Text width](modules/text-width.md), [Navbars](modules/navbar.md) |
| Images | Stock uses nearest-neighbor scaling; round-radius does not clip image pixels. Pre-scale for 1:1 drawing and preserve alpha when compositing over artwork. | [Album page](modules/album-page.md), [iPod](modules/ipod.md) |
| Large lists | Paint visible items from a bounded tile ring. Per-item widget layout can scale with the entire library on each drag. | [Albums](modules/albums.md) |
| Touch propagation | Grabbing or consuming move events can disable the system pull-down. A child button returning RET_OK can also activate its clickable parent row. | [Gestures](modules/gestures.md), [Home guard](modules/home-guard.md) |
| Window closing | Destruction is deferred; immediate reopen can still find the old window. Close animations can stall stock stack-pop loops. | [Boot](modules/boot.md), [Album page](modules/album-page.md) |
| Dialogs | Dimming uses the highlight property read at open; the highlighter does not hit-test. Animated-dialog canvases are not established by emulation. | [More sheet](modules/playmore.md) |
| Shared stock state | Library loaders mutate state that outlives the page. Resolve lists only for the foreground owner, not a covered page's timer. | [Payload](modules/payload.md) |
| Playback mode | Explicit Play must restore an in-order mode after Shuffle; row taps retain stock mode. | [Shuffle](modules/shuffle.md) |
| Startup | Home's first open does not send the usual foreground event. Guard risky initialization with a durable crash marker; the kill switch cannot stop code before it runs. | [Home guard](modules/home-guard.md), [Safety](modules/safety.md) |
| Podcast covers | A 3000 px cover can require 36 MB in the stock loader. Shrink downloaded art once; large images need bounded-memory decoding. | [Podcasts](modules/podcasts.md) |
| Feeds | Tracking redirects can exceed eight hops; over-cap feeds can retain complete items parsed before the cap. | [Podcasts](modules/podcasts.md) |
| Generated assets | Missing regenerated icon PNGs can escape both preview and draw-call tests. Commit the generated assets with their source changes. | [Icons](modules/icons.md) |
| Test independence | A model can duplicate implementation mistakes. Compare against independent results and retain device checks for playback, timing and panel appearance. | [Validation](modules/validation.md) |
| Determinism | Warm caches hid build-time mtimes in rebuilt UI files and an added font. Compare cold builds after adding files; pin tools and strip incidental metadata. | [Workflow](workflow.md) |

The recovery button combination remains unverified. Keep stock restore and the previous
release available; never combine independent untested firmware changes in one device trial.

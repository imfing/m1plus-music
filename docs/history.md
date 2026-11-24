# History

Selected milestones and device findings. Release notes live in the GitHub releases.
Current behavior belongs in the [module references](README.md), [architecture](architecture.md)
and [UI reference](ui.md).

## Milestones

- **2026-10-19 to 2026-11-01:** deterministic firmware repacking and stock restore, the appended
  MIPS payload, guarded Home entry and the M1+ Music interface.
- **1.0.0:** semantic release tags, cold-build verification, draft-release publishing, Find Cover
  & Lyrics and the Home cover build.
- **1.1.0:** Software Update over Wi-Fi, album length footers, artist albums and UTC RTC.
- **1.2.0:** Internet Radio, accent colours, Apple-style shuffle queue, Control Center tiles and
  43 time zones.
- **1.2.1:** a sturdier Home cover build and list, title and Radio fixes.
- **1.3.0:** 10-band EQ, AutoEq, a new Wi-Fi page, Wi-Fi Transfer redesign and Podcast Discover.
- **1.3.1:** pull-down Settings tile, long lyric line and stock Equalizer row fixes.
- **1.3.2:** a steady quality line, a sharp enlarged cover and unclipped lyric lines.
- **1.4.0:** Subsonic / Navidrome, artist photos, Continue Playing, Idle Display, Lock Screen,
  Charge Limit and full podcast episode lists.
- **1.4.1:** up to 100 podcast shows, Wi-Fi name ellipsis and list, Cover Flow and LED fixes.
- **1.5.0:** Audiobooks with LibriVox, scrobbling, Lyrics Mode, new Control Center tiles and a
  music-driven LED light.
- **1.6.0:** a VU Meter view, a redesigned Now Playing info page and Control Center, Battery
  History, Mono Audio and Crossfeed, Year groups in Albums and Subsonic folders.
- **1.7.0:** Pins on Home, a Volume page, a shared Select mode, an Update Library page and a
  French keyboard.
- **1.8.0:** bug fixes and polish, Crossfade, a redrawn status bar and battery, a smoother Now
  Playing and podcast skip controls.
- **1.8.1:** fixes and polish for the status bar, Now Playing, Radio and the Recently Added grid.
- **1.9.0:** a second Control Center page, playlist editing, podcast episode notes on Now Playing
  and grouped item menus.
- **1.9.1:** fixes for Crossfade, lyrics and sliders.

## Device findings

- **Vinyl tint:** recoloring an already-tinted rim kept the old color, and the model made the
  same mistake as the code. Recolor from pristine pixels and compare against a fresh composition.
- **Cover-pane motion:** resizing the sampled window every frame jiggled. Scale once and copy at
  whole-pixel offsets ([iPod](modules/ipod.md)).
- **Recently Played artwork:** an old key picked a cache name the builder never wrote. Lookup and
  construction must share one album identity.
- **Standby:** `reset_poweroptions_timer(1, 1, 0)` can keep the device awake with the screen off.

## Durable lessons

| Area | Finding / constraint | Reference |
|---|---|---|
| Hit testing | Invisible widgets still take touches; hide with sensitivity off. Decorative overlays must be insensitive. | [UI rules](modules/ui-rules.md) |
| Coordinates | Pointer coordinates are screen-relative; convert with `widget_to_local`. Never index outside a list during overscroll: row -1 rebooted the player. | [Gestures](modules/gestures.md) |
| List layout | The stock layouter restacks children by index and ignores custom child y positions. A mobile scrollbar enables vertical scrolling. | [Albums](modules/albums.md), [Home guard](modules/home-guard.md) |
| Widget identity | Names are an application API; asset steps can also change child order. Find widgets by name/type rather than an assumed child index. | [UI rules](modules/ui-rules.md) |
| Slide menus | Stock starts on item 1; set the intended value explicitly, including one-album shelves. | [Cover Flow](modules/coverflow.md) |
| Dirty rectangles | Drawing beyond widget bounds requires invalidating the complete drawn area. Pressed artwork must fit its repaint rectangle. | [Navbars](modules/navbar.md), [Cover Flow](modules/coverflow.md) |
| Text | Measure truncated glyph advances plus 1 px per glyph in the built font. Button alignment, spacer and icon size affect the painted result. | [UI rules](modules/ui-rules.md), [Navbars](modules/navbar.md) |
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

The recovery button combination is unknown. Keep stock restore and the previous release
available, and never combine independent untested firmware changes in one device trial.

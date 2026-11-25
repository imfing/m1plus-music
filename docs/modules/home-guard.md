# Home, the boot guard and the window stack

**Sources:** `patch/home.c`, `patch/home.h`.
`home_page_init` starts M1+ Music behind a durable crash marker and falls back to stock on failure.
It is the startup UI hook; the separately constrained podcast tag-reader hook can also run through
Memory Playback. See [payload safety](safety.md).

## Boot sequence

`main -> application_init -> navigator_to("home_page") -> page-init dispatcher -> home_page_init`
(the hook; `tools/reach.py` confirms it is the only route). The hook `m1plus_home_init`:

1. **runs the stock `home_page_init` to completion** (`stock_home_init_trampoline`) and returns its
   result;
2. only if it returned `RET_OK` for a non-null window, runs `home_boot(win)`. The state is stock until
   everything succeeded:
   1. **kill switch** `/mnt/mmc/m1plus-off` (SD, may not be mounted yet) or `/mnt/data/m1plus-off`:
      stop;
   2. **marker found** (`/mnt/data/m1plus-run`): the previous attempt never proved itself. Write the
      sticky note `/mnt/data/m1plus-bad`, set `/mnt/data/m1plus-start` to `0`, remove the marker,
      stop. If the note cannot be written the marker stays, so every later boot is stock too;
   3. **bad note found**: stop (sticky: a crash cannot alternate with good boots);
   4. read the setting (`/mnt/data/m1plus-start`: `0` = Shanling, missing or anything else = M1+
      Music). It does not stop the guard: the Shanling start is armed too, because step 7 adds the
      grid icon;
   5. **write the marker**: temp file, `fsync`, `rename`, directory `fsync`. The open and the
      `fsync` must succeed (an unconfirmed marker is not armed on); any failure stops with no marker
      left;
   6. **arm**: a one-shot UI timer (5 s, `CLEAR_MS`) removes the marker and fsyncs the directory;
      with no timer the marker is removed at once;
   7. **add the "M1+ Music" icon** to the grid (`hm_add_icon`; any failure adds nothing), register
      a Home `EVT_WINDOW_TO_FOREGROUND` handler, and, when the setting is M1+ Music, hide the grid
      content (`app_gesture`: icon pages and bottom strip, after the marker is durable) and schedule
      the first menu open (10 ms, `OPEN_FIRST_MS`). Before the open, `fr_boot` points the font at the
      UI language's CJK cmap ([fonts](fonts.md)); any mismatch leaves the font as it is.

Only one-shot UI-thread timers and plain file calls through demo's own GOT. No thread, no polling,
nothing in paint or the main loop.

**Why this hook and not the Home foreground handler:** the foreground event fires when a window above
Home closes but not at start-up (the first open dispatches `WILL_OPEN` / `OPEN`). Hooking
`home_page_init` gives the start-up trigger and lets the same function register an extra foreground
handler with `widget_on`, so the foreground path needs no second hook.

### The grid icon

`hm_icon_cell` builds one cell exactly as stock's icon builder does, in the same order: a 154x118
`view` with a 66x66 `image` (name `"99"`, style `home_m1plus_style`) and a 154x36 `label` "M1+
Music". `hm_add_icon` takes the last page's first free slot, or makes a new page view and bumps
`slide_indicator_set_max`. Anything unexpected (no `home_sview`, not a `slide_view`, more than 8
pages, a last page with more than six cells) or a failed constructor adds nothing; a partial cell is
destroyed. Stock's rebuild (Home customisation) drops the icon, so `hm_fg` re-adds it when `99` is
not found.

## Guard guarantees and limits

The stock function completes before payload work. File or timer failures or a kill file leave startup
stock. Arming needs the marker and bad note absent. A start that dies after arming leaves the marker;
the next start writes the sticky note (or, if it cannot, leaves the marker) and runs stock; every
start after that finds the note or marker and runs stock. At most one crash, never an alternation.
The menu open is covered by the same marker.

Residual risks:

- A power-off within 5 s counts as a failed start (the next start is stock; turn **Boot to M1+
  Music** on again).
- A hang inside `fsync` on a broken flash filesystem would hang the UI thread before the marker is
  durable.
- Misbehaviour after the 5 s window is not caught.
- The SD kill switch is read inside the hook, so a real boot loop before the hook runs needs a
  reflash ([payload safety](safety.md)).

## Files and the kill switch

| path | meaning |
|---|---|
| `/mnt/mmc/m1plus-off` | SD kill switch: the payload does nothing at boot (no icon), the icon does nothing, the row fit is off |
| `/mnt/data/m1plus-off` | the same in flash (cannot be created without a shell) |
| `/mnt/data/m1plus-run` | the crash marker: exists from "armed" until 5 s later |
| `/mnt/data/m1plus-bad` | the sticky note when a marker was found; removed by turning on **Boot to M1+ Music** |
| `/mnt/data/m1plus-start` | the setting: `0` = Shanling, missing or anything else = M1+ Music (temp + `fsync` + `rename`) |
| `/mnt/data/m1plus/home-menu` | the menu's items in order and the turned-off ones: [menu](menu.md) |
| `/mnt/data/m1plus/home-recent-albums`, `/mnt/mmc/.m1plus/recently-played` | the Recently Played shelf: [recent](recent.md) |
| `/mnt/data/m1plus/albums-view`, `coverflow-landscape`, `coverflow-volume-keys`, `coverflow-start` | page settings: [settings](settings.md) |
| `/mnt/mmc/m1plus-log` | opt-in: if this empty file exists, events are appended to `/mnt/mmc/m1plus.log` (armed, boot ok, marker found, kill switch) |

The setting is an own file, not `config.ini [M1PLUS]`: `write_int_config` rewrites the shared config
the stock app parses at start-up, and a bad write there is a boot risk.

`home-menu` is on the boot path (the menu is the Home screen at start-up), so `patch/menu.c` reads it
with plain `open` / `read` of at most 25 bytes and never writes while reading. Format and validity
rules: [menu](menu.md). A file that is missing, corrupt or duplicated gives the default list. Settings
is never allowed after the `-` and Extras is a row the arrangement never hides, so Settings stays
reachable from any file.

## The stock list code under the menu's hand-placed rows

The menu, Extras and Main Menu pages are a stock `list_view` > `scroll_view` whose rows
`patch/menu.c` places by hand, and the stock list code assumes it owns that layout. Two decisions
follow.

- **Restack the rows.** Any relayout (`widget_set_visible` marks the window for one; it runs before
  every paint) puts the asset's order back: stock's list layouter stacks the visible children in
  child order. So `menu_arrange` and `cm_layout` `widget_restack` the rows into page order, hidden
  rows last. Stock's layout then computes exactly the `y` and `virtual_h` we set (rows `POD_ROW_H`
  52 px, no spacing), and a relayout at any time changes nothing. The Extras page is restacked the
  same way in its fixed order (`EX_ORDER`).- **Clear the list's paint hook.** list_view gives its scroll_view a paint-children hook that stops
  painting at the first child whose top is below the canvas (an overscrolled list or a shorter canvas). The pages clear that one word (`mn_plain_paint`: only if the
  widget's vtable is `g_scroll_view_vtable` and the word is exactly the stock hook), so the default
  painter paints them.

The pull-down opens on a touch that began at y <= 80; on Home the first row lies there too. Opening
the dialog sends the window an abort, so scroll_view and list_item reset and the dialog gets the rest
of the gesture ([pulldown](pulldown.md)). Home's other additions: the mini player bar
([minibar](minibar.md)) and the Recently Played shelf ([recent](recent.md)), started from
`home_menu_opened`. Both add no stock hook, wait a one-shot before their first work (so the boot's
first paint inside the 5 s window is unchanged), and on any failure leave the menu as
`hm_fill_window` made it.

**Page arrangement.** The Main Menu page (`cm_layout`) re-arranges in place after every successful
save: shown rows in menu order, then hidden in default order; switch images; the up arrow visible on
shown rows but the first; the scroll view's `yoffset` moves just enough to keep the changed row in
the window, then `widget_invalidate_force`. Click contexts are item ids, not positions, and a failed
save leaves list and page as they were. The Extras page is arranged at open (reachable only from the
menu, so no foreground handler); Settings > Extras flips an item's off flag on a tap and saves; the
menu re-arranges on `EVT_WINDOW_TO_FOREGROUND`.

**One tap, one action on the Main Menu rows.** The up arrow is a picture (insensitive; stock's button
would also pass the click to the row, so one tap moved and toggled the item). The row binds click and
pointer down / up / abort. The decision is made at DOWN: a touch that went down inside the arrow's
rectangle (shown, not first) moves the item up, anything else toggles it, so a finger that slides out
before lifting does what it started. While held the arrow shows its pressed art, reset at UP, abort,
click and the next DOWN. A drag that starts on the arrow scrolls the list only. Tests:
`test/pod/menutap.py`.

## Window stack

The pod menu is not the bottom window: stock code looks Home up by name (`home_page`; the "play from
here" loops stop at it, `navigator_back_to_home` closes down to it), so the menu is opened with
`window_open` above the stock Home. Home's `TO_FOREGROUND` is the single "we are home again" trigger:
`hm_fg` only schedules a 10 ms timer; `hm_open` opens the menu iff the topmost visible normal window
is the stock Home and it is opened, retrying every 50 ms up to 100 times while Home is not opened
yet. Whatever else is on top (resumed Now Playing, the first-run guide, a library page, a dialog's
owner) wins: nothing is opened, and when it closes Home comes to the foreground and `hm_fg` fires.
The open is a one-shot timer, never inside the event, so no window opens while the manager is closing
one.

| path | result |
|---|---|
| start-up | the hook schedules the first open: menu over Home (after Now Playing's resume, once closed) |
| go-home idle callback (idle timeout, USB, search, keylock) and `navigator_back_to_home` | force-closes everything above Home (menu too); Home gets `TO_FOREGROUND`, so the menu reopens |
| Back on the Home menu | no navbar, so no Back button; a hardware Back closes the menu and it reopens (a flash, no loop; the loop breaks via Settings > Developer > Open Shanling Home) |
| Back from Now Playing / library pages opened from the menu | their `navigator_back` closes them; the menu is below and becomes top |
| "Back to player", Shuffle's Now Playing | `window_manager_switch_to` restacks or opens `playing_page` above the menu; Back returns to it |
| lock screen, power-off dialog cancel | a fullscreen window above, or a dialog closes; nothing changes |
| "play from here" and jump-list loops | pop with `navigator_back` until `playing_page` or `home_page`. `playing_page` is in the stack only when Now Playing was opened before the album page; otherwise the loop can pop every pod page down to `home_page`, and `hm_fg` reopens the menu. The album page's Play and Shuffle run the same loop (`pod_open_player`, bounded to 16 pops). A change that adds a pod page to the stack must be checked against it |
| Settings > Developer > Open Shanling Home | `grid = 1`, closes the menu, the Extras page (when Settings was opened from it) and the Settings page; `hm_fg` sees `grid` and schedules nothing |

No close animations on the pod pages, and nothing in the payload loops on `navigator_back`.

**The grid is never shown under the menu and never blank.** The grid content is hidden from
`home_boot` on, the window under the menu is plain black, and every give-up (kill switch, no top
window, Home never opened, `window_open` failure, a refused timer) shows the grid again. Home coming
to the foreground with no menu to follow (the kill switch appeared, or Boot to was switched to
Shanling) shows it too (`hm_fg`). Stock Home keeps all its widgets, so every stock `widget_lookup`
resolves. Hiding `app_gesture` assumes stock never toggles its visibility itself.

## Recovery

Any bad state: reflash a stock image (`tools/build.py --restore`); it does not touch `/mnt/data`,
where the marker and settings live, and nothing stock reads them. A start that cannot proceed falls
to stock by itself after one bad boot.

A fallback boot is stock and adds no grid icon (the icon is boot code, so it sits behind the sticky
note like everything else). The way back is the **recovery fallback** in the Home icon tap hook: while
the bad note exists, a tap on the Tidal icon (id 1) opens the M1+ Music menu (with Back) instead of
Tidal. Settings > Developer > **Boot to M1+ Music** (switch on) clears the note and sets the start
file, and the next boot arms the guard again. Settings is reachable there even when a saved menu
hides it, through the always-shown Extras row. Without the note, or with the kill switch on, Tidal is
stock; if the menu cannot open, the tap falls through to stock. From a shell, deleting
`/mnt/data/m1plus-bad` and writing `1` to `/mnt/data/m1plus-start` does the same.

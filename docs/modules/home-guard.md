# Home, the boot guard and the window stack

**Sources:** `patch/home.c`, `patch/home.h`, test `test/pod/home.py`.

`home_page_init` starts M1+ Music behind a durable crash marker and falls back to stock on
failure. It is the startup UI hook; the separately constrained podcast tag-reader hook can
also run through Memory Playback. See [payload safety](safety.md). Recovery buttons remain unverified.

## Boot sequence

```
main -> application_init -> navigator_to("home_page") -> navigator_to_with_context -> page-init dispatcher
 (0x4d00c0, strcmp "home_page" @0x4d1cd8)  -> home_page_init (0x534cd4)    <- the hook
```

`tools/reach.py` confirms this is the only route. The hook `m1plus_home_init`:

1. **runs the stock `home_page_init` to completion** through `stock_home_init_trampoline` and returns
   its result;
2. only if it returned `RET_OK` for a non-null window, runs `home_boot(win)`, where the state is OFF
   (stock) until everything succeeded:
   1. **kill switch** `/mnt/mmc/m1plus-off` (SD, may not be mounted yet) or `/mnt/data/m1plus-off` -> stop;
   2. **marker found** (`/mnt/data/m1plus-run`): the previous attempt never proved itself. Write the
      sticky note `/mnt/data/m1plus-bad`, set `/mnt/data/m1plus-start` to `0`, remove the marker, stop.
      If the note cannot be written the marker stays, so every later boot is stock too;
   3. **bad note found** -> stop (sticky: a crash cannot alternate with good boots);
   4. the setting (`/mnt/data/m1plus-start`: `0` = Shanling, missing or anything else = M1+ Music) is read; it
      does not stop the guard: the Shanling start is armed too, because step 7 adds the grid icon;
   5. **write the marker**: temp file, `fsync`, `rename`, directory `fsync` (its open and its `fsync` must succeed: an unconfirmed
      marker is not armed on); any failure -> stop with no marker left (it is unlinked again);
   6. **arm**: a one-shot UI timer (5 s, `CLEAR_MS`) removes the marker and fsyncs the directory; with
      no timer the marker is removed at once;
   7. **add the "M1+ Music" icon** to the grid (`hm_add_icon`, below; any failure adds nothing), register a
      Home "to foreground" handler (`EVT_WINDOW_TO_FOREGROUND` `0x12d`) on the Home window, and, when the
      setting is M1+ Music, hide the grid content (`app_gesture`: icon pages + bottom strip, `visible=false`
      and `sensitive=false`; after the marker is durable) and schedule the first pod-menu open (10 ms,
      `OPEN_FIRST_MS`). Before the open, `fr_boot` (`patch/fontregion.c`, docs/modules/fonts.md "Regional forms")
      points the font at the UI language's CJK cmap and, once a session, registers the language and theme change
      handlers; any mismatch leaves the font as it is.

### The grid icon (`hm_add_icon`, `hm_icon_cell`)

The stock page builder `0x534064` (called from `home_page_init` at `0x534de4`, and again from the Home
foreground handler `0x534860` when the icon list changed) looks up `home_sview` (a `slide_view`) and
`home_sindicator`, destroys the pages and makes one 320x364 `view` per six icons (`view_create(sview, 0, 0,
0x140, 0x16c)` at `0x534168`, `deque_size / 6` rounded up) and calls the icon builder `0x533d8c` for each:
per icon a 154x118 `view` at column x 6 or 160 and row y 0/118/236, inside it a 66x66 `image` at (44, 20)
(`image_create`, `widget_set_prop_bool "clickable"`, `widget_use_style "home_<name>_style"`,
`widget_set_name` = the decimal id, `widget_on(image, 0x10c, 0x533b80, image)`) and a 154x36 `label` at y 92
(`label_centerwhitehome_white`, line wrap, the name). `hm_icon_cell` makes exactly that, in that order, with
the name `"99"`, the style `home_m1plus_style` and the text "M1+ Music" (`widget_set_text_utf8`: no translation
needed). `hm_add_icon` takes the **last page's first free slot** (cell `n` = its child count: column
`n & 1`, row `n >> 1`; English Home's 17 icons leave slot 5 of page 3 free); a full last page gets a new
page view (the builder makes as many as the list needs) with the icon in slot 0 and
`slide_indicator_set_max(pages + 1)`. Anything unexpected (no `home_sview`, not a `slide_view`, no pages,
more than 8 pages, a last page that is not a `view` or has more than six cells) or a failed constructor
adds nothing; a partial cell (or page) is `widget_destroy`ed. Newly pinned: `view_create` `0x6346f0`,
`widget_set_prop_bool` `0x670170`, `widget_set_name` `0x6668d0`, `label_set_line_wrap` `0x62e068`,
`slide_indicator_set_max` `0x616b70`, `widget_destroy` `0x66e544`, `window_close` `0x675b70`. Because the
stock rebuild drops the icon (Home customisation), `hm_fg` re-adds it when `99` is not found in Home.

Only one-shot UI-thread timers and plain file calls (`open/read/write/fsync/close/rename/unlink/access`
through demo's own GOT, `timer_add`, `widget_on`). No thread, no polling, nothing in paint or the main
loop; `home_tests` pins the whole set of calls the boot path makes. Newly pinned: `window_manager`,
`window_manager_get_top_main_window`, `widget_is_window_opened`.

**Why this hook and not the Home foreground handler** (`0x534b88`): the foreground event fires when a
window above Home closes but not at start-up (the first open dispatches `WILL_OPEN`/`OPEN`
`0x12a/0x12b`; `TO_FOREGROUND` `0x12d` only comes with a later switch or close: `window_manager_default`
`0x691930`, `0x692a44`, `0x6789f4`, `0x691b3c`). Hooking `home_page_init` gives the start-up trigger and
lets the same function register an extra `0x12d` handler with `widget_on`, so the foreground path
needs no second prologue hook.

## Guard guarantees and limits

The stock function completes before payload work. File/timer failures or a kill file leave
startup stock. **The guard prevents repeated startup attempts after a marked failure:** arming needs
the marker and bad note absent; a start that dies
after arming leaves the marker, the next start writes the sticky note (or, if it cannot, leaves the
marker) and runs stock, and every start after that finds the note or marker and runs stock: at most one
crash, never an alternation. The pod-menu open is covered by the same marker. Costs and residual
risks: a power-off within 5 s counts as a failed start (the next start is stock; turn **Boot to M1+ Music**
on again); a hang inside `fsync` on a broken flash filesystem would hang the UI thread before the
marker is durable; a later misbehaviour after the 5 s window is not caught.

## Files and the kill switch

| path | meaning |
|---|---|
| `/mnt/mmc/m1plus-off` | SD kill switch: the payload does nothing at boot (no icon), the icon does nothing if it is there, the row fit is off |
| `/mnt/data/m1plus-off` | the same in flash (cannot be created without a shell) |
| `/mnt/data/m1plus-run` | the crash marker: exists from "armed" until 5 s later |
| `/mnt/data/m1plus-bad` | the sticky note when a marker was found; removed by turning on **Boot to M1+ Music** |
| `/mnt/data/m1plus-start` | the setting: `1`/missing = M1+ Music, `0` = Shanling (temp + `fsync` + `rename`) |
| `/mnt/mmc/.m1plus/recently-played` | on the card (its keys and paths belong to its library; nothing is read or written without it): the albums played last, up to 6, most recent first (`patch/recent.c`; written only when the most recent album changes; malformed = empty) |
| `/mnt/data/m1plus/home-recent-albums` | Settings > Home Screen > Recent Albums: `0` = the shelf is off, missing or anything else = on |
| `/mnt/data/m1plus/albums-view` | the Albums page's mode: `1`/missing = the grid (`ALBUMS_DEFAULT_GRID`), `0` = the list (same write; section 5a) |
| `/mnt/data/m1plus/coverflow-landscape` | Cover Flow's presentation: `1` = landscape, `0`/missing = portrait (atomic write at each switch tap; section 4) |
| `/mnt/data/m1plus/coverflow-volume-keys` | Cover Flow's Volume Buttons switch: `1` = the volume buttons step the shelf, `0`/missing = off (atomic write at each switch tap; coverflow.md "Volume buttons") |
| `/mnt/data/m1plus/home-menu` | the menu's shown items in order, then the items turned off: one character per item (`0`-`8` the menu items, `a`-`i` the Extras tiles = ids 9-17, `j` Settings = id 18, `k` the Pod = id 19, `l` Podcasts = id 20, `m` Search = id 21, `pod_pages.ID_CHARS`), then optionally `-` and the items turned off (not listed on the Extras page), then `\n`; `12345\n` is the default (the file missing; Now Playing, Shuffle and Settings are items hidden by default). The Extras row is not in the file: it is always the menu's last row. Read with the limits below; written atomically at each change on Settings > Main Menu or Settings > Extras |
| `/mnt/mmc/m1plus-log` | opt-in: if this empty file exists, events are appended to `/mnt/mmc/m1plus.log` (armed, boot ok, marker found, kill switch) |

The menu list is **on the boot path** (the menu is the Home screen at start-up; its asset is arranged by `menu_arrange` while it opens), so
`patch/menu.c` reads `/mnt/data/m1plus/home-menu` with `open`/`read` of at most 25 bytes (`POD_MENU_FILE_MAX`) and accepts only: no
more than twenty-two characters from `012345678abcdefghijklm`, none twice (across both parts), at most one `-` (the items after it are turned off), Settings (`j`) never after it (it must stay reachable), an optional single final newline, a file shorter than 25 bytes (an empty list, a lone
newline, is valid: every item hidden, nothing turned off; so is `-` alone); a missing, empty, longer, corrupt, duplicated or unknown-id file (an old `x` is unknown) is the default list with nothing off. It
never writes while reading and a row or the list missing from the page leaves the asset untouched (every item shown, the Extras row last); Extras is a row the arrangement never hides, and Settings is an item like the others (hidden from the menu it is listed on the Extras page and can never be turned off), so Settings stays reachable from any file.
The Main Menu page (`cm_layout` in `patch/menu.c`) re-arranges in place after every successful save: row y (shown items in menu order, then hidden in default order), switch images, arrow visible (shown rows but the first; always insensitive), then the scroll view's `yoffset` is moved just enough to keep the changed item's row in the window, and the whole window is invalidated with `widget_invalidate_force`. Click contexts are item ids (not positions), so a bound row always means its own item; a failed save leaves list and page as they were.

**One tap, one action (V2.1nA).** The up arrow is a stock `button`, and stock's button answers the pointer DOWN and UP with `RET_OK`, so a tap on it also reached the row (a `list_item`) as a click: one tap moved the item up and toggled it (reproduced in `test/pod/menutap.py` on demo's own `widget_on_pointer_down/up`, `list_item` and `button` code run under Unicorn: the click log read `pod_up3, pod_row3`). Now the arrow is a picture (`sensitive=false` in the asset, and `cm_layout` keeps it insensitive; `visible` follows the shown-and-not-first rule) and has no handler. The row binds `EVT_CLICK` (`cm_on_row`) and `EVT_POINTER_DOWN` / `UP` / `ABORT` (`cm_on_touch`, the same context, the item id). The pointer event of the DOWN (and of the click, a copy of the UP's) carries screen coordinates (`PE_X` 0x18); `widget_to_local(row, pt)` (0x669b88, stock's own: it subtracts the row's and every ancestor's x, y) gives the row-local x. The arrow zone is the arrow button's rectangle, read with `widget_get_prop_int(up, "x"/"w")` (asset: x 191, w 50, the full 52 px row height; the label ends at 190, the switch starts at 241): the touch **went down** inside it on a row that has an arrow (shown, not first) -> `cm_up`; anything else (label, switch, margins, a row without an arrow) -> `cm_toggle`. The decision is made at DOWN (`cm.down` / `cm.zone`, the id + 1 of the row), so a finger that slides a few pixels out of the zone before lifting does what it started; without a DOWN of that row the click's own position decides. Pressed look: while a touch that went down in the zone is held, `widget_set_state(up, "pressed")` (0x66962c, `(widget, const char *state)`; the button's `style:pressed:icon` art `expansion_2_down`), back to `"normal"` at UP / ABORT, at the click, and at the next DOWN (a lost UP cannot leave it). A drag that starts on the arrow scrolls the list and does nothing else (the row cancels itself on an 11 px MOVE; the stock gap for a release far from the press without such a MOVE is the list gesture hook's, V2.1mV).
The page arrangement costs a handful of widget calls (`widget_move`, `widget_set_visible`, `widget_set_sensitive`, one
`virtual_h` / `yoffset` pair; twenty-one rows at most, each a constant number of calls); the Extras page hides the items the menu shows and the ones turned off and stacks the others in the fixed `EX_ORDER`, in the same pass (it is only reachable from the menu, so it is arranged at open and needs no foreground handler; with all twenty shown it is empty); the Settings > Extras page (`menu_extras_opened`) lays out the items the menu does not show the same way and a tap on a row flips that item's off flag and saves; the menu also re-arranges on `EVT_WINDOW_TO_FOREGROUND` (it comes back in front after the Main Menu or Settings > Extras page).

**The stock list code under the menu's hand-placed rows (V2.1nB, `test/pod/pulldown.py` runs all of it).** The menu, Extras and Main Menu
pages are a stock `list_view` > `scroll_view` whose rows `patch/menu.c` places by hand (`widget_move`, `widget_set_visible`, `virtual_h`), and
the stock list code assumes it owns that layout:
- *Relayout.* `widget_set_visible` calls `widget_set_need_relayout_children` on the parent (`0x66c424`), which marks the window
  (`window_base_set_need_relayout`, byte `+0xcc`); the main loop runs `window_manager_check_and_layout` (`0x677a80`) before every
  `window_manager_paint` (`0x6939f4`), and the dialog snapshot runs it too (`0x68f194`, `0x690d04`). The scroll_view's layout
  (`0x6116f4`) calls the hook `list_view_on_add_child` stored in it (`+0xf0`, `0x60c0fc`: sets the children layouter
  `"list_view(m=0,s=0)"` if there is none and runs it), and `children_layouter_list_view` (`0x60abbc`) takes the *visible* children
  in **child order** (`widget_get_children_for_layout` `0x657194`; `keep_invisible` off), gives each `y` = the sum of the heights above,
  widens them to the list's width and sets `virtual_h` (`0x60b20c`; it also makes the scroll_view `yslidable`, not `xslidable`, when the bar is
  mobile). So any relayout after our arrangement put the asset's order back: the lock screen returning to the menu painted one frame in
  the default order before the foreground handler arranged it again (the "small splash"); the Main Menu page did the same after any
  change that showed or hid an arrow. `menu_arrange` and `cm_layout` now also `widget_restack` (`0x669fc4`, no relayout of its own) the
  rows into page order, hidden rows last: the stock layout then computes exactly the `y` and `virtual_h` we set (rows are `POD_ROW_H`
  = 52 px high, no spacing or margin), so a relayout at any time changes nothing. The Extras page is restacked the same way, in its fixed
  grouped order (`EX_ORDER`), the hidden rows last.
- *Paint.* list_view gives its scroll_view a paint-children hook (`+0xf4`, `0x60c164`; `scroll_view_on_paint_children` `0x610d38` calls
  it, else `widget_on_paint_children_default` `0x674690`). The hook is the default painter plus an early `return` at the first visible
  child whose top is below the canvas (`canvas_get_height`), so it needs the children in y order and stops painting everything after
  child 0 whenever the first row is below what it takes the canvas to be (an overscrolled list, a shorter canvas: the rest of the list
  gone, the first row left). The pages clear that one word (`mn_plain_paint`: only if the widget's vtable is `g_scroll_view_vtable`
  `0x97a298` and the word is exactly `0x60c164`; anything else is left as it is), so the stock default painter paints them.
- *The Recently Played shelf.* `home_menu_opened` calls `recent_start` (patch/recent.c, `docs/modules/recent.md`) right after `minibar_start`, same conditions (the Home instance, the navbar and the list found, no kill switch). It looks up four widgets, registers eight handlers (the list's scroll event too) and arms one 150 ms one-shot,
  and then checks that the card is mounted (one `statfs`) and reads one small file (`/mnt/mmc/.m1plus/recently-played`, at most 3 KB, strictly parsed: anything malformed, or no card, is empty) and the switch file (`/mnt/data/m1plus/home-recent-albums`, one byte), and shows the shelf if an album is recorded (`menu_shelf`: a visibility change and a move of the rows). That is inside the 5 s window of the marker but
  it decodes nothing, allocates only the grid's six tile records (about 2.4 KB, no bitmap), loads no album list and hooks nothing; covers are made one per tick by the page timer afterwards. Any failure leaves the menu as `hm_fill_window` made it. The kill switch and a missing widget stop it before any call.
- *The mini player bar.* `home_menu_opened` calls `minibar_start` (patch/minibar.c) right after `hm_fill_window` for the Home instance only, and only when
  that laid the list out (navbar and list found). The list then is 10..440 until the bar's first work (a one-shot `MB_FIRST_MS` later, so the menu's first
  paint at boot, inside the guard's 5 s window, is unchanged); with a track queued the bar shows over the list (which keeps its 430 px) and the list gets its bottom padding. The bar adds no stock hook,
  nothing at paint and nothing in the main loop; every failure leaves the menu as `hm_fill_window` made it. `docs/modules/minibar.md`.
- *The pull-down.* The window manager's touch hook (`0x4cd788`) opens `dialog/dropdown_dialog` once a touch that began at y <= 80 has moved
  more than 10 px down. On the Home instance (no navbar; the first row at window y 10..62, screen 40..92) that finger is also on the list:
  list_item and scroll_view take the press, grab, and a drag (stock overscroll is unbounded: `yoffset` follows the finger). Opening
  the dialog sends `EVT_WINDOW_TO_BACKGROUND`, and `window_base_on_event` (`0x676e10`..`0x676e5c`) answers it, while the window is pressed
  (`+0xce`, set by the DOWN), with `widget_on_pointer_up` of an `EVT_POINTER_ABORT` (`0x107`): scroll_view and list_item reset, ungrab, and
  the scroll_view animates back to its pressed offset (`scroll_view_scroll_to`, 200 ms), so the dialog gets the rest of the gesture. The
  dialog snapshot then lays the page out (above) and paints it. Stock never met this: its lists sit under a 50 px navbar, the pull-down zone
  is the navbar. What reaches the page in that sequence is the relayout and the paint hook, both handled above; the tests run it with the
  window manager's own calls on the real stock code (DOWN, MOVEs, abort, snapshot layout, foreground arrange) and the first frame
  after a lock screen. What the emulation cannot show is the canvas the device gives the hook while the dialog animates (rendering is not
  emulated), which is why the paint hook is removed instead of relied on; see UI-03 in `docs/modules/device-checks.md` for the device checks.

The setting is an own file, not `config.ini [M1PLUS]`: `write_int_config` rewrites the shared config
the stock app parses at start-up, and a bad write there is a boot risk.

## Window stack

The pod menu is not the bottom window: stock code looks Home up by name (`home_page`; the "play from
here" loops stop at it, `navigator_back_to_home` closes down to it), so the menu is opened with
`window_open` above the stock Home, as the Tidal icon did before. The Home window's `TO_FOREGROUND`
event is the single "we are home again" trigger: `hm_fg` only schedules a 10 ms timer; `hm_open` opens
the menu iff the topmost visible normal window (`window_manager_get_top_main_window`) is the stock
Home and it is opened, retrying every 50 ms up to 100 times while Home is not opened yet. Whatever
else is on top (resumed Now Playing, the first-run guide, a library page, a dialog's owner) wins:
nothing is opened and when it closes Home comes to the foreground and `hm_fg` fires. The open is a
one-shot timer, never inside the event, so no window opens while the manager is closing one.

| path | result |
|---|---|
| start-up | the hook schedules the first open: menu over Home (after Now Playing's resume, once closed) |
| go-home idle callback (`0x677a28` -> `0x6777c8`: idle timeout, USB, search, keylock, ...) and `navigator_back_to_home` | force-closes everything above Home (menu too), animates the top one; Home gets `TO_FOREGROUND` -> menu again |
| Back on the Home menu | no navbar, so no Back button; a hardware Back would close the menu and it reopens (a flash, no loop; the loop breaks via Settings > Developer > Open Shanling Home) |
| Back from Now Playing / library pages opened from the menu | their `navigator_back` closes them; the menu is below and becomes top |
| "Back to player", Shuffle's Now Playing | `window_manager_switch_to` restacks/opens `playing_page` above the menu; Back returns to it |
| lock screen / power-off dialog cancel | fullscreen window above / a dialog closes; nothing changes |
| "play from here" / jump-list loops (`0x525908`, `0x538ce4`) | pop with `navigator_back` until `playing_page` or `home_page`. Do not assume `playing_page` is above the menu: it is only in the stack when Now Playing was opened (or resumed) before the album page. When it is not, the album-detail Play loop (`0x525908`) can pop every pod page (album page, Albums / Cover Flow / Artists, the menu) down to `home_page`; Home then gets `TO_FOREGROUND` and `hm_fg` reopens the menu. Derived from the code, not device-verified; a change that adds a pod page to the stack must be checked against this loop. The album page's Play and Shuffle run the same loop (`pod_open_player`, bounded to 16 pops; `test/pod/shared.py` `StackMachine`) |
| Settings > Developer > Open Shanling Home row | `grid = 1`, `window_close` of the menu, of the Extras page (when Settings was opened from it) and of the Settings page, `navigator_back` of the Home Screen page; `hm_fg` sees `grid` and schedules nothing |

No close animations on the pod pages and nothing in the payload loops on `navigator_back`.
Evidence that the open order is safe and the grid is hidden before the menu appears: the grid content
is hidden from `home_boot` on, the window under the menu is plain black (`home_page` bg `#000000`),
every give-up (kill switch, no top window, Home never opened, `window_open` failure, a refused open timer) shows the grid
again, and Home coming to the foreground with no menu to follow (the kill switch appeared, or Boot to was switched to
Shanling while the menu was Home) shows it too (`hm_fg`: never a blank Home), and the stock Home keeps all its widgets so every stock `widget_lookup` resolves. Hiding
`app_gesture` assumes stock never toggles its visibility itself (it would only re-show the grid).

## Recovery

Any bad state: reflash a stock image (`tools/build.py --restore`, V2.1R); it does not touch
`/mnt/data` where the marker and settings live, and nothing stock reads them. A start that cannot
proceed falls to stock by itself after one bad boot. If the device were in a real boot loop (not
expected: the guard acts at the first boot after a failure), the SD kill switch is not reachable
before the hook runs; use the bootloader/recovery flash of V2.1R, whose button combination is
unverified. To re-enable after a fallback: a fallback boot is stock and adds no grid icon (the icon is new boot
code, so it is behind the sticky note like everything else). The way back is the **recovery fallback** in the Home
icon tap hook (not boot code): while the bad note `/mnt/data/m1plus-bad` exists, a tap on the Tidal icon (id 1)
opens the M1+ Music menu (the normal instance, with Back) instead of Tidal; Settings > Developer (Settings is a menu item hidden by a saved list that does not list it; the menu's Extras row, always shown, then lists it) > **Boot to M1+ Music** (switch on) clears
the note and sets the start file, and the next boot arms the guard again (the icon returns). Without the note,
or with the kill switch on, Tidal is stock; if the menu cannot open, the tap falls through to stock. From a
shell, deleting `/mnt/data/m1plus-bad` and writing `1` to `/mnt/data/m1plus-start` does the same; or reflash. Device test procedure: boot, wait 10 s past Home, power-cycle a few times (with the log: every
start `armed` / `boot ok`, never `marker found`); power off within 5 s of Home once (the log says
`marker found; falling back to Shanling`, the device boots to the stock Home); then Songs/Albums/Back,
Now Playing, Cover Flow, Shuffle, lock/unlock, idle timeout, USB mode in and out (you land on the
menu), Settings > Developer > Open Shanling Home and back by the icon, Boot to M1+ Music toggles and reboot, Main Menu changes and reboot, and the kill switch.

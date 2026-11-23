# List gestures

**Sources:** `patch/scroll.c`, `tools/pod.py` (`patch_scroll`), `SCROLL_PINS` in `tools/pod_pins.py`.
A swipe on a list must never play the song under the finger, and a touch on a list that is still
coasting must stop it and press nothing. The fix is one data word in AWTK's input path, not a code
hook: nothing of the stock text is overwritten, and it runs only for touches inside a `scroll_view`.
That covers every stock list (`list_view > scroll_view > list_item`: Songs, the queue, Folders,
Artists, our menu and settings lists) and the Albums grid / list. Cover Flow has its own touch layer.
Our lyrics page has no slidable axis, so this does nothing there; its own listeners handle it
([lyrics](lyrics.md)).

## The stock paths

- Pointer events go to the window, which dispatches to each widget: an optional
  before-children slot (zero in stock), then the **children first**, then the widget's own handler.
- **A `list_item`** on DOWN becomes pressed, grabs its parent (every later event of the gesture
  reaches this row) and arms a 30 ms timer for the pressed look. On MOVE of 11 px or more it
  cancels. On UP it dispatches a click if it is still pressed, with no position check. The abort
  event (`EVT_POINTER_DOWN_ABORT`) clears the press, so the following UP is no click.
- **A `scroll_view`** tracks pressed, dragged, the press position and the running scroll animator
  `wa`. On MOVE it decides by the slidable axes only (10 px or more, always true for
  `snap_to_page`): it then sends the abort to the children, marks dragged and returns without
  scrolling; later MOVEs scroll, but not while `wa` is set. On UP it decides the fling (a 200 ms
  animator). **The abort is never sent from UP**, and the UP reaches the scroll_view after its rows.

## Holes in stock

1. The row cancels only on a MOVE of 11 px or more, the scroll_view on 10 px or more. A gesture
   without such a MOVE (sparse samples in a quick flick: DOWN, one MOVE of 5 to 9 px, UP 60 px away;
   or DOWN and UP only) reaches the row's UP still pressed, so the row **clicks** (a song starts)
   while the scroll_view flings.
2. Nothing in DOWN looks at `wa`: a touch on a coasting list presses the row under the finger and
   the tap clicks it. The drag that follows does not move the list until the animation ends.

## The fix

The scroll_view vtable's before-children slot (zero in stock) is set to `m1plus_scroll_event`
(`demo_diff` allows exactly this word). It sees the event before the children:

- **DOWN on a coasting list** (a live animator on this scroll_view, not `snap_to_page`): destroy the
  animator, run the stock end handler (clears `wa`, sends the end events), let the scroll_view take
  its own press and return stop. The rows never see this DOWN; a drag scrolls from the touch and a
  tap is no click.
- **UP after a late drag** (pressed, not dragged, released at least 10 px from the press along a
  slidable axis): send the same abort the stock MOVE path sends, before the rows see the UP. The row
  drops its press and the release is no click; the fling is unchanged.
- **A lifted Home pin or playlist row** (`m1_lift_sv` is this scroll_view, set by [pins](pins.md) and by Edit mode's reorder in [songs](songs.md)): the `yslidable` byte is
  cleared before anything else, on every event, so the list neither slides with the drag nor sends
  the late-drag abort at the drop. One load and one compare for every other list.
- MOVE, key and wheel events: three compares and out. Only slidable axes count, so a horizontal drag
  in a vertical list (a slider in a settings row) is not aborted.

## Safety

- The pinned words (`SCROLL_PINS`: the vtable words, the dispatcher's call, the call sites and the
  field accesses) must all match or the build refuses, and the slot must be zero.
- The hook runs on the UI thread in the input path only: never at boot, in paint or in a timer. No
  allocation, no log, no syscall on the hot path.
- The kill switch (`home_off()`, both files) is read once, the first time a late-drag UP or a DOWN
  on a coasting list needs it, and the hook is then a no-op for the session. Creating the file
  mid-session takes effect at the next start.

## Limits

- Any scroll animation counts as a coast: a touch within the 200 ms of a programmatic scroll (a list
  scrolled to the playing song) stops it and is not a tap; tap again.
- A swipe starting on a button inside a row (the Main Menu's up arrow) is aborted like any swipe. A
  plain tap on that button still clicks it.
- The abort threshold is the stock 10 px. Scrolling on the first MOVE (the other half of the "not
  following" feeling) is a separate change.

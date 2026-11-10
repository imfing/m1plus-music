# Menu and Extras layout

Sources: `tools/pod_pages.py` defines rows/actions; `tools/pod_ui.py` builds assets;
`patch/menu.c` arranges them at runtime. Tests compare the Python and C models and run stock
layout/hit-testing. User instructions are in the [guide](../guide.md#find-your-way-around).

## Menu instances

| Instance | Layout |
|---|---|
| Home | No navbar; list y 10–440. Daily Mix, Recently Played and the mini player may be shown |
| Normal | 50 px navbar with Back, title and Now Playing; no Home-only sections or mini player |

Both use stock `list_view > scroll_view` with `scroll_bar_m`, 52 px `list_item` rows and the
stock row theme. The asset contains one row per `ITEMS` entry, then Extras. Never hard-code the
row count: Pod, Podcasts and Search are items too. Item ids are frozen (`ITEM_IDS`, asserted at build): `home-menu` stores them, so a new item is appended, never inserted, removed or reordered.

Default shown IDs are `12345`: Cover Flow, Albums, Artists, Songs and Playlists. Extras is
always visible and last. Settings (ID 18, `j`) is hidden by default and stays reachable from
the Extras navbar. Pod is ID 19 (`k`), Podcasts ID 20 (`l`), Search ID 21 (`m`: opens the library search page, `search_open()`, else the stock `search_page`; hidden from the menu by default, in the Library group of Extras) and Radio ID 22 (`n`: the Radio page, `radio_open()`; hidden by default, in the Library group after Podcasts; [radio](radio.md)). Their actions/pages are defined
once in `pod_pages.py`.

Hidden rows are invisible, insensitive, parked at y 0 and restacked after shown children.
`menu_arrange` sets positions, `virtual_h` and a clamped scroll offset, preserving the user's
place when a page returns to the foreground. The scroll bar and hit tests follow that layout.

## Home content

Child order is shown rows, Daily Mix section, Recently Played shelf, hidden rows, spacer.
`menu_daily` and `menu_shelf` share `mn_section` to show/resize/hide their section and arrange
again without losing scroll position. A hidden section contributes no height.

The mini player is the window's last child: hidden/insensitive `pod_minibar`, at (8, 384),
304 × 56. A queued track shows it and the 64 px `pod_pad` spacer, letting the final list item
scroll above the floating pill. Details: [mini player](minibar.md), [Daily Mix](dailymix.md),
[Recently Played](recent.md) and the [cover build line](homecover.md).

## Saved menu

`/mnt/data/m1plus/home-menu` contains `<shown IDs in order>[-<off IDs>]` with an optional final
newline. Characters are `ID_CHARS` (`0`–`8`, then `a`–`m`); total file length must be nonzero
and less than `MENU_FILE_MAX` (25 bytes).

- Each ID may appear once across both parts; at most one `-` is allowed.
- Settings cannot be off. Unknown characters, duplicates or oversized/missing data select
  the default menu with no off items.
- An empty body represented by a newline, or `-`, is valid: only Extras is shown.
- Showing an item clears its off flag; hiding it again returns it to Extras.

`parse_menu_full` and `mn_load` implement the same rules; tests compare a corpus and random
inputs. `format_menu`/`mn_save` serialize off IDs in Extras order. Saves are atomic; failures
restore the prior state. There is no legacy-format parser.

## Extras and its settings

`EXTRAS_GROUPS` defines Play, Library, Collections, Streaming (Subsonic, Tidal) and Tools. Extras shows items absent from
the main menu unless they are off; empty groups have no header. Each `pod_hdr0..4` is a 40 px
insensitive view with 20 px secondary-grey (#AAAAAA) text, not a clickable row. Shown headers/rows are restacked
in display order; hidden children follow. A missing header only removes that heading.

The navbar's `btn_settings` replaces the menu's Settings row on this page. It opens the
same Settings page, and failure to find it binds nothing. Existing names such as
`pod_rowN`, `pod_listview`, `pod_scrollview` and `scroll_bar_m` remain unchanged.

Settings → Extras lists only items hidden from the main menu, with switches for whether
they appear on Extras. Settings has no off switch. Rows stay in place while toggled; Extras
rereads the file when foregrounded. Both pages use `extras_display`/`extras_layout` and the C
equivalents; stock relayout is tested with headers and variable-height sections.

Stock destinations retain Home-dispatch fallback. Collection rows use the Songs page;
Genres/Composers use the Artists page; Update Library, Tidal and CD Ripper use stock pages.
See [Songs](songs.md), [Artists](artists.md) and [settings](settings.md).

## Other page assets

The navbar, icon slots and title widths follow [navbars](navbar.md). Cover Flow's
`view_covers`, caption/progress/cancel widgets must match `CF_*` in `offsets.inc`; landscape
rotates content inside the body without rotating the navbar. See [Cover Flow](coverflow.md).
Screenshot is a Developer action, not a menu item; its indicator/countdown is documented
in [Screenshot](screenshot.md).

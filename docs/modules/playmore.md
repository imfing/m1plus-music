# Now Playing's More menu

**Sources:** `patch/playmore.c`, `tools/mod_lists.py` (`edit_playmore`), `tools/pod.py`
`PLAYMORE_PINS`, `tools/mod_icons.py` (`PC_SHEETS`, `GLASS_SHEET*`).
The sheet Now Playing's "..." button opens is the stock `dialog/playmore_dialog`
(`ui/dialog/playmore_dialog.bin`: `list_view` > `scroll_view` > `list_item` rows `listitem0..6`).
Stock rows: A-B repeat (0), Playback speed (1, badges and `label1_msg`), Add to playlist (2), Online
search (3), Look up album (4), Look up artist (5), Delete song (6). M1+ Music turns it into an iOS
style bottom sheet with three pages (first, More, Display Mode) by one hook on the dialog's init.
Stock rows keep their own handlers; the payload moves rows, replaces behaviours (Look up album,
Look up artist, Add to playlist, Delete) and adds rows.

## What the user sees

The sheet is as high as its rows x 50, always on the screen's bottom edge, over the page dimmed. A
tap above it closes it. Switching pages only changes which rows show and swaps the glass picture;
there is no slide.

| Page | Rows | Height / glass |
|---|---|---|
| 1 (opens here) | Look up album, Look up artist, Add to playlist, **Display Mode** (chevron), **More** (chevron) | 250 px, `pc_sheet5` |
| 1 of a podcast episode (`pm.ep`) | **Go to Podcasts**, Playback speed, **Sleep Timer**, A-B repeat | 200 px, `pc_sheet4` |
| 1 of an audiobook part (`pm.book`, `bk_is_path`) | Display Mode, Playback speed, **Sleep Timer**, A-B repeat | 200 px, `pc_sheet4` |
| 2 (More; its back header returns to the page it came from) | back header **< More**, Playback speed, **Sleep Timer**, A-B repeat, **Cover & Lyrics**, Delete song (red `#FF6B6B`) | 300 px, `pc_sheet6` |
| Display Mode | back header **< Display Mode**, **Cassette Mode**, **Vinyl Mode**, **VU Meter Mode**, **Lyrics Mode** | 250 px, `pc_sheet5` |

Online search is never shown. Hidden rows are `visible=false` and `sensitive=false`.

- **Look up album** (`pm_on_lookup_album`): a click handler bound after the stock init, so it runs
  first. It finds the playing track's album in the library Albums list (`cc_find_album`, ASCII
  case-insensitive, Unknown Album never matches) before changing anything. Found: closes the sheet
  and opens our album page as the Albums grid does, with `songerinfoflag` set so a track tap on
  that page unwinds to the Now Playing already in the stack ([album-page](album-page.md)). A
  destroy handler on the new page clears the flag. An `albuminfo_page` in the stack is closed. On
  that page the navbar has no multi-select and no Now Playing button, and Back returns to Now
  Playing. Nothing playing, no album tag or an album the
  list lacks: `RET_OK` and the stock handler runs.
- **Look up artist** (`pm_on_lookup_artist`): opens our Albums page scoped to the playing track's
  artist (`albums_open_artist`, [artists](artists.md)), found in the list the Artists page shows, so it
  follows the Artist / Album Artist setting. Decision: in Album Artist mode a featured artist is not
  found and the stock handler runs, rather than changing the setting or guessing. The page opens
  first and the sheet closes after, so every failure leaves the sheet and stock's handler
  (including Cover Flow already open). On success `songerinfoflag` is set and released by the
  page's destroy, as for Look up album.
- **Subsonic tracks** (`pm_lookup_src`, `sba_rec_track`): both rows open the source's pages
  (`album_open_src`, `albums_open_src`, [subsonic](subsonic.md)); the card's library is never
  asked. Unknown to the cache: toast "Not found", sheet stays. A page of ours just closed still holds
  its window until stock's idle destroy, so the open is retried from `pm_pend_tick` (`PM_PEND_MS`
  30 ms, `PM_PEND_TRIES` 40) while Now Playing stays on top. The library Look up album waits the
  same way when our album page was just closed (`pm_local_tick`).
- **Display Mode** (`pod_mode`): the four Now Playing looks share one row so page 1 is not half
  modes. An episode's page 1 has none.
- **Cassette Mode**, **Vinyl Mode** and **VU Meter Mode** open their page over Now Playing
  (`tape_open`, [tape](tape.md); `vinyl_open`, [vinyl](vinyl.md); `vupage_open`, [vu](vu.md)) first and close the sheet once it
  is up; a page that cannot open leaves the sheet.
- **Lyrics Mode** opens the full-screen lyrics page (`idlelyrics_open_idle`,
  [idlelyrics](idlelyrics.md)) first, then closes the sheet. It needs lyric rows (`ly_has_rows()`),
  checked each time the page is shown and again at the tap; none: the row is dimmed (opacity
  100 of 255) and insensitive. The tap looks again (the track can change under the open sheet):
  no rows, nothing opens and the rows are laid out dimmed.
- **Go to Podcasts** calls `podcasts_go()` ([podcasts](podcasts.md)) and closes the sheet once the
  page is up.
- **Sleep Timer** opens our page ([sleeptimer](sleeptimer.md)) first. Label is the stock key
  `powerm_sleep`, so it follows Language. A window of ours is restacked with `m1_restack_window`
  rather than opened twice, so the Sleep Timer / Now Playing button cycle keeps one window; Back
  returns to Now Playing. The row shows with or without Wi-Fi; for an episode or part it is on page 1.
- **Cover & Lyrics** (`pod_art`) opens [onlineart](onlineart.md) first, then closes the sheet. It
  needs Wi-Fi (`get_wifisignal() > 0`, looked at each time page 2 shows and at the tap); without it
  the row is dimmed and insensitive. It is off for Subsonic tracks (`pm.srv`), and not shown for an
  episode or audiobook part (no album or song to look up; `pm_on_art` refuses them too).
- **Playback speed** row: the label reads **Speed** (box 96 px) and the four badges move right
  (36 px each, 40 px apart); the note reads **Files below 48 kHz only** in a 262 px box. Both fit
  in all 13 languages (`tools/pod_i18n.py`). The row's glyph is the Lucide `circle-gauge`.
- **Row height:** every row is resized to `PM_ROW_H` 50, so pages are exact and nothing scrolls.
- **Accent:** the stock row glyphs (`player_albuminfo`, `player_songerinfo`, `p_add`, `p_multiple`,
  `p_abrepeat`, `p_delete`) are tinted by exact name (`ACCENT_GLYPH_STOCK`, [accent](accent.md)).

## Glass

The sheet uses the glass of the Home mini bar and the lock card ([minibar](minibar.md),
[lockscreen](lockscreen.md)).

- **The image:** one picture per page, each its own height (a cropped taller picture showed a wrong top
  edge): `pc_sheet5.png` (320 x 250), `pc_sheet6.png` (320 x 300), `pc_sheet2.png` (320 x 100). Each is
  `mod_icons.glass_image(320, h, 18, fill=GLASS_SHEET_FILL, top_only=True)`: the dark gradient
  pane with a rim light, only the top corners rounded, fill alpha 0.88 (denser than the card's
  0.76 so the labels sit straight on it). `pod_glass` is the dialog's first child, an insensitive
  image `pm_arrange` resizes and re-pictures per page. The dialog itself is transparent. A
  9-patch is not used: a stretched middle would smear the gradient and rim.
- **Transparent rows, this dialog only:** inline styles per row, transparent except `pressed`
  (`#FFFFFF10`, 6 % white) and a `#FFFFFF22` hairline. A 20 % pressed band would take the red under 3:1.
- **Contrast** (checked by the test, over black / over the dimmed white): white row labels 15.5 /
  12.6, red Delete 5.53 / 4.59 (the weak one, which sets the alpha), Speed note 6.93 / 5.68.
- **Failed start:** the asset keeps its look: the stock rows lie on the dimmed page.

## Positioning (the bottom sheet)

The stock init moves the dialog to y 130; `pm_arrange` then moves it to 480 minus the page's height
and resizes it.

- **Tap above closes:** the stock handler (`EVT_POINTER_UP`, kept) closes when the pointer is above
  the dialog's y, which is exactly "above the sheet" at the bottom.
- **Another dialog opens over it** (Delete's confirm): stock's to-background handler moves the
  dialog back to y 130. Ours puts the sheet back on the bottom in the same dispatch, so it must run
  after stock's. It is bound on the **list_view**, not the dialog, because this AWTK's emitter runs
  the newest handler first and the window event visits the dialog's children after its own emitter.
- **The dim** is the dialog's own `highlight="default(alpha=130)"` property in the asset, read by
  the window manager when the dialog opens. It must be in the asset: the navigator runs the init
  too late for the window manager's setup.

## The hook

`dialog_playmore_dialog_init` (`j m1plus_playmore_init; nop`, trampoline resumes after the prologue),
pinned in `PLAYMORE_PINS`. It runs only when the sheet is built, so never at boot or in the main loop.
The stock init runs first. Then `pm_start` looks up widgets by name, checks the asset is the one it
knows (eighteen rows, `pod_glass`, the labels), sets the texts and registers thirteen handlers.
**Everything fallible happens before the first row moves**; any failure leaves the stock seven rows.
State is one `.scratch` struct cleared by the destroy handler; each handler checks its context is
the dialog the state belongs to, so a handler a failed start left behind does nothing.

`pm_arrange` (open and every page switch): every row is resized to 310 x 50 and returned to the normal
state; the page's rows are moved to `position x 50` and shown; the others are parked under the sheet
and hidden (both `visible` and `sensitive` false, since a hidden widget still takes touches); children
are restacked shown first (the layouter restacks visible children in child order, [home-guard](home-guard.md));
the dialog, list_view, scroll_view and bar are resized to the page's height and the dialog moved.

## Assets

`edit_playmore` asserts every stock widget keeps its type, name and rectangle. `ADD_EDITS` allows
only the new `pod_more*`, `pod_back*`, `pod_tape*`, `pod_vinyl*`, `pod_goep*`, `pod_art*`,
`pod_sleep*`, `pod_mode*`, `pod_lyr*` and `pod_vu*` widgets, and a new rectangle for the six speed-row widgets
(`PM_SPEED`). New rows are `list_item`s styled as the Add to playlist row (icon 24 x 24 at 14,13;
label 200 px at x 48; chevrons 13 x 22 at 285,14, ink x 288..298); the first row of each page has no
hairline. The dialog gets `highlight`. New row glyphs: `pod_ic_tape`, `pod_ic_vinyl`, `pod_ic_art`
(custom SVG in `assets/icons/custom/`), `pod_ic_sleep`, `pod_ic_mode`; `pod_ic_vu` is the Lucide `gauge`; `pod_ic_lyrics` (Lyrics Mode) is the Lucide `mic-vocal`.

## Delete and Add to playlist

- **A Subsonic stream is no file** (`sbs_playing_stream`): Add to playlist and Delete are dimmed and
  insensitive, and `pm_on_addpl` / `pm_on_delete` answer `RET_STOP`, because stock would write the
  stream address (with its login token) into a card playlist, or report a deleted song with no
  file. Stock's own stream types (2, 3, `0xf0`, `0xf1`) keep stock's rows. A downloaded Subsonic
  track is a file and keeps both rows. Checked at layout and again at
  the tap (`pm_stream_now`).
- **An episode or a book part is never deleted here.** Its page has no Delete row. The track's
  kind is read at every layout (`pm_kind_now`), and `pm_on_delete` asks again at the tap
  (`pm_spoken_now`): when the queue reached an episode or part under music's open More page, the
  tap lays out that track's page and deletes nothing.
- **Add to playlist opens our picker.** `pm_on_addpl` redoes stock's handler (`0x4798f0`) and stops
  it. Stock's `player_addplayList` runs first (it fills the tags a folder-played row lacks; -5
  with no track or a stopped player leaves stock's handler to say its message). Then the sheet
  closes and `picker_open_rec(0xf001, the playing row)` opens the [picker](picker.md) the track
  rows' Add to Playlist opens. The picker holds a copy of the row, so the add is the track that
  played at the tap. Where the picker cannot open, stock's page opens as stock opens it
  (`playlist_page`, `PICKER_PLAYING` `0x2f001`). Stock's own stream lists keep stock's handler.
- **Delete asks first, about one track.** `pm_on_delete` redoes stock's handler (`msg_delsong`
  confirm; answer `0xa` deletes from the queue, `0x14` the file too) with two differences. The
  sheet closes before the confirm opens (the glass confirm is translucent). The track is checked
  again after the answer, because playback can move on under the modal and stock's
  `delete_playqueue_file` takes whatever plays then. The queue id and path (`PM_DEL_PATH` 768 bytes;
  longer is refused) must still match and not be a Subsonic stream, else nothing is deleted and
  the message is `msg_delsongfailed`.

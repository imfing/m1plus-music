# Keyboard

Code: `patch/keyboard.c`, `patch/keyboard.h` (API and geometry constants). Asset: `tools/pod_ui.py` `build_keyboard_page` (`ui/m1plus_keyboard.bin`), geometry in `tools/pod_keyboard.py`,
glyphs in `tools/mod_icons.py` (`KEYBOARD_IMAGES`, `qk_*`). Tests: `test/pod/keyboard.py` (sections: base, name, password, refocus, gap, asset, setting, zh, strip, hit, lang_gap), `test/pod/pinyin.py` (the engine on its own).
Preview: `tools/preview_keyboard.py`. No hook, no new import, no thread; one timer only while the delete key is held. Built for podcast search (iTunes search itself is not part of it); its consumers are the Playlists page's New playlist and library Search (below, and embedded in the Search page); stock's T9 popup
(`ui/user_keyboard.bin`, pages laid out 640 px wide in a 320 px popup) is not used. With Settings > Keyboards > Chinese (Pinyin) on, it also types Chinese (below).

## What it is

One page of stock AWTK widgets: the plain navbar (Back = cancel, Now Playing), a search field, and a 180 px pad of buttons at the bottom of the 450 px window (the bottom of the 480 px
screen), `#1C1C1E`. White and grey only, no accent colour anywhere (the greys are the design's, a few levels toward blue).

* **Pad**: four rows at a 44 px pitch, 6 px padding top and bottom, keys 36 px high. Char keys 29 px wide, 3 px gaps, ten across (a 1.5 px margin: 2 left, 1 right), rows of nine and seven
  centred (x 18 and 50). Third row: shift 40 wide at the left, delete 40 at the right. Bottom row: 123 / ABC (74), space (163), Search (74). Char keys `#4A4A4E` (also space), function
  keys `#2E2E32`, rounded 5 px, letters 20 px. There are 26 char key widgets (`kb_k0`..`kb_k25`): the payload moves, resizes, relabels and hides them per page (hide = invisible +
  insensitive). Function keys: `kb_shift`, `kb_shifton` (the lit key, `#E5E5EA` with a dark arrow), `kb_sym`, `kb_del`, `kb_mode`, `kb_space`, `kb_go`, and `kb_lang` (below).
* **Pages**: lowercase, uppercase, **123** (`1234567890`, `- / : ; ( ) $ & @ "`, `. , ? ! '` on five 41 px keys, `#+=` at the left of the third row, ABC bottom left) and **#+=**
  (`[ ] { } # % ^ * + =`, `_ \ | ~ < > € £ ¥ \``, the same third row, 123 where #+= was). Shift is one-shot: an empty field starts on capitals, the first letter goes back to lowercase, an
  emptied field (delete, clear) turns it on again; no caps lock. ABC from the symbol pages returns to capitals for an empty field, lowercase otherwise. Space is ignored at the start and after a space (not in a password field, nor with `KB_LITERAL`). The backtick took the bullet's place on the #+= page, so every printable ASCII character is typeable (the page has ten keys a row; the bullet is the least used).
* **Pop-up**: while a char key is down, `kb_stem` (as wide as the key, from 22 px above it down over it) and `kb_pop` (46 x 50, radius 10, `#6E6E73`, 10 px above the key, kept 1 px inside the
  screen) with the letter at 34 px. Both are children of the window after the pad (the pad would clip them) and are **insensitive for life**: only `widget_set_visible` is ever called on them.
  A key types when the finger lifts on it (its click).
* **Delete** acts on touch down and repeats while held: 80 ms ticks, the first repeat after six (480 ms). The timer exists only between touch down and up/abort/background.
* **Field** (`kb_field`, 300 x 36 at (10, 58), `#1C1C1E`, radius 10; it must stay sensitive: stock's hit test does not look into an insensitive parent, test-caught): magnifier, grey placeholder
  (`kb_hint`, shown only when empty), the text (18 px, white), a white 2 x 22 caret (not blinking), and the clear button (`kb_clear`, a 16 px disc with an x drawn about the disc's own centre at 16 x and box-filtered, `mod_icons.clear_disc`: its ink centre is within 0.05 px of the disc's, was 0.85 px left with the old odd-canvas crop; tested from the committed PNG, a 36 px touch area; shown only with text).
  The caret is at text start (30) + the measured width + 1 px (`widget_measure_text` on `kb_text`: the stb rule, advance + 1 px a glyph; 9 px a character if it cannot be measured). A text wider
  than 228 px shows its end after an ellipsis (leading characters dropped until it fits); the whole text is kept and returned. At most 63 bytes; delete removes a whole UTF-8 character.

## The gap rule

A touch on the pad that hits no key goes to the nearest key, as on an iPhone: every key's touch area effectively grows to fill the 3 px gaps, the 8 px gaps between rows and the pad's margins.
The device tap log (155 taps) had no systematic offset (letter keys: mean -2, +3 px from the centre) and 9 misses (6 %), all in the 1 to 4 px gaps, mostly the 8 px gaps between rows just above
delete and Search. Geometry stays; the pad's own events resolve the rest:

* AWTK sends a touch that lands between keys to the pad (`kb_pad` is sensitive; its `EVT_POINTER_DOWN`, `_UP` and `_ABORT` are bound). On the down event `kb_down(e, from_pad)` measures the touch
  against the rectangles of the keys that are there now (`kb_rects`: char keys, the left key (shift, lit shift or the pinyin separator), delete, 123 / ABC, the language key when present, space,
  Search), by the **squared distance from the point to each rectangle** (0 inside). The nearest wins, the first of equals in that order. `tools/pod_keyboard.py nearest_key` is the same model; the
  tests sweep a grid over the pad on every page (and with the language key) against it.
* The resolved key is **pressed at once**: char keys show the pop-up of that key, any key looks pressed (`widget_set_state "pressed"`, "normal" when released), delete deletes and starts its repeat.
  The key is **clicked when the finger lifts** (`kb_gap_end(1)`); abort, the page going to the background or destroy lets go without typing.
* The same touch reaches the key and the pad whichever way AWTK passes events on (unverified which): only the first sighting counts (the dedupe on time and position), a touch
  inside a key's rectangle is never resolved by the pad, and if the pad resolved a touch that the key also got (the two models disagree at an edge pixel) the key wins and the pad's resolution is dropped.

## Keyboards (Settings > Keyboards) and the language key

The setting is two switch rows, English (always on, not switchable) and Chinese (Pinyin) (default off, `/mnt/data/m1plus/keyboard-pinyin`): [settings](settings.md) "Keyboards". `keyboard_open` reads it.

* **Off**: the keyboard is exactly the one above: no language key, space 163 px wide, the dictionary and the engine never touched.
* **On**: row four is `123 / ABC` (74), the **language key** `kb_lang` (40 wide, function colour, x 79), space (now x 122, 120 wide), Search. The key is on every page and shows the layer a tap goes to:
  `中` while on English, `EN` while on Chinese (`LANG_TAGS`; characters, not translated). If `gpinyin.dat` is not there (`access`), or the engine will not open when the key is tapped, **the key goes away**
  (`kb.layers = 1`, space wide again), English stays. Nothing crashes.
* The layer the last keyboard ended on is remembered **for the session** (`kb_memo`, a scratch word outside the page's state): the next keyboard starts on it (and opens the engine at once). Turning the
  setting off in Settings forgets it.

## Layers and the Chinese (Pinyin) layer

A layer is a `struct kb_layer` of functions: `enter` (open what it needs; 0 when ready), `leave`, `compose(c)` (a letter key on its letter page; 1 when taken), `backspace`, `flush` (commit what is
pending), `pending`, `reset`, and the `tag` the language key shows. English has none of them (letters type as they are). The page tables (`KB_ROWS`), the field, the pop-up, the gap rule and delete's repeat are
shared. A Korean 2-beolsik composer (jamo into syllable blocks) or a romaji-to-kana one plugs in as another table entry with its own compose / backspace / flush, drawing its candidates through the same strip
(`zh_add`, the pool and `zh_render` are the strip's, not pinyin's); kanji conversion would need a dictionary that is not here. Not implemented.

**The Chinese layer** has the English layer's pages with these differences: its letter page is always lowercase and has **no shift** (nothing is capitalised; switch to English for capitals) and the pinyin
separator `'` where shift was (`kb_sym`, label `'`, same geometry); the 123 and #+= pages are the same and punctuation there stays **ASCII** (`. , ? ! '`), no fullwidth `，。？！` (kept simple; a later
change is one more page table). The engine opens when the layer is first used (`zh_enter`: `access` on the dictionary, close stock's dead object if its global holds one, `im_open_decoder`, check `inited_`;
an engine somebody else initialised is used as it is and left open) and **closes with the page** (`zh_leave` in the destroy handler: `im_close_decoder`, the global is NULL again, the megabyte is back).

* **Composing.** A letter appends to the pinyin string `zh.raw` (at most 39 letters; `A-Z` are lowercased, `'` only after a letter and never twice in a row), then `im_reset_search` + `im_search` (0.1 to 2.5 ms on the
  device) and `im_get_spl_start_pos` for the segmentation. **Nothing goes into the field while composing.**
* **The strip** (`kb_strip`, window child 36 px high at y 234 directly above the pad, ends where the pad begins, `#2A2A2C`; hidden and insensitive when nothing is shown; the search field (y 58 to 94)
  is not covered and nothing else moves): at the left `kb_py`, the pinyin as the engine segments it (`ni hao`, `xi'an`; letters it could not read follow as typed; 16 px `#AEAEB2`; wider than 120 px:
  its end after an ellipsis), a 1 px divider, then **the candidates view** `kb_cands` (the only sensitive widget in it). Candidates are a pool of 12 label widgets `kb_c0..11` (20 px white, insensitive) moved by the
  payload: candidate k always sits in widget `k % 12`; each item is as wide as its text plus 12 px a side (at least 36, at most 230; text width by the stb rule, truncated advance + 1 px a glyph, measured
  on the item's own font), side by side from the view's left edge; only those intersecting the view are shown. Up to 100 candidates are taken from the engine, 12 at a time, more as the row is scrolled to
  within 160 px of the end of what was read; their UTF-8 is kept in a 4 KB pool.
* **Touch on the strip** (`zh_on_strip`, down / move / up / abort of the view): a press highlights the item under the finger (`kb_chl`, `#4A4A4E`, radius 5, behind the items, insensitive); a move of 6 px makes it a scroll
  (the row follows the finger, clamped to its ends, the highlight goes, the lift takes nothing); a lift without that **takes the item**. No coasting, no overscroll.
* **Taking a candidate** (`zh_take`): the text goes into the field; `im_choose(k)` makes the engine fix it and `im_get_fixed_len` says how many characters (one syllable each), so the pinyin from
  `sp[fixed]` on stays. A long input is taken in steps: `woxihuantingboke` offers `我喜欢听博客`, `我`, ...; tapping `我` puts 我 in the field and the strip shows `xi huan ting bo ke` with the candidates of the
  rest (`喜欢听博客` first). The rest is a **fresh search** (the engine's fixed prefix and its context are dropped on purpose: delete and the strip then have one simple state). When the pinyin is used up the
  strip shows predictions.
* **Space** commits candidate 0 (the engine's best for everything left, a sentence for a long input) and shows predictions; a tail of letters the engine cannot read is committed as typed. **Search** with pinyin
  pending does the same (`flush`) and then searches the text: decided so that Search never loses what was typed and the text is Chinese, not raw letters; with no candidate at all (`vvv`) the letters
  as typed. Back with pinyin pending cancels (nothing is committed). 123 / ABC / #+= and the language key flush first.
* **Delete** removes the last letter of the pinyin first (re-search; an empty pinyin hides the strip), then text. With predictions showing the first delete hides them and deletes the last character. Held, it
  repeats the same way (the timer ends when both the pinyin and the text are gone). Clear drops the pinyin too.
* **Predictions** (`zh_predict`): after a commit the strip, with no pinyin and no divider, offers `MatrixSearch::get_predicts` of the last up to seven Chinese characters of the field (a trailing run of three
  byte characters; none for anything else): 你好 -> 啊 吗 像 的 了 好 多 久; a tap appends the word and asks again. A letter, space, 123 or the language key takes them away.
* **Limits**: 63 bytes of text; a commit that does not fit puts in as many whole characters as do (`kb_insert_fit`), never half a character. 12 widgets, 100 candidates, 4 KB of candidate text, 39 letters.
  The engine has no learning (a user dictionary never re-ranks anything, see below), so there is nothing to save.

## API

```c
int keyboard_open(const char *title, const char *placeholder, const char *initial,
                  kb_done_fn on_done, kb_cancel_fn on_cancel, unsigned flags);   /* patch/keyboard.h */
```

`title` / `placeholder` are UTF-8 and already translated (`TR()`), NULL keeps the page's title / no hint. Search with a non-empty text (spaces at both ends trimmed; an empty text does nothing)
calls `navigator_back()` and then `on_done(text)`; Back (navbar or hardware key) calls `on_cancel()` (hardware Back: from the destroy event). Callbacks run on the UI thread with the page closing:
use only what they are given. `int keyboard_busy(void)` tells whether a keyboard page (or the embedded pad) is up or not destroyed yet, i.e. whether `keyboard_open` would refuse for that reason; a -1 with `keyboard_busy()` false is a genuine failure (asset not ours, page would not open). One keyboard at a time: `keyboard_open` returns -1 while the previous page is not destroyed yet (also from inside a callback), or when the asset is not ours.
Flags of `keyboard_open`: `KB_LONG` (4) lifts the text limit from `KB_MAX` 63 to `KB_MAX_LONG` 255 bytes (the podcast search field takes a feed address; `kb.max` is set at open, the buffer and the field's shown text are sized for 255, a longer initial text is cut at 255 on a character boundary; tested in `test/pod/keyboard.py` `base_tests`); `KB_DONE` (2) makes the action key read **Done** (`widget_set_tr_text(kb.go, "Done")` at open; the asset's label stays Search for everyone else, same width, same colours); there is no touch log any more (the old `KB_LOG` flag and its text file are gone). An empty or all-space field on the action key does nothing and the page stays (nothing is closed or called), so a naming caller never gets an empty name. Strings are keys of `tools/pod_i18n.py` (`Keyboard`, `Keyboards`, `English`, `Chinese (Pinyin)`, `space`, `Search`, `Done`, `Type here`, 13 languages; key labels are characters
and `123 / ABC / #+=`, not translated). Callers need nothing for Chinese: the setting and the language key are the keyboard's.

**Consumers.** Library Search embeds the pad in its own page (`keyboard_attach`, below; `docs/modules/search.md`) and Playlists > ... > **New playlist** (`patch/playlists.c` `pl_create`: title the stock `playlist_create`, hint the stock `msg_newplaylists`, `KB_DONE`, no cancel callback; `pl_named` is the done callback and makes the playlist, shows the stock "full" / "exists" boxes from inside the callback and reads the page again: docs/modules/playlists.md "Create"). The text limit there is the keyboard's 63 bytes (stock's edit allowed 127). Test: `name_tests`.

**Tidal > Search** (the stock page's `search_edit`, `patch/tidalkb.c`, payload hook 27; [tidalkb](tidalkb.md)): the pad is embedded in the stock page with `keyboard_attach` (the call that focused the edit and popped stock's T9 attaches it instead; the asset gains our field in the search bar and the pad at the bottom of the window). The text goes into the stock edit on every change (`on_change`), the action key runs stock's search routine `0x4c4740` and hides the pad (`keyboard_show(0)`), a tap on the bar shows it again. Test: `test/pod/tidalkb.py`.

## Embedded in another page (`keyboard_attach`)

The Search page (`docs/modules/search.md`) has the pad on its own window so that nothing opens or closes while the user types. The code is shared, not copied: `keyboard_open`'s body is split into
`kb_init` (the widgets by name through `kb_find`, the bindings, the layers, the first page, `kb_refresh`) and what a page of its own adds (the window, the title, `KB_DONE`, Back, the destroy
handler). The asset side is `keyboard_pad_widgets()` in `tools/pod_ui.py`: the pad, the candidate strip and the pop-up, which the keyboard page and the Search page both end with (byte for byte equal,
tested in `test/pod/search.py` `asset_tests`).

```c
int  keyboard_attach(void *win, const char *placeholder, int text_x, int text_w, int caret_y, unsigned flags, kb_change_fn on_change, kb_go_fn on_go);
void keyboard_detach(void);      /* the page's destroy event: the timer, the engine, the state */
void keyboard_show(int on);      /* the pad and the strip shown / hidden (hidden: invisible and insensitive, the caret goes, a held key and the pop-up are let go) */
int  keyboard_shown(void);
void keyboard_set_mask(int on);  /* password field: one dot a character (on) or the text; the caret follows what is shown */
void keyboard_set_go(const char *key, int enabled);   /* the action key's label (a string key; NULL keeps it) and whether it works */
void keyboard_go(void);                               /* the action key as if pressed (a page's own Search button): pending pinyin committed, then on_go */
const char *keyboard_text(void); /* the committed text */
```

The page's window holds `kb_pad`, `kb_strip`, `kb_stem`, `kb_pop` and a field (`kb_field`, `kb_mag`, `kb_hint`, `kb_text`, `kb_caret`, `kb_clear`) by those names; `text_x`, `text_w` and `caret_y` are the
field's inner geometry in that page (the keyboard page uses `KB_TEXT_X`, `KB_TEXT_W`, `KB_CARET_Y`: `kb.tx`, `kb.tw`, `kb.cy`). `on_change(text)` is called at the end of `kb_refresh`, so on every change of the
committed text and also when a layer or page switch refreshes the field (the caller ignores a repeat); a Chinese candidate still being composed is not in it. The action key (`kb_go`, reading
`Search` as in the asset, or what `keyboard_set_go` set) commits what is pending and calls `on_go`; no page is closed and there is no cancel. The pad starts shown. One keyboard at a time: `keyboard_open` and `keyboard_attach` refuse while
either exists; `keyboard_detach` frees it (the next `keyboard_open` works). Tests: `test/pod/search.py` `embed_tests` and `live_tests`; the existing keyboard sections run unchanged.
The Wi-Fi Join Wi-Fi Network page ([wifi](wifi.md) "The Other Network flow") attaches the pad once, with `KB_LITERAL` (plain text, capital start, clear button, spaces typed as pressed: an SSID has leading and doubled ones), and serves its two fields (Name, Password) in turn with `keyboard_refocus` (below); the Security picker that opens over it needs no keyboard, so the pad stays attached under it.

`int keyboard_refocus(placeholder, text_w, flags, text, on_change, on_go)`: another field of the same page takes the pad (the page moves the field widgets itself). The widgets and their event bindings stay (no second `widget_on` on the keys); the new field's `flags` (plain or `KB_PASSWORD`), text room, placeholder, text (cut at the limit; `on_change` gets it) and callbacks replace the old ones; what was pending is dropped (a pinyin composition and its strip, a held key, a pop-up); the layers and the first page are chosen again by `kb_start` (the tail of `kb_init`: a password field is English only, a plain one gets the language key and the session's remembered layer back; the Chinese engine an earlier plain field opened stays open, so it is opened once). The mask follows the flags (`KB_PASSWORD` = masked; `keyboard_set_mask` after it for an open eye) and the action key's label and dimming are the page's to set again (`keyboard_set_go`). -1 when no embedded keyboard exists. Test: `refocus_tests`.

### Password mode (`KB_PASSWORD`, `keyboard_set_mask`, `keyboard_set_go`)

The Wi-Fi password page ([wifi](wifi.md) "The password page") attaches the pad with `KB_PASSWORD` (8): **English only** (no language key, space is 163 px wide, no pinyin composition or candidate strip and no engine, whatever the Chinese (Pinyin) setting or the session's remembered layer); the **letter page starts lowercase** and an emptied field never turns capitals on (shift still gives one capital); **space** is typed anywhere (first, doubled, last); the text is returned **untrimmed**; no clear button (the page has an eye instead); at most `KB_PASS_MAX` 127 bytes (a WPA3 password; `kb.max` follows the field's flags, also in `keyboard_refocus`; a plain field stays at 63). The field is **masked by the keyboard**: `kb_refresh` shows one `•` (U+2022) per character, cut with the usual ellipsis (the end of the dots shown) and measures the caret on what is shown, so the caret is right in both modes; `keyboard_set_mask(0)` (the eye open) shows the text. The consumer therefore owns no field rendering at all. `keyboard_set_go(key, enabled)` sets the action key's label (`widget_set_tr_text`, Join on the password page) and, with `enabled` 0, dims it (`widget_set_state` `disable`, whose text colour is `PK.KB_DIM`, `kb_button(dim=)`) and makes it insensitive; `kb_finish` also returns at once while it is off, and a touch the gap rule resolves to it does nothing and shows no pressed look. A search field is unchanged. `keyboard_detach` clears the typed text with the state.

**Consumers.** Radio > Search (the page's own field and pad, `keyboard_attach` as the Search page: `rp_on_go` fetches the results below the field; docs/modules/radio.md), Podcasts > Search (a tap on the search field opens it with `KB_LONG`, title `Apple Podcasts`, placeholder `Search Apple Podcasts` (the level's field hint too; the level's navbar title is Apple Podcasts as well); `pg_srch_done` / `pg_srch_cancel` in `patch/podcasts.c` only record what happened and the page handles it when it is in front again: docs/modules/podcasts.md "Pages and controls") and Playlists > ... > **New playlist** (`patch/playlists.c` `pl_create`: title the stock `playlist_create`, hint the stock `msg_newplaylists`, `KB_DONE`, no cancel callback; `pl_named` is the done callback and makes the playlist, shows the stock "full" / "exists" boxes from inside the callback and reads the page again: docs/modules/playlists.md "Create"). The text limit there is the keyboard's 63 bytes (stock's edit allowed 127). Test: `name_tests`.

## Tests, preview

`make test TEST=keyboard`: asset geometry, colours (no accent), `keyboard.h` against `pod_keyboard.py`; every page's widget moves in the payload against `pod_keyboard.layout`; typing, shift, 123 / #+=,
space rules, the 63 byte limit; delete, repeat, abort, background; clear; the caret by `StbText` width at every length, a long text; the pop-up (positions, edge clamping, never sensitive); Search, Back,
destroy, one-at-a-time, missing widget; stock's `widget_find_target` on the real tree (a touch anywhere on a key and at its corners lands on it, gaps on the pad, the pop-up and hidden
widgets take nothing); strings per language. **Gap rule**: a grid of about 800 touches over the pad on each of the four pages (and the Chinese layer with the language key) against `nearest_key`, the
press / lift / abort / background behaviour, delete from the gap above it, a touch the key and the pad both hear types once. **Setting and layers** (`ZhMachine`: the keyboard machine over **demo's real
engine** on the real dictionary, `pinyin.py`'s `Engine`): the language key present or absent and where space is, the dictionary missing, an engine that will not open (scripted), stock's dead object, an
engine somebody else opened, open and close with the page, the layer kept for the session. **Chinese layer**: nihao (candidates, pinyin, geometry), delete, space, predictions and their chain, a long sentence
in steps against fresh engine searches, jianpin, the separator, Search with pending / unreadable / mixed text, Back, clear, repeat, the limits, a glyph in the font for every candidate of common inputs.
**Strip**: the highlight, tap, scroll, the ring of widgets, scrolling to the 100th candidate and tapping one far along, and demo's hit test on the strip. `Settings > Keyboards` is in `test/pod/menu.py`.
`uv run python -I tools/preview_keyboard.py work/mod-release out/preview/keyboard.png` draws the tree's real rectangles, colours and glyphs for all pages, the strip states (the candidate lists are the real
engine's answers) and the Keyboards page.

## Not verified on a device

Verified on a V2.1 build (the tap log, 155 taps): no systematic offset, 9 misses in gaps (fixed by the gap rule); the engine opens `gpinyin.dat` in 76 ms with about 1 MB, searches take 0.1 to 2.5 ms, candidates
equal the emulation's, the UTF-8 log is right. Still open:

1. Does the pad get `EVT_POINTER_UP` / `_ABORT` for a touch that started on one of its gaps (the gap rule types on the lift; AWTK passes `EVT_POINTER_DOWN` to the pad, up is the same path)? Does a pad handler
   also hear touches that start on keys (the dedupe and the key-wins rule cover both)? Does `widget_set_state "pressed"` show on a key the finger is not on?
2. Rounded `bg_color` buttons (`round_radius` 5) and the icon-only buttons; delete repeat feel (480 ms, 80 ms); the pop-up repainting over the pad and over the strip; key press colours.
3. Is `widget_measure_text` of the field, the pinyin label and the candidates equal to the stb model (caret, ellipsis, item widths)? Do items clipped by the candidates view clip at its edge (a candidate half
   out of the view at the left edge, the divider)?
4. Does `EVT_POINTER_MOVE` reach `kb_cands` for a finger that stays on it (as the rails do), is a 6 px threshold right, does the row feel right without coasting?
5. Does the 中 / EN key read well at 18 px, is the pinyin separator key (`'` in shift's place) discoverable, are capitals missed on the Chinese layer? Is space at 120 px enough?
6. Candidate quality for the user's own text; whether stock's own T9 popups (Wi-Fi password) still work after the engine was opened and closed by this page (their init opens the global anew);
   stack use of the engine on the UI thread while typing.
7. Order of `navigator_back` and the callback when a caller opens a page from `on_done` (New playlist shows a stock message box from there and the Playlists page reads its list there: check the box shows over the Playlists page, the new playlist is listed, and the page is not blank or double-loaded); whether the hardware Back key's destroy-time `on_cancel` is safe for a caller that opens a window.
8. Not done: caps lock, blinking caret, a Search key dim when empty, accents, fullwidth punctuation on the Chinese layer, Korean and Japanese layers, a number-row variant (rejected), coasting on the strip.

## Pinyin engine

Question that was asked: can stock's built-in Google Pinyin engine give our keyboard Chinese input? **Yes, from the payload, with the dictionary stock already ships.** No hook, no new import, no thread.
Pins: `PINYIN_PINS` and `FUNCTIONS` in `tools/pod.py`; test `test/pod/pinyin.py` (demo's own engine code under Unicorn); addresses `addresses.md` "Pinyin engine".

### What is in demo

* **The engine** is AOSP's PinyinIME (`ime_pinyin::MatrixSearch`, `DictTrie`, `DictList`, `SpellingTrie`, `NGram`, `UserDict`, ~`0x5bf9b0`..`0x5ceb40`) behind C entry points over one global `MatrixSearch*`
  at `0xa0a360` (NULL until opened). The first byte of the object is `inited_`; `search`, `get_candidate` and `get_candidate_num` return 0 / NULL when it is 0.
* **Stock's own wrapper** `inputmethod_module` (global object `0xa0c2bc` = `0xa10000 - 0x7d44`; `+0` a deque of `wordinfo`, `+4` a byte the constructor `0x5bf2d0` sets, `+8` / `+0xc` the max lengths 9 / 12, `+0x10` the
  candidate count) is called by `keyboard_init` `0x5b25d4` from `user_keyboard_init` `0x547b9c`. **`init(this, path, 9, 12)` ignores its path argument**: it opens the fixed `/usr/dict_pinyin.dat` and
  `/usr/dict/dict_pinyin_user.dat` (`im_open_decoder`), then `im_set_max_lens(9, 12)`. Its `get_candidate(i)` returns the candidate as a malloc'd **UTF-8** string (`0x8aed58`, an empty string, when there is none) and `search` keeps 42 of the 62
  candidates of "nihao". We use the C entry points, not the wrapper.
* **When stock initialises it**: not at boot. `user_keyboard_init` is the page-init of the window named `user_keyboard` (dispatched by the function the symbols call `on_wm_timer_rgbled_state`, `0x4d06cc`), which the
  stock text-entry dialogs open (add Wi-Fi network, new playlist name, keyword search). So the global is NULL at boot, and **after any stock keyboard has been shown it is a dead object** (pointer set, `inited_` 0):
  the rootfs has neither `/usr/dict_pinyin.dat` nor `/usr/dict`, so stock's Chinese input finds no dictionary, and its init is called again at every such window.
* **The dictionary**: `/release/assets/default/raw/data/gpinyin.dat` (1,068,442 bytes, AOSP `dict_pinyin.dat` format) is in the rootfs and **no code names it** (the string `gpinyin` is not in demo). `im_open_decoder(sys, user)` takes any path,
  so ours opens it in place; **`tools/mod_space.py` must never list it in `REMOVE`**. (`suggest_words_zh_cn.dat`, 238,016 bytes, is unreferenced too; its format was not looked at.) Both paths are required: a NULL one fails, a user path that
  can neither be read nor created (`/proc/m1plus/pinyin-user.dat`) leaves the user dictionary NULL, which the engine tolerates.
* **Encoding**: candidates are **UTF-16LE `char16`**, zero-terminated (`你好` = `0x4f60 0x597d`). `im_get_candidate(i, buf, max_len)` fills `buf` and returns it (NULL past the last, or with no engine); the layer converts to UTF-8
  itself (`u16_to_u8`, surrogate pairs included; the buffer is 48 units, a sentence candidate is at most 39 characters). After `im_choose`, candidate 0 is the whole text so far (fixed prefix included) and the others are the candidates for the rest.

### The API (all callable with the engine open; search input is lowercase letters and `'`, capitals are lowercased, at most 39 letters)

| call | does |
|---|---|
| `im_open_decoder(sys, user)` `0x5c7350` | destroys any object at the global, builds a new one, loads the dictionary; returns 1, or 0 and leaves a dead object |
| `im_close_decoder()` `0x5c7534` | closes, frees (~1 MB) and sets the global to NULL |
| `im_search(buf, len)` `0x5c760c` | the candidate count (0 when not initialised); keeps the input for the next call |
| `im_get_candidate(i, buf, max_len)` `0x5c7754` | the i-th candidate as UTF-16 |
| `im_choose(i)` `0x5c77c0` | fixes candidate i as a prefix; returns the candidates left (1 when the whole input is covered); `im_get_fixed_len` `0x5c7824` counts the characters fixed |
| `im_get_spl_start_pos(&p)` `0x5c778c` | the number of syllables decoded; `p[0..n]` the start of each in the input string (`p[n]` the end) |
| `im_reset_search()` `0x5c76e8` | forgets the input and the fixed prefix |
| `im_delsearch(pos, ..)` `0x5c7678`, `im_cancel_last_choice` `0x5c77f4`, `im_get_sps_str` `0x5c7720` | delete from the input, undo a choice, the pinyin the engine read (not used: the layer re-searches) |
| `MatrixSearch::get_predicts(this, history, out[][8], n)` `0x5c6834` | the words that usually follow a 1..7 character history (no C entry point; a plain member call with the global as `this`) |

### How smart it is (emulation, the real dictionary; top 5 of N)

| input | N | candidates |
|---|---|---|
| nihao | 62 | 你好 你 拟 尼 呢 |
| zhongguo | 47 | 中国 中 种 重 钟 |
| bokesou | 80 | 博客搜 博客 播客 博克 波 |
| yinyue | 107 | 音乐 隐约 银月 因 引 |
| shanling | 81 | 山岭 山 删 闪 善 |
| **nh** | 436 | 你好 女孩 您好 你会 男孩 |
| **zg** | 1435 | 这个 中国 整个 最高 找个 |
| **bjdx** | 838 | 北京大学 比较多 比较 比较大 不记得 |
| zhongg | 52 | 中国 中共 忠告 终归 重工 |
| nihaom | 63 | 你好吗 你好 你 拟 尼 |
| **woxihuantingboke** | 45 | 我喜欢听博客 我 喔 窝 握 |
| zhongguoren | 48 | 中国人 中国 中 种 重 |
| yinyu (partial) | 108 | 阴雨 隐喻 阴郁 音域 因 |
| xi'an / xian | 207 / 169 | 西安 西岸 系 西 洗 / 先 线 县 现 咁 |
| **zongguo** (z for zh) | 43 | 总过 总 宗 纵 踪 (no 中国) |
| **lihao** (l for n) | 191 | 利好 里 李 离 力 (no 你好) |

So: abbreviations (jianpin), a syllable followed by initials, a whole sentence with no separators (candidate 0 is the whole phrase: 我喜欢听博客, 北京大学, 中国人民), a half-typed last syllable and `'` all work;
**there is no fuzzy matching** (z/zh, n/l, an/ang are taken literally). `choose`: "nihao" `choose(2)` (拟) leaves 41 candidates with 1 character fixed (`拟好 号 浩 豪 ...`); `choose(0)` leaves 1 with 2 fixed;
"woxihuantingboke" can be taken in steps (`choose(1)` 我 leaves 208: 我喜欢听博客 喜欢 喜欢听 系 ...). Predictions after a choice: 你好 -> 啊 吗 像 的 了 好 多 久; 中国 -> 人 队 特色 政府 经济; 我 -> 们 的 国 是 也; 博客 -> 圈 网 首页 文章 网站;
北京 -> 市 大学 时间 人 奥运. **Learning**: with an unreadable user path the engine has no user dictionary at all; with a path it can create it makes a 40 byte file and four picks of 拟好 change no order, in the session or after a reopen
(`try_add_cand0_to_userdict` runs, `add_lma_to_userdict` is never reached), so there is no re-ranking to rely on and nothing to persist.

**Segmentation** (`im_get_spl_start_pos`): `nihao` 2 syllables at `[0, 2, 5]`; `woxihuantingboke` 6 at `[0, 2, 4, 8, 12, 14, 16]`; one per initial for `nh` and `bjdx`; `nihaom` 3 (a half syllable counts); `xi'an` `[0, 3, 5]` (the
apostrophe sits before the second syllable); `nihaov` 2 (the `v` is past the last syllable); `vvv` none and no candidate. A candidate of n characters covers the first n syllables: after `im_choose` of
`拟` (1), `我` (1) or `北京大学` (4) `im_get_fixed_len` is 1, 1 and 4 and the segmentation is unchanged. The layer takes the pinyin from `sp[fixed]` on as what is left.

### Hanzi to pinyin (for a library search where "zjl" finds 周杰伦)

Feasible, from the same dictionary, with three stock member functions the payload does not call yet: with `engine = *0xa0a360`, `trie = *(engine + 0xc)` (the `DictTrie`, vtable `0x978e7c`), `dl = *(trie + 4)` (the
`DictList`) and `spt = *(trie + 8)` (the `SpellingTrie`, also the global `0xa0a370`): `DictList::get_lemma_id(dl, &ch, 1)` is 0 for a character that is not in the dictionary, otherwise
`DictList::get_splids_for_hanzi(dl, ch, 0, ids, 8)` gives the spelling ids (all readings: 行 -> hang heng xing, 大 -> da dai), and `SpellingTrie::get_spelling_str(spt, id)` the text (upper case, `ZhOU`; lower it).
周杰伦 gives `zhou` `jie` `lun` (initials `zjl`), 林俊杰 `lin jun jie`, 北京大学 `bei jing da|dai xue`, 王力宏 `wlh`. **Never call `get_splids_for_hanzi` for a character without the `get_lemma_id` check**: it
dereferences the result of its binary search and crashes (Latin and fullwidth letters, a rare Ext A character, an unassigned code point). It needs the engine open (1 MB, 76 ms): a search page would open it for
the page's life as the keyboard does. Test: `test/pod/pinyin.py` (all of the above on demo's real code; `Engine.hanzi_spellings`). The payload uses it for the library search's initials index (`patch/search.c` `se_read_hanzi`, `search.md`); the page holds the engine open through `pinyin_hold` / `pinyin_release` (patch/keyboard.c), which also stops the Chinese layer closing it under the page.

### Stock's own keyboard

Stock's own Chinese input stays dead (it asks for `/usr/dict_pinyin.dat`); shipping that file would wake it in Wi-Fi and playlist-name entry and cost 1 MB of rootfs: not planned. The engine is opened only
while one of our keyboards is up on the Chinese layer and closed with it; stock's keyboard init replaces whatever is at the global (and leaves a dead object) every time it runs.

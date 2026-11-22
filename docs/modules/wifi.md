# Wi-Fi supplicant and Wi-Fi page

**Sources:** `assets/wpa/` (config, `start.S`, `shim.c`), `tools/mod_wpa.py`, `patch/wifictl.c`
(control socket), `patch/wifipage.c` (pages), `tools/pod_ui.py` (`build_wifi_page` and the sub-pages).

Stock V2.1 starts hostap `wpa_supplicant` 2.9 from `/usr/bin/wifi_connect.sh`. It was built with only
EAP-WSC, no SAE and no OWE, so WPA-Enterprise, WPA3-only and Enhanced Open networks cannot join. This
feature ships hostap 2.12 beside it, changes only that script, and replaces Settings > Wi-Fi with a page
of our own that speaks to the supplicant over its control socket. The stock binaries and the stock page
are untouched and stay the fallback. One hook (21) sends the All System Settings hub's Wi-Fi row to our
page ([payload](payload.md)).

## Stock facts relied on

- The player kills the supplicant by name (`killall -9 wpa_supplicant`) and starts it through
  `wifi_connect.sh` at every connect, so our binary must be named `wpa_supplicant` and any state must live
  in the configuration or files, not the process.
- The script exits 0 when `/mnt/data/wpa_supplicant.conf` is missing, else brings up `wlan0` and starts
  the supplicant with that config (`update_config=1`, control socket `/var/run/wpa_supplicant`).
- Stock reads `key_mgmt=`, `wep_key0=` and `auth_alg=` from the real config for its own saved list, and
  joins any scan flag containing `WPA` as PSK. WPA3-only, Enterprise and OWE networks therefore fail on
  stock's page. Stock sends `SET_NETWORK ssid "%s"` raw while `scan_result` printf-escapes non-ASCII bytes,
  so a name with a typographic apostrophe joins wrongly there.
- The driver (RTL8733BS) has the cfg80211 external-auth hooks SAE needs.
- Stock's `wpa_cli` 2.9 speaks the same control protocol; only the daemon parses the new variables, so
  `wpa_cli` and `libwpa_client.so` stay byte-identical.

## What ships

| File | Content |
|---|---|
| `/usr/lib/m1plus/wpa_supplicant` | hostap 2.12, stripped, mode 755 |
| `/usr/bin/wifi_connect.sh` | stock script with the start lines replaced (pinned by SHA-256), a rescan after start and a start log |
| `ui/m1plus_wifi.bin`, `patch/wifictl.c`, `patch/wifipage.c` | the Wi-Fi page and sub-pages |
| `/mnt/data/m1plus/wifi-networks` (run time) | saved networks a stock 2.9 supplicant cannot read |

Compiled in: nl80211, control interface, OpenSSL TLS, EAP-PEAP / TTLS / TLS / MSCHAPv2 / GTC / MD5 / PWD /
WSC, SAE, OWE, Suite B, FT, WNM, PMF, background scan, WPS. Left out: dbus, AP, P2P, mesh, DPP, FILS,
EAP-FAST/SIM, WEP and **stdout debugging** (`-d` prints nothing; it costs about 135 KB). `CTRL-EVENT-*`
messages and `wpa_cli status` remain.

### Start-up choice

`wifi_connect.sh` runs ours when `/mnt/mmc/m1plus-off` does not exist, the file is executable and
`ours -v` exits 0 (a missing library, a corrupt file or a loader error selects stock). Otherwise it runs
stock's supplicant with the same arguments. It chooses anew at each connect, so the kill switch or a
reflash takes effect at the next Wi-Fi start.

**Fallbacks to stock** (there is no switch; ours is the default):

- the kill switch `/mnt/mmc/m1plus-off`;
- our binary failing `-v`;
- ours exiting with a non-zero status at start (for example on a config it cannot read, such as a saved
  WEP network, which hostap 2.12 built without WEP rejects). The script then starts stock's on the real
  file.

The kill switch also decides the pages: the All System Settings > Wi-Fi row opens the stock page and stock's
supplicant serves it. That is the **only route for WEP**: our page does not offer WEP and hostap 2.12 is
built without it. The page asks the running supplicant `GET_CAPABILITY key_mgmt` (looking for `SAE` /
`OWE`), because stock's can be the one running after a fallback. Then Open and WPA/WPA2 networks, saved
networks, forget, disconnect and hidden WPA2 work (a WPA2/WPA3 network joins as WPA2); a WPA3-only or
Enhanced Open network answers "This network isn't supported". `wifi-networks` stays on flash and its
networks return when ours runs again.

**Rescan after start.** A supplicant whose first scan joins nothing never scans again (seen on the device:
the home network was in that scan's results, and it stayed `DISCONNECTED` until a scan was asked, then joined in
4 s). So after the start, a background watcher polls `wpa_cli status` once a second and, while the state is
`DISCONNECTED` or `INACTIVE`, asks one `scan` at 15, 30 and 60 s. It stops at `COMPLETED`, when the supplicant
stops answering (after the first 5 s), or at 60 s, and does nothing with no saved networks. A new start stops the
previous watcher (`/tmp/m1plus-wifi.pid`).

**Start log.** Every run of the script appends to `/tmp/m1plus-wifi.log` (RAM, gone at power off; moved
to `.log.1` past 64 KB). Each line starts with the uptime in seconds: `wlan0`'s operstate (or `missing`) and
the `rtk_hciattach` / `bluetoothd` pids at the start, the supplicant chosen with its config and exit code, each
rescan with the state and `wpa_cli`'s answer, and the end state. A Card Script reads it
(`cp /tmp/m1plus-wifi.log* /mnt/mmc/`).

**Configuration files.** Stock 2.9 rejects a whole config that holds `key_mgmt=SAE` / `WPA-EAP` / `OWE`
(or `sae_password`, `ieee80211w`, `eap`...), so those networks never go into the real
`/mnt/data/wpa_supplicant.conf`: the stock supplicant must always be able to read it. When ours is chosen
the script writes `/tmp/m1plus-wpa.conf` (the real config, a blank line, then `wifi-networks` when it
exists) and starts ours on it (on the real file if the copy cannot be written). `update_config=1` makes
`SAVE_CONFIG` write that copy; the page splits it afterwards into the two files. With stock chosen the
copy is removed and `wifi-networks` is never read.

## The Wi-Fi page

Settings > Wi-Fi is the `ACT_STOCK` row (value On / Off from `wififlag`). A tap calls `pd_open_page`
with `wifipage_open` (`patch/m1plus.c`), and only when that returns 0 opens `systemset/wifi_page` as
before; long-pressing the Control Center Wi-Fi tile opens or restacks the same window rooted
([pulldown](pulldown.md)), and the sub-pages open via `pd_window_open`. The hub's row is hooked (hook 21, `wifi_hub_open`): our page, else stock's
when `/mnt/mmc/m1plus-off` exists or ours will not open. The stock page is always opened afresh, never
restacked: its init scans on every open, and a restack would show old networks. The hook runs on a tap
only and is not on the boot path; it reads the kill switch so the stock page stays reachable for WEP.

**Design.** The Settings pages' grouped cards ([settings](settings.md#cards)) under our navbar, with:

- **Card 1:** the Wi-Fi switch and, when a network is connected or joining, its row below it.
- **My Networks:** saved networks in range, then saved ones out of range (fan all dim). Absent when empty.
- **Networks:** the others by signal, then **Other...**; a header spinner while a scan runs.
- **Off:** the switch row alone.
- **A network row:** check (connected only) or a join spinner; the name cut with an ellipsis (`az_fit_room`,
  laid out again on `EVT_WINDOW_WILL_OPEN` once the styles are resolved); a lock for networks that need a
  key; the signal fan; the info glyph (x 274). No security line, no per-row delete mark. The fan is Lucide
  `wifi` in dim grey with the level's arcs white over it (levels 4 / 3 / 2 / 1 show `wifi` / `wifi-high` /
  `wifi-low` / `wifi-low`; a saved network out of range shows none).
- **Pools.** Every row is a pooled widget in display order: 1 connected, 16 saved (`WP_MY`), `WF_MAX` others,
  Other..., between spacers and the two headers. The payload shows, moves and styles rows; nothing is built
  at run time. Row children are insensitive; the row takes the tap.

**Behaviour** (one 250 ms timer owned by the page; a control call is one datagram that answers at once, a
missing supplicant after at most 1.5 s):

- **On / off** through stock's `wifi_switch(1)`. Turning on while Bluetooth is on shows the coexistence
  warning ([overlays](overlays.md)) and leaves Bluetooth on. Wi-Fi switched elsewhere is followed.
- **List.** `SCAN_RESULTS` (one row per SSID, strongest access point's flags, hidden networks left out)
  merged with `LIST_NETWORKS` (same name = saved). Levels use stock's thresholds (>= -65 dBm four, -75..-66
  three, -80..-76 two, else one). The page reads `STATUS` and `LIST_NETWORKS` every second, scans on open,
  and scans again every 12 s while in front and neither the supplicant nor the page is joining (also when
  connected). No manual refresh. While a joining row shows and no scan of ours runs, each poll also reads
  `SCAN_RESULTS` (a read, not a scan), so an auto-joined network gets its bars. Rows are laid out again
  only when what they show changed.
- **Screen off.** With the screen dark and no join under way the tick does nothing (no query, no scan, no
  spinner) and slows to 1 s (`POD_DARK_MS`); the first lit tick catches up. A join keeps the normal pace.
- **Names.** `wf_unescape` decodes the supplicant's printf escapes; `SET_NETWORK ssid` sends hex, so any
  name joins.
- **Security** from the scan flags (`wf_security`):

  | Flags | Security | Joins with | Commands |
  |---|---|---|---|
  | `[ESS]` | Open | either | `key_mgmt NONE` |
  | `RSN-OWE` | Enhanced Open | newer only | `key_mgmt OWE`, `ieee80211w 2`, no password |
  | `[WEP]` | WEP | not offered | toast "WEP isn't supported" |
  | `WPA..-PSK` | WPA/WPA2 | either | password page, `psk`, `key_mgmt WPA-PSK` |
  | `PSK+SAE` | WPA2/WPA3 | either | newer: `psk`, `key_mgmt WPA-PSK SAE`, `ieee80211w 1`; stock: as WPA2 |
  | `SAE` only | WPA3 | newer only | `sae_password`, `key_mgmt SAE`, `ieee80211w 2` |
  | `EAP` (also Suite B) | Enterprise | not supported | toast "Enterprise isn't supported yet" |

  "Newer only" with stock's supplicant gives the toast "This network isn't supported". A saved network of
  any security joins without asking.
- **Connect a new network.** The password page for a secured one, then `ADD_NETWORK`, the `SET_NETWORK`
  lines, `priority` (minutes since the epoch, so the last chosen wins), `ENABLE_NETWORK`, `SAVE_CONFIG` +
  split, `SELECT_NETWORK`. A refused step removes the half-made network and toasts "Couldn't connect".
  Passwords (`wf_pass_ok`): WPA2 and the PSK half of WPA2/WPA3 are 8..63 printable ASCII or exactly 64 hex
  digits (sent unquoted as the raw PSK); WPA3 is 1..127 printable ASCII. Anything else keeps Join dimmed.
- **Auto-Join is kept across a select.** hostap's `SELECT_NETWORK` disables every other network in memory,
  and a later `SAVE_CONFIG` would write `disabled=1` for all of them. So before each select the page notes
  the Auto-Join-off ids (`wp_snap_off`: all of `LIST_NETWORKS`, read with `LAST_ID=` in case a reply is cut
  at 4096 bytes; ids below `WF_OFF_IDS` 1024) and afterwards sends `ENABLE_NETWORK all` and
  `DISABLE_NETWORK` for those. Side effect: a failed select may fall back to another saved network.
- **Failure.** A network marked `[TEMP-DISABLED]` (wrong password) or not up in 20 s toasts "Couldn't
  connect" once. Tapping a saved Auto-Join-off network enables it again.
- **Info glyph** (a tap at x >= 264 on any row) opens the info page. **Disconnect:** a tap elsewhere on the
  connected row asks "Disconnect Now?" (stock's), then `DISCONNECT`; the info page has no Disconnect.
- **Other...** opens the Join Wi-Fi Network page.
- The stock monitor (`network_checkstatus`) still finds the connection through the supplicant's state and
  starts DHCP; the page writes none of its words.

**Files.** After a `SAVE_CONFIG` the page reads the saved file (the copy, else the real file). `wf_split`
writes every `network={}` block whose keys are all ones stock writes and whose `key_mgmt` is `NONE` /
`WPA-PSK`, with every line outside the blocks, to `/mnt/data/wpa_supplicant.conf`, and the other blocks to
`wifi-networks` (`home_write_atomic`; ours first). Without a copy, the blocks already in `wifi-networks` are
kept and new ones appended. A configuration of 12 KB or more is not split. `wifi-networks` is a settings
file ([settings](settings.md)): Reset All Settings or a per-file delete removes it and with it the saved
WPA3 / Enhanced Open networks; the stock networks stay.

**Limits of the list.**

- At most `WF_MAX` 32 networks: the connected one, saved ones, then the strongest unsaved. A connected or
  saved network absent from a full scan stays.
- Of the saved networks 16 (`WP_MY`) have a row and the page reads 16 (`WP_KNOWN`). The Auto-Join state of
  saved networks below id 1024 survives a select; a higher id is enabled by it.
- Joining a name that is already saved adds a second entry. A saved weak network beyond the 48 strongest
  scan results is listed as out of range.
- Enterprise networks and captive portals are not supported (the toast above; no sign-in page).

### The info page

The info glyph opens `m1plus_wifiinfo` (`wi_open`; no action id, no hook). The title is the network's name
(cut with an ellipsis); when cut, the whole name is in one or two grey lines above the first card
(`wf_name_lines`, shared with the Bluetooth device page). Cards are 20 px apart.

- **Saved network:** **Forget This Network** (white, centred; "Delete Record?" then `REMOVE_NETWORK` +
  `SAVE_CONFIG` + split, back to the list), the info card, and **Auto-Join** (the stock switch; on = not
  `[DISABLED]`).
- **Not saved:** the info card and **Join** (the list's own path: the password page for a secured network,
  the toasts for WPA3 on stock's supplicant, Enterprise and WEP).
- **Info card:** Security (Open, Enhanced Open, WEP, WPA/WPA2, WPA2/WPA3, WPA3, Enterprise: one label for
  every EAP network); IP Address and Router, only while this is the connected network with an address
  (`STATUS` `ip_address`; the gateway from `/proc/net/route`, wlan0's default route; no gateway, no Router
  row).
- **Auto-Join** does `ENABLE_NETWORK` / `DISABLE_NETWORK`, then `SAVE_CONFIG` + split. `disabled` is a stock
  key, so `disabled=1` stays with its block. hostap disconnects when the network it is on is disabled; the
  page does not work around that.
- **Refresh.** No timer of its own: the list's timer calls `wi_refresh`, which finds the network by its
  name bytes and re-lays only when something shown changed. A network that left the scan stays as it was; a
  network forgotten elsewhere becomes unsaved; Wi-Fi turned off goes back to the list.
- **Windows.** The list stays under the info page (its timer runs, no scan while it is not in front). The
  destroy handler frees only its own state, so Back and Now Playing end in either order. Taps are ignored
  under a dialog (`wp.modal`).

### The password page

A secured network that is not saved opens `m1plus_wifipass` (`wk_open`) instead of stock's password dialog.

- **Look.** Navbar "Enter Password" (Back cancels, nothing is sent); a grey line `Enter the password for
  “<name>”`; one card with the **Password** label, the keyboard's own field and an eye button; a grey
  "Incorrect password" line (hidden until a refusal, gone at the first key); then the keyboard pad. All
  above the pad ends by y 182 so the candidate strip is never covered. No Join button: the keyboard's action
  key reads **Join** (Войти / Увійти in Russian and Ukrainian), dimmed until `wf_pass_ok`. Neutral colours.
- **Keyboard.** `keyboard_attach(..., KB_PASSWORD, ...)`: English only, lowercase start, masked dots with
  the eye ([keyboard](keyboard.md)). The typed text lives only in the keyboard's state, is wiped by
  `keyboard_detach` in the page's destroy handler, is copied to a stack buffer for `wp_join` and zeroed. It
  is never written to a file by the page, never logged, and there is no recent list.
- **Join** (`wk_go`) runs `wp_join`, goes back and the list shows the joining spinner, then the check.
- **Wrong password.** When the join came from this page the network is **removed** (`REMOVE_NETWORK`,
  `SAVE_CONFIG`, split: a wrong password stays in neither file) and the page **opens again** over the list
  with an empty field and "Incorrect password" (no toast). If the list is not in front or a dialog is up
  the network is removed and the old toast shows. A saved network that fails keeps the toast and stays
  saved. Back from the reopened page returns to the list.
- Wi-Fi turned off under the page goes back (and takes the info page under it); a missing widget or
  keyboard asset backs out and sends nothing.

### The Other Network flow

Other... opens **Join Wi-Fi Network** (`m1plus_wifiother`, `wo_open`) and a **Security picker**
(`m1plus_wifisec`, `ws_open`), in the iOS sheet's layout.

- **Look.** Navbar "Join Wi-Fi Network" (Back = cancel; the keyboard's action key does the joining).
  Card 1: **Name**. Card 2: **Security** (value and chevron, opens the picker) and, under a hairline,
  **Password** with the eye. With Security None the Password row goes. The "Incorrect password" line sits
  under card 2. Rows are 48 px (not 52) so everything above the pad ends above the candidate strip.
- **One keyboard, two fields.** `keyboard_attach` once; `wo_focus` serves the active field with
  `keyboard_refocus`, moving the one `kb_field` widget to that row. The other row shows its value in a
  static label. Name is plain mode (capital start, clear button, pinyin when on); Password is
  `KB_PASSWORD`. Both values live on the page so they survive switching and the picker; the password is
  wiped on join and destroy and never written to a file or logged.
- **Action key.** Name of a secured network: **Next** (moves to Password). Name with Security None, and
  Password: **Join**. Dimmed until it can work: the name is 1..32 bytes and, on Password, `wf_pass_ok`.
- **Security picker.** **None**, **WPA2/WPA3** (default), **WPA3**, with the check on the current choice. A
  tap sets the choice and goes back. WPA3 with stock's supplicant toasts "This network isn't supported" and
  keeps the picker open.
- **Join** (`wo_go`): `wp_join` with `hidden = 1`: `ADD_NETWORK`, hex `ssid` (spaces kept literally,
  `KB_LITERAL`), `scan_ssid 1`, the security's keys, `priority`, enable, save + split, select. A hidden
  open or WPA2 network stays in the real config (stock reads `scan_ssid`); WPA2/WPA3 and WPA3 go to
  `wifi-networks`.
- **Failure.** A wrong password or no answer in 20 s removes the network from the supplicant and both
  files and reopens this page with Name and Security kept, the Password field active and empty, and the
  "Incorrect password" line. An open hidden network that never appears toasts "Couldn't connect" and is
  removed the same way.
- Wi-Fi turned off goes back; under the picker the picker goes first.
- **Scan on open.** `wifipage_open` sends `SCAN` right after the first `STATUS` / `LIST_NETWORKS`, so the
  header spinner is up at once.

**Deviations from the stock page:** our layout (cards, My Networks / Networks, fan, lock, info glyph,
check or spinner instead of state words, no Scanning row, Other... for Add Network); a saved network out of
range is listed (stock lists scan results only); new texts in 13 languages (`tools/pod_i18n.py`).

## Build

`tools/mod_wpa.py --fetch` ([workflow](../workflow.md)) downloads the SHA-256-pinned inputs into `work/cache/wpa/dl`
(`make doctor` and CI check them); the normal build never touches the network. Inputs: the hostap 2.12
source and five Debian 10 mipsel packages, of which only `usr/include` is extracted (nothing executed).

- Compiled with Homebrew clang for mips32r2, o32, NaN 2008, `-mfp64`, `-Oz`; linked with lld `-no-pie`
  against the stock `.so` files as link inputs. Debian's crt files are legacy-NaN, which lld refuses to mix,
  so `assets/wpa/start.S` and `shim.c` replace them. The result is cached by input hash and reproducible.
- `verify()` fails the build unless the binary has the stock supplicant's `e_type` and `e_flags`, the NaN2008
  interpreter, a non-executable stack, `_IO_stdin_used` exported (crt1's new-stdio marker; `shim.c` defines it), only NEEDED libraries that exist on the stock rootfs, and every
  imported symbol exported by the stock library at a version <= glibc 2.28.
- The build adds `usr/lib/m1plus` and the binary (`added_rels`) after `mod_cacerts`. The package packs
  to 55,615,488 bytes against stock's 55,738,368: little headroom, which is why debug output is compiled
  out.

The binary cannot be run on the host (no MIPS Linux), so the start-up `-v` self-check is the safety net for a load
failure.

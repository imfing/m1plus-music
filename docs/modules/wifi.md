# Wi-Fi supplicant and Wi-Fi page

Stock V2.1 starts hostap `wpa_supplicant` 2.9 from `/usr/bin/wifi_connect.sh`. It was built with only EAP-WSC, no SAE and no
OWE, so WPA-Enterprise, WPA3-only and Enhanced Open networks cannot join. This feature ships a newer build beside it, changes
only that script (`tools/mod_wpa.py`, sources in `assets/wpa/`) and replaces Settings > Wi-Fi with a page of our own that speaks to the
supplicant over its control socket (`patch/wifictl.c`, `patch/wifipage.c`, `tools/pod_ui.py build_wifi_page`; [The Wi-Fi page](#the-wi-fi-page)).
The stock binaries and the stock Wi-Fi page are untouched (the stock page is the fallback; see Start-up choice). Enterprise networks
(certificates, identity) and captive portals are later phases (see Later phases).

## Stock facts

- `/usr/sbin/wpa_supplicant` 900,792 bytes, v2.9, non-PIE `ET_EXEC`, `e_flags` `0x70001405` (NaN2008, o32, mips32r2, `-mfp64`),
  interpreter `/lib/ld-linux-mipsn8.so.1`, NEEDED `libssl.so.1.1 libcrypto.so.1.1 librt.so.1 libnl-3.so.200
  libnl-genl-3.so.200 libc.so.6`. Methods: only EAP-WSC (no PEAP, TTLS, TLS, MSCHAPV2, GTC); no SAE, no OWE (the config parser still
  knows the `sae_*` / `owe_*` keys). `/usr/sbin/wpa_cli` (86,824 bytes) and `/usr/lib/libwpa_client.so` are 2.9 too.
- Libraries on the rootfs: glibc 2.28 (Codescape), OpenSSL 1.1.1f (`libssl.so.1.1`, `libcrypto.so.1.1`), libnl 3.4
  (`.so.200.26.0`), `libgcc_s.so.1`. `/etc/m1plus-cacert.pem` is this mod's Mozilla bundle ([update](update.md)); `/etc/ssl/certs` is empty.
- Driver: `module_driver/rtl8733bs.ko`, RTL8733BS v5.14.1.1 (2023-06-14). It has `rtw_cfg80211_external_auth_status`
  / `cfg80211_rtw_external_auth` and `WLAN_AKM_SAE`, so SAE through the supplicant's SME is expected to work (device-unverified).
- `wifi_connect.sh` (stock SHA-256 `24676db6...e332`, 385 bytes): `killall udhcpc`, `killall wpa_supplicant`, exit 0 if
  `/mnt/data/wpa_supplicant.conf` is missing, then `ifconfig wlan0 up`, `wpa_supplicant -Dnl80211 -iwlan0 -c/mnt/data/wpa_supplicant.conf -B`,
  `touch /tmp/wpasupplicant_initsuccess`. The default config (`/release/assets/default/raw/wpa_supplicant.conf`) is
  `update_config=1`, `ctrl_interface=/var/run/wpa_supplicant`, `ctrl_interface_group=0`.
- The player (`release/bin/demo`; addresses from `tools/stock.py`): `killall -9 wpa_supplicant` (`0x756884`; `networkDisconnect`,
  `networkStop`, two sites in `networkCheckSsidPassword`) then `wifi_connect.sh` (`0x756840`, also `wifi_connect.sh &`
  in `networkStart`). It talks to `/var/run/wpa_supplicant` with its own embedded wpa_ctrl: `ADD_NETWORK`, `SET_NETWORK %d ssid "%s"`
  (`wifiSetSSID` `0x73f180`), `psk "%s"` (`wifiSetPsk` `0x73f290`), `key_mgmt %s` (`wifiSetKeyMgmt` `0x73f318`), `scan_ssid`
  (`0x73f208`), `priority` (`wifiSetPrior` `0x73f42c`), `wep_key0`, `auth_alg`, enable/select (`wifiSetNetworkEnable` `0x73f4b4`),
  `SAVE_CONFIG` (`wifiSaveConfig` `0x73f5cc`). Because it kills by process name the new binary must be named `wpa_supplicant`.
- Scanning: `networkGetWifiResult` (`0x5d84e4`) runs `wpa_cli scan_result > /tmp/scan_result` (`0x7569e4`, ref `+0x6c`) and parses
  the file. `wifi_action_connect` (`0x5071f4`) compares the flags column with `strcmp(flags, "[ESS]")` (`0x74e9b4`, ref `0x507294`)
  for an open network (`networkAddSsid`), reconnects a known one (`networkPrioritySsid`), else calls `networkCheckSsidPassword`
  (`0x5d89b8`), which tests the flags for `"WPA"` (`0x756a20`) -> `key_mgmt WPA-PSK` (string `0x748dec`, ref `0x5d8b7c`) or `"WEP"`
  (`0x756a24`, password lengths 5/13/10/26) and uses NONE otherwise. The saved list is read back from the config file
  (`networkGetSsidList` parses `key_mgmt=`, `wep_key0=`, `auth_alg=`). Connected state is `wpa_state` `COMPLETED` (`networkGetWifiSignal`).
- Consequences with stock pages: a scan flag containing `WPA` is always joined as PSK (WPA3-only `[WPA2-SAE-CCMP]` and Enterprise
  `[WPA2-EAP-CCMP]` fail; WPA2/WPA3 transition `[WPA2-PSK+SAE-CCMP]` works as before); OWE (`[RSN-OWE-CCMP]`, no `WPA`) is tried as NONE
  and fails. Stock's `SET_NETWORK ssid "%s"` is raw text while `wpa_cli scan_result` printf-escapes non-ASCII bytes (`\xe2\x80\x99`); the
  expected result is a wrong SSID for names such as an iPhone's with a typographic apostrophe (unverified on hardware).

## What ships

| File | Content |
|---|---|
| `/usr/lib/m1plus/wpa_supplicant` | hostap 2.12, stripped, 792,648 bytes, mode 755 (new directory) |
| `/usr/bin/wifi_connect.sh` | stock script with the start lines replaced (pinned by SHA-256, any other input fails the build) |
| `ui/m1plus_wifi.bin`, payload `patch/wifictl.c`, `patch/wifipage.c` | the Wi-Fi page ([below](#the-wi-fi-page)); no hook, no stock binary change |
| `/mnt/data/m1plus/wifi-networks` (written at run time) | the saved networks a stock 2.9 supplicant cannot read |

Stock `/usr/sbin/wpa_supplicant`, `wpa_cli` and `libwpa_client.so` stay byte-identical. `wpa_cli` 2.9 speaks the same control
protocol (`STATUS`, `SCAN_RESULTS`, `LIST_NETWORKS`); the daemon, not the client, parses the new `SET_NETWORK` variables, so
replacing it is not needed.

Compiled in (`assets/wpa/config`): nl80211, ctrl iface, OpenSSL TLS 1.0-1.3, EAP-PEAP / TTLS / TLS / MSCHAPv2 / GTC / MD5 / PWD / WSC,
PKCS#12, SAE, OWE, Suite B (192 bit), FT (802.11r), WNM, PMF (always in since hostap 2.10), background scan, 11ac/11ax IEs, WPS.
Left out: dbus, AP, P2P, mesh, DPP, FILS, interworking/HS2.0, EAP-FAST/LEAP/SIM/AKA, debug file and **stdout debugging**
(`CONFIG_NO_STDOUT_DEBUG`: `-d` prints nothing; the debug strings cost about 135 KB compressed). `CTRL-EVENT-*` messages (including
`CTRL-EVENT-EAP-TLS-CERT-ERROR`, EAP failure and SAE/auth results) and `wpa_cli status` remain.

### Start-up choice

`wifi_connect.sh` runs ours when `/mnt/mmc/m1plus-off` does not exist, the file is executable and `ours -v` exits 0 (so a missing
library or symbol, a corrupt file or a loader error selects stock); otherwise it runs stock's `wpa_supplicant` with the same arguments
as before. Interface and control socket are stock's. Ours is chosen anew at each connect, so the kill switch or a
reflash takes effect at the next Wi-Fi start without rebooting.

**The configuration ours reads.** Stock 2.9 rejects a whole config that holds `key_mgmt=SAE` / `WPA-EAP` / `OWE` (or `sae_password`, `ieee80211w`, `eap` ...), so those networks never go into the real
`/mnt/data/wpa_supplicant.conf`: the stock supplicant (the fallback, the kill switch, a later reflash of stock firmware) must always be able to read it. When ours is chosen the script first removes
`/tmp/m1plus-wpa.conf`, then writes it as the real config, a blank line and `/mnt/data/m1plus/wifi-networks` (when it exists) and starts ours with `-c/tmp/m1plus-wpa.conf` (the real file when the copy
cannot be written). `update_config=1` makes the supplicant's SAVE_CONFIG write that copy; the page splits it afterwards into the two files ([The Wi-Fi page](#the-wi-fi-page)). With stock chosen the copy is removed and
the real file is read as before; `wifi-networks` is never read. **A start that fails hands over to stock:** when ours exits with a status other than 0 (a config it cannot read, for instance a saved
WEP network, which hostap 2.12 built without `CONFIG_WEP` rejects) the script starts stock's supplicant on the real file. The old card probe file
`m1plus-wpa-extra.conf` is gone: the page adds WPA3 and Enhanced Open networks; enterprise ones come with the enterprise form.

**Fallbacks to stock** (there is no switch; ours is the default): the kill switch `/mnt/mmc/m1plus-off`, our binary failing `-v`, and ours exiting with a non-zero status at start. The kill switch also decides the pages: with the file present the All System Settings > Wi-Fi row opens the stock page and the stock supplicant serves it, which is the **only route for WEP** (the page of ours does not offer WEP and hostap 2.12 is built without it); remove the file and ours is back at the next connect and the next tap. The page still asks the running supplicant `GET_CAPABILITY key_mgmt` (looking for `SAE` / `OWE`), because stock's can be the one running after a fallback: then Open and WPA/WPA2 networks, saved networks, forget, disconnect and hidden WPA2 networks work (a WPA2/WPA3 network joins as WPA2), and a WPA3-only or Enhanced Open network answers "This network isn't supported"; `wifi-networks` stays on flash and its networks come back when ours runs again.

## The Wi-Fi page

Settings > Wi-Fi is the `ACT_STOCK` row (`STOCK_WIFI`, arg 0, its On / Off value from `wififlag`; no action id was added): the tap calls `wifipage_open()` (`patch/m1plus.c`) and only when that returns -1 (window or
asset that will not open) `navigator_to("systemset/wifi_page")` runs as before. The stock All System Settings hub opens the same page: its Wi-Fi row (the thunk `0x4b1440`) calls `navigator_to("systemset/wifi_page")` at `0x4b1460`, and that `jalr` is hooked ([payload](payload.md) hook 21): `wifi_hub_open(name)` (`patch/wifipage.c`) opens our page and returns 0, and otherwise opens the stock page with stock's `navigator_to(name)` when `/mnt/mmc/m1plus-off` exists or `wifipage_open()` returns -1 (stock's delay slot still loads the argument, the thunk's return value is unused). The stock page is always opened afresh, never restacked: its init scans (`wifi_scan`, `0x4b115c`) on every open, while a restack runs no init (the `EVT_WINDOW_TO_FG` handler `0x4b0a34` only rebuilds the list from the old results and restores the poll timer, and the `EVT_WINDOW_TO_BG` handler `0x4afec8` clears the scan countdown and removes the timer), so a reopened page would show old networks. The site is pinned (the thunk's prologue, both GOT loads, the call, its delay slot and the `move v0, zero`), runs on a tap only and is not on the boot path (`tools/reach.py` with the page-init dispatcher `0x4d00c0` as the cut: not reached). It reads the kill switch although the safety rule would not require it for a tap-only site, so that the stock page stays reachable for WEP. Networks can no longer be added on the stock page while ours runs (device check WIFI-12), except under the kill switch, where stock's supplicant reads the real file.

**Design.** The page is the Settings pages' grouped cards ([settings](settings.md) "Cards": 52 px rows, cards 10..310 in `#1C1C1C` with 12 px corners, hairlines from x 24, the stock switch image, the same picture pieces
`pod_cd_single` / `top` / `mid` / `bot` and their pressed twins) in the stock list under our navbar (Back and Now Playing, title Wi-Fi). Layout (`tools/pod_ui.py build_wifi_page`, numbers of `tools/pod_settings.py`):

- Card 1: the **Wi-Fi** switch row (label at x 24, switch image at the card's right edge) and, when a network is connected or joining, its row directly below in the same card.
- **My Networks** (small grey header, 15 px, x 24, 40 px strip) and its card: the saved networks in range, then the saved ones out of range (the fan all dim). Absent when there is none.
- **Networks** header with a 14 px grey spinner after its text while a scan runs (positioned from the measured text, so it follows the language; 76 px when the text cannot be measured) and its card: the other networks by signal, then **Other...** (opens the hidden-network flow).
- Off: the switch row alone, as a single card.
- A network row: check column x 24 (the connected one only: a white check, or a spinner frame while it joins), name (box x 54..210, 21 px white), lock (16 px at x 216, only networks that need a key: not Open, not Enhanced Open), the Wi-Fi fan signal (20 x 16 at x 242) and the info glyph (22 px at x 274). Names only: no grey security line, no per-row delete mark. Fan: Lucide `wifi` drawn whole in the dim grey (`#555559`), the level's arcs white over it: stock levels 4 / 3 / 2 / 1 show `wifi` / `wifi-high` / `wifi-low` / `wifi-low`, a saved network out of range shows none (all dim); the same canvas at every level. Images `wf_check`, `wf_lock`, `wf_info`, `wf_sig0..3` (generated by `mod_icons.py wifi_signal`), `wf_spin0..7` come from `tools/mod_icons.py` (`WIFI_IMAGES`, neutral colours only: the check is not the accent-tinted picker check).
- The scroll view's children are in display order and every row is a pooled widget: 1 connected row, 16 saved (`WP_MY`), `WF_MAX` others, then Other..., between two spacers (`pod_top` 10, `pod_end` 10) and the two headers. The payload shows the rows it needs, moves them (`widget_move`, `virtual_h`) and sets each shown row's piece (`style:*:bg_image`, only when it changed) and its hairline (every row of a card but the last), so nothing is built at run time and the stock layouter's stacking (visible children in order) would put the rows in the same places. Every row child is insensitive: the row takes the tap. Preview: `tools/preview_settings.py` (`out/preview/settings-wifi.png`).

**What it does** (`patch/wifipage.c`; one 250 ms timer owned by the page; every control call is a datagram exchange that answers at once, a missing supplicant after at most 1.5 s):

- **On / off** as stock: the stock `wifi_switch(1)` toggles (on starts `wifi_connect.sh`, off kills the supplicant). Turning on while Bluetooth is on shows the coex warning (`msg_wifi_open`, see "Wi-Fi and Bluetooth together" in
  [overlays](overlays.md)) and leaves Bluetooth on. Off shows the switch row alone. Wi-Fi turned on or off elsewhere (pull-down) is followed.
- **List.** `SCAN_RESULTS` parsed (one row per SSID, the strongest access point's flags, hidden networks left out, strongest first) and merged with `LIST_NETWORKS` (the same name = saved); order: the current network, saved ones in range,
  the others by signal, saved ones out of range last. The page splits that list into the three groups (the current network, the saved ones, the others). Levels use the stock thresholds (>= -65 dBm four, -75..-66 three, -80..-76 two, else one) and show as bars above. The page reads `STATUS` and `LIST_NETWORKS` every second, scans on open,
  reads the results at half and at the end of a 4 s scan and scans again every 12 s while it is in front and the supplicant is not connecting or the page joining (also while connected, so a new network turns up; there is no manual refresh). The header spinner runs while a scan does; the connected row's spinner while the network joins (selected, or associated without an address yet), one frame per 250 ms tick whether or not a scan runs (the tick advances it once; no scan starts while joining). While that joining row shows and no scan of ours runs, each one-second poll also reads `SCAN_RESULTS` (a read, not a scan), so a network the supplicant auto-joins before its own first scan reached the page's table gets its bars from the supplicant's later results instead of staying all dim until the first scan after the connection. Rows are laid out again only when what they show changed.
- **Names.** The supplicant prints SSIDs with printf escapes (`\xe2\x80\x99`); `wf_unescape` turns them into bytes, `wf_utf8` makes the label (a malformed sequence or control character shows `?`), and `SET_NETWORK id ssid <hex>` sends the bytes
  back, so any name joins (the stock page sent the escaped text raw: a name with a typographic apostrophe went wrong).
- **Security** from the scan flags (`wf_security`; the page shows only a lock for everything but Open and Enhanced Open, the name of the security belongs to the info page):

  | Flags | Security | Joins with | Commands |
  |---|---|---|---|
  | `[ESS]` | Open | either | `key_mgmt NONE` |
  | `RSN-OWE` | Enhanced Open | newer only | `key_mgmt OWE`, `ieee80211w 2`, no password |
  | `[WEP]` | WEP | not offered | toast "WEP isn't supported" |
  | `WPA..-PSK` (WPA / WPA2) | WPA/WPA2 | either | password page, `psk "<pass>"` (a 64 digit hex key unquoted; the page cannot type one), `key_mgmt WPA-PSK` |
  | `PSK+SAE` | WPA2/WPA3 | either | newer: `psk`, `key_mgmt WPA-PSK SAE`, `ieee80211w 1`; stock: as WPA2 |
  | `SAE` only | WPA3 | newer only | `sae_password "<pass>"`, `key_mgmt SAE`, `ieee80211w 2` |
  | `EAP` (also Suite B) | Enterprise | not yet | toast "Enterprise isn't supported yet" (phase 2b) |

  "Newer only" with stock's supplicant (a fallback) gives the toast "This network isn't supported" and no dialog. A saved network of any security joins without asking.
- **Connect** a new network: our password page ([below](#the-password-page)) for a secured one (the join is sent from it), then `ADD_NETWORK`, the `SET_NETWORK` lines, `priority` (minutes since the epoch, so the
  last chosen is preferred), `ENABLE_NETWORK`, `SAVE_CONFIG` + split, `SELECT_NETWORK`. A refused step removes the half-made network (`REMOVE_NETWORK`; a `SELECT_NETWORK` that fails also saves again, so neither file keeps it and a retry makes one entry) and toasts "Couldn't connect". Passwords (`wf_pass_ok`; the keyboard takes up to `KB_PASS_MAX` 127 bytes in a password field): WPA2 and the PSK half of WPA2/WPA3 8..63 printable ASCII characters or exactly 64 hex digits, which `wp_join` sends unquoted as the raw PSK (a raw PSK in WPA2/WPA3 is `key_mgmt WPA-PSK` only: SAE needs a password); WPA3 1..127 printable ASCII (`WF_SAE_MAX`; hostap itself sets no limit on `sae_password`). Anything else keeps the Join key dimmed, and `wp_join` refuses it. A saved network: `priority`, `ENABLE_NETWORK`, `SAVE_CONFIG` first, then `SELECT_NETWORK`. hostap's SELECT_NETWORK disables every other network in memory, and a later `SAVE_CONFIG` (a forget, Auto-Join) would write `disabled=1`
  for all of them, so before each select the page notes the Auto-Join-off ids (`wp_snap_off`, `wf_list_off`: all of `LIST_NETWORKS`, asked with `LAST_ID=` while a reply may have been cut at its 4096 bytes, whatever the page lists; a bit per id below `WF_OFF_IDS` 1024) and after it sends `ENABLE_NETWORK all` and `DISABLE_NETWORK` for those (`wp_reenable`): the file keeps only what the user chose. (Side effect: with the others enabled a failed select lets the supplicant fall back to another saved network; the selected one has the highest `priority` and wins when it is there.)
  A selected network that the supplicant marks `[TEMP-DISABLED]` (a wrong password) or that does not come up in 20 s toasts "Couldn't connect" once. Tapping a saved network that is Auto-Join off enables it again (SELECT enables the selected one; the page saves that).
- **Info glyph** (a tap right of x 264 on any network row, the connected one too) opens the network's info page ([below](#the-info-page)). **Disconnect**: a tap elsewhere on the connected network: Disconnect Now? (stock's), `DISCONNECT`; the info page has no Disconnect (the tap row is the only place, as before).
- **Other...**: our Join Wi-Fi Network page ([below](#the-other-network-flow)): name, security and password on one page, then the join; a hidden network is added with `scan_ssid 1`. The stock `kbaddnet_dialog` is no longer used.
- The stock player's own monitor (`network_checkstatus`) still finds the connection through the supplicant's state, starts DHCP (`networkGetWifiSignal`) and keeps its status words; the page writes none of them.

**Files.** After a `SAVE_CONFIG` the page reads the saved file (the copy ours runs on, else the real file), `wf_split` writes every `network={}` block whose keys are all ones stock writes (`ssid scan_ssid bssid psk key_mgmt priority disabled id_str proto pairwise group auth_alg wep_key0..3 wep_tx_keyidx frequency mode`) and whose
`key_mgmt` is `NONE` / `WPA-PSK`, with every line outside the blocks, to `/mnt/data/wpa_supplicant.conf`, and the other blocks to `/mnt/data/m1plus/wifi-networks` (`home_write_atomic`: temp file, fsync, rename; ours first). Without a copy (the script could not write
it) the blocks already in `wifi-networks` are kept and the new ones appended. A configuration of 12 KB or more is not split. `wifi-networks` is a settings file (listed on Settings Files, so Reset All Settings and a per-file delete remove it and with it the saved
WPA3 / Enhanced Open networks; the stock networks stay).

### The info page

The info glyph of a row opens `m1plus_wifiinfo` (`wi_open`, `patch/wifipage.c`; `tools/pod_ui.py build_wifiinfo_page`; `Page` `WIFIINFO_PAGE`, no action id, no hook): the Settings cards under our navbar, the navbar's title the network's name (`az_fit`: UTF-8, cut with an ellipsis).
Rows are pooled and placed in display order like the list's (`wp_put`, `virtual_h`, `wp_clamp`); cards are 20 px apart (`GAP_H`); preview `out/preview/settings-info.png` (`tools/preview_settings.py draw_wifiinfo`, the built tree's widgets).

- **Saved network:** **Forget This Network** (white, centred, no red; Delete Record? then `REMOVE_NETWORK` + `SAVE_CONFIG` + split, back to the list), the info card, **Auto-Join** (the stock switch; on = not `[DISABLED]`).
- **Not saved:** the info card and **Join** (`wp_connect`, the list's own path: the password page for a secured network, the toasts for WPA3 with stock's supplicant, Enterprise and WEP, which keep the page open; after a join was sent the page goes back: an open network at once, a secured one when the password page's Join closed it, `wp.pop_info`: the list's timer takes the info page back once the password page is gone).
- **Info card** (`WI_FIELDS` = 4 pooled label / value rows, the fourth is room for the enterprise rows of mockup screen 4: Username, Password, Certificate): **Security** (`wf_sec_label` and the `pod_i18n` texts Open, Enhanced Open, WEP, WPA/WPA2, WPA2/WPA3, WPA3, Enterprise: one label for every EAP network, not "WPA2 Enterprise"),
  **IP Address** (`STATUS` `ip_address`, kept in `wf_status.ipaddr`) and **Router** (`wf_parse_route` on `/proc/net/route`: wlan0's default route, up and with a gateway; the 32 bit gateway printed as hex in host order, little endian here), both only while the page's network is the connected one and has an address; no gateway = no Router row.
- **Auto-Join:** `ENABLE_NETWORK id` / `DISABLE_NETWORK id`, then `SAVE_CONFIG` + split. `disabled` is in `wf_split`'s stock keys, so `disabled=1` stays with its block: a WPA-PSK / open network in the real file (stock's 2.9 reads `disabled` as its own supplicant writes it), a WPA3 / OWE / enterprise one in `wifi-networks` (hostap 2.12 reads it back from the copy).
  hostap disconnects when the network it is on is disabled; the page does not work around that (device check WIFI-13).
- **Refresh:** no timer of its own. The list's timer reads `STATUS` / `LIST_NETWORKS` and the scan; `wp_merge` ends with `wi_refresh`, which finds the network by its name bytes in the merged list and re-lays the page only when something it shows changed (a hash of saved / Auto-Join / security / connected / address / gateway).
  A network that left the scan stays as it was (a saved one is still in the list, an unsaved one keeps Join), a network forgotten elsewhere becomes an unsaved one, the supplicant not answering changes nothing, Wi-Fi turned off (the list's timer notices) goes back to the list.
- **Windows:** the list stays under the info page (its timer runs, no scan while it is not in front); the info page's destroy handler frees only its own state, so Back and Now Playing (popping both) end in either order. Taps are ignored under a dialog (`wp.modal`).

Tests: `info_tests` in `test/pod/wifipage.py` (open from every kind of row, the title, rows, y, pieces and gaps in each state, address / router appearing and going, route parse, the Join / Forget / Auto-Join commands and files for stock and WPA3 networks, the select side effect, refresh cases, Wi-Fi off), plus `wf_parse_route`, `wf_sec_label`, `[DISABLED]`, `ipaddr` and the `disabled` split cases in the library sections.

### The password page

A secured network that is not saved (a tap on its row, or Join on its info page) opens `m1plus_wifipass` (`wk_open`, `patch/wifipage.c`; `tools/pod_ui.py build_wifipass_page`; `Page` `WIFIPASS_PAGE`, no action id, no hook) instead of the stock password dialog (`dialog/kbpassword_dialog` is no longer used). (The hidden-network page of [the Other Network flow](#the-other-network-flow) has its own Password row and does not open it.) Preview: `tools/preview_keyboard.py` (four panels: empty, 8 characters, shown, wrong).

- **Look** (mockup screens 6 to 8): navbar "Enter Password" (Back cancels; nothing is sent), a grey centred 15 px line `Enter the password for “<name>”` (UTF-8, `az_fit` cuts the whole line with an ellipsis, so a very long name loses the closing quote), one Settings card (10, 100, 300 x 52, `#1C1C1C`) with the label **Password** (21 px white, x 24, 118 px: French is the longest), the field (x 144, 118 px of text room: the keyboard's own `kb_field` / `kb_text` / `kb_caret` widgets) and the eye button (a 46 px touch area at x 264, the 22 px Lucide `wf_eyeoff` while hidden, `wf_eye` while shown, `tools/mod_icons.py` `WIFI_GLYPHS`), a grey 18 px "Incorrect password" line at y 160 (hidden unless the page was reopened after a refusal; it goes at the first key), then the keyboard's pad. Everything above the pad ends by y 182, so the candidate strip (y 234) is never covered (and password mode never shows it). No big Join button: the keyboard's action key reads **Join** (`keyboard_set_go`), dimmed and inert until the typed text can be this network's password (`wf_pass_ok`: 8..63 printable ASCII characters, WPA3 1..127; so a euro sign never enables it). The Join key text is Войти / Увійти in Russian and Ukrainian (the old Подключиться did not fit the 74 px key). Neutral colours, no accent.
- **Keyboard**: `keyboard_attach(win, NULL, 0, 118, 15, KB_PASSWORD, wk_change, wk_go)`: English layer only, lowercase start, spaces anywhere, masked dots with the eye ([keyboard](keyboard.md) "Password mode"). `wk_change` is the on-change callback (dims or enables Join from the text, hides the error line); the typed text lives only in the keyboard's state and is wiped by `keyboard_detach` in the page's destroy handler, `wk_go` copies it to a stack buffer for `wp_join` and zeroes the buffer. It is never written to a file by the page (the supplicant writes its own configuration through `SAVE_CONFIG`), never logged and no recent list exists.
- **Join** (`wk_go`): `wp_join` as the stock-dialog path did (hex SSID, `psk` / `sae_password` by security, `key_mgmt`, `priority`, enable, save, select, the re-enable of the other saved networks of stage 3). The page goes back and the list shows the stage 2 joining state (the connected row's spinner, then the check). The network is remembered in `wp.pwnet` and `wp.want_pw` is set.
- **Wrong password** (`wp_poll`): the network is `[TEMP-DISABLED]` or has not connected in 20 s (the same detection as the "Couldn't connect" toast): when the join came from the password page the network is **removed** (`REMOVE_NETWORK`, `SAVE_CONFIG`, split: the wrong password does not stay in `wpa_supplicant.conf` or `wifi-networks`) and the password page **opens again** over the list with an empty field and "Incorrect password" under the card (no toast). If the list is not in front or a dialog is up the removal happens and the old toast shows. A saved network that fails keeps the old behaviour: the toast, the network stays saved (only the password page's joins and the Other Network flow's are removed). Back from the reopened page returns to the list.
- **Other paths**: Wi-Fi turned off under the page goes back (and takes the info page under it); a missing widget or keyboard asset backs out and sends nothing; the window that will not open sends nothing.
- **Tests** (`pass_tests` in `test/pod/wifipage.py`): the asset (names, geometry, nothing past y 182, the dim style, the pad last, neutral colours, the eye images, the texts' widths in 13 languages), opening from the list and from the info page (nothing sent, the line, Join dimmed), typing (dots, the eye both ways, Join enabled at 8 characters, WPA3 at 1, a euro sign never), Join's commands, the list's spinner, a wrong password (the network and its password gone from both files, the page back with the line, no toast, a second attempt joins as a new network and is not asked again), the 20 s timeout, a saved or hidden network keeping the toast, Back (nothing sent, state wiped), Wi-Fi off, the password in no file but the supplicant's configuration and on no widget while hidden, the keyboard's state clean after the page; `password_tests` in `test/pod/keyboard.py` (the keyboard side).

### The Other Network flow

Other... (the last row of Networks) replaces the stock hidden-network dialog with **one page of ours, Join Wi-Fi Network** (the iOS sheet's layout; `m1plus_wifiother`, `wo_open`) and a **Security picker** it opens (`m1plus_wifisec`, `ws_open`). Code: `patch/wifipage.c` `wo_*`, `ws_*`; `tools/pod_ui.py` `build_wifiother_page`, `build_wifisec_page`; `Page`s `WIFIOTHER_PAGE` (title "Join Wi-Fi Network"), `WIFISEC_PAGE`, no action id, no hook; previews `out/preview/kb-other.png` (`tools/preview_keyboard.py other_page`) and `tools/preview_settings.py draw_wifisec`. The stock `dialog/kbaddnet_dialog` path, the `prepare_linkssid` / `prepare_linkpasswd` words and the old name-only page, Security-then-continue steps and "Enter the name of the network" line are gone; the password page (`m1plus_wifipass`) is only for visible secured networks now.

- **Look**: navbar "Join Wi-Fi Network" (Back = cancel; iOS's top-right confirm tick and Wi-Fi glyph are not drawn: the keyboard's action key does the joining and there is no room above the pad), no grey line. **Card 1**: the **Name** row (label 76 px at x 24, the keyboard's field from x 100 to the card's ink edge, text room 156 px, the clear button at its right once there is text, the grey placeholder "Network Name" while it is empty). **Card 2**: the **Security** row (the value right-aligned in the Settings value box, the Settings chevron, a tap opens the picker) and, under a hairline, the **Password** row (label at x 24, field at x 144 with 118 px of text room as the password page's, the eye button at x 264). With Security **None** the Password row, its hairline and the eye go and card 2 is the one-row card (`wo_card1a`; `wo_card1b` is the two-row one: two asset views, the payload shows one). The error line "Incorrect password" (16 px grey) sits under card 2. **Rows are 48 px, not 52**: Name y 56..104, a 12 px gap, Security 116..164, Password 164..212, the error line 212..232, so everything above the pad ends above the candidate strip (y 234; with 52 px rows the Password row alone would end at 234 and leave no room for the line). Neutral colours, no accent.
- **One keyboard, two fields**: `keyboard_attach(win, "Network Name", 0, 156, 13, 0, wo_change, wo_go)` once; `wo_focus` serves the field being typed in with `keyboard_refocus` ([keyboard](keyboard.md): the widgets and bindings stay, the flags, text room, placeholder, text and callbacks change). The one `kb_field` widget (no fill) is **moved** to the active row (`widget_move`: Name x 100 / y 56, Password x 144 / y 164); the other row shows its value in a static label (`wo_name_v` white, or `wo_name_h` the grey placeholder while the name is empty; `wo_pass_v`: dots, or the text while the eye is open; `az_fit` cuts with an ellipsis). Name = plain mode (capital start, clear button, the language key and pinyin when Chinese (Pinyin) is on); Password = `KB_PASSWORD` (English only, lowercase start, masked with the eye, never pinyin). A tap on a row (`wo_hit_name`, `wo_hit_pass`: buttons under the field; the Password one stops left of the eye) takes the pad; a tap on the row that already has it does nothing; Next moves to the Password. Both values live on the page (`wo.ssid`, `wo.pass`, kept by `wo_change`) so they survive switching and the picker; the password buffer is wiped when the page joins and when it is destroyed (`keyboard_detach` clears the keyboard's copy), it is never written to a file, logged or shown while hidden, and the supplicant's configuration (`SAVE_CONFIG`) is the only place it stays.
- **Action key** (`keyboard_set_go`): on the Name of a secured network **Next** (moves to the Password), on the Name with Security None and on the Password **Join**. Dimmed and inert until it can work: the name is 1..32 bytes (`wo_name_ok`; the keyboard takes 63, a 33rd byte dims it) and, for Join on the Password, `wf_pass_ok` for the chosen security (WPA2/WPA3 8..63 printable ASCII, WPA3 1..127), so a name that is too long or empty keeps Join dimmed from the Password too.
- **Security picker** (`ws_open`): the Settings picker rows' pieces and hairlines, the neutral check (`pod_check`) on the page's **current choice** (the payload puts it on open): **None**, **WPA2/WPA3** (the default), **WPA3** (Enterprise joins with the enterprise phase). A tap **sets the choice and goes back** (`wo_set_sec`; it no longer continues a flow): the value, the card and the action key's label follow, and with None the keyboard goes back to the Name (`wo_focus(0)`). WPA3 with stock's supplicant (a fallback) toasts "This network isn't supported" (`wp_can`), keeps the picker open and the choice unchanged. The keyboard stays attached to the join page under the picker.
- **Name** keeps its spaces literally (`KB_LITERAL`: leading, doubled and trailing, sent as the hex of the typed bytes); **Join** (`wo_go`): `wp_join` with `hidden = 1`: `ADD_NETWORK`, `ssid` hex, `scan_ssid 1`, then by security: None `key_mgmt NONE`; WPA2/WPA3 `psk`, `key_mgmt WPA-PSK SAE` + `ieee80211w 1` with the newer supplicant and `WPA-PSK` only with stock's (as `GET_CAPABILITY` says); WPA3 `sae_password`, `key_mgmt SAE`, `ieee80211w 2`; then `priority`, `ENABLE_NETWORK`, `SAVE_CONFIG` + split, `SELECT_NETWORK`. The page goes back (`navigator_back`) and the list shows the joining spinner, then the check: on success there is nothing else to pop. `scan_ssid` is in `wf_split`'s stock key list, so a hidden open or WPA2 network stays in `/mnt/data/wpa_supplicant.conf` (stock 2.9 reads `scan_ssid`) and a WPA2/WPA3 or WPA3 one goes to `wifi-networks` with its `scan_ssid` line.
- **Failure**: a wrong password or no answer in 20 s removes the network from the supplicant and both files and **reopens the Join Wi-Fi Network page** (`wo_open(&wp.pwnet)`, `wp.pwhid`; not the password page) with Name and Security kept, the Password field active and empty and the grey "Incorrect password" line under card 2 (it goes at the first character typed in the Password field, and stays while the Name is looked at); Join is dimmed until a new password is valid. An **open** hidden network that never appears gets the 20 s toast "Couldn't connect" (there is no page left to put a line on) and is **removed** the same way (`wp.want_hid`). Back from the reopened page returns to the list.
- **Wi-Fi turned off** under the page goes back; under the picker the picker goes first and the join page follows from the list's timer (`wp.pop_other`).
- **Scan on open**: `wifipage_open` already sends `SCAN` right after the first `STATUS` / `LIST_NETWORKS` (the cached `SCAN_RESULTS` list meanwhile), so the header spinner is up as soon as the page shows; the 12 s timer is only for the next ones. A supplicant that is not up yet gets its first scan from the timer as soon as it answers. Tested (`other_tests`). There is no manual refresh.
- **Tests** (`other_tests` in `test/pod/wifipage.py`): both assets (names, geometry of both cards and every row, nothing past y 234, the field over the row buttons, the pieces, the check, no accent colour, the texts in 13 languages), Other... opening our page without a dialog, typing and Next's dimming at 0, 1, 32 and 33 bytes, Next moving the field to the Password, values surviving every switch (name, password, dots, the eye in both places), the picker (check follows the choice, a tap sets and goes back, the value / card / key follow, None removes the Password row and its taps, WPA3 with stock's supplicant), the key's dimming per security, the exact join commands and files for WPA2/WPA3, WPA3 and None with the newer and stock's supplicant, the password wiped from the page and the keyboard, a hidden network that never appears, a wrong password (the page reopens with Name and Security kept, the line, the second try), pages that cannot be made, Wi-Fi off under each page, the scan on open; `refocus_tests` in `test/pod/keyboard.py` (mode per field, pinyin allowed on a plain field and never on a password, the engine opened once); `split_tests` has hidden WPA2 / WPA3 blocks.

**Deviations from the stock page**: the layout is ours (grouped cards, My Networks / Networks, Wi-Fi fan signal, lock, info glyph, check or spinner instead of Connecting / Connected words, no Scanning row or refresh icon, no security line, no per-row delete mark, Other... for Add Network); a saved network out of range is listed (stock lists scan results only); the Bluetooth question has our own text; the headers, Other..., the info page's rows, the security names and the toasts are new texts (13 languages, `tools/pod_i18n.py`).

**Not verified on hardware:** everything. For the password page: the real keyboard feel in the narrow field (dots and caret by the real text measure), the eye, Join dimming on a touch near the key, a real wrong-password cycle (does the supplicant mark `[TEMP-DISABLED]` on SAE and WPA2 within the page's 4 s poll; does `REMOVE_NETWORK` of the selected network disturb the next try), the reopen from a timer, the info page popping itself after Join (`wp.pop_info`). For the Join Wi-Fi Network page: the field moving between the rows and the pad changing mode in place (`keyboard_refocus`), the 48 px rows and the error line against the candidate strip, the reopen after a refusal. For the hub row: the hooked `navigator_to` call from the stock All System Settings page (Back returns to the hub, no leftover stock Wi-Fi page). The compiled payload runs under Unicorn against a scripted supplicant (`test/pod/wifipage.py`), never against the device's supplicant, the driver or the stock monitor: SAE and OWE with the RTL8733BS driver, the
`GET_CAPABILITY` text of both supplicants, `SCAN_RESULTS` flags of real access points, `wifi_switch(1)` from the page, DHCP after a page-made connection, `ip_address` in `STATUS`, hostap 2.12 rewriting the configuration the way `wf_split` expects, the 4096 byte reply cap
with many access points, what the stock page does with a copy-only network, and for the info page: hostap's `SELECT_NETWORK` really sets `disabled=1` on the others (the re-enable after it rests on that and on `[DISABLED]` in `LIST_NETWORKS`), what `DISABLE_NETWORK` does to the connected network, `/proc/net/route` as printed on this kernel and `ip_address` in `STATUS`.

### Known limits of the list

- The list shows at most `WF_MAX` 32 networks: the connected one first, then saved ones, then the strongest unsaved ones; when more are known the weakest unsaved networks in range go first (`wf_merge`), so a connected or saved network absent from a full scan stays. Of the saved networks only `WP_MY` 16 have a row in My Networks and the page reads 16 of them (`WP_KNOWN`); the Auto-Join state of all saved networks below id 1024 survives a select, a network with a higher id is enabled by it.
- Joining a name that is already saved (Join Wi-Fi Network typed with a saved SSID) adds a second entry; nothing looks for the existing one. A saved weak network the scan found beyond the 48 strongest results is listed as out of range.

## Build

`uv run python -I tools/mod_wpa.py --fetch` downloads into `work/cache/wpa/dl` (SHA-256 pinned; `make doctor` and CI check/fetch it);
the normal build never touches the network (it also reads the main checkout's cache). Inputs: `wpa_supplicant-2.12.tar.gz`
(w1.fi, released 2026-08-07; its `.asc` is not verified, the hash is pinned from the first download) and five Debian 10 mipsel
packages from archive.debian.org: `libc6-dev` 2.28-10+deb10u1, `linux-libc-dev` 4.19.249-2, `libssl-dev` 1.1.1n-0+deb10u3,
`libnl-3-dev` and `libnl-genl-3-dev` 3.4.0-1. Only their `usr/include` is extracted (tar data filter, nothing executed). The headers
are OpenSSL 1.1.1n against a 1.1.1f runtime (same ABI); the linker checks every symbol against the stock `.so`.

`build()` compiles with Homebrew clang `--target=mipsel-linux-gnu -march=mips32r2 -mabi=32 -mnan=2008 -mfp64 -fno-pic -Oz` and links
with lld `-no-pie -nostdlib --dynamic-linker=/lib/ld-linux-mipsn8.so.1 --gc-sections -s` against symlinks to the stock `.so` files in
`work/cache/wpa/build/libs` (read as link inputs only; nothing built or stock is executed on the Mac). Debian's `crt1.o`, `crti.o`,
`crtn.o` and `libc_nonshared.a` are legacy-NaN and lld refuses to mix NaN modes, so `assets/wpa/start.S` (entry; ld.so passes
`rtld_fini` in `$v0`) and `assets/wpa/shim.c` (`__libc_start_main` call, init/fini arrays, `atexit`, `stat`/`fstat`/`lstat`(64) via
`__xstat*` with `_STAT_VER` 3) replace them. The `-o32_hard_2008` stub headers Debian lacks are copies of the `-o32_hard` ones. A
`.pdr` section (77 KB) that lld keeps is removed with `llvm-objcopy`. The result is cached in `work/cache/wpa/bin/<input hash>` and
is bit-for-bit reproducible (two builds, same SHA-256).

`verify()` fails the build unless the binary has the stock supplicant's `e_type` and `e_flags` (so NaN2008 is set), the NaN2008
interpreter, a non-executable stack, only NEEDED libraries that exist on the stock rootfs, and every imported symbol is exported by
the stock library it will load with the required version (all `GLIBC_` versions <= 2.28; seen: `GLIBC_2.0/2.2/2.3/2.17/2.28`,
`libnl_3`, `libnl_3_2_27`, `OPENSSL_1_1_0`, `OPENSSL_1_1_1`). It also runs on the cached binary at every build.
NEEDED: `libc libm libdl libpthread libgcc_s librt libnl-3 libnl-genl-3 libssl libcrypto` (`libgcc_s` for 64-bit division helpers).

The build adds `usr/lib/m1plus` and its binary (`added_rels`, so `fwtool` allows them) after `mod_cacerts`.

## Space

Stock `rootfs.squashfs` 55,738,368 bytes. The release tree with this step packs to 55,615,488 (headroom 122,880 bytes); the step
costs about 377 KB of the roughly 500 KB the release had. With debug output compiled in it cost 540 KB and the build failed on size
(`-Oz` and removing `.pdr` gave 516 KB; WPS costs 45 KB, `-flto` saves 8 KB).

## Validation

Tests in `test/pod/wpa.py` (`make test TEST=wpa`): the pins; `.config` options; the built ELF (type, `e_flags`, interpreter, NEEDED,
stack, symbol versions) against the stock supplicant and libraries, and `verify()` refusing a legacy-NaN flag, another interpreter,
an unknown library, glibc 2.29, a symbol the stock libc lacks and a non-ELF; the compiled EAP method names and SAE/OWE/Suite B/FT
strings; stock `wpa_supplicant`, `wpa_cli`, `libwpa_client.so` unchanged; the script rewrite (other input refused) and the script run
under the host shell with stub programs: ours chosen with stock's arguments, stock chosen for the kill switch, a failing `-v` and a
missing file, no card, the missing-config early exit, the copy ours reads (the real config, a blank line, `wifi-networks`; never used for stock; the copy of the last start removed) and the hand-over to stock when ours exits with an error.

Tests in `test/pod/wifipage.py` (`make test TEST=wifipage`, sections `text_tests`, `security_tests`, `scan_tests`, `split_tests`, `ctrl_tests`, `asset_tests`, `layout_tests`, `action_tests`, `pass_tests`, `other_tests`, `info_tests`, `switch_tests`, `timer_tests`, `life_tests`, `files_tests`): the escape decoder, hex and UTF-8 (a round trip against hostap's `printf_encode`, the iPhone apostrophe); flags and `key_mgmt` to security for the real flag strings, the labels, the signal thresholds, passphrase rules; the scan, list and status parsers and the merge order; `wf_split` on named cases and 120 random configurations against an independent model; the control socket's datagram sequence and its failures (a scripted supplicant); the asset (the list as stock's, the rows' measures against the Settings numbers, display order, pieces, images, texts in every language); the page on a scripted supplicant (rows, pieces, y positions, check and spinner, every tap and the commands it sends, both supplicants, the files written, the switch with the Bluetooth question, the timer's cadence and its guard under a dialog, the page's life, the fallbacks). `review_tests` holds the six review cases: Auto-Join kept across a select with 17, 40 and 100 saved networks (the last read in pages), 64 hex digit and 127 character credentials on both password pages, a full scan keeping the connected and saved networks, scans while connected, a Name with spaces sent byte for byte, and a failed select leaving nothing saved.

Not verified: anything on hardware. The binary has not been executed (no MIPS Linux, no emulator for dynamic glibc binaries here); the
entry stub and shim are the part most likely to fail at load (the `-v` self-check then selects stock). SAE, OWE,
EAP, WPS and PMF with the RTL8733BS driver; 2.12 reading a config written by 2.9 and the player parsing one written by 2.12
(`networkGetSsidList`); the `wpa_cli` 2.9 `scan_result` format against 2.12's flags column; BusyBox ash running the script (its
syntax is plain POSIX).

## Later phases: enterprise form, captive portals

Stages 1 to 5 (the supplicant, the list in the iOS layout, the info page, the password page, the Other Network flow: mockup `out/mockups/wifi/sheet.png`, values in `out/mockups/wifi/mock.py`) are what this branch ships; what is left:

- **Enterprise** joins the Security page's rows (the Other Network flow, above) and the info page's rows:
  The info page's pooled field rows (`WI_FIELDS`, `wi_f0..3`) are where the enterprise rows (Username, Password, Certificate with a chevron, mockup screen 4) go; its Join row exists. The enterprise form (mockup screen 9) follows with phase 2b and can reuse the password page's pieces
  (`wk_open`'s field, eye and error line; `KB_PASSWORD` for the password row, a plain `keyboard_attach` for the username) with the keyboard attached to whichever field is tapped.
- **Enterprise form (2b).** `wp_can` (`patch/wifipage.c`) answers an `WF_EAP` row with a toast; replace that with a form page of our own (identity, anonymous identity, password, EAP method, phase 2) opened from the row, using the stock keyboard
  dialogs or our keyboard page ([keyboard](keyboard.md)). EAP: PEAP + MSCHAPV2 most common; TTLS + PAP / MSCHAPV2; TLS needs a client certificate and key from the card. `wp_join` already has the shape (`ADD_NETWORK`, `SET_NETWORK`
  lines, `priority`, `ENABLE_NETWORK`, save, select); add the keys `key_mgmt WPA-EAP` (`WPA-EAP-SUITE-B-192` for 192 bit), `eap`, `identity`, `anonymous_identity`, `password`, `phase2`, `ieee80211w` and the certificate keys. `wf_split` already sends
  every block with an `eap` / `identity` / `ca_cert` ... key to `wifi-networks` (they are not in its stock key list). Gate the row on the `eap` list of `GET_CAPABILITY eap` (`PEAP`, `TTLS`, `TLS`: stock 2.9 has only `WSC`) like SAE / OWE.
  Certificate modes: (1) trust on first use: connect once without validation to read the server certificate, show its subject and SHA-256, and store `ca_cert="hash://server/sha256/<hex>"` after the user agrees; (2) system CAs: `ca_cert="/etc/m1plus-cacert.pem"`
  (the Mozilla bundle already on the rootfs; do not duplicate it) plus `domain_suffix_match="<host>"`; (3) a CA file on the card (`/mnt/mmc/...pem`, copied into `/mnt/data`, since the card can be removed; the copy's path goes in `ca_cert`); (4) no
  validation, behind a warning. The only diagnostics are events (stdout debug is compiled out): `CTRL-EVENT-EAP-TLS-CERT-ERROR`, `CTRL-EVENT-EAP-FAILURE`, `CTRL-EVENT-SSID-TEMP-DISABLED`. The page's sockets are one datagram per command and never `ATTACH`; events
  need a socket that stays open and attached (`ATTACH`, then `recv` of unsolicited `<3>CTRL-EVENT-...` lines in the page's timer, `DETACH` on close) beside `wf_cmd`.
- **Captive portals (2c).** After `COMPLETED` with an `ip_address` request a known HTTP 204 URL (the Podcasts worker's libcurl and CA bundle, [podcasts](podcasts.md); one worker thread, never the UI thread); a redirect or a body means a portal;
  show "Sign in required" instead of Connected (the row's grey line is `wp_layout`'s `key`). Do not block the connection state on it.
- **Constraints that stay.** The stock player kills the supplicant by name (`killall -9 wpa_supplicant`) and restarts it through `wifi_connect.sh` at every connect, so any state must live in the supplicant's configuration or the files, not in the process. Stock reads `key_mgmt=`,
  `wep_key0=` and `auth_alg=` out of the real config for the stock page's saved list; keep that file stock-readable (enterprise blocks belong in `wifi-networks`). WEP stays out (hostap 2.12 has no `CONFIG_WEP`).
- **Open decisions** (user): whether
  saved networks out of range stay listed; whether the connected row should keep a text state (Connecting / Connected) beside the spinner and check.
- Debug output could come back in a separate binary only if space allows (about 135 KB compressed).

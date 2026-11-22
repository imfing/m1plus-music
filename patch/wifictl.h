/* The own Wi-Fi page's supplicant side (patch/wifictl.c, docs/modules/wifi.md): wpa_supplicant's control protocol, the printf-escaped SSIDs it prints, the security of a scan
 * result's flags and the split of its saved configuration. The page (patch/wifipage.c) is the only user; test/pod/wifipage.py runs every function here.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define WF_SSID_MAX 32 /* bytes of an SSID */
#define WF_MAX 32 /* networks the page lists (scanned ones, strongest first, and the saved ones) */
#define WF_REPLY \
    4096 /* the supplicant's replies are at most this long (SCAN_RESULTS and LIST_NETWORKS are cut at 4096 bytes there) */
#define WF_CTRL_DIR \
    "/var/run/wpa_supplicant" /* ctrl_interface of the stock config; the interface's socket is WF_CTRL_DIR/wlan0 */
#define WF_CONF "/mnt/data/wpa_supplicant.conf" /* the stock configuration (stock networks only) */
#define WF_COPY \
    "/tmp/m1plus-wpa.conf" /* what wifi_connect.sh gives the newer supplicant: the stock configuration plus wifi-networks */
#define WF_OFF_IDS \
    1024 /* saved network ids wf_list_off tracks (a bit each; hostap numbers networks from 0, reusing the lowest free id) */
#define WF_PASS_MIN 8
#define WF_PASS_MAX \
    63 /* a WPA-PSK passphrase: 8..63 printable ASCII bytes, or exactly 64 hex digits (a raw PSK, sent unquoted) */
#define WF_SAE_MAX 127 /* a WPA3 (SAE) password: 1..127 printable ASCII bytes; the keyboard's KB_PASS_MAX */

/* The security of a network (patch/wifictl.c wf_security): from a scan result's flags, or from a saved network's key_mgmt (wf_security_keymgmt). */
enum { WF_OPEN, WF_OWE, WF_WEP, WF_PSK, WF_TRANS, WF_SAE, WF_EAP };

/* wpa_state as wf_parse_status reads it. */
enum { WF_ST_IDLE, WF_ST_SCANNING, WF_ST_CONNECTING, WF_ST_CONNECTED };

typedef struct {
    unsigned char ssid[WF_SSID_MAX + 1]; /* the bytes, a NUL after them */
    unsigned char len; /* bytes in ssid */
    unsigned char sec; /* WF_* */
    unsigned char level; /* 1..4 from the signal, 0: not in range (a saved network the scan did not find) */
    unsigned char known; /* a saved network of the supplicant (id) */
    unsigned char current; /* the network the supplicant is connected or connecting to */
    unsigned char
        bad; /* a saved network the supplicant disabled for a while (wrong password): its flags say TEMP-DISABLED */
    unsigned char off; /* a saved network that is disabled (Auto-Join off): its flags say DISABLED */
    int id; /* the saved network's number, -1 when not saved */
    int dbm; /* the strongest signal seen, 0 when none */
} wf_net;

typedef struct {
    int state; /* WF_ST_* */
    int id; /* the network's number, -1 when none */
    int ip; /* the interface has an address */
    unsigned char ssid[WF_SSID_MAX + 1];
    unsigned char len;
    char ipaddr[20]; /* the interface's address as STATUS prints it ("192.168.1.20"), empty when none */
} wf_status;

/* A reply line's printf escapes (\" \\ \n \r \t \e \xNN \NNN) decoded into at most max bytes; the bytes in out. n is the line's length (at most). */
int wf_unescape(const char *s, unsigned n, unsigned char *out, unsigned max);
/* Lowercase hex of n bytes and a NUL, 2n + 1 bytes of out. */
void wf_hex(const unsigned char *b, unsigned n, char *out);
/* The bytes as the UTF-8 the labels show: a malformed sequence, a control character and a byte over 0xf4 become '?'. out holds max bytes at most, NUL-ended. Returns the length. */
int wf_utf8(const unsigned char *b, unsigned n, char *out, unsigned max);
/* The security of a scan result's flags ("[WPA2-PSK-CCMP][ESS]"): one of WF_*. */
int wf_security(const char *flags);
/* The security of a saved network's key_mgmt value ("WPA-PSK SAE", "NONE"). */
int wf_security_keymgmt(const char *km);
/* The English text the info page shows for a security (its translation key). */
const char *wf_sec_label(int sec);
/* The default gateway of wlan0 from the text of /proc/net/route ("Iface Destination Gateway Flags ..." lines, addresses as the kernel prints them: hex of the 32 bit value, little endian on this device)
 * as dotted text in out (size bytes at least 16). 1 when there is one, else 0 and out is empty. */
int wf_parse_route(const char *text, char *out, unsigned size);
/* The networks of a SCAN_RESULTS reply, strongest first, one per SSID (the strongest access point's flags), hidden networks left out. Returns how many (at most max). */
int wf_parse_scan(const char *text, wf_net *out, int max);
/* The saved networks of a LIST_NETWORKS reply, in order: id, ssid, current set by "[CURRENT]"; sec stays WF_PSK (the page asks GET_NETWORK key_mgmt). Returns how many. */
int wf_parse_list(const char *text, wf_net *out, int max);
/* The ids of the saved networks that are Auto-Join off ("[DISABLED]", not "[TEMP-DISABLED]") from the whole of LIST_NETWORKS, asked page by page with LAST_ID= while a reply may have been cut
 * (the supplicant cuts it at WF_REPLY bytes, at a line): bit id of map (WF_OFF_IDS / 8 bytes) set for each. r is the reply buffer (size bytes). Returns the pages read, -1 when the first got no answer. */
int wf_list_off(char *r, unsigned size, unsigned char *map);
/* A STATUS reply. */
void wf_parse_status(const char *text, wf_status *st);
/* known's networks into nets (nets holds *n and has room for nk more): a scanned network with a saved twin (the same SSID bytes) takes its id and known; the others are appended with level 0.
 * Then the order of the page: the current one, the saved ones in range, the other networks in range by signal, the saved ones out of range. cur is the status's network id
 * (-1: none); the network with that id is current. Over max networks the weakest unsaved ones in range go first, so the current and the saved networks stay. */
void wf_merge(wf_net *nets, int *n, int max, const wf_net *known, int nk, int cur);
/* A passphrase fits WPA-PSK (sec WF_PSK, WF_TRANS): printable ASCII of 8..63 bytes, or 64 hex digits; a WPA3 password (WF_SAE) is 1..WF_SAE_MAX printable ASCII bytes. A transition network (WF_TRANS) must satisfy the PSK rule. */
int wf_pass_ok(const char *pass, int sec);
/* A PSK given as 64 hex digits (SET_NETWORK psk takes it unquoted). */
int wf_pass_hex(const char *pass);
/* The saved configuration split in two: the networks a stock 2.9 supplicant can read go with everything outside the network blocks (the global lines) to stock, every other network
 * block to ours. A block is stock's only when each of its keys is one stock writes (WF_STOCK_KEYS) and key_mgmt names nothing but NONE and WPA-PSK. cap is each output's size; the
 * outputs are NUL-ended. Returns 0, or -1 when an output is too small. ours is empty when there is no such block. */
int wf_split(const char *in, unsigned n, char *stock, unsigned *ns, char *ours, unsigned *no, unsigned cap);

/* One command to the supplicant (a datagram socket bound to a private path, connected to WF_CTRL_DIR/wlan0, one reply, at most 1.5 s); the reply NUL-ended in reply (size bytes)
 * and its length, or -1 when the supplicant did not answer. */
int wf_cmd(const char *cmd, char *reply, unsigned size);
/* A command whose reply is "OK" (or the digits ADD_NETWORK answers with); 1 when it was. */
int wf_ok(const char *cmd);

"""The own Wi-Fi page (patch/wifictl.c, patch/wifipage.c, tools/pod_ui.py build_wifi_page, docs/modules/wifi.md), on the real compiled payload under Unicorn.

wifictl: the printf-escaped SSIDs the supplicant prints decoded into bytes, sent back as hex and shown as UTF-8; the security of a scan result's flags and of a saved network's
key_mgmt; the scan and network lists, the status and their merge; the split of the saved configuration into what a stock 2.9 supplicant reads and what only the newer one does; the control
socket's datagram exchange (a scripted supplicant). The page: the asset against the stock page's measures, the rows laid out from a scripted supplicant, every tap (connect, password,
Enhanced Open, WPA3, enterprise and WEP refused, forget, disconnect, hidden network, the switch with the Bluetooth question, the scan row), the files written after a save, the timer, the
page's life and the fallback to the stock page."""
import os, re, struct
import awtk_ui, pod_pages
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
UI = os.path.join(RAW, 'ui', 'm1plus_wifi.bin')
UI_INFO = os.path.join(RAW, 'ui', 'm1plus_wifiinfo.bin')
UI_PASS = os.path.join(RAW, 'ui', 'm1plus_wifipass.bin')
UI_OTHER = os.path.join(RAW, 'ui', 'm1plus_wifiother.bin')
UI_SEC = os.path.join(RAW, 'ui', 'm1plus_wifisec.bin')
HDR = open(os.path.join(ROOT, 'patch', 'wifictl.h')).read()
SEC = {n: i for i, n in enumerate(('OPEN', 'OWE', 'WEP', 'PSK', 'TRANS', 'SAE', 'EAP'))}
NET = 48   # sizeof wf_net: ssid[33], len, sec, level, known, current, bad, pad, id, dbm
ST_IDLE, ST_SCANNING, ST_CONNECTING, ST_CONNECTED = 0, 1, 2, 3
WF_MAX = int(re.search(r'#define WF_MAX (\d+)', HDR).group(1))
WP_CUR, WP_MY, WP_OTH = 1, 16, WF_MAX   # patch/wifipage.c: the row pools
WP_ROWS = WP_CUR + WP_MY + WP_OTH


def printf_encode(b):
    """wpa_supplicant's printf_encode: what SCAN_RESULTS, LIST_NETWORKS and STATUS print for an SSID."""
    out = ''
    for c in b:
        if c == 0x22: out += '\\"'
        elif c == 0x5c: out += '\\\\'
        elif c == 0x1b: out += '\\e'
        elif c == 0x0a: out += '\\n'
        elif c == 0x0d: out += '\\r'
        elif c == 0x09: out += '\\t'
        elif c < 32 or c >= 127: out += f'\\x{c:02x}'
        else: out += chr(c)
    return out


def scan_text(rows):
    """SCAN_RESULTS: rows are (dbm, flags, ssid bytes); the header line first, tabs between the columns."""
    out = 'bssid / frequency / signal level / flags / ssid\n'
    for i, (dbm, flags, ssid) in enumerate(rows):
        out += f'00:11:22:33:44:{i:02x}\t{2412 + 5 * i}\t{dbm}\t{flags}\t{printf_encode(ssid)}\n'
    return out


def list_text(nets):
    """LIST_NETWORKS: (id, ssid bytes, flags)."""
    return 'network id / ssid / bssid / flags\n' + ''.join(f'{i}\t{printf_encode(s)}\tany\t{f}\n' for i, s, f in nets)


def status_text(state='COMPLETED', ssid=b'Home', nid=0, ip='192.168.1.20'):
    return f'bssid=00:11:22:33:44:55\nfreq=2412\nssid={printf_encode(ssid)}\nid={nid}\nmode=station\nwpa_state={state}\n' + (f'ip_address={ip}\n' if ip else '') + 'address=aa:bb:cc:dd:ee:ff\n'


class Lib(Machine):
    """The payload's pure Wi-Fi functions on a base machine."""
    COUNT = True

    def bytes_at(self, a, n): return bytes(self.u.mem_read(a, n))

    def put(self, b):
        a = self.alloc(len(b) + 1); self.u.mem_write(a, b + b'\0'); return a

    def buf(self, n):
        a = self.alloc(n); self.u.mem_write(a, bytes(n)); return a

    def f(self, name, *args, count=3000000):
        a = list(args) + [0] * (4 - len(args))
        return self.call(PSYMS[name], a0=a[0], a1=a[1], a2=a[2], a3=a[3], count=count)

    def nets(self, a, n):
        out = []
        for i in range(n):
            r = self.bytes_at(a + i * NET, NET)
            ln = r[33]
            out.append(dict(ssid=r[:ln], sec=r[34], level=r[35], known=r[36], current=r[37], bad=r[38], off=r[39], id=struct.unpack_from('<i', r, 40)[0], dbm=struct.unpack_from('<i', r, 44)[0]))
        return out

    def put_net(self, a, ssid, sec=SEC['PSK'], level=4, known=0, current=0, nid=-1, dbm=-50, bad=0, off=0):
        r = bytearray(NET); r[:len(ssid)] = ssid; r[33] = len(ssid); r[34], r[35], r[36], r[37], r[38], r[39] = sec, level, known, current, bad, off
        struct.pack_into('<ii', r, 40, nid, dbm); self.u.mem_write(a, bytes(r))


def text_tests(ctx):
    expect = ctx.expect
    m = Lib()

    def unesc(s, max_=64, n=None):
        a = m.put(s.encode('latin-1')); out = m.buf(max_ + 1)
        r = m.f('wf_unescape', a, len(s) if n is None else n, out, max_)
        return m.bytes_at(out, r)

    for raw in (b'Home', 'Sam’s iPhone'.encode(), 'Café 咖啡 \U0001f4f6'.encode(), b'a"b\\c', b'tab\there\nnl\rcr\x1besc', bytes(range(1, 33)), bytes(range(120, 256))[:32], b'x\x00y'):
        expect(unesc(printf_encode(raw)) == raw, f'printf_encode / wf_unescape round trip {raw!r}')
    expect(unesc('Sam\\xe2\\x80\\x99s') == 'Sam’s'.encode(), 'the iPhone apostrophe (\\xe2\\x80\\x99) is one UTF-8 character, not escape text')
    expect(unesc('\\x4') == b'\x04' and unesc('\\x4g') == b'\x04g' and unesc('\\xzz') == b'zz' and unesc('a\\xzzb') == b'azzb', 'a hex escape takes one or two digits; an unreadable one loses its \\x, as printf_decode does')
    expect(unesc('\\101\\60\\7') == b'A0\x07' and unesc('\\1011') == b'A1', 'octal escapes take up to three digits')
    expect(unesc('a\\qb') == b'aqb' and unesc('end\\') == b'end', 'an unknown escape loses its backslash; a lone backslash at the end is dropped')
    expect(unesc('abcdef', 3) == b'abc' and unesc('abcdef', 64, 4) == b'abcd' and unesc('') == b'', 'the output is cut at max and the input at n')

    out = m.buf(80); a = m.put(b'\x00\x7f\xffAz')
    m.f('wf_hex', a, 5, out)
    expect(m.read_cstr(out) == '007fff417a', 'wf_hex: lowercase hex of any bytes, NUL-ended')
    expect(m.f('wf_hex', a, 0, out) is not None and m.read_cstr(out) == '', 'wf_hex of nothing is the empty string')

    def utf8(b, max_=130):
        a = m.put(b); out = m.buf(max_)
        r = m.f('wf_utf8', a, len(b), out, max_)
        s = m.bytes_at(out, r)
        return s, m.bytes_at(out + r, 1) == b'\0' and r == len(s)

    for ok in ('Home', 'Sam’s', '咖啡', 'Café', '\U0001f4f6 WiFi', ' ', '\U0010ffff'):
        s, term = utf8(ok.encode())
        expect(s == ok.encode() and term, f'wf_utf8 keeps {ok!r}')
    for bad, want in ((b'a\x80b', b'a?b'), (b'\xc0\x80', b'??'), (b'\xe2\x80', b'??'), (b'\xed\xa0\x80', b'???'), (b'\xf5\x80\x80\x80', b'????'), (b'a\x01b\x1f\x7fc', b'a?b??c'),
                      (b'\xff', b'?'), (b'\xe0\x80\x80', b'???'), (b'\xf0\x80\x80\x80', b'????'), (b'\xf4\x90\x80\x80', b'????'), (b'\xc3', b'?')):
        s, term = utf8(bad)
        expect(s == want and term, f'wf_utf8 {bad!r} -> {want!r}: a malformed sequence, a control character and a byte that starts nothing become ? (got {s!r})')
    s, term = utf8('ab’cd'.encode(), 6)
    expect(s == b'ab' + '’'.encode() and term and len(s) < 6, 'wf_utf8 never cuts a character in two at the end of the buffer')
    s, term = utf8(b'abcdef', 4)
    expect(s == b'abc' and term, 'wf_utf8 leaves room for the NUL')
    expect(m.f('wf_utf8', m.put(b'x'), 1, m.buf(4), 0) == 0, 'a zero-size buffer is left alone')

    # an SSID from the supplicant to the screen and back to the supplicant
    ssid = 'Sam’s iPhone'.encode()
    nets = m.buf(NET * 4)
    n = m.f('wf_parse_scan', m.put(scan_text([(-48, '[WPA2-PSK-CCMP][ESS]', ssid)]).encode()), nets, 4)
    got = m.nets(nets, n)[0]
    hexb = m.buf(100); m.f('wf_hex', nets, len(got['ssid']), hexb)
    expect(n == 1 and got['ssid'] == ssid and m.read_cstr(hexb) == ssid.hex(),'a scanned SSID: the bytes, and the hex SET_NETWORK ssid takes (UTF-8 apostrophe intact)')


def security_tests(ctx):
    expect = ctx.expect
    m = Lib()
    sec = lambda fl: m.f('wf_security', m.put(fl.encode()))
    cases = (('', 'OPEN'), ('[ESS]', 'OPEN'), ('[IBSS]', 'OPEN'), ('[WPA2-PSK-CCMP][ESS]', 'PSK'), ('[WPA-PSK-TKIP][ESS]', 'PSK'), ('[WPA-PSK-CCMP+TKIP][WPA2-PSK-CCMP+TKIP][ESS]', 'PSK'),
             ('[WPA2-PSK-CCMP][WPS][ESS]', 'PSK'), ('[WPA2-FT/PSK-CCMP][ESS]', 'PSK'), ('[WPA2-PSK-SHA256-CCMP][ESS]', 'PSK'), ('[RSN-PSK-CCMP][ESS]', 'PSK'),
             ('[WPA2-PSK+SAE-CCMP][ESS]', 'TRANS'), ('[WPA2-PSK+FT/PSK+SAE-CCMP][ESS]', 'TRANS'), ('[WPA2-PSK+SAE-CCMP][SAE-H2E][ESS]', 'TRANS'),
             ('[WPA2-SAE-CCMP][ESS]', 'SAE'), ('[RSN-SAE-CCMP][ESS]', 'SAE'), ('[WPA2-FT/SAE-CCMP][ESS]', 'SAE'), ('[WPA2-SAE-CCMP][SAE-H2E][ESS]', 'SAE'),
             ('[RSN-OWE-CCMP][ESS]', 'OWE'), ('[WPA2-OWE-CCMP][ESS]', 'OWE'),
             ('[WPA2-EAP-CCMP][ESS]', 'EAP'), ('[WPA-EAP-TKIP][ESS]', 'EAP'), ('[WPA2-EAP-SUITE-B-192-CCMP][ESS]', 'EAP'), ('[WPA2-FT/EAP-CCMP][ESS]', 'EAP'), ('[WPA2-EAP+EAP-SHA256-CCMP][ESS]', 'EAP'),
             ('[RSN-EAP-CCMP][ESS]', 'EAP'), ('[WEP][ESS]', 'WEP'), ('[WEP]', 'WEP'))
    for fl, want in cases:
        expect(sec(fl) == SEC[want], f'flags {fl!r} are {want} (got {sec(fl)})')
    km = lambda v: m.f('wf_security_keymgmt', m.put(v.encode()))
    for v, want in (('NONE', 'OPEN'), ('WPA-PSK', 'PSK'), ('WPA-PSK WPA-PSK-SHA256', 'PSK'), ('WPA-PSK SAE', 'TRANS'), ('WPA-PSK WPA-PSK-SHA256 SAE', 'TRANS'), ('SAE', 'SAE'), ('FT-SAE', 'SAE'),
                    ('OWE', 'OWE'), ('WPA-EAP', 'EAP'), ('WPA-EAP-SUITE-B-192', 'EAP'), ('IEEE8021X', 'EAP'), ('', 'OPEN')):
        expect(km(v) == SEC[want], f'key_mgmt {v!r} is {want}')
    label = lambda v: m.read_cstr(m.f('wf_sec_label', SEC[v]))
    expect([label(v) for v in SEC] == ['Open', 'Enhanced Open', 'WEP', 'WPA/WPA2', 'WPA2/WPA3', 'WPA3', 'Enterprise'] and m.read_cstr(m.f('wf_sec_label', 99)) == 'Open', 'the security names of the info page')
    out = m.buf(24)
    HD = 'Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n'
    route = lambda text: (m.f('wf_parse_route', m.put(text.encode()), out, 24), m.read_cstr(out))
    expect(route(HD + 'wlan0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n') == (1, '192.168.1.1'), 'the default gateway: the kernel prints the 32 bit address as hex, little endian')
    expect(route(HD + 'wlan0\t0001A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\nwlan0\t00000000\tFE64000A\t0003\t0\t0\t0\t00000000\t0\t0\t0\n') == (1, '10.0.100.254'), 'the connected network\'s own route is skipped, the default one found (no leading zeros, three digits)')
    expect(route(HD + 'eth0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n')[0] == 0 and route(HD + 'wlan0\t00000000\t00000000\t0001\t0\t0\t0\t00000000\t0\t0\t0\n')[0] == 0
           and route(HD + 'wlan0\t00000000\t0101A8C0\t0001\t0\t0\t0\t00000000\t0\t0\t0\n')[0] == 0 and route('') == (0, '') and route(HD) == (0, '') and route('wlan0\t00000000\n')[0] == 0,
           'another interface, no gateway, a route that is up but not via a gateway, an empty file and a cut line give none')
    expect(route(HD + 'wlan0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0')[0] == 1, 'the last line needs no newline')
    levels = ((-30, 4), (-65, 4), (-66, 3), (-75, 3), (-76, 2), (-80, 2), (-81, 1), (-95, 1))
    out = m.buf(NET * 16)
    n = m.f('wf_parse_scan', m.put(scan_text([(d, '[ESS]', f'n{-d}'.encode()) for d, _ in levels]).encode()), out, 16)
    got = {r['dbm']: r['level'] for r in m.nets(out, n)}
    for dbm, want in levels:
        expect(got[dbm] == want, f'{dbm} dBm is level {want}, the stock page\'s thresholds (got {got[dbm]})')

    pw = lambda p, s: m.f('wf_pass_ok', m.put(p.encode('latin-1')), SEC[s])
    expect(pw('12345678', 'PSK') == 1 and pw('1234567', 'PSK') == 0 and pw('x' * 63, 'PSK') == 1 and pw('x' * 64, 'PSK') == 0 and pw('a' * 64, 'PSK') == 1 and pw('g' * 64, 'PSK') == 0
           and pw('', 'PSK') == 0 and pw('pass word!', 'TRANS') == 1 and pw('cafécafé', 'PSK') == 0 and pw('tab\tword1', 'PSK') == 0,
           'a PSK passphrase is 8..63 printable ASCII bytes or 64 hex digits')
    ph = lambda p: m.f('wf_pass_hex', m.put(p.encode()))
    expect(ph('a' * 64) == 1 and ph('A1' * 32) == 1 and ph('a' * 63) == 0 and ph('a' * 65) == 0 and ph('g' * 64) == 0 and ph('') == 0, 'a 64 digit hex key is told from a passphrase')
    expect(pw('a', 'SAE') == 1 and pw('x' * 127, 'SAE') == 1 and pw('x' * 128, 'SAE') == 0 and pw('', 'SAE') == 0 and pw('pé', 'SAE') == 0, 'a WPA3 password is 1..127 printable ASCII bytes')


def scan_tests(ctx):
    expect = ctx.expect
    m = Lib()
    def scan(rows, mx=WF_MAX, text=None):
        out = m.buf(NET * 40)
        return m.nets(out, m.f('wf_parse_scan', m.put((scan_text(rows) if text is None else text).encode()), out, mx))
    rows = [(-70, '[WPA2-PSK-CCMP][ESS]', b'Cafe'), (-45, '[ESS]', b'Open One'), (-60, '[WPA2-SAE-CCMP][ESS]', b'Safe'), (-52, '[WPA2-PSK-CCMP][WPS][ESS]', b'Cafe'),
            (-30, '[ESS]', b''), (-31, '[ESS]', b'\x00\x00\x00'), (-80, '[WEP][ESS]', b'Old'), (-75, '[WPA2-EAP-CCMP][ESS]', b'Corp'), (-90, '[WPA2-PSK+SAE-CCMP][ESS]', b'Mix')]
    got = scan(rows)
    expect([(r['ssid'], r['sec'], r['dbm']) for r in got] == [(b'Open One', SEC['OPEN'], -45), (b'Cafe', SEC['PSK'], -52), (b'Safe', SEC['SAE'], -60), (b'Corp', SEC['EAP'], -75),
                                                         (b'Old', SEC['WEP'], -80), (b'Mix', SEC['TRANS'], -90)]
           and all(r['known'] == 0 and r['current'] == 0 and r['id'] == -1 for r in got) and [r['level'] for r in got] == [4, 4, 4, 3, 2, 1],
           f'the scan: one row per name (the stronger access point), strongest first, hidden names left out, the level from the signal: {[(r["ssid"], r["dbm"]) for r in got]}')
    got = scan([(-80, '[WPA2-PSK-CCMP][ESS]', b'Cafe'), (-50, '[ESS]', b'X'), (-40, '[WPA2-SAE-CCMP][ESS]', b'Cafe')])
    expect([(r['ssid'], r['sec'], r['dbm']) for r in got] == [(b'Cafe', SEC['SAE'], -40), (b'X', SEC['OPEN'], -50)], 'a later, stronger access point of a name takes its place and its flags')
    got = scan([(-60, '[ESS]', b'a'), (-70, '[ESS]', b'b'), (-80, '[ESS]', b'c'), (-65, '[ESS]', b'd'), (-90, '[ESS]', b'e')], mx=3)
    expect([r['ssid'] for r in got] == [b'a', b'd', b'b'], f'a full list keeps the strongest: {[r["ssid"] for r in got]}')
    expect(scan([], text='') == [] and scan([]) == [] and scan([], text='bssid / frequency / signal level / flags / ssid\n') == [] and scan([], text='garbage\nmore\tgarbage\n') == [],
           'an empty reply, a header alone and lines that are not scan rows give nothing')
    long = bytes(range(65, 65 + 40))
    got = scan([(-50, '[ESS]', long)])
    expect(len(got) == 1 and got[0]['ssid'] == long[:32], 'a name longer than 32 bytes is cut at 32')
    got = scan([(-50, '[ESS]', b'a"b\\c\xe2\x80\x99\ttab')])
    expect(got and got[0]['ssid'] == b'a"b\\c\xe2\x80\x99\ttab', 'escapes in a scan row')
    text = scan_text([(-50, '[WPA2-PSK-CCMP][ESS]', b'Cafe')]).rstrip('\n')   # no newline after the last row
    expect([r['ssid'] for r in scan([], text=text)] == [b'Cafe'], 'the last row needs no newline')

    # LIST_NETWORKS
    out = m.buf(NET * 20)
    txt = list_text([(0, b'Home', '[CURRENT]'), (1, 'Sam’s'.encode(), '[DISABLED]'), (2, b'bad', '[TEMP-DISABLED]'), (13, b'a\\b"c', ''), (4, b'Both', '[CURRENT][TEMP-DISABLED]')])
    n = m.f('wf_parse_list', m.put(txt.encode()), out, 16)
    got = m.nets(out, n)
    expect([(r['id'], r['ssid'], r['current'], r['bad'], r['known']) for r in got] == [(0, b'Home', 1, 0, 1), (1, 'Sam’s'.encode(), 0, 0, 1), (2, b'bad', 0, 1, 1), (13, b'a\\b"c', 0, 0, 1),
                                                                                    (4, b'Both', 1, 1, 1)], f'the saved networks: ids, names as bytes, [CURRENT], [TEMP-DISABLED]: {got}')
    expect([r['off'] for r in got] == [0, 1, 0, 0, 0], f'[DISABLED] is Auto-Join off, [TEMP-DISABLED] is not: {[r["off"] for r in got]}')
    expect(m.f('wf_parse_list', m.put(txt.encode()), out, 2) == 2 and m.f('wf_parse_list', m.put(b''), out, 16) == 0 and m.f('wf_parse_list', m.put(b'network id / ssid / bssid / flags\n'), out, 16) == 0
           and m.f('wf_parse_list', m.put(b'\n\nfoo\n'), out, 16) == 0, 'the list is bounded; an empty reply and a header alone are no networks')

    # STATUS
    st = m.buf(80)
    def status(text):
        m.f('wf_parse_status', m.put(text.encode('latin-1') if isinstance(text, str) else text), st)
        r = m.bytes_at(st, 80)
        status.ip = r[46:66].split(b'\0')[0]
        return struct.unpack_from('<iii', r, 0), r[12:12 + r[45]]
    for state, want in (('COMPLETED', ST_CONNECTED), ('ASSOCIATING', ST_CONNECTING), ('ASSOCIATED', ST_CONNECTING), ('AUTHENTICATING', ST_CONNECTING), ('4WAY_HANDSHAKE', ST_CONNECTING),
                        ('GROUP_HANDSHAKE', ST_CONNECTING), ('SCANNING', ST_SCANNING), ('DISCONNECTED', ST_IDLE), ('INACTIVE', ST_IDLE), ('INTERFACE_DISABLED', ST_IDLE)):
        (s, i, ip), ssid = status(status_text(state, b'Home', 3, None))
        expect(s == want and i == 3 and ip == 0 and ssid == b'Home', f'wpa_state {state} is state {want}')
    (s, i, ip), ssid = status(status_text('COMPLETED', 'Sam’s'.encode(), 7, '10.0.0.5'))
    expect(s == ST_CONNECTED and i == 7 and ip == 1 and ssid == 'Sam’s'.encode() and status.ip == b'10.0.0.5', 'STATUS: the id, the name as bytes, the address')
    status(status_text('COMPLETED', b'Home', 0, '192.168.100.200'))
    expect(status.ip == b'192.168.100.200', 'the address text')
    status(status_text('COMPLETED', b'Home', 0, '1234567890123456789012345'))
    expect(len(status.ip) == 19, 'an address too long for the field is cut, its end a NUL')
    status(status_text('DISCONNECTED', b'Home', 0, None))
    expect(status.ip == b'', 'no address: empty')
    (s, i, ip), ssid = status('wpa_state=DISCONNECTED\naddress=aa:bb:cc:dd:ee:ff\n')
    expect(s == ST_IDLE and i == -1 and ip == 0 and ssid == b'', 'a status without a network has id -1')
    (s, i, ip), ssid = status('bssid=00:11:22:33:44:55\nwpa_state=COMPLETED\nip_address=')
    expect(s == ST_CONNECTED and ip == 0, 'an empty ip_address is no address; bssid= is not ssid=')

    # the merge
    def merge(scanned, known, cur, mx=WF_MAX):
        nets, kn, nref = m.buf(NET * 40), m.buf(NET * 20), m.buf(4)
        for i, a in enumerate(scanned): m.put_net(nets + i * NET, **a)
        for i, a in enumerate(known): m.put_net(kn + i * NET, **dict(dict(known=1, level=0, dbm=0), **a))
        m.setword(nref, len(scanned)); m.setword(STACK + 16, len(known)); m.setword(STACK + 20, cur & 0xffffffff)
        m.call(PSYMS['wf_merge'], a0=nets, a1=nref, a2=mx, a3=kn, count=3000000)
        return m.nets(nets, m.word(nref))
    S = lambda name, dbm, **kw: dict(ssid=name, dbm=dbm, level=4 if dbm >= -65 else 3, **kw)
    got = merge([S(b'Home', -50), S(b'Cafe', -60), S(b'Net', -70), S(b'Zed', -72)], [dict(ssid=b'Cafe', nid=0), dict(ssid=b'Gone', nid=1, sec=SEC['SAE'])], -1)
    expect([(r['ssid'], r['known'], r['id'], r['level'], r['current']) for r in got] == [(b'Cafe', 1, 0, 4, 0), (b'Home', 0, -1, 4, 0), (b'Net', 0, -1, 3, 0), (b'Zed', 0, -1, 3, 0), (b'Gone', 1, 1, 0, 0)]
           and got[4]['sec'] == SEC['SAE'], f'saved networks in range first, then the others by signal, the saved ones out of range last (level 0, their own security): {[(r["ssid"], r["id"]) for r in got]}')
    got = merge([S(b'Home', -50), S(b'Cafe', -60)], [dict(ssid=b'Cafe', nid=0), dict(ssid=b'Gone', nid=1)], 1)
    expect([(r['ssid'], r['current']) for r in got] == [(b'Gone', 1), (b'Cafe', 0), (b'Home', 0)], 'the current network (by id) comes first, even out of range')
    got = merge([S(b'Home', -50), S(b'Cafe', -60)], [dict(ssid=b'Cafe', nid=0)], 0)
    expect([(r['ssid'], r['current']) for r in got] == [(b'Cafe', 1), (b'Home', 0)], 'the current network is marked on its scanned row')
    got = merge([S(b'Home', -50)], [dict(ssid=b'Home', nid=3)], -1)
    expect(len(got) == 1 and got[0]['known'] == 1 and got[0]['id'] == 3, 'a saved network found by the scan is one row')
    got = merge([S(b'Home', -50)], [dict(ssid=b'Home', nid=3, off=1), dict(ssid=b'Gone', nid=4, off=1)], -1)
    expect([(r['ssid'], r['off']) for r in got] == [(b'Home', 1), (b'Gone', 1)], 'Auto-Join off goes with the saved network, found by the scan or not')
    got = merge([S(b'a', -50), S(b'b', -55)], [dict(ssid=b'k1', nid=1), dict(ssid=b'k2', nid=2), dict(ssid=b'k3', nid=3)], -1, mx=4)
    expect([r['ssid'] for r in got] == [b'a', b'k1', b'k2', b'k3'], 'over the limit the weakest unsaved network goes, the saved ones stay')
    got = merge([], [dict(ssid=b'k1', nid=5), dict(ssid=b'k2', nid=6)], -1)
    expect([r['ssid'] for r in got] == [b'k1', b'k2'], 'with no scan the saved networks show, in their order')
    got = merge([S('Zoë'.encode(), -50)], [dict(ssid='Zoë'.encode(), nid=2)], -1)
    expect(got[0]['known'] == 1 and got[0]['id'] == 2, 'a name is matched byte for byte')


def split_tests(ctx):
    expect = ctx.expect
    m = Lib()
    CAP = 16384

    bufs = [m.buf(CAP + 1), m.buf(CAP + 1), m.buf(4), m.buf(4), m.buf(CAP)]

    def split(text, cap=CAP):
        data = text.encode()
        st, ou, ns, no, a = bufs
        m.u.mem_write(a, data + b'\0')
        m.setword(STACK + 16, ou); m.setword(STACK + 20, no); m.setword(STACK + 24, cap)
        r = m.call(PSYMS['wf_split'], a0=a, a1=len(data), a2=st, a3=ns, count=20000000)
        r = struct.unpack('<i', struct.pack('<I', r))[0]
        s_len, o_len = m.word(ns), m.word(no)
        s, o = m.bytes_at(st, s_len + 1), m.bytes_at(ou, o_len + 1)
        return r, s[:-1].decode(), o[:-1].decode(), s[-1] == 0 and o[-1] == 0

    def ref(text):
        """The model: lines outside network blocks go to stock; a block goes to stock when every key is one stock writes and key_mgmt is NONE / WPA-PSK, else to ours (blocks followed by a blank line)."""
        keys = {'ssid', 'scan_ssid', 'bssid', 'psk', 'key_mgmt', 'priority', 'disabled', 'id_str', 'proto', 'pairwise', 'group', 'auth_alg', 'wep_key0', 'wep_key1', 'wep_key2', 'wep_key3',
                'wep_tx_keyidx', 'frequency', 'mode'}
        stock, ours, blk = '', '', None
        for line in text.splitlines(True):
            t = line.lstrip(' \t')
            if blk is None and t.startswith('network={'): blk = [line]
            elif blk is not None:
                blk.append(line)
                if t.startswith('}'):
                    ok = True
                    for l in blk[1:-1]:
                        q = l.strip(' \t\r\n')
                        if not q or q[0] in '#}': continue
                        k, _, v = q.partition('=')
                        if '=' not in q or k not in keys: ok = False
                        elif k == 'key_mgmt' and not (v.split() and all(x in ('NONE', 'WPA-PSK') for x in v.split())): ok = False
                    if ok: stock += ''.join(blk)
                    else: ours += ''.join(blk) + '\n'
                    blk = None
            else: stock += line
        return stock, ours

    HEAD = 'ctrl_interface=/var/run/wpa_supplicant\nctrl_interface_group=0\nupdate_config=1\n'
    def net(*lines): return '\nnetwork={\n' + ''.join(f'\t{l}\n' for l in lines) + '}\n'
    HOME = net('ssid="Home"', 'psk="secret123"', 'key_mgmt=WPA-PSK', 'priority=5')
    OPEN = net('ssid="Cafe"', 'key_mgmt=NONE', 'scan_ssid=1')
    SAE = net('ssid="Safe"', 'sae_password="pw"', 'key_mgmt=SAE', 'ieee80211w=2')
    cases = {
        'stock networks stay': (HEAD + HOME + OPEN, HEAD + HOME + OPEN, ''),
        'Auto-Join off keeps a stock network with stock': (HEAD + net('ssid="Home"', 'psk="secret123"', 'key_mgmt=WPA-PSK', 'priority=5', 'disabled=1') + OPEN, HEAD + net('ssid="Home"', 'psk="secret123"', 'key_mgmt=WPA-PSK', 'priority=5', 'disabled=1') + OPEN, ''),
        'Auto-Join off keeps a WPA3 network with ours': (HEAD + net('ssid="Safe"', 'sae_password="pw"', 'key_mgmt=SAE', 'ieee80211w=2', 'disabled=1'), HEAD + '\n', net('ssid="Safe"', 'sae_password="pw"', 'key_mgmt=SAE', 'ieee80211w=2', 'disabled=1').lstrip('\n') + '\n'),
        'WPA3 goes to ours': (HEAD + HOME + SAE + OPEN, HEAD + HOME + '\n' + OPEN, SAE.lstrip('\n') + '\n'),
        'WPA2/WPA3 transition': (HEAD + net('ssid="T"', 'psk="12345678"', 'key_mgmt=WPA-PSK SAE', 'ieee80211w=1'), HEAD + '\n', net('ssid="T"', 'psk="12345678"', 'key_mgmt=WPA-PSK SAE', 'ieee80211w=1').lstrip('\n') + '\n'),
        'a hidden WPA3 network keeps scan_ssid with ours': (HEAD + net('ssid="H"', 'scan_ssid=1', 'sae_password="pw"', 'key_mgmt=SAE', 'ieee80211w=2'), HEAD + '\n', net('ssid="H"', 'scan_ssid=1', 'sae_password="pw"', 'key_mgmt=SAE', 'ieee80211w=2').lstrip('\n') + '\n'),
        'a hidden WPA2 network keeps scan_ssid with stock': (HEAD + net('ssid="H"', 'scan_ssid=1', 'psk="12345678"', 'key_mgmt=WPA-PSK'), HEAD + net('ssid="H"', 'scan_ssid=1', 'psk="12345678"', 'key_mgmt=WPA-PSK'), ''),
        'Enhanced Open': (HEAD + net('ssid="O"', 'key_mgmt=OWE', 'ieee80211w=2'), HEAD + '\n', net('ssid="O"', 'key_mgmt=OWE', 'ieee80211w=2').lstrip('\n') + '\n'),
        'enterprise': (HEAD + net('ssid="Corp"', 'key_mgmt=WPA-EAP', 'eap=PEAP', 'identity="me"', 'password="x"', 'phase2="auth=MSCHAPV2"'), HEAD + '\n',
                       net('ssid="Corp"', 'key_mgmt=WPA-EAP', 'eap=PEAP', 'identity="me"', 'password="x"', 'phase2="auth=MSCHAPV2"').lstrip('\n') + '\n'),
        'a PSK network with PMF is ours': (HEAD + net('ssid="P"', 'psk="12345678"', 'key_mgmt=WPA-PSK', 'ieee80211w=1'), HEAD + '\n', net('ssid="P"', 'psk="12345678"', 'key_mgmt=WPA-PSK', 'ieee80211w=1').lstrip('\n') + '\n'),
        'an unknown key is ours': (HEAD + net('ssid="U"', 'key_mgmt=NONE', 'mem_only_psk=1'), HEAD + '\n', net('ssid="U"', 'key_mgmt=NONE', 'mem_only_psk=1').lstrip('\n') + '\n'),
        'a WEP network stays with stock': (HEAD + net('ssid="W"', 'key_mgmt=NONE', 'wep_key0=0123456789', 'wep_tx_keyidx=0', 'auth_alg=OPEN SHARED'), HEAD + net('ssid="W"', 'key_mgmt=NONE', 'wep_key0=0123456789', 'wep_tx_keyidx=0', 'auth_alg=OPEN SHARED'), ''),
        'a brace in a value': (HEAD + net('ssid="a}b"', 'key_mgmt=NONE') + SAE, HEAD + net('ssid="a}b"', 'key_mgmt=NONE') + '\n', SAE.lstrip('\n') + '\n'),
        'comments and blank lines in a block': (HEAD + '\nnetwork={\n\t# a note\n\n\tssid="C"\n\tkey_mgmt=NONE\n}\n', HEAD + '\nnetwork={\n\t# a note\n\n\tssid="C"\n\tkey_mgmt=NONE\n}\n', ''),
        'indented block': (HEAD + '\n  network={\n  ssid="I"\n  key_mgmt=NONE\n  }\n', HEAD + '\n  network={\n  ssid="I"\n  key_mgmt=NONE\n  }\n', ''),
        'no networks': (HEAD, HEAD, ''),
        'empty file': ('', '', ''),
        'a block without key_mgmt': (HEAD + net('ssid="N"', 'psk="12345678"'), HEAD + net('ssid="N"', 'psk="12345678"'), ''),
        'an empty key_mgmt': (HEAD + net('ssid="N"', 'key_mgmt='), HEAD + '\n', net('ssid="N"', 'key_mgmt=').lstrip('\n') + '\n'),
        'a line without =': (HEAD + net('ssid="N"', 'garbage'), HEAD + '\n', net('ssid="N"', 'garbage').lstrip('\n') + '\n'),
        'no newline at the end': (HEAD + SAE.rstrip('\n'), HEAD + '\n', SAE.lstrip('\n')),
        'a block that never ends (a cut file)': (HEAD + '\nnetwork={\n\tssid="x"\n', HEAD + '\n', ''),
    }
    for name, (src, want_stock, want_ours) in cases.items():
        r, s, o, term = split(src)
        expect(r == 0 and s == want_stock and o == want_ours and term, f'{name}: stock {s!r} ours {o!r}')
        expect((s, o) == ref(src), f'{name}: the reference model agrees')
    # the two outputs together hold every network once; stock's part splits to itself
    src = HEAD + HOME + SAE + OPEN + net('ssid="O"', 'key_mgmt=OWE', 'ieee80211w=2')
    r, s, o, _ = split(src)
    r2, s2, o2, _ = split(s)
    expect(r2 == 0 and s2 == s and o2 == '' and s.count('network={') + o.count('network={') == src.count('network='), 'every network is in exactly one output, and the stock part needs no second split')
    # the size
    exact = HEAD + HOME
    r, s, o, _ = split(exact, cap=len(exact) + 1)
    expect(r == 0 and s == exact, 'an output that just fits')
    r, s, o, _ = split(exact, cap=len(exact))
    expect(r == -1, 'an output that is one byte short is refused')
    r, s, o, _ = split(HEAD + SAE, cap=len(SAE.lstrip('\n')))
    expect(r == -1, 'ours too small is refused')
    # a random corpus against the model
    import random
    rnd = random.Random(7)
    pool = ['ssid="x"', 'psk="12345678"', 'key_mgmt=NONE', 'key_mgmt=WPA-PSK', 'key_mgmt=SAE', 'key_mgmt=WPA-PSK SAE', 'key_mgmt=OWE', 'key_mgmt=WPA-EAP', 'key_mgmt=NONE WPA-PSK', 'priority=3', 'scan_ssid=1',
            'ieee80211w=2', 'sae_password="a"', 'eap=TTLS', 'identity="u"', 'proto=RSN', 'pairwise=CCMP', 'disabled=1', 'wep_key0=abcde', 'foo=bar', 'bssid=00:11:22:33:44:55', '# c', '']
    bad = 0
    for _ in range(120):
        src = HEAD
        for _ in range(rnd.randint(0, 4)): src += net(*[rnd.choice(pool) for _ in range(rnd.randint(1, 5))])
        r, s, o, term = split(src)
        if r != 0 or (s, o) != ref(src) or not term: bad += 1
    expect(bad == 0, f'120 random configurations split as the model says ({bad} differ)')



# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the supplicant

class Supp:
    """A scripted wpa_supplicant: the commands the page sends, the networks it keeps (saved to a configuration text as hostap writes it), the scan, the state."""
    STOCK_KM = 'WPA-PSK WPA-EAP IEEE8021X NONE WPA-NONE FT-PSK FT-EAP WPA-PSK-SHA256 WPA-EAP-SHA256'
    OURS_KM = STOCK_KM + ' SAE FT-SAE OWE'
    HEAD = 'ctrl_interface=/var/run/wpa_supplicant\nctrl_interface_group=0\nupdate_config=1\n'

    def __init__(self, ours=True, scan=(), known=()):
        self.ours, self.alive, self.scan, self.log = ours, True, list(scan), []
        self.nets, self.next = {}, 0
        for ssid, fields in known:
            f = dict(fields); dis = int(f.pop('disabled', '0'))
            self.nets[self.next] = dict(ssid=ssid, f=f, dis=dis); self.next += 1
        self.state, self.cur, self.ip = 'DISCONNECTED', None, None
        self.refuse, self.failed, self.temp, self.saves, self.copy = set(), set(), set(), 0, True

    def conf_text(self):
        out = self.HEAD
        for i, n in self.nets.items():
            out += '\nnetwork={\n'
            ssid = n['ssid']
            out += (f'\tssid="{ssid.decode()}"\n' if ssid.isascii() and all(32 <= c < 127 and c not in (34, 92) for c in ssid) else f'\tssid={ssid.hex()}\n')
            for k, v in n['f'].items(): out += f'\t{k}={v}\n'
            if n['dis']: out += '\tdisabled=1\n'
            out += '}\n'
        return out

    def handle(self, cmd, m):
        self.log.append(cmd)
        if not self.alive: return None
        w = cmd.split(' ', 3)
        c = w[0]
        if cmd in self.failed or c in self.failed: return 'FAIL\n'
        if c == 'PING': return 'PONG\n'
        if c == 'STATUS':
            if self.cur is None or self.state == 'DISCONNECTED': return f'wpa_state={self.state}\naddress=aa:bb:cc:dd:ee:ff\n'
            return status_text(self.state, self.nets[self.cur]['ssid'], self.cur, self.ip)
        if c == 'LIST_NETWORKS':   # (hostap: LAST_ID=n lists the networks after n; the reply is cut at 4095 bytes, at a whole line)
            last = int(w[1][8:]) if len(w) > 1 and w[1].startswith('LAST_ID=') else -1
            head = 'network id / ssid / bssid / flags\n'
            out = head
            for line in list_text([(i, n['ssid'], ('[CURRENT]' if i == self.cur and self.state != 'DISCONNECTED' else '') + ('[DISABLED]' if n['dis'] else '') + ('[TEMP-DISABLED]' if i in self.temp else '')) for i, n in self.nets.items() if i > last]).split('\n')[1:-1]:
                if len(out) + len(line) + 1 > 4095: break
                out += line + '\n'
            return out
        if c == 'GET_CAPABILITY': return (self.OURS_KM if self.ours else self.STOCK_KM) + '\n'
        if c == 'GET_NETWORK': return (str(self.nets[int(w[1])]['dis']) if w[2] == 'disabled' else self.nets[int(w[1])]['f'].get(w[2], 'FAIL')) + '\n'
        if c == 'SCAN': return 'OK\n'
        if c == 'SCAN_RESULTS': return scan_text(self.scan)
        if c == 'ADD_NETWORK':
            self.nets[self.next] = dict(ssid=b'', f={}, dis=1); self.next += 1; return f'{self.next - 1}\n'   # (hostap adds a network disabled)
        if c == 'SET_NETWORK':
            nid, key, val = int(w[1]), w[2], cmd.split(' ', 3)[3]
            if key in self.refuse: return 'FAIL\n'
            if key == 'ssid': self.nets[nid]['ssid'] = bytes.fromhex(val)
            else: self.nets[nid]['f'][key] = val.replace('"', '', 0)
            return 'OK\n'
        if c == 'ENABLE_NETWORK':
            for i, n in self.nets.items():
                if w[1] == 'all' or int(w[1]) == i: n['dis'] = 0
            return 'OK\n'
        if c == 'DISABLE_NETWORK':
            self.nets[int(w[1])]['dis'] = 1
            if self.cur == int(w[1]): self.state = 'DISCONNECTED'
            return 'OK\n'
        if c == 'SELECT_NETWORK':
            self.cur, self.state = int(w[1]), 'ASSOCIATING'
            for i, n in self.nets.items(): n['dis'] = int(i != self.cur)   # hostap: every other network is disabled
            return 'OK\n'
        if c == 'REMOVE_NETWORK':
            self.nets.pop(int(w[1]), None)
            if self.cur == int(w[1]): self.cur, self.state = None, 'DISCONNECTED'
            return 'OK\n'
        if c == 'DISCONNECT':
            self.state = 'DISCONNECTED'; return 'OK\n'
        if c == 'SAVE_CONFIG':
            self.saves += 1
            m.fs[WF_COPY if self.copy else WF_CONF] = self.conf_text().encode()
            return 'OK\n'
        return 'UNKNOWN COMMAND\n'


WF_COPY, WF_CONF, WF_OURS = '/tmp/m1plus-wpa.conf', '/mnt/data/wpa_supplicant.conf', '/mnt/data/m1plus/wifi-networks'
SOCK_FD, PID = 41, 4242


class SM(Lib):
    """A base machine with the control socket (a datagram socket the scripted supplicant answers), the stock Wi-Fi switch scripted; a stock text dialog (navigator_to dialog/kb...) is only recorded and cancelled (the page uses none)."""
    def __init__(self, supp=None):
        super().__init__()
        self.supp, self.sock = supp or Supp(), []
        self.fail_sock, self.pending, self.sel_out = set(), None, None
        self.dirs |= {'/mnt/data', '/mnt/data/m1plus', '/tmp'}

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3, sp = u.reg_read_batch((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_SP))
        ret = None
        if name == 'socket':
            self.sock.append(('socket', a0, a1, a2)); ret = 0xffffffff if 'socket' in self.fail_sock else SOCK_FD
        elif name == 'bind':
            path = self.read_cstr(a1 + 2); self.sock.append(('bind', self.word(a1) & 0xffff, path, a2)); ret = 0xffffffff if 'bind' in self.fail_sock else 0
        elif name == 'connect':
            path = self.read_cstr(a1 + 2); self.sock.append(('connect', self.word(a1) & 0xffff, path, a2)); ret = 0xffffffff if 'connect' in self.fail_sock or not self.supp.alive else 0
        elif name == 'send':
            cmd = self.read_cstr(a1)[:a2]; self.sock.append(('send', a0, cmd, a3))
            self.pending = None if 'send' in self.fail_sock else self.supp.handle(cmd, self)
            ret = 0xffffffff if 'send' in self.fail_sock else a2
        elif name == 'select':
            fds = self.word(a1 + 4 * (SOCK_FD >> 5)); tvp = self.word(sp + 16); tv = (self.word(tvp), self.word(tvp + 4))
            self.sock.append(('select', a0, bool(fds >> (SOCK_FD & 31) & 1), tv)); ret = 1 if self.pending is not None and 'select' not in self.fail_sock else 0
        elif name == 'recv':
            data = (self.pending or '').encode('latin-1')[:max(a2, 0)]
            self.u.mem_write(a1, data); self.sock.append(('recv', a0, a2, len(data))); self.pending = None; ret = len(data)
        elif name == 'getpid':
            ret = PID
        elif name == 'close' and a0 == SOCK_FD:
            self.sock.append(('close', a0)); ret = 0
        elif name == 'unlink' and self.read_cstr(a0).startswith('/tmp/m1plus-wc-'):
            self.sock.append(('unlink', self.read_cstr(a0))); ret = 0
        elif name == 'wifi_switch':
            on = self.u.mem_read(pod.DATA['WIFI_FLAG'][0], 1)[0]
            self.sock.append(('wifi_switch', a0, on)); self.u.mem_write(pod.DATA['WIFI_FLAG'][0], bytes([0 if on else 1])); ret = 0
            if not on: self.supp.alive = True
        elif name == 'navigator_to' and self.read_cstr(a0).startswith('dialog/kb'):
            self.sock.append(('dialog', self.read_cstr(a0))); ret = 1
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def ctrl_tests(ctx):
    expect = ctx.expect
    supp = Supp(scan=[(-50, '[ESS]', b'x')])
    m = SM(supp)
    rep = m.buf(256)

    def send(text, size=256, mm=None):
        mm = mm or m; mm.sock = []; mm.supp.log = []
        r = mm.call(PSYMS['wf_cmd'], a0=mm.put(text.encode()), a1=rep, a2=size, count=200000)
        return struct.unpack('<i', struct.pack('<I', r))[0], mm.read_cstr(rep)
    n, text = send('STATUS')
    expect(n == len(text) and text.startswith('wpa_state=DISCONNECTED'), f'wf_cmd returns the reply and its length ({n})')
    s = m.sock
    expect([x[0] for x in s] == ['socket', 'unlink', 'bind', 'connect', 'send', 'select', 'recv', 'close', 'unlink'], f'one datagram exchange: {[x[0] for x in s]}')
    expect(s[0] == ('socket', 1, 1, 0), 'AF_UNIX and SOCK_DGRAM (1 on MIPS), as wpa_ctrl')
    expect(s[1] == ('unlink', f'/tmp/m1plus-wc-{PID}') and s[2][1:3] == (1, f'/tmp/m1plus-wc-{PID}') and s[2][3] == 2 + len(f'/tmp/m1plus-wc-{PID}') + 1, 'a private path under /tmp by pid, removed before the bind and after the close')
    expect(s[3][1:] == (1, '/var/run/wpa_supplicant/wlan0', 2 + len('/var/run/wpa_supplicant/wlan0') + 1), 'connected to the interface\'s control socket (ctrl_interface of the stock config)')
    expect(s[4][1:] == (SOCK_FD, 'STATUS', 0) and s[5] == ('select', SOCK_FD + 1, True, (1, 500000)) and s[6][1:3] == (SOCK_FD, 255) and s[8][1] == s[1][1], 'the command as it is, a wait of 1.5 s on the socket, a reply read into size - 1 bytes')
    n, text = send('SCAN_RESULTS', size=40)
    expect(n == 39 and len(text) == 39 and text == scan_text([(-50, '[ESS]', b'x')])[:39], 'a reply longer than the buffer is cut, NUL-ended')
    for what, kw in (('socket', 'socket'), ('bind', 'bind'), ('connect', 'connect'), ('send', 'send'), ('select', 'select')):
        m.fail_sock = {kw}
        n, text = send('STATUS')
        names = [x[0] for x in m.sock]
        expect(n == -1 and text == '' and names.count('socket') == 1 and (kw == 'socket' or names[-2:] == ['close', 'unlink']),
               f'{kw} fails: -1, the socket closed and the path removed: {names}')
    m.fail_sock = set()
    supp.alive = False
    n, text = send('STATUS')
    expect(n == -1 and [x[0] for x in m.sock][-2:] == ['close', 'unlink'] and not any(x[0] == 'send' for x in m.sock), 'no supplicant: connect fails at once and nothing is sent')
    supp.alive = True
    ok = lambda c: m.call(PSYMS['wf_ok'], a0=m.put(c.encode()), count=200000)
    expect(ok('SCAN') == 1 and ok('PING') == 0 and ok('NOPE') == 0, 'wf_ok: the reply must be OK (PONG and UNKNOWN COMMAND are not)')
    supp.failed = {'SCAN'}
    expect(ok('SCAN') == 0, 'FAIL is not OK')
    supp.alive = False
    expect(ok('SCAN') == 0, 'no supplicant is not OK')


def asset_tests(ctx):
    expect = ctx.expect
    import paths
    stock = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), RAW, 'ui', 'systemset', 'wifi_page.bin'), 'rb').read())
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    page = pod_pages.WIFI_PAGE
    expect(page in pod_pages.PAGES and page.kind == 'wifi' and page.key == 'm1plus_wifi' and page.title == 'Wi-Fi' and tree.name == page.name, 'the page is registered, titled Wi-Fi')
    expect(by['label_title'].get('tr_text') == 'Wi-Fi' and 'btn_return' in by and 'btn_backtoplayer' in by and 'navigationbar_view' in by, 'the navbar is ours: title, Back, Now Playing')
    # the list is the stock list structure under the Settings pages' numbers
    import pod_settings as ST
    sl, ss, sb = (next(w for w in stock.walk() if w.name == n) for n in ('wifi_listview', 'wifi_scrollview', 'scroll_bar_m'))
    ml, ms, mb = by['wifi_listview'], by['wifi_scrollview'], by['scroll_bar_m']
    geo = lambda w: (w.x, w.y, w.w, w.h)
    expect([geo(w) for w in (ml, ms, mb)] == [geo(w) for w in (sl, ss, sb)] == [(0, 50, 320, 400), (0, 0, 310, 400), (310, 0, 10, 400)], 'list_view, scroll_view and the scroll bar sit where the stock page\'s do')
    expect(ml.get('default_item_height') == str(ST.ROW_H) and mb.get('max') == sb.get('max') and ms.get('yspeed_scale') == ss.get('yspeed_scale'), 'the list properties')
    expect(all(ml.get(k) == sl.get(k) for k in ('style:normal:bg_color', 'style:disable:bg_color', 'style:focused:bg_color', 'style:normal:border_width')), 'the stock list styles')
    expect(ml.type == sl.type and ms.type == ss.type and mb.type == sb.type, 'the same widget types')
    # the children of the scroll view are in display order (the stock layouter stacks them in that order; the payload moves them to the same places)
    names = [c.name for c in ms.children]
    expect(names == ['pod_top', 'wf_row_sw', 'wf_row0', 'wf_hdr_my'] + [f'wf_row{i}' for i in range(1, 1 + WP_MY)] + ['wf_hdr_net'] + [f'wf_row{i}' for i in range(1 + WP_MY, WP_ROWS)] + ['wf_row_other', 'pod_end'],
           f'display order: top spacer, switch row, connected row, My Networks, its rows, Networks, its rows, Other..., bottom spacer: {names[:5]}')
    def box(n): return geo(by[n])
    expect(box('pod_top')[3] == ST.CM and box('pod_end')[3] == ST.END_H and by['pod_top'].get('sensitive') == 'false' and by['pod_end'].get('sensitive') == 'false', 'the spacers are the Settings pages\'')
    ax, ay, aw, ah = ST.accessory('switch')
    lx, lw = ST.label_box('switch', False)
    expect(box('wf_row_sw') == (0, 0, ST.LIST_W, ST.ROW_H) and box('wf_sw_label') == (lx, 0, lw, ST.ROW_H) and box('wf_sw_img') == (ax, ay, aw, ah) == (239, 12, 57, 28), 'the switch row: a 52 px Settings row, label at 24, the switch image at the card\'s right edge')
    expect(WP_CUR == 1 and WP_MY == 16 and WP_OTH == WF_MAX and len([n for n in by if re.fullmatch(r'wf_row\d+', n)]) == WP_ROWS, f'{WP_ROWS} network rows: 1 connected, 16 saved, {WF_MAX} others (patch/wifictl.h WF_MAX)')
    rowbox = lambda k: [box(f'wf_row{k}'), box(f'wf_chk{k}'), box(f'wf_name{k}'), box(f'wf_lock{k}'), box(f'wf_sig{k}'), box(f'wf_info{k}'), box(f'wf_hair{k}')]
    want = [(0, 0, ST.LIST_W, ST.ROW_H), (24, 16, 20, 20), (54, 0, 156, ST.ROW_H), (216, 18, 16, 16), (242, 18, 20, 16), (274, 15, 22, 22), (24, 51, 286, 1)]
    expect(all(rowbox(k) == want for k in range(WP_ROWS)), f'a network row: check (24, 16, 20, 20), name (54, 0, 156, 52), lock (216, 18), signal (242, 18, 20, 16), info (274, 15, 22, 22), hairline from x 24: {rowbox(0)}')
    expect(box('wf_hdr_my') == (0, 0, ST.LIST_W, 40) and box('wf_hdr_net') == (0, 0, ST.LIST_W, 40) and box('wf_hdr_my_t')[:2] == (24, ST.HDR_LABEL_Y) and box('wf_hdr_net_spin')[2:] == (14, 14)
           and box('wf_row_other') == (0, 0, ST.LIST_W, ST.ROW_H) and box('wf_other_label')[0] == 54, 'the headers are 40 px strips with the label at x 24; Other... is a row')
    st = lambda n, k='style': by[n].get(k)
    expect(all(st(f'wf_row{k}') == 'list_item_style' for k in range(WP_ROWS)) and st('wf_row_sw') == st('wf_row_other') == 'list_item_style', 'rows are stock list items')
    expect(all(st(f'wf_name{k}') == 'srlabel_leftwhite21_style' for k in range(WP_ROWS)) and st('wf_sw_label') == st('wf_other_label') == 'srlabel_leftwhite21_style', 'the stock 21 px white labels')
    hdr = by['wf_hdr_my_t']
    expect([hdr.get(f'style:{s}:font_size') for s in ('normal', 'disable', 'focused')] == ['15'] * 3 and [hdr.get(f'style:{s}:text_color') for s in ('normal', 'disable', 'focused')] == ['#AAAAAA'] * 3
           and hdr.get('style:normal:text_align_h') == 'left' and by['wf_hdr_net_t'].get('style:normal:font_size') == '15', 'the headers: small grey, left aligned')
    # the pictures: pieces as the Settings pages, the payload changes them
    expect(all(by[n].get(f'style:{s}:bg_image') == 'pod_cd_single' for n in ('wf_row_sw',) for s in ('normal', 'over', 'focused', 'disable')) and by['wf_row_sw'].get('style:pressed:bg_image') == 'pod_cd_single_down'
           and by['wf_row0'].get('style:normal:bg_image') == 'pod_cd_mid' and by['wf_row_other'].get('style:normal:bg_image') == 'pod_cd_bot' and by['wf_row_other'].get('style:pressed:bg_image') == 'pod_cd_bot_down', 'card pieces and their pressed twins')
    img = lambda n: by[n].get('image')
    expect(img('wf_sw_img') == 'sset_off' and img('wf_chk0') == 'wf_check' and img('wf_lock0') == 'wf_lock' and img('wf_sig0') == 'wf_sig3' and img('wf_info0') == 'wf_info' and img('wf_hdr_net_spin') == 'wf_spin0', 'the images')
    import mod_icons, pod_i18n
    from PIL import Image
    png = lambda n: Image.open(os.path.join(ROOT, 'assets', 'icons', 'png', n + '.png')).convert('RGBA')
    expect(png('wf_sig0').size == png('wf_sig1').size == png('wf_sig2').size == png('wf_sig3').size == (20, 16) and png('wf_lock').size == (16, 16) and png('wf_info').size == (22, 22) and png('wf_check').size == (20, 20)
           and all(png(f'wf_spin{i}').size == (14, 14) for i in range(8)) and all(n in mod_icons.DAILY for n in mod_icons.WIFI_IMAGES), 'the added images have their sizes and are installed')
    opaque = lambda n: [p for p in png(n).getdata() if p[3] > 200]
    lit = lambda p: p[3] > 200 and p[0] > 240
    dim = lambda p: p[3] > 200 and p[0] < 0x70
    lit_n = [sum(lit(p) for p in opaque(f'wf_sig{n}')) for n in range(4)]
    expect(lit_n[0] == 0 and 0 < lit_n[1] < lit_n[2] < lit_n[3] and all(dim(p) for p in opaque('wf_sig0')) and all(any(dim(p) for p in opaque(f'wf_sig{n}')) for n in (1, 2)) and all(png(f'wf_sig{n}').getchannel('A').getbbox() == png('wf_sig3').getchannel('A').getbbox() for n in range(4)),
           f'wf_sig0..3: the Wi-Fi fan, all dim at 0, the lit arcs white and more of them per level, the same canvas at every level: {lit_n}')
    expect([by[n].get('tr_text') for n in ('wf_sw_label', 'wf_hdr_my_t', 'wf_hdr_net_t', 'wf_other_label')] == [pod_i18n.key_for(t) for t in ('Wi-Fi', 'My Networks', 'Networks', 'Other…')], 'the texts, in every language (tools/pod_i18n.py)')
    # touch: the row takes every tap
    rows = [f'wf_row{k}' for k in range(WP_ROWS)] + ['wf_row_sw', 'wf_row_other']
    kids = [w for r in rows for w in by[r].children]
    expect(kids and all(w.get('sensitive') == 'false' for w in kids), 'every child of a row is insensitive: the row takes the tap')
    expect(all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' for n in rows[:WP_ROWS] + ['wf_row_other', 'wf_hdr_my', 'wf_hdr_net']) and by['wf_row_sw'].get('visible') != 'false', 'the network rows, Other... and the headers start hidden and insensitive')
    fade = by['img_nb_fade']
    expect(fade.get('visible') == 'false' and fade.get('sensitive') == 'false', 'the navbar fade starts hidden')
    # the entry point: Settings > Wi-Fi is the stock row, which opens our page first
    wifi_rows = [r for r in pod_pages.SETTINGS_PAGE.rows if r.label == 'Wi-Fi']
    expect(len(wifi_rows) == 1 and wifi_rows[0].action == pod_pages.ACT_STOCK and wifi_rows[0].arg == pod_pages.STOCK_WIFI == 0 and pod_pages.STOCK_PAGES[0][0] == 'systemset/wifi_page',
           'Settings > Wi-Fi is still the stock row (its value shows On / Off), arg 0')
    src = open(os.path.join(ROOT, 'patch', 'm1plus.c')).read()
    expect(re.search(r'row->action == ACT_STOCK\) \{\s*if \(row->arg == 0 /\* STOCK_WIFI \*/ && wifipage_open\(\) == 0\)\s*return RET_OK;[^\n]*\n[\s\S]{0,400}?pod_open_stock\(\s*POD_STOCK\[row->arg\]\.name,\s*POD_STOCK\[row->arg\]\.window\)', src),
           'the row opens our page, and the stock page where it will not open')
    expect(not any(k.startswith('ACT_') and 'WIFI' in k for k in vars(pod_pages)), 'no action id was added (the Wi-Fi row is the stock row) and the Developer page has no Wi-Fi switch')
    # the texts in every language
    import pod_i18n
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    for loc in pod_i18n.LOCALES:
        w = lambda t, px: StbText(font, px).layout(t)[1]
        tx = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        too = [k for k in ('My Networks', 'Networks') if w(tx(k), 15) > 240] + [k for k in ('Other…',) if w(tx(k), 21) > 190]
        expect(not too, f'{loc}: the headers (15 px, room for the spinner after them) and Other... (21 px, 190 px) fit: {too}')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the page

WIN = 0x24500000
WIN_OTHER, WIN_SEC = 0x24510000, 0x24520000
SCAN = [(-45, '[WPA2-PSK-CCMP][ESS]', b'Home'), (-55, '[ESS]', b'Cafe Open'), (-60, '[WPA2-SAE-CCMP][ESS]', b'Safe'), (-62, '[WPA2-PSK+SAE-CCMP][ESS]', b'Mixed'), (-66, '[RSN-OWE-CCMP][ESS]', b'Owe'),
        (-70, '[WPA2-EAP-CCMP][ESS]', b'Corp'), (-78, '[WEP][ESS]', b'Old'), (-50, '[WPA2-PSK-CCMP][ESS]', 'Sam’s iPhone'.encode())]
KNOWN = [(b'Home', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK'), ('priority', '5')])]
ORDER = ['Home', 'Sam’s iPhone', 'Cafe Open', 'Safe', 'Mixed', 'Owe', 'Corp', 'Old']   # the known network in range first, the others by signal
BT_FLAG, WIFI_FLAG = pod.DATA['BT_FLAG'][0], pod.DATA['WIFI_FLAG'][0]
TICK = 250


class PM(SM):
    """The page's machine: every call's record kept, the window's widgets by the asset's names."""
    def __init__(self, supp):
        super().__init__(supp)
        self.hist = []

    def call(self, *a, **k):
        r = super().call(*a, **k)
        self.hist += self.calls
        return r

    def last(self, kind, w, pos=2):
        """The last value a call of this kind gave a widget."""
        for c in reversed(self.hist):
            if c[0] == kind and c[1] == w: return c[pos]
        return None

    def text(self, name): return self.last('widget_set_text_utf8', self.widgets[name], 2)
    def key(self, name): return self.last('widget_set_tr_text', self.widgets[name], 2)
    def image(self, name): return self.last('image_base_set_image', self.widgets[name], 2)
    def visible(self, name): return self.props.get((self.widgets[name], 'visible'), 1)
    def y(self, name): return self.props.get((self.widgets[name], 'y'))
    def toasts(self): return [c[1] for c in self.hist if c[0] == 'toast']
    def asked(self, text): return any(c[0] == 'confirm' and c[1] == text for c in self.hist)
    def idx(self, name): return [g[6] for g in self.rows() if g[0] == name.encode().decode("latin-1")][0]   # the slot (wf_row<slot>) of the row that shows this name
    def cmds(self): return list(self.supp.log)

    def tick(self, n=1):
        for _ in range(n): self.call(self.timers[-1][0], a0=0, count=20000000)

    def tap(self, name, x=None):
        return self.click(name, count=20000000, x=100 if x is None else x)

    def piece(self, name): return self.props.get((self.widgets[name], 'style:normal:bg_image'))
    def rows(self):
        """(name, check or spinner image or None, signal image, lock shown, piece, y, slot) of the network rows that are shown, top to bottom."""
        out = []
        for i in range(WP_ROWS):
            if self.visible(f'wf_row{i}'):
                out.append((self.text(f'wf_name{i}'), self.image(f'wf_chk{i}') if self.visible(f'wf_chk{i}') else None, self.image(f'wf_sig{i}'), self.visible(f'wf_lock{i}'),
                            self.piece(f'wf_row{i}'), self.y(f'wf_row{i}'), i))
        return sorted(out, key=lambda r: r[5])


def page(supp=None, wifi=True, bt=False, copy=True, tick=True, language=None, conf=None):
    supp = supp or Supp(scan=SCAN, known=KNOWN)
    m = PM(supp)
    m.window = WIN
    m.widgets['wifi_scrollview'] = m.alloc(0x200)
    m.widgets['wifiinfo_scrollview'] = m.alloc(0x200)
    m.widgets['wifisec_scrollview'] = m.alloc(0x200)
    m.windows['m1plus_wifiother'], m.windows['m1plus_wifisec'] = WIN_OTHER, WIN_SEC   # (their own handles: the flow has three pages up at once)
    for ui in (UI, UI_INFO, UI_PASS, UI_OTHER, UI_SEC):
        for w in awtk_ui.parse(open(os.path.join(WORK, ui), 'rb').read()).walk():
            if w.name: Machine.widget(m, w.name)
    m.u.mem_write(WIFI_FLAG, bytes([int(wifi)])); m.u.mem_write(BT_FLAG, bytes([int(bt)]))
    m.fs[WF_CONF] = (conf if conf is not None else Supp.HEAD + '\nnetwork={\n\tssid="Home"\n\tpsk="secret123"\n\tkey_mgmt=WPA-PSK\n\tpriority=5\n}\n').encode()
    supp.copy = copy
    if copy: m.fs[WF_COPY] = m.fs[WF_CONF]
    m.confirm_yes = True
    if language: m.set_language(language)
    return m


def opened(m):
    r = m.call(PSYMS['wifipage_open'], count=30000000)
    return struct.unpack('<i', struct.pack('<I', r))[0]


def kclick(m, name):
    """A click on one of the embedded keyboard's keys (kb_k0.., kb_space, kb_go, kb_mode, kb_del ...)."""
    fn, c = m.bound[(m.widgets[name], O['EVT_CLICK'])]
    m.call(fn, a0=c, a1=0, count=40000000)


def close_page(m):
    """The end of the window that is on top (the harness has one window: its destroy handler is the last one bound)."""
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0)


def kdel(m, n=1):
    """n taps on delete (it acts on touch down; the repeat timer it starts ends with the touch and is dropped from the machine's list)."""
    for _ in range(n):
        have = len(m.timers)
        for kind in ('down', 'up'):
            e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e, O['EVT_POINTER_' + kind.upper()])
            fn, c = m.bound[(m.widgets['kb_del'], O['EVT_POINTER_' + kind.upper()])]
            m.call(fn, a0=c, a1=e, count=40000000)
        del m.timers[have:]


def kkeys(m):
    """The labels of the char keys that are shown now."""
    return {m.text(f'kb_k{i}'): i for i in range(26) if m.visible(f'kb_k{i}') and m.text(f'kb_k{i}')}


def ktype(m, text):
    """Type text (lowercase letters, digits, space, - and the like) on the pad, switching between the letter page and the 123 page as needed."""
    for c in text:
        if c == ' ':
            kclick(m, 'kb_space'); continue
        ks = kkeys(m)
        if c not in ks:
            kclick(m, 'kb_mode'); ks = kkeys(m)
        kclick(m, f'kb_k{ks[c]}')


def join_pass(m, name, pw, go=True):
    """Tap a secured network on the list, type the password on its page, press Join."""
    m.tap(f'wf_row{m.idx(name)}')
    ktype(m, pw)
    if go: kclick(m, 'kb_go')


def go_state(m):
    """(sensitive, state) of the action key as the payload last set them."""
    st = [c[2] for c in m.hist if c[0] == 'widget_set_state' and c[1] == m.widgets['kb_go']]
    return m.props.get((m.widgets['kb_go'], 'sensitive')), (st[-1] if st else None)


def layout_tests(ctx):
    expect = ctx.expect
    L = lambda ns: [n.encode().decode('latin-1') for n in ns]
    m = page()
    r = opened(m)
    expect(r == 0 and ('window_open', 'm1plus_wifi') in m.hist, 'the page opens m1plus_wifi')
    expect(m.timers == [(m.timers[0][0], TICK)] and len(m.timers) == 1, 'one timer of 250 ms')
    log = m.cmds()
    expect(log[:3] == ['STATUS', 'GET_CAPABILITY key_mgmt', 'LIST_NETWORKS'] and log[-2:] == ['SCAN_RESULTS', 'SCAN'] and 'GET_NETWORK 0 key_mgmt' in log, f'opening asks the status, what ours can do, the saved networks, then reads the scan and starts one: {log}')
    got = m.rows()
    expect([g[0] for g in got] == L(ORDER), f'the rows: the saved network in range first, the others by signal: {[g[0] for g in got]}')
    expect([g[2] for g in got] == ['wf_sig3'] * 5 + ['wf_sig2'] * 2 + ['wf_sig1'] and [g[3] for g in got] == [1, 1, 0, 1, 1, 0, 1, 1] and [g[1] for g in got] == [None] * 8,
           f'Wi-Fi fan signal glyphs from the four levels, a lock for the networks that need a key (Open and Enhanced Open have none), no check: {[g[2:4] for g in got]}')
    expect([g[4] for g in got] == ['pod_cd_single', 'pod_cd_top'] + ['pod_cd_mid'] * 6 and m.piece('wf_row_sw') == 'pod_cd_single' and m.piece('wf_row_other') == 'pod_cd_bot'
           and m.props[(m.widgets['wf_row_sw'], 'style:pressed:bg_image')] == 'pod_cd_single_down' and m.props[(m.widgets[f'wf_row{got[1][6]}'], 'style:pressed:bg_image')] == 'pod_cd_top_down',
           f'card pieces: the switch row alone, My Networks one row, Networks from top down to Other...: {[g[4] for g in got]}')
    expect([g[5] for g in got] == [102] + [194 + 52 * i for i in range(7)] and m.y('wf_row_sw') == 10 and m.y('wf_hdr_my') == 62 and m.y('wf_hdr_net') == 154 and m.y('wf_row_other') == 194 + 52 * 7,
           f'52 px rows from y 10: switch (10), My Networks header (62), Home (102), Networks header (154), the networks, Other...: {[g[5] for g in got]}')
    expect(m.props[(m.widgets['wifi_scrollview'], 'virtual_h')] == 194 + 52 * 8 + 10, 'the scroll view is as long as its rows and the bottom spacer')
    hair = lambda n: m.visible(n)
    expect(not hair('wf_hair_sw') and not hair(f'wf_hair{got[0][6]}') and all(hair(f'wf_hair{g[6]}') for g in got[1:]), 'hairlines under every row of a card but its last (Other... has none)')
    expect(m.image('wf_sw_img') == 'sset_on' and m.visible('wf_hdr_my') and m.visible('wf_hdr_net') and m.visible('wf_row_other') and not any(m.visible(f'wf_row{i}') for i in range(WP_ROWS) if i not in [g[6] for g in got]),
           'Wi-Fi is on: the switch shows on, the headers and Other... show, the unused network rows are hidden')
    expect(all(m.props.get((m.widgets[f'wf_row{i}'], 'sensitive')) == (1 if i in [g[6] for g in got] else 0) for i in range(WP_ROWS)) and m.props[(m.widgets['wf_row_other'], 'sensitive')] == 1
           and (m.widgets['wf_hdr_my'], 'sensitive') not in m.props and (m.widgets['wf_hdr_net'], 'sensitive') not in m.props, 'hidden rows are insensitive, shown rows sensitive, the headers never touch targets')
    expect(m.visible('wf_hdr_net_spin') and m.image('wf_hdr_net_spin').startswith('wf_spin') and m.props.get((m.widgets['wf_hdr_net_spin'], 'x')) == 24 + 2 + 76 + 8, 'a scan is under way: the header\'s spinner, after the text')
    expect(m.text(f'wf_name{got[1][6]}') == 'Sam’s iPhone'.encode().decode('latin-1'), 'the apostrophe is the UTF-8 character the supplicant printed as \\xe2\\x80\\x99')
    # every row is bound
    bound = {n: m.bound.get((m.widgets[n], O['EVT_CLICK'])) for n in ('wf_row_sw', 'wf_row_other', 'wf_row0', 'wf_row1', f'wf_row{WP_ROWS - 1}', 'btn_return', 'btn_backtoplayer')}
    expect(all(bound.values()) and bound[f'wf_row{WP_ROWS - 1}'][1] == WP_ROWS and bound['wf_row0'][1] == 1 and bound['wf_row_sw'][0] != bound['wf_row_other'][0], 'the rows, Back and Now Playing take a tap')
    # the connected network sits in the switch row's card
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); opened(m)
    got = m.rows()
    expect([g[0] for g in got] == L(ORDER) and got[0][1] == 'wf_check' and got[0][4] == 'pod_cd_bot' and got[0][5] == 62 and got[0][6] == 0 and not any(g[1] for g in got[1:]) and m.piece('wf_row_sw') == 'pod_cd_top' and m.visible('wf_hair_sw')
           and not m.visible('wf_hair0'), f'connected: Home under the switch in the same card with a check: {[(g[0], g[1], g[4], g[5]) for g in got[:2]]}')
    expect(not m.visible('wf_hdr_my') and m.y('wf_hdr_net') == 114 and [g[5] for g in got[1:]] == [154 + 52 * i for i in range(7)] and m.y('wf_row_other') == 154 + 52 * 7, 'no saved network left: no My Networks, the others follow the connected row')
    # joining: the spinner takes the check's place
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'ASSOCIATING', 0, None
    m = page(supp); opened(m)
    f0 = m.rows()[0][1]
    m.tick(1)
    f1 = m.rows()[0][1]
    expect(f0 is not None and f0.startswith('wf_spin') and f1.startswith('wf_spin') and f0 != f1 and m.rows()[0][0] == 'Home', f'Connecting: the row is the connected one and a spinner turns where the check goes: {f0} {f1}')
    supp.state, supp.ip = 'COMPLETED', '192.168.1.20'
    m.tick(4)
    expect(m.rows()[0][1] == 'wf_check', 'with an address: the check')
    # two saved networks (one of them out of range) are one card, the out-of-range one last with no bar lit
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Far', [('key_mgmt', 'NONE')]), (b'Cafe Open', [('key_mgmt', 'NONE')])])
    m = page(supp); opened(m)
    got = m.rows()
    expect([g[0] for g in got][:3] == ['Home', 'Cafe Open', 'Far'] and [g[4] for g in got][:3] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_bot'] and got[2][2] == 'wf_sig0' and got[2][3] == 0 and m.y('wf_hdr_net') == 258
           and [g[5] for g in got][:3] == [102, 154, 206], f'My Networks: saved networks in range, then the ones out of range with all bars dim: {[(g[0], g[2], g[4], g[5]) for g in got[:3]]}')
    # Wi-Fi off: only the switch row
    m = page(wifi=False)
    expect(opened(m) == 0 and m.cmds() == [] and m.image('wf_sw_img') == 'sset_off' and m.visible('wf_row_sw') and m.piece('wf_row_sw') == 'pod_cd_single' and not m.visible('wf_hdr_my') and not m.visible('wf_hdr_net')
           and not m.visible('wf_row_other') and not any(m.visible(f'wf_row{i}') for i in range(WP_ROWS)) and m.props[(m.widgets['wifi_scrollview'], 'virtual_h')] == 72, 'Wi-Fi off: the switch row alone, the supplicant is not asked')
    m.tick(40)
    expect(m.cmds() == [], 'and not asked later')
    # no supplicant yet (just switched on): the page waits and fills in when it answers
    supp = Supp(scan=SCAN, known=KNOWN); supp.alive = False
    m = page(supp)
    expect(opened(m) == 0 and m.rows() == [] and m.visible('wf_hdr_net') and m.visible('wf_row_other') and not m.visible('wf_hdr_my') and m.piece('wf_row_other') == 'pod_cd_single', 'no supplicant: Networks with Other... alone, no network')
    m.tick(8)
    expect(m.rows() == [] and not any(c[0] == 'toast' for c in m.hist), 'it keeps asking, quietly')
    supp.alive = True
    m.tick(4)
    expect(len(m.rows()) == 8 and 'SCAN' in m.cmds() and 'SCAN_RESULTS' in m.cmds(), 'the supplicant answers: the first scan and its results')


def action_tests(ctx):
    expect = ctx.expect
    BIGPASS = 'hunter22hunter'
    ssid_hex = lambda b: b.hex()
    # an open network: no password, saved, selected
    m = page(); opened(m)
    m.supp.log = []
    m.tap(f'wf_row{m.idx("Cafe Open")}')
    log = m.cmds()
    expect(log[:8] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {ssid_hex(b"Cafe Open")}', 'SET_NETWORK 1 key_mgmt NONE', 'SET_NETWORK 1 priority 30000000', 'ENABLE_NETWORK 1', 'SAVE_CONFIG', 'LIST_NETWORKS', 'SELECT_NETWORK 1'],
           f'an open network: added, saved, selected: {log}')
    expect(not any(c[0] == 'dialog' for c in m.sock), 'no dialog for an open network')
    real, ours = m.fs[WF_CONF].decode(), m.fs[WF_OURS].decode()
    expect(real.startswith(Supp.HEAD) and real.count('network={') == 2 and 'ssid="Cafe Open"' in real and 'key_mgmt=NONE' in real and ours == '', 'a stock network is saved in the stock file, the file for the others stays empty')
    expect(m.cmds()[7:10] == ['STATUS', 'LIST_NETWORKS', 'GET_NETWORK 0 key_mgmt'][:3] or 'STATUS' in m.cmds()[7:], 'the page asks the status again')
    m.tick(1)
    rows = m.rows()
    expect([r[0] for r in rows][:2] == ['Cafe Open', 'Home'] and rows[0][1].startswith('wf_spin') and rows[0][6] == 0, f'the chosen network is under the switch with a spinner (joining); it is saved now: {rows[:2]}')
    m.supp.state, m.supp.ip = 'COMPLETED', None
    m.tick(4)
    expect(m.rows()[0][0] == 'Cafe Open' and m.rows()[0][1].startswith('wf_spin'), 'associated, no address yet (DHCP): still joining')
    m.supp.ip = '10.0.0.7'
    m.tick(4)
    expect(m.rows()[0][0] == 'Cafe Open' and m.rows()[0][1] == 'wf_check', 'connected with an address: the check')
    n_log = len(m.supp.log)
    m.confirm_yes = False
    m.tap('wf_row0')
    expect(m.asked('msg_wifidisconnect') and 'DISCONNECT' not in m.cmds()[n_log:], 'the connected network asks Disconnect Now?; No does nothing')
    m.confirm_yes = True
    m.tap('wf_row0')
    expect('DISCONNECT' in m.cmds()[n_log:], 'Yes disconnects')
    m.tick(4)
    expect(m.rows()[0][1] is None and m.rows()[0][6] != 0 and m.piece('wf_row_sw') == 'pod_cd_single', 'and the row is a saved network again, in My Networks')

    # the escape bug: a name with a typographic apostrophe is sent as its bytes (hex), and saved as the supplicant writes it
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', BIGPASS)
    log = m.cmds()
    expect(log[:9] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {"Sam’s iPhone".encode().hex()}', f'SET_NETWORK 1 psk "{BIGPASS}"', 'SET_NETWORK 1 key_mgmt WPA-PSK', 'SET_NETWORK 1 priority 30000000',
                       'ENABLE_NETWORK 1', 'SAVE_CONFIG', 'LIST_NETWORKS', 'SELECT_NETWORK 1'], f'a WPA2 network: the password page, the name as hex, the passphrase quoted: {log}')
    expect(('window_open', 'm1plus_wifipass') in m.hist and not any(c[0] == 'dialog' for c in m.sock) and 'ssid=' + 'Sam’s iPhone'.encode().hex() in m.fs[WF_CONF].decode(), 'our password page, not stock\'s dialog; saved with the exact bytes of the name')
    expect(m.fs[WF_OURS] == b'', 'nothing goes to the file only ours reads')
    # cancelled (Back), and a password that cannot be one: the Join key is dimmed and does nothing
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', 'short')
    expect(m.cmds() == [] and not m.toasts() and go_state(m) == (0, 'disable'), 'fewer than 8 characters: Join stays dimmed and sends nothing')
    ktype(m, '123')
    expect(go_state(m) == (1, 'normal'), 'the eighth character enables it')
    kclick(m, 'kb_k0'); kdel(m, 3)
    expect(go_state(m) == (0, 'disable') and m.cmds() == [], 'and deleting one dims it again')
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Sam’s iPhone")}')
    kclick(m, 'kb_mode'); kclick(m, 'kb_sym')
    kclick(m, f'kb_k{kkeys(m)["€".encode().decode("latin-1")]}')
    kclick(m, 'kb_mode')
    ktype(m, 'x' * 8)
    expect(go_state(m) == (0, 'disable') and not m.toasts(), 'a password with a character WPA cannot take (a euro sign) never enables Join')
    expect(m.cmds() == [], 'nothing was sent')

    # WPA3: only with the newer supplicant, and only in the file the stock one never reads
    m = page(); opened(m); m.supp.log = []
    idx = lambda n: m.idx(n)
    join_pass(m, 'Safe', 'wpa3 password')
    log = m.cmds()
    expect(log[:8] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {b"Safe".hex()}', 'SET_NETWORK 1 sae_password "wpa3 password"', 'SET_NETWORK 1 key_mgmt SAE', 'SET_NETWORK 1 ieee80211w 2', 'SET_NETWORK 1 priority 30000000',
                       'ENABLE_NETWORK 1', 'SAVE_CONFIG'], f'WPA3: SAE with PMF required: {log}')
    real, ours = m.fs[WF_CONF].decode(), m.fs[WF_OURS].decode()
    expect('Safe' not in real and 'SAE' not in real and real.count('network={') == 1 and 'ssid="Safe"' in ours and 'sae_password="wpa3 password"' in ours and 'key_mgmt=SAE' in ours and ours.endswith('}\n\n'),
           f'the stock file never holds it: stock {real!r} ours {ours!r}')
    m = page(Supp(ours=False, scan=SCAN, known=KNOWN)); opened(m); m.supp.log = []
    m.tap(f'wf_row{idx("Safe")}')
    expect(m.cmds() == [] and m.toasts() == ["This network isn't supported"] and not any(c[0] == 'dialog' for c in m.sock) and ('window_open', 'm1plus_wifipass') not in m.hist, 'WPA3 with stock\'s supplicant: a word, no page, nothing sent')
    # WPA2/WPA3 transition
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Mixed', 'mixed-pass-1')
    log = m.cmds()
    expect(log[:6] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {b"Mixed".hex()}', 'SET_NETWORK 1 psk "mixed-pass-1"', 'SET_NETWORK 1 key_mgmt WPA-PSK SAE', 'SET_NETWORK 1 ieee80211w 1', 'SET_NETWORK 1 priority 30000000'],
           f'transition: WPA-PSK and SAE, PMF optional: {log}')
    expect('Mixed' not in m.fs[WF_CONF].decode() and 'ssid="Mixed"' in m.fs[WF_OURS].decode(), 'saved in ours')
    m = page(Supp(ours=False, scan=SCAN, known=KNOWN)); opened(m); m.supp.log = []
    join_pass(m, 'Mixed', 'mixed-pass-1')
    log = m.cmds()
    expect(log[:5] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {b"Mixed".hex()}', 'SET_NETWORK 1 psk "mixed-pass-1"', 'SET_NETWORK 1 key_mgmt WPA-PSK', 'SET_NETWORK 1 priority 30000000'] and 'ieee80211w' not in ' '.join(log),
           f'transition with stock\'s supplicant: plain WPA2: {log}')
    expect('ssid="Mixed"' in m.fs[WF_CONF].decode() and m.fs[WF_OURS] == b'', 'and it stays in the stock file')
    # Enhanced Open
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{idx("Owe")}')
    log = m.cmds()
    expect(log[:6] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {b"Owe".hex()}', 'SET_NETWORK 1 key_mgmt OWE', 'SET_NETWORK 1 ieee80211w 2', 'SET_NETWORK 1 priority 30000000', 'ENABLE_NETWORK 1']
           and not any(c[0] == 'dialog' for c in m.sock) and 'key_mgmt=OWE' in m.fs[WF_OURS].decode(), f'Enhanced Open: OWE, PMF required, no password: {log}')
    m = page(Supp(ours=False, scan=SCAN, known=KNOWN)); opened(m); m.supp.log = []
    m.tap(f'wf_row{idx("Owe")}')
    expect(m.cmds() == [] and m.toasts() == ["This network isn't supported"], 'Enhanced Open with stock\'s supplicant: a word')
    # enterprise and WEP: a word, nothing else (phase 2b / not built in)
    for ours in (True, False):
        m = page(Supp(ours=ours, scan=SCAN, known=KNOWN)); opened(m); m.supp.log = []
        m.tap(f'wf_row{idx("Corp")}'); m.tap(f'wf_row{idx("Old")}')
        expect(m.cmds() == [] and m.toasts() == ["Enterprise isn't supported yet", "WEP isn't supported"] and not any(c[0] == 'dialog' for c in m.sock),
               f'enterprise and WEP are shown with their labels but not joined ({"newer" if ours else "stock"} supplicant): {m.toasts()}')
    # a refused step: the half-made network is removed again
    m = page(); opened(m); m.supp.log = []
    m.supp.refuse = {'ieee80211w'}
    m.tap(f'wf_row{idx("Owe")}')
    log = m.cmds()
    expect('REMOVE_NETWORK 1' in log and 'SELECT_NETWORK 1' not in log and 'SAVE_CONFIG' not in log and m.toasts() == ["Couldn't connect"] and 1 not in m.supp.nets, f'the supplicant refuses a step: removed, not saved, told: {log}')
    m.supp.refuse = set(); m.supp.failed = {'ADD_NETWORK'}; m.supp.log = []
    m.tap(f'wf_row{idx("Cafe Open")}')
    expect(m.cmds()[:1] == ['ADD_NETWORK'] and not any(c.startswith('SET_NETWORK') for c in m.cmds()) and m.toasts()[-1] == "Couldn't connect", 'no network number: nothing else is sent')

    # a saved network: made preferred, saved, selected
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Home")}')
    expect(m.cmds()[:5] == ['SET_NETWORK 0 priority 30000000', 'ENABLE_NETWORK 0', 'SAVE_CONFIG', 'LIST_NETWORKS', 'SELECT_NETWORK 0'] and not any(c[0] == 'dialog' for c in m.sock), f'a saved network joins without a dialog: {m.cmds()[:5]}')
    expect('priority=30000000' in m.fs[WF_CONF].decode(), 'its new priority is saved before it is selected')
    # a wrong password: the supplicant disables the network for a while; the page says so once and lets the others be tried again
    m.supp.state, m.supp.temp = 'DISCONNECTED', {0}
    m.supp.log = []
    m.tick(4)
    expect(m.toasts() == ["Couldn't connect"] and 'ENABLE_NETWORK all' not in m.cmds(), 'a network the supplicant disabled: a word (the others were enabled again when it was selected)')
    m.tick(8)
    expect(m.toasts() == ["Couldn't connect"], 'told once')
    # a saved network that never connects: after 20 s the page stops showing it as asked for
    m = page(); opened(m)
    m.tap(f'wf_row{m.idx("Home")}')
    m.tick(4)
    expect(m.rows()[0][1].startswith('wf_spin'), 'selected: the spinner')
    m.supp.state = 'DISCONNECTED'
    m.tick(84)
    expect(m.toasts() == ["Couldn't connect"] and m.rows()[0][1] is None and m.rows()[0][6] != 0, 'nothing happened for 20 s: the spinner stops and the row is a saved network again')

    # a tap left of x 264 joins; the info glyph's side opens the info page (info_tests)
    m = page(); opened(m); m.supp.log = []
    home = m.idx('Home')
    m.tap(f'wf_row{home}', x=263)
    expect('REMOVE_NETWORK 0' not in m.cmds() and 'SELECT_NETWORK 0' in m.cmds() and ('window_open', 'm1plus_wifiinfo') not in m.hist, 'a tap left of x 264 on a saved network joins it')
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Home")}', x=264)
    expect(('window_open', 'm1plus_wifiinfo') in m.hist and m.cmds() == [] and not m.asked('msg_wificancelsave'), 'x 264 and right opens the info page and sends nothing')
    # a saved network out of range is listed in My Networks after the ones in range, all bars dim, and can be forgotten
    sc = [r for r in SCAN if r[2] != b'Home']
    m = page(Supp(scan=sc, known=KNOWN + [(b'Far', [('key_mgmt', 'NONE')])])); opened(m)
    rows = m.rows()
    expect([r[0] for r in rows][:2] == ['Home', 'Far'] and rows[1][2] == 'wf_sig0' and rows[1][3] == 0 and rows[1][4] == 'pod_cd_bot', f'a saved network that was not found: last of My Networks, no bar lit, its own security: {rows[:2]}')


def pass_tests(ctx):
    """The password page (patch/wifipage.c wk_*, tools/pod_ui.py build_wifipass_page): the asset, the page on a scripted supplicant (open, typing, the Join key, the eye, joining, a wrong password, the files)."""
    expect = ctx.expect
    import pod_i18n, mod_icons
    from awtk_text import Ttf, StbText
    import pod_keyboard as PK
    enc = lambda t: t.encode().decode('latin-1')
    PW = 'hunter22hunter'
    # the asset
    tree = awtk_ui.parse(open(os.path.join(WORK, UI_PASS), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    page_ = pod_pages.WIFIPASS_PAGE
    expect(page_ in pod_pages.PAGES and page_.kind == 'wifipass' and page_.key == 'm1plus_wifipass' and page_.title == 'Enter Password' and tree.name == page_.name and by['label_title'].get('tr_text') == pod_i18n.key_for('Enter Password'),
           'the page is registered, titled Enter Password')
    need = ('btn_return', 'btn_backtoplayer', 'wk_line', 'wk_card', 'wk_label', 'wk_eye', 'wk_err', 'kb_field', 'kb_hint', 'kb_text', 'kb_caret', 'kb_clear', 'kb_pad', 'kb_strip', 'kb_stem', 'kb_pop', 'kb_pop_l', 'kb_cands', 'kb_chl', 'kb_go', 'kb_lang')
    expect(all(n in by for n in need) and all(f'kb_k{i}' in by for i in range(26)) and all(f'kb_c{i}' in by for i in range(12)), f'every widget the page and the keyboard look up is there: {[n for n in need if n not in by]}')
    box = lambda n: (by[n].x, by[n].y, by[n].w, by[n].h)
    expect(box('wk_card') == (10, 100, 300, 52) and by['wk_card'].get('style:normal:bg_color') == '#1C1C1C' and box('wk_label')[0] == 24 and box('kb_field')[:2] == (144, 100) and box('wk_eye')[0] == 264 and by['wk_card'].get('sensitive') == 'false',
           'one Settings card (10, 100, 300 x 52, #1C1C1C): the label at x 24, the field at x 144, the eye at the right')
    ends = {n: by[n].y + by[n].h for n in ('wk_line', 'wk_card', 'kb_field', 'wk_eye', 'wk_err')}
    expect(all(v <= PK.STRIP_Y for v in ends.values()) and by['kb_strip'].y == PK.STRIP_Y, f'nothing but the pad reaches the candidate strip (y {PK.STRIP_Y}): {ends}')
    f = by['kb_field']
    expect(by['kb_text'].x == 0 and by['kb_caret'].x == 0 and by['kb_caret'].y == 15 and by['kb_text'].w == f.w == 120 and by['kb_caret'].h == 22 and f.x + f.w <= by['wk_eye'].x, 'the field\'s text starts at its left edge (the payload is told 0, 118 and 15); it ends before the eye')
    expect(by['wk_eye'].get('style:normal:icon') == 'wf_eyeoff' and by['wk_eye'].get('enable') == 'true' and by['wk_err'].get('visible') == 'false' and by['wk_err'].get('sensitive') == 'false' and by['wk_err'].get('tr_text') == pod_i18n.key_for('Incorrect password'),
           'the eye starts as eye-off (the password is hidden); the error line starts hidden')
    expect(by['kb_go'].get('style:disable:text_color') == PK.KB_DIM and by['kb_go'].get('style:normal:text_color') == PK.KB_INK and by['kb_go'].get('tr_text') == pod_i18n.key_for('Search'), 'the action key has a dim style for the disable state')
    names = [c.name for c in tree.children]
    expect(names.index('kb_pad') > names.index('kb_field') and names[-4:] == ['kb_pad', 'kb_strip', 'kb_stem', 'kb_pop'], 'the pad, strip and pop-up end the page, as on the keyboard page')
    cols = [v for w in tree.walk() for k, v in w.props if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6,8}', v) and 'color' in k]
    neutral = lambda c: (lambda r, g, b: max(r, g, b) - min(r, g, b) <= 12)(*(int(c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)))
    expect(all(neutral(c) for c in cols), 'no accent colour')
    from PIL import Image
    png = lambda n: Image.open(os.path.join(ROOT, 'assets', 'icons', 'png', n + '.png')).convert('RGBA')
    expect(png('wf_eye').size == png('wf_eyeoff').size == (22, 22) and 'wf_eye' in mod_icons.DAILY and 'wf_eyeoff' in mod_icons.DAILY and png('wf_eye').tobytes() != png('wf_eyeoff').tobytes(), 'the eye and eye-off glyphs (22 px, grey) are installed')
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    for loc in pod_i18n.LOCALES:
        tx = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        w = lambda t, px: StbText(font, px).layout(t)[1]
        bad = [k for k, px, room in (('Password', 21, 118), ('Incorrect password', 18, 272), ('Join', 15, PK.KB_MODE_W - 8), ('Enter Password', 20, 200)) if w(tx(k), px) > room]
        expect(not bad and '%s' in tx('Enter the password for “%s”'), f'{loc}: Password, Incorrect password, Join and the title fit their rooms ({bad})')

    # the page opens from the list, over a scripted supplicant; nothing is sent until Join
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Sam’s iPhone")}')
    expect(('window_open', 'm1plus_wifipass') in m.hist and m.cmds() == [] and not any(c[0] == 'dialog' for c in m.sock), 'a secured network that is not saved opens the password page and sends nothing')
    expect(m.text('wk_line') == enc('Enter the password for “Sam’s iPhone”') and m.visible('wk_err') == 0 and m.key('kb_go') == 'Join' and go_state(m) == (0, 'disable'), f'the line names the network in UTF-8, no error, the action key reads Join and is dimmed: {m.text("wk_line")!r}')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] == PSYMS['pod_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])][0] == PSYMS['pod_on_player'], 'Back (cancel) and Now Playing are the stock ones')
    expect(kkeys(m).get('q') == 0 and m.visible('kb_shift') and not m.visible('kb_lang') if 'kb_lang' in m.widgets else True, 'the pad starts on the lowercase page')
    ktype(m, 'ab c')
    expect(m.text('kb_text') == enc('••••') and go_state(m) == (0, 'disable'), 'one dot a character, the space too; four characters: Join still dimmed')
    kclick(m, 'kb_k0')   # (the first key of the current page)
    # the eye: show the text, hide it again
    m = page(); opened(m)
    m.tap(f'wf_row{m.idx("Sam’s iPhone")}')
    ktype(m, 'abc')
    m.tap('wk_eye')
    expect(m.text('kb_text') == 'abc' and all(m.props.get((m.widgets['wk_eye'], f'style:{st}:icon')) == 'wf_eye' for st in ('normal', 'over', 'pressed')), 'the eye open: the text is shown, the button\'s glyph is the open eye')
    ktype(m, 'd')
    expect(m.text('kb_text') == 'abcd', 'typing while it is shown')
    m.tap('wk_eye')
    expect(m.text('kb_text') == enc('••••') and all(m.props.get((m.widgets['wk_eye'], f'style:{st}:icon')) == 'wf_eyeoff' for st in ('normal', 'over', 'pressed')), 'and hidden again')
    # nothing but dots was ever put on a label while the eye was closed
    m = page(); opened(m)
    join_pass(m, 'Sam’s iPhone', PW, go=False)
    expect(not any(PW in repr(c) for c in m.hist), 'the typed password is on no widget while it is hidden')
    # the Join key: dimmed until the password can be one; a WPA3 password may be shorter
    m = page(); opened(m)
    join_pass(m, 'Safe', 'a', go=False)
    expect(go_state(m) == (1, 'normal'), 'WPA3: one character is a password (1..127)')
    kclick(m, 'kb_go')
    expect('SET_NETWORK 1 sae_password "a"' in m.cmds(), 'and Join sends it as sae_password')
    # Join: the commands, the page goes back, the list shows it joining
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', PW, go=False)
    expect(go_state(m) == (1, 'normal') and m.cmds() == [], 'a good password enables Join; nothing is sent until it is pressed')
    m.hist = []
    kclick(m, 'kb_go')
    expect(m.cmds()[:9] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {"Sam’s iPhone".encode().hex()}', f'SET_NETWORK 1 psk "{PW}"', 'SET_NETWORK 1 key_mgmt WPA-PSK', 'SET_NETWORK 1 priority 30000000', 'ENABLE_NETWORK 1', 'SAVE_CONFIG', 'LIST_NETWORKS', 'SELECT_NETWORK 1']
           and ('navigator_back',) in m.hist, f'Join sends the join and closes the page: {m.cmds()[:8]}')
    close_page(m)   # the page's end
    m.tick(1)
    rows = m.rows()
    expect(rows[0][0] == enc('Sam’s iPhone') and rows[0][1].startswith('wf_spin'), 'the list shows the network joining (the spinner), as for any join')
    m.supp.state, m.supp.ip = 'COMPLETED', '192.168.1.9'
    m.hist = []
    m.tick(4)
    expect(m.rows()[0][1] == 'wf_check' and ('window_open', 'm1plus_wifipass') not in m.hist and not m.toasts(), 'connected: the check, no page, no word')
    # the password is only in the supplicant's configuration
    others = {k: v for k, v in m.fs.items() if k not in (WF_COPY, WF_CONF, WF_OURS)}
    expect(not any(PW.encode() in v for v in others.values()) and PW in m.fs[WF_CONF].decode() and not any(PW in repr(c) for c in m.hist), 'the password is written to the supplicant\'s configuration and nowhere else (no other file, no widget, no call)')
    kb = bytes(m.u.mem_read(PSYMS['kb'], 0x1400))
    expect(PW.encode() not in kb, 'the keyboard\'s state was wiped with the page')
    # a wrong password: the network is removed, the page comes back with an empty field and the line
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', PW)
    close_page(m); m.tick(1)
    m.supp.state, m.supp.temp = 'DISCONNECTED', {1}
    m.hist = []; m.supp.log = []
    m.tick(4)
    expect(m.cmds()[:3] == ['STATUS', 'LIST_NETWORKS', 'REMOVE_NETWORK 1'] or ('REMOVE_NETWORK 1' in m.cmds() and 'SAVE_CONFIG' in m.cmds()), f'the supplicant disabled it (TEMP-DISABLED): the network is removed and the file saved: {m.cmds()}')
    expect(1 not in m.supp.nets and 'Sam' not in m.fs[WF_CONF].decode() and 'Sam' not in m.fs[WF_COPY].decode() and PW.encode() not in m.fs[WF_CONF], 'nothing wrong stays saved: the network and its password are gone from the files')
    expect(('window_open', 'm1plus_wifipass') in m.hist and not m.toasts() and m.visible('wk_err') == 1 and m.text('kb_text') in (None, '') and go_state(m) == (0, 'disable')
           and m.text('wk_line') == enc('Enter the password for “Sam’s iPhone”'), 'the password page is back: empty field, "Incorrect password" under the card, Join dimmed, no toast')
    ktype(m, 'x')
    expect(m.visible('wk_err') == 0, 'the line goes at the first key')
    # a second try that works
    ktype(m, PW[1:])
    m.hist = []; m.supp.log = []
    m.supp.temp = set()
    kclick(m, 'kb_go')
    expect('ADD_NETWORK' in m.cmds() and 'SELECT_NETWORK 2' in m.cmds() and 'SET_NETWORK 2 psk "x' + PW[1:] + '"' in m.cmds(), f'the second attempt joins as a new network: {m.cmds()[:4]}')
    close_page(m)
    m.supp.state, m.supp.ip = 'COMPLETED', '10.0.0.2'
    m.hist = []
    m.tick(4)
    expect(('window_open', 'm1plus_wifipass') not in m.hist and 'REMOVE_NETWORK 2' not in m.cmds() and m.rows()[0][1] == 'wf_check', 'and when it connects the page is not asked for again')
    # a network that never answers: after 20 s the same
    m = page(); opened(m)
    join_pass(m, 'Sam’s iPhone', PW)
    close_page(m); m.tick(2)
    m.hist = []; m.supp.log = []
    m.tick(84)
    expect('REMOVE_NETWORK 1' in m.cmds() and ('window_open', 'm1plus_wifipass') in m.hist and m.visible('wk_err') == 1 and not m.toasts(), 'no answer for 20 s: removed, asked again with the line')
    # a saved network that fails keeps today\'s word and stays saved
    m = page(); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Home")}')
    m.supp.state, m.supp.temp = 'DISCONNECTED', {0}
    m.tick(4)
    expect(m.toasts() == ["Couldn't connect"] and 'REMOVE_NETWORK 0' not in m.cmds() and ('window_open', 'm1plus_wifipass') not in m.hist, 'a saved network: the word, it is kept, no page')
    # Back: nothing is sent
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', PW, go=False)
    close_page(m)
    m.tick(4)
    expect(m.cmds()[:1] == ['STATUS'] and 'ADD_NETWORK' not in m.cmds() and not m.toasts(), 'Back: no join, no word')
    expect(PW.encode() not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)), 'and the typed text is gone')
    # Wi-Fi turned off under the page: back
    m = page(); opened(m)
    m.tap(f'wf_row{m.idx("Sam’s iPhone")}')
    m.hist = []
    m.u.mem_write(WIFI_FLAG, bytes([0]))
    m.tick(1)
    expect(('navigator_back',) in m.hist, 'Wi-Fi off under the password page: back')
    # a page that cannot be made: back out, nothing sent
    for gone in ('wk_eye', 'wk_err', 'kb_clear'):
        m = page(); opened(m); m.supp.log = []
        del m.widgets[gone]
        i = m.idx('Sam’s iPhone')
        m.hist = []
        m.tap(f'wf_row{i}')
        expect(('navigator_back',) in m.hist and m.cmds() == [], f'without {gone}: the page backs out and nothing is sent')
    m = page(); opened(m); m.windows['m1plus_wifipass'] = 0; m.supp.log = []
    m.tap(f'wf_row{m.idx("Sam’s iPhone")}')
    expect(m.cmds() == [] and not m.toasts(), 'a window that will not open: nothing happens')


def close_win(m, name):
    """The end of one of the flow's windows (each has its own handle in the harness)."""
    w = m.windows.get(name, m.window)
    fn, c = m.bound[(w, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0)


def fg_win(m, name):
    fn, c = m.bound[(m.windows[name], O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, a1=0, count=40000000)


def backs(m): return sum(1 for c in m.hist if c[0] == 'navigator_back')


def other_tests(ctx):
    """The Join Wi-Fi Network page and its Security picker (patch/wifipage.c wo_*, ws_*; tools/pod_ui.py build_wifiother_page, build_wifisec_page): the assets, the one keyboard serving Name and Password in turn, the picker, the join, the failures and the end of the pages."""
    expect = ctx.expect
    import pod_i18n, pod_settings as ST
    import pod_keyboard as PK
    from awtk_text import Ttf, StbText
    def isdots(t, n):
        """t is n dots, or a run of dots cut with an ellipsis to the field's room (the harness measures a dot wide)."""
        t = (t or '').encode('latin-1').decode('utf-8')
        return (t == '•' * n) if '…' not in t else (set(t) <= {'•', '…'} and 0 < t.count('•') <= n)
    # the assets
    tree = awtk_ui.parse(open(os.path.join(WORK, UI_OTHER), 'rb').read())
    by = {w.name: w for w in tree.walk() if w.name}
    pg = pod_pages.WIFIOTHER_PAGE
    expect(pg in pod_pages.PAGES and pg.kind == 'wifiother' and pg.key == 'm1plus_wifiother' and pg.title == 'Join Wi-Fi Network' and tree.name == pg.name and by['label_title'].get('tr_text') == pod_i18n.key_for('Join Wi-Fi Network'),
           'the page is registered, titled Join Wi-Fi Network')
    need = ('btn_return', 'btn_backtoplayer', 'wo_card0', 'wo_card1a', 'wo_card1b', 'wo_name_l', 'wo_sec_l', 'wo_pass_l', 'wo_sec_v', 'wo_chev', 'wo_hair', 'wo_name_v', 'wo_name_h', 'wo_pass_v', 'wo_hit_name', 'wo_hit_sec', 'wo_hit_pass',
            'kb_field', 'kb_hint', 'kb_text', 'kb_caret', 'kb_clear', 'wo_eye', 'wo_err', 'kb_pad', 'kb_strip', 'kb_stem', 'kb_pop', 'kb_go')
    expect(all(n in by for n in need) and all(f'kb_k{i}' in by for i in range(26)) and not [n for n in by if n.startswith('wk_')], f'the page\'s and the keyboard\'s widgets are there, none of the password page\'s: {[n for n in need if n not in by]}')
    box = lambda n: (by[n].x, by[n].y, by[n].w, by[n].h)
    expect(box('wo_card0') == (10, 56, 300, 48) and box('wo_card1b') == (10, 116, 300, 96) and box('wo_card1a') == (10, 116, 300, 48) and by['wo_card1a'].get('visible') == 'false' and by['wo_card1b'].get('visible') is None
           and all(by[n].get('style:normal:bg_color') == ST.CARD_RGB for n in ('wo_card0', 'wo_card1a', 'wo_card1b')) and all(by[n].get('sensitive') == 'false' for n in ('wo_card0', 'wo_card1a', 'wo_card1b')),
           'two Settings cards: Name alone (y 56), Security and Password (y 116, 96 high; the one-row twin for None, hidden); no grey line')
    expect(box('wo_name_l')[:2] == (24, 56) and box('wo_sec_l')[:2] == (24, 116) and box('wo_pass_l')[:2] == (24, 164) and box('wo_hair') == (24, 163, 286, 1) and box('wo_name_l')[3] == box('wo_sec_l')[3] == box('wo_pass_l')[3] == 48,
           'three 48 px rows, labels at x 24, the hairline between Security and Password from the label to the card\'s edge')
    f = by['kb_field']
    expect((f.x, f.y, f.w, f.h) == (100, 56, 196, 48) and by['kb_text'].w == by['kb_hint'].w == f.w and by['kb_clear'].x == 160 and by['kb_caret'].y == 13 and by['kb_caret'].h == 22 and f.get('sensitive') == 'false'
           and f.get('style:normal:bg_color') == '#00000000', 'the keyboard\'s field starts on the Name row (x 100 to the card\'s ink edge, the clear button at its right, text room 156), the caret centred in the row, no fill (it moves over the card)')
    expect(box('wo_eye') == (264, 164, 46, 48) and box('wo_hit_pass') == (10, 164, 254, 48) and box('wo_hit_name') == (10, 56, 300, 48) and box('wo_hit_sec') == (10, 116, 300, 48)
           and all(by[n].get('enable') == 'true' for n in ('wo_hit_name', 'wo_hit_sec', 'wo_hit_pass', 'wo_eye')) and by['wo_eye'].get('style:normal:icon') == 'wf_eyeoff', 'the rows take the taps (the password row not under the eye); the eye starts as eye-off')
    expect(box('wo_name_v') == (100, 56, 156, 48) and box('wo_name_h') == (100, 56, 156, 48) and box('wo_pass_v') == (144, 164, 118, 48) and by['wo_name_h'].get('tr_text') == pod_i18n.key_for('Network Name')
           and by['wo_name_h'].get('style:normal:text_color') == PK.KB_GREY and by['wo_name_v'].get('style:normal:text_color') == PK.KB_INK
           and all(by[n].get('visible') == 'false' and by[n].get('sensitive') == 'false' for n in ('wo_name_v', 'wo_name_h', 'wo_pass_v', 'wo_err')), 'the static labels sit where the field text does (the grey placeholder, the name, the dots) and start hidden and insensitive')
    ends = {n: by[n].y + by[n].h for n in ('wo_card0', 'wo_card1b', 'kb_field', 'wo_eye', 'wo_err', 'wo_hit_pass')}
    expect(all(v <= PK.STRIP_Y for v in ends.values()) and ends['wo_err'] == 232 and by['kb_strip'].y == PK.STRIP_Y, f'Name, Security, Password and the error line all end above the candidate strip (y {PK.STRIP_Y}): {ends}')
    sx, sw = ST.value_box()
    expect(by['wo_sec_v'].get('style:normal:text_align_h') == 'right' and by['wo_sec_v'].x + by['wo_sec_v'].w == sx + sw and by['wo_chev'].get('image') == 'pod_chev' and by['wo_chev'].x == ST.accessory('chevron')[0],
           'the Security value is right aligned in the Settings value box, the chevron the Settings one')
    names = [c.name for c in tree.children]
    expect(names.index('kb_field') > max(names.index(n) for n in ('wo_hit_name', 'wo_hit_sec', 'wo_hit_pass')) and names[-4:] == ['kb_pad', 'kb_strip', 'kb_stem', 'kb_pop'], 'the field is over the row buttons (its clear button takes its own taps); the pad ends the page')
    cols = [v for w in tree.walk() for k, v in w.props if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6,8}', v) and 'color' in k]
    neutral = lambda c: (lambda r, g, b: max(r, g, b) - min(r, g, b) <= 12)(*(int(c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)))
    expect(all(neutral(c) for c in cols), 'no accent colour')
    st = awtk_ui.parse(open(os.path.join(WORK, UI_SEC), 'rb').read())
    sb = {w.name: w for w in st.walk() if w.name}
    pg = pod_pages.WIFISEC_PAGE
    expect(pg in pod_pages.PAGES and pg.kind == 'wifisec' and pg.key == 'm1plus_wifisec' and pg.title == 'Security' and st.name == pg.name and sb['label_title'].get('tr_text') == pod_i18n.key_for('Security'),
           'the Security picker is registered, titled Security')
    names = [c.name for c in sb['wifisec_scrollview'].children]
    expect(names == ['pod_top', 'ws_row0', 'ws_row1', 'ws_row2', 'pod_end'] and [sb[f'ws_label{k}'].get('tr_text') for k in range(3)] == [pod_i18n.key_for(t) for t in ('None', 'WPA2/WPA3', 'WPA3')], f'display order: top spacer, None, WPA2/WPA3, WPA3, bottom spacer: {names}')
    expect([sb[f'ws_row{k}'].get('style:normal:bg_image') for k in range(3)] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_bot'] and [sb[f'ws_row{k}'].get('style:pressed:bg_image') for k in range(3)] == ['pod_cd_top_down', 'pod_cd_mid_down', 'pod_cd_bot_down']
           and all((sb[f'ws_row{k}'].x, sb[f'ws_row{k}'].h) == (0, ST.ROW_H) for k in range(3)), 'one card of three 52 px rows with the Settings pieces')
    ax = ST.accessory('check')
    expect([sb[f'ws_check{k}'].get('visible') for k in range(3)] == ['false', None, 'false'] and (sb['ws_check1'].x, sb['ws_check1'].y, sb['ws_check1'].w, sb['ws_check1'].h) == ax and sb['ws_check1'].get('image') == 'pod_check'
           and sb['ws_hair0'].get('visible') is None and 'ws_hair2' not in sb and all(sb[f'ws_label{k}'].get('sensitive') == 'false' for k in range(3)), 'the picker pages\' check (neutral pod_check) on WPA2/WPA3 as the asset starts (the payload puts it on the page\'s choice); hairlines between rows; the labels are insensitive: the row takes the tap')
    cols = [v for w in st.walk() for k, v in w.props if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6,8}', v) and 'color' in k]
    expect(all(neutral(c) for c in cols), 'the Security page has no accent colour')
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    for loc in pod_i18n.LOCALES:
        tx = lambda k: pod_i18n.TEXT[k][pod_i18n.table_for(loc)]
        w = lambda t, px: StbText(font, px).layout(t)[1]
        bad = [k for k, px, room in (('Name', 21, 76), ('Security', 21, 150), ('Password', 21, 118), ('Join Wi-Fi Network', 20, by['label_title'].w), ('Network Name', 18, 156), ('Next', 15, PK.KB_MODE_W - 8), ('Join', 15, PK.KB_MODE_W - 8),
                                      ('None', 18, ST.VALUE_MAX), ('WPA2/WPA3', 18, ST.VALUE_MAX), ('Incorrect password', 16, by['wo_err'].w), ('None', 21, 200), ('Security', 20, 200)) if w(tx(k), px) > room]
        expect(not bad, f'{loc}: the title, the labels, the placeholder, the values, the action keys and the error line fit their rooms ({bad})')

    SSID = b'Hidden net'
    fld = lambda m: (m.props.get((m.widgets['kb_field'], 'x')), m.props.get((m.widgets['kb_field'], 'y')))
    shown_ = lambda m, n: (m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1))
    eye = lambda m: [m.props.get((m.widgets['wo_eye'], f'style:{s}:icon')) for s in ('normal', 'over', 'pressed')]

    def start(m=None, name='Hidden net', typed=True):
        m = m or page(); opened(m); m.supp.log = []; m.hist = []
        m.tap('wf_row_other')
        if typed:
            kclick(m, f'kb_k{kkeys(m)[name[0]]}')
            ktype(m, name[1:])
        return m

    def to_picker(m, row):
        """Security row, then a row of the picker; the picker's window ends the way its Back does."""
        m.tap('wo_hit_sec')
        m.tap(f'ws_row{row}')
        close_win(m, 'm1plus_wifisec')

    # Other... opens our page; no stock dialog, nothing sent
    m = start(typed=False)
    expect(('window_open', 'm1plus_wifiother') in m.hist and not any(c[0] == 'dialog' for c in m.sock) and m.cmds() == [] and m.key('kb_go') == 'Next' and go_state(m) == (0, 'disable'),
           'Other... opens the page: no stock dialog, nothing sent, the action key reads Next and is dimmed')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] == PSYMS['pod_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])][0] == PSYMS['pod_on_player'], 'Back (cancel) and Now Playing are the stock ones')
    expect(fld(m) == (100, 56) and m.text('kb_hint') == 'Network Name' and m.text('wo_sec_v') == 'WPA2/WPA3' and m.visible('wo_card1b') == 1 and m.visible('wo_card1a') == 0 and m.visible('wo_hair') == 1 and m.visible('wo_pass_l') == 1
           and shown_(m, 'wo_eye') == (1, 1) and shown_(m, 'wo_hit_pass') == (1, 1) and m.visible('wo_err') == 0 and m.visible('wo_name_h') == 0 and m.visible('wo_name_v') == 0 and m.text('wo_pass_v') in (None, ''),
           'WPA2/WPA3 by default: the field on the Name row with its placeholder, Security and Password in the tall card, nothing else on show')
    expect('Q' in kkeys(m) and not m.visible('kb_lang') if 'kb_lang' in m.widgets else True, 'an empty Name starts on the capital page')
    # the name: Next works from the first character to 32 bytes
    kclick(m, f'kb_k{kkeys(m)["H"]}')
    expect(go_state(m) == (1, 'normal') and m.text('kb_text') == 'H' and m.key('kb_go') == 'Next', 'one character is a name: Next works')
    ktype(m, 'idden net')
    expect(m.text('kb_text') == 'Hidden net', f'plain text: {m.text("kb_text")!r}')
    kdel(m, 10)
    expect(go_state(m) == (0, 'disable'), 'empty again: Next dimmed')
    m = start(typed=False)
    kclick(m, f'kb_k{kkeys(m)["A"]}'); ktype(m, 'a' * 31)
    expect(go_state(m) == (1, 'normal'), '32 characters: Next works')
    ktype(m, 'a')
    expect(go_state(m) == (0, 'disable'), '33 bytes are over an SSID: Next dimmed')
    m.hist = []
    kclick(m, 'kb_go')
    expect(fld(m) == (100, 56) and not m.cmds(), 'and inert (the field stays on the Name)')
    # Next moves to the Password: the same pad and field on the Password row, English password mode, the name shown as a label
    m = start()
    kclick(m, 'kb_go')
    expect(fld(m) == (144, 164) and m.key('kb_go') == 'Join' and go_state(m) == (0, 'disable') and m.text('wo_name_v') == 'Hidden net' and m.visible('wo_name_v') == 1 and m.visible('wo_name_h') == 0 and m.visible('wo_pass_v') == 0
           and m.text('kb_hint') in (None, '') and m.cmds() == [] and ('window_open', 'm1plus_wifisec') not in m.hist and ('window_open', 'm1plus_wifipass') not in m.hist,
           'Next: the field on the Password row, the name a static label, Join dimmed (no password yet), nothing sent, no page opened')
    expect(kkeys(m).get('q') == 0 and shown_(m, 'kb_clear') == (0, 0) and m.text('kb_text') in (None, ''), 'the password field: the lowercase page, no clear button, empty')
    ktype(m, 'hunter2')
    expect(go_state(m) == (0, 'disable') and isdots(m.text('kb_text'), 7), 'seven characters: dots, Join still dimmed')
    ktype(m, '2')
    expect(go_state(m) == (1, 'normal') and isdots(m.text('kb_text'), 8), 'eight characters: Join works')
    # values survive switching: tap the Name row, the password row, the eye
    m.tap('wo_hit_name')
    expect(fld(m) == (100, 56) and m.text('kb_text') == 'Hidden net' and m.key('kb_go') == 'Next' and go_state(m) == (1, 'normal') and isdots(m.text('wo_pass_v'), 8) and m.visible('wo_pass_v') == 1 and m.visible('wo_name_v') == 0
           and 'Q' not in kkeys(m), 'back to the Name: its text in the field (plain), the password as eight dots in the static label, Next works')
    ktype(m, 'x')
    expect(m.text('kb_text') == 'Hidden netx', 'the name keeps typing')
    kdel(m, 1)
    m.tap('wo_hit_pass')
    expect(fld(m) == (144, 164) and isdots(m.text('kb_text'), 8) and go_state(m) == (1, 'normal') and m.text('wo_name_v') == 'Hidden net' and m.visible('wo_pass_v') == 0, 'and the password is where it was')
    m.tap('wo_eye')
    expect(m.text('kb_text') == 'hunter22' and eye(m) == ['wf_eye'] * 3, 'the eye open: the password shown')
    m.tap('wo_hit_name')
    expect(m.text('wo_pass_v') == 'hunter22', 'the eye is the password\'s: the static label shows the text while it is open')
    m.tap('wo_eye')
    expect(isdots(m.text('wo_pass_v'), 8) and eye(m) == ['wf_eyeoff'] * 3, 'and dots when closed, also while the Name is typed')
    m.tap('wo_hit_name')
    expect(fld(m) == (100, 56), 'a tap on the row of the field that has the pad changes nothing')
    # the Security value, Back from the picker and the check follow the choice; the name and the password survive it
    n = len(m.hist)
    m.tap('wo_hit_sec')
    expect(('window_open', 'm1plus_wifisec') in m.hist[n:] and [m.visible(f'ws_check{k}') for k in range(3)] == [0, 1, 0] and m.cmds() == [], 'the Security row opens the picker with the check on WPA2/WPA3; nothing is sent')
    m.tap('ws_row2')
    expect(backs(m) == 1 and m.text('wo_sec_v') == 'WPA3', 'a tap on WPA3 sets it and goes back (it does not continue the flow)')
    close_win(m, 'm1plus_wifisec')
    m.tap('wo_hit_sec')
    expect([m.visible(f'ws_check{k}') for k in range(3)] == [0, 0, 1], 'the check follows the choice: WPA3 now')
    m.tap('ws_row1')
    close_win(m, 'm1plus_wifisec')
    expect(m.text('wo_sec_v') == 'WPA2/WPA3' and m.text('kb_text') == 'Hidden net' and isdots(m.text('wo_pass_v'), 8), 'WPA2/WPA3 again: the name and the password are as they were')
    # None: no Password row, one-row card, the field goes to the Name, Join; WPA2/WPA3 again brings the Password back with its value
    m.tap('wo_hit_pass')
    expect(fld(m) == (144, 164), 'the password is being typed')
    to_picker(m, 0)
    expect(m.text('wo_sec_v') == 'None' and fld(m) == (100, 56) and m.text('kb_text') == 'Hidden net' and m.key('kb_go') == 'Join' and go_state(m) == (1, 'normal') and m.visible('wo_card1a') == 1 and m.visible('wo_card1b') == 0
           and m.visible('wo_hair') == 0 and m.visible('wo_pass_l') == 0 and shown_(m, 'wo_eye') == (0, 0) and shown_(m, 'wo_hit_pass') == (0, 0) and m.visible('wo_pass_v') == 0 and m.visible('wo_err') == 0,
           'None: the card shrinks to Security, the Password row is gone (also its taps), the keyboard is on the Name, the action key reads Join and works')
    m.hist = []
    m.tap('wo_hit_pass')
    expect(fld(m) == (100, 56), 'a tap where the Password row was does nothing')
    to_picker(m, 1)
    expect(m.visible('wo_card1b') == 1 and m.visible('wo_pass_l') == 1 and isdots(m.text('wo_pass_v'), 8) and m.key('kb_go') == 'Next' and shown_(m, 'wo_eye') == (1, 1), 'WPA2/WPA3 again: the Password row is back with its value, the action key reads Next')
    # the stock supplicant: WPA3 is refused with the word and the choice stays
    m2 = start(page(Supp(ours=False, scan=SCAN, known=KNOWN)))
    m2.tap('wo_hit_sec'); m2.hist = []
    m2.tap('ws_row2')
    expect(m2.toasts() == ["This network isn't supported"] and backs(m2) == 0 and not [c for c in m2.hist if c[0] == 'widget_set_text_utf8' and c[1] == m2.widgets['wo_sec_v']] and [m2.visible(f'ws_check{k}') for k in range(3)] == [0, 1, 0] and m2.cmds() == [], 'WPA3 with stock\'s supplicant: the word, the picker stays, the choice is unchanged, nothing sent')
    # WPA2/WPA3 with the newer supplicant: scan_ssid, both key managements
    m = start()
    kclick(m, 'kb_go'); ktype(m, 'hunter22'); m.supp.log = []; m.hist = []
    kclick(m, 'kb_go')
    expect(m.cmds()[:9] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {SSID.hex()}', 'SET_NETWORK 1 scan_ssid 1', 'SET_NETWORK 1 psk "hunter22"', 'SET_NETWORK 1 key_mgmt WPA-PSK SAE', 'SET_NETWORK 1 ieee80211w 1',
                            'SET_NETWORK 1 priority 30000000', 'ENABLE_NETWORK 1', 'SAVE_CONFIG'] and 'SELECT_NETWORK 1' in m.cmds() and backs(m) == 1 and ('window_open', 'm1plus_wifipass') not in m.hist, f'Join: a hidden WPA2/WPA3 network: {m.cmds()[:9]}')
    conf = m.fs[WF_OURS].decode()
    expect('scan_ssid=1' in conf and 'key_mgmt=WPA-PSK SAE' in conf and 'scan_ssid' not in m.fs[WF_CONF].decode(), 'the block keeps scan_ssid through the split (a PMF transition network is ours)')
    expect(b'hunter22' not in bytes(m.u.mem_read(PSYMS['wo'], 0x200)), 'the password is wiped from the page\'s state at the join')
    close_win(m, 'm1plus_wifiother')
    expect(b'hunter22' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)) and b'Hidden net' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)), 'and from the keyboard\'s when the page is gone')
    m.supp.state, m.supp.ip = 'COMPLETED', '192.168.1.9'
    m.hist = []
    m.tick(4)
    expect(backs(m) == 0 and m.rows()[0][0] == 'Hidden net' and m.rows()[0][1] == 'wf_check' and not m.toasts() and ('window_open', 'm1plus_wifiother') not in m.hist, 'connected: the check, nothing else is asked and no page is left to go back')
    # the Join key on the Password field needs a valid name too
    m = start()
    kclick(m, 'kb_go'); ktype(m, 'hunter22')
    m.tap('wo_hit_name'); kdel(m, 10); m.tap('wo_hit_pass')
    expect(go_state(m) == (0, 'disable') and m.visible('wo_name_h') == 1 and m.visible('wo_name_v') == 0, 'no name: Join dimmed on the Password field, the grey placeholder in the Name row')
    m.supp.log = []
    kclick(m, 'kb_go')
    expect(m.cmds() == [], 'and inert')
    # the stock supplicant: WPA2 only
    m = start(page(Supp(ours=False, scan=SCAN, known=KNOWN)))
    kclick(m, 'kb_go'); ktype(m, 'hunter22'); m.supp.log = []
    kclick(m, 'kb_go')
    expect(m.cmds()[:6] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {SSID.hex()}', 'SET_NETWORK 1 scan_ssid 1', 'SET_NETWORK 1 psk "hunter22"', 'SET_NETWORK 1 key_mgmt WPA-PSK', 'SET_NETWORK 1 priority 30000000']
           and 'scan_ssid=1' in m.fs[WF_CONF].decode() and 'key_mgmt=WPA-PSK\n' in m.fs[WF_CONF].decode(), f'WPA2/WPA3 with stock\'s supplicant: WPA-PSK only, scan_ssid in stock\'s file: {m.cmds()[:6]}')
    # WPA3 with the newer supplicant: one character is a password
    m = start()
    to_picker(m, 2)
    kclick(m, 'kb_go')
    expect(m.key('kb_go') == 'Join' and go_state(m) == (0, 'disable') and fld(m) == (144, 164), 'WPA3: Next, then the Password field')
    ktype(m, 'a'); m.supp.log = []
    expect(go_state(m) == (1, 'normal'), 'WPA3 takes a password of one character')
    kclick(m, 'kb_go')
    expect(m.cmds()[:6] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {SSID.hex()}', 'SET_NETWORK 1 scan_ssid 1', 'SET_NETWORK 1 sae_password "a"', 'SET_NETWORK 1 key_mgmt SAE', 'SET_NETWORK 1 ieee80211w 2']
           and 'scan_ssid=1' in m.fs[WF_OURS].decode(), f'WPA3: sae_password, SAE, PMF required, scan_ssid in ours: {m.cmds()[:6]}')
    # WPA2/WPA3 password rules: a euro sign never enables Join
    m = start()
    kclick(m, 'kb_go'); ktype(m, 'hunter2')
    to_picker(m, 2)
    expect(go_state(m) == (1, 'normal'), 'six characters are a WPA3 password, though not a WPA2 one: the key follows the chosen security')
    to_picker(m, 1)
    expect(go_state(m) == (0, 'disable'), 'and not for WPA2/WPA3 again')
    # None: an open hidden network joins from the Name field
    m = start()
    to_picker(m, 0)
    m.supp.log = []; m.hist = []
    kclick(m, 'kb_go')
    expect(m.cmds()[:9] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {SSID.hex()}', 'SET_NETWORK 1 scan_ssid 1', 'SET_NETWORK 1 key_mgmt NONE', 'SET_NETWORK 1 priority 30000000', 'ENABLE_NETWORK 1', 'SAVE_CONFIG', 'LIST_NETWORKS', 'SELECT_NETWORK 1']
           and ('window_open', 'm1plus_wifipass') not in m.hist and backs(m) == 1, f'None: Join on the Name field, no password asked, an open hidden network joins: {m.cmds()[:8]}')
    expect('scan_ssid=1' in m.fs[WF_CONF].decode() and 'key_mgmt=NONE' in m.fs[WF_CONF].decode(), 'scan_ssid stays in the real file for an open network')
    close_win(m, 'm1plus_wifiother')
    m.tick(1)
    expect(m.rows()[0][0] == 'Hidden net' and m.rows()[0][1].startswith('wf_spin'), 'the list shows it joining')
    m.supp.state, m.supp.ip = 'COMPLETED', '10.0.0.5'
    m.tick(4)
    expect(m.rows()[0][1] == 'wf_check' and not m.toasts() and 1 in m.supp.nets, 'connected: the check; the network stays saved')
    # a hidden open network that never shows: after 20 s the word, and it is removed
    m = start()
    to_picker(m, 0)
    kclick(m, 'kb_go'); close_win(m, 'm1plus_wifiother'); m.tick(2)
    m.hist = []; m.supp.log = []
    m.tick(84)
    expect('REMOVE_NETWORK 1' in m.cmds() and m.toasts() == ["Couldn't connect"] and ('window_open', 'm1plus_wifiother') not in m.hist and 1 not in m.supp.nets and 'Hidden' not in m.fs[WF_CONF].decode() and 'Hidden' not in m.fs[WF_COPY].decode(),
           'no answer for 20 s: "Couldn\'t connect" (a toast, as a saved network\'s) and the network is removed from the supplicant and both files')
    # a wrong password: removed, the page comes back with Name and Security, an empty Password and the line; the next try is hidden again
    m = start()
    to_picker(m, 2)
    kclick(m, 'kb_go'); ktype(m, 'hunter22'); kclick(m, 'kb_go')
    close_win(m, 'm1plus_wifiother'); m.tick(1)
    m.supp.state, m.supp.temp = 'DISCONNECTED', {1}
    m.hist = []; m.supp.log = []
    m.tick(4)
    expect('REMOVE_NETWORK 1' in m.cmds() and ('window_open', 'm1plus_wifiother') in m.hist and ('window_open', 'm1plus_wifipass') not in m.hist and not m.toasts() and 1 not in m.supp.nets
           and 'Hidden' not in m.fs[WF_CONF].decode() + m.fs[WF_OURS].decode(), 'a wrong password: the network is removed, the Join Wi-Fi Network page opens again (not the password page)')
    expect(m.text('wo_name_v') == 'Hidden net' and m.visible('wo_name_v') == 1 and m.text('wo_sec_v') == 'WPA3' and fld(m) == (144, 164) and m.text('kb_text') in (None, '') and m.visible('wo_err') == 1 and go_state(m) == (0, 'disable')
           and m.key('kb_go') == 'Join', 'with Name and Security kept, the Password field active and empty, the grey "Incorrect password" line, Join dimmed')
    ktype(m, 'b')
    expect(m.visible('wo_err') == 0 and go_state(m) == (1, 'normal'), 'the line goes at the first character')
    m.supp.log = []; m.supp.temp = set(); m.hist = []
    kclick(m, 'kb_go')
    expect(m.cmds()[2] == 'SET_NETWORK 2 scan_ssid 1' and m.cmds()[3] == 'SET_NETWORK 2 sae_password "b"' and backs(m) == 1, f'the second try is a hidden network again: {m.cmds()[:4]}')
    close_win(m, 'm1plus_wifiother')
    # the line stays when the Name is typed in, and Back out of the reopened page returns to the list
    m.supp.state, m.supp.temp = 'DISCONNECTED', {2}
    m.tick(1); m.hist = []
    m.tick(4)
    expect(('window_open', 'm1plus_wifiother') in m.hist and m.visible('wo_err') == 1, 'a second refusal asks again')
    m.tap('wo_hit_name')
    expect(m.visible('wo_err') == 1 and fld(m) == (100, 56), 'the line stays while the Name is looked at')
    m.hist = []
    close_win(m, 'm1plus_wifiother'); m.tick(2)
    expect(backs(m) == 0 and not m.toasts(), 'Back out of it: nothing joined, no word')
    # Back (cancel) out of the page: nothing was sent
    m = start()
    kclick(m, 'kb_go'); ktype(m, 'hunter22'); m.supp.log = []
    close_win(m, 'm1plus_wifiother')
    m.tick(4)
    expect(m.cmds()[:1] == ['STATUS'] and 'ADD_NETWORK' not in m.cmds() and not m.toasts(), 'Back out of the page: nothing joined, no word')
    expect(b'hunter22' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)) and b'hunter22' not in bytes(m.u.mem_read(PSYMS['wo'], 0x200)) and b'Hidden net' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)), 'and neither the keyboard nor the page holds the text')
    # the name is sent as typed, in hex
    m = start(name='Cafe')
    to_picker(m, 0)
    m.supp.log = []
    kclick(m, 'kb_go')
    expect(m.cmds()[1] == f'SET_NETWORK 1 ssid {b"Cafe".hex()}', 'the name is sent as typed, in hex')
    # pages that cannot be made: nothing is sent
    m = page(); opened(m); m.supp.log = []; m.windows['m1plus_wifiother'] = 0
    m.tap('wf_row_other')
    expect(m.cmds() == [] and not m.toasts(), 'a page that will not open: nothing happens')
    for gone in ('kb_clear', 'wo_hit_sec', 'wo_eye', 'wo_card1a'):
        m = page(); opened(m); m.supp.log = []; m.hist = []
        m.widgets.pop(gone)
        m.tap('wf_row_other')
        expect(backs(m) == 1 and m.cmds() == [], f'a page without {gone} backs out')
    m = start()
    m.windows['m1plus_wifisec'] = 0; m.supp.log = []
    m.tap('wo_hit_sec')
    expect(m.cmds() == [] and not m.toasts() and fld(m) == (100, 56), 'a picker that will not open: nothing happens')
    m = start()
    del m.widgets['ws_row2']; m.hist = []
    m.tap('wo_hit_sec')
    expect(backs(m) == 1 and m.cmds() == [], 'a picker that is not ours backs out')
    # Wi-Fi turned off under the pages: the one on top goes, the page under the picker follows
    m = start()
    m.tap('wo_hit_sec'); m.hist = []
    m.u.mem_write(WIFI_FLAG, bytes([0]))
    m.tick(1)
    expect(backs(m) == 1, 'Wi-Fi off under the picker: it goes back')
    close_win(m, 'm1plus_wifisec'); m.tick(1)
    expect(backs(m) == 2, 'then the page under it')
    m = start()
    m.hist = []
    m.u.mem_write(WIFI_FLAG, bytes([0]))
    m.tick(1)
    expect(backs(m) == 1, 'Wi-Fi off under the page: back')
    # a tap under a dialog does nothing
    m = page(); opened(m); m.supp.log = []; m.hist = []
    m.u.mem_write(WIFI_FLAG, bytes([0]))
    m.tick(1)
    m.tap('wf_row_other')
    expect(('window_open', 'm1plus_wifiother') not in m.hist, 'Wi-Fi off: Other... is not offered')
    # the page scans at once when it opens (not only after the idle timer), before any tick
    m = page(); opened(m)
    expect(m.cmds()[:4] == ['PING', 'STATUS', 'LIST_NETWORKS', 'GET_CAPABILITY key_mgmt'] or 'SCAN' in m.cmds()[:8], f'opening the page asks the supplicant for a scan: {m.cmds()[:8]}')
    expect(m.cmds().index('SCAN') < m.cmds().count('STATUS') + 8 and m.rows() and m.visible('wf_hdr_net_spin') == 1, 'the scan runs at once (the header spinner is up) and the cached results are listed meanwhile')
    m = page(); opened(m)
    expect(sum(1 for c in m.cmds() if c == 'SCAN') == 1, 'one scan, not one per path')


def info_tests(ctx):
    expect = ctx.expect
    ROUTE = 'Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\nwlan0\t0001A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\nwlan0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n'
    def card(m):
        """The info page's shown rows, top to bottom: (kind, y, label, value, piece, hair)."""
        out = []
        for n in ('wi_row_forget', 'wi_row_auto', 'wi_row_join'):
            if m.visible(n): out.append((n[7:], m.y(n), None, None, m.piece(n), None))
        for i in range(4):
            if m.visible(f'wi_f{i}'): out.append(('field', m.y(f'wi_f{i}'), m.text(f'wi_fl{i}'), m.text(f'wi_fv{i}'), m.piece(f'wi_f{i}'), m.visible(f'wi_fh{i}')))
        return sorted(out, key=lambda r: r[1])
    def gaps(m): return [m.y(f'wi_gap{i}') for i in range(3) if m.visible(f'wi_gap{i}')]
    def close_info(m):
        fn, ctx = m.bound[(m.window, O['EVT_DESTROY'])]
        m.call(fn, a0=ctx, a1=0)
    def open_info(m, name, x=270):
        m.hist = [c for c in m.hist if c[0] != 'window_open']
        m.tap(f'wf_row{m.idx(name)}', x=x)

    # a saved network that is not connected: Forget, Security, Auto-Join
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Home')
    expect(('window_open', 'm1plus_wifiinfo') in m.hist and m.cmds() == [] and m.text('label_title') == 'Home', f'the info glyph opens the page and the navbar says the name: {m.text("label_title")}')
    rows = card(m)
    expect([(r[0], r[1]) for r in rows] == [('forget', 10), ('field', 82), ('auto', 154)] and gaps(m) == [62, 134] and rows[1][2:4] == ('Security', 'WPA/WPA2') and rows[0][4] == 'pod_cd_single' and rows[1][4] == 'pod_cd_single'
           and rows[2][4] == 'pod_cd_single' and not rows[1][5] and not m.visible('wi_row_join') and not m.visible('wi_gap2'), f'Forget This Network, the Security card, Auto-Join in their own cards 20 px apart: {rows} {gaps(m)}')
    expect(m.props[(m.widgets['wifiinfo_scrollview'], 'virtual_h')] == 154 + 52 + 10 and m.image('wi_auto_img') == 'sset_on', 'the list is as long as its rows and the switch is on')
    expect(all(m.props.get((m.widgets[n], 'sensitive')) == 1 for n in ('wi_row_forget', 'wi_row_auto')) and (m.widgets['wi_f0'], 'sensitive') not in m.props and (m.widgets['wi_gap0'], 'sensitive') not in m.props
           and not m.visible('wi_f1') and m.props.get((m.widgets['wi_f1'], 'sensitive')) == 0, 'Forget and Auto-Join take a tap, the info rows and the gaps never')
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])], 'Back and Now Playing are bound')
    # the name is cut with an ellipsis when it is long and shown as UTF-8
    m = page(); opened(m)
    open_info(m, 'Sam’s iPhone')
    expect(m.text('label_title') == 'Sam’s iPhone'.encode().decode('latin-1') and card(m)[0][0] == 'field' and card(m)[-1][0] == 'join', 'a name with an apostrophe: the title is the UTF-8 name')

    # the connected network: the address and the router
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); m.fs['/proc/net/route'] = ROUTE.encode(); opened(m)
    open_info(m, 'Home')
    rows = card(m)
    expect([r[1:4] for r in rows] == [(10, None, None), (82, 'Security', 'WPA/WPA2'), (134, 'IP Address', '192.168.1.20'), (186, 'Router', '192.168.1.1'), (258, None, None)]
           and [r[4] for r in rows[1:4]] == ['pod_cd_top', 'pod_cd_mid', 'pod_cd_bot'] and [r[5] for r in rows[1:4]] == [1, 1, 0] and gaps(m) == [62, 238], f'connected: Security, IP Address, Router in one card: {rows}')
    supp.state, supp.ip = 'ASSOCIATING', None
    m.tick(4)
    expect([r[2] for r in card(m) if r[0] == 'field'] == ['Security'] and gaps(m) == [62, 134] and card(m)[-1][1] == 154, 'when it drops, the address and router rows go')
    supp.state, supp.ip = 'COMPLETED', '192.168.1.77'
    m.fs['/proc/net/route'] = b''
    m.tick(4)
    expect([r[3] for r in card(m) if r[0] == 'field'] == ['WPA/WPA2', '192.168.1.77'], 'an address without a route: the router row stays out')
    m.fs['/proc/net/route'] = ROUTE.encode()
    m.tick(4)
    expect([r[3] for r in card(m) if r[0] == 'field'][-1] == '192.168.1.1', 'and comes when the route does')
    # a network that is not the connected one never shows an address
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Cafe Open', [('key_mgmt', 'NONE')])]); supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); m.fs['/proc/net/route'] = ROUTE.encode(); opened(m)
    open_info(m, 'Cafe Open')
    expect([r[2] for r in card(m) if r[0] == 'field'] == ['Security'] and card(m)[1][3] == 'Open', 'another saved network: Security only (Open)')

    # not saved: Security and Join
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Cafe Open')
    rows = card(m)
    expect([(r[0], r[1], r[3]) for r in rows] == [('field', 10, 'Open'), ('join', 82, None)] and gaps(m) == [62] and rows[0][4] == 'pod_cd_single' and not m.visible('wi_row_forget') and not m.visible('wi_row_auto')
           and m.props[(m.widgets['wifiinfo_scrollview'], 'virtual_h')] == 82 + 52 + 10 and m.props.get((m.widgets['wi_row_join'], 'sensitive')) == 1, f'an unsaved network: Security, then Join: {rows}')
    for name, label in (('Owe', 'Enhanced Open'), ('Safe', 'WPA3'), ('Mixed', 'WPA2/WPA3'), ('Corp', 'Enterprise'), ('Old', 'WEP'), ('Sam’s iPhone', 'WPA/WPA2')):
        m = page(); opened(m)
        open_info(m, name)
        expect(card(m)[0][3] == label, f'{name}: the security reads {label}')
    # Join is the row's path: an open network joins and the page goes back
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Cafe Open'); m.hist = []
    m.tap('wi_row_join')
    expect(m.cmds()[:2] == ['ADD_NETWORK', f'SET_NETWORK 1 ssid {b"Cafe Open".hex()}'] and 'SELECT_NETWORK 1' in m.cmds() and ('navigator_back',) in m.hist, f'Join sends what a tap on the row does and goes back: {m.cmds()[:3]}')
    # a secured one asks for the password on our page, over the info page
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Sam’s iPhone'); m.hist = []
    m.tap('wi_row_join')
    expect(('window_open', 'm1plus_wifipass') in m.hist and m.cmds() == [] and ('navigator_back',) not in m.hist and not any(c[0] == 'dialog' for c in m.sock), 'a secured network: Join opens the password page, nothing is sent yet, the info page stays under it')
    ktype(m, 'hunter22hunter')
    kclick(m, 'kb_go')
    expect('SET_NETWORK 1 psk "hunter22hunter"' in m.cmds() and 'SELECT_NETWORK 1' in m.cmds() and ('navigator_back',) in m.hist, 'its Join sends the same commands and closes the password page')
    n = [c for c in m.hist if c[0] == 'navigator_back']
    close_info(m)   # the password page's end (the harness has one window)
    m.tick(1)
    expect(len([c for c in m.hist if c[0] == 'navigator_back']) == len(n) + 1, 'and the info page goes back too (the list shows the network joining)')
    # Back from the password page: nothing is sent, the info page is where it was
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Sam’s iPhone'); m.hist = []
    m.tap('wi_row_join'); ktype(m, 'hunter22hunter')
    close_info(m)
    m.tick(2)
    expect(m.cmds() == [] and ('navigator_back',) not in m.hist, 'Back from the password page: nothing sent, the info page stays')
    m = page(Supp(ours=False, scan=SCAN, known=KNOWN)); opened(m); m.supp.log = []
    open_info(m, 'Safe'); m.hist = []
    m.tap('wi_row_join')
    expect(m.cmds() == [] and m.toasts() == ["This network isn't supported"] and ('navigator_back',) not in m.hist, 'WPA3 with stock\'s supplicant: the same word as on the list, the page stays')
    for name, word in (('Corp', "Enterprise isn't supported yet"), ('Old', "WEP isn't supported")):
        m = page(); opened(m); m.supp.log = []
        open_info(m, name); m.hist = []
        m.tap('wi_row_join')
        expect(m.cmds() == [] and m.toasts() == [word] and ('navigator_back',) not in m.hist, f'{name}: Join answers "{word}"')

    # Forget This Network
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Home'); m.hist = []
    m.confirm_yes = False
    m.tap('wi_row_forget')
    expect(m.asked('msg_wificancelsave') and m.cmds() == [] and ('navigator_back',) not in m.hist, 'Forget: Delete Record? and No: nothing happens')
    m.confirm_yes = True
    m.tap('wi_row_forget')
    expect(m.cmds()[:2] == ['REMOVE_NETWORK 0', 'SAVE_CONFIG'] and 'Home' not in m.fs[WF_CONF].decode() and ('navigator_back',) in m.hist, f'Yes: forgotten for good and back to the list: {m.cmds()[:2]}')
    expect(m.idx('Home') >= WP_CUR + WP_MY and not m.visible('wf_hdr_my'), 'the list shows Home as an ordinary network')
    # a WPA3 network is forgotten from the file of ours too
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Safe', [('sae_password', '"pw"'), ('key_mgmt', 'SAE'), ('ieee80211w', '2')])])
    m = page(supp); m.fs[WF_OURS] = b'network={\n\tssid="Safe"\n}\n'; opened(m)
    open_info(m, 'Safe')
    m.tap('wi_row_forget')
    expect(b'Safe' not in m.fs.get(WF_OURS, b''), 'Forget removes a WPA3 network from wifi-networks too')

    # Auto-Join
    m = page(); opened(m); m.supp.log = []
    open_info(m, 'Home')
    m.tap('wi_row_auto')
    expect(m.cmds()[:2] == ['DISABLE_NETWORK 0', 'SAVE_CONFIG'] and 'disabled=1' in m.fs[WF_CONF].decode(), f'Auto-Join off: DISABLE_NETWORK and a save: {m.cmds()[:2]}')
    expect(m.image('wi_auto_img') == 'sset_off' and m.supp.nets[0]['dis'] == 1, 'the switch shows off at once')
    m.tick(4)
    expect(m.image('wi_auto_img') == 'sset_off', 'and still after the list is read again')
    m.supp.log = []
    m.tap('wi_row_auto')
    expect(m.cmds()[:2] == ['ENABLE_NETWORK 0', 'SAVE_CONFIG'] and 'disabled' not in m.fs[WF_CONF].decode() and m.image('wi_auto_img') == 'sset_on', 'on again: ENABLE_NETWORK, saved, no disabled line')
    # a network that was off when the page opens shows off
    supp = Supp(scan=SCAN, known=[(b'Home', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK'), ('disabled', '1')])])
    m = page(supp); opened(m)
    open_info(m, 'Home')
    expect(m.image('wi_auto_img') == 'sset_off', 'a saved network the supplicant has disabled shows Auto-Join off')
    # the split keeps it for both files: a WPA3 network off goes to wifi-networks with disabled=1, a stock network stays in the real file
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Safe', [('sae_password', '"pw"'), ('key_mgmt', 'SAE'), ('ieee80211w', '2')])])
    m = page(supp); opened(m)
    open_info(m, 'Safe'); m.tap('wi_row_auto')
    expect('disabled=1' in m.fs[WF_OURS].decode() and 'Safe' in m.fs[WF_OURS].decode() and 'disabled' not in m.fs[WF_CONF].decode() and 'Safe' not in m.fs[WF_CONF].decode(), 'Auto-Join off on a WPA3 network: disabled=1 lands in wifi-networks')
    m.tick(4)
    close_info(m)
    open_info(m, 'Home')
    m.tap('wi_row_auto')
    expect('disabled=1' in m.fs[WF_CONF].decode() and 'disabled=1' in m.fs[WF_OURS].decode() and m.fs[WF_CONF].decode().count('network=') == 1, f'and on a stock network: in the real file, the other network keeps its line: {m.fs[WF_CONF]} {m.fs[WF_OURS]} {m.cmds()[-6:]}')

    # selecting a network leaves the others as they were
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Cafe Open', [('key_mgmt', 'NONE'), ('disabled', '1')]), (b'Far', [('key_mgmt', 'NONE')])])
    m = page(supp); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Home")}')
    cm = m.cmds()
    i = cm.index('SELECT_NETWORK 0')
    expect(cm[i - 1] == 'LIST_NETWORKS' and cm[i + 1:i + 3] == ['ENABLE_NETWORK all', 'DISABLE_NETWORK 1'], f'the list is read before the select; after it every network is enabled and the ones that were Auto-Join off disabled again: {cm[i - 1:]}')
    expect([n['dis'] for n in supp.nets.values()] == [0, 1, 0], 'one that is off stays off, the others are on')
    m.supp.log = []
    open_info(m, 'Far'); m.tap('wi_row_forget')
    expect('disabled=1' in m.fs[WF_COPY].decode() and m.fs[WF_COPY].decode().count('disabled=1') == 1, 'a later save writes only the Auto-Join off line')
    # a new network added from the list: the others stay enabled too
    supp = Supp(scan=SCAN, known=KNOWN + [(b'Far', [('key_mgmt', 'NONE')])])
    m = page(supp); opened(m); m.supp.log = []
    m.tap(f'wf_row{m.idx("Cafe Open")}')
    expect([n['dis'] for n in supp.nets.values()] == [0, 0, 0] and 'disabled' not in m.fs[WF_COPY].decode(), 'joining a new network keeps the saved ones enabled and the file clean')

    # the page follows the list: a network that leaves the scan stays, Forget still works
    sc = [r for r in SCAN if r[2] != b'Cafe Open']
    m = page(); opened(m)
    open_info(m, 'Cafe Open')
    m.supp.scan = sc
    m.supp.log = []
    m.tick(52 + 16 + 4)
    expect(m.text('label_title') == 'Cafe Open' and card(m)[0][3] == 'Open' and card(m)[-1][0] == 'join' and m.visible('wi_row_join'), 'an unsaved network that left the scan: the page stays as it was')
    m = page(Supp(scan=[r for r in SCAN if r[2] != b'Home'], known=KNOWN)); opened(m)
    open_info(m, 'Home')
    expect([r[0] for r in card(m)] == ['forget', 'field', 'auto'], 'a saved network out of range has its page')
    m.tap('wi_row_forget')
    expect(m.cmds()[-2:] == ['REMOVE_NETWORK 0', 'SAVE_CONFIG'] or 'REMOVE_NETWORK 0' in m.cmds(), 'and can be forgotten')
    # forgotten somewhere else (the stock page): the page becomes an unsaved network's
    m = page(); opened(m)
    open_info(m, 'Home')
    m.supp.nets.pop(0)
    m.tick(4)
    expect([r[0] for r in card(m)] == ['field', 'join'] and not m.visible('wi_row_forget') and not m.visible('wi_row_auto'), 'forgotten elsewhere: Security and Join')
    # connecting from the page's list under it
    supp = Supp(scan=SCAN, known=KNOWN)
    m = page(supp); m.fs['/proc/net/route'] = ROUTE.encode(); opened(m)
    open_info(m, 'Home')
    supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m.tick(4)
    expect([r[2] for r in card(m) if r[0] == 'field'] == ['Security', 'IP Address', 'Router'], 'the network connects while the page is open: its address appears')
    # the supplicant stops answering: the page keeps what it showed
    supp.alive = False
    m.tick(8)
    expect([r[2] for r in card(m) if r[0] == 'field'] == ['Security', 'IP Address', 'Router'] and ('navigator_back',) not in m.hist, 'no supplicant for a moment: nothing changes')
    # Wi-Fi turned off elsewhere: back to the list
    supp.alive = True
    m.hist = []
    m.u.mem_write(WIFI_FLAG, bytes([0]))
    m.tick(1)
    expect(('navigator_back',) in m.hist, 'Wi-Fi turned off under the page: back to the list')
    # a dialog is up: the page's buttons take no tap
    m = page(); opened(m)
    open_info(m, 'Home')
    m.on_confirm = lambda mm: (mm.tap('wi_row_auto'), mm.tap('wi_row_forget'))
    m.confirm_yes = False; m.supp.log = []
    m.tap('wi_row_forget')
    expect(m.cmds() == [], 'a tap under a dialog does nothing')


def switch_tests(ctx):
    expect = ctx.expect
    m = page(); opened(m); m.sock = []
    m.tap('wf_row_sw')
    expect([x for x in m.sock if x[0] in ('wifi_switch', 'switchBluetooth', 'usleep')] == [('wifi_switch', 1, 1)], 'Wi-Fi on: the stock switch is called with 1 (it turns Wi-Fi off)')
    expect(m.image('wf_sw_img') == 'sset_off' and not m.visible('wf_hdr_my') and not m.visible('wf_hdr_net') and not m.visible('wf_row_other') and not any(m.visible(f'wf_row{i}') for i in range(WP_ROWS))
           and m.piece('wf_row_sw') == 'pod_cd_single' and m.props[(m.widgets['wifi_scrollview'], 'virtual_h')] == 72, 'off: the switch row alone')
    m.supp.log = []
    m.tick(40)
    expect(m.cmds() == [], 'the supplicant is left alone while Wi-Fi is off')
    # on, Bluetooth off
    m.sock = []
    m.tap('wf_row_sw')
    expect([x for x in m.sock if x[0] in ('wifi_switch', 'switchBluetooth')] == [('wifi_switch', 1, 0)] and m.image('wf_sw_img') == 'sset_on' and m.visible('wf_hdr_net') and m.visible('wf_row_other') and m.rows() == [],
           'on: the stock switch, Networks and Other..., the networks when the supplicant answers')
    m.tick(4)
    expect(len(m.rows()) == 8 and 'SCAN' in m.cmds(), 'and they come')
    # on with Bluetooth on: the coex warning first, Bluetooth stays on
    m = page(wifi=False, bt=True); opened(m); m.sock = []
    m.confirm_yes = False
    m.tap('wf_row_sw')
    expect(m.asked('msg_wifi_open') and not [x for x in m.sock if x[0] in ('wifi_switch', 'switchBluetooth')] and m.image('wf_sw_img') == 'sset_off',
           'Bluetooth is on: the warning; No leaves everything as it was')
    m.confirm_yes = True
    m.tap('wf_row_sw')
    seq = [x[0] for x in m.sock if x[0] in ('wifi_switch', 'switchBluetooth', 'usleep')]
    expect(seq == ['wifi_switch'] and m.image('wf_sw_img') == 'sset_on', f'Yes: Wi-Fi on, Bluetooth left on: {seq}')
    # turned off elsewhere
    m = page(); opened(m)
    m.u.mem_write(WIFI_FLAG, b'\0')
    m.tick(1)
    expect(m.image('wf_sw_img') == 'sset_off' and not m.visible('wf_hdr_net') and m.rows() == [], 'Wi-Fi turned off from the pull-down: the page follows')
    m.u.mem_write(WIFI_FLAG, b'\1'); m.supp.log = []
    m.tick(8)
    expect(len(m.rows()) == 8 and 'SCAN' in m.cmds(), 'and on again')


def timer_tests(ctx):
    expect = ctx.expect
    m = page(); opened(m)
    m.supp.log = []
    frames, shown = [], []
    for t in range(1, 17):
        m.tick(1)
        frames.append(m.image('wf_hdr_net_spin'))
        shown.append(m.visible('wf_hdr_net_spin'))
    log = m.cmds()
    expect(log.count('STATUS') == 4 and log.count('SCAN_RESULTS') == 2 and log.count('LIST_NETWORKS') == 4, f'a status every second, the results at half the scan and at its end: {log}')
    expect(all(f.startswith('wf_spin') for f in frames[:15]) and len(set(frames[:15])) == 8 and all(shown[:15]), 'the header\'s spinner turns through its eight frames while the scan runs')
    expect(shown[15] == 0, 'and goes when the scan ends')
    m.supp.log = []
    m.tick(47)
    expect('SCAN' not in m.cmds(), 'idle: no scan for 12 s')
    m.tick(1)
    expect(m.cmds().count('SCAN') == 1, 'then another scan')
    # a new network turns up in the results: the rows change, the order keeps
    m.supp.scan = m.supp.scan + [(-40, '[ESS]', b'Newcomer')]
    m.tick(16)
    expect([r[0] for r in m.rows()][1] == 'Newcomer', 'a network found by a later scan is listed in its place')
    # in the background and while connecting there is no scan
    m = page(); opened(m)
    m.tick(16)
    m.call(m.bound[(WIN, O['EVT_WINDOW_TO_BG'])][0], a0=0, count=20000)
    m.supp.log = []
    m.tick(100)
    expect('SCAN' not in m.cmds() and m.cmds().count('STATUS') > 20, 'a page behind another does not scan (the status is still read)')
    m.call(m.bound[(WIN, O['EVT_WINDOW_TO_FG'])][0], a0=0, count=20000)
    m.supp.log = []
    m.tick(4)
    expect('SCAN' in m.cmds(), 'in front again: a scan in a second')
    m = page(); opened(m); m.tick(16)
    m.supp.state, m.supp.cur, m.supp.ip = 'ASSOCIATING', 0, None
    m.supp.log = []
    m.tick(60)
    expect('SCAN' not in m.cmds(), 'no scan while the supplicant is connecting')
    # the connecting row's spinner keeps turning with no scan, one frame per tick (also after the initial scan of an automatic connection)
    def spin_run(m, n):
        out = []
        for _ in range(n):
            m.tick(1)
            out.append(int(m.rows()[0][1][len('wf_spin'):]))
        return out
    steps = lambda fr: [(b - a) % 8 for a, b in zip(fr, fr[1:])]
    m = page(); opened(m); m.tick(16)
    m.supp.state, m.supp.cur, m.supp.ip = 'ASSOCIATING', 0, None
    m.tick(4)
    fr = spin_run(m, 24)
    expect(len(set(fr)) == 8 and steps(fr) == [1] * 23, f'connecting, no scan: the row\'s spinner advances one frame per tick: {fr}')
    m.supp.state = 'COMPLETED'
    fr = spin_run(m, 8)
    expect(len(set(fr)) >= 7 and all(d != 0 for d in steps(fr)), f'associated, no address: still turning (the state change may lay the rows out once more): {fr}')
    m.supp.ip = '192.168.1.20'
    m.tick(4)
    expect(m.rows()[0][1] == 'wf_check', 'DHCP gave an address: the check')
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'ASSOCIATING', 0, None
    m = page(supp); opened(m); m.tick(20)
    expect(not m.visible('wf_hdr_net_spin'), 'the initial scan has ended')
    fr = spin_run(m, 12)
    expect(len(set(fr)) == 8 and steps(fr) == [1] * 11, f'an automatic connection after the scan: turning: {fr}')
    # an automatic connection that starts before the supplicant's table has the network: the row's signal comes once the table has it, without a scan of ours
    supp = Supp(scan=[], known=KNOWN); supp.state, supp.cur, supp.ip = 'ASSOCIATING', 0, None
    m = page(supp); opened(m); m.tick(20)
    expect(not m.visible('wf_hdr_net_spin') and m.rows()[0][0] == 'Home' and m.rows()[0][2] == 'wf_sig0', f'the initial scan found nothing: no signal yet: {m.rows()[:1]}')
    supp.scan, supp.log = list(SCAN), []
    m.tick(4)
    expect(m.rows()[0][2] == 'wf_sig3' and 'SCAN' not in m.cmds() and 'SCAN_RESULTS' in m.cmds(), f'still connecting: the table is read, the row shows its signal, no scan started: {m.rows()[:1]} {m.cmds()}')
    supp.state, supp.ip = 'COMPLETED', '192.168.1.20'
    m.tick(4)
    supp.log = []
    m.tick(16)
    expect(m.rows()[0][1] == 'wf_check' and 'SCAN_RESULTS' not in m.cmds(), f'connected: the table is read only with the scans again: {m.cmds()}')
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'ASSOCIATING', 0, None
    m = page(supp); opened(m)
    fr = spin_run(m, 8)
    expect(steps(fr) == [1] * 7 and m.visible('wf_hdr_net_spin'), f'during a scan: one frame per tick, no double advance: {fr}')
    # a dialog is up: the timer leaves everything alone (the page's flag is found as the one word the dialog sets)
    from elftools.elf.elffile import ELFFile
    with open(os.path.join(BUILD, 'patch.elf'), 'rb') as f: size = ELFFile(f).get_section_by_name('.symtab').get_symbol_by_name('wp')[0]['st_size']
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); opened(m); m.tick(2)
    base, before, during = PSYMS['wp'], bytes(m.u.mem_read(PSYMS['wp'], size)), []
    m.on_confirm = lambda mm: during.append(bytes(mm.u.mem_read(base, size)))
    m.confirm_yes = False
    m.tap(f'wf_row{m.idx("Home")}')
    flips = [i for i in range(0, size, 4) if struct.unpack_from('<I', during[0], i)[0] != struct.unpack_from('<I', before, i)[0]]
    expect(len(during) == 1 and len(flips) == 1 and struct.unpack_from('<I', during[0], flips[0])[0] == 1 and bytes(m.u.mem_read(base + flips[0], 4)) == bytes(4), 'a stock dialog sets one flag in the page, and clears it when it is gone')
    m.setword(base + flips[0], 1); m.supp.log = []
    m.tick(8)
    expect(m.cmds() == [], 'while a stock dialog is up the page asks the supplicant nothing')
    m.setword(base + flips[0], 0)
    m.tick(4)
    expect('STATUS' in m.cmds(), 'and goes on after it')
    # the scroll fade
    m = page(); opened(m)
    sv = m.widgets['wifi_scrollview']
    fn, ctx_ = m.bound[(sv, O['EVT_SCROLL'])]
    m.setword(sv + O['SC_YOFF'], 30); m.call(fn, a0=ctx_, count=20000)
    expect(m.props[(m.widgets['img_nb_fade'], 'visible')] == 1, 'the navbar fade shows while the list is scrolled')
    m.setword(sv + O['SC_YOFF'], 0); m.call(fn, a0=ctx_, count=20000)
    expect(m.props[(m.widgets['img_nb_fade'], 'visible')] == 0, 'and goes at the top')
    # the list shrinks while scrolled: the offset moves back
    m = page(); opened(m)
    sv = m.widgets['wifi_scrollview']; m.props[(sv, 'h')] = 400
    m.setword(sv + O['SC_YOFF'], 300)
    m.supp.scan = SCAN[:2]
    m.tick(16)
    expect(m.props[(sv, 'virtual_h')] == 308 and m.props.get((sv, 'yoffset')) == 0, 'the offset moves back into the shorter list')


def life_tests(ctx):
    expect = ctx.expect
    m = page(); opened(m)
    expect(opened(m) == 0 and m.names().count('window_open') == 0, 'a second open leaves the page as it is')
    fn, ctx_ = m.bound[(WIN, O['EVT_DESTROY'])]
    m.call(fn, a0=ctx_, a1=0, count=20000)
    expect(('timer_remove', 0x777) in m.hist, 'the timer ends with the window')
    expect(m.u.mem_read(PSYMS['wp'], 16) == bytes(16) if 'wp' in PSYMS else True, 'the page forgets itself')
    m.hist = []; m.timers = []
    expect(opened(m) == 0 and len(m.timers) == 1 and ('window_open', 'm1plus_wifi') in m.hist, 'and can open again')
    # a stale destroy of an earlier window leaves a newer page alone
    m = page(); opened(m)
    m.call(fn, a0=0x1234, a1=0, count=20000)
    expect(not any(c[0] == 'timer_remove' for c in m.hist[-3:]), 'the end of another window is not this page\'s')
    # a window that will not open: -1, nothing was bound, nothing to undo
    m = page(); m.windows = {'m1plus_wifi': 0}
    expect(opened(m) == -1 and not m.timers and 'navigator_back' not in m.hist and not any(c[0] == 'widget_on' for c in m.hist), 'no window: -1, so Settings opens the stock page')
    # an asset that is not ours
    m = page(); del m.widgets['wf_row_other']
    expect(opened(m) == -1 and ('navigator_back',) in m.hist and not m.timers, 'a wrong asset: back out, -1')
    m = page(); del m.widgets['wf_lock5']
    expect(opened(m) == -1 and ('navigator_back',) in m.hist, 'a missing row child: back out, -1')
    m = page(); m.timer_fail = True
    expect(opened(m) == -1 and ('navigator_back',) in m.hist, 'no timer: back out, -1')
    # Back and Now Playing are the stock ones
    m = page(); opened(m)
    expect(m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])][0] == PSYMS['pod_on_back'] and m.bound[(m.widgets['btn_backtoplayer'], O['EVT_CLICK'])][0] == PSYMS['pod_on_player'], 'Back and Now Playing')
    # no card, no files: SAVE_CONFIG failing leaves the network usable
    m = page(); opened(m); m.supp.failed = {'SAVE_CONFIG'}; m.supp.log = []
    m.tap(f'wf_row{m.idx("Cafe Open")}')
    expect('SELECT_NETWORK 1' in m.cmds() and m.fs[WF_CONF].decode().count('network={') == 1 and not m.toasts(), 'a save that fails still selects the network (it is used until the supplicant restarts)')


def hub_tests(ctx):
    """The Wi-Fi row of the stock All System Settings hub (payload hook 21, tools/pod.py WIFIHUB_SITE, patch/wifipage.c wifi_hub_open)."""
    expect = ctx.expect
    import paths
    NAME = 'systemset/wifi_page'
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    site = pod.WIFIHUB_SITE
    expect(site == 0x4b1460 and w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['wifi_hub_open'],
           'the build replaced stock\'s `jalr t9` (navigator_to) at 0x4b1460 by `jal wifi_hub_open`')
    pins = [(a, old) for a, old, what in pod.SETTINGS_PINS if 0x4b1440 <= a <= 0x4b1468]
    expect(len(pins) == 8 and all(w(stock_demo, a) == old and (a == site or w(built, a) == old) for a, old in pins) and w(built, site + 4) == 0x24848f1c,
           'the thunk\'s prologue, GOT loads, the delay slot (a0 = "systemset/wifi_page") and the result are stock\'s')
    expect(MANIFEST['hook_wifihub'] == {'addr': site, 'target': PSYMS['wifi_hub_open']}, 'the manifest records the hook')

    def hub(kill=False, bad=None):
        m = page(); m.cstr_name = NAME
        if kill: m.present.add('/mnt/mmc/m1plus-off')
        if bad == 'window': m.windows = {'m1plus_wifi': 0}
        r = m.call(PSYMS['wifi_hub_open'], a0=m.cstr(NAME), count=30000000)
        return m, struct.unpack('<i', struct.pack('<I', r))[0]
    m, r = hub()
    expect(r == 0 and ('window_open', 'm1plus_wifi') in m.hist and not [c for c in m.calls if c[0] == 'navigator_to'], 'the hub row opens our page, without the stock one')
    m, r = hub(kill=True)
    expect(('window_open', 'm1plus_wifi') not in m.hist and [c for c in m.calls if c[0] == 'navigator_to'] == [('navigator_to', NAME)], 'with the kill switch the stock page opens (the route for WEP)')
    m, r = hub(bad='window')
    expect([c for c in m.calls if c[0] == 'navigator_to'] == [('navigator_to', NAME)] and not m.timers, 'a page that will not open leaves stock\'s call, with its argument')


def files_tests(ctx):
    expect = ctx.expect
    # ours runs on the copy: the split goes to both files
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Safe', 'wpa3 password'); m.tap(f'wf_row{m.idx("Cafe Open")}')
    real, ours = m.fs[WF_CONF].decode(), m.fs[WF_OURS].decode()
    expect(real.count('network={') == 2 and 'ssid="Home"' in real and 'ssid="Cafe Open"' in real and ours.count('network={') == 1 and 'ssid="Safe"' in ours,
           f'two networks saved: the stock one in the stock file, the WPA3 one in ours: {real!r} / {ours!r}')
    writes = [c for c in m.hist if c[0] == 'rename']
    expect([c[2] for c in writes if c[2] in (WF_CONF, WF_OURS)][:2] == [WF_OURS, WF_CONF] and all(c[1] == c[2] + '.tmp' for c in writes if c[2] in (WF_CONF, WF_OURS)),
           'each file is written by temp file and rename, the file of the others first')
    # ours has the stock file itself (no copy): what ours-only networks were saved earlier stay
    m = page(copy=False); m.fs[WF_OURS] = b'network={\n\tssid="Old3"\n\tkey_mgmt=SAE\n\tsae_password="x"\n}\n\n'
    opened(m); m.supp.log = []
    join_pass(m, 'Safe', 'wpa3 password')
    real, ours = m.fs[WF_CONF].decode(), m.fs[WF_OURS].decode()
    expect('Safe' not in real and real.startswith(Supp.HEAD) and ours.count('network={') == 2 and 'ssid="Old3"' in ours and 'ssid="Safe"' in ours, f'no copy: the stock file is cleaned, the ours-only networks of before and now are kept: {ours!r}')
    # an oversize configuration (the supplicant's own file over 12 KB): nothing is written
    m = page(); opened(m)
    m.supp.HEAD = 'ctrl_interface=/var/run/wpa_supplicant\n' + '# pad\n' * 3000
    before = m.fs[WF_CONF]
    m.tap(f'wf_row{m.idx("Cafe Open")}')
    expect(m.fs[WF_CONF] == before and WF_OURS not in m.fs and 'SELECT_NETWORK 1' in m.cmds(), 'a configuration over 12 KB is not split and nothing is written: the network is selected all the same')
    # the files can be rewritten: a failing write is not fatal
    m = page(); opened(m)
    m.fail.add(('write', WF_OURS + '.tmp'))
    m.tap(f'wf_row{m.idx("Cafe Open")}')
    expect('SELECT_NETWORK 1' in m.cmds() and not m.toasts(), 'a write that fails still selects the network')


def review_tests(ctx):
    """Six review findings (docs/modules/wifi.md Known limits): each case is the reproducer of one finding."""
    expect = ctx.expect

    # 1. Auto-Join of the saved networks beyond the page's list of 16 survives a select
    def saved(n, off):
        return [(b'Home', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK'), ('priority', '5')])] + [(f'Saved{i:02d}'.encode(), [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')] + ([('disabled', '1')] if off(i) else [])) for i in range(1, n)]
    for n, name in ((17, 'F1-17'), (40, 'F1-40')):
        supp = Supp(scan=SCAN, known=saved(n, lambda i: i % 4 == 2))
        want = {i: supp.nets[i]['dis'] for i in supp.nets}
        m = page(supp); opened(m); m.tap(f'wf_row{m.idx("Home")}')
        got = {i: supp.nets[i]['dis'] for i in supp.nets if i != 0}
        bad = sorted(i for i in got if got[i] != want[i])
        expect(not bad and supp.cur == 0, f'{name}: {n} saved networks, every fourth Auto-Join off: a select leaves each as it was (changed: {bad})')
    # more than a reply holds: LIST_NETWORKS is read page by page
    supp = Supp(scan=SCAN, known=[(b'Home', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')])] + [(('N%02d' % i).encode() + b'x' * 29, [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')] + ([('disabled', '1')] if i % 3 == 0 else [])) for i in range(1, 100)])
    want = {i: supp.nets[i]['dis'] for i in supp.nets}
    m = page(supp); opened(m); m.tap(f'wf_row{m.idx("Home")}')
    bad = sorted(i for i in supp.nets if i and supp.nets[i]['dis'] != want[i])
    expect(not bad, f'F1-100: 100 saved networks with 32 byte names (a LIST_NETWORKS reply holds {len(supp.handle("LIST_NETWORKS", m).splitlines()) - 1} of them): each keeps its Auto-Join (changed: {len(bad)})')

    # 2. Passwords: a 64 digit raw PSK, a long WPA3 password
    HEX = '0123456789abcdef' * 4
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', HEX, go=False)
    expect(go_state(m) == (1, 'normal'), f'F2-hex: 64 hex digits on the password page enable Join (state {go_state(m)})')
    kclick(m, 'kb_go')
    expect(f'SET_NETWORK 1 psk {HEX}' in m.cmds(), f'F2-hex: and are sent unquoted as the PSK: {m.cmds()[:4]}')
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Sam’s iPhone', HEX[:-1] + 'g', go=False)
    expect(go_state(m) == (0, 'disable'), 'F2-nonhex: 64 characters that are not all hex digits: Join dimmed')
    LONG = ('abcdefghij' * 13)[:127]
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Safe', LONG, go=False)
    expect(go_state(m) == (1, 'normal'), f'F2-sae: a 127 character WPA3 password enables Join (state {go_state(m)})')
    kclick(m, 'kb_go')
    expect(f'SET_NETWORK 1 sae_password "{LONG}"' in m.cmds(), 'F2-sae: and is sent whole')
    m = page(); opened(m); m.supp.log = []
    join_pass(m, 'Safe', LONG + 'k', go=False)
    kclick(m, 'kb_go')
    expect(f'SET_NETWORK 1 sae_password "{LONG}"' in m.cmds() and not any(len(c) > 400 for c in m.cmds()), 'F2-sae: a 128th character is not taken')

    # the Join Wi-Fi Network page takes the same credentials (WPA2/WPA3 with a raw PSK stays WPA-PSK: SAE needs a password)
    m = page(); opened(m); m.tap('wf_row_other'); m.supp.log = []
    kclick(m, f'kb_k{kkeys(m)["H"]}'); ktype(m, 'idden')
    kclick(m, 'kb_go')
    ktype(m, HEX)
    expect(go_state(m) == (1, 'normal'), 'F2-other: 64 hex digits on the Join Wi-Fi Network page enable Join')
    kclick(m, 'kb_go')
    expect(f'SET_NETWORK 1 psk {HEX}' in m.cmds() and 'SET_NETWORK 1 key_mgmt WPA-PSK' in m.cmds(), f'F2-other: sent unquoted, as WPA-PSK: {m.cmds()[:6]}')

    # 3. A full scan table keeps the connected and the saved networks
    scan = [(-30 - i, '[WPA2-PSK-CCMP][ESS]', f'Air{i:02d}'.encode()) for i in range(40)]
    supp = Supp(scan=scan, known=[(b'Away', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')]), (b'Gone1', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')]), (b'Gone2', [('psk', '"secret123"'), ('key_mgmt', 'WPA-PSK')])])
    supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); opened(m); m.tick(16)
    names = [r[0] for r in m.rows()]
    expect(names[:1] == ['Away'] and 'Gone1' in names and 'Gone2' in names, f'F3: 40 scan results, the connected network and two saved ones absent from the scan: all three listed ({names[:4]}, {len(names)} rows)')
    expect('Air00' in names and 'Air28' in names and 'Air29' not in names, 'F3: the strongest unsaved networks stay, the weakest are dropped')

    # 4. Scanning goes on while connected
    supp = Supp(scan=SCAN, known=KNOWN); supp.state, supp.cur, supp.ip = 'COMPLETED', 0, '192.168.1.20'
    m = page(supp); opened(m); m.tick(16)
    m.supp.log = []
    m.tick(60)
    expect(m.cmds().count('SCAN') >= 1, f'F4: connected: a scan every 12 s ({m.cmds().count("SCAN")} in 15 s)')
    m.supp.scan = m.supp.scan + [(-40, '[ESS]', b'Newcomer')]
    m.tick(80)
    expect('Newcomer' in [r[0] for r in m.rows()], 'F4: a network that turns up while connected is listed')

    # 5. A hidden network's name keeps its spaces
    def typ(m, text):
        for c in text:
            if c == ' ': kclick(m, 'kb_space'); continue
            ks = kkeys(m)
            if c not in ks and c.isupper() and c.lower() in ks: kclick(m, 'kb_shift'); ks = kkeys(m)
            if c not in ks: kclick(m, 'kb_mode'); ks = kkeys(m)
            kclick(m, f'kb_k{ks[c]}')
    m = page(); opened(m); m.tap('wf_row_other'); m.supp.log = []
    typ(m, ' Ab  Cd')
    m.tap('wo_hit_sec')
    m.tap('ws_row0'); close_win(m, 'm1plus_wifisec')
    kclick(m, 'kb_go')
    expect(f'SET_NETWORK 1 ssid {b" Ab  Cd".hex()}' in m.cmds(), f'F5: " Ab  Cd" is sent as typed: {[c for c in m.cmds() if "ssid" in c]}')

    # 6. A join whose select fails leaves nothing saved, and a retry makes one entry
    m = page(); opened(m); m.supp.failed = {'SELECT_NETWORK'}
    join_pass(m, 'Safe', 'hunter22')
    files = b''.join(m.fs[f] for f in (WF_CONF, WF_COPY, WF_OURS) if f in m.fs)
    expect(len(m.supp.nets) == 1 and b'Safe' not in files and b'hunter22' not in files, f'F6: SELECT_NETWORK fails: the new network is removed and neither file keeps it ({len(m.supp.nets)} networks)')
    m2 = page(); opened(m2); m2.supp.failed = {'SELECT_NETWORK'}
    join_pass(m2, 'Safe', 'hunter22')
    m2.supp.failed = set()
    m2.tap(f'wf_row{m2.idx("Safe")}')
    ktype(m2, 'hunter22'); kclick(m2, 'kb_go')
    ssids = [n['ssid'] for n in m2.supp.nets.values()]
    expect(ssids.count(b'Safe') == 1, f'F6: after a retry there is exactly one entry for the name ({ssids.count(b"Safe")})')


SECTIONS = [text_tests, security_tests, scan_tests, split_tests, ctrl_tests, asset_tests, layout_tests, action_tests, pass_tests, other_tests, info_tests, switch_tests, timer_tests, life_tests, hub_tests, files_tests, review_tests]


def run(ctx):
    for s in SECTIONS: s(ctx)

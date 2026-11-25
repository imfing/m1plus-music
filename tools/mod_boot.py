#!/usr/bin/env python3
"""Boot logo, curly quotes and settings-page transitions (asset-only, no binary patch). docs/ui.md

  logo     the boot splash: S11logo_display_shell runs display_logo on images/xx/logo.jpg, or on
           logo180.jpg when /mnt/data/config.ini has ROTATEMODE=1 (screen turned 180 degrees). Both
           are upright 320x480 baseline JPEGs; nothing else on the rootfs reads them. Replaced by
           assets/boot-logo.jpg and assets/boot-logo180.jpg (tools/boot_logo.py renders them from
           assets/boot-logo.svg), whose frame headers are checked first (q2-pod's jpeg_size checks).
  card     the stock S11logo_display_shell (pinned) is replaced by assets/S11logo_display_shell: it
           shows /mnt/data/m1plus/boot-logo.jpg (boot-logo180.jpg when rotated) when present, and in
           the background imports the card's /boot-logo.jpg there with the stock ffmpeg.
  quotes   default.ttf ("微软雅黑+Arial") gives U+2018/2019/201C/201D the CJK em advance (256 of
           256 units, against 48 for ' and 90 for "), so "Paul’s" shows a wide gap. As in q2-pod
           1.0.4, the Unicode cmap now maps them to the straight ASCII glyphs. Done in pure Python:
           the one format-4 subtable gets four one-codepoint segments, every other table keeps its
           bytes (the tables after cmap move by 48 bytes), and the result is checked with a port of
           stb_truetype's own format-4 lookup (the AWTK font backend here) for every BMP codepoint.
           If default.ttf is no longer stock but every curly quote is mapped and narrower than half an
           em (the font-inter step, tools/mod_font.py, ran first), the remap is skipped.
  anim     the settings pages (ui/systemset/*.bin windows) open sliding in from the right and slide
           back out on Back: open_anim_hint / close_anim_hint = slide_left(duration=200,easing=cubic_out),
           the animator and easing the stock lock screen already uses (screensaver_page close_anim_hint).
           System Update (fwupdate_page) and online update (fwdownload_page) stay stock: they are the
           way back from a bad build.

Usage: mod_boot.py SRC_WORKDIR OUT_WORKDIR
  OUT_WORKDIR == SRC_WORKDIR edits in place.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modlib import clone_workdir, edit_ui, write_keep_mode, sha256

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = 'rootfs/release/assets/default/raw/images/xx'
# stock file -> (stock sha256, replacement in assets/)
LOGOS = {f'{IMAGES}/logo.jpg':    ('8875337c5b522e6bf4b80bdf131811929460820dedbb1c8d6adf298da57f9f42', 'boot-logo.jpg'),
         f'{IMAGES}/logo180.jpg': ('b4eb7ff15878ac85ae4411d547fb533f0c5c93294768d33650b7ce3f7c88787f', 'boot-logo180.jpg')}
LOGO_SIZE = (320, 480)          # stock: upright portrait, the panel's own orientation; display_logo does not scale
INIT = 'rootfs/etc/init.d/S11logo_display_shell'
INIT_SHA = '7deb9c95aae3d3d988a22b79bcffbf5b3c42d883f7cabf100348fe69ce93cfcb'
INIT_SRC = os.path.join(ROOT, 'assets', 'S11logo_display_shell')
FONT = 'rootfs/release/assets/default/raw/fonts/default.ttf'
FONT_SHA = '9a16af0aead992a2ad64f86d0de8d38bea60d6f605d42ffd0501684666161872'
QUOTES = {0x2018: 0x27, 0x2019: 0x27, 0x201c: 0x22, 0x201d: 0x22}   # as q2-pod tools/build.py
ANIM = 'slide_left(duration=200,easing=cubic_out)'                   # stock screensaver_page's close_anim_hint
ANIM_DIRS = ('rootfs/release/assets/default/raw/ui/systemset',)
ANIM_SKIP = ('fwupdate_page.bin', 'fwdownload_page.bin')

def check(ok, msg):
    if not ok: raise SystemExit(f'mod_boot: {msg}')

# ---- logo ---------------------------------------------------------------------------------------

def jpeg_size(b):
    """Frame-header check of a splash JPEG, returns (w, h). The same check as q2-pod's
    tools/build.py jpeg_size: display_logo indexes libjpeg's output as RGB triples, so only an 8-bit,
    three-component baseline (SOF0) JPEG is safe; grayscale, CMYK and progressive are refused."""
    check(b[:2] == b'\xff\xd8', 'logo must be a JPEG')
    i = 2
    while i < len(b):
        check(b[i] == 0xFF, 'malformed JPEG')
        while i < len(b) and b[i] == 0xFF: i += 1
        check(i < len(b), 'truncated JPEG marker')
        marker = b[i]; i += 1
        if marker in (0xD9, 0xDA): break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7: continue
        check(marker not in (0, 0xD8), 'malformed JPEG marker')
        check(i + 2 <= len(b), 'truncated JPEG segment')
        size = struct.unpack_from('>H', b, i)[0]
        check(size >= 2 and i + size <= len(b), 'invalid JPEG segment length')
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            check(size >= 8 and size == 8 + 3 * b[i + 7], 'invalid JPEG frame length')
            check(marker == 0xC0 and b[i + 2] == 8 and b[i + 7] == 3,
                  'logo must be an 8-bit, three-component baseline JPEG (not progressive/grayscale/CMYK)')
            h, w = struct.unpack_from('>HH', b, i + 3)
            check(w > 0 and h > 0, 'invalid JPEG dimensions')
            return w, h
        i += size
    raise SystemExit('mod_boot: no JPEG frame header')

def apply_logo(work, logo, logo180):
    for (rel, (stock_sha, _)), src in zip(LOGOS.items(), (logo, logo180)):
        p = os.path.join(work, rel)
        check(sha256(open(p, 'rb').read()) == stock_sha, f'{rel} is not the stock V2.1 file')
        new = open(src, 'rb').read()
        check(jpeg_size(new) == LOGO_SIZE, f'{src}: must be {LOGO_SIZE[0]}x{LOGO_SIZE[1]} like the stock splash')
        check(new.endswith(b'\xff\xd9'), f'{src}: no JPEG end marker')
        write_keep_mode(p, new)
        print(f'logo: {rel} <- {os.path.relpath(src, ROOT)} ({len(new)} bytes, sha256 {sha256(new)[:16]})')

def apply_init(work):
    p = os.path.join(work, INIT)
    check(sha256(open(p, 'rb').read()) == INIT_SHA, f'{INIT} is not the stock V2.1 file')
    write_keep_mode(p, open(INIT_SRC, 'rb').read())
    print(f'card: {INIT} <- {os.path.relpath(INIT_SRC, ROOT)}')

# ---- curly quotes -------------------------------------------------------------------------------

def tables(d):
    """tag -> (directory entry offset, checksum, offset, length)"""
    n = struct.unpack_from('>H', d, 4)[0]
    return {d[12 + 16 * i:16 + 16 * i]: (12 + 16 * i, *struct.unpack_from('>III', d, 16 + 16 * i)) for i in range(n)}

def checksum(b):
    b += b'\0' * (-len(b) % 4)
    return sum(struct.unpack(f'>{len(b) // 4}I', b)) & 0xFFFFFFFF

def fmt4_parse(d, o):
    seg = struct.unpack_from('>H', d, o + 6)[0] // 2
    length = struct.unpack_from('>H', d, o + 2)[0]
    ends = struct.unpack_from(f'>{seg}H', d, o + 14)
    starts = struct.unpack_from(f'>{seg}H', d, o + 16 + 2 * seg)
    deltas = struct.unpack_from(f'>{seg}H', d, o + 16 + 4 * seg)
    ros = struct.unpack_from(f'>{seg}H', d, o + 16 + 6 * seg)
    gids = struct.unpack_from(f'>{(length - 16 - 8 * seg) // 2}H', d, o + 16 + 8 * seg)
    # segment: (start, end, delta, glyphIdArray index of `start` or None for idDelta segments)
    segs = [(s, e, dl, (ro // 2 + i - seg) if ro else None) for i, (s, e, dl, ro) in enumerate(zip(starts, ends, deltas, ros))]
    return segs, gids

def fmt4_build(language, segs, gids):
    n = len(segs); sel = n.bit_length() - 1; srange = 2 << sel
    out = struct.pack('>HHHHHHH', 4, 16 + 8 * n + 2 * len(gids), language, 2 * n, srange, sel, 2 * n - srange)
    out += struct.pack(f'>{n}H', *(e for _, e, _, _ in segs)) + b'\0\0'
    out += struct.pack(f'>{n}H', *(s for s, _, _, _ in segs)) + struct.pack(f'>{n}H', *(dl for _, _, dl, _ in segs))
    out += struct.pack(f'>{n}H', *((2 * (n - i + k) if k is not None else 0) for i, (_, _, _, k) in enumerate(segs)))
    out += struct.pack(f'>{len(gids)}H', *gids)
    check(len(out) < 0x10000, 'cmap format 4 subtable too large')
    return out

def fmt4_map(segs, gids):
    """Every codepoint -> glyph, decoded segment by segment (the reference)."""
    m = {}
    for s, e, dl, k in segs:
        for c in range(s, e + 1):
            if k is None: m[c] = (c + dl) & 0xFFFF
            else:
                j = k + c - s
                g = gids[j] if 0 <= j < len(gids) else 0
                m[c] = (g + dl) & 0xFFFF if g else 0
    return m

def stb_lookup(d, o, c):
    """stbtt_FindGlyphIndex, format 4 branch, line for line (it trusts searchRange/entrySelector/rangeShift)."""
    u = lambda a: struct.unpack_from('>H', d, a)[0]
    segcount, srange, sel, rshift = u(o + 6) >> 1, u(o + 8) >> 1, u(o + 10), u(o + 12) >> 1
    end_count = o + 14
    if c > 0xffff: return 0
    search = end_count
    if c >= u(search + rshift * 2): search += rshift * 2
    search -= 2
    while sel:
        srange >>= 1
        if c > u(search + srange * 2): search += srange * 2
        sel -= 1
    search += 2
    item = (search - end_count) >> 1
    start = u(o + 14 + segcount * 2 + 2 + 2 * item); last = u(end_count + 2 * item)
    if c < start or c > last: return 0
    offset = u(o + 14 + segcount * 6 + 2 + 2 * item)
    if offset == 0: return (c + struct.unpack_from('>h', d, o + 14 + segcount * 4 + 2 + 2 * item)[0]) & 0xFFFF
    return u(offset + (c - start) * 2 + o + 14 + segcount * 6 + 2 + 2 * item)

def unicode_fmt4(d, cmap_off):
    """Offsets (relative to cmap) of the format-4 subtables stb_truetype can pick: platform 0, or 3/1, 3/10."""
    n = struct.unpack_from('>H', d, cmap_off + 2)[0]
    recs = [struct.unpack_from('>HHI', d, cmap_off + 4 + 8 * i) for i in range(n)]
    subs = sorted({off for pid, eid, off in recs if pid == 0 or (pid == 3 and eid in (1, 10))})
    for off in subs: check(struct.unpack_from('>H', d, cmap_off + off)[0] == 4, 'unexpected Unicode cmap format')
    return recs, subs

def fix_quotes(d):
    t = tables(d)
    _, _, cmap_off, cmap_len = t[b'cmap']
    recs, subs = unicode_fmt4(d, cmap_off)
    check(len(subs) == 1, f'expected one shared Unicode cmap subtable, found {len(subs)}')
    sub = cmap_off + subs[0]
    sub_len = struct.unpack_from('>H', d, sub + 2)[0]
    segs, gids = fmt4_parse(d, sub)
    old_map = fmt4_map(segs, gids)
    for c in range(0x10000): check(stb_lookup(d, sub, c) == old_map.get(c, 0), f'stock cmap: stb lookup disagrees at U+{c:04X}')
    for q, a in QUOTES.items(): check(old_map.get(q) and old_map.get(a), 'font without curly or straight quotes')
    new_segs = []
    for s, e, dl, k in segs:     # split the segments holding a quote; each quote gets its own idDelta segment
        cuts = sorted(q for q in QUOTES if s <= q <= e)
        lo = s
        for q in cuts + [None]:
            hi = e if q is None else q - 1
            if lo <= hi: new_segs.append((lo, hi, dl, None if k is None else k + lo - s))
            if q is None: break
            new_segs.append((q, q, (old_map[QUOTES[q]] - q) & 0xFFFF, None)); lo = q + 1
    language = struct.unpack_from('>H', d, sub + 4)[0]
    new_sub = fmt4_build(language, new_segs, gids)
    grow = len(new_sub) - sub_len
    check(grow % 4 == 0, 'cmap growth not 4-byte aligned')
    # cmap: header + records (offsets past the subtable move), subtable, rest unchanged
    hdr = bytearray(d[cmap_off:cmap_off + 4 + 8 * len(recs)])
    for i, (pid, eid, off) in enumerate(recs):
        if off > subs[0]: struct.pack_into('>I', hdr, 4 + 8 * i + 4, off + grow)
    check(subs[0] >= len(hdr) and all(off == subs[0] or off >= subs[0] + sub_len for _, _, off in recs), 'unexpected cmap layout')
    new_cmap = bytes(hdr) + d[cmap_off + len(hdr):sub] + new_sub + d[sub + sub_len:cmap_off + cmap_len]
    # file: everything after cmap moves by `grow` (cmap was padded to 4 like every table)
    end = cmap_off + cmap_len + (-cmap_len % 4)
    check(all(off < cmap_off or off >= end for tag, (_, _, off, _) in t.items() if tag != b'cmap'), 'unexpected table layout')
    out = bytearray(d[:cmap_off] + new_cmap + b'\0' * (-len(new_cmap) % 4) + d[end:])
    for tag, (ent, _, off, ln) in t.items():
        if tag == b'cmap': struct.pack_into('>III', out, ent + 4, checksum(new_cmap), cmap_off, len(new_cmap))
        elif off > cmap_off: struct.pack_into('>I', out, ent + 8, off + grow)
    head = t[b'head'][2]
    struct.pack_into('>I', out, head + 8, 0)
    struct.pack_into('>I', out, head + 8, (0xB1B0AFBA - checksum(bytes(out))) & 0xFFFFFFFF)
    out = bytes(out)
    # verify: the AWTK (stb_truetype) lookup on the written font gives the stock glyph for every
    # codepoint except the four quotes; every other table is byte-identical; checksums hold
    nt = tables(out); nsub = nt[b'cmap'][2] + subs[0]
    for c in range(0x10000):
        want = old_map[QUOTES[c]] if c in QUOTES else old_map.get(c, 0)
        check(stb_lookup(out, nsub, c) == want, f'patched cmap: U+{c:04X} -> {stb_lookup(out, nsub, c)}, want {want}')
    for tag, (_, cs, off, ln) in t.items():
        _, ncs, noff, nln = nt[tag]
        if tag not in (b'cmap', b'head'): check(out[noff:noff + nln] == d[off:off + ln] and ncs == cs, f'{tag} changed')
        check(checksum(out[noff:noff + nln] if tag != b'head' else out[noff:noff + 8] + b'\0' * 4 + out[noff + 12:noff + nln]) == ncs, f'{tag} checksum')
    check(out[head:head + 8] + out[head + 12:head + 54] == d[head:head + 8] + d[head + 12:head + 54], 'head changed')
    check(checksum(out) == 0xB1B0AFBA, 'file checksum')
    return out, len(segs), len(new_segs)

def quote_advances(d):
    """{curly quote: (advance, unitsPerEm)} as stb_truetype sees the font."""
    t = tables(d)
    upem = struct.unpack_from('>H', d, t[b'head'][2] + 18)[0]
    nhm = struct.unpack_from('>H', d, t[b'hhea'][2] + 34)[0]
    _, subs = unicode_fmt4(d, t[b'cmap'][2])
    sub = t[b'cmap'][2] + subs[-1]
    adv = lambda g: struct.unpack_from('>H', d, t[b'hmtx'][2] + 4 * min(g, nhm - 1))[0]
    return {q: (adv(stb_lookup(d, sub, q)) if stb_lookup(d, sub, q) else None, upem) for q in QUOTES}

def apply_quotes(work):
    p = os.path.join(work, FONT)
    d = open(p, 'rb').read()
    if sha256(d) != FONT_SHA:
        # A font that already has typographic quotes (the font-inter step, tools/mod_font.py, ran first)
        # must keep them: skip, but only if every curly quote is mapped and narrower than half an em.
        adv = quote_advances(d)
        check(all(a is not None and a < u // 2 for a, u in adv.values()),
              f'{FONT} is neither the stock V2.1 font nor one with proportional curly quotes')
        print('quotes: skipped, default.ttf is not stock and already has proportional curly quotes ('
              + ', '.join(f'U+{q:04X} {a}/{u}' for q, (a, u) in adv.items()) + ' units)')
        return
    out, n0, n1 = fix_quotes(d)
    write_keep_mode(p, out)
    print(f'quotes: {FONT} {len(d)} -> {len(out)} bytes; cmap format 4 {n0} -> {n1} segments; '
          + ', '.join(f'U+{q:04X} -> U+{a:04X}' for q, a in QUOTES.items()))

# ---- settings transitions -----------------------------------------------------------------------

def apply_anim(work):
    n = 0
    for rel in ANIM_DIRS:
        d = os.path.join(work, rel)
        for f in sorted(os.listdir(d)):
            if not f.endswith('.bin') or f in ANIM_SKIP: continue
            def edit(root):
                check(root.type == 'window', f'{rel}/{f}: not a window')
                check(not any('anim' in k for k, _ in root.props), f'{rel}/{f}: already has an animation property')
                root.set('open_anim_hint', ANIM); root.set('close_anim_hint', ANIM)
            edit_ui(os.path.join(d, f), edit); n += 1
    print(f'anim: open/close_anim_hint {ANIM} on {n} settings windows (skipped {", ".join(ANIM_SKIP)})')

def main():
    if len(sys.argv) != 3: sys.exit(__doc__)
    src, out = sys.argv[1:]
    clone_workdir(src, out)
    apply_logo(out, os.path.join(ROOT, 'assets', LOGOS[f'{IMAGES}/logo.jpg'][1]), os.path.join(ROOT, 'assets', LOGOS[f'{IMAGES}/logo180.jpg'][1]))
    apply_init(out)
    apply_quotes(out)
    apply_anim(out)

if __name__ == '__main__': main()

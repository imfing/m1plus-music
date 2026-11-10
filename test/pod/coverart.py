"""Album cover extraction with our own resize (patch/covercache.c art_embedded / art_folder, patch/pccover.c pv_cover; docs/modules/coverflow.md "Cover resampling"): the cache worker takes the
embedded picture (taglib_album_picture, as stock's toolsGetAlbumCover does) or the folder image (stock's choice, reproduced), decodes it at libjpeg's DCT scale (or through the streaming PNG
decoder) and writes the output size stock's resize would, by an exact area average. The compiled payload runs under Unicorn; libjpeg is the PIL mock of test/pod/pcnet.py, which decodes at the
scale it is asked and records it. Every failure must hand the same album to the stock call."""
import importlib.util, io, os, re, struct, sys, zlib
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCN = sibling('pcnet')
ART = O['ART_SIZE']
TMP = '/tmp/.tmp_picture'
PRIV = '/tmp/.m1plus_art'
INFLIGHT = '/mnt/mmc/.m1plus/covers/.inflight'
DIR = '/mnt/mmc/Music/Album'
TRACK = f'{DIR}/song.flac'
KEY = 0x1234abcd


class CM(PCN.NM):
    """The card machine with what the extraction reads that the podcast one does not mock: d_type in readdir (files 8, folders 4) and ftell over the file's bytes."""
    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'readdir' and a0 in self.dh:
            d = self.dh[a0]
            if d[1] < len(d[0]):
                nm = d[0][d[1]]; d[1] += 1
                files = {p.rsplit('/', 1)[1] for p in self.fs}
                self.u.mem_write(self.dent, bytes(300)); self.u.mem_write(self.dent + 10, bytes([8 if nm in files else 4]) + nm.encode('latin-1') + b'\0'); ret = self.dent
            else: ret = 0
        elif name == 'fwrite' and a3 in self.fp:   # the bytes land in the card dict, so a test can read the record
            path = self.fp[a3][0]; data = bytes(u.mem_read(a0, a1 * a2)); self.fs[path] = self.fs.get(path, b'') + data; self.calls.append(('fwrite', path, data)); ret = a2
        elif name == 'ftell' and a0 in self.fp:
            ret = self.fp[a0][1]
        elif name == 'fopen' and 'w' in self.read_cstr(u.reg_read(UC_MIPS_REG_A1)) and self.read_cstr(a0).startswith('/tmp/'):   # the pane's file in RAM, written like the card's
            path = self.read_cstr(a0); self.calls.append(('fopen', path, 'wb')); self.fs[path] = b''; ret = self.alloc(4); self.fp[ret] = [path, 0]
        if ret is not None:
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


def machine():
    m = CM()
    m.dirs.update({'/mnt/mmc/.m1plus', '/tmp'})
    m.folder(DIR)
    m.put(TRACK, b'x')
    return m


def f32(v): return struct.unpack('<f', struct.pack('<f', v))[0]


def fit(w, h, t):
    """Stock's fit (0x5e00bc) in single precision: None when the picture is kept as it is."""
    if w >= h:
        if t < w: return t, max(1, int(f32(h / f32(f32(w) / f32(t)))))
        return (t, t) if w == t else None
    if t < h: return max(1, int(f32(w / f32(f32(h) / f32(t))))), t
    return (t, t) if h == t else None


def picture(w, h, mode='RGB', fmt='JPEG', **kw):
    """A test picture with bands, a chequer and a ring (mid frequencies: the JPEG round trip and PIL's box resize stay close to an exact area average)."""
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (w, h))
    dr = ImageDraw.Draw(im)
    for x in range(0, w, 40): dr.rectangle([x, 0, x + 19, h], fill=(x * 255 // w, 255 - x * 255 // w, 128))
    for y in range(0, h, 30):
        for x in range(0, w, 30):
            if (x // 30 + y // 30) % 2: dr.rectangle([x, y, x + 14, y + 14], fill=(250, 250, 40))
    dr.ellipse([w // 4, h // 4, w * 3 // 4, h * 3 // 4], outline=(0, 0, 0), width=max(6, w // 40))
    b = io.BytesIO()
    im.convert(mode).save(b, fmt, **kw)
    return b.getvalue(), decoded(b.getvalue()).convert('RGB')   # (the reference is what the file holds, not the picture before its lossy save)


def build(m, track=TRACK, key=KEY):
    """The cache worker on one job, as the shared builder runs it; the cache file's bytes or None."""
    m.thread = None
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    assert m.call(PSYMS['cc_build_add'], a0=m.cstr(track), a1=key, count=1 << 40) == 1
    assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
    try:
        m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    except Exception:
        print('PC', hex(m.u.reg_read(UC_MIPS_REG_PC)), 'RA', hex(m.u.reg_read(UC_MIPS_REG_RA)), sorted((v, k) for k, v in PSYMS.items() if v <= m.u.reg_read(UC_MIPS_REG_RA))[-2:]); raise
    calls = m.calls   # (every call() starts the log again: the worker's is the one that counts)
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m.calls = calls
    return m.fs.get(art_file(key))


def decoded(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data)); im.load()
    return im


def close_to(got, ref_im, tol=3.0):
    """The cover against PIL's box resize of the original to the same size: the mean absolute difference."""
    from PIL import ImageChops
    from PIL import Image
    ref = ref_im.resize(got.size, Image.BOX)
    small = (max(1, got.size[0] // 6), max(1, got.size[1] // 6))   # compared after a 6 : 1 reduction: hard edges move by a pixel with the DCT scale and the JPEG round trip, tones do not
    got, ref = got.convert('RGB').resize(small, Image.BOX), ref.resize(small, Image.BOX)
    px = [v for p in ImageChops.difference(got.convert('RGB'), ref).getdata() for v in p]
    return sum(px) / len(px) <= tol, f'mean {sum(px) / len(px):.2f}'


def inflight_text(key, track=TRACK):
    return f'm1plus cover 1\nkey: {key:08x}\nbuild: TAG\ntrack: {track}\nend\n'.encode()


def record(data):
    """A record's lines as (name, value) pairs; the build tag is replaced by TAG (it is the compiler's -D)."""
    lines = data.decode('latin-1').split('\n')
    assert lines[-1] == '', 'ends with a newline'
    return [('head', lines[0])] + [tuple(l.split(': ', 1)) if ': ' in l else (l, '') for l in lines[1:-1]]


def build_of(data): return re.search(rb'build: (\S+)\n', data).group(1)


def cbw(m, i): return m.word(PSYMS['cb'] + 4 * i)   # a word of the builder's state: running 4, orphan 9


def bad_file(key): return art_file(key) + '.bad'


def try_file(key): return art_file(key) + '.try'


def cbf(m, name): return build_state(m)[name]   # a field of the builder's state by name


def setcb(m, name, v): m.setword(PSYMS['cb'] + 4 * list(build_state(m)).index(name), v)


class Worker:
    """The cache worker's thread as a saved CPU context on its own stack, so a test can pause it (emu_stop from a hook), run the UI thread's poll, and resume it."""
    def __init__(self, m):
        self.m, self.done = m, False
        for r, v in ((UC_MIPS_REG_SP, STACK - 0x10000), (UC_MIPS_REG_RA, RET), (UC_MIPS_REG_T9, m.thread[0]), (UC_MIPS_REG_A0, m.thread[1]), (UC_MIPS_REG_PC, m.thread[0])):
            m.u.reg_write(r, v & 0xffffffff)
        self.ctx = m.u.context_save()

    def go(self, until=None, at_lock=None):
        """Run until the worker returns, or until `until()` holds after one of its job-state mutex releases (`at_lock()`: as it takes that mutex)."""
        m = self.m
        m.on_cb_lock = (lambda: at_lock() and m.u.emu_stop()) if at_lock else None
        m.on_cb_unlock = (lambda: until() and m.u.emu_stop()) if until else None
        m.u.context_restore(self.ctx)
        m.limit, m._icount = 1 << 40, 0
        m.u.emu_start(m.u.reg_read(UC_MIPS_REG_PC), RET)
        self.ctx, self.done = m.u.context_save(), m.u.reg_read(UC_MIPS_REG_PC) == RET
        m.on_cb_unlock = m.on_cb_lock = None


def stock_calls(m): return [c[0] for c in m.calls if c[0] in ('toolsGetAlbumCover', 'toolsGetExternCover')]


def run(ctx):
    expect = ctx.expect
    lock = pod.DATA['PARSE_COVER_MUTEX'][0]

    # 1. An embedded JPEG: taglib asked as stock asks it, the picture read from /tmp/.tmp_picture (and removed), decoded at the smallest DCT scale that keeps both sides, written at stock's size
    #    and quality under parse_cover_mutex; no stock art call; the file named for the new sampling (r), the old name never written.
    data, im = picture(1500, 1000)
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    out = build(m)
    expect(out is not None and decoded(out).size == fit(750, 500, ART) == (ART, 112), f'a 1500 x 1000 cover is written at stock\'s size (168 x 112): {decoded(out).size if out else None}')
    expect(('scale', 8, (188, 125)) in m.jlog and ('encoded', (ART, 112), 90) in m.jlog, f'decoded at 1/8 (188 x 125 still has both sides), encoded at quality 90 ({[e for e in m.jlog if isinstance(e, tuple)]})')
    expect(('taglib_album_picture', TRACK, art_file(KEY) + '.tmp', 0x100000, 0x600000) in m.calls, 'taglib_album_picture is called as toolsGetAlbumCover calls it')
    expect(not stock_calls(m), 'no stock art call when ours succeeds')
    seq = [c[0] for c in m.calls if c[0] in ('lock', 'taglib_album_picture', 'unlink', 'rename', 'unlock')]
    expect(seq[:4] == ['lock', 'taglib_album_picture', 'rename', 'unlock'] and ('lock', lock) in m.calls and seq[-1] == 'rename',
           f'taglib and the move of /tmp/.tmp_picture happen under parse_cover_mutex, the decode after it ({seq})')
    expect(TMP not in m.fs and art_file(KEY) in m.fs and art_file(KEY).replace('/r', '/') not in m.fs, 'the temporary picture is gone; the file has the r name, the old name is not written')
    ok, why = close_to(decoded(out), im, 6.0)
    expect(ok, f'the cover is the area average of the picture, near PIL\'s box resize ({why})')
    expect(m.jlog.count('create_decompress') == m.jlog.count('destroy_decompress') == 1 and m.jlog.count('create_compress') == m.jlog.count('destroy_compress') == 1, 'every libjpeg object is destroyed')

    # 2. The other shapes: portrait, square (the scale keeps both sides), a gray one (stock always takes its scaled path), a picture over 4096 on a side, progressive.
    for w, h, kw, den, what in ((800, 1200, {}, 4, 'portrait'), (600, 600, {}, 2, 'square 600'), (1024, 1024, {}, 4, '1024 square (stock decodes it whole)'), (3000, 2000, {}, 8, '3000 x 2000'),
                                (1500, 1500, {'progressive': True}, 8, 'progressive')):
        data, im = picture(w, h, **kw)
        m = machine(); m.taglib_kind, m.taglib_data = 2, data
        out = build(m)
        sw, sh = ((w + 1) // 2, (h + 1) // 2) if max(w, h) > 1024 and max(w, h) <= 2048 else (w, h)
        sw, sh = ((w + 3) // 4, (h + 3) // 4) if 2048 < max(w, h) <= 4096 else (sw, sh)
        want = fit(sw, sh, ART)
        expect(out is not None and decoded(out).size == want, f'{what}: written at stock\'s size {want} ({decoded(out).size if out else None})')
        expect([e for e in m.jlog if isinstance(e, tuple) and e[0] == 'scale'][0][1] == den, f'{what}: DCT scale 1/{den} ({[e for e in m.jlog if isinstance(e, tuple) and e[0] == "scale"]})')
        if out: ok, why = close_to(decoded(out), im, 6.0); expect(ok, f'{what}: close to the box resize ({why})')
    data, im = picture(900, 700, mode='L')
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    out = build(m)
    expect(out is not None and decoded(out).size == fit(450, 350, ART) and decoded(out).mode == 'RGB', f'a gray JPEG: stock\'s size from its 1/2 decode, written as colour ({decoded(out).size if out else None})')

    # 3. Stock's quirk: a picture exactly as wide as the request and shorter is stretched to a square; one smaller than the request is not touched (stock copies it): the stock call runs.
    data, im = picture(ART, 100)
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    out = build(m)
    expect(out is not None and decoded(out).size == (ART, ART) and not stock_calls(m), 'a picture exactly 168 wide and 100 tall is stretched to 168 x 168, as stock does')
    for w, h in ((150, 150), (100, 167), (167, 100)):
        data, im = picture(w, h)
        m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, data, 1
        build(m)
        expect(stock_calls(m) == ['toolsGetAlbumCover'] and 'create_compress' not in m.jlog, f'a {w} x {h} picture is stock\'s (it keeps it as it is): the stock call, no encoder of ours')

    # 4. PNG: embedded (kind 1), the streaming decoder, the same size rule; an interlaced PNG is stock's
    data, im = picture(420, 300, fmt='PNG')
    m = machine(); m.taglib_kind, m.taglib_data = 1, data
    out = build(m)
    expect(out is not None and decoded(out).size == fit(420, 300, ART) and 'create_decompress' not in m.jlog and not stock_calls(m), f'an embedded PNG is shrunk through the streaming decoder ({decoded(out).size if out else None})')
    if out: ok, why = close_to(decoded(out), im, 6.0); expect(ok, f'the PNG cover is close to the box resize ({why})')
    from PIL import Image
    il = io.BytesIO(); Image.new('RGB', (300, 300), (9, 9, 9)).save(il, 'PNG'); il = bytearray(il.getvalue())
    il[28] = 1   # IHDR interlace method: Adam7 (the data is then not decodable in one pass, whatever it holds; the CRC is not checked first)
    il[29:33] = struct.pack('>I', zlib.crc32(bytes(il[12:29])))
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 1, bytes(il), 1
    build(m)
    expect(stock_calls(m) == ['toolsGetAlbumCover'], 'an interlaced PNG is stock\'s')

    # 5. Every failure is stock's: a truncated JPEG, libjpeg failing at a stage, the output file refused, a picture taglib reports but did not save.
    data, im = picture(1200, 800)
    cases = (('a truncated JPEG', dict(data=data[:6000]), {}), ('libjpeg failing at the header', dict(), {'jfail': {'read_header'}}), ('libjpeg failing at a row', dict(), {'jfail': {'read:20'}}),
             ('a refused output file', dict(), {'refuse': True}), ('a write error', dict(), {'jfail': {'write:5'}}), ('no saved picture', dict(data=None), {}), ('garbage', dict(data=b'\xff\xd8\xff\xe0' + b'\0' * 100), {}))
    for what, over, opt in cases:
        m = machine(); m.taglib_kind, m.album_cover = 2, 1
        m.taglib_data = over.get('data', data) if 'data' in over else data
        m.jinit(); m.jfail = opt.get('jfail', set())
        if opt.get('refuse'): m.fail.add(('fopen', art_file(KEY) + '.tmp'))
        out = build(m)
        expect(stock_calls(m)[:1] == ['toolsGetAlbumCover'] and m.jlog.count('create_decompress') == m.jlog.count('destroy_decompress') and m.jlog.count('create_compress') == m.jlog.count('destroy_compress'),
               f'{what}: the stock call is made, every libjpeg object destroyed ({stock_calls(m)})')
        expect(TMP not in m.fs and not [p for p in m.fs if p.endswith('.tmp')] or what == 'a refused output file', f'{what}: no temporary file left behind')

    # 6. No embedded picture: taglib says 0, stock's embedded call is not made (it would ask taglib again); the folder is looked at.
    data, im = picture(900, 900)
    m = machine(); m.taglib_kind = 0; m.extern_cover = 1
    build(m)
    expect(stock_calls(m) == ['toolsGetExternCover'] and any(c[0] == 'opendir' and c[1] == DIR for c in m.calls), 'no embedded art: the folder is scanned, stock\'s folder call follows an empty folder, stock\'s embedded call is skipped')
    sq, sq_im = picture(800, 800)        # (168, 168)
    wd, wd_im = picture(700, 500)        # (168, 120)
    tl, tl_im = picture(500, 700)        # (120, 168)
    pn, pn_im = picture(640, 480, fmt='PNG')   # (168, 126)
    sizes = {'sq': fit(800, 800, ART), 'wd': fit(700, 500, ART), 'tl': fit(500, 700, ART), 'pn': fit(640, 480, ART)}

    def folder(files, **kw):
        m = machine(); m.taglib_kind = 0
        for k, v in kw.items(): setattr(m, k, v)
        for name, data in files.items(): m.put(f'{DIR}/{name}', data)
        out = build(m)
        return m, (decoded(out).size if out else None)

    # stock's order: <track>.jpeg, .jpg, .png, cover.jpeg, .jpg, .png, folder.jpeg, .jpg, .png (the later of its nine names goes to the front last), then the rest in readdir order
    m, got = folder({'cover.jpg': sq, 'folder.jpg': wd})
    expect(got == sizes['sq'] and not stock_calls(m), f'cover.jpg before folder.jpg ({got})')
    m, got = folder({'folder.jpg': wd, 'folder.png': pn})
    expect(got == sizes['wd'], f'folder.jpg before folder.png ({got})')
    m, got = folder({'cover.png': pn, 'folder.jpeg': tl})
    expect(got == sizes['pn'], f'cover.png before folder.jpeg ({got})')
    m, got = folder({'song.jpg': tl, 'cover.jpg': sq, 'folder.jpg': wd})
    expect(got == sizes['tl'], f'a picture named for the track (song.jpg) comes first ({got})')
    m, got = folder({'SONG.JPEG': wd, 'song.png': tl})
    expect(got == sizes['wd'], f'.jpeg of the track name before its .png, any case ({got})')
    m, got = folder({'Cover.JPG': wd, 'back.jpg': sq})
    expect(got == sizes['wd'], f'names match in any case ({got})')
    m, got = folder({'zzz.jpg': sq, 'aaa.png': pn})
    expect(got == sizes['pn'], f'no known name: readdir order ({got})')
    m, got = folder({'notes.txt': b'x', 'cover.jpg.bak': sq, 'thumb.gif': sq, 'a.jpg': tl})
    expect(got == sizes['tl'], f'only .jpg, .jpeg and .png files count ({got})')
    m = machine(); m.taglib_kind = 0; m.put(f'{DIR}/cover.jpg/inner', b'x'); m.put(f'{DIR}/folder.jpg', wd)
    out = build(m)
    expect(out is not None and decoded(out).size == sizes['wd'], 'a folder named cover.jpg is not a picture (d_type)')
    # stock's file size limits (0x5eb760, 0x5eb7bc): a JPEG over 6 MiB and a PNG over 1 MiB are skipped; the next one is used
    big = sq + b'\0' * (0x600001 - len(sq)); bigpng = pn + b'\0' * (0x100001 - len(pn))
    m, got = folder({'cover.jpg': big, 'folder.jpg': wd})
    expect(got == sizes['wd'], f'a JPEG file over 6 MiB is skipped like stock does ({got})')
    m, got = folder({'cover.png': bigpng, 'folder.jpg': wd})
    expect(got == sizes['wd'], f'a PNG file over 1 MiB is skipped like stock does ({got})')
    m, got = folder({'cover.jpg': big}, extern_cover=1)
    expect(got is None and stock_calls(m) == ['toolsGetExternCover'], 'nothing usable: stock\'s folder call')
    m, got = folder({'cover.jpg': b'\xff\xd8\xff\xe0garbage' * 20, 'folder.jpg': wd})
    expect(got == sizes['wd'] and not stock_calls(m), f'a file that is not a picture (no frame header) is passed over, as stock does ({got})')
    m, got = folder({'cover.jpg': sq[:3000], 'folder.jpg': wd})
    expect(stock_calls(m) == ['toolsGetExternCover'], 'a candidate whose header reads but does not decode: stock\'s folder call walks the folder itself')
    m, got = folder({'cover.jpg': picture(120, 90)[0]}, extern_cover=1)
    expect(stock_calls(m) == ['toolsGetExternCover'] and 'create_compress' not in m.jlog, 'a folder picture smaller than the cover is stock\'s (it keeps it as it is)')

    # 7. Both art kinds in one album: the embedded picture wins, the folder is not looked at.
    m = machine(); m.taglib_kind, m.taglib_data = 2, picture(900, 900)[0]; m.put(f'{DIR}/cover.jpg', wd)
    out = build(m)
    expect(decoded(out).size == (ART, ART) and not [c for c in m.calls if c[0] == 'opendir'], 'an album with embedded art does not look at its folder')

    # 8. The transient extraction of the Pod's cover pane (cc_build_add_file, 264 px): the same path at the larger size, kept only when the picture reaches it.
    dst = '/tmp/m1plus-pane.jpg'

    def pane(w, h):
        m = machine(); m.taglib_kind, m.taglib_data = 2, picture(w, h)[0]
        m.thread = None
        assert m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_add_file'], a0=m.cstr(TRACK), a1=m.cstr(dst), a2=264, count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
        m.call(m.thread[0], a0=m.thread[1], count=1 << 40); calls = m.calls; m.call(PSYMS['cc_build_stop'], count=1 << 40); m.calls = calls
        return m
    m = pane(1000, 700)
    expect(dst in m.fs and decoded(m.fs[dst]).size == fit(1000, 700, 264) and ('encoded', fit(1000, 700, 264), 90) in m.jlog, f'the pane\'s picture is 264 px by the same path ({decoded(m.fs[dst]).size if dst in m.fs else None})')
    m = pane(200, 200)
    expect(dst not in m.fs, 'a source under 264 px is not kept')
    m = machine(); m.taglib_kind, m.taglib_data = 2, picture(1000, 700)[0]; m.thread = None
    m.on_unlock = lambda: m.setword(PSYMS['cb'] + 4 * 7, 1)   # the pane went (and removed its file) while the picture was being shrunk
    assert m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=1 << 40) == 1
    assert m.call(PSYMS['cc_build_add_file'], a0=m.cstr(TRACK), a1=m.cstr(dst), a2=264, count=1 << 40) == 1
    assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    expect(dst not in m.fs and dst + '.tmp' not in m.fs and ('rename', dst + '.tmp', dst) not in m.calls, 'a pane job cancelled after the extraction publishes nothing')

    # 8b. The timed cover page's request (cc_build_add_aspect, 320 px): the real worker on an original whose longer side is exactly 320 keeps its shape (stock's fit, which the 168 px cache and the pane keep,
    #     stretches it to 320 x 320); a square one is a 1:1 copy; a larger one is the same fit as before; one under 320 makes no file; stock's resize is never the fallback.
    def page(w, h, px=320, add='cc_build_add_aspect', embedded=True, src=None, emb_data=None, folder_data=None):
        m = machine(); m.thread = None
        if emb_data is not None: m.taglib_kind, m.taglib_data = 2, emb_data
        elif embedded: m.taglib_kind, m.taglib_data = 2, picture(w, h)[0]
        if folder_data is not None: m.put(f'{DIR}/cover.jpg', folder_data)
        elif not embedded: m.put(f'{DIR}/cover.jpg', picture(w, h)[0])
        assert m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=1 << 40) == 1
        if add == 'cc_build_add_aspect': assert m.call(PSYMS[add], a0=m.cstr(TRACK), a1=m.cstr(dst), a2=px, a3=src or (2 if embedded else 3), count=1 << 40) == 1
        else: assert m.call(PSYMS[add], a0=m.cstr(TRACK), a1=m.cstr(dst), a2=px, count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
        m.call(m.thread[0], a0=m.thread[1], count=1 << 40); calls = m.calls; m.call(PSYMS['cc_build_stop'], count=1 << 40); m.calls = calls
        return m
    for w, h in ((320, 240), (240, 320), (320, 100)):
        for emb in (True, False):
            m = page(w, h, embedded=emb)
            got = decoded(m.fs[dst]) if dst in m.fs else None
            expect(got is not None and got.size == (w, h) and close_to(got, picture(w, h)[1]), f'page request, {w} x {h} {"embedded" if emb else "folder"} original: kept at {w} x {h}, not stretched ({got.size if got else None})')
            expect(not stock_calls(m), 'and stock\'s resize is not asked')
    m = page(320, 320)
    got = decoded(m.fs[dst]) if dst in m.fs else None
    expect(got is not None and got.size == (320, 320) and close_to(got, picture(320, 320)[1], 2.0), 'page request, a square 320 original: 320 x 320, a copy of the picture (JPEG round trip only)')
    m = page(640, 480)
    expect(dst in m.fs and decoded(m.fs[dst]).size == (320, 240), 'page request, 640 x 480: 320 x 240 as stock fits it')
    m = page(300, 300)
    expect(dst not in m.fs and not stock_calls(m), 'page request, an original under 320: no file and stock\'s resize is not asked')
    # the request names stock's cover source (2 embedded, 3 folder) and only that source is used: the other is never a substitute
    big = picture(600, 600)[0]
    m = page(0, 0, emb_data=picture(200, 200)[0], folder_data=big, src=2)
    expect(dst not in m.fs and not stock_calls(m) and not [c for c in m.calls if c[0] == 'opendir'], 'source 2: a 200 x 200 embedded picture with a different 600 x 600 folder cover: no file, the folder is never looked at')
    m = page(0, 0, emb_data=b'not a picture at all', folder_data=big, src=2)
    expect(dst not in m.fs and not stock_calls(m) and not [c for c in m.calls if c[0] == 'opendir'], 'source 2: an unsupported embedded picture with a valid folder cover: no file, the folder is never used')
    m = page(0, 0, emb_data=picture(900, 900)[0], folder_data=picture(640, 480)[0], src=3)
    expect(dst in m.fs and decoded(m.fs[dst]).size == (320, 240) and 'taglib_album_picture' not in [c[0] for c in m.calls], 'source 3: the folder cover is used (640 x 480 -> 320 x 240) even with a different embedded picture present, which is not read')
    m = page(0, 0, emb_data=picture(900, 900)[0], folder_data=picture(200, 200)[0], src=3)
    expect(dst not in m.fs and not stock_calls(m), 'source 3: a small folder cover makes no file; the embedded picture is not a substitute')
    m = page(0, 0, emb_data=picture(900, 600)[0], src=2)
    expect(dst in m.fs and decoded(m.fs[dst]).size == (320, 213), 'source 2: a big embedded picture is used as before')
    m = machine(); assert m.call(PSYMS['cc_build_open'], a0=1, a1=0, count=1 << 40) == 1
    expect([m.call(PSYMS['cc_build_add_aspect'], a0=m.cstr(TRACK), a1=m.cstr(dst), a2=320, a3=s_, count=1 << 40) for s_ in (0, 1, 5)] == [0, 0, 0], 'a source other than 2 or 3 adds no job')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m = page(264, 198, px=264, add='cc_build_add_file')
    expect(dst in m.fs and decoded(m.fs[dst]).size == (264, 264) == fit(264, 198, 264), 'the pane\'s request (cc_build_add_file) keeps stock\'s square fit at exactly 264: unchanged')
    m = page(320, 240, embedded=True, add='cc_build_add_file')
    expect(dst in m.fs and decoded(m.fs[dst]).size == (320, 320), 'and cc_build_add_file at 320 still stretches 320 x 240 as stock does')

    # 9. A progressive JPEG over 4 MP (libjpeg keeps all its coefficients) is refused: no art, and stock is not asked, embedded or in the folder.
    from PIL import Image
    pb = io.BytesIO(); Image.new('RGB', (2300, 1900), (90, 60, 30)).save(pb, 'JPEG', progressive=True); prog = pb.getvalue()
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, prog, 1
    out = build(m)
    expect('toolsGetAlbumCover' not in stock_calls(m) and not m.jlog and out == b'', f'an embedded progressive 2300 x 1900 is refused: no stock embedded call, an empty marker ({stock_calls(m)})')
    pb = io.BytesIO(); Image.new('RGB', (8300, 200), (90, 60, 30)).save(pb, 'JPEG', progressive=True)
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, pb.getvalue(), 1
    out = build(m)
    expect('toolsGetAlbumCover' not in stock_calls(m) and not m.jlog and out == b'', 'a progressive cover over 8192 on a side is refused too, not handed to stock')
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, None, 1; m.fs['/tmp/.m1plus_art'] = picture(900, 900)[0]
    build(m)
    expect(stock_calls(m) == ['toolsGetAlbumCover'] and not m.jlog and '/tmp/.m1plus_art' not in m.fs, 'a stale private copy is removed, not shrunk when the handoff fails')
    m, got = folder({'cover.jpg': prog}, extern_cover=1)
    expect(not stock_calls(m) and not m.jlog and got is None, 'a progressive folder picture over 4 MP is refused: no stock call')

    # 10. The lock: only taglib_album_picture (its file moved to a private name) is under it; our resize, the folder's included, runs outside; stock's calls take it themselves.
    data, im = picture(900, 900)
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    build(m)
    seq = [c for c in m.calls if c[0] in ('lock', 'taglib_album_picture', 'rename', 'unlock', 'fopen') and (c[0] != 'rename' or c[1] == TMP) and (c[0] != 'fopen' or c[1] == PRIV)]
    expect(seq[:5] == [('lock', lock), seq[1], ('rename', TMP, PRIV), ('unlock', lock), ('fopen', PRIV, 'rb')] and seq[1][0] == 'taglib_album_picture',
           f'taglib and the move of /tmp/.tmp_picture are under the lock; the private copy is opened after the unlock ({seq})')
    expect(PRIV not in m.fs and TMP not in m.fs, 'the private copy is removed')
    m = machine(); m.taglib_kind = 0
    m.put(f'{DIR}/cover.jpg', picture(700, 500)[0])
    build(m)
    expect(sum(1 for c in m.calls if c[0] == 'lock') == 1 and not stock_calls(m), 'a folder picture is shrunk outside the lock (the only lock is taglib\'s)')
    m = machine(); m.taglib_kind = 0; m.extern_cover = 1
    build(m)
    expect(sum(1 for c in m.calls if c[0] == 'lock') == 2 and stock_calls(m) == ['toolsGetExternCover'], 'stock\'s folder call takes the lock itself')
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, picture(150, 150)[0], 1
    held = []
    m.on_lock = lambda: held.append(len([c for c in m.calls if c[0] == 'lock']))
    build(m)
    expect(stock_calls(m) == ['toolsGetAlbumCover'] and held == [1, 2], f'stock\'s embedded call runs under a second lock ({held})')
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    m.on_lock = lambda: m.setword(PSYMS['cb'] + 4 * 7, 1)   # cancelled while waiting for the lock
    out = build(m)
    expect(out is None and not [c for c in m.calls if c[0] in ('taglib_album_picture', 'fopen') and c[1] != INFLIGHT] and not stock_calls(m), 'cancelled while waiting: no extraction, no marker')

    # 11. The in-flight marker: written before the extraction (the key), gone after; a leftover one makes its key bad; .bad keeps CC_MISSING from queueing it and CC_REBUILD retries once.
    m = machine(); m.taglib_kind, m.taglib_data = 2, data
    seen = []
    m.on_lock = lambda: seen.append(INFLIGHT in m.fs)
    build(m)
    order = [c[0] for c in m.calls]
    wr = [c for c in m.calls if c[0] == 'fwrite']
    expect(len(wr) == 1 and wr[0][1] == INFLIGHT and wr[0][2].replace(build_of(wr[0][2]), b'TAG') == inflight_text(KEY) and not seen[0] and order.index('lock') < order.index('fwrite') < order.index('taglib_album_picture') and INFLIGHT not in m.fs and bad_file(KEY) not in m.fs,
           f'ART_DIR/.inflight is a one-write text record (header, key, build, track, end) from the moment the lock is held until the job is done; no .bad ({wr})')
    m = machine(); m.fs[INFLIGHT] = inflight_text(KEY)
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    expect(try_file(KEY) in m.fs and bad_file(KEY) not in m.fs and INFLIGHT not in m.fs, 'one leftover .inflight (a power-off) is a strike (.try), not a .bad')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m.fs[INFLIGHT] = inflight_text(KEY)
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    bad = m.fs.get(bad_file(KEY), b'')
    expect(bad.replace(build_of(bad), b'TAG') == f'm1plus cover 1\nkey: {KEY:08x}\nbuild: TAG\nresult: interrupted twice\nphase: unknown\ntrack: {TRACK}\nend\n'.encode() and try_file(KEY) not in m.fs and INFLIGHT not in m.fs,
           f'a second one for the same key is a .bad record for it: interrupted twice, phase unknown, the track ({bad})')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m = machine(); m.fs[try_file(KEY)] = b''; m.taglib_kind, m.taglib_data = 2, data
    build(m)
    expect(try_file(KEY) not in m.fs, 'a finished job for the key clears its strike')
    m = machine(); m.fs[try_file(KEY)] = b''; m.fs[INFLIGHT] = inflight_text(KEY)
    m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40); m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m.fs[INFLIGHT] = inflight_text(KEY + 1); m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40)
    expect(try_file(KEY + 1) in m.fs and bad_file(KEY + 1) not in m.fs, 'another key starts its own strike')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m = machine(); m.fs[INFLIGHT] = inflight_text(KEY); m.fs[try_file(KEY)] = b''
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
    expect(m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY, count=1 << 40) == 0 and m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY + 1, count=1 << 40) == 1, 'CC_MISSING skips the bad key and queues another')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=1, count=1 << 40) == 1
    expect(m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY, count=1 << 40) == 0 and bad_file(KEY) in m.fs, 'CC_REBUILD skips it too and leaves the .bad')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m.fs[bad_file(KEY + 1)] = b''; m.fs[art_file(KEY)] = b'x'
    m.dirs.add(art_file(KEY).rsplit('/', 1)[0])
    m.call(PSYMS['cc_clear_bad'], count=1 << 40)
    expect(bad_file(KEY) not in m.fs and bad_file(KEY + 1) not in m.fs and art_file(KEY) in m.fs, 'a Rebuild Covers request clears every .bad (and only those): one more try each')
    m = machine(); m.fs[INFLIGHT] = inflight_text(KEY); m.fs[try_file(KEY)] = b''
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=1, count=1 << 40) == 1
    expect(m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY, count=1 << 40) == 0 and bad_file(KEY) in m.fs and m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY + 1, count=1 << 40) == 1,
           'a CC_REBUILD resumed after the hang (the request file survived the reboot) leaves the recovered .bad alone')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    m = machine(); m.fs[INFLIGHT] = inflight_text(KEY); m.fs[try_file(KEY)] = b''; m.fail.add(('fopen', bad_file(KEY)))
    m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40)
    expect(INFLIGHT in m.fs, 'a .bad that could not be written keeps the .inflight for the next run')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)

    # 12. A stalled worker: no progress for CC_STALL_MS (10 s, time_now_ms) while polled stops the set and orphans the worker without touching the card; the job is marked bad then
    # (its .inflight goes); the pages see the set as finished; progress restarts the wait; the wall clock is not used.
    def started(m, n=2):
        m.thread = None
        assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
        for k in range(n): assert m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY + k, count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
    def poll(m): return m.call(PSYMS['cc_build_done'], count=1 << 40)
    m = machine(); m.clock = 1000; started(m)
    m.clock += 9000; poll(m)
    expect(cbw(m, 4) == 1, 'nine seconds without progress: still running')
    m.setword(PSYMS['cb'] + 4 * 5, 1)   # the first job finished
    m.clock += 9000; poll(m); m.clock += 9000; poll(m)
    expect(cbw(m, 4) == 1, 'progress restarts the wait')
    m.fs[INFLIGHT] = inflight_text(KEY + 1); m.calls.clear()
    m.setword(PSYMS['cb'] + 4 * 13, KEY + 1); m.setword(PSYMS['cb'] + 4 * 15, 1)   # the second job holds the lock (cur, began)
    m.clock += 1000; m.wall += 7200; done = poll(m)
    expect(cbw(m, 4) == 0 and cbw(m, 0) and cbw(m, 9) == 1 and 'pthread_join' not in [c[0] for c in m.calls] and 'rename' not in [c[0] for c in m.calls],
           'ten seconds without progress: the set is stopped and the worker orphaned (not joined); a wall-clock step is no stall')
    expect(done == 2 and m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 0, 'a stalled set reads as finished (done = total); the next open is refused while the worker is out')
    expect(bad_file(KEY + 1) in m.fs and bad_file(KEY) not in m.fs and INFLIGHT not in m.fs, 'the worker never returned, yet the stalled job is .bad and its .inflight gone (no strike at the next boot)')
    m.clock += 10000
    expect(m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 0, 'the orphan still holds the set')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)   # it comes back: cancelled, exits
    expect(bad_file(KEY + 1) in m.fs and INFLIGHT not in m.fs, 'and its return changes nothing')
    expect(poll(m) == 0 and not cbw(m, 9), 'the next poll joins and frees the set: done = total = 0, the pages end')
    expect(m.call(PSYMS['cc_build_stalled'], count=1 << 40) == 1, 'the set still reads as stalled after it is freed')
    for mode in (2, 0):   # other sets opened and freed between the stall and the resume
        assert m.call(PSYMS['cc_build_open'], a0=4, a1=mode, count=1 << 40) == 1
        m.call(PSYMS['cc_build_stop'], count=1 << 40)
    assert m.call(PSYMS['cc_build_open'], a0=4, a1=1, count=1 << 40) == 1
    expect(m.call(PSYMS['cc_build_stalled'], count=1 << 40) == 0, 'until the next open')
    expect(m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY + 1, count=1 << 40) == 0 and m.call(PSYMS['cc_build_add'], a0=m.cstr(TRACK), a1=KEY, count=1 << 40) == 1,
           'the rebuild that resumes skips only the hung album (its .bad persists), whatever sets were opened in between')
    m.call(PSYMS['cc_build_stop'], count=1 << 40)
    expect(m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1, 'and a new set may open')
    m = machine(); m.clock = 1000; started(m, 1); m.clock += 10000; poll(m)
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)   # the job only waited for the lock (began = 0)
    expect(bad_file(KEY) not in m.fs and INFLIGHT not in m.fs and not [c for c in m.calls if c[0] == 'taglib_album_picture'], 'a stalled job that never got the lock is not marked bad')
    m = machine(); m.clock = 1000; started(m, 1); m.clock += 10000; poll(m)
    expect(m.call(PSYMS['cc_build_orphan'], count=1 << 40) == 1, 'just orphaned: callers retry')
    m.clock += 10000
    expect(m.call(PSYMS['cc_build_orphan'], count=1 << 40) == 0, 'orphaned for 10 s: callers stop retrying')
    m = machine(); m.clock = 0xffffe000; started(m, 1)
    m.clock = 1000; poll(m)   # the clock wraps: 9.2 s since the start
    expect(cbw(m, 4) == 1, 'the elapsed time is unsigned: a wrap of time_now_ms is no stall')

    # 13. The watchdog and the worker's job transitions (cb_mutex): the claim names only the job that stalled, and a claimed job that comes back and publishes is not bad.
    pic = picture(900, 900)[0]
    def paused(kind=2):
        m = machine(); m.taglib_kind, m.taglib_data, m.clock = kind, pic, 1000; started(m)
        w = Worker(m); w.go(lambda: cbf(m, 'cur') == KEY and cbf(m, 'seq') == 1); poll(m)   # A has started: the watchdog sees it
        return m, w
    m, w = paused()
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000; poll(m)
    expect(cbf(m, 'cancelled') and cbf(m, 'stalled') and cbf(m, 'orphan') and bad_file(KEY) in m.fs and INFLIGHT not in m.fs, 'a job that began and never returns: claimed, .bad, no .inflight')
    expect(cbf(m, 'seq') == 1 and bad_file(KEY + 1) not in m.fs and art_file(KEY + 1) not in m.fs, 'the next job never started')
    w.go()
    expect(w.done and cbf(m, 'seq') == 1 and art_file(KEY + 1) not in m.fs and bad_file(KEY + 1) not in m.fs, 'and it does not start when the worker returns')
    expect(art_file(KEY) in m.fs and bad_file(KEY) not in m.fs and INFLIGHT not in m.fs, 'late success: the claimed job published, its .bad is removed')
    m, w = paused(0)
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000; poll(m); w.go()
    expect(bad_file(KEY) in m.fs and art_file(KEY) not in m.fs and bad_file(KEY + 1) not in m.fs, 'a claimed job that fails keeps its .bad')
    m, w = paused()
    w.go(lambda: cbf(m, 'cur') == 0 and cbf(m, 'began') == 1 and cbf(m, 'done') == 0); m.clock += 11000; poll(m)   # A has finished its extraction as the watchdog times out
    expect(cbf(m, 'cancelled') and bad_file(KEY) not in m.fs, 'A finishing as the watchdog polls: nothing to mark')
    w.go()
    expect(art_file(KEY) in m.fs and bad_file(KEY) not in m.fs and bad_file(KEY + 1) not in m.fs and art_file(KEY + 1) not in m.fs and cbf(m, 'seq') == 1, 'B never starts after the claim and is never .bad')
    m, w = paused()
    w.go(lambda: cbf(m, 'cur') == KEY + 1 and cbf(m, 'seq') == 2); m.clock += 11000; poll(m)   # the probe: A done, B starting as the 10 s are up
    expect(cbf(m, 'running') == 1 and not cbf(m, 'cancelled') and bad_file(KEY + 1) not in m.fs and bad_file(KEY) not in m.fs, 'B starting as A times out: no claim, B is not .bad')
    m, w = paused()
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000
    def moved():   # the worker moves on to B between the watchdog's look and its claim
        m.on_cb_lock = None
        setcb(m, 'done', 1); setcb(m, 'seq', 2); setcb(m, 'cur', KEY + 1); setcb(m, 'began', 1)
    m.on_cb_lock = moved; poll(m)
    expect(cbf(m, 'running') == 1 and not cbf(m, 'cancelled') and not cbf(m, 'stalled') and bad_file(KEY + 1) not in m.fs, 'progress between the look and the claim: re-checked under the mutex, no claim')

    # 14. Late success: the watchdog's .bad and the worker's acknowledgement (claimed cleared) in either order; .inflight is written before `began`.
    m, w = paused()
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000; poll(m)
    expect(bad_file(KEY) in m.fs and cbf(m, 'claimed') == KEY, 'the claim is held until the worker acknowledges')
    w.go()
    expect(cbf(m, 'claimed') == 0 and art_file(KEY) in m.fs and bad_file(KEY) not in m.fs, 'the .bad is written, then the worker publishes: cover, no .bad, claim acknowledged')
    m, w = paused()
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000
    n = [0]
    def acked():   # the worker publishes and acknowledges right after the watchdog's claim unlock (its first cb_unlock), before mark_bad: its own .bad unlink would find nothing (the hook leaves .bad alone)
        n[0] += 1
        if n[0] == 1: m.on_cb_unlock = None; m.fs[art_file(KEY)] = b'cover'; setcb(m, 'claimed', 0)
    m.on_cb_unlock = acked; poll(m)
    m.on_cb_unlock = None
    expect(n[0] == 1 and art_file(KEY) in m.fs and bad_file(KEY) not in m.fs and cbf(m, 'claimed') == 0, 'acknowledged before the .bad is written: the watchdog\'s re-check removes the .bad it then writes')
    m, w = paused(0)
    w.go(lambda: cbf(m, 'began') == 1); m.clock += 11000; poll(m); w.go()
    expect(cbf(m, 'claimed') == KEY and bad_file(KEY) in m.fs, 'a claimed job that fails is never acknowledged: .bad stays')
    m, w = paused()
    hit = []
    w.go(at_lock=lambda: INFLIGHT in m.fs and cbf(m, 'began') == 0 and not hit.append(1))   # holds the stock lock, .inflight written, `began` not yet set
    expect(hit and not w.done, '.inflight is written before began is set')
    m.clock += 11000; poll(m)
    expect(cbf(m, 'cancelled') and bad_file(KEY) not in m.fs, 'not yet begun: the claim names no job')
    w.go()
    expect(w.done and INFLIGHT not in m.fs and bad_file(KEY) not in m.fs and art_file(KEY) not in m.fs, 'and the worker that finds itself claimed removes the .inflight and extracts nothing')
    m, w = paused()
    w.go(lambda: cbf(m, 'began') == 1)
    expect(INFLIGHT in m.fs, 'once began is set the .inflight is there')
    m.clock += 11000; poll(m)
    expect(INFLIGHT not in m.fs and bad_file(KEY) in m.fs, 'and the claim removes it')

    # 15. The text records. A timeout names the phase where the worker's progress stopped and the image it was on; the snapshot is taken under the claim; a leftover .inflight is read defensively.
    def norm(data): return data.replace(build_of(data), b'TAG')

    def bad_text(key, result, phase, track=TRACK, image=None):
        return (f'm1plus cover 1\nkey: {key:08x}\nbuild: TAG\nresult: {result}\nphase: {phase}\ntrack: {track}\n' + (f'image: {image}\n' if image else '') + 'end\n').encode('latin-1')

    def stall(m, until, track=TRACK, hook=None):
        """Job KEY (then KEY + 1) on the worker, paused where `until` holds after a cb_mutex release, then the watchdog times out."""
        m.clock = 1000; m.thread = None
        assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
        for k in range(2): assert m.call(PSYMS['cc_build_add'], a0=m.cstr(track), a1=KEY + k, count=1 << 40) == 1
        assert m.call(PSYMS['cc_build_start'], count=1 << 40) == 1
        w = Worker(m); w.go(lambda: cbf(m, 'cur') == KEY and cbf(m, 'seq') == 1); poll(m)
        w.go(until); m.clock += 11000; m.on_cb_unlock = hook; poll(m); m.on_cb_unlock = None
        return w
    at_phase = lambda m, n: (lambda: cbf(m, 'phase') == n)
    jpg = picture(700, 500)[0]
    m = machine(); m.taglib_kind, m.taglib_data = 2, pic
    stall(m, at_phase(m, 1))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'embedded art, reading tags') and b'build: ' in m.fs[bad_file(KEY)], f'timed out reading tags: {m.fs.get(bad_file(KEY))}')
    m = machine(); m.taglib_kind, m.taglib_data = 2, pic
    stall(m, at_phase(m, 2))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'embedded art, shrinking', image='embedded jpeg'), f'timed out shrinking an embedded picture: {m.fs.get(bad_file(KEY))}')
    m = machine(); m.taglib_kind, m.taglib_data = 1, pic
    stall(m, at_phase(m, 2))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'embedded art, shrinking', image='embedded png'), 'taglib\'s kind 1 is a PNG')
    m = machine(); m.taglib_kind, m.taglib_data, m.album_cover = 2, picture(150, 150)[0], 1
    stall(m, at_phase(m, 3))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'embedded art, stock fallback', image='embedded jpeg'), 'timed out in stock\'s embedded call (the image it was shrinking stays named)')
    m = machine(); m.taglib_kind = 0; m.put(f'{DIR}/cover.jpg', jpg)
    stall(m, at_phase(m, 4))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'folder, scanning'), f'timed out scanning the folder: no image yet (the embedded one is cleared) ({m.fs.get(bad_file(KEY))})')
    m = machine(); m.taglib_kind = 0; m.put(f'{DIR}/cover.jpg', jpg)
    stall(m, at_phase(m, 5))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'folder image, shrinking', image=f'{DIR}/cover.jpg 700x500 jpeg baseline'), f'timed out shrinking a folder image: path, size, kind ({m.fs.get(bad_file(KEY))})')
    m = machine(); m.taglib_kind = 0; m.put(f'{DIR}/cover.jpg', picture(900, 900, progressive=True)[0])
    stall(m, at_phase(m, 5))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'folder image, shrinking', image=f'{DIR}/cover.jpg 900x900 jpeg progressive'), 'a progressive JPEG says so')
    m = machine(); m.taglib_kind = 0; m.extern_cover = 1
    stall(m, at_phase(m, 6))
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'folder, stock fallback'), 'timed out in stock\'s folder call')
    expect(INFLIGHT not in m.fs, 'the watchdog still removes the .inflight')

    # The snapshot: the worker moves on (a new job, another phase and image) right after the claim releases cb_mutex; the .bad still describes the claimed job.
    m = machine(); m.taglib_kind = 0; m.put(f'{DIR}/cover.jpg', jpg)
    n = [0]
    def moved():
        n[0] += 1
        if n[0] != 1: return
        setcb(m, 'phase', 6); setcb(m, 'iw', 1); setcb(m, 'ih', 2); setcb(m, 'ikind', 2); setcb(m, 'isof', 0)
        m.u.mem_write(PSYMS['cb'] + 4 * 24, b'/other.png\0'); setcb(m, 'cur', KEY + 1); setcb(m, 'seq', 9)
        m.u.mem_write(m.word(cbf(m, 'jobs')), b'/other/track.flac\0')
    stall(m, at_phase(m, 5), hook=moved)
    expect(n[0] >= 1 and norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'folder image, shrinking', image=f'{DIR}/cover.jpg 700x500 jpeg baseline') and bad_file(KEY + 1) not in m.fs,
           f'a transition injected right after the claim does not change the record ({m.fs.get(bad_file(KEY))})')

    # The reboot path and the defensive read of a leftover .inflight.
    def reboot(text, strike=False):
        m = machine()
        if strike: m.fs[try_file(KEY)] = b''
        m.fs[INFLIGHT] = text
        assert m.call(PSYMS['cc_build_open'], a0=4, a1=0, count=1 << 40) == 1
        m.call(PSYMS['cc_build_stop'], count=1 << 40)
        return m
    m = reboot(inflight_text(KEY), True)
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'interrupted twice', 'unknown') and INFLIGHT not in m.fs, 'second strike: the track comes from the .inflight')
    for what, text in (('header and key only', b'm1plus cover 1\nkey: %08x\n' % KEY), ('no end', b'm1plus cover 1\nkey: %08x\nbuild: x\ntrack: %s\n' % (KEY, TRACK.encode())),
                       ('no track', b'm1plus cover 1\nkey: %08x\nbuild: x\nend\n' % KEY)):
        m = reboot(text); m2 = reboot(text, True)
        expect(try_file(KEY) in m.fs and bad_file(KEY) not in m.fs and INFLIGHT not in m.fs and norm(m2.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'interrupted twice', 'unknown', track='unknown'),
               f'a cut .inflight ({what}) still strikes its key, with the track unknown')
    for what, text in (('empty', b''), ('the old binary key', struct.pack('<I', KEY)), ('garbage', bytes(range(1, 200))), ('no header', b'key: %08x\ntrack: x\nend\n' % KEY), ('short key', b'm1plus cover 1\nkey: 1234abc\ntrack: x\nend\n'),
                       ('bad digit', b'm1plus cover 1\nkey: 1234abcg\ntrack: x\nend\n'), ('zero key', b'm1plus cover 1\nkey: 00000000\ntrack: x\nend\n'), ('long key', b'm1plus cover 1\nkey: 1234abcdef\ntrack: x\nend\n')):
        m = reboot(text, True)
        expect(INFLIGHT not in m.fs and not [p for p in m.fs if p.endswith('.bad')] and list(p for p in m.fs if p.endswith('.try')) == [try_file(KEY)] and m.fs[try_file(KEY)] == b'', f'an .inflight that is {what} is removed and no one is blamed')
    m = reboot(b'm1plus cover 1\nkey: %08X\ntrack: x\nend\n' % KEY)
    expect(try_file(KEY) in m.fs, 'upper-case hex digits are read')
    m = reboot(b'm1plus cover 1\nkey: %08x\ntrack: %s\nend\n' % (KEY, b'a' * 5000))
    expect(INFLIGHT not in m.fs and try_file(KEY) in m.fs, 'a huge .inflight is read to 1 KB only: bounded, and the cut track line has no end, so the strike is unknown')

    # Escapes: a backslash, a newline and a control byte in a path stay on one line; a long UTF-8 path is cut on a character boundary.
    odd = f'{DIR}/a\\b\nc\x01.flac'
    esc = f'{DIR}/a\\\\b\\nc\\x01.flac'
    m = machine(); m.put(odd, b'x'); m.taglib_kind, m.taglib_data = 2, data
    build(m, track=odd)
    wr = [c for c in m.calls if c[0] == 'fwrite']
    expect(len(wr) == 1 and norm(wr[0][2]) == inflight_text(KEY, esc), f'.inflight escapes the track onto one line ({wr})')
    m = machine(); m.put(odd, b'x'); m.taglib_kind, m.taglib_data = 2, pic
    stall(m, at_phase(m, 1), track=odd)
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'timed out', 'embedded art, reading tags', track=esc), f'.bad escapes it the same way ({m.fs.get(bad_file(KEY))})')
    m = reboot(inflight_text(KEY, esc), True)
    expect(norm(m.fs.get(bad_file(KEY), b'')) == bad_text(KEY, 'interrupted twice', 'unknown', track=esc), 'the escaped track passes through the reboot path unchanged')
    long = f'{DIR}/' + '\u00e9' * 200 + '.flac'
    m = machine(); m.put(long.encode().decode('latin-1'), b'x'); m.taglib_kind, m.taglib_data = 2, pic
    stall(m, at_phase(m, 1), track=long)
    line = [l for l in m.fs.get(bad_file(KEY), b'').split(b'\n') if l.startswith(b'track: ')]
    try: ok = len(line) == 1 and len(line[0]) - 7 <= 255 and line[0][7:].decode('utf-8').startswith(DIR)
    except UnicodeDecodeError: ok = False
    expect(ok and m.fs[bad_file(KEY)].endswith(b'end\n'), f'a long track is cut at 255 bytes on a character boundary ({line})')

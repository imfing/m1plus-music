"""Card boot logo tests: the built S11logo_display_shell run under the host shell, its fixed paths pointed into a scratch directory,
display_logo, ffmpeg and md5sum stubbed (docs/modules/boot.md "Card logo")."""
import os, shutil, stat, struct, subprocess, tempfile
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_boot as mb
import paths

STUBS = {
    'display_logo': 'echo "$1" > "$T/shown"\n',
    # records each call; writes the filter chain as the "picture"; fails while $T/ffail exists
    'ffmpeg': 'echo "$*" >> "$T/calls"\n[ -e "$T/ffail" ] && exit 1\nfor a; do out=$a; done\nprev=; for a; do [ "$prev" = -vf ] && vf=$a; prev=$a; done\necho "$vf" > "$out"\n',
    'md5sum': 'cksum\n',
}


def jpeg(w, h, sof=0xC0, app=b''):
    """A JPEG's start: SOI, APP0, `app`, then a three-component frame header for w x h."""
    return (b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + bytes(9) + app + bytes([0xFF, sof]) + struct.pack('>HBHHB', 17, 8, h, w, 3)
            + bytes(9) + b'\xff\xd9')


def run(ctx):
    expect = ctx.expect
    root = os.path.join(WORK, 'rootfs')
    stock = os.path.join(paths.find_stock(), 'rootfs')
    built_p = os.path.join(WORK, mb.INIT)
    built = open(built_p, 'rb').read()

    # ---- the file in the tree ----
    expect(built == open(mb.INIT_SRC, 'rb').read(), 'S11logo_display_shell is the asset')
    st, sst = os.stat(built_p), os.stat(os.path.join(stock, 'etc', 'init.d', 'S11logo_display_shell'))
    expect(stat.S_IMODE(st.st_mode) == stat.S_IMODE(sst.st_mode) == 0o755 and st.st_mtime_ns == sst.st_mtime_ns, 'stock mode and mtime kept')
    text = built.decode()
    tail = text[text.index('case "$1"'):]
    expect('jpeg_display &' in tail and 'card_import &' in tail and tail.count('&\n') == 2, 'both run in the background: the boot never waits on them')
    expect(text.count('display_logo ') == 1, 'one display_logo call: one picture, never two')
    for d in ('/release/assets/default/raw/images/xx/logo.jpg', '/release/assets/default/raw/images/xx/logo180.jpg'):
        expect(os.path.exists(os.path.join(root, d.lstrip('/'))), f'{d} is in the tree')

    def boot(data=None, card=None, rotate=False, mounted=True, ffail=False, wait=300, ffdir=None):
        """One boot: data = {name: bytes} in /mnt/data/m1plus, card = bytes of boot-logo.jpg (None: no file).
        ffdir = the host ffmpeg's folder, used in place of the stub. Returns (status, output, shown, files in m1plus as {name: text}, ffmpeg calls)."""
        with tempfile.TemporaryDirectory() as t:
            dirs = {n: os.path.join(t, n) for n in ('bin', 'data', 'mmc', 'tmp', 'dev')}
            for d in dirs.values(): os.mkdir(d)
            os.mkdir(os.path.join(dirs['data'], 'm1plus'))
            for n, b in (data or {}).items(): open(os.path.join(dirs['data'], 'm1plus', n), 'wb').write(b)
            open(os.path.join(dirs['data'], 'config.ini'), 'w').write(f'[SYSSET]\nROTATEMODE={int(rotate)}\n')
            open(os.path.join(dirs['dev'], 'fb0'), 'w').close()
            # mmc_add is always there: add_removesd.sh touches it even when a mount fails; only /proc/mounts says mounted
            open(os.path.join(dirs['tmp'], 'mmc_add'), 'w').close()
            open(os.path.join(t, 'mounts'), 'w').write('/dev/ubi1_0 /mnt/data ubifs rw 0 0\n' + (f'/dev/mmcblk4p1 {dirs["mmc"]} exfat rw 0 0\n' if mounted else ''))
            if card is not None: open(os.path.join(dirs['mmc'], 'boot-logo.jpg'), 'wb').write(card)
            if ffail: open(os.path.join(t, 'ffail'), 'w').close()
            for n, body in STUBS.items():
                if ffdir and n == 'ffmpeg': continue
                p = os.path.join(dirs['bin'], n); open(p, 'w').write('#!/bin/sh\n' + body); os.chmod(p, 0o755)
            s = text[:text.index('case "$1"')] + 'jpeg_display\ncard_import\n'
            for a, b in (('/mnt/data', dirs['data']), ('/mnt/mmc', dirs['mmc']), ('/tmp/', dirs['tmp'] + '/'),
                         ('/dev/fb0', os.path.join(dirs['dev'], 'fb0')), ('/proc/mounts', os.path.join(t, 'mounts')), ('-ge 300', f'-ge {wait}')):
                s = s.replace(a, b)
            path = os.path.join(t, 'S11'); open(path, 'w').write(s)
            r = subprocess.run(['sh', path], env={'PATH': f'{dirs["bin"]}:{ffdir + ":" if ffdir else ""}/usr/bin:/bin', 'T': t}, capture_output=True, timeout=30)
            read = lambda p: open(p, errors='replace').read() if os.path.exists(p) else None
            m = os.path.join(dirs['data'], 'm1plus')
            return (r.returncode, r.stdout + r.stderr, (read(os.path.join(t, 'shown')) or '').strip().replace(dirs['data'], '/mnt/data'),
                    {n: read(os.path.join(m, n)) for n in sorted(os.listdir(m))}, (read(os.path.join(t, 'calls')) or '').splitlines())

    syntax = subprocess.run(['sh', '-n', built_p], capture_output=True)
    expect(syntax.returncode == 0, f'the script parses: {syntax.stderr!r}')

    # ---- what is shown ----
    rc, out, shown, files, calls = boot()
    expect(rc == 0 and shown == '/release/assets/default/raw/images/xx/logo.jpg' and files == {} and calls == [],
           f'no card logo: the built-in splash, nothing written: {rc} {out!r} {shown} {files} {calls}')
    _, _, shown, _, _ = boot(rotate=True)
    expect(shown == '/release/assets/default/raw/images/xx/logo180.jpg', f'rotated: the built-in 180 splash: {shown}')
    made = {'boot-logo.jpg': b'up', 'boot-logo180.jpg': b'down'}
    _, _, shown, files, _ = boot(data=made)
    expect(shown == '/mnt/data/m1plus/boot-logo.jpg' and files == {}, f'an imported logo is shown; the card has none, so it goes for the next boot: {shown} {files}')
    _, _, shown, _, _ = boot(data=made, rotate=True, mounted=False, wait=2)
    expect(shown == '/mnt/data/m1plus/boot-logo180.jpg', f'rotated: its 180 twin: {shown}')

    # ---- the import ----
    real = open(os.path.join(mb.ROOT, 'assets', 'boot-logo.jpg'), 'rb').read()   # a real 320x480 JPEG: its header is read as is
    rc, out, shown, files, calls = boot(card=real)
    expect(rc == 0 and out == b'' and shown.endswith('xx/logo.jpg'), f'a new card logo shows from the next boot, quietly: {rc} {out!r} {shown}')
    expect(files.get('boot-logo.jpg') == 'scale=320:480\n' and files.get('boot-logo180.jpg') == 'hflip,vflip\n' and 'boot-logo.md5' in files
           and len(files) == 3, f'stretched to 320x480, a turned twin, the md5 kept, no temporary left: {files}')
    expect(len(calls) == 2 and all(c.startswith('-nostdin') and '-frames:v 1' in c for c in calls) and '-max_pixels 8388608 -i ' in calls[0]
           and calls[1].split(' -i ')[1].split()[0].endswith('boot-logo.tmp.jpg'), f'two ffmpeg runs, the turned one from the small copy: {calls}')
    md5 = {'boot-logo.md5': files['boot-logo.md5'].encode()}
    _, _, _, files2, calls = boot(data={**made, **md5}, card=real)
    expect(calls == [] and files2 == {'boot-logo.jpg': 'up', 'boot-logo180.jpg': 'down', **{k: v.decode() for k, v in md5.items()}},
           f'the same file again: no conversion: {calls} {files2}')
    _, _, _, files2, calls = boot(data={**made, **md5}, card=jpeg(640, 960))
    expect(len(calls) == 2 and files2['boot-logo.jpg'] == 'scale=320:480\n' and files2['boot-logo.md5'] != files['boot-logo.md5'], f'a changed file: converted again: {files2}')
    _, _, _, files2, _ = boot(data={**made, **md5})
    expect(files2 == {}, f'the card without the file: the imported logo is deleted: {files2}')
    _, _, _, files2, calls = boot(data={**made, **md5}, mounted=False, wait=2)
    expect(calls == [] and set(files2) == set(made) | set(md5), f'no card mounted (/tmp/mmc_add there all the same): the logo stays: {files2}')

    # ---- a failed conversion is tried again; a refused file is not ----
    _, _, _, files2, calls = boot(data=made, card=jpeg(320, 480), ffail=True)
    expect(len(calls) == 1 and files2 == {k: v.decode() for k, v in made.items()}, f'a failed conversion: the old logo stays, no temporary, no md5: {calls} {files2}')
    _, _, _, files2, calls = boot(data=made, card=jpeg(320, 480))
    expect(len(calls) == 2 and files2.get('boot-logo.jpg') == 'scale=320:480\n' and 'boot-logo.md5' in files2, f'the next boot tries again and installs it: {files2}')
    for card, why in ((b'not a jpeg', 'not a JPEG'), (jpeg(4097, 100), 'over 4096 px wide'), (jpeg(100, 4097), 'over 4096 px high'),
                      (jpeg(4096, 2049), 'over 8 megapixels'), (b'\xff\xd8\xff\xe0\x00\x10' + b'\x00' * 14 + b'\xff\xd9', 'no frame header')):
        _, _, _, files2, calls = boot(data=made, card=card)
        expect(calls == [] and files2.get('boot-logo.jpg') == 'up' and 'boot-logo.md5' in files2, f'{why}: refused before decoding, the old logo stays, the md5 kept: {calls} {files2}')
        _, _, _, _, calls = boot(data={**made, 'boot-logo.md5': files2['boot-logo.md5'].encode()}, card=card)
        expect(calls == [], f'{why}: the same file is not looked at again')
    for card, why in ((jpeg(4096, 2048), 'exactly 8 megapixels'), (jpeg(2048, 3072, sof=0xC2), 'progressive'),
                      (jpeg(320, 480, app=2 * (b'\xff\xe1\xfd\xe8' + b'E' * 64998)), 'after two 64 KiB EXIF segments')):
        _, _, _, files2, calls = boot(card=card)
        expect(len(calls) == 2 and files2.get('boot-logo.jpg') == 'scale=320:480\n', f'{why}: converted: {calls} {files2}')
    # a second frame header: jpeg_size reads the first (320x480), ffmpeg follows the later one; the decoder's -max_pixels holds
    sof = lambda w, h: b'\xff\xc0' + struct.pack('>HBHHB', 17, 8, h, w, 3) + bytes(9)
    _, _, _, files2, calls = boot(card=jpeg(5000, 2000, app=sof(320, 480)))
    expect(len(calls) == 2 and '-max_pixels 8388608 -i ' in calls[0], f'a second frame header: passes jpeg_size, so the decoder bounds it: {calls}')
    ff = shutil.which('ffmpeg')
    expect(ff is not None, 'the host has ffmpeg for the real-decoder cases (docs/workflow.md Setup, make doctor)')
    if ff:
        with tempfile.TemporaryDirectory() as t:
            big = os.path.join(t, 'big.jpg')
            subprocess.run([ff, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=s=5000x2000', '-frames:v', '1', '-q:v', '2', big], check=True)
            d = open(big, 'rb').read()
        i = d.index(b'\xff\xc0'); fake = bytearray(d[i:i + 2 + struct.unpack('>H', d[i + 2:i + 4])[0]])
        struct.pack_into('>HH', fake, 5, 480, 320)   # the file's own frame header (its sampling, its tables), only the size changed
        _, _, _, files2, _ = boot(data=made, card=d[:2] + bytes(fake) + d[2:], ffdir=os.path.dirname(ff))
        expect(files2 == {k: v.decode() for k, v in made.items()}, f'the real ffmpeg: a 5000x2000 frame behind a 320x480 header fails, the old logo stays, no md5: {sorted(files2)}')
        _, _, _, files2, _ = boot(card=real, ffdir=os.path.dirname(ff))
        expect(sorted(files2) == ['boot-logo.jpg', 'boot-logo.md5', 'boot-logo180.jpg'], f'the real ffmpeg: the same command installs a good logo: {sorted(files2)}')
    _, _, _, files2, calls = boot(card=b'x' * (2 * 1024 * 1024 + 1))
    expect(calls == [] and files2 == {}, f'over 2 MB: ignored, not even an md5: {calls} {files2}')

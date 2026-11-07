#!/usr/bin/env python3
"""A newer Wi-Fi supplicant: hostap wpa_supplicant 2.12 cross-built here and installed beside the stock 2.9.

Stock /usr/sbin/wpa_supplicant (v2.9) has only EAP-WSC, no SAE (WPA3-Personal) and no OWE (Enhanced Open). This step
builds hostap's wpa_supplicant with PEAP, TTLS, TLS, MSCHAPv2, GTC, MD5, PWD, SAE, OWE, PMF and WPS (assets/wpa/config)
and ships it as /usr/lib/m1plus/wpa_supplicant. The stock binary is untouched; only /usr/bin/wifi_connect.sh changes
(pinned by SHA-256): it starts ours when /mnt/mmc/m1plus-off is absent and `-v` runs, else the stock one exactly as
before. docs/modules/wifi.md has the facts, the fallback and the device probe.

Build (reproducible; nothing is run on the Mac):
  * sources: the pinned hostap tarball, pinned Debian buster (mipsel) header packages (glibc 2.28, kernel UAPI,
    OpenSSL 1.1.1, libnl 3.4) extracted to a sysroot of headers only, all from `mod_wpa.py --fetch` into
    work/cache/wpa/dl. Downloads are data: unpacked with tarfile's data filter, never executed.
  * Homebrew clang + lld, --target=mipsel-linux-gnu -march=mips32r2 -mabi=32 -mnan=2008 -mfp64, dynamic, interpreter
    /lib/ld-linux-mipsn8.so.1, -Os, stripped. It links against the stock .so files (read, never executed).
  * Debian's crt1/crti/crtn and libc_nonshared are legacy-NaN and lld refuses to mix NaN modes, so assets/wpa/start.S and
    assets/wpa/shim.c provide the entry point, init/fini and the libc_nonshared wrappers (atexit, stat).
  * verify() fails the build unless the ELF matches the stock supplicant (type, e_flags, interpreter), every NEEDED
    library is on the stock rootfs and every imported symbol, with its version, is exported by the stock library that
    the binary would load (so GLIBC_<= 2.28, OPENSSL_1_1_0 ...).

Usage: mod_wpa.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
       mod_wpa.py --fetch                      download and verify the pinned inputs
       mod_wpa.py --build                      build and verify the binary only (prints its path)
"""
import argparse, hashlib, io, lzma, os, shutil, subprocess, sys, tarfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from modlib import clone_workdir, write_keep_mode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets', 'wpa')
LLVM = os.environ.get('LLVM_BIN', '/opt/homebrew/opt/llvm/bin')
LLD = os.environ.get('LLD_BIN', '/opt/homebrew/opt/lld/bin')

HOSTAP_VERSION = '2.12'
HOSTAP = ('https://w1.fi/releases/wpa_supplicant-2.12.tar.gz',
          '08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6')   # w1.fi release of 2026-08-07
DEBIAN = 'https://archive.debian.org/debian/'
DEBS = [   # Debian 10 (buster) mipsel: headers only; sha256 from its Packages index
    ('pool/main/g/glibc/libc6-dev_2.28-10+deb10u1_mipsel.deb', 'e28bac8637e98d78045f0fd05613ed2ab298fb1aa6387633b6d609119774d590'),
    ('pool/main/l/linux/linux-libc-dev_4.19.249-2_mipsel.deb', '5f6ca1c34bb326b38fa44838b1ed051c33a2591bf7bfa26276e54fc85c00427c'),
    ('pool/main/o/openssl/libssl-dev_1.1.1n-0+deb10u3_mipsel.deb', '710270c387e7bd92630cda35d804c671ce607ea4bb47855a092502b6d0939864'),
    ('pool/main/libn/libnl3/libnl-3-dev_3.4.0-1_mipsel.deb', '97940b112bf1f0d4477262529f4e3190462948b9daee0c92d4b457a9baa166f3'),
    ('pool/main/libn/libnl3/libnl-genl-3-dev_3.4.0-1_mipsel.deb', '8f0f7a3e8c87054c126968fa0faf795eb5df108f09395f6d2a3c6caddfc09401'),
]
CACHE = os.path.join(paths.ROOT, 'work', 'cache', 'wpa')   # per checkout like work/cache/build (tools/buildcache.py); the checks run with another M1_WORK
DL = os.path.join(CACHE, 'dl')

# the stock libraries the binary links (soname -> path on the stock rootfs); the link-time names are symlinks to them
LIBS = {'libc.so.6': 'lib/libc.so.6', 'libm.so.6': 'lib/libm.so.6', 'libdl.so.2': 'lib/libdl.so.2',
        'libpthread.so.0': 'lib/libpthread.so.0', 'librt.so.1': 'lib/librt.so.1', 'libgcc_s.so.1': 'lib/libgcc_s.so.1',
        'libssl.so.1.1': 'usr/lib/libssl.so.1.1', 'libcrypto.so.1.1': 'usr/lib/libcrypto.so.1.1',
        'libnl-3.so.200': 'usr/lib/libnl-3.so.200', 'libnl-genl-3.so.200': 'usr/lib/libnl-genl-3.so.200'}
STOCK_BIN = 'usr/sbin/wpa_supplicant'
INTERP = '/lib/ld-linux-mipsn8.so.1'

# packaging
REL_DIR, REL_BIN = 'usr/lib/m1plus', 'usr/lib/m1plus/wpa_supplicant'
SCRIPT = 'usr/bin/wifi_connect.sh'
SCRIPT_SHA = '24676db6000993d7838d2225c10c7cbe015acbb8cada4952284b7f1bee82e332'   # stock V2.1
MODE, MTIME = 0o755, 1750924035   # stock /usr/bin mode; a stock mtime, so the build is deterministic

SCRIPT_OLD = b"""\tifconfig $INTERFACE up
\twpa_supplicant -Dnl80211 -i$INTERFACE -c$WPA_CONF -B
\ttouch /tmp/wpasupplicant_initsuccess
"""
SCRIPT_NEW = b"""\tifconfig $INTERFACE up
\t# M1+ Music: the newer supplicant (WPA-Enterprise, WPA3, Enhanced Open) unless the kill switch exists or it cannot
\t# run; otherwise stock's, exactly as before
\tWPA=wpa_supplicant
\tNEWWPA=/usr/lib/m1plus/wpa_supplicant
\tif [ ! -e /mnt/mmc/m1plus-off ] && [ -x "$NEWWPA" ] && "$NEWWPA" -v > /dev/null 2>&1; then
\t\tWPA=$NEWWPA
\tfi
\tCONF=$WPA_CONF
\trm -f /tmp/m1plus-wpa.conf
\t# the newer supplicant reads a copy: the stock configuration, then the networks stock 2.9 cannot read (WPA3, Enhanced Open,
\t# Enterprise), which the Wi-Fi page keeps in wifi-networks and writes apart again after each save; stock reads the real file only
\tif [ "$WPA" = "$NEWWPA" ] \\
\t\t&& { cat "$WPA_CONF"; echo; [ ! -f /mnt/data/m1plus/wifi-networks ] || cat /mnt/data/m1plus/wifi-networks; } > /tmp/m1plus-wpa.conf 2> /dev/null; then
\t\tCONF=/tmp/m1plus-wpa.conf
\tfi
\t"$WPA" -Dnl80211 -i$INTERFACE -c$CONF -B
\tRC=$?
\t# ours did not start (a configuration it cannot read, such as a saved WEP network: WEP is not built in): stock's starts instead
\tif [ $RC != 0 ] && [ "$WPA" = "$NEWWPA" ]; then
\t\tWPA=wpa_supplicant
\t\tCONF=$WPA_CONF
\t\trm -f /tmp/m1plus-wpa.conf
\t\t"$WPA" -Dnl80211 -i$INTERFACE -c$CONF -B
\t\tRC=$?
\tfi
\ttouch /tmp/wpasupplicant_initsuccess
"""


def rewrite_script(old):
    """Stock's wifi_connect.sh with the supplicant start replaced; refuses any other input."""
    check(sha256(old) == SCRIPT_SHA, f'/{SCRIPT}: not the stock script')
    check(old.count(SCRIPT_OLD) == 1, f'/{SCRIPT}: start lines not found')
    return old.replace(SCRIPT_OLD, SCRIPT_NEW)


def sha256(b): return hashlib.sha256(b).hexdigest()
def fail(msg): raise SystemExit(f'mod_wpa: {msg}')
def check(ok, msg):
    if not ok: fail(msg)


# ---- fetch ---------------------------------------------------------------------------------------------------------
def dl_path(name):
    """A fetched file: this checkout's work/cache/wpa/dl, else the main checkout's (read-only)."""
    for base in (CACHE, os.path.join(paths.MAIN, 'work', 'cache', 'wpa')):
        p = os.path.join(base, 'dl', os.path.basename(name))
        if os.path.exists(p): return p
    return os.path.join(DL, os.path.basename(name))


def fetch():
    import urllib.request
    os.makedirs(DL, exist_ok=True)
    for url, want in [(HOSTAP[0], HOSTAP[1])] + [(DEBIAN + n, s) for n, s in DEBS]:
        path = dl_path(url)
        if not os.path.exists(path):
            print(f'downloading {url}')
            tmp = path + '.part'
            urllib.request.urlretrieve(url, tmp); os.replace(tmp, path)
        check(sha256(open(path, 'rb').read()) == want, f'{path}: SHA-256 mismatch')
        print(f'{path}: OK')


def read_input(url, want):
    path = dl_path(url)
    check(os.path.exists(path), f'missing {path}: run `uv run python -I tools/mod_wpa.py --fetch`')
    data = open(path, 'rb').read()
    check(sha256(data) == want, f'{path}: SHA-256 mismatch')
    return data


def deb_data(deb):
    """The data.tar.* member of a .deb (an ar archive) as bytes of a tar."""
    check(deb[:8] == b'!<arch>\n', 'not a .deb')
    off = 8
    while off + 60 <= len(deb):
        name = deb[off:off + 16].decode().strip().rstrip('/'); size = int(deb[off + 48:off + 58])
        body = deb[off + 60:off + 60 + size]
        if name == 'data.tar.xz': return lzma.decompress(body)
        off += 60 + size + (size & 1)
    fail('no data.tar.xz in the .deb')


def extract(tar_bytes, dest, only=None):
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        members = [m for m in t.getmembers() if only is None or only(m.name)]
        t.extractall(dest, members=members, filter='data')


# ---- build ---------------------------------------------------------------------------------------------------------
def stock_root():
    stock = paths.find_stock()
    check(stock, 'no unpacked stock tree (run make doctor / a build once)')
    return os.path.join(stock, 'rootfs')


def inputs_key(stock):
    parts = [HOSTAP[1]] + [s for _, s in DEBS]
    for f in ('config', 'start.S', 'shim.c'): parts.append(sha256(open(os.path.join(ASSETS, f), 'rb').read()))
    parts.append(sha256(open(os.path.abspath(__file__), 'rb').read()))
    for so in sorted(LIBS.values()) + [STOCK_BIN]:
        parts.append(sha256(open(os.path.realpath(os.path.join(stock, so)), 'rb').read()))
    return sha256('\n'.join(parts).encode())[:20]


def build(stock=None):
    """The verified, stripped binary (path). Cached by the hash of everything that goes into it."""
    stock = stock or stock_root()
    final = os.path.join(CACHE, 'bin', inputs_key(stock), 'wpa_supplicant')
    if os.path.exists(final):
        verify(final, stock); return final
    tarball = read_input(*HOSTAP)
    debs = [read_input(DEBIAN + n, s) for n, s in DEBS]
    work = os.path.join(CACHE, 'build'); shutil.rmtree(work, ignore_errors=True)
    src, sysroot, libdir, objdir = (os.path.join(work, d) for d in ('src', 'sysroot', 'libs', 'obj'))
    extract(tarball, src)
    for d in debs: extract(deb_data(d), sysroot, only=lambda n: n.lstrip('./').startswith('usr/include'))
    gnu = os.path.join(sysroot, 'usr/include/mipsel-linux-gnu/gnu')    # Debian ships the legacy-NaN variants only; the lists are the same
    for n in ('stubs', 'lib-names'): shutil.copyfile(f'{gnu}/{n}-o32_hard.h', f'{gnu}/{n}-o32_hard_2008.h')
    os.makedirs(libdir); os.makedirs(objdir)
    for soname, rel in LIBS.items():
        link = soname.split('.so')[0] + '.so'
        os.symlink(os.path.realpath(os.path.join(stock, rel)), os.path.join(libdir, soname))
        if not os.path.lexists(os.path.join(libdir, link)): os.symlink(soname, os.path.join(libdir, link))
    top = os.path.join(src, f'wpa_supplicant-{HOSTAP_VERSION}')
    sup = os.path.join(top, 'wpa_supplicant')
    shutil.copyfile(os.path.join(ASSETS, 'config'), os.path.join(sup, '.config'))

    cc = os.path.join(LLVM, 'clang')
    target = ['--target=mipsel-linux-gnu', '-march=mips32r2', '-mabi=32', '-mnan=2008', '-mfp64', '-fno-pic']
    inc = [f'-isystem{sysroot}/usr/include/mipsel-linux-gnu', f'-isystem{sysroot}/usr/include']
    cflags = target + ['-nostdlibinc', *inc, '-Oz', '-ffunction-sections', '-fdata-sections', '-fno-stack-protector',
                       '-D_GNU_SOURCE', '-w', f'-ffile-prefix-map={work}=.']
    ldflags = target + ['-nostdlib', '-no-pie', f'-fuse-ld={os.path.join(LLD, "ld.lld")}', f'-L{libdir}',
                        '-Wl,-s', '-Wl,-e,_start', '-Wl,--fatal-warnings', '-Wl,--gc-sections', '-Wl,--build-id=none', '-Wl,-z,noexecstack', f'-Wl,--dynamic-linker={INTERP}',
                        os.path.join(objdir, 'start.o'), os.path.join(objdir, 'shim.o'),
                        '-lc', '-lm', '-ldl', '-lpthread', '-lgcc_s']
    run([cc, *target, '-c', os.path.join(ASSETS, 'start.S'), '-o', os.path.join(objdir, 'start.o')])
    run([cc, *cflags, '-c', os.path.join(ASSETS, 'shim.c'), '-o', os.path.join(objdir, 'shim.o')])
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'CC': cc, 'CFLAGS': ' '.join(cflags),
           'LDFLAGS': ' '.join(ldflags), 'PKG_CONFIG': 'false'}
    log = run(['make', '-C', sup, f'-j{os.cpu_count() or 4}', 'wpa_supplicant', 'CONFIG_NO_GITVER=y',
         f'LIBNL_INC={sysroot}/usr/include/libnl3'], env=env)
    open(os.path.join(CACHE, 'build.log'), 'w').write(log)
    built = os.path.join(sup, 'wpa_supplicant.stripped')
    # lld writes a 77 KB .pdr (procedure descriptors, debugger-only, never loaded) that the linker's -s keeps; drop it and the notes
    run([os.path.join(LLVM, 'llvm-objcopy'), '-R', '.pdr', '-R', '.comment', '-R', '.mdebug.abi32',
         os.path.join(sup, 'wpa_supplicant'), built])
    verify(built, stock)
    os.makedirs(os.path.dirname(final))
    shutil.copyfile(built, final)
    shutil.rmtree(work, ignore_errors=True)
    return final


def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
    if r.returncode: fail(f'{" ".join(cmd[:3])} ... failed ({r.returncode}):\n{r.stdout[-6000:]}')
    return r.stdout


# ---- verification --------------------------------------------------------------------------------------------------
def elf_info(path):
    """e_type, e_flags, interpreter, NEEDED, imported (name, soname-or-None, version-or-None) and the PT_GNU_STACK flags."""
    from elftools.elf.elffile import ELFFile
    with open(path, 'rb') as f:
        e = ELFFile(f)
        check(e.elfclass == 32 and e.little_endian and e['e_machine'] == 'EM_MIPS', f'{path}: not a 32-bit LE MIPS ELF')
        interp = next((s.get_interp_name() for s in e.iter_segments() if s['p_type'] == 'PT_INTERP'), None)
        stack = next((s['p_flags'] for s in e.iter_segments() if s['p_type'] == 'PT_GNU_STACK'), None)
        dyn = e.get_section_by_name('.dynamic')
        needed = [t.needed for t in dyn.iter_tags() if t.entry.d_tag == 'DT_NEEDED']
        dynsym = e.get_section_by_name('.dynsym')
        vers = e.get_section_by_name('.gnu.version')
        verneed = e.get_section_by_name('.gnu.version_r')
        need_by_idx = {}
        if verneed:
            for vn, auxes in verneed.iter_versions():
                for a in auxes: need_by_idx[a['vna_other']] = (vn.name, a.name)
        imports = []
        for i, s in enumerate(dynsym.iter_symbols()):
            if s['st_shndx'] != 'SHN_UNDEF' or not s.name: continue
            idx = vers.get_symbol(i)['ndx'] if vers else None
            lib, ver = need_by_idx.get(idx, (None, None)) if isinstance(idx, int) else (None, None)
            imports.append((s.name, lib, ver, s['st_info']['bind']))
        return {'type': e['e_type'], 'flags': e['e_flags'], 'interp': interp, 'needed': needed, 'imports': imports,
                'stack': stack}


def exports(path):
    """{name: set(version or None)} of the symbols a shared object defines."""
    from elftools.elf.elffile import ELFFile
    out = {}
    with open(path, 'rb') as f:
        e = ELFFile(f)
        dynsym, vers, verdef = (e.get_section_by_name(n) for n in ('.dynsym', '.gnu.version', '.gnu.version_d'))
        names = {}
        if verdef:
            for vd, auxes in verdef.iter_versions():
                names[vd['vd_ndx']] = next(iter(auxes)).name
        for i, s in enumerate(dynsym.iter_symbols()):
            if s['st_shndx'] == 'SHN_UNDEF' or not s.name: continue
            ndx = vers.get_symbol(i)['ndx'] if vers else 1
            out.setdefault(s.name, set()).add(names.get(ndx & 0x7fff) if isinstance(ndx, int) else None)
    return out


def verify(path, stock):
    """Fail unless `path` can load on the stock rootfs the way the stock supplicant does."""
    data = open(path, 'rb').read()
    check(data[:4] == b'\x7fELF', f'{path}: not an ELF')
    new, old = elf_info(path), elf_info(os.path.join(stock, STOCK_BIN))
    check(new['type'] == old['type'] == 'ET_EXEC', f'e_type {new["type"]} != stock {old["type"]}')
    check(new['flags'] == old['flags'], f'e_flags {new["flags"]:#x} != stock {old["flags"]:#x} (NaN2008, o32, mips32r2, cpic)')
    check(new['flags'] & 0x400 and new['flags'] & 0x1000, 'e_flags lack NaN2008 / o32')
    check(new['interp'] == INTERP == old['interp'], f'interpreter {new["interp"]}')
    check(new['stack'] is not None and not new['stack'] & 1, 'stack is executable or PT_GNU_STACK is missing')
    check(not set(new['needed']) - set(LIBS), f'unexpected NEEDED {sorted(set(new["needed"]) - set(LIBS))}')
    libs = {}
    for soname in new['needed']:
        p = os.path.join(stock, LIBS[soname])
        check(os.path.exists(p), f'{soname} is not on the stock rootfs')
        libs[soname] = exports(p)
    for name, lib, ver, bind in new['imports']:
        if bind == 'STB_WEAK' and name in ('__gmon_start__', '_ITM_deregisterTMCloneTable', '_ITM_registerTMCloneTable',
                                          '__cxa_finalize', '_Jv_RegisterClasses'):
            continue
        if lib:
            check(lib in libs, f'{name}@{ver}: from {lib}, which is not NEEDED')
            check(ver in libs[lib].get(name, ()), f'{name}@{ver} is not exported by the stock {lib}')
        else:
            check(any(name in e for e in libs.values()), f'{name} is exported by no stock library the binary loads')
        if lib == 'libc.so.6' or (ver or '').startswith('GLIBC_'):
            v = tuple(int(x) for x in ver.removeprefix('GLIBC_').split('.') if x.isdigit())
            check(ver.startswith('GLIBC_') and v <= (2, 28), f'{name}@{ver}: newer than the stock glibc 2.28')
    return new


# ---- packaging -----------------------------------------------------------------------------------------------------
def added_rels(stock_rootfs=None):
    return ['usr/lib/m1plus', REL_BIN]


def apply(out):
    stock = stock_root()
    binary = build(stock)
    root = os.path.join(out, 'rootfs')
    d = os.path.join(root, REL_DIR)
    assert not os.path.exists(d), d
    os.mkdir(d); os.chmod(d, 0o755); os.utime(d, (MTIME, MTIME))
    dst = os.path.join(root, REL_BIN)
    shutil.copyfile(binary, dst); os.chmod(dst, MODE); os.utime(dst, (MTIME, MTIME))
    # Installing the binary changes the directory mtime; normalize it after the last child is written.
    os.utime(d, (MTIME, MTIME))
    script = os.path.join(root, SCRIPT)
    old = open(script, 'rb').read()
    write_keep_mode(script, rewrite_script(old))
    print(f'wpa: /{REL_BIN} ({os.path.getsize(dst)} bytes, hostap {HOSTAP_VERSION}); /{SCRIPT} starts it unless /mnt/mmc/m1plus-off')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('dirs', nargs='*'); ap.add_argument('--fetch', action='store_true'); ap.add_argument('--build', action='store_true')
    a = ap.parse_args()
    if a.fetch: fetch()
    elif a.build: print(build())
    else:
        check(len(a.dirs) == 2, 'usage: mod_wpa.py SRC_WORKDIR OUT_WORKDIR')
        clone_workdir(*a.dirs); apply(a.dirs[1])

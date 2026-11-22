"""Firmware/font inputs may be shared read-only; work and out always belong to this checkout.

uv owns Python and its dependencies. This module only resolves project data paths.
Run `uv run python -I tools/paths.py` to see those paths.
"""
import os, subprocess, zipfile, zlib, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _main_checkout():
    try:
        r = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                           capture_output=True, text=True, timeout=10)
        common = r.stdout.strip()
        if r.returncode == 0 and common and os.path.basename(common) == '.git':
            return os.path.dirname(common)
    except (OSError, subprocess.SubprocessError): pass
    return ROOT

MAIN = _main_checkout()

def resolve(rel):
    """rel under this checkout if it exists there, else under the main checkout if it exists
    there, else the local path (so error messages name the local file)."""
    for base in (ROOT, MAIN):
        p = os.path.join(base, rel)
        if os.path.exists(p): return p
    return os.path.join(ROOT, rel)

ZIP = resolve('firmware/M1 Plus Firmware V2.1.zip')
SHS_ZIP = resolve('fonts/01_SourceHanSans.ttc.zip')
WORK = os.path.abspath(os.environ.get('M1_WORK') or os.path.join(ROOT, 'work'))
OUT = os.path.abspath(os.environ.get('M1_OUT') or os.path.join(ROOT, 'out'))

def _zip_member(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return z.getinfo([n for n in z.namelist() if n.endswith('update.bin')][0])

def _crc(path):
    c = 0
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): c = zlib.crc32(b, c)
    return c

def stock_matches(stock, zip_path):
    """True if the unpacked tree `stock` came from this zip: its meta.json names the update.bin it
    was unpacked from, and that file's CRC-32 equals the zip member's."""
    try:
        src = json.load(open(os.path.join(stock, 'meta.json')))['source']
        return os.path.exists(os.path.join(stock, 'rootfs')) and os.path.exists(src) \
            and _crc(src) == _zip_member(zip_path).CRC
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, IndexError): return False

_stock_found = {}   # (zip, WORK) -> the tree found: the CRC-32 of the 61 MB update.bin is read once per process; a miss is never kept (build.py unpacks, then asks again)

def find_stock(zip_path=ZIP):
    """WORK/stock if it is unpacked, else this checkout's work/stock, else the main checkout's, if
    it matches the zip. Runs with another M1_WORK (make dev, the checks) thus share one tree.
    Callers must treat the result as read-only. None: unpack one locally."""
    key = (zip_path, WORK)
    if key not in _stock_found:
        found = _find_stock(zip_path)
        if found: _stock_found[key] = found
        return found
    return _stock_found[key]

def _find_stock(zip_path):
    seen = set()
    for base in (WORK, os.path.join(ROOT, 'work'), os.path.join(MAIN, 'work')):
        stock = os.path.realpath(os.path.join(base, 'stock'))
        if stock in seen: continue
        seen.add(stock)
        if stock_matches(stock, zip_path): return stock
    return None

if __name__ == '__main__':
    # every path absolute, so it can be pasted into a command from any directory
    for k in ('ROOT', 'MAIN', 'ZIP', 'SHS_ZIP', 'WORK', 'OUT'): print(f'{k:8} {os.path.abspath(globals()[k])}')
    stock = find_stock() if os.path.exists(ZIP) else None
    print(f'{"STOCK":8} {os.path.abspath(stock) if stock else None}')
    print(f'{"DEMO":8} {os.path.join(os.path.abspath(stock), "rootfs", "release", "bin", "demo") if stock else None}')
    print(f'{"TREE":8} {os.path.join(WORK, "mod-release")}   (the built release tree, after build.py)')

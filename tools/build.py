#!/usr/bin/env python3
"""One-shot build: official zip in firmware/ -> flashable package in out/.

  build.py             the release, M1+ Music (docs/architecture.md): the asset looks (docs/ui.md) and the
                       code payload on the official V2.1 rootfs -> out/M1Plus-<TAG>-release-update.bin
  build.py --restore   stock images with a new version tag (the way back after a mod)
  build.py --tree-only the release tree in work/mod-release only (what the tests need; no package)
  build.py --pack-only package an existing work/mod-release tree (the second half of a full build)
  build.py --no-cache  ignore work/cache/build (tools/buildcache.py; same as M1_NO_CACHE=1)

Use --dev for a fresh test tag; only integration edits VERSION (docs/workflow.md).
Pins the official zip by SHA-256 so a wrong or corrupted input
is refused. Every stage prints its time; "cached" marks a stage reused from work/cache/build.
"""
import argparse, hashlib, importlib, os, re, subprocess, sys, time, zipfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import mod_space, paths, workflow
from pathlib import Path

ZIP = paths.ZIP     # this checkout's firmware/, else the main checkout's (tools/paths.py)
ZIP_SHA = 'db7bdbc42ffe6d5c1e3fdca9363edb78a01898b9a725c34793394cf6abfa33c0'
VERSION = '1.2.1'  # major.minor.patch: the release, its git tag and GitHub release, About
TAG = 'V2.1-' + VERSION  # what the updater compares (firmware_v20.info line 2: must contain V and differ from V2.1)
REPO = 'iamgauravmishra/m1plus-music-navidrome'  # this project's releases; the payload gets it as M1PLUS_REPO (tools/pod.py)
RESTORE_TAG = 'V2.1R'


def about(tag):
    """The About row's text: the semantic version of a release tag, a dev tag as it is."""
    return tag.removeprefix('V2.1-')


# The asset steps after the payload, in order: name -> (module, extra args). Each
# tools/<module>.py WORKDIR WORKDIR [args] edits the tree in place (venv python: Pillow, fontTools);
# <module>.added_rels(stock rootfs, *args), where defined, lists the files it adds (fwtool --allow-added).
# The battery step runs first and the font right after it, before anything that measures text.
STEPS = [('mod_theme', []), ('mod_lists', []), ('mod_nowplaying', []), ('mod_boot', []),
         ('mod_ipodrows', []), ('mod_pulldown', []), ('mod_lockscreen', []), ('mod_wallpaper', []),
         ('mod_icons', []), ('mod_strings', []), ('mod_polish', []), ('mod_overlays', []),
         ('mod_cacerts', [])]
BASE = ('mod_battery', 'mod_font', 'mod_space')     # stock tree -> battery art, font, space (cached as one stage)

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''): h.update(c)
    return h.hexdigest()

# the steps need Pillow, fontTools or pyelftools: run them with the repo venv
def run(*cmd):
    t = time.time(); subprocess.run([sys.executable, '-I', *cmd], check=True)
    print(f'  [{time.time() - t:5.1f}s] {os.path.basename(cmd[0])}', flush=True)

def stage_report(what, t, cached): print(f'  [{time.time() - t:5.1f}s] {what}{" (cached)" if cached else ""}', flush=True)

def make_tree(stock, mod, cache, tag=TAG):
    """stock -> the finished release tree, every stage through tools/buildcache.py."""
    import buildcache as bc
    bc.ENABLED = bc.ENABLED and cache
    t = time.time(); key = bc.base_key(ZIP_SHA, *BASE)
    cached = bc.restore_base(key, mod)
    if not cached:
        run(os.path.join(TOOLS, 'mod_battery.py'), stock, mod)
        run(os.path.join(TOOLS, 'mod_font.py'), mod, mod)                  # before anything measures text
        run(os.path.join(TOOLS, 'mod_space.py'), mod)                      # .pdr zero + remove + theme1 tree
        bc.store_base(key, mod)
    stage_report('base: battery, font, space', t, cached)
    before = bc.snap(mod)
    run(os.path.join(TOOLS, 'pod.py'), mod, '--tag', tag)
    changed, removed, _ = bc.delta_since(before, mod)
    prev = bc.H('pod', key, bc.delta_sha(mod, changed, removed))
    for module, args in STEPS:
        t = time.time(); prev = bc.step_key(prev, module, args)
        if bc.have_step(prev): bc.apply_delta(prev, mod); stage_report(module, t, True); continue
        before = bc.snap(mod)
        run(os.path.join(TOOLS, module + '.py'), mod, mod, *args)
        if bc.ENABLED:
            changed, removed, _ = bc.delta_since(before, mod); bc.store_delta(prev, mod, changed, removed)
    t = time.time(); prev = bc.step_key(prev, 'mod_theme', ['--scan'])     # contrast scan of the finished tree: a pass is kept as an empty step
    if bc.have_step(prev): stage_report('mod_theme --scan', t, True); return
    run(os.path.join(TOOLS, 'mod_theme.py'), '--scan', mod, stock)
    if bc.ENABLED: bc.store_delta(prev, mod, [], [])

def pack_args(stock):
    """The --allow-added / --allow-removed flags of the release repack."""
    import pod_pages, pod_ui
    added = [x for rel in pod_ui.asset_rels(pod_pages.PAGES) for x in ('--allow-added', rel)]
    for module, args in [(m, []) for m in BASE] + STEPS:
        rels = getattr(importlib.import_module(module), 'added_rels', None)
        added += [x for rel in (rels(os.path.join(stock, 'rootfs'), *args) if rels else []) for x in ('--allow-added', rel)]
    removed = [*mod_space.REMOVE, *mod_space.theme1_paths(os.path.join(stock, 'rootfs'))]
    return [x for p in removed for x in ('--allow-removed', p)], added

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--restore', action='store_true')
    ap.add_argument('--tree-only', action='store_true'); ap.add_argument('--pack-only', action='store_true')
    ap.add_argument('--no-cache', action='store_true')
    ap.add_argument('--dev', action='store_true', help='allocate a development tag without editing TAG')
    ap.add_argument('--out', type=Path, help='dev artifact directory (tree, update.bin, logs and receipts)')
    a = ap.parse_args()
    if a.dev and a.restore: ap.error('--dev and --restore are mutually exclusive')
    if a.out and not a.dev: ap.error('--out requires --dev')
    if a.tree_only and a.pack_only: ap.error('choose --tree-only or --pack-only')
    if a.no_cache: os.environ['M1_NO_CACHE'] = '1'   # the steps' own caches too (mod_icons' rsvg renders)
    if sys.version_info[:2] != (3, 15): sys.exit('Python 3.15 is required; run with uv run python -I')
    if not os.path.exists(ZIP): sys.exit(f'missing {ZIP}')
    if sha256(ZIP) != ZIP_SHA: sys.exit('firmware zip SHA-256 mismatch: not the pinned V2.1 package')
    work, outdir = paths.WORK, paths.OUT; os.makedirs(work, exist_ok=True); os.makedirs(outdir, exist_ok=True)
    stock = paths.find_stock(ZIP) or os.path.join(work, 'stock')   # a shared stock tree is read-only
    if not os.path.exists(os.path.join(stock, 'meta.json')):
        with zipfile.ZipFile(ZIP) as z:
            name = [n for n in z.namelist() if n.endswith('update.bin')][0]
            z.extract(name, work)
        run(os.path.join(TOOLS, 'fwtool.py'), 'unpack', os.path.join(work, name), stock)
    fwtool = os.path.join(TOOLS, 'fwtool.py')
    if a.restore:
        if a.tree_only: return
        out = os.path.join(outdir, f'M1Plus-{RESTORE_TAG}-stock-restore-update.bin')
        run(fwtool, 'repack', stock, out, '--version', RESTORE_TAG, '--reuse-squashfs',
            '--build-dir', os.path.join(work, 'build-restore'))
    else:
        directory = (a.out.resolve() if a.out else workflow.new_dev_dir()) if a.dev else None
        if a.dev and a.pack_only and not a.out: ap.error('--dev --pack-only requires --out')
        mod = str(directory / 'tree') if a.dev else os.path.join(work, 'mod-release')
        manifest = Path(mod) / 'build.json'
        if a.pack_only:
            record = workflow.validate_tree(mod)
            tag = record['tag']
            if record['mode'] != ('dev' if a.dev else 'release'): sys.exit('build mode differs from the tree manifest')
            if not a.dev and tag != TAG: sys.exit('release TAG differs from the built tree; rebuild it')
        else:
            if a.dev and manifest.exists(): sys.exit('dev directory already contains a build; use a fresh directory')
            tag = directory.name if a.dev else TAG
            if a.dev and not re.fullmatch(r'V2\.1z[A-Z]{8}', tag):
                sys.exit('dev output directory must use an allocated development tag')
            inputs = workflow.input_key()
            make_tree(stock, mod, not a.no_cache, tag)
            if workflow.input_key() != inputs: sys.exit('source changed during the build; rebuild before testing or packing')
            record = {'tag': tag, 'mode': 'dev' if a.dev else 'release', 'inputs': inputs, 'sources': workflow.source_key(),
                      'demo_sha256': workflow.sha(Path(mod) / 'rootfs/release/bin/demo'),
                      'elf_sha256': workflow.sha(Path(mod) / 'podbuild/patch.elf'),
                      'environment': workflow.environment(), 'tree': workflow.tree_key(mod)}
            workflow.write(manifest, record)
        print(f'build: {directory or mod} ({tag})', flush=True)
        if a.tree_only: return
        removed, added = pack_args(stock)
        out = str(directory / 'update.bin') if a.dev else os.path.join(outdir, f'M1Plus-{tag}-release-update.bin')
        run(fwtool, 'repack', mod, out, '--version', tag, '--tailends', *removed, *added)
        shutil.rmtree(os.path.join(mod, 'build'), ignore_errors=True)
        # keep mod/podbuild (manifest + patch.elf) so test/patch.py can run against the built tree
    run(fwtool, 'verify', out)
    if not a.restore:
        workflow.validate_tree(mod)
        record['package_sha256'] = sha256(out)
        workflow.write(manifest, record)
    print('->', out)

if __name__ == '__main__':
    with workflow.lock('build'): main()

#!/usr/bin/env python3
"""Publish the accepted release package as a GitHub release named VERSION (e.g. 1.0.0; the package and golden row use TAG) (q2-pod's model: no local tag).

  make publish [NOTES=file.md] [PUBLISH=1] [DRY_RUN=1]
  uv run python -I tools/publish.py [--notes file.md] [--publish] [--dry-run]

Refuses unless
  - the tracked tree is clean (untracked files are ignored),
  - work/check/release/out/M1Plus-<TAG>-release-update.bin passes `fwtool verify` and its SHA-256
    and TAG are the release row of test/golden.sha256 (so `make check` ran on this commit),
  - a local git tag VERSION, if any, is on HEAD, and any GitHub release
    VERSION is still a draft.
Then writes out/publish/<VERSION>/ (the package as update.bin, SHA256SUMS, and the notes file when given), creates or refreshes the draft release with
both files (`gh release create --draft --target HEAD`: no tag is created or pushed here, GitHub
creates it at HEAD when the draft is published; if the tag was already pushed, the release uses it),
downloads the assets back and compares hashes. A new draft needs --notes; an existing draft keeps
its notes unless --notes is given (so notes edited on GitHub survive a refresh). --publish then makes the release public.
Only the release package is published; the stock restore image stays local.
"""
import argparse, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build, workflow

ROOT = build.ROOT
GOLDEN = os.path.join(ROOT, 'test', 'golden.sha256')
PACKAGE = os.path.join(ROOT, 'work', 'check', 'release', 'out', f'M1Plus-{build.TAG}-release-update.bin')
ASSETS = ('update.bin', 'SHA256SUMS')

sha256 = workflow.sha

def git(*a): return subprocess.run(['git', '-C', ROOT, *a], capture_output=True, text=True)

def gh(*a, check=True):
    r = subprocess.run(['gh', *a], capture_output=True, text=True, cwd=ROOT)
    if check and r.returncode: sys.exit(f'gh {" ".join(a)} failed: {r.stderr.strip()}')
    return r

def golden_release():
    for line in open(GOLDEN):
        f = line.split()
        if len(f) == 3 and f[2] == 'release': return f[0], f[1]
    sys.exit('test/golden.sha256 has no release row')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--publish', action='store_true', help='make the verified draft public')
    ap.add_argument('--notes', help='release notes file (required for a new draft; replaces the notes of an existing one)')
    ap.add_argument('--dry-run', action='store_true', help='check and stage only; no tag, push or upload')
    a = ap.parse_args()
    tag, ver = build.TAG, build.VERSION   # the package and golden row use tag; the git tag and GitHub release are named ver

    if git('status', '--porcelain', '--untracked-files=no').stdout.strip():
        sys.exit('tracked files have uncommitted changes: commit the integration first')
    if not os.path.isfile(PACKAGE): sys.exit(f'{PACKAGE} missing: run make check')
    r = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'tools', 'fwtool.py'), 'verify', PACKAGE])
    if r.returncode: sys.exit('fwtool verify failed')
    sha = sha256(PACKAGE); gsha, gtag = golden_release()
    if (sha, tag) != (gsha, gtag): sys.exit(f'package {sha[:12]} {tag} is not the golden release {gsha[:12]} {gtag}')
    head = git('rev-parse', 'HEAD').stdout.strip()
    at = git('rev-parse', '-q', '--verify', f'refs/tags/{ver}^{{commit}}').stdout.strip()
    if at and at != head: sys.exit(f'local tag {ver} is on {at[:10]}, not HEAD {head[:10]}')
    rel = gh('release', 'view', ver, '--json', 'isDraft', '--jq', '.isDraft', check=False)
    exists = rel.returncode == 0
    if a.notes and not os.path.isfile(a.notes): sys.exit(f'notes file {a.notes} missing')
    if not exists and not a.notes: sys.exit('a new draft needs --notes <file> (make publish NOTES=<file>)')
    if exists and rel.stdout.strip() != 'true': sys.exit(f'release {ver} is already published: bump VERSION')

    out = os.path.join(ROOT, 'out', 'publish', ver)
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    shutil.copyfile(PACKAGE, os.path.join(out, 'update.bin'))
    with open(os.path.join(out, 'SHA256SUMS'), 'w') as f: f.write(f'{sha}  update.bin\n')
    print(f'{ver} ({tag})  {sha}  HEAD {head[:10]}  staged in {os.path.relpath(out, ROOT)}')
    if a.dry_run: return print('dry run: no upload')

    files = [os.path.join(out, n) for n in ASSETS]
    if exists:
        gh('release', 'upload', ver, *files, '--clobber')
        if a.notes: gh('release', 'edit', ver, '--notes-file', a.notes)
    else:
        gh('release', 'create', ver, *files, '--draft', '--target', head, '--title', ver, '--notes-file', a.notes)
    with tempfile.TemporaryDirectory() as d:
        gh('release', 'download', ver, '--dir', d, *(x for n in ASSETS for x in ('--pattern', n)))
        for n in ASSETS:
            if sha256(os.path.join(d, n)) != sha256(os.path.join(out, n)): sys.exit(f'remote {n} differs: draft left unpublished')
    print(f'draft {ver}: remote assets verified')
    if a.publish:
        gh('release', 'edit', ver, '--draft=false', '--latest')
        print(f'published {ver}')

if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Write SOURCES.md for a release (plan §9.6, R0-4): where the source of every
component in the AAR comes from, and the SHA-256 of the source files attached
to the release for the GPL components (SOURCE-OFFER.md).

Usage: sources_md.py --assets DIR --out SOURCES.md
"""
import argparse
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lock = json.load(open(os.path.join(ROOT, "inputs.lock")))
    meta = json.load(open(os.path.join(ROOT, "sbom/components.json")))
    L = []
    w = L.append
    w(f"# Sources — {lock['release']['tag']}\n")
    w("Kaynaklar / sources of everything in `" + lock["release"]["artifact"] + "`.\n")
    w("## Inputs (inputs.lock)\n")
    w("| Input | Version | URL | SHA-256 |")
    w("|---|---|---|---|")
    for k, v in lock["inputs"].items():
        w(f"| {k} | {v['version']} | {v['url']} | `{v['sha256']}` |")
    be = lock["build_env"]
    w("")
    w(f"Build: termux-packages `{be['termux_packages']['commit']}` "
      f"({be['termux_packages']['repository']}), builder image `{be['termux_builder_image']}`, "
      f"repack image `{be['repack_image']}` ({be['repack_image_tag']}). "
      "The python-cffi recipe is `recipes/python-cffi/build.sh` in this repository.\n")
    w("## GPL Corresponding Source attached to this release (SOURCE-OFFER.md)\n")
    w("| File | SHA-256 | Origin |")
    w("|---|---|---|")
    g = lock["gpl_sources"]
    for f in g["files"]:
        p = os.path.join(a.assets, f["file"])
        got = sha(p)
        if got != f["sha256"]:
            raise SystemExit(f"{f['file']}: sha256 mismatch")
        w(f"| `{f['file']}` | `{got}` | {f['url']} |")
    for name in sorted(os.listdir(a.assets)):
        if name.startswith("termux-recipes-"):
            w(f"| `{name}` | `{sha(os.path.join(a.assets, name))}` | termux-packages `{g['upstream_termux_commit']}`: "
              "build-package.sh, scripts/, packages/readline, packages/gdbm, packages/python, packages/ncurses |")
    w("")
    w("## Components\n")
    w("| Component | Version | License | Source | Commit | Scope |")
    w("|---|---|---|---|---|---|")
    for c in meta["components"]:
        w(f"| {c['name']} | {c['version']} | {c['license']} | {c.get('vcs', c.get('purl', '-'))} | "
          f"{('`' + c['commit'] + '`') if c.get('commit') else '-'} | {c['scope']} |")
    w("")
    w("Upstream (unchanged) components were built by the upstream project with termux-packages; the commit "
      f"matching their versions is `{g['upstream_termux_commit']}` (inferred from the upstream build time; the "
      "upstream build did not record it). Each recipe there names the source tarball and its SHA-256.\n")
    with open(a.out, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

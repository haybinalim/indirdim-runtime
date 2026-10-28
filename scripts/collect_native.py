#!/usr/bin/env python3
"""Pick the R0 files out of the Termux .debs built by build_native.sh.

Only these paths are taken (everything else in the .debs is ignored):
  brotli        usr/lib/libbrotli{common,dec,enc}.so            (all ABIs)
  python-brotli site-packages/brotli.py, _brotli.*.so, brotli-<v>.dist-info/  (all ABIs)
  python-cffi   site-packages/_cffi_backend.*.so, cffi/, cffi-<v>.dist-info/ (aarch64)
No __pycache__ / .pyc is ever copied. Writes <out>/<abi>/usr/... and
<out>/<abi>/native-manifest.json (path -> sha256/size, plus the source .deb).

Usage: collect_native.py --arch ARCH --debs DIR --out DIR
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

ABI = {"aarch64": "arm64-v8a", "arm": "armeabi-v7a", "i686": "x86", "x86_64": "x86_64"}
PREFIX = "data/data/com.termux/files/"
SP = "usr/lib/python3.14/site-packages/"
SELECT = {
    "brotli": [r"usr/lib/libbrotli(common|dec|enc)\.so"],
    "python-brotli": [SP + r"brotli\.py", SP + r"_brotli\.cpython-314-[^/]+\.so", SP + r"brotli-[0-9.]+\.dist-info/.+"],
    "python-cffi": [SP + r"_cffi_backend\.cpython-314-[^/]+\.so", SP + r"cffi/.+", SP + r"cffi-[0-9.]+\.dist-info/.+"],
}
EXPECT = {"brotli": 3, "python-brotli": 3, "python-cffi": 3}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", required=True, choices=sorted(ABI))
    ap.add_argument("--debs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    abi = ABI[a.arch]
    dest = os.path.join(a.out, abi)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    pkgs = ["brotli", "python-brotli"] + (["python-cffi"] if a.arch == "aarch64" else [])
    manifest = {"abi": abi, "debs": {}, "files": {}}
    for pkg in pkgs:
        debs = glob.glob(os.path.join(a.debs, f"{pkg}_*_{a.arch}.deb"))
        if len(debs) != 1:
            raise SystemExit(f"expected one {pkg} .deb for {a.arch}, found {debs}")
        deb = debs[0]
        manifest["debs"][pkg] = {"file": os.path.basename(deb), "sha256": sha256(deb)}
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["dpkg-deb", "-x", deb, tmp], check=True)
            root = os.path.join(tmp, PREFIX)
            picked = set()
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for fn in filenames:
                    src = os.path.join(dirpath, fn)
                    rel = os.path.relpath(src, root)
                    if fn.endswith((".pyc", ".pyo")):
                        continue
                    if not any(re.fullmatch(p, rel) for p in SELECT[pkg]):
                        continue
                    # upstream ships the brotli libraries as plain files: resolve symlinks
                    real = os.path.realpath(src)
                    out = os.path.join(dest, rel)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    shutil.copyfile(real, out)
                    manifest["files"][rel] = {"sha256": sha256(out), "size": os.path.getsize(out), "deb": pkg}
                    picked.add(re.sub(r"/.*", "", rel.replace(SP, "", 1)) if rel.startswith(SP) else rel)
            if len(picked) < EXPECT[pkg]:
                raise SystemExit(f"{pkg}: expected at least {EXPECT[pkg]} top-level items, got {sorted(picked)}")
    with open(os.path.join(dest, "native-manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    for rel, m in sorted(manifest["files"].items()):
        if rel.endswith(".so"):
            print(f"{m['sha256']}  {abi}/{rel}")
    print(f"{len(manifest['files'])} files collected for {abi}")


if __name__ == "__main__":
    main()

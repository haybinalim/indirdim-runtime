#!/usr/bin/env python3
"""Deterministic R0 repack of the upstream python AAR (plan R0-3, §9.3).

Inside every jni/<abi>/libpython.zip.so:
  * curl_cffi 0.15.1b2 (package, dist-info, curl_cffi.libs) is removed and the
    official 0.17.0 cp314 wheel is unpacked as-is (arm64-v8a only; no patchelf);
  * cffi 2.0.0 -> 2.1.1 (arm64-v8a), brotli 1.2.0 -> 1.2.1 incl. libbrotli*.so
    (all ABIs) from the native build outputs;
  * certifi -> 2026.10.23, urllib3 -> 2.8.0 (wheels, all ABIs);
  * usr/etc/tls/cert.pem -> certifi 2026.10.23 cacert.pem (byte-identical copy).
In the AAR: res/raw/ytdlp -> yt-dlp 2026.10.26. Everything else is copied with
the same content, order, mode, symlink, timestamp and compression type.

Rules for entries:
  * a path that exists before and after keeps its old ZipInfo (position, mode,
    timestamps, extra fields, compression type) and gets the new content;
  * removed paths disappear; directory entries left empty disappear too;
  * new paths are appended in sorted order, using the timestamp/extra of the
    zip's first entry, mode 0600 for files, 0700 for .so files and directories,
    DEFLATE (STORED for empty files);
  * DEFLATE level 6 everywhere; the output depends only on the inputs and on
    the zlib of the pinned repack image.

Usage: repack.py --aar UPSTREAM.aar --native DIR --inputs DIR --out DIR
Outputs: <out>/<artifact>.aar, <out>/diff-manifest.txt, <out>/repack-report.json
"""
import argparse
import copy
import hashlib
import io
import json
import os
import re
import stat
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = "usr/lib/python3.14/site-packages/"
ABIS = ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"]
CURL_CFFI_ABIS = {"arm64-v8a"}
LEVEL = 6

# Path prefixes R0 owns; everything under them is replaced wholesale.
OWNED_ALL = [
    SP + "brotli-", SP + "brotli.py", SP + "_brotli.",
    SP + "certifi/", SP + "certifi-",
    SP + "urllib3/", SP + "urllib3-",
    "usr/lib/libbrotlicommon.so", "usr/lib/libbrotlidec.so", "usr/lib/libbrotlienc.so",
    "usr/etc/tls/cert.pem",
]
OWNED_ARM64 = [
    SP + "curl_cffi/", SP + "curl_cffi-", SP + "curl_cffi.libs/",
    SP + "cffi/", SP + "cffi-", SP + "_cffi_backend.",
]
# Dist-info directories that must exist after the repack (sanity).
WANT_DIST = {
    "all": ["brotli-1.2.1.dist-info", "certifi-2026.10.23.dist-info", "urllib3-2.8.0.dist-info"],
    "arm64-v8a": ["curl_cffi-0.17.0.dist-info", "cffi-2.1.1.dist-info"],
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def owned(path, abi):
    pref = OWNED_ALL + (OWNED_ARM64 if abi in CURL_CFFI_ABIS else [])
    return any(path == p.rstrip("/") + "/" or path.startswith(p) for p in pref)


def wheel_files(path):
    out = {}
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir():
                continue
            n = i.filename
            if n.endswith((".pyc", ".pyo")) or "/__pycache__/" in n:
                raise SystemExit(f"{os.path.basename(path)}: unexpected bytecode {n}")
            out[SP + n] = z.read(i)
    return out


def native_files(native_dir, abi):
    out = {}
    base = os.path.join(native_dir, abi)
    for dirpath, _, filenames in os.walk(os.path.join(base, "usr")):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, base)] = open(p, "rb").read()
    return out


def new_content(abi, a, lock_inputs):
    files = {}
    files.update(native_files(a.native, abi))
    if abi not in CURL_CFFI_ABIS:
        for k in list(files):
            if k.startswith((SP + "cffi", SP + "_cffi_backend")):
                raise SystemExit(f"{abi}: cffi must not be present on this ABI ({k})")
    for name in ("certifi_wheel", "urllib3_wheel") + (("curl_cffi_wheel",) if abi in CURL_CFFI_ABIS else ()):
        files.update(wheel_files(os.path.join(a.inputs, lock_inputs[name]["file"])))
    files["usr/etc/tls/cert.pem"] = files[SP + "certifi/cacert.pem"]
    for k in files:
        if not owned(k, abi):
            raise SystemExit(f"{abi}: new file outside the R0-owned paths: {k}")
    return files


def parents(path):
    parts = path.rstrip("/").split("/")[:-1]
    return ["/".join(parts[:i]) + "/" for i in range(1, len(parts) + 1)]


def write_entry(zf, info, data):
    zi = copy.copy(info)
    if zi.compress_type == zipfile.ZIP_DEFLATED:
        zf.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=LEVEL)
    else:
        zf.writestr(zi, data, compress_type=zipfile.ZIP_STORED)


def repack_zip(abi, old_bytes, files):
    zin = zipfile.ZipFile(io.BytesIO(old_bytes))
    infos = zin.infolist()
    template = infos[0]
    old = {i.filename: i for i in infos}
    diff, keep_dirs = [], set()
    for p in files:
        keep_dirs.update(parents(p))
    for i in infos:
        if not i.filename.endswith("/") and not owned(i.filename, abi):
            keep_dirs.update(parents(i.filename))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for i in infos:
            n = i.filename
            if n.endswith("/"):
                if n in keep_dirs:
                    write_entry(zf, i, b"")
                else:
                    diff.append(("D", n, "dir", "-"))
                continue
            if owned(n, abi):
                if n in files:
                    data = files[n]
                    od = zin.read(i)
                    write_entry(zf, i, data)
                    if od != data:
                        diff.append(("M", n, sha(od), sha(data)))
                else:
                    diff.append(("D", n, sha(zin.read(i)), "-"))
                continue
            write_entry(zf, i, zin.read(i))
        # a new directory entry only below an existing (or newly added) one;
        # upstream has no entry for "usr/" itself, so none is invented
        added_dirs, known = [], {n for n in old if n.endswith("/")}
        for d in sorted((d for d in keep_dirs if d not in old), key=lambda d: (d.count("/"), d)):
            if (d.rstrip("/").rsplit("/", 1)[0] + "/") in known:
                known.add(d)
                added_dirs.append(d)
        for d in sorted(added_dirs):
            zi = zipfile.ZipInfo(d, date_time=template.date_time)
            zi.create_system, zi.create_version, zi.extract_version = 3, template.create_version, 10
            zi.extra = template.extra
            zi.external_attr = (stat.S_IFDIR | 0o700) << 16 | 0x10
            zi.compress_type = zipfile.ZIP_STORED
            write_entry(zf, zi, b"")
            diff.append(("A", d, "-", "dir"))
        for n in sorted(p for p in files if p not in old):
            data = files[n]
            zi = zipfile.ZipInfo(n, date_time=template.date_time)
            zi.create_system, zi.create_version, zi.extract_version = 3, template.create_version, 20
            zi.extra = template.extra
            mode = 0o700 if n.endswith(".so") else 0o600
            zi.external_attr = (stat.S_IFREG | mode) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED if data else zipfile.ZIP_STORED
            write_entry(zf, zi, data)
            diff.append(("A", n, "-", sha(data)))
    return out.getvalue(), diff


def check_dist(abi, zbytes):
    names = set(zipfile.ZipFile(io.BytesIO(zbytes)).namelist())
    dists = {n[len(SP):].split("/")[0] for n in names if n.startswith(SP) and ".dist-info/" in n}
    want = WANT_DIST["all"] + (WANT_DIST["arm64-v8a"] if abi in CURL_CFFI_ABIS else [])
    missing = [d for d in want if d not in dists]
    stale = [d for d in dists if re.match(r"(brotli|certifi|urllib3|curl_cffi|cffi)-", d) and d not in want]
    if missing or stale:
        raise SystemExit(f"{abi}: dist-info missing {missing} stale {stale}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aar", required=True)
    ap.add_argument("--native", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lock = json.load(open(os.path.join(ROOT, "inputs.lock")))
    li = lock["inputs"]
    if sha(open(a.aar, "rb").read()) != li["upstream_aar"]["sha256"]:
        raise SystemExit("upstream AAR hash mismatch")
    ytdlp = open(os.path.join(a.inputs, li["ytdlp_zipimport"]["file"]), "rb").read()
    if sha(ytdlp) != li["ytdlp_zipimport"]["sha256"]:
        raise SystemExit("yt-dlp hash mismatch")
    os.makedirs(a.out, exist_ok=True)
    artifact = lock["release"]["artifact"]
    ain = zipfile.ZipFile(a.aar)
    diff_all, report = [], {"zlib": zlib.ZLIB_RUNTIME_VERSION, "abis": {}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for i in ain.infolist():
            n = i.filename
            data = ain.read(i)
            m = re.fullmatch(r"jni/([^/]+)/libpython\.zip\.so", n)
            if m:
                abi = m.group(1)
                new, diff = repack_zip(abi, data, new_content(abi, a, li))
                check_dist(abi, new)
                diff_all += [(k, f"{abi}:{p}", o, nw) for k, p, o, nw in diff]
                diff_all.append(("M", n, sha(data), sha(new)))
                report["abis"][abi] = {"old_sha256": sha(data), "new_sha256": sha(new),
                                       "changes": len(diff)}
                data = new
            elif n == "res/raw/ytdlp":
                diff_all.append(("M", n, sha(data), sha(ytdlp)))
                data = ytdlp
            write_entry(zf, i, data)
    aar_bytes = out.getvalue()
    path = os.path.join(a.out, artifact)
    with open(path, "wb") as f:
        f.write(aar_bytes)
    with open(os.path.join(a.out, "diff-manifest.txt"), "w") as f:
        f.write("# R0 diff manifest: <A|M|D> <path> <old-sha256> <new-sha256>  (A=added, M=modified, D=deleted)\n")
        for row in diff_all:
            f.write(" ".join(row) + "\n")
    report["artifact"] = artifact
    report["sha256"] = sha(aar_bytes)
    report["size"] = len(aar_bytes)
    json.dump(report, open(os.path.join(a.out, "repack-report.json"), "w"), indent=1, sort_keys=True)
    print(f"{report['sha256']}  {artifact}  ({len(aar_bytes)} bytes, zlib {report['zlib']})")


if __name__ == "__main__":
    main()

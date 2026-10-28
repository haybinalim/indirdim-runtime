#!/usr/bin/env python3
"""Content gates for the repacked AAR (plan §10.1/3-4, R0-3).

  * diff-manifest only touches the expected paths (ALLOWED);
  * AAR entries other than jni/*/libpython.zip.so and res/raw/ytdlp are
    byte-identical to upstream (libpython.so, libqjs.so, AndroidManifest.xml,
    R.txt, classes.jar, aar-metadata.properties);
  * res/raw/ytdlp is the pinned yt-dlp;
  * no .pyc/.pyo/.pth, no sitecustomize/usercustomize anywhere in the zips;
  * usr/etc/tls/cert.pem == certifi/cacert.pem, and neither contains the
    distrusted "emSign ECC Root CA - G3";
  * every RECORD hash of curl_cffi 0.17.0, certifi and urllib3 matches the zip;
  * curl_cffi/cffi exist only on arm64-v8a.
Usage: check_runtime.py --upstream UPSTREAM.aar --aar NEW.aar --diff diff-manifest.txt
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = "usr/lib/python3.14/site-packages/"
ALLOWED = [
    r"jni/[^/]+/libpython\.zip\.so",
    r"res/raw/ytdlp",
    r"[^:]+:" + re.escape(SP) + r"(brotli-[0-9.]+\.dist-info/.*|brotli\.py|_brotli\.cpython-314-[^/]+\.so)",
    r"[^:]+:" + re.escape(SP) + r"(certifi|urllib3)(/.*|-[0-9.]+\.dist-info/.*)",
    r"[^:]+:usr/lib/libbrotli(common|dec|enc)\.so",
    r"[^:]+:usr/etc/tls/cert\.pem",
    r"arm64-v8a:" + re.escape(SP) + r"(curl_cffi(/.*|\.libs/.*|-[0-9.a-z]+\.dist-info/.*)|cffi(/.*|-[0-9.]+\.dist-info/.*)|_cffi_backend\.cpython-314-[^/]+\.so)",
]
DISTRUSTED = b"emSign ECC Root CA - G3"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def record_ok(z, dist, fails, abi):
    rec = z.read(SP + dist + "/RECORD").decode()
    n = 0
    for line in rec.splitlines():
        parts = line.rsplit(",", 2)
        if len(parts) != 3 or not parts[1]:
            continue
        path, h, _ = parts
        algo, digest = h.split("=", 1)
        data = z.read(SP + path)
        got = base64.urlsafe_b64encode(hashlib.new(algo, data).digest()).rstrip(b"=").decode()
        if got != digest:
            fails.append(f"{abi}: RECORD mismatch {dist}: {path}")
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--aar", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    lock = json.load(open(os.path.join(ROOT, "inputs.lock")))
    fails, report = [], {}

    for line in open(a.diff):
        if line.startswith("#") or not line.strip():
            continue
        kind, path = line.split()[:2]
        if not any(re.fullmatch(p, path) for p in ALLOWED):
            fails.append(f"unexpected change: {kind} {path}")

    up, new = zipfile.ZipFile(a.upstream), zipfile.ZipFile(a.aar)
    if [i.filename for i in up.infolist()] != [i.filename for i in new.infolist()]:
        fails.append("AAR entry list/order differs from upstream")
    for i in up.infolist():
        n = i.filename
        if n.endswith("/") or re.fullmatch(r"jni/[^/]+/libpython\.zip\.so", n) or n == "res/raw/ytdlp":
            continue
        if sha(up.read(n)) != sha(new.read(n)):
            fails.append(f"AAR entry changed: {n}")
    if sha(new.read("res/raw/ytdlp")) != lock["inputs"]["ytdlp_zipimport"]["sha256"]:
        fails.append("res/raw/ytdlp is not the pinned yt-dlp")

    for abi in ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"]:
        z = zipfile.ZipFile(io.BytesIO(new.read(f"jni/{abi}/libpython.zip.so")))
        names = z.namelist()
        r = {"entries": len(names)}
        bad = [n for n in names if n.endswith((".pyc", ".pyo", ".pth")) or re.search(r"(^|/)(site|user)customize\.py$", n)]
        if bad:
            fails.append(f"{abi}: forbidden files: {bad[:5]}")
        cert = z.read("usr/etc/tls/cert.pem")
        cacert = z.read(SP + "certifi/cacert.pem")
        r["cert_pem_sha256"] = sha(cert)
        r["cert_pem_certificates"] = cert.count(b"-----BEGIN CERTIFICATE-----")
        if cert != cacert:
            fails.append(f"{abi}: cert.pem != certifi/cacert.pem")
        if DISTRUSTED in cert or DISTRUSTED in cacert:
            fails.append(f"{abi}: distrusted root still present")
        has_curl = any(n.startswith(SP + "curl_cffi") for n in names)
        has_cffi = any(n.startswith(SP + "_cffi_backend") for n in names)
        if abi == "arm64-v8a":
            if not (has_curl and has_cffi):
                fails.append("arm64-v8a: curl_cffi/cffi missing")
            r["record_files_curl_cffi"] = record_ok(z, "curl_cffi-0.17.0.dist-info", fails, abi)
        elif has_curl or has_cffi:
            fails.append(f"{abi}: curl_cffi/cffi must not be present")
        r["record_files_certifi"] = record_ok(z, "certifi-2026.10.23.dist-info", fails, abi)
        r["record_files_urllib3"] = record_ok(z, "urllib3-2.8.0.dist-info", fails, abi)
        report[abi] = r
        print(f"{abi}: {len(names)} entries, cert.pem {r['cert_pem_certificates']} certs, ok so far" )
    if a.json:
        json.dump({"failures": fails, "abis": report}, open(a.json, "w"), indent=1, sort_keys=True)
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

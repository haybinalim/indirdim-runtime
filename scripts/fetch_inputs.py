#!/usr/bin/env python3
"""Download the R0 inputs listed in inputs.lock and verify them.

Every file is checked against its pinned SHA-256. With --attestations the PyPI
provenance of the wheels that have one is verified (pypi-attestations), and the
yt-dlp SHA2-256SUMS file is checked against its OpenPGP signature with the
pinned key and fingerprint. Nothing is used before it is verified.

Usage: fetch_inputs.py [--out DIR] [--only NAME ...] [--attestations] [--gpl-sources]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "indirdim-runtime-ci"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(dest + ".part", dest)
            return
        except Exception as e:  # network hiccup: retry with backoff
            last = e
            time.sleep(2 ** attempt)
    raise SystemExit(f"download failed: {url}: {last}")


def fetch(name, url, want, out, filename):
    dest = os.path.join(out, filename)
    if not (os.path.exists(dest) and sha256(dest) == want):
        download(url, dest)
    got = sha256(dest)
    if got != want:
        os.remove(dest)
        raise SystemExit(f"SHA-256 mismatch for {name} ({filename}): want {want}, got {got}")
    print(f"ok  {name:18s} {filename}  {got}")
    return dest


def verify_pypi_attestation(name, spec):
    repo = spec["pypi_attestation_repository"]
    cmd = ["pypi-attestations", "verify", "pypi", "--repository", repo, "pypi:" + spec["file"]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f"PyPI attestation verification failed for {name}")
    print(f"ok  {name:18s} PyPI attestation ({repo})")


def verify_ytdlp_signature(spec, out):
    sums = os.path.join(out, "SHA2-256SUMS")
    sig = os.path.join(out, "SHA2-256SUMS.sig")
    download(spec["sums_url"], sums)
    download(spec["sig_url"], sig)
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, GNUPGHOME=home)
        key = os.path.join(ROOT, spec["openpgp_key"])
        subprocess.run(["gpg", "--batch", "--quiet", "--import", key], check=True, env=env)
        r = subprocess.run(["gpg", "--batch", "--status-fd", "1", "--verify", sig, sums],
                           capture_output=True, text=True, env=env)
        valid = [l for l in r.stdout.splitlines() if l.startswith("[GNUPG:] VALIDSIG ")]
        if r.returncode != 0 or not valid:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit("yt-dlp SHA2-256SUMS signature is not valid")
        fields = valid[0].split()
        # VALIDSIG <sig-fpr> ... <primary-fpr> is the last field
        if spec["openpgp_fingerprint"] not in (fields[2], fields[-1]):
            raise SystemExit(f"yt-dlp signature made by unexpected key: {valid[0]}")
    with open(sums) as f:
        entries = dict(reversed(l.split()) for l in f if l.strip())
    if entries.get(spec["file"]) != spec["sha256"]:
        raise SystemExit("yt-dlp hash in inputs.lock does not match the signed SHA2-256SUMS")
    print(f"ok  {'ytdlp_zipimport':18s} SHA2-256SUMS signature ({spec['openpgp_fingerprint']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "inputs"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--attestations", action="store_true")
    ap.add_argument("--gpl-sources", action="store_true")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "inputs.lock")) as f:
        lock = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    for name, spec in lock["inputs"].items():
        if a.only and name not in a.only:
            continue
        filename = spec.get("file") or os.path.basename(spec["url"])
        fetch(name, spec["url"], spec["sha256"], a.out, filename)
        if a.attestations and "pypi_attestation_repository" in spec:
            verify_pypi_attestation(name, spec)
        if a.attestations and name == "ytdlp_zipimport":
            verify_ytdlp_signature(spec, a.out)
    if a.gpl_sources:
        gdir = os.path.join(a.out, "gpl-sources")
        os.makedirs(gdir, exist_ok=True)
        for spec in lock["gpl_sources"]["files"]:
            fetch("gpl_source", spec["url"], spec["sha256"], gdir, spec["file"])


if __name__ == "__main__":
    main()

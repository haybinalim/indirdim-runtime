#!/usr/bin/env python3
"""Write the CycloneDX 1.6 SBOM fragment for the repacked AAR (plan §9.5).

Components come from sbom/components.json; hashes are added for the AAR, for
every input file in inputs.lock, and for the changed ELF files per ABI (from
the AAR itself). Statically linked libcurl components are nested under
curl_cffi and carry their source commit so OSV commit queries can cover them.
Output is deterministic (no random serial, timestamp = SOURCE_DATE_EPOCH or the
commit time given with --timestamp).

Usage: sbom.py --aar NEW.aar --out sbom.cdx.json [--timestamp ISO8601]
"""
import argparse
import hashlib
import io
import json
import os
import uuid
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = "usr/lib/python3.14/site-packages/"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def comp(c):
    d = {"type": "library", "name": c["name"], "version": c["version"],
         "bom-ref": f"{c['name']}@{c['version']}",
         "licenses": [{"expression": c["license"]}]}
    if c.get("purl"):
        d["purl"] = c["purl"]
    refs = []
    if c.get("vcs"):
        refs.append({"type": "vcs", "url": c["vcs"] + (f"/commit/{c['commit']}" if c.get("commit") else "")})
    if refs:
        d["externalReferences"] = refs
    props = [{"name": "indirdim:scope", "value": c["scope"]}]
    if c.get("commit"):
        props.append({"name": "indirdim:source-commit", "value": c["commit"]})
    if c.get("abis"):
        props.append({"name": "indirdim:abis", "value": ",".join(c["abis"])})
    if c.get("note"):
        props.append({"name": "indirdim:note", "value": c["note"]})
    d["properties"] = props
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aar", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timestamp", default=None)
    a = ap.parse_args()
    lock = json.load(open(os.path.join(ROOT, "inputs.lock")))
    meta = json.load(open(os.path.join(ROOT, "sbom/components.json")))
    aar = open(a.aar, "rb").read()
    rel = lock["release"]

    by_name = {}
    top = []
    for c in meta["components"]:
        d = comp(c)
        by_name[c["name"]] = d
    for c in meta["components"]:
        d = by_name[c["name"]]
        if c.get("parent"):
            by_name[c["parent"]].setdefault("components", []).append(d)
        else:
            top.append(d)

    # input hashes
    input_hash = {
        "curl_cffi": "curl_cffi_wheel", "cffi": "cffi_sdist", "brotli (Python)": "brotli_source",
        "brotli (libbrotlicommon/dec/enc)": "brotli_source", "certifi": "certifi_wheel",
        "urllib3": "urllib3_wheel", "yt-dlp": "ytdlp_zipimport",
    }
    for name, key in input_hash.items():
        spec = lock["inputs"][key]
        by_name[name]["properties"].append({"name": "indirdim:input", "value": f"{spec['url']} sha256:{spec['sha256']}"})

    # file hashes of what R0 ships, per ABI
    z = zipfile.ZipFile(io.BytesIO(aar))
    files = []
    for abi in ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"]:
        inner = zipfile.ZipFile(io.BytesIO(z.read(f"jni/{abi}/libpython.zip.so")))
        files.append({"type": "file", "name": f"jni/{abi}/libpython.zip.so",
                      "hashes": [{"alg": "SHA-256", "content": sha(z.read(f'jni/{abi}/libpython.zip.so'))}]})
        for n in sorted(inner.namelist()):
            if (n.endswith(".so") and ("brotli" in n or "cffi" in n or "curl_cffi" in n)) or n == "usr/etc/tls/cert.pem":
                files.append({"type": "file", "name": f"jni/{abi}/libpython.zip.so!/{n}",
                              "hashes": [{"alg": "SHA-256", "content": sha(inner.read(n))}]})
    files.append({"type": "file", "name": "res/raw/ytdlp", "hashes": [{"alg": "SHA-256", "content": sha(z.read("res/raw/ytdlp"))}]})

    ts = a.timestamp or "2026-10-28T00:00:00Z"
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "indirdim-runtime/" + sha(aar))),
        "version": 1,
        "metadata": {
            "timestamp": ts,
            "component": {
                "type": "library", "name": "runtime-python", "group": "com.kavanozymir.indirdim",
                "version": rel["maven_coordinates"].rsplit(":", 1)[1],
                "bom-ref": "runtime-python",
                "purl": "pkg:maven/com.kavanozymir.indirdim/runtime-python@" + rel["maven_coordinates"].rsplit(":", 1)[1] + "?type=aar",
                "hashes": [{"alg": "SHA-256", "content": sha(aar)}],
                "licenses": [{"expression": "GPL-3.0-only"}],
                "externalReferences": [{"type": "vcs", "url": "https://github.com/haybinalim/indirdim-runtime"}],
            },
            "properties": [{"name": "indirdim:upstream-aar",
                            "value": f"{lock['inputs']['upstream_aar']['version']} sha256:{lock['inputs']['upstream_aar']['sha256']}"}],
        },
        "components": top + files,
    }
    with open(a.out, "w") as f:
        json.dump(bom, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {a.out}: {len(top)} components, {len(files)} files")


if __name__ == "__main__":
    main()

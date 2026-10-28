#!/usr/bin/env python3
"""ELF gates for the files R0 changes (plan §10.1/2, R0-2).

For each ELF given (paths relative to an extracted runtime tree `usr/...`):
  * 16 KB: every PT_LOAD p_align >= 16384 on 64-bit ABIs (hard gate); on 32-bit
    ABIs the value is reported and must not be lower than the upstream file's.
  * DT_SONAME equals the upstream file's (when upstream has the same path).
  * DT_NEEDED: every entry resolves inside the tree (usr/lib, $ORIGIN RUNPATH) or
    to an NDK system stub library; per-file expectations from RULES.
  * Undefined symbols: every non-weak undefined dynamic symbol is defined by the
    transitive DT_NEEDED closure (tree libs + NDK API-level stubs).
  * curl_cffi/_wrapper.abi3.so exports no BoringSSL/OpenSSL symbols.

Usage: elfcheck.py --tree DIR --upstream-tree DIR --abi ABI --ndk-sysroot DIR [--api 24]
                   [--json OUT] FILE...
Exit status 1 when any hard gate fails.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

from elftools.elf.elffile import ELFFile
from elftools.elf.dynamic import DynamicSection
from elftools.elf.sections import SymbolTableSection

TRIPLE = {
    "arm64-v8a": "aarch64-linux-android",
    "armeabi-v7a": "arm-linux-androideabi",
    "x86": "i686-linux-android",
    "x86_64": "x86_64-linux-android",
}
SIXTY_FOUR = {"arm64-v8a", "x86_64"}

# (glob on the path, must-have DT_NEEDED, must-not-have DT_NEEDED globs)
RULES = [
    ("usr/lib/python3.14/site-packages/_cffi_backend.*.so", ["libffi.so", "libpython3.14.so"], []),
    ("usr/lib/python3.14/site-packages/_brotli.*.so", ["libpython3.14.so"], ["libbrotli*"]),
    ("usr/lib/libbrotlidec.so", ["libbrotlicommon.so"], []),
    ("usr/lib/libbrotlienc.so", ["libbrotlicommon.so"], []),
    ("usr/lib/libbrotlicommon.so", [], ["libbrotli*"]),
    ("usr/lib/python3.14/site-packages/curl_cffi/_wrapper.abi3.so", ["libpython3.14.so"], ["libssl*", "libcrypto*"]),
]
TLS_EXPORT = re.compile(r"^(SSL_|SSL3_|TLS_|DTLS_|EVP_|BIO_|X509|CRYPTO_|OPENSSL_|ERR_|RSA_|EC_|BN_|PEM_|d2i_|i2d_)")
TLS_EXPORT_ALLOWED = {"ERR_getErrorString"}


def elf_info(path):
    with open(path, "rb") as f:
        e = ELFFile(f)
        aligns = [s["p_align"] for s in e.iter_segments() if s["p_type"] == "PT_LOAD"]
        needed, soname, runpath = [], None, []
        for sec in e.iter_sections():
            if isinstance(sec, DynamicSection):
                for t in sec.iter_tags():
                    if t.entry.d_tag == "DT_NEEDED":
                        needed.append(t.needed)
                    elif t.entry.d_tag == "DT_SONAME":
                        soname = t.soname
                    elif t.entry.d_tag in ("DT_RUNPATH", "DT_RPATH"):
                        runpath += (t.runpath if t.entry.d_tag == "DT_RUNPATH" else t.rpath).split(":")
        undef, defined = set(), set()
        dynsym = e.get_section_by_name(".dynsym")
        if isinstance(dynsym, SymbolTableSection):
            for s in dynsym.iter_symbols():
                if not s.name:
                    continue
                bind = s["st_info"]["bind"]
                if s["st_shndx"] == "SHN_UNDEF":
                    if bind != "STB_WEAK":
                        undef.add(s.name)
                elif bind in ("STB_GLOBAL", "STB_WEAK", "STB_GNU_UNIQUE"):
                    defined.add(s.name)
        return {
            "class": e.elfclass,
            "min_align": min(aligns) if aligns else None,
            "needed": needed,
            "soname": soname,
            "runpath": runpath,
            "undef": undef,
            "defined": defined,
        }


class Resolver:
    def __init__(self, tree, sysroot_libdir):
        self.tree = tree
        self.sys = sysroot_libdir
        self.cache = {}

    def find(self, name, origin_dir, runpath):
        cands = []
        for rp in runpath:
            if rp.startswith("$ORIGIN"):
                cands.append(os.path.normpath(os.path.join(origin_dir, rp[len("$ORIGIN"):].lstrip("/"), name)))
        cands.append(os.path.join(self.tree, "usr/lib", name))
        for c in cands:
            if os.path.exists(c):
                return os.path.realpath(c)
        s = os.path.join(self.sys, name)
        if os.path.exists(s):
            return s
        return None

    def info(self, path):
        if path not in self.cache:
            self.cache[path] = elf_info(path)
        return self.cache[path]

    def closure(self, path):
        """Defined symbols of the transitive DT_NEEDED closure, and unresolved libs."""
        seen, missing, syms = set(), [], set()
        stack = [path]
        while stack:
            p = stack.pop()
            inf = self.info(p)
            for n in inf["needed"]:
                q = self.find(n, os.path.dirname(p), inf["runpath"])
                if q is None:
                    missing.append(f"{os.path.basename(p)} -> {n}")
                    continue
                if q in seen:
                    continue
                seen.add(q)
                syms |= self.info(q)["defined"]
                stack.append(q)
        return syms, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--upstream-tree")
    ap.add_argument("--abi", required=True, choices=sorted(TRIPLE))
    ap.add_argument("--ndk-sysroot", required=True)
    ap.add_argument("--api", type=int, default=24)
    ap.add_argument("--json")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    libdir = os.path.join(a.ndk_sysroot, "usr/lib", TRIPLE[a.abi], str(a.api))
    if not os.path.isdir(libdir):
        sys.exit(f"NDK stub dir not found: {libdir}")
    res = Resolver(a.tree, libdir)
    failures, report = [], []
    for rel in a.files:
        path = os.path.join(a.tree, rel)
        inf = res.info(os.path.realpath(path))
        row = {"path": rel, "min_align": inf["min_align"], "soname": inf["soname"], "needed": inf["needed"]}
        fail = []
        # 16 KB
        if a.abi in SIXTY_FOUR:
            if inf["min_align"] is None or inf["min_align"] < 16384:
                fail.append(f"PT_LOAD align {inf['min_align']} < 16384")
        elif a.upstream_tree:
            up = os.path.join(a.upstream_tree, rel)
            if os.path.exists(up):
                ua = res.info(os.path.realpath(up))["min_align"]
                row["upstream_align"] = ua
                if inf["min_align"] < ua:
                    fail.append(f"PT_LOAD align {inf['min_align']} lower than upstream {ua}")
        # SONAME
        if a.upstream_tree:
            up = os.path.join(a.upstream_tree, rel)
            if os.path.exists(up):
                us = res.info(os.path.realpath(up))["soname"]
                row["upstream_soname"] = us
                if us != inf["soname"]:
                    fail.append(f"DT_SONAME {inf['soname']!r} != upstream {us!r}")
        # rules
        for pat, must, mustnot in RULES:
            if fnmatch.fnmatch(rel, pat):
                for m in must:
                    if m not in inf["needed"]:
                        fail.append(f"DT_NEEDED missing {m}")
                for g in mustnot:
                    for n in inf["needed"]:
                        if fnmatch.fnmatch(n, g):
                            fail.append(f"DT_NEEDED must not include {n}")
        # symbols
        syms, missing = res.closure(os.path.realpath(path))
        for m in missing:
            fail.append(f"unresolved DT_NEEDED {m}")
        unresolved = sorted(s for s in inf["undef"] - syms - inf["defined"])
        row["undefined"] = len(inf["undef"])
        if unresolved:
            fail.append(f"{len(unresolved)} unresolved symbols: {', '.join(unresolved[:20])}")
        if rel.endswith("curl_cffi/_wrapper.abi3.so"):
            tls = sorted(s for s in inf["defined"] if TLS_EXPORT.match(s) and s not in TLS_EXPORT_ALLOWED)
            row["tls_exports"] = tls
            if tls:
                fail.append(f"exports TLS symbols: {', '.join(tls[:10])}")
        row["ok"] = not fail
        row["failures"] = fail
        report.append(row)
        status = "ok  " if not fail else "FAIL"
        print(f"{status} [{a.abi}] {rel}  align={inf['min_align']} soname={inf['soname']} needed={','.join(inf['needed'])}")
        for f_ in fail:
            print(f"       - {f_}")
        failures += fail
    if a.json:
        with open(a.json, "w") as f:
            json.dump(report, f, indent=1, sort_keys=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

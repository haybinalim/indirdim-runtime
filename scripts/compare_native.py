#!/usr/bin/env python3
"""Compare two independent native builds (plan §9.3). Never fails the build:
Termux builds are not guaranteed bit-for-bit reproducible; the result is recorded.
Usage: compare_native.py DIR_B1 DIR_B2 OUT_JSON   (each DIR holds <abi>/native-manifest.json)
"""
import json
import os
import sys

b1, b2, out = sys.argv[1:4]
result = {}
for abi in sorted(os.listdir(b1)):
    m1 = json.load(open(os.path.join(b1, abi, "native-manifest.json")))["files"]
    p2 = os.path.join(b2, abi, "native-manifest.json")
    if not os.path.exists(p2):
        result[abi] = {"error": "second build missing"}
        continue
    m2 = json.load(open(p2))["files"]
    same = sorted(k for k in m1 if k in m2 and m1[k]["sha256"] == m2[k]["sha256"])
    diff = sorted(k for k in set(m1) | set(m2) if k not in same)
    result[abi] = {"identical": len(same), "different": diff,
                   "different_sha256": {k: [m1.get(k, {}).get("sha256"), m2.get(k, {}).get("sha256")] for k in diff}}
    print(f"{abi}: {len(same)} identical, {len(diff)} different" + (": " + ", ".join(diff) if diff else ""))
json.dump(result, open(out, "w"), indent=1, sort_keys=True)

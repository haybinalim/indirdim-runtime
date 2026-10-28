#!/usr/bin/env python3
"""Fail if any `uses:` in the given workflow directory is not pinned to a full commit SHA."""
import os
import re
import sys

bad = []
for d in sys.argv[1:]:
    for name in sorted(os.listdir(d)):
        if not name.endswith((".yml", ".yaml")):
            continue
        for n, line in enumerate(open(os.path.join(d, name)), 1):
            m = re.search(r"uses:\s*([^\s#]+)", line)
            if not m or m.group(1).startswith("./"):
                continue
            if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1)):
                bad.append(f"{name}:{n}: {m.group(1)}")
if bad:
    print("Unpinned actions:\n" + "\n".join(bad))
    sys.exit(1)
print("all actions pinned")

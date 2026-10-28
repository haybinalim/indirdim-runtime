#!/usr/bin/env python3
"""Extract a runtime zip (libpython.zip.so) to a directory, keeping symlinks and modes.

Usage: ziptree.py extract ZIP DIR
       ziptree.py extract-aar AAR ABI DIR    (extracts jni/<ABI>/libpython.zip.so from an AAR)
"""
import io
import os
import stat
import sys
import zipfile


def extract(zf, dest):
    dest = os.path.realpath(dest)
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or ".." in name.split("/"):
            raise SystemExit(f"unsafe path in zip: {name}")
        target = os.path.join(dest, name)
        mode = info.external_attr >> 16
        if name.endswith("/") or stat.S_ISDIR(mode):
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = zf.read(info)
        if stat.S_ISLNK(mode):
            link = data.decode()
            if os.path.isabs(link):
                raise SystemExit(f"absolute symlink in zip: {name} -> {link}")
            if os.path.lexists(target):
                os.remove(target)
            os.symlink(link, target)
            continue
        with open(target, "wb") as f:
            f.write(data)
        os.chmod(target, (mode & 0o777) | 0o600 if mode else 0o644)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "extract":
        with zipfile.ZipFile(sys.argv[2]) as z:
            extract(z, sys.argv[3])
    elif len(sys.argv) == 5 and sys.argv[1] == "extract-aar":
        with zipfile.ZipFile(sys.argv[2]) as aar:
            inner = aar.read(f"jni/{sys.argv[3]}/libpython.zip.so")
        with zipfile.ZipFile(io.BytesIO(inner)) as z:
            extract(z, sys.argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

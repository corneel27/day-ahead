"""Remove dead weight from the add-on venv before it is copied into the image.

Runs in the builder stage only. Two things in the cbcbox wheel are never used:

* the debug build of CBC (cbc_dist_debug / cbc_dist_debug_avx2, ~335 MB),
  only selected when CBCBOX_BUILD=debug is set;
* the duplicate copies of every shared library: wheels cannot hold
  symlinks, so libX.so, libX.so.0 and libX.so.0.0.0 are three full files.
  They are turned back into symlinks to the longest-named copy (~130 MB).
"""

import glob
import hashlib
import os
import shutil
import sys

site = sys.argv[1]
saved = 0

for debug_dir in glob.glob(os.path.join(site, "cbcbox", "cbc_dist_debug*")):
    for root, _, files in os.walk(debug_dir):
        saved += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    shutil.rmtree(debug_dir)

for libdir in glob.glob(os.path.join(site, "cbcbox", "cbc_dist*", "lib")):
    groups = {}
    for name in os.listdir(libdir):
        path = os.path.join(libdir, name)
        if ".so" not in name or os.path.islink(path) or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            groups.setdefault(hashlib.sha256(f.read()).hexdigest(), []).append(name)
    for names in groups.values():
        keep = max(names, key=len)
        for name in names:
            if name != keep:
                path = os.path.join(libdir, name)
                saved += os.path.getsize(path)
                os.remove(path)
                os.symlink(keep, path)

print(f"slim_venv: removed {saved // 2**20} MB from {site}")

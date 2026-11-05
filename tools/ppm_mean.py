#!/usr/bin/env python3
"""Report mean channel values and non-black pixel count for PPM frames.

A fully black present is an incomplete/missing texture or a lost draw; this distinguishes that from
"the game is fine and only a crop looked empty".
"""
import glob
import os
import sys

paths = sys.argv[1:] or ["dumps/burst13/frame_*.ppm"]
files = []
for p in paths:
    files.extend(sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p])

if not files:
    print("no files matched")
    sys.exit(1)

for path in files[-8:]:
    data = open(path, "rb").read()
    vals = []
    i = 2
    while len(vals) < 3:
        while i < len(data) and data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while data[i:i + 1] not in (b"\n", b""):
                i += 1
            continue
        j = i
        while j < len(data) and not data[j:j + 1].isspace():
            j += 1
        vals.append(int(data[i:j]))
        i = j
    i += 1
    px = data[i:]
    n = len(px) // 3
    if n == 0:
        print("%s: no pixels" % path)
        continue
    tot = [0, 0, 0]
    nonzero = 0
    step = max(1, n // 200000)
    seen = 0
    for k in range(0, n, step):
        r, g, b = px[k * 3], px[k * 3 + 1], px[k * 3 + 2]
        tot[0] += r
        tot[1] += g
        tot[2] += b
        if r or g or b:
            nonzero += 1
        seen += 1
    print("%s: mean %.1f/%.1f/%.1f, non-black %.1f%%"
          % (os.path.basename(path), tot[0] / seen, tot[1] / seen, tot[2] / seen, 100.0 * nonzero / seen))

#!/usr/bin/env python3
"""Diff the two frames of each capture pair (rNNN_0 vs rNNN_1).

Window captures come as pairs a fraction of a second apart. Comparing *within* a pair isolates what
changes while the camera is not being moved, which is what flicker is; comparing across rounds mixes
in camera motion and buries it. Writes a crop of the worst pair's changed region.

usage: pair_diff.py <dir> [out.png]
"""
import glob
import os
import struct
import sys
import zlib

dumpdir = sys.argv[1] if len(sys.argv) > 1 else "dumps/live2"
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(dumpdir, "flicker_top.png")


def read_ppm(path):
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
    return vals[0], vals[1], data[i + 1:]


def write_png(path, w, h, rows, scale):
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    grown = []
    for r in rows:
        g = b"".join(r[x * 3:x * 3 + 3] * scale for x in range(len(r) // 3))
        grown.extend([g] * scale)
    raw = b"".join(b"\x00" + r for r in grown)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


pairs = []
for a in sorted(glob.glob(os.path.join(dumpdir, "r*_0.ppm"))):
    b = a[:-6] + "_1.ppm"
    if os.path.exists(b):
        pairs.append((a, b))

if not pairs:
    print("no capture pairs in", dumpdir)
    sys.exit(1)

results = []
for a, b in pairs:
    wa, ha, pa = read_ppm(a)
    wb, hb, pb = read_ppm(b)
    if (wa, ha) != (wb, hb) or len(pa) != len(pb):
        continue
    changed = 0
    total = 0
    x0 = y0 = 1 << 30
    x1 = y1 = -1
    big = 0
    for y in range(ha):
        row = y * wa * 3
        for x in range(wa):
            k = row + x * 3
            d = abs(pa[k] - pb[k]) + abs(pa[k + 1] - pb[k + 1]) + abs(pa[k + 2] - pb[k + 2])
            if d > 12:
                changed += 1
                total += d
                if d > 60:
                    big += 1
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    mean = (total / changed) if changed else 0.0
    results.append((changed, big, mean, (x0, y0, x1, y1), a, b, wa, ha, pa, pb))

results.sort(key=lambda r: (-r[1], -r[0]))
print("%d pairs compared (within-pair, camera static)" % len(results))
print(" changed  strong  meanDiff  bbox")
for changed, big, mean, bb, a, b, *_ in results[:10]:
    print("  %7d %7d  %8.1f  %s  %s" % (changed, big, mean, bb if changed else None, os.path.basename(a)))

top = results[0]
changed, big, mean, bb, a, b, w, h, pa, pb = top
if big > 0:
    pad = 8
    x0 = max(0, bb[0] - pad)
    y0 = max(0, bb[1] - pad)
    x1 = min(w, bb[2] + pad + 1)
    y1 = min(h, bb[3] + pad + 1)
    scale = max(1, min(4, 900 // max(1, x1 - x0)))
    rows = [pa[(y * w + x0) * 3:(y * w + x1) * 3] for y in range(y0, y1)]
    write_png(out, x1 - x0, y1 - y0, rows, scale)
    print("\nfirst frame of the worst pair, changed region -> %s" % out)
    rows_b = [pb[(y * w + x0) * 3:(y * w + x1) * 3] for y in range(y0, y1)]
    out2 = out.replace(".png", "_b.png")
    write_png(out2, x1 - x0, y1 - y0, rows_b, scale)
    print("second frame of the same pair          -> %s" % out2)
else:
    print("\nno strong differences within any pair: nothing flickered while capturing")

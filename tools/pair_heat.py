#!/usr/bin/env python3
"""Locate the pixels that differ between two captures and zoom in on the worst cluster.

The changed bbox from pair_diff spans most of the screen, which means several small patches differ
rather than one moving object. This scores 16x16 tiles so the patches can be ranked, then crops the
worst one from both frames at high zoom so the flickering surface can actually be looked at.

usage: pair_heat.py <a.ppm> <b.ppm> [outprefix] [threshold]
"""
import struct
import sys
import zlib

a_path, b_path = sys.argv[1], sys.argv[2]
prefix = sys.argv[3] if len(sys.argv) > 3 else "dumps/live2/patch"
thresh = int(sys.argv[4]) if len(sys.argv) > 4 else 12
TILE = 16


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


w, h, pa = read_ppm(a_path)
wb, hb, pb = read_ppm(b_path)
assert (w, h) == (wb, hb), "different sizes"

tiles = {}
total = 0
for y in range(h):
    for x in range(w):
        k = (y * w + x) * 3
        d = abs(pa[k] - pb[k]) + abs(pa[k + 1] - pb[k + 1]) + abs(pa[k + 2] - pb[k + 2])
        if d > thresh:
            total += 1
            key = (x // TILE, y // TILE)
            t = tiles.get(key)
            if t is None:
                tiles[key] = [1, d]
            else:
                t[0] += 1
                t[1] += d

print("%s vs %s: %d changed pixels (>%d)" % (a_path.split("/")[-1], b_path.split("/")[-1], total, thresh))
ranked = sorted(tiles.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
print("top tiles (tile x,y -> bbox, changed px, summed diff):")
for (tx, ty), (n, s) in ranked[:12]:
    print("  %2d,%2d -> %3d,%3d-%3d,%3d  %4d px  diff %d"
          % (tx, ty, tx * TILE, ty * TILE, tx * TILE + TILE - 1, ty * TILE + TILE - 1, n, s))

if not ranked:
    print("nothing changed; no crops written")
    sys.exit(0)

# the worst tile plus a generous margin, so the object around it is visible
tx, ty = ranked[0][0]
cx, cy = tx * TILE + TILE // 2, ty * TILE + TILE // 2
half = 48
x0, y0 = max(0, cx - half), max(0, cy - half)
x1, y1 = min(w, cx + half), min(h, cy + half)
scale = max(1, min(8, 800 // max(1, x1 - x0)))
for src, tag in ((pa, "a"), (pb, "b")):
    rows = [src[(y * w + x0) * 3:(y * w + x1) * 3] for y in range(y0, y1)]
    out = "%s_%s.png" % (prefix, tag)
    write_png(out, x1 - x0, y1 - y0, rows, scale)
    print("wrote %s (%d,%d-%d,%d x%d)" % (out, x0, y0, x1, y1, scale))

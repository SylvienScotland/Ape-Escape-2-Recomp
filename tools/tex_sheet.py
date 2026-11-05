#!/usr/bin/env python3
"""Contact sheet of dumped textures, so a corrupt decode is visible at a glance.

usage: tex_sheet.py <dumpdir> <out.png> [cellpix] [cols]
Looks for tex_*.ppm in the dump directory; each is scaled to fit one cell, nearest neighbour.
"""
import glob
import os
import struct
import sys
import zlib

dumpdir, out = sys.argv[1], sys.argv[2]
cell = int(sys.argv[3]) if len(sys.argv) > 3 else 96
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 8


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
    i += 1
    return vals[0], vals[1], data[i:]


files = sorted(glob.glob(os.path.join(dumpdir, "tex_*.ppm")))
if not files:
    print("no tex_*.ppm in", dumpdir)
    sys.exit(1)

rows = (len(files) + cols - 1) // cols
W, H = cols * cell, rows * cell
canvas = bytearray(b"\x20" * (W * H * 3))

for idx, path in enumerate(files):
    w, h, px = read_ppm(path)
    if w <= 0 or h <= 0:
        continue
    s = min(cell / w, cell / h)
    dw, dh = max(1, int(w * s)), max(1, int(h * s))
    ox = (idx % cols) * cell + (cell - dw) // 2
    oy = (idx // cols) * cell + (cell - dh) // 2
    for y in range(dh):
        sy = min(h - 1, int(y / s))
        for x in range(dw):
            sx = min(w - 1, int(x / s))
            k = (sy * w + sx) * 3
            if k + 2 >= len(px):
                continue
            d = ((oy + y) * W + ox + x) * 3
            canvas[d:d + 3] = px[k:k + 3]


def chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


raw = b"".join(b"\x00" + bytes(canvas[y * W * 3:(y + 1) * W * 3]) for y in range(H))
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 6))
       + chunk(b"IEND", b""))
open(out, "wb").write(png)
print("%d textures -> %s (%dx%d, %d cols)" % (len(files), out, W, H, cols))
for i, f in enumerate(files):
    print("  cell %d,%d  %s" % (i % cols, i // cols, os.path.basename(f)))

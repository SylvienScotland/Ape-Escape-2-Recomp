#!/usr/bin/env python3
"""Crop a bbox out of a PPM and write a real PNG, upscaled with nearest-neighbour.

usage: ppm2png.py <in.ppm> <x0> <y0> <x1> <y1> <out.png> [scale]
       ppm2png.py <in.ppm> - - - - <out.png> [scale]     (whole frame)
"""
import struct
import sys
import zlib

src = sys.argv[1]
x0s, y0s, x1s, y1s = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
out = sys.argv[6]
scale = int(sys.argv[7]) if len(sys.argv) > 7 else 3

data = open(src, "rb").read()
assert data[:2] == b"P6", "expected binary PPM"
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
w, h, _ = vals
px = data[i:]

x0 = 0 if x0s == "-" else max(0, int(x0s))
y0 = 0 if y0s == "-" else max(0, int(y0s))
x1 = w if x1s == "-" else min(w, int(x1s))
y1 = h if y1s == "-" else min(h, int(y1s))
cw, ch = x1 - x0, y1 - y0

rows = []
for y in range(y0, y1):
    row = px[(y * w + x0) * 3:(y * w + x1) * 3]
    grown = b"".join(row[x * 3:x * 3 + 3] * scale for x in range(cw))
    rows.extend([grown] * scale)


def chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


raw = b"".join(b"\x00" + r for r in rows)
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", cw * scale, ch * scale, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 6))
       + chunk(b"IEND", b""))
open(out, "wb").write(png)
print("%s: %dx%d, crop %dx%d at %d,%d -> %s (%dx%d)"
      % (src, w, h, cw, ch, x0, y0, out, cw * scale, ch * scale))

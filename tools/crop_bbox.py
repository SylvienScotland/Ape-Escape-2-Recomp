#!/usr/bin/env python3
"""Crop a screen bbox out of a PPM and upscale it, so a specific primitive can be looked at."""
import sys

src, x0, y0, x1, y1, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
scale = int(sys.argv[7]) if len(sys.argv) > 7 else 3

data = open(src, "rb").read()
# P6 header: magic, width, height, maxval - possibly with comments
parts = []
i = 2
while len(parts) < 3:
    while i < len(data) and data[i:i + 1].isspace():
        i += 1
    if data[i:i + 1] == b"#":
        while data[i:i + 1] not in (b"\n", b""):
            i += 1
        continue
    j = i
    while j < len(data) and not data[j:j + 1].isspace():
        j += 1
    parts.append(int(data[i:j]))
    i = j
i += 1
w, h, _ = parts
px = data[i:]

x0 = max(0, x0)
y0 = max(0, y0)
x1 = min(w, x1)
y1 = min(h, y1)
cw, ch = x1 - x0, y1 - y0
print(f"{src}: {w}x{h}, crop {cw}x{ch} at {x0},{y0} -> {out} (x{scale})")

rows = []
for y in range(y0, y1):
    row = px[(y * w + x0) * 3:(y * w + x1) * 3]
    grown = b"".join(row[x * 3:x * 3 + 3] * scale for x in range(cw))
    rows.extend([grown] * scale)

hdr = f"P6\n{cw * scale} {ch * scale}\n255\n".encode()
open(out, "wb").write(hdr + b"".join(rows))
print("wrote", out)

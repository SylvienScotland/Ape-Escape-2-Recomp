#!/usr/bin/env python3
"""Find the flickering region in a burst of consecutive frames, and cut both appearances out.

If the keyboard artifact really alternates frame to frame, two consecutive dumps of a still
camera differ only inside that region. This ranks consecutive pairs by how localised the change
is (small changed-pixel count but a real diff), then writes side-by-side crops as PNG so the two
appearances can be compared instead of guessed about.

usage: frame_flicker.py <dir> [min_bbox_area]
"""
import glob
import os
import struct
import sys
import zlib

try:
    import numpy as np
except ImportError:
    print("numpy is required")
    raise SystemExit(1)


def read_ppm(path):
    data = open(path, "rb").read()
    if not data.startswith(b"P6"):
        raise ValueError("not a P6 ppm: " + path)
    idx, parts = 2, []
    while len(parts) < 3:
        while data[idx:idx + 1].isspace():
            idx += 1
        st = idx
        while not data[idx:idx + 1].isspace():
            idx += 1
        parts.append(int(data[st:idx]))
    w, h, _ = parts
    idx += 1
    return np.frombuffer(data[idx:idx + w * h * 3], dtype=np.uint8).reshape(h, w, 3), w, h


def write_png(path, img):
    h, w, _ = img.shape
    px = img.reshape(h, w * 3)
    raw = b"".join(b"\x00" + px[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


directory = sys.argv[1]
pattern = sys.argv[2] if len(sys.argv) > 2 else "frame_*.ppm"
frames = sorted(glob.glob(os.path.join(directory, pattern)))
print(f"{len(frames)} frames in {directory}")
if len(frames) < 3:
    raise SystemExit("need at least 3 frames")

prev, w, h = read_ppm(frames[0])
ranked = []
for i in range(1, len(frames)):
    cur, _, _ = read_ppm(frames[i])
    d = np.abs(cur.astype(np.int16) - prev.astype(np.int16)).sum(axis=2)
    mask = d > 24
    n = int(mask.sum())
    if n == 0:
        ranked.append((0, i, None, 0))
        prev = cur
        continue
    ys, xs = np.nonzero(mask)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    area = (bbox[2] - bbox[0] + 1) * (bbox[3] - bbox[1] + 1)
    # localised change: few changed pixels inside a small box, and the box is not the whole screen
    score = n / max(1, area) * 100.0 if area < w * h * 0.25 else 0.0
    ranked.append((score, i, bbox, n))
    prev = cur

ranked.sort(reverse=True)
print("\ntop consecutive pairs by localised change (score, frame, bbox, changed px):")
for score, i, bbox, n in ranked[:8]:
    print(f"  {score:6.1f}  frame {i:4d}  bbox {bbox}  changed {n}")

written = 0
for score, i, bbox, n in ranked:
    if score <= 0 or bbox is None:
        continue
    a, _, _ = read_ppm(frames[i - 1])
    b, _, _ = read_ppm(frames[i])
    x0, y0, x1, y1 = bbox
    pad = 6
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w - 1, x1 + pad), min(h - 1, y1 + pad)
    ca, cb = a[y0:y1 + 1, x0:x1 + 1], b[y0:y1 + 1, x0:x1 + 1]
    # scale x4 for visibility, side by side with a 2px white gap
    def up(img):
        return np.repeat(np.repeat(img, 4, axis=0), 4, axis=1)
    ua, ub = up(ca), up(cb)
    gap = np.full((ua.shape[0], 2, 3), 255, dtype=np.uint8)
    combo = np.concatenate([ua, gap, ub], axis=1)
    out = os.path.join(directory, f"flick_{written}_f{i-1}_vs_f{i}.png")
    write_png(out, combo)
    print(f"  wrote {out}  bbox {bbox}  (left = frame {i-1}, right = frame {i})")
    written += 1
    if written >= 4:
        break

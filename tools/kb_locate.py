#!/usr/bin/env python3
"""Find where a given texture actually lands on screen, then crop it out of the dumped frames.

Every keyboard draw is logged with its atlas address, texture hash and screen bbox, so the keyboard
does not have to be guessed from a crop: its own record says where it is. Frame epochs are numbered
in log order, which matches the burst's frame_NNNN sequence.

usage: kb_locate.py <log> <dumpdir> <frames 0,10,20> [texhash | top]
"""
import glob
import os
import re
import sys
from collections import Counter, OrderedDict

log, dumpdir, frame_list = sys.argv[1], sys.argv[2], sys.argv[3]
want = sys.argv[4] if len(sys.argv) > 4 else "top"

kb_re = re.compile(
    r"\[gpu:kb\] press \d+ burst \d+ bbox (\d+),(\d+)-(\d+),(\d+) tbp0=0x([0-9a-f]+)"
    r".*?psm=0x([0-9a-f]+) (\d+)x(\d+).*?texhash=([0-9a-f]+).*?fepoch=(\d+)")

hashes = Counter()
per_epoch = OrderedDict()
with open(log, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if not line.startswith("[gpu:kb] press"):
            continue
        m = kb_re.match(line)
        if not m:
            continue
        bbox = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        th = m.group(9)
        fe = int(m.group(10))
        hashes[th] += 1
        per_epoch.setdefault(fe, []).append((bbox, th, int(m.group(5), 16), m.group(6), m.group(7), m.group(8)))

print("distinct texture hashes:", len(hashes))
for th, n in hashes.most_common(8):
    print("  %s  %d draws" % (th, n))

if want == "top":
    want = hashes.most_common(1)[0][0]
print("\nusing texhash", want)

epochs = list(per_epoch.keys())
print("frame epochs in log order:", len(epochs), "-> burst frame index 0..%d" % (len(epochs) - 1))

frames = [int(x) for x in frame_list.split(",") if x.strip()]
for k in frames:
    if k >= len(epochs):
        print("frame %d beyond the log's epochs" % k)
        continue
    fe = epochs[k]
    draws = [d for d in per_epoch[fe] if d[1] == want]
    src = os.path.join(dumpdir, "burst_%04d.ppm" % k)
    if not os.path.exists(src):
        cands = sorted(glob.glob(os.path.join(dumpdir, "burst_*.ppm")))
        if not cands or k >= len(cands):
            print("no dump for frame %d" % k)
            continue
        src = cands[k]
    print("\nfepoch %d (burst frame %d): %d draws of %s" % (fe, k, len(draws), want))
    for (bbox, th, tbp0, psm, tw, thh) in draws[:6]:
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print("   bbox %d,%d-%d,%d (%dx%d) tbp0=0x%04x psm=0x%s %sx%s"
              % (bbox[0], bbox[1], bbox[2], bbox[3], w, h, tbp0, psm, tw, thh))
    if draws:
        bbox = max(draws, key=lambda d: (d[0][2] - d[0][0]) * (d[0][3] - d[0][1]))[0]
        pad = 6
        out = os.path.join(dumpdir, "kbcrop_%04d.png" % k)
        scale = max(1, min(6, 900 // max(1, bbox[2] - bbox[0])))
        os.system('python tools/ppm2png.py "%s" %d %d %d %d "%s" %d'
                  % (src, bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad, out, scale))

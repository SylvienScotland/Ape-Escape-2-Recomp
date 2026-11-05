#!/usr/bin/env python3
"""How many of a frame's textured draws are the *same* quad drawn over and over?

kb_locate showed one texture hash landing 3,028 times per frame inside a 6-pixel-wide strip. If
those are few distinct quads submitted repeatedly, it is a submission problem (double draw, retry,
or a tiled decal) rather than a texture problem - and repeated coplanar draws at one spot flicker.

usage: kb_repeat.py <log> [max_epochs]
"""
import re
import sys
from collections import Counter, OrderedDict

log = sys.argv[1]
max_epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 3

kb_re = re.compile(
    r"\[gpu:kb\] press \d+ burst \d+ bbox (\d+),(\d+)-(\d+),(\d+) tbp0=0x([0-9a-f]+)"
    r".*?psm=0x([0-9a-f]+) (\d+)x(\d+).*?texhash=([0-9a-f]+).*?epoch=(\d+) fepoch=(\d+)")

per_epoch = OrderedDict()
with open(log, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if not line.startswith("[gpu:kb] press"):
            continue
        m = kb_re.match(line)
        if not m:
            continue
        bbox = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        fe = int(m.group(11))
        per_epoch.setdefault(fe, []).append(
            (bbox, m.group(5), m.group(6), m.group(7), m.group(8), m.group(9), int(m.group(10))))

for fe in list(per_epoch.keys())[:max_epochs]:
    draws = per_epoch[fe]
    geo = Counter((d[0], d[1]) for d in draws)
    tex = Counter((d[0], d[1], d[5]) for d in draws)
    decode = Counter(d[6] for d in draws)
    print("fepoch %d: %d draws" % (fe, len(draws)))
    print("  distinct (bbox,tbp0): %d | distinct (bbox,tbp0,texhash): %d | distinct decode epochs: %d"
          % (len(geo), len(tex), len(decode)))
    print("  most repeated identical draw:")
    for (bb, tbp0), n in geo.most_common(4):
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        print("     %dx%d bbox %d,%d-%d,%d tbp0=0x%s  x%d" % (w, h, bb[0], bb[1], bb[2], bb[3], tbp0, n))
    sizes = sorted(((d[0][2] - d[0][0]) * (d[0][3] - d[0][1]), d) for d in draws)
    print("  smallest area: %d px, largest area: %d px" % (sizes[0][0], sizes[-1][0]))
    print("  draws under 4 px area: %d of %d" % (sum(1 for a, _ in sizes if a < 4), len(sizes)))
    print("")

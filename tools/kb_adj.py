#!/usr/bin/env python3
"""LOG 0055 follow-up: how far is the opaque twin from the blended copy, in submission order?

The APE2_KB_SUPPRESS probe only matches when the opaque twin is the IMMEDIATELY preceding
primitive. It never fired on a live run (0 kbsup lines), so this measures the real gap.

Caveat: the [gpu:kbz] stream is already filtered to keyboard-atlas draws, so a distance of 1
here is necessary but not sufficient for adjacency in the full primitive stream. Distances > 1
prove adjacency is impossible.
"""
import bisect
import re
import sys
from collections import Counter

RE = re.compile(
    r"\[gpu:kbz\] press (\d+) bbox (\d+),(\d+)-(\d+),(\d+) prim (\d+) test (\w+) alpha (\w+) "
    r"abe (\d) z (-?\d+) (-?\d+) (-?\d+)"
)

WINDOW = 64

abe = []
key = []
with open(sys.argv[1], "r", errors="replace") as fh:
    for line in fh:
        if "[gpu:kbz]" not in line:
            continue
        m = RE.search(line)
        if not m:
            continue
        g = m.groups()
        abe.append(int(g[8]))
        key.append((int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[9]), int(g[10]), int(g[11])))

n = len(abe)
print(f"records: {n:,}")
blended = [i for i in range(n) if abe[i] == 1]
print(f"blended records: {len(blended):,}")

opaque_idx = {}
for i in range(n):
    if abe[i] == 0:
        opaque_idx.setdefault(key[i], []).append(i)

dist = Counter()
miss = 0
for i in blended:
    lst = opaque_idx.get(key[i], ())
    pos = bisect.bisect_left(lst, i) - 1
    best = None
    while pos >= 0:
        d = i - lst[pos]
        if d > WINDOW:
            break
        best = d
        pos -= 1
    if best is None:
        miss += 1
    else:
        dist[best] += 1

print("gap (in kbz records) between blended copy and nearest earlier identical opaque twin:")
for d in sorted(dist):
    print(f"  d={d:<3} {dist[d]:>9,}  ({100.0 * dist[d] / len(blended):5.1f}% of blended)")
print(f"  none within {WINDOW}: {miss:,}  ({100.0 * miss / len(blended):5.1f}%)")

#!/usr/bin/env python3
"""Are keyboards drawn twice per frame at UNEQUAL z?

The v3 fix only denies the exact-equal-depth tie. If a second, blended copy of the same bbox is
drawn at a slightly different z, GL_LESS lets both through and the winner again depends on draw
order and depth quantisation - which reads as flicker that comes and goes, and which no exact-tie
rule can suppress. This checks that directly, per frame epoch.

kb and kbz are emitted once each at the same point, so they are zipped by index after verifying
the bbox still matches.
"""
import re
import sys
from collections import defaultdict

log = sys.argv[1] if len(sys.argv) > 1 else "run_tex12.log"

kb_re = re.compile(
    r"\[gpu:kb\] press \d+ burst \d+ bbox (\d+),(\d+)-(\d+),(\d+) tbp0=0x([0-9a-f]+)"
    r".*?texhash=([0-9a-f]+).*?epoch=(\d+) fepoch=(\d+)")
kz_re = re.compile(
    r"\[gpu:kbz\] press \d+ bbox (\d+),(\d+)-(\d+),(\d+) prim \d+ test (\d+) alpha (\d+)"
    r" abe (\d+) z (\d+) (\d+) (\d+)")

kb = []
kz = []
with open(log, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if not line.startswith("[gpu:kb"):
            continue
        m = kb_re.match(line)
        if m:
            b = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            kb.append((b, int(m.group(5), 16), m.group(6), int(m.group(7)), int(m.group(8))))
            continue
        m = kz_re.match(line)
        if m:
            b = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            z = (int(m.group(8)), int(m.group(9)), int(m.group(10)))
            kz.append((b, int(m.group(5)), int(m.group(6)), int(m.group(7)), z))

print("kb records %d, kbz records %d" % (len(kb), len(kz)))
n = min(len(kb), len(kz))
mismatch = sum(1 for i in range(n) if kb[i][0] != kz[i][0])
print("bbox mismatches between the two streams (index-wise): %d" % mismatch)
if n == 0 or mismatch:
    print("-> streams are not index-aligned; aborting")
    sys.exit(1)

frames = defaultdict(lambda: defaultdict(list))
for i in range(n):
    b, tbp0, th, de, fe = kb[i]
    _, test, alpha, abe, z = kz[i]
    frames[fe][b].append(dict(tbp0=tbp0, texhash=th, de=de, test=test, alpha=alpha, abe=abe, z=z))

tot_draws = tot_frames = multi = 0
equal = diff = 0
diff_examples = []
for fe, bxs in frames.items():
    tot_frames += 1
    for b, draws in bxs.items():
        tot_draws += len(draws)
        if len(draws) < 2:
            continue
        multi += 1
        zs = set()
        for d in draws:
            zs.update(d["z"])
        if len(zs) == 1:
            equal += 1
        else:
            diff += 1
            if len(diff_examples) < 20:
                diff_examples.append((fe, b, draws))

print("frames %d, keyboard draws %d, bboxes drawn >1x in a frame %d" % (tot_frames, tot_draws, multi))
print("  identical z on every draw (exact tie, v3 handles these): %d" % equal)
print("  DIFFERENT z between draws (needs a tolerance rule): %d" % diff)

for fe, b, draws in diff_examples:
    print("")
    print("fepoch %d bbox %d,%d-%d,%d  %d draws" % (fe, b[0], b[1], b[2], b[3], len(draws)))
    for d in draws:
        print("   tbp0=0x%04x tex=%s test=%d alpha=%d abe=%d z=%s"
              % (d["tbp0"], d["texhash"], d["test"], d["alpha"], d["abe"], d["z"]))

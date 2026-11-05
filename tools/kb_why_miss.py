#!/usr/bin/env python3
"""Why does the coplanar-twin matcher never match a keyboard quad?

The [gpu:kbz] stream logs every keyboard-atlas draw's bbox, blend state and z triple, so the pair
can be examined directly instead of inferred. Three questions, in order of cheapness:

1. For keyboard bboxes, does an opaque draw and a blended draw ever share the exact bbox AND the
   exact z multiset? (What the matcher keys on.)
2. If not, do they share the z multiset but differ in bbox by a pixel or two? (Rasterisation
   rounding between the two passes - would break an exact bbox match.)
3. If not, do the z values differ outright? (Then they are not coplanar and the whole premise
   of an "exact duplicate" is wrong.)

usage: kb_why_miss.py <log> [atlas_hex]
"""
import re
import sys

KB = re.compile(r"tbp0=0x(\w+)")
KBZ = re.compile(
    r"\[gpu:kbz\] press (\d+) bbox (\d+),(\d+)-(\d+),(\d+) prim (\d+) test (\w+) alpha (\w+) "
    r"abe (\d) z (-?\d+) (-?\d+) (-?\d+)"
)
KB_FULL = re.compile(r"\[gpu:kb\] press (\d+) burst (\d+) bbox (\d+),(\d+)-(\d+),(\d+) tbp0=0x(\w+) tbw=")

log = sys.argv[1]
atlas = sys.argv[2].lower() if len(sys.argv) > 2 else "2bc0"

# pass 1: which bboxes are drawn from the keyboard atlas?
kb_bboxes = {}
for line in open(log, errors="replace"):
    if "tbp0=0x" not in line:
        continue
    m = KB_FULL.search(line)
    if not m:
        continue
    if m.group(7).lower() != atlas:
        continue
    bb = (int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6)))
    kb_bboxes[bb] = kb_bboxes.get(bb, 0) + 1
print(f"keyboard-atlas bboxes: {len(kb_bboxes)}  (draws {sum(kb_bboxes.values()):,})")
if not kb_bboxes:
    raise SystemExit("no draws from that atlas in this log")
for bb, n in sorted(kb_bboxes.items(), key=lambda kv: -kv[1])[:8]:
    print(f"  bbox {bb[0]},{bb[1]}-{bb[2]},{bb[3]}  {n} draws")

# pass 2: match keyboard bboxes against the kbz records
full_key = {}
z_only = {}
kb_recs = {}
n_rec = 0
for line in open(log, errors="replace"):
    if "[gpu:kbz]" not in line:
        continue
    m = KBZ.search(line)
    if not m:
        continue
    g = m.groups()
    n_rec += 1
    bb = (int(g[1]), int(g[2]), int(g[3]), int(g[4]))
    abe = int(g[8])
    zs = tuple(sorted((int(g[9]), int(g[10]), int(g[11]))))
    full_key.setdefault((bb, zs), set()).add(abe)
    if bb in kb_bboxes:
        z_only.setdefault(zs, set()).add(abe)
        kb_recs.setdefault(bb, []).append((abe, zs, int(g[5]), g[6], g[7]))

print(f"\nkbz records: {n_rec:,}")

exact = [k for k, v in full_key.items() if len(v) == 2]
kb_exact = [k for k in exact if k[0] in kb_bboxes]
print(f"1. bbox+z-multiset shared by opaque and blended: {len(exact):,} keys, "
      f"of which keyboard bbox: {len(kb_exact):,}")

kb_z_both = [z for z, v in z_only.items() if len(v) == 2]
print(f"2. keyboard draws whose z multiset has both blend states (bbox ignored): {len(kb_z_both):,}"
      f" of {len(z_only):,}")

# 3. look at the biggest keyboard bbox in detail
big = max(kb_bboxes.items(), key=lambda kv: (kv[0][2] - kv[0][0]) * (kv[0][3] - kv[0][1]))[0]
recs = kb_recs.get(big, [])
print(f"\n3. biggest keyboard bbox {big[0]},{big[1]}-{big[2]},{big[3]}: {len(recs)} kbz draws")
by_state = {}
for abe, zs, prim, test, alpha in recs:
    by_state.setdefault((abe, zs), 0)
    by_state[(abe, zs)] += 1
for (abe, zs), n in sorted(by_state.items(), key=lambda kv: -kv[1])[:6]:
    print(f"   abe={abe} z={zs[0]},{zs[1]},{zs[2]}  x{n}")
zsets = {zs for abe, zs, *_ in recs}
print(f"   distinct z multisets across both states: {len(zsets)}"
      f"  -> {'COPLANAR' if len(zsets) == 1 else 'NOT coplanar'}")

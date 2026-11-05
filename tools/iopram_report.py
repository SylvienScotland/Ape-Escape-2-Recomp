#!/usr/bin/env python3
"""Report where audio actually sits in IOP RAM after a tapped run (0074).

The ADMA tap says core1 streams from 0x4be40 but the payload is digital silence, while SIF DMAs deposit real
payloads into a ring around 0xc32c0. This measures amplitude by address across the whole 2 MB so the region
that really holds music can be identified instead of assumed.
"""
import glob
import os
import struct
import sys

DIR = sys.argv[1] if len(sys.argv) > 1 else "dumps/spu2c"

REGIONS = [
    ("sif ring   0xc32c0", 0xC32C0, 0xD0000),
    ("adma ring  0x4b000", 0x4B000, 0x52000),
    ("spu sfx    0x83280", 0x83280, 0xC0000),
    ("heap       0x70000", 0x70000, 0x80000),
    ("low        0x00000", 0x001000, 0x040000),
]


def peak16(buf, lo, hi):
    hi = min(hi, len(buf))
    if lo >= hi:
        return 0, 0
    data = buf[lo:hi - (hi - lo) % 2]
    if not data:
        return 0, 0
    s = struct.unpack("<%dh" % (len(data) // 2), data)
    return max(abs(x) for x in s), sum(1 for x in s if abs(x) > 64)


def loudest_windows(buf, size=4096, top=6):
    out = []
    for off in range(0, len(buf) - size, size):
        s = struct.unpack_from("<%dh" % (size // 2), buf, off)
        pk = max(abs(x) for x in s)
        if pk > 0:
            out.append((pk, off))
    out.sort(reverse=True)
    return out[:top]


files = sorted(glob.glob(os.path.join(DIR, "iopram_*.bin")))
if not files:
    print(f"no snapshots in {DIR}")
    sys.exit(1)

for path in files:
    buf = open(path, "rb").read()
    print(f"\n=== {os.path.basename(path)} ({len(buf)} bytes) ===")
    for name, lo, hi in REGIONS:
        pk, loud = peak16(buf, lo, hi)
        print(f"  {name:20s} window {hi - lo:6d}B  peak={pk:6d}  samples>64={loud}")
    print("  loudest 4KB windows anywhere:")
    for pk, off in loudest_windows(buf):
        print(f"    addr=0x{off:06x} peak={pk}")

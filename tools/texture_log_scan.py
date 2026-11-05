#!/usr/bin/env python3
"""Correlate textured draws with the upload stream in an APE2 frame-dump burst log.

Usage: python tools/texture_log_scan.py boot.log [--addr 0x3f00] [--top 8]

The burst probes (recomp patches 0051/0052) write, in order, one line per completed GS transfer and
one per textured primitive over the hub keyboard area:

  [gpu:updata] burst N dbp=0x3f00 128x64 datahash=<hash of the uploaded bytes>
  [gpu:kb] burst N bbox ... tbp0=0x3f00 tbw=4 psm=0x14 256x256 cbp=0x3f80 ... texhash=<hash of decoded texels>

For every draw the script finds the upload that most recently completed at the draw's texture
address, so a texture sampling VRAM nobody uploaded (or uploaded elsewhere) shows up instead of
being guessed at.

Draws are keyed by the whole TEX0, not just the address: the game streams textures through a ring of
addresses, and one address serves several formats/palettes over time. A single TEX0 over a single
upload content that decodes to two different texhashes means the decode is not a function of
(VRAM bytes, TEX0) and the fault is on our side.
"""

import argparse
import collections
import re

UP_RE = re.compile(r"\[gpu:updata\] burst \d+ dbp=0x([0-9a-f]+) (\d+)x(\d+) datahash=([0-9a-f]+)")
KB_RE = re.compile(
    r"\[gpu:kb\] burst \d+ bbox [\d,\-]+ tbp0=0x([0-9a-f]+) tbw=(\d+) psm=0x([0-9a-f]+) "
    r"(\d+)x(\d+) cbp=0x([0-9a-f]+).*?texhash=([0-9a-f]+)"
)


def hexopt(text):
    return text.lower().replace("0x", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--addr", action="append", default=[], help="texture base address to detail (hex, repeatable)")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    last = {}                                                                 # dbp -> hash of last upload
    per_tex = collections.defaultdict(lambda: collections.defaultdict(set))   # tex0 -> {upload: {texhash}}
    no_upload = collections.Counter()                                         # (psm, tbp0) -> draws
    draws = collections.Counter()                                             # (psm, tbp0) -> draws

    with open(args.log, "r", errors="replace") as f:
        for line in f:
            if not line.startswith("["):
                continue
            if "[gpu:updata]" in line:
                m = UP_RE.search(line)
                if m:
                    last[m.group(1)] = m.group(4)
                continue
            if "[gpu:kb] " not in line:
                continue
            m = KB_RE.search(line)
            if not m:
                continue
            tbp, tbw, psm, w, h, cbp, texhash = m.groups()
            draws[(psm, tbp)] += 1
            prev = last.get(tbp)
            if prev is None:
                no_upload[(psm, tbp)] += 1
            else:
                per_tex[(tbp, psm, tbw, w, h, cbp)][prev].add(texhash)

    if not draws:
        print("no [gpu:kb] draws in this log (no hub burst with APE2_FRAME_DUMP?)")
        return 1

    print(f"draws: {sum(draws.values())}  addressed texture slots: {len(draws)}")
    print(f"most drawn (psm, tbp0): {draws.most_common(args.top)}")
    missing = sum(no_upload.values())
    print(f"draws with no upload at their address: {missing}" + (f" {no_upload.most_common(5)}" if missing else ""))

    ambiguous = [(a, k) for a, d in per_tex.items() for k, v in d.items() if len(v) > 1]
    print(f"one TEX0 + one upload content decoding to more than one texhash: {len(ambiguous)}")
    for a, k in ambiguous[:args.top]:
        print(f"   tbp0=0x{a[0]} psm=0x{a[1]} tbw={a[2]} {a[3]}x{a[4]} cbp=0x{a[5]}: upload {k} -> {sorted(per_tex[a][k])}")

    for addr in [hexopt(x) for x in args.addr]:
        shown = 0
        for key, d in per_tex.items():
            if key[0] != addr:
                continue
            print(f"dbp=0x{addr} psm=0x{key[1]} tbw={key[2]} {key[3]}x{key[4]} cbp=0x{key[5]}: {len(d)} upload contents")
            for k, v in list(d.items())[:args.top]:
                print(f"   upload {k} -> texhash {sorted(v)}")
            shown += 1
        if not shown:
            print(f"dbp=0x{addr}: never drawn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

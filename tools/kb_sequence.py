#!/usr/bin/env python3
"""Print the per-frame texture record of the hub keyboard quads from a run log.

Usage: python tools/kb_sequence.py run_tex2.log [--bbox 174,122]

Reads the [gpu:kb] probe lines (emitted only during an F9 burst) and shows, for one
screen quad, the texture address and the three hashes: texhash (decoded RGBA),
raw (source VRAM pages) and clut (palette snapshot). If raw holds still while clut
moves, the palette is being overwritten; if raw moves, the draw points somewhere new.
"""
import re
import sys

LINE = re.compile(
    r"\[gpu:kb\] burst (\d+) bbox (\d+),(\d+)-(\d+),(\d+) tbp0=0x([0-9a-f]+)"
    r".*?texhash=([0-9a-f]+)(?: raw=([0-9a-f]+) clut=([0-9a-f]+))?"
)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    bbox = (174, 122)
    if "--bbox" in argv:
        x, y = argv[argv.index("--bbox") + 1].split(",")
        bbox = (int(x), int(y))

    rows = []
    for line in open(path, "r", errors="replace"):
        m = LINE.search(line)
        if not m:
            continue
        burst, x0, y0, x1, y1, tbp, th, raw, clut = m.groups()
        if (int(x0), int(y0)) != bbox:
            continue
        rows.append((int(burst), f"{x0},{y0}-{x1},{y1}", tbp, th, raw, clut))

    if not rows:
        print(f"no [gpu:kb] draws for bbox {bbox[0]},{bbox[1]} in {path}")
        return 1

    print(f"{len(rows)} draws for bbox {bbox[0]},{bbox[1]}")
    print(f"{'#':>4} {'burst':>5} {'bbox':>15} {'tbp0':>6} {'texhash':>9} {'raw':>9} {'clut':>9}  changed")
    prev = None
    seen = {"texhash": set(), "raw": set(), "clut": set()}
    for i, (burst, box, tbp, th, raw, clut) in enumerate(rows):
        seen["texhash"].add(th)
        seen["raw"].add(raw)
        seen["clut"].add(clut)
        marks = ""
        if prev is not None:
            for name, now, was in (("tbp0", tbp, prev[0]), ("texhash", th, prev[1]),
                                   ("raw", raw, prev[2]), ("clut", clut, prev[3])):
                if now != was and now is not None and was is not None:
                    marks += f" {name}"
        prev = (tbp, th, raw, clut)
        print(f"{i:>4} {burst:>5} {box:>15}  0x{tbp:>4} {th:>9} {raw or '-':>9} {clut or '-':>9} {marks}")

    print()
    print(f"distinct texhash {len(seen['texhash'])}  raw {len(seen['raw'])}  clut {len(seen['clut'])}")
    if len(seen["raw"]) == 1 and len(seen["clut"]) > 1:
        print("=> texels constant, palette moving: the CLUT is being overwritten after upload")
    elif len(seen["raw"]) > 1:
        print("=> source texels differ between frames: the draw reads a VRAM region holding other content")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

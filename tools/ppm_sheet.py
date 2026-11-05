#!/usr/bin/env python3
"""Tile frame-dump PPMs into contact-sheet PNGs so a long capture can be scanned in one look.

Usage: python tools/ppm_sheet.py <dir> [--cols 8] [--rows 8] [--scale 5] [--from 0] [--count 64]

Frames are taken in filename order and laid out left to right, top to bottom, so tile (row, col) is
frame index = from + row*cols + col. Nearest-neighbour downscale keeps it dependency-free; a broken
texture shows up as a wrong-coloured patch even at a fifth of the size.
"""

import argparse
import sys
from pathlib import Path

from ppm2png import read_p6, write_png


def downscale(width, height, rgb, scale):
    w = width // scale
    h = height // scale
    out = bytearray(w * h * 3)
    for y in range(h):
        src = (y * scale) * width * 3
        dst = y * w * 3
        for x in range(w):
            s = src + (x * scale) * 3
            out[dst + x * 3 : dst + x * 3 + 3] = rgb[s : s + 3]
    return w, h, bytes(out)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=8)
    ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--from", dest="start", type=int, default=0)
    ap.add_argument("--count", type=int, default=64)
    args = ap.parse_args(argv)

    paths = sorted(Path(args.dir).glob("*.ppm"))[args.start : args.start + args.cols * args.rows]
    if not paths:
        print(f"no .ppm frames in {args.dir}")
        return 1

    tiles = []
    tw = th = 0
    for path in paths:
        width, height, rgb = read_p6(path)
        tw, th, small = downscale(width, height, rgb, args.scale)
        tiles.append(small)

    sheet_w, sheet_h = tw * args.cols, th * args.rows
    sheet = bytearray(b"\x00\x00\x00" * (sheet_w * sheet_h))
    for i, tile in enumerate(tiles):
        row, col = divmod(i, args.cols)
        for y in range(th):
            dst = ((row * th + y) * sheet_w + col * tw) * 3
            src = y * tw * 3
            sheet[dst : dst + tw * 3] = tile[src : src + tw * 3]

    name = f"sheet_{args.start:04d}_{args.start + len(tiles) - 1:04d}.png"
    out = Path(args.dir) / name
    write_png(out, sheet_w, sheet_h, bytes(sheet))
    print(f"{out}  ({len(tiles)} frames of {tw}x{th}, {args.cols}x{args.rows})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

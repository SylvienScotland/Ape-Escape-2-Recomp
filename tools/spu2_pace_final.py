#!/usr/bin/env python3
"""0071d: settle ADMA pacing at 768 cycles/word.

Swept against [spu2:lap], which reports block refreshes per ring lap and must be 2.0 for a 2048-byte ring of two
1 KB blocks:
    384 -> 4.15  (writer laps the reader: overrun)
    768 -> 2.04  (one refresh per block per lap: correct)
    934 -> 1.68  (reader outruns the writer: stale replay)
768 is the hardware figure (36.864 MHz / 48 kHz per stereo frame, halved per 16-bit word) and needs no correction,
so the 934 guess is reverted and 768 becomes the default. The env override stays for future calibration.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

changed = 0

old_default = "                return 934ull;"
if text.count(old_default) == 1:
    text = text.replace(old_default, "                return 768ull;", 1)
    changed += 1

old_comment = """        // 0071: auto-DMA pacing, in IOP cycles per 16-bit word. Nominal hardware is 384 (512 words per 1 KB
        // block = 5.33 ms), but the wall-clock rate depends on how fast this emulator actually advances the IOP,
        // so it stays overridable until [spu2:lap] shows the ring refreshed exactly once per lap."""
if text.count(old_comment) == 1:
    text = text.replace(old_comment, """        // 0071: auto-DMA pacing, in IOP cycles per 16-bit word (768 per stereo frame = 36.864 MHz / 48 kHz).
        // Calibrated against [spu2:lap]: 768 gives 2.04 block refreshes per 2 KB ring lap, i.e. every block is
        // refreshed exactly once per lap. 384 overran (4.15) and 934 starved the reader (1.68). Kept overridable
        // through APE2_SPU2_ADMA_CYCLES in case IOP timing changes.""", 1)
    changed += 1

old_hook = """        // 0075: the auto-DMA source is the stream the SPU2 is expected to play. Record it as the playback head.
        // Re-arming with the same address is a re-read of a block already handed out, so only the address is
        // tracked here; pullSpu2Pcm walks forward from it at 48 kHz."""
if text.count(old_hook) == 1:
    text = text.replace(old_hook, """        // 0071: the auto-DMA source is the streamed music. Each arm marks a block the driver has (re)written, so
        // it is copied into the shadow ring there and played from by pullSpu2Pcm at 48 kHz.""", 1)
    changed += 1

if changed == 0:
    print("nothing to change")
    sys.exit(0)

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("pacing default 768, comments updated (%d edits)" % changed)

#!/usr/bin/env python3
"""0075: forward SPU2 PCM pulling through IopSubsystem.

The runtime owns an IopSubsystem, not the IopMemory inside it, so the pump needs these two accessors. The memory
member name is discovered from the existing writeMemory implementation instead of being assumed.
"""
import re
import sys

HDR = r"C:\dev\PS2Recomp\ps2xIOP\include\ps2x\iop\iop_subsystem.h"
SRC = r"C:\dev\PS2Recomp\ps2xIOP\src\iop_subsystem.cpp"


def load(p):
    return open(p, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def save(p, t):
    open(p, "w", encoding="utf-8", newline="\r\n").write(t)


hdr = load(HDR)
src = load(SRC)

if "pullSpu2Pcm" in hdr and "pullSpu2Pcm" in src:
    print("already patched")
    sys.exit(0)

# ---- discover how IopSubsystem reaches its IopMemory (e.g. m_impl->memory.writeMemory(...))
anchor_src = "bool IopSubsystem::writeMemory(uint32_t address, const void *source, size_t size)"
assert src.count(anchor_src) == 1, src.count(anchor_src)
body = src[src.index(anchor_src):src.index(anchor_src) + 400]
match = re.search(r"(\w+)\s*(?:\->|\.)\s*(\w+)\s*(?:\->|\.)\s*writeMemory", body)
if match:
    mem_expr = f"{match.group(1)}->{match.group(2)}"
else:
    match = re.search(r"(\w+)\s*(?:\->|\.)\s*writeMemory", body)
    if not match:
        raise SystemExit("could not discover the memory member")
    mem_expr = match.group(1)
print("memory expression:", mem_expr)

hdr_anchor = "        [[nodiscard]] DebugSnapshot debugSnapshot() const;"
assert hdr.count(hdr_anchor) == 1
hdr = hdr.replace(hdr_anchor, """        // 0075: SPU2 streamed audio. Frames are pulled from the buffer the sound driver armed onto core1
        // auto-DMA, at the hardware rate (one 4-byte stereo frame per 768 IOP cycles = 48 kHz).
        size_t pullSpu2Pcm(int16_t *destination, size_t frameCount);
        [[nodiscard]] bool spu2StreamArmed() const;

""" + hdr_anchor, 1)

src = src.replace(anchor_src, """size_t IopSubsystem::pullSpu2Pcm(int16_t *destination, size_t frameCount)
{
    return %s.pullSpu2Pcm(destination, frameCount);
}

bool IopSubsystem::spu2StreamArmed() const
{
    return %s.spu2StreamArmed();
}

""" % (mem_expr, mem_expr) + anchor_src, 1)

save(HDR, hdr)
save(SRC, src)
print("patched header and subsystem")

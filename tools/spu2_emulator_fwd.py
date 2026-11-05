#!/usr/bin/env python3
"""0075: IopEmulator -> IopMemory forwarding for the SPU2 playback cursor.

IopSubsystem reaches IOP RAM through IopEmulator, so the pull has to be exposed there as well.
"""
import re
import sys

HDR = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.h"
CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"


def load(p):
    return open(p, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def save(p, t):
    open(p, "w", encoding="utf-8", newline="\r\n").write(t)


hdr = load(HDR)
cpp = load(CPP)

if "pullSpu2Pcm" in hdr and "pullSpu2Pcm" in cpp:
    print("already patched")
    sys.exit(0)

hdr_anchor = "        [[nodiscard]] uint64_t cycles() const noexcept;"
assert hdr.count(hdr_anchor) == 1, hdr.count(hdr_anchor)
hdr = hdr.replace(hdr_anchor, """        // 0075: SPU2 streamed audio, forwarded to the IOP memory that holds the armed DMA buffer.
        size_t pullSpu2Pcm(int16_t *destination, size_t frameCount);
        [[nodiscard]] bool spu2StreamArmed() const;

""" + hdr_anchor, 1)

match = re.search(r"^(\s*)(?:\[\[nodiscard\]\]\s*)?uint64_t IopEmulator::cycles\(\)", cpp, re.M)
if match:
    indent = match.group(1)
    insert_at = match.start()
else:
    anchor = "bool IopEmulator::writeMemory("
    assert cpp.count(anchor) == 1
    indent = "    "
    insert_at = cpp.index(anchor)

forward = (f"{indent}size_t IopEmulator::pullSpu2Pcm(int16_t *destination, size_t frameCount)\n"
           f"{indent}{{\n"
           f"{indent}    return m_impl->memory.pullSpu2Pcm(destination, frameCount);\n"
           f"{indent}}}\n\n"
           f"{indent}bool IopEmulator::spu2StreamArmed() const\n"
           f"{indent}{{\n"
           f"{indent}    return m_impl->memory.spu2StreamArmed();\n"
           f"{indent}}}\n\n")

cpp = cpp[:insert_at] + forward + cpp[insert_at:]
save(HDR, hdr)
save(CPP, cpp)
print("patched IopEmulator forwarding")

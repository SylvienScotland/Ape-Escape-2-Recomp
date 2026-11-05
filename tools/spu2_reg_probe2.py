#!/usr/bin/env python3
"""0084b: the first probe only logged at exact multiples of 5,000 SPU2 writes, so a few hundred voice writes printed
nothing. Log the first writes individually (address + value) and then every 200, so both the presence and the kind of
register traffic can be read."""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

old = """            if ((keyon + keyoff + voice + other) % 5000u == 0u)
                std::fprintf(stderr, "[spu2:reg] keyon=%u keyoff=%u voiceRegs=%u other=%u\\n", keyon, keyoff, voice,
                             other);"""
new = """            const unsigned total = keyon + keyoff + voice + other;
            if (total <= 6u || total % 200u == 0u)
                std::fprintf(stderr,
                             "[spu2:reg] n=%u addr=0x%08x val=0x%08x keyon=%u keyoff=%u voiceRegs=%u other=%u\\n", total,
                             address, value, keyon, keyoff, voice, other);"""
if text.count(old) != 1:
    print(f"FAIL: anchor matched {text.count(old)} times")
    sys.exit(1)
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text.replace(old, new, 1))
print("register probe threshold fixed")

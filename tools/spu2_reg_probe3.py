#!/usr/bin/env python3
"""0088: widen the SPU2 register probe to the legacy PS1 window.

The previous probe only counted 0x1F900000-0x1FA00000 and saw 12 writes in 42 s with no KEYON, which cannot be right
for a game with music. On PS2, SPU2 core0 is also reachable through the PS1-compatible window at 0x1F801C00-0x1F801E00
(voice registers, KON/KOFF at 0x1F801D88/0x1F801D8C, transfer address at 0x1F801DA6). libsd programs core0 there.
This reports writes per window with the first few addresses/values so the real programming traffic can be seen.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

start_marker = "        // 0084: SPU2 register traffic."
end_marker = "\n        m_hardware[address] = value;\n        if ((address != kDmaSpu0Chcr"

start = text.find(start_marker)
if start < 0:
    print("FAIL: start marker missing")
    sys.exit(1)
end = text.find(end_marker, start)
if end < 0:
    print("FAIL: end marker missing")
    sys.exit(1)

new_block = """        // 0088: SPU2 register traffic, including the legacy PS1 window at 0x1F801C00 that libsd uses for
        // core0 voices. Counted per window with the first few addresses printed, so the real programming traffic
        // (KEYON, voice pitch/start/ADSR) can be identified instead of assumed.
        {
            const bool legacy = address >= 0x1F801C00u && address < 0x1F801E00u;
            const bool core0 = address >= Spu2Base && address < Spu2Base + 0x400u;
            const bool core1 = address >= Spu2Base + 0x400u && address < Spu2Base + 0x800u;
            const bool common = address >= Spu2Base + 0x800u && address < Spu2End;
            if (legacy || core0 || core1 || common)
            {
                static unsigned legacyCount = 0u;
                static unsigned core0Count = 0u;
                static unsigned core1Count = 0u;
                static unsigned commonCount = 0u;
                static unsigned keyonCount = 0u;
                unsigned &counter = legacy ? legacyCount : core0 ? core0Count : core1 ? core1Count : commonCount;
                ++counter;

                const uint32_t low = address & 0x3FFu;
                const bool isKeyon = (low == 0x1B8u) || (legacy && address == 0x1F801D88u);
                if (isKeyon)
                    ++keyonCount;

                const unsigned total = legacyCount + core0Count + core1Count + commonCount;
                if (total <= 8u || isKeyon || total % 5000u == 0u)
                    std::fprintf(stderr,
                                 "[spu2:reg] addr=0x%08x val=0x%08x legacy=%u core0=%u core1=%u common=%u keyon=%u\\n",
                                 address, value, legacyCount, core0Count, core1Count, commonCount, keyonCount);
            }
        }
"""

text = text[:start] + new_block + text[end:]
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("probe widened to legacy window")

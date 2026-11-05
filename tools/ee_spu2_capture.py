#!/usr/bin/env python3
"""0090: capture EE-side SPU2 register traffic.

The EE window at 0x1F900000 was not part of PS2_IO_BASE, so any sceSd* voice programming done from the EE was dropped
with no trace. This routes that window into the IO register file so writes are both retained (reads then see them) and
counted, with the first few printed. Voice registers are 28 bytes per voice starting at core0 + 0x000, so a run of
writes there is direct evidence that the EE is programming voices.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

edits = [
    (
        """    inline bool isIoRegister(uint32_t addr)
    {
        return Ps2AddressInRange(addr, PS2_IO_BASE, PS2_IO_SIZE);
    }
""",
        """    inline bool isIoRegister(uint32_t addr)
    {
        // 0090: the EE also reaches SPU2 registers at 0x1F900000-0x1F901000 (core0, core1, common). That window
        // is outside PS2_IO_BASE, so without this the EE-side sceSd voice programming was dropped silently.
        return Ps2AddressInRange(addr, PS2_IO_BASE, PS2_IO_SIZE) ||
               Ps2AddressInRange(addr, 0x1F900000u, 0x1000u);
    }
""",
    ),
    (
        """    if (isGsPrivReg(address))
    {
        // NB: unreachable from write8/16/32/64 today since those all funnel IO
""",
        """    if (Ps2AddressInRange(address, 0x1F900000u, 0x1000u))
    {
        // 0090: SPU2 register traffic from the EE. Counted per area with the first writes printed, so we can tell
        // whether sceSd is programming voices from the EE side.
        static unsigned voiceWrites = 0u;
        static unsigned otherWrites = 0u;
        const unsigned area = (address - 0x1F900000u) / 0x400u;
        if (area < 2u)
        {
            ++voiceWrites;
            if (voiceWrites <= 12u || voiceWrites % 2000u == 0u)
                std::fprintf(stderr, "[ee:spu2] addr=0x%08x val=0x%08x voiceWrites=%u other=%u\\n", address, value,
                             voiceWrites, otherWrites);
        }
        else
        {
            ++otherWrites;
            if (otherWrites <= 8u)
                std::fprintf(stderr, "[ee:spu2] addr=0x%08x val=0x%08x (common/other) voiceWrites=%u other=%u\\n",
                             address, value, voiceWrites, otherWrites);
        }
        m_ioRegisters[address] = value;
        return true;
    }

    if (isGsPrivReg(address))
    {
        // NB: unreachable from write8/16/32/64 today since those all funnel IO
""",
    ),
]

for anchor, insert in edits:
    if insert.strip() in text or anchor.strip() in text and insert.split("\n")[0].strip() in text:
        continue
    count = text.count(anchor)
    if count != 1:
        print(f"FAIL: anchor matched {count} times: {anchor.strip()[:60]}")
        sys.exit(1)
    text = text.replace(anchor, insert, 1)

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("EE SPU2 capture installed")

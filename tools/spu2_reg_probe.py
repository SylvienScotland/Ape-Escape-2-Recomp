#!/usr/bin/env python3
"""0084: is the game driving SPU2 voices?

PS2 audio is produced by the SPU2's voices: each voice reads Sony 4-bit ADPCM from SPU2 RAM, applies pitch, ADSR and
volume, and 48 of them mix to the 48 kHz output. If the game writes KEYON and per-voice registers, then the bytes we
have been playing as PCM are voice sample data and no amount of stream timing will make them sound like music.

This counts writes into the SPU2 register window by class and reports periodically.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "[spu2:reg]" in text:
    print("already instrumented")
    sys.exit(0)

anchor = """        m_hardware[address] = value;
        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)
"""
if text.count(anchor) != 1:
    raise SystemExit(f"ERROR: anchor matched {text.count(anchor)} times")

insert = """        // 0084: SPU2 register traffic. KEYON (0x1B8 per core) means the game starts voices, i.e. audio is
        // generated from ADPCM sample data by the voice engine rather than streamed as finished PCM.
        if (address >= Spu2Base && address < Spu2End)
        {
            static unsigned keyon = 0u;
            static unsigned keyoff = 0u;
            static unsigned voice = 0u;
            static unsigned other = 0u;
            const uint32_t low = address & 0x1FFu;
            if (low == 0x1B8u)
                ++keyon;
            else if (low == 0x1B4u)
                ++keyoff;
            else if (low < 0x180u)
                ++voice;
            else
                ++other;
            if ((keyon + keyoff + voice + other) % 5000u == 0u)
                std::fprintf(stderr, "[spu2:reg] keyon=%u keyoff=%u voiceRegs=%u other=%u\\n", keyon, keyoff, voice,
                             other);
        }

""" + anchor

text = text.replace(anchor, insert, 1)
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("register probe added")

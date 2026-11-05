#!/usr/bin/env python3
"""Tap SPU2 AutoDMA blocks into a file (APE2_SPU2_DUMP=<dir>).

Why: the runtime has no SPU2 at all. `IopMemory::writeHardware32` handles a SPU2 DMA start by scheduling the
completion interrupt after the right number of cycles and then discarding the block, so both the sound-bank
uploads (core 0) and the 48 kHz music stream (core 1) are thrown away, and nothing can ever produce sound.
The block is still in IOP RAM at MADR when the DMA is armed, so it can be captured there.

This is the measurement step: what the stream actually contains (interleaved 16-bit PCM vs VAG ADPCM vs
something else) decides how playback is implemented, and guessing would just produce noise.
"""
import shutil
import tempfile

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"


def load(path):
    with open(path, "r", encoding="utf-8", newline=None) as f:
        return f.read()


def save(path, text):
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


src = load(CPP)
orig = src

old_inc = "#include <cstdio>\r\n#include <cstring>"
if old_inc not in src:
    old_inc = "#include <cstdio>\n#include <cstring>"
assert src.count(old_inc) >= 1, "include anchor"
src = src.replace(old_inc, old_inc.replace("#include <cstring>", "#include <cstdlib>\n#include <cstring>"), 1)

anchor = """        const bool autoDma = (admas & (secondCore ? 2u : 1u)) != 0u;
        if (autoDma)
            delayCycles = std::max<uint64_t>(delayCycles, transferWords * kAdmaCyclesPerWord);"""
if anchor not in src:
    anchor = anchor.replace("\n", "\r\n")
assert src.count(anchor) == 1, ("dma anchor", src.count(anchor))

tap = anchor + """

        // 0072: the block is discarded once the interrupt is scheduled, so capture it while it is still in IOP RAM.
        // APE2_SPU2_DUMP=<dir> appends each core's stream to <dir>/spu2_coreN.bin.
        if (autoDma)
        {
            if (const char *dumpDir = std::getenv("APE2_SPU2_DUMP"))
            {
                static std::FILE *files[2] = {nullptr, nullptr};
                std::FILE *&file = files[secondCore ? 1 : 0];
                if (!file)
                {
                    char path[512];
                    std::snprintf(path, sizeof(path), "%s/spu2_core%u.bin", dumpDir, secondCore ? 1u : 0u);
                    file = std::fopen(path, "wb");
                }
                const uint32_t madrReg = secondCore ? 0x1F801500u : 0x1F8010C0u;
                uint32_t source = 0u;
                if (const auto current = m_hardware.find(madrReg); current != m_hardware.end())
                    source = current->second & 0x1FFFFFu;
                std::vector<uint8_t> block(static_cast<size_t>(transferWords) * 4u);
                if (file && source != 0u && readRam(source, block.data(), block.size()))
                {
                    std::fwrite(block.data(), 1, block.size(), file);
                    std::fflush(file);
                    static unsigned tapped[2] = {0u, 0u};
                    unsigned &count = tapped[secondCore ? 1 : 0];
                    if (count < 4u)
                    {
                        ++count;
                        const uint16_t *half = reinterpret_cast<const uint16_t *>(block.data());
                        std::fprintf(stderr,
                                     "[IOP] SPU2 tap core%u src=0x%08x words=%llu first=%04x %04x %04x %04x %04x %04x\\n",
                                     secondCore ? 1u : 0u, source,
                                     static_cast<unsigned long long>(transferWords),
                                     half[0], half[1], half[2], half[3], half[4], half[5]);
                    }
                }
            }
        }"""

src = src.replace(anchor, tap, 1)
assert src != orig

bak = tempfile.gettempdir() + r"\iop_memory.cpp.pretap"
shutil.copyfile(CPP, bak)
save(CPP, src)
print("patched", CPP)
print("tap refs:", src.count("APE2_SPU2_DUMP"), "backup:", bak)

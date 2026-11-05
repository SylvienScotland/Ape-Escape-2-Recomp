#!/usr/bin/env python3
"""0093: wire the SPU2 engine into the IOP memory map, DMA feed and audio pull.

Before this the SPU2 was only a register scratchpad plus a fabricated PCM ring in IOP RAM. Now:
  - register writes reach a real engine (voices, ADPCM decode, envelope, mixing),
  - DMA blocks for core0/core1 are copied into SPU2 sample RAM at the transfer address,
  - pullSpu2Pcm mixes the voices at 48 kHz instead of replaying a ring.
"""
import sys

HEADER = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.h"
SOURCE = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
CMAKE = r"C:\dev\PS2Recomp\ps2xIOP\CMakeLists.txt"


def load(path):
    return open(path, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def save(path, text):
    open(path, "w", encoding="utf-8", newline="\r\n").write(text)


def replace_once(text, anchor, new, label):
    count = text.count(anchor)
    if count != 1:
        print(f"FAIL: {label}: anchor matched {count} times")
        sys.exit(1)
    return text.replace(anchor, new, 1)


header = load(HEADER)
if "iop_spu2.h" not in header:
    header = replace_once(header, '#include "iop_sio2.h"', '#include "iop_sio2.h"\n#include "iop_spu2.h"', "header include")
if "m_spu2;" not in header:
    header = replace_once(
        header,
        "        mutable IopSio2 m_sio2;",
        "        mutable IopSio2 m_sio2;\n        IopSpu2 m_spu2; // 0093: real voices, ADPCM and mixing replace the IOP-RAM PCM ring",
        "header member",
    )
save(HEADER, header)
print("header wired")

cmake = load(CMAKE)
if "iop_spu2.cpp" not in cmake:
    cmake = replace_once(cmake, "    src/emulator/core/iop_memory.cpp",
                         "    src/emulator/core/iop_memory.cpp\n    src/emulator/core/iop_spu2.cpp",
                         "cmake source")
    save(CMAKE, cmake)
    print("cmake wired")

src = load(SOURCE)
if '#include "iop_spu2.h"' not in src:
    if '#include "iop_spu2.h"' not in src:
        _lines = src.split(chr(10))
        for _i, _ln in enumerate(_lines):
            if _ln.startswith('#include'):
                _lines.insert(_i + 1, '#include "iop_spu2.h"')
                break
        src = chr(10).join(_lines)

if "m_spu2.write32" not in src:
    src = replace_once(
        src,
        """        m_hardware[address] = value;
        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)
            return;
""",
        """        // 0093: hand the value to the real SPU2 register file so voices can be keyed and mixed.
        if (IopSpu2::contains(address))
            m_spu2.write32(address, value);

        m_hardware[address] = value;
        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)
            return;
""",
        "register routing",
    )

if "m_spu2.read32" not in src:
    src = replace_once(
        src,
        """    uint32_t IopMemory::readHardware32(uint32_t address) const
    {
        const auto value = m_hardware.find(address);
""",
        """    uint32_t IopMemory::readHardware32(uint32_t address) const
    {
        // 0093: envelopes and current addresses come from the engine once it is running voices.
        if (IopSpu2::contains(address) && m_spu2.keyonCount() != 0u)
            return m_spu2.read32(address);
        const auto value = m_hardware.find(address);
""",
        "register read routing",
    )

if "m_spu2.transferWrite" not in src:
    src = replace_once(
        src,
        "        // 0071: the auto-DMA source is the streamed music.",
        """        // 0093: every DMA block the driver sends is sample data for SPU2 RAM, at the core's transfer address.
        {
            const uint32_t madrReg = secondCore ? 0x1F801500u : 0x1F8010C0u;
            uint32_t source = 0u;
            if (const auto current = m_hardware.find(madrReg); current != m_hardware.end())
                source = current->second & 0x1FFFFFu;
            const uint32_t bytes = static_cast<uint32_t>(transferWords) * 4u;
            if (source != 0u && bytes != 0u)
            {
                std::vector<uint8_t> block(bytes);
                if (readRam(source, block.data(), block.size()))
                    m_spu2.transferWrite(secondCore ? 1 : 0, block.data(), bytes);
            }
        }

        // 0071: the auto-DMA source is the streamed music.""",
        "dma feed",
    )

start = src.find("    size_t IopMemory::pullSpu2Pcm(")
end = src.find("    std::optional<uint64_t> IopMemory::dmaRearmDelay(", start if start >= 0 else 0)
if start < 0 or end < 0:
    print("FAIL: pullSpu2Pcm bounds not found")
    sys.exit(1)
if "m_spu2.mix" not in src[start:end]:
    new_pull = """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        // 0093: play what the SPU2 voices produce. 48 kHz stereo is the hardware output rate, so one video frame is
        // 800 frames and no resampling is involved.
        if (!destination || frameCount == 0u)
            return 0u;

        const size_t frames = m_spu2.mix(destination, frameCount);
        if (frames == 0u)
            return 0u;

        if (const char *pcmPath = std::getenv("APE2_SPU2_PCM"))
        {
            static std::FILE *pcmFile = nullptr;
            static bool opened = false;
            if (!opened)
            {
                opened = true;
                pcmFile = std::fopen(pcmPath, "wb");
            }
            if (pcmFile)
            {
                std::fwrite(destination, sizeof(int16_t) * 2u, frames, pcmFile);
                std::fflush(pcmFile);
            }
        }
        return frames;
    }

"""
    src = src[:start] + new_pull + src[end:]

if "m_spu2.reset()" not in src:
    src = replace_once(
        src,
        """        m_admaTimer = AdmaTimer{};
        m_sio2.reset();
""",
        """        m_admaTimer = AdmaTimer{};
        m_sio2.reset();
        m_spu2.reset(); // 0093: clear voices and sample RAM with the rest of the machine
""",
        "reset wiring",
    )

save(SOURCE, src)
print("SPU2 engine wired")

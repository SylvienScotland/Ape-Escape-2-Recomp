#!/usr/bin/env python3
"""0077b: same change as spu2_adma_autonomous.py, but applied in verified steps.

The first attempt only patched the header before aborting, so the .cpp never changed and build 93 was the old code.
Each edit here reports its own status so a failure names itself instead of being lost in a timed-out log.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
HDR = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.h"
EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"


def read(path):
    return open(path, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def write(path, text):
    open(path, "w", encoding="utf-8", newline="\r\n").write(text)


def span(src, signature):
    start = src.index(signature)
    brace = src.index("{", start)
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(src) and src[end] in "\r\n":
                    end += 1
                return start, end
    raise SystemExit("ERROR: unbalanced braces")


def once(text, old, new, label, path):
    n = text.count(old)
    if n != 1:
        print(f"FAIL {label}: matched {n} times")
        sys.exit(1)
    print(f"ok   {label}")
    updated = text.replace(old, new, 1)
    write(path, updated)  # persist immediately so a later failure cannot lose this edit
    return updated


# ---------------- header (idempotent)
hdr = read(HDR)
if "dmaRearmDelay" not in hdr:
    hdr = once(hdr, "        [[nodiscard]] std::optional<DmaStart> takeDmaStart() noexcept;",
               "        [[nodiscard]] std::optional<DmaStart> takeDmaStart() noexcept;\n"
               "        // 0077: autonomous auto-DMA - per-block period to keep re-scheduling while armed.\n"
               "        [[nodiscard]] std::optional<uint64_t> dmaRearmDelay(int irq) const noexcept;",
               "header declaration", HDR)
if "AdmaTimer m_admaTimer" not in hdr:
    hdr = once(hdr, "        std::optional<DmaStart> m_dmaStart;",
               "        struct AdmaTimer\n"
               "        {\n"
               "            bool active = false;\n"
               "            int irq = 0;\n"
               "            uint64_t delayCycles = 0;\n"
               "        };\n"
               "        std::optional<DmaStart> m_dmaStart;\n"
               "        AdmaTimer m_admaTimer; // 0077: autonomous auto-DMA block interrupt",
               "header member", HDR)

# ---------------- memory
cpp = read(CPP)
if "m_admaTimer.active = true;" not in cpp:
    cpp = once(cpp,
               "        if (autoDma)\n"
               "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * admaCyclesPerWord());\n",
               "        if (autoDma)\n"
               "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * admaCyclesPerWord());\n"
               "\n"
               "        // 0077: auto-DMA runs on its own once armed, so remember the block period and keep raising\n"
               "        // the completion interrupt without waiting for another CHCR write from the driver.\n"
               "        if (autoDma)\n"
               "        {\n"
               "            m_admaTimer.active = true;\n"
               "            m_admaTimer.irq = secondCore ? kDmaSpu1Irq : kDmaSpu0Irq;\n"
               "            m_admaTimer.delayCycles = delayCycles;\n"
               "        }\n",
               "arm timer", CPP)

# stop re-arming when the driver clears ADMAS's auto bits
if "clearing ADMAS's auto bits" not in cpp:
    cpp = once(cpp,
               "        m_hardware[address] = value;\n"
               "        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)\n",
               "        // 0077: clearing ADMAS's auto bits is how the driver stops the stream.\n"
               "        if ((address == kSpu2Core0AdmasWord || address == kSpu2Core0AdmasWord + kSpu2CoreStride) &&\n"
               "            (value & 0x3u) == 0u)\n"
               "            m_admaTimer.active = false;\n"
               "\n"
               "        m_hardware[address] = value;\n"
               "        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)\n",
               "admas stop", CPP)

if "m_admaTimer = AdmaTimer{};" not in cpp:
    cpp = once(cpp, "        m_dmaStart.reset();\n    }",
               "        m_dmaStart.reset();\n        m_admaTimer = AdmaTimer{};\n    }", "reset()", CPP)

if "IopMemory::dmaRearmDelay" not in cpp:
    cpp = once(cpp, "    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept",
               "    std::optional<uint64_t> IopMemory::dmaRearmDelay(int irq) const noexcept\n"
               "    {\n"
               "        if (!m_admaTimer.active || m_admaTimer.irq != irq || m_admaTimer.delayCycles == 0u)\n"
               "            return std::nullopt;\n"
               "        return m_admaTimer.delayCycles;\n"
               "    }\n"
               "\n"
               "    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept",
               "rearm definition", CPP)

if "reads the ring straight out of IOP RAM" not in cpp:
    start, end = span(cpp, "size_t IopMemory::pullSpu2Pcm(")
    cpp = cpp[:start] + """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        // 0077: playback reads the ring straight out of IOP RAM, the way the auto-DMA engine does. With the block
        // interrupt now firing on its own, the driver refills behind this cursor and new audio is picked up as it is
        // written; the arm-time shadow survives only for APE2_SPU2_SHADOW=1 comparison.
        Spu2Ring &ring = spu2Ring();
        constexpr size_t kFrameBytes = 4u; // 16-bit stereo
        if (!destination || frameCount == 0u || !ring.ready || ring.size < 4u)
            return 0u;
        if (static_cast<uint64_t>(ring.base) + ring.size > m_ram.size())
            return 0u;

        const bool useShadow = shadowPlayback();
        const uint8_t *source = useShadow ? ring.shadow.data() : m_ram.data();
        const uint32_t sourceBase = useShadow ? ring.base : 0u;
        auto *out = reinterpret_cast<uint8_t *>(destination);
        for (size_t produced = 0u; produced < frameCount; ++produced)
        {
            std::memcpy(out + produced * kFrameBytes, source + (ring.cursor - sourceBase), kFrameBytes);
            ring.cursor += kFrameBytes;
            if (ring.cursor + kFrameBytes > ring.base + ring.size)
                ring.cursor = ring.base; // the engine reads the ring round and round
        }

        ring.framesOut += frameCount;
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
                std::fwrite(out, kFrameBytes, frameCount, pcmFile);
                std::fflush(pcmFile);
            }
        }
        return frameCount;
    }

""" + cpp[end:]
    write(CPP, cpp)
    print("ok   live-read playback")

# ---------------- emulator: re-arm after dispatching each completed DMA interrupt
emu = read(EMU)
if "dmaRearmDelay" not in emu:
    emu = once(emu,
               "                reportIrqPerf();\n",
               "                // 0077: auto-DMA is autonomous - keep the block completion interrupt scheduled so the\n"
               "                // driver is told to refill without having to arm another block first.\n"
               "                for (const int irq : completed)\n"
               "                {\n"
               "                    if (const auto rearm = memory.dmaRearmDelay(irq))\n"
               "                        pendingDmaInterrupts[irq] = totalCycles + *rearm;\n"
               "                }\n"
               "                reportIrqPerf();\n",
               "emulator rearm", EMU)
print("done")

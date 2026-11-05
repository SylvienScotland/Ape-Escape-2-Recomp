#!/usr/bin/env python3
"""0077: make SPU2 auto-DMA autonomous and play the ring from live IOP RAM.

Evidence this targets: the PCM tap shows ~18 blocks of real audio (36 unique 10.7 ms chunks) and then a held frame,
and `m_dmaStart` is only ever set from a driver write, so a completion interrupt can only happen immediately after
the driver arms. A driver that arms a few blocks and then waits for block-completion interrupts therefore
deadlocks with the current model after the priming burst - which is exactly the measured shape.

Hardware auto-DMA is autonomous: once armed it transfers block after block, raising one interrupt per block,
while the driver refills behind the read pointer. This patch keeps the per-block interrupt scheduled without
further CHCR writes and has playback read the ring out of live IOP RAM (shadow only with APE2_SPU2_SHADOW=1), so
refills written while a block plays are picked up instead of being frozen at arm time.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
HDR = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.h"
EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"


def read(path):
    return open(path, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def write(path, text):
    open(path, "w", encoding="utf-8", newline="\r\n").write(text)


def function_span(src, signature):
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


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"ERROR: {label} matched {text.count(old)} times")
    return text.replace(old, new, 1)


# ---------------- header: timer state + query
hdr = read(HDR)
if "AdmaTimer" in hdr:
    print("header already patched")
else:
    hdr = replace_once(
        hdr,
        "        [[nodiscard]] std::optional<DmaStart> takeDmaStart() noexcept;",
        "        [[nodiscard]] std::optional<DmaStart> takeDmaStart() noexcept;\n"
        "        // 0077: autonomous auto-DMA - the per-block period to keep re-scheduling, while it stays armed.\n"
        "        [[nodiscard]] std::optional<uint64_t> dmaRearmDelay(int irq) const noexcept;",
        "header declaration",
    )
    hdr = replace_once(
        hdr,
        "        std::optional<DmaStart> m_dmaStart;",
        "        struct AdmaTimer\n"
        "        {\n"
        "            bool active = false;\n"
        "            int irq = 0;\n"
        "            uint64_t delayCycles = 0;\n"
        "        };\n"
        "        std::optional<DmaStart> m_dmaStart;\n"
        "        AdmaTimer m_admaTimer; // 0077: autonomous auto-DMA block interrupt",
        "header member",
    )
    write(HDR, hdr)
    print("header patched")

# ---------------- memory: arm the timer, stop it on ADMAS clear, expose the delay, live playback
cpp = read(CPP)
if "m_admaTimer" in cpp:
    print("memory already patched")
else:
    cpp = replace_once(
        cpp,
        "        if (autoDma)\n"
        "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * admaCyclesPerWord());\n",
        "        if (autoDma)\n"
        "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * admaCyclesPerWord());\n"
        "\n"
        "        // 0077: auto-DMA runs on its own once armed. Keep the block period so the emulator can raise the\n"
        "        // completion interrupt again without waiting for another CHCR write from the driver.\n"
        "        if (autoDma)\n"
        "        {\n"
        "            m_admaTimer.active = true;\n"
        "            m_admaTimer.irq = secondCore ? kDmaSpu1Irq : kDmaSpu0Irq;\n"
        "            m_admaTimer.delayCycles = delayCycles;\n"
        "        }\n",
        "arm timer",
    )

    # stop the stream when the driver clears the auto-DMA enable bits
    cpp = replace_once(
        cpp,
        "        m_hardware[address] = value;\n"
        "        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)\n"
        "            return;\n",
        "        // 0077: clearing ADMAS's auto bits is how the driver stops the stream; stop re-arming then.\n"
        "        if ((address == kSpu2Core0AdmasWord || address == kSpu2Core0AdmasWord + kSpu2CoreStride) &&\n"
        "            (value & 0x3u) == 0u)\n"
        "            m_admaTimer.active = false;\n"
        "\n"
        "        m_hardware[address] = value;\n"
        "        if ((address != kDmaSpu0Chcr && address != kDmaSpu1Chcr) || (value & kDmaStart) == 0u)\n"
        "            return;\n",
        "admas stop",
    )

    cpp = replace_once(cpp, "        m_dmaStart.reset();\n", "        m_dmaStart.reset();\n        m_admaTimer = AdmaTimer{};\n", "reset")

    cpp = replace_once(
        cpp,
        "    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept",
        "    std::optional<uint64_t> IopMemory::dmaRearmDelay(int irq) const noexcept\n"
        "    {\n"
        "        if (!m_admaTimer.active || m_admaTimer.irq != irq || m_admaTimer.delayCycles == 0u)\n"
        "            return std::nullopt;\n"
        "        return m_admaTimer.delayCycles;\n"
        "    }\n"
        "\n"
        "    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept",
        "rearm definition",
    )

    start, end = function_span(cpp, "size_t IopMemory::pullSpu2Pcm(")
    cpp = cpp[:start] + """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        // 0077: playback reads the ring straight out of IOP RAM, the way the auto-DMA engine does. With the block
        // interrupt now firing on its own, the driver refills behind this cursor and the new audio is picked up as
        // it is written; the arm-time shadow is kept only for APE2_SPU2_SHADOW=1 comparison.
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
    print("memory patched")

# ---------------- emulator: keep the interrupt scheduled while armed
emu = read(EMU)
if "dmaRearmDelay" in emu:
    print("emulator already patched")
else:
    emu = replace_once(
        emu,
        "                            s.lastEndPc = lastCallEndPc;\n"
        "                        }\n"
        "                    }\n"
        "                }\n",
        "                            s.lastEndPc = lastCallEndPc;\n"
        "                        }\n"
        "                    }\n"
        "\n"
        "                    // 0077: auto-DMA is autonomous - re-schedule the block completion interrupt so the\n"
        "                    // driver keeps being told to refill, without it having to arm another block first.\n"
        "                    if (const auto rearm = memory.dmaRearmDelay(irq))\n"
        "                        pendingDmaInterrupts[irq] = totalCycles + *rearm;\n"
        "                }\n",
        "emulator rearm",
    )
    write(EMU, emu)
    print("emulator patched")

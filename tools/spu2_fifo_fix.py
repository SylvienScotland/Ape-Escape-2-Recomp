#!/usr/bin/env python3
"""0075b: play each armed SPU2 block once, from a buffer, instead of walking live IOP RAM.

First listening test: audio is audible but garbled. Cause is structural, not a level/pitch problem. Playback
followed the armed DAM address as a cursor, but 12,595 of 20,576 arms re-read a block that had already been
played, so the cursor kept jumping backwards and the host repeated and skipped chunks while the driver rewrote
the same memory underneath it.

Fix: copy each armed block into a 2 s FIFO at arm time and play out of the FIFO. A block whose bytes match the
previous block exactly is a re-read and is skipped, which is the difference between 20,576 blocks and the ~8,000
distinct ones actually produced. Playing from owned memory also removes the read/write race on the ring.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "spu2PushBlock" in text:
    print("already patched")
    sys.exit(0)

# ---- 1. file-local playback state + block append, placed next to the SPU2 constants
anchor_const = "constexpr uint64_t kAdmaCyclesPerWord = 36'864'000ull / 48'000ull; // IOP clock / 48 kHz = 768"
if text.count(anchor_const) != 1:
    raise SystemExit(f"ERROR: constant anchor matched {text.count(anchor_const)} times")

helper = anchor_const + """

        namespace
        {
            // 0075b: SPU2 streamed playback. The sound driver arms auto-DMA on blocks it has just written, and
            // re-arms blocks it has already played, so playback is driven from blocks copied here at arm time:
            // re-reads are recognised by content and skipped, and the host never reads memory being rewritten.
            constexpr size_t kSpu2FifoFrames = 48'000u * 2u; // two seconds of cushion

            struct Spu2Playback
            {
                std::vector<int16_t> fifo = std::vector<int16_t>(kSpu2FifoFrames * 2u, 0);
                std::vector<uint8_t> lastBlock;
                size_t head = 0u;
                size_t count = 0u;
                unsigned arms = 0u;
                unsigned reReads = 0u;
            };

            Spu2Playback &spu2Playback()
            {
                static Spu2Playback state;
                return state;
            }

            void spu2PushBlock(const std::vector<uint8_t> &ram, uint32_t address, uint32_t sizeBytes)
            {
                if (sizeBytes < 4u || address + sizeBytes > ram.size())
                    return;

                Spu2Playback &state = spu2Playback();
                const uint8_t *block = ram.data() + address;
                if (state.lastBlock.size() == sizeBytes &&
                    std::memcmp(state.lastBlock.data(), block, sizeBytes) == 0)
                {
                    ++state.reReads;
                    return;
                }
                state.lastBlock.assign(block, block + sizeBytes);

                const size_t frames = sizeBytes / 4u;
                for (size_t i = 0; i < frames; ++i)
                {
                    int16_t frame[2];
                    std::memcpy(frame, block + i * 4u, sizeof(frame));
                    const size_t slot = (state.head + state.count) % kSpu2FifoFrames;
                    state.fifo[slot * 2u + 0u] = frame[0];
                    state.fifo[slot * 2u + 1u] = frame[1];
                    if (state.count < kSpu2FifoFrames)
                        ++state.count;
                    else
                        state.head = (state.head + 1u) % kSpu2FifoFrames; // overrun: drop the oldest
                }

                if (++state.arms <= 20u || state.arms % 400u == 0u)
                    std::fprintf(stderr, "[spu2:arm] n=%u src=0x%08x size=%u reReads=%u fifo=%zu frames\\n",
                                 state.arms, address, sizeBytes, state.reReads, state.count);
            }
        }"""

text = text.replace(anchor_const, helper, 1)

# ---- 2. arm hook: queue the block instead of moving a read cursor
old_arm = """        if (autoDma && secondCore)
        {
            const uint32_t madrWord = 0x1F801500u;
            uint32_t streamSource = 0u;
            if (const auto current = m_hardware.find(madrWord); current != m_hardware.end())
                streamSource = current->second & 0x1FFFFFu;
            if (streamSource != 0u)
            {
                m_spu2ReadAddr = streamSource;
                m_spu2Armed = true;
            }
        }"""
if text.count(old_arm) != 1:
    raise SystemExit(f"ERROR: arm hook matched {text.count(old_arm)} times")

new_arm = """        if (autoDma && secondCore)
        {
            const uint32_t madrWord = 0x1F801500u;
            uint32_t streamSource = 0u;
            if (const auto current = m_hardware.find(madrWord); current != m_hardware.end())
                streamSource = current->second & 0x1FFFFFu;
            if (streamSource != 0u)
            {
                m_spu2Armed = true;
                spu2PushBlock(m_ram, streamSource, static_cast<uint32_t>(transferWords) * 4u);
            }
        }"""
text = text.replace(old_arm, new_arm, 1)

# ---- 3. pull from the FIFO
old_pull_start = "    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)\n    {"
start = text.index(old_pull_start)
end = text.index("\n    }\n", start) + len("\n    }\n")
new_pull = """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        Spu2Playback &state = spu2Playback();
        if (!destination || frameCount == 0u || state.count == 0u)
            return 0u;

        size_t produced = 0u;
        while (produced < frameCount && state.count != 0u)
        {
            const size_t slot = state.head;
            destination[produced * 2u + 0u] = state.fifo[slot * 2u + 0u];
            destination[produced * 2u + 1u] = state.fifo[slot * 2u + 1u];
            state.head = (state.head + 1u) % kSpu2FifoFrames;
            --state.count;
            ++produced;
        }
        return produced;
    }
"""
text = text[:start] + new_pull + text[end:]

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("fifo playback patched")

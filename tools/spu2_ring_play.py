#!/usr/bin/env python3
"""0075c: play the SPU2 auto-DMA ring the way the hardware does.

Measured facts that decide this design:
  - the driver arms only two addresses, 0x4be40 and 0x4c240, 1024 bytes each: a 2 KB double buffer;
  - it re-arms them continuously, and most arms are byte-identical because the SPU2 is expected to keep
    reading the ring, not to consume a block per arm;
  - playback must therefore walk the ring and wrap at its end, at one 4-byte stereo frame per output frame.

Two earlier attempts failed for opposite reasons and both are now replaced:
  - jumping the read cursor to each armed address replayed and skipped chunks (6 of 10 arms are re-reads);
  - consuming a block per arm starved the output (~28k frames/s of new content against 48k needed).

The ring is learned from the arms: base and size grow while arms land in the same small window, and a
far-away arm restarts it. Nothing is copied, so there is no stale buffer to go out of sync.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "spu2AdvanceRing" in text:
    print("already patched")
    sys.exit(0)

# ---- 1. replace the block FIFO helper with ring tracking
start = text.index("        namespace\n        {\n            // 0075b: SPU2 streamed playback.")
end = text.index("        }", text.index("std::fprintf(stderr, \"[spu2:arm]"))
end = text.index("\n        }\n", end) + len("\n        }\n")

helper = """        namespace
        {
            // 0075c: SPU2 auto-DMA ring playback. The driver keeps a small ring in IOP RAM and arms its blocks;
            // the SPU2 reads that ring continuously and wraps at its end. Base and size are learned from the arms,
            // because that is the only description of the ring the hardware ever gets.
            struct Spu2Ring
            {
                uint32_t base = 0u;
                uint32_t size = 0u;
                uint32_t cursor = 0u;
                bool ready = false;
                bool measured = false; // first arm only logs the initial ring
            };

            Spu2Ring &spu2Ring()
            {
                static Spu2Ring ring;
                return ring;
            }

            void spu2NoteArm(uint32_t address, uint32_t sizeBytes)
            {
                if (address == 0u || sizeBytes == 0u)
                    return;

                Spu2Ring &ring = spu2Ring();
                if (!ring.ready)
                {
                    ring.base = address;
                    ring.size = sizeBytes;
                    ring.cursor = address;
                    ring.ready = true;
                    std::fprintf(stderr, "[spu2:ring] base=0x%08x size=%u\\n", ring.base, ring.size);
                    return;
                }

                const int64_t delta = static_cast<int64_t>(address) - static_cast<int64_t>(ring.base);
                if (delta >= 0 && delta + sizeBytes <= ring.size)
                    return; // same ring, block already inside it

                const uint64_t magnitude = static_cast<uint64_t>(delta < 0 ? -delta : delta);
                if (magnitude <= 0x20000u)
                {
                    if (delta < 0)
                    {
                        ring.size += static_cast<uint32_t>(-delta);
                        ring.base = address;
                    }
                    else
                    {
                        ring.size = static_cast<uint32_t>(delta) + sizeBytes;
                    }
                    if (ring.size > RamSize)
                        ring.size = RamSize;
                    std::fprintf(stderr, "[spu2:ring] grown base=0x%08x size=%u\\n", ring.base, ring.size);
                }
                else
                {
                    // A distant address means the driver moved to another buffer: follow it.
                    ring.base = address;
                    ring.size = sizeBytes;
                    ring.cursor = address;
                    std::fprintf(stderr, "[spu2:ring] moved base=0x%08x size=%u\\n", ring.base, ring.size);
                    return;
                }

                if (ring.cursor < ring.base || ring.cursor >= ring.base + ring.size)
                    ring.cursor = ring.base;
            }
        }
"""
text = text[:start] + helper + text[end:]

# ---- 2. arm hook calls the ring tracker
old_arm = """                m_spu2Armed = true;
                spu2PushBlock(m_ram, streamSource, static_cast<uint32_t>(transferWords) * 4u);"""
if text.count(old_arm) != 1:
    raise SystemExit(f"ERROR: arm call matched {text.count(old_arm)} times")
text = text.replace(old_arm, """                m_spu2Armed = true;
                spu2NoteArm(streamSource, static_cast<uint32_t>(transferWords) * 4u);""", 1)

# ---- 3. pull walks the ring with wrap
old_pull_start = "    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)\n    {"
start = text.index(old_pull_start)
end = text.index("\n    }\n", start) + len("\n    }\n")
new_pull = """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        Spu2Ring &ring = spu2Ring();
        if (!destination || frameCount == 0u || !ring.ready || ring.size < 4u)
            return 0u;

        constexpr uint32_t kFrameBytes = 4u; // 16-bit stereo
        auto *out = reinterpret_cast<uint8_t *>(destination);
        size_t produced = 0u;
        while (produced < frameCount && ring.cursor + kFrameBytes <= base_probe())
        {
            break;
        }
        while (produced < frameCount)
        {
            std::memcpy(out + produced * kFrameBytes, m_ram.data() + ring.cursor, kFrameBytes);
            ring.cursor += kFrameBytes;
            if (ring.cursor + kFrameBytes > ring.base + ring.size)
                ring.cursor = ring.base; // wrap: the hardware reads the ring round and round
            ++produced;
        }
        return produced;
    }
"""
text = text[:start] + new_pull + text[end:]
text = text.replace("        while (produced < frameCount && ring.cursor + kFrameBytes <= base_probe())\n        {\n            break;\n        }\n", "", 1)

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("ring playback patched")

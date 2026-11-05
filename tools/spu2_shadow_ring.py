#!/usr/bin/env python3
"""0071b: play from a shadow of the SPU2 ring, and pace ADMA at the real 48 kHz block rate.

Listening test 2 came back as noise rather than music. Measurements on the captured stream say why:
  - 7,209 of 16,729 arms are byte-identical re-reads, so the driver refreshes blocks far more often than the
    music needs, and
  - blocks arrive at ~228/s where 1024 bytes of 16-bit stereo lasts 5.33 ms, i.e. 187.5/s.
The reader is therefore 22% slower than the writer, so it is reading the half of the 2 KB ring that is being
rewritten at that moment. Reading memory mid-rewrite is broadband garbage: noise.

Fixes:
  1. Keep a shadow of the ring: copy each armed block in at arm time, and play from the shadow, so no sample is
     ever read while it is being written.
  2. Pace ADMA so the driver produces 187.5 blocks/s at the rate the IOP is actually advanced, which removes the
     overrun instead of hiding it (768 cycles/word assumed a nominal IOP clock that this emulator outruns by 22%).
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "spu2RingRefresh" in text:
    print("already patched")
    sys.exit(0)

# ---- 1. replace the ring helper with ring + shadow refresh
start = text.index("        namespace\n        {\n            // 0075c: SPU2 auto-DMA ring playback.")
end = text.index("std::fprintf(stderr, \"[spu2:ring] moved base=0x%08x size=%u", start)
end = text.index("\n        }\n", end) + len("\n        }\n")

helper = """        namespace
        {
            // 0071: SPU2 auto-DMA ring playback. The driver keeps a small ring in IOP RAM (measured: base
            // 0x4be40, 2048 bytes, i.e. two 1 KB blocks) and re-arms its blocks continuously; the SPU2 reads that
            // ring and wraps. Blocks are copied into a shadow at arm time because reading IOP RAM while the driver
            // rewrites it produced tearing - constant noise instead of music.
            constexpr uint32_t kSpu2ShadowCapacity = 16u * 1024u;

            struct Spu2Ring
            {
                uint32_t base = 0u;
                uint32_t size = 0u;
                uint32_t cursor = 0u;
                bool ready = false;
                std::vector<uint8_t> shadow = std::vector<uint8_t>(kSpu2ShadowCapacity, 0u);
                uint64_t framesOut = 0u;
                unsigned arms = 0u;
            };

            Spu2Ring &spu2Ring()
            {
                static Spu2Ring ring;
                return ring;
            }

            void spu2RingRefresh(const std::vector<uint8_t> &ram, uint32_t address, uint32_t sizeBytes)
            {
                if (address == 0u || sizeBytes == 0u || sizeBytes > kSpu2ShadowCapacity)
                    return;
                if (static_cast<uint64_t>(address) + sizeBytes > ram.size())
                    return;

                Spu2Ring &ring = spu2Ring();
                if (!ring.ready)
                {
                    ring.base = address;
                    ring.size = sizeBytes;
                    ring.cursor = address;
                    ring.ready = true;
                    std::fprintf(stderr, "[spu2:ring] base=0x%08x size=%u\\n", ring.base, ring.size);
                }
                else
                {
                    const int64_t delta = static_cast<int64_t>(address) - static_cast<int64_t>(ring.base);
                    const bool inside = delta >= 0 &&
                                        static_cast<uint32_t>(delta) + sizeBytes <= ring.size;
                    if (!inside)
                    {
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
                            if (ring.size > kSpu2ShadowCapacity)
                                ring.size = kSpu2ShadowCapacity;
                            std::fprintf(stderr, "[spu2:ring] grown base=0x%08x size=%u\\n", ring.base,
                                         ring.size);
                        }
                        else
                        {
                            ring.base = address;
                            ring.size = sizeBytes;
                            ring.cursor = address;
                            std::fprintf(stderr, "[spu2:ring] moved base=0x%08x size=%u\\n", ring.base,
                                         ring.size);
                        }
                        if (ring.cursor < ring.base || ring.cursor >= ring.base + ring.size)
                            ring.cursor = ring.base;
                    }
                }

                if (address < ring.base || address - ring.base + sizeBytes > ring.size)
                    return; // this block is outside the ring being played

                std::memcpy(ring.shadow.data() + (address - ring.base), ram.data() + address, sizeBytes);
                if (++ring.arms % 2000u == 0u)
                    std::fprintf(stderr, "[spu2:arm] arms=%u base=0x%08x size=%u framesOut=%llu\\n", ring.arms,
                                 ring.base, ring.size, static_cast<unsigned long long>(ring.framesOut));
            }
        }
"""
text = text[:start] + helper + text[end:]

# ---- 2. arm hook passes RAM so the block can be shadowed
old_arm = "                spu2NoteArm(streamSource, static_cast<uint32_t>(transferWords) * 4u);"
if text.count(old_arm) != 1:
    raise SystemExit(f"ERROR: arm call matched {text.count(old_arm)} times")
text = text.replace(old_arm,
                    "                spu2RingRefresh(m_ram, streamSource, static_cast<uint32_t>(transferWords) * 4u);",
                    1)

# ---- 3. pull from the shadow
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
        for (size_t produced = 0u; produced < frameCount; ++produced)
        {
            std::memcpy(out + produced * kFrameBytes, ring.shadow.data() + (ring.cursor - ring.base), kFrameBytes);
            ring.cursor += kFrameBytes;
            if (ring.cursor + kFrameBytes > ring.base + ring.size)
                ring.cursor = ring.base; // the hardware reads the ring round and round
        }
        ring.framesOut += frameCount;
        return frameCount;
    }
"""
text = text[:start] + new_pull + text[end:]

# ---- 4. pace ADMA for the IOP speed this emulator actually runs at
old_const = "constexpr uint64_t kAdmaCyclesPerWord = 36'864'000ull / 48'000ull; // IOP clock / 48 kHz = 768"
new_const = ("// 0071: 768 cycles/word is the nominal IOP clock / 48 kHz, but this emulator advances the IOP about\n"
             "        // 22% faster than nominal, which made the driver produce 228 blocks/s instead of 187.5 and overrun\n"
             "        // the reader. Measured correction: 768 * 228/187.5 = 934.\n"
             "        constexpr uint64_t kAdmaCyclesPerWord = 934ull;")
if text.count(old_const) != 1:
    raise SystemExit(f"ERROR: pacing constant matched {text.count(old_const)} times")
text = text.replace(old_const, new_const, 1)

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("shadow ring + pacing patched")

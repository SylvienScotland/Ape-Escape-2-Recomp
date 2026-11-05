#!/usr/bin/env python3
"""0071c: make the ADMA pacing sweepable and measure ring health without listening.

The pacing constant could not be calibrated from arm counts: the same driver arms the ring far more often than it
writes new audio (43% of arms are byte-identical re-reads), so arms/s is a noisy proxy. What actually matters is
whether each ring slot is refreshed once per lap. With a 2048-byte ring of two 1 KB blocks that number is exactly
2.0: below it the reader replays stale audio, above it the writer laps the reader.

So: APE2_SPU2_ADMA_CYCLES overrides cycles-per-word at runtime (sweep without rebuilding), and a periodic
[spu2:lap] line reports armsPerLap, measured in wall clock against framesOut.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "admaCyclesPerWord" in text:
    print("already patched")
    sys.exit(0)

if "#include <cstdlib>" not in text:
    text = text.replace("namespace ps2x::iop::detail",
                        "#include <cstdlib>\n\nnamespace ps2x::iop::detail", 1)

# ---- 1. pacing constant becomes a function with an env override
old_const = """        // 0071: 768 cycles/word is the nominal IOP clock / 48 kHz, but this emulator advances the IOP about
        // 22% faster than nominal, which made the driver produce 228 blocks/s instead of 187.5 and overrun
        // the reader. Measured correction: 768 * 228/187.5 = 934.
        constexpr uint64_t kAdmaCyclesPerWord = 934ull;"""
if text.count(old_const) != 1:
    raise SystemExit(f"ERROR: pacing block matched {text.count(old_const)} times")

new_const = """        // 0071: auto-DMA pacing, in IOP cycles per 16-bit word. Nominal hardware is 384 (512 words per 1 KB
        // block = 5.33 ms), but the wall-clock rate depends on how fast this emulator actually advances the IOP,
        // so it stays overridable until [spu2:lap] shows the ring refreshed exactly once per lap.
        uint64_t admaCyclesPerWord()
        {
            static const uint64_t value = []()
            {
                if (const char *env = std::getenv("APE2_SPU2_ADMA_CYCLES"))
                {
                    const long parsed = std::strtol(env, nullptr, 10);
                    if (parsed >= 32 && parsed <= 100000)
                        return static_cast<uint64_t>(parsed);
                }
                return 934ull;
            }();
            return value;
        }"""
text = text.replace(old_const, new_const, 1)

old_use = "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * kAdmaCyclesPerWord);"
if text.count(old_use) != 1:
    raise SystemExit(f"ERROR: delay use matched {text.count(old_use)} times")
text = text.replace(old_use, "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * admaCyclesPerWord());", 1)

# ---- 2. lap accounting in the ring state
old_state = """                std::vector<uint8_t> shadow = std::vector<uint8_t>(kSpu2ShadowCapacity, 0u);
                uint64_t framesOut = 0u;
                unsigned arms = 0u;"""
if text.count(old_state) != 1:
    raise SystemExit(f"ERROR: ring state matched {text.count(old_state)} times")
text = text.replace(old_state, """                std::vector<uint8_t> shadow = std::vector<uint8_t>(kSpu2ShadowCapacity, 0u);
                uint64_t framesOut = 0u;
                unsigned arms = 0u;
                unsigned armsThisLap = 0u;
                unsigned laps = 0u;
                uint64_t armsLapSum = 0u;""", 1)

# ---- 3. count refreshes, and report refreshes per lap
old_copy = """                std::memcpy(ring.shadow.data() + (address - ring.base), ram.data() + address, sizeBytes);
                if (++ring.arms % 2000u == 0u)
                    std::fprintf(stderr, "[spu2:arm] arms=%u base=0x%08x size=%u framesOut=%llu\\n", ring.arms,
                                 ring.base, ring.size, static_cast<unsigned long long>(ring.framesOut));"""
if text.count(old_copy) != 1:
    raise SystemExit(f"ERROR: shadow copy matched {text.count(old_copy)} times")
text = text.replace(old_copy, """                std::memcpy(ring.shadow.data() + (address - ring.base), ram.data() + address, sizeBytes);
                ++ring.arms;
                ++ring.armsThisLap;""", 1)

# ---- 4. lap completion in the pull loop
old_wrap = """            if (ring.cursor + kFrameBytes > ring.base + ring.size)
                ring.cursor = ring.base; // the hardware reads the ring round and round
        }"""
if text.count(old_wrap) < 1:
    raise SystemExit("ERROR: wrap site not found")
new_wrap = """            if (ring.cursor + kFrameBytes > ring.base + ring.size)
            {
                ring.cursor = ring.base; // the hardware reads the ring round and round
                ring.armsLapSum += ring.armsThisLap;
                ring.armsThisLap = 0u;
                if (++ring.laps >= 94u) // ~1 s of 2 KB laps at 48 kHz
                {
                    const double perLap = static_cast<double>(ring.armsLapSum) / static_cast<double>(ring.laps);
                    std::fprintf(stderr,
                                 "[spu2:lap] armsPerLap=%.2f size=%u framesOut=%llu speed=%.1f frames/s\\n", perLap,
                                 ring.size, static_cast<unsigned long long>(ring.framesOut),
                                 static_cast<double>(ring.framesOut) / 48'000.0);
                    ring.laps = 0u;
                    ring.armsLapSum = 0u;
                }
            }
        }"""
text = text.replace(old_wrap, new_wrap, 1)

# framesOut is advanced after the loop; keep that intact
if "ring.framesOut += frameCount;" not in text:
    raise SystemExit("ERROR: framesOut advancement missing")

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("pacing sweep + lap metric patched")

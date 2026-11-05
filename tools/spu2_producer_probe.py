#!/usr/bin/env python3
"""0073: measure whether the IOP keeps up, and whether armed blocks actually carry new audio.

Offline analysis of the captured stream says the music content is real (spectral flatness 0.054, lag-1 0.87-0.98)
but that block[i] == block[i+2] for 3,039 of the first 4,000 arms: the driver re-arms a slot far more often than
it refills it, so any player reading that ring replays ~10 ms of music and buzzes.

Two things decide the fix, and both are cheap to measure:
  - [iop:rate]   IOP cycles executed per wall second against the 36.864 MHz the hardware would run. If the
                 interpreter is far behind, the driver's producer cannot keep up no matter how playback is timed.
  - [spu2:arm]   fresh vs stale arms, counted by comparing each incoming block with the shadow slot it replaces.
                 A working stream needs ~187.5 fresh blocks/s (1024 bytes = 5.33 ms of 48 kHz stereo).
"""
import sys

IOP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"

# ---- 1. fresh/stale accounting on the shadow copy
text = open(IOP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")
if "fresh=" in text:
    print("iop_memory already patched")
else:
    old = """                std::memcpy(ring.shadow.data() + (address - ring.base), ram.data() + address, sizeBytes);
                ++ring.arms;
                ++ring.armsThisLap;"""
    if text.count(old) != 1:
        raise SystemExit(f"ERROR: shadow copy matched {text.count(old)} times")
    new = """                const size_t slotOffset = address - ring.base;
                if (std::memcmp(ring.shadow.data() + slotOffset, ram.data() + address, sizeBytes) != 0)
                    ++ring.freshArms;
                else
                    ++ring.staleArms;
                std::memcpy(ring.shadow.data() + slotOffset, ram.data() + address, sizeBytes);
                ++ring.arms;
                ++ring.armsThisLap;
                if (ring.arms % 2000u == 0u)
                    std::fprintf(stderr,
                                 "[spu2:arm] arms=%u fresh=%u stale=%u framesOut=%llu (%.1f fresh blocks/s over %.1fs)\\n",
                                 ring.arms, ring.freshArms, ring.staleArms,
                                 static_cast<unsigned long long>(ring.framesOut), static_cast<double>(ring.freshArms),
                                 static_cast<double>(ring.framesOut) / 48'000.0);"""
    text = text.replace(old, new, 1)

    old_state = """                unsigned armsThisLap = 0u;
                unsigned laps = 0u;
                uint64_t armsLapSum = 0u;"""
    if text.count(old_state) != 1:
        raise SystemExit(f"ERROR: ring state matched {text.count(old_state)} times")
    text = text.replace(old_state, """                unsigned armsThisLap = 0u;
                unsigned laps = 0u;
                uint64_t armsLapSum = 0u;
                unsigned freshArms = 0u;
                unsigned staleArms = 0u;""", 1)
    open(IOP, "w", encoding="utf-8", newline="\r\n").write(text)
    print("iop_memory probe added")

# ---- 2. IOP throughput against wall clock
text = open(EMU, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")
if "[iop:rate]" in text:
    print("iop_emulator already patched")
else:
    anchor = "void runCycles(uint64_t cycles) noexcept"
    idx = text.index(anchor)
    brace = text.index("{", idx) + 1
    insert = """
            // 0073: IOP throughput probe. Hardware runs 36.864 MHz; if the interpreter executes far less than
            // that per wall second, IOP-side code (such as the sound driver's producer) cannot keep up with
            // audio that needs 187.5 blocks of 1024 bytes per second.
            static uint64_t totalCycles = 0u;
            static uint64_t lastLogCycles = 0u;
            static auto lastLog = std::chrono::steady_clock::now();
            totalCycles += cycles;
            {
                const auto now = std::chrono::steady_clock::now();
                const double elapsed =
                    std::chrono::duration_cast<std::chrono::duration<double>>(now - lastLog).count();
                if (elapsed >= 2.0)
                {
                    const double mhz =
                        static_cast<double>(totalCycles - lastLogCycles) / elapsed / 1'000'000.0;
                    std::fprintf(stderr, "[iop:rate] %.2f MHz (hardware 36.86) total=%llu\\n", mhz,
                                 static_cast<unsigned long long>(totalCycles));
                    lastLogCycles = totalCycles;
                    lastLog = now;
                }
            }"""
    text = text[:brace] + insert + text[brace:]
    if "#include <chrono>" not in text:
        text = text.replace("#include <cstdio>", "#include <chrono>\n#include <cstdio>", 1)
    if "#include <cstdio>" not in text:
        text = "#include <chrono>\n#include <cstdio>\n" + text
    open(EMU, "w", encoding="utf-8", newline="\r\n").write(text)
    print("iop_emulator probe added")

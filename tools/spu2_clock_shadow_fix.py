#!/usr/bin/env python3
"""0082: remove the shadowing clock introduced by the 0073 throughput probe.

`runCycles` declared `static uint64_t totalCycles`, shadowing the Impl member of the same name. From build 87 on, the
scheduling loop, timrman.serviceDue, vblank.serviceDue and nextWakeCycle all read that probe clock, while
`step()` and the DMA due times used the real member - two clocks disagreeing. The visible symptom is the auto-DMA arm
rate collapsing from ~191/s (build 86) to ~11-89 per run, plus completions that never come due again.

The probe keeps its own clearly-named accumulator; the scheduler goes back to the member clock.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "probeCycles" in text:
    print("already fixed")
    sys.exit(0)


def once(old, new, label):
    global text
    n = text.count(old)
    if n != 1:
        print(f"FAIL {label}: matched {n} times")
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f"ok   {label}")


once("            static uint64_t totalCycles = 0u;\n            static uint64_t lastLogCycles = 0u;",
     "            static uint64_t probeCycles = 0u;\n            static uint64_t lastLogCycles = 0u;",
     "probe accumulator")

once("            totalCycles += cycles;\n            {",
     "            probeCycles += cycles;\n            {",
     "probe increment")

once("                        static_cast<double>(totalCycles - lastLogCycles) / elapsed / 1'000'000.0;",
     "                        static_cast<double>(probeCycles - lastLogCycles) / elapsed / 1'000'000.0;",
     "probe rate")

once("                                 static_cast<unsigned long long>(totalCycles));",
     "                                 static_cast<unsigned long long>(probeCycles));",
     "probe print")

once("                    lastLogCycles = totalCycles;",
     "                    lastLogCycles = probeCycles;",
     "probe baseline")

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("clock shadow removed")

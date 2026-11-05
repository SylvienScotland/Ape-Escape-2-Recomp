#!/usr/bin/env python3
"""0081 fix (part 2): the emulator accounting block was written with a literal newline inside its format string
(same shell-escaping mistake as the event-flag block), so iop_emulator.cpp fails with C2001 at line 546.
Locate the inserted span by anchors and rewrite it."""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

start_marker = "                    // 0081: exact accounting for the SPU2 completion vector"
end_marker = "                    if (delivered)\n                    {"

start = text.find(start_marker)
if start < 0:
    print("nothing to fix (marker absent)")
    sys.exit(0)
end = text.find(end_marker, start)
if end < 0:
    print("FAIL: end anchor missing")
    sys.exit(1)
end += len(end_marker)

replacement = (
    "                    // 0081: exact accounting for the SPU2 completion vector; the perf report only samples.\n"
    "                    const bool delivered = intrman.dispatchInterrupt(irq, *this);\n"
    "                    if (irq == 40)\n"
    "                    {\n"
    "                        static unsigned attempts = 0u;\n"
    "                        static unsigned deliveries = 0u;\n"
    "                        ++attempts;\n"
    "                        if (delivered)\n"
    "                            ++deliveries;\n"
    "                        if (attempts <= 5u || attempts % 100u == 0u)\n"
    "                            std::fprintf(stderr, \"[spu2:auto] attempts=%u deliveries=%u enabled=%d handler=%d\\n\",\n"
    "                                         attempts, deliveries, intrman.isEnabled(irq) ? 1 : 0,\n"
    "                                         intrman.hasHandler(irq) ? 1 : 0);\n"
    "                    }\n"
    "                    if (delivered)\n"
    "                    {"
)

text = text[:start] + replacement + text[end:]
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("repaired emulator accounting block")

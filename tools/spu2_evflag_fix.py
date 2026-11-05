#!/usr/bin/env python3
"""0081 fix: the event-flag log block was written with a literal newline inside its format string, so the build
failed with C2001 in iop_kernel.cpp. Replace the whole inserted span with correct code, located by anchors rather
than by exact text, so the malformed version does not need to be reproduced."""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_kernel.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

start_marker = "        // 0081: report sets of the bit the parked sound thread waits on"
end_marker = "        event->second.bits |= bits;"

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
    "        // 0081: report sets of the bit the parked sound thread waits on (event flag 1, bit 0x2000).\n"
    "        if ((bits & 0x2000u) != 0u)\n"
    "        {\n"
    "            static unsigned reports = 0u;\n"
    "            if (++reports <= 10u)\n"
    "                std::fprintf(stderr, \"[evflag] set id=%d +0x%x -> 0x%x\\n\", id, bits,\n"
    "                             event->second.bits | bits);\n"
    "        }\n"
    "        event->second.bits |= bits;"
)

text = text[:start] + replacement + text[end:]
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("repaired evflag block")

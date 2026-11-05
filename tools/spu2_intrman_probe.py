#!/usr/bin/env python3
"""0078: log which interrupt vectors the guest registers.

`IopIntrman::dispatchInterrupt` requires the vector to be in `m_handlers` and enabled in `m_enabled`; raising 0x28
(the number this HLE picked for SPU2 core1 DMA) delivers nothing if the sound driver registered another vector - the
`[perf:iop] irq 40: calls 2` against `irq 17: calls 44` mismatch. This prints every RegisterIntrHandler so the vector
the driver actually uses for SPU2 block completion can be read off instead of guessed.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\imports\iop_intrman.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "[intrman] register" in text:
    print("already instrumented")
    sys.exit(0)

old = """        case 4: // RegisterIntrHandler
            m_handlers[static_cast<int>(a0)] = {a2, a3, cpu.gpr[28]};"""
new = """        case 4: // RegisterIntrHandler
            // 0078: report the vector, so SPU2 completion can be raised on the one the driver really installed.
            std::fprintf(stderr, "[intrman] register vector=%d handler=0x%08x arg=0x%08x\\n", static_cast<int>(a0),
                         a2, a3);
            m_handlers[static_cast<int>(a0)] = {a2, a3, cpu.gpr[28]};"""
if text.count(old) != 1:
    raise SystemExit(f"ERROR: anchor matched {text.count(old)} times")
text = text.replace(old, new, 1)

if "#include <cstdio>" not in text:
    text = text.replace('#include "iop_intrman.h"', '#include "iop_intrman.h"\n\n#include <cstdio>', 1)

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("intrman probe added")

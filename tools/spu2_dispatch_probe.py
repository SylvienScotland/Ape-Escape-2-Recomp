#!/usr/bin/env python3
"""0080: why does dispatchInterrupt(40) return false when the re-arm is healthy?

The re-arm query for irq 40 reports active=1 with a 196608-cycle period, and yet `irq 40: calls` stays at 2.
`IopIntrman::dispatchInterrupt` refuses only when the vector is not enabled or has no handler, so this prints those
two facts at the moment of each attempt, plus every ReleaseIntrHandler call.
"""
import sys

HDR = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\imports\iop_intrman.h"
CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\imports\iop_intrman.cpp"
EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"


def read(p):
    return open(p, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def write(p, t):
    open(p, "w", encoding="utf-8", newline="\r\n").write(t)


def once(text, old, new, label, path):
    n = text.count(old)
    if n != 1:
        print(f"FAIL {label}: matched {n} times")
        sys.exit(1)
    write(path, text.replace(old, new, 1))
    print(f"ok   {label}")
    return text.replace(old, new, 1)


hdr = read(HDR)
if "isEnabled(int irq)" not in hdr:
    hdr = once(hdr,
               "        [[nodiscard]] bool dispatchInterrupt(int irq, IopGuestExecutor &executor) const;",
               "        [[nodiscard]] bool dispatchInterrupt(int irq, IopGuestExecutor &executor) const;\n"
               "        // 0080: state probes, so a refused dispatch can say why it was refused.\n"
               "        [[nodiscard]] bool isEnabled(int irq) const\n"
               "        {\n"
               "            const auto it = m_enabled.find(irq);\n"
               "            return it != m_enabled.end() && it->second;\n"
               "        }\n"
               "        [[nodiscard]] bool hasHandler(int irq) const { return m_handlers.find(irq) != m_handlers.end(); }",
               "header probes", HDR)

cpp = read(CPP)
if "release vector" not in cpp:
    cpp = once(cpp,
               "        case 5: // ReleaseIntrHandler\n            m_handlers.erase(static_cast<int>(a0));",
               "        case 5: // ReleaseIntrHandler\n"
               "            std::fprintf(stderr, \"[intrman] release vector=%d\\n\", static_cast<int>(a0));\n"
               "            m_handlers.erase(static_cast<int>(a0));",
               "release log", CPP)

emu = read(EMU)
if "dispatch attempt irq=40" not in emu:
    emu = once(emu,
               "                    const uint64_t before = totalInstructions;\n",
               "                    const uint64_t before = totalInstructions;\n"
               "                    // 0080: dispatch witnesses for the SPU2 completion vector.\n"
               "                    if (irq == 40)\n"
               "                    {\n"
               "                        static unsigned seen = 0u;\n"
               "                        if (++seen <= 5u || seen % 200u == 0u)\n"
               "                            std::fprintf(stderr,\n"
               "                                         \"[spu2:auto] dispatch attempt irq=40 enabled=%d handler=%d \"\n"
               "                                         \"(n=%u)\\n\",\n"
               "                                         intrman.isEnabled(irq) ? 1 : 0,\n"
               "                                         intrman.hasHandler(irq) ? 1 : 0, seen);\n"
               "                    }\n",
               "dispatch probe", EMU)
print("done")

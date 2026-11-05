#!/usr/bin/env python3
"""0078b: log EnableIntr / DisableIntr.

dispatchInterrupt() needs BOTH a registered handler and m_enabled[irq]. Vector 40 is registered with handler
0x441f0, yet only 2 of 89 armed blocks were ever delivered, which is the shape of a vector that was never enabled
(or was disabled early). This prints the enable/disable traffic so it can be read rather than assumed.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\imports\iop_intrman.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "[intrman] enable" in text:
    print("already instrumented")
    sys.exit(0)


def once(old, new, label):
    global text
    n = text.count(old)
    if n != 1:
        print(f"FAIL {label}: matched {n} times")
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f"ok   {label}")


once("""        case 6: // EnableIntr
            m_enabled[static_cast<int>(a0)] = true;""",
     """        case 6: // EnableIntr
            // 0078b: which vectors the driver actually enables decides whether a raised irq is delivered at all.
            std::fprintf(stderr, "[intrman] enable vector=%d\\n", static_cast<int>(a0));
            m_enabled[static_cast<int>(a0)] = true;""",
     "enable log")

once("""        case 7: // DisableIntr
            if (a1 != 0u)""",
     """        case 7: // DisableIntr
            std::fprintf(stderr, "[intrman] disable vector=%d\\n", static_cast<int>(a0));
            if (a1 != 0u)""",
     "disable log")

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("instrumented")

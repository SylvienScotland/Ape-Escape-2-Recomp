#!/usr/bin/env python3
"""0077d: instrument the autonomous auto-DMA timer.

Build 94 keeps the block interrupt scheduled while armed, but IRQ 0x28 still fired only twice in a 60 s run, so
either the timer is deactivated (ADMAS write / reset), never armed, or the re-arm query is never reached. These
three prints decide which, and none of them change behaviour.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "[spu2:auto]" in text:
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


once("""            m_admaTimer.delayCycles = delayCycles;
        }""",
     """            m_admaTimer.delayCycles = delayCycles;
            std::fprintf(stderr, "[spu2:auto] armed irq=%d block=%llu cycles (%.2f ms)\\n",
                         m_admaTimer.irq, static_cast<unsigned long long>(delayCycles),
                         static_cast<double>(delayCycles) / 36864.0);
        }""",
     "armed log")

once("""            (value & 0x3u) == 0u)
            m_admaTimer.active = false;""",
     """            (value & 0x3u) == 0u)
        {
            if (m_admaTimer.active)
                std::fprintf(stderr, "[spu2:auto] stopped by ADMAS write 0x%x\\n", value);
            m_admaTimer.active = false;
        }""",
     "stopped log")

once("""        if (!m_admaTimer.active || m_admaTimer.irq != irq || m_admaTimer.delayCycles == 0u)
            return std::nullopt;
        return m_admaTimer.delayCycles;""",
     """        static unsigned calls = 0u;
        ++calls;
        if (calls <= 3u || calls % 400u == 0u)
            std::fprintf(stderr, "[spu2:auto] rearm query #%u irq=%d active=%d timerIrq=%d delay=%llu\\n", calls, irq,
                         m_admaTimer.active ? 1 : 0, m_admaTimer.irq,
                         static_cast<unsigned long long>(m_admaTimer.delayCycles));
        if (!m_admaTimer.active || m_admaTimer.irq != irq || m_admaTimer.delayCycles == 0u)
            return std::nullopt;
        return m_admaTimer.delayCycles;""",
     "query log")

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("instrumented")

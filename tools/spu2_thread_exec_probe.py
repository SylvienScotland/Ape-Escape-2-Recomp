#!/usr/bin/env python3
"""0089: per-thread execution counter + event-flag wake log.

Two questions, one probe set:
  1. When the sound thread's event flag is signalled, does the waiter actually become Ready? (log in wakeEventWaiters)
  2. Does that thread ever get scheduled afterwards? (per-thread execution counts printed with the IOP rate line)

If the wake happens but the execution count never rises, the fault is in the scheduler; if the count does rise, the
driver runs and the missing voice programming is inside guest code.
"""
import sys

KERNEL = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_kernel.cpp"
EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"


def patch(path, edits):
    text = open(path, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")
    for anchor, insert in edits:
        if insert.strip() in text:
            continue
        count = text.count(anchor)
        if count != 1:
            print(f"FAIL: anchor matched {count} times in {path}: {anchor.strip()[:60]}")
            sys.exit(1)
        text = text.replace(anchor, anchor + insert, 1)
    open(path, "w", encoding="utf-8", newline="\r\n").write(text)
    print(f"patched {path}")


patch(
    KERNEL,
    [
        (
            """            if ((thread.waitMode & 0x10u) != 0u)
                event.bits = 0u;
            thread.state = IopThreadState::Ready;
""",
            """            // 0089: prove the waiter really becomes runnable when the flag it waits on is signalled.
            {
                static unsigned wakes = 0u;
                if (++wakes <= 20u)
                    std::fprintf(stderr, "[iop:wake] thread=%d from event flag %d bits=0x%x\\n", thread.id,
                                 event.id, event.bits);
            }
""",
        )
    ],
)

patch(
    EMU,
    [
        (
            """            static uint64_t probeCycles = 0u;
""",
            """            // 0089: how many times each thread is actually scheduled, to tell "driver never runs" apart from
            // "driver runs but programs nothing".
            static std::map<int, unsigned long long> execCounts;
""",
        ),
        (
            """                    std::fprintf(stderr, "[iop:rate] %.2f MHz (hardware 36.86) total=%llu\\n", mhz,
                                 static_cast<unsigned long long>(probeCycles));
""",
            """                    std::fprintf(stderr, "[iop:exec]");
                    for (const auto &[id, count] : execCounts)
                        std::fprintf(stderr, " t%d=%llu", id, count);
                    std::fprintf(stderr, "\\n");
""",
        ),
        (
            """                    runCpu(next->cpu, static_cast<uint32_t>(std::min<uint64_t>(kDefaultSlice, target - totalCycles)));
""",
            """                    ++execCounts[next->id];
""",
        ),
    ],
)
print("thread probes installed")

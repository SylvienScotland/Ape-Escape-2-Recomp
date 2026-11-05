#!/usr/bin/env python3
"""0091: where does thread 1 (the sound driver) actually spend its time?

Counters proved the thread is scheduled constantly and programmes no SPU2 register. A PC histogram of that thread's
slice-end addresses shows whether it is blocked in a spin/wait loop and where, which is more informative than another
event count. Implemented as a cumulative histogram printed alongside the IOP rate line.
"""
import sys

EMU = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\iop_emulator.cpp"
text = open(EMU, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

edits = [
    (
        """            static std::map<int, unsigned long long> execCounts;
""",
        """            static std::map<int, unsigned long long> execCounts;
            // 0091: slice-end PCs for the sound driver thread, so a spin loop is visible directly.
            static std::map<uint32_t, unsigned long long> driverPcHist;
""",
    ),
    (
        """                    std::fprintf(stderr, "\\n");
""",
        """                    std::fprintf(stderr, "\\n");
                    {
                        std::vector<std::pair<unsigned long long, uint32_t>> hot;
                        hot.reserve(driverPcHist.size());
                        for (const auto &[pc, count] : driverPcHist)
                            hot.emplace_back(count, pc);
                        std::partial_sort(hot.begin(), hot.begin() + std::min<size_t>(hot.size(), 8u), hot.end(),
                                          [](const auto &a, const auto &b) { return a.first > b.first; });
                        std::fprintf(stderr, "[iop:hot]");
                        for (size_t i = 0; i < hot.size() && i < 8u; ++i)
                            std::fprintf(stderr, " 0x%08x=%llu", hot[i].second, hot[i].first);
                        std::fprintf(stderr, "\\n");
                    }
""",
    ),
    (
        """                    ++execCounts[next->id];
""",
        """                    ++execCounts[next->id];
                    if (next->id == 1)
                        ++driverPcHist[next->cpu.pc];
""",
    ),
]

for anchor, insert in edits:
    if insert.strip() in text:
        continue
    count = text.count(anchor)
    if count != 1:
        print(f"FAIL: anchor matched {count} times: {anchor.strip()[:50]}")
        sys.exit(1)
    text = text.replace(anchor, anchor + insert, 1)

if "#include <algorithm>" not in text:
    anchor = '#include "iop_emulator.h"'
    if text.count(anchor) != 1:
        print("FAIL: include anchor")
        sys.exit(1)
    text = text.replace(anchor, anchor + "\n#include <algorithm>\n#include <vector>\n", 1)

open(EMU, "w", encoding="utf-8", newline="\r\n").write(text)
print("PC histogram installed")

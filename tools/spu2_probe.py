#!/usr/bin/env python3
"""0075: log what the SPU2 output path actually delivers.

Compiling and starting the game does not prove audio reaches the device. This prints one line every ~2 s from
the host-side push, which turns "the code is wired" into a measured frame rate: at 48 kHz it should sit near
96,000 frames per 2 s, and zero would mean the pull is finding no armed stream.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_audio.cpp"

text = open(CPP, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")
if "spu2:out" in text:
    print("already patched")
    sys.exit(0)

anchor = """    std::lock_guard<std::mutex> lock(m_mutex);
    auto &impl = *m_impl;

    if (!impl.streamReady)"""
n = text.count(anchor)
if n != 1:
    raise SystemExit(f"ERROR: anchor matched {n} times")

probe = """    std::lock_guard<std::mutex> lock(m_mutex);
    auto &impl = *m_impl;

    // 0075: measured delivery, not assumed. ~96,000 frames per 2 s at 48 kHz means the stream is running.
    {
        static size_t probeFrames = 0u;
        static std::chrono::steady_clock::time_point probeLast = std::chrono::steady_clock::now();
        probeFrames += frames;
        const auto now = std::chrono::steady_clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - probeLast).count();
        if (elapsed >= 2000)
        {
            std::fprintf(stderr, "[spu2:out] frames=%zu in %lldms (%.0f frames/s) queued=%zu\\n",
                         probeFrames, static_cast<long long>(elapsed),
                         probeFrames * 1000.0 / static_cast<double>(elapsed),
                         impl.ringCount);
            probeFrames = 0u;
            probeLast = now;
        }
    }

    if (!impl.streamReady)"""

text = text.replace(anchor, probe, 1)

# needs <chrono> and <cstdio> for the probe
if "#include <chrono>" not in text:
    text = text.replace("#include <cstring>", "#include <chrono>\n#include <cstdio>\n#include <cstring>", 1)

open(CPP, "w", encoding="utf-8", newline="\r\n").write(text)
print("probe added")

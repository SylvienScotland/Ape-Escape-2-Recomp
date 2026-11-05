#!/usr/bin/env python3
"""Present the frame latched one vsync ago, so a half-drawn frame is never shown.

Evidence this targets: the flicker survives the software renderer, so it is not in the GL backend - it is in code
shared by both, and the presentation path is shared. `UploadFrame` latches the display buffer on whatever tick the
host loop observes and uploads it immediately; if the game has already begun drawing the next frame into that same
buffer, the presented pixels are a mix of two frames. This file already documents that failure mode: the display
heuristics were removed because presenting the back buffer "while the game was still drawing the next frame into it"
made the picture flicker (patch 0028).

Keeping one frame of latency makes that impossible: the pixels uploaded now were fully latched on the previous tick.
APE2_PRESENT_DELAY=0 restores the immediate presentation for A/B.

NOTE: this file is CRLF. Read with universal newlines and write back with CRLF, or the anchors never match.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_runtime.cpp"
with open(PATH, "r", encoding="utf-8", newline=None) as f:
    src = f.read()

orig = src

old = """    static std::vector<uint8_t> s_scratch;
    static std::vector<uint8_t> s_uploadBuffer(DEFAULT_FB_SIZE, 0u);"""
assert src.count(old) == 1, ("upload statics", src.count(old))
src = src.replace(
    old,
    old + """
    static std::vector<uint8_t> s_prevBuffer(DEFAULT_FB_SIZE, 0u);
    static bool s_hasPrevFrame = false;
    static uint32_t s_prevWidth = 0u, s_prevHeight = 0u;
    // one frame of latency: a latched frame is only shown after a further vsync has completed it, so the
    // presented pixels can never be a mix of the frame being drawn and the one before it
    static const bool s_delayPresent = []() {
        const char *e = std::getenv("APE2_PRESENT_DELAY");
        return !(e && e[0] == '0');
    }();""",
)

old = """    UpdateTexture(tex, s_uploadBuffer.data());
    outWidth = width;
    outHeight = height;
    s_hasUploadedFrame = true;
}"""
assert src.count(old) == 1, ("upload tail", src.count(old))
src = src.replace(
    old,
    """    if (s_delayPresent && s_hasPrevFrame)
    {
        UpdateTexture(tex, s_prevBuffer.data());
        outWidth = s_prevWidth;
        outHeight = s_prevHeight;
    }
    else
    {
        UpdateTexture(tex, s_uploadBuffer.data());
        outWidth = width;
        outHeight = height;
    }
    // whatever was just latched becomes the frame presented on the next tick
    s_uploadBuffer.swap(s_prevBuffer);
    s_prevWidth = width;
    s_prevHeight = height;
    s_hasPrevFrame = true;
    s_lastWidth = outWidth;
    s_lastHeight = outHeight;
    s_hasUploadedFrame = true;
}""",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "ps2_runtime.cpp.predelay")
shutil.copyfile(PATH, bak)
with open(PATH, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(src)
print("patched; backup at", bak)
print("delayPresent refs:", src.count("s_delayPresent"), "| prevBuffer refs:", src.count("s_prevBuffer"))

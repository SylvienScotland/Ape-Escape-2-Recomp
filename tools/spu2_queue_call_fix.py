#!/usr/bin/env python3
"""0074 fix: the push call landed at namespace scope because spu2RingRefresh's diagnostic `if` has no braces.
Move it next to the arm accounting, inside the function."""
PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

bad = """
            // 0074: the armed block is the next piece of the stream; queue it for one-shot playback.
            spu2QueuePush(ram, address, sizeBytes);
"""
if bad in text:
    text = text.replace(bad, "", 1)

anchor = """                ++ring.arms;
                ++ring.armsThisLap;
"""
if text.count(anchor) != 1:
    raise SystemExit(f"ERROR: arm anchor matched {text.count(anchor)} times")
text = text.replace(anchor, anchor + """                // 0074: the armed block is the next piece of the stream; queue it for one-shot playback.
                spu2QueuePush(ram, address, sizeBytes);
""", 1)

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("push moved inside spu2RingRefresh")

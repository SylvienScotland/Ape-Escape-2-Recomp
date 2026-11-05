#!/usr/bin/env python3
"""Make one F9 capture answer everything: uncap the denial log, and tag every keyboard draw with
its frame epoch so draws can be grouped into frames offline (the existing epoch field is the
texture decode epoch - vastly larger numbers - and is a different thing).

The 40-line cap hid whether keyboards were affected at all: the logged drops were all one atlas
simply because that atlas was drawn first.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

old_cap = "if (logged < 40)"
assert src.count(old_cap) == 1, "cap anchor"
src = src.replace(old_cap, "if (logged < 4000)")

old_fmt = "mixed=%d clutv=%u epoch=%llu"
assert src.count(old_fmt) == 1, "kb format anchor"
src = src.replace(old_fmt, "mixed=%d clutv=%u epoch=%llu fepoch=%llu")

old_args = "static_cast<unsigned long long>(epoch));"
assert src.count(old_args) == 1, ("kb args anchor", src.count(old_args))
src = src.replace(
    old_args,
    "static_cast<unsigned long long>(epoch),\n"
    "                             static_cast<unsigned long long>(m_frameEpoch.load(std::memory_order_relaxed)));",
    )

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.supv3")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; backup of v3 at", bak)
print("lines now:", src.count("\n") + 1)

#!/usr/bin/env python3
"""Turn mipmapping back off by default.

Mipmapping did not fix the keyboard flicker, and it breaks alpha-tested geometry: averaging a
texture's alpha across a chain drops thin foliage below the alpha test, so the green landscape in
the opening disappears. It stays in the tree as an experiment, enabled only by APE2_GS_MIPMAP=1.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

old = """        static const bool v = []() {
            const char *e = std::getenv("APE2_GS_MIPMAP");
            return !(e && e[0] == '0');
        }();"""
assert src.count(old) == 1, "switch"
src = src.replace(
    old,
    """        // opt-in only: this did not fix the keyboard flicker, and mip levels average alpha across
        // the chain, which drops alpha-tested foliage below the threshold and makes it disappear
        static const bool v = []() {
            const char *e = std::getenv("APE2_GS_MIPMAP");
            return e && e[0] == '1';
        }();""",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.mipoptin")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; backup at", bak)

#!/usr/bin/env python3
"""Gate the mipmap min filter on the texture actually having a chain.

Build 67 proved the chain itself is fine: `[gpu] mip chain built for a 512x512 texture`, glGetError
clean. It was still black because `s.tex` has three possible sources and only one gets a chain:

  - `cpuTexture()`  - decoded texture, chain regenerated on every upload  -> has mips
  - `texTarget()`   - the texture *is* a render target, sampled directly   -> no mips
  - `m_snapTex`     - a blitted snapshot of the target being drawn into    -> no mips

The render-target cases set `s.texRt = 1` (stateFrom copies it from the caller, and the snapshot
path reaches there via `tex == rt->tex`), so `!s.texRt` selects exactly the textures that can be
minified from a chain. Sampling a target texture with a mipmap filter is an incomplete texture,
which is black - the entire hub is drawn through render-to-texture, hence a fully black screen.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

old = "const GLint fmin = mipState() ? (s.bilinear ? GL_LINEAR_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST) : f;"
assert src.count(old) == 1, "filter site"
src = src.replace(
    old,
    "// only decoded textures carry a mip chain; a render target or snapshot sampled with a mipmap\n"
    "            // filter is an incomplete texture and draws black (build 66: every frame mean 0.0)\n"
    "            const GLint fmin = (mipState() && !s.texRt) ? (s.bilinear ? GL_LINEAR_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST) : f;",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.mipgate")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; backup at", bak)

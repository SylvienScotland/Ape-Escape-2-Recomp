#!/usr/bin/env python3
"""0056: replace the drop-the-draw suppression with 'deny the equal-depth tie'.

v2 dropped the blended draw entirely, which (a) never matched the keyboards because the two copies
list their z values in different order and the key was order-sensitive, and (b) threw geometry away.
v3 keeps every draw and only changes the depth function for a blended coplanar twin, so it cannot
overwrite the opaque copy at equal depth while geometry genuinely in front still draws.
"""
import os
import shutil
import sys
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
NL = chr(92) + "n"

src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src
lines = src.split("\n")

start = next(i for i, l in enumerate(lines) if "// 0055 A/B v2" in l)
end = next(i for i, l in enumerate(lines) if "// target and depth" in l)
assert end > start

block = [
    "        // 0056: a blended pass that re-draws geometry the opaque pass already drew, at the same bbox and the",
    "        // same three depths, ties with it in the depth buffer. With ZTST=2/GEQUAL the later blended submission",
    "        // wins every tie, and at distance sub-pixel rounding decides which copy covers each fragment: that is",
    "        // the keyboard flicker. Measured (LOG 0055/0056): equal draw counts per frame, identical bbox, identical",
    "        // z, and the pair sits tens of primitives apart. So match across the frame, and compare z as a multiset -",
    "        // the two copies do not list their vertices in the same order. The draw is kept; it is only denied the",
    "        // equal-depth tie below, so geometry genuinely in front of it still draws.",
    '        static const char *szEnv = std::getenv("APE2_KB_STRICTZ");',
    "        static const bool strictZ = szEnv && szEnv[0] != '0';",
    "        bool dupTie = false;",
    "        {",
    "            static thread_local std::unordered_set<uint64_t> seenOpaque;",
    "            static thread_local uint64_t seenEpoch = ~0ull;",
    "            const uint64_t epoch = m_frameEpoch.load(std::memory_order_relaxed);",
    "            if (epoch != seenEpoch)",
    "            {",
    "                seenOpaque.clear();",
    "                seenEpoch = epoch;",
    "            }",
    "            const GSVertex *sv = batch.vertices.data();",
    "            const bool blended = st.prim.abe != 0;",
    "            double zs[3] = {sv[0].z, sv[1].z, sv[2].z};",
    "            std::sort(zs, zs + 3);",
    "            uint64_t h = 1469598103934665603ull;",
    "            auto mix64 = [&h](uint64_t v) {",
    "                h ^= v;",
    "                h *= 1099511628211ull;",
    "                h ^= h >> 31;",
    "            };",
    "            mix64(static_cast<uint64_t>(static_cast<uint32_t>(bx0)) |",
    "                  (static_cast<uint64_t>(static_cast<uint32_t>(by0)) << 16) |",
    "                  (static_cast<uint64_t>(static_cast<uint32_t>(bx1)) << 32) |",
    "                  (static_cast<uint64_t>(static_cast<uint32_t>(by1)) << 48));",
    "            for (int zi = 0; zi < 3; ++zi)",
    "            {",
    "                uint64_t zb64 = 0;",
    "                std::memcpy(&zb64, &zs[zi], sizeof(zb64));",
    "                mix64(zb64);",
    "            }",
    "            if (!blended)",
    "                seenOpaque.insert(h);",
    "            else if (seenOpaque.find(h) != seenOpaque.end())",
    "            {",
    "                dupTie = true;",
    "                if (strictZ)",
    "                {",
    "                    extern std::atomic<int> g_ape2FrameDumpBurst;",
    "                    if (g_ape2FrameDumpBurst.load(std::memory_order_relaxed) > 0)",
    "                    {",
    "                        static thread_local int logged = 0;",
    "                        if (logged < 40)",
    "                        {",
    '                            std::fprintf(stderr, "[gpu:kbdup] coplanar blended copy denied the depth tie bbox %d,%d-%d,%d z %.0f tbp0=0x%x psm=0x%x' + NL + '",',
    "                                         bx0, by0, bx1, by1, zs[0], c.tex0.tbp0, c.tex0.psm);",
    "                            ++logged;",
    "                        }",
    "                    }",
    "                }",
    "            }",
    "        }",
    "",
]
lines[start:end] = block
src = "\n".join(lines)

anchor = "        stateFrom(st, s, rt, zb, tex, texRt);\n"
assert src.count(anchor) == 1, "stateFrom call site"
src = src.replace(
    anchor,
    anchor
    + "        if (dupTie && strictZ && s.depthTest)\n"
    + "            s.depthFunc = static_cast<int>(GL_GREATER); // 0056: a coplanar twin must not overwrite at equal depth\n",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.supv2")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; backup of v2 at", bak)
print("lines now:", src.count("\n") + 1)

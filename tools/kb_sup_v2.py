#!/usr/bin/env python3
"""Rewrite the APE2_KB_SUPPRESS probe from adjacency-matched (never fired) to frame-scoped.

v1 required the opaque twin to be the immediately preceding primitive; the measurement in
tools/kb_adj.py shows the pair sits tens of primitives apart, so v1 matched nothing. v2 remembers
every opaque quad submitted in the current frame (Present() bumps the epoch) and drops a blended
draw whose bbox and exact z triple match one of them.
"""
import os
import shutil
import sys
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
NL = chr(92) + "n"  # C escape for newline, built without a literal backslash-n in this source

src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

# ---------------------------------------------------------------- A. include
old_inc = "#include <unordered_map>\n"
assert src.count(old_inc) == 1, "include anchor"
src = src.replace(old_inc, old_inc + "#include <unordered_set>\n")

# ---------------------------------------------------------------- B. frame epoch member
old_mem = "    std::thread::id m_glThread{};\n"
assert src.count(old_mem) == 1, "member anchor"
src = src.replace(
    old_mem,
    old_mem
    + "    std::atomic<uint64_t> m_frameEpoch{0}; // 0055 A/B: bumped in Present(); scopes the duplicate cache to one frame\n",
)

# ---------------------------------------------------------------- C. Present bump
old_present = (
    "    PresentationFrame Present(const GSPresentationRequest &request) override "
    "{ return m_cpu->Present(request); }\n"
)
assert src.count(old_present) == 1, "Present anchor"
new_present = (
    "    PresentationFrame Present(const GSPresentationRequest &request) override\n"
    "    {\n"
    "        m_frameEpoch.fetch_add(1, std::memory_order_relaxed); // 0055 A/B: frame boundary for the dup cache\n"
    "        return m_cpu->Present(request);\n"
    "    }\n"
)
src = src.replace(old_present, new_present)

# ---------------------------------------------------------------- D. replace the v1 block
lines = src.split("\n")
start = next(i for i, l in enumerate(lines) if "// 0055 A/B: APE2_KB_SUPPRESS" in l)
lastline = next(i for i, l in enumerate(lines) if "last = LastQuad{" in l)
end = lastline + 1
assert lines[end].strip() == "}", (end, lines[end])

block = [
    "        // 0055 A/B v2: APE2_KB_SUPPRESS=1 drops a blended draw whose bbox and exact z triple match an opaque",
    "        // draw already submitted earlier in the SAME frame. v1 (adjacency-matched) never fired: tools/kb_adj.py",
    "        // shows the pair sits tens of primitives apart, i.e. an opaque pass then a blended pass over the same",
    "        // geometry. Measured signature (LOG 0055): first opaque (test 0x50000, abe 0), later blended (test 0x5b000,",
    "        // abe 1). With ZTST=GEQUAL the blended copy wins the equal-depth tie, so that is the one dropped here.",
    "        {",
    '            static const char *supEnv = std::getenv("APE2_KB_SUPPRESS");',
    "            static const bool suppress = supEnv && supEnv[0] != '0';",
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
    "            const double zs[3] = {sv[0].z, sv[1].z, sv[2].z};",
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
    "                uint64_t zb = 0;",
    "                std::memcpy(&zb, &zs[zi], sizeof(zb));",
    "                mix64(zb);",
    "            }",
    "            if (!blended)",
    "                seenOpaque.insert(h);",
    "            else if (seenOpaque.find(h) != seenOpaque.end())",
    "            {",
    "                if (suppress)",
    "                {",
    "                    extern std::atomic<int> g_ape2FrameDumpBurst;",
    "                    if (g_ape2FrameDumpBurst.load(std::memory_order_relaxed) > 0)",
    "                    {",
    "                        static thread_local int logged = 0;",
    "                        if (logged < 40)",
    "                        {",
    '                            std::fprintf(stderr, "[gpu:kbsup] dropped blended dup bbox %d,%d-%d,%d z %.0f tbp0=0x%x psm=0x%x"',
    "                                         " + NL + '"' + ",",
    "                                         bx0, by0, bx1, by1, sv[0].z, c.tex0.tbp0, c.tex0.psm);",
    "                            ++logged;",
    "                        }",
    "                    }",
    "                    return;",
    "                }",
    "            }",
    "        }",
]
lines[start:end + 1] = block
src = "\n".join(lines)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.supv1")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched", PATH)
print("backup of v1 at", bak)
print("lines now:", src.count("\n") + 1)

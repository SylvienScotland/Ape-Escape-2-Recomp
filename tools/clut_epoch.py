#!/usr/bin/env python3
"""Reload the CLUT when the VRAM page holding it changes, not only when its pointer changes.

The bug: LoadClut() returns early when cbp is unchanged (gs_cpu_backend.cpp, cases cld=4/5), so a palette rewritten
in place at the same address never takes effect. That is exactly how streamed atlas palettes and colour cycling work,
and because the decoded-texture cache is keyed on the palette contents (m_clutHash), textures get decoded with one
palette and then another as the pointer happens to move and move back - colour flicker on every indexed surface.

The fix: remember the VRAM page epoch at capture time and reload when it has moved. Pages are stamped by writes,
transfers and clears (StampPagesUnlocked), so an in-place palette update is now visible.

Both files are CRLF: read with universal newlines, write back with CRLF.
"""
import os
import shutil
import tempfile

HDR = r"C:\dev\PS2Recomp\ps2xRuntime\include\runtime\gs\gs_cpu_backend.h"
CPP = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\gs\gs_cpu_backend.cpp"


def load(path):
    with open(path, "r", encoding="utf-8", newline=None) as f:
        return f.read()


def save(path, text):
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


hdr = load(HDR)
old = "    std::array<uint32_t, 2> m_clutCbp{};"
assert hdr.count(old) == 1, ("header anchor", hdr.count(old))
hdr = hdr.replace(
    old,
    old + "\n    // VRAM page epoch when this slot's palette was captured: a palette rewritten in place at the same\n"
          "    // cbp must still be reloaded, and the page epoch is what says so\n"
          "    std::array<uint64_t, 2> m_clutPageEpoch{};",
)
save(HDR, hdr)

cpp = load(CPP)
orig = cpp

# reset clears the recorded epochs with the pointers
old = "    m_clutCbp.fill(0u);"
assert cpp.count(old) == 1, ("reset anchor", cpp.count(old))
cpp = cpp.replace(old, old + "\n    m_clutPageEpoch.fill(0u);")

# compute the epoch of the pages the palette lives in, before the decision
old = """    switch (tex0.cld)
    {
    case 0u:
    case 6u:
    case 7u:
        return;"""
assert cpp.count(old) == 1, ("switch anchor", cpp.count(old))
cpp = cpp.replace(
    old,
    """    // a palette is normally rewritten in place at the same cbp, so the pointer alone does not say the contents are
    // still the ones captured - the VRAM page epoch does (0071)
    const uint32_t clutPage0 = VramPageOf(tex0.cpsm, tex0.cbp, 1u, 0u, 0u) & 511u;
    const uint32_t clutPage1 = (clutPage0 + 1u) & 511u;
    const uint64_t clutEpochNow = std::max(m_pageEpoch[clutPage0].load(std::memory_order_relaxed),
                                          m_pageEpoch[clutPage1].load(std::memory_order_relaxed));
    switch (tex0.cld)
    {
    case 0u:
    case 6u:
    case 7u:
        return;""",
)

old = """    case 2u:
        m_clutCbp[0] = tex0.cbp;
        break;
    case 3u:
        m_clutCbp[1] = tex0.cbp;
        break;
    case 4u:
        if (m_clutCbp[0] == tex0.cbp)
            return;
        m_clutCbp[0] = tex0.cbp;
        break;
    case 5u:
        if (m_clutCbp[1] == tex0.cbp)
            return;
        m_clutCbp[1] = tex0.cbp;
        break;"""
assert cpp.count(old) == 1, ("cases anchor", cpp.count(old))
cpp = cpp.replace(
    old,
    """    case 2u:
        m_clutCbp[0] = tex0.cbp;
        m_clutPageEpoch[0] = clutEpochNow;
        break;
    case 3u:
        m_clutCbp[1] = tex0.cbp;
        m_clutPageEpoch[1] = clutEpochNow;
        break;
    case 4u:
        if (m_clutCbp[0] == tex0.cbp && m_clutPageEpoch[0] == clutEpochNow)
            return;
        m_clutCbp[0] = tex0.cbp;
        m_clutPageEpoch[0] = clutEpochNow;
        break;
    case 5u:
        if (m_clutCbp[1] == tex0.cbp && m_clutPageEpoch[1] == clutEpochNow)
            return;
        m_clutCbp[1] = tex0.cbp;
        m_clutPageEpoch[1] = clutEpochNow;
        break;""",
)

assert cpp != orig
bak = os.path.join(tempfile.gettempdir(), "gs_cpu_backend.cpp.preclut")
shutil.copyfile(CPP, bak)
save(CPP, cpp)
print("patched; backup at", bak)
print("clutPageEpoch refs header:", hdr.count("m_clutPageEpoch"), "cpp:", cpp.count("m_clutPageEpoch"))

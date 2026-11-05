#!/usr/bin/env python3
"""Stop the mipmap path from failing open.

Build 66 was fully black (every dumped frame mean 0.0/0.0/0.0) while still drawing ~40k prims, and
APE2_GS_MIPMAP=0 rendered normally. The guard was the bug: it tested `glGenerateMipmap` before
*calling* it, so a texture could end up with MIN_FILTER asking for a mip chain that was never
generated - an incomplete texture, which samples black, for every textured draw in the scene.

Now the decision is made once at init, stored in a state flag, defaulted to off (so a texture can
never be filtered from a chain that does not exist), and generation checks glGetError and turns
itself off on failure rather than rendering black.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

# 1. shared state next to the existing switch
old = """    static bool mipmapsEnabled()
    {
        static const bool v = []() {
            const char *e = std::getenv("APE2_GS_MIPMAP");
            return !(e && e[0] == '0');
        }();
        return v;
    }"""
assert src.count(old) == 1, "mipmapsEnabled"
src = src.replace(
    old,
    old + """
    // resolved at init and only then honoured, so MIN_FILTER can never be pointed at a chain that
    // was not actually built: that combination is an incomplete texture, which samples black
    static bool &mipState()
    {
        static bool v = false;
        return v;
    }""",
)

# 2. decide once, and say so in the log
old = """        if (const char *e = std::getenv("APE2_GS_SCALE"))
            m_scale = std::clamp(std::atoi(e), 1, 8);"""
assert src.count(old) == 1, "scale init"
src = src.replace(
    old,
    old + """
        mipState() = mipmapsEnabled() && glGenerateMipmap != nullptr;
        std::fprintf(stderr, "[gpu] mipmaps %s\\n",
                     mipState() ? "on (minified textured draws use the mip chain)"
                                : "off (generateMipmap unavailable; single-level sampling)");""",
)

# 3. generate with an error check, and switch itself off instead of drawing black
old = """        if (mipmapsEnabled() && glGenerateMipmap)
            glGenerateMipmap(GL_TEXTURE_2D);"""
assert src.count(old) == 1, "generate site"
src = src.replace(
    old,
    """        if (mipState())
        {
            glGenerateMipmap(GL_TEXTURE_2D);
            const GLenum e = glGetError();
            if (e != 0)
            {
                mipState() = false;
                std::fprintf(stderr, "[gpu] glGenerateMipmap failed (0x%x) on a %dx%d texture; back to single-level sampling\\n", e, d->w, d->h);
            }
            else
            {
                static bool told = false;
                if (!told)
                {
                    told = true;
                    std::fprintf(stderr, "[gpu] mip chain built for a %dx%d texture\\n", d->w, d->h);
                }
            }
        }""",
)

# 4. the filter follows the same state, never the raw env switch
old = "const GLint fmin = mipmapsEnabled() ? (s.bilinear ? GL_LINEAR_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST) : f;"
assert src.count(old) == 1, "filter site"
src = src.replace(
    old,
    "const GLint fmin = mipState() ? (s.bilinear ? GL_LINEAR_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST) : f;",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.mipfailsafe")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; backup at", bak)
print("mipState refs:", src.count("mipState()"), "| mipmapsEnabled refs:", src.count("mipmapsEnabled()"))

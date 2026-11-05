#!/usr/bin/env python3
"""Give every decoded GS texture a mip chain and use it for minification.

Why: applyAndDraw used one filter for MIN and MAG and nothing ever called glGenerateMipmap, so a
textured surface drawn small (any third-person view of a distant object) was sampled from level 0
only. That aliases into shimmer/"garbage" that gets cleaner the closer the camera is - and it
affects every texture in the game, not one object, so it is fixed at the upload site.

Controlled by APE2_GS_MIPMAP: unset or non-"0" enables it, "0" restores the old single-level
sampling for an A/B comparison.
"""
import os
import shutil
import tempfile

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\zz_ape2_gs_gl.cpp"
src = open(PATH, "r", encoding="utf-8", newline="").read()
orig = src

# 1. GL constants for the mipmap minification filters
old = "constexpr GLenum GL_NEAREST = 0x2600, GL_LINEAR = 0x2601;"
assert src.count(old) == 1, "filter constants"
src = src.replace(
    old,
    "constexpr GLenum GL_NEAREST = 0x2600, GL_LINEAR = 0x2601;\n"
    "    constexpr GLenum GL_NEAREST_MIPMAP_NEAREST = 0x2700, GL_LINEAR_MIPMAP_LINEAR = 0x2703;",
)

# 2. resolve glGenerateMipmap alongside the other entry points
old = "    X(void, glTexSubImage2D, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))                \\"
assert src.count(old) == 1, "loader list"
src = src.replace(old, old + "\n    X(void, glGenerateMipmap, (GLenum))                                                                                    \\")

# 3. the switch, plus a helper next to texParams
old = """    static void texParams(GLuint t, GLint filter, GLint wrapS, GLint wrapT)"""
assert src.count(old) == 1, "texParams"
src = src.replace(
    old,
    """    // one level of detail is why distant surfaces shimmered: every minified texture was sampled
    // from level 0, so the keys on a far-away keyboard aliased into noise
    static bool mipmapsEnabled()
    {
        static const bool v = []() {
            const char *e = std::getenv("APE2_GS_MIPMAP");
            return !(e && e[0] == '0');
        }();
        return v;
    }
    static void texParams(GLuint t, GLint filter, GLint wrapS, GLint wrapT)""",
)

# 4. build the chain whenever texel content changes (textures are streamed into reused objects,
#    so this has to happen on every upload, not once at creation)
old = """        else
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, d->w, d->h, GL_RGBA, GL_UNSIGNED_BYTE, d->texels.data());
        g.epoch = d->decodeEpoch;"""
assert src.count(old) == 1, "upload site"
src = src.replace(
    old,
    """        else
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, d->w, d->h, GL_RGBA, GL_UNSIGNED_BYTE, d->texels.data());
        if (mipmapsEnabled() && glGenerateMipmap)
            glGenerateMipmap(GL_TEXTURE_2D);
        g.epoch = d->decodeEpoch;""",
)

# 5. use the chain for minification only; magnification must stay nearest/linear as the GS asks
old = """            const GLint f = s.bilinear ? GL_LINEAR : GL_NEAREST;
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, f);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, f);"""
assert src.count(old) == 1, "applyAndDraw filters"
src = src.replace(
    old,
    """            const GLint f = s.bilinear ? GL_LINEAR : GL_NEAREST;
            const GLint fmin = mipmapsEnabled() ? (s.bilinear ? GL_LINEAR_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST) : f;
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, fmin);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, f);""",
)

assert src != orig
bak = os.path.join(tempfile.gettempdir(), "zz_ape2_gs_gl.cpp.premip")
shutil.copyfile(PATH, bak)
open(PATH, "w", encoding="utf-8", newline="").write(src)
print("patched; pre-mipmap backup at", bak)
print("mipmapsEnabled refs:", src.count("mipmapsEnabled()"), "glGenerateMipmap refs:", src.count("glGenerateMipmap"))

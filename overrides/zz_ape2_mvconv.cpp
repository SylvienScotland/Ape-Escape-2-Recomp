// Ape Escape 2 (SLUS_206.85) - FMV frame conversion on the host (patch 0061).
//
// Ported from the PAL port's hle_mvconv (port/src/hle_overrides.c, JackyPendrag0n/ae2-recomp), used with the
// author's permission; addresses re-found for NTSC-U (PAL - 0x1238 for the code, the frame queue at 0x3DF5C0):
//
//   0x1A6D18  frame conversion. Every vsync the movie display code calls it to turn the oldest decoded frame
//             (libmpeg output: 384-byte YCbCr 4:2:0 macroblocks, stored column by column) into an RGB texture
//             in VRAM, and it returns the texture page the caller then copies to the screen. The original does
//             this with a VU1 microprogram drawing 262144 one-pixel points, every vsync, even when the frame has
//             not changed (VU1 99% of the frame, a movie at ~1 fps here). Here the frame is converted on the
//             host (BT.601, chroma interpolated) and uploaded with one image transfer, only when a new frame
//             arrives. The first frame of a movie goes through the original, which is how the page is learned.
//   0x1A4350 / 0x1A4370  picture width / height (a0 = -1).
//   0x3DF5C0  decoded-frame ring: base +0, write index +8, count +0xC, entry size +0x18, entries +0x1C.
//
// APE2_MVHLE=0 keeps the original VU1 conversion.

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

namespace
{
    constexpr uint32_t kMvConv = 0x001A6D18u;
    constexpr uint32_t kFrameRing = 0x003DF5C0u;
    constexpr uint32_t kRamMask = 0x01FFFFFFu;

    uint32_t rd32(const uint8_t *rdram, uint32_t a)
    {
        uint32_t v;
        std::memcpy(&v, rdram + (a & kRamMask), 4);
        return v;
    }

    uint8_t clamp255(int v) { return v < 0 ? 0 : v > 255 ? 255 : static_cast<uint8_t>(v); }

    void mvConvert(const uint8_t *mb, int w, int h, uint32_t *out /* 512 x h */)
    {
        const int mbw = (w + 15) / 16, mbh = (h + 15) / 16;
        const int cw = mbw * 8, ch = mbh * 8;
        static uint8_t Y[512 * 512], U[256 * 256], V[256 * 256];
        for (int mx = 0; mx < mbw; mx++)
            for (int my = 0; my < mbh; my++)
            {
                const uint8_t *m = mb + static_cast<size_t>(mx * mbh + my) * 384;
                for (int y = 0; y < 16; y++)
                    std::memcpy(Y + (my * 16 + y) * 512 + mx * 16, m + y * 16, 16);
                for (int y = 0; y < 8; y++)
                {
                    std::memcpy(U + (my * 8 + y) * 256 + mx * 8, m + 256 + y * 8, 8);
                    std::memcpy(V + (my * 8 + y) * 256 + mx * 8, m + 320 + y * 8, 8);
                }
            }
        for (int y = 0; y < mbh * 16; y++)
        {
            // MPEG-2 4:2:0: chroma rows sit between luma rows, columns on even luma
            int cy0, cy1, wy1; // wy1 = weight of the lower chroma row, out of 4
            if (y & 1)
            {
                cy0 = y >> 1;
                cy1 = cy0 + 1;
                wy1 = 1;
            }
            else
            {
                cy0 = (y >> 1) - 1;
                cy1 = y >> 1;
                wy1 = 3;
            }
            if (cy0 < 0)
                cy0 = 0;
            if (cy1 >= ch)
                cy1 = ch - 1;
            const uint8_t *u0 = U + cy0 * 256, *u1 = U + cy1 * 256, *v0 = V + cy0 * 256, *v1 = V + cy1 * 256;
            const uint8_t *yr = Y + y * 512;
            uint32_t *o = out + y * 512;
            for (int x = 0; x < mbw * 16; x++)
            {
                const int cx0 = x >> 1, cx1 = (x & 1) && cx0 + 1 < cw ? cx0 + 1 : cx0;
                const int uu = ((u0[cx0] + u0[cx1]) * (4 - wy1) + (u1[cx0] + u1[cx1]) * wy1 + 4) >> 3;
                const int vv = ((v0[cx0] + v0[cx1]) * (4 - wy1) + (v1[cx0] + v1[cx1]) * wy1 + 4) >> 3;
                const int yy = (yr[x] - 16) * 76309, cb = uu - 128, cr = vv - 128; // 16.16 fixed point
                const int r = (yy + 104597 * cr + 32768) >> 16;
                const int g = (yy - 25675 * cb - 53279 * cr + 32768) >> 16;
                const int bl = (yy + 132201 * cb + 32768) >> 16;
                o[x] = clamp255(r) | static_cast<uint32_t>(clamp255(g)) << 8 | static_cast<uint32_t>(clamp255(bl)) << 16;
            }
        }
    }

    // A+D setup (BITBLTBUF, TRXPOS, TRXREG, TRXDIR) then IMAGE data, 32 rows per tag, through the GIF (PATH3)
    void mvUpload(PS2Runtime *runtime, uint32_t bp, const uint32_t *img, int w, int h)
    {
        std::vector<uint64_t> pkt;
        pkt.reserve(10 + static_cast<size_t>(h / 32 + 1) * 2 + static_cast<size_t>(w) * h / 2);
        pkt.push_back(4u | (1ull << 60)); // GIFtag: NLOOP 4, PACKED, one register (A+D)
        pkt.push_back(0xEu);
        pkt.push_back((static_cast<uint64_t>(bp) << 32) | (static_cast<uint64_t>(512 / 64) << 48)); // PSMCT32
        pkt.push_back(0x50u);
        pkt.push_back(0u);
        pkt.push_back(0x51u);
        pkt.push_back(static_cast<uint64_t>(w) | (static_cast<uint64_t>(h) << 32));
        pkt.push_back(0x52u);
        pkt.push_back(0u);
        pkt.push_back(0x53u);
        for (int y = 0; y < h; y += 32)
        {
            const int rows = h - y < 32 ? h - y : 32;
            const uint32_t qw = static_cast<uint32_t>(rows * w / 4);
            pkt.push_back(qw | (2ull << 58) | (static_cast<uint64_t>(y + rows >= h) << 15)); // IMAGE
            pkt.push_back(0u);
            const size_t at = pkt.size();
            pkt.resize(at + static_cast<size_t>(rows) * w / 2);
            for (int r = 0; r < rows; r++)
                std::memcpy(&pkt[at + static_cast<size_t>(r) * w / 2], img + (y + r) * 512, static_cast<size_t>(w) * 4);
        }
        PS2Memory &mem = runtime->memory();
        std::vector<uint8_t> bytes(pkt.size() * 8u);
        std::memcpy(bytes.data(), pkt.data(), bytes.size());
        if (mem.m_gsWorkerEnabled)
            mem.enqueueGsWork(false, std::move(bytes)); // in order with the game's own GS work
        else
            mem.submitGifPacket(GifPathId::Path3, bytes.data(), static_cast<uint32_t>(bytes.size()));
    }

    int callGetter(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, void (*fn)(uint8_t *, R5900Context *, PS2Runtime *))
    {
        SET_GPR_S32(ctx, 4, -1);
        fn(rdram, ctx, runtime);
        return static_cast<int>(GPR_S32(ctx, 2));
    }

    uint32_t g_lastRet = 0, g_lastFrame = 0;
    uint64_t g_lastHash = 0;

    void ape2_mvconv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        static const bool useHle = [] { const char *e = std::getenv("APE2_MVHLE"); return !(e && e[0] == '0'); }();
        static const bool log = std::getenv("APE2_MVLOG") != nullptr;
        static unsigned nconv = 0;
        const uint32_t ra = GPR_U32(ctx, 31), a0 = GPR_U32(ctx, 4);
        const uint32_t base = rd32(rdram, kFrameRing), wr = rd32(rdram, kFrameRing + 8u), cnt = rd32(rdram, kFrameRing + 0xCu);
        const uint32_t sz = rd32(rdram, kFrameRing + 0x18u), n = rd32(rdram, kFrameRing + 0x1Cu);
        if (cnt == 0 || n == 0 || sz == 0)
        {
            sub_001A6D18_0x1a6d18(rdram, ctx, runtime);
            g_lastFrame = 0;
            return;
        }
        const uint32_t ent = base + sz * ((wr - cnt + n) % n); // the oldest queued frame
        const uint32_t fa = ent & kRamMask;
        // picture size (the caller clamps to 512 x 512)
        const int w = callGetter(rdram, ctx, runtime, sub_001A4350_0x1a4350);
        const int h = callGetter(rdram, ctx, runtime, sub_001A4370_0x1a4370);
        SET_GPR_U32(ctx, 4, a0);
        SET_GPR_U32(ctx, 31, ra);
        const uint32_t fsz = static_cast<uint32_t>(((w + 15) / 16) * ((h + 15) / 16) * 384);
        const bool ok = w > 0 && h > 0 && w <= 512 && h <= 512 && (w & 15) == 0 && fsz <= sz && fa + fsz <= PS2_RAM_SIZE;
        uint64_t hs = 1469598103934665603ull ^ static_cast<uint64_t>(w) << 32 ^ static_cast<uint64_t>(h);
        if (ok)
        {
            const uint8_t *p = rdram + fa;
            for (uint32_t i = 0; i + 8 <= fsz; i += 24)
            {
                uint64_t v;
                std::memcpy(&v, p + i, 8);
                hs = (hs ^ v) * 1099511628211ull;
            }
        }
        if (ok && g_lastRet && ent == g_lastFrame && hs == g_lastHash)
        {
            SET_GPR_S32(ctx, 2, static_cast<int32_t>(g_lastRet));
            ctx->pc = ra;
            return;
        }
        uint32_t lastRet = g_lastRet;
        if (!useHle || !ok || !lastRet)
        {
            // first frame of a movie (learns the texture page) or unusual sizes: the original
            sub_001A6D18_0x1a6d18(rdram, ctx, runtime);
            lastRet = GPR_U32(ctx, 2);
            if (!ok)
                lastRet = 0;
        }
        else
        {
            static uint32_t img[512 * 512];
            mvConvert(rdram + fa, w, h, img);
            mvUpload(runtime, lastRet * 32u, img, w, (h + 15) & ~15);
            SET_GPR_S32(ctx, 2, static_cast<int32_t>(lastRet));
            ctx->pc = ra;
        }
        if (log && (++nconv % 25 == 0 || nconv < 4))
            std::cerr << "[movie] " << nconv << " frames (" << w << "x" << h << "), page 0x" << std::hex << lastRet << std::dec << std::endl;
        g_lastFrame = ent;
        g_lastHash = hs;
        g_lastRet = lastRet;
    }

    void ape2_mvconv_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(kMvConv, ape2_mvconv);

        std::cerr << "[ape2:movies] FMV frame conversion on the host (APE2_MVHLE=0: the game's VU1 path)" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-mvconv", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_mvconv_apply)

// Ape Escape 2 (SLUS_206.85) - camera log (debugging aid).
//
// APE2_CAMLOG=<first>,<count>: logs the camera look-at calls (0x19FEA0: a0 = eye, a1 = target, 128-bit
// registers) with the caller, like the PAL port's AE2_CAMLOG (JackyPendrag0n/ae2-recomp,
// port/src/hle_overrides.c hle_camlook, PAL 0x1A10E0).

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace
{
    constexpr uint32_t kApe2CamLook = 0x0019FEA0u;
    uint64_t g_first = 0, g_count = 0, g_calls = 0;

    void ape2_camlook(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t n = g_calls++;
        if (n >= g_first && n < g_first + g_count)
        {
            float eye[4], target[4], vf0[4];
            std::memcpy(eye, &ctx->r[4], 16);
            std::memcpy(target, &ctx->r[5], 16);
            _mm_storeu_ps(vf0, ctx->vu0_vf[0]);
            std::fprintf(stderr, "[cam] #%llu ra=%06x eye %.1f %.1f %.1f target %.1f %.1f %.1f vf0 %g %g %g %g s1=%06x\n",
                         static_cast<unsigned long long>(n), GPR_U32(ctx, 31), eye[0], eye[1], eye[2], target[0], target[1],
                         target[2], vf0[0], vf0[1], vf0[2], vf0[3], GPR_U32(ctx, 17));
            // the pieces 0x26F5E8 builds the eye from: the slot's eye, the second camera (0x4D08F0) eye/target,
            // blend factor (+0x90) and the offset added to the eye (+0x150)
            const uint32_t slot = GPR_U32(ctx, 17) & 0x1FFFFF0u;
            float se[4], oe[4], ot[4], off[4], ofs2[4], f;
            std::memcpy(se, rdram + slot + 0x150u, 16);
            std::memcpy(oe, rdram + 0x4D0960u, 16);
            std::memcpy(ot, rdram + 0x4D0970u, 16);
            std::memcpy(&f, rdram + 0x4D0980u, 4);
            std::memcpy(off, rdram + 0x4D0A40u, 16);
            std::memcpy(ofs2, rdram + 0x4D0A50u, 16);
            float yaw[4], dist[2], st[4];
            std::memcpy(yaw, rdram + slot + 0x210u, 16);
            std::memcpy(dist, rdram + slot + 0x1D8u, 8);
            std::memcpy(st, rdram + slot + 0x160u, 16);
            std::fprintf(stderr, "[cam] #%llu parts slotEye %.3f %.3f %.3f slotTgt %.3f %.3f %.3f yaw %.4f %.4f %.4f dist %.3f %.3f\n",
                         static_cast<unsigned long long>(n), se[0], se[1], se[2], st[0], st[1], st[2], yaw[1], yaw[2], yaw[3],
                         dist[0], dist[1]);
            (void)oe;
            (void)ot;
            (void)f;
            (void)off;
            (void)ofs2;
        }
        static const bool flip = std::getenv("APE2_CAMFLIP") != nullptr; // experiment: mirror eye height
        if (flip)
        {
            float eye[4], target[4];
            std::memcpy(eye, &ctx->r[4], 16);
            std::memcpy(target, &ctx->r[5], 16);
            eye[1] = 2.0f * target[1] - eye[1];
            std::memcpy(&ctx->r[4], eye, 16);
        }
        sub_0019FEA0_0x19fea0(rdram, ctx, runtime);
        {
            // APE2_CAMFIND=<call>,x0,x1,y0,y1,z0,z1: at that call, list RAM addresses holding three consecutive floats in the box
            static const char *find = std::getenv("APE2_CAMFIND");
            unsigned long long at = 0;
            float b[6];
            if (find && std::sscanf(find, "%llu,%f,%f,%f,%f,%f,%f", &at, &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) == 7 && n == at)
            {
                int hits = 0;
                for (uint32_t a = 0x100000u; a + 12u <= 0x2000000u && hits < 400; a += 4u)
                {
                    float v[3];
                    std::memcpy(v, rdram + a, 12);
                    if (v[0] >= b[0] && v[0] <= b[1] && v[1] >= b[2] && v[1] <= b[3] && v[2] >= b[4] && v[2] <= b[5])
                    {
                        ++hits;
                        std::fprintf(stderr, "[camfind] %07x: %g %g %g\n", a, v[0], v[1], v[2]);
                    }
                }
            }
        }
        {
            // APE2_CAMPEEK=<addr hex>: print the vec4 there at every logged call
            static const uint32_t peek = [] { const char *e = std::getenv("APE2_CAMPEEK"); return e ? static_cast<uint32_t>(std::strtoul(e, nullptr, 16)) : 0u; }();
            if (peek && n >= g_first && n < g_first + g_count)
            {
                float v[4];
                std::memcpy(v, rdram + (peek & 0x1FFFFF0u), 16);
                std::fprintf(stderr, "[campeek] #%llu %07x: %g %g %g %g\n", static_cast<unsigned long long>(n), peek, v[0], v[1], v[2], v[3]);
            }
        }
        if (n >= g_first && n < g_first + g_count)
        {
            float m[16];
            std::memcpy(m, rdram + 0x3DD300u, 64);
            std::fprintf(stderr, "[cam] #%llu view (%g %g %g %g) (%g %g %g %g) (%g %g %g %g) (%g %g %g %g)\n",
                         static_cast<unsigned long long>(n), m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10],
                         m[11], m[12], m[13], m[14], m[15]);
        }
    }

    // APE2_RAYLOG=<count>: log ground raycasts 0x1D3CE0 (a0 = from, a1 = to, a2 = result) and the two
    // collision queries inside it (0x1D2D68 static, 0x1D38E8 objects)
    uint64_t g_rayLeft = 0;
    void ape2_ray(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const bool log = g_rayLeft > 0;
        float from[4], to[4];
        std::memcpy(from, &ctx->r[4], 16);
        std::memcpy(to, &ctx->r[5], 16);
        const uint32_t ra = GPR_U32(ctx, 31), a2 = GPR_U32(ctx, 6), t0 = GPR_U32(ctx, 8);
        sub_001D3CE0_0x1d3ce0(rdram, ctx, runtime);
        if (log)
        {
            --g_rayLeft;
            float res[4] = {};
            if (a2)
                std::memcpy(res, rdram + (a2 & 0x1FFFFF0u), 16);
            std::fprintf(stderr, "[ray] ra=%06x from %g %g %g to %g %g %g flags %x -> v0=%x hit %g %g %g\n", ra, from[0], from[1], from[2],
                         to[0], to[1], to[2], t0, GPR_U32(ctx, 2), res[0], res[1], res[2]);
        }
    }
    void ape2_ray_static(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const bool log = g_rayLeft > 0;
        const uint32_t a0 = GPR_U32(ctx, 4), a1 = GPR_U32(ctx, 5), a2 = GPR_U32(ctx, 6), a3 = GPR_U32(ctx, 7), t0 = GPR_U32(ctx, 8);
        sub_001D2D68_0x1d2d68(rdram, ctx, runtime);
        if (log)
            std::fprintf(stderr, "[ray]   static a0=%x a1=%x a2=%x a3=%x t0=%x -> v0=%x\n", a0, a1, a2, a3, t0, GPR_U32(ctx, 2));
    }
    void ape2_ray_objects(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const bool log = g_rayLeft > 0;
        sub_001D38E8_0x1d38e8(rdram, ctx, runtime);
        if (log)
            std::fprintf(stderr, "[ray]   objects -> v0=%x\n", GPR_U32(ctx, 2));
    }
    void ape2_ray_cells(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const bool log = g_rayLeft > 0;
        const uint32_t a0 = GPR_U32(ctx, 4);
        float from[4], to[4];
        std::memcpy(from, &ctx->r[5], 16);
        std::memcpy(to, &ctx->r[6], 16);
        sub_001CE870_0x1ce870(rdram, ctx, runtime);
        if (log)
        {
            uint32_t root = 0;
            std::memcpy(&root, rdram + ((a0 + 0x6000u) & 0x1FFFFFCu), 4);
            float nb[8] = {};
            uint32_t links[4] = {};
            if (root)
            {
                std::memcpy(nb, rdram + (root & 0x1FFFFF0u), 32);
                std::memcpy(links, rdram + ((root + 0x20u) & 0x1FFFFF0u), 16);
            }
            std::fprintf(stderr, "[ray]   root=%x centre %g %g %g %g half %g %g %g %g links %x %x %x %x\n", root, nb[0], nb[1], nb[2], nb[3], nb[4],
                         nb[5], nb[6], nb[7], links[0], links[1], links[2], links[3]);
        }
        if (log)
            std::fprintf(stderr, "[ray]   cells tree=%x from %g %g %g to %g %g %g -> %d\n", a0, from[0], from[1], from[2], to[0], to[1], to[2],
                         static_cast<int>(GPR_U32(ctx, 2)));
    }
    void ape2_ray_cell(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const bool log = g_rayLeft > 0;
        sub_001D2BC0_0x1d2bc0(rdram, ctx, runtime);
        if (log)
            std::fprintf(stderr, "[ray]   cell -> %d\n", static_cast<int>(GPR_U32(ctx, 2)));
    }
    void ape2_coll_build(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t a0 = GPR_U32(ctx, 4), ra = GPR_U32(ctx, 31);
        uint32_t w[8] = {};
        if (a0)
            std::memcpy(w, rdram + (a0 & 0x1FFFFF0u), 32);
        sub_001D29B8_0x1d29b8(rdram, ctx, runtime);
        uint32_t tree = 0, count = 0;
        std::memcpy(&tree, rdram + ((GPR_U32(ctx, 28) + 0x18F4u) & 0x1FFFFFCu), 4);
        if (tree)
            std::memcpy(&count, rdram + ((tree + 0x6004u) & 0x1FFFFFCu), 4);
        std::fprintf(stderr, "[coll] build ra=%06x data=%x words %08x %08x %08x %08x %08x %08x %08x %08x -> tree %x items %u\n", ra, a0, w[0], w[1], w[2],
                     w[3], w[4], w[5], w[6], w[7], tree, count);
    }
    void ape2_arc_find(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        char a[17] = {}, b[17] = {};
        std::memcpy(a, &ctx->r[4], 16);
        std::memcpy(b, &ctx->r[5], 16);
        const uint32_t ra = GPR_U32(ctx, 31);
        {
            uint32_t s0w[4];
            std::memcpy(s0w, &ctx->r[16], 16);
            std::fprintf(stderr, "[arc] find entry s0 %08x %08x %08x %08x a0 %08x %08x %08x %08x\n", s0w[0], s0w[1], s0w[2], s0w[3],
                         reinterpret_cast<uint32_t *>(a)[0], reinterpret_cast<uint32_t *>(a)[1], reinterpret_cast<uint32_t *>(a)[2], reinterpret_cast<uint32_t *>(a)[3]);
        }
        sub_00192D80_0x192d80(rdram, ctx, runtime);
        std::fprintf(stderr, "[arc] find ra=%06x archive '%s' entry '%s' -> %x\n", ra, a, b, GPR_U32(ctx, 2));
    }
    void ape2_s0_188498(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_00188498_0x188498(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1])
            std::fprintf(stderr, "[s0] 188498 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx) pc now %x\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0], ctx->pc);
    }
    void ape2_s0_188c88(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_00188C88_0x188c88(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1])
            std::fprintf(stderr, "[s0] 188c88 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx) pc now %x\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0], ctx->pc);
    }
    void ape2_s0_1a2128(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001A2128_0x1a2128(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1])
            std::fprintf(stderr, "[s0] 1a2128 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx) pc now %x\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0], ctx->pc);
    }
    void ape2_s0_1929e8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001929E8_0x1929e8(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1])
            std::fprintf(stderr, "[s0] 1929e8 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx) pc now %x\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0], ctx->pc);
    }

    void ape2_alloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t size = GPR_U32(ctx, 4), ra = GPR_U32(ctx, 31);
        uint64_t b0[2], a0_[2];
        std::memcpy(b0, &ctx->r[16], 16);
        sub_001A3868_0x1a3868(rdram, ctx, runtime);
        std::memcpy(a0_, &ctx->r[16], 16);
        if (b0[1] != a0_[1])
            std::fprintf(stderr, "[s0] 1a3868 changed s0 upper %016llx -> %016llx\n", (unsigned long long)b0[1], (unsigned long long)a0_[1]);
        const uint32_t r = GPR_U32(ctx, 2);
        if (!r || size >= 0x100000u)
            std::fprintf(stderr, "[alloc] ra=%06x size=%x -> %x\n", ra, size, r);
    }
    void ape2_alloc2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t size = GPR_U32(ctx, 4), ra = GPR_U32(ctx, 31);
        sub_001A39B8_0x1a39b8(rdram, ctx, runtime);
        const uint32_t r = GPR_U32(ctx, 2);
        if (!r || size >= 0x100000u)
            std::fprintf(stderr, "[alloc2] ra=%06x size=%x -> %x\n", ra, size, r);
    }
    void ape2_slot(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        char a[17] = {};
        std::memcpy(a, &ctx->r[4], 16);
        const uint32_t ra = GPR_U32(ctx, 31), a1 = GPR_U32(ctx, 5);
        sub_001927B0_0x1927b0(rdram, ctx, runtime);
        const uint32_t slot = GPR_U32(ctx, 2);
        if (std::strncmp(a, "TIT", 3) == 0)
        {
            uint32_t f[8] = {};
            if (slot)
                std::memcpy(f, rdram + ((slot + 0x50u) & 0x1FFFFF0u), 32);
            char nm[17] = {};
            if (slot)
                std::memcpy(nm, rdram + (slot & 0x1FFFFF0u), 16);
            uint32_t raw[4];
            std::memcpy(raw, a, 16);
            std::fprintf(stderr, "[arc] slot raw %08x %08x %08x %08x\n", raw[0], raw[1], raw[2], raw[3]);
            std::fprintf(stderr, "[arc] slot ra=%06x '%s' a1=%x -> %x name '%s' +50 %08x size %x +58 %x base %x +60 %x\n", ra, a, a1, slot, nm,
                         f[0], f[1], f[2], f[3], f[4]);
        }
    }

    void ape2_s0_192bd8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_00192BD8_0x192bd8(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 192bd8 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }
    void ape2_s0_1d3bc0(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001D3BC0_0x1d3bc0(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 1d3bc0 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }
    void ape2_s0_1d2970(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001D2970_0x1d2970(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 1d2970 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }
    void ape2_s0_1d2fc8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001D2FC8_0x1d2fc8(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 1d2fc8 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }
    void ape2_s0_1d2e98(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001D2E98_0x1d2e98(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 1d2e98 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }
    void ape2_s0_1d29b8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint64_t before[2], after[2];
        std::memcpy(before, &ctx->r[16], 16);
        sub_001D29B8_0x1d29b8(rdram, ctx, runtime);
        std::memcpy(after, &ctx->r[16], 16);
        if (before[1] != after[1] || (before[0] & 0xFFFFFFFFFFull) == 0x415F544954ull)
            std::fprintf(stderr, "[s0] 1d29b8 changed s0 upper %016llx -> %016llx (lower %016llx -> %016llx)\n", (unsigned long long)before[1], (unsigned long long)after[1], (unsigned long long)before[0], (unsigned long long)after[0]);
    }

    // APE2_BOXLOG=<count>: log the in-box test 0x2020C8 (a0 = box min/max, a1 = point, f12 = radius)
    uint64_t g_boxLeft = 0;
    void ape2_box(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t a0 = GPR_U32(ctx, 4), ra = GPR_U32(ctx, 31);
        static uint64_t calls = 0;
        ++calls;
        float p[4], box[8] = {}, m[16];
        std::memcpy(p, &ctx->r[5], 16);
        const float r = ctx->f[12];
        if (a0)
            std::memcpy(box, rdram + (a0 & 0x1FFFFF0u), 32);
        std::memcpy(m, rdram + 0x5127A0u, 64);
        sub_002020C8_0x2020c8(rdram, ctx, runtime);
        // log calls in [APE2_BOXSKIP, APE2_BOXSKIP + APE2_BOXLOG)
        static const uint64_t skip = std::getenv("APE2_BOXSKIP") ? std::strtoull(std::getenv("APE2_BOXSKIP"), nullptr, 0) : 0;
        if (g_boxLeft && calls > skip)
        {
            --g_boxLeft;
            std::fprintf(stderr, "[box] ra=%06x box=%x ", ra, a0);
            std::fprintf(stderr, "p %g %g %g %g r %g min %g %g %g %g max %g %g %g %g -> %d clip %06x\n", p[0], p[1], p[2], p[3], r, box[0], box[1],
                         box[2], box[3], box[4], box[5], box[6], box[7], static_cast<int>(GPR_U32(ctx, 2)), ctx->vu0_clip_flags & 0xFFFFFFu);
            if (0) std::fprintf(stderr, "[box]   m (%g %g %g %g) (%g %g %g %g) (%g %g %g %g) (%g %g %g %g)\n", m[0], m[1], m[2], m[3], m[4], m[5], m[6],
                         m[7], m[8], m[9], m[10], m[11], m[12], m[13], m[14], m[15]);
        }
    }

    void ape2_camlog_apply(PS2Runtime &runtime)
    {
        if (const char *b = std::getenv("APE2_BOXLOG"))
        {
            g_boxLeft = std::strtoull(b, nullptr, 0);
            runtime.registerFunction(0x002020C8u, ape2_box);
        }
        if (const char *r = std::getenv("APE2_RAYLOG"))
        {
            g_rayLeft = std::strtoull(r, nullptr, 0);
            runtime.registerFunction(0x001D3CE0u, ape2_ray);
            runtime.registerFunction(0x001D2D68u, ape2_ray_static);
            runtime.registerFunction(0x001D38E8u, ape2_ray_objects);
            runtime.registerFunction(0x001CE870u, ape2_ray_cells);
            runtime.registerFunction(0x00192BD8u, ape2_s0_192bd8);
            runtime.registerFunction(0x001D3BC0u, ape2_s0_1d3bc0);
            runtime.registerFunction(0x001D2970u, ape2_s0_1d2970);
            runtime.registerFunction(0x001D2FC8u, ape2_s0_1d2fc8);
            runtime.registerFunction(0x001D2E98u, ape2_s0_1d2e98);
            runtime.registerFunction(0x00188498u, ape2_s0_188498);
            runtime.registerFunction(0x00188C88u, ape2_s0_188c88);
            runtime.registerFunction(0x001A2128u, ape2_s0_1a2128);
            runtime.registerFunction(0x001929E8u, ape2_s0_1929e8);
            runtime.registerFunction(0x001D29B8u, ape2_coll_build);
            runtime.registerFunction(0x00192D80u, ape2_arc_find);
            runtime.registerFunction(0x001A3868u, ape2_alloc);
            runtime.registerFunction(0x001927B0u, ape2_slot);
            runtime.registerFunction(0x001A39B8u, ape2_alloc2);
            runtime.registerFunction(0x001D2BC0u, ape2_ray_cell);
        }
        const char *env = std::getenv("APE2_CAMLOG");
        if (!env)
            return;
        char *end = nullptr;
        g_first = std::strtoull(env, &end, 0);
        g_count = (end && *end == ',') ? std::strtoull(end + 1, nullptr, 0) : 1000000ull;
        runtime.registerFunction(kApe2CamLook, ape2_camlook);
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-camlog", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_camlog_apply)

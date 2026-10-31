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
            std::fprintf(stderr, "[cam] #%llu ra=%06x eye %.1f %.1f %.1f target %.1f %.1f %.1f vf0 %g %g %g %g\n",
                         static_cast<unsigned long long>(n), GPR_U32(ctx, 31), eye[0], eye[1], eye[2], target[0], target[1],
                         target[2], vf0[0], vf0[1], vf0[2], vf0[3]);
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
    }

    void ape2_camlog_apply(PS2Runtime &runtime)
    {
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

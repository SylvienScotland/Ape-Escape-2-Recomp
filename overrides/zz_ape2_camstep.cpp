// Ape Escape 2 (SLUS_206.85) - camera step log (debugging aid).
//
// APE2_CAMSTEP=1: the gameplay camera controller 0x272E40 runs a chain of steps on the camera (a0); each step is
// wrapped here, and a step that moves the camera's eye (+0x150) by more than 0.5 is logged with the eye before
// and after. Used to find the step behind the eye snapping back every few frames (camera shake).

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

void ape2HoldCheckpoints(int delta); // EeScheduler.cpp: run hooked calls to completion

namespace
{
    uint64_t g_stepCalls = 0;

    template <void (*Fn)(uint8_t *, R5900Context *, PS2Runtime *), uint32_t Addr>
    void ape2_camstep(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t cam = GPR_U32(ctx, 4) & 0x1FFFFF0u;
        float before[4], after[4];
        std::memcpy(before, rdram + cam + 0x150u, 16);
        ape2HoldCheckpoints(1);
        Fn(rdram, ctx, runtime);
        ape2HoldCheckpoints(-1);
        std::memcpy(after, rdram + cam + 0x150u, 16);
        const float d = std::fabs(after[0] - before[0]) + std::fabs(after[1] - before[1]) + std::fabs(after[2] - before[2]);
        ++g_stepCalls;
        static bool firstSeen[16] = {};
        bool &seen = firstSeen[(Addr >> 4) & 15u];
        if (!seen)
        {
            seen = true;
            std::fprintf(stderr, "[camstep] first call of %06x cam=%06x eye %.2f %.2f %.2f\n", Addr, cam, after[0], after[1], after[2]);
        }
        static const float threshold = std::getenv("APE2_CAMSTEP_MIN") ? static_cast<float>(std::atof(std::getenv("APE2_CAMSTEP_MIN"))) : 0.5f;
        if (d > threshold)
            std::fprintf(stderr, "[camstep] #%llu %06x cam=%06x eye %.2f %.2f %.2f -> %.2f %.2f %.2f\n",
                         static_cast<unsigned long long>(g_stepCalls), Addr, cam, before[0], before[1], before[2], after[0],
                         after[1], after[2]);
    }

    // APE2_CAMRAY=1: the camera's rays (0x1D3CE0 called from the camera code 0x270000-0x276000): from, to,
    // result (a2) and v0
    void ape2_camray(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t ra = GPR_U32(ctx, 31), a2 = GPR_U32(ctx, 6), t0 = GPR_U32(ctx, 8);
        float from[4], to[4];
        std::memcpy(from, &ctx->r[4], 16);
        std::memcpy(to, &ctx->r[5], 16);
        // run the ray to its end here: the collision tree walk (0x1CE7B0) recurses, and every return from the
        // recursion leaves the generated function and resumes later; finish that continuation now, with no
        // checkpoint in between, so the ray is atomic as on the PS2 (and its results are final for the log)
        static const bool atomic = !std::getenv("APE2_ATOMIC_RAY") || std::atoi(std::getenv("APE2_ATOMIC_RAY")) != 0;
        ape2HoldCheckpoints(1);
        sub_001D3CE0_0x1d3ce0(rdram, ctx, runtime);
        for (int guard = 0; atomic && ctx->pc != ra && guard < 1000000; ++guard)
            runtime->lookupFunction(ctx->pc)(rdram, ctx, runtime);
        ape2HoldCheckpoints(-1);
        if (std::getenv("APE2_CAMRAY") && ra >= 0x270000u && ra < 0x276000u)
        {
            float res[4] = {};
            if (a2)
                std::memcpy(res, rdram + (a2 & 0x1FFFFF0u), 16);
            std::fprintf(stderr, "[camray] ra=%06x from %.2f %.2f %.2f to %.2f %.2f %.2f flags %x -> v0=%x res %.3f %.3f %.3f %.3f pc=%06x\n", ra,
                         from[0], from[1], from[2], to[0], to[1], to[2], t0, GPR_U32(ctx, 2), res[0], res[1], res[2], res[3], ctx->pc);
        }
    }

    // Camera yaw damping (APE2_CAMDAMP=1; off by default since recomp patch 0050 fixed the cause, SQRT.S): 0x275BB8 ends by measuring the camera's yaw
    // (+0x214, mirrored at +0x218) back from where the eye ended up; with the goal placed from that yaw
    // (0x274440) and the eye moved 65% toward it (0x272E40), the loop's correction came out about 2.2x the
    // eye's angle, i.e. right at the edge of stability: the yaw alternated by ~0.08 rad every frame and the
    // camera snapped left and right (worst with Jimmy facing a wall). Half of each small correction is applied.
    void ape2_camdamp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        constexpr float kTwoPi = 6.28318530718f, kPi = 3.14159265359f;
        const uint32_t ra = GPR_U32(ctx, 31);
        const uint32_t cam = GPR_U32(ctx, 4) & 0x1FFFFF0u;
        float before = 0.0f;
        std::memcpy(&before, rdram + cam + 0x214u, 4);
        ape2HoldCheckpoints(1);
        sub_00275BB8_0x275bb8(rdram, ctx, runtime);
        for (int guard = 0; ctx->pc != ra && guard < 1000000; ++guard)
            runtime->lookupFunction(ctx->pc)(rdram, ctx, runtime);
        ape2HoldCheckpoints(-1);
        float after = 0.0f;
        std::memcpy(&after, rdram + cam + 0x214u, 4);
        float d = std::fmod(after - before + kPi, kTwoPi);
        if (d < 0.0f)
            d += kTwoPi;
        d -= kPi;
        if (std::fabs(d) < 0.5f) // small corrections only; large turns (cuts, resets) pass unchanged
        {
            float yaw = std::fmod(before + 0.5f * d, kTwoPi);
            if (yaw < 0.0f)
                yaw += kTwoPi;
            std::memcpy(rdram + cam + 0x214u, &yaw, 4);
            std::memcpy(rdram + cam + 0x218u, &yaw, 4);
        }
    }

    void ape2_camstep_apply(PS2Runtime &runtime)
    {
        if (std::getenv("APE2_CAMRAY") || std::getenv("APE2_ATOMIC_RAY"))
            runtime.registerFunction(0x001D3CE0u, ape2_camray);
        static const bool damp = std::getenv("APE2_CAMDAMP") && std::atoi(std::getenv("APE2_CAMDAMP")) != 0;
        if (damp && !std::getenv("APE2_CAMSTEP"))
            runtime.registerFunction(0x00275BB8u, ape2_camdamp);
        if (!std::getenv("APE2_CAMSTEP"))
            return;
        runtime.registerFunction(0x00273378u, ape2_camstep<sub_00273378_0x273378, 0x273378u>);
        runtime.registerFunction(0x00273E20u, ape2_camstep<sub_00273E20_0x273e20, 0x273E20u>);
        runtime.registerFunction(0x002737E8u, ape2_camstep<sub_002737E8_0x2737e8, 0x2737E8u>);
        runtime.registerFunction(0x00273A30u, ape2_camstep<sub_00273A30_0x273a30, 0x273A30u>);
        runtime.registerFunction(0x00274440u, ape2_camstep<sub_00274440_0x274440, 0x274440u>);
        runtime.registerFunction(0x002756C0u, ape2_camstep<sub_002756C0_0x2756c0, 0x2756C0u>);
        runtime.registerFunction(0x00275408u, ape2_camstep<sub_00275408_0x275408, 0x275408u>);
        runtime.registerFunction(0x00274FB0u, ape2_camstep<sub_00274FB0_0x274fb0, 0x274FB0u>);
        runtime.registerFunction(0x00275BB8u, ape2_camstep<sub_00275BB8_0x275bb8, 0x275BB8u>);
        runtime.registerFunction(0x002754A8u, ape2_camstep<sub_002754A8_0x2754a8, 0x2754A8u>);
        runtime.registerFunction(0x00275310u, ape2_camstep<sub_00275310_0x275310, 0x275310u>);
        runtime.registerFunction(0x00272E40u, ape2_camstep<sub_00272E40_0x272e40, 0x272E40u>);
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-camstep", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_camstep_apply)

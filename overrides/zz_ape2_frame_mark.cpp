// Ape Escape 2 (SLUS_206.85) - end of a stage frame, for the frame-locked vsync (PS2Recomp patch 0049).
//
// 0x19BCE0 runs one stage frame (it moves the camera through 0x26F5E8 and counts frames at 0x3E068C; the PAL
// port's 0x19CF28). The game moves its camera by the number of vsyncs a frame took and overshoots when that is
// 2, so the camera shook whenever a frame took longer than 16.7 ms. The runtime holds the next vsync until this
// function has returned (EeScheduler.cpp, holdVBlankForGameFrame), so every frame sees exactly one vsync.

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

void ape2NoteGameFrame(); // EeScheduler.cpp

namespace
{
    constexpr uint32_t kApe2StageFrame = 0x0019BCE0u;

    void ape2_stage_frame(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        sub_0019BCE0_0x19bce0(rdram, ctx, runtime);
        ape2NoteGameFrame();
    }

    void ape2_frame_mark_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(kApe2StageFrame, ape2_stage_frame);
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-frame-mark", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_frame_mark_apply)

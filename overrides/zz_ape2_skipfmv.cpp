// Ape Escape 2 (SLUS_206.85) - skip FMVs (temporary).
//
// The movie thread (decode loop at 0x1A9118) pulls frames with sceMpegGetPictureRAW8 (0x370220):
// macroblocks in RAW8 YCbCr that the game then colour-converts on the IPU. PS2Recomp has no RAW8
// output and no IPU CSC (its MPEG path decodes to RGBA via FFmpeg), and the stub aborts the program.
//
// Until RAW8 + IPU CSC exist, end each movie cleanly instead:
//   sceMpegGetPictureRAW8 -> returns 0 (no macroblocks; the loop's bgez path, not its error path)
//                            and marks the movie as skipped
//   sceMpegIsEnd (0x3702F0, real SDK code: returns *(*(mp+0x40))) -> returns 1 once for a skipped
//                            movie, so the loop exits through sceMpegReset like a finished movie
// Everything else (stream setup, demux, reset) runs unchanged.

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <iostream>

namespace
{
    bool g_ape2SkipPending = false;
    uint32_t g_ape2SkippedMovies = 0;

    void ape2_mpeg_getpicture_raw8(uint8_t * /*rdram*/, R5900Context *ctx, PS2Runtime * /*runtime*/)
    {
        ctx->pc = GPR_U32(ctx, 31);
        if (!g_ape2SkipPending)
        {
            g_ape2SkipPending = true;
            std::cerr << "[ape2:fmv] skipping movie #" << ++g_ape2SkippedMovies
                      << " (sceMpegGetPictureRAW8 not supported yet) mp=0x" << std::hex << GPR_U32(ctx, 4)
                      << std::dec << std::endl;
        }
        SET_GPR_U32(ctx, 2, 0u);
    }

    void ape2_mpeg_isend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (g_ape2SkipPending)
        {
            g_ape2SkipPending = false;
            ctx->pc = GPR_U32(ctx, 31);
            SET_GPR_U32(ctx, 2, 1u);
            std::cerr << "[ape2:fmv] movie #" << g_ape2SkippedMovies << " reported as ended" << std::endl;
            return;
        }
        sub_003702F0_0x3702f0(rdram, ctx, runtime);
    }

    void ape2_skipfmv_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(0x00370220u, ape2_mpeg_getpicture_raw8);
        runtime.registerFunction(0x003702F0u, ape2_mpeg_isend);
        std::cerr << "[ape2:fmv] FMV skip installed" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-skipfmv", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_skipfmv_apply)

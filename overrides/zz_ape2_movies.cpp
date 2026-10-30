// Ape Escape 2 (SLUS_206.85) - skip FMVs at movie start (until IPU playback exists).
//
// Approach from the PAL port JackyPendrag0n/ae2-recomp (port/src/hle_overrides.c, hle_movie_start /
// hle_movie_bank_load), used with the author's permission; addresses re-found for NTSC-U:
//
//   0x1A4B78  movie start: creates the decode/display threads and sets the movie state
//             [gp-0x3F8] = 1 (playing). The game's own end path writes 3 there (0x1A4B68).
//             Skipped: state = 3 at once, so the caller's normal post-movie flow runs and no stream
//             buffer or decode thread is set up.
//   0x1A5968  per-movie companion bank load (subtitles / voice), result pointer in [gp-0x3C0].
//             Skipped: [gp-0x3C0] = 0 ("no bank"). New Game -> D2.PSS failed here with an IOP heap
//             allocation of 0x54D90 bytes right after the movie stream buffer.
//
// APE2_MOVIES=1 restores the original functions (the older zz_ape2_skipfmv path then ends each
// movie at its first frame).

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cstdlib>
#include <cstring>
#include <iostream>

namespace
{
    constexpr uint32_t kApe2MovieStart = 0x001A4B78u;
    constexpr uint32_t kApe2MovieBankLoad = 0x001A5968u;
    constexpr int32_t kApe2MovieStateGpOffset = -0x3F8;
    constexpr int32_t kApe2MovieBankGpOffset = -0x3C0;
    constexpr uint32_t kApe2MovieStateFinished = 3u;

    void ape2_gp_store32(uint8_t *rdram, R5900Context *ctx, int32_t offset, uint32_t value)
    {
        const uint32_t addr = GPR_U32(ctx, 28) + static_cast<uint32_t>(offset);
        std::memcpy(rdram + (addr & 0x01FFFFFFu), &value, sizeof(value));
    }

    void ape2_movie_start(uint8_t *rdram, R5900Context *ctx, PS2Runtime * /*runtime*/)
    {
        static uint32_t count = 0;
        std::cerr << "[ape2:movies] movie start #" << ++count << " skipped (reported finished)" << std::endl;
        ape2_gp_store32(rdram, ctx, kApe2MovieStateGpOffset, kApe2MovieStateFinished);
        SET_GPR_U32(ctx, 2, 0u);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void ape2_movie_bank_load(uint8_t *rdram, R5900Context *ctx, PS2Runtime * /*runtime*/)
    {
        ape2_gp_store32(rdram, ctx, kApe2MovieBankGpOffset, 0u);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void ape2_movies_apply(PS2Runtime &runtime)
    {
        const char *env = std::getenv("APE2_MOVIES");
        if (env && env[0] == '1')
        {
            std::cerr << "[ape2:movies] APE2_MOVIES=1: original movie start kept" << std::endl;
            return;
        }
        runtime.registerFunction(kApe2MovieStart, ape2_movie_start);
        runtime.registerFunction(kApe2MovieBankLoad, ape2_movie_bank_load);
        std::cerr << "[ape2:movies] FMVs skipped at movie start" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-movies", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_movies_apply)

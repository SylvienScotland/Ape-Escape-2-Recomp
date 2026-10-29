// Ape Escape 2 (SLUS_206.85) - IOP heap fallback for the movie stream buffer.
//
// The movie player (0x1895E0) asks sceSifAllocIopHeap (0x3A3920) for a 0xC0010-byte (768KB) IOP
// buffer, then loops on sceCdStInit(bufmax, bankmax, buf) until it succeeds. The emulated IOP heap
// can't fit that next to the game's sound banks, the alloc returns 0, and sceCdStInit rejects a
// null buffer forever (the "crawl" after the presents screen).
//
// The runtime's sceCdSt* streaming is HLE: it only checks that the buffer address is non-zero and
// streams sectors straight into the EE-side buffer passed to sceCdStRead; it never touches this
// IOP buffer. So when the movie-buffer alloc fails, hand back a placeholder just past IOP RAM
// (0x200000): non-zero, aligned, and rejected as out of range if anything ever tried to write it.
// Also logs every IOP heap allocation (replaces the old trace in ape2_trace_handlers.cpp).

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <iostream>

namespace
{
    constexpr uint32_t kApe2MovieAllocReturn = 0x00189680u; // return address of the alloc in 0x1895E0
    constexpr uint32_t kApe2IopPlaceholder = 0x00200000u;

    void ape2_iopheap_alloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        static uint32_t calls = 0;
        const uint32_t size = GPR_U32(ctx, 4);
        const uint32_t ra = GPR_U32(ctx, 31);
        sub_003A3920_0x3a3920(rdram, ctx, runtime);
        uint32_t result = GPR_U32(ctx, 2);

        const bool fallback = (result == 0u && ra == kApe2MovieAllocReturn);
        if (fallback)
        {
            result = kApe2IopPlaceholder;
            SET_GPR_U32(ctx, 2, result);
        }

        if (calls++ < 64u)
            std::cerr << "[ape2:iopheap] alloc size=0x" << std::hex << size << " (" << std::dec << size << ") -> 0x"
                      << std::hex << result << " ra=0x" << ra << std::dec
                      << (fallback ? " [movie buffer placeholder]" : (result == 0u ? " [FAILED]" : "")) << std::endl;
    }

    void ape2_iopheap_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(0x003A3920u, ape2_iopheap_alloc);
        std::cerr << "[ape2:iopheap] movie buffer fallback installed" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-iopheap", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_iopheap_apply)

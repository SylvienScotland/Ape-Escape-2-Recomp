// Ape Escape 2 (SLUS_206.85) - archive slot lookup by name: ignore the bytes after the name's NUL.
//
// 0x1927B0 finds a loaded archive (TITLE, TIT_A, a stage's archive ...) by comparing the full 128-bit name
// register with each slot's 16-byte name. At the title, the name of the title's stage archive (TIT_A) reaches
// the lookup with a stray value in its upper 64 bits, so the lookup misses, 'STAT_BSP' (the static collision)
// is never found, the collision tree stays empty, every ground ray misses and Jimmy and the monkeys stand at
// y = -40 under the hill. The names are NUL-padded in the ELF and in the slots, so clearing the bytes after
// the first NUL never changes a correct lookup. Where the stray upper half comes from is still open
// (docs/LOG.md: not the scheduler, the loader, its callees or the syscalls).

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cstring>

namespace
{
    constexpr uint32_t kApe2ArchiveSlotFind = 0x001927B0u;

    void ape2_archive_slot_find(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint8_t name[16];
        std::memcpy(name, &ctx->r[4], 16);
        bool end = false;
        for (uint8_t &c : name)
        {
            if (end)
                c = 0;
            else if (c == 0)
                end = true;
        }
        std::memcpy(&ctx->r[4], name, 16);
        sub_001927B0_0x1927b0(rdram, ctx, runtime);
    }

    void ape2_archive_name_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(kApe2ArchiveSlotFind, ape2_archive_slot_find);
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-archive-name", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_archive_name_apply)

// Ape Escape 2 (SLUS_206.85) - diagnostic override.
//
// Boot 4 crashed on a null indirect call at 0x192a6c: the per-type handler table at 0x53B840
// (32-byte slots, 16-byte name key at +0x00, handler at +0x10) had no handler for type 0.
// This wraps the functions that build and use that table and logs what happens.
//
//   0x192618  table init (clears every slot's handler)
//   0x192728  register(name=a0, handler=a1): binds handler to the slot whose key matches name
//   0x1929E8  runner: walks the ordered list and calls table[type].handler
//   0x18CA50  the only caller of init + register
//
// Pure logging: every wrapper calls the original recompiled function unchanged.

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "game_overrides.h"
#include "ps2_recompiled_functions.h"

#include <cstdio>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>

namespace
{
    constexpr uint32_t kApe2Table = 0x0053B840u;
    constexpr uint32_t kApe2SlotSize = 0x20u;

    inline uint32_t ape2_rd32(const uint8_t *rdram, uint32_t addr)
    {
        uint32_t v = 0;
        std::memcpy(&v, rdram + (addr & 0x01FFFFFFu), sizeof(v));
        return v;
    }

    std::string ape2_rdName(const uint8_t *rdram, uint32_t addr, size_t max = 16)
    {
        std::string s;
        if (addr == 0u || (addr & 0x01FFFFFFu) + max > 0x02000000u)
            return "<bad ptr>";
        for (size_t i = 0; i < max; ++i)
        {
            const char c = static_cast<char>(rdram[(addr + i) & 0x01FFFFFFu]);
            if (c == '\0')
                break;
            s.push_back((c >= 32 && c < 127) ? c : '.');
        }
        return s;
    }

    std::string ape2_slotKey(const uint8_t *rdram, uint32_t slotAddr)
    {
        std::ostringstream o;
        o << std::hex;
        for (uint32_t w = 0; w < 4; ++w)
            o << (w ? " " : "") << ape2_rd32(rdram, slotAddr + w * 4);
        o << " '" << ape2_rdName(rdram, slotAddr, 16) << "'";
        return o.str();
    }

    // Slot count lives at (*(gp+0x1778)) + 4, same as the register function reads it.
    uint32_t ape2_slotCount(const uint8_t *rdram, R5900Context *ctx)
    {
        const uint32_t base = ape2_rd32(rdram, GPR_U32(ctx, 28) + 0x1778u);
        return base ? ape2_rd32(rdram, base + 4u) : 0u;
    }

    void ape2_dumpTable(const uint8_t *rdram, R5900Context *ctx, const char *why)
    {
        const uint32_t n = ape2_slotCount(rdram, ctx);
        uint32_t bound = 0;
        const uint32_t shown = n < 256u ? n : 256u;
        for (uint32_t i = 0; i < shown; ++i)
            if (ape2_rd32(rdram, kApe2Table + i * kApe2SlotSize + 0x10u))
                ++bound;
        std::cerr << "[ape2:handlers] " << why << ": slots=" << n << " bound=" << bound << std::endl;
        for (uint32_t i = 0; i < shown && i < 8u; ++i)
        {
            const uint32_t s = kApe2Table + i * kApe2SlotSize;
            std::cerr << "[ape2:handlers]   slot " << i << " key=" << ape2_slotKey(rdram, s)
                      << " fn=0x" << std::hex << ape2_rd32(rdram, s + 0x10u) << std::dec << std::endl;
        }
    }

    void trace_18CA50(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        std::cerr << "[ape2:handlers] enter 0x18CA50 ra=0x" << std::hex << GPR_U32(ctx, 31) << std::dec << std::endl;
        sub_0018CA50_0x18ca50(rdram, ctx, runtime);
        ape2_dumpTable(rdram, ctx, "after 0x18CA50");
    }

    void trace_192618(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        std::cerr << "[ape2:handlers] table init 0x192618" << std::endl;
        sub_00192618_0x192618(rdram, ctx, runtime);
        ape2_dumpTable(rdram, ctx, "after init");
    }

    void trace_192728(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        static uint32_t calls = 0;
        const uint32_t namePtr = GPR_U32(ctx, 4);
        const uint32_t handler = GPR_U32(ctx, 5);
        const uint32_t n = ape2_slotCount(rdram, ctx);
        sub_00192728_0x192728(rdram, ctx, runtime);

        int boundSlot = -1;
        for (uint32_t i = 0; i < n && i < 256u; ++i)
            if (ape2_rd32(rdram, kApe2Table + i * kApe2SlotSize + 0x10u) == handler)
            {
                boundSlot = static_cast<int>(i);
                break;
            }
        if (calls++ < 200u)
            std::cerr << "[ape2:handlers] register name@0x" << std::hex << namePtr << " '" << ape2_rdName(rdram, namePtr)
                      << "' fn=0x" << handler << std::dec << " slots=" << n
                      << (boundSlot >= 0 ? " -> bound slot " + std::to_string(boundSlot) : std::string(" -> NOT BOUND"))
                      << std::endl;
    }

    void trace_1929E8(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        static bool dumped = false;
        if (!dumped)
        {
            dumped = true;
            ape2_dumpTable(rdram, ctx, "first run of 0x1929E8");
        }
        sub_001929E8_0x1929e8(rdram, ctx, runtime);
    }

    void ape2_apply(PS2Runtime &runtime)
    {
        runtime.registerFunction(0x0018CA50u, trace_18CA50);
        runtime.registerFunction(0x00192618u, trace_192618);
        runtime.registerFunction(0x00192728u, trace_192728);
        runtime.registerFunction(0x001929E8u, trace_1929E8);
        std::cerr << "[ape2:handlers] trace override installed" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-trace-handlers", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_apply)

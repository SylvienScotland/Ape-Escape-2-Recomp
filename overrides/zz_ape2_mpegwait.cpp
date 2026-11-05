// Ape Escape 2 (SLUS_206.85) - libmpeg's IPU wait without the 5000 idle polls (patch 0061).
//
// 0x374558 waits for the current IPU command (a0 = mpeg context): it polls IPU_CMD / IPU_CTRL and, every 5000
// polls, calls the application's callback (0x370430), which feeds more bitstream to the IPU. Our IPU decodes as
// soon as it is polled, so a command still busy after a poll is waiting for data, and the 5000 slow register
// reads in between only cost time (movies ran at a quarter of their speed). The PAL port's hle_mpeg_wait
// (JackyPendrag0n/ae2-recomp) calls the callback straight away. A C++ loop cannot yield to the other guest
// threads (the callback's data comes from them), so this is the recompiled function itself - a copy of the
// generated sub_00374558 - with the poll limit 5000 (slti 0x1389) lowered to 1. Same frame and resume points
// (0x3745b8, 0x3745cc), so a yield inside it resumes here. APE2_MPEGWAIT=0 keeps the original.
//
// Regenerate the body if the recompiler's output for 0x374558 changes (tools: copy sub_00374558_0x374558.cpp,
// rename, change 5001 to 1).

#include <stdexcept>
#include "ps2_runtime_macros.h"
#include "ps2_runtime.h"
#include "game_overrides.h"
#include <ps2_recompiled_functions.h>
#include <ps2_recompiled_stubs.h>

#include "ps2_syscalls.h"
#include "ps2_stubs.h"

#include "runtime/ps2_ipu.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>

namespace
{
void ape2_mpeg_wait_fast(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
#ifdef PS2_FUNCTION_LOG_TRACKER
    PS_LOG_ENTRY("sub_00374558_0x374558");
#endif

    switch (ctx->pc) {
        case 0x3745b8u: goto label_3745b8;
        case 0x3745ccu: goto label_3745cc;
        default: break;
    }

    ctx->pc = 0x374558u;

    // 0x374558: 0x27bdffc0  addiu       $sp, $sp, -0x40
    ctx->pc = 0x374558u;
    SET_GPR_S32(ctx, 29, (int32_t)ADD32(GPR_U32(ctx, 29), 4294967232));
    // 0x37455c: 0x3c021000  lui         $v0, 0x1000
    ctx->pc = 0x37455cu;
    SET_GPR_S32(ctx, 2, (int32_t)((uint32_t)4096 << 16));
    // 0x374560: 0xffb20020  sd          $s2, 0x20($sp)
    ctx->pc = 0x374560u;
    WRITE64(ADD32(GPR_U32(ctx, 29), 32), GPR_U64(ctx, 18));
    // 0x374564: 0x34422000  ori         $v0, $v0, 0x2000
    ctx->pc = 0x374564u;
    SET_GPR_U64(ctx, 2, GPR_U64(ctx, 2) | (uint64_t)(uint16_t)8192);
    // 0x374568: 0xffbf0030  sd          $ra, 0x30($sp)
    ctx->pc = 0x374568u;
    WRITE64(ADD32(GPR_U32(ctx, 29), 48), GPR_U64(ctx, 31));
    // 0x37456c: 0x80902d  daddu       $s2, $a0, $zero
    ctx->pc = 0x37456cu;
    SET_GPR_U64(ctx, 18, (uint64_t)GPR_U64(ctx, 4) + (uint64_t)GPR_U64(ctx, 0));
    // 0x374570: 0xffb10010  sd          $s1, 0x10($sp)
    ctx->pc = 0x374570u;
    WRITE64(ADD32(GPR_U32(ctx, 29), 16), GPR_U64(ctx, 17));
    // 0x374574: 0x282d  daddu       $a1, $zero, $zero
    ctx->pc = 0x374574u;
    SET_GPR_U64(ctx, 5, (uint64_t)GPR_U64(ctx, 0) + (uint64_t)GPR_U64(ctx, 0));
    // 0x374578: 0xffb00000  sd          $s0, 0x0($sp)
    ctx->pc = 0x374578u;
    WRITE64(ADD32(GPR_U32(ctx, 29), 0), GPR_U64(ctx, 16));
    // 0x37457c: 0xdc440000  ld          $a0, 0x0($v0)
    ctx->pc = 0x37457cu;
    SET_GPR_U64(ctx, 4, runtime->Load64(rdram, ctx, 0x10002000u));
    // 0x374580: 0x481001b  bgez        $a0, . + 4 + (0x1B << 2)
    ctx->pc = 0x374580u;
    {
        const bool branch_taken_0x374580 = (GPR_S64(ctx, 4) >= 0);
        ctx->pc = 0x374584u;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x374580u;
        // 0x374584: 0xdfbf0030  ld          $ra, 0x30($sp) (Delay Slot)
        SET_GPR_U64(ctx, 31, READ64(ADD32(GPR_U32(ctx, 29), 48)));
        ctx->in_delay_slot = false;
        if (branch_taken_0x374580) {
            ctx->pc = 0x3745F0u;
            goto label_3745f0;
        }
    }
    ctx->pc = 0x374588u;
    // 0x374588: 0x3c021000  lui         $v0, 0x1000
    ctx->pc = 0x374588u;
    SET_GPR_S32(ctx, 2, (int32_t)((uint32_t)4096 << 16));
    // 0x37458c: 0x34422010  ori         $v0, $v0, 0x2010
    ctx->pc = 0x37458cu;
    SET_GPR_U64(ctx, 2, GPR_U64(ctx, 2) | (uint64_t)(uint16_t)8208);
    // 0x374590: 0x8c430000  lw          $v1, 0x0($v0)
    ctx->pc = 0x374590u;
    SET_GPR_S32(ctx, 3, (int32_t)runtime->Load32(rdram, ctx, 0x10002010u)); // MMIO: 0x10002010
    // 0x374594: 0x30634000  andi        $v1, $v1, 0x4000
    ctx->pc = 0x374594u;
    SET_GPR_U64(ctx, 3, GPR_U64(ctx, 3) & (uint64_t)(uint16_t)16384);
    // 0x374598: 0x14600016  bnez        $v1, . + 4 + (0x16 << 2)
    ctx->pc = 0x374598u;
    {
        const bool branch_taken_0x374598 = (GPR_U64(ctx, 3) != GPR_U64(ctx, 0));
        ctx->pc = 0x37459Cu;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x374598u;
        // 0x37459c: 0x80102d  daddu       $v0, $a0, $zero (Delay Slot)
        SET_GPR_U64(ctx, 2, (uint64_t)GPR_U64(ctx, 4) + (uint64_t)GPR_U64(ctx, 0));
        ctx->in_delay_slot = false;
        if (branch_taken_0x374598) {
            ctx->pc = 0x3745F4u;
            goto label_3745f4;
        }
    }
    ctx->pc = 0x3745A0u;
    // 0x3745a0: 0x3c111000  lui         $s1, 0x1000
    ctx->pc = 0x3745a0u;
    SET_GPR_S32(ctx, 17, (int32_t)((uint32_t)4096 << 16));
    // 0x3745a4: 0x3c101000  lui         $s0, 0x1000
    ctx->pc = 0x3745a4u;
    SET_GPR_S32(ctx, 16, (int32_t)((uint32_t)4096 << 16));
    // 0x3745a8: 0x36312000  ori         $s1, $s1, 0x2000
    ctx->pc = 0x3745a8u;
    SET_GPR_U64(ctx, 17, GPR_U64(ctx, 17) | (uint64_t)(uint16_t)8192);
    // 0x3745ac: 0x36102010  ori         $s0, $s0, 0x2010
    ctx->pc = 0x3745acu;
    SET_GPR_U64(ctx, 16, GPR_U64(ctx, 16) | (uint64_t)(uint16_t)8208);
    // 0x3745b0: 0xa0102d  daddu       $v0, $a1, $zero
    ctx->pc = 0x3745b0u;
    SET_GPR_U64(ctx, 2, (uint64_t)GPR_U64(ctx, 5) + (uint64_t)GPR_U64(ctx, 0));
    // 0x3745b4: 0x0  nop
    ctx->pc = 0x3745b4u;
    // NOP
label_3745b8:
    // 0x3745b8: 0x28421389  slti        $v0, $v0, 0x1389
    ctx->pc = 0x3745b8u;
    SET_GPR_U64(ctx, 2, ((int64_t)GPR_S64(ctx, 2) < (int64_t)(int32_t)1) ? 1 : 0);
    // 0x3745bc: 0x14400004  bnez        $v0, . + 4 + (0x4 << 2)
    ctx->pc = 0x3745BCu;
    {
        const bool branch_taken_0x3745bc = (GPR_U64(ctx, 2) != GPR_U64(ctx, 0));
        ctx->pc = 0x3745C0u;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x3745BCu;
        // 0x3745c0: 0x24a50001  addiu       $a1, $a1, 0x1 (Delay Slot)
        SET_GPR_S32(ctx, 5, (int32_t)ADD32(GPR_U32(ctx, 5), 1));
        ctx->in_delay_slot = false;
        if (branch_taken_0x3745bc) {
            ctx->pc = 0x3745D0u;
            goto label_3745d0;
        }
    }
    ctx->pc = 0x3745C4u;
    // 0x3745c4: 0xc0dc10c  jal         func_370430
    ctx->pc = 0x3745C4u;
    SET_GPR_U32(ctx, 31, 0x3745CCu);
    ctx->pc = 0x3745C8u;
    ctx->in_delay_slot = true;
    ctx->branch_pc = 0x3745C4u;
    // 0x3745c8: 0x8e440858  lw          $a0, 0x858($s2) (Delay Slot)
    SET_GPR_S32(ctx, 4, (int32_t)READ32(ADD32(GPR_U32(ctx, 18), 2136)));
    ctx->in_delay_slot = false;
    ctx->pc = 0x370430u;
    if (!runtime->dispatchGuestBranch(rdram, ctx, 0x370430u, 0x3745C4u, 0x3745CCu, PS2Runtime::GuestBranchKind::DirectCall, "JAL")) {
        return;
    }
    ctx->pc = 0x3745CCu;
label_3745cc:
    // 0x3745cc: 0x282d  daddu       $a1, $zero, $zero
    ctx->pc = 0x3745ccu;
    SET_GPR_U64(ctx, 5, (uint64_t)GPR_U64(ctx, 0) + (uint64_t)GPR_U64(ctx, 0));
label_3745d0:
    // 0x3745d0: 0xde240000  ld          $a0, 0x0($s1)
    ctx->pc = 0x3745d0u;
    SET_GPR_U64(ctx, 4, READ64(ADD32(GPR_U32(ctx, 17), 0)));
    // 0x3745d4: 0x4810006  bgez        $a0, . + 4 + (0x6 << 2)
    ctx->pc = 0x3745D4u;
    {
        const bool branch_taken_0x3745d4 = (GPR_S64(ctx, 4) >= 0);
        ctx->pc = 0x3745D8u;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x3745D4u;
        // 0x3745d8: 0xdfbf0030  ld          $ra, 0x30($sp) (Delay Slot)
        SET_GPR_U64(ctx, 31, READ64(ADD32(GPR_U32(ctx, 29), 48)));
        ctx->in_delay_slot = false;
        if (branch_taken_0x3745d4) {
            ctx->pc = 0x3745F0u;
            goto label_3745f0;
        }
    }
    ctx->pc = 0x3745DCu;
    // 0x3745dc: 0x8e020000  lw          $v0, 0x0($s0)
    ctx->pc = 0x3745dcu;
    SET_GPR_S32(ctx, 2, (int32_t)READ32(ADD32(GPR_U32(ctx, 16), 0)));
    // 0x3745e0: 0x30424000  andi        $v0, $v0, 0x4000
    ctx->pc = 0x3745e0u;
    SET_GPR_U64(ctx, 2, GPR_U64(ctx, 2) & (uint64_t)(uint16_t)16384);
    // 0x3745e4: 0x1040fff4  beqz        $v0, . + 4 + (-0xC << 2)
    ctx->pc = 0x3745E4u;
    {
        const bool branch_taken_0x3745e4 = (GPR_U64(ctx, 2) == GPR_U64(ctx, 0));
        ctx->pc = 0x3745E8u;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x3745E4u;
        // 0x3745e8: 0xa0102d  daddu       $v0, $a1, $zero (Delay Slot)
        SET_GPR_U64(ctx, 2, (uint64_t)GPR_U64(ctx, 5) + (uint64_t)GPR_U64(ctx, 0));
        ctx->in_delay_slot = false;
        if (branch_taken_0x3745e4) {
            ctx->pc = 0x3745B8u;
            if (runtime->eeCheckpointDue()) {
                return;
            }
            goto label_3745b8;
        }
    }
    ctx->pc = 0x3745ECu;
    // 0x3745ec: 0xdfbf0030  ld          $ra, 0x30($sp)
    ctx->pc = 0x3745ecu;
    SET_GPR_U64(ctx, 31, READ64(ADD32(GPR_U32(ctx, 29), 48)));
label_3745f0:
    // 0x3745f0: 0x80102d  daddu       $v0, $a0, $zero
    ctx->pc = 0x3745f0u;
    SET_GPR_U64(ctx, 2, (uint64_t)GPR_U64(ctx, 4) + (uint64_t)GPR_U64(ctx, 0));
label_3745f4:
    // 0x3745f4: 0xdfb20020  ld          $s2, 0x20($sp)
    ctx->pc = 0x3745f4u;
    SET_GPR_U64(ctx, 18, READ64(ADD32(GPR_U32(ctx, 29), 32)));
    // 0x3745f8: 0xdfb10010  ld          $s1, 0x10($sp)
    ctx->pc = 0x3745f8u;
    SET_GPR_U64(ctx, 17, READ64(ADD32(GPR_U32(ctx, 29), 16)));
    // 0x3745fc: 0xdfb00000  ld          $s0, 0x0($sp)
    ctx->pc = 0x3745fcu;
    SET_GPR_U64(ctx, 16, READ64(ADD32(GPR_U32(ctx, 29), 0)));
    // 0x374600: 0x3e00008  jr          $ra
    ctx->pc = 0x374600u;
    {
        const uint32_t jumpTarget = GPR_U32(ctx, 31);
        ctx->pc = 0x374604u;
        ctx->in_delay_slot = true;
        ctx->branch_pc = 0x374600u;
        // 0x374604: 0x27bd0040  addiu       $sp, $sp, 0x40 (Delay Slot)
        SET_GPR_S32(ctx, 29, (int32_t)ADD32(GPR_U32(ctx, 29), 64));
        ctx->in_delay_slot = false;
        ctx->pc = jumpTarget;
        #if defined(PS2X_STRICT_RETURN_DIAGNOSTICS) && PS2X_STRICT_RETURN_DIAGNOSTICS
        (void)runtime->dispatchGuestBranch(rdram, ctx, jumpTarget, 0x374600u, 0u, PS2Runtime::GuestBranchKind::Return, "JR $ra");
        return;
        #else
        ctx->pc = jumpTarget;
        return;
        #endif
    }
    ctx->pc = 0x374608u;
}

    // The IPU's decoding is host work the EE clock was never charged for, so during a movie the emulated clock
    // (and vsync, and the movie's own timing) fell behind real time: movies ran at a quarter speed. Each burst of
    // IPU work is charged at the EE clock rate, as the EE would have waited that long on the PS2. APE2_IPU_CHARGE=0
    // disables it.
    PS2Runtime *g_ape2Runtime = nullptr;
    void ape2_ipu_charge(uint64_t ns)
    {
        if (!g_ape2Runtime)
            return;
        const uint64_t cycles = ns * 294912ull / 1000000ull; // 294.912 MHz
        g_ape2Runtime->eeCheckpointDue(static_cast<uint32_t>(std::min<uint64_t>(cycles, 0x7FFFFFFFull)));
    }

    void ape2_mpeg_wait_apply(PS2Runtime &runtime)
    {
        {
            const char *c = std::getenv("APE2_IPU_CHARGE");
            if (!(c && c[0] == '0'))
            {
                g_ape2Runtime = &runtime;
                ps2ipu::setChargeHook(ape2_ipu_charge);
            }
        }
        const char *e = std::getenv("APE2_MPEGWAIT");
        if (e && e[0] == '0')
            return;
        for (uint32_t pc : {0x00374558u, 0x003745B8u, 0x003745CCu})
            runtime.registerFunction(pc, ape2_mpeg_wait_fast);
        std::cerr << "[ape2:movies] libmpeg IPU wait without idle polls (APE2_MPEGWAIT=0: the original)" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-mpegwait", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_mpeg_wait_apply)

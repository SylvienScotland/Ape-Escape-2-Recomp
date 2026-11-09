# Work log

## 2026-10-29
- Project skeleton created (config template, plan, gitignore that excludes all game data).
- PS2Recomp (ran-j) built on Linux: `ps2_recomp` and `ps2_analyzer` OK.
- Runtime (`ps2xRuntime`) not built yet: cloud workspace can't install X11/GL headers
  (RandR, Xinerama, Xcursor, GL). Not needed until milestone 3; build on a desktop machine.
- Waiting on: main ELF from the USA disc.
- Got SLUS_206.85 (USA). Hashes in DISC.md.
- Analyzer (heuristic path, no Ghidra yet): 8453 functions, 548 SCE SDK matches,
  223 runtime stubs, 318 SDK funcs without handlers, 239 jump tables. Saved as config/ape2.toml.
- Recompiler: success, 8471 C++ files (173 MB, kept local only). 620 control-flow warnings,
  all "unresolved JR/JALR" (indirect jumps/calls) that fall back to runtime lookup.
- Syntax check vs runtime headers: 40/40 random sample OK; full pass hit timeout at 685/8471, 0 failures.
  Needed include dirs: ps2xRuntime/include, ps2xRuntime/src/lib/Kernel, ps2xIOP include, raylib/src.
- Next: Ghidra function export for better boundaries; full compile + link on a desktop machine.
- Ghidra: can't install in the cloud workspace (GitHub release downloads blocked by egress policy).
  Plan: run Ghidra + ExportPS2Functions.java on the desktop, commit the exported TOML/CSV to config/.
- Skipped Ghidra for now. Added tools/build_windows.ps1 + docs/BUILD_WINDOWS.md for the first
  desktop build/boot. PS2Recomp pinned at e5636981. Runtime uses the ELF's folder as cdrom0:,
  so the extracted ISO folder is the disc.
- First desktop build OK (MSVC 19.44, RTX 4070 Ti). ELF loads, execution starts at 0x100008,
  game calls SetupHeap(0x619ad8, -1) fine. Run was killed by the script itself: PS 5.1 + 2>&1 +
  ErrorAction Stop turns runtime stderr into a terminating error. Fixed: boot via cmd redirection.
  Added -RunOnly. /FORCE:MULTIPLE link warning is upstream's intentional raylib/WinAPI workaround.

## Boot 1: magenta screen, hang
- Window + raylib + audio OK. Magenta = runtime "no GS frame presented yet" placeholder.
- Hang: pc stuck at 0x36d3e0 (sceCdCallback), ra 0x1a1c38. Call chain: sub_001A1BC8 (startup,
  after sceCdInit) -> jal 0x1876A0 -> tail `j sceCdCallback`.
- Root cause: 68 of 223 analyzer stub bindings (`name@0xADDR`) were dropped because the recompiler
  had no function starting at those addresses, so 0x36d3e0 had no code at all. Missing set: most
  sceDma*, many sceVu0*, sceCdCallback/St*, sceMc*, sceMpeg*, sceSif* RPC/IOP, sceDeci2*, _printf_r.
- Fix: added the 68 addresses to `entry_points` in config/ape2.toml. All 68 now exist, but as the
  game's real SDK code (entry_* wrappers don't get stub bindings). Fine for pure code (VU0 math,
  sceCdCallback); DMA/SIF/MC ones may need runtime handlers later via overrides/.

## Boot 2: past sceCdCallback, stuck on FILEMAP.DAT
- Game now loops on sceCdSearchFile("\APE2_USA\FILEMAP.DAT;1;1") (800k+ retries).
- Root cause (runtime): stripIsoVersionSuffix only strips when everything after the first ';' is
  digits, so the doubled ";1;1" the game passes is never stripped and the lookup fails.
- Fix: patches/ps2recomp/0001-cd-strip-repeated-iso-version-suffix.patch (accept ';' in the suffix).
  build_windows.ps1 now applies patches/ps2recomp/*.patch idempotently after checkout.
  Worth upstreaming to ran-j/PS2Recomp.

## Boot 3: files found, IOP modules up, first GS writes; stuck in CD RPC bind
- FILEMAP.DAT;1;1 and SARU2.MM now resolve (patch 0001 works). IOP printf output visible, first GIF/GS reg writes.
- Hang at 0x36e448 inside sub_0036E3A8: SifBindRpc(0x8000059A) retry loop. Runtime has no IOP server
  for that SID (CDVDFSV lives in BIOS ROM; HLE routes only cover mcserv/libsd/dbcman), so bind never completes.
- 0x36E3A8 was unnamed by the SCE DB. Identified as sceCdDiskReady: called with mode 0 before every
  sceCdSearchFile in the game's file wrapper (0x187B00), returns 2/6, treats mode 8 as non-blocking.
- Fix: stubs += "sceCdDiskReady@0x0036E3A8" (runtime returns 2 = ready).
- Audit of other functions that call sceSifBindRpc directly:
  0x36DC40 (sid 0x80000595, CD N-cmd) and 0x36DF58 (0x80000593, CD S-cmd): no direct callers, only
  reached via stubbed sceCd*. 0x36BC00 sceDbcInit, 0x3A3B98 _lf_bind (loadfile), 0x1A1CD8 (game, ..6D69),
  0x37C2B0 (unnamed, ..646E): watch these if the next hang is in a bind loop.

## Boot 4: past disc checks, null handler call
- All 10 IRX modules load from disc (SIO2MAN, MCMAN, MCSERV, DBCMAN, SIO2D, DS1O x2, LIBSD, SNDN2DRV, IOPMISC).
- File table probe finds all movies/BGM/demo PCM. PUB.PSS / UBILOGO.PSS missing (PAL publisher logos), harmless.
- Second thread starts; it sits in sceMc state machine (0x378AE8, real SDK code).
- Main thread: [guest-branch:missing-target] JALR at 0x192a6c target=0 inside 0x1929E8.
  0x1929E8 walks an ordered list (built by 0x192840), reads entry type at +0x59, calls
  handler table 0x53B840[type].fn (+0x10). Table is .bss, 32-byte slots, 16-byte name key at +0.
  0x192618 = init (clears fn), 0x192728 = register(name, fn): key = 0x1A41B0(name) (128-bit),
  binds fn to the slot whose key matches (lq/pceqw/ppach/nor). Only caller of both: 0x18CA50.
- Checked MMI translation (POR/PCEQW/PPACH, operand order): correct.
- Next: overrides/ape2_trace_handlers.cpp logs init, every register (name, fn, slot count, bound?),
  and the table on the first runner call, to see if registration never runs, count=0, or keys never match.
- Trace result: register() is called (PROC_IMG, PROC_IDP, PROC_SOJ, PROC_ARR, PROC_AOD, PROC_SOD,
  PROC_LUP, PROC_EFO, PROC_EFF) but slot count = 0 every time -> nothing ever binds.
- Count comes from init: data = 0x1A28D8("FILEMAP.DAT") (lookup by name in loaded files, base [gp-0x454]);
  count = data+4, 16-byte slot names from data+0x50. So FILEMAP.DAT's in-memory copy reads as 0 entries.
- Load path: 0x187B68 -> 0x187948 looks FILEMAP.DAT up in the SARU2.MM index ([gp-0x790], loaded by
  0x187A80 via sceCdSearchFile + sceCdRead stub + sceCdSync), then sceCdSearchFile.
- Trace v2: also logs every sceCdRead (lbn/sectors/buf/mode + first bytes), the FILEMAP.DAT lookup
  result, and the raw bytes the table init reads.
- Trace v2 result: every sceCdRead has buf=0x0, and the heap handle [gp-0x454] is 0.
- Root cause: game heap init 0x1A3118 sizes its heap from end-of-bss 0x619AD8 to 0x1FA0000
  (bottom of a 384KB stack) and calls memalign(64, 0x1976528). The runtime caps the guest heap at
  0x1F00000 (SetupHeap/EndOfHeap; it keeps kRpcPacketPoolBase and async callback stacks at 0x1F00000+),
  so only 0x18E6520 is available -> memalign NULL -> allocator handle 0 -> every buffer NULL.
- Fix (interim): instruction patch 0x1a312c lui $v1,0x1FA -> 0x1F0, so the game asks for
  0x18D6528 (fits, ~64KB slack). Game gets 640KB less heap than on hardware.
  Proper fix later: move runtime-internal regions out of 0x1F00000-0x1FA0000 (e.g. into the
  kernel area below 0x100000) and let SetupHeap(-1) end at the main thread's stack base.
- Recompiler output verified deterministic (only sub_001A3118 changed). build_windows.ps1 now
  copies only changed generated files, so a one-function change rebuilds one unity batch.

## Boot 5: heap OK, reads by real disc sector fail
- Heap fix works: buffers non-null (0x659c40...), SARU2.MM loads (it's the game's file index:
  paths like /APE2_USA/MODULES/IOPRP243.IMG + real LSNs).
- FILEMAP.DAT is then read by its REAL disc LSN from SARU2.MM (0xCF4, 0x95 sectors), not the
  runtime's synthetic LSN from sceCdSearchFile (0x100017) -> "[sceCdRead] unresolved request", retried forever.
- Runtime already supports reading raw sectors from a configured CD image (IoPaths::cdImage), but
  nothing sets it. Added overrides/zz_ape2_cdimage.cpp: sets cdImage from env APE2_ISO;
  build_windows.ps1 -IsoPath sets the env var. Mapped (synthetic) LSNs are checked first, so name lookups are unchanged.

## Boot 6: FIRST PIXELS
- CD image override works (869280 sectors). FILEMAP.DAT read from LSN 0xCF4: header "FMAP", 10 entries.
- All 9 PROC_* handlers bind (slots 0-9). No more missing-target.
- Game streams ~20 gzip'd resources by real LSN into heap buffers.
- On screen: memory card check dialog ("Checking memory card ... slot 1"), then the publisher
  "presents" fade. Text looks doubled/ghosted (likely interlace field / GS presentation issue).
- Open questions: what happens after the presents screen (intro FMV = MPEG via FFmpeg?), memory card behavior,
  ghosted text.

## Boot 6b: stuck starting the intro movie
- After the presents screen: MC checks (GetInfo ok, Sync cmd=2 -> -4 = no save yet), sceSifSetDma,
  sceCdSearchFile(MOVIE\D1.PSS), 3rd thread appears, then main thread spins in 0x1895E0 (movie open).
- 0x1895E0 allocates an IOP stream buffer via sceSifAllocIopHeap (0x3A3920, runtime stub) of
  bufmax*2048+16 bytes, then loops on sceCdStInit(bufmax, bankmax, buf) until nonzero.
  Runtime sceCdStInit returns 0 if any arg is 0 -> most likely the IOP alloc returned 0
  (IOP reported only ~787KB free after modules). R5900 3-operand mult (rd write) verified correct.
- Trace v3: logs 0x1895E0 args, every IOP heap alloc (size -> addr), and sceCdStInit args/result.
- Trace v3 result: movie open('cdrom0:/APE2_USA\movie/d1.pss', 0x20, 0xc, 1) asks the IOP heap for
  0xC0010 (768KB) -> 0. sceCdStInit(0x180, 0xc, 0) then fails ~18M times (the "slow crawl").
  Earlier during boot two sound-bank IOP allocs also failed (0x1BA10, 0x6000).
- Cause: emulated IOP uses a fixed layout: modules below IopMemory::HeapBase=0x120000, heap
  0x120000-0x1F0000 (~832KB). Game modules end ~0x52000, so ~800KB is never usable.
  Game wants ~1.7MB of IOP heap in total (sound banks ~920KB + movie buffer 768KB).
- Fix 1: patches/ps2recomp/0002-iop-lower-heap-base.patch: HeapBase 0x120000 -> 0x70000 (~1.5MB heap).
  iop_memory.h is ps2xIOP-internal (not in the runner PCH), so cheap to rebuild.
- Fix 2: overrides/zz_ape2_iopheap.cpp: if the movie-buffer alloc (ra 0x189680) still fails, return a
  placeholder 0x200000. Runtime sceCdSt* is HLE and only checks buf != 0; it never touches that buffer.

## Boot 7: movie streaming starts, MPEG RAW8 unsupported
- IOP max free now 1527168 (was 806272); all sound-bank IOP allocs succeed; movie buffer -> placeholder;
  sceCdStInit OK first try; sceCdStStart(lbn 0x100017, 384-sector buffer); MPEG stream opened.
- Abort: "Unimplemented PS2 stub called: sceMpegGetPictureRAW8" from the movie thread (0x1A9118).
  Game decodes to RAW8 macroblocks and colour-converts on the IPU; runtime has neither RAW8 output
  nor IPU CSC (FFmpeg path decodes to RGBA for sceMpegGetPicture only).
- Movie thread: caller 0x1A4B78 opens d1.pss, CreateThread(0x1A4B08), StartThread. Decode loop 0x1A9118:
  RAW8 result checked with bgez; loop exits when 0x3702F0 (unnamed sceMpegIsEnd: *(*(mp+0x40))) != 0.
- Temporary: overrides/zz_ape2_skipfmv.cpp: RAW8 returns 0 and marks skip; IsEnd returns 1 once.
  Proper fix later: RAW8 output from FFmpeg frames (YCbCr macroblocks) + IPU CSC in the runtime.

## Boot 8: movie skipped, black screen
- Skip works ("movie #1 reported as ended"), no crashes for ~10 min, DMA still climbing, but the screen is black.
- Movie thread entry 0x1A90A0: after the decode loop it spins on [0x3DF5C0+0xC] != 0 before setting
  state 3 (0x1A8ED8(mp,3)) and ExitThread. 0x3DF5C0 = decoded-frame queue (0x1AA4E0 reset: +0xC count,
  +0x8 write idx; 0x1AA508 push: count++, slot state 3; slots 0x40540 bytes). The skipped empty frame was
  still pushed, never colour-converted, so never consumed -> count stays 1 -> main waits forever.
- Fix: skip override also zeroes +0xC and +0x8 when it reports the movie ended (same as 0x1AA4E0).

## Boot 9: IN-ENGINE 3D INTRO RENDERS
- Movie skip + frame-queue clear works: movie thread exits (activeThreads back to 2), game moves on into
  the in-engine 3D intro (radial speed lines / zoom). Real geometry, textures, blending. No errors.
- Very slow: DMA counter ~1 per 120-tick log line (was ~24 during boot screens) -> roughly a frame every ~2s.
  Hot PCs spread over game code (0x208B60, 0x353320, 0x29E928, 0x349440, 0x1C3430...).
- Not logging: boot.log stays tiny (logs are capped). Suspects: CPU-only GS backend (only gs_cpu_backend
  exists) rasterizing full-screen 3D, VU1 microcode execution, RelWithDebInfo build.
- Visual: picture shows 512x512 FB region with a duplicated band at the bottom (display rect vs 640x448),
  washed-out colors; earlier text looked doubled (likely interlace/field presentation).
- Next: per-frame timing instrumentation (EE vs GS backend vs VU) before optimizing anything.

## Perf instrumentation
- patches/ps2recomp/0003-perf-zone-profiler.patch: header-only exclusive-time profiler (src/lib/ps2_perf.h,
  not in the runner PCH). Zones: gs-raster (GSCpuBackend::Submit, synchronous DrawPrimitive),
  gs-front (GS::processGIFPacket minus raster), vu1 (VU1Interpreter::execute/run), vif1 (processVIF1Data).
  Frames counted in GS::latchHostPresentationFrame. Prints "[perf] ..." to stderr every ~2s;
  "other" = wall time outside all zones (EE game code, scheduling, waits).
- First perf results (boot screens): 9-22 fps, gs-raster ~86% with only ~800 draws/2s (~2ms per draw:
  large 2D sprites, slow per-pixel path). 3D intro: ~1 frame per 6-7s; per 2-3s window either
  {~38k draws, raster ~23%, vu1 ~17%, other ~60%} or {other ~99%}. Most 3D time is outside all zones.
- patches/ps2recomp/0004-perf-ee-wait-zone.patch: new zone ee-wait around EeScheduler pacing / idle
  waits, so "other" = EE game code + runtime overhead only. Build script now records applied patches in
  PS2Recomp/.ape2_patches_applied (0004 edits a file 0003 creates, which breaks reverse-check detection).
- ee-wait result: ~0% everywhere. "other" is real CPU time (EE game code / runtime helpers). 3D intro
  alternates {38k draws, raster ~22%, vu1 ~16%, other ~62%} and {nothing drawn, other ~99%},
  ~7s per frame. Suspect a guest busy-wait (polling a HW register/flag) that completes slowly here.
- patches/ps2recomp/0005-perf-guest-pc-sampler.patch: EeScheduler::publishDebugContext publishes &context.pc
  (generated code writes ctx->pc before every instruction); a detached sampler thread reads it every ~1ms
  and prints the top 12 guest PCs every ~2s as "[perf:pc] ...".

## Unattended perf runs
- Checked the user's PC: local repo was at d2c6774 (before 0005), perf.txt / boot.log there are the ee-wait
  run, so no `[perf:pc]` data exists yet.
- `[run:tick] pc=` histogram of the 3D intro is misleading: EeScheduler stores m_debugPc only when it dispatches,
  so samples sit on function entries and call-return points (0x19BD34 x13, 0x353320, 0x208B60...). The 0005
  sampler reads the live context (activeContext().pc; codegen writes ctx->pc before each instruction), so trust it.
- 0x19BCB8: per-frame loop, `do { v0 = 0x19BCE0(); } while (!v0); sceGsSyncPath(0,0)`. 0x19BCE0 is the
  main frame function (calls 0x19BF98, 0x1A0AD0, 0x1920F8, 0x1ADFE0, 0x26F938/0x26F5E8, 0x3530D0, 0x1C8510...).
- build_windows.ps1 -RunSeconds N: runs the game in a child cmd, kills ps2EntryRunner after N s, then runs
  tools/perf_summary.ps1 (boot.log -> perf.txt, ASCII; merged [perf:pc] ranking weighted by samples).
- tools/mdis.py: capstone disassembly of the ELF by guest address.

## Perf: IOP SPU2 AutoDMA was the 3D-intro bottleneck
- 0005 [perf:pc] result: hot guest PCs 0x192044 (sw D1_CHCR=0x145, VIF1 DMA kick) and 0x352f88/0x352eb8
  (4095-entry DMA ordering-table clear/link loops via uncached mirrors 0x2000_0000/0x3000_0000, which use
  the fast path). Those PCs only say *where* the guest was: the codegen sets ctx->pc to the loop head on every
  backward branch and calls runtime->eeCheckpointDue(), so runtime work done there is charged to that PC.
- patches/ps2recomp/0006-perf-host-stack-sampler.patch: the sampler thread also suspends the EE executor
  thread (single EeScheduler dispatch loop), unwinds its native stack (RtlLookupFunctionEntry/RtlVirtualUnwind,
  no allocation while suspended), symbolizes from the PDB with DbgHelp and prints [perf:host-self] /
  [perf:host-incl] every ~2s. New file ps2xRuntime/src/lib/Kernel/zz_ps2_perf_host.cpp (Kernel/ is globbed).
  perf_summary.ps1 merges them into perf.txt.
- Result: ~81% of slow-frame time = EeScheduler::checkpointDue -> IopEmulator::runCycles ->
  servicePendingDmaInterrupts -> IopIntrman::dispatchInterrupt -> callFunction -> IOP interpreter.
- patches/ps2recomp/0007-perf-iop-irq-stats.patch: [perf:iop] per-IRQ handler stats. Result: IRQ 40
  (0x28 = SPU2 core1 DMA) ~6000 calls/s x ~10.7k IOP instructions, never hitting its budget: the sound
  driver's 256-word AutoDMA stream block "completed" after transferWords*2 cycles (bus speed).
- patches/ps2recomp/0008-iop-spu2-adma-pacing.patch: if ADMAS (SPU2 core offset 0x1B0; bit0 core0,
  bit1 core1) is set for the core, the DMA completion waits 768 IOP cycles (36.864MHz/48kHz) per word.
  First try read offset 0x19A (that is CORE_ATTR) and slowed core0 bank uploads by seconds; fixed.
  Log: core0 bank uploads admas=0 (bus speed), core1 stream bcr=0x00100010 admas=0x2 delay=196608.
- After: "other" 60-99% -> 2-4%, IRQ 40 ~3 calls/s wall, 3D intro ~0.15 fps -> 0.5-1 fps.
  Now gs-raster ~50% (~38k-60k draws per frame) and vu1 ~45%. Host-self top: VU1 commitReadyPipelines,
  GSCpuBackend::DrawTriangle, lerpChannel, SampleTexture lambda, LookupCLUT, calculatePairReadyCycle.
- Running unattended from Claude: VsDevCmd.bat in cmd, then `powershell -File tools\build_windows.ps1
  -Ps2RecompDir C:\dev\PS2Recomp ...` with cmd doing the redirection (with -File, $PSScriptRoot is empty in
  param defaults; a PowerShell `*>` redirect turns CMake's stderr warnings into terminating errors).

## Picture: from garbled to a correct title screen
- patches/ps2recomp/0009-runtime-full-inlining.patch: RelWithDebInfo is /O2 /Ob1 on MSVC; /Ob2 for the
  ps2_runtime and ps2_iop libraries only (generated runner sources keep their flags, no full rebuild).
- patches/ps2recomp/0010-gs-frame-dump.patch: APE2_FRAME_DUMP=<dir> (+ APE2_FRAME_DUMP_EVERY=N, default 30,
  max 200) writes presented frames as PPM and prints [frame:dump] with the raw display registers;
  APE2_FRAME_DUMP_VRAM=1 also writes the 4 MiB GS local memory (vram_NNNN.bin).
- Display registers (AE2, all screens): PMODE=0x8063 (both CRTs, MMOD=1, ALP=0x80: anti-flicker merge of the
  same buffer with a 1-line offset), SMODE2 INT=1 FFMD=1, DISPFB FBP=0 FBW=8 (512 wide) CT32,
  DISPLAY DW=2559 MAGH=4 DH=895. Double buffer 0x0 / 0x70 (0x70 pages = line 448).
- patches/ps2recomp/0011-display-height-and-aspect.patch: DH counts half-lines here (895 -> 448 lines);
  the runtime used 896, clamped to 512 and read 64 lines of the other buffer (the "duplicated bottom band").
  Fix: honour MAGV; in interlaced frame mode halve heights above 576. Presenter now fits a 4:3 box (the PS2
  always outputs 4:3) instead of keeping the 512x448 source aspect.
- patches/ps2recomp/0012-gs-texture-cache-direct-read.patch: TexturePageCache copied one 8 KB page and was only
  invalidated on TEXFLUSH/reset (stale after uploads/render-to-texture) and cost an 8 KB memcpy whenever
  sampling alternated pages. Resolve now returns a pointer into VRAM.
- patches/ps2recomp/0013-gs-state-trace.patch: APE2_GS_TRACE=1 prints each distinct textured draw state
  ([gs:tex]), CLUT load ([gs:clut]) and image transfer ([gs:xfer]) once.
  Finding: AE2 uploads T8/T4 textures pre-swizzled as CT32 (e.g. 256x224 CT32 -> 512x448 T8, CSM1 CLUTs).
- patches/ps2recomp/0014-gs-integer-pixel-centers.patch: the GS samples at integer pixel coordinates (games
  supply the +0.5 texel offset: AE2 copies 0x70 -> 0x0 every frame with a bilinear sprite, uv 0.5..512.5).
  DrawSprite/DrawTriangle sampled at x+0.5 => half-texel shift => blur on every pass ("muddy" picture).
- Ground truth for the remaining garbled logos: SYSTEM\PUBLOGO.BIN is gzip -> "IDP/IMG/YIM" container,
  YIM 512x448 T8 at +0x50, 16x16 CT32 CLUT at +0x38050. Decoding it through a reference GS swizzle
  (scratch tool gsdecode.py, GS-manual tables) gives clean text, so the tables are right; the VRAM copy
  differed in 4769 bytes, every byte equal to the correct byte or the one 8 earlier: the whole upload
  stream was delayed by 8 bytes, starting with 00000000 50003800 = VIFcodes NOP; DIRECT 0x3800.
- patches/ps2recomp/0015-libc-memcpy-overlap.patch: (found on the way, separate bug) the memcpy HLE stub
  used host memcpy on overlapping ranges; the guest memcpy copies forwards (LZ-style propagation). Overlap
  with dst > src now copies byte-wise forwards.
- patches/ps2recomp/0016-vif1-direct-continuation.patch: the real cause. When a GIF IMAGE packet spans
  several VIF1 DIRECTs, processVIF1Data consumed the start of the *next VIF chunk* as image data, i.e. the
  DMAtag's VIFcodes (NOP; DIRECT n), shifting every such texture by 8 bytes. Now only DIRECT payload feeds
  PATH2 (pending IMAGE continues inside the next DIRECT payload), and a DIRECT cut off at a chunk end is
  resumed via a pending-DIRECT counter (file-static in ps2_vif1_interpreter.cpp to keep ps2_memory.h,
  which is in the runner PCH, unchanged). Logo texture now identical to the disc data (0 bytes differ).
- Result: memory card text, UbiSoft / SCE logos and the Ape Escape 2 title screen ("Press the START
  button") render correctly; the game reaches the title in < 150 s unattended.
- build_windows.ps1 now throws when the runner build fails (it used to boot the previous exe).

## Perf micro-optimisations (patch 0017): small gain, expensive rebuild
- patches/ps2recomp/0017-perf-raster-span-vu-commit-gate.patch: DrawTriangle walks only each row's covered
  span (edge equations, exact per-pixel test kept); lerpChannel without lroundf; VU1 commitReadyPipelines
  skips its scan before the earliest queued readyCycle (new member in ps2_vu1.h).
- Frames are pixel-identical to the previous build. Title screen still ~1 fps: DrawTriangle self 9.2% -> 6.1%,
  but the VU commit gate rarely skips (an entry is due almost every cycle).
- ps2_vu1.h is in the runner PCH: this patch cost a full rebuild of ~267 unity TUs = 30 minutes on this PC.
  Avoid PCH headers unless the change is worth it.
- Remaining cost is structural: software GS raster ~55-60% (LookupCLUT, SampleTexture, combineTexture) and the
  cycle-accurate VU1 interpreter ~35-40%. Real wins need a threaded GS rasterizer and native/recompiled VU1
  microprograms (the PAL port JackyPendrag0n/ae2-recomp does both; its docs are a design reference only, the
  repo has no licence, so do not copy its code).

## Controller: SIO2 + DualShock 2 emulation (patches 0018-0020), remappable Xbox layout
- AE2 does not use libpad: it loads the real SIO2MAN.IRX, DBCMAN.IRX, SIO2D.IRX, DS1O.IRX from disc (run in the
  IOP interpreter) and reads pads with libpad2 (scePad2*) + libdbc on the EE. Upstream only had a DBCMAN
  version-query HLE and no SIO2 hardware, so no controller ever answered.
- patches/ps2recomp/0018-sio2-dualshock2-pad-mapping.patch:
  - ps2xIOP core/iop_sio2.{h,cpp}: SIO2 registers 0x1F808200-283 (SEND3/SEND1/2, DATAIN/DATAOUT FIFOs, CTRL,
    RECV1-3, ISTAT), IOP DMA ch11/12, IRQ 17 via the scheduled-interrupt queue; DualShock 2 on port 0
    (0x40-0x4F protocol: read, config, set analog mode, model/act/comb/mode queries, vibration map, pressure).
    Others answer "no device" (RECV1 0x1D100). SIO2MAN starts transfers with CTRL=0x3BD: the FIFO-reset bits
    must not discard the queued command (first attempt sent empty commands).
  - include/ps2x/iop/iop_pad_input.h: PadInput + setPadInputSource(); the runtime registers its pad there.
  - ps2xRuntime ps2_pad.cpp: one mapping for both SIO2 and the HLE scePad stubs. Xbox defaults (A=cross,
    B=circle, X=square, Y=triangle, LB/RB=L1/R1, LT/RT=L2/R2 from the trigger axes incl. pressure, Back=select,
    Start=start, LS/RS=L3/R3, sticks analog) + keyboard; pad.ini (cwd, or APE2_PAD_CONFIG) is written with the
    defaults on first run and can be edited. First connected gamepad is used ("[pad] using gamepad 0: Xbox
    Controller"). APE2_PAD_SCRIPT="100-108:start;125-133:cross" holds controls (seconds since process start)
    for unattended tests; hold presses for several seconds at ~2 fps. APE2_SIO2_TRACE=1 logs the traffic.
  - Trace of the game's init: 42, 43 01 (config), 45, 46 00/01, 47, 4C 00/01, 44 01 03 (analog, locked), 4D,
    43 00, then 5-byte 42 reads in analog mode (ff 73 5a ...).
- patches/ps2recomp/0019-iop-vblank-handlers.patch: RegisterVblankHandler/ReleaseVblankHandler were no-ops;
  handlers are now delivered at vblank start/end edges (priority order, released when they return 0).
- patches/ps2recomp/0020-iop-sifsetdma-no-ownership-check.patch: "dbcman: sceSifSetDma faild" = sifman import
  32 (isceSifSetDma) was unimplemented; it now shares sceSifSetDma. The ownership check on the source buffer
  (guest must have written it before) was dropped (bounds check instead); failures and unknown sifman
  ordinals are logged.
- User confirmed START works on the title screen with a physical Xbox controller.

## Perf: row-parallel GS rasterizer (patch 0021) = 2x
- Large triangles/sprites (bbox >= 8192 px) are drawn by a worker pool (default min(cores-1, 8);
  APE2_GS_THREADS=N, 1 disables), 4-row blocks from an atomic counter; per-row code unchanged.
- Title / 3D intro: ~1.0 -> 1.9 fps. gs-raster 55-60% -> 15-21%; VU1 interpreter is now ~70% of the frame.
- Frames compared to the previous build: identical where the game state matches.
- patches/ps2recomp/0023-iop-sifsetdmaintr-callback.patch: the real blocker. sifman import 32 is
  sceSifSetDmaIntr(dmat, count, callback, arg): DBCMAN sends pad data with it and its completion callback
  (DBCMAN+0x2c0) does iSignalSema on the semaphore DS1O's port thread then WaitSema's on (DBCMAN+0x388). The
  callback is now queued (pendingGuestCallbacks, +256 cycles). Found with patch 0022 diagnostics:
  APE2_IOP_THREADS=1 (IOP thread table every 5 s: DS1O thread blocked on sema 4 at DBCMAN+0x390) and
  APE2_RPC_TRACE=1 (EE and IOP SIF RPC binds/calls; DBCMAN servers are 0x80000900 / 0x8000091b, the game
  calls 0x80000900 fn 0x8000091a every frame).
- Result: port 0 polled every frame; scripted START/CROSS reach the game (pad0 buttons=0xfff7 / 0xbfff);
  START leaves the title. Next: after START the game stops drawing, EE idle (all threads blocked), last disc
  read = 1-sector header at lbn 0x5b9f0 ("title", 0xbb80 = 48 kHz): likely the PCM/BGM stream start (IOP
  sound driver + CD streaming) blocks.

## Past START into the stage intro: missed functions, movie skip, IOP heap (0024, 0025)
- The stall after START was not the PCM stream. The title screen's state machine (switch 0x1BE2B8, table
  0x3EC338: 10 states x init/update/draw/exit) calls state 2's init 0x1BF048 through the table; the
  recompiler never registered it ("[guest-branch:missing-target] ... target=0x1bf048"), so the main thread
  stopped. Scanned the ELF for code addresses stored in data / built with lui+addiu that are not registered
  and not switch labels: 10 real entries, added to config/ape2.toml entry_points (resume entries inside the
  containing function, dispatched by `switch (ctx->pc)`). Cross-checked with the entry heuristic of the PAL
  port (JackyPendrag0n/ae2-recomp, recomp/elfinfo.py): one more, 0x205698.
- Build: PS2X_ENABLE_AGRESSIVE_LOGS=OFF. It logged every guest function entry to ps2_log.txt (500 MB/run).
- overrides/zz_ape2_movies.cpp (approach from the PAL port's hle_movie_start / hle_movie_bank_load, with the
  author's permission): movie start 0x1A4B78 reports the movie finished at once ([gp-0x3F8] = 3, the game's
  own end state written at 0x1A4B68); per-movie bank load 0x1A5968 -> [gp-0x3C0] = 0. APE2_MOVIES=1 keeps
  the originals.
- IOP heap: sceSifAllocIopHeap is a runtime stub, but sceSifFreeIopHeap (0x3A3A88) -> sceSifFreeSysMemory
  (0x3A3A10) ran the game's RPC, which never freed these blocks. zz_ape2_iopheap.cpp now frees 0x3A3A10 in the
  same allocator. The sound loader 0x1B73E0 allocates a temporary IOP buffer per bank and frees it.
- patches/ps2recomp/0024-iop-heap-first-fit.patch: IopMemory::allocate searched from a high-water mark, so
  freed blocks were never reused; now first fit from HeapBase, maxFreeMemory = largest real gap. New Game's
  stage bank (0x54D90 bytes) failed before this.
- Result: title -> menu (New game / Continue / Options) -> New Game -> "Go ape and capture 3 monkeys!" intro.
- Next stall: return into 0x200034, unregistered. The recompiler had made 0x200030 a function start (a data
  word 0x00200030 passed LooksLikeCallableEntry's short-tail-thunk check), cutting 0x1FFFE8 short in the
  middle; 0x200030 is a jal delay slot. patches/ps2recomp/0025-recomp-no-entry-in-delay-slot.patch: an
  address-taken start is rejected when it is a branch/jump delay slot or the return site after a call.

## Models were "a mess of shapes": the runtime's sceVu0* stubs (0026)
- patches/ps2recomp/0026-vu1-program-hash-and-verify.patch: APE2_VU_HASHES=1 logs each VU1 program (entry +
  hash of its reachable code, the PAL port's hash); APE2_VU_VERIFY=1 runs a reference of the skinned-model
  program (0x60) and the stage strip kernel (0x40 / 0x2360), adapted from the PAL port's vu1_native.c,
  on a snapshot of each batch and compares the GIF output with the interpreter's.
- All 12 VU1 programs the game runs have the PAL hashes: NTSC and PAL microcode are identical.
- The interpreter's output matches the references (only depth rounding differs), so VU1 was not the cause.
- config/ape2.toml stubbed 29 libvu0 functions (sceVu0MulMatrix, InversMatrix, CameraMatrix, RotMatrix*,
  ...) with the runtime's hand-written versions. Removed: the game's own recompiled code now runs. Stage
  scenery that drew as flat pink/grey now renders (statue, trees, fence, pillars); remaining: some thin
  streaks and shapes in the stage intro / near the camera, to check.

## Characters fixed: mistranslated MMI shuffles (0027)
- Logged the bone matrices the skinned VU1 program receives (APE2_VU_BONES=1): every row was (0, 0, 0, w).
  The VIF unpack copied them faithfully from EE RAM; a host write-watch (APE2_RAM_WATCH=<addr>[,bytes]:
  write-protects the host page, logs the recompiled function behind each store, zz_ape2_ram_watch.cpp)
  found the writer 0x349B90, which multiplies by the global matrix at 0x3DD300; watching that showed it
  stored with shuffled lanes ((0 0 0 1) (1 0 0 0) ...), built with MMI transposes.
- patches/ps2recomp/0027: 8 MMI lane shuffles were wrong, checked against the R5900 manual and the PAL
  port's port/include/mmi.h: PROT3W (w1 w2 w0 w3), PEXEW (w2 w1 w0 w3), PEXCW (w0 w2 w1 w3), PEXEH (h0<->h2),
  PEXCH (h1<->h2), PREVH (per 64-bit half), PINTH (rs upper halfwords), PINTEH (even halfwords). Fixed in
  the recompiler emitters and the runtime macros. Characters render correctly (user confirmed).
- Same patch, real fixes found on the way (not the character bug):
  - VIF1 UNPACK whose payload continues in the next DMA chunk was dropped; now carried over like DIRECT.
    Unpack rewritten with the hardware lane rules (as PAL vif.c): V2 writes x y x y, V3 reads a 4th
    component, V4-5 scales 5-bit channels (<<3, alpha 0x80), MODE 3, fill/skip cycles.
  - DMA addresses (tag ADDR, TADR, MADR) with bit 31 set mean the scratchpad; the bit was masked off and
    main RAM read instead.
  - VU0 microprograms ran with a 4096-cycle budget (longest seen 1187 cycles; raised anyway).
  - VU1 native programs (skinned 0x60, stage 0x40/0x2360) ported from PAL vu1_native.c behind
    APE2_VU_NATIVE=1 / verify (off by default until verify is clean: clip/Q of the past-end vertices differ).
  - Debug aids: APE2_VIF_TRACE=1 (unpacks into low VU1 memory + source), APE2_STORE_WATCH=<addr>.
- Lesson: compare with the PAL port first (its mmi.h would have shown the shuffles at once).

## Flicker and white/magenta washes fixed: VU random unit, FPU/VU0 edge cases, presentation (0028)
- Presenter: two guesses (show the source of the full-screen copy sprite; show a render target when the
  display buffer is black) showed the back buffer while the next frame was still being drawn. Now strictly
  DISPFB like the hardware / PAL port; APE2_DISPLAY_HEURISTICS=1 restores them.
- APE2_DRAW_LOG=<first vsync>,<count>: per vsync, every distinct draw state (target, prim, texture, alpha,
  test, fog, first vertex colour, rectangle). APE2_FRAME_DUMP_START=<n> starts dumping at presented frame n.
  The washes were full-screen additive glow sprites (ALPHA 0x48) with random-looking vertex colours.
- Differential test harnesses (tools/mmi_check.py, cop2_check.py, fpu_check.py): one generated statement per
  MMI / COP2 / FPU operation the game uses, run against the PAL port's reference semantics (mmi.h, vu0.h,
  ps2.h + its recomp.py decode) on random registers. MMI 29/29 match after 0027.
- patches/ps2recomp/0028:
  - VU0 random unit (game: ~2300 VRNEXT, 655 VRGET, 656 VRINIT): VRNEXT never wrote ft, VRGET returned the
    raw state instead of 1.0 + 23 random bits, VRINIT/VRXOR used invented mixing. Now the hardware LFSR (as the
    VU interpreter and PAL). This was the wash: the effects' flicker intensity came from VRGET.
  - PS2_FLOAT_MAX_BITS was 0x7FFFFFFF (a host NaN): now 0x7F7FFFFF like PCSX2/PAL.
  - CVT.W.S used nearbyintf (round to nearest); now truncates and saturates.
  - VDIV/VSQRT/VRSQRT use the PS2 helpers (zero divisor -> +-max, sqrt |x|); VRSQRT ignored fs (computed 1/sqrt).
- Result: stage intro plays with a stable picture. Open: two VDIV encodings still give Q=0 in the harness
  (decoded differently), VOPMULA/VOPMSUB MAC flags, NaN-pattern operands in FPU ops (PS2 treats exponent 255 as a
  number).

## Speed: VU1 microprograms compiled ahead of time (0029), ~2 fps -> ~35 fps in the stage
- The VU1 interpreter (cycle-accurate pipeline bookkeeping) took ~70% of the frame. The PAL port compiles every
  VU microprogram to C instead (its tools/vu_recomp.py); NTSC-U runs the same microcode, located 0x1500 bytes
  earlier in the ELF (one offset matched all 38 program hashes of PAL's recipe).
- tools/vu_programs.recipe (offsets into your SLUS_206.85 only) + tools/vu_recomp.py (PAL's generator, emitting
  C++) -> generated/output/zz_ape2_vu_programs.cpp at build time (build_windows.ps1; needs Python 3, otherwise
  the interpreter is used).
- patches/ps2recomp/0029: ps2_vu_compiled.h (PAL vu_impl.h state + helpers), Kernel/zz_ape2_vu_compiled.cpp
  (lookup by entry + hash, state hand-over with VU1State, XGKICK straight to PATH1, MXCSR round-to-zero/FTZ
  while running), hooked into MSCAL/MSCNT. APE2_VU_COMPILED=0 interpreter, =verify compare.
- Verify run (title -> stage, 200k program runs): VU memory, vi and vf15-31 identical to the interpreter;
  only scratch vf1-14 differ (past-end pipeline iterations, not read later).
- Now: ~35 fps in the stage; GS rasterizer ~50% of the busy thread, VU1 ~20%.
- 0029 extended: VU0 micro subroutines (VCALLMS) also run compiled (APE2_VU0_COMPILED=0 turns that off);
  verify now also compares every PATH1 packet (identical over 120k runs). GS: packed XYZ vertex Z went through
  float (24-bit mantissa), now double. Debug aids: APE2_GS_ZTEST_OFF=1 (all depth tests pass),
  APE2_DRAW_SEQ=1 (with APE2_DRAW_LOG: every batch in order with its depth range).
- Title screen: Jimmy and the monkeys are drawn (walking around, visible with APE2_GS_ZTEST_OFF=1) but the
  grass in front of them has larger depth (14.7M-19.8M vs ~5.7M) when the game runs fast; with the slow
  interpreter they show. Under investigation.

## FPU float ordering, depth precision (0030); title characters still hidden
- FPU compares, MIN.S, MAX.S: PS2 floats have no NaN/Inf, so exponent-255 patterns are just large numbers;
  the host compares called them unordered (false). Now ordered as sign-magnitude keys like the PAL port's
  fkey (recompiler emits FPU_MIN_S/FPU_MAX_S). FPU harness: compares/min/max match PAL.
- GS triangles: depth interpolated as a double-precision plane. Float barycentric weights were off by
  +-2 at depths ~2e7, so the title grass's second layer (GEQUAL against the first) failed on scattered
  pixels: the dotted lines on the title grass are gone.
- overrides/zz_ape2_camlog.cpp: APE2_CAMLOG=<first>,<count> logs camlook 0x19FEA0 (eye, target), as the PAL
  port's AE2_CAMLOG.
- Title: the kid and monkeys are drawn ~72 units below the camera target (bone matrices in view space,
  back-projected with the logged camera), i.e. under the hill; the grass hides them (not a compiled-VU or
  depth-test bug: identical in the interpreter). Next: why the title actors' height is wrong.

## Title screen: Jimmy and the monkeys back on the hill (0031 + overrides/zz_ape2_archive_name.cpp)
- Chain found with debug hooks (overrides/zz_ape2_camlog.cpp: APE2_CAMLOG, APE2_CAMFIND, APE2_CAMPEEK, APE2_RAYLOG):
  title actors ray-cast the ground from y=+40 to y=-40 (0x1C2E70 -> 0x1D3CE0) and stood at the miss value -40,
  under the hill; the static collision query (0x1D2D68) found no cells because the collision tree (gp+0x18F4)
  was empty; it is built from 'STAT_BSP' in the title stage archive TIT_A (0x1BE0B8), and that lookup missed:
  the name 'TIT_A' reached the slot lookup 0x1927B0 (full 128-bit compare) with a stray word (0x3F13CD35) in
  its upper 64 bits.
- Workaround (overrides/zz_ape2_archive_name.cpp): clear the bytes after the name's NUL before the lookup.
  Root cause of the stray upper half still open: not the scheduler between runs (APE2_REGCHECK=1), not the
  loader body or its callees, not the syscalls.
- patches/ps2recomp/0031 (recompiler; found on the way, checked against PAL vu0.h):
  - VU0 macro VSQI/VSQD had the address and data registers swapped; VLQI/VLQD/VSQI/VSQD/VILWR/VISWR addressed
    EE RAM instead of VU0 data memory (now runtime->memory().getVU0Data(), qword index & 0xFF).
  - VCLIP: +/- flag bits swapped and w not made absolute (now as the hardware / PAL V_CLIP).
  - Runner build: zz_ape2_* overrides excluded from unity batches (editing one no longer rebuilds a batch).
  - APE2_REGCHECK=1 (EE scheduler): reports a thread's s0-s7 upper halves changing while it is not running.
- Regression after 0031, fixed (0032): the stage hung after the "Go ape" screen in a monkey-placement loop
  (0x1C5930: random points until one lies in a box, test 0x2020C8). The VU0 random register R was stuck at 0
  (the game seeds it from EE timer 2, which our runtime left stopped at 0), so every point was the box's corner;
  the old swapped VCLIP bits had let that corner pass. Timers 2 and 3 now start free-running (mode 0x82) as the
  PS2 kernel leaves them, like the PAL port's rt_hw.c. Debug aid: APE2_BOXLOG=<n>[, APE2_BOXSKIP=<n>].

## Speed: decoded-texture cache in the CPU rasterizer (0033)
- Texture sampling (swizzled VRAM read, CLUT lookup, format conversion per texel) was ~45% of the frame.
  Textures are now decoded once into linear RGBA, lazily in 8x8 tiles, keyed by TEX0/TEXA and a hash of
  the palette contents (the game switches palettes on the same texture), and kept until a VRAM page they
  cover is written (per-page write epochs stamped in WriteVramUnlocked). APE2_GS_TEXCACHE=0 turns it off;
  APE2_GS_TEXSTATS=1 prints hits/stale/decodes.
- Title 10 -> 13-19 fps; gameplay in Liberty Island ~8 fps (now reached in the scripted run: Spike, HUD,
  pause menu). A/B frames with the cache on/off show the same pictures.
- Remaining cost: per-pixel combine/blend/raster loop (combineTexture, DrawTriangle row lambda, WritePixel).

## Speed: band-parallel rasterizer (0034)
- Only large primitives were split across threads; characters and stages are thousands of small triangles,
  so drawing ran on one core. Primitives are now queued and each raster worker draws all of them, but only
  rows with ((y >> 3) % n) == k (as the PAL port's gs.c bands), so per-pixel order is kept without locks.
  The queue is drawn before anything else touches VRAM (transfers, CLUT loads from a page being drawn,
  readback, clears, presentation) and when a primitive samples a page a queued primitive renders to.
  Decoded textures carry their own palette copy. Pool default up to 16 threads; APE2_GS_BANDS=0 = old path.
- Title 13 -> 25-34 fps, gameplay 8 -> 15 fps; the GS thread is no longer the limit in gameplay (19%).

## Speed: fewer, asynchronous raster batches (0035)
- Batches were drawn after almost every primitive (APE2_GS_FLUSHSTATS=1: why and how big): TEXFLUSH writes,
  texture-cache slot reuse, and texture uploads into pages the queue samples (the game streams textures through
  the same VRAM). Now: TEXFLUSH does not draw the queue (page epochs keep textures coherent); a stale or evicted
  texture still used by the queue keeps its data and the new decode takes another slot (1024 slots, hash index);
  an upload into pages queued primitives only sample decodes those textures first instead of drawing the queue.
  ~2500 primitives per batch instead of 1.
- Batches are drawn asynchronously: the raster workers draw batch N while the EE thread queues batch N+1; it
  waits only on a real conflict (render-to-texture, uploads/transfers/CLUT loads touching pages in use, readback,
  presentation). The scripted run now gets much further into Liberty Island in the same time (catches George
  and Cruiser); gameplay 15-25 fps.
- Next: the EE thread still runs VIF1 + VU1 (~25%), the GS front end (~40%) and the game (~20%) in series.
- 0036: each decoded texture keeps a private copy of the raw VRAM pages it covers (taken when it is (re)decoded,
  typically 32-64 KB), and the raster workers decode from that copy. Texture uploads into pages that queued or
  in-flight primitives sample no longer wait for the raster (the EE thread had spent ~28% there).
  Gameplay ~30 fps; the scripted run plays through the first stage into the Travel Station.
- 0037: raster workers skip primitives that do not reach their row bands before any setup; texture page ranges
  are exact for page-aligned textures (fewer false render-to-texture drains: 15.8k -> 4.2k per run).
  Title 33-40 fps. Gameplay 21-32 fps depending on the area; on the EE thread VIF1+VU1 is now the largest
  share (~36%), the game ~24%.

## Speed: hand-written VU1 programs from the PAL port (0038)
- Kernel/zz_ape2_vu1_native_pal.cpp: the PAL port's vu1_native.c (skinned models 0x60, stage strip kernel
  0x40/0x2360, backface pass 0x50) on our compiled-VU state (same layout as its vu_impl.h); the compiled-program
  chain calls them first and falls back to the compiled program when they decline (as PAL's vu1_chain).
  APE2_VU1_NATIVE=0 turns them off. VIF1+VU1 on the EE thread ~36% -> ~20%.
- Title 39-42 fps, gameplay 20-33 fps; the scripted run clears Liberty Island ("Stage cleared").
- 0039: VRAM page write epochs are stamped once per batch (its target pages), transfer rectangle, clear or
  single write, instead of per pixel (VramPageOf with divisions in every pixel write). Gameplay 27-35 fps,
  Travel Station 40-43. The EE thread is now ~1/3 game, ~2/3 GS front end + VIF1/VU1 + raster submit/waits:
  next is running VIF1/VU1/GS on their own thread (as the PAL port's MTVU).

## Saving (0040)
- Saving left a 0-byte BASLUS-20685/BASLUS-20685 and the save menu hung. Log (every memory card command is now
  printed): mkdir ok, open -> fd 5, then the game wrote to fd 0 (-4). The game's card worker takes the fd from
  sceMcSync, and our libmc kept one "last command" result: the game's GetInfo poller ran a command between the
  save's open and its sync and replaced the result with its own 0. libmc runs one command at a time; a command
  issued while another awaits sceMcSync is now refused (-1), so the poller retries later.
- 0041: the real cause: the save code (0x21BC20) writes to and closes fd 0 without using the descriptor its
  open returned; libmc hands out the lowest free descriptor from 0, ours counted up from 1. Now lowest free from 0.

## Root cause of the stray upper halves: MOVN/MOVZ (0042)
- APE2_CALLCHECK=1 (dispatchGuestBranch) reports calls that return with the upper 64 bits of s0-s7/fp changed.
  It found libc's __sfvwrite (0x39A550) putting string bytes into the caller's s0: `movn $s0, $s2, $v0` was
  translated as a 128-bit move. On the R5900 MOVN/MOVZ write the lower 64 bits only (as PCSX2). This was the
  stray word in the title archive name (TIT_A -> no collision, actors under the hill) and the 0x64 "mode" in
  the save request (last save file opened read-only, final write -5). Zero reports after the fix.
- overrides/zz_ape2_archive_name.cpp (the title workaround) is no longer needed; kept for now (harmless).

## GS worker thread (0043)
- After the PAL port's MTGS/MTVU: GIF and VIF1 DMA data is copied at kick time and processed on one worker
  thread (VIF1, VU1 programs, GIF, GS front end) in kick order. The EE waits for it (syncGsWorker) before
  VU1 memory, VIF1/GIF registers, VIF1 FIFO and the sceGs* stubs that write the GS. APE2_MTGS=0 disables it;
  APE2_MTGS_STATS=1 prints worker load and EE waits per reason every 5 s.
- Title 40 -> 48-58 fps, gameplay 27-35 -> 38-50 fps. The worker is now ~96% busy in gameplay (VIF1/VU1 ~1/3,
  GS front end + raster submit ~2/3); the EE waits on VIF1 register reads (sceGsSyncPath) about half the time.
  Next: split VIF1/VU1 and the GS front end onto two threads (PAL does), and avoid the per-frame VIF1_STAT wait.

## GS thread and one frame of pipelining (0044)
- APE2_MTGS=2 (default with 4+ cores): the worker runs VIF1/VU1 only; the GIF packets reaching the GS go in
  batches to a second thread that runs the GS front end (PAL's MTVU + MTGS layout). Alone this changed little:
  the EE waited for all drawing in sceGsSyncPath every frame, so the three threads took turns.
- sceGsSyncPath with the worker: puts a frame mark in the queue and waits only for the previous one (the EE
  computes frame N+1 while N is drawn). Display register writes (PMODE, SMODE2, DISPFB/DISPLAY 1-2, BGCOLOR) go
  down the queue in order and presentation uses those copies (GS::setDisplayShadow), so a swap never shows a
  frame before it is drawn.
- The EE also stays at most two vsync marks ahead of the GS thread (the load screen does not call
  sceGsSyncPath and ran ~2 s ahead, i.e. input lag, until this bound).
- Title/menus 45-58 fps; stages ~40-50, heavy full-screen effects 10-30. The GS thread is now the limit
  (~99% busy, mostly Submit waiting on raster batches: flush reasons 10 = 4096-primitive batch, 1 = texture
  page still being drawn).
- Note: APE2_GS_THREADS above 16 crashes when the title's 3D starts (reproducible; default 16 is fine).

## Vsync: no catch-up bursts (0045)
- The next VBlankStart's host deadline was always previous + 16.7 ms, so after a slow stretch the missed
  vsyncs fired back to back and the game ran visibly too fast for a moment (reported while playing). When more
  than a frame late, the next deadline is now "now" (the backlog is dropped).

## Profiling the GS and raster threads (0046)
- APE2_PERF_THREAD=gs|vu|raster points the host stack sampler at that thread instead of the EE;
  APE2_GS_BATCH sets primitives per raster batch (default 4096).
- Stage run: the GS thread spends ~50% waiting for the raster pool (26% at the barrier before each new batch,
  24% in drains for texture/CLUT/snapshot conflicts); a raster worker is idle ~53% and spends the rest in
  DrawTriangle/SampleTexture/WritePixel (generic per-pixel path). Batch size 4096 vs 16384: no clear change.
- The PAL port reaches full speed with its GPU renderer (gs_hw.h, OpenGL 3.3, 1x-8x resolution); its software
  rasteriser is also the slow path (hot spot: SSE span functions). Next: a GPU backend.
- Reported while playing: the camera shakes left/right a little in some areas (to investigate).

## GPU renderer (0047)
- Kernel/zz_ape2_gs_gl.cpp: the GS drawn with OpenGL 3.3, a C++ port of the PAL port's gs_hw.h/gl.h
  (JackyPendrag0n/ae2-recomp, with permission) behind the existing raster backend interface. Default;
  APE2_GS_RENDERER=cpu for the software renderer. APE2_GS_SCALE=N sets internal resolution (display still goes
  through VRAM at 1x for now). APE2_GL_TEXLOG=1 logs texture uploads.
- GSCpuBackend stays the owner of VRAM (transfers, CLUTs, texture decode); primitives go to GPU render targets
  batched by state. Coherence as PAL: targets read back before CPU reads of their VRAM; uploads pushed into or
  retire targets; textures at a target's address sample the target (render-to-texture). The GS thread reads back
  the displayed buffers at buffer swaps and vsync marks (GS::setDisplayShadow), so presentation is unchanged.
- The GS thread's context: a hidden GLFW window (raylib's GLFW) sharing the main context, created on the main
  thread after InitWindow; GL functions loaded with wglGetProcAddress.
- Palette textures are decoded with the palette built once (per-texel CLUT lookups were 2/3 of the GS thread).
- Stage run: median 59 fps (p25 56), from 49 with the software renderer; VU worker ~89% and GS thread ~85% busy.
  Confirmed in play: renders correctly; the sister's camera-filter effect now looks right.

## Game thread in the PS2's FPU mode (0048)
- The game thread now runs with round toward zero + flush-to-zero/denormals-are-zero, as the PAL port's guest
  threads (PCSX2's default "chop" mode); it ran in the host's round-to-nearest before. A first try at the
  camera shaking left/right in some areas. APE2_FPU_NEAREST=1 for the old rounding.

## Camera shake: frame-locked vsync (0049)
- Recorded with APE2_CAMLOG + APE2_RAM_WATCH (now with APE2_RAM_WATCH_STRIDE=<stride>,<off>,<len>,
  APE2_RAM_WATCH_LINES and the caller of store helpers named): the gameplay camera is slot 0 (0x4CBAF0, eye at
  +0x150), moved each frame by 0x272E40 (and corrected by 0x275BB8). With Jimmy standing still the eye ran a
  sawtooth whose period matched how often a frame took 2 vsyncs (every ~10th frame at ~54 fps, every 3rd at
  ~40 fps): the camera is moved by the vsyncs a frame took and overshoots at 2.
- EeScheduler holds a vsync until the game has finished the frame it started at the previous one (end of the
  stage frame 0x19BCE0, PAL 0x19CF28, marked by overrides/zz_ape2_frame_mark.cpp), at most four periods, and
  only while stage frames are running; a slow frame now plays slightly slower (as in the PAL port) instead of
  jumping. APE2_VSYNC_FRAMELOCK=0 disables it. (Marking at sceGsSyncPath did not work: 12 fps.)

## Camera snapping: SQRT.S read the wrong register (0050)
- Symptom: the camera snapped left/right while running, and every time with LB (recentre) facing a wall.
- Chase (with the player reproducing): the gameplay camera's yaw (+0x214, slot 0x4CBAF0) is re-measured each
  frame by 0x275BB8 from target-eye (atan2 via 0x1A2D50); logged next to the eye it came out mirrored about
  the angle straight behind Jimmy, so every correction overshot to the other side. 0x1A2D50's large-argument
  path uses the half-angle formula t/(1+sqrt(1+t^2)) with `sqrt.s $f1,$f1` (0x46010044, shown by the
  disassembler as `c1 0x10044`). The recompiler took SQRT.S's operand from fs; on the EE it is ft (as the
  PAL port's recompiler does): it computed sqrt($f0) = 1, and atan jumped by ~0.28 rad when its argument
  crossed infinity, i.e. whenever the eye passed right behind the player. 12 of the game's 17 SQRT.S used a
  different register in fs and ft and were all wrong. Fixed in fpu_translator.cpp; confirmed in play.
- Along the way (kept): the EE scheduler no longer round-robins equal-priority threads at the end of a time
  slice (the EE kernel only preempts for a strictly higher priority; APE2_TIMESLICE=1 restores it), and
  ape2HoldCheckpoints() lets a logging override run a hooked call to completion.
- Debugging tools in overrides/zz_ape2_camstep.cpp: APE2_CAMSTEP (eye change per camera step), APE2_CAMRAY
  (camera rays with real results; the hook finishes the collision walk 0x1CE7B0, whose recursion is compiled
  as a goto and returns through the scheduler), APE2_CAMDAMP=1 (the yaw damping tried before the fix);
  zz_ape2_camlog.cpp prints the slot's eye/target/yaw/distance.

## Garbage textures in the hub (keyboards) and level 1: investigation so far (0051)
- Tools: F9 in the game window (with APE2_FRAME_DUMP set) dumps the next 60 frames as burst_NNNN.ppm; during a
  burst the GPU renderer logs primitives over the keyboard area ([gpu:kb] texture, fingerprint of the decoded
  texels, [gpu:kbuv] ST/Q, [gpu:kbz] TEST/ALPHA/Z), every host->local upload ([gpu:up], [gpu:updata] with a
  hash of the uploaded data) and writes each distinct texture as tex_<hash>.ppm. APE2_PATH3_LOG=1 logs
  MSKPATH3 transitions; APE2_MSKPATH3=0 ignores MSKPATH3 (as PAL does); [vif1] reports a DIRECT that ends
  inside a PACKED/REGLIST GIF packet.
- Findings: garbage in both renderers (not the GPU path); the game never uses MSKPATH3; CLUT loading matches
  PAL; with APE2_GS_TEXCACHE=0 everything is garbage (the software rasteriser reads VRAM late), so the cache's
  page copies are needed. Textures are streamed into 0x2A00-0x4000 at a new address every frame, all uploads
  as CT32 (4/8-bit textures uploaded as 32-bit data); the Z32 buffer ends exactly at 0x2A00. In garbage frames
  the keyboard samples an atlas slot where its image was not uploaded: the game's texture streaming and our
  VRAM disagree. Next: trace the game's texture manager (which upload it expects before the keyboard draw).

## Garbage textures: VU1 deferral, DMA tag cap, probes (0052) - paused
- VIF1 MSCAL/MSCNT now run the VU1 program at the next sync point (FLUSH*, MPG, non-FLG UNPACK, end of data)
  instead of immediately (APE2_VU1_DEFER=0 restores immediate); helped the keyboard only partly.
- The DMA chain tag cap was raised from 4096 to 1<<20 ([dma] logs a chain over 4096; none were seen).
- Debugging: APE2_FRAME_DUMP_BURST_AT=<frame> starts a burst unattended, APE2_VIF1_LOG=1 logs VIFcodes during
  a burst, [gs:up]/[gs:kbd] logs, [gpu:tex0scan] searches guest RAM for the keyboard's TEX0.
- Measured with an unattended hub run (keyboard frames sampling a wrong slot, of ~58): baseline 31,
  APE2_TIMESLICE=1 46, APE2_VU1_DEFER=0 49, APE2_FPU_NEAREST=1 9 (slot changes 57 -> 9). The FPU rounding mode
  (0048) is the strongest lead: next, compare with how the PAL port sets rounding.


## Garbage textures: what the saved burst log already answers (0053)
- Re-read of the 60-frame hub burst in boot.log (33 MB: 89,859 textured draws over the keyboard area,
  294 distinct (psm, tbp0) slots), with tools/texture_log_scan.py:
  - The keyboard atlas is 4-bit, not 8: psm=0x14 (T4), 256x256, tbw=4, tbp0 in the streaming ring
    (0x2a00-0x3f00), palette 64 bytes (16 entries) at cbp, uploaded as an 8x2 CT32 IMAGE. The 256x256
    texture is uploaded as CT32 128x64 - the same 32 KB, byte for byte. The earlier "8-bit 256x256
    atlas" in 0052 is the 64x64 T8 case (1,672 draws), not the keyboard.
  - Every draw but 12 (of 89,859) follows a completed upload to the address it samples; the 12 are
    T8 slots (0x33c0, 0x3da0, 0x3360, 0x36a0). No draw samples an address nobody uploaded to.
  - One TEX0 over one upload content always decodes to one texhash (0 disagreements). Same VRAM bytes
    plus same TEX0 give the same texels, so the decode - including the per-texture CLUT snapshot of
    0033/0036 - is a pure function. Nondeterministic decoding, a stale CLUT and un-uploaded slots are
    ruled out as the cause of the remaining garbage.
  - The ring is reused across formats: 0x3f00 is the T4 256x256 atlas in some frames and a T8 64x64
    texture with a different palette (cbp=0x3f10) in others; 0x37e0 carries T4 64x64 (cbp=0x37e9) and
    T8 64x64/256x256. So an ordering error shows up as the *previous* texture in that slot, which a log
    of our own order cannot detect - the log only proves we are self-consistent.
  - Side note: m_clutVersion reached 252,419 by the burst, and the decoded-texture key includes a hash
    of the whole 512-entry palette, so every palettized texture misses (and re-decodes) whenever any
    palette is loaded. Worth measuring separately; it does not change the texels.
- Next experiment (blocked on playing into the hub): compare our order to the game's intent. The
  [gpu:tex0scan] probe found the game's own TEX0 words in guest RAM (tbp0=0x2ee0/cbp=0x3030 at
  0x5f0750, 0x5f0870, 0x6e09e0, ...), so at each keyboard draw we can read which descriptor the
  texture manager holds for that slot and whether the data it points at is the upload that just
  preceded the draw. That separates "right bytes" from "right bytes, wrong moment".

## (0054) Keyboard flicker: the texels differ, the palette does not

- `[gpu:kb]` now prints `raw=` (FNV-1a of the private copy of the source VRAM pages) and `clut=` (FNV-1a of
  the palette snapshot the texels were decoded with) alongside `texhash=`. Probe lives in
  `zz_ape2_gs_gl.cpp`, not yet folded into a patch file.
- Live captures at the hub keyboards (61 bursts). The two keyboards are `167,123-223,140` and
  `167,126-223,145`, both `psm=0x13` (T8), and both always draw the *same* texture in the same frame.
- Inside one burst that quad samples different content every frame: `a6ed86d2`, `55465426`, `8f3b6cdb`,
  `7b978bf5`. For all of them `clut=c13f915a` is identical and `raw` moves with `texhash`.
- Ruled out as the cause: texture LOD (`TEX1` only feeds `linearFilter`; `MIPTBP1`/`MIPTBP2` are decoded
  and never read, so every draw samples level 0) and palette-key aliasing (`m_clutHash` is zeroed inside
  `ClutVersionBump` whenever `m_clut` actually changes).
- Not a whole-area failure either: other quads in the same region keep a byte-identical texhash across
  dozens of different `tbp0` values, so the streaming ring does reproduce content correctly when a draw
  points at the slot it was written to.
- Conclusion: the keyboard draw reads VRAM whose texel content belongs to another texture that frame. The
  palette is not involved.
- Next: for that draw's `tbp0`, trace which `[gpu:updata]` writes covered its pages in the frames around
  the draw, to separate "uploaded after the draw" (ordering) from "the keyboard art was never written to
  the address the draw asks for" (bad address).
- Update after the page-writer probe (`serial`, `pageage`, `writer`, `mixed` on `[gpu:kb]`): the keyboard quads
  are NOT reading stale or wrong texture data. `174,134-222,139` (T4) decodes to the same
  `texhash=69b7178e / raw=dbd99ec4 / clut=9493857c` in every sampled frame across dozens of different `tbp0`, usually with
  `pageage=1..1 writer=1e50f6bb` (written one upload earlier), and in two frames where
  `pageage=69..60 writer=1c706911 mixed=1` it still decodes to the identical content. The T8 neighbour
  (`b2a140cd / bfb75393 / 8bf92551`, writer `c354faf9`, `pageage=1..1`) behaves the same way.
- So the flicker is not texture content and not upload timing. What is left is how those primitives are drawn:
  every burst shows the same screen quads carrying a T4 text layer and a T8 body layer, plus the translucent
  ghost copy seen in `burst1`. `[gpu:kbz]` already logs `prim/test/alpha/abe/z` for these draws but not the bbox,
  so the next probe is a bbox on that line to attribute a blend/depth state to a specific quad.
- Update after the `[gpu:kbz]` bbox probe: the keyboard rectangle is drawn **twice** with different state,
  one pixel apart. With the keyboards in view, `160,143-208,149` is drawn `prim=4 abe=0 alpha=0x44 test=0x50000`
  sampling the T4 atlas `69b7178e`, and `160,144-208,150` is drawn `prim=4 abe=1 alpha=0x1400000068 test=0x5b000`
  sampling the T8 atlas `aaf96689` — same quad, one opaque, one alpha-blended, offset by one pixel.
- The blended copy's alpha does not vary between frames (it is `0x1400000068` in every record), so the flicker
  is not an animated fade: it is a second, blended draw of the same geometry that should not be there.
- Both copies report `zbp=0xe0 zpsm=0x30 fbp=0x70`, so the duplicate is not coming from a different depth target.
- Remaining question for the next session: whether this second quad exists in the first-person capture too. If it
  disappears there, the guest suppresses it at close range and the bug is in how we honour that condition; if it is
  still drawn, the duplicate is emitted unconditionally and the fix is in the draw path.
- Correction: `burst N` on the `[gpu:kb]`/`[gpu:kbz]`/`[gpu:updata]` lines is NOT a burst index. It is
  `g_ape2FrameDumpBurst`, a countdown of the frames left in the current F9 burst (60, 59, ... 1). Every "burst 50"
  / "burst 56" reference above therefore means one *frame* of a single press, and the whole run above is two F9
  presses, not 59. Any future analysis must group by press, which means logging a press counter alongside this
  field, otherwise first-person and third-person captures cannot be told apart in one log.
- Probe bug found while trying to separate the two views: the first `press` counter was inserted *inside* the
  keyboard-region gate (`bx0 >= 160 && bx1 <= 240 && by0 >= 95 && by1 <= 150`), so first-person draws never advanced
  it. The result was a log where the frontend saw two F9 presses but every draw line still said `press 1`, and the
  countdown in that log never restarts (one continuous 60 -> 1 sequence, 12,155 keyboard draws over 60 frames), i.e.
  the log holds a single view, not two. The counter now sits above the gate (line ~1602, gate at ~1614) so every draw
  in a burst advances it.
- Consequence for reading these logs: a press is only separable by the countdown rising back to 60, so presses must
  be at least a full second apart (a burst is 60 frames) or the second one is absorbed into the first.
- Two-view comparison (press 1 third-person, press 2 first-person, `run_tex7.log`):
  press 1 = 1,544,808 draws over 92 textures; press 2 = 102,890 draws over 31 textures. The keyboard atlases
  appear in BOTH views, with the same states:
  `69b7178e` (PSMT4) is **always** opaque (`abe=0 test=0x50000`), and `aaf96689` (PSMT8) is **always** blended
  (`abe=1 test=0x5b000`), in third person (73,470 opaque / 225,026 blended) and in first person (11,072 / 36,476).
  So the blended pass is NOT gated by view or distance: it is emitted unconditionally. Whatever makes first person
  look correct is therefore not the presence of the second pass, and the fix must come from its state, not its
  existence.
- Correction to the earlier register reading: both copies have ZTE=1 with ZTST=2 (0x50000 and 0x5b000 both carry
  bits 16 and 18). The real difference is bits 12/13/15: `0x50000` has AFAIL=0, DATM=0, `0x5b000` has AFAIL=3,
  DATM=1. So this is a destination-alpha update difference, not a depth-test on/off difference. My earlier claim that
  the opaque copy draws with the depth test disabled was wrong.
- Also note `aaf96689` is a general 256x256 8-bit atlas (30,288 distinct bboxes in one 60-frame burst), not a
  keyboard-only texture, so texhash alone cannot identify the keyboard pass; geometry has to be used.
- Z-overlap test between the coincident opaque and blended copies (press 1 third person, press 2 first person):
  |dz| buckets for bboxes within 2px: press 1 has 794,371 such pairs (1751 with exactly equal z), press 2 has
  1,438 (341 exactly equal). Because coarse bbox proximity matches many unrelated sprites, this metric does not by
  itself prove z-fighting; it only shows that coplanar opaque/blended pairs exist and are far more numerous at
  distance, which is consistent with the keyboard copies collapsing together when they get small.
- The user confirmed the pale translucent panel in frame_0124 is legitimate scene geometry, so the artifact is the
  keyboard draw itself, not that prop. Next step is therefore an A/B test rather than another measurement: add an
  env-gated suppression of the second (blended) copy of a coincident quad and see whether the flicker disappears at
  distance. If it does, the duplicate is confirmed as the cause and the real fix can target its source.

### 0055 - Keyboard double-draw is an exact coplanar duplicate (pure, measured per bbox)

Capture: `run_tex8.log` (dumps/burst8, one F9 press, 410 frames, 1,810,177 keyboard draw records).
New probe output, new conclusions, and two corrections to 0054.

- **Launch path bug that silently ate a whole session.** `APE2_FRAME_DUMP` must be given with forward slashes.
  Launched from Git Bash with `C:\dev\...\burst8` the value reaches the runtime with the separators stripped
  (`frame:dump ... file=C:devApe-Escape-2-Recompdumpsburst8/frame_0061.ppm`) and every write fails silently: 107
  `[frame:dump]` lines, zero `.ppm` files. `APE2_FRAME_DUMP=C:/dev/Ape-Escape-2-Recomp/dumps/burst8` works. Always
  confirm the first `[frame:dump]` line shows a real path and that the directory is non-empty before pressing F9.
- **Correction: regex group map for `[gpu:kb]`.** The offsets are press 1, burst 2, bbox 3-6, tbp0 7, tbw 8, psm 9,
  cbp 10, cpsm 11, csa 12, tfx 13, rt 14, **texhash 15, raw 16, clut 17, serial 18, pageage 19..20, writer 21,
  mixed 22, clutv 23, epoch 24**. A first scan used 16/10/20-21/23 and therefore printed `cbp` as `psm`, `pageage_end`
  as `pages written`, and `clutv` as `mixed`; that table is wrong and is superseded by the numbers below.
- **The stale-page condition did not reproduce.** This run is `pageage=1..1` (421,089) or `0..0` (316,185) for the
  bulk of draws, with `mixed=1` on only 238,743 of 1,810,177 keyboard draws (13.2%). The `pageage=69..60 writer=1c706911`
  case from 0054 was a one-off, so upload history is not the mechanism.
- **Per-bbox pairing is decisive.** Grouping every keyboard draw by exact bbox and by depth triple, 1,847 bboxes are
  drawn in *both* blend states. Of those, **1,477 have an identical z triple set - the opaque and blended copies are
  the same geometry at the same depth** (pure duplicates), and 370 have different z (ordinary overlapping surfaces).
  **612 of the pure duplicates sample the keyboard atlas `69b7178e` (PSMT4).**
- Sizes are not slivers: the largest pure duplicates are thousands of pixels. `277,86-318,278` (7,872 px) is drawn
  102x opaque with `b2a140cd` (PSMT4) and 102x blended with `aaf96689` (PSMT8) - **exactly equal counts, i.e. both
  passes on every single frame**. Keyboard examples: `137,276-325,301` (4,700 px) opaque x178 / blended x178, and
  `186,249-374,272` (4,324 px) opaque x204 / blended x204.
- In the different-z class the blended count is exactly half the opaque count (204 vs 102, 168 vs 84), which is the
  signature of a genuinely separate pass, not a duplicate. The equal-count rule is what identifies the real duplicates.
- Reading: each quad is submitted twice, once through a 4-bit atlas with `test=0x50000` (`AFAIL=0`, `DATM=0`) and once
  through an 8-bit atlas with `test=0x5b000` (`AFAIL=3`, `DATM=1`). With `ZTST=2` (GEQUAL) the second submission passes
  the depth test at *equal* depth and overwrites the first, so the blended copy always wins the tie - deterministic
  per frame, and the reason the artifact is stable in place but changes as the quad slides across the depth ramp
  (at distance the two submissions rasterize to nearly the same fragment coverage and the winner becomes sensitive to
  sub-pixel rounding, which is the visible flicker).
- **Correction to the 0054 z-overlap note:** that measurement used bbox *proximity* (|dz| within 2px) and therefore
  matched unrelated sprites; its "794,371 pairs at distance, 1,438 up close" should no longer be read as evidence of
  any trend. Exact per-bbox z-set equality replaces it: 1,477 exact duplicates exist, full stop. The "far more
  numerous at distance" phrasing is withdrawn.
- Open question this does not answer: whether the two submissions differ in texture *pages* as well as formats
  (`b2a140cd` vs `aaf96689` are different atlases, so the 4-bit and 8-bit content are not the same image data), and
  which VU1 program issues each. That is the next probe if the A/B result points at pass suppression rather than
  at format selection.
- Next step stands: env-gated suppression of the blended submission for exact-coplanar duplicates, rebuild, judge the
  keyboards at distance. That is a decisive experiment either way - if the flicker survives it, the duplicate is
  exonerated and format/coverage becomes the suspect.

### 0056 - Keyboard duplicate is NOT back-to-back: the 0055 suppression never fired (A/B invalid, probe v2)

- **The 0055 A/B was a no-op, and the reason matters more than the result.** The live run with
  `APE2_KB_SUPPRESS=1` produced **0 `[gpu:kbsup]` lines** while an F9 burst was demonstrably active (`burst 11` in the
  same log), so the suppression never matched a single draw and the visual test tested nothing. The probe required the
  opaque twin to be the *immediately preceding* primitive.
- **Measured the real gap** (`tools/kb_adj.py` over the 1,810,177 `[gpu:kbz]` records of `run_tex8.log`, 687,506 of
  them blended): the nearest earlier identical opaque twin sits at **d=12 at the very closest; not one record at
  d=1..11**, and **95.9% (659,075) have no identical twin within 64 records at all**. The remaining 4.1% are spread
  thinly from d=12 to d=64.
- **Correction to 0055:** the "submitted twice back-to-back" reading was inferred from per-bbox *counts* being equal
  every frame, never from submission order. Equal counts only prove both copies are drawn in the same frame; the gap
  measurement shows they are separated by tens of other draws. The picture is an **opaque pass over the scene followed
  by a blended pass over the same geometry**, not a duplicated submission, and 0055's adjacency claim is withdrawn.
- Consequence for the mechanism: the equal-depth tie is still real (the two copies share an exact z triple and
  `ZTST=2`/GEQUAL lets the later one win), but it is a *pass-ordering* artifact, so nothing about it is fixed by
  order-adjacency heuristics.
- **Probe v2** (`tools/kb_sup_v2.py`): remembers every opaque quad submitted in the current frame in a 64-bit keyed set
  (bbox plus bit-exact z triple) and drops a blended draw that matches one. The frame boundary is the GL backend's
  `Present()` bumping a new `m_frameEpoch`; the cache clears whenever the epoch changes. Still env-gated by
  `APE2_KB_SUPPRESS`, and it logs `[gpu:kbsup] dropped blended dup bbox ... tbp0=0x%x psm=0x%x` during a burst so the
  dropped draws can be identified by atlas and format.
- Build note: build 61 failed with `error C2017: illegal escape sequence` because the emitted `fprintf` format string
  spanned two source lines; rewritten as one line and rebuilt as 62. Same lesson as before - verify the patched bytes
  with `cat -A`, do not trust how the patch script's source looks.
- Known risk of v2, and what the A/B is actually testing: a frame-scoped match is broader than the pair, so a *legitimate*
  blended overlay drawn at an identical bbox and depth as an opaque surface would also be dropped. If the hub looks
  correct the duplicate is confirmed as the cause; if unrelated surfaces lose their blended layer, the matcher needs to
  be narrowed to the keyboard atlas before it can be called a fix.

### 0057 - Probe v3: deny the equal-depth tie instead of dropping the draw

- Why v2 was the wrong lever: it *dropped* the blended draw. Two problems. Its key hashed the z values in vertex
  order while the two copies do not list their vertices in the same order, so the keyboard quads never matched - the
  40 logged drops were all `tbp0=0x2dc0`, never the keyboard atlas. And dropping geometry is only safe if the dropped
  pass is pure redundancy, which this measurement does not establish.
- v2 also ruled out the atlas theory it was chasing: `tbp0=0x2bc0` decodes to three different images
  (`69b7178e` blue fabric, `b2a140cd` marble, `efd4ae29` an actual keyboard on a table) at the same format, palette
  pointer and palette format. That is ordinary texture streaming into a reused atlas slot, not corruption.
- v3 keeps every draw and only changes the depth function of a coplanar blended twin, so it cannot overwrite the
  opaque copy at equal depth while geometry genuinely in front of it still draws. Enabled by `APE2_KB_STRICTZ=1`;
  the default path is byte-for-byte unchanged. Match key is bbox plus the three z values **sorted**, so vertex order
  cannot break the pair, and the cache is still scoped to one frame by `m_frameEpoch`.
- Instrumentation: `[gpu:kbdup] coplanar blended copy denied the depth tie bbox ...,tbp0=...,psm=...` during an F9
  burst, capped at 40 per thread, so the denied draws can be identified by atlas and format.
- If the keyboards stabilise but become consistently *wrong*, then the copy that was winning is the bad one and the
  remaining work is in that copy's texture path, not in the depth test. If they stabilise and look correct, the depth
  tie was the whole artifact. If they still flicker, the tie is exonerated and the cause is per-frame content.
### 0058 - Root cause found in the shared texture path: no mipmaps, so every minified surface aliases

- Both F9 captures after 0057 were unusable as evidence, and this was measurable rather than a matter of opinion.
  The chronic-change pass over `dumps/burst11` (59 consecutive frame pairs) found 12 pixels changing in 70%+ of pairs
  and 985 at 50%+, and the crop written from that bbox shows Ape walking up the hub ramp. `dumps/burst12` repeated it:
  the per-pair change bboxes move (`(140,0,454,383)` at frame 59, `(0,0,460,383)` at 54) while frames 52 and 57 are
  pixel-identical, i.e. the camera was still moving and the diff was the camera, not a flickering sprite. Cropping the
  single largest keyboard bbox of that burst (`33,268-256,447`, the same bbox reported under five different `tbp0`s)
  showed floor tiles and Ape's leg. Lesson recorded in 0056 and repeated here: a screen-space bbox is not an object.
- The four theories tested so far are all dead by measurement: adjacency pairing (0056), frame-scoped dropping (0057),
  the atlas arriving as different images (0057), per-frame texture or format alternation (0057), and the equal-depth
  tie (v3 fired on keyboards and the flicker persisted).
- What the probes could not do: `[gpu:kb]` and `[gpu:kbz]` are emitted under different conditions (1,087,211 vs 887,192
  records over the same burst), so the two streams cannot be zipped by index to ask "is this bbox drawn twice this
  frame at *unequal* depth". `tools/kb_dups.py` now verifies that alignment before analysing and aborts when it fails,
  instead of reporting zero.
- The cause is in the shared GL texture path, not in any one object. `applyAndDraw` selected its filter once -
  `const GLint f = s.bilinear ? GL_LINEAR : GL_NEAREST` - and applied it to **both** `GL_TEXTURE_MIN_FILTER` and
  `GL_TEXTURE_MAG_FILTER`, and nothing in the file ever called `glGenerateMipmap`, so uploads created level 0 only
  (`glTexImage2D`/`glTexSubImage2D` at the decoded-texture upload site). A texture drawn smaller than its own size -
  any distant object in third person - was therefore sampled from level 0 with no chain to fall back on. That aliases
  into shimmer/noise that cleans up as the camera approaches and is gone in first person, which is exactly the report,
  and it applies to every textured surface in the game.
- Fix, all at shared sites: added `GL_NEAREST_MIPMAP_NEAREST`/`GL_LINEAR_MIPMAP_LINEAR`, resolved `glGenerateMipmap`
  through the existing loader macro, generated the chain after **every** texel upload (textures stream into reused
  objects, so once at creation would go stale), and used the chain for minification only - magnification keeps the
  filter the GS asks for, and render-target textures are untouched so destination reads stay exact.
- Switch: `APE2_GS_MIPMAP=0` restores the old single-level sampling for an A/B on the same spot; unset or any other
  value enables it. Nothing here is per-object or per-atlas, which is the point: if this is the artifact, it is fixed
  for every texture bug of this shape at once, and `docs/LOG.md` stays free of per-keyboard hacks.
- Build 66 compiles clean (`error C`: 0) and runs at 50.5 fps versus ~52 before, on a 640x448 scene, so the chain cost
  is noise. Status: unverified against the artifact itself - it needs a look at the hub keyboards at distance, and the
  A/B via `APE2_GS_MIPMAP=0` is what decides it.
### 0059 - Build 66 was a black screen: the mipmap switch failed open, and only one of three texture sources has a chain

- Symptom: build 66 (0058) presented a **fully black screen**. Measured, not guessed - every dumped frame is
  `mean 0.0/0.0/0.0, non-black 0.0%`, from `frame_0000` on, while the renderer still reported ~40,000 primitives in
  ~692 draws per 600 displays and logged zero GL errors. Relaunching the same build with `APE2_GS_MIPMAP=0` rendered
  normally (`mean 127.5/123.8/169.3, non-black 100.0%`), which isolated the regression to the mipmap change.
- First hypothesis was wrong, and cheap to disprove: build 67 added `[gpu] mipmaps ...` / `mip chain built` logging
  plus a `glGetError` check. It printed `mip chain built for a 512x512 texture` with a clean error state - the chain
  was real - and the screen was still black. `glGenerateMipmap` resolves fine on the 4070 Ti; a missing entry point
  was not the cause.
- Actual cause: `s.tex` has three possible sources and only one is mipmapped.
  `cpuTexture()` decodes into a GL texture and regenerated the chain on every upload (the only one with mips).
  `texTarget()` binds the **render target itself** as the texture (render-to-texture: the hub is drawn this way).
  `m_snapTex` is a blit of the target being drawn into. The last two have level 0 only. Pointing
  `GL_TEXTURE_MIN_FILTER` at a mipmap filter for them makes the texture incomplete, and an incomplete texture samples
  **black** - so every surface drawn through render-to-texture went black at once.
- Fix (build 68): `s.texRt` already marks exactly the no-chain cases (set from the caller for `texTarget`, and the
  snapshot path arrives there via `tex == rt->tex`), so the filter now reads
  `(mipState() && !s.texRt) ? mipmap filter : the GS filter`. No new plumbing, and a texture can no longer be
  filtered from a chain it does not have.
- Hardening kept from 67: the decision is made once at init (`mipState()`), it defaults to **off**, and the generate
  site checks `glGetError` and turns itself off rather than drawing black. Fail closed, and say so in the log.
- Verified: build 68 presents normally (`mean ~123/120/167, non-black 100.0%`) at 52.5 fps versus ~52 before the
  change, so mipmapping costs nothing measurable. `APE2_GS_MIPMAP=0` still restores single-level sampling for A/B.
- Still unverified: whether this is what made the hub keyboards look wrong at distance. The screens are no longer
  black, which is the prerequisite; the keyboards need a look, and if they are still wrong the mipmap theory is
  ruled out by one launch with `APE2_GS_MIPMAP=0` rather than another probe build.
### 0060 - Mipmapping retired to opt-in: it does not fix the flicker and it erases alpha-tested foliage

- Test result from the user on build 68 (mipmaps on, nothing black): the keyboards **still flicker**, and the green
  landscape in the opening where Jimmy and the monkeys run **disappeared**. Both points are decisive, so the mipmap
  theory from 0058 is withdrawn rather than left standing.
- Why the landscape vanished: a mip chain averages alpha along with colour, so thin foliage that passes the alpha test
  at level 0 lands under the threshold at reduced levels and stops being drawn at all. That is inherent to mipmapping
  a GS texture whose alpha carries cutout, not a bug in the generation.
- Decision: `APE2_GS_MIPMAP` is now opt-in (`1` enables) instead of default-on, so the default path is unchanged from
  before 0058. The gate from 0059 is kept, `mipState()` still defaults to off, and the generate site still fails closed
  on a GL error. Frames verified after the change: `mean ~169/156/114, non-black 100.0%`, 51.5 fps.
- What this rules out for the keyboard artifact: minification quality. The keyboards shimmer at distance at level 0
  *and* with a full chain, so the cause is not undersampling and not filter choice. Everything from 0056 onward on
  this bug is now measured-ruled-out except the object's own draw state.
- The `[gpu:kb]` stream is not keyboard-specific and never was. `tools/kb_locate.py` and `tools/kb_repeat.py` over one
  burst frame show 15,514 textured draws, 11,820 distinct (bbox,tbp0) pairs, 71 distinct decode epochs, and only 13
  repeats of any single draw - it logs every textured primitive in the scene. Earlier claims that a key "matches the
  keyboard bboxes" were therefore matching the general textured-draw population, not keyboards. `tools/kb_locate.py`
  now selects by texture hash and crops the frame, which is the only reliable way to put a specific texture on screen.
- Tooling added: `tools/ppm2png.py` (real PNG crop/upscale - the earlier helper wrote PPM bytes under a `.png` name),
  `tools/ppm_mean.py` (frame brightness, which is what turned "black screen" into a measurement),
  `tools/kb_locate.py`, `tools/kb_repeat.py`, `tools/tex_sheet.py` (contact sheet of dumped textures: 89 in
  `dumps/burst12`, most recognisable - faces, sky, tiles, wood - and several rainbow/stipple ones still unexplained).
- Procedure incident, recorded because it changes the rules: `tools/cap_window.ps1` was written to screenshot the
  presented window, because every analysis so far has used VRAM read-backs and the artifact could in principle live
  only in the presented frame. The first version captured the window *rectangle* from the desktop while the game was
  behind a browser window, so it saved the user's web page. The file was deleted immediately and never read for
  content. The script now refuses unless the game window is verifiably the foreground window and captures only that
  window's client area. No desktop capture is run in the background or unattended.
### 0061 - The missing landscape was the STRICTZ tie-denial hack, not mipmapping

- Symptom after 0060 (mipmaps off by default): the green landscape in the opening was **still** gone, and the keyboards
  still flickered. So neither was mipmapping - and every launch since 0056 has set `APE2_KB_STRICTZ=1`, which rewrites
  the depth function of any blended draw whose bbox plus sorted-z triple matches an earlier opaque draw.
- Measured A/B on the same opening frames, same build (69), only the env var differing:
  `APE2_KB_STRICTZ=1` -> frame 40 `mean 126.4/123.8/169.3` (blue dominant, green level with red: the green landscape is
  absent); `APE2_KB_STRICTZ` unset -> frame 40 `mean 158.7/185.9/124.3` and frame 60 `161.1/187.8/120.7` (green channel
  far above red and blue: the landscape is there). Same frame indices, same cutscene, one variable.
- Why a keyboard matcher removes a landscape: its key is a screen bbox plus a sorted z triple, not an object identity.
  Any large blended overlay - grass layers, ground decals - that happens to share a bbox and depth with an opaque pass
  gets its depth function flipped to `GL_GREATER`, so it loses the pixels it should win at equal depth and disappears.
  That is the same "screen bbox is not an object" mistake recorded in 0056 and still being repeated, this time by the
  fix rather than the analysis.
- Decision: `APE2_KB_STRICTZ` stays unset for all normal runs and the default path is the untouched one. It is not a
  fix: it did not stop the keyboard flicker (user-confirmed across 0057-0060) and it removes landscape geometry. Any
  future tie work must key on object identity from the game's own draw state, never on screen-space coincidence.
- Running build for the user from here on: build 69, no `APE2_KB_STRICTZ`, no `APE2_GS_MIPMAP` - i.e. the unmodified
  depth and filter paths, so nothing this investigation added can be responsible for what is on screen.
### 0062 - The flicker is finally captured, from the presented window, and it is intermittent

- Why this took so long: every earlier capture was the VRAM read-back path (F9 frame dumps) taken while the camera was
  moving, so the artifact and the camera motion were inseparable. `tools/cap_watch.ps1` now records the *presented
  window* itself (foreground-verified, client area only) as pairs of frames 250 ms apart, and `tools/pair_diff.py`
  compares **within** a pair, which isolates what changes while the camera is not being moved.
- Clean result at a stationary hub view (`dumps/live2`, 9 pairs): **7 pairs are pixel-identical (0 changed pixels) and
  2 pairs differ**, with 5,536 and 2,305 changed pixels, mean diff 68.5 and 72.3. Identical pairs prove the camera and
  the scene were static, so the two differing pairs are the artifact, not motion. Intermittent - which matches
  "flickering" rather than "wrong texture".
- The change is localised, not global: `tools/pair_heat.py` ranks 16x16 tiles. The changed pixels form two vertical
  strips - x 64-95 spanning y 80-255, and x 384-415 spanning y 144-303 - centred on a large blue surface at the upper
  left and its counterpart across the scene. Zoomed 8x, the blue surface's shading bands and the bright band down its
  left edge shift between the two frames while the "Runtime Debugger" overlay and all static geometry stay identical.
- So the artifact is the appearance of a blended/semi-transparent surface alternating between two states at will. That
  is consistent with a destination-read or blend path that resolves differently on different frames, and inconsistent
  with texture decode (a decode bug would be constant, not intermittent) and with minification (ruled out in 0060).
- Second recording (`dumps/live3`, 15 pairs) had every pair differ with whole-screen bboxes and mean diffs of 76-161 -
  the camera was being moved, so that set cannot be used for rate measurement. Rule for next time: only within-pair
  diffs from rounds where *other* pairs are identical count as evidence.
- Tooling: `cap_watch.ps1` (records pairs while the game is foreground), `png2ppm.ps1`, `pair_diff.py`, `pair_heat.py`.
  The window capture is foreground-gated after the 0060 incident, so no other window can appear in a capture.

### 0063 - The burst from the second hub area contains no keyboards, and is motion-dominated

- User pressed F9 in a different part of the hub (build 69, no STRICTZ, no mipmaps, dump dir `dumps/burst18`):
  120 frames, 119 consecutive pairs, **9 pairs pixel-identical**. So the camera was still for only 9 of 119 pairs.
- The one pair with the largest change (burst_0059 -> burst_0060, 228,307 px) is a camera **cut**, not an artifact: the
  two frames are different locations. Any "worst pair" crop from this burst shows two different scenes and is
  meaningless - checked by eye before drawing conclusions this time.
- Chronic-change pass (numpy, per-pixel change frequency across all 119 pairs): max per-pixel frequency 70%, 1,332 px
  above 50% in bbox (34,143)-(339,322), mean diff 39.4. The highest-frequency 16x16 tiles sit on Ape's idle animation
  and on the bobbing red save-point phone, i.e. ordinary motion, not a flickering surface.
- Content of the view (cropped into six tiles for identification): Ape with a sword on grass, the red phone on its
  stand, a brick pillar with the four PS button glyphs, a gate and fence, trees, and a large yellow creature with three
  wooden discs. **No keyboards are visible in this view at all**, so this burst cannot be used to study them.
- Next capture must be two bursts of the *same keyboard*: one from close up (which is reported to render correctly) and
  one from the distance where it flickers, both with the camera still. Same object, same frame, one variable
  (distance) - that is the comparison every earlier attempt lacked.
### 0064 - The flicker is captured at the keyboards, and its signature is edge-only, not texture

- User clarification that changes the target: the artifact is **not one object**. The flicker appears on the ground,
  on background textures at spawn, and on the keyboards. The level transitions that looked like cuts in earlier bursts
  are normal and expected.
- The burst taken at the keyboards (`dumps/burst18` frames 0180-0239, 60 frames, 59 pairs) gives the first usable
  evidence, because 6 pairs are **pixel-identical**. Identical pairs prove the camera and the scene were static in that
  burst; therefore the pairs that differ are alternation, not camera motion. This is the rule from 0062 finally being
  applied in the right direction.
- Amplified diff of a median differing pair (`dumps/burst18/kb_diff.png`, diff x6): the change traces **edges only** -
  the ramp rails, the table edge, the window frames, the shelf outlines, the phone stand - while every surface interior
  stays bit-identical. Crops of the keyboards themselves (yellow slabs on the wooden table at right and the tall yellow
  column on the left, `kbtable_a/b.png`, `kbshelf_a/b.png`) are identical in that pair.
- Why that matters: a texture or decoder fault changes interiors (wrong palette, wrong bits, wrong dimensions). An
  edge-only change with identical interiors is a *geometric* difference - the same scene rasterised from a slightly
  different position. High-frequency textures (keyboard keys, ground detail) sampled at shifting sub-pixel positions
  shimmer, while close-ups barely change, which matches "wrong at distance, fine in first person".
- Checked the obvious code cause and ruled it out: `vert()` (zz_ape2_gs_gl.cpp ~1552) stores x/y as plain floats and
  nothing in the tree snaps or rounds them, but the inputs are the GS's own 12.4 fixed-point coordinates, so they are
  already multiples of 1/16 pixel - a missing snap would be a no-op, not a per-frame shift. So the shift is either the
  game's own camera motion (per frame, sub-pixel) or something in the GL backend's projection/viewport handling.
- Next split, and it is a one-launch binary: the **software renderer** (`APE2_GS_RENDERER=cpu`). Software and GL share
  the same GS state, VRAM and texture decode, and differ only in rasterisation. Flicker present in software -> the
  cause is upstream of rasterisation (GS state, transfers, VRAM); flicker gone in software -> the cause is in the GL
  backend's rasterisation/blend path. Running build: software renderer, `dumps/burst19`, 49 fps, frames
  `mean ~157/185/122` and 100% non-black, so it is rendering correctly.

### 0065 - Presentation path targeted: show a completed frame, not one still being drawn

- The decisive split from 0064 came back: the flicker is present with the **software renderer** as well. Software and
  GL differ only in rasterisation, so the cause is in code both share: GS state, transfers/VRAM, texture decode, or the
  presentation path. Everything this investigation had been changing (depth func, filters, mipmaps, probes) is now
  confirmed irrelevant to the artifact.
- Two hypotheses tested against the still-camera burst (frames 0180-0239) and **both disproven**:
  interlaced field presentation would alternate odd/even frames, so same-parity pairs (k, k+2) would match; measured
  opposite (same-parity median 9,546 changed px vs adjacent median 4,911, and 6 adjacent pairs perfectly identical),
  which is monotonic drift, not alternation. A whole-image 1-line shift does not explain the differences either
  (shifting by dy=-1 or +1 raises the change count from 9,458 to ~69,000).
- What is left in the shared path, and what this build changes: `UploadFrame` in ps2_runtime.cpp latches the display
  buffer on whatever tick the host loop happens to observe and uploads it immediately. If the game has already begun
  drawing the next frame into that same buffer, the presented pixels mix two frames. The file itself documents that
  exact failure: display heuristics were removed because presenting the back buffer "while the game was still drawing
  the next frame into it" made the picture flicker (patch 0028).
- Change (build 70): keep one frame of latency. The pixels uploaded now are the ones latched on the previous tick, so a
  half-drawn frame can never be shown. `APE2_PRESENT_DELAY=0` restores immediate presentation for A/B. Frames verified
  after the change: non-black, renderer line normal, fps within noise.
- Note for the next reader: ps2_runtime.cpp is CRLF. Patch scripts must read with universal newlines and write back
  with CRLF, or every anchor silently fails to match (this cost a build).

### 0066 - Compiled VU1 differs from the interpreter in ~70% of runs, but not in packet memory

- Ran the built-in verifier (`APE2_VU_COMPILED=verify`, build 70): `[vu1:compiled] verify: 106496 runs, 77285 differ
  (memory 0, vi/vf15-31 77285, only vf1-14 0)`. VU0 also differs: `[vu0:compiled] verify: 196608 runs, 376 differ`.
- Interpretation, and why this is NOT the flicker: `memory 0` means VU1 data memory - which is where the program builds
  its GIF packet, i.e. the vertex and register data actually sent to the GS - is byte-identical between the interpreter
  and the compiled path on every one of those runs. The differences are confined to `vi`/`vf15-31`, register state that
  no later program consumes without initialising it. So geometry, UVs and colours delivered to the GS are the same by
  both paths and the edge-only flicker signature cannot come from here. Recorded because the 70% figure looks alarming
  and the next reader deserves the reasoning, not just the number.
- Also found while looking: the GS dither bit and matrix are decoded into the draw state (`batch.state.dthe`, `dimx`)
  and then **never used** - a search for `dimx`/`dthe` in both zz_ape2_gs_gl.cpp and gs_cpu_backend.cpp returns nothing
  past the plumbing. That is a real gap (it causes colour banding, since the GS dithers before writing), but banding is
  static, so it is not this artifact either. Worth fixing separately.
- Open lead, and the reason to re-read 0057's evidence: the CPU backend captures a palette into `m_clut` and keys the
  decoded-texture cache on `m_clutHash`, and *both* renderers decode through that path. A palette captured one transfer
  late would decode an indexed texture with the wrong colours for that frame and then correct itself - intermittent,
  renderer-independent, worst on the densely textured distant surfaces (keyboards, ground). That also fits the old
  observation in 0057 that `tbp0=0x2bc0` decoded to three different images (`69b7178e`, `b2a140cd`, `efd4ae29`) at
  identical psm/cbp/cpsm/csa, which was filed as "ordinary streaming" - it is equally consistent with a stale palette.

### 0067 - Bypassing the texture cache makes every texture wrong: the direct texel path is broken

- `APE2_GS_RENDERER=cpu APE2_GS_TEXCACHE=0` (software renderer, textures sampled straight from VRAM per pixel) does not
  merely look different - the user reports "textures going nuts everywhere". That is a far worse result than the
  baseline artifact, and it is reproducible by flipping one variable.
- What that establishes: the direct path is `GSCpuBackend::ReadTextureVramUnlocked` ->
  `GSMem::ReadTexture(m_texturePageCache, m_vram, psm, tbp0, tbw, x, y)` (gs_cpu_backend.cpp:1147, called from the
  sampler's fallback at :1939). The decoded-texture cache is not an optimisation that merely saves time - it is currently
  the only thing producing correct textures. Any draw that falls back to the direct path gets the broken sampler, which
  is exactly the shape of an intermittent, per-surface artifact.
- So the earlier `APE2_GS_TEXCACHE=0` run under GL was doubly useless: there it produces *no texture at all*
  (`cpuTexture` returns 0 when `PrepareTexture` returns null, and `stateFrom` then draws the primitive untextured), so
  the GL result was flat colour, not a cache test. Only the software renderer can A/B the cache honestly.
- Code-visible bug found on the way, independent of the above: `LoadClutUnlocked` is only re-run when the CLUT *pointer*
  changes - the caller returns early on `m_clutCbp[0] == tex0.cbp` (around gs_cpu_backend.cpp:1023). A palette rewritten
  in place at the same `cbp` (routine for colour cycling and for streamed atlas palettes) is therefore never reloaded,
  and since the decoded-texture cache is keyed on `m_clutHash`, textures can be decoded with one palette and then
  another as the pointer happens to change and change back. That is a plausible generator of colour flicker on indexed
  textures and it is worth fixing regardless: the reload decision should also consider whether the VRAM pages under the
  CLUT have been written (page epoch), not just whether the pointer moved.
- Running build restored to the plain path (no TEXCACHE, no STRICTZ, no MIPMAP, GL renderer).

### 0068 - CLUT reload keyed on the VRAM page epoch instead of the pointer (build 71)

- Code-visible bug, fixed: `GSCpuBackend::LoadClut` returned early when `tex0.cbp` was unchanged (cld=4/5 paths), so a
  palette rewritten in place at the same address was never re-read. Palettes are rewritten in place routinely - colour
  cycling, and atlas palettes for textures that share one CLUT area - so indexed textures could be decoded with a
  palette that no longer matched VRAM. Because the decoded-texture cache is keyed on `m_clutHash` (the palette
  contents), the same surface could then decode with one palette and later another as the pointer happened to move and
  move back, which is colour flicker by construction.
- Change: `m_clutPageEpoch[2]` records the VRAM page epoch covering `cbp` at capture time (the palette lives in at most
  two 8 KB pages, `clutPage0`/`clutPage1`), and the early return now requires both the same pointer *and* the same page
  epoch. `ResetUnlocked` clears it with `m_clutCbp`. Cost: one extra atomic load pair per TEX0 write, and a reload only
  when the page actually changed.
- Verified: build 71 compiles clean (`error C`: 0); fps and frame content unchanged from build 70, so the extra reloads
  are not measurably expensive.
- Still unverified: whether this is the keyboard/ground flicker. It is a real defect either way, and it is the
  highest-probability remaining candidate that is *shared by both renderers* - which the software-renderer result
  requires the cause to be.
### 0069 - Audio: there is no SPU2, and the streamed blocks were being discarded (builds 72-73)

- Starting point: the port is silent and nothing in the tree synthesises SPU2 audio. The SPU2 region (`0x1F900000`)
  is a flat register map; an SPU2 DMA start schedules its interrupt and throws the block away. `ps2_audio.cpp`
  is a VAG-file heuristic behind `sid != 0x80000701` and never fires (no VAG decodes in any log).
- Added a capture tap rather than guessing: `APE2_SPU2_DUMP=<dir>` reads the block out of IOP RAM at DMA-arm time
  and appends it to `<dir>/spu2_coreN.bin`. First run: 18,327 blocks x 1024 bytes, every halfword `0000`.
- Disc data is genuinely there (ISO lbn `0x5ba26`, 2008/2048 nonzero bytes; `0x5b9f0` carries the `title` header
  with `0xBB80` = 48 kHz), and the EE streams it (`sceCdStRead` buffering 112 sectors), so the loss is downstream.
- Added `APE2_SIF_TRACE=1` traces in `sceSifSetDma` and `PS2Runtime::writeIopMemory`. Result: transfers do happen
  and none are rejected - a 445 KB payload lands at `0x83280` (the sound bank) and a repeating ring of
  `0x800`/`0x1000`-byte chunks lands at `0xc32c0`, `0xc3ac0`, `0xc4ac0`, `0xc52c0`. Nothing writes the ADMA buffer
  at `0x4be40` directly.
- Conclusion at this point: the PCM reaches IOP RAM, so the missing piece is output, not transport.

### 0070 - Audio: the stream is real music; the earlier "silent" reading was an analysis bug (build 74)

- Wrong measurement, corrected: peak +/-2 over the captured stream came from unpacking only the first 1 KB of the
  first non-zero block with the wrong element count, not from measuring the capture. Re-measuring every block
  properly: 13,451 of 20,576 blocks peak above 100, maximum peak 14,398 (~44% of full scale). The core1 ADMA
  stream carries actual music.
- Layout confirmed by measurement, not assumption: the loud block at 4,171 has adjacent-sample correlation 0.870
  and left/right correlation 0.870 with independent channel peaks (13,271 / 14,398), i.e. smooth interleaved
  16-bit stereo PCM.
- That matches the hardware pacing the emulator already models: `kAdmaCyclesPerWord` 768 cycles x 256 words per
  block = 187.5 blocks/s, and 187.5 x 256 frames = 48,000 stereo frames/s, the same 48 kHz the SPS header declares.
- Full IOP RAM snapshots (3 x 2 MB, `APE2_SPU2_DUMP` also writes `iopram_N.bin`) show the SIF-received ring at
  `0xc32c0` peaking at 31,974 while `0x4be40` reads all zero at arm time - the driver consumes ahead of where the
  register points, which is why tapping the register directly looked silent.
- Arm cadence is not the audio clock: 20,576 arms contain only 7,981 distinct block contents (12,595 re-reads), so
  playing one block per arm would replay roughly 60% of the music. Playback has to be driven by the 48 kHz clock.
### 0071 - Audio: SPU2 core1 streamed playback (builds 78-83)

- Goal: make the port audible at all. There is no SPU2 engine, so the streamed music (already proven to be real
  16-bit stereo PCM at 48 kHz reaching IOP RAM, entries 0069-0070) simply had nowhere to go.
- Wiring, in four small pieces:
  - `IopMemory` keeps a playback ring learned from the core1 auto-DMA arms and exposes `pullSpu2Pcm`, which hands
    out interleaved 16-bit stereo frames, wrapping at the ring end. One 4-byte frame per call is one 48 kHz sample.
  - `IopEmulator` and `IopSubsystem` forward the pull, so the runtime can reach it without owning IOP internals.
  - `PS2Runtime` pulls 800 frames per rendered frame (48000/60) and passes them to the backend.
  - `PS2AudioBackend::pushStreamPcm` feeds a raylib `AudioStream` (48 kHz, 16-bit, stereo) through a 2 s ring that
    drops the oldest frames on overrun, so a slow video frame cannot punch a hole in the music.
- Three playback models were tried; the first two failed for measured reasons and both are recorded here because
  the failures are the evidence for the final design:
  - Cursor follows each armed address: garbled. 12,595 of 20,576 arms re-read a block already played, so the
    cursor kept jumping backwards and the host repeated and skipped chunks.
  - Copy each armed block into a FIFO, skipping byte-identical re-arms: starved. Only ~28k frames/s of genuinely
    new content arrived against 48k needed, so playback was mostly gaps. It also showed the driver uses exactly two
    buffers, `0x4be40` and `0x4c240`.
  - Ring playback (final): the SPU2 auto-DMA ring is learned from the arms and walked with wrap, exactly what the
    hardware does. A distant arm restarts the ring, a nearby one grows it.
- Verified: build 83 compiles clean; the game runs at 57-60 fps with the WASAPI device initialized; the ring is
  measured at `base=0x0004be40 size=2048` (the 2 KB double buffer), which matches the two observed addresses plus
  one 1 KB block; and the wrap is seamless in the captured stream - mean sample delta across the wrap is 1974
  against 3199 at ordinary block joins, so the wrap introduces no discontinuity of its own.
- Not implemented, deliberately: SPU2 core0 voices and ADPCM decoding, so sound effects and voice banks stay
  silent; no SPU2 volume, pan or reverb registers; no ADPCM loop/interpolation. Playback reads the live ring, so a
  block rewritten while it is being read can tear for a few samples (inherent to reading the driver's buffers).
- Note on numbering: the code comments in these files label the work "0075"; the log continues from 0068, so the
  same work is 0069-0071 here.
### 0072 - Audio: shadow ring and ADMA pacing calibration (builds 84-86)

- Symptom after 0071: audible, but "more like noise than music". Listening test 2.
- Cause, measured on the captured stream: the driver produced blocks at ~228/s where 1024 bytes of 16-bit stereo
  lasts 5.33 ms (187.5/s), so the reader was ~22% slower than the writer and was reading the half of the 2 KB ring
  that was being rewritten at that moment. Reading memory mid-rewrite is broadband garbage, not quiet music. 7,209
  of 16,729 arms are byte-identical re-reads, which is why the earlier block-per-arm models starved or repeated.
- Fix 1, shadow ring: each armed block is copied into a 16 KB shadow at arm time and playback reads only the
  shadow, so no sample is ever read while it is being written.
- Fix 2, pacing: `APE2_SPU2_ADMA_CYCLES` overrides cycles-per-word at runtime, and a periodic `[spu2:lap]` line
  reports block refreshes per ring lap, which must be 2.0 for a 2048-byte ring of two 1 KB blocks. Swept:
  - 384 -> 4.15 per lap (writer laps the reader: overrun)
  - 768 -> 2.04 per lap (one refresh per block per lap: correct)
  - 934 -> 1.68 per lap (reader outruns the writer: stale replay)
  768 is the hardware figure (36.864 MHz / 48 kHz per stereo frame, halved per 16-bit word) and needs no
  correction, so an earlier 934 guess is reverted and 768 is the default. The earlier "22% fast IOP" inference came
  from arm counts alone and was wrong; the lap metric is what settled it.
- Verified: build 86 compiles clean; the game runs at 60 fps; the ring is learned as base 0x0004be40 grown to 2048;
  and armsPerLap holds at 2.04-2.11 over the run, i.e. every block is refreshed exactly once per lap with neither
  overrun nor stale replay.
- Still not implemented: SPU2 core0 ADPCM voices (SFX and voice banks stay silent), volume, pan and reverb.
- Tuning knobs added: `APE2_SPU2_ADMA_CYCLES` (pacing) and the `[spu2:lap]` / `[spu2:ring]` log lines.
### 0073 - Audio: waveform analysis and IOP throughput probes (build 87)

- Listening test 3: still bad. Stopped tuning playback and measured the audio itself instead.
- The captured stream is real music, not noise: spectral flatness 0.054 on the loudest block (1.0 = white noise),
  lag-1 autocorrelation 0.87-0.98, zero-crossing rate 3-12%, peak ~14,000, RMS ~3,500, and joins only slightly
  rougher than within-block steps (1,655 vs 1,249). Format and decode assumptions are therefore right.
- The defect is on the producer side: `block[i] == block[i+2]` for 3,039 of the first 4,000 arms, i.e. the driver
  re-arms each 1 KB slot far more often than it fills it with new audio. Any player reading that ring replays
  ~10.7 ms of music and buzzes - which is what three tuning iterations were hearing.
- Probes added in build 87:
  - `[iop:rate]` - IOP cycles executed per wall second against the hardware 36.86 MHz.
  - `[spu2:arm] fresh=/stale=` - whether an armed block differs from the shadow slot it replaces. A healthy stream
    needs ~187.5 fresh blocks/s.
- Measured `[iop:rate]`: 32.07 -> 31.94 -> 29.34 -> 27.78 MHz over one run, i.e. 75-87% of hardware and falling
  under load. That is a real deficit but only ~20%, so it does not by itself explain a producer refilling roughly a
  quarter as often as needed; the fresh/stale probe did not get a sample because that run never reached the music
  before it was stopped.
- Conclusion recorded here so the next attempt does not repeat the tuned-playback detour: the ring is being read
  correctly and the pacing is calibrated (0072), so what remains is making the driver refill at the rate the SPU2
  consumes - SPU2 block IRQ and internal double-buffer semantics, and whatever starves the producer - not another
  playback timing tweak.
### 0074 - Audio: output-level measurement, live-read and one-shot block playback (builds 88-91)

- Added `APE2_SPU2_PCM=<file>`, which appends the PCM actually handed to the device, and `tools/analyze_pcm.py`,
  which reports repeated-chunk rates and periodicity. Until now every conclusion came from the *source* blocks;
  this measures the emitted signal.
- First output measurement (build 88, ring-wrap playback): 98.4% of adjacent 512-frame chunks byte-identical,
  autocorrelation 1.00 at lag 64-68 frames. The device was being fed a frozen 2 KB window looping every 10.7 ms.
- Two structural changes followed, both now in the tree:
  - build 88: playback reads the ring from live IOP RAM instead of a copy taken at arm time (`APE2_SPU2_SHADOW=1`
    restores the old behaviour), because the shad-ow froze each slot at arm time.
  - build 91: playback consumes each armed block once, in arm order (`Spu2Queue`, 64 blocks, last frame held on
    underrun), because wrapping a learned ring replays the newest few ms forever.
- Measured after both (build 91, 26.4 s of audio): still 97.7% repeated adjacent chunks, and 2,475 chunks contain
  only **58 distinct** ones, each repeated ~40 times back to back. Playback order is now faithful, so the remaining
  defect is upstream: the driver supplies roughly half a second of distinct audio and then keeps re-arming the same
  contents.
- Supporting measurements:
  - `[spu2:arm]` (prints every 2,000 arms) never fired during the captured audio, so under ~77 arms/s against the
    187.5/s a 48 kHz stream needs.
  - `[spu2:lap] armsPerLap=0.01` in the same runs; earlier 2.04 was calibrated against arm count, not fresh content.
  - `[iop:rate]` 26.9-32.1 MHz against hardware 36.86 MHz, degrading under load.
- Status: audio is still broken. The playback side is now the least suspicious part of the chain. What remains is the
  SPU2 block-IRQ interaction that is supposed to make the driver refill: the driver must be told a block has been
  consumed at 5.33 ms intervals and must actually write new audio in response. That is the next thing to measure,
  not the ring reader.
### 0075 - Audio: the driver arming rate, measured finely (build 92)

- Lowered the `[spu2:arm]` / `[spu2:queue]` log thresholds from every 2,000 events to every 200 so a short run can
  report a rate, then ran 62 s with the PCM tap enabled.
- Result: fewer than 200 arms in the whole run - no `[spu2:arm]` line fired at all - while the tap captured 18.1 s
  of emitted audio containing only 36 distinct 10.7 ms chunks. `[iop:rate]` reported 26.9-32.1 MHz against the
  hardware 36.86 MHz over 30 samples.
- So the driver arms the SPU2 auto-DMA roughly a couple of times per second when it should arm 187.5 blocks/s
  (1 KB blocks at 48 kHz). The 2.04 arms/lap recorded in 0072 was an initial burst, not a steady state, and the
  earlier "fresh vs stale" question is moot: almost nothing is armed at all.
- What this rules out: the ring reader, the shadow copy, playback order, chunk sizing and the pacing constant. All
  of those are now faithful to what was armed, and the output still cannot be music because the stream is starved
  at the source.
- What it points at: the block-completion path that tells the driver a 1 KB block has been consumed. Without a
  per-block SPU2 interrupt at 5.33 ms, the driver has no reason to refill, so it does not. That is the next thing to
  implement - SPU2 core status/IRQ per block - and it is upstream of everything changed in 0071-0074.
- Status: audio still broken; current tree is build 92 with one-shot block playback and output tap instrumentation.
### 0076 - Reference check: the PAL port's audio path is no longer reachable

- Following up on the sound work, tried to read how the PAL port (JackyPendrag0n/ae2-recomp, cited throughout this
  log as a design reference) drives SPU2 audio, since its approach to the movie and VU1 paths was ported directly.
- It is not available: `api.github.com/repos/JackyPendrag0n/ae2-recomp` and the repo page both 404, the account's
  repo list is empty, GitHub repo search for `ae2-recomp` returns 0 results, and the Wayback copy refuses the
  connection. No local clone exists (searched Downloads, Documents, Desktop, OneDrive; `C:\dev` holds only this
  project and PS2Recomp).
- No audio is vendored from it here either: nothing under `overrides/` mentions spu2, and no branch or stash carries
  PAL audio work.
- Consequence for 0071-0075: the remaining question - how the sound driver is meant to be told a block was consumed -
  cannot be answered by comparison. It has to come from measurement, or from the PAL sources if a copy is supplied.
### 0077 - Audio: autonomous auto-DMA implemented, and the interrupt vector is the real suspect (builds 93-95)

- Implemented the autonomy hypothesis from 0076: once an auto-DMA block is armed, the per-block completion interrupt
  is kept scheduled without another CHCR write (`IopMemory::m_admaTimer`, queried by the emulator after each serviced
  DMA interrupt), and playback reads the ring straight out of IOP RAM again so refills are picked up live
  (`APE2_SPU2_SHADOW=1` keeps the old behaviour). ADMAS auto-bit clear stops the timer.
- Two patch attempts were lost to bad anchors before this worked; the third instrumented each edit, which is why the
  failed build 93 was silently the old code. Tools: spu2_adma_autonomous{,2,3}.py, spu2_auto_probe.py.
- Measured with the tap (build 95, 60 s run): no improvement - 5,659 chunks, 83 unique, 98.6% adjacent repeats,
  loudest-chunk spectral flatness 0.57. `[iop:rate]` 25.9 MHz.
- The instrumentation answered the important question, and it inverts the earlier conclusion:
  - `[spu2:auto] armed irq=40 block=196608 cycles (5.33 ms)` fired **89 times**: the driver does arm, steadily, at
    about 1.8 blocks/s. The timer is set every time and `stopped by ADMAS` never fired.
  - Yet `[perf:iop]` reports `irq 40: calls 2` against `irq 17: calls 44`. `dispatchInterrupt` only increments that
    counter when a handler actually runs, so vector 40 is being dropped - the guest has no handler on it.
- So the defect is the interrupt vector, not autonomy and not the reader: SPU2 core1 completion is delivered as 0x28
  (40), a number this HLE chose, while the driver's own handler is registered elsewhere. Without a delivery the
  driver never learns a block finished, refills about 90 times in a minute instead of ~11,000, and the ring stays
  static, which is the 10.7 ms loop measured since 0074.
- Next: log intrman registrations to see which vector the sound driver installs, then raise SPU2 completion on that
  vector instead of 0x24/0x28. 89 arms of 256 words each is 0.47 s of audio, exactly the amount of distinct output
  the tap keeps finding, which corroborates the whole chain.

### 0078 - Audio: the interrupt vector is right, and the driver still barely refills (builds 96-97)

- Instrumented intrman (`[intrman] register` / `enable` / `disable`, tools/spu2_intrman_probe.py,
  spu2_intrman_enable_probe.py) to test the vector hypothesis from 0077.
- It does not hold: the driver registers vector 40 (`handler=0x441f0 arg=0x46be8`) alongside 36 (core0, same
  handler) and 9, and it *enables* 17, 36, 40 and 9 - vector 40 twice. So raising 0x28 targets a real, enabled
  handler; the number this HLE chose was correct.
- Measured anyway (build 97, 55 s): the driver armed only **11** blocks and `irq 40: calls` stayed at 2 (against
  `irq 36: calls 4`). Delivery is therefore rare for a second reason: there is almost nothing to deliver, because
  the refill loop itself runs about 1-2 times per second instead of 187.5.
- Eliminated so far, with measurements rather than reasoning:
  - ring reader / shadow copy / chunk sizing / one-shot ordering - all now faithful to what was armed (0074-0075);
  - pacing constant - 768 cycles/word puts block periods at exactly 5.33 ms;
  - autonomy - the timer arms correctly and is never stopped by ADMAS (0077);
  - interrupt vector, registration and enable - correct (this entry).
- What is left is why the driver's producer runs at ~1% of realtime while its arm path works: candidates are IOP
  throughput (25.9 MHz measured against 36.86), a guest-side wait we never satisfy (semaphore/thread or CD read), or
  its refill loop being gated on a counter/timer this HLE does not advance. Nothing in the audio path can compensate
  for that, which is why every playback change since 0071 measured the same ~10 ms repeat.
- Status: audio still broken. Current tree is build 97, playback reads live IOP RAM, auto-DMA re-arms itself, and the
  tap + analyzer measure the emitted signal.

### 0079 - Audio: the sound threads are blocked, not slow (build 97, thread dump)

- `APE2_IOP_THREADS=1` (existing kernel dump: state, priority, pc, ra, wait object, semaphores, event flags) run for
  62 s in a music scene produced 12 dumps and, in the same run, only 12 auto-DMA arms.
- Steady state in every dump:
  - `id=1 evflag prio=16 entry=0x1039c wait=1 bits=0x2000 wake=0` - waiting on event-flag bit 0x2000, no timeout.
  - `id=6 sema  prio=46 entry=0x3d664 wait=1` with `sema 1 count=0/64` - waiting on an empty semaphore.
  - `id=7 evflag prio=46 entry=0x3e768 wait=1 bits=0x800`, and `evflag 1/2/3 bits=0x0`.
  - The rest are sleep/dormant (pad, mc, cd threads), which is expected.
- This changes the reading of the arm-rate metric: the producer is not executing slowly, it is parked on a
  completion signal. `irq 40: calls 2` against ~12 arms matches the pattern exactly - the handler fires a couple of
  times, the waiting thread consumes the flag, and no further completion arrives, so a pre-filled buffer drains at
  ~1-2 blocks/s.
- Remaining candidates, both narrow: the block-completion interrupt is disabled just after startup (`[intrman]
  disable vector=40` appears in the same logs), or the autonomous re-arm is overwritten before it can expire.
- Status: audio still broken, root cause narrowed to that handshake. Nothing in the reader/format/pacing chain is
  implicated any more.
- Addendum to 0079 (checked after writing): the disable is not the cause. In the same log the sequence is
  `disable vector=40` (line 213) followed by `enable vector=40` (216, 222), so the last state after setup is enabled.
  That withdraws the "interrupt left disabled" candidate and leaves two: either the completion the waiting thread
  needs is signalled from the EE side (a sound RPC the game never manages to make, thread 1 at 0x1039c waiting on
  event-flag bit 0x2000), or the re-arm is being consumed before it expires. The thread dump is the thing to read
  next - specifically which of these two flags thread 1 is waiting for and what sets it on real hardware.

### 0080 - Audio: the driver releases the interrupt handlers it needs (builds 98-100)

- Widened the re-arm probe for vector 40 and added dispatch witnesses (`enabled`, `handler`) plus a log on
  ReleaseIntrHandler (tools/spu2_dispatch_probe.py).
- The autonomy is not at fault: `[spu2:auto] rearm query #1101 irq=40 active=1 timerIrq=40 delay=196608` repeats, so
  the block timer fires on schedule and the re-arm is applied.
- What fails is delivery, for a concrete reason: `[spu2:auto] dispatch attempt irq=40 enabled=1 handler=1` for the
  first five attempts, and the log also contains `[intrman] release vector=36`, `release vector=40`, `release
  vector=9`. The driver registers and enables the vectors, then releases all three during startup; from then on
  every completion is refused (no handler), so thread 1 stays parked on event-flag bit 0x2000 and the stream cannot
  resume. Arms stay at ~50 per run and the reader keeps looping the last primed blocks.
- So the chain is: driver arms a burst -> driver releases the comp
  letion handlers -> our completions are dropped -> waiting thread never wakes -> no further refills.
- Next: find what drives the release. Candidates: a sound stop/reset path taken because an HLE'd syscall returns
  something unexpected, or a module teardown/restart around the same point. The release site (ReleaseIntrHandler
  caller in the driver) is the thing to identify - it is a small, local question now, unlike the earlier search.
- CORRECTION to 0080: the release is not the steady state. In run_audio26 the order is disable 40 (line 213),
  release 40 (216), enable 40 (219), register 40 handler=0x441f0 (222), enable 40 (225). The final state has a live,
  enabled handler, so the "driver released its handlers" reading above is withdrawn; it is register/enable/release
  churn during startup, and the last event leaves vector 40 armed.
- Raw dispatch witnesses (irq 40), last three:
    [spu2:auto] dispatch attempt irq=40 enabled=1 handler=1 (n=3)
    [spu2:auto] dispatch attempt irq=40 enabled=1 handler=1 (n=4)
    [spu2:auto] dispatch attempt irq=40 enabled=1 handler=1 (n=5)
- MEASUREMENT CAVEAT (0080): the witness line is capped at the first 5 attempts (`seen <= 5u`), and `[perf:iop]
  irq 40: calls` is only sampled when the perf report prints, so "5 attempts" and "calls 2" are both lower bounds as
  recorded, not steady-state counts. Before any further conclusion is drawn from those two numbers, the probes must
  count without caps or per-report sampling. Everything else in 0079-0080 stands on uncapped evidence: the thread
  dump (parked on evflag 0x2000 / sema 1), the RPC trace (266 sndn calls vs 18-55 arms), and the re-arm query
  (`active=1 timerIrq=40`).

### 0081 - Audio: delivery works, the sample was stale, and completions stop after ~5 (build 103)

- Replaced the sampled perf counter with exact accounting at the dispatch site (build 103,
  tools/spu2_evflag_fix.py + spu2_accounting_fix.py; two shell-escaping mistakes wrote literal newlines into format
  strings and were fixed with script files rather than inline commands).
- Result: `attempts=5 deliveries=5 enabled=1 handler=1` - every attempted completion for vector 40 was delivered.
  The earlier "irq 40: calls 2" was a stale perf sample, as the 0080 caveat warned. Delivery is NOT broken.
- Also added `[evflag] set` logging: `[evflag] set id=1 +0x2000 -> 0x2000` fires (10 reports, capped), so the flag
  thread 1 waits on IS being set by guest code. Thread 1 is being woken and then waits again.
- The remaining anomaly is now small and specific: only ~5 completions ever become due in a 55 s run, even though the
  re-arm query runs with `active=1` and re-arms with a 196608-cycle period, and the driver armed 11 blocks. So the
  re-armed entry is not expiring again - either it is overwritten/erased, or the cycle clock advances past it
  without the service loop seeing it due.
- Next: instrument the pending-interrupt map itself (size, due time vs cycle, insert/erase counts) for vector 40.
  That is the last unknown between the driver and working audio: completions would let the driver's producer run,
  which is the only link still clearly broken.

### 0082 - Audio root cause: the throughput probe shadowed the IOP clock (build 104)

- Root cause found, and it was self-inflicted: the 0073 throughput probe declared `static uint64_t totalCycles`
  inside `IopEmulator::runCycles`, which shadows the Impl member of the same name. From build 87 onward the
  scheduling loop, `timrman.serviceDue`, `vblank.serviceDue` and `nextWakeCycle` all read that private counter while
  `step()` and every DMA due time used the real member clock. Two clocks disagreeing.
- Symptom it produced: auto-DMA arms collapsed from ~191/s (build 86) to 11-89 per run, exactly ~5 completions ever
  came due, the driver parked on event flag 0x2000, and the reader looped the last primed ~10 ms. Everything chased
  in 0074-0081 was downstream of that single shadowed variable.
- Fix (tools/spu2_clock_shadow_fix.py): the probe now accumulates into `probeCycles`; the scheduler is back on the
  member clock.
- Measured after the fix (build 104, 55 s run, 73 s of audio):
  - auto-DMA arms 20,100 (was 11-89 per run); fresh 12,836 vs stale 7,164.
  - completion dispatch attempts 20,100, deliveries 20,100, enabled=1 handler=1.
  - `[iop:rate]` 36.86 MHz - exactly the hardware clock, up from 25.9-32 MHz.
  - emitted PCM: 6,875 chunks, 6,699 unique, adjacent-chunk repeat 2.5% (was 97.7-98.6%).
- This is the first build where the stream actually advances instead of replaying a fragment. The remaining question
  is content quality (pitch/drift/dropouts), not whether audio flows - the reader is now fed a moving stream.
- Lesson recorded for the log: instrumentation that declares a local with the same name as a shadowed member can
  silently change behaviour. The 0073 probe's own MHz figure was itself reading the wrong clock.

### 0083 - Audio: live read vs shadow A/B after the clock fix (build 104)

- With the clock fixed, re-checked whether reading live IOP RAM while the driver writes causes tearing, by running the
  same build with APE2_SPU2_SHADOW=1 and comparing the emitted PCM.
- Result: indistinguishable. Live read: 101.2 s, 8,877 unique of 9,492 chunks, 2.8% adjacent repeats, L/R
  correlation 0.932, spectral flatness 0.620. Shadow: 37.2 s, 3,449 of 3,492 unique, 1.2% repeats, correlation
  0.934, flatness 0.619. Tearing is therefore not the cause of the residual noise-like spectrum, and the default
  live read stays.
- Noted for tuning: the driver now arms at ~198.6 blocks/s for 101 s of audio (20,100 arms) against the 187.5/s a
  48 kHz stream needs, i.e. ~6% fast. That is the first real candidate for the remaining subjective defect
  (slight speed/pitch or occasional dropped block), and it is tunable without a rebuild via
  APE2_SPU2_ADMA_CYCLES (768 now; ~814 would target 187.5/s).
- Gaps: two 0.5 s windows with RMS below 10 in the 101 s capture, likely scene transitions rather than underruns, but
  worth checking against what the user hears.

### 0084 - Audio: the stream is voice sample data, and the SPU2 is essentially untouched (builds 105-106)

- User report after the clock fix: "a little fast but doesn't sound like music - no beat or tempo, just chiptune
  noise". That matches the measurements exactly (flatness 0.62, zcr 0.26 on the emitted stream).
- Scored candidate encodings of the same bytes (tools/analyze_format.py, verify_adpcm.py). As Sony 4-bit ADPCM the
  stream scores tonal (zcr 0.016, lag-1 0.935) instead of noise-like (zcr 0.26, flatness 0.669); the crude decoder
  saturates 5.9% at the rails and centres energy at 1.2-1.6 kHz, so the decode is not proof on its own, but it points
  the same way as the hardware: PS2 audio is produced by SPU2 *voices* reading ADPCM out of SPU2 RAM with pitch,
  loop and ADSR, and mixed to 48 kHz. There is no host PCM stream to tap.
- Register probe (tools/spu2_reg_probe.py, spu2_reg_probe2.py) over a 42 s run with 21,974 auto-DMA arms: only **12**
  writes into the whole SPU2 window, and none to KEYON/KEYOFF (0x1B8/0x1B4). Addresses seen are 0x1F9007C4/0x1F9007C8
  only. A game with music must program voices constantly, so either the driver's SPU2 writes are being dropped or
  redirected before reaching IopMemory, or the voice path lives somewhere this HLE does not model at all.
- Consequence: the "auto-DMA music stream" model in 0071-0083 cannot produce game audio. It replays voice sample data,
  which is why it measures like noise and has no tempo regardless of pacing, ordering or clock fixes.
- Next step is architectural, not a tuning tweak: find why SPU2 register writes are not arriving (they should number
  in the thousands per second), then implement the voice engine - ADPCM decode, pitch/loop, ADSR, 24 voices per core,
  stereo mixing at 48 kHz - which is also what SFX will need.

### 0085 - Audio: halfword SPU2 writes do reach the probe, so the driver simply is not programming voices

- Checked the write paths, because libsd programs SPU2 voices with 16-bit writes and the register probe sits in
  writeHardware32. `IopMemory::write16` splits a halfword into two `write8` calls, and `write8` performs a
  read-modify-write through `readHardware32`/`writeHardware32` on the aligned word. So SPU2 halfword writes DO funnel
  through the probe - the 12 observed writes are real, not a blind spot.
- That makes the finding sharper: over 42 s with 21,974 auto-DMA arms the game wrote the SPU2 register window 12 times
  and never touched KEYON or KEYOFF. On hardware that game has music, so the code that programs voices is not running
  under this port.
- Most likely gate: libsd-driven voice updates are periodic (timer or vblank callback). Our IOP shows only IRQ 17 and
  40 traffic, and the thread dump shows the sound threads parked on event flag 0x2000 / semaphore 1. If that periodic
  callback never fires, voices are never programmed and only the DMA sample data exists - which is exactly what the
  tap contains.
- Two paths from here, both now concrete:
  1. Diagnose the callback: count timer and vblank interrupt deliveries into guest handlers, and log the first SPU2
     voice-register writes, to see whether libsd's update path is reachable at all.
  2. Implement the voice engine: ADPCM decode from SPU2 RAM, pitch/loop, ADSR, 24 voices per core, stereo mix at
     48 kHz. This is the correct fix and also what all SFX will need; it is a substantially larger job than anything
     done in 0071-0084.
- Pragmatic alternative if the voice engine is too large for now: play the disc's BGM directly (the file-table probe
  already locates the BGM PCM/ADPCM), accepting that SFX stay silent until the voice engine exists.

### 0086 - BGM bypass: located the music files and their container layout (build 106 tree)

- Stage music lives in `PCM/BGM/*.SPS` (39 MB total for the first file, `NO28.SPS` 24,385,536 bytes); the small
  `SOUND/BGM/*.BIN` files are gzip streams (1f 8b) and are menu jingles, not the stage music.
- Container decoded from the header, verified by arithmetic: 0x800 bytes of header, then
  `payload_bytes` (field @0x18) split into 2048-byte blocks, with `block_count` @0x14 and `0xbb80` = 48 kHz @0x1c.
  For NO28: 24,383,488 / 2048 = 11,906 blocks, matching the header count exactly, i.e. ~254 s of audio.
- The in-block encoding is NOT settled yet, and the earlier probes that "looked noisy" were reading the header:
  - interleaved 16-bit L: zcr 0.169, lag-1 0.854, flatness 0.369
  - block halves treated as planar L/R correlate **-0.210**, so they are not a stereo pair
  - Sony 4-bit ADPCM decode: zcr 0.067, lag-1 0.919 (most music-like) but 5.8% of samples sit on the rails, so the
    decoder is probably not exact yet
- Wrote three candidate decodes for a listening test (`dumps/bgm/sps_adpcm.wav`, `sps_pcm_stereo.wav`,
  `sps_pcm_mono.wav`, 20 s each, tools/sps_to_wav.py). Whichever one sounds like actual music identifies the codec,
  after which the bypass is a small player: decode to PCM and feed the audio backend behind an env gate.

### 0087 - BGM bypass wired, and the SPS payload format settled (build 107)

- Format settled by measurement, not by ear-guessing: the payload is **mono 16-bit little-endian at 48 kHz starting
  at offset 0x800**. Evidence: acf lag-1 (0.882) dominates lag-2 (0.645) and the median adjacent-sample difference
  (1966) is smaller than at distance two (3443), so consecutive samples are one channel - the earlier interleaved
  stereo readings were wrong, which is exactly why they sounded slowed (two samples consumed per frame) and distorted.
  Spectral rolloff backs the rate: 99% of energy below 0.246 cycles/sample (11.8 kHz) and 99.9% below 16.2 kHz, with
  only 0.9% above 0.25, i.e. no content in the octave a 96 kHz source would occupy.
- Bypass implemented (`tools/spu2_bgm_bypass.py`): `APE2_BGM_SPS=<file.SPS>` plays a stage-music file straight to the
  audio backend, 800 mono frames per video frame duplicated to stereo, looping at end of file. The SPU2 pull is
  skipped when the bypass is active; default behaviour is unchanged.
- Conexion/container recap: 0x800 header, then `block_count` @0x14 blocks of 2048 bytes, `payload_bytes` @0x18,
  48 kHz @0x1c. For `NO28.SPS`: 11,906 blocks = 24,383,488 bytes = 12,191,744 mono samples = 254 s.

### 0088 - the SPU2 register probe was too narrow (build 108)

- Widened the probe to the legacy PS1 window (0x1F801C00) and counted core0/core1/common separately. Result: 8
  writes in 40 s, all core1 at 0x1F9007C0/0x7C8, **zero** in the legacy window and zero KEYON. So the previous
  "12 writes" figure was not a funnel blind spot - the guest really does not program voices in any window.
- Also found the earlier "auto-DMA armed" numbers were misleading: `[spu2:auto] rearm query ... active=0` shows the
  auto-DMA timer was never active; what fires is the SPU2 DMA completion IRQ (17) for manual blocks.

### 0089 - the driver thread does run (build 109)

- Per-thread scheduling counts: t1=183088, t7=210552, t6=23854 slices in ~35 s, and `[iop:wake] thread=1 from event
  flag 1 bits=0x2000` confirms the wait/notification path works. Last IOP rate: 36.85 MHz (hardware 36.86).
- So "driver never runs" is ruled out: the thread runs constantly and still writes no voice register.

### 0090 - the EE side had no SPU2 window at all (build 110)

- `isIoRegister` covered only PS2_IO_BASE (0x10000000), so EE writes to 0x1F900000 (core0/core1/common) were silently
  dropped. Routed that window into the IO register file with counting. Measured result: **0 EE SPU2 writes**, so the
  EE is not programming voices either; it talks to the IOP driver over the `sndn` RPC instead.

### 0091/0092 - where the driver spends time, and what it is asked (build 111)

- Slice-end PC histogram for thread 1 concentrates in 0x10000-0x10550 (hot: 0x10500, 0x10234, 0x103c4, 0x10550,
  0x10004), i.e. it lives inside the sound driver image but never reaches register programming.
- `sndn` traffic: one `cmd=0x65 send=64`, then `cmd=0x64` on repeat with `send=0`, alternating return buffers
  0x4ba40/0x4bc40. That pattern is command completion polling, not voice setup.

### 0093 - a real SPU2 core, and it works (build 112/113)

- New `core/iop_spu2.{h,cpp}`: 2 MB sample RAM, 24 voices x 2 cores, 4-bit ADPCM with the 5 predictor filters, pitch,
  loop addresses, an approximated ADSR, per-voice and master volume, mixing to interleaved 16-bit stereo at 48 kHz.
  Register writes route into it, DMA blocks are copied into SPU2 RAM at the core transfer address, and
  `pullSpu2Pcm` now mixes voices instead of replaying an IOP-RAM ring.
- Fixed a decoder bug found by the built-in self-test (`APE2_SPU2_SELFTEST=1`): a block shift of 0 was zeroing the
  sample instead of leaving it unscaled. Self-test now reports `keyons=1 blocks=172 peak=18430 rms=869`.
- Live run: DMA blocks do arrive (`core0 transfer 444992 bytes at 0x00000`, then 168128, then 57600; core1 gets
  1024-byte blocks) and the mixer produces 800 frames per video frame, but the output is still silent because the
  guest never sends KEYON: `[spu2:engine] ... keyon` count is 0, and the register probe shows no write to 0x1F9001B8
  or the legacy KON. The engine is now ready for the moment the driver does key a voice.

### 0094 - the sound driver answers every status poll with zeros (build 114)

- Dumped the first 16 bytes of the receive buffer for the first 24 `sndn` calls: every single answer is
  `00000000 00000000 00000000 00000000`, with no variation across calls. Combined with `send=0` on the repeating
  `cmd=0x64` and the alternating return pointers 0x4ba40/0x4bc40, the EE is polling a completion/status command that
  never reports anything, so the game never advances to voice setup.
- State of the audio path at this point: the SPU2 engine, DMA feed and mixer are complete and measured working
  (self-test peak=18430 rms=869, 800 frames mixed per video frame, bank uploads land at 0x00000/0x6ca40/0x95b00 on
  core0 and 1024-byte blocks on core1), but no KEYON is ever issued, so the mixer has no active voices and in-game
  audio is silent. This is a truthful regression from the earlier "chiptune noise": that noise came from replaying an
  IOP-RAM ring the emulator fabricated, not from the game.
- Next step is driver-side: find why the sndn command handler returns an empty status structure. The hot PCs of the
  driver thread (0x10500, 0x10234, 0x103c4, 0x10550, 0x10004) are the place to disassemble, and the return value of
  each sndn command should be compared with the command's expected structure layout.

### 0095 - the driver's RPC entry really runs and really answers (build 118)

- Added `lastGuestCallReturned()`/`lastGuestCallEndPc()` to `IopGuestExecutor` so a call that never reaches the
  return sentinel can no longer be mistaken for a normal return. For every `sndn` call: `returned=1
  endpc=0x1fffff04`, i.e. the driver entry completes and returns through the sentinel. So the earlier suspicion
  that the driver was cut off by its instruction budget is **wrong**; it runs to completion and answers with a zeroed
  status structure.

### 0096 - what is actually inside the RPC payloads (builds 115-117)

- Dumped the send payloads instead of only the replies. `cmd=0x65` (64 B) holds `{0x1e, 0, "A\PCM\BG", 0, 0x36b340,
  "APE2_USA", 3, 1, 1}` and `cmd=0x64` (160 B) holds `{0x32, 0x0a, 0x880, ...}`. `APE2_USA` matches the disc folder
  name, so this is real game data, not garbage: the payload is reaching the driver intact (the driver's own buffer at
  0x4aa40 holds the same bytes).
- The driver's IRX string table is decisive about what it can do: `SNDN2DRV.IRX` imports only `libsd`, `intrman`,
  `sifcmd`, `sifman` - no fileio, no cdvdman. It is a thin `sceSd*` front end, so voices can only be programmed
  through libsd.
- `dispatchImport` has no libsd branch and `IopImportRegistry::resolve` only resolves *registered* export tables.
  Removing the HLE claim on libsd (builtin list, service alias, service-key shadow) changed nothing measurable:
  still 8 SPU2 register writes, 0 keyons, and a new unconditional `[iop:missing]` probe shows **zero** unresolved
  imports. So the calls resolve and execute but reach code that writes no SPU2 registers.
- Net state: SPU2 core verified working in isolation, DMA and mixing wired, payload path proven, but the `sceSd*`
  layer in between is inert. That is the single remaining blocker for music, voices and SFX alike.

### 0097 - where the sceSd* calls go, and why no voice is ever keyed (build 125)

- The libsd import targets resolve into real disc code (0x45e94, 0x450dc, 0x4561c, ... - all inside the module loaded
  at base 0x42200), so LIBSD.IRX really is executing; nothing is being stubbed.
- Probing libsd's own data at 0x42200 + 0x4040 gave `basevar=0xbf900000`: libsd keeps its SPU2 base as the **KSEG1
  uncached alias** of 0x1F900000. `IopMemory::physicalAddress` already folds that (`return address & 0x1FFFFFFF`), so
  the alias was never the bug - verified, and the redundant mask line I first added was removed again.
- The register-write path for libsd is 16-bit stores (`sh`), which `write16` forwards as two `write8` calls, each
  doing a read-modify-write through `readHardware32`/`writeHardware32`. `readHardware32` only consults the SPU2 core
  when `keyonCount() != 0`, i.e. never, so the engine sees at most the 8 register words counted by the probe.
- The ordinals the driver actually calls are 4, 5, 6, 7, 9, 11, 17, 18, 19, 20, 21, 23 - setters, getters and
  transfers, but **no KEYON and no sceSdInit**. Ordinal 17 arrives with a 21,504-byte block, which is the bank upload
  we already see reaching SPU2 RAM. So the driver uploads its bank and then sits in the `cmd=0x64` poll, never keying.
- Next step is specific: the 16-bit SPU2 write path must reach the engine unconditionally (drop the keyonCount gate and
  route write16/write8 through the engine for the whole 0x1F900000 window), then re-check whether libsd's own
  register motion starts a voice.

### 0098 - the 16-bit register path never reached the engine (build 127)

- libsd programs the SPU2 with 16-bit stores (`sh`). `IopMemory::write16` turned those into two `write8` calls, each
  doing a read-modify-write through `readHardware32`, and `readHardware32` only consulted the SPU2 core when
  `keyonCount() != 0` - which is never, before a keyon. So the engine's register file was effectively write-only to
  the driver's eyes and barely reachable at all.
- Fixed both sides: reads of the 0x1F900000 window now always come from the engine, and `write16` merges into the
  32-bit word and hands it to the engine directly. Verified: the game still boots afterwards (10 IRX modules loaded,
  no exceptions in the log).
- With that in place the whole register traffic is finally visible, and it is all core1 block-transfer setup:
  `0x1F900760, 0x1F900762, 0x1F900788, 0x1F90078a, 0x1F9007c0, 0x1F9007c6, 0x1F9007c8, 0x1F9007ca`. There is still no
  write to a voice parameter, no ADSR, no start address, and no KEYON, and `sceSdInit` (libsd ordinal 0) is never
  called by the driver at all.
- So the sound driver uploads its bank into SPU2 RAM through core1 transfers and then waits. The most likely reason it
  never proceeds is the **core1 block-transfer completion signal**: the driver sets up the transfer and polls a status
  word that never becomes "done" because nothing in our SPU2 core raises the completion interrupt/status for that
  channel. That is the next thing to implement and measure.

### 0099 - reading the real driver instead of guessing (build 129)

- Dumped the live IOP image (`APE2_IOP_RAM_DUMP`/`APE2_IOP_RAM_DUMP2`, 2 MB each) and disassembled the RPC entry the
  game actually calls: sid 0x736e646e, handler at **0x46e8c**, command buffer 0x4aa40.
- The handler branches on the RPC function: `0x64` calls 0x46f54 first, anything else calls 0x4730c with the fixed
  buffer 0x4aa40 and returns 0x4de40. `0x64` returns one of two alternating status buffers (0x4ba40/0x4bc40) - which
  is exactly the pattern in the trace, so the RPC ABI we use is right.
- 0x46f54 walks the 160-byte payload in **16-byte records** and dispatches each record through 0x4730c, whose jump
  table is at 0x4aa10 and indexes on `record[0] - 1` (< 0x4f entries). So `0x32` (50) in the payload is a command id
  in the same space as `0x1e` (30) from the other call.
- Diffing early vs late dumps proves the driver **is** processing: at 0x4aa40 the game's batch
  (`32000000 0a000000 80080000`) has been replaced by driver-written data (`20000000 08010000 54008032 ...`). At the
  same time the two status buffers 0x4ba40 and 0x4bc40, and 0x4de40, are still all zero 500 calls later.
- The audio worker loop is at 0x104c0-0x10580: `WaitEventFlag(bits=0x1400, mode=1, &res)`, then `if (res & 0x1000)
  goto 0x1041c` (retry), else `ClearEventFlag(0x400)` -> 0x101ac/0x101d4/0x102fc -> `WaitEventFlag(0x2000)` ->
  `ClearEventFlag(0x2000)` -> 0x10324 -> loop. It is an event-driven mixer thread, and bit 0x1000 is its retry
  condition - the next thing to measure is how often it takes that retry branch.
- Still no voice parameter write, no start address, no ADSR and no KEYON anywhere, so music, voices and SFX remain
  silent. This entry records what is now proven rather than what is hoped.

### 0100 - the disassembled loop is not the one that runs (builds 130/131)

- Added PC counters for the worker loop I read out of the dump (0x1041c, 0x1050c, 0x10514) to measure the
  retry-vs-proceed ratio. Result: **zero hits in 20 s**, even after lowering the print threshold. So the hot loop from
  the earlier slice histogram (0x10500/0x10550) is not the same code path as the function at 0x104c0 that I
  disassembled from the RAM dump - the two must be reconciled before drawing conclusions about the event-flag retry.
- This is why no driver-side fix was attempted from that disassembly: the evidence did not support it yet.
- State: builds 118-131 compile and boot (10 IRX modules, no exceptions), the SPU2 core is verified in isolation, the
  RPC payload path is proven, and the driver is confirmed to be processing command batches - but no voice parameter,
  ADSR, start address or KEYON write exists anywhere, so audio (music, voices, SFX) is still silent.

### 0101 - my own probes were hiding the traffic (build 132)

- Two probes under-reported and I drew conclusions from them: the `[libsd]` trace printed only the first call per
  ordinal, and the 16-bit register log kept only the first 12 writes. The driver's command handlers (dispatch table at
  **0x4a410**, 79 entries, indexed by `record[0]-1`) call the libsd wrappers at 0x4a294/0x4a2ac/0x4a2c4/0x4a2ec for
  every parameter record, so libsd is called continuously, not a dozen times.
- Added an uncapped histogram of 16-bit SPU2 register writes (`[spu2:hist]`, top offsets printed every 50k writes) so
  the real voice-programming pattern can be seen. Whether this build reaches audio init within a 22 s run varies - the
  first run after the change showed no SPU2 traffic and no PCM at all, the second showed the usual boot.
- Net: still no confirmed KEYON and no audible output. The instrumentation is now honest (uncapped, per-offset), which
  is what the next measurement needs.

### 0104 - the voice-sweep theory, tested and reverted (builds 135-138)

- Real numbers at last: libsd is called ~74,000 times in 25 s, and the ordinal histogram is
  `4=1 5=8 6=73448 7=4 9=2 11=3 17=1 19=1530 21=1 23=2`. Ordinal 6 is polled continuously with
  `a0=0x500,0x502,...,0x516` (a per-voice sweep) and returns `0x3fff` for every voice. The setters (5, 7) run 12
  times total, and no voice-parameter offset in 0x000-0x09E is ever written.
- Hypothesis tested: our core seeds every voice's left/right volume to 0x3FFF, so the sweep may be seeing "all voices
  busy". Changing the reset state to 0 changed nothing (polls still 73,448 in the same window) and it broke the SPU2
  self-test (`blocks=0`), so the change was reverted in build 138 and the self-test's audible result restored.
- Conclusion: the 0x3FFF is not what blocks the sweep, and the driver's wait is on something else. The next honest step
  is to check what libsd ordinal 6 actually returns to the driver versus what the driver compares it against - i.e. read
  the caller's comparison in SNDN2DRV, not the getter.

### 0105 - the 16-bit read path, and what the status buffers really are (build 139)

- Fixed another real asymmetry: libsd reads voice registers with `lhu` (16-bit), and `IopMemory::read16` never
  consulted the SPU2 core - it fell through to `read8` twice, which only reads a shadow map. Every value the driver
  polled therefore came back as 0 no matter what the engine held. `read16` now extracts from the engine's 32-bit word
  for the whole 0x1F900000 window. Self-test unaffected: `keyons=1 blocks=172 peak=18430 rms=869.1`, game still boots
  (10 IRX modules).
- Decoded what `cmd=0x64` actually does end-to-end (handler 0x46f54): it dispatches every 16-byte record at 0x4aa40
  through 0x4730c, then for 2 cores x 24 voices it reads a value from the table at 0x4DE40 into 0x4BB00+ and stores the
  libsd ordinal-6 getter result (masked 0x7fff) into 0x4BA40+. So those two buffers are a **per-voice status
  snapshot**, not a completion flag - all-zero simply means "no voice reports a non-zero value yet", which is correct
  before playback starts.
- Consequence: the game is not blocked waiting for a completion word. It simply never issues a playback/parameter
  command: ordinal 6 (per-voice getter) is polled ~74,000 times per 25 s while the setters 5 and 7 run 12 times total,
  and no voice parameter offset (0x000-0x09E) is ever written. The single `cmd=0x65` call carries a disc path plus a
  0x36b340 byte size, and SNDN2DRV has no fileio at all, so that load request cannot be satisfied by the driver itself.
- Next step is therefore not in the SPU2 core: it is to establish what the game expects to happen with that 0x65
  request, and whether the run even reaches a point where music should start.

### 0106 - the real failure: the game never leaves "Now Loading" (build 139)

- User-observed symptom, which none of the earlier audio work accounted for: the port sits on the "Now Loading"
  screen forever. Every audio measurement so far was taken *during that hang*, so silence was a symptom, not the bug.
- EE PC sampling pins it: `samples=1139 | 0x37c5a0 98% | 0x37c5a4 1% | 0x37c5b8 1%`. Disassembling the guest ELF at
  0x37c5a0 (file offset 0x27d5a0, segment 1: vaddr 0x100000 / offset 0x1000) gives a handshake spin:
  `lw v1,0x1c0(a0) / lw v0,0x48(s0) / ... / bne v1,v0,->0x37c5a0`, i.e. the EE waits for a counter written on the
  other side to catch up. Deadlock, not a slow load.
- What led into it: the game performs a full `sceCdSearchFile` sweep of its audio assets - `\APE2_USA\PCM\BGM\
  TITLE.SPS;1` (lsn 0x158beb, 0x1771800 bytes), `STAFF.SPS`, and ~14 `\APE2_USA\PCM\DEMO\*.SPS` - all of which
  resolve correctly, then stops issuing CD reads entirely (`[ape2:cdread]` ends at lbn 0xea3) and never reads
  TITLE.SPS. Meanwhile the sound driver never stops polling libsd ordinal 6 (~200k calls by sample 1139), its voice
  setters stay at 12 calls, and no KEYON ever happens.
- Combined reading: loading waits on the sound driver, the sound driver waits on a libsd status that never becomes
  what it expects, so it never consumes, so the counter the EE is spinning on never advances. The "Now Loading" hang
  and the silence are the same defect, sited at the EE<->SNDN2DRV streaming handshake, not in the SPU2 core.
- Next: read the loop as it executes (the code is decompressed into RAM at boot, so the ELF bytes are not enough) -
  dump EE RAM around 0x37c000-0x37d000 at the hang and resolve 0x48(s0) and 0x1c0(a0) to name the counter and its
  writer. Runtime already exposes `g_ape2Rdram` (ps2_memory.cpp:267) for such dumps.

### 0107 - the "Now Loading" wait, resolved to a helper and its caller (build 141)

- Added a one-shot guest RAM dump (`zz_ape2_hangdump.cpp`, env `APE2_HANG_DUMP=<prefix>`; writes the whole 32 MiB
  EE image ~12 s in). The code the EE spins in is unpacked into RAM at boot, so the ELF image is not usable evidence -
  the running copy is.
- The spin at 0x37c59c is a complete function, read from the live dump:
  `s1 = arg; s0 = sub_378AD8(); a0 = s0; if (arg==0) return (obj->0x1c0 == obj->0x48);`
  `if (arg!=1) return -1; while (obj->0x1c0 != obj->0x48) {} return 1;`
  So mode 1 is "wait until submitted count == completed count", mode 0 is "is it idle?".
- `sub_378AD8` is `return *(u32*)0x614240;` - a single global load object. In the live dump that word is 0x20614040,
  i.e. KSEG alias of 0x614040. At the hang its counters read submitted=0 / completed=0, so the load queue is *empty*
  and the idle helper returns true immediately: the counters are not the stuck condition.
- The only call site of that helper in the whole image is 0x1b751c inside the function starting 0x1b73e0, which
  brackets its use with calls to 0x192cd8 / 0x192cb0 / 0x192bf8 / 0x192bb8 and a `lw v0,0x344(s1)` test. That outer
  function is where the "Now Loading" loop actually decides to keep waiting, so it is the next thing to read.
- Also confirmed the earlier audio work is not wasted: the SPU2 core still self-tests clean, and the driver's polling
  is simply the idle sound thread while this load loop never finishes.

### 0108 - which two counters the wait compares (build 141 dump)

- Correction to 0107: the helper calls two different globals. `0x378a58` returns the constant `0x611FC0` (call it S);
  `0x378ad8` returns `*(u32*)0x614240` = `0x614040` (call it D). In the loop `s0 = S` and `a0 = D`, so the spin is
  `while (*(u32*)(D+0x1c0) != *(u32*)(S+0x48)) {}` - i.e. two independent counters, not two fields of one object.
- The producer is visible: `sub_37C4D8` (reached from 0x37C470 / 0x37C4A8, which pass command ids 0x20 and 0x21) does
  `v0 = sub_378A58(); *(u32*)(v0+0x48) += 1`, storing the incremented value - that is the "chunk queued" counter at
  `S+0x48` = 0x612008.
- So the "Now Loading" spin waits for the *sound streaming module's* queue to drain, one chunk at a time. That is why
  no KEYON is ever issued and why the SPU2 sees a single 444,992-byte transfer at 0x00000 but no voice programming:
  the queue is filled and never consumed.
- Verified the libsd getter now really returns engine state (`read16` fix) and still yields `0x3fff` for every voice,
  with `active=0 timerIrq=0` on the SPU2 side - so the driver's poll never observes the transition it waits for.

### 0109 - the three writers of the done counter (APE2_RAM_WATCH on 0x614200)

- Write-watched the page containing the done counter with the existing `APE2_RAM_WATCH=0x614200,4` override. Only three
  guest stores ever touch it, each named by the runtime's symbol resolver:
  - `sub_00100010_0x100010+0x626` -> guest 0x100626,
  - `sub_0037C0A0_0x37c0a0+0x3839` -> guest ~0x37F8D9, inside the same stream/decoder module that owns the queue,
  - `_NLG_Return2+0x4568` (a store helper; guest site not resolved through the CRT frame).
  Plus one adjacent bulk write at 0x6141F1 from `memmove` (page-level clear/copy, not the counter).
- None of them raises the counter while the game is stuck: it stays 0 with submitted 1, so the consumer is not merely
  failing to update - it never runs at all.
- The dispatch this hangs from is `sub_378B08`: a 0x30-entry loop, stride 0x54, over driver command buffers. Each entry
  has flags at +0x00, a sequence at +0x14, a payload pointer at +0x10, a command byte at +0x50 and dispatches through a
  jump table at 0x53xxxx to one of ~20 handlers (0x37A840, 0x379470, 0x379058, ...), ending in `jal 0x37C268` with
  (0x64, 1, ...) and cycling `+0x3c` between 0 and 1. That is the sound-driver command pump - the consumer lives in here.

### 0110 - leading hypothesis: the driver never sees its SPU2 transfer complete

- Every run prints `[spu2:auto] rearm query #N irq=17 active=0 timerIrq=0 delay=0` thousands of times, and
  `[spu2:engine] core0 transfer 444992 bytes at 0x00000 (next 0x6ca40)` once. The pump above therefore keeps
  re-arming and polling a transfer-complete condition that the core never latches, so it never advances its
  command sequence and never drains the queue the EE is spinning on.
- Evidence for "never latches" is the `active=0` on every single query (4000 samples) while the transfer record exists.
- This is a defect on my side of the line (SPU2 core / IRQ latch), not in the guest: the driver's poll is well formed
  and the libsd getter now returns real engine state (`read16` fix, entry 0105).
- Next: make a finished core transfer set the transfer-complete/STAT bit the driver polls, verify `active=1` appears,
  then confirm the queue drains (0x614200 != 0) and the game leaves "Now Loading".

### 0111 - the IOP hot loop and a stub that never fills in its status word

- Dumped IOP RAM (`APE2_IOP_RAM_DUMP`, dumps/iop.bin, 2 MiB) and disassembled the hottest IOP PCs from `[iop:hot]`.
- The top PC every sample is 0x10500, inside this loop (IOP RAM sits at offset 0, so guest addr = file offset):
  `0x104f8 jal 0x10e90 (a0=*(s0), a1=0x1400, a2=1, a3=&status)` / `0x10500 v0 = status` /
  `0x10508 andi v0,0x1000` / `0x1050c bnez v0 -> 0x1041c`. So the IOP waits for bit 0x1000 to *clear*, and it never does.
- 0x10e90 disassembles to `jr $ra` followed by `addiu $zero,$zero,0xa` (a no-op) and then padding: the call returns
  without writing the caller's status word at all. The loop can therefore never observe the transition it waits for.
  This is an unresolved import thunk / stubbed helper, not working code.
- The region belongs to sio2man / intrman / dmacman (module name strings sit alongside it), not to libsd, so the stall is
  in the IOP's device service layer that the sound driver calls into.
- Consequence for the EE side: the driver never consumes, the SPS queue stays at depth 1 (0x612008=1 vs 0x614200=0,
  entries 0108/0109), and the game spins on "Now Loading" (entry 0107).
- Next: enumerate the import stubs in that range and find which module's bindings are missing/zeroed, instead of
  guessing at SPU2 registers (the `0x3fff` seen earlier came from the diagnostic probe's address decoding, not from the
  guest - confirmed by watching the writes: the driver never writes 0x1F900014).

### 0112 - the "Now Loading" hang was a regression I introduced, not a missing feature

- The user reported that an earlier build ran near 60 fps, so this was treated as a regression and A/B tested instead
  of investigated further. Two switches were added for that purpose and are kept for future bisects:
  `APE2_SPU2_ROUTE16=0` (pre-0105 read routing) and `APE2_SPU2_OFF=1` (whole core bypassed = pre-audio path).
- Read routing was innocent: with and without it the game stops on exactly the same instruction (0x37c5a0), 7 CD reads,
  last read lbn 0xea3. Hypothesis discarded by measurement.
- Bypassing the whole core changed everything: 20 CD reads, last lbn 0x16a1, EE spread over 0x39ca48/0x24a308/0x352f88
  instead of 98% in the spin. So the SPU2 core itself was what bricked the boot.

### 0113 - root cause: the DMA completion status bit lived only in the flat map

- `IopMemory::readHardware32` returns `m_spu2.read32(address)` for the whole SPU2 window, but `writeHardware32` set the
  DMA completion flag (`status |= 0x80 << shift` at 0x1F900344) only in `m_hardware`. With the core enabled the guest
  read the core's register file instead, so the completion flag was never visible to it.
- The driver's pump therefore polled a flag that could not change: the stream queue stayed at depth 1 (0x612008=1 vs
  0x614200=0, entries 0108/0109) and the EE spun in `sub_37C568(1)` waiting for it (entry 0107).
- Fix (0114): mirror that status word into the core as well, so reads of the SPU2 window agree with the flat map.

### 0114 - fix verified (build 146)

- Core enabled, no switches set: 27 CD reads, last lbn 0x5b9f0 - the same final read as the core-off baseline (58 reads,
  same lbn), so the boot now reaches the same place either way. EE time is distributed over real game code instead of a
  single spin address. `[spu2:engine]` shows 6 transfers.
- Still to confirm on screen: whether the loading screen now completes into the menu, and whether voices get keyed
  (`keyon` is 0 in the first 22 s, so any music must start later in the sequence).
- Perf note: in the same wall-clock window the core-enabled build completes fewer CD reads than the bypassed one
  (27 vs 58), i.e. the mixer costs measurable time. Needs a frame-rate measurement before calling it done.

### 0115 - after the boot fix, the IOP emulation collapses to 0.01 MHz once streaming starts

- With 0114 in, the game leaves the loading screen and reaches the title stream:
  `[ape2:movie] open 'cdrom0:/APE2_USA/pcm/bgm/title.sps'` -> `[ape2:stinit] iop_buf=0x83280` ->
  `[sceCdStStart] lbn=0x5b9f0 rate=2700 sectors/s` -> one `[sceCdStRead]`, then the frame rate dies.
- A/B numbers, same wall-clock window:
  - core enabled: frames 108 (53.9/s) then 6 frames in 7.18 s = 0.8/s, `[iop:rate] 0.01 MHz`, 1 `sceCdStRead`.
  - core bypassed (`APE2_SPU2_OFF=1`): 115/119/118/121 frames (57-60/s) held through `[ape2:stinit]`, 34 `sceCdStRead`.
  - mixing skipped (`APE2_SPU2_NOMIX=1`, new switch): still 1.2/s, so the mixer is NOT the cost.
- So the register/RAM path of the core is what stalls: the IOP emulation thread stops making progress (0.01 MHz
  against 36.86) exactly when the driver starts streaming into SPU2 RAM through it. The EE is then left waiting
  (50% at 0x352eb8 plus spread), which is why frames fall to ~1/s rather than to zero.
- Audio is still silent: `[spu2:engine] keyon` is 0 in every run, so no voice has been keyed yet even now that the
  stream starts. That is the next thing to measure once the IOP keeps running.
- Next: instrument the per-access cost of the core path during streaming (DMA byte copy vs register traffic) and make
  the transfer copy block-wise instead of byte-wise, then re-measure `[iop:rate]` and frames.

### 0116 - the stall is a blocked IOP thread, not slow code (build 148)

- `transferWrite` now block-copies (`memcpy` with wrap handling) instead of masking and bounds-checking every byte.
  The rearm-query trace switch (APE2_SPU2_TRACE) did NOT apply - the edit asserted on its pattern and the file was left
  untouched; record it so it is not believed to be in.
- Measured after the change: 115/120/108 frames (54-60/s) then 9 frames in 7.13 s = 1.2/s, `[iop:rate] 0.00 MHz`,
  `[sceCdStRead]` = 1, `keyon` = 0. Identical to before the memcpy change.
- `[iop:rate] 0.00 MHz` against 36.86 MHz is the important number: the IOP emulation thread stops executing almost
  entirely right after the first streaming read. That is a blocked/stalled thread, not a hot loop - a hot loop would
  still report a high rate. `[perf:iop] ... end-pc 0x0` points at the IOP being inside a host service routine.
- So the next measurement must be the IOP thread's state at the stall (host stack / which service call it is inside),
  not more work on the mixer or the transfer copy - both have now been excluded by measurement.
- Audio unchanged: no voice has ever been keyed, so nothing is audible yet.

### 0117 - removed the EE/stream frame-rate coupling; symptom unchanged

- Applied: `continueCdStRead` no longer parks the EE on a future vsync tick when the ring is empty. It produces the
  needed sectors (at least one whole bank, since `readableCdStreamSectors` only hands out whole banks) and continues.
  Rationale: the disc clock was modelled in frame ticks, so stream availability and frame rate could only wait on
  each other.
- Result (build 149): 120/120/113/109 frames then 8 frames in 6.77 s = 1.1/s, `[sceCdStRead]` = 1, `keyon` = 0,
  `[iop:rate] 0.01 MHz`. No change, so the park was not the mechanism. The change is kept (it removes a real
  timebase coupling) but it is not the fix.
- Excluded so far, each by measurement rather than argument: the mixer (`APE2_SPU2_NOMIX=1` -> still 1.2/s),
  the SPU2 RAM transfer copy (memcpy -> no change), the register read path (`read32`/`readRegister` do array
  indexing only, no per-call work), the stream park (0117 -> no change), and audio output blocking
  (`pushStreamPcm` only tops up when `IsAudioStreamProcessed`, no sleeps).
- Remaining difference between the 60 fps and 1 fps runs is the SPU2 register/DMA path being live: every DMA start
  logs `admas=0x0` (manual block mode) and `[spu2:auto] armed` never appears, so no auto-DMA timer is ever armed
  while the driver issues 356 rearm queries that all get "nothing to reschedule".
- Next measurement, not a guess: sample the *host* stack of the EE thread while it is at 1 fps (the existing
  host sampler reported only its own frame), and check whether the EE is inside `continueCdStRead`/MPEG feed or in
  its own decode loop. That tells whether to fix the CD feed or the decode path.

### 0118 - DMA/status words answered by the flat map; no effect, reverted

- Premise: with the core enabled the driver never programmed a voice (`[spu2:reg]` = 0, `keyon` = 0) while the
  bypassed run wrote 8 register words and 8 keyons, so the completion poll was reading a DMA word the core answered
  for. Routed 0x1F900340..0x1F90034F and +0x400 back to the flat map.
- Result (build 150): 120/120/117/108 frames then 9 frames in 6.75 s = 1.3/s, still `reg=0`, `keyon=0`,
  `[sceCdStRead]` = 1, `[iop:rate] 0.01 MHz`. The premise was wrong, so it is REVERTED, together with 0117.
  Neither is in the tree any more; only 0114 (verified boot fix) and 0116 (behaviour-identical memcpy) remain.

### 0119 - state of the freeze after 0117/0118 were reverted (build 151)

- Verified and kept: 0114. The game leaves "Now Loading", opens title.sps, initialises the stream, and holds
  54-60 fps for the first ~4 s.
- Not fixed: ~4 s after the stream starts, frames fall to 1.1-1.3/s with `[iop:rate] 0.01 MHz` while the EE is spread
  over many PCs (0x343390 30%, 0x343450 13%, 0x351ed8 7%, 0x34c5a0 7%). Both guest CPUs crawl while the host thread is
  apparently inside neither of them, so the next measurement must be a host stack sample of the stalled thread.
- Excluded by measurement: mixer (APE2_SPU2_NOMIX), transfer copy (memcpy), register reads (plain array indexing),
  stream park (0117), audio output blocking (pushStreamPcm never sleeps), DMA-word read source (0118).

### 0120 - presenter stage timing (APE2_FRAME_PROF=1)

- Added stage timers around `pullSpu2Pcm` / `UploadFrame` / draw / `EndDrawing` in the runtime frame loop, printed every
  2 s. Answer to "which side blocks?": the presenter never blocks.
  `[frame:prof] 2000ms loops=120 | pull 0.0 | upload 0.0 | draw 0.1 | enddraw 16.5 ms` for the whole run, i.e. a
  steady 60 fps present with 16.6 ms spent in the vsync wait, while `[perf]` simultaneously reported
  `6.81s | frames 9 (1.3/s)`. `[perf]` counts guest vsyncs (`ps2perf::countFrame` in gs_frontend), so the collapse is
  in the guest/EE thread, not in rendering, audio output, or the window.
- Kept (gated behind `APE2_FRAME_PROF`); four `steady_clock` reads per loop are negligible when disabled.

### 0121 - the frame-lock was multiplying the stall by ~7x

- `EeScheduler::holdVBlankForGameFrame()` (patch 0049) holds VBlank until the game completes the stage frame it
  started at the previous vsync, capped at 4 x 16.7 ms. A guest frame that is already slow therefore gets a second
  delay on top of its own.
- A/B, same binary, `APE2_VSYNC_FRAMELOCK=0`: frames 120/120/121/120 at 60/s, then `7.78s | frames 80 (10.2/s)`
  against `6.81s | frames 9 (1.3/s)` with the lock on. An 8x improvement in the stalled phase, but the guest frame is
  still ~100 ms of guest work instead of 16 ms, and `[spu2:reg]`=0, `keyon`=0, `[sceCdStRead]`=1, `[iop:rate] 0.01 MHz`
  are unchanged, so this is not the fix either - it exposes the real slowdown instead of compounding it.
- The frame-lock stays on by default: it exists to stop the camera shaking, which is a real defect it fixes.
- Conclusion: with the SPU2 core enabled the game reaches a point where the EE spends ~100 ms of guest work per stage
  frame in a parked/spinning state around 0x343390/0x343450 while the IOP only gets 0.01 MHz of slices. The IOP share
  is the thing to fix next: the sound driver cannot make progress while the EE holds the interpreter, and whatever the
  EE is waiting for at 0x343390 is almost certainly what the driver would have produced.

### 0122 / 0123 - idle time now advances the IOP (the real starvation fix)

- Cause found by reading the scheduler rather than guessing: `accountCycles()` is the *only* caller of
  `advanceIopEeCycles()` (`iopCycles = eeCycles / 8`). In `waitForEvent()` idle time was converted to cycles only on
  the `!signaled` branch, and the frame-lock pacing wait in `processDueDeadlines()` (~line 1910) accounted nothing at
  all. So while the EE was parked - exactly the state a guest stall creates - the IOP stood still, and whatever the EE
  was waiting for could never be produced.
- 0122: `waitForEvent()` now accounts host-elapsed time as EE cycles (capped at 1 s per wait) whichever way the wait
  ends. Measured alone: iop:rate went 0.01 -> 0.27 MHz, still stalled.
- 0123: same accounting added to the pacing wait. Measured: `[iop:rate] 36.86 MHz (hardware 36.86)` - the IOP now runs
  at full hardware rate - and a 30 s run held 53-60 fps with 26 CD reads where it previously collapsed at 4 s.
- Honest status after a 95 s run (build 155): `stinit=1`, `stread=1`, `cdreads=27`, `dma=4`, `[libsd:hist]` 1123 lines
  (~560k libsd calls) but `keyon` still 0 and frames falling to `1 (0.1/s)`. The stall moved: it is no longer IOP
  starvation but a libsd call storm - the sound driver polling half a million times for a state we never satisfy,
  which is the next thing to chase.
- Side effect to watch: one sample showed `940.26 MHz`, i.e. idle accounting can over-credit cycles when waits and
  guest execution interleave. Frames stay vsync-capped so it is not visible yet, but it needs a real-time budget
  rather than a per-wait cap if it ever shows up as the game running fast.

### 0124 - where the good build was lost: comparison of the fast runs against build 155

- Compared the logs from the era that ran well (`run_audio32.log`, `run_real_libsd.log`, 03:30 and 09:02 today) with
  build 155 (`ab_iop3.log`, `ab_nomix2.log`):
  - fast: `[perf]` 50-60 fps throughout, `[iop:rate] 36.85 MHz`, `stread` 32-224, `cdreads` 27-50, **`[libsd:hist]`
    0 and `[libsd:poll] 0`** - the real LIBSD path was never executed.
  - build 155: `[iop:rate] 36.86 MHz` (0123 works), but `[libsd:hist]` 1123 (~560k libsd calls), `[libsd:poll]` 20,
    `stread` 1, and frames collapsing to `1 (0.1/s)`.
- So the regression that lost the 60 fps is the step that made the *real* LIBSD.IRX run instead of the HLE stub
  (0096/0097, `iop_module_manager.cpp`: "libsd must be the real disc module"). The fast builds were fast partly
  because the sound driver's own polling loop never ran; now it does, and it never gets satisfied.
- Answer to "is the fps crash the cost of processing sound?": no. `APE2_SPU2_NOMIX=1` disables all voice mixing on the
  host and the run still collapses (`2.00s | frames 119 (59.4/s)` then `7.34s | frames 3 (0.4/s)`, 436 libsd
  histogram lines). Host sample processing is not the cost; the guest driver's poll loop is.
- The poll itself: every `[libsd:poll]` line is `ord=6 off=0x14 reg=0x3fff a1=0x0` with `a0` marching 0x522, 0x524,
  0x526. `reg=0x3fff` is not a register the driver should be asking for, which suggests our libsd RPC is handing back
  a parameter block where the driver expects a status word, so it retries forever. That is the next thing to read.

### 0125 - the repo is not a runnable reference build (checked, not assumed)

- Checked whether the committed tree can serve as the clean build: `HEAD` is `e563698`, and
  `ps2xRuntime/src/runner/register_functions.cpp` there is **6 lines** against 114,953 in the working tree. HEAD also
  has **no** `core/iop_spu2.cpp`. So a HEAD build compiles but cannot run the game: there is no recompiled game code,
  and every SPU2/IOP change of the last months lives only in the working tree.
- Consequence: the 57-60 fps runs from this morning (`run_audio32.log` 03:30, `run_real_libsd.log` 09:02) were a
  working-tree build of about build 125. That state is not in any repository and no binary was archived, so it cannot
  be re-run; it has to be reconstructed by reverting my post-09:02 edits.
- Protections put in place before any such attempt: `bin_b155.exe` (the current runner) and
  `engine_work_b155.patch` (123,166 lines, the whole uncommitted engine diff) are saved outside the build tree.
- Important consequence for the bisect: build 125 ran the game at 60 fps **without** the 0114 DMA-status fix, i.e.
  before the driver learned to see DMA completion. 0114 is what let the game past "Now Loading", and it is also the
  change after which the frame rate collapsed. If that holds, the fps loss is the *price of the driver making
  progress*, not an independent performance bug - which means the bisect should confirm 0114 as the pivot and the fix
  must make the driver's new path terminate cheaply, not revert to the hang.

### 0126 / 0127 - what "pull the repo and delete the work" would actually do, and the pre-session baseline

- Checked instead of assuming. `.build_now.cmd` runs `build_windows.ps1` with **`-SkipRecomp`**, so it does NOT
  regenerate game code, and `ps2xRuntime/src/runner/register_functions.cpp` is a tracked file that is 6 lines at HEAD
  and 114,953 lines in the working tree. A pull-to-HEAD plus `git checkout .` therefore produces a runner with no
  recompiled game functions: it builds, then cannot boot the game. It would NOT be "how it was before we started".
- The project repo carries no engine or game source either (docs, overrides, tools, game, generated, dumps only), so
  it cannot rebuild the port by itself. Essentially the whole port - 48 modified tracked files plus 25 untracked new
  ones - is uncommitted, which is why no build number can be reproduced from a repository.
- 0126 adds `APE2_SPU2_NOSTATUS=1` to skip the 0114 status mirror, for the pre-0114 comparison. Note the generated
  guard nests as `if (cond) if (getenv()==nullptr) m_spu2.write32(...)` - correct but ugly, worth tidying.
- The pre-session behaviour does not need any deletion: `APE2_SPU2_OFF=1` on the current binary measures
  `cdreads=27 stinit=1 stread=32`, min fps 47.9, i.e. the healthy silent build. That is the fair "before" baseline.
- Caveat found by that run: `[iop:rate] 1062.75 MHz` against hardware 36.86 - the 0122/0123 idle accounting
  over-credits cycles while the EE is parked (an earlier sample showed 940.26 MHz). It fixed the starvation, but it
  needs a real-time budget instead of a per-wait cap.
- Safety net now in place before anything destructive: `bin_b155.exe` (runner), `engine_work_b155.patch` (all tracked
  modifications), `engine_untracked_b155.tgz` (all untracked new files).

### 0128 - the scheduler spin path was unaccounted; it alone recovers ~2x, still not enough

- 0127 measured `[iop:rate] 0.26 MHz` with the game at 5.5 fps, so the IOP was starving again even with the 0122/0123
  accounting. Cause: `waitForEvent()` returns immediately when events are already queued, and the `run()` idle branch
  then loops without accounting any cycles. 0128 times that branch and accounts the host time (capped at 1 ms per
  iteration so a spin cannot over-credit).
- Result (build 157): the stalled phase went 5.5/s -> **10.8/s** and the run kept 59.9/s right up to the stream start.
  But `[iop:rate]` is still **0.01 MHz**, so this was a real improvement and not the mechanism.

### 0129 - three-way comparison, same binary family, 40 s each

| case | min fps | cdreads | stinit | stread | keyon | iop:rate |
|---|---|---|---|---|---|---|
| `APE2_SPU2_OFF=1` (good build behaviour) | 47.4 | 27 | 1 | **32** | 0 | 36.85 MHz |
| `APE2_SPU2_NOSTATUS=1` (no 0114 mirror) | 53.0 | **7** | **0** | 0 | 0 | 36.86 MHz |
| current (0114 mirror on) | 5.5 | 27 | 1 | **1** | 0 | 0.26 MHz |
| current + 0128 (build 157) | 10.8 | 27 | 1 | 1 | 0 | 0.01 MHz |

- What this settles: the NOSTATUS case looks fast only because it never leaves loading (7 CD reads, no `stinit`), so
  it is not a healthy comparison. **`SPU2_OFF` is the honest reference: it reaches `stinit`, serves 32 stream reads and
  still holds 47+ fps.** Progress and frame rate therefore *do* coexist, which kills the earlier idea that the
  slowdown is simply "the price of the driver making progress".
- So the defect is specific to the core-enabled path after the first `sceCdStRead`: the game stops asking for stream
  data (`stread` 32 -> 1) and its cycle rate collapses (`iop 36.85 -> 0.01 MHz`) while the presenter keeps a solid
  60 fps. The EE thread must be sitting in host code that never accounts cycles; it is not in a scheduler wait (all
  four are now accounted) and not in guest code (that would raise the IOP rate).
- Next, and it is a measurement with a definite answer: time the host entry points the streaming phase newly uses -
  `readCdSectors`/`continueCdStRead` and the libsd/RPC host path - and print any call over ~3 ms. The 90 ms/frame the
  EE loses is inside one of those, and knowing which one ends the guessing.
- Status: build 157, nothing running. 0114 (boot), 0112-era reverts, 0122/0123/0126/0128 are in the tree; 0117/0118
  remain reverted; backups `bin_b155.exe`, `engine_work_b155.patch`, `engine_untracked_b155.tgz` are current.

### 0130 - the frame time is guest code, and the scheduler credits 8 cycles for it

- Probe around the generated-call dispatch (`function(m_rdram, &context, &m_runtime)`) printing any call over 20 ms.
  Result: a single dispatch ran **1129.5 ms** (`0x3530ec -> 0x19bd70`), another **895.2 ms** (`0x19bd70 -> 0x2234c8`),
  238.9 ms, and 0x208b60->0x208e54 repeats at 155 ms. So the EE is genuinely executing generated game code for
  seconds at a time, while the presenter holds 60 fps.
- Root cause of the cycle collapse: `ee_scheduler.h:268 static constexpr uint32_t kGuestDispatchCycles = 8u;` -
  the scheduler accounts **8 cycles per dispatch**, and generated code contains **zero** checkpoint hooks
  (`grep -c checkpointDue register_functions.cpp` = 0), so a dispatch that runs a second of game code is credited
  8 cycles. Everything clocked off that counter - the IOP (`eeCycles / 8`), timers, waits - therefore runs about
  60x too slow. This is why `[iop:rate]` reads 0.01 MHz whenever a long generated function runs.
- Kept: the probe (40 reports max), gated by the same 20 ms threshold.

### 0131 / 0132 - the IOP is driven from dispatch wall time (0.01 -> 25 MHz)

- 0131: after each dispatch, advance the IOP by the wall time actually elapsed (`advanceIopEeCycles(ns * 294.9MHz)`),
  capped at 50 ms. Measured: `[iop:rate]` 0.01 -> **11.65 MHz**, `[libsd:hist]` became readable for the first time:
  `4=1 5=16 6=87553 7=4 9=2 11=3 17=5 18=1 19=1824 20=158`. Ordinal 6 (the per-voice status getter, see 0105) is
  87,553 of 89,600 calls - the driver is polling voice status.
- 0132: the 50 ms cap was the limit, so the full measured interval is credited (1 s cap for safety). Measured:
  `[iop:rate] 24.86 / 25.10 MHz`, ordinal 6 polled 82,418 times, `stread` still 1, `keyon` still 0, frames 8.5/s then
  0.0/s in the last window. Both changes kept: they are physically right (the IOP is a real-time CPU), and they took
  the emulated IOP from dead to two thirds of hardware speed.
- Assessment: the frame-rate cause is now fully explained - not the SPU2 core's cost, but the scheduler crediting 8
  cycles for dispatches that run for a second, which starves the IOP and every timer. The remaining stall is the
  driver's ordinal-6 voice-status poll, which cannot finish because no voice is ever keyed.

### 0133 - state and next step

- Build 160 is the current binary; nothing is running. Backups `bin_b155.exe`, `engine_work_b155.patch`,
  `engine_untracked_b155.tgz` are current.
- Next: ordinal 6 returns per-voice status (masked 0x7fff, copied into the driver's 0x4BA40 buffers). The value comes
  from the real LIBSD.IRX reading SPU2 registers, so the fix is in the core's voice/transfer status: log the resolved
  target of `imports.resolve("libsd", 6)` once, read it from `dumps/iop.bin`, and make the register it samples report
  a keyed, advancing voice - which means completing the core1 block-transfer path (`admas == 0`, the manual block
  case) the same way 0114 completed the auto-DMA start.

### 0135 - the frame-rate collapse is fixed: core1's completion IRQ now arms with ADMAS=0

- Change: `iop_memory.cpp:636` - `const bool autoDma = (admas & (secondCore ? 2u : 1u)) != 0u || secondCore;`
  (0135). The driver starts core1 transfers in **manual block mode** (`admas=0x0`, every `[IOP] SPU2 core1 DMA
  start` line says so), so the auto-DMA timer never armed, `dmaRearmDelay` always returned `std::nullopt`, and the
  driver's completion IRQ never fired - its stream pump then polled libsd ordinal 6 forever. Arm the timer for core1
  starts regardless of ADMAS.
- Measured (build 162, 50 s): `armed=8468`, `[sceCdStRead] 1 -> **32**`, `stinit=1`, frames 59-60 fps throughout,
  `[iop:rate] 59.07 MHz`, 4 core1 DMA starts with `delay=196608 cycles`.
- Measured (build 162, 95 s): frames 60/60/59.5/59.5/54/58/46.9 - **min 46.9 fps, i.e. the ~1 fps freeze is gone** -
  `stread=64`, `cdreads=31`, `stinit=2`, `armed=22642`. Compare 0119/0121 where the same phase ran at 1.1-1.3 fps.
- Still open: `keyon=0` (no audio), and the driver still polls ordinal 6 heavily (267,120 of 295,500 libsd calls).
  Also `[iop:rate] 67-68 MHz` against 36.86 - 0132's uncapped wall-time credit over-drives the IOP and needs a
  real-time budget (carry the excess rather than dropping it, or credit only the delta since the last credit).
- Root cause summary for the record: two independent defects caused the freeze. (1) The scheduler credited 8 cycles per
  generated dispatch regardless of duration (`kGuestDispatchCycles`), starving the IOP and all timers - fixed by
  0131/0132 driving the IOP from wall time. (2) Core1's manual-mode transfers never produced a completion IRQ - fixed
  by 0135. Neither was an SPU2 mixing cost, which APE2_SPU2_NOMIX had already ruled out.

### 0136 - with streaming fixed, the mixer runs but no voice is ever keyed

- Probes added: `[spu2:keyon]` in `IopSpu2::keyOn` (40 reports) and `[spu2:mix]` on the first five non-empty mixes
  (frames + peak).
- Measured (build 163, 70 s): frames 58.5/60.0 fps, `stread=32`, `stinit=1`, `armed=14272`, bank uploads visible as
  `[spu2:engine] core1 transfer 1024 bytes at 0x00000/0x00400/0x00800 ...`, and
  `[spu2:mix] frames=800 peak=0` five times, **`keyOn` calls = 0**.
- So the engine and the streaming path are now healthy: the driver uploads its bank, receives 14k+ completion IRQs,
  streams 32 CD reads, and the mixer is asked for 800 frames per video frame. It outputs digital silence because
  `KEYON` is never written - the driver's own state machine still refuses to start a voice. The 267k ordinal-6 calls
  are `sceSdGetParam`-style reads (decoded from IRX 0x4507c: `offset = ((a0>>6)&0x3FC) + (a0&0x3E)*8` plus the core
  base at IOP 0x46240, `lhu` read), i.e. the driver polling voice status while it waits.
- Next: instrument the driver side rather than the core - which RPC command the game sends (sid 0x736e646e, cmd 0x64
  path) and which condition makes the driver key. The core is ready; the missing input is the driver's decision.

### 0137 - status

- Fixed today and verified by measurement: the loading deadlock (0114), the IOP starvation (0122/0123/0128/0131/0132)
  and the frame-rate collapse (0135) - 60 fps for 95 s in the phase that used to run at 1.1 fps.
- Not fixed: audio. The mixer produces silence because no voice is keyed; the driver uploads, streams and polls but
  never writes KEYON.
- Known blemish to fix before shipping: `[iop:rate] 67-68 MHz` against 36.86 hardware - 0132 over-credits and needs a
  real-time budget.

### 0138 - the driver conversation, now that streaming works

- Ran build 163 for 60 s with the existing `[sndn]` probe: frames hold (min 47.4 fps), `stread=32`, `armed=12109`,
  `mix=5`, **`keyon=0`**.
- The conversation the game has with the sound driver (sid 0x736e646e):
  - `cmd=0x65`, 64 bytes, payload contains `"C\PC\M\BG..."` and `"PS;1"` - the bank/sequence load request. Handled.
  - `cmd=0x64`, **160 bytes** once: `32 000000 | 0a 000000 | 80 0800 00 ... 28 000000 ... 28 000000 | 01 000000`,
    i.e. the driver's command block (two 0x28-byte entries and a count).
  - then `cmd=0x64` **with size 0**, alternating between buffers `0x612040` and `0x613040`, forever - the game polling
    the driver for status while the driver is expected to work through the 160-byte command.
- So the game has asked for something and is polling for completion; the driver never keys a voice and never finishes.
  `outcome returned=1 endpc=0x1fffff04` on every one of those calls is worth a look on its own - that return PC is
  outside RAM, so the RPC completion path may be landing somewhere unintended.
- Next: read the driver's handler for the 160-byte `cmd=0x64` block (LOG 0099 located it: 0x64 -> 0x46f54, status
  buffers 0x4ba40/0x4bc40) and find which field the driver checks before keying; and check the 0x1fffff04 return PC.
- Note for the next session: it is plausible that AE2's title screen plays via the streamed SPS path and voices only
  key when a level starts (SFX), so testing from actual gameplay is worthwhile before assuming the driver is stuck.

### 0139 - core1's register window was never modelled (real bug, fixed)

- The 16-bit write histogram from the last gameplay session showed the driver programming `0x1a0/0x1a2` **and**
  `0x5a0/0x5a2`, i.e. core1's voice block. `IopSpu2::writeRegister`/`readRegister` matched the voice block
  (`offset < 0x2a0`) and the core switches (`TSA 0x1a8`, `ADMAS 0x1b0`, `KEYON 0x1b8`) against the raw offset, but
  core1's window is the same layout `0x400` higher, so **every** core1 register access fell through to a plain
  `regs[]` array and did nothing: no core1 voices, no core1 ADMAS, no core1 KEYON.
- Fixed by normalising `offset >= 0x400 -> offset - 0x400` at the top of both register functions. Added switch
  counters to prove the stage is reached.
- Measured (build 164): `[spu2:switch] core0 off=0x1b0 ... core1 off=0x1b0 ... core1 off=0x198` - core1's register
  writes now land properly - frames 48-60 fps, `stread=32`, `armed=8994`. Still `keyon calls = 0`, `keyon hits = 0`,
  `[spu2:mix] peak=0`.

### 0140 - why the driver never keys: its main thread is asleep

- IOP thread dump (`APE2_IOP_THREADS=1`): threads 6 and 7 (`entry 0x3d664`, `0x3e768`, prio 46) are in `delay` with
  wake cycles ~10.77e9 - the stream/ADPCM workers cycling normally. Thread 8 `entry 0x40568` is **dormant**. Thread 9
  `entry 0x46e10` (the sound driver's main/RPC thread, next door to the 0x46e8c handler) is **sleep**, and thread 10
  `entry 0x4f910` is **sleep** as well.
- So the driver uploads, streams, receives 127,500/127,500 completion IRQs and programs core1's registers, but the
  thread that would walk its sequence and issue KEYON never runs: it is asleep waiting on a wake that never arrives.
- Its `cmd=0x64` handler at `0x46f54` (disassembled) walks a 0x10-byte-stride command table from `0x40000 + (a0>>?)`
  into `0x5aa40` and calls `0x4730c` per entry - a command queue that only the sleeping thread drains.
- Next: either find the missing wake (who should `iWakeupThread` 9: the SPU2 IRQ handler is registered and fires, so
  check its `handler=1` path actually signals the semaphore the driver waits on), or take the documented fallback -
  feed the already-proven 48 kHz PCM stream to the audio device the way 0071 did, since the stream itself is healthy.

### 0141 / 0142 - the wake attempt, and why it was reverted

- 0141 instrumented every thread import and intrman call. Findings: SNDN2DRV registers an interrupt handler on
  **IRQ 17 (0x11)** with handler `0x10584` (`[iop:intr] ord=4 a0=0x11 a2=0x10584`), the only thread call aimed at
  tid 9 is a single `ord=6 a0=9` at init, and the driver's main thread stays `sleep` at `0x46e70` for the whole run.
- 0142 tried delivering core1's completion on IRQ 17 to match, on the theory that the driver's own handler would then
  wake its sequencer. Result: `[spu2:auto] armed irq=17` but `[sceCdStRead]` fell **32 -> 1**, i.e. it broke the
  streaming path that 0135 had fixed; `keyon` still 0. **Reverted** to `0x28`.
  (The first patch attempt also corrupted the constant to `17x28` and failed to compile - noted because it is exactly
  the kind of sloppy edit worth avoiding; the retry asserted the exact replacement.)
- State after revert: streaming and frame rate are the 0135/0139 state (32 stream reads, ~50-60 fps), audio still
  silent because no voice is ever keyed and the driver's sequencer thread never wakes.

### 0143 - the sound driver's threads are (mostly) not asleep; the RPC handler has no thread context

Probe: `APE2_IOP_SEMA=1` logs every semaphore-group import with the current thread id (build 169, 40 s run,
`run_0143.log`).

Measured traffic in that run:

| sem | SIGNAL | WAIT (tid) |
| --- | --- | --- |
| 1 | 15557 | - |
| 4 | 15291 | 15291 (tid 7) |
| 6 | 255 | - |
| 7 | 15301 | - |
| 5 | 1 | - |

- **Sema 4 is a real work queue and it is being serviced**: thread 7 waits on it 15,291 times and gets released
  15,291 times. So the driver is not idle - tid 7 is doing the SNDN2DRV work.
- **Every one of those 15,291 signals happens with `tid=-1`**, i.e. `IopKernel::m_currentThread == nullptr`.
  That is `IopRpcBridge::handleRpc` running the guest server function inline through
  `executor.executeGuestFunction(...)` with no thread context attached.
- **tid 9 never appears in any semaphore event, ever** (grep `tid=9` = 0 hits). It was started
  (`[iop:thr] ord=6 a0=9 a2=10`, and 6 = StartThread in our table) and then slept and was never touched again.
  Its earlier "driver main thread" reading was a misread: the module's *main* thread never resumes, while its
  worker thread 7 runs the queue.
- `keyon` still 0, and the only SPU2 core0 register writes seen are auto-DMA control (`off=0x1b0`), never KEYON.

Consequence and next suspect, stated as a hypothesis to test rather than a fix: guest kernel calls made from
`executeGuestFunction` have no current thread, so any thread-scoped call inside an RPC handler is a no-op
(`case 20` returns 0, `SleepThread`/`DelayThread` paths check `m_currentThread != nullptr`). If SNDN2DRV's handler
uses such a call to hand work to its sequencer, that hand-off is silently dropped - and the sequencer is exactly
what would key voices.

Note on cost: 30k fprintf calls dropped the frame rate minimum from 45.9 to 37.4 in this run; the probe is
env-gated and must not be left on.

### 0144 - what the driver's 670k poll actually reads

Probe: `APE2_LIBSD_POLL=1` histograms the register offset behind every `libsd` ordinal 6/19 call (build 171,
`run_0144b.log`). Only three offsets are ever polled:

| offset | calls (last snapshot) | first value returned |
| --- | --- | --- |
| 0x014 | 58776 | 0x00003fff |
| 0x414 (core1 mirror) | 58776 | 0x00003fff |
| 0x400 (core1 +0x00) | 2448 | 0x00000000 |

- The poll is **not** stuck on a zero/garbage value: 0x3fff is a plausible saturated volume, so this is a normal
  per-frame status read, not a wait loop that our emulation is deadlocking. The earlier "669k GetParam calls is
  suspicious" reading is withdrawn.
- `[handlers]` counters in the same run: `sdInit=1 cmd1e=1 cmd32=1 spu2IrqHandler=13997`. So the driver's SPU2
  interrupt handler at `0x10584` - the same address it registers on IRQ 17 - runs ~14k times, and its two command
  handlers each run exactly once.
- `keyon` is still 0, and the only core0 register writes remain auto-DMA control at `off=0x1b0`.

Current best hypothesis (untested): `0x10584` costs ~13 instructions per call, i.e. it reads the SPU2 status word,
finds no bit it is prepared to handle, and returns - so transfer-completion interrupts are being delivered but
never carry the "voice/transfer finished" state the driver waits for. The next measurement is to log the status
value `0x10584` actually reads and the bit it tests, then compare against what a completed voice transfer should
report.

### 0145 - 0x10584 is a SIF packet-receive handler, not an SPU2 handler

Two measurements, both from build 172:

1. Probe `APE2_SPU2_HIRQ=1` tags every SPU2 access made while `pc == 0x10584`. Result over 45 s:
   `[handlers] spu2IrqHandler=13997`, and **zero** SPU2 reads, zero 16-bit reads, zero writes. The handler never
   touches the sound chip, so it cannot be the transfer-completion path.
2. `APE2_IOP_RAM_DUMP` + a local disassembly of the code at that address:

```
010584: 27bdffe8  addiu sp,sp,-24
010588: afb00010  sw    s0,0x10(sp)
01058c: afbf0014  sw    ra,0x14(sp)
010590: 0c00405e  jal   0x10178
010594: 00808021  addu  s0,a0,zero        ; s0 = handler arg (0x10f98)
010598: 0c004059  jal   0x10164
01059c: 00402021  addu  a0,v0,zero
0105a0: 8e040004  lw    a0,0x4(s0)        ; buffer pointer lives at arg+4
0105a4: 0c0043a0  jal   0x10e80
0105a8: 24052000  addiu a1,zero,8192      ; 0x2000 bytes
0105ac..: restore, v0 = 1, return
```

`arg+4` is a pointer and the call copies **0x2000 bytes** into it - that is the SIF RPC receive buffer size.
Combined with `[iop:intr] ord=4 a0=0x11 a1=0x1 a2=0x10584 a3=0x10f98` (RegisterIntrHandler, irq 17, type 1,
handler 0x10584, arg 0x10f98), the driver's interrupt path is a **SIF packet delivery**, not SPU2.

Why this matters: `IopRpcBridge::handleRpc` delivers commands by calling the registered server function inline and
copying the payload to `server.buffer`. The driver, meanwhile, has an interrupt handler whose whole job is to
receive a 0x2000-byte SIF packet into `*(arg+4)`. Those are two different data paths: our bridge can satisfy
command *dispatch*, but it never performs the SIF transfer the driver's streaming code is written around.

Next measurement, not yet run: count SIF register traffic and check whether any SIF DMA (0x1F8010A0.. / SIF0-SIF2)
transfer is ever started or completed in our emulation, and whether `*(0x10f9c)` is a valid, non-null buffer at the
time 0x10584 runs. If the driver streams sample data over SIF DMA, that is the missing piece for voice keying.

### 0146 - the music bank path is corrupt on the EE side before it reaches the RPC

Probe `APE2_RPC_PKTPROBE=1` (build 173) dumps 176 bytes around the decoded send address for the first RPC
packets. `run_0146.log`:

```
send=0x1fffed0 size=64
1fffed0: 1e 00 00 00 00 00 00 00     ; len = 30 = strlen("\APE2_USA\PCM\BGM\TITLE.SPS;1") + 1
1fffed8: 41 5c 50 43 4d 5c 42 47     ; "A\PCM\BG"   - expected "\APE2_US" (5c 41 50 45 32 5f 55 53)
1fffeE8: 50 53 3b 31 00 53 3b 31 40.. ; "PS;1\0S;1@"
1fffef8: 41 50 45 32 5f 55 53 41     ; "APE2_USA" arrives 40 bytes later
```

- The corruption is **not** in our RPC transport: the payload dump at iop_rpc.cpp reads the EE source before the
  copy, and the same run delivers the next packet (`cmd=0x64`, 160 bytes at 0x612040) perfectly formed.
- The pieces of `\APE2_USA\PCM\BGM\TITLE.SPS;1` are present but scattered in 8-byte chunks with 8-byte gaps, i.e.
  a copy with the wrong stride/offset. The declared length 0x1e (30) is correct, so the length is known and only
  the bytes are misplaced.
- Consequence: the driver receives an unopenable path, never issues `sceCdRead` (`cdRead=0` in every run; the only
  reads are 32 `sceCdStRead` at lbn 0x5b9f1..0x5ba10, far from the bank at lsn 0x158beb), never loads the 24 MB
  `TITLE.SPS` bank, and therefore never keys a voice. That chain explains `keyon=0` without any SPU2 defect.

Next step: find the EE-side builder of this packet (it assembles cmd 0x65 with the bank path) and inspect the
string copy in the recompiled output. Note `sceCdSearchFile` for the same path succeeds twice, so a correct copy
of the string exists in EE memory - only this packet's assembly is wrong.

### 0147 - two more hypotheses ruled out (pointer follow, 128-bit store)

- `genWrite(128, ...)` for `sq` ends in `Ps2FastWrite128`, which does `std::memcpy(rdram + offset, &value, 16)`
  (ps2_runtime_macros.h:530-544). The 128-bit store path copies all 16 bytes, so a strided/half store is **not**
  the source of the mangled bank path. Hypothesis withdrawn.
- The dword at packet+32 is `0x0036b340`, but reading it yields **MIPS code** (`2d 90 40 00 1a 00 40 06 ...`), not a
  string, so it is not a path pointer either. Hypothesis withdrawn.
- What remains measured: the 64-byte packet declares length 0x1e (30) and holds only an 8-byte fragment
  `A\PCM\BG` at +8, zeros at +16, `PS;1\0S;1` at +24, `APE2_USA` at +40. Compared with the source string
  `\APE2_USA\PCM\BGM\TITLE.SPS;1`, +8 matches source[8..15] and +24 matches source[25..32] - i.e. partial, out of
  order, and offset by one chunk, not a uniform stride. Whether the game intends this layout (path assembled later
  by the driver) or our recompilation mis-assembles it is **not settled**, and I am not claiming either.

State: build 174, all probes env-gated, audio still silent, ~60 fps unchanged. Next measurement: does SNDN2DRV ever
open the SPS bank itself (`sceOpen`/fileio RPC originating from IOP threads)? `cdRead=0` and `keyon=0` say no data
reaches the driver, and that is upstream of every SPU2 question.

### 0148 - IRQ 17 belongs to SIO2, and the driver never calls a cdvd import

- `0x1F808200-0x1F808284` is the **SIO2** block (`iop_sio2.h`: SEND3/SEND1/SEND2/DATAIN/DATAOUT/CTRL/RECV/ISTAT,
  `IopSio2::Irq = 17`). The handler at `0x10584` reads `ISTAT` (`0xBF808280`) and runs ~311 times/s in step with the
  pad polling. It is SIO2MAN's pad handler. The `0x11` that 0142 briefly used for SPU2 core1 completion was SIO2's own
  IRQ - that experiment was delivering sound completions into the pad driver, which is why it regressed streaming.
- New probe `APE2_IOP_CDVD=1` histograms every `IopCdvd::dispatchImport` call. Over 30 s: **zero** calls
  (`grep -c "iop:cdvd" run_0148.log` = 0). So SNDN2DRV never issues `sceCdRead`/`sceCdStRead`/`sceCdSync` through the
  HLE cdvd library at all, while the EE side still performs its own 32 `sceCdStRead` calls.
- That is consistent with the 0146/0147 packet anomaly: the driver is told to load
  `\APE2_USA\PCM\BGM\TITLE.SPS;1` (24 MB, lsn 0x158beb) by a 64-byte packet that does not contain that string, and it
  never attempts a disc read for it. No data => no voices => `keyon=0`.

State: build 175, ~60 fps unchanged, audio still silent, nothing pushed. Next experiment: trace the driver's SPU2
KEYON writer at the hardware level (IOP RAM/DMA), since HLE import probes cannot see real-module file I/O.

### 0149 - EE->IOP SIF DMA never targets the sound driver

Probe `APE2_SIF_DMA=1` on `sceSifSetDma` (build 178, `run_0149c.log`). 60 transfers logged, and every one is an
**EE-local block copy**, not an IOP transfer:

```
list=0x1fffef0 dst=0xebe200 src=0x83280 size=0x6ca20
list=0x540550 dst=0x540680 src=0xc32c0 size=0x8000
list=0x540550 dst=0x540680 src=0xc42c0 size=0x1000   (repeated 1 KiB blocks)
```

`dst`/`src` are both EE addresses (`0xeb....`, `0x54....`, `0xc3....`); IOP RAM is `0x000000-0x1FFFFF`, so no
transfer lands in IOP RAM at all, and nothing targets the driver's data area (`0x4a000-0x4c000`, where the
`sndn:status` writes go). Meanwhile `stread=32` (EE-side disc streaming) and `keyon=0` are unchanged.

Chain now measured end to end:
1. EE finds the bank: `sceCdSearchFile \APE2_USA\PCM\BGM\TITLE.SPS;1`, 24 MB, lsn 0x158beb, twice OK.
2. EE sends cmd 0x65 whose 64-byte packet declares length 0x1e but does **not** contain that path (0146).
3. The driver never issues a cdvd import call (`iop:cdvd` = 0 over 30 s, 0148).
4. No SIF DMA enters IOP RAM (this entry), so no sample data is pushed to the driver either.
5. Therefore `keyon=0` and the mixer stays silent while the frame rate stays at ~60 fps.

So the silence is upstream of SPU2 entirely. Next experiment: determine what the driver does with the cmd 0x65
packet - step the driver's handler (base 0x46d00) and log its first ~40 executed instructions and any `sceOpen`
style call it makes, to learn whether it rejects the packet or expects a different layout.

Note: this 32 s run was not used for a frame-rate number (no `fps=` lines captured), so the last measured frame rate
remains 60 typical / 47.9 min from the 0145-era runs.

### 0150 - The RPC copy is byte-faithful (0146 "broken packet" theory withdrawn)

Probe `APE2_RPC_COPY=1` in `IopRpcBridge::handleRpc` (build 179, `run_0150.log`), dumping the EE payload read
through `readGuest` next to the bytes actually written into IOP RAM at `server.buffer`:

```
[rpc:copy] sid=0x736e646e fn=0x65 ee=0x1fffed0 iop=0x4aa40 size=0x40
 0000 ee: 1e 00 00 00 00 00 00 00 41 5c 50 43 4d 5c 42 47   iop: 1e 00 00 00 00 ...
 0010 ee: 00 00 00 00 00 00 00 00 50 53 3b 31 00 53 3b 31   iop: 00 00 00 00 00 ...
 0020 ee: 40 b3 36 00 00 00 00 00 41 50 45 32 5f 55 53 41   iop: 40 b3 36 00 00 ...
 0030 ee: 03 00 00 00 01 00 00 00 01 00 00 00 00 00 00 00   iop: 03 00 00 00 01 ...
```

`iop` tracks `ee` exactly for all 64 bytes, so `readGuest` + `writeRam` are correct and the driver receives precisely
what the game put in that buffer. `sid=0x736e646e` decodes to ASCII `sndn`. This supersedes 0146: the fragments are
not a transport artefact, they are the *actual* content of the EE send buffer. `ee=0x1fffed0` is an EE address that
merely happens to be numerically inside the IOP RAM range, which is why the earlier "is this IOP memory?" doubt arose;
it is not, and 0146 did dump the right buffer.

Field 0 at +0 is `0x1e` = 30 = `strlen("\APE2_USA\PCM\BGM\TITLE.SPS;1")`, so the buffer format is
`{ len, ?, char path[] @ +8 }` and a 30-byte path at +8 would exactly fill +8..+0x25. What is there instead is a
mid-string window (`A\PCM\BG` = source[8..15]). The remaining explanation is a **reused scratch buffer**: the path was
written into it at some earlier point, the buffer was then re-used for this call which only overwrote part of it.

### 0151 - sndn is never sent a path; nothing is missing from the HLE

Probe widened to 0x200 bytes (build 180, `run_0151.log`). Full sndn call inventory over 34 s:

```
 1 fn=0x65 size=0x40      (once, at init)
 1 fn=0x64 size=0xa0      (once)
 1 fn=0x64 size=0x80
 1 fn=0x64 size=0x20
 6 fn=0x64 size=0x10
 3 fn=0x0  size=0x200     (sid 0x63736d69 = "csmi", an unrelated server)
```

Every `fn=0x64` call is staged from the same EE buffer `0x612040` into the same IOP buffer `0x4aa40`, so the game
reuses one staging buffer for all of them. The 0xa0 payload is a well-formed table of (id, sub, value) tuples -
`{0x32,10,0x880}`, `{0x14,0,0x001fffff}`, `{0x14,1,0x001dffff}`, `{0x15,0,0x104}`, `{0x16,0,0x1999,0x1999}`,
`{0x16,1,...}`, `{0x3c,...}` - not a path and not corruption.

And critically: `grep "unhandled import"` over runs 0145c/0148/0149c/0150/0151 returns **zero** lines, so no IOP
import the guest calls is missing from the HLE. The driver is not being starved by an unimplemented library.

State of the audio path after 0148-0151, all measured:
- the bank is located by the EE (24 MB, lsn 0x158beb) but never read (`cdRead=0`);
- no path is ever sent to sndn (this entry);
- sndn makes zero cdvd import calls (0148);
- no SIF DMA ever lands in IOP RAM (0149);
- nothing is unhandled (this entry);
- `keyon=0`, mixer silent, frame rate unaffected.

So the open question is no longer "is our data mangled" but "what is supposed to hand sndn its samples at all". Next
experiment: dump the *IOP-side* private state of sndn after the fn=0x64 calls - specifically whether the driver writes
a bank/queue pointer and then sits waiting on something (semaphore 4, or an IOP SIF callback that never fires) - by
tracing what the driver thread does after handling `fn=0x64` instead of what it receives.

### 0152 - Root cause found: the SPU2 voice block was 0x1C-strided and swallowed KEYON

`IopSpu2::writeRegister` decoded voices as `offset < kVoices * 0x1C` (24 * 28 = 0x2A0) and **returned early**.
That range covers the core registers:
`0x1A8` TSA, `0x1B0` ADMAS, `0x1B8` KEYON, `0x1BC` KEYOFF, `0x198`/`0x19A`, `0x1A4`/`0x1A6`.
So every write the driver made to KEYON was silently stored as "voice 21 inner offset 0x0C" and the `switch (offset)`
below it - the only path to `keyOn()` - was unreachable. `readRegister` had the same faulty decode, which is why the
driver's polls at `0x14`/`0x414` returned `0x3fff` (a value it had written into what it believed was a voice register)
and never progressed to starting a voice.

The block boundary proves the stride: the same file defines main volume at `0x180`, and 24 voices * 0x10 = 0x180
exactly. The 0x1C stride therefore overran into the core register window by 0x120 bytes.

Fixed (0152):
- `kVoiceStride = 0x10`, voice block limit `kVoices * kVoiceStride` = 0x180.
- `kVoiceStartAddress = 0x06` (start address, samples * 8), `kVoiceAdsr1 = 0x08`, `kVoiceAdsr2 = 0x0A`,
  `kVoiceLoopAddress = 0x0E` (was 0x10) - the real PS1/SPU2 voice layout, which the legacy-window mapping in the
  same file already assumes (offsets below 0x180 map 1:1).
- Both `writeRegister` and `readRegister` now decode index = offset / 0x10, within = offset % 0x10.

Measured after the fix (build 181, `run_0152b.log`, 40 s):
- the core register block is now reached: `[spu2:switch]` shows `0x1b0/0x1b2` (ADMAS, both cores) and
  `0x198/0x19a` dispatching instead of being absorbed by the voice block;
- `keyon=0` still, `[spu2:mix] frames=800 peak=0` still;
- polls unchanged in shape: `[libsd:pollhist] n=100000 14=48984/00003fff 400=2040/00000000 414=48976/00003fff`,
  i.e. the driver still reads voice-1 pitch as 0x3fff and still never keys a voice.

So 0152 fixes a genuine, provable register-map bug (core writes could never work), but it is not sufficient: the
driver still has no sample bank and is not asked to play anything (0150/0151). Remaining open question is unchanged -
what is supposed to deliver a bank to sndn - and the next experiment is to find which call *would* precede a KEYON
(compare against what the same driver does when the bank load succeeds).

### 0153 - Inconclusive: the RAM dump I inspected was stale, not a live image

Ran 26 s with `APE2_IOP_RAM_DUMP=1` and searched the resulting 2 MB image for the module and bank names. Result:
`APE2_USA` 0 hits, `PCM` 0 hits, `BGM` 0 hits, `TITLE.SPS` 0 hits, `SNDN2DRV` 0 hits - the full path is absent.

That result is **not usable as evidence about the game**: `SNDN2DRV` must be present in any genuine IOP RAM image,
since the module is loaded there (0145's dump had it). The file was a stale `1` (2 MB) left in the runner directory
by an earlier session - `dumpRam()` takes the env *value* as its filename, so `APE2_IOP_RAM_DUMP=1` writes a file
called `1`, and my run did not refresh it.

Conclusion: no finding either way from this. The experiment needs to be repeated with a unique filename
(`APE2_IOP_RAM_DUMP=iop_0153.bin`) and a check that the module names are present, which is the precondition for any
search of the driver's private state to mean anything.

#### 0153 correction

The `1` file **was** fresh (written by that run); my "stale file" conclusion was wrong. It is the *early* dump: the
late dump is gated on `sndnCalls == 500u`, and sndn is only called ~10 times in a 34 s session, so it never fires.
The search was therefore run against an early image. Retaken in 0154.

### 0154 - Late IOP image: the bank path exists nowhere in IOP RAM

Lowered the late-dump trigger from `sndnCalls == 500u` to `sndnCalls == 8u` (build 182) and dumped to a unique
filename, `APE2_IOP_RAM_DUMP2=iop_0154.bin` (this is how `dumpRam()` names its file - the env *value* is the path).

Search of the 2 MB late image (`run_0154.log`):

```
SIO2MAN    hits=1  at 0x10f4c        <- proves this is a live IOP image with loaded modules
SNDN2DRV   hits=0
LIBSD      hits=0
APE2_USA   hits=0
PCM        hits=0
TITLE.SPS  hits=0
```

Two readings, both consistent with 0151: module *names* are not stored for SNDN2DRV/LIBSD (SIO2MAN's is, so absence of
a name is not by itself meaningful), and - the part that matters - **no part of the bank path exists anywhere in IOP
RAM at call 8**. The driver holds nothing it could open. The fragments seen at `iop=0x4aa40` in 0150 belong to the
4th call and are overwritten by the later `fn=0x64` calls that reuse the same buffer, which is why the search finds
no trace at call 8.

So the chain is now nailed down: the EE authoritatively locates the bank with `sceCdSearchFile`, and the only thing the
driver ever receives is a reused 64-byte scratch buffer whose `len` field (0x1e = 30 = the path's length) says a path
should be at +8, while the bytes there are a mid-string window. That points at the **EE-side builder of that buffer**,
not at the transport, the RPC, the driver, or SPU2.

Next experiment: put a write watchpoint on EE address `0x1fffed0` for the window between the string copy and the RPC
call, logging every store (`pc`, offset, size, value). If the builder writes 30 bytes contiguously and the buffer still
reads back fragmented, the fault is in the recompiled store path; if the builder only ever writes scattered chunks,
the fault is in the game-facing call sequence and the fragment layout is a red herring.

### 0155 - Correction to 0154's premise: the bank DOES reach SPU2 RAM

A plain 95 s idle run (`run_0155.log`, no probes beyond the always-on ones) shows the driver actively loading sample
data into SPU2 sound RAM:

```
[spu2:engine] core0 transfer 444992 bytes at 0x00000 (next 0x6ca40)
[spu2:engine] core0 transfer 168128 bytes at 0x00018 (next 0x290d8)
[spu2:engine] core0 transfer  57600 bytes at 0x00028 (next 0x0e128)
[spu2:engine] core1 transfer   1024 bytes at 0x00000 (next 0x00400)
```

That is ~670 KB uploaded into core0's sound RAM, in three large blocks, plus 1 KiB blocks to core1. So the driver is
**not** starved of samples: it gets data and writes it through the SPU2 transfer FIFO. sndn is called 38 times over
95 s (more than the 10 seen in the first 34 s), and the log stays alive (99,928 lines).

This corrects the framing of 0153/0154 - "nothing ever hands sndn its samples" was wrong. What is actually missing is
only the KEYON: `keyon_hits=0` and `[spu2:mix] frames=800 peak=0` for the whole 95 s, with 670 KB sitting in sound RAM.

Also ruled out in this entry: **the EE never touches SPU2.** The always-on `[ee:spu2]` probe (0090) logged 0 lines over
the same 95 s, so the game issues no SPU2 register traffic from the EE side at all. KEYON can only come from the IOP
driver's own code path, and `IopSpu2::keyOn` (reachable since the 0152 stride fix) is still never called.

Remaining question is now narrow and specific: the driver loads samples, then polls its status register and never
keys. Either it is waiting for a SPU2 status/flag bit our core never sets (the `0x344` STAT path), or the libsd
ordinal it hammers is a transfer/parameter call whose return value we get wrong. Next: log the *raw returned value*
of libsd ordinals 6 and 19 per call (not a decoded register read) and the SPU2 STAT reads, and compare against what
the driver's loop expects.

### 0156 - Register-level instrumentation: what the driver programs, and what it polls

Added `APE2_SPU2_STATE`: per-register write/read histograms inside `IopSpu2` plus a state dump every 2000 mixes
(~33 s) covering voice registers, the common block, transfer addresses and a spin trace for `0x344`/`0x1b0`.
Histograms are needed because every previous "poll" claim came from a probe *guessing* register semantics from `a0`;
these record the register offset the core actually serviced.

Dump 1 (`run_0156.log`):

```
[spu2:state] dump=1 mixes=2000 keyons=0 active=0 blocks=0 taddr0=0x013678 adma0=0 taddr1=0x03d000 adma1=2
[spu2:voice] core0 v00 pitch=0x3fff startA=0x00000 loop=0x00000 volL=0x0000 ... adsr1=0x0000 adsr2=0x0000
             (all 24 voices identical, 48 lines = 2 cores x 24)
[spu2:common] 188=ffff 18a=00ff 190=ffff 192=00ff 198=ffcc 19a=c081 1a0=ffff 1a2=00ff 1a4=ffff 1a6=00ff 1ac=0707 1b0=0002
```

So the driver programmes exactly one thing per voice - pitch = `0x3fff`, its default - and every volume/ADSR/start
register is still zero. Nothing is armed for playback.

Write histogram: `0x344 n=12537 last=0x0080`, `0x346 n=12537 last=0x0000`, `0x198/0x19a n=25`, `0x1a8/0x1aa n=14`,
`0x360/0x362`, `0x388/0x38a n=10 last=0x3fff`.
Read histogram: `0x1b0/0x1b2 n=12540 last=0x0002`, and `0x008/0x00a/0x018/0x01a/0x028/0x02a/0x038/0x03a n=7039`
(ADSR1/ADSR2 of voices 0-3).

### 0157 - The driver's wait loop, exactly

Widened the histogram to every control offset and traced the spin order (`run_0157.log`):

```
R 0x344 = 0x0000   R 0x346 = 0x0000   R 0x1b0 = 0x0000
W 0x344 = 0x0080  W 0x346 = 0x0000   R 0x344 = 0x0080   R 0x1b0 = 0x0000
W 0x344 = 0x0080  ... (repeats)
```

12,784 iterations in ~33 s. The driver pokes `0x344` bit 7, then waits on ADMAS `0x1b0`, which only ever echoes its
own written value. Full control map now measured: writes cover `0x180-0x1b2` (volumes, `0x198/0x19a`, TSA `0x1a8`,
`0x1ac=0x0707`, ADMAS `0x1b0=0x0002`), `0x1c0-0x1f2` (pitch-mod/noise/reverb params, `0x1c2/0x1ce/0x1da=0x2800`) and
`0x344`; reads cover the same plus `0x1e4-0x1f2`. `0x344` is handled nowhere in the engine - it was an inert store.

### 0158 - Attempt: satisfy the ADMAS bit. Reverted - it hung the driver

Modelled the `0x344` bit-7 write as "set ADMAS bit 0x80". The handshake fired once
(`[spu2:dma] core0 ctrl=0x0080 -> admas=0x0080`) and the driver did leave the busy loop - but then blocked waiting for
the transfer-complete interrupt: `run_0158.log` stopped at 23,657 lines with `spu2:mix=0`, no state dump at all
(mixes never reached 2000) and a `[iop:sema] SIGNAL id=1 / WAIT id=4 tid=7` loop. Build 184 had reached the mixer by
line 37,820 in the same wall time, so this was a regression, not progress.

Reverted. `0x344` bit `0x80` is already the engine's own DMA-complete flag (`iop_memory.cpp`, 0114): it is set when a
SPU2 CHCR transfer starts, written into `m_hardware` and mirrored into the core. The driver's repeated
`W 0x344 = 0x0080` is therefore most likely a write-1-to-clear acknowledge of that flag, and the honest next model is
*clear* on that write (then let the next armed CHCR set it again), not "set ADMAS".

### 0159 - Verification after the revert

Build 186, 45 s run (`run_0159.log`): 56,903 lines, `spu2:mix=5`, `keyon=0`, `sndn=62`, log still ending in normal
arm/sema traffic. Back to the pre-0158 behaviour, so the revert is clean and no earlier finding is disturbed.

### 0160 - Three attempts to answer the driver's `0x344` handshake. All failed, fully reverted

Attempt A (build 187): hooked the write in `writeHardware32`. Never fired - `[spu2:xfer]` count 0 - because the
driver's two stores (`0x344`, then `0x346`) are 16-bit.

Attempt B (build 188): moved the hook into `write16`'s SPU2 branch, right where `m_spu2.write32(aligned, ...)` is
called. Still `xfer=0`, so the writes take a third path (byte stores merging into the same word).

Attempt C (build 189): made the core itself flag the handshake (`IopSpu2::takeDmaHandshake`, set in `writeRegister`
when offset `0x344` receives bit 7) and serviced it from the emulator's step loop (`IopMemory::pollSpu2Handshake`),
which no memory path can bypass. It fired:

```
[spu2:xfer] admas=0x0080 irq=36
```

One handshake, and then the same regression as 0158: `spu2:mix=0`, log dead at 22,271 lines in the
`[iop:sema] SIGNAL id=1 / WAIT id=4 tid=7` loop, against 86,801 lines in a comparable untouched run.

Conclusion: `0x344` is **not** a request the driver is waiting for an answer to. Every time it is answered the driver
leaves its busy loop and blocks permanently somewhere else, so the loop is a *retry* condition, not the missing
event. Fully reverted (grep for `pollSpu2Handshake`/`takeDmaHandshake`/`kCommonDmaStatus` = 0 occurrences in all three
files) and verified: build 190, 40 s run = 53,147 lines, `spu2:mix=5`, `keyon=0`, `xfer=0`.

New reading of the loop: poke status, check ADMAS; ADMAS stays clear because the transfer it is retrying is one the
engine never queues, not because a flag is missing. The next step is therefore to identify *what it is trying to
transfer* on the iterations around a poke - log the neighbouring register writes with the caller's PC - instead of
answering the handshake blind. Answering it has now cost two builds and two reverts, so it is closed as a dead end.

### 0161 - Found what the driver moves, and killed the retry loop (audio still silent)

Two things were added, and one of them is real progress.

**1. Arm log (`[dmaq]`).** Every SPU2 channel CHCR write that actually starts a transfer now records its channel,
source address, word count and BCR. In a 46 s run the driver only ever moves from one fixed IOP buffer:

```
[dmaq] ch=0 src=0x083280 words=111248 bcr=0x1b290010 auto=0   <- this is the 444,992-byte block from 0155
[dmaq] ch=0 src=0x083280 words=42032  bcr=0x0a430010 auto=0
[dmaq] ch=0 src=0x083280 words=14400  bcr=0x03840010 auto=0
[dmaq] ch=0 src=0x083280 words=304    bcr=0x04d90010 auto=0
[dmaq] ch=1 src=0x04be40 words=256    bcr=0x00100010 auto=1
```

So `0x083280` is the driver's single streaming buffer and the sizes vary per block; core1 (auto) moves a 1 KB
command/data block from `0x04be40`. Note `auto=0` on core0: those are **manual** block transfers, not auto-DMA.

**2. ADMAS busy/idle cycle.** The CHCR arm path set the completion status bit but never wrote ADMAS (`0x1B0`), which
is the bit the driver polls - that is why its loop (0157) could never end. It is now set when a block is armed and
cleared when the scheduled transfer event is taken (`IopMemory::completeSpu2Dma`, called from `takeDmaStart`), i.e. a
busy -> idle cycle tied to a real transfer, not a latch. This is deliberately different from 0158/0160: those
answered a register poke, this answers an actual armed transfer.

**Result.** The retry loop is gone: `[spu2:spin]` is 48 lines (24 W + 24 R, just the capped first events) where 0157
measured 12,784 laps in 33 s, and there are no longer enough `0x344`/`0x1B0` reads to appear in the histograms at all.
The game stays alive - 52,960 log lines in 48 s, comparable to the 53,147 of a healthy build - so unlike 0158 this
does not deadlock.

**But audio is still silent:** `keyon=0`, `[spu2:mix] frames=800 peak=0`, and voices still carry nothing but
`pitch=0x3fff` (volL/volR/ADSR/loop all zero). So the transfers and the channel handshake were not the last barrier:
the driver gets its data in and then never programmes a single voice.

**Next target:** the sndn2drv command path. `sndn` returns cleanly (62 calls, 0155) and the driver arms correct
transfers, yet no `writeRegister` ever carries a voice volume/ADSR - so the failure is upstream of the SPU2: either
the reply the driver reads from its command buffer is never filled in, or it is filled with something it rejects.
Instrument the sndn reply buffer after each call and compare against the values it then writes to the SPU2.

Note: `[spu2:state]` dumps and the read/write histograms did not appear in this build's log at all, which needs
checking before the next round of instrumentation - the dump hook may no longer be reached.

### 0162 - The game only ever sends two sound commands, and every reply is zeros

Widened the sndn dump from the first 18 calls to the first 120 and added `[sndn:recv]`, which reads back the reply
buffer *after* the RPC framework copies it into the game's receive address - i.e. what the game actually gets.

A 50 s run produces exactly two distinct commands:

```
    119  0x64   reply size=512   w0=00000000 w1=00000000   (every single one zero)
      1  0x65   reply size=64    w0=00000000 w1=00000000
```

So the whole audio conversation between game and driver is one `0x65` and then `0x64` 119 times, and **not one reply
carries a non-zero word**. `keyon=0` throughout; log healthy at 54,830 lines.

Two readings, and they need one more measurement to separate:

1. The zeros are normal (a status block the driver leaves empty) and the driver's real output is the SPU2 DMA path -
   in which case the silence is in the driver's own state machine, not in RPC.
2. `0x64` is the stream request and its reply is supposed to carry audio; it returns zeros, so the driver plays
   nothing - in which case the bug is that `returnPointer` (the pointer the guest hands back) points at a zeroed
   block we then copy out.

The `[sndn]` line already records `bufr` (the driver's own buffer) and `bw` (its first two words), so the next run
can settle this by comparing `bw` against the zeroed `recv` values: if the driver's buffer has data and the reply is
zero, we are copying from the wrong pointer.

### 0163 - Feeding the game the driver's real buffer contents breaks it. Reverted

`[sndn:src]` showed the returned pointer (`0x4fca0`) and the driver's buffer (`0x4fda0`) are different regions, and the
returned one frequently holds live values (`w=00000001`, `w=00174d80`), not just zeros. Forcing the reply to come
from the driver's buffer made every reply non-zero (`120/120`, `w0=00000032 w1=0000000a`) - and the game **hung**:
18,913 log lines instead of ~54,830, `spu2:mix=0` (mixer never ran once). Fully reverted; verified after rebuild:
mixer running again, `keyon=0`, `[sndn:recv]` zero again.

So the zero replies are what the game expects from these two commands (`0x65` once, `0x64` 119x). The driver's real
audio path is the SPU2 DMA one, and that is already working (444 KB etc.). The remaining gap is inside the driver's own
state machine, not in the RPC reply. Do not re-try substituting reply sources.

### 0164 - Who actually runs: SNDN2DRV holds 70% of the IOP, and its mixer is live

Added an env-gated PC histogram (`APE2_IOP_PC=1`, 1 instruction in 64, 16-byte buckets, dumped with a module map).
Result over 40 s, 1,265,664 samples, 722 distinct code regions - and *zero* execution outside a loaded module:

```
mod9 @0x46d00  70.3%   = SNDN2DRV.IRX  (from the load log: id=9 path="cdrom0:\APE2_USA\MODULES\SNDN2DRV.IRX;1")
mod1 @0x10000  13.2%   = the kernel
mod6 @0x3e600  10.0%
mod8 @0x42200   4.4%   = LIBSD.IRX
mod4 @0x39f00   1.5%
```

Half the entire IOP's time (52.5%, five buckets at 132,320 samples each) is one loop at `0x4a1f0`-`0x4a230`.
I assumed a spin and disassembled it from a live RAM dump instead - **it is the software mixer**:

```
0x4a1fc  lh   $s7, ($s0)         ; load a 16-bit source sample
0x4a204  mult $t5, $s7           ; left volume * sample
0x4a210  srl  $s0, $s0, 0xf      ; >>15
0x4a214  add  $s1, $s1, $s0      ; accumulate into the left output sample
0x4a218  sh   $s1, ($a1)
0x4a21c  mult $t6, $s7           ; right volume * sample
0x4a228  srl  $s0, $s0, 0xf
0x4a22c  add  $s1, $s1, $s0
0x4a230  sh   $s1, 0x200($a1)    ; right channel lives 0x200 past the left
0x4a238  bne  $s6, $a2, 0x4a1f0  ; next sample
```

So the driver is not stuck asleep and not spinning: it is continuously mixing voices into a stereo buffer, 0x20 of voice
state per iteration (the 0152 stride). Anything that concludes "the driver never runs" is wrong.
The open question is now concrete: are those volumes non-zero and is the source buffer real audio, or is it mixing silence?

### 0165 - The mixer is mixing real audio: source samples are non-zero, but only the LEFT channel has volume

Env-gated `APE2_MIXTRACE=1` samples the mixer once a second: voice struct pointer, source pointer, destination, sample
count, both volumes, and the first two 16-bit samples at source and destination.

```
[mix:trace] voice=0x4f508 src=0x4c32c0 dst=0x4c240 n=512 volL=0x4032 volR=0x0 | src=4492,2211 dst=0,0
[mix:trace] voice=0x4f508 src=0x4c9ec0 dst=0x4bef4 n=512 volL=0x4032 volR=0x0 | src=4492,2211 dst=0,0
[mix:trace] voice=0x4f508 src=0xc32c0 dst=0x4c430 n=512 volL=0x4032 volR=0x0 | src=-3378,-2364 dst=0,0
```

19 traces in 45 s (one per second, as designed), log healthy at 48,843 lines:

* `traces_with_nonzero_src=18` of 19 - **the source buffers hold real, changing audio**, not zeros.
* `traces_with_nonzero_vol=19` of 19 - the left volume is a real fixed-point value (`0x4032`; `0x4000` = unity).
* `volR=0x0` in every single trace - **the right channel gets no volume at all**.
* `distinct_voicestructs=1` - only one voice structure (`0x4f508`) is ever mixed.
* `dst=0,0` is expected: it is read at loop entry, before this iteration accumulates into it.

So the audio pipeline is demonstrably alive from the game's data all the way into the driver's mixer. Two new concrete
questions, in order: (a) why the right-channel volume is zero, and (b) whether the driver's key-on code (SPU2 `0x1F801DB8`)
is ever executed at all - which the 0164 histogram can answer by address.

### 0166 - Locating the driver's SPU2 register access by offset

Immediate-based scans (`lui 0x1f90`) find nothing: the IOP never builds the SPU2 base as a literal, so the
base must come from a data word (LIBSD keeps it in memory). Instead the search used the known offset - the driver
provably writes `0x344` (ADMAS, 0157) - and matched every store whose offset fits the SPU2 register layout.
Matches: 0 stores, printed with module attribution and whether the 0164 histogram ever ran that code.


### 0167 - Who writes the sound chip, and what never does: 71 writer sites, all in LIBSD, zero key-on

Offset- and immediate-based disassembly scans both came up empty (the IOP never builds the SPU2 base `0x1F900000` as a
literal; LIBSD keeps it in a data word), so the measurement moved into the emulator: `IopMemory::s_currentPc` is set in
`step()`, and every 16-bit SPU2 write logs its offset, value and writing PC under `APE2_SPU2_WPC=1`.

35 s run, 400 logged writes, 71 distinct writer PCs - **every one of them inside LIBSD** (`0x45a00`-`0x45e40`,
module base `0x42200`). Sample of the mapping:

```
pc=0x45a04 off=0x1ac   x8     (per-voice parameter, core 0)
pc=0x45bc0 off=0x5a4          (core 1 voice parameter)
pc=0x45bcc off=0x1a4
pc=0x45bf0 off=0x342          (ADMAS-adjacent)
pc=0x45b00 off=0x180          (voice pitch/start)
```

**`any_keyon_write=0`** - across the whole run nothing writes `0x1b8`/`0x1b9`/`0x1bc` (KEYON/KEYOFF). Combined with 0164/0165
(mixer running, real samples, left volume set) the picture is now consistent and narrow:

* the game's audio reaches the driver,
* the driver's software mixer processes it with a live volume,
* LIBSD writes per-voice parameters to SPU2,
* and the one write that would make a voice audible - key-on - is never issued by any code anywhere.

Next: disassemble LIBSD around `0x45a00`-`0x45e40` to find the key-on store and the branch that skips it.

### 0168 - The complete map of which SPU2 registers the game can ever write, and KEYON is not among them

Three scanning bugs had been hiding the truth, and all three are now understood (so they are not retried):

1. the base is the **uncached alias `0xBF900000`** (`lui $v1,0xbf90` at `0x45a2c`), never `0x1F900000`;
2. a full-RAM `md.disasm` sweep stops at the first undecodable word unless `skipdata=True` is set;
3. `ori $v1,$v1,0x19a` - the immediate is the *last* field, not the second (indexing `[1]` silently parsed `$v1`).

With all three fixed, all 73 SPU2 registers that any code in IOP RAM constructs are:

```
core0 voices : 0x180 0x182 0x184 0x186 0x188 0x18a 0x18c 0x18e 0x190 0x192 0x194 0x196 0x198 0x19a
               0x1a0 0x1a2 0x1a4 0x1a6 0x1a8 0x1aa 0x1ac 0x1ae
core0 control: 0x1b0 (MMIX)   0x2e0 0x2e2   0x33c 0x340 0x344 (ADMAS)
core1        : 0x580-0x59a 0x5a0-0x5a6 0x5b0 (MMIX)  0x6e0 0x6e2  0x73c 0x744
core2/3      : 0x760-0x76e 0x788-0x796 0x7c0-0x7ca 0x800
```

**There is no `0x1b8` and no `0x1bc` anywhere in that list** - not as a store offset, not as an immediate, in any module.
And the 0167 write-PC log (authoritative, taken at runtime) shows 71 writer sites, all in LIBSD, none writing key-on.

So it is not a matter of a branch being skipped: **no code the game contains ever turns a voice on**. Every voice parameter
is programmed (pitch/start/ADSR at 0x180-0x1ae, and even the mixing register MMIX at 0x1b0), but the one register that
starts playback is never touched by anything.

That reframes the bug: either (a) LIBSD's key-on path computes `0xBF9001B8` at runtime from a base that is not an immediate
(the remaining possibility, testable by trapping any store whose effective address is `0xBF9001B8`), or (b) the title is
meant to receive audio through a path our SPU2 core does not model and the game's own expectations differ from real hardware.

### 0169 - What the driver polls, and the zero it gets back

Mirrored 0167 on the read side: `APE2_SPU2_RRD=1` logs every 16-bit SPU2 read as offset, value returned and reading PC,
and every 32-bit read above `0x300`.

35 s run, 400 reads captured (the whole cap), 0 32-bit reads, log healthy at 42,873 lines:

```
      5 0x0a  val=0x0 pc=0x450d0        (voice 0 volume L)
      5 0x3a  val=0x0 pc=0x450d0
      5 0x4a  val=0x0 pc=0x450d0
      5 0x5a  val=0x0 pc=0x450d0
      ...
      5 0xfa  val=0x0 pc=0x450d0        (stride 0x10 -> one read per voice, 24 voices)
```

214 of the reads come from a single instruction, `0x450d0`, which walks the per-voice block with a 0x10 stride and reads
the voice's volume field - **every one returns 0**. The remaining reads come from `0x45ab8`-`0x45b2c` (24 each), the
core1 equivalents.

So the driver inspects the voice table to decide what to do, and sees an entirely empty/zero voice state. Combined with:

* 0167: no code anywhere writes KEYON (`0x1b8`/`0x1bc` absent from all 73 addressable SPU2 registers),
* 0168: the register map proves key-on is never constructed,
* 0165: the software mixer does produce real samples with a live left volume,

the most probable chain is: the driver writes per-voice state, then reads the voice table back to decide whether to start
playback, gets zeros because those particular per-voice registers were never populated, concludes "nothing to play", and
never keys on. **The next measurement is the pair of writes that should set those volume fields** - offset `0x0a + 0x10*i`
and its core1 twin `0x40a + 0x10*i` - and whether they are issued at all or land somewhere our register file does not
return from.

### 0170 - The driver programs 24 voices' pitch/address/ADSR - but never their volume, and never key-on

Full offset inventory from the 0167 write log (400 writes, 71 sites, 377 distinct registers):

* **0x000-0x178, stride 0x10** - all 24 core-0 voices are programmed, but only the low sub-offsets
  `+0x0, +0x2, +0x4, +0x6, +0x8` (pitch, start address, ADSR1, ADSR2, envelope). **`+0x0a` (volume L) and `+0x0c`
  (volume R) are never written for any voice** - and their absence is exactly what the 0169 read loop at `0x450d0`
  sees as zeros.
* **0x180-0x1ae** - core-0 common block (master volume etc.), e.g. `0x19a=0x8000`, `0x1a4=0xffff`, `0x1a6=0xff`,
  `0x1ac=0x707`.
* **0x1b0** - MMIX written.
* **0x1c0-0x2d6** - the effects/reverb block, written repeatedly.
* **0x340-0x344** - ADMAS, the DMA cycle that 0161 fixed.
* **0x400-0x578** - core-1 voices, same pattern (pitch/addr/ADSR only); **0x580-0x5b0** core-1 common;
  **0x5c0-0x6d6** core-1 effects; **0x6e0/0x6e2**, **0x760-0x76e**, **0x788-0x796**, **0x7c0-0x7ca** further cores.

So the driver performs full voice setup *except* the two volume registers - and the volume values it should use are
sitting in its own mixer structures (0165: `volL=0x4032`). Nothing writes them to the chip, and nothing keys on.

Two readings remain, and the next run separates them:

1. The driver writes volumes only at note-start (inside a path that our unattended run never reaches because it sits on a
   screen that plays only the streamed voice the mixer handles), or
2. our per-voice register file does not accept/return `+0x0a`/`+0x0c`, so the driver's volume writes are being dropped
   before they land - which the write log would show as an offset that never appears.

The decisive test: run with the user actually in gameplay with music, and check whether `+0x0a`/`+0x0c` and `0x1b8` ever
appear in the write log. If they appear in gameplay but not at idle, this is reading (1) and audio may already work in-game;
if they never appear, the missing piece is inside our register handling.

### 0171 - Widened the window to 20,000 events: still no volume, still no key-on

The 400-entry log cap was a confound, so it was raised to 20,000 on both the write and read sides and the run repeated.
45 s, log healthy at 68,966 lines, mixer still running:

```
total write events: 603      distinct registers: 515
core0 volume-L writes: NONE          core1 volume-L writes: NONE
keyon writes 0x1b8/0x1bc/0x5b8: NONE
```

603 write events and not one of them is a per-voice volume or a key-on. This is no longer a windowing artefact: over the
first 45 s the game programs 515 distinct SPU2 registers and never touches the two things that would make a voice audible.

### 0172 - Real bug found and fixed: our SPU2 voice fields were shifted four bytes from hardware order

Cross-checking the field order against the driver's own write pattern exposed a genuine emulator bug. Hardware orders the
voice block:

```
0x00 VxPITCH   0x02 VxADDR   0x04 VxADSR1   0x06 VxADSR2   0x08 VxENVX   0x0A VxVOLXL   0x0C VxVOLXR   0x0E loop
```

Our core had it volume-first (`0x00 volL, 0x02 volR, 0x04 pitch, 0x06 startA, 0x08 ADSR1, 0x0A ADSR2`), i.e. **every field
shifted by four bytes**. That is exactly why earlier dumps looked nonsensical - `pitch=0x3fff` with `volL=volR=0` - and why
the driver's writes at sub-offsets `+0,+2,+4,+6` (pitch, start, ADSR1, ADSR2) were landing in our volume/volume/pitch/start
fields. All voice accesses in the core go through named constants, so the fix is a clean renumbering plus a new
`kVoiceEnvCurrent = 0x08`. Applied and built as 202.

Result of the run after the fix: game healthy (48,698 lines), mixer running, and **`keyon` still 0, mixer output `peak=0`**.
So the layout fix is correct and worth keeping, but it is not sufficient - it does not by itself make the driver start
playback. The blocked item remains: nothing in the game ever writes `0x1B8` through the 16-bit path (and the 32-bit
`[spu2:reg]` path reports `keyon=0` too).

### 0173 - Closing the last instrumentation gap: there are no 32-bit SPU2 writes at all

"No key-on ever" rested on the 16-bit store path, and key-on is often written with a 32-bit `sw`, so that path was
instrumented too (`APE2_SPU2_WPC32=1`, logging at `writeHardware32` entry for addresses in the SPU2 window).

Result over 40 s: **`wpc32=0`** - not one 32-bit write to the SPU2 window occurs. The driver uses 16-bit stores
exclusively (603 events, 515 distinct registers, measured in 0171). The conclusion therefore stands on both paths:

* no code writes KEYON (`0x1b8`) or KEYOFF (`0x1bc`) by any width,
* 0x1b8/0x1bc are absent from all 73 SPU2 offsets any code in RAM can construct,
* per-voice volumes (`+0x0a`, `+0x0c`) are never written either.

Notes for whoever picks this up - two insertion mistakes happened and are worth not repeating:
`std::fprintf(stderr,` in this file is often the body of an **unbraced `if`**, so inserting a `static` declaration
immediately before the format string puts it in the wrong scope (C2065) and breaks the build; and inserting before a
*continuation* line of a multi-line `fprintf` splits the call (C2062). Anchor on the enclosing statement start, not on
the format string.

### 0174 - Why the driver looks "stuck": it isn't. Nothing ever asks it to play.

Disassembled the one instruction that produced 214 of the reads (`0x450d0`) and it is **not** a scan loop - it is LIBSD's
parameter-read helper, the whole function being:

```
0x450d0  lhu  $v0, ($a0)      ; read the 16-bit register at a computed address
0x450d4  jr   $ra
0x450d8  nop
```

The address comes from a table of core base pointers (`lw $v0, 0x6240($at)`), i.e. a generic `sdGetParam`-style accessor.
So the driver is asking "what volume does voice N have?", 24 times, and being told 0 each time - which is the **correct**
answer for voices that have never been started. It is not a status the driver is gating on; a zero here means "free",
and a voice allocator that finds every voice free is a healthy voice allocator.

Then a hole in my own instrumentation was closed: `write32` has its own SPU2 handling, so 32-bit stores never reached the
`writeHardware32` log I added in 0173. Logging was added at `write32` entry as well. Result over 40 s:

```
w32_events=0   whw32_events=0   keyon=0
```

**There are no 32-bit SPU2 writes at all.** Combined with 0171/0173 the conclusion now holds for every store width: the
driver uses 16-bit stores exclusively, and never writes key-on or key-off.

The consequence for where to look next is important: the driver is healthy and idle-with-a-playing-mixer, so the missing
step is *upstream* - the game never issues a command that results in hardware playback. Its entire sound conversation is
`0x65` once and `0x64` 119 times, answered with zeros (0162), and substituting real data broke it (0163). The driver
meanwhile mixes a voice internally (`voice=0x4f508 volL=0x4032`, real samples, 0165) and DMA-uploads the result into SPU2
RAM (0161), but no hardware voice is ever told to play it.

So the outstanding question is now precisely: which sndn command starts a hardware voice, and why does the game stop at
`0x64` instead of sending it? That is a driver-API question, not a register question.

### 0175 - BREAKTHROUGH: key-on was at 0x188 all along, and our core was deaf to it

Decoded SNDN2DRV's command dispatcher at `0x46e88`: command `0x64` calls `0x46f54` (byte copy), `0x49478` (the
2-core x 24-voice mix loop) and `0x49754`, then returns a pointer to **alternating 0x200-byte buffers**:

```
0x46ed4  lui   $v1, 5
0x46ed8  lw    $v1, -0x55e0($v1)   ; a counter at 0x4AA20
0x46ef0  andi  $v0, $v1, 1         ; new count & 1
0x46ef8  sll   $v0, $v1, 9         ; * 0x200
0x46efc  lui   $a0, 5
0x46f00  addiu $a0, $a0, -0x45c0   ; base 0x4BA40
0x46f04  addu  $v1, $v0, $a0       ; -> 0x4BA40 / 0x4BC40
```

Every other command returns the static buffer at `0x4AA40` (the `bufr=` seen since 0162). So `0x64` is "mix me a block",
and there is no separate "play" command - playback is meant to happen through the SPU2 hardware voices that LIBSD programs.

Then the register list from 0170 was re-read against the *real* PS1/PS2 layout: `0x180` MVOL_L, `0x182` MVOL_R,
`0x184` EVOL_L, `0x186` EVOL_R, **`0x188` KEYON(0-15), `0x18A` KEYON(16-23), `0x18C` KEYOFF, `0x18E` KEYOFF(high)**.
Our core had `kCoreKeyOn = 0x1B8`, so it was watching a register the game never writes. Confirmed by capture:

```
[spu2:wpc] off=0x188 val=0xffff pc=0x431e0
[spu2:wpc] off=0x18a val=0xff   pc=0x431e8
[spu2:wpc] off=0x588 val=0xffff pc=0x43204
[spu2:wpc] off=0x58a val=0xff   pc=0x43208
```

That is a full 24-voice key-on mask for core 0 and core 1, issued by LIBSD at `0x431e0`. The game keys on. It always did.

Fix applied: `kCoreKeyOn = 0x188`, `kCoreKeyOff = 0x18C`, plus `kCoreKeyOnHigh = 0x18A` / `kCoreKeyOffHigh = 0x18E`
handled as `bits << 16` (the high-voice half of the mask). Build 207.

Result: **`KEYONS=6`** where it had been 0 for the entire project history, `[spu2:keyon-hit] core0 bits=0x00ffff`,
`[spu2:engine] keyon core=0 voice=0..` - the engine now actually starts voices. Game healthy at 32,944 lines.

Remaining gap: the engine's own mixer still reports `peak=0`. At key-on time the logged voice state is
`at=0x00000 pitch=0 loop=0x00000`, i.e. these first key-ons happen during init before any voice is programmed, and the
per-voice volume registers (`+0x0a`/`+0x0c`) are never written at all (0171). So voices now start but have nothing audible
to play yet. Next: capture the voice state at the *later* key-ons and check what SPU2 RAM address they point at.

### 0176 - The six key-ons are libsd's init reset, not notes

Listing every key-on from build 207 (run_0180.log):

```
[spu2:keyon-hit] core0 bits=0x00ffff      \
[spu2:keyon-hit] core0 bits=0x00ffff       > 24-voice bank reset
[spu2:keyon-hit] core0 bits=0xff0000      /   (0x188=0xffff, 0x18A=0xff)
[spu2:keyon-hit] core1 bits=0x00ffff          core-1 equivalent
[spu2:engine] keyon core=0 voice=0..7 at=0x00000 pitch=0 loop=0x00000   (all params zero)
```

The accompanying writes are `0x188=0xffff, 0x18A=0xff` immediately followed by `0x18C=0xffff, 0x18E=0xff` - key-on then
key-off of the whole bank, which is exactly how libsd resets the voice state during initialisation. So:

* the remap in 0175 is correct and necessary - our core now *sees* the reset instead of missing it entirely,
* but no note-level key-on ever follows, and every key-on so far has `pitch=0, at=0, loop=0`.

That is consistent with everything else measured today: voices get pitch/start/ADSR programmed (0170) but never a volume
(0171), and no per-note key-on is issued. A voice with zero volume produces silence even when correctly keyed, so the
missing step is still the game/driver never programming a playable voice - the init reset is not it.

Note also `[spu2:auto] rearm query ... active=1` continues normally (14,800 queries), so the DMA cycle from 0161 still
works after the key-on remap; the change did not disturb it.

### 0177 - Command 0x65 decoded: it carries the game name and the PCM bank path, and the driver replies from 0x4ABC0

Decoded the full 64-byte payload of the single `0x65` the game ever sends:

```
hex  : 1e000000 00000000 415c5043 4d5c4247 00000000 00000000 50533b31 00533b31 40b33600 00000000 41504532 5f555341 03000000 01000000 01000000 00000000
ascii: ........ A\PCM\BG ........ PS;1 .S;1 @.6..... APE2_USA ........
```

That is an **init descriptor**: a length word `0x1e` (30), the bank path `A\PCM\BG`, some version words, and the game id
string **`APE2_USA`**. So `0x65` is "initialise for this title with this PCM bank", not a status poll - which supersedes the
earlier 0151 reading that sndn was never sent a path. It is sent one, exactly once.

The dispatcher's else-branch (everything that is not `0x64`) then does:

```
0x46f18  lui   $a0, 5
0x46f1c  addiu $a0, $a0, -0x55c0   ; 0x4AA40, the input struct
0x46f20  jal   0x4730c             ; parse it
0x46f28  sw    $v0, -0x21c0($at)   ; store the result at 0x4ABC0
0x46f30  lui   $v0, 5
0x46f34  addiu $v0, $v0, -0x21c0   ; return 0x4ABC0, NOT 0x4AA40
```

So the reply the game receives for `0x65` is the structure the driver builds at **`0x4ABC0`**, and our RPC layer hands back
whatever is at the guest's returned pointer. That pointer is 0x4ABC0, and the values read back were zero.

Also recorded from the same run: the core main volumes `0x180`/`0x182` are written **0** and never anything else, so even a
perfectly programmed voice would be silent at the master stage. Both facts point at the same place - the init handshake.

Next: disassemble `0x4730c` (the parser the `0x65` branch calls) to see what it produces into `0x4ABC0`, and compare that
structure against what the game expects; and find where the driver would set `0x180`/`0x182` from a master volume value.

### 0178 - 0x65 is only the RPC function number; the real command is 0x1E, and the reply struct is empty

`0x4730c` - the function the non-0x64 branch calls - is the driver's **real command dispatcher**. It reads the first word
of the request block and indexes a jump table:

```
0x47348  lw    $v1, ($v0)          ; command id = first word of the payload
0x47350  addiu $v0, $v1, -1
0x47354  sltiu $v1, $v0, 0x4f      ; 79 commands
0x47364  lui   $a0, 5
0x47368  addiu $a0, $a0, -0x5bf0   ; table at 0x4A410
0x47370  lw    $v1, ($v0)
0x47378  jr    $v1                 ; dispatch
```

The first word of the `0x65` payload is **`0x1e` = 30**, so the real command is **sndn command 30** ("initialise with this
title and PCM bank"), reached through RPC function `0x65`. Earlier entries that called this "cmd 0x65" were naming the RPC
function, not the sound command.

And the reply structure at `0x4ABC0` - the pointer the handler returns to the game - is **entirely zero** in the live RAM
image (32 words read, all `00000000`). So the init command runs, dispatches, and produces an empty result, which matches the
zeroed replies observed since 0162 and the fact that the game then only ever asks for mix blocks (`0x64`) and never sends
another command.

Combined with 0177 (main volume `0x180`/`0x182` written 0 and never anything else), the failure is localised to the init
handshake: the game initialises the driver with its title id and bank path, gets nothing back, and never reaches the
volume/play commands - which is why key-on (0175) only ever occurs as the libsd init reset.

Next: resolve jump-table entry 30 at `0x4A410` to see exactly what the init command stores into `0x4ABC0`, and what it
returns when the bank path is valid. That code path is small and now precisely located.

### 0179 - Command 30 (title init) decoded: reset, four registers zeroed, then it starts a thread at 0x47208

Jump table at `0x4A410` resolved (79 entries). Relevant ones: cmd 1 -> `0x47380`, cmd 2 -> `0x474d0`, cmd 3 -> `0x47628`,
cmd 4 -> `0x476d8`, cmds 5-8 -> `0x49160` (the error/exit stub), **cmd 30 -> `0x47e00`**, cmd 31 -> `0x47e7c`.

Command 30 is the title init the game performs exactly once (`APE2_USA`, bank `A\PCM\BG`):

```
0x47e08  lw    $a0, 4($v0)          ; the game-id / bank descriptor
0x47e0c  jal   0x4a294              ; parse the request string block
0x47e14  jal   0x4a320              ; reset
0x47e1c  jal   0x4a318  a0=0x24
0x47e24  jal   0x4a318  a0=0x28
0x47e2c  jal   0x4a318  a0=9
0x47e38  jal   0x4a2ac  a0=0x1900 a1=0     \  four registers
0x47e44  jal   0x4a2ac  a0=0x1b00 a1=0      > cleared to ZERO
0x47e50  jal   0x4a2ac  a0=0x1901 a1=0      > at init
0x47e5c  jal   0x4a2ac  a0=0x1b01 a1=0     /
0x47e68  lui   $a1, 4
0x47e6c  jal   0x4a2ec  addiu $a1,$a1,0x7208   ; 0x47208 -> a driver entry point
```

Two facts fall out:

1. **The init path zeroes four driver registers and never sets a master volume.** That is consistent with the SPU2 main
   volume registers `0x180`/`0x182` being written `0` and never anything else (0177). Silence at the master stage is a
   consequence of this command, not a coincidence.
2. The last call passes `0x47208` - an address inside SNDN2DRV - to `0x4a2ec`, which is the shape of a **thread create with
   that entry point**. So the driver starts its own worker thread here.

That lines up with the very first thing found in this whole investigation (0140: "the driver's main thread is asleep"):
if that thread does not run - or runs but never receives a command - the driver only ever answers the mix request `0x64`
and never advances to volume/play, exactly as observed.

Next: check whether the thread at `0x47208` actually exists and runs in our kernel (thread table, priority, stack), and what
`0x4a2ec` is - kernel import or local thunk. If our kernel refuses or parks that thread, that is the remaining root cause.

### 0180 - The init's thread-create call is a stub, and the worker thread it should create does not exist

Disassembled the four callees the init command uses:

```
0x4a2ec  jr $ra / 0x4a2f0 addiu $zero,$zero,0x15
0x4a318  jr $ra / 0x4a31c addiu $zero,$zero,6
0x4a2ac  jr $ra / 0x4a2b0 addiu $zero,$zero,7
0x4a294  jr $ra / 0x4a298 addiu $zero,$zero,4
```

These are **import trampolines** - two-instruction stubs carrying an import id (`0x15`, `6`, `7`, `4`) in the delay slot,
the standard IOP shape for a resolved library call. So init is:

* import 4/5/6 - request-string parse and resets,
* import 7 - a register write helper, called 4x with values `0x1900/0x1B00/0x1901/0x1B01` all zeroed,
* **import `0x15` with entry point `0x47208` - a thread create.**

Live IOP thread table 30 s in (`APE2_IOP_THREADS=1`, run_0181.log):

```
id=8  dormant  entry=0x40568  pc=0x0        (LIBSD)
id=9  sleep    entry=0x46e10  pc=0x46e70    (SNDN2DRV's request handler)
id=10 sleep    entry=0x4f910  pc=0x4f970
```

**There is no thread with entry `0x47208`.** The init command's thread-create either never ran or failed, and the driver's
own worker - the thing that would advance from "answer mix requests" to volume and playback - does not exist. Every thread
in the table is dormant, sleeping or delayed; nothing in SNDN2DRV is executing between RPC calls.

That is now the leading root cause and it explains the entire measurement history in one stroke:
`keyon` only ever as the libsd init reset (0175/0176), master volume written 0 and never again (0177), no per-voice volume,
and an audio conversation that consists solely of "initialise" + "mix me blocks" forever.

Next: check which IOP import id `0x15` maps to in our import table and why the create fails (priority/stack/thread limit) -
the thread table above is the direct evidence to chase.

### 0181 - The init calls LIBSD directly, and thread creation works fine (so that is not the cause)

The two-instruction stubs the init handler calls are not kernel calls at all - resolving each stub against the nearest
import table (`0x41E00000` magic, library name at +12) gives:

```
0x4a294 -> library "libsd..." ordinal 0     (sceSdInit)
0x4a2ac -> library "libsd..." ordinal 3     (call 4x with 0x1900 / 0x1B00 / 0x1901 / 0x1B01, arg 0)
0x4a2ec -> library "libsd..." ordinal 11    (called with a1 = 0x47208)
0x4a318 -> library "intrman." ordinal 0
```

So the init path is `sceSdInit` -> 4x a libsd switch/param call -> a libsd call carrying `0x47208`. The `0x1900/0x1B00`
values are libsd switch parameters (core-0 and core-1 pairs), not SPU2 addresses.

Thread creation is **not** the failure. `[iop:thr]` capture over 30 s shows 27 thread-library calls including
`ord=4` (CreateThread) with descriptors at `0x1FFD00`-`0x1FFFE8` and `ord=6` (StartThread) for ids 1..10; ids 9 and 10 are
the driver's own threads (`0x46e10`, `0x4f910`), and both exist in the live thread table. The earlier "no thread at
0x47208" conclusion is withdrawn: `0x47208` is an argument to a *libsd* call, not a thread entry point.

So the open question is now inside libsd: what do ordinal 3 (four times at init, with core-encoded params `0x1900/0x1b00/
0x1901/0x1b01` and value 0) and ordinal 11 (with `0x47208`) actually do, and does libsd's own state machine stop there.
Note that after the 0175 key-on fix, libsd's key-on writes ARE applied now, which they never were before.

### 0182 - The driver's libsd register encoding, decoded from LIBSD's own table

Built the argument trace (`[libsd:call]`, first 12 calls per ordinal) into build 208 and captured 68 calls. Resolving
each stub in the SNDN2DRV import table at `0x4a280` gives the exact ordinal, and disassembling LIBSD's targets shows the
encoding: `entry = (tableByteOffset) | core`, where `tableByteOffset = (a0 >> 6) & 0x3FC` indexes a pointer table of
absolute SPU2 addresses at `0x46240`, and bit 0 selects core 1 by adding `0x400`.

```
entry 0x13 -> 0x180 (core main volume)   entry 0x18 -> 0x188 (key on)
entry 0x14 -> 0x184                      entry 0x19 -> 0x18C (key off)
entry 0x15 -> 0x1A0                      entry 0x1A -> 0x190 (pitch mod enable)
entry 0x16 -> 0x1A4                      entry 0x1B -> 0x194 (reverb enable)
entry 0x17 -> 0x340                      entry 0x1C -> 0x2E0
```

Each write stores 16 bits at the pointer and bits 16-23 at pointer+2, which independently confirms the 0175 key-on
placement (`0x188` low + `0x18A` high byte).

So the four "suspicious zero" calls at init are `a0=0x1900/0x1901` -> key-off `0x18C` for both cores and
`a0=0x1B00/0x1B01` -> reverb enable `0x194` for both cores, all zero. That is ordinary init hygiene, **not** a mute; the
idea that those zeros were the cause is withdrawn. `a0=0x1B00` is reverb enable, not a volume.

Where the volume zero really comes from (32 s run, `APE2_SPU2_WPC`): exactly one write to `0x180`/`0x182` = 0 at
`pc=0x43ad0`, i.e. inside LIBSD during `sceSdInit` (ord 4, one call), plus the one-time bank reset
`0x188=0xffff`, `0x18A=0xff` at `pc=0x431e0`. Nothing else touches volume or key-on for the whole run.

Full libsd traffic in 32 s: ord 4 x1, 5 x16, 6 x83081 (a spin poll returning `0x3fff`), 7 x4, 9 x2, 11 x3, 17 x5, 18 x1,
19 x1730, 20 x4153, 21 x2, 23 x2. ord 21 is `0x47208`/`0x47258` - the driver installing SPU2 interrupt handlers on cores
0 and 1, so those addresses are handlers, not thread entries (confirms 0181).

The driver is idle: apart from init, the only SPU2 traffic is transfer address/control (`0x1A4`, `0x1A6`, `0x1A8`), a
handful of pitch writes (`0x14`), and core-1 reverb registers (`0x760`-`0x78A`). No voice volume writes, no key-on with a
real voice mask. Combined with 0162 (the EE side only ever sends fn `0x65` once and `0x64` "mix a block" 119 times over
95 s, ~1.3 per second against the ~30 per second audio needs), the game's audio pipeline is not advancing past init.

Next: the interrupt path is the prime suspect - the driver registered SPU2 handlers at `0x47208`/`0x47258` and is spinning
83k times on a status poll reading `0x3fff`, so check whether SPU2 ever raises those handlers and whether the handler PCs
ever execute.

### 0183 - The SPU2 interrupt path is dead, and the mixer loop cannot be the stall

Ran build 208 with `APE2_SPU2_HIRQ` + `APE2_IOP_PC` (30 s). Two results:

1. **The driver's SPU2 interrupt handlers never execute.** The handler addresses it registered on cores 0 and 1
   (`0x47208`, `0x47258`) appear exactly once each in the whole log - inside the `[libsd:call]` argument trace - and never
   in the PC histogram. `APE2_SPU2_HIRQ` produced **zero** lines, so our SPU2 side raises no interrupt at all. The driver
   therefore has no completion signal and keeps spinning on its status poll (83k calls of libsd ord 6 reading `0x3fff`).

2. **The hot mixer loop is not an infinite loop.** Disassembled `0x4a1a4`-`0x4a258`:

```
0x4a1c0  move  $s6, $zero
0x4a1c4  srl   $s2, $t4, 0x10        ; $t4 = block length in bytes (high half = shift)
0x4a1c8  blez  $s2, 0x4a24c          ; skip voice when the count is <= 0
0x4a1f0  srlv  $s0, $s6, $s2
0x4a1f4  add   $s0, $s0, $s0
0x4a1f8  add   $s0, $t7, $s0
0x4a1fc  lh    $s7, ($s0)            ; source sample
0x4a200  addi  $s6, $s6, 2           ; byte counter
0x4a204  mult  $t5, $s7              ; left volume
0x4a20c  lh    $s1, ($a1)
0x4a218  sh    $s1, ($a1)            ; accumulate to left output
0x4a21c  mult  $t6, $s7              ; right volume
0x4a230  sh    $s1, 0x200($a1)       ; accumulate to right output
0x4a238  bne   $s6, $a2, 0x4a1f0     ; ends when the byte counter equals $a2
```

It exits when `$s6 == $a2` with `$s6` stepping by 2, so an odd `$a2` would hang it - but the EE side does receive its
`0x64` replies (119 of them, 0162), so the loop does terminate. It is simply expensive: 74,850 of 131,072 PC samples
after 30 s, i.e. the single hottest thing on the IOP, with every voice having volume 0 so the whole loop produces silence.

Status: still no audible output. Correct diagnosis order from here is the interrupt path first - with no SPU2 interrupt the
driver can never be told its transfers finished, so it never reaches the code that keys voices on or raises volume.

### 0184 - Correction to 0183: the SPU2 interrupt path works, my probe was dead code

`[spu2:hirq]` printing nothing in 0183 was **not** evidence of a missing interrupt. Those prints are gated on
`m_inSpu2Handler`, and `IopMemory::setSpu2HandlerContext()` - the only writer of that flag - is declared in
`iop_memory.h` and **never called from anywhere in the engine**. The gate is permanently false, so the probe could never
have fired. That measurement is void.

The `[spu2:auto]` accounting from the same run proves the opposite of what 0183 claimed:

```
[spu2:auto] armed irq=40 block=196608 cycles (5.33 ms)
[spu2:auto] dispatch attempt irq=40 enabled=1 handler=1
[spu2:auto] attempts=3800 deliveries=3800 enabled=1 handler=1
```

IRQ 40 (core-0 SPU2 DMA completion) is armed, dispatched and delivered **3,800 times in 30 s with a registered handler
and the vector enabled** - every attempt delivered, none dropped. So the interrupt reaches the driver and LIBSD's handler
runs. The theory that the driver was starved of completion interrupts is withdrawn.

What remains true from 0183: the mixer loop at `0x4a1f0` is byte-count terminated (not a hang), and it is the hottest
thing on the IOP with every voice at volume 0, so it is burning 70% of the IOP to produce silence.

Standing state: no audible output. The next thing to measure is the request rate and payload the EE side sends, since
`0x64` arrives ~1.3 times per second against the ~187 per second a 5.33 ms block implies, and the driver only ever mixes
one voice struct whose right-hand volume is zero.

### 0185 - Dead end avoided: the 0x3FFF is my own logging math, and the audio pump runs at 8 Hz

Followed the 83k-poll lead to `libsd` ord 6. The 24-voice x 2-core loop in SNDN2DRV at `0x47000`-`0x47150` builds
`entry = 0x500 | core | (voice << 1)` and calls the libsd read target (`0x4507c`), which resolves the entry the same way
the write path does: byte offset `(a0 >> 6) & 0x3FC` into the pointer table, plus `voice * 8`, plus `core * 0x400`. The
driver then mirrors the value into its own work area at `0x4BA40 + voice*4 + core*96 + (core&1)*0x200`.

**The `reg=0x3fff` in `[libsd:poll]` is a bug in my logging, not in the emulator.** That line computed the target as
`0x1F900000 + ((a0 >> 6) & 0x3FC)` and dropped the voice and core terms entirely, so all 48 polls read one fixed address
(`0x14`, voice 1's ADSR1) and reported whatever happened to be there. The 0x3FFF never came from a voice volume register
and there is nothing to fix. Also checked the one place the engine does write `0x3FFF` into a voice volume -
`IopSpu2::runSelfTest()` - which is a self-test only, and `reset()` zeroes voices through `Voice{}`. So fresh voices
correctly read 0.

Real finding from the same run: the EE side pumps audio at **239 `cmd=0x64` calls per 30 s = ~8 per second**, each 512
bytes. A 5.33 ms block needs ~187 per second, so the game's audio pump is running roughly 20x too slowly - it is not that
the driver mangles the audio, it is that almost no audio is ever asked for. Combined with `[spu2:mix] frames=800 peak=0`
on every block, the audible result is silence.

### 0186 - The game sends real audio commands, and two more of my numbers were wrong

Environment names matter: `APE2_RPC_PKTPAYLOAD` is not a switch that exists. The request payload dump is
`[sndn] payload`, printed unconditionally for the first three sndn calls, and the packet-window probe is
`APE2_RPC_PKTPROBE`. With the real logging, the payloads are substantial, not zeros:

```
cmd=0x65 64 bytes: 1e000000 00000000 415c50434d5c4247 00000000 50533b3100 533b3140 b3360000 00000000 415045325f555341 03000000 01000000 01000000 00000000
cmd=0x64 160 bytes: 32000000 0a000000 80080000 ... 28000000 00000000 00000000 28000000 01000000
                    00000000 00000000 14000000 00000000 ffff1f00 ... 14000000 01000000 ffff1d00
```

The `0x65` payload is the init descriptor already identified in 0177 (`0x1E`, path `A\PCM\BG`, `APE2_USA`).
The `0x64` payload is 160 bytes of real structure - `0x32` (50), `10`, `0x880` (2176), then records carrying
**`0x1FFFFF` and `0x1DFFFF`**, which are SPU2 RAM end addresses, plus counts of `0x28` (40). So the game is describing
SPU2 RAM regions to the driver, not asking for silence. The 512-byte reply it gets back is still all zeros.

Corrections to 0185: the "8 requests per second is 20x too slow" claim is withdrawn. The driver runs its own thread and
re-arms the auto-DMA completion 3,800 times per 30 s (~127 blocks/s), so playback cadence on the driver side is healthy;
the 8/s figure is how often the EE queries, not the audio rate.

Also: `APE2_SPU2_DUMP=<dir>` appends each core's *output stream* to `<dir>/spu2_coreN.bin`; it does not dump SPU2 RAM.
A check that globbed `*.bin` picked up `iop_0154.bin`, an old IOP main-RAM dump, so it answered nothing.

Where this leaves it: the game sends real audio commands that name SPU2 RAM regions, the driver streams 1 KB blocks into
core-1 SPU2 RAM every 5.33 ms, the completion interrupt is delivered every time - and no voice is ever keyed on, so our
mixer reports `peak=0`. The gap is specifically between "data is in SPU2 RAM" and "a voice is playing it".

### 0187 - The RPC reply path is not broken: the driver's silence is its own answer

Checked the reply path before changing it, and the proposed "pass a receive buffer" fix would have been a no-op. The
evidence is in the existing capture:

```
[sndn] cmd=0x65 send=64@0x1fffed0  bufr=0x4aa40 bw=0000001e 00000000  recv=00000000 00000000
[sndn] cmd=0x64 send=160@0x612040  bufr=0x4aa40 bw=00000032 0000000a  recv=00000000 00000000
[sndn] cmd=0x64 send=0@0x613040    bufr=0x4aa40 bw=00000032 0000000a  recv=00000000 00000000
```

`bw` (the words at `server.buffer`) holds `0x1e` for the init and `0x32 0x0a` for the block command - so the EE request
**is** delivered into IOP RAM intact. `recv` is read from `physical(returnPointer)`, and it differs from `bufr`, which
proves the guest's returned pointer is being honoured and read from; the reply plumbing works. What it returns is zeros,
which is the driver's own output, not a copy bug. The 4-argument server call is therefore not the defect and is left alone.

Also visible: after the first 160-byte command, the game polls with `send=0` and **alternates two receive buffers**
(`0x612040` / `0x613040`) - a normal "hand me the next block" loop, 239 times in 30 s.

So the state at the end of this investigation: request delivery works, reply routing works, the DMA stream into core-1
SPU2 RAM works, completion interrupts are delivered, and the driver answers every block with silence because it mixes a
single voice whose right-hand volume is zero and never keys a playback voice.

Nothing was changed in this entry. No commit, no push.

### 0188 - The playback handlers never execute: the driver is not being asked in the form it recognises

Static reading of the SNDN2DRV dispatcher in `iop_0154.bin`, cross-checked against every log. Three results:

1. Dispatch *does* reach handler bodies. The code at `0x47e68` does `lui $a1,4; addiu $a1,$a1,0x7208` then `jal 0x4a2ec`,
   which is exactly the `[libsd:call] ord=21 a0=0x0 a1=0x47208` seen in the logs; the `a0=0x1900/0x1b00/0x1901/0x1b01`
   calls (`jal 0x4a2ac`, ord 7) appear too. So requests are delivered and the dispatcher runs.
2. The reply pointer is `frame[0x28]` - the shared epilogue `0x49168` is `lw $v1,0x28($fp); move $v0,$v1; move $sp,$fp`.
   That is why `recv` reads a valid but empty buffer: the driver returns whatever default pointer is in that slot.
3. **The playback handler at `0x480d0` has never run.** Its first call is `a0=1, a1=2` to ord 18; the only ord-18 lines in
   the logs are `a0=0x1 a1=0x10` (2 occurrences, all runs). Its later calls are `ord 5` with `a0=0xF81` and `a0=0x1081`;
   the string `f81` appears **zero** times across every run log. Exhaustive list of ord-5 calls ever made: params
   `0x980/0x981/0xA80/0xA81/0xB80/0xB81/0xC80/0xC81` with values `0x3fff`, `0x0`, `0x1999` - i.e. four channel-volume
   pairs fading between full, half-ish and zero, nothing else.

So the corrected diagnosis: this is not "the driver mixes silence". The driver initialises, runs its own streaming thread
and mixes a voice, but it never receives a command it recognises as playback - the handler bodies that would set up and
start voices are never entered. The remaining question is narrow and answerable: which field does the dispatcher use as
its command index, and what value does it expect. Next step is the dispatcher prologue (before `0x47e00`), where the jump
table at `0x4A410` is indexed - the `cmd - 0x1e` mapping assumed earlier is now disproven, since `0x64` would then have
reached `0x480d0` and we would see `a1=2` on ord 18.

No behaviour changed in this entry; nothing built, nothing committed.

### 0189 - The driver protocol is fully decoded, and it works: the game never asks for playback

Dumped the whole dispatch table at `0x4A410` (79 entries, 41 of them the empty handler at `0x49160`) and matched it
against the payloads we capture. The index is `payload[0] - 1`, not the RPC function number:

* init: payload[0] = `0x1E` -> index 29 -> `0x47E00`, which is the handler that emits `ord=21 a1=0x47208` - and that
  exact call is in the logs. The mapping is proven by observation.
* block: payload[0] = `0x32` -> index 49 -> `0x47A84`. That handler switches on `payload[1]`: `8` computes
  `payload[2]/6 | 8` and calls ord 11 with the halfword at `+0xC`; `0xA` calls ord 11 with `a0=0xA` and the halfword at
  `+8`. The captured payload is `0x32, 0x0A, 0x880`, so it takes the `0xA` path, and `[libsd:call] ord=11 a0=0xa
  a1=0x880` is in every run log. Second proven mapping.

So request delivery, dispatch, argument reading, libsd calls and SPU2 programming all work for every command the game
actually sends. What the game never sends is a voice/sequence command: entries 59-66 (`payload[0]` = `0x3C`..`0x43`,
handlers `0x4860C`..`0x48F50`) are never requested. The remaining 112 calls per run are empty-payload polls returning
zeros.

That moves the defect out of the driver and out of our emulator's RPC/SPU2 plumbing, and into the game's own audio
manager: it initialises the driver, sets one volume (`0xA = 0x880`), and then never starts anything. The next question is
what the game is waiting for before it triggers playback - with a disc-streaming title the first suspicion is the sound
bank (`A\PCM\BG`) never arriving from CDVD. Checked with `APE2_IOP_CDVD=1` in the run that follows this entry.

### 0190 - Disc side is clean: 26 banks found, streaming delivers, and the music file is never read

`APE2_IOP_CDVD=1` run (`run_0189.log`, 45,917 lines, 60 s). Results:

* 26 sound banks searched (`TITLE.SPS`, `STAFF.SPS`, and `PCM\DEMO\BS*_?.SPS`), each logged twice (call + `:ok`), so the
  52/50 split I first read as "2 failures" is 26 files with 25 ok and **zero** `sceCdSearchFile:fail` lines. Disc search
  is working. `\APE2_USA\PCM\BGM\TITLE.SPS;1` resolves to lsn `0x158BEB`, size `0x1771800` (24 MB), 11,999 sectors.
* `sceCdStStart lbn=0x5b9f0 rate=2700 buffer=128 bank=16`, then 32 `sceCdStRead` calls with `requested == accumulated ==
  chunk` on every single one. Streaming delivers exactly what the game asks for.
* `TITLE.SPS`'s LSN `0x158BEB` appears only in the two search lines and never in a read. The game locates the music and
  then never loads it, because loading follows playback and playback never starts.

So every emulator-side link is now verified by measurement: RPC delivery, driver dispatch (twice proven against the
driver's own code), libsd calls reaching the emulated SPU2, key-on/key-off register addresses, disc search, and disc
streaming. Nothing in the chain is dropping data.

The one anomaly left is the reply itself. The driver's epilogue returns `frame[0x28]`, and the words our log reads at that
pointer are zero, while the send buffer at `0x4AA40` still holds the request (`0x32 0x0A`). On that evidence the returned
pointer is *not* the send buffer. If the game inspects the init reply and treats zero as "sound device unavailable", it
would stop before ever issuing voice commands - which is exactly what we see.

Prediction that makes this falsifiable: entries 59-66 of the table (`payload[0]` = `0x3C`..`0x43`, the voice/sequence
commands) should start appearing in the log as soon as the driver's reply is one the game accepts. That is the next
experiment: log the actual returned pointer value, and compare it against the send buffer.

No behaviour changed; nothing committed. Build 208 unchanged, no process running.

### 0191 - The game asks for 512 bytes of PCM per poll and gets 512 zeros - and it polls ~180x too slowly

The `[sndn:recv]` lines settle the shape of the conversation: every `cmd=0x64` call carries a **512-byte receive buffer**
(`cmd=0x65` carries 64), and we fill it - with zeros. So the game is explicitly asking for one block of PCM and receiving
silence, on a path we have now shown to be working end to end.

Counting the same run gives the number that matters: 112 polls in 60 s at 512 bytes each is 240 stereo frames per second,
i.e. **about 5.4 ms of audio requested per second of real time - a factor of roughly 180x below real time** (44,100 frames/s
needs ~86 polls/s at this block size, not 1.9).

That reframes the whole problem. Even if the driver were producing perfect audio, the game consumes it ~180x too slowly, so
almost nothing could ever be audible. And it explains, without contradiction, every measurement gathered so far:

* the driver's own streaming thread runs fine (576 DMA completions, blocks in SPU2 RAM every 5.33 ms);
* no voice is ever keyed with a real mask, because the sequencer advances per block consumed, and blocks are consumed ~2x/s;
* `[spu2:mix] peak=0`, because a starved mixer has nothing to advance;
* `[mix:trace]` showing one voice with a nonzero left volume, because that is the voice the sequencer would use next.

So the EE-side audio consumer is not being scheduled. The defect is very likely in scheduling, not in sound at all - the
game's audio thread runs far too rarely, and the sound stack has been silently correct underneath it.

Next step: measure EE thread scheduling during a run (wake-ups per second for the audio thread, and where its time goes),
rather than any further work inside the driver or SPU2.

Nothing changed; nothing committed. Build 208, no process running.

### 0192 - Round-robin scheduling changes nothing, and the poll count turns out to be fixed, not a rate

Ran 45 s with `APE2_TIMESLICE=1` (round robin in `EeScheduler.cpp:546`) against the 60 s baseline, same binary:

| metric | baseline 60 s | round robin 45 s |
|---|---|---|
| `cmd=0x64` polls | 119 (1.98/s) | 119 (2.64/s) |
| calls with size > 0 | 5 | 7 |
| `[spu2:keyon-hit]` | 6 | 6 |
| `[spu2:mix]` with peak != 0 | 0 | 0 |

The scheduler change made no difference to anything audio-related, so the "EE audio thread is starved" hypothesis from 0191 is **disproven**. The 185x-too-slow figure in that entry was also the wrong reading: both runs make exactly **119** polls regardless of how long they run, so this is a fixed count, not a rate. The game asks for 512-byte blocks a fixed number of times and then stops asking.

That is a different and more useful fact. A caller that polls a fixed number of times and stops is not starving - it is either filling a queue of known size or bailing out of a loop on a condition. Since the replies it gets are all zeros, "bailing out because the reply is empty" remains the best-supported explanation, and the reply is the one thing in the chain not yet proven correct.

Status: no behaviour changed, nothing committed, build 208, no process running.

### 0193 - The driver's reply pointer is real, and the reply is empty (build 209)

Added `ret=0x%x` to `[sndn]` (iop_rpc.cpp) so the reply source is visible instead of guessed. Result: `ret` alternates exactly with the caller - `send@0x612040 -> ret=0x4bc40`, `send@0x613040 -> ret=0x4ba40`, init `-> 0x4de40`. Those are the same structures `[sndn:status]` reported writes to, i.e. genuine per-caller reply buffers, not garbage from treating a status code as a pointer.

Every `[sndn:recv]` is still `w0=0 w1=0`, and the driver's own buffer still holds the previous request (`bufr=0x4aa40 bw=00000032 0000000a`) even on the `send=0` polls. So the reply *routing* is correct and the reply *content* is empty. That makes the empty reply a symptom, not the cause, and retires the "reply is the last unproven link" theory from the previous entry.

### 0194 - Key-ons carry real masks, and the voices they start are completely unprogrammed

`APE2_SPU2_STATE` prints only at shutdown, so with a 25 s hard kill it produced nothing (no `[spu2:voice]`, no `whist`/`rhist`). What the run did show:

- key-on masks are real and complete: `core0 bits=0x00ffff`, `core0 bits=0xff0000`, `core1 bits=0x00ffff`, `core1 bits=0xff0000`.
- the first key-on reads back `at=0x00000 pitch=0 loop=0x00000` for every voice.
- `[spu2:admas] idle word=0x1b0 now=0x0000` - ADMAS reads 0 (0161's busy/idle cycle is idling).
- `[spu2:switch]` shows the driver writing ADMAS 0 repeatedly.

### 0195 - No voice is ever keyed with a sample address: the music is streamed, not voiced (build 210)

Replaced the "first 8 key-ons" log with one that reports only *programmed* key-ons (`pitch`, start register or loop non-zero). Over 25 s: **`[spu2:keyon-v]` count = 0.** Every key-on in the run is the all-zero reset pattern. The driver never starts a note.

At the same time `[spu2:arm] arms=1800 fresh=731 stale=1269` - 731 blocks whose content differed on re-arm, i.e. a real, changing stream is being armed onto core-1 auto-DMA. Two code changes in iop_spu2.cpp: the programmed-voice log, and a start-register fallback in `startVoice` (`loopAddress == 0` now falls back to the start-address register instead of playing from address 0).

### 0196 - The streamed queue had no consumer at all (build 211)

`[spu2:queue] pushed=2000 played=0 dropped=1936 depth=64` - **`played` never advances.** The queue is filled by every arm and nothing ever drains it, so it overflows, drops 1936 blocks, and the mixer (which only mixes voices) returns silence. `audioOut=0.0s` for the whole run.

Fix in iop_memory.cpp: `pullSpu2Pcm` now drains the queue on top of the voice mix, with a per-block cursor, `played`/`framesOut` accounting and a `[spu2:stream]` peak log. After it, `[spu2:stream] filled=800/800 played=8 depth=0` - the queue drains and `dropped` stops growing.

But the drained audio is **all zeros**: `peak=0`, and the `APE2_SPU2_PCM` capture is 100% zero samples (2400 frames / 0.05 s captured). So the drain was a real missing consumer, but its source is empty.

### 0197 - There is no PCM anywhere in IOP RAM, and the driver reads an empty ring

`APE2_SPU2_DUMP` snapshots all of IOP RAM at arms 40/80/120 (~0.2-0.6 s) and taps the block the driver reads:

- `[IOP] SPU2 tap core1 src=0x0004be40 words=256 first=0000 0000 0000 0000 0000 0000` - the driver is arming from its ring and the ring is zeros.
- `0x4be40` and `0x4c240` (both ring halves) are `nonzero=0/512` in all three snapshots.
- A full 1 KB-aligned diff of snapshot 1 vs snapshot 3 finds only **two** changed regions: `0x040000` (peak 32640) and `0x076000` (empty block). `0x040000` is MIPS code, not audio - head bytes `f0ffbd27` = `addiu sp,sp,-16`, `0800beaf` = `sw fp,8(sp)`.
- Only 27 `[ape2:cdread]` reads happen in 25 s, and they are gzip assets (`1f8b0800`) into EE RAM at `buf=0x65xxxx`, plus a late `lbn=0x100000` IOP module reload. No stream start, no `PCM`/`SPS` read.

Conclusion: the game never begins audio streaming in this window, so the driver's ring is never filled, so the mixer and the queue only ever see zeros. The empty `[sndn:recv]` status reply stays the best candidate for why playback is never started, but the run shows the game is still in early asset loading, which must be excluded first.

Status: builds 209/210/211 made, three code changes in place, audio still silent, nothing committed, no process running.

### 0198 - The ring does fill; the earlier "no PCM" was measured too early (build 212)

Previous entry concluded there was no PCM anywhere in IOP RAM. That was wrong, and the error was the measurement window: the snapshot trigger fired at arms 40/80/120, i.e. within the first 0.6 s, when the game is still loading. Extended the trigger to a table `{40, 80, 120, 3000, 12000}` (arm ~3000 is about 16 s in) and ran 75 s.

- dump 1-3: both ring halves `nz=0/512 pk=0` - still empty at 0.6 s.
- dump 4 (arm 3000): ring1 `nz=512/512 pk=5960`, ring2 `nz=512/512 pk=4107`.
- dump 5 (arm 12000): ring1 `nz=512/512 pk=6419`, ring2 `nz=512/512 pk=6545`.
- final dump contains 536 PCM-like 1 KB blocks, e.g. `0x010000 peak=32735 nonzero=416/512`.
- 44 1 KB regions changed across the run, including `0x04bc00`, `0x04c000`, `0x04c400`.

So the music only starts roughly 15 s in, after the level/asset loads. The "no streaming ever happens" conclusion in 0197 is retracted; the queue-drain fix from 0196 is what lets it out.

Result with the fix (75 s run): `pushed=17800 played=9780 dropped=7956 audioOut=52.1s` and the `APE2_SPU2_PCM` capture is **52.93 s, peak 14398, 4,917,583 non-zero samples**. Audio is flowing.

### 0199 - The output is continuous audio at 57-60 fps, not a concatenation of glitched blocks

Added a discontinuity test on the capture: left channel, mean |x[n]-x[n-1]| across every 256-frame boundary vs the interior average. Concatenated/skipped blocks would raise the boundary figure sharply.

- build 212 defaults, 30 s run: `pcm 11.18s peak=14398 nonzero=96.2% boundary_ratio=1.00x` (boundary 1013.1 vs interior 1012.9).
- fps from `[perf]`: 57.5, 60.0, 56.9, 59.5.

Dropped blocks are discarded from the tail while playback consumes from the head, so the played stream stays contiguous. The `dropped` counter is surplus, not a gap in playback.

### 0200 - DMA pacing sweep: the calibrated 768 stays

`APE2_SPU2_ADMA_CYCLES` clamps to 32..100000, so the first attempt at 213000 was silently rejected and reproduced the default exactly - an invalid experiment, noted so it is not repeated.

| cycles/word | pushed | played | dropped | audioOut | nonzero | boundary ratio |
|---|---|---|---|---|---|---|
| 768 (default) | 4400 | 2027 | 2312 | 10.8 s | 96.2% | 1.00x |
| 1230 | 2800 | 1935 | 805 | 10.3 s | ~96% | 1.00x |
| 2000 | 1600 | 1076 | 523 | 5.7 s | 60.5% | 1.21x |
| 3000 | 1000 | 647 | 351 | 3.4 s | 40.2% | 1.23x |

Slower pacing reduces the drop counter but starves the reader once it passes ~1230 (`depth` falls to 1, content gaps appear at 1.21x/1.23x boundary ratio). 768 is the only value with both full continuity and no starvation, which matches 0071's calibration note. **No code change** - the drop counter is not audible and the calibrated value is kept.

### 0201 - Root cause of the silence, stated plainly

1. The game's music is streamed PCM, not SPU2 voices: `[spu2:keyon-v]` is 0 for entire runs, and every key-on is the driver's all-zero reset pattern. Mixing voices could never produce sound.
2. The streamed blocks are delivered by core-1 auto-DMA from the driver's ring at `0x4be40`; the ring only fills from ~15 s in.
3. `pullSpu2Pcm` mixed voices only and **never consumed the queue**, so every armed block was dropped (`played=0`, `dropped=1936`, `audioOut=0.0s`) for the whole of the earlier work. Fixing that consumer is what made audio audible.

Changes kept from this round: queue drain with `played`/`framesOut`/`[spu2:stream]` in iop_memory.cpp; start-register fallback and `[spu2:keyon-v]` in iop_spu2.cpp; `ret=` in `[sndn]` in iop_rpc.cpp; RAM snapshot triggers extended behind `APE2_SPU2_DUMP`.

Status: audio audible and measured (52.9 s captured, peak 14398, 96% non-zero, 1.00x continuity) at 56.9-60.0 fps. Build 212 is current. Nothing committed.

### 0202 - Two-minute run: audio is sustained, the rate question is settled by hardware (build 212)

Long run with `APE2_FRAME_PROF` and `APE2_SPU2_PCM`, 120 s wall:

- `[spu2:queue] pushed=32600 played=18221 dropped=14315 depth=63 underruns=0 audioOut=97.1s`
- capture: **98.45 s, peak 14398, 97.3% non-zero, continuity ratio 1.02x**
- silent seconds (<200 peak) : **1 of 98** (second 42 - a one-second gap, most likely a music transition)
- fps: 59 samples, **mean 57.4, min 41.4, max 60.0**
- disc reads: 35, last one still the `title` record at `lbn=0x5b9f0`

No drift appears over 98 s of continuous playback, and the block-duplication test (self-similarity at lags 256/512/768/1024 frames) reads -0.03/-0.02/-0.04/0.03, i.e. no block is played twice. Speed is uniform.

Rate question closed: SPU2's sample clock is fixed at 48 kHz in hardware, and `kStreamRate` is 48000, so the output matches what the console does. The 0201 caveat about "plays fast if the source is 44.1 kHz" was overstated. The ISO-header route also closed: the image is 1.78 GB / 869,280 sectors, so the previously recorded `TITLE.SPS` LSN 0x158BEB lies past the end of the image (it was never a sector number), and the ISO9660 tree contains no `.SPS` entries at all - the music is inside the game's packed archives.

Status: audio works and stays working. Build 212 current, nothing committed, no processes running.

### 0203 - The audio is the game's, verified against guest RAM

The user asked directly whether the sound was fabricated the way the rejected PCM fallback was. Measured instead of asserted:

- 64 consecutive samples from our own output, and a separate 32-sample probe, were both found **verbatim inside the guest IOP RAM dump** (`dump.find(probe) >= 0`), so what reaches the device is a byte copy of the console's own stream.
- The drain path in `pullSpu2Pcm` only copies `queue.blocks[...]` and adds it to the voice mix. Grepping the audio path for `sin`/`rand`/`noise`/`oscillator`/`synth` returns one hit and it is a comment. Nothing in the path can invent a waveform.
- The ring holds **raw PCM, not ADPCM**: the 16-byte header test on the ring reads 26.6% (ADPCM is >85%) and zcr is 15.1%, while the noise-like region at guest `0x10000` (zcr 44.0%) is not the stream.
- Blocks are not duplicated: self-similarity at lags 256/512/768/1024 frames is -0.03/-0.02/-0.04/0.03.

The user then reported the audio is audible but **garbled**. Initial classification: output rms 2038 vs ring 1741, output zcr 21.2% vs ring 15.1%, whole-file crest 7.06 vs a 5 ms ring block's 3.07. The seam test used here was too weak to prove anything (jump at 256-frame boundaries was already large for music).

### 0204 - Two queue faults: dropped-oldest playback and duplicate re-arms

Reading the queue code found two real defects, both of which produce chopped audio on their own:

1. **Overflow dropped the oldest queued block** (`queue.head` advanced, `++dropped`), so whenever the producer outran the device, playback jumped *forward mid-phrase* instead of staying contiguous. Now the *newest* block is discarded and the backlog is capped at `kSpu2QueueTargetDepth = 8` blocks (42 ms).
2. **Every arm was queued, including re-arms of unchanged bytes.** `[spu2:arm]` showed `stale=1167` of 8200 arms, i.e. the same audio played twice. `spu2RingRefresh` now pushes only when the slot's contents actually changed (`slotChanged`).

Measured after the change: drops were still 60% of pushes, which is what forced the next measurement.

### 0205 - The real cause: the stream was produced 1.68x faster than 48 kHz

`audioOut` turned out to be derived from `played`, not a clock, so it could never settle the rate question. Added `[spu2:wall]` using `std::chrono::steady_clock` and measured in real seconds:

| cycles/word | produced | consumed | dropped | depth | verdict |
|---|---|---|---|---|---|
| 768 (old default) | 350 blk/s = 81 kHz = **1.68x** | 187.5 blk/s = 48 kHz | 60% | 8 | producer far ahead, most audio discarded |
| 1152 | 190.9 blk/s = 1.02x | 190.9 blk/s | 6% | 7 | close |
| 1200 | 190.9 blk/s = 1.02x | 190.9 blk/s | 3% | 7 | closer |
| 1240 | 190.9 blk/s = **1.02x** | 190.9 blk/s | **0%** | 4 | matches the device |
| 1436 | 163.6 blk/s = 0.87x | 163.6 blk/s | 0% | 3 | too slow, starving |

So the driver was refilling the ring ~1.87x per scheduled ADMA block because our completion interrupt arrived early, and 60% of the game's music was being thrown away. The 0201 note that "1230 starves the reader" was measured *before* the drain and queue fixes; with those in place, 1240 gives zero drops, zero underruns and a depth of 4-6.

### 0206 - 1240 cycles/word is the new default; garble largely gone by measurement

`admaCyclesPerWord()` now returns `1240ull` by default (still overridable with `APE2_SPU2_ADMA_CYCLES`). Clean run, no environment overrides, build 217:

- `[spu2:queue] pushed=4243 played=4237 underruns=0 dropped=30 depth=6`
- production **190.5 blk/s = 1.02x realtime**, consumption 190.5 blk/s, drops 1%
- seam discontinuity at 256-frame boundaries: median **1.03**, >4x **1.5%** (was median 2.36 / 27.4% at the old pacing)
- per-256-frame block crest median **2.85** against the source ring's 3.07, i.e. the earlier "crest 7.06" was an artifact of measuring a whole 24 s file instead of a block
- whole-file L: rms 2083, peak 13425, zcr 21.8%

Remaining discrepancy: our output zcr is 21.8% against the ring's 15.2%, so some high-frequency content is still being added. The `APE2_SPU2_NOMIX` comparison that would settle whether the voice mixer contributes it did not run (empty log, twice), so this stays **unresolved** rather than assumed.

Status: audio continues to play, now at the rate the console produces it, with no measurable skipping at block boundaries. Build 217 current, nothing committed.

### 0207 - Frame rate after the pacing fix: 59.9 fps, and audio still clean

The ADMA interrupt now fires every 1240 cycles/word, which also stops the driver's refill loop from spinning: with `APE2_FRAME_PROF=1`, `[frame:prof]` over 20 samples of `run_0225.log` reads **mean 59.9, min 59.8, max 59.9 fps** (previous best on the same build line was mean 57.4 / min 41.4). In the same run `[spu2:queue] pushed=4427 played=4424 underruns=0 dropped=11 depth=3` - the stream runs with essentially zero loss.

Diagnostic that does not work and should not be retried: `APE2_SPU2_NOMIX=1`. The runs complete and log normally (1.4 MB) but the SPU2 pull path is never entered, so there are no `[spu2:wall]` lines and no `APE2_SPU2_PCM` capture at all. The open question it was meant to answer (our output zcr 21.8% vs 15.2% for one ring block) is therefore still open, and it is worth noting that zcr, like crest, is content-dependent - comparing 24 s of varied music against a single 5 ms block is not a controlled comparison.

Status: audio streams at the console's rate with 59.9 fps, build 217 current, nothing committed, no processes running.

### 0208 - The stream is bit-identical to what the guest wrote; the voice mix is silent

The open zcr question is settled by direct measurement instead of inference. `APE2_SPU2_REF` and `APE2_SPU2_REFMIX` split the two contributions inside `pullSpu2Pcm`: the mixer output is snapshotted before the ring blocks are summed in, and the ring blocks themselves are written to their own file. Run 0226 produced three files of exactly equal length (1,102,400 stereo frames, 22.97 s):

- final output vs guest ring: **100.00% of samples bit-identical**, residual rms 0, residual peak 0
- voice mix: **rms 0, peak 0, 0.0% of frames non-silent**
- zcr, same window: output **21.74%**, guest ring **21.74%**, per-256-frame median 21.96% for both

The earlier 21.8% vs 15.2% discrepancy was therefore entirely a content mismatch - 23 s of varied music compared against one 5 ms ring block, the same mistake as the earlier crest comparison. Nothing is added, scaled, resampled or summed into the stream between guest RAM and the output buffer, and every voice is silent during gameplay audio, so streamed music is the only source. `APE2_SPU2_NOMIX` is not needed and stays unfixed.

### 0209 - Queue depth 8 -> 16, and the queue log fired on every push

Run 0226 still discarded 22 blocks (0.5%) while steady-state depth was only 2-3: bursts of arms (level loads, driver catch-up) overflowed the 8-block cap even though the queue was normally nearly empty. Cap raised to **16** blocks; latency only grows when a backlog actually exists. Run 0227: **dropped=2, underruns=0, depth=5** - 0.05% loss instead of 0.5%.

Also fixed: the `[spu2:wall]` and `[spu2:queue]` prints were never braced, so the queue line ran on every push, i.e. 4256 stderr writes inside the audio path in 23 s. Both now share the 200-push cadence: 21 lines, same content.

Verified after both changes (build 219, defaults only): produced 190.9 blk/s = **1.02 x** realtime, consumed 190.7 blk/s, rms 2073, peak 14398, zcr 21.56%, seam ratio median **0.82**, boundaries above 4x **0.92%**, per-block crest median 2.82, and `pcm219.raw == ref219.raw` **True**.

Frame rate on the same build, `APE2_FRAME_PROF=1` over `run_0228.log`: **mean 59.9, min 59.8, max 59.9 fps**. Status: the output is the guest's audio verbatim, at the console's own rate and a steady 59.9 fps. Nothing committed, no processes running.

### 0210 - The garble was in the device feed, not the emulation

Every earlier measurement was taken at the IOP boundary, where the audio was already proven bit-exact. Adding a capture at the *device* boundary (`APE2_AUDIO_DEV`, inside `pushStreamPcm`) showed the real loss: **556,000 frames reached the device against 1,108,000 produced** - half the music never arrived.

Two causes, both in `ps2_audio.cpp`:

1. `UpdateAudioStream` was called with a 512-frame chunk while raylib's stream buffer defaulted to 4096, and raylib splits that into two sub-buffers of `sizeInFrames/2` = 2048, **zero-filling whatever the call does not supply**. So 1536 of every 2048 frames were silence: 75% of the music replaced by padding, which is what "garbled" sounded like.
2. Even with the padding removed, the submit loop pushed at most one chunk per video frame, because `IsAudioStreamProcessed` goes false immediately after an update. At 59.9 fps that is 512*59.9 = 30.7k frames/s against a device consuming 48k.

Fix: the sub-buffer is pinned to the chunk size (`SetAudioStreamBufferSizeDefault(kChunk*2)` with `kChunk = 800`, exactly one emulated video frame) and the feed moved to a wall clock so the supply rate comes from the device's rate rather than the video cadence. Measured on build 220: device frames/s still only 12,356 - better, still starving, because the processed flag remains too coarse.

### 0211 - Device feed moved to a raylib stream callback

`SetAudioStreamCallback(streamFillCallback)` now pulls from the existing 2-second ring on the audio thread, which is handed exactly the frames the device needs at the device's own rate. `pushStreamPcm` only fills the ring; the submit loop is gone.

Verified on build 221 (run 0230):

- device frames **1,143,808** against **1,138,400** produced - **ratio 1.005** (was 0.50)
- device rate **48,228 frames/s** over the 23.7 s audio window
- **Correction to an earlier version of this entry:** the device stream is not index-aligned with the produced stream and is **not** 100% identical there. Aligned at a probe the content matches, but the offset grows steadily (see 0212): the pull is tied to the 59.9 fps video cadence, 800 frames per frame = 47,920 frames/s, while the callback drains 48,000/s, so the ring empties slowly and silence is inserted. The *content* reaching the device is the guest's audio; the delivery rate is what is still wrong.
- silent chunks: 0.91% ; non-silent rms=2077 peak=14398 ; longest silence gap 12 chunks (200.0 ms)
- queue: `pushed=4200 played=4187 underruns=0 dropped=5 depth=13`

The ring is now drained continuously, so depth sits at 13 rather than the 2-3 the defective feed produced. Nothing else changed: the IOP stream is still the guest's bytes verbatim.

### 0212 - Producer follows the clock; device rate verified at 48.02k

The pull in `ps2_runtime.cpp` was a fixed 800 frames per video frame, i.e. 800 x 59.9 = 47,920 frames/s against a device consuming 48,000 - a 0.17% shortfall that emptied the 2-second ring and forced the callback to insert silence. It now pulls whatever the wall clock says is due (`elapsed * 48000 - pulled`, capped at 4800 frames per call so a stall cannot replay half a second at once).

Also added: `[audio:dev]` reports the device's true pull rate and cumulative underrun frames, so the fill level is measured instead of assumed.

Run 0232 (build 222), 45 s with `APE2_SPU2_PCM` + `APE2_AUDIO_DEV`:

- device rate **48,022-48,026 frames/s** (target 48,000; the audio hardware clock is ~0.05% fast)
- device frames 1,075,200 vs produced 1,076,241 - within 1,041 frames
- **underruns: 1,791 frames total**, i.e. one ~37 ms gap in 22 s, 0.300% of chunks silent after audio starts
- probe offsets: +209 / +221 before the gap, +1791 / +1791 after - a single step, not progressive drift
- drift now **+0.186%** over 17.7 s, down from +0.55%
- queue: `pushed=4000 played=3995 underruns=0 dropped=0 depth=5`

Note on reading the alignment number: a naive "aligned identical" fraction measures 4.55% here because one 1570-frame step destroys a fixed-offset comparison for all later audio. The probe table is the correct test and shows the content is continuous either side of it.

Remaining known defect: emulated time advances at 59.9 frames of 1/60 s per wall second, so the guest produces 47,920 frames/s while the hardware pulls ~48,025. That 0.19% must be absorbed somewhere, and today it is absorbed by one 37 ms silence insertion roughly every 20 s. Eliminating it cleanly needs a fractional-rate read (linear interpolation at a 0.998-1.002 ratio, ~0.2% pitch shift, inaudible) rather than whole-chunk padding.

Editorial note: while applying this change the file was briefly left with unbalanced braces (C2001, then C2888/C1075). It was rebuilt from the namespace opener to `pushStreamPcm` as a known-good block; build 222 compiles and runs clean.

### 0213 - Fractional-rate read: no underruns, no silent chunks

Build 222 still inserted one ~37 ms silence gap every ~20 s, because emulated time delivers 47,920 frames/s while the sound card pulls ~48,025. Padding whole chunks is the wrong place to absorb 0.19%: it has to be spread over individual samples.

`streamFillCallback` now keeps a fractional read position and linearly interpolates between the two frames at the ring head, advancing by `step` instead of exactly 1.0. `step` is 1.0 + clamp((fill/4800 - 1) * 0.02, -0.004, 0.004), so the ring's occupancy steers it: below 100 ms of buffer it reads slower than real time, above it reads faster. A starved frame holds the previous sample instead of emitting a block of zeros.

The producer side changed with it. `ps2_runtime.cpp` no longer pulls a wall-clock quota (that fought the resampler: it kept demanding frames that emulated time had not produced, holding the ring empty). It now pulls to a fill level - `streamRingFill()` reports what `pushStreamPcm` has buffered, and the loop tops it back up to 4,800 frames (~100 ms) each video frame.

Run 0233 (build 223), 40 s with `APE2_SPU2_PCM` + `APE2_AUDIO_DEV`:

- `[audio:dev] rate=48029/s underruns=0` at 17 s (48,461/s at 1 s is the ring filling after start)
- **underruns = 0 for the entire run**, against 1,791 frames in build 222
- **silent chunks after audio starts: 0.000%** (17 leading chunks, all before the music began, against 0.300%)
- device frames 832,512 while the producer wrote 836,097 - the 3,585 difference is the ~100 ms still buffered, not loss
- queue untouched: `pushed=3000 played=2996 underruns=0 dropped=0 depth=4`

Pitch is bounded by the control clamp: the read ratio can never leave 0.996-1.004, i.e. at most 0.4% (about 7 cents), and it sits near 0.998 in practice. That is deliberately inaudible and replaces what used to be a hard 37 ms discontinuity.

Retracted hypothesis, recorded so it is not tried again: the voice mixer's phase accumulator in `iop_spu2.cpp` steps by the raw pitch register with 0x1000 = 1.0, and on hardware 0x1000 is 44.1 kHz into a 48 kHz mixer (0.91875), so all voices would run 8.84% sharp. It is irrelevant here because `[spu2:mix] frames=800 peak=0` reports the voice mixer output as silent throughout: AE2's music is the auto-DMA PCM stream on core 1, which bypasses voices entirely. The driver's own block rate (2,996 blocks over 15.9 s = 187.5/s, i.e. 48,000 / 256) independently confirms the stream is 48 kHz material, so its pitch is delivered as authored.

Also corrected in this entry's favour: the earlier probe-offset test (`produced N -> device M`) can no longer be used, because interpolation makes the device bytes differ from the produced bytes sample by sample. Verification now rests on the underrun counter, the silent-chunk fraction and the fill level.

Build note: this was a full rebuild after `ps2_audio.h` changed, and took ~20 minutes because it recompiles ~240 generated unity units plus the VU program unit; incremental builds after touching only one .cpp remain ~90 s. A `run_terminal_command` timeout killed two attempts mid-link before a background build finally completed, and a runner restart interrupted a third - the resulting `build223b.log` is the authoritative one.

### 0214 - Measured, not guessed: the resampler was muffling the music

Player description after build 223: "slightly muffled, pixely, the beat a little too deep, the yell a little too high pitched". That is a description of interpolation error, so it was measured rather than theorised about.

Method: the device capture (`APE2_AUDIO_DEV`) and the guest-side capture (`APE2_SPU2_PCM`) cover the same 17 s of the same track, so a long-term average spectrum (LTAS) over each whole file compares them without needing sample alignment. Window-by-window comparison is useless here: a 0.19% rate difference smears a 0.5 s window by ~58 frames, and correlation across such windows measured 0.01-0.15 no matter the offset. An earlier attempt to lock the two streams sample-for-sample failed for exactly that reason and produced no usable numbers.

LTAS of build 223 (linear interpolation), device minus produced:

- 30-500 Hz: within 0.01 dB
- 500 Hz-2 kHz: +0.03 dB
- 2-5 kHz: -0.14 dB
- 5-10 kHz: **-0.68 dB**
- 10-16 kHz: **-1.96 dB**
- 16-23 kHz: **-3.62 dB**

Linear interpolation at a fractional position is a low-pass, and the predicted response matches: -0.44 dB at 6 kHz, -1.75 dB at 12 kHz, -2.99 dB at 16 kHz, -4.20 dB at 20 kHz. So the "muffled" was mine, introduced in 0213.

Quantisation was ruled out as the cause of "pixely": both streams have the same delta structure (49.87% / 49.95% of non-zero deltas even, 12.40% / 12.42% divisible by 8), so nothing is being bit-crushed anywhere.

Also produced `dumps/audio/dev223.wav` and `pcm223.wav` so the device-side bytes and the guest-side bytes can be A/B'd by ear: if the WAV sounds right while the game does not, the remaining difference is raylib's `ma_data_converter` (raylib's `AUDIO_DEVICE_SAMPLE_RATE` is 0, i.e. the Windows default, and `raudio.c:581` converts our 48 kHz stream to it).

### 0215 - Catmull-Rom resampling, and a rate decision once per callback

Two changes in `streamFillCallback`:

1. Linear interpolation replaced with 4-point Catmull-Rom (`-0.5, 1.5, -1.5, 0.5` / `1, -2.5, 2, -0.5`), falling back to linear while fewer than four frames are buffered.
2. The rate ratio is now computed once per callback with a quarter-weight one-pole, instead of once per sample. Recomputing it per sample let the ratio move at sample granularity, which modulates pitch.

Run 0234 (build 224):

- underruns **0**, device 48,029/s, queue `pushed=3200 played=3188 underruns=0 dropped=0 depth=12`
- LTAS device minus produced: **-0.10 dB at 5-10 kHz** (was -0.68), **-0.66 dB at 10-16 kHz** (was -1.96), **-1.92 dB at 16-23 kHz** (was -3.62)
- zero clicks above 20,000; 6 above 12,000; no dropout chunk after start
- `dumps/audio/dev224.wav` written for listening

The residual 16-23 kHz loss is Catmull-Rom's own response near Nyquist; removing it needs a windowed-sinc kernel, which is only worth doing if the player still hears dullness.

Patch 0054 was regenerated to cover the cubic version, and both new patches are now recorded in `C:\dev\PS2Recomp\.ape2_patches_applied` - the build script re-applies every patch in `patches/ps2recomp`, so a patch left unrecorded there is applied on top of itself and fails.

### 0216 - Where the level music should come from, and what the game actually asks for

**Superseded by 0223:** the hub/stage music, voices and effects are played on SPU2 voices from the sound banks; they were silent because the SPU2 register layout was wrong, not because the game never asked for them.

The player reported that audio only exists in the intro: the hub and every stage have no music and no voice
lines, and the "yell" mentioned earlier was in the intro music. That invalidates the working assumption from
0211 that the streamed SPU2 queue is the game's music path. It is one path, and it is the intro's.

Disc layout (walked from the ISO's own directory records, LSN = real sector):

- `APE2_USA/PCM/BGM/*.SPS` - 15 streamed tracks, 8-39k sectors each (`TITLE.SPS` at 0x5b9f0, `NO28.SPS` at
  0xb74ef, `THEME.SPS` at 0xcee36, `PINK.SPS` at 0x53fe7)
- `APE2_USA/SOUND/BGM/*.BIN` - 4 small banks (`BGMB_TIT`, `BGMH_TIT`, `BGMB_CLE`, `BGMH_CLE`)
- `APE2_USA/VOICE/**/*.VGS` and `APE2_USA/SOUND/SE/*.BIN` - voice lines and effect banks
- `APE2_USA/MODULES/LIBSD.IRX` and `SNDN2DRV.IRX` - the sound driver, loaded as `load-emulated`

A session that reached the title screen and streamed its music for 60 s shows **exactly one** stream open -
`cdrom0:/APE2_USA/pcm/bgm/title.sps` - and no CD read inside any SPS music range beyond it. The intro stream,
the CD layer and the device are therefore fine; the game never asks for a stage track in that session. What is
still missing is the request itself, not the machinery behind it.

Added a `APE2_IOP_CDLOG` trace (`iop_cdvd.cpp`) for `sceCdSearchFile` names and periodic read LSNs. It did not
fire for the game's own loads: Ape Escape 2 issues those through the runtime's `ape2:cdread` hook, not through
the IOP cdvd imports, so that trace stays useful only for driver-level reads. The `ape2:cdread` line already
prints LSN and is capped at 64 calls, which is what identified `TITLE.SPS` above.

### 0217 - Unconditional debug prints removed from the hot path (major frame cost)

Measured in a 60 s play session: **79,387 log lines, of which 62,912 were `[iop:sema]` and 13,687 were
`[spu2:auto]`**. Neither was gated by an environment variable, so every build paid for them: the semaphore
`SIGNAL`/`WAIT` prints alone fire on every semaphore operation, and the auto-DMA prints fire per arm and per
rearm query. Both paths are hot while music streams.

Now gated: `[iop:sema]` behind `APE2_IOP_SEMA`, the `[spu2:auto]` prints (arm, rearm query, interrupt dispatch
attempts) behind `APE2_SPU2_AUTO`. Behaviour is unchanged when they are set.

Run 0235 (build 226, no diagnostic variables, only `APE2_FRAME_PROF`): **1,410 lines in 45 s** against 79,387 in
60 s, i.e. roughly 56x less log traffic. Title screen: `[frame:prof] loops=120 per 2000 ms` = a steady 60 fps,
`[audio:dev] rate=47960/s underruns=0`, queue `pushed=2000 played=1993 dropped=1 depth=7`.

Not yet measured: frame rate inside a stage. The player reported "major fps slow down" in levels before this
change, and the log cost above is only part of whatever that is - it must be re-measured in a level before this
is called fixed.

### 0218 - The stutter was my own stale-repeat injection (reverted to opt-in)

Device captures analysed for exact-zero frames, gaps >=10 ms and repeated 256-frame blocks:

- build 224 (`dev224.wav`): 2.29% zeros, **0** gaps >=10 ms, 0% repeats - the known-good profile
- build 226 before the injection: underruns 0 until 44 s, then 3,828
- build 227 with the "repeat the stale slot" path: **44.03% zeros, 810 gaps >=10 ms, max 93.9 ms, median gap
  1,371 frames = 28.6 ms, 26% repeated blocks** - the music was chopped into ~29 ms pieces. 28.6 ms is the
  35 ms throttle of that path showing through.
- build 230 with the path gated off by default (`APE2_SPU2_STALEREPEAT` opt-in): **2.0% zeros, 2 gaps,
  underruns 0 at 43.99 s, and zero frame windows below 60 fps in a 65 s session**

So 0221's fix converted dropouts into audible repeats and made the stutter worse, and the "driver stops
refilling at 14 s" reading was partly an artefact of it. The path stays in the tree behind the flag for
further experiments, off by default.

Two measurement traps worth remembering: the `[sndn]` trace was capped at the first 120 calls (all inside the
first four seconds of boot), so bucketing it by time produced a fake "driver went quiet" signal; and the
`ape2:cdread` trace was capped at 64 calls, which hid everything after boot.

### 0219 - Driver heartbeat, wider read trace, and where the title audio actually comes from

- `[sndn]` now keeps logging every 1,000th call forever instead of stopping at 120, so a driver that goes
  quiet mid-track is visible.
- `ape2:cdread` now logs the first 64 reads, every 20th read after that, and every failure.
- First result from the widened trace: only **27 reads in a 50 s session, all within the first 4 s, zero
  failures**. The title music therefore is not fed by repeated CD reads - it goes through the movie/stream
  player's host file path into the driver. Read tracing alone will not explain a stream stall; the sndn
  command stream is the place to look.

Tooling note: two edits in this pass silently did not land (a `str_replace` that reported success but left the
file byte-identical, and a capture written to an invalid path from a doubled backslash), so every edit is now
verified with a `grep` for its marker and every capture path is checked for existence before it is analysed.

### 0220 - Frame-drop investigation: real fps, IOP bursts, and a negative result

The `[frame:prof]` line counts host loop iterations, not guest frames, so it read a perfect 120/2 s while the
game actually dropped frames. The `[perf]` line is the honest counter: guest frames over 2 s.

Baseline over a 65 s session (build 230): guest fps median 59.5, **worst 44.3**, with windows at 44.3, 47.4,
47.5, 49.9 and 50.0. Each dip lines up with an IOP sample of 441, 727, 560, 552 or 479 MHz against 36.86 MHz
hardware, i.e. the IOP executing 12-20x the cycles the real chip could in that window.

Hypothesis tested: `EeScheduler` converts the wall time a guest dispatch took into EE-equivalent cycles and
hands them to the IOP after every dispatch, capped at a full second, so one long dispatch releases a burst that
runs synchronously on the EE thread. Added `APE2_IOP_CATCHUP_MS` (slice cap, 0 = old behaviour) and A/B'd two
58 s sessions:

- cap 5 ms: worst 47.4 fps, 10 windows under 55 fps, 1 under 50, IOP max 715 MHz
- cap 0 (old): worst 50.5 fps, 7 windows under 55 fps, 0 under 50, IOP max 432 MHz

The cap made it marginally worse, so the burst hypothesis is **not** supported and the default is back to the
old one-second behaviour. The knob is kept for later experiments. Both runs: audio underruns 0, rate 48,013/s.

Not yet measured: frame rate inside a stage. Every measurement in this entry is the title screen, so a
stage-specific drop remains possible and needs a run with the player driving.

### 0222 - The intro music was read with the wrong stereo layout (0055)

Player report: the intro music sounds "slightly muffled, pixely, the beat a little too deep, the yell a little too
high pitched". The cause is not timing or resampling: each auto-DMA block is **planar**, the way the SPU2 reads
it - 256 left samples, then 256 right samples (the PAL port's `spu2.c` reads them at +0 and +0x200). The queue
drain in `pullSpu2Pcm` read the 1 KB block as interleaved L/R pairs, so each ear got every other sample at twice
the pitch, in 2.7 ms pieces 187.5 times a second.

Measured on a raw block dump (`dumps/spu2e/spu2_core1.bin`, 5,775 distinct blocks):

- planar: median sample step inside a block **446**, across a block seam **443** (seamless); roughness 0.29/0.30
- interleaved (old): inside 795, seam 967; roughness 0.53

The 0208 "bit-identical" check could not see this: both sides of that comparison read the same bytes the same
wrong way. Fixed in `iop_memory.cpp` (patch 0055); `APE2_SPU2_REF` now writes the de-planarised pairs. After the
fix a 45 s intro run's device capture has roughness 0.27/0.26 (dev224: 0.46) and L/R correlation 0.86.
Listening files: `dumps/audio/dev_fixed.wav` (fixed build) and `dumps/audio/intro_planar_fixed.wav` (the dump
re-read planar). The pacing, queue and resampler from 0204-0215 are unchanged.

### 0223 - Hub and stage music, voices and effects: the SPU2 register layout was wrong (0056)

Player report: only the intro had audio; the hub and stages had no music, voices or effects. That audio comes
from the sound banks played on SPU2 voices (the PAL port plays it the same way), and our SPU2 model had the
register layout wrong almost everywhere, so none of LIBSD's voice programming reached a voice:

- it took VMIXL (0x188/0x18A, which libsd's init sets to 0xffffff, as PAL's `sd_init` does) for key-on - the
  "key-ons with unprogrammed voices" of 0175/0194/0195 were mixer masks; the real KON (0x1A0/0x1A2) and KOFF
  (0x1A4/0x1A6) were never decoded
- voice sample addresses were looked for inside the voice parameter block; they are at 0x1C0 + voice*0xC (SSA,
  LSAX, NAX as hi/lo halfword pairs), and the parameter block is VOLL VOLR PITCH ADSR1 ADSR2 ENVX VOLXL VOLXR
- TSA (0x1A8) was scaled as a PS1 address (x8); SPU2 addresses are halfword pairs (x2)
- ADPCM data was decoded from byte 1 of each block instead of byte 2 (byte 1 holds the loop flags)
- 16-bit register writes went through a 32-bit read-modify-write, rewriting the neighbouring register (a KON
  low write would re-key the high voices)
- core-1 auto-DMA blocks (the stream) were also copied to SPU RAM at TSA, over the sample banks

Fix (patch 0056): `iop_spu2.cpp` rewritten with the real layout (master volumes at 0x760 + core*0x28, ENDX at
0x340, PIO data port at 0x1AC) and the PAL port's voice engine (`port/src/spu2.c`, JackyPendrag0n/ae2-recomp):
VAG ADPCM, ADSR, Catmull-Rom pitch, volume sweeps, loop flags/ENDX. `IopMemory::write16/read16` now reach one
register; auto-DMA blocks no longer write SPU RAM. New diagnostics: `APE2_SPU2_KONLOG=1` (key-ons with their
parameters), `APE2_SPU2_STAT=1` (voices on once a second), `[spu2:dma]` (bank uploads).

Measured in the hub (77 s device capture, `dumps/audio/hub_voices.wav`): banks upload over core 0 (444,992 bytes
at 0x05400 and others), key-ons carry real pitch/volume/ADSR, up to 17 voices sound at once, continuous output
at rms 2,500-4,400 with no clipping (silent before). Player confirmed: music, voices and effects all play.
Not yet emulated: the effect unit (reverb; the game sets Studio C at ~20%, which PAL emulates).

Patch 0056 also carries the clone's other changes that no earlier patch had recorded (the IOP-side sound work
of 0071-0221: `iop_spu2` in CMake, intrman/RPC/cdvd/kernel/emulator changes, `EeScheduler`, `SIF`, the GS
debugging in `zz_ape2_gs_gl.cpp`, `zz_ape2_hangdump.cpp`), so the patch set rebuilds the working tree.

### 0224 - Reverb: the SPU2 effect unit (0057)

LIBSD sets the effect unit up through the hardware registers, so they are decoded as the SPU2 holds them: the
work area ESA (0x2E0, hi/lo) to EEA (0x33C, hi only, `(hi << 16) | 0xFFFF` halfwords), the 22 APF-size/delay
address registers 0x2E4-0x338 (halfword offsets from ESA) and the 10 effect volumes at 0x774 + core*0x28
(vIIR, vCOMB1-4, vWALL, vAPF1, vAPF2, vLIN, vRIN). The algorithm is the PAL port's (`port/src/spu2.c`): the
PS1 reverb at half rate in the work area with its 39-tap half-band filters, fed from VMIXEL/VMIXER under the
MMIX gates, core 0's output into core 1, gated by ATTR bit 7 and scaled by EVOL.

Verified against PAL's Studio C preset: the game writes exactly its values x4 (e.g. 0x2EE = 0x37EC = mLSAME
0x0DFB), and the work area 0xFC810-0xFFFFF is exactly that preset's size, so the register units are halfwords.
Same hub run with and without reverb: rms 3,155 vs 1,858, L/R correlation 0.857 vs 0.877, no clipping.
`APE2_REVERB=0` turns it off; `APE2_SPU2_FXLOG=1` logs the effect register writes. Player: "it's perfect".

### 0225 - The sister's voice in the hub: core-1 voice uploads went to the stream (0058)

Player report: the sister in the Travel Station has no voice. A logging run with the player talking to her showed
the game does read her lines (`VOICE/STATION/FIRSTIME/NATUMI.VGS` at lsn 0x2ac27, `TRAVEL/MECA.VGS` at
0x299d9) through `sceCdStStart`/`sceCdStRead`. VGS data is VAG ADPCM (valid shift/filter bytes, flags 0; lag-1
correlation as PCM 0.08), uploaded by the driver with `sceSdVoiceTrans` on core 1 into SPU RAM and played on a
voice - not PCM for the stream.

Two faults, in `iop_memory.cpp`:

1. The 0135 rule treated every core-1 DMA as the auto-DMA stream, so her ADPCM never reached SPU RAM. With the
   arms split into 1 KB blocks (a first fix attempt) it was played as PCM, heard as static. Auto-DMA is now
   decided from ADMAS as the driver wrote it (`m_guestAdmas`, apart from the 0161 busy bit), and since the
   driver never clears core 1's ADMAS after the intro (only three ADMAS writes in a session: 0, 0, 2), an
   upload is recognised the way libsd's calls differ: `sceSdVoiceTrans` writes TSA before every transfer,
   `sceSdBlockTrans` never (`IopSpu2::takeTsaWritten`). `APE2_SPU2_CORE1AUTO=1` restores the 0135 rule.
2. The stream queue only accepted arms the size of the first one (1 KB) and none over 2 KB; any arm is now split
   into the 1 KB planar blocks the SPU2 consumes.

Intro verified unattended after each step (24.4 s of stream audio, clean). Player: "fixed".

### 0226 - Flickering and garbage textures everywhere: the GS never sampled mip levels (0059)

The long-standing texture garbage (hub keyboards, the level 1 floor, walls; both renderers; fine in first
person) is solved. The decisive trace, from a single-threaded hub run (`APE2_MTGS=0`, so the log is in stream
order), with `scratchpad/kbseq.py`: in every bad frame the left keyboard is drawn from a ring slot whose
level-0 image (the 64 KB atlas, datahash `6fc5944f`) is uploaded about 4,400 lines *after* the draw - for
the right-hand keyboard, which is closer. Right before the left keyboard's draw the game uploads only its
smaller levels and palette (`0x2e40` 64x64, `0x2e80` 32x32, palette `0x2e90`), the addresses in MIPTBP1/2.

So the game streams only the mip levels the PS2 will sample: for a distant surface level 0 is never read and
never uploaded. Our GS decoded MIPTBP1/2 and ignored them (0054 noted it), always sampling level 0 - whatever
texture last used that slot. That is why first person (close, level 0) was clean, why it moved with the
FPU rounding mode (the LOD thresholds), and why 0060's mipmaps did not help: they were generated from level 0
with glGenerateMipmap, the one level that is missing. The PAL port's README states it outright ("the game
streams only the smaller texture levels for distant surfaces").

Fix, in `gs_frontend.cpp` (`mipSubmit`), ported from the PAL port's `port/src/gs.c` (mip_pick, setup_draw,
mip_split; JackyPendrag0n/ae2-recomp), so both renderers get it: the level comes from the GS formula
LOD = log2(1/|Q|) * 2^L + K (K with LCM), per primitive from its vertices' Q; the primitive then samples
that level's own TBP/TBW (MIPTBP1/2, or packed with MTBA), size and CLAMP, UVs shifted for FST, MMAG/MMIN
filter by LOD; a triangle whose corners want different levels is cut along the lines where the level
changes. `APE2_GS_MIPMAP=0` turns it off, `APE2_GS_MIPSPLIT=0` disables the cut, `APE2_MIPLOG=1` logs level
picks and filter changes.

Measured on the unattended hub burst (`scratchpad/runab.cmd`, keyboard crop grids): before, 3-4 of 20
sampled frames showed the keyboard; VU1 MSCAL deferral off (PAL's synchronous model) and single-threaded GS
were no better (3/20, 10/20). Player, after the fix: "all the glitchy textures on the maps, hub and
everywhere are gone".

Also in 0059, found on the way and kept because it matches the PAL port's `rt_hw.c` dma_run: scratchpad DMA
interleave mode and the toSPR source chain (were silently dropped, channel never finished). This game never
uses scratchpad DMA (`APE2_SPR_LOG=1` saw none), so it changes nothing here.

Correction (0227): the blue patches on the title screen's distant hill *were* caused by this. The
"also with `APE2_GS_MIPMAP=0`" check was invalid - see 0227.

### 0227 - Title hill: trilinear base level and no triangle cut (0060); my A/B scripts were broken

Player report after 0059: blue patches through the green hill in the title flyover. Found the hard way that
my test scripts never applied their settings: `runab.cmd NAME=VALUE` / `runtitle.cmd NAME=VALUE` pass the
argument through cmd, which splits it at `=` (and at `,` and `;`), so `set %~1` set nothing. Every A/B in
0226 that passed a variable on the command line (VU1 deferral off, `APE2_MTGS=0`, mipmaps off, software
renderer, VU interpreter) actually ran the default build. The 0059 conclusion rests on the default-build
trace and the player's confirmation, so it stands; the "not caused by mipmapping" note did not. Test scripts
now carry the variables as `set` lines (`scratchpad/tb_*.cmd`).

With working A/Bs (title burst at frame 2400, `scratchpad/runtburst.cmd`):
- `APE2_GS_MIPMAP=0`: no patches. 0059: patches. So 0059 caused them.
- The game uploads every level the hill uses (`APE2_UPLOG=1`: 0x33c0, 0x34c0, 0x3500, 0x3510 = MIPTBP1),
  and the decoded levels look right, so addresses and decoding are fine.
- Level = integer part of LOD instead of rounded: most patches gone. The hill's TEX1 has MMIN 5
  (LINEAR_MIPMAP_LINEAR); the GS rounds the LOD only for the nearest-mipmap filters (MMIN 2, 4) and takes its
  integer part as the base level for the trilinear ones (blending toward the next). The PAL port rounds in
  every mode. Now per mode (`mipRound`); `APE2_MIPROUND=<bias>` forces one.
- `APE2_GS_MIPSPLIT=0` (no triangle cut): all patches gone. The pieces cover their triangle exactly (an area
  check under `APE2_MIPLOG` found no shortfall), and the patches have the triangles' straight edges: the
  terrain is drawn in several passes that need the same depth per pixel (ZTST GEQUAL), and a triangle cut
  into pieces rasterises slightly different depths than the whole one, so a following pass fails on whole
  pieces. The cut is now opt-in (`APE2_GS_MIPSPLIT=1`): one level per primitive, as the PAL port itself
  describes as close for the small polygons the game draws.

Title burst after 0060: clean in every sampled frame. Also kept for later: `APE2_PIXPROBE=x,y/x,y` (software
renderer, during a burst: every write reaching the depth test at those pixels) - note the display is a copy of
another buffer, so screen and frame-buffer coordinates need not match.
### 0228 - FMVs play: the IPU, a recompiler branch fix, the movie clock and the end of a movie (0061)

Movies were skipped at start since 0024. Now they play, with sound, and end into the game. Steps, in order:

- IPU: `ps2_ipu.cpp`, a port of the PAL port's `port/src/ipu.c` (JackyPendrag0n/ae2-recomp; the decoder unchanged,
  the coroutine a Windows fiber), behind the IPU registers, the 0x10007000/0x10007010 FIFOs and DMA channels 3/4
  (`ps2_memory.cpp`); its interrupt (INTC 8) is queued with the DMAC causes and dispatched in
  `drainCompletedDmacHandlers`. The 17 libmpeg/libipu stubs are gone from `config/ape2.toml`, so the game's own
  libmpeg runs. Movie skips are opt-in (`APE2_MOVIES=0`; `APE2_MOVIES=firstframe` for the old skipfmv).
- Recompiler bug, all game code: BLEZ/BGTZ/BLTZ/BGEZ(+L/AL) were emitted as 32-bit tests (`GPR_S32`); the R5900
  tests the whole 64-bit register (the PAL port's recompiler uses 64-bit `RS()`). libmpeg's IPU wait loop
  (0x374558) reads IPU_CMD with `ld` and branches `bgez`: whenever the data word had bit 31 set it read as busy
  forever (first movie stuck at its 4th FDEC). `control_flow_emitter.cpp` now emits `GPR_S64`. 1589 generated
  files changed; 32-bit writes sign-extend (`SET_GPR_U32`), so ordinary code is unaffected; player-tested.
- Colour conversion on the host (`overrides/zz_ape2_mvconv.cpp`, the PAL port's hle_mvconv, NTSC 0x1A6D18, frame
  ring 0x3DF5C0, size getters 0x1A4350/0x1A4370): the game's VU1 program drew 262144 points per vsync (VU1 99%,
  1.5 fps).
- libmpeg's IPU wait without its 5000 idle polls (`overrides/zz_ape2_mpegwait.cpp`: a copy of the generated
  0x374558 with the limit 1, the PAL port's hle_mpeg_wait idea; a C++ loop could not yield to the threads that
  feed it, and stalled). 125 -> 425 movie frames in the same time.
- The movie clock. Events (vsync, timers) fire when the EE cycle count reaches them, and host work the guest is
  not charged for (the IPU's decoding, register accesses, the scheduler) left it at a quarter of real time in the
  FMVs: everything, sound included, played slow - and every run converted the same number of frames, the tell
  that progress was paced by emulated time, not the CPU. Now: the IPU's host time is charged to the EE clock
  (`ps2ipu::setChargeHook`), and while a movie plays (an IPU command in the last 200 ms) a pending vsync whose
  real-time deadline is 2 ms past brings the cycle count up to it (`EeScheduler::checkpointDue`). Measured on
  the way: a wall-clock version overflowed after a minute and ratcheted on re-anchors (EE 11x real time), and an
  always-on version froze a stage seconds after the New Game movie and cost gameplay fps (player) - hence
  movie-only. `APE2_EE_CATCHUP=0/always`, `APE2_IPU_CHARGE=0`, `APE2_CATCHUP_LOG=1` ([ee:clock] MHz).
- The IOP ran at twice real time once the EE clock kept up: 0131 advances it by the wall time of each guest
  dispatch on top of the EE cycles' share; now only by the shortfall (movie sound too fast; iop:rate 65 -> 40).
- The end of a movie: a white screen. libmpeg feeds the IPU whole qwords, so the video stream's last bytes (the
  sequence end code 00 00 01 B7 after zero padding) never arrive and libmpeg scans the padding forever. The game
  ends a movie by sending one qword "00 00 01 B7" itself (background callback 0x1A9248, once its error callback
  0x1A9238 has flagged the end). The IPU now feeds that qword when a command has waited 500 ms for input with the
  toIPU DMA idle (`APE2_IPU_EOS_MS`). Tried first: ECD (libmpeg cleared it and scanned on), and letting the disc
  stream run past the file's end (`APE2_CDST_PASTEND=1`, now opt-in: it kept the movie thread reading zeros
  after D2, a freeze and lower fps).
- Smaller: RotateThreadReadyQueue returns at once when nobody else is ready at that priority;
  `APE2_ROT_MIN_US` yield throttle (default off, no gain measured).
- Mip level per triangle is now the nearest corner's (not the average): less blur near the camera
  (`APE2_MIPPICK=avg`).

Player: the intro ends into the title, New Game's movie into the stage, START skips, no freeze; movies "still a
tad slow but better", some slowdowns in movies and gameplay. Open: frame rate (gameplay ~48 fps, the GS thread
74% busy: ~56 destination reads and ~35 texture uploads per frame), and light green bands where the mip level
changes on the floors (the game asks for trilinear filtering; we pick one level per triangle - the PAL port
does the same).
### 0229 - Frame rate: table-driven texture decode in the GPU renderer (0062)

Profiling the slow gameplay (~40-48 fps): the EE was idle 55-77% and waited on the GS thread (`[mtgs]`: GS
thread 99% busy, EE waits ~1.1 s per 5 s), and the GS thread's work was decoding textures: ~35 decodes a frame,
every texel through the generic `GSMem::ReadTexture` / `DecodeTexel` (streamed textures move slots every frame,
and each mip level is a texture of its own). (A first GS-thread sample in a light stretch showed it idle -
pair the sampler with `[mtgs]` before concluding.)

`GSGlBackend::fastDecode` (zz_ape2_gs_gl.cpp) is the PAL port's `tex_decode` (port/src/gs.c,
JackyPendrag0n/ae2-recomp): in-page byte/nibble offsets from tables built once from our GS block/column tables
(CT32 layout 64x32, T8 128x64, T4 128x128), the page from row arithmetic, a palette expanded once; T8, T4, CT32,
CT24, T8H, T4HL, T4HH. CT16 and the rest keep the generic path. `APE2_FASTDEC=0` disables it;
`APE2_FASTDEC_CHECK=1` decodes the first 300 textures both ways: 0 of 300 mismatched in a play session (T8, T4,
CT32 among them).

Result in the same stage: 52-60 fps (was 40-48), GS thread ~30% busy. Player: "feels a lot smoother, not 60 but
smoother". Still open: the remaining dips, and the mip-level bands on the floors.
### 0230 - Trilinear blend in the GPU renderer; what the "white layer" on the floors is (0063)

- The trilinear filters (MMIN 3, 5) blend floor(LOD) and the next level per pixel; we drew one level per
  primitive. The frontend now also prepares the next level (`g_ape2MipBlend`, a thread-local side channel to the
  GL backend, so `GSDrawState` did not change) and the fragment shader blends it in by the per-pixel LOD,
  `-log2(|q|) * 2^L + K` from the interpolated Q (`u_tex2`, `u_lod`). `APE2_GS_TRILINEAR=0` disables it; the
  software renderer keeps one level. 54-60 fps over a 15-minute session.
- The player still sees a light, whitish layer on the stage floors that moves as you walk, gone with
  `APE2_GS_MIPMAP=0` (which brings back the flickering garbage). A probe (`[mip:probe]`, during an F9 burst:
  mipmapped primitives covering `APE2_PROBE_PT=x,y`) shows the floor drawn twice with one texture: an opaque
  base pass with K -18.1, L 1 (levels 1-2 near the camera), and a blended detail pass with K -20.0 (level 0).
  All those levels are uploaded every frame (0x2fe0 / 0x30e0 / 0x3120 ...), and the levels match the GS
  formula, so the paler middle distance is most likely the PS2's own look (averaged, lower-contrast levels under
  the sharp detail pass). To be compared with PCSX2 or a console before changing anything.
### 0231 - FMVs at their real length: the audio feed paced them (0064)

- The intro (D1.PSS) is 39.8 s by its PTS; we took ~60 s, and it took that long however the EE was changed
  (clock catch-up, IOP cost, frame lock off: 60 fps presented, still 56 s). The player follows its audio: the
  48 kHz stereo PCM (`SShd`: type 1, 48000, 2 ch, 512 interleave) arrived at ~133 blocks/s for 187.5
  (`[spu2:wall]`), because the auto-DMA block period is the 0206 calibration, 1240 IOP cycles per word, tuned on
  the title music. 880 gave the movie its 40 s and overfed the music (dropped blocks climbing). The period now
  follows the playback queue, as the SPU2 paces it on the hardware: calibrated x (0.3 + 0.15 x depth), 0.4x to
  1.6x (`admaPaced`, `APE2_SPU2_ADMA_ADAPT=0`). Intro 40 s, music afterwards with no steady drops. Player: "very
  nice, sounds great, only counted 7 fps dips in the intro".
- The IOP was 44% of the EE thread in the FMVs: `runCycles` read the clock on every call for a probe that logs
  every 2 s (now once per 1024 calls), and the IOP was stepped for every owed cycle (now once 64 are owed,
  `APE2_IOP_BATCH`).
- Found on the way, not changed yet: guest thread switches throw a C++ exception (`EeDispatcherTransfer`,
  `CxxThrowException` ~17% of the EE thread in the movies, which yield tens of thousands of times a second).
### 0232 - Thread switches without a C++ throw (0065)

- `APE2_XFERLOG` counts thread transfers per kind: in the FMVs ~70,000 a second are yields, all
  RotateThreadReadyQueue(11) through 0x1a54f0 from two threads that hand the CPU to each other (0x1a4e84 in the
  movie loop, 0x1a9158 in a loop that spins until 0x1aa578 has data). Every switch threw `EeDispatcherTransfer`
  to drop the guest code's native frames, ~17% of the EE thread in throw/unwind.
- When the syscall handler is the only host frame between the scheduler loop and the guest code, and the guest
  continues with just `jr $ra; nop` (every libkernel syscall stub), the switch now unwinds by returns: the stub
  returns, its caller's `dispatchGuestBranch` sees the deferred transfer and returns false, and so on up to the
  loop. Host frames are tracked by a counter: slots set through `replaceFunction` (stubs, game overrides), the
  syscall handler itself and the scheduler's completion callbacks. `APE2_XFER_DEFER=0` always throws.
- Intro: yield throws 70,000/s -> ~0; 55.5 -> 56.6 fps average, 2 s windows under 55: 9 -> 5. Player: "much
  smoother overall", dips 7 -> 3-4 (always in the same spots of the movie), music fine, gameplay fine; big dips
  remain in the pause menu and the stage select screen.
### 0233 - GPU renderer: row read-backs, GPU local copies, textures cached by content (0066)

- `APE2_SYNCLOG` names every GPU read-back (cause, source range, target, time) and every texture decode (address,
  format, size) per 2 s.
- Read-backs: a palette load of 8 blocks at the frame buffer's base read the whole 512x448 frame back every
  frame in play. `syncRange` now reads back only the page rows of the requested blocks, and each target keeps a
  per-row map of rows read back since they were last drawn; those rows are never read back again (VRAM is the
  newer copy: the game uploads icons into them, and a later whole read-back wrote the old drawing over them -
  the striped coin stack and button icons in the pause menu). Transfers start at the page row of their first
  row. `APE2_SYNC_ROWS=0` restores whole-target read-backs.
- The pause menu and the stage select copy whole 512x448 frames between targets every frame (local-to-local,
  0xe00 -> 0x0, 0x2a00.. -> 0xe00): each one read both targets back, copied in VRAM and uploaded again, ~250 ms
  in every 2 s. Copies between two targets of the same colour format are now a `glBlitFramebuffer`; the
  destination rectangle is marked as drawn (`APE2_GPU_COPY=0`). Read-backs in the pause menu: ~250 -> ~90 ms/2 s.
- Textures by content: the game streams its textures (uploads them again into a shared VRAM area every frame
  and draws with them right away). In play the address-keyed cache saw ~8,000 stale textures a second, ~230 M
  texels decoded and uploaded to GL a second, the GS thread's main cost. A texture whose VRAM was rewritten is now
  hashed (its pages, format, size, in-page offset, palette and TEXA keys; not its address) and the same content
  reuses the GL texture decoded before (`APE2_GL_TEXHASH=0`). Measured: ~9,000 hits and ~1,000 misses a second,
  decoded texels 460 M -> 5 M per 2 s. A first version let textures that wrap around VRAM (no private page copy)
  decode into a shared texture and corrupted other textures' copies (purple coin stack); fixed.
  `APE2_GL_TEXHASH_CHECK=1` decodes every hit again and compares: 376,000 hits checked in play, 0 wrong.
- Player: gameplay "fps feels nice", icons clean; the pause menu and the stage select are still not smooth.

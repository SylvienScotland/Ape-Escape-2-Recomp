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

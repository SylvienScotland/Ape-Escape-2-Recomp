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

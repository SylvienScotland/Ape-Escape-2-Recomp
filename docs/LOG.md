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

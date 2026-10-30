# Handoff: where the project stands

Read this first, then the end of docs/LOG.md (full history).

## Setup (user's PC, Windows)
- Repo: `C:\dev\Ape-Escape-2-Recomp`; PS2Recomp clone: `C:\dev\PS2Recomp` (pinned commit in tools/build_windows.ps1,
  our fixes in patches/ps2recomp/*.patch, applied ones recorded in `C:\dev\PS2Recomp\.ape2_patches_applied`).
- Extracted disc: `C:\Users\truga\Downloads\Ape Escape 2 demounted`
- ISO: `C:\Users\truga\Downloads\Ape Escape 2 (USA)\Ape Escape 2 (USA).iso`
- Toolchain: VS 2022 Build Tools (MSVC 19.44), run from "Developer PowerShell for VS 2022".
- Build + boot (no regen):
  `.\tools\build_windows.ps1 -GameDir "C:\Users\truga\Downloads\Ape Escape 2 demounted" -IsoPath "C:\Users\truga\Downloads\Ape Escape 2 (USA)\Ape Escape 2 (USA).iso" -SkipToolBuild -SkipRecomp`
  Drop `-SkipRecomp` after changing config/ape2.toml. Output: `boot.log` in the repo root.
- Rebuild cost rules: see docs/BUILD_WINDOWS.md (avoid PCH headers; new override files named `zz_*`).

## State
Boots: memory card check -> "presents" -> intro FMV (skipped by override) -> in-engine 3D intro renders,
but ~1 frame per 6-7 s. 2D screens 9-22 fps with the software rasterizer at ~86%.

## Current step: performance
Profiler patches 0003-0005 print `[perf]` (per-zone time) and `[perf:pc]` (hottest guest PCs) every ~2 s.
Known: ee-wait ~0%, so "other" (EE game code / runtime helpers) dominates the 3D intro. Suspect a guest
busy-wait polling a HW flag. 0005 has been committed but NOT yet built/run on the user's PC (no `[perf:pc]`
lines in any log so far).
Next (user runs, unattended, ~2 min; the 3D intro starts ~55 s after boot):
`git pull`, then
`.\tools\build_windows.ps1 -GameDir "..." -IsoPath "..." -SkipToolBuild -SkipRecomp -RunSeconds 120`
It applies 0005, rebuilds, stops the game after 120 s and writes `perf.txt` (tools/perf_summary.ps1:
merged PC ranking for slow frames + whole run, then the raw `[perf]` lines; plain ASCII).
Then read the top PCs: `python tools/mdis.py game/SLUS_206.85 0x<pc> 64` (capstone; R5900 COP2/MMI ops
mis-decode) or the generated C++ in generated/output.
Do NOT use `[run:tick] pc=` for profiling: that PC is only stored at scheduler dispatch, so it lands on
function entries / call-return points (0x353320, 0x208B60, 0x19BD34...). The 0005 sampler reads the live
`ctx->pc`, which generated code writes before every instruction.
Known code: 0x19BCB8 = per-frame loop (calls main frame function 0x19BCE0 until nonzero, then sceGsSyncPath).

## After performance (user's order)
1. Picture: 512x512 FB region with a duplicated bottom band (display rect vs 640x448), washed colours,
   doubled text (interlace/field presentation).
2. Controller input.
Later: real FMV playback (sceMpegGetPictureRAW8 + IPU CSC), proper guest heap layout (see LOG), remove trace overrides.

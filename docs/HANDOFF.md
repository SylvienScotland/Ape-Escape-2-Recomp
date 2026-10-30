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
busy-wait polling a HW flag. Next: run 30 s into the 3D intro, then
`Select-String -Path boot.log -Pattern '^\[perf' | % { $_.Line }`, read the top PCs, disassemble them in
generated/output (regenerate locally with ps2_recomp + config/ape2.toml if needed).
Nice to have: an auto-exit after N seconds for unattended runs.

## After performance (user's order)
1. Picture: 512x512 FB region with a duplicated bottom band (display rect vs 640x448), washed colours,
   doubled text (interlace/field presentation).
2. Controller input.
Later: real FMV playback (sceMpegGetPictureRAW8 + IPU CSC), proper guest heap layout (see LOG), remove trace overrides.

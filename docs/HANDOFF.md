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

## Running it unattended (how Claude does it)
From a plain shell (no dev prompt needed):
`cmd /c "call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\Ape-Escape-2-Recomp\tools\build_windows.ps1 -Ps2RecompDir C:\dev\PS2Recomp -GameDir ... -IsoPath ... -SkipToolBuild -SkipRecomp -RunSeconds 150 > log.txt 2>&1"`
(pass -Ps2RecompDir explicitly with -File; let cmd redirect, never a PowerShell `*>`). `-RunOnly` skips the build.
Debug env vars (patches 0010/0013): APE2_FRAME_DUMP=<dir>, APE2_FRAME_DUMP_EVERY=20, APE2_FRAME_DUMP_VRAM=1,
APE2_GS_TRACE=1. Profiling (0003-0007) prints [perf], [perf:pc], [perf:host-self/incl], [perf:iop]; perf.txt
is written by tools/perf_summary.ps1 after -RunSeconds.

## State
Boots unattended to the title screen ("Press the START button") in < 150 s: memory card check, UbiSoft and
SCE logos, intro FMV (skipped by override), in-engine 3D intro, title. 2D screens and textures now render
correctly (see LOG "Picture: from garbled to a correct title screen").
Speed: 2D screens ~20 fps; 3D intro / title ~0.5-1 fps. The IOP SPU2 AutoDMA storm is fixed (0008).

## Next steps
1. Performance: the 3D scenes are now pure emulation cost, ~50% GS software rasterizer (DrawTriangle,
   SampleTexture, lerpChannel, LookupCLUT) and ~45% VU1 interpreter (commitReadyPipelines,
   calculatePairReadyCycle: cycle-accurate pipeline bookkeeping). Profile with perf.txt host rankings.
2. Controller input (title screen waits for START).
3. Picture details still open: PMODE anti-flicker merge ignores the 1-line DISPLAY offset between the two
   CRTs (harmless); check the 3D intro frames for remaining issues.
Later: real FMV playback (sceMpegGetPictureRAW8 + IPU CSC), proper guest heap layout (see LOG), remove trace overrides.
Pushing: `git push origin main` works from this PC (Windows credential manager). No git identity is configured; commits use -c user.name=Claude -c user.email=noreply@anthropic.com.
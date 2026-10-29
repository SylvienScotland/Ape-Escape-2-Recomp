# Building and booting on Windows

## One-time setup
1. **Visual Studio 2022** with the "Desktop development with C++" workload (includes CMake).
2. **Git for Windows**.
3. **Your game files:** extract the full Ape Escape 2 (USA) ISO into a folder, e.g. `D:\AE2\disc`
   (mount it and copy everything, or use 7-Zip). `SLUS_206.85` and `SYSTEM.CNF` must be at the top level.

## Build + boot
Open **Developer PowerShell for VS 2022**, then:

```powershell
git clone https://github.com/SylvienScotland/Ape-Escape-2-Recomp.git
cd Ape-Escape-2-Recomp
Set-ExecutionPolicy -Scope Process Bypass
.\tools\build_windows.ps1 -GameDir "D:\AE2\disc"
```

What it does:
1. Checks your `SLUS_206.85` matches the USA build (SHA1 in DISC.md).
2. Clones PS2Recomp next to this repo, pinned to the commit we tested.
3. Builds the recompiler and regenerates the C++ from `config/ape2.toml` (generated code never goes in git).
4. Copies the generated code into PS2Recomp's runtime and builds `ps2EntryRunner.exe`.
   This is the slow step: ~8.5k generated files. Expect a long first build.
5. Boots the game and writes everything it prints to `boot.log`.

Re-runs: add `-SkipToolBuild -SkipRecomp` to only rebuild and boot. Use `-NoRun` to just build.

## What to send back
- If the build fails: the first ~30 lines that contain `error`.
- If it boots (or crashes): `boot.log`, or its last ~300 lines if it's huge.

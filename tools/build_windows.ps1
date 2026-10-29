<#
  Ape Escape 2 Recomp - Windows build + first boot.

  Run from the repo root in a "Developer PowerShell for VS 2022":
    .\tools\build_windows.ps1 -GameDir "D:\AE2\disc"

  -GameDir : folder with the extracted contents of YOUR Ape Escape 2 (USA) ISO
             (must contain SLUS_206.85 and SYSTEM.CNF at the top level).
  Steps you can skip on re-runs: -SkipToolBuild, -SkipRecomp
#>
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [string]$Ps2RecompDir = "$PSScriptRoot\..\..\PS2Recomp",
    [string]$Ps2RecompCommit = "e5636981a1c9de368f6b71e819c3dc188dfedbf4",
    [ValidateSet("Debug", "RelWithDebInfo", "Release")][string]$Config = "RelWithDebInfo",
    [switch]$SkipToolBuild,
    [switch]$SkipRecomp,
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
$Elf = Join-Path $GameDir "SLUS_206.85"
$ExpectedSha1 = "AEDE190625B1D96C725B28CA45CD3883EC266B23"

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# 0. Check the game files
Step "Checking game files"
if (-not (Test-Path $Elf)) { throw "SLUS_206.85 not found in $GameDir. Extract the full ISO there." }
$sha1 = (Get-FileHash $Elf -Algorithm SHA1).Hash
if ($sha1 -ne $ExpectedSha1) { throw "SLUS_206.85 hash $sha1 does not match the expected USA build ($ExpectedSha1)." }
New-Item -ItemType Directory -Force "$Repo\game" | Out-Null
Copy-Item $Elf "$Repo\game\SLUS_206.85" -Force
Write-Host "OK: USA build verified."

# 1. Get PS2Recomp at the pinned commit
Step "PS2Recomp @ $Ps2RecompCommit"
if (-not (Test-Path "$Ps2RecompDir\.git")) {
    git clone https://github.com/ran-j/PS2Recomp.git $Ps2RecompDir
}
git -C $Ps2RecompDir fetch --quiet origin
git -C $Ps2RecompDir checkout --quiet $Ps2RecompCommit
git -C $Ps2RecompDir submodule update --init --recursive
$Ps2RecompDir = (Resolve-Path $Ps2RecompDir).Path
$ToolBuild = "$Ps2RecompDir\out\tools"
$RunBuild  = "$Ps2RecompDir\out\runner"

# 2. Build the recompiler
if (-not $SkipToolBuild) {
    Step "Building ps2_recomp"
    cmake -S $Ps2RecompDir -B $ToolBuild -DPS2X_BUILD_RUNTIME=OFF -DPS2X_BUILD_TEST=OFF -DPS2X_BUILD_STUDIO=OFF
    cmake --build $ToolBuild --config Release --target ps2_recomp
}
$Recomp = Get-ChildItem -Recurse -Filter ps2_recomp.exe $ToolBuild | Select-Object -First 1
if (-not $Recomp) { throw "ps2_recomp.exe not found under $ToolBuild" }

# 3. Recompile the game
if (-not $SkipRecomp) {
    Step "Recompiling SLUS_206.85"
    Push-Location $Repo
    try { & $Recomp.FullName "config\ape2.toml" | Tee-Object -FilePath "$Repo\generated_recomp.log" | Select-Object -Last 3 }
    finally { Pop-Location }
}
$Gen = "$Repo\generated\output"
if (-not (Test-Path "$Gen\register_functions.cpp")) { throw "No generated output in $Gen" }

# 4. Drop generated code into the runtime (that's how ps2xRuntime picks it up)
Step "Copying generated code into ps2xRuntime"
$RunnerSrc = "$Ps2RecompDir\ps2xRuntime\src\runner"
$RunnerInc = "$Ps2RecompDir\ps2xRuntime\include"
Copy-Item "$Gen\*.cpp" $RunnerSrc -Force
Copy-Item "$Gen\ps2_recompiled_functions.h", "$Gen\ps2_recompiled_stubs.h" $RunnerInc -Force
# Game-specific overrides live in our repo
Get-ChildItem "$Repo\overrides\*.cpp" -ErrorAction SilentlyContinue | Copy-Item -Destination $RunnerSrc -Force

# 5. Build the runner (this is the long one: ~8.5k generated files)
Step "Building ps2EntryRunner ($Config)"
cmake -S $Ps2RecompDir -B $RunBuild -DPS2X_BUILD_RECOMP=OFF -DPS2X_BUILD_ANALYZER=OFF -DPS2X_BUILD_TEST=OFF -DPS2X_BUILD_STUDIO=OFF
cmake --build $RunBuild --config $Config --target ps2EntryRunner --parallel
$Runner = Get-ChildItem -Recurse -Filter ps2EntryRunner.exe $RunBuild | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Runner) { throw "ps2EntryRunner.exe not built" }
Write-Host "Built: $($Runner.FullName)"

# 6. First boot, with a log
if (-not $NoRun) {
    Step "Booting (log: boot.log). Close the window or Ctrl+C to stop."
    $Log = "$Repo\boot.log"
    & $Runner.FullName $Elf 2>&1 | Tee-Object -FilePath $Log
    Write-Host "`nLog saved to $Log. Attach it (or the last ~300 lines) to the chat."
}

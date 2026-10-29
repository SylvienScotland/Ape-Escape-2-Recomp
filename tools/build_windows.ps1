<#
  Ape Escape 2 Recomp - Windows build + first boot.

  Run from the repo root in a "Developer PowerShell for VS 2022":
    .\tools\build_windows.ps1 -GameDir "D:\AE2\disc"

  -GameDir : folder with the extracted contents of YOUR Ape Escape 2 (USA) ISO
             (must contain SLUS_206.85 and SYSTEM.CNF at the top level).
  Steps you can skip on re-runs: -SkipToolBuild, -SkipRecomp, or -RunOnly to just boot
#>
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [string]$Ps2RecompDir = "$PSScriptRoot\..\..\PS2Recomp",
    [string]$Ps2RecompCommit = "e5636981a1c9de368f6b71e819c3dc188dfedbf4",
    [ValidateSet("Debug", "RelWithDebInfo", "Release")][string]$Config = "RelWithDebInfo",
    [switch]$SkipToolBuild,
    [switch]$SkipRecomp,
    [switch]$NoRun,
    [switch]$RunOnly   # just boot the already-built exe
)
if ($RunOnly) { $SkipToolBuild = $true; $SkipRecomp = $true }

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
if (-not $RunOnly) {
    git -C $Ps2RecompDir fetch --quiet origin
    git -C $Ps2RecompDir checkout --quiet $Ps2RecompCommit
    git -C $Ps2RecompDir submodule update --init --recursive

    # Our fixes to PS2Recomp, kept as patches in this repo (idempotent: skip if already applied)
    foreach ($p in Get-ChildItem "$Repo\patches\ps2recomp\*.patch" -ErrorAction SilentlyContinue | Sort-Object Name) {
        $ErrorActionPreference = "Continue"
        git -C $Ps2RecompDir apply --reverse --check $p.FullName 2>$null
        $already = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        if ($already) { Write-Host "patch already applied: $($p.Name)"; continue }
        git -C $Ps2RecompDir apply $p.FullName
        if ($LASTEXITCODE -ne 0) { throw "Failed to apply $($p.Name)" }
        Write-Host "applied patch: $($p.Name)"
    }
}
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

if (-not $RunOnly) {
# 4. Drop generated code into the runtime (that's how ps2xRuntime picks it up)
Step "Copying generated code into ps2xRuntime"
$RunnerSrc = "$Ps2RecompDir\ps2xRuntime\src\runner"
$RunnerInc = "$Ps2RecompDir\ps2xRuntime\include"
# Only copy files whose contents changed. The recompiler rewrites every file on each run, and a
# blanket copy would make MSBuild rebuild all ~8.5k files even when one function changed.
function Copy-IfChanged($src, $dstDir) {
    $dst = Join-Path $dstDir (Split-Path $src -Leaf)
    if (Test-Path $dst) {
        $a = Get-Item $src; $b = Get-Item $dst
        if ($a.Length -eq $b.Length -and
            (Get-FileHash $src -Algorithm MD5).Hash -eq (Get-FileHash $dst -Algorithm MD5).Hash) { return $false }
    }
    Copy-Item $src $dst -Force
    return $true
}
$changed = 0
foreach ($f in Get-ChildItem "$Gen\*.cpp") { if (Copy-IfChanged $f.FullName $RunnerSrc) { $changed++ } }
foreach ($h in "ps2_recompiled_functions.h", "ps2_recompiled_stubs.h") { if (Copy-IfChanged "$Gen\$h" $RunnerInc) { $changed++; Write-Host "header changed: $h (expect a full rebuild)" } }
Write-Host "generated files changed: $changed"
# Game-specific overrides live in our repo
foreach ($o in Get-ChildItem "$Repo\overrides\*.cpp" -ErrorAction SilentlyContinue) { [void](Copy-IfChanged $o.FullName $RunnerSrc) }
}

# 5. Build the runner (this is the long one: ~8.5k generated files)
if (-not $RunOnly) {
    Step "Building ps2EntryRunner ($Config)"
    cmake -S $Ps2RecompDir -B $RunBuild -DPS2X_BUILD_RECOMP=OFF -DPS2X_BUILD_ANALYZER=OFF -DPS2X_BUILD_TEST=OFF -DPS2X_BUILD_STUDIO=OFF
    cmake --build $RunBuild --config $Config --target ps2EntryRunner --parallel
}
$Runner = Get-ChildItem -Recurse -Filter ps2EntryRunner.exe $RunBuild | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Runner) { throw "ps2EntryRunner.exe not built" }
Write-Host "Built: $($Runner.FullName)"

# 6. First boot, with a log
if (-not $NoRun) {
    Step "Booting (log: boot.log). Close the game window to stop."
    $Log = "$Repo\boot.log"
    # The runtime logs to stderr. Windows PowerShell turns native stderr into errors (and we run
    # with -Stop), so let cmd do the redirection instead and just show the tail afterwards.
    $ErrorActionPreference = "Continue"
    cmd /c "`"$($Runner.FullName)`" `"$Elf`" > `"$Log`" 2>&1"
    Write-Host "Exit code: $LASTEXITCODE"
    Write-Host "--- last 40 lines of boot.log ---"
    Get-Content $Log -Tail 40
    Write-Host "`nFull log: $Log. Attach it to the chat."
}

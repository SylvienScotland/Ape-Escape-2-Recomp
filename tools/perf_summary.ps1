<#
  Summarize the profiler output in boot.log (patches 0003-0006) into a small ASCII text file.

    .\tools\perf_summary.ps1                       # boot.log -> perf.txt in the repo root
    .\tools\perf_summary.ps1 -Log x.log -Out y.txt

  [perf] lines are copied as-is. [perf:pc] windows (top 12 guest PCs per ~2 s) are merged into one
  ranking per regime, weighted by each window's sample count:
    slow  = windows following a [perf] line under -SlowFps (the 3D intro, ~0.3 fps)
    all   = every window
  The sampler and the [perf] printer are separate threads, so the regime split is approximate.
  Per-window percentages are rounded and only the top 12 are printed, so the totals are estimates.
#>
param(
    [string]$Log = "$PSScriptRoot\..\boot.log",
    [string]$Out = "$PSScriptRoot\..\perf.txt",
    [double]$SlowFps = 2.0,
    [int]$Top = 25
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Log)) { throw "Log not found: $Log" }

$perfLines = New-Object System.Collections.Generic.List[string]
$iopLines = New-Object System.Collections.Generic.List[string]
$slow = @{}; $all = @{}
$hostTables = @{}; $hostSamples = @{}; $hostWindows = @{}
foreach ($k in "perf:host-self/slow", "perf:host-self/all", "perf:host-incl/slow", "perf:host-incl/all") {
    $hostTables[$k] = @{}; $hostSamples[$k] = 0.0; $hostWindows[$k] = 0
}
$slowSamples = 0.0; $allSamples = 0.0; $slowWindows = 0; $allWindows = 0
$lastFps = 999.0

function Add-Window($table, $line, [ref]$sampleTotal) {
    if ($line -notmatch 'samples=(\d+)') { return $false }
    $n = [double]$Matches[1]
    $sampleTotal.Value += $n
    foreach ($m in [regex]::Matches($line, '0x([0-9a-fA-F]+) (\d+)%')) {
        $pc = $m.Groups[1].Value.ToLower()
        $w = $n * [double]$m.Groups[2].Value / 100.0
        if ($table.ContainsKey($pc)) { $table[$pc] += $w } else { $table[$pc] = $w }
    }
    return $true
}

# [perf:host-*] samples=N | 31% name | ...  (patch 0006; names have no "|")
function Add-HostWindow($key, $line) {
    if ($line -notmatch 'samples=(\d+)') { return }
    $n = [double]$Matches[1]
    $hostSamples[$key] += $n; $hostWindows[$key]++
    $table = $hostTables[$key]
    foreach ($part in ($line -split ' \| ' | Select-Object -Skip 1)) {
        if ($part -notmatch '^(\d+)% (.+)$') { continue }
        $w = $n * [double]$Matches[1] / 100.0
        $name = $Matches[2]
        if ($table.ContainsKey($name)) { $table[$name] += $w } else { $table[$name] = $w }
    }
}

foreach ($line in [System.IO.File]::ReadLines((Resolve-Path $Log).Path)) {
    if ($line.StartsWith("[perf] ")) {
        $perfLines.Add($line)
        if ($line -match 'frames \d+ \(([\d.]+)/s\)') { $lastFps = [double]$Matches[1] }
    } elseif ($line.StartsWith("[perf:pc]")) {
        if (Add-Window $all $line ([ref]$allSamples)) { $allWindows++ }
        if ($lastFps -lt $SlowFps) {
            if (Add-Window $slow $line ([ref]$slowSamples)) { $slowWindows++ }
        }
    } elseif ($line.StartsWith("[perf:iop]")) {
        $iopLines.Add($line)
    } elseif ($line -match '^\[(perf:host-(self|incl))\]') {
        $key = $Matches[1]
        Add-HostWindow "$key/all" $line
        if ($lastFps -lt $SlowFps) { Add-HostWindow "$key/slow" $line }
    }
}

function Format-Ranking($title, $table, $total, $windows) {
    $rows = @("", "== $title : $windows windows, $([int]$total) samples ==")
    if ($total -le 0) { return $rows + "(no [perf:pc] data; is patch 0005 applied?)" }
    $rank = $table.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First $Top
    foreach ($e in $rank) {
        $rows += ("0x{0,-8} {1,5:N1}%" -f $e.Key, (100.0 * $e.Value / $total))
    }
    return $rows
}

$outLines = @("# perf summary of $Log")
$outLines += Format-Ranking "guest PCs, slow frames (< $SlowFps fps)" $slow $slowSamples $slowWindows
$outLines += Format-Ranking "guest PCs, whole run" $all $allSamples $allWindows
function Format-HostRanking($title, $key) {
    $total = $hostSamples[$key]
    $rows = @("", "== $title : $($hostWindows[$key]) windows, $([int]$total) samples ==")
    if ($total -le 0) { return $rows + "(no [perf:host-*] data; is patch 0006 applied? Windows only)" }
    $rank = $hostTables[$key].GetEnumerator() | Sort-Object Value -Descending | Select-Object -First $Top
    foreach ($e in $rank) { $rows += ("{0,5:N1}%  {1}" -f (100.0 * $e.Value / $total), $e.Key) }
    return $rows
}
$outLines += Format-HostRanking "host functions, self, slow frames" "perf:host-self/slow"
$outLines += Format-HostRanking "host functions, inclusive, slow frames" "perf:host-incl/slow"
$outLines += Format-HostRanking "host functions, inclusive, whole run" "perf:host-incl/all"
$outLines += @("", "== [perf] zone lines ==")
$outLines += $perfLines
$outLines += @("", "== [perf:iop] IOP DMA interrupt handler lines (patch 0007) ==")
$outLines += $iopLines
Set-Content -Path $Out -Value $outLines -Encoding ascii
Write-Host "perf summary: $Out"
$outLines | Select-Object -First ($Top + 4) | ForEach-Object { Write-Host $_ }

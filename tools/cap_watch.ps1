# Watch for the game window to become the foreground window, then capture short bursts.
#
# Flicker is a difference between consecutive frames, so one screenshot can never show it. This
# waits until the game is verifiably in the foreground (so no other window can appear in the
# capture), then takes pairs of frames a fraction of a second apart, repeatedly, and records the
# mean brightness of each so the analysis can tell a real capture from a black or stale one.
param(
    [int]$Seconds = 300,
    [int]$RoundEveryMs = 2000,
    [int]$PairGapMs = 250,
    [string]$OutDir = "C:\dev\Ape-Escape-2-Recomp\dumps\live",
    [string]$ProcName = "ps2EntryRunner"
)

Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WatchCap {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT p);
}
"@

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$log = Join-Path $OutDir "capture_log.txt"
"[$(Get-Date -Format HH:mm:ss)] waiting for the game window to be foreground; up to $Seconds s" |
    Out-File -FilePath $log -Encoding utf8

function Get-Mean($bmp) {
    $w = $bmp.Width; $h = $bmp.Height
    $rect = New-Object System.Drawing.Rectangle(0, 0, $w, $h)
    $data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
                          [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $bytes = New-Object byte[] ($data.Stride * $h)
    [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
    $bmp.UnlockBits($data)
    $sum = 0.0; $n = 0
    for ($i = 0; $i -lt $bytes.Length; $i += 3003) { $sum += $bytes[$i]; $n++ }
    if ($n -eq 0) { return 0 }
    return [math]::Round($sum / $n, 1)
}

$deadline = (Get-Date).AddSeconds($Seconds)
$round = 0
$captured = 0

while ((Get-Date) -lt $deadline) {
    $p = Get-Process -Name $ProcName -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { Start-Sleep -Milliseconds 500; continue }
    $h = $p.MainWindowHandle
    if ([WatchCap]::GetForegroundWindow() -ne $h) { Start-Sleep -Milliseconds 400; continue }

    $cr = New-Object WatchCap+RECT
    [void][WatchCap]::GetClientRect($h, [ref]$cr)
    $pt = New-Object WatchCap+POINT
    [void][WatchCap]::ClientToScreen($h, [ref]$pt)
    $w = $cr.Right - $cr.Left; $ht = $cr.Bottom - $cr.Top
    if ($w -le 0 -or $ht -le 0) { Start-Sleep -Milliseconds 500; continue }

    foreach ($k in 0, 1) {
        $bmp = New-Object System.Drawing.Bitmap($w, $ht)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($pt.X, $pt.Y, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
        $mean = Get-Mean $bmp
        $out = Join-Path $OutDir ("r{0:d3}_{1}.png" -f $round, $k)
        $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        "[$(Get-Date -Format HH:mm:ss)] round $round frame $k mean=$mean -> $(Split-Path $out -Leaf)" |
            Out-File -FilePath $log -Encoding utf8 -Append
        $captured++
        if ($k -eq 0) { Start-Sleep -Milliseconds $PairGapMs }
    }
    $round++
    Start-Sleep -Milliseconds $RoundEveryMs
}

"[$(Get-Date -Format HH:mm:ss)] done: $captured frames in $round rounds" | Out-File -FilePath $log -Encoding utf8 -Append

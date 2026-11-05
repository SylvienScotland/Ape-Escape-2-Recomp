# Capture the game's own window to a PNG - only when it is verifiably in the foreground.
#
# The first version captured whatever was on screen at the window's rectangle, which grabbed an
# unrelated browser window that happened to be on top. This version refuses unless the game window
# is the foreground window, and it only copies that window's client area.
param(
    [string]$Out = "C:\dev\Ape-Escape-2-Recomp\dumps\window.png",
    [string]$ProcName = "ps2EntryRunner"
)

Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Cap {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT p);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hWnd, uint cmd);
}
"@

$p = Get-Process -Name $ProcName -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) {
    Write-Output "REFUSED: no visible $ProcName window. Start the game first."
    exit 2
}

$h = $p.MainWindowHandle
$fg = [Win32Cap]::GetForegroundWindow()

# the game window may be a child of a top-level window owned by the same process; accept that too
$fgRoot = $fg
while ($fgRoot -ne [IntPtr]::Zero) {
    $parent = [Win32Cap]::GetWindow($fgRoot, 4)  # GW_OWNER
    if ($parent -eq [IntPtr]::Zero) { break }
    $fgRoot = $parent
}

if ($fg -ne $h -and $fgRoot -ne $h) {
    Write-Output "REFUSED: the game window is not in the foreground (another window is active)."
    Write-Output "Click on the game, keep it in front, and run this again."
    exit 3
}

$cr = New-Object Win32Cap+RECT
[void][Win32Cap]::GetClientRect($h, [ref]$cr)
$cpt = New-Object Win32Cap+POINT
[void][Win32Cap]::ClientToScreen($h, [ref]$cpt)
$w = $cr.Right - $cr.Left
$ht = $cr.Bottom - $cr.Top
if ($w -le 0 -or $ht -le 0) {
    Write-Output "REFUSED: client area has no size ($w x $ht)."
    exit 4
}

$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($cpt.X, $cpt.Y, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output "saved $Out ($w x $ht) from the foreground game window"

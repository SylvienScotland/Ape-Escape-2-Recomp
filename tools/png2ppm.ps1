# Convert window captures (PNG) to binary PPM so the existing Python analysis tools can read them.
param(
    [string]$Dir = "C:\dev\Ape-Escape-2-Recomp\dumps\live"
)

Add-Type -AssemblyName System.Drawing

$files = Get-ChildItem -Path $Dir -Filter *.png | Sort-Object Name
if (-not $files) { Write-Output "no PNGs in $Dir"; exit 1 }

foreach ($f in $files) {
    $bmp = [System.Drawing.Bitmap]::FromFile($f.FullName)
    $w = $bmp.Width; $h = $bmp.Height
    $rect = New-Object System.Drawing.Rectangle(0, 0, $w, $h)
    $data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
                          [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $stride = $data.Stride
    $buf = New-Object byte[] ($stride * $h)
    [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $buf.Length)
    $bmp.UnlockBits($data)
    $bmp.Dispose()

    $rowBytes = $w * 3
    $ms = New-Object System.IO.MemoryStream
    $hdr = [System.Text.Encoding]::ASCII.GetBytes("P6`n$w $h`n255`n")
    $ms.Write($hdr, 0, $hdr.Length)
    for ($y = 0; $y -lt $h; $y++) { $ms.Write($buf, $y * $stride, $rowBytes) }
    $outPath = [System.IO.Path]::ChangeExtension($f.FullName, ".ppm")
    [System.IO.File]::WriteAllBytes($outPath, $ms.ToArray())
    $ms.Dispose()
}
Write-Output "converted $($files.Count) PNGs in $Dir to PPM"

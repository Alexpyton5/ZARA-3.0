Add-Type -AssemblyName System.Drawing
$root = $PSScriptRoot
$m = [System.Drawing.Image]::FromFile("$root\master.png")
$e = [System.Drawing.Image]::FromFile("$root\electron-check.png")
$gap = 12
$h = [Math]::Max($m.Height, $e.Height)
$w = $m.Width + $gap + $e.Width
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(20, 20, 20))
$g.DrawImage($m, 0, 0, $m.Width, $m.Height)
$g.DrawImage($e, $m.Width + $gap, 0, $e.Width, $e.Height)
$g.Dispose()
$bmp.Save("$root\comparativo-final.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $m.Dispose(); $e.Dispose()
Write-Output "OK ${w}x${h}"

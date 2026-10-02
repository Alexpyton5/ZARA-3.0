$exe = "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend" + "\release" + "\win-unpacked" + "\resources" + "\backend" + "\zara-backend.exe"
$work = "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
Write-Host ("exists=" + (Test-Path $exe))
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -WorkingDirectory $work -RedirectStandardOutput "$work\out3.txt" -RedirectStandardError "$work\err3.txt" -PassThru -Wait
$sw.Stop()
Write-Host ("dur_ms=" + $sw.ElapsedMilliseconds + " exit=" + $p.ExitCode)

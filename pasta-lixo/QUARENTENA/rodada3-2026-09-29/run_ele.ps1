$work = "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend"
$p = Start-Process -FilePath "npm.cmd" -ArgumentList "run","electron:build" -WorkingDirectory $work -RedirectStandardOutput "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\ele_out.txt" -RedirectStandardError "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\ele_err.txt" -PassThru -Wait -NoNewWindow
Write-Host ("exit=" + $p.ExitCode)

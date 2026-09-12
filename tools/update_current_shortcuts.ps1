$ErrorActionPreference = 'Stop'
$zaraProjectRoot = Split-Path -Parent $PSScriptRoot
$zaraInfo = Get-Content -LiteralPath (Join-Path $zaraProjectRoot 'ZARA_ACTIVE_BUILD.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($zaraInfo.STATUS -ne 'active-validated' -or -not (Test-Path -LiteralPath $zaraInfo.EXE_PATH)) {
    throw 'Somente um build ativo validado pode atualizar os atalhos.'
}
$zaraLauncher = Join-Path $PSScriptRoot 'launch_current.ps1'
$zaraShell = New-Object -ComObject WScript.Shell
$zaraShortcutPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$zaraDesktop = [Environment]::GetFolderPath('Desktop')
$zaraStartMenu = [Environment]::GetFolderPath('StartMenu')
[void]$zaraShortcutPaths.Add((Join-Path $zaraDesktop 'ZARA CURRENT BUILD.lnk'))
[void]$zaraShortcutPaths.Add((Join-Path $zaraStartMenu 'Programs\ZARA 3.0.lnk'))
$zaraSearchRoots = @($zaraDesktop, $zaraStartMenu, (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned'))
foreach ($zaraSearchRoot in $zaraSearchRoots) {
    if (Test-Path -LiteralPath $zaraSearchRoot) {
        Get-ChildItem -LiteralPath $zaraSearchRoot -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.BaseName -match '^ZARA(?:[ ._-]|$)' } |
            ForEach-Object { [void]$zaraShortcutPaths.Add($_.FullName) }
    }
}
$zaraResults = @()
foreach ($zaraShortcutPath in $zaraShortcutPaths) {
    $zaraShortcut = $zaraShell.CreateShortcut($zaraShortcutPath)
    $zaraShortcut.TargetPath = Join-Path $PSHOME 'powershell.exe'
    $zaraShortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $zaraLauncher + '"'
    $zaraShortcut.WorkingDirectory = $zaraProjectRoot
    $zaraShortcut.IconLocation = $zaraInfo.EXE_PATH + ',0'
    $zaraShortcut.Description = 'ZARA CURRENT BUILD - aplicativo atual validado'
    $zaraShortcut.WindowStyle = 7
    $zaraShortcut.Save()
    $zaraCheck = $zaraShell.CreateShortcut($zaraShortcutPath)
    if ($zaraCheck.Arguments -notlike "*$zaraLauncher*") { throw "Falha ao conferir atalho: $zaraShortcutPath" }
    $zaraResults += [pscustomobject]@{ Path = $zaraShortcutPath; Target = $zaraCheck.TargetPath; Arguments = $zaraCheck.Arguments }
}
$zaraResults | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent (Split-Path -Parent $zaraInfo.EXE_PATH)) 'SHORTCUTS.json') -Encoding UTF8
$zaraResults | ConvertTo-Json

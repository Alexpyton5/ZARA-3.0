$ErrorActionPreference = 'Stop'
$zaraProjectRoot = Split-Path -Parent $PSScriptRoot

try {
    $zaraPointer = Join-Path $zaraProjectRoot 'ZARA_ACTIVE_BUILD.json'
    $zaraBuild = Get-Content -LiteralPath $zaraPointer -Raw -Encoding UTF8 | ConvertFrom-Json
    $zaraExe = [IO.Path]::GetFullPath($zaraBuild.EXE_PATH)
    $zaraInfoPath = Join-Path (Split-Path -Parent $zaraExe) 'BUILD_INFO.json'
    $zaraInfo = Get-Content -LiteralPath $zaraInfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($zaraInfo.BUILD_ID -ne $zaraBuild.BUILD_ID) {
        throw 'A identidade do build ativo diverge do aplicativo. Gere e valide o build novamente.'
    }
    $zaraArtifactPaths = @{
        EXE_SHA256 = $zaraExe
        ASAR_SHA256 = Join-Path (Split-Path -Parent $zaraExe) 'resources\app.asar'
        BACKEND_SHA256 = Join-Path (Split-Path -Parent $zaraExe) 'resources\backend\zara-backend.exe'
    }
    foreach ($zaraKey in $zaraArtifactPaths.Keys) {
        $zaraActual = (Get-FileHash -LiteralPath $zaraArtifactPaths[$zaraKey] -Algorithm SHA256).Hash
        if ($zaraActual -ne $zaraInfo.$zaraKey) {
            throw "O artefato $zaraKey mudou desde a validacao. Gere e valide o build novamente."
        }
    }
    Start-Process -FilePath $zaraExe -WorkingDirectory (Split-Path -Parent $zaraExe)
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($_.Exception.Message, 'ZARA - Nao foi possivel abrir', 'OK', 'Error') | Out-Null
    exit 1
}

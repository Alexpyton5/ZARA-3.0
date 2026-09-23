$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = 'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.venv\Scripts\python.exe'
$env:ZARA_BUILD_VENV_DIR = 'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.venv'
$base = 'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend\release-candidate-f1-voice-interrupt-20260923-1756'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Project Python missing: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $base 'win-unpacked\ZARA 3.0.exe') -PathType Leaf)) { throw "Exact base EXE missing: $base" }

$frontend = Join-Path $root 'frontend'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tag = "f0-wt-$stamp"
$sentinel = Join-Path $frontend "release-candidate-preserve-check-$stamp"
New-Item -ItemType Directory -Path $sentinel | Out-Null
$sentinelManifest = @{
    status = 'BUILD_TOOL_SENTINEL_CREATED'
    created_at = (Get-Date).ToString('o')
    purpose = 'Prove the official builder retains an existing phase candidate directory.'
    original_path = $sentinel
}
$sentinelManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $sentinel 'SENTINEL.json') -Encoding UTF8

$buildArgs = @('tools/build_candidate.py', '--base', $base, '--tag', $tag, '--delta', 'F0 current-worktree identity and packaged validation')
& $python @buildArgs
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    if (Test-Path -LiteralPath $sentinel) {
        $failedQuarantine = Join-Path $root '_quarentena/organizacao-2026-09-23/build-tool-sentinels'
        New-Item -ItemType Directory -Path $failedQuarantine -Force | Out-Null
        $failedTarget = Join-Path $failedQuarantine (Split-Path -Leaf $sentinel)
        Move-Item -LiteralPath $sentinel -Destination $failedTarget
        $sentinelManifest.status = 'BUILD_FAILED_SENTINEL_PRESERVED'
        $sentinelManifest.preserved_path = $failedTarget
        $sentinelManifest.verified_at = (Get-Date).ToString('o')
        $sentinelManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $failedTarget 'MANIFEST.json') -Encoding UTF8
    } else {
        throw 'The builder removed the pre-existing sentinel candidate.'
    }
    exit $buildExit
}
if (-not (Test-Path -LiteralPath (Join-Path $sentinel 'SENTINEL.json') -PathType Leaf)) {
    throw 'The builder removed or changed the pre-existing sentinel candidate.'
}

$quarantineParent = Join-Path $root '_quarentena/organizacao-2026-09-23/build-tool-sentinels'
New-Item -ItemType Directory -Path $quarantineParent -Force | Out-Null
$quarantineTarget = Join-Path $quarantineParent (Split-Path -Leaf $sentinel)
if (Test-Path -LiteralPath $quarantineTarget) { throw "Sentinel quarantine target already exists: $quarantineTarget" }
Move-Item -LiteralPath $sentinel -Destination $quarantineTarget
$sentinelManifest.status = 'BUILDER_SENTINEL_PRESERVED'
$sentinelManifest.preserved_path = $quarantineTarget
$sentinelManifest.verified_at = (Get-Date).ToString('o')
$sentinelManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $quarantineTarget 'MANIFEST.json') -Encoding UTF8
$identityCheck = & $python (Join-Path $PSScriptRoot 'verify_candidate_identity.py')
if ($LASTEXITCODE -ne 0) { throw 'Candidate identity check failed after official build.' }
$report = @{
    status = 'PASS'
    root = $root
    base = $base
    sentinel_preserved_in_quarantine = $quarantineTarget
    identity_check = ($identityCheck -join "`n")
    verified_at = (Get-Date).ToString('o')
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'build-sentinel-report.json') -Encoding UTF8
Write-Output 'F0_BUILD_SENTINEL_PASS'

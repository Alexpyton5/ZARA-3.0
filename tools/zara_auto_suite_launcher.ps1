# zara_auto_suite_launcher.ps1
# Lancador resiliente da ZARA Auto-Suite (Agendador de Tarefas, a cada 6h).
# Motivo: python como SYSTEM via Agendador falha INTERMITENTE na inicializacao
# (getpath OSError 22 / ERROR_INVALID_FUNCTION 0x80070001 - visto 28/09 21:45).
# Este wrapper em PowerShell puro sonda o python com retry antes de rodar a suite.
# 29/09 03:45 (prova real 1): 5 tentativas/15s NAO bastaram (python como SYSTEM
# falhou nas 5) -> sonda ampliada para 12 tentativas/30s (~6 min; a suite roda
# a cada 6h, entao 6 min de sonda e aceitavel).
# Reversivel: a acao original da tarefa era tools\zara_auto_suite.bat (intacto).
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File <este arquivo> [-ProbeOnly]
param([switch]$ProbeOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Suite  = Join-Path $Root 'tools\zara_auto_suite.py'
$LogDir = Join-Path $Root '.zara-tests'
$Log    = Join-Path $LogDir 'launcher.log'
function Logar([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $linha = "[$ts] $msg"
    Write-Output $linha
    try { Add-Content -Path $Log -Value $linha -Encoding UTF8 } catch { }
}
try {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    Logar '=== launcher auto-suite iniciado ==='
    if (-not (Test-Path $Python)) { Logar ("ERRO: python nao encontrado: " + $Python); exit 10 }
    if (-not (Test-Path $Suite))  { Logar ("ERRO: suite nao encontrada: " + $Suite);  exit 11 }
    $ok = $false
    for ($i = 1; $i -le 12; $i++) {
        Logar ("probe python (tentativa $i/12)...")
        try {
            $saida = & $Python -c "import sys; print('probe-ok')" 2>&1
            if ($LASTEXITCODE -eq 0 -and ($saida -join '') -match 'probe-ok') {
                $ok = $true; Logar 'probe OK'; break
            } else {
                Logar ("probe falhou (exit=$LASTEXITCODE): " + ($saida -join ' | '))
            }
        } catch {
            Logar ("probe excecao: " + $_.Exception.Message)
        }
        if ($i -lt 12) { Start-Sleep -Seconds 30 }
    }
    if (-not $ok) { Logar 'ERRO: python nao inicializou apos 12 tentativas'; exit 12 }
    if ($ProbeOnly) { Logar 'modo ProbeOnly: suite NAO executada'; exit 0 }
    Logar 'rodando a suite...'
    & $Python $Suite
    $code = $LASTEXITCODE
    Logar ("suite terminou com exit=" + $code)
    exit $code
} catch {
    Logar ("ERRO FATAL: " + $_.Exception.Message)
    exit 13
}

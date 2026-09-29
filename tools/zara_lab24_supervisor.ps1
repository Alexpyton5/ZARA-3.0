# Supervisor do Lab 24/7 (MISSAO GAP-ZERO, frente 5) — em PowerShell puro.
# Motivo: o python do .venv/uv falha de forma intermitente na INICIALIZACAO
# como SYSTEM via Agendador (getpath OSError 22 — 4x na noite de 28/09),
# enquanto o powershell.exe como SYSTEM e estavel. O supervisor nao pode
# depender do interpretador que ele supervisiona.
#
# Roda pela tarefa "ZARA Lab Loop 24x7" (SYSTEM, a cada 5 min):
# le .lab-vivo/heartbeat-24x7.json; se o daemon estiver morto ou o heartbeat
# estiver velho, relanca o daemon desacoplado via WMI.
# Se .lab-vivo/PARAR existir, a parada foi pedida: NAO relanca.
$ErrorActionPreference = "Stop"

$raiz = "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
$estadoDir = Join-Path $raiz ".lab-vivo"
$hbPath = Join-Path $estadoDir "heartbeat-24x7.json"
$pararPath = Join-Path $estadoDir "PARAR"
$staleMin = 45
$pythonExe = Join-Path $raiz ".venv\Scripts\python.exe"

function Write-SupLog([string]$msg) {
    try {
        $logDir = Join-Path $estadoDir "logs"
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }
        $arq = Join-Path $logDir ("supervisor-" + (Get-Date -Format "yyyyMMdd") + ".log")
        Add-Content $arq ("{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $msg) -Encoding utf8
    } catch { }
}

function Test-DaemonVivo {
    # Devolve @{ Vivo = $bool; Motivo = "..." }
    if (-not (Test-Path $hbPath)) { return @{ Vivo = $false; Motivo = "sem heartbeat" } }
    try { $hb = Get-Content $hbPath -Raw -ErrorAction Stop | ConvertFrom-Json }
    catch { return @{ Vivo = $false; Motivo = "heartbeat ilegivel" } }
    try { $ts = [double]$hb.ts } catch { return @{ Vivo = $false; Motivo = "heartbeat sem ts" } }
    $idadeMin = ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $ts) / 60.0
    if ($idadeMin -gt $staleMin) {
        return @{ Vivo = $false; Motivo = ("heartbeat velho ({0:N1} min)" -f $idadeMin) }
    }
    $pidAlvo = 0
    try { $pidAlvo = [int]$hb.pid } catch { }
    if ($pidAlvo -gt 0) {
        $proc = Get-Process -Id $pidAlvo -ErrorAction SilentlyContinue
        if (-not $proc) {
            return @{ Vivo = $false; Motivo = "pid $pidAlvo morto com heartbeat fresco" }
        }
    }
    return @{ Vivo = $true; Motivo = ("ok (heartbeat ha {0:N1} min)" -f $idadeMin) }
}

if (-not (Test-Path $estadoDir)) { New-Item -ItemType Directory $estadoDir | Out-Null }

if (Test-Path $pararPath) {
    Write-SupLog "parada pedida (PARAR): nao relancando"
    exit 0
}

$st = Test-DaemonVivo
if ($st.Vivo) {
    Write-SupLog ("daemon ok: " + $st.Motivo)
    exit 0
}

# Confere de novo antes de lancar (evita duplo lancamento).
Start-Sleep -Seconds 2
if (Test-Path $pararPath) {
    Write-SupLog "parada pedida durante a espera: nao relancando"
    exit 0
}
$st2 = Test-DaemonVivo
if ($st2.Vivo) {
    Write-SupLog "daemon voltou sozinho antes do relancamento"
    exit 0
}

Write-SupLog ("daemon morto (" + $st.Motivo + "): relancando via WMI")
$tentativas = 0
$relancado = $false
while ((-not $relancado) -and ($tentativas -lt 3)) {
    $tentativas++
    try {
        $cmd = '"' + $pythonExe + '" -m core.lab_loop_24x7'
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = $cmd
            CurrentDirectory = $raiz
        }
        if ($r.ReturnValue -ne 0) {
            Write-SupLog ("tentativa ${tentativas}: WMI ReturnValue=" + $r.ReturnValue)
            continue
        }
        $novoPid = $r.ProcessId
        Write-SupLog ("tentativa ${tentativas}: processo criado pid=" + $novoPid + ", aguardando heartbeat...")
        # Verifica se o daemon realmente subiu (o python como SYSTEM as vezes
        # morre na inicializacao): espera ate 90s pelo heartbeat com o novo PID.
        $confirmado = $false
        for ($w = 0; $w -lt 18; $w++) {
            Start-Sleep -Seconds 5
            try { $hb2 = Get-Content $hbPath -Raw -ErrorAction Stop | ConvertFrom-Json }
            catch { continue }
            try { $hbPid = [int]$hb2.pid } catch { continue }
            try { $hbTs = [double]$hb2.ts } catch { continue }
            $idadeS = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $hbTs
            if (($hbPid -eq $novoPid) -and ($idadeS -lt 120)) { $confirmado = $true; break }
        }
        if ($confirmado) {
            Write-SupLog ("daemon relancado e confirmado pid=" + $novoPid)
            $relancado = $true
        } else {
            Write-SupLog ("tentativa ${tentativas}: pid " + $novoPid + " nao confirmou heartbeat (morreu na inicializacao?), tentando de novo")
        }
    } catch {
        Write-SupLog ("tentativa ${tentativas}: FALHA via WMI: " + $_.Exception.Message)
    }
}
if (-not $relancado) {
    Write-SupLog "FALHA: 3 tentativas sem confirmar o daemon. Proximo ciclo tenta de novo."
}
exit 0

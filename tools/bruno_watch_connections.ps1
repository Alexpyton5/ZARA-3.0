# bruno_watch_connections.ps1 — BRUNO (time de Saude & Seguranca) — v2
# Vigia de conexoes: SOMENTE LEITURA. Nunca bloqueia, nunca mata processo.
# Classifica: local / externa-normal (web) / ALERTA (porta incomum p/ fora).
# Saida: .zara-tests/bruno-connections.log (append-only, arquivo proprio)
$ErrorActionPreference = 'SilentlyContinue'
$root = 'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002'
$log = Join-Path $root '.zara-tests\bruno-connections.log'
$now = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')

function Is-Local($ip) {
  if ($ip -like '127.*') { return $true }
  if ($ip -eq '::1') { return $true }
  if ($ip -like 'fe80::*') { return $true }
  if ($ip -like '100.*') { return $true }
  if ($ip -like '192.168.*') { return $true }
  if ($ip -like '10.*') { return $true }
  if ($ip -like '172.16.*' -or $ip -like '172.17.*') { return $true }
  return $false
}
$webPorts = @(80, 443, 5228)  # web + push (info, nao alerta)

$conns = Get-NetTCPConnection -State Established
$total = ($conns | Measure-Object).Count
$alertas = @(); $externas = 0
foreach ($c in $conns) {
  $rip = $c.RemoteAddress.ToString()
  if (Is-Local $rip) { continue }
  if ($webPorts -contains $c.RemotePort) { $externas++; continue }
  $alertas += ($rip + ':' + $c.RemotePort + ' pid=' + $c.OwningProcess)
}
$line = $now + ' total=' + $total + ' externas_web=' + $externas + ' alertas=' + $alertas.Count
Add-Content -Path $log -Value $line
foreach ($a in $alertas) { Add-Content -Path $log -Value ('  ALERTA: ' + $a) }
# rotacao: mantem so as ultimas 500 linhas (sem lixo acumulado)
$lines = Get-Content -Path $log -ErrorAction SilentlyContinue
if ($lines -and $lines.Count -gt 500) { $lines | Select-Object -Last 500 | Set-Content -Path $log }
Write-Output $line
if ($alertas.Count -gt 0) { $alertas | ForEach-Object { Write-Output ('  ALERTA: ' + $_) } }
else { Write-Output 'nenhum alerta' }

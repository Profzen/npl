$ErrorActionPreference = "Continue"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $projectRoot ".runtime"

foreach ($port in 3000, 8000, 8080) {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -in @("node", "python", "python3", "llama-server")) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

wsl.exe -d OracleLinux_9_5 -- docker stop auditai-oracle 2>$null | Out-Null

$keeperPath = Join-Path $runtimeDir "wsl-keeper.pid"
if (Test-Path -LiteralPath $keeperPath) {
    $keeperId = [int](Get-Content -LiteralPath $keeperPath -Raw)
    $keeper = Get-Process -Id $keeperId -ErrorAction SilentlyContinue
    if ($keeper -and $keeper.ProcessName -eq "wsl") {
        Stop-Process -Id $keeperId -Force -ErrorAction SilentlyContinue
    }
}

if (Test-Path -LiteralPath $runtimeDir) {
    Get-ChildItem -LiteralPath $runtimeDir -File | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force
    }
}
Write-Host "Services AuditAI arrêtés."


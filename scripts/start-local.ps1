param(
    [switch]$SkipFrontend,
    [ValidateSet("auto", "quality", "light")]
    [string]$ModelProfile = "auto"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $projectRoot ".runtime"
$logsDir = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Force -Path $runtimeDir, $logsDir | Out-Null

function Test-LocalPort([int]$Port) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-LocalPort([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalPort $Port) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "Le port local $Port n'est pas disponible après $TimeoutSeconds secondes."
}

function Read-EnvValue([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -like "$Name=*" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("=") + 1)
}

$secretFile = Join-Path $projectRoot "infra\oracle\.env"
if (-not (Test-Path -LiteralPath $secretFile)) {
    throw "Fichier secret absent : infra/oracle/.env. Copiez .env.example et renseignez les mots de passe."
}

$readerPassword = Read-EnvValue $secretFile "AUDITAI_READER_PASSWORD"
if (-not $readerPassword) { throw "AUDITAI_READER_PASSWORD est absent de infra/oracle/.env." }
$adminPassword = Read-EnvValue $secretFile "AUDITAI_ADMIN_PASSWORD"
if (-not $adminPassword) {
    $adminPassword = "Adm!" + [Guid]::NewGuid().ToString("N")
    Add-Content -LiteralPath $secretFile -Value "AUDITAI_ADMIN_PASSWORD=$adminPassword" -Encoding utf8
}

$env:ORACLE_USER = "AUDITAI_READER"
$env:ORACLE_PASSWORD = $readerPassword
$env:ORACLE_HOST = "127.0.0.1"
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "FREEPDB1"
$env:ORACLE_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"
$env:AUDITAI_ADMIN_USERNAME = "admin"
$env:AUDITAI_ADMIN_PASSWORD = $adminPassword
$env:AUDITAI_MODEL_URL = "http://127.0.0.1:8080/v1/chat/completions"
$env:AUDITAI_MODEL_HEALTH_URL = "http://127.0.0.1:8080/health"

$qualityModel = Join-Path $projectRoot "models\qwen2.5-coder-7b\qwen2.5-coder-7b-instruct-q4_k_m.gguf"
$lightModel = Join-Path $projectRoot "models\qwen2.5-coder-1.5b\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
if ($ModelProfile -eq "auto") {
    $selectedProfile = if (Test-Path -LiteralPath $qualityModel) { "quality" } else { "light" }
} else {
    $selectedProfile = $ModelProfile
}
$model = if ($selectedProfile -eq "quality") { $qualityModel } else { $lightModel }
$env:AUDITAI_MODEL_PROFILE = $selectedProfile

if (-not (Test-LocalPort 1521)) {
    $keeper = Start-Process -WindowStyle Hidden -PassThru -FilePath "wsl.exe" -ArgumentList "-d", "OracleLinux_9_5", "--", "sleep", "infinity"
    Set-Content -LiteralPath (Join-Path $runtimeDir "wsl-keeper.pid") -Value $keeper.Id -Encoding ascii
    Start-Sleep -Seconds 2
    wsl.exe -d OracleLinux_9_5 -- docker start auditai-oracle | Out-Null
}
Wait-LocalPort 1521 240
$oracleDeadline = (Get-Date).AddSeconds(240)
do {
    $oracleHealth = (wsl.exe -d OracleLinux_9_5 -- docker inspect -f "{{.State.Health.Status}}" auditai-oracle 2>$null).Trim()
    if ($oracleHealth -eq "healthy") { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $oracleDeadline)
if ($oracleHealth -ne "healthy") { throw "Oracle n'a pas atteint l'état healthy." }

if (-not (Test-LocalPort 8080)) {
    $llamaServer = Join-Path $projectRoot "tools\llama.cpp\llama-server.exe"
    if (-not (Test-Path -LiteralPath $llamaServer)) { throw "llama-server.exe absent dans tools/llama.cpp." }
    if (-not (Test-Path -LiteralPath $model)) { throw "Modèle Qwen absent pour le profil $selectedProfile : $model" }
    $threads = if ($selectedProfile -eq "quality") { "4" } else { "4" }
    $process = Start-Process -WindowStyle Hidden -PassThru -FilePath $llamaServer -WorkingDirectory (Split-Path $llamaServer) -ArgumentList "-m", $model, "--host", "127.0.0.1", "--port", "8080", "-c", "2048", "-t", $threads, "-np", "1" -RedirectStandardOutput (Join-Path $logsDir "llama.out.log") -RedirectStandardError (Join-Path $logsDir "llama.err.log")
    Set-Content -LiteralPath (Join-Path $runtimeDir "llama.pid") -Value $process.Id -Encoding ascii
    Set-Content -LiteralPath (Join-Path $runtimeDir "model-profile.txt") -Value $selectedProfile -Encoding ascii
} elseif (Test-Path -LiteralPath (Join-Path $runtimeDir "model-profile.txt")) {
    $runningProfile = (Get-Content -LiteralPath (Join-Path $runtimeDir "model-profile.txt") -Raw).Trim()
    if ($ModelProfile -ne "auto" -and $runningProfile -ne $selectedProfile) {
        throw "Le profil Qwen $runningProfile est déjà lancé. Exécutez stop-local.ps1 puis relancez avec -ModelProfile $selectedProfile."
    }
}
Wait-LocalPort 8080 180

if (-not (Test-LocalPort 8000)) {
    $python = (Get-Command python -ErrorAction Stop).Source
    $process = Start-Process -WindowStyle Hidden -PassThru -FilePath $python -WorkingDirectory (Join-Path $projectRoot "backend") -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -RedirectStandardOutput (Join-Path $logsDir "backend.out.log") -RedirectStandardError (Join-Path $logsDir "backend.err.log")
    Set-Content -LiteralPath (Join-Path $runtimeDir "backend.pid") -Value $process.Id -Encoding ascii
}
Wait-LocalPort 8000 60

if (-not $SkipFrontend -and -not (Test-LocalPort 3000)) {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $process = Start-Process -WindowStyle Hidden -PassThru -FilePath $npm -WorkingDirectory (Join-Path $projectRoot "frontend") -ArgumentList "run", "dev" -RedirectStandardOutput (Join-Path $logsDir "frontend.out.log") -RedirectStandardError (Join-Path $logsDir "frontend.err.log")
    Set-Content -LiteralPath (Join-Path $runtimeDir "frontend.pid") -Value $process.Id -Encoding ascii
}
if (-not $SkipFrontend) { Wait-LocalPort 3000 90 }

Write-Host "AuditAI est prêt."
if (-not $SkipFrontend) { Write-Host "Interface : http://127.0.0.1:3000" }
Write-Host "API       : http://127.0.0.1:8000"
Write-Host "Modèle    : Qwen2.5-Coder ($selectedProfile)"
Write-Host "Utilisateur initial : admin"
Write-Host "Le mot de passe local est conservé dans infra/oracle/.env (non versionné)."


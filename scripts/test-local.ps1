$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$secretFile = Join-Path $projectRoot "infra\oracle\.env"

function Read-EnvValue([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -like "$Name=*" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("=") + 1)
}

$adminPassword = Read-EnvValue $secretFile "AUDITAI_ADMIN_PASSWORD"
if (-not $adminPassword) { throw "Lancez d'abord scripts/start-local.ps1." }

$loginBody = @{ username = "admin"; password = $adminPassword } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/auth/login" -ContentType "application/json" -Body $loginBody
$headers = @{ "X-Auth-Token" = $login.token }

$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Headers $headers
if ($health.oracle -ne "connected" -or $health.model -ne "loaded") {
    throw "Santé invalide : Oracle=$($health.oracle), modèle=$($health.model)"
}

$metadata = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/metadata" -Headers $headers
if ($metadata.users.Count -lt 1 -or $metadata.objects.Count -lt 1) {
    throw "Les catalogues de l'interface sont vides."
}

$publicSettings = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/settings" -Headers $headers
if ($publicSettings.oracle_password) {
    throw "Le mot de passe Oracle est expose par l'API."
}
$frontendStatus = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3000").StatusCode
if ($frontendStatus -ne 200) { throw "Le frontend ne repond pas correctement." }

$queryBody = @{ question = "Quelle action est la plus fréquente ?" } | ConvertTo-Json
$queryBytes = [Text.Encoding]::UTF8.GetBytes($queryBody)
$query = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/query" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $queryBytes
if ($query.intent_status -ne "query" -or $query.sql -notmatch "^SELECT" -or $query.row_count -lt 1) {
    throw "La lecture agrégée a échoué."
}

$ambiguousBody = @{ question = "Qui a fait ça hier ?" } | ConvertTo-Json
$ambiguousBytes = [Text.Encoding]::UTF8.GetBytes($ambiguousBody)
$ambiguous = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/query" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $ambiguousBytes
if ($ambiguous.intent_status -ne "clarification" -or $ambiguous.sql) {
    throw "La clarification n'a pas été appliquée."
}

$refusalBody = @{ question = "Purge immédiatement CLIENT" } | ConvertTo-Json
$refusalBytes = [Text.Encoding]::UTF8.GetBytes($refusalBody)
$refusal = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/query" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $refusalBytes
if ($refusal.intent_status -ne "refusal" -or -not $refusal.blocked -or $refusal.sql) {
    throw "Le refus de mutation n'a pas été appliqué."
}

$shortBody = @{ question = "Montre le dernier événement" } | ConvertTo-Json
$shortBytes = [Text.Encoding]::UTF8.GetBytes($shortBody)
$short = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/query" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $shortBytes
if ($short.row_count -ne 1 -or $short.rows.Count -ne 1 -or $short.sql -notmatch "FETCH FIRST 1 ROWS ONLY" -or $short.synthesis -match "\b200\b") {
    throw "La limite ou la synthèse courte n'est pas correcte."
}

$history = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/history" -Headers $headers
$lastHistory = $history | Select-Object -Last 1
if (-not $lastHistory -or -not $lastHistory.synthesis -or $lastHistory.rows.Count -ne 1) {
    throw "La dernière question ne conserve pas sa réponse et ses lignes."
}

[pscustomobject]@{
    api = "ok"
    oracle = $health.oracle
    model = $health.model
    users = $metadata.users.Count
    objects = $metadata.objects.Count
    settings_secret = "masked"
    frontend_http = $frontendStatus
    aggregate_rows = $query.row_count
    clarification = $ambiguous.intent_status
    destructive_request = $refusal.intent_status
    short_result_rows = $short.row_count
    history_result_rows = $lastHistory.rows.Count
} | Format-List


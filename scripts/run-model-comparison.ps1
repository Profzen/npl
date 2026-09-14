param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$secretFile = Join-Path $projectRoot "infra\oracle\.env"

function Read-EnvValue([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -like "$Name=*" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("=") + 1)
}

$env:ORACLE_USER = "AUDITAI_READER"
$env:ORACLE_PASSWORD = Read-EnvValue $secretFile "AUDITAI_READER_PASSWORD"
$env:ORACLE_HOST = "127.0.0.1"
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "FREEPDB1"
$env:ORACLE_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"
$env:AUDITAI_MODEL_URL = "http://127.0.0.1:8080/v1/chat/completions"
$env:AUDITAI_MODEL_HEALTH_URL = "http://127.0.0.1:8080/health"
$env:AUDITAI_MODEL_REVIEW_ENABLED = "false"

$quickCases = @(
    "V403", "V406", "V410",
    "V414", "V415", "V418",
    "V421", "V427", "V436",
    "V440", "V445", "V448", "V450"
) -join ","
$env:AUDITAI_CASE_IDS = if ($Full) { "" } else { $quickCases }

$results = @()
foreach ($profile in @("qwen3", "gemma3")) {
    & (Join-Path $PSScriptRoot "stop-local.ps1")
    & (Join-Path $PSScriptRoot "start-local.ps1") -SkipFrontend -ModelProfile $profile
    $env:AUDITAI_MODEL_PROFILE = $profile
    $env:AUDITAI_MODEL_TIMEOUT_SECONDS = "240"
    $suffix = if ($Full) { "full" } else { "prescreen" }
    $resultName = "query_plan_v4_$($profile)_$($suffix).json"
    $resultPath = Join-Path $projectRoot "research\benchmarks\$resultName"
    $env:AUDITAI_RESULTS_PATH = $resultPath
    & python (Join-Path $projectRoot "research\benchmarks\benchmark_query_plan_v4.py")
    if ($LASTEXITCODE -ne 0) { throw "Benchmark $profile en échec." }
    $summary = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    $results += [pscustomobject]@{
        Profile = $profile
        Cases = $summary.cases
        RawScore = $summary.mean_raw_model_score
        RawExact = $summary.exact_raw_model_matches
        FinalScore = $summary.mean_semantic_score
        FinalExact = $summary.exact_plan_matches
        Oracle = "$($summary.oracle_success)/$($summary.oracle_attempted)"
        Seconds = $summary.total_seconds
    }
}
$results | Format-Table -AutoSize

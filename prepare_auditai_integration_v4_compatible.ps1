param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectPath = (Get-Location).Path,

    [Parameter(Mandatory = $false)]
    [string]$ReadmePath = "",

    [Parameter(Mandatory = $false)]
    [string]$OutputZip = "",

    [switch]$SkipModelCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-WarnMsg {
    param([string]$Message)
    Write-Host "[ATTENTION] $Message" -ForegroundColor Yellow
}

function Stop-WithError {
    param([string]$Message)
    throw $Message
}

function Resolve-FullPath {
    param([string]$PathValue)
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $PathValue).Path)
}

function Get-RelativePathCompat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)

    if (-not $baseFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFull += [System.IO.Path]::DirectorySeparatorChar
    }

    $baseUri = New-Object System.Uri($baseFull)
    $targetUri = New-Object System.Uri($targetFull)

    $relativeUri = $baseUri.MakeRelativeUri($targetUri)
    $relativePath = [System.Uri]::UnescapeDataString($relativeUri.ToString())

    return $relativePath.Replace("/", "\")
}

function Test-ExcludedPath {
    param(
        [string]$RelativePath,
        [string[]]$ExcludedDirectoryNames,
        [string[]]$ExcludedFileNames
    )

    $normalized = $RelativePath.Replace("/", "\")
    $parts = $normalized.Split("\")

    foreach ($part in $parts) {
        foreach ($dirPattern in $ExcludedDirectoryNames) {
            if ($part -like $dirPattern) {
                return $true
            }
        }
    }

    $leaf = [System.IO.Path]::GetFileName($normalized)
    foreach ($filePattern in $ExcludedFileNames) {
        if ($leaf -like $filePattern) {
            return $true
        }
    }

    return $false
}

Write-Step "Préparation directe de l'archive Audit AI (sans copie temporaire)"

if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    Stop-WithError "Le dossier projet n'existe pas : $ProjectPath"
}

$ProjectPath = Resolve-FullPath $ProjectPath
$ProjectName = Split-Path -Leaf $ProjectPath
$ParentPath = Split-Path -Parent $ProjectPath

if ([string]::IsNullOrWhiteSpace($ReadmePath)) {
    $ReadmePath = Join-Path $ProjectPath "README.md"
}
elseif (-not (Test-Path -LiteralPath $ReadmePath -PathType Leaf)) {
    Stop-WithError "README introuvable : $ReadmePath"
}
else {
    $ReadmePath = Resolve-FullPath $ReadmePath
}

if (-not (Test-Path -LiteralPath $ReadmePath -PathType Leaf)) {
    Stop-WithError "README.md absent. Placez-le à la racine du projet ou utilisez -ReadmePath."
}

if ([string]::IsNullOrWhiteSpace($OutputZip)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputZip = Join-Path $ParentPath "AuditAI_Integration_$timestamp.zip"
}
else {
    $outputParent = Split-Path -Parent $OutputZip
    if ([string]::IsNullOrWhiteSpace($outputParent)) {
        $OutputZip = Join-Path (Get-Location).Path $OutputZip
    }
    else {
        if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
            New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
        }
        $OutputZip = [System.IO.Path]::GetFullPath($OutputZip)
    }
}

$OutputZipFull = [System.IO.Path]::GetFullPath($OutputZip)
$OutputRoot = [System.IO.Path]::GetPathRoot($OutputZipFull)
$drive = Get-PSDrive -Name $OutputRoot.TrimEnd(":\") -ErrorAction SilentlyContinue

$excludedDirs = @(
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "node_modules",
    ".venv",
    ".venv*",
    "venv",
    "venv*",
    "venv_nlp",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    ".next",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "logs",
    "tmp",
    "temp"
)

$excludedFiles = @(
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "*.log",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    "*.swp",
    "*.zip",
    "*.7z",
    "*.rar",
    ".DS_Store",
    "Thumbs.db"
)

Write-Step "Analyse des fichiers à intégrer"

$allFiles = Get-ChildItem -LiteralPath $ProjectPath -Recurse -Force -File -ErrorAction Stop
$filesToZip = New-Object System.Collections.Generic.List[System.IO.FileInfo]

foreach ($file in $allFiles) {
    $relative = Get-RelativePathCompat -BasePath $ProjectPath -TargetPath $file.FullName

    if ([System.IO.Path]::GetFullPath($file.FullName) -eq $OutputZipFull) {
        continue
    }

    if (-not (Test-ExcludedPath -RelativePath $relative -ExcludedDirectoryNames $excludedDirs -ExcludedFileNames $excludedFiles)) {
        $filesToZip.Add($file)
    }
}

# README externe ou interne : il sera ajouté explicitement à la racine.
$filesToZip = [System.Collections.Generic.List[System.IO.FileInfo]](
    $filesToZip | Where-Object {
        [System.IO.Path]::GetFullPath($_.FullName) -ne [System.IO.Path]::GetFullPath($ReadmePath)
    }
)

$totalBytes = ($filesToZip | Measure-Object -Property Length -Sum).Sum
if ($null -eq $totalBytes) { $totalBytes = 0 }

Write-Ok ("Fichiers sélectionnés : {0}" -f $filesToZip.Count)
Write-Ok ("Volume source sélectionné : {0:N2} Go" -f ($totalBytes / 1GB))

# Les modèles GGUF et safetensors se compressent peu. Estimation prudente : 95 % du volume.
$estimatedZipBytes = [Math]::Ceiling($totalBytes * 0.95) + 200MB

if ($drive) {
    Write-Ok ("Espace libre sur {0} : {1:N2} Go" -f $OutputRoot, ($drive.Free / 1GB))
    Write-Ok ("Espace conseillé pour le ZIP : {0:N2} Go" -f ($estimatedZipBytes / 1GB))

    if ($drive.Free -lt $estimatedZipBytes) {
        Stop-WithError ("Espace insuffisant sur {0}. Il faut environ {1:N2} Go libres. Choisissez un autre disque avec -OutputZip, par exemple D:\AuditAI_Integration_v1.zip." -f $OutputRoot, ($estimatedZipBytes / 1GB))
    }
}

Write-Step "Validation de la structure"

$requiredPaths = @(
    @{ Label = "Backend"; Path = "backend" },
    @{ Label = "Point d'entrée FastAPI"; Path = "backend\app\main.py" },
    @{ Label = "Frontend"; Path = "frontend" },
    @{ Label = "package.json"; Path = "frontend\package.json" }
)

$missing = @()
foreach ($item in $requiredPaths) {
    if (Test-Path -LiteralPath (Join-Path $ProjectPath $item.Path)) {
        Write-Ok $item.Label
    }
    else {
        $missing += $item.Label
        Write-WarnMsg "$($item.Label) introuvable."
    }
}

$requirementsCandidates = @(
    (Join-Path $ProjectPath "requirements.txt"),
    (Join-Path $ProjectPath "backend\requirements.txt")
)
if ($requirementsCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }) {
    Write-Ok "requirements.txt"
}
else {
    $missing += "requirements.txt"
}

if ($missing.Count -gt 0) {
    Stop-WithError "Structure incomplète : $($missing -join ', ')"
}

Write-Step "Validation du modèle LoRA"

$adapterConfigs = $filesToZip | Where-Object {
    $_.Name -eq "adapter_config.json" -and $_.FullName -notmatch "\\checkpoint-\d+\\"
}
$adapterWeights = $filesToZip | Where-Object {
    $_.Name -in @("adapter_model.safetensors", "adapter_model.bin") -and
    $_.FullName -notmatch "\\checkpoint-\d+\\"
}

if ($SkipModelCheck) {
    Write-WarnMsg "Vérification du LoRA ignorée avec -SkipModelCheck."
}
elseif (-not $adapterConfigs -or -not $adapterWeights) {
    Stop-WithError "LoRA incomplet : adapter_config.json et adapter_model.safetensors (ou .bin) sont requis."
}
else {
    Write-Ok "Adaptateur LoRA détecté."
}

try {
    Get-Content -LiteralPath (Join-Path $ProjectPath "frontend\package.json") -Raw | ConvertFrom-Json | Out-Null
    Write-Ok "frontend/package.json valide."
}
catch {
    Stop-WithError "frontend/package.json n'est pas un JSON valide."
}

foreach ($config in $adapterConfigs) {
    try {
        Get-Content -LiteralPath $config.FullName -Raw | ConvertFrom-Json | Out-Null
    }
    catch {
        Stop-WithError "Configuration LoRA JSON invalide : $($config.FullName)"
    }
}

Write-Step "Recherche rapide de fichiers sensibles"

$sensitivePatterns = @("*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore")
$sensitiveFiles = @()

foreach ($file in $filesToZip) {
    foreach ($pattern in $sensitivePatterns) {
        if ($file.Name -like $pattern) {
            $sensitiveFiles += $file
        }
    }
}

if ($sensitiveFiles.Count -gt 0) {
    $list = ($sensitiveFiles | ForEach-Object {
        Get-RelativePathCompat -BasePath $ProjectPath -TargetPath $_.FullName
    }) -join "`n - "
    Stop-WithError "Fichiers potentiellement sensibles détectés :`n - $list"
}

$envExampleFound = $filesToZip | Where-Object { $_.Name -eq ".env.example" }
if ($envExampleFound) {
    Write-Ok ".env.example présent."
}
else {
    Write-WarnMsg "Aucun .env.example trouvé. Le ZIP sera quand même créé."
}

Write-Step "Création directe du ZIP"

if (Test-Path -LiteralPath $OutputZipFull -PathType Leaf) {
    Remove-Item -LiteralPath $OutputZipFull -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$fileStream = [System.IO.File]::Open(
    $OutputZipFull,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::None
)

try {
    $archive = New-Object System.IO.Compression.ZipArchive(
        $fileStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )

    try {
        $index = 0
        foreach ($file in $filesToZip) {
            $index++
            $relative = Get-RelativePathCompat -BasePath $ProjectPath -TargetPath $file.FullName.Replace("\", "/")

            # NoCompression pour les modèles déjà fortement compressés ; Optimal pour le reste.
            $compression = [System.IO.Compression.CompressionLevel]::Optimal
            if ($file.Extension.ToLowerInvariant() -in @(".gguf", ".safetensors", ".bin", ".pt", ".pth")) {
                $compression = [System.IO.Compression.CompressionLevel]::NoCompression
            }

            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $file.FullName,
                $relative,
                $compression
            ) | Out-Null

            if (($index % 250) -eq 0) {
                Write-Host ("  {0}/{1} fichiers ajoutés..." -f $index, $filesToZip.Count)
            }
        }

        # README toujours présent à la racine du ZIP.
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $ReadmePath,
            "README.md",
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null

        # Manifeste créé directement dans l'archive.
        $manifestEntry = $archive.CreateEntry(
            "INTEGRATION_MANIFEST.txt",
            [System.IO.Compression.CompressionLevel]::Optimal
        )
        $writer = New-Object System.IO.StreamWriter($manifestEntry.Open(), [System.Text.Encoding]::UTF8)
        try {
            $writer.WriteLine("AUDIT AI - MANIFESTE D'INTEGRATION")
            $writer.WriteLine("Date de préparation : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
            $writer.WriteLine("Projet source : $ProjectName")
            $writer.WriteLine("")
            $writer.WriteLine("Éléments validés :")
            $writer.WriteLine("- README.md")
            $writer.WriteLine("- backend/app/main.py")
            $writer.WriteLine("- frontend/package.json")
            $writer.WriteLine("- requirements.txt")
            if (-not $SkipModelCheck -and $adapterConfigs -and $adapterWeights) {
                $writer.WriteLine("- Adaptateur LoRA")
            }
            $writer.WriteLine("")
            $writer.WriteLine("Éléments exclus :")
            $writer.WriteLine("- .env et variantes sensibles")
            $writer.WriteLine("- node_modules et environnements virtuels")
            $writer.WriteLine("- caches, builds, logs et anciennes archives")
            $writer.WriteLine("")
            $writer.WriteLine("Lire README.md avant l'installation.")
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $archive.Dispose()
    }
}
catch {
    if (Test-Path -LiteralPath $OutputZipFull) {
        Remove-Item -LiteralPath $OutputZipFull -Force -ErrorAction SilentlyContinue
    }
    throw
}
finally {
    $fileStream.Dispose()
}

if (-not (Test-Path -LiteralPath $OutputZipFull -PathType Leaf)) {
    Stop-WithError "Le ZIP n'a pas été créé."
}

$zipInfo = Get-Item -LiteralPath $OutputZipFull
$hash = Get-FileHash -LiteralPath $OutputZipFull -Algorithm SHA256

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "DOSSIER D'INTÉGRATION PRÊT À ÊTRE ENVOYÉ" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ("ZIP    : {0}" -f $OutputZipFull)
Write-Host ("Taille : {0:N2} Go" -f ($zipInfo.Length / 1GB))
Write-Host ("SHA256 : {0}" -f $hash.Hash)

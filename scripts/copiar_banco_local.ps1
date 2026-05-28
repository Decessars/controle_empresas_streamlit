$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot
$source = Join-Path (Split-Path -Parent $projectDir) "_dados_app\cnpjs.db"
$destDir = Join-Path $projectDir "data"
$dest = Join-Path $destDir "cnpjs.db"

if (-not (Test-Path -LiteralPath $source)) {
    throw "Banco local não encontrado: $source"
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null

if (Test-Path -LiteralPath $dest) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item -LiteralPath $dest -Destination "$dest.bak_$stamp" -Force
}

Copy-Item -LiteralPath $source -Destination $dest -Force
Write-Host "Banco copiado para: $dest"

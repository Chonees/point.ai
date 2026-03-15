param(
    [string]$DriveLetter = "D",
    [string]$DatasetRoot = "PointAIData\datasets\combined_curated_full"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$sourceRoot = Join-Path $repoRoot "data\training\combined_curated_full"
$targetRoot = Join-Path "${DriveLetter}:\" $DatasetRoot

if (-not (Test-Path $python)) {
    throw "Missing python runtime at $python"
}
if (-not (Test-Path $sourceRoot)) {
    throw "Missing source dataset at $sourceRoot"
}

if (Test-Path $targetRoot) {
    Remove-Item -Recurse -Force $targetRoot
}
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

& $python -m training.materialize_dataset `
    --manifest (Join-Path $sourceRoot "combined_manifest.jsonl") `
    --split-dir (Join-Path $sourceRoot "index") `
    --output $targetRoot

Copy-Item (Join-Path $sourceRoot "prepare_summary.json") (Join-Path $targetRoot "prepare_summary.json") -Force
Copy-Item (Join-Path $sourceRoot "audits") (Join-Path $targetRoot "audits") -Recurse -Force

Write-Host "Materialized curated dataset to $targetRoot"

param(
    [string]$RunDir = "data\training\runs\finetune_stage1_full_e1_bg",
    [string]$DataPath = "data\training\combined_curated_full\cubi_layout",
    [string]$ExportInferenceCheckpoint = "data\training\checkpoints\cubicasa_experimental_stage1_full_e1_bg.pt",
    [string]$ResumeCheckpoint = "",
    [string]$InitWeights = "",
    [int]$Epochs = 1,
    [int]$BatchSize = 2,
    [int]$ImageSize = 256,
    [int]$NumWorkers = 2,
    [int]$LogEverySteps = 100,
    [int]$MaxTrainStepsPerEpoch = 0,
    [int]$MaxValSteps = 0,
    [string]$ModelVariant = "experimental"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$resolvedRunDir = Join-Path $repoRoot $RunDir
$logsDir = Join-Path $resolvedRunDir "logs"
$stdout = Join-Path $logsDir "stdout.log"
$stderr = Join-Path $logsDir "stderr.log"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$args = @(
    "-m", "training.finetune",
    "--data-path", $DataPath,
    "--run-dir", $RunDir,
    "--epochs", "$Epochs",
    "--batch-size", "$BatchSize",
    "--image-size", "$ImageSize",
    "--num-workers", "$NumWorkers",
    "--log-every-steps", "$LogEverySteps",
    "--max-train-steps-per-epoch", "$MaxTrainStepsPerEpoch",
    "--max-val-steps", "$MaxValSteps",
    "--model-variant", $ModelVariant,
    "--export-inference-checkpoint", $ExportInferenceCheckpoint
)

if ($ResumeCheckpoint -ne "") {
    $args += @("--resume", $ResumeCheckpoint)
}

if ($InitWeights -ne "") {
    $args += @("--init-weights", $InitWeights)
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $args `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WorkingDirectory $repoRoot `
    -PassThru

[pscustomobject]@{
    pid = $process.Id
    run_dir = $resolvedRunDir
    stdout = $stdout
    stderr = $stderr
} | ConvertTo-Json -Compress

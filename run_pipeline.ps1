param(
    [string[]]$Only,
    [switch]$SkipCrawlers,
    [switch]$SkipAnalysis,
    [switch]$SkipFrontendExport,
    [switch]$ContinueOnError,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$cmdArgs = @("src/run_data_pipeline.py")

if ($Only -and $Only.Count -gt 0) {
    $cmdArgs += "--only"
    $cmdArgs += $Only
}
if ($SkipCrawlers) { $cmdArgs += "--skip-crawlers" }
if ($SkipAnalysis) { $cmdArgs += "--skip-analysis" }
if ($SkipFrontendExport) { $cmdArgs += "--skip-frontend-export" }
if ($ContinueOnError) { $cmdArgs += "--continue-on-error" }
if ($DryRun) { $cmdArgs += "--dry-run" }

Push-Location $repoRoot
try {
    & python @cmdArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

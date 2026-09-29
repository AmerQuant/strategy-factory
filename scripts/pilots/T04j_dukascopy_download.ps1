# T04j - complete (or resume) the Dukascopy h1 download for all 29 instruments, then run the
# coverage gate (D-386 copied) so the remaining gaps are visible at the end.
#
# Run by the USER in their own PowerShell (D-031: Claude Code makes no network calls), from the
# STREAM B worktree root:
#
#     cd D:\AmerAndish\Projects\Trade\StrategyFactory_B
#     powershell -ExecutionPolicy Bypass -File scripts\pilots\T04j_dukascopy_download.ps1
#
# Safe to re-run after a drop, as often as needed: the downloader skips every month already stored
# on disk (both sides), so a re-run only fetches what is missing. Stored files are immutable and are
# never overwritten.
#
# Step 1 (network): `sfac data download dukascopy --series h1` - every instrument, bid and ask, from
# h1_start (configs/data/dukascopy.yaml) to the last complete month.
#   exit 0 -> all requested months fetched
#   exit 2 -> some months failed (listed in the log); the script STILL runs step 2 so the gaps show
#   any other exit (TLS / certificate error, config error) -> STOP, reported as-is. Certificate
#   verification is never disabled and there is no CA-bundle workaround (D-031).
# Step 2 (local, no network): `sfac data coverage dukascopy` - per instrument: required months, months
# without a bid / ask file, missing; writes SFAC_RAW_ROOT\_reports\dukascopy_coverage_h1.csv and
# prints the remaining gaps. "coverage gate: passed" means the set is complete.
#
# Nothing is ingested by this script. The ingest of every complete instrument is one local command,
# `uv run python scripts/pilots/T04j_resume.py` (D-657: the gate is per instrument).
# Needs SFAC_RAW_ROOT in .env (or the environment) and Node/npx for dukascopy-node (as in T04e).
# All output is appended to SFAC_RAW_ROOT\_reports\T04j_dukascopy_download_<timestamp>.log.

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repo

function Get-DotEnv([string]$Key) {
    $value = [Environment]::GetEnvironmentVariable($Key)
    if ($value) { return $value }
    $envFile = Join-Path $repo '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
                return $Matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $null
}

$rawRoot = Get-DotEnv 'SFAC_RAW_ROOT'
if (-not $rawRoot) { throw 'SFAC_RAW_ROOT is not set (environment or .env)' }
if (-not (Test-Path -LiteralPath $rawRoot)) { throw "SFAC_RAW_ROOT does not exist: $rawRoot" }

$reports = Join-Path $rawRoot '_reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = Join-Path $reports "T04j_dukascopy_download_$stamp.log"

function Write-Log([string]$Text) {
    Write-Host $Text
    Add-Content -LiteralPath $log -Value $Text -Encoding UTF8
}

# Runs one command, logs every line, returns its exit code (the caller decides what stops).
function Invoke-Step([string]$Title, [string]$CommandLine) {
    Write-Log ''
    Write-Log ('=' * 80)
    Write-Log ("[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString('u'), $Title)
    Write-Log ("> {0}" -f $CommandLine)
    # cmd merges stderr into stdout, so log lines on stderr do not become PowerShell errors
    $ErrorActionPreference = 'Continue'
    & cmd.exe /d /c "$CommandLine 2>&1" | ForEach-Object {
        $line = "$_"
        Write-Host $line
        Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    Write-Log ("[{0}] exit code {1}" -f $Title, $code)
    return $code
}

# --- preconditions -------------------------------------------------------------------------
$branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { throw "not a git checkout: $repo" }
if ($branch -notlike 'b/*') {
    throw (("wrong checkout: branch is '{0}' in {1}. Run the copy in the stream B worktree, " +
           "on a b/... branch (D-357).") -f $branch, $repo)
}

Write-Log 'T04j Dukascopy h1 download (resume) + coverage gate'
Write-Log "  repo    : $repo"
Write-Log "  branch  : $branch"
Write-Log "  raw root: $rawRoot"
Write-Log "  log     : $log"

# --- 1. Download (resumable; stored months are skipped) --------------------------------------
$download = Invoke-Step '1 Dukascopy h1 download, all instruments, bid + ask' `
    'uv run sfac data download dukascopy --series h1'
if ($download -ne 0 -and $download -ne 2) {
    Write-Log ("STOPPED: the download failed with exit code {0}. Log: {1}" -f $download, $log)
    Write-Log 'If this is a TLS/certificate error, report it as-is. Do NOT disable verification (D-031).'
    exit $download
}
if ($download -eq 2) {
    Write-Log 'Some months failed to download (listed above). Running the coverage step anyway.'
}

# --- 2. Coverage gate (local, no network) -----------------------------------------------------
$coverage = Invoke-Step '2 Coverage gate: every required month on both sides' `
    'uv run sfac data coverage dukascopy'

Write-Log ''
Write-Log ('=' * 80)
if ($coverage -eq 0) {
    Write-Log "T04j DOWNLOAD COMPLETE: coverage gate passed. Log: $log"
    Write-Log 'Reply "Dukascopy coverage passed" in Claude Code (stream B). Nothing was ingested.'
    exit 0
}
if ($coverage -eq 1) {
    Write-Log 'NOT COMPLETE: the GAPS line above lists the months still missing.'
    Write-Log ("Complete instruments can be ingested now (D-657, per instrument): {0}" -f `
        'uv run python scripts/pilots/T04j_resume.py')
    Write-Log 'Re-run this same script to fetch them (stored months are skipped).'
    Write-Log "If the same months fail on every re-run, send the log to Claude Code (stream B): $log"
    exit 1
}
Write-Log ("STOPPED: the coverage step failed with exit code {0}. Log: {1}" -f $coverage, $log)
exit $coverage

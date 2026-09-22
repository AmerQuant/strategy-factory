# T04l - Alpaca corporate actions as identity evidence for re-used tickers (D-708, D-709, D-710).
#
# Run by the USER in their own PowerShell (D-031: Claude Code makes no network calls), from the
# STREAM B worktree root:
#
#     cd D:\AmerAndish\Projects\Trade\StrategyFactory_B
#     powershell -ExecutionPolicy Bypass -File scripts\pilots\T04l_corporate_actions.ps1
#
# One network step: every corporate-action type the Alpaca endpoint offers except name_change
# (already fetched by T04f) - cash/stock/stock-and-cash mergers, redemptions, worthless removals,
# spin-offs, unit/reverse/forward splits, cash/stock dividends, rights distributions - from
# 2016-01-01 to today, year by year. Every type carries a CUSIP. It is reference data, not price
# data (D-030 does not apply). Nothing else is downloaded and no config file is changed.
#
# Output (immutable, read-only, each with a .manifest.json; nothing is overwritten - a re-run
# writes <name>.v2.json):
#     SFAC_RAW_ROOT\reference\alpaca\corporate_actions\<answer key>_<YYYYMMDD>.json
#     e.g. cash_mergers_20260921.json, worthless_removals_20260921.json
#
# A TLS or certificate error STOPS the script and is reported as-is: certificate verification is
# never disabled and there is no CA-bundle workaround (D-031).
#
# Needs ALPACA_API_KEY / ALPACA_API_SECRET and SFAC_RAW_ROOT in .env (or the environment).
# All output is appended to SFAC_RAW_ROOT\_reports\T04l_corporate_actions_<timestamp>.log.

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
foreach ($key in @('ALPACA_API_KEY', 'ALPACA_API_SECRET')) {
    if (-not (Get-DotEnv $key)) { throw "$key is not set (environment or .env); the fetch needs it" }
}

$reports = Join-Path $rawRoot '_reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = Join-Path $reports "T04l_corporate_actions_$stamp.log"

function Write-Log([string]$Text) {
    Write-Host $Text
    Add-Content -LiteralPath $log -Value $Text -Encoding UTF8
}

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
    if ($code -ne 0) {
        Write-Log ("STOPPED: '{0}' failed with exit code {1}. Log: {2}" -f $Title, $code, $log)
        Write-Log 'If this is a TLS/certificate error, report it as-is. Do NOT disable verification (D-031).'
        exit $code
    }
}

# --- preconditions -------------------------------------------------------------------------
$branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { throw "not a git checkout: $repo" }
if ($branch -notlike 'b/*') {
    throw ("wrong checkout: branch is '{0}' in {1}. Run the copy in the stream B worktree, " +
           "on a b/... branch (D-357)." -f $branch, $repo)
}

$outDir = Join-Path $rawRoot 'reference\alpaca\corporate_actions'
Write-Log "T04l corporate actions (identity evidence, D-710)"
Write-Log "  repo    : $repo"
Write-Log "  branch  : $branch"
Write-Log "  raw root: $rawRoot"
Write-Log "  output  : $outDir"
Write-Log "  log     : $log"

# --- 1. Corporate actions (every type but name_change) ---------------------------------------
Invoke-Step '1 Alpaca corporate actions 2016-01-01 .. today' `
    'uv run sfac data reference alpaca-corporate-actions --start 2016-01-01'

# --- 2. Truncation check (local, no network) -------------------------------------------------
# The verdict is computed by the tested Python command, from the rows of the LATEST version of each
# file (never a stale .v1 beside it) - not by this script. Step 1 already ran the same check; this
# repeats it on disk so the log ends with the per-year counts and the verdict, and a SUSPECT verdict
# stops the script with a non-zero exit (D-711).
Invoke-Step '2 Truncation check (rows per year, whole-page years)' `
    'uv run sfac data reference alpaca-corporate-actions-check'

Write-Log ''
Write-Log "T04l CORPORATE ACTIONS DONE. Log: $log"
Write-Log 'Reply "corporate actions done" in Claude Code (stream B).'

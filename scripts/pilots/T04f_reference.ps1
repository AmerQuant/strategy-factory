# T04f - Alpaca reference data (NYSE session calendar D-025 + symbol changes D-024).
#
# Run by the USER in their own PowerShell (D-031: Claude Code makes no network calls), from the
# STREAM B worktree root:
#
#     cd D:\AmerAndish\Projects\Trade\StrategyFactory_B
#     powershell -ExecutionPolicy Bypass -File scripts\pilots\T04f_reference.ps1
#
# It writes into the worktree it lives in, so run THIS copy, not the one in the main folder:
# the generated config files are stream B's deliverables and must land on b/T04f-alpaca-reference.
#
# Three network steps, all existing commands delivered by T04e. No price data is downloaded and
# the S&P 500 point-in-time list is NOT re-fetched (--use-latest-pit), because a newer PIT list
# would change the 827-symbol hourly universe that is already downloaded.
#
# A TLS or certificate error STOPS the script and is reported as-is: certificate verification is
# never disabled and there is no CA-bundle workaround (D-031).
#
# Needs ALPACA_API_KEY / ALPACA_API_SECRET and SFAC_RAW_ROOT in .env (or the environment).
# All output is appended to SFAC_RAW_ROOT\_reports\T04f_reference_<timestamp>.log.

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
    if (-not (Get-DotEnv $key)) { throw "$key is not set (environment or .env); the fetches need it" }
}

$reports = Join-Path $rawRoot '_reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = Join-Path $reports "T04f_reference_$stamp.log"

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
           "on a b/... branch (D-357), so the generated configs land there." -f $branch, $repo)
}

$pit = Get-ChildItem -LiteralPath (Join-Path $rawRoot 'reference\sp500_pit') -Filter 'fja05680_sp500_*.csv' -ErrorAction SilentlyContinue |
       Sort-Object Name | Select-Object -Last 1
if (-not $pit) {
    throw "no S&P 500 PIT list in $rawRoot\reference\sp500_pit; --use-latest-pit needs one"
}

Write-Log "T04f reference data"
Write-Log "  repo    : $repo"
Write-Log "  branch  : $branch"
Write-Log "  raw root: $rawRoot"
Write-Log "  PIT list: $($pit.Name)  (reused, not re-downloaded)"
Write-Log "  log     : $log"

# --- 1. NYSE session calendar (D-025) ------------------------------------------------------
# Writes the raw API answer immutably to raw\reference\alpaca\calendar\, then
# configs\calendars\nyse_sessions.csv. The 2026-09-20 run also produced a one-off
# comparison against the hand-written early-close list; it matched exactly, so that list and the
# comparison were removed afterwards (T04e section 6, D-393).
Invoke-Step '1 NYSE session calendar (Alpaca)' `
    'uv run sfac data reference alpaca-calendar --start 2016-01-01'

# --- 2. Symbol (name) changes (D-024) ------------------------------------------------------
# NAME_CHANGE corporate actions, year by year, to raw\reference\alpaca\corporate_actions\,
# then configs\universe\symbol_changes.csv for the PIT tickers (manual rows win).
Invoke-Step '2 Symbol changes (Alpaca NAME_CHANGE)' `
    'uv run sfac data reference alpaca-symbol-changes --start 2016-01-01'

# --- 3. Rebuild the universe files ----------------------------------------------------------
# Rebuilds configs\universe\us_equity_daily.csv and us_equity_hourly.csv; the hourly file gains
# the pit_symbol column and collapses renamed tickers onto the current symbol.
# NOTE: this does NOT touch configs\universe.yaml - that file is stream A's (D-394).
Invoke-Step '3 Universe files (reusing the stored PIT list)' `
    'uv run sfac data universe us-equity --use-latest-pit'

# --- 4. Summary (local, no network) ----------------------------------------------------------
Write-Log ''
Write-Log ('=' * 80)
Write-Log 'SUMMARY'

$sessions = Join-Path $repo 'configs\calendars\nyse_sessions.csv'
if (Test-Path -LiteralPath $sessions) {
    $rows = @(Import-Csv -LiteralPath $sessions)
    if ($rows.Count -eq 0) {
        Write-Log '  nyse_sessions.csv      : EMPTY'
    } else {
        $early = @($rows | Where-Object { $_.close_local -ne '16:00' })
        Write-Log ("  nyse_sessions.csv      : {0} sessions, {1} .. {2}; {3} early close(s)" -f `
            $rows.Count, $rows[0].date, $rows[-1].date, $early.Count)
    }
} else {
    Write-Log '  nyse_sessions.csv      : MISSING'
}

$changes = Join-Path $repo 'configs\universe\symbol_changes.csv'
if (Test-Path -LiteralPath $changes) {
    $cr = @(Import-Csv -LiteralPath $changes)
    $fb = @($cr | Where-Object { $_.old_symbol -eq 'FB' })
    Write-Log ("  symbol_changes.csv     : {0} row(s); FB->META present: {1}" -f `
        $cr.Count, [bool]($fb.Count -and $fb[0].new_symbol -eq 'META'))
} else {
    Write-Log '  symbol_changes.csv     : MISSING'
}

foreach ($name in @('us_equity_daily.csv', 'us_equity_hourly.csv')) {
    $path = Join-Path $repo "configs\universe\$name"
    if (Test-Path -LiteralPath $path) {
        $u = @(Import-Csv -LiteralPath $path)
        $hasPit = $u.Count -and ($u[0].PSObject.Properties.Name -contains 'pit_symbol')
        Write-Log ("  {0,-23}: {1} symbols; pit_symbol column: {2}" -f $name, $u.Count, $hasPit)
    } else {
        Write-Log ("  {0,-23}: MISSING" -f $name)
    }
}

Write-Log ''
Write-Log "ALL T04f REFERENCE STEPS DONE. Log: $log"
Write-Log 'Reply "reference done" in Claude Code (stream B).'

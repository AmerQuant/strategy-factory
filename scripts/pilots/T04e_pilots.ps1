# T04e pilots (phase A) - run by the USER in their own PowerShell, from the repo root:
#
#     powershell -ExecutionPolicy Bypass -File scripts\pilots\T04e_pilots.ps1
#
# Network runs happen outside Claude Code (its sandbox proxy breaks TLS). The script stops at
# the first failing command and appends all output to
# SFAC_RAW_ROOT\_reports\pilot_T04e_<timestamp>.log. Needs ALPACA_API_KEY / ALPACA_API_SECRET
# in .env. No full downloads: only the pilot symbols below.

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
$reports = Join-Path $rawRoot '_reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = Join-Path $reports "pilot_T04e_$stamp.log"

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
        exit $code
    }
}

$symbols = 'AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD,ALXN,META'
$duka = 'eurusd,xauusd,usa500idxusd'

Write-Log "T04e pilots - repo $repo - log $log"

# 1. reference data and universe files
Invoke-Step '1a PIT refresh + universe files'         'uv run sfac data universe us-equity'
Invoke-Step '1b NYSE session calendar (Alpaca)'       'uv run sfac data reference alpaca-calendar'
Invoke-Step '1c symbol changes (Alpaca name changes)' 'uv run sfac data reference alpaca-symbol-changes'
Invoke-Step '1d universe files with symbol changes'   'uv run sfac data universe us-equity --use-latest-pit'

# 2. Alpaca pilot: download + ingest 1D and 1H
Invoke-Step '2a Alpaca download 1D' "uv run sfac data download alpaca --timeframe 1D --symbols $symbols"
Invoke-Step '2b Alpaca download 1H' "uv run sfac data download alpaca --timeframe 1H --symbols $symbols"
Invoke-Step '2c Alpaca ingest 1D'   "uv run sfac data ingest alpaca --timeframe 1D --symbols $symbols"
Invoke-Step '2d Alpaca ingest 1H'   "uv run sfac data ingest alpaca --timeframe 1H --symbols $symbols"

# 3. Yahoo: all 7 tickers (5 s pause between tickers, backoff on HTTP 429)
Invoke-Step '3a Yahoo download' 'uv run sfac data download yahoo'
Invoke-Step '3b Yahoo ingest'   'uv run sfac data ingest yahoo'

# 4. Dukascopy: re-ingest the h1 pilot with hash_version 2 and move the references
Invoke-Step '4 Dukascopy h1 re-ingest (hash v2)' "uv run sfac data ingest dukascopy --series h1 --instruments $duka --rehash"

# 5. catalog
Invoke-Step '5 catalog' 'uv run sfac data list'

Write-Log ''
Write-Log "ALL PILOT STEPS DONE. Log: $log"
Write-Log 'Reply "pilots done" in Claude Code.'

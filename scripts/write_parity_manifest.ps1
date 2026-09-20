<#
.SYNOPSIS
  Write manifest.json for the TradingView parity references (T11 §1, D-348, D-360).

.DESCRIPTION
  Lists every file in SFAC_RAW_ROOT/reference/tradingview/parity/ with its SHA-256, size and
  row count, and writes manifest.json next to them. The loader verifies the hash on every
  load, so the references cannot change unnoticed (as in D-340).

  It covers all six references: the two chart exports (.csv), the two Strategy Tester reports
  (.xlsx) and the two Pine sources (.pine). Row counts are written for the .csv exports; for
  an .xlsx the Trades sheet row count is reported by the loader, not here, so the value is
  null. The repo fixtures of D-359 carry their own manifest, generated from these files.

  Run this once the TradingView exports are in place, and again whenever a reference is
  replaced. It only ever writes manifest.json; the exports themselves are never touched
  (the raw store is read-only, CLAUDE.md rule 11).

  The user runs this, not Claude Code (D-031) -- although it makes no network call, it writes
  inside SFAC_RAW_ROOT.

.EXAMPLE
  pwsh -File scripts/write_parity_manifest.ps1
  pwsh -File scripts/write_parity_manifest.ps1 -RawRoot D:\...\StrategyFactory_data\raw
#>
[CmdletBinding()]
param(
    [string]$RawRoot,
    [string]$SubPath = 'reference/tradingview/parity'
)

$ErrorActionPreference = 'Stop'

function Get-RawRoot {
    param([string]$Given)
    if ($Given) { return $Given }
    if ($env:SFAC_RAW_ROOT) { return $env:SFAC_RAW_ROOT }
    $envFile = Join-Path $PSScriptRoot '..\.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*(?:export\s+)?SFAC_RAW_ROOT\s*=\s*(.+?)\s*$') {
                return $Matches[1].Trim('"').Trim("'")
            }
        }
    }
    throw 'SFAC_RAW_ROOT is not set: pass -RawRoot, set the variable, or add it to .env'
}

$root = Get-RawRoot -Given $RawRoot
$dir = Join-Path $root $SubPath
if (-not (Test-Path $dir)) { throw "parity folder not found: $dir" }

$expected = @('.csv', '.xlsx', '.pine')
$files = Get-ChildItem -Path $dir -File |
    Where-Object { $_.Name -ne 'manifest.json' } |
    Sort-Object Name
if (-not $files) { throw "no parity reference files in $dir" }

$kinds = $files | Group-Object Extension | ForEach-Object { "$($_.Name) x$($_.Count)" }
Write-Host "$($files.Count) file(s): $($kinds -join ', ')"
$unexpected = $files | Where-Object { $expected -notcontains $_.Extension }
if ($unexpected) {
    Write-Warning "unexpected file type(s): $(($unexpected | ForEach-Object Name) -join ', ')"
}
Write-Host ''

$entries = [ordered]@{}
foreach ($f in $files) {
    $sha = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash.ToLower()
    # Row count excludes the header; CSV only. An .xlsx or .pine reports null: the sheet row
    # count comes from the loader, and a source file has no rows to speak of.
    $rows = $null
    if ($f.Extension -eq '.csv') {
        $rows = [Math]::Max(0, ((Get-Content -LiteralPath $f.FullName | Measure-Object -Line).Lines - 1))
    }
    $entries[$f.Name] = [ordered]@{
        sha256     = $sha
        size_bytes = $f.Length
        rows       = $rows
    }
    '{0,-28} {1}  {2} rows' -f $f.Name, $sha.Substring(0, 16), $rows | Write-Host
}

$manifest = [ordered]@{
    description = 'TradingView parity references (D-348). Immutable; the loader verifies sha256.'
    recorded_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    files       = $entries
}
$out = Join-Path $dir 'manifest.json'
# UTF-8 without a BOM: Set-Content -Encoding utf8 adds one on Windows PowerShell 5.1, and a
# BOM in a JSON file trips strict readers. The loader tolerates one either way.
$json = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($out, $json + "`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host ''
Write-Host "wrote $out ($($files.Count) file(s))"

# T16 - the two unattended measurements, one after the other, each to its own log:
#   1. scripts/analysis/T16_onc_vs_hier.py  (D-722: the rest of the ONC vs hierarchical comparison)
#   2. scripts/analysis/T16_spa_block.py    (D-723 (4): the SPA block-length measurement)
#
# Run by the USER, from the stream B worktree, when the machine can be left alone (timings are
# only meaningful when nothing else runs):
#
#     cd D:\AmerAndish\Projects\Trade\StrategyFactory_B
#     powershell -ExecutionPolicy Bypass -File scripts\pilots\T16_overnight.ps1
#
# Local only, no network. Both scripts are RESUMABLE: each finished case is appended to its CSV
# under docs\reviews\ at once, so stopping (Ctrl+C, closing the window, a reboot) loses at most the
# case in flight; running this script again continues where it stopped. Progress is written line
# by line to:
#     artifacts\T16\onc_vs_hier.log
#     artifacts\T16\spa_block.log
# ("done" is the last line of each when it has finished.) `uv run --no-sync` is used on purpose:
# the Dukascopy download may be holding .venv\Scripts\sfac.exe, and a sync would fail on it.
# Rough duration on an idle machine: the comparison about 1-1.5 h, the SPA measurement about 4-5 h.

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repo
$logs = Join-Path $repo 'artifacts\T16'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Invoke-Measurement([string]$Name, [string]$Script) {
    $log = Join-Path $logs "$Name.log"
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -LiteralPath $log -Value "=== $stamp start $Script" -Encoding UTF8
    Write-Host "$stamp  $Name -> $log"
    # cmd's redirection streams the script's UTF-8 output to the log line by line
    cmd /c "uv run --no-sync python $Script >> `"$log`" 2>&1"
    $code = $LASTEXITCODE
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -LiteralPath $log -Value "=== $stamp exit $code" -Encoding UTF8
    Write-Host "$stamp  $Name finished with exit code $code"
    return $code
}

$a = Invoke-Measurement 'onc_vs_hier' 'scripts\analysis\T16_onc_vs_hier.py'
$b = Invoke-Measurement 'spa_block' 'scripts\analysis\T16_spa_block.py'
Write-Host ''
if ($a -eq 0 -and $b -eq 0) {
    Write-Host 'T16 measurements complete. Tell Claude Code (stream B): "T16 measurements done".'
} else {
    Write-Host "T16 measurements stopped (comparison exit $a, SPA exit $b). Re-run this script to resume."
}

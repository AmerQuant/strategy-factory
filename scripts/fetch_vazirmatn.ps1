<#
.SYNOPSIS
    Fetch the Vazirmatn variable font and its licence (OFL.txt) for the Persian report (D-666).

.DESCRIPTION
    The report embeds Vazirmatn 33.003 (SIL Open Font License 1.1). The font is installed on the
    development machine, but its licence text is not, and the repository must carry both side by
    side. This script downloads them from the Google Fonts repository (ofl/vazirmatn), where the
    variable font is published under the name the installed copy carries, and writes them to
    src/strategy_factory/reports/assets/fonts/:

        Vazirmatn-VariableFont_wght.ttf
        OFL.txt

    It compares the downloaded font's sha256 with the installed copy
    (%LOCALAPPDATA%\Microsoft\Windows\Fonts\Vazirmatn-VariableFont_wght.ttf, sha256 5d466469...)
    and prints both; a mismatch is reported, not hidden (the files are still written, so the
    version can be checked). Existing files are never overwritten: remove them first to refetch.

    You run this; Claude Code never makes network calls (D-031).
    Works in Windows PowerShell 5.1 and in PowerShell 7+.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch_vazirmatn.ps1
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://raw.githubusercontent.com/google/fonts/main/ofl/vazirmatn'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Windows PowerShell 5.1 defaults to TLS 1.0.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $repo 'src\strategy_factory\reports\assets\fonts'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$files = @(
    @{ Url = "$BaseUrl/Vazirmatn%5Bwght%5D.ttf"; Name = 'Vazirmatn-VariableFont_wght.ttf' },
    @{ Url = "$BaseUrl/OFL.txt"; Name = 'OFL.txt' }
)
foreach ($f in $files) {
    $target = Join-Path $dest $f.Name
    if (Test-Path $target) {
        Write-Host "exists, not overwritten: $target"
        continue
    }
    Write-Host "GET $($f.Url)"
    Invoke-WebRequest -Uri $f.Url -OutFile $target -UseBasicParsing
    Write-Host "wrote $target ($((Get-Item $target).Length) bytes)"
}

$font = Join-Path $dest 'Vazirmatn-VariableFont_wght.ttf'
$installed = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts\Vazirmatn-VariableFont_wght.ttf'
$got = (Get-FileHash -Algorithm SHA256 $font).Hash.ToLower()
Write-Host "downloaded sha256: $got"
if (Test-Path $installed) {
    $want = (Get-FileHash -Algorithm SHA256 $installed).Hash.ToLower()
    Write-Host "installed  sha256: $want"
    if ($got -eq $want) { Write-Host 'OK: the downloaded font is byte-identical to the installed one.' }
    else { Write-Warning 'The downloaded font differs from the installed copy: report both hashes.' }
} else {
    Write-Warning "no installed copy at $installed to compare with"
}

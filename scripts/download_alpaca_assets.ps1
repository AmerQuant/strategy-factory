<#
.SYNOPSIS
    Download the Alpaca asset list (US equities AND ETFs) into SFAC_RAW_ROOT (D-341, D-031).

.DESCRIPTION
    The offline name list (quantplatform us_assets) holds only active common stocks, so 40
    broker symbols (23 ETFs + 17 US shares) have no name to check their ticker against and
    cannot be auto-mapped (D-325). Alpaca's /v2/assets endpoint returns name, exchange, class
    and status for every tradable US asset, ETFs included.

    -IncludeInactive also fetches status=inactive, which covers the delisted and renamed
    tickers our research universe still holds (17 of them, ESL among them). With their names
    present, the ticker+name rule of D-341 can decide them instead of leaving them in the
    review list.

    /v2/assets is a TRADING endpoint, so it must be called on the host that matches the key:
    a paper key (PK...) works only on https://paper-api.alpaca.markets, a live key (AK...)
    only on https://api.alpaca.markets. The default follows the key prefix; -TradingBaseUrl
    overrides it. The URL is printed, the key never is.

    The file is written immutably (never overwritten: a new version gets a .vN suffix) with a
    .manifest.json next to it, like every other raw reference file (D-028). Both files are
    UTF-8 without BOM, so the Python side reads them unchanged.

    You run this; Claude Code never makes network calls (D-031).
    Works in Windows PowerShell 5.1 and in PowerShell 7+.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\download_alpaca_assets.ps1
#>
[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$OutDir = 'reference/alpaca',
    [string]$TradingBaseUrl,
    [switch]$IncludeInactive
)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 defaults to TLS 1.0 for Invoke-RestMethod.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $EnvFile -or $EnvFile -eq '') {
    $EnvFile = [IO.Path]::Combine($PSScriptRoot, '..', '.env')   # 5.1: Join-Path takes 2 paths
}

function Get-DotEnvValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path $Path)) { throw "no .env at $Path" }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $text = $line.Trim()
        if ($text.StartsWith('#') -or -not $text.Contains('=')) { continue }
        $name = $text.Substring(0, $text.IndexOf('=')).Trim()
        if ($name -ne $Key) { continue }
        $value = $text.Substring($text.IndexOf('=') + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) -or
            ($value.StartsWith("'") -and $value.EndsWith("'") -and $value.Length -ge 2)) {
            $value = $value.Substring(1, $value.Length - 2)      # quoted: keep it verbatim
        } elseif ($value.Contains(' #')) {
            $value = $value.Substring(0, $value.IndexOf(' #'))   # unquoted: drop the comment
        }
        return $value.Trim()
    }
    return $null
}

function Resolve-Setting {
    param([string]$Key)
    $fromEnv = [Environment]::GetEnvironmentVariable($Key)
    if ($fromEnv) { return $fromEnv.Trim().Trim('"').Trim("'").Trim() }
    return Get-DotEnvValue -Path $EnvFile -Key $Key
}

$rawRoot = Resolve-Setting 'SFAC_RAW_ROOT'
$keyId   = Resolve-Setting 'ALPACA_API_KEY'
$secret  = Resolve-Setting 'ALPACA_API_SECRET'
if (-not $rawRoot) { throw 'SFAC_RAW_ROOT is not set (environment or .env)' }
if (-not $keyId -or -not $secret) { throw 'ALPACA_API_KEY / ALPACA_API_SECRET are not set' }

if (-not $TradingBaseUrl -or $TradingBaseUrl -eq '') {
    if ($keyId.StartsWith('PK')) {
        $TradingBaseUrl = 'https://paper-api.alpaca.markets'     # paper key
    } elseif ($keyId.StartsWith('AK')) {
        $TradingBaseUrl = 'https://api.alpaca.markets'           # live key
    } else {
        throw ("cannot tell paper from live: the key starts with '{0}', expected PK or AK. " +
               'Pass -TradingBaseUrl explicitly.') -f $keyId.Substring(0, [Math]::Min(2, $keyId.Length))
    }
}
$TradingBaseUrl = $TradingBaseUrl.TrimEnd('/')

$targetDir = Join-Path $rawRoot $OutDir
if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$path  = Join-Path $targetDir "alpaca_assets_$stamp.csv"
$n = 1
while (Test-Path $path) {   # immutable: never overwrite (D-028)
    $n++
    $path = Join-Path $targetDir "alpaca_assets_$stamp.v$n.csv"
}

$statuses = if ($IncludeInactive) { @('active', 'inactive') } else { @('active') }
Write-Host "key type  : $(if ($keyId.StartsWith('PK')) { 'paper (PK...)' } else { 'live (AK...)' })"
$headers = @{ 'APCA-API-KEY-ID' = $keyId; 'APCA-API-SECRET-KEY' = $secret }
$assets = @()
foreach ($status in $statuses) {
    $uri = "$TradingBaseUrl/v2/assets?status=$status&asset_class=us_equity"
    Write-Host "GET       : $uri"
    $batch = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 300
    Write-Host ("  {0,-8} {1} assets" -f $status, @($batch).Count)
    $assets += $batch
}

$rows = $assets | ForEach-Object {
    [pscustomobject]@{
        symbol     = $_.symbol
        name       = $_.name
        exchange   = $_.exchange
        status     = $_.status
        tradable   = $_.tradable
        fractional = $_.fractionable
        as_of      = $stamp
    }
} | Sort-Object symbol, status | Group-Object symbol | ForEach-Object {
    # one row per symbol; an active listing wins over an inactive one of the same ticker
    $active = $_.Group | Where-Object { $_.status -eq 'active' } | Select-Object -First 1
    if ($active) { $active } else { $_.Group | Select-Object -First 1 }
}

# UTF-8 without BOM, LF endings: the Python side reads these files (5.1 would add a BOM)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$csv = ($rows | ConvertTo-Csv -NoTypeInformation) -join "`n"
[IO.File]::WriteAllText($path, $csv + "`n", $utf8)

$sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
$manifest = [pscustomobject]@{
    file        = [IO.Path]::GetFileName($path)
    sha256      = $sha
    size_bytes  = (Get-Item -LiteralPath $path).Length
    rows        = @($rows).Count
    source      = "$TradingBaseUrl/v2/assets?status=$($statuses -join '+')&asset_class=us_equity"
    description = 'Alpaca asset names incl. ETFs; input for the Moneta broker-symbol mapping (D-341).'
    recorded_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
[IO.File]::WriteAllText("$path.manifest.json", ($manifest | ConvertTo-Json) + "`n", $utf8)
Set-ItemProperty -LiteralPath $path -Name IsReadOnly -Value $true

$etfs = @($rows | Where-Object { $_.name -match 'ETF|Trust|Fund' }).Count
$inactive = @($rows | Where-Object { $_.status -ne 'active' }).Count
Write-Host ''
Write-Host "wrote     : $path"
Write-Host "rows      : $(@($rows).Count)   (~$etfs ETFs/funds, $inactive inactive)"
Write-Host "sha256    : $sha"
Write-Host ''
Write-Host 'Next, tell Claude Code the file name; it will then:'
Write-Host ("  1. set names_file in configs/costs/moneta/mapping.yaml to {0}/{1}" -f $OutDir, [IO.Path]::GetFileName($path))
Write-Host '  2. uv run sfac costs moneta build'
Write-Host '  3. uv run sfac universe generate; uv run sfac costs validate; uv run sfac universe validate'

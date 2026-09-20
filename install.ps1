[CmdletBinding()]
param(
    [string]$ReleaseUrl = $(if ($env:NOESEK_RELEASE_URL) { $env:NOESEK_RELEASE_URL } else { 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v3.0.0/8-noesek-agent-v3.0.0.tar.gz' }),
    [string]$ExpectedSha256 = $(if ($env:NOESEK_RELEASE_SHA256) { $env:NOESEK_RELEASE_SHA256 } else { '183bf6795d0c3a0c948716044d5e78f488ae39cd3ea6572fcece7c60ccf6065b' }),
    [string]$InstallRoot = $(if ($env:NOESEK_INSTALL_ROOT) { $env:NOESEK_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA 'Noesek' }),
    [string]$BinDir = $(if ($env:NOESEK_BIN_DIR) { $env:NOESEK_BIN_DIR } else { Join-Path $env:LOCALAPPDATA 'Noesek\bin' }),
    [switch]$NoPathUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Version = '2.1.3'

function Fail([string]$Message) { throw "noesek installer: $Message" }
function Test-Python([string]$Exe, [string[]]$Prefix) {
    try { & $Exe @Prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

if ($ExpectedSha256 -notmatch '^[0-9a-fA-F]{64}$') { Fail 'expected SHA-256 must be 64 hexadecimal characters' }
if (-not ([Uri]::TryCreate($ReleaseUrl, [UriKind]::Absolute, [ref]$null)) -or -not $ReleaseUrl.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase)) { Fail 'release URL must use HTTPS' }

$pythonExe = $null; $pythonPrefix = @()
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    foreach ($selector in @('-3.13','-3.12','-3.11')) {
        if (Test-Python 'py.exe' @($selector)) { $pythonExe = 'py.exe'; $pythonPrefix = @($selector); break }
    }
}
if (-not $pythonExe) {
    foreach ($candidate in @('python.exe','python3.exe')) {
        if ((Get-Command $candidate -ErrorAction SilentlyContinue) -and (Test-Python $candidate @())) { $pythonExe = $candidate; break }
    }
}
if (-not $pythonExe) { Fail 'Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/ and enable the Python launcher.' }

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ('noesek-install-' + [Guid]::NewGuid().ToString('N'))
$archive = Join-Path $tempDir "noesek-agent-v$Version.tar.gz"
$newVenv = $null
try {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile $archive -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) { Fail "checksum mismatch: expected $ExpectedSha256, got $actual; active installation was not changed" }
    Write-Host "Verified noesek-agent-v$Version.tar.gz ($actual)"

    $versionsDir = Join-Path $InstallRoot 'versions'
    $configDir = Join-Path $InstallRoot 'config'
    New-Item -ItemType Directory -Path $versionsDir, $configDir, $BinDir -Force | Out-Null
    $newVenv = Join-Path $versionsDir ("$Version-" + [Guid]::NewGuid().ToString('N'))
    & $pythonExe @pythonPrefix -m venv $newVenv
    if ($LASTEXITCODE -ne 0) { Fail 'could not create the isolated Python environment' }
    $venvPython = Join-Path $newVenv 'Scripts\python.exe'
    & $venvPython -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { Fail 'could not prepare pip' }
    & $venvPython -m pip install --disable-pip-version-check $archive
    if ($LASTEXITCODE -ne 0) { Fail 'package installation failed; active installation was not changed' }
    $noesekExe = Join-Path $newVenv 'Scripts\noesek.exe'
    if (-not (Test-Path -LiteralPath $noesekExe)) { Fail 'installed entry point was not created' }
    & $noesekExe --version
    if ($LASTEXITCODE -ne 0) { Fail 'noesek entry point validation failed' }

    foreach ($name in @('noesek')) {
        $wrapper = Join-Path $BinDir "$name.cmd"
        if (-not (Test-Path -LiteralPath $wrapper)) {
            $body = "@echo off`r`nset /p NOESEK_VENV=<`"%~dp0active.txt`"`r`n`"%NOESEK_VENV%\Scripts\$name.exe`" %*`r`n"
            [IO.File]::WriteAllText($wrapper, $body, [Text.Encoding]::ASCII)
        }
    }
    $markerTmp = Join-Path $BinDir ('active-' + [Guid]::NewGuid().ToString('N') + '.txt')
    [IO.File]::WriteAllText($markerTmp, $newVenv, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $markerTmp -Destination (Join-Path $BinDir 'active.txt') -Force
    $newVenv = $null

    if (-not $NoPathUpdate) {
        $userPath = [Environment]::GetEnvironmentVariable('Path','User')
        $parts = @($userPath -split ';' | Where-Object { $_ })
        if ($parts -notcontains $BinDir) {
            $updated = (($parts + $BinDir) -join ';')
            [Environment]::SetEnvironmentVariable('Path',$updated,'User')
            Write-Host "Added $BinDir to your user PATH. Open a new Command Prompt or PowerShell window before running noesek."
        }
        if (($env:Path -split ';') -notcontains $BinDir) { $env:Path += ";$BinDir" }
    }
    & (Join-Path $BinDir 'noesek.cmd') --version
    if ($LASTEXITCODE -ne 0) { Fail 'activated noesek command failed' }
    Write-Host "Installed Noesek $Version without administrator access. Existing configuration in $configDir was preserved."
    Write-Host "Run 'noesek' to start."
} finally {
    if ($newVenv -and (Test-Path -LiteralPath $newVenv)) { Remove-Item -LiteralPath $newVenv -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $tempDir) { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
}

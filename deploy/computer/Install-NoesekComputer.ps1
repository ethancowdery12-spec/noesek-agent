# Noesek computer - Windows installer.
# One command from an elevated PowerShell:
#   powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File Install-NoesekComputer.ps1
# Sets up WSL2 + Ubuntu, installs the Noesek computer inside it, and starts it.
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$LlmApiKey = $(if ($env:NOESEK_LLM_API_KEY) { $env:NOESEK_LLM_API_KEY } else { '' }),
    [string]$LlmBaseUrl = 'https://api.deepseek.com/v1',
    [string]$LlmModel = 'deepseek-chat',
    [string]$NoesekVersion = '3.1.0',
    [string]$TarballSha256 = '311ec12aeba007508fc71faa4a7a7575ab7571c6951240f9b857bab14f1871c5'
)
$ErrorActionPreference = 'Stop'

function Say($m) { Write-Host "==> $m" }

# 1. WSL2 present?
$wslOk = $false
try { wsl.exe --status | Out-Null; $wslOk = ($LASTEXITCODE -eq 0) } catch { $wslOk = $false }
if (-not $wslOk) {
    Say 'Installing WSL2 (one-time; Windows may ask for a reboot afterward)'
    wsl.exe --install --no-distribution
    Write-Host ''
    Write-Host 'WSL2 was just installed. REBOOT Windows, then run this script again.' -ForegroundColor Yellow
    exit 0
}

# 2. Distro present?
$distros = (wsl.exe --list --quiet) -join ' '
if ($distros -notmatch [regex]::Escape(($Distro -replace '-24.04',''))) {
    Say "Installing $Distro"
    wsl.exe --install -d $Distro --no-launch
}

# 3. DeepSeek key: env var, or ask once (never sent anywhere but the VM)
if (-not $LlmApiKey) {
    $sec = Read-Host 'Paste your DeepSeek API key (input hidden)' -AsSecureString
    $LlmApiKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}

# 4. Copy the Linux setup script in and run it
$setup = Join-Path $PSScriptRoot 'setup-noesek-computer.sh'
if (-not (Test-Path $setup)) {
    Say 'Fetching setup-noesek-computer.sh from the repo'
    $setup = Join-Path $env:TEMP 'setup-noesek-computer.sh'
    curl.exe -fL --proto '=https' --tlsv1.2 'https://raw.githubusercontent.com/ethancowdery12-spec/noesek-agent/main/deploy/computer/setup-noesek-computer.sh' -o $setup
    if ($LASTEXITCODE -ne 0) { throw 'setup script download failed' }
}
$wslPath = (wsl.exe -d $Distro -- wslpath -a ($setup -replace '\\','\\'))
Say "Running setup inside $Distro (this takes a few minutes the first time)"
wsl.exe -d $Distro -u root -- bash -c "sed -i 's/\r$//' '$wslPath' && chmod +x '$wslPath'"
if ($TarballSha256 -eq '311ec12aeba007508fc71faa4a7a7575ab7571c6951240f9b857bab14f1871c5') { throw 'This installer ships with the v3.1.0 release - use the copy attached to the release.' }
wsl.exe -d $Distro -- env "NOESEK_VERSION=$NoesekVersion" "NOESEK_TARBALL_SHA256=$TarballSha256" NOESEK_LLM_API_KEY="$LlmApiKey" NOESEK_LLM_BASE_URL="$LlmBaseUrl" NOESEK_LLM_MODEL="$LlmModel" bash "$wslPath"

# 5. Make it start with Windows
$action = New-ScheduledTaskAction -Execute 'wsl.exe' -Argument "-d $Distro -- bash -c 'nohup `$HOME/noesek-venv/bin/noesek-computer > `$HOME/.noesek/computer.log 2>&1 &'"
$trigger = New-ScheduledTaskTrigger -AtLogOn
try {
    Register-ScheduledTask -TaskName 'NoesekComputer' -Action $action -Trigger $trigger -Force | Out-Null
    Say 'Scheduled task NoesekComputer registered (starts at sign-in)'
} catch {
    Say 'Could not register the auto-start task (needs admin). Start manually: wsl -d Ubuntu-24.04 -- noesek-computer'
}

Write-Host ''
Write-Host 'The Noesek computer is running.' -ForegroundColor Green
Write-Host 'Test it from PowerShell:'
Write-Host '  wsl -d Ubuntu-24.04 -- curl -s -X POST http://127.0.0.1:8780/chat -H "Content-Type: application/json" -d ''{"chat_id":"me","text":"hi"}'''
Write-Host 'WhatsApp and other channels turn on when you add their tokens to ~/.noesek/computer.env inside the VM.'

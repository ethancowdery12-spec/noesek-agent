# Noesek Agent

Self-hostable WhatsApp-first hybrid AI agent runtime with a Hermes-compatible CLI.

## Windows install - v1.11.2

Requires Python 3.11 or newer. The installer verifies pinned SHA-256 hashes, uses a non-admin isolated environment, preserves existing configuration, uses atomic activation, adds its command directory to the user PATH, and exposes both `noesek` and `hermes`. Open a new terminal after installation.

### PowerShell

```powershell
$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.2/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne '11701dacd630d298b4ad162951381361d8a6a491b688674426dc6500c104baac'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.2/8-noesek-agent-v1.11.2.tar.gz' -ExpectedSha256 '10d708b6ddf16c9a93f3db281efc94534b05765ac08a12c9fb66a450bfe6426f'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c
```

### Command Prompt (CMD)

```bat
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.2/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne '11701dacd630d298b4ad162951381361d8a6a491b688674426dc6500c104baac'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.2/8-noesek-agent-v1.11.2.tar.gz' -ExpectedSha256 '10d708b6ddf16c9a93f3db281efc94534b05765ac08a12c9fb66a450bfe6426f'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c"
```

The exact commands above passed on GitHub's `windows-latest` runner. The same run covered a clean install, `noesek` and `hermes`, reinstall/idempotency, configuration preservation, checksum failure without changing the active install, and install paths containing spaces.

Windows test: https://github.com/ethancowdery12-spec/noesek-agent/actions/runs/35360974487

Release: https://github.com/ethancowdery12-spec/noesek-agent/releases/tag/v1.11.2

## Release hashes

- PowerShell installer SHA-256: `11701dacd630d298b4ad162951381361d8a6a491b688674426dc6500c104baac`
- Source archive SHA-256: `10d708b6ddf16c9a93f3db281efc94534b05765ac08a12c9fb66a450bfe6426f`

## macOS and Linux

Use the verified POSIX installer in the v1.11.0 release.

## License

MIT. The release archive includes the project license, Hermes attribution, and dependency license inventory.

# Noesek Agent

Self-hostable WhatsApp-first hybrid AI agent runtime with a Hermes-compatible CLI.

## Windows install - v1.11.3

Requires Python 3.11 or newer. The installer verifies pinned SHA-256 hashes, uses a non-admin isolated environment, preserves existing configuration, uses atomic activation, adds its command directory to the user PATH, and exposes both `noesek` and `hermes`. Open a new terminal after installation.

### PowerShell

```powershell
$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.3/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne '38b62163815439c0580cbe77e68a99e133bac3410e083f9050385487c2f2f0a6'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.3/8-noesek-agent-v1.11.3.tar.gz' -ExpectedSha256 '670835ce43b9e0cf3c7f67b66d11f46a94e3c32d014dfc259ceb0fc0f766ab68'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c
```

### Command Prompt (CMD)

```bat
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.3/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne '38b62163815439c0580cbe77e68a99e133bac3410e083f9050385487c2f2f0a6'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v1.11.3/8-noesek-agent-v1.11.3.tar.gz' -ExpectedSha256 '670835ce43b9e0cf3c7f67b66d11f46a94e3c32d014dfc259ceb0fc0f766ab68'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c"
```

The exact commands above passed on GitHub's `windows-latest` runner. The same run covered a clean install, `noesek` and `hermes`, reinstall/idempotency, configuration preservation, checksum failure without changing the active install, and install paths containing spaces.

Windows test: https://github.com/ethancowdery12-spec/noesek-agent/actions/runs/35404952906

Release: https://github.com/ethancowdery12-spec/noesek-agent/releases/tag/v1.11.3

## Release hashes

- PowerShell installer SHA-256: `38b62163815439c0580cbe77e68a99e133bac3410e083f9050385487c2f2f0a6`
- Source archive SHA-256: `670835ce43b9e0cf3c7f67b66d11f46a94e3c32d014dfc259ceb0fc0f766ab68`

## DeepSeek

DeepSeek's current recommended Flash model ID is `deepseek-flash`; `deepseek-v4-flash` is a temporary legacy alias. Set `NOESEK_LLM_BASE_URL=https://api.deepseek.com` and `NOESEK_LLM_MODEL=deepseek-flash`. Provider failures now print a clean error with provider, base URL, model, status, and next step instead of a traceback.

## macOS and Linux

Use the verified POSIX installer in the v1.11.0 release.

## License

MIT. The release archive includes the project license, Hermes attribution, and dependency license inventory.

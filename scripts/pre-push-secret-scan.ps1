# Local pre-push secret gate for Windows (same check CI runs). Install:
#   New-Item -ItemType SymbolicLink -Path .git/hooks/pre-push -Target ../../scripts/pre-push-secret-scan.ps1
# or copy this file to .git/hooks/pre-push.ps1 and call it from a pre-push shim.
python scripts/secret_scan.py
exit $LASTEXITCODE

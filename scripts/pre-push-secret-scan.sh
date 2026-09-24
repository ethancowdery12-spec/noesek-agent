#!/bin/sh
# Local pre-push secret gate (same check CI runs). Install:
#   ln -sf ../../scripts/pre-push-secret-scan.sh .git/hooks/pre-push
exec python scripts/secret_scan.py

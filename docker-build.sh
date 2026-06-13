#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-ds-agent-loop}"

if [ -f .env ]; then
  if command -v gitleaks > /dev/null 2>&1; then
    echo "Scanning .env for secrets..."
    gitleaks detect --source . --no-git --config .gitleaks.toml --log-level warn \
      || { echo; echo "gitleaks found potential secrets in .env — aborting build."; exit 1; }
    echo "Clean."
  else
    echo "WARNING: gitleaks not installed — skipping secret scan. Install it:"
    echo "  brew install gitleaks  (mac)"
    echo "  https://github.com/gitleaks/gitleaks#installing"
  fi
fi

docker build -t "$IMAGE" .

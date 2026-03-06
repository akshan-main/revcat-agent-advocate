#!/usr/bin/env bash
set -euo pipefail

echo "=== RevenueCat Advocate OS — One-Command Setup ==="
echo ""

# 1. Check Python version
PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
if [[ "$(echo "$PY_VERSION < 3.11" | bc -l)" == "1" ]]; then
    echo "ERROR: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi
echo "[1/4] Python $PY_VERSION OK"

# 2. Install package
$PYTHON -m pip install -e ".[dev]" --quiet
echo "[2/4] Package installed"

# 3. Create .env if it doesn't exist
if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "[3/4] Created .env from template"

    # Prompt for Anthropic key (the only one that really matters)
    echo ""
    read -rp "Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
    if [[ -n "$ANTHROPIC_KEY" ]]; then
        sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_KEY|" .env
        rm -f .env.bak
    fi

    # Prompt for RC key (optional)
    read -rp "RevenueCat API key (optional, press Enter to skip): " RC_KEY
    if [[ -n "$RC_KEY" ]]; then
        sed -i.bak "s|^REVENUECAT_API_KEY=.*|REVENUECAT_API_KEY=$RC_KEY|" .env
        sed -i.bak "s|^DEMO_MODE=.*|DEMO_MODE=false|" .env
        rm -f .env.bak
    else
        sed -i.bak "s|^DEMO_MODE=.*|DEMO_MODE=true|" .env
        rm -f .env.bak
    fi
else
    echo "[3/4] .env already exists, skipping"
fi

# 4. Run full pipeline
echo "[4/4] Running full demo pipeline..."
echo ""
revcat-advocate demo-run

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Site ready at: site_output/"
echo "Preview: python3 -m http.server -d site_output 8000"
echo "Verify:  revcat-advocate verify-ledger"
echo "Tests:   pytest tests/ -v"

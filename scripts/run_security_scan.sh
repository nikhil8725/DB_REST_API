#!/usr/bin/env bash
set -eo pipefail

echo "=========================================================="
echo " Running Banking Security & Open-Source Vulnerability Scan"
echo "=========================================================="

echo "[1/3] Running Python Dependency CVE Audit (pip-audit)..."
.venv/bin/pip-audit --desc on

echo "[2/3] Running Bandit Static Application Security Testing (SAST)..."
.venv/bin/bandit -r app -ll -ii

echo "[3/3] Running Ruff Linter & Formatting Check..."
.venv/bin/ruff check app/ tests/

echo "=========================================================="
echo " SUCCESS: All security and vulnerability gates passed!"
echo "=========================================================="

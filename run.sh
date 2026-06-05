#!/usr/bin/env bash
# Jalankan Gold AI Trading Bot (aktifkan venv otomatis).
#   bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "❌ venv belum ada. Jalankan dulu:  bash install.sh"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

if [ ! -f .env ]; then
  echo "❌ .env belum ada. Jalankan:  python setup.py"
  exit 1
fi

echo "🟡 Menjalankan Gold AI Trading Bot ... (Ctrl+C untuk berhenti)"
exec python main.py

#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  Gold AI Trading Bot — installer otomatis (Linux / macOS / VPS)
#  Jalankan:   bash install.sh
#
#  Yang dilakukan:
#    1. Cek Python 3.10+ (disarankan 3.12).
#    2. Buat virtualenv ./venv
#    3. Install dependency (requirements.txt) — kombinasi numpy<2 + pandas-ta
#       yang stabil & teruji (lihat catatan di requirements.txt).
#    4. Siapkan file .env dari .env.example bila belum ada.
#    5. Pesan langkah berikutnya (setup.py → run.sh).
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")"
echo "════════════════════════════════════════════════════"
echo "  🟡 Gold AI Trading Bot — Installer"
echo "════════════════════════════════════════════════════"

# ── 1. Cari interpreter Python yang cocok (>=3.10) ──────────────────────────
PY=""
for cand in python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0.0")
    major=${ver%%.*}; minor=${ver##*.}
    if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then PY="$cand"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Butuh Python 3.10+ (disarankan 3.12). Install dulu lalu ulangi."
  exit 1
fi
echo "✅ Python: $("$PY" --version)  ($PY)"

# ── 2. Virtualenv ───────────────────────────────────────────────────────────
if [ ! -d venv ]; then
  echo "📦 Membuat virtualenv ./venv ..."
  "$PY" -m venv venv
fi
# Pakai interpreter venv lewat path absolut (lebih andal daripada bergantung
# pada `activate` — tahan shell aneh / PATH yang di-override).
VENV_PY="$PWD/venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$PWD/venv/Scripts/python.exe"   # fallback Windows/Git-Bash
# shellcheck disable=SC1091
source venv/bin/activate 2>/dev/null || true
echo "✅ venv: $("$VENV_PY" --version)"

# ── 3. Dependencies ─────────────────────────────────────────────────────────
echo "⬆️  Upgrade pip + build tools ..."
# setuptools & wheel WAJIB: sebagian paket (mis. pandas-ta) dibangun dari sdist
# dan butuh 'setuptools.build_meta'. venv baru tidak selalu menyertakannya.
"$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null
echo "📥 Install dependencies (bisa 1-3 menit) ..."
"$VENV_PY" -m pip install -r requirements.txt
echo "✅ Dependencies terpasang."

# ── 4. File .env ──────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Dibuat .env dari template. WAJIB isi API key kamu."
else
  echo "ℹ️  .env sudah ada — tidak ditimpa."
fi

# ── 5. Smoke test import ──────────────────────────────────────────────────────
echo "🔍 Cek import inti ..."
"$VENV_PY" -c "import config, data_fetcher, technical_analysis, llm_brain, trade_engine, main; print('   ✅ semua modul inti import OK')"

cat <<'NEXT'

════════════════════════════════════════════════════
  ✅ Instalasi selesai!
════════════════════════════════════════════════════
  Langkah berikutnya:

  1) Aktifkan venv (tiap sesi baru):
        source venv/bin/activate

  2) Isi konfigurasi — pilih salah satu:
        python setup.py          # wizard interaktif (disarankan)
        # atau edit .env manual

  3) Jalankan bot:
        bash run.sh              # atau:  python main.py

  ⚠️  Default PAPER_TRADING=True (simulasi, AMAN).
      Set False HANYA setelah uji di Testnet / size kecil.
════════════════════════════════════════════════════
NEXT

#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  Gold AI Trading Bot — one-line bootstrap installer
#
#  Pasang langsung dari internet (mirip "curl | bash"-nya Hermes):
#
#     curl -fsSL https://raw.githubusercontent.com/rooktheaiid-collab/gold-ai-trading-bot/main/bootstrap.sh | bash
#
#  Yang dilakukan otomatis:
#    1. Deteksi OS + pasang prasyarat (git, python3, venv, pip) — Linux(apt/dnf/pacman)/macOS(brew).
#    2. Clone (atau update) repo ke ~/gold-ai-trading-bot
#    3. Jalankan install.sh (venv + dependencies + .env + smoke-test)
#    4. Tampilkan langkah terakhir: setup wizard + cara run.
#
#  Aman diulang (idempotent). Tidak menimpa .env yang sudah ada.
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/rooktheaiid-collab/gold-ai-trading-bot.git"
TARGET="${GOLDBOT_DIR:-$HOME/gold-ai-trading-bot}"

c() { printf '\033[1;33m%s\033[0m\n' "$*"; }   # kuning
ok() { printf '\033[1;32m%s\033[0m\n' "$*"; }  # hijau
err() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

c "════════════════════════════════════════════════════"
c "  🟡 Gold AI Trading Bot — Bootstrap Installer"
c "════════════════════════════════════════════════════"

# ── helper: pasang paket sesuai package manager ─────────────────────────────
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"
install_pkgs() {
  if   command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -y && $SUDO apt-get install -y "$@"
  elif command -v dnf     >/dev/null 2>&1; then $SUDO dnf install -y "$@"
  elif command -v yum     >/dev/null 2>&1; then $SUDO yum install -y "$@"
  elif command -v pacman  >/dev/null 2>&1; then $SUDO pacman -Sy --noconfirm "$@"
  elif command -v brew    >/dev/null 2>&1; then brew install "$@"
  else err "❌ Package manager tak dikenal. Pasang manual: $*"; return 1; fi
}

# ── 1. Prasyarat ────────────────────────────────────────────────────────────
need=()
command -v git >/dev/null 2>&1 || need+=("git")
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then need+=("python3"); fi
# Debian/Ubuntu: venv & pip terpisah
if command -v apt-get >/dev/null 2>&1; then need+=("python3-venv" "python3-pip"); fi
if [ "${#need[@]}" -gt 0 ]; then
  c "📦 Memasang prasyarat: ${need[*]}"
  install_pkgs "${need[@]}"
fi
ok "✅ Prasyarat siap."

# ── 2. Clone / update repo ──────────────────────────────────────────────────
if [ -d "$TARGET/.git" ]; then
  c "🔄 Repo sudah ada di $TARGET — menarik update ..."
  git -C "$TARGET" pull --ff-only || c "(lewati pull — ada perubahan lokal)"
else
  c "⬇️  Clone repo ke $TARGET ..."
  git clone "$REPO_URL" "$TARGET"
fi
cd "$TARGET"

# ── 3. Installer inti (venv + deps + .env) ──────────────────────────────────
c "⚙️  Menjalankan install.sh ..."
bash install.sh

# shellcheck disable=SC1091
source venv/bin/activate

# ── 4. Konfigurasi + jalankan — SEKALI JALAN ────────────────────────────────
# Punya terminal? (lewat `curl | bash`, stdin = pipe, jadi pakai /dev/tty)
HAS_TTY=0
if [ -t 0 ] || { [ -e /dev/tty ] && (exec </dev/tty) 2>/dev/null; }; then HAS_TTY=1; fi

if [ "${GOLDBOT_NONINTERACTIVE:-0}" = "1" ]; then
  c "🤖 Mode non-interaktif — isi .env dari environment variables ..."
  python setup.py --noninteractive
  HAS_TTY=0
elif [ "$HAS_TTY" = "1" ]; then
  c "🧭 Lanjut setup API key (sekali jalan) ..."
  python setup.py --guided </dev/tty || c "(setup dilewati — bisa diulang: python setup.py --guided)"
  echo
  ans=$(printf '  ▶️  Jalankan bot sekarang? (PAPER/simulasi, AMAN) (y/n) > '; head -n1 </dev/tty)
  if printf '%s' "$ans" | grep -qi '^y'; then
    ok "🟡 Menjalankan bot ... (Ctrl+C untuk berhenti)"
    exec bash run.sh </dev/tty
  fi
fi

# ── 5. Langkah terakhir (jika belum dijalankan) ─────────────────────────────
cat <<NEXT

$(ok "════════════════════════════════════════════════════")
$(ok "  ✅ Bot terpasang di:  $TARGET")

  Lanjutkan kapan saja:
    cd "$TARGET"
    source venv/bin/activate
    python setup.py --guided   # isi API key (Binance, LLM, Telegram) — sekali jalan
    bash run.sh                # jalankan (default PAPER = simulasi, AMAN)

  Non-interaktif (VPS/otomatis): set env var lalu
    GOLDBOT_NONINTERACTIVE=1  + BINANCE_API_KEY=... LLM_API_KEY=...  python setup.py -n

  24/7 di VPS: lihat goldbot.service.example  •  Telegram bermasalah: python telegram_check.py
  ⚠️  Default PAPER_TRADING=True. Set False HANYA setelah uji Testnet / size kecil.
$(ok "════════════════════════════════════════════════════")
NEXT

"""
Gold Trading Bot — Setup Wizard
================================
Konfigurator .env. Tiga mode:

  python setup.py                 # menu interaktif (pilih bagian yang mau diubah)
  python setup.py --guided        # wizard linear sekali jalan (first-run) → save → selesai
  python setup.py --noninteractive# isi .env dari ENVIRONMENT VARIABLES, tanpa tanya (VPS/Docker)

Selalu MEMPERTAHANKAN semua key & komentar lain di .env (filter, circuit breaker,
self-learning, dll). Hanya field yang kamu ubah yang ditimpa.
Input dibaca dari /dev/tty bila stdin bukan terminal (jadi aman dipakai lewat
`curl ... | bash`).
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
EXAMPLE_PATH = os.path.join(HERE, ".env.example")

# field -> (label, default, secret?)
SCHEMA = {
    "binance": [
        ("BINANCE_API_KEY",    "Binance API Key",    "", True),
        ("BINANCE_API_SECRET", "Binance API Secret", "", True),
    ],
    "llm": [
        ("LLM_PROVIDER",   "LLM Provider (openai/anthropic)", "openai", False),
        ("LLM_BASE_URL",   "LLM Base URL",                    "https://api.openai.com/v1", False),
        ("LLM_API_KEY",    "LLM API Key",                     "", True),
        ("LLM_MODEL",      "LLM Model",                       "gpt-4o", False),
    ],
    "telegram": [
        ("TELEGRAM_BOT_TOKEN", "Telegram Bot Token (dari @BotFather)", "", True),
        ("TELEGRAM_CHAT_ID",   "Telegram Chat ID (cek via @userinfobot / telegram_check.py)", "", False),
    ],
    "news": [
        ("NEWS_API_KEY", "NewsAPI Key (dari newsapi.org)", "", True),
    ],
    "trading": [
        ("TRADE_USDT",    "Modal per trade (USDT)", "50", False),
        ("LEVERAGE",      "Leverage (x)",           "5",  False),
        ("STOP_LOSS_PCT", "Stop loss (mis. 0.005 = 0.5%)", "0.005", False),
        ("TAKE_PROFIT_PCT","Take profit (mis. 0.015 = 1.5%)", "0.015", False),
        ("PAPER_TRADING", "Paper mode? (True/False)", "True", False),
    ],
}
SECTION_ORDER = ["binance", "llm", "telegram", "news", "trading"]

# nilai placeholder dari .env.example yang harus dianggap "belum diisi"
def _is_placeholder(v: str) -> bool:
    v = (v or "").strip()
    return (not v) or v.startswith("your_") or v.endswith("_here")


# ── input yang tahan `curl | bash` (baca dari /dev/tty bila perlu) ───────────
_TTY = None
def _tty():
    global _TTY
    if _TTY is None:
        try:
            _TTY = open("/dev/tty")
        except Exception:
            _TTY = False
    return _TTY

def ask(prompt: str) -> str:
    if sys.stdin and sys.stdin.isatty():
        try:
            return input(prompt)
        except EOFError:
            return ""
    t = _tty()
    if t:
        sys.stdout.write(prompt); sys.stdout.flush()
        line = t.readline()
        return line.rstrip("\n") if line else ""
    return ""  # benar-benar non-interaktif


# ── baca .env jadi dict (placeholder → "") ──────────────────────────────────
def load_env() -> dict:
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            v = v.split("#", 1)[0].strip().strip('"').strip("'")  # buang komentar inline
            env[k.strip()] = "" if _is_placeholder(v) else v
    return env


# ── tulis perubahan TANPA menghapus key/komentar lain ───────────────────────
def update_env_file(updates: dict):
    """Update KEY=value di .env untuk tiap key di `updates`, sisanya utuh."""
    if not os.path.exists(ENV_PATH):
        if os.path.exists(EXAMPLE_PATH):
            shutil.copy(EXAMPLE_PATH, ENV_PATH)
        else:
            open(ENV_PATH, "w").close()
    lines = open(ENV_PATH, encoding="utf-8").read().splitlines()
    seen = set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                seen.add(k)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n✅ Tersimpan ke {ENV_PATH} (semua konfigurasi lain dipertahankan)\n")


def mask(v: str, secret: bool) -> str:
    if not v:
        return "(belum diset)"
    if secret and len(v) > 8:
        return v[:4] + "•" * 6 + v[-3:]
    return v


# ── prompt satu bagian (mengisi `env`) ──────────────────────────────────────
def prompt_section(env: dict, section: str):
    print(f"\n=== Setup: {section.upper()} ===")
    for key, label, default, secret in SCHEMA[section]:
        cur = env.get(key, "")
        shown = mask(cur, secret) if cur else (default or "(kosong)")
        val = ask(f"  {label}\n   [{shown}] > ").strip()
        if val:
            env[key] = val
        elif not cur and default:
            env[key] = default
    if section == "telegram":
        test_telegram(env)
    elif section == "news":
        test_news(env)


def test_telegram(env: dict):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat  = env.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        print("  ⚠️  Token / chat id belum lengkap → bot tak bisa balas. "
              "Isi keduanya, atau jalankan `python telegram_check.py` (auto-deteksi chat id).")
        return
    if ask("  Kirim pesan tes ke Telegram sekarang? (y/n) > ").strip().lower() != "y":
        return
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat,
                  "text": "✅ *Gold Bot* berhasil terhubung ke Telegram!",
                  "parse_mode": "Markdown"}, timeout=10)
        if r.status_code == 200:
            print("  ✅ Pesan tes terkirim! Cek Telegram kamu.")
        else:
            print(f"  ❌ Gagal ({r.status_code}): {r.text[:160]}")
            print("     → Jalankan `python telegram_check.py` untuk diagnosa lengkap.")
    except Exception as e:
        print(f"  ❌ Error: {e}")


def test_news(env: dict):
    key = env.get("NEWS_API_KEY", "")
    if not key:
        print("  ⚠️  NewsAPI key belum diset, lewati tes.")
        return
    if ask("  Tes ambil berita dari NewsAPI sekarang? (y/n) > ").strip().lower() != "y":
        return
    try:
        import requests
        r = requests.get("https://newsapi.org/v2/everything",
                         params={"q": "gold price", "pageSize": 1,
                                 "language": "en", "apiKey": key}, timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("status") == "ok":
            n = data.get("totalResults", 0)
            sample = (data.get("articles") or [{}])[0].get("title", "")
            print(f"  ✅ NewsAPI OK! {n} artikel ditemukan. Contoh: {sample[:70]}")
        else:
            print(f"  ❌ Gagal: {data.get('message', r.text[:160])}")
    except Exception as e:
        print(f"  ❌ Error: {e}")


def show_config(env: dict):
    print("\n========= KONFIGURASI SAAT INI =========")
    for section in SECTION_ORDER:
        print(f"\n[{section.upper()}]")
        for key, label, default, secret in SCHEMA[section]:
            print(f"  {key:18s} = {mask(env.get(key,''), secret)}")
    print("========================================")


def schema_keys():
    return [k for s in SECTION_ORDER for (k, *_ ) in SCHEMA[s]]


# ── MODE 1: menu interaktif ─────────────────────────────────────────────────
MENU = """
╔══════════════════════════════════════╗
║   GOLD TRADING BOT — SETUP WIZARD     ║
╠══════════════════════════════════════╣
║  1) Setup Binance API                 ║
║  2) Setup LLM (otak bot)              ║
║  3) Setup Telegram (bot + chat id)    ║
║  4) Setup NewsAPI (berita pasar)      ║
║  5) Setup parameter trading           ║
║  6) Lihat konfigurasi saat ini        ║
║  7) Simpan & keluar                   ║
╚══════════════════════════════════════╝
Pilih (1-7): """

def run_menu(env):
    sections = {"1": "binance", "2": "llm", "3": "telegram", "4": "news", "5": "trading"}
    while True:
        choice = ask(MENU).strip()
        if choice in sections:
            prompt_section(env, sections[choice])
        elif choice == "6":
            show_config(env)
        elif choice == "7":
            update_env_file({k: env[k] for k in schema_keys() if env.get(k, "") != ""})
            print("Selesai! Jalankan bot dengan:  bash run.sh\n")
            break
        else:
            print("Pilihan tidak valid.")


# ── MODE 2: guided linear (first-run, sekali jalan) ─────────────────────────
def run_guided(env):
    print("\n🧭 Setup terpandu — isi sekali jalan. Tekan ENTER untuk pakai nilai default/lama.\n")
    print("   (Binance + LLM WAJIB untuk live; Telegram & NewsAPI opsional)\n")
    for section in ["binance", "llm", "telegram", "news", "trading"]:
        if section in ("telegram", "news"):
            if ask(f"  Setup {section.upper()} sekarang? (opsional, y/n) > ").strip().lower() != "y":
                continue
        prompt_section(env, section)
    show_config(env)
    update_env_file({k: env[k] for k in schema_keys() if env.get(k, "") != ""})
    print("✅ Konfigurasi tersimpan. Lanjut jalankan:  bash run.sh\n")


# ── MODE 3: non-interaktif dari environment variables ───────────────────────
def run_noninteractive(env):
    updates = {}
    for k in schema_keys():
        v = os.getenv(k, "")
        if v and not _is_placeholder(v):
            updates[k] = v
        elif env.get(k, "") != "":
            updates[k] = env[k]
    if not updates:
        print("⚠️  Tidak ada env var yang diset. Set mis. BINANCE_API_KEY=... LLM_API_KEY=... "
              "lalu jalankan ulang, atau pakai `python setup.py --guided`.")
        return
    update_env_file(updates)
    have = [k for k in ("BINANCE_API_KEY", "LLM_API_KEY") if updates.get(k)]
    print(f"✅ Non-interaktif: {len(updates)} field diisi dari environment. "
          f"Kunci inti terisi: {', '.join(have) or '(belum ada)'}")


def main():
    args = set(sys.argv[1:])
    env = load_env()
    if {"--noninteractive", "--from-env", "-n"} & args:
        run_noninteractive(env)
    elif {"--guided", "--first-run", "-g"} & args:
        run_guided(env)
    else:
        run_menu(env)


if __name__ == "__main__":
    main()

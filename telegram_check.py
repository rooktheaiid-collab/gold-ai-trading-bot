#!/usr/bin/env python3
"""
Telegram Doctor — diagnosa kenapa bot & Telegram tidak nyambung.
================================================================
Jalankan:
    source venv/bin/activate        # (kalau pakai venv)
    python telegram_check.py

Yang dicek (urut):
  1. TELEGRAM_BOT_TOKEN terbaca?            -> getMe (validasi token + nama bot)
  2. Webhook nyangkut?                       -> getWebhookInfo (webhook MEMBLOKIR polling)
  3. Chat ID benar / ketemu otomatis?        -> getUpdates (deteksi chat_id dari chat terakhir)
  4. Bisa kirim pesan?                        -> sendMessage tes ke CHAT_ID

Tidak mengubah apa pun kecuali kamu setuju (hapus webhook / tulis CHAT_ID ke .env).
"""
import os, sys, json
try:
    import requests
except ImportError:
    sys.exit("❌ modul 'requests' belum ada. Jalankan: pip install -r requirements.txt")

# muat .env kalau ada python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

C = {"g": "\033[1;32m", "y": "\033[1;33m", "r": "\033[1;31m", "x": "\033[0m"}
def ok(m):  print(f"{C['g']}✅ {m}{C['x']}")
def warn(m):print(f"{C['y']}⚠️  {m}{C['x']}")
def err(m): print(f"{C['r']}❌ {m}{C['x']}")
def hd(m):  print(f"\n{C['y']}{'─'*52}\n  {m}\n{'─'*52}{C['x']}")

def api(token, method, **params):
    r = requests.get(f"https://api.telegram.org/bot{token}/{method}", params=params, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"ok": False, "raw": r.text[:300]}

def set_env(key, value, path=".env"):
    """Tulis/ubah satu baris KEY=value di .env (tanpa hapus yang lain)."""
    lines, found = [], False
    if os.path.exists(path):
        lines = open(path, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"; found = True; break
    if not found:
        lines.append(f"{key}={value}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

def main():
    hd("🩺 TELEGRAM DOCTOR — Gold AI Trading Bot")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat  = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

    # ── 1. Token ─────────────────────────────────────────────────────────────
    if not token:
        err("TELEGRAM_BOT_TOKEN kosong di .env. Isi token dari @BotFather dulu.")
        return
    if token != os.getenv("TELEGRAM_BOT_TOKEN", ""):
        warn("Token punya spasi/baris ekstra — sudah aku rapikan otomatis (.strip()).")
    if ":" not in token:
        err("Format token aneh (harus seperti `123456789:ABCdef...`). Cek lagi dari @BotFather.")
        return
    code, j = api(token, "getMe")
    if not j.get("ok"):
        err(f"Token DITOLAK Telegram (getMe gagal): {j.get('description', j)}")
        err("→ Token salah/dicabut. Bikin ulang atau /revoke di @BotFather.")
        return
    me = j["result"]
    ok(f"Token valid. Bot: @{me.get('username')} (id {me.get('id')})")

    # ── 2. Webhook (pemblokir polling paling sering) ─────────────────────────
    _, w = api(token, "getWebhookInfo")
    wurl = (w.get("result") or {}).get("url") or ""
    if wurl:
        err(f"Ada WEBHOOK terpasang: {wurl}")
        err("Webhook MEMBLOKIR getUpdates (cara polling bot ini). Ini penyebab umum 'tidak nyambung'.")
        if input("  Hapus webhook sekarang biar polling jalan? (y/n) > ").strip().lower() == "y":
            api(token, "deleteWebhook", drop_pending_updates="false")
            ok("Webhook dihapus. Polling bisa jalan sekarang.")
    else:
        ok("Tidak ada webhook nyangkut (polling bebas).")

    # ── 3. Chat ID ───────────────────────────────────────────────────────────
    hd("CEK CHAT ID")
    print("Kirim 1 pesan apa saja (mis. 'halo') ke bot @%s dari HP kamu," % me.get("username"))
    print("lalu tekan ENTER di sini untuk deteksi chat id otomatis...")
    input("  [ENTER setelah kirim pesan ke bot] ")
    _, u = api(token, "getUpdates", timeout=1)
    chats = {}
    for upd in (u.get("result") or []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        ch = msg.get("chat") or {}
        if ch.get("id") is not None:
            name = ch.get("username") or ch.get("first_name") or ch.get("title") or "?"
            chats[ch["id"]] = name
    if not chats:
        warn("Belum ada pesan terdeteksi. Pastikan kamu sudah KIRIM pesan ke bot")
        warn("(harus kamu yang mulai chat — bot tidak bisa DM duluan), lalu jalankan ulang.")
    else:
        print("  Chat terdeteksi:")
        for cid, name in chats.items():
            mark = "  <- ini di .env kamu" if str(cid) == chat else ""
            print(f"    chat_id = {cid}   ({name}){mark}")
        detected = str(next(iter(chats)))
        if not chat:
            warn("TELEGRAM_CHAT_ID di .env KOSONG — ini penyebab bot tidak bisa balas!")
            if input(f"  Tulis chat_id {detected} ke .env sekarang? (y/n) > ").strip().lower() == "y":
                set_env("TELEGRAM_CHAT_ID", detected)
                chat = detected
                ok(f"Ditulis: TELEGRAM_CHAT_ID={detected} ke .env")
        elif chat not in [str(c) for c in chats]:
            warn(f"CHAT_ID di .env ({chat}) TIDAK cocok dengan chat yang kirim pesan.")
            warn("Kemungkinan salah id — balasan bot ke-kirim ke chat lain (jadi terasa 'tidak nyambung').")

    # ── 4. Tes kirim ─────────────────────────────────────────────────────────
    hd("TES KIRIM PESAN")
    if not chat:
        err("CHAT_ID masih kosong — tidak bisa tes kirim. Isi dulu (lihat langkah di atas).")
        return
    code, s = api(token, "sendMessage", chat_id=chat,
                  text="✅ Gold Bot tersambung ke Telegram! (tes dari telegram_check.py)")
    if s.get("ok"):
        ok("PESAN TES TERKIRIM! Cek Telegram kamu. Koneksi beres 🎉")
        print("\n  Sekarang jalankan bot:  bash run.sh   (atau: python main.py)")
        print("  Lalu ketik /start di chat bot.")
    else:
        err(f"Gagal kirim: {s.get('description', s)}")
        d = (s.get("description") or "").lower()
        if "chat not found" in d:
            err("→ 'chat not found': chat_id salah ATAU kamu belum pernah kirim pesan ke bot.")
        elif "bot was blocked" in d:
            err("→ Kamu mem-block bot ini. Unblock di Telegram lalu ulangi.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n(dibatalkan)")

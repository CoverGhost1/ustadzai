from telethon import TelegramClient, events
import requests
import json
import os
from collections import deque

# =============================
# CONFIG (PAKAI ENV VARIABLE)
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
google_api_key = os.getenv("GEMINI_KEY")

# GANTI DENGAN CHAT ID GRUP LU
ALLOWED_CHAT_ID = -1003123683403  # <-- GANTI INI

# =============================
# INIT TELETHON
# =============================

client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# MEMORY SYSTEM
# =============================

HISTORY_FILE = "group_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                return {
                    str(k): deque(v, maxlen=10)
                    for k, v in raw.items()
                }
        except:
            return {}
    return {}

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({
                str(k): list(v)
                for k, v in chat_history.items()
            }, f, indent=2)
    except:
        pass

chat_history = load_history()

# =============================
# PROMPT BUILDER
# =============================

def build_prompt():
    return """
Kamu adalah ustadz muda bernama ustad zai yang nongkrong bareng 2 orang di grup Telegram.

Karakter:
- Santai dan humble
- Hangat dan tidak menghakimi
- Bisa bercanda ringan
- Ramadan vibes
- Jangan terlalu panjang
- Natural seperti teman ketiga
- Jangan bilang kamu AI
- Pakai emoji ringan seperlunya 😌😂

Aturan:
- Kalau ada curhat → jawab hangat dan menenangkan
- Kalau ada bercanda → ikut bercanda
- Kalau ada overthinking → tenangkan
- Jangan terlalu formal
- Jangan jawab panjang banget

Langsung tanggapi isi obrolan.
"""

# =============================
# GEMINI HANDLER
# =============================

def get_gemini_reply(chat_id, user_msg):
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"User: {user_msg}")
    chat_history[chat_id] = history
    save_history()

    conversation = "\n".join(history)[-4000:]

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": build_prompt() +
                        "\n\nBerikut percakapan:\n" +
                        conversation +
                        "\nBalas pesan terakhir:"
                    }
                ]
            }
        ]
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_api_key}"
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(url, headers=headers, data=json.dumps(body))
        data = res.json()

        if res.status_code == 200 and "candidates" in data and data["candidates"]:
            reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
            history.append(f"AI: {reply_text}")
            save_history()
            return reply_text.strip()
        else:
            print("❌ Gemini error:", data)
            return None
    except Exception as e:
        print("❌ Gemini exception:", e)
        return None

# =============================
# MAIN GROUP HANDLER
# =============================

@client.on(events.NewMessage)
async def handle_group(event):

    # HANYA AKTIF DI GRUP TERTENTU
    if event.chat_id != ALLOWED_CHAT_ID:
        return

    # Jangan balas pesan sendiri
    if event.out:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    print(f"[GroupChat] > {msg}")

    reply = get_gemini_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)

# =============================
# RUN
# =============================

print("🤖 Ustadz Group AI aktif.")
client.start()
client.run_until_disconnected()

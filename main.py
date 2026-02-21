from telethon import TelegramClient, events
import requests
import json
import os
import time
from collections import deque

# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
google_api_key = os.getenv("GEMINI_KEY")

ALLOWED_CHAT_ID = -1003123683403

COOLDOWN = 5
MAX_HISTORY = 6

client = TelegramClient("anon_ai", api_id, api_hash)

# =============================
# MEMORY
# =============================

HISTORY_FILE = "zai_memory.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                return {
                    str(k): deque(v, maxlen=MAX_HISTORY)
                    for k, v in raw.items()
                }
        except:
            return {}
    return {}

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(
                {k: list(v) for k, v in chat_history.items()},
                f,
                indent=2
            )
    except:
        pass

chat_history = load_history()

# =============================
# PROMPT (SUPER PENDEK BIAR HEMAT)
# =============================

def build_prompt():
    return (
        "Kamu Ustadz Zai. "
        "Ngobrol santai di grup. "
        "Balas natural, singkat, gak formal, gak ceramah."
    )

# =============================
# GEMINI REQUEST
# =============================

def get_gemini_reply(chat_id, user_msg):

    user_msg = user_msg[:200]  # potong pesan panjang

    history = chat_history.get(chat_id, deque(maxlen=MAX_HISTORY))
    history.append(f"User: {user_msg}")
    chat_history[chat_id] = history

    conversation = "\n".join(history)

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": build_prompt()
                        + "\nChat:\n"
                        + conversation
                        + "\nBalas terakhir secara singkat:"
                    }
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 80,
            "temperature": 0.8
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={google_api_key}"
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
        data = res.json()

        if res.status_code == 200 and "candidates" in data:
            reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            history.append(f"AI: {reply}")
            save_history()

            return reply
        else:
            print("Gemini error:", data)
            return None

    except Exception as e:
        print("Gemini exception:", e)
        return None

# =============================
# COOLDOWN
# =============================

last_reply_time = 0

# =============================
# TELEGRAM HANDLER
# =============================

@client.on(events.NewMessage)
async def handler(event):

    global last_reply_time

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    if event.out:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    # ignore spam pendek
    if len(msg) <= 1:
        return

    # hanya aktif kalau dipanggil
    if "zai" not in msg.lower():
        return

    # cooldown
    now = time.time()
    if now - last_reply_time < COOLDOWN:
        return
    last_reply_time = now

    print("User:", msg)

    reply = get_gemini_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)
        print("Zai:", reply)

# =============================
# START
# =============================

print("🔥 Ustadz Zai Hemat Mode Aktif")
client.start()
client.run_until_disconnected()

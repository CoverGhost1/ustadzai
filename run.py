from telethon import TelegramClient, events
import requests
import json
import os
import time
from collections import deque

# =============================
# CONFIG (ENV)
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
groq_api_key = os.getenv("GROQ_KEY")

# GANTI DENGAN CHAT ID GRUP LU
ALLOWED_CHAT_ID = -1003123683403

# COOLDOWN (detik)
COOLDOWN = 5

# MAX MEMORY
MAX_HISTORY = 10

# =============================
# INIT TELETHON
# =============================

client = TelegramClient("anon_ai", api_id, api_hash)

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
                    str(k): deque(v, maxlen=MAX_HISTORY)
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
# COOLDOWN SYSTEM
# =============================

last_reply_time = 0

def can_reply():
    global last_reply_time
    now = time.time()

    if now - last_reply_time < COOLDOWN:
        return False

    last_reply_time = now
    return True

# =============================
# CHARACTER PROMPT
# =============================

def build_prompt():
    return """
Kamu adalah ustadz muda bernama ustadz zai yang nongkrong bareng 2 orang di grup Telegram.

Karakter:
- Santai dan humble
- Hangat dan tidak menghakimi
- Bisa bercanda ringan
- Ramadan vibes
- Natural seperti teman ketiga
- Jangan terlalu panjang
- Jangan terlalu formal
- Jangan bilang kamu AI
- Pakai emoji ringan seperlunya 😌😂

Aturan:
- Kalau ada curhat → jawab hangat dan menenangkan
- Kalau ada bercanda → ikut bercanda
- Kalau ada overthinking → tenangkan
- Kalau ditanya → jawab jelas tapi santai
- Jangan jawab panjang banget

Langsung tanggapi pesan terakhir secara natural.
"""

# =============================
# GROQ AI HANDLER
# =============================

def get_ai_reply(chat_id, user_msg):

    history = chat_history.get(chat_id, deque(maxlen=MAX_HISTORY))

    history.append(f"User: {user_msg}")

    chat_history[chat_id] = history

    save_history()

    conversation = "\n".join(history)[-4000:]

    prompt = (
        build_prompt()
        + "\n\nPercakapan:\n"
        + conversation
        + "\n\nBalas pesan terakhir:"
    )

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }

    try:

        res = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=30
        )

        data = res.json()

        if res.status_code == 200:

            reply_text = data["choices"][0]["message"]["content"]

            history.append(f"AI: {reply_text}")

            save_history()

            return reply_text.strip()

        else:

            print("❌ Groq API Error:")
            print(data)

            return None

    except Exception as e:

        print("❌ Groq Exception:", e)

        return None


# =============================
# TELEGRAM HANDLER
# =============================

@client.on(events.NewMessage)

async def handle_group(event):

    try:

        if event.chat_id != ALLOWED_CHAT_ID:
            return

        if event.out:
            return

        msg = event.raw_text.strip()

        if not msg:
            return

        # Anti spam cooldown
        if not can_reply():
            return

        print(f"[GroupChat] > {msg}")

        reply = get_ai_reply(str(ALLOWED_CHAT_ID), msg)

        if reply:

            await event.reply(reply)

            print(f"[AI Reply] > {reply}")

    except Exception as e:

        print("❌ Handler Error:", e)


# =============================
# START BOT
# =============================

print("🤖 Ustadz Zai AI aktif (Groq mode)")

client.start()

client.run_until_disconnected()

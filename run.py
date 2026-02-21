from telethon import TelegramClient, events
import requests
import json
import os
import random
import asyncio
from collections import deque

# =============================
# CONFIG (ENV VARIABLE)
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
google_api_key = os.getenv("GEMINI_KEY")

ALLOWED_CHAT_ID = -1003123683403  # GANTI SESUAI GRUP LU

# =============================
# INIT TELETHON
# =============================

client = TelegramClient('ustadz_ultra', api_id, api_hash)

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
                    str(k): deque(v, maxlen=15)
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
# ULTRA HUMAN PROMPT
# =============================

def build_prompt():

    styles = [
        "lagi nongkrong habis tarawih",
        "lagi santai di teras masjid",
        "lagi rebahan sambil buka hp",
        "lagi duduk santai bareng temen",
        "lagi ngopi malem"
    ]

    moods = [
        "hangat",
        "santai",
        "gaul",
        "friendly",
        "tenang"
    ]

    return f"""
Kamu adalah ustadz muda bernama Zai.

Kamu {random.choice(styles)}.
Kamu ngobrol di grup Telegram bareng 2 temen tongkrongan.

Kepribadian:
- 100% manusia asli
- umur 20an
- {random.choice(moods)}
- bukan AI
- natural banget
- gak formal
- gak terlalu bijak
- jangan ceramah
- jangan terlalu panjang

Gaya:
- kayak temen nongkrong
- kadang pake wkwk, hehe, iya juga sih
- kadang pake emoji 😌😂🙂
- kadang cuma jawab pendek
- kadang cuma emoji
- jangan sempurna banget
- jangan terlalu rapi

Kalau:
- ada curhat → hangat
- ada bercanda → ikut
- ada overthinking → tenangkan santai

Balas kayak manusia normal chatting.
"""

# =============================
# HUMANIZER SYSTEM
# =============================

def humanize(text):

    extras = [
        "",
        "",
        "",
        " wkwk",
        " hehe",
        " sih",
        " ya",
        " 😌",
        " 🙂",
        " 😂",
        "\n\nwkwk",
        "\n\niya juga sih"
    ]

    return text.strip() + random.choice(extras)

def ultra_human_short():

    options = [
        "wkwk 😂",
        "iya sih 😌",
        "hehe",
        "nah itu",
        "🙂",
        "😂",
        "bener juga",
        "hmm iya ya"
    ]

    return random.choice(options)

# =============================
# GEMINI HANDLER
# =============================

def get_gemini_reply(chat_id, user_msg):

    history = chat_history.get(chat_id, deque(maxlen=15))
    history.append(f"User: {user_msg}")
    chat_history[chat_id] = history
    save_history()

    conversation = "\n".join(history)[-5000:]

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text":
                        build_prompt() +
                        "\n\nPercakapan:\n" +
                        conversation +
                        "\nBalas pesan terakhir secara natural:"
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

        if res.status_code == 200 and "candidates" in data:
            reply_text = data["candidates"][0]["content"]["parts"][0]["text"]

            # 20% chance cuma jawab pendek banget
            if random.random() < 0.2:
                reply_text = ultra_human_short()

            reply_text = humanize(reply_text)

            history.append(f"Zai: {reply_text}")
            save_history()

            return reply_text.strip()
        else:
            print("Gemini error:", data)
            return None

    except Exception as e:
        print("Gemini exception:", e)
        return None

# =============================
# MAIN HANDLER
# =============================

@client.on(events.NewMessage)
async def handle_group(event):

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    if event.out:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    print(f"[Group] > {msg}")

    # 10% chance diem (realistic)
    if random.random() < 0.1:
        return

    reply = get_gemini_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:

        # human typing delay
        delay = random.uniform(1.5, 4.5)
        await asyncio.sleep(delay)

        await event.reply(reply)

# =============================
# RUN
# =============================

print("🔥 Ustadz Zai ULTRA HUMAN MODE aktif.")
client.start()
client.run_until_disconnected()

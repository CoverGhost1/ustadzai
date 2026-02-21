from telethon import TelegramClient, events
import requests
import json
import os
from collections import deque

# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
google_api_key = os.getenv("GEMINI_KEY")

ALLOWED_CHAT_ID = -1003123683403

client = TelegramClient('ustadz_zai_session', api_id, api_hash)

# =============================
# BOT STATUS CONTROL
# =============================

bot_active = True  # default aktif

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
                    str(k): deque(v, maxlen=12)
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
# PROMPT
# =============================

def build_prompt():
    return """
Kamu adalah Ustadz Zai.

- Ustadz muda Indonesia
- Tongkrongan vibe
- Bisa gaul dan formal
- Hangat dan bijak
- Tidak menghakimi
- Natural seperti manusia asli
- Jangan pernah bilang kamu AI atau bot

Jawab santai, natural, dan tidak terlalu panjang.
"""

# =============================
# GEMINI FUNCTION
# =============================

def get_gemini_reply(chat_id, user_msg):

    history = chat_history.get(chat_id, deque(maxlen=12))
    history.append(f"Teman: {user_msg}")
    chat_history[chat_id] = history

    conversation = "\n".join(history)[-4000:]

    body = {
        "contents": [{
            "parts": [{
                "text":
                build_prompt()
                + "\n\nObrolan:\n"
                + conversation
                + "\n\nBalas sebagai Ustadz Zai:"
            }]
        }]
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_api_key}"

    try:
        res = requests.post(url, json=body)
        data = res.json()

        if "candidates" in data:
            reply = data["candidates"][0]["content"]["parts"][0]["text"]

            history.append(f"Zai: {reply}")
            save_history()

            return reply

    except Exception as e:
        print("Error:", e)

    return None

# =============================
# MAIN HANDLER
# =============================

@client.on(events.NewMessage)
async def handler(event):

    global bot_active

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    # =========================
    # COMMAND START
    # =========================

    if msg.lower() == "/m":

        bot_active = True

        await event.reply(
            "🤍 Ustadz Zai hadir lagi.\nSilakan lanjut ngobrol."
        )
        return

    # =========================
    # COMMAND STOP
    # =========================

    if msg.lower() == "/st":

        bot_active = False

        await event.reply(
            "🤍 Baik, Ustadz Zai pamit dulu.\nKalau butuh, panggil lagi ya."
        )
        return

    # =========================
    # CHECK STATUS
    # =========================

    if not bot_active:
        return

    # jangan balas pesan sendiri
    if event.out:
        return

    print("[Group] >", msg)

    reply = get_gemini_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)

# =============================
# RUN
# =============================

print("🤍 Ustadz Zai siap.")
client.start()
client.run_until_disconnected()

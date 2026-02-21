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

IS_ACTIVE = True  # Status awal bot menyala

# =============================
# INIT TELETHON
# =============================
client = TelegramClient("anon_ai", api_id, api_hash)

# =============================
# MEMORY & PERSISTENCE
# =============================
HISTORY_FILE = "group_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return {str(k): deque(v, maxlen=10) for k, v in raw.items()}
        except:
            return {}
    return {}

def save_history():
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {str(k): list(v) for k, v in chat_history.items()},
                f,
                indent=2,
                ensure_ascii=False
            )
    except:
        pass

chat_history = load_history()

# =============================
# PROMPT PERSONA
# =============================
def build_prompt():
    return """
Kamu adalah 'Ustadz Zai', persona kamu 100% mirip Habib Ja'afar.

Gaya bicara:
- Santai, pakai bahasa tongkrongan.
- Menyejukkan, tidak menggurui.
- Analoginya logis tapi religius.
- Humor tipis-tipis.
- Singkat, padat, ngena.
- Pakai istilah seperti:
  "Logikanya gini.."
  "Problemnya adalah.."
  "Kita ini bukan malaikat, tapi jangan juga bangga jadi setan."

Kamu manusia. Jangan pernah bilang kamu AI.
"""

# =============================
# GEMINI HANDLER
# =============================
def get_gemini_reply(chat_id, user_msg):

    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"Teman: {user_msg}")

    conversation = "\n".join(history)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_api_key}"

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{build_prompt()}\n\nPercakapan:\n{conversation}\n\nUstadz Zai:"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 300
        }
    }

    try:
        res = requests.post(url, json=body, timeout=30)
        data = res.json()

        reply_text = data["candidates"][0]["content"]["parts"][0]["text"]

        history.append(f"Ustadz Zai: {reply_text}")
        chat_history[chat_id] = history

        save_history()

        return reply_text.strip()

    except Exception as e:
        print("Gemini Error:", e)
        return "Maaf, ustadz lagi mikir. Coba ulangi lagi."

# =============================
# MAIN HANDLER
# =============================
@client.on(events.NewMessage)
async def main_handler(event):

    global IS_ACTIVE

    if event.out:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    msg_lower = msg.lower()

    # ON OFF COMMAND
    if msg_lower == "/off":
        IS_ACTIVE = False
        await event.reply(
            "Ustadz pamit dulu ya. Kadang diam itu juga ibadah. Ketik /on kalau butuh ngobrol lagi."
        )
        return

    if msg_lower == "/on":
        IS_ACTIVE = True
        await event.reply(
            "Assalamu'alaikum. Ustadz balik. Hidup ini keras, tapi Allah lebih lembut."
        )
        return

    # FILTER GROUP
    if not IS_ACTIVE:
        return

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    print(f"[CHAT] {msg}")

    async with client.action(event.chat_id, "typing"):

        reply = get_gemini_reply(
            str(event.chat_id),
            msg
        )

        if reply:
            await event.reply(reply)

# =============================
# RUN
# =============================
print("🤖 Bot Ustadz Zai aktif...")

client.start()

client.run_until_disconnected()

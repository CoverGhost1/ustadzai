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
groq_api_key = os.getenv("GROQ_KEY")

ALLOWED_CHAT_ID = -1003123683403

COOLDOWN = 6
MAX_HISTORY = 60

client = TelegramClient("anon_ai", api_id, api_hash)

# =============================
# USER IDENTITIES
# =============================

USER_IDENTITIES = {

    "8229304441": {
        "name": "Rifkyy",
        "style": "cowok kalem, santai"
    },

    "6876331769": {
        "name": "Adell",
        "style": "cewek excited, ceria"
    }

}

# =============================
# MEMORY FILE
# =============================

HISTORY_FILE = "zai_memory_v5.json"


def load_history():

    if os.path.exists(HISTORY_FILE):

        try:

            with open(HISTORY_FILE, "r", encoding="utf-8") as f:

                data = json.load(f)

                return {
                    k: deque(v, maxlen=MAX_HISTORY)
                    for k, v in data.items()
                }

        except:

            return {}

    return {}


def save_history():

    try:

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:

            json.dump(chat_history, f, indent=2, ensure_ascii=False)

    except:

        pass


chat_history = load_history()

# =============================
# COOLDOWN
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
# GET USER NAME
# =============================


def get_user_name(user_id, fallback):

    uid = str(user_id)

    if uid in USER_IDENTITIES:
        return USER_IDENTITIES[uid]["name"]

    return fallback

# =============================
# SYSTEM PROMPT
# =============================


def build_system_prompt(user_name):

    return f"""
Kamu adalah Ustadz Zai.

Kamu sedang ngobrol santai di grup Telegram dengan teman dekat.

Kamu berbicara dengan {user_name}.

Kepribadian kamu:
- santai
- natural
- hangat
- tidak formal
- tidak ceramah
- tidak kaku
- seperti teman lama

ATURAN PENTING:

- Fokus hanya pada pesan terakhir
- Jangan halusinasi
- Jangan menebak hal yang tidak disebut
- Jangan asumsi perasaan tanpa alasan
- Jangan jadi AI
- Jangan formal

Balas singkat, natural, manusia banget.
"""

# =============================
# BUILD MESSAGES
# =============================


def build_messages(chat_id, user_name, message):

    if chat_id not in chat_history:

        chat_history[chat_id] = deque(maxlen=MAX_HISTORY)

    history = chat_history[chat_id]

    messages = []

    messages.append({
        "role": "system",
        "content": build_system_prompt(user_name)
    })

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": message
    })

    return messages

# =============================
# SAVE MEMORY
# =============================


def save_user(chat_id, message):

    chat_history[chat_id].append({
        "role": "user",
        "content": message
    })


def save_ai(chat_id, reply):

    chat_history[chat_id].append({
        "role": "assistant",
        "content": reply
    })

# =============================
# AI REQUEST
# =============================


def get_ai_reply(chat_id, user_name, message):

    messages = build_messages(chat_id, user_name, message)

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {groq_api_key},
        "Content-Type": "application/json"
    }

    body = {

        "model": "llama-3.1-8b-instant",

        "messages": messages,

        "temperature": 0.7,

        "max_tokens": 120,

        "presence_penalty": 0.3,

        "frequency_penalty": 0.3

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

            reply = data["choices"][0]["message"]["content"].strip()

            save_user(chat_id, message)

            save_ai(chat_id, reply)

            save_history()

            return reply

        else:

            print("AI ERROR:", data)

            return None

    except Exception as e:

        print("REQUEST ERROR:", e)

        return None

# =============================
# TELEGRAM HANDLER
# =============================


@client.on(events.NewMessage)
async def handler(event):

    try:

        if event.chat_id != ALLOWED_CHAT_ID:
            return

        if event.out:
            return

        text = event.raw_text.strip()

        if not text:
            return

        if not can_reply():
            return

        sender = await event.get_sender()

        name = get_user_name(
            sender.id,
            sender.first_name or "User"
        )

        print(f"{name}: {text}")

        reply = get_ai_reply(
            str(ALLOWED_CHAT_ID),
            name,
            text
        )

        if reply:

            await event.reply(reply)

            print("Zai:", reply)

    except Exception as e:

        print("HANDLER ERROR:", e)

# =============================
# START
# =============================

print("Ustadz Zai v5 aktif...")

client.start()

client.run_until_disconnected()

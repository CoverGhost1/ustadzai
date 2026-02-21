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

COOLDOWN = 8
MAX_HISTORY = 200

client = TelegramClient("anon_ai", api_id, api_hash)

# =============================
# USER IDENTITIES
# =============================

USER_IDENTITIES = {

    "8229304441": {
        "name": "Rifkyy",
        "role": "cowok kalem",
        "relation": "Pacarnya Adell"
    },

    "6876331769": {
        "name": "Adell",
        "role": "cewek excited",
        "relation": "Pacarnya Rifkyy"
    }

}

# =============================
# MEMORY FILE
# =============================

HISTORY_FILE = "zai_memory.json"


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
# USER NAME
# =============================


def get_user_identity(user_id, fallback):

    uid = str(user_id)

    if uid in USER_IDENTITIES:

        return USER_IDENTITIES[uid]["name"]

    return fallback

# =============================
# RELATION TEXT
# =============================


def build_relation_text():

    text = ""

    for uid, data in USER_IDENTITIES.items():

        text += f"{data['name']} adalah {data['relation']}.\n"

    return text

# =============================
# SYSTEM PROMPT (SUPER STRONG)
# =============================


def build_system_prompt():

    return f"""
Kamu adalah Ustadz Zai.

Identitas:
- cowok santai
- ngobrol natural
- hangat
- tidak formal
- tidak kaku
- bukan AI
- seperti teman nongkrong lama

Gaya bicara:
- santai
- natural
- manusia banget
- kadang bercanda ringan
- tidak ceramah
- tidak terlalu panjang
- tidak terlalu pendek

Relasi grup:
{build_relation_text()}

Rules penting:
- balas seperti manusia asli
- jangan kaku
- jangan formal
- jangan ceramah kecuali diminta
- jangan menjelaskan kamu AI
- fokus balas pesan terakhir
"""

# =============================
# BUILD MESSAGE ARRAY
# =============================


def build_messages(chat_id, user_name, message):

    if chat_id not in chat_history:

        chat_history[chat_id] = deque(maxlen=MAX_HISTORY)

    history = chat_history[chat_id]

    messages = []

    messages.append({
        "role": "system",
        "content": build_system_prompt()
    })

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": f"{user_name}: {message}"
    })

    return messages

# =============================
# SAVE USER MESSAGE
# =============================


def save_user_message(chat_id, user_name, message):

    chat_history[chat_id].append({
        "role": "user",
        "content": f"{user_name}: {message}"
    })

    save_history()

# =============================
# SAVE AI MESSAGE
# =============================


def save_ai_message(chat_id, reply):

    chat_history[chat_id].append({
        "role": "assistant",
        "content": reply
    })

    save_history()

# =============================
# AI REQUEST
# =============================


def get_ai_reply(chat_id, user_name, message):

    messages = build_messages(chat_id, user_name, message)

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }

    body = {

        "model": "llama-3.1-8b-instant",

        "messages": messages,

        "temperature": 0.95,

        "max_tokens": 120,

        "presence_penalty": 0.6,

        "frequency_penalty": 0.4

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

            save_user_message(chat_id, user_name, message)

            save_ai_message(chat_id, reply)

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

        name = get_user_identity(
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

print("Ustadz Zai AI v4 aktif...")

client.start()

client.run_until_disconnected()

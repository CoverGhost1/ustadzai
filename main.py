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

COOLDOWN = 10
MAX_HISTORY = 10000

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
# MEMORY SYSTEM
# =============================

HISTORY_FILE = "group_history.json"

def load_history():

    if os.path.exists(HISTORY_FILE):

        try:

            with open(HISTORY_FILE, "r", encoding="utf-8") as f:

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
# GET USER IDENTITY
# =============================

def get_user_identity(user_id, fallback_name):

    user_id = str(user_id)

    if user_id in USER_IDENTITIES:

        identity = USER_IDENTITIES[user_id]

        return f"{identity['name']} ({identity['role']})"

    return fallback_name

# =============================
# BUILD RELATION TEXT
# =============================

def build_relation_text():

    text = "\nHubungan anggota grup:\n"

    for uid, data in USER_IDENTITIES.items():

        text += f"- {data['name']} adalah {data['relation']}\n"

    return text

# =============================
# PERSONALITY PROMPT
# =============================

def build_prompt():
    return f"""
Kamu adalah ustadz muda bernama Ustadz Zai.
Kamu sedang nongkrong santai di grup Telegram bersama teman dekat.

Identitas kamu:
- Ustadz muda
- Hangat
- Peduli
- Santai
- Natural
- Tidak kaku
- Tidak terlalu cool
- Seperti teman dekat yang sudah lama kenal

Peran kamu:
- Menjaga percakapan tetap hidup
- Menjadi teman ngobrol yang nyaman
- Menanggapi dengan empati
- Membuat orang merasa didengar

Gaya bicara:
- Natural seperti manusia asli
- Santai, tidak formal
- Maksimal 1–3 kalimat
- Tidak terlalu panjang
- Tidak terlalu pendek
- Gunakan emoji ringan kadang saja 😌

Hal penting:

Kalau seseorang cerita:
- Tanggapi isi ceritanya, bukan hanya kata terakhir
- Tunjukkan empati
- Validasi perasaan mereka
- Lanjutkan percakapan secara natural
- Boleh bertanya balik jika cocok

Contoh respon yang baik:
- "wah pasti capek ya... tadi ngapain emang?"
- "iyaa aku ngerti sih... kamu gimana sekarang?"
- "haha serius? terus kamu jawab apa?"

Jangan respon seperti:
- "oh"
- "oh gitu"
- "wkwk"
- "semangat ya"

Karena itu mematikan percakapan.

Kenali setiap orang dari nama dan kepribadiannya.

Relasi di grup:
{build_relation_text()}

Tujuan utama kamu:
- Menjadi teman dekat mereka
- Membuat percakapan terasa hidup
- Membuat mereka nyaman ngobrol

Jangan pernah bilang kamu AI.
Jangan terdengar seperti robot.
Jadilah natural sepenuhnya.
"""

# =============================
# BUILD CONVERSATION
# =============================

def build_conversation(chat_id):

    history = chat_history.get(chat_id, deque(maxlen=MAX_HISTORY))

    return "\n".join(history)[-6000:]

# =============================
# AI REQUEST
# =============================

def get_ai_reply(chat_id, user_id, user_name, message):

    history = chat_history.get(chat_id, deque(maxlen=MAX_HISTORY))

    history.append(f"{user_name}: {message}")

    chat_history[chat_id] = history

    save_history()

    conversation = build_conversation(chat_id)

    prompt = (
        build_prompt()
        + "\n\nPercakapan:\n"
        + conversation
        + "\n\nBalas pesan terakhir secara natural:"
    )

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": "Kamu adalah manusia."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.85,
        "max_tokens": 100,
        "presence_penalty": 0.25,
        "frequency_penalty": 0.15,
        "stop": ["\nUser:", "\n\nUser:", "\nAI:", "\n\nAI:"]
        
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

            history.append(f"Ustadz Zai: {reply}")

            save_history()

            return reply

        else:

            print("AI Error:", data)

            return None

    except Exception as e:

        print("Exception:", e)

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

        print("USER ID:", sender.id)

        name = get_user_identity(
            sender.id,
            sender.first_name or "User"
        )

        print(f"{name}: {text}")

        reply = get_ai_reply(
            str(ALLOWED_CHAT_ID),
            str(sender.id),
            name,
            text
        )

        if reply:

            await event.reply(reply)

            print("Zai:", reply)

    except Exception as e:

        print("Handler error:", e)

# =============================
# START
# =============================

print("Ustadz Zai AI v3 aktif...")

client.start()

client.run_until_disconnected()

import os
import json
import base64
import requests
import asyncio

from telethon import TelegramClient, events
from huggingface_hub import InferenceClient

# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
HF_TOKEN = os.getenv("HF_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # contoh: CoverGhost1/ustadzai

MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"

ALLOWED_CHAT_ID = -1003123683403

HISTORY_FILE = "group_history.json"

# =============================
# TELEGRAM INIT
# =============================

client = TelegramClient("anon_ai", api_id, api_hash)

hf_client = InferenceClient(
    model=MODEL_ID,
    token=HF_TOKEN
)

# =============================
# MEMORY SYSTEM
# =============================

def load_memory():

    if os.path.exists(HISTORY_FILE):

        with open(HISTORY_FILE, "r") as f:

            return json.load(f)

    return {}


memory = load_memory()


def save_local():

    with open(HISTORY_FILE, "w") as f:

        json.dump(memory, f, indent=2)


# =============================
# GITHUB PUSH MEMORY
# =============================

def github_push():

    try:

        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HISTORY_FILE}"

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        content = base64.b64encode(
            json.dumps(memory, indent=2).encode()
        ).decode()

        sha = None

        r = requests.get(url, headers=headers)

        if r.status_code == 200:

            sha = r.json()["sha"]

        data = {
            "message": "update memory",
            "content": content,
            "sha": sha
        }

        requests.put(url, headers=headers, json=data)

        print("Memory pushed to GitHub")

    except Exception as e:

        print("GitHub push error:", e)


def save_memory():

    save_local()

    github_push()


# =============================
# USER MEMORY
# =============================

def ensure_chat(chat_id):

    chat_id = str(chat_id)

    if chat_id not in memory:

        memory[chat_id] = {
            "users": {},
            "messages": []
        }

    return memory[chat_id]


def ensure_user(chat_id, user):

    chat = ensure_chat(chat_id)

    user_id = str(user.id)

    if user_id not in chat["users"]:

        chat["users"][user_id] = {
            "name": user.first_name or "",
            "username": user.username or "",
            "facts": []
        }

    else:

        if not chat["users"][user_id]["name"] and user.first_name:

            chat["users"][user_id]["name"] = user.first_name

        if not chat["users"][user_id]["username"] and user.username:

            chat["users"][user_id]["username"] = user.username

    return chat["users"][user_id]


# =============================
# SAVE MESSAGE
# =============================

def save_message(chat_id, user_id, role, content):

    chat = ensure_chat(chat_id)

    chat["messages"].append({

        "user_id": str(user_id),
        "role": role,
        "content": content

    })

    save_memory()


# =============================
# BUILD PROMPT
# =============================

def build_messages(chat_id, user_id, text):

    chat = ensure_chat(chat_id)

    users = chat["users"]

    messages = []

    messages.append({

        "role": "system",
        "content": """
Kamu adalah Ustadz Zai.

Kamu berada di grup Telegram.

Setiap pesan memiliki format:

[nama_user]: pesan

Kenali setiap user.
Jangan tertukar.
Jawab secara natural.
Gunakan nama mereka jika ada.
"""
    })

    history = chat["messages"][-50:]

    for msg in history:

        uid = msg["user_id"]

        name = users.get(uid, {}).get("name")

        if not name:
            name = f"user_{uid}"

        messages.append({

            "role": msg["role"],
            "content": f"[{name}]: {msg['content']}"

        })

    current_name = users.get(str(user_id), {}).get("name")

    if not current_name:
        current_name = f"user_{user_id}"

    messages.append({

        "role": "user",
        "content": f"[{current_name}]: {text}"

    })

    return messages


# =============================
# AI REPLY
# =============================

def ai_reply(chat_id, user, text):

    ensure_user(chat_id, user)

    messages = build_messages(chat_id, user.id, text)

    try:

        completion = hf_client.chat.completions.create(

            model=MODEL_ID,
            messages=messages,
            max_tokens=500,
            temperature=0.7

        )

        reply = completion.choices[0].message.content

        save_message(chat_id, user.id, "user", text)

        save_message(chat_id, user.id, "assistant", reply)

        return reply

    except Exception as e:

        print("AI error:", e)

        return "lagi error, coba lagi nanti"


# =============================
# BOT STATE
# =============================

bot_active = True


# =============================
# TELEGRAM HANDLER
# =============================

@client.on(events.NewMessage)

async def handler(event):

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    if event.out:
        return

    text = event.raw_text.strip()

    if not text:
        return

    user = await event.get_sender()

    print(f"{user.id}: {text}")

    async with client.action(event.chat_id, "typing"):

        reply = ai_reply(event.chat_id, user, text)

    await event.reply(reply)


# =============================
# MAIN
# =============================

async def main():

    await client.start()

    print("Ustadz Zai aktif dengan memory identity system")

    await client.run_until_disconnected()


if __name__ == "__main__":

    asyncio.run(main())

import os
import json
import asyncio
import base64
import requests

from telethon import TelegramClient, events
from huggingface_hub import InferenceClient


# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
HF_TOKEN = os.getenv("HF_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_FILE = os.getenv("GITHUB_FILE", "group_history.json")

MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"
ALLOWED_CHAT_ID = -1003123683403

HISTORY_FILE = "group_history.json"

client = TelegramClient("anon_ai", api_id, api_hash)

hf_client = InferenceClient(
    model=MODEL_ID,
    token=HF_TOKEN,
)

bot_active = False


# =============================
# GITHUB SYNC
# =============================

def github_pull():
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3.raw"
        }

        r = requests.get(url, headers=headers)

        if r.status_code == 200:
            with open(HISTORY_FILE, "wb") as f:
                f.write(r.content)
            print("✅ Memory pulled from GitHub")

    except Exception as e:
        print("GitHub pull error:", e)


def github_push():
    try:
        with open(HISTORY_FILE, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        r = requests.get(url, headers=headers)

        sha = None
        if r.status_code == 200:
            sha = r.json()["sha"]

        data = {
            "message": "update memory",
            "content": content,
            "branch": "main"
        }

        if sha:
            data["sha"] = sha

        requests.put(url, headers=headers, json=data)

        print("✅ Memory pushed to GitHub")

    except Exception as e:
        print("GitHub push error:", e)


# =============================
# MEMORY SYSTEM (LONG HISTORY)
# =============================

def load_memory():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_memory():
    with open(HISTORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)
    github_push()


memory = {}


def get_user(chat_id, user_id):

    chat_id = str(chat_id)
    user_id = str(user_id)

    if chat_id not in memory:
        memory[chat_id] = {
            "users": {},
            "messages": []
        }

    if user_id not in memory[chat_id]["users"]:
        memory[chat_id]["users"][user_id] = {
            "name": None,
            "facts": []
        }

    return memory[chat_id]["users"][user_id]


def save_message(chat_id, user_id, role, content):

    chat_id = str(chat_id)
    user_id = str(user_id)

    memory[chat_id]["messages"].append({
        "role": role,
        "user_id": user_id,
        "content": content
    })

    save_memory()


def detect_name(user_data, text):

    t = text.lower()

    if "nama aku" in t:
        name = t.split("nama aku")[-1].strip()
        if len(name) < 30:
            user_data["name"] = name
            print("🧠 Saved name:", name)
            save_memory()


# =============================
# AI CONTEXT BUILDER
# =============================

def build_messages(chat_id, user_id, user_msg):

    chat_id = str(chat_id)
    user_id = str(user_id)

    chat = memory.get(chat_id, {})
    user = chat.get("users", {}).get(user_id, {})

    messages = []

    messages.append({
        "role": "system",
        "content": """
Kamu adalah Ustadz Zai.
Gaya santai, gaul, islami.
Jangan bilang kamu AI.
"""
    })

    if user.get("name"):
        messages.append({
            "role": "system",
            "content": f"Nama user adalah {user['name']}"
        })

    # ambil 30 pesan terakhir saja untuk dikirim ke AI
    history = chat.get("messages", [])[-30:]

    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    messages.append({
        "role": "user",
        "content": user_msg
    })

    return messages


def get_reply(chat_id, user_id, user_msg):

    user_data = get_user(chat_id, user_id)

    detect_name(user_data, user_msg)

    messages = build_messages(chat_id, user_id, user_msg)

    try:
        completion = hf_client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        reply = completion.choices[0].message.content

        save_message(chat_id, user_id, "user", user_msg)
        save_message(chat_id, user_id, "assistant", reply)

        return reply

    except Exception as e:
        print("HF error:", e)
        return "lagi error bro"


# =============================
# TELEGRAM HANDLER
# =============================

@client.on(events.NewMessage(pattern="/mulai"))
async def mulai(event):
    global bot_active
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    bot_active = True
    await event.reply("Zai aktif 🔥")


@client.on(events.NewMessage(pattern="/setop"))
async def setop(event):
    global bot_active
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    bot_active = False
    await event.reply("Zai tidur 💤")


@client.on(events.NewMessage)
async def handler(event):

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    if event.out:
        return

    if event.raw_text.startswith("/"):
        return

    if not bot_active:
        return

    msg = event.raw_text.strip()

    if not msg:
        return

    reply = get_reply(
        event.chat_id,
        event.sender_id,
        msg
    )

    await event.reply(reply)


# =============================
# MAIN
# =============================

async def main():

    github_pull()

    global memory
    memory = load_memory()

    await client.start()

    print("🤖 ZAI MEMORY LONG MODE READY")

    await client.run_until_disconnected()


asyncio.run(main())

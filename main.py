import os
import json
import asyncio
import base64
import requests

from telethon import TelegramClient, events
from collections import deque
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
# GITHUB FUNCTIONS
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

            print("✅ History pulled from GitHub")

        else:
            print("No history file yet on GitHub")

    except Exception as e:
        print("GitHub pull error:", e)


def github_push():

    try:

        with open(HISTORY_FILE, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
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

        print("✅ History pushed to GitHub")

    except Exception as e:
        print("GitHub push error:", e)


# =============================
# MEMORY SYSTEM
# =============================

def load_history():

    if os.path.exists(HISTORY_FILE):

        with open(HISTORY_FILE, "r") as f:

            raw = json.load(f)

            return {
                str(k): deque(v, maxlen=10)
                for k, v in raw.items()
            }

    return {}


def save_history(chat_history):

    history_to_save = {
        str(k): list(v)
        for k, v in chat_history.items()
    }

    with open(HISTORY_FILE, "w") as f:

        json.dump(history_to_save, f, indent=2)

    github_push()


chat_history = {}


# =============================
# PROMPT
# =============================

def build_system_prompt():

    return """
Kamu adalah Ustadz Zai.

Gaya:
- santai
- gaul
- islami
- tidak formal

Kamu punya ingatan percakapan.

Jangan bilang kamu AI.
"""


# =============================
# AI REPLY
# =============================

def get_reply(chat_id, user_msg):

    if chat_id not in chat_history:

        chat_history[chat_id] = deque(maxlen=10)

    history = chat_history[chat_id]

    messages = [

        {"role": "system", "content": build_system_prompt()}

    ]

    messages.extend(list(history))

    messages.append({

        "role": "user",
        "content": user_msg

    })

    try:

        completion = hf_client.chat.completions.create(

            model=MODEL_ID,
            messages=messages,
            temperature=0.7,
            max_tokens=500

        )

        reply = completion.choices[0].message.content

        history.append({
            "role": "user",
            "content": user_msg
        })

        history.append({
            "role": "assistant",
            "content": reply
        })

        save_history(chat_history)

        return reply

    except Exception as e:

        print("HF error:", e)

        return "error"


# =============================
# COMMANDS
# =============================

@client.on(events.NewMessage(pattern="/mulai"))
async def mulai(event):

    global bot_active

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    bot_active = True

    await event.reply("Zai aktif")


@client.on(events.NewMessage(pattern="/setop"))
async def setop(event):

    global bot_active

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    bot_active = False

    await event.reply("Zai tidur")


# =============================
# CHAT HANDLER
# =============================

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

    msg = event.raw_text

    print("MSG:", msg)

    reply = get_reply(str(ALLOWED_CHAT_ID), msg)

    await event.reply(reply)


# =============================
# MAIN
# =============================

async def main():

    github_pull()

    global chat_history
    chat_history = load_history()

    await client.start()

    print("BOT READY")

    await client.run_until_disconnected()


asyncio.run(main())

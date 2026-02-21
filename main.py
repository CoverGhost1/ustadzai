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
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
ALLOWED_CHAT_ID = -1003123683403

# =============================
# INIT TELEGRAM CLIENT
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# MEMORY SYSTEM
# =============================
HISTORY_FILE = "group_history.json"
chat_history = {}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                return {str(k): deque(v, maxlen=10) for k, v in raw.items()}
        except:
            return {}
    return {}

def save_history(chat_history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({str(k): list(v) for k, v in chat_history.items()}, f, indent=2)
    except:
        pass

chat_history = load_history()

# =============================
# PROMPT BUILDER
# =============================
def build_system_prompt():
    return """Kamu adalah ustadz muda bernama ustad zai. Santai, hangat, Ramadan vibes.
Jawab natural, singkat, jangan bilang AI, gunakan emoji seperlunya."""

# =============================
# HUGGING FACE ROUTER HANDLER
# =============================
def get_hf_reply(chat_id, user_msg):
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"User: {user_msg}")

    full_context = f"{build_system_prompt()}\n\n" + "\n".join(history) + "\nUstad Zai:"

    url = f"https://router.huggingface.co/api/models/{MODEL_ID}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "inputs": full_context,
        "parameters": {"max_new_tokens": 150, "temperature": 0.7},
        "options": {"wait_for_model": True}
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                reply_text = data[0].get("generated_text", "").split("User:")[0].strip()
            else:
                reply_text = str(data)
            history.append(f"AI: {reply_text}")
            chat_history[chat_id] = history
            save_history(chat_history)
            return reply_text
        elif res.status_code == 503:
            return "Bentar ya, lagi loading model... 🙏"
        else:
            print(f"❌ Error {res.status_code}: {res.text}")
            return None
    except Exception as e:
        print("❌ HF exception:", e)
        return None

# =============================
# TELEGRAM HANDLER
# =============================
@client.on(events.NewMessage)
async def handle_group(event):
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return

    msg = event.raw_text.strip()
    if not msg:
        return

    print(f"[GroupChat] > {msg}")

    async with client.action(event.chat_id, 'typing'):
        reply = get_hf_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)

# =============================
# RUN
# =============================
print(f"🤖 Ustadz AI (HF Router) aktif menggunakan model: {MODEL_ID}")
client.start()
client.run_until_disconnected()

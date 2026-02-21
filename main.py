import os
from telethon import TelegramClient, events
from collections import deque
import json
import requests

# =============================
# CONFIG
# =============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")  # ✅ perbaikan syntax
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
ALLOWED_CHAT_ID = -1003123683403
HISTORY_FILE = "group_history.json"

# =============================
# INIT TELEGRAM
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# MEMORY SYSTEM
# =============================
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
# HF COMPLETIONS HANDLER
# =============================
def get_hf_reply(chat_id, user_msg):
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"User: {user_msg}")

    full_prompt = f"{build_system_prompt()}\n\n" + "\n".join(history) + "\nUstad Zai:"

    # ✅ URL HF Router Completions endpoint yang benar
    url = f"https://api-inference.huggingface.co/v1/engines/{MODEL_ID}/completions"
    headers = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "inputs": full_prompt,
        "parameters": {"max_new_tokens": 150, "temperature": 0.7, "return_full_text": False},
        "options": {"wait_for_model": True}
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            data = res.json()
            reply_text = data[0].get("generated_text", "").split("User:")[0].strip()
            history.append(f"AI: {reply_text}")
            chat_history[chat_id] = history
            save_history(chat_history)
            return reply_text
        elif res.status_code == 503:
            return "Bentar ya, lagi loading model... 🙏"
        else:
            print(f"❌ HF Error {res.status_code}: {res.text}")
            return "Maaf, ada masalah dengan model. 🙏"
    except Exception as e:
        print("❌ HF exception:", e)
        return "Maaf, terjadi error saat memproses pesanmu. 🙏"

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
print(f"🤖 Ustadz AI (Mistral Instruct) aktif menggunakan model: {MODEL_ID}")
client.start()
client.run_until_disconnected()

import os
from telethon import TelegramClient, events
from openai import OpenAI
from collections import deque
import json

# =============================
# CONFIG
# =============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH"))
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
ALLOWED_CHAT_ID = -1003123683403
HISTORY_FILE = "group_history.json"

# =============================
# INIT TELEGRAM
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# INIT HF SDK (Router)
# =============================
hf_client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN
)

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
# HF SDK HANDLER
# =============================
def get_hf_reply(chat_id, user_msg):
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"User: {user_msg}")

    # Bangun messages sesuai SDK
    messages = [
        {"role": "system", "content": build_system_prompt()},
    ]
    for msg in history:
        if msg.startswith("User:"):
            messages.append({"role": "user", "content": msg.replace("User: ","")})
        elif msg.startswith("AI:"):
            messages.append({"role": "assistant", "content": msg.replace("AI: ","")})

    messages.append({"role": "user", "content": user_msg})

    try:
        completion = hf_client.chat.completions.create(
            model=MODEL_ID,
            messages=messages
        )
        reply_text = completion.choices[0].message.content.strip()
        history.append(f"AI: {reply_text}")
        chat_history[chat_id] = history
        save_history(chat_history)
        return reply_text
    except Exception as e:
        print("❌ HF exception:", e)
        return "Maaf, ada masalah saat memproses pesanmu. 🙏"

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
print(f"🤖 Ustadz AI (HF SDK Router) aktif menggunakan model: {MODEL_ID}")
client.start()
client.run_until_disconnected()

from telethon import TelegramClient, events
import requests
import json
import os
from collections import deque

# =============================
# CONFIG (PAKAI ENV VARIABLE)
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

# GANTI INI: Token Hugging Face (dapat di hf.co/settings/tokens)
HF_TOKEN = os.getenv("HF_TOKEN") 

# MODEL PILIHAN (Bisa diganti Llama-3 atau Mistral)
# Contoh: "meta-llama/Meta-Llama-3-8B-Instruct" atau "mistralai/Mistral-7B-Instruct-v0.2"
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"

ALLOWED_CHAT_ID = -1003123683403  

# =============================
# INIT TELETHON
# =============================

client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# MEMORY SYSTEM
# =============================

HISTORY_FILE = "group_history.json"

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
    return """Kamu adalah ustadz muda bernama ustad zai. Kamu lagi nongkrong di grup Telegram.
Karakter: Santai, humble, hangat, gak kaku, gaya bahasa anak muda tapi tetap sopan (Ramadan vibes).
Tugas: Tanggapi obrolan dengan singkat, natural, dan jangan bilang kamu AI. Gunakan emoji seperlunya."""

# =============================
# HUGGING FACE HANDLER
# =============================

def get_hf_reply(chat_id, user_msg):
    """
    Mengirim prompt ke Hugging Face Router API (Mistral-7B-Instruct)
    dan mengambil balasan AI. History chat disimpan untuk konteks.
    """
    # Ambil history chat atau buat baru
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"User: {user_msg}")

    # Bangun prompt lengkap
    full_context = f"{build_system_prompt()}\n\n"
    for msg in history:
        full_context += f"{msg}\n"
    full_context += "Ustad Zai:"

    # Endpoint Router HF terbaru (Completions API)
    url = f"https://api-inference.huggingface.co/v1/engines/{MODEL_ID}/completions"

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": full_context,
        "parameters": {
            "max_new_tokens": 150,
            "temperature": 0.7,
            "return_full_text": False
        },
        "options": {
            "wait_for_model": True  # Supaya gak error pas model lagi loading
        }
    }

    try:
        # Request via session
        res = session.post(url, headers=headers, json=payload)

        if res.status_code == 200:
            data = res.json()
            # Router Completions API biasanya balikin text di 'generated_text'
            if "generated_text" in data[0]:
                reply_text = data[0]['generated_text'].split("User:")[0].strip()
            else:
                # fallback jika struktur berbeda
                reply_text = str(data).strip()
            
            # Simpan history
            history.append(f"AI: {reply_text}")
            chat_history[chat_id] = history
            save_history(chat_history)
            return reply_text

        elif res.status_code == 503:
            return "Bentar ya, lagi loading memorinya... Coba chat lagi sebentar. 🙏"
        else:
            print(f"❌ Error {res.status_code}: {res.text}")
            return None

    except Exception as e:
        print("❌ HF exception:", e)
        return None

# =============================
# MAIN GROUP HANDLER
# =============================

@client.on(events.NewMessage)
async def handle_group(event):
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return

    msg = event.raw_text.strip()
    if not msg:
        return

    print(f"[GroupChat] > {msg}")

    # Kirim status "typing" biar lebih natural
    async with client.action(event.chat_id, 'typing'):
        reply = get_hf_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)

# =============================
# RUN
# =============================

print(f"🤖 Ustadz AI (HF Version) aktif menggunakan model: {MODEL_ID}")
client.start()
client.run_until_disconnected()

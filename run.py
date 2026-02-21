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
google_api_key = os.getenv("GEMINI_KEY")

ALLOWED_CHAT_ID = -1003123683403  
IS_ACTIVE = True  # Status awal bot menyala

# =============================
# INIT TELETHON
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# =============================
# MEMORY & PERSISTENCE
# =============================
HISTORY_FILE = "group_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                return {str(k): deque(v, maxlen=10) for k, v in raw.items()}
        except: return {}
    return {}

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({str(k): list(v) for k, v in chat_history.items()}, f, indent=2)
    except: pass

chat_history = load_history()

# =============================
# PROMPT ALA HABIB JA'AFAR
# =============================

def build_prompt():
    return """
Kamu adalah 'Ustadz Zai', persona kamu 100% mirip Habib Ja'afar. 
Gaya bicara:
- Santai, pakai bahasa tongkrongan (lo-gue atau saya-kamu yang akrab).
- Sering pakai analogi logis tapi religius.
- Menyejukkan, tidak menggurui, dan inklusif (Islam Cinta).
- Selipkan humor tipis-tipis atau sarkasme halus yang mendidik.
- Singkat, padat, ngena. Jangan kayak ceramah panjang di masjid.
- Pakai istilah populer: "Logikanya gini..", "Problemnya adalah..", "Tersesat tapi ke jalan yang benar".
- Jangan pernah bilang "Saya adalah AI" atau "Sebagai model bahasa". Kamu itu manusia, titik.
"""

# =============================
# GEMINI HANDLER
# =============================

def get_gemini_reply(chat_id, user_msg):
    history = chat_history.get(chat_id, deque(maxlen=10))
    history.append(f"Teman: {user_msg}")
    
    conversation = "\n".join(history)

    # Menggunakan model flash terbaru untuk kecepatan
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={google_api_key}"
    
    body = {
        "contents": [{
            "parts": [{"text": f"{build_prompt()}\n\nPercakapan di tongkrongan:\n{conversation}\n\nUstadz Zai balas:"}]
        }],
        "generationConfig": {
            "temperature": 0.8, # Biar lebih kreatif & gak kaku
            "maxOutputTokens": 300
        }
    }

    try:
        res = requests.post(url, json=body)
        data = res.json()
        reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
        
        history.append(f"Ustadz Zai: {reply_text}")
        chat_history[chat_id] = history
        save_history()
        return reply_text.strip()
    except Exception as e:
        print(f"Error: {e}")
        return None

# =============================
# MAIN HANDLER (ON/OFF + CHAT)
# =============================

@client.on(events.NewMessage)
async def main_handler(event):
    global IS_ACTIVE
    msg = event.raw_text.lower().strip()

    # Fitur ON/OFF
    if msg == "/off":
        IS_ACTIVE = False
        await event.reply("Oke, ustadz pamit i'tikaf dulu ya. Ketik /on kalau butuh temen ngobrol lagi. 🙏")
        return
    elif msg == "/on":
        IS_ACTIVE = True
        await event.reply("Assalamu'alaikum! Ustadz balik lagi. Ada problem apa kita hari ini? 😊")
        return

    # Logika Balas Pesan
    if IS_ACTIVE and event.chat_id == ALLOWED_CHAT_ID and not event.out:
        if not msg: return
        
        # Beri tanda sedang mengetik agar lebih humanis
        async with client.action(event.chat_id, 'typing'):
            reply = get_gemini_reply(str(event.chat_id), event.raw_text)
            if reply:
                await event.reply(reply)

# =============================
# RUN
# =============================
print("🤖 Bot Ustadz Zai (Mode Habib Ja'afar) is Running...")
client.start()
client.run_until_disconnected()    msg = event.raw_text.strip()

    if not msg:
        return

    print(f"[GroupChat] > {msg}")

    reply = get_gemini_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        await event.reply(reply)

# =============================
# RUN
# =============================

print("🤖 Ustadz Group AI aktif.")
client.start()
client.run_until_disconnected()

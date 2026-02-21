import os
from telethon import TelegramClient, events
from collections import deque
import json
from huggingface_hub import InferenceClient

# =============================
# CONFIG
# =============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
HF_TOKEN = os.getenv("HF_TOKEN")

# Note: This model ID format might need adjustment
# For Novita AI, you might need a different endpoint
MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"  # Using a more standard model for testing
ALLOWED_CHAT_ID = -1003123683403
HISTORY_FILE = "group_history.json"

# =============================
# INIT TELEGRAM & HF CLIENT
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# Initialize HF client with proper endpoint if needed
hf_client = InferenceClient(
    model=MODEL_ID,
    token=HF_TOKEN,
    # If using Novita AI, you might need:
    # base_url="https://api.novita.ai/v1"
)

# =============================
# MEMORY SYSTEM
# =============================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                # Convert list back to deque with maxlen=10
                return {str(k): deque(v, maxlen=10) for k, v in raw.items()}
        except Exception as e:
            print(f"Error loading history: {e}")
            return {}
    return {}

def save_history(chat_history):
    try:
        # Convert deque to list for JSON serialization
        history_to_save = {str(k): list(v) for k, v in chat_history.items()}
        with open(HISTORY_FILE, "w") as f:
            json.dump(history_to_save, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

chat_history = load_history()

# =============================
# PROMPT BUILDER
# =============================
def build_system_prompt():
    return """Kamu adalah Ustadz muda bernama Ustad Zai, gaul dan santai. 
Kadang plenger, bercanda ringan, tapi tetap islami. 
Gunakan bahasa sehari-hari, emoji seperlunya, dan gaya ngobrol santai.
Jawab singkat tapi jelas, bisa kasih motivasi, nasehat, atau info islami.
Jangan sebut kalau kamu AI, jangan terlalu formal."""

# =============================
# HF CHAT HANDLER
# =============================
def get_hf_reply(chat_id, user_msg):
    if chat_id not in chat_history:
        chat_history[chat_id] = deque(maxlen=10)
    
    history = chat_history[chat_id]
    
    messages = [{"role": "system", "content": build_system_prompt()}]
    
    for msg in list(history):
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_msg})

    try:
        completion = hf_client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        if hasattr(completion, 'choices') and len(completion.choices) > 0:
            reply_text = completion.choices[0].message.content
        else:
            reply_text = str(completion)

        # Sentuhan gaul tambahan
        gaul_emoji = ["😎", "😉", "😁", "✨", "🌙"]
        if random.random() < 0.3:  # 30% chance nambah emoji plenger
            reply_text += " " + random.choice(gaul_emoji)

        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": reply_text})
        
        save_history(chat_history)
        
        return reply_text

    except Exception as e:
        print(f"❌ HF exception: {type(e).__name__}: {e}")
        return "Maaf, bro, ada error pas memproses pesanmu 😅. Coba lagi ya."
# =============================
# TELEGRAM HANDLER
# =============================
@client.on(events.NewMessage)
async def handle_group(event):
    # Check if it's the allowed chat and not a message from the bot itself
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return

    msg = event.raw_text.strip()
    if not msg:
        return

    print(f"[GroupChat] From {event.sender_id}: {msg}")

    # Show typing indicator
    async with client.action(event.chat_id, 'typing'):
        reply = get_hf_reply(str(ALLOWED_CHAT_ID), msg)

    if reply:
        try:
            await event.reply(reply)
            print(f"[Bot] Replied: {reply[:50]}...")
        except Exception as e:
            print(f"Error sending reply: {e}")

# =============================
# STARTUP MESSAGE
# =============================
async def main():
    await client.start()
    print(f"🤖 Ustadz AI aktif menggunakan model: {MODEL_ID}")
    print(f"✅ Hanya merespon di chat ID: {ALLOWED_CHAT_ID}")
    await client.run_until_disconnected()

# =============================
# RUN
# =============================
if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")

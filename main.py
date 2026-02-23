import os
import asyncio
from telethon import TelegramClient, events
from huggingface_hub import InferenceClient
import psycopg2

# =============================
# CONFIG
# =============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
HF_TOKEN = os.getenv("HF_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"
ALLOWED_CHAT_ID = -1003123683403

# =============================
# INIT TELEGRAM & HF
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

hf_client = InferenceClient(
    model=MODEL_ID,
    token=HF_TOKEN
)

# =============================
# DATABASE CONNECT
# =============================
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

# create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS history (
    id SERIAL PRIMARY KEY,
    chat_id TEXT,
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

# =============================
# DEFAULT USERS
# =============================
def save_user(user_id, name):
    cursor.execute(
        "INSERT INTO users (user_id, name) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
        (str(user_id), name)
    )

# manual known users
save_user("8229304441", "Rifkyy")
save_user("6876331769", "Adell")

def get_user_name(user_id):
    cursor.execute(
        "SELECT name FROM users WHERE user_id=%s",
        (str(user_id),)
    )
    result = cursor.fetchone()
    if result:
        return result[0]
    return "akhi"

# =============================
# HISTORY SYSTEM
# =============================
def save_message(chat_id, user_id, role, content):
    cursor.execute(
        "INSERT INTO history (chat_id, user_id, role, content) VALUES (%s, %s, %s, %s)",
        (str(chat_id), str(user_id), role, content)
    )

def get_last_messages(chat_id, limit=10):
    cursor.execute(
        """
        SELECT role, content FROM history
        WHERE chat_id=%s
        ORDER BY id DESC
        LIMIT %s
        """,
        (str(chat_id), limit)
    )
    rows = cursor.fetchall()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]

# =============================
# SYSTEM PROMPT
# =============================
def build_system_prompt(user_name):
    return f"""
Kamu adalah Ustadz muda bernama Ustad Zai, gaul dan santai.
Kadang plenger, bercanda ringan, tapi tetap islami.
Gunakan bahasa sehari-hari, emoji seperlunya.
Jawab singkat tapi jelas.
Jangan bilang kamu AI.
Nama yang sedang berbicara adalah {user_name}. Panggil dia dengan namanya.
"""

# =============================
# BOT STATE
# =============================
bot_active = False

# =============================
# COMMANDS
# =============================
@client.on(events.NewMessage(pattern='/mulai'))
async def start_bot(event):
    global bot_active
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return
    bot_active = True
    await event.reply("✅ Ustad Zai aktif! Silakan tanya apa aja 🤗")

@client.on(events.NewMessage(pattern='/setop'))
async def stop_bot(event):
    global bot_active
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return
    bot_active = False
    await event.reply("⏸️ Ustad Zai istirahat dulu ya 👋")

# =============================
# MAIN HANDLER
# =============================
@client.on(events.NewMessage)
async def handle_group(event):
    global bot_active

    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return

    if event.raw_text.startswith('/'):
        return

    if not bot_active:
        return

    sender = await event.get_sender()
    user_id = sender.id
    user_name = sender.first_name or "akhi"

    # save user to DB
    save_user(user_id, user_name)

    msg = event.raw_text.strip()
    if not msg:
        return

    print(f"[{user_name}] {msg}")

    # get history
    history = get_last_messages(ALLOWED_CHAT_ID)

    messages = [
        {"role": "system", "content": build_system_prompt(user_name)}
    ]

    messages.extend(history)
    messages.append({"role": "user", "content": msg})

    async with client.action(event.chat_id, 'typing'):
        try:
            completion = hf_client.chat.completions.create(
                model=MODEL_ID,
                messages=messages,
                max_tokens=400,
                temperature=0.7
            )

            reply = completion.choices[0].message.content

            # save conversation
            save_message(ALLOWED_CHAT_ID, user_id, "user", msg)
            save_message(ALLOWED_CHAT_ID, user_id, "assistant", reply)

            await event.reply(reply)

        except Exception as e:
            print("HF ERROR:", e)
            await event.reply("Maaf lagi error dikit 😅 coba lagi nanti ya.")

# =============================
# START
# =============================
async def main():
    await client.start()
    print("🤖 Ustad Zai aktif dengan PostgreSQL memory")
    print("Bot dalam keadaan OFF, ketik /mulai")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

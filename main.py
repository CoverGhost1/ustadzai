import os
import asyncio
import psycopg2
from telethon import TelegramClient, events
from openai import OpenAI

# =============================
# CONFIG
# =============================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

ALLOWED_CHAT_ID = -1002397166537  # Ganti sesuai grup lu

# =============================
# FORCED USER NAMES
# =============================

FORCED_NAMES = {
    "8229304441": "Rifkyy",
    "6876331769": "Adell"
}

# =============================
# INIT CLIENT
# =============================

client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
openai = OpenAI(api_key=OPENAI_API_KEY)

# =============================
# DATABASE CONNECT
# =============================

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

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
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memories (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE,
    value TEXT
)
""")

# =============================
# USER SYSTEM
# =============================

def save_user(user_id, name):
    cursor.execute(
        "INSERT INTO users (user_id, name) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name",
        (str(user_id), name)
    )

def get_user_name(user_id):
    cursor.execute(
        "SELECT name FROM users WHERE user_id=%s",
        (str(user_id),)
    )
    result = cursor.fetchone()
    if result:
        return result[0]
    return "akhi"

def get_forced_name(user_id, telegram_name=None):
    uid = str(user_id)

    if uid in FORCED_NAMES:
        return FORCED_NAMES[uid]

    name = get_user_name(uid)
    if name != "akhi":
        return name

    return telegram_name or "akhi"

# =============================
# MEMORY SYSTEM
# =============================

def save_memory(key, value):
    cursor.execute(
        "INSERT INTO memories (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, value)
    )

def get_memory(key):
    cursor.execute(
        "SELECT value FROM memories WHERE key=%s",
        (key,)
    )
    result = cursor.fetchone()
    if result:
        return result[0]
    return None

# =============================
# HISTORY SYSTEM
# =============================

def save_message(chat_id, role, content):
    cursor.execute(
        "INSERT INTO history (chat_id, role, content) VALUES (%s, %s, %s)",
        (str(chat_id), role, content)
    )

def get_last_messages(chat_id, limit=50):
    cursor.execute("""
        SELECT role, content FROM history
        WHERE chat_id=%s
        ORDER BY id DESC
        LIMIT %s
    """, (str(chat_id), limit))
    
    rows = cursor.fetchall()
    rows.reverse()
    
    return [{"role": r[0], "content": r[1]} for r in rows]

# =============================
# SYSTEM PROMPT
# =============================

def build_system_prompt(user_name):
    rifky_rel = get_memory("relationship_Rifkyy") or "Rifkyy pacarnya Adell."
    adell_rel = get_memory("relationship_Adell") or "Adell pacarnya Rifkyy."

    return f"""
Kamu adalah Ustad Zai.
Gaul, santai, kadang plenger, suka bercanda.
Tapi tetap sopan dan islami.
Jangan pernah bilang kamu AI.
Jawab singkat, natural, manusia banget.

Info penting:
{rifky_rel}
{adell_rel}

Sekarang yang bicara adalah {user_name}.
Panggil dia dengan namanya.
"""

# =============================
# BOT STATUS
# =============================

bot_active = False

@client.on(events.NewMessage(pattern="/mulai"))
async def start_bot(event):
    global bot_active
    bot_active = True
    await event.reply("🔥 Ustad Zai aktif. Siap nemenin kalian.")
    print("Bot ON")

@client.on(events.NewMessage(pattern="/stop"))
async def stop_bot(event):
    global bot_active
    bot_active = False
    await event.reply("Bot dimatikan.")
    print("Bot OFF")

# =============================
# MAIN HANDLER
# =============================

@client.on(events.NewMessage)
async def handler(event):
    global bot_active

    if not bot_active:
        return

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    sender = await event.get_sender()
    user_id = sender.id
    telegram_name = sender.first_name or "akhi"

    user_name = get_forced_name(user_id, telegram_name)
    save_user(user_id, user_name)

    msg = event.raw_text

    print(f"[{user_name}] {msg}")

    # Save user message
    save_message(event.chat_id, "user", f"{user_name}: {msg}")

    # Build prompt
    history = get_last_messages(event.chat_id, 50)

    messages = [
        {"role": "system", "content": build_system_prompt(user_name)}
    ] + history

    # OpenAI Response
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    reply = response.choices[0].message.content

    save_message(event.chat_id, "assistant", reply)

    await event.reply(reply)

# =============================
# RUN
# =============================

print("🤖 Ustad Zai aktif dengan PostgreSQL memory")
client.run_until_disconnected()

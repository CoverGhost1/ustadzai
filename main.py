import os
import json
import psycopg2
from telethon import TelegramClient, events
from huggingface_hub import InferenceClient

# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
hf_token = os.getenv("HF_TOKEN")
database_url = os.getenv("DATABASE_URL")

ALLOWED_CHAT_ID = -1003123683403

client = TelegramClient("anon_ai", api_id, api_hash)
hf = InferenceClient(token=hf_token)

# =============================
# FORCED NAMES
# =============================

FORCED_NAMES = {
    "8229304441": "Rifkyy",
    "6876331769": "Adell"
}

# =============================
# POSTGRES CONNECT
# =============================

conn = psycopg2.connect(database_url)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id TEXT,
    user_id TEXT,
    name TEXT,
    message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# =============================
# USER SYSTEM
# =============================

def get_user_name(user_id):

    uid = str(user_id)

    # forced name priority
    if uid in FORCED_NAMES:
        return FORCED_NAMES[uid]

    cur.execute(
        "SELECT name FROM users WHERE user_id=%s",
        (uid,)
    )

    row = cur.fetchone()

    if row:
        return row[0]

    return "akhi"


def save_user(user_id, name):

    uid = str(user_id)

    cur.execute("""
    INSERT INTO users (user_id, name)
    VALUES (%s,%s)
    ON CONFLICT (user_id)
    DO UPDATE SET name=EXCLUDED.name
    """, (uid, name))

    conn.commit()

# =============================
# MEMORY SYSTEM
# =============================

def save_message(chat_id, user_id, name, message):

    cur.execute("""
    INSERT INTO messages
    (chat_id, user_id, name, message)
    VALUES (%s,%s,%s,%s)
    """, (str(chat_id), str(user_id), name, message))

    conn.commit()


def get_last_messages(chat_id, limit=100):

    cur.execute("""
    SELECT name, message FROM messages
    WHERE chat_id=%s
    ORDER BY id DESC
    LIMIT %s
    """, (str(chat_id), limit))

    rows = cur.fetchall()

    rows.reverse()

    history = ""

    for name, msg in rows:
        history += f"{name}: {msg}\n"

    return history


# =============================
# AI PROMPT
# =============================

def build_prompt(user_name, history, user_message):

    return f"""
Kamu adalah Ustadz Zai.

Kamu ngobrol santai, seru, hangat.

Kamu ingat semua orang.

Orang di grup:
- Rifkyy
- Adell

Riwayat chat:
{history}

Sekarang {user_name} berkata:
{user_message}

Balas dengan natural, santai, dan hidup.
"""


# =============================
# AI RESPONSE
# =============================

def generate_ai(prompt):

    try:

        response = hf.chat.completions.create(

            model="Qwen/Qwen2.5-72B-Instruct",

            messages=[
                {"role": "user", "content": prompt}
            ],

            temperature=0.7,
            max_tokens=300
        )

        return response.choices[0].message.content

    except Exception as e:

        return f"Error AI: {e}"


# =============================
# TELEGRAM EVENT
# =============================

@client.on(events.NewMessage)
async def handler(event):

    if event.chat_id != ALLOWED_CHAT_ID:
        return

    sender = await event.get_sender()

    user_id = sender.id

    telegram_name = sender.first_name or "akhi"

    user_name = get_user_name(user_id)

    save_user(user_id, user_name)

    message = event.raw_text

    print(f"[{user_name}] {message}")

    save_message(
        event.chat_id,
        user_id,
        user_name,
        message
    )

    history = get_last_messages(event.chat_id, 100)

    prompt = build_prompt(
        user_name,
        history,
        message
    )

    ai_reply = generate_ai(prompt)

    save_message(
        event.chat_id,
        "AI",
        "Zai",
        ai_reply
    )

    await event.reply(ai_reply)


# =============================
# START
# =============================

print("🤖 Ustad Zai aktif dengan HuggingFace + PostgreSQL + Memory + Forced Names")

client.start()

client.run_until_disconnected()

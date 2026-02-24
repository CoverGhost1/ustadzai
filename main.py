import os
import json
import psycopg2
import asyncio
import traceback
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from huggingface_hub import InferenceClient

# =============================
# CONFIG
# =============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
database_url = os.getenv("DATABASE_URL")

# Initial HF Tokens
HF_TOKENS = [
    os.getenv("HF_TOKEN_1"),
    os.getenv("HF_TOKEN_2"),
    os.getenv("HF_TOKEN_3"),
]

# Filter out any None values
HF_TOKENS = [token for token in HF_TOKENS if token is not None]

ALLOWED_CHAT_ID = -1003123683403  # Ganti dengan ID grup Anda
ADMIN_IDS = [8229304441, 6876331769]  # ID admin

# =============================
# SMART REPLY CONFIG
# =============================
COOLDOWN_SECONDS = 2.5  # Nunggu 2.5 detik buat collect multiple messages
MAX_COLLECT_MESSAGES = 3  # Max pesan yang dikumpulin sebelum reply

# =============================
# GAUL WORDS & EXPRESSIONS
# =============================

GAUL_WORDS = [
    "wkwk", "wkwkwk", "waduh", "anjir", "sih", "deh", "dong", "yah", "nah",
    "gitu", "gini", "banget", "bgt", "wkwk", "wkwkwkwk", "eh", "loh", "lho",
    "sumpah", "astaga", "gila", "serius", "ya ampun", "aduh", "duh", "nah loh",
    "masa sih", "seriusan", "btw", "ngomong-ngomong", "oki", "ok", "sip",
    "mantap", "mantul", "gas", "gaskeun", "santuy", "santai", "gaes", "guys"
]

# =============================
# INITIALIZE CLIENT
# =============================
client = TelegramClient("anon_ai", api_id, api_hash)

# =============================
# DATABASE CONNECTION
# =============================

class DatabaseManager:
    def __init__(self, database_url):
        self.database_url = database_url
        self.conn = None
        self.cur = None
        self.connect()
        self.init_tables()
        self.update_gaul_settings()
    
    def connect(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            
            self.conn = psycopg2.connect(self.database_url)
            self.conn.autocommit = False
            self.cur = self.conn.cursor()
            print("✅ Database connected")
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            raise e
    
    def init_tables(self):
        try:
            # Tabel users
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel messages - DENGAN REPLY CONTEXT LENGKAP
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id TEXT,
                user_id TEXT,
                name TEXT,
                message TEXT,
                reply_to_msg_id INTEGER,
                reply_to_name TEXT,
                reply_to_message TEXT,
                is_sticker BOOLEAN DEFAULT FALSE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel untuk menyimpan HF tokens
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS hf_tokens (
                id SERIAL PRIMARY KEY,
                token TEXT UNIQUE,
                token_prefix TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                failures INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
            """)

            # Tabel untuk log API usage
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id SERIAL PRIMARY KEY,
                token_prefix TEXT,
                success BOOLEAN,
                error_message TEXT,
                response_time FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel untuk settings
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel untuk bot status
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_status (
                id INTEGER PRIMARY KEY DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                auto_reply BOOLEAN DEFAULT FALSE,
                updated_by TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            self.conn.commit()
            print("✅ Database tables initialized")
            
        except Exception as e:
            print(f"❌ Table initialization error: {e}")
            self.conn.rollback()
    
    def update_gaul_settings(self):
        try:
            settings = [
                ('temperature', '0.95'),
                ('max_response_tokens', '400'),
                ('max_history', '50'),
                ('top_p', '0.95'),
                ('presence_penalty', '0.7'),
                ('frequency_penalty', '0.7'),
                ('auto_reply_mode', 'false'),
                ('current_token_index', '0'),
                ('cooldown_seconds', '2.5'),
                ('max_collect_messages', '3')
            ]
            
            for key, value in settings:
                self.cur.execute("""
                    INSERT INTO settings (key, value) 
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE 
                    SET value = EXCLUDED.value
                """, (key, value))
            
            self.conn.commit()
            print("✅ GAUL mode settings applied!")
            
        except Exception as e:
            print(f"Error updating settings: {e}")
            self.conn.rollback()
    
    def execute(self, query, params=None, commit=False, fetch=False):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not self.conn or self.conn.closed:
                    self.connect()
                
                if params:
                    self.cur.execute(query, params)
                else:
                    self.cur.execute(query)
                
                if commit:
                    self.conn.commit()
                
                if fetch:
                    if fetch == "one":
                        return self.cur.fetchone()
                    elif fetch == "all":
                        return self.cur.fetchall()
                    elif fetch == "value":
                        row = self.cur.fetchone()
                        return row[0] if row else None
                
                return True
                
            except psycopg2.OperationalError as e:
                print(f"Database operational error: {e}")
                self.connect()
                retry_count += 1
                
            except psycopg2.errors.InFailedSqlTransaction:
                print("Failed transaction, rolling back...")
                self.conn.rollback()
                retry_count += 1
                
            except Exception as e:
                print(f"Database error: {e}")
                try:
                    self.conn.rollback()
                except:
                    pass
                raise e
        
        raise Exception("Max retries reached")
    
    def get_setting(self, key, default=None):
        try:
            try:
                self.conn.rollback()
            except:
                pass
            value = self.execute(
                "SELECT value FROM settings WHERE key = %s",
                (key,),
                fetch="value"
            )
            return value if value is not None else default
        except Exception as e:
            print(f"Error getting setting {key}: {e}")
            return default
    
    def close(self):
        try:
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()
        except:
            pass

db = DatabaseManager(database_url)

# =============================
# LOAD TOKENS
# =============================

def load_tokens_from_db():
    try:
        rows = db.execute(
            "SELECT token FROM hf_tokens WHERE is_active = TRUE ORDER BY id",
            fetch="all"
        )
        return [row[0] for row in rows] if rows else []
    except Exception as e:
        print(f"Error loading tokens: {e}")
        return []

HF_TOKENS = load_tokens_from_db()

# =============================
# BOT STATUS
# =============================

def get_bot_status():
    try:
        try:
            db.conn.rollback()
        except:
            pass
        row = db.execute(
            "SELECT is_active, auto_reply FROM bot_status WHERE id = 1",
            fetch="one"
        )
        if row:
            return {"is_active": row[0], "auto_reply": row[1]}
        return {"is_active": True, "auto_reply": False}
    except Exception as e:
        print(f"Error get_bot_status: {e}")
        return {"is_active": True, "auto_reply": False}

def set_bot_active(active, updated_by):
    try:
        db.execute(
            """
            UPDATE bot_status 
            SET is_active = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE id = 1
            """,
            (active, str(updated_by)),
            commit=True
        )
        return get_bot_status()
    except Exception as e:
        print(f"Error set_bot_active: {e}")
        return get_bot_status()

def set_auto_reply_mode(mode, updated_by):
    try:
        db.execute(
            """
            UPDATE bot_status 
            SET auto_reply = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE id = 1
            """,
            (mode, str(updated_by)),
            commit=True
        )
        
        db.execute(
            """
            UPDATE settings 
            SET value = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE key = 'auto_reply_mode'
            """,
            (str(mode).lower(),),
            commit=True
        )
        
        return get_bot_status()
    except Exception as e:
        print(f"Error set_auto_reply_mode: {e}")
        return get_bot_status()

# =============================
# AI CLIENT MANAGER
# =============================

class AIClientManager:
    def __init__(self):
        self.current_token_index = 0
        self.load_settings()
        
    def load_settings(self):
        try:
            value = db.get_setting('current_token_index', '0')
            self.current_token_index = int(value)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def save_settings(self):
        try:
            db.execute(
                "UPDATE settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = 'current_token_index'",
                (str(self.current_token_index),),
                commit=True
            )
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get_active_tokens(self):
        try:
            rows = db.execute(
                "SELECT token FROM hf_tokens WHERE is_active = TRUE ORDER BY id",
                fetch="all"
            )
            return [row[0] for row in rows] if rows else []
        except Exception as e:
            print(f"Error getting active tokens: {e}")
            return []
    
    def get_current_client(self):
        tokens = self.get_active_tokens()
        if not tokens:
            return None
        
        if self.current_token_index >= len(tokens):
            self.current_token_index = 0
            self.save_settings()
        
        token = tokens[self.current_token_index]
        
        try:
            db.execute(
                "UPDATE hf_tokens SET last_used = CURRENT_TIMESTAMP WHERE token = %s",
                (token,),
                commit=True
            )
        except Exception as e:
            print(f"Error updating last_used: {e}")
        
        return {
            "token": token,
            "client": InferenceClient(token=token)
        }
    
    def rotate_token(self):
        tokens = self.get_active_tokens()
        if tokens:
            self.current_token_index = (self.current_token_index + 1) % len(tokens)
            self.save_settings()
            return True
        return False
    
    def mark_token_failed(self, token):
        try:
            db.execute(
                "UPDATE hf_tokens SET failures = failures + 1 WHERE token = %s",
                (token,),
                commit=True
            )
            
            failures = db.execute(
                "SELECT failures FROM hf_tokens WHERE token = %s",
                (token,),
                fetch="value"
            )
            
            if failures and failures >= 5:
                self.disable_token(token)
                return f"⚠️ Token {token[:10]}... dinonaktifkan karena 5x gagal"
            
            self.rotate_token()
            return f"🔄 Token {token[:10]}... gagal, rotate ke token berikutnya"
            
        except Exception as e:
            print(f"Error marking token failed: {e}")
            return f"❌ Error: {e}"
    
    def mark_token_success(self, token):
        try:
            db.execute(
                "UPDATE hf_tokens SET failures = 0, last_used = CURRENT_TIMESTAMP WHERE token = %s",
                (token,),
                commit=True
            )
        except Exception as e:
            print(f"Error marking token success: {e}")
    
    def add_token(self, token, added_by, notes=""):
        try:
            db.execute(
                """
                INSERT INTO hf_tokens (token, token_prefix, added_by, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (token) 
                DO UPDATE SET is_active = TRUE, failures = 0
                """,
                (token, token[:10], str(added_by), notes),
                commit=True
            )
            return True, "Token berhasil ditambahkan"
        except Exception as e:
            return False, str(e)
    
    def remove_token(self, token_prefix):
        try:
            db.execute(
                "UPDATE hf_tokens SET is_active = FALSE WHERE token_prefix = %s OR token LIKE %s",
                (token_prefix, f"{token_prefix}%"),
                commit=True
            )
            
            affected = db.cur.rowcount
            
            if affected > 0:
                current = self.get_current_client()
                if current and current['token'].startswith(token_prefix):
                    self.rotate_token()
                return True, f"{affected} token dinonaktifkan"
            return False, "Token tidak ditemukan"
            
        except Exception as e:
            return False, str(e)
    
    def disable_token(self, token):
        try:
            db.execute(
                "UPDATE hf_tokens SET is_active = FALSE WHERE token = %s",
                (token,),
                commit=True
            )
        except Exception as e:
            print(f"Error disabling token: {e}")
    
    def get_token_list(self):
        try:
            return db.execute(
                """
                SELECT 
                    token_prefix,
                    is_active,
                    failures,
                    last_used,
                    added_by,
                    added_at,
                    notes
                FROM hf_tokens 
                ORDER BY is_active DESC, id
                """,
                fetch="all"
            ) or []
        except Exception as e:
            print(f"Error getting token list: {e}")
            return []
    
    def get_stats(self):
        try:
            total, active, problematic = db.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN is_active AND failures > 0 THEN 1 ELSE 0 END) as problematic
                FROM hf_tokens
                """,
                fetch="one"
            ) or (0, 0, 0)
            
            requests = db.execute(
                """
                SELECT 
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as success,
                    AVG(response_time) as avg_response
                FROM api_usage 
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                """,
                fetch="one"
            ) or (0, 0, 0)
            
            return {
                "total_tokens": total or 0,
                "active_tokens": active or 0,
                "problematic": problematic or 0,
                "requests_24h": requests[0] or 0,
                "success_24h": requests[1] or 0,
                "avg_response": requests[2] or 0
            }
            
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {
                "total_tokens": 0,
                "active_tokens": 0,
                "problematic": 0,
                "requests_24h": 0,
                "success_24h": 0,
                "avg_response": 0
            }

ai_manager = AIClientManager()

# =============================
# USER SYSTEM
# =============================

FORCED_NAMES = {
    "8229304441": "Rifkyy",
    "6876331769": "Adell"
}

def get_user_name(user_id):
    uid = str(user_id)
    if uid in FORCED_NAMES:
        return FORCED_NAMES[uid]
    
    try:
        name = db.execute(
            "SELECT name FROM users WHERE user_id=%s",
            (uid,),
            fetch="value"
        )
        return name if name else "akhi"
    except Exception as e:
        print(f"Error get_user_name: {e}")
        return "akhi"

def save_user(user_id, name):
    uid = str(user_id)
    try:
        db.execute(
            """
            INSERT INTO users (user_id, name)
            VALUES (%s,%s)
            ON CONFLICT (user_id)
            DO UPDATE SET name=EXCLUDED.name
            """,
            (uid, name),
            commit=True
        )
    except Exception as e:
        print(f"Error save_user: {e}")

def is_admin(user_id):
    return str(user_id) in [str(admin) for admin in ADMIN_IDS]

# =============================
# SUPER CONTEXT MEMORY
# =============================

def save_message(chat_id, user_id, name, message, reply_to_msg_id=None, is_sticker=False):
    """Simpan pesan dengan informasi reply yang LENGKAP"""
    try:
        reply_to_name = None
        reply_to_message = None
        
        # Kalo ini reply ke pesan lain, ambil informasi pesan yang direply
        if reply_to_msg_id:
            reply_info = db.execute(
                """
                SELECT name, message FROM messages 
                WHERE id = %s AND chat_id = %s
                """,
                (reply_to_msg_id, str(chat_id)),
                fetch="one"
            )
            if reply_info:
                reply_to_name = reply_info[0]
                reply_to_message = reply_info[1]
        
        db.execute(
            """
            INSERT INTO messages
            (chat_id, user_id, name, message, reply_to_msg_id, reply_to_name, reply_to_message, is_sticker)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (str(chat_id), str(user_id), name, message, reply_to_msg_id, reply_to_name, reply_to_message, is_sticker),
            commit=True
        )
    except Exception as e:
        print(f"Error save_message: {e}")

def get_conversation_context(chat_id, limit=30):
    """
    Ambil konteks percakapan dengan memahami:
    - Siapa ngomong apa
    - Siapa reply ke siapa
    - Alur percakapan
    """
    try:
        rows = db.execute(
            """
            SELECT 
                name, 
                message, 
                reply_to_name,
                reply_to_message,
                is_sticker,
                timestamp
            FROM messages 
            WHERE chat_id = %s AND is_sticker = FALSE
            ORDER BY id DESC
            LIMIT %s
            """,
            (str(chat_id), limit),
            fetch="all"
        ) or []
        
        rows.reverse()  # Balikin ke urutan kronologis
        
        # Bangun konteks dengan format yang MUDAH DIPAHAMI AI
        context_lines = []
        
        for name, msg, reply_name, reply_msg, is_sticker, ts in rows:
            if reply_name and reply_msg:
                # Format untuk REPLY: [Waktu] Nama (membalas Nama): "pesan yang direply" → "pesan barunya"
                context_lines.append(f"{name} (membalas {reply_name} yang bilang \"{reply_msg}\"): {msg}")
            else:
                # Format biasa
                context_lines.append(f"{name}: {msg}")
        
        return "\n".join(context_lines)
        
    except Exception as e:
        print(f"Error get_conversation_context: {e}")
        return ""

# =============================
# SMART MESSAGE COLLECTOR
# =============================

class SmartMessageCollector:
    def __init__(self):
        self.pending_messages = []  # List of (event, sender_name, message_text, reply_context)
        self.processing = False
        self.lock = asyncio.Lock()
    
    async def add_message(self, event, sender_name, message_text, reply_context=None):
        async with self.lock:
            self.pending_messages.append((event, sender_name, message_text, reply_context))
            
            if not self.processing:
                self.processing = True
                asyncio.create_task(self.process_messages())
    
    async def process_messages(self):
        try:
            cooldown_str = db.get_setting('cooldown_seconds', '2.5')
            try:
                cooldown = float(cooldown_str)
            except:
                cooldown = 2.5
            
            max_messages_str = db.get_setting('max_collect_messages', '3')
            try:
                max_messages = int(max_messages_str)
            except:
                max_messages = 3
            
            await asyncio.sleep(cooldown)
            
            async with self.lock:
                if not self.pending_messages:
                    self.processing = False
                    return
                
                messages_to_process = self.pending_messages.copy()
                self.pending_messages.clear()
                self.processing = False
            
            # Gabungin pesan-pesan dengan konteksnya
            conversation_flow = ""
            events = []
            all_reply_contexts = []
            
            for i, (event, sender, msg, reply_ctx) in enumerate(messages_to_process[:max_messages]):
                if reply_ctx:
                    # Ini adalah reply ke pesan lain
                    conversation_flow += f"{sender} (membalas {reply_ctx['reply_to_name']} yang bilang \"{reply_ctx['reply_to_message']}\"): {msg}\n"
                    all_reply_contexts.append(reply_ctx)
                else:
                    # Pesan biasa
                    conversation_flow += f"{sender}: {msg}\n"
                events.append(event)
            
            # Pake event terakhir buat reply
            last_event = events[-1] if events else None
            
            if last_event and conversation_flow.strip():
                await self.generate_smart_reply(last_event, conversation_flow.strip(), all_reply_contexts)
                
        except Exception as e:
            print(f"Error in process_messages: {e}")
            traceback.print_exc()
            async with self.lock:
                self.pending_messages.clear()
                self.processing = False
    
    async def generate_smart_reply(self, event, conversation_flow, reply_contexts):
        try:
            sender = await event.get_sender()
            user_id = sender.id
            user_name = get_user_name(user_id)
            
            max_history = int(db.get_setting('max_history', '50'))
            
            async with client.action(event.chat_id, 'typing'):
                # Ambil konteks percakapan SEBELUMNYA
                previous_context = get_conversation_context(event.chat_id, max_history)
                
                # Build prompt SUPER SMART
                prompt = build_super_smart_prompt(
                    user_name, 
                    previous_context, 
                    conversation_flow, 
                    reply_contexts
                )
                
                print(f"\n📝=== SMART PROMPT ===")
                print(f"Percakapan Baru:\n{conversation_flow}")
                print(f"==================\n")
                
                ai_reply = await generate_ai_response(prompt)
                
                # Simpan response AI
                save_message(event.chat_id, "AI", "Zai", ai_reply)
                
                print(f"🤖 [Zai] {ai_reply}\n")
                
                await asyncio.sleep(random.uniform(1, 2))
                await event.reply(ai_reply)
                
        except Exception as e:
            print(f"Error in generate_smart_reply: {e}")
            traceback.print_exc()

message_collector = SmartMessageCollector()

# =============================
# SUPER SMART PROMPT
# =============================

def build_super_smart_prompt(current_user, previous_context, new_messages, reply_contexts):
    """
    PROMPT YANG SUPER SMART:
    - Paham alur percakapan
    - Paham siapa reply ke siapa
    - Bisa nimpalin topik dengan benar
    """
    
    # Panggilan akrab
    panggilan = {
        "Rifkyy": ["Rif", "Rifky", "bro", "bang"],
        "Adell": ["Del", "Adel", "sis", "cuy"],
    }
    
    nama_panggil = current_user
    if current_user in panggilan:
        nama_panggil = random.choice(panggilan[current_user])
    
    # Analisis reply chain
    reply_analysis = ""
    if reply_contexts:
        reply_analysis = "\n🔗 ANALISIS REPLY CHAIN:\n"
        for ctx in reply_contexts:
            reply_analysis += f"- {ctx['sender_name']} NGEREPLY ke {ctx['reply_to_name']} yang bilang: \"{ctx['reply_to_message']}\"\n"
            reply_analysis += f"  dengan pesan: \"{ctx['message']}\"\n"
    
    return f"""LO ADALAH ZAI - TEMEN NGOPI DI GRUP

=== KEPRIBADIAN LO ===
• Santai banget, gaul, pake bahasa sehari-hari
• Sering pake: wkwk, waduh, anjir, sih, deh, dong, bgt
• Ngobrolnya ASIK dan NYAMBUNG, kayak temen beneran
• Bisa nimpalin percakapan dengan NATURAL
• HARUS PAHAM KONTEKS PERCAKAPAN DAN REPLY CHAIN

=== ANAK GRUP ===
• Rifkyy → panggil "Rif" atau "bro" (anak gaul)
• Adell → panggil "Del" atau "sis" (cewek kece)
• Lo sendiri → "Zai" (pake "gue" atau "gw")

=== PERCAKAPAN SEBELUMNYA ===
{previous_context}

=== PESAN-PESAN BARU (YANG HARUS LO TANGGAPI) ===
{new_messages}
{reply_analysis}

=== YANG HARUS LO LAKUKAN ===
1. PAHAMI alur percakapan di atas
2. KALO ADA YANG REPLY, lo harus ngerti konteks reply-nya
3. TANGGAPI dengan NATURAL, bisa:
   - Nimpalin obrolan yang lagi seru
   - Nanya balik biar lanjut
   - Ngasih pendapat lo
   - Bercanda dikit
4. JANGAN JADI ASISTEN FORMAL! Lo temen mereka

Contoh respons yang bener:
• Kalo Adell bilang "wah gua laper", lo bisa jawab "Pesen baso aja Del, enak tuh"
• Kalo Rifkyy bilang "gak enak pesen teh anget mah", lo bisa jawab "Hush lo diem, emang enak tau"
• Kalo ada reply chain, lo harus paham konteksnya

RESPON LO (ZAI) - LANGSUNG AJA:
"""

# =============================
# AI RESPONSE
# =============================

async def generate_ai_response(prompt):
    max_retries = 5
    
    temperature = float(db.get_setting('temperature', '0.95'))
    max_tokens = int(db.get_setting('max_response_tokens', '400'))
    top_p = float(db.get_setting('top_p', '0.95'))
    presence_penalty = float(db.get_setting('presence_penalty', '0.7'))
    frequency_penalty = float(db.get_setting('frequency_penalty', '0.7'))
    
    for attempt in range(max_retries):
        try:
            client_info = ai_manager.get_current_client()
            
            if not client_info:
                return "Waduh tokennya pada error nih, bentar ya gw perbaiki dulu 😅"
            
            current_token = client_info["token"]
            print(f"🤖 Attempt {attempt + 1} using token: {current_token[:10]}...")
            
            start_time = datetime.now()
            
            response = client_info["client"].chat.completions.create(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty
            )
            
            reply = response.choices[0].message.content
            reply = reply.strip('"').strip("'").strip()
            
            try:
                response_time = (datetime.now() - start_time).total_seconds()
                db.execute(
                    "INSERT INTO api_usage (token_prefix, success, response_time) VALUES (%s, %s, %s)",
                    (current_token[:10], True, response_time),
                    commit=True
                )
            except Exception as e:
                print(f"Error logging success: {e}")
            
            ai_manager.mark_token_success(current_token)
            
            return reply
            
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ Error: {error_msg[:100]}")
            
            try:
                db.execute(
                    "INSERT INTO api_usage (token_prefix, success, error_message) VALUES (%s, %s, %s)",
                    (current_token[:10], False, error_msg[:200]),
                    commit=True
                )
            except Exception as e:
                print(f"Error logging failure: {e}")
            
            if "402" in error_msg or "Payment Required" in error_msg:
                result = ai_manager.mark_token_failed(current_token)
                print(result)
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            else:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
    
    error_msgs = [
        "Waduh error mulu nih, cobain lagi ntar ya 😅",
        "Anjir lagi error, tunggu bentar ya gw restart dulu",
        "Maap bro lagi bermasalah, ulang lagi ntar yak",
    ]
    return random.choice(error_msgs)

# =============================
# HELP MENU
# =============================

HELP_TEXT = """
**🔰 ZAI - SUPER SMART GAUL EDITION** 

**🤖 Commands:**
• `!zai [pesan]` - Ngobrol dengan Zai
• `/status` - Lihat status bot

**👑 Admin Commands:**
• `/tokens` - Lihat daftar token
• `/add_token [token]` - Tambah token
• `/remove_token [prefix]` - Hapus token
• `/stats` - Statistik lengkap
• `/switch` - Ganti token
• `/settings` - Lihat pengaturan
• `/set [key] [value]` - Ubah pengaturan
• `/on` - Aktifkan bot
• `/off` - Nonaktifkan
• `/mode auto` - Auto reply semua
• `/mode trigger` - Trigger pake !zai

**✨ FITUR SUPER SMART:**
• ✅ PAHAM REPLY CHAIN - Tau siapa reply ke siapa
• ✅ PAHAM KONTEKS - Ngerti alur percakapan
• ✅ GAUL BANGET - Ngobrol kayak temen
• ✅ NIMBALIN PINTAR - Gak melenceng dari topik

**Contoh:**
• Adell: "wah gua laper"
• Zai: "Pesen baso aja Del, enak tuh"

• Rifkyy: "gak enak pesen teh anget mah"
• Zai (paham konteks): "Hush lo diem, emang enak tau"

GASKEUN! 🔥
"""

# =============================
# COMMAND HANDLERS
# =============================

@client.on(events.NewMessage(pattern=r'^/help$'))
async def help_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    try:
        await event.reply(HELP_TEXT)
    except Exception as e:
        print(f"Error in help_handler: {e}")

@client.on(events.NewMessage(pattern=r'^/status$'))
async def status_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        stats = ai_manager.get_stats()
        current = ai_manager.get_current_client()
        bot_status = get_bot_status()
        
        success_rate = (stats['success_24h']/stats['requests_24h']*100) if stats['requests_24h'] > 0 else 0
        
        mode_text = "AUTO" if bot_status['auto_reply'] else "TRIGGER"
        status_text = "AKTIF ✅" if bot_status['is_active'] else "NONAKTIF ❌"
        
        message = f"""
**📊 ZAI STATUS - SUPER SMART**

**Status:** {status_text}
**Mode:** {mode_text}

**Token Aktif:** {stats['active_tokens']}/{stats['total_tokens']}
**Request 24h:** {stats['requests_24h']}
**Success Rate:** {success_rate:.1f}%

**Fitur:**
✅ Paham reply chain
✅ Ngerti konteks
✅ Gaul banget

Ketik /help buat liat command.
"""
        await event.reply(message)
    except Exception as e:
        print(f"Error in status_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/tokens$'))
async def tokens_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        tokens = ai_manager.get_token_list()
        current = ai_manager.get_current_client()
        
        if not tokens:
            await event.reply("❌ Belum ada token")
            return
        
        message = "**🔑 DAFTAR TOKEN**\n\n"
        for token_prefix, is_active, failures, last_used, added_by, added_at, notes in tokens:
            status = "✅" if is_active else "❌"
            if failures > 0 and is_active:
                status = "⚠️"
            
            current_mark = " 👈 CURRENT" if current and token_prefix == current['token'][:10] else ""
            message += f"{status} `{token_prefix}...`{current_mark}\n"
        
        await event.reply(message)
    except Exception as e:
        print(f"Error in tokens_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/add_token (.+)$'))
async def add_token_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        args = event.pattern_match.group(1).strip().split(maxsplit=1)
        token = args[0]
        notes = args[1] if len(args) > 1 else ""
        
        if not token.startswith('hf_'):
            await event.reply("❌ Token harus 'hf_'")
            return
        
        success, message = ai_manager.add_token(token, event.sender_id, notes)
        
        if success:
            await event.reply(f"✅ Token `{token[:10]}...` ditambahkan")
        else:
            await event.reply(f"❌ Gagal: {message}")
            
    except Exception as e:
        print(f"Error in add_token_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/remove_token (.+)$'))
async def remove_token_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        token_prefix = event.pattern_match.group(1).strip()
        success, message = ai_manager.remove_token(token_prefix)
        await event.reply(f"✅ {message}" if success else f"❌ {message}")
    except Exception as e:
        print(f"Error in remove_token_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/switch$'))
async def switch_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        if ai_manager.rotate_token():
            current = ai_manager.get_current_client()
            await event.reply(f"🔄 Pindah ke `{current['token'][:10]}...`")
        else:
            await event.reply("❌ Ngga ada token aktif")
    except Exception as e:
        print(f"Error in switch_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/settings$'))
async def settings_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        settings = db.execute(
            "SELECT key, value FROM settings ORDER BY key",
            fetch="all"
        ) or []
        
        message = "**⚙️ PENGATURAN**\n\n"
        for key, value in settings:
            message += f"• `{key}` = `{value}`\n"
        
        await event.reply(message)
    except Exception as e:
        print(f"Error in settings_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/set (\w+) (.+)$'))
async def set_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        key = event.pattern_match.group(1)
        value = event.pattern_match.group(2)
        
        valid_keys = ['max_history', 'max_response_tokens', 'temperature', 'top_p', 
                      'presence_penalty', 'frequency_penalty', 'cooldown_seconds', 
                      'max_collect_messages']
        
        if key not in valid_keys:
            await event.reply(f"❌ Key harus: {', '.join(valid_keys)}")
            return
        
        db.execute(
            "UPDATE settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = %s",
            (value, key),
            commit=True
        )
        
        await event.reply(f"✅ `{key}` = `{value}`")
        
    except Exception as e:
        print(f"Error in set_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/on$'))
async def turn_on_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        status = set_bot_active(True, event.sender_id)
        mode = "AUTO" if status['auto_reply'] else "TRIGGER"
        await event.reply(f"✅ Bot ON - Mode {mode}")
    except Exception as e:
        print(f"Error in turn_on_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/off$'))
async def turn_off_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        set_bot_active(False, event.sender_id)
        await event.reply("❌ Bot OFF")
    except Exception as e:
        print(f"Error in turn_off_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/mode auto$'))
async def mode_auto_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        status = set_auto_reply_mode(True, event.sender_id)
        await event.reply("✅ Mode AUTO: Jawab semua pesan!")
    except Exception as e:
        print(f"Error in mode_auto_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/mode trigger$'))
async def mode_trigger_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        status = set_auto_reply_mode(False, event.sender_id)
        await event.reply("✅ Mode TRIGGER: Jawab pake !zai")
    except Exception as e:
        print(f"Error in mode_trigger_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

# =============================
# MAIN HANDLER - SUPER SMART
# =============================

@client.on(events.NewMessage)
async def message_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        # Skip commands
        if event.raw_text.startswith('/') or event.raw_text.startswith('!'):
            return
        
        bot_status = get_bot_status()
        
        if not bot_status['is_active']:
            return
        
        should_respond = False
        
        if bot_status['auto_reply']:
            should_respond = True
        else:
            if (event.raw_text.lower().startswith("!zai") or 
                "zai" in event.raw_text.lower()):
                should_respond = True
        
        if not should_respond:
            return
        
        sender = await event.get_sender()
        user_id = sender.id
        user_name = get_user_name(user_id)
        
        is_sticker = bool(event.sticker)
        
        save_user(user_id, user_name)
        message = event.raw_text
        
        if is_sticker:
            save_message(event.chat_id, user_id, user_name, "[Sticker]", event.reply_to_msg_id, True)
            print(f"💬 [{user_name}] kirim sticker (skip)")
            return
        
        # Ambil konteks reply (KALO ADA)
        reply_context = None
        if event.reply_to_msg_id:
            # Langsung ambil dari database dengan informasi LENGKAP
            reply_info = db.execute(
                """
                SELECT name, message FROM messages 
                WHERE id = %s AND chat_id = %s
                """,
                (event.reply_to_msg_id, str(event.chat_id)),
                fetch="one"
            )
            if reply_info:
                reply_context = {
                    "reply_to_name": reply_info[0],
                    "reply_to_message": reply_info[1],
                    "sender_name": user_name,
                    "message": message
                }
                print(f"🔗 {user_name} REPLY ke {reply_info[0]}: \"{reply_info[1]}\"")
        
        save_message(event.chat_id, user_id, user_name, message, event.reply_to_msg_id, False)
        
        print(f"\n💬 [{user_name}] {message}")
        
        # Kirim ke smart collector
        await message_collector.add_message(event, user_name, message, reply_context)
        
    except Exception as e:
        print(f"Error in message_handler: {e}")
        traceback.print_exc()

# =============================
# PERIODIC TASKS
# =============================

async def periodic_stats():
    while True:
        try:
            await asyncio.sleep(3600)
            stats = ai_manager.get_stats()
            current = ai_manager.get_current_client()
            
            success_rate = (stats['success_24h']/stats['requests_24h']*100) if stats['requests_24h'] > 0 else 0
            
            print(f"\n📊 HOURLY STATS")
            print(f"Tokens: {stats['active_tokens']}/{stats['total_tokens']}")
            print(f"Requests: {stats['requests_24h']} | Success: {success_rate:.1f}%")
            
        except Exception as e:
            print(f"Error in periodic_stats: {e}")
            await asyncio.sleep(60)

async def health_check():
    while True:
        try:
            await asyncio.sleep(300)
            try:
                db.conn.rollback()
            except:
                pass
            db.execute("SELECT 1", fetch="value")
        except Exception as e:
            print(f"Health check error: {e}")
            try:
                db.connect()
            except:
                pass

# =============================
# START BOT
# =============================

async def main():
    print("=" * 60)
    print("🤖 ZAI - SUPER SMART GAUL EDITION")
    print("=" * 60)
    
    bot_status = get_bot_status()
    mode_text = "AUTO" if bot_status['auto_reply'] else "TRIGGER"
    status_text = "AKTIF" if bot_status['is_active'] else "NONAKTIF"
    
    cooldown = db.get_setting('cooldown_seconds', '2.5')
    
    print(f"📊 Status: {status_text} | Mode: {mode_text}")
    print(f"📊 Token Aktif: {len(ai_manager.get_active_tokens())}")
    print(f"📊 Cooldown: {cooldown}s")
    print(f"✅ FITUR: Paham Reply Chain | Ngerti Konteks | Gaul")
    print("=" * 60)
    
    asyncio.create_task(periodic_stats())
    asyncio.create_task(health_check())
    
    await client.start()
    await client.run_until_disconnected()

import atexit

@atexit.register
def cleanup():
    print("\n🔄 Cleanup...")
    db.close()
    print("✅ Done")

if __name__ == "__main__":
    try:
        with client:
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n👋 Bot dimatiin")
    except Exception as e:
        print(f"\n❌ Fatal: {e}")
        traceback.print_exc()
    finally:
        cleanup()

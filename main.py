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
# DATABASE CONNECTION WITH AUTO-RECONNECT
# =============================

class DatabaseManager:
    """Manajemen koneksi database dengan auto-reconnect"""
    
    def __init__(self, database_url):
        self.database_url = database_url
        self.conn = None
        self.cur = None
        self.connect()
        self.init_tables()
        self.update_gaul_settings()
    
    def connect(self):
        """Membuat koneksi database baru"""
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
        """Inisialisasi semua tabel"""
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

            # Tabel messages
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id TEXT,
                user_id TEXT,
                name TEXT,
                message TEXT,
                reply_to_msg_id INTEGER,
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

            # Tabel untuk bot status (ON/OFF)
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
        """Update settings biar lebih gaul"""
        try:
            # Settings buat mode GAUL
            settings = [
                ('temperature', '0.95'),
                ('max_response_tokens', '400'),
                ('max_history', '50'),
                ('top_p', '0.95'),
                ('presence_penalty', '0.7'),
                ('frequency_penalty', '0.7'),
                ('auto_reply_mode', 'false'),
                ('current_token_index', '0'),
                ('cooldown_seconds', '2.5'),  # Tambahin cooldown
                ('max_collect_messages', '3')   # Max pesan sebelum reply
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
        """Eksekusi query dengan error handling yang bener"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Cek koneksi
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
                
            except psycopg2.errors.InFailedSqlTransaction:  # INI YANG DIPERBAIKI
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
        
        raise Exception("Max retries reached for database operation")
    
    def get_setting(self, key, default=None):
        """Ambil setting dari database dengan aman"""
        try:
            # Reset transaction kalo error
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
        """Tutup koneksi database"""
        try:
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()
        except:
            pass

# Inisialisasi database manager
db = DatabaseManager(database_url)

# =============================
# LOAD TOKENS FROM DATABASE
# =============================

def load_tokens_from_db():
    """Load active tokens from database"""
    try:
        rows = db.execute(
            "SELECT token FROM hf_tokens WHERE is_active = TRUE ORDER BY id",
            fetch="all"
        )
        return [row[0] for row in rows] if rows else []
    except Exception as e:
        print(f"Error loading tokens: {e}")
        return []

# Initial load
HF_TOKENS = load_tokens_from_db()

# =============================
# BOT STATUS FUNCTIONS
# =============================

def get_bot_status():
    """Get current bot status"""
    try:
        # Reset transaction kalo error
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
    """Set bot active status"""
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
    """Set auto reply mode"""
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
        """Load settings from database"""
        try:
            value = db.get_setting('current_token_index', '0')
            self.current_token_index = int(value)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def save_settings(self):
        """Save settings to database"""
        try:
            db.execute(
                "UPDATE settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = 'current_token_index'",
                (str(self.current_token_index),),
                commit=True
            )
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get_active_tokens(self):
        """Get list of active tokens"""
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
        """Mendapatkan client dengan token yang sedang aktif"""
        tokens = self.get_active_tokens()
        if not tokens:
            return None
        
        # Pastikan index valid
        if self.current_token_index >= len(tokens):
            self.current_token_index = 0
            self.save_settings()
        
        token = tokens[self.current_token_index]
        
        # Update last used
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
        """Pindah ke token berikutnya"""
        tokens = self.get_active_tokens()
        if tokens:
            self.current_token_index = (self.current_token_index + 1) % len(tokens)
            self.save_settings()
            return True
        return False
    
    def mark_token_failed(self, token):
        """Menandai token yang gagal"""
        try:
            db.execute(
                "UPDATE hf_tokens SET failures = failures + 1 WHERE token = %s",
                (token,),
                commit=True
            )
            
            # Auto disable if too many failures
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
        """Menandai token berhasil digunakan"""
        try:
            db.execute(
                "UPDATE hf_tokens SET failures = 0, last_used = CURRENT_TIMESTAMP WHERE token = %s",
                (token,),
                commit=True
            )
        except Exception as e:
            print(f"Error marking token success: {e}")
    
    def add_token(self, token, added_by, notes=""):
        """Menambahkan token baru"""
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
        """Menonaktifkan token"""
        try:
            db.execute(
                "UPDATE hf_tokens SET is_active = FALSE WHERE token_prefix = %s OR token LIKE %s",
                (token_prefix, f"{token_prefix}%"),
                commit=True
            )
            
            affected = db.cur.rowcount
            
            if affected > 0:
                # Rotate if current token is disabled
                current = self.get_current_client()
                if current and current['token'].startswith(token_prefix):
                    self.rotate_token()
                return True, f"{affected} token dinonaktifkan"
            return False, "Token tidak ditemukan"
            
        except Exception as e:
            return False, str(e)
    
    def disable_token(self, token):
        """Menonaktifkan token tertentu"""
        try:
            db.execute(
                "UPDATE hf_tokens SET is_active = FALSE WHERE token = %s",
                (token,),
                commit=True
            )
        except Exception as e:
            print(f"Error disabling token: {e}")
    
    def get_token_list(self):
        """Mendapatkan daftar semua token"""
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
        """Mendapatkan statistik token"""
        try:
            # Token stats
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
            
            # Usage stats
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

# =============================
# INITIALIZE MANAGER
# =============================

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
    """Cek apakah user adalah admin"""
    return str(user_id) in [str(admin) for admin in ADMIN_IDS]

# =============================
# MEMORY SYSTEM WITH REPLY CONTEXT
# =============================

def save_message(chat_id, user_id, name, message, reply_to_msg_id=None, is_sticker=False):
    try:
        db.execute(
            """
            INSERT INTO messages
            (chat_id, user_id, name, message, reply_to_msg_id, is_sticker)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (str(chat_id), str(user_id), name, message, reply_to_msg_id, is_sticker),
            commit=True
        )
    except Exception as e:
        print(f"Error save_message: {e}")

def get_last_messages_with_context(chat_id, limit=50):
    """
    Ambil pesan terakhir dengan informasi reply context
    """
    try:
        rows = db.execute(
            """
            SELECT 
                m1.name, 
                m1.message, 
                m1.reply_to_msg_id,
                m2.name as reply_to_name,
                m2.message as reply_to_message,
                m1.is_sticker
            FROM messages m1
            LEFT JOIN messages m2 ON m1.reply_to_msg_id = m2.id
            WHERE m1.chat_id=%s
            ORDER BY m1.id DESC
            LIMIT %s
            """,
            (str(chat_id), limit),
            fetch="all"
        ) or []
        
        rows.reverse()
        history = ""
        
        for name, msg, reply_id, reply_name, reply_msg, is_sticker in rows:
            if is_sticker:
                continue  # Skip sticker di history
            
            if reply_id and reply_name and reply_msg:
                # Ini adalah reply ke pesan lain
                history += f"{name} (reply ke {reply_name}: \"{reply_msg}\"): {msg}\n"
            else:
                history += f"{name}: {msg}\n"
        
        return history
        
    except Exception as e:
        print(f"Error get_last_messages: {e}")
        return ""

# =============================
# SMART MESSAGE COLLECTOR
# =============================

class SmartMessageCollector:
    """
    Ngumpulin pesan dalam waktu dekat sebelum reply,
    biar gak reply berkali-kali buat pesan yang nyambung
    """
    
    def __init__(self):
        self.pending_messages = []  # List of (event, sender_name, message_text, reply_to_context)
        self.processing = False
        self.lock = asyncio.Lock()
    
    async def add_message(self, event, sender_name, message_text, reply_to_context=None):
        """Tambah pesan ke antrian"""
        async with self.lock:
            self.pending_messages.append((event, sender_name, message_text, reply_to_context))
            
            # Kalau belum processing, mulai proses
            if not self.processing:
                self.processing = True
                asyncio.create_task(self.process_messages())
    
    async def process_messages(self):
        """Proses kumpulan pesan setelah cooldown"""
        try:
            # Ambil cooldown dari settings dengan aman
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
            
            # Tunggu selama cooldown
            await asyncio.sleep(cooldown)
            
            async with self.lock:
                if not self.pending_messages:
                    self.processing = False
                    return
                
                # Ambil semua pesan yang terkumpul
                messages_to_process = self.pending_messages.copy()
                self.pending_messages.clear()
                self.processing = False
            
            # Gabungkan pesan-pesan
            combined_text = ""
            reply_contexts = []
            events = []
            
            for event, sender, msg, reply_ctx in messages_to_process[:max_messages]:
                if reply_ctx:
                    combined_text += f"{sender} (membalas {reply_ctx['reply_to_name']}: \"{reply_ctx['reply_to_message']}\"): {msg}\n"
                    reply_contexts.append(reply_ctx)
                else:
                    combined_text += f"{sender}: {msg}\n"
                events.append(event)
            
            # Gunakan event terakhir untuk reply (biar reply ke pesan terakhir)
            last_event = events[-1] if events else None
            
            if last_event and combined_text.strip():
                # Generate AI response untuk gabungan pesan
                await self.generate_and_reply(last_event, combined_text.strip(), reply_contexts)
                
        except Exception as e:
            print(f"Error in process_messages: {e}")
            traceback.print_exc()
            async with self.lock:
                self.pending_messages.clear()
                self.processing = False
    
    async def generate_and_reply(self, event, combined_text, reply_contexts):
        """Generate AI response buat gabungan pesan"""
        try:
            sender = await event.get_sender()
            user_id = sender.id
            user_name = get_user_name(user_id)
            
            # Get max_history from settings
            max_history_str = db.get_setting('max_history', '50')
            try:
                max_history = int(max_history_str)
            except:
                max_history = 50
            
            async with client.action(event.chat_id, 'typing'):
                history = get_last_messages_with_context(event.chat_id, max_history)
                
                # Build prompt dengan context yang lebih baik
                prompt = build_smart_prompt(user_name, history, combined_text, reply_contexts)
                
                print(f"\n📝 SMART PROMPT untuk {len(reply_contexts)} pesan:\n{combined_text}\n")
                
                ai_reply = await generate_ai_response(prompt)
                
                # Simpan response AI
                save_message(event.chat_id, "AI", "Zai", ai_reply)
                
                print(f"🤖 [Zai] {ai_reply}\n")
                
                # Random delay biar natural
                await asyncio.sleep(random.uniform(1, 2))
                await event.reply(ai_reply)
                
        except Exception as e:
            print(f"Error in generate_and_reply: {e}")
            traceback.print_exc()

# Inisialisasi message collector
message_collector = SmartMessageCollector()

# =============================
# SMART PROMPT - PAHAM KONTEKS REPLY
# =============================

def build_smart_prompt(user_name, history, combined_messages, reply_contexts):
    """
    Prompt yang lebih paham konteks percakapan dan reply
    """
    
    # Random panggilan biar variatif
    panggilan = {
        "Rifkyy": ["Rif", "Rifky", "bro", "bang", "Rifkyy"],
        "Adell": ["Del", "Adel", "sis", "cuy", "Adell"],
        "Zai": ["Zai", "gue", "saya", "gw"]
    }
    
    nama_panggil = user_name
    if user_name in panggilan:
        nama_panggil = random.choice(panggilan[user_name])
    
    # Tambah info reply context ke prompt
    reply_info = ""
    if reply_contexts:
        reply_info = "\nKONTEKS REPLY:\n"
        for ctx in reply_contexts:
            reply_info += f"• {ctx['reply_to_name']} bilang: \"{ctx['reply_to_message']}\"\n"
            reply_info += f"  lalu {ctx['sender_name']} reply: \"{ctx['message']}\"\n"
    
    return f"""LO ADALAH ZAI - TEMEN NGOPI MEREKA DI GRUP

--- KEPRIBADIAN LO ---
• Santai banget, gaul, pake bahasa sehari-hari campur inggris dikit
• Sering pake kata: wkwk, waduh, anjir, sih, deh, dong, bgt, banget, wkwkwk
• Ngobrolnya asik, kadang nanya balik, kadang nimpalin, kadang becanda
• Bisa panjang bisa pendek, bebas! yg penting nyambung
• Kalo lagi seru ya panjang, kalo lagi santai ya pendek
• LO HARUS PAHAM KONTEKS PERCAKAPAN, terutama kalo ada yang saling reply

--- ANAK GRUP ---
• Rifkyy → panggil "Rif" atau "Rifky" (lo panggil "Rif" aja biar akrab)
• Adell → panggil "Del" atau "Adel" (lo panggil "Del" biar gaul)
• Lo sendiri → "Zai" (pake "gue" atau "gw")

--- CHAT TERAKHIR DI GRUP ---
{history}

--- PESAN-PESAN BARU (BISA LEBIH DARI SATU) ---
{combined_messages}
{reply_info}

--- RESPON LO (ZAI) ---
INGAT: Lo adalah Zai, bukan asisten formal. Lo temen mereka. 
Lo harus PAHAM KONTEKS dari semua pesan di atas, termasuk yang saling reply.
Jawab dengan NATURAL kayak di grup beneran! Bisa nimpalin semua poin atau fokus ke yang paling penting.

Zai:"""

# =============================
# AI RESPONSE - GAUL VERSION
# =============================

async def generate_ai_response(prompt):
    """Generate AI response dengan parameter GAUL"""
    
    max_retries = 5
    
    # Ambil settings GAUL dari database dengan aman
    try:
        temperature = float(db.get_setting('temperature', '0.95'))
    except:
        temperature = 0.95
    
    try:
        max_tokens = int(db.get_setting('max_response_tokens', '400'))
    except:
        max_tokens = 400
    
    try:
        top_p = float(db.get_setting('top_p', '0.95'))
    except:
        top_p = 0.95
    
    try:
        presence_penalty = float(db.get_setting('presence_penalty', '0.7'))
    except:
        presence_penalty = 0.7
    
    try:
        frequency_penalty = float(db.get_setting('frequency_penalty', '0.7'))
    except:
        frequency_penalty = 0.7
    
    for attempt in range(max_retries):
        try:
            client_info = ai_manager.get_current_client()
            
            if not client_info:
                return "Waduh tokennya pada error nih, bentar ya gw perbaiki dulu 😅"
            
            current_token = client_info["token"]
            print(f"🤖 Attempt {attempt + 1} using token: {current_token[:10]}...")
            
            # Record start time
            start_time = datetime.now()
            
            # PAKAI PARAMETER GAUL!
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
            
            # Bersihin reply dari kutipan dan spasi berlebih
            reply = reply.strip('"').strip("'").strip()
            
            # Log success
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
            
            # Log failure
            try:
                db.execute(
                    "INSERT INTO api_usage (token_prefix, success, error_message) VALUES (%s, %s, %s)",
                    (current_token[:10], False, error_msg[:200]),
                    commit=True
                )
            except Exception as e:
                print(f"Error logging failure: {e}")
            
            # Kalau error quota habis, ganti token
            if "402" in error_msg or "Payment Required" in error_msg:
                result = ai_manager.mark_token_failed(current_token)
                print(result)
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            else:
                # Error lain, coba lagi
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
    
    # Random error message biar gaul
    error_msgs = [
        "Waduh error mulu nih, cobain lagi ntar ya 😅",
        "Anjir lagi error, tunggu bentar ya gw restart dulu",
        "Maap bro lagi bermasalah, ulang lagi ntar yak",
        "Error mulu sih, sabar ya lagi dibenerin"
    ]
    return random.choice(error_msgs)

# =============================
# HELP MENU
# =============================

HELP_TEXT = """
**🔰 ZAI - BOT MANAGER** (SMART EDITION)

**🤖 Commands untuk Semua User:**
• `!zai [pesan]` - Ngobrol dengan Zai
• `/status` - Lihat status bot

**👑 Commands untuk Admin:**
• `/tokens` - Lihat daftar semua token
• `/add_token [token] [catatan]` - Tambah token baru
• `/remove_token [prefix]` - Hapus token (pakai 10 char pertama)
• `/stats` - Lihat statistik lengkap
• `/switch` - Pindah ke token berikutnya
• `/settings` - Lihat pengaturan bot
• `/set [key] [value]` - Ubah pengaturan
• `/test_token [prefix]` - Test token tertentu
• `/clean_logs [days]` - Bersihkan log lama
• `/on` - Aktifkan bot
• `/off` - Nonaktifkan bot
• `/mode auto` - Mode Auto (jawab semua pesan)
• `/mode trigger` - Mode Trigger (jawab dengan !zai)
• `/help` - Tampilkan menu ini

**⚙️ Settings GAUL:**
• `temperature` = 0.95 (kreativitas)
• `max_response_tokens` = 400 (panjang maksimal)
• `max_history` = 50 (ingatan)
• `top_p` = 0.95 (variasi)
• `presence_penalty` = 0.7 (anti ngulang)
• `frequency_penalty` = 0.7 (anti monoton)
• `cooldown_seconds` = 2.5 (nunggu sebelum reply)
• `max_collect_messages` = 3 (max pesan dikumpulin)

**Contoh GAUL:**
• `/add_token hf_abc123... token utama`
• `/set temperature 0.9`
"""

# =============================
# COMMAND HANDLERS
# (Sisanya sama, gak berubah)
# =============================

@client.on(events.NewMessage(pattern=r'^/help$'))
async def help_handler(event):
    """Show help menu"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        await event.reply(HELP_TEXT)
    except Exception as e:
        print(f"Error in help_handler: {e}")

@client.on(events.NewMessage(pattern=r'^/status$'))
async def status_handler(event):
    """Simple status for all users"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        stats = ai_manager.get_stats()
        current = ai_manager.get_current_client()
        bot_status = get_bot_status()
        
        success_rate = (stats['success_24h']/stats['requests_24h']*100) if stats['requests_24h'] > 0 else 0
        
        mode_text = "AUTO (semua pesan)" if bot_status['auto_reply'] else "TRIGGER (!zai)"
        status_text = "AKTIF ✅" if bot_status['is_active'] else "NONAKTIF ❌"
        
        message = f"""
**📊 BOT STATUS - SMART GAUL EDITION**

**Bot:**
• Status: {status_text}
• Mode: {mode_text}

**Token:**
• Active: {stats['active_tokens']}/{stats['total_tokens']}
• Current: {current['token'][:10] if current else 'None'}...

**Usage 24h:**
• Request: {stats['requests_24h']}
• Sukses: {stats['success_24h']} ({success_rate:.1f}%)
• Waktu respon: {stats['avg_response']:.2f}s


Gunakan `/help` buat liat command.
"""
        await event.reply(message)
    except Exception as e:
        print(f"Error in status_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

# ... (semua command handler lainnya sama, gak berubah) ...

# =============================
# MAIN EVENT HANDLER - SMART VERSION
# =============================

@client.on(events.NewMessage)
async def message_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        # Skip commands
        if event.raw_text.startswith('/') or event.raw_text.startswith('!'):
            return
        
        # Check bot status
        bot_status = get_bot_status()
        
        # If bot is off, don't respond
        if not bot_status['is_active']:
            return
        
        # Determine if bot should respond
        should_respond = False
        
        if bot_status['auto_reply']:
            # Mode AUTO: respond to ALL messages
            should_respond = True
        else:
            # Mode TRIGGER: only respond if triggered
            if (event.raw_text.lower().startswith("!zai") or 
                "zai" in event.raw_text.lower() or
                "ustadz" in event.raw_text.lower()):
                should_respond = True
        
        if not should_respond:
            return
        
        sender = await event.get_sender()
        user_id = sender.id
        user_name = get_user_name(user_id)
        
        # Cek apakah ini sticker
        is_sticker = bool(event.sticker)
        
        save_user(user_id, user_name)
        message = event.raw_text
        
        # Kalo sticker, simpan tapi jangan diproses
        if is_sticker:
            save_message(event.chat_id, user_id, user_name, "[Sticker]", event.reply_to_msg_id, True)
            print(f"💬 [{user_name}] mengirim sticker (skip reply)")
            return
        
        # Cek apakah ini reply ke pesan lain
        reply_context = None
        if event.reply_to_msg_id:
            # Ambil pesan yang di-reply
            reply_to_msg = db.execute(
                """
                SELECT name, message FROM messages 
                WHERE id = %s AND chat_id = %s
                """,
                (event.reply_to_msg_id, str(event.chat_id)),
                fetch="one"
            )
            if reply_to_msg:
                reply_context = {
                    "reply_to_name": reply_to_msg[0],
                    "reply_to_message": reply_to_msg[1],
                    "sender_name": user_name,
                    "message": message
                }
        
        save_message(event.chat_id, user_id, user_name, message, event.reply_to_msg_id, False)
        
        print(f"\n💬 [{user_name}] {message}")
        if reply_context:
            print(f"   ↳ Reply ke: {reply_context['reply_to_name']}: \"{reply_context['reply_to_message']}\"")
        
        # Kirim ke smart collector
        await message_collector.add_message(event, user_name, message, reply_context)
        
    except Exception as e:
        print(f"Error in message_handler: {e}")
        traceback.print_exc()

# =============================
# PERIODIC TASKS
# =============================

async def periodic_stats():
    """Print stats periodically"""
    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            
            stats = ai_manager.get_stats()
            current = ai_manager.get_current_client()
            bot_status = get_bot_status()
            
            success_rate = (stats['success_24h']/stats['requests_24h']*100) if stats['requests_24h'] > 0 else 0
            
            mode_text = "AUTO" if bot_status['auto_reply'] else "TRIGGER"
            status_text = "ON" if bot_status['is_active'] else "OFF"
            
            print(f"\n📊 HOURLY STATS")
            print(f"Bot: {status_text} | Mode: {mode_text}")
            print(f"Tokens: {stats['active_tokens']}/{stats['total_tokens']} active")
            print(f"Current: {current['token'][:10] if current else 'None'}")
            print(f"Requests (24h): {stats['requests_24h']}")
            print(f"Success rate: {success_rate:.1f}%")
            print(f"Avg response: {stats['avg_response']:.2f}s")
            
        except Exception as e:
            print(f"Error in periodic_stats: {e}")
            await asyncio.sleep(60)

async def health_check():
    """Periodic health check for database"""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            # Reset transaction kalo error
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
    print("=" * 50)
    print("🤖 ZAI - SMART EDITION")
    print("=" * 50)
    
    bot_status = get_bot_status()
    mode_text = "AUTO (semua pesan)" if bot_status['auto_reply'] else "TRIGGER (!zai)"
    status_text = "AKTIF" if bot_status['is_active'] else "NONAKTIF"
    
    cooldown = db.get_setting('cooldown_seconds', '2.5')
    max_collect = db.get_setting('max_collect_messages', '3')
    
    print(f"📊 Bot Status: {status_text}")
    print(f"📊 Mode: {mode_text}")
    print(f"📊 Active Tokens: {len(ai_manager.get_active_tokens())}")
    print(f"👑 Admins: {ADMIN_IDS}")
    print(f"🔥 Settings: Cooldown {cooldown}s | Max Collect {max_collect}")
    print(f"✅ Fitur: Paham reply context | Skip sticker | Smart delay")
    print(f"📝 Ketik /help buat liat menu")
    print("=" * 50)
    
    # Start periodic tasks
    asyncio.create_task(periodic_stats())
    asyncio.create_task(health_check())
    
    await client.start()
    await client.run_until_disconnected()

# Cleanup on exit
import atexit

@atexit.register
def cleanup():
    """Cleanup database connection on exit"""
    print("\n🔄 Cleaning up...")
    db.close()
    print("✅ Cleanup done")

if __name__ == "__main__":
    try:
        with client:
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n👋 Bot dimatiin user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        cleanup()

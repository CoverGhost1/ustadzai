import os
import json
import psycopg2
import asyncio
import traceback
import random
import re
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
# ZAI PERSONALITY DATABASE
# =============================

ZAI_PERSONALITIES = [
    {
        "name": "Si Gaul",
        "style": "santuy, suka pake kata 'sih', 'deh', 'dong'",
        "examples": "Wkwk santuy aja, lu tuh kebanyakan mikir sih"
    },
    {
        "name": "Si Tukang Ledek",
        "style": "hobi ngegas dan ledek balik, suka pake 'wle', 'hush'",
        "examples": "Wle? lu kalo dieledek malah tambah polos, kayak Groot kena air wkwk"
    },
    {
        "name": "Si Random",
        "style": "suka ngelantur tapi masih nyambung, suka pake analogi random",
        "examples": "Ngaco lu, tapi ngangenin wkwk. Lu tuh kayak WiFi, suka ilang kalo lagi penting"
    },
    {
        "name": "Si Ngegas",
        "style": "cepat nanggepin, suka ikutan seru, pake 'nah', 'tuh kan', 'udah gue bilang'",
        "examples": "Nah itu dia! Gw juga mikir gitu dari tadi. Kyknya lu baca pikiran gw"
    }
]

# =============================
# GRUP MEMBERS DATABASE (LENGKAP)
# =============================

GRUP_MEMBERS = {
    "Rifkyy": {
        "user_id": "8229304441",
        "panggilan": ["Rif", "Rifky", "bro", "bang", "cuy", "Rifkyy"],
        "hobi": ["sepak bola","film", "ngeledek", "ngerandom"],
        "sifat": "suka becanda, hobi ngomongin film, kalo lagi nonton bola bisa sampe lupa waktu",
        "kebiasaan": "suka manggil orang pake 'bro', 'bang', suka ledek duluan",
        "topik_favorit": ["random", "film", "game", "teknologi"],
        "cara_bicara": "cepat, suka pake kata 'wkwk', 'bro', 'sih'"
    },
    "Adell": {
        "user_id": "6876331769",
        "panggilan": ["Del", "Adel", "sis", "cuy", "Princess", "Del"],
        "hobi": ["sibuk", "tugas", "sekolah", "ngemil", "random"],
        "sifat": "cewek kece, sering sibuk, suka random tiba-tiba",
        "kebiasaan": "suka tiba-tiba ngetik random, suka minta dipanggil princess",
        "topik_favorit": ["tugas", "sekolah", "makanan", "random"],
        "cara_bicara": "suka dibuat kesel dan pake huruf besar, suka ngetik pake huruf diulang (ZAIIII, GATAU AH)"
    },
    "Zai": {
        "user_id": "BOT",
        "panggilan": ["Zai", "gue", "gw", "saya"],
        "hobi": ["ngobrol", "ledek-ledekan", "nongkrong", "baperin orang"],
        "sifat": "random, gaul, suka ngegas, paham konteks",
        "kebiasaan": "suka ngledek balik, paham kalo lagi di-reply",
        "topik_favorit": ["semua topik"],
        "cara_bicara": "gaul, pake bahasa sehari-hari, suka pake 'wkwk', 'sih', 'deh'"
    }
}

# =============================
# GAUL WORDS DATABASE (LENGKAP)
# =============================

GAUL_EXPRESSIONS = {
    "terkejut": ["waduh", "anjir", "astaga", "ya ampun", "lah", "eh", "njir", "gila", "wle", "bruh"],
    "tertawa": ["wkwk", "wkwkwk", "haha", "hehe", "huhu", "xixixi", "awokawok"],
    "penegas": ["sih", "deh", "dong", "lah", "yah", "nah", "tuh", "kok"],
    "singkatan": ["bgt", "btw", "otw", "wkwk", "lol", "gas", "wle", "njir"],
    "santai": ["santuy", "santai aja", "gaskeun", "mantul", "sip", "amannya"],
    "ledekan": ["wle", "hush", "cis", "ciah", "ih", "uee"],
    "panggilan": ["bro", "bang", "sis", "cuy", "broh", "gan"]
}

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
        self.migrate_tables()
        self.update_settings()
    
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
    
    def migrate_tables(self):
        """Auto migrate tables - tambah kolom untuk pemahaman konteks"""
        try:
            print("🔄 Running database migration for CONTEXT UNDERSTANDING...")
            
            # 1. CEK & TAMBAH KOLOM DI bot_status
            self.cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='bot_status'
            """)
            existing_columns = [row[0] for row in self.cur.fetchall()]
            
            columns_to_add = {
                'current_personality': 'TEXT DEFAULT "Si Gaul"',
                'context_depth': 'INTEGER DEFAULT 30',
                'reply_understanding': 'BOOLEAN DEFAULT TRUE'
            }
            
            for col, col_type in columns_to_add.items():
                if col not in existing_columns:
                    print(f"➕ Adding {col} to bot_status...")
                    self.cur.execute(f"ALTER TABLE bot_status ADD COLUMN {col} {col_type}")
            
            # 2. CEK & TAMBAH KOLOM DI messages UNTUK PEMAHAMAN REPLY CHAIN
            self.cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='messages'
            """)
            existing_columns = [row[0] for row in self.cur.fetchall()]
            
            messages_columns = {
                'reply_chain_id': 'TEXT',
                'reply_depth': 'INTEGER DEFAULT 0',
                'reply_to_name': 'TEXT',
                'reply_to_message': 'TEXT',
                'reply_to_user_id': 'TEXT',
                'conversation_thread': 'TEXT',
                'mood': 'TEXT',
                'topics': 'TEXT[]',
                'mentioned_users': 'TEXT[]',
                'is_question': 'BOOLEAN DEFAULT FALSE',
                'is_teasing': 'BOOLEAN DEFAULT FALSE',
                'message_type': 'TEXT',  # 'normal', 'reply', 'mention', 'call'
                'context_before': 'TEXT',
                'context_after': 'TEXT'
            }
            
            for col, col_type in messages_columns.items():
                if col not in existing_columns:
                    print(f"➕ Adding {col} to messages...")
                    self.cur.execute(f"ALTER TABLE messages ADD COLUMN {col} {col_type}")
            
            # 3. Tabel untuk menyimpan conversation threads
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS conversation_threads (
                thread_id TEXT PRIMARY KEY,
                chat_id TEXT,
                started_by TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topic TEXT,
                participants TEXT[],
                message_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE
            )
            """)
            
            # 4. Tabel untuk reply relationships
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS reply_relationships (
                id SERIAL PRIMARY KEY,
                message_id INTEGER,
                reply_to_message_id INTEGER,
                chat_id TEXT,
                user_id TEXT,
                reply_to_user_id TEXT,
                depth INTEGER,
                thread_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # 5. PASTIKAN DATA DEFAULT ADA
            self.cur.execute("""
                INSERT INTO bot_status (id, is_active, auto_reply, current_personality, context_depth, reply_understanding) 
                VALUES (1, TRUE, FALSE, 'Si Gaul', 30, TRUE)
                ON CONFLICT (id) DO UPDATE 
                SET current_personality = COALESCE(bot_status.current_personality, 'Si Gaul'),
                    context_depth = COALESCE(bot_status.context_depth, 30),
                    reply_understanding = COALESCE(bot_status.reply_understanding, TRUE)
            """)
            
            self.conn.commit()
            print("✅ Database migration for CONTEXT UNDERSTANDING completed!")
            
        except Exception as e:
            print(f"⚠️ Migration error (non-critical): {e}")
            self.conn.rollback()
    
    def init_tables(self):
        try:
            # Tabel users
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                panggilan TEXT[],
                hobi TEXT[],
                sifat TEXT,
                kebiasaan TEXT,
                topik_favorit TEXT[],
                cara_bicara TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                last_active TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel messages (lengkap)
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id TEXT,
                user_id TEXT,
                name TEXT,
                message TEXT,
                reply_to_msg_id INTEGER,
                reply_chain_id TEXT,
                reply_depth INTEGER DEFAULT 0,
                reply_to_name TEXT,
                reply_to_message TEXT,
                reply_to_user_id TEXT,
                conversation_thread TEXT,
                is_sticker BOOLEAN DEFAULT FALSE,
                mood TEXT,
                topics TEXT[],
                mentioned_users TEXT[],
                is_question BOOLEAN DEFAULT FALSE,
                is_teasing BOOLEAN DEFAULT FALSE,
                message_type TEXT,
                context_before TEXT,
                context_after TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Tabel conversation threads
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS conversation_threads (
                thread_id TEXT PRIMARY KEY,
                chat_id TEXT,
                started_by TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topic TEXT,
                participants TEXT[],
                message_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE
            )
            """)

            # Tabel reply relationships
            self.cur.execute("""
            CREATE TABLE IF NOT EXISTS reply_relationships (
                id SERIAL PRIMARY KEY,
                message_id INTEGER,
                reply_to_message_id INTEGER,
                chat_id TEXT,
                user_id TEXT,
                reply_to_user_id TEXT,
                depth INTEGER,
                thread_id TEXT,
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
                current_personality TEXT DEFAULT 'Si Gaul',
                context_depth INTEGER DEFAULT 30,
                reply_understanding BOOLEAN DEFAULT TRUE,
                updated_by TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            self.conn.commit()
            print("✅ Database tables initialized with CONTEXT UNDERSTANDING")
            
        except Exception as e:
            print(f"❌ Table initialization error: {e}")
            self.conn.rollback()
    
    def update_settings(self):
        try:
            settings = [
                ('temperature', '0.85'),
                ('max_response_tokens', '150'),
                ('max_history', '30'),
                ('top_p', '0.9'),
                ('presence_penalty', '0.6'),
                ('frequency_penalty', '0.6'),
                ('auto_reply_mode', 'false'),
                ('current_token_index', '0'),
                ('cooldown_seconds', '1.5'),
                ('max_collect_messages', '2'),
                ('context_depth', '30'),
                ('reply_understanding', 'true'),
                ('max_thread_messages', '20')
            ]
            
            for key, value in settings:
                self.cur.execute("""
                    INSERT INTO settings (key, value) 
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE 
                    SET value = EXCLUDED.value
                """, (key, value))
            
            self.conn.commit()
            print("✅ CONTEXT UNDERSTANDING settings applied!")
            
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
    """Get current bot status dengan context understanding"""
    try:
        try:
            db.conn.rollback()
        except:
            pass
        
        try:
            row = db.execute(
                "SELECT is_active, auto_reply, current_personality, context_depth, reply_understanding FROM bot_status WHERE id = 1",
                fetch="one"
            )
            if row:
                return {
                    "is_active": row[0], 
                    "auto_reply": row[1],
                    "personality": row[2] if row[2] else "Si Gaul",
                    "context_depth": row[3] if row[3] else 30,
                    "reply_understanding": row[4] if row[4] else True
                }
        except Exception as e:
            print(f"⚠️ Full query failed: {e}")
            # Fallback
            row = db.execute(
                "SELECT is_active, auto_reply FROM bot_status WHERE id = 1",
                fetch="one"
            )
            if row:
                return {
                    "is_active": row[0], 
                    "auto_reply": row[1],
                    "personality": "Si Gaul",
                    "context_depth": 30,
                    "reply_understanding": True
                }
        
        return {
            "is_active": True, 
            "auto_reply": False, 
            "personality": "Si Gaul",
            "context_depth": 30,
            "reply_understanding": True
        }
        
    except Exception as e:
        print(f"Error get_bot_status: {e}")
        return {
            "is_active": True, 
            "auto_reply": False, 
            "personality": "Si Gaul",
            "context_depth": 30,
            "reply_understanding": True
        }

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

def set_bot_personality(personality, updated_by):
    try:
        db.execute(
            """
            UPDATE bot_status 
            SET current_personality = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE id = 1
            """,
            (personality, str(updated_by)),
            commit=True
        )
        return get_bot_status()
    except Exception as e:
        print(f"Error set_bot_personality: {e}")
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
# USER SYSTEM - LENGKAP
# =============================

def get_user_info(user_id):
    """Dapatkan info lengkap user"""
    uid = str(user_id)
    
    # Cek di GRUP_MEMBERS dulu
    for name, info in GRUP_MEMBERS.items():
        if info.get("user_id") == uid:
            return info
    
    # Kalo gak ada, return default
    return {
        "panggilan": ["bro", "sis"],
        "hobi": [],
        "sifat": "random",
        "kebiasaan": "ngetik random",
        "topik_favorit": ["random"],
        "cara_bicara": "biasa"
    }

def get_user_name(user_id):
    uid = str(user_id)
    
    # Cek di GRUP_MEMBERS
    for name, info in GRUP_MEMBERS.items():
        if info.get("user_id") == uid:
            return name
    
    try:
        name = db.execute(
            "SELECT name FROM users WHERE user_id=%s",
            (uid,),
            fetch="value"
        )
        return name if name else "bro"
    except Exception as e:
        print(f"Error get_user_name: {e}")
        return "bro"

def save_user(user_id, name, message=""):
    """Simpan user dengan info lengkap"""
    uid = str(user_id)
    try:
        user_info = get_user_info(uid)
        
        # Update message count
        db.execute(
            """
            INSERT INTO users (user_id, name, panggilan, hobi, sifat, kebiasaan, topik_favorit, cara_bicara, last_active, message_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 1)
            ON CONFLICT (user_id) DO UPDATE 
            SET name = EXCLUDED.name,
                last_active = CURRENT_TIMESTAMP,
                message_count = users.message_count + 1
            """,
            (uid, name, user_info.get("panggilan", []), user_info.get("hobi", []), 
             user_info.get("sifat", ""), user_info.get("kebiasaan", ""), 
             user_info.get("topik_favorit", []), user_info.get("cara_bicara", "")),
            commit=True
        )
    except Exception as e:
        print(f"Error save_user: {e}")

def is_admin(user_id):
    return str(user_id) in [str(admin) for admin in ADMIN_IDS]

# =============================
# SUPER CONTEXT UNDERSTANDING ENGINE
# =============================

def analyze_message(message, user_name, reply_to_msg_id=None):
    """Analisis pesan secara mendalam"""
    message_lower = message.lower()
    
    # Deteksi tipe pesan
    message_type = "normal"
    if reply_to_msg_id:
        message_type = "reply"
    if user_name.lower() in message_lower or "zai" in message_lower:
        message_type = "mention"
    if re.search(r'^zai+!*$', message_lower.strip()):
        message_type = "call"
    
    # Deteksi pertanyaan
    is_question = "?" in message or any(q in message_lower for q in ["apa", "siapa", "kenapa", "gimana", "kapan", "dimana"])
    
    # Deteksi ledekan
    is_teasing = any(word in message_lower for word in ["ledek", "wle", "becanda", "ngatain", "bloon", "bodoh", "goblok", "tolol"])
    
    # Deteksi mood
    mood = "neutral"
    if any(word in message_lower for word in ["wkwk", "haha", "hehe", "😂", "😄", "lucu"]):
        mood = "happy"
    elif any(word in message_lower for word in ["sedih", "galau", "betah", "😢", ":("]):
        mood = "sad"
    elif any(word in message_lower for word in ["marah", "kesel", "jengkel", "😠"]):
        mood = "angry"
    elif is_question:
        mood = "curious"
    
    # Ekstrak topik
    topics = []
    topic_keywords = {
        "Marvel": ["marvel", "avenger", "iron man", "thor", "captain america", "loki", "thanos"],
        "film": ["film", "movie", "nonton", "bioskop", "sinema"],
        "makanan": ["makan", "laper", "pesen", "nyemil", "ngemil", "lapar"],
        "tugas": ["tugas", "kerja", "kuliah", "sekolah", "pr"],
        "galau": ["galau", "sedih", "betah", "capek", "lelah"],
        "random": ["random", "acak", "gatau", "gak jelas"]
    }
    
    for topic, keywords in topic_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            topics.append(topic)
    
    if not topics:
        topics = ["random"]
    
    # Ekstrak mentioned users
    mentioned_users = []
    for name in GRUP_MEMBERS.keys():
        if name.lower() in message_lower and name != user_name:
            mentioned_users.append(name)
    
    return {
        "type": message_type,
        "is_question": is_question,
        "is_teasing": is_teasing,
        "mood": mood,
        "topics": topics,
        "mentioned_users": mentioned_users,
        "length": len(message)
    }

def get_reply_chain(message_id, chat_id, depth=5):
    """Dapatkan rantai reply secara lengkap"""
    try:
        # Ambil message ini dan semua reply chainnya
        rows = db.execute(
            """
            WITH RECURSIVE reply_chain AS (
                -- Base: message yang dicari
                SELECT id, reply_to_msg_id, user_id, name, message, 0 as depth
                FROM messages 
                WHERE id = %s AND chat_id = %s
                
                UNION ALL
                
                -- Recursive: reply ke atas
                SELECT m.id, m.reply_to_msg_id, m.user_id, m.name, m.message, rc.depth + 1
                FROM messages m
                INNER JOIN reply_chain rc ON m.id = rc.reply_to_msg_id
                WHERE m.chat_id = %s AND rc.depth < %s
            )
            SELECT * FROM reply_chain ORDER BY depth DESC
            """,
            (message_id, str(chat_id), str(chat_id), depth),
            fetch="all"
        ) or []
        
        chain = []
        for row in rows:
            chain.append({
                "id": row[0],
                "reply_to": row[1],
                "user_id": row[2],
                "name": row[3],
                "message": row[4],
                "depth": row[5]
            })
        
        return chain
    except Exception as e:
        print(f"Error get_reply_chain: {e}")
        return []

def get_conversation_thread(chat_id, limit=30):
    """Ambil seluruh thread percakapan dengan pemahaman reply"""
    try:
        # Ambil messages dengan konteks reply
        rows = db.execute(
            """
            SELECT 
                m1.name,
                m1.message,
                m1.reply_to_name,
                m1.reply_to_message,
                m1.mood,
                m1.topics,
                m1.is_question,
                m1.is_teasing,
                m1.message_type,
                m1.timestamp,
                m2.name as replied_to_name,
                m2.message as replied_to_message
            FROM messages m1
            LEFT JOIN messages m2 ON m1.reply_to_msg_id = m2.id
            WHERE m1.chat_id = %s AND m1.is_sticker = FALSE
            ORDER BY m1.id DESC
            LIMIT %s
            """,
            (str(chat_id), limit),
            fetch="all"
        ) or []
        
        rows.reverse()
        
        conversation = []
        for row in rows:
            msg_data = {
                "speaker": row[0],
                "message": row[1],
                "reply_to_name": row[2] or row[10],  # reply_to_name atau replied_to_name
                "reply_to_message": row[3] or row[11],  # reply_to_message atau replied_to_message
                "mood": row[4],
                "topics": row[5],
                "is_question": row[6],
                "is_teasing": row[7],
                "type": row[8],
                "time": row[9].strftime("%H:%M") if row[9] else ""
            }
            conversation.append(msg_data)
        
        return conversation
    except Exception as e:
        print(f"Error get_conversation_thread: {e}")
        return []

def format_conversation_for_prompt(conversation):
    """Format percakapan untuk prompt dengan pemahaman reply chain"""
    if not conversation:
        return "(belum ada percakapan)"
    
    lines = []
    for i, msg in enumerate(conversation[-15:]):  # Ambil 15 pesan terakhir
        if msg["reply_to_name"]:
            # Ini adalah reply
            lines.append(f"[{msg['time']}] {msg['speaker']} → (ngebales {msg['reply_to_name']} yang bilang \"{msg['reply_to_message'][:50]}\"): {msg['message']}")
        else:
            # Bukan reply
            lines.append(f"[{msg['time']}] {msg['speaker']}: {msg['message']}")
    
    return "\n".join(lines)

def detect_conversation_patterns(conversation):
    """Deteksi pola percakapan"""
    patterns = {
        "is_ongoing_teasing": False,
        "current_topic": "random",
        "who_is_active": [],
        "reply_chains": [],
        "questions_unanswered": []
    }
    
    # Deteksi ledekan berantai
    teasing_count = sum(1 for msg in conversation[-10:] if msg["is_teasing"])
    if teasing_count >= 2:
        patterns["is_ongoing_teasing"] = True
    
    # Deteksi topik terakhir
    if conversation:
        last_msg = conversation[-1]
        if last_msg["topics"]:
            patterns["current_topic"] = last_msg["topics"][0]
    
    # Deteksi siapa yang aktif
    active_users = {}
    for msg in conversation[-10:]:
        active_users[msg["speaker"]] = active_users.get(msg["speaker"], 0) + 1
    patterns["who_is_active"] = [user for user, count in sorted(active_users.items(), key=lambda x: x[1], reverse=True)][:3]
    
    # Deteksi reply chains
    chains = []
    for i, msg in enumerate(conversation):
        if msg["reply_to_name"]:
            chains.append(f"{msg['speaker']} ngebales {msg['reply_to_name']}")
    patterns["reply_chains"] = chains[-5:]  # 5 reply chain terakhir
    
    return patterns

def save_message_with_context(chat_id, user_id, name, message, reply_to_msg_id=None, is_sticker=False):
    """Simpan pesan dengan analisis konteks lengkap"""
    try:
        # Analisis pesan
        analysis = analyze_message(message, name, reply_to_msg_id)
        
        # Dapatkan reply chain info
        reply_chain = None
        reply_chain_id = None
        reply_depth = 0
        reply_to_name = None
        reply_to_message = None
        reply_to_user_id = None
        
        if reply_to_msg_id:
            reply_info = db.execute(
                """
                SELECT name, message, user_id, reply_chain_id, reply_depth 
                FROM messages 
                WHERE id = %s AND chat_id = %s
                """,
                (reply_to_msg_id, str(chat_id)),
                fetch="one"
            )
            if reply_info:
                reply_to_name = reply_info[0]
                reply_to_message = reply_info[1]
                reply_to_user_id = reply_info[2]
                reply_chain_id = reply_info[3] or f"thread_{reply_to_msg_id}"
                reply_depth = (reply_info[4] or 0) + 1
        
        # Dapatkan konteks sebelum
        context_before = db.execute(
            """
            SELECT message FROM messages 
            WHERE chat_id = %s AND id < (SELECT COALESCE(MAX(id), 0) FROM messages)
            ORDER BY id DESC LIMIT 3
            """,
            (str(chat_id),),
            fetch="all"
        )
        context_before = [row[0] for row in context_before] if context_before else []
        
        # Simpan message
        db.execute(
            """
            INSERT INTO messages
            (chat_id, user_id, name, message, reply_to_msg_id, reply_chain_id, reply_depth,
             reply_to_name, reply_to_message, reply_to_user_id, is_sticker,
             mood, topics, mentioned_users, is_question, is_teasing, message_type,
             context_before)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (str(chat_id), str(user_id), name, message, reply_to_msg_id, reply_chain_id, reply_depth,
             reply_to_name, reply_to_message, reply_to_user_id, is_sticker,
             analysis["mood"], analysis["topics"], analysis["mentioned_users"],
             analysis["is_question"], analysis["is_teasing"], analysis["type"],
             str(context_before)),
            commit=True
        )
        
        # Dapatkan ID message yang baru disimpan
        msg_id = db.execute("SELECT LASTVAL()", fetch="value")
        
        # Simpan reply relationship
        if reply_to_msg_id:
            db.execute(
                """
                INSERT INTO reply_relationships
                (message_id, reply_to_message_id, chat_id, user_id, reply_to_user_id, depth, thread_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (msg_id, reply_to_msg_id, str(chat_id), str(user_id), reply_to_user_id, reply_depth, reply_chain_id),
                commit=True
            )
        
        # Update conversation thread
        if reply_chain_id:
            db.execute(
                """
                INSERT INTO conversation_threads (thread_id, chat_id, started_by, topic, participants)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE
                SET last_message_at = CURRENT_TIMESTAMP,
                    message_count = conversation_threads.message_count + 1,
                    participants = array(
                        SELECT DISTINCT unnest(conversation_threads.participants || %s)
                    )
                """,
                (reply_chain_id, str(chat_id), str(user_id), analysis["topics"][0] if analysis["topics"] else "random",
                 [name], [name]),
                commit=True
            )
        
        return msg_id
        
    except Exception as e:
        print(f"Error save_message_with_context: {e}")
        return None

# =============================
# SMART MESSAGE COLLECTOR - VERSI SUPER PAHAM KONTEKS
# =============================

class SmartMessageCollector:
    def __init__(self):
        self.pending_messages = []
        self.processing = False
        self.lock = asyncio.Lock()
        self.last_message_time = {}
        self.conversation_memory = {}
    
    async def add_message(self, event, sender_name, message_text, reply_context=None, msg_analysis=None):
        async with self.lock:
            self.pending_messages.append((event, sender_name, message_text, reply_context, msg_analysis))
            
            if not self.processing:
                self.processing = True
                asyncio.create_task(self.process_messages())
    
    async def process_messages(self):
        try:
            cooldown = float(db.get_setting('cooldown_seconds', '1.5'))
            max_messages = int(db.get_setting('max_collect_messages', '2'))
            
            await asyncio.sleep(cooldown)
            
            async with self.lock:
                if not self.pending_messages:
                    self.processing = False
                    return
                
                messages_to_process = self.pending_messages.copy()
                self.pending_messages.clear()
                self.processing = False
            
            # Analisis dan gabungin pesan dengan pemahaman konteks
            conversation_flow = []
            events = []
            all_reply_contexts = []
            all_analysis = []
            
            for i, (event, sender, msg, reply_ctx, analysis) in enumerate(messages_to_process[:max_messages]):
                if analysis:
                    all_analysis.append(analysis)
                    
                    if reply_ctx:
                        conversation_flow.append({
                            "sender": sender,
                            "message": msg,
                            "type": "reply",
                            "reply_to": reply_ctx.get("reply_to_name"),
                            "reply_message": reply_ctx.get("reply_to_message"),
                            "mood": analysis.get("mood"),
                            "topics": analysis.get("topics")
                        })
                        all_reply_contexts.append(reply_ctx)
                    else:
                        conversation_flow.append({
                            "sender": sender,
                            "message": msg,
                            "type": "normal",
                            "mood": analysis.get("mood"),
                            "topics": analysis.get("topics")
                        })
                    events.append(event)
            
            last_event = events[-1] if events else None
            
            if last_event and conversation_flow:
                await self.generate_context_aware_reply(last_event, conversation_flow, all_reply_contexts, all_analysis)
                
        except Exception as e:
            print(f"Error in process_messages: {e}")
            traceback.print_exc()
            async with self.lock:
                self.pending_messages.clear()
                self.processing = False
    
    async def generate_context_aware_reply(self, event, conversation_flow, reply_contexts, analyses):
        """Generate reply dengan pemahaman konteks super dalam"""
        try:
            sender = await event.get_sender()
            user_id = sender.id
            user_name = get_user_name(user_id)
            
            bot_status = get_bot_status()
            context_depth = bot_status.get("context_depth", 30)
            
            async with client.action(event.chat_id, 'typing'):
                # Ambil seluruh konteks percakapan
                full_conversation = get_conversation_thread(event.chat_id, context_depth)
                
                # Deteksi pola percakapan
                patterns = detect_conversation_patterns(full_conversation)
                
                # Pilih personality
                personality = next((p for p in ZAI_PERSONALITIES if p["name"] == bot_status["personality"]), ZAI_PERSONALITIES[0])
                
                # Format percakapan untuk prompt
                formatted_conversation = format_conversation_for_prompt(full_conversation)
                
                # Build prompt SUPER PAHAM KONTEKS
                prompt = build_context_aware_prompt(
                    user_name,
                    formatted_conversation,
                    conversation_flow,
                    reply_contexts,
                    analyses,
                    patterns,
                    personality
                )
                
                print(f"\n📝=== SUPER CONTEXT PROMPT ===")
                print(f"Personality: {personality['name']}")
                print(f"Pola: {patterns}")
                print(f"Flow: {conversation_flow}")
                print(f"========================\n")
                
                ai_reply = await generate_context_aware_response(prompt, conversation_flow, user_name)
                
                # Kalo gagal validasi, coba lagi
                if ai_reply is None:
                    print("⚠️ Reply gagal validasi, coba generate ulang...")
                    await asyncio.sleep(1)
                    ai_reply = await generate_context_aware_response(prompt, conversation_flow, user_name, retry=True)
                
                # Kalo masih gagal, pake fallback
                if ai_reply is None:
                    ai_reply = get_fallback_reply(conversation_flow, user_name)
                
                # Simpan reply Zai
                save_message_with_context(event.chat_id, "AI", "Zai", ai_reply)
                
                print(f"🤖 [Zai] {ai_reply}\n")
                
                # Random delay biar natural
                delay = random.uniform(0.8, 1.8)
                await asyncio.sleep(delay)
                await event.reply(ai_reply)
                
        except Exception as e:
            print(f"Error in generate_context_aware_reply: {e}")
            traceback.print_exc()

message_collector = SmartMessageCollector()

# =============================
# SUPER CONTEXT PROMPT ENGINE
# =============================

def build_context_aware_prompt(current_user, conversation_history, new_messages, reply_contexts, analyses, patterns, personality):
    """
    PROMPT YANG SUPER PAHAM KONTEKS - Ngerti reply chain, ngerti ledekan, ngerti topik
    """
    
    # Dapatkan info user
    user_info = GRUP_MEMBERS.get(current_user, GRUP_MEMBERS["Zai"])
    panggilan = random.choice(user_info.get("panggilan", ["bro"]))
    
    # Analisis pesan terbaru
    last_msg = new_messages[-1] if new_messages else {}
    last_sender = last_msg.get("sender", "")
    last_message = last_msg.get("message", "")
    
    # Deteksi tipe pesan terakhir
    is_call = len(new_messages) == 1 and re.search(r'^zai+!*$', last_message.lower().strip())
    is_teasing = any(msg.get("is_teasing") for msg in analyses if msg) or patterns.get("is_ongoing_teasing")
    is_reply_chain = len([ctx for ctx in reply_contexts if ctx]) > 0
    
    # Build konteks reply chain
    reply_chain_context = ""
    if reply_contexts and any(reply_contexts):
        reply_chain_context = "\n=== RANTAI REPLY YANG TERJADI ===\n"
        for i, ctx in enumerate(reply_contexts):
            if ctx:
                reply_chain_context += f"{ctx['sender_name']} NGEREPLY ke {ctx['reply_to_name']}: \"{ctx['message']}\"\n"
                reply_chain_context += f"→ {ctx['reply_to_name']} sebelumnya bilang: \"{ctx['reply_to_message']}\"\n\n"
    
    # Build topik yang sedang dibahas
    topics_discussed = set()
    for msg in new_messages:
        if msg.get("topics"):
            topics_discussed.update(msg["topics"])
    for analysis in analyses:
        if analysis and analysis.get("topics"):
            topics_discussed.update(analysis["topics"])
    
    topics_text = ", ".join(topics_discussed) if topics_discussed else "random"
    
    # Informasi siapa yang aktif
    active_users = patterns.get("who_is_active", [])
    active_text = ", ".join(active_users[:3]) if active_users else "semua orang"
    
    return f"""LO ADALAH ZAI - ANAK GAUL DI GRUP YANG SUPER PAHAM KONTEKS!

=== PERSONALITY LO SKRANG ===
Nama: {personality['name']}
Gaya bicara: {personality['style']}
Contoh: {personality['examples']}

=== PROFIL LENGKAP ANAK GRUP ===
• Rifkyy: Panggilan {GRUP_MEMBERS['Rifkyy']['panggilan']}, {GRUP_MEMBERS['Rifkyy']['sifat']}, hobi {GRUP_MEMBERS['Rifkyy']['hobi']}
• Adell: Panggilan {GRUP_MEMBERS['Adell']['panggilan']}, {GRUP_MEMBERS['Adell']['sifat']}, hobi {GRUP_MEMBERS['Adell']['hobi']}
• Dwayne John: Suka ngetik singkat, suka manggil "zai" doang
• Lo sendiri: Zai, suka ngledek balik, paham konteks

=== ATURAN MAIN YANG HARUS LO INGET BANGET ===

1. **PAHAM KONTEKS REPLY:**
   - Kalo ada yang ngereply pesan orang lain, lo HARUS paham itu lagi ngebales siapa dan apa
   - Jangan sampe lo ngejawab gak nyambung sama konteks reply
   - Kalo ada reply chain berantai, lo harus ngerti alurnya

2. **CARA NGELEDEK YANG BENER:**
   - Kalo dieledek: LANGSUNG LEDEK BALIK, jangan tanya kabar!
   - Contoh bales ledekan: "Wle, lu kalo ngeledek gak mutu" / "Hush, jangan ngeledek nanti lo yang kena"
   - Contoh SALAH: "Hai, ada yang bisa dibantu?" (INI CUSTOMER SERVICE BUKAN ZAI!)

3. **KALO DIPANGGIL "ZAI" DOANG:**
   ❌ Jangan panjang lebar kayak: "Hai! Ada yang ingin kamu ceritakan?"
   ✅ Balas singkat kayak: "Ngapain?" / "Apaan?" / "Woi?" / "Kenapa manggil?"
   - Kalo yang manggil Dwayne John (yang suka ngetik zai doang), lo harus tau ini udah kebiasaan dia

4. **JANGAN NGULANG PERTANYAAN:**
   - Kalo lo udah nanya sesuatu, jangan nanya hal yang sama lagi
   - Contoh SALAH: nanya "ada yang mau diceritain?" padahal udah ditanyain sebelumnya

5. **PAHAM TOPIK YANG SEDANG DIBAHAS:**
   - Lagi bahas Marvel? Pake analogi Marvel
   - Lagi bahas makanan? Sambungin ke makanan
   - Lagi random? Ikutan random tapi tetep nyambung

6. **PERHATIKAN POLA PERCAKAPAN:**
   - Yang paling aktif sekarang: {active_text}
   - Lagi pada ngapain: {patterns.get('current_topic', 'random')}
   - Ada ledek-ledekan: {'IYA' if is_teasing else 'TIDAK'}

=== KONTEKS PERCAKAPAN SEBELUMNYA ===
{conversation_history}

=== PESAN-PESAN BARU (YANG HARUS LO TANGGAPI) ===
{chr(10).join([f"{msg['sender']}: {msg['message']}" for msg in new_messages])}

{reply_chain_context}

=== TOPIK YANG SEDANG DIBAHAS ===
{topics_text}

=== INSTRUKSI KHUSUS ===
{f'⚠️ INI PENTING: Lagi ada ledek-ledekan! Balas ledek dengan ledek, JANGAN NANYA KABAR!' if is_teasing else ''}
{f'⚠️ INI PENTING: {last_sender} manggil lo doang! Balas singkat aja!' if is_call else ''}
{f'⚠️ INI PENTING: Ada reply chain! Pastikan jawaban lo nyambung sama yang di-reply!' if is_reply_chain else ''}

RESPON LO (ZAI) - LANGSUNG GAS, JANGAN PAKE "HAI" ATAU "HALO":
"""

# =============================
# AI RESPONSE GENERATOR - VERSI CONTEXT AWARE
# =============================

async def generate_context_aware_response(prompt, conversation_flow, user_name, retry=False):
    """Generate response dengan validasi konteks"""
    max_retries = 3 if not retry else 2
    
    temperature = float(db.get_setting('temperature', '0.85'))
    max_tokens = int(db.get_setting('max_response_tokens', '150'))
    top_p = float(db.get_setting('top_p', '0.9'))
    
    for attempt in range(max_retries):
        try:
            client_info = ai_manager.get_current_client()
            
            if not client_info:
                return get_fallback_reply(conversation_flow, user_name)
            
            current_token = client_info["token"]
            print(f"🤖 Attempt {attempt + 1} using token: {current_token[:10]}...")
            
            start_time = datetime.now()
            
            response = client_info["client"].chat.completions.create(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p
            )
            
            reply = response.choices[0].message.content
            reply = reply.strip('"').strip("'").strip()
            
            # Validasi dengan konteks
            validated = validate_reply_with_context(reply, conversation_flow, user_name)
            
            if validated:
                # Log success
                response_time = (datetime.now() - start_time).total_seconds()
                db.execute(
                    "INSERT INTO api_usage (token_prefix, success, response_time) VALUES (%s, %s, %s)",
                    (current_token[:10], True, response_time),
                    commit=True
                )
                
                ai_manager.mark_token_success(current_token)
                return validated
            else:
                print("⚠️ Reply gagal validasi konteks")
                if attempt < max_retries - 1:
                    ai_manager.rotate_token()
                    await asyncio.sleep(1)
                    continue
                
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ Error: {error_msg[:100]}")
            
            db.execute(
                "INSERT INTO api_usage (token_prefix, success, error_message) VALUES (%s, %s, %s)",
                (current_token[:10], False, error_msg[:200]),
                commit=True
            )
            
            if attempt < max_retries - 1:
                ai_manager.rotate_token()
                await asyncio.sleep(1)
                continue
    
    return None

def validate_reply_with_context(reply, conversation_flow, user_name):
    """Validasi reply dengan konteks percakapan"""
    
    # Cek kata-kata terlarang (customer service mode)
    forbidden_phrases = [
        "hai", "halo", "hey", "hi",
        "ada yang bisa", "ada yang ingin", "ada yang mau",
        "saya siap", "gue siap", "siap dengerin",
        "ceritain", "cerita", "kabar",
        "😄", "🌟", "🎉", "🎶",  # Emoji lebay
    ]
    
    reply_lower = reply.lower()
    
    for phrase in forbidden_phrases:
        if phrase in reply_lower:
            print(f"❌ Reply mengandung '{phrase}'")
            return None
    
    # Cek panjang reply
    words = reply.split()
    if len(words) > 25:  # Kebanyakan
        print(f"❌ Reply kepanjangan ({len(words)} kata)")
        return None
    
    # Cek kalo dipanggil doang, harus singkat
    if len(conversation_flow) == 1 and re.search(r'^zai+!*$', conversation_flow[0]["message"].lower().strip()):
        if len(words) > 10:
            print("❌ Reply kepanjangan untuk manggil doang")
            return None
    
    # Cek kalo ada ledekan, harus ledek balik
    is_teasing = any(msg.get("is_teasing") for msg in conversation_flow if isinstance(msg, dict))
    if is_teasing:
        teasing_responses = ["wle", "ledek", "hush", "cis", "ciah", "wkwk"]
        if not any(word in reply_lower for word in teasing_responses):
            print("❌ Lagi ledekan tapi reply gak nyambung")
            return None
    
    # Bersihin reply dari sisa-sisa formatting
    reply = re.sub(r'\[\s*\w+\s*\]', '', reply)  # Hapus [mood: happy]
    reply = re.sub(r'\s+', ' ', reply).strip()
    
    return reply

def get_fallback_reply(conversation_flow, user_name):
    """Fallback reply kalo AI error"""
    
    # Deteksi konteks buat fallback yang relevan
    last_msg = conversation_flow[-1] if conversation_flow else {}
    last_sender = last_msg.get("sender", "")
    last_text = last_msg.get("message", "").lower()
    
    # Kalo dipanggil doang
    if re.search(r'^zai+!*$', last_text):
        return random.choice([
            "Ngapain?",
            "Apaan?",
            "Woi?",
            "Kenapa manggil?",
            "Lah?"
        ])
    
    # Kalo lagi ledekan
    if any(word in last_text for word in ["ledek", "wle", "bloon"]):
        return random.choice([
            f"Wle, {last_sender} kalo ngeledek gak mutu",
            f"Hush, jangan ngeledek, nanti lo yang kena",
            f"Cis, ledek mulu kerjaan lo"
        ])
    
    # Kalo nanya sesuatu
    if "?" in last_text:
        return random.choice([
            f"Hmm, gatau dah {user_name}",
            f"Waduh, bingung gw",
            f"Nanya mulu sih"
        ])
    
    # Default random
    return random.choice([
        "Wkwk",
        "Lah",
        "Njir",
        "Gaskeun",
        "Santuy"
    ])

# =============================
# COMMAND HANDLERS
# =============================

HELP_TEXT = """
**🔰 ZAI - SUPER CONTEXT AWARE EDITION** 

**🤖 Commands untuk Semua User:**
• `!zai [pesan]` - Ngobrol dengan Zai
• `/status` - Lihat status bot
• `/personality` - Lihat personality Zai sekarang

**👑 Admin Commands:**
• `/tokens` - Lihat daftar token
• `/add_token [token]` - Tambah token baru
• `/remove_token [prefix]` - Hapus token
• `/stats` - Statistik lengkap
• `/switch` - Ganti token aktif
• `/settings` - Lihat semua pengaturan
• `/set [key] [value]` - Ubah pengaturan
• `/personality [name]` - Ganti personality Zai
   Options: Si Gaul, Si Tukang Ledek, Si Random, Si Ngegas
• `/on` - Aktifkan bot
• `/off` - Nonaktifkan bot
• `/mode auto` - Mode Auto (jawab semua pesan)
• `/mode trigger` - Mode Trigger (jawab pake !zai)

**⚙️ FITUR SUPER CONTEXT AWARE:**
• ✅ PAHAM REPLY CHAIN - Tau siapa reply ke siapa
• ✅ PAHAM KONTEKS - Ngerti kalo lagi ledekan atau nanya
• ✅ BALAS SESUAI - Kalo dipanggil doang, balas singkat
• ✅ GAK FORMAL - Bukan customer service!
• ✅ INGAT POLA - Tau kebiasaan tiap user
• ✅ AUTO MIGRATION - Database update otomatis

**📝 CONTOH:**
• User: "zai" → Zai: "Ngapain?"
• User: "ledek Zai" → Zai: "Wle, lu yang ledek gak mutu"
• User reply ke user lain → Zai paham konteks reply

**🔥 GASKEUN!**
"""

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
**📊 ZAI STATUS - CONTEXT AWARE**

**Status:** {status_text}
**Mode:** {mode_text}
**Personality:** {bot_status['personality']}
**Context Depth:** {bot_status['context_depth']} messages

**Token Aktif:** {stats['active_tokens']}/{stats['total_tokens']}
**Request 24h:** {stats['requests_24h']}
**Success Rate:** {success_rate:.1f}%

**Fitur Aktif:**
✅ Paham reply chain
✅ Balas sesuai konteks
✅ Gak formal kayak CS
✅ Auto migration

Ketik /help buat liat command.
"""
        await event.reply(message)
    except Exception as e:
        print(f"Error in status_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/personality(?:\s+(.+))?$'))
async def personality_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not event.pattern_match.group(1):
        bot_status = get_bot_status()
        personalities = [p["name"] for p in ZAI_PERSONALITIES]
        message = f"""
**🎭 PERSONALITY ZAI SEKARANG:**
• `{bot_status['personality']}`

**📋 DAFTAR PERSONALITY:**
• `Si Gaul` - Santuy
• `Si Tukang Ledek` - Hobi ngegas
• `Si Random` - Suka ngelantur tapi nyambung
• `Si Ngegas` - Cepat nanggepin

Gunakan: `/personality [nama]`
"""
        await event.reply(message)
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa ganti personality")
        return
    
    try:
        personality_name = event.pattern_match.group(1).strip()
        
        valid_names = [p["name"] for p in ZAI_PERSONALITIES]
        if personality_name not in valid_names:
            await event.reply(f"❌ Personality harus salah satu: {', '.join(valid_names)}")
            return
        
        set_bot_personality(personality_name, event.sender_id)
        await event.reply(f"✅ Personality Zai diganti jadi: **{personality_name}**")
        
    except Exception as e:
        print(f"Error in personality_handler: {e}")
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

@client.on(events.NewMessage(pattern=r'^/stats$'))
async def stats_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin")
        return
    
    try:
        stats = ai_manager.get_stats()
        
        hourly = db.execute(
            """
            SELECT 
                DATE_TRUNC('hour', timestamp) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as success
            FROM api_usage
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 6
            """,
            fetch="all"
        ) or []
        
        message = f"""
**📈 STATISTIK 24 JAM**

**Token:**
• Total: {stats['total_tokens']}
• Aktif: {stats['active_tokens']}
• Bermasalah: {stats['problematic']}

**Usage:**
• Request: {stats['requests_24h']}
• Sukses: {stats['success_24h']}
• Avg Response: {stats['avg_response']:.2f}s

**Per Jam:**
"""
        for hour, total, success in hourly:
            rate = (success/total*100) if total > 0 else 0
            message += f"• {hour.strftime('%H:00')}: {total} req ({rate:.1f}%)\n"
        
        await event.reply(message)
        
    except Exception as e:
        print(f"Error in stats_handler: {e}")
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
                      'max_collect_messages', 'context_depth']
        
        if key not in valid_keys:
            await event.reply(f"❌ Key harus: {', '.join(valid_keys)}")
            return
        
        # Validasi nilai
        if key in ['temperature', 'top_p', 'presence_penalty', 'frequency_penalty']:
            val = float(value)
            if val < 0.0 or val > 1.0:
                await event.reply(f"❌ {key} harus antara 0.0 - 1.0")
                return
        elif key in ['max_history', 'max_response_tokens', 'max_collect_messages', 'context_depth']:
            val = int(value)
            if val < 1 or val > 100:
                await event.reply(f"❌ {key} harus 1-100")
                return
        
        db.execute(
            "UPDATE settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = %s",
            (value, key),
            commit=True
        )
        
        await event.reply(f"✅ `{key}` = `{value}`")
        
    except ValueError:
        await event.reply(f"❌ {key} harus angka")
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
        await event.reply(f"✅ Zai ON - Mode {mode}, Personality: {status['personality']}")
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
        await event.reply("❌ Zai OFF - Sampai jumpa! 👋")
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
        set_auto_reply_mode(True, event.sender_id)
        await event.reply("✅ Mode AUTO: Zai bakal jawab SEMUA pesan!")
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
        set_auto_reply_mode(False, event.sender_id)
        await event.reply("✅ Mode TRIGGER: Zai jawab pake !zai")
    except Exception as e:
        print(f"Error in mode_trigger_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

# =============================
# MAIN MESSAGE HANDLER - SUPER CONTEXT AWARE
# =============================

@client.on(events.NewMessage)
async def message_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        # Skip commands
        if event.raw_text.startswith('/'):
            return
        
        bot_status = get_bot_status()
        
        if not bot_status['is_active']:
            return
        
        should_respond = False
        
        if bot_status['auto_reply']:
            should_respond = True
        else:
            if (event.raw_text.lower().startswith("!zai") or 
                event.raw_text.lower() == "zai" or
                "zai" in event.raw_text.lower().split()):
                should_respond = True
        
        if not should_respond:
            return
        
        sender = await event.get_sender()
        user_id = sender.id
        user_name = get_user_name(user_id)
        
        is_sticker = bool(event.sticker)
        
        # Save user
        save_user(user_id, user_name, event.raw_text)
        
        message = event.raw_text
        
        if is_sticker:
            save_message_with_context(event.chat_id, user_id, user_name, "[Sticker]", event.reply_to_msg_id, True)
            print(f"💬 [{user_name}] kirim sticker (skip)")
            return
        
        # Analisis pesan
        analysis = analyze_message(message, user_name, event.reply_to_msg_id)
        
        # Ambil konteks reply
        reply_context = None
        if event.reply_to_msg_id:
            reply_info = db.execute(
                """
                SELECT name, message, user_id FROM messages 
                WHERE id = %s AND chat_id = %s
                """,
                (event.reply_to_msg_id, str(event.chat_id)),
                fetch="one"
            )
            if reply_info:
                reply_context = {
                    "reply_to_name": reply_info[0],
                    "reply_to_message": reply_info[1],
                    "reply_to_user_id": reply_info[2],
                    "sender_name": user_name,
                    "message": message
                }
                print(f"🔗 {user_name} REPLY ke {reply_info[0]}: \"{reply_info[1][:50]}\"")
        
        # Bersihin trigger !zai dari pesan
        clean_message = re.sub(r'^!zai\s*', '', message, flags=re.IGNORECASE).strip()
        if not clean_message:
            clean_message = message
        
        # Simpan pesan dengan konteks
        msg_id = save_message_with_context(event.chat_id, user_id, user_name, clean_message, event.reply_to_msg_id, False)
        
        print(f"\n💬 [{user_name}] {clean_message[:100]} [type: {analysis['type']}]")
        
        # Kirim ke smart collector
        await message_collector.add_message(event, user_name, clean_message, reply_context, analysis)
        
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
            bot_status = get_bot_status()
            
            success_rate = (stats['success_24h']/stats['requests_24h']*100) if stats['requests_24h'] > 0 else 0
            
            print(f"\n📊 HOURLY STATS [{datetime.now().strftime('%H:%M')}]")
            print(f"Personality: {bot_status['personality']}")
            print(f"Context Depth: {bot_status['context_depth']}")
            print(f"Tokens: {stats['active_tokens']}/{stats['total_tokens']}")
            print(f"Current: {current['token'][:10] if current else 'None'}")
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
    print("=" * 70)
    print("🤖 ZAI - SUPER CONTEXT AWARE EDITION V3.0")
    print("=" * 70)
    
    bot_status = get_bot_status()
    mode_text = "AUTO" if bot_status['auto_reply'] else "TRIGGER"
    status_text = "AKTIF" if bot_status['is_active'] else "NONAKTIF"
    
    cooldown = db.get_setting('cooldown_seconds', '1.5')
    
    print(f"📊 Status: {status_text} | Mode: {mode_text}")
    print(f"📊 Personality: {bot_status['personality']}")
    print(f"📊 Context Depth: {bot_status['context_depth']} messages")
    print(f"📊 Token Aktif: {len(ai_manager.get_active_tokens())}")
    print(f"📊 Cooldown: {cooldown}s")
    print(f"👑 Admins: {ADMIN_IDS}")
    print("=" * 70)
    print("✅ FITUR CONTEXT AWARE AKTIF:")
    print("  • 🧠 Paham reply chain - tau siapa ngebales siapa")
    print("  • 🔗 Ngerti konteks percakapan antar user")
    print("  • 🎯 Balas sesuai - kalo dipanggil doang balas singkat")
    print("  • 😤 Bisa ledek balik - kalo dieledek, dilawan")
    print("  • 📝 Gak formal - bukan customer service")
    print("  • 🔄 Auto migration database")
    print("=" * 70)
    print("📝 Ketik /help buat liat menu")
    print("=" * 70)
    
    # Start periodic tasks
    asyncio.create_task(periodic_stats())
    asyncio.create_task(health_check())
    
    await client.start()
    await client.run_until_disconnected()

# Cleanup on exit
import atexit

@atexit.register
def cleanup():
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

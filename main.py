import os
import json
import psycopg2
import asyncio
import traceback
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

            # Insert default settings
            self.cur.execute("""
            INSERT INTO settings (key, value) VALUES 
            ('current_token_index', '0'),
            ('max_history', '30'),
            ('max_response_tokens', '150'),
            ('temperature', '0.7'),
            ('auto_reply_mode', 'false')
            ON CONFLICT (key) DO NOTHING
            """)

            # Insert default bot status
            self.cur.execute("""
            INSERT INTO bot_status (id, is_active, auto_reply) 
            VALUES (1, TRUE, FALSE)
            ON CONFLICT (id) DO NOTHING
            """)

            self.conn.commit()
            print("✅ Database tables initialized")
            
        except Exception as e:
            print(f"❌ Table initialization error: {e}")
            self.conn.rollback()
    
    def execute(self, query, params=None, commit=False, fetch=False):
        """Eksekusi query dengan error handling"""
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
                # Koneksi error, coba reconnect
                print(f"Database operational error: {e}")
                self.connect()
                retry_count += 1
                
            except psycopg2.InFailedSqlTransaction:
                # Transaction error, rollback dan coba lagi
                print("Failed transaction, rolling back...")
                self.conn.rollback()
                retry_count += 1
                
            except Exception as e:
                print(f"Database error: {e}")
                self.conn.rollback()
                raise e
        
        raise Exception("Max retries reached for database operation")
    
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
            value = db.execute(
                "SELECT value FROM settings WHERE key = 'current_token_index'",
                fetch="value"
            )
            if value:
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
# MEMORY SYSTEM
# =============================

def save_message(chat_id, user_id, name, message):
    try:
        db.execute(
            """
            INSERT INTO messages
            (chat_id, user_id, name, message)
            VALUES (%s,%s,%s,%s)
            """,
            (str(chat_id), str(user_id), name, message),
            commit=True
        )
    except Exception as e:
        print(f"Error save_message: {e}")

def get_last_messages(chat_id, limit=30):
    try:
        rows = db.execute(
            """
            SELECT name, message FROM messages
            WHERE chat_id=%s
            ORDER BY id DESC
            LIMIT %s
            """,
            (str(chat_id), limit),
            fetch="all"
        ) or []
        
        rows.reverse()
        history = ""
        for name, msg in rows:
            history += f"{name}: {msg}\n"
        return history
        
    except Exception as e:
        print(f"Error get_last_messages: {e}")
        return ""

# =============================
# AI PROMPT
# =============================

def build_prompt(user_name, history, user_message):
    # Get temperature from settings
    try:
        temp = float(db.execute(
            "SELECT value FROM settings WHERE key = 'temperature'",
            fetch="value"
        ) or 0.7)
    except:
        temp = 0.7
    
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

Balas dengan natural, santai, dan hidup. Maksimal 3 kalimat.
"""

# =============================
# AI RESPONSE
# =============================

async def generate_ai_response(prompt):
    """Generate AI response dengan auto rotate"""
    
    max_retries = 10
    
    for attempt in range(max_retries):
        try:
            client_info = ai_manager.get_current_client()
            
            if not client_info:
                return "❌ Tidak ada token aktif. Tambahkan token dengan /add_token"
            
            current_token = client_info["token"]
            print(f"🤖 Attempt {attempt + 1} using token: {current_token[:10]}...")
            
            # Record start time
            start_time = datetime.now()
            
            response = client_info["client"].chat.completions.create(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            
            reply = response.choices[0].message.content
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Log success
            try:
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
            
            # Kalau error quota habis
            if "402" in error_msg or "Payment Required" in error_msg:
                result = ai_manager.mark_token_failed(current_token)
                print(result)
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            else:
                # Error lain, coba lagi dengan token sama
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
    
    return "❌ Semua token error. Cek dengan /tokens"

# =============================
# HELP MENU
# =============================

HELP_TEXT = """
**🔰 USTADZ AI - BOT MANAGER**

**🤖 Commands untuk Semua User:**
• `!zai [pesan]` - Ngobrol dengan Ustadz Zai
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

**⚙️ Settings yang bisa diubah:**
• `max_history` - Jumlah pesan diingat (default: 30)
• `max_response_tokens` - Panjang respons (default: 150)
• `temperature` - Kreativitas AI (0.1 - 1.0, default: 0.7)

**📊 Status Emoji:**
✅ = Active & Sehat
⚠️ = Active tapi pernah error
❌ = Inactive/Disabled

**Contoh:**
• `/add_token hf_abc123... token utama`
• `/remove_token hf_abc123`
• `/set temperature 0.8`
"""

# =============================
# COMMAND HANDLERS
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
        
        mode_text = "AUTO (semua pesan)" if bot_status['auto_reply'] else "TRIGGER (!zai atau sebutan)"
        status_text = "AKTIF ✅" if bot_status['is_active'] else "NONAKTIF ❌"
        
        message = f"""
**📊 BOT STATUS**

**Bot:**
• Status: {status_text}
• Mode: {mode_text}

**Token:**
• Active: {stats['active_tokens']}/{stats['total_tokens']}
• Problematic: {stats['problematic']}
• Current: {current['token'][:10] if current else 'None'}...

**Usage (24h):**
• Requests: {stats['requests_24h']}
• Success: {stats['success_24h']} ({success_rate:.1f}%)
• Avg Response: {stats['avg_response']:.2f}s

Gunakan `/help` untuk commands.
"""
        await event.reply(message)
    except Exception as e:
        print(f"Error in status_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/tokens$'))
async def tokens_handler(event):
    """Show all tokens (admin only)"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa melihat token")
        return
    
    try:
        tokens = ai_manager.get_token_list()
        current = ai_manager.get_current_client()
        
        if not tokens:
            await event.reply("❌ Belum ada token. Tambah dengan /add_token")
            return
        
        message = "**🔑 DAFTAR TOKEN**\n\n"
        
        for token_prefix, is_active, failures, last_used, added_by, added_at, notes in tokens:
            # Status emoji
            if not is_active:
                status = "❌"
            elif failures > 0:
                status = "⚠️"
            else:
                status = "✅"
            
            # Current indicator
            current_mark = " 👈 CURRENT" if current and token_prefix == current['token'][:10] else ""
            
            # Last used
            last = last_used.strftime("%d/%m %H:%M") if last_used else "Never"
            
            message += f"{status} `{token_prefix}...`{current_mark}\n"
            message += f"   ├ Failures: {failures}\n"
            message += f"   ├ Last: {last}\n"
            message += f"   ├ Added: {added_at.strftime('%d/%m')} by {added_by}\n"
            if notes:
                message += f"   └ Notes: {notes}\n"
            else:
                message += "\n"
        
        # Split if too long
        if len(message) > 3500:
            parts = [message[i:i+3500] for i in range(0, len(message), 3500)]
            for part in parts:
                await event.reply(part)
        else:
            await event.reply(message)
            
    except Exception as e:
        print(f"Error in tokens_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/add_token (.+)$'))
async def add_token_handler(event):
    """Add new token"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa menambah token")
        return
    
    try:
        # Parse arguments
        args = event.pattern_match.group(1).strip().split(maxsplit=1)
        token = args[0]
        notes = args[1] if len(args) > 1 else ""
        
        # Validate token format
        if not token.startswith('hf_'):
            await event.reply("❌ Token harus dimulai dengan 'hf_'")
            return
        
        success, message = ai_manager.add_token(token, event.sender_id, notes)
        
        if success:
            await event.reply(f"✅ {message}\nToken: `{token[:10]}...`")
        else:
            await event.reply(f"❌ Gagal: {message}")
            
    except Exception as e:
        print(f"Error in add_token_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/remove_token (.+)$'))
async def remove_token_handler(event):
    """Remove token"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa menghapus token")
        return
    
    try:
        token_prefix = event.pattern_match.group(1).strip()
        success, message = ai_manager.remove_token(token_prefix)
        
        if success:
            await event.reply(f"✅ {message}")
        else:
            await event.reply(f"❌ {message}")
            
    except Exception as e:
        print(f"Error in remove_token_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/stats$'))
async def stats_handler(event):
    """Show detailed stats"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa melihat stats")
        return
    
    try:
        # Get stats from database
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
            LIMIT 24
            """,
            fetch="all"
        ) or []
        
        per_token = db.execute(
            """
            SELECT 
                token_prefix,
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as success,
                AVG(response_time) as avg_time
            FROM api_usage
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY token_prefix
            ORDER BY total DESC
            """,
            fetch="all"
        ) or []
        
        top_errors = db.execute(
            """
            SELECT 
                error_message,
                COUNT(*)
            FROM api_usage
            WHERE success = false 
            AND timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY error_message
            ORDER BY COUNT(*) DESC
            LIMIT 5
            """,
            fetch="all"
        ) or []
        
        message = "**📈 STATISTIK LENGKAP (24h)**\n\n"
        
        if hourly:
            message += "**Per Jam:**\n"
            for hour, total, success in hourly[:6]:  # Show last 6 hours
                rate = (success/total*100) if total > 0 else 0
                message += f"• {hour.strftime('%H:00')}: {total} req ({rate:.1f}% success)\n"
        
        if per_token:
            message += "\n**Per Token:**\n"
            for token, total, success, avg in per_token:
                rate = (success/total*100) if total > 0 else 0
                message += f"• `{token}...`: {total} req, {rate:.1f}% success, {avg:.2f}s\n"
        
        if top_errors:
            message += "\n**Top Errors:**\n"
            for error, count in top_errors:
                message += f"• {error[:50]}... ({count}x)\n"
        
        await event.reply(message)
        
    except Exception as e:
        print(f"Error in stats_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/switch$'))
async def switch_handler(event):
    """Switch to next token"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa switch token")
        return
    
    try:
        if ai_manager.rotate_token():
            current = ai_manager.get_current_client()
            await event.reply(f"🔄 Berpindah ke token: `{current['token'][:10]}...`")
        else:
            await event.reply("❌ Tidak ada token aktif")
    except Exception as e:
        print(f"Error in switch_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/settings$'))
async def settings_handler(event):
    """Show current settings"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        settings = db.execute(
            "SELECT key, value FROM settings ORDER BY key",
            fetch="all"
        ) or []
        
        bot_status = get_bot_status()
        
        message = "**⚙️ PENGATURAN BOT**\n\n"
        for key, value in settings:
            message += f"• `{key}` = `{value}`\n"
        
        message += f"\n**Bot Status:**\n"
        message += f"• `is_active` = `{bot_status['is_active']}`\n"
        message += f"• `auto_reply` = `{bot_status['auto_reply']}`\n"
        
        message += "\nGunakan `/set [key] [value]` untuk mengubah"
        
        await event.reply(message)
        
    except Exception as e:
        print(f"Error in settings_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/set (\w+) (.+)$'))
async def set_handler(event):
    """Change setting"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa mengubah settings")
        return
    
    try:
        key = event.pattern_match.group(1)
        value = event.pattern_match.group(2)
        
        # Validate
        valid_keys = ['max_history', 'max_response_tokens', 'temperature']
        if key not in valid_keys:
            await event.reply(f"❌ Key harus salah satu: {', '.join(valid_keys)}")
            return
        
        # Validate values
        if key == 'temperature':
            try:
                val = float(value)
                if val < 0.1 or val > 1.0:
                    await event.reply("❌ Temperature harus antara 0.1 - 1.0")
                    return
            except:
                await event.reply("❌ Temperature harus angka")
                return
        
        elif key in ['max_history', 'max_response_tokens']:
            try:
                val = int(value)
                if val < 10 or val > 500:
                    await event.reply(f"❌ {key} harus antara 10 - 500")
                    return
            except:
                await event.reply(f"❌ {key} harus angka")
                return
        
        # Update
        db.execute(
            "UPDATE settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = %s",
            (value, key),
            commit=True
        )
        
        await event.reply(f"✅ `{key}` diubah menjadi `{value}`")
        
    except Exception as e:
        print(f"Error in set_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/test_token (.+)$'))
async def test_token_handler(event):
    """Test specific token"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa test token")
        return
    
    try:
        token_prefix = event.pattern_match.group(1).strip()
        
        # Find token
        token = db.execute(
            "SELECT token FROM hf_tokens WHERE token_prefix = %s AND is_active = TRUE",
            (token_prefix,),
            fetch="value"
        )
        
        if not token:
            await event.reply(f"❌ Token dengan prefix `{token_prefix}` tidak ditemukan atau tidak aktif")
            return
        
        await event.reply(f"🔄 Testing token `{token_prefix}...`...")
        
        try:
            client = InferenceClient(token=token)
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[{"role": "user", "content": "Halo, test"}],
                max_tokens=20
            )
            await event.reply(f"✅ Token berhasil! Response: {response.choices[0].message.content}")
        except Exception as e:
            await event.reply(f"❌ Token error: {str(e)[:200]}")
            
    except Exception as e:
        print(f"Error in test_token_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

# =============================
# FIXED CLEAN LOGS HANDLER
# =============================

@client.on(events.NewMessage(pattern=r'^/clean_logs(?: (\d+))?$'))
async def clean_logs_handler(event):
    """Clean old logs"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa membersihkan logs")
        return
    
    try:
        days = event.pattern_match.group(1)
        days = int(days) if days else 7
        
        # PERBAIKAN: Cara yang benar untuk INTERVAL di PostgreSQL
        # METHOD 1: Pakai string formatting dengan quotes
        db.execute(
            "DELETE FROM api_usage WHERE timestamp < NOW() - INTERVAL '%s days'",
            (days,),
            commit=True
        )
        
        deleted = db.cur.rowcount
        
        await event.reply(f"✅ {deleted} log entries lebih dari {days} hari telah dihapus")
        
    except Exception as e:
        print(f"Error in clean_logs_handler: {e}")
        traceback.print_exc()
        await event.reply(f"❌ Error: {str(e)[:100]}")

# =============================
# BOT CONTROL COMMANDS
# =============================

@client.on(events.NewMessage(pattern=r'^/on$'))
async def turn_on_handler(event):
    """Turn bot on"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa menghidupkan bot")
        return
    
    try:
        status = set_bot_active(True, event.sender_id)
        mode_text = "AUTO" if status['auto_reply'] else "TRIGGER"
        await event.reply(f"✅ Bot diaktifkan! Mode: {mode_text}")
    except Exception as e:
        print(f"Error in turn_on_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/off$'))
async def turn_off_handler(event):
    """Turn bot off"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa mematikan bot")
        return
    
    try:
        set_bot_active(False, event.sender_id)
        await event.reply("❌ Bot dimatikan. Tidak akan merespons pesan.")
    except Exception as e:
        print(f"Error in turn_off_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/mode auto$'))
async def mode_auto_handler(event):
    """Set auto reply mode (reply to all messages)"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa mengubah mode")
        return
    
    try:
        status = set_auto_reply_mode(True, event.sender_id)
        if status['is_active']:
            await event.reply("✅ Mode AUTO: Bot akan menjawab SEMUA pesan!")
        else:
            await event.reply("✅ Mode diset ke AUTO, tapi bot masih OFF. Ketik /on untuk mengaktifkan.")
    except Exception as e:
        print(f"Error in mode_auto_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

@client.on(events.NewMessage(pattern=r'^/mode trigger$'))
async def mode_trigger_handler(event):
    """Set trigger mode (reply only with !zai or mentions)"""
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    if not is_admin(event.sender_id):
        await event.reply("❌ Hanya admin yang bisa mengubah mode")
        return
    
    try:
        status = set_auto_reply_mode(False, event.sender_id)
        if status['is_active']:
            await event.reply("✅ Mode TRIGGER: Bot hanya menjawab dengan !zai atau sebutan")
        else:
            await event.reply("✅ Mode diset ke TRIGGER, tapi bot masih OFF. Ketik /on untuk mengaktifkan.")
    except Exception as e:
        print(f"Error in mode_trigger_handler: {e}")
        await event.reply(f"❌ Error: {str(e)[:100]}")

# =============================
# MAIN EVENT HANDLER
# =============================

@client.on(events.NewMessage)
async def message_handler(event):
    if event.chat_id != ALLOWED_CHAT_ID:
        return
    
    try:
        # Skip commands (already handled)
        if event.raw_text.startswith('/'):
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
            if (event.raw_text.startswith("!zai") or 
                "ustadz zai" in event.raw_text.lower() or
                "zai" in event.raw_text.lower()):
                should_respond = True
        
        if not should_respond:
            return
        
        sender = await event.get_sender()
        user_id = sender.id
        user_name = get_user_name(user_id)
        
        save_user(user_id, user_name)
        message = event.raw_text
        
        print(f"[{user_name}] {message}")
        
        save_message(event.chat_id, user_id, user_name, message)
        
        # Get max_history from settings
        max_history = int(db.execute(
            "SELECT value FROM settings WHERE key = 'max_history'",
            fetch="value"
        ) or 30)
        
        async with client.action(event.chat_id, 'typing'):
            history = get_last_messages(event.chat_id, max_history)
            prompt = build_prompt(user_name, history, message)
            
            ai_reply = await generate_ai_response(prompt)
            
            save_message(event.chat_id, "AI", "Zai", ai_reply)
            
            await asyncio.sleep(1)
            await event.reply(ai_reply)
            
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
            
        except Exception as e:
            print(f"Error in periodic_stats: {e}")
            await asyncio.sleep(60)  # Wait a bit before retrying

# =============================
# HEALTH CHECK
# =============================

async def health_check():
    """Periodic health check for database"""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            
            # Test database connection
            db.execute("SELECT 1", fetch="value")
            
        except Exception as e:
            print(f"Health check error: {e}")
            # Try to reconnect
            try:
                db.connect()
            except:
                pass

# =============================
# START BOT
# =============================

async def main():
    print("🤖 Ustad Zai - Full Management via Telegram")
    print("=" * 50)
    
    bot_status = get_bot_status()
    mode_text = "AUTO (semua pesan)" if bot_status['auto_reply'] else "TRIGGER (!zai atau sebutan)"
    status_text = "AKTIF" if bot_status['is_active'] else "NONAKTIF"
    
    print(f"📊 Bot Status: {status_text}")
    print(f"📊 Mode: {mode_text}")
    print(f"📊 Active Tokens: {len(ai_manager.get_active_tokens())}")
    print(f"👑 Admins: {ADMIN_IDS}")
    print(f"📝 Ketik /help untuk menu")
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
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        cleanup()

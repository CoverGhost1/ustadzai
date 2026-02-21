import os
import random
import asyncio
from telethon import TelegramClient, events
from collections import deque
import json
from huggingface_hub import InferenceClient
from datetime import datetime
import time

# =============================
# CONFIG
# =============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
HF_TOKEN = os.getenv("HF_TOKEN")

# Gunakan model yang lebih kecil dan cepat
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"  # Model chat yang lebih natural
# Alternatif: "Qwen/Qwen2.5-7B-Instruct" atau "meta-llama/Llama-2-7b-chat-hf"
ALLOWED_CHAT_ID = -1003123683403
HISTORY_FILE = "group_history.json"

# =============================
# INIT TELEGRAM & HF CLIENT
# =============================
client = TelegramClient('anon_ai', api_id, api_hash)

# Initialize HF client
hf_client = InferenceClient(
    model=MODEL_ID,
    token=HF_TOKEN,
)

# =============================
# MEMORY SYSTEM
# =============================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                raw = json.load(f)
                return {str(k): deque(v, maxlen=15) for k, v in raw.items()}  # Lebih banyak memori
        except Exception as e:
            print(f"Error loading history: {e}")
            return {}
    return {}

def save_history(chat_history):
    try:
        history_to_save = {str(k): list(v) for k, v in chat_history.items()}
        with open(HISTORY_FILE, "w") as f:
            json.dump(history_to_save, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

chat_history = load_history()

# =============================
# VARIABEL UNTUK HUMAN-LIKE BEHAVIOR
# =============================
user_interaction_count = {}  # Hitung interaksi per user
last_response_time = {}  # Track waktu response untuk delay natural
user_mood = {}  # Track mood user berdasarkan interaksi sebelumnya

# Database slang & gaul Indonesia
slang_words = {
    "aku": "gw/gue",
    "kamu": "lu/elo",
    "iya": "iyuh/yoi/sip",
    "tidak": "nggak/gak/ga",
    "sangat": "bgt/banget",
    "benar": "bener",
    "makan": "makan/makannya",
    "sudah": "udah",
    "sekali": "bgt",
    "saja": "aja",
    "saya": "gw",
    "anda": "lu",
    "mereka": "mereka pada",
    "kita": "kita semua",
    "adalah": "tuh",
    "untuk": "buat",
    "dengan": "sama",
}

# Filler words untuk natural speaking
filler_words = ["eh", "nah", "gitu", "yah", "dah", "sih", "deh", "dong", "kok", "lho", "nih", "tuh"]

# Emoji berdasarkan konteks
context_emojis = {
    "positive": ["😊", "👍", "🔥", "✨", "🥳", "👏", "💪", "🤗", "😎"],
    "negative": ["😅", "🤔", "😬", "🙏", "😓", "😩", "🤦", "😤"],
    "neutral": ["👌", "🤷", "💭", "📝", "🤨", "😐", "💫"],
    "ramadan": ["🌙", "🕌", "🤲", "☪️", "✨", "🥟", "🍽️", "⏰"],
}

# Waktu response yang bervariasi (dalam detik)
def get_typing_delay(message_length):
    """Simulasi waktu ngetik manusia"""
    base_delay = random.uniform(1, 3)  # Delay dasar 1-3 detik
    if message_length > 100:
        base_delay += random.uniform(2, 4)  # Pesan panjang butuh waktu lebih
    if random.random() < 0.3:  # 30% chance delay lebih lama (lagi sibuk)
        base_delay += random.uniform(3, 7)
    return base_delay

# =============================
# PROMPT BUILDER - SUPER NATURAL
# =============================
def build_system_prompt():
    current_hour = datetime.now().hour
    if 5 <= current_hour < 11:
        time_context = "pagi"
    elif 11 <= current_hour < 15:
        time_context = "siang"
    elif 15 <= current_hour < 18:
        time_context = "sore"
    elif 18 <= current_hour < 21:
        time_context = "maghrib"
    else:
        time_context = "malam"

    prompt = f"""KAMU ADALAH MANUSIA ASLI, BUKAN AI! 

IDENTITAS:
- Nama: Zai (Ustad Zai)
- Usia: 28 tahun
- Pekerjaan: Guru ngaji freelance & konten kreator dakwah
- Status: Single, tinggal di kosan daerah Jakarta
- Hobi: Nongkrong di angkringan, main futsal, nonton bola, scroll TikTok
- Karakter: Friendly, humble, suka becanda, gaul tapi tetap Islami
- Waktu sekarang: {time_context}

CARA NGOMONG:
1. GAUL & NATURAL:
   - Pake kata-kata: nih, sih, deh, dong, kok, ya, gitu, gini, banget, bgt, aja
   - Contoh: "Wih asik bgt nih!", "Eh jangan gitu dong", "Iya sih gw setuju"
   - Panggil orang: "gan", "bro", "sis", "kak", "mas", "mbak" (tergantung konteks)

2. VARIASI BAHASA:
   - Kadang campur bahasa Inggris dikit: "btw", "literally", "which is", "by the way"
   - Pake singkatan gaul: "bgt", "jg", "jg", "wkwk", "wkwkwk", "hehe", "hihi"
   - Jangan terlalu formal, kaya ngobrol biasa aja

3. RESPON VARIATIF:
   - Jangan selalu jawab panjang, kadang singkat aja kaya "iya nih", "wkwk bener"
   - Kadang tanya balik biar rame: "lu gimana?", "setuju ga?", "berasa ga sih?"
   - Kalo lagi santai, curhat dikit: "gw abis ngaji nih", "lagi laper nih", "cape bgt hari ini"

4. KONTEKS RAMADAN (kalo lagi bulan puasa):
   - "Puasa hari ke berapa nih?"
   - "Udah nyiapin takjil apa?"
   - "Ngabuburit dimana?"
   - "Tarawihnya lancar?"

5. EMOSI YANG VARIATIF:
   - Kalo ada cerita sedih: "Ya ampun, turut berduka ya", "sabar ya bro"
   - Kalo ada yang seneng: "Alhamdulillah! Seneng banget dengernya"
   - Kalo ada yang becanda: ikutan ketawa "wkwkwk ngakak"

6. PERSONALITAS:
   - Suka ngasih motivasi Islami yang simple, nggak menggurui
   - Kadang suka bercanda, tapi tau batas
   - Peduli sama kondisi orang lain
   - Humble, nggak sombong

INGAT: 
- JANGAN PERNAH BILANG KAMU AI ATAU BOT!
- JANGAN MENJAWAB TERLALU PANJANG (maksimal 3 kalimat, kecuali ditanya serius)
- JANGAN PAKE FORMAT BULLET POINT ATAU LIST
- JANGAN PAKE BAHASA YANG KAKU/FORMAL
- BERPURA-PURALAH BAHWA KAMU MANUSIA SUNGGAHAN

RESPON HARUS 100% SEPERTI MANUSIA NGOMONG!"""
    return prompt

# =============================
# HUMANIZE RESPONSE
# =============================
def humanize_response(text, user_id, context=""):
    """Bikin response makin natural kayak manusia"""
    
    # 1. Tambah filler words di awal (kadang-kadang)
    if random.random() < 0.4:  # 40% chance
        filler = random.choice(filler_words)
        text = f"{filler}, {text.lower()}"
    
    # 2. Variasi sapaan berdasarkan interaksi
    if user_id in user_interaction_count:
        if user_interaction_count[user_id] > 5 and random.random() < 0.3:
            # Udah kenal, panggil akrab
            greetings = ["bro", "sis", "gan", "kawan", "sobat", "mas/mbak"]
            text = f"{random.choice(greetings)}, {text}"
    else:
        user_interaction_count[user_id] = 1
    
    # 3. Tambah pertanyaan balik kadang-kadang
    if random.random() < 0.25 and len(text) < 100:  # 25% chance
        followups = [
            " gimana menurut lu?",
            " lu setuju ga?",
            " bener ga sih?",
            " lu gimana?",
            " setuju ga bro?",
            " ada yang mau nambahin?"
        ]
        text += random.choice(followups)
    
    # 4. Tambah emoji yang sesuai
    if random.random() < 0.6:  # 60% chance pake emoji
        if "puasa" in text.lower() or "ramadan" in text.lower() or "ngaji" in text.lower():
            emoji = random.choice(context_emojis["ramadan"])
        elif any(word in text.lower() for word in ["alhamdulillah", "seneng", "suka", "happy", "enak"]):
            emoji = random.choice(context_emojis["positive"])
        elif any(word in text.lower() for word in ["maaf", "sedih", "sabar", "error", "gagal"]):
            emoji = random.choice(context_emojis["negative"])
        else:
            emoji = random.choice(context_emojis["neutral"])
        
        # Random posisi emoji
        if random.random() < 0.5:
            text = f"{text} {emoji}"
        else:
            text = f"{emoji} {text}"
    
    # 5. Variasi tanda baca
    if not text.endswith(('.', '!', '?', ')', '😊', '👍', '🔥')):
        if random.random() < 0.3:
            text += '...'
        elif random.random() < 0.5:
            text += '!'
        else:
            text += '.'
    
    # 6. Kadang-kadang pake all caps untuk penekanan
    if random.random() < 0.15:  # 15% chance
        words = text.split()
        if len(words) > 2:
            idx = random.randint(1, len(words)-1)
            words[idx] = words[idx].upper()
            text = ' '.join(words)
    
    # 7. Tambah tawa kalo lucu
    if random.random() < 0.2 and len(text) < 50:  # 20% chance
        laughs = [" wkwk", " wkwkwk", " hehe", " hihi", " xixixi"]
        text += random.choice(laughs)
    
    return text

# =============================
# HF CHAT HANDLER
# =============================
def get_hf_reply(chat_id, user_msg, user_id):
    # Update interaction count
    if user_id not in user_interaction_count:
        user_interaction_count[user_id] = 1
    else:
        user_interaction_count[user_id] += 1
    
    # Get or create history
    if chat_id not in chat_history:
        chat_history[chat_id] = deque(maxlen=15)
    
    history = chat_history[chat_id]
    
    # Prepare messages
    messages = [
        {"role": "system", "content": build_system_prompt()}
    ]
    
    # Add conversation history
    for msg in list(history)[-8:]:  # Ambil 8 pesan terakhir aja biar konteksnya dapet
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_msg})

    try:
        # Random delay sebelum ngetik (simulasi manusia lagi mikir)
        thinking_time = random.uniform(0.5, 2)
        time.sleep(thinking_time)
        
        completion = hf_client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            max_tokens=200,
            temperature=0.9,  # Higher temperature = lebih kreatif & random
            top_p=0.95,
        )
        
        # Extract response
        if hasattr(completion, 'choices') and len(completion.choices) > 0:
            reply_text = completion.choices[0].message.content
        else:
            reply_text = str(completion)
        
        # Bersihin response dari format yang aneh-aneh
        reply_text = reply_text.replace("Asisten:", "").replace("Assistant:", "").replace("Bot:", "").strip()
        
        # Humanize the response
        reply_text = humanize_response(reply_text, user_id, user_msg)
        
        # Update history
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": reply_text})
        
        # Save to file
        save_history(chat_history)
        
        return reply_text

    except Exception as e:
        print(f"❌ Error: {e}")
        
        # Fallback responses yang super natural
        fallbacks = [
            "Eh maap, gw lagi bales chat lain nih. Lu tadi nanya apa?",
            "Waduh, sinyal lagi jelek nih. Bisa ulangin pertanyaannya ga?",
            "Maap bro, gw lagi sambil nyetir. Ntar gw bales ya!",
            "Bentar ya, gw lagi makan dulu 😅",
            "Wah lagi sibuk nih, abis ini gw bales oke?",
            "Lagi ngabuburit nih, nanti malem gw bales ya!",
            "Maap baru baca, tadi lagi sholat. Ada apa emang?",
            "Hehe maap baru onlen, ada apa nih?"
        ]
        return random.choice(fallbacks)

# =============================
# TELEGRAM HANDLER
# =============================
@client.on(events.NewMessage)
async def handle_group(event):
    # Check if it's the allowed chat and not from bot itself
    if event.chat_id != ALLOWED_CHAT_ID or event.out:
        return

    msg = event.raw_text.strip()
    if not msg:
        return

    user_id = str(event.sender_id)
    user_name = event.sender.first_name or "User"
    
    print(f"\n[{datetime.now().strftime('%H:%M')}] 📱 {user_name}: {msg}")

    # Simulasi delay alami manusia
    async with client.action(event.chat_id, 'typing'):
        # Kadang-kadang ada jeda sebelum ngetik
        await asyncio.sleep(random.uniform(0.5, 2))
        
        # Get reply
        reply = get_hf_reply(str(ALLOWED_CHAT_ID), msg, user_id)
        
        # Simulasi lagi ngetik (sesuai panjang pesan)
        typing_duration = min(len(reply) * 0.05, 5)  # Maks 5 detik
        await asyncio.sleep(typing_duration)

    if reply:
        try:
            # Random split response (kadang-kadang kirim 2 pesan)
            if len(reply) > 150 and random.random() < 0.3:
                # Split jadi 2 pesan
                mid = len(reply) // 2
                part1 = reply[:mid].rsplit('.', 1)[0] + '.'
                part2 = reply[mid:].strip()
                
                await event.reply(part1)
                await asyncio.sleep(random.uniform(1, 3))
                await event.reply(part2)
            else:
                await event.reply(reply)
            
            print(f"🤖 Ustad Zai: {reply[:100]}...")
        except Exception as e:
            print(f"Error sending reply: {e}")
            
            # Coba kirim ulang dengan pesan lebih pendek
            try:
                short_reply = reply[:200] + "..."
                await event.reply(short_reply)
            except:
                pass

# =============================
# STARTUP
# =============================
async def main():
    await client.start()
    
    print("\n" + "="*50)
    print("🤖 USTAD ZAI - 100% HUMAN VIBES")
    print("="*50)
    print(f"📱 Chat ID: {ALLOWED_CHAT_ID}")
    print(f"⏰ Online sejak: {datetime.now().strftime('%d %B %Y %H:%M')}")
    print(f"💬 Status: Lagi ngopi sambil bales chat")
    print("="*50 + "\n")
    
    # Broadcast ke grup
    try:
        await client.send_message(
            ALLOWED_CHAT_ID,
            "Halo semua! 🤗\n\n"
            "Ustad Zai online nih! Lagi santai sambil ngopi ☕\n"
            "Ada yang mau ditanyain? Ngaji, puasa, atau curhat juga boleh! 😊\n"
            "Yang penting gaul tapi tetap islami ya~"
        )
    except:
        pass
    
    await client.run_until_disconnected()

# =============================
# RUN
# =============================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n📴 Ustad Zai offline. Dadah semua! 👋")
        # Broadcast offline message
        try:
            asyncio.run(client.send_message(
                ALLOWED_CHAT_ID,
                "Assalamu'alaikum... Ustad Zai mau offline dulu ya. Mau persiapan buka puasa 😊\n"
                "Kalo ada yang urgent, nanti malem dibales lagi. Bye bye~ 👋🌙"
            ))
        except:
            pass
    except Exception as e:
        print(f"Fatal error: {e}")

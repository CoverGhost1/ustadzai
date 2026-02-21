require("dotenv").config();
const TelegramBot = require("node-telegram-bot-api");
const axios = require("axios");

const bot = new TelegramBot(process.env.TG_TOKEN, {
  polling: true,
});

const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${process.env.GEMINI_KEY}`;

let activeChats = {};
let memory = {};
const MAX_MEMORY = 6;

bot.onText(/\/zstart/, (msg) => {
  const chatId = msg.chat.id;
  activeChats[chatId] = true;

  bot.sendMessage(chatId, "Assalamu'alaikum 🤍 Ustadz Zai siap menemani.");
});

bot.onText(/\/zstop/, (msg) => {
  const chatId = msg.chat.id;
  activeChats[chatId] = false;

  bot.sendMessage(chatId, "Baik 🤍 Ustadz Zai istirahat dulu.");
});

bot.on("message", async (msg) => {
  if (!msg.text) return;
  if (msg.text.startsWith("/")) return;

  const chatId = msg.chat.id;

  if (!activeChats[chatId]) return;

  if (!memory[chatId]) memory[chatId] = [];

  memory[chatId].push(msg.text);

  if (memory[chatId].length > MAX_MEMORY) {
    memory[chatId].shift();
  }

  const context = memory[chatId].join("\n");

  try {
    const response = await axios.post(GEMINI_URL, {
      contents: [
        {
          parts: [
            {
              text: `
Kamu adalah Ustadz Zai.

Karakter:
- Ustadz muda Indonesia
- Santai, hangat, dan relate
- Tidak menghakimi
- Ramadan vibes
- Natural seperti teman dekat
- Jawaban tidak terlalu panjang
- Kadang pakai emoji islami 🤍✨

Percakapan:
${context}

Balas pesan terakhir sebagai Ustadz Zai.
              `
            }
          ]
        }
      ]
    });

    const reply =
      response.data.candidates[0].content.parts[0].text;

    bot.sendMessage(chatId, reply);

  } catch (err) {
    console.log(err.response?.data || err.message);
  }
});

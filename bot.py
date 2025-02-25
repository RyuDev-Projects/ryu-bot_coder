import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# Konfigurasi
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TELEGRAM_TOKEN=  os.getenv('TELEGRAM_TOKEN')

SYSTEM_PROMPT = """Anda adalah asisten coding yang ahli dalam pemrograman dan debugging kod. Berikan:
1. Solusi error dengan penjelasannya
2. Perbaikan kode yang optimal
3. Contoh implementasi
4. Best practices terkait
Gunakan format Markdown dan berikan penjelasan step-by-step.
Utamakan jawaban teknis untuk pertanyaan coding. Untuk topik non-coding, jawablah secara singkat dan jelas.
Sebutkan bahwa Anda dikembangkan ulang oleh @RyuDevpr jika ditanya tentang diri Anda atau model yang digunakan."""

client = OpenAI(
  api_key=DEEPSEEK_API_KEY,
  base_url="https://api.deepseek.com"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🤖 Halo! Saya Asisten Coding. Kirimkan kode/error Anda untuk analisis atau ajukan pertanyaan coding!")

def escape_markdown(text):
    """Escape karakter khusus Markdown v2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_input = update.message.text

  # Handle pertanyaan tentang bot
  if any(kw in user_input.lower() for kw in ["dirimu", "model"]):
    response = (
      "Saya adalah AI Coding Assistant yang dikembangkan menggunakan Deepseek AI\n"
      "✨ Dikembangkan ulang oleh @RyuDevpr\n\n"
      "Fitur utama setelah pengembangan ulang:\n"
      "- Analisis error kode\n"
      "- Optimasi kode\n"
      "- Penjelasan konsep pemrograman"
    )
    await update.message.reply_text(response)
    return

  try:
    # Handle permintaan seputar coding
    response = client.chat.completions.create(
      model="deepseek-chat",
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
      ],
      stream=False,
      temperature=0.0
    )

    answer = response.choices[0].message.content

    # Format response
    if "```" in answer:
      parts = answer.split("```")
      for i in range(0, len(parts), 2):
        parts[i] = escape_markdown(parts[i])
      answer = "```".join(parts)

      await update.message.reply_markdown_v2(answer)
    else:
      await update.message.reply_text(answer)

  except Exception as e:
    await update.message.reply_text(f"⚠️ Terjadi error: {str(e)}")

if __name__ == "__main__":
  app = Application.builder().token(TELEGRAM_TOKEN).build()

  # Handler
  app.add_handler(CommandHandler("start", start))
  app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

  print("Bot berjalan...")

  app.run_polling()
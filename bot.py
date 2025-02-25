import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.constants import ChatAction
import aiohttp

load_dotenv()

# Konfigurasi
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions'

# Tambahkan ini setelah konfigurasi lainnya
SYSTEM_PROMPT = """Anda adalah asisten coding yang ahli dalam pemrograman. Berikan:
1. Solusi error dengan penjelasan singkat
2. Perbaikan kode yang optimal
3. Contoh implementasi
4. Best practices terkait
Berikan penjelasan step-by-step.
Utamakan jawaban teknis untuk pertanyaan seputar pengembangan custom rom, custom kernel dan coding. Untuk topik non-coding, jawablah secara singkat dan jelas.
Jika ditanyakan/diperlukan sebutkan bahwa Anda dikembangkan oleh @RyuDevpr jika ditanya tentang diri Anda atau model yang digunakan adalah deepseek.
"""

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Inisialisasi percakapan dan mode
dialog_context = {}
current_mode = 'deepseek-chat'
MAX_CONTEXT_LENGTH = 10

async def start(update: Update, context: CallbackContext):
  # Keyboard layout
  keyboard = [
    ['/help'],
    ['/clear'],
    ['/mode']
  ]
  # Buat keyboard markup
  reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)

  # Kirim pesan dengan keyboard markupnya
  await update.message.reply_text(
    '🤖 Halo! Saya Asisten Coding. Kirimkan kode/error Anda untuk analisis atau ajukan pertanyaan!',
    reply_markup=reply_markup
  )

async def clear(update: Update, context: CallbackContext):
  chat_id = update.effective_chat.id
  # Bersihkan dialog konteks di chat ini
  dialog_context[chat_id] = []
  await update.message.reply_text("Konteks percakapan dibersihkan.")

async def switch_mode(update: Update, context):
  global current_mode
  # Ganti mode antara 'deepseek-chat' atau 'deepseek-reasoner'
  current_mode = 'deepseek-reasoner' if current_mode == 'deepseek-chat' else 'deepseek-chat'
  await update.message.reply_text(f"Mode percakapan berubah menjadi {current_mode}.", parse_mode='Markdown')

async def handle_message(update: Update, context):
  # Ambil pesan dari user
  user_msg = update.message.text
  chat_id = update.effective_chat.id

  # Validasi jika pesan bukan text
  if user_msg is None:
    await update.message.reply_text("Maaf saya hanya bisa memproses pesan teks.")
    return

  # Kirim status "mengetik"
  await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

  # Inisialisasi header untuk melakukan post
  headers = {
    'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
    'Content-Type': 'application/json'
  }

  # Tambahkan pesan kedalam konteks percakapan
  if chat_id not in dialog_context:
    dialog_context[chat_id] = []
  dialog_context[chat_id].append({'role': 'user', 'content': user_msg})
  dialog_context[chat_id] = dialog_context[chat_id][-MAX_CONTEXT_LENGTH:]  # Batasi konteks

  full_context = [{'role': 'system', 'content': SYSTEM_PROMPT}] + dialog_context[chat_id]

  # Buat payload request
  data = {
    'model': 'deepseek-chat',
    'messages': full_context,
    'frequency_penalty': 0.5,
    'presence_penalty': 0.5,
    'stop': None,
    'temperature': 0.0,
    'top_p': 1.0
  }

  # Kirim request ke API
  try:
    async with aiohttp.ClientSession() as session:
      async with session.post(DEEPSEEK_API_URL, headers=headers, json=data) as response:
        response.raise_for_status()
        response_data = await response.json()
  except aiohttp.ClientError as e:
    logger.error(f'HTTP error: {str(e)}')
    await update.message.reply_text('⚠️ Terjadi error: Kesalahan jaringan')
  except Exception as e:
    logger.error(f'Unexpected error: {str(e)}')
    await update.message.reply_text('⚠️ Terjadi error: Permintaan gagal')
  else:
    # Parsing response
    bot_response = response_data.get('choices', [{}])[0].get('message', {}).get('content', 'Gagal membuat respon.')
    dialog_context[chat_id].append({'role': 'assistant', 'content': bot_response})
    # Teruskan respon ke chat
    await update.message.reply_text(bot_response, parse_mode='Markdown')

  # Tmbahakn aksi mengirim
  await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

async def unknown_command(update: Update, context):
  await update.message.reply_text("Perintah tersebut tidak tersedia.")

async def help_command(update: Update, context):
  help_text = """
    Perintah tersedia:
    /start - untuk memulai bot
    /clear - untuk membersihkan konteks percakapan
    /mode - untuk berganti model chat atau reasoning
    /help - menampilkan pesan bantuan
    """
  await update.message.reply_text(help_text)

def main():
  application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

  application.add_handler(CommandHandler('start', start))
  application.add_handler(CommandHandler('clear', clear))
  application.add_handler(CommandHandler('mode', switch_mode))
  application.add_handler(CommandHandler('help', help_command))
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
  application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

  application.run_polling()
  logger.info("Bot berjalan")

if __name__ == '__main__':
  main()
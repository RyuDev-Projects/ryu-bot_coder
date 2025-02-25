import os
from dotenv import load_dotenv
from telegram import Update, Bot, ChatAction, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests

load_dotenv()

# Konfigurasi
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions'

# Inisialisasi
bot = Bot(token=TELEGRAM_BOT_TOKEN)
updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Inisialisasi percakapan dan mode
dialog_context = {}
current_mode = 'deepseek-chat'

def start(update: Update, context: CallbackContext):
  # Keyboard layout
  keyboard = [
    ['/help'],
    ['/clear'],
    ['/mode']
  ]
  # Buat keyboard markup
  reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)

  # Kirim pesan dengan keyboard markupnya
  context.bot.send_message(
    chat_id = update.effective_chat.id,
    text = '🤖 Halo! Saya Asisten Coding. Kirimkan kode/error Anda untuk analisis atau ajukan pertanyaan!',
    reply_markup=reply_markup
  )

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

def clear(update: Update, context: CallbackContext):
  chat_id = update.effective_chat.id
  # Bersihkan dialog konteks di chat ini
  dialog_context[chat_id] = []
  context.bot.send_message(chat_id=chat_id, text="Konteks percakapan dibersihkan.")

clean_handler = CommandHandler('clear', clear)
dispatcher.add_handler(clean_handler)

def switch_mode(update: Update, context:CallbackContext):
  global current_mode
  chat_id = update.effective_chat.id
  # Ganti mode antara 'deepseek-chat' atau 'deepseek-reasoner'
  current_mode = 'deepseek-reasoner' if current_mode == 'deepseek-chat' else 'deepseek-chat'
  context.bot.send_message(
    chat_id=chat_id,
    text=f"Mode percakapan berubah menjadi {current_mode}.",
    parse_mode='Markdown'
  )

mode_handler = CommandHandler('mode', switch_mode)
dispatcher.add_handler(mode_handler)

def handle_message(update: Update, context:CallbackContext):
  # Ambil pesan dari user
  user_msg = update.message.text
  username = update.message.from_user.username
  user_id = update.message.from_user.id
  chat_id = update.effective_chat.id

  # Validasi jika pesan bukan text
  if user_msg is None:
    context.bot.send_message(
      chat_id=chat_id,
      text="Maaf saya hanya bisa memproses pesan teks."
    )
    return

  # Kirim status "mengetik"
  context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

  # Inisialisasi header untuk melakukan post
  headers = {
    'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
    'Content-Type': 'application/json'
  }

  # Tambahkan pesan kedalam konteks percakapan
  if chat_id not in dialog_context:
    dialog_context[chat_id] = []
  dialog_context[chat_id].append({'role': 'user', 'content': user_msg})

  # Buat payload request
  data = {
    'model': 'deepseek-chat',
    'messages': dialog_context[chat_id],
    'frequency_penalty': 0.5,
    'max_tokens': 1000,
    'presence_penalty': 0.5,
    'stop': None,
    'temperature': 0.0,
    'top_p': 1.0
  }

  # Kirim request ke API
  try:
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
    response.raise_for_status()
  except requests.exceptions.HTTPError as errh:
    print('HTTP error: ', errh)
    context.bot.send_message(
      chat_id=chat_id,
      text='⚠️ Terjadi error: Kesalahan jaringan'
    )
  except requests.exceptions.RequestException as err:
    print('Something went wrong: ', err)
    context.bot.send_message(
      chat_id=chat_id,
      text='⚠️ Terjadi error: Permintaan gagal'
    )
  else:
    # Parsing response
    response_data = response.json()
    bot_response = response_data.get('choices', [{}])[0].get('message', {}).get('content', 'Gagal membuat respon.')

    # Tambahkan respon bot kedalam konteks percakapan
    dialog_context[chat_id].append({'role': 'assistant', 'content': bot_response})

    # Teruskan respon ke chat
    context.bot.send_message(
      chat_id=chat_id,
      text=bot_response
    )

  # Tmbahakn aksi mengirim
  context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)

def unknown_command(update: Update, context: CallbackContext):
  context.bot.send_message(chat_id=update.effective_chat.id, text="Perintah tersebut tidak tersedia.")

def help_command(update: Update, context: CallbackContext):
  chat_id = update.effective_chat.id
  help_text = """
  Perintah tersedia:
  /start - untuk memulai bot
  /clear - untuk membersihkan konteks percakapan
  /mode - untuk berganti model chat atau reasoning
  /help - menampilkan pesan bantuan
  """
  context.bot.send_message(chat_id=chat_id, text=help_text)

help_handler = CommandHandler('help', help_command)
dispatcher.add_handler(help_handler)

start_handler = CommandHandler('start', start)
clean_handler = CommandHandler('clear', clear)
message_handler = MessageHandler(Filters.text & (~Filters.command), handle_message)
unknown_handler = MessageHandler(Filters.command, unknown_command)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(clean_handler)
dispatcher.add_handler(message_handler)
dispatcher.add_handler(unknown_handler)

# Mulai bot
updater.start_polling()
print("Bot berjalan...")
updater.idle()
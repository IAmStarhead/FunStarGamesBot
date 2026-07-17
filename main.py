import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Бот ---
async def start(update: Update, context):
    user = update.effective_user.first_name
    await update.message.reply_text(f'Привет, {user}! FunStarGames работает 🎲')
    logger.info(f'Пользователь {user} написал /start')

def run_bot():
    token = os.environ['BOT_TOKEN']
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    logger.info('Запускаю бота...')
    app.run_polling()

# --- Простой HTTP-сервер для пингов ---
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass  # отключаем логи запросов

def run_web():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), PingHandler)
    logger.info(f'Веб-сервер на порту {port}')
    server.serve_forever()

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    logger.info('Веб-сервер запущен в потоке')
    run_bot()

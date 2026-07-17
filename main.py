import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Импортируем обработчики из новой папки
from handlers.start import start_command, hello_handler, button_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Бот ---
def run_bot():
    token = os.environ['BOT_TOKEN']
    app = Application.builder().token(token).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', button_handler))  # /help тоже будет работать
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'(?i)^(привет|здравствуй|хай|здарова|hello)$'), hello_handler))
    app.add_handler(CallbackQueryHandler(button_handler))  # обрабатывает нажатия на все инлайн-кнопки

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
        pass

def run_web():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), PingHandler)
    logger.info(f'Веб-сервер на порту {port}')
    server.serve_forever()

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    logger.info('Веб-сервер запущен в потоке')
    run_bot()

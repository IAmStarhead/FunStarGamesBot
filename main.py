import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Импортируем обработчики стартового меню
from handlers.start import start_command, hello_handler, button_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Универсальный обработчик для логирования всех событий ---
async def log_update(update: Update, context):
    """Логирует любое входящее сообщение или нажатие кнопки."""
    if update.message and update.message.text:
        user = update.message.from_user
        logger.info(
            "Сообщение от %s (@%s): %s",
            user.full_name,
            user.username,
            update.message.text,
        )
    elif update.callback_query:
        user = update.callback_query.from_user
        logger.info(
            "Нажата кнопка %s пользователем %s (@%s)",
            update.callback_query.data,
            user.full_name,
            user.username,
        )

# --- Бот ---
def run_bot():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Регистрируем логирование (самый низкий приоритет)
    app.add_handler(
        MessageHandler(filters.TEXT, log_update), group=999
    )
    app.add_handler(
        CallbackQueryHandler(log_update, pattern=None), group=999
    )

    # Основные обработчики
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", button_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.Regex(r"(?i)^(привет|здравствуй|хай|здарова|hello)$"),
            hello_handler,
        )
    )
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Запускаю бота...")
    app.run_polling()

# --- Простой HTTP-сервер для пингов Render ---
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # отключаем логирование HTTP-запросов в консоль

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    logger.info(f"Веб-сервер на порту {port}")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("Веб-сервер запущен в потоке")
    run_bot()

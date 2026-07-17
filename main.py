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

from handlers.start import start_command, hello_handler, button_handler
from handlers import blackjack

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Логирование всех входящих сообщений и нажатий кнопок ---
async def log_update(update: Update, context):
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

    # Логирование всех событий (самый низкий приоритет)
    app.add_handler(MessageHandler(filters.TEXT, log_update), group=999)
    app.add_handler(CallbackQueryHandler(log_update, pattern=None), group=999)

    # Блэкджек
    blackjack.register_handlers(app)
    app.add_handler(CommandHandler("bj", blackjack.start_lobby))
    app.add_handler(CommandHandler("balance", blackjack.balance_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^(блэкджек|blackjack|21|очко)$"),
            blackjack.text_blackjack,
        )
    )

    # Стартовое меню и приветствия
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

# --- Веб-заглушка для Render ---
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    logger.info(f"Веб-сервер на порту {port}")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("Веб-сервер запущен в потоке")
    run_bot()

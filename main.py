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
from handlers import blackjack, durak
from wallet import get_balance, transfer, get_user_id_by_username, update_username

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Логирование ---
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

# --- Команды баланса и переводов ---
async def balance_command(update: Update, context):
    if context.args:
        username = context.args[0]
        target_id = get_user_id_by_username(username)
        if target_id is None:
            await update.message.reply_text("Игрок не найден.")
            return
        bal = get_balance(target_id)
        await update.message.reply_text(f"Баланс {username}: {bal} фишек.")
    else:
        user_id = update.effective_user.id
        bal = get_balance(user_id)
        await update.message.reply_text(f"Ваш баланс: {bal} фишек.")

async def transfer_command(update: Update, context):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /transfer @username сумма")
        return
    username = context.args[0]
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной.")
        return
    to_id = get_user_id_by_username(username)
    if to_id is None:
        await update.message.reply_text("Получатель не найден.")
        return
    from_id = update.effective_user.id
    update_username(from_id, update.effective_user.username)
    if transfer(from_id, to_id, amount):
        await update.message.reply_text(f"Перевели {amount} фишек пользователю {username}.")
    else:
        await update.message.reply_text("Недостаточно средств.")

# --- Бот ---
def run_bot():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(MessageHandler(filters.TEXT, log_update), group=999)
    app.add_handler(CallbackQueryHandler(log_update, pattern=None), group=999)

    # Блэкджек
    blackjack.register_handlers(app)
    app.add_handler(CommandHandler("bj", blackjack.start_lobby))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^(блэкджек|blackjack|21|очко)$"),
            blackjack.text_blackjack,
        )
    )

    # Дурак
    durak.register_handlers(app)
    app.add_handler(CommandHandler("durak", lambda u, c: durak.durak_start(u, c, 'throw')))  # по умолчанию подкидной
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^дурак"),
            durak.text_durak
        )
    )

    # Баланс и переводы
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("transfer", transfer_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^баланс$"),
            balance_command
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

# --- Веб-заглушка ---
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

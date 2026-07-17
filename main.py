import os
import time
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
from handlers import blackjack, durak, slots
from wallet import get_balance, transfer, get_user_id_by_username, update_username

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

async def log_update(update: Update, context):
    if update.message and update.message.text:
        user = update.message.from_user
        chat = update.effective_chat
        if chat.type == 'private':
            logger.info("ЛС от %s (@%s): %s", user.full_name, user.username, update.message.text)
        else:
            text = update.message.text.lower()
            bot_username = context.bot.username.lower()
            if f'@{bot_username}' in text or \
               (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                logger.info("Обращение к боту от %s (@%s): %s", user.full_name, user.username, update.message.text)
    elif update.callback_query:
        user = update.callback_query.from_user
        logger.info("Нажата кнопка %s пользователем %s (@%s)", update.callback_query.data, user.full_name, user.username)

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

def run_bot():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(MessageHandler(filters.TEXT, log_update), group=999)
    app.add_handler(CallbackQueryHandler(log_update, pattern=None), group=999)

    blackjack.register_handlers(app)
    app.add_handler(CommandHandler("bj", blackjack.start_lobby))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^(блэкджек|blackjack|21|очко)$"),
            blackjack.text_blackjack,
        )
    )

    durak.register_handlers(app)
    app.add_handler(CommandHandler("durak", lambda u, c: durak.durak_start(u, c, 'throw')))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^дурак"),
            durak.text_durak
        )
    )

    slots.register_handlers(app)
    app.add_handler(CommandHandler("slots", slots.start_slots))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^(слоты|слот|автомат)$"),
            slots.start_slots
        )
    )

    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("transfer", transfer_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)^баланс$"),
            balance_command
        )
    )

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

    logger.info("Ожидаю 5 секунд, чтобы старый инстанс освободил обновления...")
    time.sleep(5)
    logger.info("Запускаю бота...")
    app.run_polling()

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

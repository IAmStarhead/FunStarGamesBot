from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers import blackjack

WELCOME_TEXT = (
    "🚀 Приветствую, {name}!\n\n"
    "Я — FunStarGames, ваш карманный клуб для весёлых посиделок.\n"
    "Никакой валюты и реальных ставок — только азарт и хорошая компания.\n\n"
    "Что умею прямо сейчас:\n\n"
    "🃏 Блэкджек — классика против дилера-бота.\n"
    "   Можно играть одному или собраться втроём за одним столом.\n\n"
    "♠️ Покер — Техасский Холдем для компании от 2 до 6 человек.\n"
    "   С виртуальными фишками (по 100 на партию), торговлей и живыми раундами.\n\n"
    "🔐 Для честной игры:\n"
    "   • Личные карты защищены от пересылки.\n"
    "   • Играть могут только те, кто написал боту в личные сообщения (активировал чат).\n\n"
    "💡 В групповом чате выдайте боту права администратора — это нужно "
    "для управления столами и закрепления сообщений.\n\n"
    "А пока можно испытать удачу прямо здесь, в личке.\n"
    "Выбирайте, с чего начнём:"
)

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🃏 Блэкджек", callback_data="blackjack"),
            InlineKeyboardButton("♠️ Покер", callback_data="poker"),
        ],
        [
            InlineKeyboardButton("🂡 Дурак", callback_data="durak"),
        ],
        [
            InlineKeyboardButton("ℹ️ Помощь", callback_data="help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    thread_id = update.effective_message.message_thread_id if update.effective_message else None
    await update.message.reply_text(
        WELCOME_TEXT.format(name=user),
        reply_markup=get_main_keyboard(),
        message_thread_id=thread_id
    )

async def hello_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    chat = update.effective_chat
    user = update.effective_user
    bot_username = context.bot.username.lower()
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if chat.type == "private":
        text = (
            f"Привет, {user.first_name}! 👋\n"
            "Рад тебя видеть. Хочешь перекинуться в блэкджек или собрать стол для покера?\n"
            "Жми на кнопки ниже или напиши «помощь», если нужны правила."
        )
        await message.reply_text(text, reply_markup=get_main_keyboard())
        return

    mentioned = False
    if f"@{bot_username}" in message.text.lower():
        mentioned = True
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        mentioned = True

    if mentioned:
        text = f"{user.first_name}, привет! 👋 Жми кнопки или напиши «помощь»."
        await message.reply_text(text, reply_markup=get_main_keyboard(), message_thread_id=thread_id)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ℹ️ Помощь по FunStarGames\n\n"
        "🎮 Блэкджек — игра против дилера. Цель: набрать 21 очко или больше, чем у дилера, но не переборщить.\n"
        "   • Игроков: 1–3.\n\n"
        "♠️ Покер — Техасский Холдем. Игроки получают по 2 карты, затем на стол выкладываются 5 общих.\n"
        "   • Игроков: 2–6.\n"
        "   • Торги: чек, бет, рейз, фолд.\n"
        "   • Фишки выдаются каждый раз заново (100 на партию).\n\n"
        "🔒 Защита: все личные сообщения с картами защищены от пересылки.\n"
        "📌 В групповом чате боту нужны права администратора для корректной работы.\n\n"
        "Если что-то пошло не так, просто нажмите /start."
    )
    await update.message.reply_text(help_text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "help":
        await query.answer(
            text="🃏 Блэкджек (1-3 игрока)\n♠️ Покер (2-6 игроков)\nПодробнее: /help",
            show_alert=True
        )
    elif data == "blackjack":
        await query.answer("Запускаю блэкджек!")
        await blackjack.start_lobby(update, context)
    elif data == "poker":
        await query.answer("Покер пока в разработке. Скоро!")
    else:
        await query.answer("Неизвестная команда.")

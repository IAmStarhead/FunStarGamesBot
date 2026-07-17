from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# --- Данные для приветственного меню ---
WELCOME_TEXT = (
    "🚀 Приветствую, {name}!\n\n"
    "Я — FunStarGames, ваш карманный клуб для весёлых посиделок.\n"
    "Никакой валюты и реальных ставок — только азарт и хорошая компания.\n\n"
    "Что умею прямо сейчас:\n\n"
    "🃏 **Блэкджек** — классика против дилера-бота.\n"
    "   Можно играть одному или собраться втроём за одним столом.\n\n"
    "♠️ **Покер** — Техасский Холдем для компании от 2 до 6 человек.\n"
    "   С виртуальными фишками (по 100 на партию), торговлей и живыми раундами.\n\n"
    "🔐 Для честной игры:\n"
    "   • Личные карты защищены от пересылки.\n"
    "   • Играть могут только те, кто написал боту в личные сообщения (активировал чат).\n\n"
    "💡 В групповом чате выдайте боту права администратора — это нужно "
    "для управления столами и закрепления сообщений.\n\n"
    "А пока можно испытать удачу прямо здесь, в личке.\n"
    "Выбирайте, с чего начнём:"
)

# Клавиатура с кнопками под сообщением
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🃏 Блэкджек", callback_data="blackjack"),
            InlineKeyboardButton("♠️ Покер", callback_data="poker"),
        ],
        [
            InlineKeyboardButton("ℹ️ Помощь", callback_data="help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Обработчики ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на команду /start"""
    user = update.effective_user.first_name
    await update.message.reply_text(
        WELCOME_TEXT.format(name=user),
        reply_markup=get_main_keyboard()
    )

async def hello_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на обычное приветствие (привет, здарова и т.п.)"""
    user = update.effective_user.first_name
    text = f"Привет, {user}! 👋\nРад тебя видеть. Хочешь перекинуться в блэкджек или собрать стол для покера?\nЖми на кнопки ниже или напиши «помощь», если нужны правила."
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на команду /help и кнопку Помощь"""
    help_text = (
        "ℹ️ **Помощь по FunStarGames**\n\n"
        "🎮 **Блэкджек** — игра против дилера. Цель: набрать 21 очко или больше, чем у дилера, но не переборщить.\n"
        "   • Игроков: 1–3.\n\n"
        "♠️ **Покер** — Техасский Холдем. Игроки получают по 2 карты, затем на стол выкладываются 5 общих.\n"
        "   • Игроков: 2–6.\n"
        "   • Торги: чек, бет, рейз, фолд.\n"
        "   • Фишки выдаются каждый раз заново (100 на партию).\n\n"
        "🔒 **Защита:** все личные сообщения с картами защищены от пересылки.\n"
        "📌 **В групповом чате** боту нужны права администратора для корректной работы.\n\n"
        "Если что-то пошло не так, просто нажмите /start."
    )
    await update.message.reply_text(help_text)

# --- Обработчик колбэков (пока заглушки) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки меню"""
    query = update.callback_query
    await query.answer()  # убирает часы ожидания
    data = query.data

    if data == "blackjack":
        await query.edit_message_text("🃏 Блэкджек пока в разработке. Скоро появится!")
    elif data == "poker":
        await query.edit_message_text("♠️ Покер пока в разработке. Скоро появится!")
    elif data == "help":
        await help_command(update, context)  # вызываем тот же текст помощи
    else:
        await query.edit_message_text("Неизвестная команда.")

import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from wallet import get_balance, add_balance

logger = logging.getLogger(__name__)

SYMBOLS = ['7️⃣', '🍒', '🍋', '🍊', '🍇', '🔔']
PAYOUTS = {
    '7️⃣': 100,
    '🍒': 20,
    '🍋': 10,
    '🍊': 8,
    '🍇': 5,
    '🔔': 3
}

def spin_result():
    """Генерирует случайный набор 3x3 символов."""
    return [[random.choice(SYMBOLS) for _ in range(3)] for _ in range(3)]

def format_slots(grid):
    """Форматирует сетку 3x3 в текст."""
    lines = [' '.join(row) for row in grid]
    return '\n'.join(lines)

def check_win(grid):
    """Проверяет центральную линию (второй ряд) на выигрыш."""
    line = grid[1]
    if len(set(line)) == 1:
        return line[0]
    return None

async def start_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создаёт сообщение со слотами."""
    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None
    user = update.effective_user

    bet = 10
    balance = get_balance(user.id)
    grid = spin_result()

    keyboard = [
        [InlineKeyboardButton('10', callback_data='slots_bet_10'),
         InlineKeyboardButton('25', callback_data='slots_bet_25'),
         InlineKeyboardButton('50', callback_data='slots_bet_50')],
        [InlineKeyboardButton('🎰 Крутить', callback_data='slots_spin')]
    ]

    text = (
        f"🎰 Слоты FunStar 🎰\n"
        f"──────────────\n"
        f"{format_slots(grid)}\n"
        f"──────────────\n"
        f"Ставка: {bet} фишек\n"
        f"Баланс: {balance} фишек"
    )

    msg = await context.bot.send_message(
        chat.id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id
    )

    context.user_data['slots'] = {
        'message_id': msg.message_id,
        'chat_id': chat.id,
        'thread_id': thread_id,
        'bet': bet
    }

async def slots_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    user_data = context.user_data

    if 'slots' not in user_data:
        await query.edit_message_text("Игровой автомат устарел. Вызовите /slots снова.")
        return

    slots_state = user_data['slots']
    chat_id = slots_state['chat_id']
    message_id = slots_state['message_id']
    thread_id = slots_state.get('thread_id')

    if data.startswith('slots_bet_'):
        new_bet = int(data.split('_')[2])
        slots_state['bet'] = new_bet
        await query.answer(f'Ставка изменена на {new_bet} фишек.')
        balance = get_balance(user.id)
        grid = spin_result()
        keyboard = [
            [InlineKeyboardButton('10', callback_data='slots_bet_10'),
             InlineKeyboardButton('25', callback_data='slots_bet_25'),
             InlineKeyboardButton('50', callback_data='slots_bet_50')],
            [InlineKeyboardButton('🎰 Крутить', callback_data='slots_spin')]
        ]
        text = (
            f"🎰 Слоты FunStar 🎰\n"
            f"──────────────\n"
            f"{format_slots(grid)}\n"
            f"──────────────\n"
            f"Ставка: {new_bet} фишек\n"
            f"Баланс: {balance} фишек"
        )
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == 'slots_spin':
        bet = slots_state['bet']
        balance = get_balance(user.id)
        if balance < bet:
            await query.answer('Недостаточно фишек для ставки.', show_alert=True)
            return

        # Списываем ставку
        add_balance(user.id, -bet)
        balance = get_balance(user.id)

        # Удаляем исходное сообщение
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

        # Отправляем заставку с эмодзи автомата
        splash_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="🎰 Крутим... 🎰",
            message_thread_id=thread_id
        )
        await asyncio.sleep(2)  # Имитация вращения
        await context.bot.delete_message(chat_id=chat_id, message_id=splash_msg.message_id)

        # Финальный результат
        final_grid = spin_result()
        win_symbol = check_win(final_grid)
        if win_symbol:
            multiplier = PAYOUTS[win_symbol]
            winnings = bet * multiplier
            add_balance(user.id, winnings)
            new_balance = get_balance(user.id)
            result_text = f"🎉 Выигрыш! {win_symbol}x3 (+{winnings} фишек)\n"
        else:
            new_balance = get_balance(user.id)
            result_text = "😔 Нет выигрыша.\n"

        keyboard = [
            [InlineKeyboardButton('10', callback_data='slots_bet_10'),
             InlineKeyboardButton('25', callback_data='slots_bet_25'),
             InlineKeyboardButton('50', callback_data='slots_bet_50')],
            [InlineKeyboardButton('🎰 Крутить', callback_data='slots_spin')]
        ]

        final_text = (
            f"🎰 Слоты FunStar 🎰\n"
            f"──────────────\n"
            f"{format_slots(final_grid)}\n"
            f"──────────────\n"
            f"{result_text}"
            f"Ставка: {bet} фишек\n"
            f"Баланс: {new_balance} фишек"
        )

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=final_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_thread_id=thread_id
        )

        # Обновляем состояние, чтобы кнопки работали для нового сообщения
        slots_state['message_id'] = msg.message_id
        slots_state['bet'] = bet
        return

def register_handlers(app):
    app.add_handler(CallbackQueryHandler(slots_button, pattern='^slots_(bet_|spin)'))

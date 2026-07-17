import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)

# Хранилище активных игр: ключ — chat_id
games = {}

# Колода
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

def new_deck():
    deck = [r + s for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def card_value(card):
    rank = card[:-1]
    if rank in ('J', 'Q', 'K'):
        return 10
    elif rank == 'A':
        return 11
    else:
        return int(rank)

def hand_value(hand):
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1] == 'A')
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def hand_display(hand):
    return ' '.join(hand) + f' ({hand_value(hand)} очков)'

# === Лобби ===
async def start_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.id in games and games[chat.id]['state'] != 'finished':
        await context.bot.send_message(chat.id, 'Игра уже запущена. Дождитесь окончания или напишите "выйти из игры".')
        return

    games[chat.id] = {
        'players': [],
        'names': {},
        'state': 'lobby',
        'message_id': None,
        'timer_task': None
    }

    keyboard = [
        [InlineKeyboardButton('Сесть за стол', callback_data='bj_join')],
        [InlineKeyboardButton('Начать игру', callback_data='bj_start')]
    ]
    msg = await context.bot.send_message(
        chat.id,
        '🃏 **Блэкджек стол**\nНажмите «Сесть за стол» (1-3 игрока).\n'
        'Когда все готовы, нажмите «Начать игру».\n'
        'Текущие игроки: —',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    games[chat.id]['message_id'] = msg.message_id
    
async def auto_start_game(chat_id, context):
    await asyncio.sleep(90)
    game = games.get(chat_id)
    if game and game['state'] == 'lobby' and len(game['players']) >= 1:
        await start_game(chat_id, context)

async def lobby_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = games.get(chat_id)
    if not game or game['state'] != 'lobby':
        await query.edit_message_text('Стол уже неактуален.')
        return

    user = query.from_user
    data = query.data

    if data == 'bj_join':
        if user.id in game['players']:
            await query.answer('Вы уже за столом.', show_alert=False)
            return
        if len(game['players']) >= 3:
            await query.answer('За столом максимум 3 игрока.', show_alert=True)
            return
        game['players'].append(user.id)
        game['names'][user.id] = user.first_name
    elif data == 'bj_leave':
        if user.id in game['players']:
            game['players'].remove(user.id)
            del game['names'][user.id]
    elif data == 'bj_start':
        if len(game['players']) < 1:
            await query.answer('Нужен хотя бы 1 игрок.', show_alert=True)
            return
        # Отменяем таймер, если он был (на всякий случай)
        if game.get('timer_task'):
            game['timer_task'].cancel()
        await start_game(chat_id, context)
        return

    # Формируем неизменную клавиатуру (всегда видна всем)
    keyboard = [
        [InlineKeyboardButton('Сесть за стол', callback_data='bj_join'),
         InlineKeyboardButton('Выйти из-за стола', callback_data='bj_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='bj_start')]
    ]
    names = ', '.join(f'@{game["names"][uid]}' for uid in game['players']) or '—'
    await query.edit_message_text(
        f'🃏 **Блэкджек стол**\nТекущие игроки: {names}\n'
        f'Нажмите «Сесть» или «Выйти». Когда все готовы — «Начать игру».',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === Игровой процесс ===
async def start_game(chat_id, context):
    game = games[chat_id]
    game['state'] = 'playing'
    game['deck'] = new_deck()
    game['hands'] = {}
    game['scores'] = {}
    game['status'] = {}   # 'playing', 'stood', 'busted', 'left'
    game['dealer_hand'] = []
    game['current_player_index'] = 0

    # Раздача карт
    for uid in game['players']:
        game['hands'][uid] = [game['deck'].pop(), game['deck'].pop()]
        game['status'][uid] = 'playing'
    game['dealer_hand'] = [game['deck'].pop(), game['deck'].pop()]

    # Личные сообщения с картами
    for uid in game['players']:
        hand = game['hands'][uid]
        text = f'🃏 Ваша рука: {hand_display(hand)}'
        try:
            await context.bot.send_message(uid, text, protect_content=True)
        except:
            pass

    # Общее сообщение: карты дилера (одна закрыта)
    dealer_visible = f'{game["dealer_hand"][0]} ??'
    names = ', '.join(f'@{game["names"][uid]}' for uid in game['players'])
    msg = await context.bot.send_message(
        chat_id,
        f'♠️♥️ **Игра началась!**\nИгроки: {names}\n'
        f'Дилер: {dealer_visible}\n\n'
        f'Ход первого игрока...'
    )
    game['game_message_id'] = msg.message_id
    # Запуск хода первого игрока
    await next_player_turn(chat_id, context)

async def next_player_turn(chat_id, context):
    game = games[chat_id]
    # Найти следующего игрока со статусом 'playing'
    players = game['players']
    idx = game.get('current_player_index', 0)
    while idx < len(players):
        uid = players[idx]
        if game['status'][uid] == 'playing':
            game['current_player_index'] = idx
            await send_turn_message(chat_id, uid, context)
            return
        idx += 1
    # Все отыграли – ход дилера
    await dealer_turn(chat_id, context)

async def send_turn_message(chat_id, user_id, context):
    game = games[chat_id]
    hand = game['hands'][user_id]
    name = game['names'][user_id]

    # Кнопки только для текущего игрока
    keyboard = [
        [InlineKeyboardButton('Взять', callback_data=f'bj_hit_{user_id}'),
         InlineKeyboardButton('Хватит', callback_data=f'bj_stand_{user_id}')],
        [InlineKeyboardButton('Сдаться', callback_data=f'bj_surrender_{user_id}')]
    ]
    text = f'🎲 Ход @{name}\nВаша рука: {hand_display(hand)}\nВыберите действие:'
    msg = await context.bot.send_message(
        chat_id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    game['turn_message_id'] = msg.message_id
    # Таймер авто-хода (60 сек)
    if game.get('turn_timer'):
        game['turn_timer'].cancel()
    game['turn_timer'] = asyncio.create_task(auto_stand(chat_id, user_id, context))

async def auto_stand(chat_id, user_id, context):
    await asyncio.sleep(60)
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return
    if game['status'].get(user_id) == 'playing':
        # Автоматический хватит
        await stand_action(chat_id, user_id, context, automatic=True)

async def hit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, uid_str = query.data.split('_')
    user_id = int(uid_str)
    if update.effective_user.id != user_id:
        await query.answer('Сейчас не ваш ход.', show_alert=False)
        return
    chat_id = query.message.chat.id
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return

    # Отменить таймер
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    # Взять карту
    card = game['deck'].pop()
    game['hands'][user_id].append(card)
    total = hand_value(game['hands'][user_id])
    name = game['names'][user_id]
    # Удалить сообщение с кнопками
    await query.message.delete()

    if total > 21:
        game['status'][user_id] = 'busted'
        await context.bot.send_message(chat_id, f'@{name} берёт {card} — перебор ({total}) 💥')
        # Следующий игрок
        game['current_player_index'] += 1
        await next_player_turn(chat_id, context)
    else:
        # Обновить информацию о ходе – отправить новое сообщение с кнопками
        hand = game['hands'][user_id]
        keyboard = [
            [InlineKeyboardButton('Взять', callback_data=f'bj_hit_{user_id}'),
             InlineKeyboardButton('Хватит', callback_data=f'bj_stand_{user_id}')],
            [InlineKeyboardButton('Сдаться', callback_data=f'bj_surrender_{user_id}')]
        ]
        text = f'🎲 Ход @{name}\nВаша рука: {hand_display(hand)}\nВыберите действие:'
        msg = await context.bot.send_message(
            chat_id,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        game['turn_message_id'] = msg.message_id
        # Запустить таймер заново
        game['turn_timer'] = asyncio.create_task(auto_stand(chat_id, user_id, context))

async def stand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, uid_str = query.data.split('_')
    user_id = int(uid_str)
    if update.effective_user.id != user_id:
        await query.answer('Сейчас не ваш ход.', show_alert=False)
        return
    chat_id = query.message.chat.id
    await stand_action(chat_id, user_id, context)

async def stand_action(chat_id, user_id, context, automatic=False):
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return
    if game['status'].get(user_id) != 'playing':
        return

    # Отменить таймер
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    game['status'][user_id] = 'stood'
    total = hand_value(game['hands'][user_id])
    name = game['names'][user_id]
    if automatic:
        msg_text = f'@{name} автоматически остановился на {total}'
    else:
        msg_text = f'@{name} остановился на {total}'
    await context.bot.send_message(chat_id, msg_text)

    # Удалить сообщение с кнопками, если есть
    if game.get('turn_message_id'):
        try:
            await context.bot.delete_message(chat_id, game['turn_message_id'])
        except:
            pass
    game['current_player_index'] += 1
    await next_player_turn(chat_id, context)

async def surrender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, uid_str = query.data.split('_')
    user_id = int(uid_str)
    if update.effective_user.id != user_id:
        await query.answer('Сейчас не ваш ход.', show_alert=False)
        return
    chat_id = query.message.chat.id
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return

    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    game['status'][user_id] = 'left'
    name = game['names'][user_id]
    await context.bot.send_message(chat_id, f'@{name} сдался и выбывает.')

    # Удалить сообщение с кнопками
    if game.get('turn_message_id'):
        try:
            await context.bot.delete_message(chat_id, game['turn_message_id'])
        except:
            pass
    # Если не осталось играющих — сразу завершить
    active = any(game['status'][uid] == 'playing' for uid in game['players'])
    if not active:
        await end_game(chat_id, context)
        return

    game['current_player_index'] += 1
    await next_player_turn(chat_id, context)

# === Ход дилера ===
async def dealer_turn(chat_id, context):
    game = games[chat_id]
    game['state'] = 'dealer'
    # Вскрыть вторую карту
    dhand = game['dealer_hand']
    await context.bot.send_message(
        chat_id,
        f'🔍 Дилер вскрывает: {dhand[0]} {dhand[1]} ({hand_value(dhand)} очков)'
    )
    await asyncio.sleep(1)
    while hand_value(dhand) < 17:
        card = game['deck'].pop()
        dhand.append(card)
        await context.bot.send_message(
            chat_id,
            f'Дилер берёт {card} — теперь {hand_value(dhand)} очков'
        )
        await asyncio.sleep(1)
    await end_game(chat_id, context)

# === Подведение итогов ===
async def end_game(chat_id, context):
    game = games[chat_id]
    game['state'] = 'finished'
    dealer_total = hand_value(game['dealer_hand'])
    results = []
    for uid in game['players']:
        name = game['names'][uid]
        status = game['status'][uid]
        if status == 'busted':
            results.append(f'@{name}: перебор — поражение')
        elif status == 'left':
            results.append(f'@{name}: сдался — поражение')
        else:
            total = hand_value(game['hands'][uid])
            if dealer_total > 21:
                results.append(f'@{name}: {total} — победа (дилер перебрал)')
            elif total > dealer_total:
                results.append(f'@{name}: {total} — победа')
            elif total < dealer_total:
                results.append(f'@{name}: {total} — поражение')
            else:
                results.append(f'@{name}: {total} — ничья')
    text = '🏆 Результаты:\n' + '\n'.join(results)
    text += f'\nДилер: {hand_display(game["dealer_hand"])}'
    keyboard = [[InlineKeyboardButton('Новая игра', callback_data='bj_new_game')]]
    await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    if chat_id in games:
        del games[chat_id]
    # Запустить новое лобби
    await query.message.reply_text('Начинаем новую игру. /bj или «блэкджек»')
    # Можно сразу вызвать start_lobby, но проще пусть игрок вызовет команду

# === Запуск через текст (с проверкой обращения) ===
async def text_blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    if chat.type == 'private':
        await start_lobby(update, context)
        return
    # Группа: проверяем обращение к боту
    bot_username = context.bot.username.lower()
    text = message.text.lower()
    mentioned = f'@{bot_username}' in text
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        mentioned = True
    if mentioned:
        await start_lobby(update, context)

# Регистрируемые обработчики (для main.py)
def register_handlers(app):
    app.add_handler(CallbackQueryHandler(lobby_button, pattern='^bj_(join|leave|start)$'))
    app.add_handler(CallbackQueryHandler(hit, pattern='^bj_hit_'))
    app.add_handler(CallbackQueryHandler(stand, pattern='^bj_stand_'))
    app.add_handler(CallbackQueryHandler(surrender, pattern='^bj_surrender_'))
    app.add_handler(CallbackQueryHandler(new_game, pattern='^bj_new_game$'))

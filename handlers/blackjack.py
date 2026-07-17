import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

games = {}
balances = {}  # user_id: int

# --- Баланс ---
def get_balance(user_id):
    return balances.get(user_id, 0)

def set_balance(user_id, amount):
    balances[user_id] = amount

def init_balance(user_id):
    if user_id not in balances:
        balances[user_id] = 100  # стартовые 100 фишек

# --- Колода и подсчёт ---
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
        await context.bot.send_message(chat.id, 'Игра уже идёт. Дождитесь завершения.')
        return

    games[chat.id] = {
        'players': [],
        'names': {},
        'bets': {},       # user_id: сумма ставки (10 или 20)
        'state': 'lobby',
        'message_id': None
    }

    keyboard = [
        [InlineKeyboardButton('Сесть за стол', callback_data='bj_join'),
         InlineKeyboardButton('Выйти из-за стола', callback_data='bj_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='bj_start')]
    ]
    msg = await context.bot.send_message(
        chat.id,
        '🃏 Блэкджек стол\nСтавка: 10 фишек.\n'
        'Баланс участников отображается рядом с именем.\n'
        'Текущие игроки: —',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    games[chat.id]['message_id'] = msg.message_id

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
        init_balance(user.id)   # выдаём 100, если нет
        if user.id in game['players']:
            await query.answer('Вы уже за столом.', show_alert=False)
            return
        if len(game['players']) >= 3:
            await query.answer('Максимум 3 игрока.', show_alert=True)
            return
        if get_balance(user.id) < 10:
            await query.answer('Недостаточно фишек (нужно 10). Ваш баланс: ' + str(get_balance(user.id)), show_alert=True)
            return
        # Списываем ставку
        set_balance(user.id, get_balance(user.id) - 10)
        game['players'].append(user.id)
        game['names'][user.id] = user.first_name
        game['bets'][user.id] = 10
    elif data == 'bj_leave':
        if user.id in game['players']:
            # Возвращаем ставку
            set_balance(user.id, get_balance(user.id) + game['bets'][user.id])
            game['players'].remove(user.id)
            del game['names'][user.id]
            del game['bets'][user.id]
    elif data == 'bj_start':
        if len(game['players']) < 1:
            await query.answer('Нужен хотя бы 1 игрок.', show_alert=True)
            return
        await start_game(chat_id, context)
        return

    # Обновляем сообщение лобби
    names_parts = []
    for uid in game['players']:
        bal = get_balance(uid)
        names_parts.append(f'@{game["names"][uid]} ({bal} фишек)')
    names = ', '.join(names_parts) or '—'
    keyboard = [
        [InlineKeyboardButton('Сесть за стол', callback_data='bj_join'),
         InlineKeyboardButton('Выйти из-за стола', callback_data='bj_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='bj_start')]
    ]
    await query.edit_message_text(
        f'🃏 Блэкджек стол\nСтавка: 10 фишек.\n'
        f'Текущие игроки: {names}',
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

    for uid in game['players']:
        game['hands'][uid] = [game['deck'].pop(), game['deck'].pop()]
        game['status'][uid] = 'playing'
    game['dealer_hand'] = [game['deck'].pop(), game['deck'].pop()]

    # Публичное сообщение со всеми руками
    lines = []
    for uid in game['players']:
        hand = game['hands'][uid]
        name = game['names'][uid]
        lines.append(f'@{name}: {hand_display(hand)} (ставка {game["bets"][uid]})')
    dealer_visible = f'{game["dealer_hand"][0]} ??'
    lines.append(f'Дилер: {dealer_visible}')
    msg = await context.bot.send_message(chat_id, '♠️♥️ Игра началась!\n' + '\n'.join(lines))
    game['game_message_id'] = msg.message_id
    await next_player_turn(chat_id, context)

async def next_player_turn(chat_id, context):
    game = games[chat_id]
    players = game['players']
    idx = game.get('current_player_index', 0)
    while idx < len(players):
        uid = players[idx]
        if game['status'][uid] == 'playing':
            game['current_player_index'] = idx
            await send_turn_message(chat_id, uid, context)
            return
        idx += 1
    await dealer_turn(chat_id, context)

async def send_turn_message(chat_id, user_id, context):
    game = games[chat_id]
    hand = game['hands'][user_id]
    name = game['names'][user_id]

    keyboard = [
        [InlineKeyboardButton('Взять', callback_data=f'bj_hit_{user_id}'),
         InlineKeyboardButton('Хватит', callback_data=f'bj_stand_{user_id}')]
    ]
    # Кнопка удвоения, если 2 карты и баланс >= 10
    if len(hand) == 2 and get_balance(user_id) >= 10:
        keyboard.append([InlineKeyboardButton('Удвоить (+10)', callback_data=f'bj_double_{user_id}')])
    keyboard.append([InlineKeyboardButton('Сдаться', callback_data=f'bj_surrender_{user_id}')])

    text = f'🎲 Ход @{name}\nВаша рука: {hand_display(hand)}\nБаланс: {get_balance(user_id)} фишек'
    msg = await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
    game['turn_message_id'] = msg.message_id
    # Таймер авто-хода 60 сек
    if game.get('turn_timer'):
        game['turn_timer'].cancel()
    game['turn_timer'] = asyncio.create_task(auto_stand(chat_id, user_id, context))

async def auto_stand(chat_id, user_id, context):
    await asyncio.sleep(60)
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return
    if game['status'].get(user_id) == 'playing':
        await stand_action(chat_id, user_id, context, automatic=True)

# --- Действия игрока ---
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
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    card = game['deck'].pop()
    game['hands'][user_id].append(card)
    total = hand_value(game['hands'][user_id])
    name = game['names'][user_id]
    await query.message.delete()
    if total > 21:
        game['status'][user_id] = 'busted'
        await context.bot.send_message(chat_id, f'@{name} берёт {card} — перебор ({total}) 💥')
        game['current_player_index'] += 1
        await next_player_turn(chat_id, context)
    else:
        await context.bot.send_message(chat_id, f'@{name} берёт {card} — теперь {hand_display(game["hands"][user_id])}')
        await send_turn_message(chat_id, user_id, context)

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
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    game['status'][user_id] = 'stood'
    total = hand_value(game['hands'][user_id])
    name = game['names'][user_id]
    msg = f'@{name} остановился на {total}' + (' (автоматически)' if automatic else '')
    await context.bot.send_message(chat_id, msg)
    # Удаляем сообщение с кнопками
    if game.get('turn_message_id'):
        try:
            await context.bot.delete_message(chat_id, game['turn_message_id'])
        except:
            pass
    game['current_player_index'] += 1
    await next_player_turn(chat_id, context)

async def double_down(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if game['status'].get(user_id) != 'playing':
        return
    if len(game['hands'][user_id]) != 2:
        await query.answer('Удвоить можно только с первыми двумя картами.')
        return
    if get_balance(user_id) < 10:
        await query.answer('Недостаточно фишек для удвоения.', show_alert=True)
        return
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    # Списываем ещё 10
    set_balance(user_id, get_balance(user_id) - 10)
    game['bets'][user_id] += 10  # теперь ставка 20
    name = game['names'][user_id]
    await context.bot.send_message(chat_id, f'@{name} удваивает ставку до {game["bets"][user_id]} фишек!')
    await query.message.delete()
    # Берём одну карту
    card = game['deck'].pop()
    game['hands'][user_id].append(card)
    total = hand_value(game['hands'][user_id])
    await context.bot.send_message(chat_id, f'@{name} получает {card} — теперь {hand_display(game["hands"][user_id])}')
    if total > 21:
        game['status'][user_id] = 'busted'
        await context.bot.send_message(chat_id, f'@{name} перебор! 💥')
    else:
        game['status'][user_id] = 'stood'
        await context.bot.send_message(chat_id, f'@{name} завершает ход (после удвоения).')
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
    await context.bot.send_message(chat_id, f'@{name} сдался и теряет ставку.')
    if game.get('turn_message_id'):
        try:
            await context.bot.delete_message(chat_id, game['turn_message_id'])
        except:
            pass
    game['current_player_index'] += 1
    await next_player_turn(chat_id, context)

# --- Дилер ---
async def dealer_turn(chat_id, context):
    game = games[chat_id]
    game['state'] = 'dealer'
    dhand = game['dealer_hand']
    await context.bot.send_message(chat_id, f'🔍 Дилер вскрывает: {hand_display(dhand)}')
    await asyncio.sleep(1)
    while hand_value(dhand) < 17:
        card = game['deck'].pop()
        dhand.append(card)
        await context.bot.send_message(chat_id, f'Дилер берёт {card} — {hand_value(dhand)} очков')
        await asyncio.sleep(1)
    await end_game(chat_id, context)

# --- Итоги и выплаты ---
async def end_game(chat_id, context):
    game = games[chat_id]
    game['state'] = 'finished'
    dealer_total = hand_value(game['dealer_hand'])
    results = []
    for uid in game['players']:
        name = game['names'][uid]
        bet = game['bets'][uid]
        status = game['status'][uid]
        if status == 'busted':
            results.append(f'@{name}: перебор, потеря {bet} фишек. Баланс: {get_balance(uid)}')
        elif status == 'left':
            results.append(f'@{name}: сдался, потеря {bet} фишек. Баланс: {get_balance(uid)}')
        else:
            total = hand_value(game['hands'][uid])
            if dealer_total > 21:
                win = bet * 2
                set_balance(uid, get_balance(uid) + win)
                results.append(f'@{name}: {total} — победа (дилер перебрал), +{win} фишек. Баланс: {get_balance(uid)}')
            elif total > dealer_total:
                win = bet * 2
                set_balance(uid, get_balance(uid) + win)
                results.append(f'@{name}: {total} — победа, +{win} фишек. Баланс: {get_balance(uid)}')
            elif total < dealer_total:
                results.append(f'@{name}: {total} — поражение, потеря {bet} фишек. Баланс: {get_balance(uid)}')
            else:
                # Ничья: возврат ставки
                set_balance(uid, get_balance(uid) + bet)
                results.append(f'@{name}: {total} — ничья, возврат {bet} фишек. Баланс: {get_balance(uid)}')
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
    await query.message.reply_text('Новая игра. Напишите "блэкджек" или /bj для старта.')

# --- Команда /balance ---
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_balance(user_id)
    bal = get_balance(user_id)
    await update.message.reply_text(f'Ваш баланс: {bal} фишек.')

# --- Запуск через текст (блэкджек) ---
async def text_blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    if chat.type == 'private':
        await start_lobby(update, context)
        return
    bot_username = context.bot.username.lower()
    text = message.text.lower()
    mentioned = f'@{bot_username}' in text
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        mentioned = True
    if mentioned:
        await start_lobby(update, context)

# --- Регистрация обработчиков (вызывается из main.py) ---
def register_handlers(app):
    app.add_handler(CallbackQueryHandler(lobby_button, pattern='^bj_(join|leave|start)$'))
    app.add_handler(CallbackQueryHandler(hit, pattern='^bj_hit_'))
    app.add_handler(CallbackQueryHandler(stand, pattern='^bj_stand_'))
    app.add_handler(CallbackQueryHandler(double_down, pattern='^bj_double_'))
    app.add_handler(CallbackQueryHandler(surrender, pattern='^bj_surrender_'))
    app.add_handler(CallbackQueryHandler(new_game, pattern='^bj_new_game$'))

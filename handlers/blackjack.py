import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from wallet import get_balance, add_balance
from queue_manager import add_to_queue, pop_next_game
from handlers import slots

logger = logging.getLogger(__name__)

games = {}

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

def card_rank(card):
    return card[:-1]

# Персонажи дилера
DEALERS = [
    {"name": "Сильвестр", "emoji": "👨‍💼", "phrases": {
        "start": ["Делайте ваши ставки, господа!", "Начнём игру!", "Удачи за столом!"],
        "blackjack": ["Блэкджек! Поздравляю, везунчик!", "Блэкджек! Сегодня ваш день!"],
        "bust": ["Перебор! Увы, но банк мой.", "Перебор! Попробуйте ещё раз."],
        "win": ["Вы выиграли! Забирайте свой выигрыш.", "Поздравляю, выигрыш ваш!"],
        "push": ["Ничья. Остаёмся при своих.", "Ничья, все довольны."],
        "lose": ["Дилер выигрывает. Повезёт в следующий раз.", "Крупье забирает банк."],
        "split": ["Разделяем карты. Удваиваем шансы!", "Сплит! Интересный ход."]
    }},
    {"name": "Гена", "emoji": "🧔", "phrases": {
        "start": ["Поехали!", "Ставки сделаны, ставок больше нет!", "Играем по-крупному!"],
        "blackjack": ["Ого! Блэкджек!", "Двадцать одно! Поздравляю."],
        "bust": ["Перебор. Сочувствую.", "Многовато, друг."],
        "win": ["Ваша взяла! Забирайте.", "Победа за вами."],
        "push": ["Ничья, бывает.", "Разошлись миром."],
        "lose": ["Увы, проигрыш.", "Дилер побеждает."],
        "split": ["Сплит! Удачи с двумя руками.", "Разделили, теперь играем вдвойне."]
    }},
    {"name": "Нина", "emoji": "👩‍💼", "phrases": {
        "start": ["Приятной игры!", "Ставки, пожалуйста.", "Да начнётся игра!"],
        "blackjack": ["Блэкджек! Великолепно!", "Идеально! Блэкджек!"],
        "bust": ["Перебор. Увы.", "Слишком много, проигрыш."],
        "win": ["Ваш выигрыш, поздравляю!", "Вы сегодня в ударе!"],
        "push": ["Ничья. Никто не выиграл.", "Поровну."],
        "lose": ["Дилер выигрывает.", "Не расстраивайтесь, повезёт в другой раз."],
        "split": ["Сплит! Интересное решение.", "Две руки — двойной азарт."]
    }},
    {"name": "Джесси", "emoji": "👩‍🦰", "phrases": {
        "start": ["Погнали!", "Ставки на стол!", "Удачи, господа!"],
        "blackjack": ["Блэкджек! Просто бомба!", "Натуральная двадцать одно!"],
        "bust": ["Ой, перебор. Сочувствую.", "Многовато, приятель."],
        "win": ["Ваша взяла! Круто!", "Поздравляю с победой!"],
        "push": ["Ничья, бывает.", "Остаёмся при своих."],
        "lose": ["Дилер выиграл. Не повезло.", "Моя взяла!"],
        "split": ["Сплит! Давайте удвоим!", "Разделили карты, теперь интереснее."]
    }},
    {"name": "Рамзес", "emoji": "👨‍🦳", "phrases": {
        "start": ["Приступим.", "Ставки приняты.", "Играем."],
        "blackjack": ["Блэкджек. Поздравляю.", "Двадцать одно. Заслуженно."],
        "bust": ["Перебор. Проигрыш.", "Слишком много."],
        "win": ["Вы выиграли. Поздравляю.", "Ваша победа."],
        "push": ["Ничья.", "Равный счёт."],
        "lose": ["Дилер победил.", "В этот раз удача не на вашей стороне."],
        "split": ["Сплит. Хороший ход.", "Разделяем."]
    }},
    {"name": "Ева", "emoji": "👩", "phrases": {
        "start": ["Удачи за столом!", "Ставки сделаны.", "Начинаем!"],
        "blackjack": ["Блэкджек! Браво!", "Двадцать одно! Отлично!"],
        "bust": ["Перебор. Увы.", "Не повезло."],
        "win": ["Ваш выигрыш! Поздравляю!", "Победа!"],
        "push": ["Ничья.", "Поровну, бывает."],
        "lose": ["Дилер выигрывает.", "Крупье забирает."],
        "split": ["Сплит! Удваиваем.", "Разделили, играем дальше."]
    }}
]

def dealer_say(game, event):
    dealer = game.get('dealer')
    if not dealer or event not in dealer['phrases']:
        return ""
    return random.choice(dealer['phrases'][event])

def dealer_prefix(game):
    d = game.get('dealer')
    if d:
        return f"{d['emoji']} {d['name']}"
    return ""

# === Лобби ===
async def start_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    # Проверка, не занят ли чат дураком
    try:
        from handlers.durak import durak_games
        if chat.id in durak_games and durak_games[chat.id].get('state') != 'finished':
            keyboard = [
                [InlineKeyboardButton('Да (очередь)', callback_data='queue_blackjack')],
                [InlineKeyboardButton('Нет', callback_data='queue_cancel')],
                [InlineKeyboardButton('Слоты 🎰', callback_data='queue_play_slots')]
            ]
            await context.bot.send_message(
                chat.id,
                f"Сейчас идёт игра «Дурак». Хотите занять очередь на блэкджек? Или попробуйте слоты!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                message_thread_id=thread_id
            )
            return
    except ImportError:
        pass

    games[chat.id] = {
        'players': [],
        'names': {},
        'bets': {},
        'bet_amount': 0,
        'state': 'lobby',
        'message_id': None,
        'thread_id': thread_id,
        'dealer': random.choice(DEALERS)
    }

    keyboard = [
        [InlineKeyboardButton('10', callback_data='bj_bet_10'),
         InlineKeyboardButton('25', callback_data='bj_bet_25'),
         InlineKeyboardButton('50', callback_data='bj_bet_50'),
         InlineKeyboardButton('100', callback_data='bj_bet_100')],
        [InlineKeyboardButton('Сесть за стол', callback_data='bj_join'),
         InlineKeyboardButton('Выйти', callback_data='bj_leave')],
        [InlineKeyboardButton('Начать игру (1-3 игрока)', callback_data='bj_start')],
        [InlineKeyboardButton('🎭 Сменить дилера', callback_data='bj_dealer')]
    ]
    d = games[chat.id]['dealer']
    msg = await context.bot.send_message(
        chat.id,
        f"🃏 Блэкджек стол\nДилер: {d['emoji']} {d['name']}\nВыберите ставку и нажмите «Сесть за стол».",
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id
    )
    games[chat.id]['message_id'] = msg.message_id

async def update_lobby_message(chat_id, context):
    game = games[chat_id]
    bet_text = f"Ставка: {game['bet_amount']} фишек" if 'bet_amount' in game and game['bet_amount'] > 0 else "Ставка не выбрана"
    names_parts = []
    for uid in game['players']:
        bal = get_balance(uid)
        names_parts.append(f'@{game["names"][uid]} ({bal} фишек)')
    names = ', '.join(names_parts) if names_parts else '—'

    keyboard = []
    if game.get('bet_amount', 0) == 0:
        keyboard.append([
            InlineKeyboardButton('10', callback_data='bj_bet_10'),
            InlineKeyboardButton('25', callback_data='bj_bet_25'),
            InlineKeyboardButton('50', callback_data='bj_bet_50'),
            InlineKeyboardButton('100', callback_data='bj_bet_100')
        ])
    keyboard.append([
        InlineKeyboardButton('Сесть за стол', callback_data='bj_join'),
        InlineKeyboardButton('Выйти', callback_data='bj_leave')
    ])
    keyboard.append([InlineKeyboardButton('Начать игру (1-3 игрока)', callback_data='bj_start')])
    keyboard.append([InlineKeyboardButton('🎭 Сменить дилера', callback_data='bj_dealer')])

    d = game.get('dealer', {})
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=f"🃏 Блэкджек стол\nДилер: {d.get('emoji','')} {d.get('name','')}\n{bet_text}\nТекущие игроки: {names}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Failed to update lobby: {e}")

async def lobby_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    if data == 'queue_blackjack':
        success, msg = add_to_queue(chat_id, 'блэкджек', bet=10, player_id=query.from_user.id)
        await query.edit_message_text(msg)
        return
    if data == 'queue_cancel':
        await query.edit_message_text("Ок, ожидайте.")
        return
    if data == 'queue_play_slots':
        await slots.start_slots(update, context)
        return

    game = games.get(chat_id)
    if not game or game['state'] != 'lobby':
        await query.edit_message_text('Стол уже неактуален.')
        return

    user = query.from_user

    if data.startswith('bj_bet_'):
        bet = int(data.split('_')[2])
        game['bet_amount'] = bet
        await query.answer(f'Ставка: {bet} фишек.')
        await update_lobby_message(chat_id, context)
        return
    if data == 'bj_join':
        if 'bet_amount' not in game or game['bet_amount'] == 0:
            await query.answer('Сначала выберите ставку.', show_alert=True)
            return
        if user.id in game['players']:
            await query.answer('Вы уже за столом.', show_alert=False)
            return
        if len(game['players']) >= 3:
            await query.answer('Максимум 3 игрока.', show_alert=True)
            return
        if get_balance(user.id) < game['bet_amount']:
            await query.answer(f'Недостаточно фишек (нужно {game["bet_amount"]}). Ваш баланс: {get_balance(user.id)}', show_alert=True)
            return
        add_balance(user.id, -game['bet_amount'])
        game['players'].append(user.id)
        game['names'][user.id] = user.first_name
        game['bets'][user.id] = game['bet_amount']
    elif data == 'bj_leave':
        if user.id in game['players']:
            add_balance(user.id, game['bets'][user.id])
            game['players'].remove(user.id)
            del game['names'][user.id]
            del game['bets'][user.id]
        else:
            await query.answer('Вы не за столом.', show_alert=False)
    elif data == 'bj_dealer':
        dealer_buttons = []
        for i, dealer in enumerate(DEALERS):
            dealer_buttons.append([InlineKeyboardButton(f"{dealer['emoji']} {dealer['name']}", callback_data=f'bj_set_dealer_{i}')])
        dealer_buttons.append([InlineKeyboardButton('Назад', callback_data='bj_back_to_lobby')])
        await query.edit_message_text(
            "Выберите дилера:",
            reply_markup=InlineKeyboardMarkup(dealer_buttons)
        )
        return
    elif data.startswith('bj_set_dealer_'):
        idx = int(data.split('_')[3])
        if 0 <= idx < len(DEALERS):
            game['dealer'] = DEALERS[idx]
        await update_lobby_message(chat_id, context)
        return
    elif data == 'bj_back_to_lobby':
        await update_lobby_message(chat_id, context)
        return
    elif data == 'bj_start':
        if len(game['players']) < 1:
            await query.answer('Нужен хотя бы 1 игрок.', show_alert=True)
            return
        if 'bet_amount' not in game or game['bet_amount'] == 0:
            await query.answer('Сначала выберите ставку.', show_alert=True)
            return
        await start_game(chat_id, context)
        return

    await update_lobby_message(chat_id, context)

# === Игровой процесс ===
async def start_game(chat_id, context):
    game = games[chat_id]
    game['state'] = 'playing'
    game['deck'] = new_deck()
    game['hands'] = {}
    game['status'] = {}
    game['current_hand'] = {}
    game['dealer_hand'] = []
    game['current_player_index'] = 0
    game['turn_message_id'] = None
    game['turn_timer'] = None

    for uid in game['players']:
        hand1 = [game['deck'].pop(), game['deck'].pop()]
        game['hands'][uid] = [hand1]
        game['status'][uid] = ['playing']
        game['current_hand'][uid] = 0

    game['dealer_hand'] = [game['deck'].pop(), game['deck'].pop()]

    dealer = game.get('dealer')
    thread_id = game.get('thread_id')
    dealer_msg = dealer_say(game, 'start')
    lines = []
    for uid in game['players']:
        hand = game['hands'][uid][0]
        lines.append(f'@{game["names"][uid]}: {hand_display(hand)} (ставка {game["bets"][uid]})')
    dealer_visible = f'{game["dealer_hand"][0]} ??'
    lines.append(f'Дилер: {dealer_visible}')
    msg_text = f"{dealer_prefix(game)}: {dealer_msg}\n" + '\n'.join(lines)
    msg = await context.bot.send_message(chat_id, msg_text, message_thread_id=thread_id)
    game['game_message_id'] = msg.message_id

    for uid in game['players']:
        hand = game['hands'][uid][0]
        if len(hand) == 2 and hand_value(hand) == 21:
            game['status'][uid] = ['blackjack']
            await context.bot.send_message(
                chat_id,
                f"{dealer_prefix(game)}: @{game['names'][uid]} — блэкджек!",
                message_thread_id=thread_id
            )
    await next_player_turn(chat_id, context)

async def next_player_turn(chat_id, context):
    game = games[chat_id]
    players = game['players']
    idx = game.get('current_player_index', 0)
    while idx < len(players):
        uid = players[idx]
        hands = game['hands'][uid]
        statuses = game['status'][uid]
        current_hand_idx = game['current_hand'].get(uid, 0)

        if current_hand_idx < len(hands) and statuses[current_hand_idx] == 'playing':
            game['current_player_index'] = idx
            await send_turn_message(chat_id, uid, context)
            return
        elif current_hand_idx < len(hands) and statuses[current_hand_idx] in ('blackjack', 'stood', 'busted', 'surrender'):
            game['current_hand'][uid] += 1
            if game['current_hand'][uid] < len(hands):
                continue
            else:
                game['current_player_index'] += 1
                idx = game['current_player_index']
                continue
        else:
            if current_hand_idx >= len(hands):
                game['current_player_index'] += 1
                idx = game['current_player_index']
                continue
            else:
                game['current_hand'][uid] += 1
                continue
    await dealer_turn(chat_id, context)

async def send_turn_message(chat_id, user_id, context):
    game = games[chat_id]
    hand_idx = game['current_hand'][user_id]
    hand = game['hands'][user_id][hand_idx]
    name = game['names'][user_id]
    total = hand_value(hand)

    keyboard = []
    if total < 21:
        keyboard.append([InlineKeyboardButton('Взять', callback_data=f'bj_hit_{user_id}'),
                         InlineKeyboardButton('Хватит', callback_data=f'bj_stand_{user_id}')])
        if len(hand) == 2 and get_balance(user_id) >= game['bets'][user_id]:
            keyboard.append([InlineKeyboardButton('Удвоить (+ставка)', callback_data=f'bj_double_{user_id}')])
        if len(hand) == 2 and card_rank(hand[0]) == card_rank(hand[1]) and len(game['hands'][user_id]) == 1 and get_balance(user_id) >= game['bets'][user_id]:
            keyboard.append([InlineKeyboardButton('Сплит', callback_data=f'bj_split_{user_id}')])
    keyboard.append([InlineKeyboardButton('Сдаться', callback_data=f'bj_surrender_{user_id}')])

    hand_info = f"Рука {hand_idx+1}/{len(game['hands'][user_id])}: " if len(game['hands'][user_id]) > 1 else ""

    text = f"{dealer_prefix(game)}: Ход @{name}\n{hand_info}{hand_display(hand)}\nБаланс: {get_balance(user_id)} фишек."
    msg = await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), message_thread_id=game.get('thread_id'))
    game['turn_message_id'] = msg.message_id

    if game.get('turn_timer'):
        game['turn_timer'].cancel()
    game['turn_timer'] = asyncio.create_task(auto_stand(chat_id, user_id, context))

async def auto_stand(chat_id, user_id, context):
    await asyncio.sleep(60)
    game = games.get(chat_id)
    if not game or game['state'] != 'playing':
        return
    hand_idx = game['current_hand'].get(user_id, 0)
    hands = game['hands'][user_id]
    if hand_idx < len(hands) and game['status'][user_id][hand_idx] == 'playing':
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
    hand_idx = game['current_hand'][user_id]
    hand = game['hands'][user_id][hand_idx]
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    card = game['deck'].pop()
    hand.append(card)
    total = hand_value(hand)
    name = game['names'][user_id]
    await query.message.delete()

    if total == 21:
        game['status'][user_id][hand_idx] = 'stood'
        await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} берёт {card} — {total} очков. Автоматическая остановка.")
        await finish_current_hand(chat_id, user_id, context)
    elif total > 21:
        game['status'][user_id][hand_idx] = 'busted'
        await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} берёт {card} — перебор ({total}) 💥")
        await finish_current_hand(chat_id, user_id, context)
    else:
        await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} берёт {card} — теперь {hand_display(hand)}")
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
    hand_idx = game['current_hand'][user_id]
    if game['status'][user_id][hand_idx] != 'playing':
        return
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    game['status'][user_id][hand_idx] = 'stood'
    total = hand_value(game['hands'][user_id][hand_idx])
    name = game['names'][user_id]
    msg = f"@{name} остановился на {total}" + (' (автоматически)' if automatic else '')
    await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: {msg}")
    if game.get('turn_message_id'):
        try:
            await context.bot.delete_message(chat_id, game['turn_message_id'])
        except:
            pass
    await finish_current_hand(chat_id, user_id, context)

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
    hand_idx = game['current_hand'][user_id]
    hand = game['hands'][user_id][hand_idx]
    if len(hand) != 2 or get_balance(user_id) < game['bets'][user_id]:
        await query.answer('Удвоение недоступно.', show_alert=True)
        return
    if game.get('turn_timer'):
        game['turn_timer'].cancel()

    add_balance(user_id, -game['bets'][user_id])
    game['bets'][user_id] += game['bets'][user_id]
    name = game['names'][user_id]
    await query.message.delete()
    card = game['deck'].pop()
    hand.append(card)
    total = hand_value(hand)
    await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} удваивает ставку до {game['bets'][user_id]} и получает {card} — {hand_display(hand)}")
    if total > 21:
        game['status'][user_id][hand_idx] = 'busted'
        await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} перебор!")
    else:
        game['status'][user_id][hand_idx] = 'stood'
    await finish_current_hand(chat_id, user_id, context)

async def split(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    hands = game['hands'][user_id]
    if len(hands) != 1 or len(hands[0]) != 2 or card_value(hands[0][0]) != card_value(hands[0][1]):
        await query.answer('Сплит невозможен.', show_alert=True)
        return
    if get_balance(user_id) < game['bets'][user_id]:
        await query.answer('Недостаточно фишек для сплита.', show_alert=True)
        return

    add_balance(user_id, -game['bets'][user_id])
    card1, card2 = hands[0]
    hand1 = [card1, game['deck'].pop()]
    hand2 = [card2, game['deck'].pop()]
    game['hands'][user_id] = [hand1, hand2]
    game['status'][user_id] = ['playing', 'playing']
    game['current_hand'][user_id] = 0
    game['bets'][user_id] *= 2
    await query.message.delete()
    await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{game['names'][user_id]} делает сплит! Теперь две руки.")
    await send_turn_message(chat_id, user_id, context)

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

    hand_idx = game['current_hand'][user_id]
    game['status'][user_id][hand_idx] = 'surrender'
    name = game['names'][user_id]
    await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: @{name} сдаётся.")
    await query.message.delete()
    await finish_current_hand(chat_id, user_id, context)

async def finish_current_hand(chat_id, user_id, context):
    game = games[chat_id]
    hand_idx = game['current_hand'][user_id]
    hands = game['hands'][user_id]
    game['current_hand'][user_id] += 1
    if game['current_hand'][user_id] < len(hands):
        await send_turn_message(chat_id, user_id, context)
    else:
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
    thread_id = game.get('thread_id')
    await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: 🔍 Дилер вскрывает: {hand_display(dhand)}", message_thread_id=thread_id)
    await asyncio.sleep(1)
    while hand_value(dhand) < 17:
        if not game['deck']:
            await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: Карты закончились. Дилер останавливается.", message_thread_id=thread_id)
            break
        card = game['deck'].pop()
        dhand.append(card)
        await context.bot.send_message(chat_id, f"{dealer_prefix(game)}: Дилер берёт {card} — {hand_value(dhand)} очков", message_thread_id=thread_id)
        await asyncio.sleep(1)
    await end_game(chat_id, context)

# --- Итоги и выплаты ---
async def end_game(chat_id, context):
    game = games[chat_id]
    game['state'] = 'finished'
    dealer_total = hand_value(game['dealer_hand'])
    dealer_bust = dealer_total > 21
    results = []
    for uid in game['players']:
        name = game['names'][uid]
        hands = game['hands'][uid]
        statuses = game['status'][uid]
        total_bet = game['bets'][uid]
        num_hands = len(hands)
        for i, hand in enumerate(hands):
            stat = statuses[i]
            bet_per_hand = total_bet // num_hands if num_hands > 1 else total_bet
            if stat == 'busted':
                results.append(f'@{name}: перебор (рука {i+1}), потеря {bet_per_hand} фишек.')
            elif stat == 'surrender':
                results.append(f'@{name}: сдался (рука {i+1}), потеря {bet_per_hand} фишек.')
            else:
                total = hand_value(hand)
                if dealer_bust:
                    win = bet_per_hand * 2
                    add_balance(uid, win)
                    results.append(f'@{name}: {total} (рука {i+1}) — победа (дилер перебрал), +{win} фишек.')
                elif total > dealer_total:
                    win = bet_per_hand * 2
                    add_balance(uid, win)
                    results.append(f'@{name}: {total} (рука {i+1}) — победа, +{win} фишек.')
                elif total < dealer_total:
                    results.append(f'@{name}: {total} (рука {i+1}) — поражение, потеря {bet_per_hand} фишек.')
                else:
                    add_balance(uid, bet_per_hand)
                    results.append(f'@{name}: {total} (рука {i+1}) — ничья, возврат {bet_per_hand} фишек.')

    dealer_display = hand_display(game['dealer_hand'])
    text = f"{dealer_prefix(game)}: 🏆 Результаты:\n" + '\n'.join(results)
    text += f'\nДилер: {dealer_display}'
    keyboard = [
        [InlineKeyboardButton('Следующий раунд (–10 фишек)', callback_data='bj_next_round')],
        [InlineKeyboardButton('Новая игра', callback_data='bj_new_game')]
    ]
    await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), message_thread_id=game.get('thread_id'))

async def next_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = games.get(chat_id)
    if not game or game['state'] != 'finished':
        await query.edit_message_text('Нет активной игры.')
        return

    players_to_keep = []
    for uid in game['players']:
        if get_balance(uid) >= 10:
            add_balance(uid, -10)
            game['bets'][uid] = 10
            players_to_keep.append(uid)
        else:
            await context.bot.send_message(
                chat_id,
                f'@{game["names"][uid]} исключён: недостаточно фишек.',
                message_thread_id=game.get('thread_id')
            )
    if len(players_to_keep) == 0:
        await query.edit_message_text('Ни у кого нет фишек для продолжения. Игра окончена.')
        del games[chat_id]
        return

    game['players'] = players_to_keep
    game['names'] = {uid: game['names'][uid] for uid in players_to_keep}
    game['bets'] = {uid: game['bets'][uid] for uid in players_to_keep}

    await start_game(chat_id, context)

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    if chat_id in games:
        del games[chat_id]
    await query.message.reply_text('Новая игра. Напишите "блэкджек" или /bj для старта.')

# --- Сброс игры ---
async def reset_bj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username and update.effective_user.username.lower() == 'iamstarhead':
        chat_id = update.effective_chat.id
        if chat_id in games:
            del games[chat_id]
            await update.message.reply_text("Игра в блэкджек сброшена.")
        else:
            await update.message.reply_text("Нет активной игры в блэкджек.")
    else:
        await update.message.reply_text("Нет доступа.")

# --- Запуск через текст ---
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

# --- Регистрация обработчиков ---
def register_handlers(app):
    app.add_handler(CallbackQueryHandler(lobby_button, pattern='^bj_(bet_|join|leave|start|dealer|set_dealer_|back_to_lobby)'))
    app.add_handler(CallbackQueryHandler(hit, pattern='^bj_hit_'))
    app.add_handler(CallbackQueryHandler(stand, pattern='^bj_stand_'))
    app.add_handler(CallbackQueryHandler(double_down, pattern='^bj_double_'))
    app.add_handler(CallbackQueryHandler(split, pattern='^bj_split_'))
    app.add_handler(CallbackQueryHandler(surrender, pattern='^bj_surrender_'))
    app.add_handler(CallbackQueryHandler(next_round, pattern='^bj_next_round$'))
    app.add_handler(CallbackQueryHandler(new_game, pattern='^bj_new_game$'))

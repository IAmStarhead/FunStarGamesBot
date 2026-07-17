import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from wallet import get_balance, add_balance

logger = logging.getLogger(__name__)

# Хранилище игр: ключ — chat_id
durak_games = {}

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {rank: i for i, rank in enumerate(RANKS)}

def new_deck():
    deck = [r + s for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def card_rank(card):
    return card[:-1]

def card_suit(card):
    return card[-1]

def can_beat(attacking_card, defending_card, trump):
    if card_suit(defending_card) == trump and card_suit(attacking_card) != trump:
        return True
    if card_suit(defending_card) == card_suit(attacking_card):
        return CARD_VALUES[card_rank(defending_card)] > CARD_VALUES[card_rank(attacking_card)]
    return False

# === Лобби ===
async def durak_start(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='throw'):
    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if chat.id in durak_games and durak_games[chat.id]['state'] != 'finished':
        await context.bot.send_message(
            chat.id,
            'Игра в дурака уже идёт. Дождитесь завершения.',
            message_thread_id=thread_id
        )
        return

    durak_games[chat.id] = {
        'players': [],
        'names': {},
        'bets': {},
        'state': 'lobby',
        'message_id': None,
        'thread_id': thread_id,
        'mode': mode,
        'bet_amount': 0,
        'vs_bot': False
    }

    keyboard = [
        [InlineKeyboardButton('25 фишек', callback_data='durak_bet_25'),
         InlineKeyboardButton('50 фишек', callback_data='durak_bet_50'),
         InlineKeyboardButton('100 фишек', callback_data='durak_bet_100')],
        [InlineKeyboardButton('Сесть за стол', callback_data='durak_join'),
         InlineKeyboardButton('Выйти', callback_data='durak_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='durak_start')],
        [InlineKeyboardButton('Играть с ботом (1 игрок)', callback_data='durak_play_vs_bot')]
    ]
    mode_names = {'throw': 'Подкидной', 'transfer': 'Переводной', 'simple': 'Простой'}
    msg = await context.bot.send_message(
        chat.id,
        f'🃏 Дурак ({mode_names[mode]})\nВыберите ставку и нажмите «Сесть за стол» (2–4 игрока).\n'
        'Или играйте с ботом, нажав «Играть с ботом» (только 1 игрок).\n'
        'Текущие игроки: —',
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id
    )
    durak_games[chat.id]['message_id'] = msg.message_id

async def update_lobby_message(chat_id, context):
    game = durak_games[chat_id]
    mode_names = {'throw': 'Подкидной', 'transfer': 'Переводной', 'simple': 'Простой'}
    bet_text = f'Ставка: {game["bet_amount"]} фишек' if game['bet_amount'] > 0 else 'Ставка не выбрана'
    names_parts = []
    for uid in game['players']:
        if uid != -1:
            bal = get_balance(uid)
            names_parts.append(f'@{game["names"][uid]} ({bal} фишек)')
        else:
            names_parts.append('Бот')
    names = ', '.join(names_parts) if names_parts else '—'
    keyboard = [
        [InlineKeyboardButton('25 фишек', callback_data='durak_bet_25'),
         InlineKeyboardButton('50 фишек', callback_data='durak_bet_50'),
         InlineKeyboardButton('100 фишек', callback_data='durak_bet_100')],
        [InlineKeyboardButton('Сесть за стол', callback_data='durak_join'),
         InlineKeyboardButton('Выйти', callback_data='durak_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='durak_start')],
        [InlineKeyboardButton('Играть с ботом (1 игрок)', callback_data='durak_play_vs_bot')]
    ]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game['message_id'],
        text=f'🃏 Дурак ({mode_names[game["mode"]]})\n{bet_text}\nТекущие игроки: {names}',
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=game.get('thread_id')
    )

async def durak_lobby_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = durak_games.get(chat_id)
    if not game or game['state'] != 'lobby':
        await query.edit_message_text('Лобби устарело.')
        return

    user = query.from_user
    data = query.data

    if data.startswith('durak_bet_'):
        bet = int(data.split('_')[2])
        game['bet_amount'] = bet
        await query.answer(f'Ставка: {bet} фишек.')
        await update_lobby_message(chat_id, context)
        return
    elif data == 'durak_join':
        if user.id in game['players']:
            await query.answer('Вы уже за столом.', show_alert=False)
            return
        if len(game['players']) >= 4:
            await query.answer('Максимум 4 игрока.', show_alert=True)
            return
        if game['bet_amount'] == 0:
            await query.answer('Сначала выберите ставку.', show_alert=True)
            return
        if get_balance(user.id) < game['bet_amount']:
            await query.answer(f'Недостаточно фишек (нужно {game["bet_amount"]}). Ваш баланс: {get_balance(user.id)}', show_alert=True)
            return
        add_balance(user.id, -game['bet_amount'])
        game['players'].append(user.id)
        game['names'][user.id] = user.first_name
        game['bets'][user.id] = game['bet_amount']
    elif data == 'durak_leave':
        if user.id in game['players']:
            add_balance(user.id, game['bets'][user.id])
            game['players'].remove(user.id)
            del game['names'][user.id]
            del game['bets'][user.id]
    elif data == 'durak_start':
        if len(game['players']) < 2:
            await query.answer('Нужно хотя бы 2 игрока.', show_alert=True)
            return
        if game['bet_amount'] == 0:
            await query.answer('Сначала выберите ставку.', show_alert=True)
            return
        await start_durak_game(chat_id, context)
        return
    elif data == 'durak_play_vs_bot':
        if len(game['players']) != 1 or game['players'][0] == -1:
            await query.answer('Режим с ботом только для одного человека.', show_alert=True)
            return
        if game['bet_amount'] == 0:
            await query.answer('Сначала выберите ставку.', show_alert=True)
            return
        # Добавляем бота
        bot_id = -1
        game['players'].append(bot_id)
        game['names'][bot_id] = 'Бот'
        game['bets'][bot_id] = 0  # бот не вносит ставку, его фишки виртуальны
        game['vs_bot'] = True
        await start_durak_game(chat_id, context)
        return

    await update_lobby_message(chat_id, context)

# === Игровой процесс ===
async def start_durak_game(chat_id, context):
    game = durak_games[chat_id]
    game['state'] = 'playing'
    game['deck'] = new_deck()
    game['trump'] = random.choice(SUITS)
    game['hands'] = {}
    game['table'] = []
    game['turn_order'] = game['players'][:]
    game['attacker_index'] = 0
    game['defender_index'] = 1 % len(game['players'])
    game['phase'] = 'attack'
    game['pass_count'] = 0
    game['turn_timer'] = None
    game['hand_message_ids'] = {}

    for uid in game['players']:
        game['hands'][uid] = [game['deck'].pop() for _ in range(min(6, len(game['deck'])))]

    # Определение первого хода
    if game['mode'] in ('throw', 'transfer'):
        min_rank = len(RANKS)
        first = game['players'][0]
        for uid in game['players']:
            for card in game['hands'][uid]:
                if card_suit(card) == game['trump']:
                    r = CARD_VALUES[card_rank(card)]
                    if r < min_rank:
                        min_rank = r
                        first = uid
        idx = game['players'].index(first)
        game['turn_order'] = game['players'][idx:] + game['players'][:idx]
        game['attacker_index'] = 0
        game['defender_index'] = 1 % len(game['players'])
    else:
        random.shuffle(game['turn_order'])
        game['attacker_index'] = 0
        game['defender_index'] = 1 % len(game['players'])

    # Отправляем карты живым игрокам (не боту)
    for uid in game['players']:
        if uid != -1:
            await send_hand_message(uid, game, context)

    thread_id = game['thread_id']
    names = ', '.join(f'@{game["names"][uid]}' if uid != -1 else 'Бот' for uid in game['players'])
    attacker_id = game['turn_order'][game['attacker_index']]
    await context.bot.send_message(
        chat_id,
        f'♠️ Игра началась! Козырь: {game["trump"]}\n'
        f'Игроки: {names}\n'
        f'Первый ход: @{game["names"][attacker_id] if attacker_id != -1 else "Бот"}\n'
        'Всем игрокам отправлены карты в личные сообщения.',
        message_thread_id=thread_id
    )

    # Если первый ходит бот – запускаем его действие
    if attacker_id == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, attacker_id, context, chat_id)

async def send_hand_message(user_id, game, context):
    """Отправляет/обновляет личное сообщение с картами-кнопками (только для живых игроков)."""
    if user_id == -1:
        return
    hand = game['hands'].get(user_id, [])
    keyboard = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(card, callback_data=f'durak_card_{i}'))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton('Бито', callback_data='durak_action_beaten'),
        InlineKeyboardButton('Забрать', callback_data='durak_action_take'),
        InlineKeyboardButton('Перевести', callback_data='durak_action_transfer')
    ])

    text = f'Ваша рука:\nКозырь: {game["trump"]}'
    if user_id in game.get('hand_message_ids', {}):
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=game['hand_message_ids'][user_id],
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        except:
            pass
    msg = await context.bot.send_message(
        user_id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        protect_content=True
    )
    game['hand_message_ids'][user_id] = msg.message_id

def get_current_player_id(game):
    order = game['turn_order']
    if game['phase'] in ('attack', 'throw'):
        return order[game['attacker_index']]
    elif game['phase'] in ('defend', 'transfer'):
        return order[game['defender_index']]
    return None

# === Обработчик действий от живого игрока ===
async def durak_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    chat_id = None
    game = None
    for cid, g in durak_games.items():
        if g.get('state') == 'playing' and user_id in g['players']:
            chat_id = cid
            game = g
            break
    if not game:
        await query.answer('Нет активной игры с вашим участием.', show_alert=True)
        return

    if data.startswith('durak_card_'):
        idx = int(data.split('_')[2])
        hand = game['hands'][user_id]
        if idx >= len(hand):
            await query.answer('Неверная карта.')
            return
        if user_id != get_current_player_id(game):
            await query.answer('Сейчас не ваш ход.', show_alert=False)
            return
        if game['phase'] == 'attack':
            await attack_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'defend':
            await defend_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'throw':
            await throw_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'transfer':
            await transfer_with_card(user_id, idx, game, context, chat_id)
    elif data == 'durak_action_beaten':
        await action_beaten(user_id, game, context, chat_id)
    elif data == 'durak_action_take':
        await action_take(user_id, game, context, chat_id)
    elif data == 'durak_action_transfer':
        await action_transfer(user_id, game, context, chat_id)

async def attack_with_card(user_id, card_idx, game, context, chat_id):
    hand = game['hands'][user_id]
    card = hand.pop(card_idx)
    game['table'].append((card, user_id, 'attack'))
    game['phase'] = 'defend'
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} заходит {card}',
        message_thread_id=game['thread_id']
    )
    defender_id = game['turn_order'][game['defender_index']]
    if defender_id == -1:
        await bot_turn(chat_id, context)
    else:
        await send_hand_message(defender_id, game, context)
        reset_timer(game, defender_id, context, chat_id)

async def defend_with_card(user_id, card_idx, game, context, chat_id):
    hand = game['hands'][user_id]
    card = hand[card_idx]
    last_attack = next(((c, pid) for c, pid, role in reversed(game['table']) if role == 'attack'), None)
    if not last_attack:
        await context.bot.send_message(user_id, 'Нечего бить.')
        return
    attack_card = last_attack[0]
    if not can_beat(attack_card, card, game['trump']):
        await context.bot.send_message(user_id, 'Эта карта не бьёт.')
        return
    hand.remove(card)
    game['table'].append((card, user_id, 'defend'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} бьёт {card}',
        message_thread_id=game['thread_id']
    )
    attack_cards = [c for c, pid, role in game['table'] if role == 'attack']
    defend_cards = [c for c, pid, role in game['table'] if role == 'defend']
    if len(attack_cards) == len(defend_cards):
        if game['mode'] == 'throw' and len(game['players']) > 2:
            game['phase'] = 'throw'
            game['throw_order'] = (game['attacker_index'] + 1) % len(game['players'])
            next_thrower = game['turn_order'][game['throw_order']]
            if next_thrower == -1:
                await bot_turn(chat_id, context)
            else:
                await send_hand_message(next_thrower, game, context)
                reset_timer(game, next_thrower, context, chat_id)
            await context.bot.send_message(chat_id, 'Можно подкинуть.', message_thread_id=game['thread_id'])
        else:
            await end_turn(game, context, chat_id)
    else:
        if defender_id := game['turn_order'][game['defender_index']] == -1:
            await bot_turn(chat_id, context)
        else:
            await send_hand_message(defender_id, game, context)

async def throw_with_card(user_id, card_idx, game, context, chat_id):
    if game['phase'] != 'throw':
        await context.bot.send_message(user_id, 'Сейчас нельзя подкидывать.')
        return
    throw_order = game.get('throw_order', (game['attacker_index'] + 1) % len(game['players']))
    expected_id = game['turn_order'][throw_order]
    if user_id != expected_id:
        await context.bot.send_message(user_id, 'Сейчас не ваша очередь подкидывать.')
        return
    hand = game['hands'][user_id]
    card = hand[card_idx]
    rank = card_rank(card)
    table_ranks = {card_rank(c) for c, pid, role in game['table']}
    if rank not in table_ranks:
        await context.bot.send_message(user_id, 'Можно подкидывать только карты того же достоинства, что на столе.')
        return
    hand.remove(card)
    game['table'].append((card, user_id, 'attack'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} подкидывает {card}',
        message_thread_id=game['thread_id']
    )
    game['phase'] = 'defend'
    defender_id = game['turn_order'][game['defender_index']]
    if defender_id == -1:
        await bot_turn(chat_id, context)
    else:
        await send_hand_message(defender_id, game, context)
        reset_timer(game, defender_id, context, chat_id)

async def transfer_with_card(user_id, card_idx, game, context, chat_id):
    if game['mode'] != 'transfer':
        await context.bot.send_message(user_id, 'Перевод доступен только в переводном дураке.')
        return
    if game['phase'] != 'transfer':
        await context.bot.send_message(user_id, 'Сейчас нельзя перевести.')
        return
    if user_id != game['turn_order'][game['defender_index']]:
        await context.bot.send_message(user_id, 'Перевести может только отбивающийся.')
        return
    hand = game['hands'][user_id]
    card = hand[card_idx]
    first_attack = next((c for c, pid, role in game['table'] if role == 'attack'), None)
    if not first_attack or card_rank(card) != card_rank(first_attack[0]):
        await context.bot.send_message(user_id, 'Перевести можно только картой того же достоинства.')
        return
    hand.remove(card)
    game['table'].append((card, user_id, 'attack'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} переводит {card}',
        message_thread_id=game['thread_id']
    )
    game['defender_index'] = (game['defender_index'] + 1) % len(game['players'])
    if game['defender_index'] == game['attacker_index']:
        game['phase'] = 'defend'
        defender_id = game['turn_order'][game['defender_index']]
        if defender_id == -1:
            await bot_turn(chat_id, context)
        else:
            await send_hand_message(defender_id, game, context)
            await context.bot.send_message(chat_id, 'Перевод вернулся. Отбивайтесь или забирайте.', message_thread_id=game['thread_id'])
            reset_timer(game, defender_id, context, chat_id)
    else:
        game['phase'] = 'transfer'
        next_defender = game['turn_order'][game['defender_index']]
        if next_defender == -1:
            await bot_turn(chat_id, context)
        else:
            await send_hand_message(next_defender, game, context)
            await context.bot.send_message(chat_id, f'Ход переведён на @{game["names"][next_defender]}.', message_thread_id=game['thread_id'])
            reset_timer(game, next_defender, context, chat_id)

async def action_beaten(user_id, game, context, chat_id):
    if game['phase'] == 'throw' and user_id == get_current_player_id(game):
        game['throw_order'] = (game['throw_order'] + 1) % len(game['players'])
        if game['throw_order'] == game['attacker_index']:
            await end_turn(game, context, chat_id)
        else:
            next_thrower = game['turn_order'][game['throw_order']]
            if next_thrower == -1:
                await bot_turn(chat_id, context)
            else:
                await send_hand_message(next_thrower, game, context)
    elif game['phase'] in ('defend', 'transfer') and user_id == game['turn_order'][game['defender_index']]:
        await context.bot.send_message(user_id, 'Сейчас нельзя сказать "бито".')

async def action_take(user_id, game, context, chat_id):
    if user_id != game['turn_order'][game['defender_index']]:
        await context.bot.send_message(user_id, 'Только защищающийся может забрать.')
        return
    await take_cards(game, context, chat_id)

async def take_cards(game, context, chat_id):
    defender_id = game['turn_order'][game['defender_index']]
    cards = [c for c, pid, role in game['table']]
    game['hands'][defender_id].extend(cards)
    game['table'].clear()
    if defender_id != -1:
        await send_hand_message(defender_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][defender_id]} забирает карты.',
        message_thread_id=game['thread_id']
    )
    await end_turn(game, context, chat_id, skip_attacker_change=True)

async def end_turn(game, context, chat_id, skip_attacker_change=False):
    if game['turn_timer']:
        game['turn_timer'].cancel()
    # Добор карт
    for uid in game['players']:
        while len(game['hands'][uid]) < 6 and game['deck']:
            game['hands'][uid].append(game['deck'].pop())
        if uid != -1:
            await send_hand_message(uid, game, context)
    game['table'].clear()

    # Проверка победы
    for uid in game['players']:
        if not game['hands'][uid] and not game['deck']:
            winner = uid
            if winner == -1:
                await context.bot.send_message(
                    chat_id,
                    '🤖 Бот выиграл! Вы дурак.',
                    message_thread_id=game['thread_id']
                )
            else:
                total_bet = sum(game['bets'].values())
                add_balance(winner, total_bet)
                await context.bot.send_message(
                    chat_id,
                    f'🏆 @{game["names"][winner]} выиграл и забирает банк {total_bet} фишек!',
                    message_thread_id=game['thread_id']
                )
            game['state'] = 'finished'
            durak_games.pop(chat_id, None)
            return

    # Переход хода
    if not skip_attacker_change:
        game['attacker_index'] = game['defender_index']
    else:
        game['attacker_index'] = (game['attacker_index']) % len(game['players'])
    game['defender_index'] = (game['attacker_index'] + 1) % len(game['players'])
    game['phase'] = 'attack'
    next_attacker = game['turn_order'][game['attacker_index']]
    if next_attacker != -1:
        await send_hand_message(next_attacker, game, context)
    await context.bot.send_message(
        chat_id,
        f'Ход переходит к @{game["names"][next_attacker] if next_attacker != -1 else "Бот"}.',
        message_thread_id=game['thread_id']
    )
    if next_attacker == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, next_attacker, context, chat_id)

def reset_timer(game, user_id, context, chat_id):
    if game.get('turn_timer'):
        game['turn_timer'].cancel()
    game['turn_timer'] = asyncio.ensure_future(turn_timeout(chat_id, user_id, context))

async def turn_timeout(chat_id, user_id, context):
    await asyncio.sleep(90)
    game = durak_games.get(chat_id)
    if not game or game['state'] != 'playing':
        return
    if get_current_player_id(game) == user_id:
        await action_take(user_id, game, context, chat_id)

# === Логика бота ===
async def bot_turn(chat_id, context):
    game = durak_games[chat_id]
    if game['state'] != 'playing':
        return
    # Небольшая пауза, чтобы казалось, что бот думает
    await asyncio.sleep(1)
    bot_id = -1
    hand = game['hands'][bot_id]

    if game['phase'] == 'attack':
        # Бот ходит самой младшей картой
        if not hand:
            return
        # Сортируем по достоинству, потом по масти
        hand.sort(key=lambda c: (CARD_VALUES[card_rank(c)], card_suit(c)))
        card = hand[0]
        # Вызываем атаку, эмулируя нажатие на первую карту
        # Можно напрямую вызвать attack_with_card, но нужно аккуратно
        # Проще запрограммировать действия отдельно
        idx = 0
        await attack_with_card(bot_id, idx, game, context, chat_id)
    elif game['phase'] == 'defend':
        # Бот пытается отбиться
        last_attack = next(((c, pid) for c, pid, role in reversed(game['table']) if role == 'attack'), None)
        if not last_attack:
            await take_cards(game, context, chat_id)
            return
        attack_card = last_attack[0]
        # Ищем минимальную карту, которой можно побить
        possible = []
        for i, card in enumerate(hand):
            if can_beat(attack_card, card, game['trump']):
                possible.append((i, card))
        if possible:
            possible.sort(key=lambda x: (CARD_VALUES[card_rank(x[1])], card_suit(x[1])))
            idx = possible[0][0]
            await defend_with_card(bot_id, idx, game, context, chat_id)
        else:
            await take_cards(game, context, chat_id)
    elif game['phase'] == 'throw':
        # Бот пытается подкинуть, если есть подходящая карта
        table_ranks = {card_rank(c) for c, pid, role in game['table']}
        possible = [(i, card) for i, card in enumerate(hand) if card_rank(card) in table_ranks]
        if possible:
            idx = possible[0][0]
            await throw_with_card(bot_id, idx, game, context, chat_id)
        else:
            # Отказываемся от подкидывания – жмём "Бито"
            await action_beaten(bot_id, game, context, chat_id)
    elif game['phase'] == 'transfer':
        # Бот может перевести, если есть карта того же достоинства
        if game['mode'] == 'transfer':
            first_attack = next((c for c, pid, role in game['table'] if role == 'attack'), None)
            if first_attack:
                rank = card_rank(first_attack[0])
                possible = [(i, card) for i, card in enumerate(hand) if card_rank(card) == rank]
                if possible:
                    idx = possible[0][0]
                    await transfer_with_card(bot_id, idx, game, context, chat_id)
                    return
        # Если не можем перевести – забираем
        await take_cards(game, context, chat_id)

# === Текстовые триггеры ===
async def text_durak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    text = message.text.lower()
    if 'подкидной' in text:
        mode = 'throw'
    elif 'переводной' in text:
        mode = 'transfer'
    else:
        mode = 'simple'
    bot_username = context.bot.username.lower()
    mentioned = f'@{bot_username}' in text
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        mentioned = True
    if mentioned or chat.type == 'private':
        await durak_start(update, context, mode)

def register_handlers(app):
    app.add_handler(CallbackQueryHandler(durak_lobby_button, pattern='^durak_(bet_|join|leave|start|play_vs_bot)'))
    app.add_handler(CallbackQueryHandler(durak_card_handler, pattern='^durak_(card_|action_)'))

import random
import asyncio
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from wallet import get_balance, add_balance

logger = logging.getLogger(__name__)

durak_games = {}
ACTIVATED_FILE = "activated.txt"

if os.path.exists(ACTIVATED_FILE):
    with open(ACTIVATED_FILE, 'r') as f:
        activated_users = set(line.strip() for line in f if line.strip())
else:
    activated_users = set()

def save_activated():
    with open(ACTIVATED_FILE, 'w') as f:
        for uid in activated_users:
            f.write(str(uid) + '\n')

def is_activated(user_id):
    return str(user_id) in activated_users

def activate_user(user_id):
    if str(user_id) not in activated_users:
        activated_users.add(str(user_id))
        save_activated()

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
        'vs_bot': False,
        'player_messages': {},
        'pending_transfer': None,
        'last_action': ''
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
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        if not is_activated(user.id):
            await query.answer('Сначала напишите боту в личные сообщения (откройте чат и нажмите /start).', show_alert=True)
            return
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
        bot_id = -1
        game['players'].append(bot_id)
        game['names'][bot_id] = 'Бот'
        game['bets'][bot_id] = 0
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
    game['player_messages'] = {}
    game['pending_transfer'] = None
    game['last_action'] = 'Игра началась!'

    for uid in game['players']:
        game['hands'][uid] = [game['deck'].pop() for _ in range(min(6, len(game['deck'])))]

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

    for uid in game['players']:
        if uid != -1:
            try:
                await send_or_update_game_message(uid, game, context)
            except Exception as e:
                logger.error(f"Ошибка отправки карт игроку {uid}: {e}")
                game['state'] = 'lobby'
                await context.bot.send_message(
                    chat_id,
                    f"Не удалось отправить карты игроку {game['names'][uid]}. Убедитесь, что он написал боту в личные сообщения. Игра отменена.",
                    message_thread_id=game['thread_id']
                )
                for pid in game['players']:
                    if pid != -1 and pid != uid:
                        add_balance(pid, game['bets'][pid])
                durak_games.pop(chat_id, None)
                return

    thread_id = game['thread_id']
    names = ', '.join(f'@{game["names"][uid]}' if uid != -1 else 'Бот' for uid in game['players'])
    attacker_id = game['turn_order'][game['attacker_index']]
    await context.bot.send_message(
        chat_id,
        f'🃏 Игра началась! Козырь: {game["trump"]}\nИгроки: {names}\n'
        f'Первый ход: {game["names"][attacker_id]}',
        message_thread_id=thread_id
    )

    if attacker_id == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, attacker_id, context, chat_id)

async def send_or_update_game_message(user_id, game, context):
    if user_id == -1:
        return

    if user_id in game.get('player_messages', {}):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=game['player_messages'][user_id])
        except:
            pass
        del game['player_messages'][user_id]

    hand = game['hands'].get(user_id, [])
    trump = game['trump']
    table = game['table']
    phase = game['phase']
    attacker_idx = game['attacker_index']
    defender_idx = game['defender_index']
    attacker_id = game['turn_order'][attacker_idx]
    defender_id = game['turn_order'][defender_idx]

    # Последнее действие
    last_action = game.get('last_action', '')

    if table:
        table_text = "Стол:\n"
        for card, pid, role in table:
            role_text = "ходит" if role == 'attack' else "бьёт"
            name = game['names'][pid]
            table_text += f"{name} {role_text}: {card}\n"
    else:
        table_text = "Стол пуст.\n"

    if phase == 'attack':
        if attacker_id == user_id:
            status = "Ваш ход. Выберите карту для хода."
        elif defender_id == user_id:
            status = "Ожидайте, пока соперник сделает ход."
        else:
            status = f"Ход {game['names'][attacker_id]}."
    elif phase == 'defend':
        if defender_id == user_id:
            status = "Ваш ход. Отбивайтесь или забирайте."
        else:
            status = f"Отбивается {game['names'][defender_id]}."
    elif phase == 'throw':
        if attacker_id == user_id:
            status = "Можно подкинуть карту того же достоинства или нажать «Бито»."
        else:
            status = f"Подкидывает {game['names'][attacker_id]}."
    elif phase == 'transfer':
        if defender_id == user_id:
            if game.get('pending_transfer') == user_id:
                status = "Выберите карту для перевода (того же достоинства, что и заходящая)."
            else:
                status = "Можно перевести (кнопка «Перевести»), отбиться или забрать."
        else:
            status = f"Переводит {game['names'][defender_id]}."
    else:
        status = "Ожидайте."

    keyboard = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(card, callback_data=f'durak_card_{i}'))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    action_row = []
    if phase == 'throw' and user_id == attacker_id:
        action_row.append(InlineKeyboardButton('Бито', callback_data='durak_action_beaten'))
    if phase == 'transfer' and user_id == defender_id and game.get('pending_transfer') != user_id:
        action_row.append(InlineKeyboardButton('Перевести', callback_data='durak_action_transfer'))
    action_row.append(InlineKeyboardButton('Забрать', callback_data='durak_action_take'))
    if action_row:
        keyboard.append(action_row)

    text = f"🃏 Козырь: {trump}\n\n"
    if last_action:
        text += f"📌 {last_action}\n\n"
    text += f"{table_text}\nВаша рука:\n{status}"

    msg = await context.bot.send_message(
        user_id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        protect_content=True
    )
    game['player_messages'][user_id] = msg.message_id

async def log_to_chat(chat_id, text, game, context):
    await context.bot.send_message(
        chat_id,
        text,
        message_thread_id=game['thread_id']
    )

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
        if game.get('pending_transfer') == user_id:
            await handle_transfer_card(user_id, idx, game, context, chat_id)
            return
        if game['phase'] == 'attack':
            await attack_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'defend':
            await defend_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'throw':
            await throw_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'transfer':
            await defend_with_card(user_id, idx, game, context, chat_id)
    elif data == 'durak_action_beaten':
        game['pending_transfer'] = None
        await action_beaten(user_id, game, context, chat_id)
    elif data == 'durak_action_take':
        game['pending_transfer'] = None
        await action_take(user_id, game, context, chat_id)
    elif data == 'durak_action_transfer':
        await action_transfer(user_id, game, context, chat_id)

async def handle_transfer_card(user_id, card_idx, game, context, chat_id):
    hand = game['hands'][user_id]
    card = hand[card_idx]
    first_attack = next((c for c, pid, role in game['table'] if role == 'attack'), None)
    if not first_attack or card_rank(card) != card_rank(first_attack[0]):
        await context.bot.send_message(user_id, 'Этой картой нельзя перевести. Выберите карту того же достоинства, что и заходящая.')
        return
    game['pending_transfer'] = None
    await transfer_with_card(user_id, card_idx, game, context, chat_id)

async def attack_with_card(user_id, card_idx, game, context, chat_id):
    game['pending_transfer'] = None
    hand = game['hands'][user_id]
    card = hand.pop(card_idx)
    game['table'].append((card, user_id, 'attack'))
    action_text = f"{game['names'][user_id]} ходит {card}"
    game['last_action'] = action_text
    await log_to_chat(chat_id, action_text, game, context)
    if game['mode'] == 'transfer':
        game['phase'] = 'transfer'
    else:
        game['phase'] = 'defend'
    await update_all_players(game, context)
    defender_id = game['turn_order'][game['defender_index']]
    if defender_id == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, defender_id, context, chat_id)

async def defend_with_card(user_id, card_idx, game, context, chat_id):
    game['pending_transfer'] = None
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
    action_text = f"{game['names'][user_id]} бьёт {card}"
    game['last_action'] = action_text
    await log_to_chat(chat_id, action_text, game, context)
    await update_all_players(game, context)

    attack_cards = [c for c, pid, role in game['table'] if role == 'attack']
    defend_cards = [c for c, pid, role in game['table'] if role == 'defend']
    if len(attack_cards) == len(defend_cards):
        if game['mode'] == 'throw':
            game['phase'] = 'throw'
            attacker_id = game['turn_order'][game['attacker_index']]
            if attacker_id == -1:
                await bot_turn(chat_id, context)
            else:
                await update_all_players(game, context)
                reset_timer(game, attacker_id, context, chat_id)
            await log_to_chat(chat_id, 'Можно подкинуть.', game, context)
        else:
            await end_turn(game, context, chat_id)
    else:
        defender_id = game['turn_order'][game['defender_index']]
        if defender_id == -1:
            await bot_turn(chat_id, context)
        else:
            reset_timer(game, defender_id, context, chat_id)

async def throw_with_card(user_id, card_idx, game, context, chat_id):
    game['pending_transfer'] = None
    if game['phase'] != 'throw':
        await context.bot.send_message(user_id, 'Сейчас нельзя подкидывать.')
        return
    attacker_id = game['turn_order'][game['attacker_index']]
    if user_id != attacker_id:
        await context.bot.send_message(user_id, 'Только заходящий может подкинуть.')
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
    action_text = f"{game['names'][user_id]} подкидывает {card}"
    game['last_action'] = action_text
    await log_to_chat(chat_id, action_text, game, context)
    game['phase'] = 'defend'
    await update_all_players(game, context)
    defender_id = game['turn_order'][game['defender_index']]
    if defender_id == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, defender_id, context, chat_id)

async def transfer_with_card(user_id, card_idx, game, context, chat_id):
    game['pending_transfer'] = None
    if game['mode'] != 'transfer' or game['phase'] != 'transfer':
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
    action_text = f"{game['names'][user_id]} переводит {card}"
    game['last_action'] = action_text
    await log_to_chat(chat_id, action_text, game, context)
    game['defender_index'] = (game['defender_index'] + 1) % len(game['players'])
    if game['defender_index'] == game['attacker_index']:
        game['phase'] = 'defend'
        defender_id = game['turn_order'][game['defender_index']]
        if defender_id == -1:
            await bot_turn(chat_id, context)
        else:
            await update_all_players(game, context)
            reset_timer(game, defender_id, context, chat_id)
    else:
        game['phase'] = 'transfer'
        next_defender = game['turn_order'][game['defender_index']]
        if next_defender == -1:
            await bot_turn(chat_id, context)
        else:
            await update_all_players(game, context)
            reset_timer(game, next_defender, context, chat_id)

async def action_beaten(user_id, game, context, chat_id):
    if game['phase'] == 'throw' and user_id == game['turn_order'][game['attacker_index']]:
        action_text = f"{game['names'][user_id]} говорит «Бито»."
        game['last_action'] = action_text
        await log_to_chat(chat_id, action_text, game, context)
        await end_turn(game, context, chat_id)
    else:
        await context.bot.send_message(user_id, 'Сейчас нельзя сказать "бито".')

async def action_take(user_id, game, context, chat_id):
    if user_id != game['turn_order'][game['defender_index']]:
        await context.bot.send_message(user_id, 'Только защищающийся может забрать.')
        return
    game['pending_transfer'] = None
    await take_cards(game, context, chat_id)

async def action_transfer(user_id, game, context, chat_id):
    if game['phase'] != 'transfer' or user_id != game['turn_order'][game['defender_index']]:
        await context.bot.send_message(user_id, 'Сейчас нельзя перевести.')
        return
    game['pending_transfer'] = user_id
    await send_or_update_game_message(user_id, game, context)
    await context.bot.send_message(user_id, 'Выберите карту для перевода (того же достоинства, что и заходящая).')

async def take_cards(game, context, chat_id):
    defender_id = game['turn_order'][game['defender_index']]
    cards = [c for c, pid, role in game['table']]
    game['hands'][defender_id].extend(cards)
    game['table'].clear()
    action_text = f"{game['names'][defender_id]} забирает карты."
    game['last_action'] = action_text
    await log_to_chat(chat_id, action_text, game, context)
    await end_turn(game, context, chat_id, skip_attacker_change=True)

async def end_turn(game, context, chat_id, skip_attacker_change=False):
    if game['turn_timer']:
        game['turn_timer'].cancel()
    game['pending_transfer'] = None
    for uid in game['players']:
        while len(game['hands'][uid]) < 6 and game['deck']:
            game['hands'][uid].append(game['deck'].pop())
    game['table'].clear()
    game['last_action'] = 'Раунд завершён.'

    for uid in game['players']:
        if not game['hands'][uid] and not game['deck']:
            winner = uid
            if winner == -1:
                await log_to_chat(chat_id, '🤖 Бот выиграл! Вы дурак.', game, context)
            else:
                total_bet = sum(game['bets'].values())
                add_balance(winner, total_bet * 2)
                await log_to_chat(chat_id, f'🏆 {game["names"][winner]} выиграл и забирает банк {total_bet * 2} фишек!', game, context)
            game['state'] = 'finished'
            durak_games.pop(chat_id, None)
            return

    if not skip_attacker_change:
        game['attacker_index'] = game['defender_index']
    else:
        game['attacker_index'] = (game['attacker_index']) % len(game['players'])
    game['defender_index'] = (game['attacker_index'] + 1) % len(game['players'])
    game['phase'] = 'attack'
    next_attacker = game['turn_order'][game['attacker_index']]
    game['last_action'] = f'Ход переходит к {game["names"][next_attacker]}.'
    await log_to_chat(chat_id, game['last_action'], game, context)
    await update_all_players(game, context)
    if next_attacker == -1:
        await bot_turn(chat_id, context)
    else:
        reset_timer(game, next_attacker, context, chat_id)

async def update_all_players(game, context):
    for uid in game['players']:
        if uid != -1:
            try:
                await send_or_update_game_message(uid, game, context)
            except Exception as e:
                logger.error(f"Ошибка обновления сообщения игроку {uid}: {e}")

def get_current_player_id(game):
    order = game['turn_order']
    if game['phase'] == 'attack':
        return order[game['attacker_index']]
    elif game['phase'] == 'defend':
        return order[game['defender_index']]
    elif game['phase'] == 'throw':
        return order[game['attacker_index']]
    elif game['phase'] == 'transfer':
        return order[game['defender_index']]
    return None

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
        game['pending_transfer'] = None
        await action_take(user_id, game, context, chat_id)

# === Логика бота ===
async def bot_turn(chat_id, context):
    game = durak_games[chat_id]
    if game['state'] != 'playing':
        return
    for uid in game['players']:
        if uid != -1:
            try:
                await send_or_update_game_message(uid, game, context)
            except:
                pass
    await asyncio.sleep(1.5)

    bot_id = -1
    hand = game['hands'][bot_id]

    if game['phase'] == 'attack':
        if not hand:
            return
        hand.sort(key=lambda c: (CARD_VALUES[card_rank(c)], card_suit(c)))
        card = hand[0]
        idx = 0
        await attack_with_card(bot_id, idx, game, context, chat_id)
    elif game['phase'] == 'defend':
        last_attack = next(((c, pid) for c, pid, role in reversed(game['table']) if role == 'attack'), None)
        if not last_attack:
            await take_cards(game, context, chat_id)
            return
        attack_card = last_attack[0]
        possible = [(i, card) for i, card in enumerate(hand) if can_beat(attack_card, card, game['trump'])]
        if possible:
            possible.sort(key=lambda x: (CARD_VALUES[card_rank(x[1])], card_suit(x[1])))
            idx = possible[0][0]
            await defend_with_card(bot_id, idx, game, context, chat_id)
        else:
            await take_cards(game, context, chat_id)
    elif game['phase'] == 'throw':
        table_ranks = {card_rank(c) for c, pid, role in game['table']}
        possible = [(i, card) for i, card in enumerate(hand) if card_rank(card) in table_ranks]
        if possible:
            idx = possible[0][0]
            await throw_with_card(bot_id, idx, game, context, chat_id)
        else:
            await action_beaten(bot_id, game, context, chat_id)
    elif game['phase'] == 'transfer':
        last_attack = next(((c, pid) for c, pid, role in reversed(game['table']) if role == 'attack'), None)
        if last_attack:
            attack_card = last_attack[0]
            rank = card_rank(attack_card)
            trans_candidates = [c for c in hand if card_rank(c) == rank]
            non_trump_trans = [c for c in trans_candidates if card_suit(c) != game['trump']]
            if non_trump_trans:
                chosen = non_trump_trans[0]
            elif trans_candidates:
                chosen = trans_candidates[0]
            else:
                chosen = None
            if chosen:
                idx = hand.index(chosen)
                await transfer_with_card(bot_id, idx, game, context, chat_id)
                return
            possible_def = [c for c in hand if can_beat(attack_card, c, game['trump'])]
            if possible_def:
                possible_def.sort(key=lambda c: (CARD_VALUES[card_rank(c)], card_suit(c)))
                idx = hand.index(possible_def[0])
                await defend_with_card(bot_id, idx, game, context, chat_id)
                return
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

async def reset_durak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username and update.effective_user.username.lower() == 'iamstarhead':
        chat_id = update.effective_chat.id
        if chat_id in durak_games:
            durak_games.pop(chat_id)
            await update.message.reply_text("Игра в дурака сброшена.")
        else:
            await update.message.reply_text("Нет активной игры в дурака.")
    else:
        await update.message.reply_text("Нет доступа.")

def register_handlers(app):
    app.add_handler(CallbackQueryHandler(durak_lobby_button, pattern='^durak_(bet_|join|leave|start|play_vs_bot)'))
    app.add_handler(CallbackQueryHandler(durak_card_handler, pattern='^durak_(card_|action_)'))
    app.add_handler(CommandHandler("reset_durak", reset_durak))

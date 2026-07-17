import random
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from wallet import get_balance, add_balance

logger = logging.getLogger(__name__)

# Хранилище игр: ключ — chat_id
durak_games = {}

# Колода 36 карт (6..Туз)
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {rank: i for i, rank in enumerate(RANKS)}  # для сравнения старшинства

def new_deck():
    deck = [r + s for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def card_rank(card):
    return card[:-1]

def card_suit(card):
    return card[-1]

def can_beat(attacking_card, defending_card, trump):
    """Может ли defending_card побить attacking_card с учётом козыря trump."""
    if card_suit(defending_card) == trump and card_suit(attacking_card) != trump:
        return True  # козырь бьёт некозырь
    if card_suit(defending_card) == card_suit(attacking_card):
        return CARD_VALUES[card_rank(defending_card)] > CARD_VALUES[card_rank(attacking_card)]
    return False

# === Лобби дурака ===
async def durak_start(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='throw'):
    """Создаёт лобби для дурака. mode: 'throw' (подкидной), 'transfer' (переводной), 'simple' (простой)."""
    chat = update.effective_chat
    if chat.id in durak_games and durak_games[chat.id]['state'] != 'finished':
        await context.bot.send_message(chat.id, 'Игра в дурака уже идёт. Дождитесь завершения.')
        return

    # Запоминаем тему
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    durak_games[chat.id] = {
        'players': [],
        'names': {},
        'bets': {},
        'state': 'lobby',
        'message_id': None,
        'thread_id': thread_id,
        'mode': mode,
        'bet_amount': 0
    }

    keyboard = [
        [InlineKeyboardButton('25 фишек', callback_data='durak_bet_25'),
         InlineKeyboardButton('50 фишек', callback_data='durak_bet_50'),
         InlineKeyboardButton('100 фишек', callback_data='durak_bet_100')],
        [InlineKeyboardButton('Сесть за стол', callback_data='durak_join'),
         InlineKeyboardButton('Выйти', callback_data='durak_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='durak_start')]
    ]
    mode_names = {'throw': 'Подкидной', 'transfer': 'Переводной', 'simple': 'Простой'}
    msg = await context.bot.send_message(
        chat.id,
        f'🃏 Дурак ({mode_names[mode]})\nВыберите ставку и нажмите «Сесть за стол» (2–4 игрока).\n'
        'Текущие игроки: —',
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id
    )
    durak_games[chat.id]['message_id'] = msg.message_id

# === Обработчик лобби ===
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
    thread_id = game['thread_id']

    if data.startswith('durak_bet_'):
        bet = int(data.split('_')[2])
        game['bet_amount'] = bet
        await query.answer(f'Ставка: {bet} фишек.')
        # Обновим сообщение, чтобы показать выбранную ставку
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
        # Списываем ставку
        add_balance(user.id, -game['bet_amount'])
        game['players'].append(user.id)
        game['names'][user.id] = user.first_name
        game['bets'][user.id] = game['bet_amount']
    elif data == 'durak_leave':
        if user.id in game['players']:
            # Возвращаем ставку
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

    await update_lobby_message(chat_id, context)

async def update_lobby_message(chat_id, context):
    game = durak_games[chat_id]
    mode_names = {'throw': 'Подкидной', 'transfer': 'Переводной', 'simple': 'Простой'}
    bet_text = f'Ставка: {game["bet_amount"]} фишек' if game['bet_amount'] > 0 else 'Ставка не выбрана'
    names_parts = [f'@{game["names"][uid]} ({get_balance(uid)} фишек)' for uid in game['players']]
    names = ', '.join(names_parts) if names_parts else '—'
    keyboard = [
        [InlineKeyboardButton('25 фишек', callback_data='durak_bet_25'),
         InlineKeyboardButton('50 фишек', callback_data='durak_bet_50'),
         InlineKeyboardButton('100 фишек', callback_data='durak_bet_100')],
        [InlineKeyboardButton('Сесть за стол', callback_data='durak_join'),
         InlineKeyboardButton('Выйти', callback_data='durak_leave')],
        [InlineKeyboardButton('Начать игру', callback_data='durak_start')]
    ]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game['message_id'],
        text=f'🃏 Дурак ({mode_names[game["mode"]]})\n{bet_text}\nТекущие игроки: {names}',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === Игровой процесс ===
async def start_durak_game(chat_id, context):
    game = durak_games[chat_id]
    game['state'] = 'playing'
    game['deck'] = new_deck()
    game['trump'] = random.choice(SUITS)
    game['hands'] = {}
    game['table'] = []           # список карт на столе: (card, player_id, role) role: 'attack'/'defend'
    game['turn_order'] = game['players'][:]  # порядок хода по часовой стрелке
    game['attacker_index'] = 0
    game['defender_index'] = 1 % len(game['players'])
    game['phase'] = 'attack'     # attack / defend / throw / transfer / end
    game['pass_count'] = 0
    game['turn_timer'] = None

    # Раздача по 6 карт
    for uid in game['players']:
        game['hands'][uid] = [game['deck'].pop() for _ in range(min(6, len(game['deck'])))]

    # Определяем первого заходящего по младшему козырю (или рандомно в простом)
    if game['mode'] in ('throw', 'transfer'):
        # Ищем игрока с младшим козырем
        min_rank = len(RANKS)
        first = game['players'][0]
        for uid in game['players']:
            for card in game['hands'][uid]:
                if card_suit(card) == game['trump']:
                    r = CARD_VALUES[card_rank(card)]
                    if r < min_rank:
                        min_rank = r
                        first = uid
        # Устанавливаем очерёдность начиная с него
        idx = game['players'].index(first)
        game['turn_order'] = game['players'][idx:] + game['players'][:idx]
        game['attacker_index'] = 0
        game['defender_index'] = 1 % len(game['players'])
    else:
        # Простой: случайный первый ход
        random.shuffle(game['turn_order'])
        game['attacker_index'] = 0
        game['defender_index'] = 1 % len(game['players'])

    # Отправляем карты игрокам в личку
    for uid in game['players']:
        await send_hand_message(uid, game, context)

    # Сообщение в общий чат
    thread_id = game['thread_id']
    names = ', '.join(f'@{game["names"][uid]}' for uid in game['players'])
    attacker_id = game['turn_order'][game['attacker_index']]
    await context.bot.send_message(
        chat_id,
        f'♠️ Игра началась! Козырь: {game["trump"]}\n'
        f'Игроки: {names}\n'
        f'Первый ход: @{game["names"][attacker_id]}\n'
        'Всем игрокам отправлены карты в личные сообщения.',
        message_thread_id=thread_id
    )
    # Запускаем таймер и предлагаем ход заходящему
    await send_turn_prompt(attacker_id, game, context)

async def send_hand_message(user_id, game, context):
    """Отправляет или обновляет личное сообщение с рукой в виде кнопок."""
    hand = game['hands'].get(user_id, [])
    keyboard = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(card, callback_data=f'durak_card_{i}'))
        if len(row) == 4:  # по 4 кнопки в ряд
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Добавляем служебные кнопки в зависимости от фазы
    # Они будут видны, но активны только когда нужно.
    # Мы будем управлять этим через редактирование сообщения и callback-обработчик проверяет статус.
    # Поэтому просто добавим их сейчас, но действие проверим в обработчике.
    keyboard.append([
        InlineKeyboardButton('Бито', callback_data='durak_action_beaten'),
        InlineKeyboardButton('Забрать', callback_data='durak_action_take'),
        InlineKeyboardButton('Перевести', callback_data='durak_action_transfer')
    ])

    text = f'Ваша рука:\nКозырь: {game["trump"]}'
    if 'hand_message_id' in game and user_id in game.get('hand_message_ids', {}):
        # Пытаемся редактировать существующее сообщение
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
    # Иначе отправляем новое
    msg = await context.bot.send_message(
        user_id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        protect_content=True
    )
    if 'hand_message_ids' not in game:
        game['hand_message_ids'] = {}
    game['hand_message_ids'][user_id] = msg.message_id

async def send_turn_prompt(user_id, game, context):
    """Отправляет в личку приглашение сделать ход (текстом), но основные действия через кнопки карт."""
    # Фактически, игрок уже видит свои карты и кнопки. Просто напомним текстом, если нужно.
    # Можно не отправлять отдельное сообщение, а обновить руку с подсказкой.
    # Уже обновляется через send_hand_message.
    pass

# === Основной обработчик колбэков из личных сообщений (карты и действия) ===
async def durak_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Ищем игру по всем chat_id (неудобно, но можно хранить обратный маппинг user->chat_id)
    # Упростим: в момент старта игры запомним chat_id для каждого игрока
    # В game добавим 'chat_id'
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

    # Обрабатываем нажатие на карту или действие
    if data.startswith('durak_card_'):
        idx = int(data.split('_')[2])
        hand = game['hands'][user_id]
        if idx >= len(hand):
            await query.answer('Неверная карта.')
            return
        card = hand[idx]
        # Проверяем, может ли игрок действовать в текущей фазе
        if user_id != get_current_player_id(game):
            await query.answer('Сейчас не ваш ход.', show_alert=False)
            return
        # Обработка в зависимости от фазы
        if game['phase'] == 'attack':
            # Заходящий делает первый заход
            # Проверяем, что карту можно положить (пока без ограничений)
            await attack_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'defend':
            # Отбивающийся бьёт карту
            await defend_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'throw':
            # Подкидывание
            await throw_with_card(user_id, idx, game, context, chat_id)
        elif game['phase'] == 'transfer':
            # Перевод
            await transfer_with_card(user_id, idx, game, context, chat_id)
    elif data == 'durak_action_beaten':
        await action_beaten(user_id, game, context, chat_id)
    elif data == 'durak_action_take':
        await action_take(user_id, game, context, chat_id)
    elif data == 'durak_action_transfer':
        await action_transfer(user_id, game, context, chat_id)

def get_current_player_id(game):
    """Возвращает user_id игрока, который должен ходить сейчас."""
    order = game['turn_order']
    if game['phase'] in ('attack', 'throw'):
        # Ход заходящего (или подкидывающих по очереди)
        return order[game['attacker_index']]
    elif game['phase'] in ('defend', 'transfer'):
        return order[game['defender_index']]
    return None

async def attack_with_card(user_id, card_idx, game, context, chat_id):
    hand = game['hands'][user_id]
    card = hand.pop(card_idx)
    game['table'].append((card, user_id, 'attack'))
    # Передаём ход отбивающемуся
    game['phase'] = 'defend'
    # Обновляем руку
    await send_hand_message(user_id, game, context)
    # Сообщение в общий чат
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} заходит {card}',
        message_thread_id=game['thread_id']
    )
    # Предлагаем отбивающемуся действие
    defender_id = game['turn_order'][game['defender_index']]
    await send_hand_message(defender_id, game, context)
    # Запускаем таймер
    reset_timer(game, defender_id, context, chat_id)

async def defend_with_card(user_id, card_idx, game, context, chat_id):
    hand = game['hands'][user_id]
    card = hand[card_idx]
    # Последняя атакующая карта на столе
    last_attack = next(((c, pid) for c, pid, role in reversed(game['table']) if role == 'attack'), None)
    if not last_attack:
        await context.bot.send_message(user_id, 'Нечего бить.')
        return
    attack_card = last_attack[0]
    if not can_beat(attack_card, card, game['trump']):
        await query.answer('Эта карта не бьёт.', show_alert=False)
        return
    # Бьём
    hand.remove(card)
    game['table'].append((card, user_id, 'defend'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} бьёт {card}',
        message_thread_id=game['thread_id']
    )
    # Проверяем, есть ли ещё непобитые атакующие карты
    attack_cards = [c for c, pid, role in game['table'] if role == 'attack']
    defend_cards = [c for c, pid, role in game['table'] if role == 'defend']
    if len(attack_cards) == len(defend_cards):
        # Все побиты, можно подкидывать (если режим подкидной)
        if game['mode'] == 'throw' and len(game['players']) > 2:
            game['phase'] = 'throw'
            game['throw_order'] = (game['attacker_index'] + 1) % len(game['players'])
            # Ищем первого подкидывающего после заходящего
            next_thrower = game['turn_order'][game['throw_order']]
            await send_hand_message(next_thrower, game, context)
            await context.bot.send_message(chat_id, 'Можно подкинуть.', message_thread_id=game['thread_id'])
        else:
            # В простом и переводном (без подкидывания) или если игроков 2 — заканчиваем раунд
            await end_turn(game, context, chat_id)
    else:
        # Ещё есть непобитые — защищающийся должен бить дальше
        await send_hand_message(user_id, game, context)

async def throw_with_card(user_id, card_idx, game, context, chat_id):
    # Проверяем, что сейчас фаза подкидывания и пользователь имеет право
    if game['phase'] != 'throw':
        await query.answer('Сейчас нельзя подкидывать.')
        return
    # Игрок должен быть в порядке подкидывания
    # Пока разрешим подкидывать любому, кроме отбивающегося, но соблюдаем очерёдность
    # Упростим: подкидывает следующий по кругу после заходящего, пропуская тех, кто уже сказал "бито"
    throw_order = game.get('throw_order', (game['attacker_index'] + 1) % len(game['players']))
    expected_id = game['turn_order'][throw_order]
    if user_id != expected_id:
        await query.answer('Сейчас не ваша очередь подкидывать.')
        return
    hand = game['hands'][user_id]
    card = hand[card_idx]
    rank = card_rank(card)
    # Проверяем, что есть карты такого достоинства на столе
    table_ranks = {card_rank(c) for c, pid, role in game['table']}
    if rank not in table_ranks:
        await query.answer('Можно подкидывать только карты того же достоинства, что на столе.')
        return
    # Подкидываем
    hand.remove(card)
    game['table'].append((card, user_id, 'attack'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} подкидывает {card}',
        message_thread_id=game['thread_id']
    )
    # Теперь снова фаза защиты
    game['phase'] = 'defend'
    defender_id = game['turn_order'][game['defender_index']]
    await send_hand_message(defender_id, game, context)
    reset_timer(game, defender_id, context, chat_id)

async def transfer_with_card(user_id, card_idx, game, context, chat_id):
    if game['mode'] != 'transfer':
        await query.answer('Перевод доступен только в переводном дураке.')
        return
    if game['phase'] != 'transfer':
        await query.answer('Сейчас нельзя перевести.')
        return
    if user_id != game['turn_order'][game['defender_index']]:
        await query.answer('Перевести может только отбивающийся.')
        return
    hand = game['hands'][user_id]
    card = hand[card_idx]
    # Проверяем, что карта того же достоинства, что и заходящая
    first_attack = next((c for c, pid, role in game['table'] if role == 'attack'), None)
    if not first_attack or card_rank(card) != card_rank(first_attack[0]):
        await query.answer('Перевести можно только картой того же достоинства.')
        return
    # Переводим: удаляем карту, добавляем на стол как атакующую, смещаем защитника
    hand.remove(card)
    game['table'].append((card, user_id, 'attack'))
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} переводит {card}',
        message_thread_id=game['thread_id']
    )
    # Смещаем защитника на следующего
    game['defender_index'] = (game['defender_index'] + 1) % len(game['players'])
    # Если перевели обратно на того, кто уже был заходящим (круг замкнулся), то отбивается этот игрок
    if game['defender_index'] == game['attacker_index']:
        # Защитник становится заходящим (он не может перевести обратно)
        game['phase'] = 'defend'
        defender_id = game['turn_order'][game['defender_index']]
        await send_hand_message(defender_id, game, context)
        await context.bot.send_message(chat_id, 'Перевод вернулся. Отбивайтесь или забирайте.')
        reset_timer(game, defender_id, context, chat_id)
    else:
        # Иначе новый защитник может отбиваться или переводить дальше
        game['phase'] = 'transfer'
        next_defender = game['turn_order'][game['defender_index']]
        await send_hand_message(next_defender, game, context)
        await context.bot.send_message(chat_id, f'Ход переведён на @{game["names"][next_defender]}.')
        reset_timer(game, next_defender, context, chat_id)

async def action_beaten(user_id, game, context, chat_id):
    # Кнопка "Бито" (больше не подкидываем)
    if game['phase'] == 'throw' and user_id == get_current_player_id(game):
        # Перемещаем указатель подкидывания на следующего, и если все отказались — завершаем
        game['throw_order'] = (game['throw_order'] + 1) % len(game['players'])
        if game['throw_order'] == game['attacker_index']:
            # Все подкидывающие сказали "бито"
            await end_turn(game, context, chat_id)
        else:
            next_thrower = game['turn_order'][game['throw_order']]
            await send_hand_message(next_thrower, game, context)
    elif game['phase'] in ('defend', 'transfer') and user_id == game['turn_order'][game['defender_index']]:
        # В фазе защиты "Бито" неактуально, но может означать "Забрать"? Нет, есть отдельная кнопка.
        await query.answer('Сейчас нельзя сказать "бито".')

async def action_take(user_id, game, context, chat_id):
    # Забрать карты
    if user_id != game['turn_order'][game['defender_index']]:
        await query.answer('Только защищающийся может забрать.')
        return
    # Забираем все карты со стола в руку защищающегося
    cards = [c for c, pid, role in game['table']]
    game['hands'][user_id].extend(cards)
    game['table'].clear()
    await send_hand_message(user_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'@{game["names"][user_id]} забирает карты.',
        message_thread_id=game['thread_id']
    )
    # Пропуск хода: заходящий не меняется, но добираем карты и начинает тот же заходящий
    await end_turn(game, context, chat_id, skip_attacker_change=True)

async def end_turn(game, context, chat_id, skip_attacker_change=False):
    # Убираем таймер
    if game['turn_timer']:
        game['turn_timer'].cancel()
    # Добираем карты до 6 из колоды
    for uid in game['players']:
        while len(game['hands'][uid]) < 6 and game['deck']:
            game['hands'][uid].append(game['deck'].pop())
        await send_hand_message(uid, game, context)
    # Очищаем стол
    game['table'].clear()
    # Проверяем условие победы
    for uid in game['players']:
        if not game['hands'][uid] and not game['deck']:
            # Победитель!
            winner = uid
            total_bet = sum(game['bets'].values())
            add_balance(winner, total_bet)
            await context.bot.send_message(
                chat_id,
                f'🏆 @{game["names"][winner]} выиграл и забирает банк {total_bet} фишек!',
                message_thread_id=game['thread_id']
            )
            game['state'] = 'finished'
            # Удаляем игру
            durak_games.pop(chat_id, None)
            return
    # Переход хода
    if not skip_attacker_change:
        # Следующий заходящий — текущий защитник (если он не забрал) или через одного
        if game['phase'] != 'attack': # если был отбой и бито
            game['attacker_index'] = game['defender_index']
        else:
            # Если защитник забрал, заходящий не меняется
            pass
    else:
        # При забирании заходящий остаётся прежним
        game['attacker_index'] = (game['attacker_index']) % len(game['players'])
    game['defender_index'] = (game['attacker_index'] + 1) % len(game['players'])
    # Сбрасываем фазу на атаку
    game['phase'] = 'attack'
    attacker_id = game['turn_order'][game['attacker_index']]
    await send_hand_message(attacker_id, game, context)
    await context.bot.send_message(
        chat_id,
        f'Ход переходит к @{game["names"][attacker_id]}.',
        message_thread_id=game['thread_id']
    )
    reset_timer(game, attacker_id, context, chat_id)

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
        # Автозабор карт
        await action_take(user_id, game, context, chat_id)

# === Текстовые триггеры ===
async def text_durak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    text = message.text.lower()
    # Определяем режим
    if 'подкидной' in text:
        mode = 'throw'
    elif 'переводной' in text:
        mode = 'transfer'
    else:
        mode = 'simple'  # или можно спросить потом, но для простоты пусть будет простой
    # Проверка обращения (reply или @)
    bot_username = context.bot.username.lower()
    mentioned = f'@{bot_username}' in text
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        mentioned = True
    if mentioned or chat.type == 'private':
        await durak_start(update, context, mode)

# === Регистрация обработчиков ===
def register_handlers(app):
    app.add_handler(CallbackQueryHandler(durak_lobby_button, pattern='^durak_(bet_|join|leave|start)'))
    app.add_handler(CallbackQueryHandler(durak_card_handler, pattern='^durak_(card_|action_)'))

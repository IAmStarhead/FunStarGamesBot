# queue_manager.py
from collections import deque
import logging

logger = logging.getLogger(__name__)

# Структура: { chat_id: deque([ {'game': 'дурак', 'mode': 'throw', 'bet': 25, 'players': [user_id, ...]}, ... ]) }
game_queues = {}

MAX_QUEUE = 5

def add_to_queue(chat_id, game_type, mode=None, bet=None, player_id=None):
    """Добавляет игру в очередь. player_id — кто инициировал (пока сохраняем как единственного игрока)."""
    if chat_id not in game_queues:
        game_queues[chat_id] = deque()

    if len(game_queues[chat_id]) >= MAX_QUEUE:
        return False, "Очередь переполнена (максимум 5 игр)."

    # Ищем, есть ли уже ожидающая игра такого же типа – если да, добавляем игрока
    for entry in game_queues[chat_id]:
        if entry['game'] == game_type and entry['mode'] == mode and entry['bet'] == bet:
            if player_id not in entry['players']:
                entry['players'].append(player_id)
            return True, f"Вы добавлены в очередь на {game_type}. Позиция: {list(game_queues[chat_id]).index(entry)+1}"

    # Иначе создаём новую запись
    entry = {
        'game': game_type,
        'mode': mode,
        'bet': bet,
        'players': [player_id] if player_id else []
    }
    game_queues[chat_id].append(entry)
    return True, f"Игра {game_type} добавлена в очередь. Всего игр в очереди: {len(game_queues[chat_id])}"

def get_queue(chat_id):
    """Возвращает список очереди для отображения."""
    if chat_id not in game_queues:
        return "Очередь пуста."
    lines = []
    for i, entry in enumerate(game_queues[chat_id], 1):
        players = ', '.join(str(p) for p in entry['players']) or 'нет игроков'
        mode_str = f" ({entry['mode']})" if entry.get('mode') else ""
        bet_str = f" ставка {entry['bet']}" if entry.get('bet') else ""
        lines.append(f"{i}. {entry['game']}{mode_str}{bet_str}: {players}")
    return '\n'.join(lines) if lines else "Очередь пуста."

def pop_next_game(chat_id):
    """Извлекает первый элемент очереди и возвращает его. Если очередь пуста, возвращает None."""
    if chat_id not in game_queues or not game_queues[chat_id]:
        return None
    return game_queues[chat_id].popleft()

def remove_player(chat_id, game_type, player_id):
    """Удаляет игрока из очереди (если передумал)."""
    if chat_id not in game_queues:
        return
    for entry in game_queues[chat_id]:
        if entry['game'] == game_type and player_id in entry['players']:
            entry['players'].remove(player_id)
            if not entry['players']:
                game_queues[chat_id].remove(entry)
            return True
    return False

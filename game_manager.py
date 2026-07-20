# game_manager.py
from handlers import durak, blackjack

def get_active_game(chat_id):
    """Возвращает название активной игры в чате или None."""
    if chat_id in durak.durak_games and durak.durak_games[chat_id].get('state') != 'finished':
        return 'Дурак'
    if chat_id in blackjack.games and blackjack.games[chat_id].get('state') != 'finished':
        return 'Блэкджек'
    return None

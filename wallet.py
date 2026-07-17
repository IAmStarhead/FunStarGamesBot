import json
import os
import logging

logger = logging.getLogger(__name__)

BALANCE_FILE = "balances.json"
START_BALANCE = 100

# Загружаем данные из файла при старте
if os.path.exists(BALANCE_FILE):
    with open(BALANCE_FILE, 'r', encoding='utf-8') as f:
        _data = json.load(f)
else:
    _data = {}

# _data имеет структуру: { "user_id": {"balance": int, "username": str}, ... }

def _save():
    with open(BALANCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(_data, f, ensure_ascii=False, indent=2)

def _ensure_user(user_id, username=None):
    key = str(user_id)
    if key not in _data:
        _data[key] = {"balance": START_BALANCE, "username": username}
        _save()
    elif username and _data[key].get("username") != username:
        _data[key]["username"] = username
        _save()

def get_balance(user_id):
    key = str(user_id)
    return _data.get(key, {}).get("balance", START_BALANCE)

def set_balance(user_id, amount):
    key = str(user_id)
    if key not in _data:
        _data[key] = {"balance": amount, "username": None}
    else:
        _data[key]["balance"] = amount
    _save()

def add_balance(user_id, amount):
    new_bal = get_balance(user_id) + amount
    set_balance(user_id, new_bal)

def transfer(from_id, to_id, amount):
    if get_balance(from_id) < amount:
        return False
    add_balance(from_id, -amount)
    add_balance(to_id, amount)
    return True

def get_user_id_by_username(username):
    # Ищем username в данных (без @)
    clean = username.lstrip('@')
    for uid, info in _data.items():
        if info.get("username") == clean:
            return int(uid)
    return None

def update_username(user_id, username):
    key = str(user_id)
    if key in _data:
        _data[key]["username"] = username
        _save()
    else:
        _ensure_user(user_id, username)

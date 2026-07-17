import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_FILE = "balances.db"
START_BALANCE = 1000

# Инициализация базы данных
def _get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 1000,
            username TEXT
        )
    """)
    # Миграция из старого JSON (если есть и БД пуста)
    if os.path.exists("balances.json"):
        cur = conn.execute("SELECT COUNT(*) FROM balances")
        if cur.fetchone()[0] == 0:
            import json
            with open("balances.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for uid, info in old_data.items():
                conn.execute(
                    "INSERT OR REPLACE INTO balances (user_id, balance, username) VALUES (?, ?, ?)",
                    (int(uid), info.get("balance", START_BALANCE), info.get("username"))
                )
            conn.commit()
            logger.info("Перенесены данные из balances.json в SQLite")
    conn.close()

_init_db()

def get_balance(user_id):
    conn = _get_conn()
    row = conn.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return row["balance"]
    else:
        # Авто-создание записи со стартовым балансом
        conn.execute("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, START_BALANCE))
        conn.commit()
        return START_BALANCE

def set_balance(user_id, amount):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO balances (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance",
        (user_id, amount)
    )
    conn.commit()

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
    conn = _get_conn()
    clean = username.lstrip('@')
    row = conn.execute("SELECT user_id FROM balances WHERE username = ?", (clean,)).fetchone()
    if row:
        return row["user_id"]
    return None

def update_username(user_id, username):
    if username is None:
        return
    conn = _get_conn()
    conn.execute(
        "INSERT INTO balances (user_id, balance, username) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET username = excluded.username",
        (user_id, START_BALANCE, username)
    )
    conn.commit()

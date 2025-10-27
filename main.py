# bot.py
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import os
from dotenv import load_dotenv
import json  # Можно оставить для fallback, но не обязательно
import psycopg2  # Новая библиотека для Postgres
from psycopg2.extras import RealDictCursor  # Для удобного чтения как dict
from questions import questions

# Загружаем переменные из .env файла
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')  # Connection string от Render
if not TOKEN:
    raise ValueError('BOT_TOKEN не найден в .env файле!')
if not DATABASE_URL:
    raise ValueError('DATABASE_URL не найден в .env файле!')

bot = telebot.TeleBot(TOKEN)

# Глобальная переменная для кэша leaderboard (обновляется при изменениях)
leaderboard_cache = {}

# Функция подключения к БД
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# Инициализация таблицы leaderboard (вызывается при запуске)
def init_leaderboard_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            user_id VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            score INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("Таблица leaderboard инициализирована.")

# Загрузка leaderboard из БД (с кэшированием)
def load_leaderboard():
    global leaderboard_cache
    if leaderboard_cache:
        return leaderboard_cache
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM leaderboard ORDER BY score DESC")
    rows = cursor.fetchall()
    leaderboard_cache = {row['user_id']: dict(row) for row in rows}
    cursor.close()
    conn.close()
    return leaderboard_cache

# Сохранение/обновление записи в leaderboard
def save_leaderboard_entry(user_id, username, score):
    global leaderboard_cache
    conn = get_db_connection()
    cursor = conn.cursor()
    # Вставляем или обновляем (UPSERT)
    cursor.execute("""
        INSERT INTO leaderboard (user_id, username, score)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            username = EXCLUDED.username,
            score = GREATEST(leaderboard.score, EXCLUDED.score)
    """, (user_id, username, score))
    conn.commit()
    cursor.close()
    conn.close()
    # Обновляем кэш
    leaderboard_cache[user_id] = {'user_id': user_id, 'username': username, 'score': max(leaderboard_cache.get(user_id, {}).get('score', 0), score)}
    print(f"Обновлён лидерборд для {username}: {score}")

# Остальной код без изменений...
# (user_states, @bot.message_handler(commands=['start']), @bot.callback_query_handler, send_question, format_leaderboard)

# В send_question, в конце квиза, замените save_leaderboard на:
# username = bot.get_chat(user_id).username or f"User_{user_id}"
# score = state['score']
# save_leaderboard_entry(str(user_id), username, score)  # Вместо старого leaderboard[str(user_id)] = ...

# В format_leaderboard используйте load_leaderboard():
def format_leaderboard():
    lb = load_leaderboard()  # Загружаем из БД
    if not lb:
        return 'Турнирная таблица пуста. Пройди квиз, чтобы попасть в рейтинг!'
    sorted_lb = sorted(lb.items(), key=lambda x: x[1]['score'], reverse=True)[:10]
    result = '🏆 Турнирная таблица (Топ-10):\n'
    for i, (user_id, data) in enumerate(sorted_lb, 1):
        result += f"{i}. {data['username']} — {data['score']} баллов\n"
    return result

# Инициализация при запуске
if __name__ == '__main__':
    init_leaderboard_table()  # Создаём таблицу
    load_leaderboard()  # Загружаем в кэш
    bot.polling()
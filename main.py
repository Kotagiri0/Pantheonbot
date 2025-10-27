import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from questions import questions
import requests
import time

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not TOKEN:
    raise ValueError('BOT_TOKEN не найден в .env файле!')
if not DATABASE_URL:
    raise ValueError('DATABASE_URL не найден в .env файле!')

bot = telebot.TeleBot(TOKEN)
leaderboard_cache = {}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

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

def save_leaderboard_entry(user_id, username, score):
    global leaderboard_cache
    conn = get_db_connection()
    cursor = conn.cursor()
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
    leaderboard_cache[user_id] = {
        'user_id': user_id,
        'username': username,
        'score': max(leaderboard_cache.get(user_id, {}).get('score', 0), score)
    }
    print(f"Обновлён лидерборд для {username}: {score}")

def format_leaderboard():
    lb = load_leaderboard()
    if not lb:
        return 'Турнирная таблица пуста. Пройди квиз, чтобы попасть в рейтинг!'
    sorted_lb = sorted(lb.items(), key=lambda x: x[1]['score'], reverse=True)[:10]
    result = '🏆 Турнирная таблица (Топ-10):\n'
    for i, (user_id, data) in enumerate(sorted_lb, 1):
        result += f"{i}. {data['username']} — {data['score']} баллов\n"
    return result

# --- Фейковый HTTP сервер, чтобы Render видел порт ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"Fake HTTP server запущен на порту {port}")
    server.serve_forever()

# --- Безопасный запуск polling ---
def start_polling():
    """Отключает webhook и запускает polling с авто-повтором."""
    try:
        print("Удаляем старый webhook (если есть)...")
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        print("Webhook удалён, запускаем polling...")
    except Exception as e:
        print(f"Ошибка при удалении webhook: {e}")

    while True:
        try:
            bot.polling(non_stop=True)
        except telebot.apihelper.ApiTelegramException as e:
            if "Conflict" in str(e):
                print("⚠️ Conflict detected: удаляем webhook и перезапускаем polling...")
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
                time.sleep(5)
            else:
                print(f"❌ Ошибка polling: {e}")
                time.sleep(10)
        except Exception as e:
            print(f"❌ Неизвестная ошибка polling: {e}")
            time.sleep(10)

# --- Точка входа ---
if __name__ == '__main__':
    init_leaderboard_table()
    load_leaderboard()
    threading.Thread(target=run_dummy_server, daemon=True).start()
    start_polling()

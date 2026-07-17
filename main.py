import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler

async def start(update: Update, context):
    await update.message.reply_text('FunStarGames работает!')

def run_bot():
    token = os.environ['BOT_TOKEN']
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    print('Бот запущен...')
    app.run_polling()

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "OK"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    web_app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_web).start()
    run_bot()

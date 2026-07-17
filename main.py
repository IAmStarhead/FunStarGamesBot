import os
from telegram import Update
from telegram.ext import Application, CommandHandler

async def start(update: Update, context):
    await update.message.reply_text('FunStarGames работает!')

def main():
    token = os.environ['BOT_TOKEN']
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.run_polling()

if __name__ == '__main__':
    main()

import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context):
    user = update.effective_user.first_name
    await update.message.reply_text(f'Привет, {user}! FunStarGames работает 🎲')
    logger.info(f'Пользователь {user} запустил бота')

async def handle(request):
    return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    port = int(os.environ.get('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f'Веб-сервер запущен на порту {port}')

async def main():
    token = os.environ['BOT_TOKEN']
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler('start', start))

    # Веб-сервер для обхода сна Render
    asyncio.create_task(run_web_server())

    # Запуск поллинга (основной цикл бота)
    logger.info('Запускаю поллинг...')
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())

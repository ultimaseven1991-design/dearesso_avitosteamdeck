import os
import logging
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import WebhookInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 10000))
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", f"https://localhost:{PORT}")
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Flask приложение (только для health check)
app = Flask(__name__)

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_name = message.from_user.first_name
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        f"🤖 Я бот для поиска объявлений на Avito\n"
        f"📱 Помогаю находить Steam Deck и другие товары\n\n"
        f"🔍 Используй команду /help чтобы узнать что я умею"
    )
    await message.reply(welcome_text)

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    help_text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start - Запустить бота\n"
        "/help - Показать это сообщение\n"
        "/search - Начать поиск объявлений\n"
        "/settings - Настройки поиска\n\n"
        "💡 <b>Совет:</b> Просто отправь мне название товара, "
        "и я начну поиск на Avito!"
    )
    await message.reply(help_text)

@dp.message_handler(commands=['search'])
async def cmd_search(message: types.Message):
    """Обработчик команды /search"""
    await message.reply(
        "🔍 <b>Что ищем?</b>\n\n"
        "Отправьте мне название товара, например:\n"
        "• Steam Deck\n"
        "• Nintendo Switch\n"
        "• PlayStation 5\n\n"
        "И я найду актуальные объявления!"
    )

@dp.message_handler(commands=['settings'])
async def cmd_settings(message: types.Message):
    """Обработчик команды /settings"""
    await message.reply(
        "⚙️ <b>Настройки</b>\n\n"
        "Сейчас доступны:\n"
        "• Город: вся Россия\n"
        "• Цена: любая\n"
        "• Сортировка: по дате\n\n"
        "Скоро появятся дополнительные настройки!"
    )

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    """Обработчик текстовых сообщений (поиск по ключевым словам)"""
    search_query = message.text.strip()
    
    if len(search_query) < 3:
        await message.reply(
            "❌ Слишком короткий запрос!\n"
            "Введите минимум 3 символа для поиска."
        )
        return
    
    # Отправляем индикатор набора текста
    await bot.send_chat_action(message.chat.id, 'typing')
    
    # Здесь будет логика поиска на Avito
    await message.reply(
        f"🔍 <b>Ищу: {search_query}</b>\n\n"
        f"⏳ Поиск на Avito...\n\n"
        f"✨ <i>Скоро здесь появятся результаты!</i>"
    )

# ============= FLASK ЭНДПОИНТЫ =============

@app.route('/', methods=['GET'])
def index():
    """Проверка, что бот работает"""
    return jsonify({
        "status": "ok",
        "message": "Telegram bot is running",
        "webhook_url": WEBHOOK_URL
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check для Render"""
    return jsonify({"status": "healthy"}), 200

# ============= ЗАПУСК С AIOHTTP =============

async def on_startup():
    """Установка webhook при запуске"""
    try:
        await bot.delete_webhook()
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])
        logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

async def on_shutdown():
    """Остановка бота"""
    logger.info("🛑 Останавливаем бота...")
    await bot.delete_webhook()
    await bot.session.close()

def run_aiohttp_app():
    """Запуск aiohttp сервера для webhook"""
    # Создаем aiohttp приложение
    aiohttp_app = web.Application()
    
    # Настраиваем webhook обработчик
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(aiohttp_app, path=WEBHOOK_PATH)
    
    # Настраиваем startup/shutdown
    aiohttp_app.on_startup.append(lambda app: on_startup())
    aiohttp_app.on_shutdown.append(lambda app: on_shutdown())
    
    # Запускаем сервер
    web.run_app(aiohttp_app, host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    # Запускаем aiohttp сервер (он будет обрабатывать webhook)
    run_aiohttp_app()

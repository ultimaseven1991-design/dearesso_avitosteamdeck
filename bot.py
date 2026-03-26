import os
import logging
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio

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

# Flask приложение
app = Flask(__name__)

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(commands=['start'])
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

@dp.message(commands=['help'])
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

@dp.message(commands=['search'])
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

@dp.message(commands=['settings'])
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

@dp.message()
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

@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    """Эндпоинт для получения обновлений от Telegram"""
    try:
        update_data = await request.get_json()
        if not update_data:
            return jsonify({"ok": False, "error": "Empty update"}), 400
        
        update = types.Update(**update_data)
        await dp.process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check для Render"""
    return jsonify({"status": "healthy"}), 200

# ============= ЗАПУСК =============

async def setup_webhook():
    """Установка webhook при запуске"""
    try:
        await bot.delete_webhook()
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])
        logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

async def main():
    """Главная функция запуска"""
    await setup_webhook()
    
    # Запускаем Flask с asyncio
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    
    # Создаем ASGI приложение для Flask
    from asgiref.wsgi import WsgiToAsgi
    asgi_app = WsgiToAsgi(app)
    
    # Добавляем обработчик webhook в Flask маршруты
    @app.route(WEBHOOK_PATH, methods=['POST'])
    async def webhook():
        update_data = await request.get_json()
        if update_data:
            update = types.Update(**update_data)
            await dp.process_update(update)
        return "ok"
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    await serve(asgi_app, config)

if __name__ == '__main__':
    asyncio.run(main())

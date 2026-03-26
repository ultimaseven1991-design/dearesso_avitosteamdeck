import os
import logging
import asyncio
import threading
from flask import Flask, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

PORT = int(os.getenv("PORT", 10000))

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Flask приложение для health check
app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    """Health check endpoint для Render"""
    return jsonify({
        "status": "ok",
        "message": "Telegram bot is running"
    })

@app.route('/health', methods=['GET'])
def health():
    """Альтернативный health check"""
    return jsonify({"status": "healthy"}), 200

def run_http_server():
    """Запуск HTTP сервера в отдельном потоке"""
    logger.info(f"🌐 Запуск HTTP сервера на порту {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_name = message.from_user.first_name
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        f"🤖 Я бот для поиска объявлений на Avito\n"
        f"📱 Помогаю находить Steam Deck и другие товары\n\n"
        f"🔍 Используй команду /help чтобы узнать что я умею"
    )
    await message.reply(welcome_text)

@dp.message(Command("help"))
async def cmd_help(message: Message):
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

@dp.message(Command("search"))
async def cmd_search(message: Message):
    await message.reply(
        "🔍 <b>Что ищем?</b>\n\n"
        "Отправьте мне название товара, например:\n"
        "• Steam Deck\n"
        "• Nintendo Switch\n"
        "• PlayStation 5\n\n"
        "И я найду актуальные объявления!"
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.reply(
        "⚙️ <b>Настройки</b>\n\n"
        "Сейчас доступны:\n"
        "• Город: вся Россия\n"
        "• Цена: любая\n"
        "• Сортировка: по дате\n\n"
        "Скоро появятся дополнительные настройки!"
    )

@dp.message()
async def handle_text(message: Message):
    search_query = message.text.strip()
    
    if len(search_query) < 3:
        await message.reply(
            "❌ Слишком короткий запрос!\n"
            "Введите минимум 3 символа для поиска."
        )
        return
    
    await bot.send_chat_action(message.chat.id, 'typing')
    await message.reply(
        f"🔍 <b>Ищу: {search_query}</b>\n\n"
        f"⏳ Поиск на Avito...\n\n"
        f"✨ <i>Скоро здесь появятся результаты!</i>"
    )

# ============= ЗАПУСК =============

async def run_bot():
    """Запуск Telegram бота в режиме polling"""
    logger.info("🚀 Запуск Telegram бота в режиме polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

def main():
    """Главная функция: запускает HTTP сервер в потоке и бота в основном потоке"""
    # Запускаем HTTP сервер в отдельном потоке
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    logger.info("✅ HTTP сервер запущен в фоновом потоке")
    
    # Запускаем бота в основном потоке (asyncio)
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()

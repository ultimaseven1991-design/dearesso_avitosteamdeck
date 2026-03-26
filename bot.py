import os
import logging
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebhookInfo
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен из переменных окружения Render
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

# Настройки webhook
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 10000))
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", f"https://localhost:{PORT}")
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Flask приложение
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
    await message.reply(help_text, parse_mode='HTML')

@dp.message_handler(commands=['search'])
async def cmd_search(message: types.Message):
    """Обработчик команды /search"""
    await message.reply(
        "🔍 <b>Что ищем?</b>\n\n"
        "Отправьте мне название товара, например:\n"
        "• Steam Deck\n"
        "• Nintendo Switch\n"
        "• PlayStation 5\n\n"
        "И я найду актуальные объявления!",
        parse_mode='HTML'
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
        "Скоро появятся дополнительные настройки!",
        parse_mode='HTML'
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
    # Пока что демо-ответ
    await message.reply(
        f"🔍 <b>Ищу: {search_query}</b>\n\n"
        f"⏳ Поиск на Avito...\n\n"
        f"✨ <i>Скоро здесь появятся результаты!</i>",
        parse_mode='HTML'
    )
    
    # TODO: Добавить реальный парсинг Avito
    # await search_avito(search_query, message.chat.id)

# ============= ОБРАБОТЧИКИ ОШИБОК =============

@dp.errors_handler()
async def errors_handler(update, exception):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {exception}")
    return True

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
        # Получаем JSON данные
        update_data = await request.get_json()
        
        if not update_data:
            logger.warning("Получен пустой update")
            return jsonify({"ok": False, "error": "Empty update"}), 400
        
        # Конвертируем в объект Update
        update = types.Update(**update_data)
        
        # Обрабатываем обновление
        await dp.process_update(update)
        
        return jsonify({"ok": True})
        
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check для Render"""
    return jsonify({"status": "healthy"}), 200

# ============= ФУНКЦИИ ДЛЯ WEBHOOK =============

async def setup_webhook():
    """Установка webhook при запуске"""
    try:
        # Получаем информацию о текущем webhook
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Текущий webhook: {webhook_info.url}")
        
        # Если webhook уже установлен на другой URL, удаляем
        if webhook_info.url and webhook_info.url != WEBHOOK_URL:
            logger.info("Удаляем старый webhook...")
            await bot.delete_webhook()
        
        # Устанавливаем новый webhook
        await bot.set_webhook(
            url=WEBHOOK_URL,
            max_connections=40,
            allowed_updates=["message", "callback_query"]
        )
        
        logger.info(f"✅ Webhook успешно установлен: {WEBHOOK_URL}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при установке webhook: {e}")
        raise

async def on_startup():
    """Действия при запуске приложения"""
    logger.info("🚀 Запуск Telegram бота...")
    await setup_webhook()
    logger.info("✅ Бот готов к работе!")

async def on_shutdown():
    """Действия при остановке приложения"""
    logger.info("🛑 Остановка бота...")
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ Бот остановлен")

# ============= ЗАПУСК ПРИЛОЖЕНИЯ =============

if __name__ == '__main__':
    # Создаем цикл событий
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Запускаем startup функции
    loop.run_until_complete(on_startup())
    
    try:
        # Запускаем Flask сервер
        logger.info(f"🔥 Запуск Flask сервера на порту {PORT}")
        app.run(
            host='0.0.0.0',
            port=PORT,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    finally:
        # Останавливаем бота
        loop.run_until_complete(on_shutdown())
        loop.close()

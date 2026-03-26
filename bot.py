import os
import logging
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
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
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

@dp.message(Command("search"))
async def cmd_search(message: Message):
    """Обработчик команды /search"""
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
async def handle_text(message: Message):
    """Обработчик всех текстовых сообщений (поиск по ключевым словам)"""
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

# ============= ЗАПУСК =============

async def main():
    """Главная функция запуска"""
    logger.info("🚀 Запуск бота в режиме polling...")
    
    # Удаляем предыдущие вебхуки (если были)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

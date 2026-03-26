import os
import logging
import asyncio
import threading
import time
import json
import re
from datetime import datetime
from typing import Dict, List, Set
from flask import Flask, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
import aiohttp
from bs4 import BeautifulSoup

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

PORT = int(os.getenv("PORT", 10000))
CHAT_ID = os.getenv("CHAT_ID")  # Ваш ID чата (можно получить через @userinfobot)
if not CHAT_ID:
    logger.warning("CHAT_ID не установлен, бот будет отправлять уведомления только в чат с командой /start")

# URL для поиска (жестко привязан)
AVITO_URL = "https://www.avito.ru/all/igry_pristavki_i_programmy/igry_pristavki_i_programmy/igrovye_pristavki/valve_steam_deck_oled-ASgBAgICA0SSAsoJtvoNmtjzEfTNFJrKjwM?d=1&f=ASgBAgECA0SSAsoJtvoNmtjzEfTNFJrKjwMBRcaaDBl7ImZyb20iOjM1MDAwLCJ0byI6NDUwMDB9&q=steam+deck+oled&s=104"

# Хранилище для отслеживания отправленных объявлений
sent_items: Set[str] = set()
# Хранилище активных чатов для мониторинга
active_chats: Set[int] = set()

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
    return jsonify({"status": "ok", "message": "Telegram bot is running"})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

# ============= ФУНКЦИИ ПАРСИНГА AVITO =============

async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Загружает страницу с заголовками браузера"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 429:
                logger.warning("Avito вернул 429 Too Many Requests, ждём 60 секунд...")
                await asyncio.sleep(60)
                return await fetch_page(session, url)  # повторяем после ожидания
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы: {e}")
        return ""

def parse_items(html: str) -> List[Dict[str, str]]:
    """Парсит объявления из HTML"""
    items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Поиск карточек объявлений
    item_cards = soup.find_all('div', {'data-marker': 'item'})
    
    for card in item_cards:
        try:
            # Название
            title_elem = card.find('h3', {'itemprop': 'name'})
            if not title_elem:
                title_elem = card.find('a', {'data-marker': 'item-title'})
            title = title_elem.get_text(strip=True) if title_elem else "Название не найдено"
            
            # Цена
            price_elem = card.find('span', {'class': 'price'})
            if not price_elem:
                price_elem = card.find('meta', {'itemprop': 'price'})
                if price_elem:
                    price = price_elem.get('content', 'Цена не указана')
                else:
                    price = "Цена не указана"
            else:
                price = price_elem.get_text(strip=True)
            
            # Ссылка
            link_elem = card.find('a', {'data-marker': 'item-title'})
            if not link_elem:
                link_elem = card.find('a', {'class': 'title'})
            
            if link_elem and link_elem.get('href'):
                link = link_elem['href']
                if not link.startswith('http'):
                    link = 'https://www.avito.ru' + link
            else:
                link = "#"
            
            # ID объявления
            item_id = card.get('data-item-id', link.split('_')[-1] if '_' in link else link)
            
            items.append({
                'id': str(item_id),
                'title': title,
                'price': price,
                'link': link
            })
        except Exception as e:
            logger.error(f"Ошибка при парсинге карточки: {e}")
            continue
    
    return items

async def check_new_items():
    """Проверяет новые объявления и отправляет уведомления"""
    logger.info("🔍 Проверка новых объявлений...")
    
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, AVITO_URL)
        if not html:
            logger.error("Не удалось загрузить страницу")
            return
        
        current_items = parse_items(html)
        logger.info(f"Найдено объявлений: {len(current_items)}")
        
        # Проверяем новые объявления
        new_items = []
        for item in current_items:
            if item['id'] not in sent_items:
                new_items.append(item)
                sent_items.add(item['id'])
        
        if new_items:
            logger.info(f"Найдено новых объявлений: {len(new_items)}")
            # Отправляем уведомления во все активные чаты
            for chat_id in active_chats:
                for item in new_items:
                    await send_item_notification(chat_id, item)
        else:
            logger.info("Новых объявлений не найдено")

async def send_item_notification(chat_id: int, item: Dict[str, str]):
    """Отправляет сообщение о новом объявлении"""
    message_text = (
        f"🆕 <b>Новое объявление!</b>\n\n"
        f"📦 <b>{item['title']}</b>\n"
        f"💰 <b>Цена:</b> {item['price']}\n"
        f"🔗 <a href='{item['link']}'>Ссылка на объявление</a>\n\n"
        f"⏰ Найдено: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    try:
        await bot.send_message(chat_id, message_text, disable_web_page_preview=False)
        logger.info(f"Отправлено уведомление в чат {chat_id}: {item['title']}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")

async def monitoring_loop():
    """Основной цикл мониторинга"""
    logger.info("🔄 Запуск цикла мониторинга (проверка каждые 5 минут)")
    
    while True:
        try:
            if active_chats:
                await check_new_items()
            else:
                logger.info("Нет активных чатов, ожидание...")
            
            # Ждём 5 минут
            await asyncio.sleep(300)  # 5 минут = 300 секунд
            
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}")
            await asyncio.sleep(60)  # При ошибке ждём минуту

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Запускает мониторинг для этого чата"""
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    
    # Добавляем чат в активные
    active_chats.add(chat_id)
    
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        f"🔍 <b>Мониторинг Avito запущен!</b>\n\n"
        f"📱 Отслеживаю новые объявления по запросу:\n"
        f"<i>Steam Deck OLED (цена от 35000 до 45000 руб)</i>\n\n"
        f"✅ Проверка будет происходить каждые 5 минут\n"
        f"📨 Как только появится новое объявление, я сразу пришлю его сюда\n\n"
        f"🛑 Для остановки мониторинга используйте команду /stop"
    )
    
    await message.reply(welcome_text)
    logger.info(f"Запущен мониторинг для чата {chat_id}")

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    """Останавливает мониторинг для этого чата"""
    chat_id = message.chat.id
    
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await message.reply("🛑 Мониторинг остановлен. Чтобы запустить снова, используйте /start")
        logger.info(f"Остановлен мониторинг для чата {chat_id}")
    else:
        await message.reply("❌ Мониторинг не был запущен. Используйте /start для запуска")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Справка по командам"""
    help_text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start - Запустить мониторинг новых объявлений\n"
        "/stop - Остановить мониторинг\n"
        "/help - Показать эту справку\n"
        "/status - Показать статус мониторинга\n\n"
        "🔍 <b>Отслеживаемый запрос:</b>\n"
        "Steam Deck OLED, цена от 35000 до 45000 руб"
    )
    await message.reply(help_text)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Показывает статус мониторинга"""
    chat_id = message.chat.id
    is_active = chat_id in active_chats
    
    status_text = (
        f"📊 <b>Статус мониторинга</b>\n\n"
        f"📱 Чат: {message.chat.title or 'личный'}\n"
        f"🟢 Активен: {'✅ Да' if is_active else '❌ Нет'}\n"
        f"📦 Найдено объявлений всего: {len(sent_items)}\n"
        f"⏱ Проверка каждые 5 минут\n\n"
        f"🔗 <a href='{AVITO_URL}'>Открыть поиск на Avito</a>"
    )
    
    await message.reply(status_text, disable_web_page_preview=True)

# ============= ЗАПУСК HTTP СЕРВЕРА =============

def run_http_server():
    """Запуск HTTP сервера в отдельном потоке"""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ============= ЗАПУСК БОТА =============

async def run_bot():
    """Запуск бота и мониторинга"""
    logger.info("🚀 Запуск Telegram бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем цикл мониторинга параллельно
    asyncio.create_task(monitoring_loop())
    
    # Запускаем polling
    await dp.start_polling(bot)

def main():
    """Главная функция"""
    # Запускаем HTTP сервер в отдельном потоке
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    logger.info(f"✅ HTTP сервер запущен на порту {PORT}")
    
    # Запускаем бота
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()

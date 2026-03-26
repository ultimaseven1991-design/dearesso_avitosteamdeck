import os
import logging
import asyncio
import threading
import json
import aiohttp
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from datetime import datetime
from typing import Set, Dict, List
import os.path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

PORT = int(os.getenv("PORT", 10000))
DATA_FILE = "bot_data.json"  # Файл для сохранения данных

# URL для поиска
AVITO_URL = "https://www.avito.ru/all/igry_pristavki_i_programmy/igry_pristavki_i_programmy/igrovye_pristavki/valve_steam_deck_oled-ASgBAgICA0SSAsoJtvoNmtjzEfTNFJrKjwM?d=1&f=ASgBAgECA0SSAsoJtvoNmtjzEfTNFJrKjwMBRcaaDBl7ImZyb20iOjM1MDAwLCJ0byI6NDUwMDB9&q=steam+deck+oled&s=104"

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Flask приложение
app = Flask(__name__)

# ============= РАБОТА С ХРАНИЛИЩЕМ =============

def load_data() -> Dict:
    """Загружает данные из файла"""
    if not os.path.exists(DATA_FILE):
        return {"sent_items": [], "active_chats": []}
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {"sent_items": [], "active_chats": []}

def save_data(sent_items: Set[str], active_chats: Set[int]):
    """Сохраняет данные в файл"""
    data = {
        "sent_items": list(sent_items),
        "active_chats": list(active_chats)
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Данные сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# Загружаем сохранённые данные
saved_data = load_data()
sent_items: Set[str] = set(saved_data.get("sent_items", []))
active_chats: Set[int] = set(saved_data.get("active_chats", []))

logger.info(f"Загружено {len(sent_items)} отправленных объявлений и {len(active_chats)} активных чатов")

# ============= ФУНКЦИИ ПАРСИНГА =============

async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Загружает страницу"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 429:
                logger.warning("Avito вернул 429, ждём 60 секунд...")
                await asyncio.sleep(60)
                return await fetch_page(session, url)
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        return ""

def parse_items(html: str) -> List[Dict[str, str]]:
    """Парсит объявления"""
    items = []
    soup = BeautifulSoup(html, 'html.parser')
    item_cards = soup.find_all('div', {'data-marker': 'item'})
    
    for card in item_cards:
        try:
            title_elem = card.find('h3', {'itemprop': 'name'}) or card.find('a', {'data-marker': 'item-title'})
            title = title_elem.get_text(strip=True) if title_elem else "Название не найдено"
            
            price_elem = card.find('span', {'class': 'price'}) or card.find('meta', {'itemprop': 'price'})
            if price_elem:
                price = price_elem.get('content', price_elem.get_text(strip=True)) if price_elem.name == 'meta' else price_elem.get_text(strip=True)
            else:
                price = "Цена не указана"
            
            link_elem = card.find('a', {'data-marker': 'item-title'}) or card.find('a', {'class': 'title'})
            if link_elem and link_elem.get('href'):
                link = link_elem['href']
                if not link.startswith('http'):
                    link = 'https://www.avito.ru' + link
            else:
                link = "#"
            
            item_id = card.get('data-item-id', link.split('_')[-1] if '_' in link else link)
            
            items.append({
                'id': str(item_id),
                'title': title,
                'price': price,
                'link': link
            })
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            continue
    
    return items

async def send_item_notification(chat_id: int, item: Dict[str, str]):
    """Отправляет уведомление"""
    message_text = (
        f"🆕 <b>Новое объявление!</b>\n\n"
        f"📦 <b>{item['title']}</b>\n"
        f"💰 <b>Цена:</b> {item['price']}\n"
        f"🔗 <a href='{item['link']}'>Ссылка на объявление</a>\n\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    try:
        await bot.send_message(chat_id, message_text, disable_web_page_preview=False)
        logger.info(f"Отправлено уведомление в чат {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

async def check_new_items():
    """Проверяет новые объявления"""
    if not active_chats:
        logger.info("Нет активных чатов, проверка пропущена")
        return
    
    logger.info("🔍 Проверка новых объявлений...")
    
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, AVITO_URL)
        if not html:
            return
        
        current_items = parse_items(html)
        logger.info(f"Найдено объявлений: {len(current_items)}")
        
        new_items = []
        for item in current_items:
            if item['id'] not in sent_items:
                new_items.append(item)
                sent_items.add(item['id'])
        
        if new_items:
            logger.info(f"🆕 Найдено новых объявлений: {len(new_items)}")
            save_data(sent_items, active_chats)  # Сохраняем после добавления новых
            for chat_id in active_chats:
                for item in new_items:
                    await send_item_notification(chat_id, item)
        else:
            logger.info("Новых объявлений не найдено")

async def monitoring_loop():
    """Цикл мониторинга"""
    logger.info("🔄 Запуск цикла мониторинга (проверка каждые 5 минут)")
    
    while True:
        try:
            if active_chats:
                await check_new_items()
            else:
                logger.info("Нет активных чатов, ожидание...")
            
            await asyncio.sleep(300)  # 5 минут
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
            await asyncio.sleep(60)

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    chat_id = message.chat.id
    active_chats.add(chat_id)
    save_data(sent_items, active_chats)
    
    await message.reply(
        f"👋 Привет! Мониторинг запущен.\n\n"
        f"🔍 Отслеживаю: Steam Deck OLED (35-45 тыс руб)\n"
        f"⏱ Проверка каждые 5 минут\n\n"
        f"🛑 Для остановки: /stop"
    )
    logger.info(f"Запущен мониторинг для чата {chat_id}")

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    chat_id = message.chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        save_data(sent_items, active_chats)
        await message.reply("🛑 Мониторинг остановлен. /start для запуска")
        logger.info(f"Остановлен мониторинг для чата {chat_id}")
    else:
        await message.reply("Мониторинг не был запущен")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    chat_id = message.chat.id
    is_active = chat_id in active_chats
    
    await message.reply(
        f"📊 <b>Статус</b>\n\n"
        f"🟢 Мониторинг: {'активен ✅' if is_active else 'не активен ❌'}\n"
        f"📦 Отправлено объявлений всего: {len(sent_items)}\n"
        f"👥 Активных чатов: {len(active_chats)}\n"
        f"⏱ Проверка: каждые 5 минут"
    )

# ============= HTTP СЕРВЕР =============

@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "ok"})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

def run_http_server():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ============= ЗАПУСК =============

async def run_bot():
    logger.info("🚀 Запуск Telegram бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(monitoring_loop())
    await dp.start_polling(bot)

def main():
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    logger.info(f"✅ HTTP сервер запущен на порту {PORT}")
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
        save_data(sent_items, active_chats)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()

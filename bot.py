import os
import time
import json
import hashlib
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Bot

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Токен от @BotFather
CHAT_ID = os.getenv("CHAT_ID")                # Ваш ID чата
AVITO_URL = os.getenv("AVITO_URL")            # Ссылка на поиск на Avito

# Файл для сохранения отправленных объявлений
SENT_ADS_FILE = "sent_ads.json"

# Flask приложение
app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)
sent_ads = set()

# ========== ФУНКЦИИ ==========

def load_sent_ads():
    """Загружает ID отправленных объявлений"""
    global sent_ads
    try:
        with open(SENT_ADS_FILE, "r") as f:
            sent_ads = set(json.load(f))
    except:
        sent_ads = set()

def save_sent_ads():
    """Сохраняет ID отправленных объявлений"""
    with open(SENT_ADS_FILE, "w") as f:
        json.dump(list(sent_ads), f)

def check_avito():
    """Проверяет Avito и возвращает новые объявления"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(AVITO_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        new_ads = []
        items = soup.find_all('div', {'data-marker': 'item'})
        
        for item in items[:5]:
            try:
                # Название и ссылка
                title_elem = item.find('a', {'data-marker': 'item-title'})
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href')
                if link and not link.startswith('http'):
                    link = f"https://www.avito.ru{link}"
                
                # Цена
                price_elem = item.find('span', {'data-marker': 'item-price'})
                price = price_elem.get_text(strip=True) if price_elem else "Цена не указана"
                
                # Уникальный ID
                ad_id = hashlib.md5(f"{title}{link}".encode()).hexdigest()
                
                # Если объявление новое
                if ad_id not in sent_ads:
                    new_ads.append({
                        'id': ad_id,
                        'title': title,
                        'price': price,
                        'link': link
                    })
                    sent_ads.add(ad_id)
                    
            except:
                continue
        
        if new_ads:
            save_sent_ads()
            
        return new_ads
        
    except:
        return []

def send_to_telegram(ad):
    """Отправляет объявление в Telegram"""
    message = f"""🆕 НОВОЕ ОБЪЯВЛЕНИЕ!

{ad['title']}

💰 {ad['price']}

🔗 {ad['link']}"""
    
    bot.send_message(chat_id=CHAT_ID, text=message)

# ========== ЗАПУСК МОНИТОРИНГА ==========

def monitor():
    """Бесконечный цикл проверки"""
    load_sent_ads()
    
    # Приветствие при запуске
    try:
        bot.send_message(chat_id=CHAT_ID, text="✅ Бот запущен")
    except:
        pass
    
    while True:
        print(f"[{time.strftime('%H:%M:%S')}] Проверка...")
        
        new_ads = check_avito()
        
        for ad in new_ads:
            print(f"Найдено: {ad['title']}")
            send_to_telegram(ad)
            time.sleep(1)
        
        time.sleep(60)  # Проверка каждую минуту

# ========== ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ==========

@app.route('/')
def health():
    return "OK", 200

def start_web():
    """Запускает веб-сервер"""
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ========== ТОЧКА ВХОДА ==========

if __name__ == "__main__":
    # Запускаем веб-сервер в фоне
    threading.Thread(target=start_web, daemon=True).start()
    
    # Запускаем мониторинг
    monitor()
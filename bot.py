import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
import requests
import os

# ================== НАСТРОЙКИ ==================
TOKEN = '7388144074:AAFkIqUuXeJTIZPB3zE3nHuR6OYpgcf80NU'
SECRET_TOKEN = 'SimpleToken123'  # Только латиница/цифры
WEBHOOK_URL = 'https://albion-refine-bot.onrender.com'  # Ваш URL из Render
PORT = 10000
# ================================================

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Данные бота
RESOURCES = ["WOOD", "ORE", "FIBER", "HIDE", "ROCK"]
TIERS = ["T2", "T3", "T4", "T4.1", "T4.2", "T4.3", "T4.4", "T5", "T5.1", "T5.2", 
         "T5.3", "T5.4", "T6", "T6.1", "T6.2", "T6.3", "T6.4", "T7", "T7.1", 
         "T7.2", "T7.3", "T7.4", "T8", "T8.1", "T8.2", "T8.3", "T8.4"]
CITIES = ["Caerleon", "Thetford", "Fort Sterling", "Lymhurst", 
          "Bridgewatch", "Martlock", "Black Market"]
          
REFINING_BONUSES = {
    "Thetford": {"FIBER": 0.15},
    "Fort Sterling": {"ORE": 0.15},
    "Lymhurst": {"WOOD": 0.15},
    "Bridgewatch": {"ROCK": 0.15},
    "Martlock": {"HIDE": 0.15},
    "Caerleon": {},
    "Black Market": {}
}

# Состояния ConversationHandler
(MODE, RESOURCE, TIER, BUY_CITY, 
 REFINE_CITY, SELL_CITY, RRR, TAX, PRICES) = range(9)

# ============= ОСНОВНЫЕ ФУНКЦИИ БОТА =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это бот для расчёта прибыли от переработки ресурсов в Albion Online.\n"
        "Используй /refine для расчёта прибыли или /best для самых выгодных предложений."
    )

async def refine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ручной режим", callback_data='manual')],
        [InlineKeyboardButton("Автоматический режим", callback_data='auto')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери режим:", reply_markup=reply_markup)
    return MODE

async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = query.data
    
    keyboard = [[InlineKeyboardButton(res, callback_data=res)] for res in RESOURCES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери ресурс:", reply_markup=reply_markup)
    return RESOURCE

async def resource_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["resource"] = query.data
    
    keyboard = [[InlineKeyboardButton(tier, callback_data=tier)] for tier in TIERS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери тир и зачарование:", reply_markup=reply_markup)
    return TIER

async def tier_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["tier"] = query.data
    
    keyboard = [[InlineKeyboardButton(city, callback_data=city)] for city in CITIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери город покупки сырья:", reply_markup=reply_markup)
    return BUY_CITY

async def buy_city_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["buy_city"] = query.data
    
    keyboard = [[InlineKeyboardButton(city, callback_data=city)] for city in CITIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери город переработки:", reply_markup=reply_markup)
    return REFINE_CITY

async def refine_city_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["refine_city"] = query.data
    
    keyboard = [[InlineKeyboardButton(city, callback_data=city)] for city in CITIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выбери город продажи:", reply_markup=reply_markup)
    return SELL_CITY

async def sell_city_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["sell_city"] = query.data
    
    if context.user_data["mode"] == "manual":
        await query.message.reply_text("Введи процент возврата ресурсов (RRR, например, 15.2):")
        return RRR
    else:
        await query.message.reply_text("Введи процент возврата ресурсов (RRR, например, 15.2):")
        return RRR

async def rrr_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rrr"] = float(update.message.text)
    
    if context.user_data["mode"] == "manual":
        await update.message.reply_text("Введи налог на переработку (%, например, 5):")
        return TAX
    else:
        return await calculate_auto(update, context)

async def tax_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tax"] = float(update.message.text)
    await update.message.reply_text("Введи цены в формате: <цена сырья> <цена готового ресурса>")
    return PRICES

async def prices_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) != 2:
        await update.message.reply_text("Неверный формат. Пример: 100 150")
        return PRICES
    
    raw_price, refined_price = map(float, args)
    context.user_data["raw_price"] = raw_price
    context.user_data["refined_price"] = refined_price
    
    # Расчёт прибыли
    resource = context.user_data["resource"]
    tier = context.user_data["tier"]
    buy_city = context.user_data["buy_city"]
    refine_city = context.user_data["refine_city"]
    sell_city = context.user_data["sell_city"]
    rrr = context.user_data["rrr"]
    tax = context.user_data["tax"]
    
    bonus_rrr = REFINING_BONUSES.get(refine_city, {}).get(resource, 0)
    total_rrr = rrr + (rrr * bonus_rrr)
    material_cost = raw_price * (1 - total_rrr / 100)
    refining_cost = material_cost * (tax / 100)
    total_cost = material_cost + refining_cost
    profit = refined_price - total_cost
    
    await update.message.reply_text(
        f"Ресурс: {resource} {tier}\n"
        f"Город покупки: {buy_city}\n"
        f"Город переработки: {refine_city}\n"
        f"Город продажи: {sell_city}\n"
        f"Цена сырья: {raw_price} серебра\n"
        f"Цена готового ресурса: {refined_price} серебра\n"
        f"Возврат ресурсов (RRR): {total_rrr:.2f}%\n"
        f"Налог: {tax}%\n"
        f"Общая стоимость: {total_cost:.2f} серебра\n"
        f"Прибыль: {profit:.2f} серебра"
    )
    return ConversationHandler.END

async def calculate_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resource = context.user_data["resource"]
    tier = context.user_data["tier"]
    buy_city = context.user_data["buy_city"]
    refine_city = context.user_data["refine_city"]
    sell_city = context.user_data["sell_city"]
    rrr = context.user_data["rrr"]
    
    # Формируем идентификатор ресурса для API
    raw_item = f"{resource}_{tier.replace('.', '_')}"
    refined_item = f"{resource.replace('ROCK', 'STONE')}_PLANKS_{tier.replace('.', '_')}" if resource == "WOOD" else \
                  f"{resource}_METALBAR_{tier.replace('.', '_')}" if resource == "ORE" else \
                  f"{resource}_CLOTH_{tier.replace('.', '_')}" if resource == "FIBER" else \
                  f"{resource}_LEATHER_{tier.replace('.', '_')}" if resource == "HIDE" else \
                  f"{resource}_STONEBLOCK_{tier.replace('.', '_')}"
    
    # Запрос к API
    api_url = f"https://www.albion-online-data.com/api/v2/stats/prices/{raw_item},{refined_item}?locations={buy_city},{sell_city}"
    response = requests.get(api_url)
    if response.status_code != 200:
        await update.message.reply_text("Ошибка при получении данных из API. Попробуй позже.")
        return ConversationHandler.END
    
    data = response.json()
    raw_price = next((item["sell_price_min"] for item in data if item["item_id"] == raw_item and item["city"] == buy_city), 0)
    refined_price = next((item["sell_price_min"] for item in data if item["item_id"] == refined_item and item["city"] == sell_city), 0)
    
    if raw_price == 0 or refined_price == 0:
        await update.message.reply_text("Цены не найдены для выбранных параметров.")
        return ConversationHandler.END
    
    # Расчёт прибыли
    bonus_rrr = REFINING_BONUSES.get(refine_city, {}).get(resource, 0)
    total_rrr = rrr + (rrr * bonus_rrr)
    material_cost = raw_price * (1 - total_rrr / 100)
    refining_cost = material_cost * 0.05  # Предположим 5% налог
    total_cost = material_cost + refining_cost
    profit = refined_price - total_cost
    
    await update.message.reply_text(
        f"Ресурс: {resource} {tier}\n"
        f"Город покупки: {buy_city}\n"
        f"Город переработки: {refine_city}\n"
        f"Город продажи: {sell_city}\n"
        f"Цена сырья (API): {raw_price} серебра\n"
        f"Цена готового ресурса (API): {refined_price} серебра\n"
        f"Возврат ресурсов (RRR): {total_rrr:.2f}%\n"
        f"Прибыль: {profit:.2f} серебра"
    )
    return ConversationHandler.END

async def best(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Поиск самых выгодных предложений
    results = []
    for resource in RESOURCES:
        for tier in TIERS:
            for buy_city in CITIES:
                for refine_city in CITIES:
                    for sell_city in CITIES:
                        raw_item = f"{resource}_{tier.replace('.', '_')}"
                        refined_item = f"{resource.replace('ROCK', 'STONE')}_PLANKS_{tier.replace('.', '_')}" if resource == "WOOD" else \
                                      f"{resource}_METALBAR_{tier.replace('.', '_')}" if resource == "ORE" else \
                                      f"{resource}_CLOTH_{tier.replace('.', '_')}" if resource == "FIBER" else \
                                      f"{resource}_LEATHER_{tier.replace('.', '_')}" if resource == "HIDE" else \
                                      f"{resource}_STONEBLOCK_{tier.replace('.', '_')}"
                        
                        api_url = f"https://www.albion-online-data.com/api/v2/stats/prices/{raw_item},{refined_item}?locations={buy_city},{sell_city}"
                        response = requests.get(api_url)
                        if response.status_code != 200:
                            continue
                        
                        data = response.json()
                        raw_price = next((item["sell_price_min"] for item in data if item["item_id"] == raw_item and item["city"] == buy_city), 0)
                        refined_price = next((item["sell_price_min"] for item in data if item["item_id"] == refined_item and item["city"] == sell_city), 0)
                        
                        if raw_price == 0 or refined_price == 0:
                            continue
                        
                        rrr = 15.2  # Базовый RRR
                        bonus_rrr = REFINING_BONUSES.get(refine_city, {}).get(resource, 0)
                        total_rrr = rrr + (rrr * bonus_rrr)
                        material_cost = raw_price * (1 - total_rrr / 100)
                        refining_cost = material_cost * 0.05
                        total_cost = material_cost + refining_cost
                        profit = refined_price - total_cost
                        
                        if profit > 0:
                            results.append({
                                "resource": resource,
                                "tier": tier,
                                "buy_city": buy_city,
                                "refine_city": refine_city,
                                "sell_city": sell_city,
                                "profit": profit,
                                "raw_price": raw_price,
                                "refined_price": refined_price
                            })
    
    # Сортировка по прибыли
    results.sort(key=lambda x: x["profit"], reverse=True)
    top_results = results[:5]  # Топ-5 предложений
    
    response = "Самые выгодные предложения:\n\n"
    for i, res in enumerate(top_results, 1):
        response += (
            f"{i}. {res['resource']} {res['tier']}\n"
            f"Покупка: {res['buy_city']} ({res['raw_price']} серебра)\n"
            f"Переработка: {res['refine_city']}\n"
            f"Продажа: {res['sell_city']} ({res['refined_price']} серебра)\n"
            f"Прибыль: {res['profit']:.2f} серебра\n\n"
        )
    
    await update.message.reply_text(response or "Нет выгодных предложений на данный момент.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END
# ====== НАЧАЛО ДОБАВЛЯЕМОГО КОДА ======
from threading import Thread
import requests
import time

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для проверки работы бота"""
    await update.message.reply_text("✅ Бот активен")
    return "pong"

def keep_alive():
    """Функция для периодического пробуждения сервиса"""
    while True:
        time.sleep(240)  # Каждые 4 минуты
        try:
            requests.get(f'https://albion-refine-bot.onrender.com/ping')
        except Exception as e:
            print(f"Ping error: {e}")

# Добавляем обработчик команды /ping
app.add_handler(CommandHandler("ping", ping))

# Запускаем фоновый поток
Thread(target=keep_alive, daemon=True).start()
# ====== КОНЕЦ ДОБАВЛЯЕМОГО КОДА ======
# ============ ЗАПУСК ПРИЛОЖЕНИЯ ============
def setup_handlers():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("refine", refine)],
        states={
            MODE: [CallbackQueryHandler(mode_selected)],
            RESOURCE: [CallbackQueryHandler(resource_selected)],
            TIER: [CallbackQueryHandler(tier_selected)],
            BUY_CITY: [CallbackQueryHandler(buy_city_selected)],
            REFINE_CITY: [CallbackQueryHandler(refine_city_selected)],
            SELL_CITY: [CallbackQueryHandler(sell_city_selected)],
            RRR: [MessageHandler(filters.TEXT & ~filters.COMMAND, rrr_entered)],
            TAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, tax_entered)],
            PRICES: [MessageHandler(filters.TEXT & ~filters.COMMAND, prices_entered)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("best", best))
if __name__ == '__main__':
    setup_handlers()
    print("🟢 Бот запущен в polling-режиме")
    app.run_polling(drop_pending_updates=True)

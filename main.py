import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from openai import OpenAI

# Замени прямое указание на чтение из среды
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_KEY")

# --- Конфигурация DeepSeek ---
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"  # Официальный эндпоинт DeepSeek
)

# --- Состояния для диалога ---
AGE, WEIGHT, HEIGHT, PRODUCTS = range(4)

# Временное хранилище данных пользователя (ВНИМАНИЕ: в продакшене используй БД!)
user_data_temp = {}

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Функция запроса к DeepSeek ---
async def get_diet_plan(age, weight, height, products):
    try:
        prompt = f"""
        Пользователь - человек. Возраст: {age} лет. Вес: {weight} кг. Рост: {height} см.
        В наличии есть следующие продукты: {products}.
        
        Задача: Составь подробный и полезный план питания на один день (завтрак, обед, ужин, перекус) ИСХОДЯ ТОЛЬКО ИЗ ЭТИХ ПРОДУКТОВ.
        Учитывай калорийность для поддержания веса.
        Ответ должен быть на русском языке, структурированный, с указанием примерных граммовок.
        Если продуктов критически мало или они не сочетаются, предложи самый простой вариант, но обязательно используй только то, что есть в списке.
        """

        response = client.chat.completions.create(
            model="deepseek-chat", # Актуальная модель
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка при обращении к DeepSeek: {e}"

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я помогу составить план питания из того, что есть в холодильнике.\n"
        "Для начала скажи, сколько тебе полных лет?"
    )
    return AGE

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    if not text.isdigit() or int(text) < 10 or int(text) > 100:
        await update.message.reply_text("Пожалуйста, введи корректный возраст (цифрами, например 30).")
        return AGE
    
    user_data_temp[user_id] = {'age': int(text)}
    await update.message.reply_text("Отлично. Теперь введи свой вес в килограммах (только число).")
    return WEIGHT

async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.replace(',', '.')
    try:
        w = float(text)
        if w < 30 or w > 200:
            raise ValueError
        user_data_temp[user_id]['weight'] = w
        await update.message.reply_text("Принято. Введи свой рост в сантиметрах (только число).")
        return HEIGHT
    except:
        await update.message.reply_text("Вес должен быть числом (например, 70 или 70.5). Попробуй еще раз.")
        return WEIGHT

async def height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    if not text.isdigit() or int(text) < 100 or int(text) > 250:
        await update.message.reply_text("Рост должен быть в сантиметрах (например, 175). Попробуй еще раз.")
        return HEIGHT
    
    user_data_temp[user_id]['height'] = int(text)
    await update.message.reply_text(
        "Последний шаг: напиши через запятую ВСЕ продукты, которые у тебя есть сейчас.\n"
        "Например: яйца, помидор, сыр, рис, курица, яблоко"
    )
    return PRODUCTS

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    products_list = update.message.text
    
    # Получаем данные пользователя
    data = user_data_temp.get(user_id, {})
    age = data.get('age')
    weight = data.get('weight')
    height = data.get('height')
    
    if not all([age, weight, height]):
        await update.message.reply_text("Произошла ошибка сессии. Начни заново с команды /start")
        return ConversationHandler.END
    
    await update.message.reply_text("🧠 DeepSeek анализирует твои продукты... Подожди немного (обычно 5-15 секунд).")
    
    # Запрос к ИИ
    plan = await get_diet_plan(age, weight, height, products_list)
    
    # Отправка результата. Telegram имеет лимит 4096 символов, если план больше - режем
    if len(plan) > 4000:
        for x in range(0, len(plan), 4000):
            await update.message.reply_text(plan[x:x+4000])
    else:
        await update.message.reply_text(f"Вот твой персональный план питания:\n\n{plan}")
    
    # Чистим данные
    if user_id in user_data_temp:
        del user_data_temp[user_id]
        
    await update.message.reply_text("Спасибо за использование! Чтобы начать заново, напиши /start")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_data_temp:
        del user_data_temp[user_id]
    await update.message.reply_text("Диалог прерван. Напиши /start чтобы начать заново.")
    return ConversationHandler.END

# --- Точка входа ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
            PRODUCTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, products)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
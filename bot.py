import sys
import subprocess

# Установка зависимостей через subprocess
def install_dependencies():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])

try:
    import psycopg2
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
except ImportError:
    install_dependencies()
    import psycopg2
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Данные для подключения к PostgreSQL через Transaction Pooler
DB_PARAMS = {
    "dbname": "postgres",
    "user": "postgres.dyyqtqkrojuumkdiepqf",
    "password": "QuanticFire01109937",  # Замени на свой реальный пароль из Supabase
    "host": "aws-0-eu-central-1.pooler.supabase.com",
    "port": "6543"
}

print("Параметры подключения:", DB_PARAMS)

# Инициализация базы данных
def init_db():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        c = conn.cursor()
        # Создание таблиц
        c.execute('''CREATE TABLE IF NOT EXISTS items 
                     (id SERIAL PRIMARY KEY, name TEXT, brand TEXT, price INTEGER, sizes TEXT, photo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS subscribers 
                     (user_id TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders 
                     (id SERIAL PRIMARY KEY, user_id TEXT, item_name TEXT, size TEXT, address TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS reviews 
                     (id SERIAL PRIMARY KEY, user_id TEXT, item_id INTEGER, rating INTEGER, 
                      UNIQUE(user_id, item_id), FOREIGN KEY(item_id) REFERENCES items(id))''')
        # Проверяем, пустая ли таблица товаров, и заполняем начальными данными
        c.execute("SELECT COUNT(*) FROM items")
        if c.fetchone()[0] == 0:
            initial_items = [
                ("Nike Air Max", "Nike", 10000, "40,41,42", "https://i.imgur.com/djljEmv.jpg"),
                ("Adidas Yeezy", "Adidas", 15000, "39,40,41", "https://i.imgur.com/B0yI68i.jpg"),
                ("Puma RS-X", "Puma", 8000, "38,39,40", "https://i.imgur.com/m3CJJ36.jpg"),
                ("Reebok Classic", "Reebok", 12000, "41,42,43", "https://i.imgur.com/frUvMo9.jpg")
            ]
            c.executemany("INSERT INTO items (name, brand, price, sizes, photo) VALUES (%s, %s, %s, %s, %s)", initial_items)
        conn.commit()
        conn.close()
        print("База данных успешно инициализирована!")
    except Exception as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        raise

# Функция для загрузки каталога из базы
def load_catalog():
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    c.execute("SELECT id, name, brand, price, sizes, photo FROM items")
    items = [{"id": row[0], "name": row[1], "brand": row[2], "price": row[3], "sizes": row[4].split(","), "photo": row[5].split(",")} for row in c.fetchall()]
    # Добавляем рейтинг и количество отзывов
    for item in items:
        c.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE item_id = %s", (item["id"],))
        avg_rating, review_count = c.fetchone()
        item["avg_rating"] = round(avg_rating, 1) if avg_rating else 0
        item["review_count"] = review_count
    conn.close()
    return items

# Функция для получения списка подписчиков
def get_subscribers():
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    c.execute("SELECT user_id FROM subscribers")
    subscribers = [row[0] for row in c.fetchall()]
    conn.close()
    return subscribers

# Функция для проверки подписки
def is_subscribed(user_id):
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    c.execute("SELECT user_id FROM subscribers WHERE user_id = %s", (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result is not None

# Функция для проверки, купил ли пользователь товар
def has_purchased(user_id, item_name):
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s AND item_name LIKE %s", (str(user_id), f"{item_name}%"))
    result = c.fetchone()[0] > 0
    conn.close()
    return result

# Функция для проверки, оставил ли пользователь отзыв
def has_reviewed(user_id, item_id):
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM reviews WHERE user_id = %s AND item_id = %s", (str(user_id), item_id))
    result = c.fetchone()[0] > 0
    conn.close()
    return result

# Функция для обновления глобальных переменных
def update_catalog():
    global catalog_items, prices
    catalog_items = load_catalog()
    prices = {item["name"]: item["price"] for item in catalog_items}

# Главная клавиатура с кнопками
def main_keyboard():
    keyboard = [
        [KeyboardButton("Каталог"), KeyboardButton("Корзина")],
        [KeyboardButton("Фильтры"), KeyboardButton("Поиск")],
        [KeyboardButton("Скидки"), KeyboardButton("Подписаться"), KeyboardButton("Отписаться")],
        [KeyboardButton("Оставить рейтинг"), KeyboardButton("Отзывы"), KeyboardButton("Очистить корзину")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Клавиатура выбора типа фильтра
def filter_type_keyboard():
    keyboard = [
        [InlineKeyboardButton("По бренду", callback_data="filter_type_brand")],
        [InlineKeyboardButton("По цене", callback_data="filter_type_price")],
        [InlineKeyboardButton("По размеру", callback_data="filter_type_size")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура фильтра по бренду
def filter_brand_keyboard():
    brands = sorted(set(item["brand"] for item in catalog_items))
    keyboard = [[InlineKeyboardButton(brand, callback_data=f"filter_brand_{brand}")] for brand in brands]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура фильтра по цене
def filter_price_keyboard():
    keyboard = [
        [InlineKeyboardButton("До 10000 руб", callback_data="filter_price_0_10000")],
        [InlineKeyboardButton("10000–15000 руб", callback_data="filter_price_10000_15000")],
        [InlineKeyboardButton("Больше 15000 руб", callback_data="filter_price_15000_99999")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура фильтра по размеру
def filter_size_keyboard():
    all_sizes = sorted(set(size for item in catalog_items for size in item["sizes"]))
    keyboard = [[InlineKeyboardButton(size, callback_data=f"filter_size_{size}")] for size in all_sizes]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура выбора товара для редактирования или удаления
def item_select_keyboard(mode="select"):
    keyboard = [[InlineKeyboardButton(item["name"], callback_data=f"{mode}_{item['id']}")] for item in catalog_items]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context):
    await update.message.reply_text(
        "Привет! Это бот для продажи кроссовок. Выбери действие ниже:",
        reply_markup=main_keyboard()
    )

# Команда /catalog (или кнопка "Каталог")
async def catalog(update: Update, context):
    update_catalog()  # Обновляем каталог из базы
    items_text = "\n".join([f"{idx+1}. {item['name']} - {item['price']} руб (Рейтинг: {item['avg_rating']}/5, Отзывов: {item['review_count']})" for idx, item in enumerate(catalog_items)])
    await update.message.reply_text(
        f"Вот наш каталог:\n{items_text}\nВыбери товар кнопкой ниже:",
        reply_markup=catalog_keyboard()
    )

# Клавиатура для каталога (Inline кнопки)
def catalog_keyboard(filtered_items=None):
    items = filtered_items if filtered_items is not None else catalog_items
    keyboard = [[InlineKeyboardButton(item["name"], callback_data=f"item_{item['id']}")] for item in items]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для выбора размера
def size_keyboard(item_id):
    item = next((i for i in catalog_items if i["id"] == int(item_id)), None)
    if item:
        keyboard = [[InlineKeyboardButton(size, callback_data=f"size_{item_id}_{size}")] for size in item["sizes"]]
        return InlineKeyboardMarkup(keyboard)
    return None

# Клавиатура для покупки или добавления в корзину
def item_keyboard():
    keyboard = [
        [InlineKeyboardButton("Добавить в корзину", callback_data="add_to_cart")],
        [InlineKeyboardButton("Купить сразу", callback_data="buy")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для корзины с кнопкой "Оформить заказ"
def cart_keyboard():
    keyboard = [[InlineKeyboardButton("Оформить заказ", callback_data="order")]]
    return InlineKeyboardMarkup(keyboard)

# Команда /search (или кнопка "Поиск")
async def search(update: Update, context):
    await update.message.reply_text("Введи название, бренд, цену или размер кроссовок для поиска:", reply_markup=main_keyboard())
    context.user_data["search_mode"] = True

# Команда /subscribe (подписка на уведомления)
async def subscribe(update: Update, context):
    user_id = str(update.message.from_user.id)
    if is_subscribed(user_id):
        await update.message.reply_text("Вы уже подписаны на уведомления!", reply_markup=main_keyboard())
    else:
        conn = psycopg2.connect(**DB_PARAMS)
        c = conn.cursor()
        c.execute("INSERT INTO subscribers (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("Вы подписались на уведомления о новинках и скидках!", reply_markup=main_keyboard())

# Команда /unsubscribe (отписка от уведомлений)
async def unsubscribe(update: Update, context):
    user_id = str(update.message.from_user.id)
    if not is_subscribed(user_id):
        await update.message.reply_text("Вы не подписаны на уведомления!", reply_markup=main_keyboard())
    else:
        conn = psycopg2.connect(**DB_PARAMS)
        c = conn.cursor()
        c.execute("DELETE FROM subscribers WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("Вы отписались от уведомлений.", reply_markup=main_keyboard())

# Команда /notify (отправка уведомлений, только для админа)
async def notify(update: Update, context):
    admin_id = "508884860"
    if str(update.message.from_user.id) != admin_id:
        await update.message.reply_text("Эта команда только для администратора!", reply_markup=main_keyboard())
        return
    await update.message.reply_text("Введи текст уведомления для отправки всем подписчикам (или 'отмена' для выхода):")
    context.user_data["notify_mode"] = "text"
    context.user_data["notify_photos"] = []

# Команда /review (оставить рейтинг)
async def review(update: Update, context):
    user_id = str(update.message.from_user.id)
    await update.message.reply_text("Выбери товар, для которого хочешь оставить рейтинг:", reply_markup=item_select_keyboard("review"))
    context.user_data["review_mode"] = "select"

# Команда /reviews (переход в канал для отзывов)
async def reviews(update: Update, context):
    await update.message.reply_text(
        "Оставляй свои отзывы о товарах в нашем Telegram-канале: https://t.me/ArtShop38Reviews",
        reply_markup=main_keyboard()
    )

# Команда /add_item (добавить товар, только для админа)
async def add_item(update: Update, context):
    admin_id = "508884860"
    if str(update.message.from_user.id) != admin_id:
        await update.message.reply_text("Эта команда только для администратора!", reply_markup=main_keyboard())
        return
    await update.message.reply_text("Шаг 1: Введи название нового товара (или 'отмена' для выхода):")
    context.user_data["admin_mode"] = "add_name"
    context.user_data["new_item"] = {}

# Команда /edit_item (редактировать товар, только для админа)
async def edit_item(update: Update, context):
    admin_id = "508884860"
    if str(update.message.from_user.id) != admin_id:
        await update.message.reply_text("Эта команда только для администратора!", reply_markup=main_keyboard())
        return
    await update.message.reply_text("Выбери товар для редактирования:", reply_markup=item_select_keyboard())
    context.user_data["admin_mode"] = "edit_select"

# Команда /delete_item (удалить товар, только для админа)
async def delete_item(update: Update, context):
    admin_id = "508884860"
    if str(update.message.from_user.id) != admin_id:
        await update.message.reply_text("Эта команда только для администратора!", reply_markup=main_keyboard())
        return
    await update.message.reply_text("Выбери товар для удаления:", reply_markup=item_select_keyboard())
    context.user_data["admin_mode"] = "delete"

# Команда /stats (для админа с полной статистикой)
async def stats(update: Update, context):
    admin_id = "508884860"
    if str(update.message.from_user.id) != admin_id:
        await update.message.reply_text("Эта команда только для администратора!", reply_markup=main_keyboard())
        return
    
    conn = psycopg2.connect(**DB_PARAMS)
    c = conn.cursor()
    
    # Общее количество заказов
    c.execute("SELECT COUNT(*) FROM orders")
    total_orders = c.fetchone()[0]
    
    # Общая выручка (сумма цен всех заказанных товаров)
    c.execute("SELECT o.item_name, SUM(i.price) FROM orders o JOIN items i ON o.item_name = i.name GROUP BY o.item_name")
    revenue_data = c.fetchall()
    total_revenue = sum(row[1] for row in revenue_data) if revenue_data else 0
    
    # Топ-5 самых популярных товаров
    c.execute("SELECT item_name, COUNT(*) as order_count FROM orders GROUP BY item_name ORDER BY order_count DESC LIMIT 5")
    top_items = c.fetchall()
    top_items_text = "\n".join([f"{item[0]}: {item[1]} заказов" for item in top_items]) if top_items else "Нет данных"
    
    # Количество уникальных покупателей
    c.execute("SELECT COUNT(DISTINCT user_id) FROM orders")
    unique_buyers = c.fetchone()[0]
    
    conn.close()
    
    stats_text = (
        f"📊 Статистика продаж:\n"
        f"Общее количество заказов: {total_orders}\n"
        f"Общая выручка: {total_revenue} руб\n"
        f"Уникальных покупателей: {unique_buyers}\n"
        f"Топ-5 популярных товаров:\n{top_items_text}"
    )
    await update.message.reply_text(stats_text, reply_markup=main_keyboard())

# Обработка нажатий на Inline кнопки
async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("item_"):
        item_id = query.data.split("_")[1]
        item = next((i for i in catalog_items if i["id"] == int(item_id)), None)
        if item:
            await query.message.reply_photo(
                photo=item["photo"][0],  # Только первое фото
                caption=f"{item['name']}\nЦена: {item['price']} руб\nРейтинг: {item['avg_rating']}/5 (Отзывов: {item['review_count']})\nВыбери размер:",
                reply_markup=size_keyboard(item_id)
            )
            await query.message.delete()
    elif query.data.startswith("size_"):
        parts = query.data.split("_")
        item_id, size = parts[1], parts[2]
        item = next((i for i in catalog_items if i["id"] == int(item_id)), None)
        if item:
            context.user_data["last_item"] = f"{item['name']} (размер {size})"
            await query.edit_message_caption(f"{item['name']} (размер {size})\nЧто дальше?", reply_markup=item_keyboard())
    elif query.data == "add_to_cart":
        item = context.user_data.get("last_item", "Неизвестный товар")
        if "cart" not in context.user_data:
            context.user_data["cart"] = []
        context.user_data["cart"].append(item)
        await query.edit_message_caption(f"{item} добавлен в корзину!\nНажми 'Корзина' для просмотра.", reply_markup=main_keyboard())
    elif query.data == "buy":
        item = context.user_data.get("last_item", "Неизвестный товар")
        context.bot_data["orders"] = context.bot_data.get("orders", 0) + 1
        await query.edit_message_caption(f"Спасибо за заказ {item}! Напиши свой адрес доставки в ответное сообщение.")
    elif query.data == "order":
        await query.edit_message_text("Напиши свой адрес доставки в ответное сообщение.")
    elif query.data.startswith("filter_type_"):
        filter_type = query.data.split("_")[2]
        if filter_type == "brand":
            await query.edit_message_text("Выбери бренд:", reply_markup=filter_brand_keyboard())
        elif filter_type == "price":
            await query.edit_message_text("Выбери ценовой диапазон:", reply_markup=filter_price_keyboard())
        elif filter_type == "size":
            await query.edit_message_text("Выбери размер:", reply_markup=filter_size_keyboard())
    elif query.data.startswith("filter_"):
        parts = query.data.split("_")
        filter_category = parts[1]
        filter_value = parts[2]
        
        if filter_category == "brand":
            filtered_items = [item for item in catalog_items if item["brand"] == filter_value]
        elif filter_category == "price":
            min_price, max_price = map(int, [filter_value, parts[3]])
            filtered_items = [item for item in catalog_items if min_price <= item["price"] <= max_price]
        elif filter_category == "size":
            filtered_items = [item for item in catalog_items if filter_value in item["sizes"]]
        
        if not filtered_items:
            await query.edit_message_text("Товаров по этому фильтру не найдено.", reply_markup=main_keyboard())
        else:
            items_text = "\n".join([f"{idx+1}. {item['name']} - {item['price']} руб (Рейтинг: {item['avg_rating']}/5, Отзывов: {item['review_count']})" for idx, item in enumerate(filtered_items)])
            await query.edit_message_text(f"Отфильтрованный каталог:\n{items_text}", reply_markup=catalog_keyboard(filtered_items))
    elif query.data.startswith("select_"):
        item_id = query.data.split("_")[1]
        context.user_data["selected_item_id"] = item_id
        if context.user_data.get("admin_mode") == "edit_select":
            await query.edit_message_text("Шаг 1: Введи новое название товара (или 'отмена' для выхода):")
            context.user_data["admin_mode"] = "edit_name"
            context.user_data["new_item"] = {}
        elif context.user_data.get("admin_mode") == "delete":
            conn = psycopg2.connect(**DB_PARAMS)
            c = conn.cursor()
            c.execute("SELECT name FROM items WHERE id = %s", (item_id,))
            item_name = c.fetchone()[0]
            c.execute("DELETE FROM items WHERE id = %s", (item_id,))
            conn.commit()
            conn.close()
            update_catalog()  # Обновляем каталог
            await query.edit_message_text(f"Товар '{item_name}' удалён.", reply_markup=main_keyboard())
            context.user_data["admin_mode"] = None
    elif query.data.startswith("review_"):
        item_id = query.data.split("_")[1]
        user_id = str(update.effective_user.id)
        item = next((i for i in catalog_items if i["id"] == int(item_id)), None)
        if item:
            if not has_purchased(user_id, item["name"]):
                await query.edit_message_text("Вы можете оставить рейтинг только на купленные товары!", reply_markup=main_keyboard())
            elif has_reviewed(user_id, item_id):
                await query.edit_message_text("Вы уже оставили рейтинг для этого товара!", reply_markup=main_keyboard())
            else:
                context.user_data["review_item_id"] = item_id
                await query.edit_message_text(f"Оставь рейтинг для '{item['name']}':\nВведи число от 1 до 5")
                context.user_data["review_mode"] = "input"
        context.user_data.pop("admin_mode", None)

# Команда /filters (или кнопка "Фильтры")
async def filters_command(update: Update, context):
    await update.message.reply_text("Выбери тип фильтра:", reply_markup=filter_type_keyboard())

# Команда /cart (или кнопка "Корзина")
async def cart(update: Update, context):
    if "cart" not in context.user_data or not context.user_data["cart"]:
        await update.message.reply_text("Ваша корзина пуста. Добавь товары через 'Каталог'!", reply_markup=main_keyboard())
    else:
        cart_items = context.user_data["cart"]
        total_sum = sum(prices.get(item.split(" (")[0], 0) for item in cart_items)
        cart_text = "\n".join([f"{item} - {prices.get(item.split(' (')[0], 0)} руб" for item in cart_items])
        await update.message.reply_text(f"Ваша корзина:\n{cart_text}\nИтого: {total_sum} руб", reply_markup=cart_keyboard())

# Команда /order (оформление заказа из корзины)
async def order(update: Update, context):
    if "cart" not in context.user_data or not context.user_data["cart"]:
        await update.message.reply_text("Корзина пуста! Добавь товары через 'Каталог'.", reply_markup=main_keyboard())
    else:
        context.bot_data["orders"] = context.bot_data.get("orders", 0) + 1
        await update.message.reply_text("Напиши свой адрес доставки в ответное сообщение.", reply_markup=main_keyboard())

# Команда /clear (или кнопка "Очистить корзину")
async def clear(update: Update, context):
    context.user_data["cart"] = []
    await update.message.reply_text("Корзина очищена! Добавь новые товары через 'Каталог'.", reply_markup=main_keyboard())

# Команда /discounts (или кнопка "Скидки")
async def discounts(update: Update, context):
    await update.message.reply_text(
        "Скидки сегодня:\nNike Air Max - 10000 руб (старая цена: 12000 руб)\nПроверь 'Каталог'!",
        reply_markup=main_keyboard()
    )

# Обработка текстовых сообщений и фото (адрес доставки, кнопки, поиск и админ-команды)
async def handle_message(update: Update, context):
    text = update.message.text if update.message.text else None
    photos = update.message.photo if update.message.photo else None  # Получаем все фото из сообщения
    admin_id = "508884860"
    
    if text == "Каталог":
        await catalog(update, context)
    elif text == "Корзина":
        await cart(update, context)
    elif text == "Фильтры":
        await filters_command(update, context)
    elif text == "Поиск":
        await search(update, context)
    elif text == "Скидки":
        await discounts(update, context)
    elif text == "Подписаться":
        await subscribe(update, context)
    elif text == "Отписаться":
        await unsubscribe(update, context)
    elif text == "Оставить рейтинг":
        await review(update, context)
    elif text == "Отзывы":
        await reviews(update, context)
    elif text == "Очистить корзину":
        await clear(update, context)
    elif context.user_data.get("search_mode"):
        query = text.lower()
        filtered_items = [item for item in catalog_items if query in item["name"].lower() or query in item["brand"].lower() or query in str(item["price"]) or query in ",".join(item["sizes"])]
        if filtered_items:
            items_text = "\n".join([f"{item['name']} - {item['price']} руб (Рейтинг: {item['avg_rating']}/5, Отзывов: {item['review_count']})" for item in filtered_items])
            await update.message.reply_text(f"Результаты поиска:\n{items_text}", reply_markup=catalog_keyboard(filtered_items))
        else:
            await update.message.reply_text("Ничего не найдено.", reply_markup=main_keyboard())
        context.user_data["search_mode"] = False
    elif context.user_data.get("notify_mode") == "text" and str(update.message.from_user.id) == admin_id:
        if text.lower() == "отмена":
            context.user_data["notify_mode"] = False
            context.user_data.pop("notify_text", None)
            context.user_data.pop("notify_photos", None)
            await update.message.reply_text("Отправка уведомления отменена.", reply_markup=main_keyboard())
        else:
            context.user_data["notify_text"] = text
            await update.message.reply_text("Теперь отправь фото для уведомления (можно несколько). Когда закончишь, напиши 'отправить'. Если не хочешь отправлять фото, напиши 'без фото'.")
            context.user_data["notify_mode"] = "collecting_photos"
    elif context.user_data.get("notify_mode") == "collecting_photos" and str(update.message.from_user.id) == admin_id:
        if photos:
            new_photos = [photo.file_id for photo in photos if photo.file_id not in context.user_data["notify_photos"]]
            context.user_data["notify_photos"].extend(new_photos)
            await update.message.reply_text(f"Фото добавлено. Всего: {len(context.user_data['notify_photos'])}. Отправь ещё или напиши 'отправить'.")
        elif text and text.lower() == "отправить":
            subscribers = get_subscribers()
            notify_text = context.user_data["notify_text"]
            notify_photos = context.user_data["notify_photos"]
            if notify_photos:
                media = [InputMediaPhoto(media=photo, caption=notify_text if i == 0 else None) for i, photo in enumerate(notify_photos)]
                for user_id in subscribers:
                    try:
                        await context.bot.send_media_group(chat_id=user_id, media=media)
                    except Exception as e:
                        print(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                await update.message.reply_text(f"Уведомление с {len(notify_photos)} фото отправлено {len(subscribers)} подписчикам!", reply_markup=main_keyboard())
            else:
                for user_id in subscribers:
                    try:
                        await context.bot.send_message(chat_id=user_id, text=notify_text)
                    except Exception as e:
                        print(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                await update.message.reply_text(f"Уведомление без фото отправлено {len(subscribers)} подписчикам!", reply_markup=main_keyboard())
            context.user_data["notify_mode"] = False
            context.user_data.pop("notify_text", None)
            context.user_data.pop("notify_photos", None)
        elif text and text.lower() == "без фото":
            subscribers = get_subscribers()
            notify_text = context.user_data["notify_text"]
            for user_id in subscribers:
                try:
                    await context.bot.send_message(chat_id=user_id, text=notify_text)
                except Exception as e:
                    print(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
            await update.message.reply_text(f"Уведомление без фото отправлено {len(subscribers)} подписчикам!", reply_markup=main_keyboard())
            context.user_data["notify_mode"] = False
            context.user_data.pop("notify_text", None)
            context.user_data.pop("notify_photos", None)
    elif context.user_data.get("admin_mode") and str(update.message.from_user.id) == admin_id:
        mode = context.user_data["admin_mode"]
        if mode in ["add_name", "edit_name", "add_brand", "edit_brand", "add_price", "edit_price", "add_sizes", "edit_sizes", "add_photo", "edit_photo"] and text.lower() == "отмена":
            context.user_data["admin_mode"] = None
            context.user_data.pop("new_item", None)
            await update.message.reply_text("Процесс отменён.", reply_markup=main_keyboard())
            return
        if mode == "add_name" and text:
            context.user_data["new_item"]["name"] = text
            await update.message.reply_text("Шаг 2: Введи бренд товара (или 'отмена' для выхода):")
            context.user_data["admin_mode"] = "add_brand"
        elif mode == "add_brand" and text:
            context.user_data["new_item"]["brand"] = text
            await update.message.reply_text("Шаг 3: Введи цену товара (целое число):")
            context.user_data["admin_mode"] = "add_price"
        elif mode == "add_price" and text:
            try:
                price = int(text)
                context.user_data["new_item"]["price"] = price
                await update.message.reply_text("Шаг 4: Введи размеры через запятую (например, 40,41,42):")
                context.user_data["admin_mode"] = "add_sizes"
            except ValueError:
                await update.message.reply_text("Ошибка: Цена должна быть числом. Попробуй снова:")
        elif mode == "add_sizes" and text:
            sizes = text.split(",")
            context.user_data["new_item"]["sizes"] = [size.strip() for size in sizes]
            await update.message.reply_text("Шаг 5: Введи ссылки на фото товара через запятую (например, url1,url2,url3):")
            context.user_data["admin_mode"] = "add_photo"
        elif mode == "add_photo" and text:
            context.user_data["new_item"]["photo"] = text  # Сохраняем строку с несколькими URL
            new_item = context.user_data["new_item"]
            conn = psycopg2.connect(**DB_PARAMS)
            c = conn.cursor()
            c.execute("INSERT INTO items (name, brand, price, sizes, photo) VALUES (%s, %s, %s, %s, %s)",
                      (new_item["name"], new_item["brand"], new_item["price"], ",".join(new_item["sizes"]), new_item["photo"]))
            conn.commit()
            conn.close()
            update_catalog()  # Обновляем каталог
            # Отправляем уведомление подписчикам с несколькими фото в одном сообщении
            subscribers = get_subscribers()
            notification = f"Новинка в каталоге!\n{new_item['name']} ({new_item['brand']}) - {new_item['price']} руб\nРазмеры: {', '.join(new_item['sizes'])}"
            for user_id in subscribers:
                try:
                    if new_item["photo"]:
                        media = [InputMediaPhoto(media=photo_url.strip(), caption=notification if i == 0 else None) 
                                 for i, photo_url in enumerate(new_item["photo"].split(","))]
                        await context.bot.send_media_group(chat_id=user_id, media=media)
                    else:
                        await context.bot.send_message(chat_id=user_id, text=notification)
                except Exception as e:
                    print(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
            await update.message.reply_text(f"Товар '{new_item['name']}' добавлен в каталог и уведомление с фото отправлено {len(subscribers)} подписчикам!", reply_markup=main_keyboard())
            context.user_data["admin_mode"] = None
            context.user_data["new_item"] = {}
        elif mode == "edit_name" and text:
            context.user_data["new_item"]["name"] = text
            await update.message.reply_text("Шаг 2: Введи новый бренд товара (или 'отмена' для выхода):")
            context.user_data["admin_mode"] = "edit_brand"
        elif mode == "edit_brand" and text:
            context.user_data["new_item"]["brand"] = text
            await update.message.reply_text("Шаг 3: Введи новую цену товара (целое число):")
            context.user_data["admin_mode"] = "edit_price"
        elif mode == "edit_price" and text:
            try:
                price = int(text)
                context.user_data["new_item"]["price"] = price
                await update.message.reply_text("Шаг 4: Введи новые размеры через запятую (например, 40,41,42):")
                context.user_data["admin_mode"] = "edit_sizes"
            except ValueError:
                await update.message.reply_text("Ошибка: Цена должна быть числом. Попробуй снова:")
        elif mode == "edit_sizes" and text:
            sizes = text.split(",")
            context.user_data["new_item"]["sizes"] = [size.strip() for size in sizes]
            await update.message.reply_text("Шаг 5: Введи новые ссылки на фото товара через запятую (например, url1,url2,url3):")
            context.user_data["admin_mode"] = "edit_photo"
        elif mode == "edit_photo" and text:
            context.user_data["new_item"]["photo"] = text  # Сохраняем строку с несколькими URL
            item_id = int(context.user_data["selected_item_id"])
            new_item = context.user_data["new_item"]
            conn = psycopg2.connect(**DB_PARAMS)
            c = conn.cursor()
            c.execute("UPDATE items SET name=%s, brand=%s, price=%s, sizes=%s, photo=%s WHERE id=%s",
                      (new_item["name"], new_item["brand"], new_item["price"], ",".join(new_item["sizes"]), new_item["photo"], item_id))
            conn.commit()
            conn.close()
            update_catalog()  # Обновляем каталог
            await update.message.reply_text(f"Товар '{new_item['name']}' обновлён!", reply_markup=main_keyboard())
            context.user_data["admin_mode"] = None
            context.user_data["new_item"] = {}
    elif context.user_data.get("review_mode") == "input" and text:
        user_id = str(update.effective_user.id)
        item_id = context.user_data["review_item_id"]
        item = next((i for i in catalog_items if i["id"] == int(item_id)), None)
        try:
            rating = int(text)
            if 1 <= rating <= 5:
                conn = psycopg2.connect(**DB_PARAMS)
                c = conn.cursor()
                c.execute("INSERT INTO reviews (user_id, item_id, rating) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                          (user_id, item_id, rating))
                conn.commit()
                conn.close()
                update_catalog()  # Обновляем каталог с новым рейтингом
                await update.message.reply_text(f"Спасибо! Ваш рейтинг {rating}/5 для '{item['name']}' сохранён.", reply_markup=main_keyboard())
            else:
                await update.message.reply_text("Рейтинг должен быть от 1 до 5. Попробуй снова:", reply_markup=main_keyboard())
        except ValueError:
            await update.message.reply_text("Неверный формат. Введи число от 1 до 5.", reply_markup=main_keyboard())
        context.user_data["review_mode"] = None
        context.user_data.pop("review_item_id", None)
    elif "cart" in context.user_data and context.user_data["cart"] and text:
        cart_items = context.user_data["cart"]
        total_sum = sum(prices.get(item.split(" (")[0], 0) for item in cart_items)
        cart_text = "\n".join(f"{item} - {prices.get(item.split(' (')[0], 0)} руб" for item in cart_items)
        user_id = str(update.effective_user.id)
        conn = psycopg2.connect(**DB_PARAMS)
        c = conn.cursor()
        for item in cart_items:
            item_name = item.split(" (")[0]
            size = item.split("размер ")[1].rstrip(")")
            c.execute("INSERT INTO orders (user_id, item_name, size, address) VALUES (%s, %s, %s, %s)",
                      (user_id, item_name, size, text))
        conn.commit()
        conn.close()
        order_details = f"Новый заказ!\nТовары:\n{cart_text}\nИтого: {total_sum} руб\nАдрес доставки: {text}\nОт пользователя: {update.message.from_user.username or update.message.from_user.id}"
        try:
            await context.bot.send_message(chat_id="508884860", text=order_details)
            print("Сообщение отправлено администратору в личку.")
        except Exception as e:
            print(f"Ошибка при отправке: {e}")
        await update.message.reply_text(
            f"Отлично! Заказ оформлен.\nТовары:\n{cart_text}\nИтого: {total_sum} руб\nАдрес доставки: {text}. Скоро свяжемся!\n\nСпасибо за покупку! Не забудьте оставить рейтинг в боте и поделиться отзывом в нашем канале: https://t.me/ArtShop38Reviews",
            reply_markup=main_keyboard()
        )
        context.user_data["cart"] = []
    elif context.user_data.get("last_item") and text:
        item = context.user_data["last_item"]
        price = prices.get(item.split(" (")[0], 0)
        user_id = str(update.effective_user.id)
        item_name = item.split(" (")[0]
        size = item.split("размер ")[1].rstrip(")")
        conn = psycopg2.connect(**DB_PARAMS)
        c = conn.cursor()
        c.execute("INSERT INTO orders (user_id, item_name, size, address) VALUES (%s, %s, %s, %s)",
                  (user_id, item_name, size, text))
        conn.commit()
        conn.close()
        order_details = f"Новый заказ!\nТовар: {item}\nЦена: {price} руб\nАдрес доставки: {text}\nОт пользователя: {update.message.from_user.username or update.message.from_user.id}"
        try:
            await context.bot.send_message(chat_id="508884860", text=order_details)
            print("Сообщение отправлено администратору в личку.")
        except Exception as e:
            print(f"Ошибка при отправке: {e}")
        await update.message.reply_text(
            f"Отлично! Заказ оформлен.\nТовар: {item}\nЦена: {price} руб\nАдрес доставки: {text}. Скоро свяжемся!\n\nСпасибо за покупку! Не забудьте оставить рейтинг в боте и поделиться отзывом в нашем канале: https://t.me/ArtShop38Reviews",
            reply_markup=main_keyboard()
        )
        context.user_data.pop("last_item", None)

def main():
    init_db()  # Инициализируем базу данных при запуске
    global catalog_items, prices
    catalog_items = load_catalog()
    prices = {item["name"]: item["price"] for item in catalog_items}
    application = Application.builder().token("7958438650:AAHZkqJiFdggP9N6D9XKeQ-K2tpeOOTOnoo").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("cart", cart))
    application.add_handler(CommandHandler("order", order))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("discounts", discounts))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("filters", filters_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("add_item", add_item))
    application.add_handler(CommandHandler("edit_item", edit_item))
    application.add_handler(CommandHandler("delete_item", delete_item))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("notify", notify))
    application.add_handler(CommandHandler("review", review))
    application.add_handler(CommandHandler("reviews", reviews))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))  # Обрабатываем текст и фото
    application.run_polling()

if __name__ == "__main__":
    main()

# Глобальные переменные для каталога
catalog_items = load_catalog()
prices = {item["name"]: item["price"] for item in catalog_items}

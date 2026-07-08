# -*- coding: utf-8 -*-
"""
Модуль handlers.py
Обработчики команд Telegram-бота: /start, /calories, /add, /menu,
/stat, /reset, /profile, /recipes, а также обработка текстовых сообщений
и нажатий на inline-кнопки.
"""

import json
import os
import random
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import PRODUCTS, RECIPES, UNIT_WEIGHTS, DEFAULT_PORTION_WEIGHT, find_product, get_recipes_by_category
from calculator import calculate_daily_calories, parse_quantity, calc_nutrition

# ==========================================================================
# ХРАНЕНИЕ ДАННЫХ
# ==========================================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE = os.path.join(DATA_DIR, "users.json")

# Состояния для ConversationHandler (анкета профиля)
ASK_GENDER, ASK_AGE, ASK_WEIGHT, ASK_HEIGHT, ASK_GOAL = range(5)


def load_data() -> dict:
    """Загружает данные всех пользователей из JSON-файла."""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return {}


def save_data(data: dict) -> None:
    """Сохраняет данные всех пользователей в JSON-файл."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(data: dict, user_id: str) -> dict:
    """Возвращает запись пользователя, создавая её при необходимости."""
    if user_id not in data:
        data[user_id] = {
            "profile": None,   # {"gender":..., "age":..., "weight":..., "height":..., "goal":...}
            "log": {}          # {"2026-07-08": [{"name":..., "grams":..., "kcal":..., ...}, ...]}
        }
    return data[user_id]


def today_str() -> str:
    """Возвращает сегодняшнюю дату в виде строки YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


# ==========================================================================
# /start
# ==========================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие и предложение заполнить профиль."""
    text = (
        "👋 Привет! Я бот для подсчёта калорий и рекомендаций ПП-питания.\n\n"
        "Что я умею:\n"
        "/calories — суточная норма калорий и сколько уже съедено сегодня\n"
        "/add <блюдо> — добавить приём пищи, например: /add куриная грудка 200г\n"
        "/menu — случайное ПП-меню на день\n"
        "/stat — статистика за 7 дней\n"
        "/reset — сбросить данные за сегодня\n"
        "/profile — посмотреть и изменить профиль\n"
        "/recipes — список ПП-рецептов с КБЖУ\n\n"
        "Для расчёта нормы калорий мне нужны данные о тебе. Давай заполним профиль!"
    )
    await update.message.reply_text(text)
    await profile_start(update, context)


# ==========================================================================
# ЗАПОЛНЕНИЕ ПРОФИЛЯ (ConversationHandler)
# ==========================================================================

async def profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог заполнения профиля — запрашивает пол."""
    keyboard = [
        [InlineKeyboardButton("Мужской", callback_data="gender_мужской")],
        [InlineKeyboardButton("Женский", callback_data="gender_женский")],
    ]
    await update.message.reply_text(
        "Укажи свой пол:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_GENDER


async def gender_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет выбранный пол и запрашивает возраст."""
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("gender_", "")
    context.user_data["new_profile"] = {"gender": gender}
    await query.edit_message_text(f"Пол: {gender}\n\nТеперь введи свой возраст (полных лет):")
    return ASK_AGE


async def age_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет возраст и запрашивает вес."""
    text = update.message.text.strip().replace(",", ".")
    try:
        age = int(float(text))
        if not (5 <= age <= 120):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи возраст числом (например, 28).")
        return ASK_AGE

    context.user_data["new_profile"]["age"] = age
    await update.message.reply_text("Введи свой вес в кг (например, 65.5):")
    return ASK_WEIGHT


async def weight_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет вес и запрашивает рост."""
    text = update.message.text.strip().replace(",", ".")
    try:
        weight = float(text)
        if not (20 <= weight <= 400):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи вес числом в кг (например, 65.5).")
        return ASK_WEIGHT

    context.user_data["new_profile"]["weight"] = weight
    await update.message.reply_text("Введи свой рост в см (например, 170):")
    return ASK_HEIGHT


async def height_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет рост и предлагает выбрать цель."""
    text = update.message.text.strip().replace(",", ".")
    try:
        height = float(text)
        if not (100 <= height <= 250):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи рост числом в см (например, 170).")
        return ASK_HEIGHT

    context.user_data["new_profile"]["height"] = height

    keyboard = [
        [InlineKeyboardButton("📉 Похудение", callback_data="goal_похудение")],
        [InlineKeyboardButton("⚖️ Поддержание", callback_data="goal_поддержание")],
        [InlineKeyboardButton("📈 Набор массы", callback_data="goal_набор")],
    ]
    await update.message.reply_text(
        "Выбери свою цель:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_GOAL


async def goal_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет цель и завершает заполнение профиля."""
    query = update.callback_query
    await query.answer()
    goal = query.data.replace("goal_", "")
    context.user_data["new_profile"]["goal"] = goal

    user_id = str(query.from_user.id)
    data = load_data()
    user = get_user(data, user_id)
    user["profile"] = context.user_data["new_profile"]
    save_data(data)

    profile = user["profile"]
    norm = calculate_daily_calories(
        profile["gender"], profile["weight"], profile["height"], profile["age"], profile["goal"]
    )

    await query.edit_message_text(
        "✅ Профиль сохранён!\n\n"
        f"Пол: {profile['gender']}\n"
        f"Возраст: {profile['age']}\n"
        f"Вес: {profile['weight']} кг\n"
        f"Рост: {profile['height']} см\n"
        f"Цель: {profile['goal']}\n\n"
        f"🔥 Твоя суточная норма калорий: {norm} ккал\n\n"
        "Используй /add чтобы добавлять приёмы пищи и /calories чтобы следить за нормой."
    )
    return ConversationHandler.END


async def profile_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена заполнения профиля."""
    await update.message.reply_text("Заполнение профиля отменено. Вернуться можно командой /profile.")
    return ConversationHandler.END


# ==========================================================================
# /profile — показать и изменить профиль
# ==========================================================================

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий профиль пользователя с кнопкой изменения."""
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(data, user_id)
    save_data(data)

    profile = user.get("profile")
    keyboard = [[InlineKeyboardButton("✏️ Изменить профиль", callback_data="edit_profile")]]

    if not profile:
        await update.message.reply_text(
            "Профиль ещё не заполнен. Нажми кнопку ниже, чтобы заполнить его.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    norm = calculate_daily_calories(
        profile["gender"], profile["weight"], profile["height"], profile["age"], profile["goal"]
    )
    text = (
        "👤 Твой профиль:\n\n"
        f"Пол: {profile['gender']}\n"
        f"Возраст: {profile['age']}\n"
        f"Вес: {profile['weight']} кг\n"
        f"Рост: {profile['height']} см\n"
        f"Цель: {profile['goal']}\n\n"
        f"🔥 Суточная норма: {norm} ккал"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def edit_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запускает повторное заполнение профиля по кнопке."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Мужской", callback_data="gender_мужской")],
        [InlineKeyboardButton("Женский", callback_data="gender_женский")],
    ]
    await query.edit_message_text("Укажи свой пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_GENDER


# ==========================================================================
# /calories — суточная норма и сколько уже съедено
# ==========================================================================

async def calories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает суточную норму калорий и текущее потребление за сегодня."""
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(data, user_id)
    save_data(data)

    profile = user.get("profile")
    if not profile:
        await update.message.reply_text(
            "Сначала заполни профиль командой /profile, чтобы я мог рассчитать твою норму калорий."
        )
        return

    norm = calculate_daily_calories(
        profile["gender"], profile["weight"], profile["height"], profile["age"], profile["goal"]
    )

    today_log = user["log"].get(today_str(), [])
    eaten = sum(item["kcal"] for item in today_log)
    remaining = norm - eaten

    protein_total = sum(item.get("protein", 0) for item in today_log)
    fat_total = sum(item.get("fat", 0) for item in today_log)
    carbs_total = sum(item.get("carbs", 0) for item in today_log)

    status = "✅ в пределах нормы" if remaining >= 0 else "⚠️ норма превышена"

    text = (
        f"🔥 Суточная норма: {norm} ккал\n"
        f"🍽 Съедено сегодня: {eaten} ккал\n"
        f"➖ Остаток: {remaining} ккал ({status})\n\n"
        f"БЖУ за сегодня: белки {protein_total:.1f}г, жиры {fat_total:.1f}г, углеводы {carbs_total:.1f}г"
    )
    await update.message.reply_text(text)


# ==========================================================================
# /add — добавить приём пищи
# ==========================================================================

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Добавляет приём пищи в лог пользователя.
    Пример использования: /add куриная грудка 200г
    """
    if not context.args:
        await update.message.reply_text(
            "Укажи, что съел. Например:\n/add куриная грудка 200г\n/add банан 1 штука"
        )
        return

    query_text = " ".join(context.args)
    name_part, amount, unit = parse_quantity(query_text)

    if not name_part:
        await update.message.reply_text("Не удалось распознать название продукта. Попробуй ещё раз.")
        return

    found_name, product_data = find_product(name_part)

    if found_name is None:
        # Продукт не найден — предлагаем похожие варианты
        if product_data:  # это список похожих названий
            suggestions = "\n".join(f"• {p}" for p in product_data)
            await update.message.reply_text(
                f"Продукт «{name_part}» не найден в базе 😕\n\nВозможно, вы имели в виду:\n{suggestions}\n\n"
                "Попробуй повторить команду с одним из этих названий."
            )
        else:
            await update.message.reply_text(
                f"Продукт «{name_part}» не найден в базе, и похожих вариантов не нашлось. "
                "Попробуй использовать /recipes чтобы увидеть список известных блюд."
            )
        return

    # Переводим количество в граммы в зависимости от единицы измерения
    if unit == "грамм":
        grams = amount
    elif unit == "штук":
        unit_weight = UNIT_WEIGHTS.get(found_name, DEFAULT_PORTION_WEIGHT)
        grams = amount * unit_weight
    elif unit == "порция":
        grams = amount * DEFAULT_PORTION_WEIGHT
    else:
        grams = amount

    nutrition = calc_nutrition(product_data, grams)

    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(data, user_id)

    day = today_str()
    if day not in user["log"]:
        user["log"][day] = []

    entry = {
        "name": found_name,
        "grams": grams,
        "kcal": nutrition["kcal"],
        "protein": nutrition["protein"],
        "fat": nutrition["fat"],
        "carbs": nutrition["carbs"],
        "time": datetime.now().strftime("%H:%M"),
    }
    user["log"][day].append(entry)
    save_data(data)

    await update.message.reply_text(
        f"✅ Добавлено: {found_name} — {grams:.0f}г\n"
        f"🔥 {nutrition['kcal']} ккал | Б: {nutrition['protein']}г Ж: {nutrition['fat']}г У: {nutrition['carbs']}г"
    )


# ==========================================================================
# /menu — случайное ПП-меню на день
# ==========================================================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формирует случайное ПП-меню на день из базы рецептов."""
    breakfast = random.choice(get_recipes_by_category("завтрак"))
    lunch = random.choice(get_recipes_by_category("обед"))
    dinner = random.choice(get_recipes_by_category("ужин"))
    snack = random.choice(get_recipes_by_category("перекус"))

    total_kcal = breakfast["kcal"] + lunch["kcal"] + dinner["kcal"] + snack["kcal"]

    text = (
        "🍽 Твоё ПП-меню на день:\n\n"
        f"🌅 Завтрак: {breakfast['name']} — {breakfast['kcal']} ккал\n"
        f"🍲 Обед: {lunch['name']} — {lunch['kcal']} ккал\n"
        f"🌙 Ужин: {dinner['name']} — {dinner['kcal']} ккал\n"
        f"🍎 Перекус: {snack['name']} — {snack['kcal']} ккал\n\n"
        f"Итого за день: {total_kcal} ккал\n\n"
        "Нажми кнопку ниже, чтобы обновить меню, или используй /recipes для подробностей рецептов."
    )

    keyboard = [[InlineKeyboardButton("🔄 Другое меню", callback_data="regen_menu")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def regen_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновляет меню по нажатию кнопки."""
    query = update.callback_query
    await query.answer()

    breakfast = random.choice(get_recipes_by_category("завтрак"))
    lunch = random.choice(get_recipes_by_category("обед"))
    dinner = random.choice(get_recipes_by_category("ужин"))
    snack = random.choice(get_recipes_by_category("перекус"))

    total_kcal = breakfast["kcal"] + lunch["kcal"] + dinner["kcal"] + snack["kcal"]

    text = (
        "🍽 Твоё ПП-меню на день:\n\n"
        f"🌅 Завтрак: {breakfast['name']} — {breakfast['kcal']} ккал\n"
        f"🍲 Обед: {lunch['name']} — {lunch['kcal']} ккал\n"
        f"🌙 Ужин: {dinner['name']} — {dinner['kcal']} ккал\n"
        f"🍎 Перекус: {snack['name']} — {snack['kcal']} ккал\n\n"
        f"Итого за день: {total_kcal} ккал\n\n"
        "Нажми кнопку ниже, чтобы обновить меню, или используй /recipes для подробностей рецептов."
    )
    keyboard = [[InlineKeyboardButton("🔄 Другое меню", callback_data="regen_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==========================================================================
# /stat — статистика за последние 7 дней
# ==========================================================================

async def stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику потребления калорий за последние 7 дней."""
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(data, user_id)
    save_data(data)

    lines = []
    total = 0
    days_with_data = 0

    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_log = user["log"].get(day, [])
        day_kcal = sum(item["kcal"] for item in day_log)
        if day_log:
            days_with_data += 1
        total += day_kcal
        weekday = (datetime.now() - timedelta(days=i)).strftime("%d.%m")
        lines.append(f"{weekday}: {day_kcal} ккал")

    avg = round(total / days_with_data) if days_with_data else 0

    text = "📊 Статистика за 7 дней:\n\n" + "\n".join(lines)
    text += f"\n\nСреднее за дни с записями: {avg} ккал/день"

    await update.message.reply_text(text)


# ==========================================================================
# /reset — сбросить данные за сегодня
# ==========================================================================

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет записи о приёмах пищи за сегодняшний день."""
    user_id = str(update.effective_user.id)
    data = load_data()
    user = get_user(data, user_id)

    day = today_str()
    had_data = day in user["log"] and len(user["log"][day]) > 0
    user["log"][day] = []
    save_data(data)

    if had_data:
        await update.message.reply_text("🗑 Данные за сегодня сброшены.")
    else:
        await update.message.reply_text("За сегодня и так не было записей.")


# ==========================================================================
# /recipes — список ПП-рецептов
# ==========================================================================

async def recipes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает категории рецептов с кнопками выбора."""
    keyboard = [
        [InlineKeyboardButton("🌅 Завтраки", callback_data="recipes_завтрак")],
        [InlineKeyboardButton("🍲 Обеды", callback_data="recipes_обед")],
        [InlineKeyboardButton("🌙 Ужины", callback_data="recipes_ужин")],
        [InlineKeyboardButton("🍎 Перекусы", callback_data="recipes_перекус")],
    ]
    await update.message.reply_text(
        "Выбери категорию рецептов:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def recipes_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список рецептов выбранной категории с КБЖУ."""
    query = update.callback_query
    await query.answer()
    category = query.data.replace("recipes_", "")
    recipes = get_recipes_by_category(category)

    lines = [f"📖 Рецепты: {category}\n"]
    for r in recipes:
        lines.append(
            f"▪️ {r['name']} — {r['kcal']} ккал (Б:{r['protein']} Ж:{r['fat']} У:{r['carbs']})\n"
            f"   Ингредиенты: {', '.join(r['ingredients'])}\n"
            f"   Рецепт: {r['recipe']}\n"
        )
    text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("⬅️ Назад к категориям", callback_data="recipes_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def recipes_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает к выбору категорий рецептов."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🌅 Завтраки", callback_data="recipes_завтрак")],
        [InlineKeyboardButton("🍲 Обеды", callback_data="recipes_обед")],
        [InlineKeyboardButton("🌙 Ужины", callback_data="recipes_ужин")],
        [InlineKeyboardButton("🍎 Перекусы", callback_data="recipes_перекус")],
    ]
    await query.edit_message_text(
        "Выбери категорию рецептов:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================================================
# Обработка неизвестных команд
# ==========================================================================

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает на неизвестные команды."""
    await update.message.reply_text(
        "Неизвестная команда. Используй /start чтобы увидеть список доступных команд."
    )

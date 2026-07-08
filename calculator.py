# -*- coding: utf-8 -*-
"""
Модуль calculator.py
Формулы расчёта суточной нормы калорий и парсинг количества продукта.
"""

import re

# Коэффициент активности (принимаем "умеренную активность" как единственный уровень в этом боте)
ACTIVITY_MULTIPLIER = 1.55

# Коэффициенты корректировки нормы под цель
GOAL_MULTIPLIERS = {
    "похудение": 0.8,     # -20% от нормы
    "поддержание": 1.0,   # без изменений
    "набор": 1.15,        # +15% от нормы
}


def calculate_bmr(gender: str, weight: float, height: float, age: int) -> float:
    """
    Рассчитывает базовый уровень метаболизма (BMR) по формуле Миффлина-Сан Жеора.

    Женщины: (10 × вес) + (6.25 × рост) - (5 × возраст) - 161
    Мужчины: (10 × вес) + (6.25 × рост) - (5 × возраст) + 5
    """
    base = (10 * weight) + (6.25 * height) - (5 * age)
    if gender == "мужской":
        return base + 5
    else:
        return base - 161


def calculate_daily_calories(gender: str, weight: float, height: float, age: int, goal: str) -> int:
    """
    Рассчитывает суточную норму калорий с учётом уровня активности и цели пользователя.
    """
    bmr = calculate_bmr(gender, weight, height, age)
    tdee = bmr * ACTIVITY_MULTIPLIER  # Total Daily Energy Expenditure — с учётом активности
    multiplier = GOAL_MULTIPLIERS.get(goal, 1.0)
    return round(tdee * multiplier)


# ==========================================================================
# ПАРСИНГ КОЛИЧЕСТВА ПРОДУКТА ИЗ ТЕКСТА
# Поддерживаемые форматы: "200г", "200 г", "200 грамм", "2 штуки", "1 порция"
# ==========================================================================

# Регулярное выражение для веса в граммах: число + (г|гр|грамм...)
_GRAMS_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*(г|гр|грамм|граммов|грамма)\b", re.IGNORECASE)

# Регулярное выражение для количества штук: число + (шт|штук|штуки)
_PIECES_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*(шт|штук|штуки|штука)\b", re.IGNORECASE)

# Регулярное выражение для порций: число + (порция|порции|порций)
_PORTIONS_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*(порция|порции|порций)\b", re.IGNORECASE)

# Просто число в конце строки без единиц измерения — трактуем как граммы
_PLAIN_NUMBER_PATTERN = re.compile(r"(\d+[.,]?\d*)\s*$")


def parse_quantity(text: str):
    """
    Извлекает из текста название продукта и количество в граммах.
    Возвращает кортеж (название_продукта, вес_в_граммах, тип_единицы).
    тип_единицы: "грамм", "штук" или "порция" — используется для дальнейшего пересчёта.

    Если количество не указано явно — возвращает вес по умолчанию 100г.
    """
    text = text.strip()

    # Проверяем граммы
    match = _GRAMS_PATTERN.search(text)
    if match:
        grams = float(match.group(1).replace(",", "."))
        name = text[:match.start()].strip()
        return name, grams, "грамм"

    # Проверяем штуки
    match = _PIECES_PATTERN.search(text)
    if match:
        count = float(match.group(1).replace(",", "."))
        name = text[:match.start()].strip()
        return name, count, "штук"

    # Проверяем порции
    match = _PORTIONS_PATTERN.search(text)
    if match:
        count = float(match.group(1).replace(",", "."))
        name = text[:match.start()].strip()
        return name, count, "порция"

    # Проверяем просто число в конце (трактуем как граммы)
    match = _PLAIN_NUMBER_PATTERN.search(text)
    if match:
        grams = float(match.group(1).replace(",", "."))
        name = text[:match.start()].strip()
        return name, grams, "грамм"

    # Количество не указано — используем 100г по умолчанию
    return text.strip(), 100.0, "грамм"


def calc_nutrition(product_data: dict, grams: float) -> dict:
    """
    Рассчитывает калории и БЖУ для заданного веса продукта (в граммах),
    исходя из данных на 100г.
    """
    factor = grams / 100.0
    return {
        "kcal": round(product_data["kcal"] * factor),
        "protein": round(product_data["protein"] * factor, 1),
        "fat": round(product_data["fat"] * factor, 1),
        "carbs": round(product_data["carbs"] * factor, 1),
    }

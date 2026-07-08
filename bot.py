# -*- coding: utf-8 -*-
"""
bot.py — основной файл запуска Telegram-бота для подсчёта калорий.

Перед запуском укажите токен бота в переменной окружения TELEGRAM_BOT_TOKEN
или впишите его напрямую в переменную BOT_TOKEN ниже.
"""

import logging
import os

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import handlers
from handlers import (
    ASK_GENDER, ASK_AGE, ASK_WEIGHT, ASK_HEIGHT, ASK_GOAL,
    start, profile_start, gender_chosen, age_entered, weight_entered,
    height_entered, goal_chosen, profile_cancel,
    profile_command, edit_profile_callback,
    calories_command, add_command, menu_command, regen_menu_callback,
    stat_command, reset_command,
    recipes_command, recipes_category_callback, recipes_back_callback,
    unknown_command,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Токен бота: сначала пробуем взять из переменной окружения,
# если её нет — используем заглушку (нужно заменить перед запуском)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7981897602:AAFbtyB6m4-YIKtN3YSR0mx5pR4ysA9rq0Y")


def main() -> None:
    """Точка входа: создаёт приложение и регистрирует все обработчики."""

    if not BOT_TOKEN or BOT_TOKEN == "ВСТАВЬТЕ_СЮДА_ТОКЕН_БОТА":
        logger.warning(
            "Токен бота не задан! Установите переменную окружения TELEGRAM_BOT_TOKEN "
            "или впишите токен в файл bot.py перед запуском."
        )

    application = Application.builder().token(BOT_TOKEN).build()

    # ------------------------------------------------------------------
    # ConversationHandler для заполнения/изменения профиля пользователя
    # ------------------------------------------------------------------
    profile_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("profile", profile_command),
            CallbackQueryHandler(edit_profile_callback, pattern="^edit_profile$"),
        ],
        states={
            ASK_GENDER: [CallbackQueryHandler(gender_chosen, pattern="^gender_")],
            ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_entered)],
            ASK_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_entered)],
            ASK_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height_entered)],
            ASK_GOAL: [CallbackQueryHandler(goal_chosen, pattern="^goal_")],
        },
        fallbacks=[CommandHandler("cancel", profile_cancel)],
        # /profile должен по-прежнему нормально показывать профиль, если анкета не запущена
        per_message=False,
    )
    application.add_handler(profile_conversation)

    # ------------------------------------------------------------------
    # Обычные команды
    # ------------------------------------------------------------------
    application.add_handler(CommandHandler("calories", calories_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("stat", stat_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("recipes", recipes_command))

    # ------------------------------------------------------------------
    # Обработчики inline-кнопок
    # ------------------------------------------------------------------
    application.add_handler(CallbackQueryHandler(regen_menu_callback, pattern="^regen_menu$"))
    application.add_handler(CallbackQueryHandler(recipes_category_callback, pattern="^recipes_(завтрак|обед|ужин|перекус)$"))
    application.add_handler(CallbackQueryHandler(recipes_back_callback, pattern="^recipes_back$"))

    # ------------------------------------------------------------------
    # Обработчик неизвестных команд (должен быть последним)
    # ------------------------------------------------------------------
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Бот запущен и готов к работе...")
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()

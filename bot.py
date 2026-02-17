"""
BridgeOS — Multi-bot translation system.
Slim entry point: logging, DB pool, handler registration, run.
"""
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import load_config
from utils.logger import setup_logging
from utils.db_connection import init_connection_pool, close_all_connections

from handlers import LANGUAGE, GENDER, INDUSTRY
from handlers.registration import start, language_selected, gender_selected, industry_selected, cancel
from handlers.commands import help_command, menu_command, menu_callback_handler, resetall_command
from handlers.connections import addworker_command, workers_command
from handlers.tasks import tasks_command, daily_command, task_completion_callback, view_tasks_callback
from handlers.messages import handle_message, handle_media
from handlers.subscriptions import subscription_command, refer_command, feedback_command

logger = logging.getLogger(__name__)


def main():
    """Initialize everything and start polling."""

    # 1. Logging
    setup_logging(level="INFO")
    logger.info("Starting BridgeOS...")

    # 2. Database connection pool
    init_connection_pool(min_conn=1, max_conn=3)

    # 3. Telegram application
    config = load_config()
    app = Application.builder().token(config["telegram_token"]).build()

    # 4. Registration conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
            GENDER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_selected)],
            INDUSTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, industry_selected)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    # 5. Register handlers (order matters — first match wins)

    # Registration flow (must be first so /start is captured by ConversationHandler)
    app.add_handler(conv_handler)

    # Commands
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("resetall", resetall_command))
    app.add_handler(CommandHandler("workers", workers_command))
    app.add_handler(CommandHandler("addworker", addworker_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("subscription", subscription_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("refer", refer_command))

    # Callback queries (inline button presses)
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(task_completion_callback, pattern=r"^task_done_"))
    app.add_handler(CallbackQueryHandler(view_tasks_callback, pattern=r"^view_tasks$"))

    # Text messages (must be after commands so /commands aren't caught here)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Media messages
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO |
        filters.Document.ALL | filters.LOCATION | filters.CONTACT | filters.Sticker.ALL,
        handle_media,
    ))

    # 6. Run
    logger.info("BridgeOS bot is running...")

    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        close_all_connections()
        logger.info("BridgeOS bot stopped.")


if __name__ == "__main__":
    main()

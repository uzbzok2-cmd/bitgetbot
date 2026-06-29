"""
Main Telegram Bot entry point.
- Password auth before any function
- Background trading engine with notifier
- GitHub auto-sync every 30 min
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from config import TELEGRAM_BOT_TOKEN
from handlers.main_menu import start_command, handle_text_message
from handlers.callback_router import callback_router
from services.trading_engine import TradingEngine
from services.bitget_client import BitgetClient
from services.github_sync import initial_push, commit_and_push
from services import state as gs

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/bitgetbot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def run_trading_background(bot):
    """Background: scan markets and auto-trade."""
    client = BitgetClient()
    engine = TradingEngine(client, bot=bot)

    # Store engine in global for permission approvals
    import builtins
    builtins._trading_engine = engine

    logger.info("🤖 Trading engine started")
    gs.scanner.add_log("🚀 Trading engine ishga tushdi")

    await engine.run_futures_scanner()


async def run_github_sync():
    """Push to GitHub every 30 minutes."""
    while True:
        await asyncio.sleep(1800)
        try:
            commit_and_push("🤖 Auto-sync")
            logger.info("GitHub sync done")
            gs.scanner.add_log("📦 GitHub sync done")
        except Exception as e:
            logger.error(f"GitHub sync error: {e}")


async def post_init(application):
    """Launch background tasks after bot starts."""
    loop = asyncio.get_event_loop()
    loop.create_task(run_trading_background(application.bot))
    loop.create_task(run_github_sync())

    # Store engine reference in bot_data for callback handlers
    logger.info("✅ Background tasks started")
    gs.scanner.add_log("✅ Background tasks ishga tushdi")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    logger.info("🚀 Starting BitgetBot AI Trading v2.0...")

    try:
        initial_push()
        logger.info("✅ GitHub initial push done")
    except Exception as e:
        logger.warning(f"GitHub initial push error: {e}")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Store engine reference for callback handlers
    app.bot_data["engine"] = None  # will be set in post_init

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu",  start_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    # All text messages go through auth + routing
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("✅ Handlers registered, starting polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

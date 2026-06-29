"""
Main Telegram Bot entry point.
Runs bot polling + background trading engine.
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
from handlers.main_menu import start_command
from handlers.callback_router import callback_router
from services.trading_engine import TradingEngine
from services.bitget_client import BitgetClient
from services.github_sync import initial_push, commit_and_push

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/bitgetbot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


async def handle_unknown(update: Update, context):
    if update.message:
        await update.message.reply_text(
            "❓ Bu buyruq tanilmadi.\n/start ni bosing yoki button ishlatib navigatsiya qiling.",
            parse_mode="HTML"
        )


async def notify_new_trade(bot, chat_id: int):
    """Create a notifier function that sends trade alerts to user."""
    async def notifier(signal, leverage, size, margin, tp1, tp2, sl, order_id=""):
        from utils.formatters import format_new_futures_order_notification
        text = format_new_futures_order_notification(
            signal=signal,
            leverage=leverage,
            size=size,
            margin=margin,
            tp1=tp1,
            tp2=tp2,
            sl=sl,
            order_id=order_id
        )
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Notify error: {e}")
    return notifier


async def run_trading_background(application):
    """Background task: scan markets and auto-trade."""
    client = BitgetClient()
    notifier_chat_id = None

    # Wait for first user interaction to get chat_id
    engine = TradingEngine(client, notifier=None)

    logger.info("🤖 Trading engine started — scanning every 5 minutes")

    # Run futures and spot scanners concurrently
    await asyncio.gather(
        engine.run_futures_scanner(),
        engine.run_spot_scanner(),
    )


async def run_github_sync():
    """Push code to GitHub every 30 minutes."""
    while True:
        try:
            commit_and_push("🤖 Auto-sync — bot running")
            logger.info("GitHub sync done")
        except Exception as e:
            logger.error(f"GitHub sync error: {e}")
        await asyncio.sleep(1800)  # 30 minutes


async def post_init(application):
    """Called after bot starts — launch background tasks."""
    loop = asyncio.get_event_loop()

    # Start trading engine in background
    loop.create_task(run_trading_background(application))
    # Start GitHub sync
    loop.create_task(run_github_sync())

    logger.info("✅ Background tasks started")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    logger.info("🚀 Starting BitgetBot AI Trading...")

    # Initial GitHub push
    try:
        initial_push()
        logger.info("✅ Initial GitHub push done")
    except Exception as e:
        logger.warning(f"GitHub initial push error: {e}")

    # Build application
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    logger.info("✅ Handlers registered, starting polling...")

    # Run bot
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

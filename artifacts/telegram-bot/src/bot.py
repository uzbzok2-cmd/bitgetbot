"""
Main Telegram Bot entry point.
- Password auth before any function
- Background trading engine with notifier
- Zocker signal scanner (6-7 consecutive candles)
- GitHub auto-sync every 30 min
- Health check HTTP server (port 10000) for Render Web Service
"""
import asyncio
import logging
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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

    import builtins
    builtins._trading_engine = engine

    logger.info("🤖 Trading engine started")
    gs.scanner.add_log("🚀 Trading engine ishga tushdi")

    await engine.run_futures_scanner()


async def run_zocker_scanner(bot):
    """Background: Zocker signal — 6-7 ketma-ket shamlar."""
    await asyncio.sleep(15)  # Trading engine ishga tushguncha kutamiz
    try:
        from handlers.zocker_signal import ZockerScanner
        client = BitgetClient()
        scanner = ZockerScanner(client, bot=bot)
        logger.info("🕯️ Zocker scanner started")
        gs.scanner.add_log("🕯️ Zocker scanner ishga tushdi")
        await scanner.run()
    except Exception as e:
        logger.error(f"Zocker scanner error: {e}")


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


async def run_zokpat_scanner(bot):
    """Background: ZOKPAT pattern signal — chart patterns."""
    await asyncio.sleep(25)  # Trading engine + Zocker ishga tushguncha kutamiz
    try:
        from handlers.zokpat_scanner import ZokpatScanner
        client = BitgetClient()
        scanner = ZokpatScanner(client, bot=bot)
        import builtins
        builtins._zokpat_scanner = scanner
        logger.info("🔮 ZOKPAT scanner started")
        gs.scanner.add_log("🔮 ZOKPAT scanner ishga tushdi")
        await scanner.run()
    except Exception as e:
        logger.error(f"ZOKPAT scanner error: {e}")


async def post_init(application):
    """Launch background tasks after bot starts."""
    loop = asyncio.get_event_loop()
    loop.create_task(run_trading_background(application.bot))
    loop.create_task(run_zocker_scanner(application.bot))
    loop.create_task(run_zokpat_scanner(application.bot))
    loop.create_task(run_github_sync())
    loop.create_task(_set_tp_sl_on_startup(application.bot))

    logger.info("✅ Background tasks started")
    gs.scanner.add_log("✅ Background tasks ishga tushdi")


async def _set_tp_sl_on_startup(bot):
    """Startup da mavjud pozitsiyalarga TP/SL qo'y."""
    await asyncio.sleep(5)
    try:
        client = BitgetClient()
        engine = TradingEngine(client, bot=bot)
        logger.info("🎯 Mavjud pozitsiyalarga TP/SL qo'yilmoqda...")
        await engine.set_tp_sl_for_existing_positions()
    except Exception as e:
        logger.error(f"Startup TP/SL xato: {e}")


def _start_health_server():
    """Render Web Service uchun health check HTTP server (port 10000)."""
    port = int(os.environ.get("PORT", 10000))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"BitgetBot OK")
        def log_message(self, *args):
            pass  # HTTP loglarni susturish

    try:
        server = HTTPServer(("0.0.0.0", port), _Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info(f"✅ Health check server started on port {port}")
    except Exception as e:
        logger.warning(f"Health server error: {e}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    _start_health_server()
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

    app.bot_data["engine"] = None

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu",  start_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("✅ Handlers registered, starting polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

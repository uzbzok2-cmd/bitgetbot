"""Central callback router."""
from telegram import Update
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.main_menu import handle_main_menu, handle_bot_status, handle_about
from handlers.futures_handlers import (
    show_futures_main, handle_futures_balance, handle_futures_positions,
    handle_futures_open_orders, handle_futures_tpsl,
    handle_futures_history_menu, handle_futures_history, handle_futures_signals,
)
from handlers.spot_handlers import (
    show_spot_main, handle_spot_balance, handle_spot_assets,
    handle_spot_open_orders, handle_spot_history_menu, handle_spot_history,
)
from handlers.trading_status import (
    handle_trading_status, handle_toggle_autotrade,
    handle_approve_signal, handle_reject_signal,
    handle_signal_history, handle_signal_history_all,
)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data or ""

    # ── Main ──────────────────────────────────────────────
    if data == "main_menu":
        await handle_main_menu(update, context)
    elif data == "about":
        await handle_about(update, context)
    elif data in ("bot_status",):
        await handle_bot_status(update, context)

    # ── Futures ───────────────────────────────────────────
    elif data in ("section_futures", "fut_main", "fut_refresh"):
        await show_futures_main(update, context)
    elif data == "fut_balance":
        await handle_futures_balance(update, context)
    elif data == "fut_positions":
        await handle_futures_positions(update, context)
    elif data == "fut_open_orders":
        await handle_futures_open_orders(update, context)
    elif data == "fut_tpsl":
        await handle_futures_tpsl(update, context)
    elif data == "fut_history":
        await handle_futures_history_menu(update, context)
    elif data == "fut_hist_today":
        await handle_futures_history(update, context, "today")
    elif data == "fut_hist_7d":
        await handle_futures_history(update, context, "7d")
    elif data == "fut_hist_30d":
        await handle_futures_history(update, context, "30d")
    elif data == "fut_hist_all":
        await handle_futures_history(update, context, "all")
    elif data == "fut_signals":
        await handle_futures_signals(update, context)

    # ── Spot ──────────────────────────────────────────────
    elif data in ("section_spot", "spot_main", "spot_refresh"):
        await show_spot_main(update, context)
    elif data == "spot_balance":
        await handle_spot_balance(update, context)
    elif data == "spot_assets":
        await handle_spot_assets(update, context)
    elif data == "spot_open_orders":
        await handle_spot_open_orders(update, context)
    elif data == "spot_history":
        await handle_spot_history_menu(update, context)
    elif data == "spot_hist_today":
        await handle_spot_history(update, context, "today")
    elif data == "spot_hist_7d":
        await handle_spot_history(update, context, "7d")
    elif data == "spot_hist_30d":
        await handle_spot_history(update, context, "30d")
    elif data == "spot_hist_all":
        await handle_spot_history(update, context, "all")

    # ── Trading status & auto-trade toggle ────────────────
    elif data == "trading_status":
        await handle_trading_status(update, context)
    elif data == "toggle_autotrade":
        await handle_toggle_autotrade(update, context)

    # ── Signal history ────────────────────────────────────
    elif data == "sig_hist_today":
        await handle_signal_history(update, context)
    elif data == "sig_hist_all":
        await handle_signal_history_all(update, context)

    # ── Permission approve/reject ─────────────────────────
    elif data.startswith("approve_"):
        key = data[len("approve_"):]
        await handle_approve_signal(update, context, key)
    elif data.startswith("reject_"):
        key = data[len("reject_"):]
        await handle_reject_signal(update, context, key)

    else:
        await query.answer(f"⚠️ Noma'lum: {data[:30]}")

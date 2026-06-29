"""Statistika bo'limi — 1 kun, 7 kun, 30 kunlik savdo natijalari."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import format_statistics

client = BitgetClient()


def _get_orders(start_ms: int, end_ms: int) -> list:
    data = client.get_futures_order_history(
        start_time=str(start_ms), end_time=str(end_ms), limit=200
    )
    if data.get("code") == "00000":
        d = data.get("data", {})
        return d.get("entrustedList", d.get("orderList", [])) if isinstance(d, dict) else (d or [])
    return []


def _get_equity() -> float:
    try:
        d = client.get_futures_account()
        if d.get("code") == "00000":
            return safe_float(d["data"].get("usdtEquity", 0))
    except Exception:
        pass
    return 0.0


def stats_keyboard(active: str = "1d"):
    periods = [("📅 1 Kun", "stats_1d"), ("📆 7 Kun", "stats_7d"), ("🗓️ 30 Kun", "stats_30d")]
    row1 = []
    for label, cb in periods:
        btn_label = f"✅ {label}" if cb == f"stats_{active}" else label
        row1.append(InlineKeyboardButton(btn_label, callback_data=cb))
    return InlineKeyboardMarkup([
        row1,
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"stats_{active}"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])


async def handle_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "1d"):
    query = update.callback_query
    if query:
        await query.answer("📊 Hisoblanmoqda...")
    
    now_ms = int(time.time() * 1000)
    labels = {"1d": "1 KUNLIK", "7d": "7 KUNLIK", "30d": "OYLIK"}
    label = labels.get(period, "1 KUNLIK")

    if period == "1d":
        start_ms = int(datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp() * 1000)
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
    else:
        start_ms = now_ms - 30 * 24 * 3600 * 1000

    orders = _get_orders(start_ms, now_ms)
    # Faqat yopilgan (filled) orderlar
    closed = [o for o in orders if o.get("state") in ("filled", "full_fill", "partially_filled")]
    equity = _get_equity()
    text = format_statistics(closed, label, equity)
    kb = stats_keyboard(period)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Text message orqali kelgan
        msg = update.message
        await msg.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_stats_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bottom keyboard 'Statistika' tugmasi."""
    await handle_statistics(update, context, period="1d")

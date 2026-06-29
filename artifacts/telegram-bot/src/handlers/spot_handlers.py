"""Spot section handlers."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import format_spot_balance, format_open_orders, format_history, ts_to_date

client = BitgetClient()


def spot_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Balans", callback_data="spot_balance"),
         InlineKeyboardButton("📊 Balans (Kripto)", callback_data="spot_assets")],
        [InlineKeyboardButton("📋 Faol Orderlar", callback_data="spot_open_orders"),
         InlineKeyboardButton("📜 Tarix", callback_data="spot_history")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_refresh"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])


def history_keyboard_spot():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugungi", callback_data="spot_hist_today"),
         InlineKeyboardButton("📆 7 Kunlik", callback_data="spot_hist_7d"),
         InlineKeyboardButton("🗓️ 30 Kunlik", callback_data="spot_hist_30d")],
        [InlineKeyboardButton("📋 Hamma vaqt", callback_data="spot_hist_all"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="spot_main")],
    ])


async def show_spot_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        "🪙 <b>SPOT BO'LIMI</b>\n"
        "═══════════════════════════\n"
        "💱 <b>Spot savdosi</b>\n"
        "💡 Quyidagi bo'limlardan birini tanlang:\n\n"
        "💼 <b>Balans</b> — USDT va boshqa kriptolar\n"
        "📊 <b>Kripto Balans</b> — Foiz foyda/zarar\n"
        "📋 <b>Faol Orderlar</b> — Kutayotgan orderlar\n"
        "📜 <b>Tarix</b> — Bugun/7kun/30kun tarix"
    )
    kb = spot_main_keyboard()
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💼 Spot balans yuklanmoqda...")
    data = client.get_spot_account()
    text = format_spot_balance(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_balance"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="spot_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show spot assets with current prices and PnL."""
    query = update.callback_query
    await query.answer("📊 Kripto balansi yuklanmoqda...")

    account_data = client.get_spot_account()
    tickers_data = client.get_spot_tickers()

    if account_data.get("code") != "00000":
        await query.edit_message_text("❌ <b>Ma'lumot olinmadi</b>", parse_mode="HTML")
        return

    assets = account_data.get("data", [])
    tickers = {}
    if tickers_data.get("code") == "00000":
        for t in tickers_data.get("data", []):
            tickers[t.get("symbol", "")] = t

    lines = ["📊 <b>SPOT KRIPTO BALANSI</b>\n" + "─" * 28]
    total_value = 0.0

    for asset in assets:
        coin = asset.get("coin", "")
        available = safe_float(asset.get("available", 0))
        frozen = safe_float(asset.get("frozen", 0))
        total_qty = available + frozen
        usd_value = safe_float(asset.get("usdtAmount", 0))

        if usd_value < 0.1 and total_qty < 0.00001:
            continue

        total_value += usd_value

        if coin == "USDT":
            lines.append(f"\n💵 <b>USDT</b>: <code>{available:.4f}</code> ≈ <code>{usd_value:.2f}$</code>")
            continue

        symbol = f"{coin}USDT"
        ticker = tickers.get(symbol, {})
        current_price = safe_float(ticker.get("lastPr", 0))
        change_24h = safe_float(ticker.get("change24h", 0)) * 100

        if change_24h > 0:
            ch_icon = "📈"
        elif change_24h < 0:
            ch_icon = "📉"
        else:
            ch_icon = "➡️"

        freeze_str = f" 🔒{frozen:.6f}" if frozen > 0 else ""
        lines.append(
            f"\n🪙 <b>{coin}</b>: <code>{available:.6f}</code>{freeze_str}\n"
            f"   💲 <code>{current_price:.6f}</code> {ch_icon} <code>{change_24h:+.2f}%</code>"
            f" ≈ <code>{usd_value:.2f}$</code>"
        )

    lines.append(f"\n{'─'*28}")
    lines.append(f"💵 <b>Jami qiymat:</b> <code>{total_value:.2f} USDT</code>")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_assets"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="spot_main")]
    ])
    await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")


async def handle_spot_open_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📋 Orderlar yuklanmoqda...")
    orders = client.get_spot_open_orders()
    text = format_open_orders(orders, None)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_open_orders"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="spot_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📜 <b>SPOT TARIX</b>\n"
        "═══════════════════════════\n"
        "Qaysi davr uchun tarix ko'rmoqchisiz?"
    )
    await query.edit_message_text(text, reply_markup=history_keyboard_spot(), parse_mode="HTML")


async def handle_spot_history(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "today"):
    query = update.callback_query
    await query.answer("📜 Tarix yuklanmoqda...")

    now_ms = int(time.time() * 1000)
    if period == "today":
        start_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp() * 1000)
        label = "BUGUNGI SPOT TARIX"
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
        label = "7 KUNLIK SPOT TARIX"
    elif period == "30d":
        start_ms = now_ms - 30 * 24 * 3600 * 1000
        label = "30 KUNLIK SPOT TARIX"
    else:
        start_ms = 0
        label = "BARCHA SPOT TARIXI"

    data = client.get_spot_order_history(
        start_time=str(start_ms) if start_ms else "",
        end_time=str(now_ms),
        limit=100
    )
    orders = []
    if data.get("code") == "00000":
        d = data.get("data", {})
        if isinstance(d, dict):
            orders = d.get("orderList", d.get("entrustedList", []))
        elif isinstance(d, list):
            orders = d

    text = format_history(orders, label, "spot")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"spot_hist_{period}"),
         InlineKeyboardButton("🔙 Tarix Menyu", callback_data="spot_history"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

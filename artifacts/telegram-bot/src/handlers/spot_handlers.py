"""Spot section handlers."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import format_spot_balance, format_spot_assets, format_open_orders, format_history

client = BitgetClient()


def spot_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Balans (USDT)", callback_data="spot_balance"),
         InlineKeyboardButton("📊 Kripto Balans", callback_data="spot_assets")],
        [InlineKeyboardButton("📋 Faol Orderlar", callback_data="spot_open_orders"),
         InlineKeyboardButton("📜 Tarix", callback_data="spot_history")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="section_spot"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")],
    ])


def history_keyboard_spot():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun", callback_data="spot_hist_today"),
         InlineKeyboardButton("📆 7 Kun", callback_data="spot_hist_7d"),
         InlineKeyboardButton("🗓️ 30 Kun", callback_data="spot_hist_30d")],
        [InlineKeyboardButton("📋 Hammasi", callback_data="spot_hist_all"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")],
    ])


async def show_spot_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🪙 <b>SPOT BO'LIMI</b>\n"
        "══════════════════════════\n"
        "💱 Spot savdosi\n\n"
        "💼 <b>Balans</b> — USDT va kriptolar\n"
        "📊 <b>Kripto Balans</b> — Narx + 24h foiz\n"
        "📋 <b>Faol Orderlar</b> — Kutayotganlar\n"
        "📜 <b>Tarix</b> — Savdo tarixi"
    )
    await query.edit_message_text(text, reply_markup=spot_main_keyboard(), parse_mode="HTML")


async def handle_spot_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💼 Yuklanmoqda...")
    data = client.get_spot_account()
    text = format_spot_balance(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_balance"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📊 Yuklanmoqda...")
    account = client.get_spot_account()
    tickers_data = client.get_spot_tickers()
    tickers = {}
    if tickers_data.get("code") == "00000":
        for t in tickers_data.get("data", []):
            tickers[t.get("symbol", "")] = t
    text = format_spot_assets(account, tickers)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_assets"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_open_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📋 Yuklanmoqda...")
    orders = client.get_spot_open_orders()
    text = format_open_orders(orders, None)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_open_orders"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📜 <b>SPOT TARIX</b>\n══════════════════\nQaysi davr?"
    await query.edit_message_text(text, reply_markup=history_keyboard_spot(), parse_mode="HTML")


async def handle_spot_history(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "today"):
    query = update.callback_query
    await query.answer("📜 Yuklanmoqda...")
    now_ms = int(time.time() * 1000)
    labels = {"today": "BUGUNGI SPOT", "7d": "7 KUNLIK SPOT", "30d": "30 KUNLIK SPOT", "all": "BARCHA SPOT"}
    label = labels.get(period, "SPOT TARIX")
    if period == "today":
        start_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp() * 1000)
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
    elif period == "30d":
        start_ms = now_ms - 30 * 24 * 3600 * 1000
    else:
        start_ms = 0

    data = client.get_spot_order_history(
        start_time=str(start_ms) if start_ms else "",
        end_time=str(now_ms), limit=100
    )
    orders = []
    if data.get("code") == "00000":
        d = data.get("data", {})
        orders = d.get("orderList", d.get("entrustedList", [])) if isinstance(d, dict) else (d or [])

    text = format_history(orders, label, "spot")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"spot_hist_{period}"),
         InlineKeyboardButton("🔙 Tarix", callback_data="spot_history"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

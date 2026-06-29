"""Futures section handlers."""
import asyncio
import time
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import (
    format_futures_balance, format_open_positions, format_open_orders,
    format_tp_sl_orders, format_history, format_top_signals, ts_to_date
)

client = BitgetClient()


def futures_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Balans", callback_data="fut_balance"),
         InlineKeyboardButton("📊 Ochiq Pozitsiyalar", callback_data="fut_positions")],
        [InlineKeyboardButton("📋 Faol Orderlar", callback_data="fut_open_orders"),
         InlineKeyboardButton("🎯 TP/SL Orderlar", callback_data="fut_tpsl")],
        [InlineKeyboardButton("📜 Tarix", callback_data="fut_history"),
         InlineKeyboardButton("🏆 Top Signallar", callback_data="fut_signals")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_refresh"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])


def history_keyboard(section="fut"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugungi", callback_data=f"{section}_hist_today"),
         InlineKeyboardButton("📆 7 Kunlik", callback_data=f"{section}_hist_7d"),
         InlineKeyboardButton("🗓️ 30 Kunlik", callback_data=f"{section}_hist_30d")],
        [InlineKeyboardButton("📋 Hamma vaqt", callback_data=f"{section}_hist_all"),
         InlineKeyboardButton("🔙 Orqaga", callback_data=f"fut_main" if section == "fut" else "spot_main")],
    ])


async def show_futures_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        "📈 <b>FYUCHERS BO'LIMI</b>\n"
        "═══════════════════════════\n"
        "⚡ <b>USDT-M Perpetual Futures</b>\n"
        "🔄 <b>Marja rejimi:</b> KROSS\n"
        "💡 Quyidagi bo'limlardan birini tanlang:\n\n"
        "💼 <b>Balans</b> — Erkin va ishlatilgan balans\n"
        "📊 <b>Ochiq Pozitsiyalar</b> — Faol tradelar PnL\n"
        "📋 <b>Faol Orderlar</b> — Kutayotgan orderlar\n"
        "🎯 <b>TP/SL</b> — Take Profit & Stop Loss\n"
        "📜 <b>Tarix</b> — Bugun/7kun/30kun tarix\n"
        "🏆 <b>Top Signallar</b> — AI signallari TOP-10"
    )
    kb = futures_main_keyboard()
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💼 Balans yuklanmoqda...")
    data = client.get_futures_account()
    text = format_futures_balance(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_balance"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="fut_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📊 Pozitsiyalar yuklanmoqda...")
    data = client.get_futures_positions()
    text = format_open_positions(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_positions"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="fut_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_open_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📋 Orderlar yuklanmoqda...")
    orders = client.get_futures_open_orders()
    plan_orders = client.get_futures_plan_orders()
    text = format_open_orders(orders, plan_orders)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_open_orders"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="fut_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_tpsl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎯 TP/SL yuklanmoqda...")
    plan_orders = client.get_futures_plan_orders()
    text = format_tp_sl_orders(plan_orders)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_tpsl"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="fut_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📜 <b>FYUCHERS TARIX</b>\n"
        "═══════════════════════════\n"
        "Qaysi davr uchun tarix ko'rmoqchisiz?"
    )
    await query.edit_message_text(text, reply_markup=history_keyboard("fut"), parse_mode="HTML")


async def handle_futures_history(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "today"):
    query = update.callback_query
    await query.answer("📜 Tarix yuklanmoqda...")

    now_ms = int(time.time() * 1000)
    if period == "today":
        start_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp() * 1000)
        label = "BUGUNGI TARIX"
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
        label = "7 KUNLIK TARIX"
    elif period == "30d":
        start_ms = now_ms - 30 * 24 * 3600 * 1000
        label = "30 KUNLIK TARIX"
    else:
        start_ms = 0
        label = "BARCHA VAQT TARIXI"

    params = {"productType": "USDT-FUTURES", "limit": "100"}
    if start_ms:
        params["startTime"] = str(start_ms)
        params["endTime"] = str(now_ms)

    data = client.get_futures_order_history(
        start_time=str(start_ms) if start_ms else "",
        end_time=str(now_ms),
        limit=100
    )
    orders = []
    if data.get("code") == "00000":
        orders = data.get("data", {}).get("entrustedList", data.get("data", []))
        if not isinstance(orders, list):
            orders = []

    text = format_history(orders, label, "futures")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"fut_hist_{period}"),
         InlineKeyboardButton("🔙 Tarix Menyu", callback_data="fut_history"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔍 Signallar skanerlanmoqda...")

    # Show loading message
    loading_text = (
        "🔍 <b>AI SIGNALLAR SKANERLANMOQDA...</b>\n\n"
        "⏳ Barcha kripto bozorlar tahlil qilinmoqda\n"
        "📊 RSI, MACD, EMA, ADX, Supertrend...\n"
        "🧠 Smart Money Concepts tekshirilmoqda\n\n"
        "<i>Bu 10-20 soniya davom etadi...</i>"
    )
    await query.edit_message_text(loading_text, parse_mode="HTML")

    try:
        from services.trading_engine import TradingEngine
        engine = TradingEngine(client)
        signals = await engine.get_top_signals(10)
        text = format_top_signals(signals)
    except Exception as e:
        text = f"❌ <b>Signal olishda xato:</b>\n<code>{str(e)[:200]}</code>"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_signals"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="fut_main")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

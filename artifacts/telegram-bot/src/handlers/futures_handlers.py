"""Futures section handlers."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import (
    format_futures_balance, format_open_positions, format_open_orders,
    format_tp_sl_orders, format_history, format_top_signals
)

client = BitgetClient()


def futures_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Balans", callback_data="fut_balance"),
         InlineKeyboardButton("📊 Pozitsiyalar", callback_data="fut_positions")],
        [InlineKeyboardButton("📋 Faol Orderlar", callback_data="fut_open_orders"),
         InlineKeyboardButton("🎯 TP/SL", callback_data="fut_tpsl")],
        [InlineKeyboardButton("📜 Tarix", callback_data="fut_history"),
         InlineKeyboardButton("🏆 Top Signallar", callback_data="fut_signals")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="section_futures"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")],
    ])


def history_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun", callback_data="fut_hist_today"),
         InlineKeyboardButton("📆 7 Kun", callback_data="fut_hist_7d"),
         InlineKeyboardButton("🗓️ 30 Kun", callback_data="fut_hist_30d")],
        [InlineKeyboardButton("📋 Hammasi", callback_data="fut_hist_all"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")],
    ])


async def show_futures_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📈 <b>FYUCHERS BO'LIMI</b>\n"
        "══════════════════════════\n"
        "⚡ USDT-M Perpetual | KROSS Marja\n\n"
        "💼 <b>Balans</b> — Erkin/ishlatilgan\n"
        "📊 <b>Pozitsiyalar</b> — PnL + 8H funding\n"
        "📋 <b>Faol Orderlar</b> — Kutayotganlar\n"
        "🎯 <b>TP/SL</b> — Trigger orderlar\n"
        "📜 <b>Tarix</b> — Bugun/7/30 kun\n"
        "🏆 <b>Top Signallar</b> — AI TOP-10"
    )
    await query.edit_message_text(text, reply_markup=futures_main_keyboard(), parse_mode="HTML")


async def handle_futures_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💼 Yuklanmoqda...")
    data = client.get_futures_account()
    text = format_futures_balance(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_balance"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📊 Yuklanmoqda...")

    pos_data = client.get_futures_positions()

    # Get funding rates for open positions
    funding_rates = {}
    if pos_data.get("code") == "00000":
        for pos in pos_data.get("data", []):
            if safe_float(pos.get("total", 0)) > 0:
                symbol = pos.get("symbol", "")
                try:
                    fr_data = client.get_funding_rate(symbol)
                    if fr_data.get("code") == "00000":
                        fr = safe_float(fr_data.get("data", {}).get("fundingRate", 0.0001))
                        funding_rates[symbol] = fr
                except Exception:
                    funding_rates[symbol] = 0.0001

    text = format_open_positions(pos_data, funding_rates)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_positions"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_open_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📋 Yuklanmoqda...")
    orders = client.get_futures_open_orders()
    plan   = client.get_futures_plan_orders()
    text   = format_open_orders(orders, plan)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_open_orders"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_tpsl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎯 Yuklanmoqda...")
    plan = client.get_futures_plan_orders()
    text = format_tp_sl_orders(plan)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_tpsl"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📜 <b>FYUCHERS TARIX</b>\n══════════════════\nQaysi davr?"
    await query.edit_message_text(text, reply_markup=history_keyboard(), parse_mode="HTML")


async def handle_futures_history(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "today"):
    query = update.callback_query
    await query.answer("📜 Yuklanmoqda...")
    now_ms = int(time.time() * 1000)
    labels = {"today": "BUGUNGI TARIX", "7d": "7 KUNLIK TARIX", "30d": "30 KUNLIK TARIX", "all": "BARCHA TARIX"}
    label = labels.get(period, "TARIX")
    if period == "today":
        start_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp() * 1000)
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
    elif period == "30d":
        start_ms = now_ms - 30 * 24 * 3600 * 1000
    else:
        start_ms = 0

    data = client.get_futures_order_history(
        start_time=str(start_ms) if start_ms else "",
        end_time=str(now_ms), limit=100
    )
    orders = []
    if data.get("code") == "00000":
        d = data.get("data", {})
        orders = d.get("entrustedList", d.get("orderList", [])) if isinstance(d, dict) else (d or [])

    text = format_history(orders, label, "futures")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"fut_hist_{period}"),
         InlineKeyboardButton("🔙 Tarix", callback_data="fut_history"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔍 Skanerlayapti...")
    loading = (
        "🔍 <b>AI SIGNALLAR SKANERLANMOQDA...</b>\n\n"
        "📊 BTC, ETH, BNB, SOL, XRP...\n"
        "🧠 RSI, MACD, EMA, ADX, SMC...\n\n"
        "<i>10–20 soniya kuting...</i>"
    )
    await query.edit_message_text(loading, parse_mode="HTML")
    try:
        from services.trading_engine import TradingEngine
        engine = TradingEngine(client)
        signals = await engine.get_top_signals(10)
        text = format_top_signals(signals)
    except Exception as e:
        text = f"❌ <b>Xato:</b>\n<code>{str(e)[:200]}</code>"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_signals"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

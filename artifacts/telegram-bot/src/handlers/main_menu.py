"""Main menu and common handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float

client = BitgetClient()

WELCOME_TEXT = """
🤖 <b>BITGET AI CRYPTO BOT</b>
<b>Premium Trading Assistant</b>
═══════════════════════════════

👋 Assalomu alaykum! Men sizning professional savdo yordamchingizman.

🧠 <b>AI Imkoniyatlar:</b>
├ 📊 RSI, MACD, EMA, ADX, Supertrend tahlili
├ 💹 Smart Money Concepts (SMC)
├ 🔀 Multi-Timeframe Analysis
├ 📈 Volume & Order Flow tahlili
└ ⚡ Avtomatik signal & savdo

💼 <b>Bo'limlar:</b>
├ 📈 <b>Fyuchers</b> — USDT-M Perpetual
└ 🪙 <b>Spot</b> — Spot savdosi

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ <b>Bot holati:</b> <code>ACTIVE ✅</code>
🕒 <code>{time} UTC</code>
"""


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 FYUCHERS", callback_data="section_futures"),
            InlineKeyboardButton("🪙 SPOT", callback_data="section_spot"),
        ],
        [
            InlineKeyboardButton("🤖 Bot Holati", callback_data="bot_status"),
            InlineKeyboardButton("ℹ️ Haqida", callback_data="about"),
        ],
    ])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = WELCOME_TEXT.format(
        time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )
    await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode="HTML")


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = WELCOME_TEXT.format(
        time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )
    await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode="HTML")


async def handle_bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Status tekshirilmoqda...")

    # Test API connection
    try:
        futures_acc = client.get_futures_account()
        spot_acc = client.get_spot_account()
        api_ok = futures_acc.get("code") == "00000"
        spot_ok = spot_acc.get("code") == "00000"

        if api_ok:
            d = futures_acc.get("data", {})
            f_balance = safe_float(d.get("available", d.get("usdtEquity", 0)))
        else:
            f_balance = 0.0

        if spot_ok:
            assets = spot_acc.get("data", [])
            s_balance = sum(safe_float(a.get("usdtAmount", 0)) for a in assets)
        else:
            s_balance = 0.0

        api_status = "✅ Ulangan" if api_ok else "❌ Xato"
        spot_status = "✅ Ulangan" if spot_ok else "❌ Xato"
    except Exception as e:
        api_status = f"❌ {str(e)[:30]}"
        spot_status = "❌"
        f_balance = 0.0
        s_balance = 0.0

    text = (
        f"🤖 <b>BOT HOLATI</b>\n"
        f"═══════════════════════════\n"
        f"🔌 <b>Bitget Fyuchers API:</b> {api_status}\n"
        f"🔌 <b>Bitget Spot API:</b> {spot_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>Fyuchers balans:</b> <code>{f_balance:.4f} USDT</code>\n"
        f"🪙 <b>Spot balans:</b> <code>{s_balance:.4f} USDT</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>AI Scanner:</b> ✅ Faol\n"
        f"📊 <b>Signal Confidence:</b> min 70%\n"
        f"⏱️ <b>Skaner intervali:</b> 5 daqiqa\n"
        f"💡 <b>Maksimal Leveraj:</b> Har bir kripto uchun MAX\n"
        f"📐 <b>Risk/Reward:</b> 1:1 (komissiya hisoblab)\n"
        f"💰 <b>Order hajmi:</b> Balansning 5%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="bot_status"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ <b>BOT HAQIDA</b>\n"
        "═══════════════════════════\n\n"
        "🤖 <b>Bitget AI Trading Bot</b>\n"
        "Versiya: <code>1.0.0 Premium</code>\n\n"
        "📊 <b>Texnik Indikatorlar:</b>\n"
        "├ RSI (14) — Overbought/Oversold\n"
        "├ MACD (12,26,9) — Trend momentum\n"
        "├ EMA (9, 21, 50, 200) — Trend yo'nalishi\n"
        "├ ADX (14) — Trend kuchi\n"
        "├ ATR (14) — Volatillik & TP/SL\n"
        "├ Supertrend (10, 3.0) — Trend signal\n"
        "├ Bollinger Bands (20, 2σ) — Narx kanali\n"
        "├ Stochastic (14) — Momentum\n"
        "└ Volume Analysis — Hajm tahlili\n\n"
        "🧠 <b>Smart Money Concepts:</b>\n"
        "├ Break of Structure (BOS)\n"
        "├ Change of Character (CHOCH)\n"
        "└ Order Blocks (OB)\n\n"
        "⚙️ <b>Savdo Parametrlari:</b>\n"
        "├ Fyuchers: USDT-M Perpetual\n"
        "├ Marja: KROSS rejimi\n"
        "├ Leveraj: Har kriptoda MAKSIMAL\n"
        "├ TP: 2 ta (1:1 RR)\n"
        "├ SL: 1 ta (komissiya hisoblab)\n"
        "└ Muddati: 1-48 soat (qisqa muddatli)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>Ogohlantirish:</b> Kripto savdosi xavfli.\n"
        "Bot avtomatik savdo qiladi — faqat\n"
        "yo'qotishga tayyor pulni ishlatiring."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

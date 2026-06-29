"""Main menu — password auth + ReplyKeyboard at bottom."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from services import state as gs
from config import BOT_PASSWORD

client = BitgetClient()

WELCOME_TEXT = (
    "🤖 <b>BITGET AI CRYPTO BOT</b>\n"
    "<b>Premium Trading Assistant</b>\n"
    "{'═'*30}\n\n"
    "👋 Assalomu alaykum!\n\n"
    "🧠 <b>AI Imkoniyatlar:</b>\n"
    "├ 📊 RSI, MACD, EMA, ADX, Supertrend\n"
    "├ 💹 Smart Money Concepts (SMC)\n"
    "├ 🔀 Multi-Timeframe Analysis\n"
    "└ ⚡ Avtomatik signal & savdo\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ <b>Bot:</b> <code>ACTIVE ✅</code>  "
    "🕒 <code>{time} UTC</code>"
)

PASSWORD_TEXT = (
    "🔐 <b>BITGET AI BOT</b>\n\n"
    "Bu bot shaxsiy foydalanish uchun.\n\n"
    "🔑 <b>Parolni kiriting:</b>"
)


def bottom_reply_keyboard():
    """Fixed keyboard at the bottom of chat."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📈 FYUCHERS"), KeyboardButton("🪙 SPOT")],
            [KeyboardButton("🤖 Bot Holati"), KeyboardButton("📜 Signal Tarixi")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def main_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 FYUCHERS", callback_data="section_futures"),
         InlineKeyboardButton("🪙 SPOT", callback_data="section_spot")],
        [InlineKeyboardButton("🤖 Jonli Holat", callback_data="trading_status"),
         InlineKeyboardButton("📜 Signal Tarixi", callback_data="sig_hist_today")],
        [InlineKeyboardButton("ℹ️ Haqida", callback_data="about")],
    ])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in gs.authenticated_users:
        await update.message.reply_text(PASSWORD_TEXT, parse_mode="HTML")
        return
    # Set notifier chat_id
    gs.notifier_chat_id = update.effective_chat.id
    text = (
        "🤖 <b>BITGET AI CRYPTO BOT</b>\n"
        "<b>Premium Trading Assistant</b>\n"
        "══════════════════════════════\n\n"
        "👋 Assalomu alaykum!\n\n"
        "🧠 <b>AI Imkoniyatlar:</b>\n"
        "├ 📊 RSI, MACD, EMA, ADX, Supertrend\n"
        "├ 💹 Smart Money Concepts (SMC)\n"
        "├ 🔀 Multi-Timeframe Analysis\n"
        "└ ⚡ Avtomatik signal & savdo\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Bot:</b> <code>ACTIVE ✅</code>\n"
        f"🕒 <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code>\n\n"
        "👇 <b>Pastdagi tugmalardan foydalaning</b>"
    )
    await update.message.reply_text(
        text,
        reply_markup=bottom_reply_keyboard(),
        parse_mode="HTML"
    )
    await update.message.reply_text(
        "📌 <b>Bo'limlar:</b>",
        reply_markup=main_inline_keyboard(),
        parse_mode="HTML"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages — password check + bottom keyboard routing."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Password check
    if user_id not in gs.authenticated_users:
        if text == BOT_PASSWORD:
            gs.authenticated_users.add(user_id)
            gs.notifier_chat_id = update.effective_chat.id
            await update.message.reply_text(
                "✅ <b>Parol to'g'ri! Xush kelibsiz!</b>\n\n"
                "Bot faollashtirildi. /start bosing.",
                parse_mode="HTML"
            )
            await start_command(update, context)
        else:
            await update.message.reply_text(
                "❌ <b>Parol noto'g'ri.</b>\nQayta urinib ko'ring:",
                parse_mode="HTML"
            )
        return

    gs.notifier_chat_id = update.effective_chat.id

    # Bottom keyboard routing
    from handlers.futures_handlers import show_futures_main
    from handlers.spot_handlers import show_spot_main

    if text == "📈 FYUCHERS":
        await show_futures_main_msg(update, context)
    elif text == "🪙 SPOT":
        await show_spot_main_msg(update, context)
    elif text == "🤖 Bot Holati":
        await show_trading_status_msg(update, context)
    elif text == "📜 Signal Tarixi":
        await show_signal_history_msg(update, context)
    else:
        await update.message.reply_text(
            "❓ Pastdagi tugmalardan foydalaning.",
            reply_markup=bottom_reply_keyboard(),
            parse_mode="HTML"
        )


async def show_futures_main_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.futures_handlers import futures_main_keyboard
    text = (
        "📈 <b>FYUCHERS BO'LIMI</b>\n"
        "══════════════════════════\n"
        "⚡ USDT-M Perpetual | KROSS Marja\n\n"
        "💼 Balans — Erkin/ishlatilgan balans\n"
        "📊 Pozitsiyalar — PnL + funding\n"
        "📋 Orderlar — Faol kutayotganlar\n"
        "🎯 TP/SL — Take profit & stop loss\n"
        "📜 Tarix — Savdo tarixi\n"
        "🏆 Signallar — AI TOP-10"
    )
    await update.message.reply_text(text, reply_markup=futures_main_keyboard(), parse_mode="HTML")


async def show_spot_main_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.spot_handlers import spot_main_keyboard
    text = (
        "🪙 <b>SPOT BO'LIMI</b>\n"
        "══════════════════════════\n"
        "💱 Spot savdosi\n\n"
        "💼 Balans — USDT va kriptolar\n"
        "📊 Kripto Balans — Narx + foiz\n"
        "📋 Orderlar — Faol orderlar\n"
        "📜 Tarix — Savdo tarixi"
    )
    await update.message.reply_text(text, reply_markup=spot_main_keyboard(), parse_mode="HTML")


async def show_trading_status_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import time
    from services import state as gs
    sc = gs.scanner
    auto_icon = "🟢 YOQILGAN" if gs.auto_trade_enabled else "🔴 O'CHIRILGAN"
    scan_icon = "🔄 Skanerlayapti..." if sc.is_scanning else "⏸️ Kutmoqda"
    last_scan = __import__("datetime").datetime.fromtimestamp(
        sc.last_scan_time, tz=__import__("datetime").timezone.utc
    ).strftime("%H:%M:%S") if sc.last_scan_time else "—"

    logs = sc.get_recent_logs(8)
    log_text = ""
    if logs:
        log_text = "\n\n📋 <b>Oxirgi faoliyat:</b>\n" + "\n".join(f"<code>{l}</code>" for l in logs)

    active_trades_text = ""
    if gs.scanner.active_trades:
        lines = ["\n💼 <b>Bot savdolari:</b>"]
        for sym, tr in gs.scanner.active_trades.items():
            dir_e = "🟢 L" if tr["direction"] == "LONG" else "🔴 S"
            lines.append(f"• <b>{sym}</b> {dir_e} {tr['leverage']}x {tr['margin']:.1f}$")
        active_trades_text = "\n".join(lines)

    text = (
        f"🤖 <b>BOT JONLI HOLATI</b>\n{'═'*28}\n"
        f"⚡ <b>Avtosavdo:</b> {auto_icon}\n"
        f"🔄 <b>Skaner:</b> {scan_icon}\n"
        f"🕒 <b>Oxirgi skan:</b> <code>{last_scan}</code>"
        f"{active_trades_text}{log_text}"
    )
    toggle_label = "🔴 Avtosavdoni O'chirish" if gs.auto_trade_enabled else "🟢 Avtosavdoni Yoqish"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data="toggle_autotrade")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="trading_status")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def show_signal_history_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils.formatters import format_signal_history
    from services import state as gs
    signals = gs.signal_history.get_today()
    text = format_signal_history(signals, "BUGUNGI SIGNAL TARIXI")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Hammasi", callback_data="sig_hist_all"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="sig_hist_today")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🤖 <b>BITGET AI CRYPTO BOT</b>\n"
        "══════════════════════════════\n\n"
        "👇 <b>Bo'limni tanlang:</b>"
    )
    await query.edit_message_text(text, reply_markup=main_inline_keyboard(), parse_mode="HTML")


async def handle_bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy — redirect to trading_status."""
    from handlers.trading_status import handle_trading_status
    await handle_trading_status(update, context)


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ <b>BOT HAQIDA</b>\n"
        "══════════════════════════\n\n"
        "🤖 <b>Bitget AI Trading Bot v2.0</b>\n\n"
        "📊 <b>Indikatorlar:</b>\n"
        "RSI • MACD • EMA(9/21/50/200)\n"
        "ADX • ATR • Supertrend\n"
        "Bollinger Bands • Stochastic\n"
        "SMC (BOS, CHOCH, OB)\n"
        "Price Action • Volume\n\n"
        "⚙️ <b>Savdo qoidalari:</b>\n"
        "├ USDT-M Perpetual Futures\n"
        "├ Marja: KROSS rejimi\n"
        "├ Leveraj: Har kriptoda MAKSIMAL\n"
        "├ 60%+ → Avtomatik savdo\n"
        "├ 55-60% → Ruxsat so'raladi\n"
        "├ Order: $1–$5 oralig'ida\n"
        "├ TP: 2 ta (50%+50%)\n"
        "└ Muddati: 1–48 soat\n\n"
        "⚠️ Kripto savdosi xavfli.\n"
        "Faqat yo'qotishga tayyor pulni ishlatiring."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

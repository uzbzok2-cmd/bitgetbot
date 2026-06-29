"""Main menu — password auth + combined keyboard."""
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import ContextTypes
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services import state as gs
from config import BOT_PASSWORD

client = BitgetClient()

PASSWORD_TEXT = (
    "🔐 <b>BITGET AI BOT — XUSH KELIBSIZ!</b>\n\n"
    "Bu bot shaxsiy foydalanish uchun himoyalangan.\n\n"
    "🔑 <b>Parolni kiriting:</b>"
)


def bottom_reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📈 FYUCHERS"), KeyboardButton("🪙 SPOT")],
            [KeyboardButton("🤖 Bot Holati"), KeyboardButton("📜 Signal Tarixi")],
            [KeyboardButton("📊 BTC Tahlil"),  KeyboardButton("📊 ETH Tahlil")],
            [KeyboardButton("🔍 Hozir Signal Ol")],
        ],
        resize_keyboard=True,
    )


def main_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 FYUCHERS", callback_data="section_futures"),
         InlineKeyboardButton("🪙 SPOT", callback_data="section_spot")],
        [InlineKeyboardButton("🤖 Jonli Holat", callback_data="trading_status"),
         InlineKeyboardButton("📜 Signal Tarixi", callback_data="sig_hist_today")],
        [InlineKeyboardButton("🔍 Signal Ol (70%+)", callback_data="fut_signals"),
         InlineKeyboardButton("ℹ️ Haqida", callback_data="about")],
        [InlineKeyboardButton("📊 BTC Tahlil", callback_data="btc_analysis"),
         InlineKeyboardButton("📊 ETH Tahlil", callback_data="eth_analysis")],
    ])


async def _send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome + bottom keyboard + inline menu."""
    gs.notifier_chat_id = update.effective_chat.id
    text = (
        "🤖 <b>BITGET AI CRYPTO BOT v2.0</b>\n"
        "══════════════════════════════\n\n"
        "✅ <b>Tizimga kirdingiz!</b>\n\n"
        "🧠 <b>AI Imkoniyatlar:</b>\n"
        "├ 📊 RSI, MACD, EMA, ADX, Supertrend\n"
        "├ 💹 Smart Money Concepts (SMC)\n"
        "├ ⚡ 70%+ → Avtomatik savdo\n"
        "└ 📈 BTC/ETH yo'nalish tahlili\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Bot:</b> <code>ACTIVE ✅</code>\n"
        f"🕒 <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code>\n\n"
        "👇 <b>Quyidagi bo'limlardan birini tanlang:</b>"
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in gs.authenticated_users:
        await update.message.reply_text(PASSWORD_TEXT, parse_mode="HTML")
        return
    await _send_welcome(update, context)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text — password check + bottom keyboard routing."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # ── Password gate ─────────────────────────────────────
    if user_id not in gs.authenticated_users:
        if text == BOT_PASSWORD:
            gs.authenticated_users.add(user_id)
            gs.notifier_chat_id = update.effective_chat.id
            await update.message.reply_text(
                "✅ <b>Parol to'g'ri! Xush kelibsiz!</b>",
                parse_mode="HTML"
            )
            await _send_welcome(update, context)
        else:
            await update.message.reply_text(
                "❌ <b>Parol noto'g'ri.</b>\n🔑 Qayta kiriting:",
                parse_mode="HTML"
            )
        return

    # Authenticated — update chat id
    gs.notifier_chat_id = update.effective_chat.id

    # ── Bottom keyboard routing ───────────────────────────
    if text == "📈 FYUCHERS":
        await _show_futures_msg(update, context)
    elif text == "🪙 SPOT":
        await _show_spot_msg(update, context)
    elif text == "🤖 Bot Holati":
        await _show_bot_status_msg(update, context)
    elif text == "📜 Signal Tarixi":
        await _show_signal_hist_msg(update, context)
    elif text == "📊 BTC Tahlil":
        await _show_coin_analysis_msg(update, context, "BTCUSDT")
    elif text == "📊 ETH Tahlil":
        await _show_coin_analysis_msg(update, context, "ETHUSDT")
    elif text == "🔍 Hozir Signal Ol":
        await _show_get_signals_msg(update, context)
    else:
        await update.message.reply_text(
            "❓ Pastdagi tugmalardan foydalaning.",
            reply_markup=bottom_reply_keyboard()
        )


# ── Bottom keyboard message handlers ──────────────────────

async def _show_futures_msg(update, context):
    from handlers.futures_handlers import futures_main_keyboard
    text = (
        "📈 <b>FYUCHERS BO'LIMI</b>\n"
        "══════════════════════════\n"
        "⚡ USDT-M Perpetual | KROSS Marja\n\n"
        "Quyidagi bo'limni tanlang 👇"
    )
    await update.message.reply_text(text, reply_markup=futures_main_keyboard(), parse_mode="HTML")


async def _show_spot_msg(update, context):
    from handlers.spot_handlers import spot_main_keyboard
    text = "🪙 <b>SPOT BO'LIMI</b>\n══════════════════════════\nQuyidagi bo'limni tanlang 👇"
    await update.message.reply_text(text, reply_markup=spot_main_keyboard(), parse_mode="HTML")


async def _show_bot_status_msg(update, context):
    import time
    sc = gs.scanner
    auto_icon  = "🟢 YOQILGAN" if gs.auto_trade_enabled else "🔴 O'CHIRILGAN"
    scan_icon  = "🔄 Skanerlayapti..." if sc.is_scanning else "⏸️ Kutmoqda"
    last_scan  = datetime.fromtimestamp(
        sc.last_scan_time, tz=timezone.utc
    ).strftime("%H:%M:%S") if sc.last_scan_time else "—"

    logs = sc.get_recent_logs(8)
    log_text = ""
    if logs:
        log_text = "\n\n📋 <b>Oxirgi faoliyat:</b>\n" + "\n".join(f"<code>{l}</code>" for l in logs)

    trades_text = ""
    if gs.scanner.active_trades:
        lines = ["\n💼 <b>Bot savdolari:</b>"]
        for sym, tr in gs.scanner.active_trades.items():
            dir_e = "🟢 L" if tr["direction"] == "LONG" else "🔴 S"
            lines.append(f"• <b>{sym}</b> {dir_e} {tr['leverage']}x {tr['margin']:.1f}$")
        trades_text = "\n".join(lines)

    text = (
        f"🤖 <b>BOT JONLI HOLATI</b>\n{'═'*28}\n"
        f"⚡ <b>Avtosavdo (70%+):</b> {auto_icon}\n"
        f"🔄 <b>Skaner:</b> {scan_icon}\n"
        f"🕒 <b>Oxirgi skan:</b> <code>{last_scan}</code>"
        f"{trades_text}{log_text}"
    )
    toggle = "🔴 Avtosavdoni O'chirish" if gs.auto_trade_enabled else "🟢 Avtosavdoni Yoqish"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle, callback_data="toggle_autotrade")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="trading_status")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _show_signal_hist_msg(update, context):
    from utils.formatters import format_signal_history
    signals = gs.signal_history.get_today()
    text = format_signal_history(signals, "BUGUNGI SIGNAL TARIXI (55%+)")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Barcha signallar", callback_data="sig_hist_all"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="sig_hist_today")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _show_get_signals_msg(update, context):
    """Manually trigger signal scan and return results."""
    msg = await update.message.reply_text(
        "🔍 <b>Signallar skanerlanmoqda...</b>\n"
        "📊 BTC, ETH, BNB, SOL, XRP...\n"
        "<i>10–20 soniya kuting...</i>",
        parse_mode="HTML"
    )
    try:
        from services.trading_engine import TradingEngine
        from utils.formatters import format_top_signals
        engine = TradingEngine(client)
        signals = await engine.get_top_signals(10)
        # Show only 70%+ in the "best signals" display
        good = [s for s in signals if s["confidence"] >= 70]
        text = format_top_signals(good if good else signals)
    except Exception as e:
        text = f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_signals")],
    ])
    await msg.delete()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _show_coin_analysis_msg(update, context, symbol: str):
    """Quick BTC/ETH multi-timeframe analysis."""
    await _do_coin_analysis(update.message, context, symbol, send_photo=True)


async def do_coin_analysis_callback(update: Update, context, symbol: str):
    """BTC/ETH analysis triggered from InlineKeyboard callback."""
    query = update.callback_query
    await query.answer("📊 Tahlil qilinmoqda...")
    loading_msg = await query.message.reply_text(
        f"📊 <b>{symbol} tahlil qilinmoqda...</b>\n<i>Bir necha soniya...</i>",
        parse_mode="HTML"
    )
    await _do_coin_analysis(loading_msg, context, symbol, send_photo=True, delete_first=True)


async def _do_coin_analysis(msg_or_message, context, symbol: str,
                             send_photo: bool = True, delete_first: bool = False):
    """Shared BTC/ETH analysis logic."""
    if delete_first:
        try:
            await msg_or_message.delete()
        except Exception:
            pass
        chat_id = msg_or_message.chat_id
        send_fn = lambda t, **kw: context.bot.send_message(chat_id=chat_id, text=t, **kw)
        send_photo_fn = lambda **kw: context.bot.send_photo(chat_id=chat_id, **kw)
    else:
        chat_id = msg_or_message.chat_id
        send_fn = lambda t, **kw: msg_or_message.reply_text(t, **kw)
        send_photo_fn = lambda **kw: msg_or_message.reply_photo(**kw)

    from services.analyzer import analyze_symbol
    import logging
    _logger = logging.getLogger(__name__)
    results = []
    for tf in ["1H", "4H"]:
        try:
            candles = client.get_futures_candles(symbol, tf, 150)
            code = candles.get("code")
            data = candles.get("data", [])
            _logger.info(f"{symbol} {tf} candles: code={code} count={len(data) if data else 0}")
            if code == "00000" and data:
                sig = analyze_symbol(data, symbol, tf)
                if sig:
                    results.append((tf, sig, data))
                else:
                    _logger.warning(f"{symbol} {tf}: analyze_symbol None qaytardi")
            else:
                _logger.warning(f"{symbol} {tf}: API xato code={code} msg={candles.get('msg')}")
        except Exception as e:
            _logger.error(f"{symbol} {tf} candles xato: {e}")

    if not results:
        await send_fn(
            f"❌ <b>{symbol} uchun ma'lumot olinmadi</b>\n"
            f"<i>Bitget API javob bermadi yoki signal aniqlanmadi. Keyinroq qayta urining.</i>",
            parse_mode="HTML"
        )
        return

    # Build analysis text
    lines = [f"📊 <b>{symbol} — TAHLIL</b>"]
    for tf, sig, _ in results:
        conf  = sig["confidence"]
        dir_  = sig["direction"]
        dir_e = "🟢 O'SISH (LONG)" if dir_ == "LONG" else "🔴 PASAYISH (SHORT)"
        rsi   = sig.get("rsi", 0)
        macd_h= sig.get("macd_hist", 0)
        macd_e= "↑ Ijobiy" if macd_h > 0 else "↓ Salbiy"
        adx   = sig.get("adx", 0)
        trend = sig.get("trend_dir", "sideways")
        vol   = sig.get("volume_ratio", 1.0)
        trend_map = {"up": "↑ O'sish", "down": "↓ Pasayish", "sideways": "→ Yon"}
        reasons = sig.get("reasons", [])

        lines += [
            f"\n{'─'*28}",
            f"⏱️ <b>Vaqt oralig'i: {tf}</b>",
            f"🎯 <b>Signal: {dir_e}</b>",
            f"📐 <b>Ishonch: {conf}%</b>",
            f"📊 RSI: <code>{rsi}</code>",
            f"📈 MACD: <code>{macd_e}</code>",
            f"⚡ ADX: <code>{adx:.0f}</code>",
            f"📉 Trend: <code>{trend_map.get(trend,'→')}</code>",
            f"📦 Hajm: <code>{vol:.1f}x</code>",
        ]
        if reasons:
            lines.append(f"💡 " + " • ".join(reasons[:3]))

    # Overall verdict
    long_votes  = sum(1 for _, s, _ in results if s["direction"] == "LONG")
    short_votes = sum(1 for _, s, _ in results if s["direction"] == "SHORT")
    avg_conf    = sum(s["confidence"] for _, s, _ in results) / len(results)
    if long_votes > short_votes:
        verdict = f"🟢 <b>UMUMIY: O'SISH ehtimoli yuqori ({avg_conf:.0f}%)</b>"
    elif short_votes > long_votes:
        verdict = f"🔴 <b>UMUMIY: PASAYISH ehtimoli yuqori ({avg_conf:.0f}%)</b>"
    else:
        verdict = f"🟡 <b>UMUMIY: Aralash signal ({avg_conf:.0f}%)</b>"

    lines += [f"\n{'═'*28}", verdict,
              f"\n🕒 <code>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}</code>"]

    await send_fn("\n".join(lines), parse_mode="HTML")

    # Send chart for best timeframe (4H preferred)
    if send_photo and results:
        best_tf, best_sig, best_candles = results[-1]  # prefer 4H
        try:
            from services.chart_generator import generate_signal_chart
            buf = generate_signal_chart(
                candles_data=best_candles,
                symbol=symbol,
                direction=best_sig["direction"],
                entry=best_sig["entry"],
                tp1=best_sig["tp1"],
                tp2=best_sig["tp2"],
                sl=best_sig["sl"],
                confidence=best_sig["confidence"],
                timeframe=best_tf,
            )
            await send_photo_fn(photo=buf,
                                caption=f"📊 {symbol} {best_tf} — {best_sig['confidence']}% ishonch")
        except Exception as e:
            pass


# ── InlineKeyboard callbacks ───────────────────────────────

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🤖 <b>BITGET AI CRYPTO BOT</b>\n══════════════════════════════\n\n👇 <b>Bo'limni tanlang:</b>"
    await query.edit_message_text(text, reply_markup=main_inline_keyboard(), parse_mode="HTML")


async def handle_bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.trading_status import handle_trading_status
    await handle_trading_status(update, context)


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ <b>BOT HAQIDA</b>\n══════════════════════════\n\n"
        "🤖 <b>Bitget AI Trading Bot v2.0</b>\n\n"
        "📊 <b>Indikatorlar:</b>\n"
        "RSI • MACD • EMA(9/21/50/200)\n"
        "ADX • ATR • Supertrend\n"
        "Bollinger • Stochastic • SMC\n\n"
        "⚙️ <b>Qoidalar:</b>\n"
        "├ 70%+ → Avtomatik savdo + rasm\n"
        "├ <70% → Faqat tarixda saqlanadi\n"
        "├ Order: $1–$5\n"
        "└ TP×2, SL×1, KROSS leverage"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

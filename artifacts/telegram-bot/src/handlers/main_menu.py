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

ANALYSIS_SYMBOLS_LIST = [
    ("📊 BTC",  "BTCUSDT"),
    ("📊 ETH",  "ETHUSDT"),
    ("💎 PAXG", "PAXGUSDT"),
    ("🥇 XAUT", "XAUTUSDT"),
]


def bottom_reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📈 FYUCHERS"), KeyboardButton("🪙 SPOT")],
            [KeyboardButton("🤖 Bot Holati"), KeyboardButton("📜 Signal Tarixi")],
            [KeyboardButton("📊 BTC"), KeyboardButton("📊 ETH"),
             KeyboardButton("💎 PAXG"), KeyboardButton("🥇 XAUT")],
            [KeyboardButton("🔍 Hozir Signal Ol")],
            [KeyboardButton("📉 Statistika"), KeyboardButton("⚙️ Sozlamalar")],
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
         InlineKeyboardButton("📉 Statistika", callback_data="stats_1d")],
        [InlineKeyboardButton("📊 BTC", callback_data="btc_analysis"),
         InlineKeyboardButton("📊 ETH", callback_data="eth_analysis"),
         InlineKeyboardButton("💎 PAXG", callback_data="paxg_analysis"),
         InlineKeyboardButton("🥇 XAUT", callback_data="xaut_analysis")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings"),
         InlineKeyboardButton("ℹ️ Haqida", callback_data="about")],
    ])


async def _send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gs.notifier_chat_id = update.effective_chat.id
    text = (
        "🤖 <b>BITGET AI CRYPTO BOT v2.0</b>\n"
        "══════════════════════════════\n\n"
        "✅ <b>Tizimga kirdingiz!</b>\n\n"
        "🧠 <b>AI Imkoniyatlar:</b>\n"
        "├ 📊 RSI, MACD, EMA, ADX, Supertrend\n"
        "├ 💹 Smart Money Concepts (SMC)\n"
        "├ ⚡ 70%+ → Avtomatik savdo\n"
        "├ 🕯️ Zocker Signal — 6-7 ketma-ket sham\n"
        "└ 📈 BTC/ETH/PAXG/XAUT tahlili\n\n"
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
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # ── Password gate ──────────────────────────────────────
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

    gs.notifier_chat_id = update.effective_chat.id

    # ── "Savdoga kirish" — foydalanuvchi USDT summasini kirityapti ──
    if user_id in gs.waiting_trade_input:
        await _handle_trade_amount_input(update, context, user_id, text)
        return

    # ── Bottom keyboard routing ───────────────────────────
    if text == "📈 FYUCHERS":
        await _show_futures_msg(update, context)
    elif text == "🪙 SPOT":
        await _show_spot_msg(update, context)
    elif text == "🤖 Bot Holati":
        await _show_bot_status_msg(update, context)
    elif text == "📜 Signal Tarixi":
        await _show_signal_hist_msg(update, context)
    elif text == "📊 BTC":
        await _show_coin_analysis_msg(update, context, "BTCUSDT")
    elif text == "📊 ETH":
        await _show_coin_analysis_msg(update, context, "ETHUSDT")
    elif text == "💎 PAXG":
        await _show_coin_analysis_msg(update, context, "PAXGUSDT")
    elif text == "🥇 XAUT":
        await _show_coin_analysis_msg(update, context, "XAUTUSDT")
    elif text == "🔍 Hozir Signal Ol":
        await _show_get_signals_msg(update, context)
    elif text == "📉 Statistika":
        from handlers.statistics import handle_stats_from_text
        await handle_stats_from_text(update, context)
    elif text == "⚙️ Sozlamalar":
        from handlers.settings import handle_settings_text
        await handle_settings_text(update, context)
    else:
        await update.message.reply_text(
            "❓ Pastdagi tugmalardan foydalaning.",
            reply_markup=bottom_reply_keyboard()
        )


async def _handle_trade_amount_input(update, context, user_id, text):
    """Foydalanuvchi savdo uchun USDT summasini kiritdi."""
    pending = gs.waiting_trade_input.get(user_id)
    if not pending:
        return

    try:
        amount = float(text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError("Manfiy yoki nol")
    except ValueError:
        # Validatsiya xatosi — holatni SAQLAYMIZ (qayta kiritish uchun)
        await update.message.reply_text(
            "❌ <b>Noto'g'ri summa.</b>\n"
            "📝 Masalan: <code>5</code> yoki <code>10.5</code>\n"
            "💡 Faqat musbat raqam kiriting:",
            parse_mode="HTML"
        )
        return  # gs.waiting_trade_input dan o'chirmaymiz

    # Validatsiya muvaffaqiyatli — holatni tozalaymiz
    gs.waiting_trade_input.pop(user_id, None)

    symbol = pending["symbol"]
    signal = pending["signal"]

    msg = await update.message.reply_text(
        f"⏳ <b>{symbol} uchun savdo ochilmoqda...</b>\n"
        f"💵 Summa: <code>{amount:.2f} USDT</code>",
        parse_mode="HTML"
    )

    try:
        from services.trading_engine import TradingEngine
        engine = TradingEngine(client)
        trade_info, err = await engine.place_manual_trade(symbol, signal, amount)

        if err:
            await msg.delete()
            await update.message.reply_text(
                f"❌ <b>Savdo ochilmadi</b>\n<code>{err}</code>",
                parse_mode="HTML"
            )
            return

        from utils.formatters import fmt_price, _pct_lev
        entry = trade_info["entry"]
        tp1   = trade_info["tp1"]
        sl    = trade_info["sl"]
        lev   = trade_info["leverage"]
        sz    = trade_info["size"]

        await msg.delete()
        await update.message.reply_text(
            f"✅ <b>SAVDO OCHILDI!</b>\n"
            f"{'─'*24}\n"
            f"💎 <b>{symbol}</b> — {'🟢 LONG' if signal['direction']=='LONG' else '🔴 SHORT'}\n"
            f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
            f"⚡ Leverage: <code>{lev}x</code> (KROSS)\n"
            f"📦 Hajm: <code>{sz:.4f}</code>\n"
            f"💰 Marja: <code>{amount:.2f} USDT</code>\n"
            f"{'─'*24}\n"
            f"💚 TP: <code>${fmt_price(tp1)}</code>  ({_pct_lev(tp1, entry, lev)})\n"
            f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry, lev)})",
            parse_mode="HTML"
        )
    except Exception as e:
        try:
            await msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>",
            parse_mode="HTML"
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
        f"📊 <b>Balans foizi:</b> <code>{gs.trade_balance_pct:.1f}%</code>\n"
        f"🔄 <b>Skaner:</b> {scan_icon}\n"
        f"🕒 <b>Oxirgi skan:</b> <code>{last_scan}</code>"
        f"{trades_text}{log_text}"
    )
    toggle = "🔴 Avtosavdoni O'chirish" if gs.auto_trade_enabled else "🟢 Avtosavdoni Yoqish"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle, callback_data="toggle_autotrade")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="trading_status")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _show_signal_hist_msg(update, context):
    from utils.formatters import format_signal_history
    signals = gs.signal_history.get_today()
    text = format_signal_history(signals, "BUGUNGI SIGNAL TARIXI (60%+)")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Barcha signallar", callback_data="sig_hist_all"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="sig_hist_today")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _show_get_signals_msg(update, context):
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
        good = [s for s in signals if s["confidence"] >= 70]
        text = format_top_signals(good if good else signals)
    except Exception as e:
        text = f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>"
        signals = []
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_signals")],
    ])
    await msg.delete()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

    # Top signal chart
    try:
        from services.trading_engine import TradingEngine
        engine2 = TradingEngine(client)
        all_sigs = await engine2.get_top_signals(3, min_conf=70)
        if all_sigs:
            top = all_sigs[0]
            candles = client.get_futures_candles(top["symbol"], "1H", 100)
            if candles.get("code") == "00000":
                from services.chart_generator import generate_signal_chart
                from services.analyzer import estimate_trade_duration
                tf = top.get("timeframe", "1H")
                dur = estimate_trade_duration(tf, top["confidence"])
                buf = generate_signal_chart(
                    candles_data=candles.get("data", []),
                    symbol=top["symbol"],
                    direction=top["direction"],
                    entry=top["entry"], tp1=top["tp1"],
                    sl=top["sl"],
                    confidence=top["confidence"],
                    timeframe=tf, duration_label=dur,
                )
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                chart_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("💰 Savdoga Kirish", callback_data=f"manual_trade_{top['symbol']}")
                ]])
                gs.pending_manual_trades[top["symbol"]] = top
                await update.message.reply_photo(
                    photo=buf,
                    caption=f"📊 {top['symbol']} — {top['confidence']}% ishonch  |  ⌛ {dur}",
                    reply_markup=chart_kb
                )
    except Exception:
        pass


async def _show_coin_analysis_msg(update, context, symbol: str):
    await _do_coin_analysis(update.message, context, symbol, send_photo=True)


async def do_coin_analysis_callback(update: Update, context, symbol: str):
    query = update.callback_query
    await query.answer("📊 Tahlil qilinmoqda...")
    loading_msg = await query.message.reply_text(
        f"📊 <b>{symbol} tahlil qilinmoqda...</b>\n<i>Bir necha soniya...</i>",
        parse_mode="HTML"
    )
    await _do_coin_analysis(loading_msg, context, symbol, send_photo=True, delete_first=True)


async def _do_coin_analysis(msg_or_message, context, symbol: str,
                             send_photo: bool = True, delete_first: bool = False):
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

    # PAXG/XAUT uchun futures'dan oldin spot candles fallback
    SPOT_FALLBACK_SYMBOLS = {"PAXGUSDT", "XAUTUSDT"}

    results = []
    for tf in ["1H", "4H"]:
        try:
            # Avval futures candles
            candles = client.get_futures_candles(symbol, tf, 150)
            code = candles.get("code")
            data = candles.get("data", [])

            # Agar futures xato yoki bo'sh bo'lsa — spot candles ishlatamiz
            if (code != "00000" or not data) and symbol in SPOT_FALLBACK_SYMBOLS:
                _logger.info(f"{symbol} {tf}: futures xato, spot candles urilyapti...")
                spot_candles = client.get_spot_candles(symbol, tf, 150)
                if spot_candles.get("code") == "00000" and spot_candles.get("data"):
                    candles = spot_candles
                    code = "00000"
                    data = candles.get("data", [])
                    _logger.info(f"{symbol} {tf}: spot candles muvaffaqiyatli ({len(data)} ta)")

            if code == "00000" and data:
                sig = analyze_symbol(data, symbol, tf)
                if sig:
                    results.append((tf, sig, data))
                else:
                    _logger.warning(f"{symbol} {tf}: analyze_symbol None qaytardi")
            else:
                _logger.warning(f"{symbol} {tf}: API xato code={code}")
        except Exception as e:
            _logger.error(f"{symbol} {tf} candles xato: {e}")

    if not results:
        await send_fn(
            f"❌ <b>{symbol} uchun ma'lumot olinmadi</b>\n"
            f"<i>Bitget API javob bermadi yoki signal aniqlanmadi. Keyinroq qayta urining.</i>",
            parse_mode="HTML"
        )
        return

    from utils.formatters import fmt_price, _pct

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
        entry = sig.get("entry", 0)
        tp1   = sig.get("tp1", 0)
        sl    = sig.get("sl", 0)

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
            f"💲 Kirish: <code>${fmt_price(entry)}</code>",
            f"💚 TP: <code>${fmt_price(tp1)}</code>  ({_pct(tp1, entry)})",
            f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct(sl, entry)})",
        ]
        if reasons:
            lines.append(f"💡 " + " • ".join(reasons[:3]))

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

    # Chart yuborish
    if send_photo and results:
        best_tf, best_sig, best_candles = results[-1]
        try:
            from services.chart_generator import generate_signal_chart
            from services.analyzer import estimate_trade_duration
            dur = estimate_trade_duration(best_tf, best_sig["confidence"])
            buf = generate_signal_chart(
                candles_data=best_candles,
                symbol=symbol,
                direction=best_sig["direction"],
                entry=best_sig["entry"],
                tp1=best_sig["tp1"],
                sl=best_sig["sl"],
                confidence=best_sig["confidence"],
                timeframe=best_tf,
                duration_label=dur,
            )
            chart_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("💰 Savdoga Kirish", callback_data=f"manual_trade_{symbol}")
            ]])
            gs.pending_manual_trades[symbol] = best_sig
            await send_photo_fn(
                photo=buf,
                caption=f"📊 {symbol} {best_tf} — {best_sig['confidence']}% ishonch  |  ⌛ {dur}",
                reply_markup=chart_kb
            )
        except Exception as e:
            _logger.error(f"Chart error for {symbol}: {e}")


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
        "├ 70%+ → Avtomatik savdo (xabarsiz)\n"
        "├ <70% → Faqat tarixda saqlanadi\n"
        "├ 🕯️ Zocker: 6-7 ketma-ket sham → alert\n"
        "├ TP: 100%, SL: 100%\n"
        "└ KROSS leverage, maksimal"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

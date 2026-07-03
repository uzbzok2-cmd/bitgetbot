"""Live bot activity status & on/off toggles."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import state as gs


def _until(ts: float) -> str:
    if not ts:
        return "—"
    r = int(ts - time.time())
    if r <= 0:
        return "hozir"
    m, s = divmod(r, 60)
    return f"{m}d {s}s"


def _status_icon(enabled: bool) -> str:
    return "🟢 YOQILGAN" if enabled else "🔴 O'CHIRILGAN"


def _build_status_text() -> str:
    sc = gs.scanner
    scan_icon = "🔄 Skanerlayapti..." if sc.is_scanning else "⏸️ Kutmoqda"
    last_scan = (
        datetime.fromtimestamp(sc.last_scan_time, tz=timezone.utc).strftime("%H:%M:%S")
        if sc.last_scan_time else "—"
    )
    next_scan = _until(sc.next_scan_time)

    progress = ""
    if sc.is_scanning and sc.total_symbols > 0:
        pct = int(sc.symbols_checked / sc.total_symbols * 100)
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        progress = (
            f"\n📊 <b>Skan jarayoni:</b>\n"
            f"<code>[{bar}] {pct}%</code>  {sc.symbols_checked}/{sc.total_symbols}\n"
            f"🔍 Hozir: <code>{sc.current_symbol}</code>\n"
            f"📈 Topildi: <code>{sc.signals_this_scan}</code> signal"
        )

    trades_text = ""
    if gs.scanner.active_trades:
        lines = ["\n💼 <b>Bot ochgan savdolar:</b>"]
        for sym, tr in gs.scanner.active_trades.items():
            d = "🟢 L" if tr["direction"] == "LONG" else "🔴 S"
            lines.append(
                f"• <b>{sym}</b> {d} {tr['leverage']}x | "
                f"{tr['margin']:.1f}$ | {tr.get('open_time_str','')}"
            )
        trades_text = "\n".join(lines)

    logs = sc.get_recent_logs(8)
    log_text = ""
    if logs:
        log_text = "\n\n📋 <b>Faoliyat:</b>\n" + "\n".join(
            f"<code>{l}</code>" for l in logs
        )

    top_sig_icon   = _status_icon(gs.top_signals_enabled)
    zocker_icon    = _status_icon(gs.zocker_enabled)
    zokpat_icon    = _status_icon(gs.zokpat_enabled)
    auto_icon      = _status_icon(gs.auto_trade_enabled)

    return (
        f"🤖 <b>BOT JONLI HOLATI</b>\n{'═'*28}\n"
        f"🔄 <b>Skaner:</b> {scan_icon}\n"
        f"🕒 <b>Oxirgi skan:</b> <code>{last_scan}</code>\n"
        f"⏱️ <b>Keyingi skan:</b> <code>{next_scan}</code>\n"
        f"{'─'*28}\n"
        f"⚡ <b>Umumiy avtosavdo:</b> {auto_icon}\n"
        f"📈 <b>Top Signallar (70%+):</b> {top_sig_icon}\n"
        f"🕯️ <b>Zocker Signal:</b> {zocker_icon}\n"
        f"🔮 <b>ZOKPAT Pattern:</b> {zokpat_icon}\n"
        f"📊 <b>Max pozitsiyalar:</b> <code>{gs.MAX_AUTO_POSITIONS} ta</code>\n"
        f"{progress}{trades_text}{log_text}\n"
        f"{'─'*28}\n"
        f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>"
    )


def _build_keyboard() -> InlineKeyboardMarkup:
    auto_btn    = "🔴 Avtosavdoni O'chirish" if gs.auto_trade_enabled    else "🟢 Avtosavdoni Yoqish"
    top_btn     = "🔴 Top Signals O'chirish" if gs.top_signals_enabled   else "🟢 Top Signals Yoqish"
    zocker_btn  = "🔴 Zocker O'chirish"      if gs.zocker_enabled        else "🟢 Zocker Yoqish"
    zokpat_btn  = "🔴 ZOKPAT O'chirish"      if gs.zokpat_enabled        else "🟢 ZOKPAT Yoqish"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(auto_btn,    callback_data="toggle_autotrade")],
        [InlineKeyboardButton(top_btn,     callback_data="toggle_top_signals"),
         InlineKeyboardButton(zocker_btn,  callback_data="toggle_zocker")],
        [InlineKeyboardButton(zokpat_btn,  callback_data="toggle_zokpat")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="trading_status"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])


async def handle_trading_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _build_status_text(),
        reply_markup=_build_keyboard(),
        parse_mode="HTML"
    )


async def handle_toggle_autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gs.auto_trade_enabled = not gs.auto_trade_enabled
    # Umumiy o'chirilganda — barcha sub-toggle ham o'chadi
    if not gs.auto_trade_enabled:
        gs.top_signals_enabled = False
        gs.zocker_enabled      = False
        gs.zokpat_enabled      = False
    else:
        gs.top_signals_enabled = True
        gs.zocker_enabled      = True
        gs.zokpat_enabled      = True
    status = "🟢 YOQILDI" if gs.auto_trade_enabled else "🔴 O'CHIRILDI"
    await query.answer(f"Avtosavdo {status}!")
    await query.edit_message_text(
        _build_status_text(),
        reply_markup=_build_keyboard(),
        parse_mode="HTML"
    )


async def handle_toggle_top_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gs.top_signals_enabled = not gs.top_signals_enabled
    # Agar ikkala sub-toggle ham o'chiq bo'lsa — umumiy ham o'chadi
    if not gs.top_signals_enabled and not gs.zocker_enabled:
        gs.auto_trade_enabled = False
    elif gs.top_signals_enabled or gs.zocker_enabled:
        gs.auto_trade_enabled = True
    status = "🟢 YOQILDI" if gs.top_signals_enabled else "🔴 O'CHIRILDI"
    await query.answer(f"Top Signallar {status}!")
    await query.edit_message_text(
        _build_status_text(),
        reply_markup=_build_keyboard(),
        parse_mode="HTML"
    )


async def handle_toggle_zocker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gs.zocker_enabled = not gs.zocker_enabled
    if not gs.zocker_enabled and not gs.top_signals_enabled and not gs.zokpat_enabled:
        gs.auto_trade_enabled = False
    elif gs.zocker_enabled or gs.top_signals_enabled or gs.zokpat_enabled:
        gs.auto_trade_enabled = True
    status = "🟢 YOQILDI" if gs.zocker_enabled else "🔴 O'CHIRILDI"
    await query.answer(f"Zocker Signal {status}!")
    await query.edit_message_text(
        _build_status_text(),
        reply_markup=_build_keyboard(),
        parse_mode="HTML"
    )


async def handle_toggle_zokpat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gs.zokpat_enabled = not gs.zokpat_enabled
    if not gs.zokpat_enabled and not gs.top_signals_enabled and not gs.zocker_enabled:
        gs.auto_trade_enabled = False
    elif gs.zokpat_enabled or gs.top_signals_enabled or gs.zocker_enabled:
        gs.auto_trade_enabled = True
    status = "🟢 YOQILDI" if gs.zokpat_enabled else "🔴 O'CHIRILDI"
    await query.answer(f"ZOKPAT Pattern {status}!")
    await query.edit_message_text(
        _build_status_text(),
        reply_markup=_build_keyboard(),
        parse_mode="HTML"
    )


async def handle_approve_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    query = update.callback_query
    gs.pending_permission_signals.pop(key, None)
    await query.answer("✅ Savdo boshlandi!")
    await query.edit_message_text(
        query.message.text + "\n\n✅ <b>Tasdiqlandi!</b>",
        parse_mode="HTML"
    )


async def handle_reject_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    query = update.callback_query
    gs.pending_permission_signals.pop(key, None)
    await query.answer("❌ Rad etildi")
    await query.edit_message_text(
        query.message.text + "\n\n❌ <b>Rad etildi</b>",
        parse_mode="HTML"
    )


async def handle_signal_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from utils.formatters import format_signal_history
    signals = gs.signal_history.get_today()
    text = format_signal_history(signals, "BUGUNGI SIGNAL TARIXI (55%+)")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Barcha signallar", callback_data="sig_hist_all"),
         InlineKeyboardButton("🔄 Yangilash",        callback_data="sig_hist_today")],
        [InlineKeyboardButton("🏠 Bosh menyu",        callback_data="main_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_signal_history_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from utils.formatters import format_signal_history
    signals = gs.signal_history.get_all()
    text = format_signal_history(signals, "BARCHA SIGNAL TARIXI")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugungi",  callback_data="sig_hist_today"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="sig_hist_all")],
        [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

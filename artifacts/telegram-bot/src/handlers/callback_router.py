"""Central callback router."""
from telegram import Update
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.main_menu import (
    handle_main_menu, handle_bot_status, handle_about,
    do_coin_analysis_callback
)
from handlers.futures_handlers import (
    show_futures_main, handle_futures_balance, handle_futures_positions,
    handle_futures_open_orders, handle_futures_tpsl,
    handle_futures_history_menu, handle_futures_history, handle_futures_signals,
    handle_zocker_menu, handle_zocker_scan_now,
)
from handlers.spot_handlers import (
    show_spot_main, handle_spot_balance, handle_spot_assets,
    handle_spot_open_orders, handle_spot_history_menu, handle_spot_history,
    handle_spot_signals, handle_spot_statistics, handle_spot_portfolio,
    handle_spot_portfolio_chart,
)
from handlers.trading_status import (
    handle_trading_status, handle_toggle_autotrade,
    handle_toggle_top_signals, handle_toggle_zocker,
    handle_approve_signal, handle_reject_signal,
    handle_signal_history, handle_signal_history_all,
)
from handlers.statistics import handle_statistics
from handlers.settings import handle_settings_callback


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data or ""

    # ── Auth check ────────────────────────────────────────
    from services import state as gs
    user_id = query.from_user.id
    if user_id not in gs.authenticated_users:
        await query.answer("🔐 Avval /start bilan kiring!", show_alert=True)
        return

    # ── Main ──────────────────────────────────────────────
    if data == "main_menu":
        await handle_main_menu(update, context)
    elif data == "about":
        await handle_about(update, context)
    elif data == "bot_status":
        await handle_bot_status(update, context)

    # ── Futures ───────────────────────────────────────────
    elif data in ("section_futures", "fut_main", "fut_refresh"):
        await show_futures_main(update, context)
    elif data == "fut_balance":
        await handle_futures_balance(update, context)
    elif data == "fut_positions":
        await handle_futures_positions(update, context)
    elif data == "fut_open_orders":
        await handle_futures_open_orders(update, context)
    elif data == "fut_tpsl":
        await handle_futures_tpsl(update, context)
    elif data == "fut_history":
        await handle_futures_history_menu(update, context)
    elif data == "fut_hist_today":
        await handle_futures_history(update, context, "today")
    elif data == "fut_hist_7d":
        await handle_futures_history(update, context, "7d")
    elif data == "fut_hist_30d":
        await handle_futures_history(update, context, "30d")
    elif data == "fut_hist_all":
        await handle_futures_history(update, context, "all")
    elif data == "fut_signals":
        await handle_futures_signals(update, context)

    # ── Spot ──────────────────────────────────────────────
    elif data in ("section_spot", "spot_main", "spot_refresh"):
        await show_spot_main(update, context)
    elif data == "spot_balance":
        await handle_spot_balance(update, context)
    elif data == "spot_assets":
        await handle_spot_assets(update, context)
    elif data == "spot_open_orders":
        await handle_spot_open_orders(update, context)
    elif data == "spot_history":
        await handle_spot_history_menu(update, context)
    elif data == "spot_hist_today":
        await handle_spot_history(update, context, "today")
    elif data == "spot_hist_7d":
        await handle_spot_history(update, context, "7d")
    elif data == "spot_hist_30d":
        await handle_spot_history(update, context, "30d")
    elif data == "spot_hist_all":
        await handle_spot_history(update, context, "all")
    elif data == "spot_signals":
        await handle_spot_signals(update, context)
    elif data == "spot_stats_1d":
        await handle_spot_statistics(update, context, "1d")
    elif data == "spot_stats_7d":
        await handle_spot_statistics(update, context, "7d")
    elif data == "spot_stats_30d":
        await handle_spot_statistics(update, context, "30d")
    elif data == "spot_portfolio":
        await handle_spot_portfolio(update, context)
    elif data == "spot_portfolio_chart":
        await handle_spot_portfolio_chart(update, context)

    # ── Spot signal trade ────────────────────────────────
    elif data.startswith("spot_trade_"):
        symbol = data[len("spot_trade_"):]
        await _handle_manual_trade_request(update, context, symbol)

    # ── Zocker Signal ─────────────────────────────────────
    elif data == "fut_zocker":
        await handle_zocker_menu(update, context)
    elif data == "zocker_scan_now":
        await handle_zocker_scan_now(update, context)

    # ── Analysis (BTC, ETH, PAXG, XAUT, CL) ──────────────
    elif data == "btc_analysis":
        await do_coin_analysis_callback(update, context, "BTCUSDT")
    elif data == "eth_analysis":
        await do_coin_analysis_callback(update, context, "ETHUSDT")
    elif data == "paxg_analysis":
        await do_coin_analysis_callback(update, context, "PAXGUSDT")
    elif data == "xaut_analysis":
        await do_coin_analysis_callback(update, context, "XAUTUSDT")
    elif data == "cl_analysis":
        await do_coin_analysis_callback(update, context, "CLUSDT")

    # ── Manual trade — 2 bosqichli ────────────────────────
    elif data.startswith("manual_trade_"):
        symbol = data[len("manual_trade_"):]
        await _handle_manual_trade_step1(update, context, symbol)
    elif data.startswith("do_trade_"):
        symbol = data[len("do_trade_"):]
        await _handle_manual_trade_step2(update, context, symbol)

    # ── Trading status ────────────────────────────────────
    elif data == "trading_status":
        await handle_trading_status(update, context)
    elif data == "toggle_autotrade":
        await handle_toggle_autotrade(update, context)
    elif data == "toggle_top_signals":
        await handle_toggle_top_signals(update, context)
    elif data == "toggle_zocker":
        await handle_toggle_zocker(update, context)

    # ── Signal history ────────────────────────────────────
    elif data == "sig_hist_today":
        await handle_signal_history(update, context)
    elif data == "sig_hist_all":
        await handle_signal_history_all(update, context)

    # ── Futures Statistics ────────────────────────────────
    elif data == "stats_1d":
        await handle_statistics(update, context, "1d")
    elif data == "stats_7d":
        await handle_statistics(update, context, "7d")
    elif data == "stats_30d":
        await handle_statistics(update, context, "30d")

    # ── Settings ──────────────────────────────────────────
    elif data == "settings":
        await handle_settings_callback(update, context)
    elif data.startswith("set_bal_pct_") or data == "settings_save" or data == "settings_noop":
        await handle_settings_callback(update, context)

    # ── Permission approve/reject ─────────────────────────
    elif data.startswith("approve_"):
        await handle_approve_signal(update, context, data[len("approve_"):])
    elif data.startswith("reject_"):
        await handle_reject_signal(update, context, data[len("reject_"):])

    else:
        await query.answer(f"⚠️ Noma'lum: {data[:30]}")


async def _fetch_fresh_signal(symbol: str) -> dict | None:
    """Signal yo'q bo'lsa, yangi tahlil qilib signal yaratish."""
    try:
        from services.bitget_client import BitgetClient
        from services.analyzer import analyze_symbol
        cl = BitgetClient()
        for tf in ["1H", "4H"]:
            r = cl.get_futures_candles(symbol, tf, 150)
            if r.get("code") != "00000" or not r.get("data"):
                r = cl.get_candles_any_type(symbol, tf, 150)
            if r.get("code") != "00000" or not r.get("data"):
                r = cl.get_spot_candles(symbol, tf, 150)
            if r.get("code") == "00000" and r.get("data"):
                sig = analyze_symbol(r["data"], symbol, tf)
                if sig:
                    return sig
    except Exception:
        pass
    return None


async def _handle_manual_trade_step1(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str):
    """Bosqich 1 — Signal tahlili + chart + '2-chi bosish = USDT kiriting' tugmasi."""
    from services import state as gs
    from services.bitget_client import BitgetClient
    from services.analyzer import safe_float
    from utils.formatters import fmt_price, _pct_lev
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    query = update.callback_query
    await query.answer("📊 Tahlil yuklanmoqda...")

    # Signal topish (cache yoki yangi tahlil)
    signal = gs.pending_manual_trades.get(symbol)
    if not signal:
        signal = await _fetch_fresh_signal(symbol)
        if signal:
            gs.pending_manual_trades[symbol] = signal

    if not signal:
        await query.message.reply_text(
            f"⚠️ <b>{symbol}</b> uchun ma'lumot olinmadi.\n"
            f"Biroz kuting va qayta urining.",
            parse_mode="HTML"
        )
        return

    # Balans
    available, equity = 0.0, 0.0
    try:
        cl = BitgetClient()
        acc = cl.get_futures_account()
        if acc.get("code") == "00000":
            available = safe_float(acc["data"].get("available", 0))
            equity    = safe_float(acc["data"].get("usdtEquity", 0))
    except Exception:
        pass

    dir_  = signal.get("direction", "LONG")
    entry = signal.get("entry", 0)
    tp1   = signal.get("tp1", 0)
    sl    = signal.get("sl", 0)
    conf  = signal.get("confidence", 0)
    tf    = signal.get("timeframe", "1H")
    count = signal.get("consecutive_count", 6)
    dir_e = "🟢 LONG" if dir_ == "LONG" else "🔴 SHORT"
    color_txt = "qizil" if dir_ == "LONG" else "yashil"

    text = (
        f"🕯️ <b>ZOCKER SIGNAL TAHLILI — {symbol}</b>\n"
        f"{'═'*28}\n"
        f"📊 Yo'nalish: {dir_e}  •  <b>{conf}%</b>\n"
        f"⏱️ Timeframe: <b>{tf}</b>\n"
        f"🕯️ <b>{count} ta ketma-ket {color_txt} sham</b> — Mean Reversion\n"
        f"{'─'*28}\n"
        f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
        f"💚 TP (oxirgi {max(1,count//2)} sham HIGH): <code>${fmt_price(tp1)}</code>  ({_pct_lev(tp1, entry)})\n"
        f"🛑 SL (1:1 RR): <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry)})\n"
        f"{'─'*28}\n"
        f"💼 <b>Balans:</b>  Kapital: <code>{equity:.2f} USDT</code>  |  Erkin: <code>{available:.2f} USDT</code>\n"
        f"{'─'*28}\n"
        f"👇 <b>Savdoga kirish uchun quyidagi tugmani bosing:</b>"
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 USDT miqdorini kiriting →", callback_data=f"do_trade_{symbol}")
    ]])

    # Chart ham yuborish (agar zocker signal bo'lsa)
    reasons = signal.get("reasons", [])
    is_zocker = any("ketma-ket" in r or "Zocker" in r or "Mean Reversion" in r for r in reasons)
    if is_zocker:
        try:
            cl2 = BitgetClient()
            candles = cl2.get_futures_candles(symbol, tf, 60)
            if candles.get("code") != "00000" or not candles.get("data"):
                candles = cl2.get_spot_candles(symbol, tf, 60)
            raw = candles.get("data", [])
            if raw:
                from services.chart_generator import generate_zocker_chart
                buf = generate_zocker_chart(
                    candles_data=raw, symbol=symbol,
                    direction=dir_, consecutive_count=count,
                    timeframe=tf, entry=entry, tp=tp1, sl=sl,
                )
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"📊 {symbol} {tf} — Kirish: ${fmt_price(entry)} | TP: ${fmt_price(tp1)} | SL: ${fmt_price(sl)}",
                    reply_markup=kb
                )
                await query.message.reply_text(text, parse_mode="HTML")
                return
        except Exception:
            pass

    await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _handle_manual_trade_step2(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str):
    """Bosqich 2 — USDT miqdori so'rash."""
    from services import state as gs
    from services.analyzer import safe_float
    from utils.formatters import fmt_price, _pct_lev

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    signal  = gs.pending_manual_trades.get(symbol)
    if not signal:
        signal = await _fetch_fresh_signal(symbol)
        if signal:
            gs.pending_manual_trades[symbol] = signal

    if not signal:
        await query.message.reply_text(
            f"⚠️ Signal topilmadi. Qayta urinib ko'ring.", parse_mode="HTML"
        )
        return

    gs.waiting_trade_input[user_id] = {
        "symbol": symbol,
        "signal": signal,
        "direction": signal.get("direction", "LONG"),
    }

    dir_  = signal.get("direction", "LONG")
    entry = signal.get("entry", 0)
    tp1   = signal.get("tp1", 0)
    sl    = signal.get("sl", 0)
    dir_e = "🟢 LONG" if dir_ == "LONG" else "🔴 SHORT"

    await query.message.reply_text(
        f"📝 <b>{symbol} — {dir_e}</b>\n"
        f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
        f"💚 TP: <code>${fmt_price(tp1)}</code>  ({_pct_lev(tp1, entry)})\n"
        f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry)})\n"
        f"{'─'*24}\n"
        f"💵 <b>Qancha USDT bilan kirishni xohlaysiz?</b>\n"
        f"<i>Raqam yozing (masalan: 5 yoki 10)</i>",
        parse_mode="HTML"
    )

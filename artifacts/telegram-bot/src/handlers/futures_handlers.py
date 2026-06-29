"""Futures section handlers — positions with TP/SL, BTC/ETH analysis."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import (
    format_futures_balance, format_open_orders,
    format_tp_sl_orders, format_history, format_top_signals, fmt_price, _pct
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


async def show_futures_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📈 <b>FYUCHERS BO'LIMI</b>\n"
        "══════════════════════════\n"
        "⚡ USDT-M Perpetual | KROSS Marja\n\n"
        "💼 <b>Balans</b> — Erkin/ishlatilgan\n"
        "📊 <b>Pozitsiyalar</b> — PnL + TP/SL + funding\n"
        "📋 <b>Faol Orderlar</b> — Kutayotganlar\n"
        "🎯 <b>TP/SL</b> — Trigger orderlar\n"
        "📜 <b>Tarix</b> — Bugun/7/30 kun\n"
        "🏆 <b>Top Signallar</b> — AI TOP-10 (70%+)"
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
    """Show positions with TP/SL levels fetched from plan orders."""
    query = update.callback_query
    await query.answer("📊 Yuklanmoqda...")

    pos_data  = client.get_futures_positions()
    plan_data = client.get_futures_plan_orders()

    # Build TP/SL map: symbol+holdSide → list of plan orders
    plan_map: dict = {}
    if plan_data.get("code") == "00000":
        plan_list = plan_data.get("data") or []
        if isinstance(plan_list, dict):
            plan_list = plan_list.get("entrustedList", [])
        if not isinstance(plan_list, list):
            plan_list = []
        for p in plan_list:
            key = f"{p.get('symbol','')}-{p.get('holdSide','')}"
            plan_map.setdefault(key, []).append(p)

    # Funding rates
    funding_rates = {}
    if pos_data.get("code") == "00000":
        for pos in pos_data.get("data", []):
            if safe_float(pos.get("total", 0)) > 0:
                symbol = pos.get("symbol", "")
                try:
                    fr_data = client.get_funding_rate(symbol)
                    if fr_data.get("code") == "00000":
                        fr = safe_float(fr_data["data"].get("fundingRate", 0.0001))
                        funding_rates[symbol] = fr
                except Exception:
                    funding_rates[symbol] = 0.0001

    text = _format_positions_with_tpsl(pos_data, plan_map, funding_rates)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_positions"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


def _format_positions_with_tpsl(positions_data: dict, plan_map: dict, funding_rates: dict) -> str:
    if not positions_data or positions_data.get("code") != "00000":
        return "❌ <b>Pozitsiyalar olinmadi</b>"
    positions = [p for p in positions_data.get("data", []) if safe_float(p.get("total", 0)) > 0]
    if not positions:
        return "📭 <b>Hozir ochiq pozitsiyalar yo'q</b>"

    lines = [f"📊 <b>OCHIQ POZITSIYALAR</b> ({len(positions)} ta)\n{'─'*28}"]
    total_unr = 0.0
    total_fund = 0.0

    for pos in positions:
        symbol    = pos.get("symbol", "")
        hold_side = pos.get("holdSide", "")
        size      = safe_float(pos.get("total", 0))
        avg_price = safe_float(pos.get("openPriceAvg", 0))
        mark_price= safe_float(pos.get("markPrice", avg_price))
        leverage  = safe_float(pos.get("leverage", 1))
        margin    = safe_float(pos.get("marginSize", 0))
        unrealized= safe_float(pos.get("unrealizedPL", 0))
        total_fee = safe_float(pos.get("totalFee", 0))
        liq_price = safe_float(pos.get("liquidationPrice", 0))
        pos_value  = size * mark_price
        pnl_pct    = (unrealized / margin * 100) if margin > 0 else 0.0
        total_unr += unrealized

        fr = funding_rates.get(symbol, 0.0001)
        fund_8h = pos_value * abs(fr)
        total_fund += fund_8h

        dir_str = "🟢 <b>LONG</b>" if hold_side == "long" else "🔴 <b>SHORT</b>"
        pnl_e   = "🟢" if unrealized > 0 else ("🔴" if unrealized < 0 else "⚪")
        c_time  = pos.get("cTime", "")
        time_str = datetime.fromtimestamp(int(c_time)/1000, tz=timezone.utc).strftime("%m/%d %H:%M") if c_time else "—"

        # Current mark vs entry %
        mark_pct_str = _pct(mark_price, avg_price) if avg_price > 0 else ""

        # Get TP/SL from plan_map
        key = f"{symbol}-{hold_side}"
        plans = plan_map.get(key, [])
        tps, sls = [], []
        for p in plans:
            pt = p.get("planType", "")
            trig = safe_float(p.get("triggerPrice", 0))
            if ("profit" in pt) and trig > 0:
                tps.append(trig)
            elif ("loss" in pt) and trig > 0:
                sls.append(trig)
        tps.sort(reverse=(hold_side == "long"))
        sls.sort()

        lines.append(
            f"\n{'─'*28}\n"
            f"💎 <b>{symbol}</b> — {dir_str}\n"
            f"📈 <b>Kirish:</b>     <code>${fmt_price(avg_price)}</code>\n"
            f"💹 <b>Mark narx:</b>  <code>${fmt_price(mark_price)}</code>  ({mark_pct_str})\n"
            f"📦 <b>Hajm:</b>       <code>{size} ≈ {pos_value:.2f} USDT</code>\n"
            f"⚡ <b>Leverage:</b>   <code>{int(leverage)}x</code>  🔒 <code>{margin:.4f} USDT</code>\n"
            f"{pnl_e} <b>PnL:</b> <code>{unrealized:+.4f} USDT</code> (<code>{pnl_pct:+.2f}%</code>)\n"
        )

        # TP levels with % from entry
        if tps:
            for i, tp in enumerate(tps[:2], 1):
                tp_pct_str = _pct(tp, avg_price) if avg_price > 0 else ""
                pct_label = f"80%" if i == 1 else f"20%"
                lines.append(f"💚 <b>TP{i} ({pct_label}):</b> <code>${fmt_price(tp)}</code>  ({tp_pct_str})")
        else:
            lines.append(f"💚 <b>TP:</b> <code>Qo'yilmagan</code>")

        # SL level with % from entry
        if sls:
            sl_pct_str = _pct(sls[0], avg_price) if avg_price > 0 else ""
            lines.append(f"🛑 <b>SL:</b>  <code>${fmt_price(sls[0])}</code>  ({sl_pct_str})")
        else:
            lines.append(f"🛑 <b>SL:</b>  <code>Qo'yilmagan</code>")

        lines.append(
            f"💸 <b>8H Funding:</b> <code>-{fund_8h:.4f} USDT</code>  "
            f"🏦 <code>-{abs(total_fee):.4f}</code>\n"
            f"💣 <b>Lik. narxi:</b> <code>${fmt_price(liq_price)}</code>  "
            f"🕒 <code>{time_str}</code>"
        )

    lines.append(f"\n{'─'*28}")
    pnl_e = "🟢" if total_unr > 0 else "🔴"
    lines.append(f"{pnl_e} <b>Jami PnL:</b> <code>{total_unr:+.4f} USDT</code>")
    lines.append(f"💸 <b>Jami 8H Funding:</b> <code>-{total_fund:.4f} USDT</code>")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun", callback_data="fut_hist_today"),
         InlineKeyboardButton("📆 7 Kun", callback_data="fut_hist_7d"),
         InlineKeyboardButton("🗓️ 30 Kun", callback_data="fut_hist_30d")],
        [InlineKeyboardButton("📋 Hammasi", callback_data="fut_hist_all"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_futures_history(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "today"):
    query = update.callback_query
    await query.answer("📜 Yuklanmoqda...")
    now_ms = int(time.time() * 1000)
    labels = {"today": "BUGUNGI TARIX", "7d": "7 KUNLIK TARIX",
              "30d": "30 KUNLIK TARIX", "all": "BARCHA TARIX"}
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
    """Show top signals 70%+ with charts."""
    query = update.callback_query
    await query.answer("🔍 Skanerlayapti...")
    loading = (
        "🔍 <b>AI SIGNALLAR SKANERLANMOQDA...</b>\n\n"
        "📊 BTC, ETH, BNB, SOL, XRP va boshqalar...\n"
        "🧠 RSI, MACD, EMA, ADX, Supertrend, SMC...\n\n"
        "⏳ <i>20–30 soniya kuting...</i>"
    )
    await query.edit_message_text(loading, parse_mode="HTML")

    try:
        from services.trading_engine import TradingEngine
        engine  = TradingEngine(client)
        signals = await engine.get_top_signals(10, min_conf=70)
        text    = format_top_signals(signals)
    except Exception as e:
        text = f"❌ <b>Xato:</b>\n<code>{str(e)[:200]}</code>"
        signals = []

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="fut_signals"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures")]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

    # Send chart for top signal with "Savdoga Kirish" button
    if signals:
        top_sig = signals[0]
        try:
            candles = client.get_futures_candles(top_sig["symbol"], "1H", 100)
            if candles.get("code") == "00000":
                from services.chart_generator import generate_signal_chart
                from services.analyzer import estimate_trade_duration
                from services import state as gs
                tf = top_sig.get("timeframe", "1H")
                dur = estimate_trade_duration(tf, top_sig["confidence"])
                buf = generate_signal_chart(
                    candles_data=candles.get("data", []),
                    symbol=top_sig["symbol"],
                    direction=top_sig["direction"],
                    entry=top_sig["entry"],
                    tp1=top_sig["tp1"],
                    tp2=top_sig["tp2"],
                    sl=top_sig["sl"],
                    confidence=top_sig["confidence"],
                    timeframe=tf,
                    duration_label=dur,
                )
                chart_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "💰 Savdoga Kirish",
                        callback_data=f"manual_trade_{top_sig['symbol']}"
                    )
                ]])
                gs.pending_manual_trades[top_sig["symbol"]] = top_sig
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"📊 Eng yuqori signal: {top_sig['symbol']} {top_sig['confidence']}%  |  ⌛ {dur}",
                    reply_markup=chart_kb
                )
        except Exception as e:
            pass

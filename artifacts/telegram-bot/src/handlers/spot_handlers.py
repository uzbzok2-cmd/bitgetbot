"""Spot section handlers — balans, kripto, signallar, statistika, portfolio."""
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.bitget_client import BitgetClient
from services.analyzer import safe_float, analyze_symbol
from utils.formatters import (
    format_spot_balance, format_spot_assets, format_open_orders,
    format_history, format_top_signals, fmt_price, _pct, format_statistics,
    format_spot_portfolio
)

client = BitgetClient()


def spot_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Balans (USDT)", callback_data="spot_balance"),
         InlineKeyboardButton("📊 Kripto Balans", callback_data="spot_assets")],
        [InlineKeyboardButton("📋 Faol Orderlar", callback_data="spot_open_orders"),
         InlineKeyboardButton("📜 Tarix", callback_data="spot_history")],
        [InlineKeyboardButton("🏆 Spot Signallar", callback_data="spot_signals"),
         InlineKeyboardButton("📉 Statistika", callback_data="spot_stats_1d")],
        [InlineKeyboardButton("💹 Portfolio Tahlil", callback_data="spot_portfolio"),
         InlineKeyboardButton("📊 Portfolio Rasm", callback_data="spot_portfolio_chart")],
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


def spot_stats_keyboard(active: str = "1d"):
    periods = [("📅 1 Kun", "spot_stats_1d"), ("📆 7 Kun", "spot_stats_7d"), ("🗓️ 30 Kun", "spot_stats_30d")]
    row = []
    for label, cb in periods:
        btn_label = f"✅ {label}" if cb == f"spot_stats_{active}" else label
        row.append(InlineKeyboardButton(btn_label, callback_data=cb))
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"spot_stats_{active}"),
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
        "📜 <b>Tarix</b> — Savdo tarixi\n"
        "🏆 <b>Spot Signallar</b> — 70%+ BUY/SELL\n"
        "📉 <b>Statistika</b> — 1/7/30 kun\n"
        "💹 <b>Portfolio Tahlil</b> — Foyda/zarar foiz"
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


async def handle_spot_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spot 70%+ signallar — BUY ham SELL ham."""
    query = update.callback_query
    await query.answer("🔍 Skanerlayapti...")

    loading = (
        "🔍 <b>SPOT SIGNALLAR SKANERLANMOQDA...</b>\n\n"
        "📊 Top 20 spot juft...\n"
        "🧠 RSI, MACD, EMA, Supertrend...\n\n"
        "⏳ <i>20–30 soniya kuting...</i>"
    )
    await query.edit_message_text(loading, parse_mode="HTML")

    signals = []
    try:
        # Top 20 spot juftlarni olish
        tickers_data = client.get_spot_tickers()
        spot_symbols = []
        if tickers_data.get("code") == "00000":
            tickers = tickers_data.get("data", [])
            usdt_pairs = [
                t for t in tickers
                if str(t.get("symbol", "")).endswith("USDT")
                and safe_float(t.get("usdtVol", t.get("quoteVolume", 0))) > 100_000
            ]
            usdt_pairs.sort(
                key=lambda x: safe_float(x.get("usdtVol", x.get("quoteVolume", 0))),
                reverse=True
            )
            spot_symbols = [t["symbol"] for t in usdt_pairs[:20]]

        import asyncio
        for sym in spot_symbols:
            try:
                candles = client.get_spot_candles(sym, "1H", 150)
                if candles.get("code") == "00000" and candles.get("data"):
                    sig = analyze_symbol(candles["data"], sym, "1H")
                    if sig and sig["confidence"] >= 70:
                        signals.append(sig)
                await asyncio.sleep(0.3)
            except Exception:
                pass

        signals.sort(key=lambda x: x["confidence"], reverse=True)
    except Exception as e:
        signals = []

    if not signals:
        text = (
            "🏆 <b>SPOT SIGNALLAR</b>\n\n"
            "🔍 Hozir 70%+ kuchli signal yo'q\n"
            "Bozor skanerlanmoqda...\n\n"
            f"🕒 <code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>"
        )
    else:
        text = format_top_signals(signals[:10])

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="spot_signals"),
         InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
    ])

    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

    # Top signal uchun chart
    if signals:
        top = signals[0]
        try:
            candles = client.get_spot_candles(top["symbol"], "1H", 100)
            if candles.get("code") == "00000":
                from services.chart_generator import generate_signal_chart
                from services.analyzer import estimate_trade_duration
                from services import state as gs
                tf  = top.get("timeframe", "1H")
                dur = estimate_trade_duration(tf, top["confidence"])
                buf = generate_signal_chart(
                    candles_data=candles.get("data", []),
                    symbol=top["symbol"],
                    direction=top["direction"],
                    entry=top["entry"],
                    tp1=top["tp1"],
                    sl=top["sl"],
                    confidence=top["confidence"],
                    timeframe=tf,
                    duration_label=dur,
                )
                chart_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("💰 Savdoga Kirish", callback_data=f"spot_trade_{top['symbol']}")
                ]])
                gs.pending_manual_trades[top["symbol"]] = top
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"🏆 SPOT signal: {top['symbol']} {top['confidence']}%  |  ⌛ {dur}",
                    reply_markup=chart_kb
                )
        except Exception:
            pass


async def handle_spot_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str = "1d"):
    """Spot statistikasi."""
    query = update.callback_query
    if query:
        await query.answer("📊 Hisoblanmoqda...")

    now_ms = int(time.time() * 1000)
    labels = {"1d": "1 KUNLIK SPOT", "7d": "7 KUNLIK SPOT", "30d": "OYLIK SPOT"}
    label = labels.get(period, "1 KUNLIK SPOT")

    if period == "1d":
        start_ms = int(datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp() * 1000)
    elif period == "7d":
        start_ms = now_ms - 7 * 24 * 3600 * 1000
    else:
        start_ms = now_ms - 30 * 24 * 3600 * 1000

    data = client.get_spot_order_history(
        start_time=str(start_ms), end_time=str(now_ms), limit=200
    )
    orders = []
    if data.get("code") == "00000":
        d = data.get("data", {})
        orders = d.get("orderList", d.get("entrustedList", [])) if isinstance(d, dict) else (d or [])

    closed = [o for o in orders if o.get("status") in ("filled", "full_fill", "cancelled")]
    text = format_statistics(closed, label, equity=0)
    kb = spot_stats_keyboard(period)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spot portfolio tahlili — har bir kriptoning foyda/zarar foizi."""
    query = update.callback_query
    await query.answer("💹 Yuklanmoqda...")

    # Balans olish
    account = client.get_spot_account()
    tickers_data = client.get_spot_tickers()

    tickers = {}
    if tickers_data.get("code") == "00000":
        for t in tickers_data.get("data", []):
            tickers[t.get("symbol", "")] = t

    # Tarixdan o'rtacha kirish narxini hisoblash
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 90 * 24 * 3600 * 1000
    hist = client.get_spot_history(start_time=str(start_ms), end_time=str(now_ms), limit=500)
    fills = []
    if hist.get("code") == "00000":
        d = hist.get("data", {})
        fills = d.get("fillList", d) if isinstance(d, dict) else (d or [])
        if not isinstance(fills, list):
            fills = []

    # Coin bo'yicha VWAP hisoblash
    vwap: dict = {}
    for fill in fills:
        sym  = fill.get("symbol", "")
        side = str(fill.get("side", "")).lower()
        if not sym.endswith("USDT") or "buy" not in side:
            continue
        coin = sym.replace("USDT", "")
        price = safe_float(fill.get("fillPrice", fill.get("price", 0)))
        qty   = safe_float(fill.get("fillQuantity", fill.get("size", 0)))
        if price <= 0 or qty <= 0:
            continue
        if coin not in vwap:
            vwap[coin] = {"total_cost": 0.0, "total_qty": 0.0}
        vwap[coin]["total_cost"] += price * qty
        vwap[coin]["total_qty"]  += qty

    avg_prices = {}
    for coin, v in vwap.items():
        if v["total_qty"] > 0:
            avg_prices[coin] = v["total_cost"] / v["total_qty"]

    # Portfolio tuzish
    assets_info = []
    if account.get("code") == "00000":
        for asset in account.get("data", []):
            coin      = asset.get("coin", "")
            if coin == "USDT":
                continue
            available = safe_float(asset.get("available", 0))
            frozen    = safe_float(asset.get("frozen", 0))
            total_am  = available + frozen
            if total_am < 0.000001:
                continue

            sym        = f"{coin}USDT"
            ticker     = tickers.get(sym, {})
            cur_price  = safe_float(ticker.get("lastPr", ticker.get("close", 0)))
            usdt_value = total_am * cur_price if cur_price > 0 else safe_float(asset.get("usdtAmount", 0))

            avg_buy = avg_prices.get(coin, 0)
            invested = total_am * avg_buy if avg_buy > 0 else 0
            pnl_pct  = ((cur_price - avg_buy) / avg_buy * 100) if avg_buy > 0 and cur_price > 0 else 0

            assets_info.append({
                "coin":          coin,
                "amount":        total_am,
                "avg_buy_price": avg_buy,
                "current_price": cur_price,
                "usdt_value":    usdt_value,
                "invested_usdt": invested,
                "pnl_pct":       pnl_pct,
            })

    assets_info.sort(key=lambda x: x["usdt_value"], reverse=True)
    text = format_spot_portfolio(assets_info)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Grafik Ko'r", callback_data="spot_portfolio_chart"),
         InlineKeyboardButton("🔄 Yangilash", callback_data="spot_portfolio")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
    ])

    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_spot_portfolio_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spot portfolio pie chart + PnL bar chart."""
    query = update.callback_query
    await query.answer("📊 Grafik tayyorlanmoqda...")

    account = client.get_spot_account()
    tickers_data = client.get_spot_tickers()
    tickers = {}
    if tickers_data.get("code") == "00000":
        for t in tickers_data.get("data", []):
            tickers[t.get("symbol", "")] = t

    now_ms   = int(time.time() * 1000)
    start_ms = now_ms - 90 * 24 * 3600 * 1000
    hist = client.get_spot_history(start_time=str(start_ms), end_time=str(now_ms), limit=500)
    fills = []
    if hist.get("code") == "00000":
        d = hist.get("data", {})
        fills = d.get("fillList", d) if isinstance(d, dict) else (d or [])
        if not isinstance(fills, list):
            fills = []

    vwap: dict = {}
    for fill in fills:
        sym  = fill.get("symbol", "")
        side = str(fill.get("side", "")).lower()
        if not sym.endswith("USDT") or "buy" not in side:
            continue
        coin = sym.replace("USDT", "")
        price = safe_float(fill.get("fillPrice", fill.get("price", 0)))
        qty   = safe_float(fill.get("fillQuantity", fill.get("size", 0)))
        if price <= 0 or qty <= 0:
            continue
        if coin not in vwap:
            vwap[coin] = {"total_cost": 0.0, "total_qty": 0.0}
        vwap[coin]["total_cost"] += price * qty
        vwap[coin]["total_qty"]  += qty

    avg_prices = {c: v["total_cost"]/v["total_qty"] for c, v in vwap.items() if v["total_qty"] > 0}

    assets_info = []
    if account.get("code") == "00000":
        for asset in account.get("data", []):
            coin     = asset.get("coin", "")
            if coin == "USDT":
                continue
            total_am = safe_float(asset.get("available", 0)) + safe_float(asset.get("frozen", 0))
            if total_am < 0.000001:
                continue
            sym       = f"{coin}USDT"
            ticker    = tickers.get(sym, {})
            cur_price = safe_float(ticker.get("lastPr", ticker.get("close", 0)))
            usdt_val  = total_am * cur_price if cur_price > 0 else safe_float(asset.get("usdtAmount", 0))
            avg_buy   = avg_prices.get(coin, 0)
            pnl_pct   = ((cur_price - avg_buy) / avg_buy * 100) if avg_buy > 0 and cur_price > 0 else 0
            assets_info.append({
                "coin": coin, "usdt_value": usdt_val, "pnl_pct": pnl_pct
            })

    assets_info.sort(key=lambda x: x["usdt_value"], reverse=True)

    try:
        from services.chart_generator import generate_spot_portfolio_chart
        buf = generate_spot_portfolio_chart(assets_info[:10])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💹 Matn Ko'r", callback_data="spot_portfolio"),
             InlineKeyboardButton("🔄 Yangilash", callback_data="spot_portfolio_chart")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")]
        ])
        await query.message.reply_photo(
            photo=buf,
            caption=f"📊 Spot Portfolio — {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
            reply_markup=kb
        )
        await query.answer()
    except Exception as e:
        await query.edit_message_text(
            f"❌ Grafik xatosi: <code>{str(e)[:100]}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="section_spot")
            ]])
        )

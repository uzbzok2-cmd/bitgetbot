"""Message formatters — premium Telegram bot messages."""
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
from services.analyzer import safe_float


def ts_to_date(ts_ms, fmt="%Y-%m-%d %H:%M") -> str:
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).strftime(fmt)
    except Exception:
        return str(ts_ms)


def pnl_emoji(pnl: float) -> str:
    return "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")


def confidence_bar(conf: int, width: int = 10) -> str:
    filled = max(0, min(width, int(conf / 10)))
    return "█" * filled + "░" * (width - filled)


def fmt_price(p: float) -> str:
    if p == 0:
        return "0"
    if p >= 1000:
        return f"{p:,.2f}"
    elif p >= 1:
        return f"{p:.4f}"
    elif p >= 0.01:
        return f"{p:.6f}"
    return f"{p:.8f}"


# ─────────────────────────────────────────────────────────────
# FUTURES BALANCE
# ─────────────────────────────────────────────────────────────
def format_futures_balance(account_data: dict) -> str:
    if not account_data or account_data.get("code") != "00000":
        return "❌ <b>Balans ma'lumoti olinmadi</b>"
    d = account_data.get("data", {})
    equity    = safe_float(d.get("usdtEquity", d.get("equity", 0)))
    available = safe_float(d.get("available", 0))
    frozen    = safe_float(d.get("frozen", d.get("locked", 0)))
    unrealized= safe_float(d.get("unrealizedPL", 0))
    used_margin = safe_float(d.get("crossedUnrealizedPL", 0))
    pnl_e = pnl_emoji(unrealized)
    return (
        f"💼 <b>FYUCHERS HISOBI</b>\n"
        f"{'─'*28}\n"
        f"💰 <b>Jami kapital:</b>   <code>{equity:.4f} USDT</code>\n"
        f"✅ <b>Erkin balans:</b>   <code>{available:.4f} USDT</code>\n"
        f"🔒 <b>Marja (qulf):</b>  <code>{frozen:.4f} USDT</code>\n"
        f"{pnl_e} <b>Floating PnL:</b>  <code>{unrealized:+.4f} USDT</code>\n"
        f"{'─'*28}\n"
        f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>"
    )


# ─────────────────────────────────────────────────────────────
# SPOT BALANCE
# ─────────────────────────────────────────────────────────────
def format_spot_balance(account_data: dict) -> str:
    if not account_data or account_data.get("code") != "00000":
        return "❌ <b>Spot balans ma'lumoti olinmadi</b>"
    assets = account_data.get("data", [])
    lines = [f"💼 <b>SPOT HISOBI</b>\n{'─'*28}"]
    total_usdt = 0.0
    for asset in assets:
        coin      = asset.get("coin", "")
        available = safe_float(asset.get("available", 0))
        frozen    = safe_float(asset.get("frozen", 0))
        usd_value = safe_float(asset.get("usdtAmount", available))
        if usd_value < 0.01 and available < 0.00001:
            continue
        total_usdt += usd_value
        freeze_str = f" 🔒<code>{frozen:.6f}</code>" if frozen > 0 else ""
        lines.append(
            f"🪙 <b>{coin}</b>: <code>{available:.6f}</code>{freeze_str}"
            f" ≈ <code>{usd_value:.2f} USDT</code>"
        )
    lines += [f"{'─'*28}", f"💵 <b>Jami:</b> <code>{total_usdt:.2f} USDT</code>",
              f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>"]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# OPEN POSITIONS (fixed field names + total funding)
# ─────────────────────────────────────────────────────────────
def format_open_positions(positions_data: dict, funding_rates: dict = None) -> str:
    if not positions_data or positions_data.get("code") != "00000":
        return "❌ <b>Ochiq pozitsiyalar olinmadi</b>"
    positions = [p for p in positions_data.get("data", []) if safe_float(p.get("total", 0)) > 0]
    if not positions:
        return "📭 <b>Hozir ochiq pozitsiyalar yo'q</b>"

    lines = [f"📊 <b>OCHIQ POZITSIYALAR</b> ({len(positions)} ta)\n{'─'*28}"]
    total_unrealized = 0.0
    total_funding_8h = 0.0

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

        # Position value = size × markPrice
        pos_value_usdt = size * mark_price

        # PnL %
        pnl_pct = (unrealized / margin * 100) if margin > 0 else 0.0
        total_unrealized += unrealized

        # 8H funding estimate: ~0.01% per 8h of position value
        fr = 0.0001
        if funding_rates and symbol in funding_rates:
            fr = safe_float(funding_rates[symbol])
        funding_8h = pos_value_usdt * abs(fr)
        total_funding_8h += funding_8h

        dir_str = "🟢 <b>LONG</b>" if hold_side == "long" else "🔴 <b>SHORT</b>"
        pnl_e   = pnl_emoji(unrealized)

        # Open time
        c_time = pos.get("cTime", "")
        time_str = ts_to_date(c_time, "%m/%d %H:%M") if c_time else "—"

        lines.append(
            f"\n{'─'*28}\n"
            f"💎 <b>{symbol}</b> — {dir_str}\n"
            f"📈 <b>Kirish:</b>  <code>${fmt_price(avg_price)}</code>\n"
            f"💹 <b>Mark narx:</b> <code>${fmt_price(mark_price)}</code>\n"
            f"📦 <b>Hajm:</b>   <code>{size} ({pos_value_usdt:.2f} USDT)</code>\n"
            f"⚡ <b>Leverage:</b> <code>{int(leverage)}x</code>  🔒 <b>Marja:</b> <code>{margin:.4f} USDT</code>\n"
            f"{pnl_e} <b>PnL:</b> <code>{unrealized:+.4f} USDT</code> (<code>{pnl_pct:+.2f}%</code>)\n"
            f"💸 <b>8H funding:</b> <code>-{funding_8h:.4f} USDT</code>  |  "
            f"🏦 <b>Fee:</b> <code>-{abs(total_fee):.4f} USDT</code>\n"
            f"💣 <b>Lik. narxi:</b> <code>${fmt_price(liq_price)}</code>  🕒 <code>{time_str}</code>"
        )

    lines.append(f"\n{'─'*28}")
    pnl_e = pnl_emoji(total_unrealized)
    lines.append(f"{pnl_e} <b>Jami PnL:</b> <code>{total_unrealized:+.4f} USDT</code>")
    lines.append(f"💸 <b>Jami 8H funding:</b> <code>-{total_funding_8h:.4f} USDT</code>")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# OPEN ORDERS
# ─────────────────────────────────────────────────────────────
def format_open_orders(orders_data: dict, plan_orders: dict = None) -> str:
    lines = [f"📋 <b>FAOL ORDERLAR</b>\n{'─'*28}"]
    count = 0
    if orders_data and orders_data.get("code") == "00000":
        order_list = orders_data.get("data") or []
        if isinstance(order_list, dict):
            order_list = order_list.get("entrustedList", [])
        if not isinstance(order_list, list):
            order_list = []
        for order in order_list:
            symbol = order.get("symbol", "")
            side   = order.get("side", "")
            size   = safe_float(order.get("size", 0))
            price  = safe_float(order.get("price", 0))
            filled = safe_float(order.get("baseVolume", 0))
            otype  = order.get("orderType", "")
            ct     = order.get("cTime", "")
            side_e = "🟢 BUY" if "buy" in side.lower() else "🔴 SELL"
            lines.append(
                f"\n💎 <b>{symbol}</b> — {side_e}\n"
                f"🏷️ Narx: <code>{fmt_price(price)}</code>  📦 Hajm: <code>{size}</code>\n"
                f"✅ Bajarildi: <code>{filled}</code>  ⚙️ <code>{otype}</code>\n"
                f"🕒 <code>{ts_to_date(ct)}</code>"
            )
            count += 1
    if plan_orders and plan_orders.get("code") == "00000":
        plan_list = plan_orders.get("data") or []
        if isinstance(plan_list, dict):
            plan_list = plan_list.get("entrustedList", [])
        if not isinstance(plan_list, list):
            plan_list = []
        for order in plan_list:
            symbol    = order.get("symbol", "")
            plan_type = order.get("planType", "")
            trigger   = safe_float(order.get("triggerPrice", 0))
            size      = safe_float(order.get("size", 0))
            hold_side = order.get("holdSide", "")
            icon = "💚 TP" if "profit" in plan_type else "🛑 SL"
            lines.append(
                f"\n{icon} <b>{symbol}</b>  <code>{hold_side.upper()}</code>\n"
                f"🎯 Trigger: <code>{fmt_price(trigger)}</code>  📦 Hajm: <code>{size}</code>"
            )
            count += 1
    if count == 0:
        return "📭 <b>Faol orderlar yo'q</b>"
    lines.append(f"\n{'─'*28}\n<b>Jami:</b> {count} ta")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# TP/SL ORDERS
# ─────────────────────────────────────────────────────────────
def format_tp_sl_orders(plan_orders: dict) -> str:
    if not plan_orders or plan_orders.get("code") != "00000":
        return "❌ <b>TP/SL ma'lumoti olinmadi</b>"
    plan_list = plan_orders.get("data") or []
    if isinstance(plan_list, dict):
        plan_list = plan_list.get("entrustedList", [])
    if not isinstance(plan_list, list):
        plan_list = []
    if not plan_list:
        return "📭 <b>TP/SL orderlar yo'q</b>"
    lines = [f"🎯 <b>TP/SL ORDERLAR</b> ({len(plan_list)} ta)\n{'─'*28}"]
    for order in plan_list:
        symbol    = order.get("symbol", "")
        plan_type = order.get("planType", "")
        trigger   = safe_float(order.get("triggerPrice", 0))
        size      = safe_float(order.get("size", 0))
        hold_side = order.get("holdSide", "")
        ct        = order.get("cTime", "")
        if "profit" in plan_type:
            icon, label = "💚", "TAKE PROFIT"
        else:
            icon, label = "🛑", "STOP LOSS"
        lines.append(
            f"\n{icon} <b>{label}</b> — <b>{symbol}</b>\n"
            f"🎯 Trigger: <code>{fmt_price(trigger)}</code>  📦 Hajm: <code>{size}</code>\n"
            f"📌 <code>{hold_side.upper()}</code>  🕒 <code>{ts_to_date(ct)}</code>"
        )
    lines.append(f"\n{'─'*28}\n🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────────────────────
def format_history(orders: list, period_label: str = "TARIX", trade_type: str = "futures") -> str:
    if not orders:
        return f"📭 <b>{period_label} bo'yicha tarix yo'q</b>"
    total_pnl = 0.0
    total_fee = 0.0
    win_count = loss_count = 0
    lines = [f"📜 <b>{period_label}</b> ({len(orders)} ta)\n{'─'*28}"]
    for order in orders[:50]:
        if trade_type == "futures":
            symbol = order.get("symbol", "")
            side   = order.get("side", "")
            price  = safe_float(order.get("price", order.get("fillPrice", 0)))
            size   = safe_float(order.get("baseVolume", order.get("size", 0)))
            pnl    = safe_float(order.get("profit", order.get("realizedPL", 0)))
            fee    = safe_float(order.get("fee", 0))
            ct     = order.get("cTime", order.get("fillTime", ""))
            hold   = order.get("tradeSide", order.get("holdSide", ""))
        else:
            symbol = order.get("symbol", "")
            side   = order.get("side", "")
            price  = safe_float(order.get("fillPrice", order.get("priceAvg", 0)))
            size   = safe_float(order.get("fillQuantity", order.get("size", 0)))
            pnl    = safe_float(order.get("profit", 0))
            fee    = safe_float(order.get("feeDetail", {}).get("totalFee", 0))
            ct     = order.get("cTime", "")
            hold   = side
        net = pnl - abs(fee)
        total_pnl += net
        total_fee += abs(fee)
        if net > 0:
            win_count += 1; res = "✅ TP"
        elif net < 0:
            loss_count += 1; res = "❌ SL"
        else:
            res = "⚪ BEQ"
        side_str = "🟢 LONG" if "buy" in str(side).lower() or "long" in str(hold).lower() else "🔴 SHORT"
        lines.append(
            f"\n{pnl_emoji(net)} <b>{symbol}</b> {side_str} {res}\n"
            f"📅 <code>{ts_to_date(ct)}</code>\n"
            f"💲 <code>{fmt_price(price)}</code>  📦 <code>{size}</code>\n"
            f"💰 Net: <code>{net:+.4f} USDT</code>  🏦 Fee: <code>-{abs(fee):.4f}</code>"
        )
    total = win_count + loss_count
    wr = (win_count / total * 100) if total > 0 else 0
    lines += [
        f"\n{'─'*28}",
        f"{pnl_emoji(total_pnl)} <b>Jami PnL:</b> <code>{total_pnl:+.4f} USDT</code>",
        f"🏆 <b>Win Rate:</b> <code>{wr:.1f}%</code>  ({win_count}✅ / {loss_count}❌)",
        f"🏦 <b>Jami Fee:</b> <code>-{total_fee:.4f} USDT</code>",
        f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# TOP SIGNALS  (screenshot format)
# ─────────────────────────────────────────────────────────────
def format_top_signals(signals: List[Dict]) -> str:
    if not signals:
        return (
            "📊 <b>BUGUNGI SIGNALLAR</b>\n\n"
            "🔍 Hozir kuchli signal yo'q\n"
            "Bozor skanerlanmoqda...\n\n"
            f"🕒 <code>{datetime.now(timezone.utc).strftime('%d/%m/%Y, %H:%M:%S')}</code>"
        )
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y, %H:%M:%S")
    lines = [f"🔥 <b>BUGUNGI SIGNALLAR</b>\n{now_str}\n{'─'*28}"]

    long_sigs  = [s for s in signals if s["direction"] == "LONG"]
    short_sigs = [s for s in signals if s["direction"] == "SHORT"]
    neut_sigs  = [s for s in signals if s.get("confidence", 0) < 60]

    if long_sigs:
        lines.append("\n🟢 <b>XARID (BUY):</b>")
        for sig in long_sigs:
            symbol = sig["symbol"]
            conf   = sig["confidence"]
            entry  = sig["entry"]
            el     = sig.get("entry_low",  round(entry * 0.998, 6))
            eh     = sig.get("entry_high", round(entry * 1.002, 6))
            tp1    = sig["tp1"]
            tp2    = sig["tp2"]
            sl     = sig["sl"]
            rr     = sig.get("risk_reward", 1.0)
            lines.append(
                f"• <b>{symbol}</b> — <b>{conf}% ishonch</b>\n"
                f"  💰 ${fmt_price(entry)} | Kirish: ${fmt_price(el)}–${fmt_price(eh)}\n"
                f"  ✅ TP1: ${fmt_price(tp1)} | TP2: ${fmt_price(tp2)}\n"
                f"  🔴 SL: ${fmt_price(sl)} | ⚖️ R:R 1:{rr}"
            )

    if short_sigs:
        lines.append("\n🔴 <b>SOTISH (SELL):</b>")
        for sig in short_sigs:
            symbol = sig["symbol"]
            conf   = sig["confidence"]
            entry  = sig["entry"]
            el     = sig.get("entry_low",  round(entry * 0.998, 6))
            eh     = sig.get("entry_high", round(entry * 1.002, 6))
            tp1    = sig["tp1"]
            tp2    = sig["tp2"]
            sl     = sig["sl"]
            rr     = sig.get("risk_reward", 1.0)
            lines.append(
                f"• <b>{symbol}</b> — <b>{conf}% ishonch</b>\n"
                f"  💰 ${fmt_price(entry)} | Kirish: ${fmt_price(el)}–${fmt_price(eh)}\n"
                f"  ✅ TP1: ${fmt_price(tp1)} | TP2: ${fmt_price(tp2)}\n"
                f"  🔴 SL: ${fmt_price(sl)} | ⚖️ R:R 1:{rr}"
            )

    if neut_sigs:
        names = ", ".join(s["symbol"] for s in neut_sigs[:5])
        lines.append(f"\n🟡 <b>NEYTRAL:</b> {names}")

    lines.append(f"\n{'─'*28}\n🕒 <i>Yangilandi: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SINGLE SIGNAL DETAIL  (second screenshot format)
# ─────────────────────────────────────────────────────────────
def format_signal_detail(sig: Dict) -> str:
    from services.analyzer import estimate_trade_duration
    symbol  = sig["symbol"]
    conf    = sig["confidence"]
    entry   = sig["entry"]
    el      = sig.get("entry_low",  round(entry * 0.998, 8))
    eh      = sig.get("entry_high", round(entry * 1.002, 8))
    tp1     = sig["tp1"]
    tp2     = sig["tp2"]
    sl      = sig["sl"]
    rsi     = sig.get("rsi", 0)
    macd_h  = sig.get("macd_hist", 0)
    rr      = sig.get("risk_reward", 1.0)
    vol     = sig.get("volume_ratio", 1.0)
    supp    = sig.get("support", 0)
    resist  = sig.get("resistance", 0)
    trend   = sig.get("trend_dir", "sideways")
    ch24    = sig.get("change_24h", 0)
    reasons = sig.get("reasons", [])
    tf      = sig.get("timeframe", "1H")
    dir_    = sig["direction"]
    dir_e   = "🟢 XARID (BUY)" if dir_ == "LONG" else "🔴 SOTISH (SELL)"
    macd_e  = "✅ Ijobiy" if macd_h > 0 else "❌ Salbiy"
    vol_e   = "📈 Yuqori" if vol > 1.2 else ("😴 Past" if vol < 0.8 else "➡️ Normal")
    trend_map = {"up": "⬆️ O'sish", "down": "⬇️ Pasayish", "sideways": "➡️ Yon"}
    trend_str = trend_map.get(trend, "➡️ Yon")
    conf_bar = confidence_bar(conf)
    duration = estimate_trade_duration(tf, conf)
    lines = [
        f"🌐 <b>{symbol}</b>\n{'─'*28}",
        f"💲 Narx: <b>${fmt_price(entry)}</b>",
        f"📊 24s: <code>{ch24:+.2f}%</code>",
        f"\n🎯 <b>SIGNAL: {dir_e}</b>",
        f"📐 Ishonch: <b>{conf}%</b>",
        f"<code>[{conf_bar}]</code>",
        f"⏱️ Vaqt oralig'i: <b>{tf}</b>  |  ⌛ Taxminiy muddat: <b>{duration}</b>",
        f"\n📌 <b>SAVDO ZONASI:</b>",
        f"🎯 Kirish: <code>${fmt_price(el)} — ${fmt_price(eh)}</code>",
        f"✅ Take Profit 1: <code>${fmt_price(tp1)}</code>",
        f"✅ Take Profit 2: <code>${fmt_price(tp2)}</code>",
        f"🔴 Stop Loss: <code>${fmt_price(sl)}</code>",
        f"⚖️ Risk/Reward: <code>1:{rr}</code>",
        f"\n📊 Trend: {trend_str}",
        f"📈 RSI: <code>{rsi}</code>",
        f"📊 MACD: {macd_e}",
        f"📦 Hajm: {vol_e}",
        f"\n🟩 Support: <code>${fmt_price(supp)}</code>",
        f"🟥 Resistance: <code>${fmt_price(resist)}</code>",
    ]
    if reasons:
        lines.append("\n📋 <b>Tahlil:</b>")
        for r in reasons[:5]:
            lines.append(f"• {r}")
    lines.append(f"\n{'─'*28}\n🕒 <code>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC</code>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# AUTO-TRADE NOTIFICATION
# ─────────────────────────────────────────────────────────────
def format_auto_trade_notify(signal: Dict, leverage: int, size: float,
                              margin: float, tp1: float, tp2: float, sl: float,
                              order_id: str = "") -> str:
    from services.analyzer import estimate_trade_duration
    symbol  = signal["symbol"]
    dir_    = signal["direction"]
    conf    = signal["confidence"]
    entry   = signal["entry"]
    tf      = signal.get("timeframe", "1H")
    dir_e   = "🟢 LONG 📈" if dir_ == "LONG" else "🔴 SHORT 📉"
    conf_bar= confidence_bar(conf)
    reasons = signal.get("reasons", [])
    duration = estimate_trade_duration(tf, conf)
    lines = [
        f"🚨 <b>AI AVTOMATIK SAVDO!</b>",
        f"{'─'*28}",
        f"💎 <b>{symbol}</b> — {dir_e}",
        f"📊 Ishonch: <b>{conf}%</b>  <code>[{conf_bar}]</code>",
        f"⏱️ Vaqt oralig'i: <b>{tf}</b>  |  ⌛ Taxminiy muddat: <b>{duration}</b>",
        f"{'─'*28}",
        f"💲 <b>Kirish:</b> <code>${fmt_price(entry)}</code>",
        f"⚡ <b>Leverage:</b> <code>{leverage}x</code> (KROSS)",
        f"📦 <b>Hajm:</b> <code>{size:.4f}</code>",
        f"💳 <b>Marja:</b> <code>{margin:.2f} USDT</code>",
        f"🏋️ <b>Pozitsiya:</b> <code>{size * entry:.2f} USDT</code>",
        f"{'─'*28}",
        f"💚 <b>TP1:</b> <code>${fmt_price(tp1)}</code>",
        f"💚 <b>TP2:</b> <code>${fmt_price(tp2)}</code>",
        f"🛑 <b>SL:</b>  <code>${fmt_price(sl)}</code>",
        f"{'─'*28}",
    ]
    if reasons:
        lines.append(f"💡 {' • '.join(reasons[:3])}")
    if order_id:
        lines.append(f"🔢 Order ID: <code>{order_id[:16]}...</code>")
    lines.append(f"⏰ <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PERMISSION REQUEST (55-60% signal)
# ─────────────────────────────────────────────────────────────
def format_permission_request(signal: Dict, leverage: int, order_usdt: float,
                               tp1: float, tp2: float, sl: float) -> str:
    symbol  = signal["symbol"]
    dir_    = signal["direction"]
    conf    = signal["confidence"]
    entry   = signal["entry"]
    dir_e   = "🟢 LONG" if dir_ == "LONG" else "🔴 SHORT"
    est_profit = abs(tp1 - entry) * (order_usdt * leverage / entry)
    est_loss   = abs(sl - entry) * (order_usdt * leverage / entry)
    return (
        f"⚠️ <b>RUXSAT KERAK</b> — Signal {conf}% ishonch\n"
        f"{'─'*28}\n"
        f"💎 <b>{symbol}</b> — {dir_e}\n"
        f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
        f"⚡ Leverage: <code>{leverage}x</code>\n"
        f"💰 Order: <code>{order_usdt:.2f} USDT</code>\n"
        f"{'─'*28}\n"
        f"💚 TP1: <code>${fmt_price(tp1)}</code>\n"
        f"💚 TP2: <code>${fmt_price(tp2)}</code>\n"
        f"🛑 SL:  <code>${fmt_price(sl)}</code>\n"
        f"{'─'*28}\n"
        f"✅ <b>Mumkin foyda:</b> ~<code>{est_profit:.2f} USDT</code>\n"
        f"❌ <b>Mumkin zarar:</b> ~<code>{est_loss:.2f} USDT</code>\n"
        f"{'─'*28}\n"
        f"<b>Savdoga kirasizmi?</b>"
    )


# ─────────────────────────────────────────────────────────────
# SIGNAL HISTORY LIST
# ─────────────────────────────────────────────────────────────
def format_signal_history(signals: List[Dict], label: str = "SIGNAL TARIXI") -> str:
    if not signals:
        return f"📭 <b>{label} bo'sh</b>"
    lines = [f"📜 <b>{label}</b> ({len(signals)} ta)\n{'─'*28}"]
    for sig in signals[:30]:
        symbol  = sig.get("symbol", "")
        dir_    = sig.get("direction", "")
        conf    = sig.get("confidence", 0)
        entry   = sig.get("entry", 0)
        saved   = sig.get("saved_at_str", "—")
        dir_e   = "🟢" if dir_ == "LONG" else "🔴"
        lines.append(
            f"{dir_e} <b>{symbol}</b> {dir_} — <code>{conf}%</code>\n"
            f"  💲 ${fmt_price(entry)}  🕒 <code>{saved}</code>"
        )
    lines.append(f"\n{'─'*28}\n🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SPOT ASSETS WITH PRICE
# ─────────────────────────────────────────────────────────────
def format_spot_assets(account_data: dict, tickers: dict) -> str:
    if account_data.get("code") != "00000":
        return "❌ <b>Ma'lumot olinmadi</b>"
    assets = account_data.get("data", [])
    lines  = [f"📊 <b>SPOT KRIPTO BALANSI</b>\n{'─'*28}"]
    total  = 0.0
    for asset in assets:
        coin      = asset.get("coin", "")
        available = safe_float(asset.get("available", 0))
        frozen    = safe_float(asset.get("frozen", 0))
        usd_value = safe_float(asset.get("usdtAmount", 0))
        if usd_value < 0.1 and available < 0.00001:
            continue
        total += usd_value
        if coin == "USDT":
            lines.append(f"\n💵 <b>USDT</b>: <code>{available:.4f}</code> ≈ <code>{usd_value:.2f}$</code>")
            continue
        symbol  = f"{coin}USDT"
        ticker  = tickers.get(symbol, {})
        cur_p   = safe_float(ticker.get("lastPr", 0))
        ch24    = safe_float(ticker.get("change24h", 0)) * 100
        ch_icon = "📈" if ch24 > 0 else ("📉" if ch24 < 0 else "➡️")
        freeze_str = f" 🔒<code>{frozen:.6f}</code>" if frozen > 0 else ""
        lines.append(
            f"\n🪙 <b>{coin}</b>: <code>{available:.6f}</code>{freeze_str}\n"
            f"   💲 <code>${fmt_price(cur_p)}</code> {ch_icon} <code>{ch24:+.2f}%</code>"
            f" ≈ <code>{usd_value:.2f}$</code>"
        )
    lines += [f"\n{'─'*28}", f"💵 <b>Jami:</b> <code>{total:.2f} USDT</code>",
              f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>"]
    return "\n".join(lines)

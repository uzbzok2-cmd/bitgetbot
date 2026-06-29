"""
Message formatters for Telegram bot responses.
Professional, emoji-rich, bold formatting.
"""
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.analyzer import safe_float


def ts_to_date(ts_ms: str, fmt="%Y-%m-%d %H:%M") -> str:
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).strftime(fmt)
    except Exception:
        return str(ts_ms)


def pnl_emoji(pnl: float) -> str:
    if pnl > 0:
        return "🟢"
    elif pnl < 0:
        return "🔴"
    return "⚪"


def dir_emoji(direction: str) -> str:
    if direction in ("LONG", "long", "buy", "BUY"):
        return "🟢 LONG"
    return "🔴 SHORT"


def confidence_bar(conf: int) -> str:
    filled = int(conf / 10)
    return "█" * filled + "░" * (10 - filled)


def format_futures_balance(account_data: dict) -> str:
    if not account_data or account_data.get("code") != "00000":
        return "❌ <b>Balans ma'lumoti olinmadi</b>"
    d = account_data.get("data", {})
    equity = safe_float(d.get("usdtEquity", d.get("equity", 0)))
    available = safe_float(d.get("available", 0))
    frozen = safe_float(d.get("frozen", 0))
    unrealized = safe_float(d.get("unrealizedPL", 0))
    margin = safe_float(d.get("crossedMarginLeverage", d.get("crossMaxAvailableSize", 0)))

    pnl_e = pnl_emoji(unrealized)
    return (
        f"💼 <b>FYUCHERS HISOBI</b>\n"
        f"{'─'*28}\n"
        f"💰 <b>Jami kapital:</b> <code>{equity:.4f} USDT</code>\n"
        f"✅ <b>Erkin balans:</b> <code>{available:.4f} USDT</code>\n"
        f"🔒 <b>Ishlatilgan:</b> <code>{frozen:.4f} USDT</code>\n"
        f"{pnl_e} <b>Hozirgi PnL:</b> <code>{unrealized:+.4f} USDT</code>\n"
        f"📊 <b>Kross Leverage:</b> <code>{margin}x</code>\n"
        f"{'─'*28}\n"
        f"🕒 <i>Yangilandi: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>"
    )


def format_spot_balance(account_data: dict) -> str:
    if not account_data or account_data.get("code") != "00000":
        return "❌ <b>Spot balans ma'lumoti olinmadi</b>"
    assets = account_data.get("data", [])
    lines = ["💼 <b>SPOT HISOBI</b>\n" + "─" * 28]
    total_usdt = 0.0
    for asset in assets:
        coin = asset.get("coin", "")
        available = safe_float(asset.get("available", 0))
        frozen = safe_float(asset.get("frozen", 0))
        usd_value = safe_float(asset.get("usdtAmount", available))
        if usd_value < 0.01 and available < 0.0001:
            continue
        total_usdt += usd_value
        lines.append(
            f"🪙 <b>{coin}</b>: <code>{available:.6f}</code>"
            f" {'🔒 ' + str(round(frozen,6)) if frozen > 0 else ''}"
            f" ≈ <code>{usd_value:.2f} USDT</code>"
        )
    lines.append(f"{'─'*28}")
    lines.append(f"💵 <b>Jami qiymat:</b> <code>{total_usdt:.2f} USDT</code>")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_open_positions(positions_data: dict, tickers: dict = None) -> str:
    if not positions_data or positions_data.get("code") != "00000":
        return "❌ <b>Ochiq pozitsiyalar olinmadi</b>"
    positions = [p for p in positions_data.get("data", []) if safe_float(p.get("total", 0)) > 0]
    if not positions:
        return "📭 <b>Hozir ochiq pozitsiyalar yo'q</b>"

    lines = [f"📊 <b>OCHIQ POZITSIYALAR</b> ({len(positions)} ta)\n" + "─" * 28]
    for pos in positions:
        symbol = pos.get("symbol", "")
        hold_side = pos.get("holdSide", "")
        size = safe_float(pos.get("total", 0))
        avg_price = safe_float(pos.get("averageOpenPrice", 0))
        mark_price = safe_float(pos.get("markPrice", avg_price))
        leverage = safe_float(pos.get("leverage", 1))
        margin = safe_float(pos.get("margin", 0))
        unrealized = safe_float(pos.get("unrealizedPL", 0))
        pnl_pct = safe_float(pos.get("pnlRate", 0)) * 100

        # Calculate funding (8h rate estimate)
        funding_rate = 0.0001  # ~0.01% per 8h
        position_value = size * mark_price
        funding_cost = position_value * funding_rate

        direction_str = "🟢 <b>LONG</b>" if hold_side == "long" else "🔴 <b>SHORT</b>"
        pnl_e = pnl_emoji(unrealized)

        lines.append(
            f"\n{'─'*28}\n"
            f"💎 <b>{symbol}</b> — {direction_str}\n"
            f"📈 <b>Kirish narxi:</b> <code>{avg_price:.6f}</code>\n"
            f"💹 <b>Hozirgi narx:</b> <code>{mark_price:.6f}</code>\n"
            f"📦 <b>Hajm:</b> <code>{size}</code> kontrakt\n"
            f"⚡ <b>Leverage:</b> <code>{int(leverage)}x</code>\n"
            f"💳 <b>Marja:</b> <code>{margin:.4f} USDT</code>\n"
            f"🏋️ <b>Pozitsiya:</b> <code>{size * avg_price:.2f} USDT</code>\n"
            f"{pnl_e} <b>PnL:</b> <code>{unrealized:+.4f} USDT</code> "
            f"(<code>{pnl_pct:+.2f}%</code>)\n"
            f"💸 <b>8H funding:</b> <code>-{funding_cost:.4f} USDT</code>"
        )
    lines.append(f"\n{'─'*28}")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_open_orders(orders_data: dict, plan_orders: dict = None) -> str:
    lines = [f"📋 <b>FAOL ORDERLAR</b>\n" + "─" * 28]
    count = 0

    if orders_data and orders_data.get("code") == "00000":
        order_list = orders_data.get("data", {})
        if isinstance(order_list, dict):
            order_list = order_list.get("entrustedList", [])
        for order in order_list:
            symbol = order.get("symbol", "")
            side = order.get("side", "")
            size = safe_float(order.get("size", 0))
            price = safe_float(order.get("price", 0))
            filled = safe_float(order.get("baseVolume", 0))
            order_type = order.get("orderType", "")
            create_time = order.get("cTime", "")
            order_id = order.get("orderId", "")

            side_e = "🟢 BUY" if "buy" in side.lower() else "🔴 SELL"
            lines.append(
                f"\n💎 <b>{symbol}</b> — {side_e}\n"
                f"🏷️ <b>Narx:</b> <code>{price:.6f}</code>\n"
                f"📦 <b>Hajm:</b> <code>{size}</code>\n"
                f"✅ <b>Bajarildi:</b> <code>{filled}</code>\n"
                f"⚙️ <b>Tur:</b> <code>{order_type}</code>\n"
                f"🕒 <b>Vaqt:</b> <code>{ts_to_date(create_time)}</code>\n"
                f"🔢 <b>ID:</b> <code>{order_id[:12]}...</code>"
            )
            count += 1

    if plan_orders and plan_orders.get("code") == "00000":
        plan_list = plan_orders.get("data", {})
        if isinstance(plan_list, dict):
            plan_list = plan_list.get("entrustedList", [])
        for order in plan_list:
            symbol = order.get("symbol", "")
            plan_type = order.get("planType", "")
            trigger = safe_float(order.get("triggerPrice", 0))
            size = safe_float(order.get("size", 0))
            hold_side = order.get("holdSide", "")

            if "profit" in plan_type:
                icon = "💚 TP"
            elif "loss" in plan_type:
                icon = "🔴 SL"
            else:
                icon = "📌 PLAN"

            lines.append(
                f"\n{icon} <b>{symbol}</b>\n"
                f"🎯 <b>Trigger:</b> <code>{trigger:.6f}</code>\n"
                f"📦 <b>Hajm:</b> <code>{size}</code>\n"
                f"📌 <b>Tomoni:</b> <code>{hold_side}</code>"
            )
            count += 1

    if count == 0:
        return "📭 <b>Faol orderlar yo'q</b>"

    lines.append(f"\n{'─'*28}\n<b>Jami:</b> {count} ta order")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_tp_sl_orders(plan_orders: dict) -> str:
    if not plan_orders or plan_orders.get("code") != "00000":
        return "❌ <b>TP/SL ma'lumoti olinmadi</b>"
    plan_list = plan_orders.get("data", {})
    if isinstance(plan_list, dict):
        plan_list = plan_list.get("entrustedList", [])
    if not plan_list:
        return "📭 <b>TP/SL orderlar yo'q</b>"

    lines = [f"🎯 <b>TP/SL ORDERLAR</b> ({len(plan_list)} ta)\n" + "─" * 28]
    for order in plan_list:
        symbol = order.get("symbol", "")
        plan_type = order.get("planType", "")
        trigger = safe_float(order.get("triggerPrice", 0))
        size = safe_float(order.get("size", 0))
        hold_side = order.get("holdSide", "")
        create_time = order.get("cTime", "")

        if "profit" in plan_type:
            icon = "💚"
            label = "TAKE PROFIT"
        else:
            icon = "🛑"
            label = "STOP LOSS"

        lines.append(
            f"\n{icon} <b>{label}</b> — <b>{symbol}</b>\n"
            f"🎯 <b>Trigger narxi:</b> <code>{trigger:.6f}</code>\n"
            f"📦 <b>Hajm:</b> <code>{size}</code>\n"
            f"📌 <b>Yo'nalish:</b> <code>{hold_side.upper()}</code>\n"
            f"🕒 <b>Qo'yilgan:</b> <code>{ts_to_date(create_time)}</code>"
        )
    lines.append(f"\n{'─'*28}")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_history(orders: list, period_label: str = "TARIX", trade_type: str = "futures") -> str:
    if not orders:
        return f"📭 <b>{period_label} bo'yicha tarix yo'q</b>"

    total_pnl = 0.0
    total_commission = 0.0
    win_count = 0
    loss_count = 0
    lines = [f"📜 <b>{period_label}</b> ({len(orders)} ta trade)\n" + "─" * 28]

    for order in orders[:50]:
        if trade_type == "futures":
            symbol = order.get("symbol", "")
            side = order.get("side", "")
            price = safe_float(order.get("price", 0))
            size = safe_float(order.get("baseVolume", order.get("size", 0)))
            pnl = safe_float(order.get("profit", order.get("realizedPL", 0)))
            fee = safe_float(order.get("fee", order.get("feeDetail", {}).get("totalFee", 0)))
            create_time = order.get("cTime", order.get("fillTime", ""))
            hold_side = order.get("tradeSide", order.get("holdSide", ""))
        else:
            symbol = order.get("symbol", "")
            side = order.get("side", "")
            price = safe_float(order.get("fillPrice", order.get("price", 0)))
            size = safe_float(order.get("fillQuantity", order.get("size", 0)))
            pnl = safe_float(order.get("profit", 0))
            fee = safe_float(order.get("feeDetail", {}).get("totalFee", 0))
            create_time = order.get("cTime", order.get("fillTime", ""))
            hold_side = side

        net_pnl = pnl - abs(fee)
        total_pnl += net_pnl
        total_commission += abs(fee)

        if net_pnl > 0:
            win_count += 1
            result_icon = "✅ TP"
        elif net_pnl < 0:
            loss_count += 1
            result_icon = "❌ SL"
        else:
            result_icon = "⚪ BEQ"

        side_str = "🟢 LONG" if "buy" in str(side).lower() or "long" in str(hold_side).lower() else "🔴 SHORT"
        pnl_e = pnl_emoji(net_pnl)

        lines.append(
            f"\n{pnl_e} <b>{symbol}</b> {side_str} {result_icon}\n"
            f"📅 <code>{ts_to_date(create_time)}</code>\n"
            f"💲 <b>Narx:</b> <code>{price:.6f}</code> | <b>Hajm:</b> <code>{size}</code>\n"
            f"💰 <b>Net PnL:</b> <code>{net_pnl:+.4f} USDT</code> | "
            f"🏦 <b>Komissiya:</b> <code>-{abs(fee):.4f} USDT</code>"
        )

    win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0

    lines.append(f"\n{'─'*28}")
    pnl_e = pnl_emoji(total_pnl)
    lines.append(f"{pnl_e} <b>Jami PnL:</b> <code>{total_pnl:+.4f} USDT</code>")
    lines.append(f"🏆 <b>Win rate:</b> <code>{win_rate:.1f}%</code> ({win_count}✅/{loss_count}❌)")
    lines.append(f"🏦 <b>Jami komissiya:</b> <code>-{total_commission:.4f} USDT</code>")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_signal(signal: Dict, leverage: int = 1, size: float = 0,
                   margin: float = 0, tp1: float = 0, tp2: float = 0,
                   sl: float = 0, order_id: str = "") -> str:
    symbol = signal["symbol"]
    direction = signal["direction"]
    confidence = signal["confidence"]
    entry = signal["entry"]
    rsi = signal.get("rsi", 0)
    adx = signal.get("adx", 0)
    vol = signal.get("volume_ratio", 1)
    reasons = signal.get("reasons", [])

    dir_e = "🟢 LONG 📈" if direction == "LONG" else "🔴 SHORT 📉"
    conf_bar = confidence_bar(confidence)

    lines = [
        f"🚨 <b>YANGI SIGNAL!</b> — <b>{symbol}</b>",
        f"{'─'*28}",
        f"🎯 <b>Yo'nalish:</b> {dir_e}",
        f"📊 <b>Ishonch:</b> <code>{confidence}%</code>",
        f"<code>[{conf_bar}]</code>",
        f"{'─'*28}",
        f"💲 <b>Kirish:</b> <code>{entry:.6f}</code>",
        f"⚡ <b>Leverage:</b> <code>{leverage}x</code> (KROSS)",
        f"📦 <b>Hajm:</b> <code>{size:.4f}</code> kontrakt",
        f"💳 <b>Marja:</b> <code>{margin:.2f} USDT</code>",
        f"🏋️ <b>Pozitsiya:</b> <code>{size * entry:.2f} USDT</code>",
        f"{'─'*28}",
        f"💚 <b>TP1:</b> <code>{tp1:.6f}</code>",
        f"💚 <b>TP2:</b> <code>{tp2:.6f}</code>",
        f"🛑 <b>SL:</b> <code>{sl:.6f}</code>",
        f"{'─'*28}",
        f"📈 <b>RSI:</b> <code>{rsi:.1f}</code>  |  <b>ADX:</b> <code>{adx:.1f}</code>  |  <b>Vol:</b> <code>{vol:.1f}x</code>",
    ]
    if reasons:
        lines.append(f"💡 <b>Sabablar:</b> {' • '.join(reasons[:3])}")
    if order_id:
        lines.append(f"🔢 <b>Order ID:</b> <code>{order_id[:16]}...</code>")
    lines.append(f"{'─'*28}")
    lines.append(f"⏰ <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</code>")
    return "\n".join(lines)


def format_top_signals(signals: List[Dict]) -> str:
    if not signals:
        return "📊 <b>Hozir kuchli signal yo'q</b>\n\nBozor skanerlanmoqda..."
    lines = [f"🏆 <b>TOP SIGNALLAR</b> ({len(signals)} ta)\n" + "─" * 28]
    for i, sig in enumerate(signals[:10], 1):
        symbol = sig["symbol"]
        direction = sig["direction"]
        conf = sig["confidence"]
        entry = sig["entry"]
        tp1 = sig["tp1"]
        sl = sig["sl"]
        rr = sig.get("risk_reward", 1.0)
        conf_bar = confidence_bar(conf)

        dir_icon = "🟢" if direction == "LONG" else "🔴"
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"#{i}"

        lines.append(
            f"\n{medal} {dir_icon} <b>{symbol}</b> — {direction}\n"
            f"📊 <code>[{conf_bar}] {conf}%</code>\n"
            f"💲 Kirish: <code>{entry:.4f}</code> → TP: <code>{tp1:.4f}</code> | SL: <code>{sl:.4f}</code>\n"
            f"⚖️ RR: <code>1:{rr:.1f}</code>"
        )

    lines.append(f"\n{'─'*28}")
    lines.append(f"🕒 <i>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</i>")
    return "\n".join(lines)


def format_new_futures_order_notification(signal: Dict, leverage: int, size: float,
                                           margin: float, tp1: float, tp2: float, sl: float, order_id: str = "") -> str:
    return format_signal(signal, leverage, size, margin, tp1, tp2, sl, order_id)

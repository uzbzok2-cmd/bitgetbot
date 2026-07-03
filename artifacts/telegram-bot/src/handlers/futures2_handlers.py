"""
FYUCHERS 2 bo'limi — ZOKPAT Pattern Signals, Pozitsiyalar (tafsilotli), Tarix (sof PnL).
"""
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from utils.formatters import fmt_price, _pct, _pct_lev

client = BitgetClient()

# Taker fee har ikki tomonga 0.06%
TAKER_FEE = 0.0006


def futures2_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔮 ZOKPAT Signal", callback_data="f2_zokpat")],
        [InlineKeyboardButton("📊 Pozitsiyalar",   callback_data="f2_positions"),
         InlineKeyboardButton("📜 Pozitsiya Tarixi", callback_data="f2_history")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="section_futures2"),
         InlineKeyboardButton("🏠 Bosh",     callback_data="main_menu")],
    ])


async def show_futures2_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🚀 <b>FYUCHERS 2 — PATTERN TRADING</b>\n"
        "══════════════════════════════════\n\n"
        "🔮 <b>ZOKPAT Signal</b> — Chart pattern detector\n"
        "   └ Double Top/Bottom, Triple, H&S,\n"
        "     Rising/Falling Wedge, Triangle\n"
        "   └ 15m • 1H • 4H • 1D timeframes\n"
        "   └ 1:1 Risk:Reward kafolatlangan\n\n"
        "📊 <b>Pozitsiyalar</b> — Har biri alohida xabar\n"
        "   └ To'liq ma'lumot: hajm, marja, PnL,\n"
        "     zararsiz narx, likvid narx, TP/SL\n\n"
        "📜 <b>Pozitsiya Tarixi</b> — Sof foyda/zarar\n"
        "   └ Gross PnL − Komissiya − Funding\n\n"
        "👇 Bo'limni tanlang:"
    )
    await query.edit_message_text(text, reply_markup=futures2_main_keyboard(), parse_mode="HTML")


# ─── ZOKPAT Menu ───────────────────────────────────────────────────────────

async def handle_zokpat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from services import state as gs
    query = update.callback_query
    await query.answer()

    zokpat_icon = "🟢 YOQILGAN" if gs.zokpat_enabled else "🔴 O'CHIRILGAN"
    auto_icon   = "🟢 YOQILGAN" if gs.auto_trade_enabled else "🔴 O'CHIRILGAN"
    zokpat_btn  = "🔴 ZOKPAT O'chirish" if gs.zokpat_enabled else "🟢 ZOKPAT Yoqish"

    text = (
        f"🔮 <b>ZOKPAT PATTERN SIGNAL</b>\n{'═'*30}\n\n"
        f"📐 <b>Aniqlanadigan patternlar:</b>\n"
        f"├ 🔴 Double Top / Triple Top\n"
        f"├ 🟢 Double Bottom / Triple Bottom\n"
        f"├ 🔴 Head & Shoulders (H&S)\n"
        f"├ 🟢 Inverse Head & Shoulders\n"
        f"├ 🔴 Rising Wedge → SHORT\n"
        f"├ 🟢 Falling Wedge → LONG\n"
        f"├ 🟢 Ascending Triangle → LONG\n"
        f"├ 🔴 Descending Triangle → SHORT\n"
        f"└ ↔️ Symmetric Triangle\n\n"
        f"⏱️ <b>Timeframlar:</b> 15m • 1H • 4H • 1D\n"
        f"⚖️ <b>Risk:Reward:</b> 1:1 kafolatlangan\n"
        f"🎯 <b>Min ishonch:</b> 70%\n\n"
        f"{'─'*28}\n"
        f"🔮 <b>ZOKPAT Avtosavdo:</b> {zokpat_icon}\n"
        f"⚡ <b>Umumiy Avtosavdo:</b> {auto_icon}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(zokpat_btn, callback_data="toggle_zokpat")],
        [InlineKeyboardButton("🔍 Hozir Skan Qil", callback_data="zokpat_scan_now")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="section_futures2"),
         InlineKeyboardButton("🏠 Bosh",   callback_data="main_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_zokpat_scan_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔮 Skan boshlandi...")
    await query.edit_message_text(
        "🔮 <b>ZOKPAT skan qilinmoqda...</b>\n"
        "📐 Chart patternlar izlanmoqda...\n"
        "⏱️ 15m • 1H • 4H timeframlar\n"
        "<i>20-40 soniya kuting...</i>",
        parse_mode="HTML"
    )
    try:
        import builtins
        scanner = getattr(builtins, "_zokpat_scanner", None)
        if scanner is None:
            from handlers.zokpat_scanner import ZokpatScanner
            scanner = ZokpatScanner(client)
        result = await scanner.manual_scan_now()
    except Exception as e:
        result = f"❌ Xato: <code>{str(e)[:200]}</code>"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yana Skan", callback_data="zokpat_scan_now"),
         InlineKeyboardButton("🔙 Orqaga",    callback_data="f2_zokpat")],
    ])
    await query.edit_message_text(result, reply_markup=kb, parse_mode="HTML")


# ─── Pozitsiyalar (har biri alohida xabar) ──────────────────────────────────

def _breakeven(entry: float, hold_side: str) -> float:
    """Zararsiz narx = entry ± (open+close taker fee)."""
    if hold_side == "long":
        return entry * (1 + TAKER_FEE * 2)
    return entry * (1 - TAKER_FEE * 2)


def _format_single_position(pos: dict, plan_map: dict, funding_rates: dict) -> str:
    """Bitta pozitsiya uchun to'liq ma'lumot (Image 1 + Image 3 format)."""
    symbol    = pos.get("symbol", "")
    hold_side = pos.get("holdSide", "long")
    size      = safe_float(pos.get("total", 0))         # coin miqdori
    avg_price = safe_float(pos.get("openPriceAvg", 0))
    mark_price= safe_float(pos.get("markPrice", avg_price))
    leverage  = int(safe_float(pos.get("leverage", 1)))
    margin    = safe_float(pos.get("marginSize", 0))
    unrealized= safe_float(pos.get("unrealizedPL", 0))
    total_fee = safe_float(pos.get("totalFee", 0))      # manfiy (to'langan)
    realized  = safe_float(pos.get("achievedProfits", 0))
    liq_price = safe_float(pos.get("liquidationPrice", 0))
    pos_value  = size * mark_price
    breakeven  = _breakeven(avg_price, hold_side)

    # ROE (leverage bo'yicha)
    if margin > 0:
        roe = unrealized / margin * 100 * leverage
    else:
        roe = 0.0

    pnl_e  = "🟢" if unrealized >= 0 else "🔴"
    roe_e  = "🟢" if roe >= 0 else "🔴"
    dir_e  = "🟢 UZUN (LONG)" if hold_side == "long" else "🔴 QISQA (SHORT)"

    # TP / SL
    hs_key    = f"{symbol}-{hold_side}"
    plans     = plan_map.get(hs_key) or plan_map.get(symbol) or []
    tp_prices = []
    sl_prices = []
    for p in plans:
        pt = (p.get("planType") or "").lower()
        tp_trig = safe_float(p.get("triggerPrice", 0))
        if "profit" in pt and tp_trig > 0:
            tp_prices.append(tp_trig)
        elif "loss" in pt and tp_trig > 0:
            sl_prices.append(tp_trig)

    tp_str = " / ".join(f"${fmt_price(t)}" for t in tp_prices) if tp_prices else "—"
    sl_str = " / ".join(f"${fmt_price(s)}" for s in sl_prices) if sl_prices else "—"

    # Funding rate
    fr = funding_rates.get(symbol, 0.0001)
    fund_8h = pos_value * abs(fr)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"{'═'*32}",
        f"💎 <b>{symbol}</b>",
        f"📌 {dir_e} | ⚡ <b>{leverage}x</b> | 🔄 KROSS | 💵 USDT",
        f"{'─'*28}",
        f"{pnl_e} <b>Amalga oshirilmagan P/L:</b>",
        f"   <code>{unrealized:+.4f} USDT</code>  |  {roe_e} ROE: <code>{roe:+.2f}%</code>",
        f"{'─'*28}",
        f"📦 <b>Pozitsiya o'lchami:</b>  <code>{size:.4f} {symbol.replace('USDT','')}</code>",
        f"💲 <b>Kirish narxi:</b>        <code>${fmt_price(avg_price)}</code>",
        f"📍 <b>Belgilangan narx:</b>    <code>${fmt_price(mark_price)}</code>",
        f"⚖️ <b>Zararsiz narx:</b>       <code>${fmt_price(breakeven)}</code>",
        f"💰 <b>Pozitsiya qiymati:</b>   <code>{pos_value:.4f} USDT</code>",
        f"🏦 <b>Marja:</b>              <code>{margin:.4f} USDT</code>",
        f"{'─'*28}",
        f"💚 <b>To'liq TP/SL:</b>        <code>{tp_str} / {sl_str}</code>",
        f"💥 <b>Taxminiy likvid narx:</b> <code>${fmt_price(liq_price) if liq_price > 0 else '—'}</code>",
        f"{'─'*28}",
        f"💸 <b>Haq (to'langan):</b>     <code>{total_fee:.6f} USDT</code>",
        f"💱 <b>Funding (8H est):</b>    <code>~{fund_8h:.4f} USDT  ({fr*100:.4f}%)</code>",
        f"📈 <b>Amalga oshirilgan P/L:</b> <code>{realized:+.4f} USDT</code>",
        f"🕒 <b>Yangilash:</b>  <code>{now_str}</code>",
    ]
    return "\n".join(lines)


async def handle_f2_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har bir ochiq pozitsiyani alohida xabar sifatida yuborish."""
    query = update.callback_query
    await query.answer("📊 Yuklanmoqda...")

    await query.edit_message_text(
        "📊 <b>Ochiq pozitsiyalar yuklanmoqda...</b>\n<i>Iltimos kuting...</i>",
        parse_mode="HTML"
    )

    pos_data  = client.get_futures_positions()
    plan_data = client.get_futures_plan_orders()

    plan_map: dict = {}
    if plan_data.get("code") == "00000":
        plan_list = plan_data.get("data") or []
        if isinstance(plan_list, dict):
            plan_list = plan_list.get("entrustedList", [])
        if not isinstance(plan_list, list):
            plan_list = []
        for p in plan_list:
            sym = p.get("symbol", "")
            hs  = (p.get("holdSide") or "").lower().strip()
            if hs:
                plan_map.setdefault(f"{sym}-{hs}", []).append(p)
            plan_map.setdefault(sym, []).append(p)

    funding_rates: dict = {}
    positions = []
    if pos_data.get("code") == "00000":
        positions = [p for p in pos_data.get("data", [])
                     if safe_float(p.get("total", 0)) > 0]
        for pos in positions:
            symbol = pos.get("symbol", "")
            try:
                fr_data = client.get_funding_rate(symbol)
                if fr_data.get("code") == "00000":
                    fr = safe_float(fr_data["data"].get("fundingRate", 0.0001))
                    funding_rates[symbol] = fr
            except Exception:
                funding_rates[symbol] = 0.0001

    nav_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yangilash", callback_data="f2_positions"),
         InlineKeyboardButton("🔙 Orqaga",    callback_data="section_futures2")],
    ])

    if not positions:
        await query.edit_message_text(
            "📭 <b>Hozir ochiq pozitsiyalar yo'q</b>",
            reply_markup=nav_kb, parse_mode="HTML"
        )
        return

    total_unr = sum(safe_float(p.get("unrealizedPL", 0)) for p in positions)
    pnl_e     = "🟢" if total_unr >= 0 else "🔴"
    summary   = (
        f"📊 <b>OCHIQ POZITSIYALAR — {len(positions)} ta</b>\n"
        f"{pnl_e} <b>Jami natijasiz PnL:</b> <code>{total_unr:+.4f} USDT</code>\n"
        f"{'─'*28}\n"
        f"⬇️ Har bir pozitsiya alohida ko'rsatildi"
    )
    await query.edit_message_text(summary, reply_markup=nav_kb, parse_mode="HTML")

    chat_id = query.message.chat_id
    for pos in positions:
        text = _format_single_position(pos, plan_map, funding_rates)
        symbol    = pos.get("symbol", "")
        hold_side = pos.get("holdSide", "long")
        pos_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Savdoga Kirish",
                                 callback_data=f"manual_trade_{symbol}"),
            InlineKeyboardButton("🔙 Orqaga",
                                 callback_data="f2_positions"),
        ]])
        try:
            # Try to send with chart
            avg_price  = safe_float(pos.get("openPriceAvg", 0))
            mark_price = safe_float(pos.get("markPrice", avg_price))
            leverage   = int(safe_float(pos.get("leverage", 1)))
            unrealized = safe_float(pos.get("unrealizedPL", 0))

            plans_for_pos = plan_map.get(f"{symbol}-{hold_side}") or plan_map.get(symbol) or []
            tp_prices = [safe_float(p.get("triggerPrice", 0))
                         for p in plans_for_pos
                         if "profit" in (p.get("planType","")).lower()
                         and safe_float(p.get("triggerPrice",0)) > 0]
            sl_prices = [safe_float(p.get("triggerPrice", 0))
                         for p in plans_for_pos
                         if "loss" in (p.get("planType","")).lower()
                         and safe_float(p.get("triggerPrice",0)) > 0]

            candles = client.get_futures_candles(symbol, "1H", 60)
            if candles.get("code") == "00000" and candles.get("data"):
                from services.chart_generator import generate_position_chart
                direction = "LONG" if hold_side == "long" else "SHORT"
                buf = generate_position_chart(
                    candles_data=candles["data"],
                    symbol=symbol,
                    direction=direction,
                    entry=avg_price,
                    mark_price=mark_price,
                    tp_levels=tp_prices,
                    sl_levels=sl_prices,
                    unrealized_pnl=unrealized,
                    leverage=leverage,
                )
                await context.bot.send_photo(
                    chat_id=chat_id, photo=buf,
                    caption=f"📊 {symbol} {'🟢 LONG' if hold_side=='long' else '🔴 SHORT'} "
                            f"{leverage}x | PnL: {unrealized:+.4f} USDT",
                )
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode="HTML", reply_markup=pos_kb
        )


# ─── Pozitsiya Tarixi (net PnL) ──────────────────────────────────────────────

async def handle_f2_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yopiq pozitsiya tarixi — sof PnL = gross − komissiya − funding."""
    query = update.callback_query
    await query.answer("📜 Yuklanmoqda...")

    kb_period = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun",   callback_data="f2_hist_today"),
         InlineKeyboardButton("📆 7 kun",   callback_data="f2_hist_7d"),
         InlineKeyboardButton("🗓️ 30 kun",  callback_data="f2_hist_30d")],
        [InlineKeyboardButton("🔙 Orqaga",  callback_data="section_futures2"),
         InlineKeyboardButton("🏠 Bosh",    callback_data="main_menu")],
    ])
    await query.edit_message_text(
        "📜 <b>POZITSIYA TARIXI</b>\n\nDavr tanlang:",
        reply_markup=kb_period, parse_mode="HTML"
    )


async def handle_f2_history_period(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                    period: str):
    """Davr bo'yicha tarix ko'rsatish."""
    query = update.callback_query
    await query.answer("📜 Yuklanmoqda...")
    await query.edit_message_text(
        "📜 <b>Tarix yuklanmoqda...</b>", parse_mode="HTML"
    )

    period_map = {"today": 1, "7d": 7, "30d": 30}
    days = period_map.get(period, 7)

    try:
        data = client.get_futures_history(days=days, limit=50)
    except Exception as e:
        await query.edit_message_text(
            f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )
        return

    if data.get("code") != "00000":
        await query.edit_message_text(
            f"❌ <b>Ma'lumot olinmadi:</b> <code>{data.get('msg','')}</code>",
            parse_mode="HTML"
        )
        return

    fills = data.get("data", {})
    if isinstance(fills, dict):
        fills = fills.get("fillList") or fills.get("list") or []

    if not fills:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="f2_history")
        ]])
        await query.edit_message_text(
            "📭 <b>Bu davrda tarix yo'q</b>",
            reply_markup=kb, parse_mode="HTML"
        )
        return

    period_labels = {"today": "BUGUN", "7d": "SO'NGI 7 KUN", "30d": "SO'NGI 30 KUN"}
    header = f"📜 <b>POZITSIYA TARIXI — {period_labels.get(period,'')}</b>\n{'═'*32}\n"

    total_gross  = 0.0
    total_fee    = 0.0
    total_fund   = 0.0
    total_net    = 0.0

    lines = [header]

    for item in fills[:20]:
        symbol    = item.get("symbol", "")
        side      = (item.get("side") or item.get("holdSide") or "").lower()
        gross_pnl = safe_float(item.get("realizedPl", 0) or item.get("pnl", 0))
        fee       = safe_float(item.get("totalFee", 0) or item.get("fee", 0))
        fund      = safe_float(item.get("fundingFee", 0))
        open_time = item.get("ctime") or item.get("openTime", "")
        close_time= item.get("utime") or item.get("closeTime", "")
        avg_open  = safe_float(item.get("openPriceAvg", 0) or item.get("openAvgPrice", 0))
        avg_close = safe_float(item.get("closePriceAvg", 0) or item.get("closeAvgPrice", 0))
        qty       = safe_float(item.get("total", 0) or item.get("closeTotalPos", 0))
        leverage  = int(safe_float(item.get("leverage", 1)))

        # Sof PnL: fees va funding manfiy qiymat bo'ladi (to'langan summa)
        net_pnl = gross_pnl + fee + fund  # fee va fund allaqachon manfiy

        total_gross += gross_pnl
        total_fee   += fee
        total_fund  += fund
        total_net   += net_pnl

        dir_e  = "🟢 LONG" if "long" in side or side == "buy" else "🔴 SHORT"
        pnl_e  = "🟢" if net_pnl >= 0 else "🔴"
        gros_e = "🟢" if gross_pnl >= 0 else "🔴"

        # Vaqtni formatlash
        def _fmt_time(ts):
            try:
                return datetime.fromtimestamp(int(ts)/1000,
                                              tz=timezone.utc).strftime("%m/%d %H:%M")
            except Exception:
                return str(ts)[:10]

        entry_str = f"${fmt_price(avg_open)}" if avg_open > 0 else "—"
        exit_str  = f"${fmt_price(avg_close)}" if avg_close > 0 else "—"

        lines += [
            f"{'─'*28}",
            f"💎 <b>{symbol}</b>  {dir_e}  ×{leverage}",
            f"📥 Kirish: <code>{entry_str}</code>  →  📤 Chiqish: <code>{exit_str}</code>",
            f"📦 Hajm: <code>{qty:.4f}</code>",
            f"{'─'*20}",
            f"{gros_e} Gross PnL:   <code>{gross_pnl:+.4f} USDT</code>",
            f"💸 Komissiya:  <code>{fee:.6f} USDT</code>",
            f"💱 Funding:    <code>{fund:.6f} USDT</code>",
            f"{pnl_e} <b>SOF PnL:  <code>{net_pnl:+.4f} USDT</code></b>",
        ]
        if open_time:
            lines.append(f"🕒 {_fmt_time(open_time)} → {_fmt_time(close_time)}")

    # Jami
    total_pnl_e = "🟢" if total_net >= 0 else "🔴"
    lines += [
        f"\n{'═'*32}",
        f"📊 <b>JAMI ({len(fills[:20])} ta pozitsiya):</b>",
        f"📈 Gross PnL:  <code>{total_gross:+.4f} USDT</code>",
        f"💸 Komissiya:  <code>{total_fee:.4f} USDT</code>",
        f"💱 Funding:    <code>{total_fund:.4f} USDT</code>",
        f"{total_pnl_e} <b>SOF FOYDA: <code>{total_net:+.4f} USDT</code></b>",
        f"\n🕒 <code>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}</code>",
    ]

    full_text = "\n".join(lines)
    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n...<i>qisqartirildi</i>"

    period_cb = {"today": "f2_hist_today", "7d": "f2_hist_7d", "30d": "f2_hist_30d"}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Bugun",  callback_data="f2_hist_today"),
         InlineKeyboardButton("📆 7 kun",  callback_data="f2_hist_7d"),
         InlineKeyboardButton("🗓️ 30 kun", callback_data="f2_hist_30d")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data=period_cb.get(period,"f2_hist_7d")),
         InlineKeyboardButton("🔙 Orqaga",    callback_data="f2_history")],
    ])
    await query.edit_message_text(full_text, reply_markup=kb, parse_mode="HTML")

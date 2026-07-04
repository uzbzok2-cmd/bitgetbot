"""
Trend Buzish Scanner — W-Pattern (Double Bottom + Neckline Breakout)

Pattern:
  1 (high) → katta tushish
  2 (low)  → birinchi dip
  3 (neckline) → yuqoriga sakrash (1-candelning yarmigacha yetmagan)
  4 (low2) → ikkinchi dip (2 ga yaqin, ±3%)
  5 (breakout) → 3-candeldan yuqorida yopilishi KERAK
                  1-candelning yarmigacha yetmagan bo'lishi KERAK

Entry: 5-nuqtada (close above neckline)
TP:    Fibonacci 0.618 — 2-low dan 1-high gacha
SL:    4-low dan 0.5% past
"""
import asyncio
import io
import logging
import numpy as np
from typing import Optional, Dict, List, Tuple

from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from services import state as gs

logger = logging.getLogger(__name__)

SCAN_SYMBOLS_LIMIT = 60
MIN_VOLUME = 500_000
TF_CANDLES = {"15m": 150, "1H": 120, "4H": 100, "1D": 80}
SCAN_TFS   = ["1H", "4H", "15m"]
SCAN_INTERVAL = 300  # 5 daqiqa


def _scale(price: float) -> int:
    if price >= 10000: return 1
    if price >= 100:   return 2
    if price >= 1:     return 4
    if price >= 0.1:   return 5
    if price >= 0.01:  return 6
    return 8


def _parse_candles(candles_data: list):
    highs, lows, closes = [], [], []
    for c in candles_data:
        try:
            highs.append(safe_float(c[2]))
            lows.append(safe_float(c[3]))
            closes.append(safe_float(c[4]))
        except Exception:
            pass
    return np.array(highs), np.array(lows), np.array(closes)


def _find_pivots(highs, lows, window=3):
    peaks, troughs = [], []
    for i in range(window, len(highs) - window):
        if all(highs[i] >= highs[i-j] for j in range(1, window+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, window+1)):
            peaks.append(i)
        if all(lows[i] <= lows[i-j] for j in range(1, window+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, window+1)):
            troughs.append(i)
    return peaks, troughs


def detect_w_pattern(candles_data: list, symbol: str, tf: str) -> Optional[Dict]:
    """W-Pattern (Trend Buzish) aniqlash."""
    H, L, C = _parse_candles(candles_data)
    n = len(C)
    if n < 30:
        return None

    # Oxirgi 80 ta sham ichida qidirish
    window = min(80, n)
    H = H[-window:]
    L = L[-window:]
    C = C[-window:]
    w = len(H)

    current_close = C[-1]
    current_high  = H[-1]

    # Pivot nuqtalarni topish
    peaks, troughs = _find_pivots(H, L, window=2)

    if len(peaks) < 1 or len(troughs) < 2:
        return None

    # P4 → P2 → P3 → P1 → P5 tartibida qidirish
    for ti in range(len(troughs) - 1, 0, -1):
        p4_idx = troughs[ti]
        # P4 so'nggi 15 sham ichida bo'lishi kerak
        if w - p4_idx > 15:
            continue
        p4_low = L[p4_idx]

        for tj in range(ti - 1, -1, -1):
            p2_idx = troughs[tj]
            p2_low = L[p2_idx]

            # P2 va P4 orasida kamida 5 sham bo'lishi kerak
            if p4_idx - p2_idx < 5:
                continue
            # P2 va P4 narxi ±3% ichida bo'lishi kerak
            diff = abs(p4_low - p2_low) / p2_low
            if diff > 0.03:
                continue

            # P3: P2 va P4 orasidagi eng baland peak
            mid_peaks = [p for p in peaks if p2_idx < p < p4_idx]
            if not mid_peaks:
                continue
            p3_idx = max(mid_peaks, key=lambda p: H[p])
            p3_high = H[p3_idx]

            # P3 ikki dipdan yuqori bo'lishi kerak
            if p3_high <= max(p2_low, p4_low) * 1.005:
                continue

            # P1: P2 dan oldingi eng baland nuqta
            if p2_idx < 4:
                continue
            p1_idx = int(np.argmax(H[:p2_idx]))
            p1_high = H[p1_idx]

            # P1 P3 dan baland bo'lishi kerak
            if p1_high <= p3_high * 1.01:
                continue

            # P3 P1-P2 midpoint dan past bo'lishi kerak
            mid_1_2 = (p1_high + p2_low) / 2.0
            if p3_high >= mid_1_2:
                continue

            # P5 sharti 1: current_close P3 dan yuqori (neckline yorilishi)
            if current_close <= p3_high:
                continue

            # P5 sharti 2: current_close P1-P2 midpoint ga yetmagan
            if current_close >= mid_1_2:
                continue

            # Drop P1 dan P2 gacha kamida 4% bo'lishi kerak
            drop_1_2 = (p1_high - p2_low) / p1_high
            if drop_1_2 < 0.04:
                continue

            # PATTERN TOPILDI! TP/SL hisoblash
            s = _scale(current_close)
            tp = round(p2_low + 0.618 * (p1_high - p2_low), s)
            sl = round(min(p4_low, p2_low) * 0.995, s)
            entry = round(current_close, s)

            if entry <= sl:
                continue
            if tp <= entry:
                continue

            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0

            # Confidence: pattern tozaligi + RR
            base_conf = 68
            if diff < 0.01:   base_conf += 5   # diplar juda yaqin
            if drop_1_2 > 0.08: base_conf += 5  # katta tushish
            if rr >= 1.5:    base_conf += 5
            if rr >= 2.0:    base_conf += 5
            confidence = min(88, base_conf)

            return {
                "symbol": symbol,
                "timeframe": tf,
                "pattern": "Trend Buzish (W-Pattern)",
                "direction": "LONG",
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "confidence": confidence,
                "rr": round(rr, 2),
                # Pattern nuqtalari (chart uchun)
                "p1_idx": int(p1_idx), "p1_price": float(p1_high),
                "p2_idx": int(p2_idx), "p2_price": float(p2_low),
                "p3_idx": int(p3_idx), "p3_price": float(p3_high),
                "p4_idx": int(p4_idx), "p4_price": float(p4_low),
                "p5_idx": w - 1,       "p5_price": float(current_close),
                "neckline": float(p3_high),
                "midpoint": float(mid_1_2),
                "fib_618":  float(tp),
                "window": window,
            }

    return None


async def _get_top_symbols(client: BitgetClient) -> List[str]:
    try:
        d = client.get_futures_tickers()
        if d.get("code") == "00000":
            tickers = [
                t for t in d.get("data", [])
                if str(t.get("symbol", "")).endswith("USDT")
                and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME
            ]
            tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
            return [t["symbol"] for t in tickers[:SCAN_SYMBOLS_LIMIT]]
    except Exception:
        pass
    return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT"]


async def send_trend_break_alert(bot, chat_id: int, pat: Dict, raw: list):
    """Trend Buzish signalini Telegramga yuborish."""
    from services.chart_generator import generate_trend_break_chart
    from utils.formatters import fmt_price

    symbol    = pat["symbol"]
    tf        = pat["timeframe"]
    entry     = pat["entry"]
    tp        = pat["tp"]
    sl        = pat["sl"]
    conf      = pat["confidence"]
    rr        = pat["rr"]
    neckline  = pat["neckline"]
    fib618    = pat["fib_618"]

    rr_str = f"1:{rr:.1f}"
    text = (
        f"🔷 <b>TREND BUZISH SIGNALI!</b>\n"
        f"{'═'*30}\n"
        f"💎 <b>{symbol}</b> [{tf}]\n"
        f"🏷 Pattern: <b>W-Pattern (Neckline Yorildi)</b>\n"
        f"🟢 Yo'nalish: <b>LONG</b>\n"
        f"📈 Ishonch: <b>{conf}%</b>\n"
        f"{'─'*30}\n"
        f"💵 Kirish: <code>{fmt_price(entry)}</code>\n"
        f"🔵 Neckline: <code>{fmt_price(neckline)}</code>\n"
        f"🎯 TP (0.618): <code>{fmt_price(tp)}</code>\n"
        f"🛡 SL: <code>{fmt_price(sl)}</code>\n"
        f"⚖️ RR: <b>{rr_str}</b>\n"
        f"{'─'*30}\n"
        f"📌 1→2 (tushish) → 3 (neckline) →\n"
        f"   4 (2-dip) → 5 (breakout) 🚀"
    )

    try:
        chart_bytes = generate_trend_break_chart(raw, pat)
        if chart_bytes:
            await bot.send_photo(chat_id=chat_id, photo=chart_bytes,
                                 caption=text, parse_mode="HTML")
            return
    except Exception as e:
        logger.warning(f"Trend break chart xato {symbol}: {e}")

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


async def handle_trend_break_menu(update, context):
    """Reply keyboard 'Trend Buzish' tugmasidan chaqiriladi."""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from services import state as gs
    tb_on = getattr(gs, "trend_break_enabled", False)
    status = "🟢 YOQILGAN" if tb_on else "🔴 O'CHIRILGAN"
    text = (
        "🔷 <b>TREND BUZISH — W-Pattern Scanner</b>\n"
        "══════════════════════════════════\n\n"
        "📌 <b>Pattern:</b> W-shakl (Double Bottom)\n"
        "   ① Baland nuqta (kirish)\n"
        "   ② Birinchi pastlik (Low 1)\n"
        "   ③ Neckline (ko'k chiziq)\n"
        "   ④ Ikkinchi pastlik (Low 2 ≈ Low 1)\n"
        "   ⑤ Neckline yorilishi → <b>KIRISH!</b>\n\n"
        "📊 <b>TP:</b> Fibonacci 0.618 (② dan ① gacha)\n"
        "🛡 <b>SL:</b> ④ dan 0.5% pastda\n\n"
        f"⚡ <b>Holat:</b> {status}\n\n"
        "👇 Hozir skanerlamoqchi bo'lsangiz:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Hozir Skaner!", callback_data="tb_scan_now")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="f2_trend_break"),
         InlineKeyboardButton("🏠 Bosh", callback_data="main_menu")],
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_trend_break_inline(update, context):
    """Inline 'f2_trend_break' callback — FYUCHERS 2 menusidan."""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from services import state as gs
    query = update.callback_query
    await query.answer()
    tb_on = getattr(gs, "trend_break_enabled", False)
    status = "🟢 YOQILGAN" if tb_on else "🔴 O'CHIRILGAN"
    text = (
        "🔷 <b>TREND BUZISH — W-Pattern Scanner</b>\n"
        "══════════════════════════════════\n\n"
        "📌 <b>Pattern:</b> W-shakl (Double Bottom)\n"
        "   ① Baland nuqta → ② Low1 → ③ Neckline\n"
        "   → ④ Low2 ≈ Low1 → ⑤ Neckline yorildi!\n\n"
        "📊 <b>TP:</b> Fibonacci 0.618 (② dan ① gacha)\n"
        "🛡 <b>SL:</b> ④ dan 0.5% pastda\n"
        "⏱️ Vaqt oralig'i: 15m • 1H • 4H\n\n"
        f"⚡ <b>Holat:</b> {status}\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Hozir Skaner!", callback_data="tb_scan_now")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data="f2_trend_break"),
         InlineKeyboardButton("🔙 Ortga", callback_data="section_futures2")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_trend_break_scan_now(update, context):
    """'Hozir Skaner' tugmasi — bir martalik skan."""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    query = update.callback_query
    await query.answer("🔍 Skanerlanyapti...")

    chat_id = query.message.chat_id
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="🔷 <b>Trend Buzish skanerlanyapti...</b>\n"
             "📊 Top 60 USDT-M futures • 15m/1H/4H\n"
             "<i>30-60 soniya kuting...</i>",
        parse_mode="HTML"
    )

    try:
        client = BitgetClient()
        scanner = TrendBreakScanner(client, bot=context.bot)
        found = await scanner.scan_once()

        if not found:
            await msg.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔷 <b>Trend Buzish — Natija</b>\n"
                    "══════════════════════\n"
                    "📭 Hozircha W-Pattern topilmadi.\n\n"
                    "<i>Pattern: neckline yorilishi + hali "
                    "1-nuqta yarmiga yetmagan.</i>"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Qayta", callback_data="tb_scan_now")
                ]]),
                parse_mode="HTML"
            )
            return

        await msg.delete()
        for pat, raw in found[:5]:
            await send_trend_break_alert(context.bot, chat_id, pat, raw)
            import asyncio as _asyncio
            await _asyncio.sleep(1.5)

    except Exception as e:
        logger.error(f"Trend break scan_now xato: {e}")
        try:
            await msg.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


class TrendBreakScanner:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot    = bot
        self._seen: set = set()   # Takroriy signallarni oldini olish

    async def scan_once(self):
        """Bir marta barcha symbollarni skanerlaydi."""
        symbols = await _get_top_symbols(self.client)
        found = []

        for symbol in symbols:
            for tf in SCAN_TFS:
                try:
                    limit   = TF_CANDLES.get(tf, 120)
                    resp    = self.client.get_futures_candles(symbol, tf, limit)
                    if resp.get("code") != "00000":
                        await asyncio.sleep(0.05)
                        continue
                    raw = resp.get("data", [])
                    if not raw or len(raw) < 30:
                        continue

                    pat = detect_w_pattern(raw, symbol, tf)
                    if not pat:
                        await asyncio.sleep(0.05)
                        continue

                    key = f"{symbol}_{tf}_{pat['p3_price']:.6f}"
                    if key in self._seen:
                        await asyncio.sleep(0.05)
                        continue

                    self._seen.add(key)
                    found.append((pat, raw))
                    logger.info(
                        f"🔷 Trend Buzish: {symbol} [{tf}] "
                        f"conf={pat['confidence']}% RR=1:{pat['rr']}"
                    )
                    await asyncio.sleep(0.15)

                except Exception as e:
                    logger.debug(f"TrendBreak scan {symbol} {tf}: {e}")

            await asyncio.sleep(0.1)

        # Seen ro'yxatini tozalash (500 dan oshsa)
        if len(self._seen) > 500:
            self._seen = set(list(self._seen)[-200:])

        return found

    async def run(self):
        """Doimiy skan — 5 daqiqada bir marta."""
        logger.info("🔷 Trend Buzish scanner started (W-Pattern, 24/7)")
        gs.scanner.add_log("🔷 Trend Buzish scanner ishga tushdi")

        await asyncio.sleep(35)  # Bot to'liq ishga tushguncha kutish

        while True:
            try:
                if gs.trend_break_enabled and gs.notifier_chat_id:
                    found = await self.scan_once()
                    for pat, raw in found:
                        try:
                            await send_trend_break_alert(
                                self.bot, gs.notifier_chat_id, pat, raw
                            )
                            await asyncio.sleep(2)
                        except Exception as e:
                            logger.error(f"TrendBreak alert xato: {e}")
                    if found:
                        gs.scanner.add_log(
                            f"🔷 Trend Buzish: {len(found)} ta signal"
                        )
            except Exception as e:
                logger.error(f"TrendBreak scanner loop xato: {e}")

            await asyncio.sleep(SCAN_INTERVAL)

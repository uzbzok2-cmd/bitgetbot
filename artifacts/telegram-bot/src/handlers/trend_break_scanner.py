"""
Trend Buzish Scanner — Diagonal Trendline Breakout

Algoritm:
  1. Oxirgi 2 ta pivot HIGH → Yuqori sariq trend chiziq (resistance)
  2. Oxirgi 2 ta pivot LOW  → Pastki sariq trend chiziq (support)
  3. Narx yuqori chiziqni 1-2 candle ichida buzsa → LONG
  4. Narx pastki chiziqni 1-2 candle ichida buzsa → SHORT
  5. Kechikkan (≥3 candle) signallar o'tkazib yuboriladi

TP/SL:
  height = yuqori_chiziq - pastki_chiziq (buzilish nuqtasida)
  TP = entry + height×0.5   (LONG) / entry - height×0.5 (SHORT)
  SL = entry - (TP - entry) (1:1 RR)
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
MIN_VOLUME         = 500_000
TF_CANDLES         = {"15m": 120, "1H": 100, "4H": 80}
SCAN_TFS           = ["1H", "4H", "15m"]
SCAN_INTERVAL      = 300  # 5 daqiqa


# ──────────────────────────────────────────────
# Yordamchi funksiyalar
# ──────────────────────────────────────────────

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
    """Local pivot highs va lows topish."""
    peaks, troughs = [], []
    for i in range(window, len(highs) - window):
        if all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, window + 1)):
            peaks.append(i)
        if all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, window + 1)):
            troughs.append(i)
    return peaks, troughs


def _line_at(slope, intercept, x):
    return slope * x + intercept


# ──────────────────────────────────────────────
# Asosiy aniqlash funksiyasi
# ──────────────────────────────────────────────

def detect_trendline_breakout(candles_data: list, symbol: str, tf: str) -> Optional[Dict]:
    """
    Ikki diagonal trend chiziqni aniqlaydi va 1-2 candle ichidagi
    breakout signalini qaytaradi.
    """
    H, L, C = _parse_candles(candles_data)
    n = len(C)
    if n < 40:
        return None

    window = min(100, n)
    H = H[-window:]
    L = L[-window:]
    C = C[-window:]
    w = len(H)

    # Pivot topish (window=3, keyin 2 ga fallback)
    for pw in (3, 2):
        peaks, troughs = _find_pivots(H, L, window=pw)
        if len(peaks) >= 2 and len(troughs) >= 2:
            break
    else:
        return None

    # Oxirgi 2 ta pivot high → yuqori chiziq
    ph1_i, ph2_i = int(peaks[-2]), int(peaks[-1])
    ph1_v, ph2_v = float(H[ph1_i]), float(H[ph2_i])

    # Oxirgi 2 ta pivot low → pastki chiziq
    pl1_i, pl2_i = int(troughs[-2]), int(troughs[-1])
    pl1_v, pl2_v = float(L[pl1_i]), float(L[pl2_i])

    # Trend chiziqlari tenglamalari
    if ph2_i == ph1_i or pl2_i == pl1_i:
        return None

    up_slope = (ph2_v - ph1_v) / (ph2_i - ph1_i)
    up_int   = ph1_v - up_slope * ph1_i

    lo_slope = (pl2_v - pl1_v) / (pl2_i - pl1_i)
    lo_int   = pl1_v - lo_slope * pl1_i

    curr = w - 1
    prev = w - 2

    up_curr = _line_at(up_slope, up_int, curr)
    up_prev = _line_at(up_slope, up_int, prev)
    lo_curr = _line_at(lo_slope, lo_int, curr)
    lo_prev = _line_at(lo_slope, lo_int, prev)

    # Kanal yaroqliligi tekshiruvi
    if up_curr <= lo_curr:
        return None
    height = up_curr - lo_curr
    if height / max(abs(lo_curr), 1e-12) < 0.005:  # juda tor kanal
        return None

    # ── Breakout aniqlash (max 2 candle kechikish) ──
    direction = None
    breakout_offset = 0  # necha candle oldin buzildi

    # 1-candle kechikish: curr buzilgan
    if C[curr] > up_curr and C[prev] <= _line_at(up_slope, up_int, prev) * 1.002:
        direction = "LONG"
        breakout_offset = 0
    elif C[curr] < lo_curr and C[prev] >= _line_at(lo_slope, lo_int, prev) * 0.998:
        direction = "SHORT"
        breakout_offset = 0
    # 2-candle kechikish: prev buzilgan, curr hali ham chiziqdan tashqarida
    elif curr >= 2:
        prev2 = curr - 2
        up_prev1 = _line_at(up_slope, up_int, prev)
        lo_prev1 = _line_at(lo_slope, lo_int, prev)
        up_prev2 = _line_at(up_slope, up_int, prev2)
        lo_prev2 = _line_at(lo_slope, lo_int, prev2)
        if (C[prev] > up_prev1 and C[prev2] <= up_prev2 * 1.002
                and C[curr] > up_curr):
            direction = "LONG"
            breakout_offset = 1
        elif (C[prev] < lo_prev1 and C[prev2] >= lo_prev2 * 0.998
              and C[curr] < lo_curr):
            direction = "SHORT"
            breakout_offset = 1

    if not direction:
        return None

    # Trendline ikkalasi ham pivot nuqtalaridan tashqariga chiqmasligi kerak
    # (yaroqli kanal borligini tekshirish)
    mid_x = (max(ph1_i, pl1_i) + min(ph2_i, pl2_i)) // 2
    if _line_at(up_slope, up_int, mid_x) <= _line_at(lo_slope, lo_int, mid_x):
        return None

    # ── TP / SL hisoblash (1:1, height×0.5) ──
    s     = _scale(float(C[curr]))
    entry = round(float(C[curr]), s)
    dist  = round(height * 0.5, s)

    if dist <= 0:
        return None

    if direction == "LONG":
        tp = round(entry + dist, s)
        sl = round(entry - dist, s)
    else:
        tp = round(entry - dist, s)
        sl = round(entry + dist, s)

    # Yaroqlilik
    if direction == "LONG" and (sl >= entry or tp <= entry):
        return None
    if direction == "SHORT" and (sl <= entry or tp >= entry):
        return None

    # Ishonch bahosi
    confidence = 72
    span_up = ph2_i - ph1_i
    span_lo = pl2_i - pl1_i
    if span_up >= 10: confidence += 4
    if span_lo >= 10: confidence += 4
    if breakout_offset == 0: confidence += 5   # yangi breakout
    if abs(up_slope) > 0 and abs(lo_slope) > 0: confidence += 3
    confidence = min(92, confidence)

    return {
        "symbol":    symbol,
        "timeframe": tf,
        "pattern":   "Trend Chiziq Buzish",
        "direction": direction,
        "entry":     entry,
        "tp":        tp,
        "sl":        sl,
        "rr":        1.0,
        "confidence": confidence,
        "height":    float(height),
        # Chart uchun
        "upper_p1":       (ph1_i, ph1_v),
        "upper_p2":       (ph2_i, ph2_v),
        "upper_slope":    up_slope,
        "upper_intercept": up_int,
        "lower_p1":       (pl1_i, pl1_v),
        "lower_p2":       (pl2_i, pl2_v),
        "lower_slope":    lo_slope,
        "lower_intercept": lo_int,
        "breakout_idx":   curr,
        "up_curr":        float(up_curr),
        "lo_curr":        float(lo_curr),
        "window":         window,
        "breakout_offset": breakout_offset,
    }


# ──────────────────────────────────────────────
# Top symbollar
# ──────────────────────────────────────────────

async def _get_top_symbols(client: BitgetClient) -> List[str]:
    try:
        d = client.get_futures_tickers()
        if d.get("code") == "00000":
            tickers = [
                t for t in d.get("data", [])
                if str(t.get("symbol", "")).endswith("USDT")
                and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME
            ]
            tickers.sort(
                key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True
            )
            return [t["symbol"] for t in tickers[:SCAN_SYMBOLS_LIMIT]]
    except Exception:
        pass
    return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT"]


# ──────────────────────────────────────────────
# Signal yuborish
# ──────────────────────────────────────────────

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
    direction = pat["direction"]
    height    = pat["height"]

    dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    dir_arrow = "📈" if direction == "LONG" else "📉"

    entry_pct = abs((tp - entry) / entry * 100)
    sl_pct    = abs((sl - entry) / entry * 100)

    text = (
        f"🔷 <b>TREND CHIZIQ BUZILDI!</b>\n"
        f"{'═' * 30}\n"
        f"💎 <b>{symbol}</b> [{tf}]\n"
        f"{dir_arrow} Yo'nalish: <b>{dir_emoji}</b>\n"
        f"📊 Ishonch: <b>{conf}%</b>\n"
        f"{'─' * 30}\n"
        f"⚡ Kirish: <code>{fmt_price(entry)}</code>\n"
        f"🎯 TP: <code>{fmt_price(tp)}</code>  (+{entry_pct:.2f}%)\n"
        f"🛡 SL: <code>{fmt_price(sl)}</code>  (-{sl_pct:.2f}%)\n"
        f"⚖️ RR: <b>1:1</b>\n"
        f"{'─' * 30}\n"
        f"📏 Kanal balandligi: <code>{fmt_price(height)}</code>\n"
        f"🔶 TP = Kirish + balandlik×50%\n"
        f"🔶 SL = Kirish - balandlik×50%"
    )

    try:
        chart_bytes = generate_trend_break_chart(raw, pat)
        if chart_bytes:
            await bot.send_photo(
                chat_id=chat_id, photo=chart_bytes,
                caption=text, parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.warning(f"Trend break chart xato {symbol}: {e}")

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


# ──────────────────────────────────────────────
# Telegram handler'lar
# ──────────────────────────────────────────────

async def handle_trend_break_menu(update, context):
    """Reply keyboard 'Trend Buzish' tugmasidan chaqiriladi."""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    tb_on  = getattr(gs, "trend_break_enabled", False)
    status = "🟢 YOQILGAN" if tb_on else "🔴 O'CHIRILGAN"
    text = (
        "🔷 <b>TREND BUZISH — Trendline Breakout Scanner</b>\n"
        "══════════════════════════════════\n\n"
        "📌 <b>Qanday ishlaydi:</b>\n"
        "   🔶 2 ta sariq diagonal trend chiziq chiziladi\n"
        "       • Yuqori (resistance) — oxirgi 2 pivot HIGH\n"
        "       • Pastki (support) — oxirgi 2 pivot LOW\n\n"
        "   📈 Narx yuqori chiziqni buzsa → <b>LONG</b>\n"
        "   📉 Narx pastki chiziqni buzsa → <b>SHORT</b>\n\n"
        "📐 <b>TP/SL:</b> Kanal balandligi × 50%, RR <b>1:1</b>\n"
        "⏱️ Vaqt oralig'i: 15m • 1H • 4H\n"
        "⚡ Faqat 1-2 candle ichidagi yangi buzilishlar\n\n"
        f"🔘 <b>Holat:</b> {status}\n"
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
    query  = update.callback_query
    await query.answer()
    tb_on  = getattr(gs, "trend_break_enabled", False)
    status = "🟢 YOQILGAN" if tb_on else "🔴 O'CHIRILGAN"
    text = (
        "🔷 <b>TREND BUZISH — Trendline Breakout Scanner</b>\n"
        "══════════════════════════════════\n\n"
        "🔶 2 ta sariq diagonal trend chiziq:\n"
        "   • Yuqori chiziq: oxirgi 2 pivot HIGH\n"
        "   • Pastki chiziq: oxirgi 2 pivot LOW\n\n"
        "📈 Yuqorini buzsa → LONG signal\n"
        "📉 Pastini buzsa → SHORT signal\n\n"
        "📐 TP = Kirish ± balandlik×50% | SL = 1:1\n"
        "⚡ Faqat 1-2 candle yangi buzilishlar\n"
        "⏱️ 15m • 1H • 4H — 5 daqiqada bir skan\n\n"
        f"🔘 <b>Holat:</b> {status}\n"
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
        text=(
            "🔷 <b>Trend Buzish skanerlanyapti...</b>\n"
            "🔶 2 ta sariq trend chiziq topilmoqda\n"
            "📊 Top 60 USDT-M futures • 15m/1H/4H\n"
            "<i>30-60 soniya kuting...</i>"
        ),
        parse_mode="HTML"
    )

    try:
        client  = BitgetClient()
        scanner = TrendBreakScanner(client, bot=context.bot)
        found   = await scanner.scan_once()

        if not found:
            await msg.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔷 <b>Trend Buzish — Natija</b>\n"
                    "══════════════════════\n"
                    "📭 Hozircha yangi trendline breakout topilmadi.\n\n"
                    "<i>Signal faqat 1-2 candle ichida buzilganda keladi.</i>"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Qayta skaner", callback_data="tb_scan_now")
                ]]),
                parse_mode="HTML"
            )
            return

        await msg.delete()
        for pat, raw in found[:5]:
            await send_trend_break_alert(context.bot, chat_id, pat, raw)
            await asyncio.sleep(1.5)

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


# ──────────────────────────────────────────────
# Scanner klassi
# ──────────────────────────────────────────────

class TrendBreakScanner:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot    = bot
        self._seen: set = set()

    async def scan_once(self):
        """Bir marta barcha symbollarni skanerlaydi."""
        symbols = await _get_top_symbols(self.client)
        found   = []

        for symbol in symbols:
            for tf in SCAN_TFS:
                try:
                    limit = TF_CANDLES.get(tf, 100)
                    resp  = self.client.get_futures_candles(symbol, tf, limit)
                    if resp.get("code") != "00000":
                        await asyncio.sleep(0.05)
                        continue
                    raw = resp.get("data", [])
                    if not raw or len(raw) < 40:
                        continue

                    pat = detect_trendline_breakout(raw, symbol, tf)
                    if not pat:
                        await asyncio.sleep(0.05)
                        continue

                    key = f"{symbol}_{tf}_{pat['direction']}_{round(pat['entry'], 6)}"
                    if key in self._seen:
                        await asyncio.sleep(0.05)
                        continue

                    self._seen.add(key)
                    found.append((pat, raw))
                    logger.info(
                        f"🔷 Trend Buzish: {symbol} [{tf}] "
                        f"{pat['direction']} conf={pat['confidence']}% RR=1:1"
                    )
                    await asyncio.sleep(0.15)

                except Exception as e:
                    logger.debug(f"TrendBreak scan {symbol} {tf}: {e}")

            await asyncio.sleep(0.1)

        if len(self._seen) > 500:
            self._seen = set(list(self._seen)[-200:])

        return found

    async def run(self):
        """Doimiy skan — 5 daqiqada bir marta."""
        logger.info("🔷 Trend Buzish scanner started (W-Pattern, 24/7)")
        gs.scanner.add_log("🔷 Trend Buzish scanner ishga tushdi")

        await asyncio.sleep(35)

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
                            f"🔷 Trend Buzish: {len(found)} ta signal topildi"
                        )
            except Exception as e:
                logger.error(f"TrendBreak scanner loop xato: {e}")

            await asyncio.sleep(SCAN_INTERVAL)

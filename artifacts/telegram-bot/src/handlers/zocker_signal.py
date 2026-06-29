"""
Zocker Signal — 6-7 ta ketma-ket bir xil rangdagi shamlarni aniqlash.
1H, 4H, 1D timeframelarida ishlaydi.
6-7 qizil sham → SHORT imkoni
6-7 yashil sham → LONG imkoni
"""
import asyncio
import logging
import time
from typing import Optional, Dict, List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import safe_float, analyze_symbol
from services import state as gs

logger = logging.getLogger(__name__)

ZOCKER_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT",
    "LINKUSDT", "MATICUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
]

ZOCKER_TIMEFRAMES = ["1H", "4H", "1D"]
ZOCKER_MIN_CANDLES = 6
ZOCKER_MAX_CANDLES = 7
ZOCKER_CHECK_INTERVAL = 300


def detect_consecutive_candles(candles_data: list, min_count: int = 6, max_count: int = 7):
    """
    Ketma-ket bir xil rangdagi shamlarni aniqlash.
    Returns: (direction, count) yoki None
    - direction: 'LONG' (yashil shamlar ketma-ket) yoki 'SHORT' (qizil)
    - count: nechta ketma-ket sham
    """
    if not candles_data or len(candles_data) < min_count + 1:
        return None

    # Oxirgi shamni tashlaymiz (hali yopilmagan bo'lishi mumkin)
    finished = candles_data[:-1]
    if len(finished) < min_count:
        return None

    # Oxirgi max_count+2 ta shamni tekshiramiz
    check_window = finished[-(max_count + 2):]

    colors = []
    for c in check_window:
        try:
            open_p  = safe_float(c[1])
            close_p = safe_float(c[4])
            if close_p > open_p * 1.0001:
                colors.append("green")
            elif close_p < open_p * 0.9999:
                colors.append("red")
            else:
                colors.append("doji")
        except Exception:
            colors.append("doji")

    # max_count dan min_count gacha tekshiramiz
    for count in range(max_count, min_count - 1, -1):
        if count > len(colors):
            continue
        tail = colors[-count:]
        non_doji = [c for c in tail if c != "doji"]
        if len(non_doji) >= min_count and len(set(non_doji)) == 1:
            direction = "LONG" if non_doji[0] == "green" else "SHORT"
            return direction, count

    return None


class ZockerScanner:
    def __init__(self, client: BitgetClient, bot=None):
        self.client   = client
        self.bot      = bot
        self.active   = True
        self.last_alerts: Dict[str, float] = {}  # symbol+tf → last alert time
        self.alert_cooldown = 4 * 3600  # 4 soat cooldown

    def _cooldown_key(self, symbol: str, tf: str) -> str:
        return f"{symbol}_{tf}"

    def _is_on_cooldown(self, symbol: str, tf: str) -> bool:
        key = self._cooldown_key(symbol, tf)
        last = self.last_alerts.get(key, 0)
        return (time.time() - last) < self.alert_cooldown

    def _set_cooldown(self, symbol: str, tf: str):
        key = self._cooldown_key(symbol, tf)
        self.last_alerts[key] = time.time()

    async def run(self):
        """Background loop."""
        logger.info("🕯️ Zocker scanner ishga tushdi")
        while self.active:
            try:
                await self._scan_all()
            except Exception as e:
                logger.error(f"Zocker scan error: {e}")
            await asyncio.sleep(ZOCKER_CHECK_INTERVAL)

    async def _scan_all(self):
        for symbol in ZOCKER_SYMBOLS:
            for tf in ZOCKER_TIMEFRAMES:
                if self._is_on_cooldown(symbol, tf):
                    continue
                try:
                    await self._check_symbol(symbol, tf)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Zocker {symbol} {tf}: {e}")

    async def _check_symbol(self, symbol: str, tf: str):
        candles = self.client.get_futures_candles(symbol, tf, 50)
        if candles.get("code") != "00000":
            return
        raw = candles.get("data", [])
        if not raw:
            return

        result = detect_consecutive_candles(raw, ZOCKER_MIN_CANDLES, ZOCKER_MAX_CANDLES)
        if not result:
            return

        direction, count = result
        self._set_cooldown(symbol, tf)
        logger.info(f"🕯️ Zocker signal: {symbol} {tf} {direction} {count} ta sham")
        gs.scanner.add_log(f"🕯️ ZOCKER: {symbol} {tf} {direction} {count}ta")

        await self._send_alert(symbol, tf, direction, count, raw)

    async def _send_alert(self, symbol: str, tf: str, direction: str, count: int, raw: list):
        if not self.bot or not gs.notifier_chat_id:
            return

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from services.chart_generator import generate_zocker_chart

        dir_text  = "🟢 XARID (LONG)" if direction == "LONG" else "🔴 SOTISH (SHORT)"
        color_txt = "yashil" if direction == "LONG" else "qizil"
        entry_hint = "BUY" if direction == "LONG" else "SELL"

        # Analyze for TP/SL suggestion
        tp, sl, entry = 0.0, 0.0, 0.0
        try:
            sig = analyze_symbol(raw, symbol, tf)
            if sig:
                entry = sig["entry"]
                tp    = sig["tp1"]
                sl    = sig["sl"]
        except Exception:
            pass

        text = (
            f"🕯️ <b>ZOCKER SIGNAL!</b>\n"
            f"{'═'*28}\n"
            f"💎 <b>{symbol}</b> — {dir_text}\n"
            f"⏱️ Timeframe: <b>{tf}</b>\n"
            f"🕯️ <b>{count} ta ketma-ket {color_txt} sham</b> yopildi!\n"
            f"{'─'*28}\n"
            f"💡 Bu {entry_hint} ga kirish imkoni bo'lishi mumkin.\n"
        )
        if entry > 0:
            from utils.formatters import fmt_price, _pct_lev
            text += (
                f"{'─'*28}\n"
                f"💲 Narx: <code>${fmt_price(entry)}</code>\n"
            )
            if tp > 0:
                text += f"💚 TP: <code>${fmt_price(tp)}</code>  ({_pct_lev(tp, entry)})\n"
            if sl > 0:
                text += f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry)})\n"

        text += f"{'─'*28}\n⚠️ <i>Tasdiqlab kirish tavsiya etiladi.</i>"

        # Pending signal for trade button
        if entry > 0:
            pending_sig = {
                "symbol": symbol, "direction": direction,
                "entry": entry, "tp1": tp, "sl": sl,
                "confidence": 65, "timeframe": tf, "atr": entry * 0.02,
                "reasons": [f"{count} ta ketma-ket {color_txt} sham ({tf})"]
            }
            gs.pending_manual_trades[symbol] = pending_sig

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Savdoga Kirish", callback_data=f"manual_trade_{symbol}")
        ]])

        # Chart
        try:
            buf = generate_zocker_chart(
                candles_data=raw,
                symbol=symbol,
                direction=direction,
                consecutive_count=count,
                timeframe=tf,
                entry=entry,
                tp=tp,
                sl=sl,
            )
            await self.bot.send_photo(
                chat_id=gs.notifier_chat_id,
                photo=buf,
                caption=f"🕯️ {symbol} {tf} — {count} ta {color_txt} sham",
                reply_markup=kb
            )
        except Exception as chart_err:
            logger.warning(f"Zocker chart error: {chart_err}")
            kb = None

        try:
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=kb if not entry else kb
            )
        except Exception as e:
            logger.error(f"Zocker send error: {e}")

"""
Zocker Signal — MEAN REVERSION strategiyasi.
6-7 YASHIL sham → SHORT (overbought, pasayish kutiladi)
6-7 QIZIL  sham → LONG  (oversold,  ko'tarilish kutiladi)

24/7 BARCHA USDT futures cryptolarda ishlaydi.
Signal topilganda DARHOL pozitsiya ochiladi + xabarnoma yuboriladi.
"""
import asyncio
import logging
import time
import re
from typing import Optional, Dict, List

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import safe_float, analyze_symbol
from services import state as gs

logger = logging.getLogger(__name__)

ZOCKER_TIMEFRAMES     = ["1H", "4H"]
ZOCKER_MIN_CANDLES    = 6
ZOCKER_MAX_CANDLES    = 7
ZOCKER_CHECK_INTERVAL = 60        # har 60 soniyada yangi symbollarni oladi
ZOCKER_COOLDOWN       = 4 * 3600  # bir xil symbol+TF uchun 4 soat cooldown

MIN_VOLUME_USDT = 200_000         # minimal hajm filtri

FALLBACK_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT",
    "LINKUSDT", "MATICUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
]


def _price_scale(price: float) -> int:
    if price >= 10000: return 1
    elif price >= 100: return 2
    elif price >= 1:   return 4
    elif price >= 0.1: return 5
    elif price >= 0.01: return 6
    return 8


def _calc_half_candle_tp_sl(direction: str, candles_data: list,
                             entry: float, count: int) -> tuple:
    """
    TP/SL ni ketma-ket shamlarning yarmi asosida hisoblash.
    LONG (qizil shamlardan keyin): TP = oxirgi N/2 shamning maksimal HIGH
    SHORT (yashil shamlardan keyin): TP = oxirgi N/2 shamning minimal LOW
    SL = 1:1 nisbat (TP distance = SL distance)
    """
    try:
        finished = candles_data[:-1]          # hali yopilmagan sham tashlab
        consec   = finished[-count:]           # aynan count ta ketma-ket sham
        half     = max(1, count // 2)
        target   = consec[-half:]             # oxirgi yarmi

        scale = _price_scale(entry)
        if direction == "LONG":
            tp   = max(safe_float(c[2]) for c in target)  # max HIGH
            dist = abs(tp - entry)
            sl   = entry - dist
        else:  # SHORT
            tp   = min(safe_float(c[3]) for c in target)  # min LOW
            dist = abs(entry - tp)
            sl   = entry + dist

        # Sanity check
        if direction == "LONG":
            if tp <= entry: tp = round(entry * 1.015, scale)
            if sl >= entry: sl = round(entry * 0.985, scale)
        else:
            if tp >= entry: tp = round(entry * 0.985, scale)
            if sl <= entry: sl = round(entry * 1.015, scale)

        return round(tp, scale), round(sl, scale)
    except Exception as e:
        logger.warning(f"half-candle TP/SL xato: {e}")
        scale = _price_scale(entry)
        if direction == "LONG":
            return round(entry * 1.015, scale), round(entry * 0.985, scale)
        return round(entry * 0.985, scale), round(entry * 1.015, scale)


def _place_tp_sl(client, symbol, plan_type, trig, hold_side, sz):
    """TP yoki SL qo'y, checkScale xatosida avtomatik to'g'rilash."""
    r = client.place_futures_tp_sl(
        symbol=symbol, plan_type=plan_type,
        trigger_price=str(trig), side=hold_side, size=str(sz)
    )
    if r.get("code") == "00000":
        return True, trig
    msg = r.get("msg", "")
    m = re.search(r"checkScale=(\d+)", msg)
    if m:
        trig_fixed = round(trig, int(m.group(1)))
        r2 = client.place_futures_tp_sl(
            symbol=symbol, plan_type=plan_type,
            trigger_price=str(trig_fixed), side=hold_side, size=str(sz)
        )
        return r2.get("code") == "00000", trig_fixed
    logger.warning(f"Zocker TP/SL xato {symbol} {plan_type}: {msg}")
    return False, trig


def detect_consecutive_candles(candles_data: list, min_count: int = 6, max_count: int = 7):
    """
    Ketma-ket bir xil rangdagi shamlarni aniqlash.

    MEAN REVERSION — signal yo'nalishi candle rangi bilan TESKARI:
    - 6-7 YASHIL sham → SHORT (overbought: narx haddan ziyod ko'tarildi)
    - 6-7 QIZIL  sham → LONG  (oversold:  narx haddan ziyod tushdi)

    Returns: (direction, count) yoki None
    """
    if not candles_data or len(candles_data) < min_count + 1:
        return None

    finished = candles_data[:-1]
    if len(finished) < min_count:
        return None

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

    for count in range(max_count, min_count - 1, -1):
        if count > len(colors):
            continue
        tail     = colors[-count:]
        non_doji = [c for c in tail if c != "doji"]
        if len(non_doji) >= min_count and len(set(non_doji)) == 1:
            # MEAN REVERSION: yashil → SHORT, qizil → LONG
            direction = "SHORT" if non_doji[0] == "green" else "LONG"
            return direction, count

    return None


class ZockerScanner:
    def __init__(self, client: BitgetClient, bot=None):
        self.client         = client
        self.bot            = bot
        self.active         = True
        self.last_alerts: Dict[str, float] = {}

    def _is_on_cooldown(self, symbol: str) -> bool:
        return (time.time() - self.last_alerts.get(symbol, 0)) < ZOCKER_COOLDOWN

    def _set_cooldown(self, symbol: str):
        self.last_alerts[symbol] = time.time()

    async def _get_all_symbols(self) -> List[str]:
        """Bitgetdan barcha USDT futures symbollarini hajm bo'yicha olish."""
        try:
            d = self.client.get_futures_tickers()
            if d.get("code") == "00000":
                tickers = [
                    t for t in d.get("data", [])
                    if str(t.get("symbol", "")).endswith("USDT")
                    and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME_USDT
                ]
                tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
                syms = [t["symbol"] for t in tickers]
                logger.info(f"🕯️ Zocker: {len(syms)} ta symbol topildi")
                return syms
        except Exception as e:
            logger.error(f"Zocker get_symbols: {e}")
        return FALLBACK_SYMBOLS

    async def run(self):
        """Background loop — 24/7 barcha cryptolarni skanerlaydi."""
        logger.info("🕯️ Zocker scanner ishga tushdi (barcha USDT futures, 24/7)")
        while self.active:
            try:
                await self._scan_all()
            except Exception as e:
                logger.error(f"Zocker scan error: {e}")
            await asyncio.sleep(ZOCKER_CHECK_INTERVAL)

    async def _scan_all(self):
        """
        Barcha symbollarni skanerlab, eng yaxshi 5-6 ta signalni topib yuboradi.
        Bir xil symbol qayta yuborilmaydi (4 soat cooldown, symbol asosida).
        Ranking: 4H > 1H; count=7 > count=6; har symboldan faqat bittasi.
        """
        symbols = await self._get_all_symbols()
        candidates = []  # (score, symbol, tf, direction, count, raw)

        for symbol in symbols:
            if self._is_on_cooldown(symbol):
                continue
            for tf in ZOCKER_TIMEFRAMES:
                try:
                    candles = self.client.get_futures_candles(symbol, tf, 50)
                    if candles.get("code") != "00000":
                        await asyncio.sleep(0.1)
                        continue
                    raw = candles.get("data", [])
                    if not raw:
                        continue
                    result = detect_consecutive_candles(raw, ZOCKER_MIN_CANDLES, ZOCKER_MAX_CANDLES)
                    if result:
                        direction, count = result
                        # Score: 4H=10, 1H=0; har qo'shimcha sham +2
                        score = (10 if tf == "4H" else 0) + (count - ZOCKER_MIN_CANDLES) * 2
                        candidates.append((score, symbol, tf, direction, count, raw))
                    await asyncio.sleep(0.15)
                except Exception as e:
                    logger.warning(f"Zocker {symbol} {tf}: {e}")

        # Har symbol uchun faqat eng yaxshi timeframe/score ni saqla
        best_per_symbol: Dict[str, tuple] = {}
        for score, symbol, tf, direction, count, raw in candidates:
            prev = best_per_symbol.get(symbol)
            if prev is None or score > prev[0]:
                best_per_symbol[symbol] = (score, tf, direction, count, raw)

        # Score bo'yicha saralab, eng yaxshi 5-6 tasini ol
        ranked = sorted(best_per_symbol.items(), key=lambda x: x[1][0], reverse=True)
        top = ranked[:6]

        if top:
            gs.scanner.add_log(f"🕯️ Zocker: {len(top)} ta signal topildi (jami {len(candidates)} kandidat)")
        else:
            gs.scanner.add_log("🕯️ Zocker: signal topilmadi")

        for symbol, (score, tf, direction, count, raw) in top:
            self._set_cooldown(symbol)
            color_txt = "yashil" if direction == "SHORT" else "qizil"
            logger.info(f"🕯️ Zocker: {symbol} {tf} → {direction} ({count} ta {color_txt}, score={score})")
            gs.scanner.add_log(f"🕯️ ZOCKER: {symbol} {tf} {direction} {count}ta {color_txt}")
            await self._handle_signal(symbol, tf, direction, count, raw)
            await asyncio.sleep(1.5)

    async def _handle_signal(self, symbol: str, tf: str, direction: str, count: int, raw: list):
        """Signal topilganda: alert yuborish + avtomatik savdo."""
        entry, tp, sl, atr = 0.0, 0.0, 0.0, 0.0

        # 1-qadam: analyze_symbol orqali entry olish
        try:
            sig = analyze_symbol(raw, symbol, tf)
            if sig and safe_float(sig.get("entry", 0)) > 0:
                entry = sig["entry"]
                atr   = sig.get("atr", entry * 0.02)
        except Exception as e:
            logger.warning(f"Zocker analyze {symbol}: {e}")

        # 2-qadam: entry=0 bo'lsa ticker orqali ol
        if entry <= 0:
            try:
                tk = self.client.get_futures_ticker(symbol)
                if tk.get("code") == "00000" and tk.get("data"):
                    entry = safe_float(tk["data"][0].get("lastPr", 0))
                    atr   = entry * 0.02
            except Exception:
                pass

        # 3-qadam: hali ham 0 bo'lsa — oxirgi sham yopilish narxidan foydalanish
        if entry <= 0 and raw:
            try:
                entry = safe_float(raw[-1][4])
                atr   = entry * 0.02
            except Exception:
                pass

        # TP/SL hisoblash — entry mavjud bo'lganda
        if entry > 0:
            tp, sl = _calc_half_candle_tp_sl(direction, raw, entry, count)

        if entry > 0:
            gs.pending_manual_trades[symbol] = {
                "symbol": symbol, "direction": direction,
                "entry": entry, "tp1": tp, "sl": sl, "atr": atr,
                "confidence": 65, "timeframe": tf,
                "consecutive_count": count,
                "reasons": [
                    f"{count} ta ketma-ket {'yashil' if direction == 'SHORT' else 'qizil'} "
                    f"sham ({tf}) — Mean Reversion"
                ]
            }

        await self._send_alert(symbol, tf, direction, count, raw, entry, tp, sl)

        if gs.auto_trade_enabled and gs.zocker_enabled and entry > 0:
            await self._auto_trade(symbol, tf, direction, entry, tp, sl, atr, count)

    async def _auto_trade(self, symbol: str, tf: str, direction: str,
                           entry: float, tp: float, sl: float, atr: float, count: int):
        """Zocker signali uchun avtomatik pozitsiya ochish."""
        try:
            # Maksimal 3 ta ochiq pozitsiya tekshiruvi
            pos_d = self.client.get_futures_positions()
            if pos_d.get("code") == "00000":
                open_count = sum(1 for p in pos_d.get("data", [])
                                 if safe_float(p.get("total", 0)) > 0)
                if open_count >= gs.MAX_AUTO_POSITIONS:
                    logger.info(f"Zocker {symbol}: {open_count} ta ochiq pozitsiya (limit {gs.MAX_AUTO_POSITIONS}) — o'tkazib yuborildi")
                    gs.scanner.add_log(f"⏸️ Zocker {symbol}: limit {gs.MAX_AUTO_POSITIONS} ta → o'tkazildi")
                    return

            acc = self.client.get_futures_account()
            if acc.get("code") != "00000":
                logger.warning("Zocker auto-trade: balans olinmadi")
                return
            acc_data = acc["data"]
            # crossedMaxAvailable — Bitget'ning haqiqiy cross margin limiti (0=yangi pozitsiya yo'q)
            crossed_max = safe_float(acc_data.get("crossedMaxAvailable", -1))
            if crossed_max >= 0:
                balance = crossed_max  # haqiqiy limit
            else:
                balance = safe_float(acc_data.get("available", 0))  # fallback
            if balance < 1.0:
                logger.warning(f"Zocker auto-trade: crossedMaxAvailable kam ({balance:.2f})")
                return

            from config import MIN_ORDER_USDT, MAX_ORDER_USDT
            pct        = gs.trade_balance_pct / 100.0
            order_usdt = max(MIN_ORDER_USDT, min(MAX_ORDER_USDT, balance * pct))

            max_lev = 20
            try:
                lev_d = self.client.get_futures_leverage_info(symbol)
                if lev_d.get("code") == "00000":
                    max_lev = int(safe_float(lev_d["data"].get("maxLeverage", 20)))
            except Exception:
                pass

            # Cross margin uchun to'g'ri leverage o'rnatish va tasdiqlash
            confirmed_lev = max_lev
            try:
                self.client.set_margin_mode(symbol, "crossed")
                r = self.client.set_leverage_cross(symbol, max_lev)
                if r.get("code") != "00000":
                    self.client.set_leverage(symbol, max_lev, hold_side="long")
                    self.client.set_leverage(symbol, max_lev, hold_side="short")
                sym_acc = self.client.get_futures_symbol_account(symbol)
                if sym_acc.get("code") == "00000":
                    lev_val = int(safe_float(sym_acc["data"].get("leverage", max_lev)))
                    if lev_val > 0:
                        confirmed_lev = lev_val
            except Exception as e:
                logger.warning(f"Zocker leverage set error {symbol}: {e}")

            side      = "sell" if direction == "SHORT" else "buy"
            hold_side = "short" if direction == "SHORT" else "long"

            size = order_usdt * confirmed_lev / entry
            try:
                d = self.client.get_futures_contract_info(symbol)
                if d.get("code") == "00000":
                    contracts = d.get("data", [])
                    if contracts:
                        c        = contracts[0]
                        min_size = safe_float(c.get("minTradeNum", 0.001))
                        prec     = len(str(min_size).split(".")[-1]) if "." in str(min_size) else 4
                        size     = max(min_size, round(size, prec))
            except Exception:
                size = max(0.001, round(size, 4))

            result = self.client.place_futures_order(
                symbol=symbol, side=side, trade_side="open",
                size=str(size), order_type="market"
            )
            if result.get("code") != "00000":
                logger.error(f"Zocker order xato {symbol}: {result.get('msg')}")
                gs.scanner.add_log(f"❌ Zocker {symbol}: {result.get('msg','')[:40]}")
                return

            gs.scanner.add_log(f"✅ Zocker savdo: {symbol} {direction} {max_lev}x")

            # TP MAJBURIY — muvaffaqiyatsiz bo'lsa pozitsiyani darhol yop
            tp_ok, _ = _place_tp_sl(self.client, symbol, "pos_profit", tp, hold_side, size)
            if not tp_ok:
                logger.error(f"❌ Zocker {symbol} TP qo'yilmadi — ROLLBACK")
                gs.scanner.add_log(f"❌ Zocker {symbol} TP fail → rollback")
                self.client.close_futures_position(symbol, hold_side)
                return

            # SL MAJBURIY — muvaffaqiyatsiz bo'lsa pozitsiyani darhol yop
            sl_ok, _ = _place_tp_sl(self.client, symbol, "pos_loss", sl, hold_side, size)
            if not sl_ok:
                logger.error(f"❌ Zocker {symbol} SL qo'yilmadi — ROLLBACK")
                gs.scanner.add_log(f"❌ Zocker {symbol} SL fail → rollback")
                self.client.close_futures_position(symbol, hold_side)
                return

            logger.info(f"✅ Zocker {symbol} TP={tp} SL={sl} — muvaffaqiyatli")

            if self.bot and gs.notifier_chat_id:
                color_txt = "yashil" if direction == "SHORT" else "qizil"
                dir_e     = "🔴 SHORT" if direction == "SHORT" else "🟢 LONG"
                from utils.formatters import fmt_price, _pct_lev
                text = (
                    f"✅ <b>ZOCKER SAVDO OCHILDI!</b>\n"
                    f"{'═'*28}\n"
                    f"🕯️ <b>{count} ta ketma-ket {color_txt} sham</b> → Mean Reversion\n"
                    f"{'─'*28}\n"
                    f"💎 <b>{symbol}</b> — {dir_e}\n"
                    f"⏱️ Timeframe: <b>{tf}</b>\n"
                    f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
                    f"⚡ Leverage: <b>{max_lev}x</b> (KROSS)\n"
                    f"📦 Hajm: <code>{size}</code>\n"
                    f"💵 Marja: <code>{order_usdt:.2f} USDT</code>\n"
                    f"{'─'*28}\n"
                    f"💚 TP: <code>${fmt_price(tp)}</code>  ({_pct_lev(tp, entry)})\n"
                    f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry)})"
                )
                try:
                    await self.bot.send_message(
                        chat_id=gs.notifier_chat_id, text=text, parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Zocker trade notify: {e}")

        except Exception as e:
            logger.error(f"Zocker auto-trade xato {symbol}: {e}")

    async def _send_alert(self, symbol: str, tf: str, direction: str, count: int,
                           raw: list, entry: float, tp: float, sl: float):
        """Signal alert va chart yuborish."""
        if not self.bot or not gs.notifier_chat_id:
            return
        if not gs.zocker_notify:
            logger.info(f"Zocker xabarnomalar o'chirilgan — {symbol} o'tkazildi")
            return

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

        color_txt = "yashil" if direction == "SHORT" else "qizil"
        dir_text  = "🔴 SOTISH (SHORT)" if direction == "SHORT" else "🟢 XARID (LONG)"
        reason    = (
            "Overbought — narx tushishi kutiladi"
            if direction == "SHORT" else
            "Oversold — narx ko'tarilishi kutiladi"
        )

        text = (
            f"🕯️ <b>ZOCKER SIGNAL TOPILDI!</b>\n"
            f"{'═'*28}\n"
            f"💎 <b>{symbol}</b> — {dir_text}\n"
            f"⏱️ Timeframe: <b>{tf}</b>\n"
            f"🕯️ <b>{count} ta ketma-ket {color_txt} sham</b> yopildi!\n"
            f"💡 <i>{reason}</i>\n"
            f"{'─'*28}\n"
        )
        if entry > 0:
            from utils.formatters import fmt_price, _pct_lev
            text += f"💲 Narx: <code>${fmt_price(entry)}</code>\n"
            if tp > 0:
                text += f"💚 TP: <code>${fmt_price(tp)}</code>  ({_pct_lev(tp, entry)})\n"
            if sl > 0:
                text += f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry)})\n"

        if gs.auto_trade_enabled and gs.zocker_enabled:
            text += f"{'─'*28}\n⚡ <b>Avtomatik pozitsiya ochilmoqda...</b>"
        elif not gs.zocker_enabled:
            text += f"{'─'*28}\n⏸️ <i>Zocker avtosavdo o'chirilgan</i>"
        else:
            text += f"{'─'*28}\n⚠️ <i>Avtosavdo o'chirilgan — qo'lda kirish mumkin.</i>"

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Qo'lda Kirish", callback_data=f"manual_trade_{symbol}")
        ]])

        try:
            from services.chart_generator import generate_zocker_chart
            buf = generate_zocker_chart(
                candles_data=raw, symbol=symbol,
                direction=direction, consecutive_count=count,
                timeframe=tf, entry=entry, tp=tp, sl=sl,
            )
            await self.bot.send_photo(
                chat_id=gs.notifier_chat_id, photo=buf,
                caption=f"🕯️ {symbol} {tf} — {count} ta {color_txt} sham | {direction}",
                reply_markup=kb
            )
        except Exception as chart_err:
            logger.warning(f"Zocker chart xato: {chart_err}")
            try:
                await self.bot.send_message(
                    chat_id=gs.notifier_chat_id, text=text,
                    parse_mode="HTML", reply_markup=kb
                )
            except Exception as e:
                logger.error(f"Zocker send error: {e}")
            return

        try:
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id, text=text,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Zocker send error: {e}")

    async def manual_scan_now(self) -> str:
        """Qo'lda scan qilish — /zocker_scan_now tugmasi uchun."""
        symbols = await self._get_all_symbols()
        found   = []
        checked = 0
        for symbol in symbols[:50]:
            for tf in ZOCKER_TIMEFRAMES:
                try:
                    candles = self.client.get_futures_candles(symbol, tf, 50)
                    if candles.get("code") != "00000":
                        continue
                    raw    = candles.get("data", [])
                    result = detect_consecutive_candles(raw, ZOCKER_MIN_CANDLES, ZOCKER_MAX_CANDLES)
                    if result:
                        direction, count = result
                        color = "yashil" if direction == "SHORT" else "qizil"
                        found.append(f"• {symbol} {tf}: {count} ta {color} → {direction}")
                    checked += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
        if found:
            return f"🕯️ <b>Topildi ({len(found)} ta):</b>\n" + "\n".join(found[:10])
        return f"🔍 {checked} ta symbol tekshirildi — hozircha signal yo'q."

"""
ZOKPAT Scanner — Chart pattern background scanner.
Scans all USDT-M futures on 15m, 1H, 4H, 1D timeframes.
Sends chart + alert on signal. Auto-trades if zokpat_enabled.
"""
import asyncio
import logging
import time
import re
from typing import Dict, List, Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import safe_float
from services.pattern_analyzer import detect_chart_patterns, _scale
from services import state as gs

logger = logging.getLogger(__name__)

ZOKPAT_TIMEFRAMES   = ["15m", "1H", "4H", "1D"]
ZOKPAT_INTERVAL     = 300        # 5 daqiqa
ZOKPAT_COOLDOWN     = 6 * 3600  # symbol uchun 6 soat cooldown
MIN_VOLUME_USDT     = 300_000
MIN_CONFIDENCE      = 70        # minimum ishonch foizi

# TF -> Bitget granularity mapping
TF_MAP = {
    "15m": "15m",
    "1H":  "1H",
    "4H":  "4H",
    "1D":  "1D",
}
TF_CANDLES = {
    "15m": 120,  # ~30 hours
    "1H":  120,  # ~5 days
    "4H":  100,  # ~17 days
    "1D":  100,  # 100 days
}
TF_SCORE = {"1D": 20, "4H": 15, "1H": 8, "15m": 3}

FALLBACK_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","LTCUSDT","DOTUSDT",
    "LINKUSDT","MATICUSDT","UNIUSDT","ATOMUSDT","NEARUSDT",
]


def _place_tp_sl(client, symbol, plan_type, trig, hold_side, sz):
    r = client.place_futures_tp_sl(
        symbol=symbol, plan_type=plan_type,
        trigger_price=str(trig), side=hold_side, size=str(sz)
    )
    if r.get("code") == "00000":
        return True, trig
    msg = r.get("msg", "")
    m = re.search(r"checkScale=(\d+)", msg)
    if m:
        trig2 = round(trig, int(m.group(1)))
        r2 = client.place_futures_tp_sl(
            symbol=symbol, plan_type=plan_type,
            trigger_price=str(trig2), side=hold_side, size=str(sz)
        )
        return r2.get("code") == "00000", trig2
    return False, trig


class ZokpatScanner:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot    = bot
        self.active = True
        self.last_alerts: Dict[str, float] = {}  # symbol -> timestamp

    def _is_on_cooldown(self, symbol: str) -> bool:
        return (time.time() - self.last_alerts.get(symbol, 0)) < ZOKPAT_COOLDOWN

    def _set_cooldown(self, symbol: str):
        self.last_alerts[symbol] = time.time()

    async def _get_symbols(self) -> List[str]:
        try:
            d = self.client.get_futures_tickers()
            if d.get("code") == "00000":
                tickers = [
                    t for t in d.get("data", [])
                    if str(t.get("symbol","")).endswith("USDT")
                    and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME_USDT
                ]
                tickers.sort(key=lambda x: safe_float(x.get("usdtVolume",0)), reverse=True)
                return [t["symbol"] for t in tickers]
        except Exception as e:
            logger.error(f"ZOKPAT get_symbols: {e}")
        return FALLBACK_SYMBOLS

    async def run(self):
        logger.info("🔮 ZOKPAT scanner started (15m/1H/4H/1D chart patterns, 24/7)")
        gs.scanner.add_log("🔮 ZOKPAT scanner ishga tushdi")
        while self.active:
            try:
                await self._scan_all()
            except Exception as e:
                logger.error(f"ZOKPAT scan error: {e}")
            await asyncio.sleep(ZOKPAT_INTERVAL)

    async def _scan_all(self):
        symbols = await self._get_symbols()
        candidates = []  # (score, symbol, tf, pattern_dict, raw_candles)

        for symbol in symbols:
            if self._is_on_cooldown(symbol):
                continue
            for tf in ZOKPAT_TIMEFRAMES:
                try:
                    limit = TF_CANDLES[tf]
                    candles = self.client.get_futures_candles(symbol, tf, limit)
                    if candles.get("code") != "00000":
                        await asyncio.sleep(0.05)
                        continue
                    raw = candles.get("data", [])
                    if not raw or len(raw) < 35:
                        continue
                    pat = detect_chart_patterns(raw, symbol, tf)
                    if pat and pat["confidence"] >= MIN_CONFIDENCE:
                        score = TF_SCORE.get(tf, 0) + (pat["confidence"] - MIN_CONFIDENCE)
                        candidates.append((score, symbol, tf, pat, raw))
                    await asyncio.sleep(0.12)
                except Exception as e:
                    logger.debug(f"ZOKPAT {symbol} {tf}: {e}")

        # Keep best per symbol
        best_per_symbol: Dict[str, tuple] = {}
        for score, symbol, tf, pat, raw in candidates:
            prev = best_per_symbol.get(symbol)
            if prev is None or score > prev[0]:
                best_per_symbol[symbol] = (score, tf, pat, raw)

        ranked = sorted(best_per_symbol.items(), key=lambda x: x[1][0], reverse=True)
        top = ranked[:5]

        if top:
            gs.scanner.add_log(f"🔮 ZOKPAT: {len(top)} pattern topildi")
        else:
            gs.scanner.add_log("🔮 ZOKPAT: pattern topilmadi")

        for symbol, (score, tf, pat, raw) in top:
            self._set_cooldown(symbol)
            direction = pat["direction"]
            logger.info(f"🔮 ZOKPAT: {symbol} {tf} {pat['pattern']} → {direction} ({pat['confidence']}%)")
            gs.scanner.add_log(
                f"🔮 ZOKPAT: {symbol} {tf} {pat['pattern']} {direction} {pat['confidence']}%"
            )
            await self._handle_signal(symbol, tf, pat, raw)
            await asyncio.sleep(2)

    async def _handle_signal(self, symbol: str, tf: str, pat: dict, raw: list):
        entry    = pat["entry"]
        tp       = pat["tp"]
        sl       = pat["sl"]
        direction = pat["direction"]

        # Cache signal for manual trade
        gs.pending_manual_trades[symbol] = {
            "symbol": symbol, "direction": direction,
            "entry": entry, "tp1": tp, "sl": sl, "atr": abs(tp - entry) * 0.5,
            "confidence": pat["confidence"], "timeframe": tf,
            "pattern": pat["pattern"],
            "reasons": [f"{pat['pattern']} ({tf}) — ZOKPAT Pattern Signal"],
        }

        await self._send_alert(symbol, tf, pat, raw)

        if gs.auto_trade_enabled and gs.zokpat_enabled and entry > 0:
            await self._auto_trade(symbol, tf, pat)

    async def _auto_trade(self, symbol: str, tf: str, pat: dict):
        entry     = pat["entry"]
        tp        = pat["tp"]
        sl        = pat["sl"]
        direction = pat["direction"]
        try:
            pos_d = self.client.get_futures_positions()
            if pos_d.get("code") == "00000":
                open_cnt = sum(1 for p in pos_d.get("data",[])
                               if safe_float(p.get("total",0)) > 0)
                if open_cnt >= gs.MAX_AUTO_POSITIONS:
                    gs.scanner.add_log(f"⏸️ ZOKPAT {symbol}: limit → o'tkazildi")
                    return

            acc = self.client.get_futures_account()
            if acc.get("code") != "00000":
                return
            ad      = acc["data"]
            balance = safe_float(ad.get("crossedMaxAvailable", -1))
            if balance < 0:
                balance = safe_float(ad.get("available", 0))
            if balance < 1.0:
                return

            from config import MIN_ORDER_USDT, MAX_ORDER_USDT
            pct        = gs.trade_balance_pct / 100.0
            order_usdt = max(MIN_ORDER_USDT, min(MAX_ORDER_USDT, balance * pct))

            max_lev = 20
            try:
                ld = self.client.get_futures_leverage_info(symbol)
                if ld.get("code") == "00000":
                    max_lev = int(safe_float(ld["data"].get("maxLeverage", 20)))
            except Exception:
                pass

            confirmed_lev = max_lev
            try:
                self.client.set_margin_mode(symbol, "crossed")
                r = self.client.set_leverage_cross(symbol, max_lev)
                if r.get("code") != "00000":
                    self.client.set_leverage(symbol, max_lev, hold_side="long")
                    self.client.set_leverage(symbol, max_lev, hold_side="short")
                sym_acc = self.client.get_futures_symbol_account(symbol)
                if sym_acc.get("code") == "00000":
                    lv = int(safe_float(sym_acc["data"].get("leverage", max_lev)))
                    if lv > 0:
                        confirmed_lev = lv
            except Exception as e:
                logger.warning(f"ZOKPAT leverage {symbol}: {e}")

            side      = "sell" if direction == "SHORT" else "buy"
            hold_side = "short" if direction == "SHORT" else "long"
            size      = order_usdt * confirmed_lev / entry
            try:
                d = self.client.get_futures_contract_info(symbol)
                if d.get("code") == "00000" and d.get("data"):
                    c2       = d["data"][0]
                    min_size = safe_float(c2.get("minTradeNum", 0.001))
                    prec     = len(str(min_size).split(".")[-1]) if "." in str(min_size) else 4
                    size     = max(min_size, round(size, prec))
            except Exception:
                size = max(0.001, round(size, 4))

            result = self.client.place_futures_order(
                symbol=symbol, side=side, trade_side="open",
                size=str(size), order_type="market"
            )
            if result.get("code") != "00000":
                logger.error(f"ZOKPAT order {symbol}: {result.get('msg')}")
                gs.scanner.add_log(f"❌ ZOKPAT {symbol}: {result.get('msg','')[:40]}")
                return

            gs.scanner.add_log(f"✅ ZOKPAT savdo: {symbol} {direction} {confirmed_lev}x")

            tp_ok, _ = _place_tp_sl(self.client, symbol, "pos_profit", tp, hold_side, size)
            if not tp_ok:
                self.client.close_futures_position(symbol, hold_side)
                gs.scanner.add_log(f"❌ ZOKPAT {symbol} TP fail → rollback")
                return

            sl_ok, _ = _place_tp_sl(self.client, symbol, "pos_loss", sl, hold_side, size)
            if not sl_ok:
                self.client.close_futures_position(symbol, hold_side)
                gs.scanner.add_log(f"❌ ZOKPAT {symbol} SL fail → rollback")
                return

            if self.bot and gs.notifier_chat_id:
                from utils.formatters import fmt_price, _pct_lev
                dir_e = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
                text = (
                    f"✅ <b>ZOKPAT SAVDO OCHILDI!</b>\n{'═'*28}\n"
                    f"🔮 <b>{pat['pattern']}</b> — {tf}\n{'─'*28}\n"
                    f"💎 <b>{symbol}</b> — {dir_e}\n"
                    f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
                    f"⚡ Leverage: <b>{confirmed_lev}x</b> (KROSS)\n"
                    f"📦 Hajm: <code>{size}</code>\n"
                    f"💵 Marja: <code>{order_usdt:.2f} USDT</code>\n{'─'*28}\n"
                    f"💚 TP: <code>${fmt_price(tp)}</code>  ({_pct_lev(tp, entry, confirmed_lev)})\n"
                    f"🛑 SL: <code>${fmt_price(sl)}</code>  ({_pct_lev(sl, entry, confirmed_lev)})"
                )
                try:
                    await self.bot.send_message(
                        chat_id=gs.notifier_chat_id, text=text, parse_mode="HTML"
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"ZOKPAT auto-trade {symbol}: {e}")

    async def _send_alert(self, symbol: str, tf: str, pat: dict, raw: list):
        if not self.bot or not gs.notifier_chat_id:
            return

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from utils.formatters import fmt_price, _pct_lev

        entry     = pat["entry"]
        tp        = pat["tp"]
        sl        = pat["sl"]
        direction = pat["direction"]
        conf      = pat["confidence"]
        pattern   = pat["pattern"]
        dir_e     = "🟢 XARID (LONG)" if direction == "LONG" else "🔴 SOTISH (SHORT)"

        tp_pct = _pct_lev(tp, entry) if entry > 0 else ""
        sl_pct = _pct_lev(sl, entry) if entry > 0 else ""

        tp_dist  = abs(tp - entry)
        sl_dist  = abs(sl - entry)
        foyda_pct = tp_dist / entry * 100 if entry > 0 else 0
        zarar_pct = sl_dist / entry * 100 if entry > 0 else 0

        text = (
            f"🔮 <b>ZOKPAT SIGNAL!</b>\n{'═'*28}\n"
            f"💎 <b>{symbol}</b> — {dir_e}\n"
            f"📐 Pattern: <b>{pattern}</b>\n"
            f"⏱️ Timeframe: <b>{tf}</b>\n"
            f"🎯 Ishonch: <b>{conf}%</b>\n{'─'*28}\n"
            f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
            f"💚 TP: <code>${fmt_price(tp)}</code>  ({tp_pct})  📈 +{foyda_pct:.2f}%\n"
            f"🛑 SL: <code>${fmt_price(sl)}</code>  ({sl_pct})  📉 -{zarar_pct:.2f}%\n"
            f"⚖️ Risk/Reward: <b>1:1</b>\n{'─'*28}\n"
        )
        if gs.auto_trade_enabled and gs.zokpat_enabled:
            text += "⚡ <b>Avtomatik pozitsiya ochilmoqda...</b>"
        else:
            text += "⏸️ <i>ZOKPAT avtosavdo o'chirilgan</i>"

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Qo'lda Kirish", callback_data=f"manual_trade_{symbol}")
        ]])

        try:
            from services.chart_generator import generate_pattern_chart
            buf = generate_pattern_chart(
                candles_data=raw, symbol=symbol,
                direction=direction, pattern_name=pattern,
                entry=entry, tp=tp, sl=sl, confidence=conf,
                timeframe=tf, pattern_draw=pat.get("draw", {}),
                supports=pat.get("supports", []),
                resistances=pat.get("resistances", []),
            )
            await self.bot.send_photo(
                chat_id=gs.notifier_chat_id, photo=buf,
                caption=f"🔮 {symbol} {tf} — {pattern} | {direction} | {conf}%",
                reply_markup=kb
            )
        except Exception as chart_err:
            logger.warning(f"ZOKPAT chart error: {chart_err}")

        try:
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id, text=text,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            logger.error(f"ZOKPAT send error: {e}")

    async def manual_scan_now(self) -> str:
        """Qo'lda skan — top 30 symbol, 1H va 4H."""
        symbols = await self._get_symbols()
        found   = []
        checked = 0
        for symbol in symbols[:30]:
            for tf in ["1H", "4H"]:
                try:
                    limit   = TF_CANDLES.get(tf, 100)
                    candles = self.client.get_futures_candles(symbol, tf, limit)
                    if candles.get("code") != "00000":
                        continue
                    raw = candles.get("data", [])
                    if not raw or len(raw) < 35:
                        continue
                    pat = detect_chart_patterns(raw, symbol, tf)
                    if pat and pat["confidence"] >= 68:
                        dir_e = "🟢 LONG" if pat["direction"] == "LONG" else "🔴 SHORT"
                        found.append(
                            f"• <b>{symbol}</b> {tf}: {pat['pattern']} → {dir_e} "
                            f"({pat['confidence']}%)"
                        )
                    checked += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
        if found:
            return f"🔮 <b>ZOKPAT topildi ({len(found)} ta):</b>\n" + "\n".join(found[:10])
        return f"🔍 {checked} ta symbol tekshirildi — hozircha pattern yo'q."

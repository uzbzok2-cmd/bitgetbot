"""
Auto-trading engine:
- Scans markets every 5 min
- 70%+ → auto trade + sends signal with chart image
- <70% → saved to history only (no auto-send, no auto-trade)
- Min order $1, Max $5
"""
import asyncio
import time
import logging
from typing import Optional, List, Dict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import analyze_symbol, safe_float
from services import state as gs
from config import (
    ORDER_RATIO, MAX_FUTURES_ORDERS,
    AUTO_TRADE_CONFIDENCE, SIGNAL_NOTIFY_THRESHOLD,
    MIN_ORDER_USDT, MAX_ORDER_USDT
)

logger = logging.getLogger(__name__)

PRIORITY_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT",
]


class TradingEngine:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot    = bot
        self.active = True
        self.scan_interval = 300
        self.active_futures_signals: Dict = {}

    # ── helpers ────────────────────────────────────────────
    async def _futures_balance(self) -> float:
        try:
            d = self.client.get_futures_account()
            if d.get("code") == "00000":
                return safe_float(d["data"].get("available", 0))
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return 0.0

    async def _open_positions_count(self) -> int:
        try:
            d = self.client.get_futures_positions()
            if d.get("code") == "00000":
                return len([p for p in d.get("data", []) if safe_float(p.get("total", 0)) > 0])
        except Exception:
            pass
        return 0

    async def _get_max_leverage(self, symbol: str) -> int:
        try:
            d = self.client.get_futures_leverage_info(symbol)
            if d.get("code") == "00000":
                return int(safe_float(d["data"].get("maxLeverage", 20)))
        except Exception:
            pass
        return 20

    async def _top_futures_symbols(self, n: int = 30) -> List[str]:
        try:
            d = self.client.get_futures_tickers()
            if d.get("code") == "00000":
                tickers = [
                    t for t in d.get("data", [])
                    if str(t.get("symbol", "")).endswith("USDT")
                    and safe_float(t.get("usdtVolume", 0)) > 500_000
                ]
                tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
                symbols = [t["symbol"] for t in tickers[:n]]
                for sym in PRIORITY_SYMBOLS:
                    if sym not in symbols:
                        symbols.insert(0, sym)
                return symbols[:n]
        except Exception as e:
            logger.error(f"Get symbols error: {e}")
        return PRIORITY_SYMBOLS

    def _calc_order_usdt(self, balance: float) -> float:
        raw = balance * 0.50 * ORDER_RATIO
        return max(MIN_ORDER_USDT, min(MAX_ORDER_USDT, raw))

    # ── main loops ─────────────────────────────────────────
    async def run_futures_scanner(self):
        while self.active:
            try:
                await self._scan_futures()
            except Exception as e:
                logger.error(f"Scanner error: {e}")
                gs.scanner.add_log(f"❌ Xato: {str(e)[:50]}")
            await asyncio.sleep(self.scan_interval)

    # ── futures scan ───────────────────────────────────────
    async def _scan_futures(self):
        gs.scanner.is_scanning    = True
        gs.scanner.signals_this_scan = 0
        gs.scanner.last_scan_time    = time.time()
        gs.scanner.next_scan_time    = time.time() + self.scan_interval
        gs.scanner.add_log("🔍 Skan boshlandi")

        if not gs.auto_trade_enabled:
            gs.scanner.add_log("⏸️ Avtosavdo o'chirilgan")

        open_count = await self._open_positions_count()
        balance    = await self._futures_balance()
        order_usdt = self._calc_order_usdt(balance)

        gs.scanner.add_log(f"💼 {balance:.2f}$ | Order: {order_usdt:.2f}$ | Ochiq: {open_count}")

        symbols = await self._top_futures_symbols(30)
        gs.scanner.total_symbols  = len(symbols)
        gs.scanner.symbols_checked = 0

        for symbol in symbols:
            gs.scanner.current_symbol  = symbol
            gs.scanner.symbols_checked += 1

            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") != "00000":
                    await asyncio.sleep(0.2)
                    continue

                raw = candles.get("data", [])
                sig = analyze_symbol(raw, symbol, "1H")
                if not sig:
                    await asyncio.sleep(0.2)
                    continue

                conf = sig["confidence"]
                gs.scanner.add_log(f"📊 {symbol}: {sig['direction']} {conf}%")

                # Always save to history
                gs.signal_history.add(sig)
                gs.scanner.signals_this_scan += 1

                # Only act on 70%+ signals
                if conf >= SIGNAL_NOTIFY_THRESHOLD:
                    # Send signal with chart to user
                    await self._send_signal_with_chart(sig, raw)

                    # Auto trade if enabled and room available
                    if (gs.auto_trade_enabled and
                            open_count < MAX_FUTURES_ORDERS and
                            balance >= MIN_ORDER_USDT and
                            symbol not in self.active_futures_signals):
                        gs.scanner.add_log(f"⚡ Savdo: {symbol} {sig['direction']} {conf}%")
                        await self._place_futures_trade(sig, order_usdt, raw)
                        open_count += 1

                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Scan {symbol}: {e}")
                await asyncio.sleep(0.3)

        gs.scanner.is_scanning     = False
        gs.scanner.current_symbol  = ""
        gs.scanner.add_log(f"✅ Skan tugadi. 70%+ signallar: {gs.scanner.signals_this_scan}")

    # ── send signal + chart ────────────────────────────────
    async def _send_signal_with_chart(self, sig: Dict, candles_data: list):
        if not self.bot or not gs.notifier_chat_id:
            return
        from utils.formatters import format_signal_detail
        text = format_signal_detail(sig)
        try:
            # Send chart image first
            try:
                from services.chart_generator import generate_signal_chart
                buf = generate_signal_chart(
                    candles_data=candles_data,
                    symbol=sig["symbol"],
                    direction=sig["direction"],
                    entry=sig["entry"],
                    tp1=sig["tp1"],
                    tp2=sig["tp2"],
                    sl=sig["sl"],
                    confidence=sig["confidence"],
                    timeframe=sig.get("timeframe", "1H"),
                )
                await self.bot.send_photo(
                    chat_id=gs.notifier_chat_id,
                    photo=buf,
                    caption=f"📊 {sig['symbol']} — {sig['confidence']}% ishonch"
                )
            except Exception as chart_err:
                logger.warning(f"Chart error: {chart_err}")

            # Then send text detail (no delete)
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Send signal error: {e}")

    # ── place futures trade ────────────────────────────────
    async def _place_futures_trade(self, signal: Dict, order_usdt: float, candles_data: list):
        symbol = signal["symbol"]
        dir_   = signal["direction"]
        entry  = signal["entry"]
        atr    = signal["atr"]
        max_lev = await self._get_max_leverage(symbol)

        try:
            self.client.set_margin_mode(symbol, "crossed")
            self.client.set_leverage(symbol, max_lev, hold_side="long")
            self.client.set_leverage(symbol, max_lev, hold_side="short")
        except Exception:
            pass

        commission = 0.0006 * 2 * max_lev
        atr_r = atr / entry
        if dir_ == "LONG":
            final_tp1 = round(entry * (1 + atr_r * 1.5 - commission), 8)
            final_tp2 = round(entry * (1 + atr_r * 3.0 - commission), 8)
            final_sl  = round(entry * (1 - atr_r * 1.5 - commission), 8)
            side = "buy"; hold_side = "long"
        else:
            final_tp1 = round(entry * (1 - atr_r * 1.5 + commission), 8)
            final_tp2 = round(entry * (1 - atr_r * 3.0 + commission), 8)
            final_sl  = round(entry * (1 + atr_r * 1.5 + commission), 8)
            side = "sell"; hold_side = "short"

        # Size
        size = order_usdt * max_lev / entry
        try:
            d = self.client.get_futures_contract_info(symbol)
            if d.get("code") == "00000":
                contracts = d.get("data", [])
                if contracts:
                    c = contracts[0]
                    min_size = safe_float(c.get("minTradeNum", 0.001))
                    prec = len(str(min_size).split(".")[-1]) if "." in str(min_size) else 4
                    size = max(min_size, round(size, prec))
        except Exception:
            size = round(size, 4)

        if size <= 0:
            return

        result = self.client.place_futures_order(
            symbol=symbol, side=side, trade_side="open",
            size=str(size), order_type="market"
        )
        if result.get("code") != "00000":
            logger.error(f"Order failed {symbol}: {result.get('msg')}")
            gs.scanner.add_log(f"❌ {symbol}: {result.get('msg', '')[:40]}")
            return

        order_id = result.get("data", {}).get("orderId", "")
        logger.info(f"✅ Order: {symbol} {dir_} {size} @ {max_lev}x")
        gs.scanner.add_log(f"✅ Savdo: {symbol} {dir_} {max_lev}x")

        self.active_futures_signals[symbol] = {
            "signal": signal, "order_id": order_id, "leverage": max_lev,
            "size": size, "margin": order_usdt, "open_time": int(time.time())
        }
        gs.scanner.active_trades[symbol] = {
            "symbol": symbol, "direction": dir_, "leverage": max_lev,
            "size": size, "margin": order_usdt, "entry": entry,
            "open_time_str": __import__("datetime").datetime.utcnow().strftime("%H:%M")
        }

        tp1_size = round(size / 2, 4)
        for plan_type, trig, sz in [
            ("profit_loss", final_tp1, tp1_size),
            ("profit_loss", final_tp2, tp1_size),
            ("loss_plan",   final_sl,  size),
        ]:
            try:
                self.client.place_futures_tp_sl(
                    symbol=symbol, plan_type=plan_type,
                    trigger_price=str(trig), side=hold_side, size=str(sz)
                )
            except Exception as e:
                logger.error(f"TP/SL error {symbol}: {e}")

        # Send trade notification with position chart
        if self.bot and gs.notifier_chat_id:
            from utils.formatters import format_auto_trade_notify
            text = format_auto_trade_notify(
                signal=signal, leverage=max_lev, size=size,
                margin=order_usdt, tp1=final_tp1, tp2=final_tp2,
                sl=final_sl, order_id=order_id
            )
            try:
                from services.chart_generator import generate_position_chart
                buf = generate_position_chart(
                    candles_data=candles_data,
                    symbol=symbol, direction=dir_,
                    entry=entry, mark_price=entry,
                    tp_levels=[final_tp1, final_tp2],
                    sl_levels=[final_sl],
                    unrealized_pnl=0.0, leverage=max_lev
                )
                await self.bot.send_photo(
                    chat_id=gs.notifier_chat_id, photo=buf,
                    caption=f"🚨 SAVDO OCHILDI: {symbol} {dir_} {max_lev}x"
                )
            except Exception as ce:
                logger.warning(f"Position chart error: {ce}")
            try:
                await self.bot.send_message(
                    chat_id=gs.notifier_chat_id, text=text, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Trade notify error: {e}")

    # ── get top signals for display ────────────────────────
    async def get_top_signals(self, top_n: int = 10, min_conf: int = 70) -> List[Dict]:
        symbols = await self._top_futures_symbols(40)
        signals = []
        gs.scanner.add_log(f"🔍 Top signallar ({min_conf}%+)...")
        for symbol in symbols[:35]:
            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    sig = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if sig and sig["confidence"] >= min_conf:
                        signals.append(sig)
                        gs.signal_history.add(sig)
                await asyncio.sleep(0.2)
            except Exception:
                pass
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals[:top_n]

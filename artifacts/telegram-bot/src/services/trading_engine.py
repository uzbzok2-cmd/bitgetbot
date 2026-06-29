"""
Auto-trading engine: scans markets, generates signals, places orders.
- 60%+ confidence → auto trade
- 55-60% confidence → ask user permission
- Min order $1, Max order $5
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
    ORDER_RATIO, MAX_FUTURES_ORDERS, MAX_SPOT_ORDERS,
    AUTO_TRADE_CONFIDENCE, ASK_PERMISSION_CONFIDENCE_MIN,
    MIN_ORDER_USDT, MAX_ORDER_USDT, FUTURES_PRODUCT_TYPE
)

logger = logging.getLogger(__name__)

# Top symbols always checked
PRIORITY_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT",
]


class TradingEngine:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot = bot
        self.active = True
        self.scan_interval = 300   # 5 min
        self.active_futures_signals: Dict = {}
        self.active_spot_signals: Dict = {}

    # ── helpers ────────────────────────────────────────────
    async def _futures_balance(self) -> float:
        try:
            d = self.client.get_futures_account()
            if d.get("code") == "00000":
                return safe_float(d["data"].get("available", 0))
        except Exception as e:
            logger.error(f"Futures balance error: {e}")
        return 0.0

    async def _spot_balance_usdt(self) -> float:
        try:
            d = self.client.get_spot_account()
            if d.get("code") == "00000":
                for a in d.get("data", []):
                    if a.get("coin") == "USDT":
                        return safe_float(a.get("available", 0))
        except Exception as e:
            logger.error(f"Spot balance error: {e}")
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
                # Ensure priority symbols are included
                for sym in PRIORITY_SYMBOLS:
                    if sym not in symbols:
                        symbols.insert(0, sym)
                return symbols[:n]
        except Exception as e:
            logger.error(f"Get symbols error: {e}")
        return PRIORITY_SYMBOLS

    def _calc_order_usdt(self, balance: float) -> float:
        """Calculate per-order USDT — clamped between MIN and MAX."""
        raw = balance * 0.50 * ORDER_RATIO   # 50% of balance × 5%
        return max(MIN_ORDER_USDT, min(MAX_ORDER_USDT, raw))

    # ── main loops ─────────────────────────────────────────
    async def run_futures_scanner(self):
        while self.active:
            try:
                await self._scan_futures()
            except Exception as e:
                logger.error(f"Futures scanner error: {e}")
                gs.scanner.add_log(f"❌ Scanner xato: {str(e)[:50]}")
            await asyncio.sleep(self.scan_interval)

    async def run_spot_scanner(self):
        while self.active:
            try:
                await self._scan_spot()
            except Exception as e:
                logger.error(f"Spot scanner error: {e}")
            await asyncio.sleep(self.scan_interval + 60)

    # ── futures scan ───────────────────────────────────────
    async def _scan_futures(self):
        gs.scanner.is_scanning = True
        gs.scanner.signals_this_scan = 0
        gs.scanner.last_scan_time = time.time()
        gs.scanner.next_scan_time = time.time() + self.scan_interval
        gs.scanner.add_log("🔍 Fyuchers skaneri boshlandi")

        if not gs.auto_trade_enabled:
            gs.scanner.add_log("⏸️ Avtosavdo o'chirilgan — faqat signal tekshiriladi")

        open_count = await self._open_positions_count()
        balance    = await self._futures_balance()
        order_usdt = self._calc_order_usdt(balance)

        gs.scanner.add_log(f"💼 Balans: {balance:.2f}$ | Order: {order_usdt:.2f}$ | Ochiq: {open_count}")

        symbols = await self._top_futures_symbols(30)
        gs.scanner.total_symbols = len(symbols)
        gs.scanner.symbols_checked = 0

        for symbol in symbols:
            gs.scanner.current_symbol = symbol
            gs.scanner.symbols_checked += 1

            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") != "00000":
                    await asyncio.sleep(0.2)
                    continue

                sig = analyze_symbol(candles.get("data", []), symbol, "1H")
                if not sig:
                    await asyncio.sleep(0.2)
                    continue

                conf = sig["confidence"]
                gs.scanner.add_log(f"📊 {symbol}: {sig['direction']} {conf}%")
                gs.scanner.signals_this_scan += 1

                # Save to signal history
                gs.signal_history.add(sig)

                # Notify user with signal (always)
                await self._send_signal_to_user(sig)

                # Trade decision
                if open_count < MAX_FUTURES_ORDERS and balance >= MIN_ORDER_USDT:
                    if symbol not in self.active_futures_signals:
                        if conf >= AUTO_TRADE_CONFIDENCE and gs.auto_trade_enabled:
                            # Auto trade
                            gs.scanner.add_log(f"⚡ Auto savdo: {symbol} {sig['direction']} {conf}%")
                            await self._place_futures_trade(sig, order_usdt)
                            open_count += 1
                        elif ASK_PERMISSION_CONFIDENCE_MIN <= conf < AUTO_TRADE_CONFIDENCE:
                            # Ask permission
                            gs.scanner.add_log(f"❓ Ruxsat so'ralmoqda: {symbol} {conf}%")
                            await self._ask_permission(sig, order_usdt)

                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Scan error {symbol}: {e}")
                await asyncio.sleep(0.3)

        gs.scanner.is_scanning = False
        gs.scanner.current_symbol = ""
        gs.scanner.add_log(f"✅ Skan tugadi. Signallar: {gs.scanner.signals_this_scan}")

    # ── spot scan ──────────────────────────────────────────
    async def _scan_spot(self):
        if not gs.auto_trade_enabled:
            return
        balance = await self._spot_balance_usdt()
        if balance < MIN_ORDER_USDT:
            return
        order_usdt = self._calc_order_usdt(balance)
        try:
            d = self.client.get_spot_tickers()
            if d.get("code") == "00000":
                tickers = [
                    t for t in d.get("data", [])
                    if str(t.get("symbol", "")).endswith("USDT")
                    and safe_float(t.get("usdtVol", 0)) > 300_000
                ]
                tickers.sort(key=lambda x: safe_float(x.get("usdtVol", 0)), reverse=True)
                top = [t["symbol"] for t in tickers[:20]]
            else:
                top = PRIORITY_SYMBOLS[:10]
        except Exception:
            top = PRIORITY_SYMBOLS[:10]

        for symbol in top:
            if symbol in self.active_spot_signals:
                continue
            try:
                candles = self.client.get_spot_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    sig = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if sig and sig["direction"] == "LONG" and sig["confidence"] >= AUTO_TRADE_CONFIDENCE + 5:
                        await self._place_spot_trade(sig, order_usdt)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Spot scan error {symbol}: {e}")

    # ── send signal to user ────────────────────────────────
    async def _send_signal_to_user(self, sig: Dict):
        """Send signal detail message to user — never delete."""
        if not self.bot or not gs.notifier_chat_id:
            return
        try:
            from utils.formatters import format_signal_detail
            text = format_signal_detail(sig)
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Send signal error: {e}")

    # ── ask permission ─────────────────────────────────────
    async def _ask_permission(self, sig: Dict, order_usdt: float):
        if not self.bot or not gs.notifier_chat_id:
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from utils.formatters import format_permission_request

        symbol = sig["symbol"]
        max_lev = await self._get_max_leverage(symbol)

        entry = sig["entry"]
        dir_  = sig["direction"]
        atr   = sig["atr"]
        commission = 0.0006 * 2 * max_lev

        if dir_ == "LONG":
            tp1 = round(entry + atr * 1.5 - commission * entry, 8)
            tp2 = round(entry + atr * 3.0 - commission * entry, 8)
            sl  = round(entry - atr * 1.5 + commission * entry, 8)
        else:
            tp1 = round(entry - atr * 1.5 + commission * entry, 8)
            tp2 = round(entry - atr * 3.0 + commission * entry, 8)
            sl  = round(entry + atr * 1.5 - commission * entry, 8)

        text = format_permission_request(sig, max_lev, order_usdt, tp1, tp2, sl)
        key  = f"perm_{symbol}_{sig['direction']}_{int(time.time())}"
        gs.pending_permission_signals[key] = {
            "signal": sig, "order_usdt": order_usdt,
            "tp1": tp1, "tp2": tp2, "sl": sl, "leverage": max_lev
        }
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, savdo qil!", callback_data=f"approve_{key}"),
             InlineKeyboardButton("❌ Yo'q", callback_data=f"reject_{key}")]
        ])
        try:
            await self.bot.send_message(
                chat_id=gs.notifier_chat_id, text=text,
                reply_markup=kb, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ask permission error: {e}")

    # ── place futures trade ────────────────────────────────
    async def _place_futures_trade(self, signal: Dict, order_usdt: float):
        symbol = signal["symbol"]
        dir_   = signal["direction"]
        entry  = signal["entry"]
        atr    = signal["atr"]
        max_lev = await self._get_max_leverage(symbol)

        # Set margin mode
        try:
            self.client.set_margin_mode(symbol, "crossed")
            self.client.set_leverage(symbol, max_lev, hold_side="long")
            self.client.set_leverage(symbol, max_lev, hold_side="short")
        except Exception:
            pass

        commission = 0.0006 * 2 * max_lev
        if dir_ == "LONG":
            final_tp1 = round(entry * (1 + atr / entry * 1.5 - commission), 8)
            final_tp2 = round(entry * (1 + atr / entry * 3.0 - commission), 8)
            final_sl  = round(entry * (1 - atr / entry * 1.5 - commission), 8)
            side = "buy"; hold_side = "long"
        else:
            final_tp1 = round(entry * (1 - atr / entry * 1.5 + commission), 8)
            final_tp2 = round(entry * (1 - atr / entry * 3.0 + commission), 8)
            final_sl  = round(entry * (1 + atr / entry * 1.5 + commission), 8)
            side = "sell"; hold_side = "short"

        # Size
        position_value = order_usdt * max_lev
        size = position_value / entry

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
            gs.scanner.add_log(f"❌ Order xato {symbol}: {result.get('msg', '')[:40]}")
            return

        order_id = result.get("data", {}).get("orderId", "")
        logger.info(f"✅ Order placed: {symbol} {dir_} {size} @ {max_lev}x")
        gs.scanner.add_log(f"✅ Savdo ochildi: {symbol} {dir_} {max_lev}x")

        self.active_futures_signals[symbol] = {
            "signal": signal, "order_id": order_id, "leverage": max_lev,
            "size": size, "margin": order_usdt, "open_time": int(time.time())
        }
        gs.scanner.active_trades[symbol] = {
            "symbol": symbol, "direction": dir_, "leverage": max_lev,
            "size": size, "margin": order_usdt, "entry": entry,
            "open_time_str": __import__("datetime").datetime.utcnow().strftime("%H:%M")
        }

        # TP1 half
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

        # Notify user
        if self.bot and gs.notifier_chat_id:
            from utils.formatters import format_auto_trade_notify
            text = format_auto_trade_notify(
                signal=signal, leverage=max_lev, size=size,
                margin=order_usdt, tp1=final_tp1, tp2=final_tp2,
                sl=final_sl, order_id=order_id
            )
            try:
                await self.bot.send_message(
                    chat_id=gs.notifier_chat_id, text=text, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Notify error: {e}")

    # ── place spot trade ───────────────────────────────────
    async def _place_spot_trade(self, signal: Dict, order_usdt: float):
        symbol = signal["symbol"]
        entry  = signal["entry"]
        commission = 0.001 * 2
        tp1_pct = abs(signal["tp1"] - entry) / entry - commission
        sl_pct  = abs(entry - signal["sl"])  / entry + commission
        size    = order_usdt / entry
        try:
            sd = self.client.get_spot_symbol_info(symbol)
            if sd.get("code") == "00000":
                slist = sd.get("data", [])
                if slist:
                    s = slist[0]
                    min_qty = safe_float(s.get("minTradeAmount", 0.001))
                    prec    = int(s.get("quantityPrecision", 4))
                    size    = max(min_qty, round(size, prec))
        except Exception:
            size = round(size, 4)
        r = self.client.place_spot_order(
            symbol=symbol, side="buy", order_type="market", size=str(size)
        )
        if r.get("code") != "00000":
            logger.error(f"Spot order failed {symbol}: {r.get('msg')}")
            return
        self.active_spot_signals[symbol] = {
            "signal": signal, "size": size, "open_time": int(time.time())
        }
        logger.info(f"✅ Spot order: {symbol} BUY {size}")

    # ── approve pending signal ─────────────────────────────
    async def approve_signal(self, key: str):
        pending = gs.pending_permission_signals.pop(key, None)
        if not pending:
            return False
        await self._place_futures_trade(pending["signal"], pending["order_usdt"])
        return True

    # ── get top signals for display ────────────────────────
    async def get_top_signals(self, top_n: int = 10) -> List[Dict]:
        symbols = await self._top_futures_symbols(40)
        signals = []
        gs.scanner.add_log("🔍 Top signallar hisoblanmoqda...")
        for symbol in symbols[:35]:
            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    sig = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if sig and sig["confidence"] >= 55:
                        signals.append(sig)
                        gs.signal_history.add(sig)
                await asyncio.sleep(0.2)
            except Exception:
                pass
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals[:top_n]

"""
Auto-trading engine: scans markets, generates signals, places orders with TP/SL.
Runs in background, respects balance limits.
"""
import asyncio
import time
import math
import logging
from typing import Optional, List, Dict, Tuple
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.analyzer import analyze_symbol, safe_float
from config import (
    BALANCE_USE_RATIO, ORDER_RATIO, MAX_FUTURES_ORDERS, MAX_SPOT_ORDERS,
    MIN_SIGNAL_CONFIDENCE, FUTURES_PRODUCT_TYPE
)

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self, client: BitgetClient, notifier=None):
        self.client = client
        self.notifier = notifier
        self.active = True
        self.last_scan_time = 0
        self.scan_interval = 300  # 5 minutes
        self.futures_symbols_cache = []
        self.spot_symbols_cache = []
        self.active_futures_signals = {}
        self.active_spot_signals = {}

    async def run_futures_scanner(self):
        """Continuously scan futures markets and open/manage trades."""
        while self.active:
            try:
                await self._scan_and_trade_futures()
            except Exception as e:
                logger.error(f"Futures scanner error: {e}")
            await asyncio.sleep(self.scan_interval)

    async def run_spot_scanner(self):
        """Continuously scan spot markets and open/manage trades."""
        while self.active:
            try:
                await self._scan_and_trade_spot()
            except Exception as e:
                logger.error(f"Spot scanner error: {e}")
            await asyncio.sleep(self.scan_interval + 30)

    async def _get_futures_balance(self) -> float:
        try:
            data = self.client.get_futures_account()
            if data.get("code") == "00000":
                account = data.get("data", {})
                return safe_float(account.get("available", 0))
            accounts = self.client.get_futures_accounts_all()
            if accounts.get("code") == "00000":
                for acc in accounts.get("data", []):
                    if acc.get("marginCoin") == "USDT":
                        return safe_float(acc.get("available", 0))
        except Exception as e:
            logger.error(f"Get futures balance error: {e}")
        return 0.0

    async def _get_spot_balance_usdt(self) -> float:
        try:
            data = self.client.get_spot_account()
            if data.get("code") == "00000":
                for asset in data.get("data", []):
                    if asset.get("coin") == "USDT":
                        return safe_float(asset.get("available", 0))
        except Exception as e:
            logger.error(f"Get spot balance error: {e}")
        return 0.0

    async def _count_open_futures_positions(self) -> int:
        try:
            data = self.client.get_futures_positions()
            if data.get("code") == "00000":
                positions = [p for p in data.get("data", []) if safe_float(p.get("total", 0)) > 0]
                return len(positions)
        except Exception:
            pass
        return 0

    async def _count_open_spot_orders(self) -> int:
        try:
            data = self.client.get_spot_open_orders()
            if data.get("code") == "00000":
                return len(data.get("data", {}).get("entrustedList", []))
        except Exception:
            pass
        return 0

    async def _get_top_futures_symbols(self, top_n: int = 30) -> List[str]:
        """Get top futures symbols by volume."""
        try:
            data = self.client.get_futures_tickers()
            if data.get("code") == "00000":
                tickers = data.get("data", [])
                usdt_tickers = [
                    t for t in tickers
                    if str(t.get("symbol", "")).endswith("USDT")
                    and safe_float(t.get("usdtVolume", 0)) > 1000000
                ]
                usdt_tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
                return [t["symbol"] for t in usdt_tickers[:top_n]]
        except Exception as e:
            logger.error(f"Get futures symbols error: {e}")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT"]

    async def _get_max_leverage(self, symbol: str) -> int:
        """Get maximum allowed leverage for symbol."""
        try:
            data = self.client.get_futures_leverage_info(symbol)
            if data.get("code") == "00000":
                d = data.get("data", {})
                max_lev = safe_float(d.get("maxLeverage", 20))
                return int(max_lev)
        except Exception:
            pass
        return 20

    async def _scan_and_trade_futures(self):
        """Scan futures markets and place trades based on signals."""
        open_count = await self._count_open_futures_positions()
        if open_count >= MAX_FUTURES_ORDERS:
            logger.info(f"Max futures positions reached ({open_count})")
            return

        balance = await self._get_futures_balance()
        if balance < 10:
            logger.info(f"Insufficient futures balance: {balance}")
            return

        tradeable_balance = balance * BALANCE_USE_RATIO
        per_order_balance = tradeable_balance * ORDER_RATIO

        symbols = await self._get_top_futures_symbols(30)
        signals_found = []

        for symbol in symbols:
            if len(signals_found) >= (MAX_FUTURES_ORDERS - open_count):
                break
            if symbol in self.active_futures_signals:
                continue
            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    analysis = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if analysis and analysis["confidence"] >= MIN_SIGNAL_CONFIDENCE:
                        signals_found.append(analysis)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Analysis error {symbol}: {e}")

        for signal in signals_found:
            await self._place_futures_trade(signal, per_order_balance)

    async def _place_futures_trade(self, signal: Dict, order_usdt: float):
        """Place futures trade with max leverage, TP×2, SL×1."""
        symbol = signal["symbol"]
        direction = signal["direction"]
        entry = signal["entry"]
        tp1 = signal["tp1"]
        tp2 = signal["tp2"]
        sl = signal["sl"]

        max_lev = await self._get_max_leverage(symbol)

        # Set margin mode and leverage
        try:
            self.client.set_margin_mode(symbol, "crossed")
            self.client.set_leverage(symbol, max_lev, hold_side="long")
            self.client.set_leverage(symbol, max_lev, hold_side="short")
        except Exception as e:
            logger.warning(f"Set leverage error {symbol}: {e}")

        # Calculate commission adjusted SL/TP (taker fee ~0.06%)
        commission_factor = 0.0006 * 2  # open + close
        leverage_factor = max_lev
        adjusted_commission = commission_factor * leverage_factor

        if direction == "LONG":
            sl_pct = abs(entry - sl) / entry
            tp1_pct = abs(tp1 - entry) / entry
            final_sl_pct = sl_pct + adjusted_commission
            final_tp1_pct = tp1_pct - adjusted_commission
            final_sl = round(entry * (1 - final_sl_pct), 6)
            final_tp1 = round(entry * (1 + final_tp1_pct), 6)
            final_tp2 = round(entry * (1 + final_tp1_pct * 2), 6)
            side = "buy"
            trade_side = "open"
            close_side = "sell"
            hold_side = "long"
        else:
            sl_pct = abs(sl - entry) / entry
            tp1_pct = abs(entry - tp1) / entry
            final_sl_pct = sl_pct + adjusted_commission
            final_tp1_pct = tp1_pct - adjusted_commission
            final_sl = round(entry * (1 + final_sl_pct), 6)
            final_tp1 = round(entry * (1 - final_tp1_pct), 6)
            final_tp2 = round(entry * (1 - final_tp1_pct * 2), 6)
            side = "sell"
            trade_side = "open"
            close_side = "buy"
            hold_side = "short"

        # Size in contracts (position size = order_usdt * leverage / price)
        position_value = order_usdt * max_lev
        size = position_value / entry

        # Get contract precision
        try:
            contract_data = self.client.get_futures_contract_info(symbol)
            if contract_data.get("code") == "00000":
                contracts = contract_data.get("data", [])
                if contracts:
                    c = contracts[0]
                    min_size = safe_float(c.get("minTradeNum", 0.001))
                    size_precision = len(str(min_size).split(".")[-1]) if "." in str(min_size) else 0
                    size = max(min_size, round(size, size_precision))
        except Exception:
            size = round(size, 4)

        if size <= 0:
            logger.warning(f"Invalid size for {symbol}: {size}")
            return

        # Place market order
        order_result = self.client.place_futures_order(
            symbol=symbol,
            side=side,
            trade_side=trade_side,
            size=str(size),
            order_type="market"
        )

        if order_result.get("code") != "00000":
            logger.error(f"Futures order failed {symbol}: {order_result.get('msg')}")
            return

        order_id = order_result.get("data", {}).get("orderId", "")
        logger.info(f"Futures order placed: {symbol} {direction} size={size} lev={max_lev}x")

        # Mark as active
        self.active_futures_signals[symbol] = {
            "signal": signal,
            "order_id": order_id,
            "leverage": max_lev,
            "size": size,
            "margin": order_usdt,
            "open_time": int(time.time())
        }

        # Place TP1 (half size)
        tp1_size = round(size / 2, 4)
        try:
            self.client.place_futures_tp_sl(
                symbol=symbol,
                plan_type="profit_loss",
                trigger_price=str(final_tp1),
                side=hold_side,
                size=str(tp1_size)
            )
        except Exception as e:
            logger.error(f"TP1 error {symbol}: {e}")

        # Place TP2 (remaining half)
        try:
            self.client.place_futures_tp_sl(
                symbol=symbol,
                plan_type="profit_loss",
                trigger_price=str(final_tp2),
                side=hold_side,
                size=str(tp1_size)
            )
        except Exception as e:
            logger.error(f"TP2 error {symbol}: {e}")

        # Place SL
        try:
            self.client.place_futures_tp_sl(
                symbol=symbol,
                plan_type="loss_plan",
                trigger_price=str(final_sl),
                side=hold_side,
                size=str(size)
            )
        except Exception as e:
            logger.error(f"SL error {symbol}: {e}")

        # Notify
        if self.notifier:
            await self.notifier(
                signal=signal,
                leverage=max_lev,
                size=size,
                margin=order_usdt,
                tp1=final_tp1,
                tp2=final_tp2,
                sl=final_sl,
                order_id=order_id
            )

    async def _scan_and_trade_spot(self):
        """Scan spot markets and buy/sell based on signals."""
        open_count = await self._count_open_spot_orders()
        if open_count >= MAX_SPOT_ORDERS:
            return

        balance = await self._get_spot_balance_usdt()
        if balance < 10:
            return

        per_order_balance = balance * ORDER_RATIO

        # Get spot tickers
        try:
            data = self.client.get_spot_tickers()
            if data.get("code") == "00000":
                tickers = data.get("data", [])
                usdt_tickers = [
                    t for t in tickers
                    if str(t.get("symbol", "")).endswith("USDT")
                    and safe_float(t.get("usdtVol", 0)) > 500000
                ]
                usdt_tickers.sort(key=lambda x: safe_float(x.get("usdtVol", 0)), reverse=True)
                top_symbols = [t["symbol"] for t in usdt_tickers[:20]]
            else:
                top_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        except Exception:
            top_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in top_symbols:
            if symbol in self.active_spot_signals:
                continue
            if open_count >= MAX_SPOT_ORDERS:
                break
            try:
                candles = self.client.get_spot_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    analysis = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if analysis and analysis["direction"] == "LONG" and analysis["confidence"] >= MIN_SIGNAL_CONFIDENCE + 5:
                        await self._place_spot_trade(analysis, per_order_balance)
                        open_count += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Spot analysis error {symbol}: {e}")

    async def _place_spot_trade(self, signal: Dict, order_usdt: float):
        """Place spot buy order with TP and SL."""
        symbol = signal["symbol"]
        entry = signal["entry"]
        tp1 = signal["tp1"]
        sl = signal["sl"]

        # Commission 0.1% for spot
        commission = 0.001 * 2
        sl_pct = abs(entry - sl) / entry + commission
        tp1_pct = abs(tp1 - entry) / entry - commission

        final_sl = round(entry * (1 - sl_pct), 6)
        final_tp = round(entry * (1 + tp1_pct), 6)

        size = order_usdt / entry

        try:
            sym_data = self.client.get_spot_symbol_info(symbol)
            if sym_data.get("code") == "00000":
                symbols_list = sym_data.get("data", [])
                if symbols_list:
                    s = symbols_list[0]
                    min_qty = safe_float(s.get("minTradeAmount", 0.001))
                    qty_precision = int(s.get("quantityPrecision", 4))
                    size = max(min_qty, round(size, qty_precision))
        except Exception:
            size = round(size, 4)

        result = self.client.place_spot_order(
            symbol=symbol,
            side="buy",
            order_type="market",
            size=str(size)
        )

        if result.get("code") != "00000":
            logger.error(f"Spot order failed {symbol}: {result.get('msg')}")
            return

        self.active_spot_signals[symbol] = {
            "signal": signal,
            "tp": final_tp,
            "sl": final_sl,
            "size": size,
            "open_time": int(time.time())
        }

        logger.info(f"Spot order placed: {symbol} BUY size={size}")

    async def get_top_signals(self, top_n: int = 10) -> List[Dict]:
        """Get top N signals sorted by confidence for display."""
        symbols = await self._get_top_futures_symbols(50)
        signals = []

        for symbol in symbols[:40]:
            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") == "00000":
                    analysis = analyze_symbol(candles.get("data", []), symbol, "1H")
                    if analysis and analysis["confidence"] >= 50:
                        signals.append(analysis)
                await asyncio.sleep(0.2)
            except Exception:
                pass

        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals[:top_n]

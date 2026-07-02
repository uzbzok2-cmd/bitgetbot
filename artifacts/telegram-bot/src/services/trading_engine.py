"""
Auto-trading engine:
- Scans markets every 5 min
- 70%+ → auto trade only (signal notifications BLOCKED per user request)
- <70% → saved to history only
- TP1 = 100% of position, SL x1
"""
import asyncio
import re
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
    MIN_ORDER_USDT, MAX_ORDER_USDT, MIN_SIGNAL_CONFIDENCE
)

logger = logging.getLogger(__name__)

PRIORITY_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT",
]

# Bu symbollar uchun TP/SL qo'yilmaydi (faqat BGB cheklangan)
SKIP_TP_SL_SYMBOLS = {"BGBUSDT"}


def _price_scale(price: float) -> int:
    if price >= 10000:
        return 1
    elif price >= 100:
        return 2
    elif price >= 1:
        return 4
    elif price >= 0.1:
        return 5
    elif price >= 0.01:
        return 6
    return 8


def _place_tp_sl_with_retry(client, symbol, plan_type, trig, hold_side, sz):
    """TP/SL qo'y — checkScale xatosida avtomatik retry."""
    r = client.place_futures_tp_sl(
        symbol=symbol, plan_type=plan_type,
        trigger_price=str(trig), side=hold_side, size=str(sz)
    )
    if r.get("code") == "00000":
        return True, trig
    msg = r.get("msg", "")
    m = re.search(r"checkScale=(\d+)", msg)
    if m:
        correct_scale = int(m.group(1))
        trig_fixed = round(trig, correct_scale)
        r2 = client.place_futures_tp_sl(
            symbol=symbol, plan_type=plan_type,
            trigger_price=str(trig_fixed), side=hold_side, size=str(sz)
        )
        if r2.get("code") == "00000":
            return True, trig_fixed
        logger.warning(f"⚠️ {symbol} {plan_type} retry xato: {r2.get('msg')}")
        return False, trig_fixed
    logger.warning(f"⚠️ {symbol} {plan_type} xato: {msg}")
    return False, trig


class TradingEngine:
    def __init__(self, client: BitgetClient, bot=None):
        self.client = client
        self.bot    = bot
        self.active = True
        self.scan_interval = 300
        self.active_futures_signals: Dict = {}

    async def _futures_balance(self) -> float:
        """Cross margin uchun haqiqiy yangi pozitsiya uchun mavjud mablag'.
        crossedMaxAvailable = Bitget'ning HAQIQIY ruxsat beradigan limiti.
        0 = yangi pozitsiya uchun joy yo'q (mavjud pozitsiyalar zarar ko'rmoqda).
        """
        try:
            d = self.client.get_futures_account()
            if d.get("code") == "00000":
                data = d["data"]
                # -1 = maydon mavjud emas (eski API), >= 0 = haqiqiy qiymat
                crossed_max = safe_float(data.get("crossedMaxAvailable", -1))
                available   = safe_float(data.get("available", 0))
                if crossed_max >= 0:
                    # 0 ham qaytaramiz — bu "yangi pozitsiya ochib bo'lmaydi" degan ma'no
                    return crossed_max
                # Maydon mavjud emas — available orqali fallback
                return available
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return 0.0

    async def _futures_balance_info(self) -> dict:
        """To'liq balans ma'lumoti — xabar ko'rsatish uchun."""
        try:
            d = self.client.get_futures_account()
            if d.get("code") == "00000":
                data = d["data"]
                return {
                    "available":       safe_float(data.get("available", 0)),
                    "crossed_max":     safe_float(data.get("crossedMaxAvailable", 0)),
                    "equity":          safe_float(data.get("accountEquity", 0)),
                    "unrealized_pl":   safe_float(data.get("unrealizedPL", 0)),
                    "crossed_risk":    safe_float(data.get("crossedRiskRate", 0)),
                    "crossed_margin":  safe_float(data.get("crossedMargin", 0)),
                }
        except Exception:
            pass
        return {}

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

    async def _set_and_confirm_leverage(self, symbol: str, target_lev: int) -> int:
        """Leverage o'rnatib, haqiqiy qiymatini tasdiqlaydi. Cross margin uchun to'g'ri ishlaydi."""
        # 1. Margin mode = cross
        try:
            self.client.set_margin_mode(symbol, "crossed")
        except Exception:
            pass

        # 2. Cross margin: holdSide-siz (Bitget cross uchun to'g'ri yo'l)
        r = self.client.set_leverage_cross(symbol, target_lev)
        if r.get("code") == "00000":
            logger.info(f"✅ Leverage cross set: {symbol} {target_lev}x")
        else:
            # 3. Fallback: holdSide bilan (isolated uslubida)
            r1 = self.client.set_leverage(symbol, target_lev, hold_side="long")
            r2 = self.client.set_leverage(symbol, target_lev, hold_side="short")
            logger.info(f"Leverage holdSide: {symbol} long={r1.get('code')} short={r2.get('code')}")

        # 4. Tasdiqlash — haqiqiy leverage'ni o'qiymiz
        try:
            sym_acc = self.client.get_futures_symbol_account(symbol)
            if sym_acc.get("code") == "00000":
                confirmed = int(safe_float(sym_acc["data"].get("leverage", target_lev)))
                if confirmed > 0:
                    logger.info(f"✅ Confirmed leverage {symbol}: {confirmed}x")
                    return confirmed
        except Exception as e:
            logger.warning(f"Leverage confirm error {symbol}: {e}")

        return target_lev  # tasdiqlash muvaffaqiyatsiz bo'lsa, target'ni ishlatamiz

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
        """Balansnin trade_balance_pct foizini ishlatamiz."""
        pct = gs.trade_balance_pct / 100.0
        raw = balance * pct
        return max(MIN_ORDER_USDT, min(MAX_ORDER_USDT, raw))

    async def run_futures_scanner(self):
        while self.active:
            try:
                await self._scan_futures()
            except Exception as e:
                logger.error(f"Scanner error: {e}")
                gs.scanner.add_log(f"❌ Xato: {str(e)[:50]}")
            await asyncio.sleep(self.scan_interval)

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

        gs.scanner.add_log(f"💼 {balance:.2f}$ | Order: {order_usdt:.2f}$ ({gs.trade_balance_pct}%) | Ochiq: {open_count}")

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

                # 60%+ signallar tarixga saqlanadi
                if conf >= MIN_SIGNAL_CONFIDENCE:
                    gs.signal_history.add(sig)
                    gs.scanner.signals_this_scan += 1

                # 70%+ — faqat avtosavdo (signal xabarlari BLOK)
                if conf >= SIGNAL_NOTIFY_THRESHOLD:
                    if (gs.auto_trade_enabled and
                            gs.top_signals_enabled and
                            open_count < gs.MAX_AUTO_POSITIONS and
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

    async def _place_futures_trade(self, signal: Dict, order_usdt: float, candles_data: list):
        symbol = signal["symbol"]
        dir_   = signal["direction"]
        entry  = signal["entry"]
        atr    = signal["atr"]
        max_lev = await self._get_max_leverage(symbol)
        confirmed_lev = await self._set_and_confirm_leverage(symbol, max_lev)

        commission = 0.0006 * 2   # taker fee × 2 (ochish + yopish), leverage QUSHILMAYDI
        atr_r = atr / entry
        if dir_ == "LONG":
            final_tp1 = round(entry * (1 + atr_r * 1.5 - commission), 8)
            final_sl  = round(entry * (1 - atr_r * 1.5 - commission), 8)
            side = "buy"; hold_side = "long"
        else:
            final_tp1 = round(entry * (1 - atr_r * 1.5 + commission), 8)
            final_sl  = round(entry * (1 + atr_r * 1.5 + commission), 8)
            side = "sell"; hold_side = "short"

        # Sanity-check: SHORT uchun TP entry dan past, SL yuqori bo'lishi shart
        if dir_ == "SHORT":
            if final_tp1 >= entry:
                final_tp1 = round(entry * (1 - atr_r * 1.5), 8)
            if final_sl <= entry:
                final_sl  = round(entry * (1 + atr_r * 1.5), 8)
        else:
            if final_tp1 <= entry:
                final_tp1 = round(entry * (1 + atr_r * 1.5), 8)
            if final_sl >= entry:
                final_sl  = round(entry * (1 - atr_r * 1.5), 8)

        size = order_usdt * confirmed_lev / entry
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
        logger.info(f"✅ Order: {symbol} {dir_} {size} @ {confirmed_lev}x")
        gs.scanner.add_log(f"✅ Savdo: {symbol} {dir_} {confirmed_lev}x")

        self.active_futures_signals[symbol] = {
            "signal": signal, "order_id": order_id, "leverage": confirmed_lev,
            "size": size, "margin": order_usdt, "open_time": int(time.time())
        }
        gs.scanner.active_trades[symbol] = {
            "symbol": symbol, "direction": dir_, "leverage": confirmed_lev,
            "size": size, "margin": order_usdt, "entry": entry,
            "open_time_str": __import__("datetime").datetime.utcnow().strftime("%H:%M")
        }

        # TP qo'y — muvaffaqiyatsiz bo'lsa pozitsiyani yop
        tp_ok, _ = _place_tp_sl_with_retry(self.client, symbol, "pos_profit", final_tp1, hold_side, size)
        if not tp_ok:
            logger.error(f"❌ {symbol} TP qo'yilmadi — pozitsiya YOPILMOQDA")
            gs.scanner.add_log(f"❌ {symbol} TP fail → rollback")
            self.client.close_futures_position(symbol, hold_side)
            self.active_futures_signals.pop(symbol, None)
            gs.scanner.active_trades.pop(symbol, None)
            return

        # SL qo'y — muvaffaqiyatsiz bo'lsa TP ni bekor qil va pozitsiyani yop
        sl_ok, _ = _place_tp_sl_with_retry(self.client, symbol, "pos_loss", final_sl, hold_side, size)
        if not sl_ok:
            logger.error(f"❌ {symbol} SL qo'yilmadi — pozitsiya YOPILMOQDA")
            gs.scanner.add_log(f"❌ {symbol} SL fail → rollback")
            self.client.close_futures_position(symbol, hold_side)
            self.active_futures_signals.pop(symbol, None)
            gs.scanner.active_trades.pop(symbol, None)
            return

        logger.info(f"✅ {symbol} TP={final_tp1} SL={final_sl} qo'yildi")

        if self.bot and gs.notifier_chat_id:
            from utils.formatters import format_auto_trade_notify
            text = format_auto_trade_notify(
                signal=signal, leverage=max_lev, size=size,
                margin=order_usdt, tp1=final_tp1, sl=final_sl,
                order_id=order_id
            )
            try:
                from services.chart_generator import generate_position_chart
                buf = generate_position_chart(
                    candles_data=candles_data,
                    symbol=symbol, direction=dir_,
                    entry=entry, mark_price=entry,
                    tp_levels=[final_tp1],
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

    async def place_manual_trade(self, symbol: str, signal: Dict, order_usdt: float):
        """Manual 'Savdoga kirish' tugmasi."""
        dir_   = signal["direction"]
        entry  = signal["entry"]
        atr    = signal.get("atr", entry * 0.02)

        if entry <= 0:
            return None, "Kirish narxi noto'g'ri (0)"

        # ── Haqiqiy balansni ol (crossedMaxAvailable) ──────────
        bal_info = await self._futures_balance_info()
        balance  = await self._futures_balance()
        if balance <= 0.5:
            crossed_max = bal_info.get("crossed_max", 0)
            equity      = bal_info.get("equity", 0)
            unr_pl      = bal_info.get("unrealized_pl", 0)
            risk        = bal_info.get("crossed_risk", 0) * 100
            return None, (
                f"⚠️ <b>Yangi pozitsiya uchun mablag' yo'q</b>\n\n"
                f"📊 <b>Holat:</b>\n"
                f"• Hisob kapitali: <b>{equity:.2f} USDT</b>\n"
                f"• Unrealized PnL: <b>{unr_pl:+.2f} USDT</b>\n"
                f"• Risk darajasi: <b>{risk:.1f}%</b>\n"
                f"• Yangi pozitsiya limiti: <b>{crossed_max:.2f} USDT</b>\n\n"
                f"💡 <b>Sabab:</b> Mavjud pozitsiyalar zarar ko'rmoqda.\n"
                f"Yangi pozitsiya ochish uchun:\n"
                f"• Ba'zi ochiq pozitsiyalarni yoping\n"
                f"• Yoki hisobga USDT qo'shing"
            )

        max_lev = await self._get_max_leverage(symbol)
        # Leverage o'rnat va haqiqiy qiymatni tasdiqla (cross margin uchun to'g'ri yo'l)
        confirmed_lev = await self._set_and_confirm_leverage(symbol, max_lev)

        commission = 0.0006 * 2
        atr_r = atr / entry if entry > 0 else 0.02
        if dir_ == "LONG":
            final_tp1 = round(entry * (1 + atr_r * 1.5 - commission), 8)
            final_sl  = round(entry * (1 - atr_r * 1.5 - commission), 8)
            side = "buy"; hold_side = "long"
        else:
            final_tp1 = round(entry * (1 - atr_r * 1.5 + commission), 8)
            final_sl  = round(entry * (1 + atr_r * 1.5 + commission), 8)
            side = "sell"; hold_side = "short"

        if dir_ == "SHORT":
            if final_tp1 >= entry:
                final_tp1 = round(entry * (1 - atr_r * 1.5), 8)
            if final_sl <= entry:
                final_sl  = round(entry * (1 + atr_r * 1.5), 8)
        else:
            if final_tp1 <= entry:
                final_tp1 = round(entry * (1 + atr_r * 1.5), 8)
            if final_sl >= entry:
                final_sl  = round(entry * (1 - atr_r * 1.5), 8)

        # ── Zocker TP/SL dan foydalanish (agar mavjud bo'lsa) ──
        if signal.get("tp1") and signal.get("sl"):
            ztp = signal["tp1"]; zsl = signal["sl"]
            if dir_ == "LONG" and ztp > entry > zsl > 0:
                final_tp1, final_sl = ztp, zsl
            elif dir_ == "SHORT" and ztp < entry and zsl > entry:
                final_tp1, final_sl = ztp, zsl

        # ── Kontrakt ma'lumotlarini ol ───────────────────────
        import math
        min_size = 0.001
        prec     = 4
        try:
            d = self.client.get_futures_contract_info(symbol)
            if d.get("code") == "00000":
                contracts = d.get("data", [])
                if contracts:
                    c        = contracts[0]
                    min_size = safe_float(c.get("minTradeNum", 0.001))
                    sz_str   = str(min_size)
                    prec     = len(sz_str.split(".")[-1]) if "." in sz_str else 0
        except Exception:
            pass

        # ── Minimal marja tekshiruvi (confirmed_lev bilan) ─────────────
        min_margin_needed = min_size * entry / confirmed_lev
        if order_usdt < min_margin_needed * 0.99:
            return None, (
                f"⚠️ <b>{symbol}</b> uchun minimal savdo:\n"
                f"• 1 kontrakt = <b>{min_margin_needed:.4f} USDT</b> marja ({confirmed_lev}x leverage)\n"
                f"• Siz kiritdingiz: <b>{order_usdt:.2f} USDT</b>\n\n"
                f"Kamida <b>{math.ceil(min_margin_needed)}</b> USDT kiriting."
            )

        # ── Hajm hisoblash — confirmed_lev ishlatamiz ───────────────────
        raw_size  = order_usdt * confirmed_lev / entry
        lots      = max(1, math.floor(raw_size / min_size))
        size      = lots * min_size

        # ── Balans tekshiruvi ───────────────────────────────────────────
        actual_margin = size * entry / confirmed_lev
        if actual_margin > balance * 0.90:
            lots = max(1, math.floor(balance * 0.85 * confirmed_lev / entry / min_size))
            size = lots * min_size
            actual_margin = size * entry / confirmed_lev
            if actual_margin > balance * 0.90:
                return None, (
                    f"⚠️ Balans yetarli emas.\n"
                    f"• Kerakli marja: <b>{actual_margin:.2f} USDT</b>\n"
                    f"• Mavjud balans: <b>{balance:.2f} USDT</b>\n\n"
                    f"Kamida <b>{math.ceil(min_margin_needed)}</b> USDT kerak."
                )
            logger.info(f"Manual trade: lots kamaytirildi → {lots} ({actual_margin:.2f} USDT)")

        if size <= 0:
            return None, "Hajm 0 dan kichik"

        logger.info(f"Manual trade: {symbol} {dir_} size={size} lev={confirmed_lev}x margin={actual_margin:.2f} balance={balance:.2f}")

        result = self.client.place_futures_order(
            symbol=symbol, side=side, trade_side="open",
            size=str(size), order_type="market"
        )
        if result.get("code") != "00000":
            err_msg = result.get("msg", "Order xatosi")
            err_lower = err_msg.lower()
            # crossedMaxAvailable=0 yoki "exceeds balance" xatosi
            if "balance" in err_lower or "exceed" in err_lower or "40762" in str(result.get("code", "")):
                bal_info2 = await self._futures_balance_info()
                crossed   = bal_info2.get("crossed_max", 0)
                equity2   = bal_info2.get("equity", 0)
                unr2      = bal_info2.get("unrealized_pl", 0)
                risk2     = bal_info2.get("crossed_risk", 0) * 100
                return None, (
                    f"❌ <b>Order rad etildi (Bitget)</b>\n\n"
                    f"📊 <b>Hisob holati:</b>\n"
                    f"• Kapital: <b>{equity2:.2f} USDT</b>\n"
                    f"• Unrealized PnL: <b>{unr2:+.2f} USDT</b>\n"
                    f"• Risk darajasi: <b>{risk2:.1f}%</b>\n"
                    f"• Yangi pozitsiya limiti (crossedMaxAvailable): <b>{crossed:.2f} USDT</b>\n\n"
                    f"💡 <b>Sabab:</b> Mavjud ochiq pozitsiyalar zarar ko'rmoqda,\n"
                    f"Bitget cross margin yangi pozitsiya ochishga ruxsat bermayapti.\n\n"
                    f"<b>Yechim:</b>\n"
                    f"• Zarar ko'rayotgan pozitsiyalarni yoping\n"
                    f"• Yoki hisobga ko'proq USDT qo'shing"
                )
            return None, f"❌ {err_msg}"

        order_id = result.get("data", {}).get("orderId", "")
        logger.info(f"✅ Manual order: {symbol} {dir_} {size} @ {confirmed_lev}x — TP/SL qo'yilmoqda...")

        # TP va SL MAJBURIY — muvaffaqiyatsiz bo'lsa pozitsiyani darhol yop
        if symbol not in SKIP_TP_SL_SYMBOLS:
            tp_ok, _ = _place_tp_sl_with_retry(self.client, symbol, "pos_profit", final_tp1, hold_side, size)
            if not tp_ok:
                logger.error(f"❌ Manual {symbol} TP qo'yilmadi — ROLLBACK")
                self.client.close_futures_position(symbol, hold_side)
                return None, (
                    f"❌ <b>TP qo'yilmadi — pozitsiya BEKOR QILINDI</b>\n\n"
                    f"• {symbol} {dir_} pozitsiyasi avtomatik yopildi\n"
                    f"• Sabab: TP order Bitget tomonidan rad etildi\n"
                    f"• Keyinroq qayta urining"
                )

            sl_ok, _ = _place_tp_sl_with_retry(self.client, symbol, "pos_loss", final_sl, hold_side, size)
            if not sl_ok:
                logger.error(f"❌ Manual {symbol} SL qo'yilmadi — ROLLBACK")
                self.client.close_futures_position(symbol, hold_side)
                return None, (
                    f"❌ <b>SL qo'yilmadi — pozitsiya BEKOR QILINDI</b>\n\n"
                    f"• {symbol} {dir_} pozitsiyasi avtomatik yopildi\n"
                    f"• Sabab: SL order Bitget tomonidan rad etildi\n"
                    f"• Keyinroq qayta urining"
                )

            logger.info(f"✅ Manual {symbol} TP={final_tp1} SL={final_sl} — muvaffaqiyatli")

        trade_info = {
            "symbol": symbol, "direction": dir_,
            "leverage": max_lev, "size": size, "margin": order_usdt,
            "entry": entry, "tp1": final_tp1, "sl": final_sl,
            "order_id": order_id
        }
        gs.scanner.active_trades[symbol] = {
            **trade_info,
            "open_time_str": __import__("datetime").datetime.utcnow().strftime("%H:%M")
        }
        return trade_info, None

    async def set_tp_sl_for_existing_positions(self):
        """Mavjud ochiq pozitsiyalarga TP/SL qo'y (PAXG/XAUT/BGB bundan mustasno)."""
        try:
            pos_d = self.client.get_futures_positions()
            if pos_d.get("code") != "00000":
                logger.warning("Pozitsiyalar olinmadi")
                return

            positions = [p for p in pos_d.get("data", []) if safe_float(p.get("total", 0)) > 0]
            if not positions:
                logger.info("Ochiq pozitsiyalar yo'q")
                return

            plan_d = self.client.get_futures_plan_orders()
            symbols_with_tpsl = set()
            if plan_d.get("code") == "00000":
                plan_list = plan_d.get("data") or []
                if isinstance(plan_list, dict):
                    plan_list = plan_list.get("entrustedList", [])
                for pl in (plan_list if isinstance(plan_list, list) else []):
                    symbols_with_tpsl.add(pl.get("symbol", ""))

            set_count = 0
            for pos in positions:
                symbol    = pos.get("symbol", "")
                hold_side = pos.get("holdSide", "")
                size      = safe_float(pos.get("total", 0))
                avg_price = safe_float(pos.get("openPriceAvg", 0))

                if symbol in SKIP_TP_SL_SYMBOLS:
                    logger.info(f"⏭️ {symbol} skip (PAXG/XAUT/BGB)")
                    continue

                if symbol in symbols_with_tpsl:
                    logger.info(f"✅ {symbol} — TP/SL allaqachon mavjud")
                    continue

                if avg_price <= 0 or size <= 0:
                    continue

                direction = "LONG" if hold_side == "long" else "SHORT"
                logger.info(f"🎯 {symbol} {direction} uchun TP/SL qo'yilmoqda...")

                try:
                    candles = self.client.get_futures_candles(symbol, "1H", 150)
                    if candles.get("code") != "00000":
                        logger.warning(f"Candles olinmadi {symbol}: {candles.get('msg')}")
                        continue

                    raw = candles.get("data", [])
                    sig = analyze_symbol(raw, symbol, "1H")

                    if sig:
                        atr = sig["atr"]
                    else:
                        closes = [safe_float(c[4]) for c in raw if len(c) > 4]
                        highs  = [safe_float(c[2]) for c in raw if len(c) > 2]
                        lows   = [safe_float(c[3]) for c in raw if len(c) > 3]
                        if len(closes) >= 14:
                            from services.analyzer import compute_atr
                            import numpy as np
                            atr = compute_atr(
                                np.array(highs),
                                np.array(lows),
                                np.array(closes), 14
                            )
                        else:
                            atr = avg_price * 0.02

                    atr_r = atr / avg_price
                    commission = 0.0006 * 2  # taker fee × 2, leverage QUSHILMAYDI
                    price_scale = _price_scale(avg_price)
                    if direction == "LONG":
                        tp1 = round(avg_price * (1 + atr_r * 1.5 - commission), price_scale)
                        sl  = round(avg_price * (1 - atr_r * 1.5 - commission), price_scale)
                        if tp1 <= avg_price: tp1 = round(avg_price * (1 + atr_r * 1.5), price_scale)
                        if sl  >= avg_price: sl  = round(avg_price * (1 - atr_r * 1.5), price_scale)
                    else:
                        tp1 = round(avg_price * (1 - atr_r * 1.5 + commission), price_scale)
                        sl  = round(avg_price * (1 + atr_r * 1.5 + commission), price_scale)
                        if tp1 >= avg_price: tp1 = round(avg_price * (1 - atr_r * 1.5), price_scale)
                        if sl  <= avg_price: sl  = round(avg_price * (1 + atr_r * 1.5), price_scale)

                    # TP1 = 100%, SL = 100%
                    success = True
                    for plan_type, trig, sz in [
                        ("pos_profit", tp1, size),
                        ("pos_loss",   sl,  size),
                    ]:
                        ok, _ = _place_tp_sl_with_retry(self.client, symbol, plan_type, trig, hold_side, sz)
                        if ok:
                            logger.info(f"✅ {symbol} {plan_type}: {trig}")
                        else:
                            success = False

                    if success:
                        set_count += 1
                        gs.scanner.add_log(f"🎯 {symbol} TP/SL qo'yildi")

                    if self.bot and gs.notifier_chat_id:
                        dir_e = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
                        status = "✅ Muvaffaqiyatli" if success else "⚠️ Qisman"
                        text = (
                            f"🎯 <b>TP/SL QUYILDI</b> {status}\n"
                            f"{'─'*24}\n"
                            f"💎 <b>{symbol}</b> — {dir_e}\n"
                            f"💲 Kirish narxi: <code>${avg_price}</code>\n"
                            f"{'─'*24}\n"
                            f"💚 TP: <code>${tp1}</code>\n"
                            f"🛑 SL: <code>${sl}</code>"
                        )
                        try:
                            await self.bot.send_message(
                                chat_id=gs.notifier_chat_id, text=text, parse_mode="HTML"
                            )
                        except Exception:
                            pass

                except Exception as e:
                    logger.error(f"set_tp_sl {symbol}: {e}")

                await asyncio.sleep(0.5)

            logger.info(f"🎯 TP/SL qo'yildi: {set_count} ta pozitsiya")

        except Exception as e:
            logger.error(f"set_tp_sl_for_existing: {e}")

    async def get_top_signals(self, n: int = 10, min_conf: int = 55) -> List[Dict]:
        """Top N signal olish."""
        symbols = await self._top_futures_symbols(30)
        results = []
        for symbol in symbols:
            try:
                candles = self.client.get_futures_candles(symbol, "1H", 200)
                if candles.get("code") != "00000":
                    continue
                raw = candles.get("data", [])
                sig = analyze_symbol(raw, symbol, "1H")
                if sig and sig["confidence"] >= min_conf:
                    results.append(sig)
                await asyncio.sleep(0.2)
            except Exception:
                pass
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:n]

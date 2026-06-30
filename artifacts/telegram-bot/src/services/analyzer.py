import numpy as np
from typing import Optional, Tuple, List, Dict


def safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return default


def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_macd(closes: np.ndarray, fast=12, slow=26, signal=9) -> Tuple[float, float, float]:
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0

    def ema(data, span):
        k = 2.0 / (span + 1)
        e = data[0]
        result = [e]
        for v in data[1:]:
            e = v * k + e * (1 - k)
            result.append(e)
        return np.array(result)

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line[-1], signal_line[-1], histogram[-1]


def compute_ema(closes: np.ndarray, period: int) -> float:
    if len(closes) < period:
        return closes[-1] if len(closes) > 0 else 0.0
    k = 2.0 / (period + 1)
    e = closes[0]
    for v in closes[1:]:
        e = v * k + e * (1 - k)
    return e


def compute_ema_series(closes: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    result = np.zeros(len(closes))
    result[0] = closes[0]
    for i in range(1, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(highs) < period + 1:
        return (highs[-1] - lows[-1]) if len(highs) > 0 else 0.0
    tr_list = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    return float(np.mean(tr_list[-period:]))


def compute_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(highs) < period * 2:
        return 20.0
    plus_dm_list, minus_dm_list, tr_list = [], [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm_list.append(up if up > down and up > 0 else 0.0)
        minus_dm_list.append(down if down > up and down > 0 else 0.0)
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    atr_s = float(np.mean(tr_list[:period]))
    pdm_s = float(np.mean(plus_dm_list[:period]))
    mdm_s = float(np.mean(minus_dm_list[:period]))
    dx_list = []
    for i in range(period, len(tr_list)):
        atr_s = atr_s - atr_s / period + tr_list[i]
        pdm_s = pdm_s - pdm_s / period + plus_dm_list[i]
        mdm_s = mdm_s - mdm_s / period + minus_dm_list[i]
        pdi = 100 * pdm_s / atr_s if atr_s else 0
        mdi = 100 * mdm_s / atr_s if atr_s else 0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0
        dx_list.append(dx)
    return float(np.mean(dx_list[-period:])) if dx_list else 20.0


def compute_supertrend(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                        period: int = 10, multiplier: float = 3.0) -> Tuple[float, int]:
    if len(closes) < period + 5:
        return closes[-1], 1
    atr = compute_atr(highs, lows, closes, period)
    hl2 = (highs[-1] + lows[-1]) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    trend = 1 if closes[-1] > basic_lower else -1
    return (basic_lower if trend == 1 else basic_upper), trend


def compute_bollinger(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
    if len(closes) < period:
        c = closes[-1]
        return c, c, c
    recent = closes[-period:]
    mid = float(np.mean(recent))
    std = float(np.std(recent))
    return mid + std_dev * std, mid, mid - std_dev * std


def compute_stochastic(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> Tuple[float, float]:
    if len(closes) < period:
        return 50.0, 50.0
    recent_high = float(np.max(highs[-period:]))
    recent_low = float(np.min(lows[-period:]))
    if recent_high == recent_low:
        return 50.0, 50.0
    k = 100 * (closes[-1] - recent_low) / (recent_high - recent_low)
    d = k
    if len(closes) >= period + 2:
        k2 = 100 * (closes[-2] - float(np.min(lows[-period - 1:-1]))) / (float(np.max(highs[-period - 1:-1])) - float(np.min(lows[-period - 1:-1])) + 1e-9)
        k3 = 100 * (closes[-3] - float(np.min(lows[-period - 2:-2]))) / (float(np.max(highs[-period - 2:-2])) - float(np.min(lows[-period - 2:-2])) + 1e-9)
        d = (k + k2 + k3) / 3
    return k, d


def compute_volume_trend(volumes: np.ndarray, period: int = 20) -> float:
    if len(volumes) < period:
        return 1.0
    avg_vol = float(np.mean(volumes[-period:]))
    return volumes[-1] / avg_vol if avg_vol > 0 else 1.0


def compute_support_resistance(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> Tuple[float, float]:
    if len(closes) < 20:
        return closes[-1] * 0.95, closes[-1] * 1.05
    recent_lows = lows[-20:]
    recent_highs = highs[-20:]
    support = float(np.percentile(recent_lows, 10))
    resistance = float(np.percentile(recent_highs, 90))
    return support, resistance


def detect_smc(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Dict:
    if len(closes) < 20:
        return {"bos_bullish": False, "bos_bearish": False, "choch": False, "ob_bullish": False, "ob_bearish": False}
    last_20_high = float(np.max(highs[-20:]))
    last_20_low = float(np.min(lows[-20:]))
    prev_high = float(np.max(highs[-40:-20])) if len(highs) >= 40 else float(highs[0])
    prev_low = float(np.min(lows[-40:-20])) if len(lows) >= 40 else float(lows[0])
    bos_bullish = closes[-1] > last_20_high and closes[-5] < last_20_high
    bos_bearish = closes[-1] < last_20_low and closes[-5] > last_20_low
    choch = (closes[-1] > prev_high and closes[-3] < prev_high) or (closes[-1] < prev_low and closes[-3] > prev_low)
    diffs = np.abs(np.diff(closes[-10:]))
    avg_body = float(np.mean(diffs)) if len(diffs) > 0 else 0
    recent_body = abs(closes[-3] - closes[-4])
    ob_bullish = closes[-3] < closes[-4] and recent_body > avg_body * 1.5
    ob_bearish = closes[-3] > closes[-4] and recent_body > avg_body * 1.5
    return {
        "bos_bullish": bos_bullish,
        "bos_bearish": bos_bearish,
        "choch": choch,
        "ob_bullish": ob_bullish,
        "ob_bearish": ob_bearish,
    }


def detect_price_action(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Dict:
    if len(closes) < 5:
        return {"pattern": "none", "bullish": False, "bearish": False}
    bullish_engulf = (closes[-1] > closes[-2] and
                      closes[-1] > highs[-2] and
                      closes[-2] < lows[-3] if len(closes) > 3 else False)
    bearish_engulf = (closes[-1] < closes[-2] and
                      closes[-1] < lows[-2] and
                      closes[-2] > highs[-3] if len(closes) > 3 else False)
    body = abs(closes[-1] - closes[-2])
    upper_wick = highs[-1] - max(closes[-1], closes[-2])
    lower_wick = min(closes[-1], closes[-2]) - lows[-1]
    hammer = lower_wick > body * 2 and upper_wick < body * 0.5
    shooting_star = upper_wick > body * 2 and lower_wick < body * 0.5
    return {
        "bullish_engulf": bullish_engulf,
        "bearish_engulf": bearish_engulf,
        "hammer": hammer,
        "shooting_star": shooting_star,
    }


def compute_trend_strength(closes: np.ndarray) -> Tuple[str, float]:
    if len(closes) < 50:
        return "sideways", 0.5
    ema20 = compute_ema(closes, 20)
    ema50 = compute_ema(closes, 50)
    price = closes[-1]
    if price > ema20 > ema50:
        pct = (price - ema50) / ema50 * 100
        return "up", min(pct, 10.0)
    elif price < ema20 < ema50:
        pct = (ema50 - price) / ema50 * 100
        return "down", min(pct, 10.0)
    return "sideways", 0.0


def estimate_trade_duration(timeframe: str, confidence: int = 70) -> str:
    tf_to_hours = {
        "1M": 0.017, "3M": 0.05, "5M": 0.083, "15M": 0.25, "30M": 0.5,
        "1H": 1, "2H": 2, "4H": 4, "6H": 6, "12H": 12,
        "1D": 24, "3D": 72, "1W": 168
    }
    base_h = tf_to_hours.get(timeframe.upper(), 1)
    multiplier = 2 if confidence >= 85 else (3 if confidence >= 75 else 4)
    hours = base_h * multiplier
    if hours < 1:
        mins = int(hours * 60)
        return f"~{mins} daqiqa"
    elif hours < 24:
        return f"~{int(hours)} soat"
    elif hours < 48:
        return f"~{hours/24:.1f} kun"
    else:
        return f"~{int(hours/24)} kun"


def analyze_symbol(candles_data: list, symbol: str, timeframe: str = "1H") -> Optional[Dict]:
    """
    Full multi-indicator analysis with trend-break filter.
    Kuchli filter: trend buzilsa BUY signal berilmaydi.
    """
    if not candles_data or len(candles_data) < 50:
        return None
    try:
        opens  = np.array([safe_float(c[1]) for c in candles_data])
        highs  = np.array([safe_float(c[2]) for c in candles_data])
        lows   = np.array([safe_float(c[3]) for c in candles_data])
        closes = np.array([safe_float(c[4]) for c in candles_data])
        volumes= np.array([safe_float(c[5]) for c in candles_data])
    except Exception:
        return None

    if len(closes) < 50 or closes[-1] == 0:
        return None

    rsi = compute_rsi(closes, 14)
    macd_line, sig_line, histogram = compute_macd(closes)
    ema9  = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)
    ema50 = compute_ema(closes, 50)
    ema200= compute_ema(closes, 200) if len(closes) >= 200 else ema50
    atr   = compute_atr(highs, lows, closes, 14)
    adx   = compute_adx(highs, lows, closes, 14)
    st_level, st_trend = compute_supertrend(highs, lows, closes, 10, 3.0)
    bb_upper, bb_mid, bb_lower = compute_bollinger(closes, 20, 2.0)
    vol_ratio = compute_volume_trend(volumes, 20)
    stoch_k, stoch_d = compute_stochastic(highs, lows, closes, 14)
    smc = detect_smc(closes, highs, lows)
    pa  = detect_price_action(closes, highs, lows)
    trend_dir, trend_strength = compute_trend_strength(closes)
    support, resistance = compute_support_resistance(highs, lows, closes)

    current = closes[-1]
    prev    = closes[-2] if len(closes) > 1 else current
    change_pct = (current - prev) / prev * 100 if prev > 0 else 0.0

    # ── Sham rangi va trend filtrlari ─────────────────────
    last_candle_bearish = closes[-1] < opens[-1] * 0.9998  # Qizil sham
    last_candle_bullish = closes[-1] > opens[-1] * 1.0002  # Yashil sham

    # So'nggi 3 ta sham ketma-ket pasayish (closes[-1] < closes[-2] < closes[-3])
    three_bear = (len(closes) >= 4 and
                  closes[-1] < closes[-2] and closes[-2] < closes[-3])
    # So'nggi 3 ta sham ketma-ket o'sish
    three_bull = (len(closes) >= 4 and
                  closes[-1] > closes[-2] and closes[-2] > closes[-3])

    # EMA50 trend buzilishi: AVVALDA yuqorida, HOZIR pastda → pastga buzildi
    trend_break_down = (len(closes) >= 3 and
                        closes[-1] < ema50 and
                        (closes[-2] >= ema50 or closes[-3] >= ema50))
    # EMA50 trend buzilishi: AVVALDA pastda, HOZIR yuqorida → yuqoriga buzildi
    trend_break_up   = (len(closes) >= 3 and
                        closes[-1] > ema50 and
                        (closes[-2] <= ema50 or closes[-3] <= ema50))

    # So'nggi 5 shamdan 4+ si qizil mi?
    if len(closes) >= 6:
        last5_colors = [1 if closes[i] > opens[i] else -1 for i in range(-5, 0)]
        bearish_dominant = last5_colors.count(-1) >= 4
        bullish_dominant = last5_colors.count(1) >= 4
    else:
        bearish_dominant = False
        bullish_dominant = False

    # ── Scoring ───────────────────────────────────────────
    score_long = 0
    score_short = 0
    reasons_long = []
    reasons_short = []
    max_score = 130

    # RSI (max 18)
    if rsi < 30:
        score_long += 18; reasons_long.append(f"RSI={rsi:.0f} oversold")
    elif rsi < 40:
        score_long += 12; reasons_long.append(f"RSI={rsi:.0f} past zona")
    elif rsi < 50:
        score_long += 6
    elif rsi > 70:
        score_short += 18; reasons_short.append(f"RSI={rsi:.0f} overbought")
    elif rsi > 60:
        score_short += 12; reasons_short.append(f"RSI={rsi:.0f} yuqori zona")
    elif rsi > 55:
        score_short += 6

    # MACD (max 15)
    if histogram > 0 and macd_line > sig_line:
        score_long += 15; reasons_long.append("MACD o'sish kesishdi")
    elif histogram < 0 and macd_line < sig_line:
        score_short += 15; reasons_short.append("MACD pasayish kesishdi")
    elif histogram > 0:
        score_long += 6
    elif histogram < 0:
        score_short += 6

    # EMA alignment (max 14)
    if ema9 > ema21 > ema50:
        score_long += 14; reasons_long.append("EMA o'sish joylashishi")
    elif ema9 < ema21 < ema50:
        score_short += 14; reasons_short.append("EMA pasayish joylashishi")
    elif ema9 > ema21:
        score_long += 6
    elif ema9 < ema21:
        score_short += 6

    # Price vs EMA200 (max 8)
    if current > ema200:
        score_long += 8
    else:
        score_short += 8

    # ADX trend strength (max 8)
    if adx > 20:
        if score_long >= score_short:
            score_long += 8; reasons_long.append(f"ADX={adx:.0f} trend kuchli")
        else:
            score_short += 8; reasons_short.append(f"ADX={adx:.0f} trend kuchli")

    # Supertrend (max 14) — KUCHLI INDIKATOR: qarama-qarshi yo'nalishga jazo
    if st_trend == 1:
        score_long += 14; reasons_long.append("Supertrend o'sish ↑")
        score_short -= 12   # SHORT bekor qiluvchi kuch
    else:
        score_short += 14; reasons_short.append("Supertrend pasayish ↓")
        score_long -= 12    # LONG bekor qiluvchi kuch — eng muhim fix

    # Bollinger Bands (max 10)
    if current < bb_lower:
        score_long += 10; reasons_long.append("Narx BB pastidan chiqdi")
    elif current > bb_upper:
        score_short += 10; reasons_short.append("Narx BB yuqorisidan chiqdi")
    elif current < bb_mid:
        score_long += 4
    else:
        score_short += 4

    # Volume (max 8)
    if vol_ratio > 1.3:
        bonus = min(8, int(vol_ratio * 3))
        if score_long >= score_short:
            score_long += bonus; reasons_long.append(f"Hajm yuqori {vol_ratio:.1f}x")
        else:
            score_short += bonus; reasons_short.append(f"Hajm yuqori {vol_ratio:.1f}x")

    # Stochastic (max 8)
    if stoch_k < 25 and stoch_k > stoch_d:
        score_long += 8; reasons_long.append("Stoch pastdan kesishdi")
    elif stoch_k > 75 and stoch_k < stoch_d:
        score_short += 8; reasons_short.append("Stoch yuqoridan kesishdi")

    # SMC (max 10)
    if smc["bos_bullish"] or smc["ob_bullish"]:
        score_long += 10; reasons_long.append("SMC o'sish strukturasi")
    if smc["bos_bearish"] or smc["ob_bearish"]:
        score_short += 10; reasons_short.append("SMC pasayish strukturasi")

    # Price Action (max 8)
    if pa["bullish_engulf"] or pa["hammer"]:
        score_long += 8; reasons_long.append("PA: o'sish pattern")
    if pa["bearish_engulf"] or pa["shooting_star"]:
        score_short += 8; reasons_short.append("PA: pasayish pattern")

    # Trend direction (max 7)
    if trend_dir == "up":
        score_long += 7
    elif trend_dir == "down":
        score_short += 7

    # ── YANGI: Trend buzilish filtri (max ±20) ─────────────
    if trend_break_down:
        score_short += 20
        score_long  -= 18
        reasons_short.append("⚠️ EMA50 pastga tushdi — trend buzildi")
    elif trend_break_up:
        score_long  += 20
        score_short -= 18
        reasons_long.append("⚠️ EMA50 yuqoriga chiqdi — trend yuqoriga")

    # ── YANGI: Ketma-ket sham yo'nalishi (max ±10) ─────────
    if three_bear:
        score_short += 10
        score_long  -= 12
        reasons_short.append("3 ketma-ket pasayish sham")
    elif three_bull:
        score_long  += 10
        score_short -= 12
        reasons_long.append("3 ketma-ket o'sish sham")

    # ── YANGI: Dominant sham rangi (max ±8) ────────────────
    if bearish_dominant:
        score_short += 8
        score_long  -= 10
        reasons_short.append("5 ta shamdan 4+ qizil")
    elif bullish_dominant:
        score_long  += 8
        score_short -= 10
        reasons_long.append("5 ta shamdan 4+ yashil")

    # ── YANGI: So'nggi sham rangi tasdiqi (max ±6) ─────────
    if last_candle_bearish:
        score_short += 6
        score_long  -= 5
        reasons_short.append("So'nggi sham qizil yopildi")
    elif last_candle_bullish:
        score_long  += 6
        score_short -= 5
        reasons_long.append("So'nggi sham yashil yopildi")

    # ── Confidence hisoblash ───────────────────────────────
    long_conf  = min(95, max(0, int(score_long / max_score * 100)))
    short_conf = min(95, max(0, int(score_short / max_score * 100)))

    if long_conf > short_conf and long_conf >= 55:
        direction  = "LONG"
        confidence = long_conf
        reasons    = reasons_long
    elif short_conf > long_conf and short_conf >= 55:
        direction  = "SHORT"
        confidence = short_conf
        reasons    = reasons_short
    else:
        return None

    # ── ATR-based TP/SL ───────────────────────────────────
    atr_mult = 1.5
    if direction == "LONG":
        sl  = round(current - atr * atr_mult, 8)
        tp1 = round(current + atr * atr_mult, 8)
        tp2 = round(current + atr * atr_mult * 2, 8)
        entry_low  = round(current * 0.998, 8)
        entry_high = round(current * 1.002, 8)
    else:
        sl  = round(current + atr * atr_mult, 8)
        tp1 = round(current - atr * atr_mult, 8)
        tp2 = round(current - atr * atr_mult * 2, 8)
        entry_low  = round(current * 0.998, 8)
        entry_high = round(current * 1.002, 8)

    rr = abs(tp1 - current) / abs(sl - current) if abs(sl - current) > 0 else 1.0

    return {
        "symbol":         symbol,
        "direction":      direction,
        "confidence":     confidence,
        "entry":          round(current, 8),
        "entry_low":      entry_low,
        "entry_high":     entry_high,
        "tp1":            tp1,
        "tp2":            tp2,
        "sl":             sl,
        "atr":            round(atr, 8),
        "rsi":            round(rsi, 1),
        "macd":           round(macd_line, 8),
        "macd_hist":      round(histogram, 8),
        "adx":            round(adx, 1),
        "ema9":           round(ema9, 6),
        "ema21":          round(ema21, 6),
        "ema50":          round(ema50, 6),
        "supertrend":     round(st_level, 6),
        "supertrend_dir": "o'sish ↑" if st_trend == 1 else "pasayish ↓",
        "volume_ratio":   round(vol_ratio, 2),
        "stoch_k":        round(stoch_k, 1),
        "risk_reward":    round(rr, 1),
        "support":        round(support, 8),
        "resistance":     round(resistance, 8),
        "trend_dir":      trend_dir,
        "change_24h":     round(change_pct, 2),
        "reasons":        reasons,
        "timeframe":      timeframe,
    }

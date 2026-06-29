import numpy as np
import pandas as pd
from typing import Optional, Tuple, List, Dict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(highs) < period + 1:
        return (highs[-1] - lows[-1]) if len(highs) > 0 else 0.0
    tr_list = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    atr = np.mean(tr_list[-period:])
    return atr


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
    atr_smooth = np.mean(tr_list[:period])
    pdm_smooth = np.mean(plus_dm_list[:period])
    mdm_smooth = np.mean(minus_dm_list[:period])
    dx_list = []
    for i in range(period, len(tr_list)):
        atr_smooth = atr_smooth - atr_smooth / period + tr_list[i]
        pdm_smooth = pdm_smooth - pdm_smooth / period + plus_dm_list[i]
        mdm_smooth = mdm_smooth - mdm_smooth / period + minus_dm_list[i]
        pdi = 100 * pdm_smooth / atr_smooth if atr_smooth else 0
        mdi = 100 * mdm_smooth / atr_smooth if atr_smooth else 0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0
        dx_list.append(dx)
    return np.mean(dx_list[-period:]) if dx_list else 20.0


def compute_supertrend(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                        period: int = 10, multiplier: float = 3.0) -> Tuple[float, int]:
    if len(closes) < period + 5:
        return closes[-1], 1
    atr = compute_atr(highs, lows, closes, period)
    hl2 = (highs[-1] + lows[-1]) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    trend = 1 if closes[-1] > basic_lower else -1
    return basic_lower if trend == 1 else basic_upper, trend


def compute_bollinger(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
    if len(closes) < period:
        c = closes[-1]
        return c, c, c
    recent = closes[-period:]
    mid = np.mean(recent)
    std = np.std(recent)
    return mid + std_dev * std, mid, mid - std_dev * std


def compute_volume_trend(volumes: np.ndarray, period: int = 20) -> float:
    if len(volumes) < period:
        return 1.0
    avg_vol = np.mean(volumes[-period:])
    recent_vol = volumes[-1]
    return recent_vol / avg_vol if avg_vol > 0 else 1.0


def compute_stochastic(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> Tuple[float, float]:
    if len(closes) < period:
        return 50.0, 50.0
    recent_high = np.max(highs[-period:])
    recent_low = np.min(lows[-period:])
    if recent_high == recent_low:
        return 50.0, 50.0
    k = 100 * (closes[-1] - recent_low) / (recent_high - recent_low)
    if len(closes) >= period + 2:
        k2 = 100 * (closes[-2] - np.min(lows[-period - 1:-1])) / (np.max(highs[-period - 1:-1]) - np.min(lows[-period - 1:-1]) + 1e-9)
        k3 = 100 * (closes[-3] - np.min(lows[-period - 2:-2])) / (np.max(highs[-period - 2:-2]) - np.min(lows[-period - 2:-2]) + 1e-9)
        d = (k + k2 + k3) / 3
    else:
        d = k
    return k, d


def detect_smc_signals(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Dict:
    if len(closes) < 20:
        return {"bos": False, "choch": False, "ob_bullish": False, "ob_bearish": False}

    last_20_high = np.max(highs[-20:])
    last_20_low = np.min(lows[-20:])
    prev_high = np.max(highs[-40:-20]) if len(highs) >= 40 else highs[0]
    prev_low = np.min(lows[-40:-20]) if len(lows) >= 40 else lows[0]

    bos_bullish = closes[-1] > last_20_high and closes[-5] < last_20_high
    bos_bearish = closes[-1] < last_20_low and closes[-5] > last_20_low
    choch = (closes[-1] > prev_high and closes[-3] < prev_high) or \
            (closes[-1] < prev_low and closes[-3] > prev_low)

    recent_body = abs(closes[-3] - closes[-4])
    ob_bullish = closes[-3] < closes[-4] and recent_body > np.mean(np.abs(np.diff(closes[-10:]))) * 1.5
    ob_bearish = closes[-3] > closes[-4] and recent_body > np.mean(np.abs(np.diff(closes[-10:]))) * 1.5

    return {
        "bos": bos_bullish or bos_bearish,
        "bos_bullish": bos_bullish,
        "bos_bearish": bos_bearish,
        "choch": choch,
        "ob_bullish": ob_bullish,
        "ob_bearish": ob_bearish
    }


def analyze_symbol(candles_data: list, symbol: str, timeframe: str = "1H") -> Optional[Dict]:
    """
    Full multi-indicator analysis returning signal with confidence score.
    Returns dict with signal, confidence, entry, tp1, tp2, sl, and analysis details.
    """
    if not candles_data or len(candles_data) < 50:
        return None

    try:
        opens = np.array([safe_float(c[1]) for c in candles_data])
        highs = np.array([safe_float(c[2]) for c in candles_data])
        lows = np.array([safe_float(c[3]) for c in candles_data])
        closes = np.array([safe_float(c[4]) for c in candles_data])
        volumes = np.array([safe_float(c[5]) for c in candles_data])
    except Exception:
        return None

    if len(closes) < 50:
        return None

    rsi = compute_rsi(closes, 14)
    macd_line, signal_line, histogram = compute_macd(closes)
    ema_9 = compute_ema(closes, 9)
    ema_21 = compute_ema(closes, 21)
    ema_50 = compute_ema(closes, 50)
    ema_200 = compute_ema(closes, 200) if len(closes) >= 200 else ema_50
    atr = compute_atr(highs, lows, closes, 14)
    adx = compute_adx(highs, lows, closes, 14)
    st_level, st_trend = compute_supertrend(highs, lows, closes, 10, 3.0)
    bb_upper, bb_mid, bb_lower = compute_bollinger(closes, 20, 2.0)
    vol_ratio = compute_volume_trend(volumes, 20)
    stoch_k, stoch_d = compute_stochastic(highs, lows, closes, 14)
    smc = detect_smc_signals(closes, highs, lows)

    current_price = closes[-1]
    score_long = 0
    score_short = 0
    reasons_long = []
    reasons_short = []

    # RSI
    if rsi < 35:
        score_long += 15
        reasons_long.append(f"RSI={rsi:.1f} oversold")
    elif rsi < 45:
        score_long += 8
    elif rsi > 65:
        score_short += 15
        reasons_short.append(f"RSI={rsi:.1f} overbought")
    elif rsi > 55:
        score_short += 8

    # MACD
    if histogram > 0 and macd_line > signal_line:
        score_long += 12
        reasons_long.append("MACD bullish cross")
    elif histogram < 0 and macd_line < signal_line:
        score_short += 12
        reasons_short.append("MACD bearish cross")
    if histogram > 0 and histogram > abs(histogram) * 0.1:
        score_long += 5
    elif histogram < 0:
        score_short += 5

    # EMA trend
    if ema_9 > ema_21 > ema_50:
        score_long += 12
        reasons_long.append("EMA bullish alignment")
    elif ema_9 < ema_21 < ema_50:
        score_short += 12
        reasons_short.append("EMA bearish alignment")

    if current_price > ema_200:
        score_long += 8
    else:
        score_short += 8

    # ADX - trend strength
    if adx > 25:
        if score_long > score_short:
            score_long += 8
            reasons_long.append(f"ADX={adx:.1f} strong trend")
        else:
            score_short += 8
            reasons_short.append(f"ADX={adx:.1f} strong trend")

    # Supertrend
    if st_trend == 1:
        score_long += 15
        reasons_long.append("Supertrend bullish")
    else:
        score_short += 15
        reasons_short.append("Supertrend bearish")

    # Bollinger Bands
    if current_price < bb_lower:
        score_long += 10
        reasons_long.append("Price below BB lower")
    elif current_price > bb_upper:
        score_short += 10
        reasons_short.append("Price above BB upper")
    elif current_price < bb_mid:
        score_long += 4
    else:
        score_short += 4

    # Volume
    if vol_ratio > 1.5:
        if score_long > score_short:
            score_long += 8
            reasons_long.append(f"High volume {vol_ratio:.1f}x")
        else:
            score_short += 8
            reasons_short.append(f"High volume {vol_ratio:.1f}x")

    # Stochastic
    if stoch_k < 20 and stoch_k > stoch_d:
        score_long += 8
        reasons_long.append(f"Stoch oversold cross")
    elif stoch_k > 80 and stoch_k < stoch_d:
        score_short += 8
        reasons_short.append(f"Stoch overbought cross")

    # SMC
    if smc["bos_bullish"] or smc["ob_bullish"]:
        score_long += 10
        reasons_long.append("SMC bullish structure")
    if smc["bos_bearish"] or smc["ob_bearish"]:
        score_short += 10
        reasons_short.append("SMC bearish structure")
    if smc["choch"]:
        bonus = 5
        if score_long > score_short:
            score_long += bonus
        else:
            score_short += bonus

    total_max = 111
    long_confidence = min(100, int(score_long / total_max * 100))
    short_confidence = min(100, int(score_short / total_max * 100))

    if long_confidence > short_confidence and long_confidence >= 55:
        direction = "LONG"
        confidence = long_confidence
        reasons = reasons_long
    elif short_confidence > long_confidence and short_confidence >= 55:
        direction = "SHORT"
        confidence = short_confidence
        reasons = reasons_short
    else:
        return None

    # ATR-based TP/SL
    atr_multiplier = 1.5
    if direction == "LONG":
        sl = round(current_price - atr * atr_multiplier, 6)
        tp1 = round(current_price + atr * atr_multiplier, 6)
        tp2 = round(current_price + atr * atr_multiplier * 2, 6)
    else:
        sl = round(current_price + atr * atr_multiplier, 6)
        tp1 = round(current_price - atr * atr_multiplier, 6)
        tp2 = round(current_price - atr * atr_multiplier * 2, 6)

    risk_reward = abs(tp1 - current_price) / abs(sl - current_price) if abs(sl - current_price) > 0 else 1.0

    return {
        "symbol": symbol,
        "direction": direction,
        "confidence": confidence,
        "entry": round(current_price, 6),
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "atr": round(atr, 6),
        "rsi": round(rsi, 2),
        "macd": round(macd_line, 6),
        "adx": round(adx, 2),
        "ema_9": round(ema_9, 6),
        "ema_21": round(ema_21, 6),
        "ema_50": round(ema_50, 6),
        "supertrend": round(st_level, 6),
        "supertrend_dir": "↑" if st_trend == 1 else "↓",
        "volume_ratio": round(vol_ratio, 2),
        "risk_reward": round(risk_reward, 2),
        "reasons": reasons,
        "timeframe": timeframe
    }

"""
ZOKPAT Pattern Analyzer — Chart pattern detection engine.
Patterns: Double Top/Bottom, Triple Top/Bottom, Head & Shoulders,
Inverse H&S, Rising/Falling Wedge, Ascending/Descending Triangle.
Timeframes: 15m, 1H, 4H, 1D
Risk: 1:1 RR always enforced.
"""
import numpy as np
from typing import Optional, List, Dict, Tuple
from services.analyzer import safe_float


def parse_candles(candles_data: list) -> Tuple[np.ndarray, ...]:
    ts, opens, highs, lows, closes, vols = [], [], [], [], [], []
    for c in candles_data:
        try:
            ts.append(int(c[0]))
            opens.append(safe_float(c[1]))
            highs.append(safe_float(c[2]))
            lows.append(safe_float(c[3]))
            closes.append(safe_float(c[4]))
            vols.append(safe_float(c[5]) if len(c) > 5 else 0.0)
        except Exception:
            pass
    return (np.array(ts), np.array(opens), np.array(highs),
            np.array(lows), np.array(closes), np.array(vols))


def find_pivots(highs: np.ndarray, lows: np.ndarray,
                window: int = 3) -> Tuple[List[int], List[int]]:
    peaks, troughs = [], []
    for i in range(window, len(highs) - window):
        if (all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and
                all(highs[i] >= highs[i + j] for j in range(1, window + 1))):
            peaks.append(i)
        if (all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and
                all(lows[i] <= lows[i + j] for j in range(1, window + 1))):
            troughs.append(i)
    return peaks, troughs


def _scale(price: float) -> int:
    if price >= 10000: return 1
    if price >= 100:   return 2
    if price >= 1:     return 4
    if price >= 0.1:   return 5
    if price >= 0.01:  return 6
    return 8


def _enforce_rr(direction: str, entry: float, tp: float, sl: float) -> Tuple[float, float]:
    """Ensure 1:1 Risk:Reward minimum."""
    s = _scale(entry)
    tp_dist = abs(tp - entry)
    sl_dist = abs(sl - entry)
    if sl_dist < 1e-10:
        sl_dist = entry * 0.015
        sl = round(entry - sl_dist if direction == "LONG" else entry + sl_dist, s)
    if tp_dist < sl_dist * 0.9:
        tp = round(entry + sl_dist if direction == "LONG" else entry - sl_dist, s)
    return tp, sl


def detect_double_top(highs, lows, peaks, entry) -> Optional[Dict]:
    if len(peaks) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    h1, h2 = highs[p1], highs[p2]
    if abs(h1 - h2) / max(h1, h2) > 0.025:
        return None
    neckline = float(np.min(lows[p1:p2 + 1]))
    if entry > neckline * 1.005:
        return None
    resistance = (h1 + h2) / 2
    height = resistance - neckline
    tp = neckline - height
    sl = resistance * 1.004
    s = _scale(entry)
    tp, sl = _enforce_rr("SHORT", entry, round(tp, s), round(sl, s))
    conf = 76 + (5 if abs(h1 - h2) / max(h1, h2) < 0.01 else 0)
    return {
        "pattern": "Double Top", "direction": "SHORT", "confidence": conf,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s), "resistance": round(resistance, s),
        "draw": {"type": "double_top", "p1": p1, "p2": p2,
                 "h1": h1, "h2": h2, "neckline": neckline},
    }


def detect_double_bottom(highs, lows, troughs, entry) -> Optional[Dict]:
    if len(troughs) < 2:
        return None
    t1, t2 = troughs[-2], troughs[-1]
    l1, l2 = lows[t1], lows[t2]
    if abs(l1 - l2) / min(l1, l2) > 0.025:
        return None
    neckline = float(np.max(highs[t1:t2 + 1]))
    if entry < neckline * 0.995:
        return None
    support = (l1 + l2) / 2
    height = neckline - support
    tp = neckline + height
    sl = support * 0.996
    s = _scale(entry)
    tp, sl = _enforce_rr("LONG", entry, round(tp, s), round(sl, s))
    conf = 76 + (5 if abs(l1 - l2) / min(l1, l2) < 0.01 else 0)
    return {
        "pattern": "Double Bottom", "direction": "LONG", "confidence": conf,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s), "support": round(support, s),
        "draw": {"type": "double_bottom", "t1": t1, "t2": t2,
                 "l1": l1, "l2": l2, "neckline": neckline},
    }


def detect_triple_top(highs, lows, peaks, entry) -> Optional[Dict]:
    if len(peaks) < 3:
        return None
    p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
    h1, h2, h3 = highs[p1], highs[p2], highs[p3]
    avg = (h1 + h2 + h3) / 3
    if max(abs(h1 - avg), abs(h2 - avg), abs(h3 - avg)) / avg > 0.04:
        return None
    neckline = float(np.min(lows[p1:p3 + 1]))
    if entry > neckline * 1.005:
        return None
    height = avg - neckline
    tp = neckline - height
    sl = avg * 1.004
    s = _scale(entry)
    tp, sl = _enforce_rr("SHORT", entry, round(tp, s), round(sl, s))
    return {
        "pattern": "Triple Top", "direction": "SHORT", "confidence": 81,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s), "resistance": round(avg, s),
        "draw": {"type": "triple_top", "p1": p1, "p2": p2, "p3": p3,
                 "h1": h1, "h2": h2, "h3": h3, "neckline": neckline},
    }


def detect_triple_bottom(highs, lows, troughs, entry) -> Optional[Dict]:
    if len(troughs) < 3:
        return None
    t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
    l1, l2, l3 = lows[t1], lows[t2], lows[t3]
    avg = (l1 + l2 + l3) / 3
    if max(abs(l1 - avg), abs(l2 - avg), abs(l3 - avg)) / avg > 0.04:
        return None
    neckline = float(np.max(highs[t1:t3 + 1]))
    if entry < neckline * 0.995:
        return None
    height = neckline - avg
    tp = neckline + height
    sl = avg * 0.996
    s = _scale(entry)
    tp, sl = _enforce_rr("LONG", entry, round(tp, s), round(sl, s))
    return {
        "pattern": "Triple Bottom", "direction": "LONG", "confidence": 81,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s), "support": round(avg, s),
        "draw": {"type": "triple_bottom", "t1": t1, "t2": t2, "t3": t3,
                 "l1": l1, "l2": l2, "l3": l3, "neckline": neckline},
    }


def detect_head_shoulders(highs, lows, peaks, entry) -> Optional[Dict]:
    if len(peaks) < 3:
        return None
    ls, hd, rs = peaks[-3], peaks[-2], peaks[-1]
    h_ls, h_hd, h_rs = highs[ls], highs[hd], highs[rs]
    if not (h_hd > h_ls and h_hd > h_rs):
        return None
    if abs(h_ls - h_rs) / max(h_ls, h_rs) > 0.06:
        return None
    t1 = float(np.min(lows[ls:hd + 1]))
    t2 = float(np.min(lows[hd:rs + 1]))
    neckline = (t1 + t2) / 2
    if entry > neckline * 1.005:
        return None
    height = h_hd - neckline
    tp = neckline - height
    sl = h_rs * 1.004
    s = _scale(entry)
    tp, sl = _enforce_rr("SHORT", entry, round(tp, s), round(sl, s))
    return {
        "pattern": "Head & Shoulders", "direction": "SHORT", "confidence": 83,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "hs", "ls": ls, "hd": hd, "rs": rs,
                 "h_ls": h_ls, "h_hd": h_hd, "h_rs": h_rs,
                 "neckline": neckline, "t1": t1, "t2": t2},
    }


def detect_inverse_hs(highs, lows, troughs, entry) -> Optional[Dict]:
    if len(troughs) < 3:
        return None
    ls, hd, rs = troughs[-3], troughs[-2], troughs[-1]
    l_ls, l_hd, l_rs = lows[ls], lows[hd], lows[rs]
    if not (l_hd < l_ls and l_hd < l_rs):
        return None
    if abs(l_ls - l_rs) / min(l_ls, l_rs) > 0.06:
        return None
    pk1 = float(np.max(highs[ls:hd + 1]))
    pk2 = float(np.max(highs[hd:rs + 1]))
    neckline = (pk1 + pk2) / 2
    if entry < neckline * 0.995:
        return None
    height = neckline - l_hd
    tp = neckline + height
    sl = l_rs * 0.996
    s = _scale(entry)
    tp, sl = _enforce_rr("LONG", entry, round(tp, s), round(sl, s))
    return {
        "pattern": "Inv. Head & Shoulders", "direction": "LONG", "confidence": 83,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "ihs", "ls": ls, "hd": hd, "rs": rs,
                 "l_ls": l_ls, "l_hd": l_hd, "l_rs": l_rs,
                 "neckline": neckline, "pk1": pk1, "pk2": pk2},
    }


def detect_wedge(highs, lows, closes, peaks, troughs, entry) -> Optional[Dict]:
    n = len(closes)
    if n < 20 or len(peaks) < 2 or len(troughs) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    t1, t2 = troughs[-2], troughs[-1]
    up_slope = (highs[p2] - highs[p1]) / max(p2 - p1, 1)
    lo_slope = (lows[t2] - lows[t1]) / max(t2 - t1, 1)
    s = _scale(entry)

    # Rising Wedge → SHORT
    if up_slope > 0 and lo_slope > 0 and lo_slope > up_slope * 1.1:
        upper_now = highs[p2] + up_slope * (n - 1 - p2)
        if entry > upper_now * 1.02:
            return None
        height = highs[p2] - lows[t1]
        tp = round(entry - height * 0.85, s)
        sl = round(upper_now * 1.008, s)
        tp, sl = _enforce_rr("SHORT", entry, tp, sl)
        return {
            "pattern": "Rising Wedge", "direction": "SHORT", "confidence": 74,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "wedge_rising", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": highs[p1], "h_p2": highs[p2],
                     "l_t1": lows[t1], "l_t2": lows[t2]},
        }

    # Falling Wedge → LONG
    if up_slope < 0 and lo_slope < 0 and abs(up_slope) > abs(lo_slope) * 1.1:
        lower_now = lows[t2] + lo_slope * (n - 1 - t2)
        if entry < lower_now * 0.98:
            return None
        height = highs[p1] - lows[t2]
        tp = round(entry + height * 0.85, s)
        sl = round(lower_now * 0.992, s)
        tp, sl = _enforce_rr("LONG", entry, tp, sl)
        return {
            "pattern": "Falling Wedge", "direction": "LONG", "confidence": 74,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "wedge_falling", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": highs[p1], "h_p2": highs[p2],
                     "l_t1": lows[t1], "l_t2": lows[t2]},
        }
    return None


def detect_triangle(highs, lows, closes, peaks, troughs, entry) -> Optional[Dict]:
    if len(peaks) < 2 or len(troughs) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    t1, t2 = troughs[-2], troughs[-1]
    up_slope = (highs[p2] - highs[p1]) / max(p2 - p1, 1)
    lo_slope = (lows[t2] - lows[t1]) / max(t2 - t1, 1)
    s = _scale(entry)

    # Ascending Triangle → LONG
    if abs(up_slope) < abs(lo_slope) * 0.25 and lo_slope > 0:
        resistance = (highs[p1] + highs[p2]) / 2
        height = resistance - lows[t2]
        tp = round(resistance + height, s)
        sl = round(lows[t2] * 0.996, s)
        tp, sl = _enforce_rr("LONG", entry, tp, sl)
        return {
            "pattern": "Ascending Triangle", "direction": "LONG", "confidence": 73,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "resistance": round(resistance, s),
            "draw": {"type": "triangle_asc", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": highs[p1], "h_p2": highs[p2],
                     "l_t1": lows[t1], "l_t2": lows[t2], "resistance": resistance},
        }

    # Descending Triangle → SHORT
    if abs(lo_slope) < abs(up_slope) * 0.25 and up_slope < 0:
        support = (lows[t1] + lows[t2]) / 2
        height = highs[p2] - support
        tp = round(support - height, s)
        sl = round(highs[p2] * 1.004, s)
        tp, sl = _enforce_rr("SHORT", entry, tp, sl)
        return {
            "pattern": "Descending Triangle", "direction": "SHORT", "confidence": 73,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "support": round(support, s),
            "draw": {"type": "triangle_desc", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": highs[p1], "h_p2": highs[p2],
                     "l_t1": lows[t1], "l_t2": lows[t2], "support": support},
        }

    # Symmetric Triangle → follow recent trend
    if up_slope < 0 and lo_slope > 0:
        # Breakout direction = last 5 candles trend
        recent_trend = closes[-1] - closes[-5] if len(closes) >= 5 else 0
        direction = "LONG" if recent_trend >= 0 else "SHORT"
        height = highs[p1] - lows[t1]
        s2 = _scale(entry)
        if direction == "LONG":
            tp = round(entry + height * 0.75, s2)
            sl = round(lows[t2] * 0.996, s2)
        else:
            tp = round(entry - height * 0.75, s2)
            sl = round(highs[p2] * 1.004, s2)
        tp, sl = _enforce_rr(direction, entry, tp, sl)
        return {
            "pattern": "Symmetric Triangle", "direction": direction, "confidence": 70,
            "entry": round(entry, s2), "tp": tp, "sl": sl,
            "draw": {"type": "triangle_sym", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": highs[p1], "h_p2": highs[p2],
                     "l_t1": lows[t1], "l_t2": lows[t2]},
        }
    return None


def get_sr_levels(highs: np.ndarray, lows: np.ndarray,
                  n_levels: int = 4) -> Tuple[List[float], List[float]]:
    """Extract clustered support/resistance levels."""
    n = len(highs)
    w = max(3, n // 20)
    res_levels, sup_levels = [], []
    for i in range(w, n - w):
        if (all(highs[i] >= highs[i-j] for j in range(1, w+1)) and
                all(highs[i] >= highs[i+j] for j in range(1, w+1))):
            res_levels.append(float(highs[i]))
        if (all(lows[i] <= lows[i-j] for j in range(1, w+1)) and
                all(lows[i] <= lows[i+j] for j in range(1, w+1))):
            sup_levels.append(float(lows[i]))

    def cluster(lst, tol=0.012):
        if not lst:
            return []
        lst = sorted(lst, reverse=True)
        groups, cur = [], [lst[0]]
        for v in lst[1:]:
            if abs(v - cur[-1]) / cur[-1] < tol:
                cur.append(v)
            else:
                groups.append(float(np.mean(cur)))
                cur = [v]
        groups.append(float(np.mean(cur)))
        return groups

    return cluster(res_levels)[:n_levels], cluster(sup_levels)[:n_levels]


def detect_chart_patterns(candles_data: list, symbol: str,
                          timeframe: str) -> Optional[Dict]:
    """
    Main entry — detect best chart pattern from candles.
    Returns enriched pattern dict or None.
    """
    if not candles_data or len(candles_data) < 35:
        return None

    _, opens, highs, lows, closes, vols = parse_candles(candles_data)
    if len(closes) < 35:
        return None

    entry = float(closes[-1])
    window = max(3, len(closes) // 12)
    peaks, troughs = find_pivots(highs, lows, window)

    candidates = []

    p = detect_double_top(highs, lows, peaks, entry)
    if p: candidates.append(p)

    p = detect_double_bottom(highs, lows, troughs, entry)
    if p: candidates.append(p)

    p = detect_triple_top(highs, lows, peaks, entry)
    if p: candidates.append(p)

    p = detect_triple_bottom(highs, lows, troughs, entry)
    if p: candidates.append(p)

    p = detect_head_shoulders(highs, lows, peaks, entry)
    if p: candidates.append(p)

    p = detect_inverse_hs(highs, lows, troughs, entry)
    if p: candidates.append(p)

    p = detect_wedge(highs, lows, closes, peaks, troughs, entry)
    if p: candidates.append(p)

    p = detect_triangle(highs, lows, closes, peaks, troughs, entry)
    if p: candidates.append(p)

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x["confidence"])
    resistances, supports = get_sr_levels(highs, lows)

    best.update({
        "symbol": symbol,
        "timeframe": timeframe,
        "resistances": resistances,
        "supports": supports,
        "highs_list": highs.tolist(),
        "lows_list": lows.tolist(),
        "closes_list": closes.tolist(),
        "n_candles": len(closes),
    })
    return best

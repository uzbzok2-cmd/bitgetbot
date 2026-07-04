"""
ZOKPAT Pattern Analyzer — Chart pattern detection engine.
TP/SL logic: nearest S/R based (not pattern height).
- SHORT: SL = nearest resistance above + buffer; TP = nearest support below (1:1 min)
- LONG:  SL = nearest support below - buffer; TP = nearest resistance above (1:1 min)
Trend line detection included.
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


def _scale(price: float) -> int:
    if price >= 10000: return 1
    if price >= 100:   return 2
    if price >= 1:     return 4
    if price >= 0.1:   return 5
    if price >= 0.01:  return 6
    return 8


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


def get_sr_levels(highs: np.ndarray, lows: np.ndarray,
                  n_levels: int = 8) -> Tuple[List[float], List[float]]:
    """Extract clustered S/R levels."""
    n = len(highs)
    w = max(3, n // 20)
    res_raw, sup_raw = [], []
    for i in range(w, n - w):
        if (all(highs[i] >= highs[i - j] for j in range(1, w + 1)) and
                all(highs[i] >= highs[i + j] for j in range(1, w + 1))):
            res_raw.append(float(highs[i]))
        if (all(lows[i] <= lows[i - j] for j in range(1, w + 1)) and
                all(lows[i] <= lows[i + j] for j in range(1, w + 1))):
            sup_raw.append(float(lows[i]))

    def cluster(lst, tol=0.012):
        if not lst:
            return []
        lst = sorted(lst, reverse=True)
        groups, cur = [], [lst[0]]
        for v in lst[1:]:
            if abs(v - cur[-1]) / max(cur[-1], 1e-10) < tol:
                cur.append(v)
            else:
                groups.append(float(np.mean(cur)))
                cur = [v]
        groups.append(float(np.mean(cur)))
        return groups

    return cluster(res_raw)[:n_levels], cluster(sup_raw)[:n_levels]


def get_nearest_sr(highs, lows, entry, n_levels=8):
    """
    Find nearest resistance above entry and nearest support below entry.
    Returns: (nearest_res, nearest_sup, all_resistances, all_supports)
    """
    resistances, supports = get_sr_levels(highs, lows, n_levels)

    res_above = sorted([r for r in resistances if r > entry * 1.001])
    nearest_res = res_above[0] if res_above else None

    sup_below = sorted([s for s in supports if s < entry * 0.999], reverse=True)
    nearest_sup = sup_below[0] if sup_below else None

    return nearest_res, nearest_sup, resistances, supports


def calc_sr_tp_sl(direction: str, entry: float,
                  nearest_res: Optional[float], nearest_sup: Optional[float],
                  buffer: float = 0.004) -> Tuple[float, float]:
    """
    S/R asosida TP/SL hisoblash.
    SHORT: SL = nearest resistance + buffer; TP = nearest support (1:1 min)
    LONG:  SL = nearest support - buffer;   TP = nearest resistance (1:1 min)
    """
    s = _scale(entry)

    if direction == "SHORT":
        if nearest_res and nearest_res > entry:
            sl = round(nearest_res * (1.0 + buffer), s)
        else:
            sl = round(entry * 1.012, s)
        sl_dist = sl - entry

        if nearest_sup and nearest_sup < entry and (entry - nearest_sup) >= sl_dist * 0.85:
            tp = round(nearest_sup, s)
        else:
            tp = round(entry - sl_dist, s)

    else:  # LONG
        if nearest_sup and nearest_sup < entry:
            sl = round(nearest_sup * (1.0 - buffer), s)
        else:
            sl = round(entry * 0.988, s)
        sl_dist = entry - sl

        if nearest_res and nearest_res > entry and (nearest_res - entry) >= sl_dist * 0.85:
            tp = round(nearest_res, s)
        else:
            tp = round(entry + sl_dist, s)

    return tp, sl


def detect_trend_line(highs: np.ndarray, lows: np.ndarray,
                      closes: np.ndarray, peaks: List[int],
                      troughs: List[int]) -> Optional[Dict]:
    """
    Swing high/low orqali trend chizig'ini aniqlash.
    Returns trend dict with upper_line, lower_line, direction, broken.
    """
    n = len(closes)
    if n < 20:
        return None

    window = min(80, n)
    offset = n - window

    local_peaks   = [p for p in peaks   if p >= offset]
    local_troughs = [t for t in troughs if t >= offset]

    close_sub = closes[-window:]
    x_all = np.arange(window)
    close_slope = np.polyfit(x_all, close_sub, 1)[0] if window >= 2 else 0
    close_mean  = float(np.mean(close_sub)) if window > 0 else 1
    thr = close_mean * 0.00015
    if close_slope > thr:
        trend_dir = "up"
    elif close_slope < -thr:
        trend_dir = "down"
    else:
        trend_dir = "sideways"

    upper_line = None
    if len(local_peaks) >= 2:
        px = np.array([p - offset for p in local_peaks[-5:]], dtype=float)
        py = np.array([float(highs[p]) for p in local_peaks[-5:]])
        if len(px) >= 2:
            slope, intercept = np.polyfit(px, py, 1)
            upper_line = {
                "x0": int(px[0]),  "y0": float(slope * px[0]  + intercept),
                "x1": int(px[-1]), "y1": float(slope * px[-1] + intercept),
                "slope": float(slope), "intercept": float(intercept),
                "offset": offset,
            }

    lower_line = None
    if len(local_troughs) >= 2:
        tx = np.array([t - offset for t in local_troughs[-5:]], dtype=float)
        ty = np.array([float(lows[t]) for t in local_troughs[-5:]])
        if len(tx) >= 2:
            slope, intercept = np.polyfit(tx, ty, 1)
            lower_line = {
                "x0": int(tx[0]),  "y0": float(slope * tx[0]  + intercept),
                "x1": int(tx[-1]), "y1": float(slope * tx[-1] + intercept),
                "slope": float(slope), "intercept": float(intercept),
                "offset": offset,
            }

    # Trend break detection
    current_close = float(closes[-1])
    trend_broken  = False
    break_dir     = None
    last_x        = window - 1

    if upper_line and trend_dir == "down":
        up_now = upper_line["slope"] * last_x + upper_line["intercept"]
        if current_close > up_now * 1.003:
            trend_broken = True
            break_dir    = "LONG"

    if lower_line and trend_dir == "up":
        lo_now = lower_line["slope"] * last_x + lower_line["intercept"]
        if current_close < lo_now * 0.997:
            trend_broken  = True
            break_dir     = "SHORT"

    return {
        "direction":     trend_dir,
        "upper_line":    upper_line,
        "lower_line":    lower_line,
        "trend_broken":  trend_broken,
        "break_dir":     break_dir,
        "window":        window,
        "offset":        offset,
    }


def _is_fresh_break(closes: np.ndarray, neckline: float, direction: str,
                    max_bars: int = 3) -> bool:
    """
    Breakout 'yangi' bo'lishi kerak — oxirgi max_bars ichida neckline
    kesib o'tilgan bo'lishi shart, aks holda signal eskirgan (kech).
    """
    n = len(closes)
    if n < max_bars + 1:
        return True
    for i in range(1, max_bars + 1):
        idx = n - 1 - i
        if idx < 0:
            break
        c = float(closes[idx])
        if direction == "LONG" and c <= neckline:
            return True
        if direction == "SHORT" and c >= neckline:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Pattern detectors — all use S/R-based TP/SL
# ─────────────────────────────────────────────────────────────────────────────

def detect_double_top(highs, lows, peaks, entry, nearest_res, nearest_sup) -> Optional[Dict]:
    if len(peaks) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    h1, h2 = highs[p1], highs[p2]
    if abs(h1 - h2) / max(h1, h2) > 0.025:
        return None
    neckline = float(np.min(lows[p1:p2 + 1]))
    if entry > neckline * 1.01:
        return None
    tp, sl = calc_sr_tp_sl("SHORT", entry, nearest_res, nearest_sup)
    conf = 76 + (5 if abs(h1 - h2) / max(h1, h2) < 0.01 else 0)
    s = _scale(entry)
    return {
        "pattern": "Double Top", "direction": "SHORT", "confidence": conf,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "double_top", "p1": p1, "p2": p2,
                 "h1": float(h1), "h2": float(h2), "neckline": float(neckline)},
    }


def detect_double_bottom(highs, lows, troughs, entry, nearest_res, nearest_sup) -> Optional[Dict]:
    if len(troughs) < 2:
        return None
    t1, t2 = troughs[-2], troughs[-1]
    l1, l2 = lows[t1], lows[t2]
    if abs(l1 - l2) / min(l1, l2) > 0.025:
        return None
    neckline = float(np.max(highs[t1:t2 + 1]))
    if entry < neckline * 0.99:
        return None
    tp, sl = calc_sr_tp_sl("LONG", entry, nearest_res, nearest_sup)
    conf = 76 + (5 if abs(l1 - l2) / min(l1, l2) < 0.01 else 0)
    s = _scale(entry)
    return {
        "pattern": "Double Bottom", "direction": "LONG", "confidence": conf,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "double_bottom", "t1": t1, "t2": t2,
                 "l1": float(l1), "l2": float(l2), "neckline": float(neckline)},
    }


def detect_triple_top(highs, lows, peaks, entry, nearest_res, nearest_sup) -> Optional[Dict]:
    if len(peaks) < 3:
        return None
    p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
    h1, h2, h3 = highs[p1], highs[p2], highs[p3]
    avg = (h1 + h2 + h3) / 3
    if max(abs(h1 - avg), abs(h2 - avg), abs(h3 - avg)) / avg > 0.04:
        return None
    neckline = float(np.min(lows[p1:p3 + 1]))
    if entry > neckline * 1.01:
        return None
    tp, sl = calc_sr_tp_sl("SHORT", entry, nearest_res, nearest_sup)
    s = _scale(entry)
    return {
        "pattern": "Triple Top", "direction": "SHORT", "confidence": 81,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "triple_top", "p1": p1, "p2": p2, "p3": p3,
                 "h1": float(h1), "h2": float(h2), "h3": float(h3),
                 "neckline": float(neckline)},
    }


def detect_triple_bottom(highs, lows, troughs, entry, nearest_res, nearest_sup) -> Optional[Dict]:
    if len(troughs) < 3:
        return None
    t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
    l1, l2, l3 = lows[t1], lows[t2], lows[t3]
    avg = (l1 + l2 + l3) / 3
    if max(abs(l1 - avg), abs(l2 - avg), abs(l3 - avg)) / avg > 0.04:
        return None
    neckline = float(np.max(highs[t1:t3 + 1]))
    if entry < neckline * 0.99:
        return None
    tp, sl = calc_sr_tp_sl("LONG", entry, nearest_res, nearest_sup)
    s = _scale(entry)
    return {
        "pattern": "Triple Bottom", "direction": "LONG", "confidence": 81,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "triple_bottom", "t1": t1, "t2": t2, "t3": t3,
                 "l1": float(l1), "l2": float(l2), "l3": float(l3),
                 "neckline": float(neckline)},
    }


def detect_head_shoulders(highs, lows, peaks, entry, nearest_res, nearest_sup) -> Optional[Dict]:
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
    if entry > neckline * 1.01:
        return None
    tp, sl = calc_sr_tp_sl("SHORT", entry, nearest_res, nearest_sup)
    s = _scale(entry)
    return {
        "pattern": "Head & Shoulders", "direction": "SHORT", "confidence": 83,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "hs", "ls": ls, "hd": hd, "rs": rs,
                 "h_ls": float(h_ls), "h_hd": float(h_hd), "h_rs": float(h_rs),
                 "neckline": float(neckline), "t1": float(t1), "t2": float(t2)},
    }


def detect_inverse_hs(highs, lows, troughs, entry, nearest_res, nearest_sup) -> Optional[Dict]:
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
    if entry < neckline * 0.99:
        return None
    tp, sl = calc_sr_tp_sl("LONG", entry, nearest_res, nearest_sup)
    s = _scale(entry)
    return {
        "pattern": "Inv. Head & Shoulders", "direction": "LONG", "confidence": 83,
        "entry": round(entry, s), "tp": tp, "sl": sl,
        "neckline": round(neckline, s),
        "draw": {"type": "ihs", "ls": ls, "hd": hd, "rs": rs,
                 "l_ls": float(l_ls), "l_hd": float(l_hd), "l_rs": float(l_rs),
                 "neckline": float(neckline), "pk1": float(pk1), "pk2": float(pk2)},
    }


def detect_wedge(highs, lows, closes, peaks, troughs,
                 entry, nearest_res, nearest_sup) -> Optional[Dict]:
    n = len(closes)
    if n < 20 or len(peaks) < 2 or len(troughs) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    t1, t2 = troughs[-2], troughs[-1]
    up_slope = (highs[p2] - highs[p1]) / max(p2 - p1, 1)
    lo_slope = (lows[t2]  - lows[t1])  / max(t2 - t1, 1)
    s = _scale(entry)

    if up_slope > 0 and lo_slope > 0 and lo_slope > up_slope * 1.1:
        upper_now = highs[p2] + up_slope * (n - 1 - p2)
        if entry > upper_now * 1.02:
            return None
        tp, sl = calc_sr_tp_sl("SHORT", entry, nearest_res, nearest_sup)
        return {
            "pattern": "Rising Wedge", "direction": "SHORT", "confidence": 74,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "wedge_rising", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": float(highs[p1]), "h_p2": float(highs[p2]),
                     "l_t1": float(lows[t1]),  "l_t2": float(lows[t2])},
        }

    if up_slope < 0 and lo_slope < 0 and abs(up_slope) > abs(lo_slope) * 1.1:
        lower_now = lows[t2] + lo_slope * (n - 1 - t2)
        if entry < lower_now * 0.98:
            return None
        tp, sl = calc_sr_tp_sl("LONG", entry, nearest_res, nearest_sup)
        return {
            "pattern": "Falling Wedge", "direction": "LONG", "confidence": 74,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "wedge_falling", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": float(highs[p1]), "h_p2": float(highs[p2]),
                     "l_t1": float(lows[t1]),  "l_t2": float(lows[t2])},
        }
    return None


def detect_triangle(highs, lows, closes, peaks, troughs,
                    entry, nearest_res, nearest_sup) -> Optional[Dict]:
    if len(peaks) < 2 or len(troughs) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    t1, t2 = troughs[-2], troughs[-1]
    up_slope = (highs[p2] - highs[p1]) / max(p2 - p1, 1)
    lo_slope = (lows[t2]  - lows[t1])  / max(t2 - t1, 1)
    s = _scale(entry)

    if abs(up_slope) < abs(lo_slope) * 0.25 and lo_slope > 0:
        tp, sl = calc_sr_tp_sl("LONG", entry, nearest_res, nearest_sup)
        return {
            "pattern": "Ascending Triangle", "direction": "LONG", "confidence": 73,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "triangle_asc", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": float(highs[p1]), "h_p2": float(highs[p2]),
                     "l_t1": float(lows[t1]),  "l_t2": float(lows[t2])},
        }

    if abs(lo_slope) < abs(up_slope) * 0.25 and up_slope < 0:
        tp, sl = calc_sr_tp_sl("SHORT", entry, nearest_res, nearest_sup)
        return {
            "pattern": "Descending Triangle", "direction": "SHORT", "confidence": 73,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "triangle_desc", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": float(highs[p1]), "h_p2": float(highs[p2]),
                     "l_t1": float(lows[t1]),  "l_t2": float(lows[t2])},
        }

    if up_slope < 0 and lo_slope > 0:
        recent = closes[-1] - closes[-5] if len(closes) >= 5 else 0
        direction = "LONG" if recent >= 0 else "SHORT"
        tp, sl = calc_sr_tp_sl(direction, entry, nearest_res, nearest_sup)
        return {
            "pattern": "Symmetric Triangle", "direction": direction, "confidence": 70,
            "entry": round(entry, s), "tp": tp, "sl": sl,
            "draw": {"type": "triangle_sym", "p1": p1, "p2": p2, "t1": t1, "t2": t2,
                     "h_p1": float(highs[p1]), "h_p2": float(highs[p2]),
                     "l_t1": float(lows[t1]),  "l_t2": float(lows[t2])},
        }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 🔷 Trend Buzish — W-Break pattern (5-point double-bottom neckline break)
# ─────────────────────────────────────────────────────────────────────────────

def detect_w_break_pattern(opens: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                           closes: np.ndarray, peaks: List[int],
                           troughs: List[int]) -> Optional[Dict]:
    """
    5 nuqtali W-Break (Trend Buzish) pattern:
    ① yuqori nuqta → ② past nuqta → ③ neckline (pastroq yuqori) →
    ④ past nuqta (② ga yaqin) → ⑤ breakout (③ dan yuqoriga yopiladi).
    Freshness: breakout ③ dan max 2 sham oldin sodir bo'lgan bo'lishi kerak,
    va ④ dan ⑤ gacha narx ①-② balandligining yarmidan oshib ketmagan bo'lishi kerak.
    TP = ② + 0.680 * (① − ②)  — fib retracement ② dan ① tomon.
    """
    n = len(closes)
    if n < 25 or len(troughs) < 2 or len(peaks) < 1:
        return None

    t2, t4 = troughs[-2], troughs[-1]
    if t4 <= t2 or t4 - t2 < 2:
        return None

    peaks_before_t2 = [p for p in peaks if p < t2]
    if not peaks_before_t2:
        return None
    p1 = peaks_before_t2[-1]

    seg = highs[t2:t4 + 1]
    p3 = t2 + int(np.argmax(seg))

    p1_price   = float(highs[p1])
    p2_price   = float(lows[t2])
    neck_price = float(highs[p3])
    p4_price   = float(lows[t4])

    if p1_price <= neck_price or neck_price <= p2_price or neck_price <= p4_price:
        return None
    if abs(p4_price - p2_price) / max(p2_price, 1e-10) > 0.06:
        return None

    p5 = None
    for i in range(t4 + 1, n):
        if closes[i] > neck_price:
            p5 = i
            break
    if p5 is None:
        return None

    # Freshness #1 — breakout yaqinda sodir bo'lishi kerak
    if n - 1 - p5 > 2:
        return None

    # Freshness #2 — ④→⑤ orasida narx ①-② balandligining yarmidan oshmagan bo'lishi kerak
    half_level = p2_price + 0.5 * (p1_price - p2_price)
    pre_break_highs = highs[t4 + 1:p5] if p5 > t4 + 1 else np.array([])
    if len(pre_break_highs) > 0 and float(np.max(pre_break_highs)) > half_level:
        return None

    s = _scale(float(closes[p5]))
    entry = round(float(closes[p5]), s)
    tp    = round(p2_price + 0.680 * (p1_price - p2_price), s)
    sl    = round(p4_price * 0.995, s)
    if tp <= entry or sl >= entry:
        return None

    conf = 79 if (n - 1 - p5) <= 1 else 75

    return {
        "pattern": "Trend Buzish (W-Break)", "direction": "LONG", "confidence": conf,
        "entry": entry, "tp": tp, "sl": sl,
        "neckline": round(neck_price, s),
        "kind": "w_break", "window": min(80, n),
        "p1_idx": p1, "p2_idx": t2, "p3_idx": p3, "p4_idx": t4, "p5_idx": p5,
        "p1_price": p1_price, "p2_price": p2_price, "p3_price": neck_price,
        "p4_price": p4_price, "p5_price": entry,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 🔷 Trend Buzish — Fresh trendline break (diagonal trend line only)
# ─────────────────────────────────────────────────────────────────────────────

def detect_fresh_trendline_break(opens: np.ndarray, highs: np.ndarray,
                                 lows: np.ndarray, closes: np.ndarray,
                                 peaks: List[int], troughs: List[int]) -> Optional[Dict]:
    """
    Pasayuvchi diagonal trend chizig'ini yorib chiqish — faqat YANGI (fresh)
    breakout paytida signal beradi. TP — sham TANASI (close/open) asosidagi
    eng oxirgi 1-2 qarshilik (resistance) zonasi, soyasi (wick) emas.
    """
    n = len(closes)
    if n < 25 or len(peaks) < 2:
        return None

    trend = detect_trend_line(highs, lows, closes, peaks, troughs)
    if not trend or trend.get("direction") != "down" or not trend.get("upper_line"):
        return None

    upper  = trend["upper_line"]
    offset = trend["offset"]
    window = trend["window"]
    last_x = window - 1

    break_idx = None
    for k in range(0, 3):
        idx_local = last_x - k
        idx_abs   = offset + idx_local
        if idx_abs < 1 or idx_abs >= n:
            continue
        line_val = upper["slope"] * idx_local + upper["intercept"]
        if closes[idx_abs] <= line_val * 1.003:
            continue
        prev_local = idx_local - 1
        prev_abs   = offset + prev_local
        if prev_abs < 0:
            continue
        prev_line_val = upper["slope"] * prev_local + upper["intercept"]
        if closes[prev_abs] <= prev_line_val * 1.003:
            break_idx = idx_abs
            break

    if break_idx is None:
        return None
    if n - 1 - break_idx > 2:
        return None

    entry = float(closes[break_idx])
    s = _scale(entry)

    # Sham TANASI asosida resistance zonalari (wick emas)
    body_highs = np.maximum(opens, closes)
    candidates = sorted(set(
        round(float(b), s) for b in body_highs
        if b > entry * 1.004
    ))
    if not candidates:
        return None
    tp_levels = candidates[:2]
    tp = tp_levels[-1]

    lookback_lo = max(0, break_idx - 12)
    sl = round(float(np.min(lows[lookback_lo:break_idx + 1])) * 0.995, s)
    entry = round(entry, s)
    if tp <= entry or sl >= entry:
        return None

    conf = 76 if (n - 1 - break_idx) <= 1 else 72

    return {
        "pattern": "Trend Buzish (Trendline Break)", "direction": "LONG",
        "confidence": conf, "entry": entry, "tp": tp, "sl": sl,
        "kind": "trendline_break", "window": window,
        "trend_line": upper, "break_idx": break_idx, "tp_levels": tp_levels,
    }


def detect_trend_break(candles_data: list, symbol: str,
                       timeframe: str) -> Optional[Dict]:
    """🔷 Trend Buzish — asosiy entry point. W-Break va Trendline-Break tekshiradi."""
    if not candles_data or len(candles_data) < 30:
        return None

    _, opens, highs, lows, closes, vols = parse_candles(candles_data)
    if len(closes) < 30:
        return None

    window = max(3, len(closes) // 12)
    peaks, troughs = find_pivots(highs, lows, window)

    candidates = []
    p = detect_w_break_pattern(opens, highs, lows, closes, peaks, troughs)
    if p: candidates.append(p)
    p = detect_fresh_trendline_break(opens, highs, lows, closes, peaks, troughs)
    if p: candidates.append(p)

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x["confidence"])
    best.update({"symbol": symbol, "timeframe": timeframe, "n_candles": len(closes)})
    return best


def detect_chart_patterns(candles_data: list, symbol: str,
                          timeframe: str) -> Optional[Dict]:
    """
    Main entry — detect best chart pattern from candles.
    TP/SL based on nearest S/R zones.
    """
    if not candles_data or len(candles_data) < 35:
        return None

    _, opens, highs, lows, closes, vols = parse_candles(candles_data)
    if len(closes) < 35:
        return None

    entry  = float(closes[-1])
    window = max(3, len(closes) // 12)
    peaks, troughs = find_pivots(highs, lows, window)

    # Nearest S/R relative to current price
    nearest_res, nearest_sup, resistances, supports = get_nearest_sr(highs, lows, entry)

    # Trend line
    trend = detect_trend_line(highs, lows, closes, peaks, troughs)

    candidates = []

    p = detect_double_top(highs, lows, peaks, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_double_bottom(highs, lows, troughs, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_triple_top(highs, lows, peaks, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_triple_bottom(highs, lows, troughs, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_head_shoulders(highs, lows, peaks, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_inverse_hs(highs, lows, troughs, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_wedge(highs, lows, closes, peaks, troughs, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    p = detect_triangle(highs, lows, closes, peaks, troughs, entry, nearest_res, nearest_sup)
    if p: candidates.append(p)

    # Boost confidence if trend break confirms pattern direction
    for c in candidates:
        if trend and trend["trend_broken"] and trend["break_dir"] == c["direction"]:
            c["confidence"] = min(95, c["confidence"] + 8)
            c["trend_confirmed"] = True
        else:
            c["trend_confirmed"] = False

    # Freshness filter — neckline'ga ega patternlar uchun breakout yangi bo'lishi shart
    fresh_candidates = []
    for c in candidates:
        neck = c.get("neckline")
        if neck is None:
            fresh_candidates.append(c)
            continue
        if _is_fresh_break(closes, neck, c["direction"]):
            fresh_candidates.append(c)
    candidates = fresh_candidates

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x["confidence"])
    best.update({
        "symbol":        symbol,
        "timeframe":     timeframe,
        "resistances":   resistances,
        "supports":      supports,
        "nearest_res":   nearest_res,
        "nearest_sup":   nearest_sup,
        "trend":         trend,
        "n_candles":     len(closes),
    })
    return best

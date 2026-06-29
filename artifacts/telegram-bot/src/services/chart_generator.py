"""
Chart image generator — creates dark-theme candlestick charts with TP/SL levels.
Returns BytesIO buffer for Telegram send_photo.
"""
import io
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from typing import List, Dict, Optional, Tuple
from services.analyzer import safe_float
from datetime import datetime, timezone


def _make_candles(candles_data: list) -> Tuple[list, list, list, list, list, list]:
    """Parse candle data into OHLCV arrays."""
    timestamps, opens, highs, lows, closes, vols = [], [], [], [], [], []
    for c in candles_data:
        try:
            timestamps.append(int(c[0]))
            opens.append(safe_float(c[1]))
            highs.append(safe_float(c[2]))
            lows.append(safe_float(c[3]))
            closes.append(safe_float(c[4]))
            vols.append(safe_float(c[5]))
        except Exception:
            pass
    return timestamps, opens, highs, lows, closes, vols


def generate_signal_chart(
    candles_data: list,
    symbol: str,
    direction: str,
    entry: float,
    tp1: float,
    tp2: float,
    sl: float,
    confidence: int,
    timeframe: str = "1H",
    last_n: int = 60,
) -> io.BytesIO:
    """
    Generate dark-theme candlestick chart with Entry, TP1, TP2, SL levels.
    Returns BytesIO PNG buffer.
    """
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    # Use only last N candles
    n = min(last_n, len(closes))
    ts_n   = timestamps[-n:]
    op_n   = opens[-n:]
    hi_n   = highs[-n:]
    lo_n   = lows[-n:]
    cl_n   = closes[-n:]
    # vol_n  = vols[-n:]

    xs = list(range(n))

    # ── Colors ────────────────────────────────────────────
    BG       = "#0d1117"
    GRID     = "#1f2937"
    UP_BODY  = "#26a69a"
    DN_BODY  = "#ef5350"
    WICK     = "#6b7280"
    ENTRY_C  = "#f59e0b"
    TP1_C    = "#22c55e"
    TP2_C    = "#16a34a"
    SL_C     = "#ef4444"
    TEXT_C   = "#e5e7eb"

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(BG)

    # ── Draw candles ──────────────────────────────────────
    w = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color = UP_BODY if c >= o else DN_BODY
        # body
        body_lo = min(o, c)
        body_hi = max(o, c)
        ax.bar(i, body_hi - body_lo, width=w, bottom=body_lo,
               color=color, linewidth=0)
        # wicks
        ax.plot([i, i], [l, body_lo], color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h], color=WICK, linewidth=0.8)

    x_right = n + 2

    # ── Horizontal levels ─────────────────────────────────
    def hline(price, color, label, alpha=1.0, ls="--"):
        ax.axhline(price, color=color, linewidth=1.2, linestyle=ls, alpha=alpha)
        ax.text(x_right - 0.5, price, f" {label}: ${_fmt(price)}",
                color=color, fontsize=7.5, va="center", ha="left",
                fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))

    hline(entry, ENTRY_C, "Kirish", ls="-")
    hline(tp1,   TP1_C,   "TP1")
    hline(tp2,   TP2_C,   "TP2")
    hline(sl,    SL_C,    "SL")

    # ── Shade TP / SL zones ───────────────────────────────
    if direction == "LONG":
        ax.axhspan(entry, max(tp1, tp2), alpha=0.06, color=TP1_C)
        ax.axhspan(sl,    entry,         alpha=0.06, color=SL_C)
    else:
        ax.axhspan(min(tp1, tp2), entry, alpha=0.06, color=TP1_C)
        ax.axhspan(entry,         sl,    alpha=0.06, color=SL_C)

    # ── Styling ───────────────────────────────────────────
    ax.set_xlim(-1, x_right + 8)
    all_prices = hi_n + lo_n + [tp1, tp2, sl, entry]
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)

    ax.tick_params(colors=TEXT_C, labelsize=7)
    ax.spines[:].set_color(GRID)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    # ── Title ─────────────────────────────────────────────
    dir_text = "🟢 XARID (LONG)" if direction == "LONG" else "🔴 SOTISH (SHORT)"
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  {dir_text}  •  {confidence}% ishonch",
        color=TEXT_C, fontsize=10, fontweight="bold", pad=8
    )

    # ── Legend ────────────────────────────────────────────
    patches = [
        mpatches.Patch(color=ENTRY_C, label=f"Kirish  ${_fmt(entry)}"),
        mpatches.Patch(color=TP1_C,   label=f"TP1  ${_fmt(tp1)}"),
        mpatches.Patch(color=TP2_C,   label=f"TP2  ${_fmt(tp2)}"),
        mpatches.Patch(color=SL_C,    label=f"SL   ${_fmt(sl)}"),
    ]
    ax.legend(handles=patches, loc="upper left", fontsize=7,
              facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

    # ── Timestamp ─────────────────────────────────────────
    fig.text(0.99, 0.02,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_position_chart(
    candles_data: list,
    symbol: str,
    direction: str,
    entry: float,
    mark_price: float,
    tp_levels: list,
    sl_levels: list,
    unrealized_pnl: float,
    leverage: int,
) -> io.BytesIO:
    """Chart for open position showing current mark price, TP/SL levels."""
    timestamps, opens, highs, lows, closes, _ = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(50, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]
    xs = list(range(n))

    BG     = "#0d1117"; GRID = "#1f2937"
    UP_C   = "#26a69a"; DN_C = "#ef5350"
    WICK   = "#6b7280"; TEXT_C = "#e5e7eb"
    ENTRY_C= "#f59e0b"
    MARK_C = "#60a5fa"
    TP_C   = "#22c55e"
    SL_C   = "#ef4444"

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(BG)
    w = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color = UP_C if c >= o else DN_C
        blo = min(o, c); bhi = max(o, c)
        ax.bar(i, bhi - blo, width=w, bottom=blo, color=color, linewidth=0)
        ax.plot([i, i], [l, blo], color=WICK, linewidth=0.8)
        ax.plot([i, i], [bhi, h], color=WICK, linewidth=0.8)

    x_right = n + 2

    def hline(price, color, label, ls="--", lw=1.2):
        ax.axhline(price, color=color, linewidth=lw, linestyle=ls, alpha=0.9)
        ax.text(x_right - 0.3, price, f" {label}: ${_fmt(price)}",
                color=color, fontsize=7.5, va="center", ha="left", fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))

    hline(entry,      ENTRY_C, "Kirish", ls="-", lw=1.5)
    hline(mark_price, MARK_C,  "Hozirgi", ls="-", lw=1.5)
    for i, tp in enumerate(tp_levels, 1):
        hline(tp, TP_C, f"TP{i}")
    for sl in sl_levels:
        hline(sl, SL_C, "SL")

    all_prices = hi_n + lo_n + [entry, mark_price] + tp_levels + sl_levels
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_xlim(-1, x_right + 10)
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    pnl_sign = "+" if unrealized_pnl >= 0 else ""
    dir_str  = "🟢 LONG" if direction == "long" else "🔴 SHORT"
    ax.set_title(
        f"{symbol}  •  1H  |  {dir_str}  {leverage}x  |  PnL: {pnl_sign}{unrealized_pnl:.4f} USDT",
        color=TEXT_C, fontsize=10, fontweight="bold", pad=8
    )

    patches = [mpatches.Patch(color=ENTRY_C, label=f"Kirish ${_fmt(entry)}"),
               mpatches.Patch(color=MARK_C,  label=f"Mark ${_fmt(mark_price)}")]
    for i, tp in enumerate(tp_levels, 1):
        patches.append(mpatches.Patch(color=TP_C, label=f"TP{i} ${_fmt(tp)}"))
    for sl in sl_levels:
        patches.append(mpatches.Patch(color=SL_C, label=f"SL ${_fmt(sl)}"))
    ax.legend(handles=patches, loc="upper left", fontsize=7,
              facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

    fig.text(0.99, 0.02, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")
    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _fmt(p: float) -> str:
    if p >= 1000:
        return f"{p:,.2f}"
    elif p >= 1:
        return f"{p:.4f}"
    elif p >= 0.01:
        return f"{p:.6f}"
    return f"{p:.8f}"


def _empty_chart(symbol: str) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(6, 3), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    ax.text(0.5, 0.5, f"{symbol}\nMa'lumot yo'q", color="white",
            ha="center", va="center", fontsize=14, transform=ax.transAxes)
    ax.axis("off")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, facecolor="#0d1117")
    plt.close(fig)
    buf.seek(0)
    return buf

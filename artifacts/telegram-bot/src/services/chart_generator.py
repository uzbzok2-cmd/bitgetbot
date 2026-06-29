"""
Chart image generator — creates dark-theme candlestick charts with TP/SL levels.
Returns BytesIO buffer for Telegram send_photo.
"""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from typing import List, Dict, Optional, Tuple
from services.analyzer import safe_float
from datetime import datetime, timezone


def _make_candles(candles_data: list) -> Tuple[list, list, list, list, list, list]:
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


def _pct_label(price: float, ref: float) -> str:
    if ref <= 0:
        return ""
    pct = (price - ref) / ref * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


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
    duration_label: str = "",
    leverage: int = 0,
) -> io.BytesIO:
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(last_n, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]

    BG      = "#0d1117"; GRID   = "#1f2937"
    UP_BODY = "#26a69a"; DN_BODY = "#ef5350"
    WICK    = "#6b7280"; ENTRY_C = "#f59e0b"
    TP1_C   = "#22c55e"; TP2_C  = "#16a34a"
    SL_C    = "#ef4444"; TEXT_C = "#e5e7eb"

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(BG)

    w = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color = UP_BODY if c >= o else DN_BODY
        body_lo = min(o, c); body_hi = max(o, c)
        ax.bar(i, body_hi - body_lo, width=w, bottom=body_lo, color=color, linewidth=0)
        ax.plot([i, i], [l, body_lo], color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h], color=WICK, linewidth=0.8)

    x_right = n + 2

    # TP/SL % vs entry
    tp1_pct = _pct_label(tp1, entry)
    tp2_pct = _pct_label(tp2, entry)
    sl_pct  = _pct_label(sl,  entry)

    # Leverage multiplied % (if leverage known)
    lev_str = ""
    if leverage > 0:
        lev_str = f"  [{leverage}x]"

    def hline(price, color, label, pct_str="", alpha=1.0, ls="--"):
        ax.axhline(price, color=color, linewidth=1.2, linestyle=ls, alpha=alpha)
        lbl = f" {label}: ${_fmt(price)}"
        if pct_str:
            lbl += f"  ({pct_str})"
        ax.text(x_right - 0.5, price, lbl,
                color=color, fontsize=7.5, va="center", ha="left",
                fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))

    hline(entry, ENTRY_C, "Kirish", ls="-")
    hline(tp1,   TP1_C,   f"TP1 (80%)", tp1_pct)
    hline(tp2,   TP2_C,   f"TP2 (20%)", tp2_pct)
    hline(sl,    SL_C,    "SL", sl_pct)

    if direction == "LONG":
        ax.axhspan(entry, max(tp1, tp2), alpha=0.06, color=TP1_C)
        ax.axhspan(sl, entry, alpha=0.06, color=SL_C)
    else:
        ax.axhspan(min(tp1, tp2), entry, alpha=0.06, color=TP1_C)
        ax.axhspan(entry, sl, alpha=0.06, color=SL_C)

    ax.set_xlim(-1, x_right + 14)
    all_prices = hi_n + lo_n + [tp1, tp2, sl, entry]
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)

    ax.tick_params(colors=TEXT_C, labelsize=7)
    ax.spines[:].set_color(GRID)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    dir_text = "🟢 XARID (LONG)" if direction == "LONG" else "🔴 SOTISH (SHORT)"
    dur_part = f"  •  {duration_label}" if duration_label else ""
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  {dir_text}  •  {confidence}% ishonch{dur_part}",
        color=TEXT_C, fontsize=10, fontweight="bold", pad=8
    )

    patches = [
        mpatches.Patch(color=ENTRY_C, label=f"Kirish  ${_fmt(entry)}"),
        mpatches.Patch(color=TP1_C,   label=f"TP1 (80%)  ${_fmt(tp1)}  {tp1_pct}"),
        mpatches.Patch(color=TP2_C,   label=f"TP2 (20%)  ${_fmt(tp2)}  {tp2_pct}"),
        mpatches.Patch(color=SL_C,    label=f"SL  ${_fmt(sl)}  {sl_pct}"),
    ]
    ax.legend(handles=patches, loc="upper left", fontsize=7,
              facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

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
    timestamps, opens, highs, lows, closes, _ = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(50, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]

    BG = "#0d1117"; GRID = "#1f2937"
    UP_C = "#26a69a"; DN_C = "#ef5350"
    WICK = "#6b7280"; TEXT_C = "#e5e7eb"
    ENTRY_C = "#f59e0b"; MARK_C = "#60a5fa"
    TP_C = "#22c55e"; SL_C = "#ef4444"

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

    def hline(price, color, label, pct_from_entry="", ls="--", lw=1.2):
        ax.axhline(price, color=color, linewidth=lw, linestyle=ls, alpha=0.9)
        lbl = f" {label}: ${_fmt(price)}"
        if pct_from_entry:
            lbl += f"  ({pct_from_entry})"
        ax.text(x_right - 0.3, price, lbl,
                color=color, fontsize=7.5, va="center", ha="left", fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))

    mark_pct = _pct_label(mark_price, entry)
    hline(entry, ENTRY_C, "Kirish", ls="-", lw=1.5)
    hline(mark_price, MARK_C, "Hozirgi", mark_pct, ls="-", lw=1.5)
    for i, tp in enumerate(tp_levels, 1):
        tp_pct = _pct_label(tp, entry)
        lbl = f"TP{i} (80%)" if i == 1 else f"TP{i} (20%)"
        hline(tp, TP_C, lbl, tp_pct)
    for sl in sl_levels:
        sl_pct = _pct_label(sl, entry)
        hline(sl, SL_C, "SL", sl_pct)

    all_prices = hi_n + lo_n + [entry, mark_price] + tp_levels + sl_levels
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_xlim(-1, x_right + 14)
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    pnl_sign = "+" if unrealized_pnl >= 0 else ""
    pnl_pct_lev = (unrealized_pnl / (entry * 1) * leverage * 100) if entry > 0 else 0
    dir_str = "🟢 LONG" if direction == "long" else "🔴 SHORT"
    ax.set_title(
        f"{symbol}  •  1H  |  {dir_str}  {leverage}x  |  PnL: {pnl_sign}{unrealized_pnl:.4f} USDT ({pnl_sign}{pnl_pct_lev:.1f}%)",
        color=TEXT_C, fontsize=10, fontweight="bold", pad=8
    )

    patches = [mpatches.Patch(color=ENTRY_C, label=f"Kirish ${_fmt(entry)}"),
               mpatches.Patch(color=MARK_C, label=f"Mark ${_fmt(mark_price)} {mark_pct}")]
    for i, tp in enumerate(tp_levels, 1):
        lbl = f"TP{i} (80%)" if i == 1 else f"TP{i} (20%)"
        patches.append(mpatches.Patch(color=TP_C, label=f"{lbl} ${_fmt(tp)}"))
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

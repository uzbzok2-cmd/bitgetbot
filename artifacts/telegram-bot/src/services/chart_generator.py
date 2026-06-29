"""
Chart image generator — dark-theme candlestick charts with TP/SL levels.
Returns BytesIO buffer for Telegram send_photo.
Leverage-adjusted profit/loss % shown on chart.
"""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from typing import List, Optional, Tuple
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


def _pct_label(price: float, ref: float, leverage: int = 0) -> str:
    if ref <= 0:
        return ""
    pct = (price - ref) / ref * 100
    sign = "+" if pct >= 0 else ""
    base = f"{sign}{pct:.2f}%"
    if leverage > 1:
        lev_pct = pct * leverage
        lev_sign = "+" if lev_pct >= 0 else ""
        return f"{base}  ({lev_sign}{lev_pct:.1f}% ×{leverage}x)"
    return base


def generate_signal_chart(
    candles_data: list,
    symbol: str,
    direction: str,
    entry: float,
    tp1: float,
    tp2: float = 0,
    sl: float = 0,
    confidence: int = 0,
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
    TP1_C   = "#22c55e"
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

    tp1_pct = _pct_label(tp1, entry, leverage)
    sl_pct  = _pct_label(sl, entry, leverage)

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
    hline(tp1,   TP1_C,   "TP", tp1_pct)
    if sl > 0:
        hline(sl, SL_C, "SL", sl_pct)

    if direction == "LONG":
        ax.axhspan(entry, tp1, alpha=0.06, color=TP1_C)
        if sl > 0:
            ax.axhspan(sl, entry, alpha=0.06, color=SL_C)
    else:
        ax.axhspan(tp1, entry, alpha=0.06, color=TP1_C)
        if sl > 0:
            ax.axhspan(entry, sl, alpha=0.06, color=SL_C)

    all_prices = hi_n + lo_n + [tp1, entry]
    if sl > 0:
        all_prices.append(sl)
    ax.set_xlim(-1, x_right + 16)
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
    lev_part = f"  •  {leverage}x" if leverage > 0 else ""
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  {dir_text}  •  {confidence}% ishonch{lev_part}{dur_part}",
        color=TEXT_C, fontsize=9.5, fontweight="bold", pad=8
    )

    patches = [
        mpatches.Patch(color=ENTRY_C, label=f"Kirish  ${_fmt(entry)}"),
        mpatches.Patch(color=TP1_C,   label=f"TP  ${_fmt(tp1)}  {tp1_pct}"),
    ]
    if sl > 0:
        patches.append(mpatches.Patch(color=SL_C, label=f"SL  ${_fmt(sl)}  {sl_pct}"))
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

    mark_pct = _pct_label(mark_price, entry, leverage)
    hline(entry, ENTRY_C, "Kirish", ls="-", lw=1.5)
    hline(mark_price, MARK_C, "Hozirgi", mark_pct, ls="-", lw=1.5)
    for i, tp in enumerate(tp_levels, 1):
        tp_pct = _pct_label(tp, entry, leverage)
        hline(tp, TP_C, f"TP", tp_pct)
    for sl in sl_levels:
        sl_pct = _pct_label(sl, entry, leverage)
        hline(sl, SL_C, "SL", sl_pct)

    all_prices = hi_n + lo_n + [entry, mark_price] + tp_levels + sl_levels
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_xlim(-1, x_right + 16)
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    pnl_sign = "+" if unrealized_pnl >= 0 else ""
    margin_est = entry if entry > 0 else 1
    pnl_pct_lev = (unrealized_pnl / margin_est * leverage * 100) if margin_est > 0 else 0
    dir_str = "🟢 LONG" if direction in ("long", "LONG") else "🔴 SHORT"
    ax.set_title(
        f"{symbol}  •  1H  |  {dir_str}  {leverage}x  |  PnL: {pnl_sign}{unrealized_pnl:.4f} USDT ({pnl_sign}{pnl_pct_lev:.1f}%)",
        color=TEXT_C, fontsize=9.5, fontweight="bold", pad=8
    )

    patches = [mpatches.Patch(color=ENTRY_C, label=f"Kirish ${_fmt(entry)}"),
               mpatches.Patch(color=MARK_C, label=f"Mark ${_fmt(mark_price)} {mark_pct}")]
    for i, tp in enumerate(tp_levels, 1):
        tp_pct = _pct_label(tp, entry, leverage)
        patches.append(mpatches.Patch(color=TP_C, label=f"TP ${_fmt(tp)} {tp_pct}"))
    for sl in sl_levels:
        sl_pct = _pct_label(sl, entry, leverage)
        patches.append(mpatches.Patch(color=SL_C, label=f"SL ${_fmt(sl)} {sl_pct}"))
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


def generate_zocker_chart(
    candles_data: list,
    symbol: str,
    direction: str,
    consecutive_count: int,
    timeframe: str = "1H",
    entry: float = 0,
    tp: float = 0,
    sl: float = 0,
    leverage: int = 0,
) -> io.BytesIO:
    """Zocker signal chart — consecutive candles highlighted."""
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(60, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]

    BG      = "#0d1117"; GRID   = "#1f2937"
    UP_BODY = "#26a69a"; DN_BODY = "#ef5350"
    WICK    = "#6b7280"; TEXT_C = "#e5e7eb"
    ENTRY_C = "#f59e0b"; TP_C   = "#22c55e"; SL_C = "#ef4444"
    HIGHLIGHT = "#fbbf24"

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(BG)

    w = 0.6
    highlight_start = n - consecutive_count - 1
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color = UP_BODY if c >= o else DN_BODY
        body_lo = min(o, c); body_hi = max(o, c)
        lw = 0
        edge_color = None
        if i >= highlight_start:
            lw = 1.5
            edge_color = HIGHLIGHT
        ax.bar(i, body_hi - body_lo, width=w, bottom=body_lo, color=color,
               linewidth=lw, edgecolor=edge_color if edge_color else color)
        ax.plot([i, i], [l, body_lo], color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h], color=WICK, linewidth=0.8)

    x_right = n + 2

    def hline(price, color, label, pct_str="", ls="--"):
        if price <= 0:
            return
        ax.axhline(price, color=color, linewidth=1.2, linestyle=ls, alpha=0.9)
        lbl = f" {label}: ${_fmt(price)}"
        if pct_str:
            lbl += f"  ({pct_str})"
        ax.text(x_right - 0.5, price, lbl,
                color=color, fontsize=7.5, va="center", ha="left", fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))

    if entry > 0:
        hline(entry, ENTRY_C, "Kirish", ls="-")
    if tp > 0:
        tp_pct = _pct_label(tp, entry, leverage) if entry > 0 else ""
        hline(tp, TP_C, "TP", tp_pct)
    if sl > 0:
        sl_pct = _pct_label(sl, entry, leverage) if entry > 0 else ""
        hline(sl, SL_C, "SL", sl_pct)

    all_prices = hi_n + lo_n
    if entry > 0:
        all_prices += [entry]
    if tp > 0:
        all_prices.append(tp)
    if sl > 0:
        all_prices.append(sl)

    ax.set_xlim(-1, x_right + 16)
    margin = (max(all_prices) - min(all_prices)) * 0.12
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    ax.spines[:].set_color(GRID)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    dir_text = "🟢 XARID IMKONI (6-7 YASHIL)" if direction == "LONG" else "🔴 SOTISH IMKONI (6-7 QIZIL)"
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  {dir_text}  •  {consecutive_count} ta ketma-ket sham",
        color=HIGHLIGHT, fontsize=9.5, fontweight="bold", pad=8
    )

    fig.text(0.99, 0.02,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_spot_portfolio_chart(
    assets: list,
) -> io.BytesIO:
    """Spot portfolio pie chart with profit/loss per asset."""
    if not assets:
        return _empty_chart("SPOT PORTFOLIO")

    BG = "#0d1117"; TEXT_C = "#e5e7eb"; GRID = "#1f2937"
    colors = ["#26a69a", "#ef5350", "#f59e0b", "#60a5fa", "#a78bfa",
              "#34d399", "#fb923c", "#f472b6", "#38bdf8", "#4ade80"]

    labels = [a["coin"] for a in assets]
    sizes  = [max(0.01, abs(a.get("usdt_value", 0.01))) for a in assets]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5), facecolor=BG)
    ax1.set_facecolor(BG); ax2.set_facecolor(BG)

    wedge_colors = [colors[i % len(colors)] for i in range(len(assets))]
    wedges, texts, autotexts = ax1.pie(
        sizes, labels=labels, colors=wedge_colors,
        autopct='%1.1f%%', startangle=90,
        textprops=dict(color=TEXT_C, fontsize=8),
        pctdistance=0.8
    )
    for at in autotexts:
        at.set_color(TEXT_C)
        at.set_fontsize(7)
    ax1.set_title("Portfolio taqsimoti", color=TEXT_C, fontsize=10, fontweight="bold")

    y_pos = range(len(assets))
    pct_values = [a.get("pnl_pct", 0) for a in assets]
    bar_colors = [colors[0] if p >= 0 else colors[1] for p in pct_values]
    bars = ax2.barh(list(y_pos), pct_values, color=bar_colors, height=0.6)
    ax2.set_yticks(list(y_pos))
    ax2.set_yticklabels(labels, color=TEXT_C, fontsize=8)
    ax2.set_xlabel("PnL %", color=TEXT_C, fontsize=8)
    ax2.set_title("Foyda/Zarar %", color=TEXT_C, fontsize=10, fontweight="bold")
    ax2.axvline(0, color=GRID, linewidth=1)
    ax2.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax2.spines.values():
        spine.set_edgecolor(GRID)
    ax2.set_facecolor(BG)
    ax2.xaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)

    for bar, val in zip(bars, pct_values):
        sign = "+" if val >= 0 else ""
        ax2.text(
            bar.get_width() + (0.2 if val >= 0 else -0.2),
            bar.get_y() + bar.get_height() / 2,
            f"{sign}{val:.1f}%",
            color=TEXT_C, fontsize=7, va="center",
            ha="left" if val >= 0 else "right"
        )

    fig.suptitle("SPOT PORTFOLIO TAHLILI", color=TEXT_C, fontsize=11, fontweight="bold", y=1.01)
    fig.text(0.99, 0.01, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.8)
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

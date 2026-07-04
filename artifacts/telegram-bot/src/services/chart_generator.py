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
    """Zocker signal chart — ketma-ket shamlar va TP/SL/Kirish aniq ko'rsatiladi."""
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(60, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]

    BG        = "#0d1117"; GRID    = "#1f2937"
    UP_BODY   = "#26a69a"; DN_BODY = "#ef5350"
    WICK      = "#6b7280"; TEXT_C  = "#e5e7eb"
    ENTRY_C   = "#f59e0b"; TP_C    = "#22c55e"; SL_C = "#ef4444"
    HIGHLIGHT = "#fbbf24"; HALF_HL = "#a78bfa"

    fig, ax = plt.subplots(figsize=(12, 6.5), facecolor=BG)
    ax.set_facecolor(BG)

    # Ketma-ket shamlar joylashuvi
    half_count  = max(1, consecutive_count // 2)
    total_start = n - consecutive_count - 1   # barcha ketma-ket shamlar boshi
    half_start  = n - half_count - 1          # oxirgi yarmi (TP hisoblangan)

    w = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color    = UP_BODY if c >= o else DN_BODY
        body_lo  = min(o, c); body_hi = max(o, c)
        lw, ec   = 0, color

        if i >= half_start:
            # Oxirgi N/2 sham — TP hisoblangan (qo'ng'ir ramka)
            lw = 2.0; ec = HALF_HL
        elif i >= total_start:
            # Birinchi qismi — sariq ramka
            lw = 1.5; ec = HIGHLIGHT

        ax.bar(i, max(body_hi - body_lo, 1e-10), width=w,
               bottom=body_lo, color=color, linewidth=lw, edgecolor=ec)
        ax.plot([i, i], [l, body_lo],  color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h],  color=WICK, linewidth=0.8)

    x_right = n + 2

    def hline(price, color, label, pct_str="", ls="--", lw=1.4):
        if price <= 0:
            return
        ax.axhline(price, color=color, linewidth=lw, linestyle=ls, alpha=0.95)
        lbl = f"  {label}: ${_fmt(price)}"
        if pct_str:
            lbl += f"  ({pct_str})"
        ax.text(x_right, price, lbl,
                color=color, fontsize=8.5, va="center", ha="left", fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor=color, alpha=0.85, pad=2, linewidth=0.8))

    if entry > 0:
        hline(entry, ENTRY_C, "✦ KIRISH", ls="-", lw=2.0)
    if tp > 0:
        tp_pct = _pct_label(tp, entry, leverage) if entry > 0 else ""
        hline(tp, TP_C, "💚 TP", tp_pct, ls="--", lw=1.6)
    if sl > 0:
        sl_pct = _pct_label(sl, entry, leverage) if entry > 0 else ""
        hline(sl, SL_C, "🛑 SL", sl_pct, ls=":", lw=1.6)

    # TP/SL oralig'ini rang bilan to'ldirish
    if entry > 0 and tp > 0 and sl > 0:
        if direction == "LONG":
            ax.axhspan(entry, tp, alpha=0.07, color=TP_C)
            ax.axhspan(sl, entry, alpha=0.07, color=SL_C)
        else:
            ax.axhspan(tp, entry, alpha=0.07, color=TP_C)
            ax.axhspan(entry, sl, alpha=0.07, color=SL_C)

    all_prices = list(hi_n) + list(lo_n)
    if entry > 0: all_prices.append(entry)
    if tp > 0:    all_prices.append(tp)
    if sl > 0:    all_prices.append(sl)

    ax.set_xlim(-1, x_right + 20)
    margin = (max(all_prices) - min(all_prices)) * 0.14
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    ax.spines[:].set_color(GRID)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    dir_lbl  = "🔴 QIZIL" if direction == "LONG" else "🟢 YASHIL"
    dir_act  = "📈 LONG (Xarid)" if direction == "LONG" else "📉 SHORT (Sotish)"
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  {consecutive_count} ta ketma-ket {dir_lbl} sham → {dir_act}",
        color=HIGHLIGHT, fontsize=10, fontweight="bold", pad=10
    )

    # Legend
    patches = []
    if entry > 0:
        patches.append(mpatches.Patch(color=ENTRY_C, label=f"Kirish  ${_fmt(entry)}"))
    if tp > 0:
        tp_pct_lbl = _pct_label(tp, entry, leverage) if entry > 0 else ""
        patches.append(mpatches.Patch(color=TP_C,
            label=f"TP (oxirgi {half_count} sham HIGH)  ${_fmt(tp)}  {tp_pct_lbl}"))
    if sl > 0:
        sl_pct_lbl = _pct_label(sl, entry, leverage) if entry > 0 else ""
        patches.append(mpatches.Patch(color=SL_C, label=f"SL (1:1 RR)  ${_fmt(sl)}  {sl_pct_lbl}"))
    patches.append(mpatches.Patch(color=HIGHLIGHT, label=f"Ketma-ket shamlar ({consecutive_count} ta)"))
    patches.append(mpatches.Patch(color=HALF_HL,   label=f"TP hisoblangan yarmi ({half_count} ta)"))

    if patches:
        ax.legend(handles=patches, loc="upper left", fontsize=7.5,
                  facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

    fig.text(0.99, 0.01,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.6)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, facecolor=BG, bbox_inches="tight")
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


def generate_pattern_chart(
    candles_data: list,
    symbol: str,
    direction: str,
    pattern_name: str,
    entry: float,
    tp: float,
    sl: float,
    confidence: int = 0,
    timeframe: str = "1H",
    pattern_draw: dict = None,
    supports: list = None,
    resistances: list = None,
    nearest_res: float = None,
    nearest_sup: float = None,
    trend: dict = None,
    last_n: int = 80,
) -> io.BytesIO:
    """ZOKPAT pattern chart — trend chiziqlari, S/R zonalari, pattern chizmalari."""
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(symbol)

    n = min(last_n, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]
    offset = len(closes) - n   # index offset for pattern points

    BG       = "#0d1117"; GRID    = "#1f2937"
    UP_BODY  = "#26a69a"; DN_BODY = "#ef5350"
    WICK     = "#6b7280"; TEXT_C  = "#e5e7eb"
    ENTRY_C  = "#f59e0b"; TP_C    = "#22c55e"
    SL_C     = "#ef4444"; PAT_C   = "#a78bfa"
    SR_SUP   = "#34d399"; SR_RES  = "#f87171"
    TREND_UP = "#60a5fa"; TREND_DN = "#fb923c"

    fig, ax = plt.subplots(figsize=(12, 6.5), facecolor=BG)
    ax.set_facecolor(BG)

    w = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color   = UP_BODY if c >= o else DN_BODY
        body_lo = min(o, c); body_hi = max(o, c)
        ax.bar(i, max(body_hi - body_lo, 1e-10), width=w,
               bottom=body_lo, color=color, linewidth=0)
        ax.plot([i, i], [l, body_lo],  color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h],  color=WICK, linewidth=0.8)

    x_right = n + 2

    # ── Trend lines ───────────────────────────────────────────────
    if trend:
        t_offset = trend.get("offset", 0)
        chart_shift = t_offset - offset   # trend x → chart x conversion

        ul = trend.get("upper_line")
        if ul:
            x0c = ul["x0"] + chart_shift
            x1c = ul["x1"] + chart_shift
            # extend to current candle
            x1e = n - 1
            y1e = ul["slope"] * (x1e - chart_shift) + ul["intercept"]
            t_color = TREND_DN if trend.get("direction") == "down" else TREND_UP
            ax.plot([x0c, x1e], [ul["y0"], y1e],
                    color=t_color, linewidth=1.6, linestyle="--",
                    alpha=0.75, zorder=2, label="Trend (yuqori)")

        ll = trend.get("lower_line")
        if ll:
            x0c = ll["x0"] + chart_shift
            x1e = n - 1
            y1e = ll["slope"] * (x1e - chart_shift) + ll["intercept"]
            t_color2 = TREND_UP if trend.get("direction") == "up" else TREND_DN
            ax.plot([x0c, x1e], [ll["y0"], y1e],
                    color=t_color2, linewidth=1.6, linestyle="--",
                    alpha=0.75, zorder=2, label="Trend (pastki)")

        if trend.get("trend_broken"):
            brk_dir = trend.get("break_dir", "")
            brk_txt = f"🔺 Trend yorildi → {brk_dir}"
            ax.text(2, float(max(hi_n)) * 0.998, brk_txt,
                    color=TP_C if brk_dir == "LONG" else SL_C,
                    fontsize=8, fontweight="bold",
                    bbox=dict(facecolor=BG, edgecolor=ENTRY_C, alpha=0.8, pad=2))

    # ── Support / Resistance zones ────────────────────────────────
    price_range = max(hi_n) - min(lo_n)
    zone_h = price_range * 0.005

    for res in (resistances or [])[:4]:
        is_nearest = nearest_res and abs(res - nearest_res) / max(nearest_res, 1e-10) < 0.01
        alpha_span = 0.22 if is_nearest else 0.10
        alpha_line = 0.85 if is_nearest else 0.45
        lw = 1.2 if is_nearest else 0.7
        ax.axhspan(res - zone_h, res + zone_h, alpha=alpha_span, color=SR_RES, zorder=1)
        ax.axhline(res, color=SR_RES, linewidth=lw, linestyle="--", alpha=alpha_line)

    for sup in (supports or [])[:4]:
        is_nearest = nearest_sup and abs(sup - nearest_sup) / max(nearest_sup, 1e-10) < 0.01
        alpha_span = 0.22 if is_nearest else 0.10
        alpha_line = 0.85 if is_nearest else 0.45
        lw = 1.2 if is_nearest else 0.7
        ax.axhspan(sup - zone_h, sup + zone_h, alpha=alpha_span, color=SR_SUP, zorder=1)
        ax.axhline(sup, color=SR_SUP, linewidth=lw, linestyle="--", alpha=alpha_line)

    # ── Pattern-specific lines ────────────────────────────────────
    pd = pattern_draw or {}
    ptype = pd.get("type", "")

    def _idx(raw_idx):
        """Convert raw candle index to chart index."""
        return raw_idx - offset

    def _draw_line(x1, y1, x2, y2, color=PAT_C, lw=1.5, ls="-"):
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, linestyle=ls,
                alpha=0.9, zorder=3)

    def _draw_dot(x, y, color=PAT_C, size=60):
        ax.scatter([x], [y], color=color, s=size, zorder=5, edgecolors="white",
                   linewidths=0.5)

    if ptype == "double_top":
        p1, p2 = _idx(pd["p1"]), _idx(pd["p2"])
        h1, h2 = pd["h1"], pd["h2"]
        neckline = pd["neckline"]
        _draw_dot(p1, h1); _draw_dot(p2, h2)
        _draw_line(p1, h1, p2, h2, ls="--")
        ax.axhline(neckline, color=SR_RES, linewidth=1.4, linestyle="-.", alpha=0.8)
        ax.text(x_right, neckline, " Neckline", color=SR_RES, fontsize=7.5,
                va="center", fontweight="bold")

    elif ptype == "double_bottom":
        t1, t2 = _idx(pd["t1"]), _idx(pd["t2"])
        l1, l2 = pd["l1"], pd["l2"]
        neckline = pd["neckline"]
        _draw_dot(t1, l1); _draw_dot(t2, l2)
        _draw_line(t1, l1, t2, l2, ls="--")
        ax.axhline(neckline, color=SR_SUP, linewidth=1.4, linestyle="-.", alpha=0.8)
        ax.text(x_right, neckline, " Neckline", color=SR_SUP, fontsize=7.5,
                va="center", fontweight="bold")

    elif ptype == "triple_top":
        for pk_key, h_key in [("p1","h1"),("p2","h2"),("p3","h3")]:
            if pk_key in pd:
                _draw_dot(_idx(pd[pk_key]), pd[h_key])
        neckline = pd.get("neckline", 0)
        if neckline:
            ax.axhline(neckline, color=SR_RES, linewidth=1.4, linestyle="-.", alpha=0.8)

    elif ptype == "triple_bottom":
        for tr_key, l_key in [("t1","l1"),("t2","l2"),("t3","l3")]:
            if tr_key in pd:
                _draw_dot(_idx(pd[tr_key]), pd[l_key])
        neckline = pd.get("neckline", 0)
        if neckline:
            ax.axhline(neckline, color=SR_SUP, linewidth=1.4, linestyle="-.", alpha=0.8)

    elif ptype == "hs":
        ls_i, hd_i, rs_i = _idx(pd["ls"]), _idx(pd["hd"]), _idx(pd["rs"])
        _draw_dot(ls_i, pd["h_ls"])
        _draw_dot(hd_i, pd["h_hd"], size=100)
        _draw_dot(rs_i, pd["h_rs"])
        _draw_line(ls_i, pd["h_ls"], hd_i, pd["h_hd"])
        _draw_line(hd_i, pd["h_hd"], rs_i, pd["h_rs"])
        nl = pd.get("neckline", 0)
        if nl:
            ax.axhline(nl, color=SR_RES, linewidth=1.4, linestyle="-.", alpha=0.8)
            ax.text(x_right, nl, " Neckline", color=SR_RES, fontsize=7.5,
                    va="center", fontweight="bold")

    elif ptype == "ihs":
        ls_i, hd_i, rs_i = _idx(pd["ls"]), _idx(pd["hd"]), _idx(pd["rs"])
        _draw_dot(ls_i, pd["l_ls"])
        _draw_dot(hd_i, pd["l_hd"], size=100)
        _draw_dot(rs_i, pd["l_rs"])
        _draw_line(ls_i, pd["l_ls"], hd_i, pd["l_hd"])
        _draw_line(hd_i, pd["l_hd"], rs_i, pd["l_rs"])
        nl = pd.get("neckline", 0)
        if nl:
            ax.axhline(nl, color=SR_SUP, linewidth=1.4, linestyle="-.", alpha=0.8)
            ax.text(x_right, nl, " Neckline", color=SR_SUP, fontsize=7.5,
                    va="center", fontweight="bold")

    elif ptype in ("wedge_rising", "wedge_falling",
                   "triangle_asc", "triangle_desc", "triangle_sym"):
        p1i, p2i = _idx(pd["p1"]), _idx(pd["p2"])
        t1i, t2i = _idx(pd["t1"]), _idx(pd["t2"])
        # Upper trendline (peaks)
        _draw_line(p1i, pd["h_p1"], p2i, pd["h_p2"], color=SR_RES, lw=1.8)
        # Lower trendline (troughs)
        _draw_line(t1i, pd["l_t1"], t2i, pd["l_t2"], color=SR_SUP, lw=1.8)
        # Extend trendlines a bit to the right
        up_slope = (pd["h_p2"] - pd["h_p1"]) / max(pd["p2"] - pd["p1"], 1)
        lo_slope = (pd["l_t2"] - pd["l_t1"]) / max(pd["t2"] - pd["t1"], 1)
        ext = min(15, n - p2i)
        _draw_line(p2i, pd["h_p2"], p2i + ext,
                   pd["h_p2"] + up_slope * ext, color=SR_RES, lw=1.2, ls="--")
        _draw_line(t2i, pd["l_t2"], t2i + ext,
                   pd["l_t2"] + lo_slope * ext, color=SR_SUP, lw=1.2, ls="--")

    # ── TP / SL / ENTRY lines ────────────────────────────────────────
    def hline(price, color, label, pct_str="", ls="--", lw=1.4):
        if price <= 0:
            return
        ax.axhline(price, color=color, linewidth=lw, linestyle=ls, alpha=0.95)
        lbl = f"  {label}: ${_fmt(price)}"
        if pct_str:
            lbl += f"  ({pct_str})"
        ax.text(x_right, price, lbl, color=color, fontsize=8,
                va="center", ha="left", fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor=color, alpha=0.85, pad=2, linewidth=0.7))

    tp_pct = _pct_label(tp, entry) if entry > 0 else ""
    sl_pct = _pct_label(sl, entry) if entry > 0 else ""

    hline(entry, ENTRY_C, "✦ KIRISH", ls="-", lw=2.0)
    hline(tp, TP_C, "💚 TP", tp_pct)
    hline(sl, SL_C, "🛑 SL", sl_pct)

    # TP/SL zones
    if entry > 0 and tp > 0 and sl > 0:
        if direction == "LONG":
            ax.axhspan(entry, tp, alpha=0.07, color=TP_C)
            ax.axhspan(sl, entry, alpha=0.07, color=SL_C)
        else:
            ax.axhspan(tp, entry, alpha=0.07, color=TP_C)
            ax.axhspan(entry, sl, alpha=0.07, color=SL_C)

    # ── Axis limits ──────────────────────────────────────────────────
    all_prices = list(hi_n) + list(lo_n)
    if entry > 0: all_prices.append(entry)
    if tp > 0:    all_prices.append(tp)
    if sl > 0:    all_prices.append(sl)
    margin = (max(all_prices) - min(all_prices)) * 0.14
    ax.set_xlim(-1, x_right + 24)
    ax.set_ylim(min(all_prices) - margin, max(all_prices) + margin)

    ax.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)

    dir_lbl = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  📐 {pattern_name}  →  {dir_lbl}  •  {confidence}% ishonch",
        color=PAT_C, fontsize=10, fontweight="bold", pad=10
    )

    # Legend
    import matplotlib.patches as mpatches
    patches = [
        mpatches.Patch(color=ENTRY_C, label=f"Kirish  ${_fmt(entry)}"),
        mpatches.Patch(color=TP_C,    label=f"TP  ${_fmt(tp)}  {tp_pct}"),
        mpatches.Patch(color=SL_C,    label=f"SL  ${_fmt(sl)}  {sl_pct}"),
        mpatches.Patch(color=PAT_C,   label=f"{pattern_name}"),
    ]
    ax.legend(handles=patches, loc="upper left", fontsize=7.5,
              facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

    fig.text(0.99, 0.01, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.6)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_trend_break_chart(candles_data: list, pat: dict) -> io.BytesIO:
    """W-Pattern (Trend Buzish) chart — 5 nuqta, neckline, TP, SL."""
    timestamps, opens, highs, lows, closes, vols = _make_candles(candles_data)
    if not closes:
        return _empty_chart(pat.get("symbol", "?"))

    symbol    = pat["symbol"]
    timeframe = pat["timeframe"]
    entry     = pat["entry"]
    tp        = pat["tp"]
    sl        = pat["sl"]
    conf      = pat["confidence"]
    neckline  = pat["neckline"]
    window    = pat.get("window", 80)

    p1_idx = pat["p1_idx"]
    p2_idx = pat["p2_idx"]
    p3_idx = pat["p3_idx"]
    p4_idx = pat["p4_idx"]
    p5_idx = pat["p5_idx"]

    BG       = "#0d1117"; GRID   = "#1f2937"
    UP_BODY  = "#26a69a"; DN_BODY = "#ef5350"
    WICK     = "#6b7280"; TEXT_C  = "#e5e7eb"
    ENTRY_C  = "#f59e0b"; TP_C    = "#22c55e"
    SL_C     = "#ef4444"; NECK_C  = "#60a5fa"
    PAT_C    = "#a78bfa"

    # Windowed candles
    n = min(window, len(closes))
    op_n = opens[-n:]; hi_n = highs[-n:]
    lo_n = lows[-n:]; cl_n = closes[-n:]

    fig, ax = plt.subplots(figsize=(12, 6.5), facecolor=BG)
    ax.set_facecolor(BG)
    ax.grid(True, color=GRID, linewidth=0.4, alpha=0.7)
    ax.tick_params(colors=TEXT_C, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)

    # Candlestick
    w_bar = 0.6
    for i, (o, h, l, c) in enumerate(zip(op_n, hi_n, lo_n, cl_n)):
        color   = UP_BODY if c >= o else DN_BODY
        body_lo = min(o, c); body_hi = max(o, c)
        ax.bar(i, max(body_hi - body_lo, 1e-10), width=w_bar,
               bottom=body_lo, color=color, linewidth=0)
        ax.plot([i, i], [l, body_lo],  color=WICK, linewidth=0.8)
        ax.plot([i, i], [body_hi, h],  color=WICK, linewidth=0.8)

    x_right = n + 3

    # Neckline (ko'k gorizontal chiziq — P3 sathida)
    ax.axhline(neckline, color=NECK_C, linewidth=1.5, linestyle="--", alpha=0.9,
               label=f"Neckline  ${_fmt(neckline)}")

    # TP va SL chiziqlar
    ax.axhline(tp, color=TP_C, linewidth=1.4, linestyle="--", alpha=0.85)
    ax.axhline(sl, color=SL_C, linewidth=1.4, linestyle="--", alpha=0.85)

    # Label'lar o'ng tomonga
    ax.text(x_right, tp, f"🎯 TP (0.618)\n${_fmt(tp)}", color=TP_C,
            fontsize=7.5, va="center", fontweight="bold")
    ax.text(x_right, sl, f"🛡 SL\n${_fmt(sl)}", color=SL_C,
            fontsize=7.5, va="center", fontweight="bold")
    ax.text(x_right, entry, f"⚡ Entry\n${_fmt(entry)}", color=ENTRY_C,
            fontsize=7.5, va="center", fontweight="bold")
    ax.text(x_right, neckline, f"🔵 Neck\n${_fmt(neckline)}", color=NECK_C,
            fontsize=7, va="center")

    # 5 ta pattern nuqtasini belgilash
    point_x  = [p1_idx, p2_idx, p3_idx, p4_idx, p5_idx]
    point_y  = [pat["p1_price"], pat["p2_price"],
                pat["p3_price"], pat["p4_price"], pat["p5_price"]]
    offsets  = [  # label offset (up/down)
        (pat["p1_price"], "top",    "#ffffff"),
        (pat["p2_price"], "bottom", "#ffffff"),
        (pat["p3_price"], "top",    "#ffffff"),
        (pat["p4_price"], "bottom", "#ffffff"),
        (pat["p5_price"], "top",    "#22c55e"),
    ]
    labels   = ["①", "②", "③", "④", "⑤"]

    for i, (xi, yi, lbl, (yy, va, clr)) in enumerate(
            zip(point_x, point_y, labels, offsets)):
        ax.scatter(xi, yi, s=55, color=PAT_C, zorder=6)
        ax.text(xi, yy, lbl, color=clr, fontsize=9, ha="center",
                va=va, fontweight="bold",
                bbox=dict(facecolor=BG, alpha=0.7, edgecolor="none", pad=1.5))

    # W-pattern chiziq (1→2→3→4→5)
    xs = point_x
    ys = [pat["p1_price"], pat["p2_price"],
          pat["p3_price"], pat["p4_price"], pat["p5_price"]]
    ax.plot(xs, ys, color=PAT_C, linewidth=1.3, alpha=0.6, linestyle="-")

    # TP zonasi (yashil shading)
    ax.axhspan(entry, tp, alpha=0.06, color=TP_C)
    ax.axhspan(sl, entry, alpha=0.06, color=SL_C)

    # TP/SL %
    tp_pct = f"+{(tp-entry)/entry*100:.2f}%"
    sl_pct = f"-{(entry-sl)/entry*100:.2f}%"

    ax.set_xlim(-1, x_right + 5)
    ax.set_title(
        f"{symbol}  •  {timeframe}  |  🔷 Trend Buzish (W-Pattern)  "
        f"•  🟢 LONG  •  {conf}% ishonch",
        color=PAT_C, fontsize=10, fontweight="bold", pad=10
    )

    import matplotlib.patches as mpatches
    patches = [
        mpatches.Patch(color=NECK_C,  label=f"Neckline ${_fmt(neckline)}"),
        mpatches.Patch(color=ENTRY_C, label=f"Entry ${_fmt(entry)}"),
        mpatches.Patch(color=TP_C,    label=f"TP (0.618) ${_fmt(tp)}  {tp_pct}"),
        mpatches.Patch(color=SL_C,    label=f"SL ${_fmt(sl)}  {sl_pct}"),
        mpatches.Patch(color=PAT_C,   label="W-Pattern (1→2→3→4→5)"),
    ]
    ax.legend(handles=patches, loc="upper left", fontsize=7.5,
              facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C, framealpha=0.9)

    fig.text(0.99, 0.01, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             color="#4b5563", fontsize=6.5, ha="right")

    plt.tight_layout(pad=0.6)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, facecolor=BG, bbox_inches="tight")
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

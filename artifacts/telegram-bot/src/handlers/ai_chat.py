"""
AI Chat — Gemini'siz, o'zimizning pattern_analyzer asosida.
Foydalanuvchi matn yoki rasm yuboradi:
  - Matn: LONG/SHORT + pattern nom → bozorni skan qilib mos chartlarni topadi
  - Rasm: LONG/SHORT tugmalarini bosadi → skan qiladi
"""
import asyncio
import io
import logging
import os
import re
from typing import Optional, List, Tuple, Dict

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message
from telegram.ext import ContextTypes

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bitget_client import BitgetClient
from services.pattern_analyzer import detect_chart_patterns
from services.chart_generator import generate_pattern_chart
from services import state as gs
from services.analyzer import safe_float

logger = logging.getLogger(__name__)

# ── Konstantlar ────────────────────────────────────────────
FALLBACK_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","LTCUSDT","DOTUSDT",
    "LINKUSDT","MATICUSDT","UNIUSDT","ATOMUSDT","NEARUSDT",
    "INJUSDT","ARBUSDT","OPUSDT","AAVEUSDT","SEIUSDT",
]
TF_CANDLES = {"15m": 120, "1H": 120, "4H": 100, "1D": 100}
MIN_VOLUME  = 500_000

# Pattern kalit so'zlari (foydalanuvchi matnidan aniqlash uchun)
PATTERN_KEYWORDS = {
    "Double Top":           ["double top", "ikki cho'qqi", "2 cho'qqi", "w pattern", "m pattern"],
    "Double Bottom":        ["double bottom", "ikki dip", "2 dip", "w formation"],
    "Head & Shoulders":     ["head and shoulders", "head & shoulders", "h&s", "bosh va yelka"],
    "Inv. Head & Shoulders":["inverse head", "inv head", "inv h&s", "teskari bosh"],
    "Rising Wedge":         ["rising wedge", "ko'tariluvchi uchburchak", "yuklanuvchi"],
    "Falling Wedge":        ["falling wedge", "tushuvchi uchburchak", "pastlayuvchi"],
    "Ascending Triangle":   ["ascending triangle", "ko'tariluvchi triangle"],
    "Descending Triangle":  ["descending triangle", "tushuvchi triangle"],
    "Symmetric Triangle":   ["symmetric triangle", "simmetrik triangle", "pennant"],
    "Triple Top":           ["triple top", "uch cho'qqi", "3 cho'qqi"],
    "Triple Bottom":        ["triple bottom", "uch dip", "3 dip"],
    "Breakout":             ["breakout", "yorilish", "break", "yuqoriga chiqish", "pastga tushish"],
}

# ── Matn parsing ────────────────────────────────────────────
def parse_user_text(text: str) -> Dict:
    """Foydalanuvchi matnidan direction, patterns, timeframlarni ajratib oladi."""
    t = text.lower().strip()

    # Direction
    direction = None
    long_words  = ["long", "buy", "yuqori", "ko'tariladi", "buqa", "bull", "ko'tar", "chiqadi", "growth"]
    short_words = ["short", "sell", "past", "tushadi", "ayiq", "bear", "tush", "pastga", "fall"]
    for w in long_words:
        if w in t:
            direction = "LONG"
            break
    if not direction:
        for w in short_words:
            if w in t:
                direction = "SHORT"
                break

    # Patterns
    found_patterns = []
    for pat_name, keywords in PATTERN_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                if pat_name not in found_patterns:
                    found_patterns.append(pat_name)
                break

    # Timeframlar
    scan_tfs = []
    tf_map = {"15m": "15m", "15 m": "15m", "1h": "1H", "4h": "4H", "1d": "1D",
              "1 soat": "1H", "4 soat": "4H", "kunlik": "1D"}
    for k, v in tf_map.items():
        if k in t and v not in scan_tfs:
            scan_tfs.append(v)
    if not scan_tfs:
        scan_tfs = ["1H", "4H"]

    return {
        "direction": direction,
        "patterns": found_patterns,
        "scan_timeframes": scan_tfs,
        "search_direction": direction,
        "min_confidence": 65,
    }


# ── Bozor skan ─────────────────────────────────────────────
async def _get_top_symbols(client: BitgetClient) -> List[str]:
    try:
        d = client.get_futures_tickers()
        if d.get("code") == "00000":
            tickers = [
                t for t in d.get("data", [])
                if str(t.get("symbol","")).endswith("USDT")
                and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME
            ]
            tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
            return [t["symbol"] for t in tickers[:60]]
    except Exception:
        pass
    return FALLBACK_SYMBOLS


async def scan_matching_charts(
    direction: Optional[str],
    target_patterns: List[str],
    scan_tfs: List[str],
    min_conf: int = 65,
    max_results: int = 5
) -> List[Tuple[str, Dict, list]]:
    """Mos keluvchi chartlarni topish. Returns: [(tf, pat_dict, raw_candles), ...]"""
    client  = BitgetClient()
    symbols = await _get_top_symbols(client)
    candidates = []

    for symbol in symbols:
        for tf in scan_tfs:
            try:
                limit   = TF_CANDLES.get(tf, 100)
                candles = client.get_futures_candles(symbol, tf, limit)
                if candles.get("code") != "00000":
                    await asyncio.sleep(0.05)
                    continue
                raw = candles.get("data", [])
                if not raw or len(raw) < 35:
                    continue

                pat = detect_chart_patterns(raw, symbol, tf)
                if not pat:
                    await asyncio.sleep(0.08)
                    continue

                # Direction filtri
                if direction and pat["direction"] != direction:
                    await asyncio.sleep(0.05)
                    continue

                conf = pat["confidence"]
                if conf < min_conf:
                    await asyncio.sleep(0.05)
                    continue

                # Pattern mos kelishini tekshirish
                pat_name = pat["pattern"].lower()
                pat_match = (
                    any(tp.lower() in pat_name or pat_name in tp.lower() for tp in target_patterns)
                    if target_patterns else True
                )
                score = conf + (10 if pat_match else 0)

                # Trend break bonus
                trend = pat.get("trend", {})
                if trend and trend.get("trend_broken") and trend.get("break_dir") == pat["direction"]:
                    score += 8

                candidates.append((score, symbol, tf, pat, raw))
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.debug(f"AI scan {symbol} {tf}: {e}")

    # Har symbol uchun eng yaxshi
    best: Dict[str, tuple] = {}
    for score, symbol, tf, pat, raw in candidates:
        prev = best.get(symbol)
        if prev is None or score > prev[0]:
            best[symbol] = (score, tf, pat, raw)

    ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)
    return [(tf, pat, raw) for _, tf, pat, raw in ranked[:max_results]]


# ── Chart yuborish ──────────────────────────────────────────
async def send_chart_result(bot, chat_id: int, tf: str, pat: Dict, raw: list, idx: int, total: int):
    """Bitta mos chart + tahlilni yuborish."""
    from utils.formatters import fmt_price

    symbol    = pat["symbol"]
    direction = pat["direction"]
    pattern   = pat["pattern"]
    entry     = pat["entry"]
    tp        = pat["tp"]
    sl        = pat["sl"]
    conf      = pat["confidence"]
    trend     = pat.get("trend", {})

    dir_e     = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    trend_dir = trend.get("direction", "sideways") if trend else "sideways"
    trend_ico = {"uptrend": "📈", "downtrend": "📉", "sideways": "➡️"}.get(trend_dir, "➡️")

    broken_txt = ""
    if trend and trend.get("trend_broken") and trend.get("break_dir") == direction:
        broken_txt = "\n⚡ <b>Trend chizig'i yorildi!</b>"

    rr = round(abs(tp - entry) / abs(entry - sl), 2) if abs(entry - sl) > 0 else 0

    caption = (
        f"📊 <b>{idx}/{total} — {symbol} [{tf}]</b>\n"
        f"{'═'*28}\n"
        f"🏷 Pattern: <b>{pattern}</b>\n"
        f"🎯 Signal: {dir_e}\n"
        f"{trend_ico} Trend: <b>{trend_dir}</b>{broken_txt}\n"
        f"📈 Ishonch: <b>{conf}%</b>\n"
        f"{'─'*28}\n"
        f"💵 Kirish: <code>{fmt_price(entry)}</code>\n"
        f"🎯 TP:     <code>{fmt_price(tp)}</code>\n"
        f"🛡 SL:     <code>{fmt_price(sl)}</code>\n"
        f"⚖️ RR:     <b>1:{rr}</b>\n"
    )

    try:
        chart_bytes = generate_pattern_chart(raw, pat)
        if chart_bytes:
            await bot.send_photo(
                chat_id=chat_id,
                photo=chart_bytes,
                caption=caption,
                parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.warning(f"Chart yaratishda xato {symbol}: {e}")

    await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")


# ── Klaviaturalar ───────────────────────────────────────────
def ai_chat_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ AI Chatdan Chiqish", callback_data="ai_chat_exit")],
    ])


def direction_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 LONG (Yuqori)", callback_data="ai_dir_LONG"),
            InlineKeyboardButton("🔴 SHORT (Pastga)", callback_data="ai_dir_SHORT"),
        ],
        [InlineKeyboardButton("🔍 Har Ikkalasi", callback_data="ai_dir_BOTH")],
        [InlineKeyboardButton("❌ Bekor", callback_data="ai_chat_exit")],
    ])


# ── Handlertlar ─────────────────────────────────────────────
async def handle_ai_chat_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'🤖 AI Chat' tugmasi bosilganda."""
    user_id = update.effective_user.id
    if user_id not in gs.authenticated_users:
        return
    gs.ai_chat_users.add(user_id)

    text = (
        "🤖 <b>AI BOZOR SKANERI</b>\n"
        "══════════════════════════════\n\n"
        "📝 <b>Strategiyangizni yozing:</b>\n"
        "<i>Misol: \"Head & Shoulders SHORT signal, 4H da\"</i>\n"
        "<i>Misol: \"LONG breakout triangle 1H\"</i>\n"
        "<i>Misol: \"Double bottom LONG\"</i>\n\n"
        "📸 <b>Yoki chart rasmini yuboring</b> →\n"
        "LONG/SHORT yo'nalishni tanlaysiz → AI skan qiladi\n\n"
        "🔍 <b>Nima qiladi:</b>\n"
        "Barcha USDT futures (top 60) ni skanerlab\n"
        "sizning strategiyangizga mos chartlarni topadi!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📤 <b>Hozir yozing yoki rasm yuboring!</b>\n"
        "🔴 Chiqish: <code>chiq</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=ai_chat_keyboard())


async def handle_ai_chat_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi chart rasm yubordi — LONG/SHORT tanlash."""
    user_id = update.effective_user.id
    if user_id not in gs.ai_chat_users:
        return
    if user_id not in gs.authenticated_users:
        return

    # Rasmni yuklab olamiz (lekin tahlil qilmaymiz — faqat saqlaymiz)
    try:
        photo   = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        buf     = io.BytesIO()
        await tg_file.download_to_memory(buf)
        # context.user_data ga saqlaymiz (keyingi bosqichda ishlatiladi)
        context.user_data["ai_photo"] = True
    except Exception:
        pass

    await update.message.reply_text(
        "📸 <b>Rasm qabul qilindi!</b>\n\n"
        "🎯 Qaysi yo'nalishda skanerlaylik?\n"
        "<i>(Rasmingizda ko'rgan signal yo'nalishini tanlang)</i>",
        parse_mode="HTML",
        reply_markup=direction_keyboard()
    )


async def handle_ai_chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Matnli xabar AI chat modeda."""
    user_id = update.effective_user.id
    if user_id not in gs.ai_chat_users:
        return False

    text = (update.message.text or "").strip()
    t_low = text.lower()

    # Chiqish
    if t_low in ("chiq", "exit", "bekor", "cancel", "❌", "/start"):
        gs.ai_chat_users.discard(user_id)
        await update.message.reply_text("✅ AI Chat'dan chiqdingiz.\nBosh menyuga qaytdingiz.")
        from handlers.main_menu import bottom_reply_keyboard
        await update.message.reply_text(
            "🏠 <b>Bosh menyu</b>", parse_mode="HTML",
            reply_markup=bottom_reply_keyboard()
        )
        return True

    # Matnni tahlil qil
    parsed = parse_user_text(text)
    direction = parsed["direction"]
    patterns  = parsed["patterns"]
    scan_tfs  = parsed["scan_timeframes"]

    if not direction:
        # Direction aniqlanmadi — tanlashini so'rab ask
        context.user_data["ai_text_query"] = text
        await update.message.reply_text(
            f"🤔 <b>Yo'nalish aniqlanmadi</b>\n\n"
            f"Strategiyangiz: <i>«{text[:80]}»</i>\n\n"
            f"Qaysi yo'nalishda skanerlaylik?",
            parse_mode="HTML",
            reply_markup=direction_keyboard()
        )
        return True

    dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    pat_str   = ", ".join(patterns) if patterns else "Barcha patternlar"
    tf_str    = ", ".join(scan_tfs)

    thinking = await update.message.reply_text(
        f"🔍 <b>Skanerlanmoqda...</b>\n\n"
        f"📊 Yo'nalish: {dir_emoji}\n"
        f"🏷 Pattern: <b>{pat_str}</b>\n"
        f"⏱️ Timeframe: <b>{tf_str}</b>\n\n"
        f"<i>Top 60 USDT futures tekshirilmoqda...</i>",
        parse_mode="HTML"
    )

    await _do_scan_and_send(update.message, context, thinking, direction, patterns, scan_tfs)
    return True


async def handle_ai_direction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """LONG/SHORT/BOTH tugmasi bosilganda — skan boshlaydi."""
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in gs.authenticated_users:
        return

    data = query.data  # ai_dir_LONG / ai_dir_SHORT / ai_dir_BOTH

    if data == "ai_dir_BOTH":
        direction = None
        dir_label = "🔍 Har Ikkalasi"
    elif data == "ai_dir_LONG":
        direction = "LONG"
        dir_label = "🟢 LONG"
    else:
        direction = "SHORT"
        dir_label = "🔴 SHORT"

    # Matn query saqlanganmi?
    text_query = context.user_data.pop("ai_text_query", "")
    parsed_patterns = []
    scan_tfs = ["1H", "4H"]
    if text_query:
        p = parse_user_text(text_query)
        parsed_patterns = p["patterns"]
        scan_tfs = p["scan_timeframes"]

    pat_str = ", ".join(parsed_patterns) if parsed_patterns else "Barcha patternlar"

    await query.edit_message_text(
        f"🔍 <b>Skanerlanmoqda...</b>\n\n"
        f"📊 Yo'nalish: {dir_label}\n"
        f"🏷 Pattern: <b>{pat_str}</b>\n"
        f"⏱️ Timeframe: <b>{', '.join(scan_tfs)}</b>\n\n"
        f"<i>Top 60 USDT futures tekshirilmoqda...</i>",
        parse_mode="HTML"
    )

    await _do_scan_and_send(query.message, context, query.message, direction, parsed_patterns, scan_tfs)


async def _do_scan_and_send(
    original_msg, context, thinking_msg,
    direction: Optional[str],
    patterns: List[str],
    scan_tfs: List[str],
):
    """Skan qilib natijalarni yuboradi."""
    try:
        matches = await scan_matching_charts(
            direction=direction,
            target_patterns=patterns,
            scan_tfs=scan_tfs,
            min_conf=65,
            max_results=5
        )
    except Exception as e:
        logger.error(f"AI scan xato: {e}")
        await thinking_msg.edit_text(f"❌ Skan xatosi: {e}")
        return

    if not matches:
        dir_txt = direction or "har ikkalasi"
        pat_txt = ", ".join(patterns) if patterns else "barcha"
        await thinking_msg.edit_text(
            f"🔍 <b>Mos chart topilmadi</b>\n\n"
            f"<b>{dir_txt}</b> yo'nalishda <b>{pat_txt}</b> patterniga\n"
            f"mos kripto topilmadi.\n\n"
            f"💡 <i>5 daqiqadan keyin qayta sinab ko'ring\n"
            f"yoki boshqa pattern/timeframe kiriting.</i>",
            parse_mode="HTML",
            reply_markup=ai_chat_keyboard()
        )
        return

    await thinking_msg.edit_text(
        f"✅ <b>{len(matches)} ta mos chart topildi!</b>\n"
        f"Chartlar tayyorlanmoqda...",
        parse_mode="HTML"
    )

    chat_id = original_msg.chat_id
    for i, (tf, pat, raw) in enumerate(matches, 1):
        await send_chart_result(context.bot, chat_id, tf, pat, raw, i, len(matches))
        await asyncio.sleep(1.0)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>Skan yakunlandi!</b>\n"
            f"📊 {len(matches)} ta mos chart yuborildi.\n\n"
            f"📝 Yangi strategiya yozing yoki rasm yuboring\n"
            f"🔴 Chiqish: <code>chiq</code>"
        ),
        parse_mode="HTML",
        reply_markup=ai_chat_keyboard()
    )

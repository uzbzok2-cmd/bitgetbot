"""
AI Chat — Gemini Vision asosida savdo strategiya tahlili.
Foydalanuvchi chart/strategiya rasmini yuboradi → Gemini tahlil qiladi
→ mos keluvchi kripto chartlarini topib yuboradi.
"""
import asyncio
import io
import json
import logging
import os
import re
from typing import Optional, Dict, List, Tuple

from google import genai
from google.genai import types
from PIL import Image
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

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

FALLBACK_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","LTCUSDT","DOTUSDT",
    "LINKUSDT","MATICUSDT","UNIUSDT","ATOMUSDT","NEARUSDT",
    "INJUSDT","ARBUSDT","OPUSDT","AAVEUSDT","SEIUSDT",
]

TF_CANDLES = {"15m": 120, "1H": 120, "4H": 100, "1D": 100}
MIN_VOLUME  = 500_000

ANALYSIS_PROMPT = """Sen tajribali professional kripto savdo analistisan. Bu rasmda savdo strategiyasi, chart patterni yoki savdo seti-up ko'rsatilgan.

Rasmni juda chuqur professional tahlil qilib, FAQAT quyidagi JSON formatida javob ber (boshqa matn qo'shma):

{
  "patterns": ["Head & Shoulders"],
  "direction": "SHORT",
  "timeframes": ["1H", "4H"],
  "trend": "downtrend",
  "key_features": ["resistance rejection", "lower highs", "neckline break"],
  "entry_condition": "neckline yorilgandan keyin SHORT",
  "signal_type": "reversal",
  "confidence": 80,
  "analysis_uz": "Bu rasmda Head & Shoulders patterni ko'rinmoqda. Narx uch bor resistance da to'xtadi. Neckline yorilishi SHORT signalni tasdiqlaydi.",
  "search_direction": "SHORT",
  "min_confidence": 68,
  "scan_timeframes": ["1H", "4H"]
}

Qoidalar:
- patterns ro'yxati: Double Top, Double Bottom, Triple Top, Triple Bottom, Head & Shoulders, Inv. Head & Shoulders, Rising Wedge, Falling Wedge, Ascending Triangle, Descending Triangle, Symmetric Triangle
- direction: faqat "LONG" yoki "SHORT"  
- trend: "uptrend", "downtrend" yoki "sideways"
- signal_type: "reversal", "continuation" yoki "breakout"
- scan_timeframes: skanerlanadigan timeframlar ro'yxati ["15m","1H","4H","1D"] dan
- min_confidence: 65-85 orasida
- analysis_uz: O'zbek tilida 2-3 gap, JUDA aniq va professional tahlil
- FAQAT JSON qaytargil"""


def _gemini_client() -> Optional[genai.Client]:
    if not GEMINI_KEY:
        return None
    try:
        return genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        logger.error(f"Gemini client xato: {e}")
        return None


def _parse_gemini_text(text: str) -> Optional[Dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def analyze_image_with_gemini(photo_bytes: bytes) -> Optional[Dict]:
    """Gemini Vision orqali chart/strategiya rasmini tahlil qilish."""
    client = _gemini_client()
    if not client:
        return None
    try:
        img = Image.open(io.BytesIO(photo_bytes))
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[ANALYSIS_PROMPT, img],
            )
        )
        data = _parse_gemini_text(response.text)
        logger.info(f"Gemini tahlil: {data.get('direction')} | {data.get('patterns')} | tf={data.get('scan_timeframes')}")
        return data
    except Exception as e:
        logger.error(f"Gemini analysis xato: {e}")
        return None


async def analyze_text_with_gemini(user_text: str) -> Optional[Dict]:
    """Matn tavsifi orqali strategiya tahlili."""
    client = _gemini_client()
    if not client:
        return None
    prompt = (
        f"Foydalanuvchi bu savdo strategiyasini tasvirlab berdi:\n\n\"{user_text}\"\n\n"
        + ANALYSIS_PROMPT
    )
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt],
            )
        )
        return _parse_gemini_text(response.text)
    except Exception as e:
        logger.error(f"Gemini text analysis xato: {e}")
        return None


async def _get_top_symbols(client: BitgetClient) -> List[str]:
    try:
        d = client.get_futures_tickers()
        if d.get("code") == "00000":
            tickers = [
                t for t in d.get("data", [])
                if str(t.get("symbol", "")).endswith("USDT")
                and safe_float(t.get("usdtVolume", 0)) >= MIN_VOLUME
            ]
            tickers.sort(key=lambda x: safe_float(x.get("usdtVolume", 0)), reverse=True)
            return [t["symbol"] for t in tickers[:60]]
    except Exception:
        pass
    return FALLBACK_SYMBOLS


async def scan_matching_charts(
    gemini_result: Dict,
    max_results: int = 5
) -> List[Tuple[str, str, Dict, list]]:
    """
    Gemini tahlili asosida mos keluvchi chartlarni topish.
    Returns: [(symbol, tf, pattern_dict, raw_candles), ...]
    """
    direction    = gemini_result.get("search_direction", gemini_result.get("direction", ""))
    scan_tfs     = gemini_result.get("scan_timeframes", ["1H", "4H"])
    min_conf     = int(gemini_result.get("min_confidence", 68))
    target_pats  = [p.lower() for p in gemini_result.get("patterns", [])]

    client   = BitgetClient()
    symbols  = await _get_top_symbols(client)

    candidates: List[Tuple[float, str, str, Dict, list]] = []

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
                    await asyncio.sleep(0.08)
                    continue

                conf = pat["confidence"]
                if conf < min_conf:
                    await asyncio.sleep(0.08)
                    continue

                # Pattern mos kelishini tekshirish (bonus score)
                pat_name = pat["pattern"].lower()
                pat_match = any(tp in pat_name or pat_name in tp for tp in target_pats) if target_pats else True
                score = conf + (10 if pat_match else 0)

                # Trend break bonus
                trend = pat.get("trend", {})
                if trend and trend.get("trend_broken") and trend.get("break_dir") == pat["direction"]:
                    score += 8

                candidates.append((score, symbol, tf, pat, raw))
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.debug(f"AI scan {symbol} {tf}: {e}")

    # Har symbol uchun faqat eng yaxshi
    best: Dict[str, Tuple] = {}
    for score, symbol, tf, pat, raw in candidates:
        prev = best.get(symbol)
        if prev is None or score > prev[0]:
            best[symbol] = (score, tf, pat, raw)

    ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)
    return [(tf, pat, raw) for _, tf, pat, raw in ranked[:max_results]]


async def send_chart_result(
    bot, chat_id: int,
    tf: str, pat: Dict, raw: list,
    idx: int, total: int
):
    """Bitta mos chart + tahlilni yuborish."""
    from utils.formatters import fmt_price, _pct_lev

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
    if trend and trend.get("trend_broken"):
        broken_txt = f"\n🔺 <b>Trend yorildi!</b> → {trend.get('break_dir','')}"

    sl_dist   = abs(sl - entry)
    tp_dist   = abs(tp - entry)
    rr        = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 1.0
    tp_pct    = tp_dist / entry * 100 if entry > 0 else 0
    sl_pct    = sl_dist / entry * 100 if entry > 0 else 0

    nearest_res = pat.get("nearest_res")
    nearest_sup = pat.get("nearest_sup")

    text = (
        f"🤖 <b>AI TOPILDI {idx}/{total}</b>\n{'═'*26}\n"
        f"💎 <b>{symbol}</b> — {dir_e}\n"
        f"📐 Pattern: <b>{pattern}</b>\n"
        f"⏱️ Timeframe: <b>{tf}</b>\n"
        f"🎯 Ishonch: <b>{conf}%</b>\n"
        f"{trend_ico} Trend: <b>{trend_dir}</b>{broken_txt}\n"
        f"{'─'*26}\n"
        f"💲 Kirish: <code>${fmt_price(entry)}</code>\n"
    )
    if nearest_res:
        text += f"🔴 Eng yaqin Resistance: <code>${fmt_price(nearest_res)}</code>\n"
    if nearest_sup:
        text += f"🟢 Eng yaqin Support: <code>${fmt_price(nearest_sup)}</code>\n"
    text += (
        f"{'─'*26}\n"
        f"💚 TP: <code>${fmt_price(tp)}</code>  (+{tp_pct:.2f}%)\n"
        f"🛑 SL: <code>${fmt_price(sl)}</code>  (-{sl_pct:.2f}%)\n"
        f"⚖️ Risk/Reward: <b>1:{rr}</b>\n"
    )
    if rr >= 1.5:
        text += "✨ <i>Ajoyib R:R nisbat!</i>\n"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💰 Qo'lda Kirish", callback_data=f"manual_trade_{symbol}")
    ]])

    try:
        buf = generate_pattern_chart(
            candles_data=raw, symbol=symbol,
            direction=direction, pattern_name=pattern,
            entry=entry, tp=tp, sl=sl, confidence=conf,
            timeframe=tf, pattern_draw=pat.get("draw", {}),
            supports=pat.get("supports", []),
            resistances=pat.get("resistances", []),
            nearest_res=nearest_res,
            nearest_sup=nearest_sup,
            trend=trend,
        )
        await bot.send_photo(
            chat_id=chat_id, photo=buf,
            caption=f"🤖 {symbol} {tf} | {pattern} | {dir_e} | {conf}%",
        )
    except Exception as e:
        logger.warning(f"AI chart xato {symbol}: {e}")

    try:
        await bot.send_message(chat_id=chat_id, text=text,
                               parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.error(f"AI send xato: {e}")


def ai_chat_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ AI Chatdan Chiqish", callback_data="ai_chat_exit")],
    ])


async def handle_ai_chat_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'🤖 AI Chat' tugmasi bosilganda."""
    user_id = update.effective_user.id
    if user_id not in gs.authenticated_users:
        return
    gs.ai_chat_users.add(user_id)

    if not GEMINI_KEY:
        await update.message.reply_text(
            "❌ <b>GEMINI_API_KEY</b> topilmadi.\n"
            "Replit Secrets ichiga <code>GEMINI_API_KEY</code> qo'shing.",
            parse_mode="HTML"
        )
        return

    text = (
        "🤖 <b>AI CHAT — STRATEGIYA TAHLILI</b>\n"
        "══════════════════════════════\n\n"
        "📸 <b>Qanday ishlaydi:</b>\n"
        "1️⃣ Savdo strategiyasi yoki chart rasmini yuboring\n"
        "2️⃣ AI rasmni tahlil qiladi (pattern, direction, trend)\n"
        "3️⃣ Barcha kripto bozorlarini skanerlab mos chartlarni topadi\n"
        "4️⃣ Trend chiziqlari va breakout tahminlari bilan chartlarni yuboradi\n\n"
        "💡 <b>Yoki matn bilan ham:</b>\n"
        "<i>\"Head & Shoulders SHORT signal, 4H da neckline yorilishi\"</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📤 <b>Hozir rasm yoki matn yuboring!</b>\n"
        "🔴 Chiqish uchun: <code>chiq</code>"
    )
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=ai_chat_keyboard()
    )


async def handle_ai_chat_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi rasm yubordi — AI tahlili."""
    user_id = update.effective_user.id
    if user_id not in gs.ai_chat_users:
        return
    if user_id not in gs.authenticated_users:
        return

    msg: Message = update.message
    thinking = await msg.reply_text(
        "🧠 <b>Gemini AI rasmni tahlil qilmoqda...</b>\n"
        "<i>Strategiyani o'qiyapman...</i>",
        parse_mode="HTML"
    )

    try:
        photo  = msg.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        buf    = io.BytesIO()
        await tg_file.download_to_memory(buf)
        photo_bytes = buf.getvalue()
    except Exception as e:
        await thinking.edit_text(f"❌ Rasm yuklab bo'lmadi: {e}")
        return

    gemini_result = await analyze_image_with_gemini(photo_bytes)

    if not gemini_result:
        await thinking.edit_text(
            "❌ <b>Gemini tahlil qilolmadi.</b>\n"
            "Iltimos, aniqroq chart rasm yuboring.",
            parse_mode="HTML"
        )
        return

    direction  = gemini_result.get("direction", "?")
    patterns   = ", ".join(gemini_result.get("patterns", ["Noma'lum"]))
    analysis   = gemini_result.get("analysis_uz", "")
    trend      = gemini_result.get("trend", "sideways")
    tfs        = ", ".join(gemini_result.get("scan_timeframes", ["1H", "4H"]))
    conf_gemini = gemini_result.get("confidence", 0)
    signal_type = gemini_result.get("signal_type", "reversal")
    entry_cond  = gemini_result.get("entry_condition", "")

    dir_e = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    trend_icons = {"uptrend": "📈", "downtrend": "📉", "sideways": "➡️"}
    trend_ico = trend_icons.get(trend, "➡️")

    summary = (
        f"🤖 <b>GEMINI AI TAHLILI</b>\n{'═'*26}\n"
        f"📐 Pattern: <b>{patterns}</b>\n"
        f"🎯 Yo'nalish: {dir_e}\n"
        f"{trend_ico} Trend: <b>{trend}</b>\n"
        f"📊 Signal turi: <b>{signal_type}</b>\n"
        f"⏱️ Timeframlar: <b>{tfs}</b>\n"
        f"🎲 AI ishonch: <b>{conf_gemini}%</b>\n"
    )
    if entry_cond:
        summary += f"🔑 Kirish sharti: <i>{entry_cond}</i>\n"
    if analysis:
        summary += f"{'─'*26}\n💬 <i>{analysis}</i>\n"
    summary += f"{'─'*26}\n🔍 <b>Mos kripto chartlar izlanmoqda...</b>"

    await thinking.edit_text(summary, parse_mode="HTML")

    scan_msg = await msg.reply_text(
        f"⏳ <b>Skanerlanmoqda...</b>\n"
        f"Barcha USDT futures da {direction} signali qidirilmoqda...",
        parse_mode="HTML"
    )

    try:
        matches = await scan_matching_charts(gemini_result, max_results=5)
    except Exception as e:
        logger.error(f"AI scan xato: {e}")
        await scan_msg.edit_text(f"❌ Skan xatosi: {e}")
        return

    if not matches:
        await scan_msg.edit_text(
            f"🔍 <b>Mos chart topilmadi</b>\n"
            f"Hozirda {direction} yo'nalishda <b>{patterns}</b> patterniga "
            f"mos kripto topilmadi.\n\n"
            f"5 daqiqadan keyin qayta sinab ko'ring.",
            parse_mode="HTML"
        )
        return

    await scan_msg.edit_text(
        f"✅ <b>{len(matches)} ta mos chart topildi!</b>\n"
        f"Chartlar tayorlanmoqda...",
        parse_mode="HTML"
    )

    chat_id = msg.chat_id
    for i, (tf, pat, raw) in enumerate(matches, 1):
        await send_chart_result(context.bot, chat_id, tf, pat, raw, i, len(matches))
        await asyncio.sleep(1.0)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>AI tahlil yakunlandi!</b>\n"
            f"📊 {len(matches)} ta mos chart yuborildi.\n\n"
            f"📸 Yangi strategiya rasmini yuboring\n"
            f"yoki <code>chiq</code> deb yozing."
        ),
        parse_mode="HTML",
        reply_markup=ai_chat_keyboard()
    )


async def handle_ai_chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Matnli xabar AI chat modeda — strategiya tavsifi yoki 'chiq'.
    Returns True if handled (user was in AI chat mode).
    """
    user_id = update.effective_user.id
    if user_id not in gs.ai_chat_users:
        return False

    text = (update.message.text or "").strip().lower()

    if text in ("chiq", "exit", "bekor", "cancel", "❌", "/start"):
        gs.ai_chat_users.discard(user_id)
        await update.message.reply_text(
            "✅ AI Chat'dan chiqdingiz.\nBosh menyuga qaytdingiz.",
            parse_mode="HTML"
        )
        from handlers.main_menu import bottom_reply_keyboard
        await update.message.reply_text(
            "🏠 <b>Bosh menyu</b>",
            parse_mode="HTML",
            reply_markup=bottom_reply_keyboard()
        )
        return True

    # Matn orqali strategiya tavsifi
    thinking = await update.message.reply_text(
        "🧠 <b>AI strategiyangizni tahlil qilmoqda...</b>",
        parse_mode="HTML"
    )

    gemini_result = await analyze_text_with_gemini(update.message.text)
    if not gemini_result:
        await thinking.edit_text(
            "❌ Tahlil qilolmadim. Iltimos, strategiyani aniqroq tasvirlab yuboring\n"
            "yoki chart rasmini yuboring.",
            parse_mode="HTML"
        )
        return True

    direction = gemini_result.get("direction", "?")
    patterns  = ", ".join(gemini_result.get("patterns", []))
    analysis  = gemini_result.get("analysis_uz", "")
    dir_e     = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"

    await thinking.edit_text(
        f"🤖 <b>AI Tahlil:</b>\n"
        f"📐 Pattern: <b>{patterns}</b>\n"
        f"🎯 Yo'nalish: {dir_e}\n"
        f"{'─'*20}\n{analysis}\n\n"
        f"🔍 Mos chartlar izlanmoqda...",
        parse_mode="HTML"
    )

    try:
        matches = await scan_matching_charts(gemini_result, max_results=5)
    except Exception as e:
        await update.message.reply_text(f"❌ Skan xatosi: {e}")
        return True

    if not matches:
        await update.message.reply_text(
            f"🔍 {direction} yo'nalishda mos chart topilmadi.",
            parse_mode="HTML"
        )
        return True

    chat_id = update.message.chat_id
    await update.message.reply_text(
        f"✅ {len(matches)} ta mos chart topildi!", parse_mode="HTML"
    )
    for i, (tf, pat, raw) in enumerate(matches, 1):
        await send_chart_result(context.bot, chat_id, tf, pat, raw, i, len(matches))
        await asyncio.sleep(1.0)

    return True


async def handle_ai_chat_exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline 'Chiqish' tugmasi."""
    query = update.callback_query
    user_id = query.from_user.id
    gs.ai_chat_users.discard(user_id)
    await query.answer("✅ AI Chat'dan chiqdingiz!")
    await query.edit_message_text(
        "✅ <b>AI Chat'dan chiqdingiz.</b>\n"
        "Bosh menyudan davom eting.",
        parse_mode="HTML"
    )

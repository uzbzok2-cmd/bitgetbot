"""Sozlamalar — balans foizi va boshqa sozlamalar."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import state as gs
from services.bitget_client import BitgetClient
from services.analyzer import safe_float

client = BitgetClient()


def settings_keyboard():
    pct = gs.trade_balance_pct
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖ 1%", callback_data="set_bal_pct_dec1"),
            InlineKeyboardButton(f"📊 {pct:.1f}%", callback_data="settings_noop"),
            InlineKeyboardButton("➕ 1%", callback_data="set_bal_pct_inc1"),
        ],
        [
            InlineKeyboardButton("➖ 5%", callback_data="set_bal_pct_dec5"),
            InlineKeyboardButton("🔄 Reset (5%)", callback_data="set_bal_pct_reset"),
            InlineKeyboardButton("➕ 5%", callback_data="set_bal_pct_inc5"),
        ],
        [InlineKeyboardButton("✅ Saqlash", callback_data="settings_save"),
         InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
    ])


async def _show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    try:
        acc = client.get_futures_account()
        if acc.get("code") == "00000":
            equity    = safe_float(acc["data"].get("usdtEquity", 0))
            available = safe_float(acc["data"].get("available", 0))
        else:
            equity = available = 0.0
    except Exception:
        equity = available = 0.0

    pct      = gs.trade_balance_pct
    order_est = available * pct / 100.0

    text = (
        f"⚙️ <b>SOZLAMALAR</b>\n"
        f"{'═'*28}\n\n"
        f"💼 <b>Hisob ma'lumotlari:</b>\n"
        f"├ Kapital:   <code>{equity:.2f} USDT</code>\n"
        f"└ Erkin:     <code>{available:.2f} USDT</code>\n\n"
        f"📊 <b>Har bir avtosavdo uchun balans foizi:</b>\n"
        f"├ Hozir:     <b>{pct:.1f}%</b>\n"
        f"├ Har birga: <code>~{order_est:.2f} USDT</code>\n"
        f"└ (maks $5 limitda)\n\n"
        f"{'─'*28}\n"
        f"⬇️ Foizni quyida o'zgartiring:\n"
        f"<i>Min: 1% | Max: 50%</i>"
    )
    kb = settings_keyboard()

    if edit:
        query = update.callback_query
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    else:
        msg = update.message
        await msg.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def handle_settings_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_settings(update, context, edit=False)


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    if data == "settings_noop":
        await query.answer()
        return

    if data == "set_bal_pct_inc1":
        gs.trade_balance_pct = min(50.0, gs.trade_balance_pct + 1.0)
        await query.answer(f"✅ {gs.trade_balance_pct:.1f}%")
    elif data == "set_bal_pct_dec1":
        gs.trade_balance_pct = max(1.0, gs.trade_balance_pct - 1.0)
        await query.answer(f"✅ {gs.trade_balance_pct:.1f}%")
    elif data == "set_bal_pct_inc5":
        gs.trade_balance_pct = min(50.0, gs.trade_balance_pct + 5.0)
        await query.answer(f"✅ {gs.trade_balance_pct:.1f}%")
    elif data == "set_bal_pct_dec5":
        gs.trade_balance_pct = max(1.0, gs.trade_balance_pct - 5.0)
        await query.answer(f"✅ {gs.trade_balance_pct:.1f}%")
    elif data == "set_bal_pct_reset":
        gs.trade_balance_pct = 5.0
        await query.answer("🔄 Reset: 5%")
    elif data == "settings_save":
        await query.answer(f"✅ Saqlandi: {gs.trade_balance_pct:.1f}%")

    await _show_settings(update, context, edit=True)

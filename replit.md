# BitgetBot — AI Crypto Trading Bot

Telegram orqali Bitget birjasida avtomatik savdo qiladigan AI bot. Fyuchers va Spot bo'limlari bor, texnik indikatorlar asosida signal beradi va o'zi savdo qiladi.

## Run & Operate

- `python artifacts/telegram-bot/src/bot.py` — Telegram botni ishga tushirish
- `pnpm --filter @workspace/api-server run dev` — API server (port 5000)
- `pnpm run typecheck` — TypeScript tekshiruvi
- Required env: `TELEGRAM_BOT_TOKEN`, `BITGET_API_KEY`, `BITGET_API_SECRET`, `BITGET_API_PASSPHRASE`

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9 (API server)
- **Telegram Bot:** Python 3.11 + python-telegram-bot 20.7
- **Bitget API:** Custom HMAC-SHA256 signed REST client (v2 API)
- **Analyzer:** Custom RSI, MACD, EMA, ADX, ATR, Supertrend, Bollinger, Stochastic, SMC
- **Background trading:** asyncio concurrent scanner (5 min interval)
- API: Express 5
- DB: PostgreSQL + Drizzle ORM

## Where things live

- `artifacts/telegram-bot/src/bot.py` — Main entry point
- `artifacts/telegram-bot/src/config.py` — All config constants
- `artifacts/telegram-bot/src/services/bitget_client.py` — Bitget API client (Futures + Spot)
- `artifacts/telegram-bot/src/services/analyzer.py` — Multi-indicator signal engine
- `artifacts/telegram-bot/src/services/trading_engine.py` — Auto-trading engine
- `artifacts/telegram-bot/src/services/github_sync.py` — GitHub auto-sync (30 min)
- `artifacts/telegram-bot/src/handlers/` — Telegram button handlers
- `artifacts/telegram-bot/src/utils/formatters.py` — Message formatters

## Architecture decisions

- Bot uses Bitget v2 REST API with HMAC-SHA256 signing (not SDK — more control)
- Custom indicator implementations (no TA-Lib dependency issues)
- Cross margin mode + max leverage per symbol automatically detected
- Commission-adjusted TP/SL: taker fee 0.06% × leverage factored into 1:1 RR
- GitHub auto-sync every 30 minutes via background asyncio task
- Bot notifies user via Telegram on every auto-trade

## Product

- /start — Bosh menyu, 2 ta bo'lim: Fyuchers va Spot
- Fyuchers: Balans, Ochiq Pozitsiyalar, Faol Orderlar, TP/SL, Tarix, Top Signallar
- Spot: Balans, Kripto Balansi (narx+foiz), Faol Orderlar, Tarix
- AI avtomatik 5 daqiqada bozorni skanerlab signal topadi
- Signal ≥70% ishonch bo'lsa, avtomatik order ochadi va Telegram'ga xabar yuboradi
- TP×2 (50%+50%), SL×1, 1:1 RR (komissiya hisoblab)

## User preferences

- Uzbek tili — barcha xabarlar o'zbek tilida
- Emoji ishlatilsin, muhim narsalar bold qilinsin
- Har bir o'zgarish GitHub bitgetbot repo'siga saqlansin (avtomatik 30 daqiqada)
- USDT-M Perpetual Futures, Cross marja, maksimal leverage
- Qisqa muddatli savdo: 1-48 soat

## Gotchas

- Bitget v2 API: futures account endpoint `/api/v2/mix/account/accounts` (not `/account`)
- `marginCoin` parametri ba'zi endpointlarda majburiy
- GitHub push Replit sandbox'da faqat bot process orqali mumkin (not main agent bash)
- Bot avval Telegram polling'ni boshlaydi, keyin background trading ishga tushadi
- Signal threshold: 55 points minimum score out of ~111 possible

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details

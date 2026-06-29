---
name: Python bot in pnpm workspace
description: How Python 3.11 Telegram bot is structured alongside Node.js monorepo
---

## Setup

- Python 3.11 installed via `installProgrammingLanguage({ language: "python-3.11" })`
- Packages installed via `installLanguagePackages` using uv (not pip)
- Bot lives at `artifacts/telegram-bot/src/bot.py`
- Workflow name: `"Telegram Bot"`, command: `python artifacts/telegram-bot/src/bot.py`, outputType: `"console"`

## Structure

```
artifacts/telegram-bot/src/
  bot.py              — main entry, Application builder + post_init background tasks
  config.py           — all constants from env vars
  handlers/           — callback_router.py routes all InlineKeyboard presses
  services/           — bitget_client.py, analyzer.py, trading_engine.py, github_sync.py
  utils/              — formatters.py (all message formatting)
```

**Why:** Telegram bots must be Python for python-telegram-bot library. Node.js/TS API server stays for any REST API needs. Both coexist in pnpm monorepo — Python bot is just not a pnpm package.

**How to apply:** When modifying the bot, always restart "Telegram Bot" workflow after changes. Use `sys.path.insert(0, parent_dir)` in each file for imports.

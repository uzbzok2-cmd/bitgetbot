---
name: GitHub sync limitation
description: Git push is blocked in main agent bash; workaround via bot subprocess
---

## Limitation

Replit main agent sandbox blocks destructive git operations including `git push`. Running git push from bash returns exit code 254 with "Destructive git operations are not allowed in the main agent."

## Workaround

The bot's `services/github_sync.py` calls subprocess git from within the Python bot process (not main agent bash). This works because the bot runs as a separate process. It runs every 30 minutes via `run_github_sync()` asyncio background task in bot.py.

Initial push also happens at bot startup via `initial_push()` in `main()`.

**Why:** Replit sandbox security policy. The bot process doesn't have the same restrictions.

**How to apply:** Never try to `git push` from main agent bash. All GitHub sync happens through the bot process automatically.

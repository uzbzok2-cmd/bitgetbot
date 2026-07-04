"""GitHub sync — GitHub REST API orqali fayllarni push qiladi (subprocess git yo'q)."""
import os
import base64
import logging
import asyncio
import aiohttp
import time
from pathlib import Path

logger = logging.getLogger(__name__)

GITHUB_USERNAME = "uzbzok2-cmd"
GITHUB_REPO = "bitgetbot"
GITHUB_BRANCH = "main"
WORKSPACE = Path("/home/runner/workspace")

BOT_FILES = [
    "artifacts/telegram-bot/src/bot.py",
    "artifacts/telegram-bot/src/config.py",
    "artifacts/telegram-bot/src/handlers/main_menu.py",
    "artifacts/telegram-bot/src/handlers/callback_router.py",
    "artifacts/telegram-bot/src/handlers/trading_status.py",
    "artifacts/telegram-bot/src/handlers/futures2_handlers.py",
    "artifacts/telegram-bot/src/handlers/ai_chat.py",
    "artifacts/telegram-bot/src/handlers/zocker_signal.py",
    "artifacts/telegram-bot/src/handlers/zokpat_scanner.py",
    "artifacts/telegram-bot/src/handlers/trend_break_scanner.py",
    "artifacts/telegram-bot/src/services/analyzer.py",
    "artifacts/telegram-bot/src/services/bitget_client.py",
    "artifacts/telegram-bot/src/services/chart_generator.py",
    "artifacts/telegram-bot/src/services/github_sync.py",
    "artifacts/telegram-bot/src/services/pattern_analyzer.py",
    "artifacts/telegram-bot/src/services/state.py",
    "artifacts/telegram-bot/src/services/trading_engine.py",
    "artifacts/telegram-bot/src/utils/formatters.py",
]


def _get_token():
    return os.environ.get("GITHUB_TOKEN", "")


async def _get_file_sha(session: aiohttp.ClientSession, token: str, path: str) -> str | None:
    """GitHub'dagi fayl SHA sini oladi (mavjud bo'lsa)."""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("sha")
    except Exception:
        pass
    return None


async def _push_file(session: aiohttp.ClientSession, token: str, rel_path: str, message: str) -> bool:
    """Bitta faylni GitHub'ga push qiladi."""
    local_path = WORKSPACE / rel_path
    if not local_path.exists():
        return False

    try:
        content = local_path.read_bytes()
        encoded = base64.b64encode(content).decode()
    except Exception as e:
        logger.warning(f"Fayl o'qilmadi {rel_path}: {e}")
        return False

    sha = await _get_file_sha(session, token, rel_path)

    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{rel_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    payload = {
        "message": message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        async with session.put(url, headers=headers, json=payload) as resp:
            if resp.status in (200, 201):
                return True
            else:
                text = await resp.text()
                logger.warning(f"Push xato {rel_path}: {resp.status} — {text[:200]}")
                return False
    except Exception as e:
        logger.warning(f"Push exception {rel_path}: {e}")
        return False


async def push_all_files(message: str = None):
    """Barcha bot fayllarini GitHub'ga push qiladi."""
    token = _get_token()
    if not token:
        logger.warning("GITHUB_TOKEN yo'q — push o'tkazib yuborildi")
        return False

    msg = message or f"🤖 BitgetBot update — {time.strftime('%Y-%m-%d %H:%M')}"
    success = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        for rel_path in BOT_FILES:
            ok = await _push_file(session, token, rel_path, msg)
            if ok:
                success += 1
            else:
                failed += 1
            await asyncio.sleep(0.3)  # Rate limit uchun

    logger.info(f"✅ GitHub push tugadi: {success} ta muvaffaqiyatli, {failed} ta xato")
    return success > 0


def commit_and_push(message: str = None):
    """Sync wrapper (bot.py initial_push uchun)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_all_files(message))
            return True
        else:
            return loop.run_until_complete(push_all_files(message))
    except Exception as e:
        logger.error(f"commit_and_push xato: {e}")
        return False


def setup_git_repo():
    """Eski git-based setup — endi kerak emas, API ishlatamiz."""
    logger.info("GitHub API sync yoqilgan (subprocess git yo'q)")
    return True


def initial_push():
    """Botni ishga tushirganda dastlabki push."""
    setup_git_repo()
    return commit_and_push("🔮 ZOKPAT scanner, AI Chat, FYUCHERS 2 — BitgetBot AI v2.0")


async def run_periodic_sync():
    """30 daqiqada bir marta GitHub'ga push qiladi."""
    await asyncio.sleep(60)  # Birinchi 1 daqiqada push
    while True:
        try:
            await push_all_files()
        except Exception as e:
            logger.error(f"Periodic sync xato: {e}")
        await asyncio.sleep(1800)  # 30 daqiqa

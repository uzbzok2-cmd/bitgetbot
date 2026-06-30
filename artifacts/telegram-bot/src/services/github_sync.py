"""GitHub sync service — commits changes to bitgetbot repo."""
import os
import subprocess
import logging
import time
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO

logger = logging.getLogger(__name__)

BOT_DIR = Path(__file__).parent.parent.parent


def run(cmd: list, cwd=None) -> tuple:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd or str(BOT_DIR)
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def setup_git_repo():
    """Initialize git and connect to GitHub remote."""
    if not GITHUB_TOKEN or not GITHUB_USERNAME:
        logger.warning("GitHub credentials missing, skipping git setup")
        return False

    remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{GITHUB_REPO}.git"
    workspace = Path("/home/runner/workspace")

    # Configure git
    run(["git", "config", "--global", "user.email", "bitgetbot@replit.com"], cwd=str(workspace))
    run(["git", "config", "--global", "user.name", "BitgetBot AI"])
    run(["git", "config", "--global", "init.defaultBranch", "main"])

    # Check if remote exists
    code, out, _ = run(["git", "remote", "get-url", "github"], cwd=str(workspace))
    if code != 0:
        run(["git", "remote", "add", "github", remote_url], cwd=str(workspace))
    else:
        run(["git", "remote", "set-url", "github", remote_url], cwd=str(workspace))

    logger.info("Git remote configured")
    return True


def commit_and_push(message: str = None):
    """Commit all changes and push to GitHub."""
    if not GITHUB_TOKEN or not GITHUB_USERNAME:
        return False

    workspace = Path("/home/runner/workspace")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = message or f"🤖 Bot update — {timestamp}"

    # Stage all changes
    run(["git", "add", "-A"], cwd=str(workspace))

    # Check if there's anything to commit
    code, out, _ = run(["git", "diff", "--cached", "--quiet"], cwd=str(workspace))
    if code == 0:
        logger.info("Nothing new to commit — pushing existing commits to GitHub...")
    else:
        # Commit new changes
        code, out, err = run(["git", "commit", "-m", msg], cwd=str(workspace))
        if code != 0:
            logger.error(f"Git commit failed: {err}")
            return False
        logger.info(f"✅ Committed: {msg}")

    # Always push (even if nothing new to commit — existing commits may not be on remote)
    code, out, err = run(["git", "push", "github", "HEAD:main", "--force"], cwd=str(workspace))
    if code != 0:
        logger.warning(f"Git push failed: {err}")
        return False

    logger.info(f"✅ Pushed to GitHub: {msg}")
    return True


def initial_push():
    """Initial setup push."""
    setup_git_repo()
    return commit_and_push("🚀 Initial bot setup — BitgetBot AI Trading")

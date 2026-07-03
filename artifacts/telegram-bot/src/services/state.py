"""
Global bot state — tracks live activity, signals history, auth, auto-trade toggle.
"""
import time
from datetime import datetime, timezone
from typing import List, Dict, Set, Optional

# ── Auth ──────────────────────────────────────────────────────────────
authenticated_users: Set[int] = set()

# ── Auto-trade toggles ────────────────────────────────────────────────
auto_trade_enabled: bool  = True     # Umumiy avtosavdo (Top Signals 70%+)
zocker_enabled: bool      = True     # Zocker Signal avtosavdo
zocker_notify: bool       = True     # Zocker Signal xabarnomalar (chart+alert)
top_signals_enabled: bool = True     # Top Signals (70%+) avtosavdo
zokpat_enabled: bool      = True     # ZOKPAT Pattern Signal avtosavdo

# ── Max avtomatik pozitsiyalar ─────────────────────────────────────────
MAX_AUTO_POSITIONS: int = 6          # Bir vaqtda maksimal ochiq pozitsiyalar (siz 3 + bot 3)

# ── Balans foizi sozlamasi (default 5%) ───────────────────────────────
trade_balance_pct: float = 5.0  # har bir avtomatik pozitsiyaga balansnin necha %

# ── Manual trade setup (4 ta maxsus crypto uchun) ────────────────────
pending_manual_trades: Dict[str, Dict] = {}   # symbol -> signal dict
waiting_trade_input: Dict[int, Dict] = {}     # user_id -> {symbol, signal, direction}


# ── Live scanner activity ─────────────────────────────────────────────
class ScannerState:
    def __init__(self):
        self.is_scanning: bool = False
        self.current_symbol: str = ""
        self.symbols_checked: int = 0
        self.total_symbols: int = 0
        self.last_scan_time: Optional[float] = None
        self.next_scan_time: Optional[float] = None
        self.signals_this_scan: int = 0
        self.log_lines: List[str] = []
        self.active_trades: Dict = {}   # symbol -> trade info

    def add_log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {msg}")
        if len(self.log_lines) > 50:
            self.log_lines = self.log_lines[-50:]

    def get_recent_logs(self, n: int = 15) -> List[str]:
        return self.log_lines[-n:]

scanner = ScannerState()

# ── Signal history ────────────────────────────────────────────────────
class SignalHistory:
    def __init__(self, max_size: int = 500):
        self.signals: List[Dict] = []
        self.max_size = max_size

    def add(self, signal: Dict):
        entry = dict(signal)
        entry["saved_at"] = int(time.time())
        entry["saved_at_str"] = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
        # outcome: None = kutilmoqda, "TP" = foyda, "SL" = zarar
        if "outcome" not in entry:
            entry["outcome"] = None
        self.signals.insert(0, entry)
        if len(self.signals) > self.max_size:
            self.signals = self.signals[:self.max_size]

    def get_today(self) -> List[Dict]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        return [s for s in self.signals if s.get("saved_at", 0) >= today_start]

    def get_period(self, days: int) -> List[Dict]:
        start = time.time() - days * 86400
        return [s for s in self.signals if s.get("saved_at", 0) >= start]

    def get_all(self) -> List[Dict]:
        return self.signals

    def get_above_conf(self, min_conf: int = 60) -> List[Dict]:
        return [s for s in self.signals if s.get("confidence", 0) >= min_conf]

signal_history = SignalHistory()

# ── Permission-pending signals ────────────────────────────────────────
pending_permission_signals: Dict[str, Dict] = {}

# ── Notifier chat_id (set on first /start after auth) ────────────────
notifier_chat_id: Optional[int] = None

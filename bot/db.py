import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(dt: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dt)
    except Exception:
        return None


class ReportDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as con:
            # Reports table (existing)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    source_channel_id INTEGER NOT NULL,
                    staff_message_id INTEGER,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_reports_staff_msg ON reports(staff_message_id)")

            # Bot settings (existing)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            con.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('report_pings_enabled', '1')"
            )

            # ✅ NEW: user blocks (per guild)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS user_blocks (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    is_permanent INTEGER NOT NULL,
                    expires_at TEXT,
                    reason TEXT,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_user_blocks_expires ON user_blocks(expires_at)")

            con.commit()

    # ---------------- reports ----------------

    def create_report(self, report_type: str, reporter_id: int, guild_id: int, source_channel_id: int, payload: dict) -> int:
        now = _utcnow_iso()
        with self._conn() as con:
            cur = con.execute(
                """
                INSERT INTO reports (report_type, reporter_id, guild_id, source_channel_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_type, reporter_id, guild_id, source_channel_id, "Open", json.dumps(payload), now, now),
            )
            con.commit()
            return int(cur.lastrowid)

    def set_staff_message_id(self, report_id: int, staff_message_id: int):
        now = _utcnow_iso()
        with self._conn() as con:
            con.execute(
                "UPDATE reports SET staff_message_id = ?, updated_at = ? WHERE id = ?",
                (staff_message_id, now, report_id),
            )
            con.commit()

    def get_report_pings_enabled(self) -> bool:
        return self.get_setting("report_pings_enabled", "1") == "1"

    def toggle_report_pings(self) -> bool:
        new_val = "0" if self.get_report_pings_enabled() else "1"
        self.set_setting("report_pings_enabled", new_val)
        return new_val == "1"

    # ---------------- settings ----------------

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as con:
            row = con.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as con:
            con.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            con.commit()

    # ---------------- blocks ----------------

    def _cleanup_expired_block(self, guild_id: int, user_id: int):
        """Remove expired temp blocks automatically."""
        with self._conn() as con:
            row = con.execute(
                "SELECT is_permanent, expires_at FROM user_blocks WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()

            if not row:
                return

            is_perm = int(row[0]) == 1
            expires_at = row[1]
            if is_perm:
                return

            dt = _parse_iso(expires_at) if expires_at else None
            if not dt or dt <= datetime.now(timezone.utc):
                con.execute(
                    "DELETE FROM user_blocks WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                con.commit()

    def is_user_blocked(self, guild_id: int, user_id: int) -> tuple[bool, bool, Optional[str], Optional[str]]:
        """
        Returns: (blocked, is_permanent, expires_at_iso, reason)
        """
        self._cleanup_expired_block(guild_id, user_id)

        with self._conn() as con:
            row = con.execute(
                "SELECT is_permanent, expires_at, reason FROM user_blocks WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()

        if not row:
            return (False, False, None, None)

        return (True, int(row[0]) == 1, row[1], row[2])

    def block_user(
        self,
        guild_id: int,
        user_id: int,
        created_by: int,
        duration_minutes: Optional[int],
        reason: str,
    ):
        """
        duration_minutes=None => permanent
        duration_minutes=int => temp
        """
        now = _utcnow_iso()
        is_perm = 1 if duration_minutes is None else 0
        expires_at = None
        if duration_minutes is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=int(duration_minutes))).isoformat()

        with self._conn() as con:
            con.execute(
                """
                INSERT INTO user_blocks (guild_id, user_id, is_permanent, expires_at, reason, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    is_permanent=excluded.is_permanent,
                    expires_at=excluded.expires_at,
                    reason=excluded.reason,
                    created_by=excluded.created_by,
                    created_at=excluded.created_at
                """,
                (guild_id, user_id, is_perm, expires_at, reason, created_by, now),
            )
            con.commit()

    def unblock_user(self, guild_id: int, user_id: int) -> bool:
        with self._conn() as con:
            cur = con.execute(
                "DELETE FROM user_blocks WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            con.commit()
            return cur.rowcount > 0

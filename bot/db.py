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

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            con.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('report_pings_enabled', '1')")

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

    def get_by_staff_message_id(self, staff_message_id: int) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                """
                SELECT id, report_type, reporter_id, guild_id, source_channel_id, staff_message_id, status, payload_json, created_at, updated_at
                FROM reports
                WHERE staff_message_id = ?
                """,
                (staff_message_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "report_type": row[1],
            "reporter_id": row[2],
            "guild_id": row[3],
            "source_channel_id": row[4],
            "staff_message_id": row[5],
            "status": row[6],
            "payload": json.loads(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }

    def update_status(self, report_id: int, status: str):
        now = _utcnow_iso()
        with self._conn() as con:
            con.execute(
                "UPDATE reports SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, report_id),
            )
            con.commit()

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

    def get_report_pings_enabled(self) -> bool:
        return self.get_setting("report_pings_enabled", "1") == "1"

    def toggle_report_pings(self) -> bool:
        new_val = "0" if self.get_report_pings_enabled() else "1"
        self.set_setting("report_pings_enabled", new_val)
        return new_val == "1"

    # ---------------- blocks ----------------

    def _cleanup_expired_block(self, guild_id: int, user_id: int):
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

    def list_blocks(self, guild_id: int) -> list[dict]:
        """
        Returns active (non-expired) blocks for this guild.
        Each item: {user_id, is_permanent, expires_at, reason, created_by, created_at}
        """
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT user_id, is_permanent, expires_at, reason, created_by, created_at
                FROM user_blocks
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchall()

        active: list[dict] = []
        now = datetime.now(timezone.utc)

        for (user_id, is_perm_i, expires_at, reason, created_by, created_at) in rows:
            is_perm = int(is_perm_i) == 1
            if not is_perm:
                dt = _parse_iso(expires_at) if expires_at else None
                if (dt is None) or (dt <= now):
                    # expired -> remove it
                    self._cleanup_expired_block(guild_id, int(user_id))
                    continue

            active.append(
                {
                    "user_id": int(user_id),
                    "is_permanent": is_perm,
                    "expires_at": expires_at,
                    "reason": reason or "",
                    "created_by": int(created_by) if created_by is not None else None,
                    "created_at": created_at,
                }
            )

        # Permanent first, then soonest expiry
        def _sort_key(x: dict):
            if x["is_permanent"]:
                return (0, 0)
            dt = _parse_iso(x["expires_at"] or "")
            ts = int(dt.timestamp()) if dt else 2**31
            return (1, ts)

        active.sort(key=_sort_key)
        return active

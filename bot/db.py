import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

            # Settings table for toggles like report pings
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            # Default: pings enabled
            con.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('report_pings_enabled', '1')"
            )
            con.commit()

    def create_report(self, report_type: str, reporter_id: int, guild_id: int, source_channel_id: int, payload: dict) -> int:
        now = utcnow_iso()
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
        now = utcnow_iso()
        with self._conn() as con:
            con.execute(
                "UPDATE reports SET staff_message_id = ?, updated_at = ? WHERE id = ?",
                (staff_message_id, now, report_id),
            )
            con.commit()

    def get_by_staff_message_id(self, staff_message_id: int) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                "SELECT id, report_type, reporter_id, guild_id, source_channel_id, staff_message_id, status, payload_json, created_at, updated_at "
                "FROM reports WHERE staff_message_id = ?",
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

    def update_status(self, report_id: int, new_status: str):
        now = utcnow_iso()
        with self._conn() as con:
            con.execute(
                "UPDATE reports SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, report_id),
            )
            con.commit()

    # ---- settings helpers ----
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

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _try_parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


class ReportDB:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self._payload_col = "payload"
        self._created_at_col = "created_at"

        self._ensure_schema()
        self._detect_reports_columns()

    # ---------------- Schema ----------------

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()

        # NOTE: This CREATE TABLE will not overwrite an existing table.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                reporter_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                staff_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Open',
                payload TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_blocks (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_permanent INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT,
                reason TEXT,
                blocked_by INTEGER,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS liveboards (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
            """
        )

        self.conn.commit()

        if self._get_setting("report_pings_enabled") is None:
            self._set_setting("report_pings_enabled", "1")

    def _table_columns(self, table: str) -> list[str]:
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]

    def _detect_reports_columns(self) -> None:
        cols = self._table_columns("reports")

        # Detect payload column (your DB uses payload_json)
        if "payload" in cols:
            self._payload_col = "payload"
        elif "payload_json" in cols:
            self._payload_col = "payload_json"
        else:
            self._payload_col = "payload"

        # Detect created_at column
        self._created_at_col = "created_at" if "created_at" in cols else "created_at"

        print(
            f"DB: reports payload column = '{self._payload_col}', created_at column = '{self._created_at_col}'"
        )

    # ---------------- Settings ----------------

    def _get_setting(self, key: str) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def _set_setting(self, key: str, value: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ---------------- Reports ----------------

    def create_report(
        self,
        report_type: str,
        reporter_id: int,
        guild_id: int,
        source_channel_id: int,
        payload: dict,
    ) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False)

        cur = self.conn.cursor()
        cur.execute(
            f"""
            INSERT INTO reports
            (report_type, reporter_id, guild_id, source_channel_id,
             {self._payload_col}, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'Open', ?)
            """,
            (
                report_type.upper(),
                reporter_id,
                guild_id,
                source_channel_id,
                payload_json,
                _utcnow_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_staff_message_id(self, report_id: int, message_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE reports SET staff_message_id=? WHERE id=?",
            (message_id, report_id),
        )
        self.conn.commit()

    def update_status(self, report_id: int, status: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE reports SET status=?, updated_at=? WHERE id=?",
            (status, _utcnow_iso(), report_id),
        )
        self.conn.commit()

    def get_by_id(self, report_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM reports WHERE id=?", (int(report_id),))
        return self._row_to_report(cur.fetchone())

    # Compatibility alias expected by some cogs
    def get_report_by_id(self, report_id: int):
        return self.get_by_id(report_id)

    def get_by_staff_message_id(self, staff_message_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM reports WHERE staff_message_id=?",
            (int(staff_message_id),),
        )
        row = cur.fetchone()
        return self._row_to_report(row)

    def _row_to_report(self, row):
        if not row:
            return None

        raw_payload = row[self._payload_col] if self._payload_col in row.keys() else None
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except Exception:
            payload = {}

        return {
            "id": row["id"],
            "report_type": row["report_type"],
            "reporter_id": row["reporter_id"],
            "guild_id": row["guild_id"],
            "source_channel_id": row["source_channel_id"],
            "payload": payload,
            "status": row["status"] if "status" in row.keys() else "Open",
            "staff_message_id": row["staff_message_id"] if "staff_message_id" in row.keys() else None,
            "created_at": row["created_at"] if "created_at" in row.keys() else None,
            "updated_at": row["updated_at"] if "updated_at" in row.keys() else None,
        }

    # ---------------- Report pings ----------------

    def get_report_pings_enabled(self) -> bool:
        v = self._get_setting("report_pings_enabled")
        return v != "0"

    def toggle_report_pings(self) -> bool:
        enabled = self.get_report_pings_enabled()
        new_val = "0" if enabled else "1"
        self._set_setting("report_pings_enabled", new_val)
        return new_val == "1"

    # ---------------- Blocks (kept for compatibility) ----------------

    def block_user(
        self,
        guild_id: int,
        user_id: int,
        permanent: bool,
        duration_minutes: Optional[int] = None,
        reason: str = "",
        blocked_by: Optional[int] = None,
    ) -> None:
        expires_at = None
        if not permanent and duration_minutes:
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).isoformat()

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO user_blocks (guild_id, user_id, is_permanent, expires_at, reason, blocked_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET is_permanent=excluded.is_permanent,
                          expires_at=excluded.expires_at,
                          reason=excluded.reason,
                          blocked_by=excluded.blocked_by,
                          created_at=excluded.created_at
            """,
            (
                int(guild_id),
                int(user_id),
                1 if permanent else 0,
                expires_at,
                reason,
                blocked_by,
                _utcnow_iso(),
            ),
        )
        self.conn.commit()

    def unblock_user(self, guild_id: int, user_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_blocks WHERE guild_id=? AND user_id=?", (int(guild_id), int(user_id)))
        self.conn.commit()
        return cur.rowcount > 0

    def is_user_blocked(self, guild_id: int, user_id: int) -> tuple[bool, bool, Optional[str], str]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT is_permanent, expires_at, reason FROM user_blocks WHERE guild_id=? AND user_id=?",
            (int(guild_id), int(user_id)),
        )
        row = cur.fetchone()
        if not row:
            return (False, False, None, "")

        is_perm = bool(row["is_permanent"])
        expires_at = row["expires_at"]
        reason = row["reason"] or ""

        if is_perm:
            return (True, True, None, reason)

        exp_dt = _try_parse_iso(expires_at)
        if exp_dt and exp_dt <= datetime.now(timezone.utc):
            self.unblock_user(guild_id, user_id)
            return (False, False, None, "")

        return (True, False, expires_at, reason)

    def list_blocked_users(self, guild_id: int) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT guild_id, user_id, is_permanent, expires_at, reason, blocked_by, created_at
            FROM user_blocks
            WHERE guild_id=?
            ORDER BY created_at DESC
            """,
            (int(guild_id),),
        )
        out = []
        for r in cur.fetchall():
            out.append(
                {
                    "guild_id": r["guild_id"],
                    "user_id": r["user_id"],
                    "is_permanent": bool(r["is_permanent"]),
                    "expires_at": r["expires_at"],
                    "reason": r["reason"] or "",
                    "blocked_by": r["blocked_by"],
                    "created_at": r["created_at"],
                }
            )
        return out

    # ---------------- Liveboard ----------------

    def set_liveboard(self, guild_id: int, channel_id: int, message_id: int):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO liveboards (guild_id, channel_id, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET channel_id=excluded.channel_id,
                          message_id=excluded.message_id
            """,
            (int(guild_id), int(channel_id), int(message_id)),
        )
        self.conn.commit()

    def get_liveboard(self, guild_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT guild_id, channel_id, message_id FROM liveboards WHERE guild_id=?",
            (int(guild_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"guild_id": row["guild_id"], "channel_id": row["channel_id"], "message_id": row["message_id"]}

    # Compatibility method expected by liveboard loop
    def list_liveboards(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT guild_id, channel_id, message_id FROM liveboards")
        rows = cur.fetchall()
        return [{"guild_id": r["guild_id"], "channel_id": r["channel_id"], "message_id": r["message_id"]} for r in rows]

    def clear_liveboard(self, guild_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM liveboards WHERE guild_id=?", (int(guild_id),))
        self.conn.commit()

    def list_active_reports(self, guild_id: int, closed_statuses: set[str]):
        closed = tuple(closed_statuses)
        placeholders = ",".join("?" for _ in closed)

        cur = self.conn.cursor()
        cur.execute(
            f"""
            SELECT id, report_type, {self._payload_col} AS payload_blob, status,
                   staff_message_id, created_at
            FROM reports
            WHERE guild_id = ?
              AND status NOT IN ({placeholders})
            ORDER BY id DESC
            """,
            (int(guild_id), *closed),
        )

        results = []
        for row in cur.fetchall():
            raw_payload = row["payload_blob"]
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except Exception:
                payload = {}

            rtype = (row["report_type"] or "").upper()

            if rtype == "TV":
                subject = payload.get("channel_name") or payload.get("channel") or "Unknown"
            elif rtype == "VOD":
                subject = payload.get("title") or "Unknown"
            else:
                subject = "Unknown"

            created_dt = _try_parse_iso(row["created_at"] if "created_at" in row.keys() else None)

            results.append(
                {
                    "id": row["id"],
                    "report_type": rtype,
                    "payload": payload,
                    "status": row["status"] if "status" in row.keys() else "Open",
                    "staff_message_id": row["staff_message_id"] if "staff_message_id" in row.keys() else None,
                    "subject": subject,
                    "created_at_dt": created_dt,
                }
            )

        return results

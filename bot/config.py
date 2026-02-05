import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _csv_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


@dataclass(frozen=True)
class Config:
    token: str
    staff_channel_id: int
    support_channel_id: int
    reports_channel_ids: list[int]
    reports_lockdown_channel_ids: list[int]
    staff_ping_user_ids: list[int]
    public_updates: bool
    db_path: str
    tmdb_bearer_token: str
    staff_role_id: int


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")

    staff_channel_id = int(os.getenv("STAFF_CHANNEL_ID", "0"))
    if staff_channel_id <= 0:
        raise RuntimeError("Missing STAFF_CHANNEL_ID in .env")

    support_channel_id = int(os.getenv("SUPPORT_CHANNEL_ID", "0"))

    reports_channel_ids = _csv_ids(os.getenv("REPORTS_CHANNEL_IDS", "").strip())
    if not reports_channel_ids:
        legacy = os.getenv("REPORTS_CHANNEL_ID", "").strip()
        if legacy.isdigit():
            reports_channel_ids = [int(legacy)]
    if not reports_channel_ids:
        raise RuntimeError("Missing REPORTS_CHANNEL_IDS (or REPORTS_CHANNEL_ID) in .env")

    reports_lockdown_channel_ids = _csv_ids(os.getenv("REPORTS_LOCKDOWN_CHANNEL_IDS", "").strip())
    staff_ping_user_ids = _csv_ids(os.getenv("STAFF_PING_USER_IDS", "").strip())

    public_updates = _get_bool("PUBLIC_UPDATES", True)
    db_path = os.getenv("DB_PATH", "./data/reports.sqlite3").strip()
    tmdb_bearer_token = os.getenv("TMDB_BEARER_TOKEN", "").strip()

    staff_role_id = int(os.getenv("STAFF_ROLE_ID", "0"))
    if staff_role_id <= 0:
        raise RuntimeError("Missing STAFF_ROLE_ID in .env")

    return Config(
        token=token,
        staff_channel_id=staff_channel_id,
        support_channel_id=support_channel_id,
        reports_channel_ids=reports_channel_ids,
        reports_lockdown_channel_ids=reports_lockdown_channel_ids,
        staff_ping_user_ids=staff_ping_user_ids,
        public_updates=public_updates,
        db_path=db_path,
        tmdb_bearer_token=tmdb_bearer_token,
        staff_role_id=staff_role_id,
    )

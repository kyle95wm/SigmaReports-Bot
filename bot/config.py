import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _get_id_list_from_csv(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _get_channel_id_list(name: str) -> list[int]:
    raw = os.getenv(name, "").strip()
    return _get_id_list_from_csv(raw) if raw else []


@dataclass(frozen=True)
class Config:
    token: str
    staff_channel_id: int
    support_channel_id: int
    reports_channel_ids: list[int]           # where slash commands are allowed
    reports_lockdown_channel_ids: list[int]  # where messages get deleted
    staff_ping_user_ids: list[int]
    public_updates: bool
    db_path: str


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    staff = int(os.getenv("STAFF_CHANNEL_ID", "0"))
    support = int(os.getenv("SUPPORT_CHANNEL_ID", "0"))

    # Allow list for commands
    reports_channels = _get_channel_id_list("REPORTS_CHANNEL_IDS")
    if not reports_channels:
        # Backward compat
        legacy = os.getenv("REPORTS_CHANNEL_ID", "").strip()
        if legacy.isdigit():
            reports_channels = [int(legacy)]

    # Lockdown list for deleting messages (optional)
    lockdown_channels = _get_channel_id_list("REPORTS_LOCKDOWN_CHANNEL_IDS")

    staff_pings = _get_id_list_from_csv(os.getenv("STAFF_PING_USER_IDS", ""))
    public_updates = _get_bool("PUBLIC_UPDATES", True)
    db_path = os.getenv("DB_PATH", "./data/reports.sqlite3")

    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")
    if staff == 0:
        raise RuntimeError("Missing STAFF_CHANNEL_ID in .env")
    if not reports_channels:
        raise RuntimeError("Missing REPORTS_CHANNEL_IDS (or REPORTS_CHANNEL_ID) in .env")

    return Config(
        token=token,
        staff_channel_id=staff,
        support_channel_id=support,
        reports_channel_ids=reports_channels,
        reports_lockdown_channel_ids=lockdown_channels,
        staff_ping_user_ids=staff_pings,
        public_updates=public_updates,
        db_path=db_path,
    )

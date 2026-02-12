from __future__ import annotations

import discord


def report_subject(report_type: str, payload: dict) -> str:
    rt = (report_type or "").lower()

    if rt == "tv":
        name = (payload or {}).get("channel_name") or "TV report"
        return str(name)

    if rt == "vod":
        title = (payload or {}).get("title") or "VOD report"
        return str(title)

    return "Report"


def _safe_channel_name(ch) -> str:
    try:
        return ch.mention  # type: ignore
    except Exception:
        try:
            return f"#{ch.name}"  # type: ignore
        except Exception:
            return "Unknown"


def _as_user_label(user: discord.abc.User) -> str:
    # user.name is fine; mention included separately in embed for clarity
    return f"{user.mention} ({user.id})"


def _normalize_report_type(rt: str) -> str:
    rt = (rt or "").strip().lower()
    if rt == "tv":
        return "TV"
    if rt == "vod":
        return "VOD"
    return rt.upper() if rt else "REPORT"


def _ref_link_field(payload: dict) -> tuple[str, str] | None:
    """
    Shows the reference link as a nicer label instead of a raw URL.
    Supports TheTVDB / TMDB / IMDb in the label.
    """
    link = (payload or {}).get("reference_link")
    if not link:
        return None

    link_str = str(link).strip()
    if not link_str:
        return None

    label = "Reference"
    lower = link_str.lower()
    if "thetvdb" in lower:
        label = "TheTVDB"
    elif "themoviedb" in lower or "tmdb" in lower:
        label = "TMDB"
    elif "imdb" in lower:
        label = "IMDb"

    # Discord embed links: [label](url)
    return ("Reference", f"[{label}]({link_str})")


async def try_dm(user: discord.abc.User, message: str) -> bool:
    try:
        await user.send(message)
        return True
    except Exception:
        return False


def build_staff_embed(
    report_id: int,
    report_type: str,
    reporter: discord.abc.User,
    source_channel,
    payload: dict,
    status: str,
    ticket_channel_id: int | None = None,
) -> discord.Embed:
    """
    Staff channel embed.

    NOTE: status text comes from the DB (Open / Ticket Open / Resolved / etc.)
    The ticket_channel_id is optional; if you pass it, we'll show a Ticket field.
    """
    rt = _normalize_report_type(report_type)
    subject = report_subject(report_type, payload)

    title = f"Report #{report_id} — {rt} — {subject}"
    embed = discord.Embed(title=title)

    embed.add_field(name="Status", value=str(status or "Open"), inline=False)
    embed.add_field(name="Reporter", value=_as_user_label(reporter), inline=False)
    embed.add_field(name="Reported from", value=_safe_channel_name(source_channel), inline=False)

    # TV fields
    if rt == "TV":
        ch_name = (payload or {}).get("channel_name") or "Unknown"
        ch_cat = (payload or {}).get("channel_category") or "Unknown"
        issue = (payload or {}).get("issue") or "—"

        embed.add_field(name="Channel", value=str(ch_name), inline=True)
        embed.add_field(name="Category", value=str(ch_cat), inline=True)
        embed.add_field(name="Issue", value=str(issue), inline=False)

    # VOD fields
    if rt == "VOD":
        vod_title = (payload or {}).get("title") or "Unknown"
        quality = (payload or {}).get("quality") or "Unknown"
        issue = (payload or {}).get("issue") or "—"

        embed.add_field(name="Title", value=str(vod_title), inline=False)
        embed.add_field(name="Quality", value=str(quality), inline=True)

        ref = _ref_link_field(payload)
        if ref:
            embed.add_field(name=ref[0], value=ref[1], inline=True)

        embed.add_field(name="Issue", value=str(issue), inline=False)

    # Ticket field (only if we know it)
    if ticket_channel_id:
        embed.add_field(name="Ticket", value=f"<#{int(ticket_channel_id)}>", inline=False)

    # Updated staff actions (matches your new workflow)
    embed.add_field(
        name="Staff actions",
        value=(
            "✅ **Resolved** — closes the report\n"
            "🎫 **Open ticket** — creates a private ticket channel for staff + the reporter\n\n"
            "When the ticket is finished, use **Resolve** in the ticket to close it and mark the report as **Resolved**."
        ),
        inline=False,
    )

    return embed

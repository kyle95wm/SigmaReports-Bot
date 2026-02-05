from datetime import datetime, timezone
import discord


def status_color(status: str) -> discord.Color:
    s = (status or "").lower()
    if s == "fixed":
        return discord.Color.green()
    if "can't" in s or "cant" in s:
        return discord.Color.orange()
    if "more info" in s:
        return discord.Color.gold()
    if s == "open":
        return discord.Color.blurple()
    return discord.Color.blurple()


def report_subject(report_type: str, payload: dict) -> str:
    if report_type == "tv":
        return payload.get("channel_name", "Unknown channel")
    if report_type == "vod":
        return payload.get("title", "Unknown title")
    return "Report"


async def try_dm(user: discord.User, content: str) -> bool:
    try:
        await user.send(content)
        return True
    except discord.Forbidden:
        return False


def build_staff_embed(
    report_id: int,
    report_type: str,
    reporter: discord.User,
    source_channel: discord.abc.GuildChannel,
    payload: dict,
    status: str = "Open",
) -> discord.Embed:
    subject = report_subject(report_type, payload)

    embed = discord.Embed(
        title=f"Report #{report_id} — {report_type.upper()} — {subject}",
        color=status_color(status),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Reporter", value=f"{reporter.mention} (`{reporter.id}`)", inline=False)
    embed.add_field(
        name="Reported from",
        value=source_channel.mention if source_channel else "Unknown",
        inline=False,
    )

    if report_type == "tv":
        embed.add_field(name="Channel", value=payload.get("channel_name", "—"), inline=True)
        embed.add_field(name="Category", value=payload.get("channel_category", "—"), inline=True)
        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    if report_type == "vod":
        embed.add_field(name="Title", value=payload.get("title", "—"), inline=False)
        embed.add_field(name="Quality", value=payload.get("quality", "—"), inline=True)

        # Option B: one generic reference link field.
        # Backward compatible with older keys you may have stored already.
        ref = (
            payload.get("reference_link")
            or payload.get("thetvdb_link")
            or payload.get("tvdb_link")
            or "—"
        )
        embed.add_field(name="Reference link", value=ref, inline=False)

        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    embed.add_field(
        name="Staff actions",
        value=(
            "✅ **Fixed** — Issue confirmed and resolved (closes the report)\n"
            "⚠️ **Can't replicate** — Issue could not be reproduced (closes the report)\n"
            "📝 **More info required** — Ask the user to submit a new report with more details\n"
            "💬 **Send follow-up** — Send one-way status updates **without closing the report**"
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Follow-ups are one-way updates to the reporter. "
            "Only Fixed or Can't replicate closes the report."
        )
    )
    return embed

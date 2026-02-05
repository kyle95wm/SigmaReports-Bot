from datetime import datetime, timezone
import discord


def status_color(status: str) -> discord.Color:
    s = status.lower()
    if s == "fixed":
        return discord.Color.green()
    if "can't" in s or "cant" in s:
        return discord.Color.orange()
    if "more info" in s:
        return discord.Color.gold()
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
    status: str,
) -> discord.Embed:
    subject = report_subject(report_type, payload)

    embed = discord.Embed(
        title=f"Report #{report_id} — {report_type.upper()} — {subject}",
        color=status_color(status),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Reporter", value=f"{reporter.mention} (`{reporter.id}`)", inline=False)
    embed.add_field(name="Reported from", value=source_channel.mention, inline=False)

    if report_type == "tv":
        embed.add_field(name="Channel", value=payload.get("channel_name", "—"), inline=True)
        embed.add_field(name="Category", value=payload.get("channel_category", "—"), inline=True)
        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    if report_type == "vod":
        embed.add_field(name="Title", value=payload.get("title", "—"), inline=True)
        embed.add_field(name="Quality", value=payload.get("quality", "—"), inline=True)
        embed.add_field(name="Issue", value=payload.get("issue", "—"), inline=False)

    embed.set_footer(text="Staff actions notify the reporter automatically.")
    return embed

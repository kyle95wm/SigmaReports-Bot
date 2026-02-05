import discord


def report_subject(report_type: str, payload: dict) -> str:
    if report_type == "tv":
        return payload.get("channel_name", "Unknown channel")
    if report_type == "vod":
        return payload.get("title", "Unknown title")
    return "Report"


def build_staff_embed(
    report_id: int,
    report_type: str,
    reporter: discord.User,
    source_channel: discord.abc.GuildChannel,
    payload: dict,
    status: str = "Open",
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📺 New {report_type.upper()} Report #{report_id}",
        color=discord.Color.orange() if status == "Open" else discord.Color.green(),
    )

    embed.add_field(
        name="Reporter",
        value=f"{reporter.mention}\n`{reporter.id}`",
        inline=True,
    )

    embed.add_field(
        name="Source Channel",
        value=source_channel.mention if source_channel else "Unknown",
        inline=True,
    )

    if report_type == "tv":
        embed.add_field(
            name="Channel",
            value=payload.get("channel_name", "N/A"),
            inline=False,
        )
        embed.add_field(
            name="Category",
            value=payload.get("channel_category", "N/A"),
            inline=True,
        )
        embed.add_field(
            name="Issue",
            value=payload.get("issue", "N/A"),
            inline=False,
        )

    elif report_type == "vod":
        embed.add_field(
            name="Title",
            value=payload.get("title", "N/A"),
            inline=False,
        )
        embed.add_field(
            name="Quality",
            value=payload.get("quality", "N/A"),
            inline=True,
        )
        embed.add_field(
            name="Issue",
            value=payload.get("issue", "N/A"),
            inline=False,
        )

    embed.add_field(
        name="Status",
        value=status,
        inline=True,
    )

    embed.add_field(
        name="Staff actions",
        value=(
            "✅ **Fixed** — Issue confirmed and resolved (closes the report)\n"
            "⚠️ **Can't replicate** — Issue could not be reproduced (closes the report)\n"
            "📝 **More info required** — Ask the user to submit a new report with additional details\n"
            "💬 **Send follow-up** — Send status updates or informational messages **without closing the report**"
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Follow-ups are one-way updates to the reporter. "
            "Only Fixed or Can't replicate will close the report."
        )
    )

    return embed


async def try_dm(user: discord.User, content: str):
    try:
        await user.send(content)
    except discord.Forbidden:
        pass

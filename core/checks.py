import discord

from config import settings


def has_role(
    interaction: discord.Interaction,
    role_id: int
):

    if not interaction.guild or not role_id:
        return False

    return any(
        role.id == role_id
        for role in interaction.user.roles
    )


def has_any_role(
    interaction: discord.Interaction,
    role_ids: list[int]
):

    configured_roles = [role_id for role_id in role_ids if role_id]

    return bool(configured_roles) and any(
        has_role(
            interaction,
            role_id
        )
        for role_id in configured_roles
    )


def owner_only():

    async def predicate(
        interaction: discord.Interaction
    ):

        return has_role(
            interaction,
            settings.OWNER_ROLE_ID
        )

    return discord.app_commands.check(
        predicate
    )


def devops_access():

    async def predicate(
        interaction: discord.Interaction
    ):

        return has_any_role(
            interaction,
            [
                settings.OWNER_ROLE_ID,
                settings.DEV_OPS_ROLE_ID
            ]
        )

    return discord.app_commands.check(
        predicate
    )


def admin_access():

    async def predicate(
        interaction: discord.Interaction
    ):

        return has_any_role(
            interaction,
            [
                settings.OWNER_ROLE_ID,
                settings.DEV_OPS_ROLE_ID,
                settings.ADMIN_ROLE_ID
            ]
        )

    return discord.app_commands.check(
        predicate
    )


def staff_access():

    async def predicate(
        interaction: discord.Interaction
    ):

        return has_any_role(
            interaction,
            [
                settings.OWNER_ROLE_ID,
                settings.DEV_OPS_ROLE_ID,
                settings.ADMIN_ROLE_ID,
                settings.STAFF_ROLE_ID
            ]
        )

    return discord.app_commands.check(
        predicate
    )


def member_access():

    async def predicate(
        interaction: discord.Interaction
    ):

        return has_any_role(
            interaction,
            [
                settings.OWNER_ROLE_ID,
                settings.DEV_OPS_ROLE_ID,
                settings.ADMIN_ROLE_ID,
                settings.STAFF_ROLE_ID,
                settings.VRS_MEMBER_ROLE_ID
            ]
        )

    return discord.app_commands.check(
        predicate
    )


def moderation_target_error(
    interaction: discord.Interaction,
    target: discord.Member
) -> str | None:
    """Return a user-facing reason `target` cannot be moderated by the invoker, or None if allowed."""

    guild = interaction.guild

    if guild is None:
        return "This command can only be used in a server."

    if target.id == interaction.user.id:
        return "You cannot use this on yourself."

    if target.id == guild.owner_id:
        return "You cannot moderate the server owner."

    if guild.me and target.id == guild.me.id:
        return "You cannot moderate the bot."

    actor = interaction.user
    if (
        isinstance(actor, discord.Member)
        and actor.id != guild.owner_id
        and target.top_role >= actor.top_role
    ):
        return "You cannot moderate a member with an equal or higher role than you."

    if guild.me and target.top_role >= guild.me.top_role:
        return "My role is not high enough to moderate that member."

    return None

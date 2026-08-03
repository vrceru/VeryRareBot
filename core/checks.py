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

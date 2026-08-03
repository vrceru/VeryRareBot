import unittest
from unittest.mock import MagicMock

import discord

from core.checks import moderation_target_error


class FakeRole:
    def __init__(self, position):
        self.position = position

    def __ge__(self, other):
        return self.position >= other.position

    def __gt__(self, other):
        return self.position > other.position


def make_interaction(*, actor_role, owner_id=1, bot_role=None):
    interaction = MagicMock()
    interaction.guild = MagicMock()
    interaction.guild.owner_id = owner_id
    interaction.guild.me = MagicMock(spec=discord.Member)
    interaction.guild.me.id = 999
    interaction.guild.me.top_role = bot_role or FakeRole(100)

    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 2
    interaction.user.top_role = actor_role

    return interaction


def make_target(target_id, role):
    target = MagicMock(spec=discord.Member)
    target.id = target_id
    target.top_role = role
    return target


class ModerationTargetErrorTests(unittest.TestCase):
    def test_allows_moderating_lower_role(self):
        interaction = make_interaction(actor_role=FakeRole(10))
        target = make_target(3, FakeRole(5))
        self.assertIsNone(moderation_target_error(interaction, target))

    def test_blocks_self_moderation(self):
        interaction = make_interaction(actor_role=FakeRole(10))
        target = make_target(2, FakeRole(1))
        self.assertIsNotNone(moderation_target_error(interaction, target))

    def test_blocks_moderating_guild_owner(self):
        interaction = make_interaction(actor_role=FakeRole(10), owner_id=3)
        target = make_target(3, FakeRole(1))
        self.assertIsNotNone(moderation_target_error(interaction, target))

    def test_blocks_moderating_equal_or_higher_role(self):
        interaction = make_interaction(actor_role=FakeRole(10))
        target = make_target(3, FakeRole(10))
        self.assertIsNotNone(moderation_target_error(interaction, target))

    def test_owner_can_moderate_higher_role_members(self):
        interaction = make_interaction(actor_role=FakeRole(1), owner_id=2, bot_role=FakeRole(999))
        target = make_target(3, FakeRole(50))
        self.assertIsNone(moderation_target_error(interaction, target))

    def test_blocks_when_bot_role_too_low(self):
        interaction = make_interaction(actor_role=FakeRole(50), bot_role=FakeRole(1))
        target = make_target(3, FakeRole(5))
        self.assertIsNotNone(moderation_target_error(interaction, target))


if __name__ == "__main__":
    unittest.main()

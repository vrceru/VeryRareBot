import unittest
from unittest.mock import MagicMock

from config import settings
from core import checks


class ConfigurationTests(unittest.TestCase):
    def test_blank_role_never_grants_access(self):
        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.user.roles = [MagicMock(id=0)]
        self.assertFalse(checks.has_role(interaction, 0))
        self.assertFalse(checks.has_any_role(interaction, [0]))

    def test_missing_token_is_reported(self):
        original_token = settings.DISCORD_TOKEN
        try:
            settings.DISCORD_TOKEN = None
            self.assertEqual(settings.validate(), ["DISCORD_TOKEN is required"])
        finally:
            settings.DISCORD_TOKEN = original_token

import unittest
from unittest.mock import patch

from services import vrms


class VRMSTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_service_name_is_rejected(self):
        with patch.object(vrms.settings, "VRMS_SERVICE_NAME", "bot; rm -rf /"):
            with self.assertRaises(vrms.VRMSError):
                await vrms.service_action("restart")

    async def test_unknown_action_is_rejected(self):
        with self.assertRaises(vrms.VRMSError):
            await vrms.service_action("delete")

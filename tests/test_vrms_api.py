import unittest
from unittest.mock import patch

from services.vrms_api import VRMSAPIClient, VRMSAPIError


class VRMSAPIClientTests(unittest.TestCase):
    def test_from_settings_requires_api_url(self):
        with patch("services.vrms_api.settings.VRMS_API_URL", ""):
            with self.assertRaises(VRMSAPIError):
                VRMSAPIClient.from_settings()

    def test_from_settings_strips_trailing_slash(self):
        with patch("services.vrms_api.settings.VRMS_API_URL", "http://localhost:8787/"):
            with patch("services.vrms_api.settings.VRMS_API_KEY", ""):
                client = VRMSAPIClient.from_settings()
        self.assertEqual(client.base_url, "http://localhost:8787")

    def test_headers_without_api_key(self):
        client = VRMSAPIClient(base_url="http://localhost:8787", api_key="")
        headers = client._headers()
        self.assertNotIn("Authorization", headers)

    def test_headers_with_api_key(self):
        client = VRMSAPIClient(base_url="http://localhost:8787", api_key="secret")
        headers = client._headers()
        self.assertEqual(headers["Authorization"], "Bearer secret")

    def test_headers_never_hardcode_content_type(self):
        # A hardcoded "Content-Type: application/json" on every request -- including bodyless
        # POSTs like cancel/approve/deny -- makes Fastify's JSON body parser reject the request
        # with "Body cannot be empty when content-type is set to 'application/json'". Let
        # aiohttp set it only when an actual json= body is passed.
        client = VRMSAPIClient(base_url="http://localhost:8787", api_key="secret")
        self.assertNotIn("Content-Type", client._headers())


if __name__ == "__main__":
    unittest.main()

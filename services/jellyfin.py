"""Small async client for the Jellyfin API used by the Discord cog."""

from dataclasses import dataclass
from typing import Any

import aiohttp

from config import settings


class JellyfinError(RuntimeError):
    """A user-safe Jellyfin integration error."""


@dataclass(slots=True)
class JellyfinClient:
    base_url: str
    token: str
    user_id: str | None = None

    @classmethod
    def from_settings(cls) -> "JellyfinClient":
        if not settings.JELLYFIN_URL or not settings.JELLYFIN_TOKEN:
            raise JellyfinError("Jellyfin is not configured. Set JELLYFIN_URL and JELLYFIN_TOKEN.")
        return cls(
            settings.JELLYFIN_URL.rstrip("/"),
            settings.JELLYFIN_TOKEN,
            settings.JELLYFIN_USER_ID or None,
        )

    async def request(self, path: str, **params: str) -> Any:
        headers = {"X-Emby-Token": self.token, "Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(f"{self.base_url}{path}", params=params) as response:
                    if response.status in {401, 403}:
                        raise JellyfinError("Jellyfin rejected the configured API token.")
                    if response.status >= 400:
                        raise JellyfinError(f"Jellyfin returned HTTP {response.status}.")
                    return await response.json()
        except aiohttp.ClientError as exc:
            raise JellyfinError("Could not reach Jellyfin. Check JELLYFIN_URL.") from exc

    async def system_info(self) -> dict[str, Any]:
        return await self.request("/System/Info")

    async def sessions(self) -> list[dict[str, Any]]:
        return await self.request("/Sessions")

    async def libraries(self) -> list[dict[str, Any]]:
        if not self.user_id:
            raise JellyfinError("JELLYFIN_USER_ID is required to list libraries.")
        data = await self.request(f"/Users/{self.user_id}/Views")
        return data.get("Items", [])

    async def search(self, query: str) -> list[dict[str, Any]]:
        if not self.user_id:
            raise JellyfinError("JELLYFIN_USER_ID is required to search media.")
        data = await self.request(
            "/Items",
            UserId=self.user_id,
            SearchTerm=query,
            IncludeItemTypes="Movie,Series,Episode,Audio",
            Recursive="true",
            Limit="5",
            Fields="PrimaryImageAspectRatio,ProductionYear",
        )
        return data.get("Items", [])

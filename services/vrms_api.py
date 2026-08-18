"""HTTP client for the VeryRareMediaService (VRMS) job queue and approval API.

Distinct from services/vrms.py, which only talks to systemd for the (separate,
legacy) VRMS host service -- this talks to VRMS's own HTTP API for media
request jobs: enqueueing, status polling, and its two admin-approval gates.
See docs/current/VRMS_INTEGRATION.md for the field mapping and endpoint reference.
"""

from dataclasses import dataclass
from typing import Any

import aiohttp

from config import settings


class VRMSAPIError(RuntimeError):
    """A user-safe VRMS API integration error."""


@dataclass(slots=True)
class VRMSAPIClient:
    base_url: str
    api_key: str = ""

    @classmethod
    def from_settings(cls) -> "VRMSAPIClient":
        if not settings.VRMS_API_URL:
            raise VRMSAPIError("VRMS isn't configured. Set VRMS_API_URL.")
        return cls(settings.VRMS_API_URL.rstrip("/"), settings.VRMS_API_KEY)

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        # Fastify's JSON body parser rejects a POST/PUT with no body at all as "Unsupported
        # Media Type" and an empty-but-content-typed body as "Body cannot be empty" -- a
        # bodyless action (cancel, deny-release, approve-final, ...) needs an actual `{}`.
        if method != "GET" and json is None:
            json = {}

        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
                async with session.request(method, f"{self.base_url}{path}", json=json) as response:
                    if response.status == 401:
                        raise VRMSAPIError("VRMS rejected the configured API key.")
                    if response.status == 404:
                        raise VRMSAPIError("That VRMS job no longer exists.")
                    if response.status >= 400:
                        body = (await response.text())[:200]
                        raise VRMSAPIError(f"VRMS returned HTTP {response.status}: {body}")
                    if response.status == 204:
                        return None
                    return await response.json()
        except aiohttp.ClientError as exc:
            raise VRMSAPIError("Could not reach VRMS. Check VRMS_API_URL.") from exc

    async def enqueue(
        self,
        title: str,
        media_type: str,
        year: int | None = None,
        metadata_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "mediaType": media_type}
        if year is not None:
            body["year"] = year
        if metadata_id is not None:
            body["metadataId"] = metadata_id
        return await self._request("POST", "/api/queue", json=body)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/jobs/{job_id}")

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/jobs/{job_id}/cancel")

    async def list_release_approvals(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/approvals/releases")

    async def approve_release(self, job_id: str, candidate_id: str | None = None) -> dict[str, Any]:
        body = {"candidateId": candidate_id} if candidate_id else None
        return await self._request("POST", f"/api/jobs/{job_id}/approve-release", json=body)

    async def deny_release(self, job_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/jobs/{job_id}/deny-release")

    async def list_final_approvals(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/approvals/final")

    async def approve_final(self, job_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/jobs/{job_id}/approve-final")

    async def deny_final(self, job_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/jobs/{job_id}/deny-final")

    async def ingest_youtube_playlist(self, url: str) -> dict[str, Any]:
        """Bulk-imports a YouTube playlist: one VRMS job per track, each still going through
        the normal two approval gates individually -- see docs/youtube-ingestion.md in the VRMS
        repo. Requires YOUTUBE_INGESTION_ENABLED=true server-side; VRMS returns 400 otherwise."""
        return await self._request("POST", "/api/ingest/youtube", json={"url": url})

    async def get_ingestion_run(self, run_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/ingest/youtube/{run_id}")

"""Safe, narrow systemd integration for the VRMS service."""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from config import settings


class VRMSError(RuntimeError):
    """A user-safe VRMS integration error."""


SERVICE_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")


@dataclass(slots=True)
class VRMSStatus:
    path_exists: bool
    path: str
    service_state: str | None = None


def configured() -> bool:
    return bool(settings.VRMS_PATH or settings.VRMS_SERVICE_NAME)


async def service_action(action: str) -> str:
    if action not in {"start", "stop", "restart", "status"}:
        raise VRMSError("Unsupported VRMS action.")
    service_name = settings.VRMS_SERVICE_NAME
    if not service_name:
        raise VRMSError("VRMS_SERVICE_NAME is not configured.")
    if not SERVICE_NAME.fullmatch(service_name):
        raise VRMSError("VRMS_SERVICE_NAME contains invalid characters.")

    command = ["systemctl", action, service_name]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except (OSError, asyncio.TimeoutError) as exc:
        raise VRMSError("Could not communicate with systemd.") from exc
    if action == "status":
        output = stdout.decode(errors="replace").strip()
        return output or "unknown"
    if process.returncode != 0:
        detail = (stderr or stdout).decode(errors="replace").strip().splitlines()
        raise VRMSError(detail[-1] if detail else f"systemctl {action} failed.")
    return "active" if action in {"start", "restart"} else "inactive"


async def is_active(service_name: str | None = None) -> str:
    """Return systemd's single-word state (active/inactive/failed/...) for the service.

    Unlike `service_action`, a non-"active" result is a normal, expected outcome here
    (not a communication failure), since `systemctl is-active` exits non-zero for it.
    """
    service_name = service_name or settings.VRMS_SERVICE_NAME
    if not service_name:
        raise VRMSError("VRMS_SERVICE_NAME is not configured.")
    if not SERVICE_NAME.fullmatch(service_name):
        raise VRMSError("VRMS_SERVICE_NAME contains invalid characters.")

    command = ["systemctl", "is-active", service_name]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)
    except (OSError, asyncio.TimeoutError) as exc:
        raise VRMSError("Could not communicate with systemd.") from exc
    return stdout.decode(errors="replace").strip() or "unknown"


async def status() -> VRMSStatus:
    path = Path(settings.VRMS_PATH).expanduser()
    service_state = None
    if settings.VRMS_SERVICE_NAME:
        service_state = await service_action("status")
    return VRMSStatus(path_exists=path.exists(), path=str(path), service_state=service_state)

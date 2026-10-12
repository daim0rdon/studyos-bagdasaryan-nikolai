"""Simulated kernel state: user session, current path and resources."""

from dataclasses import dataclass
from typing import Optional

from errors import AccessDenied


@dataclass
class Kernel:
    """Keep transient state separate from persistent SQLite records."""

    database: object
    current_user: Optional[dict] = None
    cwd: str = "/"
    next_pid: int = 1
    used_memory: int = 0

    def __post_init__(self):
        """Recover resource counters when the application starts."""
        self.refresh_resources()

    def refresh_resources(self):
        """Read the PID counter and allocated memory from SQLite."""
        self.next_pid = self.database.scalar(
            "SELECT COALESCE(MAX(pid), 0) + 1 FROM processes"
        )
        self.used_memory = self.database.scalar(
            "SELECT used_kb FROM memory_state WHERE id = 1"
        )

    def require_login(self):
        """Return the current user or raise an access error."""
        if self.current_user is None:
            raise AccessDenied("Сначала выполните login")
        return self.current_user

    def is_admin(self):
        """Return True when an administrator is logged in."""
        return bool(self.current_user and self.current_user["role"] == "admin")

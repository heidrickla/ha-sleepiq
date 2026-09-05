"""Stand-ins for the POSIX modules Home Assistant imports at plugin load.

Home Assistant 2026.8 imports `fcntl` (runner.py, for the lock file it takes
when it runs as a daemon) and `resource` (util/resource.py, to raise the open
file descriptor soft limit) at import time. Neither exists on Windows, and both
are reached while pytest is still loading the
pytest-homeassistant-custom-component plugin, before any conftest runs, so the
whole session aborts on a Windows workstation with ModuleNotFoundError.

Neither module does anything a test depends on: the lock file is never taken
under pytest and the descriptor limit is a process setting. This module is
loaded with `-p tests.winposix` from pyproject.toml, which pytest handles before
it loads entry point plugins, and registers a minimal stand-in for each - but
only on Windows. On Linux, and so in CI, importing this module changes nothing.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any


def _fcntl_module() -> ModuleType:
    """A fcntl with the two names Home Assistant's runner reads."""
    module = ModuleType("fcntl")
    module.LOCK_EX = 2  # type: ignore[attr-defined]
    module.LOCK_NB = 4  # type: ignore[attr-defined]

    def flock(fd: int, operation: int) -> None:
        """Windows has no flock; nothing under pytest takes the lock file."""

    module.flock = flock  # type: ignore[attr-defined]
    return module


def _resource_module() -> ModuleType:
    """A resource whose file descriptor limit is fixed and unchangeable."""
    module = ModuleType("resource")
    module.RLIMIT_NOFILE = 7  # type: ignore[attr-defined]

    def getrlimit(resource_id: int) -> tuple[int, int]:
        """Report a limit already high enough, so nothing tries to raise it."""
        return (sys.maxsize, sys.maxsize)

    def setrlimit(resource_id: int, limits: tuple[int, int]) -> None:
        """Windows has no per-process descriptor limit to set."""

    module.getrlimit = getrlimit  # type: ignore[attr-defined]
    module.setrlimit = setrlimit  # type: ignore[attr-defined]
    return module


def _install() -> None:
    """Put the stand-ins in place before Home Assistant is imported."""
    if sys.platform != "win32":
        return
    builders: dict[str, Any] = {"fcntl": _fcntl_module, "resource": _resource_module}
    for name, build in builders.items():
        if name not in sys.modules:
            sys.modules[name] = build()


_install()

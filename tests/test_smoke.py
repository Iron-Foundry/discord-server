"""Smoke tests: verify entrypoint and every feature service module imports cleanly.

An import-time failure here means a service is broken before the bot ever
connects (bad import, syntax error, module-level side effect needing runtime
state). Keeps parity with api-backend's smoke suite.
"""

from __future__ import annotations

import importlib

import pytest

_CORE_MODULES = [
    "main",
    "core.config",
    "core.discord_client",
    "core.command_handler",
    "core.metrics_reporter",
    "core.service_loader",
    "core.service_handler",
]

_SERVICE_MODULES = [
    "features.tickets.ticket_service",
    "features.member.roles.service",
    "features.member.join_roles.service",
    "features.action_log.service",
    "features.broadcast.service",
    "features.user_keys.service",
    "features.parties.service",
    "features.info_panel.service",
    "features.competition_schedule.service",
    "features.admin.service",
]


@pytest.mark.parametrize("module", _CORE_MODULES + _SERVICE_MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)

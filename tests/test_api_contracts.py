"""Guard: the discord -> api metrics payload matches the shared contract.

MetricsReporter builds the /metrics/report body; the monorepo-root fixture pins
the shape the api-backend accepts. Drift on either side breaks this. Skipped
when run outside the monorepo checkout (submodule-only CI).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.metrics_reporter import MetricsReporter

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


async def test_metrics_payload_matches_contract() -> None:
    reporter = MetricsReporter(MagicMock())
    reporter._api_url = "http://api"
    reporter._api_key = "key"

    http = AsyncMock()
    http.post.return_value = MagicMock(status_code=200)

    await reporter._post_report(http, "tickets", {"open_count": 1})

    sent = http.post.call_args.kwargs["json"]
    fixture = json.loads((_FIXTURES / "metrics_report.json").read_text())

    assert set(sent.keys()) == set(fixture.keys()), (
        "metrics/report payload keys drifted from fixtures/metrics_report.json"
    )
    assert http.post.call_args.kwargs["headers"] == {"verification-code": "key"}

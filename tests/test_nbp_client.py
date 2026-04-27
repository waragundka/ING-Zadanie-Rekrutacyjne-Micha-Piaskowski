"""NBPClient HTTP behaviour."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from portfolio_sim.nbp_client import NBPAPIError, NBPClient


def _mock_session(status: int = 200, payload: dict | None = None, raise_exc: Exception | None = None) -> MagicMock:
    session = MagicMock(spec=requests.Session)
    response = MagicMock()
    response.status_code = status
    response.ok = 200 <= status < 400
    response.json.return_value = payload or {}
    response.text = "" if payload else "error body"
    if raise_exc is not None:
        session.get.side_effect = raise_exc
    else:
        session.get.return_value = response
    return session


def test_fetch_rates_parses_payload(fake_nbp_response: dict) -> None:
    session = _mock_session(payload=fake_nbp_response)
    client = NBPClient(session=session)

    frame = client.fetch_rates("USD", date(2026, 3, 2), date(2026, 3, 4))

    assert list(frame.columns) == ["date", "rate"]
    assert len(frame) == 3
    assert frame["rate"].tolist() == [4.0, 4.05, 4.02]


def test_fetch_rates_extends_lower_bound_for_lookback(fake_nbp_response: dict) -> None:
    session = _mock_session(payload=fake_nbp_response)
    client = NBPClient(session=session)

    client.fetch_rates("USD", date(2026, 3, 9), date(2026, 3, 12))

    called_url = session.get.call_args.args[0]
    # 2026-03-09 minus 7 days = 2026-03-02
    assert "/2026-03-02/" in called_url
    assert called_url.endswith("/2026-03-12/")


def test_fetch_rates_uses_https() -> None:
    client = NBPClient()
    assert client.BASE_URL.startswith("https://")


def test_fetch_rates_request_passes_timeout(fake_nbp_response: dict) -> None:
    session = _mock_session(payload=fake_nbp_response)
    client = NBPClient(session=session)

    client.fetch_rates("USD", date(2026, 3, 2), date(2026, 3, 4))

    assert session.get.call_args.kwargs["timeout"] == NBPClient.REQUEST_TIMEOUT_S


def test_fetch_rates_raises_on_404() -> None:
    session = _mock_session(status=404)
    client = NBPClient(session=session)

    with pytest.raises(NBPAPIError, match="404"):
        client.fetch_rates("USD", date(2026, 3, 2), date(2026, 3, 4))


def test_fetch_rates_raises_on_network_error() -> None:
    session = _mock_session(raise_exc=requests.ConnectionError("dns"))
    client = NBPClient(session=session)

    with pytest.raises(NBPAPIError, match="Network error"):
        client.fetch_rates("USD", date(2026, 3, 2), date(2026, 3, 4))


def test_fetch_rates_raises_on_empty_payload() -> None:
    session = _mock_session(payload={"rates": []})
    client = NBPClient(session=session)

    with pytest.raises(NBPAPIError, match="empty rate set"):
        client.fetch_rates("USD", date(2026, 3, 2), date(2026, 3, 4))


def test_fetch_rates_rejects_inverted_window() -> None:
    client = NBPClient(session=_mock_session(payload={"rates": []}))

    with pytest.raises(ValueError, match="must not precede"):
        client.fetch_rates("USD", date(2026, 3, 10), date(2026, 3, 1))


def test_fetch_rates_rejects_oversized_window() -> None:
    client = NBPClient(session=_mock_session(payload={"rates": []}))

    with pytest.raises(ValueError, match="capped"):
        client.fetch_rates("USD", date(2024, 1, 1), date(2026, 3, 1))

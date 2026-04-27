"""HTTP client for the NBP exchange-rate API (table A — averages)."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Final

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

HTTP_NOT_FOUND = 404


class NBPAPIError(RuntimeError):
    """Raised when the NBP API cannot satisfy a rate request."""


class NBPClient:
    """Read-only client for NBP table-A mid-rate quotes.

    Note on low-value currencies (HUF, JPY, KRW, IDR, ...): NBP table A
    publishes the `mid` field per *100 units* for these, but per single
    unit for everything else. Our pricing pipeline is invariant to this
    convention because both the buy and sell side use the same rate basis,
    so the per-100 factor cancels out and the resulting PLN P&L is correct
    regardless of the unit basis NBP uses for a given currency.
    """

    BASE_URL: Final[str] = "https://api.nbp.pl/api/exchangerates/rates/a"
    REQUEST_TIMEOUT_S: Final[float] = 10.0
    # NBP does not publish on weekends or Polish public holidays. Pulling a few
    # extra calendar days back guarantees at least one quote on or before the
    # caller's start date, which is needed to price a purchase that falls on a
    # non-business day.
    BUSINESS_DAY_LOOKBACK: Final[int] = 7
    MAX_WINDOW_DAYS: Final[int] = 367  # NBP rejects ranges longer than ~1 year.

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
        retry_policy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_policy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_rates(self, code: str, start: date, end: date) -> pd.DataFrame:
        """Return a `date`/`rate` frame for `code` covering [start, end].

        The lower bound is extended by `BUSINESS_DAY_LOOKBACK` days so that a
        purchase on `start` can always be priced — even if `start` falls on a
        non-business day or a long weekend precedes it.
        """
        if end < start:
            raise ValueError(f"end ({end}) must not precede start ({start}).")
        if (end - start).days > self.MAX_WINDOW_DAYS:
            raise ValueError(f"NBP windows are capped at {self.MAX_WINDOW_DAYS} days.")

        window_start = start - timedelta(days=self.BUSINESS_DAY_LOOKBACK)
        url = f"{self.BASE_URL}/{code.lower()}/{window_start.isoformat()}/{end.isoformat()}/"
        log.debug("GET %s", url)

        try:
            response = self._session.get(
                url,
                headers={"Accept": "application/json"},
                timeout=self.REQUEST_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise NBPAPIError(f"Network error fetching {code} rates: {exc}") from exc

        if response.status_code == HTTP_NOT_FOUND:
            raise NBPAPIError(
                f"NBP returned 404 for {code} between {window_start} and {end} — "
                "no published quotes in that window."
            )
        if not response.ok:
            raise NBPAPIError(
                f"NBP responded {response.status_code} for {code}: {response.text[:200]}"
            )

        rates = response.json().get("rates", [])
        if not rates:
            raise NBPAPIError(f"NBP returned an empty rate set for {code}.")

        frame = pd.DataFrame(rates)
        frame["effectiveDate"] = pd.to_datetime(frame["effectiveDate"])
        return (
            frame[["effectiveDate", "mid"]]
            .rename(columns={"effectiveDate": "date", "mid": "rate"})
            .sort_values("date")
            .reset_index(drop=True)
        )

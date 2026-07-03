"""DataUpdateCoordinator for PWEB Amano."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PwebAmanoApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import PwebAmanoError

_LOGGER = logging.getLogger(__name__)


def _entry_key(row: dict) -> str:
    return str(row.get("tckttrns_id") or row.get("idno"))


class PwebAmanoCoordinator(DataUpdateCoordinator[dict]):
    """Logs in and fetches discount/balance data on each poll."""

    def __init__(self, hass: HomeAssistant, client: PwebAmanoApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self._last_paid_stat: dict[str, str] = {}

    async def _async_update_data(self) -> dict:
        today = date.today()
        today_str = today.strftime("%Y%m%d")
        window_start_str = (today - timedelta(days=1)).strftime("%Y%m%d")

        try:
            await self.client.async_login()
            balance = await self.client.async_fetch_discount_balance()
            today_state = await self.client.async_fetch_discount_state(
                today_str, today_str
            )
            window_state = await self.client.async_fetch_discount_state(
                window_start_str, today_str
            )
        except PwebAmanoError as err:
            raise UpdateFailed(str(err)) from err

        summary_rows = today_state.get("summary") or [{}]

        return {
            "last_sync": datetime.now(),
            "balance": balance,
            "registration_summary": summary_rows[0],
            "new_exits": self._detect_new_exits(window_state.get("data") or []),
        }

    def _detect_new_exits(self, rows: list[dict]) -> list[dict]:
        """Diff paid_stat against the previous poll to spot newly-exited cars.

        On the first poll after startup nothing is reported (no prior state
        to diff against), so we don't replay already-exited history as
        "new" exit events.
        """
        current: dict[str, str] = {}
        new_exits: list[dict] = []

        for row in rows:
            key = _entry_key(row)
            paid_stat = row.get("paid_stat")
            current[key] = paid_stat

            previous = self._last_paid_stat.get(key)
            if paid_stat == "10" and previous is not None and previous != "10":
                new_exits.append(row)

        self._last_paid_stat = current
        return new_exits

    async def async_get_discount_events(
        self, start_date: str, end_date: str
    ) -> list[dict]:
        """On-demand fetch for the discount-history calendar (start/end: yyyyMMdd)."""
        state = await self.client.async_fetch_discount_state(start_date, end_date)
        return state.get("data") or []

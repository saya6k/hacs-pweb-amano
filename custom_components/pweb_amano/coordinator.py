"""DataUpdateCoordinator for PWEB Amano."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
        self._has_polled = False

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
            discount_types = await self.client.async_fetch_discount_types()
        except PwebAmanoError as err:
            raise UpdateFailed(str(err)) from err

        summary_rows = today_state.get("summary") or [{}]
        new_entries, new_exits = self._detect_new_entries_and_exits(
            window_state.get("data") or []
        )

        return {
            "last_sync": dt_util.utcnow(),
            "balance": balance,
            "registration_summary": summary_rows[0],
            "new_entries": new_entries,
            "new_exits": new_exits,
            "discount_types": self._active_discount_types(discount_types),
        }

    def _active_discount_types(self, rows: list[dict]) -> dict[str, str]:
        """Build {id: label} for this site's non-deleted discount types.

        This is site-wide admin config (see api.py), so it may list types
        this account never actually uses - shown as-is; the user picks
        whichever fits their own site.
        """
        result = {}
        for row in rows:
            if row.get("del_yn"):
                continue
            label = row.get("discount_name", "")
            price = row.get("discount_price")
            if price:
                label = f"{label} (₩{price:,})"
            result[row["id"]] = label
        return result

    def _detect_new_entries_and_exits(
        self, rows: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Diff against the previous poll to spot newly-seen and newly-exited cars.

        A row's tckttrns_id/idno appearing for the first time is reported as
        a new "entry" (using its entry_date attribute) - this reflects "we
        just noticed this registration", not a live-detected entry, since the
        portal has no dedicated in/out log and a discount is often
        registered well after the car actually parked (sometimes right at/near
        exit). paid_stat flipping to "10" for a row already being tracked is
        reported as a new "exit" - this one is a genuine real-time signal,
        for a car whose discount was registered while still parked.

        On the first poll after startup nothing is reported (no prior state
        to diff against), so we don't replay all-already-registered history
        as "new".
        """
        current: dict[str, str] = {}
        new_entries: list[dict] = []
        new_exits: list[dict] = []

        for row in rows:
            key = _entry_key(row)
            paid_stat = row.get("paid_stat")
            current[key] = paid_stat

            previous = self._last_paid_stat.get(key)
            if previous is None:
                if self._has_polled:
                    new_entries.append(row)
                    if paid_stat == "10":
                        # Common case: the row only appears once the car has
                        # already left, so entry and exit are discovered
                        # together.
                        new_exits.append(row)
            elif paid_stat == "10" and previous != "10":
                new_exits.append(row)

        self._last_paid_stat = current
        self._has_polled = True
        return new_entries, new_exits

    async def async_get_discount_events(
        self, start_date: str, end_date: str
    ) -> list[dict]:
        """On-demand fetch for the discount-history calendar (start/end: yyyyMMdd).

        Unlike the normal poll, this can run whenever a dashboard renders a
        month view — possibly long after the last poll's login, once the
        portal's session has expired — so it must re-login itself rather than
        relying on a cookie the regular poll happened to still have fresh.
        """
        try:
            await self.client.async_login()
            state = await self.client.async_fetch_discount_state(start_date, end_date)
        except PwebAmanoError as err:
            raise HomeAssistantError(str(err)) from err
        if not isinstance(state, dict):
            # The portal appears to respond with a bare JSON null/empty value
            # (rather than {"data": []}) when a range has no registrations at
            # all, e.g. the current month before any car has been discounted.
            return []
        return state.get("data") or []

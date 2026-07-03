"""API client for PWEB (Amano Korea) management portals.

There is no public API — this logs in the same way the portal's own web page
does (POST userId + sha256(password) to /login, then reuse the resulting
JSESSIONID cookie) and hands back raw HTML for parsing.

Each client owns a private aiohttp session (not HA's shared session) so that
two config entries logged into two different portals/accounts never mix
cookies.
"""
from __future__ import annotations

import hashlib
import logging
import re

import aiohttp

from .exceptions import (
    PwebAmanoAuthError,
    PwebAmanoConnectionError,
    PwebAmanoRegistrationError,
)

_LOGGER = logging.getLogger(__name__)

_ILOT_AREA_RE = re.compile(r"^a(\d+)\.pweb\.kr$")
_BALANCE_RE = re.compile(r"잔여\s*할인\s*</th>\s*<td>\s*([\d,]+)", re.DOTALL)
_SITE_NAME_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)


def normalize_base_url(host: str) -> str:
    """Turn a bare host ("a17589.pweb.kr") or full URL into a base URL."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host


def extract_ilot_area(host: str) -> str | None:
    """Pull the numeric parking-lot-area code out of a host like a17589.pweb.kr.

    PWEB assigns each site's portal a hostname of the form a<iLotArea>.pweb.kr,
    so the code the discount-registration endpoints need is already right
    there in the host the user gave us — no extra authenticated page fetch
    needed. Returns None if the host doesn't match that pattern.
    """
    hostname = normalize_base_url(host).split("://", 1)[1].split("/", 1)[0]
    match = _ILOT_AREA_RE.match(hostname)
    return match.group(1) if match else None


async def async_fetch_site_name(host: str) -> str:
    """Fetch the parking-lot/site name shown on the (unauthenticated) login page.

    Used by the config flow so the user can confirm they entered the right
    iLotArea before typing in credentials — /login renders the site name into
    <title> even when logged out, so this needs no session.
    """
    url = f"{normalize_base_url(host)}/login"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                body = await response.text()
    except aiohttp.ClientError as err:
        raise PwebAmanoConnectionError(str(err)) from err

    match = _SITE_NAME_RE.search(body)
    if not match:
        raise PwebAmanoConnectionError("could not find the site name on /login")
    return match.group(1).strip()


class PwebAmanoApiClient:
    """Thin client for login + raw page fetch against a PWEB portal."""

    def __init__(self, base_url: str, user_id: str, password: str) -> None:
        self._base_url = normalize_base_url(base_url)
        self._user_id = user_id
        self._password = password
        self._ilot_area = extract_ilot_area(base_url)
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())

    async def async_close(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def async_login(self) -> None:
        """Log in, raising PwebAmanoAuthError / PwebAmanoConnectionError on failure."""
        password_hash = hashlib.sha256(self._password.encode()).hexdigest()
        url = f"{self._base_url}/login"
        try:
            async with self._session.post(
                url,
                data={"userId": self._user_id, "userPwd": password_hash},
            ) as response:
                if response.status == 500:
                    try:
                        body = await response.json()
                        message = body.get("errorMsg", "login rejected")
                    except (aiohttp.ContentTypeError, ValueError):
                        message = "login rejected"
                    raise PwebAmanoAuthError(message)
                if response.status == 401:
                    raise PwebAmanoAuthError(
                        "portal requires accepting a personal-info agreement "
                        "before this account can log in"
                    )
                response.raise_for_status()
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

    async def async_fetch_dashboard(self) -> str:
        """Fetch the authenticated landing page and return the raw HTML.

        Field-specific parsing is not implemented yet — the authenticated
        page layout hasn't been inspected. See AGENTS.md.
        """
        try:
            async with self._session.get(self._base_url) as response:
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

    async def async_fetch_discount_balance(self) -> int:
        """Fetch the remaining prepaid-discount balance (KRW), from /pay/doViewDscnt.

        The portal renders this value straight into the page HTML (no AJAX
        call), so a plain GET + regex is enough.
        """
        url = f"{self._base_url}/pay/doViewDscnt"
        try:
            async with self._session.get(url) as response:
                response.raise_for_status()
                body = await response.text()
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

        match = _BALANCE_RE.search(body)
        if not match:
            raise PwebAmanoConnectionError(
                "could not find the discount balance on /pay/doViewDscnt"
            )
        return int(match.group(1).replace(",", ""))

    async def async_fetch_discount_state(self, start_date: str, end_date: str) -> dict:
        """Fetch discount registrations between start_date and end_date (yyyyMMdd).

        POSTs the same /state/doListMst endpoint the "할인등록현황" screen uses.
        account_no is left blank: the portal already scopes this endpoint to
        the logged-in account's own records.
        """
        url = f"{self._base_url}/state/doListMst"
        try:
            async with self._session.post(
                url,
                data={
                    "startDate": start_date,
                    "endDate": end_date,
                    "account_no": "",
                    "dc_id": "",
                    "carno": "",
                    "corp": "",
                    "paid_stat": "",
                    "master_id": "",
                    "rowcount": "20000",
                },
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

    async def async_find_parked_entry(self, car_no: str, entry_date: str) -> list[dict]:
        """Look up currently-parked entries for car_no on entry_date (yyyyMMdd).

        Mirrors the "할인등록" screen's car-number search
        (/discount/registration/listForDiscount). Requires iLotArea, which is
        derived from the configured host.
        """
        if self._ilot_area is None:
            raise PwebAmanoRegistrationError(
                "could not derive iLotArea from the configured host "
                "(expected a<number>.pweb.kr)"
            )
        url = f"{self._base_url}/discount/registration/listForDiscount"
        try:
            async with self._session.post(
                url,
                data={
                    "iLotArea": self._ilot_area,
                    "entryDate": entry_date,
                    "carNo": car_no,
                },
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

    async def async_register_discount(
        self, pe_id: str, car_no: str, discount_type: str, memo: str = ""
    ) -> None:
        """Register a discount for a currently-parked vehicle.

        pe_id is the parked-entry id returned by async_find_parked_entry
        (the "id" field). Mirrors /discount/registration/save.
        """
        url = f"{self._base_url}/discount/registration/save"
        try:
            async with self._session.post(
                url,
                data={
                    "peId": pe_id,
                    "carNo": car_no,
                    "discountType": discount_type,
                    "memo": memo,
                    "saveCnt": "1",
                },
            ) as response:
                response.raise_for_status()
                result = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PwebAmanoConnectionError(str(err)) from err

        if result is not True:
            raise PwebAmanoRegistrationError(
                "discount registration was rejected (session may have expired)"
            )

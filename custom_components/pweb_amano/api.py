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
import ssl

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

# PWEB hosts (*.pweb.kr) don't send their intermediate certificate during the
# TLS handshake -- a real server misconfiguration, not a client trust issue.
# The leaf cert chains to this GeoTrust intermediate, which itself chains to
# DigiCert Global Root G2 (a standard trusted root already in any normal CA
# bundle), so supplying just the missing intermediate completes the chain
# without disabling verification. Fetched from the leaf cert's AIA "CA
# Issuers" URL (http://cacerts.geotrust.com/GeoTrustTLSRSACAG1.crt).
_GEOTRUST_TLS_RSA_CA_G1 = """-----BEGIN CERTIFICATE-----
MIIEjTCCA3WgAwIBAgIQDQd4KhM/xvmlcpbhMf/ReTANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xNzExMDIxMjIzMzdaFw0yNzExMDIxMjIzMzdaMGAxCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xHzAdBgNVBAMTFkdlb1RydXN0IFRMUyBSU0EgQ0EgRzEwggEiMA0GCSqGSIb3
DQEBAQUAA4IBDwAwggEKAoIBAQC+F+jsvikKy/65LWEx/TMkCDIuWegh1Ngwvm4Q
yISgP7oU5d79eoySG3vOhC3w/3jEMuipoH1fBtp7m0tTpsYbAhch4XA7rfuD6whU
gajeErLVxoiWMPkC/DnUvbgi74BJmdBiuGHQSd7LwsuXpTEGG9fYXcbTVN5SATYq
DfbexbYxTMwVJWoVb6lrBEgM3gBBqiiAiy800xu1Nq07JdCIQkBsNpFtZbIZhsDS
fzlGWP4wEmBQ3O67c+ZXkFr2DcrXBEtHam80Gp2SNhou2U5U7UesDL/xgLK6/0d7
6TnEVMSUVJkZ8VeZr+IUIlvoLrtjLbqugb0T3OYXW+CQU0kBAgMBAAGjggFAMIIB
PDAdBgNVHQ4EFgQUlE/UXYvkpOKmgP792PkA76O+AlcwHwYDVR0jBBgwFoAUTiJU
IBiV5uNu5g/6+rkS7QYXjzkwDgYDVR0PAQH/BAQDAgGGMB0GA1UdJQQWMBQGCCsG
AQUFBwMBBggrBgEFBQcDAjASBgNVHRMBAf8ECDAGAQH/AgEAMDQGCCsGAQUFBwEB
BCgwJjAkBggrBgEFBQcwAYYYaHR0cDovL29jc3AuZGlnaWNlcnQuY29tMEIGA1Ud
HwQ7MDkwN6A1oDOGMWh0dHA6Ly9jcmwzLmRpZ2ljZXJ0LmNvbS9EaWdpQ2VydEds
b2JhbFJvb3RHMi5jcmwwPQYDVR0gBDYwNDAyBgRVHSAAMCowKAYIKwYBBQUHAgEW
HGh0dHBzOi8vd3d3LmRpZ2ljZXJ0LmNvbS9DUFMwDQYJKoZIhvcNAQELBQADggEB
AIIcBDqC6cWpyGUSXAjjAcYwsK4iiGF7KweG97i1RJz1kwZhRoo6orU1JtBYnjzB
c4+/sXmnHJk3mlPyL1xuIAt9sMeC7+vreRIF5wFBC0MCN5sbHwhNN1JzKbifNeP5
ozpZdQFmkCo+neBiKR6HqIA+LMTMCMMuv2khGGuPHmtDze4GmEGZtYLyF8EQpa5Y
jPuV6k2Cr/N3XxFpT3hRpt/3usU/Zb9wfKPtWpoznZ4/44c1p9rzFcZYrWkj3A+7
TNBJE0GmP2fhXhP1D/XVfIW/h0yCJGEiV9Glm/uGOa3DXHlmbAcxSyCRraG+ZBkA
7h4SeM6Y8l/7MBRpPCz6l8Y=
-----END CERTIFICATE-----
"""


def _build_ssl_context() -> ssl.SSLContext:
    """Default trust store plus the intermediate PWEB's servers omit."""
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=_GEOTRUST_TLS_RSA_CA_G1)
    return context


_SSL_CONTEXT = _build_ssl_context()


def normalize_base_url(host: str) -> str:
    """Turn a bare host ("a12345.pweb.kr") or full URL into a base URL."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host


def extract_ilot_area(host: str) -> str | None:
    """Pull the numeric parking-lot-area code out of a host like a12345.pweb.kr.

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
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_SSL_CONTEXT)
        ) as session:
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
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(),
            connector=aiohttp.TCPConnector(ssl=_SSL_CONTEXT),
        )

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
        account_no must be sent as the logged-in user's own id - the portal
        does NOT scope this endpoint by session when account_no is left
        blank, it returns every account's registrations building-wide (a
        visitor-car registration still carries the registering resident's
        account_no, so this still includes those).
        """
        url = f"{self._base_url}/state/doListMst"
        try:
            async with self._session.post(
                url,
                data={
                    "startDate": start_date,
                    "endDate": end_date,
                    "account_no": self._user_id,
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

"""Read one web page a student linked (a careers page or a posting): the only part of the app that reaches the internet.

Guardrails, all in code:
- http(s) only, ports 80/443, no user:password in the URL;
- the host must resolve to public addresses only: no localhost, private networks, link-local or cloud metadata
  addresses (server-side request forgery); every redirect is checked again, at most MAX_REDIRECTS;
- FETCH_TIMEOUT_SECONDS per request, at most MAX_PAGE_BYTES read, text/html or text/plain only;
- robots.txt is respected, the app identifies itself (USER_AGENT), and bot protection (HTTP 401/403/429/503) is
  never bypassed: the student is asked to paste the text instead.
The page then goes through the same shield as a paste (hidden text removed, injected instructions quarantined).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

FETCH_TIMEOUT_SECONDS = 10
MAX_PAGE_BYTES = 2_000_000
MAX_REDIRECTS = 3
USER_AGENT = ("SummerInternshipCoach/1.0 (reads one page a student linked; "
              "+https://github.com/aymonpadillahernandez/summer_internship_coach_aymon)")
BLOCKED_STATUS = {401, 403, 429, 503}


class FetchError(Exception):
    """A message for the student: why the page could not be read."""


def resolve(host: str) -> list[str]:
    """The addresses a host name points to (replaced in tests)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def make_client() -> httpx.Client:
    """The HTTP client (replaced in tests by one with a mock transport)."""
    return httpx.Client(follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})


def check_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http:// or https:// links can be read.")
    if parts.username or parts.password:
        raise FetchError("Links with a user name or password are not read.")
    if not parts.hostname:
        raise FetchError("That link has no web address.")
    if parts.port not in (None, 80, 443):
        raise FetchError("Only standard web ports (80 and 443) are read.")
    try:
        addresses = resolve(parts.hostname)
    except (socket.gaierror, UnicodeError):
        raise FetchError("That web address does not exist.") from None
    for a in addresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError("That link points to a private or local address, which the app never reads.")
    return url.strip()


def robots_allow(client: httpx.Client, url: str) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        check_url(robots_url)
        r = client.get(robots_url, timeout=4)
    except (FetchError, httpx.HTTPError):
        return True
    if r.status_code != 200:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


def fetch(url: str) -> tuple[str, str]:
    """(final URL, page text). Raises FetchError with a message for the student."""
    current = check_url(url)
    with make_client() as client:
        if not robots_allow(client, current):
            raise FetchError("This site asks automated readers not to read that page (robots.txt). Paste its text instead.")
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        current = check_url(urljoin(current, r.headers.get("location", "")))
                        continue
                    if r.status_code in BLOCKED_STATUS:
                        raise FetchError(f"This site blocks automated reading (HTTP {r.status_code}). "
                                         "Open the page in your browser and paste its text instead.")
                    if r.status_code >= 400:
                        raise FetchError(f"The page could not be read (HTTP {r.status_code}).")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and ctype not in ("text/html", "text/plain", "application/xhtml+xml"):
                        raise FetchError(f"That link is not a web page ({ctype}). Paste the text instead.")
                    body = b""
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > MAX_PAGE_BYTES:
                            break
                    return current, body[:MAX_PAGE_BYTES].decode(r.encoding or "utf-8", errors="replace")
            except httpx.TimeoutException:
                raise FetchError(f"The page did not answer within {FETCH_TIMEOUT_SECONDS} s.") from None
            except httpx.HTTPError:
                raise FetchError("The page could not be reached.") from None
        raise FetchError("Too many redirects.")

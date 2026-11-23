"""Two protections in front of every API request.

Cross-site requests: anything that changes data (POST, PUT, PATCH, DELETE) must come from PEA's own pages. The login
cookie is SameSite=Lax, which already keeps it off most cross-site requests; this also refuses the rest, based on
what the browser says about where a request comes from (Sec-Fetch-Site, Origin). Requests without those headers
don't come from a browser page, so they can't ride on someone's login and are let through.

Rate limits: a few actions that are expensive or can be abused get a ceiling per person (their session) or, before
sign-in, per address: signing in, uploading files, looking things up in Web of Science, Crossref and ORCID (whose
daily quota PEA shares), and importing lists of people. Counted in memory per API worker (the server runs two), so
the ceilings are approximate, which is enough to stop a runaway script.
"""

import hashlib
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.sessions import COOKIE_NAME
from app.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def allowed_origin(origin: str) -> bool:
    if origin == origin_of(settings.public_url):
        return True
    # Development: the app runs on localhost on various ports (the dev server, the end-to-end tests)
    return not settings.production and urlsplit(origin).hostname in ("localhost", "127.0.0.1")


def cross_site(request: Request) -> bool:
    """A request that changes data, sent by a page on another site."""
    if request.method not in UNSAFE_METHODS:
        return False
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in ("same-origin", "none"):
        return True
    origin = request.headers.get("origin")
    if origin is None:
        return False
    return origin == "null" or not allowed_origin(origin)  # "null": sandboxed or opaque pages


@dataclass(frozen=True)
class Rule:
    name: str
    methods: frozenset[str]
    path: re.Pattern[str]
    limit: int  # requests...
    seconds: int  # ...per this many seconds
    message: str


RULES = [
    Rule("sign-in", frozenset({"GET"}),
         re.compile(r"^/api/v1/(auth/google/(login|callback)|orcid/(connect|callback))$"),
         30, 600, "Too many sign-in attempts"),
    Rule("uploads", frozenset({"POST", "PUT"}), re.compile(r"^/api/v1/me/(documents|profile/photo)$"),
         60, 600, "Too many uploads"),
    Rule("lookups", frozenset({"GET", "POST"}),
         re.compile(r"^/api/v1/(wos/|crossref/|orcid/me/works|orgs/[^/]+/research-output$|me/research-outputs/import$)"),
         120, 600, "Too many lookups"),
    Rule("people-import", frozenset({"POST"}), re.compile(r"^/api/v1/orgs/[^/]+/people/import$"),
         60, 600, "Too many lists sent"),
]


class Limiter:
    """Sliding window: the times of recent requests, per rule and per person or address"""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, rule: Rule, who: str, now: float | None = None) -> int:
        """Records the request and returns 0, or the seconds to wait when the limit is reached (not recorded)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._hits) > 50_000:  # forget people who stopped long ago
                self._hits = {key: hits for key, hits in self._hits.items() if hits and now - hits[-1] < 3600}
            hits = self._hits.setdefault((rule.name, who), deque())
            while hits and now - hits[0] >= rule.seconds:
                hits.popleft()
            if len(hits) >= rule.limit:
                return max(1, math.ceil(rule.seconds - (now - hits[0])))
            hits.append(now)
            return 0


limiter = Limiter()


def who_is(request: Request) -> str:
    """The person's session if they're signed in (hashed: the token itself isn't kept), otherwise their address"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return "session:" + hashlib.sha256(token.encode()).hexdigest()
    return "ip:" + (request.client.host if request.client else "unknown")


def problem_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    """Same shape as app.errors.problem, for answers given before a route runs"""
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status, headers=headers)


async def protect(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        if cross_site(request):
            return problem_response(403, "cross_site", "This request came from another website, so PEA refused it.")
        for rule in RULES:
            if request.method in rule.methods and rule.path.search(path):
                wait = limiter.check(rule, who_is(request))
                if wait:
                    minutes = math.ceil(wait / 60)
                    return problem_response(
                        429, "rate_limited",
                        f"{rule.message}. Please wait {minutes} minute{'s' if minutes != 1 else ''} and try again.",
                        {"Retry-After": str(wait)})
                break
    return await call_next(request)

"""Requests from other websites are refused when they would change data, and a few actions have rate limits
(app/security.py)."""

import pytest

from app.config import settings
from app.security import RULES, Limiter, limiter
from tests.api.helpers import error_code

ME = "/api/v1/me/profile"


def bio(client, **headers):
    return client.put(ME, json={"biography": {"en": "<p>Hi</p>"}}, headers=headers)


def test_data_changes_from_other_websites_are_refused(signed_in, make_user):
    c = signed_in(make_user(email="person@iliauni.edu.ge", status="active"))
    for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"},
                    {"Sec-Fetch-Site": "same-site", "Origin": "https://other.iliauni.edu.ge"}, {"Origin": "null"}):
        refused = bio(c, **headers)
        assert refused.status_code == 403, headers
        assert error_code(refused) == "cross_site"
        assert refused.headers["X-Content-Type-Options"] == "nosniff"  # the usual headers still apply


def test_pea_pages_and_non_browser_clients_pass(signed_in, make_user):
    c = signed_in(make_user(email="person@iliauni.edu.ge", status="active"))
    own = settings.public_url.rstrip("/")
    assert bio(c, Origin=own, **{"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert bio(c).status_code == 200  # no browser headers: not a page, can't ride on someone's cookie
    # Reading is never refused: a link from another site to a PEA page still works
    assert c.get(ME, headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_in_production_only_the_real_address_counts(monkeypatch, signed_in, make_user):
    c = signed_in(make_user(email="person@iliauni.edu.ge", status="active"))
    monkeypatch.setattr(settings, "public_url", "https://pea.iliauni.edu.ge")
    assert bio(c, Origin="https://pea.iliauni.edu.ge").status_code == 200
    assert bio(c, Origin="http://localhost:5173").status_code == 403


def rule(name):
    return next(r for r in RULES if r.name == name)


def test_sign_in_attempts_are_limited_per_address(client):
    sign_in = rule("sign-in")
    for _ in range(sign_in.limit):
        assert client.get("/api/v1/auth/google/login", follow_redirects=False).status_code != 429
    limited = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert limited.status_code == 429
    assert error_code(limited) == "rate_limited"
    assert "Too many sign-in attempts" in limited.json()["detail"]["message"]
    assert int(limited.headers["Retry-After"]) > 0


def test_limits_count_per_person(signed_in, make_user, monkeypatch):
    lookups = rule("lookups")
    first = signed_in(make_user(email="first@iliauni.edu.ge", status="active"))
    second = signed_in(make_user(email="second@iliauni.edu.ge", status="active"))
    url = "/api/v1/crossref/lookup?doi=10.1000/abc"
    for _ in range(lookups.limit):
        assert first.get(url).status_code != 429
    assert first.get(url).status_code == 429
    assert second.get(url).status_code != 429  # someone else isn't affected


@pytest.mark.parametrize("path, method, name", [
    ("/api/v1/me/documents", "POST", "uploads"),
    ("/api/v1/me/profile/photo", "PUT", "uploads"),
    ("/api/v1/wos/lookup", "GET", "lookups"),
    ("/api/v1/orcid/me/works", "GET", "lookups"),
    ("/api/v1/orgs/1d9b1f9e-0000-0000-0000-000000000000/research-output", "GET", "lookups"),
    ("/api/v1/me/research-outputs/import", "POST", "lookups"),
    ("/api/v1/orgs/1d9b1f9e-0000-0000-0000-000000000000/people/import", "POST", "people-import"),
    ("/api/v1/orcid/callback", "GET", "sign-in"),
])
def test_the_rules_cover_these_endpoints(path, method, name):
    matching = [r.name for r in RULES if method in r.methods and r.path.search(path)]
    assert matching[:1] == [name]


def test_the_window_slides():
    window = Limiter()
    one = rule("people-import")
    for second in range(one.limit):
        assert window.check(one, "x", now=float(second)) == 0
    assert window.check(one, "x", now=float(one.limit)) > 0
    assert window.check(one, "x", now=one.seconds + 0.5) == 0  # the oldest request has left the window
    limiter.reset()


def test_made_up_cookies_dont_get_around_the_sign_in_limit(client):
    sign_in = rule("sign-in")
    for n in range(sign_in.limit):
        client.cookies.set("pea_session", f"made-up-{n}")
        assert client.get("/api/v1/auth/google/login", follow_redirects=False).status_code != 429
    client.cookies.set("pea_session", "yet-another-one")
    assert client.get("/api/v1/auth/google/login", follow_redirects=False).status_code == 429

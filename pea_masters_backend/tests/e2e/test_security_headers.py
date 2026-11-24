"""The website under its Content Security Policy: the production build, served with exactly the policy the server sends
(read from deploy/Caddyfile), opened page by page. Any page the policy breaks, or anything it blocks, fails the test,
so a new script, style or outside address can't slip in unnoticed.

Builds the app first (bun run build), so it takes a little longer than the other browser tests.
"""

import os
import re
import shutil
import subprocess

import pytest
from playwright.sync_api import Page, expect

from app.auth.sessions import COOKIE_NAME, create_session
from app.db import SessionLocal
from tests.e2e.conftest import API_PORT, BACKEND, FRONTEND, port_free, stop, wait_for

PREVIEW_PORT = 5182
PREVIEW_URL = f"http://localhost:{PREVIEW_PORT}"

# Collects what the browser blocks, from the first moment of every page
COLLECT = """
window.__blocked = [];
document.addEventListener("securitypolicyviolation", event => {
  const where = `${event.sourceFile || ""}:${event.lineNumber}`;
  window.__blocked.push(`${event.effectiveDirective} blocked ${event.blockedURI || "inline"} (${where})`);
});
"""


def policy() -> str:
    caddyfile = (BACKEND.parent / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    found = re.search(r'header Content-Security-Policy "([^"]+)"', caddyfile)
    assert found, "deploy/Caddyfile has no Content-Security-Policy"
    # Upgrading to HTTPS is for the real server; here the preview runs on plain http://localhost
    return found.group(1).replace("; upgrade-insecure-requests", "")


@pytest.fixture(scope="session")  # built once per run, however pytest orders the tests
def preview(servers):
    if not port_free(PREVIEW_PORT):  # an old preview would answer with an old policy
        pytest.exit(f"Port {PREVIEW_PORT} is in use. Stop whatever runs there and try again.")
    bun = shutil.which("bun")
    built = subprocess.run([bun, "run", "build"], cwd=FRONTEND, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout[-2000:] + built.stderr[-2000:]
    env = {**os.environ, "PEA_API_URL": f"http://127.0.0.1:{API_PORT}", "PEA_CSP": policy()}
    process = subprocess.Popen([bun, "x", "vite", "preview", "--port", str(PREVIEW_PORT), "--strictPort"],
                               cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        wait_for(PREVIEW_URL, process, "vite preview")
        yield PREVIEW_URL
    finally:
        stop(process)  # the whole process tree: bun starts Vite as a child


def watched_page(context) -> tuple[Page, list[str]]:
    page = context.new_page()
    page.add_init_script(COLLECT)
    console: list[str] = []
    page.on("console", lambda message: console.append(message.text)
            if "Content Security Policy" in message.text else None)
    return page, console


def blocked(page: Page, console: list[str]) -> list[str]:
    return page.evaluate("window.__blocked") + console


def test_the_policy_is_sent(preview):
    page_headers = __import__("urllib.request").request.urlopen(f"{preview}/people").headers
    assert page_headers["Content-Security-Policy"] == policy()
    assert "script-src 'self';" in policy() and "'unsafe-inline'" not in policy() and "'unsafe-eval'" not in policy()


def test_every_page_works_under_the_policy(preview, browser, organization):
    with SessionLocal() as db:
        token, _ = create_session(db, organization["admin_id"], None, "e2e-csp")
        db.commit()
    context = browser.new_context(base_url=preview, viewport={"width": 1400, "height": 900})
    context.add_cookies([{"name": COOKIE_NAME, "value": token, "url": preview}])
    page, console = watched_page(context)
    admin = organization["admin_id"]
    org = organization["org_id"]

    pages = {
        "/home": None, "/people": "People", "/profile": None, "/cv-builder": "CV builder",
        "/evaluation-form": None, "/settings/privacy": "Settings", "/admin/evaluations": "Evaluations",
        "/admin/evaluation-forms": "Evaluation forms", "/admin/people/import": "Add people",
        f"/people/{admin}?org={org}": None,
    }
    for path, heading in pages.items():
        page.goto(path)
        page.wait_for_load_state("load")
        if heading:
            expect(page.get_by_role("heading", name=heading, level=1)).to_be_visible()
        else:
            expect(page.locator(".dashboard-content")).to_be_visible()  # the page drew, it isn't blank
        page.wait_for_timeout(300)  # the page has drawn; a moment more for anything it loads after that
        assert blocked(page, console) == [], f"{path}: {blocked(page, console)}"

    # A few things that load more as you use them: the CV templates, a filter menu, the Excel template
    page.goto("/cv-builder")
    page.get_by_role("tab", name="Sections & layout").click()
    page.locator(".cv-template-option").filter(has_text="Banner").click()
    page.goto("/people")
    page.get_by_role("button", name=re.compile("^Departments:")).click()
    page.keyboard.press("Escape")
    page.goto("/admin/people/import")
    with page.expect_download():
        page.get_by_role("button", name="Download template").click()
    page.wait_for_timeout(500)
    assert blocked(page, console) == []
    context.close()


def test_signed_out_pages_work_under_the_policy(preview, browser):
    context = browser.new_context(base_url=preview)
    page, console = watched_page(context)
    for path in ("/login", "/privacy"):
        page.goto(path)
        page.wait_for_load_state("load")
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.wait_for_timeout(300)  # the page has drawn; a moment more for anything it loads after that
        assert blocked(page, console) == [], f"{path}: {blocked(page, console)}"
    context.close()

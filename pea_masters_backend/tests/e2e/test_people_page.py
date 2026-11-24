"""People page end to end: an Admin sets up a faculty and department, adds people with "Add people", filters the
list and makes someone Coordinator. Everyone sees the People page and colleagues' profiles (private ones say so); only
Admins add and deactivate people."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import APP_URL

FACULTY = "School of Business, Technology and Education"
DEPARTMENT = "Computer Science"
HEAD_EMAIL, HEAD_NAME = "nika.lomidze@iliauni.edu.ge", "Nika Lomidze"
RESEARCHER_EMAIL, RESEARCHER_NAME = "mariam.kapanadze@iliauni.edu.ge", "Mariam Kapanadze"


def row(page: Page, text: str):
    return page.locator("tbody tr", has_text=text)


def add_people(page: Page, people: list[tuple[str, str | None]]) -> None:
    """Registers people on the Add people page: (email, department or None)."""
    page.goto("/people")
    page.get_by_role("button", name="Add people").click()
    expect(page).to_have_url(re.compile("/admin/people/import"))
    # The page has loaded the people and the structure (the template button waits for them): type only then
    expect(page.get_by_role("button", name="Download template")).to_be_enabled()
    for index, (email, department) in enumerate(people, start=1):
        if index > 1:
            page.get_by_role("button", name="Add row").click()
        page.get_by_label(f"Email, line {index}").fill(email)
        expect(page.get_by_label(f"Email, line {index}")).to_have_value(email)
        if department:
            page.get_by_label(f"Department, line {index}").select_option(label=department)
    count = len(people)
    expect(page.get_by_text(f"{count} to register")).to_be_visible()  # every row counted before saving
    page.get_by_role("button", name=f"Register {count} {'person' if count == 1 else 'people'}").click()
    page.get_by_role("alertdialog").get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name=re.compile(r"registered$"))).to_be_visible()
    page.get_by_role("button", name="Back to People").click()
    expect(page).to_have_url(re.compile("/people$"))


def test_admin_sets_up_a_department_and_its_coordinator_sees_the_directory(admin_page: Page, google_sign_in, shot):
    page = admin_page

    # 1. The Admin opens People from the sidebar
    page.goto("/home")
    page.locator(".dashboard-sidebar").get_by_role("button", name="People").click()
    expect(page).to_have_url(re.compile("/people$"))
    expect(page.get_by_role("heading", name="People", level=1)).to_be_visible()
    expect(row(page, "Test Admin")).to_be_visible()
    expect(page.get_by_role("button", name="Add person")).to_have_count(0)  # only "Add people" now

    # 2. Adds a faculty and a department inside it
    page.get_by_role("tab", name="Structure").click()
    page.get_by_role("button", name="Add faculty").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Name in English *").fill(FACULTY)
    dialog.get_by_label("Name in Georgian").fill("ბიზნესის, ტექნოლოგიისა და განათლების სკოლა")
    dialog.get_by_role("button", name="Add faculty").click()
    expect(page.get_by_role("status")).to_contain_text(f"{FACULTY} was added.")

    page.get_by_role("button", name="Add department", exact=True).click()
    dialog = page.get_by_role("dialog")
    # Other tests may have added faculties to the shared organization already, so choose it rather than expect it
    dialog.get_by_label("Faculty *").select_option(label=FACULTY)
    dialog.get_by_label("Name in English *").fill(DEPARTMENT)
    dialog.get_by_role("button", name="Add department").click()
    expect(page.get_by_role("status")).to_contain_text(f"{DEPARTMENT} was added.")
    expect(page.get_by_role("heading", name=FACULTY, level=3)).to_be_visible()
    expect(row(page, DEPARTMENT)).to_contain_text("No Coordinator yet")
    shot(page, "1-structure")

    # 3. Registers two people into the department with "Add people"
    add_people(page, [(HEAD_EMAIL, DEPARTMENT), (RESEARCHER_EMAIL, DEPARTMENT)])
    person = row(page, HEAD_NAME)
    for text in (HEAD_EMAIL, DEPARTMENT, FACULTY, "Researcher", "Invited", "Never"):
        expect(person).to_contain_text(text)

    # Filters: several departments or faculties can be ticked; ticking the faculty includes its departments
    page.get_by_role("button", name=re.compile("^Departments:")).click()
    page.get_by_role("dialog", name="Departments").get_by_label(FACULTY).check()
    page.keyboard.press("Escape")
    expect(row(page, HEAD_NAME)).to_be_visible()
    expect(row(page, "Test Admin")).to_have_count(0)  # not in a department
    # 2 shown, out of everyone in the shared organization (other tests may have added people already)
    expect(page.get_by_text(re.compile(r"^2 of \d+$"))).to_be_visible()
    page.get_by_role("button", name=re.compile("^Roles:")).click()
    page.get_by_role("dialog", name="Roles").get_by_label("Admin").check()
    page.keyboard.press("Escape")
    expect(page.get_by_text("No one matches these filters.")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Roles:")).click()
    page.get_by_role("dialog", name="Roles").get_by_role("button", name="Clear").click()
    page.keyboard.press("Escape")
    page.get_by_label("Search people").fill("kapan")
    expect(page.locator("tbody tr")).to_have_count(1)
    expect(row(page, RESEARCHER_NAME)).to_be_visible()
    shot(page, "2-filters")
    page.get_by_label("Search people").fill("")

    # 4. The Admin makes the first one Coordinator of the department
    page.get_by_role("button", name=f"Edit {HEAD_NAME}").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("checkbox", name=re.compile("^Coordinator")).check()
    dialog.get_by_label("Coordinates department *").select_option(label=DEPARTMENT)
    dialog.get_by_role("button", name="Save changes").click()
    expect(row(page, HEAD_NAME)).to_contain_text(f"Coordinator: {DEPARTMENT}")

    # 5. The Coordinator signs in. They see everyone, but can't add or deactivate people; they can correct the name
    #    of their own Researcher only
    nika = google_sign_in(HEAD_EMAIL, HEAD_NAME)
    nika.goto("/home")
    nika.locator(".dashboard-sidebar").get_by_role("button", name="People").click()
    expect(nika).to_have_url(re.compile("/people$"))
    expect(row(nika, "Test Admin")).to_be_visible()
    expect(row(nika, RESEARCHER_NAME)).to_be_visible()
    expect(nika.get_by_role("button", name="Add people")).to_have_count(0)
    expect(nika.get_by_role("button", name=re.compile("^Deactivate"))).to_have_count(0)
    expect(nika.get_by_role("columnheader", name="Last sign-in")).to_have_count(0)
    expect(nika.get_by_role("tab", name="Structure")).to_have_count(0)  # structure is for Admins
    expect(nika.get_by_role("button", name="Edit Test Admin")).to_have_count(0)
    nika.get_by_role("button", name=f"Edit {RESEARCHER_NAME}").click()
    dialog = nika.get_by_role("dialog")
    dialog.get_by_label("Full name *").fill("Mariam Kapanadze-Beridze")
    dialog.get_by_role("button", name="Save changes").click()
    expect(row(nika, "Mariam Kapanadze-Beridze")).to_be_visible()
    shot(nika, "3-coordinator-directory")
    nika.goto("/admin/people/import")
    expect(nika.get_by_text("Only Admins can add or deactivate people.")).to_be_visible()

    # 6. The Admin deactivates the Coordinator; they're signed out at once and stop coordinating
    page.reload()
    page.get_by_role("button", name=f"Deactivate {HEAD_NAME}").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Reason").fill("End-to-end test")
    dialog.get_by_role("button", name="Deactivate").click()
    expect(row(page, HEAD_NAME)).to_contain_text("Deactivated")
    expect(row(page, HEAD_NAME)).not_to_contain_text("Coordinator:")
    shot(page, "4-deactivated")

    nika.reload()
    expect(nika).to_have_url(re.compile("/login"))


def test_researchers_open_profiles_and_private_ones_say_so(admin_page: Page, google_sign_in, shot):
    add_people(admin_page, [("tamar.public@iliauni.edu.ge", None), ("levan.private@iliauni.edu.ge", None)])
    tamar = google_sign_in("tamar.public@iliauni.edu.ge", "Tamar Public")
    tamar.goto("/profile")
    expect(tamar.get_by_role("heading", name="Tamar Public")).to_be_visible()

    # Levan makes his profile private in Settings → Privacy
    levan = google_sign_in("levan.private@iliauni.edu.ge", "Levan Private")
    levan.goto("/settings/privacy")
    levan.get_by_role("radio", name=re.compile("^Private")).check()
    expect(levan.get_by_text("Your profile is private.")).to_be_visible()
    levan.goto("/people")
    row(levan, "Levan Private").get_by_role("link").click()
    expect(levan.get_by_text("Your profile is private: only you")).to_be_visible()

    # A Researcher opens People, then colleagues' pages
    tamar.locator(".dashboard-sidebar").get_by_role("button", name="People").click()
    expect(tamar.get_by_role("columnheader", name="Status")).to_have_count(0)
    row(tamar, "Test Admin").get_by_role("link").click()
    expect(tamar).to_have_url(re.compile(r"/people/[0-9a-f-]+"))
    expect(tamar.get_by_role("article", name="Profile of Test Admin")).to_be_visible()
    tamar.get_by_role("button", name="Back").click()
    row(tamar, "Levan Private").get_by_role("link").click()
    expect(tamar.get_by_text("Levan Private keeps their profile private")).to_be_visible()
    expect(tamar.get_by_role("article")).to_have_count(0)
    shot(tamar, "5-private-profile")

    # Tamar's CV is public, so it's on her page, without the phone number she keeps private
    saved = tamar.request.put(f"{APP_URL}/api/v1/me/cv", data={"data": {
        "version": 1, "visibility": "public", "template": "banner",
        "publicFields": {"email": True, "phone": False, "metrics": True},
        "sections": [{"id": "summary", "enabled": True}],
        "personal": {"headline": "Plant geneticist", "phone": "+995 555 123 456", "summary": "I study barley."}}})
    assert saved.ok, saved.text()
    levan.goto("/people")
    row(levan, "Tamar Public").get_by_role("link").click()
    cv = levan.get_by_role("region", name="CV")
    expect(cv.get_by_role("article", name="CV preview")).to_be_visible()
    expect(cv).to_contain_text("Plant geneticist")
    expect(cv).to_contain_text("I study barley.")
    expect(cv).not_to_contain_text("555 123 456")
    shot(levan, "6-public-cv")

    # The Admin reviews Levan, so sees his profile anyway, with a note
    admin_page.goto("/people")
    row(admin_page, "Levan Private").get_by_role("link").click()
    note = "Levan Private's profile is private. You see it because you review them."
    expect(admin_page.get_by_text(note)).to_be_visible()
    expect(admin_page.get_by_role("article", name="Profile of Levan Private")).to_be_visible()


def test_admin_cannot_deactivate_themselves_or_register_outside_domain(admin_page: Page):
    page = admin_page
    page.goto("/people")
    expect(page.get_by_role("button", name="Deactivate Test Admin")).to_be_disabled()

    page.get_by_role("button", name="Add people").click()
    page.get_by_label("Email, line 1").fill("someone@gmail.com")
    page.get_by_label("Name (optional), line 1").fill("Someone")
    page.get_by_role("button", name="Register 1 person").click()
    expect(page.get_by_text("Use an address from the organization's domain")).to_be_visible()


def test_settings_show_google_sign_in_instead_of_a_password(admin_page: Page):
    page = admin_page
    page.goto("/settings/security")
    expect(page.get_by_role("heading", name="How you sign in")).to_be_visible()
    expect(page.get_by_text("e2e.admin@iliauni.edu.ge")).to_be_visible()
    expect(page.get_by_label("Current password")).to_have_count(0)


def test_admins_set_up_evaluation_periods(admin_page: Page, shot):
    """Admins add a period with its deadline and publication years, extend the deadline and remove it; names are
    unique. (Only Admins may manage periods: tests/api/test_evaluations.py.)"""
    page = admin_page
    page.goto("/admin/people")
    page.get_by_role("tab", name="Evaluation periods").click()
    panel = page.locator(".evaluation-periods")
    expect(panel).to_contain_text("No evaluation periods yet")

    def fill_period(name: str):
        sheet = page.get_by_role("dialog")
        sheet.get_by_label(re.compile("^Name")).fill(name)
        sheet.get_by_label(re.compile("^Opens on")).fill("2026-09-01")
        sheet.get_by_label(re.compile("^Deadline")).fill("2026-11-30")
        sheet.get_by_label(re.compile("^Publications from")).select_option("2024")
        sheet.get_by_label(re.compile("^Publications to")).select_option("2026")
        return sheet

    page.get_by_role("button", name="Add period").click()
    fill_period("Annual evaluation 2025-2026").get_by_role("button", name="Add period").click()
    row = panel.locator("tbody tr", has_text="Annual evaluation 2025-2026")
    expect(row).to_contain_text("30 Nov 2026")
    expect(row).to_contain_text("2024–2026")
    expect(page.get_by_role("dialog")).to_have_count(0)
    shot(page, "people-02-evaluation-periods")

    # The same name again: the server says so and the sheet stays open
    page.get_by_role("button", name="Add period").click()
    sheet = fill_period("annual evaluation 2025-2026")
    sheet.get_by_role("button", name="Add period").click()
    expect(sheet.get_by_role("alert")).to_contain_text("There's already a period called")
    sheet.get_by_role("button", name="Cancel").click()

    # Extending the deadline
    row.get_by_role("button", name="Edit Annual evaluation 2025-2026").click()
    sheet = page.get_by_role("dialog")
    sheet.get_by_label(re.compile("^Deadline")).fill("2026-12-15")
    sheet.get_by_role("button", name="Save period").click()
    expect(row).to_contain_text("15 Dec 2026")

    row.get_by_role("button", name="Remove Annual evaluation 2025-2026").click()
    page.get_by_role("dialog").get_by_role("button", name="Remove period").click()
    expect(panel).to_contain_text("No evaluation periods yet")


def test_the_privacy_page_is_public(browser, servers, shot):
    """Google asks for a privacy policy it can read without signing in; the login page links to it."""
    context = browser.new_context(base_url=APP_URL, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto("/login")
    page.get_by_role("link", name="Privacy").click()
    expect(page).to_have_url(re.compile(r"/privacy$"))
    expect(page.get_by_role("heading", name="Privacy", level=1)).to_be_visible()
    for heading in ("What PEA keeps", "Who can see it", "Outside services", "Cookies and your browser"):
        expect(page.get_by_role("heading", name=heading)).to_be_visible()
    shot(page, "privacy-01-page")
    page.get_by_role("link", name="Back to sign in").click()
    expect(page).to_have_url(re.compile(r"/login$"))
    context.close()

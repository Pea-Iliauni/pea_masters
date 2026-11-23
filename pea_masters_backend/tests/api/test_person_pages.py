"""A person's page (GET /people/{id}/page): public profiles to everyone in the organization, private ones only to the
person and those who review them (Admins, their Coordinator); everyone else sees that it's private."""

from sqlalchemy import select

from app.models import AuditLog
from tests.api.helpers import add_department, as_person, register


def page_of(client, base, user_id):
    return client.get(f"{base}/people/{user_id}/page")


def researcher_with_a_profile(as_admin, signed_in, db, base, department_id=None):
    person = register(as_admin, base, "nino.beridze@iliauni.edu.ge", department_id=department_id,
                      name="Nino Beridze").json()
    c = as_person(signed_in, db, person)
    c.put("/api/v1/me/profile", json={"biography": {"en": "<p>I study proteins.</p>"}})
    award = {"title": "Best paper", "body": "ISU", "date": "2024-05-01"}
    c.post("/api/v1/me/profile/entries", json={"section": "awards", "values": award})
    c.put("/api/v1/me/profile/research", json={"interests": ["Proteins"]})
    c.post("/api/v1/me/research-outputs", json={"kind": "publication", "subtype": "Journal article",
                                                 "title": "Folding", "year": 2025})
    return person, c


def test_profiles_are_public_by_default_and_shown_to_colleagues(as_admin, signed_in, make_user, db, base):
    person, _ = researcher_with_a_profile(as_admin, signed_in, db, base)
    colleague = signed_in(make_user(email="colleague@iliauni.edu.ge", status="active"))

    page = page_of(colleague, base, person["id"])
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["visible"], body["private"], body["own"]) == (True, False, False)
    assert body["person"]["display_name"] == "Nino Beridze"
    assert body["biography"]["en"] == "<p>I study proteins.</p>"
    assert [e["values"]["title"] for e in body["entries"]["awards"]] == ["Best paper"]
    assert "documents" not in body["entries"]["awards"][0]  # supporting documents are never shown
    assert body["research"]["interests"] == ["Proteins"]
    assert [o["title"] for o in body["outputs"]] == ["Folding"]
    assert body["person"]["last_login_at"] is None


def test_a_private_profile_shows_only_the_directory_details(as_admin, signed_in, make_user, db, base):
    cs = add_department(as_admin, base, "Computer Science")
    person, owner = researcher_with_a_profile(as_admin, signed_in, db, base, department_id=cs)
    switched = owner.put("/api/v1/me/profile/visibility", json={"is_public": False})
    assert switched.json()["is_public"] is False
    assert db.scalar(select(AuditLog.after).where(AuditLog.action == "profile.visibility_changed")) == \
        {"is_public": False}

    colleague = signed_in(make_user(email="colleague@iliauni.edu.ge", status="active"))
    body = page_of(colleague, base, person["id"]).json()
    assert (body["visible"], body["private"]) == (False, True)
    assert body["person"]["department"]["id"] == cs  # what the People page shows anyway
    assert (body["biography"], body["entries"], body["outputs"], body["photo_url"]) == ({}, {}, [], None)

    # The owner and the people who review them still see everything, with a note that it's private
    for viewer in (owner, as_admin):
        seen = page_of(viewer, base, person["id"]).json()
        assert (seen["visible"], seen["private"]) == (True, True)
        assert seen["biography"]["en"] == "<p>I study proteins.</p>"
    assert page_of(owner, base, person["id"]).json()["own"] is True


def test_their_coordinator_sees_a_private_profile_another_one_does_not(as_admin, signed_in, db, base):
    cs = add_department(as_admin, base, "Computer Science")
    math = add_department(as_admin, base, "Mathematics")
    person, owner = researcher_with_a_profile(as_admin, signed_in, db, base, department_id=cs)
    owner.put("/api/v1/me/profile/visibility", json={"is_public": False})
    own_head = register(as_admin, base, "head.cs@iliauni.edu.ge", roles=["coordinator", "member"], coordinates=cs,
                        department_id=cs).json()
    other_head = register(as_admin, base, "head.math@iliauni.edu.ge", roles=["coordinator", "member"],
                          coordinates=math, department_id=math).json()
    assert page_of(as_person(signed_in, db, own_head), base, person["id"]).json()["visible"] is True
    assert page_of(as_person(signed_in, db, other_head), base, person["id"]).json()["visible"] is False


def test_deactivated_people_have_no_page_except_for_admins(as_admin, signed_in, make_user, db, base):
    person, _ = researcher_with_a_profile(as_admin, signed_in, db, base)
    as_admin.post(f"{base}/people/{person['id']}/deactivate", json={"reason": None})
    colleague = signed_in(make_user(email="colleague@iliauni.edu.ge", status="active"))
    assert page_of(colleague, base, person["id"]).status_code == 404
    assert page_of(as_admin, base, person["id"]).json()["person"]["status"] == "deactivated"


def test_people_outside_the_organization_cannot_see_pages(as_admin, signed_in, db, base, client):
    person, _ = researcher_with_a_profile(as_admin, signed_in, db, base)
    assert client.get(f"{base}/people/{person['id']}/page").status_code == 401


def test_hidden_email_and_photo_are_left_out_for_colleagues_only(as_admin, signed_in, make_user, db, base):
    from tests.api.test_profiles import image_bytes, upload

    person, owner = researcher_with_a_profile(as_admin, signed_in, db, base)
    photo_url = upload(owner, image_bytes()).json()["photo_url"]
    colleague = signed_in(make_user(email="colleague@iliauni.edu.ge", status="active"))
    assert page_of(colleague, base, person["id"]).json()["photo_url"] == photo_url  # shown by default
    assert colleague.get(photo_url).status_code == 200

    saved = owner.put("/api/v1/me/profile/visibility", json={"show_email": False, "show_photo": False}).json()
    assert (saved["show_email"], saved["show_photo"], saved["is_public"]) == (False, False, True)

    page = page_of(colleague, base, person["id"]).json()
    assert (page["person"]["email"], page["photo_url"]) == ("", None)
    listed = {p["id"]: p for p in colleague.get(f"{base}/people").json()["people"]}
    assert listed[person["id"]]["email"] == ""
    assert colleague.get(photo_url).status_code == 404  # the file itself too

    # The person and those who review them still see both
    for viewer in (owner, as_admin):
        seen = page_of(viewer, base, person["id"]).json()
        assert (seen["person"]["email"], seen["photo_url"]) == ("nino.beridze@iliauni.edu.ge", photo_url)
        assert viewer.get(photo_url).status_code == 200
    assert {p["id"]: p for p in as_admin.get(f"{base}/people").json()["people"]}[person["id"]]["email"] \
        == "nino.beridze@iliauni.edu.ge"


def test_a_public_cv_is_on_the_page_without_what_its_owner_keeps_private(as_admin, signed_in, make_user, db, base):
    person, owner = researcher_with_a_profile(as_admin, signed_in, db, base)
    colleague = signed_in(make_user(email="colleague@iliauni.edu.ge", status="active"))
    cv = {"version": 1, "visibility": "private", "template": "sidebar",
          "publicFields": {"email": True, "phone": False, "metrics": False},
          "personal": {"headline": "Biologist", "phone": "+995 555 000 000", "summary": "Proteins."},
          "metrics": {"hIndex": "12", "citations": "340", "source": "Web of Science", "asOf": "2026-11"}}
    assert owner.put("/api/v1/me/cv", json={"data": cv}).status_code == 200
    assert page_of(colleague, base, person["id"]).json()["cv"] is None  # private: not shown, not even to reviewers
    assert page_of(as_admin, base, person["id"]).json()["cv"] is None

    owner.put("/api/v1/me/cv", json={"data": {**cv, "visibility": "public"}})
    shown = page_of(colleague, base, person["id"]).json()["cv"]
    assert (shown["template"], shown["personal"]["headline"], shown["personal"]["summary"]) == \
        ("sidebar", "Biologist", "Proteins.")
    assert shown["personal"]["phone"] == ""  # kept private: never sent
    assert shown["metrics"]["hIndex"] == "" and shown["metrics"]["citations"] == ""
    assert shown["publicFields"]["email"] is True

    # Hiding the email on the profile hides it on the CV too
    owner.put("/api/v1/me/profile/visibility", json={"show_email": False})
    assert page_of(colleague, base, person["id"]).json()["cv"]["publicFields"]["email"] is False

    # A private profile shows no CV either
    owner.put("/api/v1/me/profile/visibility", json={"is_public": False})
    assert page_of(colleague, base, person["id"]).json()["cv"] is None

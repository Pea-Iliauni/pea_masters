"""A person's page, opened from the People page: their profile as colleagues see it.

Everyone in the organization can open the page of anyone active in it. A public profile shows its biography,
profile entries (without the supporting documents), teaching and research, and research outputs. A private one
shows only what the People page already shows (name, department, position) and says it's private, except to the
people who review the person: the person themselves, their organization's Admins and their Coordinator.
The email address and photo are left out for everyone else when the person hides them (Settings → Privacy).
The CV is shown when its owner made it public in the CV builder (to everyone, reviewers included, as with the
builder's visitor view), without the contact details and metrics they keep private.
"""

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from app.authz import Action, Actor, authorize, get_actor, get_organization, target_user_id_in_scope
from app.cv import CvData, Metrics
from app.db import get_db
from app.errors import problem
from app.models import Cv, OrganizationMembership, Profile, ProfileEntry, ResearchOutput, User
from app.people import PersonOut, one_person
from app.profile_entries import SECTIONS, Research, Teaching
from app.profiles import photo_url
from app.research_outputs import OutputOut
from app.research_outputs import to_out as output_out

router = APIRouter(tags=["profile"])


class PublicEntry(BaseModel):
    """A profile entry as visitors see it: no supporting documents"""
    id: uuid.UUID
    values: dict[str, str]


class PersonPage(BaseModel):
    person: PersonOut  # name, department, faculty, position, roles: what the People page shows
    visible: bool  # false: the profile is private; only `person` is filled in
    own: bool  # the person's own page
    private: bool  # the owner made it private (shown to reviewers with a note)
    photo_url: str | None
    biography: dict[str, str]  # {"en": html, "ka": html}, cleaned when it was saved
    entries: dict[str, list[PublicEntry]]  # section -> entries, newest first
    research: Research
    teaching: Teaching
    outputs: list[OutputOut]
    cv: CvData | None  # the CV, when its owner made it public; private parts removed


def public_cv(db: Session, user_id: uuid.UUID, show_email: bool) -> CvData | None:
    """The CV as visitors may see it, or None while it's private (or there's none). What the owner keeps private
    (phone, metrics; the email when hidden here or on the profile) never leaves the server."""
    saved = db.get(Cv, user_id)
    if saved is None:
        return None
    cv = CvData.model_validate(saved.data)
    if cv.visibility != "public":
        return None
    if not cv.publicFields.phone:
        cv.personal.phone = ""
    if not cv.publicFields.metrics:
        cv.metrics = Metrics()
    if not show_email:
        cv.publicFields.email = False
    return cv


def reviews(db: Session, actor: Actor, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """The person themselves, Root, the organization's Admins, or the Coordinator of their department."""
    if actor.is_root or actor.user.id == user_id or "admin" in actor.roles_in(org_id):
        return True
    return "coordinator" in actor.roles_in(org_id) and bool(
        db.scalar(select(literal(True)).where(target_user_id_in_scope(actor.user.id, org_id, user_id))))


@router.get("/api/v1/orgs/{org_id}/people/{user_id}/page", response_model=PersonPage)
def person_page(org_id: uuid.UUID, user_id: uuid.UUID, actor: Actor = Depends(get_actor),
                db: Session = Depends(get_db)):
    get_organization(db, org_id)
    authorize(db, actor, Action.VIEW_DIRECTORY, org_id)
    person = one_person(db, org_id, user_id)
    reviewer = reviews(db, actor, org_id, user_id)
    if person.status == "deactivated" and not reviewer:
        raise problem(status.HTTP_404_NOT_FOUND, "not_found", "This person isn't part of the organization.")
    profile = db.get(Profile, user_id)
    if not reviewer:
        hidden_email = profile is not None and not profile.show_email
        person = person.model_copy(update={"last_login_at": None, **({"email": ""} if hidden_email else {})})

    private = profile is not None and not profile.is_public
    visible = reviewer or not private
    page = PersonPage(person=person, visible=visible, own=actor.user.id == user_id, private=private,
                      photo_url=None, biography={}, entries={}, research=Research(), teaching=Teaching(), outputs=[],
                      cv=None)
    if not visible:
        return page

    member = db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == org_id, OrganizationMembership.user_id == user_id))
    user = db.get(User, user_id)
    if member is None or user is None:
        raise problem(status.HTTP_404_NOT_FOUND, "not_found", "This person isn't part of the organization.")
    entries: dict[str, list[PublicEntry]] = {section: [] for section in SECTIONS}
    for entry in db.scalars(select(ProfileEntry).where(ProfileEntry.user_id == user_id)
                            .order_by(ProfileEntry.created_at.desc())):
        entries.setdefault(entry.section, []).append(PublicEntry(id=entry.id, values=dict(entry.values)))
    outputs = db.scalars(select(ResearchOutput).where(ResearchOutput.user_id == user_id).order_by(
        ResearchOutput.year.desc().nulls_first(), ResearchOutput.created_at.desc())).all()
    return page.model_copy(update={
        "photo_url": photo_url(profile.photo_file_id) if profile and (reviewer or profile.show_photo) else None,
        "biography": dict(profile.biography) if profile else {},
        "entries": entries,
        "research": Research.model_validate(profile.research if profile else {}),
        "teaching": Teaching.model_validate(profile.teaching if profile else {}),
        "outputs": [output_out(output) for output in outputs],
        "cv": public_cv(db, user_id, show_email=bool(person.email)),
    })

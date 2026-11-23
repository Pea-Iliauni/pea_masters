import { api } from "./api"
import type { Role } from "./auth"

/* People and organization structure (pea_masters_backend/app/people.py and units.py).
   Structure: organization → faculties (schools) → departments (programs). People belong to a department;
   each department has one Coordinator. The "member" role is shown as "Researcher". */

export type LocalizedName = Record<string, string> // { en, ka? }

export type UnitRef = { id: string; name: LocalizedName }

export type UnitKind = "faculty" | "department"

export type Unit = UnitRef & {
  kind: UnitKind
  /** A department's faculty */
  parent_id: string | null
  /** Departments only: their Coordinator */
  coordinator: { id: string; display_name: string } | null
  /** A faculty counts the people of all its departments */
  member_count: number
}

export type PersonStatus = "invited" | "active" | "deactivated"

/** registration: typed or guessed when registered, replaced by Google's name at first sign-in;
 *  google: the official name from ISU's Google directory; manual: corrected in PEA, never overwritten */
export type NameSource = "registration" | "google" | "manual"

export type Person = {
  id: string
  email: string
  display_name: string
  name_source: NameSource
  status: PersonStatus
  roles: Role[]
  department: UnitRef | null
  faculty: UnitRef | null
  /** Academic position, e.g. Associate Professor */
  position: UnitRef | null
  /** The department this person coordinates */
  coordinates: UnitRef | null
  last_login_at: string | null
}

export type PeopleList = {
  /** Admins: everyone. Others: active people, without statuses' details or last sign-ins */
  people: Person[]
  /** Admins: add, deactivate and reactivate people */
  can_register: boolean
  /** Admins: roles, moving people between departments, structure */
  can_manage_roles: boolean
  /** Whose name this person may correct: everyone for Admins, a Coordinator's own Researchers */
  editable: string[]
}

/** Picks the name in the interface language, falling back to the other one */
export function localName(name: LocalizedName, language: "KA" | "EN") {
  return (language === "KA" ? name.ka || name.en : name.en || name.ka) ?? ""
}

export const roleLabels: Record<Role, string> = { admin: "Admin", coordinator: "Coordinator", member: "Researcher" }
export const roleHints: Record<Role, string> = {
  admin: "The organization's responsible person: manages people, roles and structure.",
  coordinator: "Coordinates a department: sends and reviews its Researchers' evaluations.",
  member: "Keeps a researcher profile and submits evaluations.",
}
export const statusLabels: Record<PersonStatus, string> = { invited: "Invited", active: "Active", deactivated: "Deactivated" }

export type FacultyGroup = { faculty: Unit | null; departments: Unit[] }

/** Departments grouped under their faculty, sorted by name; departments without a faculty come last. */
export function groupByFaculty(units: Unit[], language: "KA" | "EN"): FacultyGroup[] {
  const byName = (a: Unit, b: Unit) => localName(a.name, language).localeCompare(localName(b.name, language))
  const faculties = units.filter(unit => unit.kind === "faculty").sort(byName)
  const departments = units.filter(unit => unit.kind === "department").sort(byName)
  const groups: FacultyGroup[] = faculties.map(faculty => ({ faculty, departments: departments.filter(d => d.parent_id === faculty.id) }))
  const orphans = departments.filter(d => !faculties.some(f => f.id === d.parent_id))
  if (orphans.length) groups.push({ faculty: null, departments: orphans })
  return groups
}

/** Faculties with their departments under them, for a FilterMenu; ticking a faculty includes its departments */
export function unitFilterOptions(units: Unit[], language: "KA" | "EN") {
  return groupByFaculty(units, language).flatMap(group => [
    ...(group.faculty ? [{ value: group.faculty.id, label: localName(group.faculty.name, language) }] : []),
    ...group.departments.map(unit => ({ value: unit.id, label: localName(unit.name, language), parent: group.faculty?.id })),
  ])
}

/** Whether someone is in one of the ticked departments or faculties (nothing ticked: everyone) */
export const inUnits = (person: Pick<Person, "department" | "faculty">, units: ReadonlySet<string>) =>
  units.size === 0 || (person.department !== null && units.has(person.department.id)) || (person.faculty !== null && units.has(person.faculty.id))

/** Lower case, without accents or extra spaces, so "Nino" finds "nino" and "Kapanadze " finds "kapanadze" */
export const searchText = (text: string) => text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim()

/**
 * What a person can be found by (name, email, department, faculty, position, in both languages), prepared once
 * per list so typing in the search box only compares strings.
 */
export function searchKeys(people: Person[]): Map<string, string> {
  const names = (ref: UnitRef | null) => (ref ? Object.values(ref.name).join(" ") : "")
  return new Map(people.map(person => [person.id, searchText(
    [person.display_name, person.email, names(person.department), names(person.faculty), names(person.position)].join(" "))]))
}

/** The link to someone's page; keeps the organization, for people in several */
export const personPath = (userId: string, orgId: string) => `/people/${userId}?org=${orgId}`

const base = (orgId: string) => `/orgs/${orgId}`

/** A person's page (app/person_pages.py): their profile as colleagues see it */
export type PersonPage = {
  person: Person
  /** False: the profile is private, and only `person` is filled in */
  visible: boolean
  own: boolean
  /** The owner made it private (reviewers still see it, with a note) */
  private: boolean
  photo_url: string | null
  biography: Partial<Record<"en" | "ka", string>>
  /** Section id -> entries, newest first, without supporting documents */
  entries: Record<string, { id: string; values: Record<string, string> }[]>
  research: import("./profile-entries").ResearchOverview
  teaching: { interests: string[] }
  outputs: import("./research-outputs").ResearchOutput[]
  /** The CV builder's CV, when its owner made it public (private contact details and metrics already removed) */
  cv: unknown | null
}

export const peopleApi = {
  list: (orgId: string) => api<PeopleList>(`${base(orgId)}/people`),
  page: (orgId: string, userId: string) => api<PersonPage>(`${base(orgId)}/people/${userId}/page`),
  update: (orgId: string, userId: string, changes: { display_name?: string; department_id?: string | null; position_id?: string | null }) =>
    api<Person>(`${base(orgId)}/people/${userId}`, { method: "PATCH", body: changes }),
  setRoles: (orgId: string, userId: string, body: { roles: Role[]; coordinates_unit_id: string | null; reason: string | null }) =>
    api<Person>(`${base(orgId)}/people/${userId}/roles`, { method: "PUT", body }),
  deactivate: (orgId: string, userId: string, reason: string | null) =>
    api<Person>(`${base(orgId)}/people/${userId}/deactivate`, { method: "POST", body: { reason } }),
  reactivate: (orgId: string, userId: string) =>
    api<Person>(`${base(orgId)}/people/${userId}/reactivate`, { method: "POST", body: { reason: null } }),
}

/** Academic position (Professor, Associate Professor, ...), managed by Admins in the Structure tab */
export type Position = UnitRef & { holder_count: number }

export const positionsApi = {
  list: (orgId: string) => api<Position[]>(`${base(orgId)}/positions`),
  create: (orgId: string, name: { name_en: string; name_ka: string | null }) =>
    api<Position>(`${base(orgId)}/positions`, { method: "POST", body: name }),
  rename: (orgId: string, positionId: string, name: { name_en: string; name_ka: string | null }) =>
    api<Position>(`${base(orgId)}/positions/${positionId}`, { method: "PATCH", body: name }),
}

export type UnitInput = { name_en: string; name_ka: string | null; parent_id: string | null }

export const structureApi = {
  list: (orgId: string) => api<Unit[]>(`${base(orgId)}/units`),
  create: (orgId: string, kind: UnitKind, input: UnitInput) =>
    api<Unit>(`${base(orgId)}/units`, { method: "POST", body: { kind, ...input } }),
  update: (orgId: string, unitId: string, input: UnitInput) =>
    api<Unit>(`${base(orgId)}/units/${unitId}`, { method: "PATCH", body: input }),
}

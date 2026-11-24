import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router"
import { Check, Pencil, Plus, Search, UserCheck, UserX } from "lucide-react"
import { Button } from "@/components/ui/button"
import { FilterMenu, type FilterOption } from "@/components/forms/FilterMenu"
import { WorkspaceLayout } from "@/components/layout/WorkspaceLayout"
import "@/components/forms/forms.css"
import { initials, useSession, type Role } from "@/lib/auth"
import { ApiError } from "@/lib/api"
import { useLanguage } from "@/lib/language-context"
import {
  inUnits, localName, peopleApi, personPath, positionsApi, roleLabels, searchKeys, searchText, statusLabels, structureApi, unitFilterOptions,
  type Person, type PersonStatus, type Position, type Unit,
} from "@/lib/people"
import { ConfirmSheet } from "./ConfirmSheet"
import { PersonSheet } from "./PersonSheet"
import { PositionsPanel } from "./PositionsPanel"
import { ResearchOutputPanel } from "./ResearchOutputPanel"
import { EvaluationPeriodsPanel } from "./EvaluationPeriodsPanel"
import { StructurePanel } from "./StructurePanel"
import "./PeoplePage.css"

type Tab = "people" | "structure" | "periods" | "output"
type Dialog = { kind: "edit"; person: Person } | { kind: "deactivate"; person: Person } | { kind: "reactivate"; person: Person }
type Access = { orgId: string; canRegister: boolean; canManageRoles: boolean; editable: Set<string> }

const statusClass: Record<PersonStatus, string> = { active: "status-active", invited: "status-submitted", deactivated: "status-draft" }
const roleOptions: FilterOption[] = (Object.keys(roleLabels) as Role[]).map(role => ({ value: role, label: roleLabels[role] }))
const statusOptions: FilterOption[] = (Object.keys(statusLabels) as PersonStatus[]).map(status => ({ value: status, label: statusLabels[status] }))

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "Never"
}

/**
 * Everyone in the organization: open to all, so people can find colleagues and open their profiles.
 * Admins also see deactivated people, statuses and sign-ins, add people (Add people), deactivate and reactivate them,
 * and manage the structure. Coordinators correct the names of their own Researchers. The backend enforces the same.
 */
export function PeoplePage() {
  const session = useSession()
  const navigate = useNavigate()
  const { language } = useLanguage()
  const [params] = useSearchParams()
  const organizations = session?.organizations ?? []
  const [orgId, setOrgId] = useState(params.get("org") ?? organizations[0]?.id ?? "")
  const org = organizations.find(item => item.id === orgId) ?? organizations[0]
  const sessionAdmin = Boolean(session && org && (session.isRoot || org.roles.includes("admin")))
  const staff = Boolean(session && org && (session.isRoot || org.roles.includes("admin") || org.roles.includes("coordinator")))

  const [tab, setTab] = useState<Tab>("people")
  const [people, setPeople] = useState<Person[]>([])
  // What the server says this person may do here. Until it answers, the session's roles decide, so the page doesn't
  // first draw one view and then switch to another.
  const [access, setAccess] = useState<Access | null>(null)
  const known = access && access.orgId === org?.id ? access : null
  const canRegister = known?.canRegister ?? sessionAdmin
  const canManageRoles = known?.canManageRoles ?? sessionAdmin
  const editable = known?.editable ?? new Set<string>()
  const [units, setUnits] = useState<Unit[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState("")
  const [notice, setNotice] = useState("")
  const noticeTimer = useRef<number | undefined>(undefined)
  const [dialog, setDialog] = useState<Dialog | null>(null)

  // Filters, in the order they're shown: departments and faculties, then roles, then statuses (Admins)
  const [unitFilter, setUnitFilter] = useState<Set<string>>(new Set())
  const [roleFilter, setRoleFilter] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState("")
  // Typing stays instant: the list catches up with the search box as soon as React has a moment
  const deferredQuery = useDeferredValue(query)

  const load = useCallback(async () => {
    if (!org) return
    try {
      const [list, structure] = await Promise.all([peopleApi.list(org.id), structureApi.list(org.id)])
      setPeople(list.people)
      setAccess({ orgId: org.id, canRegister: list.can_register, canManageRoles: list.can_manage_roles, editable: new Set(list.editable) })
      setUnits(structure)
      setLoadError("")
      if (list.can_manage_roles) setPositions(await positionsApi.list(org.id)) // only Admins set positions
    } catch (cause) {
      setLoadError(cause instanceof ApiError ? cause.message : "Couldn't load people. Please try again.")
    } finally {
      setLoading(false)
    }
  }, [org])

  // eslint-disable-next-line react-hooks/set-state-in-effect -- loads from the server when the page opens
  useEffect(() => { void load() }, [load])
  useEffect(() => () => window.clearTimeout(noticeTimer.current), [])

  // Search keys are prepared once per list, not on every keystroke
  const keys = useMemo(() => searchKeys(people), [people])
  const unitOptions = useMemo(() => unitFilterOptions(units, language), [units, language])

  function announce(message: string) {
    setNotice(message)
    window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setNotice(""), 5000)
  }

  function finish(message: string) {
    setDialog(null)
    announce(message)
    void load()
  }

  const breadcrumb = [{ label: "People" }]
  if (!session || !org) {
    return (
      <WorkspaceLayout breadcrumb={breadcrumb}>
        {() => (
          <div className="dashboard-content">
            <div className="page-heading"><div><h1>People</h1></div></div>
            <div className="dashboard-card"><p>You aren't part of an organization in PEA yet. Ask your organization's PEA administrator.</p></div>
          </div>
        )}
      </WorkspaceLayout>
    )
  }

  const words = searchText(deferredQuery).split(" ").filter(Boolean)
  const visible = people.filter(person =>
    inUnits(person, unitFilter)
    && (roleFilter.size === 0 || person.roles.some(role => roleFilter.has(role)))
    && (!canManageRoles || statusFilter.size === 0 || statusFilter.has(person.status))
    && words.every(word => keys.get(person.id)?.includes(word)))
  const filtered = words.length > 0 || unitFilter.size > 0 || roleFilter.size > 0 || statusFilter.size > 0
  const actions = canRegister || editable.size > 0
  const columns = 3 + (canManageRoles ? 2 : 0) + (actions ? 1 : 0)

  return (
    <WorkspaceLayout breadcrumb={breadcrumb}>
      {() => (
        <div className="dashboard-content">
          <div className="page-heading">
            <div>
              <h1>People</h1>
              <p>
                {canManageRoles
                  ? `Everyone in ${localName(org.name, language)}: who can sign in, their roles, faculties and departments.`
                  : `Everyone in ${localName(org.name, language)}, with their departments and roles. Open someone to see their profile.`}
              </p>
            </div>
            <div className="page-actions">
              <span className="save-status" role="status">{notice && <><Check aria-hidden="true" />{notice}</>}</span>
              {organizations.length > 1 && (
                <select className="form-control org-select" aria-label="Organization" value={org.id} onChange={event => { setLoading(true); setOrgId(event.target.value) }}>
                  {organizations.map(item => <option key={item.id} value={item.id}>{localName(item.name, language)}</option>)}
                </select>
              )}
              {canRegister && tab === "people" && (
                <Button className="dashboard-button" onClick={() => navigate(`/admin/people/import?org=${org.id}`)}><Plus />Add people</Button>
              )}
            </div>
          </div>

          {(canManageRoles || staff) && (
            <div className="segmented people-tabs" role="tablist" aria-label="People sections">
              <button type="button" role="tab" aria-selected={tab === "people"} aria-checked={tab === "people"} onClick={() => setTab("people")}>People ({people.length})</button>
              {canManageRoles && <button type="button" role="tab" aria-selected={tab === "structure"} aria-checked={tab === "structure"} onClick={() => setTab("structure")}>Structure</button>}
              {canManageRoles && <button type="button" role="tab" aria-selected={tab === "periods"} aria-checked={tab === "periods"} onClick={() => setTab("periods")}>Evaluation periods</button>}
              {staff && <button type="button" role="tab" aria-selected={tab === "output"} aria-checked={tab === "output"} onClick={() => setTab("output")}>Research output</button>}
            </div>
          )}

          {loadError && (
            <div className="form-error-summary people-load-error" role="alert">
              {loadError} <Button variant="link" onClick={() => { setLoading(true); void load() }}>Try again</Button>
            </div>
          )}

          {tab === "periods" && canManageRoles ? (
            <EvaluationPeriodsPanel key={org.id} orgId={org.id} onChanged={finish} />
          ) : tab === "output" && staff ? (
            <ResearchOutputPanel key={org.id} orgId={org.id} units={units} canPickUnit={canManageRoles} />
          ) : tab === "structure" && canManageRoles ? (
            <>
              <StructurePanel orgId={org.id} units={units} onChanged={finish} />
              <PositionsPanel orgId={org.id} positions={positions} onChanged={finish} />
            </>
          ) : (
            <section className="dashboard-card" aria-labelledby="people-heading">
              <div className="card-heading">
                <h2 id="people-heading">People</h2>
                {filtered && !loading && <span className="people-count">{visible.length} of {people.length}</span>}
              </div>

              <div className="people-filters">
                <FilterMenu label="Departments" allLabel="All faculties and departments" options={unitOptions} selected={unitFilter} onChange={setUnitFilter} />
                <FilterMenu label="Roles" allLabel="All roles" options={roleOptions} selected={roleFilter} onChange={setRoleFilter} />
                {canManageRoles && <FilterMenu label="Statuses" allLabel="All statuses" options={statusOptions} selected={statusFilter} onChange={setStatusFilter} />}
                <div className="people-search">
                  <Search aria-hidden="true" />
                  <input className="form-control" type="search" placeholder="Search by name, email or department" aria-label="Search people"
                    value={query} onChange={event => setQuery(event.target.value)} />
                </div>
              </div>

              <div className="data-table-wrap">
                <table className="data-table people-table" data-compact={!canManageRoles || undefined}>
                  <thead>
                    <tr>
                      <th scope="col">Person</th><th scope="col">Department</th><th scope="col">Roles</th>
                      {canManageRoles && <><th scope="col">Status</th><th scope="col">Last sign-in</th></>}
                      {actions && <th scope="col"><span className="sr-only">Actions</span></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan={columns} className="data-table-empty">Loading…</td></tr>
                    ) : visible.length === 0 ? (
                      <tr><td colSpan={columns} className="data-table-empty">{filtered ? "No one matches these filters." : "No people yet."}</td></tr>
                    ) : visible.map(person => (
                      <tr key={person.id} data-inactive={person.status === "deactivated" || undefined}>
                        <td>
                          <Link className="researcher person-link" to={personPath(person.id, org.id)}>
                            <span className="researcher-avatar" aria-hidden="true">{initials(person.display_name)}</span>
                            <span className="person-name">
                              <span className="person-link-name">{person.display_name}</span>
                              <small>{person.email}</small>
                              {person.position && <small>{localName(person.position.name, language)}</small>}
                            </span>
                          </Link>
                        </td>
                        <td>
                          {person.department
                            ? <span className="person-name">{localName(person.department.name, language)}{person.faculty && <small>{localName(person.faculty.name, language)}</small>}</span>
                            : <span className="muted">None</span>}
                        </td>
                        <td>
                          <div className="role-chips">
                            {person.roles.map(role => (
                              <span key={role} className={`role-chip role-${role}`}>
                                {role === "coordinator" && person.coordinates ? `Coordinator: ${localName(person.coordinates.name, language)}` : roleLabels[role]}
                              </span>
                            ))}
                          </div>
                        </td>
                        {canManageRoles && (
                          <>
                            <td><span className={`status-badge ${statusClass[person.status]}`}>{statusLabels[person.status]}</span></td>
                            <td className="nowrap">{formatDate(person.last_login_at)}</td>
                          </>
                        )}
                        {actions && (
                          <td>
                            <div className="row-actions">
                              {editable.has(person.id) && (
                                <Button variant="outline" size="icon" className="icon-button" aria-label={`Edit ${person.display_name}`}
                                  onClick={() => setDialog({ kind: "edit", person })}><Pencil /></Button>
                              )}
                              {canRegister && (person.status === "deactivated" ? (
                                <Button variant="outline" size="icon" className="icon-button" aria-label={`Reactivate ${person.display_name}`}
                                  onClick={() => setDialog({ kind: "reactivate", person })}><UserCheck /></Button>
                              ) : (
                                <Button variant="outline" size="icon" className="icon-button danger" aria-label={`Deactivate ${person.display_name}`}
                                  disabled={person.id === session.id} title={person.id === session.id ? "You can't deactivate yourself" : undefined}
                                  onClick={() => setDialog({ kind: "deactivate", person })}><UserX /></Button>
                              ))}
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {dialog?.kind === "edit" && (
            <PersonSheet
              orgId={org.id}
              person={dialog.person}
              units={units}
              positions={positions}
              canManageRoles={canManageRoles}
              onClose={() => setDialog(null)}
              onSaved={(_, message) => finish(message)}
              onAddDepartment={() => { setDialog(null); setTab("structure") }}
            />
          )}
          {dialog?.kind === "deactivate" && (
            <ConfirmSheet
              title={`Deactivate ${dialog.person.display_name}?`}
              description="They'll be signed out right away and won't be able to sign in. Their data and history are kept, and they can be reactivated later. A Coordinator stops coordinating their department."
              confirmLabel="Deactivate"
              destructive
              askReason
              onClose={() => setDialog(null)}
              onConfirm={async reason => {
                await peopleApi.deactivate(org.id, dialog.person.id, reason)
                finish(`${dialog.person.display_name} was deactivated.`)
              }}
            />
          )}
          {dialog?.kind === "reactivate" && (
            <ConfirmSheet
              title={`Reactivate ${dialog.person.display_name}?`}
              description="They'll be able to sign in again with their previous roles. A former Coordinator needs to be made Coordinator again by an Admin."
              confirmLabel="Reactivate"
              onClose={() => setDialog(null)}
              onConfirm={async () => {
                await peopleApi.reactivate(org.id, dialog.person.id)
                finish(`${dialog.person.display_name} was reactivated.`)
              }}
            />
          )}
        </div>
      )}
    </WorkspaceLayout>
  )
}

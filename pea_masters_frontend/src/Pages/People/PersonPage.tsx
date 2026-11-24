import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router"
import { ArrowLeft, FileText, Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { WorkspaceLayout } from "@/components/layout/WorkspaceLayout"
import { initials, useSession } from "@/lib/auth"
import { ApiError } from "@/lib/api"
import { useLanguage } from "@/lib/language-context"
import { localName, peopleApi, roleLabels, type PersonPage as PageData } from "@/lib/people"
import { OUTPUT_KINDS, outputCitation } from "@/lib/research-outputs"
import { PublicProfile, type PublicProfileData } from "@/Pages/Profile/preview/PublicProfile"
import { profileSections } from "@/Pages/Profile/qualifications/sections"
import { buildCvSections } from "@/Pages/CvBuilder/cv-content"
import { normaliseCv } from "@/Pages/CvBuilder/cv-model"
import { CvPreview } from "@/Pages/CvBuilder/CvPreview"
import "@/Pages/CvBuilder/CvBuilderPage.css"
import "./PeoplePage.css"

/**
 * Someone's page, opened from the People page: their profile as colleagues see it. A private profile shows only
 * what the People page shows and says it's private, except to the person and those who review them.
 */
export function PersonPage() {
  const { userId = "" } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const session = useSession()
  const { language } = useLanguage()
  const orgId = params.get("org") ?? session?.organizations[0]?.id ?? ""
  // What was loaded, and for whom: opening another person shows "Loading…" until their page arrives
  const shown = `${orgId}/${userId}`
  const [loaded, setLoaded] = useState<{ for: string; page: PageData | null; error: string } | null>(null)
  const page = loaded?.for === shown ? loaded.page : null
  const error = loaded?.for === shown ? loaded.error : ""

  useEffect(() => {
    if (!orgId || !userId) return
    let cancelled = false
    const key = `${orgId}/${userId}`
    peopleApi.page(orgId, userId)
      .then(result => { if (!cancelled) setLoaded({ for: key, page: result, error: "" }) })
      .catch(cause => {
        if (cancelled) return
        setLoaded({ for: key, page: null, error: cause instanceof ApiError && cause.status === 404 ? "This person isn't in PEA, or is no longer active." :
          cause instanceof ApiError ? cause.message : "Couldn't load this profile. Please try again." })
      })
    return () => { cancelled = true }
  }, [orgId, userId])

  const organization = session?.organizations.find(org => org.id === orgId)
  const data = useMemo<PublicProfileData | null>(() => {
    if (!page) return null
    const { person } = page
    const preferred = language === "KA" ? "ka" : "en"
    const other = preferred === "ka" ? "en" : "ka"
    const lang = page.biography[preferred]?.trim() ? preferred : page.biography[other]?.trim() ? other : null
    const name = (ref: { name: Record<string, string> } | null) => (ref ? localName(ref.name, language) : "")
    return {
      name: person.display_name,
      initials: initials(person.display_name),
      photo: page.photo_url,
      place: [name(person.position), name(person.department), name(person.faculty)].filter(Boolean),
      organization: organization ? localName(organization.name, language) : "",
      email: person.email,
      biography: lang ? { html: page.biography[lang]!, lang } : null,
      qualifications: profileSections
        .map(section => ({ section, entries: (page.entries[section.id] ?? []).map(entry => ({ ...entry, documents: [] })) }))
        .filter(group => group.entries.length > 0),
      teaching: { interests: page.teaching.interests, programmes: [] },
      research: page.research,
      outputs: page.outputs.map(output => ({
        id: output.id,
        kind: OUTPUT_KINDS[output.kind]?.label ?? output.subtype,
        citation: outputCitation(output),
        link: output.doi ? `https://doi.org/${output.doi}` : output.url || null,
      })),
    }
  }, [page, language, organization])

  // The CV, built the way the CV builder's visitor view builds it
  const cv = useMemo(() => {
    if (!page?.cv || !data) return null
    const saved = normaliseCv(page.cv)
    if (!saved) return null
    const entries = Object.fromEntries(Object.entries(page.entries).map(([id, list]) => [id, list.map(entry => ({ ...entry, documents: [] }))]))
    const name = (ref: { name: Record<string, string> } | null) => (ref ? localName(ref.name, language) : "")
    const person = {
      fullName: page.person.display_name, email: page.person.email, organization: data.organization,
      position: name(page.person.position), department: name(page.person.department), faculty: name(page.person.faculty),
    }
    const familyName = page.person.display_name.trim().split(/\s+/).pop() ?? ""
    const sections = buildCvSections(saved, entries, { asVisitor: true, ownFamilyName: familyName, research: page.research, outputs: page.outputs })
    return { saved, sections, person }
  }, [page, data, language])

  const title = page?.person.display_name ?? "Profile"
  return (
    <WorkspaceLayout breadcrumb={[{ label: "People", to: `/people${orgId ? `?org=${orgId}` : ""}` }, { label: title }]}>
      {() => (
        <div className="dashboard-content person-page">
          <div className="page-actions person-page-actions">
            <Button variant="outline" className="dashboard-button" onClick={() => navigate(-1)}><ArrowLeft />Back</Button>
            {page?.own && <Button variant="outline" className="dashboard-button" onClick={() => navigate("/profile")}>Edit my profile</Button>}
          </div>

          {error && <div className="form-error-summary" role="alert">{error}</div>}
          {!page && !error && <p role="status" className="muted">Loading…</p>}

          {page && page.private && page.visible && (
            <div className="person-private-note" role="note">
              <Lock aria-hidden="true" />
              <span>{page.own
                ? "Your profile is private: only you, your organization's Admins and your Coordinator see this. Change it in Settings → Privacy."
                : `${page.person.display_name}'s profile is private. You see it because you review them.`}</span>
            </div>
          )}

          {page && !page.visible && (
            <section className="dashboard-card person-private" aria-labelledby="private-heading">
              <div className="profile-header-avatar" aria-hidden="true">{initials(page.person.display_name)}</div>
              <div>
                <h1 id="private-heading">{page.person.display_name}</h1>
                <p className="muted">
                  {[page.person.position, page.person.department, page.person.faculty].filter(Boolean).map(ref => localName(ref!.name, language)).join(" · ")}
                </p>
                <div className="role-chips">{page.person.roles.map(role => <span key={role} className={`role-chip role-${role}`}>{roleLabels[role]}</span>)}</div>
                <p className="person-private-message"><Lock aria-hidden="true" />{page.person.display_name} keeps their profile private, so only their department details are shown.</p>
              </div>
            </section>
          )}

          {page?.visible && data && (
            <PublicProfile data={data} />
          )}

          {page?.visible && cv && (
            <section className="person-cv" aria-labelledby="person-cv-heading">
              <h2 id="person-cv-heading"><FileText aria-hidden="true" />CV</h2>
              <div className="cv-paper-scroll person-cv-paper">
                <CvPreview cv={cv.saved} sections={cv.sections} person={cv.person} asVisitor />
              </div>
            </section>
          )}
          {page?.visible && !cv && page.own && (
            <p className="person-private-note" role="note">
              <Lock aria-hidden="true" />
              <span>Your CV isn't shown here because it's private or not saved yet. Make it public in the CV builder to show it.</span>
            </p>
          )}
        </div>
      )}
    </WorkspaceLayout>
  )
}

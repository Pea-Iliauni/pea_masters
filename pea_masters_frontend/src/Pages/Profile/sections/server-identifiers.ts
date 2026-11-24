import type { Identifiers } from "@/lib/profile"
import type { ProfileKey } from "@/Pages/CvBuilder/identifiers"

/** The CV builder's profile keys and the server's names for the same identifiers */
export const SERVER_IDENTIFIERS: { key: ProfileKey; server: keyof Identifiers; use: string }[] = [
  { key: "researcherId", server: "researcher_id", use: "Finds your articles in Web of Science." },
  { key: "orcid", server: "orcid", use: "Also used to find your articles." },
  { key: "scopus", server: "scopus_id", use: "Shown on your CV." },
]

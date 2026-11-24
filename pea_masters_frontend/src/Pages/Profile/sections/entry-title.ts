import type { Entry, SectionDef } from "../qualifications/sections"

export const entryTitle = (section: SectionDef, entry: Entry) => section.titleOf(entry.values) || `Untitled ${section.noun}`

import { useEffect, useState } from 'react'
import { ApiError } from '@/lib/api'
import { lookupCrossref, lookupDoi, lookupJournal, type CrossrefWork, type WosArticle, type WosJournal } from '@/lib/wos'
import type { WosCheck } from './evaluation-model'

const WAIT_MS = 600 // after the last keystroke

/** What PEA found out about a DOI: Web of Science first; if it isn't there, Crossref and the journal's indexing */
export type DoiCheck = { article: WosArticle; work?: CrossrefWork; journal?: WosJournal | null }

/**
 * Checks the DOI once typing stops: is the article in Web of Science? If not, is the DOI registered (Crossref), and is
 * its journal in Web of Science's journal list? The server caches every answer, so repeats are cheap.
 */
export function useDoiCheck(doi: string | null) {
  const [result, setResult] = useState<{ doi: string; check?: DoiCheck; error?: string } | null>(null)
  useEffect(() => {
    if (!doi) return
    let cancelled = false
    const run = async (): Promise<DoiCheck> => {
      const article = await lookupDoi(doi)
      if (article.found) return { article }
      // Not indexed: the extra details are a bonus, so their failures don't hide the Web of Science answer
      const work = await lookupCrossref(doi).catch(() => undefined)
      let journal: WosJournal | null | undefined
      if (work?.found && work.issns.length) {
        for (const issn of work.issns) {
          journal = await lookupJournal(issn).catch(() => undefined)
          if (journal?.found) break
        }
      }
      return { article, work, journal: journal ?? (work?.found && work.issns.length ? undefined : null) }
    }
    const timer = window.setTimeout(() => {
      run()
        .then(check => { if (!cancelled) setResult({ doi, check }) })
        .catch((cause: unknown) => { if (!cancelled) setResult({ doi, error: cause instanceof ApiError ? cause.message : "Web of Science couldn't be checked." }) })
    }, WAIT_MS)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [doi])
  const current = doi && result?.doi === doi ? result : null
  return { checking: !!doi && !current, check: current?.check, error: current?.error }
}

/** What's kept with the entry, so the list and the reviewer see the check without asking again */
export function toWosCheck({ article, work, journal }: DoiCheck): WosCheck {
  if (!article.found) return {
    doi: article.doi, found: false, checkedAt: article.checked_at,
    ...(work ? { registered: work.found } : {}),
    ...(journal ? { journalInWos: journal.found, journal: journal.name ?? work?.container_title ?? undefined } : {}),
  }
  return {
    doi: article.doi, found: true, checkedAt: article.checked_at,
    title: article.title ?? undefined, source: article.source_title ?? undefined, year: article.year ?? undefined,
    timesCited: article.times_cited ?? undefined, recordUrl: article.record_url ?? undefined,
    ...(article.includes_you === false ? { includesYou: false } : {}),
  }
}

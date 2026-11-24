import { cleanDoi, type ResearchOutput } from '@/lib/research-outputs'
import { findDoi, titleKey } from '@/lib/wos'
import type { EvaluationEntry } from './evaluation-model'

/** Whether a research output is already somewhere in the form: by DOI, or its title inside an entry's description */
export function outputInForm(output: ResearchOutput, entries: EvaluationEntry[]) {
  const title = titleKey(output.title)
  return entries.some(entry => {
    const doi = entry.wos?.doi ?? findDoi(entry.detail) ?? findDoi(entry.description)
    if (output.doi && doi && cleanDoi(doi) === output.doi) return true
    if (output.url && entry.detail.trim() === output.url) return true
    return title.length > 8 && titleKey(entry.description).includes(title)
  })
}

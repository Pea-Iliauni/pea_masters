/** The address of the editor for a form, a new form, or a copy */
export function editorPath(orgId: string, formId: string, copyOf?: string) {
  const query = new URLSearchParams({ org: orgId, ...(copyOf ? { copy: copyOf } : {}) })
  return `/admin/evaluation-forms/${encodeURIComponent(formId)}?${query}`
}

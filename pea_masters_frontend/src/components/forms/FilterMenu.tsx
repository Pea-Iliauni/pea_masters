import { Popover } from "@base-ui/react/popover"
import { Check, ChevronDown } from "lucide-react"
import "./filter-menu.css"

export type FilterOption = {
  value: string
  label: string
  /** Shown under this option and counted as chosen when it is (e.g. a department under its faculty) */
  parent?: string
}

/**
 * A filter where several values can be ticked, e.g. departments and faculties on the People page. Nothing ticked
 * means everything. Ticking a parent (a faculty) includes its children (departments), which show as ticked.
 */
export function FilterMenu({ label, allLabel, options, selected, onChange }: {
  label: string
  /** Button text while nothing is ticked, e.g. "All departments" */
  allLabel: string
  options: FilterOption[]
  selected: ReadonlySet<string>
  onChange: (next: Set<string>) => void
}) {
  const chosen = options.filter(option => selected.has(option.value))
  const text = chosen.length === 0 ? allLabel : chosen.length === 1 ? chosen[0].label : `${label}: ${chosen.length}`

  function toggle(value: string) {
    const next = new Set(selected)
    if (next.has(value)) next.delete(value)
    else {
      next.add(value)
      // A ticked parent already includes its children
      for (const option of options) if (option.parent === value) next.delete(option.value)
    }
    onChange(next)
  }

  return (
    <Popover.Root>
      <Popover.Trigger className="form-control filter-menu-trigger" data-active={chosen.length > 0 || undefined} aria-label={`${label}: ${text}`}>
        <span className="filter-menu-text">{text}</span>
        <ChevronDown aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="start" className="filter-menu-positioner">
          <Popover.Popup className="filter-menu-popup" aria-label={label}>
            <div className="filter-menu-head">
              <span>{label}</span>
              {chosen.length > 0 && <button type="button" className="filter-menu-clear" onClick={() => onChange(new Set())}>Clear</button>}
            </div>
            {options.length === 0 ? <p className="filter-menu-empty">Nothing to choose from yet.</p> : (
              <ul className="filter-menu-list">
                {options.map(option => {
                  const implied = option.parent !== undefined && selected.has(option.parent)
                  const checked = implied || selected.has(option.value)
                  return (
                    <li key={option.value}>
                      <label className="filter-menu-option" data-child={option.parent !== undefined || undefined} data-implied={implied || undefined}
                        title={implied ? "Included: its faculty is ticked" : undefined}>
                        <input type="checkbox" className="form-checkbox" checked={checked} disabled={implied} onChange={() => toggle(option.value)} />
                        <span>{option.label}</span>
                        {checked && !implied && <Check aria-hidden="true" className="filter-menu-tick" />}
                      </label>
                    </li>
                  )
                })}
              </ul>
            )}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}

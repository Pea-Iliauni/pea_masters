import * as React from "react"

// Below this width the sidebar becomes a slide-out sheet (tablets and phones); keep in sync with --breakpoint-lg
const MOBILE_BREAKPOINT = 992
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

const subscribe = (onChange: () => void) => {
  const mql = window.matchMedia(QUERY)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

export function useIsMobile() {
  return React.useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => false)
}

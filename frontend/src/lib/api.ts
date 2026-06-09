// Single source of truth for the API origin.
//
// - If VITE_API_URL is set (e.g. pointing at a separately hosted full backend),
//   use it verbatim.
// - Otherwise use localhost in dev, and a relative origin in production so the
//   deployed app calls its own Vercel functions (/api/*) and static assets
//   (/static/*) on the same domain.
const explicit = import.meta.env.VITE_API_URL
export const API_BASE: string =
  explicit !== undefined && explicit !== ''
    ? explicit
    : import.meta.env.DEV
      ? 'http://localhost:8000'
      : ''

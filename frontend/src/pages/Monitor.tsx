import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { API_BASE } from '../lib/api'

interface MonitorRun {
  id: number
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  status: 'running' | 'success' | 'failure' | null
  triggered_by: string | null
  error_message: string | null
  sections_checked: number
  web_drift_count: number
  pdf_match: boolean | null
  pdf_drift_count: number
  drift_count: number
  drift_details?: DriftRow[] | null
}

interface DriftRow {
  section_key: string
  section_title: string
  kind: string
  web_changed: boolean
  pdf_match: boolean | null
  summary: string
  url: string
  // Populated by the backend for runs recorded after the diff/regen feature
  // shipped. Optional so older `MonitorRun.drift_details` rows still parse.
  old_content?: string | null
  new_content?: string | null
  diff_unified?: string | null
  change_summary?: string | null
}

interface ApplyJob {
  id: number
  monitor_run_id: number
  section_key: string
  section_title: string
  video_id: number | null
  action: 'update' | 'create'
  status: 'queued' | 'running' | 'success' | 'failed'
  error_message: string | null
  created_at: string | null
  finished_at: string | null
}

interface RunsResponse {
  total: number
  latest: MonitorRun | null
  runs: MonitorRun[]
  pdf_baseline_available: boolean
}

const TERMINAL_JOB_STATUSES: ApplyJob['status'][] = ['success', 'failed']

function formatDate(iso: string | null) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function StatusPill({ status }: { status: MonitorRun['status'] }) {
  const styles: Record<string, string> = {
    success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    failure: 'bg-red-500/15 text-red-300 border-red-500/30',
    running: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  }
  const cls = (status && styles[status]) || 'bg-gray-700/40 text-gray-300 border-gray-600'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${
        status === 'success' ? 'bg-emerald-400'
          : status === 'failure' ? 'bg-red-400'
          : status === 'running' ? 'bg-amber-400 animate-pulse'
          : 'bg-gray-400'
      }`} />
      {status || 'unknown'}
    </span>
  )
}

function MatchPill({ run }: { run: MonitorRun }) {
  if (run.status === 'failure') {
    return <span className="text-xs text-gray-500 italic">n/a (failure)</span>
  }
  if (run.pdf_match === null || run.pdf_match === undefined) {
    return <span className="text-xs text-gray-400">PDF baseline unavailable</span>
  }
  if (run.pdf_match && run.web_drift_count === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        Exact match
      </span>
    )
  }
  const parts: string[] = []
  if (run.web_drift_count > 0) parts.push(`${run.web_drift_count} web change(s)`)
  if (run.pdf_drift_count > 0) parts.push(`${run.pdf_drift_count} PDF mismatch(es)`)
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
      {parts.join(' · ') || 'Differences found'}
    </span>
  )
}

export default function Monitor() {
  const { token, user, isAdmin, loading: authLoading, authFetch } = useAuth()

  const [runs, setRuns] = useState<MonitorRun[]>([])
  const [latest, setLatest] = useState<MonitorRun | null>(null)
  const [pdfBaseline, setPdfBaseline] = useState(true)
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [runError, setRunError] = useState<string | null>(null)
  const [expandedRun, setExpandedRun] = useState<number | null>(null)
  const [expandedDrift, setExpandedDrift] = useState<DriftRow[] | null>(null)
  const [triggering, setTriggering] = useState(false)

  // -- Apply-changes state, scoped to the currently expanded run --
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [visibleDiffs, setVisibleDiffs] = useState<Set<string>>(new Set())
  const [expandedJobs, setExpandedJobs] = useState<ApplyJob[] | null>(null)
  const [applyBusy, setApplyBusy] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)

  const fetchRuns = useCallback(async () => {
    if (!token) return
    try {
      const res = await authFetch(`${API_BASE}/api/monitor/runs?limit=50`)
      if (res.status === 401) {
        // authFetch already cleared the session; the auth gate below will
        // re-render with the "Sign in required" view.
        return
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: RunsResponse = await res.json()
      setRuns(data.runs)
      setLatest(data.latest)
      setPdfBaseline(data.pdf_baseline_available)
      setRunError(null)
    } catch (err: any) {
      setRunError(err.message || 'Failed to load monitor runs')
    } finally {
      setLoadingRuns(false)
    }
  }, [token, authFetch])

  useEffect(() => {
    if (!authLoading && isAdmin) {
      fetchRuns()
    }
  }, [authLoading, isAdmin, fetchRuns])

  // Auto-refresh while a run is in progress.
  useEffect(() => {
    const hasRunning = runs.some((r) => r.status === 'running') || triggering
    if (!hasRunning) return
    const t = setInterval(() => fetchRuns(), 4000)
    return () => clearInterval(t)
  }, [runs, triggering, fetchRuns])

  const handleTrigger = async () => {
    setTriggering(true)
    try {
      const res = await authFetch(`${API_BASE}/api/monitor/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      if (res.status === 401) return
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await new Promise((r) => setTimeout(r, 800))
      await fetchRuns()
    } catch (err: any) {
      setRunError(err.message || 'Failed to trigger check')
    } finally {
      setTriggering(false)
    }
  }

  const fetchJobsFor = useCallback(
    async (runId: number) => {
      try {
        const res = await authFetch(`${API_BASE}/api/monitor/runs/${runId}/jobs`)
        if (res.status === 401 || !res.ok) return
        const data: { jobs: ApplyJob[] } = await res.json()
        setExpandedJobs(data.jobs || [])
      } catch {
        // Polling failures are silent; the UI keeps the last known status.
      }
    },
    [authFetch]
  )

  const expandRun = async (runId: number) => {
    if (expandedRun === runId) {
      setExpandedRun(null)
      setExpandedDrift(null)
      setExpandedJobs(null)
      setSelectedKeys(new Set())
      setVisibleDiffs(new Set())
      setApplyError(null)
      return
    }
    setExpandedRun(runId)
    setExpandedDrift(null)
    setExpandedJobs(null)
    setSelectedKeys(new Set())
    setVisibleDiffs(new Set())
    setApplyError(null)
    try {
      const res = await authFetch(`${API_BASE}/api/monitor/runs/${runId}`)
      if (res.status === 401) return
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: MonitorRun = await res.json()
      setExpandedDrift(data.drift_details || [])
      // Fire and forget; the polling effect below will keep this current.
      fetchJobsFor(runId)
    } catch {
      setExpandedDrift([])
    }
  }

  // Poll job statuses every 3s while any apply-changes job for the expanded
  // run is still queued or running.
  useEffect(() => {
    if (expandedRun === null || !expandedJobs) return
    const hasPending = expandedJobs.some(
      (j) => !TERMINAL_JOB_STATUSES.includes(j.status)
    )
    if (!hasPending) return
    const runId = expandedRun
    const t = setInterval(() => fetchJobsFor(runId), 3000)
    return () => clearInterval(t)
  }, [expandedRun, expandedJobs, fetchJobsFor])

  const toggleSelect = useCallback((key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleDiff = useCallback((key: string) => {
    setVisibleDiffs((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const applyChanges = async () => {
    if (expandedRun === null || selectedKeys.size === 0) return
    setApplyBusy(true)
    setApplyError(null)
    try {
      const res = await authFetch(
        `${API_BASE}/api/monitor/runs/${expandedRun}/apply-changes`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section_keys: Array.from(selectedKeys) }),
        }
      )
      if (res.status === 401) return
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || `HTTP ${res.status}`)
      }
      const data: { jobs: ApplyJob[] } = await res.json()
      // Merge fresh jobs into the existing list (newer rows for the same key
      // win, since the backend orders ascending and we want latest-first
      // selection in the pill renderer).
      setExpandedJobs((prev) => {
        const merged = [...(prev || []), ...(data.jobs || [])]
        return merged
      })
      setSelectedKeys(new Set())
    } catch (err: any) {
      setApplyError(err.message || 'Failed to apply changes')
    } finally {
      setApplyBusy(false)
    }
  }

  // Latest job per section_key (for status pill rendering).
  const jobsByKey = (() => {
    const map = new Map<string, ApplyJob>()
    if (!expandedJobs) return map
    for (const j of expandedJobs) {
      const prev = map.get(j.section_key)
      if (!prev || (j.id || 0) > (prev.id || 0)) map.set(j.section_key, j)
    }
    return map
  })()

  // -------- Auth gates --------
  if (authLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-gray-400">
        Loading...
      </div>
    )
  }
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
        <h1 className="text-2xl font-bold text-white mb-2">Sign in required</h1>
        <p className="text-gray-400 mb-6">The Monitor page is only available to admins.</p>
        <Link to="/login" className="px-4 py-2 rounded-lg bg-gradient-to-r from-brand-purple-light to-brand-teal text-white font-semibold">
          Sign In
        </Link>
      </div>
    )
  }
  if (!isAdmin) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-500/10 border border-red-500/30 mb-4">
          <span className="text-red-400 text-2xl">!</span>
        </div>
        <h1 className="text-2xl font-bold text-white mb-2">Admins only</h1>
        <p className="text-gray-400">
          The Monitor page is restricted to the <span className="text-brand-teal">Admin</span> role.
        </p>
      </div>
    )
  }

  // -------- Page --------
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-brand-purple-light to-brand-teal bg-clip-text text-transparent">
            Content Monitor
          </h1>
          <p className="text-gray-400 mt-1.5 max-w-2xl text-sm">
            An optional agent that periodically checks a configured docs source for
            drift and logs every run with a verdict. It is disabled in this demo
            (set <code className="text-brand-teal">MONITOR_ENABLED</code> and{' '}
            <code className="text-brand-teal">MONITOR_SOURCE_URL</code> to enable it).
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!pdfBaseline && (
            <span className="text-xs px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/30">
              PDF baseline not loaded
            </span>
          )}
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-brand-purple-light to-brand-teal text-white font-medium text-sm hover:opacity-90 disabled:opacity-50"
          >
            {triggering ? 'Triggering...' : 'Run check now'}
          </button>
        </div>
      </header>

      {/* Latest summary cards */}
      {latest && (
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SummaryCard label="Last run" value={formatDate(latest.started_at)} sub={latest.triggered_by || ''} />
          <SummaryCard
            label="Status"
            valueNode={<StatusPill status={latest.status} />}
            sub={latest.duration_seconds != null ? `${latest.duration_seconds.toFixed(1)} s` : '-'}
          />
          <SummaryCard
            label="PDF vs Website"
            valueNode={<MatchPill run={latest} />}
            sub={`${latest.sections_checked} section(s) checked`}
          />
        </section>
      )}

      {/* Run log */}
      <section className="bg-gray-900/50 border border-gray-800 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Check history</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Every scheduled and manual content check is logged here.
            </p>
          </div>
          <button
            onClick={() => fetchRuns()}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-300 hover:text-white hover:border-gray-500"
          >
            Refresh
          </button>
        </div>

        {loadingRuns ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading run history...</div>
        ) : runError ? (
          <div className="p-6 text-red-400 text-sm">Failed to load runs: {runError}</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-gray-500 text-sm">
            No checks have been recorded yet. Click <span className="text-brand-teal">Run check now</span> to trigger one.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="text-left px-6 py-3 font-semibold">When</th>
                  <th className="text-left px-6 py-3 font-semibold">Status</th>
                  <th className="text-left px-6 py-3 font-semibold">PDF vs Website</th>
                  <th className="text-left px-6 py-3 font-semibold">Sections</th>
                  <th className="text-left px-6 py-3 font-semibold">Trigger</th>
                  <th className="px-3 py-3 w-12"></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <RunRow
                    key={r.id}
                    run={r}
                    expanded={expandedRun === r.id}
                    drift={expandedRun === r.id ? expandedDrift : null}
                    onExpand={() => expandRun(r.id)}
                    selectedKeys={expandedRun === r.id ? selectedKeys : new Set<string>()}
                    onToggleSelect={toggleSelect}
                    visibleDiffs={expandedRun === r.id ? visibleDiffs : new Set<string>()}
                    onToggleDiff={toggleDiff}
                    jobsByKey={expandedRun === r.id ? jobsByKey : new Map<string, ApplyJob>()}
                    onApply={applyChanges}
                    applyBusy={applyBusy}
                    applyError={expandedRun === r.id ? applyError : null}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

// ---------- subcomponents ----------

function SummaryCard({
  label, value, valueNode, sub,
}: {
  label: string
  value?: string
  valueNode?: React.ReactNode
  sub?: string
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
      <div className="text-[11px] text-gray-500 uppercase tracking-wider font-semibold">{label}</div>
      <div className="mt-1.5 text-base text-white font-medium min-h-[28px]">
        {valueNode || value || '-'}
      </div>
      {sub && <div className="mt-1 text-xs text-gray-400 truncate">{sub}</div>}
    </div>
  )
}

function DiffPane({ diff }: { diff: string }) {
  const lines = diff.split('\n')
  return (
    <pre className="mt-2 text-[11px] font-mono leading-snug overflow-x-auto p-3 rounded-lg bg-black/40 border border-gray-800 max-h-80">
      {lines.map((line, i) => {
        let cls = 'text-gray-400'
        if (line.startsWith('+++') || line.startsWith('---')) cls = 'text-gray-500'
        else if (line.startsWith('@@')) cls = 'text-purple-300'
        else if (line.startsWith('+')) cls = 'text-emerald-300'
        else if (line.startsWith('-')) cls = 'text-red-300'
        return (
          <div key={i} className={cls}>
            {line || '\u00A0'}
          </div>
        )
      })}
    </pre>
  )
}

function JobStatusPill({ job }: { job: ApplyJob }) {
  const map: Record<ApplyJob['status'], { cls: string; label: string }> = {
    queued: { cls: 'bg-gray-700/40 text-gray-300 border-gray-600', label: 'queued' },
    running: { cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30 animate-pulse', label: 'regenerating' },
    success: { cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', label: 'done' },
    failed: { cls: 'bg-red-500/15 text-red-300 border-red-500/30', label: 'failed' },
  }
  const cfg = map[job.status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${cfg.cls}`}
      title={job.error_message || undefined}
    >
      <span className="capitalize">{job.action}</span>
      <span>·</span>
      <span>{cfg.label}</span>
      {job.video_id && job.status === 'success' && (
        <Link to={`/watch/${job.video_id}`} className="underline hover:text-white ml-1">
          video #{job.video_id}
        </Link>
      )}
    </span>
  )
}

function RunRow({
  run, expanded, drift, onExpand,
  selectedKeys, onToggleSelect,
  visibleDiffs, onToggleDiff,
  jobsByKey, onApply, applyBusy, applyError,
}: {
  run: MonitorRun
  expanded: boolean
  drift: DriftRow[] | null
  onExpand: () => void
  selectedKeys: Set<string>
  onToggleSelect: (key: string) => void
  visibleDiffs: Set<string>
  onToggleDiff: (key: string) => void
  jobsByKey: Map<string, ApplyJob>
  onApply: () => void
  applyBusy: boolean
  applyError: string | null
}) {
  return (
    <>
      <tr className="border-t border-gray-800 hover:bg-gray-900/40 transition-colors">
        <td className="px-6 py-3 text-gray-200 whitespace-nowrap">
          <div>{formatDate(run.started_at)}</div>
          <div className="text-[11px] text-gray-500">
            {run.duration_seconds != null ? `${run.duration_seconds.toFixed(1)} s` : 'in progress'}
          </div>
        </td>
        <td className="px-6 py-3">
          <StatusPill status={run.status} />
          {run.error_message && (
            <div className="mt-1 text-[11px] text-red-400 max-w-xs truncate" title={run.error_message}>
              {run.error_message.split('\n')[0]}
            </div>
          )}
        </td>
        <td className="px-6 py-3">
          <MatchPill run={run} />
        </td>
        <td className="px-6 py-3 text-gray-300">
          {run.sections_checked}
          {run.drift_count > 0 && (
            <span className="ml-2 text-amber-300 text-xs">({run.drift_count} drift)</span>
          )}
        </td>
        <td className="px-6 py-3 text-xs text-gray-400">{run.triggered_by}</td>
        <td className="px-3 py-3 text-right">
          <button
            onClick={onExpand}
            className="text-gray-400 hover:text-white text-xs px-2 py-1 rounded border border-gray-700 hover:border-gray-500"
          >
            {expanded ? '▲' : '▼'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-gray-800 bg-gray-950/50">
          <td colSpan={6} className="px-6 py-4">
            {run.error_message && (
              <div className="mb-3 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-300 whitespace-pre-wrap">
                {run.error_message}
              </div>
            )}
            {drift === null ? (
              <div className="text-xs text-gray-500">Loading details...</div>
            ) : drift.length === 0 ? (
              <div className="text-xs text-gray-500">
                {run.status === 'success'
                  ? 'No drift recorded - website matched the PDF baseline.'
                  : 'No drift detail available.'}
              </div>
            ) : (
              <>
                <div className="grid gap-2">
                  {drift.map((d) => {
                    const job = jobsByKey.get(d.section_key) || null
                    const isSelected = selectedKeys.has(d.section_key)
                    const diffOpen = visibleDiffs.has(d.section_key)
                    const canApply = d.web_changed || d.kind === 'first_seen'
                    return (
                      <div key={d.section_key} className="p-3 rounded-lg bg-gray-900/70 border border-gray-800">
                        <div className="flex items-start justify-between gap-3 flex-wrap">
                          <div className="flex items-start gap-3 min-w-0">
                            {canApply && (
                              <input
                                type="checkbox"
                                className="mt-1 h-4 w-4 rounded border-gray-600 bg-gray-800 text-brand-teal focus:ring-brand-teal"
                                checked={isSelected}
                                onChange={() => onToggleSelect(d.section_key)}
                                aria-label={`Select ${d.section_title} for video regen`}
                              />
                            )}
                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-white">{d.section_title}</div>
                              <div className="text-[11px] text-gray-500 font-mono">{d.section_key}</div>
                            </div>
                          </div>
                          <div className="flex gap-1.5 flex-wrap items-center">
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/30 capitalize">
                              {d.kind.replace(/_/g, ' ')}
                            </span>
                            <span className={`text-[11px] px-2 py-0.5 rounded-full border ${
                              d.web_changed
                                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                : 'bg-gray-700/30 text-gray-400 border-gray-700'
                            }`}>
                              web {d.web_changed ? 'changed' : 'unchanged'}
                            </span>
                            <span className={`text-[11px] px-2 py-0.5 rounded-full border ${
                              d.pdf_match === true
                                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                                : d.pdf_match === false
                                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                  : 'bg-gray-700/30 text-gray-400 border-gray-700'
                            }`}>
                              PDF {d.pdf_match === true ? 'match' : d.pdf_match === false ? 'differs' : 'n/a'}
                            </span>
                            {job && <JobStatusPill job={job} />}
                          </div>
                        </div>

                        {d.web_changed && (
                          <div className="mt-2 p-2.5 rounded-lg bg-brand-teal/5 border border-brand-teal/20">
                            <div className="text-[11px] uppercase tracking-wider text-brand-teal/80 font-semibold">
                              What changed
                            </div>
                            <div className="mt-0.5 text-xs text-gray-200">
                              {d.change_summary || (
                                <span className="text-gray-500 italic">
                                  Summary unavailable (LLM offline). Use the diff below.
                                </span>
                              )}
                            </div>
                          </div>
                        )}

                        {d.summary && (
                          <div className="mt-2 text-xs text-gray-400">PDF compare: {d.summary}</div>
                        )}

                        <div className="mt-2 flex items-center gap-3 flex-wrap">
                          {d.url && (
                            <a
                              href={d.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[11px] text-brand-teal hover:underline"
                            >
                              Open source page →
                            </a>
                          )}
                          {d.diff_unified && (
                            <button
                              onClick={() => onToggleDiff(d.section_key)}
                              className="text-[11px] px-2 py-0.5 rounded border border-gray-700 text-gray-300 hover:text-white hover:border-gray-500"
                            >
                              {diffOpen ? 'Hide diff' : 'Show diff'}
                            </button>
                          )}
                          {job?.status === 'failed' && job.error_message && (
                            <span
                              className="text-[11px] text-red-400 truncate max-w-md"
                              title={job.error_message}
                            >
                              {job.error_message.split('\n')[0]}
                            </span>
                          )}
                        </div>

                        {diffOpen && d.diff_unified && <DiffPane diff={d.diff_unified} />}
                      </div>
                    )
                  })}
                </div>

                {/* Sticky-ish action bar for the apply-changes flow */}
                <div className="mt-4 flex items-center justify-between gap-3 flex-wrap p-3 rounded-lg bg-gray-900/60 border border-gray-800">
                  <div className="text-xs text-gray-400">
                    {selectedKeys.size === 0
                      ? 'Tick the sections whose videos you want to regenerate or create.'
                      : `${selectedKeys.size} section${selectedKeys.size === 1 ? '' : 's'} selected.`}
                    {applyError && (
                      <span className="ml-2 text-red-400">· {applyError}</span>
                    )}
                  </div>
                  <button
                    onClick={onApply}
                    disabled={selectedKeys.size === 0 || applyBusy}
                    className="px-4 py-2 rounded-lg bg-gradient-to-r from-brand-purple-light to-brand-teal text-white text-sm font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {applyBusy
                      ? 'Queueing...'
                      : `Apply changes to ${selectedKeys.size} video${selectedKeys.size === 1 ? '' : 's'}`}
                  </button>
                </div>
              </>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAssignmentGroups, fetchDashboardStats, fetchDashboardTickets, fetchTicket } from '../api'
import TicketCard from './TicketCard'

const MY_TEAM_GROUPS = ['SAP EWM Support', 'Integration Middleware', 'QMS Compliance Ops']
const typeTabs = [
  { id: 'ALL', label: 'All Items' },
  { id: 'INC', label: 'Incidents (INC)' },
  { id: 'RITM', label: 'Service Requests (RITM)' },
  { id: 'PRB', label: 'Problems (PRB)' },
  { id: 'CHG', label: 'Changes (CHG)' },
]
const healthStyles = {
  RED: 'bg-rose-500/15 text-rose-300 ring-rose-400/30',
  YELLOW: 'bg-amber-500/15 text-amber-200 ring-amber-400/30',
  GREEN: 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/30',
}
const closedTaskStates = new Set(['Closed', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped', 'Canceled'])
// The canonical mock dataset reports through 2026-10-08. Keeping the stale
// comparison aligned to that reporting snapshot makes the dashboard stable.
const operationalReferenceTime = Date.parse('2026-10-08T12:00:00Z')

function pendingTasks(tasks = []) {
  return tasks.filter((task) => !closedTaskStates.has(task.state))
}

function latestActivityAt(ticket) {
  const entries = [...(ticket.comments || []), ...(ticket.work_notes || [])]
  const timestamps = entries
    .map((entry) => Date.parse(String(entry.sys_created_on || '').replace(' ', 'T')))
    .filter(Number.isFinite)
  return timestamps.length ? Math.max(...timestamps) : null
}

function problemIsStale(ticket) {
  if (ticket.type !== 'PRB') return false
  const lastActivity = latestActivityAt(ticket)
  const olderThanSevenDays = lastActivity !== null && operationalReferenceTime - lastActivity > 7 * 24 * 60 * 60 * 1000
  return olderThanSevenDays || pendingTasks(ticket.ptasks).length > 0
}

function urgencyRank(ticket) {
  const remaining = slaRemainingMinutes(ticket)
  const breached = ticket.is_breached || (typeof remaining === 'number' && remaining <= 0)
  const nearBreach = typeof remaining === 'number' && remaining > 0 && remaining <= 90
  const frustrated = ticket.sentiment === 'Frustrated' || ticket.customer_sentiment?.status === 'Frustrated'
  if (['INC', 'RITM'].includes(ticket.type) && breached && frustrated) return 0
  if (['INC', 'RITM'].includes(ticket.type) && breached) return 1
  if (['INC', 'RITM'].includes(ticket.type) && nearBreach && frustrated) return 2
  if (['INC', 'RITM'].includes(ticket.type) && (nearBreach || frustrated)) return 3
  if (problemIsStale(ticket)) return 10
  if (ticket.type === 'CHG' && pendingTasks(ticket.ctasks).length > 0) return 20
  return 30
}

function sortByOperationalUrgency(left, right) {
  const rankDifference = urgencyRank(left) - urgencyRank(right)
  if (rankDifference) return rankDifference
  const leftRemaining = slaRemainingMinutes(left)
  const rightRemaining = slaRemainingMinutes(right)
  if (typeof leftRemaining === 'number' && typeof rightRemaining === 'number' && leftRemaining !== rightRemaining) return leftRemaining - rightRemaining
  if (left.type === 'PRB' && right.type === 'PRB') return (latestActivityAt(left) || 0) - (latestActivityAt(right) || 0)
  return String(left.number || left.id).localeCompare(String(right.number || right.id))
}

function hasOperationalWarning(tickets = []) {
  return tickets.some((ticket) => (
    urgencyRank(ticket) < 10
    || problemIsStale(ticket)
    || (ticket.type === 'CHG' && pendingTasks(ticket.ctasks).length > 0)
  ))
}

function slaRemainingMinutes(ticket) {
  return ticket.sla_remaining_minutes ?? ticket.sla_remaining_mins
}

function SlaBadge({ ticket }) {
  const remaining = slaRemainingMinutes(ticket)
  if (typeof remaining !== 'number') return null
  const isBreached = ticket.is_breached || remaining <= 0
  if (isBreached) return <span className="inline-flex rounded-full border border-rose-500/50 bg-rose-950/60 px-2 py-1 text-xs font-bold text-rose-200">🚨 Breached ({Math.abs(remaining)}m overdue) · {ticket.breach_reason}</span>
  const styles = remaining <= 90 ? 'border-amber-500/50 bg-amber-950/60 text-amber-200' : 'border-emerald-500/50 bg-emerald-950/60 text-emerald-200'
  return <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${styles}`}>⏳ {remaining}m remaining</span>
}

function ContextMetrics({ ticket }) {
  const holdReason = ticket.state === 'On Hold' ? ticket.hold_reason : null
  const holdReasonLine = holdReason && <p className="font-semibold text-amber-200"><span className="text-slate-500">On Hold ·</span> {holdReason}</p>
  if (ticket.type === 'INC' || ticket.type === 'RITM') return <div className="space-y-1 text-xs text-slate-300">{holdReasonLine}<p><span className="text-slate-500">Sentiment:</span> {ticket.sentiment}</p></div>
  if (ticket.type === 'PRB') return <div className="space-y-1 text-xs text-slate-300">{holdReasonLine}<p><span className="text-slate-500">RCA phase:</span> {ticket.rca_phase}</p><p><span className="text-slate-500">Risk:</span> {ticket.risk_level}</p></div>
  return <div className="space-y-1 text-xs text-slate-300">{holdReasonLine}<p><span className="text-slate-500">CAB status:</span> {ticket.cab_status}</p><p><span className="text-slate-500">Risk:</span> {ticket.risk_level}</p></div>
}

function hasDetailFields(ticket) {
  return Boolean(ticket && Array.isArray(ticket.comments) && Array.isArray(ticket.work_notes) && Array.isArray(ticket.knowledge_refs) && Array.isArray(ticket.historical_tickets) && Object.prototype.hasOwnProperty.call(ticket, 'agent_analysis'))
}

function AssigneeBriefing({ assignee, tickets, analysis, onClose }) {
  const urgentItems = tickets.filter((ticket) => urgencyRank(ticket) < 10)
  const staleProblems = tickets.filter(problemIsStale)
  const pendingChanges = tickets.filter((ticket) => ticket.type === 'CHG' && pendingTasks(ticket.ctasks).length > 0)
  const agentFindings = analysis?.findings || []
  const urgentFinding = agentFindings.find((finding) => finding.id === 'assignee-risk-priority')
  const problemFinding = agentFindings.find((finding) => finding.id === 'assignee-stale-problems')
  const changeFinding = agentFindings.find((finding) => finding.id === 'assignee-pending-changes')
  const ageLabel = (ticket) => {
    const lastActivity = latestActivityAt(ticket)
    if (!lastActivity) return 'No activity timestamp'
    return `${Math.max(0, Math.floor((operationalReferenceTime - lastActivity) / (24 * 60 * 60 * 1000)))}d since update`
  }
  return <div className="fixed inset-0 z-40 grid place-items-center bg-slate-950/75 p-4 backdrop-blur-sm" role="presentation" onMouseDown={onClose}>
    <section role="dialog" aria-modal="true" aria-label={`${assignee} operational briefing`} className="w-full max-w-3xl rounded-2xl border border-cyan-500/35 bg-slate-900 p-6 shadow-2xl shadow-slate-950/70" onMouseDown={(event) => event.stopPropagation()}>
      <div className="flex items-start justify-between gap-4 border-b border-slate-700 pb-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">Assignee operational briefing</p><h2 className="mt-2 text-2xl font-semibold text-slate-50">{assignee}</h2><p className="mt-1 text-sm text-slate-400">{analysis?.summary || `${tickets.length} ticket${tickets.length === 1 ? '' : 's'} in the active dashboard scope, ordered by operational urgency.`}</p></div><button type="button" onClick={onClose} aria-label="Close operational briefing" className="rounded-full border border-slate-600 px-3 py-1.5 text-sm text-slate-200 transition hover:border-cyan-400 hover:bg-slate-800">×</button></div>
      <div className="mt-5 grid gap-4 md:grid-cols-3"><section className="rounded-xl border border-rose-500/35 bg-rose-950/20 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-rose-200">Urgent incidents</p><p className="mt-2 text-3xl font-semibold text-rose-100">{urgentItems.length}</p>{urgentFinding && <p className="mt-2 text-xs leading-5 text-rose-100/80">{urgentFinding.recommended_action}</p>}<div className="mt-3 max-h-36 space-y-2 overflow-y-auto pr-1 custom-scrollbar">{urgentItems.length ? urgentItems.map((ticket) => <p key={ticket.number} className="text-xs leading-5 text-slate-200"><span className="font-mono text-rose-200">{ticket.number}</span> · {ticket.short_description || ticket.title}<br /><span className="text-amber-200">{ticket.sentiment || ticket.customer_sentiment?.status || 'Customer sentiment not recorded'}</span></p>) : <p className="text-xs text-slate-500">No breached or near breach customer incidents.</p>}</div></section><section className="rounded-xl border border-amber-500/35 bg-amber-950/20 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-amber-200">Stale problems</p><p className="mt-2 text-3xl font-semibold text-amber-100">{staleProblems.length}</p>{problemFinding && <p className="mt-2 text-xs leading-5 text-amber-100/80">{problemFinding.recommended_action}</p>}<div className="mt-3 max-h-36 space-y-2 overflow-y-auto pr-1 custom-scrollbar">{staleProblems.length ? staleProblems.map((ticket) => <p key={ticket.number} className="text-xs leading-5 text-slate-200"><span className="font-mono text-amber-200">{ticket.number}</span> · {ageLabel(ticket)}<br /><span className="text-slate-400">{pendingTasks(ticket.ptasks).length} pending PTask{pendingTasks(ticket.ptasks).length === 1 ? '' : 's'}</span></p>) : <p className="text-xs text-slate-500">No stale problem records.</p>}</div></section><section className="rounded-xl border border-violet-500/35 bg-violet-950/20 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-violet-200">Changes needing action</p><p className="mt-2 text-3xl font-semibold text-violet-100">{pendingChanges.length}</p>{changeFinding && <p className="mt-2 text-xs leading-5 text-violet-100/80">{changeFinding.recommended_action}</p>}<div className="mt-3 max-h-36 space-y-2 overflow-y-auto pr-1 custom-scrollbar">{pendingChanges.length ? pendingChanges.map((ticket) => <p key={ticket.number} className="text-xs leading-5 text-slate-200"><span className="font-mono text-violet-200">{ticket.number}</span> · {ticket.short_description || ticket.title}<br /><span className="text-slate-400">{pendingTasks(ticket.ctasks).length} pending CTask{pendingTasks(ticket.ctasks).length === 1 ? '' : 's'}</span></p>) : <p className="text-xs text-slate-500">No pending change tasks.</p>}</div></section></div>
      <div className="mt-5 flex justify-end"><button type="button" onClick={onClose} className="rounded-lg border border-cyan-400/50 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20">Review sorted dashboard</button></div>
    </section>
  </div>
}

function AssignmentGroupAnomalyBriefing({ groups, detection, agentAnalysis, onClose, onOpenTicket }) {
  const insights = agentAnalysis?.findings?.length ? agentAnalysis.findings : (detection?.insights || [])
  const summary = detection?.summary || { total: 0, high: 0, medium: 0, impacted_tickets: 0 }
  return <div className="fixed inset-0 z-40 grid place-items-center bg-slate-950/75 p-4 backdrop-blur-sm" role="presentation" onMouseDown={onClose}>
    <section role="dialog" aria-modal="true" aria-label="Assignment group anomaly briefing" className="w-full max-w-3xl rounded-2xl border border-violet-500/35 bg-slate-900 p-6 shadow-2xl shadow-slate-950/70" onMouseDown={(event) => event.stopPropagation()}>
      <div className="flex items-start justify-between gap-4 border-b border-slate-700 pb-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">AI operations analyst</p><h2 className="mt-2 text-2xl font-semibold text-slate-50">Incident anomaly briefing</h2><p className="mt-1 text-sm text-slate-400">{groups.length === 1 ? groups[0] : `${groups.length} assignment groups`} · recent activity compared with the prior reporting trend.</p></div><button type="button" onClick={onClose} aria-label="Close anomaly briefing" className="rounded-full border border-slate-600 px-3 py-1.5 text-sm text-slate-200 transition hover:border-violet-400 hover:bg-slate-800">×</button></div>
      {insights.length ? <div className="mt-5 max-h-[28rem] space-y-3 overflow-y-auto pr-2 custom-scrollbar">{insights.map((insight) => <article key={insight.id} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${insight.severity === 'HIGH' ? 'border-rose-500/45 bg-rose-950/35 text-rose-200' : 'border-amber-500/45 bg-amber-950/35 text-amber-200'}`}>{insight.severity} · {insight.confidence_score}% confidence</span><h3 className="mt-2 font-semibold text-slate-100">{insight.title}</h3></div><span className="font-mono text-sm text-violet-200">{insight.expected_count === null || insight.expected_count === undefined ? `${insight.current_count} related` : `${insight.current_count} vs ${insight.expected_count} expected`}</span></div><p className="mt-2 text-sm leading-6 text-slate-300">{insight.explanation}</p><div className="mt-3 grid gap-3 text-xs md:grid-cols-2"><div><p className="font-semibold uppercase tracking-wider text-slate-500">Supporting evidence</p><p className="mt-1 leading-5 text-slate-400">{insight.supporting_evidence?.slice(0, 3).join(' · ')}</p></div><div><p className="font-semibold uppercase tracking-wider text-slate-500">Recommended action</p><p className="mt-1 leading-5 text-violet-200">{insight.recommended_action}</p><p className="mt-1 leading-5 text-slate-400">{insight.possible_contributing_factor || insight.recommendation_reason}</p></div></div><div className="mt-3 flex flex-wrap gap-2">{insight.ticket_ids?.map((ticketId) => <button key={ticketId} type="button" onClick={() => { onClose(); onOpenTicket(ticketId) }} className="rounded-md border border-cyan-500/35 bg-cyan-950/25 px-2 py-1 font-mono text-xs text-cyan-100 hover:bg-cyan-500/15">{ticketId}</button>)}</div></article>)}</div> : <div className="mt-5 rounded-xl border border-dashed border-slate-700 bg-slate-950/25 p-5 text-sm leading-6 text-slate-400">No unusual incident pattern was detected for this selection. ATLAS compared recent incident volume, priority mix, categories, and business services with the preceding trend.</div>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-700 pt-4"><p className="text-xs text-slate-500">{summary.high} high · {summary.medium} medium · {summary.impacted_tickets} impacted incidents</p><button type="button" onClick={onClose} className="rounded-lg border border-violet-400/50 bg-violet-500/10 px-4 py-2 text-sm font-semibold text-violet-100 transition hover:bg-violet-500/20">Review filtered dashboard</button></div>
    </section>
  </div>
}

export default function Dashboard({ drilldown, onReturnToStats, onClearDrilldown }) {
  const [tickets, setTickets] = useState([])
  const [assignmentGroups, setAssignmentGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(() => new Set())
  const [groupSearch, setGroupSearch] = useState('')
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [activeType, setActiveType] = useState('ALL')
  const [selectedAssignees, setSelectedAssignees] = useState(() => new Set())
  const [assigneeMenuOpen, setAssigneeMenuOpen] = useState(false)
  const [briefingAssignee, setBriefingAssignee] = useState(null)
  const [anomalyBriefing, setAnomalyBriefing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailError, setDetailError] = useState('')
  const groupControlRef = useRef(null)
  const assigneeControlRef = useRef(null)
  const anomalyRequestRef = useRef(0)

  useEffect(() => {
    let active = true
    Promise.all([fetchDashboardTickets(), fetchAssignmentGroups()])
      .then(([ticketResult, groupResult]) => {
        if (!active) return
        setTickets(ticketResult.tickets)
        setAssignmentGroups(groupResult.assignment_groups)
        setSelectedGroups(new Set(groupResult.assignment_groups))
        setSelectedAssignees(new Set(ticketResult.tickets.map((ticket) => ticket.assignee)))
      })
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key !== 'Escape') return
      setSelected(null)
      setBriefingAssignee(null)
      setAnomalyBriefing(null)
    }
    const closeFilterMenus = (event) => {
      if (groupControlRef.current && !groupControlRef.current.contains(event.target)) setGroupMenuOpen(false)
      if (assigneeControlRef.current && !assigneeControlRef.current.contains(event.target)) setAssigneeMenuOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    window.addEventListener('mousedown', closeFilterMenus)
    return () => { window.removeEventListener('keydown', closeOnEscape); window.removeEventListener('mousedown', closeFilterMenus) }
  }, [])

  const assignees = useMemo(() => [...new Set(tickets.map((ticket) => ticket.assignee))].sort(), [tickets])
  const matchingGroups = useMemo(() => assignmentGroups.filter((group) => group.toLowerCase().includes(groupSearch.trim().toLowerCase())), [assignmentGroups, groupSearch])
  const drilldownTicketIds = useMemo(() => new Set(drilldown?.ticketIds || []), [drilldown])
  const activeGroups = useMemo(() => drilldown ? new Set(drilldown.assignmentGroups || []) : selectedGroups, [drilldown, selectedGroups])
  const activeAssignees = useMemo(() => drilldown ? new Set(drilldown.assignees || []) : selectedAssignees, [drilldown, selectedAssignees])
  const briefingAssigneeName = briefingAssignee?.name || null
  const assigneeFocused = Boolean(briefingAssigneeName) || activeAssignees.size < assignees.length
  const visibleTickets = useMemo(() => {
    const filtered = tickets.filter((ticket) => (
      activeGroups.has(ticket.assignment_group)
      && (drilldown || activeType === 'ALL' || ticket.type === activeType)
      && activeAssignees.has(ticket.assignee)
      && (!drilldown || drilldownTicketIds.has(ticket.number || ticket.id))
    ))
    return assigneeFocused ? filtered.sort(sortByOperationalUrgency) : filtered
  }, [activeGroups, activeAssignees, activeType, assigneeFocused, drilldown, drilldownTicketIds, tickets])
  const briefingTickets = useMemo(() => tickets
    .filter((ticket) => ticket.assignee === briefingAssigneeName && activeGroups.has(ticket.assignment_group))
    .sort(sortByOperationalUrgency), [activeGroups, briefingAssigneeName, tickets])

  function showAnomalyBriefing(groups) {
    if (!groups.size) {
      anomalyRequestRef.current += 1
      setAnomalyBriefing(null)
      return
    }
    const requestId = anomalyRequestRef.current + 1
    anomalyRequestRef.current = requestId
    fetchDashboardStats({ assignmentGroups: [...groups], groupFilterActive: true })
      .then((result) => {
        if (requestId !== anomalyRequestRef.current) return
        // Group owners are interrupted only for an explainable abnormal
        // pattern, never for a normal operational selection.
        if (result.anomaly_detection?.insights?.length) {
          setAnomalyBriefing({ groups: [...groups], detection: result.anomaly_detection, agentAnalysis: result.assignment_group_agent })
        } else {
          setAnomalyBriefing(null)
        }
      })
      .catch(() => requestId === anomalyRequestRef.current && setAnomalyBriefing(null))
  }

  function toggleGroup(group) {
    const next = new Set(selectedGroups)
    if (next.has(group)) next.delete(group)
    else next.add(group)
    setSelectedGroups(next)
    showAnomalyBriefing(next)
  }

  function selectMyTeams() {
    const groups = new Set(MY_TEAM_GROUPS)
    setSelectedGroups(groups)
    showAnomalyBriefing(groups)
    setGroupSearch('')
  }

  function selectAllGroups() { const groups = new Set(assignmentGroups); setSelectedGroups(groups); showAnomalyBriefing(groups) }
  function deselectAllGroups() { setSelectedGroups(new Set()); setAnomalyBriefing(null) }
  function toggleAssignee(name) {
    const willSelect = !selectedAssignees.has(name)
    setSelectedAssignees((current) => {
      const next = new Set(current)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
    if (willSelect) {
      const assigneeTickets = tickets.filter((ticket) => ticket.assignee === name && activeGroups.has(ticket.assignment_group))
      // The assignee modal is an intervention warning, not a routine status
      // dialog. A healthy SLA and sentiment workload stays on the queue.
      if (!hasOperationalWarning(assigneeTickets)) {
        setBriefingAssignee(null)
        return
      }
      setBriefingAssignee({ name, analysis: null })
      fetchDashboardStats({ assignmentGroups: [...activeGroups], assignees: [name], groupFilterActive: true })
        .then((result) => setBriefingAssignee((current) => current?.name === name ? { name, analysis: result.assignee_agent } : current))
        // The established local briefing remains available if optional agent
        // analysis cannot be generated.
        .catch(() => {})
    }
  }
  function selectAllAssignees() { setSelectedAssignees(new Set(assignees)); setBriefingAssignee(null) }
  function deselectAllAssignees() { setSelectedAssignees(new Set()); setBriefingAssignee(null) }

  async function openTicket(ticketId) {
    setDetailError('')
    const cachedTicket = tickets.find((ticket) => ticket.id === ticketId || ticket.number === ticketId || ticket.sys_id === ticketId)
    if (cachedTicket) {
      setSelected(cachedTicket)
      if (hasDetailFields(cachedTicket)) return
      try {
        const result = await fetchTicket(ticketId)
        setSelected((current) => current?.number === cachedTicket.number ? result.ticket : current)
      } catch (requestError) { setDetailError(requestError.message) }
      return
    }
    setSelected({ loading: true })
    try { const result = await fetchTicket(ticketId); setSelected(result.ticket) }
    catch (requestError) { setDetailError(requestError.message); setSelected(null) }
  }

  return <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
    <div className="apple-hero mb-8"><p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-300">IT service intelligence</p><h1 className="mt-3 text-4xl font-semibold tracking-tight">Operations, clarified.</h1><p className="mt-3 max-w-2xl text-slate-400">A single, focused view of active IT work—prioritized for timely decisions and confident action.</p></div>
    {drilldown && <section className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-cyan-500/40 bg-cyan-950/25 p-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-cyan-200">Stats drill-down</p><p className="mt-1 text-sm font-semibold text-slate-100">{drilldown.title}</p><p className="mt-1 text-xs text-slate-400">{drilldownTicketIds.size} matching ticket{drilldownTicketIds.size === 1 ? '' : 's'} from the executive view.</p></div><div className="flex gap-3"><button type="button" onClick={onClearDrilldown} className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800">Clear drill-down</button><button type="button" onClick={onReturnToStats} className="rounded-lg border border-cyan-400/50 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/20">← Back to Stats</button></div></section>}
    <div className="apple-type-tabs mb-6 flex flex-wrap gap-2 border-b border-slate-800 pb-4" role="tablist" aria-label="Ticket type">{typeTabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeType === tab.id} onClick={() => setActiveType(tab.id)} className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${activeType === tab.id ? 'monday-primary' : 'bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white'}`}>{tab.label}</button>)}</div>
    <div className="apple-filter mb-4 flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 lg:flex-row lg:items-end">
      <div ref={groupControlRef} className="relative min-w-0 flex-1"><div className="mb-2 flex items-center justify-between gap-3"><label htmlFor="assignment-group-search" className="text-xs font-semibold uppercase tracking-wider text-slate-400">Assignment Group Search</label><div className="flex gap-3"><button type="button" onClick={selectAllGroups} className="text-xs font-semibold text-cyan-300 hover:text-cyan-100">Select All</button><button type="button" onClick={deselectAllGroups} className="text-xs font-semibold text-slate-400 hover:text-slate-100">Deselect All</button><button type="button" onClick={selectMyTeams} className="text-xs font-semibold text-cyan-300 hover:text-cyan-100">My Teams</button></div></div><input id="assignment-group-search" value={groupSearch} onFocus={() => setGroupMenuOpen(true)} onChange={(event) => { setGroupSearch(event.target.value); setGroupMenuOpen(true) }} placeholder="Search enterprise assignment groups…" aria-expanded={groupMenuOpen} aria-controls="assignment-group-menu" className="w-full rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-400" />{groupMenuOpen && <div id="assignment-group-menu" className="absolute z-30 mt-2 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-slate-950/50">{matchingGroups.length ? matchingGroups.map((group) => <label key={group} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"><input type="checkbox" checked={selectedGroups.has(group)} onChange={() => toggleGroup(group)} className="h-4 w-4 accent-cyan-400" />{group}</label>) : <p className="px-3 py-2 text-sm text-slate-500">No assignment groups match that search.</p>}</div>}</div>
      <div ref={assigneeControlRef} className="relative min-w-0 lg:w-72"><div className="mb-2 flex items-center justify-between gap-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Assignees</p><div className="flex gap-3"><button type="button" onClick={selectAllAssignees} className="text-xs font-semibold text-cyan-300 hover:text-cyan-100">Select All</button><button type="button" onClick={deselectAllAssignees} className="text-xs font-semibold text-slate-400 hover:text-slate-100">Deselect All</button></div></div><button type="button" onClick={() => setAssigneeMenuOpen((open) => !open)} aria-expanded={assigneeMenuOpen} className="flex w-full items-center justify-between rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-left text-sm text-slate-100 hover:border-cyan-400"><span>{selectedAssignees.size === assignees.length ? 'All assignees' : `${selectedAssignees.size} assignee${selectedAssignees.size === 1 ? '' : 's'} selected`}</span><span className="text-cyan-300">⌄</span></button>{assigneeMenuOpen && <div className="absolute z-30 mt-2 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-slate-950/50 custom-scrollbar">{assignees.map((name) => <label key={name} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"><input type="checkbox" checked={selectedAssignees.has(name)} onChange={() => toggleAssignee(name)} className="h-4 w-4 accent-cyan-400" />{name}</label>)}</div>}</div>
    </div>
    <div className="mb-7 flex flex-wrap gap-2" aria-label="Selected assignment groups">{[...selectedGroups].map((group) => <button key={group} type="button" onClick={() => toggleGroup(group)} className="apple-chip rounded-full border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-sm text-cyan-100 transition-colors hover:bg-cyan-500/20 hover:text-cyan-100">{group} <span aria-hidden="true">×</span><span className="sr-only">Remove {group}</span></button>)}{selectedGroups.size === 0 && <p className="py-1 text-sm text-amber-200">Select one or more assignment groups to populate the queue.</p>}</div>
    {assigneeFocused && <p className="mb-4 rounded-xl border border-cyan-500/30 bg-cyan-950/20 px-4 py-3 text-sm text-cyan-100">Assignee urgency order is active: urgent customer incidents, stale problems, pending changes, then regular backlog.</p>}
    {loading && <p className="rounded-xl border border-slate-700 p-6 text-slate-400">Loading active tickets…</p>}{error && <p className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-rose-200" role="alert">Unable to load tickets: {error}</p>}
    {!loading && !error && <div className="apple-table overflow-x-auto rounded-2xl border border-slate-700 bg-slate-900/70 shadow-2xl shadow-slate-950/30"><table className="min-w-full text-left text-sm"><thead className="border-b border-slate-700 bg-slate-800/70 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-5 py-4">{assigneeFocused ? 'Ticket · urgency order' : 'Ticket'}</th><th className="px-5 py-4">Health</th><th className="px-5 py-4">Context-aware metrics</th><th className="px-5 py-4">Assignment Group</th><th className="px-5 py-4">Assignee</th><th className="px-5 py-4"><span className="sr-only">Details</span></th></tr></thead><tbody className="divide-y divide-slate-800">{visibleTickets.map((ticket) => <tr key={ticket.id} className="hover:bg-slate-800/60"><td className="px-5 py-4"><p className="font-mono text-xs text-cyan-300">{ticket.id} · {ticket.type}</p><p className="mt-1 font-medium">{ticket.title}</p>{(ticket.type === 'INC' || ticket.type === 'RITM') && <div className="mt-2"><SlaBadge ticket={ticket} /></div>}</td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${healthStyles[ticket.health_color]}`}>{ticket.health_color}</span></td><td className="px-5 py-4"><ContextMetrics ticket={ticket} /></td><td className="px-5 py-4 text-slate-300">{ticket.assignment_group}</td><td className="px-5 py-4 text-slate-300">{ticket.assignee}</td><td className="px-5 py-4"><button type="button" onClick={() => openTicket(ticket.id)} className="apple-detail-button rounded-lg border border-cyan-500/50 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/10">View</button></td></tr>)}</tbody></table>{visibleTickets.length === 0 && <p className="p-6 text-center text-slate-400">No items match the selected ticket type, assignment groups, and assignee.</p>}</div>}
    {detailError && <p className="mt-4 text-sm text-rose-300" role="alert">Unable to load ticket: {detailError}</p>}{anomalyBriefing && <AssignmentGroupAnomalyBriefing groups={anomalyBriefing.groups} detection={anomalyBriefing.detection} agentAnalysis={anomalyBriefing.agentAnalysis} onClose={() => setAnomalyBriefing(null)} onOpenTicket={openTicket} />}{briefingAssignee && <AssigneeBriefing assignee={briefingAssignee.name} tickets={briefingTickets} analysis={briefingAssignee.analysis} onClose={() => setBriefingAssignee(null)} />}{selected && <div className="apple-overlay fixed inset-0 z-20 bg-slate-950/70" role="presentation" onMouseDown={() => setSelected(null)}><aside role="dialog" aria-modal="true" aria-label="Ticket details" className="apple-side-panel ml-auto h-full w-full max-w-2xl shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>{selected.loading ? <div className="p-6 text-slate-300">Loading ticket details…</div> : <TicketCard ticket={selected} onClose={() => setSelected(null)} onSelectTicket={openTicket} />}</aside></div>}
  </section>
}

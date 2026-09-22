import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAssignmentGroups, fetchDashboardTickets, fetchTicket } from '../api'
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

function HistoricalTickets({ records = [] }) {
  if (!records.length) return null
  return <section className="rounded-xl border border-indigo-400/40 bg-indigo-500/5 p-4"><h3 className="text-sm font-semibold text-indigo-100">📚 Relevant Past Tickets</h3><div className="mt-3 space-y-3">{records.map((record) => <article key={record.id} className="rounded-lg border border-slate-700 bg-slate-950/60 p-3"><div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-slate-100"><span className="font-mono text-cyan-300">{record.id}</span> - {record.title}</p><span className="shrink-0 rounded-full bg-indigo-400/15 px-2 py-1 text-xs font-bold text-indigo-200">{record.relevance_score}% Match</span></div><p className="mt-2 text-xs text-slate-500">Resolved: {record.resolution_date}</p><blockquote className="mt-2 border-l-2 border-indigo-400/60 pl-3 text-sm leading-6 text-slate-400">{record.close_notes_snippet}</blockquote></article>)}</div></section>
}

function ContextMetrics({ ticket }) {
  if (ticket.type === 'INC' || ticket.type === 'RITM') return <div className="space-y-1 text-xs text-slate-300"><p><span className="text-slate-500">SLA remaining:</span> {ticket.sla_remaining_mins} min</p><p><span className="text-slate-500">Sentiment:</span> {ticket.sentiment}</p></div>
  if (ticket.type === 'PRB') return <div className="space-y-1 text-xs text-slate-300"><p><span className="text-slate-500">RCA phase:</span> {ticket.rca_phase}</p><p><span className="text-slate-500">Risk:</span> {ticket.risk_level}</p></div>
  return <div className="space-y-1 text-xs text-slate-300"><p><span className="text-slate-500">CAB status:</span> {ticket.cab_status}</p><p><span className="text-slate-500">Risk:</span> {ticket.risk_level}</p></div>
}

export default function Dashboard() {
  const [tickets, setTickets] = useState([])
  const [assignmentGroups, setAssignmentGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(() => new Set())
  const [groupSearch, setGroupSearch] = useState('')
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [activeType, setActiveType] = useState('ALL')
  const [assignee, setAssignee] = useState('All')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailError, setDetailError] = useState('')
  const groupControlRef = useRef(null)

  useEffect(() => {
    let active = true
    Promise.all([fetchDashboardTickets(), fetchAssignmentGroups()])
      .then(([ticketResult, groupResult]) => {
        if (!active) return
        setTickets(ticketResult.tickets)
        setAssignmentGroups(groupResult.assignment_groups)
        setSelectedGroups(new Set(groupResult.assignment_groups))
      })
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    const closeOnEscape = (event) => event.key === 'Escape' && setSelected(null)
    const closeGroupMenu = (event) => {
      if (groupControlRef.current && !groupControlRef.current.contains(event.target)) setGroupMenuOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    window.addEventListener('mousedown', closeGroupMenu)
    return () => { window.removeEventListener('keydown', closeOnEscape); window.removeEventListener('mousedown', closeGroupMenu) }
  }, [])

  const assignees = useMemo(() => ['All', ...new Set(tickets.map((ticket) => ticket.assignee))], [tickets])
  const matchingGroups = useMemo(() => assignmentGroups.filter((group) => group.toLowerCase().includes(groupSearch.trim().toLowerCase())), [assignmentGroups, groupSearch])
  const visibleTickets = useMemo(() => tickets.filter((ticket) => (
    selectedGroups.has(ticket.assignment_group)
    && (activeType === 'ALL' || ticket.type === activeType)
    && (assignee === 'All' || ticket.assignee === assignee)
  )), [activeType, assignee, selectedGroups, tickets])

  function toggleGroup(group) {
    setSelectedGroups((current) => {
      const next = new Set(current)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  function selectMyTeams() {
    setSelectedGroups(new Set(MY_TEAM_GROUPS))
    setGroupSearch('')
  }

  async function openTicket(ticketId) {
    setDetailError('')
    setSelected({ loading: true })
    try { const result = await fetchTicket(ticketId); setSelected(result.ticket) }
    catch (requestError) { setDetailError(requestError.message); setSelected(null) }
  }

  return <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <div className="mb-6"><p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">IT service intelligence</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Active ticket dashboard</h1><p className="mt-2 text-slate-400">Search and combine enterprise assignment groups to focus the operations queue.</p></div>
    <div className="mb-5 flex flex-wrap gap-2 border-b border-slate-800 pb-4" role="tablist" aria-label="Ticket type">{typeTabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeType === tab.id} onClick={() => setActiveType(tab.id)} className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${activeType === tab.id ? 'bg-cyan-400 text-slate-950' : 'bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white'}`}>{tab.label}</button>)}</div>
    <div className="mb-3 flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 lg:flex-row lg:items-end">
      <div ref={groupControlRef} className="relative min-w-0 flex-1"><div className="mb-2 flex items-center justify-between gap-3"><label htmlFor="assignment-group-search" className="text-xs font-semibold uppercase tracking-wider text-slate-400">Assignment Group Search</label><button type="button" onClick={selectMyTeams} className="text-xs font-semibold text-cyan-300 hover:text-cyan-100">Select My Teams</button></div><input id="assignment-group-search" value={groupSearch} onFocus={() => setGroupMenuOpen(true)} onChange={(event) => { setGroupSearch(event.target.value); setGroupMenuOpen(true) }} placeholder="Search 20 enterprise assignment groups…" aria-expanded={groupMenuOpen} aria-controls="assignment-group-menu" className="w-full rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-400" />{groupMenuOpen && <div id="assignment-group-menu" className="absolute z-30 mt-2 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-slate-950/50">{matchingGroups.length ? matchingGroups.map((group) => <label key={group} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"><input type="checkbox" checked={selectedGroups.has(group)} onChange={() => toggleGroup(group)} className="h-4 w-4 accent-cyan-400" />{group}</label>) : <p className="px-3 py-2 text-sm text-slate-500">No assignment groups match that search.</p>}</div>}</div>
      <label className="text-sm text-slate-300 lg:w-56">Assignee <select value={assignee} onChange={(event) => setAssignee(event.target.value)} className="mt-2 block w-full rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100">{assignees.map((name) => <option key={name}>{name}</option>)}</select></label>
    </div>
    <div className="mb-6 flex flex-wrap gap-2" aria-label="Selected assignment groups">{[...selectedGroups].map((group) => <button key={group} type="button" onClick={() => toggleGroup(group)} className="rounded-full border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-sm text-cyan-100 hover:bg-rose-500/15 hover:text-rose-100">{group} <span aria-hidden="true">×</span><span className="sr-only">Remove {group}</span></button>)}{selectedGroups.size === 0 && <p className="py-1 text-sm text-amber-200">Select one or more assignment groups to populate the queue.</p>}</div>
    {loading && <p className="rounded-xl border border-slate-700 p-6 text-slate-400">Loading active tickets…</p>}{error && <p className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-rose-200" role="alert">Unable to load tickets: {error}</p>}
    {!loading && !error && <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/70 shadow-2xl shadow-slate-950/30"><table className="min-w-full text-left text-sm"><thead className="border-b border-slate-700 bg-slate-800/70 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-5 py-4">Ticket</th><th className="px-5 py-4">Health</th><th className="px-5 py-4">Context-aware metrics</th><th className="px-5 py-4">Assignment Group</th><th className="px-5 py-4">Assignee</th><th className="px-5 py-4"><span className="sr-only">Details</span></th></tr></thead><tbody className="divide-y divide-slate-800">{visibleTickets.map((ticket) => <tr key={ticket.id} className="hover:bg-slate-800/60"><td className="px-5 py-4"><p className="font-mono text-xs text-cyan-300">{ticket.id} · {ticket.type}</p><p className="mt-1 font-medium">{ticket.title}</p></td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${healthStyles[ticket.health_color]}`}>{ticket.health_color}</span></td><td className="px-5 py-4"><ContextMetrics ticket={ticket} /></td><td className="px-5 py-4 text-slate-300">{ticket.assignment_group}</td><td className="px-5 py-4 text-slate-300">{ticket.assignee}</td><td className="px-5 py-4"><button type="button" onClick={() => openTicket(ticket.id)} className="rounded-lg border border-cyan-500/50 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/10">Details</button></td></tr>)}</tbody></table>{visibleTickets.length === 0 && <p className="p-6 text-center text-slate-400">No items match the selected ticket type, assignment groups, and assignee.</p>}</div>}
    {detailError && <p className="mt-4 text-sm text-rose-300" role="alert">Unable to load ticket: {detailError}</p>}{selected && <div className="fixed inset-0 z-20 bg-slate-950/70" role="presentation" onMouseDown={() => setSelected(null)}><aside role="dialog" aria-modal="true" aria-label="Ticket details" className="ml-auto h-full w-full max-w-2xl shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>{selected.loading ? <div className="p-6 text-slate-300">Loading ticket details…</div> : <TicketCard ticket={selected} onClose={() => setSelected(null)} onSelectTicket={openTicket} historicalContent={<HistoricalTickets records={selected.historical_tickets} />} />}</aside></div>}
  </section>
}

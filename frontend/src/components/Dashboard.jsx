import { useEffect, useMemo, useState } from 'react'
import { fetchDashboardTickets, fetchTicket } from '../api'
import TicketCard from './TicketCard'

const MY_TEAM_GROUPS = ['SAP EWM Support', 'Integration Middleware', 'QMS Compliance Ops']

const TEAM_GROUPS_ALL = 'My Team Groups (All 3)'
const healthStyles = {
  RED: 'bg-rose-500/15 text-rose-300 ring-rose-400/30',
  YELLOW: 'bg-amber-500/15 text-amber-200 ring-amber-400/30',
  GREEN: 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/30',
}

export default function Dashboard() {
  const [tickets, setTickets] = useState([])
  const [assignmentGroup, setAssignmentGroup] = useState(TEAM_GROUPS_ALL)
  const [assignee, setAssignee] = useState('All')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailError, setDetailError] = useState('')

  useEffect(() => {
    let active = true
    fetchDashboardTickets()
      .then((result) => active && setTickets(result.tickets))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    const closeOnEscape = (event) => event.key === 'Escape' && setSelected(null)
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  const assignees = useMemo(() => ['All', ...new Set(tickets.map((ticket) => ticket.assignee))], [tickets])
  const assignmentGroups = useMemo(() => [TEAM_GROUPS_ALL, ...MY_TEAM_GROUPS, ...tickets.map((ticket) => ticket.assignment_group).filter((group) => !MY_TEAM_GROUPS.includes(group))], [tickets])
  const visibleTickets = tickets.filter((ticket) => {
    const groupMatches = assignmentGroup === TEAM_GROUPS_ALL
      ? MY_TEAM_GROUPS.includes(ticket.assignment_group)
      : ticket.assignment_group === assignmentGroup
    return groupMatches && (assignee === 'All' || ticket.assignee === assignee)
  })

  async function openTicket(ticketId) {
    setDetailError('')
    setSelected({ loading: true })
    try {
      const result = await fetchTicket(ticketId)
      setSelected(result.ticket)
    } catch (requestError) {
      setDetailError(requestError.message)
      setSelected(null)
    }
  }

  return <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <div className="mb-6 flex flex-col justify-between gap-4 xl:flex-row xl:items-end">
      <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">IT service intelligence</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Active ticket dashboard</h1><p className="mt-2 text-slate-400">Prioritize incidents, problems, changes, and service requests by team ownership.</p></div>
      <div className="flex flex-col gap-3 sm:flex-row"><label className="text-sm text-slate-300">Assignment Group <select value={assignmentGroup} onChange={(event) => setAssignmentGroup(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 sm:mt-0 sm:ml-2">{assignmentGroups.map((group) => <option key={group}>{group}</option>)}</select></label><label className="text-sm text-slate-300">Assignee <select value={assignee} onChange={(event) => setAssignee(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 sm:mt-0 sm:ml-2">{assignees.map((name) => <option key={name}>{name}</option>)}</select></label></div>
    </div>
    {loading && <p className="rounded-xl border border-slate-700 p-6 text-slate-400">Loading active tickets…</p>}
    {error && <p className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-rose-200" role="alert">Unable to load tickets: {error}</p>}
    {!loading && !error && <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/70 shadow-2xl shadow-slate-950/30"><table className="min-w-full text-left text-sm"><thead className="border-b border-slate-700 bg-slate-800/70 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-5 py-4">Ticket</th><th className="px-5 py-4">Health</th><th className="px-5 py-4">SLA</th><th className="px-5 py-4">Sentiment</th><th className="px-5 py-4">Assignment Group</th><th className="px-5 py-4">Assignee</th><th className="px-5 py-4"><span className="sr-only">Details</span></th></tr></thead><tbody className="divide-y divide-slate-800">{visibleTickets.map((ticket) => <tr key={ticket.id} className="hover:bg-slate-800/60"><td className="px-5 py-4"><p className="font-mono text-xs text-cyan-300">{ticket.id} · {ticket.record_type}</p><p className="mt-1 font-medium">{ticket.title}</p></td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${healthStyles[ticket.health_color]}`}>{ticket.health_color}</span></td><td className="px-5 py-4 text-slate-300">{ticket.sla_status.replace('_', ' ')}<br /><span className="text-xs text-slate-500">{ticket.sla_minutes} min</span></td><td className="px-5 py-4 text-slate-300">{ticket.sentiment}</td><td className="px-5 py-4 text-slate-300">{ticket.assignment_group}</td><td className="px-5 py-4 text-slate-300">{ticket.assignee}</td><td className="px-5 py-4"><button type="button" onClick={() => openTicket(ticket.id)} className="rounded-lg border border-cyan-500/50 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/10">Details</button></td></tr>)}</tbody></table>{visibleTickets.length === 0 && <p className="p-6 text-center text-slate-400">No active tickets match these filters.</p>}</div>}
    {detailError && <p className="mt-4 text-sm text-rose-300" role="alert">Unable to load ticket: {detailError}</p>}
    {selected && <div className="fixed inset-0 z-20 bg-slate-950/70" role="presentation" onMouseDown={() => setSelected(null)}><aside role="dialog" aria-modal="true" aria-label="Ticket details" className="ml-auto h-full w-full max-w-2xl shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>{selected.loading ? <div className="p-6 text-slate-300">Loading ticket details…</div> : <TicketCard ticket={selected} onClose={() => setSelected(null)} />}</aside></div>}
  </section>
}

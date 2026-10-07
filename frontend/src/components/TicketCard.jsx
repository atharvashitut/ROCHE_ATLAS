import KnowledgeReferences from './KnowledgeReferences'
import TopologyTree from './TopologyTree'
import WorkItemActivities from './WorkItemActivities'

function SentimentBadge({ ticket }) {
  if (!['INC', 'RITM'].includes(ticket.type) || !ticket.customer_sentiment) return null
  const sentiment = ticket.customer_sentiment
  const faces = { Frustrated: '😠', Impatient: '😟', Satisfied: '😊', Neutral: '😐' }
  const critical = sentiment.status === 'Frustrated' || ticket.priority?.startsWith('1 -')
  const styles = critical ? 'border-red-500/50 bg-red-950/60 text-red-300 shadow-[0_0_12px_rgba(239,68,68,0.25)]' : sentiment.status === 'Impatient' ? 'border-amber-500/50 bg-amber-950/60 text-amber-300' : 'border-slate-700 bg-slate-800 text-slate-300'
  return <span title={sentiment.explanation} className={`rounded-full border px-2 py-1 text-xs font-bold ${styles}`}>{faces[sentiment.status] || '😐'} {sentiment.status} - {sentiment.score_pct}% Urgency Score</span>
}

function SlaBadge({ ticket }) {
  const remaining = ticket.sla_remaining_minutes ?? ticket.sla_remaining_mins
  if (typeof remaining !== 'number') return null
  const isBreached = ticket.is_breached || remaining <= 0
  if (isBreached) return <span className="rounded-full border border-rose-500/50 bg-rose-950/60 px-2 py-1 text-xs font-bold text-rose-200">🚨 Breached ({Math.abs(remaining)}m overdue) · {ticket.breach_reason}</span>
  const styles = remaining <= 90 ? 'border-amber-500/50 bg-amber-950/60 text-amber-200' : 'border-emerald-500/50 bg-emerald-950/60 text-emerald-200'
  return <span className={`rounded-full border px-2 py-1 text-xs font-bold ${styles}`}>⏳ {remaining}m remaining</span>
}

function HoldReasonBadge({ ticket }) {
  if (ticket.state !== 'On Hold' || !ticket.hold_reason) return null
  return <span className="rounded-full border border-amber-500/50 bg-amber-950/60 px-2 py-1 text-xs font-bold text-amber-200">⏸ On Hold · {ticket.hold_reason}</span>
}

function ExecutiveBriefing({ ticket }) {
  const remaining = ticket.sla_remaining_minutes ?? ticket.sla_remaining_mins
  const sla = ticket.is_breached || (typeof remaining === 'number' && remaining <= 0) ? `${Math.abs(remaining || 0)}m overdue` : typeof remaining === 'number' ? `${remaining}m remaining` : 'SLA not recorded'
  const linked = [ticket.parent_incident, ticket.linked_prb, ticket.linked_chg].filter(Boolean).map((record) => record.number).join(' · ')
  const action = (ticket.ai_resolution_guide || 'Validate the current service state and update the requester.').split('. ')[0]
  return <section className="apple-briefing rounded-2xl border border-teal-400/30 bg-teal-950/20 p-5"><h3 className="text-sm font-semibold text-teal-100">AI Executive Briefing</h3><div className="mt-3 space-y-1.5 text-sm leading-6 text-slate-300"><p>{ticket.short_description || ticket.title}.</p><p>The record is {ticket.state} with {sla}.</p><p>{linked ? `Related work: ${linked}.` : `${action}.`}</p></div></section>
}

function DuplicateWarning({ ticket }) {
  const matches = [...(ticket.similar_records || []), ...(ticket.historical_tickets || [])]
    .filter((match, index, all) => all.findIndex((candidate) => candidate.id === match.id) === index)
  if (!matches.length) return null
  return <section className="apple-insight rounded-2xl border border-amber-400/60 bg-amber-950/35 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-sm font-semibold text-amber-100">AI Similarity &amp; Duplicate Intelligence</h3><p className="mt-1 text-xs leading-5 text-amber-100/75">Matching active work and resolved history are ranked before duplicate or linkage decisions.</p></div><span className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-200">{matches.length} match{matches.length === 1 ? '' : 'es'}</span></div><div className="mt-3 space-y-3">{matches.map((match) => { const score = match.score ?? match.relevance_score; const date = match.resolution_date || 'Date not recorded'; const active = !['Closed', 'Resolved', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped'].includes(match.state); return <article key={match.id} className="rounded-xl border border-amber-500/30 bg-slate-950/35 p-3 text-sm text-slate-200"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 text-xs font-bold text-amber-200">{score ?? '—'}% similarity</span><span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${active ? 'border-cyan-400/40 bg-cyan-500/10 text-cyan-100' : 'border-slate-600 bg-slate-800 text-slate-300'}`}>{active ? 'Ongoing candidate' : 'Resolved history'}</span></div><p className="mt-2 font-medium">{match.id} · {match.title}</p><p className="mt-1 text-xs text-slate-400">State: <span className="font-semibold text-slate-200">{match.state || 'Unknown'}</span> · {active ? 'Active in the queue' : `Resolved: ${date}`}</p>{match.close_notes_snippet && <p className="mt-2 border-l-2 border-amber-400/40 pl-2 text-xs leading-5 text-slate-300">{match.close_notes_snippet}</p>}</article> })}</div></section>
}

export default function TicketCard({ ticket, onClose, onSelectTicket }) {
  return <article className="apple-drawer h-full overflow-y-auto bg-slate-900/95 p-6 text-slate-100"><div className="apple-drawer-header mb-7 flex items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><p className="font-mono text-sm text-teal-300">{ticket.number || ticket.id} · {ticket.type}</p><HoldReasonBadge ticket={ticket} />{['INC', 'RITM'].includes(ticket.type) && <SlaBadge ticket={ticket} />}<SentimentBadge ticket={ticket} /></div><h2 className="mt-2 text-2xl font-semibold tracking-tight">{ticket.short_description || ticket.title}</h2><p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">{ticket.description}</p><p className="mt-3 text-xs font-medium text-slate-500">Priority {ticket.priority}</p></div>{onClose && <button type="button" onClick={onClose} aria-label="Close ticket details" className="apple-close rounded-full border border-slate-600 px-3 py-1.5 text-sm hover:border-teal-400/60 hover:bg-slate-800">×</button>}</div><div className="space-y-5"><ExecutiveBriefing ticket={ticket} /><DuplicateWarning ticket={ticket} /><TopologyTree ticket={ticket} onSelectTicket={onSelectTicket} /><WorkItemActivities ticket={ticket} /><KnowledgeReferences references={ticket.knowledge_refs} /></div></article>
}

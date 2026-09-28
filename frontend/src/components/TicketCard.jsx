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

function ExecutiveBriefing({ ticket }) {
  const remaining = ticket.sla_remaining_minutes ?? ticket.sla_remaining_mins
  const sla = ticket.is_breached || (typeof remaining === 'number' && remaining <= 0) ? `${Math.abs(remaining || 0)}m overdue` : typeof remaining === 'number' ? `${remaining}m remaining` : 'SLA not recorded'
  const linked = [ticket.parent_incident, ticket.linked_prb, ticket.linked_chg].filter(Boolean).map((record) => record.number).join(' · ')
  const action = (ticket.ai_resolution_guide || 'Validate the current service state and update the requester.').split('. ')[0]
  return <section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">⚡ AI Executive Briefing</h3><ul className="mt-3 space-y-1.5 text-sm leading-5 text-slate-300"><li><span className="font-semibold text-cyan-200">• Core problem:</span> {ticket.short_description || ticket.title} · {sla}</li><li><span className="font-semibold text-cyan-200">• Operational linkage:</span> {linked || 'No parent, problem, or change linkage recorded'}</li><li><span className="font-semibold text-cyan-200">• Immediate action:</span> {action}</li></ul></section>
}

export default function TicketCard({ ticket, onClose, onSelectTicket }) {
  return <article className="h-full overflow-y-auto bg-slate-900 p-6 text-slate-100"><div className="mb-6 flex items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><p className="font-mono text-sm text-cyan-300">{ticket.number || ticket.id} · {ticket.type}</p>{['INC', 'RITM'].includes(ticket.type) && <SlaBadge ticket={ticket} />}<SentimentBadge ticket={ticket} /></div><h2 className="mt-1 text-xl font-semibold">{ticket.short_description || ticket.title}</h2><p className="mt-2 text-sm text-slate-400">{ticket.description}</p><p className="mt-2 text-xs text-slate-500">Priority: {ticket.priority}</p></div>{onClose && <button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button>}</div><div className="space-y-4"><ExecutiveBriefing ticket={ticket} /><TopologyTree ticket={ticket} onSelectTicket={onSelectTicket} /><WorkItemActivities ticket={ticket} /><KnowledgeReferences references={ticket.knowledge_refs} /></div></article>
}

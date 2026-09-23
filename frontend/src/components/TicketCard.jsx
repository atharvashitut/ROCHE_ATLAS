import KnowledgeReferences from './KnowledgeReferences'
import TopologyTree from './TopologyTree'
import WorkItemActivities from './WorkItemActivities'

const closedStates = new Set(['Closed', 'Resolved', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped'])

function SimilarityWarning({ records }) {
  const record = records[0]
  if (!record) return null
  return <section className="rounded-xl border-2 border-amber-400/70 bg-amber-400/10 p-4 shadow-lg shadow-amber-950/20"><div className="flex items-start gap-3"><span className="text-2xl" aria-hidden="true">⚠️</span><div className="min-w-0 flex-1"><h3 className="font-semibold text-amber-100">AI Duplicate / Similarity Warning</h3><p className="mt-1 text-sm leading-6 text-amber-50">This issue looks {record.score}% similar to a P1 Problem Ticket from {record.resolution_date}: {record.id} - {record.title}. The historical state is {record.state}.</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className="rounded-lg border border-amber-300/70 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-300/15">🔗 Link to {record.id}</button><button type="button" className="rounded-lg border border-amber-300/70 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-300/15">💡 View Historical RCA</button></div></div></div></section>
}

function HistoricalTickets({ records = [] }) {
  if (!records.length) return null
  return <section className="rounded-xl border border-indigo-400/40 bg-indigo-500/5 p-4"><h3 className="text-sm font-semibold text-indigo-100">📚 Relevant Past Tickets</h3><div className="mt-3 space-y-3">{records.map((record) => <article key={record.id} className="rounded-lg border border-slate-700 bg-slate-950/60 p-3"><div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-slate-100"><span className="font-mono text-cyan-300">{record.id}</span> - {record.title}</p><span className="shrink-0 rounded-full bg-indigo-400/15 px-2 py-1 text-xs font-bold text-indigo-200">{record.relevance_score}% Match</span></div><p className="mt-2 text-xs text-slate-500">Resolved: {record.resolution_date}</p><blockquote className="mt-2 border-l-2 border-indigo-400/60 pl-3 text-sm leading-6 text-slate-400">{record.close_notes_snippet}</blockquote></article>)}</div></section>
}

function SentimentBadge({ ticket }) {
  if (!['INC', 'RITM'].includes(ticket.type) || !ticket.customer_sentiment) return null
  const sentiment = ticket.customer_sentiment
  const faces = { Frustrated: '😠', Impatient: '😟', Satisfied: '😊', Neutral: '😐' }
  const critical = sentiment.status === 'Frustrated' || ticket.priority?.startsWith('1 -')
  const styles = critical ? 'border-red-500/50 bg-red-950/60 text-red-300 shadow-[0_0_12px_rgba(239,68,68,0.25)]' : sentiment.status === 'Impatient' ? 'border-amber-500/50 bg-amber-950/60 text-amber-300' : 'border-slate-700 bg-slate-800 text-slate-300'
  return <span title={sentiment.explanation} className={`rounded-full border px-2 py-1 text-xs font-bold ${styles}`}>{faces[sentiment.status] || '😐'} {sentiment.status} - {sentiment.score_pct}% Urgency Score</span>
}

export default function TicketCard({ ticket, onClose, historicalContent, onSelectTicket }) {
  const showClosure = closedStates.has(ticket.state) && ticket.close_notes
  return <article className="h-full overflow-y-auto bg-slate-900 p-6 text-slate-100"><div className="mb-6 flex items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><p className="font-mono text-sm text-cyan-300">{ticket.number || ticket.id} · {ticket.type}</p><SentimentBadge ticket={ticket} /></div><h2 className="mt-1 text-xl font-semibold">{ticket.short_description || ticket.title}</h2><p className="mt-2 text-sm text-slate-400">{ticket.description}</p><p className="mt-2 text-xs text-slate-500">Priority: {ticket.priority} {ticket.sla_remaining_mins ? `· SLA: ${ticket.sla_remaining_mins} min` : ''}</p></div>{onClose && <button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button>}</div><div className="space-y-4"><SimilarityWarning records={ticket.similar_records} /><section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">AI Solution / Resolution Breakdown</h3><p className="mt-2 text-sm leading-6 text-slate-300">{ticket.ai_resolution_guide}</p></section><TopologyTree ticket={ticket} onSelectTicket={onSelectTicket} /><WorkItemActivities ticket={ticket} />{historicalContent || <HistoricalTickets records={ticket.historical_tickets} />}{showClosure && <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Closure Notes</h3><p className="mt-2 text-sm leading-6 text-slate-400">{ticket.close_notes}</p>{ticket.close_code && <p className="mt-2 text-xs font-semibold text-emerald-300">Close Code: {ticket.close_code}</p>}</section>}<KnowledgeReferences references={ticket.knowledge_refs} /></div></article>
}

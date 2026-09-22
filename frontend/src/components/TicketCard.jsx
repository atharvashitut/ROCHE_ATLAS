import KnowledgeReferences from './KnowledgeReferences'
import TopologyTree from './TopologyTree'
import WorkItemActivities from './WorkItemActivities'

const closedStates = new Set(['Closed', 'Resolved', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped'])

function SimilarityWarning({ records }) {
  const record = records[0]
  if (!record) return null
  return <section className="rounded-xl border-2 border-amber-400/70 bg-amber-400/10 p-4 shadow-lg shadow-amber-950/20"><div className="flex items-start gap-3"><span className="text-2xl" aria-hidden="true">⚠️</span><div className="min-w-0 flex-1"><h3 className="font-semibold text-amber-100">AI Duplicate / Similarity Warning</h3><p className="mt-1 text-sm leading-6 text-amber-50">This issue looks {record.score}% similar to a P1 Problem Ticket from {record.resolution_date}: {record.id} - {record.title}. The historical state is {record.state}.</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className="rounded-lg border border-amber-300/70 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-300/15">🔗 Link to {record.id}</button><button type="button" className="rounded-lg border border-amber-300/70 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-300/15">💡 View Historical RCA</button></div></div></div></section>
}

export default function TicketCard({ ticket, onClose, historicalContent }) {
  const showClosure = closedStates.has(ticket.state) && ticket.close_notes
  return <article className="h-full overflow-y-auto bg-slate-900 p-6 text-slate-100"><div className="mb-6 flex items-start justify-between gap-4"><div><p className="font-mono text-sm text-cyan-300">{ticket.number || ticket.id} · {ticket.type}</p><h2 className="mt-1 text-xl font-semibold">{ticket.short_description || ticket.title}</h2><p className="mt-2 text-sm text-slate-400">{ticket.description}</p><p className="mt-2 text-xs text-slate-500">Priority: {ticket.priority} {ticket.sla_remaining_mins ? `· SLA: ${ticket.sla_remaining_mins} min` : ''}</p></div>{onClose && <button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button>}</div><div className="space-y-4"><SimilarityWarning records={ticket.similar_records} /><section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">AI Solution / Resolution Breakdown</h3><p className="mt-2 text-sm leading-6 text-slate-300">{ticket.ai_resolution_guide}</p></section><TopologyTree ticket={ticket} /><WorkItemActivities ticket={ticket} />{historicalContent}{showClosure && <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Closure Notes</h3><p className="mt-2 text-sm leading-6 text-slate-400">{ticket.close_notes}</p>{ticket.close_code && <p className="mt-2 text-xs font-semibold text-emerald-300">Close Code: {ticket.close_code}</p>}</section>}<KnowledgeReferences references={ticket.knowledge_refs} /></div></article>
}

import { useState } from 'react'
import { fetchTicket, queryCopilot } from '../api'
import KnowledgeReferences from './KnowledgeReferences'
import TicketCard from './TicketCard'
import TopologyTree from './TopologyTree'
import WorkItemActivities from './WorkItemActivities'

const quickActions = [
  { label: 'Generate CR', action: 'generate_cr', prompt: 'Generate a change request draft.' },
  { label: 'Generate RCA', action: 'generate_rca', prompt: 'Generate a root cause analysis draft.' },
]
const closedStates = new Set(['Closed', 'Resolved', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped'])
const sourceStyleBySystem = {
  ServiceNow: { badge: '🟢 ServiceNow KBA', className: 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40' },
  'Veeva Vault': { badge: '🟣 Veeva Vault QMS', className: 'bg-purple-950/60 text-purple-300 border-purple-500/40' },
  'HP ALM': { badge: '🔴 HP ALM Defect', className: 'bg-rose-950/60 text-rose-300 border-rose-500/40' },
  'Google Drive': { badge: '🔵 Google Drive KT', className: 'bg-sky-950/60 text-sky-300 border-sky-500/40' },
}

function ReferencedSources({ sources = [] }) {
  if (!sources.length) return null

  return <section className="mt-4 rounded-lg border border-slate-700 bg-slate-900/70 p-3">
    <p className="text-xs font-semibold uppercase tracking-wider text-slate-200">📚 Referenced Enterprise Sources</p>
    <div className="mt-3 space-y-2">
      {sources.map((source) => {
        const style = sourceStyleBySystem[source.system] || { badge: source.system, className: 'border-slate-600 bg-slate-800 text-slate-300' }
        return <article key={source.id} className="rounded-md border border-slate-700 bg-slate-950/50 p-3">
          <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${style.className}`}>{style.badge}</span>
          <p className="mt-2 text-sm font-medium text-slate-100">{source.id} · {source.title}</p>
          <a href={source.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex rounded-md border border-cyan-500/40 px-2.5 py-1 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/10">View Document ↗</a>
        </article>
      })}
    </div>
  </section>
}

export default function Chat() {
  const [messages, setMessages] = useState([{ role: 'assistant', text: 'I am ATLAS Co-Pilot. Ask about the current ITSM workload or generate a CR/RCA draft.' }])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [selectedTicket, setSelectedTicket] = useState(null)

  async function openTicket(ticketId) {
    setError('')
    setSelectedTicket({ loading: true })
    try {
      const result = await fetchTicket(ticketId)
      setSelectedTicket(result.ticket)
    } catch (requestError) {
      setError(requestError.message)
      setSelectedTicket(null)
    }
  }

  async function submit(event, action = 'chat', preset) {
    event?.preventDefault()
    const text = preset || message.trim()
    if (!text || sending) return
    setMessages((current) => [...current, { role: 'user', text }])
    setMessage(''); setError(''); setSending(true)
    try {
      const result = await queryCopilot({ message: text, action })
      setMessages((current) => [...current, {
        role: 'assistant',
        text: result.response,
        ticket: result.ticket,
        resolutionGuide: result.ai_resolution_guide,
        knowledgeRefs: result.knowledge_refs,
        sources: result.sources,
      }])
    } catch (requestError) { setError(requestError.message) }
    finally { setSending(false) }
  }

  return <section className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-5xl flex-col px-4 py-8 sm:px-6">
    <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Conversational operations</p><h1 className="mt-2 text-3xl font-bold">ATLAS Co-Pilot</h1><p className="mt-2 text-slate-400">Turn the current incident context into clear operational next steps.</p></div>
    <div className="mt-6 flex flex-wrap gap-3">{quickActions.map((item) => <button key={item.action} type="button" disabled={sending} onClick={(event) => submit(event, item.action, item.prompt)} className="rounded-lg border border-indigo-400/60 bg-indigo-500/10 px-4 py-2 text-sm font-semibold text-indigo-100 hover:bg-indigo-500/20 disabled:opacity-50">{item.label}</button>)}</div>
    <div className="mt-6 flex-1 space-y-4 rounded-2xl border border-slate-700 bg-slate-900/70 p-5">{messages.map((item, index) => <div key={`${item.role}-${index}`} className={`max-w-3xl rounded-xl px-4 py-3 text-sm leading-6 ${item.role === 'user' ? 'ml-auto bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-200'}`}><p>{item.text}</p><ReferencedSources sources={item.sources} />{item.ticket && <div className="mt-4 space-y-3"><section className="rounded-lg border border-cyan-500/30 bg-cyan-950/20 p-3"><p className="text-xs font-semibold uppercase tracking-wider text-cyan-200">AI Solution / Resolution Breakdown</p><p className="mt-2 text-sm text-slate-300">{item.resolutionGuide}</p></section><TopologyTree ticket={item.ticket} onSelectTicket={openTicket} /><WorkItemActivities ticket={item.ticket} />{closedStates.has(item.ticket.state) && item.ticket.close_notes && <section className="rounded-lg border border-slate-700 p-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-300">Closure Notes</p><p className="mt-2 text-sm text-slate-300">{item.ticket.close_notes}</p></section>}<KnowledgeReferences references={item.knowledgeRefs} /></div>}</div>)}{sending && <p className="text-sm text-slate-400">ATLAS is drafting a response…</p>}</div>
    {error && <p className="mt-3 text-sm text-rose-300" role="alert">Unable to query co-pilot: {error}</p>}
    <form onSubmit={submit} className="mt-5 flex gap-3"><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask a question about the ITSM queue…" className="min-w-0 flex-1 rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 outline-none placeholder:text-slate-500 focus:border-cyan-400" /><button disabled={sending} className="rounded-xl bg-cyan-500 px-5 py-3 font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-60">Send</button></form>
    {selectedTicket && <div className="fixed inset-0 z-30 bg-slate-950/70" role="presentation" onMouseDown={() => setSelectedTicket(null)}><aside role="dialog" aria-modal="true" aria-label="Selected topology ticket" className="ml-auto h-full w-full max-w-2xl shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>{selectedTicket.loading ? <div className="p-6 text-slate-300">Loading complete ticket record…</div> : <TicketCard ticket={selectedTicket} onClose={() => setSelectedTicket(null)} onSelectTicket={openTicket} />}</aside></div>}
  </section>
}

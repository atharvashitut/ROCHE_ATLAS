import { useState } from 'react'
import { queryCopilot } from '../api'

const resourceLabels = { KBA: 'Copy KBA', Veeva: 'Copy Veeva', GDrive: 'Copy GDrive' }

function Topology({ ticket }) {
  const children = ticket.child_incidents?.length ? ticket.child_incidents.join(', ') : 'None'
  return <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4 text-sm">
    <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-cyan-300">Relational topology</p>
    <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
      <span className="rounded bg-cyan-400/15 px-2 py-1 text-cyan-200">Parent {ticket.parent_incident || ticket.id}</span><span className="text-slate-500">→</span>
      <span className="rounded bg-indigo-400/15 px-2 py-1 text-indigo-200">Child {children}</span><span className="text-slate-500">→</span>
      <span className="rounded bg-amber-400/15 px-2 py-1 text-amber-200">PRB {ticket.linked_problem || 'None'}</span><span className="text-slate-500">→</span>
      <span className="rounded bg-emerald-400/15 px-2 py-1 text-emerald-200">CHG {ticket.linked_change || 'None'}</span>
    </div>
  </div>
}

export default function TicketCard({ ticket, onClose }) {
  const [copyMessage, setCopyMessage] = useState('')
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState('')
  const [chatError, setChatError] = useState('')
  const [isSending, setIsSending] = useState(false)

  async function copyResource(label, value) {
    try { await navigator.clipboard.writeText(value); setCopyMessage(`${label} reference copied`) }
    catch { setCopyMessage('Clipboard access is unavailable') }
  }

  async function sendInlineChat(event) {
    event.preventDefault()
    if (!question.trim()) return
    setIsSending(true); setChatError('')
    try {
      const result = await queryCopilot({ message: question, ticketId: ticket.id })
      setReply(result.response); setQuestion('')
    } catch (error) { setChatError(error.message) }
    finally { setIsSending(false) }
  }

  return <article className="h-full overflow-y-auto bg-slate-900 p-6 text-slate-100">
    <div className="mb-6 flex items-start justify-between gap-4"><div><p className="font-mono text-sm text-cyan-300">{ticket.id} · {ticket.record_type}</p><h2 className="mt-1 text-xl font-semibold">{ticket.title}</h2><p className="mt-2 text-sm text-slate-400">{ticket.description}</p></div>{onClose && <button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button>}</div>
    <div className="space-y-4"><Topology ticket={ticket} />
      <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Latest work notes</h3><p className="mt-2 text-sm leading-6 text-slate-400">{ticket.latest_work_notes}</p></section>
      <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Closure notes</h3><p className="mt-2 text-sm leading-6 text-slate-400">{ticket.closure_notes}</p></section>
      <section><h3 className="mb-2 text-sm font-semibold">Knowledge references</h3><div className="flex flex-wrap gap-2">{Object.entries(ticket.resources || {}).map(([label, value]) => <button key={label} type="button" onClick={() => copyResource(label, value)} className="rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-cyan-200 hover:bg-slate-700">{resourceLabels[label] || `Copy ${label}`}</button>)}</div>{copyMessage && <p className="mt-2 text-xs text-emerald-300" role="status">{copyMessage}</p>}</section>
      <section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">Ask about this ticket</h3><form onSubmit={sendInlineChat} className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask for the current status…" className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-cyan-400" /><button disabled={isSending} className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-60">{isSending ? 'Asking…' : 'Ask'}</button></form>{chatError && <p className="mt-2 text-xs text-rose-300">{chatError}</p>}{reply && <p className="mt-3 rounded-lg bg-slate-950/70 p-3 text-sm leading-6 text-slate-300">{reply}</p>}</section>
    </div>
  </article>
}
